use std::collections::BTreeMap;
use ygo_goal::*;
#[test]
fn matches_all_properties_on_one_instance_not_a_card_name() {
    let f = Filter {
        codes: vec![62709239],
        materials_min: Some(2),
        proper_xyz: Some(true),
        ..Default::default()
    };
    let facts = Facts {
        cards: vec![
            FactCard {
                instance: "a".into(),
                code: 62709239,
                proper_xyz: Some(true),
                materials: vec![],
                ..Default::default()
            },
            FactCard {
                instance: "b".into(),
                code: 62709239,
                proper_xyz: Some(false),
                materials: vec![1, 1],
                ..Default::default()
            },
        ],
        ..Default::default()
    };
    assert_eq!(
        evaluate(
            &Expr::Count {
                filter: f,
                min: 1,
                max: None
            },
            &facts,
            &BTreeMap::new()
        )
        .result,
        Truth::No
    );
}
#[test]
fn rejected_goals_include_recursive_probes_duplicate_metrics_and_unknown_fields() {
    let e: Expr = serde_json::from_value(
        serde_json::json!({"op":"available","effect_id":"x","filter":{},"window":"main_end"}),
    )
    .unwrap();
    let g = Goal {
        version: 1,
        expr: Expr::Continuation {
            goal: Box::new(e),
            gains: vec![],
            max_steps: None,
        },
        continuation_steps: 4,
        max_aux_candidates: 8,
        gain_order: vec![],
    };
    assert!(g.validate().is_err());
    assert!(serde_json::from_value::<Expr>(
        serde_json::json!({"op":"count","filter":{},"min":1,"invented":true})
    )
    .is_err());
}
#[test]
fn history_unknown_does_not_prove_absence_and_goal_ids_cover_budgets() {
    let e = Expr::History {
        kind: "xyz_summon".into(),
        filter: Default::default(),
        effect_id: None,
        reason_mask: None,
        min: 1,
        max: None,
    };
    let v = evaluate(
        &Expr::Not {
            arg: Box::new(e.clone()),
        },
        &Facts::default(),
        &BTreeMap::new(),
    );
    assert_eq!(v.result, Truth::Unknown);
    let mut g = Goal {
        version: 1,
        expr: e,
        continuation_steps: 4,
        max_aux_candidates: 8,
        gain_order: vec![],
    };
    let id = g.id();
    g.continuation_steps = 5;
    assert_ne!(id, g.id());
}
#[test]
fn equivalent_filter_sets_have_the_same_canonical_goal_identity() {
    let mut a = Goal {
        version: 1,
        expr: Expr::Count {
            filter: Filter {
                codes: vec![2, 1, 1],
                locations: vec![8, 4, 4],
                ..Default::default()
            },
            min: 1,
            max: None,
        },
        continuation_steps: 4,
        max_aux_candidates: 8,
        gain_order: vec![],
    };
    let id = a.id();
    if let Expr::Count { filter, .. } = &mut a.expr {
        filter.codes = vec![1, 2];
        filter.locations = vec![4, 8];
    }
    assert_eq!(id, a.id());
}
#[test]
fn unavailable_position_and_identity_are_unknown_instead_of_false() {
    let card = FactCard {
        code: 1,
        instance: "unresolved".into(),
        ..Default::default()
    };
    assert_eq!(
        Filter {
            position_mask: Some(8),
            ..Default::default()
        }
        .matches(&card),
        Truth::Unknown
    );
    assert_eq!(
        Filter {
            instance: Some("original".into()),
            ..Default::default()
        }
        .matches(&card),
        Truth::Unknown
    );
}
#[test]
fn link_and_xyz_rank_are_not_monster_levels_even_when_query_returns_zero() {
    let xyz = FactCard {
        type_flags: 0x800021,
        level: Some(0),
        rank: Some(3),
        ..Default::default()
    };
    assert_eq!(
        Filter {
            level: Some(0),
            ..Default::default()
        }
        .matches(&xyz),
        Truth::No
    );
    assert_eq!(
        Filter {
            rank: Some(3),
            ..Default::default()
        }
        .matches(&xyz),
        Truth::Yes
    );
    let link = FactCard {
        type_flags: 0x4000021,
        level: Some(0),
        rank: Some(0),
        ..Default::default()
    };
    assert_eq!(
        Filter {
            rank: Some(0),
            ..Default::default()
        }
        .matches(&link),
        Truth::No
    );
}
#[test]
fn gain_predicates_share_the_total_expression_node_limit() {
    let gains: Vec<_> = (0..64)
        .map(|i| Gain {
            id: format!("g{i}"),
            filter: Default::default(),
            min_delta: 1,
        })
        .collect();
    let goal = Goal {
        version: 1,
        gain_order: gains.iter().map(|g| g.id.clone()).collect(),
        expr: Expr::Continuation {
            goal: Box::new(Expr::Count {
                filter: Default::default(),
                min: 0,
                max: None,
            }),
            gains,
            max_steps: None,
        },
        continuation_steps: 4,
        max_aux_candidates: 8,
    };
    assert!(goal.validate().is_err());
}
