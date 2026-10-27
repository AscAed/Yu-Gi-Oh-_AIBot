//! Fixed seven-request Mooyan Curry option scope.
//!
//! This module owns only the Curry scope's stage graph and ledger contract. The
//! example runner remains responsible for validating the prepared report,
//! source pins, assets, and fixed research paths before opening this batch.
use crate::{
    audit_prompt_responses, curry_option_purpose, decode_frame, parse_prompt,
    validate_curry_option_prompt, validate_curry_option_slot, validate_curry_recover_result,
    Action, CallJournal, Choice, CoreEventFrame, DuelResult, DuelStatus, EngineAdapter,
    JournaledAdapter, LedgerStats, ReadOnlyJournal, RunDuelRequest, WorkerError, Zone, CORE_COMMIT,
    INITIALIZER_VERSION,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    sync::{Arc, Mutex},
    time::{SystemTime, UNIX_EPOCH},
};

const WINDOW_SECONDS: u64 = 7_200;
const WORKER_TIMEOUT_MS: u64 = 30_000;
const PLACE_MASK: u32 = 0xffff_e0ff;
const CURRY_CARD: u32 = 58_074_572;
const FORBIDDEN_RABBIT_CARD: u32 = 85_138_716;
const CURRY_ROOT: &str = "data/runtime/p1-curry-option-validation-native-2026-10-23/research";
const CURRY_CONFIRMATION_ROOT: &str =
    "data/runtime/p1-curry-option-confirmation-native-2026-10-24/research";
const CURRY_VERIFICATION_ROOT: &str =
    "data/runtime/p1-curry-option-verification-native-2026-10-25/research";
const CURRY_REVALIDATION_ROOT: &str =
    "data/runtime/p1-curry-option-revalidation-native-2026-10-26/research";
pub const CURRY_OPTION_REVALIDATION_SCOPE: &str = "curry-option-revalidation-v1";
const VALIDATION_STAGE_KIND: &str = "native_curry_option_validation_stage";
const CONFIRMATION_STAGE_KIND: &str = "native_curry_option_confirmation_stage";
const VERIFICATION_STAGE_KIND: &str = "native_curry_option_verification_stage";
const REVALIDATION_STAGE_KIND: &str = "native_curry_option_revalidation_stage";
const CURRY_MAIN_DECK: [u32; 40] = [
    58_074_572, 69_247_929, 69_247_929, 2_964_201, 2_964_201, 2_964_201, 2_971_090, 2_971_090,
    2_971_090, 3_797_883, 3_797_883, 3_797_883, 4_035_199, 4_035_199, 4_035_199, 4_179_849,
    4_179_849, 4_179_849, 4_392_470, 4_392_470, 4_392_470, 6_368_038, 6_368_038, 6_368_038,
    6_631_034, 6_631_034, 6_631_034, 6_740_720, 6_740_720, 6_740_720, 7_562_372, 7_562_372,
    7_562_372, 8_353_769, 8_353_769, 8_353_769, 9_540_040, 9_540_040, 9_540_040, 10_538_007,
];
const CURRY_EXTRA_DECK: [u32; 3] = [84_013_237, 71_594_310, 77_637_979];

#[derive(Clone, Copy)]
struct CurryOptionSpec {
    scope: &'static str,
    key_prefix: &'static str,
    stage_kind: &'static str,
    research_root: &'static str,
    limit: usize,
}

const VALIDATION_SPEC: CurryOptionSpec = CurryOptionSpec {
    scope: crate::CURRY_OPTION_SCOPE,
    key_prefix: "curry-option-validation",
    stage_kind: VALIDATION_STAGE_KIND,
    research_root: CURRY_ROOT,
    limit: 7,
};

const CONFIRMATION_SPEC: CurryOptionSpec = CurryOptionSpec {
    scope: crate::CURRY_OPTION_CONFIRMATION_SCOPE,
    key_prefix: "curry-option-confirmation",
    stage_kind: CONFIRMATION_STAGE_KIND,
    research_root: CURRY_CONFIRMATION_ROOT,
    limit: 7,
};

const VERIFICATION_SPEC: CurryOptionSpec = CurryOptionSpec {
    scope: crate::CURRY_OPTION_VERIFICATION_SCOPE,
    key_prefix: "curry-option-verification",
    stage_kind: VERIFICATION_STAGE_KIND,
    research_root: CURRY_VERIFICATION_ROOT,
    limit: 7,
};

const REVALIDATION_SPEC: CurryOptionSpec = CurryOptionSpec {
    scope: CURRY_OPTION_REVALIDATION_SCOPE,
    key_prefix: "curry-option-revalidation",
    stage_kind: REVALIDATION_STAGE_KIND,
    research_root: CURRY_REVALIDATION_ROOT,
    limit: 7,
};

/// Return the single fixed research root owned by the Curry option scope.
pub fn curry_option_validation_research_root() -> Result<std::path::PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(VALIDATION_SPEC.research_root))
}

/// Return the single fixed research root owned by the Curry confirmation scope.
pub fn curry_option_confirmation_research_root() -> Result<std::path::PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(CONFIRMATION_SPEC.research_root))
}

/// Return the single fixed research root owned by the Curry verification scope.
pub fn curry_option_verification_research_root() -> Result<std::path::PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(VERIFICATION_SPEC.research_root))
}

/// Return the single fixed research root owned by the Curry revalidation scope.
pub fn curry_option_revalidation_research_root() -> Result<std::path::PathBuf, WorkerError> {
    Ok(std::env::current_dir()
        .map_err(|_| fail("current directory unavailable"))?
        .join(REVALIDATION_SPEC.research_root))
}

fn fail(message: &str) -> WorkerError {
    WorkerError::new("curry_option_gate", "curry_option_batch", message)
}

fn value<T: Serialize>(value: &T) -> Result<Value, WorkerError> {
    serde_json::to_value(value).map_err(|_| fail("serialization failed"))
}

fn now() -> Result<u64, WorkerError> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .map_err(|_| fail("system clock predates Unix epoch"))
}

/// The fixed predecessor graph; the two response branches diverge after stage 3.
pub fn curry_option_parent_stage(stage: u8) -> Result<Option<u8>, WorkerError> {
    match stage {
        1 => Ok(None),
        2 => Ok(Some(1)),
        3 => Ok(Some(2)),
        4 => Ok(Some(3)),
        5 => Ok(Some(4)),
        6 => Ok(Some(3)),
        7 => Ok(Some(6)),
        _ => Err(fail("stage outside fixed seven-call scope")),
    }
}

/// Whether a new worker request may be charged at `now` under the immutable
/// 2-hour window. Exactly thirty seconds remaining is insufficient.
pub fn curry_option_window_allows_request(started: u64, at: u64) -> bool {
    let Some(deadline) = started.checked_add(WINDOW_SECONDS) else {
        return false;
    };
    at >= started && at.checked_add(30).is_some_and(|limit| limit < deadline)
}

/// Whether an outcome completed before the fixed window expired.
pub fn curry_option_window_allows_result(started: u64, at: u64) -> bool {
    started
        .checked_add(WINDOW_SECONDS)
        .is_some_and(|deadline| at >= started && at < deadline)
}

fn intent_key(spec: CurryOptionSpec, stage: u8) -> String {
    format!("immutable/{}/intent/{stage}", spec.key_prefix)
}
fn evidence_key(spec: CurryOptionSpec, stage: u8) -> String {
    format!("immutable/{}/evidence/{stage}", spec.key_prefix)
}
fn assets_key(spec: CurryOptionSpec, stage: u8) -> String {
    format!("immutable/{}/assets/{stage}", spec.key_prefix)
}
fn start_key(spec: CurryOptionSpec) -> String {
    format!("immutable/{}/start", spec.key_prefix)
}

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    stage: u8,
    request: RunDuelRequest,
}

/// Accounting and evidence access common to mutable execution and immutable
/// recorded verification. It deliberately has no mutation methods.
trait JournalView {
    fn checkpoint(&self, key: &str) -> Result<Option<Value>, WorkerError>;
    fn checkpoint_consumed(&self, key: &str) -> Result<Option<usize>, WorkerError>;
    fn checkpoint_budget(&self, key: &str) -> Result<Option<LedgerStats>, WorkerError>;
    fn checkpoint_sequence(&self, key: &str) -> Result<Option<String>, WorkerError>;
    fn load(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError>;
}

impl JournalView for CallJournal {
    fn checkpoint(&self, key: &str) -> Result<Option<Value>, WorkerError> {
        CallJournal::checkpoint(self, key)
    }
    fn checkpoint_consumed(&self, key: &str) -> Result<Option<usize>, WorkerError> {
        CallJournal::checkpoint_consumed(self, key)
    }
    fn checkpoint_budget(&self, key: &str) -> Result<Option<LedgerStats>, WorkerError> {
        CallJournal::checkpoint_budget(self, key)
    }
    fn checkpoint_sequence(&self, key: &str) -> Result<Option<String>, WorkerError> {
        CallJournal::checkpoint_charged_sequence_id(self, key)
    }
    fn load(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        CallJournal::load_outcome(self, call_id, request)
    }
}

impl JournalView for ReadOnlyJournal {
    fn checkpoint(&self, key: &str) -> Result<Option<Value>, WorkerError> {
        ReadOnlyJournal::checkpoint(self, key)
    }
    fn checkpoint_consumed(&self, key: &str) -> Result<Option<usize>, WorkerError> {
        ReadOnlyJournal::checkpoint_consumed(self, key)
    }
    fn checkpoint_budget(&self, key: &str) -> Result<Option<LedgerStats>, WorkerError> {
        ReadOnlyJournal::checkpoint_budget(self, key)
    }
    fn checkpoint_sequence(&self, key: &str) -> Result<Option<String>, WorkerError> {
        ReadOnlyJournal::checkpoint_charged_sequence_id(self, key)
    }
    fn load(
        &self,
        call_id: u64,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        ReadOnlyJournal::load_outcome(self, call_id, request)
    }
}

/// Fixed-scope owner of the Curry call journal. This type does not validate the
/// prepared report or live assets; the dedicated runner must do that before it
/// opens the scope or charges a call.
pub struct CurryOptionBatch {
    journal: Arc<CallJournal>,
    context: String,
    started: u64,
    spec: CurryOptionSpec,
    gate: Mutex<()>,
}

impl CurryOptionBatch {
    /// Opens only the fixed Curry scope with seven call slots.
    pub fn open(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, VALIDATION_SPEC)
    }

    /// Opens only the fixed Curry confirmation scope with seven call slots.
    pub fn open_confirmation(
        path: &Path,
        context: &str,
        started: u64,
    ) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, CONFIRMATION_SPEC)
    }

    /// Opens only the fixed Curry verification scope with seven call slots.
    pub fn open_verification(
        path: &Path,
        context: &str,
        started: u64,
    ) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, VERIFICATION_SPEC)
    }

    /// Opens only the fixed Curry revalidation scope with seven call slots.
    pub fn open_revalidation(
        path: &Path,
        context: &str,
        started: u64,
    ) -> Result<Self, WorkerError> {
        Self::open_with_spec(path, context, started, REVALIDATION_SPEC)
    }

    fn open_with_spec(
        path: &Path,
        context: &str,
        started: u64,
        spec: CurryOptionSpec,
    ) -> Result<Self, WorkerError> {
        if context.is_empty() || started > now()? {
            return Err(fail("invalid Curry context or start time"));
        }
        let journal = CallJournal::open(path, spec.scope, context, spec.limit)?;
        let key = start_key(spec);
        match journal.checkpoint(&key)? {
            Some(saved) if saved != json!(started) => return Err(fail("start time changed")),
            Some(_) => {}
            None => journal.save_checkpoint(&key, &json!(started))?,
        }
        Ok(Self {
            journal,
            context: context.to_owned(),
            started,
            spec,
            gate: Mutex::new(()),
        })
    }

    pub fn context(&self) -> &str {
        &self.context
    }

    pub fn started_at(&self) -> u64 {
        self.started
    }

    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        self.journal.stats()
    }

    pub fn verify(&self) -> Result<(), WorkerError> {
        if self.journal.checkpoint(&start_key(self.spec))? != Some(json!(self.started)) {
            return Err(fail("Curry start checkpoint differs"));
        }
        self.journal.verify()
    }

    pub fn require_time(&self) -> Result<(), WorkerError> {
        self.require_time_at(now()?)
    }

    pub fn require_time_at(&self, at: u64) -> Result<(), WorkerError> {
        if curry_option_window_allows_request(self.started, at) {
            Ok(())
        } else {
            Err(fail("window has less than thirty seconds remaining"))
        }
    }

    pub fn evidence(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        curry_option_parent_stage(stage)?;
        self.journal
            .checkpoint(&evidence_key(self.spec, stage))?
            .map(|value| {
                value
                    .get("receipt")
                    .cloned()
                    .ok_or_else(|| fail("evidence receipt missing"))
            })
            .transpose()
    }

    pub fn has_intent(&self, stage: u8) -> Result<bool, WorkerError> {
        curry_option_parent_stage(stage)?;
        Ok(self
            .journal
            .checkpoint(&intent_key(self.spec, stage))?
            .is_some())
    }

    fn intent(&self, stage: u8) -> Result<Option<Intent>, WorkerError> {
        self.journal
            .checkpoint(&intent_key(self.spec, stage))?
            .map(|saved| serde_json::from_value(saved).map_err(|_| fail("intent malformed")))
            .transpose()
    }

    pub fn load_outcome(
        &self,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        curry_option_parent_stage(stage)?;
        let Some(intent) = self.intent(stage)? else {
            return Ok(None);
        };
        if value(&intent.request)? != value(request)? {
            return Err(fail("immutable request differs from charged intent"));
        }
        self.journal.load_outcome(u64::from(stage), request)
    }

    /// Return the exact child request implied by an already stored successful
    /// parent. Stage 5/7 repeat their paired execution request without edits.
    pub fn derive_request(&self, stage: u8) -> Result<RunDuelRequest, WorkerError> {
        let parent_stage = curry_option_parent_stage(stage)?
            .ok_or_else(|| fail("stage 1 has no parent request"))?;
        let parent = self
            .evidence(parent_stage)?
            .ok_or_else(|| fail("successful parent receipt missing"))?;
        self.verify_evidence(parent_stage, &parent)?;
        if parent["successful"] != true {
            return Err(fail("parent receipt did not pass"));
        }
        derive_request_from_receipt(stage, &parent)
    }

    pub fn validate_request(&self, stage: u8, request: &RunDuelRequest) -> Result<(), WorkerError> {
        curry_option_parent_stage(stage)?;
        validate_candidate_request(request)?;
        if stage == 1 {
            if !request.decisions.is_empty() {
                return Err(fail("stage 1 must be the empty-decision candidate prefix"));
            }
            return Ok(());
        }
        let expected = self.derive_request(stage)?;
        if value(&expected)? != value(request)? {
            return Err(fail("request is not the exact public-parent derivation"));
        }
        Ok(())
    }

    pub fn save_assets_before(&self, stage: u8, identity: &Value) -> Result<(), WorkerError> {
        curry_option_parent_stage(stage)?;
        self.journal
            .save_checkpoint(&assets_key(self.spec, stage), identity)
    }

    pub fn assets_before(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        curry_option_parent_stage(stage)?;
        self.journal.checkpoint(&assets_key(self.spec, stage))
    }

    pub fn verify_evidence(&self, stage: u8, receipt: &Value) -> Result<(), WorkerError> {
        verify_evidence_inner(
            &*self.journal,
            stage,
            &self.context,
            self.started,
            self.spec,
            receipt,
            &mut BTreeSet::new(),
        )
    }

    /// Record an outcome only after the caller's post-call asset scan. Failed
    /// engine or validation outcomes are still immutably receipted.
    pub fn record_evidence(
        &self,
        stage: u8,
        request: &RunDuelRequest,
        outcome: &Result<DuelResult, WorkerError>,
        assets_before: &Value,
        assets_after: Option<&Value>,
    ) -> Result<Value, WorkerError> {
        self.validate_request(stage, request)?;
        let journaled = self
            .load_outcome(stage, request)?
            .ok_or_else(|| fail("charged outcome is missing or unresolved"))?;
        if value(&journaled)? != value(outcome)? {
            return Err(fail("outcome differs from charged journal result"));
        }
        if self.assets_before(stage)?.as_ref() != Some(assets_before) {
            return Err(fail("precharge asset identity is not journal-bound"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|error| error.message.clone())
            .and_then(|result| validate_curry_option_result(stage, request, result));
        let stats = self.stats()?;
        let checkpoint = evidence_key(self.spec, stage);
        // Freeze the authenticated ledger state first. The evidence checkpoint
        // containing that prefix does not exist until the final save below.
        let consumed = stats.consumed;
        let sequence = self.journal.charged_sequence_id()?;
        let ledger = stats;
        if consumed != stage as usize
            || ledger.limit != self.spec.limit
            || ledger.completed != consumed
            || ledger.unknown != 0
            || ledger.reserved != 0
            || ledger.abandoned != 0
        {
            return Err(fail("current ledger is not the exact Curry stage prefix"));
        }
        let replay = self.replay_match(stage, outcome)?;
        let result_at = now().ok();
        let in_time =
            result_at.is_some_and(|at| curry_option_window_allows_result(self.started, at));
        let assets_unchanged = assets_after == Some(assets_before);
        let settled = ledger.completed == ledger.consumed
            && ledger.unknown == 0
            && ledger.reserved == 0
            && ledger.abandoned == 0;
        let successful = validation.is_ok()
            && assets_unchanged
            && settled
            && in_time
            && replay != Value::Bool(false);
        let diagnostic = if outcome.is_err() {
            Some("engine_or_journal_error")
        } else if validation.is_err() {
            Some("unexpected_intermediate_prompt")
        } else if assets_after.is_none() {
            Some("asset_postscan_missing")
        } else if !assets_unchanged {
            Some("asset_identity_drift")
        } else if !settled {
            Some("unresolved_consumption")
        } else if replay == Value::Bool(false) {
            Some("independent_replay_mismatch")
        } else if !in_time {
            Some("window_exhausted")
        } else {
            None
        };
        let receipt = json!({
            "schema_version": 1,
            "kind": self.spec.stage_kind,
            "scope": self.spec.scope,
            "context": self.context,
            "stage": stage,
            "request": request,
            "result": outcome,
            "validation": validation,
            "assets_before": assets_before,
            "assets_after": assets_after,
            "assets_unchanged": assets_unchanged,
            "ledger": ledger,
            "consumed_prefix": consumed,
            "charged_sequence_id": sequence,
            "started_at": self.started,
            "result_at": result_at,
            "window_valid_at_result": in_time,
            "independent_replay_matches": replay,
            "successful": successful,
            "diagnostic": diagnostic,
            "proof_ready": false,
            "complete_action_coverage": false,
            "global_optimality": false,
            "native_probability_verified": false
        });
        self.journal
            .save_checkpoint(&checkpoint, &json!({"receipt": receipt}))?;
        self.verify_evidence(stage, &receipt)?;
        Ok(receipt)
    }

    /// Charge exactly the next stage. The example runner should first persist
    /// the request and seal, preflight the fixed inputs/assets, and save the
    /// precharge asset snapshot.
    pub fn run<A: EngineAdapter>(
        &self,
        adapter: A,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<DuelResult, WorkerError> {
        let _guard = self.gate.lock().map_err(|_| fail("poisoned stage gate"))?;
        self.validate_request(stage, request)?;
        self.require_time()?;
        let stats = self.stats()?;
        validate_curry_option_slot(stage, &stats)?;
        if self.intent(stage)?.is_some() {
            return Err(fail(
                "stage intent exists; retrying a worker call is forbidden",
            ));
        }
        if self.evidence(stage)?.is_some() {
            return Err(fail("stage evidence already exists"));
        }
        if self.assets_before(stage)?.is_none() {
            return Err(fail("precharge asset identity is missing"));
        }
        if stage > 1 {
            let parent_stage = curry_option_parent_stage(stage)?.unwrap();
            let parent = self
                .evidence(parent_stage)?
                .ok_or_else(|| fail("parent receipt missing"))?;
            self.verify_evidence(parent_stage, &parent)?;
            if parent["successful"] != true {
                return Err(fail("parent receipt did not pass"));
            }
        }
        self.journal.save_checkpoint(
            &intent_key(self.spec, stage),
            &value(&Intent {
                stage,
                request: request.clone(),
            })?,
        )?;
        JournaledAdapter::new(adapter, self.journal.clone(), curry_option_purpose(stage)?)
            .run(request)
    }

    fn replay_match(
        &self,
        stage: u8,
        outcome: &Result<DuelResult, WorkerError>,
    ) -> Result<Value, WorkerError> {
        if !matches!(stage, 5 | 7) {
            return Ok(Value::Null);
        }
        let execution_stage = if stage == 5 { 4 } else { 6 };
        let parent = self
            .evidence(execution_stage)?
            .ok_or_else(|| fail("execution receipt for replay branch missing"))?;
        let previous: Result<DuelResult, WorkerError> =
            serde_json::from_value(parent["result"].clone())
                .map_err(|_| fail("execution result is malformed"))?;
        Ok(json!(match (&previous, outcome) {
            (Ok(left), Ok(right)) => curry_option_replay_matches(left, right),
            _ => false,
        }))
    }
}

/// Pure recorded verifier: it accepts only a read-only journal view, does not
/// open/recover a mutable batch, does not publish missing receipts, and does
/// not inspect the clock.
pub fn verify_curry_option_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_curry_option_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        VALIDATION_SPEC,
    )
}

/// Verify a Curry confirmation receipt using its fixed isolated scope.
/// This path is read-only and remains valid after the native window expires.
pub fn verify_curry_option_confirmation_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_curry_option_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        CONFIRMATION_SPEC,
    )
}

/// Verify a Curry option verification receipt using its fixed isolated scope.
/// This path is read-only and remains valid after the native window expires.
pub fn verify_curry_option_verification_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_curry_option_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        VERIFICATION_SPEC,
    )
}

/// Verify a Curry option revalidation receipt using its fixed isolated scope.
/// This path is read-only and remains valid after the native window expires.
pub fn verify_curry_option_revalidation_recorded(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
) -> Result<(), WorkerError> {
    verify_curry_option_recorded_with_spec(
        journal,
        stage,
        context,
        started,
        receipt,
        REVALIDATION_SPEC,
    )
}

fn verify_curry_option_recorded_with_spec(
    journal: &ReadOnlyJournal,
    stage: u8,
    context: &str,
    started: u64,
    receipt: &Value,
    spec: CurryOptionSpec,
) -> Result<(), WorkerError> {
    if context.is_empty() || journal.checkpoint(&start_key(spec))? != Some(json!(started)) {
        return Err(fail("read-only Curry start binding differs"));
    }
    verify_evidence_inner(
        journal,
        stage,
        context,
        started,
        spec,
        receipt,
        &mut BTreeSet::new(),
    )?;
    journal.verify()
}

fn verify_evidence_inner<J: JournalView>(
    journal: &J,
    stage: u8,
    context: &str,
    started: u64,
    spec: CurryOptionSpec,
    receipt: &Value,
    active: &mut BTreeSet<u8>,
) -> Result<(), WorkerError> {
    curry_option_parent_stage(stage)?;
    if !active.insert(stage) {
        return Err(fail("Curry parent cycle"));
    }
    if journal.checkpoint(&start_key(spec))? != Some(json!(started)) {
        return Err(fail("immutable Curry start checkpoint differs"));
    }
    if receipt["schema_version"] != 1
        || receipt["kind"] != spec.stage_kind
        || receipt["scope"] != spec.scope
        || receipt["stage"] != json!(stage)
        || receipt["context"] != context
        || receipt["started_at"] != json!(started)
    {
        return Err(fail("receipt scope binding differs"));
    }
    let request: RunDuelRequest = serde_json::from_value(receipt["request"].clone())
        .map_err(|_| fail("receipt request is malformed"))?;
    let intent: Intent = journal
        .checkpoint(&intent_key(spec, stage))?
        .ok_or_else(|| fail("immutable intent missing"))
        .and_then(|value| serde_json::from_value(value).map_err(|_| fail("intent malformed")))?;
    if intent.stage != stage || value(&intent.request)? != value(&request)? {
        return Err(fail("receipt request differs from immutable intent"));
    }

    if let Some(parent_stage) = curry_option_parent_stage(stage)? {
        let parent = journal
            .checkpoint(&evidence_key(spec, parent_stage))?
            .and_then(|value| value.get("receipt").cloned())
            .ok_or_else(|| fail("recorded parent receipt missing"))?;
        verify_evidence_inner(
            journal,
            parent_stage,
            context,
            started,
            spec,
            &parent,
            active,
        )?;
        if parent["successful"] != true {
            return Err(fail("parent receipt did not pass"));
        }
        let expected_request = derive_request_from_receipt(stage, &parent)?;
        if value(&expected_request)? != value(&request)? {
            return Err(fail("receipt request is not exact parent derivation"));
        }
    } else {
        validate_candidate_request(&request)?;
        if !request.decisions.is_empty() {
            return Err(fail("stage 1 decision prefix differs"));
        }
    }

    let evidence = journal
        .checkpoint(&evidence_key(spec, stage))?
        .and_then(|value| value.get("receipt").cloned())
        .ok_or_else(|| fail("immutable evidence missing"))?;
    if evidence != *receipt {
        return Err(fail("published receipt differs from immutable evidence"));
    }

    let outcome = journal
        .load(u64::from(stage), &request)?
        .ok_or_else(|| fail("charged outcome is incomplete"))?;
    if value(&outcome)? != receipt["result"] {
        return Err(fail("receipt outcome differs from charged result"));
    }
    let validation = outcome
        .as_ref()
        .map_err(|error| error.message.clone())
        .and_then(|result| validate_curry_option_result(stage, &request, result));
    if value(&validation)? != receipt["validation"] {
        return Err(fail("receipt validation differs from independent oracle"));
    }
    let assets_before = journal
        .checkpoint(&assets_key(spec, stage))?
        .ok_or_else(|| fail("precharge asset checkpoint missing"))?;
    if receipt["assets_before"] != assets_before {
        return Err(fail("precharge asset identity differs"));
    }
    let checkpoint = evidence_key(spec, stage);
    let prefix_stats = journal
        .checkpoint_budget(&checkpoint)?
        .ok_or_else(|| fail("ledger prefix checkpoint missing"))?;
    let prefix_consumed = journal
        .checkpoint_consumed(&checkpoint)?
        .ok_or_else(|| fail("ledger prefix count missing"))?;
    let prefix_sequence = journal
        .checkpoint_sequence(&checkpoint)?
        .ok_or_else(|| fail("ledger prefix sequence missing"))?;
    if prefix_stats
        != serde_json::from_value(receipt["ledger"].clone())
            .map_err(|_| fail("ledger stats malformed"))?
        || prefix_consumed != stage as usize
        || receipt["consumed_prefix"] != json!(prefix_consumed)
        || receipt["charged_sequence_id"] != prefix_sequence
        || prefix_stats.limit != spec.limit
        || prefix_stats.consumed != prefix_consumed
        || prefix_stats.completed != prefix_stats.consumed
        || prefix_stats.unknown != 0
        || prefix_stats.reserved != 0
        || prefix_stats.abandoned != 0
    {
        return Err(fail("receipt is not bound to exact settled ledger prefix"));
    }
    let result_at = receipt["result_at"].as_u64();
    let in_time = result_at.is_some_and(|at| curry_option_window_allows_result(started, at));
    if receipt["window_valid_at_result"] != json!(in_time) {
        return Err(fail("result window claim differs"));
    }
    let assets_unchanged = receipt["assets_unchanged"] == true
        && receipt["assets_after"].is_object()
        && receipt["assets_before"] == receipt["assets_after"];
    let replay = replay_match_from_view(journal, stage, spec, &outcome)?;
    if receipt["independent_replay_matches"] != replay {
        return Err(fail("replay comparison differs"));
    }
    let settled = prefix_stats.completed == prefix_stats.consumed
        && prefix_stats.unknown == 0
        && prefix_stats.reserved == 0
        && prefix_stats.abandoned == 0;
    let successful = validation.is_ok()
        && assets_unchanged
        && settled
        && in_time
        && replay != Value::Bool(false);
    let diagnostic = if outcome.is_err() {
        Some("engine_or_journal_error")
    } else if validation.is_err() {
        Some("unexpected_intermediate_prompt")
    } else if !assets_unchanged {
        Some("asset_identity_drift")
    } else if !settled {
        Some("unresolved_consumption")
    } else if replay == Value::Bool(false) {
        Some("independent_replay_mismatch")
    } else if !in_time {
        Some("window_exhausted")
    } else {
        None
    };
    if receipt["successful"] != json!(successful)
        || receipt["diagnostic"] != diagnostic.map(Value::from).unwrap_or(Value::Null)
        || receipt["proof_ready"] != false
        || receipt["complete_action_coverage"] != false
        || receipt["global_optimality"] != false
        || receipt["native_probability_verified"] != false
        || (matches!(stage, 1..=4 | 6) && replay != Value::Null)
        || (matches!(stage, 5 | 7) && !replay.is_boolean())
        || (matches!(stage, 5 | 7) && successful && replay != Value::Bool(true))
    {
        return Err(fail(
            "receipt success, diagnostic, or qualification flags differ",
        ));
    }
    active.remove(&stage);
    Ok(())
}

fn replay_match_from_view<J: JournalView>(
    journal: &J,
    stage: u8,
    spec: CurryOptionSpec,
    outcome: &Result<DuelResult, WorkerError>,
) -> Result<Value, WorkerError> {
    if !matches!(stage, 5 | 7) {
        return Ok(Value::Null);
    }
    let execution_stage = if stage == 5 { 4 } else { 6 };
    let parent = journal
        .checkpoint(&evidence_key(spec, execution_stage))?
        .and_then(|value| value.get("receipt").cloned())
        .ok_or_else(|| fail("replay execution receipt missing"))?;
    let previous: Result<DuelResult, WorkerError> =
        serde_json::from_value(parent["result"].clone())
            .map_err(|_| fail("replay result malformed"))?;
    Ok(json!(match (&previous, outcome) {
        (Ok(left), Ok(right)) => curry_option_replay_matches(left, right),
        _ => false,
    }))
}

fn derive_request_from_receipt(stage: u8, parent: &Value) -> Result<RunDuelRequest, WorkerError> {
    if matches!(stage, 5 | 7) {
        let expected_parent = if stage == 5 { 4 } else { 6 };
        if parent["stage"] != json!(expected_parent) || parent["successful"] != true {
            return Err(fail(
                "replay stage must repeat its successful execution request",
            ));
        }
        return serde_json::from_value(parent["request"].clone())
            .map_err(|_| fail("execution request malformed"));
    }
    let mut request: RunDuelRequest = serde_json::from_value(parent["request"].clone())
        .map_err(|_| fail("parent request malformed"))?;
    if !parent["successful"].as_bool().unwrap_or(false) {
        return Err(fail("parent stage was not successful"));
    }
    let result: Result<DuelResult, WorkerError> = serde_json::from_value(parent["result"].clone())
        .map_err(|_| fail("parent result malformed"))?;
    let result = result.map_err(|_| fail("parent result failed"))?;
    let prompt = result
        .prompt
        .as_ref()
        .ok_or_else(|| fail("parent pending prompt missing"))?;
    let choice = match stage {
        2 => unique_curry_activation(prompt)?.choice,
        3 => unique_fixed_zone(prompt)?.choice,
        4 | 6 => unique_option(prompt, if stage == 4 { 0 } else { 1 })?.choice,
        _ => return Err(fail("unsupported Curry request derivation")),
    };
    let encoded = prompt
        .encode(&choice)
        .map_err(|_| fail("parent menu does not permit fixed Curry response"))?;
    let action = prompt
        .actions
        .iter()
        .filter(|action| action.choice == choice && action.bytes == encoded)
        .count();
    if action != 1 {
        return Err(fail("parent response is not unique"));
    }
    request.decisions = result.resolved_decisions;
    request.decisions.push(crate::Decision {
        prompt_id: prompt.id,
        player: prompt.player,
        choice,
    });
    Ok(request)
}

/// Derive a fixed child from an already authenticated Curry parent receipt.
/// The caller must run `verify_curry_option_recorded` before trusting it.
pub fn derive_curry_option_request_from_receipt(
    stage: u8,
    parent: &Value,
) -> Result<RunDuelRequest, WorkerError> {
    derive_request_from_receipt(stage, parent)
}

fn unique_curry_activation(prompt: &crate::Prompt) -> Result<Action, WorkerError> {
    if prompt.opcode != 11 || prompt.player != 0 {
        return Err(fail("stage 1 did not stop at own idle"));
    }
    let actions = prompt
        .actions
        .iter()
        .filter(|action| {
            matches!(&action.choice, Choice::Command { command: 5, .. })
                && action.card_ids == [CURRY_CARD]
        })
        .collect::<Vec<_>>();
    if actions.len() != 1 {
        return Err(fail("Mooyan Curry activation is not unique"));
    }
    let action = actions[0];
    if let Choice::Command { command: 5, index } = &action.choice {
        if *index > u16::MAX as u32 || action.bytes != ((*index << 16) | 5).to_le_bytes() {
            return Err(fail("Mooyan Curry command encoding differs"));
        }
    } else {
        return Err(fail("Mooyan Curry activation choice differs"));
    }
    Ok(action.clone())
}

fn unique_fixed_zone(prompt: &crate::Prompt) -> Result<Action, WorkerError> {
    if prompt.opcode != 18 || prompt.player != 0 {
        return Err(fail("stage 2 did not stop at own opcode18"));
    }
    let matching = prompt
        .actions
        .iter()
        .filter(|action| {
            action.choice
                == (Choice::Place {
                    zones: vec![Zone {
                        player: 0,
                        location: 8,
                        sequence: 0,
                    }],
                })
                && action.bytes == [0, 8, 0]
        })
        .collect::<Vec<_>>();
    if matching.len() != 1 {
        return Err(fail("spell/trap zone zero placement is not unique"));
    }
    Ok(matching[0].clone())
}

fn unique_option(prompt: &crate::Prompt, index: u32) -> Result<Action, WorkerError> {
    if prompt.opcode != 14 || prompt.player != 0 {
        return Err(fail("stage 3 did not stop at own opcode14"));
    }
    let expected = [index as u8, 0, 0, 0];
    let matching = prompt
        .actions
        .iter()
        .filter(|action| action.choice == (Choice::Option { index }) && action.bytes == expected)
        .collect::<Vec<_>>();
    if matching.len() != 1 {
        return Err(fail("fixed Curry option is not uniquely available"));
    }
    Ok(matching[0].clone())
}

/// Validate the frozen Curry request shape without opening a journal or
/// touching assets. The dedicated runner uses this before either preflight or
/// a mutable batch is opened.
pub fn validate_curry_option_request_shape(request: &RunDuelRequest) -> Result<(), WorkerError> {
    if request.protocol_version != 2
        || request.engine.timeout_ms != WORKER_TIMEOUT_MS
        || request.probe_only
        || request.scenario.is_some()
        || request.interruption.is_some()
        || request.first_turn.is_some()
        || request.research_capture.is_some()
        || request.seed != 1
        || request
            .deck
            .main
            .iter()
            .map(|card| card.0)
            .ne(CURRY_MAIN_DECK)
        || request
            .deck
            .extra
            .iter()
            .map(|card| card.0)
            .ne(CURRY_EXTRA_DECK)
        || !request.deck.side.is_empty()
        || request.opening_hand
            != [
                crate::CardId(CURRY_CARD),
                crate::CardId(2_964_201),
                crate::CardId(2_964_201),
                crate::CardId(2_964_201),
                crate::CardId(2_971_090),
            ]
        || request
            .deck
            .main
            .iter()
            .filter(|card| card.0 == CURRY_CARD)
            .count()
            != 1
        || request
            .deck
            .main
            .iter()
            .any(|card| card.0 == FORBIDDEN_RABBIT_CARD)
        || request.versions.rules != "ocg-mr5"
        || !request.versions.catalog.is_empty()
        || !request.versions.banlist.is_empty()
        || request.versions.core_commit != CORE_COMMIT
        || request.versions.initializer != INITIALIZER_VERSION
        || !valid_hash(&request.versions.engine_sha256)
        || !valid_hash(&request.versions.cdb_sha256)
        || !valid_hash(&request.versions.scripts_sha256)
    {
        return Err(fail("request differs from frozen Curry candidate shape"));
    }
    let mut remaining = BTreeMap::new();
    for card in &request.deck.main {
        *remaining.entry(card.0).or_insert(0usize) += 1;
    }
    for card in &request.opening_hand {
        let count = remaining
            .get_mut(&card.0)
            .ok_or_else(|| fail("opening card absent from candidate main deck"))?;
        *count = count
            .checked_sub(1)
            .ok_or_else(|| fail("opening multiplicity exceeds candidate deck"))?;
    }
    Ok(())
}

fn validate_candidate_request(request: &RunDuelRequest) -> Result<(), WorkerError> {
    validate_curry_option_request_shape(request)
}

fn valid_hash(hash: &str) -> bool {
    hash.len() == 64
        && hash
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Validate a candidate result at its exact expected stopping point. All raw
/// prompts and automatic decisions are rebound to their source event frames.
pub fn validate_curry_option_result(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<Value, String> {
    curry_option_purpose(stage).map_err(|error| error.message)?;
    validate_candidate_request(request).map_err(|error| error.message)?;
    if result.status != DuelStatus::DecisionRequired
        || result.error.is_some()
        || !result.coverage_gaps.is_empty()
        || result.resolved_decisions.len() < request.decisions.len()
        || result.resolved_decisions[..request.decisions.len()] != request.decisions
        || result.versions != request.versions
    {
        return Err("Curry result is not a clean decision-required prefix".into());
    }
    let prompts = collect_prompts(result)?;
    let pending = result
        .prompt
        .as_ref()
        .ok_or("pending Curry prompt missing")?;
    let prompt_ids = prompts
        .iter()
        .map(|(_, prompt)| prompt.id)
        .collect::<BTreeSet<_>>();
    if prompt_ids.len() != prompts.len() {
        return Err("Curry result repeats a prompt identity".into());
    }
    let (pending_frame, parsed_pending) = prompts
        .iter()
        .find(|(_, prompt)| prompt.id == pending.id)
        .ok_or("pending raw Curry frame missing")?;
    if parsed_pending != pending
        || pending.player != 0
        || prompts.last().map(|(_, prompt)| prompt) != Some(pending)
        || result.events.last().map(|event| event.sequence) != Some(pending_frame.sequence)
    {
        return Err("pending Curry prompt is not the final own event".into());
    }
    if result
        .resolved_decisions
        .iter()
        .any(|decision| decision.prompt_id == pending.id)
    {
        return Err("pending Curry prompt was already marked resolved".into());
    }
    validate_decision_bindings(
        request,
        &result.resolved_decisions,
        &request.decisions,
        &prompts,
    )?;
    let resolved_ids = result
        .resolved_decisions
        .iter()
        .map(|decision| decision.prompt_id)
        .collect::<BTreeSet<_>>();
    for (_, prompt) in prompts.iter().filter(|(_, prompt)| prompt.id != pending.id) {
        if prompt.player == 1 && request.protocol_version == 2 {
            if resolved_ids.contains(&prompt.id) {
                return Err(
                    "protocol-2 opponent auto choice must remain outside resolved decisions".into(),
                );
            }
        } else if !resolved_ids.contains(&prompt.id) {
            return Err("Curry result contains an unaccounted prompt".into());
        }
    }
    for event in &result.events {
        if event.opcode == 16 {
            validate_empty_chain(event)?;
        }
    }
    validate_step_bindings(result, request, &prompts, pending.id)?;

    match stage {
        1 => {
            unique_curry_activation(pending).map_err(|error| error.message)?;
        }
        2 => validate_place_menu(pending_frame, pending)?,
        3 => validate_curry_option_prompt(pending_frame, pending)?,
        4..=7 => {
            if pending.opcode != 11 {
                return Err("Curry option branch did not stop at next own idle".into());
            }
            let option = branch_option(request).map_err(|error| error.message)?;
            let option_prompt_sequences = prompts
                .iter()
                .filter(|(_, prompt)| prompt.opcode == 14)
                .map(|(frame, _)| frame.sequence)
                .collect::<Vec<_>>();
            if option_prompt_sequences.len() != 1 {
                return Err("Curry option branch must contain exactly one opcode14 prompt".into());
            }
            validate_curry_recover_result(
                option,
                option_prompt_sequences[0],
                &result.events,
                &result.checkpoint,
            )?;
        }
        _ => unreachable!(),
    }
    Ok(json!({
        "stage": stage,
        "pending_opcode": pending.opcode,
        "raw_prompt_count": prompts.len(),
        "response_oracle_matches": true,
        "automatic_decisions_single_legal": true,
        "complete_action_coverage": false,
        "global_optimality": false
    }))
}

fn collect_prompts(result: &DuelResult) -> Result<Vec<(CoreEventFrame, crate::Prompt)>, String> {
    if result
        .events
        .windows(2)
        .any(|pair| pair[0].sequence >= pair[1].sequence)
    {
        return Err("Curry event sequence is not strictly increasing".into());
    }
    let mut prompts = Vec::new();
    for frame in &result.events {
        let decoded = decode_frame(frame.sequence, &frame.raw)?;
        if !frame.supported || frame.raw.first().copied() != Some(frame.opcode) || decoded != *frame
        {
            return Err("unsupported or raw/normalized-mismatched Curry event".into());
        }
        if matches!(frame.opcode, 11..=16 | 18 | 19 | 24 | 26) {
            let prompt = parse_prompt(frame.sequence, &frame.raw)?
                .ok_or("prompt opcode did not decode to a prompt")?;
            let recorded: crate::Prompt = serde_json::from_value(
                frame
                    .fields
                    .get("prompt")
                    .cloned()
                    .ok_or("normalized prompt missing")?,
            )
            .map_err(|_| "normalized prompt malformed")?;
            if prompt != recorded {
                return Err("raw prompt differs from normalized prompt".into());
            }
            let responses = prompt
                .actions
                .iter()
                .map(|action| action.bytes.clone())
                .collect::<Vec<_>>();
            if !audit_prompt_responses(&frame.raw, &responses)?.matches {
                return Err("independent prompt response audit failed".into());
            }
            prompts.push((frame.clone(), prompt));
        }
    }
    Ok(prompts)
}

fn validate_decision_bindings(
    request: &RunDuelRequest,
    resolved: &[crate::Decision],
    requested: &[crate::Decision],
    prompts: &[(CoreEventFrame, crate::Prompt)],
) -> Result<(), String> {
    if resolved
        .windows(2)
        .any(|pair| pair[0].prompt_id >= pair[1].prompt_id)
    {
        return Err("resolved Curry decisions are not in prompt order".into());
    }
    for (index, decision) in resolved.iter().enumerate() {
        let matches = prompts
            .iter()
            .filter(|(_, prompt)| prompt.id == decision.prompt_id)
            .collect::<Vec<_>>();
        if matches.len() != 1 {
            return Err("resolved Curry decision has no unique raw prompt".into());
        }
        let (frame, prompt) = matches[0];
        if decision.player != prompt.player {
            return Err("resolved Curry decision player differs".into());
        }
        if request_protocol_is_v2_opponent(request, decision.player, prompt.opcode) {
            return Err(
                "protocol-2 opponent action must be audited from steps, not resolved decisions"
                    .into(),
            );
        }
        let matching_actions = prompt
            .actions
            .iter()
            .filter(|action| action.choice == decision.choice)
            .collect::<Vec<_>>();
        if matching_actions.len() != 1 || prompt.encode(&decision.choice).is_err() {
            return Err("resolved Curry decision is not a unique legal action".into());
        }
        if index < requested.len() {
            if decision != &requested[index] {
                return Err("requested decision prefix changed".into());
            }
        } else {
            if prompt.actions.len() != 1 || matching_actions[0].bytes != prompt.actions[0].bytes {
                return Err("automatic Curry response was not the unique menu action".into());
            }
            if decision.player == 1 {
                if prompt.opcode != 16 {
                    return Err("opponent automatic handling is limited to empty chains".into());
                }
                validate_empty_chain(frame)?;
            }
        }
    }
    Ok(())
}

fn request_protocol_is_v2_opponent(request: &RunDuelRequest, player: u8, opcode: u8) -> bool {
    request.protocol_version == 2 && player == 1 && opcode == 16
}

fn validate_step_bindings(
    result: &DuelResult,
    request: &RunDuelRequest,
    prompts: &[(CoreEventFrame, crate::Prompt)],
    pending_id: u64,
) -> Result<(), String> {
    let completed = prompts
        .iter()
        .filter(|(_, prompt)| prompt.id != pending_id)
        .collect::<Vec<_>>();
    if result.steps.len() != completed.len() {
        return Err("Curry steps do not cover every responded prompt exactly once".into());
    }
    for ((frame, prompt), step) in completed.into_iter().zip(&result.steps) {
        let selected = prompt
            .actions
            .iter()
            .filter(|action| *action == step)
            .collect::<Vec<_>>();
        if selected.len() != 1 {
            return Err("Curry step is not the exact unique raw-menu response".into());
        }
        if prompt.player == 1 {
            if request.protocol_version != 2
                || prompt.opcode != 16
                || prompt.actions.len() != 1
                || prompt.actions[0].choice != (Choice::Chain { index: None })
            {
                return Err(
                    "protocol-2 opponent auto-processing is limited to empty nonforced chains"
                        .into(),
                );
            }
            validate_empty_chain(frame)?;
        } else {
            let decisions = result
                .resolved_decisions
                .iter()
                .filter(|decision| decision.prompt_id == prompt.id)
                .collect::<Vec<_>>();
            if decisions.len() != 1
                || decisions[0].player != prompt.player
                || decisions[0].choice != step.choice
            {
                return Err("owned Curry step lacks its unique resolved decision".into());
            }
        }
    }
    Ok(())
}

fn validate_empty_chain(frame: &CoreEventFrame) -> Result<(), String> {
    let raw = &frame.raw;
    if raw.len() != 16
        || raw.first().copied() != Some(16)
        || raw.get(2).copied() != Some(0)
        || raw.get(3).copied() != Some(0)
        || u32::from_le_bytes(raw[12..16].try_into().map_err(|_| "chain count width")?) != 0
    {
        return Err("Curry path contains a forced or nonempty chain".into());
    }
    Ok(())
}

fn validate_place_menu(frame: &CoreEventFrame, prompt: &crate::Prompt) -> Result<(), String> {
    if frame.opcode != 18
        || frame.raw.len() != 7
        || frame.raw[..3] != [18, 0, 1]
        || u32::from_le_bytes(frame.raw[3..7].try_into().map_err(|_| "zone mask width")?)
            != PLACE_MASK
        || prompt.opcode != 18
        || prompt.player != 0
    {
        return Err("Curry spell-zone frame differs from frozen mask".into());
    }
    let expected = (0..5)
        .map(|sequence| vec![0, 8, sequence])
        .collect::<Vec<_>>();
    let actual = prompt
        .actions
        .iter()
        .map(|action| action.bytes.clone())
        .collect::<Vec<_>>();
    let actual_set = actual.iter().cloned().collect::<BTreeSet<_>>();
    let expected_set = expected.iter().cloned().collect::<BTreeSet<_>>();
    if actual.len() != 5 || actual_set != expected_set {
        return Err("Curry spell-zone response set differs".into());
    }
    let mut sequences = BTreeSet::new();
    for action in &prompt.actions {
        let Choice::Place { zones } = &action.choice else {
            return Err("Curry region menu contains a non-place action".into());
        };
        if zones.len() != 1
            || zones[0].player != 0
            || zones[0].location != 8
            || zones[0].sequence > 4
            || action.bytes != [0, 8, zones[0].sequence]
            || !sequences.insert(zones[0].sequence)
        {
            return Err("Curry region coordinate is invalid or duplicated".into());
        }
    }
    if sequences != (0..5).collect() {
        return Err("Curry region response set is incomplete".into());
    }
    Ok(())
}

fn branch_option(request: &RunDuelRequest) -> Result<u8, WorkerError> {
    let mut options = request
        .decisions
        .iter()
        .filter_map(|decision| match &decision.choice {
            Choice::Option { index: 0 } => Some(0),
            Choice::Option { index: 1 } => Some(1),
            Choice::Option { .. } => Some(2),
            _ => None,
        });
    let option = options
        .next()
        .ok_or_else(|| fail("option branch decision missing"))?;
    if option > 1 || options.next().is_some() {
        return Err(fail("option branch decision is duplicated or unsupported"));
    }
    Ok(option)
}

/// Compare full replay semantics, excluding only the documented process-memory statistic.
pub fn curry_option_replay_matches(left: &DuelResult, right: &DuelResult) -> bool {
    let Ok(mut left) = serde_json::to_value(left) else {
        return false;
    };
    let Ok(mut right) = serde_json::to_value(right) else {
        return false;
    };
    left["peak_working_set_bytes"] = Value::Null;
    right["peak_working_set_bytes"] = Value::Null;
    left == right
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_request(protocol_version: u16) -> RunDuelRequest {
        RunDuelRequest {
            protocol_version,
            engine: Default::default(),
            deck: Default::default(),
            opening_hand: Vec::new(),
            seed: 1,
            decisions: Vec::new(),
            versions: Default::default(),
            probe_only: false,
            scenario: None,
            interruption: None,
            first_turn: None,
            research_capture: None,
        }
    }

    #[test]
    fn request_and_result_window_boundaries_are_strict() {
        assert!(curry_option_window_allows_request(100, 101));
        assert!(curry_option_window_allows_request(100, 7_269));
        assert!(!curry_option_window_allows_request(100, 7_270));
        assert!(!curry_option_window_allows_request(100, 99));
        assert!(curry_option_window_allows_result(100, 7_299));
        assert!(!curry_option_window_allows_result(100, 7_300));
        assert!(!curry_option_window_allows_request(u64::MAX - 1, u64::MAX));
    }

    #[test]
    fn own_automatic_response_requires_a_unique_action() {
        let choice = Choice::Chain { index: None };
        let unique = Action {
            choice: choice.clone(),
            label: "pass".into(),
            card_ids: Vec::new(),
            bytes: u32::MAX.to_le_bytes().to_vec(),
        };
        let frame = CoreEventFrame {
            sequence: 1,
            opcode: 16,
            raw: empty_chain_raw(0),
            supported: true,
            fields: json!({}),
        };
        let prompt = crate::Prompt {
            id: 1,
            player: 0,
            opcode: 16,
            actions: vec![unique.clone()],
        };
        let decision = crate::Decision {
            prompt_id: 1,
            player: 0,
            choice: choice.clone(),
        };
        assert!(validate_decision_bindings(
            &test_request(2),
            std::slice::from_ref(&decision),
            &[],
            &[(frame.clone(), prompt)]
        )
        .is_ok());

        let mut multiple = unique.clone();
        multiple.choice = Choice::Chain { index: Some(0) };
        multiple.bytes = 0u32.to_le_bytes().to_vec();
        let prompt = crate::Prompt {
            id: 1,
            player: 0,
            opcode: 16,
            actions: vec![unique, multiple],
        };
        assert!(
            validate_decision_bindings(&test_request(2), &[decision], &[], &[(frame, prompt)])
                .is_err()
        );
    }

    #[test]
    fn protocol_two_opponent_chain_is_a_step_not_a_resolved_decision() {
        let choice = Choice::Chain { index: None };
        let action = Action {
            choice: choice.clone(),
            label: "pass".into(),
            card_ids: Vec::new(),
            bytes: u32::MAX.to_le_bytes().to_vec(),
        };
        let decision = crate::Decision {
            prompt_id: 1,
            player: 1,
            choice,
        };
        let prompt = crate::Prompt {
            id: 1,
            player: 1,
            opcode: 16,
            actions: vec![action.clone()],
        };
        let frame = CoreEventFrame {
            sequence: 1,
            opcode: 16,
            raw: empty_chain_raw(1),
            supported: true,
            fields: json!({}),
        };
        assert!(validate_decision_bindings(
            &test_request(2),
            std::slice::from_ref(&decision),
            &[],
            &[(frame.clone(), prompt.clone())],
        )
        .is_err());

        let result = DuelResult {
            protocol_version: 2,
            status: DuelStatus::DecisionRequired,
            events: vec![],
            prompt: None,
            checkpoint: Default::default(),
            error: None,
            versions: Default::default(),
            loaded_scripts: BTreeMap::new(),
            steps: vec![action.clone()],
            resolved_decisions: Vec::new(),
            coverage_gaps: Vec::new(),
            peak_working_set_bytes: None,
            terminal_observation: None,
        };
        assert!(validate_step_bindings(
            &result,
            &test_request(2),
            &[(frame.clone(), prompt.clone())],
            99,
        )
        .is_ok());

        let mut forced = frame.clone();
        forced.raw[3] = 1;
        assert!(
            validate_step_bindings(&result, &test_request(2), &[(forced, prompt.clone())], 99,)
                .is_err()
        );

        let mut nonempty = frame.clone();
        nonempty.raw[12..16].copy_from_slice(&1u32.to_le_bytes());
        assert!(validate_step_bindings(
            &result,
            &test_request(2),
            &[(nonempty, prompt.clone())],
            99,
        )
        .is_err());

        let mut trailing = frame.clone();
        trailing.raw.push(0);
        assert!(validate_step_bindings(
            &result,
            &test_request(2),
            &[(trailing, prompt.clone())],
            99,
        )
        .is_err());

        let mut wrong_opcode = prompt;
        wrong_opcode.opcode = 11;
        assert!(
            validate_step_bindings(&result, &test_request(2), &[(frame, wrong_opcode)], 99,)
                .is_err()
        );
    }

    fn empty_chain_raw(player: u8) -> Vec<u8> {
        let mut raw = vec![16, player, 0, 0];
        raw.extend([0; 12]);
        raw
    }
}
