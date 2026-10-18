use ygo_knowledge::first_turn::*;

#[test]
fn complete_classification_is_separate_from_implemented_and_verified_coverage() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    assert_eq!(pack.cards.len(), 39);
    assert_eq!(pack.rules.len(), 102);
    assert_eq!(pack.rules.iter().filter(|r| r.applicable).count(), 86);
    assert!(pack.require_verified_coverage().is_err());
    assert!(pack.verified_ash_effects().is_empty());
    let candidates = pack.potential_ash_effects();
    assert!(candidates.iter().any(|r| r.id == "78449284:deck_special"));
    assert!(candidates
        .iter()
        .any(|r| r.id == "99745551:random_discard_special_draw"));
    assert!(!candidates.iter().any(|r| r.id == "83566725:deck_set"));
    assert!(!candidates
        .iter()
        .any(|r| r.id == "58699500:cost_mill_and_stat_boost"));
}

#[test]
fn first_turn_knowledge_rejects_ambiguous_binding_and_unbacked_verified_claims() {
    let mut pack = FirstTurnKnowledge::builtin().unwrap();
    let i = pack
        .rules
        .iter()
        .position(|r| r.id == "78449284:deck_special")
        .unwrap();
    pack.rules[i].description = Some(0);
    assert!(pack.validate().is_err());
    let mut pack = FirstTurnKnowledge::builtin().unwrap();
    pack.rules[i].status = ImplementationStatus::Verified;
    assert!(pack.validate().is_err());
    let mut pack = FirstTurnKnowledge::builtin().unwrap();
    pack.rules.pop();
    assert!(pack.validate().is_err());
}

#[test]
fn imported_json_cannot_certify_itself_or_swap_source_cards() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let mut value = serde_json::to_value(pack).unwrap();
    value["rules"][0]["status"] = "verified".into();
    value["rules"][0]["evidence_cases"] =
        serde_json::json!(["invented-positive", "invented-negative"]);
    let imported: FirstTurnKnowledge = serde_json::from_value(value.clone()).unwrap();
    assert!(imported.validate().is_err());
    assert!(imported.verified_ash_effects().is_empty());
    value["certified"] = serde_json::json!(["83566725:normal_summon_and_set"]);
    assert!(serde_json::from_value::<FirstTurnKnowledge>(value).is_err());
    let mut changed = FirstTurnKnowledge::builtin().unwrap();
    changed.cards[0].script_sha256 = "0".repeat(64);
    assert!(changed.validate().is_err());
}

#[test]
fn source_filter_distinguishes_the_phantom_knights_from_broader_family() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let set = pack.rule("83566725:deck_set").unwrap();
    let search = pack.rule("36426778:grave_spell_trap_search").unwrap();
    let fog = ygo_domain::Card {
        id: ygo_domain::CardId(25542642),
        type_flags: 4,
        setcodes: vec![0xdb],
        ..Default::default()
    };
    let veil = ygo_domain::Card {
        id: ygo_domain::CardId(85257384),
        type_flags: 4,
        setcodes: vec![0x10db],
        ..Default::default()
    };
    assert_eq!(
        set.selections[0].filter.matches(Some(&fog)),
        ygo_knowledge::Truth::No
    );
    assert_eq!(
        set.selections[0].filter.matches(Some(&veil)),
        ygo_knowledge::Truth::Yes
    );
    assert_eq!(
        search.selections[0].filter.matches(Some(&fog)),
        ygo_knowledge::Truth::Yes
    );
}

#[test]
#[ignore = "opt-in: independent frozen 2026 CDB and scripts, no engine call"]
fn curated_first_turn_sources_match_actual_frozen_asset_bytes() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../data/runtime/tournament-2026/frozen");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    pack.validate_sources(&root).unwrap();
    let mut changed = pack.clone();
    changed.cards[0].text_sha256 = "0".repeat(64);
    assert!(changed.validate_sources(&root).is_err());
}

#[test]
fn rusty_deck_mill_set_is_not_a_hand_discard_operation() {
    let pack = ygo_knowledge::first_turn::FirstTurnKnowledge::builtin().unwrap();
    let effect = pack.rule("26692769:deck_mill_and_set").unwrap();
    assert_eq!(
        effect.operation,
        ygo_knowledge::first_turn::Operation::DeckMillSet
    );
    assert!(effect.costs.is_empty());
    assert!(effect.selections.iter().all(|s| s.stage != "cost"));
}
