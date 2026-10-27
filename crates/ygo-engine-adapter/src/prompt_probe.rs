//! Dedicated six-slot Tenki prompt experiment; never reused by older scopes.
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn exact_six_purpose_slots() {
        assert_eq!(prompt_probe_purpose(1).unwrap(), crate::CallPurpose::Probe);
        assert_eq!(prompt_probe_purpose(2).unwrap(), crate::CallPurpose::Probe);
        assert_eq!(
            prompt_probe_purpose(3).unwrap(),
            crate::CallPurpose::Execution
        );
        assert_eq!(prompt_probe_purpose(4).unwrap(), crate::CallPurpose::Replay);
        assert_eq!(
            prompt_probe_purpose(5).unwrap(),
            crate::CallPurpose::Execution
        );
        assert_eq!(prompt_probe_purpose(6).unwrap(), crate::CallPurpose::Replay);
        assert!(prompt_probe_purpose(0).is_err());
        assert!(prompt_probe_purpose(7).is_err());
    }
    fn request() -> RunDuelRequest {
        let fixture: Value =
            serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.request.json"))
                .unwrap();
        let mut r: RunDuelRequest = serde_json::from_value(json!({"protocol_version":2,"engine":{},"deck":fixture["deck"],"opening_hand":fixture["opening_hand"],"seed":1,"decisions":[],"versions":RuntimeVersions::default()})).unwrap();
        r.deck.main[0] = ygo_domain::CardId(57103969);
        r.opening_hand[0] = ygo_domain::CardId(57103969);
        r.versions=serde_json::from_value(json!({"rules":"ocg-mr5","catalog":"","banlist":"","core_commit":"38d04c9feb1a26617407091380634c87262fe3f8","initializer":"fixed-hand-shuffle-v1","engine_sha256":"446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9","cdb_sha256":"c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225","scripts_sha256":"69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91"})).unwrap();
        r
    }
    fn result(raw: Vec<u8>) -> DuelResult {
        let prompt = parse_prompt(1, &raw).unwrap().unwrap();
        let mut r = DuelResult::failure(fail("unused"));
        r.status = DuelStatus::DecisionRequired;
        r.error = None;
        r.prompt = Some(prompt.clone());
        r.events = vec![CoreEventFrame {
            sequence: 1,
            opcode: raw[0],
            raw,
            supported: true,
            fields: json!({"prompt":prompt}),
        }];
        r
    }
    #[test]
    fn exact_yes_no_raw_description_and_oracle_required() {
        let mut raw = vec![13, 0];
        raw.extend(59877851398144u64.to_le_bytes());
        let r = result(raw.clone());
        assert!(validate_prompt_probe_result(2, &request(), &r).is_ok());
        raw[2] ^= 1;
        assert!(validate_prompt_probe_result(2, &request(), &result(raw)).is_err());
        let mut bad = r.clone();
        bad.events[0].raw.push(0);
        assert!(validate_prompt_probe_result(2, &request(), &bad).is_err());
        let mut bad = r;
        bad.prompt.as_mut().unwrap().actions[0].bytes[0] = 1;
        assert!(validate_prompt_probe_result(2, &request(), &bad).is_err());
    }
    #[test]
    fn intermediate_place_is_preserved_but_refused_at_stage_two() {
        let mut raw = vec![18, 0, 1];
        raw.extend(0xfffffffeu32.to_le_bytes());
        let r = result(raw.clone());
        let before = encoded(&r).unwrap();
        assert!(validate_prompt_probe_result(2, &request(), &r).is_err());
        assert_eq!(encoded(&r).unwrap(), before);
        assert_eq!(r.events[0].raw, raw);
    }
    #[test]
    fn two_target_single_selection_and_no_unapproved_auto_choice() {
        let mut raw = vec![15, 0, 0];
        for n in [1u32, 1, 2] {
            raw.extend(n.to_le_bytes());
        }
        for sequence in [0u32, 1] {
            raw.extend(69247929u32.to_le_bytes());
            raw.extend([0, 1]);
            raw.extend(sequence.to_le_bytes());
            raw.extend(0u32.to_le_bytes());
        }
        let mut r = result(raw);
        assert!(validate_prompt_probe_result(5, &request(), &r).is_ok());
        for (offset, value) in [(19, 1), (20, 4), (35, 0), (39, 3)] {
            let mut raw = r.events[0].raw.clone();
            raw[offset] = value;
            assert!(validate_prompt_probe_result(5, &request(), &result(raw)).is_err());
        }
        let mut duplicate = r.clone();
        duplicate.events.push(duplicate.events[0].clone());
        assert!(validate_prompt_probe_result(5, &request(), &duplicate).is_err());
        r.resolved_decisions.push(Decision {
            prompt_id: 1,
            player: 0,
            choice: r.prompt.as_ref().unwrap().actions[0].choice.clone(),
        });
        assert!(validate_prompt_probe_result(5, &request(), &r).is_err());
    }
    #[test]
    fn replay_normalization_only_clears_memory_in_copies() {
        let mut a = DuelResult::failure(fail("same"));
        let mut b = a.clone();
        a.peak_working_set_bytes = Some(1);
        b.peak_working_set_bytes = Some(2);
        assert!(prompt_probe_replay_matches(&a, &b));
        assert_eq!(a.peak_working_set_bytes, Some(1));
        b.coverage_gaps.push("different".into());
        assert!(!prompt_probe_replay_matches(&a, &b));
    }
    struct SyntheticFail;
    struct SyntheticResult(DuelResult);
    impl EngineAdapter for SyntheticResult {
        fn doctor(&self) -> DoctorReport {
            panic!("no doctor")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Ok(self.0.clone())
        }
    }
    fn idle(tenki: bool) -> Vec<u8> {
        let mut raw = vec![11, 0];
        for command in 0..6 {
            raw.extend(u32::from(tenki && command == 5).to_le_bytes());
            if tenki && command == 5 {
                raw.extend(57103969u32.to_le_bytes());
                raw.extend([0, 2]);
                raw.extend(0u32.to_le_bytes());
                raw.extend(0u64.to_le_bytes());
                raw.push(0);
            }
        }
        raw.extend([0, 1, 0]);
        raw
    }
    fn stage_result(stage: u8, request: &RunDuelRequest) -> DuelResult {
        let mut raws = vec![idle(true)];
        if stage > 1 {
            let mut raw = vec![13, 0];
            raw.extend(59877851398144u64.to_le_bytes());
            raws.push(raw);
        }
        if stage == 3 || stage == 4 {
            raws.push(idle(false));
        }
        if stage == 5 || stage == 6 {
            let mut raw = vec![15, 0, 0];
            for n in [1u32, 1, 2] {
                raw.extend(n.to_le_bytes());
            }
            for seq in [0u32, 1] {
                raw.extend(69247929u32.to_le_bytes());
                raw.extend([0, 1]);
                raw.extend(seq.to_le_bytes());
                raw.extend(0u32.to_le_bytes());
            }
            raws.push(raw);
        }
        let mut r = DuelResult::failure(fail("unused"));
        r.status = DuelStatus::DecisionRequired;
        r.error = None;
        r.resolved_decisions = request.decisions.clone();
        r.events = raws
            .into_iter()
            .enumerate()
            .map(|(i, raw)| {
                let sequence = i as u64 + 1;
                let p = parse_prompt(sequence, &raw).unwrap().unwrap();
                r.prompt = Some(p.clone());
                CoreEventFrame {
                    sequence,
                    opcode: raw[0],
                    raw,
                    supported: true,
                    fields: json!({"prompt":p}),
                }
            })
            .collect();
        r
    }
    fn temp_path() -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "tenki-six-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }
    #[test]
    fn all_six_slots_exact_parent_derivation_restore_and_seventh_refused() {
        let path = temp_path();
        let start = now().unwrap();
        let batch = PromptProbeBatch::open(&path, "six", start).unwrap();
        let mut requests = vec![request()];
        let mut outcomes = Vec::new();
        for stage in 1..=6u8 {
            let r = if stage == 1 {
                requests[0].clone()
            } else {
                let parent = match stage {
                    2 => 1,
                    3 | 5 => 2,
                    4 => 3,
                    6 => 5,
                    _ => unreachable!(),
                };
                let mut r = requests[parent - 1].clone();
                if stage != 4 && stage != 6 {
                    let prior: &DuelResult = &outcomes[parent - 1];
                    let p = prior.prompt.as_ref().unwrap();
                    let choice = if stage == 2 {
                        unique_tenki(p).unwrap().choice
                    } else {
                        Choice::YesNo { yes: stage == 5 }
                    };
                    r.decisions = prior.resolved_decisions.clone();
                    r.decisions.push(Decision {
                        prompt_id: p.id,
                        player: p.player,
                        choice,
                    });
                }
                r
            };
            if stage > 1 {
                requests.push(r.clone());
                let mut wrong = r.clone();
                wrong.seed = 2;
                assert!(batch.validate_request(stage, &wrong).is_err());
            }
            batch
                .save_assets_before(stage, &json!({"synthetic":true}))
                .unwrap();
            let outcome = batch
                .run(SyntheticResult(stage_result(stage, &r)), stage, &r)
                .unwrap();
            let validation = validate_prompt_probe_result(stage, &r, &outcome);
            assert!(validation.is_ok(), "{validation:?}");
            let receipt = json!({"scope":PROMPT_PROBE_SCOPE,"stage":stage,"started_at":start,"request":r,"result":Ok::<_,WorkerError>(&outcome),"validation":validation,"assets_before":{"synthetic":true},"assets_after":{"synthetic":true},"assets_unchanged":true,"successful":true,"independent_replay_matches":if stage==4||stage==6{json!(true)}else{Value::Null}});
            batch.save_evidence(stage, &receipt).unwrap();
            batch.verify_evidence(stage, &receipt).unwrap();
            outcomes.push(outcome);
        }
        assert_eq!(batch.stats().unwrap().consumed, 6);
        assert!(batch.run(SyntheticFail, 7, &requests[0]).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 6);
        drop(batch);
        let restored = PromptProbeBatch::open(&path, "six", start).unwrap();
        for stage in 1..=6u8 {
            let receipt = restored.evidence(stage).unwrap().unwrap();
            restored.verify_evidence(stage, &receipt).unwrap();
            assert!(restored
                .load_outcome(stage, &requests[stage as usize - 1])
                .unwrap()
                .is_some());
        }
        assert_eq!(restored.stats().unwrap().consumed, 6);
        drop(restored);
        std::fs::remove_file(path).unwrap();
    }
    #[test]
    fn expired_unknown_and_partial_intent_refuse_native_work() {
        let path = temp_path();
        let batch = PromptProbeBatch::open(&path, "expired", now().unwrap() - 7200).unwrap();
        assert!(batch.run(SyntheticFail, 1, &request()).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        drop(batch);
        std::fs::remove_file(path).unwrap();
        let path = temp_path();
        let batch = PromptProbeBatch::open(&path, "unknown", now().unwrap()).unwrap();
        batch
            .journal
            .begin_call(&request(), CallPurpose::Probe, None)
            .unwrap();
        assert_eq!(batch.stats().unwrap().unknown, 1);
        assert!(batch.run(SyntheticFail, 1, &request()).is_err());
        drop(batch);
        std::fs::remove_file(path).unwrap();
        let path = temp_path();
        let batch = PromptProbeBatch::open(&path, "partial", now().unwrap()).unwrap();
        batch
            .journal
            .save_checkpoint(
                "immutable/prompt-probe/intent/1",
                &encoded(&Intent {
                    stage: 1,
                    request: request(),
                })
                .unwrap(),
            )
            .unwrap();
        assert!(batch.run(SyntheticFail, 1, &request()).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        drop(batch);
        std::fs::remove_file(path).unwrap();
    }
    impl EngineAdapter for SyntheticFail {
        fn doctor(&self) -> DoctorReport {
            panic!("no doctor")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Err(fail("synthetic charged failure"))
        }
    }
    #[test]
    fn dedicated_scope_sequence_failed_call_and_zero_call_recovery() {
        let root = std::env::temp_dir().join(format!(
            "tenki-probe-test-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let batch = PromptProbeBatch::open(&root, "synthetic", now().unwrap()).unwrap();
        let r = request();
        let mut invalid = r.clone();
        invalid.opening_hand = vec![ygo_domain::CardId(69247929); 5];
        assert!(batch.validate_request(1, &invalid).is_err());
        assert!(batch.run(SyntheticFail, 2, &r).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 0);
        assert!(batch.run(SyntheticFail, 1, &r).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
        assert!(batch.load_outcome(1, &r).unwrap().is_some());
        assert!(batch.run(SyntheticFail, 1, &r).is_err());
        assert!(batch.run(SyntheticFail, 2, &r).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
        assert!(CallJournal::open(&root, "terminal-followup-v1", "synthetic", 4).is_err());
        batch.verify().unwrap();
        drop(batch);
        std::fs::remove_file(root).unwrap();
    }
}
use crate::*;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    path::Path,
    sync::{Arc, Mutex},
};

pub const PROMPT_PROBE_SCOPE: &str = "tenki-prompt-probe-v1";
fn fail(s: &str) -> WorkerError {
    WorkerError::new("prompt_probe_gate", "prompt_probe", s)
}
fn now() -> Result<u64, WorkerError> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|v| v.as_secs())
        .map_err(|_| fail("invalid clock"))
}
fn encoded<T: Serialize>(v: &T) -> Result<Value, WorkerError> {
    serde_json::to_value(v).map_err(|_| fail("serialization"))
}
fn request_hash(r: &RunDuelRequest) -> Result<String, WorkerError> {
    serde_json::to_vec(r)
        .map(|v| digest(&v))
        .map_err(|_| fail("request serialization"))
}
/// The purpose of each of the six globally ordered slots is immutable.
pub fn prompt_probe_purpose(stage: u8) -> Result<CallPurpose, WorkerError> {
    match stage {
        1 | 2 => Ok(CallPurpose::Probe),
        3 | 5 => Ok(CallPurpose::Execution),
        4 | 6 => Ok(CallPurpose::Replay),
        _ => Err(fail("stage outside six-slot scope")),
    }
}

/// Dedicated persistent journal; failed calls never authorize another stage.
pub struct PromptProbeBatch {
    journal: Arc<CallJournal>,
    started: u64,
    gate: Mutex<()>,
}
#[derive(Serialize, Deserialize)]
struct Intent {
    stage: u8,
    request: RunDuelRequest,
}
impl PromptProbeBatch {
    pub fn open(path: &Path, context: &str, started: u64) -> Result<Self, WorkerError> {
        if context.is_empty() || started > now()? {
            return Err(fail("invalid context/start"));
        }
        let journal = CallJournal::open(path, PROMPT_PROBE_SCOPE, context, 6)?;
        let key = "immutable/prompt-probe/start";
        match journal.checkpoint(key)? {
            Some(v) if v != json!(started) => return Err(fail("start receipt changed")),
            Some(_) => {}
            None => journal.save_checkpoint(key, &json!(started))?,
        }
        Ok(Self {
            journal,
            started,
            gate: Mutex::new(()),
        })
    }
    pub fn stats(&self) -> Result<LedgerStats, WorkerError> {
        self.journal.stats()
    }
    pub fn verify(&self) -> Result<(), WorkerError> {
        self.journal.verify()
    }
    pub fn assets_before(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        self.journal
            .checkpoint(&format!("immutable/prompt-probe/assets/{stage}"))
    }
    pub fn save_assets_before(&self, stage: u8, value: &Value) -> Result<(), WorkerError> {
        self.journal
            .save_checkpoint(&format!("immutable/prompt-probe/assets/{stage}"), value)
    }
    pub fn require_time(&self) -> Result<(), WorkerError> {
        let at = now()?;
        if at < self.started || at - self.started >= 7170 {
            Err(fail("window exhausted"))
        } else {
            Ok(())
        }
    }
    pub fn evidence(&self, stage: u8) -> Result<Option<Value>, WorkerError> {
        prompt_probe_purpose(stage)?;
        self.journal
            .checkpoint(&format!("immutable/prompt-probe/evidence/{stage}"))
    }
    pub fn save_evidence(&self, stage: u8, v: &Value) -> Result<(), WorkerError> {
        let key = format!("immutable/prompt-probe/evidence/{stage}");
        match self.journal.checkpoint(&key)? {
            Some(old) if old == *v => Ok(()),
            Some(_) => Err(fail("immutable evidence differs")),
            None => self.journal.save_checkpoint(&key, v),
        }
    }
    fn intent(&self, stage: u8) -> Result<Option<Intent>, WorkerError> {
        self.journal
            .checkpoint(&format!("immutable/prompt-probe/intent/{stage}"))?
            .map(|v| serde_json::from_value(v).map_err(|_| fail("invalid intent")))
            .transpose()
    }
    pub fn load_outcome(
        &self,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<Option<Result<DuelResult, WorkerError>>, WorkerError> {
        prompt_probe_purpose(stage)?;
        if let Some(intent) = self.intent(stage)? {
            if request_hash(&intent.request)? != request_hash(request)? {
                return Err(fail("request changed"));
            }
            self.journal.load_outcome(stage.into(), request)
        } else {
            Ok(None)
        }
    }
    pub fn validate_request(&self, stage: u8, request: &RunDuelRequest) -> Result<(), WorkerError> {
        prompt_probe_purpose(stage)?;
        let deck_binding =
            json!({"deck":request.deck,"opening_hand":request.opening_hand,"seed":request.seed});
        if digest(&serde_json::to_vec(&deck_binding).map_err(|_| fail("deck binding"))?)
            != "367b15e0e63359108fa74a33ee1db17d77f766aba88f2df3e0689ba023696e47"
            || digest(
                &serde_json::to_vec(&encoded(&request.versions)?)
                    .map_err(|_| fail("version binding"))?,
            ) != "cf7c2fefe9ed6d62c71f1f138cfee50428de80f1b9d7dbf66c20ef389071e6b1"
        {
            return Err(fail("frozen Tenki deck or versions differ"));
        }
        let mut remaining = std::collections::BTreeMap::new();
        for card in &request.deck.main {
            *remaining.entry(card.0).or_insert(0usize) += 1;
        }
        for card in &request.opening_hand {
            let count = remaining
                .get_mut(&card.0)
                .ok_or_else(|| fail("opening card absent from main"))?;
            *count = count
                .checked_sub(1)
                .ok_or_else(|| fail("opening multiplicity exceeds main"))?;
        }
        if request.engine.timeout_ms != 30000
            || request.protocol_version != 2
            || request.probe_only
            || request.scenario.is_some()
            || request.interruption.is_some()
            || request.first_turn.is_some()
            || request.research_capture.is_some()
            || request.seed != 1
            || request.deck.main.len() != 40
            || request.deck.extra.len() != 3
            || !request.deck.side.is_empty()
            || request.opening_hand.len() != 5
            || request.deck.main.iter().any(|c| c.0 == 85138716)
            || request
                .deck
                .main
                .iter()
                .filter(|c| c.0 == 69247929)
                .count()
                .checked_sub(
                    request
                        .opening_hand
                        .iter()
                        .filter(|c| c.0 == 69247929)
                        .count(),
                )
                != Some(2)
            || request
                .opening_hand
                .iter()
                .filter(|c| c.0 == 57103969)
                .count()
                != 1
            || request.deck.main.iter().filter(|c| c.0 == 57103969).count() != 1
        {
            return Err(fail("unsupported Tenki request"));
        }
        if stage == 1 {
            if !request.decisions.is_empty() {
                return Err(fail("initial request must have no decisions"));
            }
            return Ok(());
        }
        let parent = match stage {
            2 => 1,
            3 | 5 => 2,
            4 => 3,
            6 => 5,
            _ => unreachable!(),
        };
        let receipt = self
            .evidence(parent)?
            .ok_or_else(|| fail("missing parent receipt"))?;
        self.verify_evidence(parent, &receipt)?;
        if receipt["successful"] != true {
            return Err(fail("parent stage failed"));
        }
        let mut expected: RunDuelRequest = serde_json::from_value(receipt["request"].clone())
            .map_err(|_| fail("parent request"))?;
        if stage != 4 && stage != 6 {
            let result: Result<DuelResult, WorkerError> =
                serde_json::from_value(receipt["result"].clone())
                    .map_err(|_| fail("parent result"))?;
            let result = result.map_err(|_| fail("parent error"))?;
            let prompt = result
                .prompt
                .ok_or_else(|| fail("parent pending prompt missing"))?;
            let choice = if stage == 2 {
                unique_tenki(&prompt)?.choice
            } else {
                Choice::YesNo { yes: stage == 5 }
            };
            prompt
                .encode(&choice)
                .map_err(|_| fail("parent choice not legal"))?;
            expected.decisions = result.resolved_decisions;
            expected.decisions.push(Decision {
                prompt_id: prompt.id,
                player: prompt.player,
                choice,
            });
        }
        if request_hash(&expected)? != request_hash(request)? {
            return Err(fail("request not exact parent derivation"));
        }
        Ok(())
    }
    pub fn verify_evidence(&self, stage: u8, v: &Value) -> Result<(), WorkerError> {
        if v["stage"] != json!(stage)
            || v["scope"] != PROMPT_PROBE_SCOPE
            || v["started_at"] != self.started
        {
            return Err(fail("receipt binding"));
        }
        let request: RunDuelRequest =
            serde_json::from_value(v["request"].clone()).map_err(|_| fail("receipt request"))?;
        self.validate_request(stage, &request)?;
        let outcome = self
            .load_outcome(stage, &request)?
            .ok_or_else(|| fail("missing charged outcome"))?;
        if encoded(&outcome)? != v["result"] {
            return Err(fail("receipt outcome differs"));
        }
        let validation = outcome
            .as_ref()
            .map_err(|e| e.message.clone())
            .and_then(|r| validate_prompt_probe_result(stage, &request, r));
        if encoded(&validation)? != v["validation"] {
            return Err(fail("receipt validation differs"));
        }
        if self.assets_before(stage)?.as_ref() != Some(&v["assets_before"]) {
            return Err(fail("asset precheck receipt differs"));
        }
        let expected_replay = if stage == 4 || stage == 6 {
            let previous = self
                .evidence(stage - 1)?
                .ok_or_else(|| fail("replay receipt missing"))?;
            let parent: Result<DuelResult, WorkerError> =
                serde_json::from_value(previous["result"].clone())
                    .map_err(|_| fail("replay outcome"))?;
            json!(match (&parent, &outcome) {
                (Ok(a), Ok(b)) => prompt_probe_replay_matches(a, b),
                _ => false,
            })
        } else {
            Value::Null
        };
        if v["independent_replay_matches"] != expected_replay {
            return Err(fail("replay comparison differs"));
        }
        if v["successful"] == true && expected_replay == false {
            return Err(fail("unsuccessful replay"));
        }
        if v["successful"] == true
            && (validation.is_err()
                || v["assets_unchanged"] != true
                || v["assets_before"] != v["assets_after"])
        {
            return Err(fail("invalid successful receipt"));
        }
        self.journal.verify()
    }
    /// Debits exactly one worker call; no retries, refunds, or implicit replay.
    pub fn run<A: EngineAdapter>(
        &self,
        adapter: A,
        stage: u8,
        request: &RunDuelRequest,
    ) -> Result<DuelResult, WorkerError> {
        let _guard = self.gate.lock().map_err(|_| fail("poisoned gate"))?;
        self.validate_request(stage, request)?;
        self.require_time()?;
        let stats = self.stats()?;
        if stats.consumed != stage as usize - 1
            || stats.unknown != 0
            || stats.reserved != 0
            || stats.consumed >= 6
            || self.intent(stage)?.is_some()
        {
            return Err(fail("out of sequence or unresolved debit"));
        }
        if stage > 1 {
            let previous = self
                .evidence(stage - 1)?
                .ok_or_else(|| fail("previous receipt missing"))?;
            self.verify_evidence(stage - 1, &previous)?;
            if previous["successful"] != true {
                return Err(fail("previous stage failed"));
            }
        }
        self.journal.save_checkpoint(
            &format!("immutable/prompt-probe/intent/{stage}"),
            &encoded(&Intent {
                stage,
                request: request.clone(),
            })?,
        )?;
        JournaledAdapter::new(adapter, self.journal.clone(), prompt_probe_purpose(stage)?)
            .run(request)
    }
}
fn unique_tenki(prompt: &Prompt) -> Result<Action, WorkerError> {
    if prompt.player != 0 || prompt.opcode != 11 {
        return Err(fail("not own idle"));
    }
    let found: Vec<_> = prompt
        .actions
        .iter()
        .filter(|a| {
            matches!(a.choice, Choice::Command { command: 5, .. }) && a.card_ids == [57103969]
        })
        .collect();
    if found.len() != 1 {
        return Err(fail("Tenki activation not unique"));
    }
    let a = found[0];
    if let Choice::Command { index, .. } = a.choice {
        if index > 65535 || a.bytes != ((index << 16) | 5).to_le_bytes() {
            return Err(fail("Tenki encoding"));
        }
    }
    Ok(a.clone())
}
/// Independent raw-response oracle and fixed expected pending prompt assertions.
pub fn validate_prompt_probe_result(
    stage: u8,
    request: &RunDuelRequest,
    result: &DuelResult,
) -> Result<Value, String> {
    prompt_probe_purpose(stage).map_err(|e| e.message)?;
    if result.status != DuelStatus::DecisionRequired
        || result.error.is_some()
        || !result.coverage_gaps.is_empty()
        || !result.resolved_decisions.starts_with(&request.decisions)
    {
        return Err("not complete pending decision prefix".into());
    }
    let pending = result.prompt.as_ref().ok_or("pending prompt missing")?;
    if result
        .events
        .windows(2)
        .any(|pair| pair[0].sequence >= pair[1].sequence)
    {
        return Err("event sequence not strictly increasing".into());
    }
    let mut prompts = Vec::new();
    for f in &result.events {
        if matches!(f.opcode, 11..=16 | 18 | 19 | 24 | 26) {
            let p = parse_prompt(f.sequence, &f.raw)?.ok_or("raw prompt missing")?;
            let recorded: Prompt = serde_json::from_value(
                f.fields
                    .get("prompt")
                    .cloned()
                    .ok_or("recorded prompt missing")?,
            )
            .map_err(|_| "recorded prompt malformed")?;
            if p != recorded {
                return Err("raw/recorded prompt mismatch".into());
            }
            let audit = audit_prompt_responses(
                &f.raw,
                &p.actions
                    .iter()
                    .map(|a| a.bytes.clone())
                    .collect::<Vec<_>>(),
            )?;
            if !audit.matches {
                return Err("independent response oracle mismatch".into());
            }
            prompts.push((f, p));
        }
    }
    let (frame, parsed) = prompts
        .iter()
        .find(|(_, p)| p.id == pending.id)
        .ok_or("pending frame missing")?;
    if parsed != pending || pending.player != 0 {
        return Err("pending player/frame mismatch".into());
    }
    if prompts.last().map(|(_, p)| p) != Some(pending) {
        return Err("pending prompt is not final prompt".into());
    }
    for (i, d) in result.resolved_decisions.iter().enumerate() {
        if d.prompt_id >= pending.id
            || result.resolved_decisions[..i]
                .iter()
                .any(|old| old.prompt_id >= d.prompt_id)
        {
            return Err("resolved decision sequence overlaps pending".into());
        }
        let (_, p) = prompts
            .iter()
            .find(|(_, p)| p.id == d.prompt_id)
            .ok_or("decision prompt missing")?;
        if d.player != p.player
            || p.encode(&d.choice).is_err()
            || (i >= request.decisions.len()
                && (p.actions.len() != 1 || p.actions[0].choice != d.choice))
        {
            return Err("unapproved automatic decision".into());
        }
    }
    match stage {
        1 => {
            unique_tenki(pending).map_err(|e| e.message)?;
        }
        2 => {
            let mut raw = vec![13, 0];
            raw.extend(59877851398144u64.to_le_bytes());
            if frame.raw != raw
                || pending.actions.len() != 2
                || pending.actions[0].choice != (Choice::YesNo { yes: false })
                || pending.actions[1].choice != (Choice::YesNo { yes: true })
            {
                return Err("expected exact Tenki yes/no".into());
            }
        }
        3 | 4 => {
            if pending.opcode != 11 {
                return Err("false branch must return to own idle".into());
            }
        }
        5 | 6 => {
            let r = &frame.raw;
            if r.len() != 43
                || r[..3] != [15, 0, 0]
                || u32::from_le_bytes(r[3..7].try_into().unwrap()) != 1
                || u32::from_le_bytes(r[7..11].try_into().unwrap()) != 1
                || u32::from_le_bytes(r[11..15].try_into().unwrap()) != 2
                || pending.actions.len() != 2
                || pending.actions.iter().any(|a| a.card_ids != [69247929])
            {
                return Err("expected two Tenki single-card targets".into());
            }
            let mut sequences = std::collections::BTreeSet::new();
            for (index, record) in r[15..].chunks_exact(14).enumerate() {
                let code = u32::from_le_bytes(record[..4].try_into().unwrap());
                let sequence = u32::from_le_bytes(record[6..10].try_into().unwrap());
                let position = u32::from_le_bytes(record[10..14].try_into().unwrap());
                let action = &pending.actions[index];
                let expected_bytes = [0u32, 1, index as u32]
                    .iter()
                    .flat_map(|n| n.to_le_bytes())
                    .collect::<Vec<_>>();
                if code != 69247929
                    || record[4] != 0
                    || record[5] != 1
                    || sequence >= 35
                    || !sequences.insert(sequence)
                    || !matches!(position, 0 | 1 | 2 | 4 | 8)
                    || action.choice
                        != (Choice::Cards {
                            indices: vec![index as u32],
                        })
                    || action.bytes != expected_bytes
                {
                    return Err("invalid Tenki raw target coordinate or response".into());
                }
            }
        }
        _ => unreachable!(),
    }
    Ok(
        json!({"pending_opcode":pending.opcode,"raw_prompt_count":prompts.len(),"response_oracle_matches":true,"expected_target_matches":true,"automatic_decisions_single_legal":true}),
    )
}
/// Comparison clears only the volatile memory counter, preserving saved originals.
pub fn prompt_probe_replay_matches(a: &DuelResult, b: &DuelResult) -> bool {
    let mut a = encoded(a).ok();
    let mut b = encoded(b).ok();
    for value in [&mut a, &mut b].into_iter().flatten() {
        value["peak_working_set_bytes"] = Value::Null;
    }
    a == b
}
