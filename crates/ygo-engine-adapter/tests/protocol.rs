use ygo_engine_adapter::*;
fn select_all(n: u32, min: u32) -> Vec<u8> {
    let mut raw = vec![15, 0, 0];
    for v in [min, n, n] {
        raw.extend(v.to_le_bytes());
    }
    for code in 1..=n {
        raw.extend(code.to_le_bytes());
        raw.extend([0, 1]);
        raw.extend(0u32.to_le_bytes());
        raw.extend(8u32.to_le_bytes());
    }
    raw
}
#[test]
fn near_all_card_selection_does_not_walk_impossible_subsets() {
    let start = std::time::Instant::now();
    let p = parse_prompt(1, &select_all(24, 24)).unwrap().unwrap();
    assert_eq!(p.actions.len(), 1);
    assert!(start.elapsed() < std::time::Duration::from_millis(300));
    assert_eq!(
        parse_prompt(1, &select_all(40, 40))
            .unwrap()
            .unwrap()
            .actions
            .len(),
        1
    );
    // min=39,max=40 includes the forty choose-39 sets and the full set.
    assert_eq!(
        parse_prompt(1, &select_all(40, 39))
            .unwrap()
            .unwrap()
            .actions
            .len(),
        41
    );
}
#[test]
fn decodes_hint_and_shuffle_with_pinned_widths() {
    assert_eq!(
        decode_frame(1, &[2, 3, 0, 1, 0, 0, 0, 0, 0, 0, 0])
            .unwrap()
            .fields["value"],
        1
    );
    assert_eq!(decode_frame(2, &[32, 0]).unwrap().fields["player"], 0);
    let hand = decode_frame(3, &[33, 0, 1, 0, 0, 0, 42, 0, 0, 0]).unwrap();
    assert_eq!(hand.fields["cards"][0], 42);
    assert!(decode_frame(3, &[33, 0, 1, 0, 0, 0, 42]).is_err());
}
#[test]
fn position_change_uses_byte_positions_and_set_uses_full_location() {
    let p = decode_frame(1, &[53, 42, 0, 0, 0, 0, 4, 1, 1, 4]).unwrap();
    assert_eq!(p.fields["position"], 4);
    assert!(decode_frame(1, &[53, 42, 0, 0, 0, 0, 4, 1, 1]).is_err());
    assert_eq!(
        decode_frame(2, &[54, 42, 0, 0, 0, 0, 4, 1, 0, 0, 0, 8, 0, 0, 0])
            .unwrap()
            .fields["location"]["sequence"],
        1
    );
}
#[test]
fn chain_acknowledgements_use_one_byte_index() {
    assert_eq!(decode_frame(1, &[71, 1]).unwrap().fields["chain"], 1);
    assert_eq!(decode_frame(2, &[73, 1]).unwrap().fields["chain"], 1);
    assert!(decode_frame(3, &[71, 1, 0, 0, 0]).is_err());
}
#[test]
fn rejects_truncated_frames_and_preserves_multiple_messages() {
    assert!(split_frames(&[8, 0, 0, 0, 41, 4, 0]).is_err());
    assert_eq!(
        split_frames(&[3, 0, 0, 0, 41, 4, 0, 2, 0, 0, 0, 40, 0])
            .unwrap()
            .len(),
        2
    );
}
#[test]
fn phase_parser_distinguishes_main_and_end() {
    let main = decode_frame(1, &[41, 4, 0]).unwrap();
    let end = decode_frame(2, &[41, 0, 2]).unwrap();
    assert_eq!(main.fields["phase"], 4);
    assert_eq!(end.fields["phase"], 512);
    assert!(decode_frame(1, &[41, 4]).is_err());
    assert!(!decode_frame(1, &[255, 1, 2]).unwrap().supported);
}
#[test]
fn invalid_jsonl_and_wrong_protocol_are_structured_failures() {
    let mut out = Vec::new();
    run_worker(std::io::Cursor::new(b"not-json\n"), &mut out).unwrap();
    let v: serde_json::Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(v["error"]["code"], "invalid_request");
    let r = RunDuelRequest {
        protocol_version: 1,
        engine: Default::default(),
        deck: Default::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions: Default::default(),
        probe_only: true,
        scenario: None,
        interruption: None,
    };
    out.clear();
    run_worker(
        std::io::Cursor::new(serde_json::to_vec(&r).unwrap()),
        &mut out,
    )
    .unwrap();
    let v: serde_json::Value = serde_json::from_slice(&out).unwrap();
    assert_eq!(v["error"]["code"], "protocol_version");
}
#[test]
fn card_selections_encode_full_width_indices() {
    let raw = [
        15, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 42, 0, 0, 0, 0, 2, 0, 0, 0, 0, 1, 0, 0, 0,
    ];
    let p = parse_prompt(1, &raw).unwrap().unwrap();
    assert_eq!(p.actions[0].bytes, vec![0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0]);
    assert!(p.encode(&Choice::Cards { indices: vec![1] }).is_err());
}
