//! The planner is never given the human preparation recipes.
use ygo_engine_adapter::*;
use ygo_goal::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;

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
    for variant in 0..6 {
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
            _ => forged.choices[0].instance_map.clear(),
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
