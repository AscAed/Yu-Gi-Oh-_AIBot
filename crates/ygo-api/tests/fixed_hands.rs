#[test]
#[ignore = "opt-in:16 fixed hands and human baselines"]
fn fixed_hands_match_manual_baselines_and_replay() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join("target/release/ygo-engine-worker.exe");
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let samples = serde_json::from_str(include_str!(
        "../../../tests/fixtures/phantom.fixed-hands.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let r = ygo_api::regression::run(
        samples,
        engine,
        &store,
        active["catalog_id"].as_str().unwrap(),
        pack,
    )
    .unwrap();
    std::fs::write(
        root.join("data/runtime/fixed-hands-report.json"),
        serde_json::to_vec_pretty(&r).unwrap(),
    )
    .unwrap();
    assert_eq!(r["passed"], true);
}
