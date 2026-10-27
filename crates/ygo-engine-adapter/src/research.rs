//! Independent bounded protocol response oracle; no engine or search qualification.
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResponseAudit {
    pub opcode: u8,
    pub matches: bool,
    pub missing: Vec<Vec<u8>>,
    pub unexpected: Vec<Vec<u8>>,
    pub duplicate_count: usize,
    pub global_optimality: bool,
    pub qualification: String,
    pub complete_action_coverage: bool,
    pub coverage_gaps: Vec<String>,
}
struct Cursor<'a>(&'a [u8]);
impl Cursor<'_> {
    fn take(&mut self, count: usize) -> Result<&[u8], String> {
        if count > self.0.len() {
            return Err("truncated oracle input".into());
        }
        let (head, tail) = self.0.split_at(count);
        self.0 = tail;
        Ok(head)
    }
    fn byte(&mut self) -> Result<u8, String> {
        Ok(self.take(1)?[0])
    }
    fn number(&mut self) -> Result<usize, String> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().unwrap()) as usize)
    }
}
fn response(numbers: &[u32]) -> Vec<u8> {
    numbers.iter().flat_map(|n| n.to_le_bytes()).collect()
}
// Enumerate via include/exclude traversal independently from the production combinations routine.
fn subsets(n: usize, min: usize, max: usize) -> Result<Vec<Vec<usize>>, String> {
    if min > max || max > n || n > 4096 {
        return Err("invalid oracle bounds".into());
    }
    let mut stack = vec![(0usize, Vec::new())];
    let mut result = Vec::new();
    while let Some((offset, chosen)) = stack.pop() {
        if chosen.len() > max || chosen.len() + n - offset < min {
            continue;
        }
        if offset == n {
            result.push(chosen);
            if result.len() > 4096 {
                return Err("oracle combination limit exceeded".into());
            }
        } else {
            stack.push((offset + 1, chosen.clone()));
            if chosen.len() < max {
                let mut included = chosen;
                included.push(offset);
                stack.push((offset + 1, included));
            }
        }
    }
    Ok(result)
}
/// Expected wire responses read directly from one unframed ocgcore prompt.
/// Unsupported or bounded-out prompts return a gap rather than an empty legal set.
pub fn expected_prompt_responses(raw: &[u8]) -> Result<Vec<Vec<u8>>, String> {
    let mut r = Cursor(raw);
    let opcode = r.byte()?;
    let player = r.byte()?;
    if player > 1 {
        return Err("invalid oracle player".into());
    }
    let mut out = Vec::new();
    match opcode {
        11 => {
            for command in 0..6u32 {
                let count = r.number()?;
                if count > 4096 {
                    return Err("oracle count limit".into());
                }
                for index in 0..count {
                    r.take(if command == 5 { 19 } else { 10 })?;
                    out.push(response(&[(index as u32) << 16 | command]));
                }
            }
            let battle = r.byte()?;
            let end = r.byte()?;
            let shuffle = r.byte()?;
            if battle != 0 {
                out.push(response(&[6]));
            }
            if end != 0 {
                out.push(response(&[7]));
            }
            if shuffle != 0 {
                out.push(response(&[8]));
            }
        }
        12 | 13 => {
            if opcode == 12 {
                r.take(14)?;
            }
            r.take(8)?;
            out.extend([response(&[0]), response(&[1])]);
        }
        14 => {
            let count = r.byte()?;
            for index in 0..count {
                r.take(8)?;
                out.push(response(&[index as u32]));
            }
        }
        15 => {
            let cancel = r.byte()?;
            let min = r.number()?;
            let max = r.number()?;
            let n = r.number()?;
            r.take(n.checked_mul(14).ok_or("oracle length overflow")?)?;
            for set in subsets(n, min, max)? {
                let mut words = vec![0, set.len() as u32];
                words.extend(set.iter().map(|x| *x as u32));
                out.push(response(&words));
            }
            if cancel != 0 {
                out.push(response(&[u32::MAX]));
            }
        }
        16 => {
            r.byte()?;
            let forced = r.byte()?;
            r.take(8)?;
            let n = r.number()?;
            if n > 4096 {
                return Err("oracle count limit".into());
            }
            for i in 0..n {
                r.take(23)?;
                out.push(response(&[i as u32]));
            }
            if forced == 0 {
                out.push(response(&[u32::MAX]));
            }
        }
        18 | 24 => {
            let count = r.byte()? as usize;
            let mask = r.number()? as u32;
            let mut slots = Vec::new();
            for bit in 0..32 {
                let local = bit % 16;
                if (local < 7 || (8..16).contains(&local)) && mask & (1 << bit) == 0 {
                    slots.push([
                        if bit < 16 { player } else { 1 - player },
                        if local < 8 { 4 } else { 8 },
                        (local % 8) as u8,
                    ]);
                }
            }
            for set in subsets(slots.len(), count, count)? {
                out.push(set.iter().flat_map(|i| slots[*i]).collect());
            }
        }
        19 => {
            r.take(4)?;
            let mask = r.byte()?;
            for bit in [1u8, 2, 4, 8] {
                if mask & bit != 0 {
                    out.push(response(&[bit as u32]));
                }
            }
        }
        26 => {
            let finish = r.byte()?;
            let cancel = r.byte()?;
            r.take(8)?;
            let mut total = 0;
            for _ in 0..2 {
                let n = r.number()?;
                if n > 4096 {
                    return Err("oracle count limit".into());
                }
                r.take(n * 14)?;
                total += n;
            }
            for i in 0..total {
                out.push(response(&[1, i as u32]));
            }
            if finish != 0 || cancel != 0 {
                out.push(response(&[u32::MAX]));
            }
        }
        _ => return Err(format!("unsupported opcode {opcode}")),
    }
    if !r.0.is_empty() {
        return Err("oracle unexpected tail".into());
    }
    out.sort();
    Ok(out)
}
/// Compare externally supplied wire encodings with the independent oracle.
pub fn audit_prompt_responses(raw: &[u8], actual: &[Vec<u8>]) -> Result<ResponseAudit, String> {
    let expected: BTreeSet<_> = expected_prompt_responses(raw)?.into_iter().collect();
    let found: BTreeSet<_> = actual.iter().cloned().collect();
    let missing = expected.difference(&found).cloned().collect::<Vec<_>>();
    let unexpected = found.difference(&expected).cloned().collect::<Vec<_>>();
    let duplicate_count = actual.len() - found.len();
    Ok(ResponseAudit {
        opcode: raw[0],
        matches: missing.is_empty() && unexpected.is_empty() && duplicate_count == 0,
        missing,
        unexpected,
        duplicate_count,
        global_optimality: false,
        qualification: "canonical_response_comparison".into(),
        complete_action_coverage: false,
        coverage_gaps: vec![
            "ordering_equivalence_unproven".into(),
            "protocol_oracle_is_not_engine_semantic_proof".into(),
        ],
    })
}

/// A single durable ledger enforces all first-batch limits, including across reopen.
pub struct ResearchBatch {
    journal: std::sync::Arc<crate::CallJournal>,
    started: u64,
    resume: Option<AuthorizedWindow>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct AuthorizedWindow {
    id: String,
    case_id: String,
    started: u64,
    base_consumed: usize,
    additional_calls: usize,
}
impl ResearchBatch {
    pub fn open(path: &std::path::Path, context: &str) -> Result<Self, crate::WorkerError> {
        let journal = crate::CallJournal::open(path, "research-first-batch-v1", context, 4096)?;
        let started = match journal.checkpoint("research/start")? {
            Some(v) => v
                .as_u64()
                .ok_or_else(|| research_error("invalid persisted start"))?,
            None => {
                let now = unix_seconds()?;
                journal.save_checkpoint("research/start", &serde_json::json!(now))?;
                now
            }
        };
        Ok(Self {
            journal,
            started,
            resume: None,
        })
    }
    /// Record a separately human-authorized two-call continuation.
    ///
    /// The caller must obtain authorization outside this library. The ID is
    /// only an audit reference, not proof of authorization. A new ID starts
    /// this continuation's clock but does not reset the shared ledger budget.
    pub fn open_authorized_window(
        path: &std::path::Path,
        context: &str,
        id: &str,
        case_id: &str,
    ) -> Result<Self, crate::WorkerError> {
        for value in [id, case_id] {
            if value.is_empty()
                || !value
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'-')
            {
                return Err(research_error("invalid authorized window identity"));
            }
        }
        let mut batch = Self::open(path, context)?;
        let stats = batch.stats()?;
        if stats.unknown != 0 {
            return Err(research_error("unresolved calls block a new window"));
        }
        let key = format!("immutable/research/authorized-window/{id}");
        let window: AuthorizedWindow = match batch.journal.checkpoint(&key)? {
            Some(value) => serde_json::from_value(value)
                .map_err(|_| research_error("invalid authorized window checkpoint"))?,
            None => {
                if stats.consumed > 4094 {
                    return Err(research_error("insufficient total call budget"));
                }
                let value = AuthorizedWindow {
                    id: id.into(),
                    case_id: case_id.into(),
                    started: unix_seconds()?,
                    base_consumed: stats.consumed,
                    additional_calls: 2,
                };
                batch.journal.save_checkpoint(
                    &key,
                    &serde_json::to_value(&value)
                        .map_err(|_| research_error("window serialization failed"))?,
                )?;
                value
            }
        };
        if window.id != id
            || window.case_id != case_id
            || window.additional_calls != 2
            || window.base_consumed > 4094
            || window.base_consumed > stats.consumed
        {
            return Err(research_error(
                "authorized window differs from frozen binding",
            ));
        }
        batch.started = window.started;
        batch.resume = Some(window);
        Ok(batch)
    }
    /// Observed window provenance, not a substitute for the caller's human authorization.
    pub fn authorized_window(&self) -> Option<serde_json::Value> {
        self.resume
            .as_ref()
            .map(|v| serde_json::to_value(v).expect("window consists of primitive fields"))
    }
    /// Restore and verify recorded evidence without starting any engine call.
    pub fn load_outcome(
        &self,
        call_id: u64,
        request: &crate::RunDuelRequest,
    ) -> Result<Option<Result<crate::DuelResult, crate::WorkerError>>, crate::WorkerError> {
        self.journal.load_outcome(call_id, request)
    }
    pub fn stats(&self) -> Result<crate::LedgerStats, crate::WorkerError> {
        self.journal.stats()
    }
    pub fn verify(&self) -> Result<(), crate::WorkerError> {
        self.journal.verify()
    }
    pub fn charged_sequence_id(&self) -> Result<String, crate::WorkerError> {
        self.journal.charged_sequence_id()
    }
    fn authorize(&self, case: &str, now: u64) -> Result<usize, crate::WorkerError> {
        if case.is_empty() || !case.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-') {
            return Err(research_error("invalid case id"));
        }
        if now < self.started || now - self.started >= 7170 {
            return Err(research_error(
                "batch wall-clock exhausted or clock moved backwards",
            ));
        }
        let stats = self.journal.stats()?;
        if let Some(window) = &self.resume {
            if case != window.case_id || stats.consumed >= window.base_consumed + 2 {
                return Err(research_error(
                    "authorized two-call continuation exhausted or wrong case",
                ));
            }
        }
        if stats.consumed >= 4096 || stats.unknown > 0 {
            return Err(research_error("batch calls exhausted or unresolved call"));
        }
        let mut counts = std::collections::BTreeMap::<String, usize>::new();
        for index in 0..stats.consumed {
            let value = self
                .journal
                .checkpoint(&format!("research/debit/{index}"))?
                .ok_or_else(|| research_error("missing case debit"))?;
            let name = value
                .as_str()
                .ok_or_else(|| research_error("invalid case debit"))?
                .to_string();
            *counts.entry(name).or_default() += 1;
        }
        if self
            .journal
            .checkpoint(&format!("research/debit/{}", stats.consumed))?
            .is_some()
        {
            return Err(research_error(
                "unfinished pre-call intent requires investigation",
            ));
        }
        validate_counts(stats.consumed, &counts, case)?;
        Ok(stats.consumed)
    }
    /// Every request, including independent replay and failure, passes the same accounting gate.
    pub fn run<A: crate::EngineAdapter>(
        &self,
        adapter: A,
        case: &str,
        request: &crate::RunDuelRequest,
        purpose: crate::CallPurpose,
    ) -> Result<crate::DuelResult, crate::WorkerError> {
        if request.engine.timeout_ms != 30000 {
            return Err(research_error("research worker timeout must be 30000ms"));
        }
        let index = self.authorize(case, unix_seconds()?)?;
        if let Some(window) = &self.resume {
            let expected = if index == window.base_consumed {
                crate::CallPurpose::Execution
            } else {
                crate::CallPurpose::Replay
            };
            if purpose != expected {
                return Err(research_error(
                    "authorized continuation requires execution then replay",
                ));
            }
        }
        let request_hash = crate::digest(
            &serde_json::to_vec(request)
                .map_err(|_| research_error("request serialization failed"))?,
        );
        let binding_name = format!("immutable/research/case/{case}");
        match self.journal.checkpoint(&binding_name)? {
            None => self
                .journal
                .save_checkpoint(&binding_name, &serde_json::json!(request_hash))?,
            Some(existing) if existing.as_str() == Some(request_hash.as_str()) => {}
            Some(_) => return Err(research_error("case request differs from frozen binding")),
        }

        self.journal
            .save_checkpoint(&format!("research/debit/{index}"), &serde_json::json!(case))?;
        crate::EngineAdapter::run(
            &crate::JournaledAdapter::new(adapter, self.journal.clone(), purpose),
            request,
        )
    }
}
fn validate_counts(
    total: usize,
    counts: &std::collections::BTreeMap<String, usize>,
    case: &str,
) -> Result<(), crate::WorkerError> {
    if total >= 4096
        || counts.get(case).copied().unwrap_or(0) >= 512
        || (!counts.contains_key(case) && counts.len() >= 8)
    {
        return Err(research_error("batch/case count exhausted"));
    }
    Ok(())
}
fn research_error(message: &str) -> crate::WorkerError {
    crate::WorkerError::new("research_budget", "research", message)
}
fn unix_seconds() -> Result<u64, crate::WorkerError> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs())
        .map_err(|_| research_error("system time before epoch"))
}

#[cfg(test)]
mod budget_tests {
    use super::*;
    struct Fail;
    impl crate::EngineAdapter for Fail {
        fn doctor(&self) -> crate::DoctorReport {
            panic!("unused")
        }
        fn run(&self, _: &crate::RunDuelRequest) -> Result<crate::DuelResult, crate::WorkerError> {
            Err(crate::WorkerError::new(
                "synthetic",
                "test",
                "count failure",
            ))
        }
    }
    use crate::*;
    fn path() -> std::path::PathBuf {
        let path = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "research-{}-{}.jsonl",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        path
    }
    fn request() -> RunDuelRequest {
        serde_json::from_value(serde_json::json!({"protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":RuntimeVersions::default()})).unwrap()
    }
    #[test]
    fn identical_request_execution_and_replay_both_reach_backend_after_reopen() {
        let path = path();
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert_eq!(
            batch
                .run(Fail, "case", &request(), CallPurpose::Execution)
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert_eq!(
            batch
                .run(Fail, "case", &request(), CallPurpose::Replay)
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert_eq!(batch.stats().unwrap().consumed, 2);
        drop(batch);
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert_eq!(
            batch
                .run(Fail, "case", &request(), CallPurpose::Replay)
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert_eq!(batch.stats().unwrap().consumed, 3);
        let mut changed = request();
        changed.seed = 2;
        assert_eq!(
            batch
                .run(Fail, "case", &changed, CallPurpose::Replay)
                .unwrap_err()
                .code,
            "research_budget"
        );
        assert_eq!(batch.stats().unwrap().consumed, 3);
    }
    #[test]
    fn authorized_resume_window_preserves_old_start_and_allows_only_two_more_calls() {
        let path = path();
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        for _ in 0..7 {
            assert_eq!(
                batch
                    .run(Fail, "case", &request(), CallPurpose::Execution)
                    .unwrap_err()
                    .code,
                "synthetic"
            );
        }
        let expired = unix_seconds().unwrap() - 8000;
        batch
            .journal
            .save_checkpoint("research/start", &serde_json::json!(expired))
            .unwrap();
        drop(batch);
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert!(batch
            .run(Fail, "case", &request(), CallPurpose::Execution)
            .is_err());
        drop(batch);
        let batch =
            ResearchBatch::open_authorized_window(&path, "fixed", "user-resume", "case").unwrap();
        assert_eq!(
            batch.journal.checkpoint("research/start").unwrap(),
            Some(serde_json::json!(expired))
        );
        assert!(batch
            .run(Fail, "other", &request(), CallPurpose::Execution)
            .is_err());
        assert!(batch
            .run(Fail, "case", &request(), CallPurpose::Replay)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 7);
        assert_eq!(
            batch
                .run(Fail, "case", &request(), CallPurpose::Execution)
                .unwrap_err()
                .code,
            "synthetic"
        );
        let start = batch.started;
        drop(batch);
        let batch =
            ResearchBatch::open_authorized_window(&path, "fixed", "user-resume", "case").unwrap();
        assert_eq!(batch.started, start);
        assert_eq!(
            batch
                .run(Fail, "case", &request(), CallPurpose::Replay)
                .unwrap_err()
                .code,
            "synthetic"
        );
        assert!(batch
            .run(Fail, "case", &request(), CallPurpose::Replay)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 9);
        drop(batch);
        let batch =
            ResearchBatch::open_authorized_window(&path, "fixed", "user-resume", "case").unwrap();
        assert!(batch.authorize("case", unix_seconds().unwrap()).is_err());
        assert_eq!(batch.stats().unwrap().consumed, 9);
        drop(batch);
        assert!(
            ResearchBatch::open_authorized_window(&path, "fixed", "user-resume", "different")
                .is_err()
        );
        let original = ResearchBatch::open(&path, "fixed").unwrap();
        assert_eq!(original.started, expired);
        assert!(original.authorize("case", unix_seconds().unwrap()).is_err());
    }
    #[test]
    fn total_boundary_and_request_binding_reject_before_another_charge() {
        let mut counts = std::collections::BTreeMap::new();
        counts.insert("case".to_string(), 511);
        assert!(validate_counts(4095, &counts, "case").is_ok());
        assert!(validate_counts(4096, &counts, "case").is_err());
        counts.insert("case".to_string(), 512);
        assert!(validate_counts(512, &counts, "case").is_err());
        let path = path();
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert!(batch
            .run(Fail, "case", &request(), CallPurpose::Execution)
            .is_err());
        let mut changed = request();
        changed.seed = 2;
        assert!(batch
            .run(Fail, "case", &changed, CallPurpose::Replay)
            .is_err());
        assert_eq!(batch.stats().unwrap().consumed, 1);
    }
    #[test]
    fn wall_time_and_unfinished_intent_survive_reopen() {
        let path = path();
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        let start = batch.started;
        assert!(batch.authorize("case", start + 7169).is_ok());
        assert!(batch.authorize("case", start + 7170).is_err());
        assert!(batch.authorize("case", start - 1).is_err());
        batch
            .journal
            .save_checkpoint("research/debit/0", &serde_json::json!("case"))
            .unwrap();
        drop(batch);
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert_eq!(batch.started, start);
        assert!(batch.authorize("case", start).is_err());
        drop(batch);
        assert!(ResearchBatch::open(&path, "changed").is_err());
    }
    #[test]
    fn per_case_and_eight_case_limits_count_failures_and_reopens() {
        let path = path();
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        for i in 0..512 {
            batch
                .journal
                .save_checkpoint(&format!("research/debit/{i}"), &serde_json::json!("case"))
                .unwrap();
            assert!(
                JournaledAdapter::new(Fail, batch.journal.clone(), CallPurpose::Audit)
                    .run(&request())
                    .is_err()
            );
        }
        let started = batch.started;
        drop(batch);
        let batch = ResearchBatch::open(&path, "fixed").unwrap();
        assert_eq!(batch.stats().unwrap().consumed, 512);
        assert!(batch.authorize("case", started).is_err());
        assert!(batch.authorize("other", started).is_ok());
        for i in 512..519 {
            batch
                .journal
                .save_checkpoint(
                    &format!("research/debit/{i}"),
                    &serde_json::json!(format!("case-{i}")),
                )
                .unwrap();
            assert!(
                JournaledAdapter::new(Fail, batch.journal.clone(), CallPurpose::Replay)
                    .run(&request())
                    .is_err()
            );
        }
        assert!(batch.authorize("ninth", started).is_err());
        assert!(batch.authorize("case-512", started).is_ok());
        batch.verify().unwrap();
    }
}
