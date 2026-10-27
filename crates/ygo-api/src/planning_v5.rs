//! Bounded strategy matrix against one real Ash activation.
use crate::planning_v3::{self as arm, PlanningContext, ProposalMode};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use ygo_domain::{CardId, Catalog};
use ygo_engine_adapter::*;
use ygo_knowledge::KnowledgePack;
use ygo_planner::{v2::*, v3};
use ygo_search::combo::{prefix_key, ScoringConfig};
use ygo_storage::SnapshotStore;
mod recovery;
pub use recovery::reconstruct;

pub const PROFILE: &str = "phantom-ash-strategy-v1";
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanRequest {
    pub schema_version: u16,
    pub analysis: crate::combo::ComboAnalyzeRequest,
    pub goal: ygo_goal::Goal,
    pub knowledge_id: Option<String>,
    pub max_proposals: usize,
    pub max_steps: usize,
    pub max_strategies: usize,
    pub total_budget: usize,
    pub policies: Vec<String>,
    pub opponent: InterruptionConfig,
}
impl PlanRequest {
    fn inner(&self, budget: usize, steps: usize) -> arm::PlanRequest {
        let mut a = self.analysis.clone();
        a.search.node_budget = budget;
        arm::PlanRequest {
            schema_version: 3,
            analysis: a,
            goal: self.goal.clone(),
            knowledge_id: None,
            max_proposals: self.max_proposals,
            max_steps: steps,
            scenario: None,
        }
    }
    fn legacy(&self) -> crate::planning_v4::PlanRequest {
        let mut i = self.opponent.clone();
        i.policy = "ash_scales_once".into();
        i.effect_id = "25538345:mill".into();
        crate::planning_v4::PlanRequest {
            schema_version: 4,
            analysis: self.analysis.clone(),
            goal: self.goal.clone(),
            knowledge_id: None,
            max_proposals: self.max_proposals,
            max_steps: self.max_steps,
            interruption: i,
        }
    }
    pub fn validate(&self) -> Result<(), String> {
        self.legacy().validate()?;
        self.opponent.validate_v5()?;
        if self.schema_version != 5
            || self.max_strategies != 2
            || self.total_budget != 8192
            || self.opponent.policy != "pass"
            || self.policies != policies()
        {
            return Err("unsupported strategy matrix configuration".into());
        }
        Ok(())
    }
}
pub fn policies() -> Vec<String> {
    std::iter::once("pass")
        .chain(ASH_EFFECTS)
        .map(String::from)
        .collect()
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Score {
    pub goal: bool,
    pub gains: Vec<Option<i64>>,
    pub main_resources: usize,
    pub verification_decisions: usize,
}
impl Ord for Score {
    fn cmp(&self, b: &Self) -> std::cmp::Ordering {
        self.goal
            .cmp(&b.goal)
            .then(self.gains.cmp(&b.gains))
            .then(self.main_resources.cmp(&b.main_resources))
            .then_with(|| b.verification_decisions.cmp(&self.verification_decisions))
    }
}
impl PartialOrd for Score {
    fn partial_cmp(&self, b: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(b))
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Outcome {
    pub execution_id: String,
    pub score: Score,
    pub evaluation: ygo_goal::Evaluation,
    pub witnesses: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Settlement {
    pub effect_id: String,
    pub reason: String,
    pub before: arm::Witness,
    pub selected: Decision,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Anchor {
    pub runtime: RunDuelRequest,
    pub observation: DuelResult,
    pub state: SymbolicState,
    pub id: String,
    pub consumed_steps: usize,
    pub settlements: Vec<Settlement>,
    pub witness: arm::Witness,
    pub used_calls: usize,
    pub reserved_calls: usize,
    pub replay_verified: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FailedSettlement {
    pub selections: Vec<Settlement>,
    pub observation: DuelResult,
    pub used_calls: usize,
    pub replay_attempts: usize,
    pub error: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct CellComparison {
    pub pass_execution_id: String,
    pub reference_window_id: Option<String>,
    pub actual_anchor_id: Option<String>,
    pub interruption_changes: Option<Vec<crate::planning_v4::ResourceChange>>,
    pub recovery_changes: Option<Vec<crate::planning_v4::ResourceChange>>,
    pub terminal_difference: Option<Vec<crate::planning_v4::ResourceChange>>,
    pub lost_goal_conditions: Vec<String>,
    pub window_semantics: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cell {
    pub comparison: Option<CellComparison>,
    pub failed_settlement: Option<FailedSettlement>,
    pub policy: String,
    pub classification: String,
    pub original: Option<arm::PlanReport>,
    pub anchor: Option<Anchor>,
    pub recovery: Option<arm::PlanReport>,
    pub outcome: Option<Outcome>,
    pub calls: usize,
    pub detail: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Strategy {
    pub id: String,
    pub proposal: Proposal,
    pub first_sensitive: String,
    pub prediction: String,
    pub discovery: usize,
    pub selected_execution: usize,
    pub cells: Vec<Cell>,
    pub worst_first: Option<Vec<Score>>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanReport {
    pub schema_version: u16,
    pub planner_profile: String,
    pub request: PlanRequest,
    pub knowledge_id: String,
    pub opponent_knowledge: ygo_knowledge::CardKnowledge,
    pub discoveries: Vec<arm::PlanReport>,
    pub strategies: Vec<Strategy>,
    pub ranking: Vec<String>,
    pub comparison: String,
    pub total_calls: usize,
    pub limitations: Vec<String>,
}
fn hash<T: Serialize>(x: &T) -> String {
    ygo_knowledge::hash(&serde_json::to_vec(x).unwrap())
}
fn same<T: Serialize>(a: &T, b: &T) -> bool {
    serde_json::to_value(a).unwrap() == serde_json::to_value(b).unwrap()
}
fn calls(a: &arm::PlanReport) -> usize {
    a.ledger.used_calls + a.ledger.reserved_calls
}
fn initial(q: &PlanRequest, cat: &Catalog) -> Result<SymbolicState, String> {
    crate::planning_v4::initial(&q.legacy(), cat)
}
fn strategy_id(q: &PlanRequest, kid: &str, p: &Proposal) -> String {
    hash(&(PROFILE, q.goal.id(), kid, &q.policies, &p.steps))
}
fn prediction(p: &Proposal) -> String {
    format!("实验前预测：首个敏感效果{}；按目标缺口生成此展开，费用和墓地资源可能在无效后改变；稳健优劣须由八种策略实际验证。",v3::first_sensitive(&p.steps))
}
fn outcome(a: &arm::PlanReport, only: Option<usize>) -> Option<Outcome> {
    let mut xs = vec![];
    for assessment in &a.assessments {
        if only.is_some_and(|i| i != assessment.execution)
            || assessment.verification != "independently_replayed"
            || assessment.evaluation.result == ygo_goal::Truth::Unknown
        {
            continue;
        }
        let e = &a.executions[assessment.execution];
        let obs = e.trace.observation.as_ref()?;
        let mut gains = BTreeMap::new();
        for p in &assessment.probes {
            gains.extend(p.gains.clone());
        }
        xs.push(Outcome {
            execution_id: e.id.clone(),
            score: Score {
                goal: assessment.evaluation.result == ygo_goal::Truth::Yes,
                gains: a
                    .request
                    .goal
                    .gain_order
                    .iter()
                    .map(|id| gains.get(id).copied())
                    .collect(),
                main_resources: obs
                    .checkpoint
                    .cards
                    .iter()
                    .filter(|c| c.player == 0 && matches!(c.location, 2 | 4 | 8))
                    .count(),
                verification_decisions: obs.resolved_decisions.len()
                    + assessment
                        .probes
                        .iter()
                        .filter_map(|p| p.best)
                        .collect::<BTreeSet<_>>()
                        .into_iter()
                        .map(|i| {
                            a.executions[i].trace.observation.as_ref().map_or(0, |o| {
                                o.resolved_decisions
                                    .len()
                                    .saturating_sub(a.executions[i].runtime.decisions.len())
                            })
                        })
                        .sum::<usize>(),
            },
            evaluation: assessment.evaluation.clone(),
            witnesses: a.witnesses.keys().cloned().collect(),
        });
    }
    xs.sort_by(|a, b| {
        b.score
            .cmp(&a.score)
            .then(a.execution_id.cmp(&b.execution_id))
    });
    xs.into_iter().next()
}
fn witness(runtime: RunDuelRequest, o: &DuelResult) -> arm::Witness {
    arm::Witness {
        runtime,
        events: o.events.clone(),
        checkpoint: o.checkpoint.clone(),
        decisions: o.resolved_decisions.clone(),
        status: o.status.clone(),
        replay_verified: true,
        steps: o.steps.clone(),
        loaded_scripts: Some(o.loaded_scripts.clone()),
    }
}
fn verify_witness(w: &arm::Witness, engine: &ProcessEngineConfig) -> Result<(), String> {
    let mut q = w.runtime.clone();
    q.engine = engine.clone();
    let o = ProcessEngineAdapter::new(engine.clone())
        .run(&q)
        .map_err(|e| e.message)?;
    if o.events != w.events
        || o.checkpoint != w.checkpoint
        || o.resolved_decisions != w.decisions
        || o.status != w.status
        || o.steps != w.steps
        || Some(&o.loaded_scripts) != w.loaded_scripts.as_ref()
    {
        return Err("anchor/prediction witness replay mismatch".into());
    }
    Ok(())
}
fn settlement_choice(
    o: &DuelResult,
    pack: &KnowledgePack,
    active: &str,
) -> Result<(String, String, Decision), String> {
    let p = o.prompt.as_ref().ok_or("missing settlement prompt")?;
    let f = o
        .events
        .iter()
        .find(|e| e.sequence == p.id)
        .ok_or("missing raw settlement prompt")?;
    let ms = prompt_metadata(p.id, &f.raw)?;
    for m in &ms {
        if let (Some(source), Some(desc)) = (&m.source, m.effect_description) {
            if source.player == 0 {
                if let Some(effect) = pack.card(source.code).and_then(|k| {
                    k.effects.iter().find(|e| {
                        e.supported
                            && e.trigger.is_some()
                            && (p.opcode == 12
                                || ygo_goal::matches_description(e, source.code, desc))
                    })
                }) {
                    if matches!(
                        effect.rule,
                        ygo_knowledge::Rule::ScaleRevive | ygo_knowledge::Rule::GreavesSummon
                    ) && matches!(
                        m.choice,
                        Choice::YesNo { yes: true } | Choice::Chain { index: Some(_) }
                    ) {
                        return Ok((effect.id.clone(),"执行前：实际事件已产生支持的复活/特殊召唤触发，保留可用于原目标的场上资源".into(),Decision{prompt_id:p.id,player:p.player,choice:m.choice.clone()}));
                    }
                }
            }
        }
    }
    let m = ms
        .iter()
        .find(|m| {
            matches!(
                m.choice,
                Choice::Place { .. }
                    | Choice::Position { position: 1 }
                    | Choice::Chain { index: None }
                    | Choice::YesNo { yes: false }
                    | Choice::Finish
            )
        })
        .ok_or("recovery_coverage_gap: unsupported trigger settlement prompt")?;
    Ok((
        active.into(),
        "执行前：完成已绑定触发的合法区域/表示选择；放弃未支持的可选效果".into(),
        Decision {
            prompt_id: p.id,
            player: p.player,
            choice: m.choice.clone(),
        },
    ))
}
#[allow(clippy::too_many_arguments)]
fn settle(
    mut runtime: RunDuelRequest,
    mut o: DuelResult,
    cat: &Catalog,
    pack: &KnowledgePack,
    prefix_steps: usize,
    max_steps: usize,
    budget: usize,
    progress: &mut FailedSettlement,
) -> Result<Anchor, String> {
    if prefix_steps > max_steps {
        return Err("budget_exhausted: interrupted prefix semantic steps".into());
    }
    let adapter = ProcessEngineAdapter::new(runtime.engine.clone());
    let mut active = "system:settlement".to_string();
    loop {
        runtime.decisions = o.resolved_decisions.clone();
        if o.prompt
            .as_ref()
            .is_some_and(|p| p.player == 0 && p.opcode == 11)
        {
            break;
        }
        if progress.selections.len() >= 32
            || progress.used_calls + 2 * (progress.selections.len() + 2) + 1 > budget
        {
            return Err("budget_exhausted: settlement replay reservation".into());
        }
        let (effect_id, reason, selected) = settlement_choice(&o, pack, &active)?;
        let prior = progress
            .selections
            .iter()
            .filter(|s| {
                matches!(
                    s.selected.choice,
                    Choice::YesNo { yes: true } | Choice::Chain { index: Some(_) }
                )
            })
            .count();
        let activating = usize::from(matches!(
            selected.choice,
            Choice::YesNo { yes: true } | Choice::Chain { index: Some(_) }
        ));
        if prefix_steps + prior + activating > max_steps {
            return Err("budget_exhausted: settlement semantic steps".into());
        }
        active = effect_id.clone();
        let mut before = witness(runtime.clone(), &o);
        before.replay_verified = false;
        progress.selections.push(Settlement {
            effect_id,
            reason,
            before,
            selected: selected.clone(),
        });
        runtime.decisions.push(selected);
        progress.used_calls += 1;
        o = adapter.run(&runtime).map_err(|e| e.message)?;
        progress.observation = o.clone();
        if o.status == DuelStatus::Failed {
            return Err("engine_failure: trigger settlement".into());
        }
    }
    let state = reconstruct(&o, cat, pack)?;
    runtime.decisions = o.resolved_decisions.clone();
    let w = witness(runtime.clone(), &o);
    if progress.used_calls + 2 * (progress.selections.len() + 1) > budget {
        return Err("budget_exhausted: anchor witness reservation".into());
    }
    for settlement in &mut progress.selections {
        progress.used_calls += 1;
        progress.replay_attempts += 1;
        verify_witness(&settlement.before, &runtime.engine)?;
        settlement.before.replay_verified = true;
    }
    progress.used_calls += 1;
    progress.replay_attempts += 1;
    verify_witness(&w, &runtime.engine)?;
    let consumed_steps = prefix_steps
        + progress
            .selections
            .iter()
            .filter(|s| {
                matches!(
                    s.selected.choice,
                    Choice::YesNo { yes: true } | Choice::Chain { index: Some(_) }
                )
            })
            .count();
    Ok(Anchor {
        id: hash(&(PROFILE, prefix_key(&runtime), &state)),
        runtime,
        observation: o,
        state,
        consumed_steps,
        reserved_calls: progress.selections.len() + 1,
        used_calls: progress.used_calls,
        settlements: progress.selections.clone(),
        witness: w,
        replay_verified: true,
    })
}

fn effect_seen(o: &DuelResult, id: &str, pack: &KnowledgePack) -> bool {
    pack.effect(id).is_some_and(|eff| {
        o.events.iter().any(|e| {
            e.opcode == 70
                && e.fields["player"] == 0
                && pack
                    .card(e.fields["code"].as_u64().unwrap_or(0) as u32)
                    .is_some_and(|k| k.effects.iter().any(|x| x.id == eff.id))
                && e.fields["description"].as_u64().is_some_and(|d| {
                    ygo_goal::matches_description_version(
                        5,
                        eff,
                        e.fields["code"].as_u64().unwrap_or(0) as u32,
                        d,
                    )
                })
        })
    })
}
fn response_hit(o: &DuelResult) -> bool {
    o.events
        .iter()
        .any(|e| e.opcode == 70 && e.fields["player"] == 1 && e.fields["code"] == 14558127u32)
        && o.events.iter().any(|e| e.opcode == 76)
}
fn row_score(row: &Strategy) -> Option<Vec<Score>> {
    let mut x: Vec<_> = row
        .cells
        .iter()
        .map(|c| c.outcome.as_ref().map(|o| o.score.clone()))
        .collect::<Option<_>>()?;
    if x.len() != 8 {
        return None;
    }
    x.sort();
    Some(x)
}
fn confirmed_losses(
    expr: &ygo_goal::Expr,
    before: &ygo_goal::Evaluation,
    after: &ygo_goal::Evaluation,
) -> Vec<String> {
    let b = ygo_goal::condition_values(expr, after);
    ygo_goal::condition_values(expr, before)
        .into_iter()
        .filter(|(id, t)| *t == ygo_goal::Truth::Yes && b.get(id) == Some(&ygo_goal::Truth::No))
        .map(|(id, _)| id)
        .collect()
}
fn cell_comparison(
    pass: &arm::PlanReport,
    index: usize,
    proposal: &Proposal,
    c: &Cell,
    goal: &ygo_goal::Goal,
) -> Option<CellComparison> {
    if c.policy == "pass" {
        return None;
    }
    let base = pass.executions.get(index)?;
    let before = base.trace.observation.as_ref()?;
    let target = proposal.steps.iter().position(|s| s.effect_id == c.policy);
    let reference = target.and_then(|target| {
        base.trace.predictions.iter().find(|p| {
            p.semantic_step > target
                && before
                    .events
                    .get(p.before_events.saturating_sub(1))
                    .is_some_and(|e| e.opcode == 11)
        })
    });
    let arm = c.recovery.as_ref().or(c.original.as_ref());
    let terminal = c
        .outcome
        .as_ref()
        .and_then(|o| arm.and_then(|a| a.executions.iter().find(|e| e.id == o.execution_id)))
        .and_then(|e| e.trace.observation.as_ref());
    let lost = pass
        .assessments
        .iter()
        .find(|a| a.execution == index)
        .zip(c.outcome.as_ref())
        .map_or_else(Vec::new, |(a, b)| {
            confirmed_losses(&goal.expr, &a.evaluation, &b.evaluation)
        });
    Some(CellComparison{pass_execution_id:base.id.clone(),reference_window_id:reference.map(|p|p.before_prefix.clone()),actual_anchor_id:c.anchor.as_ref().map(|a|a.id.clone()),interruption_changes:reference.and_then(|p|c.anchor.as_ref().map(|a|crate::planning_v4::resource_changes(&p.before_checkpoint,&a.observation.checkpoint))),recovery_changes:c.anchor.as_ref().and_then(|a|terminal.map(|t|crate::planning_v4::resource_changes(&a.observation.checkpoint,&t.checkpoint))),terminal_difference:terminal.map(|t|crate::planning_v4::resource_changes(&before.checkpoint,&t.checkpoint)),lost_goal_conditions:lost,window_semantics:"实际合法操作窗口对照包含已选择的触发结算；终场差异单列，不自动解释为纯中断损失或可用收益".into()})
}
struct MatrixSummary {
    total: usize,
    scores: Vec<Option<Vec<Score>>>,
    ranking: Vec<String>,
    comparison: String,
}
fn summary(r: &PlanReport) -> MatrixSummary {
    let total = r.discoveries.iter().map(calls).sum::<usize>()
        + r.strategies
            .iter()
            .flat_map(|s| &s.cells)
            .filter(|c| c.policy != "pass")
            .map(|c| c.calls)
            .sum::<usize>();
    let scores: Vec<_> = r.strategies.iter().map(row_score).collect();
    let mut rows: Vec<_> = r
        .strategies
        .iter()
        .enumerate()
        .filter(|(i, _)| scores[*i].is_some())
        .collect();
    rows.sort_by(|(i, a), (j, b)| scores[*j].cmp(&scores[*i]).then(a.id.cmp(&b.id)));
    let ranking: Vec<_> = rows.iter().map(|(_, s)| s.id.clone()).collect();
    let comparison=format!("验证后比较：{}个策略有八格完整见证；按同一实际分支的最坏结果优先，{}。这里只比较本次探索的已验证下界，不声称全局最优或响应概率。",rows.len(),ranking.first().map_or("证据不足，暂无稳健推荐".into(),|id|format!("首推策略{id}")));
    MatrixSummary {
        total,
        scores,
        ranking,
        comparison,
    }
}
fn limitations(r: &PlanReport) -> Vec<String> {
    let mut out = vec![];
    if r.strategies.is_empty() {
        out.push(
            if r.discoveries
                .iter()
                .any(|d| d.failure_summary.contains(&FailureKind::BudgetExhausted))
            {
                "budget_exhausted: no verified initial strategy"
            } else {
                "no_verified_initial_strategy: bounded search or coverage"
            }
            .into(),
        );
    } else if r.strategies.len() < 2 {
        out.push(
            "second_strategy_not_found: no distinct first-sensitive verified candidate".into(),
        );
    }
    for row in &r.strategies {
        for c in &row.cells {
            if c.outcome.is_none() {
                out.push(format!(
                    "incomplete_cell:{}:{}:{}",
                    row.id, c.policy, c.classification
                ));
            }
        }
    }
    out
}
fn finish(r: &mut PlanReport) {
    for row in &mut r.strategies {
        let pass = &r.discoveries[row.discovery];
        for cell in &mut row.cells {
            cell.comparison = cell_comparison(
                pass,
                row.selected_execution,
                &row.proposal,
                cell,
                &r.request.goal,
            );
        }
    }
    let x = summary(r);
    r.total_calls = x.total;
    r.ranking = x.ranking;
    r.comparison = x.comparison;
    r.limitations = limitations(r);
    for (row, score) in r.strategies.iter_mut().zip(x.scores) {
        row.worst_first = score;
    }
}
#[allow(clippy::too_many_arguments)]
pub fn plan(
    mut q: PlanRequest,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog: &str,
    weights: &ScoringConfig,
    pack: KnowledgePack,
) -> Result<PlanReport, String> {
    q.validate()?;
    let ash = KnowledgePack::ash_source(&engine.catalog_path, &engine.scripts_path)?;
    let kid = hash(&(pack.id(), &ash));
    if q.knowledge_id.as_ref().is_some_and(|x| x != &kid) {
        return Err("knowledge ID mismatch".into());
    }
    q.knowledge_id = Some(kid.clone());
    let (resolved, mut runtime, cat) =
        crate::combo::prepare(q.analysis.clone(), engine.clone(), store, catalog)?;
    q.analysis = resolved;
    if !ygo_domain::validate_catalog_deck(
        &q.opponent.opponent_deck,
        &store.banlist(&q.analysis.banlist_id)?.data,
        &cat,
    )
    .is_legal()
    {
        return Err("illegal opponent deck".into());
    }
    runtime.protocol_version = 5;
    runtime.versions.initializer = "fixed-ash-strategy-v1".into();
    runtime.interruption = Some(q.opponent.clone());
    let initial = initial(&q, &cat)?;
    let mut r = PlanReport {
        schema_version: 5,
        planner_profile: PROFILE.into(),
        request: q.clone(),
        knowledge_id: kid.clone(),
        opponent_knowledge: ash,
        discoveries: vec![],
        strategies: vec![],
        ranking: vec![],
        comparison: String::new(),
        total_calls: 0,
        limitations: vec![],
    };
    // Both candidates are frozen using pass-only experiments before any responsive column.
    for diversity in [false, true] {
        if diversity && r.strategies.is_empty() {
            break;
        }
        let mut discovery_q = q.clone();
        discovery_q.max_proposals = if diversity {
            q.max_proposals
                .saturating_sub(r.discoveries[0].proposals.plans.len())
        } else {
            (q.max_proposals / 2).max(1)
        };
        if discovery_q.max_proposals == 0 {
            break;
        }
        let ctx = PlanningContext {
            knowledge_bundle_id: kid.clone(),
            runtime: runtime.clone(),
            initial: initial.clone(),
            anchor: None,
            proposal_mode: diversity.then(|| ProposalMode::Diverse {
                expansion_start: r.discoveries[0].ledger.expansions,
            }),
        };
        let a = arm::plan_context(
            discovery_q.inner(q.analysis.search.node_budget, q.max_steps),
            engine.clone(),
            store,
            catalog,
            weights,
            pack.clone(),
            Some(ctx),
        )?;
        let chosen = a
            .recommendations
            .iter()
            .find(|rec| {
                !diversity
                    || v3::first_sensitive(&a.executions[rec.execution].proposal.steps)
                        != r.strategies[0].first_sensitive
            })
            .map(|rec| rec.execution);
        let index = r.discoveries.len();
        r.discoveries.push(a);
        if let Some(i) = chosen {
            let p = r.discoveries[index].executions[i].proposal.clone();
            let result = outcome(&r.discoveries[index], Some(i));
            let used = calls(&r.discoveries[index]);
            r.strategies.push(Strategy {
                id: strategy_id(&q, &kid, &p),
                first_sensitive: v3::first_sensitive(&p.steps),
                prediction: prediction(&p),
                proposal: p,
                discovery: index,
                selected_execution: i,
                cells: vec![Cell {
                    comparison: None,
                    failed_settlement: None,
                    policy: "pass".into(),
                    classification: "no_interference".into(),
                    original: None,
                    anchor: None,
                    recovery: None,
                    outcome: result,
                    calls: used,
                    detail: "对方持灰但始终放弃响应；只作为无干扰基准".into(),
                }],
                worst_first: None,
            });
        } else {
            r.limitations.push(
                "second_strategy_not_found: no distinct first-sensitive verified candidate".into(),
            );
        }
    }
    for row in &mut r.strategies {
        for policy in q.policies.iter().skip(1) {
            let mut rt = runtime.clone();
            let mut config = q.opponent.clone();
            config.policy = "ash_effect_once".into();
            config.effect_id = policy.clone();
            rt.interruption = Some(config);
            let ctx = PlanningContext {
                knowledge_bundle_id: kid.clone(),
                runtime: rt.clone(),
                initial: initial.clone(),
                anchor: None,
                proposal_mode: Some(ProposalMode::Frozen {
                    proposal: row.proposal.clone(),
                }),
            };
            let a = arm::plan_context(
                q.inner(q.analysis.search.node_budget, q.max_steps),
                engine.clone(),
                store,
                catalog,
                weights,
                pack.clone(),
                Some(ctx),
            )?;
            let mut c = Cell {
                comparison: None,
                failed_settlement: None,
                policy: policy.clone(),
                classification: "unknown".into(),
                outcome: outcome(&a, None),
                calls: calls(&a),
                original: Some(a),
                anchor: None,
                recovery: None,
                detail: String::new(),
            };
            let obs = c
                .original
                .as_ref()
                .unwrap()
                .executions
                .first()
                .and_then(|e| e.trace.observation.clone());
            if let Some(o) = obs {
                if response_hit(&o) {
                    let step = row
                        .proposal
                        .steps
                        .iter()
                        .position(|s| s.effect_id == *policy)
                        .ok_or("hit outside frozen proposal")?
                        + 2;
                    let left = q.analysis.search.node_budget.saturating_sub(c.calls);
                    let mut progress = FailedSettlement {
                        selections: vec![],
                        observation: o.clone(),
                        used_calls: 0,
                        replay_attempts: 0,
                        error: String::new(),
                    };
                    match settle(rt, o, &cat, &pack, step, q.max_steps, left, &mut progress) {
                        Ok(anchor) => {
                            c.calls += anchor.used_calls + anchor.reserved_calls;
                            let left = q.analysis.search.node_budget.saturating_sub(c.calls);
                            if left > 0 && q.max_steps > anchor.consumed_steps {
                                let mut inner = q.inner(left, q.max_steps - anchor.consumed_steps);
                                inner.goal.max_aux_candidates = q.goal.max_aux_candidates;
                                let context = PlanningContext {
                                    knowledge_bundle_id: kid.clone(),
                                    runtime: anchor.runtime.clone(),
                                    initial: anchor.state.clone(),
                                    anchor: Some(anchor.observation.clone()),
                                    proposal_mode: Some(ProposalMode::Recovery),
                                };
                                let recovery = arm::plan_context(
                                    inner,
                                    engine.clone(),
                                    store,
                                    catalog,
                                    weights,
                                    pack.clone(),
                                    Some(context),
                                )?;
                                c.calls += calls(&recovery);
                                c.outcome = outcome(&recovery, None);
                                c.recovery = Some(recovery);
                            }
                            c.classification = "original_plan_interrupted".into();
                            c.anchor = Some(anchor);
                        }
                        Err(e) => {
                            c.classification = if e.starts_with("budget") {
                                "budget_exhausted"
                            } else {
                                "recovery_coverage_gap"
                            }
                            .into();
                            c.calls += progress.used_calls;
                            progress.error = e.clone();
                            for selection in &mut progress.selections {
                                selection.before.replay_verified = false;
                            }
                            c.failed_settlement = Some(progress);
                            c.detail = e;
                        }
                    }
                } else {
                    c.classification = if effect_seen(&o, policy, &pack) {
                        "response_illegal"
                    } else if c.outcome.is_some() {
                        "response_point_not_reached"
                    } else {
                        "budget_or_execution_incomplete"
                    }
                    .into();
                }
            } else {
                c.classification = "engine_failure".into();
            }
            row.cells.push(c);
        }
    }
    finish(&mut r);
    validate_report(&r)?;
    Ok(r)
}

#[allow(clippy::too_many_arguments)]
fn validate_arm(
    a: &arm::PlanReport,
    q: &PlanRequest,
    kid: &str,
    runtime: &RunDuelRequest,
    initial: &SymbolicState,
    mode: &Option<ProposalMode>,
    anchor: Option<&DuelResult>,
    limit: usize,
    steps: usize,
) -> Result<(), String> {
    arm::validate_plan_contract(a)?;
    let c = a.context.as_ref().ok_or("missing strategy context")?;
    let mut expected = q.inner(limit, steps);
    expected.knowledge_id = Some(a.knowledge.id());
    if !same(&a.request, &expected)
        || c.knowledge_bundle_id != kid
        || prefix_key(&c.runtime) != prefix_key(runtime)
        || c.initial != *initial
        || !same(&c.proposal_mode, mode)
        || !same(&c.anchor.as_ref(), &anchor)
        || a.schema_version != 5
        || a.planner_profile != PROFILE
    {
        return Err("matrix arm/request/state/mode mismatch".into());
    }
    Ok(())
}
pub fn validate_report(r: &PlanReport) -> Result<(), String> {
    r.request.validate()?;
    let q = &r.request;
    if r.schema_version != 5
        || r.planner_profile != PROFILE
        || r.knowledge_id
            != hash(&(
                r.discoveries
                    .first()
                    .ok_or("missing pass discovery")?
                    .knowledge
                    .id(),
                &r.opponent_knowledge,
            ))
        || q.knowledge_id.as_deref() != Some(&r.knowledge_id)
        || r.discoveries.len() > 2
        || r.strategies.len() > 2
    {
        return Err("strategy envelope/source mismatch".into());
    }
    let base = &r.discoveries[0];
    let cat = &base.catalog_projection;
    let state = initial(q, cat)?;
    let mut runtime = base.analysis.runtime_request.clone();
    runtime.interruption = Some(q.opponent.clone());
    if runtime.deck != q.analysis.deck
        || runtime.opening_hand != q.analysis.opening_hand
        || runtime.seed != q.analysis.seed
        || runtime.protocol_version != 5
        || runtime.versions.initializer != "fixed-ash-strategy-v1"
        || !runtime.decisions.is_empty()
    {
        return Err("forged initial scenario".into());
    }
    let mut expected_rows = vec![];
    for (index, a) in r.discoveries.iter().enumerate() {
        let mode = (index == 1).then(|| ProposalMode::Diverse {
            expansion_start: r.discoveries[0].ledger.expansions,
        });
        let mut discovery_q = q.clone();
        discovery_q.max_proposals = if index == 0 {
            (q.max_proposals / 2).max(1)
        } else {
            q.max_proposals
                .saturating_sub(r.discoveries[0].proposals.plans.len())
        };
        if discovery_q.max_proposals == 0 {
            return Err("exhausted shared initial candidate allowance".into());
        }
        validate_arm(
            a,
            &discovery_q,
            &r.knowledge_id,
            &runtime,
            &state,
            &mode,
            None,
            q.analysis.search.node_budget,
            q.max_steps,
        )?;
        let selected = a
            .recommendations
            .iter()
            .find(|rec| {
                index == 0
                    || expected_rows
                        .first()
                        .is_some_and(|(_, first): &(usize, String)| {
                            v3::first_sensitive(&a.executions[rec.execution].proposal.steps)
                                != *first
                        })
            })
            .map(|rec| rec.execution);
        if let Some(i) = selected {
            expected_rows.push((i, v3::first_sensitive(&a.executions[i].proposal.steps)));
        }
    }
    if r.discoveries
        .iter()
        .map(|a| a.proposals.plans.len())
        .sum::<usize>()
        > q.max_proposals
        || r.discoveries
            .last()
            .is_some_and(|a| a.ledger.expansions > 5000)
    {
        return Err("shared initial search budget exceeded".into());
    }
    if expected_rows.len() != r.strategies.len() {
        return Err("missing/extra frozen strategy".into());
    }
    for (row_index, row) in r.strategies.iter().enumerate() {
        let (selected, first) = &expected_rows[row_index];
        let a = r
            .discoveries
            .get(row.discovery)
            .ok_or("unknown discovery")?;
        if row.discovery != row_index
            || row.selected_execution != *selected
            || row.first_sensitive != *first
            || !same(&row.proposal, &a.executions[*selected].proposal)
            || row.id != strategy_id(q, &r.knowledge_id, &row.proposal)
            || row.prediction != prediction(&row.proposal)
            || row.cells.len() != 8
        {
            return Err("forged frozen strategy/prediction".into());
        }
        for (policy, c) in q.policies.iter().zip(&row.cells) {
            if c.comparison != cell_comparison(a, *selected, &row.proposal, c, &q.goal) {
                return Err("forged resource comparison/goal loss".into());
            }
            if let Some(id) = c
                .comparison
                .as_ref()
                .and_then(|x| x.reference_window_id.as_ref())
            {
                if !a.witnesses.contains_key(id) {
                    return Err("unverified comparison window".into());
                }
            }
            if &c.policy != policy || c.calls > q.analysis.search.node_budget {
                return Err("matrix policy/order/budget mismatch".into());
            }
            if policy == "pass" {
                if c.original.is_some()
                    || c.anchor.is_some()
                    || c.recovery.is_some()
                    || c.failed_settlement.is_some()
                    || c.classification != "no_interference"
                    || c.calls != calls(a)
                    || c.outcome != outcome(a, Some(*selected))
                {
                    return Err("invalid pass cell".into());
                }
                continue;
            }
            let mut rt = runtime.clone();
            let mut config = q.opponent.clone();
            config.effect_id = policy.clone();
            config.policy = "ash_effect_once".into();
            rt.interruption = Some(config);
            let original = c.original.as_ref().ok_or("missing frozen execution")?;
            validate_arm(
                original,
                q,
                &r.knowledge_id,
                &rt,
                &state,
                &Some(ProposalMode::Frozen {
                    proposal: row.proposal.clone(),
                }),
                None,
                q.analysis.search.node_budget,
                q.max_steps,
            )?;
            let obs = original
                .executions
                .first()
                .and_then(|e| e.trace.observation.as_ref());
            let mut count = calls(original);
            if let Some(anchor) = &c.anchor {
                if c.failed_settlement.is_some() {
                    return Err("successful anchor has failed settlement".into());
                }
                let before = obs.ok_or("missing interrupted prefix")?;
                if !response_hit(before)
                    || !anchor.replay_verified
                    || anchor.reserved_calls != anchor.settlements.len() + 1
                    || anchor.used_calls != 2 * anchor.settlements.len() + 1
                    || anchor.state != reconstruct(&anchor.observation, cat, &original.knowledge)?
                    || anchor.id != hash(&(PROFILE, prefix_key(&anchor.runtime), &anchor.state))
                    || anchor.runtime.decisions != anchor.observation.resolved_decisions
                    || anchor.runtime.interruption != rt.interruption
                    || prefix_key(&anchor.runtime) != hash_prefix(&rt, &anchor.runtime.decisions)
                    || !anchor.observation.events.starts_with(&before.events)
                    || !anchor
                        .observation
                        .resolved_decisions
                        .starts_with(&before.resolved_decisions)
                    || !same(
                        &anchor.witness,
                        &witness(anchor.runtime.clone(), &anchor.observation),
                    )
                {
                    return Err("forged recovery anchor/state/prefix".into());
                }
                let mut prefix = before.resolved_decisions.clone();
                let mut active = "system:settlement".to_string();
                for s in &anchor.settlements {
                    if s.before.runtime.decisions != prefix
                        || !s.before.replay_verified
                        || prefix_key(&s.before.runtime) != hash_prefix(&rt, &prefix)
                        || !anchor.observation.events.starts_with(&s.before.events)
                    {
                        return Err("settlement before-prefix mismatch".into());
                    }
                    let f = anchor
                        .observation
                        .events
                        .iter()
                        .find(|e| e.sequence == s.selected.prompt_id)
                        .ok_or("missing settlement frame")?;
                    let p = recorded_prompt(f)?.ok_or("missing settlement prompt")?;
                    let mut dummy = anchor.observation.clone();
                    dummy.events = s.before.events.clone();
                    dummy.prompt = Some(p);
                    dummy.resolved_decisions = prefix.clone();
                    let (effect, reason, decision) =
                        settlement_choice(&dummy, &original.knowledge, &active)?;
                    if s.effect_id != effect || s.reason != reason || s.selected != decision {
                        return Err("forged settlement prediction/binding".into());
                    }
                    active = effect;
                    prefix.push(decision);
                    // Worker may add forced opponent passes between our two choices.
                    let end = anchor
                        .settlements
                        .iter()
                        .find(|next| next.selected.prompt_id > s.selected.prompt_id)
                        .map_or(anchor.runtime.decisions.len(), |next| {
                            next.before.decisions.len()
                        });
                    if !anchor.runtime.decisions.starts_with(&prefix) {
                        return Err("settlement decision linkage mismatch".into());
                    }
                    prefix = anchor.runtime.decisions[..end].to_vec();
                }
                let consumed = row
                    .proposal
                    .steps
                    .iter()
                    .position(|s| s.effect_id == *policy)
                    .ok_or("response outside frozen plan")?
                    + 2
                    + anchor
                        .settlements
                        .iter()
                        .filter(|s| {
                            matches!(
                                s.selected.choice,
                                Choice::YesNo { yes: true } | Choice::Chain { index: Some(_) }
                            )
                        })
                        .count();
                if anchor.consumed_steps != consumed || consumed > q.max_steps {
                    return Err("forged semantic step allowance".into());
                }
                let seen_frame = before
                    .events
                    .iter()
                    .find(|e| {
                        e.opcode == 70 && e.fields["code"] == 14558127u32 && e.fields["player"] == 1
                    })
                    .ok_or("missing Ash")?;
                let baseline_obs = a.executions[*selected]
                    .trace
                    .observation
                    .as_ref()
                    .ok_or("missing pass terminal")?;
                let own_before: Vec<_> = before
                    .resolved_decisions
                    .iter()
                    .filter(|d| d.player == 0 && d.prompt_id < seen_frame.sequence)
                    .collect();
                let baseline_own: Vec<_> = baseline_obs
                    .resolved_decisions
                    .iter()
                    .filter(|d| d.player == 0)
                    .take(own_before.len())
                    .collect();
                if own_before
                    .iter()
                    .zip(baseline_own)
                    .any(|(x, y)| x.choice != y.choice)
                {
                    return Err("choices changed before response".into());
                }
                count += anchor.used_calls + anchor.reserved_calls;
                if let Some(recovery) = &c.recovery {
                    let left = q
                        .analysis
                        .search
                        .node_budget
                        .checked_sub(count)
                        .ok_or("cell budget exceeded")?;
                    validate_arm(
                        recovery,
                        q,
                        &r.knowledge_id,
                        &anchor.runtime,
                        &anchor.state,
                        &Some(ProposalMode::Recovery),
                        Some(&anchor.observation),
                        left,
                        q.max_steps - consumed,
                    )?;
                    count += calls(recovery);
                    if c.outcome != outcome(recovery, None) {
                        return Err("forged recovery outcome".into());
                    }
                } else if c.outcome.is_some() {
                    return Err("unverified recovery outcome".into());
                }
                if c.classification != "original_plan_interrupted" {
                    return Err("forged interruption classification".into());
                }
            } else {
                if c.recovery.is_some() {
                    return Err("recovery without anchor".into());
                }
                if obs.is_some_and(response_hit) {
                    let failed = c
                        .failed_settlement
                        .as_ref()
                        .ok_or("missing failed settlement accounting")?;
                    if failed.used_calls != failed.selections.len() + failed.replay_attempts
                        || failed.replay_attempts > failed.selections.len() + 1
                        || failed.error != c.detail
                        || !failed.observation.events.starts_with(&obs.unwrap().events)
                    {
                        return Err("forged failed settlement calls/evidence".into());
                    }
                    validate_failed(failed, &rt, obs.unwrap(), &original.knowledge)?;
                    count += failed.used_calls;
                    if c.outcome.is_some()
                        || !matches!(
                            c.classification.as_str(),
                            "recovery_coverage_gap" | "budget_exhausted"
                        )
                    {
                        return Err("missing recovery anchor/evidence".into());
                    }
                } else {
                    let expected = if let Some(o) = obs {
                        if effect_seen(o, policy, &original.knowledge) {
                            "response_illegal"
                        } else if outcome(original, None).is_some() {
                            "response_point_not_reached"
                        } else {
                            "budget_or_execution_incomplete"
                        }
                    } else {
                        "engine_failure"
                    };
                    if c.classification != expected || c.outcome != outcome(original, None) {
                        return Err("forged no-response result".into());
                    }
                }
            }
            if c.calls != count {
                return Err("cell call accounting mismatch".into());
            }
        }
    }
    let rebuilt = summary(r);
    if r.total_calls != rebuilt.total
        || r.total_calls > q.total_budget
        || r.ranking != rebuilt.ranking
        || r.comparison != rebuilt.comparison
        || r.limitations != limitations(r)
        || r.strategies
            .iter()
            .zip(rebuilt.scores)
            .any(|(a, b)| a.worst_first != b)
    {
        return Err("forged matrix ranking/total".into());
    }
    Ok(())
}
fn automatic_extension(prefix: &[Decision], all: &[Decision], events: &[CoreEventFrame]) -> bool {
    all.starts_with(prefix)
        && all[prefix.len()..].iter().all(|d| {
            if d.player == 1 {
                return matches!(d.choice, Choice::Chain { index: None });
            }
            events
                .iter()
                .find(|e| e.sequence == d.prompt_id)
                .and_then(|e| recorded_prompt(e).ok().flatten())
                .is_some_and(|p| p.actions.len() == 1 && p.actions[0].choice == d.choice)
        })
}
fn validate_failed(
    f: &FailedSettlement,
    rt: &RunDuelRequest,
    original: &DuelResult,
    pack: &KnowledgePack,
) -> Result<(), String> {
    for e in &f.observation.events {
        if !frame_matches_raw(e)? {
            return Err("forged failed raw frame".into());
        }
    }
    if f.observation.protocol_version != 5
        || f.observation.versions != rt.versions
        || f.error.is_empty()
        || f.observation.events.len() < original.events.len()
        || !f
            .observation
            .resolved_decisions
            .starts_with(&original.resolved_decisions)
        || f.observation.steps
            != arm::recorded_steps(&f.observation.events, &f.observation.resolved_decisions)
    {
        return Err("failed observation provenance mismatch".into());
    }
    let mut prefix = original.resolved_decisions.clone();
    let mut active = "system:settlement".to_string();
    for (index, s) in f.selections.iter().enumerate() {
        if s.before.replay_verified
            || s.before.status != DuelStatus::DecisionRequired
            || prefix_key(&s.before.runtime) != hash_prefix(rt, &s.before.decisions)
            || s.before.runtime.decisions != s.before.decisions
            || !automatic_extension(&prefix, &s.before.decisions, &s.before.events)
            || !f.observation.events.starts_with(&s.before.events)
            || s.before.steps != arm::recorded_steps(&s.before.events, &s.before.decisions)
        {
            return Err("forged failed settlement witness/linkage".into());
        }
        let e = s
            .before
            .events
            .iter()
            .find(|e| e.sequence == s.selected.prompt_id)
            .ok_or("missing failed selection frame")?;
        let p = recorded_prompt(e)?.ok_or("missing failed prompt")?;
        let mut before = f.observation.clone();
        before.events = s.before.events.clone();
        before.prompt = Some(p);
        before.checkpoint = s.before.checkpoint.clone();
        before.resolved_decisions = s.before.decisions.clone();
        let (id, reason, decision) = settlement_choice(&before, pack, &active)?;
        if id != s.effect_id || reason != s.reason || decision != s.selected {
            return Err("forged failed settlement prediction/choice".into());
        }
        active = id;
        prefix = s.before.decisions.clone();
        prefix.push(decision);
        if index + 1 < f.selections.len() && !f.observation.resolved_decisions.starts_with(&prefix)
        {
            return Err("failed settlement skipped a confirmed choice".into());
        }
    }
    if !automatic_extension(
        &prefix,
        &f.observation.resolved_decisions,
        &f.observation.events,
    ) && !f.selections.last().is_some_and(|s| {
        f.observation.events == s.before.events
            && f.observation.resolved_decisions == s.before.decisions
    }) {
        return Err("failed settlement fabricated decision history".into());
    }
    Ok(())
}
fn hash_prefix(rt: &RunDuelRequest, decisions: &[Decision]) -> String {
    let mut x = rt.clone();
    x.decisions = decisions.to_vec();
    prefix_key(&x)
}
pub fn replay(
    r: &PlanReport,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
) -> Result<serde_json::Value, String> {
    validate_report(r)?;
    let ash = KnowledgePack::ash_source(&engine.catalog_path, &engine.scripts_path)?;
    if !same(&ash, &r.opponent_knowledge) {
        return Err("Ash source mismatch".into());
    }
    for a in &r.discoveries {
        arm::replay(a, engine.clone(), store)?;
    }
    for row in &r.strategies {
        for c in row.cells.iter().skip(1) {
            if let Some(a) = &c.original {
                arm::replay(a, engine.clone(), store)?;
            }
            if let Some(anchor) = &c.anchor {
                for s in &anchor.settlements {
                    verify_witness(&s.before, &engine)?;
                }
                verify_witness(&anchor.witness, &engine)?;
            }
            if let Some(a) = &c.recovery {
                arm::replay(a, engine.clone(), store)?;
            }
        }
    }
    Ok(
        serde_json::json!({"schema_version":5,"matrix_verified":r.strategies.len()==2&&r.ranking.len()==2,"report_evidence_verified":!r.strategies.is_empty()&&r.strategies.iter().flat_map(|s|&s.cells).all(|c|c.failed_settlement.is_none()),"unverified_failures":r.strategies.iter().flat_map(|s|&s.cells).filter(|c|c.failed_settlement.is_some()).map(|c|&c.policy).collect::<Vec<_>>(),"ranking":r.ranking,"total_calls":r.total_calls,"strategies":r.strategies.len()}),
    )
}

#[cfg(test)]
mod tests;
