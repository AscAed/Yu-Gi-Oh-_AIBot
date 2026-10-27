use ygo_engine_adapter::*;
#[test]
fn historical_idle_projection_is_exact_and_never_accepts_arbitrary_edits() {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ash-v5-anchor.events.json"
    ))
    .unwrap();
    let result: DuelResult = serde_json::from_value(fixture["observation"].clone()).unwrap();
    for frame in &result.events {
        assert!(frame_matches_raw(frame).unwrap());
    }
    let frame = result
        .events
        .iter()
        .find(|e| e.opcode == 11 && decode_frame(e.sequence, &e.raw).unwrap() != **e)
        .unwrap();
    let prompt = recorded_prompt(frame).unwrap().unwrap();
    assert!(prompt_matches_raw(&prompt, &frame.raw).unwrap());
    for command in [6, 8] {
        assert!(prompt
            .encode(&Choice::Command { command, index: 0 })
            .is_err());
    }
    assert!(
        parse_prompt(frame.sequence, &frame.raw)
            .unwrap()
            .unwrap()
            .actions
            .len()
            > prompt.actions.len()
    );
    let mut bad = frame.clone();
    bad.fields["prompt"]["actions"][0]["label"] = serde_json::json!("forged");
    assert!(!frame_matches_raw(&bad).unwrap());
    let mut bad = frame.clone();
    bad.fields["prompt"]["actions"]
        .as_array_mut()
        .unwrap()
        .remove(0);
    assert!(!frame_matches_raw(&bad).unwrap());
    let mut bad = frame.clone();
    bad.fields["prompt"]["actions"][0]["bytes"] = serde_json::json!([255, 0, 0, 0]);
    assert!(!frame_matches_raw(&bad).unwrap());
    let mut bad = frame.clone();
    bad.fields["injected"] = serde_json::json!(true);
    assert!(!frame_matches_raw(&bad).unwrap());
    let mut bad = frame.clone();
    let action = bad.fields["prompt"]["actions"][0].clone();
    bad.fields["prompt"]["actions"]
        .as_array_mut()
        .unwrap()
        .push(action);
    assert!(!frame_matches_raw(&bad).unwrap());
    let mut raw = vec![11, 0];
    raw.extend([0; 24]);
    raw.extend([1, 0, 1]);
    let mut empty = decode_frame(1, &raw).unwrap();
    empty.fields["prompt"]["actions"] = serde_json::json!([]);
    assert!(!frame_matches_raw(&empty).unwrap());
}

#[test]
fn newly_supported_events_keep_their_historical_unparsed_projection() {
    for raw in [vec![92, 0, 200, 0, 0, 0], vec![56, 0xe0, 0xff, 0xe0, 0xff]] {
        let historical = CoreEventFrame {
            sequence: 1,
            opcode: raw[0],
            raw: raw.clone(),
            supported: false,
            fields: serde_json::json!({"unparsed":true}),
        };
        let current = decode_frame(historical.sequence, &historical.raw).unwrap();

        assert_ne!(current, historical);
        assert!(frame_matches_raw(&historical).unwrap());
        assert!(frame_matches_raw(&current).unwrap());

        let mut forged = historical;
        forged.fields = serde_json::json!({"player":0});
        assert!(!frame_matches_raw(&forged).unwrap());
    }

    for (opcode, raw) in [
        (92, vec![92, 0, 200]),
        (56, vec![56, 0xe0, 0xff, 0xe0, 0xff, 1]),
    ] {
        let malformed = CoreEventFrame {
            sequence: 1,
            opcode,
            raw,
            supported: false,
            fields: serde_json::json!({"unparsed":true}),
        };
        assert!(frame_matches_raw(&malformed).is_err());
    }
}
