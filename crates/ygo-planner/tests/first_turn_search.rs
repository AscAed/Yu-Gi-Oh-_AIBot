//! Symbolic search tests are forecasts, never native rule certification.
use ygo_domain::{Card, CardId, Catalog};
use ygo_engine_adapter::*;
use ygo_goal::Goal;
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;
fn fixture() -> (CausalState, Catalog, Goal) {
    let mut cat = Catalog::new();
    for (code, kind, sets, level) in [
        (46072770, 0x21, 0x10db, 3),
        (25538345, 0x21, 0x10db, 3),
        (83566725, 0x21, 0x10db, 3),
        (36426778, 0x21, 0x10db, 3),
        (63821877, 0x21, 0x10db, 3),
        (85257384, 4, 0x10db, 0),
        (25542642, 4, 0xdb, 0),
        (78449284, 0x800021, 0x10db, 3),
        (26692769, 0x4000021, 0x10db, 3),
    ] {
        cat.insert(
            CardId(code),
            Card {
                id: CardId(code),
                name: code.to_string(),
                type_flags: kind,
                setcodes: vec![sets],
                attribute: if kind & 1 != 0 { 32 } else { 0 },
                race: if kind & 1 != 0 { 1 } else { 0 },
                level,
                ..Default::default()
            },
        );
    }
    let mut checkpoint = Checkpoint {
        turn: 1,
        turn_player: 0,
        phase: 4,
        ..Default::default()
    };
    for (code, zone, seq) in [
        (46072770, 2, 0),
        (25538345, 2, 1),
        (83566725, 2, 2),
        (36426778, 2, 3),
        (63821877, 2, 4),
        (78449284, 64, 0),
        (26692769, 64, 1),
        (85257384, 1, 0),
        (36426778, 1, 1),
        (46072770, 1, 2),
        (25542642, 1, 3),
        (63821877, 1, 4),
    ] {
        let c = &cat[&CardId(code)];
        checkpoint.cards.push(StateCard {
            code,
            player: 0,
            location: zone,
            sequence: seq,
            position: 10,
            type_flags: c.type_flags,
            level: Some(if c.type_flags & 0x4800000 == 0 {
                c.level
            } else {
                0
            }),
            rank: Some(if c.type_flags & 0x800000 != 0 {
                c.level
            } else {
                0
            }),
            attribute: Some(c.attribute),
            race: Some(c.race),
            link: Some(if c.type_flags & 0x4000000 != 0 { 3 } else { 0 }),
            is_public: Some(false),
            ..Default::default()
        });
    }
    let state = CausalState::initial(&first_turn_public_state(&checkpoint)).unwrap();
    let goal=serde_json::from_value(serde_json::json!({"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[26692769],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25542642],"locations":[8],"position_mask":10},"min":1}]}})).unwrap();
    (state, cat, goal)
}
#[test]
fn resource_search_finds_new_pilot_actions_without_importing_human_preparation() {
    let (s, cat, g) = fixture();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let found = propose_partial(&s, &cat, &pack, &g, &Default::default()).unwrap();
    assert!(!found.plans.is_empty(), "{:?}", found.limits);
    let sensitive = pack
        .potential_ash_effects()
        .iter()
        .map(|r| r.id.clone())
        .collect::<std::collections::BTreeSet<_>>();
    for p in &found.plans {
        assert_eq!(p.first_sensitive,p.steps.iter().find(|s|s.kind!=TransitionKind::DeclineTrigger&&sensitive.contains(&s.rule_id)).map(|s|s.rule_id.clone()));
    }

    assert!(found.plans.iter().any(|p| p
        .steps
        .iter()
        .any(|s| s.rule_id == "26692769:dark_link_three")));
    assert!(found.plans.iter().all(|p| p.steps.len() <= 64));
    assert!(found.expanded <= 5000);
    assert!(found.plans.len() <= 8);
    let repeat = propose_partial(&s, &cat, &pack, &g, &Default::default()).unwrap();
    assert_eq!(
        found.plans.iter().map(|p| &p.id).collect::<Vec<_>>(),
        repeat.plans.iter().map(|p| &p.id).collect::<Vec<_>>()
    );
}

#[test]
fn a_frozen_forecast_rejects_changed_start_identity_steps_limits_and_goal_evidence() {
    let (s, cat, goal) = fixture();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let plans = propose_partial(&s, &cat, &pack, &goal, &Default::default()).unwrap();
    let plan = &plans.plans[0];
    validate_forecast(plan, &s, &cat, &pack, &goal).unwrap();
    for field in ["id", "start_id", "knowledge_id", "goal_id"] {
        let mut v = serde_json::to_value(plan).unwrap();
        v[field] = serde_json::json!("forged");
        let forged: ForecastPlan = serde_json::from_value(v).unwrap();
        assert!(
            validate_forecast(&forged, &s, &cat, &pack, &goal).is_err(),
            "{field}"
        );
    }
    let mut forged = plan.clone();
    forged.predicted_resources += 1;
    assert!(validate_forecast(&forged, &s, &cat, &pack, &goal).is_err());
    forged = plan.clone();
    forged.steps[0].after_resolution.normal_remaining = None;
    assert!(validate_forecast(&forged, &s, &cat, &pack, &goal).is_err());
    forged = plan.clone();
    forged.limits.steps -= 1;
    assert!(validate_forecast(&forged, &s, &cat, &pack, &goal).is_err());
}
#[test]
fn changing_the_goal_changes_the_search_and_identity() {
    let (s, cat, mut g) = fixture();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let old = propose_partial(&s, &cat, &pack, &g, &Default::default()).unwrap();
    g.expr = serde_json::from_value(
        serde_json::json!({"op":"count","filter":{"codes":[85257384],"locations":[8]},"min":1}),
    )
    .unwrap();
    let changed = propose_partial(&s, &cat, &pack, &g, &Default::default()).unwrap();
    assert!(!changed.plans.is_empty());
    assert!(!changed.plans[0]
        .steps
        .iter()
        .any(|s| s.rule_id == "26692769:deck_mill_and_set"));
    assert_ne!(old.plans[0].id, changed.plans[0].id);
}
