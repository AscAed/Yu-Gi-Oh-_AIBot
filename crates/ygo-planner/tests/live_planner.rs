use std::{fs, path::PathBuf};
use ygo_domain::{CardId, Catalog, Deck};
use ygo_engine_adapter::*;
use ygo_knowledge::KnowledgePack;
use ygo_planner::*;
use ygo_search::combo::*;
#[test]
#[ignore = "opt-in: frozen local core/CDB/scripts"]
fn phantom_causal_plan_reaches_goal_and_independently_replays() {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine: ProcessEngineConfig = toml_config(&root);
    let active: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join("data/snapshots/active.json")).unwrap())
            .unwrap();
    let id = active["catalog_id"].as_str().unwrap();
    let data: serde_json::Value =
        serde_json::from_slice(&fs::read(root.join(format!("data/snapshots/{id}.json"))).unwrap())
            .unwrap();
    let catalog: Catalog = serde_json::from_value(data["data"].clone()).unwrap();
    let fixture: serde_json::Value = serde_json::from_slice(
        &fs::read(root.join("tests/fixtures/phantom.request.json")).unwrap(),
    )
    .unwrap();
    let deck: Deck = serde_json::from_value(fixture["analysis"]["deck"].clone()).unwrap();
    let hand: Vec<CardId> =
        serde_json::from_value(fixture["analysis"]["opening_hand"].clone()).unwrap();
    let pack = KnowledgePack::read(&root.join("knowledge/phantom-v1.json")).unwrap();
    pack.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )
    .unwrap();
    let request = runtime_request(engine.clone(), deck.clone(), hand.clone(), 1).unwrap();
    let proposals = propose(&deck, &hand, &catalog, &pack, 8, 32).unwrap();
    let result = execute(
        &ProcessEngineAdapter::new(engine),
        &request,
        proposals,
        &SearchBudget {
            node_budget: 512,
            time_limit_ms: 120000,
            ..Default::default()
        },
        &ScoringConfig::default(),
        &pack,
    )
    .unwrap();
    for a in &result.attempts {
        println!("{} {} {:?}", a.proposal_id, a.status, a.discrepancies);
    }
    assert!(
        !result.search.lines.is_empty(),
        "{}",
        result.search.termination
    );
    assert!(result
        .search
        .lines
        .iter()
        .all(|l| l.replay_verified && l.result.status == DuelStatus::EngineVerified));
    assert!(result.attempts.iter().any(|a| a.goal_achieved));
    assert!(result.search.stats.engine_calls <= 512);
}
fn toml_config(root: &std::path::Path) -> ProcessEngineConfig {
    ProcessEngineConfig::from_toml(&fs::read_to_string(root.join("configs/engine.toml")).unwrap())
        .unwrap()
}
