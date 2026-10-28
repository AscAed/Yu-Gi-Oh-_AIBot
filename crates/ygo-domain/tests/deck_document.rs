use ygo_domain::{CardId, DeckDocumentV1, DeckZone};

#[test]
fn a_partial_draft_preserves_order_duplicates_and_separate_zones() {
    let doc = DeckDocumentV1::new("work in progress", vec![1, 1], vec![1], vec![]).unwrap();
    assert_eq!(doc.main, vec![CardId(1), CardId(1)]);
    assert_eq!(doc.extra, vec![CardId(1)]);
    assert_eq!(doc.side, Vec::<CardId>::new());
    assert!(doc.validate().is_ok());
}

#[test]
fn draft_import_round_trips_ydk_and_json_without_claiming_ydk_title_support() {
    let doc = DeckDocumentV1::new("ordered", vec![5, 2, 5], vec![7], vec![9, 9]).unwrap();
    let json = doc.to_json().unwrap();
    assert_eq!(DeckDocumentV1::from_json(&json).unwrap(), doc);
    let ydk = doc.to_ydk();
    let imported = DeckDocumentV1::from_ydk(&ydk).unwrap();
    assert_eq!(imported.main, doc.main);
    assert_eq!(imported.extra, doc.extra);
    assert_eq!(imported.side, doc.side);
    assert_eq!(imported.title, "Imported YDK deck");
}

#[test]
fn imports_legacy_bare_deck_json_and_rejects_duplicate_json_fields() {
    let legacy = r#"{"main":[3,3],"extra":[],"side":[3]}"#;
    let doc = DeckDocumentV1::import_json(legacy).unwrap();
    assert_eq!(doc.main, vec![CardId(3), CardId(3)]);
    assert_eq!(doc.side, vec![CardId(3)]);
    assert!(DeckDocumentV1::import_json(r#"{"schema_version":1,"schema_version":1,"kind":"deck_draft","title":"x","main":[],"extra":[],"side":[]}"#).is_err());
    assert!(DeckDocumentV1::import_json(
        r#"{"schema_version":2,"kind":"deck_draft","title":"x","main":[],"extra":[],"side":[]}"#
    )
    .is_err());
}

#[test]
fn edit_changes_only_the_requested_zone_and_rejects_short_removal() {
    let mut doc = DeckDocumentV1::new("edit", vec![4, 4, 8], vec![4], vec![8]).unwrap();
    doc.edit(DeckZone::Main, "remove", 4, 1).unwrap();
    doc.edit(DeckZone::Side, "add", 4, 2).unwrap();
    assert_eq!(doc.main, vec![CardId(4), CardId(8)]);
    assert_eq!(doc.extra, vec![CardId(4)]);
    assert_eq!(doc.side, vec![CardId(8), CardId(4), CardId(4)]);
    let before = doc.clone();
    assert!(doc.edit(DeckZone::Main, "remove", 4, 2).is_err());
    assert_eq!(doc, before);
}

#[test]
fn rejects_zero_ids_and_malformed_ydk_with_line_context() {
    assert!(DeckDocumentV1::new("bad", vec![0], vec![], vec![]).is_err());
    let error = DeckDocumentV1::from_ydk("#main\n12\nnope\n").unwrap_err();
    assert!(error.contains("line 3"), "{error}");
}
