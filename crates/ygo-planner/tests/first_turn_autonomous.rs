//! The planner is never given the human preparation recipes.
use ygo_engine_adapter::*;
use ygo_goal::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;

#[test]
#[ignore = "opt-in: real prefixes and a labelled injected worker failure after a material cost"]
fn an_injected_failure_after_material_payment_keeps_a_replayable_pending_prefix() {
    use std::sync::atomic::{AtomicUsize, Ordering};
    struct StopAt {
        inner: ProcessEngineAdapter,
        count: AtomicUsize,
        at: usize,
    }
    impl EngineAdapter for StopAt {
        fn doctor(&self) -> DoctorReport {
            panic!("no uncharged probe")
        }
        fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            if self.count.fetch_add(1, Ordering::SeqCst) == self.at {
                return Err(WorkerError::new(
                    "injected_worker_exit",
                    "fault_injection",
                    "controlled worker loss",
                ));
            }
            self.inner.run(q)
        }
    }
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = std::path::PathBuf::from(std::env::var("YGO_PILOT_REPORT_DIR").unwrap());
    let saved: PartialExecution =
        serde_json::from_slice(&std::fs::read(dir.join("pass.report.json")).unwrap()).unwrap();
    let plans: PartialPlans =
        serde_json::from_slice(&std::fs::read(dir.join("frozen-forecasts.json")).unwrap()).unwrap();
    let plan = plans.plans.iter().find(|p| p.id == saved.plan_id).unwrap();
    let step = plan
        .steps
        .iter()
        .position(|s| s.rule_id == "78449284:deck_special")
        .unwrap();
    // Freeze the fault location before executing the experiment: the first
    // selection after the actual host has paid one of its two materials.
    let at = saved
        .choices
        .iter()
        .position(|c| {
            c.step == Some(step)
                && c.public.visible.cards.iter().any(|card| {
                    card.code == 78449284 && card.location == 4 && card.overlay.len() == 1
                })
                && saved.result.events[c.prompt as usize - 1].opcode == 15
        })
        .unwrap();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let cat = ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"))
        .catalog(&saved.start_request.versions.catalog)
        .unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let output = dir.join(format!(
        "paid-cost-fault-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&output).unwrap();
    let j = CallJournal::open(
        output.join("calls.jsonl"),
        "fault-injection-with-native-prefixes",
        &pack.id(),
        512,
    )
    .unwrap();
    let q = saved.start_request;
    let initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        j.clone(),
        CallPurpose::Execution,
    )
    .run(&q)
    .unwrap();
    let report = execute_partial_v2_with_backend(
        &q,
        &initial,
        &[QueryWitness::capture(&initial).unwrap()],
        plan,
        &cat.data,
        &pack,
        &goal,
        j.clone(),
        StopAt {
            inner: ProcessEngineAdapter::new(q.engine.clone()),
            count: AtomicUsize::new(0),
            at,
        },
    )
    .unwrap();
    std::fs::write(
        output.join("report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    assert_eq!(report.faults[0].code, "injected_worker_exit");
    assert_eq!(report.failure.as_ref().unwrap().step, step);
    assert!(!report.verified());
    assert!(report.audit_failure.is_none());
    assert!(report.last_audited_prefix.is_some());
    assert_eq!(report.observed_terminal, Some(false));
    let last = report.last_result.as_ref().unwrap();
    assert!(last
        .checkpoint
        .cards
        .iter()
        .any(|c| c.code == 78449284 && c.location == 4 && c.overlay.len() == 1));
    assert!(last.events.iter().any(|e| e.opcode == 50
        && e.fields["from"]["location"] == 132
        && e.fields["to"]["location"] == 16
        && e.raw.len() >= 4
        && u32::from_le_bytes(e.raw[e.raw.len() - 4..].try_into().unwrap()) & 0x80 != 0));
    validate_partial_execution_v2(&report, plan, &cat.data, &pack, &goal, &j).unwrap();
    let mut forged: PartialExecutionV2 =
        serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
    forged
        .last_result
        .as_mut()
        .unwrap()
        .checkpoint
        .cards
        .iter_mut()
        .find(|c| c.code == 78449284 && c.location == 4)
        .unwrap()
        .overlay
        .push(85257384);
    assert!(validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &j).is_err());
    forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
    forged.failure.as_mut().unwrap().kind = PartialFailureKind::OriginalPlanBlocked;
    assert!(validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &j).is_err());
    std::fs::write(
        output.join("experiment.json"),
        serde_json::to_vec_pretty(&serde_json::json!({
        "kind":"fault_injection_with_native_prefixes", "scope":"not_rule_qualification_or_matrix",
        "injected_debits":1,"paid_total":j.stats().unwrap().consumed,
        "native_adapter_attempts":j.stats().unwrap().consumed-1,
        "report_sha256":ygo_knowledge::hash(&serde_json::to_vec(&report).unwrap())}))
        .unwrap(),
    )
    .unwrap();
    println!(
        "paid-cost injected failure, charged{}, {}",
        j.stats().unwrap().consumed,
        output.display()
    );
}

#[test]
#[ignore = "opt-in: real initial state and worker-start failures; uses YGO_PILOT_REPORT_DIR"]
fn a_worker_failure_returns_a_v2_diagnostic_instead_of_losing_the_prefix() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = std::path::PathBuf::from(std::env::var("YGO_PILOT_REPORT_DIR").unwrap());
    let saved: PartialExecution =
        serde_json::from_slice(&std::fs::read(dir.join("pass.report.json")).unwrap()).unwrap();
    let plans: PartialPlans =
        serde_json::from_slice(&std::fs::read(dir.join("frozen-forecasts.json")).unwrap()).unwrap();
    let plan = plans.plans.iter().find(|p| p.id == saved.plan_id).unwrap();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let cat = ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"))
        .catalog(&saved.start_request.versions.catalog)
        .unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let output = dir.join(format!(
        "worker-failure-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&output).unwrap();
    let j = CallJournal::open(
        output.join("calls.jsonl"),
        "worker-failure",
        &pack.id(),
        512,
    )
    .unwrap();
    let mut q = saved.start_request;
    let initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        j.clone(),
        CallPurpose::Execution,
    )
    .run(&q)
    .unwrap();
    let queries = vec![QueryWitness::capture(&initial).unwrap()];
    let audit_engine = q.engine.clone();
    q.engine.worker_path = output.join("missing-worker.exe");
    let mut report = execute_partial_v2(
        &q,
        &initial,
        &queries,
        plan,
        &cat.data,
        &pack,
        &goal,
        j.clone(),
    )
    .unwrap();
    assert_eq!(report.schema_version, 2);
    assert!(report.audit_failure.is_some());
    assert!(report.last_audited_prefix.is_none());
    assert_eq!(report.last_result.as_ref().unwrap().events, initial.events);
    assert!(!report.verified());
    assert_eq!(j.stats().unwrap().consumed, 3);
    assert_eq!(j.stats().unwrap().reserved, 0);
    validate_partial_execution_v2(&report, plan, &cat.data, &pack, &goal, &j).unwrap();
    let mut forged: PartialExecutionV2 =
        serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
    forged.audit_failure.as_mut().unwrap().completed_witnesses = 1;
    assert!(validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &j).is_err());
    forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
    forged.faults[0].stage = ExecutionStage::EndPhase;
    assert!(validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &j).is_err());
    forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
    forged.start_call = usize::MAX;
    assert!(validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &j).is_err());
    std::fs::write(
        output.join("report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    println!("worker failure retained; calls3; {}", output.display());
    let audit = CallJournal::open(
        output.join("prefix-audit.jsonl"),
        "prefix-audit",
        &pack.id(),
        512,
    )
    .unwrap();
    let calls = replay_partial_execution_v2_with_engine(
        &mut report,
        plan,
        &cat.data,
        &pack,
        &goal,
        &j,
        audit.clone(),
        &audit_engine,
    )
    .unwrap();
    assert_eq!(calls, vec![1, 2]);
    assert_eq!(audit.stats().unwrap().consumed, 2);
    assert_eq!(j.stats().unwrap().consumed, 3);
    assert!(
        !report.verified(),
        "replaying a retained prefix cannot erase the failed execution"
    );
    std::fs::write(output.join("prefix-audit-reference.json"), serde_json::to_vec_pretty(
        &serde_json::json!({"source_report_sha256":ygo_knowledge::hash(&serde_json::to_vec(&report).unwrap()),
            "audit_calls":calls, "journal":"prefix-audit.jsonl"})).unwrap()).unwrap();
    let start_journal = CallJournal::open(
        output.join("initial-failure.jsonl"),
        "initial-failure",
        &pack.id(),
        1,
    )
    .unwrap();
    let report =
        start_partial_v2(&q, plan, &cat.data, &pack, &goal, start_journal.clone()).unwrap();
    assert!(report.last_result.is_none());
    assert!(report.last_audited_prefix.is_none());
    assert_eq!(report.observed_terminal, None);
    assert!(report.observed_goal.is_none());
    assert_eq!(report.faults[0].call, Some(1));
    assert_eq!(start_journal.stats().unwrap().consumed, 1);
    validate_partial_execution_v2(&report, plan, &cat.data, &pack, &goal, &start_journal).unwrap();
    std::fs::write(
        output.join("initial-failure.report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    let denied =
        start_partial_v2(&q, plan, &cat.data, &pack, &goal, start_journal.clone()).unwrap();
    assert!(denied.last_result.is_none());
    assert_eq!(denied.calls, 0);
    assert_eq!(denied.faults[0].call, None);
    assert_eq!(
        denied.failure.as_ref().unwrap().kind,
        PartialFailureKind::BudgetExhausted
    );
    assert_eq!(start_journal.stats().unwrap().consumed, 1);
    validate_partial_execution_v2(&denied, plan, &cat.data, &pack, &goal, &start_journal).unwrap();
    let mut forged: PartialExecutionV2 =
        serde_json::from_value(serde_json::to_value(&denied).unwrap()).unwrap();
    forged.initial_attempt_checkpoint = None;
    assert!(
        validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &start_journal)
            .is_err()
    );
    forged = serde_json::from_value(serde_json::to_value(&denied).unwrap()).unwrap();
    forged.faults[0].call = Some(2);
    assert!(
        validate_partial_execution_v2(&forged, plan, &cat.data, &pack, &goal, &start_journal)
            .is_err()
    );
    std::fs::write(
        output.join("initial-budget.report.json"),
        serde_json::to_vec_pretty(&denied).unwrap(),
    )
    .unwrap();
}

#[test]
#[ignore = "opt-in: real 1/12/30/70/71/72/73-call caps with independent prefix audits"]
fn interrupted_native_operations_keep_the_latest_result_and_reserved_replay_budget() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = std::path::PathBuf::from(std::env::var("YGO_PILOT_REPORT_DIR").unwrap());
    let saved: PartialExecution =
        serde_json::from_slice(&std::fs::read(dir.join("pass.report.json")).unwrap()).unwrap();
    let plans: PartialPlans =
        serde_json::from_slice(&std::fs::read(dir.join("frozen-forecasts.json")).unwrap()).unwrap();
    let plan = plans.plans.iter().find(|p| p.id == saved.plan_id).unwrap();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let cat = ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"))
        .catalog(&saved.start_request.versions.catalog)
        .unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let output = dir.join(format!(
        "budget-boundaries-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&output).unwrap();
    for cap in [1, 12, 30, 70, 71, 72, 73] {
        let j = CallJournal::open(
            output.join(format!("{cap}.jsonl")),
            "boundary",
            &pack.id(),
            cap,
        )
        .unwrap();
        let mut report = start_partial_v2(
            &saved.start_request,
            plan,
            &cat.data,
            &pack,
            &goal,
            j.clone(),
        )
        .unwrap();
        std::fs::write(
            output.join(format!("{cap}.report.json")),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .unwrap();
        if cap == 73 {
            assert!(report.failure.is_none());
            assert!(report.verified());
        } else {
            assert_eq!(
                report.failure.as_ref().unwrap().kind,
                PartialFailureKind::BudgetExhausted
            );
            assert!(!report.verified());
        }
        assert_eq!(j.stats().unwrap().reserved, 0);
        assert!(j.stats().unwrap().consumed <= cap);
        let actual = report.last_result.as_ref().unwrap();
        if cap == 1 {
            assert!(report.audit_failure.is_some());
            assert!(report.last_audited_prefix.is_none());
            assert!(report.choices.is_empty());
        } else if cap != 73 {
            assert!(report.audit_failure.is_none());
            assert_eq!(
                report.last_audited_prefix.as_ref().unwrap().result.events,
                actual.events
            );
            let pending = report.pending_choice.as_ref().unwrap();
            assert_eq!(pending.prompt, actual.prompt.as_ref().unwrap().id);
            assert_eq!(
                pending.before_call,
                (report.start_call + report.choices.len() + 1) as u64
            );
        }
        if cap != 1 {
            validate_partial_execution_v2(&report, plan, &cat.data, &pack, &goal, &j).unwrap();
            let mut imported: PartialExecutionV2 =
                serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
            assert!(!imported.verified(), "JSON must not grant a native receipt");
            validate_partial_execution_v2(&imported, plan, &cat.data, &pack, &goal, &j).unwrap();
            imported.last_audited_prefix.as_mut().unwrap().witness_call += 1;
            assert!(
                validate_partial_execution_v2(&imported, plan, &cat.data, &pack, &goal, &j)
                    .is_err()
            );
            if cap != 73 {
                let mut imported: PartialExecutionV2 =
                    serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
                imported.faults[0].stage = ExecutionStage::Cleanup;
                assert!(validate_partial_execution_v2(
                    &imported, plan, &cat.data, &pack, &goal, &j
                )
                .is_err());
            }
        }
        println!(
            "cap{cap}:calls{}, step{:?}, opcode{:?}",
            j.stats().unwrap().consumed,
            report.failure.as_ref().map(|f| f.step),
            actual.prompt.as_ref().map(|p| p.opcode)
        );
        std::fs::write(
            output.join(format!("{cap}.report.json")),
            serde_json::to_vec_pretty(&report).unwrap(),
        )
        .unwrap();
        report.plan_id.push_str("forged");
        assert!(
            !report.verified(),
            "mutating a returned report must invalidate its runtime seal"
        );
    }
}

#[test]
#[ignore = "opt-in: real 4-call truncation cap; uses saved forecasts via YGO_PILOT_REPORT_DIR"]
fn a_tiny_native_budget_retains_the_audited_prefix_without_claiming_an_executed_choice() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = std::path::PathBuf::from(std::env::var("YGO_PILOT_REPORT_DIR").unwrap());
    let saved: PartialExecution =
        serde_json::from_slice(&std::fs::read(dir.join("pass.report.json")).unwrap()).unwrap();
    let plans: PartialPlans =
        serde_json::from_slice(&std::fs::read(dir.join("frozen-forecasts.json")).unwrap()).unwrap();
    let plan = plans.plans.iter().find(|p| p.id == saved.plan_id).unwrap();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let cat = store
        .catalog(&saved.start_request.versions.catalog)
        .unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let output_dir = dir.join(format!(
        "budget-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::create_dir_all(&output_dir).unwrap();
    let journal = CallJournal::open(
        output_dir.join("budget.jsonl"),
        "pilot-budget4",
        &pack.id(),
        4,
    )
    .unwrap();
    let q = saved.start_request;
    let initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::Execution,
    )
    .run(&q)
    .unwrap();
    let queries = vec![QueryWitness::capture(&initial).unwrap()];
    let report = execute_partial(
        &q,
        &initial,
        &queries,
        plan,
        &cat.data,
        &pack,
        &goal,
        journal.clone(),
    )
    .unwrap();
    std::fs::write(
        output_dir.join("report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    assert_eq!(
        report.failure.as_ref().unwrap().kind,
        PartialFailureKind::BudgetExhausted
    );
    assert!(report.pending_choice.is_some());
    assert!(report.choices.is_empty());
    assert!(report.result.resolved_decisions.is_empty());
    assert!(!report.terminal);
    assert_eq!(report.audit_calls.len(), 2);
    assert_eq!(journal.stats().unwrap().consumed, 3);
    validate_partial_execution(&report, plan, &cat.data, &pack, &goal, &journal).unwrap();
    println!("budget prefix3/4 calls; evidence={}", output_dir.display());
}

#[test]
#[ignore = "opt-in: local persisted native reports; no engine call, requires YGO_PILOT_REPORT_DIR"]
fn saved_local_reports_reject_relabelled_failures_and_anchor_or_resource_tampering() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let dir = std::path::PathBuf::from(std::env::var("YGO_PILOT_REPORT_DIR").unwrap());
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let cat = store
        .catalog(active["catalog_id"].as_str().unwrap())
        .unwrap();
    let frozen: PartialPlans =
        serde_json::from_slice(&std::fs::read(dir.join("frozen-forecasts.json")).unwrap()).unwrap();
    let plan = frozen
        .plans
        .iter()
        .find(|p| p.first_sensitive.as_deref() == Some("78449284:deck_special"))
        .unwrap();
    let report: PartialExecution =
        serde_json::from_slice(&std::fs::read(dir.join("blocked.report.json")).unwrap()).unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let journal = CallJournal::open(
        dir.join("blocked.jsonl"),
        "partial-autonomous-blocked",
        &pack.id(),
        512,
    )
    .unwrap();
    validate_partial_execution(&report, plan, &cat.data, &pack, &goal, &journal).unwrap();
    let spent = journal.stats().unwrap().consumed;
    for variant in 0..8 {
        let mut forged = report.clone();
        match variant {
            0 => forged.failure.as_mut().unwrap().kind = PartialFailureKind::CoverageGap,
            1 => forged.failure.as_mut().unwrap().step -= 1,
            2 => forged.interruption.as_mut().unwrap().state.normal_remaining = Some(1),
            3 => forged.predictions[4].differences.clear(),
            4 => forged.predictions[0].candidates[0]
                .cost_change
                .insert(2, 99)
                .map(|_| ())
                .unwrap_or(()),
            5 => forged.choices[0].instance_map.clear(),
            6 => forged.start_call = usize::MAX,
            _ => forged.calls = usize::MAX,
        }
        assert!(
            validate_partial_execution(&forged, plan, &cat.data, &pack, &goal, &journal).is_err(),
            "tamper variant={variant}"
        );
    }
    assert_eq!(journal.stats().unwrap().consumed, spent);
}
#[test]
#[ignore = "opt-in: autonomous partial-model pilot through native engine; charged, not formal v6"]
fn autonomous_generated_scythe_forecast_reaches_the_goal_and_recovers_after_ash() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let cat = store
        .catalog(active["catalog_id"].as_str().unwrap())
        .unwrap();
    let banlist = store
        .banlist(active["banlist_id"].as_str().unwrap())
        .unwrap();
    let portable: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let mut q: RunDuelRequest =
        serde_json::from_value(portable["cases"][0]["runtime_request"].clone()).unwrap();
    q.engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    q.opening_hand = [46072770, 99745551, 83566725, 25538345, 44088353]
        .into_iter()
        .map(ygo_domain::CardId)
        .collect();
    q.decisions.clear();
    q.interruption.as_mut().unwrap().policy = "pass".into();
    q.interruption.as_mut().unwrap().effect_id = "78449284:deck_special".into();
    assert!(ygo_domain::validate_catalog_deck(&q.deck, &banlist.data, &cat.data).is_legal());
    pack.validate_sources(q.engine.catalog_path.parent().unwrap())
        .unwrap();
    let goal:Goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = root.join(format!(
        "data/runtime/tournament-2026/pilot-autonomous/{stamp}"
    ));
    std::fs::create_dir_all(&dir).unwrap();
    let journal = CallJournal::open(
        dir.join("pass.jsonl"),
        "partial-autonomous-pass",
        &pack.id(),
        512,
    )
    .unwrap();
    let adapter = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::Execution,
    );
    let initial = adapter.run(&q).unwrap();
    let queries = vec![QueryWitness::capture(&initial).unwrap()];
    let state = actual_state(&initial, &queries, &cat.data, &pack).unwrap();
    let plans =
        propose_partial(&state.state, &cat.data, &pack, &goal, &Default::default()).unwrap();
    std::fs::write(
        dir.join("frozen-forecasts.json"),
        serde_json::to_vec_pretty(&plans).unwrap(),
    )
    .unwrap();
    for p in &plans.plans {
        println!(
            "{} {:?} resources={} steps={}",
            p.id,
            p.first_sensitive,
            p.predicted_resources,
            p.steps.len()
        );
    }
    // This directed vertical experiment uses a generated candidate reaching the
    // explicitly requested Scythe response point. No manual route is supplied.
    let plan = plans
        .plans
        .iter()
        .find(|p| p.first_sensitive.as_deref() == Some("78449284:deck_special"))
        .expect("bounded discovery did not retain the directed Scythe branch");
    let output = execute_partial(
        &q,
        &initial,
        &queries,
        plan,
        &cat.data,
        &pack,
        &goal,
        journal.clone(),
    )
    .unwrap();
    std::fs::write(
        dir.join("pass.report.json"),
        serde_json::to_vec_pretty(&output).unwrap(),
    )
    .unwrap();
    println!(
        "native calls={} report={}",
        journal.stats().unwrap().consumed,
        dir.display()
    );
    assert!(output.failure.is_none(), "{:?}", output.failure);
    assert!(output.terminal);
    assert_eq!(output.goal.result, ygo_goal::Truth::Yes);
    assert!(!output.audit_calls.is_empty());
    validate_partial_execution(&output, plan, &cat.data, &pack, &goal, &journal).unwrap();
    let spent = journal.stats().unwrap().consumed;
    let mut forged = output.clone();
    forged.choices[0].before_call += 1;
    assert!(validate_partial_execution(&forged, plan, &cat.data, &pack, &goal, &journal).is_err());
    forged = output.clone();
    forged.predictions[0].goal_before.result = Truth::Yes;
    assert!(validate_partial_execution(&forged, plan, &cat.data, &pack, &goal, &journal).is_err());
    forged = output.clone();
    forged.calls += 1;
    assert!(validate_partial_execution(&forged, plan, &cat.data, &pack, &goal, &journal).is_err());
    forged = output.clone();
    forged.goal.result = Truth::No;
    assert!(validate_partial_execution(&forged, plan, &cat.data, &pack, &goal, &journal).is_err());
    assert_eq!(journal.stats().unwrap().consumed, spent);
    let mut blocked_request = q.clone();
    blocked_request.interruption.as_mut().unwrap().policy = "ash_effect_once".into();
    let blocked_journal = CallJournal::open(
        dir.join("blocked.jsonl"),
        "partial-autonomous-blocked",
        &pack.id(),
        512,
    )
    .unwrap();
    let blocked_initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        blocked_journal.clone(),
        CallPurpose::Execution,
    )
    .run(&blocked_request)
    .unwrap();
    let blocked_queries = vec![QueryWitness::capture(&blocked_initial).unwrap()];
    let blocked = execute_partial(
        &blocked_request,
        &blocked_initial,
        &blocked_queries,
        plan,
        &cat.data,
        &pack,
        &goal,
        blocked_journal.clone(),
    )
    .unwrap();
    std::fs::write(
        dir.join("blocked.report.json"),
        serde_json::to_vec_pretty(&blocked).unwrap(),
    )
    .unwrap();
    validate_partial_execution(&blocked, plan, &cat.data, &pack, &goal, &blocked_journal).unwrap();
    let anchor = blocked
        .interruption
        .as_ref()
        .expect("actual closed Ash anchor");
    assert_eq!(
        blocked.failure.as_ref().unwrap().kind,
        PartialFailureKind::OriginalPlanBlocked
    );
    assert!(blocked.failure.as_ref().unwrap().step > anchor.step);
    assert!(!blocked.terminal);
    assert!(anchor.state.pending.is_empty());
    assert_eq!(anchor.state.normal_remaining, Some(0));
    assert!(!anchor
        .state
        .cards
        .iter()
        .any(|c| c.card.code == 88544390 && c.card.location == 4));
    let before_ash = blocked
        .result
        .events
        .iter()
        .find(|e| e.opcode == 70 && e.fields["player"] == 1)
        .unwrap()
        .sequence;
    let own_prefix = |r: &DuelResult| {
        r.resolved_decisions
            .iter()
            .filter(|d| d.player == 0 && d.prompt_id < before_ash)
            .cloned()
            .collect::<Vec<_>>()
    };
    assert_eq!(own_prefix(&output.result), own_prefix(&blocked.result));

    let recovery_journal = CallJournal::open(
        dir.join("recovery.jsonl"),
        "partial-autonomous-recovery",
        &pack.id(),
        512,
    )
    .unwrap();
    let replayed_anchor = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        recovery_journal.clone(),
        CallPurpose::Execution,
    )
    .run(&anchor.request)
    .unwrap();
    assert_eq!(replayed_anchor.events, anchor.result.events);
    assert_eq!(replayed_anchor.checkpoint, anchor.result.checkpoint);
    let actual = actual_state(&replayed_anchor, &anchor.queries, &cat.data, &pack).unwrap();
    assert_eq!(
        serde_json::to_value(&actual.state).unwrap(),
        serde_json::to_value(&anchor.state).unwrap()
    );
    let limits = SearchLimits {
        steps: 64 - anchor.semantic_steps,
        ..Default::default()
    };
    let alternatives = propose_partial(&actual.state, &cat.data, &pack, &goal, &limits).unwrap();
    std::fs::write(
        dir.join("recovery-forecasts.json"),
        serde_json::to_vec_pretty(&alternatives).unwrap(),
    )
    .unwrap();
    let alternative = alternatives
        .plans
        .first()
        .expect("bounded autonomous recovery");
    let recovered = execute_partial(
        &anchor.request,
        &replayed_anchor,
        &anchor.queries,
        alternative,
        &cat.data,
        &pack,
        &goal,
        recovery_journal.clone(),
    )
    .unwrap();
    std::fs::write(
        dir.join("recovery.report.json"),
        serde_json::to_vec_pretty(&recovered).unwrap(),
    )
    .unwrap();
    assert!(recovered.failure.is_none(), "{:?}", recovered.failure);
    assert!(recovered.terminal);
    assert_eq!(recovered.goal.result, Truth::Yes);
    assert!(recovered
        .result
        .resolved_decisions
        .starts_with(&anchor.result.resolved_decisions));
    validate_partial_execution(
        &recovered,
        alternative,
        &cat.data,
        &pack,
        &goal,
        &recovery_journal,
    )
    .unwrap();
    let costs = [
        journal.stats().unwrap().consumed,
        blocked_journal.stats().unwrap().consumed,
        recovery_journal.stats().unwrap().consumed,
    ];
    println!(
        "three-group calls={costs:?}; total={}",
        costs.iter().sum::<usize>()
    );
    assert!(costs.iter().all(|n| *n <= 512));
    assert!(costs.iter().sum::<usize>() <= 1536);
}
