//! Resumable orchestration for the first-turn semantic execution loop.
//!
//! This layer stores semantic progress around the lower-level, single-call
//! checkpoint. It is diagnostic execution state only and cannot mint the
//! legacy `PartialExecutionV2` credential.
use super::resumable::{advance_execution_v1_with_backend, binding, execution_id, save_progress};
use super::*;
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::Path,
    sync::Arc,
};

const LOOP_KIND: &str = "first_turn_resumable_execution_loop";

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResumableExecutionPhaseV1 {
    Semantic,
    EndPhase,
    QueryAudit,
    Complete,
    Blocked,
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ResumableAuditStatusV1 {
    Pending,
    Running,
    Complete,
    Blocked,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResumableAuditProgressV1 {
    pub status: ResumableAuditStatusV1,
    pub next_query: usize,
    pub call_ids: Vec<u64>,
    pub reservation: Option<String>,
    pub diagnostic: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResumableLoopIntentV1 {
    pub expected_call: u64,
    pub purpose: CallPurpose,
    pub request: RunDuelRequest,
    pub phase: ResumableExecutionPhaseV1,
    pub step: Option<usize>,
    pub choice: Option<Decision>,
    pub selection_index: Option<usize>,
    pub prior_prefix_sha256: String,
}

/// Full-loop progress. The embedded single-call checkpoint remains the source
/// of truth for charged execution calls; this versioned record captures the
/// semantic operation, End Phase and independent query-audit cursor.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResumablePartialExecutionV1 {
    pub schema_version: u16,
    pub kind: String,
    pub execution_id: String,
    pub phase: ResumableExecutionPhaseV1,
    pub semantic_step: usize,
    pub inner: ExecutionCheckpointV1,
    pub instance_mapping: BTreeMap<String, String>,
    pub used_selections: BTreeSet<usize>,
    pub current_transition: Option<Transition>,
    pub before_state: Option<CausalState>,
    pub event_boundary: usize,
    pub predictions: Vec<PartialPrediction>,
    pub choices: Vec<PartialDecisionEvidence>,
    pub identity_gaps: Vec<String>,
    pub interruption: Option<PartialAnchor>,
    pub audit: ResumableAuditProgressV1,
    pub pending: Option<ResumableLoopIntentV1>,
    pub diagnostic: Option<String>,
}

impl ResumablePartialExecutionV1 {
    fn checkpoint_name(&self) -> String {
        format!("execution-loop-v1/{}", self.execution_id)
    }
}

fn persist_loop(state: &ResumablePartialExecutionV1, journal: &CallJournal) -> Result<(), String> {
    journal
        .save_checkpoint(
            &state.checkpoint_name(),
            &serde_json::to_value(state).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.message)
}

fn validate_loop_boundary(
    state: &ResumablePartialExecutionV1,
    journal: &CallJournal,
) -> Result<(), String> {
    let saved = journal
        .checkpoint(&state.checkpoint_name())
        .map_err(|e| e.message)?
        .ok_or("resumable loop checkpoint is missing")?;
    if saved != serde_json::to_value(state).map_err(|e| e.to_string())?
        || journal.stats().map_err(|e| e.message)? != state.inner.progress.ledger
        || journal.reservation_state().map_err(|e| e.message)? != state.inner.progress.reservations
    {
        return Err("resumable loop state or accounting differs from its saved boundary".into());
    }
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub fn begin_resumable_partial_execution_v1(
    request: &RunDuelRequest,
    initial_call: u64,
    initial_queries: &[QueryWitness],
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<ResumablePartialExecutionV1, String> {
    let mut inner = begin_execution_v1(
        request,
        initial_call,
        plan,
        catalog,
        pack,
        goal,
        journal.clone(),
    )?;
    let captured = QueryWitness::capture(&inner.progress.current_prefix)?;
    let mut queries = initial_queries.to_vec();
    if !queries
        .iter()
        .any(|query| serde_json::to_value(query).ok() == serde_json::to_value(&captured).ok())
    {
        queries.push(captured);
    }
    inner.progress.queries = queries;
    save_progress(&inner, &journal)?;
    let start = observed(
        &inner.progress.current_prefix,
        &inner.progress.queries,
        catalog,
        pack,
    )?;
    validate_forecast(plan, &start.state, catalog, pack, goal)?;
    let instance_mapping = start
        .state
        .cards
        .iter()
        .map(|card| (card.id.clone(), card.id.clone()))
        .collect();
    let state = ResumablePartialExecutionV1 {
        schema_version: 1,
        kind: LOOP_KIND.into(),
        execution_id: inner.execution_id.clone(),
        phase: if plan.steps.is_empty() {
            ResumableExecutionPhaseV1::EndPhase
        } else {
            ResumableExecutionPhaseV1::Semantic
        },
        semantic_step: 0,
        inner,
        instance_mapping,
        used_selections: BTreeSet::new(),
        current_transition: None,
        before_state: None,
        event_boundary: 0,
        predictions: Vec::new(),
        choices: Vec::new(),
        identity_gaps: Vec::new(),
        interruption: None,
        audit: ResumableAuditProgressV1 {
            status: ResumableAuditStatusV1::Pending,
            next_query: 0,
            call_ids: Vec::new(),
            reservation: None,
            diagnostic: None,
        },
        pending: None,
        diagnostic: None,
    };
    persist_loop(&state, &journal)?;
    Ok(state)
}

fn choose_semantic_action(
    state: &mut ResumablePartialExecutionV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(Choice, Option<usize>, ExecutionStage), String> {
    let result = &state.inner.progress.current_prefix;
    let prompt = result
        .prompt
        .as_ref()
        .ok_or("current prefix has no prompt")?;
    if state.phase == ResumableExecutionPhaseV1::EndPhase {
        let choice = if prompt.opcode == 11 {
            Choice::Command {
                command: 7,
                index: 0,
            }
        } else if prompt.opcode == 16 {
            Choice::Chain { index: None }
        } else {
            return Err(format!(
                "coverage_gap: unmodeled end phase opcode {}",
                prompt.opcode
            ));
        };
        if !prompt.actions.iter().any(|action| action.choice == choice) {
            return Err("end phase action is not legal".into());
        }
        return Ok((choice, None, ExecutionStage::EndPhase));
    }
    if state.phase != ResumableExecutionPhaseV1::Semantic {
        return Err("semantic action requested outside semantic phase".into());
    }
    if let Some(step) = state.current_transition.as_ref() {
        if prompt.opcode == 11 || prompt.opcode == 12 {
            return Err("semantic operation closed before choosing an action".into());
        }
        let before = state
            .before_state
            .as_ref()
            .ok_or("semantic operation before-state is missing")?;
        let (choice, selection) = follow_choice(result, step, before, &state.used_selections)?;
        return Ok((choice, selection, ExecutionStage::Execution));
    }

    let planned = plan
        .steps
        .get(state.semantic_step)
        .ok_or("semantic plan exhausted")?
        .clone();
    let before = observed(result, &state.inner.progress.queries, catalog, pack)?;
    let unknown = required_instances_unknown(&planned, &before.state, &state.instance_mapping);
    if !unknown.is_empty() {
        return Err(format!("required_instance_unknown: {}", unknown.join(",")));
    }
    let options = successors(&before.state, catalog, pack);
    let step = options
        .transitions
        .iter()
        .find(|candidate| same_action(&planned, candidate, &state.instance_mapping))
        .ok_or_else(|| {
            format!(
                "original_plan_blocked: {} prerequisites unavailable",
                planned.rule_id
            )
        })?
        .clone();
    let source = lookup(&before.state, &step.source).ok_or("source instance missing")?;
    if !source.identity_known {
        return Err("source identity unknown".into());
    }
    let trigger = before.state.pending.iter().any(|pending| {
        pending.rule_id == step.rule_id
            && pending.source == step.source
            && pending.eligibility == Truth::Yes
    });
    let rule = pack.rule(&step.rule_id).ok_or("missing rule")?;
    let choice = bind_start(result, &source.card, rule, step.kind, trigger)?;
    let mut prediction = PartialPrediction {
        checkpoint_id: None,
        step: state.semantic_step,
        before_call: journal.stats().map_err(|e| e.message)?.consumed as u64 + 1,
        at_prompt: prompt.id,
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
        expected_following_rules: plan.steps[state.semantic_step + 1..]
            .iter()
            .map(|s| s.rule_id.clone())
            .collect(),
        selected: step.clone(),
        differences: Vec::new(),
        after_prompt: None,
    };
    prediction.checkpoint_id = Some(immutable_prediction_checkpoint(&plan.id, &prediction));
    journal
        .save_checkpoint(
            prediction.checkpoint_id.as_deref().unwrap(),
            &serde_json::to_value(&prediction).unwrap(),
        )
        .map_err(|e| e.message)?;
    state.predictions.push(prediction);
    state.current_transition = Some(step);
    state.before_state = Some(before.state);
    state.event_boundary = result.events.len();
    state.used_selections.clear();
    Ok((choice, None, ExecutionStage::Execution))
}

fn apply_execution_outcome(
    state: &mut ResumablePartialExecutionV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(), String> {
    let result = state
        .inner
        .progress
        .last_completed_result
        .as_ref()
        .ok_or("completed execution result is missing")?
        .clone();
    if result.status == DuelStatus::EngineVerified {
        if state.phase != ResumableExecutionPhaseV1::EndPhase
            || state.semantic_step != plan.steps.len()
        {
            state.phase = ResumableExecutionPhaseV1::Blocked;
            state.diagnostic = Some(
                "engine terminal result arrived before semantic steps and End Phase were complete"
                    .into(),
            );
            return Ok(());
        }
        state.phase = ResumableExecutionPhaseV1::QueryAudit;
        let token = format!("resumable-query-audit-{}", state.execution_id);
        let needed = state.inner.progress.queries.len() + 1;
        journal.reserve(&token, needed).map_err(|e| e.message)?;
        state.audit.reservation = Some(token);
        state.audit.status = ResumableAuditStatusV1::Running;
        state.inner.progress.ledger = journal.stats().map_err(|e| e.message)?;
        state.inner.progress.reservations = journal.reservation_state().map_err(|e| e.message)?;
    } else if state.phase == ResumableExecutionPhaseV1::EndPhase {
        if result.status != DuelStatus::DecisionRequired {
            return Err("end phase did not stop at a supported decision".into());
        }
    } else if state.phase == ResumableExecutionPhaseV1::Semantic {
        if let Some(step) = state.current_transition.clone() {
            if result
                .prompt
                .as_ref()
                .is_some_and(|prompt| matches!(prompt.opcode, 11 | 12))
            {
                let _before = state
                    .before_state
                    .as_ref()
                    .ok_or("semantic before-state is missing")?;
                let after = observed(&result, &state.inner.progress.queries, catalog, pack)?;
                let comparison = compare_resources(&step.after_resolution, &after.public);
                let mut differences = comparison.differences;
                if step.after_resolution.normal_remaining != after.state.normal_remaining {
                    differences.push("normal summon opportunity differs".into());
                }
                if step.after_resolution.used != after.state.used {
                    differences.push("actual use counts differ".into());
                }
                let prediction = state
                    .predictions
                    .last_mut()
                    .ok_or("semantic prediction is missing")?;
                prediction.differences = differences.clone();
                prediction.after_prompt = result.prompt.as_ref().map(|p| p.id);
                let negated = result.events[state.event_boundary..]
                    .iter()
                    .any(|event| matches!(event.opcode, 75 | 76));
                if (comparison.result != Truth::Yes || !differences.is_empty()) && !negated {
                    return Err(format!(
                        "prediction_mismatch: {}: {}",
                        step.rule_id,
                        differences.join("; ")
                    ));
                }
                state.identity_gaps.extend(update_map(
                    &plan.steps[state.semantic_step].after_resolution,
                    &after.state,
                    &mut state.instance_mapping,
                ));
                state.current_transition = None;
                state.before_state = None;
                state.used_selections.clear();
                state.semantic_step += 1;
                if state.semantic_step == plan.steps.len() {
                    state.phase = ResumableExecutionPhaseV1::EndPhase;
                }
            }
        }
    }
    if state.phase == ResumableExecutionPhaseV1::EndPhase
        && state.inner.progress.current_prefix.status == DuelStatus::EngineVerified
    {
        state.phase = ResumableExecutionPhaseV1::QueryAudit;
    }
    state.inner.progress.ledger = journal.stats().map_err(|e| e.message)?;
    state.inner.progress.reservations = journal.reservation_state().map_err(|e| e.message)?;
    state.inner.progress.instance_mapping = state.instance_mapping.clone();
    state.inner.progress.used_selections = state.used_selections.clone();
    state.inner.progress.predictions = state.predictions.clone();
    let _ = goal;
    Ok(())
}

#[allow(clippy::too_many_arguments)]
pub fn advance_resumable_partial_execution_v1(
    state: &mut ResumablePartialExecutionV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<(), String> {
    advance_resumable_partial_execution_with_backend(
        state,
        plan,
        catalog,
        pack,
        goal,
        journal,
        ProcessEngineAdapter::new(state.inner.progress.current_request.engine.clone()),
    )
}

#[allow(clippy::too_many_arguments)]
fn advance_resumable_partial_execution_with_backend<A: EngineAdapter>(
    state: &mut ResumablePartialExecutionV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<(), String> {
    if state.schema_version != 1
        || state.kind != LOOP_KIND
        || state.phase == ResumableExecutionPhaseV1::Blocked
        || state.phase == ResumableExecutionPhaseV1::Complete
    {
        return Err("resumable loop is not at an advancing boundary".into());
    }
    state.inner.validate_bindings(
        &state.inner.progress.start_request,
        plan,
        catalog,
        pack,
        goal,
    )?;
    validate_loop_boundary(state, &journal)?;
    if state.phase == ResumableExecutionPhaseV1::QueryAudit {
        return Err("query audit requires its dedicated advance API".into());
    }
    let (choice, selection, stage) =
        choose_semantic_action(state, plan, catalog, pack, goal, &journal)?;
    let prefix = state.inner.progress.current_prefix.clone();
    let prompt = prefix.prompt.as_ref().ok_or("execution prompt missing")?;
    let mut request = state.inner.progress.start_request.clone();
    request.decisions = prefix.resolved_decisions.clone();
    let decision = Decision {
        prompt_id: prompt.id,
        player: prompt.player,
        choice,
    };
    request.decisions.push(decision.clone());
    // Synchronize semantic snapshots into the single-call checkpoint before
    // deriving the call intent. The intent must bind exactly the same mapping,
    // selections, and predictions as the authenticated inner boundary.
    persist_execution_semantics_v1(
        &mut state.inner,
        plan,
        catalog,
        pack,
        goal,
        state.instance_mapping.clone(),
        state.used_selections.clone(),
        state.predictions.clone(),
        state.before_state.as_ref(),
        &journal,
    )?;
    persist_loop(state, &journal)?;
    let intent = ExecutionIntentV1::from_prompt(
        &state.inner,
        request.clone(),
        stage,
        if stage == ExecutionStage::Execution {
            Some(state.semantic_step)
        } else {
            None
        },
        decision.clone(),
    )?;
    state.pending = Some(ResumableLoopIntentV1 {
        expected_call: intent.expected_call,
        purpose: CallPurpose::Execution,
        request,
        phase: state.phase,
        step: intent.step,
        choice: Some(decision.clone()),
        selection_index: selection,
        prior_prefix_sha256: intent.prior_prefix_sha256.clone(),
    });
    persist_loop(state, &journal)?;
    advance_execution_v1_with_backend(&mut state.inner, intent, journal.clone(), backend)?;
    if state.inner.progress.ledger.consumed as u64 != state.pending.as_ref().unwrap().expected_call
    {
        state.phase = ResumableExecutionPhaseV1::Blocked;
        state.diagnostic =
            Some("execution intent did not complete a certified call; no retry is allowed".into());
        persist_loop(state, &journal)?;
        return Ok(());
    }
    if state.inner.progress.status == ExecutionRecoveryStatus::Blocked {
        state.phase = ResumableExecutionPhaseV1::Blocked;
        state.diagnostic = state.inner.progress.diagnostic.clone();
        persist_loop(state, &journal)?;
        return Ok(());
    }
    if let Some(index) = selection {
        state.used_selections.insert(index);
    }
    state.choices.push(PartialDecisionEvidence {
        checkpoint_id: None,
        before_call: state.pending.as_ref().unwrap().expected_call,
        step: state.pending.as_ref().unwrap().step,
        prompt: decision.prompt_id,
        prefix_id: prefix_id(&prefix),
        public: first_turn_public_state(&prefix.checkpoint),
        choice: decision.choice.clone(),
        instance_map: state.instance_mapping.clone(),
        used_roles: state.used_selections.clone(),
    });
    apply_execution_outcome(state, plan, catalog, pack, goal, &journal)?;
    state.pending = None;
    persist_loop(state, &journal)
}

#[doc(hidden)]
#[cfg(test)]
#[allow(clippy::too_many_arguments)]
pub fn advance_resumable_partial_execution_v1_with_backend<A: EngineAdapter>(
    state: &mut ResumablePartialExecutionV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<(), String> {
    advance_resumable_partial_execution_with_backend(
        state, plan, catalog, pack, goal, journal, backend,
    )
}

fn normalized_result(result: &DuelResult) -> serde_json::Value {
    let mut value = result.clone();
    value.peak_working_set_bytes = None;
    serde_json::to_value(value).unwrap()
}

fn apply_audit_result(
    state: &mut ResumablePartialExecutionV1,
    actual: DuelResult,
    call_id: u64,
    journal: &CallJournal,
) -> Result<(), String> {
    let root = state
        .inner
        .progress
        .last_completed_result
        .as_ref()
        .ok_or("terminal root result missing")?
        .clone();
    if let Some(witness) = state.inner.progress.queries.get(state.audit.next_query) {
        let found = QueryWitness::capture(&actual)?;
        if serde_json::to_value(found).unwrap() != serde_json::to_value(witness).unwrap() {
            state.audit.status = ResumableAuditStatusV1::Blocked;
            state.audit.diagnostic = Some("query replay differs from recorded witness".into());
            state.phase = ResumableExecutionPhaseV1::Blocked;
            state.diagnostic = state.audit.diagnostic.clone();
            return Err("query replay differs from recorded witness".into());
        }
    } else if normalized_result(&actual) != normalized_result(&root) {
        state.audit.status = ResumableAuditStatusV1::Blocked;
        state.audit.diagnostic = Some("root replay differs from terminal result".into());
        state.phase = ResumableExecutionPhaseV1::Blocked;
        state.diagnostic = state.audit.diagnostic.clone();
        return Err("root replay differs from terminal result".into());
    }
    if journal.call_purpose(call_id).map_err(|e| e.message)? != CallPurpose::Witness {
        return Err("query audit call purpose differs".into());
    }
    state.audit.call_ids.push(call_id);
    state.audit.next_query += 1;
    state.pending = None;
    state.inner.progress.ledger = journal.stats().map_err(|e| e.message)?;
    state.inner.progress.reservations = journal.reservation_state().map_err(|e| e.message)?;
    save_progress(&state.inner, journal)?;
    if state.audit.next_query == state.inner.progress.queries.len() + 1 {
        let token = state
            .audit
            .reservation
            .take()
            .ok_or("query audit reservation missing")?;
        if journal
            .remaining_reservation(&token)
            .map_err(|e| e.message)?
            .is_some()
        {
            journal.release(&token).map_err(|e| e.message)?;
        }
        state.audit.status = ResumableAuditStatusV1::Complete;
        state.phase = ResumableExecutionPhaseV1::Complete;
        state.inner.progress.ledger = journal.stats().map_err(|e| e.message)?;
        state.inner.progress.reservations = journal.reservation_state().map_err(|e| e.message)?;
        save_progress(&state.inner, journal)?;
    }
    Ok(())
}

pub fn advance_resumable_query_audit_v1(
    state: &mut ResumablePartialExecutionV1,
    journal: Arc<CallJournal>,
) -> Result<(), String> {
    advance_resumable_query_audit_with_backend(
        state,
        journal,
        ProcessEngineAdapter::new(state.inner.progress.start_request.engine.clone()),
    )
}

fn advance_resumable_query_audit_with_backend<A: EngineAdapter>(
    state: &mut ResumablePartialExecutionV1,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<(), String> {
    if state.phase != ResumableExecutionPhaseV1::QueryAudit
        || state.audit.status != ResumableAuditStatusV1::Running
    {
        return Err("query audit is not at a resumable boundary".into());
    }
    validate_loop_boundary(state, &journal)?;
    let root = state
        .inner
        .progress
        .last_completed_result
        .as_ref()
        .ok_or("terminal root result missing")?;
    let mut request = state.inner.progress.start_request.clone();
    if let Some(witness) = state.inner.progress.queries.get(state.audit.next_query) {
        request.decisions = root
            .resolved_decisions
            .iter()
            .filter(|decision| decision.prompt_id < witness.event)
            .cloned()
            .collect();
    } else {
        request.decisions = root.resolved_decisions.clone();
    }
    let expected_call = journal.stats().map_err(|e| e.message)?.consumed as u64 + 1;
    let phase = state.phase;
    state.pending = Some(ResumableLoopIntentV1 {
        expected_call,
        purpose: CallPurpose::Witness,
        request: request.clone(),
        phase,
        step: None,
        choice: None,
        selection_index: None,
        prior_prefix_sha256: ygo_knowledge::hash(&serde_json::to_vec(root).unwrap()),
    });
    let name = format!(
        "immutable/execution-loop-audit/{}/{}",
        state.execution_id, expected_call
    );
    let intent_value = serde_json::to_value(state.pending.as_ref().unwrap()).unwrap();
    journal
        .save_checkpoint(&name, &intent_value)
        .map_err(|e| e.message)?;
    persist_loop(state, &journal)?;
    let token = state
        .audit
        .reservation
        .as_deref()
        .ok_or("query audit reservation missing")?;
    let actual = JournaledAdapter::new(backend, journal.clone(), CallPurpose::Witness)
        .run_reserved(&request, token)
        .map_err(|e| e.message)?;
    apply_audit_result(state, actual, expected_call, &journal)?;
    persist_loop(state, &journal)
}

#[doc(hidden)]
#[cfg(test)]
pub fn advance_resumable_query_audit_v1_with_backend<A: EngineAdapter>(
    state: &mut ResumablePartialExecutionV1,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<(), String> {
    advance_resumable_query_audit_with_backend(state, journal, backend)
}

/// Reopen the execution cursor. Execution-phase recovery delegates to A3's
/// strict read-only/then-exclusive reconciliation. Audit-phase recovery is
/// intentionally read-only unless the saved audit ledger exactly matches the
/// checkpoint; ambiguous tails are rejected for a later explicit recovery.
#[allow(clippy::too_many_arguments)]
pub fn resume_resumable_partial_execution_v1(
    path: impl AsRef<Path>,
    scope: &str,
    context: &str,
    limit: usize,
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
) -> Result<ResumablePartialExecutionV1, String> {
    let bound = binding(request, plan, catalog, pack, goal)?;
    let id = execution_id(&bound);
    let name = format!("execution-loop-v1/{id}");
    let (mut state, saved_value, read_stats, read_sequence) = {
        let readonly = CallJournal::inspect_existing(&path, scope, context, limit)
            .map_err(|e| e.message)?
            .ok_or("journal missing")?;
        readonly.verify().map_err(|e| e.message)?;
        if readonly.stats().map_err(|e| e.message)?.unknown != 0 {
            return Err("execution journal has unknown consumption".into());
        }
        let value = readonly
            .checkpoint(&name)
            .map_err(|e| e.message)?
            .ok_or("resumable loop checkpoint missing")?;
        let state: ResumablePartialExecutionV1 =
            serde_json::from_value(value.clone()).map_err(|e| e.to_string())?;
        if state.kind != LOOP_KIND || state.schema_version != 1 || state.execution_id != id {
            return Err("resumable loop checkpoint identity differs".into());
        }
        state
            .inner
            .validate_bindings(request, plan, catalog, pack, goal)?;
        if readonly.checkpoint_consumed(&name).map_err(|e| e.message)?
            != Some(state.inner.progress.ledger.consumed)
            || readonly.checkpoint_budget(&name).map_err(|e| e.message)?
                != Some(state.inner.progress.ledger.clone())
            || readonly
                .checkpoint_reservations(&name)
                .map_err(|e| e.message)?
                != Some(state.inner.progress.reservations.clone())
        {
            return Err("outer checkpoint ledger binding differs".into());
        }
        (
            state,
            value,
            readonly.stats().map_err(|e| e.message)?,
            readonly.charged_sequence_id().map_err(|e| e.message)?,
        )
    };
    if matches!(
        state.phase,
        ResumableExecutionPhaseV1::QueryAudit | ResumableExecutionPhaseV1::Complete
    ) {
        let pending = state.pending.clone();
        if let Some(intent) = &pending {
            if intent.purpose != CallPurpose::Witness
                || intent.expected_call != state.inner.progress.ledger.consumed as u64 + 1
            {
                return Err("saved query-audit intent identity or sequence differs".into());
            }
            if read_stats.consumed == intent.expected_call as usize {
                if read_stats.completed != read_stats.consumed
                    || read_stats.unknown != 0
                    || CallJournal::inspect_existing(&path, scope, context, limit)
                        .map_err(|e| e.message)?
                        .ok_or("journal missing")?
                        .call_purpose(intent.expected_call)
                        .map_err(|e| e.message)?
                        != CallPurpose::Witness
                {
                    return Err(
                        "query-audit trailing call is unresolved or has the wrong purpose".into(),
                    );
                }
                let (outcome, sequence) = {
                    let readonly = CallJournal::inspect_existing(&path, scope, context, limit)
                        .map_err(|e| e.message)?
                        .ok_or("journal missing")?;
                    (
                        readonly
                            .load_outcome(intent.expected_call, &intent.request)
                            .map_err(|e| e.message)?
                            .ok_or("query-audit result is unresolved")?,
                        readonly.charged_sequence_id().map_err(|e| e.message)?,
                    )
                };
                let exclusive = CallJournal::open_existing_strict(&path, scope, context, limit)
                    .map_err(|e| e.message)?
                    .ok_or("journal missing on exclusive reopen")?;
                if exclusive.stats().map_err(|e| e.message)? != read_stats
                    || exclusive.charged_sequence_id().map_err(|e| e.message)? != sequence
                    || exclusive.checkpoint(&name).map_err(|e| e.message)? != Some(saved_value)
                {
                    return Err("query-audit journal changed during exclusive reopen".into());
                }
                let actual =
                    outcome.map_err(|error| format!("query-audit worker error: {}", error.code))?;
                apply_audit_result(&mut state, actual, intent.expected_call, &exclusive)?;
                persist_loop(&state, &exclusive)?;
                return Ok(state);
            }
            if read_stats.consumed + 1 == intent.expected_call as usize {
                if read_stats != state.inner.progress.ledger {
                    return Err("uncharged query-audit intent has changed ledger state".into());
                }
                let exclusive = CallJournal::open_existing_strict(&path, scope, context, limit)
                    .map_err(|e| e.message)?
                    .ok_or("journal missing on exclusive reopen")?;
                if exclusive.stats().map_err(|e| e.message)? != read_stats
                    || exclusive.charged_sequence_id().map_err(|e| e.message)? != read_sequence
                    || exclusive.checkpoint(&name).map_err(|e| e.message)? != Some(saved_value)
                {
                    return Err("query-audit journal changed during exclusive reopen".into());
                }
                state.pending = None;
                persist_loop(&state, &exclusive)?;
                return Ok(state);
            }
            return Err("query-audit intent is not at the single recoverable call boundary".into());
        }
        if read_stats != state.inner.progress.ledger {
            return Err("query audit ledger changed after checkpoint".into());
        }
        for (index, call) in state.audit.call_ids.iter().enumerate() {
            let readonly = CallJournal::inspect_existing(&path, scope, context, limit)
                .map_err(|e| e.message)?
                .ok_or("journal missing")?;
            if *call
                != state
                    .inner
                    .progress
                    .completed_call_ids
                    .last()
                    .copied()
                    .unwrap_or(0)
                    + index as u64
                    + 1
                || readonly.call_purpose(*call).map_err(|e| e.message)? != CallPurpose::Witness
            {
                return Err("query audit call prefix differs".into());
            }
            let root = state
                .inner
                .progress
                .last_completed_result
                .as_ref()
                .ok_or("query audit root is missing")?;
            let mut expected_request = state.inner.progress.start_request.clone();
            if let Some(witness) = state.inner.progress.queries.get(index) {
                expected_request.decisions = root
                    .resolved_decisions
                    .iter()
                    .filter(|decision| decision.prompt_id < witness.event)
                    .cloned()
                    .collect();
            } else {
                expected_request.decisions = root.resolved_decisions.clone();
            }
            let outcome = readonly
                .load_outcome(*call, &expected_request)
                .map_err(|e| e.message)?
                .ok_or("query audit outcome is unresolved")?;
            let actual =
                outcome.map_err(|error| format!("query audit worker error: {}", error.code))?;
            if let Some(witness) = state.inner.progress.queries.get(index) {
                let found = QueryWitness::capture(&actual)?;
                if serde_json::to_value(found).unwrap() != serde_json::to_value(witness).unwrap() {
                    return Err("saved query audit differs from its witness".into());
                }
            } else if normalized_result(&actual) != normalized_result(root) {
                return Err("saved root audit differs from the terminal result".into());
            }
        }
        if state.audit.next_query != state.audit.call_ids.len()
            || state.audit.call_ids.len() > state.inner.progress.queries.len() + 1
        {
            return Err("query audit progress index differs from its authenticated calls".into());
        }
        let exclusive = CallJournal::open_existing_strict(&path, scope, context, limit)
            .map_err(|e| e.message)?
            .ok_or("journal missing on exclusive reopen")?;
        if exclusive.stats().map_err(|e| e.message)? != read_stats
            || exclusive.charged_sequence_id().map_err(|e| e.message)? != read_sequence
            || exclusive.checkpoint(&name).map_err(|e| e.message)? != Some(saved_value)
        {
            return Err("query audit ledger changed during exclusive reopen".into());
        }
        return Ok(state);
    }
    // Drop the read-only handle before the low-level strict exclusive reopen.
    let old_pending = state.pending.clone();
    drop(state);
    let inner = resume_execution_v1(
        &path, scope, context, limit, request, plan, catalog, pack, goal,
    )?;
    let exclusive = CallJournal::open_existing_strict(&path, scope, context, limit)
        .map_err(|e| e.message)?
        .ok_or("journal missing on exclusive reopen")?;
    if exclusive.stats().map_err(|e| e.message)? != read_stats
        || exclusive.charged_sequence_id().map_err(|e| e.message)? != read_sequence
        || exclusive
            .checkpoint(&inner.checkpoint_name())
            .map_err(|e| e.message)?
            != Some(serde_json::to_value(&inner).map_err(|e| e.to_string())?)
    {
        return Err("execution journal changed during exclusive reopen".into());
    }
    let value = exclusive
        .checkpoint(&name)
        .map_err(|e| e.message)?
        .ok_or("resumable loop checkpoint missing")?;
    let mut state: ResumablePartialExecutionV1 =
        serde_json::from_value(value).map_err(|e| e.to_string())?;
    if let Some(intent) = old_pending {
        if inner.progress.ledger.consumed as u64 == intent.expected_call {
            state.inner = inner;
            if let Some(index) = intent.selection_index {
                state.used_selections.insert(index);
            }
            apply_execution_outcome(&mut state, plan, catalog, pack, goal, &exclusive)?;
            state.pending = None;
            persist_loop(&state, &exclusive)?;
            return Ok(state);
        }
        if inner.progress.ledger.consumed as u64 + 1 == intent.expected_call {
            state.inner = inner;
            state.inner.progress.status = ExecutionRecoveryStatus::Ready;
            state.inner.progress.pending_action = None;
            state.inner.progress.pending_intent = None;
            state.inner.progress.diagnostic = None;
            state.pending = None;
            save_progress(&state.inner, &exclusive)?;
            persist_loop(&state, &exclusive)?;
            return Ok(state);
        }
        return Err("execution intent is not at the single recoverable call boundary".into());
    }
    if state.inner.progress.ledger != inner.progress.ledger {
        return Err("inner and outer execution checkpoints differ".into());
    }
    state.inner = inner;
    persist_loop(&state, &exclusive)?;
    Ok(state)
}
