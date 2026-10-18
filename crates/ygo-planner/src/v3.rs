use crate::v2::*;
use std::collections::{BTreeMap, BTreeSet};
use ygo_domain::{CardId, Catalog};
use ygo_goal::{count, evaluate, Evaluation, Expr, FactCard, Facts, Goal, HistoryFact, Truth};
use ygo_knowledge::{KnowledgePack, Rule};
pub const PROFILE: &str = "phantom-goal-v2";
pub fn initialize(
    deck: &ygo_domain::Deck,
    hand: &[CardId],
    cat: &Catalog,
) -> Result<SymbolicState, String> {
    let mut state = initial_state(deck, hand, cat)?;
    for c in &mut state.cards {
        if cat
            .get(&CardId(c.code))
            .is_some_and(|card| card.type_flags & 1 == 0)
        {
            c.level = 0;
            c.base_level = 0;
        }
    }
    Ok(state)
}
fn facts_seeded(
    state: &SymbolicState,
    history: &[SemanticStep],
    cat: &Catalog,
    pack: &KnowledgePack,
    prefix: Option<&Facts>,
) -> Facts {
    let mut f = facts(state, history, cat, pack);
    if let Some(p) = prefix {
        let mut past = p.history.clone();
        past.extend(f.history);
        f.history = past;
        f.history_complete &= p.history_complete;
    }
    f
}
pub fn proposal_id(pack: &KnowledgePack, goal: &Goal, steps: &[SemanticStep]) -> String {
    ygo_knowledge::hash(
        &serde_json::to_vec(&(PROFILE, pack.id(), goal.id(), steps))
            .expect("proposal serialization"),
    )
}
pub fn facts(
    state: &SymbolicState,
    history: &[SemanticStep],
    cat: &Catalog,
    pack: &KnowledgePack,
) -> Facts {
    let card_at = |r: &Resource, context: &SymbolicState| FactCard {
        instance: r.instance.clone(),
        identity_known: false,
        type_flags: cat.get(&CardId(r.code)).map_or(0, |c| c.type_flags)
            | if r.location == 4 && r.level > 0 { 1 } else { 0 },
        code: r.code,
        player: r.player,
        location: r.location,
        sequence: 0,
        position: if matches!(r.location, 1 | 8 | 64) {
            8
        } else if matches!(r.location, 16 | 32) {
            0
        } else {
            1
        },
        level: Some(r.level),
        rank: Some(
            cat.get(&CardId(r.code))
                .filter(|c| c.type_flags & 0x800000 != 0)
                .map_or(0, |c| c.level),
        ),
        proper_xyz: Some(r.xyz_summoned),
        materials_complete: None,
        materials: context
            .cards
            .iter()
            .filter(|m| m.overlay_host.as_deref() == Some(&r.instance))
            .map(|m| m.code)
            .collect(),
    };
    let cards = state
        .cards
        .iter()
        .filter(|c| c.location & 128 == 0)
        .map(|r| card_at(r, state))
        .collect();
    let mut events = vec![];
    for (i, step) in history.iter().enumerate() {
        let prior = if i > 0 {
            &history[i - 1].after
        } else {
            &step.after
        };
        let kind = match step.kind {
            StepKind::NormalSummon => Some("normal_summon"),
            StepKind::SpecialSummon => Some("special_summon"),
            StepKind::LinkSummon => Some("link_summon"),
            StepKind::XyzSummon => Some("xyz_summon"),
            StepKind::Activate | StepKind::Trigger => Some("effect_resolved"),
            _ => None,
        };
        if let Some(kind) = kind {
            let actor = if kind.ends_with("summon") {
                step.after
                    .cards
                    .iter()
                    .find(|c| c.instance == step.source.instance)
                    .map(|r| card_at(r, &step.after))
                    .unwrap_or_else(|| card_at(&step.source, prior))
            } else {
                card_at(&step.source, prior)
            };
            events.push(HistoryFact {
                kind: kind.into(),
                card: actor,
                effect_id: if kind == "effect_resolved" {
                    Some(step.effect_id.clone())
                } else {
                    None
                },
                reason: 0,
                reason_complete: false,
                event: i as u64,
            });
        }
        let mut seen = BTreeSet::new();
        let inputs: Vec<_> = if i > 0 {
            prior.cards.iter().collect()
        } else {
            std::iter::once(&step.source)
                .chain(&step.costs)
                .chain(&step.targets)
                .collect()
        };
        for before in inputs {
            if !seen.insert(before.instance.clone()) {
                continue;
            }
            if let Some(after) = step
                .after
                .cards
                .iter()
                .find(|r| r.instance == before.instance)
            {
                if after.location == 16 && before.location != 16 {
                    let cost = step.costs.iter().any(|c| c.instance == before.instance);
                    let reason = if matches!(step.kind, StepKind::LinkSummon) {
                        8 | 0x10000000
                    } else if cost {
                        128
                    } else if before.location & 128 != 0 {
                        1024
                    } else {
                        64
                    };
                    events.push(HistoryFact {
                        kind: "sent_to_grave".into(),
                        card: card_at(after, &step.after),
                        effect_id: None,
                        reason,
                        reason_complete: false,
                        event: i as u64,
                    });
                }
                if before.location != 4
                    && after.location == 4
                    && !(before.instance == step.source.instance
                        && matches!(step.kind, StepKind::NormalSummon | StepKind::SpecialSummon))
                {
                    events.push(HistoryFact {
                        kind: "special_summon".into(),
                        card: card_at(after, &step.after),
                        effect_id: None,
                        reason: 0,
                        reason_complete: false,
                        event: i as u64,
                    });
                }
                if step.effect_id.ends_with(":destroy")
                    && step.targets.iter().any(|t| t.instance == before.instance)
                {
                    let mut origin = card_at(before, prior);
                    for cost in step
                        .costs
                        .iter()
                        .filter(|c| c.overlay_host.as_deref() == Some(&before.instance))
                    {
                        if let Some(j) = origin.materials.iter().position(|code| *code == cost.code)
                        {
                            origin.materials.remove(j);
                        }
                    }
                    events.push(HistoryFact {
                        kind: "destroyed".into(),
                        card: origin,
                        effect_id: None,
                        reason: 65,
                        reason_complete: false,
                        event: i as u64,
                    });
                }
            }
        }
    }
    Facts {
        known_effects: pack
            .cards
            .iter()
            .flat_map(|c| c.effects.iter())
            .filter(|e| e.description_index.is_some())
            .map(|e| e.id.clone())
            .collect(),
        cards,
        history: events,
        history_complete: true,
    }
}

pub fn transitions(
    state: &SymbolicState,
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
) -> Vec<SemanticStep> {
    successors(state, cat, pack)
        .into_iter()
        .map(|mut s| {
            s.reason = if let Some(e) = pack.effect(&s.effect_id) {
                format!(
                    "目标 {}；{}：{}。条件：{}；费用：{}；限制：{}。此为执行前预测。",
                    goal.id(),
                    e.id,
                    e.operations.join("；"),
                    e.conditions.join("；"),
                    e.costs.join("；"),
                    e.restrictions.join("；")
                )
            } else {
                format!(
                    "目标 {}；{:?} {}；转移资源以满足目标缺口，仍需引擎验证。",
                    goal.id(),
                    s.kind,
                    s.source.code
                )
            };
            s
        })
        .collect()
}
#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Forecast {
    pub kind: String,
    pub proposal_id: String,
    pub semantic_step: usize,
    pub effect_id: String,
    pub before: Facts,
    pub goal_before: Evaluation,
    pub goal_after: Evaluation,
    pub branch_before: Option<Evaluation>,
    pub branch_after: Option<Evaluation>,
    pub missing_nodes: Vec<String>,
    pub contribution_nodes: Vec<String>,
    pub lost_nodes: Vec<String>,
    pub consumers: Vec<String>,
    pub gain_prediction: BTreeMap<String, i64>,
}
/// Built before an adapter call, and reproducible from the frozen planning inputs.
#[allow(clippy::too_many_arguments)]
pub fn forecasts(
    initial: &SymbolicState,
    history: &[SemanticStep],
    proposal: &Proposal,
    cat: &Catalog,
    goal: &Goal,
    branch: Option<&Expr>,
    pack: &KnowledgePack,
) -> Vec<Forecast> {
    forecasts_seeded(initial, history, proposal, cat, goal, branch, pack, None)
}
#[allow(clippy::too_many_arguments)]
pub fn forecasts_seeded(
    initial: &SymbolicState,
    history: &[SemanticStep],
    proposal: &Proposal,
    cat: &Catalog,
    goal: &Goal,
    branch: Option<&Expr>,
    pack: &KnowledgePack,
    prefix: Option<&Facts>,
) -> Vec<Forecast> {
    let anchor = facts_seeded(initial, history, cat, pack, prefix);
    let mut state = initial.clone();
    let mut prior = history.to_vec();
    let mut out = vec![];
    for (index, step) in proposal.steps.iter().enumerate() {
        let before = facts_seeded(&state, &prior, cat, pack, prefix);
        let b = evaluate(&goal.expr, &before, &BTreeMap::new());
        prior.push(step.clone());
        let after = facts_seeded(&step.after, &prior, cat, pack, prefix);
        let a = evaluate(&goal.expr, &after, &BTreeMap::new());
        let lb = ygo_goal::condition_values(&goal.expr, &b);
        let la = ygo_goal::condition_values(&goal.expr, &a);
        let contribution_nodes = la
            .iter()
            .filter(|(id, t)| **t == Truth::Yes && lb.get(*id) != Some(&Truth::Yes))
            .map(|(id, _)| id.clone())
            .collect();
        let lost_nodes = lb
            .iter()
            .filter(|(id, t)| **t == Truth::Yes && la.get(*id) == Some(&Truth::No))
            .map(|(id, _)| id.clone())
            .collect();
        let missing_nodes = lb
            .iter()
            .filter(|(_, t)| **t != Truth::Yes)
            .map(|(id, _)| id.clone())
            .collect();
        let resources = std::iter::once(&step.source)
            .chain(&step.costs)
            .chain(&step.targets)
            .map(|r| r.instance.as_str())
            .collect::<BTreeSet<_>>();
        let consumers = proposal.steps[index + 1..]
            .iter()
            .filter(|s| {
                std::iter::once(&s.source)
                    .chain(&s.costs)
                    .chain(&s.targets)
                    .any(|r| resources.contains(r.instance.as_str()))
            })
            .map(|s| s.effect_id.clone())
            .collect();
        let (branch_before, branch_after, gain_prediction) =
            if let Some(Expr::Continuation {
                goal: sub, gains, ..
            }) = branch
            {
                (
                    Some(evaluate(sub, &before, &BTreeMap::new())),
                    Some(evaluate(sub, &after, &BTreeMap::new())),
                    gains
                        .iter()
                        .filter_map(|g| {
                            Some((
                                g.id.clone(),
                                count(&g.filter, &after)? - count(&g.filter, &anchor)?,
                            ))
                        })
                        .collect(),
                )
            } else {
                (None, None, BTreeMap::new())
            };
        out.push(Forecast {
            kind: "symbolic_prediction".into(),
            proposal_id: proposal.id.clone(),
            semantic_step: index,
            effect_id: step.effect_id.clone(),
            before,
            goal_before: b,
            goal_after: a,
            branch_before,
            branch_after,
            missing_nodes,
            contribution_nodes,
            lost_nodes,
            consumers,
            gain_prediction,
        });
        state = step.after.clone();
    }
    out
}
fn make_plan(steps: Vec<SemanticStep>, pack: &KnowledgePack, goal: &Goal) -> Proposal {
    Proposal {
        id: proposal_id(pack, goal, &steps),
        steps,
        goal_predicted: true,
    }
}
#[allow(clippy::too_many_arguments)]
fn dynamic_prediction(
    e: &Expr,
    state: &SymbolicState,
    history: &[SemanticStep],
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    expanded: &mut usize,
    prefix: Option<&Facts>,
) -> Evaluation {
    let f = facts_seeded(state, history, cat, pack, prefix);
    let mut probes = BTreeMap::new();
    for (path, node) in ygo_goal::probe_nodes(e) {
        let found =
            auxiliary_candidates_seeded(state, history, cat, pack, goal, node, expanded, prefix);
        probes.insert(
            path.clone(),
            Evaluation {
                node: path,
                result: if found.is_empty() {
                    Truth::Unknown
                } else {
                    Truth::Yes
                },
                observed: None,
                matches: vec![],
                reason: "symbolic hypothesis; not engine evidence".into(),
                children: vec![],
            },
        );
    }
    evaluate(e, &f, &probes)
}
fn priority_eval(expr: &Expr, e: &Evaluation) -> i64 {
    match expr {
        Expr::All { args } => args
            .iter()
            .zip(&e.children)
            .map(|(x, v)| priority_eval(x, v))
            .sum(),
        Expr::Any { args } => args
            .iter()
            .zip(&e.children)
            .map(|(x, v)| priority_eval(x, v))
            .max()
            .unwrap_or(0),
        Expr::Count { min, max, .. } | Expr::History { min, max, .. } => {
            if e.result == Truth::Yes {
                if matches!(expr, Expr::History { .. }) {
                    30000
                } else {
                    10000
                }
            } else {
                let n = e.observed.unwrap_or(0).max(0) as usize;
                let deficit = min.saturating_sub(n) + max.map_or(0, |m| n.saturating_sub(m));
                -(deficit.min(100) as i64) * 100
            }
        }
        _ => match e.result {
            Truth::Yes => 10000,
            Truth::No => -10000,
            Truth::Unknown => 0,
        },
    }
}
/// Search guidance only; this value is never reported as a verified benefit.
pub fn goal_priority(expr: &Expr, facts: &Facts) -> i64 {
    priority_eval(expr, &evaluate(expr, facts, &BTreeMap::new()))
}
fn future_truth(expr: &Expr, value: &Evaluation) -> (bool, bool) {
    match expr {
        Expr::History { min, max, .. } => {
            let n = value.observed.unwrap_or(0).max(0) as usize;
            (max.map_or(true, |m| n <= m), max.is_some() || n < *min)
        }
        Expr::All { args } => {
            let xs: Vec<_> = args
                .iter()
                .zip(&value.children)
                .map(|(x, v)| future_truth(x, v))
                .collect();
            (xs.iter().all(|x| x.0), xs.iter().any(|x| x.1))
        }
        Expr::Any { args } => {
            let xs: Vec<_> = args
                .iter()
                .zip(&value.children)
                .map(|(x, v)| future_truth(x, v))
                .collect();
            (xs.iter().any(|x| x.0), xs.iter().all(|x| x.1))
        }
        Expr::Not { arg } => {
            let Some(child) = value.children.first() else {
                return (true, true);
            };
            let (a, b) = future_truth(arg, child);
            (b, a)
        }
        Expr::Count {
            min: 0, max: None, ..
        } => (true, false),
        _ => (true, true),
    }
}
/// Only irreversible history violations are pruned; current resource shortages may be repaired.
pub fn goal_may_still_hold(expr: &Expr, facts: &Facts) -> bool {
    future_truth(expr, &evaluate(expr, facts, &BTreeMap::new())).0
}
/// One global expansion counter covers primary and continuation search.
#[allow(clippy::too_many_arguments)]
pub fn propose_from(
    initial: SymbolicState,
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    max_plans: usize,
    max_steps: usize,
    expanded: &mut usize,
) -> Result<Proposals, String> {
    propose_from_seeded(
        initial, cat, pack, goal, max_plans, max_steps, expanded, None,
    )
}
#[allow(clippy::too_many_arguments)]
pub fn propose_from_seeded(
    initial: SymbolicState,
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    max_plans: usize,
    max_steps: usize,
    expanded: &mut usize,
    prefix: Option<&Facts>,
) -> Result<Proposals, String> {
    propose_mode(
        initial, cat, pack, goal, max_plans, max_steps, expanded, prefix, false,
    )
}
#[allow(clippy::too_many_arguments)]
pub fn propose_diverse(
    initial: SymbolicState,
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    max_plans: usize,
    max_steps: usize,
    expanded: &mut usize,
    prefix: Option<&Facts>,
) -> Result<Proposals, String> {
    propose_mode(
        initial, cat, pack, goal, max_plans, max_steps, expanded, prefix, true,
    )
}
pub fn first_sensitive(steps: &[SemanticStep]) -> String {
    steps
        .iter()
        .find(|s| ygo_engine_adapter::ASH_EFFECTS.contains(&s.effect_id.as_str()))
        .map_or("none".into(), |s| s.effect_id.clone())
}
#[allow(clippy::too_many_arguments)]
fn propose_mode(
    initial: SymbolicState,
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    max_plans: usize,
    max_steps: usize,
    expanded: &mut usize,
    prefix: Option<&Facts>,
    diverse: bool,
) -> Result<Proposals, String> {
    goal.validate()?;
    pack.validate()?;
    if !(1..=8).contains(&max_plans) || !(1..=32).contains(&max_steps) {
        return Err("invalid v3 proposal limits".into());
    }
    let start = *expanded;
    let mut frontier = vec![(initial.clone(), Vec::<SemanticStep>::new())];
    let mut plans = vec![];
    let mut ids = BTreeSet::new();
    let mut fallback: Vec<Proposal> = vec![];
    let mut termination = "exhausted";
    for depth in 0..=max_steps {
        let mut next = vec![];
        for (state, history) in frontier {
            if *expanded >= 5000 {
                termination = "symbolic_node_budget";
                break;
            }
            *expanded += 1;
            let base = evaluate(
                &goal.expr,
                &facts_seeded(&state, &history, cat, pack, prefix),
                &BTreeMap::new(),
            );
            if !future_truth(&goal.expr, &base).0 {
                continue;
            }
            let eval = if base.result == Truth::Unknown && state.pending.is_empty() {
                dynamic_prediction(
                    &goal.expr, &state, &history, cat, pack, goal, expanded, prefix,
                )
            } else {
                base.clone()
            };
            if state.pending.is_empty() && eval.result == Truth::Yes {
                let p = make_plan(history.clone(), pack, goal);
                if ids.insert(p.id.clone())
                    && (!diverse
                        || !plans.iter().any(|old: &Proposal| {
                            first_sensitive(&old.steps) == first_sensitive(&p.steps)
                        }))
                {
                    plans.push(p);
                }
                if plans.len() >= max_plans {
                    termination = "proposal_budget";
                    break;
                }
                continue;
            }
            if state.pending.is_empty() && eval.result == Truth::Unknown {
                let mut p = make_plan(history.clone(), pack, goal);
                p.goal_predicted = false;
                if !fallback.iter().any(|x| x.id == p.id) {
                    fallback.push(p);
                }
                if plans.len() + fallback.len() >= max_plans {
                    termination = "hypothesis_budget";
                    break;
                }
            }
            if depth == max_steps {
                termination = "symbolic_depth_budget";
                continue;
            }
            for step in transitions(&state, cat, pack, goal) {
                if step.after == initial || history.iter().any(|s| s.after == step.after) {
                    continue;
                }
                let mut steps = history.clone();
                let after = step.after.clone();
                steps.push(step);
                let ev = evaluate(
                    &goal.expr,
                    &facts_seeded(&after, &steps, cat, pack, prefix),
                    &BTreeMap::new(),
                );
                if future_truth(&goal.expr, &ev).0 {
                    next.push((after, steps, priority_eval(&goal.expr, &ev)));
                }
            }
        }
        if plans.len() + fallback.len() >= max_plans || *expanded >= 5000 {
            break;
        }
        next.sort_by_cached_key(|(_, h, score)| {
            (
                std::cmp::Reverse(*score),
                h.len(),
                ygo_knowledge::hash(&serde_json::to_vec(h).unwrap()),
            )
        });
        if diverse {
            let mut chosen = Vec::new();
            let mut classes = BTreeSet::new();
            for (i, (_, h, _)) in next.iter().enumerate() {
                if classes.insert(first_sensitive(h)) {
                    chosen.push(i);
                }
            }
            for i in 0..next.len() {
                if chosen.len() >= 32 {
                    break;
                }
                if !chosen.contains(&i) {
                    chosen.push(i);
                }
            }
            chosen.sort_unstable();
            next = next
                .into_iter()
                .enumerate()
                .filter(|(i, _)| chosen.contains(i))
                .map(|(_, v)| v)
                .collect();
        } else {
            next.truncate(32);
        }
        frontier = next.into_iter().map(|(s, h, _)| (s, h)).collect();
        if frontier.is_empty() {
            break;
        }
    }
    let left = max_plans.saturating_sub(plans.len());
    plans.extend(fallback.into_iter().take(left));
    let coverage_gaps = initial
        .cards
        .iter()
        .filter(|c| {
            c.player == 0
                && !pack.cards.iter().any(|k| k.card_id == c.code)
                && cat
                    .get(&CardId(c.code))
                    .is_some_and(|c| c.type_flags & 0x20 != 0 || c.type_flags & 6 != 0)
        })
        .map(|c| format!("unknown effect semantics {}", c.code))
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect();
    Ok(Proposals {
        plans,
        expansions: *expanded - start,
        termination: termination.into(),
        coverage_gaps,
    })
}
/// Enumerate hypotheses only. Every returned branch must be checked against actual engine facts.
#[allow(clippy::too_many_arguments)]
pub fn auxiliary_candidates(
    state: &SymbolicState,
    history: &[SemanticStep],
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    node: &Expr,
    expanded: &mut usize,
) -> Vec<Proposal> {
    auxiliary_candidates_seeded(state, history, cat, pack, goal, node, expanded, None)
}
#[allow(clippy::too_many_arguments)]
pub fn auxiliary_candidates_seeded(
    state: &SymbolicState,
    history: &[SemanticStep],
    cat: &Catalog,
    pack: &KnowledgePack,
    goal: &Goal,
    node: &Expr,
    expanded: &mut usize,
    prefix: Option<&Facts>,
) -> Vec<Proposal> {
    match node {
        Expr::Available {
            effect_id,
            filter,
            window,
        } => {
            if *expanded >= 5000 {
                return vec![];
            }
            *expanded += 1;
            if filter.player != 0
                || window != "main_end"
                || pack.effect(effect_id).map_or(true, |e| {
                    !e.supported || matches!(e.rule, Rule::BootsSummon)
                })
            {
                return vec![];
            }
            let before = facts_seeded(state, history, cat, pack, prefix);
            transitions(state, cat, pack, goal)
                .into_iter()
                .filter(|s| {
                    s.effect_id == *effect_id
                        && before
                            .cards
                            .iter()
                            .find(|c| c.instance == s.source.instance)
                            .is_some_and(|c| filter.matches(c) == Truth::Yes)
                })
                .take(goal.max_aux_candidates)
                .map(|s| make_plan(vec![s], pack, goal))
                .collect()
        }
        Expr::Continuation {
            goal: target,
            gains,
            max_steps,
        } => {
            let initial = facts_seeded(state, history, cat, pack, prefix);
            let mut frontier = vec![(state.clone(), vec![])];
            let mut out = vec![];
            for depth in 0..=max_steps.unwrap_or(goal.continuation_steps) {
                let mut next = vec![];
                for (s, steps) in frontier {
                    if *expanded >= 5000 {
                        return out;
                    }
                    *expanded += 1;
                    let all: Vec<_> = history
                        .iter()
                        .cloned()
                        .chain(steps.iter().cloned())
                        .collect();
                    let f = facts_seeded(&s, &all, cat, pack, prefix);
                    let deltas: Option<Vec<i64>> = gains
                        .iter()
                        .map(|g| Some(count(&g.filter, &f)? - count(&g.filter, &initial)?))
                        .collect();
                    if s.pending.is_empty()
                        && evaluate(target, &f, &BTreeMap::new()).result == Truth::Yes
                        && deltas
                            .as_ref()
                            .is_some_and(|ds| ds.iter().zip(gains).all(|(d, g)| *d >= g.min_delta))
                    {
                        out.push(make_plan(steps.clone(), pack, goal));
                        if out.len() >= goal.max_aux_candidates {
                            return out;
                        }
                    }
                    if depth == max_steps.unwrap_or(goal.continuation_steps) {
                        continue;
                    }
                    for step in transitions(&s, cat, pack, goal) {
                        if step.after == *state
                            || steps.iter().any(|x: &SemanticStep| x.after == step.after)
                        {
                            continue;
                        }
                        let mut h = steps.clone();
                        let after = step.after.clone();
                        h.push(step);
                        let mut full = history.to_vec();
                        full.extend(h.clone());
                        let f = facts_seeded(&after, &full, cat, pack, prefix);
                        let score = priority_eval(target, &evaluate(target, &f, &BTreeMap::new()))
                            + gains
                                .iter()
                                .map(|g| count(&g.filter, &f).unwrap_or(0) * 100)
                                .sum::<i64>();
                        next.push((after, h, score));
                    }
                }
                next.sort_by_cached_key(|(_, h, p)| {
                    (
                        std::cmp::Reverse(*p),
                        h.len(),
                        ygo_knowledge::hash(&serde_json::to_vec(h).unwrap()),
                    )
                });
                next.truncate(8);
                frontier = next.into_iter().map(|(s, h, _)| (s, h)).collect();
                if frontier.is_empty() {
                    break;
                }
            }
            out
        }
        _ => vec![],
    }
}
