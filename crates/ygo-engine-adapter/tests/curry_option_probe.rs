use ygo_engine_adapter::*;

fn option_frame(sequence: u64) -> (CoreEventFrame, Prompt) {
    let mut raw = vec![14, 0, 2];
    raw.extend(60_895_602_409_472u64.to_le_bytes());
    raw.extend(60_895_602_409_473u64.to_le_bytes());
    let frame = decode_frame(sequence, &raw).unwrap();
    let prompt = parse_prompt(sequence, &raw).unwrap().unwrap();
    (frame, prompt)
}

fn recover_event(sequence: u64, player: u8, amount: u32) -> CoreEventFrame {
    let mut raw = vec![92, player];
    raw.extend(amount.to_le_bytes());
    decode_frame(sequence, &raw).unwrap()
}

#[test]
fn curry_option_oracle_checks_descriptions_order_and_exact_response_set() {
    let (frame, prompt) = option_frame(3);
    validate_curry_option_prompt(&frame, &prompt).unwrap();

    let mut reversed = frame.clone();
    reversed.raw[3..11].copy_from_slice(&60_895_602_409_473u64.to_le_bytes());
    reversed.raw[11..19].copy_from_slice(&60_895_602_409_472u64.to_le_bytes());
    assert!(validate_curry_option_prompt(&reversed, &prompt).is_err());

    let mut duplicate = prompt.clone();
    duplicate.actions[1].bytes = duplicate.actions[0].bytes.clone();
    assert!(validate_curry_option_prompt(&frame, &duplicate).is_err());
}

#[test]
fn curry_recover_oracle_binds_the_selected_player_and_life_points() {
    let player0 = Checkpoint {
        lp: [8200, 8000],
        ..Checkpoint::default()
    };
    validate_curry_recover_result(0, 3, &[recover_event(4, 0, 200)], &player0).unwrap();

    let player1 = Checkpoint {
        lp: [8000, 8200],
        ..Checkpoint::default()
    };
    validate_curry_recover_result(1, 3, &[recover_event(4, 1, 200)], &player1).unwrap();

    assert!(validate_curry_recover_result(0, 3, &[recover_event(4, 1, 200)], &player0).is_err());
    assert!(validate_curry_recover_result(0, 3, &[recover_event(2, 0, 200)], &player0).is_err());
    assert!(validate_curry_recover_result(
        0,
        3,
        &[recover_event(4, 0, 200), recover_event(5, 0, 200)],
        &player0
    )
    .is_err());

    let mut nonzero_special_count = vec![16, 1, 1, 0];
    nonzero_special_count.extend([0; 12]);
    let special_count_frame = decode_frame(4, &nonzero_special_count).unwrap();
    assert!(validate_curry_recover_result(
        0,
        3,
        &[special_count_frame, recover_event(5, 0, 200)],
        &player0
    )
    .is_err());

    let mut valid_chain = vec![16, 1, 0, 0];
    valid_chain.extend([0; 12]);
    let mut trailing_frame = decode_frame(4, &valid_chain).unwrap();
    trailing_frame.raw.push(0);
    assert!(validate_curry_recover_result(
        0,
        3,
        &[trailing_frame, recover_event(5, 0, 200)],
        &player0
    )
    .is_err());
}

#[test]
fn curry_scope_uses_seven_ordered_purpose_slots_and_rejects_the_eighth() {
    let purposes = (1..=7)
        .map(|stage| curry_option_purpose(stage).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(purposes[0], CallPurpose::Probe);
    assert_eq!(purposes[1], CallPurpose::Probe);
    assert_eq!(purposes[2], CallPurpose::Probe);
    assert_eq!(purposes[3], CallPurpose::Execution);
    assert_eq!(purposes[4], CallPurpose::Replay);
    assert_eq!(purposes[5], CallPurpose::Execution);
    assert_eq!(purposes[6], CallPurpose::Replay);
    assert!(curry_option_purpose(8).is_err());

    let prefix = LedgerStats {
        consumed: 3,
        completed: 3,
        unknown: 0,
        reserved: 0,
        abandoned: 0,
        limit: 7,
    };
    validate_curry_option_slot(4, &prefix).unwrap();
    assert!(validate_curry_option_slot(8, &prefix).is_err());
}
