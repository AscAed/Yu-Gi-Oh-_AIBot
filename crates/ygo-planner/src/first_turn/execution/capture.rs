//! Internal v2 diagnostics retain incomplete evidence without granting a receipt.
use super::*;
use ygo_goal::{AuditedQueries, QueryAuditFailure};
mod validation;
pub use validation::validate_partial_execution_v2;

#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionStage {
    Execution,
    QueryCapture,
    EndPhase,
    WitnessReplay,
    Observation,
    Cleanup,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExecutionFault {
    pub kind: PartialFailureKind,
    pub stage: ExecutionStage,
    pub call: Option<u64>,
    pub step: Option<usize>,
    pub code: String,
    pub detail: String,
}
pub(super) fn worker_failure_kind(code: &str) -> PartialFailureKind {
    match code {
        "journal_budget" => PartialFailureKind::BudgetExhausted,
        "unsupported_prompt" => PartialFailureKind::CoverageGap,
        _ => PartialFailureKind::EngineFailure,
    }
}
pub(super) fn failure_label(kind: PartialFailureKind) -> &'static str {
    match kind {
        PartialFailureKind::BudgetExhausted => "budget_exhausted",
        PartialFailureKind::CoverageGap => "coverage_gap",
        _ => "engine_failure",
    }
}
#[derive(Debug)]
pub(super) struct StepFailure {
    pub kind: PartialFailureKind,
    pub code: &'static str,
    pub detail: String,
    pub stage: Option<ExecutionStage>,
}
impl StepFailure {
    pub fn new(kind: PartialFailureKind, code: &'static str, detail: impl Into<String>) -> Self {
        Self {
            kind,
            code,
            detail: detail.into(),
            stage: None,
        }
    }
    pub fn coverage(detail: String) -> Self {
        let mut error = Self::new(PartialFailureKind::CoverageGap, "observation", detail);
        error.stage = Some(ExecutionStage::Observation);
        error
    }
    pub fn journal(error: WorkerError) -> Self {
        Self::new(
            if error.code == "journal_budget" {
                PartialFailureKind::BudgetExhausted
            } else {
                PartialFailureKind::EngineFailure
            },
            "journal",
            format!("{}: {}", error.code, error.message),
        )
    }
}
impl From<String> for StepFailure {
    fn from(detail: String) -> Self {
        Self::new(
            PartialFailureKind::PromptBindingFailed,
            "prompt_binding",
            detail,
        )
    }
}
impl From<&str> for StepFailure {
    fn from(detail: &str) -> Self {
        detail.to_owned().into()
    }
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct AuditedPrefix {
    pub request: RunDuelRequest,
    pub result: DuelResult,
    pub witness_call: u64,
}

/// Observations and a verified recommendation are deliberately separate. JSON
/// cannot construct the private runtime receipt, even if every flag is forged.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialExecutionV2 {
    pub schema_version: u16,
    pub scope: String,
    pub plan_id: String,
    pub request: RunDuelRequest,
    pub start_request: RunDuelRequest,
    pub start_call: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub initial_attempt_checkpoint: Option<String>,
    pub last_result: Option<DuelResult>,
    pub last_audited_prefix: Option<AuditedPrefix>,
    pub queries: Vec<QueryWitness>,
    pub predictions: Vec<PartialPrediction>,
    /// Attempts include debited failures; resolved decisions remain in last_result.
    pub choices: Vec<PartialDecisionEvidence>,
    pub pending_choice: Option<PartialDecisionEvidence>,
    pub failure: Option<PartialFailure>,
    pub faults: Vec<ExecutionFault>,
    /// Provisional until independently replayed; never a receipt by itself.
    pub interruption: Option<PartialAnchor>,
    pub observed_terminal: Option<bool>,
    pub observed_goal: Option<ygo_goal::Evaluation>,
    pub audit_failure: Option<QueryAuditFailure>,
    pub audit_calls: Vec<u64>,
    pub calls: usize,
    pub identity_gaps: Vec<String>,
    #[serde(skip)]
    pub(super) receipt: Option<AuditedQueries>,
    #[serde(skip)]
    pub(super) receipt_content: Option<String>,
}
impl PartialExecutionV2 {
    /// Only a fresh in-process native receipt can make this true.
    pub fn verified(&self) -> bool {
        self.schema_version == 2
            && self
                .receipt_content
                .as_ref()
                .is_some_and(|hash| *hash == self.content_hash())
            && self.failure.is_none()
            && self.faults.is_empty()
            && self.audit_failure.is_none()
            && self.observed_terminal == Some(true)
            && self
                .observed_goal
                .as_ref()
                .is_some_and(|g| g.result == ygo_goal::Truth::Yes)
            && self.last_result.as_ref().is_some_and(|r| {
                self.receipt
                    .as_ref()
                    .is_some_and(|a| a.matches(&self.request, r, &self.queries))
            })
    }
    fn content_hash(&self) -> String {
        ygo_knowledge::hash(&serde_json::to_vec(self).unwrap())
    }
    pub(super) fn seal(&mut self) {
        self.receipt_content = Some(self.content_hash());
    }
    pub(super) fn into_legacy(self) -> Result<PartialExecution, String> {
        if self.audit_failure.is_some()
            || self.faults.iter().any(|f| {
                f.call.is_some()
                    || !matches!(
                        f.kind,
                        PartialFailureKind::BudgetExhausted
                            | PartialFailureKind::OriginalPlanBlocked
                            | PartialFailureKind::RequiredInstanceUnknown
                            | PartialFailureKind::PredictionMismatch
                    )
            })
            || self.receipt.is_none()
        {
            return Err("incomplete v2 diagnostic cannot become a verified v1 report".into());
        }
        Ok(PartialExecution {
            schema_version: 1,
            scope: self.scope,
            plan_id: self.plan_id,
            request: self.request,
            start_request: self.start_request,
            start_call: self.start_call,
            result: self.last_result.ok_or("no actual result")?,
            queries: self.queries,
            predictions: self.predictions,
            choices: self.choices,
            pending_choice: self.pending_choice,
            failure: self.failure,
            interruption: self.interruption,
            terminal: self.observed_terminal.ok_or("terminal status unknown")?,
            goal: self.observed_goal.ok_or("goal status unknown")?,
            audit_calls: self.audit_calls,
            calls: self.calls,
            identity_gaps: self.identity_gaps,
        })
    }

    fn observation_view(&self) -> Result<PartialExecution, String> {
        if self.schema_version != 2 {
            return Err(
                "incomplete v2 audit is diagnostic, not a complete contract receipt".into(),
            );
        }
        Ok(PartialExecution {
            schema_version: 1,
            scope: self.scope.clone(),
            plan_id: self.plan_id.clone(),
            request: self.request.clone(),
            start_request: self.start_request.clone(),
            start_call: self.start_call,
            result: self.last_result.clone().ok_or("no actual result")?,
            queries: self.queries.clone(),
            predictions: self.predictions.clone(),
            choices: self.choices.clone(),
            pending_choice: self.pending_choice.clone(),
            failure: self.failure.clone(),
            interruption: self.interruption.clone(),
            terminal: self
                .observed_terminal
                .ok_or("terminal observation unknown")?,
            goal: self
                .observed_goal
                .clone()
                .ok_or("goal observation unknown")?,
            audit_calls: self.audit_calls.clone(),
            calls: self.calls,
            identity_gaps: self.identity_gaps.clone(),
        })
    }
}

/// Recompute all completed local evidence. Incomplete audit diagnostics remain
/// explicitly unqualified until their failure-specific proof is supported.
fn validate_completed_capture(
    report: &PartialExecutionV2,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(), String> {
    let legacy = report.observation_view()?;
    validate_partial_execution(&legacy, plan, cat, pack, goal, journal)?;
    let prefix = report
        .last_audited_prefix
        .as_ref()
        .ok_or("missing last audited prefix")?;
    if !same_json(&prefix.request, &report.request)
        || report.audit_calls.last() != Some(&prefix.witness_call)
        || !same_native(&prefix.result, &legacy.result)
    {
        return Err("audited prefix reference differs".into());
    }
    if report.failure.is_none() && !report.faults.is_empty() {
        return Err("success has unresolved faults".into());
    }
    if report
        .failure
        .as_ref()
        .is_some_and(|f| f.kind != PartialFailureKind::BoundedRecoveryNotFound)
        && report.faults.len() != 1
    {
        return Err("failure must retain its typed cause".into());
    }
    for fault in &report.faults {
        let failure = report.failure.as_ref().ok_or("fault has no failure")?;
        let stage = if failure.step == plan.steps.len() {
            ExecutionStage::EndPhase
        } else {
            ExecutionStage::Execution
        };
        let step = (stage != ExecutionStage::EndPhase).then_some(failure.step);
        let code = match failure.kind {
            PartialFailureKind::BudgetExhausted => "journal_budget",
            PartialFailureKind::OriginalPlanBlocked => "prerequisites",
            PartialFailureKind::RequiredInstanceUnknown => "required_instance",
            PartialFailureKind::PredictionMismatch => "resources",
            _ => return Err("failure-specific v2 proof is not implemented".into()),
        };
        if fault.kind != failure.kind
            || fault.stage != stage
            || fault.step != step
            || fault.call.is_some()
            || fault.code != code
            || (failure.kind != PartialFailureKind::BudgetExhausted
                && fault.detail != failure.detail)
        {
            return Err("typed fault context differs from actual stopped operation".into());
        }
        if fault.kind == PartialFailureKind::BudgetExhausted {
            let pending = report
                .pending_choice
                .as_ref()
                .ok_or("missing unexecuted intent")?;
            let budget = journal
                .checkpoint_budget(&evidence_checkpoint(&plan.id, pending))
                .map_err(|e| e.message)?
                .ok_or("missing stopped budget")?;
            let available = budget
                .limit
                .saturating_sub(budget.consumed + budget.reserved);
            let detail = if available == 0 {
                "reservation exceeds scope budget"
            } else {
                "scope call budget exhausted"
            };
            if fault.detail != detail || failure.detail != format!("budget_exhausted: {detail}") {
                return Err("budget failure detail differs from the denied operation".into());
            }
        }
    }
    Ok(())
}

/// Importing JSON never grants a receipt. Replay must reacquire native queries.
#[allow(clippy::too_many_arguments)]
pub fn replay_partial_execution_v2(
    report: &mut PartialExecutionV2,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
    audit: Arc<CallJournal>,
) -> Result<(), String> {
    let engine = report.request.engine.clone();
    replay_partial_execution_v2_with_engine(report, plan, cat, pack, goal, journal, audit, &engine)
        .map(|_| ())
}

/// Use a working deployment to re-observe a retained prefix after a process
/// failure. Original error evidence and its original charges remain unchanged.
#[allow(clippy::too_many_arguments)]
pub fn replay_partial_execution_v2_with_engine(
    report: &mut PartialExecutionV2,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
    audit: Arc<CallJournal>,
    engine: &ProcessEngineConfig,
) -> Result<Vec<u64>, String> {
    validate_partial_execution_v2(report, plan, cat, pack, goal, journal)?;
    let mut request = report.request.clone();
    request.engine = engine.clone();
    report.receipt = Some(verify_query_replays(
        &request,
        report.last_result.as_ref().ok_or("no actual result")?,
        &report.queries,
        audit,
    )?);
    report.seal();
    Ok(report.receipt.as_ref().unwrap().call_ids.clone())
}

/// Start a fresh local experiment. A failed initial call has no trusted prefix;
/// the failed attempt is still charged and can be inspected independently.
pub fn start_partial_v2(
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
) -> Result<PartialExecutionV2, String> {
    start_partial_v2_with_backend(
        request,
        plan,
        cat,
        pack,
        goal,
        journal,
        ProcessEngineAdapter::new(request.engine.clone()),
    )
}

fn start_partial_v2_with_backend<A: EngineAdapter>(
    request: &RunDuelRequest,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: Arc<CallJournal>,
    backend: A,
) -> Result<PartialExecutionV2, String> {
    request.validate_protocol()?;
    pack.validate()?;
    goal.validate()?;
    if request.protocol_version != 6 || plan.goal_id != goal.id() || plan.knowledge_id != pack.id()
    {
        return Err("partial start input/profile/goal mismatch".into());
    }
    let budget = journal.stats().map_err(|e| e.message)?;
    if !(1..=512).contains(&budget.limit) {
        return Err("partial group budget must be 1..512".into());
    }
    let before = budget.consumed;
    let intent = initial_attempt_intent(request, &plan.id, &budget);
    let initial_attempt_checkpoint = format!(
        "immutable/partial-start/{}",
        ygo_knowledge::hash(&serde_json::to_vec(&intent).unwrap())
    );
    journal
        .save_checkpoint(&initial_attempt_checkpoint, &intent)
        .map_err(|e| e.message)?;
    let adapter = JournaledAdapter::new(backend, journal.clone(), CallPurpose::Execution);
    let outcome = adapter.run(request);
    let mut last_result = None;
    let (kind, stage, code, detail) = match outcome {
        Ok(result) if result.error.is_some() => {
            let error = result.error.clone().unwrap();
            last_result = Some(result);
            (
                worker_failure_kind(&error.code),
                ExecutionStage::Execution,
                error.code,
                error.message,
            )
        }
        Ok(result) => match QueryWitness::capture(&result) {
            Ok(witness) => {
                return execute_partial_v2(
                    request,
                    &result,
                    &[witness],
                    plan,
                    cat,
                    pack,
                    goal,
                    journal,
                )
            }
            Err(detail) => {
                let kind = if result.status == DuelStatus::DecisionRequired {
                    PartialFailureKind::EngineFailure
                } else {
                    PartialFailureKind::CoverageGap
                };
                last_result = Some(result);
                (
                    kind,
                    ExecutionStage::QueryCapture,
                    "query_capture".into(),
                    detail,
                )
            }
        },
        Err(error) => (
            worker_failure_kind(&error.code),
            ExecutionStage::Execution,
            error.code,
            error.message,
        ),
    };
    let after = journal.stats().map_err(|e| e.message)?.consumed;
    Ok(PartialExecutionV2 {
        schema_version: 2,
        scope: "partial_integration_native_execution; not full rule certification".into(),
        plan_id: plan.id.clone(),
        request: request.clone(),
        start_request: request.clone(),
        start_call: before,
        initial_attempt_checkpoint: Some(initial_attempt_checkpoint),
        last_result,
        last_audited_prefix: None,
        queries: vec![],
        predictions: vec![],
        choices: vec![],
        pending_choice: None,
        failure: Some(PartialFailure {
            kind,
            step: 0,
            prompt: None,
            detail: detail.clone(),
        }),
        faults: vec![ExecutionFault {
            kind,
            stage,
            call: (after > before).then_some(after as u64),
            step: None,
            code,
            detail,
        }],
        interruption: None,
        observed_terminal: None,
        observed_goal: None,
        audit_failure: None,
        audit_calls: vec![],
        calls: after - before,
        identity_gaps: vec![],
        receipt: None,
        receipt_content: None,
    })
}

fn initial_attempt_intent(
    request: &RunDuelRequest,
    plan_id: &str,
    budget: &LedgerStats,
) -> serde_json::Value {
    serde_json::json!({"version":1,"request":request,"plan_id":plan_id,"before_call":budget.consumed+1,"budget":budget})
}
