//! Path-free job metadata and pure transitions. No storage, execution or proof
//! capability is provided. A checksum authenticates neither origin nor assets.

use super::{FrozenAnalysisIdentity, FrozenAnalysisInput};
use serde::{
    de::{DeserializeSeed, MapAccess, SeqAccess, Visitor},
    Deserialize, Serialize,
};
use serde_json::Value;
use std::{collections::BTreeSet, fmt};
use ygo_api::combo::ComboAnalyzeRequest;
use ygo_domain::{validate_hand, Banlist, DeckValidationRules};
use ygo_engine_adapter::RuntimeVersions;
use ygo_search::combo::ScoringConfig;
use ygo_storage::hash;

const BINDING_DOMAIN: &str = "workbench-analysis-job-input-v1";

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AnalysisJobError {
    JsonInvalid,
    RecordInvalid,
    InputInvalid,
    BindingMismatch,
    ScoringInvalid,
    RevisionConflict,
    TimeInvalid,
    TransitionInvalid,
    RevisionExhausted,
    ReportInvalid,
}

impl AnalysisJobError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::JsonInvalid => "job_json_invalid",
            Self::RecordInvalid => "job_record_invalid",
            Self::InputInvalid => "job_input_invalid",
            Self::BindingMismatch => "job_binding_mismatch",
            Self::ScoringInvalid => "job_scoring_invalid",
            Self::RevisionConflict => "job_revision_conflict",
            Self::TimeInvalid => "job_time_invalid",
            Self::TransitionInvalid => "job_transition_invalid",
            Self::RevisionExhausted => "job_revision_exhausted",
            Self::ReportInvalid => "job_report_invalid",
        }
    }
}
impl fmt::Display for AnalysisJobError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.code())
    }
}
impl std::error::Error for AnalysisJobError {}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AnalysisJobState {
    Queued,
    Running,
    Completed,
    BudgetLimited,
    Failed,
    Cancelled,
    Interrupted,
    Unknown,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AnalysisJobFailure {
    AnalysisFailed,
    ServiceRestarted,
    CompletionUncertain,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalysisJobReportRefV1 {
    pub report_id: String,
    pub sha256: String,
    pub termination: String,
    pub verified_lines: u64,
}

impl AnalysisJobReportRefV1 {
    fn outcome(&self) -> Result<AnalysisJobState, AnalysisJobError> {
        if !hex(&self.report_id, 32) || !hex(&self.sha256, 64) {
            return Err(AnalysisJobError::ReportInvalid);
        }
        let (base, empty) = match self.termination.strip_suffix(":no_verified_lines") {
            Some(base) => (base, true),
            None => (self.termination.as_str(), false),
        };
        if empty != (self.verified_lines == 0) {
            return Err(AnalysisJobError::ReportInvalid);
        }
        match base {
            "exhausted" => Ok(AnalysisJobState::Completed),
            "node_budget" | "time_budget" | "depth_budget" => Ok(AnalysisJobState::BudgetLimited),
            _ => Err(AnalysisJobError::ReportInvalid),
        }
    }
}

/// The publisher must first validate report content, its input binding and
/// successful persistence. This event does not perform those operations.
#[derive(Clone, Debug)]
pub enum AnalysisJobEvent {
    Start,
    Cancel,
    ClassifyRestart,
    Fail(AnalysisJobFailure),
    ReportPublished(AnalysisJobReportRefV1),
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalysisJobInputV1 {
    pub draft_id: String,
    pub draft_revision: String,
    pub request: ComboAnalyzeRequest,
    pub identity: FrozenAnalysisIdentity,
    pub scoring: ScoringConfig,
    pub binding_sha256: String,
}

fn versions(identity: &FrozenAnalysisIdentity) -> RuntimeVersions {
    RuntimeVersions {
        rules: identity.rules.clone(),
        catalog: identity.catalog_id.clone(),
        banlist: identity.banlist_id.clone(),
        engine_sha256: identity.engine_sha256.clone(),
        cdb_sha256: identity.cdb_sha256.clone(),
        scripts_sha256: identity.scripts_sha256.clone(),
        core_commit: identity.core_commit.clone(),
        initializer: identity.initializer.clone(),
    }
}

impl AnalysisJobInputV1 {
    fn checksum(&self) -> Result<String, AnalysisJobError> {
        // Ordered typed tuple; neither JSON object ordering nor runtime paths
        // participate. Changes require a new domain/version.
        serde_json::to_vec(&(
            BINDING_DOMAIN,
            &self.draft_id,
            &self.draft_revision,
            &self.request,
            &self.identity,
            &self.scoring,
        ))
        .map(|bytes| hash(&bytes))
        .map_err(|_| AnalysisJobError::InputInvalid)
    }

    fn validate(&self) -> Result<(), AnalysisJobError> {
        let r = &self.request;
        let i = &self.identity;
        if !hex(&self.draft_id, 32)
            || !hex(&self.draft_revision, 64)
            || r.rules != "ocg-mr5"
            || r.rules != i.rules
            || r.catalog_id.as_deref() != Some(i.catalog_id.as_str())
            || r.banlist_id != i.banlist_id
            || !snapshot_id(&i.catalog_id, "catalog-")
            || !snapshot_id(&i.banlist_id, "banlist-")
            || i.protocol_version != 2
            || !label(&i.core_commit)
            || !label(&i.initializer)
            || [
                &i.input_sha256,
                &i.engine_sha256,
                &i.worker_sha256,
                &i.cdb_sha256,
                &i.scripts_sha256,
                &i.engine_manifest_sha256,
                &i.catalog_source_sha256,
                &i.banlist_source_sha256,
            ]
            .iter()
            .any(|s| !hex(s, 64))
            || i.catalog_source_sha256 != i.cdb_sha256
            || ygo_storage::validate_date(&r.as_of).is_err()
            || r.search.validate().is_err()
            || !r
                .deck
                .validate(
                    &Banlist::ocg("structural-only", []),
                    &DeckValidationRules::ocg(),
                )
                .is_legal()
            || r.deck
                .main
                .iter()
                .chain(&r.deck.extra)
                .chain(&r.deck.side)
                .any(|c| c.0 == 0)
            || validate_hand(&r.deck, &r.opening_hand).is_err()
        {
            return Err(AnalysisJobError::InputInvalid);
        }
        if [
            self.scoring.board_interaction,
            self.scoring.resource_advantage,
            self.scoring.follow_up,
            self.scoring.complexity,
        ]
        .iter()
        .any(|v| !v.is_finite())
        {
            return Err(AnalysisJobError::ScoringInvalid);
        }
        let old = serde_json::to_vec(&(
            &self.request,
            versions(i),
            &i.worker_sha256,
            &i.engine_manifest_sha256,
            &i.catalog_source_sha256,
            &i.banlist_source_sha256,
            &self.draft_id,
            &self.draft_revision,
        ))
        .map_err(|_| AnalysisJobError::InputInvalid)?;
        if hash(&old) != i.input_sha256
            || !hex(&self.binding_sha256, 64)
            || self.checksum()? != self.binding_sha256
        {
            return Err(AnalysisJobError::BindingMismatch);
        }
        Ok(())
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct RecordWire {
    schema_version: u16,
    kind: String,
    job_id: String,
    revision: u64,
    created_at_ms: u64,
    updated_at_ms: u64,
    input: AnalysisJobInputV1,
    state: AnalysisJobState,
    report: Option<AnalysisJobReportRefV1>,
    error_code: Option<AnalysisJobFailure>,
}

/// Immutable validated record. Use `read_json` rather than a permissive serde
/// deserializer; all transitions return a new value and never edit the input.
#[derive(Clone, Debug, Serialize)]
#[serde(transparent)]
pub struct AnalysisJobRecordV1(RecordWire);

impl AnalysisJobRecordV1 {
    pub fn new(
        job_id: String,
        frozen: &FrozenAnalysisInput,
        scoring: ScoringConfig,
        now_ms: u64,
    ) -> Result<Self, AnalysisJobError> {
        let runtime = &frozen.runtime_request;
        if runtime.versions != versions(&frozen.identity)
            || runtime.protocol_version != frozen.identity.protocol_version
            || runtime.deck != frozen.request.deck
            || runtime.opening_hand != frozen.request.opening_hand
            || runtime.seed != frozen.request.seed
        {
            return Err(AnalysisJobError::BindingMismatch);
        }
        let mut input = AnalysisJobInputV1 {
            draft_id: frozen.draft_id.clone(),
            draft_revision: frozen.draft_revision.clone(),
            request: frozen.request.clone(),
            identity: frozen.identity.clone(),
            scoring,
            binding_sha256: String::new(),
        };
        input.binding_sha256 = input.checksum()?;
        let record = Self(RecordWire {
            schema_version: 1,
            kind: "workbench_analysis_job".into(),
            job_id,
            revision: 1,
            created_at_ms: now_ms,
            updated_at_ms: now_ms,
            input,
            state: AnalysisJobState::Queued,
            report: None,
            error_code: None,
        });
        record.validate()?;
        Ok(record)
    }

    pub fn input(&self) -> &AnalysisJobInputV1 {
        &self.0.input
    }
    pub fn state(&self) -> AnalysisJobState {
        self.0.state
    }
    pub fn revision(&self) -> u64 {
        self.0.revision
    }
    pub fn job_id(&self) -> &str {
        &self.0.job_id
    }
    pub fn report(&self) -> Option<&AnalysisJobReportRefV1> {
        self.0.report.as_ref()
    }
    pub fn error_code(&self) -> Option<AnalysisJobFailure> {
        self.0.error_code
    }

    pub fn validate(&self) -> Result<(), AnalysisJobError> {
        let w = &self.0;
        if w.schema_version != 1
            || w.kind != "workbench_analysis_job"
            || !hex(&w.job_id, 32)
            || w.revision == 0
        {
            return Err(AnalysisJobError::RecordInvalid);
        }
        if w.updated_at_ms < w.created_at_ms {
            return Err(AnalysisJobError::TimeInvalid);
        }
        w.input.validate()?;
        let valid = match w.state {
            AnalysisJobState::Queued => {
                w.revision == 1
                    && w.updated_at_ms == w.created_at_ms
                    && w.report.is_none()
                    && w.error_code.is_none()
            }
            AnalysisJobState::Running => {
                w.revision == 2 && w.report.is_none() && w.error_code.is_none()
            }
            AnalysisJobState::Cancelled => {
                w.revision == 2 && w.report.is_none() && w.error_code.is_none()
            }
            AnalysisJobState::Interrupted => {
                w.revision == 2
                    && w.report.is_none()
                    && w.error_code == Some(AnalysisJobFailure::ServiceRestarted)
            }
            AnalysisJobState::Failed => {
                w.revision == 3
                    && w.report.is_none()
                    && w.error_code == Some(AnalysisJobFailure::AnalysisFailed)
            }
            AnalysisJobState::Unknown => {
                w.revision == 3
                    && w.report.is_none()
                    && w.error_code == Some(AnalysisJobFailure::CompletionUncertain)
            }
            AnalysisJobState::Completed | AnalysisJobState::BudgetLimited => {
                w.revision == 3
                    && w.error_code.is_none()
                    && w.report.as_ref().is_some_and(|r| {
                        r.outcome() == Ok(w.state)
                            && r.verified_lines <= w.input.request.search.top_k as u64
                    })
            }
        };
        if !valid {
            return Err(AnalysisJobError::RecordInvalid);
        }
        Ok(())
    }

    pub fn transition(
        &self,
        expected_revision: u64,
        event: AnalysisJobEvent,
        now_ms: u64,
    ) -> Result<Self, AnalysisJobError> {
        self.validate()?;
        if expected_revision != self.0.revision {
            return Err(AnalysisJobError::RevisionConflict);
        }
        if now_ms < self.0.updated_at_ms {
            return Err(AnalysisJobError::TimeInvalid);
        }
        let mut next = self.clone();
        let w = &mut next.0;
        match (w.state, event) {
            (AnalysisJobState::Queued, AnalysisJobEvent::Start) => {
                w.state = AnalysisJobState::Running
            }
            (AnalysisJobState::Queued, AnalysisJobEvent::Cancel) => {
                w.state = AnalysisJobState::Cancelled
            }
            (AnalysisJobState::Queued, AnalysisJobEvent::ClassifyRestart) => {
                w.state = AnalysisJobState::Interrupted;
                w.error_code = Some(AnalysisJobFailure::ServiceRestarted);
            }
            (AnalysisJobState::Running, AnalysisJobEvent::ClassifyRestart) => {
                w.state = AnalysisJobState::Unknown;
                w.error_code = Some(AnalysisJobFailure::CompletionUncertain);
            }
            (
                AnalysisJobState::Running,
                AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
            ) => {
                w.state = AnalysisJobState::Failed;
                w.error_code = Some(AnalysisJobFailure::AnalysisFailed);
            }
            (AnalysisJobState::Running, AnalysisJobEvent::ReportPublished(report)) => {
                w.state = report.outcome()?;
                w.report = Some(report);
            }
            _ => return Err(AnalysisJobError::TransitionInvalid),
        }
        w.revision = w
            .revision
            .checked_add(1)
            .ok_or(AnalysisJobError::RevisionExhausted)?;
        w.updated_at_ms = now_ms;
        next.validate()?;
        Ok(next)
    }

    pub fn encode_json(&self) -> Result<Vec<u8>, AnalysisJobError> {
        self.validate()?;
        serde_json::to_vec_pretty(&self.0).map_err(|_| AnalysisJobError::JsonInvalid)
    }

    pub fn read_json(bytes: &[u8]) -> Result<Self, AnalysisJobError> {
        let mut parser = serde_json::Deserializer::from_slice(bytes);
        Unique
            .deserialize(&mut parser)
            .map_err(|_| AnalysisJobError::JsonInvalid)?;
        parser.end().map_err(|_| AnalysisJobError::JsonInvalid)?;
        let raw: Value =
            serde_json::from_slice(bytes).map_err(|_| AnalysisJobError::JsonInvalid)?;
        let wire: RecordWire =
            serde_json::from_value(raw.clone()).map_err(|_| AnalysisJobError::JsonInvalid)?;
        let canonical = serde_json::to_value(&wire).map_err(|_| AnalysisJobError::JsonInvalid)?;
        // Existing nested request types have defaults. Require every field and
        // reject unknowns recursively without changing their legacy contracts.
        if !same_shape(&raw, &canonical) {
            return Err(AnalysisJobError::JsonInvalid);
        }
        let record = Self(wire);
        record.validate()?;
        Ok(record)
    }
}

fn hex(value: &str, len: usize) -> bool {
    value.len() == len
        && value
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
fn snapshot_id(value: &str, prefix: &str) -> bool {
    value.strip_prefix(prefix).is_some_and(|h| hex(h, 64))
}
fn label(value: &str) -> bool {
    value.len() <= 128
        && value
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"._-".contains(&b))
}
fn same_shape(a: &Value, b: &Value) -> bool {
    match (a, b) {
        (Value::Object(a), Value::Object(b)) => {
            a.len() == b.len()
                && a.iter()
                    .all(|(k, v)| b.get(k).is_some_and(|w| same_shape(v, w)))
        }
        (Value::Array(a), Value::Array(b)) => {
            a.len() == b.len() && a.iter().zip(b).all(|(v, w)| same_shape(v, w))
        }
        _ => true,
    }
}

// Check duplicates before serde can discard them, including nested legacy
// request types. Messages from this parser never escape as public errors.
struct Unique;
impl<'de> DeserializeSeed<'de> for Unique {
    type Value = ();
    fn deserialize<D: serde::Deserializer<'de>>(self, d: D) -> Result<(), D::Error> {
        d.deserialize_any(self)
    }
}
impl<'de> Visitor<'de> for Unique {
    type Value = ();
    fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str("unique JSON keys")
    }
    fn visit_bool<E: serde::de::Error>(self, _: bool) -> Result<(), E> {
        Ok(())
    }
    fn visit_u64<E: serde::de::Error>(self, _: u64) -> Result<(), E> {
        Ok(())
    }
    fn visit_i64<E: serde::de::Error>(self, _: i64) -> Result<(), E> {
        Ok(())
    }
    fn visit_f64<E: serde::de::Error>(self, _: f64) -> Result<(), E> {
        Ok(())
    }
    fn visit_str<E: serde::de::Error>(self, _: &str) -> Result<(), E> {
        Ok(())
    }
    fn visit_unit<E: serde::de::Error>(self) -> Result<(), E> {
        Ok(())
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut a: A) -> Result<(), A::Error> {
        while a.next_element_seed(Unique)?.is_some() {}
        Ok(())
    }
    fn visit_map<A: MapAccess<'de>>(self, mut a: A) -> Result<(), A::Error> {
        let mut keys = BTreeSet::new();
        while let Some(key) = a.next_key::<String>()? {
            if !keys.insert(key) {
                return Err(serde::de::Error::custom("duplicate key"));
            }
            a.next_value_seed(Unique)?;
        }
        Ok(())
    }
}
