use crate::*;
pub type Catalog = BTreeMap<CardId, Card>;
pub fn canonical_id(id: CardId, catalog: &Catalog) -> Result<CardId, String> {
    let mut current = id;
    let mut seen = std::collections::BTreeSet::new();
    loop {
        if !seen.insert(current) {
            return Err(format!("alias cycle at {}", current.0));
        }
        let card = catalog
            .get(&current)
            .ok_or_else(|| format!("unknown card {}", current.0))?;
        if card.alias == 0 {
            return Ok(current);
        }
        current = CardId(card.alias);
    }
}
pub fn validate_catalog_deck(
    deck: &Deck,
    banlist: &Banlist,
    catalog: &Catalog,
) -> ValidationReport {
    let mut normalized = Deck::default();
    let mut problems = Vec::new();
    if banlist.region != "OCG" {
        problems.push(Violation::new("banlist_region", "requires OCG"));
    }
    for (zone, cards, dest) in [
        ("main", &deck.main, &mut normalized.main),
        ("extra", &deck.extra, &mut normalized.extra),
        ("side", &deck.side, &mut normalized.side),
    ] {
        for &id in cards {
            match canonical_id(id, catalog) {
                Ok(alias) => dest.push(alias),
                Err(error) => {
                    problems.push(Violation::new("unknown_card", error));
                    dest.push(id);
                }
            }
            if let Some(card) = catalog.get(&id) {
                let kind_bit = match card.kind {
                    CardKind::Monster => 1,
                    CardKind::Spell => 2,
                    CardKind::Trap => 4,
                };
                if card.id != id
                    || card.name.trim().is_empty()
                    || card.type_flags & 7 != kind_bit
                    || card.type_flags & 0x8000000 != 0
                {
                    problems.push(Violation::new(
                        "catalog_data",
                        format!(
                            "{} has incomplete/inconsistent or unsupported card data",
                            id.0
                        ),
                    ));
                }
                let extra = card.type_flags & (0x40 | 0x2000 | 0x800000 | 0x4000000) != 0;
                if (zone == "main" && extra)
                    || (zone == "extra" && !extra)
                    || card.type_flags & 0x4000 != 0
                {
                    problems.push(Violation::new(
                        "card_location",
                        format!("{} cannot be in {zone}", id.0),
                    ));
                }
            }
        }
    }
    let mut limits = BTreeMap::new();
    for (&id, &limit) in &banlist.limits {
        let key = canonical_id(id, catalog).unwrap_or(id);
        let n = |v| match v {
            Limit::Forbidden => 0,
            Limit::Limited => 1,
            Limit::SemiLimited => 2,
            Limit::Unlimited => 3,
        };
        let old = limits.get(&key).copied().unwrap_or(Limit::Unlimited);
        limits.insert(key, if n(old) < n(limit) { old } else { limit });
    }
    let mut report = normalized.validate(
        &Banlist::ocg(&banlist.version, limits),
        &DeckValidationRules::ocg(),
    );
    report.violations.extend(problems);
    report
}
pub fn validate_hand(deck: &Deck, hand: &[CardId]) -> Result<Vec<CardId>, String> {
    if hand.len() != 5 {
        return Err("opening hand must have exactly five cards".into());
    }
    let mut remaining = deck.main.clone();
    for card in hand {
        let index = remaining
            .iter()
            .position(|id| id == card)
            .ok_or_else(|| format!("hand contains unavailable card {}", card.0))?;
        remaining.remove(index);
    }
    Ok(remaining)
}
pub fn parse_deck(text: &str) -> Result<Deck, String> {
    let text = text.trim_start_matches('\u{feff}').trim();
    if text.starts_with('{') {
        return serde_json::from_str(text).map_err(|e| e.to_string());
    }
    let mut deck = Deck::default();
    let mut zone = "";
    for line in text.lines().map(str::trim).filter(|s| !s.is_empty()) {
        match line {
            "#main" => zone = "main",
            "#extra" => zone = "extra",
            "!side" => zone = "side",
            s if s.starts_with('#') => (),
            s => {
                let code = s
                    .parse::<u32>()
                    .map_err(|_| format!("invalid card code: {s}"))?;
                if code == 0 {
                    return Err("zero card code".into());
                }
                match zone {
                    "main" => deck.main.push(CardId(code)),
                    "extra" => deck.extra.push(CardId(code)),
                    "side" => deck.side.push(CardId(code)),
                    _ => return Err("YDK section missing".into()),
                }
            }
        }
    }
    Ok(deck)
}
