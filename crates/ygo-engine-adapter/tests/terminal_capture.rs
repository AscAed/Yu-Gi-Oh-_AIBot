#[test]
fn capture_policy_is_opt_in_and_rejects_nonstandard_requests() {
    use ygo_engine_adapter::*;
    let mut r = RunDuelRequest {
        protocol_version: 2,
        engine: ProcessEngineConfig::default(),
        deck: Default::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions: Default::default(),
        probe_only: true,
        scenario: None,
        interruption: None,
        first_turn: None,
        research_capture: None,
    };
    let old = serde_json::to_value(&r).unwrap();
    assert!(old.get("research_capture").is_none());
    let legacy = serde_json::json!({"protocol_version":2,"engine":r.engine,"deck":r.deck,"opening_hand":[],"seed":1,"decisions":[],"versions":r.versions,"probe_only":true});
    assert_eq!(
        serde_json::to_vec(&old).unwrap(),
        serde_json::to_vec(&legacy).unwrap()
    );
    r.research_capture = Some(ResearchCaptureV1 {
        schema_version: 1,
        objective: "rabbit-own-face-up-xyz-v1".into(),
        boundary: "first-next-turn-process-return-v1".into(),
    });
    assert!(validate_research_capture(&r).is_err());
    r.probe_only = false;
    r.opening_hand = vec![ygo_domain::CardId(1); 5];
    assert!(validate_research_capture(&r).is_ok());
    r.protocol_version = 3;
    assert!(validate_research_capture(&r).is_err());
    let result =
        serde_json::to_value(DuelResult::failure(WorkerError::new("a", "b", "c"))).unwrap();
    assert!(result.get("terminal_observation").is_none());
}
