use ygo_goal::Truth::*;
#[test]
fn boolean_goals_require_evidence_and_preserve_unknown() {
    assert_eq!(Yes.negate(), No);
    assert_eq!(Unknown.negate(), Unknown);
    assert_eq!(ygo_goal::Truth::all([Yes, Unknown]), Unknown);
    assert_eq!(ygo_goal::Truth::all([No, Unknown]), No);
    assert_eq!(ygo_goal::Truth::any([No, Unknown]), Unknown);
    assert_eq!(ygo_goal::Truth::any([Yes, Unknown]), Yes);
}
