//! One controlled Ash response, followed by planning from replayed engine facts.
use crate::{
    combo::ComboAnalyzeRequest,
    planning_v3::{self as arm, PlanningContext},
};
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use ygo_domain::{CardId, Catalog};
use ygo_engine_adapter::*;
use ygo_goal::{Facts, Goal};
use ygo_knowledge::KnowledgePack;
use ygo_planner::{v2::*, v3};
use ygo_search::combo::{prefix_key, ScoringConfig};
use ygo_storage::SnapshotStore;
pub const PROFILE: &str = "phantom-recovery-v1";
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum FailureClass {
    ResponsePointNotReached,
    ResponseIllegal,
    OriginalPlanInterrupted,
    RecoveryCoverageGap,
    PromptBindingFailed,
    BudgetExhausted,
    EngineFailure,
    NoRecoveryPlanFound,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Failure {
    pub category: FailureClass,
    pub detail: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ResourceChange {
    pub player: u8,
    pub code: u32,
    pub location: u8,
    pub before: i64,
    pub after: i64,
    pub delta: i64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ResourceComparison {
    pub kind: String,
    pub reference_window_witness: String,
    pub interrupted_state_id: String,
    pub baseline_execution_id: String,
    pub recovery_execution_id: Option<String>,
    pub interruption_paid_cost_events: Vec<u64>,
    pub interruption_window_changes: Vec<ResourceChange>,
    pub recovery_changes: Option<Vec<ResourceChange>>,
    pub terminal_difference: Option<Vec<ResourceChange>>,
    pub missing_expected_grave: BTreeMap<u32, usize>,
    pub changed_plan_reason: String,
}
impl From<String> for Failure {
    fn from(detail: String) -> Self {
        let category = match detail.split(':').next().unwrap_or("") {
            "response_point_not_reached" => FailureClass::ResponsePointNotReached,
            "response_illegal" => FailureClass::ResponseIllegal,
            "original_plan_interrupted" => FailureClass::OriginalPlanInterrupted,
            "recovery_coverage_gap" => FailureClass::RecoveryCoverageGap,
            "prompt_binding_failed" => FailureClass::PromptBindingFailed,
            "budget_exhausted" => FailureClass::BudgetExhausted,
            "engine_failure" => FailureClass::EngineFailure,
            _ => FailureClass::NoRecoveryPlanFound,
        };
        Self { category, detail }
    }
}
impl From<&str> for Failure {
    fn from(s: &str) -> Self {
        s.to_string().into()
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanRequest {
    pub schema_version: u16,
    pub analysis: ComboAnalyzeRequest,
    pub goal: Goal,
    pub knowledge_id: Option<String>,
    pub max_proposals: usize,
    pub max_steps: usize,
    pub interruption: InterruptionConfig,
}
impl PlanRequest {
    fn inner(&self) -> arm::PlanRequest {
        arm::PlanRequest {
            schema_version: 3,
            analysis: self.analysis.clone(),
            goal: self.goal.clone(),
            knowledge_id: None,
            max_proposals: self.max_proposals,
            max_steps: self.max_steps,
            scenario: None,
        }
    }
    pub fn validate(&self) -> Result<(), String> {
        self.inner().validate()?;
        self.interruption.validate()?;
        let mut expected = self.analysis.deck.clone();
        expected.extra.clear();
        expected.side.clear();
        let at = expected
            .main
            .iter()
            .position(|c| c.0 == 2964201)
            .ok_or("opponent setup requires Ryu-Ran placeholder")?;
        expected.main[at] = CardId(14558127);
        if self.schema_version != 4
            || self.analysis.search.node_budget > 512
            || self.max_steps < 4
            || self.interruption.opponent_deck != expected
            || self.interruption.policy != "ash_scales_once"
        {
            return Err("unsupported recovery request/resources/budget".into());
        }
        Ok(())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Interrupted {
    pub classification: FailureClass,
    pub consumed_steps: usize,
    pub runtime: RunDuelRequest,
    pub observation: DuelResult,
    pub original_proposal: Proposal,
    pub attempt: Attempt,
    pub state: SymbolicState,
    pub facts: Facts,
    pub state_id: String,
    pub replay_verified: bool,
    pub used_calls: usize,
    pub reserved_calls: usize,
    pub explanation: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanReport {
    #[serde(default)]
    pub comparison: Option<ResourceComparison>,
    pub schema_version: u16,
    pub planner_profile: String,
    pub request: PlanRequest,
    pub knowledge_id: String,
    pub opponent_knowledge: ygo_knowledge::CardKnowledge,
    pub baseline: Option<arm::PlanReport>,
    pub interrupted: Option<Interrupted>,
    pub recovery: Option<arm::PlanReport>,
    pub failures: Vec<Failure>,
    pub total_calls: usize,
    pub interruption_calls: usize,
    pub failed_interruption: Option<Attempt>,
    pub interruption_diagnostics: Vec<WorkerError>,
}
fn same<T: Serialize>(a: &T, b: &T) -> bool {
    serde_json::to_value(a).unwrap() == serde_json::to_value(b).unwrap()
}
fn state_id(runtime: &RunDuelRequest, state: &SymbolicState) -> String {
    ygo_knowledge::hash(&serde_json::to_vec(&(PROFILE, prefix_key(runtime), state)).unwrap())
}
pub(crate) fn initial(q: &PlanRequest, cat: &Catalog) -> Result<SymbolicState, String> {
    let mut s = v3::initialize(&q.analysis.deck, &q.analysis.opening_hand, cat)?;
    let mut remaining = q.interruption.opponent_deck.main.clone();
    let at = remaining
        .iter()
        .position(|c| c.0 == 14558127)
        .ok_or("missing Ash resource")?;
    remaining.remove(at);
    // validate_hand returns the remaining deck. Opponent identities are never own resources.
    for (zone, cards) in [
        (1, &mut remaining),
        (2, &mut q.interruption.opponent_hand.clone()),
    ] {
        for (i, c) in cards.iter().enumerate() {
            let meta = cat.get(c).ok_or("unknown opponent card")?;
            s.cards.push(Resource {
                instance: format!("opponent:{zone}:{i}"),
                code: c.0,
                location: zone,
                level: meta.level,
                base_level: meta.level,
                redirect: false,
                player: 1,
                overlay_host: None,
                xyz_summoned: false,
                epoch: 0,
            });
        }
    }
    Ok(s)
}
/// The first supported anchor is after the first Scales mill/Ash chain, before any other effect.
/// More complex anchors are rejected rather than guessing hidden restrictions or usage.
pub fn reconstruct(r: &DuelResult, pack: &KnowledgePack) -> Result<SymbolicState, String> {
    if r.protocol_version != 4
        || r.status != DuelStatus::DecisionRequired
        || r.error.is_some()
        || !r.coverage_gaps.is_empty()
        || r.checkpoint.turn != 1
        || r.checkpoint.turn_player != 0
        || r.checkpoint.phase != 4
        || !r
            .prompt
            .as_ref()
            .is_some_and(|p| p.player == 0 && p.opcode == 11)
    {
        return Err("recovery_coverage_gap: no settled own main-phase window".into());
    }
    let chains: Vec<_> = r.events.iter().filter(|e| e.opcode == 70).collect();
    if chains.len() != 2
        || chains[0].fields["code"] != 25538345u32
        || chains[1].fields["code"] != 14558127u32
        || chains[0].fields["description"].as_u64() != Some(25538345u64 << 20)
        || !r
            .events
            .iter()
            .any(|e| e.opcode == 76 && e.fields["chain"] == chains[0].fields["chain"])
        || r.events
            .iter()
            .rev()
            .find(|e| matches!(e.opcode, 70 | 74))
            .map_or(true, |e| e.opcode != 74)
    {
        return Err("recovery_coverage_gap: unsupported or unfinished interruption history".into());
    }
    let f = ygo_goal::actual_facts(r, &Default::default(), pack);
    if !f.history_complete {
        return Err("recovery_coverage_gap: incomplete history evidence".into());
    }
    let normals = f
        .history
        .iter()
        .filter(|h| h.kind == "normal_summon" && h.card.player == 0)
        .count();
    if normals != 1
        || !f
            .history
            .iter()
            .any(|h| h.kind == "effect_negated" && h.effect_id.as_deref() == Some("25538345:mill"))
    {
        return Err("recovery_coverage_gap: missing normal summon or negation identity".into());
    }
    let mut cards = vec![];
    for c in &f.cards {
        if !c.materials.is_empty() || c.location & 128 != 0 {
            return Err("recovery_coverage_gap: material anchor not supported".into());
        }
        let level = c
            .level
            .ok_or("recovery_coverage_gap: unknown actual level")?;
        cards.push(Resource {
            instance: c.instance.clone(),
            code: c.code,
            location: c.location,
            level,
            base_level: level,
            player: c.player,
            overlay_host: None,
            xyz_summoned: false,
            epoch: 0,
            redirect: false,
        });
    }
    let cost = f
        .history
        .iter()
        .filter(|h| h.kind == "sent_to_grave" && h.card.player == 0 && h.reason & 128 != 0)
        .count();
    if cost != 1
        || !f.history.iter().any(|h| {
            h.kind == "sent_to_grave"
                && h.card.player == 1
                && h.card.code == 14558127
                && h.reason & 128 != 0
        })
    {
        return Err("recovery_coverage_gap: missing paid costs".into());
    }
    let mut used = BTreeSet::from(["25538345:mill".into()]);
    if f.history
        .iter()
        .any(|h| h.card.player == 0 && h.card.code == 36426778 && h.kind == "special_summon")
    {
        used.insert("36426778:summon".into());
    }
    Ok(SymbolicState {
        cards,
        used,
        normal_left: 0,
        pending: vec![],
        dark_only: false,
        destroyed_xyz: BTreeSet::new(),
    })
}
fn explanation(s: &SymbolicState) -> Vec<String> {
    vec![
        "灰流丽无效 Torn Scales 效果；双方弃牌费用已支付，不退还；牌库送墓没有发生".into(),
        "Torn Scales 送墓次数与通常召唤已消耗，禁止再次使用；原计划依赖的墓地资源尚未取得".into(),
        format!(
            "恢复起点来自实际引擎窗口：手牌{}张、场上{}张；保持原目标，重新比较合法资源转移",
            s.cards
                .iter()
                .filter(|c| c.player == 0 && c.location == 2)
                .count(),
            s.cards
                .iter()
                .filter(|c| c.player == 0 && matches!(c.location, 4 | 8))
                .count()
        ),
    ]
}
pub fn plan(
    mut q: PlanRequest,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog: &str,
    weights: &ScoringConfig,
    pack: KnowledgePack,
) -> Result<PlanReport, String> {
    q.validate()?;
    let opponent_knowledge = KnowledgePack::ash_source(&engine.catalog_path, &engine.scripts_path)?;
    let knowledge_id =
        ygo_knowledge::hash(&serde_json::to_vec(&(pack.id(), &opponent_knowledge)).unwrap());
    if q.knowledge_id
        .as_ref()
        .is_some_and(|id| id != &knowledge_id)
    {
        return Err("interruption knowledge ID mismatch".into());
    }
    q.knowledge_id = Some(knowledge_id.clone());
    let (resolved, mut runtime, cat) =
        crate::combo::prepare(q.analysis.clone(), engine.clone(), store, catalog)?;
    q.analysis = resolved;
    if !ygo_domain::validate_catalog_deck(
        &q.interruption.opponent_deck,
        &store.banlist(&q.analysis.banlist_id)?.data,
        &cat,
    )
    .is_legal()
    {
        return Err("illegal opponent deck".into());
    }
    runtime.protocol_version = 4;
    runtime.versions.initializer = "fixed-interruption-v1".into();
    let mut pass = q.interruption.clone();
    pass.policy = "pass".into();
    runtime.interruption = Some(pass);
    let context = PlanningContext {
        proposal_mode: None,
        knowledge_bundle_id: knowledge_id.clone(),
        runtime: runtime.clone(),
        initial: initial(&q, &cat)?,
        anchor: None,
    };
    let baseline = arm::plan_context(
        q.inner(),
        engine.clone(),
        store,
        catalog,
        weights,
        pack.clone(),
        Some(context),
    )?;
    let mut report = PlanReport {
        comparison: None,
        schema_version: 4,
        planner_profile: PROFILE.into(),
        request: q.clone(),
        knowledge_id,
        opponent_knowledge,
        baseline: Some(baseline),
        interrupted: None,
        recovery: None,
        failures: vec![],
        total_calls: 0,
        interruption_calls: 0,
        failed_interruption: None,
        interruption_diagnostics: vec![],
    };
    let base = report.baseline.as_ref().unwrap();
    let Some(rec) = base.recommendations.first() else {
        let reason = if base.failure_summary.contains(&FailureKind::BudgetExhausted) {
            "budget_exhausted"
        } else if base.failure_summary.contains(&FailureKind::EngineFailure) {
            "engine_failure"
        } else {
            "response_point_not_reached"
        };
        report.failures.push(reason.into());
        finish(&mut report);
        return Ok(report);
    };
    let original = base.executions[rec.execution].proposal.clone();
    if !original
        .steps
        .iter()
        .any(|s| s.effect_id == q.interruption.effect_id)
    {
        report.failures.push("response_point_not_reached".into());
        finish(&mut report);
        return Ok(report);
    }
    runtime.interruption = Some(q.interruption.clone());
    let adapter = ProcessEngineAdapter::new(engine.clone());
    let mut budget = q.analysis.search.clone();
    // Leave one call for anchor verification and another for independent plan-replay.
    if budget.node_budget < 4 {
        report.failures.push("budget_exhausted".into());
        finish(&mut report);
        return Ok(report);
    }
    budget.node_budget -= 2;
    let out = execute_general(
        &adapter,
        &runtime,
        Proposals {
            plans: vec![original.clone()],
            expansions: 0,
            termination: "frozen_baseline".into(),
            coverage_gaps: vec![],
        },
        &budget,
        weights,
        &pack,
        true,
        |_| true,
    )?;
    report.interruption_calls = out.search.stats.engine_calls;
    report.interruption_diagnostics = out.search.diagnostics.clone();
    let Some(attempt) = out.attempts.into_iter().next() else {
        report.failures.push("engine_failure".into());
        finish(&mut report);
        return Ok(report);
    };
    let observation = attempt
        .observation
        .clone()
        .ok_or("missing interrupted observation")?;
    let state = match reconstruct(&observation, &pack) {
        Ok(s) => s,
        Err(e) => {
            report
                .failures
                .push(interruption_failure(&attempt, &pack, &e));
            report.failed_interruption = Some(attempt);
            finish(&mut report);
            return Ok(report);
        }
    };
    let mut anchor_runtime = runtime;
    anchor_runtime.decisions = observation.resolved_decisions.clone();
    report.interruption_calls += 1;
    let repeated = adapter.run(&anchor_runtime).map_err(|e| e.message)?;
    if !same(&observation.events, &repeated.events)
        || observation.checkpoint != repeated.checkpoint
        || observation.resolved_decisions != repeated.resolved_decisions
    {
        return Err("interrupted prefix replay mismatch".into());
    }
    let facts = ygo_goal::actual_facts(&observation, &cat, &pack);
    let stopped = Interrupted {
        classification: FailureClass::OriginalPlanInterrupted,
        consumed_steps: original
            .steps
            .iter()
            .position(|s| s.effect_id == q.interruption.effect_id)
            .ok_or("missing targeted step")?
            + 2,
        state_id: state_id(&anchor_runtime, &state),
        runtime: anchor_runtime.clone(),
        observation: observation.clone(),
        original_proposal: original,
        attempt,
        state: state.clone(),
        facts,
        replay_verified: true,
        used_calls: out.search.stats.engine_calls + 1,
        reserved_calls: 1,
        explanation: explanation(&state),
    };
    report.interrupted = Some(stopped);
    let prefix_steps = report.interrupted.as_ref().unwrap().consumed_steps;
    if q.max_steps <= prefix_steps {
        report.failures.push("budget_exhausted".into());
        finish(&mut report);
        return Ok(report);
    }
    let mut recovery_request = q.inner();
    recovery_request.max_steps -= prefix_steps;
    let ctx = PlanningContext {
        proposal_mode: None,
        knowledge_bundle_id: report.knowledge_id.clone(),
        runtime: anchor_runtime,
        initial: state,
        anchor: Some(observation),
    };
    report.recovery = Some(arm::plan_context(
        recovery_request,
        engine,
        store,
        catalog,
        weights,
        pack,
        Some(ctx),
    )?);
    if report.recovery.as_ref().unwrap().recommendations.is_empty() {
        report.failures.push("no_recovery_plan_found".into());
        if report
            .recovery
            .as_ref()
            .unwrap()
            .proposals
            .termination
            .contains("budget")
            || report
                .recovery
                .as_ref()
                .unwrap()
                .failure_summary
                .contains(&FailureKind::BudgetExhausted)
        {
            report.failures.push("budget_exhausted".into());
        }
    }
    finish(&mut report);
    validate_report(&report)?;
    Ok(report)
}
fn finish(r: &mut PlanReport) {
    r.total_calls = r
        .baseline
        .iter()
        .chain(r.recovery.iter())
        .map(|a| a.ledger.used_calls + a.ledger.reserved_calls)
        .sum::<usize>()
        + r.interruption_calls
        + r.interrupted.as_ref().map_or(0, |i| i.reserved_calls);
    r.comparison = resource_comparison(r);
}
fn inventory(c: &Checkpoint) -> BTreeMap<(u8, u32, u8), i64> {
    let mut counts = BTreeMap::new();
    for card in &c.cards {
        *counts
            .entry((card.player, card.code, card.location))
            .or_default() += 1;
        for code in &card.overlay {
            *counts.entry((card.player, *code, 128)).or_default() += 1;
        }
    }
    counts
}
pub(crate) fn resource_changes(before: &Checkpoint, after: &Checkpoint) -> Vec<ResourceChange> {
    let a = inventory(before);
    let b = inventory(after);
    a.keys()
        .chain(b.keys())
        .copied()
        .collect::<BTreeSet<_>>()
        .into_iter()
        .filter_map(|(player, code, location)| {
            let before = *a.get(&(player, code, location)).unwrap_or(&0);
            let after = *b.get(&(player, code, location)).unwrap_or(&0);
            (before != after).then_some(ResourceChange {
                player,
                code,
                location,
                before,
                after,
                delta: after - before,
            })
        })
        .collect()
}
fn resource_comparison(r: &PlanReport) -> Option<ResourceComparison> {
    let b = r.baseline.as_ref()?;
    let i = r.interrupted.as_ref()?;
    let chosen = b.recommendations.first()?;
    let e = b.executions.get(chosen.execution)?;
    let target = e
        .proposal
        .steps
        .iter()
        .position(|s| s.effect_id == r.request.interruption.effect_id)?;
    let reference = e
        .trace
        .predictions
        .iter()
        .find(|p| p.semantic_step > target)?;
    let terminal = &e.trace.observation.as_ref()?.checkpoint;
    let recovered = r.recovery.as_ref().and_then(|a| {
        a.recommendations
            .first()
            .and_then(|rec| a.executions.get(rec.execution))
    });
    let recovered_checkpoint = recovered
        .and_then(|x| x.trace.observation.as_ref())
        .map(|o| &o.checkpoint);
    let mut expected = BTreeMap::<u32, usize>::new();
    for c in e.proposal.steps[target]
        .after
        .cards
        .iter()
        .filter(|c| c.player == 0 && c.location == 16)
    {
        *expected.entry(c.code).or_default() += 1;
    }
    for c in i
        .observation
        .checkpoint
        .cards
        .iter()
        .filter(|c| c.player == 0 && c.location == 16)
    {
        if let Some(n) = expected.get_mut(&c.code) {
            *n = n.saturating_sub(1);
        }
    }
    expected.retain(|_, n| *n > 0);
    Some(ResourceComparison {
        kind:"actual_comparison".into(),reference_window_witness:reference.before_prefix.clone(),interrupted_state_id:i.state_id.clone(),baseline_execution_id:e.id.clone(),recovery_execution_id:recovered.map(|x|x.id.clone()),
        interruption_paid_cost_events:i.facts.history.iter().filter(|h|h.kind=="sent_to_grave"&&h.reason&128!=0).map(|h|h.event).collect(),
        interruption_window_changes:resource_changes(&reference.before_checkpoint,&i.observation.checkpoint),
        recovery_changes:recovered_checkpoint.map(|c|resource_changes(&i.observation.checkpoint,c)),
        terminal_difference:recovered_checkpoint.map(|c|resource_changes(terminal,c)),
        changed_plan_reason:format!("{}被无效后，原路线缺少预期墓地资源{:?}；从已核验窗口重新比较资源转移，保留原目标。终场对照仅比较本次有界搜索实际验证的线路。",r.request.interruption.effect_id,expected),
        missing_expected_grave:expected,
    })
}
fn interruption_failure(a: &Attempt, pack: &KnowledgePack, detail: &str) -> Failure {
    if a.failure == Some(FailureKind::BudgetExhausted) {
        return "budget_exhausted".into();
    }
    if a.failure == Some(FailureKind::EngineFailure) {
        return "engine_failure".into();
    }
    if let Some(o) = &a.observation {
        if !o
            .events
            .iter()
            .any(|e| e.opcode == 70 && e.fields["code"] == 25538345u32)
        {
            return "prompt_binding_failed".into();
        }
        if !o
            .events
            .iter()
            .any(|e| e.opcode == 70 && e.fields["code"] == 14558127u32)
        {
            return "response_illegal".into();
        }
        return reconstruct(o, pack)
            .err()
            .unwrap_or_else(|| detail.into())
            .into();
    }
    "engine_failure".into()
}
fn expected_failures(r: &PlanReport) -> Result<Vec<Failure>, String> {
    let b = r.baseline.as_ref().ok_or("missing baseline")?;
    let Some(rec) = b.recommendations.first() else {
        return Ok(vec![
            if b.failure_summary.contains(&FailureKind::BudgetExhausted) {
                "budget_exhausted"
            } else if b.failure_summary.contains(&FailureKind::EngineFailure) {
                "engine_failure"
            } else {
                "response_point_not_reached"
            }
            .into(),
        ]);
    };
    let e = b
        .executions
        .get(rec.execution)
        .ok_or("missing baseline execution")?;
    if !e
        .proposal
        .steps
        .iter()
        .any(|s| s.effect_id == r.request.interruption.effect_id)
    {
        return Ok(vec!["response_point_not_reached".into()]);
    }
    if r.request.analysis.search.node_budget < 4 {
        return Ok(vec!["budget_exhausted".into()]);
    }
    if let Some(a) = &r.failed_interruption {
        return Ok(vec![interruption_failure(a, &b.knowledge, "")]);
    }
    let Some(i) = &r.interrupted else {
        if !r.interruption_diagnostics.is_empty() {
            return Ok(vec!["engine_failure".into()]);
        }
        return Err("missing attempted interruption".into());
    };
    if r.request.max_steps <= i.consumed_steps {
        return Ok(vec!["budget_exhausted".into()]);
    }
    let a = r.recovery.as_ref().ok_or("missing recovery arm")?;
    let mut result = vec![];
    if a.recommendations.is_empty() {
        result.push("no_recovery_plan_found".into());
        if a.proposals.termination.contains("budget")
            || a.failure_summary.contains(&FailureKind::BudgetExhausted)
        {
            result.push("budget_exhausted".into());
        }
    }
    Ok(result)
}
pub fn validate_report(r: &PlanReport) -> Result<(), String> {
    r.request.validate()?;
    if r.failures != expected_failures(r)? {
        return Err("recovery failure classification mismatch".into());
    }
    if r.schema_version != 4
        || r.planner_profile != PROFILE
        || r.request.knowledge_id.as_deref() != Some(&r.knowledge_id)
    {
        return Err("recovery envelope mismatch".into());
    }
    let base = r.baseline.as_ref().ok_or("missing baseline")?;
    arm::validate_plan_contract(base)?;
    let mut expected_base_request = r.request.inner();
    expected_base_request.knowledge_id = Some(base.knowledge.id());
    if !same(&base.request, &expected_base_request) {
        return Err("baseline request/configuration mismatch".into());
    }
    if !same(&base.request.analysis, &r.request.analysis)
        || base.request.goal.id() != r.request.goal.id()
        || r.knowledge_id
            != ygo_knowledge::hash(
                &serde_json::to_vec(&(base.knowledge.id(), &r.opponent_knowledge)).unwrap(),
            )
    {
        return Err("recovery request/knowledge mismatch".into());
    }
    let ctx = base.context.as_ref().ok_or("missing baseline context")?;
    let mut pass = r.request.interruption.clone();
    pass.policy = "pass".into();
    if ctx.runtime.interruption.as_ref() != Some(&pass)
        || ctx.knowledge_bundle_id != r.knowledge_id
        || !ctx.runtime.decisions.is_empty()
        || ctx.anchor.is_some()
        || !same(
            &ctx.initial,
            &initial(&r.request, &base.catalog_projection)?,
        )
    {
        return Err("forged baseline resources".into());
    }
    if let Some(i) = &r.interrupted {
        let rebuilt = reconstruct(&i.observation, &base.knowledge)?;
        for e in &i.observation.events {
            if decode_frame(e.sequence, &e.raw)? != *e {
                return Err("raw interruption evidence mismatch".into());
            }
        }
        let mut expected_runtime = ctx.runtime.clone();
        expected_runtime.interruption = Some(r.request.interruption.clone());
        expected_runtime.decisions = i.runtime.decisions.clone();
        if prefix_key(&i.runtime) != prefix_key(&expected_runtime) {
            return Err("interrupted runtime provenance mismatch".into());
        }

        if i.used_calls != r.interruption_calls
            || i.classification != FailureClass::OriginalPlanInterrupted
            || i.attempt.goal_achieved
            || i.attempt.line_id.is_some()
            || i.attempt.status != "prediction_rejected"
            || i.attempt.failure.is_none()
            || !i.attempt.grave_resources.is_empty()
            || !i.replay_verified
            || !same(&i.state, &rebuilt)
            || i.state_id != state_id(&i.runtime, &rebuilt)
            || i.runtime.interruption.as_ref() != Some(&r.request.interruption)
            || i.runtime.decisions != i.observation.resolved_decisions
            || i.explanation != explanation(&rebuilt)
            || i.reserved_calls != 1
            || i.used_calls + i.reserved_calls > r.request.analysis.search.node_budget
            || i.facts
                != ygo_goal::actual_facts(&i.observation, &base.catalog_projection, &base.knowledge)
        {
            return Err("forged interruption/state/cost/history".into());
        }
        let rec = base
            .recommendations
            .first()
            .ok_or("missing selected baseline")?;
        let base_observation = base.executions[rec.execution]
            .trace
            .observation
            .as_ref()
            .ok_or("missing selected baseline observation")?;
        let response = i
            .observation
            .resolved_decisions
            .iter()
            .find(|d| d.player == 1 && matches!(d.choice, Choice::Chain { index: Some(_) }))
            .ok_or("missing actual opponent response")?;
        let prefix = (response.prompt_id as usize).min(i.observation.events.len());
        if base_observation.events.get(..prefix) != i.observation.events.get(..prefix)
            || base_observation
                .resolved_decisions
                .iter()
                .take_while(|d| d.prompt_id < response.prompt_id)
                .ne(i
                    .observation
                    .resolved_decisions
                    .iter()
                    .take_while(|d| d.prompt_id < response.prompt_id))
        {
            return Err("pre-interruption choices changed".into());
        }
        if !same(
            &i.original_proposal,
            &base.executions[rec.execution].proposal,
        ) || !same(&i.attempt.observation, &Some(i.observation.clone()))
        {
            return Err("interrupted route provenance mismatch".into());
        }
        if i.consumed_steps
            != i.original_proposal
                .steps
                .iter()
                .position(|s| s.effect_id == r.request.interruption.effect_id)
                .ok_or("missing interrupted effect")?
                + 2
        {
            return Err("interrupted semantic step accounting mismatch".into());
        }
        validate_bindings(&i.original_proposal, &i.attempt, &base.knowledge)?;
        for p in &i.attempt.predictions {
            let step = i
                .original_proposal
                .steps
                .get(p.semantic_step)
                .ok_or("invalid interrupted prediction step")?;
            let index = i
                .observation
                .resolved_decisions
                .iter()
                .position(|d| d == &p.selected)
                .ok_or("unconfirmed interrupted choice")?;
            let mut before = i.runtime.clone();
            before.decisions.truncate(index);
            let frame = i
                .observation
                .events
                .iter()
                .find(|e| e.sequence == p.selected.prompt_id)
                .ok_or("missing interrupted prompt")?;
            let base_prediction = base.executions[rec.execution]
                .trace
                .predictions
                .iter()
                .find(|x| x.selected == p.selected)
                .ok_or("interrupted prediction differs before response")?;
            if p.reason != step.reason
                || p.effect_id != step.effect_id
                || p.before_prefix != prefix_key(&before)
                || p.before_events != base_prediction.before_events
                || p.before_checkpoint != base_prediction.before_checkpoint
                || p.alternatives != prompt_metadata(frame.sequence, &frame.raw)?
                || p.comparisons
                    != assess_alternatives(
                        &i.original_proposal,
                        p.semantic_step,
                        &p.alternatives,
                        &p.selected.choice,
                        &base.knowledge,
                    )
                || p.outcome != "observed"
                || p.after_events > i.observation.events.len()
                || p.after_events < p.before_events
            {
                return Err("interrupted prediction chronology/references mismatch".into());
            }
        }
        if let Some(a) = &r.recovery {
            arm::validate_plan_contract(a)?;
            let c = a.context.as_ref().ok_or("missing recovery context")?;
            let mut expected_request = expected_base_request.clone();
            expected_request.max_steps = expected_request
                .max_steps
                .checked_sub(i.consumed_steps)
                .ok_or("invalid consumed steps")?;
            if !same(&a.request, &expected_request)
                || !same(&a.knowledge, &base.knowledge)
                || a.ledger.limit != r.request.analysis.search.node_budget
            {
                return Err("recovery request/knowledge/arm budget mismatch".into());
            }
            if !same(&c.runtime, &i.runtime)
                || c.knowledge_bundle_id != r.knowledge_id
                || !same(&c.initial, &i.state)
                || !same(&c.anchor, &Some(i.observation.clone()))
                || a.request.goal.id() != r.request.goal.id()
                || a.request.max_steps + i.consumed_steps != r.request.max_steps
            {
                return Err("recovery prefix/anchor mismatch".into());
            }
        }
    } else if r.recovery.is_some() {
        return Err("recovery without interruption".into());
    }
    if let Some(a) = &r.failed_interruption {
        if r.interrupted.is_some()
            || a.goal_achieved
            || a.line_id.is_some()
            || a.status == "engine_verified"
        {
            return Err("failed interruption claims success".into());
        }
        if let Some(o) = &a.observation {
            if o.protocol_version != 4 {
                return Err("failed interruption protocol mismatch".into());
            }
            for e in &o.events {
                if decode_frame(e.sequence, &e.raw)? != *e {
                    return Err("failed interruption raw mismatch".into());
                }
            }
        }
    }
    if r.interruption_calls > r.request.analysis.search.node_budget
        || (r.interrupted.is_none()
            && r.interruption_calls > 0
            && r.failed_interruption.is_none()
            && r.interruption_diagnostics.is_empty())
    {
        return Err("unaccounted interrupted attempt".into());
    }
    let mut expected = r.clone();
    finish(&mut expected);
    if r.comparison != expected.comparison {
        return Err("resource comparison arithmetic/references mismatch".into());
    }
    if let Some(c) = &r.comparison {
        if !base.witnesses.contains_key(&c.reference_window_witness) {
            return Err("unverified resource reference window".into());
        }
    }
    if r.total_calls != expected.total_calls
        || r.total_calls > 3 * r.request.analysis.search.node_budget
    {
        return Err("recovery total budget mismatch".into());
    }
    Ok(())
}
pub fn replay(
    r: &PlanReport,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
) -> Result<serde_json::Value, String> {
    validate_report(r)?;
    if !same(
        &r.opponent_knowledge,
        &KnowledgePack::ash_source(&engine.catalog_path, &engine.scripts_path)?,
    ) {
        return Err("Ash knowledge sources changed".into());
    }
    let mut arms = BTreeMap::new();
    for (name, a) in [("baseline", &r.baseline), ("recovery", &r.recovery)] {
        if let Some(a) = a {
            if !a.recommendations.is_empty() {
                arms.insert(name, arm::replay(a, engine.clone(), store)?);
            }
        }
    }
    if let Some(i) = &r.interrupted {
        let mut q = i.runtime.clone();
        q.engine = engine.clone();
        let actual = ProcessEngineAdapter::new(engine)
            .run(&q)
            .map_err(|e| e.message)?;
        if !same(&actual.events, &i.observation.events)
            || actual.checkpoint != i.observation.checkpoint
            || actual.resolved_decisions != i.runtime.decisions
            || actual.steps != i.observation.steps
            || actual.loaded_scripts != i.observation.loaded_scripts
        {
            return Err("recovery anchor independent replay mismatch".into());
        }
    }
    Ok(
        serde_json::json!({"schema_version":4,"arms":arms,"total_calls":r.total_calls,"anchor_replayed":r.interrupted.is_some()}),
    )
}
