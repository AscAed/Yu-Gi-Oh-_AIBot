//! Path-free operation metadata. Digests prove integrity, not provenance.
use super::jobs::{same_shape, strict_json_value, AnalysisJobInputV1, AnalysisJobRecordV1};
use serde::{Deserialize, Serialize};
use ygo_domain::CardId;
use ygo_search::combo::{ScoringConfig, SearchBudget};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AnalysisOperationError {
    Invalid,
    JsonInvalid,
    Conflict,
    TimeInvalid,
}
impl AnalysisOperationError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::Invalid => "analysis_operation_invalid",
            Self::JsonInvalid => "analysis_operation_json_invalid",
            Self::Conflict => "analysis_operation_conflict",
            Self::TimeInvalid => "analysis_operation_time_invalid",
        }
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum AnalysisOperationState {
    Allocated,
    Accepting,
    Accepted,
    Rejected,
    Unknown,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalysisOperationContext {
    pub scoring: ScoringConfig,
    pub default_catalog_id: String,
    pub configuration_sha256: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalysisOperationCommand {
    pub draft_id: String,
    pub draft_revision: String,
    pub opening_hand: Vec<CardId>,
    pub seed: u64,
    pub rules: String,
    pub catalog_id: Option<String>,
    pub banlist_id: String,
    pub as_of: String,
    pub search: SearchBudget,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AnalysisOperationRejection {
    pub http_status: u16,
    pub error_code: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Wire {
    schema_version: u16,
    kind: String,
    operation_id: String,
    revision: u64,
    created_at_ms: u64,
    updated_at_ms: u64,
    state: AnalysisOperationState,
    service_context: AnalysisOperationContext,
    command: Option<AnalysisOperationCommand>,
    command_sha256: Option<String>,
    job_id: Option<String>,
    frozen_input: Option<AnalysisJobInputV1>,
    frozen_binding_sha256: Option<String>,
    rejection: Option<AnalysisOperationRejection>,
    error_code: Option<String>,
}
#[derive(Clone, Debug, Serialize)]
#[serde(transparent)]
pub struct AnalysisOperationRecordV1(Wire);
fn hex(s: &str, n: usize) -> bool {
    s.len() == n
        && s.bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}
fn equal<T: Serialize>(a: &T, b: &T) -> bool {
    serde_json::to_vec(a).ok() == serde_json::to_vec(b).ok()
}
impl AnalysisOperationContext {
    pub fn validate(&self) -> Result<(), AnalysisOperationError> {
        if !self
            .default_catalog_id
            .strip_prefix("catalog-")
            .is_some_and(|s| hex(s, 64))
            || !hex(&self.configuration_sha256, 64)
            || [
                self.scoring.board_interaction,
                self.scoring.resource_advantage,
                self.scoring.follow_up,
                self.scoring.complexity,
            ]
            .iter()
            .any(|x| !x.is_finite())
        {
            return Err(AnalysisOperationError::Invalid);
        }
        Ok(())
    }
}
impl AnalysisOperationCommand {
    pub fn validate(&self) -> Result<(), AnalysisOperationError> {
        if !hex(&self.draft_id, 32)
            || !hex(&self.draft_revision, 64)
            || self.opening_hand.iter().any(|c| c.0 == 0)
            || self.rules != "ocg-mr5"
            || self.opening_hand.len() != 5
            || self.search.validate().is_err()
            || self
                .catalog_id
                .as_ref()
                .is_some_and(|x| !x.strip_prefix("catalog-").is_some_and(|h| hex(h, 64)))
            || !(self.banlist_id == "latest-ocg"
                || self
                    .banlist_id
                    .strip_prefix("banlist-")
                    .is_some_and(|h| hex(h, 64)))
            || ygo_storage::validate_date(&self.as_of).is_err()
        {
            return Err(AnalysisOperationError::Invalid);
        }
        Ok(())
    }
    pub fn checksum(
        &self,
        ctx: &AnalysisOperationContext,
    ) -> Result<String, AnalysisOperationError> {
        self.validate()?;
        ctx.validate()?;
        serde_json::to_vec(&(
            "workbench-analysis-command-v1",
            &self.draft_id,
            &self.draft_revision,
            &self.opening_hand,
            self.seed,
            &self.rules,
            &self.catalog_id,
            &self.banlist_id,
            &self.as_of,
            &self.search,
            &ctx.scoring,
            &ctx.default_catalog_id,
        ))
        .map(|b| ygo_storage::hash(&b))
        .map_err(|_| AnalysisOperationError::Invalid)
    }
}
impl AnalysisOperationRecordV1 {
    pub fn allocate(
        id: String,
        ctx: AnalysisOperationContext,
        now: u64,
    ) -> Result<Self, AnalysisOperationError> {
        let r = Self(Wire {
            schema_version: 1,
            kind: "workbench_analysis_operation".into(),
            operation_id: id,
            revision: 1,
            created_at_ms: now,
            updated_at_ms: now,
            state: AnalysisOperationState::Allocated,
            service_context: ctx,
            command: None,
            command_sha256: None,
            job_id: None,
            frozen_input: None,
            frozen_binding_sha256: None,
            rejection: None,
            error_code: None,
        });
        r.validate()?;
        Ok(r)
    }
    fn next(&self, now: u64) -> Result<Self, AnalysisOperationError> {
        self.validate()?;
        if now < self.updated_at_ms() {
            return Err(AnalysisOperationError::TimeInvalid);
        }
        let mut r = self.clone();
        r.0.revision =
            r.0.revision
                .checked_add(1)
                .ok_or(AnalysisOperationError::Invalid)?;
        r.0.updated_at_ms = now;
        Ok(r)
    }
    pub fn begin(
        &self,
        command: AnalysisOperationCommand,
        job_id: String,
        now: u64,
    ) -> Result<Self, AnalysisOperationError> {
        if self.state() != AnalysisOperationState::Allocated {
            return Err(AnalysisOperationError::Conflict);
        }
        let mut r = self.next(now)?;
        r.0.command_sha256 = Some(command.checksum(self.context())?);
        r.0.command = Some(command);
        r.0.job_id = Some(job_id);
        r.0.state = AnalysisOperationState::Accepting;
        r.validate()?;
        Ok(r)
    }
    pub fn reject(
        &self,
        command: AnalysisOperationCommand,
        status: u16,
        code: &str,
        now: u64,
    ) -> Result<Self, AnalysisOperationError> {
        if !matches!(
            self.state(),
            AnalysisOperationState::Allocated | AnalysisOperationState::Accepting
        ) {
            return Err(AnalysisOperationError::Conflict);
        }
        if self.command().is_some_and(|c| !equal(c, &command)) {
            return Err(AnalysisOperationError::Conflict);
        }
        let mut r = self.next(now)?;
        r.0.command_sha256 = Some(command.checksum(self.context())?);
        r.0.command = Some(command);
        r.0.state = AnalysisOperationState::Rejected;
        r.0.frozen_input = None;
        r.0.frozen_binding_sha256 = None;
        r.0.rejection = Some(AnalysisOperationRejection {
            http_status: status,
            error_code: code.into(),
        });
        r.0.error_code = Some(code.into());
        r.validate()?;
        Ok(r)
    }
    pub fn bind_input(
        &self,
        input: AnalysisJobInputV1,
        now: u64,
    ) -> Result<Self, AnalysisOperationError> {
        if self.state() != AnalysisOperationState::Accepting || self.frozen_input().is_some() {
            return Err(AnalysisOperationError::Conflict);
        }
        let mut r = self.next(now)?;
        r.0.frozen_binding_sha256 = Some(input.binding_sha256.clone());
        r.0.frozen_input = Some(input);
        r.validate()?;
        Ok(r)
    }
    pub fn accept(&self, now: u64) -> Result<Self, AnalysisOperationError> {
        if self.state() != AnalysisOperationState::Accepting || self.frozen_input().is_none() {
            return Err(AnalysisOperationError::Conflict);
        }
        let mut r = self.next(now)?;
        r.0.state = AnalysisOperationState::Accepted;
        r.validate()?;
        Ok(r)
    }
    pub fn mark_unknown(&self, now: u64) -> Result<Self, AnalysisOperationError> {
        if self.state() != AnalysisOperationState::Accepting {
            return Err(AnalysisOperationError::Conflict);
        }
        let mut r = self.next(now)?;
        r.0.state = AnalysisOperationState::Unknown;
        r.0.error_code = Some("analysis_commit_uncertain".into());
        r.validate()?;
        Ok(r)
    }
    pub fn operation_id(&self) -> &str {
        &self.0.operation_id
    }
    pub fn revision(&self) -> u64 {
        self.0.revision
    }
    pub fn created_at_ms(&self) -> u64 {
        self.0.created_at_ms
    }
    pub fn updated_at_ms(&self) -> u64 {
        self.0.updated_at_ms
    }
    pub fn state(&self) -> AnalysisOperationState {
        self.0.state
    }
    pub fn context(&self) -> &AnalysisOperationContext {
        &self.0.service_context
    }
    pub fn command(&self) -> Option<&AnalysisOperationCommand> {
        self.0.command.as_ref()
    }
    pub fn command_sha256(&self) -> Option<&str> {
        self.0.command_sha256.as_deref()
    }
    pub fn job_id(&self) -> Option<&str> {
        self.0.job_id.as_deref()
    }
    pub fn frozen_input(&self) -> Option<&AnalysisJobInputV1> {
        self.0.frozen_input.as_ref()
    }
    pub fn frozen_binding_sha256(&self) -> Option<&str> {
        self.0.frozen_binding_sha256.as_deref()
    }
    pub fn rejection(&self) -> Option<&AnalysisOperationRejection> {
        self.0.rejection.as_ref()
    }
    pub fn error_code(&self) -> Option<&str> {
        self.0.error_code.as_deref()
    }
    pub fn validate(&self) -> Result<(), AnalysisOperationError> {
        let w = &self.0;
        w.service_context.validate()?;
        if w.schema_version != 1
            || w.kind != "workbench_analysis_operation"
            || !hex(&w.operation_id, 32)
            || w.revision == 0
            || w.updated_at_ms < w.created_at_ms
            || w.job_id.as_ref().is_some_and(|s| !hex(s, 32))
        {
            return Err(AnalysisOperationError::Invalid);
        }
        if let Some(c) = &w.command {
            if w.command_sha256.as_deref() != Some(c.checksum(&w.service_context)?.as_str()) {
                return Err(AnalysisOperationError::Invalid);
            }
        } else if w.command_sha256.is_some() {
            return Err(AnalysisOperationError::Invalid);
        }
        if let Some(input) = &w.frozen_input {
            let job = serde_json::json!({"schema_version":1,"kind":"workbench_analysis_job","job_id":w.job_id,"revision":1,"created_at_ms":w.created_at_ms,"updated_at_ms":w.created_at_ms,"input":input,"state":"queued","report":null,"error_code":null});
            AnalysisJobRecordV1::read_json(
                &serde_json::to_vec(&job).map_err(|_| AnalysisOperationError::Invalid)?,
            )
            .map_err(|_| AnalysisOperationError::Invalid)?;
            let c = w.command.as_ref().ok_or(AnalysisOperationError::Invalid)?;
            if w.frozen_binding_sha256.as_deref() != Some(input.binding_sha256.as_str())
                || c.draft_id != input.draft_id
                || c.draft_revision != input.draft_revision
                || c.opening_hand != input.request.opening_hand
                || c.seed != input.request.seed
                || c.rules != input.request.rules
                || c.as_of != input.request.as_of
                || !equal(&c.search, &input.request.search)
                || !equal(&w.service_context.scoring, &input.scoring)
                || c.catalog_id
                    .as_ref()
                    .unwrap_or(&w.service_context.default_catalog_id)
                    != &input.identity.catalog_id
                || (c.banlist_id != "latest-ocg" && c.banlist_id != input.identity.banlist_id)
            {
                return Err(AnalysisOperationError::Invalid);
            }
        } else if w.frozen_binding_sha256.is_some() {
            return Err(AnalysisOperationError::Invalid);
        }
        use AnalysisOperationState::*;
        let valid = match w.state {
            Allocated => {
                w.revision == 1
                    && w.created_at_ms == w.updated_at_ms
                    && w.command.is_none()
                    && w.job_id.is_none()
                    && w.frozen_input.is_none()
                    && w.rejection.is_none()
                    && w.error_code.is_none()
            }
            Accepting => {
                w.command.is_some()
                    && w.job_id.is_some()
                    && w.rejection.is_none()
                    && w.error_code.is_none()
                    && if w.frozen_input.is_some() {
                        w.revision == 3
                    } else {
                        w.revision == 2
                    }
            }
            Accepted => {
                w.revision == 4
                    && w.command.is_some()
                    && w.job_id.is_some()
                    && w.frozen_input.is_some()
                    && w.rejection.is_none()
                    && w.error_code.is_none()
            }
            Rejected => {
                matches!(w.revision, 2..=4)
                    && w.command.is_some()
                    && w.frozen_input.is_none()
                    && w.rejection.as_ref().is_some_and(|r| {
                        matches!(r.http_status, 409 | 422)
                            && r.error_code
                                .as_bytes()
                                .first()
                                .is_some_and(u8::is_ascii_lowercase)
                            && r.error_code.len() <= 128
                            && r.error_code
                                .bytes()
                                .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_')
                            && w.error_code.as_deref() == Some(&r.error_code)
                    })
            }
            Unknown => {
                w.revision == if w.frozen_input.is_some() { 4 } else { 3 }
                    && w.command.is_some()
                    && w.job_id.is_some()
                    && w.rejection.is_none()
                    && w.error_code.as_deref() == Some("analysis_commit_uncertain")
            }
        };
        if !valid {
            return Err(AnalysisOperationError::Invalid);
        }
        Ok(())
    }
    pub fn encode_json(&self) -> Result<Vec<u8>, AnalysisOperationError> {
        self.validate()?;
        serde_json::to_vec_pretty(&self.0).map_err(|_| AnalysisOperationError::JsonInvalid)
    }
    pub fn read_json(bytes: &[u8]) -> Result<Self, AnalysisOperationError> {
        let raw = strict_json_value(bytes).map_err(|_| AnalysisOperationError::JsonInvalid)?;
        let wire: Wire =
            serde_json::from_value(raw.clone()).map_err(|_| AnalysisOperationError::JsonInvalid)?;
        let canonical =
            serde_json::to_value(&wire).map_err(|_| AnalysisOperationError::JsonInvalid)?;
        if !same_shape(&raw, &canonical) {
            return Err(AnalysisOperationError::JsonInvalid);
        }
        let r = Self(wire);
        r.validate()?;
        Ok(r)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn allocated_roundtrip_and_duplicate_rejection() {
        let context = AnalysisOperationContext {
            scoring: ygo_search::combo::ScoringConfig::default(),
            default_catalog_id: format!("catalog-{}", "a".repeat(64)),
            configuration_sha256: "b".repeat(64),
        };
        let record = AnalysisOperationRecordV1::allocate("c".repeat(32), context, 100).unwrap();
        let bytes = record.encode_json().unwrap();
        assert_eq!(
            AnalysisOperationRecordV1::read_json(&bytes)
                .unwrap()
                .revision(),
            1
        );
        let text = String::from_utf8(bytes).unwrap();
        assert!(AnalysisOperationRecordV1::read_json(
            text.replacen(
                "\"schema_version\": 1",
                "\"schema_version\": 1, \"schema_version\": 1",
                1
            )
            .as_bytes()
        )
        .is_err());
    }
}

#[cfg(test)]
mod corpus_tests {
    use super::*;
    #[test]
    fn shared_schema_corpus() {
        let corpus: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/workbench-analysis-operation-v1-cases.json"
        ))
        .unwrap();
        for case in corpus["cases"].as_array().unwrap() {
            let mut value = corpus["golden"].clone();
            if let Some(patches) = case["patches"].as_array() {
                for patch in patches {
                    let path = patch["pointer"].as_str().unwrap();
                    if patch["remove"].as_bool() == Some(true) {
                        let (parent, key) = path.rsplit_once('/').unwrap();
                        value
                            .pointer_mut(parent)
                            .unwrap()
                            .as_object_mut()
                            .unwrap()
                            .remove(key);
                    } else {
                        let (parent, key) = path.rsplit_once('/').unwrap();
                        value
                            .pointer_mut(parent)
                            .unwrap()
                            .as_object_mut()
                            .unwrap()
                            .insert(key.into(), patch["value"].clone());
                    }
                }
            }
            let mut text = serde_json::to_string(&value).unwrap();
            if let Some(replacements) = case["replace"].as_array() {
                for pair in replacements {
                    text = text.replacen(pair[0].as_str().unwrap(), pair[1].as_str().unwrap(), 1);
                }
            }
            if let Some(suffix) = case["suffix"].as_str() {
                text.push_str(suffix);
            }
            let bytes = text.into_bytes();
            assert_eq!(
                AnalysisOperationRecordV1::read_json(&bytes).is_ok(),
                case["schema_valid"].as_bool().unwrap(),
                "{}",
                case["name"]
            );
        }
    }
    #[test]
    fn transitions_reject_terminal_reuse_time_rollback_and_binding_changes() {
        let ctx = AnalysisOperationContext {
            scoring: ScoringConfig::default(),
            default_catalog_id: format!("catalog-{}", "a".repeat(64)),
            configuration_sha256: "b".repeat(64),
        };
        let command = AnalysisOperationCommand {
            draft_id: "d".repeat(32),
            draft_revision: "e".repeat(64),
            opening_hand: vec![CardId(1); 5],
            seed: 1,
            rules: "ocg-mr5".into(),
            catalog_id: None,
            banlist_id: "latest-ocg".into(),
            as_of: "2026-10-31".into(),
            search: SearchBudget::default(),
        };
        let initial = AnalysisOperationRecordV1::allocate("c".repeat(32), ctx, 100).unwrap();
        assert!(initial.begin(command.clone(), "f".repeat(32), 99).is_err());
        let pending = initial.begin(command.clone(), "f".repeat(32), 101).unwrap();
        assert!(pending.accept(102).is_err());
        let unknown = pending.mark_unknown(102).unwrap();
        assert!(unknown.begin(command.clone(), "f".repeat(32), 103).is_err());
        let rejected = pending
            .reject(command.clone(), 422, "opening_hand_invalid", 102)
            .unwrap();
        assert!(rejected.mark_unknown(103).is_err());
        assert!(rejected
            .reject(command.clone(), 422, "opening_hand_invalid", 103)
            .is_err());
        let mut changed = command;
        changed.seed = 2;
        assert!(pending
            .reject(changed, 422, "opening_hand_invalid", 102)
            .is_err());
        assert_eq!(initial.revision(), 1);
    }
}

#[cfg(test)]
mod strict_state_regressions {
    use super::*;
    #[test]
    fn unknown_revision_matches_binding_presence_and_error_code_starts_with_letter() {
        let corpus: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/workbench-analysis-operation-v1-cases.json"
        ))
        .unwrap();
        let golden = corpus["golden"].clone();
        for (name, pointer, replacement) in [
            ("unknown_unbound", "/revision", serde_json::json!(4)),
            ("rejected", "/error_code", serde_json::json!("1bad")),
        ] {
            let case = corpus["cases"]
                .as_array()
                .unwrap()
                .iter()
                .find(|c| c["name"] == name)
                .unwrap();
            let mut v = golden.clone();
            for p in case["patches"].as_array().unwrap() {
                let (parent, key) = p["pointer"].as_str().unwrap().rsplit_once('/').unwrap();
                v.pointer_mut(parent)
                    .unwrap()
                    .as_object_mut()
                    .unwrap()
                    .insert(key.into(), p["value"].clone());
            }
            *v.pointer_mut(pointer).unwrap() = replacement;
            if name == "rejected" {
                v["rejection"]["error_code"] = serde_json::json!("1bad");
            }
            assert!(
                AnalysisOperationRecordV1::read_json(&serde_json::to_vec(&v).unwrap()).is_err(),
                "{name}"
            );
        }
    }
}
