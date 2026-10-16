#[test]
#[ignore = "opt-in frozen core: full two-strategy eight-policy matrix"]
fn two_distinct_strategies_have_replayed_eight_policy_evidence() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::env::set_current_dir(&root).unwrap();
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string("configs/engine.toml").unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let q: ygo_api::planning_v5::PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ash-strategy.request.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let mut r = ygo_api::planning_v5::plan(
        q.clone(),
        engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack.clone(),
    )
    .unwrap();
    std::fs::write(
        "data/runtime/ash-strategy-report.json",
        serde_json::to_vec(&r).unwrap(),
    )
    .unwrap();
    assert_eq!(r.strategies.len(), 2, "{:?}", r.limitations);
    assert_ne!(
        r.strategies[0].first_sensitive,
        r.strategies[1].first_sensitive
    );
    for row in &r.strategies {
        assert_eq!(row.cells.len(), 8);
        for c in &row.cells {
            assert!(c.calls <= 512);
            assert!(
                c.outcome.is_some(),
                "{} {} {}",
                row.first_sensitive,
                c.policy,
                c.detail
            );
        }
    }
    assert_eq!(r.ranking.len(), 2);
    assert!(r.total_calls <= 8192);
    ygo_api::planning_v5::replay(&r, engine.clone(), &store).unwrap();
    r.strategies[0].cells[0]
        .outcome
        .as_mut()
        .unwrap()
        .score
        .main_resources += 1;
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[0]
        .outcome
        .as_mut()
        .unwrap()
        .score
        .main_resources -= 1;
    r.ranking.reverse();
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.ranking.reverse();
    r.strategies[0].cells[1].calls += 1;
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1].calls -= 1;
    let old = r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .state
        .normal_left;
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .state
        .normal_left = 1;
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .state
        .normal_left = old;
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .runtime
        .seed += 1;
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .runtime
        .seed -= 1;
    r.strategies[0].cells[1]
        .comparison
        .as_mut()
        .unwrap()
        .lost_goal_conditions
        .push("forged".into());
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1]
        .comparison
        .as_mut()
        .unwrap()
        .lost_goal_conditions
        .pop();
    let key = "25538345:mill".to_string();
    assert!(r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .state
        .used
        .remove(&key));
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .state
        .used
        .insert(key);
    let d = r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .runtime
        .decisions
        .pop()
        .unwrap();
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1]
        .anchor
        .as_mut()
        .unwrap()
        .runtime
        .decisions
        .push(d);
    let old = r.strategies[0].cells[1].policy.clone();
    r.strategies[0].cells[1].policy = "36426778:search".into();
    assert!(ygo_api::planning_v5::validate_report(&r).is_err());
    r.strategies[0].cells[1].policy = old;
    ygo_api::planning_v5::validate_report(&r).unwrap();
    let mut small = q;
    small.analysis.search.node_budget = 1;
    let limited = ygo_api::planning_v5::plan(
        small,
        engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack,
    )
    .unwrap();
    assert!(limited.ranking.is_empty());
    assert!(limited.total_calls <= 16);
    assert!(limited
        .limitations
        .iter()
        .any(|s| s.contains("budget_exhausted")));
    let proof = ygo_api::planning_v5::replay(&limited, engine, &store).unwrap();
    assert_eq!(proof["matrix_verified"], false);
    assert_eq!(proof["report_evidence_verified"], false);
    std::fs::write(
        "data/runtime/ash-strategy-budget.json",
        serde_json::to_vec(&limited).unwrap(),
    )
    .unwrap();
}
#[test]
fn request_requires_fixed_policies_and_shared_matrix_limit() {
    let q: ygo_api::planning_v5::PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ash-strategy.request.json"
    ))
    .unwrap();
    q.validate().unwrap();
    let mut bad = q.clone();
    bad.total_budget += 1;
    assert!(bad.validate().is_err());
    let mut bad = q;
    bad.policies.pop();
    assert!(bad.validate().is_err());
}
#[test]
fn worst_result_precedes_average_and_unknown_gain_is_not_zero() {
    use ygo_api::planning_v5::Score;
    let low = Score {
        goal: false,
        gains: vec![],
        main_resources: 9,
        verification_decisions: 1,
    };
    let high = Score {
        goal: true,
        gains: vec![],
        main_resources: 1,
        verification_decisions: 20,
    };
    assert!(high > low);
    let unknown = Score {
        goal: true,
        gains: vec![None],
        main_resources: 99,
        verification_decisions: 1,
    };
    let zero = Score {
        goal: true,
        gains: vec![Some(0)],
        main_resources: 1,
        verification_decisions: 10,
    };
    assert!(zero > unknown);
}
