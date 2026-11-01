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
    let child_output = fs::File::create(root.join("child-output.log")).unwrap();
    let mut child = ChildGuard(
        Command::new(std::env::current_exe().unwrap())
            .args(["--exact", CRASH_TEST, "--nocapture"])
            .env(CHILD_STAGE, stage)
            .env(CHILD_ROOT, root)
            .env(CHILD_MARKER, &marker)
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

    if stage == "report_persisted_before_terminal" {
        let ticket = coordinator.claim_next(102).unwrap().unwrap();
        let bytes = report_bytes(ticket.input(), ticket.record().input().scoring.clone());
        let _ = coordinator.publish_report(&ticket, &bytes, 103);
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

#[test]
fn h3_2b_cross_chain_windows_recover_after_process_kill() {
    if let Some(stage) = std::env::var_os(CHILD_STAGE) {
        let root = std::path::PathBuf::from(std::env::var_os(CHILD_ROOT).unwrap());
        let stage = stage.to_string_lossy();
        if stage == "recovery_operation_repaired_before_task_classified" {
            child_recovery_checkpoint(&root);
        }
        child_submit_to_checkpoint(&root, &stage);
    }

    let stages = [
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
        assert_eq!(operations.len(), 1);
        let operation_id = operations[0].clone();
        let operation_revision = if matches!(
            stage,
            "frozen_input_persisted_before_task" | "task_persisted_before_acceptance"
        ) {
            3
        } else {
            4
        };
        let operation = read_record(&store, "operations", &operation_id, operation_revision);
        let job_id = operation["job_id"].as_str().unwrap().to_owned();

        match stage {
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
        let status = child.kill();
        assert!(!status.success(), "checkpointed child must be terminated");

        let coordinator = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        let operation_history = coordinator.inspect_operation(&operation_id).unwrap();
        let recovered = operation_history.last().unwrap();
        assert!(coordinator.snapshot().unwrap().queued.is_none());
        assert!(coordinator.claim_next(10_000).unwrap().is_none());
        match stage {
            "frozen_input_persisted_before_task" => {
                assert_eq!(recovered.state(), AnalysisOperationState::Unknown);
                assert!(coordinator.inspect_job_optional(&job_id).unwrap().is_none());
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
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert!(reopened.snapshot().unwrap().queued.is_none());
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        assert_eq!(persisted_material(&store), after_first_reopen, "{stage}");
    }
}
