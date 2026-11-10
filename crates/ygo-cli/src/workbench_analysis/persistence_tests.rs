use super::jobs::*;
use super::persistence::*;
use super::tests::{fixtures, spec};
use super::*;
use std::path::PathBuf;
use ygo_search::combo::{ScoringConfig, SearchReport, SearchStats};

fn root() -> PathBuf {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1b3-persistence-tests")
        .join(ygo_storage::secure_random_hex(16).unwrap());
    std::fs::create_dir_all(&root).unwrap();
    root
}

#[test]
fn killed_store_process_reopens_queued_as_interrupted_and_running_as_unknown() {
    const CHILD_ROOT: &str = "YGO_PERSISTENCE_CRASH_CHILD_ROOT";
    if let Some(root) = std::env::var_os(CHILD_ROOT) {
        let root = PathBuf::from(root);
        let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
        let queued_id = "11111111111111111111111111111111";
        let queued_record = queued(queued_id.into());
        store.append_initial(queued_record).unwrap();

        let running_id = "22222222222222222222222222222222";
        let running_queued = queued(running_id.into());
        store.append_initial(running_queued.clone()).unwrap();
        let running = running_queued
            .transition(1, AnalysisJobEvent::Start, 101)
            .unwrap();
        store.append_expected(running_id, 1, running).unwrap();

        let ready = root.with_extension("child-ready.json");
        std::fs::write(
            ready,
            serde_json::json!({"queued_id": queued_id, "running_id": running_id}).to_string(),
        )
        .unwrap();
        loop {
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
    }

    let root = root();
    let ready = root.with_extension("child-ready.json");
    let executable = std::env::current_exe().unwrap();
    let mut child = std::process::Command::new(executable)
        .arg("--exact")
        .arg("workbench_analysis::persistence_tests::killed_store_process_reopens_queued_as_interrupted_and_running_as_unknown")
        .env(CHILD_ROOT, &root)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .unwrap();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs(10);
    while !ready.is_file() && std::time::Instant::now() < deadline {
        if child.try_wait().unwrap().is_some() {
            panic!("persistence child exited before writing its ready marker");
        }
        std::thread::sleep(std::time::Duration::from_millis(10));
    }
    if !ready.is_file() {
        let _ = child.kill();
        let _ = child.wait();
        panic!("persistence child did not reach the committed state");
    }
    let marker: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&ready).unwrap()).unwrap();
    child.kill().unwrap();
    child.wait().unwrap();

    let store = PersistentAnalysisJobStore::open(root).unwrap();
    let queued = store
        .history(marker["queued_id"].as_str().unwrap())
        .unwrap();
    assert_eq!(
        queued.last().unwrap().state(),
        AnalysisJobState::Interrupted
    );
    let running = store
        .history(marker["running_id"].as_str().unwrap())
        .unwrap();
    assert_eq!(running.len(), 3);
    assert_eq!(running[1].state(), AnalysisJobState::Running);
    assert_eq!(running[2].state(), AnalysisJobState::Unknown);
}

fn frozen() -> FrozenAnalysisInput {
    let fixture_root = root().join("fixtures");
    std::fs::create_dir_all(&fixture_root).unwrap();
    let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&fixture_root);
    std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
    let saved = drafts.create(draft.clone()).unwrap();
    freeze_analysis_input(
        &drafts,
        spec(saved.id, saved.revision, banlist, draft.main[..5].to_vec()),
        engine,
        &snapshots,
        &catalog,
    )
    .unwrap()
}

fn queued(id: String) -> AnalysisJobRecordV1 {
    AnalysisJobRecordV1::new(id, &frozen(), ScoringConfig::default(), 100).unwrap()
}

fn report_bytes(frozen: &FrozenAnalysisInput, scoring: ScoringConfig) -> Vec<u8> {
    serde_json::to_vec(&ygo_api::combo::AnalysisReport {
        schema_version: 2,
        request: frozen.request.clone(),
        runtime_request: frozen.runtime_request.clone(),
        search: SearchReport {
            termination: "exhausted".into(),
            lines: Vec::new(),
            stats: SearchStats::default(),
            diagnostics: Vec::new(),
            scoring,
            budget: frozen.request.search.clone(),
        },
        card_names: Default::default(),
    })
    .unwrap()
}

#[test]
fn uncertain_execution_is_durably_unknown_and_stops_dispatch() {
    let root = root();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();

    let unknown = coordinator.mark_unknown(&ticket, 102).unwrap();

    assert_eq!(unknown.job_id(), queued.job_id());
    assert_eq!(unknown.state(), AnalysisJobState::Unknown);
    assert_eq!(unknown.revision(), 3);
    assert_eq!(
        unknown.error_code(),
        Some(AnalysisJobFailure::CompletionUncertain)
    );
    assert!(unknown.report().is_none());
    assert!(coordinator.is_stopped().unwrap());
    drop(coordinator);

    let reopened = super::durable::DurableAnalysisCoordinator::open(root).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.last().unwrap().state(), AnalysisJobState::Unknown);
    assert!(reopened.claim_next(103).unwrap().is_none());
}

fn revision_path(root: &std::path::Path, id: &str, revision: u64) -> PathBuf {
    root.join("jobs")
        .join(id)
        .join("revisions")
        .join(format!("{revision}.json"))
}

#[test]
fn scan_waits_for_initial_job_revision_publication() {
    let root = root();
    let store = std::sync::Arc::new(PersistentAnalysisJobStore::open(root).unwrap());
    let record = queued(ygo_storage::secure_random_hex(16).unwrap());
    let entered = std::sync::Arc::new(std::sync::Barrier::new(2));
    let release = std::sync::Arc::new(std::sync::Barrier::new(2));
    store.pause_initial_publish_for_test(entered.clone(), release.clone());

    let publisher_store = store.clone();
    let publisher = std::thread::spawn(move || publisher_store.append_initial(record));
    entered.wait();

    let inspector_store = store.clone();
    let (started_tx, started_rx) = std::sync::mpsc::channel();
    let (done_tx, done_rx) = std::sync::mpsc::channel();
    let inspector = std::thread::spawn(move || {
        started_tx.send(()).unwrap();
        done_tx.send(inspector_store.scan()).unwrap();
    });
    started_rx.recv().unwrap();
    let early_result = done_rx
        .recv_timeout(std::time::Duration::from_millis(50))
        .ok();
    let scan_waited = early_result.is_none();

    release.wait();
    publisher.join().unwrap().unwrap();
    let scan = early_result
        .unwrap_or_else(|| {
            done_rx
                .recv_timeout(std::time::Duration::from_secs(2))
                .unwrap()
        })
        .unwrap();
    inspector.join().unwrap();
    assert!(scan_waited);
    assert_eq!(scan.len(), 1);
    assert_eq!(scan.values().next().unwrap().len(), 1);
}

#[test]
fn append_valid_revisions_and_classify_unfinished_jobs_on_reopen() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let initial = queued(id.clone());
    store.append_initial(initial.clone()).unwrap();
    let running = initial.transition(1, AnalysisJobEvent::Start, 101).unwrap();
    store.append_expected(&id, 1, running.clone()).unwrap();
    assert_eq!(
        store.history(&id).unwrap().last().unwrap().state(),
        AnalysisJobState::Running
    );
    drop(store);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let history = reopened.history(&id).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history[0].state(), AnalysisJobState::Queued);
    assert_eq!(history[1].state(), AnalysisJobState::Running);
    assert_eq!(history[2].state(), AnalysisJobState::Unknown);
    assert_eq!(history[2].revision(), 3);
    assert_eq!(
        history[2].error_code(),
        Some(AnalysisJobFailure::CompletionUncertain)
    );
    let bytes = std::fs::read(revision_path(&root, &id, 3)).unwrap();
    let text = String::from_utf8(bytes).unwrap();
    assert!(!text.contains("worker_path"));
    assert!(!text.contains("runtime_request"));
}

#[test]
fn queued_jobs_are_interrupted_without_being_requeued_on_restart() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    store.append_initial(queued(id.clone())).unwrap();
    drop(store);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let history = reopened.history(&id).unwrap();
    assert_eq!(history.len(), 2);
    assert_eq!(history[1].state(), AnalysisJobState::Interrupted);
    assert_eq!(
        history[1].error_code(),
        Some(AnalysisJobFailure::ServiceRestarted)
    );
    assert_eq!(reopened.history(&id).unwrap().len(), 2);
}

#[test]
fn stale_or_invalid_appends_leave_the_committed_chain_unchanged() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let initial = queued(id.clone());
    store.append_initial(initial.clone()).unwrap();
    let committed = std::fs::read(revision_path(&root, &id, 1)).unwrap();
    let cancelled = initial
        .transition(1, AnalysisJobEvent::Cancel, 101)
        .unwrap();
    assert!(store.append_expected(&id, 0, cancelled.clone()).is_err());
    assert!(store.append_expected(&id, 1, initial.clone()).is_err());
    assert_eq!(store.history(&id).unwrap().len(), 1);
    assert_eq!(
        std::fs::read(revision_path(&root, &id, 1)).unwrap(),
        committed
    );
    assert_eq!(
        store.history(&id).unwrap()[0].encode_json().unwrap(),
        initial.encode_json().unwrap()
    );
}

#[test]
fn store_rejects_second_writer_and_does_not_treat_lock_file_presence_as_busy() {
    let root = root();
    let first = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    assert_eq!(
        PersistentAnalysisJobStore::open(root.clone())
            .unwrap_err()
            .code(),
        "job_store_locked"
    );
    drop(first);
    let reopened = PersistentAnalysisJobStore::open(root).unwrap();
    drop(reopened);
}

#[test]
fn open_rejects_duplicate_envelope_keys_and_broken_revision_chains() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    store.append_initial(queued(id.clone())).unwrap();
    drop(store);

    let path = revision_path(&root, &id, 1);
    let original = std::fs::read_to_string(&path).unwrap();
    let duplicate = original.replacen(
        "\"kind\": \"workbench_analysis_job_revision\"",
        "\"kind\": \"workbench_analysis_job_revision\",\"kind\": \"other\"",
        1,
    );
    std::fs::write(&path, duplicate).unwrap();
    assert_eq!(
        PersistentAnalysisJobStore::open(root.clone())
            .unwrap_err()
            .code(),
        "job_store_chain_invalid"
    );
    std::fs::write(&path, original).unwrap();
    let mut broken = std::fs::read(&path).unwrap();
    broken[0] = b'!';
    std::fs::write(&path, broken).unwrap();
    assert_eq!(
        PersistentAnalysisJobStore::open(root).unwrap_err().code(),
        "job_store_chain_invalid"
    );
}

#[test]
fn report_persistence_checks_strict_json_binding_and_saved_bytes() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let frozen = frozen();
    let scoring = ScoringConfig::default();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let initial = AnalysisJobRecordV1::new(id.clone(), &frozen, scoring.clone(), 100).unwrap();
    store.append_initial(initial.clone()).unwrap();
    let running = initial.transition(1, AnalysisJobEvent::Start, 101).unwrap();
    store.append_expected(&id, 1, running.clone()).unwrap();

    let bytes = report_bytes(&frozen, scoring.clone());
    let reference = store.persist_report(&running, &frozen, &bytes).unwrap();
    assert_eq!(reference.sha256, ygo_storage::hash(&bytes));
    let report = store
        .read_verified_report(&running, &reference, &frozen)
        .unwrap();
    assert_eq!(report.search.termination, "exhausted");
    assert_eq!(report.search.lines.len(), 0);

    let mut changed_frozen = frozen.clone();
    changed_frozen.request.seed += 1;
    assert_eq!(
        store
            .read_verified_report(&running, &reference, &changed_frozen)
            .unwrap_err(),
        PersistenceError::ReportBindingMismatch
    );

    let path = root
        .join("reports")
        .join(format!("{}.json", reference.report_id));
    let mut corrupt = bytes;
    corrupt.push(b' ');
    std::fs::write(path, corrupt).unwrap();
    assert_eq!(
        store
            .read_verified_report(&running, &reference, &frozen)
            .unwrap_err(),
        PersistenceError::ReportInvalid
    );
}

#[test]
fn report_persistence_rejects_duplicate_keys_and_contract_drift_before_writing() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let frozen = frozen();
    let scoring = ScoringConfig::default();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let initial = AnalysisJobRecordV1::new(id.clone(), &frozen, scoring.clone(), 100).unwrap();
    store.append_initial(initial.clone()).unwrap();
    let running = initial.transition(1, AnalysisJobEvent::Start, 101).unwrap();
    store.append_expected(&id, 1, running.clone()).unwrap();

    let valid = report_bytes(&frozen, scoring.clone());
    let duplicate = String::from_utf8(valid.clone()).unwrap().replacen(
        "\"schema_version\":2",
        "\"schema_version\":2,\"schema_version\":2",
        1,
    );
    assert_eq!(
        store
            .persist_report(&running, &frozen, duplicate.as_bytes())
            .unwrap_err(),
        PersistenceError::ReportInvalid
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 0);

    let invalid_scoring = report_bytes(
        &frozen,
        ScoringConfig {
            complexity: 0.0,
            ..scoring
        },
    );
    assert_eq!(
        store
            .persist_report(&running, &frozen, &invalid_scoring)
            .unwrap_err(),
        PersistenceError::ReportBindingMismatch
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 0);
}

#[test]
fn reopening_rejects_terminal_records_with_missing_or_tampered_reports() {
    let root = root();
    let id = ygo_storage::secure_random_hex(16).unwrap();
    let frozen = frozen();
    let scoring = ScoringConfig::default();
    let store = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let initial = AnalysisJobRecordV1::new(id.clone(), &frozen, scoring.clone(), 100).unwrap();
    store.append_initial(initial.clone()).unwrap();
    let running = initial.transition(1, AnalysisJobEvent::Start, 101).unwrap();
    store.append_expected(&id, 1, running.clone()).unwrap();
    let bytes = report_bytes(&frozen, scoring);
    let reference = store.persist_report(&running, &frozen, &bytes).unwrap();
    let completed = running
        .transition(2, AnalysisJobEvent::ReportPublished(reference.clone()), 102)
        .unwrap();
    store.append_expected(&id, 2, completed).unwrap();
    drop(store);

    let report_path = root
        .join("reports")
        .join(format!("{}.json", reference.report_id));
    std::fs::remove_file(&report_path).unwrap();
    assert_eq!(
        PersistentAnalysisJobStore::open(root.clone())
            .unwrap_err()
            .code(),
        "job_report_invalid"
    );
    std::fs::write(&report_path, &bytes).unwrap();
    let mut tampered = bytes;
    tampered.push(b' ');
    std::fs::write(&report_path, tampered).unwrap();
    assert_eq!(
        PersistentAnalysisJobStore::open(root).unwrap_err().code(),
        "job_report_invalid"
    );
}

#[test]
fn durable_coordinator_persists_queue_transitions_before_returning_them() {
    let root = root();
    let input = frozen();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    assert_eq!(queued.state(), AnalysisJobState::Queued);
    assert_eq!(coordinator.history(queued.job_id()).unwrap().len(), 1);

    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    assert_eq!(ticket.record().state(), AnalysisJobState::Running);
    let history = coordinator.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 2);
    assert_eq!(history[1].state(), AnalysisJobState::Running);
    assert_eq!(
        coordinator.snapshot().unwrap().running.unwrap().state(),
        AnalysisJobState::Running
    );

    let cancelled = coordinator.cancel(queued.job_id(), 1, 102).unwrap_err();
    assert_eq!(cancelled.code(), "cannot_cancel_running");
    let failed = coordinator.fail(&ticket, 103).unwrap();
    assert_eq!(failed.state(), AnalysisJobState::Failed);
    assert_eq!(
        coordinator
            .history(queued.job_id())
            .unwrap()
            .last()
            .unwrap()
            .state(),
        AnalysisJobState::Failed
    );
}

#[test]
fn durable_coordinator_publishes_report_before_terminal_revision() {
    let root = root();
    let input = frozen();
    let bytes = report_bytes(&input, ScoringConfig::default());
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    let (completed, report) = coordinator.publish_report(&ticket, &bytes, 102).unwrap();
    assert_eq!(completed.state(), AnalysisJobState::Completed);
    assert_eq!(
        completed.report().unwrap().termination,
        "exhausted:no_verified_lines"
    );
    assert_eq!(report.search.termination, "exhausted");
    assert_eq!(
        coordinator
            .history(queued.job_id())
            .unwrap()
            .last()
            .unwrap()
            .state(),
        AnalysisJobState::Completed
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
    assert_eq!(
        coordinator
            .publish_report(&ticket, &bytes, 103)
            .unwrap_err()
            .code(),
        "analysis_ticket_mismatch"
    );
    assert_eq!(coordinator.history(queued.job_id()).unwrap().len(), 3);
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root).unwrap();
    assert_eq!(
        reopened
            .history(queued.job_id())
            .unwrap()
            .last()
            .unwrap()
            .state(),
        AnalysisJobState::Completed
    );
}

#[test]
fn uncertain_report_terminal_publish_stops_coordinator_and_reopens_completed() {
    let root = root();
    let input = frozen();
    let bytes = report_bytes(&input, ScoringConfig::default());
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    coordinator.inject_uncertain_after_next_publish();

    let error = coordinator
        .publish_report(&ticket, &bytes, 102)
        .unwrap_err();
    assert_eq!(error.code(), "job_store_commit_uncertain");
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history.last().unwrap().state(), AnalysisJobState::Completed);
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
}

#[test]
fn uncertain_cancel_and_failure_settlements_stop_and_reopen_committed_terminals() {
    let cancel_root = root();
    let canceller = super::durable::DurableAnalysisCoordinator::open(cancel_root.clone()).unwrap();
    let queued = canceller
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    canceller.inject_uncertain_after_next_publish();
    assert_eq!(
        canceller
            .cancel(queued.job_id(), queued.revision(), 101)
            .unwrap_err()
            .code(),
        "job_store_commit_uncertain"
    );
    assert_eq!(
        canceller.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(canceller);
    let reopened = PersistentAnalysisJobStore::open(cancel_root).unwrap();
    assert_eq!(
        reopened
            .history(queued.job_id())
            .unwrap()
            .last()
            .unwrap()
            .state(),
        AnalysisJobState::Cancelled
    );

    let fail_root = root();
    let failing = super::durable::DurableAnalysisCoordinator::open(fail_root.clone()).unwrap();
    let queued = failing
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    let ticket = failing.claim_next(101).unwrap().unwrap();
    failing.inject_uncertain_after_next_publish();
    assert_eq!(
        failing.fail(&ticket, 102).unwrap_err().code(),
        "job_store_commit_uncertain"
    );
    assert_eq!(
        failing.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(failing);
    let reopened = PersistentAnalysisJobStore::open(fail_root).unwrap();
    assert_eq!(
        reopened
            .history(queued.job_id())
            .unwrap()
            .last()
            .unwrap()
            .state(),
        AnalysisJobState::Failed
    );
}

#[test]
fn uncertain_submit_stops_and_reopens_the_committed_job_interrupted() {
    let root = root();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    coordinator.inject_uncertain_after_next_publish();

    assert_eq!(
        coordinator
            .submit(frozen(), ScoringConfig::default(), 100)
            .unwrap_err()
            .code(),
        "job_store_commit_uncertain"
    );
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let job_dirs: Vec<_> = std::fs::read_dir(root.join("jobs"))
        .unwrap()
        .map(Result::unwrap)
        .collect();
    assert_eq!(job_dirs.len(), 1);
    let id = job_dirs[0].file_name().to_string_lossy().into_owned();
    let history = reopened.history(&id).unwrap();
    assert_eq!(history.len(), 2);
    assert_eq!(history[0].state(), AnalysisJobState::Queued);
    assert_eq!(history[1].state(), AnalysisJobState::Interrupted);
}

#[test]
fn report_publish_failure_before_file_creation_keeps_running_retryable() {
    let root = root();
    let input = frozen();
    let bytes = report_bytes(&input, ScoringConfig::default());
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    coordinator.inject_report_publish_failure(false);

    assert_eq!(
        coordinator
            .publish_report(&ticket, &bytes, 102)
            .unwrap_err()
            .code(),
        "job_store_io_failed"
    );
    assert_eq!(
        coordinator.snapshot().unwrap().running.unwrap().job_id(),
        queued.job_id()
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 0);

    let completed = coordinator.publish_report(&ticket, &bytes, 103).unwrap().0;
    assert_eq!(completed.state(), AnalysisJobState::Completed);
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
}

#[test]
fn uncertain_report_file_publish_stops_coordinator_and_reopens_as_unknown() {
    let root = root();
    let input = frozen();
    let bytes = report_bytes(&input, ScoringConfig::default());
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    coordinator.inject_report_publish_failure(true);

    assert_eq!(
        coordinator
            .publish_report(&ticket, &bytes, 102)
            .unwrap_err()
            .code(),
        "job_store_commit_uncertain"
    );
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history.last().unwrap().state(), AnalysisJobState::Unknown);
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
}

#[test]
fn failed_report_terminal_publish_stops_coordinator_and_reopens_as_unknown() {
    let root = root();
    let input = frozen();
    let bytes = report_bytes(&input, ScoringConfig::default());
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    let ticket = coordinator.claim_next(101).unwrap().unwrap();
    coordinator.inject_failure_before_next_publish();

    let error = coordinator
        .publish_report(&ticket, &bytes, 102)
        .unwrap_err();
    assert_eq!(error.code(), "job_store_io_failed");
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root.clone()).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.last().unwrap().state(), AnalysisJobState::Unknown);
    assert_eq!(history.len(), 3);
    assert_eq!(std::fs::read_dir(root.join("reports")).unwrap().count(), 1);
}

#[test]
fn uncertain_persistent_claim_stops_coordinator_and_reopens_as_unknown() {
    let root = root();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    coordinator.inject_uncertain_after_next_publish();

    let error = coordinator.claim_next(101).unwrap_err();
    assert_eq!(error.code(), "job_store_commit_uncertain");
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history[0].state(), AnalysisJobState::Queued);
    assert_eq!(history[1].state(), AnalysisJobState::Running);
    assert_eq!(history[2].state(), AnalysisJobState::Unknown);
}

#[test]
fn prepublication_failure_keeps_queued_memory_and_disk_state_retryable() {
    let root = root();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root).unwrap();
    let queued = coordinator
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    coordinator.inject_failure_before_next_publish();

    let error = coordinator.claim_next(101).unwrap_err();
    assert_eq!(error.code(), "job_store_io_failed");
    let snapshot = coordinator.snapshot().unwrap();
    assert_eq!(snapshot.queued.unwrap().job_id(), queued.job_id());
    assert!(snapshot.running.is_none());

    let ticket = coordinator.claim_next(102).unwrap().unwrap();
    assert_eq!(ticket.record().state(), AnalysisJobState::Running);
}

#[test]
fn prepublication_failures_leave_submit_cancel_and_fail_states_unchanged() {
    let submit_root = root();
    let submitter = super::durable::DurableAnalysisCoordinator::open(submit_root.clone()).unwrap();
    submitter.inject_failure_before_next_publish();
    assert_eq!(
        submitter
            .submit(frozen(), ScoringConfig::default(), 100)
            .unwrap_err()
            .code(),
        "job_store_io_failed"
    );
    assert!(submitter.snapshot().unwrap().queued.is_none());
    assert_eq!(
        std::fs::read_dir(submit_root.join("jobs")).unwrap().count(),
        0
    );
    let submitted = submitter
        .submit(frozen(), ScoringConfig::default(), 101)
        .unwrap();

    let cancel_root = root();
    let canceller = super::durable::DurableAnalysisCoordinator::open(cancel_root.clone()).unwrap();
    let queued = canceller
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    canceller.inject_failure_before_next_publish();
    assert_eq!(
        canceller
            .cancel(queued.job_id(), queued.revision(), 101)
            .unwrap_err()
            .code(),
        "job_store_io_failed"
    );
    assert_eq!(
        canceller.snapshot().unwrap().queued.unwrap().state(),
        AnalysisJobState::Queued
    );
    assert_eq!(canceller.history(queued.job_id()).unwrap().len(), 1);
    assert_eq!(
        canceller
            .cancel(queued.job_id(), queued.revision(), 102)
            .unwrap()
            .state(),
        AnalysisJobState::Cancelled
    );

    let fail_root = root();
    let failing = super::durable::DurableAnalysisCoordinator::open(fail_root).unwrap();
    let queued = failing
        .submit(frozen(), ScoringConfig::default(), 100)
        .unwrap();
    let ticket = failing.claim_next(101).unwrap().unwrap();
    failing.inject_failure_before_next_publish();
    assert_eq!(
        failing.fail(&ticket, 102).unwrap_err().code(),
        "job_store_io_failed"
    );
    assert_eq!(
        failing.snapshot().unwrap().running.unwrap().state(),
        AnalysisJobState::Running
    );
    assert_eq!(failing.history(queued.job_id()).unwrap().len(), 2);
    assert_eq!(
        failing.fail(&ticket, 103).unwrap().state(),
        AnalysisJobState::Failed
    );
    assert_eq!(failing.history(queued.job_id()).unwrap().len(), 3);
    assert_eq!(submitter.history(submitted.job_id()).unwrap().len(), 1);
}

#[test]
fn durable_claim_rejects_assets_changed_after_input_freeze() {
    let root = root();
    let input = frozen();
    let engine_path = input.runtime_request.engine.ocgcore_path.clone();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    std::fs::write(engine_path, b"changed after freeze").unwrap();

    let error = coordinator.claim_next(101).unwrap_err();
    assert_eq!(error.code(), "analysis_asset_mismatch");
    let history = coordinator.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history[1].state(), AnalysisJobState::Running);
    assert_eq!(history[2].state(), AnalysisJobState::Failed);
    assert_eq!(
        serde_json::to_value(history[2].error_code()).unwrap(),
        serde_json::json!("asset_mismatch")
    );
    assert!(coordinator.snapshot().unwrap().running.is_none());
}

#[test]
fn durable_claim_rejects_drift_in_each_asset_role_and_runtime_path() {
    for drift in 0..7 {
        let root = root();
        let mut input = frozen();
        let engine = &input.runtime_request.engine;
        let role_paths = [
            engine.worker_path.clone(),
            engine.ocgcore_path.clone(),
            engine.catalog_path.clone(),
            engine.script_manifest_path.clone(),
            engine.engine_manifest_path.clone(),
        ];
        if drift < role_paths.len() {
            std::fs::write(&role_paths[drift], b"changed after freeze").unwrap();
        } else if drift == role_paths.len() {
            std::fs::write(engine.scripts_path.join("unexpected.lua"), b"changed").unwrap();
        } else {
            let replacement = input
                .runtime_request
                .engine
                .ocgcore_path
                .with_file_name("replacement-core.bin");
            std::fs::write(&replacement, b"different core at replacement path").unwrap();
            input.runtime_request.engine.ocgcore_path = replacement;
        }

        let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
        let queued = coordinator
            .submit(input, ScoringConfig::default(), 100)
            .unwrap();
        assert_eq!(
            coordinator.claim_next(101).unwrap_err().code(),
            "analysis_asset_mismatch",
            "asset drift case {drift} must be rejected before dispatch"
        );
        let history = coordinator.history(queued.job_id()).unwrap();
        assert_eq!(history.len(), 3);
        assert_eq!(history[2].state(), AnalysisJobState::Failed);
        assert_eq!(
            history[2].error_code(),
            Some(AnalysisJobFailure::AssetMismatch)
        );
    }
}

#[test]
fn failed_asset_mismatch_settlement_stops_coordinator_after_running_commit() {
    let root = root();
    let input = frozen();
    let engine_path = input.runtime_request.engine.ocgcore_path.clone();
    let coordinator = super::durable::DurableAnalysisCoordinator::open(root.clone()).unwrap();
    let queued = coordinator
        .submit(input, ScoringConfig::default(), 100)
        .unwrap();
    std::fs::write(engine_path, b"changed after freeze").unwrap();
    coordinator.inject_failure_before_publish_after(1);

    let error = coordinator.claim_next(101).unwrap_err();
    assert_eq!(error.code(), "job_store_io_failed");
    assert_eq!(
        coordinator.snapshot().unwrap_err().code(),
        "job_coordinator_stopped"
    );
    drop(coordinator);

    let reopened = PersistentAnalysisJobStore::open(root).unwrap();
    let history = reopened.history(queued.job_id()).unwrap();
    assert_eq!(history.len(), 3);
    assert_eq!(history[1].state(), AnalysisJobState::Running);
    assert_eq!(history[2].state(), AnalysisJobState::Unknown);
}
