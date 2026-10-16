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

#[test]
fn v5_accepts_each_scoped_effect_but_keeps_v4_closed() {
    let mut deck = ygo_domain::Deck {
        main: vec![ygo_domain::CardId(2964201); 40],
        extra: vec![],
        side: vec![],
    };
    deck.main[0] = ygo_domain::CardId(14558127);
    let mut c = InterruptionConfig {
        opponent_deck: deck,
        opponent_hand: vec![ygo_domain::CardId(14558127)],
        policy: "ash_effect_once".into(),
        effect_id: "25538345:mill".into(),
        occurrence: 1,
    };
    for id in ASH_EFFECTS {
        c.effect_id = id.into();
        c.validate_v5().unwrap();
        assert!(c.validate().is_err());
    }
    c.effect_id = "58699500:mill".into();
    assert!(c.validate_v5().is_err());
}
