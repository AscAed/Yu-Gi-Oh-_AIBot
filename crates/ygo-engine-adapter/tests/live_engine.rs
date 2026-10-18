use std::{collections::BTreeMap, path::Path};
use ygo_engine_adapter::*;

#[test]
#[ignore = "opt-in: pinned x64 engine, official CDB and scripts required"]
fn rabbit_routes_replay_and_end_phase_is_settled() {
    std::env::set_current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("../..")).unwrap();
    let engine =
        ProcessEngineConfig::from_toml(&std::fs::read_to_string("configs/engine.toml").unwrap())
            .unwrap();
    let fixture: serde_json::Value =
        serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.request.json")).unwrap();
    let routes: BTreeMap<String, serde_json::Value> =
        serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.lines.json")).unwrap();
    let mut request = runtime_request(
        engine.clone(),
        serde_json::from_value(fixture["deck"].clone()).unwrap(),
        serde_json::from_value(fixture["opening_hand"].clone()).unwrap(),
        1,
    )
    .unwrap();
    let adapter = ProcessEngineAdapter::new(engine);
    assert!(adapter.doctor().abi_ok);
    let a = adapter.run(&request).unwrap();
    request.seed = 2;
    let b = adapter.run(&request).unwrap();
    let deck_order = |r: &DuelResult| {
        r.checkpoint
            .cards
            .iter()
            .filter(|c| c.player == 0 && c.location == 1)
            .map(|c| c.code)
            .collect::<Vec<_>>()
    };
    assert_ne!(
        deck_order(&a),
        deck_order(&b),
        "seed must shuffle the remaining deck"
    );
    request.seed = 1;
    for (name, route) in routes {
        request.opening_hand = serde_json::from_value(
            route
                .get("opening_hand")
                .unwrap_or(&fixture["opening_hand"])
                .clone(),
        )
        .unwrap();
        request.decisions = serde_json::from_value(route["decisions"].clone()).unwrap();
        let result = adapter.run(&request).unwrap();
        assert_eq!(
            result.status,
            DuelStatus::EngineVerified,
            "{name}: {:?}",
            result.error
        );
        let board: Vec<u32> = result
            .checkpoint
            .cards
            .iter()
            .filter(|c| c.player == 0 && c.location == 4)
            .map(|c| c.code)
            .collect();
        assert_eq!(serde_json::json!(board), route["board"], "{name}");
        let replay = adapter.run(&request).unwrap();
        assert_eq!(replay.events, result.events);
        assert_eq!(replay.checkpoint, result.checkpoint);
        assert_eq!(replay.loaded_scripts, result.loaded_scripts);
        if name == "xyz" {
            assert_eq!(
                result
                    .checkpoint
                    .cards
                    .iter()
                    .find(|c| c.code == 84013237 && c.location == 4)
                    .unwrap()
                    .overlay,
                [69247929, 69247929]
            );
        }
        request.decisions[0].prompt_id += 1;
        let failure = adapter.run(&request).unwrap();
        assert_eq!(failure.status, DuelStatus::Failed);
        assert!(!failure.events.is_empty());
        assert!(failure.prompt.is_some());
    }
    request.decisions.clear();
    request.versions.cdb_sha256 = "00".repeat(32);
    assert_eq!(
        adapter.run(&request).unwrap().error.unwrap().code,
        "asset_hash"
    );
    request.versions.cdb_sha256 = hash_file(&request.engine.catalog_path).unwrap();
    let empty = std::env::temp_dir().join(format!("ygo-empty-script-{}", std::process::id()));
    std::fs::create_dir_all(&empty).unwrap();
    request.engine.scripts_path = empty.clone();
    let failure = adapter.run(&request).unwrap();
    assert_eq!(failure.status, DuelStatus::Failed);
    assert!(failure.error.unwrap().message.contains("script"));
    std::fs::remove_dir(empty).unwrap();
}
