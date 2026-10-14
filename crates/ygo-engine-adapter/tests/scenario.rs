use ygo_engine_adapter::*;
#[test]
fn scenario_and_actual_levels_are_versioned() {
    let q = serde_json::json!({"protocol_version":3,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":{"rules":"ocg-mr5","catalog":"","banlist":"","engine_sha256":"","cdb_sha256":"","scripts_sha256":"","core_commit":"","initializer":"fixed-opponent-v1"},"scenario":"ryu-ran"});
    let request: RunDuelRequest = serde_json::from_value(q).expect("v3 scenario request");
    let value = serde_json::to_value(&request).unwrap();
    assert_eq!(value["scenario"], "ryu-ran");
    let state:StateCard=serde_json::from_value(serde_json::json!({"code":62709239,"player":0,"location":4,"sequence":0,"position":1,"type_flags":0,"attack":0,"defense":0,"overlay":[],"level":0,"rank":3})).unwrap();
    assert_eq!(serde_json::to_value(state).unwrap()["rank"], 3);
}
#[test]
fn destruction_targets_and_player_restriction_hints_are_decoded() {
    for raw in [
        vec![83, 1, 0, 0, 0, 0, 4, 0, 0, 0, 0, 1, 0, 0, 0],
        vec![165, 0, 6, 2, 0, 112, 223, 205, 59, 0, 0],
    ] {
        assert!(ygo_engine_adapter::decode_frame(1, &raw).unwrap().supported);
        assert!(ygo_engine_adapter::decode_frame(1, &raw[..raw.len() - 1]).is_err());
    }
}
#[test]
fn v3_failures_keep_the_request_protocol() {
    let request:RunDuelRequest=serde_json::from_value(serde_json::json!({"protocol_version":3,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":{"rules":"bad","catalog":"","banlist":"","engine_sha256":"","cdb_sha256":"","scripts_sha256":"","core_commit":"","initializer":"fixed-opponent-v1"}})).unwrap();
    let mut bytes = vec![];
    run_worker(
        std::io::Cursor::new(serde_json::to_vec(&request).unwrap()),
        &mut bytes,
    )
    .unwrap();
    let r: DuelResult = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(r.protocol_version, 3);
    assert_eq!(r.status, DuelStatus::Failed);
}
