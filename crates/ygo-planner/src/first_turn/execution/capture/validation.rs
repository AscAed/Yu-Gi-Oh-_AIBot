//! Diagnostic validity and successful native qualification are different checks.
use super::*;

pub fn validate_partial_execution_v2(
    report: &PartialExecutionV2,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(), String> {
    pack.validate()?;
    goal.validate()?;
    journal.verify().map_err(|e| e.message)?;
    if report.schema_version != 2
        || report.start_call > 512
        || report.calls > 512
        || report.plan_id != plan.id
        || plan.knowledge_id != pack.id()
        || plan.goal_id != goal.id()
        || report.scope != "partial_integration_native_execution; not full rule certification"
        || report.start_call + report.calls > journal.stats().map_err(|e| e.message)?.consumed
        || !(1..=512).contains(&journal.stats().map_err(|e| e.message)?.limit)
    {
        return Err("diagnostic version, identity, scope, or cost differs".into());
    }
    if report.last_result.is_none() {
        return validate_failed_start(report, journal);
    }
    if report.initial_attempt_checkpoint.is_some() {
        return validate_failed_initial_result(report, journal);
    }
    if report.audit_failure.is_none() && !report.faults.iter().any(|f| f.call.is_some()) {
        return validate_completed_capture(report, plan, cat, pack, goal, journal);
    }
    validate_failed_audit_capture(report, plan, cat, pack, goal, journal)
}

fn validate_failed_initial_result(
    report: &PartialExecutionV2,
    journal: &CallJournal,
) -> Result<(), String> {
    if report.calls != 1
        || report.faults.len() != 1
        || report.failure.is_none()
        || !same_json(&report.request, &report.start_request)
        || report.last_audited_prefix.is_some()
        || !report.queries.is_empty()
        || !report.predictions.is_empty()
        || !report.choices.is_empty()
        || report.pending_choice.is_some()
        || report.interruption.is_some()
        || report.observed_terminal.is_some()
        || report.observed_goal.is_some()
        || report.audit_failure.is_some()
        || !report.audit_calls.is_empty()
        || !report.identity_gaps.is_empty()
    {
        return Err("failed initial result has invented state or evidence".into());
    }
    let key = report
        .initial_attempt_checkpoint
        .as_deref()
        .ok_or("missing initial attempt intent")?;
    let budget = validate_initial_attempt_intent(report, journal, key)?;
    if report.start_call != budget.consumed {
        return Err("initial attempt call position differs".into());
    }
    let call = report.start_call as u64 + 1;
    if report.faults[0].call != Some(call)
        || journal.call_purpose(call).map_err(|e| e.message)? != CallPurpose::Execution
    {
        return Err("initial result call or purpose differs".into());
    }
    let outcome = journal
        .load_outcome(call, &report.start_request)
        .map_err(|e| e.message)?
        .ok_or("initial attempt is still unknown")?;
    let actual = outcome.map_err(|_| "initial result outcome is not a DuelResult")?;
    let saved = report
        .last_result
        .as_ref()
        .ok_or("missing initial diagnostic result")?;
    if !same_json(&actual, saved) || actual.versions != report.start_request.versions {
        return Err("initial diagnostic result differs from charged journal result".into());
    }
    let (kind, stage, code, detail) = if let Some(error) = &actual.error {
        (
            worker_failure_kind(&error.code),
            ExecutionStage::Execution,
            error.code.clone(),
            error.message.clone(),
        )
    } else {
        let detail = QueryWitness::capture(&actual)
            .err()
            .ok_or("initial result contains a capturable query")?;
        let kind = if actual.status == ygo_engine_adapter::DuelStatus::DecisionRequired {
            PartialFailureKind::EngineFailure
        } else {
            PartialFailureKind::CoverageGap
        };
        (
            kind,
            ExecutionStage::QueryCapture,
            "query_capture".to_string(),
            detail,
        )
    };
    let fault = ExecutionFault {
        kind,
        stage,
        call: Some(call),
        step: None,
        code,
        detail: detail.clone(),
    };
    let failure = PartialFailure {
        kind,
        step: 0,
        prompt: None,
        detail,
    };
    if !same_json(&report.faults, &vec![fault]) || !same_json(&report.failure, &Some(failure)) {
        return Err("initial result failure classification differs from charged result".into());
    }
    Ok(())
}

fn validate_initial_attempt_intent(
    report: &PartialExecutionV2,
    journal: &CallJournal,
    key: &str,
) -> Result<ygo_engine_adapter::LedgerStats, String> {
    let budget = journal
        .checkpoint_budget(key)
        .map_err(|e| e.message)?
        .ok_or("missing initial attempt budget")?;
    let intent = initial_attempt_intent(&report.start_request, &report.plan_id, &budget);
    if key
        != format!(
            "immutable/partial-start/{}",
            ygo_knowledge::hash(&serde_json::to_vec(&intent).unwrap())
        )
        || journal.checkpoint(key).map_err(|e| e.message)? != Some(intent)
    {
        return Err("initial attempt request, identity, or budget differs".into());
    }
    Ok(budget)
}

fn validate_failed_start(report: &PartialExecutionV2, journal: &CallJournal) -> Result<(), String> {
    if report.calls > 1
        || report.faults.len() != 1
        || report.failure.is_none()
        || !same_json(&report.request, &report.start_request)
        || report.last_audited_prefix.is_some()
        || !report.queries.is_empty()
        || !report.predictions.is_empty()
        || !report.choices.is_empty()
        || report.pending_choice.is_some()
        || report.interruption.is_some()
        || report.observed_terminal.is_some()
        || report.observed_goal.is_some()
        || report.audit_failure.is_some()
        || !report.audit_calls.is_empty()
        || !report.identity_gaps.is_empty()
    {
        return Err("failed initial call has invented state or evidence".into());
    }
    let budget = if let Some(key) = &report.initial_attempt_checkpoint {
        let budget = validate_initial_attempt_intent(report, journal, key)?;
        if report.start_call != budget.consumed {
            return Err("initial attempt request, identity, or budget differs".into());
        }
        Some(budget)
    } else {
        None
    };
    if report.calls == 0 {
        let budget = budget.ok_or("initial budget refusal has no persistent intent")?;
        if budget.consumed + budget.reserved < budget.limit {
            return Err("initial call could still start".into());
        }
        let detail = "scope call budget exhausted";
        let fault = ExecutionFault {
            kind: PartialFailureKind::BudgetExhausted,
            stage: ExecutionStage::Execution,
            call: None,
            step: None,
            code: "journal_budget".into(),
            detail: detail.into(),
        };
        let failure = PartialFailure {
            kind: fault.kind,
            step: 0,
            prompt: None,
            detail: detail.into(),
        };
        if !same_json(&report.faults, &vec![fault]) || !same_json(&report.failure, &Some(failure)) {
            return Err("initial budget refusal classification differs".into());
        }
        return Ok(());
    }
    let call = report.start_call as u64 + 1;
    if journal.call_purpose(call).map_err(|e| e.message)? != CallPurpose::Execution {
        return Err("initial attempt purpose differs".into());
    }
    let outcome = journal
        .load_outcome(call, &report.start_request)
        .map_err(|e| e.message)?
        .ok_or("initial attempt is still unknown")?;
    let error = outcome
        .err()
        .ok_or("initial call did produce an actual result")?;
    let fault = ExecutionFault {
        kind: worker_failure_kind(&error.code),
        stage: ExecutionStage::Execution,
        call: Some(call),
        step: None,
        code: error.code,
        detail: error.message.clone(),
    };
    let failure = PartialFailure {
        kind: fault.kind,
        step: 0,
        prompt: None,
        detail: error.message,
    };
    if !same_json(&report.faults, &vec![fault]) || !same_json(&report.failure, &Some(failure)) {
        return Err("initial failure classification differs from charged worker error".into());
    }
    Ok(())
}

fn validate_failed_audit_capture(
    report: &PartialExecutionV2,
    plan: &ForecastPlan,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    goal: &Goal,
    journal: &CallJournal,
) -> Result<(), String> {
    let legacy = report.observation_view()?;
    let error = report.audit_failure.as_ref();
    if let Some(error) = error {
        ygo_goal::validate_query_audit_failure(
            &report.request,
            &legacy.result,
            &report.queries,
            error,
            journal,
        )?;
    } else {
        validate_audits(&legacy, journal)?;
    }
    let mut expected_request = report.start_request.clone();
    expected_request.decisions = legacy.result.resolved_decisions.clone();
    if !same_json(&report.request, &expected_request)
        || report.calls != report.choices.len() + report.audit_calls.len()
        || error.is_some_and(|e| report.audit_calls != e.call_ids)
        || report.pending_choice.is_some()
        || report.start_call == 0
        || journal
            .call_purpose(report.start_call as u64)
            .map_err(|e| e.message)?
            != CallPurpose::Execution
    {
        return Err("failed execution request, calls, or unexecuted intent differs".into());
    }
    let initial = journal
        .load_result(report.start_call as u64, &report.start_request)
        .map_err(|e| e.message)?
        .ok_or("missing initial result")?;
    if initial.protocol_version != report.start_request.protocol_version
        || initial.versions != report.start_request.versions
    {
        return Err("initial diagnostic runtime differs from its request".into());
    }
    let mut actual_queries = vec![QueryWitness::capture(&initial)?];
    let start = observed(&initial, &actual_queries, cat, pack)?;
    validate_forecast(plan, &start.state, cat, pack, goal)?;
    let mut results = vec![initial];
    let mut worker_fault = None;
    for (i, choice) in report.choices.iter().enumerate() {
        let before = results.last().ok_or("missing preceding actual prefix")?;
        if choice.before_call != (report.start_call + i + 1) as u64
            || journal
                .call_purpose(choice.before_call)
                .map_err(|e| e.message)?
                != CallPurpose::Execution
        {
            return Err("execution attempt sequence differs".into());
        }
        validate_choice_checkpoint(choice, &plan.id, before, journal)?;
        let mut q = report.start_request.clone();
        q.decisions = before.resolved_decisions.clone();
        q.decisions.push(Decision {
            prompt_id: choice.prompt,
            player: 0,
            choice: choice.choice.clone(),
        });
        match journal
            .load_outcome(choice.before_call, &q)
            .map_err(|e| e.message)?
            .ok_or("execution attempt is still unknown")?
        {
            Ok(after) => {
                if !after.events.starts_with(&before.events)
                    || !after
                        .resolved_decisions
                        .starts_with(&before.resolved_decisions)
                {
                    return Err("latest actual result breaks the legal prefix".into());
                }
                if after.prompt.is_some() && after.error.is_none() {
                    actual_queries.push(QueryWitness::capture(&after)?);
                }
                results.push(after);
            }
            Err(error) => {
                if i + 1 != report.choices.len() {
                    return Err("execution continued after worker failure".into());
                }
                let stage = if choice.step.is_some() {
                    ExecutionStage::Execution
                } else {
                    ExecutionStage::EndPhase
                };
                let fault = ExecutionFault {
                    kind: worker_failure_kind(&error.code),
                    stage,
                    call: Some(choice.before_call),
                    step: choice.step,
                    code: error.code,
                    detail: error.message.clone(),
                };
                let failure = PartialFailure {
                    kind: fault.kind,
                    step: choice.step.unwrap_or(plan.steps.len()),
                    prompt: before.prompt.as_ref().map(|p| p.id),
                    detail: format!("{}: {}", failure_label(fault.kind), error.message),
                };
                worker_fault = Some((fault, failure));
            }
        }
    }
    if !same_native(
        results.last().ok_or("missing actual prefix")?,
        &legacy.result,
    ) || !same_json(&actual_queries, &report.queries)
    {
        return Err("last actual result or query sequence differs".into());
    }
    validate_predictions(&legacy, plan, cat, pack, goal, journal, &start, &results)?;
    if let Some((fault, failure)) = worker_fault {
        if !same_json(&report.faults, &vec![fault]) || !same_json(&report.failure, &Some(failure)) {
            return Err(
                "worker failure stage, instance operation, or original error differs".into(),
            );
        }
    } else if report.choices.is_empty()
        && report.predictions.is_empty()
        && error.is_some_and(|e| {
            e.stage == ygo_goal::QueryAuditStage::Reservation && e.code == "journal_budget"
        })
    {
        let detail = "journal_budget: reservation exceeds scope budget";
        let fault = ExecutionFault {
            kind: PartialFailureKind::BudgetExhausted,
            stage: ExecutionStage::Execution,
            call: None,
            step: Some(0),
            code: "journal".into(),
            detail: detail.into(),
        };
        let failure = PartialFailure {
            kind: fault.kind,
            step: 0,
            prompt: legacy.result.prompt.as_ref().map(|p| p.id),
            detail: detail.into(),
        };
        if !same_json(&report.faults, &vec![fault]) || !same_json(&report.failure, &Some(failure)) {
            return Err("initial witness reservation failure differs".into());
        }
    } else if !report.faults.is_empty() || report.failure.is_some() {
        return Err("this execution failure needs its own diagnostic proof".into());
    }
    let start_audit = report.start_call + report.choices.len();
    if let Some(error) = error {
        if journal
            .checkpoint_consumed(
                error
                    .checkpoint
                    .as_deref()
                    .ok_or("audit checkpoint missing")?,
            )
            .map_err(|e| e.message)?
            != Some(start_audit)
        {
            return Err("audit did not start after the recorded execution attempts".into());
        }
    }
    let prefix = if let Some(error) = error {
        if error.completed_witnesses == 0 {
            None
        } else {
            let index = error.completed_witnesses - 1;
            let witness = report
                .queries
                .get(index)
                .ok_or("audit progress outside queries")?;
            let call = *error
                .call_ids
                .get(index)
                .ok_or("audit progress outside calls")?;
            let mut q = report.request.clone();
            q.decisions.retain(|d| d.prompt_id < witness.event);
            Some(AuditedPrefix {
                result: journal
                    .load_result(call, &q)
                    .map_err(|e| e.message)?
                    .ok_or("missing audited prefix")?,
                request: q,
                witness_call: call,
            })
        }
    } else {
        Some(AuditedPrefix {
            request: report.request.clone(),
            result: legacy.result.clone(),
            witness_call: *report
                .audit_calls
                .last()
                .ok_or("missing complete root replay")?,
        })
    };
    if !same_json(&prefix, &report.last_audited_prefix) {
        return Err("last audited prefix differs".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::first_turn::execution::ExecutionStage;
    use crate::first_turn::{ForecastPlan, SearchLimits};
    use std::sync::Arc;
    use ygo_engine_adapter::{
        Checkpoint, DuelResult, DuelStatus, EngineAdapter, RunDuelRequest, WorkerError,
    };
    use ygo_goal::{evaluate, Facts};
    use ygo_knowledge::first_turn::FirstTurnKnowledge;

    struct Fixed(Result<DuelResult, WorkerError>);
    impl EngineAdapter for Fixed {
        fn doctor(&self) -> ygo_engine_adapter::DoctorReport {
            panic!("diagnostic validation must not run doctor")
        }
        fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
            self.0.clone()
        }
    }

    fn request() -> RunDuelRequest {
        let portable: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
        ))
        .unwrap();
        serde_json::from_value(portable["cases"][0]["runtime_request"].clone()).unwrap()
    }

    fn goal() -> ygo_goal::Goal {
        serde_json::from_value(serde_json::json!({
            "version": 1,
            "expr": {"op": "count", "filter": {}, "min": 1}
        }))
        .unwrap()
    }

    fn make_report(
        outcome: Result<DuelResult, WorkerError>,
    ) -> (
        PartialExecutionV2,
        Arc<CallJournal>,
        ForecastPlan,
        FirstTurnKnowledge,
        ygo_goal::Goal,
        ygo_domain::Catalog,
    ) {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let goal = goal();
        let plan = ForecastPlan {
            id: "synthetic-plan".into(),
            start_id: "synthetic-start".into(),
            knowledge_id: pack.id(),
            limits: SearchLimits::default(),
            goal_id: goal.id(),
            first_sensitive: None,
            steps: vec![],
            predicted_goal: evaluate(&goal.expr, &Facts::default(), &Default::default()),
            predicted_resources: 0,
        };
        let request = request();
        let root = std::env::temp_dir().join(format!(
            "ygo-a1-initial-diagnostic-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).unwrap();
        let journal =
            CallJournal::open(root.join("calls.jsonl"), "a1-synthetic", &pack.id(), 4).unwrap();
        let mut outcome = outcome;
        if let Ok(result) = &mut outcome {
            result.versions = request.versions.clone();
        }
        let report = super::super::start_partial_v2_with_backend(
            &request,
            &plan,
            &Default::default(),
            &pack,
            &goal,
            journal.clone(),
            Fixed(outcome),
        )
        .unwrap();
        (report, journal, plan, pack, goal, Default::default())
    }

    #[test]
    fn validates_charged_initial_result_level_error_without_trusting_a_prefix() {
        let result = DuelResult {
            protocol_version: 2,
            status: DuelStatus::Failed,
            events: vec![],
            prompt: None,
            checkpoint: Checkpoint::default(),
            error: Some(WorkerError::new(
                "engine_rejected",
                "execution",
                "controlled failure",
            )),
            versions: RuntimeVersions::default(),
            loaded_scripts: Default::default(),
            steps: vec![],
            resolved_decisions: vec![],
            coverage_gaps: vec![],
            peak_working_set_bytes: None,
            terminal_observation: None,
        };
        let (report, journal, plan, pack, goal, catalog) = make_report(Ok(result));
        validate_partial_execution_v2(&report, &plan, &catalog, &pack, &goal, &journal).unwrap();
        assert_eq!(journal.stats().unwrap().consumed, 1);
        assert!(report.queries.is_empty());
        assert!(report.last_audited_prefix.is_none());
        assert!(report.receipt.is_none());
        assert!(!report.verified());
        let mut forged: PartialExecutionV2 =
            serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.queries.push(ygo_goal::QueryWitness {
            event: 1,
            raw_prefix_sha256: "0".repeat(64),
            decisions_sha256: "0".repeat(64),
            public: ygo_engine_adapter::first_turn_public_state(&Checkpoint::default()),
        });
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
        forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.last_audited_prefix = Some(AuditedPrefix {
            request: report.start_request.clone(),
            result: report.last_result.clone().unwrap(),
            witness_call: 1,
        });
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
        let mut forged: PartialExecutionV2 =
            serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.faults[0].code = "invented_error".into();
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
        forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged
            .last_result
            .as_mut()
            .unwrap()
            .error
            .as_mut()
            .unwrap()
            .message = "forged".into();
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
        forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.initial_attempt_checkpoint = None;
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
    }

    #[test]
    fn validates_charged_initial_query_capture_failure_without_trusting_a_prefix() {
        let result = DuelResult {
            protocol_version: 2,
            status: DuelStatus::DecisionRequired,
            events: vec![],
            prompt: None,
            checkpoint: Checkpoint::default(),
            error: None,
            versions: RuntimeVersions::default(),
            loaded_scripts: Default::default(),
            steps: vec![],
            resolved_decisions: vec![],
            coverage_gaps: vec![],
            peak_working_set_bytes: None,
            terminal_observation: None,
        };
        let (report, journal, plan, pack, goal, catalog) = make_report(Ok(result));
        validate_partial_execution_v2(&report, &plan, &catalog, &pack, &goal, &journal).unwrap();
        assert_eq!(journal.stats().unwrap().consumed, 1);
        assert!(report.queries.is_empty());
        assert!(report.last_audited_prefix.is_none());
        assert!(report.receipt.is_none());
        assert!(!report.verified());
        let mut forged: PartialExecutionV2 =
            serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.faults[0].stage = ExecutionStage::Execution;
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
        forged = serde_json::from_value(serde_json::to_value(&report).unwrap()).unwrap();
        forged.calls = 0;
        assert!(
            validate_partial_execution_v2(&forged, &plan, &catalog, &pack, &goal, &journal)
                .is_err()
        );
    }
}
