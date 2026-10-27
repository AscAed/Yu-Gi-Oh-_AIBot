//! Isolated small native regression window; opening it starts its persistent clock.
use crate::*;
use serde::{Deserialize, Serialize};
use std::{
    path::Path,
    sync::{Arc, Mutex},
};

pub struct NativeRegressionBatch {
    journal: Arc<CallJournal>,
    cases: Vec<String>,
    started: u64,
    gate: Mutex<()>,
    limit: usize,
}
#[derive(Serialize, Deserialize)]
struct Intent {
    case: String,
    purpose: CallPurpose,
    request_hash: String,
}
fn error(message: &str) -> WorkerError {
    WorkerError::new("regression_budget", "native_regression", message)
}
fn now() -> Result<u64, WorkerError> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|v| v.as_secs())
        .map_err(|_| error("invalid clock"))
}
fn hash(request: &RunDuelRequest) -> Result<String, WorkerError> {
    serde_json::to_vec(request)
        .map(|v| digest(&v))
        .map_err(|_| error("request serialization failed"))
}
impl NativeRegressionBatch {
    /// Context must bind the experiment manifest, historical ledger, builds and assets.
    /// Call before the first asset precheck, never after it.
    pub fn open(path: &Path, context: &str, cases: &[String]) -> Result<Self, WorkerError> {
        Self::open_started(path, context, cases, None, "native-regression-v1", 16)
    }
    /// Import the immutable clock receipt written before external asset capture.
    pub fn open_with_start(
        path: &Path,
        context: &str,
        cases: &[String],
        started: u64,
    ) -> Result<Self, WorkerError> {
        if started > now()? {
            return Err(error("window start lies in the future"));
        }
        Self::open_started(
            path,
            context,
            cases,
            Some(started),
            "native-regression-v1",
            16,
        )
    }
    /// Dedicated six-request terminal experiment, never interchangeable with prior scopes.
    pub fn open_terminal_with_start(
        path: &Path,
        context: &str,
        cases: &[String],
        started: u64,
    ) -> Result<Self, WorkerError> {
        let expected = [
            "terminal-rabbit",
            "terminal-tournament",
            "terminal-shuffle-end",
        ]
        .map(str::to_owned);
        if cases != expected || started > now()? {
            return Err(error("invalid terminal scope or start"));
        }
        Self::open_started(
            path,
            context,
            cases,
            Some(started),
            "terminal-regression-v1",
            6,
        )
    }
    /// Dedicated Rabbit execution/replay scope, with a hard two-request ceiling.
    pub fn open_terminal_smoke_with_start(
        path: &Path,
        context: &str,
        cases: &[String],
        started: u64,
    ) -> Result<Self, WorkerError> {
        if cases != ["terminal-rabbit".to_owned()] || started > now()? {
            return Err(error("invalid terminal smoke scope or start"));
        }
        Self::open_started(path, context, cases, Some(started), "terminal-smoke-v1", 2)
    }
    /// Dedicated two-case follow-up scope, with a hard four-request ceiling.
    pub fn open_terminal_followup_with_start(
        path: &Path,
        context: &str,
        cases: &[String],
        started: u64,
    ) -> Result<Self, WorkerError> {
        if cases
            != [
                "terminal-tournament".to_owned(),
                "terminal-shuffle-end".to_owned(),
            ]
            || started > now()?
        {
            return Err(error("invalid terminal followup scope or start"));
        }
        Self::open_started(
            path,
            context,
            cases,
            Some(started),
            "terminal-followup-v1",
            4,
        )
    }
    fn open_started(
        path: &Path,
        context: &str,
        cases: &[String],
        supplied: Option<u64>,
        scope: &str,
        limit: usize,
    ) -> Result<Self, WorkerError> {
        if cases.is_empty()
            || cases.len() > 8
            || cases
                .iter()
                .any(|v| v.is_empty() || !v.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-'))
            || cases
                .iter()
                .collect::<std::collections::BTreeSet<_>>()
                .len()
                != cases.len()
        {
            return Err(error("invalid case allowlist"));
        }
        let binding = serde_json::to_string(&(context, cases))
            .map_err(|_| error("invalid manifest binding"))?;
        let journal = CallJournal::open(path, scope, &binding, limit)?;
        let key = "immutable/native-regression/start";
        let started = match journal.checkpoint(key)? {
            Some(v) => v.as_u64().ok_or_else(|| error("invalid persisted start"))?,
            None => {
                let n = supplied.unwrap_or(now()?);
                journal.save_checkpoint(key, &serde_json::json!(n))?;
                n
            }
        };
        if supplied.is_some_and(|v| v != started) {
            return Err(error("window start differs from persisted receipt"));
        }
        Ok(Self {
            journal,
            cases: cases.to_vec(),
            started,
            gate: Mutex::new(()),
            limit,
        })
    }
    pub fn started_at(&self) -> u64 {
        self.started
    }
    /// Remaining wall time including asset prechecks; keep 30 seconds for a worker.
    pub fn remaining_seconds(&self) -> Result<u64, WorkerError> {
        let at = now()?;
        if at < self.started {
            return Err(error("clock moved backwards"));
        }
        Ok(7200u64.saturating_sub(at - self.started))
    }
    pub fn require_time(&self) -> Result<(), WorkerError> {
        if self.remaining_seconds()? <= 30 {
            return Err(error("window exhausted"));
        }
        Ok(())
    }
    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        self.journal.stats()
    }
    pub fn verify(&self) -> Result<(), WorkerError> {
        self.journal.verify()
    }
    pub fn charged_sequence_id(&self) -> Result<String, WorkerError> {
        self.journal.charged_sequence_id()
    }
    /// Bind a published pair receipt to the ledger, preserving it across later pairs.
    pub fn save_evidence(&self, case: &str, value: &serde_json::Value) -> Result<(), WorkerError> {
        let _guard = self
            .gate
            .lock()
            .map_err(|_| error("execution gate poisoned"))?;
        if !self.cases.iter().any(|v| v == case) {
            return Err(error("case outside manifest"));
        }
        let key = format!("immutable/native-regression/evidence/{case}");
        match self.journal.checkpoint(&key)? {
            Some(existing) if existing == *value => Ok(()),
            Some(_) => Err(error("pair evidence differs from immutable receipt")),
            None => self.journal.save_checkpoint(&key, value),
        }
    }
    pub fn load_evidence(&self, case: &str) -> Result<Option<serde_json::Value>, WorkerError> {
        if !self.cases.iter().any(|v| v == case) {
            return Err(error("case outside manifest"));
        }
        self.journal
            .checkpoint(&format!("immutable/native-regression/evidence/{case}"))
    }
    fn intents(&self) -> Result<Vec<Intent>, WorkerError> {
        let stats = self.stats()?;
        (0..stats.consumed)
            .map(|i| {
                let v = self
                    .journal
                    .checkpoint(&format!("immutable/native-regression/debit/{i}"))?
                    .ok_or_else(|| error("missing call intent"))?;
                serde_json::from_value(v).map_err(|_| error("invalid call intent"))
            })
            .collect()
    }
    /// Restores completed execution or replay without charging or consulting the clock.
    pub fn load_outcome(
        &self,
        case: &str,
        request: &RunDuelRequest,
        purpose: CallPurpose,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        let request_hash = hash(request)?;
        if !matches!(purpose, CallPurpose::Execution | CallPurpose::Replay) {
            return Err(error("unsupported regression purpose"));
        }
        if !self.cases.iter().any(|v| v == case) {
            return Err(error("case outside manifest"));
        }
        for (i, intent) in self.intents()?.iter().enumerate() {
            if intent.case == case && intent.purpose == purpose {
                if intent.request_hash != request_hash {
                    return Err(error("request differs from frozen binding"));
                }
                return self.journal.load_outcome(i as u64 + 1, request);
            }
        }
        Ok(None)
    }
    fn authorize(
        &self,
        case: &str,
        request: &RunDuelRequest,
        purpose: CallPurpose,
        at: u64,
    ) -> Result<usize, WorkerError> {
        if request.engine.timeout_ms != 30000 || !self.cases.iter().any(|v| v == case) {
            return Err(error("wrong case or timeout"));
        }
        if at < self.started || at - self.started >= 7170 {
            return Err(error("window expired or clock moved backwards"));
        }
        let stats = self.stats()?;
        if stats.consumed >= self.limit || stats.unknown != 0 || stats.reserved != 0 {
            return Err(error("budget exhausted or unresolved consumption"));
        }
        let intents = self.intents()?;
        let prior: Vec<_> = intents.iter().filter(|v| v.case == case).collect();
        let expected = if prior.is_empty() {
            CallPurpose::Execution
        } else {
            CallPurpose::Replay
        };
        if prior.len() >= 2 || purpose != expected {
            return Err(error("requires execution then one independent replay"));
        }
        let request_hash = hash(request)?;
        if prior.iter().any(|v| v.request_hash != request_hash) {
            return Err(error("request differs from frozen binding"));
        }
        if self
            .journal
            .checkpoint(&format!(
                "immutable/native-regression/debit/{}",
                stats.consumed
            ))?
            .is_some()
        {
            return Err(error("unfinished pre-call intent"));
        }
        Ok(stats.consumed)
    }
    /// All native work must pass this gate; no automatic retries or refunds.
    pub fn run<A: EngineAdapter>(
        &self,
        adapter: A,
        case: &str,
        request: &RunDuelRequest,
        purpose: CallPurpose,
    ) -> Result<DuelResult, WorkerError> {
        let _guard = self
            .gate
            .lock()
            .map_err(|_| error("execution gate poisoned"))?;
        let index = self.authorize(case, request, purpose, now()?)?;
        let request_hash = hash(request)?;
        let binding = format!("immutable/native-regression/request/{case}");
        match self.journal.checkpoint(&binding)? {
            Some(v) if v.as_str() != Some(request_hash.as_str()) => {
                return Err(error("request differs from frozen binding"))
            }
            Some(_) => {}
            None => self
                .journal
                .save_checkpoint(&binding, &serde_json::json!(request_hash))?,
        }
        let intent = Intent {
            case: case.into(),
            purpose,
            request_hash,
        };
        self.journal.save_checkpoint(
            &format!("immutable/native-regression/debit/{index}"),
            &serde_json::to_value(intent).map_err(|_| error("intent serialization failed"))?,
        )?;
        JournaledAdapter::new(adapter, self.journal.clone(), purpose).run(request)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fail;
    impl EngineAdapter for Fail {
        fn doctor(&self) -> DoctorReport {
            panic!("unused")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Err(WorkerError::new("synthetic", "test", "counted failure"))
        }
    }
    fn request() -> RunDuelRequest {
        serde_json::from_value(serde_json::json!({"protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":RuntimeVersions::default()})).unwrap()
    }
    #[test]
    fn terminal_followup_is_four_calls_and_isolates_scope() {
        let (p, _) = setup();
        let cases = [
            "terminal-tournament".to_owned(),
            "terminal-shuffle-end".to_owned(),
        ];
        let started = now().unwrap();
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p, "followup", &cases, started,
        )
        .unwrap();
        assert!(batch
            .run(Fail, "terminal-rabbit", &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        for case in &cases {
            for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
                assert_eq!(
                    batch.run(Fail, case, &request(), purpose).unwrap_err().code,
                    "synthetic"
                );
            }
        }
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 4);
        drop(batch);
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p, "followup", &cases, started,
        )
        .unwrap();
        assert!(batch
            .load_outcome(&cases[0], &request(), CallPurpose::Execution)
            .unwrap()
            .is_some());
        assert_eq!(batch.stats().unwrap().consumed, 4);
        drop(batch);
        assert!(NativeRegressionBatch::open(&p, "followup", &cases).is_err());
        let (other, _) = setup();
        assert!(NativeRegressionBatch::open_terminal_followup_with_start(
            &other,
            "followup",
            &[cases[1].clone(), cases[0].clone()],
            started
        )
        .is_err());
    }
    #[test]
    fn terminal_smoke_is_two_calls_and_preserves_paid_results() {
        let (p, _) = setup();
        let cases = ["terminal-rabbit".to_owned()];
        let started = now().unwrap();
        let batch =
            NativeRegressionBatch::open_terminal_smoke_with_start(&p, "smoke", &cases, started)
                .unwrap();
        assert!(batch
            .run(
                Fail,
                "terminal-tournament",
                &request(),
                CallPurpose::Execution
            )
            .is_err());
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Replay)
            .is_err());
        for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
            assert_eq!(
                batch
                    .run(Fail, &cases[0], &request(), purpose)
                    .unwrap_err()
                    .code,
                "synthetic"
            );
        }
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 2);
        drop(batch);
        let batch =
            NativeRegressionBatch::open_terminal_smoke_with_start(&p, "smoke", &cases, started)
                .unwrap();
        assert!(batch
            .load_outcome(&cases[0], &request(), CallPurpose::Execution)
            .unwrap()
            .is_some());
        assert_eq!(batch.stats().unwrap().consumed, 2);
        drop(batch);
        assert!(NativeRegressionBatch::open(&p, "smoke", &cases).is_err());
    }
    #[test]
    fn smoke_expiry_unknown_and_request_changes_block_before_charge() {
        let (p, _) = setup();
        let cases = ["terminal-rabbit".to_owned()];
        let expired = now().unwrap() - 8000;
        let batch =
            NativeRegressionBatch::open_terminal_smoke_with_start(&p, "smoke", &cases, expired)
                .unwrap();
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        drop(batch);
        assert!(NativeRegressionBatch::open_terminal_smoke_with_start(
            &p,
            "smoke",
            &cases,
            now().unwrap()
        )
        .is_err());
        let (p, _) = setup();
        let batch = NativeRegressionBatch::open_terminal_smoke_with_start(
            &p,
            "smoke",
            &cases,
            now().unwrap(),
        )
        .unwrap();
        batch
            .journal
            .begin_call(&request(), CallPurpose::Execution, None)
            .unwrap();
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
        let (p, _) = setup();
        let started = now().unwrap();
        let batch =
            NativeRegressionBatch::open_terminal_smoke_with_start(&p, "smoke", &cases, started)
                .unwrap();
        let _ = batch.run(Fail, &cases[0], &request(), CallPurpose::Execution);
        drop(batch);
        let batch =
            NativeRegressionBatch::open_terminal_smoke_with_start(&p, "smoke", &cases, started)
                .unwrap();
        let mut changed = request();
        changed.seed += 1;
        assert!(batch
            .run(Fail, &cases[0], &changed, CallPurpose::Replay)
            .is_err());
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Probe)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
    }
    #[test]
    fn followup_expiry_unknown_and_request_changes_block_before_charge() {
        let (p, _) = setup();
        let cases = [
            "terminal-tournament".to_owned(),
            "terminal-shuffle-end".to_owned(),
        ];
        let expired = now().unwrap() - 8000;
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p, "followup", &cases, expired,
        )
        .unwrap();
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        drop(batch);
        assert!(NativeRegressionBatch::open_terminal_followup_with_start(
            &p,
            "followup",
            &cases,
            now().unwrap()
        )
        .is_err());
        let (p, _) = setup();
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p,
            "followup",
            &cases,
            now().unwrap(),
        )
        .unwrap();
        batch
            .journal
            .begin_call(&request(), CallPurpose::Execution, None)
            .unwrap();
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
        let (p, _) = setup();
        let started = now().unwrap();
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p, "followup", &cases, started,
        )
        .unwrap();
        let _ = batch.run(Fail, &cases[0], &request(), CallPurpose::Execution);
        drop(batch);
        let batch = NativeRegressionBatch::open_terminal_followup_with_start(
            &p, "followup", &cases, started,
        )
        .unwrap();
        let mut changed = request();
        changed.seed += 1;
        assert!(batch
            .run(Fail, &cases[0], &changed, CallPurpose::Replay)
            .is_err());
        assert!(batch
            .run(Fail, &cases[0], &request(), CallPurpose::Probe)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
    }
    fn setup() -> (std::path::PathBuf, Vec<String>) {
        let p = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "regression-{}-{}.jsonl",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        (p, (0..8).map(|i| format!("case-{i}")).collect())
    }
    #[test]
    fn terminal_six_call_scope_rejects_seventh_and_wrong_allowlist() {
        let (p, _) = setup();
        let cases = [
            "terminal-rabbit",
            "terminal-tournament",
            "terminal-shuffle-end",
        ]
        .map(str::to_owned);
        let started = now().unwrap();
        let b = NativeRegressionBatch::open_terminal_with_start(&p, "terminal", &cases, started)
            .unwrap();
        for case in &cases {
            for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
                assert_eq!(
                    b.run(Fail, case, &request(), purpose).unwrap_err().code,
                    "synthetic"
                );
            }
        }
        assert_eq!(b.stats().unwrap().consumed, 6);
        assert!(b
            .run(Fail, &cases[0], &request(), CallPurpose::Execution)
            .is_err());
        drop(b);
        assert!(NativeRegressionBatch::open(&p, "terminal", &cases).is_err());
        let b = NativeRegressionBatch::open_terminal_with_start(&p, "terminal", &cases, started)
            .unwrap();
        assert_eq!(b.stats().unwrap().consumed, 6);
    }
    #[test]
    fn sixteen_calls_survive_reopen_and_seventeenth_is_rejected() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        for case in &c {
            for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
                assert_eq!(
                    b.run(Fail, case, &request(), purpose).unwrap_err().code,
                    "synthetic"
                );
            }
        }
        assert_eq!(b.stats().unwrap().consumed, 16);
        drop(b);
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        assert!(b
            .load_outcome(&c[0], &request(), CallPurpose::Execution)
            .unwrap()
            .unwrap()
            .is_err());
        assert_eq!(b.stats().unwrap().consumed, 16);
    }
    #[test]
    fn wrong_case_purpose_duplicate_and_request_are_free_rejections() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        for (case, purpose) in [
            ("wrong", CallPurpose::Execution),
            (&c[0], CallPurpose::Replay),
            (&c[0], CallPurpose::Probe),
        ] {
            assert!(b.run(Fail, case, &request(), purpose).is_err());
        }
        assert_eq!(b.stats().unwrap().consumed, 0);
        let _ = b.run(Fail, &c[0], &request(), CallPurpose::Execution);
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        let mut changed = request();
        changed.seed = 2;
        assert!(b.run(Fail, &c[0], &changed, CallPurpose::Replay).is_err());
        assert_eq!(b.stats().unwrap().consumed, 1);
        drop(b);
        assert!(NativeRegressionBatch::open(&p, "changed", &c).is_err());
    }
    #[test]
    fn expired_window_and_unknown_consumption_block_before_charge() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert!(b
            .authorize(&c[0], &request(), CallPurpose::Execution, b.started + 7170)
            .is_err());
        assert!(b
            .authorize(&c[0], &request(), CallPurpose::Execution, b.started - 1)
            .is_err());
        b.journal
            .begin_call(&request(), CallPurpose::Execution, None)
            .unwrap();
        assert!(b
            .run(Fail, &c[1], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(b.stats().unwrap().consumed, 1);
    }
    #[test]
    fn persisted_expired_start_is_not_reset() {
        let (p, c) = setup();
        let binding = serde_json::to_string(&("frozen", &c)).unwrap();
        let j = CallJournal::open(&p, "native-regression-v1", &binding, 16).unwrap();
        j.save_checkpoint(
            "immutable/native-regression/start",
            &serde_json::json!(now().unwrap() - 8000),
        )
        .unwrap();
        drop(j);
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(b.stats().unwrap().consumed, 0);
    }
    #[test]
    fn partial_pair_recovers_without_charge_then_only_replay_runs() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        let start = b.started_at();
        assert_eq!(
            b.run(Fail, &c[0], &request(), CallPurpose::Execution)
                .unwrap_err()
                .code,
            "synthetic"
        );
        drop(b);
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert_eq!(b.started_at(), start);
        assert_eq!(
            b.load_outcome(&c[0], &request(), CallPurpose::Execution)
                .unwrap()
                .unwrap()
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert!(b
            .load_outcome(&c[0], &request(), CallPurpose::Replay)
            .unwrap()
            .is_none());
        let mut changed = request();
        changed.engine.worker_path = "changed-worker".into();
        assert!(b
            .load_outcome(&c[0], &changed, CallPurpose::Execution)
            .is_err());
        assert_eq!(b.stats().unwrap().consumed, 1);
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(
            b.run(Fail, &c[0], &request(), CallPurpose::Replay)
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert_eq!(b.stats().unwrap().consumed, 2);
    }
    #[test]
    fn unfinished_intent_blocks_even_without_unknown_consumption() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        b.journal.save_checkpoint("immutable/native-regression/debit/0",&serde_json::json!({"case":c[0],"purpose":"execution","request_hash":hash(&request()).unwrap()})).unwrap();
        drop(b);
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        assert_eq!(b.stats().unwrap().consumed, 0);
    }
    #[test]
    fn rejects_ninth_or_duplicate_manifest_case() {
        let (p, mut c) = setup();
        c.push("ninth".into());
        assert!(NativeRegressionBatch::open(&p, "frozen", &c).is_err());
        c.pop();
        c[1] = c[0].clone();
        assert!(NativeRegressionBatch::open(&p, "frozen", &c).is_err());
        assert!(!p.exists());
    }
    #[test]
    fn evidence_receipt_is_immutable_and_survives_later_calls() {
        let (p, c) = setup();
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        let value = serde_json::json!({"runs":[],"ledger_sequence":"receipt"});
        b.save_evidence(&c[0], &value).unwrap();
        let _ = b.run(Fail, &c[1], &request(), CallPurpose::Execution);
        b.save_evidence(&c[0], &value).unwrap();
        assert!(b
            .save_evidence(&c[0], &serde_json::json!({"runs":["forged"]}))
            .is_err());
        drop(b);
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert_eq!(b.load_evidence(&c[0]).unwrap(), Some(value));
        assert_eq!(b.stats().unwrap().consumed, 1);
    }
    #[test]
    fn imported_precheck_clock_cannot_be_reset_after_reopen() {
        let (p, c) = setup();
        let expired = now().unwrap() - 8000;
        let b = NativeRegressionBatch::open_with_start(&p, "frozen", &c, expired).unwrap();
        assert_eq!(b.started_at(), expired);
        assert!(b
            .run(Fail, &c[0], &request(), CallPurpose::Execution)
            .is_err());
        drop(b);
        assert!(NativeRegressionBatch::open_with_start(&p, "frozen", &c, now().unwrap()).is_err());
        assert!(
            NativeRegressionBatch::open_with_start(&p, "frozen", &c, now().unwrap() + 10).is_err()
        );
        let b = NativeRegressionBatch::open(&p, "frozen", &c).unwrap();
        assert_eq!(b.started_at(), expired);
        assert_eq!(b.stats().unwrap().consumed, 0);
    }
}
