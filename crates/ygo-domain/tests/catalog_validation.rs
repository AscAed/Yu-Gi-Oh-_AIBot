use std::collections::BTreeMap;
use ygo_domain::{
    parse_deck, validate_catalog_deck, validate_hand, Banlist, Card, CardId, CardKind, Deck, Limit,
};

fn card(id: u32, alias: u32, flags: u32) -> Card {
    Card {
        id: CardId(id),
        alias,
        type_flags: flags,
        name: id.to_string(),
        kind: CardKind::Monster,
        ..Default::default()
    }
}

#[test]
fn aliases_share_limits_and_unknown_cards_are_rejected() {
    let catalog = BTreeMap::from([(CardId(1), card(1, 0, 17)), (CardId(2), card(2, 1, 17))]);
    let banlist = Banlist::ocg("test", [(CardId(1), Limit::Limited)]);
    let deck = Deck::new(vec![CardId(2); 40], vec![], vec![]);
    assert!(validate_catalog_deck(&deck, &banlist, &catalog)
        .violations
        .iter()
        .any(|v| v.code == "copy_limit"));
    let deck = Deck::new(vec![CardId(999); 40], vec![], vec![]);
    assert!(validate_catalog_deck(&deck, &banlist, &catalog)
        .violations
        .iter()
        .any(|v| v.code == "unknown_card"));
}

#[test]
fn rejects_extra_monsters_in_main_and_impossible_hand() {
    let catalog = BTreeMap::from([(CardId(1), card(1, 0, 0x4000001))]);
    let deck = Deck::new(vec![CardId(1); 40], vec![], vec![]);
    assert!(
        validate_catalog_deck(&deck, &Banlist::ocg("x", []), &catalog)
            .violations
            .iter()
            .any(|v| v.code == "card_location")
    );
    assert!(validate_hand(&deck, &[CardId(2); 5]).is_err());
    assert!(validate_hand(&deck, &[CardId(1); 4]).is_err());
}
#[test]
fn incomplete_or_skill_card_data_is_not_legality_evidence() {
    for flags in [0, 0x8000000, 3] {
        let catalog = BTreeMap::from([(CardId(1), card(1, 0, flags))]);
        let deck = Deck::new(vec![CardId(1); 40], vec![], vec![]);
        assert!(
            validate_catalog_deck(&deck, &Banlist::ocg("x", []), &catalog)
                .violations
                .iter()
                .any(|v| v.code == "catalog_data")
        );
    }
}

#[test]
fn ydk_and_json_keep_main_extra_side_separate() {
    let deck = parse_deck("#created by test\n#main\n1\n2\n#extra\n3\n!side\n4\n").unwrap();
    assert_eq!(deck.main, vec![CardId(1), CardId(2)]);
    assert_eq!(deck.extra, vec![CardId(3)]);
    assert_eq!(deck.side, vec![CardId(4)]);
    assert_eq!(
        parse_deck("{\"main\":[1],\"extra\":[],\"side\":[]}")
            .unwrap()
            .main,
        vec![CardId(1)]
    );
    assert!(parse_deck("#main\nbad").is_err());
}
