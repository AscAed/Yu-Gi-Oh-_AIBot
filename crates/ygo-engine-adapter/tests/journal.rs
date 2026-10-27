use std::{
    path::PathBuf,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
};
use ygo_engine_adapter::*;

fn folder() -> PathBuf {
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    let base = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data/tmp");
    let name = format!(
        "journal-test-{}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    );
    let path = base.join(name);
    std::fs::create_dir_all(&path).unwrap();
    path
}

fn readonly_folder() -> PathBuf {
    static NEXT: AtomicUsize = AtomicUsize::new(0);
    let base = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/curry-option-validation-tests/tmp");
    let name = format!(
        "journal-readonly-test-{}-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        NEXT.fetch_add(1, Ordering::SeqCst)
    );
    let path = base.join(name);
    std::fs::create_dir_all(&path).unwrap();
    path
}
fn request() -> RunDuelRequest {
    serde_json::from_value(serde_json::json!({"protocol_version":2,"engine":{},
        "deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],
        "versions":{"rules":"ocg-mr5","catalog":"test","banlist":"test","engine_sha256":"engine","cdb_sha256":"cdb","scripts_sha256":"scripts","core_commit":"core"}})).unwrap()
}
#[derive(Clone)]
struct Fake(Arc<AtomicUsize>);
impl EngineAdapter for Fake {
    fn doctor(&self) -> DoctorReport {
        DoctorReport {
            ready: true,
            assets_ok: true,
            abi_ok: true,
            smoke_ok: None,
            issues: vec![],
        }
    }
    fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        self.0.fetch_add(1, Ordering::SeqCst);
        let mut r = DuelResult::failure(WorkerError::new("test", "test", "test"));
        r.error = None;
        r.status = DuelStatus::DecisionRequired;
        r.versions = q.versions.clone();
        r.peak_working_set_bytes = Some(42);
        Ok(r)
    }
}

#[test]
fn durable_debits_reservations_cache_and_resume_are_separate() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let count = Arc::new(AtomicUsize::new(0));
    let q = request();
    let journal = CallJournal::open(&path, "cell-a", "request-a", 3).unwrap();
    journal.reserve("replay", 1).unwrap();
    assert_eq!(journal.stats().unwrap().consumed, 0);
    let adapter =
        JournaledAdapter::new(Fake(count.clone()), journal.clone(), CallPurpose::Execution);
    let result = adapter.run(&q).unwrap();
    assert_eq!(journal.stats().unwrap().consumed, 1);
    assert_eq!(journal.stats().unwrap().reserved, 1);
    let cached = journal.load_result(1, &q).unwrap().unwrap();
    assert_eq!(result.checkpoint, cached.checkpoint);
    assert_eq!(count.load(Ordering::SeqCst), 1);
    adapter.run_reserved(&q, "replay").unwrap();
    assert_eq!(journal.stats().unwrap().reserved, 0);
    drop(adapter);
    drop(journal);
    let resumed = CallJournal::open(&path, "cell-a", "request-a", 3).unwrap();
    assert_eq!(resumed.stats().unwrap().consumed, 2);
    assert_eq!(resumed.stats().unwrap().completed, 2);
    assert_eq!(resumed.stats().unwrap().unknown, 0);
    let adapter = JournaledAdapter::new(Fake(count.clone()), resumed.clone(), CallPurpose::Replay);
    adapter.run(&q).unwrap();
    assert_eq!(adapter.run(&q).unwrap_err().code, "journal_budget");
    assert_eq!(count.load(Ordering::SeqCst), 3);
}

#[test]
fn crash_after_debit_is_not_a_free_retry() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "effect-a", "knowledge-a", 2).unwrap();
    journal
        .begin_call(&q, CallPurpose::RuleVerification, None)
        .unwrap();
    drop(journal);
    let journal = CallJournal::open(&path, "effect-a", "knowledge-a", 2).unwrap();
    assert_eq!(journal.stats().unwrap().unknown, 1);
    assert_eq!(journal.stats().unwrap().consumed, 1);
    assert!(journal.load_result(1, &q).unwrap().is_none());
    let count = Arc::new(AtomicUsize::new(0));
    let adapter = JournaledAdapter::new(
        Fake(count.clone()),
        journal.clone(),
        CallPurpose::RuleVerification,
    );
    adapter.run(&q).unwrap();
    assert_eq!(journal.stats().unwrap().consumed, 2);
    assert_eq!(count.load(Ordering::SeqCst), 1);
    assert!(adapter.run(&q).is_err());
}

#[test]
fn another_writer_changed_context_and_tampered_records_are_rejected() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let journal = CallJournal::open(&path, "cell", "frozen", 2).unwrap();
    assert!(CallJournal::open(&path, "cell", "frozen", 2).is_err());
    drop(journal);
    assert!(CallJournal::open(&path, "cell", "changed", 2).is_err());
    assert!(CallJournal::open(&path, "cell", "frozen", 3).is_err());
    let bytes = std::fs::read_to_string(&path)
        .unwrap()
        .replace("frozen", "forged");
    std::fs::write(&path, bytes).unwrap();
    assert!(CallJournal::open(&path, "cell", "forged", 2).is_err());
}

#[test]
fn readonly_journal_view_releases_shared_lock_before_exclusive_writer_open() {
    let dir = readonly_folder();
    let path = dir.join("calls.jsonl");
    drop(CallJournal::open(&path, "lock-lifetime", "fixed-context", 2).unwrap());

    let view = CallJournal::inspect_existing(&path, "lock-lifetime", "fixed-context", 2)
        .unwrap()
        .unwrap();
    assert!(CallJournal::open(&path, "lock-lifetime", "fixed-context", 2).is_err());
    drop(view);

    let writer = CallJournal::open(&path, "lock-lifetime", "fixed-context", 2).unwrap();
    assert!(CallJournal::inspect_existing(&path, "lock-lifetime", "fixed-context", 2).is_err());
    drop(writer);
}

#[test]
fn result_tampering_and_different_resume_request_are_rejected() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "cell", "context", 2).unwrap();
    let adapter = JournaledAdapter::new(
        Fake(Arc::new(AtomicUsize::new(0))),
        journal.clone(),
        CallPurpose::Execution,
    );
    adapter.run(&q).unwrap();
    let mut changed = q.clone();
    changed.seed = 2;
    assert!(journal.load_result(1, &changed).is_err());
    let file = std::fs::read_dir(dir.join("calls.jsonl.blobs/results"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    std::fs::write(file, b"forged result").unwrap();
    assert!(journal.load_result(1, &q).is_err());
}

#[test]
fn ledger_creation_failure_does_not_start_the_engine() {
    let dir = folder();
    let file = dir.join("not-a-directory");
    std::fs::write(&file, b"occupied").unwrap();
    let count = Arc::new(AtomicUsize::new(0));
    assert!(CallJournal::open(file.join("calls.jsonl"), "cell", "context", 2).is_err());
    assert_eq!(count.load(Ordering::SeqCst), 0);
}

#[test]
fn safe_checkpoint_resume_has_the_same_charged_sequence() {
    let q = request();
    let execute = |journal: Arc<CallJournal>, purpose| {
        JournaledAdapter::new(Fake(Arc::new(AtomicUsize::new(0))), journal, purpose)
            .run(&q)
            .unwrap();
    };
    let dir = folder();
    let path = dir.join("resumed.jsonl");
    let resumed = CallJournal::open(&path, "case", "frozen", 3).unwrap();
    execute(resumed.clone(), CallPurpose::Execution);
    drop(resumed);
    let resumed = CallJournal::open(&path, "case", "frozen", 3).unwrap();
    assert!(resumed.load_result(1, &q).unwrap().is_some());
    execute(resumed.clone(), CallPurpose::Replay);
    let uninterrupted = CallJournal::open(dir.join("full.jsonl"), "case", "frozen", 3).unwrap();
    execute(uninterrupted.clone(), CallPurpose::Execution);
    execute(uninterrupted.clone(), CallPurpose::Replay);
    assert_eq!(resumed.stats().unwrap(), uninterrupted.stats().unwrap());
    assert_eq!(
        resumed.charged_sequence_id().unwrap(),
        uninterrupted.charged_sequence_id().unwrap()
    );
}

#[test]
fn readonly_inspection_never_repairs_or_changes_a_journal() {
    let dir = readonly_folder();
    let path = dir.join("readonly.jsonl");
    let journal = CallJournal::open(&path, "readonly", "frozen", 6).unwrap();
    journal
        .save_checkpoint("immutable/seed", &serde_json::json!({"started_at":1}))
        .unwrap();
    drop(journal);

    let before = std::fs::read(&path).unwrap();
    let view = CallJournal::inspect_existing(&path, "readonly", "frozen", 6)
        .unwrap()
        .expect("existing journal");
    assert_eq!(view.stats().unwrap().consumed, 0);
    assert_eq!(
        view.checkpoint("immutable/seed").unwrap(),
        Some(serde_json::json!({"started_at":1}))
    );
    assert_eq!(view.charged_sequence_id().unwrap().len(), 64);
    drop(view);
    assert_eq!(std::fs::read(&path).unwrap(), before);

    let mut torn = before;
    torn.extend_from_slice(b"{\"torn\":true}");
    std::fs::write(&path, &torn).unwrap();
    assert!(CallJournal::inspect_existing(&path, "readonly", "frozen", 6).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), torn);
}

#[test]
fn readonly_inspection_distinguishes_missing_from_invalid_without_creating_files() {
    let dir = readonly_folder();
    let missing = dir.join("missing.jsonl");
    assert!(
        CallJournal::inspect_existing(&missing, "readonly", "frozen", 6)
            .unwrap()
            .is_none()
    );
    assert!(!missing.exists());

    let path = dir.join("invalid.jsonl");
    std::fs::write(&path, b"not-json\n").unwrap();
    let before = std::fs::read(&path).unwrap();
    assert!(CallJournal::inspect_existing(&path, "readonly", "frozen", 6).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), before);
    assert!(!path.with_extension("jsonl.blobs").exists());
}

#[test]
fn readonly_inspection_rejects_blank_records_without_normalizing_them() {
    let dir = readonly_folder();
    let path = dir.join("blank-record.jsonl");
    let journal = CallJournal::open(&path, "readonly", "frozen", 6).unwrap();
    drop(journal);
    let mut bytes = std::fs::read(&path).unwrap();
    bytes.extend_from_slice(b"\n");
    std::fs::write(&path, &bytes).unwrap();
    assert!(CallJournal::inspect_existing(&path, "readonly", "frozen", 6).is_err());
    assert_eq!(std::fs::read(&path).unwrap(), bytes);
}

#[test]
fn readonly_inspection_binds_recovery_marker_to_its_journal_prefix() {
    let dir = readonly_folder();
    let path = dir.join("recovery.jsonl");
    drop(CallJournal::open(&path, "readonly", "frozen", 6).unwrap());
    use std::io::Write;
    std::fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"{\"truncated\":true")
        .unwrap();
    drop(CallJournal::open(&path, "readonly", "frozen", 6).unwrap());

    let mut blob_root = path.as_os_str().to_owned();
    blob_root.push(".blobs");
    let recovery_dir = PathBuf::from(blob_root).join("recoveries");
    let marker_path = std::fs::read_dir(&recovery_dir)
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    let mut marker: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&marker_path).unwrap()).unwrap();
    marker["prefix_hash"] = serde_json::json!("a".repeat(64));
    let marker_bytes = serde_json::to_vec(&marker).unwrap();
    let forged_path = recovery_dir.join(format!("{}.json", digest(&marker_bytes)));
    std::fs::write(&forged_path, marker_bytes).unwrap();
    std::fs::remove_file(marker_path).unwrap();

    assert!(CallJournal::inspect_existing(&path, "readonly", "frozen", 6).is_err());
}

#[test]
fn immutable_checkpoint_exposes_its_charged_prefix_not_the_later_tail() {
    let dir = folder();
    let journal = CallJournal::open(dir.join("prefix.jsonl"), "case", "frozen", 3).unwrap();
    let q = request();
    JournaledAdapter::new(
        Fake(Arc::new(AtomicUsize::new(0))),
        journal.clone(),
        CallPurpose::Probe,
    )
    .run(&q)
    .unwrap();
    let first = journal.charged_sequence_id().unwrap();
    journal
        .save_checkpoint("immutable/prefix-one", &serde_json::json!({"ok":true}))
        .unwrap();
    JournaledAdapter::new(
        Fake(Arc::new(AtomicUsize::new(0))),
        journal.clone(),
        CallPurpose::Replay,
    )
    .run(&q)
    .unwrap();
    assert_eq!(
        journal.checkpoint_consumed("immutable/prefix-one").unwrap(),
        Some(1)
    );
    assert_eq!(
        journal
            .checkpoint_charged_sequence_id("immutable/prefix-one")
            .unwrap()
            .as_deref(),
        Some(first.as_str())
    );
    assert_ne!(journal.charged_sequence_id().unwrap(), first);
}

#[test]
fn incomplete_result_storage_keeps_the_debit_and_forbids_a_free_retry() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    // Obstruct result persistence after the debit, without affecting the engine.
    let results = dir.join("calls.jsonl.blobs/results");
    std::fs::remove_dir(&results).unwrap();
    std::fs::write(&results, b"occupied").unwrap();
    let count = Arc::new(AtomicUsize::new(0));
    let adapter =
        JournaledAdapter::new(Fake(count.clone()), journal.clone(), CallPurpose::Execution);
    assert!(adapter.run(&q).is_err());
    assert_eq!(count.load(Ordering::SeqCst), 1);
    assert_eq!(journal.stats().unwrap().unknown, 1);
    assert_eq!(journal.stats().unwrap().consumed, 1);
}

#[test]
fn torn_completion_tail_preserves_evidence_and_pending_debit() {
    use std::io::Write;
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    journal
        .begin_call(&q, CallPurpose::Execution, None)
        .unwrap();
    drop(journal);
    std::fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"{\"sequence\":2,\"previous\":\"torn")
        .unwrap();
    let resumed = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    assert_eq!(resumed.stats().unwrap().consumed, 1);
    assert_eq!(resumed.stats().unwrap().unknown, 1);
    assert_eq!(resumed.recoveries().unwrap().len(), 1);
    assert!(resumed.load_result(1, &q).unwrap().is_none());
    drop(resumed);
    let reopened = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    assert_eq!(reopened.stats().unwrap().consumed, 1);
    assert_eq!(reopened.recoveries().unwrap().len(), 1);
}

#[test]
fn torn_debit_tail_is_conservatively_charged() {
    use std::io::Write;
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let journal = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    drop(journal);
    std::fs::OpenOptions::new()
        .append(true)
        .open(&path)
        .unwrap()
        .write_all(b"{\"sequence\":1")
        .unwrap();
    let resumed = CallJournal::open(&path, "case", "frozen", 2).unwrap();
    assert_eq!(resumed.stats().unwrap().consumed, 1);
    assert_eq!(resumed.stats().unwrap().unknown, 1);
    assert!(resumed.recoveries().unwrap()[0].additional_charge);
}

#[test]
fn search_checkpoint_binds_candidate_order_and_budget_to_completed_calls() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "matrix-a", "suite-a", 3).unwrap();
    let adapter = JournaledAdapter::new(
        Fake(Arc::new(AtomicUsize::new(0))),
        journal.clone(),
        CallPurpose::Execution,
    );
    adapter.run(&q).unwrap();
    let search = serde_json::json!({"frontier":["b","a"],"expanded":7,"next_cell":2});
    journal.save_checkpoint("search", &search).unwrap();
    journal.verify().unwrap();
    drop(adapter);
    drop(journal);
    let resumed = CallJournal::open(&path, "matrix-a", "suite-a", 3).unwrap();
    assert_eq!(resumed.checkpoint("search").unwrap().unwrap(), search);
    resumed.begin_call(&q, CallPurpose::Replay, None).unwrap();
    assert!(resumed.save_checkpoint("uncertain", &search).is_err());
    let checkpoint = std::fs::read_dir(dir.join("calls.jsonl.blobs/checkpoints"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    std::fs::write(checkpoint, b"forged frontier").unwrap();
    assert!(resumed.checkpoint("search").is_err());
    assert!(resumed.verify().is_err());
}

#[test]
fn chunked_prefix_evidence_is_shared_and_verified() {
    #[derive(Clone)]
    struct WithEvents;
    impl EngineAdapter for WithEvents {
        fn doctor(&self) -> DoctorReport {
            Fake(Arc::new(AtomicUsize::new(0))).doctor()
        }
        fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            let mut r = Fake(Arc::new(AtomicUsize::new(0))).run(q)?;
            let event = CoreEventFrame {
                sequence: 0,
                opcode: 1,
                raw: vec![1],
                supported: true,
                fields: serde_json::json!({}),
            };
            r.events = vec![event; 128];
            Ok(r)
        }
    }
    let dir = folder();
    let journal = CallJournal::open(dir.join("calls.jsonl"), "case", "source", 2).unwrap();
    let q = request();
    let adapter = JournaledAdapter::new(WithEvents, journal.clone(), CallPurpose::Execution);
    adapter.run(&q).unwrap();
    adapter.run(&q).unwrap();
    assert_eq!(
        std::fs::read_dir(dir.join("calls.jsonl.blobs/events"))
            .unwrap()
            .count(),
        1
    );
    assert_eq!(
        journal.load_result(1, &q).unwrap().unwrap().events.len(),
        128
    );
    journal.verify().unwrap();
    let chunk = std::fs::read_dir(dir.join("calls.jsonl.blobs/events"))
        .unwrap()
        .next()
        .unwrap()
        .unwrap()
        .path();
    std::fs::write(chunk, b"forged raw events").unwrap();
    assert!(journal.verify().is_err());
}

#[test]
fn adapter_failures_are_charged_completed_and_reusable_as_failures() {
    struct Fails;
    impl EngineAdapter for Fails {
        fn doctor(&self) -> DoctorReport {
            Fake(Arc::new(AtomicUsize::new(0))).doctor()
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Err(WorkerError::new("spawn", "process", "unavailable"))
        }
    }
    let dir = folder();
    let q = request();
    let journal = CallJournal::open(dir.join("calls.jsonl"), "case", "source", 1).unwrap();
    let adapter = JournaledAdapter::new(Fails, journal.clone(), CallPurpose::Execution);
    assert_eq!(adapter.run(&q).unwrap_err().code, "spawn");
    assert_eq!(journal.stats().unwrap().completed, 1);
    assert_eq!(journal.stats().unwrap().consumed, 1);
    assert_eq!(journal.load_result(1, &q).unwrap_err().code, "spawn");
    journal.verify().unwrap();
}

#[test]
fn disclosed_unknown_calls_remain_charged_while_later_checkpoints_can_progress() {
    let dir = folder();
    let path = dir.join("calls.jsonl");
    let q = request();
    let journal = CallJournal::open(&path, "case", "frozen", 3).unwrap();
    journal
        .begin_call(&q, CallPurpose::Execution, None)
        .unwrap();
    drop(journal);
    let journal = CallJournal::open(&path, "case", "frozen", 3).unwrap();
    assert!(journal.acknowledge_unknown(1, "").is_err());
    journal
        .acknowledge_unknown(
            1,
            "process stopped before result persistence; retry will cost another call",
        )
        .unwrap();
    assert_eq!(journal.stats().unwrap().unknown, 1);
    assert_eq!(journal.stats().unwrap().abandoned, 1);
    let adapter = JournaledAdapter::new(
        Fake(Arc::new(AtomicUsize::new(0))),
        journal.clone(),
        CallPurpose::Execution,
    );
    adapter.run(&q).unwrap();
    journal
        .save_checkpoint("search", &serde_json::json!({"next":2}))
        .unwrap();
    assert_eq!(journal.stats().unwrap().consumed, 2);
    assert_eq!(journal.stats().unwrap().completed, 1);
    drop(adapter);
    drop(journal);
    let resumed = CallJournal::open(&path, "case", "frozen", 3).unwrap();
    assert_eq!(resumed.stats().unwrap().abandoned, 1);
    assert!(resumed.checkpoint("search").unwrap().is_some());
}
