#[test]
#[ignore = "opt-in: effect verification with frozen engine"]
fn all_curated_effects_have_real_positive_and_negative_cases() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join("target/release/ygo-engine-worker.exe");
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let cases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/phantom.engine-cases.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let r = ygo_api::verification::verify(
        cases,
        engine,
        &store,
        active["catalog_id"].as_str().unwrap(),
        pack,
    )
    .unwrap();
    std::fs::write(
        root.join("data/runtime/effect-verification.json"),
        serde_json::to_vec_pretty(&r).unwrap(),
    )
    .unwrap();
    for c in r["cases"].as_array().unwrap() {
        println!("{} {} {}", c["effect_id"], c["passed"], c["error"]);
    }
    assert_eq!(r["passed"], true);
}
