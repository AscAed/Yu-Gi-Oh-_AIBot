use ygo_engine_adapter::*;
#[test]
fn preserves_distinct_effects_of_the_same_card_without_changing_responses() {
    let mut raw = vec![11, 0];
    for command in 0..6u8 {
        raw.extend(if command == 5 { 2u32 } else { 0 }.to_le_bytes());
        if command == 5 {
            for description in [(25538345u64 << 20), (25538345u64 << 20) + 1] {
                raw.extend(25538345u32.to_le_bytes());
                raw.extend([0, 4]);
                raw.extend(0u32.to_le_bytes());
                raw.extend(description.to_le_bytes());
                raw.push(0);
            }
        }
    }
    raw.extend([0, 1, 0]);
    let before = parse_prompt(9, &raw).unwrap().unwrap();
    let metadata = prompt_metadata(9, &raw).unwrap();
    assert_ne!(
        metadata[0].effect_description,
        metadata[1].effect_description
    );
    assert_eq!(metadata[0].source, metadata[1].source);
    assert_eq!(before, parse_prompt(9, &raw).unwrap().unwrap());
}
#[test]
fn binds_same_name_instances_by_location_and_index() {
    let mut raw = vec![15, 0, 0];
    for n in [1u32, 1, 2] {
        raw.extend(n.to_le_bytes());
    }
    for sequence in [0u32, 1] {
        raw.extend(36426778u32.to_le_bytes());
        raw.extend([0, 2]);
        raw.extend(sequence.to_le_bytes());
        raw.extend(1u32.to_le_bytes());
    }
    let m = prompt_metadata(1, &raw).unwrap();
    assert_eq!(m.len(), 2);
    assert_ne!(m[0].selected, m[1].selected);
    assert_eq!(m[0].selected[0].sequence, 0);
    assert_eq!(m[1].selected[0].sequence, 1);
}
