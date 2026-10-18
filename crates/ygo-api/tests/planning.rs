use ygo_api::planning::*;
#[test]
fn request_limits_and_goal_are_explicit() {
    let mut q: PlanRequest =
        serde_json::from_str(include_str!("../../../tests/fixtures/phantom.request.json")).unwrap();
    assert!(q.validate().is_ok());
    q.max_steps = 33;
    assert!(q.validate().is_err());
    q.max_steps = 32;
    q.goal = "win_probability".into();
    assert!(q.validate().is_err());
}
#[test]
#[ignore = "opt-in: local frozen assets"]
fn planning_report_rejects_edited_knowledge_and_posthoc_reasons() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let q: PlanRequest =
        serde_json::from_str(include_str!("../../../tests/fixtures/phantom.request.json")).unwrap();
    let mut q = q;
    q.max_proposals = 2;
    let r = plan(
        q,
        engine,
        &store,
        pointer["catalog_id"].as_str().unwrap(),
        &ygo_search::combo::ScoringConfig::default(),
        ygo_knowledge::KnowledgePack::builtin().unwrap(),
    )
    .unwrap();
    assert!(validate_plan_contract(&r).is_ok());
    assert!(!r.analysis.search.lines.is_empty());
    let mut invalid = r.clone();
    invalid.knowledge_id = "edited".into();
    assert!(validate_plan_contract(&invalid).is_err());
    let mut invalid = r.clone();
    let proposal = invalid
        .proposals
        .plans
        .iter()
        .find(|p| p.id == invalid.attempts[0].proposal_id)
        .unwrap()
        .clone();
    let prediction = &mut invalid.attempts[0].predictions[0];
    prediction.semantic_step = 2;
    prediction.reason = proposal.steps[2].reason.clone();
    prediction.effect_id = proposal.steps[2].effect_id.clone();
    prediction.comparisons = ygo_planner::assess_alternatives(
        &proposal,
        2,
        &prediction.alternatives,
        &prediction.selected.choice,
        &invalid.knowledge,
    );
    assert!(validate_plan_contract(&invalid).is_err());
    let mut invalid = r.clone();
    invalid.attempts[0].predictions.clear();
    assert!(validate_plan_contract(&invalid).is_err());
    let mut invalid = r.clone();
    invalid.attempts[0].predictions[0].reason = "posthoc story".into();
    assert!(validate_plan_contract(&invalid).is_err());
    let mut invalid = r.clone();
    invalid.analysis.search.lines[0]
        .result
        .coverage_gaps
        .push("unknown".into());
    assert!(validate_plan_contract(&invalid).is_err());
}
#[test]
#[ignore = "opt-in: local frozen assets"]
fn exhausted_budget_preserves_unobserved_prediction_and_failure_report() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let mut q: PlanRequest =
        serde_json::from_str(include_str!("../../../tests/fixtures/phantom.request.json")).unwrap();
    q.analysis.search.node_budget = 1;
    q.max_proposals = 1;
    let r = plan(
        q,
        engine,
        &store,
        pointer["catalog_id"].as_str().unwrap(),
        &ygo_search::combo::ScoringConfig::default(),
        ygo_knowledge::KnowledgePack::builtin().unwrap(),
    )
    .unwrap();
    assert!(r.analysis.search.lines.is_empty());
    assert_eq!(r.analysis.search.stats.engine_calls, 1);
    assert!(!r.attempts[0].discrepancies.is_empty());
    assert!(validate_plan_contract(&r).is_ok());
}
