use ygo_engine_adapter::*;
#[test]
fn phantom_card_hints_and_set_confirmation_are_fully_decoded() {
    let hint = vec![
        160, 0, 4, 0, 0, 0, 0, 1, 0, 0, 0, 6, 228, 12, 0, 0, 0, 0, 0, 0,
    ];
    let set = vec![31, 0, 1, 0, 0, 0, 242, 191, 133, 1, 0, 8, 0, 0, 0, 0];
    let a = decode_frame(1, &hint).unwrap();
    let b = decode_frame(2, &set).unwrap();
    assert!(a.supported);
    assert!(b.supported);
    assert_eq!(a.fields["hint_type"], 6);
    assert_eq!(b.fields["cards"][0]["code"], 25542642);
    assert!(decode_frame(3, &hint[..hint.len() - 1]).is_err());
    assert!(decode_frame(4, &set[..set.len() - 1]).is_err());
}
