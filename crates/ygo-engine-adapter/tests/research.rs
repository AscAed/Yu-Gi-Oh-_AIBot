use ygo_engine_adapter::*;
#[test]
fn oracle_rejects_missing_extra_and_position_corruption() {
    let raw = [19, 0, 1, 0, 0, 0, 5];
    let legal = vec![1u32.to_le_bytes().to_vec(), 4u32.to_le_bytes().to_vec()];
    assert!(audit_prompt_responses(&raw, &legal).unwrap().matches);
    assert!(!audit_prompt_responses(&raw, &legal[..1]).unwrap().matches);
    let extra = vec![
        legal[0].clone(),
        legal[1].clone(),
        2u32.to_le_bytes().to_vec(),
    ];
    assert!(!audit_prompt_responses(&raw, &extra).unwrap().matches);
}
#[test]
fn forced_chain_does_not_allow_pass() {
    let mut raw = vec![16, 0, 0, 1];
    raw.extend([0; 12]);
    assert!(audit_prompt_responses(&raw, &[]).unwrap().matches);
    assert!(
        !audit_prompt_responses(&raw, &[u32::MAX.to_le_bytes().to_vec()])
            .unwrap()
            .matches
    );
}
#[test]
fn unknown_and_excessive_combinations_are_gaps() {
    assert!(expected_prompt_responses(&[200, 0]).is_err());
    let mut raw = vec![15, 0, 0];
    for n in [7u32, 7, 15] {
        raw.extend(n.to_le_bytes());
    }
    raw.extend(vec![0; 15 * 14]);
    assert!(expected_prompt_responses(&raw)
        .unwrap_err()
        .contains("limit"));
}

#[test]
fn all_ten_opcodes_match_canonical_oracle_and_reject_tampering() {
    let mut frames: Vec<Vec<u8>> =
        vec![
            serde_json::from_str(include_str!("../../../tests/fixtures/v3-idle-frame.json"))
                .unwrap(),
        ];
    let mut effect = vec![12, 0];
    effect.extend([0; 22]);
    frames.push(effect);
    let mut yesno = vec![13, 0];
    yesno.extend([0; 8]);
    frames.push(yesno);
    let mut option = vec![14, 0, 1];
    option.extend([0; 8]);
    frames.push(option);
    let mut cards = vec![15, 0, 1];
    for n in [1u32, 1, 1] {
        cards.extend(n.to_le_bytes());
    }
    cards.extend([0; 14]);
    frames.push(cards);
    let mut chain = vec![16, 0, 0, 0];
    chain.extend([0; 8]);
    chain.extend(1u32.to_le_bytes());
    chain.extend([0; 23]);
    frames.push(chain);
    for opcode in [18, 24] {
        let mut place = vec![opcode, 0, 1];
        place.extend((u32::MAX ^ 1).to_le_bytes());
        frames.push(place);
    }
    frames.push(vec![19, 0, 1, 0, 0, 0, 5]);
    let mut toggle = vec![26, 0, 1, 1];
    toggle.extend([0; 8]);
    toggle.extend(1u32.to_le_bytes());
    toggle.extend([0; 14]);
    toggle.extend(0u32.to_le_bytes());
    frames.push(toggle);
    assert_eq!(frames.len(), 10);
    for raw in frames {
        let production = parse_prompt(1, &raw)
            .unwrap()
            .unwrap()
            .actions
            .into_iter()
            .map(|a| a.bytes)
            .collect::<Vec<_>>();
        assert!(
            audit_prompt_responses(&raw, &production).unwrap().matches,
            "opcode {}",
            raw[0]
        );
        assert!(
            !audit_prompt_responses(&raw, &production[1..])
                .unwrap()
                .matches
        );
        let mut corrupt = production.clone();
        corrupt.push(vec![0xde, 0xad]);
        assert!(!audit_prompt_responses(&raw, &corrupt).unwrap().matches);
        assert!(expected_prompt_responses(&raw[..raw.len() - 1]).is_err());
    }
}
#[test]
fn battle_transition_matches_independent_oracle_after_repair() {
    let mut raw = vec![11, 0];
    raw.extend([0; 24]);
    raw.extend([1, 1, 0]);
    let production = parse_prompt(1, &raw).unwrap().unwrap();
    assert!(
        audit_prompt_responses(
            &raw,
            &production
                .actions
                .iter()
                .map(|a| a.bytes.clone())
                .collect::<Vec<_>>()
        )
        .unwrap()
        .matches
    );
}
