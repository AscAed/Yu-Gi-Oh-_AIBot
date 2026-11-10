use serde::Deserialize;
use ygo_engine_adapter::*;

#[derive(Deserialize)]
struct Opcode24MenuFixture {
    classification: String,
    raw_prompt: Vec<u8>,
    disabled_mask: String,
    available_zones: usize,
    canonical_menu_pair_count: usize,
    distinct_ordered_encodings: usize,
    actions: Vec<Opcode24FixtureAction>,
    native_reachability_verified: bool,
    native_response_acceptance_verified: bool,
    order_equivalence_verified: bool,
}

#[derive(Deserialize)]
struct Opcode24FixtureAction {
    choice: Choice,
    card_ids: Vec<u32>,
    bytes: Vec<u8>,
}

fn idle(flags: u8) -> Vec<u8> {
    let mut raw = vec![11, 0];
    raw.extend(2u32.to_le_bytes());
    for _ in 0..2 {
        raw.extend(100u32.to_le_bytes());
        raw.extend([0, 2]);
        raw.extend(0u32.to_le_bytes());
    }
    raw.extend([0; 20]);
    raw.extend([flags & 1, (flags >> 1) & 1, (flags >> 2) & 1]);
    raw
}
fn cards(n: u32, min: u32, max: u32, cancel: bool) -> Vec<u8> {
    let mut raw = vec![15, 0, u8::from(cancel)];
    for value in [min, max, n] {
        raw.extend(value.to_le_bytes());
    }
    // Repeated card IDs must remain different selectable positions.
    raw.extend(vec![0; n as usize * 14]);
    raw
}
#[test]
fn idle_flags_have_handwritten_exact_choices_and_encodings() {
    for flags in 0..8 {
        let raw = idle(flags);
        let prompt = parse_prompt(3, &raw).unwrap().unwrap();
        let mut expected = vec![(0, 0), (0, 1)];
        for (mask, command) in [(1, 6), (2, 7), (4, 8)] {
            if flags & mask != 0 {
                expected.push((command, 0));
            }
        }
        let mut bytes = Vec::new();
        assert_eq!(prompt.actions.len(), expected.len());
        for (action, (command, index)) in prompt.actions.iter().zip(expected) {
            let choice = Choice::Command { command, index };
            let encoding = ((index << 16) | u32::from(command)).to_le_bytes().to_vec();
            assert_eq!(action.choice, choice);
            assert_eq!(action.bytes, encoding);
            assert_eq!(prompt.encode(&choice).unwrap(), encoding);
            bytes.push(encoding);
        }
        bytes.sort();
        assert_eq!(expected_prompt_responses(&raw).unwrap(), bytes);
    }
}
#[test]
fn combination_cap_is_inclusive_and_cancel_is_separate() {
    for cancel in [false, true] {
        let raw = cards(12, 0, 12, cancel);
        let prompt = parse_prompt(1, &raw).unwrap().unwrap();
        assert_eq!(prompt.actions.len(), 4096 + usize::from(cancel));
        assert!(
            audit_prompt_responses(
                &raw,
                &prompt
                    .actions
                    .into_iter()
                    .map(|a| a.bytes)
                    .collect::<Vec<_>>()
            )
            .unwrap()
            .matches
        );
    }
    assert!(parse_prompt(1, &cards(4096, 0, 1, false)).is_err());
    assert!(parse_prompt(1, &cards(15, 7, 7, false)).is_err());
    assert!(expected_prompt_responses(&cards(15, 7, 7, false)).is_err());
    let forced = parse_prompt(1, &cards(4096, 4096, 4096, false))
        .unwrap()
        .unwrap();
    assert_eq!(forced.actions.len(), 1);
    assert_eq!(forced.actions[0].card_ids.len(), 4096);
}
#[test]
fn small_card_subsets_match_test_owned_bit_masks() {
    for n in 0..=5u32 {
        for min in 0..=n {
            for max in min..=n {
                let raw = cards(n, min, max, true);
                let mut expected = vec![u32::MAX.to_le_bytes().to_vec()];
                for mask in 0..(1u32 << n) {
                    let count = mask.count_ones();
                    if count < min || count > max {
                        continue;
                    }
                    let mut words = vec![0, count];
                    words.extend((0..n).filter(|i| mask & (1 << i) != 0));
                    expected.push(words.iter().flat_map(|w| w.to_le_bytes()).collect());
                }
                expected.sort();
                let mut actual = parse_prompt(1, &raw)
                    .unwrap()
                    .unwrap()
                    .actions
                    .into_iter()
                    .map(|a| a.bytes)
                    .collect::<Vec<_>>();
                actual.sort();
                assert_eq!(actual, expected);
                assert_eq!(expected_prompt_responses(&raw).unwrap(), expected);
            }
        }
    }
}
#[test]
fn place_subsets_follow_independent_mask_enumeration() {
    for opcode in [18, 24] {
        for count in 1..=3u8 {
            let mut raw = vec![opcode, 1, count];
            raw.extend((u32::MAX ^ 0b111).to_le_bytes());
            let mut expected = Vec::new();
            for mask in 1u32..8 {
                if mask.count_ones() != u32::from(count) {
                    continue;
                }
                expected.push(
                    (0..3u8)
                        .filter(|i| mask & (1 << i) != 0)
                        .flat_map(|i| [1, 4, i])
                        .collect::<Vec<_>>(),
                );
            }
            expected.sort();
            let mut actual = parse_prompt(1, &raw)
                .unwrap()
                .unwrap()
                .actions
                .into_iter()
                .map(|a| a.bytes)
                .collect::<Vec<_>>();
            actual.sort();
            assert_eq!(actual, expected);
            assert_eq!(expected_prompt_responses(&raw).unwrap(), expected);
        }
        let mut raw = vec![opcode, 0, 15];
        raw.extend(0u32.to_le_bytes());
        assert!(parse_prompt(1, &raw).is_err());
        assert!(expected_prompt_responses(&raw).is_err());
    }
}

#[test]
fn ground_collapse_opcode24_menu_matches_independent_fixture() {
    let fixture: Opcode24MenuFixture = serde_json::from_str(include_str!(
        "../../../tests/fixtures/ground-collapse-opcode24-menu-v1.json"
    ))
    .unwrap();
    assert_eq!(fixture.classification, "synthetic_only");
    assert_eq!(fixture.disabled_mask, "ffe0ffe0");
    assert_eq!(fixture.available_zones, 10);
    assert_eq!(fixture.canonical_menu_pair_count, 45);
    assert_eq!(fixture.distinct_ordered_encodings, 90);
    assert!(!fixture.native_reachability_verified);
    assert!(!fixture.native_response_acceptance_verified);
    assert!(!fixture.order_equivalence_verified);

    let prompt = parse_prompt(71, &fixture.raw_prompt).unwrap().unwrap();
    assert_eq!(prompt.id, 71);
    assert_eq!(prompt.player, 0);
    assert_eq!(prompt.opcode, 24);
    assert_eq!(prompt.actions.len(), fixture.actions.len());
    for (actual, expected) in prompt.actions.iter().zip(&fixture.actions) {
        assert_eq!(actual.choice, expected.choice);
        assert_eq!(actual.card_ids, expected.card_ids);
        assert_eq!(actual.bytes, expected.bytes);
        assert_eq!(prompt.encode(&expected.choice).unwrap(), expected.bytes);
    }

    let forward = Choice::Place {
        zones: vec![
            Zone {
                player: 1,
                location: 4,
                sequence: 0,
            },
            Zone {
                player: 1,
                location: 4,
                sequence: 1,
            },
        ],
    };
    let reverse = Choice::Place {
        zones: vec![
            Zone {
                player: 1,
                location: 4,
                sequence: 1,
            },
            Zone {
                player: 1,
                location: 4,
                sequence: 0,
            },
        ],
    };
    assert_eq!(prompt.encode(&forward).unwrap(), [1, 4, 0, 1, 4, 1]);
    assert!(prompt.encode(&reverse).is_err());
}
