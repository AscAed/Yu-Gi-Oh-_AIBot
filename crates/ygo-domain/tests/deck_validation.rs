use ygo_domain::{Banlist, CardId, Deck, DeckValidationRules, Limit};

#[test]
fn rejects_a_deck_with_a_banned_card() {
    let deck = Deck::new(vec![CardId(100); 40], vec![], vec![]);
    let banlist = Banlist::ocg("2026-09", [(CardId(100), Limit::Forbidden)]);

    let report = deck.validate(&banlist, &DeckValidationRules::ocg());

    assert!(!report.is_legal());
    assert!(report
        .violations
        .iter()
        .any(|violation| violation.code == "copy_limit"));
}

#[test]
fn accepts_a_legal_ocg_deck() {
    let main = (1..=40).map(CardId).collect();
    let deck = Deck::new(main, vec![CardId(1000); 3], vec![]);

    let report = deck.validate(&Banlist::ocg("2026-09", []), &DeckValidationRules::ocg());

    assert!(report.is_legal(), "{:#?}", report.violations);
}

#[test]
fn reports_main_deck_size_and_extra_deck_limits() {
    let deck = Deck::new(
        (1..=39).map(CardId).collect(),
        (100..=115).map(CardId).collect(),
        vec![],
    );

    let report = deck.validate(&Banlist::ocg("2026-09", []), &DeckValidationRules::ocg());

    assert_eq!(report.violations.len(), 2);
    assert!(report
        .violations
        .iter()
        .any(|violation| violation.code == "main_size"));
    assert!(report
        .violations
        .iter()
        .any(|violation| violation.code == "extra_size"));
}
