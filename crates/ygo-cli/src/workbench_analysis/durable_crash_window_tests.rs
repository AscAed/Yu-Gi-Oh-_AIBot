use std::{
    collections::BTreeMap,
    fs,
    path::Path,
    process::{Child, Command, ExitStatus, Stdio},
    time::{Duration, Instant},
};
use ygo_search::combo::{SearchReport, SearchStats};
use crate::workbench_analysis::jobs::AnalysisJobState;

const CRASH_TEST: &str =
    "workbench_analysis::durable::operation_tests::h3_2b_cross_chain_windows_recover_after_process_kill";
const CHILD_STAGE: &str = "YGO_H3_CRASH_CHECKPOINT";
const CHILD_ROOT: &str = "YGO_H3_CRASH_ROOT";
const CHILD_MARKER: &str = "YGO_H3_CRASH_MARKER";
const CHILD_EVENTS: &str = "YGO_H3_CRASH_EVENTS";

struct ChildGuard(Child);

impl ChildGuard {
    fn kill(&mut self) -> ExitStatus {
        self.0.kill().expect("terminate checkpointed child");
        self.0.wait().expect("reap terminated child")
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if self.0.try_wait().ok().flatten().is_none() {
            let _ = self.0.kill();
            let _ = self.0.wait();
        }
    }
}

fn operation_dirs(store: &Path) -> Vec<String> {
    let mut ids = fs::read_dir(store.join("operations"))
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    ids.sort();
    ids
}

fn read_record(store: &Path, chain: &str, id: &str, revision: u64) -> serde_json::Value {
    let bytes = fs::read(
        store
            .join(chain)
            .join(id)
            .join("revisions")
            .join(format!("{revision}.json")),
    )
    .unwrap();
    serde_json::from_slice::<serde_json::Value>(&bytes).unwrap()["record"].clone()
}

fn authenticate_partial_recovery_pair(store: &Path, op_id: &str, job_id: &str, classified: bool, running: bool) {
    let mut operations: Vec<Operation> = Vec::new();
    let mut previous = None;
    let revisions = store.join("operations").join(op_id).join("revisions");
    assert_eq!(fs::read_dir(&revisions).unwrap().count(), 4);
    for revision in 1..=4 {
        let bytes = fs::read(revisions.join(format!("{revision}.json"))).unwrap();
        let envelope: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(envelope["schema_version"], 1);
        assert_eq!(envelope["kind"], "workbench_analysis_operation_revision");
        assert_eq!(envelope["operation_id"], op_id);
        assert_eq!(envelope["revision"], revision);
        assert_eq!(envelope["previous_sha256"].as_str().map(str::to_owned), previous);
        let record = Operation::read_json(&serde_json::to_vec(&envelope["record"]).unwrap()).unwrap();
        assert_eq!(envelope["record_sha256"].as_str(), Some(ygo_storage::hash(&record.encode_json().unwrap()).as_str()));
        assert_eq!(record.operation_id(), op_id);
        assert_eq!(record.revision(), revision);
        if revision == 2 {
            let expected = operations[0].begin(record.command().unwrap().clone(), job_id.to_owned(), record.updated_at_ms()).unwrap();
            assert_eq!(expected.encode_json().unwrap(), record.encode_json().unwrap());
        } else if revision == 3 {
            let expected = operations[1].bind_input(record.frozen_input().unwrap().clone(), record.updated_at_ms()).unwrap();
            assert_eq!(expected.encode_json().unwrap(), record.encode_json().unwrap());
        } else if revision == 4 {
            let expected = operations[2].accept(record.updated_at_ms()).unwrap();
            assert_eq!(expected.encode_json().unwrap(), record.encode_json().unwrap());
        } else { assert_eq!(record.state(), AnalysisOperationState::Allocated); }
        previous = Some(ygo_storage::hash(&bytes));
        operations.push(record);
    }
    let revisions = store.join("jobs").join(job_id).join("revisions");
    let count = 1 + usize::from(running) + usize::from(classified);
    assert_eq!(fs::read_dir(&revisions).unwrap().count(), count);
    let mut jobs: Vec<AnalysisJobRecordV1> = Vec::new();
    let mut previous = None;
    for revision in 1..=count as u64 {
        let bytes = fs::read(revisions.join(format!("{revision}.json"))).unwrap();
        let envelope: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(envelope["schema_version"], 1);
        assert_eq!(envelope["kind"], "workbench_analysis_job_revision");
        assert_eq!(envelope["job_id"], job_id);
        assert_eq!(envelope["revision"], revision);
        assert_eq!(envelope["previous_sha256"].as_str().map(str::to_owned), previous);
        let record = AnalysisJobRecordV1::read_json(&serde_json::to_vec(&envelope["record"]).unwrap()).unwrap();
        assert_eq!(record.job_id(), job_id);
        assert_eq!(record.revision(), revision);
        assert_eq!(envelope["record_sha256"].as_str(), Some(ygo_storage::hash(&record.encode_json().unwrap()).as_str()));
        if revision == 1 { assert_eq!(record.state(), AnalysisJobState::Queued); }
        else {
            let expected = jobs[(revision - 2) as usize].transition(revision - 1, if running && revision == 2 { AnalysisJobEvent::Start } else { AnalysisJobEvent::ClassifyRestart }, record.updated_at_ms()).unwrap();
            assert_eq!(expected.encode_json().unwrap(), record.encode_json().unwrap());
        }
        previous = Some(ygo_storage::hash(&bytes));
        jobs.push(record);
    }
    assert_eq!(serde_json::to_value(operations[3].frozen_input().unwrap()).unwrap(), serde_json::to_value(jobs[0].input()).unwrap());
}

fn authenticate_operation_chain(store: &Path, id: &str) -> Vec<Operation> {
    let revisions = store.join("operations").join(id).join("revisions");
    let mut names = fs::read_dir(&revisions)
        .unwrap()
        .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
        .collect::<Vec<_>>();
    names.sort();
    assert!(
        names == ["1.json", "2.json"]
            || names == ["1.json", "2.json", "3.json"]
            || names == ["1.json", "2.json", "3.json", "4.json"]
    );

    let mut previous_sha256 = None;
    let mut history: Vec<Operation> = Vec::new();
    for revision in 1..=names.len() as u64 {
        let raw = fs::read(revisions.join(format!("{revision}.json"))).unwrap();
        let envelope: serde_json::Value = serde_json::from_slice(&raw).unwrap();
        assert_eq!(envelope["schema_version"], 1);
        assert_eq!(envelope["kind"], "workbench_analysis_operation_revision");
        assert_eq!(envelope["operation_id"], id);
        assert_eq!(envelope["revision"], revision);
        assert_eq!(
            envelope["previous_sha256"].as_str().map(str::to_owned),
            previous_sha256
        );

        let record_bytes = serde_json::to_vec(&envelope["record"]).unwrap();
        let record = Operation::read_json(&record_bytes).unwrap();
        assert_eq!(record.operation_id(), id);
        assert_eq!(record.revision(), revision);
        assert_eq!(
            envelope["record_sha256"].as_str(),
            Some(ygo_storage::hash(&record.encode_json().unwrap()).as_str())
        );
        if revision == 1 {
            assert_eq!(record.state(), AnalysisOperationState::Allocated);
        } else {
            assert!(matches!(record.state(), AnalysisOperationState::Accepting | AnalysisOperationState::Accepted | AnalysisOperationState::Rejected | AnalysisOperationState::Unknown));
            let command = record.command().expect("accepting command");
            let command_bytes = serde_json::to_vec(&(
                "workbench-analysis-command-v1",
                &command.draft_id,
                &command.draft_revision,
                &command.opening_hand,
                command.seed,
                &command.rules,
                &command.catalog_id,
                &command.banlist_id,
                &command.as_of,
                &command.search,
                &record.context().scoring,
                &record.context().default_catalog_id,
            ))
            .unwrap();
            assert_eq!(
                record.command_sha256(),
                Some(ygo_storage::hash(&command_bytes).as_str())
            );
            let expected = match revision {
                2 if record.state() == AnalysisOperationState::Accepting => history[0]
                    .begin(
                        command.clone(),
                        record.job_id().expect("accepting job").to_owned(),
                        record.updated_at_ms(),
                    )
                    .unwrap(),
                2 => {
                    assert_eq!(record.state(), AnalysisOperationState::Rejected);
                    history[0]
                        .reject(
                            command.clone(),
                            409,
                            record.error_code().unwrap(),
                            record.updated_at_ms(),
                        )
                        .unwrap()
                }
                3 if record.state() == AnalysisOperationState::Accepting => history[1]
                    .bind_input(
                        record.frozen_input().expect("bound accepting input").clone(),
                        record.updated_at_ms(),
                    )
                    .unwrap(),
                3 if record.state() == AnalysisOperationState::Unknown => {
                    history[1].mark_unknown(record.updated_at_ms()).unwrap()
                }
                3 => {
                    assert_eq!(record.state(), AnalysisOperationState::Rejected);
                    history[1]
                        .reject(
                            command.clone(),
                            422,
                            record.error_code().unwrap(),
                            record.updated_at_ms(),
                        )
                        .unwrap()
                }
                4 => {
                    assert_eq!(record.state(), AnalysisOperationState::Accepted);
                    history[2].accept(record.updated_at_ms()).unwrap()
                }
                _ => unreachable!("operation revision must be covered by its state transition"),
            };
            assert_eq!(expected.encode_json().unwrap(), record.encode_json().unwrap());
        }
        previous_sha256 = Some(ygo_storage::hash(&raw));
        history.push(record);
    }
    history
}

fn authenticate_single_queued_job(store: &Path, id: &str) -> AnalysisJobRecordV1 {
    let raw = fs::read(store.join("jobs").join(id).join("revisions/1.json")).unwrap();
    let envelope: serde_json::Value = serde_json::from_slice(&raw).unwrap();
    assert_eq!(envelope["schema_version"], 1);
    assert_eq!(envelope["kind"], "workbench_analysis_job_revision");
    assert_eq!(envelope["job_id"], id);
    assert_eq!(envelope["revision"], 1);
    assert!(envelope["previous_sha256"].is_null());
    let record = AnalysisJobRecordV1::read_json(&serde_json::to_vec(&envelope["record"]).unwrap()).unwrap();
    assert_eq!(record.job_id(), id);
    assert_eq!(record.revision(), 1);
    assert_eq!(record.state(), AnalysisJobState::Queued);
    assert_eq!(
        envelope["record_sha256"].as_str(),
        Some(ygo_storage::hash(&record.encode_json().unwrap()).as_str())
    );
    record
}

fn assert_child_event_counts(root: &Path, freeze: usize, claim: usize) {
    let events = fs::read_to_string(root.join("child-events.log")).unwrap();
    assert_eq!(events.lines().filter(|line| *line == "freeze").count(), freeze);
    assert_eq!(events.lines().filter(|line| *line == "claim").count(), claim);
}

fn persisted_material(root: &Path) -> BTreeMap<String, Vec<u8>> {
    fn visit(base: &Path, current: &Path, files: &mut BTreeMap<String, Vec<u8>>) {
        for entry in fs::read_dir(current).unwrap() {
            let entry = entry.unwrap();
            let path = entry.path();
            if path.is_dir() {
                visit(base, &path, files);
            } else if entry.file_name() != ".ygo-analysis.lock" {
                files.insert(
                    path.strip_prefix(base).unwrap().to_string_lossy().into_owned(),
                    fs::read(path).unwrap(),
                );
            }
        }
    }
    let mut files = BTreeMap::new();
    visit(root, root, &mut files);
    files
}

fn wait_for_checkpoint(child: &mut ChildGuard, marker: &Path, expected: &str) {
    let deadline = Instant::now() + Duration::from_secs(20);
    while !marker.is_file() && Instant::now() < deadline {
        if let Some(status) = child.0.try_wait().expect("poll child process") {
            let output = fs::read_to_string(marker.with_file_name("child-output.log"))
                .unwrap_or_default();
            panic!("child exited before checkpoint {expected}: {status}; output: {output}");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    assert!(marker.is_file(), "child missed checkpoint {expected}");
    let reached = fs::read_to_string(marker).unwrap();
    assert_eq!(reached.trim(), expected);
}

fn spawn_checkpoint_child(root: &Path, stage: &str) -> (ChildGuard, std::path::PathBuf) {
    let marker = root.join("checkpoint.txt");
    let events = root.join("child-events.log");
    fs::write(&events, b"").unwrap();
    let child_output = fs::File::create(root.join("child-output.log")).unwrap();
    let mut child = ChildGuard(
        Command::new(std::env::current_exe().unwrap())
            .args(["--exact", CRASH_TEST, "--nocapture"])
            .env(CHILD_STAGE, stage)
            .env(CHILD_ROOT, root)
            .env(CHILD_MARKER, &marker)
            .env(CHILD_EVENTS, &events)
            .stdout(Stdio::from(child_output.try_clone().unwrap()))
            .stderr(Stdio::from(child_output))
            .spawn()
            .unwrap(),
    );
    wait_for_checkpoint(&mut child, &marker, stage);
    (child, marker)
}

fn child_submit_to_checkpoint(root: &Path, stage: &str) {
    let (drafts, snapshots, engine, context, command) = setup(root);
    let store = root.join("store");
    let coordinator = DurableAnalysisCoordinator::open_operations(store).unwrap();
    let operation = coordinator.allocate_operation(context.clone(), 100).unwrap();
    if stage == "preparation_rejected_persisted_before_return" {
        let _ = coordinator.submit_operation_core(operation.operation_id(), command, &context, 101, |_, _| Err(super::super::AnalysisFreezeError::OpeningHandInvalid));
        panic!("preparation rejection checkpoint did not stop the child");
    }
    if stage == "context_rejected_persisted_before_return" {
        let mut changed = context.clone();
        changed.configuration_sha256 = "f".repeat(64);
        assert_ne!(changed.configuration_sha256, context.configuration_sha256);
        let _ = coordinator.begin_operation(operation.operation_id(), command, &changed, 101);
        panic!("context rejection checkpoint did not stop the child");
    }
    if stage == "capacity_rejected_persisted_before_return" {
        let _ticket = coordinator.begin_operation(operation.operation_id(), command.clone(), &context, 101).unwrap().ticket.unwrap();
        let other = coordinator.allocate_operation(context.clone(), 102).unwrap();
        let _ = coordinator.begin_operation(other.operation_id(), command, &context, 103);
        panic!("capacity rejection checkpoint did not stop the child");
    }
    let engine_path = engine.ocgcore_path.clone();
    let accepted = coordinator
        .submit_operation(
            operation.operation_id(),
            command,
            &context,
            101,
            &drafts,
            &snapshots,
            engine,
        )
        .unwrap();
    assert_eq!(accepted.state(), AnalysisOperationState::Accepted);

    if stage == "failed_persisted_before_queue_update" {
        let ticket = coordinator.claim_next(102).unwrap().unwrap();
        let _ = coordinator.fail(&ticket, 103);
        panic!("failure checkpoint did not stop the child");
    }
    if stage == "asset_mismatch_persisted_before_queue_update" {
        fs::write(engine_path, b"changed after frozen acceptance").unwrap();
        let _ = coordinator.claim_next(102);
        panic!("asset mismatch checkpoint did not stop the child");
    }
    if stage == "running_persisted_before_queue_update"
        || stage == "running_queue_updated_before_ticket_return"
    {
        let _ = coordinator.claim_next(102);
        panic!("claim checkpoint did not stop the child");
    }
    if stage == "unknown_persisted_before_queue_update" {
        let ticket = coordinator.claim_next(102).unwrap().unwrap();
        coordinator.mark_unknown(&ticket, 103).unwrap();
        panic!("unknown checkpoint did not stop the child");
    }
    if stage == "cancelled_persisted_before_queue_update" {
        let _ = coordinator.cancel(accepted.job_id().unwrap(), 1, 102);
        panic!("cancel checkpoint did not stop the child");
    }
    if stage == "report_persisted_before_terminal" || stage == "completed_persisted_before_queue_update" || stage == "budget_persisted_before_queue_update" || stage == "time_budget_persisted_before_queue_update" {
        let ticket = coordinator.claim_next(102).unwrap().unwrap();
        let mut bytes = report_bytes(ticket.input(), ticket.record().input().scoring.clone());
        if stage == "budget_persisted_before_queue_update" || stage == "time_budget_persisted_before_queue_update" {
            let mut report: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
            report["search"]["termination"] = if stage == "time_budget_persisted_before_queue_update" { "time_budget" } else { "node_budget" }.into();
            bytes = serde_json::to_vec(&report).unwrap();
        }
        coordinator.publish_report(&ticket, &bytes, 103).unwrap();
        panic!("report checkpoint did not stop the child");
    }
    panic!("submission checkpoint did not stop the child for {stage}");
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

fn freeze_test_input(
    drafts: &ygo_storage::DeckDraftStore,
    snapshots: &ygo_storage::SnapshotStore,
    engine: ygo_engine_adapter::ProcessEngineConfig,
    context: &AnalysisOperationContext,
    command: &AnalysisOperationCommand,
) -> FrozenAnalysisInput {
    crate::workbench_analysis::freeze_analysis_input(
        drafts,
        crate::workbench_analysis::AnalysisFreezeSpec {
            draft_id: command.draft_id.clone(),
            expected_revision: command.draft_revision.clone(),
            opening_hand: command.opening_hand.clone(),
            seed: command.seed,
            rules: command.rules.clone(),
            catalog_id: command.catalog_id.clone(),
            banlist_id: command.banlist_id.clone(),
            as_of: command.as_of.clone(),
            search: command.search.clone(),
        },
        engine,
        snapshots,
        &context.default_catalog_id,
    )
    .unwrap()
}

#[test]
fn mismatched_cross_chain_binding_blocks_recovery_before_any_append() {
    let root = root();
    let (drafts_a, snapshots_a, engine_a, context_a, command_a) = setup(&root);
    let (drafts_b, snapshots_b, engine_b, context_b, command_b) = setup(&root.join("other"));
    let frozen_a = freeze_test_input(&drafts_a, &snapshots_a, engine_a, &context_a, &command_a);
    let frozen_b = freeze_test_input(&drafts_b, &snapshots_b, engine_b, &context_b, &command_b);
    let store_path = root.join("store");
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();
    let operation_id = "c".repeat(32);
    let job_id = "d".repeat(32);
    let allocated = Operation::allocate(operation_id.clone(), context_a.clone(), 100).unwrap();
    let begun = allocated.begin(command_a, job_id.clone(), 101).unwrap();
    let accepting = begun
        .bind_input(
            AnalysisJobRecordV1::new(
                job_id.clone(),
                &frozen_a,
                context_a.scoring.clone(),
                102,
            )
            .unwrap()
            .input()
            .clone(),
            102,
        )
        .unwrap();
    let mismatched_job = AnalysisJobRecordV1::new(job_id.clone(), &frozen_b, context_b.scoring, 102)
        .unwrap();
    store.append_operation(&allocated).unwrap();
    store.append_operation(&begun).unwrap();
    store.append_operation(&accepting).unwrap();
    store.append_initial(mismatched_job).unwrap();
    drop(store);

    let before = persisted_material(&store_path);
    assert!(matches!(
        DurableAnalysisCoordinator::open_operations(store_path.clone()),
        Err(DurableCoordinatorError::Persistence(
            PersistenceError::InvalidChain
        ))
    ));
    assert_eq!(persisted_material(&store_path), before);
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();
    assert_eq!(store.operation_history(&operation_id).unwrap().len(), 3);
    assert_eq!(store.history(&job_id).unwrap().len(), 1);
    assert!(!store_path
        .join("operations")
        .join(&operation_id)
        .join("revisions/4.json")
        .exists());
    assert!(!store_path
        .join("jobs")
        .join(&job_id)
        .join("revisions/2.json")
        .exists());
}

fn child_recovery_checkpoint(root: &Path) {
    let (drafts, snapshots, engine, context, command) = setup(root);
    let frozen = crate::workbench_analysis::freeze_analysis_input(
        &drafts,
        crate::workbench_analysis::AnalysisFreezeSpec {
            draft_id: command.draft_id.clone(),
            expected_revision: command.draft_revision.clone(),
            opening_hand: command.opening_hand.clone(),
            seed: command.seed,
            rules: command.rules.clone(),
            catalog_id: command.catalog_id.clone(),
            banlist_id: command.banlist_id.clone(),
            as_of: command.as_of.clone(),
            search: command.search.clone(),
        },
        engine,
        &snapshots,
        &context.default_catalog_id,
    )
    .unwrap();
    let store_path = root.join("store");
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();
    let operation_id = "a".repeat(32);
    let job_id = "b".repeat(32);
    let allocated = Operation::allocate(operation_id, context.clone(), 100).unwrap();
    let queued = AnalysisJobRecordV1::new(job_id.clone(), &frozen, context.scoring.clone(), 102)
        .unwrap();
    let begun = allocated.begin(command, job_id.clone(), 101).unwrap();
    let accepting = begun
        .bind_input(queued.input().clone(), 102)
        .unwrap();
    store.append_operation(&allocated).unwrap();
    store.append_operation(&begun).unwrap();
    store.append_operation(&accepting).unwrap();
    store.append_initial(queued).unwrap();
    drop(store);
    let _ = DurableAnalysisCoordinator::open_operations(store_path).unwrap();
    panic!("recovery checkpoint did not stop the child");
}

fn child_partial_task_recovery(root: &Path, running_job: Option<char>) {
    let (drafts, snapshots, engine, context, command) = setup(root);
    let frozen = freeze_test_input(&drafts, &snapshots, engine, &context, &command);
    let store_path = root.join("store");
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();
    for (op_char, job_char) in [('a', 'b'), ('c', 'd')] {
        let operation_id = op_char.to_string().repeat(32);
        let job_id = job_char.to_string().repeat(32);
        let allocated = Operation::allocate(operation_id, context.clone(), 100).unwrap();
        let job = AnalysisJobRecordV1::new(job_id.clone(), &frozen, context.scoring.clone(), 102).unwrap();
        let begun = allocated.begin(command.clone(), job_id, 101).unwrap();
        let bound = begun.bind_input(job.input().clone(), 102).unwrap();
        store.append_operation(&allocated).unwrap();
        store.append_operation(&begun).unwrap();
        store.append_operation(&bound).unwrap();
        store.append_initial(job.clone()).unwrap();
        if running_job == Some(job_char) {
            let running = job.transition(1, AnalysisJobEvent::Start, 103).unwrap();
            store.append_expected(job.job_id(), 1, running).unwrap();
        }
    }
    drop(store);
    let _coordinator = DurableAnalysisCoordinator::open_operations(store_path).unwrap();
    panic!("task classification checkpoint did not stop the child");
}

fn child_partial_operation_recovery(root: &Path) {
    let (_, _, _, context, command) = setup(root);
    let store_path = root.join("store");
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();
    for (op_char, job_char) in [('a', 'b'), ('c', 'd')] {
        let allocated = Operation::allocate(op_char.to_string().repeat(32), context.clone(), 100).unwrap();
        let begun = allocated.begin(command.clone(), job_char.to_string().repeat(32), 101).unwrap();
        store.append_operation(&allocated).unwrap();
        store.append_operation(&begun).unwrap();
    }
    drop(store);
    let _coordinator = DurableAnalysisCoordinator::open_operations(store_path).unwrap();
    panic!("operation classification checkpoint did not stop the child");
}

fn child_mixed_operation_recovery(root: &Path) {
    let (drafts, snapshots, engine, context, command) = setup(root);
    let frozen = freeze_test_input(&drafts, &snapshots, engine, &context, &command);
    let store_path = root.join("store");
    let store = PersistentAnalysisJobStore::open_unclassified(store_path.clone()).unwrap();

    let unknown_id = "a".repeat(32);
    let unknown_allocated = Operation::allocate(unknown_id, context.clone(), 100).unwrap();
    let unknown = unknown_allocated
        .begin(command.clone(), "b".repeat(32), 101)
        .unwrap();
    store.append_operation(&unknown_allocated).unwrap();
    store.append_operation(&unknown).unwrap();

    let accepted_id = "c".repeat(32);
    let job_id = "d".repeat(32);
    let allocated = Operation::allocate(accepted_id, context.clone(), 100).unwrap();
    let job = AnalysisJobRecordV1::new(job_id.clone(), &frozen, context.scoring.clone(), 102).unwrap();
    let begun = allocated
        .begin(command.clone(), job_id.clone(), 101)
        .unwrap();
    let accepting = begun.bind_input(job.input().clone(), 102).unwrap();
    store.append_operation(&allocated).unwrap();
    store.append_operation(&begun).unwrap();
    store.append_operation(&accepting).unwrap();
    store.append_initial(job).unwrap();
    drop(store);

    let _coordinator = DurableAnalysisCoordinator::open_operations(store_path).unwrap();
    panic!("mixed operation recovery checkpoint did not stop the child");
}

#[test]
fn recovery_unknown_operation_publish_faults_preserve_later_work_and_resume_once() {
    use super::super::persistence::FaultPhase;
    for phase in [FaultPhase::BeforePublish, FaultPhase::AfterPublish, FaultPhase::Reread] {
        let root = root();
        let (_, _, _, context, command) = setup(&root);
        let path = root.join("store");
        let store = PersistentAnalysisJobStore::open_unclassified(path.clone()).unwrap();
        let ids = ["a".repeat(32), "c".repeat(32)];
        for (id, job_char) in ids.iter().zip(['b', 'd']) {
            let allocated = Operation::allocate(id.clone(), context.clone(), 100).unwrap();
            let accepting = allocated.begin(command.clone(), job_char.to_string().repeat(32), 101).unwrap();
            store.append_operation(&allocated).unwrap();
            store.append_operation(&accepting).unwrap();
        }
        store.authenticate_operation_bindings().unwrap();
        drop(store);
        let before = persisted_material(&path);
        let (result, hits) = DurableAnalysisCoordinator::open_operations_with_fault(
            path.clone(), "operation", "unknown", 3, phase,
        );
        assert_eq!(hits, 1);
        assert!(result.is_err());
        let faulted = persisted_material(&path);
        for (name, bytes) in &before { assert_eq!(faulted.get(name), Some(bytes)); }
        let before_publish = matches!(phase, FaultPhase::BeforePublish);
        assert_eq!(faulted.len(), before.len() + usize::from(!before_publish));
        let store = PersistentAnalysisJobStore::open_unclassified(path.clone()).unwrap();
        store.authenticate_operation_bindings().unwrap();
        let first = store.operation_history(&ids[0]).unwrap();
        let second = store.operation_history(&ids[1]).unwrap();
        assert_eq!(first.len(), if before_publish { 2 } else { 3 });
        assert_eq!(first.last().unwrap().state(), if before_publish { AnalysisOperationState::Accepting } else { AnalysisOperationState::Unknown });
        assert_eq!(second.len(), 2);
        assert_eq!(second.last().unwrap().state(), AnalysisOperationState::Accepting);
        assert_eq!(fs::read_dir(path.join("jobs")).unwrap().count(), 0);
        assert_eq!(fs::read_dir(path.join("reports")).unwrap().count(), 0);
        drop(store);
        assert_eq!(persisted_material(&path), faulted);
        let coordinator = DurableAnalysisCoordinator::open_operations(path.clone()).unwrap();
        for id in &ids {
            let history = coordinator.inspect_operation(id).unwrap();
            assert_eq!(history.len(), 3);
            assert_eq!(history.last().unwrap().state(), AnalysisOperationState::Unknown);
            let duplicate = coordinator.begin_operation(id, command.clone(), &context, 102).unwrap();
            assert_eq!(duplicate.record.state(), AnalysisOperationState::Unknown);
            assert!(duplicate.ticket.is_none());
        }
        assert_eq!(coordinator.freeze_attempts_for_test(), 0);
        assert!(coordinator.snapshot().unwrap().queued.is_none());
        assert!(coordinator.snapshot().unwrap().running.is_none());
        assert!(coordinator.claim_next(10_000).unwrap().is_none());
        drop(coordinator);
        let recovered = persisted_material(&path);
        assert_eq!(recovered.len(), before.len() + 2);
        for (name, bytes) in &faulted { assert_eq!(recovered.get(name), Some(bytes)); }
        let reopened = DurableAnalysisCoordinator::open_operations(path.clone()).unwrap();
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        assert_eq!(persisted_material(&path), recovered);
        let hash_map = |files: &BTreeMap<String, Vec<u8>>| files.iter().map(|(name, bytes)| (name.clone(), ygo_storage::hash(bytes))).collect::<BTreeMap<_, _>>();
        fs::write(root.join("unknown-operation-fault-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
            "phase": format!("{phase:?}"), "fault_hits": hits, "before": hash_map(&before),
            "faulted": hash_map(&faulted), "recovered": hash_map(&recovered), "repeat_reopen_stable": true,
        })).unwrap()).unwrap();
    }
}

#[test]
fn h3_2b_cross_chain_windows_recover_after_process_kill() {
    if let Some(stage) = std::env::var_os(CHILD_STAGE) {
        let root = std::path::PathBuf::from(std::env::var_os(CHILD_ROOT).unwrap());
        let stage = stage.to_string_lossy();
        if stage == "recovery_first_operation_classified_before_next" {
            child_partial_operation_recovery(&root);
        }
        if stage == "recovery_mixed_operations_first_classified_before_next" {
            child_mixed_operation_recovery(&root);
        }
        if stage == "recovery_first_task_classified_before_next" || stage == "recovery_first_task_classified_before_running" || stage == "recovery_unknown_before_queued" {
            let running_job = if stage == "recovery_first_task_classified_before_running" { Some('d') } else if stage == "recovery_unknown_before_queued" { Some('b') } else { None };
            child_partial_task_recovery(&root, running_job);
        }
        if stage == "recovery_operation_repaired_before_task_classified" {
            child_recovery_checkpoint(&root);
        }
        child_submit_to_checkpoint(&root, &stage);
    }

    let stages = [
        "recovery_unknown_before_queued",
        "recovery_first_task_classified_before_running",
        "accepted_persisted_before_queue_update",
        "recovery_first_operation_classified_before_next",
        "recovery_mixed_operations_first_classified_before_next",
        "recovery_first_task_classified_before_next",
        "budget_persisted_before_queue_update",
        "time_budget_persisted_before_queue_update",
        "unknown_persisted_before_queue_update",
        "completed_persisted_before_queue_update",
        "failed_persisted_before_queue_update",
        "asset_mismatch_persisted_before_queue_update",
        "running_persisted_before_queue_update",
        "running_queue_updated_before_ticket_return",
        "cancelled_persisted_before_queue_update",
        "preparation_rejected_persisted_before_return",
        "context_rejected_persisted_before_return",
        "capacity_rejected_persisted_before_return",
        "allocated_persisted_before_return",
        "accepting_persisted_before_freeze",
        "frozen_input_persisted_before_task",
        "task_persisted_before_acceptance",
        "report_persisted_before_terminal",
        "recovery_operation_repaired_before_task_classified",
    ];
    for stage in stages {
        let root = root();
        let store = root.join("store");
        let (mut child, _marker) = spawn_checkpoint_child(&root, stage);
        let operations = operation_dirs(&store);
        if stage == "recovery_first_operation_classified_before_next" {
            assert_eq!(operations, ["a".repeat(32), "c".repeat(32)]);
            let first = authenticate_operation_chain(&store, &operations[0]);
            let second = authenticate_operation_chain(&store, &operations[1]);
            assert_eq!(first.len(), 3);
            assert_eq!(first.last().unwrap().state(), AnalysisOperationState::Unknown);
            assert_eq!(second.len(), 2);
            assert_eq!(second.last().unwrap().state(), AnalysisOperationState::Accepting);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            assert_child_event_counts(&root, 0, 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            for id in &operations {
                let history = coordinator.inspect_operation(id).unwrap();
                assert_eq!(history.len(), 3);
                assert_eq!(history.last().unwrap().state(), AnalysisOperationState::Unknown);
            }
            assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            assert!(coordinator.snapshot().unwrap().queued.is_none());
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.claim_next(10_000).unwrap().is_none());
            drop(coordinator);
            let recovered = persisted_material(&store);
            for (path, bytes) in &before { assert_eq!(recovered.get(path), Some(bytes)); }
            assert_eq!(recovered.len(), before.len() + 1);
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            assert!(reopened.claim_next(10_001).unwrap().is_none());
            drop(reopened);
            assert_eq!(persisted_material(&store), recovered);
            let before_hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            let after_hashes: BTreeMap<_, _> = recovered.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join("partial-operation-recovery-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "operation_ids": operations,
                "pre_kill_material_sha256": before_hashes, "recovered_material_sha256": after_hashes, "repeat_reopen_stable": true,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "recovery_mixed_operations_first_classified_before_next" {
            assert_eq!(operations, ["a".repeat(32), "c".repeat(32)]);
            let job_id = "d".repeat(32);
            let unknown = authenticate_operation_chain(&store, &operations[0]);
            assert_eq!(unknown.len(), 3);
            assert_eq!(unknown.last().unwrap().state(), AnalysisOperationState::Unknown);
            let accepting = authenticate_operation_chain(&store, &operations[1]);
            assert_eq!(accepting.len(), 3);
            assert_eq!(accepting.last().unwrap().state(), AnalysisOperationState::Accepting);
            assert_eq!(accepting.last().unwrap().job_id(), Some(job_id.as_str()));
            let queued = authenticate_single_queued_job(&store, &job_id);
            assert_eq!(
                serde_json::to_value(accepting.last().unwrap().frozen_input().unwrap()).unwrap(),
                serde_json::to_value(queued.input()).unwrap()
            );
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 1);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            assert_child_event_counts(&root, 0, 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);

            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let unknown = coordinator.inspect_operation(&operations[0]).unwrap();
            assert_eq!(unknown.len(), 3);
            assert_eq!(unknown.last().unwrap().state(), AnalysisOperationState::Unknown);
            let accepted = coordinator.inspect_operation(&operations[1]).unwrap();
            assert_eq!(accepted.len(), 4);
            assert_eq!(accepted.last().unwrap().state(), AnalysisOperationState::Accepted);
            let interrupted = coordinator.inspect_job(&job_id).unwrap();
            assert_eq!(interrupted.len(), 2);
            assert_eq!(interrupted.last().unwrap().state(), AnalysisJobState::Interrupted);
            let duplicate_unknown = coordinator
                .begin_operation(
                    &operations[0],
                    unknown.last().unwrap().command().unwrap().clone(),
                    unknown.last().unwrap().context(),
                    10_000,
                )
                .unwrap();
            assert_eq!(duplicate_unknown.record.state(), AnalysisOperationState::Unknown);
            assert!(duplicate_unknown.ticket.is_none());
            let duplicate_accepted = coordinator
                .begin_operation(
                    &operations[1],
                    accepted.last().unwrap().command().unwrap().clone(),
                    accepted.last().unwrap().context(),
                    10_000,
                )
                .unwrap();
            assert_eq!(duplicate_accepted.record.state(), AnalysisOperationState::Accepted);
            assert!(duplicate_accepted.ticket.is_none());
            assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            assert!(coordinator.snapshot().unwrap().queued.is_none());
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.claim_next(10_001).unwrap().is_none());
            drop(coordinator);

            let recovered = persisted_material(&store);
            for (path, bytes) in &before {
                assert_eq!(recovered.get(path), Some(bytes));
            }
            assert_eq!(recovered.len(), before.len() + 2);
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            assert_eq!(
                reopened.inspect_operation(&operations[1]).unwrap().last().unwrap().state(),
                AnalysisOperationState::Accepted
            );
            assert_eq!(
                reopened.inspect_job(&job_id).unwrap().last().unwrap().state(),
                AnalysisJobState::Interrupted
            );
            assert!(reopened.claim_next(10_002).unwrap().is_none());
            drop(reopened);
            assert_eq!(persisted_material(&store), recovered);

            let before_hashes: BTreeMap<_, _> = before
                .iter()
                .map(|(path, bytes)| (path, ygo_storage::hash(bytes)))
                .collect();
            let after_hashes: BTreeMap<_, _> = recovered
                .iter()
                .map(|(path, bytes)| (path, ygo_storage::hash(bytes)))
                .collect();
            fs::write(
                root.join("mixed-operation-recovery-evidence.json"),
                serde_json::to_vec_pretty(&serde_json::json!({
                    "checkpoint": stage,
                    "child_exit": killed.to_string(),
                    "operation_ids": operations,
                    "job_id": job_id,
                    "pre_kill_material_sha256": before_hashes,
                    "recovered_material_sha256": after_hashes,
                    "repeat_reopen_stable": true,
                }))
                .unwrap(),
            )
            .unwrap();
            continue;
        }
        if stage == "recovery_first_task_classified_before_next" || stage == "recovery_first_task_classified_before_running" || stage == "recovery_unknown_before_queued" {
            let mixed = stage == "recovery_first_task_classified_before_running";
            let unknown_first = stage == "recovery_unknown_before_queued";
            assert_eq!(operations, ["a".repeat(32), "c".repeat(32)]);
            let first = "b".repeat(32);
            let second = "d".repeat(32);
            authenticate_partial_recovery_pair(&store, &operations[0], &first, true, unknown_first);
            authenticate_partial_recovery_pair(&store, &operations[1], &second, false, mixed);
            for id in &operations {
                assert_eq!(read_record(&store, "operations", id, 4)["state"], "accepted");
            }
            assert_eq!(read_record(&store, "jobs", &first, if unknown_first { 3 } else { 2 })["state"], if unknown_first { "unknown" } else { "interrupted" });
            assert_eq!(read_record(&store, "jobs", &second, 1)["state"], "queued");
            if mixed { assert_eq!(read_record(&store, "jobs", &second, 2)["state"], "running"); }
            else { assert!(!store.join("jobs").join(&second).join("revisions/2.json").exists()); }
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            assert_child_event_counts(&root, 0, 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let first_history = coordinator.inspect_job(&first).unwrap();
            assert_eq!(first_history.len(), if unknown_first { 3 } else { 2 });
            assert_eq!(first_history.last().unwrap().state(), if unknown_first { AnalysisJobState::Unknown } else { AnalysisJobState::Interrupted });
            let second_history = coordinator.inspect_job(&second).unwrap();
            assert_eq!(second_history.len(), if mixed { 3 } else { 2 });
            assert_eq!(second_history.last().unwrap().state(), if mixed { AnalysisJobState::Unknown } else { AnalysisJobState::Interrupted });
            assert!(coordinator.snapshot().unwrap().queued.is_none());
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.claim_next(10_000).unwrap().is_none());
            drop(coordinator);
            let recovered = persisted_material(&store);
            for (path, bytes) in &before { assert_eq!(recovered.get(path), Some(bytes)); }
            assert_eq!(recovered.len(), before.len() + 1);
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            assert!(reopened.claim_next(10_001).unwrap().is_none());
            drop(reopened);
            assert_eq!(persisted_material(&store), recovered);
            let before_hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            let after_hashes: BTreeMap<_, _> = recovered.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join(if unknown_first { "unknown-first-recovery-evidence.json" } else if mixed { "mixed-task-recovery-evidence.json" } else { "partial-task-recovery-evidence.json" }), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "first_job": first, "second_job": second,
                "pre_kill_material_sha256": before_hashes, "recovered_material_sha256": after_hashes, "repeat_reopen_stable": true,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "capacity_rejected_persisted_before_return" {
            assert_eq!(operations.len(), 2);
            let mut rejected_id = None;
            let mut accepting_id = None;
            for id in &operations {
                let history = authenticate_operation_chain(&store, id);
                match history.last().unwrap().state() {
                    AnalysisOperationState::Accepting => accepting_id = Some(id.clone()),
                    AnalysisOperationState::Rejected => rejected_id = Some(id.clone()),
                    state => panic!("unexpected operation state {state:?}"),
                }
            }
            let accepting_id = accepting_id.unwrap();
            let rejected_id = rejected_id.unwrap();
            assert_eq!(read_record(&store, "operations", &rejected_id, 2)["error_code"], "analysis_queue_full");
            assert_child_event_counts(&root, 0, 0);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let accepting = coordinator.inspect_operation(&accepting_id).unwrap();
            assert_eq!(accepting.len(), 3);
            assert_eq!(accepting.last().unwrap().state(), AnalysisOperationState::Unknown);
            let rejected = coordinator.inspect_operation(&rejected_id).unwrap();
            assert_eq!(rejected.len(), 2);
            assert_eq!(rejected.last().unwrap().state(), AnalysisOperationState::Rejected);
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.snapshot().unwrap().queued.is_none());
            assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            assert!(coordinator.claim_next(10_000).unwrap().is_none());
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            drop(coordinator);
            let recovered = persisted_material(&store);
            for (path, bytes) in &before { assert_eq!(recovered.get(path), Some(bytes)); }
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let saved_rejection = reopened.inspect_operation(&rejected_id).unwrap().pop().unwrap();
            let duplicate = reopened.begin_operation(&rejected_id, saved_rejection.command().unwrap().clone(), saved_rejection.context(), 10_001).unwrap();
            assert_eq!(duplicate.record.state(), AnalysisOperationState::Rejected);
            assert_eq!(duplicate.record.error_code(), Some("analysis_queue_full"));
            assert!(duplicate.ticket.is_none());
            assert_eq!(reopened.freeze_attempts_for_test(), 0);
            assert!(reopened.claim_next(10_001).unwrap().is_none());
            drop(reopened);
            assert_eq!(persisted_material(&store), recovered);
            let before_hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            let recovered_hashes: BTreeMap<_, _> = recovered.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join("capacity-rejected-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage,
                "child_exit": killed.to_string(),
                "accepting_operation_id": accepting_id,
                "rejected_operation_id": rejected_id,
                "freeze_events_before_kill": 0,
                "claim_events_before_kill": 0,
                "pre_kill_material_sha256": before_hashes,
                "recovered_material_sha256": recovered_hashes,
                "repeated_reopen_stable": true,
            })).unwrap()).unwrap();
            continue;
        }
        assert_eq!(operations.len(), 1);
        let operation_id = operations[0].clone();
        if stage == "accepted_persisted_before_queue_update" {
            let op = read_record(&store, "operations", &operation_id, 4);
            let job_id = op["job_id"].as_str().unwrap().to_owned();
            authenticate_partial_recovery_pair(&store, &operation_id, &job_id, false, false);
            assert_child_event_counts(&root, 1, 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let history = coordinator.inspect_operation(&operation_id).unwrap();
            assert_eq!(history.len(), 4);
            assert_eq!(history.last().unwrap().state(), AnalysisOperationState::Accepted);
            let jobs = coordinator.inspect_job(&job_id).unwrap();
            assert_eq!(jobs.len(), 2);
            assert_eq!(jobs.last().unwrap().state(), AnalysisJobState::Interrupted);
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.snapshot().unwrap().queued.is_none());
            assert!(coordinator.claim_next(10_000).unwrap().is_none());
            drop(coordinator);
            let recovered = persisted_material(&store);
            for (path, bytes) in &before { assert_eq!(recovered.get(path), Some(bytes)); }
            assert_eq!(recovered.len(), before.len() + 1);
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            assert!(reopened.claim_next(10_001).unwrap().is_none());
            drop(reopened);
            assert_eq!(persisted_material(&store), recovered);
            let before_hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            let after_hashes: BTreeMap<_, _> = recovered.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join("accepted-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "operation_id": operation_id, "job_id": job_id,
                "pre_kill_material_sha256": before_hashes, "recovered_material_sha256": after_hashes, "repeat_reopen_stable": true,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "cancelled_persisted_before_queue_update" || stage == "running_persisted_before_queue_update" || stage == "running_queue_updated_before_ticket_return" || stage == "failed_persisted_before_queue_update" || stage == "asset_mismatch_persisted_before_queue_update" || stage == "completed_persisted_before_queue_update" || stage == "budget_persisted_before_queue_update" || stage == "time_budget_persisted_before_queue_update" || stage == "unknown_persisted_before_queue_update" {
            let running = stage == "running_persisted_before_queue_update" || stage == "running_queue_updated_before_ticket_return";
            let failed = stage == "failed_persisted_before_queue_update";
            let asset_mismatch = stage == "asset_mismatch_persisted_before_queue_update";
            let explicit_unknown = stage == "unknown_persisted_before_queue_update";
            let terminal_failure = failed || asset_mismatch;
            let node_budget = stage == "budget_persisted_before_queue_update";
            let time_budget = stage == "time_budget_persisted_before_queue_update";
            let budget = node_budget || time_budget;
            let completed = stage == "completed_persisted_before_queue_update" || budget;
            let terminal_revision = terminal_failure || completed || explicit_unknown;
            let operation_history = authenticate_operation_chain(&store, &operation_id);
            assert_eq!(operation_history.len(), 4);
            let op = operation_history.last().unwrap();
            assert_eq!(op.state(), AnalysisOperationState::Accepted);
            let job_id = op.job_id().unwrap().to_owned();
            let revisions = store.join("jobs").join(&job_id).join("revisions");
            assert_eq!(fs::read_dir(&revisions).unwrap().count(), if terminal_revision { 3 } else { 2 });
            let mut previous = None;
            let mut jobs: Vec<AnalysisJobRecordV1> = Vec::new();
            for revision in 1..=if terminal_revision { 3 } else { 2 } {
                let raw = fs::read(revisions.join(format!("{revision}.json"))).unwrap();
                let envelope: serde_json::Value = serde_json::from_slice(&raw).unwrap();
                assert_eq!(envelope["schema_version"], 1);
                assert_eq!(envelope["kind"], "workbench_analysis_job_revision");
                assert_eq!(envelope["job_id"], job_id);
                assert_eq!(envelope["revision"], revision);
                assert_eq!(envelope["previous_sha256"].as_str().map(str::to_owned), previous);
                let job = AnalysisJobRecordV1::read_json(&serde_json::to_vec(&envelope["record"]).unwrap()).unwrap();
                assert_eq!(envelope["record_sha256"].as_str(), Some(ygo_storage::hash(&job.encode_json().unwrap()).as_str()));
                assert_eq!(job.job_id(), job_id);
                assert_eq!(job.revision(), revision);
                previous = Some(ygo_storage::hash(&raw));
                jobs.push(job);
            }
            assert_eq!(jobs[0].state(), AnalysisJobState::Queued);
            assert_eq!(jobs[1].state(), if running || terminal_revision { AnalysisJobState::Running } else { AnalysisJobState::Cancelled });
            assert_eq!(jobs[0].transition(1, if running || terminal_revision { AnalysisJobEvent::Start } else { AnalysisJobEvent::Cancel }, 102).unwrap().encode_json().unwrap(), jobs[1].encode_json().unwrap());
            if failed {
                assert_eq!(jobs[2].state(), AnalysisJobState::Failed);
                assert_eq!(jobs[1].transition(2, AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed), 103).unwrap().encode_json().unwrap(), jobs[2].encode_json().unwrap());
            }
            if asset_mismatch {
                assert_eq!(jobs[2].state(), AnalysisJobState::Failed);
                assert_eq!(jobs[2].error_code(), Some(AnalysisJobFailure::AssetMismatch));
                assert_eq!(jobs[1].transition(2, AnalysisJobEvent::Fail(AnalysisJobFailure::AssetMismatch), 102).unwrap().encode_json().unwrap(), jobs[2].encode_json().unwrap());
            }
            if explicit_unknown {
                assert_eq!(jobs[2].state(), AnalysisJobState::Unknown);
                assert_eq!(jobs[2].error_code(), Some(AnalysisJobFailure::CompletionUncertain));
                assert_eq!(jobs[1].transition(2, AnalysisJobEvent::Fail(AnalysisJobFailure::CompletionUncertain), 103).unwrap().encode_json().unwrap(), jobs[2].encode_json().unwrap());
            }
            if completed {
                assert_eq!(jobs[2].state(), if budget { AnalysisJobState::BudgetLimited } else { AnalysisJobState::Completed });
                let reference = jobs[2].report().unwrap();
                let report = fs::read(store.join("reports").join(format!("{}.json", reference.report_id))).unwrap();
                assert_eq!(ygo_storage::hash(&report), reference.sha256);
                assert_eq!(jobs[1].transition(2, AnalysisJobEvent::ReportPublished(reference.clone()), 103).unwrap().encode_json().unwrap(), jobs[2].encode_json().unwrap());
            }
            assert_eq!(serde_json::to_value(op.frozen_input().unwrap()).unwrap(), serde_json::to_value(jobs[0].input()).unwrap());
            assert_child_event_counts(&root, 1, usize::from(running || terminal_failure || completed || explicit_unknown));
            if asset_mismatch {
                let events = fs::read_to_string(root.join("child-events.log")).unwrap();
                assert_eq!(events.lines().collect::<Vec<_>>(), ["freeze", "claim", "asset_mismatch_persisted"]);
            }
            if stage == "running_queue_updated_before_ticket_return" {
                let events = fs::read_to_string(root.join("child-events.log")).unwrap();
                assert_eq!(events.lines().collect::<Vec<_>>(), ["freeze", "claim", "queue_updated"]);
            }
            if explicit_unknown {
                let events = fs::read_to_string(root.join("child-events.log")).unwrap();
                assert_eq!(events.lines().collect::<Vec<_>>(), ["freeze", "claim"]);
            }
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), usize::from(completed));
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            let mut first_recovery = None;
            for now in [10_000, 10_001] {
                let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
                assert_eq!(coordinator.inspect_operation(&operation_id).unwrap().last().unwrap().state(), AnalysisOperationState::Accepted);
                let saved = coordinator.inspect_job(&job_id).unwrap();
                assert_eq!(saved.len(), if running || terminal_revision { 3 } else { 2 });
                assert_eq!(saved.last().unwrap().state(), if running || explicit_unknown { AnalysisJobState::Unknown } else if terminal_failure { AnalysisJobState::Failed } else if budget { AnalysisJobState::BudgetLimited } else if completed { AnalysisJobState::Completed } else { AnalysisJobState::Cancelled });
                if asset_mismatch {
                    assert_eq!(saved.last().unwrap().error_code(), Some(AnalysisJobFailure::AssetMismatch));
                }
                if explicit_unknown {
                    assert_eq!(saved.last().unwrap().error_code(), Some(AnalysisJobFailure::CompletionUncertain));
                }
                if completed { assert_eq!(coordinator.inspect_report(&job_id).unwrap().search.termination, if time_budget { "time_budget" } else if node_budget { "node_budget" } else { "exhausted" }); }
                assert!(coordinator.snapshot().unwrap().queued.is_none());
                assert!(coordinator.snapshot().unwrap().running.is_none());
                assert!(coordinator.claim_next(now).unwrap().is_none());
                drop(coordinator);
                let after = persisted_material(&store);
                for (path, bytes) in &before { assert_eq!(after.get(path), Some(bytes)); }
                assert_eq!(after.len(), before.len() + usize::from(running));
                if let Some(ref first) = first_recovery { assert_eq!(&after, first); } else { first_recovery = Some(after); }
            }
            let hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            let recovered_hashes = first_recovery.as_ref().map(|files| {
                files.iter().map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes))).collect::<BTreeMap<_, _>>()
            });
            fs::write(root.join(if asset_mismatch { "asset-mismatch-evidence.json" } else if explicit_unknown { "unknown-terminal-evidence.json" } else if running { "running-evidence.json" } else if failed { "failed-evidence.json" } else if time_budget { "time-budget-evidence.json" } else if node_budget { "budget-evidence.json" } else if completed { "completed-evidence.json" } else { "cancelled-evidence.json" }), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "operation_id": operation_id, "job_id": job_id,
                "freeze_events_before_kill": 1, "claim_events_before_kill": usize::from(running || terminal_failure || completed || explicit_unknown),
                "events_before_kill": fs::read_to_string(root.join("child-events.log")).unwrap().lines().collect::<Vec<_>>(),
                "report_count_before_kill": usize::from(completed), "executor_invocations_before_kill": 0,
                "report_termination": if time_budget { Some("time_budget") } else if node_budget { Some("node_budget") } else { None },
                "claim_returned": if asset_mismatch { Some(false) } else { None },
                "failure_code": if asset_mismatch { Some("asset_mismatch") } else { None },
                "recovered_material_sha256": recovered_hashes,
                "pre_kill_material_sha256": hashes, "stable_reopens": 2,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "preparation_rejected_persisted_before_return" {
            let history = authenticate_operation_chain(&store, &operation_id);
            assert_eq!(history.len(), 3);
            let rejected = history.last().unwrap();
            assert_eq!(rejected.state(), AnalysisOperationState::Rejected);
            assert_eq!(rejected.error_code(), Some("opening_hand_invalid"));
            assert_eq!(rejected.rejection().unwrap().http_status, 422);
            assert!(rejected.job_id().is_some());
            assert!(rejected.frozen_input().is_none());
            assert_child_event_counts(&root, 1, 0);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            for now in [10_000, 10_001] {
                let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
                let saved = coordinator.inspect_operation(&operation_id).unwrap();
                assert_eq!(saved.len(), 3);
                let last = saved.last().unwrap();
                assert_eq!(last.state(), AnalysisOperationState::Rejected);
                let duplicate = coordinator.begin_operation(&operation_id, last.command().unwrap().clone(), last.context(), now).unwrap();
                assert_eq!(duplicate.record.error_code(), Some("opening_hand_invalid"));
                assert!(duplicate.ticket.is_none());
                assert_eq!(coordinator.freeze_attempts_for_test(), 0);
                assert!(coordinator.snapshot().unwrap().running.is_none());
                assert!(coordinator.snapshot().unwrap().queued.is_none());
                assert!(coordinator.claim_next(now).unwrap().is_none());
                drop(coordinator);
                assert_eq!(persisted_material(&store), before);
            }
            let hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join("preparation-rejected-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "operation_id": operation_id,
                "freeze_events_before_kill": 1, "claim_events_before_kill": 0,
                "pre_kill_material_sha256": hashes, "stable_reopens": 2,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "context_rejected_persisted_before_return" {
            let history = authenticate_operation_chain(&store, &operation_id);
            let rejected = history.last().unwrap();
            assert_eq!(rejected.state(), AnalysisOperationState::Rejected);
            assert_eq!(rejected.error_code(), Some("analysis_operation_context_changed"));
            assert!(rejected.job_id().is_none());
            assert_child_event_counts(&root, 0, 0);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            for now in [10_000, 10_001] {
                let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
                let saved = coordinator.inspect_operation(&operation_id).unwrap();
                assert_eq!(saved.len(), 2);
                let last = saved.last().unwrap();
                assert_eq!(last.state(), AnalysisOperationState::Rejected);
                let duplicate = coordinator.begin_operation(&operation_id, last.command().unwrap().clone(), last.context(), now).unwrap();
                assert_eq!(duplicate.record.error_code(), Some("analysis_operation_context_changed"));
                assert!(duplicate.ticket.is_none());
                assert_eq!(coordinator.freeze_attempts_for_test(), 0);
                assert!(coordinator.snapshot().unwrap().running.is_none());
                assert!(coordinator.snapshot().unwrap().queued.is_none());
                assert!(coordinator.claim_next(now).unwrap().is_none());
                drop(coordinator);
                assert_eq!(persisted_material(&store), before);
            }
            let hashes: BTreeMap<_, _> = before.iter().map(|(path, bytes)| (path, ygo_storage::hash(bytes))).collect();
            fs::write(root.join("context-rejected-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage, "child_exit": killed.to_string(), "operation_id": operation_id,
                "freeze_events_before_kill": 0, "claim_events_before_kill": 0,
                "pre_kill_material_sha256": hashes, "stable_reopens": 2,
            })).unwrap()).unwrap();
            continue;
        }
        if stage == "allocated_persisted_before_return" {
            let revisions = store.join("operations").join(&operation_id).join("revisions");
            assert_eq!(fs::read_dir(&revisions).unwrap().count(), 1);
            let raw = fs::read(revisions.join("1.json")).unwrap();
            let envelope: serde_json::Value = serde_json::from_slice(&raw).unwrap();
            let record = Operation::read_json(&serde_json::to_vec(&envelope["record"]).unwrap()).unwrap();
            assert_eq!(envelope["schema_version"], 1);
            assert_eq!(envelope["kind"], "workbench_analysis_operation_revision");
            assert_eq!(envelope["operation_id"], operation_id);
            assert_eq!(envelope["revision"], 1);
            assert!(envelope["previous_sha256"].is_null());
            assert_eq!(envelope["record_sha256"].as_str(), Some(ygo_storage::hash(&record.encode_json().unwrap()).as_str()));
            assert_eq!(record.state(), AnalysisOperationState::Allocated);
            assert_eq!(record.operation_id(), operation_id);
            assert!(record.command().is_none());
            assert!(record.command_sha256().is_none());
            assert!(record.job_id().is_none());
            assert_child_event_counts(&root, 0, 0);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let before = persisted_material(&store);
            let killed = child.kill();
            assert!(!killed.success());
            assert_eq!(persisted_material(&store), before);
            for now in [10_000, 10_001] {
                let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
                let history = coordinator.inspect_operation(&operation_id).unwrap();
                assert_eq!(history.len(), 1);
                assert_eq!(history[0].state(), AnalysisOperationState::Allocated);
                assert_eq!(coordinator.freeze_attempts_for_test(), 0);
                assert!(coordinator.snapshot().unwrap().queued.is_none());
                assert!(coordinator.snapshot().unwrap().running.is_none());
                assert!(coordinator.claim_next(now).unwrap().is_none());
                drop(coordinator);
                assert_eq!(persisted_material(&store), before);
            }
            let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let fresh = coordinator.allocate_operation(record.context().clone(), 10_002).unwrap();
            assert_ne!(fresh.operation_id(), operation_id);
            assert_eq!(fresh.state(), AnalysisOperationState::Allocated);
            assert!(fresh.job_id().is_none());
            assert!(coordinator.snapshot().unwrap().running.is_none());
            assert!(coordinator.claim_next(10_003).unwrap().is_none());
            assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            assert_eq!(fs::read_dir(store.join("jobs")).unwrap().count(), 0);
            assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            let hashes: BTreeMap<_, _> = before.iter()
                .map(|(path, bytes)| (path, ygo_storage::hash(bytes)))
                .collect();
            fs::write(root.join("allocated-evidence.json"), serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": stage,
                "operation_id": operation_id,
                "new_operation_id": fresh.operation_id(),
                "child_exit": killed.to_string(),
                "freeze_events": 0,
                "claim_events_before_kill": 0,
                "stable_reopens": 2,
                "pre_kill_material_sha256": hashes,
            })).unwrap()).unwrap();
            continue;
        }
        let operation_revision = if matches!(
            stage,
            "frozen_input_persisted_before_task" | "task_persisted_before_acceptance"
        ) {
            3
        } else if stage == "accepting_persisted_before_freeze" {
            2
        } else {
            4
        };
        let operation = read_record(&store, "operations", &operation_id, operation_revision);
        let job_id = operation["job_id"].as_str().unwrap().to_owned();

        let (freeze_attempts, claim_attempts) = match stage {
            "accepting_persisted_before_freeze" | "recovery_operation_repaired_before_task_classified" => (0, 0),
            "report_persisted_before_terminal" => (1, 1),
            _ => (1, 0),
        };
        assert_child_event_counts(&root, freeze_attempts, claim_attempts);
        if stage == "accepting_persisted_before_freeze" {
            assert_eq!(
                authenticate_operation_chain(&store, &operation_id).last().unwrap().state(),
                AnalysisOperationState::Accepting
            );
        }

        match stage {
            "accepting_persisted_before_freeze" => {
                assert_eq!(operation["state"], "accepting");
                assert!(!operation["command_sha256"].is_null());
                assert!(operation["frozen_input"].is_null());
                assert!(!store.join("jobs").join(&job_id).exists());
                assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 0);
            }
            "frozen_input_persisted_before_task" => {
                assert_eq!(operation["state"], "accepting");
                assert!(!operation["frozen_input"].is_null());
                assert!(!store.join("jobs").join(&job_id).exists());
            }
            "task_persisted_before_acceptance" => {
                assert_eq!(operation["state"], "accepting");
                assert_eq!(read_record(&store, "jobs", &job_id, 1)["state"], "queued");
            }
            "report_persisted_before_terminal" => {
                assert_eq!(operation["state"], "accepted");
                assert_eq!(read_record(&store, "jobs", &job_id, 2)["state"], "running");
                assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 1);
            }
            "recovery_operation_repaired_before_task_classified" => {
                assert_eq!(operation["state"], "accepted");
                assert_eq!(read_record(&store, "jobs", &job_id, 1)["state"], "queued");
            }
            _ => unreachable!(),
        }
        let before_kill = persisted_material(&store);
        let status = child.kill();
        assert!(!status.success(), "checkpointed child must be terminated");
        assert_eq!(persisted_material(&store), before_kill);

        let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        let operation_history = coordinator.inspect_operation(&operation_id).unwrap();
        let recovered = operation_history.last().unwrap();
        assert!(coordinator.snapshot().unwrap().queued.is_none());
        assert!(coordinator.claim_next(10_000).unwrap().is_none());
        match stage {
            "accepting_persisted_before_freeze" | "frozen_input_persisted_before_task" => {
                assert_eq!(recovered.state(), AnalysisOperationState::Unknown);
                assert!(coordinator.inspect_job_optional(&job_id).unwrap().is_none());
                if stage == "accepting_persisted_before_freeze" {
                    assert_eq!(operation_history.len(), 3);
                    assert_eq!(coordinator.freeze_attempts_for_test(), 0);
                }
            }
            "task_persisted_before_acceptance" | "recovery_operation_repaired_before_task_classified" => {
                assert_eq!(recovered.state(), AnalysisOperationState::Accepted);
                let job = coordinator.inspect_job(&job_id).unwrap();
                assert_eq!(job.last().unwrap().state(), AnalysisJobState::Interrupted);
                assert_eq!(job.len(), 2);
            }
            "report_persisted_before_terminal" => {
                assert_eq!(recovered.state(), AnalysisOperationState::Accepted);
                let job = coordinator.inspect_job(&job_id).unwrap();
                assert_eq!(job.last().unwrap().state(), AnalysisJobState::Unknown);
                assert!(job.last().unwrap().report().is_none());
                assert_eq!(fs::read_dir(store.join("reports")).unwrap().count(), 1);
            }
            _ => unreachable!(),
        }
        drop(coordinator);
        let after_first_reopen = persisted_material(&store);
        for (path, bytes) in &before_kill {
            assert_eq!(after_first_reopen.get(path), Some(bytes));
        }
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert!(reopened.snapshot().unwrap().queued.is_none());
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        assert_eq!(persisted_material(&store), after_first_reopen, "{stage}");
    }
}
