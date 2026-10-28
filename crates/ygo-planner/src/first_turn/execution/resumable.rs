//! Durable execution cursors. These preserve progress; they never create a
//! native query-audit receipt or turn serialized data into a verified report.
use super::*;
use serde::{Deserialize, Serialize};
use std::path::Path;
use ygo_goal::{actual_trace_v6, TraceWindow};

const CHECKPOINT_KIND: &str = "first_turn_execution_checkpoint";

#[cfg(test)]
std::thread_local! {
    static FAIL_PROGRESS_SAVE: std::cell::Cell<(usize, Option<usize>)> =
        const { std::cell::Cell::new((0, None)) };
}

#[cfg(test)]
pub fn fail_next_execution_progress_save_v1() {
    fail_execution_progress_save_v1(1);
}

#[cfg(test)]
pub fn fail_execution_progress_save_v1(at_attempt: usize) {
    FAIL_PROGRESS_SAVE.with(|state| state.set((0, Some(at_attempt))));
}

#[cfg(test)]
fn should_fail_progress_save() -> bool {
    FAIL_PROGRESS_SAVE.with(|state| {
        let (attempts, fail_at) = state.get();
        let attempts = attempts + 1;
        let should_fail = fail_at == Some(attempts);
        state.set((attempts, if should_fail { None } else { fail_at }));
        should_fail
    })
}

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionRecoveryStatus {
    Ready,
    IntentPersisted,
    Paused,
    CompletedAwaitingAudit,
    Blocked,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct ExecutionBindingV1 {
    pub start_request_sha256: String,
    pub plan_sha256: String,
    pub catalog_sha256: String,
    pub knowledge_sha256: String,
    pub goal_sha256: String,
    pub runtime_versions_sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionIntentV1 {
    pub schema_version: u16,
    pub execution_id: String,
    pub expected_call: u64,
    pub purpose: CallPurpose,
    pub stage: ExecutionStage,
    pub step: Option<usize>,
    pub request: RunDuelRequest,
    pub choice: Decision,
    pub prior_prefix_sha256: String,
    pub instance_mapping: BTreeMap<String, String>,
    pub used_selections: BTreeSet<usize>,
    pub predictions: Vec<PartialPrediction>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionProgressV1 {
    pub status: ExecutionRecoveryStatus,
    pub stage: ExecutionStage,
    pub step: Option<usize>,
    pub start_request: RunDuelRequest,
    pub current_request: RunDuelRequest,
    pub current_prefix: DuelResult,
    /// Exact public engine resources at the last authenticated prefix. This is
    /// duplicated intentionally so resume can reject a stale or edited view.
    pub actual_resources: Checkpoint,
    pub trusted_prefix_request: RunDuelRequest,
    pub trusted_prefix_call: u64,
    pub last_completed_request: RunDuelRequest,
    pub last_completed_result: Option<DuelResult>,
    pub last_completed_error: Option<WorkerError>,
    pub instance_mapping: BTreeMap<String, String>,
    pub used_selections: BTreeSet<usize>,
    pub predictions: Vec<PartialPrediction>,
    pub queries: Vec<QueryWitness>,
    pub pending_action: Option<Decision>,
    pub pending_intent: Option<ExecutionIntentV1>,
    pub completed_call_ids: Vec<u64>,
    pub ledger: LedgerStats,
    pub reservations: BTreeMap<String, usize>,
    pub diagnostic: Option<String>,
}

/// Persisted execution state. It is an authenticated progress record only;
/// unlike `PartialExecutionV2`, it intentionally contains no success receipt.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionCheckpointV1 {
    pub schema_version: u16,
    pub kind: String,
    pub execution_id: String,
    pub binding: ExecutionBindingV1,
    pub plan_id: String,
    pub progress: ExecutionProgressV1,
}

impl ExecutionCheckpointV1 {
    pub fn validate_bindings(
        &self,
        request: &RunDuelRequest,
        plan: &ForecastPlan,
        catalog: &Catalog,
        pack: &FirstTurnKnowledge,
        goal: &Goal,
    ) -> Result<(), String> {
        let expected = binding(request, plan, catalog, pack, goal)?;
        if self.schema_version != 1
            || self.kind != CHECKPOINT_KIND
            || self.binding != expected
            || self.plan_id != plan.id
            || self.execution_id != execution_id(&expected)
            || serde_json::to_value(&self.progress.start_request).map_err(|e| e.to_string())?
                != serde_json::to_value(request).map_err(|e| e.to_string())?
        {
            return Err("execution checkpoint identity or input binding differs".into());
        }
        Ok(())
    }

    pub(super) fn checkpoint_name(&self) -> String {
        format!("execution-v1/{}", self.execution_id)
    }
}

fn hash_value<T: Serialize>(value: &T) -> Result<String, String> {
    Ok(ygo_knowledge::hash(
        &serde_json::to_vec(value).map_err(|error| error.to_string())?,
    ))
}

pub(super) fn binding(
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
) -> Result<ExecutionBindingV1, String> {
    Ok(ExecutionBindingV1 {
        start_request_sha256: hash_value(request)?,
        plan_sha256: hash_value(plan)?,
        catalog_sha256: hash_value(catalog)?,
        knowledge_sha256: hash_value(pack)?,
        goal_sha256: hash_value(goal)?,
        runtime_versions_sha256: hash_value(&request.versions)?,
    })
}

pub(super) fn execution_id(binding: &ExecutionBindingV1) -> String {
    ygo_knowledge::hash(&serde_json::to_vec(binding).unwrap())
}

fn intent_checkpoint_name(execution_id: &str, call_id: u64) -> String {
    format!("immutable/execution-intent/{execution_id}/{call_id}")
}

fn validate_inputs(
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
) -> Result<(), String> {
    request.validate_protocol()?;
    pack.validate()?;
    goal.validate()?;
    if request.protocol_version != 6
        || plan.goal_id != goal.id()
        || plan.knowledge_id != pack.id()
        || plan.steps.len() > 64
    {
        return Err("execution checkpoint input/profile/goal mismatch".into());
    }
    Ok(())
}

/// Begin at a previously charged, completed initial call. No engine is run.
#[allow(clippy::too_many_arguments)]
pub fn begin_execution_v1(
    request: &RunDuelRequest,
    initial_call: u64,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<ExecutionCheckpointV1, String> {
    validate_inputs(request, plan, pack, goal)?;
    let stats = journal.stats().map_err(|error| error.message)?;
    if stats.unknown != 0
        || stats.completed != stats.consumed
        || initial_call == 0
        || initial_call != stats.consumed as u64
        || !journal
            .unresolved_calls()
            .map_err(|error| error.message)?
            .is_empty()
        || journal
            .call_purpose(initial_call)
            .map_err(|error| error.message)?
            != CallPurpose::Execution
    {
        return Err(
            "initial execution prefix is incomplete or not the current charged call".into(),
        );
    }
    let result = journal
        .load_result(initial_call, request)
        .map_err(|error| error.message)?
        .ok_or("initial execution result is not completed")?;
    if result.error.is_some() {
        return Err("initial execution result is a recorded failure".into());
    }
    let query = QueryWitness::capture(&result)?;
    let bound = binding(request, plan, catalog, pack, goal)?;
    let id = execution_id(&bound);
    let checkpoint = ExecutionCheckpointV1 {
        schema_version: 1,
        kind: CHECKPOINT_KIND.into(),
        execution_id: id,
        binding: bound,
        plan_id: plan.id.clone(),
        progress: ExecutionProgressV1 {
            status: ExecutionRecoveryStatus::Ready,
            stage: ExecutionStage::Execution,
            step: Some(0),
            start_request: request.clone(),
            current_request: request.clone(),
            current_prefix: result.clone(),
            actual_resources: result.checkpoint.clone(),
            trusted_prefix_request: request.clone(),
            trusted_prefix_call: initial_call,
            last_completed_request: request.clone(),
            last_completed_result: Some(result),
            last_completed_error: None,
            instance_mapping: BTreeMap::new(),
            used_selections: BTreeSet::new(),
            predictions: Vec::new(),
            queries: vec![query],
            pending_action: None,
            pending_intent: None,
            completed_call_ids: vec![initial_call],
            ledger: stats,
            reservations: journal.reservation_state().map_err(|error| error.message)?,
            diagnostic: None,
        },
    };
    checkpoint.validate_bindings(request, plan, catalog, pack, goal)?;
    journal
        .save_checkpoint(
            &checkpoint.checkpoint_name(),
            &serde_json::to_value(&checkpoint).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.message)?;
    Ok(checkpoint)
}

impl ExecutionIntentV1 {
    /// Bind one legal choice at the currently observed raw prompt.
    pub fn from_prompt(
        checkpoint: &ExecutionCheckpointV1,
        request: RunDuelRequest,
        stage: ExecutionStage,
        step: Option<usize>,
        decision: Decision,
    ) -> Result<Self, String> {
        if !matches!(stage, ExecutionStage::Execution | ExecutionStage::EndPhase)
            || checkpoint.progress.status != ExecutionRecoveryStatus::Ready
        {
            return Err("execution intent is not valid at this checkpoint stage".into());
        }
        let result = &checkpoint.progress.current_prefix;
        let prompt = result
            .prompt
            .as_ref()
            .ok_or("current prefix has no prompt")?;
        if decision.prompt_id != prompt.id
            || decision.player != prompt.player
            || !prompt
                .actions
                .iter()
                .any(|action| action.choice == decision.choice)
        {
            return Err("execution intent choice is not in the observed prompt".into());
        }
        let mut expected_decisions = result.resolved_decisions.clone();
        expected_decisions.push(decision.clone());
        let mut root = request.clone();
        root.decisions.clear();
        let mut original_root = checkpoint.progress.start_request.clone();
        original_root.decisions.clear();
        if serde_json::to_value(&root).map_err(|error| error.to_string())?
            != serde_json::to_value(&original_root).map_err(|error| error.to_string())?
            || request.decisions != expected_decisions
        {
            return Err("execution intent request is not derived from the current prefix".into());
        }
        let ledger = &checkpoint.progress.ledger;
        Ok(Self {
            schema_version: 1,
            execution_id: checkpoint.execution_id.clone(),
            expected_call: ledger.consumed as u64 + 1,
            purpose: CallPurpose::Execution,
            stage,
            step,
            request,
            choice: decision,
            prior_prefix_sha256: hash_value(result)?,
            instance_mapping: checkpoint.progress.instance_mapping.clone(),
            used_selections: checkpoint.progress.used_selections.clone(),
            predictions: checkpoint.progress.predictions.clone(),
        })
    }
}

fn validate_intent(
    checkpoint: &ExecutionCheckpointV1,
    intent: &ExecutionIntentV1,
    stats: &LedgerStats,
) -> Result<(), String> {
    let mut boundary = checkpoint.clone();
    boundary.progress.status = ExecutionRecoveryStatus::Ready;
    boundary.progress.pending_intent = None;
    boundary.progress.pending_action = None;
    let expected = ExecutionIntentV1::from_prompt(
        &boundary,
        intent.request.clone(),
        intent.stage,
        intent.step,
        intent.choice.clone(),
    )?;
    if serde_json::to_value(intent).map_err(|error| error.to_string())?
        != serde_json::to_value(expected).map_err(|error| error.to_string())?
        || intent.schema_version != 1
        || intent.purpose != CallPurpose::Execution
        || intent.expected_call != stats.consumed as u64 + 1
    {
        return Err("execution intent does not match the authenticated call boundary".into());
    }
    Ok(())
}

pub(super) fn save_progress(
    checkpoint: &ExecutionCheckpointV1,
    journal: &CallJournal,
) -> Result<(), String> {
    #[cfg(test)]
    if should_fail_progress_save() {
        return Err("injected execution checkpoint publication failure".into());
    }
    journal
        .save_checkpoint(
            &checkpoint.checkpoint_name(),
            &serde_json::to_value(checkpoint).map_err(|error| error.to_string())?,
        )
        .map_err(|error| error.message)
}

/// Persist planner-side snapshots at an authenticated no-call boundary. These
/// remain forecast/diagnostic data; this operation cannot create a runtime
/// receipt or validate a semantic transition as engine evidence.
#[allow(clippy::too_many_arguments)]
pub fn persist_execution_semantics_v1(
    checkpoint: &mut ExecutionCheckpointV1,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    instance_mapping: BTreeMap<String, String>,
    used_selections: BTreeSet<usize>,
    predictions: Vec<PartialPrediction>,
    journal: &CallJournal,
) -> Result<(), String> {
    checkpoint.validate_bindings(
        &checkpoint.progress.start_request,
        plan,
        catalog,
        pack,
        goal,
    )?;
    if checkpoint.progress.status != ExecutionRecoveryStatus::Ready
        || checkpoint.progress.pending_intent.is_some()
        || journal.stats().map_err(|e| e.message)? != checkpoint.progress.ledger
    {
        return Err("semantic snapshot requires a ready, unchanged call boundary".into());
    }
    let saved = journal
        .checkpoint(&checkpoint.checkpoint_name())
        .map_err(|e| e.message)?
        .ok_or("execution checkpoint is missing")?;
    if saved != serde_json::to_value(&*checkpoint).map_err(|e| e.to_string())? {
        return Err("semantic snapshot differs from authenticated checkpoint".into());
    }
    let trace = actual_trace_v6(
        &checkpoint.progress.current_prefix,
        catalog,
        pack,
        &checkpoint.progress.queries,
    )?;
    let mapping_is_bound = match trace.window {
        TraceWindow::OwnMainAction => {
            let observed_ids = actual_state(
                &checkpoint.progress.current_prefix,
                &checkpoint.progress.queries,
                catalog,
                pack,
            )?
            .state
            .cards
            .iter()
            .map(|card| card.id.clone())
            .collect::<BTreeSet<_>>();
            instance_mapping
                .values()
                .all(|instance| observed_ids.contains(instance))
        }
        TraceWindow::Pending => {
            // During a multi-prompt operation mapped instances can temporarily
            // leave the visible facts. The mapping cannot advance until the
            // operation closes, so retain only the last authenticated mapping.
            instance_mapping == checkpoint.progress.instance_mapping
        }
        _ => return Err("semantic snapshot is outside a supported action window".into()),
    };
    if !mapping_is_bound {
        return Err("instance mapping references an unobserved actual instance".into());
    }
    let mut steps = BTreeSet::new();
    for prediction in &predictions {
        if prediction.step >= plan.steps.len()
            || !steps.insert(prediction.step)
            || !same_action(
                &plan.steps[prediction.step],
                &prediction.selected,
                &instance_mapping,
            )
        {
            return Err("prediction snapshot is not bound to a unique plan step".into());
        }
    }
    checkpoint.progress.instance_mapping = instance_mapping;
    checkpoint.progress.used_selections = used_selections;
    checkpoint.progress.predictions = predictions;
    save_progress(checkpoint, journal)
}

fn finish_recorded_call(
    checkpoint: &mut ExecutionCheckpointV1,
    intent: ExecutionIntentV1,
    outcome: Result<DuelResult, WorkerError>,
    journal: &CallJournal,
) -> Result<(), String> {
    checkpoint.progress.stage = intent.stage;
    checkpoint.progress.step = intent.step;
    checkpoint.progress.pending_action = None;
    checkpoint.progress.pending_intent = None;
    checkpoint.progress.instance_mapping = intent.instance_mapping.clone();
    checkpoint.progress.used_selections = intent.used_selections.clone();
    checkpoint.progress.predictions = intent.predictions.clone();
    checkpoint.progress.last_completed_request = intent.request.clone();
    checkpoint.progress.last_completed_result = None;
    checkpoint.progress.last_completed_error = None;
    match outcome {
        Ok(result) => {
            checkpoint.progress.last_completed_result = Some(result.clone());
            let prefix = &checkpoint.progress.current_prefix;
            if result.events.len() < prefix.events.len()
                || result.events[..prefix.events.len()] != prefix.events
                || !result
                    .resolved_decisions
                    .starts_with(&intent.request.decisions)
            {
                checkpoint.progress.status = ExecutionRecoveryStatus::Blocked;
                checkpoint.progress.diagnostic =
                    Some("recorded result does not extend the intended actual prefix".into());
            } else if let Some(error) = &result.error {
                let code = error.code.clone();
                checkpoint.progress.status = ExecutionRecoveryStatus::Blocked;
                checkpoint.progress.diagnostic = Some(format!("recorded worker result: {code}"));
            } else {
                if result.status == DuelStatus::DecisionRequired {
                    match QueryWitness::capture(&result) {
                        Ok(witness) => checkpoint.progress.queries.push(witness),
                        Err(detail) => {
                            checkpoint.progress.status = ExecutionRecoveryStatus::Blocked;
                            checkpoint.progress.diagnostic =
                                Some(format!("query capture: {detail}"));
                            checkpoint.progress.ledger = journal.stats().map_err(|e| e.message)?;
                            checkpoint.progress.reservations =
                                journal.reservation_state().map_err(|e| e.message)?;
                            checkpoint
                                .progress
                                .completed_call_ids
                                .push(intent.expected_call);
                            return Ok(());
                        }
                    }
                    checkpoint.progress.status = ExecutionRecoveryStatus::Ready;
                } else if result.status == DuelStatus::EngineVerified {
                    checkpoint.progress.status = ExecutionRecoveryStatus::CompletedAwaitingAudit;
                } else {
                    checkpoint.progress.status = ExecutionRecoveryStatus::Paused;
                }
                checkpoint.progress.diagnostic = None;
                checkpoint.progress.current_request = intent.request.clone();
                checkpoint.progress.trusted_prefix_request = intent.request.clone();
                checkpoint.progress.trusted_prefix_call = intent.expected_call;
                checkpoint.progress.actual_resources = result.checkpoint.clone();
                checkpoint.progress.current_prefix = result;
            }
        }
        Err(error) => {
            checkpoint.progress.last_completed_request = intent.request.clone();
            checkpoint.progress.last_completed_error = Some(error.clone());
            checkpoint.progress.status = ExecutionRecoveryStatus::Blocked;
            checkpoint.progress.diagnostic = Some(format!("recorded worker error: {}", error.code));
        }
    }
    checkpoint.progress.ledger = journal.stats().map_err(|error| error.message)?;
    checkpoint.progress.reservations =
        journal.reservation_state().map_err(|error| error.message)?;
    if !checkpoint
        .progress
        .completed_call_ids
        .contains(&intent.expected_call)
    {
        checkpoint
            .progress
            .completed_call_ids
            .push(intent.expected_call);
    }
    Ok(())
}

fn authenticate_saved_progress(
    readonly: &ReadOnlyJournal,
    checkpoint: &ExecutionCheckpointV1,
) -> Result<(), String> {
    let progress = &checkpoint.progress;
    if progress.completed_call_ids.last().copied() != Some(progress.ledger.consumed as u64)
        || !progress
            .completed_call_ids
            .contains(&progress.trusted_prefix_call)
        || progress
            .completed_call_ids
            .windows(2)
            .any(|calls| calls[1] != calls[0] + 1)
    {
        return Err("execution call prefix is incomplete or out of sequence".into());
    }
    for call_id in &progress.completed_call_ids {
        if readonly
            .call_purpose(*call_id)
            .map_err(|error| error.message)?
            != CallPurpose::Execution
        {
            return Err("execution prefix contains a call with another purpose".into());
        }
    }
    let trusted = readonly
        .load_outcome(
            progress.trusted_prefix_call,
            &progress.trusted_prefix_request,
        )
        .map_err(|error| error.message)?
        .ok_or("trusted execution prefix result is unresolved")?
        .map_err(|error| format!("trusted execution prefix is a worker error: {}", error.code))?;
    if !same_native(&trusted, &progress.current_prefix) {
        return Err("saved actual prefix differs from its charged journal result".into());
    }
    if progress.actual_resources != progress.current_prefix.checkpoint {
        return Err("saved resource snapshot differs from its authenticated prefix".into());
    }
    let last_call = *progress.completed_call_ids.last().unwrap();
    let outcome = readonly
        .load_outcome(last_call, &progress.last_completed_request)
        .map_err(|error| error.message)?
        .ok_or("last execution outcome is unresolved")?;
    match (
        &progress.last_completed_result,
        &progress.last_completed_error,
        outcome,
    ) {
        (Some(expected), None, Ok(found)) if same_native(expected, &found) => {}
        (None, Some(expected), Err(found))
            if serde_json::to_value(expected).ok() == serde_json::to_value(&found).ok() => {}
        _ => return Err("saved last outcome differs from the charged journal result".into()),
    }
    Ok(())
}

/// Execute exactly one caller-selected, raw-prompt-bound call. The checkpoint
/// intent is durable before the journal debit; a completed trailing call can
/// therefore be replayed from its authenticated result after a process crash.
pub fn advance_execution_v1(
    checkpoint: &mut ExecutionCheckpointV1,
    intent: ExecutionIntentV1,
    journal: Arc<CallJournal>,
) -> Result<(), String> {
    advance_execution_v1_with_backend(
        checkpoint,
        intent,
        journal,
        ProcessEngineAdapter::new(checkpoint.progress.current_request.engine.clone()),
    )
}

#[doc(hidden)]
pub fn advance_execution_v1_with_backend<A: EngineAdapter>(
    checkpoint: &mut ExecutionCheckpointV1,
    intent: ExecutionIntentV1,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<(), String> {
    let stats = journal.stats().map_err(|error| error.message)?;
    if stats.unknown != 0
        || stats.completed != stats.consumed
        || !journal
            .unresolved_calls()
            .map_err(|error| error.message)?
            .is_empty()
        || stats != checkpoint.progress.ledger
        || journal.reservation_state().map_err(|error| error.message)?
            != checkpoint.progress.reservations
    {
        return Err("execution ledger is not at the saved certified boundary".into());
    }
    let saved = journal
        .checkpoint(&checkpoint.checkpoint_name())
        .map_err(|error| error.message)?
        .ok_or("execution checkpoint is missing")?;
    if saved != serde_json::to_value(&*checkpoint).map_err(|error| error.to_string())? {
        return Err("in-memory execution checkpoint differs from journal".into());
    }
    validate_intent(checkpoint, &intent, &stats)?;
    let intent_name = intent_checkpoint_name(&checkpoint.execution_id, intent.expected_call);
    let intent_value = serde_json::to_value(&intent).map_err(|error| error.to_string())?;
    journal
        .save_checkpoint(&intent_name, &intent_value)
        .map_err(|error| error.message)?;
    checkpoint.progress.pending_action = Some(intent.choice.clone());
    checkpoint.progress.pending_intent = Some(intent.clone());
    checkpoint.progress.status = ExecutionRecoveryStatus::IntentPersisted;
    save_progress(checkpoint, &journal)?;

    if stats.consumed.saturating_add(stats.reserved) >= stats.limit {
        checkpoint.progress.status = ExecutionRecoveryStatus::Paused;
        checkpoint.progress.diagnostic = Some("budget has no unreserved call slot".into());
        return save_progress(checkpoint, &journal);
    }

    let _returned = JournaledAdapter::new(backend, journal.clone(), CallPurpose::Execution)
        .run(&intent.request);
    let after = journal.stats().map_err(|error| error.message)?;
    if after.consumed != intent.expected_call as usize {
        checkpoint.progress.status = ExecutionRecoveryStatus::Blocked;
        checkpoint.progress.diagnostic =
            Some("call boundary did not complete; debit state requires read-only recovery".into());
        checkpoint.progress.ledger = after;
        // Do not claim a call result or clear the intent. A reopen must decide
        // from the authenticated journal whether the debit is unresolved.
        save_progress(checkpoint, &journal)?;
        return Err("execution call did not reach its authenticated completion boundary".into());
    }
    if journal
        .call_purpose(intent.expected_call)
        .map_err(|error| error.message)?
        != CallPurpose::Execution
    {
        return Err("charged continuation has an unexpected purpose".into());
    }
    let outcome = journal
        .load_outcome(intent.expected_call, &intent.request)
        .map_err(|error| error.message)?
        .ok_or("charged continuation result remains unresolved")?;
    finish_recorded_call(checkpoint, intent, outcome, &journal)?;
    save_progress(checkpoint, &journal)
}

/// Authenticate a saved journal read-only, release its shared handle, then take
/// the exclusive writer and recheck the same ledger sequence before recovery.
#[allow(clippy::too_many_arguments)]
pub fn resume_execution_v1(
    path: impl AsRef<Path>,
    scope: &str,
    context: &str,
    limit: usize,
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
) -> Result<ExecutionCheckpointV1, String> {
    validate_inputs(request, plan, pack, goal)?;
    let expected_binding = binding(request, plan, catalog, pack, goal)?;
    let id = execution_id(&expected_binding);
    let name = format!("execution-v1/{id}");
    let (read_stats, read_sequence, saved_checkpoint, mut checkpoint, journal_path) = {
        let readonly = CallJournal::inspect_existing(&path, scope, context, limit)
            .map_err(|error| error.message)?
            .ok_or("execution journal does not exist")?;
        readonly.verify().map_err(|error| error.message)?;
        let stats = readonly.stats().map_err(|error| error.message)?;
        if stats.unknown != 0 {
            return Err("execution journal has unknown or abandoned consumption".into());
        }
        let saved = readonly
            .checkpoint(&name)
            .map_err(|error| error.message)?
            .ok_or("execution checkpoint is missing")?;
        let saved_checkpoint = saved.clone();
        let checkpoint: ExecutionCheckpointV1 =
            serde_json::from_value(saved).map_err(|error| error.to_string())?;
        checkpoint.validate_bindings(request, plan, catalog, pack, goal)?;
        let consumed = readonly
            .checkpoint_consumed(&name)
            .map_err(|error| error.message)?
            .ok_or("execution checkpoint prefix is missing")?;
        let saved_budget = readonly
            .checkpoint_budget(&name)
            .map_err(|error| error.message)?
            .ok_or("execution checkpoint budget is missing")?;
        let saved_reservations = readonly
            .checkpoint_reservations(&name)
            .map_err(|error| error.message)?
            .ok_or("execution checkpoint reservations are missing")?;
        if checkpoint.progress.ledger != saved_budget
            || checkpoint.progress.ledger.consumed != consumed
            || checkpoint.progress.reservations != saved_reservations
            || readonly
                .reservation_state()
                .map_err(|error| error.message)?
                != checkpoint.progress.reservations
        {
            return Err("execution checkpoint ledger or reservation binding differs".into());
        }
        authenticate_saved_progress(&readonly, &checkpoint)?;
        let sequence = readonly
            .charged_sequence_id()
            .map_err(|error| error.message)?;
        (
            stats,
            sequence,
            saved_checkpoint,
            checkpoint,
            path.as_ref().to_path_buf(),
        )
    };

    if read_stats.consumed < checkpoint.progress.ledger.consumed
        || read_stats.consumed > checkpoint.progress.ledger.consumed + 1
    {
        return Err("journal contains calls beyond the single recoverable intent".into());
    }
    let next_call = checkpoint.progress.ledger.consumed as u64 + 1;
    if checkpoint.progress.pending_intent.is_none() {
        let intent_name = intent_checkpoint_name(&id, next_call);
        let readonly = CallJournal::inspect_existing(&journal_path, scope, context, limit)
            .map_err(|error| error.message)?
            .ok_or("execution journal disappeared")?;
        if let Some(saved) = readonly.checkpoint(&intent_name).map_err(|e| e.message)? {
            let intent: ExecutionIntentV1 =
                serde_json::from_value(saved).map_err(|e| e.to_string())?;
            validate_intent(&checkpoint, &intent, &checkpoint.progress.ledger)?;
            checkpoint.progress.pending_action = Some(intent.choice.clone());
            checkpoint.progress.pending_intent = Some(intent);
            checkpoint.progress.status = ExecutionRecoveryStatus::IntentPersisted;
        }
    }
    let intent = checkpoint.progress.pending_intent.clone();
    if let Some(intent) = intent {
        if intent.expected_call != next_call || intent.execution_id != id {
            return Err("saved execution intent sequence or identity differs".into());
        }
        if read_stats.consumed == intent.expected_call as usize {
            let readonly = CallJournal::inspect_existing(&journal_path, scope, context, limit)
                .map_err(|error| error.message)?
                .ok_or("execution journal disappeared")?;
            if readonly
                .call_purpose(intent.expected_call)
                .map_err(|e| e.message)?
                != CallPurpose::Execution
            {
                return Err("trailing charged call has a different purpose".into());
            }
            match readonly
                .load_outcome(intent.expected_call, &intent.request)
                .map_err(|error| error.message)?
            {
                Some(_) => {}
                None => return Err("execution intent has an unresolved charged call".into()),
            }
        } else if read_stats.consumed + 1 != intent.expected_call as usize {
            return Err("execution intent is not at the next call boundary".into());
        }
    } else if read_stats.consumed != checkpoint.progress.ledger.consumed {
        return Err("unbound ledger calls follow the saved execution checkpoint".into());
    }

    let exclusive = CallJournal::open_existing_strict(&journal_path, scope, context, limit)
        .map_err(|error| error.message)?
        .ok_or("execution journal disappeared before exclusive reopen")?;
    if exclusive.stats().map_err(|error| error.message)? != read_stats
        || exclusive
            .charged_sequence_id()
            .map_err(|error| error.message)?
            != read_sequence
        || exclusive.checkpoint(&name).map_err(|error| error.message)? != Some(saved_checkpoint)
        || exclusive
            .reservation_state()
            .map_err(|error| error.message)?
            != checkpoint.progress.reservations
    {
        return Err("journal or execution checkpoint changed between read-only inspection and exclusive reopen".into());
    }
    let trailing_intent_name = intent_checkpoint_name(&id, next_call);
    let expected_intent = checkpoint
        .progress
        .pending_intent
        .as_ref()
        .map(serde_json::to_value)
        .transpose()
        .map_err(|error| error.to_string())?;
    if exclusive
        .checkpoint(&trailing_intent_name)
        .map_err(|error| error.message)?
        != expected_intent
    {
        return Err(
            "execution intent changed between read-only inspection and exclusive reopen".into(),
        );
    }
    let mut reconciled = false;
    if checkpoint.progress.pending_intent.is_some()
        && read_stats.consumed
            == checkpoint
                .progress
                .pending_intent
                .as_ref()
                .unwrap()
                .expected_call as usize
    {
        let intent = checkpoint.progress.pending_intent.clone().unwrap();
        if exclusive
            .call_purpose(intent.expected_call)
            .map_err(|e| e.message)?
            != CallPurpose::Execution
        {
            return Err("trailing charged call has a different purpose".into());
        }
        let outcome = exclusive
            .load_outcome(intent.expected_call, &intent.request)
            .map_err(|e| e.message)?
            .ok_or("execution intent has an unresolved charged call")?;
        finish_recorded_call(&mut checkpoint, intent, outcome, &exclusive)?;
        reconciled = true;
    }
    if checkpoint.progress.pending_intent.is_some()
        && checkpoint.progress.status != ExecutionRecoveryStatus::Paused
    {
        checkpoint.progress.status = ExecutionRecoveryStatus::IntentPersisted;
    }
    if reconciled || checkpoint.progress.status == ExecutionRecoveryStatus::IntentPersisted {
        save_progress(&checkpoint, &exclusive)?;
    }
    Ok(checkpoint)
}

#[cfg(test)]
mod contract_tests {
    use super::*;

    #[test]
    fn checkpoint_contract_requires_version_identity_and_complete_progress() {
        let value = serde_json::json!({
            "schema_version": 1,
            "kind": CHECKPOINT_KIND,
            "execution_id": "identity",
            "binding": {
                "start_request_sha256": "a", "plan_sha256": "b", "catalog_sha256": "c",
                "knowledge_sha256": "d", "goal_sha256": "e", "runtime_versions_sha256": "f"
            },
            "plan_id": "p",
            "progress": {}
        });
        assert!(serde_json::from_value::<ExecutionCheckpointV1>(value).is_err());
    }
}
