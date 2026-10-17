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
        return Err(
            "initial failure intent cannot be attached to a completed initial state".into(),
        );
    }
    if report.audit_failure.is_none() && !report.faults.iter().any(|f| f.call.is_some()) {
        return validate_completed_capture(report, plan, cat, pack, goal, journal);
    }
    validate_failed_audit_capture(report, plan, cat, pack, goal, journal)
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
        let budget = journal
            .checkpoint_budget(key)
            .map_err(|e| e.message)?
            .ok_or("missing initial attempt budget")?;
        let intent = initial_attempt_intent(&report.start_request, &report.plan_id, &budget);
        if *key
            != format!(
                "immutable/partial-start/{}",
                ygo_knowledge::hash(&serde_json::to_vec(&intent).unwrap())
            )
            || journal.checkpoint(key).map_err(|e| e.message)? != Some(intent)
            || report.start_call != budget.consumed
        {
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
