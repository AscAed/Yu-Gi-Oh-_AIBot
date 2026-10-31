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

fn revision_path(root: &std::path::Path, id: &str, revision: u64) -> PathBuf {
    root.join("jobs")
        .join(id)
        .join("revisions")
        .join(format!("{revision}.json"))
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
