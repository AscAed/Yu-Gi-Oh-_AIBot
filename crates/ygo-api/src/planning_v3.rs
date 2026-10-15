//! Goal-aware planning envelope; engine execution identities remain protocol-v3 identities.
use crate::combo::{AnalysisReport, ComboAnalyzeRequest};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use ygo_engine_adapter::*;
use ygo_goal::{Evaluation, Expr, Facts, Goal, Truth};
use ygo_knowledge::KnowledgePack;
use ygo_planner::{v2::*, v3};
use ygo_search::combo::{prefix_key, ScoringConfig, SearchReport, SearchStats};
use ygo_storage::SnapshotStore;
fn eight() -> usize {
    8
}
fn thirty_two() -> usize {
    32
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanRequest {
    pub schema_version: u16,
    pub analysis: ComboAnalyzeRequest,
    pub goal: Goal,
    #[serde(default)]
    pub knowledge_id: Option<String>,
    #[serde(default = "eight")]
    pub max_proposals: usize,
    #[serde(default = "thirty_two")]
    pub max_steps: usize,
    #[serde(default)]
    pub scenario: Option<String>,
}
impl PlanRequest {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != 3 {
            return Err("v3 planning request required".into());
        }
        self.goal.validate()?;
        legacy_request(self).validate()
    }
}
fn legacy_request(q: &PlanRequest) -> crate::planning_v2::PlanRequest {
    crate::planning_v2::PlanRequest {
        schema_version: 2,
        analysis: q.analysis.clone(),
        goal: "rusty-fog".into(),
        knowledge_id: q.knowledge_id.clone(),
        max_proposals: q.max_proposals,
        max_steps: q.max_steps,
        scenario: q.scenario.clone(),
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Trace {
    pub proposal_id: String,
    pub failure: Option<FailureKind>,
    pub status: String,
    pub execution_verified: bool,
    pub execution_id: Option<String>,
    pub predictions: Vec<Prediction>,
    pub discrepancies: Vec<String>,
    pub grave_resources: Vec<String>,
    pub observation: Option<DuelResult>,
}
impl From<Attempt> for Trace {
    fn from(a: Attempt) -> Self {
        Self {
            proposal_id: a.proposal_id,
            failure: a.failure,
            status: a.status,
            execution_verified: a.goal_achieved,
            execution_id: a.line_id,
            predictions: a.predictions,
            discrepancies: a.discrepancies,
            grave_resources: a.grave_resources,
            observation: a.observation,
        }
    }
}
impl Trace {
    fn attempt(&self) -> Attempt {
        Attempt {
            proposal_id: self.proposal_id.clone(),
            failure: self.failure.clone(),
            status: self.status.clone(),
            goal_achieved: self.execution_verified,
            line_id: self.execution_id.clone(),
            predictions: self.predictions.clone(),
            discrepancies: self.discrepancies.clone(),
            grave_resources: self.grave_resources.clone(),
            observation: self.observation.clone(),
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Execution {
    pub id: String,
    pub purpose: String,
    pub runtime: RunDuelRequest,
    pub proposal: Proposal,
    pub trace: Trace,
    pub facts: Facts,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Probe {
    pub node: String,
    pub anchor: String,
    pub result: Evaluation,
    pub candidates: Vec<usize>,
    pub best: Option<usize>,
    pub gains: BTreeMap<String, i64>,
    pub lost_conditions: Vec<String>,
    pub reason: String,
    pub expansion_start: usize,
    pub expansion_end: usize,
    pub attempted: usize,
    pub plans: Vec<Proposal>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Assessment {
    pub execution: usize,
    pub evaluation: Evaluation,
    pub probes: Vec<Probe>,
    pub verification: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Recommendation {
    pub id: String,
    pub execution_id: String,
    pub execution: usize,
    pub evaluation: Evaluation,
    pub probes: Vec<Probe>,
    pub gains: BTreeMap<String, i64>,
    pub witness_ids: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Witness {
    pub runtime: RunDuelRequest,
    pub events: Vec<CoreEventFrame>,
    pub checkpoint: Checkpoint,
    pub decisions: Vec<Decision>,
    pub status: DuelStatus,
    pub replay_verified: bool,
    pub steps: Vec<Action>,
    pub loaded_scripts: Option<BTreeMap<String, String>>,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Ledger {
    pub limit: usize,
    pub used_calls: usize,
    pub reserved_calls: usize,
    pub main_calls: usize,
    pub auxiliary_calls: usize,
    pub witness_calls: usize,
    pub expansions: usize,
    pub aux_candidates: usize,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanReport {
    pub schema_version: u16,
    pub planner_profile: String,
    pub goal_id: String,
    pub knowledge_id: String,
    pub knowledge: KnowledgePack,
    pub request: PlanRequest,
    pub proposals: Proposals,
    pub executions: Vec<Execution>,
    pub forecasts: BTreeMap<String, Vec<v3::Forecast>>,
    pub catalog_projection: ygo_domain::Catalog,
    pub assessments: Vec<Assessment>,
    pub recommendations: Vec<Recommendation>,
    pub witnesses: BTreeMap<String, Witness>,
    pub ledger: Ledger,
    pub analysis: AnalysisReport,
    pub failure_summary: Vec<FailureKind>,
}
fn initial(q: &PlanRequest, cat: &ygo_domain::Catalog) -> Result<SymbolicState, String> {
    let mut s = v3::initialize(&q.analysis.deck, &q.analysis.opening_hand, cat)?;
    let mut reserved_opponent = false;
    for (i, id) in q.analysis.deck.main.iter().enumerate() {
        if q.scenario.is_some() && !reserved_opponent && id.0 == 2964201 {
            reserved_opponent = true;
            continue;
        }
        let card = cat.get(id).ok_or("unknown opponent placeholder card")?;
        s.cards.push(Resource {
            instance: format!("opponent:deck:{i}"),
            code: id.0,
            location: 1,
            level: if card.type_flags & 1 == 0 {
                0
            } else {
                card.level
            },
            redirect: false,
            player: 1,
            overlay_host: None,
            xyz_summoned: false,
            base_level: if card.type_flags & 1 == 0 {
                0
            } else {
                card.level
            },
            epoch: 0,
        });
    }
    if q.scenario.is_some() {
        s.cards.push(Resource {
            instance: "opponent:0".into(),
            code: 2964201,
            location: 4,
            level: 7,
            redirect: false,
            player: 1,
            overlay_host: None,
            xyz_summoned: false,
            base_level: 7,
            epoch: 0,
        });
    }
    Ok(s)
}
fn actual(r: &DuelResult, k: &KnowledgePack) -> Facts {
    ygo_goal::actual_facts(r, &Default::default(), k)
}
fn add_witnesses(e: &Execution) -> Result<BTreeMap<String, Witness>, String> {
    let r = e
        .trace
        .observation
        .as_ref()
        .ok_or("missing execution observation")?;
    let mut out = BTreeMap::new();
    if !e.trace.execution_verified {
        return Ok(out);
    }
    let mut q = e.runtime.clone();
    q.decisions = r.resolved_decisions.clone();
    out.insert(
        prefix_key(&q),
        Witness {
            runtime: q,
            events: r.events.clone(),
            checkpoint: r.checkpoint.clone(),
            decisions: r.resolved_decisions.clone(),
            status: r.status.clone(),
            replay_verified: false,
            steps: r.steps.clone(),
            loaded_scripts: Some(r.loaded_scripts.clone()),
        },
    );
    for p in &e.trace.predictions {
        let i = r
            .resolved_decisions
            .iter()
            .position(|d| d == &p.selected)
            .ok_or("missing witnessed decision")?;
        let mut q = e.runtime.clone();
        q.decisions = r.resolved_decisions[..i].to_vec();
        let events = r
            .events
            .get(..p.before_events)
            .ok_or("invalid prefix length")?
            .to_vec();
        out.insert(
            prefix_key(&q),
            Witness {
                runtime: q.clone(),
                events,
                checkpoint: p.before_checkpoint.clone(),
                decisions: q.decisions.clone(),
                status: DuelStatus::DecisionRequired,
                replay_verified: false,
                steps: recorded_steps(&r.events[..p.before_events], &q.decisions),
                loaded_scripts: None,
            },
        );
    }
    Ok(out)
}
fn merge_witnesses(report: &mut PlanReport, e: &Execution) -> Result<bool, String> {
    let new = add_witnesses(e)?;
    let count = report
        .witnesses
        .keys()
        .chain(new.keys())
        .collect::<std::collections::BTreeSet<_>>()
        .len();
    if report.ledger.used_calls + 2 * count > report.ledger.limit {
        return Ok(false);
    }
    for (k, v) in new {
        report.witnesses.entry(k).or_insert(v);
    }
    report.ledger.reserved_calls = 2 * report.witnesses.len();
    Ok(true)
}
fn run_execution<A: EngineAdapter>(
    report: &mut PlanReport,
    runtime: RunDuelRequest,
    proposal: Proposal,
    purpose: String,
    adapter: &A,
    start: std::time::Instant,
    weights: &ScoringConfig,
) -> Result<Option<usize>, String> {
    let available = report
        .ledger
        .limit
        .saturating_sub(report.ledger.used_calls + report.ledger.reserved_calls);
    let mut budget = report.request.analysis.search.clone();
    budget.node_budget = available;
    budget.top_k = 1;
    budget.time_limit_ms = budget
        .time_limit_ms
        .saturating_sub(start.elapsed().as_millis() as u64);
    if available < 2 || budget.time_limit_ms == 0 {
        report.failure_summary.push(FailureKind::BudgetExhausted);
        return Ok(None);
    }
    let out = execute_general(
        adapter,
        &runtime,
        Proposals {
            plans: vec![proposal.clone()],
            expansions: 0,
            termination: "single_candidate".into(),
            coverage_gaps: vec![],
        },
        &budget,
        weights,
        &report.knowledge,
        true,
        |_| true,
    )?;
    report.ledger.used_calls += out.search.stats.engine_calls;
    if purpose == "main" {
        report.ledger.main_calls += out.search.stats.engine_calls;
    } else {
        report.ledger.auxiliary_calls += out.search.stats.engine_calls;
    }
    let initial_failure = if start.elapsed().as_millis() as u64
        >= report.request.analysis.search.time_limit_ms
        || out
            .search
            .diagnostics
            .iter()
            .any(|e| ["planner_budget", "analysis_timeout"].contains(&e.code.as_str()))
    {
        FailureKind::BudgetExhausted
    } else {
        FailureKind::EngineFailure
    };
    report
        .analysis
        .search
        .diagnostics
        .extend(out.search.diagnostics);
    let Some(a) = out.attempts.into_iter().next() else {
        report.failure_summary.push(initial_failure);
        return Ok(None);
    };
    if let Some(f) = &a.failure {
        if matches!(f, FailureKind::BudgetExhausted | FailureKind::EngineFailure) {
            report.failure_summary.push(f.clone());
        }
    }
    let facts = a
        .observation
        .as_ref()
        .map(|r| actual(r, &report.knowledge))
        .unwrap_or_default();
    let id = a
        .line_id
        .clone()
        .unwrap_or_else(|| format!("unverified:{}", proposal.id));
    let e = Execution {
        id,
        purpose,
        runtime,
        proposal,
        trace: a.into(),
        facts,
    };
    let index = report.executions.len();
    report.executions.push(e);
    Ok(Some(index))
}
fn anchor_observation(e: &Execution) -> Result<(RunDuelRequest, DuelResult), String> {
    let r = e.trace.observation.as_ref().ok_or("missing observation")?;
    let p = e
        .trace
        .predictions
        .iter()
        .find(|p| {
            p.semantic_step == e.proposal.steps.len()
                && matches!(p.selected.choice, Choice::Command { command: 7, .. })
        })
        .ok_or("no stable main-end window")?;
    let i = r
        .resolved_decisions
        .iter()
        .position(|d| d == &p.selected)
        .ok_or("missing end decision")?;
    if p.before_checkpoint.turn != 1
        || p.before_checkpoint.turn_player != 0
        || p.before_checkpoint.phase != 4
    {
        return Err("unsupported goal sampling window".into());
    }
    let mut q = e.runtime.clone();
    q.decisions = r.resolved_decisions[..i].to_vec();
    let mut snapshot = r.clone();
    snapshot.events = r.events[..p.before_events].to_vec();
    snapshot.checkpoint = p.before_checkpoint.clone();
    snapshot.resolved_decisions = q.decisions.clone();
    snapshot.status = DuelStatus::DecisionRequired;
    snapshot.prompt = parse_prompt(
        p.selected.prompt_id,
        &snapshot.events.last().ok_or("missing main-end frame")?.raw,
    )?;
    Ok((q, snapshot))
}
fn unknown(node: &str, reason: &str) -> Evaluation {
    Evaluation {
        node: node.into(),
        result: Truth::Unknown,
        observed: None,
        matches: vec![],
        reason: reason.into(),
        children: vec![],
    }
}
fn lost(expr: &Expr, before: &Facts, after: &Facts) -> Vec<String> {
    let a = ygo_goal::condition_values(expr, &ygo_goal::evaluate(expr, before, &BTreeMap::new()));
    let b = ygo_goal::condition_values(expr, &ygo_goal::evaluate(expr, after, &BTreeMap::new()));
    a.into_iter()
        .filter(|(id, t)| *t == Truth::Yes && b.get(id) == Some(&Truth::No))
        .map(|(id, _)| id)
        .collect()
}
fn branch_value(
    node: &Expr,
    exec: &Execution,
    before: &Facts,
    anchor_events: usize,
    knowledge: &KnowledgePack,
) -> Result<(Truth, BTreeMap<String, i64>), String> {
    if !exec.trace.execution_verified {
        return Ok((Truth::Unknown, BTreeMap::new()));
    }
    match node {
        Expr::Continuation { goal, gains, .. } => {
            let mut deltas = BTreeMap::new();
            let mut results = vec![ygo_goal::evaluate(goal, &exec.facts, &BTreeMap::new()).result];
            for g in gains {
                match (
                    ygo_goal::count(&g.filter, before),
                    ygo_goal::count(&g.filter, &exec.facts),
                ) {
                    (Some(a), Some(b)) => {
                        deltas.insert(g.id.clone(), b - a);
                        results.push(if b - a >= g.min_delta {
                            Truth::Yes
                        } else {
                            Truth::No
                        });
                    }
                    _ => results.push(Truth::Unknown),
                }
            }
            Ok((Truth::all(results), deltas))
        }
        Expr::Available {
            effect_id,
            filter,
            window,
        } => {
            if filter.player != 0
                || window != "main_end"
                || knowledge.effect(effect_id).map_or(true, |x| {
                    !x.supported || matches!(x.rule, ygo_knowledge::Rule::BootsSummon)
                })
            {
                return Ok((Truth::Unknown, BTreeMap::new()));
            }
            let Some(p) = exec.trace.predictions.first() else {
                return Ok((Truth::Unknown, BTreeMap::new()));
            };
            let source = p
                .alternatives
                .iter()
                .find(|m| m.choice == p.selected.choice)
                .and_then(|m| m.source.as_ref());
            let source_matches = source.is_some_and(|s| {
                before.cards.iter().any(|c| {
                    c.code == s.code
                        && c.player == s.player
                        && c.location == s.location
                        && c.sequence == s.sequence
                        && filter.matches(c) == Truth::Yes
                })
            });
            let resolved = exec.facts.history.iter().any(|h| {
                h.kind == "effect_resolved"
                    && h.effect_id.as_deref() == Some(effect_id)
                    && h.event as usize > anchor_events
            });
            Ok((
                if source_matches && resolved {
                    Truth::Yes
                } else {
                    Truth::Unknown
                },
                BTreeMap::new(),
            ))
        }
        _ => Err("not a probe expression".into()),
    }
}
fn probe_value(
    path: &str,
    node: &Expr,
    e: &Execution,
    before: &Facts,
    anchor_events: usize,
    k: &KnowledgePack,
) -> Result<Evaluation, String> {
    let (value, deltas) = branch_value(node, e, before, anchor_events, k)?;
    let mut children = vec![];
    if let Expr::Continuation { goal, gains, .. } = node {
        fn rename(e: &mut Evaluation, prefix: &str) {
            e.node = e.node.replacen("/goal", prefix, 1);
            for c in &mut e.children {
                rename(c, prefix);
            }
        }
        let mut goal_value = ygo_goal::evaluate(goal, &e.facts, &BTreeMap::new());
        rename(&mut goal_value, &format!("{path}/continuation/goal"));
        children.push(goal_value);
        for g in gains {
            let delta = deltas.get(&g.id).copied();
            children.push(Evaluation {
                node: format!("{path}/gain/{}", g.id),
                result: delta.map_or(Truth::Unknown, |d| {
                    if d >= g.min_delta {
                        Truth::Yes
                    } else {
                        Truth::No
                    }
                }),
                observed: delta,
                matches: vec![e.id.clone()],
                reason: format!("signed resource delta; required >= {}", g.min_delta),
                children: vec![],
            });
        }
    }
    Ok(Evaluation {
        node: path.into(),
        result: value,
        observed: None,
        matches: vec![e.id.clone()],
        reason:
            "engine branch with costs and completed resolution; prefix replay recorded separately"
                .into(),
        children,
    })
}
fn branch_cmp(
    r: &PlanReport,
    a: usize,
    ag: &BTreeMap<String, i64>,
    b: usize,
    bg: &BTreeMap<String, i64>,
) -> std::cmp::Ordering {
    let av: Vec<_> = r
        .request
        .goal
        .gain_order
        .iter()
        .map(|id| ag.get(id))
        .collect();
    let bv: Vec<_> = r
        .request
        .goal
        .gain_order
        .iter()
        .map(|id| bg.get(id))
        .collect();
    let cost = |i: usize| {
        r.executions[i]
            .trace
            .observation
            .as_ref()
            .map_or(usize::MAX, |o| {
                o.resolved_decisions
                    .len()
                    .saturating_sub(r.executions[i].runtime.decisions.len())
            })
    };
    av.cmp(&bv)
        .then_with(|| cost(b).cmp(&cost(a)))
        .then_with(|| r.executions[b].id.cmp(&r.executions[a].id))
}
fn absent_available(node: &Expr, before: &DuelResult, k: &KnowledgePack) -> bool {
    let Expr::Available {
        effect_id,
        filter,
        window,
    } = node
    else {
        return false;
    };
    let Some(effect) = k.effect(effect_id) else {
        return false;
    };
    if before.checkpoint.turn != 1
        || before.checkpoint.turn_player != 0
        || before.checkpoint.phase != 4
    {
        return false;
    }
    if filter.player != 0
        || !effect.supported
        || matches!(effect.rule, ygo_knowledge::Rule::BootsSummon)
        || window != "main_end"
        || !before.coverage_gaps.is_empty()
    {
        return false;
    }
    let Some(prompt) = before
        .prompt
        .as_ref()
        .filter(|p| p.player == 0 && p.opcode == 11)
    else {
        return false;
    };
    let Some(frame) = before.events.iter().find(|e| e.sequence == prompt.id) else {
        return false;
    };
    let Ok(ms) = prompt_metadata(frame.sequence, &frame.raw) else {
        return false;
    };
    let f = actual(before, k);
    !ms.iter().any(|m| {
        m.source.as_ref().is_some_and(|s| {
            let source = f.cards.iter().any(|c| {
                c.code == s.code
                    && c.player == s.player
                    && c.location == s.location
                    && c.sequence == s.sequence
                    && filter.matches(c) != Truth::No
            });
            source
                && m.effect_description
                    .is_some_and(|d| ygo_goal::matches_description(effect, s.code, d))
                && matches!(m.choice, Choice::Command { command: 5, .. })
        })
    })
}
fn auxiliary_id(
    pack: &KnowledgePack,
    goal: &Goal,
    anchor: &str,
    node: &str,
    steps: &[SemanticStep],
) -> String {
    ygo_knowledge::hash(
        &serde_json::to_vec(&(
            v3::PROFILE,
            goal.id(),
            pack.id(),
            anchor,
            node,
            v3::proposal_id(pack, goal, steps),
        ))
        .unwrap(),
    )
}
fn evaluate_probes(
    report: &mut PlanReport,
    index: usize,
    cat: &ygo_domain::Catalog,
    adapter: &ProcessEngineAdapter,
    start: std::time::Instant,
    weights: &ScoringConfig,
) -> Result<Vec<Probe>, String> {
    let main = report.executions[index].clone();
    let Ok((q, observation)) = anchor_observation(&main) else {
        return Ok(ygo_goal::probe_nodes(&report.request.goal.expr)
            .iter()
            .map(|(path, _)| Probe {
                node: path.clone(),
                anchor: String::new(),
                result: unknown(path, "no stable main-end window"),
                candidates: vec![],
                best: None,
                gains: BTreeMap::new(),
                lost_conditions: vec![],
                reason: "prompt_unbound".into(),
                expansion_start: report.ledger.expansions,
                expansion_end: report.ledger.expansions,
                attempted: 0,
                plans: vec![],
            })
            .collect());
    };
    let before = actual(&observation, &report.knowledge);
    let state = main
        .proposal
        .steps
        .last()
        .map(|s| s.after.clone())
        .unwrap_or(initial(&report.request, cat)?);
    let nodes: Vec<_> = ygo_goal::probe_nodes(&report.request.goal.expr)
        .into_iter()
        .map(|(p, e)| (p, e.clone()))
        .collect();
    let mut probes = vec![];
    let node_count = nodes.len();
    for (node_number, (path, node)) in nodes.into_iter().enumerate() {
        let mut p = Probe {
            node: path.clone(),
            anchor: prefix_key(&q),
            result: unknown(
                &path,
                "no independently verified branch found within bounds",
            ),
            candidates: vec![],
            best: None,
            gains: BTreeMap::new(),
            lost_conditions: vec![],
            reason: "bounded_lower_bound".into(),
            expansion_start: report.ledger.expansions,
            expansion_end: report.ledger.expansions,
            attempted: 0,
            plans: vec![],
        };
        if let Expr::Available {
            effect_id,
            window,
            filter,
        } = &node
        {
            if filter.player != 0
                || window != "main_end"
                || report.knowledge.effect(effect_id).map_or(true, |e| {
                    !e.supported || matches!(e.rule, ygo_knowledge::Rule::BootsSummon)
                })
            {
                p.reason = "coverage_gap".into();
            }
        }
        let candidates = v3::auxiliary_candidates(
            &state,
            &main.proposal.steps,
            cat,
            &report.knowledge,
            &report.request.goal,
            &node,
            &mut report.ledger.expansions,
        );
        p.expansion_end = report.ledger.expansions;
        let allowance = report
            .request
            .goal
            .max_aux_candidates
            .saturating_sub(report.ledger.aux_candidates)
            .saturating_sub(node_count - node_number - 1);
        if allowance == 0 {
            p.reason = "auxiliary_candidate_budget".into();
        }
        if report.ledger.expansions >= 5000 {
            p.reason = "symbolic_node_budget".into();
        }
        for mut proposal in candidates
            .into_iter()
            .take(if matches!(node, Expr::Available { .. }) {
                allowance.min(1)
            } else {
                allowance
            })
        {
            if report.ledger.aux_candidates >= report.request.goal.max_aux_candidates {
                p.reason = "auxiliary_candidate_budget".into();
                break;
            }
            report.ledger.aux_candidates += 1;
            p.attempted += 1;
            proposal.id = auxiliary_id(
                &report.knowledge,
                &report.request.goal,
                &p.anchor,
                &path,
                &proposal.steps,
            );
            p.plans.push(proposal.clone());
            report.forecasts.insert(
                proposal.id.clone(),
                v3::forecasts(
                    &state,
                    &main.proposal.steps,
                    &proposal,
                    cat,
                    &report.request.goal,
                    Some(&node),
                    &report.knowledge,
                ),
            );
            let Some(i) = run_execution(
                report,
                q.clone(),
                proposal,
                path.clone(),
                adapter,
                start,
                weights,
            )?
            else {
                p.reason = if report.failure_summary.last() == Some(&FailureKind::EngineFailure) {
                    "engine_failure"
                } else {
                    "budget_exhausted"
                }
                .into();
                break;
            };
            p.candidates.push(i);
            let e = report.executions[i].clone();
            let (value, gains) = branch_value(
                &node,
                &e,
                &before,
                observation.events.len(),
                &report.knowledge,
            )?;
            if value != Truth::Yes {
                continue;
            }
            if !merge_witnesses(report, &e)? {
                p.reason = "replay_reservation_budget".into();
                break;
            }
            let better = p.best.map_or(true, |old| {
                branch_cmp(report, i, &gains, old, &p.gains).is_gt()
            });
            if better {
                p.best = Some(i);
                p.gains = gains;
                p.lost_conditions = lost(&report.request.goal.expr, &before, &e.facts);
                p.result = probe_value(
                    &path,
                    &node,
                    &e,
                    &before,
                    observation.events.len(),
                    &report.knowledge,
                )?;
            }
        }
        if p.best.is_none() && absent_available(&node, &observation, &report.knowledge) {
            p.result = Evaluation {
                node: path.clone(),
                result: Truth::No,
                observed: Some(0),
                matches: vec![p.anchor.clone()],
                reason: "complete supported main-end prompt offers no matching activation".into(),
                children: vec![],
            };
        }
        probes.push(p);
    }
    Ok(probes)
}
fn recommendation_id(goal_id: &str, execution_id: &str) -> String {
    ygo_knowledge::hash(&serde_json::to_vec(&(v3::PROFILE, goal_id, execution_id)).unwrap())
}
fn sort_recommendations(r: &mut PlanReport) {
    let order = &r.request.goal.gain_order;
    let executions = &r.executions;
    r.recommendations.sort_by(|a, b| {
        let ga: Vec<_> = order.iter().map(|id| a.gains.get(id)).collect();
        let gb: Vec<_> = order.iter().map(|id| b.gains.get(id)).collect();
        let resources = |x: &Recommendation| {
            executions[x.execution]
                .facts
                .cards
                .iter()
                .filter(|c| c.player == 0 && matches!(c.location, 2 | 4 | 8))
                .count()
        };
        let cost = |x: &Recommendation| {
            let main = &executions[x.execution];
            main.trace
                .observation
                .as_ref()
                .map_or(0, |o| o.resolved_decisions.len())
                + x.probes
                    .iter()
                    .filter_map(|p| p.best)
                    .collect::<std::collections::BTreeSet<_>>()
                    .iter()
                    .map(|i| {
                        let e = &executions[*i];
                        e.trace.observation.as_ref().map_or(0, |o| {
                            o.resolved_decisions
                                .len()
                                .saturating_sub(e.runtime.decisions.len())
                        })
                    })
                    .sum::<usize>()
        };
        gb.cmp(&ga)
            .then_with(|| resources(b).cmp(&resources(a)))
            .then_with(|| cost(a).cmp(&cost(b)))
            .then_with(|| a.id.cmp(&b.id))
    });
}
fn check_witness(w: &Witness, actual: &DuelResult) -> bool {
    actual.events == w.events
        && actual.checkpoint == w.checkpoint
        && actual.resolved_decisions == w.decisions
        && actual.status == w.status
        && actual.versions == w.runtime.versions
        && actual.steps == w.steps
        && w.loaded_scripts
            .as_ref()
            .map_or(true, |scripts| scripts == &actual.loaded_scripts)
}
fn verify_witnesses<A: EngineAdapter>(
    r: &mut PlanReport,
    adapter: &A,
    start: std::time::Instant,
) -> Result<(), String> {
    let mut order = vec![];
    let mut seen = std::collections::BTreeSet::new();
    for id in r
        .recommendations
        .iter()
        .flat_map(|x| x.witness_ids.iter())
        .chain(r.witnesses.keys())
    {
        if seen.insert(id.clone()) {
            order.push(id.clone());
        }
    }
    for id in order {
        let left = r
            .request
            .analysis
            .search
            .time_limit_ms
            .saturating_sub(start.elapsed().as_millis() as u64);
        let passed = r.witnesses.values().filter(|w| w.replay_verified).count();
        if left == 0 || r.ledger.used_calls + passed + 2 > r.ledger.limit {
            r.failure_summary.push(FailureKind::BudgetExhausted);
            break;
        }
        let w = r.witnesses.get_mut(&id).ok_or("missing reserved witness")?;
        let mut q = w.runtime.clone();
        q.engine.timeout_ms = q.engine.timeout_ms.min(left);
        r.ledger.used_calls += 1;
        r.ledger.witness_calls += 1;
        match adapter.run(&q) {
            Ok(actual) if actual.status == DuelStatus::Failed => {
                r.failure_summary.push(
                    if start.elapsed().as_millis() as u64 >= r.request.analysis.search.time_limit_ms
                    {
                        FailureKind::BudgetExhausted
                    } else {
                        FailureKind::EngineFailure
                    },
                );
                r.analysis
                    .search
                    .diagnostics
                    .push(actual.error.unwrap_or_else(|| {
                        WorkerError::new(
                            "goal_worker_failed",
                            "replay",
                            "worker returned failed without details",
                        )
                    }));
                break;
            }
            Ok(actual) if check_witness(w, &actual) => w.replay_verified = true,
            Ok(_) => {
                r.failure_summary.push(FailureKind::PredictionMismatch);
                r.analysis.search.diagnostics.push(WorkerError::new(
                    "goal_witness_mismatch",
                    "replay",
                    format!("witness {id} differs from execution"),
                ));
                break;
            }
            Err(error) => {
                r.failure_summary.push(
                    if start.elapsed().as_millis() as u64 >= r.request.analysis.search.time_limit_ms
                    {
                        FailureKind::BudgetExhausted
                    } else {
                        FailureKind::EngineFailure
                    },
                );
                r.analysis.search.diagnostics.push(error);
                break;
            }
        }
    }
    r.witnesses.retain(|_, w| w.replay_verified);
    r.recommendations.retain(|rec| {
        rec.witness_ids
            .iter()
            .all(|id| r.witnesses.contains_key(id))
    });
    r.ledger.reserved_calls = r.witnesses.len();
    Ok(())
}

pub fn plan(
    mut request: PlanRequest,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog: &str,
    weights: &ScoringConfig,
    knowledge: KnowledgePack,
) -> Result<PlanReport, String> {
    request.validate()?;
    if knowledge.profile_version != "phantom-v2" {
        return Err("v3 requires phantom-v2 knowledge".into());
    }
    knowledge.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )?;
    let kid = knowledge.id();
    if request.knowledge_id.as_ref().is_some_and(|id| id != &kid) {
        return Err("knowledge ID mismatch".into());
    }
    let (resolved, mut runtime, cat) =
        crate::combo::prepare(request.analysis.clone(), engine.clone(), store, catalog)?;
    request.analysis = resolved.clone();
    request.knowledge_id = Some(kid.clone());
    runtime.protocol_version = 3;
    runtime.versions.initializer = "fixed-opponent-v1".into();
    runtime.scenario = request.scenario.clone();
    let start = std::time::Instant::now();
    let mut expansions = 0;
    let proposals = v3::propose_from(
        initial(&request, &cat)?,
        &cat,
        &knowledge,
        &request.goal,
        request.max_proposals,
        request.max_steps,
        &mut expansions,
    )?;
    let budget = request.analysis.search.clone();
    let gid = request.goal.id();
    let catalog_projection = cat
        .iter()
        .filter(|(id, _)| {
            request.analysis.deck.main.contains(id)
                || request.analysis.deck.extra.contains(id)
                || request.analysis.deck.side.contains(id)
        })
        .map(|(id, c)| (*id, c.clone()))
        .collect();
    let card_names = cat
        .values()
        .filter(|c| {
            request.analysis.deck.main.contains(&c.id)
                || request.analysis.deck.extra.contains(&c.id)
                || request.analysis.deck.side.contains(&c.id)
        })
        .map(|c| (c.id.0, c.name.clone()))
        .collect();
    let mut r = PlanReport {
        schema_version: 3,
        planner_profile: v3::PROFILE.into(),
        goal_id: gid,
        knowledge_id: kid,
        knowledge,
        request,
        proposals: proposals.clone(),
        executions: vec![],
        forecasts: BTreeMap::new(),
        catalog_projection,
        assessments: vec![],
        recommendations: vec![],
        witnesses: BTreeMap::new(),
        ledger: Ledger {
            limit: budget.node_budget,
            expansions,
            ..Default::default()
        },
        analysis: AnalysisReport {
            schema_version: 3,
            request: resolved,
            runtime_request: runtime.clone(),
            search: SearchReport {
                termination: "proposals_exhausted".into(),
                lines: vec![],
                stats: SearchStats::default(),
                diagnostics: vec![],
                scoring: weights.clone(),
                budget: budget.clone(),
            },
            card_names,
        },
        failure_summary: vec![],
    };
    let initial_state = initial(&r.request, &cat)?;
    for p in &proposals.plans {
        r.forecasts.insert(
            p.id.clone(),
            v3::forecasts(
                &initial_state,
                &[],
                p,
                &cat,
                &r.request.goal,
                None,
                &r.knowledge,
            ),
        );
    }
    let adapter = ProcessEngineAdapter::new(engine);
    for proposal in proposals.plans {
        let Some(i) = run_execution(
            &mut r,
            runtime.clone(),
            proposal,
            "main".into(),
            &adapter,
            start,
            weights,
        )?
        else {
            break;
        };
        let exec = r.executions[i].clone();
        if !exec.trace.execution_verified {
            r.assessments.push(Assessment {
                execution: i,
                evaluation: unknown("/goal", "main execution did not complete"),
                probes: vec![],
                verification: "unverified".into(),
            });
            if let Some(f) = exec.trace.failure {
                r.failure_summary.push(f);
            }
            continue;
        }
        if !merge_witnesses(&mut r, &exec)? {
            r.assessments.push(Assessment {
                execution: i,
                evaluation: ygo_goal::evaluate(&r.request.goal.expr, &exec.facts, &BTreeMap::new()),
                probes: vec![],
                verification: "engine_observed".into(),
            });
            r.failure_summary.push(FailureKind::BudgetExhausted);
            break;
        }
        let probes = evaluate_probes(&mut r, i, &cat, &adapter, start, weights)?;
        let mapping = probes
            .iter()
            .map(|p| (p.node.clone(), p.result.clone()))
            .collect();
        let eval = ygo_goal::evaluate(&r.request.goal.expr, &exec.facts, &mapping);
        r.assessments.push(Assessment {
            execution: i,
            evaluation: eval.clone(),
            probes: probes.clone(),
            verification: "engine_observed".into(),
        });
        if eval.result != Truth::Yes {
            r.failure_summary
                .push(if probes.iter().any(|p| p.reason.contains("budget")) {
                    FailureKind::BudgetExhausted
                } else if probes.iter().any(|p| p.reason == "engine_failure") {
                    FailureKind::EngineFailure
                } else if probes
                    .iter()
                    .any(|p| p.reason == "coverage_gap" || p.reason == "prompt_unbound")
                {
                    FailureKind::CoverageGap
                } else if eval.result == Truth::No {
                    if exec.proposal.goal_predicted {
                        FailureKind::PredictionMismatch
                    } else {
                        FailureKind::RulesRejected
                    }
                } else if !probes.is_empty() {
                    FailureKind::NoPlanFound
                } else {
                    FailureKind::CoverageGap
                });
            continue;
        }
        let mut ids = add_witnesses(&exec)?
            .keys()
            .cloned()
            .collect::<std::collections::BTreeSet<_>>();
        let mut gains = BTreeMap::new();
        for p in &probes {
            gains.extend(p.gains.clone());
            if let Some(j) = p.best {
                ids.extend(add_witnesses(&r.executions[j])?.keys().cloned());
            }
        }
        if r.recommendations.iter().any(|x| x.execution_id == exec.id) {
            continue;
        }
        r.recommendations.push(Recommendation {
            id: recommendation_id(&r.goal_id, &exec.id),
            execution_id: exec.id,
            execution: i,
            evaluation: eval,
            probes,
            gains,
            witness_ids: ids.into_iter().collect(),
        });
    }
    verify_witnesses(&mut r, &adapter, start)?;
    for a in &mut r.assessments {
        let e = &r.executions[a.execution];
        let mut ids = add_witnesses(e)?
            .keys()
            .cloned()
            .collect::<std::collections::BTreeSet<_>>();
        for p in &a.probes {
            if let Some(i) = p.best {
                ids.extend(add_witnesses(&r.executions[i])?.keys().cloned());
            }
        }
        if e.trace.execution_verified
            && !ids.is_empty()
            && ids.iter().all(|id| r.witnesses.contains_key(id))
        {
            a.verification = "independently_replayed".into();
        }
    }
    sort_recommendations(&mut r);
    for rec in r.recommendations.iter().take(budget.top_k) {
        let e = &r.executions[rec.execution];
        let actual = e
            .trace
            .observation
            .as_ref()
            .ok_or("missing verified observation")?;
        r.analysis.search.lines.push(ygo_search::combo::ComboLine {
            id: e.id.clone(),
            decisions: actual.resolved_decisions.clone(),
            evaluation: ygo_search::combo::evaluate(
                &actual.checkpoint,
                actual.resolved_decisions.len(),
                weights,
            ),
            result: actual.clone(),
            replay_verified: true,
        });
    }
    r.analysis.search.stats.engine_calls = r.ledger.used_calls;
    r.analysis.search.stats.nodes = r.ledger.main_calls + r.ledger.auxiliary_calls;
    r.analysis.search.stats.completed_lines = r.analysis.search.lines.len();
    r.analysis.search.stats.elapsed_ms = start.elapsed().as_millis() as u64;
    if r.recommendations.is_empty() {
        if !r.proposals.coverage_gaps.is_empty() {
            r.failure_summary.push(FailureKind::CoverageGap);
        }
        if r.failure_summary.is_empty() {
            r.failure_summary.push(FailureKind::NoPlanFound);
        }
        r.analysis.search.termination = "no_verified_goal".into();
    }
    validate_plan_contract(&r)?;
    Ok(r)
}
fn recorded_steps(events: &[CoreEventFrame], decisions: &[Decision]) -> Vec<Action> {
    events
        .iter()
        .filter_map(|e| parse_prompt(e.sequence, &e.raw).ok().flatten())
        .filter_map(|p| {
            let choice = if p.player == 0 {
                decisions
                    .iter()
                    .find(|d| d.prompt_id == p.id)
                    .map(|d| d.choice.clone())
            } else {
                p.actions
                    .iter()
                    .find(|a| matches!(a.choice, Choice::Chain { index: None }))
                    .map(|a| a.choice.clone())
            };
            choice.and_then(|choice| p.actions.into_iter().find(|a| a.choice == choice))
        })
        .collect()
}
fn validate_execution(e: &Execution, r: &PlanReport) -> Result<(), String> {
    let o = e
        .trace
        .observation
        .as_ref()
        .ok_or("missing trace observation")?;
    if e.runtime.probe_only
        || e.runtime.protocol_version != 3
        || e.runtime.versions != r.analysis.runtime_request.versions
        || e.runtime.scenario != r.request.scenario
        || e.runtime.deck != r.analysis.runtime_request.deck
        || e.runtime.opening_hand != r.analysis.runtime_request.opening_hand
        || e.runtime.seed != r.analysis.runtime_request.seed
        || e.proposal.id
            != if e.purpose == "main" {
                v3::proposal_id(&r.knowledge, &r.request.goal, &e.proposal.steps)
            } else {
                auxiliary_id(
                    &r.knowledge,
                    &r.request.goal,
                    &prefix_key(&e.runtime),
                    &e.purpose,
                    &e.proposal.steps,
                )
            }
        || e.trace.proposal_id != e.proposal.id
        || o.versions != e.runtime.versions
        || o.protocol_version != 3
        || e.facts != actual(o, &r.knowledge)
    {
        return Err("execution provenance/facts mismatch".into());
    }
    if !o.resolved_decisions.starts_with(&e.runtime.decisions)
        || (e.purpose == "main" && !e.runtime.decisions.is_empty())
        || o.steps != recorded_steps(&o.events, &o.resolved_decisions)
    {
        return Err("execution prefix/response bytes mismatch".into());
    }
    for frame in &o.events {
        if decode_frame(frame.sequence, &frame.raw)? != *frame {
            return Err("raw goal evidence mismatch".into());
        }
    }
    validate_bindings(&e.proposal, &e.trace.attempt(), &r.knowledge)?;
    let mut previous = 0;
    for (number, p) in e.trace.predictions.iter().enumerate() {
        let index = match o.resolved_decisions.iter().position(|d| d == &p.selected) {
            Some(i) if p.outcome == "observed" => i,
            None if p.outcome == "unobserved"
                && !e.trace.execution_verified
                && number + 1 == e.trace.predictions.len()
                && p.before_events == p.after_events =>
            {
                o.resolved_decisions.len()
            }
            _ => return Err("goal prediction chronology mismatch".into()),
        };
        let mut q = e.runtime.clone();
        q.decisions = o.resolved_decisions[..index].to_vec();
        let reason = e
            .proposal
            .steps
            .get(p.semantic_step)
            .map_or("目标已预测完成；结束回合并验证终场", |s| {
                s.reason.as_str()
            });
        let id = e
            .proposal
            .steps
            .get(p.semantic_step)
            .map_or("system:end_turn", |s| s.effect_id.as_str());
        let frame = o
            .events
            .iter()
            .find(|f| f.sequence == p.selected.prompt_id)
            .ok_or("missing goal prompt")?;
        if p.reason != reason
            || p.effect_id != id
            || p.before_prefix != prefix_key(&q)
            || p.before_events < previous
            || p.before_events < p.selected.prompt_id as usize
            || p.after_events < p.before_events
            || p.after_events > o.events.len()
            || p.alternatives != prompt_metadata(frame.sequence, &frame.raw)?
            || p.comparisons
                != assess_alternatives(
                    &e.proposal,
                    p.semantic_step,
                    &p.alternatives,
                    &p.selected.choice,
                    &r.knowledge,
                )
            || !p.alternatives.iter().any(|m| m.choice == p.selected.choice)
        {
            return Err("goal prediction reference/reason mismatch".into());
        }
        previous = p.after_events;
    }
    if e.trace.execution_verified {
        let mut q = e.runtime.clone();
        q.decisions = o.resolved_decisions.clone();
        if e.trace.status != "engine_verified"
            || e.trace.failure.is_some()
            || !e.trace.discrepancies.is_empty()
            || o.status != DuelStatus::EngineVerified
            || o.prompt.is_some()
            || o.error.is_some()
            || !o.coverage_gaps.is_empty()
            || e.id != prefix_key(&q)
            || e.trace.execution_id.as_deref() != Some(&e.id)
            || e.proposal
                .steps
                .iter()
                .enumerate()
                .any(|(i, _)| !e.trace.predictions.iter().any(|p| p.semantic_step == i))
        {
            return Err("forged verified execution".into());
        }
    } else if e.trace.execution_id.is_some()
        || e.trace.status == "engine_verified"
        || e.trace.failure.is_none()
    {
        return Err("unverified execution marked successful".into());
    }
    Ok(())
}
type CheckedGoalEvidence = (
    Evaluation,
    BTreeMap<String, i64>,
    std::collections::BTreeSet<String>,
);
fn validate_goal_evidence(
    r: &PlanReport,
    e: &Execution,
    probes: &[Probe],
) -> Result<CheckedGoalEvidence, String> {
    let mut expected_witnesses = add_witnesses(e)?
        .keys()
        .cloned()
        .collect::<std::collections::BTreeSet<_>>();
    let mut mapping = BTreeMap::new();
    let mut gains = BTreeMap::new();
    let nodes = ygo_goal::probe_nodes(&r.request.goal.expr);
    if nodes.len() != probes.len() {
        return Err("goal probe coverage mismatch".into());
    }
    for ((path, node), p) in nodes.into_iter().zip(probes) {
        if p.node != path || p.result.node != path {
            return Err("probe node reference mismatch".into());
        }
        let (q, obs) = anchor_observation(e)?;
        let before = actual(&obs, &r.knowledge);
        if p.anchor != prefix_key(&q) {
            return Err("probe anchor mismatch".into());
        }
        if p.best
            .is_some_and(|i| i >= r.executions.len() || !p.candidates.contains(&i))
        {
            return Err("unknown best branch reference".into());
        }
        let mut candidate_set = std::collections::BTreeSet::new();
        for index in &p.candidates {
            let candidate = r
                .executions
                .get(*index)
                .ok_or("unknown auxiliary execution")?;
            if !candidate_set.insert(*index)
                || candidate.purpose != path
                || prefix_key(&candidate.runtime) != p.anchor
            {
                return Err("auxiliary candidate provenance mismatch".into());
            }
            if let Some(best) = p.best {
                let (value, delta) =
                    branch_value(node, candidate, &before, obs.events.len(), &r.knowledge)?;
                if value == Truth::Yes
                    && add_witnesses(candidate)?
                        .keys()
                        .all(|id| r.witnesses.contains_key(id))
                    && branch_cmp(r, *index, &delta, best, &p.gains).is_gt()
                {
                    return Err("reported best branch ignores a better verified candidate".into());
                }
            }
        }
        if let Some(i) = p.best {
            if !p.candidates.contains(&i) {
                return Err("unknown probe candidate".into());
            }
            let aux = r.executions.get(i).ok_or("unknown branch")?;
            if aux.purpose != path || prefix_key(&aux.runtime) != p.anchor {
                return Err("probe branch starts at wrong prefix".into());
            }
            let (value, delta) = branch_value(node, aux, &before, obs.events.len(), &r.knowledge)?;
            if p.result != probe_value(&path, node, aux, &before, obs.events.len(), &r.knowledge)? {
                return Err("probe structured evaluation mismatch".into());
            }
            if value != Truth::Yes
                || p.result.result != value
                || p.result.matches != vec![aux.id.clone()]
                || delta != p.gains
                || p.lost_conditions != lost(&r.request.goal.expr, &before, &aux.facts)
            {
                return Err("probe result/gain/loss mismatch".into());
            }
            let max_steps = match node {
                Expr::Continuation { max_steps, .. } => {
                    max_steps.unwrap_or(r.request.goal.continuation_steps)
                }
                Expr::Available { .. } => 1,
                _ => return Err("invalid probe node".into()),
            };
            if aux.proposal.steps.len() > max_steps {
                return Err("continuation exceeded semantic step limit".into());
            }
            expected_witnesses.extend(add_witnesses(aux)?.keys().cloned());
            gains.extend(delta);
        } else {
            if !p.gains.is_empty() || !p.lost_conditions.is_empty() {
                return Err("gain without branch evidence".into());
            }
            if p.result.result == Truth::Yes
                || (p.result.result == Truth::No && !absent_available(node, &obs, &r.knowledge))
            {
                return Err("unsupported negative/positive probe claim".into());
            }
        }
        mapping.insert(path, p.result.clone());
    }
    let evaluation = ygo_goal::evaluate(&r.request.goal.expr, &e.facts, &mapping);
    Ok((evaluation, gains, expected_witnesses))
}
pub fn validate_plan_contract(r: &PlanReport) -> Result<(), String> {
    if r.planner_profile != v3::PROFILE {
        return Err(format!(
            "unsupported goal planner profile {}; regenerate the v3 report with {}",
            r.planner_profile,
            v3::PROFILE
        ));
    }
    r.request.validate()?;
    r.knowledge.validate()?;
    crate::combo::validate_report_contract(&r.analysis)?;
    if r.schema_version != 3
        || r.planner_profile != v3::PROFILE
        || r.goal_id != r.request.goal.id()
        || r.knowledge_id != r.knowledge.id()
        || r.request.knowledge_id.as_deref() != Some(&r.knowledge_id)
        || r.knowledge.profile_version != "phantom-v2"
        || r.analysis.schema_version != 3
        || r.analysis.runtime_request.protocol_version != 3
        || r.analysis.runtime_request.versions.initializer != "fixed-opponent-v1"
        || r.analysis.runtime_request.scenario != r.request.scenario
        || serde_json::to_value(&r.request.analysis).unwrap()
            != serde_json::to_value(&r.analysis.request).unwrap()
        || r.knowledge.cdb_sha256 != r.analysis.runtime_request.versions.cdb_sha256
        || r.knowledge.scripts_sha256 != r.analysis.runtime_request.versions.scripts_sha256
        || r.proposals.plans.len() > r.request.max_proposals
    {
        return Err("goal envelope/version/source mismatch".into());
    }
    if r.ledger.limit != r.request.analysis.search.node_budget
        || r.ledger.used_calls + r.ledger.reserved_calls > r.ledger.limit
        || r.ledger.used_calls
            != r.ledger.main_calls + r.ledger.auxiliary_calls + r.ledger.witness_calls
        || r.ledger.reserved_calls != r.witnesses.len()
        || r.ledger.witness_calls < r.witnesses.len()
        || (r.ledger.witness_calls > r.witnesses.len() && r.analysis.search.diagnostics.is_empty())
        || r.ledger.expansions > 5000
        || r.ledger.aux_candidates > r.request.goal.max_aux_candidates
        || r.analysis.search.stats.engine_calls != r.ledger.used_calls
    {
        return Err("goal budget accounting mismatch".into());
    }
    let mut proposal_ids = std::collections::BTreeSet::new();
    for p in &r.proposals.plans {
        if p.steps.len() > r.request.max_steps
            || p.id != v3::proposal_id(&r.knowledge, &r.request.goal, &p.steps)
            || !proposal_ids.insert(p.id.clone())
        {
            return Err("invalid goal proposal ID/steps".into());
        }
    }
    let mut potential = BTreeMap::new();
    for e in &r.executions {
        validate_execution(e, r)?;
        for (k, v) in add_witnesses(e)? {
            if let Some(old) = potential.insert(k, v.clone()) {
                let mut old: Witness = old;
                old.replay_verified = false;
                if serde_json::to_value(old).unwrap() != serde_json::to_value(v).unwrap() {
                    return Err("conflicting prefix observations".into());
                }
            }
        }
    }
    for (id, w) in &r.witnesses {
        let expected = potential.get(id).ok_or("unreferenced goal witness")?;
        let mut w0 = w.clone();
        w0.replay_verified = false;
        if !w.replay_verified
            || prefix_key(&w.runtime) != *id
            || w.decisions != w.runtime.decisions
            || serde_json::to_value(w0).unwrap() != serde_json::to_value(expected).unwrap()
        {
            return Err("goal witness identity/content mismatch".into());
        }
    }
    let projected_ids: std::collections::BTreeSet<_> = r
        .request
        .analysis
        .deck
        .main
        .iter()
        .chain(&r.request.analysis.deck.extra)
        .chain(&r.request.analysis.deck.side)
        .copied()
        .collect();
    if r.catalog_projection
        .keys()
        .copied()
        .collect::<std::collections::BTreeSet<_>>()
        != projected_ids
        || r.catalog_projection.iter().any(|(id, c)| *id != c.id)
    {
        return Err("planning catalog projection mismatch".into());
    }
    let initial_state = initial(&r.request, &r.catalog_projection)?;
    let mut regenerated_expansions = 0;
    let regenerated = v3::propose_from(
        initial_state.clone(),
        &r.catalog_projection,
        &r.knowledge,
        &r.request.goal,
        r.request.max_proposals,
        r.request.max_steps,
        &mut regenerated_expansions,
    )?;
    if serde_json::to_value(regenerated).unwrap() != serde_json::to_value(&r.proposals).unwrap() {
        return Err("primary causal proposal regeneration mismatch".into());
    }
    let mut expected_forecasts = BTreeMap::new();
    for p in &r.proposals.plans {
        expected_forecasts.insert(
            p.id.clone(),
            v3::forecasts(
                &initial_state,
                &[],
                p,
                &r.catalog_projection,
                &r.request.goal,
                None,
                &r.knowledge,
            ),
        );
    }
    for a in &r.assessments {
        let main = r
            .executions
            .get(a.execution)
            .ok_or("unknown forecast source execution")?;
        let state = main
            .proposal
            .steps
            .last()
            .map(|s| s.after.clone())
            .unwrap_or(initial_state.clone());
        for p in &a.probes {
            let node = ygo_goal::probe_nodes(&r.request.goal.expr)
                .into_iter()
                .find(|(id, _)| id == &p.node)
                .ok_or("unknown forecast node")?
                .1;
            let mut expansion = p.expansion_start;
            let mut generated = v3::auxiliary_candidates(
                &state,
                &main.proposal.steps,
                &r.catalog_projection,
                &r.knowledge,
                &r.request.goal,
                node,
                &mut expansion,
            );
            for plan in &mut generated {
                plan.id = auxiliary_id(
                    &r.knowledge,
                    &r.request.goal,
                    &p.anchor,
                    &p.node,
                    &plan.steps,
                );
            }
            if expansion != p.expansion_end
                || p.plans.len() > generated.len()
                || p.plans.iter().zip(&generated).any(|(a, b)| {
                    serde_json::to_value(a).unwrap() != serde_json::to_value(b).unwrap()
                })
            {
                return Err("auxiliary causal proposal regeneration mismatch".into());
            }
            if p.plans.len() != p.attempted || p.candidates.len() > p.plans.len() {
                return Err("planned/attempted auxiliary accounting mismatch".into());
            }
            for (i, plan) in p.plans.iter().enumerate() {
                if plan.id
                    != auxiliary_id(
                        &r.knowledge,
                        &r.request.goal,
                        &p.anchor,
                        &p.node,
                        &plan.steps,
                    )
                    || p.candidates.get(i).is_some_and(|idx| {
                        r.executions
                            .get(*idx)
                            .map_or(true, |e| e.proposal.id != plan.id)
                    })
                {
                    return Err("auxiliary history identity mismatch".into());
                }
                expected_forecasts.insert(
                    plan.id.clone(),
                    v3::forecasts(
                        &state,
                        &main.proposal.steps,
                        plan,
                        &r.catalog_projection,
                        &r.request.goal,
                        Some(node),
                        &r.knowledge,
                    ),
                );
            }
        }
    }
    if r.forecasts != expected_forecasts {
        return Err("pre-execution goal forecast mismatch".into());
    }
    let mut assessment_indices = std::collections::BTreeSet::new();
    let mut expanded = r.proposals.expansions;
    let mut attempted = 0;
    for a in &r.assessments {
        let e = r
            .executions
            .get(a.execution)
            .ok_or("unknown assessment execution")?;
        if e.purpose != "main" || !assessment_indices.insert(a.execution) {
            return Err("duplicate/non-primary assessment".into());
        }
        if !e.trace.execution_verified {
            if a.verification != "unverified"
                || a.evaluation != unknown("/goal", "main execution did not complete")
                || !a.probes.is_empty()
            {
                return Err("false assessment verification".into());
            }
            continue;
        }
        let (eval, _, ids) =
            if a.probes.is_empty() && !ygo_goal::probe_nodes(&r.request.goal.expr).is_empty() {
                (
                    ygo_goal::evaluate(&r.request.goal.expr, &e.facts, &BTreeMap::new()),
                    BTreeMap::new(),
                    add_witnesses(e)?.keys().cloned().collect(),
                )
            } else {
                validate_goal_evidence(r, e, &a.probes)?
            };
        if eval != a.evaluation {
            return Err("assessment evaluation mismatch".into());
        }
        let independent = !ids.is_empty() && ids.iter().all(|id| r.witnesses.contains_key(id));
        if a.verification
            != if independent {
                "independently_replayed"
            } else {
                "engine_observed"
            }
        {
            return Err("assessment replay status mismatch".into());
        }
        for p in &a.probes {
            if p.expansion_start != expanded
                || p.expansion_end < p.expansion_start
                || p.expansion_end > 5000
                || p.candidates.len() > p.attempted
            {
                return Err("probe expansion accounting mismatch".into());
            }
            expanded = p.expansion_end;
            attempted += p.attempted;
        }
    }
    if assessment_indices
        != r.executions
            .iter()
            .enumerate()
            .filter(|(_, e)| e.purpose == "main")
            .map(|(i, _)| i)
            .collect()
        || expanded != r.ledger.expansions
        || attempted != r.ledger.aux_candidates
    {
        return Err("missing assessment/auxiliary accounting".into());
    }
    let mut recids = std::collections::BTreeSet::new();
    for rec in &r.recommendations {
        let e = r
            .executions
            .get(rec.execution)
            .ok_or("unknown recommendation execution")?;
        if e.purpose != "main"
            || !e.trace.execution_verified
            || rec.execution_id != e.id
            || rec.id != recommendation_id(&r.goal_id, &e.id)
            || !recids.insert(rec.id.clone())
            || !r.proposals.plans.iter().any(|p| p.id == e.proposal.id)
        {
            return Err("recommendation provenance mismatch".into());
        }
        let assessment = r
            .assessments
            .iter()
            .find(|a| a.execution == rec.execution)
            .ok_or("recommendation lacks assessment")?;
        if assessment.verification != "independently_replayed"
            || assessment.evaluation != rec.evaluation
            || serde_json::to_value(&assessment.probes).unwrap()
                != serde_json::to_value(&rec.probes).unwrap()
        {
            return Err("recommendation differs from goal assessment".into());
        }
        let (evaluation, gains, expected_witnesses) = validate_goal_evidence(r, e, &rec.probes)?;
        if evaluation != rec.evaluation
            || evaluation.result != Truth::Yes
            || gains != rec.gains
            || rec.witness_ids != expected_witnesses.into_iter().collect::<Vec<_>>()
            || rec
                .witness_ids
                .iter()
                .any(|id| !r.witnesses.contains_key(id))
        {
            return Err("goal evaluation/evidence mismatch".into());
        }
    }
    let mut sorted = r.clone();
    sort_recommendations(&mut sorted);
    if sorted
        .recommendations
        .iter()
        .map(|x| &x.id)
        .collect::<Vec<_>>()
        != r.recommendations.iter().map(|x| &x.id).collect::<Vec<_>>()
    {
        return Err("goal ranking mismatch".into());
    }
    let expected: Vec<_> = r
        .recommendations
        .iter()
        .take(r.request.analysis.search.top_k)
        .map(|rec| rec.execution_id.as_str())
        .collect();
    if r.analysis
        .search
        .lines
        .iter()
        .map(|x| x.id.as_str())
        .collect::<Vec<_>>()
        != expected
    {
        return Err("analysis/recommendation mismatch".into());
    }
    for line in &r.analysis.search.lines {
        let e = r
            .executions
            .iter()
            .find(|e| e.id == line.id && e.purpose == "main")
            .ok_or("unknown analysis execution")?;
        let o = e
            .trace
            .observation
            .as_ref()
            .ok_or("missing line observation")?;
        if line.result.events != o.events
            || line.result.checkpoint != o.checkpoint
            || line.result.resolved_decisions != o.resolved_decisions
        {
            return Err("line and goal trace disagree".into());
        }
    }
    Ok(())
}
pub fn replay(
    r: &PlanReport,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
) -> Result<serde_json::Value, String> {
    validate_plan_contract(r)?;
    r.knowledge.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )?;
    let (resolved, runtime, cat) = crate::combo::prepare(
        r.request.analysis.clone(),
        engine.clone(),
        store,
        &r.analysis.runtime_request.versions.catalog,
    )?;
    if serde_json::to_value(resolved).unwrap() != serde_json::to_value(&r.request.analysis).unwrap()
        || runtime.versions.cdb_sha256 != r.analysis.runtime_request.versions.cdb_sha256
    {
        return Err("replay frozen input mismatch".into());
    }
    if r.catalog_projection
        .iter()
        .any(|(id, c)| cat.get(id) != Some(c))
    {
        return Err("catalog projection differs from frozen snapshot".into());
    }
    if r.recommendations.is_empty() {
        return Err("no goal recommendations to replay".into());
    }
    let adapter = ProcessEngineAdapter::new(engine.clone());
    let start = std::time::Instant::now();
    let mut calls = 0;
    for w in r.witnesses.values() {
        let left = r
            .request
            .analysis
            .search
            .time_limit_ms
            .saturating_sub(start.elapsed().as_millis() as u64);
        if left == 0 || r.ledger.used_calls + calls >= r.ledger.limit {
            return Err("shared goal replay budget exhausted".into());
        }
        let mut q = w.runtime.clone();
        q.engine = engine.clone();
        q.engine.timeout_ms = q.engine.timeout_ms.min(left);
        calls += 1;
        let actual = adapter.run(&q).map_err(|e| e.message)?;
        if !check_witness(w, &actual) {
            return Err("goal witness replay mismatch".into());
        }
    }
    Ok(
        serde_json::json!({"schema_version":3,"goal_id":r.goal_id,"recommendations":r.recommendations.iter().map(|x|&x.id).collect::<Vec<_>>(),"witnesses":calls,"execution_calls":r.ledger.used_calls,"replay_calls":calls,"total_calls":r.ledger.used_calls+calls,"goal_evidence_verified":true}),
    )
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::cell::Cell;
    struct ReplayFailure {
        calls: Cell<usize>,
    }
    impl EngineAdapter for ReplayFailure {
        fn doctor(&self) -> DoctorReport {
            DoctorReport {
                ready: true,
                assets_ok: true,
                abi_ok: true,
                smoke_ok: None,
                issues: vec![],
            }
        }
        fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            let n = self.calls.get();
            self.calls.set(n + 1);
            if n > 0 {
                return Err(WorkerError::new("worker_timeout", "duel", "worker failed"));
            }
            let mut result = DuelResult::failure(WorkerError::new("unused", "unused", "unused"));
            result.versions = q.versions.clone();
            result.status = DuelStatus::DecisionRequired;
            Ok(result)
        }
    }
    fn empty_report() -> PlanReport {
        let request: PlanRequest = serde_json::from_str(include_str!(
            "../../../tests/fixtures/goal-rusty.request.json"
        ))
        .unwrap();
        let runtime = RunDuelRequest {
            protocol_version: 3,
            engine: Default::default(),
            deck: request.analysis.deck.clone(),
            opening_hand: request.analysis.opening_hand.clone(),
            seed: 1,
            decisions: vec![],
            versions: Default::default(),
            probe_only: false,
            scenario: None,
        };
        let knowledge = KnowledgePack::builtin().unwrap();
        PlanReport {
            schema_version: 3,
            planner_profile: v3::PROFILE.into(),
            goal_id: request.goal.id(),
            knowledge_id: knowledge.id(),
            knowledge,
            proposals: Proposals {
                plans: vec![],
                expansions: 0,
                termination: "test".into(),
                coverage_gaps: vec![],
            },
            executions: vec![],
            forecasts: Default::default(),
            catalog_projection: Default::default(),
            assessments: vec![],
            recommendations: vec![],
            witnesses: BTreeMap::new(),
            ledger: Ledger {
                limit: 512,
                ..Default::default()
            },
            analysis: AnalysisReport {
                schema_version: 3,
                request: request.analysis.clone(),
                runtime_request: runtime,
                search: SearchReport {
                    termination: "test".into(),
                    lines: vec![],
                    stats: Default::default(),
                    diagnostics: vec![],
                    scoring: Default::default(),
                    budget: request.analysis.search.clone(),
                },
                card_names: Default::default(),
            },
            request,
            failure_summary: vec![],
        }
    }
    #[test]
    fn witness_failure_retains_already_verified_recommendations() {
        let mut r = empty_report();
        let q = r.analysis.runtime_request.clone();
        for id in ["a", "b"] {
            r.witnesses.insert(
                id.into(),
                Witness {
                    runtime: q.clone(),
                    events: vec![],
                    checkpoint: Default::default(),
                    decisions: vec![],
                    status: DuelStatus::DecisionRequired,
                    replay_verified: false,
                    steps: vec![],
                    loaded_scripts: None,
                },
            );
            r.recommendations.push(Recommendation {
                id: id.into(),
                execution_id: id.into(),
                execution: 0,
                evaluation: unknown("/goal", "test"),
                probes: vec![],
                gains: Default::default(),
                witness_ids: vec![id.into()],
            });
        }
        let adapter = ReplayFailure {
            calls: Cell::new(0),
        };
        assert!(verify_witnesses(&mut r, &adapter, std::time::Instant::now()).is_ok());
        assert_eq!(r.recommendations.len(), 1);
        assert_eq!(r.recommendations[0].id, "a");
        assert_eq!(r.ledger.used_calls, 2);
        assert_eq!(r.ledger.reserved_calls, 1);
        assert!(r.failure_summary.contains(&FailureKind::EngineFailure));
    }
    #[test]
    fn first_worker_failure_is_engine_failure_not_budget_exhaustion() {
        let mut r = empty_report();
        let q = r.analysis.runtime_request.clone();
        let adapter = ReplayFailure {
            calls: Cell::new(1),
        };
        let proposal = Proposal {
            id: v3::proposal_id(&r.knowledge, &r.request.goal, &[]),
            steps: vec![],
            goal_predicted: true,
        };
        run_execution(
            &mut r,
            q,
            proposal,
            "main".into(),
            &adapter,
            std::time::Instant::now(),
            &Default::default(),
        )
        .unwrap();
        assert!(r.failure_summary.contains(&FailureKind::EngineFailure));
        assert!(!r.failure_summary.contains(&FailureKind::BudgetExhausted));
    }
    #[test]
    fn old_goal_profile_requires_report_regeneration() {
        let mut r = empty_report();
        r.planner_profile = "phantom-goal-v1".into();
        assert!(validate_plan_contract(&r)
            .unwrap_err()
            .contains("regenerate"));
    }
    #[test]
    fn negated_conditions_report_loss_at_the_negation_node() {
        let node = Expr::Not {
            arg: Box::new(Expr::Count {
                filter: ygo_goal::Filter {
                    codes: vec![1],
                    ..Default::default()
                },
                min: 1,
                max: None,
            }),
        };
        let before = Facts::default();
        let after = Facts {
            cards: vec![ygo_goal::FactCard {
                code: 1,
                ..Default::default()
            }],
            ..Default::default()
        };
        assert_eq!(lost(&node, &before, &after), vec!["/goal"]);
        assert!(lost(&node, &after, &before).is_empty());
    }
    #[test]
    fn own_idle_menu_cannot_prove_opponent_activation_absent() {
        let raw: Vec<u8> =
            serde_json::from_str(include_str!("../../../tests/fixtures/v3-idle-frame.json"))
                .unwrap();
        let mut before = DuelResult::failure(WorkerError::new("test", "test", "test"));
        before.error = None;
        before.status = DuelStatus::DecisionRequired;
        before.events = vec![decode_frame(1, &raw).unwrap()];
        before.prompt = parse_prompt(1, &raw).unwrap();
        before.checkpoint.turn = 1;
        before.checkpoint.turn_player = 0;
        before.checkpoint.phase = 4;
        let node = Expr::Available {
            effect_id: "25538345:mill".into(),
            filter: ygo_goal::Filter {
                player: 1,
                ..Default::default()
            },
            window: "main_end".into(),
        };
        assert!(!absent_available(
            &node,
            &before,
            &KnowledgePack::builtin().unwrap()
        ));
    }
    struct SerializedFailure;
    impl EngineAdapter for SerializedFailure {
        fn doctor(&self) -> DoctorReport {
            ReplayFailure {
                calls: Cell::new(0),
            }
            .doctor()
        }
        fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            let mut r =
                DuelResult::failure(WorkerError::new("callback_failed", "scripts", "Lua failed"));
            r.protocol_version = 3;
            r.versions = q.versions.clone();
            Ok(r)
        }
    }
    #[test]
    fn serialized_worker_failure_is_not_a_prediction_difference() {
        let mut r = empty_report();
        let q = r.analysis.runtime_request.clone();
        r.witnesses.insert(
            "a".into(),
            Witness {
                runtime: q,
                events: vec![],
                checkpoint: Default::default(),
                decisions: vec![],
                status: DuelStatus::DecisionRequired,
                replay_verified: false,
                steps: vec![],
                loaded_scripts: None,
            },
        );
        verify_witnesses(&mut r, &SerializedFailure, std::time::Instant::now()).unwrap();
        assert!(r.failure_summary.contains(&FailureKind::EngineFailure));
        assert!(!r.failure_summary.contains(&FailureKind::PredictionMismatch));
    }
}
