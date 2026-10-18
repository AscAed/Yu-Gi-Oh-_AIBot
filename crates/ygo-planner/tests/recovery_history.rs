use std::collections::BTreeSet;
use ygo_goal::*;
use ygo_planner::{v2::SymbolicState, v3};
#[test]
fn recovery_proposals_keep_already_observed_history_without_repeating_the_action() {
    let state = SymbolicState {
        cards: vec![],
        used: BTreeSet::new(),
        normal_left: 0,
        pending: vec![],
        dark_only: false,
        destroyed_xyz: BTreeSet::new(),
    };
    let goal: Goal = serde_json::from_value(
        serde_json::json!({"version":1,"expr":{"op":"history","kind":"normal_summon","min":1}}),
    )
    .unwrap();
    let past = Facts {
        history_complete: true,
        history: vec![HistoryFact {
            kind: "normal_summon".into(),
            card: FactCard::default(),
            effect_id: None,
            reason: 0,
            reason_complete: true,
            event: 3,
        }],
        ..Default::default()
    };
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let plans = v3::propose_from_seeded(
        state,
        &Default::default(),
        &pack,
        &goal,
        1,
        1,
        &mut 0,
        Some(&past),
    )
    .unwrap();
    assert_eq!(plans.plans.len(), 1);
    assert!(plans.plans[0].steps.is_empty());
}
