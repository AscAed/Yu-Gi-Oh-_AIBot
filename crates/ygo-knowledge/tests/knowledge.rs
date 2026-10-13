#[test]
fn curated_twelve_card_pack_has_consistent_effect_references() {
    assert!(ygo_knowledge::validate_builtin().is_ok());
}
#[test]
fn cherubini_candidates_exclude_traps_and_keep_level_three_monsters() {
    let k = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut catalog = ygo_domain::Catalog::new();
    for (id, bits, level) in [(25542642, 4, 0), (36426778, 33, 3)] {
        catalog.insert(
            ygo_domain::CardId(id),
            ygo_domain::Card {
                id: ygo_domain::CardId(id),
                name: id.to_string(),
                type_flags: bits,
                level,
                setcodes: vec![0x10db],
                ..Default::default()
            },
        );
    }
    let explanation = k.explain_catalog(58699500, &catalog).unwrap();
    assert_eq!(
        explanation["catalog_candidates"][0]["cards"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        explanation["catalog_candidates"][0]["cards"][0]["card_id"],
        36426778
    );
    assert!(explanation["conditional_links"]
        .as_array()
        .unwrap()
        .iter()
        .all(|l| l["to"] != "25542642:revive"));
}
#[test]
fn unknown_card_metadata_cannot_satisfy_a_filter() {
    use ygo_knowledge::{Filter, Truth};
    assert_eq!(Filter::default().matches(None), Truth::Unknown);
    let card = ygo_domain::Card {
        id: ygo_domain::CardId(25538345),
        type_flags: 33,
        setcodes: vec![0x10db],
        level: 3,
        race: 1,
        ..Default::default()
    };
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    assert_eq!(
        pack.effect("25538345:mill")
            .unwrap()
            .candidate_filter
            .as_ref()
            .unwrap()
            .matches(Some(&card)),
        Truth::No
    );
    assert_eq!(
        pack.effect("32807846:search")
            .unwrap()
            .candidate_filter
            .as_ref()
            .unwrap()
            .matches(Some(&card)),
        Truth::Yes
    );
}
#[test]
fn duplicate_ids_bad_sources_and_unsupported_effect_claims_are_rejected() {
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut k = pack.clone();
    k.cards.push(k.cards[0].clone());
    assert!(k.validate().is_err());
    let mut k = pack.clone();
    k.cards[0].script = "../outside.lua".into();
    assert!(k.validate().is_err());
    let mut k = pack;
    k.cards[0].effects[0].rule = ygo_knowledge::Rule::Unsupported;
    assert!(k.validate().is_err());
}
#[test]
fn ranks_and_link_ratings_are_not_levels_or_main_deck_search_targets() {
    use ygo_knowledge::{Filter, Truth};
    let link = ygo_domain::Card {
        id: ygo_domain::CardId(26692769),
        name: "Rusty".into(),
        type_flags: 0x4000021,
        level: 3,
        race: 1,
        setcodes: vec![0x10db],
        ..Default::default()
    };
    assert_eq!(
        Filter {
            level: Some(3),
            ..Default::default()
        }
        .matches(Some(&link)),
        Truth::No
    );
    let k = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut catalog = ygo_domain::Catalog::new();
    catalog.insert(link.id, link);
    let explanation = k.explain_catalog(90432163, &catalog).unwrap();
    assert!(explanation["catalog_candidates"][0]["cards"]
        .as_array()
        .unwrap()
        .is_empty());
}
