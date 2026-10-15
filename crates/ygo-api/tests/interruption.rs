#[test]
#[ignore = "opt-in frozen engine: actual Ash interruption, recovery and independent replay"]
fn ash_interrupts_scales_and_planner_recovers_from_paid_costs() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::env::set_current_dir(&root).unwrap();
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string("configs/engine.toml").unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let q: ygo_api::planning_v4::PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ash-recovery.request.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let r = ygo_api::planning_v4::plan(
        q,
        engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack,
    )
    .unwrap();
    std::fs::write(
        "data/runtime/ash-recovery-report.json",
        serde_json::to_vec_pretty(&r).unwrap(),
    )
    .unwrap();
    let stopped = r.interrupted.as_ref().expect("actual interrupted prefix");
    assert!(stopped.observation.events.iter().any(|e| e.opcode == 76));
    assert!(stopped.observation.events.iter().any(|e| e.opcode == 50
        && e.fields["code"] == 14558127u32
        && e.fields["to"]["location"] == 16));
    assert!(stopped.observation.events.iter().any(|e| e.opcode == 50
        && e.fields["code"] == 2964201u32
        && e.fields["reason"].as_u64().unwrap_or(0) & 128 != 0));
    assert!(!stopped.observation.events.iter().any(|e| e.opcode == 50
        && e.fields["from"]["player"] == 0
        && e.fields["from"]["location"] == 1
        && e.fields["to"]["location"] == 16));
    assert_eq!(stopped.state.normal_left, 0);
    assert_eq!(
        stopped
            .state
            .cards
            .iter()
            .filter(|c| c.player == 0 && c.code == 2964201 && c.location == 2)
            .count(),
        1
    );
    assert_eq!(
        stopped
            .state
            .cards
            .iter()
            .filter(|c| c.player == 0 && c.code == 2964201 && c.location == 16)
            .count(),
        1
    );
    assert!(stopped.state.used.contains("25538345:mill"));
    let recovery = r.recovery.as_ref().expect("recovery arm");
    assert!(
        !recovery.recommendations.is_empty(),
        "{:?}",
        recovery.failure_summary
    );
    assert!(r.total_calls <= 1536);
    let comparison = r.comparison.as_ref().expect("actual resource comparison");
    assert!(comparison
        .interruption_window_changes
        .iter()
        .any(|c| c.player == 1 && c.code == 14558127 && c.location == 16 && c.delta == 1));
    assert_eq!(comparison.interruption_paid_cost_events.len(), 2);
    ygo_api::planning_v4::replay(&r, engine, &store).unwrap();
    let mut forged = r.clone();
    forged.interrupted.as_mut().unwrap().state.normal_left = 1;
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    forged
        .comparison
        .as_mut()
        .unwrap()
        .interruption_window_changes[0]
        .delta += 1;
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    let a = &mut forged.interrupted.as_mut().unwrap().attempt;
    a.goal_achieved = true;
    a.status = "engine_verified".into();
    a.line_id = Some("forged".into());
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    forged.interrupted.as_mut().unwrap().consumed_steps -= 1;
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    forged.request.max_proposals = 7;
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    let a = forged.recovery.as_mut().unwrap();
    a.request.analysis.search.node_budget = 1024;
    a.analysis.request.search.node_budget = 1024;
    a.analysis.search.budget.node_budget = 1024;
    a.ledger.limit = 1024;
    ygo_api::planning_v3::validate_plan_contract(a)
        .expect("individually valid arm with different budget");
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut unknown = stopped.observation.clone();
    unknown.checkpoint.phase = 512;
    assert!(
        ygo_api::planning_v4::reconstruct(&unknown, &r.baseline.as_ref().unwrap().knowledge)
            .is_err()
    );
    let mut forged = r.clone();
    forged.interrupted.as_mut().unwrap().attempt.predictions[0].reason =
        "fabricated before execution".into();
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let mut forged = r.clone();
    forged.interrupted.as_mut().unwrap().runtime.decisions.pop();
    assert!(ygo_api::planning_v4::validate_report(&forged).is_err());
    let base = r.baseline.as_ref().unwrap();
    let cat = &base.catalog_projection;
    let pack = &base.knowledge;
    // Human-written preparation: summon Scales and Boots, link Cherubini,
    // send Gloves as cost. Scales mill is never activated, so Ash stays in hand.
    let mut state = base.context.as_ref().unwrap().initial.clone();
    let mut manual = vec![];
    for effect in [
        "25538345:normal",
        "36426778:summon",
        "58699500:link",
        "58699500:mill",
    ] {
        let step = ygo_planner::v2::successors(&state, cat, pack)
            .into_iter()
            .find(|s| {
                s.effect_id == effect
                    && (effect != "58699500:mill" || s.costs.iter().any(|c| c.code == 63821877))
            })
            .expect(effect);
        state = step.after.clone();
        manual.push(step);
    }
    let mut runtime = base.context.as_ref().unwrap().runtime.clone();
    runtime.interruption.as_mut().unwrap().policy = "ash_scales_once".into();
    let adapter = ygo_engine_adapter::ProcessEngineAdapter::new(runtime.engine.clone());
    let output = ygo_planner::v2::execute_general(
        &adapter,
        &runtime,
        ygo_planner::v2::Proposals {
            plans: vec![ygo_planner::v2::Proposal {
                id: "manual-cherubini-negative".into(),
                steps: manual,
                goal_predicted: false,
            }],
            expansions: 0,
            termination: "manual_case".into(),
            coverage_gaps: vec![],
        },
        &r.request.analysis.search,
        &Default::default(),
        pack,
        true,
        |_| true,
    )
    .unwrap();
    let observed = output.attempts[0].observation.as_ref().unwrap();
    assert!(
        output.attempts[0].goal_achieved,
        "{:?}",
        output.attempts[0].discrepancies
    );
    assert!(observed
        .checkpoint
        .cards
        .iter()
        .any(|c| c.player == 1 && c.code == 14558127 && c.location == 2));
    let chained = observed
        .events
        .iter()
        .find(|e| e.opcode == 70 && e.fields["code"] == 58699500u32)
        .unwrap();
    let solved = observed
        .events
        .iter()
        .find(|e| {
            e.sequence > chained.sequence
                && e.opcode == 73
                && e.fields["chain"] == chained.fields["chain"]
        })
        .unwrap();
    for e in observed
        .events
        .iter()
        .filter(|e| e.sequence > chained.sequence && e.sequence < solved.sequence)
    {
        if let Ok(ms) = ygo_engine_adapter::prompt_metadata(e.sequence, &e.raw) {
            assert!(!ms.iter().any(|m| m
                .source
                .as_ref()
                .is_some_and(|s| s.player == 1 && s.code == 14558127)));
        }
    }
    std::fs::write(
        "data/runtime/ash-cherubini-negative.json",
        serde_json::to_vec_pretty(&observed).unwrap(),
    )
    .unwrap();
    // No activation point: an initial hand fact goal must not manufacture an interruption.
    let mut small = r.request.clone();
    small.goal.expr = serde_json::from_value(
        serde_json::json!({"op":"count","filter":{"codes":[2964201],"locations":[2]},"min":1}),
    )
    .unwrap();
    small.max_proposals = 1;
    let not_reached = ygo_api::planning_v4::plan(
        small.clone(),
        runtime.engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack.clone(),
    )
    .unwrap();
    assert!(not_reached.interrupted.is_none());
    assert!(not_reached
        .failures
        .iter()
        .any(|f| f.category == ygo_api::planning_v4::FailureClass::ResponsePointNotReached));
    small.analysis.search.node_budget = 1;
    let limited = ygo_api::planning_v4::plan(
        small,
        runtime.engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack.clone(),
    )
    .unwrap();
    assert!(limited.total_calls <= 3);
    assert!(limited
        .failures
        .iter()
        .any(|f| f.category == ygo_api::planning_v4::FailureClass::BudgetExhausted));
}

#[test]
fn recovery_request_rejects_uncontrolled_resources_and_budget() {
    let q: ygo_api::planning_v4::PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ash-recovery.request.json"
    ))
    .unwrap();
    q.validate().unwrap();
    let mut bad = q.clone();
    bad.interruption.occurrence = 2;
    assert!(bad.validate().is_err());
    let mut bad = q.clone();
    bad.interruption.opponent_hand.clear();
    assert!(bad.validate().is_err());
    let mut bad = q.clone();
    bad.analysis.search.node_budget = 513;
    assert!(bad.validate().is_err());
    let mut bad = q;
    bad.interruption.effect_id = "58699500:mill".into();
    assert!(bad.validate().is_err());
}

#[test]
#[ignore = "opt-in: fresh Ash report and human-authored recovery recipe"]
fn manual_recovery_recipe_reaches_rusty_and_set_fog_after_real_ash() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::env::set_current_dir(&root).unwrap();
    let report: ygo_api::planning_v4::PlanReport =
        serde_json::from_slice(&std::fs::read("data/runtime/ash-recovery-report.json").unwrap())
            .unwrap();
    ygo_api::planning_v4::validate_report(&report).unwrap();
    let base = report.baseline.as_ref().unwrap();
    let anchor = report.interrupted.as_ref().unwrap();
    let mut state = anchor.state.clone();
    let mut steps = vec![];
    // Authored independently of proposal search; every preparation/selection still runs in core.
    for effect in [
        "36426778:summon",
        "58699500:link",
        "58699500:mill",
        "63821877:mill",
        "25538345:revive",
        "36426778:search",
        "26692769:link",
        "25542642:set",
    ] {
        let step = ygo_planner::v2::successors(&state, &base.catalog_projection, &base.knowledge)
            .into_iter()
            .find(|s| {
                s.effect_id == effect
                    && (effect != "58699500:mill" || s.costs.iter().any(|c| c.code == 63821877))
                    && (effect != "63821877:mill" || s.targets.iter().any(|c| c.code == 90432163))
                    && (effect != "36426778:search" || s.targets.iter().any(|c| c.code == 25542642))
            })
            .expect(effect);
        state = step.after.clone();
        steps.push(step);
    }
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string("configs/engine.toml").unwrap(),
    )
    .unwrap();
    let mut runtime = anchor.runtime.clone();
    runtime.engine = engine.clone();
    let adapter = ygo_engine_adapter::ProcessEngineAdapter::new(engine);
    let result = ygo_planner::v2::execute_general(
        &adapter,
        &runtime,
        ygo_planner::v2::Proposals {
            plans: vec![ygo_planner::v2::Proposal {
                id: "human-ash-recovery-v1".into(),
                steps,
                goal_predicted: true,
            }],
            expansions: 0,
            termination: "human_recipe".into(),
            coverage_gaps: vec![],
        },
        &report.request.analysis.search,
        &Default::default(),
        &base.knowledge,
        true,
        |r| ygo_planner::v2::checkpoint_goal(&r.checkpoint),
    )
    .unwrap();
    assert_eq!(
        result.search.lines.len(),
        1,
        "{:?}",
        result.attempts[0].discrepancies
    );
    assert!(result.search.lines[0].replay_verified);
    assert!(result.search.stats.engine_calls <= 512);
    let observation = &result.search.lines[0].result;
    assert!(observation.events.iter().any(|e| e.opcode == 76));
    assert!(observation
        .checkpoint
        .cards
        .iter()
        .any(|c| c.player == 0 && c.location == 4 && c.code == 26692769));
    assert!(observation
        .checkpoint
        .cards
        .iter()
        .any(|c| c.player == 0 && c.location == 8 && c.code == 25542642 && c.position & 10 != 0));
    std::fs::write(
        "data/runtime/ash-manual-recovery.json",
        serde_json::to_vec_pretty(&result).unwrap(),
    )
    .unwrap();
}
