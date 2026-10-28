//! Internal vertical integration. This is not the fully certified v6 API.
use super::*;
use std::sync::Arc;
use ygo_engine_adapter::*;
use ygo_goal::{actual_trace_v6, verify_query_replays, Goal, QueryWitness, TraceWindow};
mod capture;
pub use capture::*;
mod resumable;
mod resumable_loop;
#[cfg(test)]
pub use resumable::advance_execution_v1_with_backend;
pub use resumable::{
    advance_execution_v1, begin_execution_v1, persist_execution_semantics_v1, resume_execution_v1,
    ExecutionCheckpointV1, ExecutionIntentV1, ExecutionProgressV1, ExecutionRecoveryStatus,
};
pub use resumable_loop::{
    advance_resumable_partial_execution_v1, advance_resumable_query_audit_v1,
    begin_resumable_partial_execution_v1, resume_resumable_partial_execution_v1,
    ResumableAuditProgressV1, ResumableAuditStatusV1, ResumableExecutionPhaseV1,
    ResumableLoopIntentV1, ResumablePartialExecutionV1,
};
#[cfg(test)]
pub use resumable_loop::{
    advance_resumable_partial_execution_v1_with_backend,
    advance_resumable_query_audit_v1_with_backend,
};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialDecisionEvidence {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub checkpoint_id: Option<String>,
    pub before_call: u64,
    pub step: Option<usize>,
    pub prompt: u64,
    pub prefix_id: String,
    pub public: FirstTurnPublicState,
    pub choice: Choice,
    pub instance_map: BTreeMap<String, String>,
    pub used_roles: BTreeSet<usize>,
}
fn prefix_id(result: &DuelResult) -> String {
    ygo_knowledge::hash(
        &serde_json::to_vec(&(
            result.events.iter().map(|e| &e.raw).collect::<Vec<_>>(),
            &result.resolved_decisions,
        ))
        .unwrap(),
    )
}
fn choice_checkpoint(plan_id: &str, prompt: u64) -> String {
    format!("partial-{plan_id}-before-choice-{prompt}")
}
fn immutable_choice_checkpoint(plan: &str, evidence: &PartialDecisionEvidence) -> String {
    let mut value = serde_json::to_value(evidence).unwrap();
    value.as_object_mut().unwrap().remove("checkpoint_id");
    format!(
        "immutable/partial-choice/{}",
        ygo_knowledge::hash(&serde_json::to_vec(&(plan, value)).unwrap())
    )
}
fn evidence_checkpoint(plan: &str, evidence: &PartialDecisionEvidence) -> String {
    evidence
        .checkpoint_id
        .clone()
        .unwrap_or_else(|| choice_checkpoint(plan, evidence.prompt))
}
fn validate_raw_choice(result: &DuelResult, choice: &Choice) -> Result<u64, String> {
    let frame = result.events.last().ok_or("missing actual raw prompt")?;
    let parsed = result.prompt.as_ref().ok_or("missing actual prompt")?;
    if !frame_matches_raw(frame)?
        || parsed.id != frame.sequence
        || !prompt_matches_raw(parsed, &frame.raw)?
        || !parsed.actions.iter().any(|a| &a.choice == choice)
        || parsed.player != 0
    {
        return Err("choice does not match actual legal raw prompt".into());
    }
    Ok(parsed.id)
}
#[cfg(test)]
#[test]
fn compact_new_frame_with_legacy_menu_never_grants_new_choices() {
    let mut raw = vec![11, 0];
    raw.extend([0; 24]);
    raw.extend([1, 1, 1]);
    let frame = decode_frame(1, &raw).unwrap();
    let mut prompt = parse_prompt(1, &raw).unwrap().unwrap();
    prompt
        .actions
        .retain(|a| !matches!(a.choice, Choice::Command { command: 6 | 8, .. }));
    let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "unused"));
    result.events = vec![frame];
    result.prompt = Some(prompt);
    assert_eq!(
        validate_raw_choice(
            &result,
            &Choice::Command {
                command: 7,
                index: 0
            }
        )
        .unwrap(),
        1
    );
    for command in [6, 8] {
        assert!(validate_raw_choice(&result, &Choice::Command { command, index: 0 }).is_err());
    }
    let mut changed = result.clone();
    changed.prompt.as_mut().unwrap().player = 1;
    assert!(validate_raw_choice(
        &changed,
        &Choice::Command {
            command: 7,
            index: 0
        }
    )
    .is_err());
    let mut changed = result.clone();
    changed.prompt.as_mut().unwrap().id = 2;
    assert!(validate_raw_choice(
        &changed,
        &Choice::Command {
            command: 7,
            index: 0
        }
    )
    .is_err());
    let mut changed = result;
    changed.events[0].fields["injected"] = serde_json::json!(true);
    assert!(validate_raw_choice(
        &changed,
        &Choice::Command {
            command: 7,
            index: 0
        }
    )
    .is_err());
}
fn persist_choice(
    journal: &CallJournal,
    plan: &str,
    result: &DuelResult,
    step: Option<usize>,
    choice: Choice,
    map: &BTreeMap<String, String>,
    used: &BTreeSet<usize>,
) -> Result<PartialDecisionEvidence, StepFailure> {
    let prompt = validate_raw_choice(result, &choice)?;
    let mut evidence = PartialDecisionEvidence {
        checkpoint_id: None,
        before_call: journal.stats().map_err(StepFailure::journal)?.consumed as u64 + 1,
        step,
        prompt,
        prefix_id: prefix_id(result),
        public: first_turn_public_state(&result.checkpoint),
        choice,
        instance_map: map.clone(),
        used_roles: used.clone(),
    };
    evidence.checkpoint_id = Some(immutable_choice_checkpoint(plan, &evidence));
    journal
        .save_checkpoint(
            &evidence_checkpoint(plan, &evidence),
            &serde_json::to_value(&evidence).unwrap(),
        )
        .map_err(StepFailure::journal)?;
    Ok(evidence)
}
pub fn validate_choice_checkpoint(
    evidence: &PartialDecisionEvidence,
    plan: &str,
    before: &DuelResult,
    journal: &CallJournal,
) -> Result<(), String> {
    let name = evidence_checkpoint(plan, evidence);
    if evidence.checkpoint_id.is_some() && name != immutable_choice_checkpoint(plan, evidence) {
        return Err("choice checkpoint identity differs".into());
    }
    let saved = journal
        .checkpoint(&name)
        .map_err(|e| e.message)?
        .ok_or("missing pre-choice checkpoint")?;
    let consumed = journal
        .checkpoint_consumed(&name)
        .map_err(|e| e.message)?
        .ok_or("missing checkpoint count")?;
    if saved != serde_json::to_value(evidence).unwrap()
        || evidence.before_call != consumed as u64 + 1
        || validate_raw_choice(before, &evidence.choice)? != evidence.prompt
        || evidence.prefix_id != prefix_id(before)
        || serde_json::to_value(&evidence.public).unwrap()
            != serde_json::to_value(first_turn_public_state(&before.checkpoint)).unwrap()
    {
        return Err("pre-choice timing, prefix, or public facts differ".into());
    }
    Ok(())
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialCandidateComparison {
    pub rule_id: String,
    pub source: String,
    pub selections: Vec<SemanticSelection>,
    pub requirements: Vec<String>,
    pub goal_after: ygo_goal::Evaluation,
    pub cost_change: BTreeMap<u8, i64>,
    pub resolution_change: BTreeMap<u8, i64>,
}
fn resource_change(before: &CausalState, after: &CausalState) -> BTreeMap<u8, i64> {
    [2, 4, 8, 16, 32, 64, 132]
        .into_iter()
        .map(|zone| {
            let count = |s: &CausalState| {
                s.cards
                    .iter()
                    .filter(|c| c.card.player == 0 && c.card.location == zone)
                    .count() as i64
            };
            (zone, count(after) - count(before))
        })
        .collect()
}
fn comparisons(
    state: &CausalState,
    options: &Successors,
    goal: &Goal,
) -> Vec<PartialCandidateComparison> {
    options
        .transitions
        .iter()
        .map(|t| PartialCandidateComparison {
            rule_id: t.rule_id.clone(),
            source: t.source.clone(),
            selections: t.selections.clone(),
            requirements: t.requirements.clone(),
            goal_after: ygo_goal::evaluate(
                &goal.expr,
                &forecast_facts(&t.after_resolution),
                &Default::default(),
            ),
            cost_change: resource_change(state, &t.after_cost),
            resolution_change: resource_change(state, &t.after_resolution),
        })
        .collect()
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialPrediction {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub checkpoint_id: Option<String>,
    pub step: usize,
    pub before_call: u64,
    pub at_prompt: u64,
    pub selected: Transition,
    pub goal_before: ygo_goal::Evaluation,
    pub goal_after: ygo_goal::Evaluation,
    pub public: FirstTurnPublicState,
    pub candidates: Vec<PartialCandidateComparison>,
    pub expected_following_rules: Vec<String>,
    pub differences: Vec<String>,
    pub after_prompt: Option<u64>,
}
fn immutable_prediction_checkpoint(plan: &str, prediction: &PartialPrediction) -> String {
    let mut original = prediction.clone();
    original.checkpoint_id = None;
    original.differences.clear();
    original.after_prompt = None;
    format!(
        "immutable/partial-prediction/{}",
        ygo_knowledge::hash(&serde_json::to_vec(&(plan, original)).unwrap())
    )
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PartialFailureKind {
    ResponseNotReached,
    ResponseIllegal,
    OriginalPlanBlocked,
    RequiredInstanceUnknown,
    CoverageGap,
    PredictionMismatch,
    PromptBindingFailed,
    BudgetExhausted,
    EngineFailure,
    BoundedRecoveryNotFound,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialFailure {
    pub kind: PartialFailureKind,
    pub step: usize,
    pub prompt: Option<u64>,
    pub detail: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialAnchor {
    pub step: usize,
    pub semantic_steps: usize,
    pub request: RunDuelRequest,
    pub result: DuelResult,
    pub queries: Vec<QueryWitness>,
    pub state: CausalState,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialExecution {
    pub schema_version: u16,
    pub scope: String,
    pub plan_id: String,
    pub request: RunDuelRequest,
    pub start_request: RunDuelRequest,
    pub start_call: usize,
    pub result: DuelResult,
    pub queries: Vec<QueryWitness>,
    pub predictions: Vec<PartialPrediction>,
    pub choices: Vec<PartialDecisionEvidence>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pending_choice: Option<PartialDecisionEvidence>,
    pub failure: Option<PartialFailure>,
    pub interruption: Option<PartialAnchor>,
    pub terminal: bool,
    pub goal: ygo_goal::Evaluation,
    pub audit_calls: Vec<u64>,
    pub calls: usize,
    pub identity_gaps: Vec<String>,
}
fn observed(
    result: &DuelResult,
    queries: &[QueryWitness],
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
) -> Result<ObservedState, String> {
    if result.prompt.as_ref().is_some_and(|p| p.opcode == 12) {
        actual_trigger_state(result, queries, cat, pack)
    } else {
        actual_state(result, queries, cat, pack)
    }
}
fn mapped<'a>(id: &str, map: &'a BTreeMap<String, String>) -> Result<&'a str, String> {
    map.get(id)
        .map(String::as_str)
        .ok_or_else(|| format!("unbound planned instance {id}"))
}
type SelectionKey = (String, String, u32, u8, Option<String>, Option<String>);
fn selection_keys(
    step: &Transition,
    map: Option<&BTreeMap<String, String>>,
) -> Option<Vec<SelectionKey>> {
    let mut keys = vec![];
    for s in &step.selections {
        let resolve = |id: &Option<String>| -> Option<Option<String>> {
            match (id, map) {
                (None, _) => Some(None),
                (Some(id), None) => Some(Some(id.clone())),
                (Some(id), Some(map)) => map.get(id).cloned().map(Some),
            }
        };
        keys.push((
            s.role.clone(),
            s.stage.clone(),
            s.card_id,
            s.from,
            resolve(&s.instance)?,
            resolve(&s.host)?,
        ));
    }
    keys.sort();
    Some(keys)
}
fn same_action(a: &Transition, b: &Transition, map: &BTreeMap<String, String>) -> bool {
    a.rule_id == b.rule_id
        && a.kind == b.kind
        && mapped(&a.source, map).is_ok_and(|id| id == b.source)
        && selection_keys(a, Some(map)).is_some_and(|keys| Some(keys) == selection_keys(b, None))
}
fn required_instances_unknown(
    step: &Transition,
    actual: &CausalState,
    map: &BTreeMap<String, String>,
) -> Vec<String> {
    let mut dependencies = vec![step.source.as_str()];
    for pick in &step.selections {
        dependencies.extend(pick.instance.as_deref());
        dependencies.extend(pick.host.as_deref());
    }
    let mut unknown = vec![];
    for id in dependencies {
        if map
            .get(id)
            .and_then(|id| lookup(actual, id))
            .is_some_and(|c| c.identity_known)
        {
            continue;
        }
        let predicted = lookup(&step.after_cost, id).or_else(|| lookup(&step.after_resolution, id));
        if predicted.is_some_and(|p| {
            actual.cards.iter().any(|a| {
                !a.identity_known
                    && a.card.code == p.card.code
                    && a.card.player == p.card.player
                    && a.card.location == p.card.location
            })
        }) {
            unknown.push(id.to_owned());
        }
    }
    unknown.sort();
    unknown.dedup();
    unknown
}
fn same_native(a: &DuelResult, b: &DuelResult) -> bool {
    let mut a = a.clone();
    let mut b = b.clone();
    a.peak_working_set_bytes = None;
    b.peak_working_set_bytes = None;
    serde_json::to_value(a).unwrap() == serde_json::to_value(b).unwrap()
}
fn same_json<T: Serialize>(a: &T, b: &T) -> bool {
    serde_json::to_value(a).unwrap() == serde_json::to_value(b).unwrap()
}
fn execution_request(report: &PartialExecution, e: &PartialDecisionEvidence) -> RunDuelRequest {
    let mut q = report.start_request.clone();
    q.decisions = report
        .result
        .resolved_decisions
        .iter()
        .filter(|d| d.prompt_id < e.prompt)
        .cloned()
        .collect();
    q.decisions.push(Decision {
        prompt_id: e.prompt,
        player: 0,
        choice: e.choice.clone(),
    });
    q
}
/// Check a local v1 report against charged native results, causal predictions,
/// actual query receipts, and pre-choice checkpoints. No rule certificate is
/// created. Imported reports additionally need fresh `replay_partial_execution`.
pub fn validate_partial_execution(
    report: &PartialExecution,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(), String> {
    journal.verify().map_err(|e| e.message)?;
    let mut expected_request = report.start_request.clone();
    expected_request.decisions = report.result.resolved_decisions.clone();
    if report.schema_version != 1
        || report.start_call > 512
        || report.calls > 512
        || report.plan_id != plan.id
        || !same_json(&expected_request, &report.request)
        || report.scope != "partial_integration_native_execution; not full rule certification"
        || report.calls != report.choices.len() + report.audit_calls.len()
        || report.audit_calls.len() != report.queries.len() + 1
        || report.start_call + report.calls > journal.stats().map_err(|e| e.message)?.limit
        || !(1..=512).contains(&journal.stats().map_err(|e| e.message)?.limit)
    {
        return Err("local execution version, identity, request, or budget differs".into());
    }
    let initial = journal
        .load_result(report.start_call as u64, &report.start_request)
        .map_err(|e| e.message)?
        .ok_or("initial charged result missing")?;
    let initial_queries: Vec<_> = report
        .queries
        .iter()
        .filter(|w| w.event <= initial.events.len() as u64)
        .cloned()
        .collect();
    if initial.protocol_version != report.start_request.protocol_version
        || initial.versions != report.start_request.versions
    {
        return Err("initial result runtime differs from its request".into());
    }
    let start = observed(&initial, &initial_queries, cat, pack)?;
    validate_forecast(plan, &start.state, cat, pack, goal)?;
    let mut results = vec![initial.clone()];
    for (i, evidence) in report.choices.iter().enumerate() {
        let before = results.last().unwrap();
        if evidence.before_call != (report.start_call + i + 1) as u64
            || journal
                .call_purpose(evidence.before_call)
                .map_err(|e| e.message)?
                != CallPurpose::Execution
        {
            return Err("choice call sequence or purpose differs".into());
        }
        validate_choice_checkpoint(evidence, &plan.id, before, journal)?;
        let after = journal
            .load_result(evidence.before_call, &execution_request(report, evidence))
            .map_err(|e| e.message)?
            .ok_or("choice result missing")?;
        if !after.events.starts_with(&before.events)
            || !after
                .resolved_decisions
                .starts_with(&before.resolved_decisions)
        {
            return Err("choice breaks actual raw/decision prefix".into());
        }
        results.push(after);
    }
    if !same_native(results.last().unwrap(), &report.result) {
        return Err("reported final prefix differs from charged execution".into());
    }
    if let Some(pending) = &report.pending_choice {
        validate_choice_checkpoint(pending, &plan.id, results.last().unwrap(), journal)?;
        let budget = journal
            .checkpoint_budget(&evidence_checkpoint(&plan.id, pending))
            .map_err(|e| e.message)?
            .ok_or("missing pre-call budget")?;
        if pending.before_call != (report.start_call + report.choices.len() + 1) as u64
            || budget
                .limit
                .saturating_sub(budget.consumed + budget.reserved)
                >= 2
            || journal
                .call_purpose(pending.before_call)
                .map_err(|e| e.message)?
                != CallPurpose::Witness
            || report.failure.as_ref().map(|f| f.kind) != Some(PartialFailureKind::BudgetExhausted)
        {
            return Err("unexecuted choice is not a proved budget truncation".into());
        }
    }
    validate_audits(report, journal)?;
    let map = validate_predictions(report, plan, cat, pack, goal, journal, &start, &results)?;
    if let Some(failure) = &report.failure {
        if failure.prompt != report.result.prompt.as_ref().map(|p| p.id) {
            return Err("failure does not reference its actual stopped prompt".into());
        }
        match failure.kind {
            PartialFailureKind::BudgetExhausted => {
                let pending = report.pending_choice.as_ref().ok_or("budget failure lacks its unexecuted intent")?;
                if failure.step != pending.step.unwrap_or(plan.steps.len())
                    || !failure.detail.starts_with("budget_exhausted:") {
                    return Err("budget failure classification differs".into());
                }
            }
            PartialFailureKind::RequiredInstanceUnknown => {
                let planned = plan.steps.get(failure.step).ok_or("unknown-instance step outside plan")?;
                let actual = observed(&report.result,&report.queries,cat,pack)?;
                let unknown = required_instances_unknown(planned,&actual.state,&map);
                if failure.step != report.predictions.len() || unknown.is_empty()
                    || failure.detail != format!("required_instance_unknown: {}",unknown.join(",")) {
                    return Err("required unknown instance dependency differs".into());
                }
            }
            PartialFailureKind::OriginalPlanBlocked => {
                let planned = plan.steps.get(failure.step).ok_or("blocked step outside plan")?;
                let actual = observed(&report.result, &report.queries, cat, pack)?;
                if failure.step != report.predictions.len()
                    || failure.detail != format!("original_plan_blocked: {} prerequisites unavailable", planned.rule_id)
                    || successors(&actual.state, cat, pack).transitions.iter().any(|t|same_action(planned,t,&map)) {
                    return Err("blocked classification or failed original step differs".into());
                }
            }
            PartialFailureKind::PredictionMismatch => {
                let p = report.predictions.last().ok_or("prediction mismatch has no prediction")?;
                if failure.step != p.step || p.differences.is_empty()
                    || failure.detail != format!("prediction_mismatch: {}: {}",p.selected.rule_id,p.differences.join("; ")) {
                    return Err("prediction failure classification differs".into());
                }
            }
            PartialFailureKind::BoundedRecoveryNotFound => {
                if failure.step != plan.steps.len() || report.predictions.len() != plan.steps.len()
                    || report.terminal && report.goal.result == ygo_goal::Truth::Yes {
                    return Err("bounded goal failure differs".into());
                }
            }
            _ => return Err("this partial local validator lacks a complete witness for the reported failure category".into()),
        }
    }
    Ok(())
}
fn validate_audits(report: &PartialExecution, journal: &CallJournal) -> Result<(), String> {
    if report.audit_calls.len() != report.queries.len() + 1 {
        return Err("complete query/root audit is missing".into());
    }
    for (i, call) in report.audit_calls.iter().enumerate() {
        if *call != (report.start_call + report.choices.len() + i + 1) as u64
            || journal.call_purpose(*call).map_err(|e| e.message)? != CallPurpose::Witness
        {
            return Err("independent witness cost sequence differs".into());
        }
        let mut q = report.request.clone();
        if let Some(witness) = report.queries.get(i) {
            q.decisions.retain(|d| d.prompt_id < witness.event);
            let r = journal
                .load_result(*call, &q)
                .map_err(|e| e.message)?
                .ok_or("query replay result missing")?;
            if r.protocol_version != q.protocol_version || r.versions != q.versions {
                return Err("query replay runtime differs from its request".into());
            }
            if !same_json(&QueryWitness::capture(&r)?, witness) {
                return Err("independent query content differs".into());
            }
        } else {
            let r = journal
                .load_result(*call, &q)
                .map_err(|e| e.message)?
                .ok_or("root replay missing")?;
            if r.protocol_version != q.protocol_version || r.versions != q.versions {
                return Err("root replay runtime differs from its request".into());
            }
            if !same_native(&r, &report.result) {
                return Err("independent complete replay differs".into());
            }
        }
    }
    Ok(())
}
#[allow(clippy::too_many_arguments)]
fn validate_predictions(
    report: &PartialExecution,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
    start: &ObservedState,
    results: &[DuelResult],
) -> Result<BTreeMap<String, String>, String> {
    let mut map: BTreeMap<_, _> = start
        .state
        .cards
        .iter()
        .map(|c| (c.id.clone(), c.id.clone()))
        .collect();
    let mut gaps = vec![];
    let mut expected_anchor = None;
    for (index, prediction) in report.predictions.iter().enumerate() {
        if prediction.step != index || index >= plan.steps.len() {
            return Err("prediction step order differs".into());
        }
        let i = report
            .choices
            .iter()
            .position(|e| e.step == Some(index))
            .or_else(|| {
                report
                    .pending_choice
                    .as_ref()
                    .filter(|p| p.step == Some(index))
                    .map(|_| report.choices.len())
            })
            .ok_or("prediction has no choice or proved unexecuted intent")?;
        let first_choice = report
            .choices
            .get(i)
            .or(report.pending_choice.as_ref())
            .ok_or("missing predicted choice")?;
        let before = results
            .get(i)
            .ok_or("prediction refers beyond the actual prefix")?;
        let queries: Vec<_> = report
            .queries
            .iter()
            .filter(|w| w.event <= before.events.len() as u64)
            .cloned()
            .collect();
        let observed = observed(before, &queries, cat, pack)?;
        let options = successors(&observed.state, cat, pack);
        if prediction.before_call != first_choice.before_call
            || prediction.at_prompt != first_choice.prompt
            || !same_json(&map, &first_choice.instance_map)
            || !same_action(&plan.steps[index], &prediction.selected, &map)
            || !options
                .transitions
                .iter()
                .any(|t| same_json(t, &prediction.selected))
            || !same_json(&prediction.public, &observed.public)
            || !same_json(
                &prediction.candidates,
                &comparisons(&observed.state, &options, goal),
            )
            || prediction.expected_following_rules
                != plan.steps[index + 1..]
                    .iter()
                    .map(|s| s.rule_id.clone())
                    .collect::<Vec<_>>()
            || !same_json(
                &prediction.goal_before,
                &ygo_goal::evaluate(
                    &goal.expr,
                    &forecast_facts(&observed.state),
                    &Default::default(),
                ),
            )
            || !same_json(
                &prediction.goal_after,
                &ygo_goal::evaluate(
                    &goal.expr,
                    &forecast_facts(&prediction.selected.after_resolution),
                    &Default::default(),
                ),
            )
        {
            return Err("prediction source, facts, selection, or goal differs".into());
        }
        let mut original = prediction.clone();
        original.differences.clear();
        original.after_prompt = None;
        let name = prediction
            .checkpoint_id
            .clone()
            .unwrap_or_else(|| format!("partial-{}-prediction-{index}", plan.id));
        if prediction.checkpoint_id.is_some()
            && name != immutable_prediction_checkpoint(&plan.id, prediction)
        {
            return Err("semantic prediction checkpoint identity differs".into());
        }
        if journal.checkpoint(&name).map_err(|e| e.message)?
            != Some(serde_json::to_value(&original).unwrap())
            || journal
                .checkpoint_consumed(&name)
                .map_err(|e| e.message)?
                .map(|n| n as u64 + 1)
                != Some(prediction.before_call)
        {
            return Err("semantic prediction was changed or saved after execution".into());
        }
        if let Some(prompt) = prediction.after_prompt {
            let after = results
                .iter()
                .find(|r| r.prompt.as_ref().is_some_and(|p| p.id == prompt))
                .ok_or("missing semantic completion")?;
            let after_queries: Vec<_> = report
                .queries
                .iter()
                .filter(|w| w.event <= after.events.len() as u64)
                .cloned()
                .collect();
            let actual = super::execution::observed(after, &after_queries, cat, pack)?;
            let mut differences =
                compare_resources(&prediction.selected.after_resolution, &actual.public)
                    .differences;
            if prediction.selected.after_resolution.normal_remaining
                != actual.state.normal_remaining
            {
                differences.push("normal summon opportunity differs".into());
            }
            if prediction.selected.after_resolution.used != actual.state.used {
                differences.push("actual use counts differ".into());
            }
            if differences != prediction.differences {
                return Err("predicted resource difference differs".into());
            }
            if expected_anchor.is_none()
                && after.events[before.events.len()..]
                    .iter()
                    .any(|e| matches!(e.opcode, 75 | 76))
            {
                let state = actual_state(after, &after_queries, cat, pack)?.state;
                let mut q = report.start_request.clone();
                q.decisions = after.resolved_decisions.clone();
                expected_anchor = Some(PartialAnchor {
                    step: index,
                    semantic_steps: index + 2,
                    request: q,
                    result: after.clone(),
                    queries: after_queries,
                    state,
                });
            }
            gaps.extend(update_map(
                &plan.steps[index].after_resolution,
                &actual.state,
                &mut map,
            ));
        } else if !prediction.differences.is_empty() {
            return Err("unfinished operation has fabricated differences".into());
        }
    }
    gaps.sort();
    gaps.dedup();
    if !same_json(&expected_anchor, &report.interruption) || gaps != report.identity_gaps {
        return Err("actual anchor or identity gaps differ".into());
    }
    let actual = actual_trace_v6(&report.result, cat, pack, &report.queries)?;
    let evaluation = ygo_goal::evaluate(&goal.expr, &actual.facts, &Default::default());
    if !same_json(&evaluation, &report.goal)
        || report.terminal != (actual.window == TraceWindow::OwnTurnEnded)
        || report.failure.is_none()
            && (!report.terminal
                || report.goal.result != ygo_goal::Truth::Yes
                || report.predictions.len() != plan.steps.len())
    {
        return Err("goal or terminal verification status differs".into());
    }
    Ok(map)
}
/// An imported local report never inherits a native qualification from JSON.
#[allow(clippy::too_many_arguments)]
pub fn replay_partial_execution(
    report: &PartialExecution,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    evidence: &CallJournal,
    audit: Arc<CallJournal>,
) -> Result<ygo_goal::AuditedQueries, String> {
    validate_partial_execution(report, plan, cat, pack, goal, evidence)?;
    verify_query_replays(&report.request, &report.result, &report.queries, audit)
}
fn update_map(
    predicted: &CausalState,
    actual: &CausalState,
    map: &mut BTreeMap<String, String>,
) -> Vec<String> {
    let mut gaps = vec![];
    // A mapping is a current correspondence, not a permanent alias. A hand
    // shuffle or an unobserved identity must invalidate it before dependency use.
    map.retain(|predicted_id, actual_id| {
        match (lookup(predicted, predicted_id), lookup(actual, actual_id)) {
            (Some(p), Some(a)) => {
                a.identity_known && p.card.code == a.card.code && p.card.player == a.card.player
            }
            _ => false,
        }
    });
    for host in [false, true] {
        for c in predicted
            .cards
            .iter()
            .filter(|c| c.host.is_some() == host && !map.contains_key(&c.id))
            .collect::<Vec<_>>()
        {
            if actual.cards.iter().any(|a| {
                !a.identity_known
                    && a.card.code == c.card.code
                    && a.card.player == c.card.player
                    && a.card.location == c.card.location
            }) {
                gaps.push(format!(
                    "unbound predicted instance {}; actual same-name identity remains unknown",
                    c.id
                ));
                continue;
            }
            let candidates = actual
                .cards
                .iter()
                .filter(|a| {
                    a.identity_known
                        && a.card.code == c.card.code
                        && a.card.player == c.card.player
                        && a.card.location == c.card.location
                        && !map.values().any(|id| id == &a.id)
                        && match (&c.host, &a.host) {
                            (None, None) => true,
                            (Some(x), Some(y)) => map.get(x) == Some(y),
                            _ => false,
                        }
                })
                .collect::<Vec<_>>();
            if candidates.len() != 1 {
                gaps.push(format!(
                    "unbound predicted instance {}; actual same-name identity remains unknown",
                    c.id
                ));
                continue;
            }
            map.insert(c.id.clone(), candidates[0].id.clone());
        }
    }
    gaps
}
fn chosen_pick(
    ms: &[ActionMetadata],
    step: &Transition,
    before: &CausalState,
    used: &BTreeSet<usize>,
) -> Result<(Choice, usize), String> {
    for (i, pick) in step
        .selections
        .iter()
        .enumerate()
        .filter(|(i, _)| !used.contains(i))
    {
        let instance = pick
            .instance
            .as_deref()
            .and_then(|id| lookup(before, id))
            .map(|c| &c.card);
        if let Ok(choice) = bind_pick(ms, pick, instance) {
            return Ok((choice, i));
        }
    }
    Err("prompt cannot bind to the remaining semantic roles".into())
}
fn follow_choice(
    result: &DuelResult,
    step: &Transition,
    before: &CausalState,
    used: &BTreeSet<usize>,
) -> Result<(Choice, Option<usize>), String> {
    let p = result.prompt.as_ref().ok_or("missing following prompt")?;
    let ms = prompt_metadata(
        p.id,
        &result
            .events
            .last()
            .ok_or("missing following raw frame")?
            .raw,
    )?;
    if matches!(p.opcode, 15 | 26) {
        if let Ok((c, i)) = chosen_pick(&ms, step, before, used) {
            return Ok((c, Some(i)));
        }
        if step
            .selections
            .iter()
            .enumerate()
            .filter(|(_, p)| p.role == "material")
            .all(|(i, _)| used.contains(&i))
            && p.actions.iter().any(|a| a.choice == Choice::Finish)
        {
            return Ok((Choice::Finish, None));
        }
        return Err("material/cost/target/resolution selection cannot be bound".into());
    }
    if p.opcode == 16
        && p.actions
            .iter()
            .any(|a| a.choice == Choice::Chain { index: None })
    {
        return Ok((Choice::Chain { index: None }, None));
    }
    let destinations = step
        .after_resolution
        .cards
        .iter()
        .filter(|a| {
            matches!(a.card.location, 4 | 8)
                && lookup(before, &a.id).map_or(true, |b| b.card.location != a.card.location)
        })
        .collect::<Vec<_>>();
    for action in &p.actions {
        let matched = match &action.choice {
            Choice::Place { zones } => {
                zones.len() == 1
                    && destinations.iter().any(|c| {
                        zones[0].player == c.card.player
                            && zones[0].location == c.card.location
                            && u32::from(zones[0].sequence) == c.card.sequence
                    })
            }
            Choice::Position { position } => {
                destinations.iter().any(|c| c.card.position == *position)
            }
            _ => false,
        };
        if matched {
            return Ok((action.choice.clone(), None));
        }
    }
    Err(format!("unsupported following prompt {}", p.opcode))
}
struct Runner<A: EngineAdapter> {
    adapter: JournaledAdapter<A>,
    journal: Arc<CallJournal>,
    held: Vec<String>,
    queries: Vec<QueryWitness>,
    base: usize,
    latest: Option<DuelResult>,
    faults: Vec<ExecutionFault>,
    stage: ExecutionStage,
    step: Option<usize>,
}
impl<A: EngineAdapter> Runner<A> {
    fn record_error(
        &mut self,
        error: WorkerError,
        stage: ExecutionStage,
        call: Option<u64>,
    ) -> String {
        let kind = worker_failure_kind(&error.code);
        let detail = format!("{}: {}", failure_label(kind), error.message);
        self.faults.push(ExecutionFault {
            kind,
            stage,
            call,
            step: self.step,
            code: error.code,
            detail: error.message,
        });
        detail
    }
    fn run(&mut self, q: &RunDuelRequest) -> Result<DuelResult, String> {
        let before_call = self.journal.stats().map_err(|e| e.message)?.consumed as u64;
        let token = format!(
            "partial-query-{}-{}",
            self.base,
            self.journal.stats().map_err(|e| e.message)?.consumed
        );
        if let Err(error) = self.journal.reserve(&token, 1) {
            return Err(self.record_error(error, self.stage, None));
        }
        self.held.push(token.clone());
        match self.adapter.run(q) {
            Ok(result) => {
                self.latest = Some(result.clone());
                if result.prompt.is_some() && result.error.is_none() {
                    match QueryWitness::capture(&result) {
                        Ok(witness) => self.queries.push(witness),
                        Err(detail) => {
                            self.faults.push(ExecutionFault {
                                kind: if result.status == DuelStatus::DecisionRequired {
                                    PartialFailureKind::EngineFailure
                                } else {
                                    PartialFailureKind::CoverageGap
                                },
                                stage: ExecutionStage::QueryCapture,
                                call: Some(
                                    self.journal.stats().map_err(|e| e.message)?.consumed as u64,
                                ),
                                step: self.step,
                                code: "query_capture".into(),
                                detail: detail.clone(),
                            });
                            return Err(detail);
                        }
                    }
                } else {
                    if let Some(error) = &result.error {
                        self.record_error(
                            error.clone(),
                            self.stage,
                            Some(self.journal.stats().map_err(|e| e.message)?.consumed as u64),
                        );
                    }
                    if let Err(error) = self.journal.release(&token) {
                        return Err(self.record_error(error, ExecutionStage::Cleanup, None));
                    }
                    self.held.retain(|t| t != &token);
                }
                Ok(result)
            }
            Err(error) => {
                let charged = self.journal.stats().map_err(|e| e.message)?.consumed as u64;
                let detail = self.record_error(
                    error,
                    self.stage,
                    (charged > before_call).then_some(charged),
                );
                if let Err(error) = self.journal.release(&token) {
                    self.record_error(error, ExecutionStage::Cleanup, None);
                } else {
                    self.held.retain(|t| t != &token);
                }
                Err(detail)
            }
        }
    }
    fn release(&mut self) -> Result<(), String> {
        for token in self.held.drain(..) {
            self.journal.release(&token).map_err(|e| e.message)?;
        }
        Ok(())
    }
}
/// Execute an independently generated forecast, preserving actual failed prefixes.
/// Caller obtained the initial result through this same journal. Every following
/// decision is bound to a legal raw prompt, with a prediction saved before run.
#[allow(clippy::too_many_arguments)]
pub fn execute_partial(
    request: &RunDuelRequest,
    initial: &DuelResult,
    queries: &[QueryWitness],
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<PartialExecution, String> {
    execute_partial_v2(request, initial, queries, plan, cat, pack, goal, journal)?.into_legacy()
}

/// Keep actual results and audit failures even when no recommendation qualifies.
#[allow(clippy::too_many_arguments)]
pub fn execute_partial_v2(
    request: &RunDuelRequest,
    initial: &DuelResult,
    queries: &[QueryWitness],
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<PartialExecutionV2, String> {
    execute_partial_v2_with_backend(
        request,
        initial,
        queries,
        plan,
        cat,
        pack,
        goal,
        journal,
        ProcessEngineAdapter::new(request.engine.clone()),
    )
}

/// Internal adapter seam for labelled fault tests. Independent query/root audits
/// always use ProcessEngineAdapter; a supplied backend cannot grant a receipt.
#[doc(hidden)]
#[allow(clippy::too_many_arguments)]
pub fn execute_partial_v2_with_backend<A: EngineAdapter>(
    request: &RunDuelRequest,
    initial: &DuelResult,
    queries: &[QueryWitness],
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<PartialExecutionV2, String> {
    request.validate_protocol()?;
    goal.validate()?;
    pack.validate()?;
    if request.protocol_version != 6
        || initial.protocol_version != request.protocol_version
        || request.versions != initial.versions
        || plan.goal_id != goal.id()
        || plan.steps.len() > 64
    {
        return Err("partial execution input/profile/goal mismatch".into());
    }
    let actual_start = observed(initial, queries, cat, pack)?;
    validate_forecast(plan, &actual_start.state, cat, pack, goal)?;
    let base = journal.stats().map_err(|e| e.message)?.consumed;
    if !(1..=512).contains(&journal.stats().map_err(|e| e.message)?.limit) {
        return Err("partial group budget must be 1..512".into());
    }
    let charged_start = journal
        .load_result(base as u64, request)
        .map_err(|e| e.message)?
        .ok_or("initial native call is not completed")?;
    if !same_native(&charged_start, initial) {
        return Err("initial result differs from charged call".into());
    }
    let held = format!("partial-witness-{base}");
    let reserve_error = journal.reserve(&held, queries.len() + 1).err();
    let mut runner = Runner {
        adapter: JournaledAdapter::new(backend, journal.clone(), CallPurpose::Execution),
        journal: journal.clone(),
        held: if reserve_error.is_none() {
            vec![held]
        } else {
            vec![]
        },
        queries: queries.to_vec(),
        base,
        latest: None,
        faults: vec![],
        stage: ExecutionStage::Execution,
        step: None,
    };
    let mut q = request.clone();
    let mut result = initial.clone();
    let mut predictions = vec![];
    let mut choices = vec![];
    let mut pending_choice = None;
    let mut map = BTreeMap::new();
    let mut failure = None;
    let mut interruption = None;
    let mut current_step = 0;
    let mut identity_gaps = vec![];
    let execution = (|| -> Result<(), StepFailure> {
        if let Some(error) = reserve_error {
            return Err(StepFailure::journal(error));
        }
        let start = observed(&result, &runner.queries, cat, pack).map_err(StepFailure::coverage)?;
        for c in &start.state.cards {
            map.insert(c.id.clone(), c.id.clone());
        }
        for (index, planned) in plan.steps.iter().enumerate() {
            current_step = index;
            runner.step = Some(index);
            let before =
                observed(&result, &runner.queries, cat, pack).map_err(StepFailure::coverage)?;
            let unknown = required_instances_unknown(planned, &before.state, &map);
            if !unknown.is_empty() {
                return Err(StepFailure::new(
                    PartialFailureKind::RequiredInstanceUnknown,
                    "required_instance",
                    format!("required_instance_unknown: {}", unknown.join(",")),
                ));
            }
            let options = successors(&before.state, cat, pack);
            let step = options
                .transitions
                .iter()
                .find(|t| same_action(planned, t, &map))
                .ok_or_else(|| {
                    StepFailure::new(
                        PartialFailureKind::OriginalPlanBlocked,
                        "prerequisites",
                        format!(
                            "original_plan_blocked: {} prerequisites unavailable",
                            planned.rule_id
                        ),
                    )
                })?
                .clone();
            let source = lookup(&before.state, &step.source).ok_or("source instance missing")?;
            if !source.identity_known {
                return Err(StepFailure::new(
                    PartialFailureKind::RequiredInstanceUnknown,
                    "source_identity",
                    "source identity unknown",
                ));
            }
            let trigger = before.state.pending.iter().any(|p| {
                p.rule_id == step.rule_id && p.source == step.source && p.eligibility == Truth::Yes
            });
            let rule = pack.rule(&step.rule_id).ok_or("missing rule")?;
            let mut choice = bind_start(&result, &source.card, rule, step.kind, trigger)?;
            let mut used = BTreeSet::new();
            let mut started = false;
            let mut entry = PartialPrediction {
                checkpoint_id: None,
                step: index,
                before_call: journal.stats().map_err(StepFailure::journal)?.consumed as u64 + 1,
                at_prompt: result.prompt.as_ref().ok_or("missing start prompt")?.id,
                goal_before: ygo_goal::evaluate(
                    &goal.expr,
                    &forecast_facts(&before.state),
                    &Default::default(),
                ),
                goal_after: ygo_goal::evaluate(
                    &goal.expr,
                    &forecast_facts(&step.after_resolution),
                    &Default::default(),
                ),
                public: before.public.clone(),
                candidates: comparisons(&before.state, &options, goal),
                expected_following_rules: plan.steps[index + 1..]
                    .iter()
                    .map(|s| s.rule_id.clone())
                    .collect(),
                selected: step.clone(),
                differences: vec![],
                after_prompt: None,
            };
            entry.checkpoint_id = Some(immutable_prediction_checkpoint(&plan.id, &entry));
            journal
                .save_checkpoint(
                    entry.checkpoint_id.as_ref().unwrap(),
                    &serde_json::to_value(&entry).unwrap(),
                )
                .map_err(StepFailure::journal)?;
            predictions.push(entry);
            let begin = result.events.len();
            for _ in 0..80 {
                let p = result
                    .prompt
                    .as_ref()
                    .ok_or("line ended inside a semantic operation")?
                    .clone();
                q.decisions = result.resolved_decisions.clone();
                choices.push(persist_choice(
                    &journal,
                    &plan.id,
                    &result,
                    Some(index),
                    choice.clone(),
                    &map,
                    &used,
                )?);
                q.decisions.push(Decision {
                    prompt_id: p.id,
                    player: p.player,
                    choice,
                });
                let old = result.events.clone();
                let next = runner.run(&q)?;
                if next.events.len() < old.len() || next.events[..old.len()] != old {
                    return Err(StepFailure::new(
                        PartialFailureKind::EngineFailure,
                        "raw_prefix",
                        "engine raw prefix changed",
                    ));
                }
                result = next;
                if let Some(error) = &result.error {
                    return Err(StepFailure::new(
                        PartialFailureKind::EngineFailure,
                        "worker_result",
                        format!("engine_failure: {}", error.message),
                    ));
                }
                for d in result
                    .resolved_decisions
                    .iter()
                    .filter(|d| d.prompt_id > p.id)
                {
                    let event = &result.events[d.prompt_id as usize - 1];
                    if let Ok(ms) = prompt_metadata(d.prompt_id, &event.raw) {
                        for (i, pick) in step
                            .selections
                            .iter()
                            .enumerate()
                            .filter(|(i, _)| !used.contains(i))
                            .collect::<Vec<_>>()
                        {
                            let instance = pick
                                .instance
                                .as_deref()
                                .and_then(|id| lookup(&before.state, id))
                                .map(|c| &c.card);
                            if bind_pick(&ms, pick, instance).ok() == Some(d.choice.clone()) {
                                used.insert(i);
                                break;
                            }
                        }
                    }
                }
                if result
                    .prompt
                    .as_ref()
                    .is_some_and(|p| matches!(p.opcode, 11 | 12))
                {
                    // Only a closed observed window may complete this operation. A foreign
                    // optional prompt or an unresolved chain stops the unsupported branch.
                    let after = observed(&result, &runner.queries, cat, pack)
                        .map_err(StepFailure::coverage)?;
                    let comparison = compare_resources(&step.after_resolution, &after.public);
                    let mut differences = comparison.differences;
                    if step.after_resolution.normal_remaining != after.state.normal_remaining {
                        differences.push("normal summon opportunity differs".into());
                    }
                    if step.after_resolution.used != after.state.used {
                        differences.push("actual use counts differ".into());
                    }
                    predictions.last_mut().unwrap().differences = differences.clone();
                    predictions.last_mut().unwrap().after_prompt =
                        result.prompt.as_ref().map(|p| p.id);
                    let negated = result.events[begin..]
                        .iter()
                        .any(|e| matches!(e.opcode, 75 | 76));
                    if negated && interruption.is_none() {
                        // Optional triggers are not anchors. This strict builder
                        // requires the actual settled own action window.
                        let anchor_state = actual_state(&result, &runner.queries, cat, pack)
                            .map_err(StepFailure::coverage)?;
                        let mut anchor_request = request.clone();
                        anchor_request.decisions = result.resolved_decisions.clone();
                        interruption = Some(PartialAnchor {
                            step: index,
                            semantic_steps: index + 2, // completed prefix plus the single Ash
                            request: anchor_request,
                            result: result.clone(),
                            queries: runner.queries.clone(),
                            state: anchor_state.state,
                        });
                    }
                    if (comparison.result != Truth::Yes || !differences.is_empty()) && !negated {
                        return Err(StepFailure::new(
                            PartialFailureKind::PredictionMismatch,
                            "resources",
                            format!(
                                "{}: {}: {}",
                                "prediction_mismatch",
                                step.rule_id,
                                differences.join("; ")
                            ),
                        ));
                    }
                    identity_gaps.extend(update_map(
                        &planned.after_resolution,
                        &after.state,
                        &mut map,
                    ));
                    started = true;
                    break;
                }
                let (following, selection) = follow_choice(&result, &step, &before.state, &used)?;
                choice = following;
                if let Some(i) = selection {
                    used.insert(i);
                }
            }
            if !started {
                return Err("prompt_binding_failed: semantic operation did not close".into());
            }
        }
        // Goal facts are accepted only after actual End Phase processing.
        current_step = plan.steps.len();
        runner.step = None;
        runner.stage = ExecutionStage::EndPhase;
        for _ in 0..80 {
            if result.status == DuelStatus::EngineVerified {
                return Ok(());
            }
            let p = result
                .prompt
                .as_ref()
                .ok_or("missing end processing prompt")?;
            let choice = if p.opcode == 11 {
                Choice::Command {
                    command: 7,
                    index: 0,
                }
            } else if p.opcode == 16 {
                Choice::Chain { index: None }
            } else {
                return Err(StepFailure::new(
                    PartialFailureKind::CoverageGap,
                    "end_processing",
                    "coverage_gap: unmodeled end phase processing",
                ));
            };
            if !p.actions.iter().any(|a| a.choice == choice) {
                return Err("end phase choice not legal".into());
            }
            q.decisions = result.resolved_decisions.clone();
            choices.push(persist_choice(
                &journal,
                &plan.id,
                &result,
                None,
                choice.clone(),
                &map,
                &BTreeSet::new(),
            )?);
            q.decisions.push(Decision {
                prompt_id: p.id,
                player: p.player,
                choice,
            });
            result = runner.run(&q)?;
            if result.error.is_some() {
                return Err(StepFailure::new(
                    PartialFailureKind::EngineFailure,
                    "worker_result",
                    "engine_failure during end processing",
                ));
            }
        }
        Err(StepFailure::new(
            PartialFailureKind::BudgetExhausted,
            "end_step_limit",
            "end processing step budget",
        ))
    })();
    if let Some(latest) = runner.latest.take() {
        result = latest;
    }
    if let Err(error) = execution {
        let kind = if let Some(fault) = runner.faults.first() {
            fault.kind
        } else {
            runner.faults.push(ExecutionFault {
                kind: error.kind,
                stage: error.stage.unwrap_or(runner.stage),
                call: None,
                step: Some(current_step),
                code: error.code.into(),
                detail: error.detail.clone(),
            });
            error.kind
        };
        failure = Some(PartialFailure {
            kind,
            step: current_step,
            prompt: result.prompt.as_ref().map(|p| p.id),
            detail: error.detail,
        });
        if kind == PartialFailureKind::BudgetExhausted
            && choices.last().is_some_and(|e| {
                e.before_call > journal.stats().map(|s| s.consumed as u64).unwrap_or(0)
            })
        {
            pending_choice = choices.pop();
        }
    }
    q.decisions = result.resolved_decisions.clone();
    if let Err(error) = runner.release() {
        runner.faults.push(ExecutionFault {
            kind: PartialFailureKind::EngineFailure,
            stage: ExecutionStage::Cleanup,
            call: None,
            step: None,
            code: "reservation_release".into(),
            detail: error,
        });
    }
    let (receipt, audit_failure, audit_calls) = match ygo_goal::verify_query_replays_recorded(
        &q,
        &result,
        &runner.queries,
        journal.clone(),
    ) {
        Ok(audit) => {
            let calls = audit.call_ids.clone();
            (Some(audit), None, calls)
        }
        Err(error) => {
            let calls = error.call_ids.clone();
            (None, Some(error), calls)
        }
    };
    let last_audited_prefix = if receipt.is_some() {
        audit_calls.last().map(|call| AuditedPrefix {
            request: q.clone(),
            result: result.clone(),
            witness_call: *call,
        })
    } else if let Some(error) = &audit_failure {
        if error.completed_witnesses > 0 {
            let index = error.completed_witnesses - 1;
            let mut prefix = q.clone();
            prefix
                .decisions
                .retain(|d| d.prompt_id < runner.queries[index].event);
            let call = error.call_ids[index];
            journal
                .load_result(call, &prefix)
                .ok()
                .flatten()
                .map(|result| AuditedPrefix {
                    request: prefix,
                    result,
                    witness_call: call,
                })
        } else {
            None
        }
    } else {
        None
    };
    let (terminal, evaluation) = match actual_trace_v6(&result, cat, pack, &runner.queries) {
        Ok(actual) => (
            Some(actual.window == TraceWindow::OwnTurnEnded),
            Some(ygo_goal::evaluate(
                &goal.expr,
                &actual.facts,
                &Default::default(),
            )),
        ),
        Err(error) => {
            runner.faults.push(ExecutionFault {
                kind: PartialFailureKind::CoverageGap,
                stage: ExecutionStage::Observation,
                call: None,
                step: Some(current_step),
                code: "actual_trace".into(),
                detail: error,
            });
            (None, None)
        }
    };
    if failure.is_none()
        && (terminal != Some(true)
            || evaluation
                .as_ref()
                .map_or(true, |e| e.result != ygo_goal::Truth::Yes))
    {
        failure = Some(PartialFailure {
            kind: PartialFailureKind::BoundedRecoveryNotFound,
            step: plan.steps.len(),
            prompt: result.prompt.as_ref().map(|p| p.id),
            detail: "bounded goal not met".into(),
        });
    }
    identity_gaps.sort();
    identity_gaps.dedup();
    let mut report = PartialExecutionV2 {
        schema_version: 2,
        scope: "partial_integration_native_execution; not full rule certification".into(),
        plan_id: plan.id.clone(),
        request: q,
        start_request: request.clone(),
        start_call: base,
        initial_attempt_checkpoint: None,
        last_result: Some(result),
        last_audited_prefix,
        queries: runner.queries,
        predictions,
        choices,
        pending_choice,
        failure,
        interruption,
        faults: runner.faults,
        observed_terminal: terminal,
        observed_goal: evaluation,
        audit_failure,
        receipt,
        receipt_content: None,
        audit_calls,
        calls: journal.stats().map_err(|e| e.message)?.consumed - base,
        identity_gaps,
    };
    report.seal();
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ygo_domain::{Card, CardId, CardKind};
    fn a3_test_root(label: &str) -> std::path::PathBuf {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/a3-resumable/tests")
            .join(format!(
                "{label}-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        std::fs::create_dir_all(&root).unwrap();
        root
    }
    #[test]
    fn prefix_query_versions_are_checked_even_when_public_fields_match() {
        struct Fixed(DuelResult);
        impl EngineAdapter for Fixed {
            fn doctor(&self) -> DoctorReport {
                panic!("no uncharged probe")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        let (mut q, result) = initial();
        q.versions = result.versions.clone();
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "query-version-{}.jsonl",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let j = CallJournal::open(path, "query-version-unit", "not-native-proof", 512).unwrap();
        let mut wrong_version = result.clone();
        wrong_version.versions.catalog = "forged-catalog".into();
        JournaledAdapter::new(Fixed(wrong_version), j.clone(), CallPurpose::Witness)
            .run(&q)
            .unwrap();
        JournaledAdapter::new(Fixed(result.clone()), j.clone(), CallPurpose::Witness)
            .run(&q)
            .unwrap();
        let report = PartialExecution {
            schema_version: 1,
            scope: "partial_integration_native_execution; not full rule certification".into(),
            plan_id: "unused-in-audit-only-test".into(),
            request: q.clone(),
            start_request: q,
            start_call: 0,
            queries: vec![QueryWitness::capture(&result).unwrap()],
            result,
            predictions: vec![],
            choices: vec![],
            pending_choice: None,
            failure: None,
            interruption: None,
            terminal: false,
            goal: ygo_goal::Evaluation {
                node: "/goal".into(),
                result: ygo_goal::Truth::Unknown,
                observed: None,
                matches: vec![],
                reason: "not a native qualification".into(),
                children: vec![],
            },
            audit_calls: vec![1, 2],
            calls: 2,
            identity_gaps: vec![],
        };
        assert!(validate_audits(&report, &j).is_err());
    }
    struct FailedWorker(&'static str);
    impl EngineAdapter for FailedWorker {
        fn doctor(&self) -> DoctorReport {
            panic!("no uncharged probe")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            Err(WorkerError::new(
                self.0,
                "test",
                "identity unknown in worker diagnostics",
            ))
        }
    }
    #[test]
    fn worker_failure_types_survive_misleading_text_and_keep_their_debit() {
        let (q, _) = initial();
        for code in ["worker_exit", "worker_timeout", "worker_output"] {
            for stage in [ExecutionStage::Execution, ExecutionStage::EndPhase] {
                let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                    .join("../../data/tmp")
                    .join(format!(
                        "typed-worker-{}.jsonl",
                        std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap()
                            .as_nanos()
                    ));
                let j = CallJournal::open(path, "fault-injection", "unit-not-native-proof", 512)
                    .unwrap();
                let mut runner = Runner {
                    adapter: JournaledAdapter::new(
                        FailedWorker(code),
                        j.clone(),
                        CallPurpose::Execution,
                    ),
                    journal: j.clone(),
                    held: vec![],
                    queries: vec![],
                    base: 0,
                    latest: None,
                    faults: vec![],
                    stage,
                    step: (stage == ExecutionStage::Execution).then_some(1),
                };
                assert!(runner.run(&q).is_err());
                assert_eq!(runner.faults.len(), 1);
                assert_eq!(runner.faults[0].kind, PartialFailureKind::EngineFailure);
                assert_eq!(runner.faults[0].code, code);
                assert_eq!(runner.faults[0].stage, stage);
                assert_eq!(runner.faults[0].call, Some(1));
                assert!(runner.latest.is_none());
                assert_eq!(j.stats().unwrap().consumed, 1);
                assert_eq!(j.stats().unwrap().reserved, 0);
                assert_eq!(
                    j.load_outcome(1, &q).unwrap().unwrap().unwrap_err().code,
                    code
                );
            }
        }
    }
    #[test]
    fn a_corrupt_query_keeps_the_new_result_without_minting_a_witness() {
        struct CorruptQuery(DuelResult);
        impl EngineAdapter for CorruptQuery {
            fn doctor(&self) -> DoctorReport {
                panic!("no uncharged probe")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        let (q, mut result) = initial();
        result.prompt.as_mut().unwrap().id += 1;
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "corrupt-query-{}.jsonl",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let j = CallJournal::open(path, "fault-injection", "unit-not-native-proof", 512).unwrap();
        let mut runner = Runner {
            adapter: JournaledAdapter::new(
                CorruptQuery(result.clone()),
                j.clone(),
                CallPurpose::Execution,
            ),
            journal: j.clone(),
            held: vec![],
            queries: vec![],
            base: 0,
            latest: None,
            faults: vec![],
            stage: ExecutionStage::Execution,
            step: Some(0),
        };
        assert!(runner.run(&q).is_err());
        assert!(same_native(runner.latest.as_ref().unwrap(), &result));
        assert!(runner.queries.is_empty());
        assert_eq!(runner.faults[0].kind, PartialFailureKind::EngineFailure);
        assert_eq!(runner.faults[0].stage, ExecutionStage::QueryCapture);
        assert_eq!(runner.faults[0].call, Some(1));
        runner.release().unwrap();
        assert_eq!(j.stats().unwrap().consumed, 1);
        assert_eq!(j.stats().unwrap().reserved, 0);
    }
    fn initial() -> (RunDuelRequest, DuelResult) {
        let mut v: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.trace-resource.json"
        ))
        .unwrap();
        v["result"]["events"] = serde_json::json!([]);
        let mut r: DuelResult = serde_json::from_value(v["result"].clone()).unwrap();
        let w: Vec<QueryWitness> = serde_json::from_value(v["witnesses"].clone()).unwrap();
        r.events = v["frames"]
            .as_array()
            .unwrap()
            .iter()
            .take(w[0].event as usize)
            .enumerate()
            .map(|(i, raw)| {
                decode_frame(
                    i as u64 + 1,
                    &serde_json::from_value::<Vec<u8>>(raw.clone()).unwrap(),
                )
                .unwrap()
            })
            .collect();
        r.prompt = parse_prompt(w[0].event, &r.events.last().unwrap().raw).unwrap();
        r.checkpoint = w[0].public.visible.clone();
        r.resolved_decisions.clear();
        let value: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
        ))
        .unwrap();
        let mut q: RunDuelRequest =
            serde_json::from_value(value["cases"][0]["runtime_request"].clone()).unwrap();
        q.decisions.clear();
        (q, r)
    }
    fn fixture_catalog(result: &DuelResult) -> Catalog {
        result
            .checkpoint
            .cards
            .iter()
            .map(|state_card| {
                let id = CardId(state_card.code);
                let kind = match state_card.type_flags & 7 {
                    2 => CardKind::Spell,
                    4 => CardKind::Trap,
                    _ => CardKind::Monster,
                };
                (
                    id,
                    Card {
                        id,
                        name: format!("synthetic-{}", id.0),
                        kind,
                        type_flags: state_card.type_flags,
                        level: state_card.level.unwrap_or(0),
                        attribute: state_card.attribute.unwrap_or(0),
                        race: state_card.race.unwrap_or(0),
                        attack: state_card.attack,
                        defense: state_card.defense,
                        ..Default::default()
                    },
                )
            })
            .collect()
    }
    fn resource_trace_prefixes() -> Vec<DuelResult> {
        let mut fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../tests/fixtures/tournament-2026.trace-resource.json"
        ))
        .unwrap();
        fixture["result"]["events"] = serde_json::json!([]);
        let base: DuelResult = serde_json::from_value(fixture["result"].clone()).unwrap();
        let witnesses: Vec<QueryWitness> =
            serde_json::from_value(fixture["witnesses"].clone()).unwrap();
        let frames = fixture["frames"].as_array().unwrap();
        witnesses
            .iter()
            .map(|witness| {
                let mut result = base.clone();
                result.events = frames
                    .iter()
                    .take(witness.event as usize)
                    .enumerate()
                    .map(|(index, raw)| {
                        decode_frame(
                            index as u64 + 1,
                            &serde_json::from_value::<Vec<u8>>(raw.clone()).unwrap(),
                        )
                        .unwrap()
                    })
                    .collect();
                result.prompt =
                    parse_prompt(witness.event, &result.events.last().unwrap().raw).unwrap();
                result.checkpoint = witness.public.visible.clone();
                result.status = DuelStatus::DecisionRequired;
                result.error = None;
                result.resolved_decisions.clear();
                result
            })
            .collect()
    }
    #[test]
    fn resumable_loop_reopens_with_valid_nonempty_semantic_plan() {
        let (request, mut initial_result) = initial();
        initial_result.versions = request.versions.clone();
        let catalog = fixture_catalog(&initial_result);
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let witness = QueryWitness::capture(&initial_result).unwrap();
        let start = actual_state(&initial_result, &[witness], &catalog, &pack)
            .unwrap()
            .state;
        let goal: Goal = serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op":"count", "filter":{"codes":[78449284],"locations":[4]}, "min":1}
        }))
        .unwrap();
        let limits = SearchLimits {
            candidates: 1,
            expansions: 150,
            frontier: 8,
            steps: 4,
        };
        let plans = propose_partial(&start, &catalog, &pack, &goal, &limits).unwrap();
        let plan = plans
            .plans
            .into_iter()
            .find(|plan| plan.steps.len() >= 2)
            .expect("fixture goal should produce a valid multistep forecast");
        validate_forecast(&plan, &start, &catalog, &pack, &goal).unwrap();

        struct Initial(DuelResult);
        impl EngineAdapter for Initial {
            fn doctor(&self) -> DoctorReport {
                panic!("initial result is already supplied")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        let root = a3_test_root("resumable-loop-nonempty-reopen");
        let path = root.join("calls.jsonl");
        let journal = CallJournal::open(&path, "resumable-loop", "synthetic-context", 8).unwrap();
        JournaledAdapter::new(
            Initial(initial_result.clone()),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();
        let checkpoint = begin_resumable_partial_execution_v1(
            &request,
            1,
            &[],
            &plan,
            &catalog,
            &pack,
            &goal,
            journal.clone(),
        )
        .unwrap();
        assert_eq!(checkpoint.phase, ResumableExecutionPhaseV1::Semantic);
        assert_eq!(checkpoint.semantic_step, 0);
        assert_eq!(plan.steps.len(), 3);
        assert_eq!(checkpoint.instance_mapping.len(), start.cards.len());
        assert_eq!(checkpoint.inner.progress.queries.len(), 1);
        assert_eq!(journal.stats().unwrap().consumed, 1);
        drop(journal);
        drop(checkpoint);

        let resumed = resume_resumable_partial_execution_v1(
            &path,
            "resumable-loop",
            "synthetic-context",
            8,
            &request,
            &plan,
            &catalog,
            &pack,
            &goal,
        )
        .unwrap();
        assert_eq!(resumed.phase, ResumableExecutionPhaseV1::Semantic);
        assert_eq!(resumed.semantic_step, 0);
        assert_eq!(resumed.predictions.len(), 0);
        assert_eq!(resumed.choices.len(), 0);
        assert_eq!(resumed.instance_mapping.len(), start.cards.len());
        assert_eq!(resumed.inner.progress.queries.len(), 1);
        assert_eq!(resumed.inner.progress.ledger.consumed, 1);
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn unsupported_trigger_boundary_blocks_without_charging_after_reopen() {
        use std::collections::VecDeque;

        struct Initial(DuelResult);
        impl EngineAdapter for Initial {
            fn doctor(&self) -> DoctorReport {
                panic!("initial result is already supplied")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        #[derive(Clone)]
        struct Prefixes(std::sync::Arc<std::sync::Mutex<VecDeque<DuelResult>>>);
        impl EngineAdapter for Prefixes {
            fn doctor(&self) -> DoctorReport {
                panic!("synthetic trace adapter must not call doctor")
            }
            fn run(&self, request: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                let mut result =
                    self.0.lock().unwrap().pop_front().ok_or_else(|| {
                        WorkerError::new("fixture_exhausted", "test", "no prefix")
                    })?;
                result.resolved_decisions = request.decisions.clone();
                Ok(result)
            }
        }

        fn run_case(paused: bool) -> serde_json::Value {
            let (request, _) = initial();
            let mut prefixes = resource_trace_prefixes();
            for result in &mut prefixes {
                result.versions = request.versions.clone();
            }
            let initial_result = prefixes[0].clone();
            let catalog = fixture_catalog(&initial_result);
            let pack = FirstTurnKnowledge::builtin().unwrap();
            let witness = QueryWitness::capture(&initial_result).unwrap();
            let start = actual_state(&initial_result, &[witness], &catalog, &pack)
                .unwrap()
                .state;
            let goal: Goal = serde_json::from_value(serde_json::json!({
                "version": 1,
                "expr": {"op":"count", "filter":{"codes":[78449284],"locations":[4]}, "min":1}
            }))
            .unwrap();
            let limits = SearchLimits {
                candidates: 1,
                expansions: 150,
                frontier: 8,
                steps: 4,
            };
            let plans = propose_partial(&start, &catalog, &pack, &goal, &limits).unwrap();
            let plan = plans
                .plans
                .into_iter()
                .find(|plan| plan.steps.len() >= 2)
                .expect("fixture goal should produce a multistep forecast");
            validate_forecast(&plan, &start, &catalog, &pack, &goal).unwrap();

            let root = a3_test_root(if paused {
                "resumable-loop-semantic-paused"
            } else {
                "resumable-loop-semantic-continuous"
            });
            let path = root.join("calls.jsonl");
            let mut journal =
                CallJournal::open(&path, "resumable-loop", "synthetic-context", 8).unwrap();
            JournaledAdapter::new(
                Initial(initial_result.clone()),
                journal.clone(),
                CallPurpose::Execution,
            )
            .run(&request)
            .unwrap();
            let mut state = begin_resumable_partial_execution_v1(
                &request,
                1,
                &[],
                &plan,
                &catalog,
                &pack,
                &goal,
                journal.clone(),
            )
            .unwrap();
            let backend = Prefixes(std::sync::Arc::new(std::sync::Mutex::new(
                prefixes.into_iter().skip(1).collect::<VecDeque<_>>(),
            )));
            advance_resumable_partial_execution_v1_with_backend(
                &mut state,
                &plan,
                &catalog,
                &pack,
                &goal,
                journal.clone(),
                backend.clone(),
            )
            .unwrap();
            assert_eq!(state.semantic_step, 1);
            assert_eq!(
                state
                    .inner
                    .progress
                    .current_prefix
                    .prompt
                    .as_ref()
                    .unwrap()
                    .opcode,
                12
            );
            if paused {
                drop(journal);
                drop(state);
                state = resume_resumable_partial_execution_v1(
                    &path,
                    "resumable-loop",
                    "synthetic-context",
                    8,
                    &request,
                    &plan,
                    &catalog,
                    &pack,
                    &goal,
                )
                .unwrap();
                journal = CallJournal::open_existing_strict(
                    &path,
                    "resumable-loop",
                    "synthetic-context",
                    8,
                )
                .unwrap()
                .unwrap();
            }
            let before_block = serde_json::to_value(&state).unwrap();
            let consumed_before_block = journal.stats().unwrap().consumed;
            let pending_responses = backend.0.lock().unwrap().len();
            let error = advance_resumable_partial_execution_v1_with_backend(
                &mut state,
                &plan,
                &catalog,
                &pack,
                &goal,
                journal.clone(),
                backend.clone(),
            )
            .unwrap_err();
            assert!(error.contains("original_plan_blocked"), "{error}");
            assert_eq!(serde_json::to_value(&state).unwrap(), before_block);
            assert_eq!(journal.stats().unwrap().consumed, consumed_before_block);
            assert_eq!(backend.0.lock().unwrap().len(), pending_responses);
            let summary = serde_json::json!({
                "phase": state.phase,
                "semantic_step": state.semantic_step,
                "choices": state.choices,
                "predictions": state.predictions,
                "instance_mapping": state.instance_mapping,
                "queries": state.inner.progress.queries,
                "prefix": state.inner.progress.current_prefix,
                "ledger": journal.stats().unwrap(),
                "reservations": journal.reservation_state().unwrap(),
                "pending_responses": backend.0.lock().unwrap().len(),
            });
            drop(journal);
            drop(state);
            let _ = std::fs::remove_dir_all(root);
            summary
        }

        assert_eq!(run_case(false), run_case(true));
    }
    #[test]
    fn resumable_loop_refuses_to_retry_after_crash_with_unknown_consumption() {
        use std::sync::{
            atomic::{AtomicUsize, Ordering},
            Arc,
        };

        struct Initial(DuelResult);
        impl EngineAdapter for Initial {
            fn doctor(&self) -> DoctorReport {
                panic!("initial result is already supplied")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        struct Crash(Arc<AtomicUsize>);
        impl EngineAdapter for Crash {
            fn doctor(&self) -> DoctorReport {
                panic!("synthetic crash adapter must not call doctor")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                self.0.fetch_add(1, Ordering::SeqCst);
                panic!("simulated process loss after the call debit")
            }
        }

        let (request, mut initial_result) = initial();
        initial_result.versions = request.versions.clone();
        let catalog = fixture_catalog(&initial_result);
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let witness = QueryWitness::capture(&initial_result).unwrap();
        let start = actual_state(&initial_result, &[witness], &catalog, &pack)
            .unwrap()
            .state;
        let goal: Goal = serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op":"count", "filter":{"codes":[78449284],"locations":[4]}, "min":1}
        }))
        .unwrap();
        let limits = SearchLimits {
            candidates: 1,
            expansions: 150,
            frontier: 8,
            steps: 4,
        };
        let plans = propose_partial(&start, &catalog, &pack, &goal, &limits).unwrap();
        let plan = plans
            .plans
            .into_iter()
            .find(|plan| plan.steps.len() >= 2)
            .expect("fixture goal should produce a valid multistep forecast");
        validate_forecast(&plan, &start, &catalog, &pack, &goal).unwrap();

        let root = a3_test_root("resumable-loop-unknown-consumption");
        let path = root.join("calls.jsonl");
        let journal = CallJournal::open(&path, "resumable-loop", "synthetic-context", 8).unwrap();
        JournaledAdapter::new(
            Initial(initial_result.clone()),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();
        let mut state = begin_resumable_partial_execution_v1(
            &request,
            1,
            &[],
            &plan,
            &catalog,
            &pack,
            &goal,
            journal.clone(),
        )
        .unwrap();

        let adapter_calls = Arc::new(AtomicUsize::new(0));
        let crashed = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let _ = advance_resumable_partial_execution_v1_with_backend(
                &mut state,
                &plan,
                &catalog,
                &pack,
                &goal,
                journal.clone(),
                Crash(adapter_calls.clone()),
            );
        }));
        assert!(crashed.is_err());
        assert_eq!(adapter_calls.load(Ordering::SeqCst), 1);
        assert_eq!(journal.stats().unwrap().unknown, 1);
        drop(journal);
        drop(state);

        let error = resume_resumable_partial_execution_v1(
            &path,
            "resumable-loop",
            "synthetic-context",
            8,
            &request,
            &plan,
            &catalog,
            &pack,
            &goal,
        )
        .unwrap_err();
        assert!(error.contains("unknown consumption"), "{error}");
        assert_eq!(adapter_calls.load(Ordering::SeqCst), 1);
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn resumable_first_turn_loop_persists_end_phase_and_query_audit_progress() {
        let (mut request, mut initial_result) = initial();
        let initial_queries = Vec::<QueryWitness>::new();
        initial_result.versions = request.versions.clone();
        let mut raw = vec![11, 0];
        raw.extend([0; 24]);
        raw.extend([0, 1, 0]);
        let sequence = initial_result.events.last().unwrap().sequence + 1;
        let frame = decode_frame(sequence, &raw).unwrap();
        initial_result.events.push(frame.clone());
        initial_result.prompt = parse_prompt(sequence, &raw).unwrap();
        initial_result.status = DuelStatus::DecisionRequired;
        initial_result.error = None;
        initial_result.resolved_decisions.clear();
        request.decisions.clear();
        let catalog: Catalog = initial_result
            .checkpoint
            .cards
            .iter()
            .map(|state_card| {
                let id = CardId(state_card.code);
                let kind = match state_card.type_flags & 7 {
                    2 => CardKind::Spell,
                    4 => CardKind::Trap,
                    _ => CardKind::Monster,
                };
                (
                    id,
                    Card {
                        id,
                        name: format!("synthetic-{}", id.0),
                        kind,
                        type_flags: state_card.type_flags,
                        level: state_card.level.unwrap_or(0),
                        attribute: state_card.attribute.unwrap_or(0),
                        race: state_card.race.unwrap_or(0),
                        attack: state_card.attack,
                        defense: state_card.defense,
                        ..Default::default()
                    },
                )
            })
            .collect();

        let pack = FirstTurnKnowledge::builtin().unwrap();
        let goal: ygo_goal::Goal = serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op": "count", "filter": {}, "min": 1}
        }))
        .unwrap();
        let start_witness = QueryWitness::capture(&initial_result).unwrap();
        let start_state = actual_state(&initial_result, &[start_witness], &catalog, &pack)
            .unwrap()
            .state;
        let plan = empty_forecast_plan(
            &start_state,
            &catalog,
            &pack,
            &goal,
            &SearchLimits::default(),
        )
        .unwrap();
        let root = a3_test_root("resumable-loop-end-phase");
        let path = root.join("calls.jsonl");
        let journal = CallJournal::open(&path, "resumable-loop", "synthetic-context", 8).unwrap();
        struct Fixed(DuelResult);
        impl EngineAdapter for Fixed {
            fn doctor(&self) -> DoctorReport {
                panic!("resumable execution must not call doctor")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        JournaledAdapter::new(
            Fixed(initial_result.clone()),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();
        let mut checkpoint = begin_resumable_partial_execution_v1(
            &request,
            1,
            &initial_queries,
            &plan,
            &catalog,
            &pack,
            &goal,
            journal.clone(),
        )
        .unwrap();
        let mut tampered = checkpoint.clone();
        tampered.semantic_step += 1;
        assert!(advance_resumable_partial_execution_v1_with_backend(
            &mut tampered,
            &plan,
            &catalog,
            &pack,
            &goal,
            journal.clone(),
            Fixed(initial_result.clone())
        )
        .is_err());
        assert_eq!(journal.stats().unwrap().consumed, 1);
        let mut terminal = initial_result.clone();
        terminal.status = DuelStatus::EngineVerified;
        terminal.prompt = None;
        let mut calls = request.decisions.clone();
        calls.push(Decision {
            prompt_id: sequence,
            player: 0,
            choice: Choice::Command {
                command: 7,
                index: 0,
            },
        });
        terminal.resolved_decisions = calls;
        advance_resumable_partial_execution_v1_with_backend(
            &mut checkpoint,
            &plan,
            &catalog,
            &pack,
            &goal,
            journal.clone(),
            Fixed(terminal.clone()),
        )
        .unwrap();
        assert_eq!(checkpoint.phase, ResumableExecutionPhaseV1::QueryAudit);
        assert_eq!(journal.stats().unwrap().consumed, 2);

        advance_resumable_query_audit_v1_with_backend(
            &mut checkpoint,
            journal.clone(),
            Fixed(initial_result.clone()),
        )
        .unwrap();
        assert_eq!(checkpoint.audit.next_query, 1);
        assert_eq!(journal.stats().unwrap().consumed, 3);
        drop(journal);
        drop(checkpoint);

        let mut checkpoint = resume_resumable_partial_execution_v1(
            &path,
            "resumable-loop",
            "synthetic-context",
            8,
            &request,
            &plan,
            &catalog,
            &pack,
            &goal,
        )
        .unwrap();
        let journal =
            CallJournal::open_existing_strict(&path, "resumable-loop", "synthetic-context", 8)
                .unwrap()
                .unwrap();
        advance_resumable_query_audit_v1_with_backend(
            &mut checkpoint,
            journal.clone(),
            Fixed(terminal),
        )
        .unwrap();
        assert_eq!(checkpoint.audit.status, ResumableAuditStatusV1::Complete);
        assert_eq!(checkpoint.audit.call_ids.len(), 2);
        assert_eq!(journal.stats().unwrap().consumed, 4);
        assert_eq!(journal.stats().unwrap().reserved, 0);
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn resumable_checkpoint_binds_plan_and_request_before_any_continuation() {
        struct Fixed(DuelResult);
        impl EngineAdapter for Fixed {
            fn doctor(&self) -> DoctorReport {
                panic!("initial result is already charged")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                Ok(self.0.clone())
            }
        }
        let (request, mut initial) = initial();
        initial.versions = request.versions.clone();
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let goal: ygo_goal::Goal = serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op": "count", "filter": {}, "min": 1}
        }))
        .unwrap();
        let plan = ForecastPlan {
            id: "resume-plan".into(),
            start_id: "resume-start".into(),
            knowledge_id: pack.id(),
            limits: SearchLimits::default(),
            goal_id: goal.id(),
            first_sensitive: None,
            steps: vec![],
            predicted_goal: ygo_goal::Evaluation {
                node: "/goal".into(),
                result: ygo_goal::Truth::Unknown,
                observed: None,
                matches: vec![],
                reason: "synthetic forecast only".into(),
                children: vec![],
            },
            predicted_resources: 0,
        };
        let root = a3_test_root("bindings");
        let path = root.join("calls.jsonl");
        let journal = CallJournal::open(&path, "a3-synthetic", "a3-test-context", 1).unwrap();
        JournaledAdapter::new(
            Fixed(initial.clone()),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();

        let mut checkpoint = begin_execution_v1(
            &request,
            1,
            &plan,
            &Default::default(),
            &pack,
            &goal,
            journal.clone(),
        )
        .unwrap();
        assert_eq!(checkpoint.schema_version, 1);
        assert_eq!(checkpoint.progress.status, ExecutionRecoveryStatus::Ready);
        assert_eq!(checkpoint.progress.completed_call_ids, vec![1]);
        checkpoint
            .validate_bindings(&request, &plan, &Default::default(), &pack, &goal)
            .unwrap();

        let mut changed_plan = plan.clone();
        changed_plan.id.push_str("-changed");
        assert!(checkpoint
            .validate_bindings(&request, &changed_plan, &Default::default(), &pack, &goal)
            .is_err());
        let mut changed_request = request.clone();
        changed_request.seed = changed_request.seed.wrapping_add(1);
        assert!(checkpoint
            .validate_bindings(&changed_request, &plan, &Default::default(), &pack, &goal)
            .is_err());
        let prompt = checkpoint.progress.current_prefix.prompt.as_ref().unwrap();
        let decision = Decision {
            prompt_id: prompt.id,
            player: prompt.player,
            choice: prompt.actions[0].choice.clone(),
        };
        let mut next_request = request.clone();
        next_request.decisions.push(decision.clone());
        let intent = ExecutionIntentV1::from_prompt(
            &checkpoint,
            next_request,
            ExecutionStage::Execution,
            Some(0),
            decision,
        )
        .unwrap();
        let adapter_calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let unused_result = checkpoint.progress.current_prefix.clone();
        advance_execution_v1_with_backend(&mut checkpoint, intent, journal.clone(), {
            struct Count(DuelResult, Arc<std::sync::atomic::AtomicUsize>);
            impl EngineAdapter for Count {
                fn doctor(&self) -> DoctorReport {
                    panic!("budget rejection must not call doctor")
                }
                fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                    self.1.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                    Ok(self.0.clone())
                }
            }
            Count(unused_result, adapter_calls.clone())
        })
        .unwrap();
        assert_eq!(checkpoint.progress.status, ExecutionRecoveryStatus::Paused);
        assert_eq!(journal.stats().unwrap().consumed, 1);
        assert_eq!(adapter_calls.load(std::sync::atomic::Ordering::SeqCst), 0);
        drop(journal);
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn completed_trailing_call_is_reused_after_reopen_without_a_second_charge() {
        use std::sync::atomic::{AtomicUsize, Ordering};
        struct Fixed(DuelResult, Arc<AtomicUsize>);
        impl EngineAdapter for Fixed {
            fn doctor(&self) -> DoctorReport {
                panic!("resume never calls doctor")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                self.1.fetch_add(1, Ordering::SeqCst);
                Ok(self.0.clone())
            }
        }
        let (request, mut initial) = initial();
        initial.versions = request.versions.clone();
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let goal: ygo_goal::Goal = serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op": "count", "filter": {}, "min": 1}
        }))
        .unwrap();
        let plan = ForecastPlan {
            id: "resume-replay-plan".into(),
            start_id: "resume-replay-start".into(),
            knowledge_id: pack.id(),
            limits: SearchLimits::default(),
            goal_id: goal.id(),
            first_sensitive: None,
            steps: vec![],
            predicted_goal: ygo_goal::Evaluation {
                node: "/goal".into(),
                result: ygo_goal::Truth::Unknown,
                observed: None,
                matches: vec![],
                reason: "synthetic forecast only".into(),
                children: vec![],
            },
            predicted_resources: 0,
        };
        let root = a3_test_root("trailing-result-recovery");
        let path = root.join("calls.jsonl");
        let journal = CallJournal::open(&path, "a3-replay", "a3-replay-context", 8).unwrap();
        JournaledAdapter::new(
            Fixed(initial.clone(), Arc::new(AtomicUsize::new(0))),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();
        let mut checkpoint = begin_execution_v1(
            &request,
            1,
            &plan,
            &Default::default(),
            &pack,
            &goal,
            journal.clone(),
        )
        .unwrap();
        let prompt = checkpoint.progress.current_prefix.prompt.as_ref().unwrap();
        let decision = Decision {
            prompt_id: prompt.id,
            player: prompt.player,
            choice: prompt.actions[0].choice.clone(),
        };
        let mut next_request = request.clone();
        next_request.decisions.push(decision.clone());
        let intent = ExecutionIntentV1::from_prompt(
            &checkpoint,
            next_request.clone(),
            ExecutionStage::Execution,
            Some(0),
            decision,
        )
        .unwrap();
        let intent_name = format!("immutable/execution-intent/{}/2", checkpoint.execution_id);
        journal
            .save_checkpoint(&intent_name, &serde_json::to_value(&intent).unwrap())
            .unwrap();
        checkpoint.progress.status = ExecutionRecoveryStatus::IntentPersisted;
        checkpoint.progress.pending_action = Some(intent.choice.clone());
        checkpoint.progress.pending_intent = Some(intent.clone());
        journal
            .save_checkpoint(
                &format!("execution-v1/{}", checkpoint.execution_id),
                &serde_json::to_value(&checkpoint).unwrap(),
            )
            .unwrap();

        let unresolved_path = root.join("unresolved.jsonl");
        let unresolved = CallJournal::open(
            &unresolved_path,
            "a3-unresolved",
            "a3-unresolved-context",
            8,
        )
        .unwrap();
        JournaledAdapter::new(
            Fixed(initial.clone(), Arc::new(AtomicUsize::new(0))),
            unresolved.clone(),
            CallPurpose::Execution,
        )
        .run(&request)
        .unwrap();
        let mut unresolved_checkpoint = begin_execution_v1(
            &request,
            1,
            &plan,
            &Default::default(),
            &pack,
            &goal,
            unresolved.clone(),
        )
        .unwrap();
        let unresolved_prompt = unresolved_checkpoint
            .progress
            .current_prefix
            .prompt
            .as_ref()
            .unwrap();
        let unresolved_decision = Decision {
            prompt_id: unresolved_prompt.id,
            player: unresolved_prompt.player,
            choice: unresolved_prompt.actions[0].choice.clone(),
        };
        let mut unresolved_request = request.clone();
        unresolved_request
            .decisions
            .push(unresolved_decision.clone());
        let unresolved_intent = ExecutionIntentV1::from_prompt(
            &unresolved_checkpoint,
            unresolved_request.clone(),
            ExecutionStage::Execution,
            Some(0),
            unresolved_decision,
        )
        .unwrap();
        unresolved
            .save_checkpoint(
                &format!(
                    "immutable/execution-intent/{}/2",
                    unresolved_checkpoint.execution_id
                ),
                &serde_json::to_value(&unresolved_intent).unwrap(),
            )
            .unwrap();
        unresolved_checkpoint.progress.status = ExecutionRecoveryStatus::IntentPersisted;
        unresolved_checkpoint.progress.pending_action = Some(unresolved_intent.choice.clone());
        unresolved_checkpoint.progress.pending_intent = Some(unresolved_intent);
        unresolved
            .save_checkpoint(
                &format!("execution-v1/{}", unresolved_checkpoint.execution_id),
                &serde_json::to_value(&unresolved_checkpoint).unwrap(),
            )
            .unwrap();
        assert_eq!(
            unresolved
                .begin_call(&unresolved_request, CallPurpose::Execution, None)
                .unwrap(),
            2
        );
        drop(unresolved);
        assert!(resume_execution_v1(
            &unresolved_path,
            "a3-unresolved",
            "a3-unresolved-context",
            8,
            &request,
            &plan,
            &Default::default(),
            &pack,
            &goal,
        )
        .is_err());
        let unresolved_view = CallJournal::inspect_existing(
            &unresolved_path,
            "a3-unresolved",
            "a3-unresolved-context",
            8,
        )
        .unwrap()
        .unwrap();
        assert_eq!(unresolved_view.stats().unwrap().unknown, 1);
        assert_eq!(unresolved_view.stats().unwrap().consumed, 2);
        drop(unresolved_view);

        let mut completed = initial;
        completed.status = DuelStatus::EngineVerified;
        completed.prompt = None;
        completed.resolved_decisions = next_request.decisions.clone();
        let calls = Arc::new(AtomicUsize::new(0));
        JournaledAdapter::new(
            Fixed(completed, calls.clone()),
            journal.clone(),
            CallPurpose::Execution,
        )
        .run(&next_request)
        .unwrap();
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(journal.stats().unwrap().consumed, 2);
        drop(journal);

        let resumed = resume_execution_v1(
            &path,
            "a3-replay",
            "a3-replay-context",
            8,
            &request,
            &plan,
            &Default::default(),
            &pack,
            &goal,
        )
        .unwrap();
        assert_eq!(
            resumed.progress.status,
            ExecutionRecoveryStatus::CompletedAwaitingAudit
        );
        assert_eq!(resumed.progress.completed_call_ids, vec![1, 2]);
        assert_eq!(resumed.progress.ledger.consumed, 2);
        assert!(resumed.progress.pending_intent.is_none());

        let before = std::fs::metadata(&path).unwrap().len();
        let resumed_again = resume_execution_v1(
            &path,
            "a3-replay",
            "a3-replay-context",
            8,
            &request,
            &plan,
            &Default::default(),
            &pack,
            &goal,
        )
        .unwrap();
        assert_eq!(resumed_again.progress.ledger.consumed, 2);
        assert_eq!(std::fs::metadata(&path).unwrap().len(), before);
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        let _ = std::fs::remove_dir_all(root);
    }
    #[test]
    fn continuous_and_pause_reopen_execution_have_identical_prefix_queries_and_charges() {
        use std::{
            collections::VecDeque,
            sync::atomic::{AtomicUsize, Ordering},
        };
        struct Scripted {
            results: std::sync::Mutex<VecDeque<DuelResult>>,
            calls: Arc<AtomicUsize>,
        }
        impl EngineAdapter for Scripted {
            fn doctor(&self) -> DoctorReport {
                panic!("synthetic continuation never calls doctor")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                self.calls.fetch_add(1, Ordering::SeqCst);
                self.results
                    .lock()
                    .unwrap()
                    .pop_front()
                    .ok_or_else(|| WorkerError::new("script_exhausted", "test", "no result"))
            }
        }
        fn goal() -> ygo_goal::Goal {
            serde_json::from_value(serde_json::json!({
                "version": 1,
                "expr": {"op": "count", "filter": {}, "min": 1}
            }))
            .unwrap()
        }
        fn plan(pack: &FirstTurnKnowledge, goal: &ygo_goal::Goal) -> ForecastPlan {
            ForecastPlan {
                id: "continuous-vs-resume".into(),
                start_id: "same-start".into(),
                knowledge_id: pack.id(),
                limits: SearchLimits::default(),
                goal_id: goal.id(),
                first_sensitive: None,
                steps: vec![],
                predicted_goal: ygo_goal::Evaluation {
                    node: "/goal".into(),
                    result: ygo_goal::Truth::Unknown,
                    observed: None,
                    matches: vec![],
                    reason: "synthetic forecast only".into(),
                    children: vec![],
                },
                predicted_resources: 0,
            }
        }
        fn next_prompt_result(initial: &DuelResult, resolved: Vec<Decision>) -> DuelResult {
            let mut result = initial.clone();
            let old = initial.events.last().unwrap();
            let frame = decode_frame(old.sequence + 1, &old.raw).unwrap();
            result.events.push(frame.clone());
            result.prompt = parse_prompt(frame.sequence, &frame.raw).unwrap();
            result.resolved_decisions = resolved;
            result.status = DuelStatus::DecisionRequired;
            result.error = None;
            result
        }
        fn run_case(paused: bool) -> (ExecutionCheckpointV1, String, usize, std::path::PathBuf) {
            let (request, mut initial) = initial();
            initial.versions = request.versions.clone();
            let pack = FirstTurnKnowledge::builtin().unwrap();
            let goal = goal();
            let plan = plan(&pack, &goal);
            let root = a3_test_root("pause-reopen-equivalence");
            let path = root.join("calls.jsonl");
            let journal = CallJournal::open(&path, "a3-equivalence", "same-context", 8).unwrap();
            journal.reserve("keep-for-later-audit", 1).unwrap();
            JournaledAdapter::new(
                Scripted {
                    results: std::sync::Mutex::new(VecDeque::from([initial.clone()])),
                    calls: Arc::new(AtomicUsize::new(0)),
                },
                journal.clone(),
                CallPurpose::Execution,
            )
            .run(&request)
            .unwrap();
            let mut checkpoint = begin_execution_v1(
                &request,
                1,
                &plan,
                &Default::default(),
                &pack,
                &goal,
                journal.clone(),
            )
            .unwrap();
            let initial_decision = {
                let prompt = checkpoint.progress.current_prefix.prompt.as_ref().unwrap();
                Decision {
                    prompt_id: prompt.id,
                    player: prompt.player,
                    choice: prompt.actions[0].choice.clone(),
                }
            };
            let mut first_request = request.clone();
            first_request.decisions.push(initial_decision.clone());
            let middle = next_prompt_result(&initial, vec![initial_decision]);
            let middle_prompt = middle.prompt.as_ref().unwrap();
            let second_decision = Decision {
                prompt_id: middle_prompt.id,
                player: middle_prompt.player,
                choice: middle_prompt.actions[0].choice.clone(),
            };
            let mut second_request = request.clone();
            second_request.decisions = middle.resolved_decisions.clone();
            second_request.decisions.push(second_decision.clone());
            let mut terminal = middle.clone();
            terminal.status = DuelStatus::EngineVerified;
            terminal.prompt = None;
            terminal.resolved_decisions = second_request.decisions.clone();
            let calls = Arc::new(AtomicUsize::new(0));
            let first_prompt = checkpoint.progress.current_prefix.prompt.as_ref().unwrap();
            let first_intent = ExecutionIntentV1::from_prompt(
                &checkpoint,
                first_request,
                ExecutionStage::Execution,
                Some(0),
                Decision {
                    prompt_id: first_prompt.id,
                    player: first_prompt.player,
                    choice: first_prompt.actions[0].choice.clone(),
                },
            )
            .unwrap();
            advance_execution_v1_with_backend(
                &mut checkpoint,
                first_intent,
                journal.clone(),
                Scripted {
                    results: std::sync::Mutex::new(VecDeque::from([middle, terminal.clone()])),
                    calls: calls.clone(),
                },
            )
            .unwrap();
            let mut open_journal = Some(journal);
            if paused {
                drop(open_journal.take());
                checkpoint = resume_execution_v1(
                    &path,
                    "a3-equivalence",
                    "same-context",
                    8,
                    &request,
                    &plan,
                    &Default::default(),
                    &pack,
                    &goal,
                )
                .unwrap();
            }
            let journal = match open_journal {
                Some(journal) => journal,
                None => CallJournal::open(&path, "a3-equivalence", "same-context", 8).unwrap(),
            };
            let second_intent = ExecutionIntentV1::from_prompt(
                &checkpoint,
                second_request,
                ExecutionStage::EndPhase,
                None,
                second_decision,
            )
            .unwrap();
            advance_execution_v1_with_backend(
                &mut checkpoint,
                second_intent,
                journal.clone(),
                Scripted {
                    results: std::sync::Mutex::new(VecDeque::from([terminal])),
                    calls: calls.clone(),
                },
            )
            .unwrap();
            let sequence = journal.charged_sequence_id().unwrap();
            drop(journal);
            (checkpoint, sequence, calls.load(Ordering::SeqCst), root)
        }

        let (continuous, continuous_charges, continuous_adapter_calls, continuous_root) =
            run_case(false);
        let (resumed, resumed_charges, resumed_adapter_calls, resumed_root) = run_case(true);
        assert_eq!(continuous_charges, resumed_charges);
        assert_eq!(continuous_adapter_calls, 2);
        assert_eq!(resumed_adapter_calls, 2);
        assert_eq!(
            continuous.progress.completed_call_ids,
            resumed.progress.completed_call_ids
        );
        assert_eq!(
            continuous.progress.queries.len(),
            resumed.progress.queries.len()
        );
        assert_eq!(continuous.progress.ledger.consumed, 3);
        assert_eq!(resumed.progress.ledger.consumed, 3);
        assert_eq!(
            continuous.progress.reservations,
            BTreeMap::from([("keep-for-later-audit".into(), 1)])
        );
        assert_eq!(
            continuous.progress.reservations,
            resumed.progress.reservations
        );
        assert_eq!(
            serde_json::to_value(&continuous.progress.current_prefix).unwrap(),
            serde_json::to_value(&resumed.progress.current_prefix).unwrap()
        );
        assert_eq!(
            continuous.progress.actual_resources,
            resumed.progress.actual_resources
        );
        assert_eq!(
            serde_json::to_value(&continuous.progress.predictions).unwrap(),
            serde_json::to_value(&resumed.progress.predictions).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&continuous.progress.instance_mapping).unwrap(),
            serde_json::to_value(&resumed.progress.instance_mapping).unwrap()
        );
        let _ = std::fs::remove_dir_all(continuous_root);
        let _ = std::fs::remove_dir_all(resumed_root);
    }
    #[test]
    fn a_second_intent_at_the_same_prompt_cannot_replace_the_first_prediction() {
        let (_, r) = initial();
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "choice-retry-{}.jsonl",
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let j = CallJournal::open(path, "retry", "fixture", 4).unwrap();
        let actions = &r.prompt.as_ref().unwrap().actions;
        assert!(actions.len() > 1);
        let first = persist_choice(
            &j,
            "forecast",
            &r,
            Some(0),
            actions[0].choice.clone(),
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
        .unwrap();
        let second = persist_choice(
            &j,
            "forecast",
            &r,
            Some(0),
            actions[1].choice.clone(),
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
        .unwrap();
        validate_choice_checkpoint(&first, "forecast", &r, &j).unwrap();
        validate_choice_checkpoint(&second, "forecast", &r, &j).unwrap();
        assert_eq!(j.stats().unwrap().consumed, 0);
    }
    #[test]
    fn a_pre_choice_checkpoint_rejects_changed_timing_public_facts_and_action() {
        let (_, r) = initial();
        let path = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../data/tmp")
            .join(format!(
                "pre-choice-{}-{}.jsonl",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
        let j = CallJournal::open(path, "pre-choice-unit", "recorded-raw-fixture", 4).unwrap();
        let choice = r.prompt.as_ref().unwrap().actions[0].choice.clone();
        let e = persist_choice(
            &j,
            "forecast",
            &r,
            Some(0),
            choice,
            &BTreeMap::new(),
            &BTreeSet::new(),
        )
        .unwrap();
        validate_choice_checkpoint(&e, "forecast", &r, &j).unwrap();
        let mut forged = e.clone();
        forged.before_call += 1;
        assert!(validate_choice_checkpoint(&forged, "forecast", &r, &j).is_err());
        forged = e.clone();
        forged.public.own_deck_counts.insert(1, 99);
        assert!(validate_choice_checkpoint(&forged, "forecast", &r, &j).is_err());
        forged = e;
        forged.choice = Choice::Command {
            command: 7,
            index: 0,
        };
        assert!(validate_choice_checkpoint(&forged, "forecast", &r, &j).is_err());
        assert_eq!(j.stats().unwrap().consumed, 0);
    }
    #[test]
    fn stale_identity_aliases_are_removed_after_an_ambiguous_shuffle() {
        let (_, r) = initial();
        let p = CausalState::initial(&first_turn_public_state(&r.checkpoint)).unwrap();
        let mut actual = p.clone();
        let id = p.cards[0].id.clone();
        actual.cards[0].identity_known = false;
        let mut map = p
            .cards
            .iter()
            .map(|c| (c.id.clone(), c.id.clone()))
            .collect();
        update_map(&p, &actual, &mut map);
        assert!(!map.contains_key(&id));
        assert!(map.contains_key(&p.cards[1].id));
    }
    #[test]
    fn an_unrelated_new_copy_cannot_replace_an_unknown_existing_instance() {
        let (_, r) = initial();
        let p = CausalState::initial(&first_turn_public_state(&r.checkpoint)).unwrap();
        let mut actual = p.clone();
        let mut new = actual.cards[0].clone();
        new.id = "new-physical-copy".into();
        new.card.sequence = 99;
        actual.cards[0].identity_known = false;
        actual.cards.push(new);
        let mut map = p
            .cards
            .iter()
            .map(|c| (c.id.clone(), c.id.clone()))
            .collect();
        update_map(&p, &actual, &mut map);
        assert!(
            !map.contains_key(&p.cards[0].id),
            "an exposed new copy is not proof of the old hidden instance"
        );
    }
    #[test]
    fn an_unknown_identity_stops_only_actions_that_depend_on_it() {
        let (_, r) = initial();
        let p = CausalState::initial(&first_turn_public_state(&r.checkpoint)).unwrap();
        let mut actual = p.clone();
        actual.cards[1].identity_known = false;
        let mut map = p
            .cards
            .iter()
            .map(|c| (c.id.clone(), c.id.clone()))
            .collect();
        update_map(&p, &actual, &mut map);
        let mut step = Transition {
            kind: TransitionKind::NormalSummon,
            rule_id: "pilot-normal".into(),
            source: p.cards[0].id.clone(),
            selections: vec![],
            requirements: vec![],
            after_cost: p.clone(),
            after_resolution: p.clone(),
        };
        assert!(required_instances_unknown(&step, &actual, &map).is_empty());
        step.selections.push(SemanticSelection {
            role: "cost".into(),
            stage: "cost".into(),
            card_id: p.cards[1].card.code,
            instance: Some(p.cards[1].id.clone()),
            from: p.cards[1].card.location,
            host: None,
        });
        assert_eq!(
            required_instances_unknown(&step, &actual, &map),
            vec![p.cards[1].id.clone()]
        );
        step.source = p.cards[1].id.clone();
        step.selections.clear();
        assert_eq!(
            required_instances_unknown(&step, &actual, &map),
            vec![p.cards[1].id.clone()]
        );
    }
}
