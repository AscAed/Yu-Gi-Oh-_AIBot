use ygo_engine_adapter::*;

#[test]
fn controlled_interruption_is_versioned_and_preserves_failure_protocol() {
    let value = serde_json::json!({"protocol_version":4,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":{"rules":"bad","catalog":"","banlist":"","engine_sha256":"","cdb_sha256":"","scripts_sha256":"","core_commit":"","initializer":"fixed-interruption-v1"},"interruption":{"opponent_deck":{"main":[],"extra":[],"side":[]},"opponent_hand":[14558127],"policy":"ash_scales_once","effect_id":"25538345:mill","occurrence":1}});
    let request: RunDuelRequest = serde_json::from_value(value).expect("typed v4 interruption");
    let mut bytes = vec![];
    run_worker(
        std::io::Cursor::new(serde_json::to_vec(&request).unwrap()),
        &mut bytes,
    )
    .unwrap();
    let r: DuelResult = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(r.protocol_version, 4);
    assert_eq!(r.status, DuelStatus::Failed);
    assert_eq!(r.versions.initializer, "fixed-interruption-v1");
}
