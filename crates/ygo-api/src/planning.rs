use crate::combo::{AnalysisReport, ComboAnalyzeRequest};
use serde::{Deserialize, Serialize};
use ygo_engine_adapter::*;
use ygo_knowledge::KnowledgePack;
use ygo_planner::{Attempt, Proposals};
use ygo_search::combo::{prefix_key, ScoringConfig};
use ygo_storage::SnapshotStore;
fn goal() -> String {
    "rusty-fog".into()
}
fn proposals() -> usize {
    8
}
fn steps() -> usize {
    32
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanRequest {
    pub schema_version: u16,
    pub analysis: ComboAnalyzeRequest,
    #[serde(default = "goal")]
    pub goal: String,
    #[serde(default)]
    pub knowledge_id: Option<String>,
    #[serde(default = "proposals")]
    pub max_proposals: usize,
    #[serde(default = "steps")]
    pub max_steps: usize,
}
impl PlanRequest {
    pub fn validate(&self) -> Result<(), String> {
        if self.schema_version != 1
            || self.goal != "rusty-fog"
            || self.max_proposals == 0
            || self.max_proposals > 8
            || self.max_steps == 0
            || self.max_steps > 32
        {
            return Err("unsupported planning goal/version/limits".into());
        }
        self.analysis.search.validate()
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PlanReport {
    pub schema_version: u16,
    pub knowledge_id: String,
    pub knowledge: KnowledgePack,
    pub request: PlanRequest,
    pub proposals: Proposals,
    pub attempts: Vec<Attempt>,
    pub analysis: AnalysisReport,
}
pub fn plan(
    mut request: PlanRequest,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    active_catalog: &str,
    weights: &ScoringConfig,
    knowledge: KnowledgePack,
) -> Result<PlanReport, String> {
    request.validate()?;
    knowledge.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )?;
    let knowledge_id = knowledge.id();
    if request
        .knowledge_id
        .as_ref()
        .is_some_and(|id| id != &knowledge_id)
    {
        return Err("requested knowledge ID mismatch".into());
    }
    let (resolved, runtime, catalog) = crate::combo::prepare(
        request.analysis.clone(),
        engine.clone(),
        store,
        active_catalog,
    )?;
    let proposals = ygo_planner::propose(
        &resolved.deck,
        &resolved.opening_hand,
        &catalog,
        &knowledge,
        request.max_proposals,
        request.max_steps,
    )?;
    let result = ygo_planner::execute(
        &ProcessEngineAdapter::new(engine),
        &runtime,
        proposals,
        &resolved.search,
        weights,
        &knowledge,
    )?;
    request.analysis = resolved.clone();
    request.knowledge_id = Some(knowledge_id.clone());
    let card_names = catalog
        .values()
        .filter(|c| {
            resolved
                .deck
                .main
                .iter()
                .chain(&resolved.deck.extra)
                .any(|id| *id == c.id)
        })
        .map(|c| (c.id.0, c.name.clone()))
        .collect();
    let report = PlanReport {
        schema_version: 1,
        knowledge_id,
        knowledge,
        request,
        proposals: result.proposals,
        attempts: result.attempts,
        analysis: AnalysisReport {
            schema_version: 2,
            request: resolved,
            runtime_request: runtime,
            search: result.search,
            card_names,
        },
    };
    validate_plan_contract(&report)?;
    Ok(report)
}
pub fn validate_plan_contract(report: &PlanReport) -> Result<(), String> {
    report.request.validate()?;
    report.knowledge.validate()?;
    crate::combo::validate_report_contract(&report.analysis)?;
    if report.schema_version != 1
        || report.knowledge_id != report.knowledge.id()
        || report.request.knowledge_id.as_deref() != Some(report.knowledge_id.as_str())
        || serde_json::to_value(&report.request.analysis).map_err(|e| e.to_string())?
            != serde_json::to_value(&report.analysis.request).map_err(|e| e.to_string())?
        || report.knowledge.cdb_sha256 != report.analysis.runtime_request.versions.cdb_sha256
        || report.knowledge.scripts_sha256
            != report.analysis.runtime_request.versions.scripts_sha256
        || report.proposals.plans.len() > report.request.max_proposals
    {
        return Err("planning envelope/provenance mismatch".into());
    }
    let mut ids = std::collections::BTreeSet::new();
    for p in &report.proposals.plans {
        let expected = ygo_knowledge::hash(
            &serde_json::to_vec(&(report.knowledge_id.clone(), &p.steps))
                .map_err(|e| e.to_string())?,
        );
        if p.id != expected
            || !ids.insert(p.id.clone())
            || p.steps.is_empty()
            || p.steps.len() > report.request.max_steps
            || !p.goal_predicted
            || !ygo_planner::goal(&p.steps.last().unwrap().after)
        {
            return Err("invalid symbolic proposal".into());
        }
    }
    for a in &report.attempts {
        let proposal = report
            .proposals
            .plans
            .iter()
            .find(|p| p.id == a.proposal_id)
            .ok_or("unknown proposal evidence")?;
        let observed = a
            .observation
            .as_ref()
            .ok_or("missing observation evidence")?;
        ygo_planner::validate_bindings(proposal, a, &report.knowledge)?;
        let mut previous = 0;
        for (number, prediction) in a.predictions.iter().enumerate() {
            let index = match observed
                .resolved_decisions
                .iter()
                .position(|d| d == &prediction.selected)
            {
                Some(index) if prediction.outcome == "observed" => index,
                None if prediction.outcome == "unobserved"
                    && !a.goal_achieved
                    && !a.discrepancies.is_empty()
                    && number + 1 == a.predictions.len()
                    && prediction.before_events == prediction.after_events =>
                {
                    observed.resolved_decisions.len()
                }
                _ => return Err("prediction outcome/observation mismatch".into()),
            };
            let mut prefix = report.analysis.runtime_request.clone();
            prefix.decisions = observed.resolved_decisions[..index].to_vec();
            let expected_reason = proposal
                .steps
                .get(prediction.semantic_step)
                .map_or("目标已预测完成；结束回合并验证终场", |s| {
                    s.reason.as_str()
                });
            let expected_effect = proposal
                .steps
                .get(prediction.semantic_step)
                .map_or("system:end_turn", |s| s.effect_id.as_str());
            let frame = observed
                .events
                .iter()
                .find(|e| e.sequence == prediction.selected.prompt_id)
                .ok_or("missing prediction prompt")?;
            if prediction.reason != expected_reason
                || prediction.effect_id != expected_effect
                || prediction.before_prefix != prefix_key(&prefix)
                || prediction.before_events < previous
                || prediction.before_events < prediction.selected.prompt_id as usize
                || prediction.after_events < prediction.before_events
                || prediction.after_events > observed.events.len()
                || prediction.alternatives != prompt_metadata(frame.sequence, &frame.raw)?
                || prediction.comparisons
                    != ygo_planner::assess_alternatives(
                        proposal,
                        prediction.semantic_step,
                        &prediction.alternatives,
                        &prediction.selected.choice,
                        &report.knowledge,
                    )
                || !prediction
                    .alternatives
                    .iter()
                    .any(|m| m.choice == prediction.selected.choice)
            {
                return Err("prediction chronology/reference mismatch".into());
            }
            previous = prediction.after_events;
        }
        if a.goal_achieved {
            if a.predictions.is_empty()
                || (0..proposal.steps.len())
                    .any(|i| !a.predictions.iter().any(|p| p.semantic_step == i))
            {
                return Err("verified attempt lacks pre-execution predictions".into());
            }
            let id = a.line_id.as_deref().ok_or("missing verified line ID")?;
            let line = report
                .analysis
                .search
                .lines
                .iter()
                .find(|l| l.id == id)
                .ok_or("unknown verified line")?;
            if a.status != "engine_verified"
                || !a.discrepancies.is_empty()
                || !ygo_planner::checkpoint_goal(&line.result.checkpoint)
                || line.result.status != DuelStatus::EngineVerified
                || observed.status != line.result.status
                || observed.checkpoint != line.result.checkpoint
                || observed.events != line.result.events
                || observed.steps != line.result.steps
                || observed.loaded_scripts != line.result.loaded_scripts
                || observed.resolved_decisions != line.result.resolved_decisions
                || observed.versions != line.result.versions
            {
                return Err("planning goal verification mismatch".into());
            }
        } else if a.line_id.is_some() || a.status == "engine_verified" {
            return Err("falsely verified attempt".into());
        }
    }
    for line in &report.analysis.search.lines {
        if !report
            .attempts
            .iter()
            .any(|a| a.goal_achieved && a.line_id.as_deref() == Some(line.id.as_str()))
        {
            return Err("verified line has no prediction evidence".into());
        }
    }
    Ok(())
}
pub fn replay(
    report: &PlanReport,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
) -> Result<serde_json::Value, String> {
    validate_plan_contract(report)?;
    report.knowledge.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )?;
    let catalog = store.catalog(&report.analysis.runtime_request.versions.catalog)?;
    let predicted = ygo_planner::propose(
        &report.request.analysis.deck,
        &report.request.analysis.opening_hand,
        &catalog.data,
        &report.knowledge,
        report.request.max_proposals,
        report.request.max_steps,
    )?;
    if serde_json::to_value(&predicted).map_err(|e| e.to_string())?
        != serde_json::to_value(&report.proposals).map_err(|e| e.to_string())?
    {
        return Err("causal proposal regeneration mismatch".into());
    }
    let banlist = store.banlist(&report.analysis.runtime_request.versions.banlist)?;
    if catalog.source_sha256 != report.analysis.runtime_request.versions.cdb_sha256
        || banlist
            .effective_date
            .as_deref()
            .map_or(true, |d| d > report.analysis.request.as_of.as_str())
        || !ygo_domain::validate_catalog_deck(
            &report.analysis.runtime_request.deck,
            &banlist.data,
            &catalog.data,
        )
        .is_legal()
    {
        return Err("planning replay deck/catalog/banlist mismatch".into());
    }
    let start = std::time::Instant::now();
    let budget = &report.request.analysis.search;
    let adapter = ProcessEngineAdapter::new(engine.clone());
    let mut calls = 0;
    let mut verified_lines = vec![];
    if report.analysis.search.lines.is_empty() {
        return Err("report contains no goal lines to replay".into());
    }
    for line in &report.analysis.search.lines {
        let mut q = report.analysis.runtime_request.clone();
        q.engine = engine.clone();
        q.decisions = line.decisions.clone();
        let actual = bounded_replay_run(&adapter, &q, budget, start, &mut calls)?;
        if actual.status != line.result.status
            || actual.checkpoint != line.result.checkpoint
            || actual.events != line.result.events
            || actual.steps != line.result.steps
            || actual.loaded_scripts != line.result.loaded_scripts
            || actual.resolved_decisions != line.decisions
        {
            return Err("independent planning line replay mismatch".into());
        }
        verified_lines.push(
            serde_json::json!({"id":line.id,"replay_verified":true,"verification":actual.status}),
        );
    }
    let verified = serde_json::json!({"schema_version":2,"lines":verified_lines});
    let mut witnesses = std::collections::BTreeMap::<String, DuelResult>::new();
    for attempt in report.attempts.iter().filter(|a| a.goal_achieved) {
        let observation = attempt.observation.as_ref().ok_or("missing observation")?;
        for prediction in &attempt.predictions {
            if !witnesses.contains_key(&prediction.before_prefix) {
                let index = observation
                    .resolved_decisions
                    .iter()
                    .position(|d| d == &prediction.selected)
                    .ok_or("missing replay decision")?;
                let mut q = report.analysis.runtime_request.clone();
                q.engine = engine.clone();
                q.decisions = observation.resolved_decisions[..index].to_vec();
                let actual = bounded_replay_run(&adapter, &q, budget, start, &mut calls)?;
                witnesses.insert(prediction.before_prefix.clone(), actual);
            }
            let actual = &witnesses[&prediction.before_prefix];
            if actual.checkpoint != prediction.before_checkpoint
                || actual.events.len() != prediction.before_events
                || actual.prompt.as_ref().map(|p| p.id) != Some(prediction.selected.prompt_id)
            {
                return Err("pre-execution checkpoint witness mismatch".into());
            }
        }
    }
    Ok(
        serde_json::json!({"schema_version":1,"goal":report.request.goal,"knowledge_id":report.knowledge_id,"prediction_references_verified":true,"prefix_witnesses":witnesses.len(),"engine_calls":calls,"replay":verified}),
    )
}

fn bounded_replay_run<A: EngineAdapter>(
    adapter: &A,
    request: &RunDuelRequest,
    budget: &ygo_search::combo::SearchBudget,
    start: std::time::Instant,
    calls: &mut usize,
) -> Result<DuelResult, String> {
    let left = budget
        .time_limit_ms
        .saturating_sub(start.elapsed().as_millis() as u64);
    if left == 0 || *calls >= budget.node_budget {
        return Err("shared planning replay budget exhausted".into());
    }
    let mut q = request.clone();
    q.engine.timeout_ms = q.engine.timeout_ms.min(left);
    *calls += 1;
    adapter
        .run(&q)
        .map_err(|e| format!("{}: {}", e.code, e.message))
}
#[cfg(test)]
mod replay_regression {
    use super::*;
    struct Spy(std::cell::Cell<usize>, std::cell::Cell<u64>);
    impl EngineAdapter for Spy {
        fn doctor(&self) -> DoctorReport {
            unreachable!()
        }
        fn run(&self, q: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.0.set(self.0.get() + 1);
            self.1.set(q.engine.timeout_ms);
            Err(WorkerError::new("fixture", "replay", "fixture stop"))
        }
    }
    #[test]
    fn line_and_prefix_replays_share_call_and_remaining_time_limits() {
        let spy = Spy(std::cell::Cell::new(0), std::cell::Cell::new(0));
        let mut calls = 0;
        let q = RunDuelRequest {
            protocol_version: 2,
            engine: Default::default(),
            deck: Default::default(),
            opening_hand: vec![],
            seed: 1,
            decisions: vec![],
            versions: Default::default(),
            probe_only: false,
            scenario: None,
            interruption: None,
        };
        let budget = ygo_search::combo::SearchBudget {
            node_budget: 1,
            time_limit_ms: 7,
            ..Default::default()
        };
        let start = std::time::Instant::now();
        assert!(bounded_replay_run(&spy, &q, &budget, start, &mut calls).is_err());
        assert!(spy.1.get() <= 7);
        assert!(bounded_replay_run(&spy, &q, &budget, start, &mut calls).is_err());
        assert_eq!(spy.0.get(), 1);
    }
}
