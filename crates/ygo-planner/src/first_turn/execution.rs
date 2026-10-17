//! Internal vertical integration. This is not the fully certified v6 API.
use super::*;
use std::sync::Arc;
use ygo_engine_adapter::*;
use ygo_goal::{actual_trace_v6, verify_query_replays, Goal, QueryWitness, TraceWindow};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PartialDecisionEvidence {
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
fn validate_raw_choice(result: &DuelResult, choice: &Choice) -> Result<u64, String> {
    let frame = result.events.last().ok_or("missing actual raw prompt")?;
    let parsed = parse_prompt(frame.sequence, &frame.raw)?.ok_or("unsupported actual prompt")?;
    if !parsed.actions.iter().any(|a| &a.choice == choice)
        || parsed.player != 0
        || serde_json::to_value(&parsed).unwrap() != serde_json::to_value(&result.prompt).unwrap()
    {
        return Err("choice does not match actual legal raw prompt".into());
    }
    Ok(parsed.id)
}
fn persist_choice(
    journal: &CallJournal,
    plan: &str,
    result: &DuelResult,
    step: Option<usize>,
    choice: Choice,
    map: &BTreeMap<String, String>,
    used: &BTreeSet<usize>,
) -> Result<PartialDecisionEvidence, String> {
    let prompt = validate_raw_choice(result, &choice)?;
    let evidence = PartialDecisionEvidence {
        before_call: journal.stats().map_err(|e| e.message)?.consumed as u64 + 1,
        step,
        prompt,
        prefix_id: prefix_id(result),
        public: first_turn_public_state(&result.checkpoint),
        choice,
        instance_map: map.clone(),
        used_roles: used.clone(),
    };
    journal
        .save_checkpoint(
            &choice_checkpoint(plan, prompt),
            &serde_json::to_value(&evidence).unwrap(),
        )
        .map_err(|e| e.message)?;
    Ok(evidence)
}
pub fn validate_choice_checkpoint(
    evidence: &PartialDecisionEvidence,
    plan: &str,
    before: &DuelResult,
    journal: &CallJournal,
) -> Result<(), String> {
    let name = choice_checkpoint(plan, evidence.prompt);
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
        || report.plan_id != plan.id
        || !same_json(&expected_request, &report.request)
        || report.scope != "partial_integration_native_execution; not full rule certification"
        || report.calls != report.choices.len() + report.audit_calls.len()
        || report.audit_calls.len() != report.queries.len() + 1
        || report.start_call + report.calls > 512
        || journal.stats().map_err(|e| e.message)?.limit != 512
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
            if !same_json(&QueryWitness::capture(&r)?, witness) {
                return Err("independent query content differs".into());
            }
        } else {
            let r = journal
                .load_result(*call, &q)
                .map_err(|e| e.message)?
                .ok_or("root replay missing")?;
            if !same_native(&r, &report.result) {
                return Err("independent complete replay differs".into());
            }
        }
    }
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
            .ok_or("prediction has no executed choice")?;
        let first_choice = &report.choices[i];
        let before = &results[i];
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
        let name = format!("partial-{}-prediction-{index}", plan.id);
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
    if let Some(failure) = &report.failure {
        if failure.prompt != report.result.prompt.as_ref().map(|p| p.id) {
            return Err("failure does not reference its actual stopped prompt".into());
        }
        match failure.kind {
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
struct Runner {
    adapter: JournaledAdapter<ProcessEngineAdapter>,
    journal: Arc<CallJournal>,
    held: Vec<String>,
    queries: Vec<QueryWitness>,
    base: usize,
}
impl Runner {
    fn run(&mut self, q: &RunDuelRequest) -> Result<DuelResult, String> {
        let token = format!(
            "partial-query-{}-{}",
            self.base,
            self.journal.stats().map_err(|e| e.message)?.consumed
        );
        self.journal
            .reserve(&token, 1)
            .map_err(|e| format!("budget_exhausted: {}", e.message))?;
        match self.adapter.run(q) {
            Ok(result) => {
                if result.prompt.is_some() && result.error.is_none() {
                    self.queries.push(QueryWitness::capture(&result)?);
                    self.held.push(token);
                } else {
                    self.journal.release(&token).map_err(|e| e.message)?;
                }
                Ok(result)
            }
            Err(error) => {
                self.journal.release(&token).map_err(|e| e.message)?;
                Err(format!("engine_failure: {}", error.message))
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
    request.validate_protocol()?;
    goal.validate()?;
    pack.validate()?;
    if request.protocol_version != 6
        || request.versions != initial.versions
        || plan.goal_id != goal.id()
        || plan.steps.len() > 64
    {
        return Err("partial execution input/profile/goal mismatch".into());
    }
    let actual_start = observed(initial, queries, cat, pack)?;
    validate_forecast(plan, &actual_start.state, cat, pack, goal)?;
    let base = journal.stats().map_err(|e| e.message)?.consumed;
    let charged_start = journal
        .load_result(base as u64, request)
        .map_err(|e| e.message)?
        .ok_or("initial native call is not completed")?;
    if !same_native(&charged_start, initial) {
        return Err("initial result differs from charged call".into());
    }
    let held = format!("partial-witness-{base}");
    journal
        .reserve(&held, queries.len() + 1)
        .map_err(|e| e.message)?;
    let mut runner = Runner {
        adapter: JournaledAdapter::new(
            ProcessEngineAdapter::new(request.engine.clone()),
            journal.clone(),
            CallPurpose::Execution,
        ),
        journal: journal.clone(),
        held: vec![held],
        queries: queries.to_vec(),
        base,
    };
    let mut q = request.clone();
    let mut result = initial.clone();
    let mut predictions = vec![];
    let mut choices = vec![];
    let mut map = BTreeMap::new();
    let mut failure = None;
    let mut interruption = None;
    let mut current_step = 0;
    let mut identity_gaps = vec![];
    let execution = (|| -> Result<(), String> {
        let start = observed(&result, &runner.queries, cat, pack)?;
        for c in &start.state.cards {
            map.insert(c.id.clone(), c.id.clone());
        }
        for (index, planned) in plan.steps.iter().enumerate() {
            current_step = index;
            let before = observed(&result, &runner.queries, cat, pack)?;
            let unknown = required_instances_unknown(planned, &before.state, &map);
            if !unknown.is_empty() {
                return Err(format!("required_instance_unknown: {}", unknown.join(",")));
            }
            let options = successors(&before.state, cat, pack);
            let step = options
                .transitions
                .iter()
                .find(|t| same_action(planned, t, &map))
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
            let trigger = before.state.pending.iter().any(|p| {
                p.rule_id == step.rule_id && p.source == step.source && p.eligibility == Truth::Yes
            });
            let rule = pack.rule(&step.rule_id).ok_or("missing rule")?;
            let mut choice = bind_start(&result, &source.card, rule, step.kind, trigger)?;
            let mut used = BTreeSet::new();
            let mut started = false;
            let entry = PartialPrediction {
                step: index,
                before_call: journal.stats().map_err(|e| e.message)?.consumed as u64 + 1,
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
            journal
                .save_checkpoint(
                    &format!("partial-{}-prediction-{index}", plan.id),
                    &serde_json::to_value(&entry).unwrap(),
                )
                .map_err(|e| e.message)?;
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
                    return Err("engine raw prefix changed".into());
                }
                result = next;
                if let Some(error) = &result.error {
                    return Err(format!("engine_failure: {}", error.message));
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
                    let after = observed(&result, &runner.queries, cat, pack)?;
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
                        let anchor_state = actual_state(&result, &runner.queries, cat, pack)?;
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
                        return Err(format!(
                            "{}: {}: {}",
                            "prediction_mismatch",
                            step.rule_id,
                            differences.join("; ")
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
                return Err("coverage_gap: unmodeled end phase processing".into());
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
                return Err("engine_failure during end processing".into());
            }
        }
        Err("end processing step budget".into())
    })();
    if let Err(error) = execution {
        let kind = if error.starts_with("original_plan_blocked:") {
            PartialFailureKind::OriginalPlanBlocked
        } else if error.starts_with("required_instance_unknown:")
            || error.contains("identity unknown")
            || error.contains("unbound planned instance")
        {
            PartialFailureKind::RequiredInstanceUnknown
        } else if error.starts_with("prediction_mismatch:") {
            PartialFailureKind::PredictionMismatch
        } else if error.starts_with("budget_exhausted:") {
            PartialFailureKind::BudgetExhausted
        } else if error.starts_with("engine_failure") {
            PartialFailureKind::EngineFailure
        } else if error.starts_with("coverage_gap:") || error.contains("unknown") {
            PartialFailureKind::CoverageGap
        } else {
            PartialFailureKind::PromptBindingFailed
        };
        failure = Some(PartialFailure {
            kind,
            step: current_step,
            prompt: result.prompt.as_ref().map(|p| p.id),
            detail: error,
        });
    }
    q.decisions = result.resolved_decisions.clone();
    runner.release()?;
    let audit = verify_query_replays(&q, &result, &runner.queries, journal.clone())?;
    let actual = actual_trace_v6(&result, cat, pack, &runner.queries)?;
    let terminal = actual.window == TraceWindow::OwnTurnEnded;
    let evaluation = ygo_goal::evaluate(&goal.expr, &actual.facts, &Default::default());
    if failure.is_none() && (!terminal || evaluation.result != ygo_goal::Truth::Yes) {
        failure = Some(PartialFailure {
            kind: PartialFailureKind::BoundedRecoveryNotFound,
            step: plan.steps.len(),
            prompt: result.prompt.as_ref().map(|p| p.id),
            detail: "bounded goal not met".into(),
        });
    }
    identity_gaps.sort();
    identity_gaps.dedup();
    Ok(PartialExecution {
        schema_version: 1,
        scope: "partial_integration_native_execution; not full rule certification".into(),
        plan_id: plan.id.clone(),
        request: q,
        start_request: request.clone(),
        start_call: base,
        result,
        queries: runner.queries,
        predictions,
        choices,
        failure,
        interruption,
        terminal,
        goal: evaluation,
        audit_calls: audit.call_ids,
        calls: journal.stats().map_err(|e| e.message)?.consumed - base,
        identity_gaps,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
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
