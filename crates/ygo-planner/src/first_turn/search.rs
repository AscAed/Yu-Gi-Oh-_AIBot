//! Bounded forecasts for internal integration. No engine verification is claimed.
use super::*;
mod resume;
pub use resume::{ResumableSearch, SearchCheckpoint};
use ygo_goal::{FactCard, Facts, Goal};
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SearchLimits {
    pub candidates: usize,
    pub expansions: usize,
    pub frontier: usize,
    pub steps: usize,
}
impl Default for SearchLimits {
    fn default() -> Self {
        Self {
            candidates: 8,
            expansions: 5000,
            frontier: 32,
            steps: 64,
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ForecastPlan {
    pub id: String,
    pub start_id: String,
    pub knowledge_id: String,
    pub limits: SearchLimits,
    pub goal_id: String,
    pub first_sensitive: Option<String>,
    pub steps: Vec<Transition>,
    pub predicted_goal: ygo_goal::Evaluation,
    pub predicted_resources: usize,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialPlans {
    pub scope: String,
    pub plans: Vec<ForecastPlan>,
    pub expanded: usize,
    pub limits: SearchLimits,
    pub termination: String,
    pub unknowns: Vec<String>,
    pub coverage_gaps: Vec<String>,
}
/// A predicted fact view; histories and probes are deliberately not asserted.
pub fn forecast_facts(state: &CausalState) -> Facts {
    Facts {
        known_effects: vec![],
        cards: state
            .cards
            .iter()
            .filter(|c| c.host.is_none())
            .map(|c| FactCard {
                instance: c.id.clone(),
                identity_known: c.identity_known,
                type_flags: c.card.type_flags,
                code: c.card.code,
                player: c.card.player,
                location: c.card.location,
                sequence: c.card.sequence,
                position: c.card.position,
                level: c.card.level,
                rank: c.card.rank,
                proper_xyz: c.proper_xyz,
                materials: c.card.overlay.clone(),
                materials_complete: Some(true),
            })
            .collect(),
        history: vec![],
        history_complete: false,
    }
}
fn resources(state: &CausalState) -> usize {
    state
        .cards
        .iter()
        .filter(|c| c.card.player == 0 && matches!(c.card.location, 2 | 4 | 8))
        .count()
}
fn hash<T: Serialize>(value: &T) -> String {
    ygo_knowledge::hash(&serde_json::to_vec(value).expect("forecast serialization"))
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Node {
    state: CausalState,
    steps: Vec<Transition>,
    seen: Vec<String>,
    first: Option<String>,
    score: i64,
}
fn plan(
    node: &Node,
    goal: &Goal,
    pack: &FirstTurnKnowledge,
    limits: &SearchLimits,
    start: &str,
) -> ForecastPlan {
    ForecastPlan {
        id: hash(&(
            "partial_integration",
            "phantom-first-turn-v1",
            pack.id(),
            goal.id(),
            limits,
            start,
            &node.steps,
        )),
        start_id: start.into(),
        knowledge_id: pack.id(),
        limits: limits.clone(),
        goal_id: goal.id(),
        first_sensitive: node.first.clone(),
        steps: node.steps.clone(),
        predicted_goal: ygo_goal::evaluate(
            &goal.expr,
            &forecast_facts(&node.state),
            &Default::default(),
        ),
        predicted_resources: resources(&node.state),
    }
}
/// Recompute a frozen forecast from its actual start and causal operators.
/// This validates predictions, not native rule qualification or execution.
pub fn validate_forecast(
    forecast: &ForecastPlan,
    initial: &CausalState,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
) -> Result<(), String> {
    initial.validate(cat)?;
    goal.validate()?;
    pack.validate()?;
    let limits = &forecast.limits;
    if !(1..=8).contains(&limits.candidates)
        || !(1..=5000).contains(&limits.expansions)
        || !(1..=32).contains(&limits.frontier)
        || !(1..=64).contains(&limits.steps)
        || forecast.steps.len() > limits.steps
    {
        return Err("invalid forecast limits".into());
    }
    let mut state = initial.clone();
    let mut first = None;
    let sensitive = pack
        .potential_ash_effects()
        .iter()
        .map(|r| r.id.as_str())
        .collect::<BTreeSet<_>>();
    for step in &forecast.steps {
        let options = successors(&state, cat, pack);
        if !options
            .transitions
            .iter()
            .any(|t| serde_json::to_value(t).unwrap() == serde_json::to_value(step).unwrap())
        {
            return Err("forecast transition contradicts its causal start".into());
        }
        if first.is_none()
            && step.kind != TransitionKind::DeclineTrigger
            && sensitive.contains(step.rule_id.as_str())
        {
            first = Some(step.rule_id.clone());
        }
        state = step.after_resolution.clone();
    }
    let expected = plan(
        &Node {
            state,
            steps: forecast.steps.clone(),
            seen: vec![],
            first,
            score: 0,
        },
        goal,
        pack,
        limits,
        &hash(initial),
    );
    if serde_json::to_value(expected).unwrap() != serde_json::to_value(forecast).unwrap() {
        return Err("frozen forecast identity, goal, or ranking evidence differs".into());
    }
    Ok(())
}
/// This entry accepts a partial model for experiments. Formal v6 must additionally
/// require verified coverage; forecasts cannot grant that qualification.
pub fn propose_partial(
    initial: &CausalState,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    limits: &SearchLimits,
) -> Result<PartialPlans, String> {
    initial.validate(cat)?;
    pack.validate()?;
    goal.validate()?;
    if !(1..=8).contains(&limits.candidates)
        || !(1..=5000).contains(&limits.expansions)
        || !(1..=32).contains(&limits.frontier)
        || !(1..=64).contains(&limits.steps)
    {
        return Err("invalid bounded first-turn limits".into());
    }
    let start = hash(initial);
    let mut frontier = vec![Node {
        state: initial.clone(),
        steps: vec![],
        seen: vec![start.clone()],
        first: None,
        score: 0,
    }];
    let mut output = PartialPlans {
        scope: "partial_integration_forecast".into(),
        plans: vec![],
        expanded: 0,
        limits: limits.clone(),
        termination: "exhausted_supported_model".into(),
        unknowns: vec![],
        coverage_gaps: vec![],
    };
    let sensitive = pack
        .potential_ash_effects()
        .iter()
        .map(|r| r.id.clone())
        .collect::<BTreeSet<_>>();
    let mut unknowns = BTreeSet::new();
    let mut gaps = BTreeSet::new();
    let mut plan_ids = BTreeSet::new();
    for depth in 0..=limits.steps {
        let mut next = vec![];
        for node in frontier {
            if output.expanded >= limits.expansions {
                output.termination = "symbolic_expansion_budget".into();
                break;
            }
            output.expanded += 1;
            let facts = forecast_facts(&node.state);
            let evaluation = ygo_goal::evaluate(&goal.expr, &facts, &Default::default());
            if evaluation.result == ygo_goal::Truth::Yes && node.state.pending.is_empty() {
                let p = plan(&node, goal, pack, limits, &start);
                if plan_ids.insert(p.id.clone()) {
                    output.plans.push(p);
                }
                output.plans.sort_by_key(|p| {
                    (
                        std::cmp::Reverse(p.predicted_resources),
                        p.steps.len(),
                        p.id.clone(),
                    )
                });
                // Keep a first-sensitive alternative before filling remaining candidate slots.
                let mut keep = vec![];
                let mut classes = BTreeSet::new();
                for (i, p) in output.plans.iter().enumerate() {
                    if classes.insert(p.first_sensitive.clone()) && keep.len() < limits.candidates {
                        keep.push(i);
                    }
                }
                for i in 0..output.plans.len() {
                    if keep.len() == limits.candidates {
                        break;
                    }
                    if !keep.contains(&i) {
                        keep.push(i);
                    }
                }
                keep.sort_unstable();
                output.plans = output
                    .plans
                    .into_iter()
                    .enumerate()
                    .filter(|(i, _)| keep.contains(i))
                    .map(|(_, p)| p)
                    .collect();
                continue;
            }
            if depth == limits.steps {
                output.termination = "symbolic_step_budget".into();
                continue;
            }
            let expanded = successors(&node.state, cat, pack);
            unknowns.extend(expanded.unknowns);
            gaps.extend(expanded.coverage_gaps);
            for step in expanded.transitions {
                let id = hash(&step.after_resolution);
                if node.seen.contains(&id) {
                    continue;
                }
                let mut seen = node.seen.clone();
                seen.push(id.clone());
                let first = node.first.clone().or_else(|| {
                    (step.kind != TransitionKind::DeclineTrigger
                        && sensitive.contains(&step.rule_id))
                    .then(|| step.rule_id.clone())
                });
                let state = step.after_resolution.clone();
                let score = crate::v3::goal_priority(&goal.expr, &forecast_facts(&state));
                let mut steps = node.steps.clone();
                steps.push(step);
                next.push(Node {
                    state,
                    steps,
                    seen,
                    first,
                    score,
                });
            }
        }
        if output.expanded >= limits.expansions || next.is_empty() {
            break;
        }
        next.sort_by_cached_key(|n| {
            (
                std::cmp::Reverse(n.score),
                std::cmp::Reverse(resources(&n.state)),
                n.steps.len(),
                hash(&n.steps),
            )
        });
        let mut classes = BTreeSet::new();
        let mut chosen = vec![];
        for (i, node) in next.iter().enumerate() {
            let last = node
                .steps
                .last()
                .and_then(|s| pack.rule(&s.rule_id))
                .map(|r| format!("{:?}", r.operation));
            if classes.insert((node.first.clone(), last)) && chosen.len() < limits.frontier {
                chosen.push(i);
            }
        }
        for i in 0..next.len() {
            if chosen.len() == limits.frontier {
                break;
            }
            if !chosen.contains(&i) {
                chosen.push(i);
            }
        }
        chosen.sort_unstable();
        frontier = next
            .into_iter()
            .enumerate()
            .filter(|(i, _)| chosen.contains(i))
            .map(|(_, n)| n)
            .collect();
    }
    output.unknowns = unknowns.into_iter().collect();
    output.coverage_gaps = gaps.into_iter().collect();
    Ok(output)
}

/// Build a validated zero-operation forecast for a caller that only wants to
/// advance an already observed prompt through End Phase and query audit.
pub fn empty_forecast_plan(
    initial: &CausalState,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    limits: &SearchLimits,
) -> Result<ForecastPlan, String> {
    initial.validate(catalog)?;
    pack.validate()?;
    goal.validate()?;
    let start = hash(initial);
    Ok(plan(
        &Node {
            state: initial.clone(),
            steps: Vec::new(),
            seen: Vec::new(),
            first: None,
            score: 0,
        },
        goal,
        pack,
        limits,
        &start,
    ))
}
