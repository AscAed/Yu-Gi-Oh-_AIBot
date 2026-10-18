use std::collections::BTreeMap;
use ygo_goal::*;
fn present() -> Expr {
    Expr::Count {
        filter: Filter {
            codes: vec![1],
            ..Default::default()
        },
        min: 1,
        max: None,
    }
}
#[test]
fn negation_and_double_negation_are_conditions_with_their_own_truth() {
    let f = Facts::default();
    let not = Expr::Not {
        arg: Box::new(present()),
    };
    let double = Expr::Not {
        arg: Box::new(not.clone()),
    };
    for (expr, truth) in [(not, Truth::Yes), (double, Truth::No)] {
        let ev = evaluate(&expr, &f, &BTreeMap::new());
        assert_eq!(
            condition_values(&expr, &ev),
            BTreeMap::from([("/goal".into(), truth)])
        );
    }
}
#[test]
fn boolean_groups_keep_negated_condition_paths_and_do_not_invert_unknown() {
    let missing_identity = Filter {
        instance: Some("unresolved".into()),
        ..Default::default()
    };
    let unknown = Expr::Not {
        arg: Box::new(Expr::Count {
            filter: missing_identity,
            min: 1,
            max: None,
        }),
    };
    let facts = Facts {
        cards: vec![FactCard {
            code: 1,
            ..Default::default()
        }],
        ..Default::default()
    };
    let not = Expr::Not {
        arg: Box::new(present()),
    };
    for expr in [
        Expr::All {
            args: vec![present(), not.clone(), unknown.clone()],
        },
        Expr::Any {
            args: vec![present(), not, unknown],
        },
    ] {
        let ev = evaluate(&expr, &facts, &BTreeMap::new());
        let values = condition_values(&expr, &ev);
        assert_eq!(values["/goal/1"], Truth::No);
        assert_eq!(values["/goal/2"], Truth::Unknown);
        if matches!(expr, Expr::Any { .. }) {
            assert_eq!(ev.result, Truth::Yes);
        }
    }
}
