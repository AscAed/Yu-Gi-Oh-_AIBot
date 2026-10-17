use ygo_knowledge::first_turn::{certification::*, verification::*, FirstTurnKnowledge};

fn suite() -> NativeCases {
    serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap()
}

#[test]
fn reviewed_case_identity_rejects_replacing_assertions_or_rule_ownership() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let registry = ReviewedCases::builtin().unwrap();
    let suite = suite();
    registry.validate_suite(&pack, &suite).unwrap();
    let mut changed = suite.clone();
    changed.cases[0].assertions = vec![NativeAssertion::Count {
        card_id: 14558127,
        player: 1,
        location: 2,
        count: 1,
    }];
    assert!(registry.validate_suite(&pack, &changed).is_err());
    let mut changed = suite;
    changed.cases[0].rule_id = "26692769:deck_mill_and_set".into();
    assert!(registry.validate_suite(&pack, &changed).is_err());
}

#[test]
fn an_uncertified_view_cannot_promote_curated_status_or_potential_ash_effects() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let id = pack.id();
    let view = VerifiedKnowledge::uncertified(pack).unwrap();
    assert_eq!(view.knowledge().id(), id);
    assert!(view.certificates().is_empty());
    assert!(view.verified_ash_effects().is_empty());
    assert!(view.require_verified_coverage().is_err());
}

#[test]
fn reviewed_scythe_response_preserves_the_manual_case_identity() {
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-ash.json"
    ))
    .unwrap();
    ReviewedCases::builtin()
        .unwrap()
        .validate_suite(&FirstTurnKnowledge::builtin().unwrap(), &suite)
        .unwrap();
}

#[test]
fn independent_human_dependencies_have_frozen_case_assertions() {
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-dependencies.json"
    ))
    .unwrap();
    ReviewedCases::builtin()
        .unwrap()
        .validate_suite(&FirstTurnKnowledge::builtin().unwrap(), &suite)
        .unwrap();
}
