use ygo_goal::*;
use ygo_planner::{v2::*, v3};
#[test]
fn forecasts_identify_negated_loss_and_reverse_contribution_before_execution() {
    let x = Resource {
        instance: "x".into(),
        code: 1,
        location: 4,
        level: 3,
        redirect: false,
        player: 0,
        overlay_host: None,
        xyz_summoned: false,
        base_level: 3,
        epoch: 0,
    };
    let empty = SymbolicState {
        cards: vec![],
        used: Default::default(),
        normal_left: 1,
        pending: vec![],
        dark_only: false,
        destroyed_xyz: Default::default(),
    };
    let mut field = empty.clone();
    field.cards.push(x.clone());
    let goal: Goal = serde_json::from_value(serde_json::json!({"version":1,"expr":{
        "op":"not","arg":{"op":"count","filter":{"codes":[1]},"min":1}}}))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    for (before, after, loss) in [(&empty, &field, true), (&field, &empty, false)] {
        let p = Proposal {
            id: "test".into(),
            goal_predicted: !loss,
            steps: vec![SemanticStep {
                kind: StepKind::SpecialSummon,
                effect_id: "test".into(),
                source: x.clone(),
                costs: vec![],
                targets: vec![],
                reason: "test".into(),
                after: after.clone(),
            }],
        };
        let fs = v3::forecasts(before, &[], &p, &Default::default(), &goal, None, &pack);
        assert_eq!(fs[0].lost_nodes, if loss { vec!["/goal"] } else { vec![] });
        assert_eq!(
            fs[0].contribution_nodes,
            if loss { vec![] } else { vec!["/goal"] }
        );
    }
}
#[test]
fn already_satisfied_goal_has_a_zero_expansion_proposal() {
    let state = SymbolicState {
        cards: vec![],
        used: Default::default(),
        normal_left: 1,
        pending: vec![],
        dark_only: false,
        destroyed_xyz: Default::default(),
    };
    let goal = Goal {
        version: 1,
        expr: Expr::Count {
            filter: Default::default(),
            min: 0,
            max: None,
        },
        continuation_steps: 4,
        max_aux_candidates: 8,
        gain_order: vec![],
    };
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut expanded = 0;
    let p = v3::propose_from(
        state,
        &Default::default(),
        &pack,
        &goal,
        1,
        32,
        &mut expanded,
    )
    .unwrap();
    assert_eq!(p.plans.len(), 1);
    assert!(p.plans[0].steps.is_empty());
}
#[test]
fn upper_count_goals_prefer_fewer_resources_without_discarding_minimum_goals() {
    let f = |n| Facts {
        cards: (0..n)
            .map(|i| FactCard {
                instance: i.to_string(),
                code: 1,
                location: 2,
                ..Default::default()
            })
            .collect(),
        ..Default::default()
    };
    let upper = Expr::Count {
        filter: Filter {
            locations: vec![2],
            ..Default::default()
        },
        min: 0,
        max: Some(0),
    };
    assert!(v3::goal_priority(&upper, &f(1)) > v3::goal_priority(&upper, &f(3)));
    let lower = Expr::Count {
        filter: Filter {
            locations: vec![2],
            ..Default::default()
        },
        min: 4,
        max: None,
    };
    assert!(v3::goal_priority(&lower, &f(3)) > v3::goal_priority(&lower, &f(1)));
}
#[test]
fn trap_monster_level_is_zero_until_it_becomes_a_monster() {
    let ids = [98827725, 25542642, 81439173, 32807846, 25538345].map(ygo_domain::CardId);
    let deck = ygo_domain::Deck::new(ids.to_vec(), vec![], vec![]);
    let mut cat = ygo_domain::Catalog::new();
    for id in ids {
        cat.insert(
            id,
            ygo_domain::Card {
                id,
                type_flags: if id.0 == 25538345 { 33 } else { 4 },
                level: if id.0 == 98827725 { 4 } else { 0 },
                ..Default::default()
            },
        );
    }
    let state = v3::initialize(&deck, &ids, &cat).unwrap();
    let shade = state.cards.iter().find(|c| c.code == 98827725).unwrap();
    assert_eq!((shade.level, shade.base_level), (0, 0));
}
#[test]
fn irreversible_history_conflicts_are_pruned_but_current_shortages_are_not() {
    let history = Expr::History {
        kind: "effect_resolved".into(),
        filter: Default::default(),
        effect_id: Some("x".into()),
        reason_mask: None,
        min: 0,
        max: Some(0),
    };
    let facts = Facts {
        history: vec![HistoryFact {
            kind: "effect_resolved".into(),
            card: Default::default(),
            effect_id: Some("x".into()),
            reason: 0,
            reason_complete: true,
            event: 1,
        }],
        history_complete: true,
        ..Default::default()
    };
    assert!(!v3::goal_may_still_hold(&history, &facts));
    let field = Expr::Count {
        filter: Filter {
            locations: vec![4],
            ..Default::default()
        },
        min: 1,
        max: None,
    };
    assert!(v3::goal_may_still_hold(
        &Expr::Any {
            args: vec![history.clone(), field.clone()]
        },
        &facts
    ));
    assert!(!v3::goal_may_still_hold(
        &Expr::All {
            args: vec![history, field.clone()]
        },
        &facts
    ));
    assert!(v3::goal_may_still_hold(&field, &facts));
}
