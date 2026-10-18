use crate::{Proposals, Resource, SemanticStep, StepKind, SymbolicState};
use serde::{Deserialize, Serialize};
use std::{collections::BTreeMap, time::Instant};
use ygo_engine_adapter::*;
use ygo_knowledge::{KnowledgePack, Rule};
use ygo_search::combo::*;
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Prediction {
    pub semantic_step: usize,
    pub effect_id: String,
    pub reason: String,
    pub before_prefix: String,
    pub before_events: usize,
    pub before_checkpoint: Checkpoint,
    pub alternatives: Vec<ActionMetadata>,
    pub comparisons: Vec<AlternativeReason>,
    pub selected: Decision,
    pub after_events: usize,
    pub outcome: String,
}
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
pub struct AlternativeReason {
    pub choice: Choice,
    pub selected: bool,
    pub reasons: Vec<String>,
    pub consumer_effects: Vec<String>,
}
pub fn assess_alternatives(
    proposal: &crate::Proposal,
    index: usize,
    alternatives: &[ActionMetadata],
    selected: &Choice,
    pack: &KnowledgePack,
) -> Vec<AlternativeReason> {
    alternatives.iter().map(|m| {
        let chosen=&m.choice==selected;let mut reasons=vec![];let mut consumers=vec![];
        if let Some(step)=proposal.steps.get(index) {
            for card in &m.selected {
                let planned=step.costs.iter().chain(&step.targets).find(|r|r.code==card.code && r.location==card.location);
                if let Some(resource)=planned {
                    if let Some(after)=step.after.cards.iter().find(|r|r.instance==resource.instance) {reasons.push(format!("本方案将 {} 从区域 {} 转为区域 {} 的资源；实例由位置和提示索引绑定。",resource.code,resource.location,after.location));}
                    consumers.extend(proposal.steps[index+1..].iter().filter(|next|next.source.instance==resource.instance || next.costs.iter().any(|r|r.instance==resource.instance)).map(|next|next.effect_id.clone()));
                } else {
                    let future:Vec<_>=proposal.steps[index+1..].iter().filter(|next|next.source.code==card.code || next.costs.iter().any(|r|r.code==card.code)).map(|s|s.effect_id.clone()).collect();
                    if !future.is_empty() {reasons.push(format!("该卡名资源在本方案后续用于 {}；提前消耗需另行修订方案。",future.join("、")));}
                }
                if let Some(k)=pack.card(card.code) {for e in k.effects.iter().filter(|e|matches!(e.rule,Rule::BootsSearch|Rule::CloakSearch|Rule::GlovesMill|Rule::FogRevive|Rule::GreavesRevive)) {reasons.push(format!("潜在墓地用途 {}：{}；须满足费用、次数和对象条件。",e.id,e.operations.join("；")));}}
            }
            if chosen {reasons.push(format!("符合预先声明的 {} 步骤；收益依据是目标资源链，尚需实际执行验证。",step.effect_id));}
            else {reasons.push("引擎当前允许该选择，但它不属于本方案下一步；未据此判断其全局收益更低。".into());}
        } else {reasons.push(if chosen {"结束回合并验证目标终场"} else {"不在目标完成后的结束回合策略内"}.into());}
        if !consumers.is_empty() {reasons.push(format!("计划中的后续资源使用：{}。",consumers.join("、")));}
        AlternativeReason{choice:m.choice.clone(),selected:chosen,reasons,consumer_effects:consumers}
    }).collect()
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Attempt {
    pub proposal_id: String,
    pub status: String,
    pub goal_achieved: bool,
    pub line_id: Option<String>,
    pub predictions: Vec<Prediction>,
    pub discrepancies: Vec<String>,
    pub grave_resources: Vec<String>,
    pub observation: Option<DuelResult>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PlanningOutput {
    pub goal: String,
    pub proposals: Proposals,
    pub attempts: Vec<Attempt>,
    pub search: SearchReport,
}
pub fn checkpoint_goal(c: &Checkpoint) -> bool {
    c.cards
        .iter()
        .any(|c| c.player == 0 && c.location == 4 && c.code == 26692769)
        && c.cards
            .iter()
            .any(|c| c.player == 0 && c.location == 8 && c.code == 25542642 && c.position & 10 != 0)
}
fn projection_matches(expected: &SymbolicState, actual: &Checkpoint) -> bool {
    let mut a = expected
        .cards
        .iter()
        .filter(|c| matches!(c.location, 2 | 4 | 8 | 16 | 32 | 64))
        .map(|c| (c.code, c.location))
        .collect::<Vec<_>>();
    let mut b = actual
        .cards
        .iter()
        .filter(|c| c.player == 0 && matches!(c.location, 2 | 4 | 8 | 16 | 32 | 64))
        .map(|c| (c.code, c.location))
        .collect::<Vec<_>>();
    a.sort();
    b.sort();
    a == b
}
fn same(a: &CardReference, b: &CardReference) -> bool {
    a.code == b.code && a.player == b.player && a.location == b.location && a.sequence == b.sequence
}
fn matches_resource(
    r: &Resource,
    c: &CardReference,
    map: &BTreeMap<String, CardReference>,
) -> bool {
    r.code == c.code
        && r.location == c.location
        && c.player == 0
        && map.get(&r.instance).map_or(true, |known| same(known, c))
}
fn refresh(map: &mut BTreeMap<String, CardReference>, events: &[CoreEventFrame]) {
    for e in events {
        if e.opcode == 33 {
            let player = e.fields["player"].as_u64().unwrap_or(2) as u8;
            let cards = e.fields["cards"].as_array().cloned().unwrap_or_default();
            let mut counts = BTreeMap::<u32, usize>::new();
            for c in map
                .values()
                .filter(|c| c.location == 2 && c.player == player)
            {
                *counts.entry(c.code).or_default() += 1;
            }
            for c in map
                .values_mut()
                .filter(|c| c.location == 2 && c.player == player)
            {
                let positions: Vec<_> = cards
                    .iter()
                    .enumerate()
                    .filter(|(_, code)| code.as_u64() == Some(c.code as u64))
                    .map(|(i, _)| i as u32)
                    .collect();
                c.sequence = if positions.len() == 1 && counts[&c.code] == 1 {
                    positions[0]
                } else {
                    u32::MAX
                };
            }
            continue;
        }
        if e.opcode != 50 {
            continue;
        }
        let code = e.fields["code"].as_u64().unwrap_or(0) as u32;
        let from = &e.fields["from"];
        let to = &e.fields["to"];
        let moving: Vec<_> = map
            .iter()
            .filter(|(_, m)| {
                m.code == code
                    && from["player"].as_u64() == Some(m.player as u64)
                    && from["location"].as_u64() == Some(m.location as u64)
                    && from["sequence"].as_u64() == Some(m.sequence as u64)
            })
            .map(|(key, _)| key.clone())
            .collect();
        for (key, mapped) in map.iter_mut() {
            if moving.contains(key) {
                mapped.player = to["player"].as_u64().unwrap_or(0) as u8;
                mapped.location = to["location"].as_u64().unwrap_or(0) as u8;
                mapped.sequence = to["sequence"].as_u64().unwrap_or(0) as u32;
                mapped.position = to["position"].as_u64().unwrap_or(0) as u32;
            } else if mapped.sequence != u32::MAX
                && matches!(mapped.location, 1 | 2 | 16 | 32 | 64)
                && from["player"].as_u64() == Some(mapped.player as u64)
                && from["location"].as_u64() == Some(mapped.location as u64)
                && from["sequence"]
                    .as_u64()
                    .is_some_and(|n| n < mapped.sequence as u64)
            {
                mapped.sequence -= 1;
            }
        }
    }
}

fn primary(
    step: &SemanticStep,
    m: &ActionMetadata,
    pack: &KnowledgePack,
    map: &BTreeMap<String, CardReference>,
) -> bool {
    let source_ok = m
        .source
        .as_ref()
        .is_some_and(|c| matches_resource(&step.source, c, map));
    if !source_ok {
        return false;
    }
    match step.kind {
        StepKind::NormalSummon => matches!(m.choice, Choice::Command { command: 0, .. }),
        StepKind::SpecialSummon | StepKind::LinkSummon => {
            matches!(m.choice, Choice::Command { command: 1, .. })
        }
        StepKind::Set => matches!(m.choice, Choice::Command { command: 4, .. }),
        StepKind::Activate | StepKind::Trigger => {
            let Some(e) = pack.effect(&step.effect_id) else {
                return false;
            };
            let desc = e
                .description_index
                .map(|i| ((step.source.code as u64) << 20) + i);
            let desc_ok = m.effect_description == desc
                || (m.effect_description == Some(0)
                    && matches!(e.rule, Rule::Rota | Rule::Fool | Rule::Brigandine));
            (desc_ok
                || (step.kind == StepKind::Trigger
                    && e.trigger.is_some()
                    && matches!(m.choice, Choice::YesNo { yes: true })))
                && matches!(
                    m.choice,
                    Choice::Command { command: 5, .. }
                        | Choice::Chain { index: Some(_) }
                        | Choice::YesNo { yes: true }
                )
        }
        StepKind::EndTurn => false,
    }
}
fn choose(
    step: &SemanticStep,
    started: bool,
    wanted: &[Resource],
    metadata: &[ActionMetadata],
    pack: &KnowledgePack,
    map: &BTreeMap<String, CardReference>,
) -> Option<ActionMetadata> {
    if !started {
        return metadata
            .iter()
            .find(|m| primary(step, m, pack, map))
            .cloned();
    }
    if let Some(m) = metadata.iter().find(|m| {
        !m.selected.is_empty()
            && m.selection_group != Some(1)
            && m.selected
                .iter()
                .all(|c| wanted.iter().any(|r| matches_resource(r, c, map)))
    }) {
        return Some(m.clone());
    }
    // Zone/position choices have no resource conversion; choose a deterministic legal placement.
    if let Some(m) = metadata.iter().find(|m| {
        matches!(
            m.choice,
            Choice::Place { .. } | Choice::Position { position: 1 }
        )
    }) {
        return Some(m.clone());
    }
    if let Some(e) = pack.effect(&step.effect_id) {
        if let Some(index) = e.description_index {
            if let Some(m) = metadata.iter().find(|m| {
                matches!(m.choice, Choice::Option { .. })
                    && m.effect_description == Some(((step.source.code as u64) << 20) + index)
            }) {
                return Some(m.clone());
            }
        }
    }
    metadata
        .iter()
        .find(|m| {
            matches!(
                m.choice,
                Choice::Finish | Choice::Chain { index: None } | Choice::YesNo { yes: false }
            )
        })
        .cloned()
}
fn run<A: EngineAdapter>(
    adapter: &A,
    request: &RunDuelRequest,
    budget: &SearchBudget,
    start: Instant,
    stats: &mut SearchStats,
) -> Result<DuelResult, WorkerError> {
    let left = budget
        .time_limit_ms
        .saturating_sub(start.elapsed().as_millis() as u64);
    if stats.nodes >= budget.node_budget || left == 0 {
        return Err(WorkerError::new(
            "planner_budget",
            "planning",
            "shared execution/replay budget exhausted",
        ));
    }
    let mut q = request.clone();
    q.engine.timeout_ms = q.engine.timeout_ms.min(left);
    stats.nodes += 1;
    stats.engine_calls += 1;
    let result = adapter.run(&q)?;
    stats.worker_peak_working_set_bytes = stats
        .worker_peak_working_set_bytes
        .max(result.peak_working_set_bytes);
    Ok(result)
}
pub fn execute<A: EngineAdapter>(
    adapter: &A,
    request: &RunDuelRequest,
    proposals: Proposals,
    budget: &SearchBudget,
    weights: &ScoringConfig,
    pack: &KnowledgePack,
) -> Result<PlanningOutput, String> {
    budget.validate()?;
    pack.validate()?;
    if !request.decisions.is_empty() || request.probe_only || request.protocol_version != 2 {
        return Err("planning requires a fresh protocol v2 duel".into());
    }
    if proposals.plans.len() > 8
        || proposals
            .plans
            .iter()
            .any(|p| p.steps.is_empty() || p.steps.len() > 32)
    {
        return Err("invalid proposal limits".into());
    }
    let start = Instant::now();
    let mut stats = SearchStats::default();
    let mut lines = vec![];
    let mut attempts = vec![];
    let mut diagnostics = vec![];
    let mut termination = if proposals.plans.is_empty() {
        "no_symbolic_plan"
    } else {
        "proposals_exhausted"
    }
    .to_string();
    for proposal in &proposals.plans {
        let mut attempt = Attempt {
            proposal_id: proposal.id.clone(),
            status: "unverified".into(),
            goal_achieved: false,
            line_id: None,
            predictions: vec![],
            discrepancies: vec![],
            grave_resources: vec![],
            observation: None,
        };
        let mut q = request.clone();
        let mut map = BTreeMap::new();
        let mut result = match run(adapter, &q, budget, start, &mut stats) {
            Ok(r) => r,
            Err(e) => {
                diagnostics.push(e);
                termination = "execution_budget_or_failure".into();
                break;
            }
        };
        q.decisions = result.resolved_decisions.clone();
        let mut step_index = 0;
        let mut started = false;
        let mut wanted = vec![];
        loop {
            if result.status == DuelStatus::Failed {
                attempt
                    .discrepancies
                    .push(format!("engine failure: {:?}", result.error));
                break;
            }
            let Some(prompt) = result.prompt.as_ref() else {
                if step_index >= proposal.steps.len()
                    && result.status == DuelStatus::EngineVerified
                    && checkpoint_goal(&result.checkpoint)
                {
                    let replay_start = Instant::now();
                    match run(adapter, &q, budget, start, &mut stats) {
                        Ok(replayed)
                            if replayed.status == result.status
                                && replayed.checkpoint == result.checkpoint
                                && replayed.events == result.events
                                && replayed.steps == result.steps
                                && replayed.loaded_scripts == result.loaded_scripts
                                && replayed.resolved_decisions == q.decisions =>
                        {
                            let id = prefix_key(&q);
                            attempt.line_id = Some(id.clone());
                            attempt.goal_achieved = true;
                            attempt.status = "engine_verified".into();
                            attempt.grave_resources=result.checkpoint.cards.iter().filter(|c|c.player==0 && c.location==16 && pack.card(c.code).is_some()).map(|c|format!("{} 墓地资源：可用性取决于费用、次数和目标，不计为已验证互动",c.code)).collect();
                            if !lines.iter().any(|l: &ComboLine| l.id == id) {
                                lines.push(ComboLine {
                                    id,
                                    decisions: q.decisions.clone(),
                                    evaluation: evaluate(
                                        &result.checkpoint,
                                        q.decisions.len(),
                                        weights,
                                    ),
                                    result: result.clone(),
                                    replay_verified: true,
                                });
                            }
                        }
                        Ok(_) => attempt
                            .discrepancies
                            .push("independent replay mismatch".into()),
                        Err(e) => {
                            attempt.discrepancies.push(e.message.clone());
                            diagnostics.push(e);
                        }
                    }
                    stats.replay_ms += replay_start.elapsed().as_millis() as u64;
                } else {
                    attempt.discrepancies.push(format!(
                        "incomplete/partial goal verification: {:?}, step {step_index}",
                        result.status
                    ));
                }
                break;
            };
            let raw = result
                .events
                .iter()
                .find(|e| e.sequence == prompt.id)
                .ok_or("missing raw prompt provenance")?;
            let metadata = prompt_metadata(prompt.id, &raw.raw)?;
            if step_index < proposal.steps.len()
                && started
                && projection_matches(&proposal.steps[step_index].after, &result.checkpoint)
            {
                let next = proposal.steps.get(step_index + 1);
                let trigger_ready = next.is_some_and(|s| {
                    s.kind == StepKind::Trigger
                        && metadata.iter().any(|m| primary(s, m, pack, &map))
                });
                if prompt.opcode == 11 || trigger_ready {
                    step_index += 1;
                    started = false;
                    wanted.clear();
                }
            }
            if q.decisions.len() >= budget.max_depth {
                attempt
                    .discrepancies
                    .push("decision depth budget exhausted".into());
                break;
            }
            let selected = if let Some(step) = proposal.steps.get(step_index) {
                if !started {
                    wanted = step
                        .costs
                        .iter()
                        .chain(&step.targets)
                        .filter(|r| r.instance != step.source.instance || r.location == 4)
                        .cloned()
                        .collect();
                }
                choose(step, started, &wanted, &metadata, pack, &map)
            } else {
                metadata
                    .iter()
                    .find(|m| {
                        matches!(
                            m.choice,
                            Choice::Command { command: 7, .. }
                                | Choice::Chain { index: None }
                                | Choice::YesNo { yes: false }
                                | Choice::Finish
                        )
                    })
                    .cloned()
            };
            let Some(selected) = selected else {
                attempt.discrepancies.push(format!("unbound prompt {} opcode {} at semantic step {step_index} ({:?}); prediction stopped; alternatives={:?}",prompt.id,prompt.opcode,proposal.steps.get(step_index).map(|s|(&s.effect_id,&s.source)),metadata));
                break;
            };
            if let Some(step) = proposal.steps.get(step_index) {
                if !started {
                    if let Some(source) = &selected.source {
                        map.insert(step.source.instance.clone(), source.clone());
                    }
                    started = true;
                }
                for c in &selected.selected {
                    if let Some(i) = wanted.iter().position(|r| matches_resource(r, c, &map)) {
                        let resource = wanted.remove(i);
                        map.insert(resource.instance, c.clone());
                    }
                }
            }
            let decision = Decision {
                prompt_id: prompt.id,
                player: prompt.player,
                choice: selected.choice,
            };
            let comparisons =
                assess_alternatives(proposal, step_index, &metadata, &decision.choice, pack);
            // Append the prediction before invoking the next engine execution.
            attempt.predictions.push(Prediction {
                semantic_step: step_index,
                effect_id: proposal
                    .steps
                    .get(step_index)
                    .map_or("system:end_turn", |s| s.effect_id.as_str())
                    .into(),
                reason: proposal.steps.get(step_index).map_or(
                    "目标已预测完成；结束回合并验证终场".into(),
                    |s| s.reason.clone(),
                ),
                before_prefix: prefix_key(&q),
                before_events: result.events.len(),
                before_checkpoint: result.checkpoint.clone(),
                alternatives: metadata,
                comparisons,
                selected: decision.clone(),
                after_events: result.events.len(),
                outcome: "unobserved".into(),
            });
            q.decisions.push(decision);
            let old_events = result.events.len();
            match run(adapter, &q, budget, start, &mut stats) {
                Ok(next) => {
                    if !next
                        .resolved_decisions
                        .iter()
                        .any(|d| d == &attempt.predictions.last().unwrap().selected)
                    {
                        attempt.discrepancies.push(format!(
                            "worker did not confirm the selected decision: {:?}",
                            next.error
                        ));
                        break;
                    }
                    refresh(&mut map, next.events.get(old_events..).unwrap_or(&[]));
                    q.decisions = next.resolved_decisions.clone();
                    attempt.predictions.last_mut().unwrap().after_events = next.events.len();
                    attempt.predictions.last_mut().unwrap().outcome = "observed".into();
                    result = next;
                }
                Err(e) => {
                    attempt.discrepancies.push(e.message.clone());
                    diagnostics.push(e);
                    termination = "execution_budget_or_failure".into();
                    break;
                }
            }
            stats.max_decision_depth = stats.max_decision_depth.max(q.decisions.len());
        }
        attempt.observation = Some(result);
        if !attempt.goal_achieved {
            attempt.status = "prediction_rejected".into();
            stats.failed_branches += 1;
        }
        attempts.push(attempt);
        if lines.len() >= budget.top_k {
            termination = "top_k".into();
            break;
        }
        if stats.nodes >= budget.node_budget
            || start.elapsed().as_millis() as u64 >= budget.time_limit_ms
        {
            termination = "execution_budget".into();
            break;
        }
    }
    lines.sort_by(|a, b| {
        let resources = |l: &ComboLine| {
            l.result
                .checkpoint
                .cards
                .iter()
                .filter(|c| c.player == 0 && matches!(c.location, 2 | 4 | 8))
                .count()
        };
        resources(b)
            .cmp(&resources(a))
            .then_with(|| a.decisions.len().cmp(&b.decisions.len()))
            .then_with(|| a.id.cmp(&b.id))
    });
    stats.completed_lines = lines.len();
    stats.elapsed_ms = start.elapsed().as_millis() as u64;
    Ok(PlanningOutput {
        goal: "rusty-fog".into(),
        proposals,
        attempts,
        search: SearchReport {
            termination,
            lines,
            stats,
            diagnostics,
            scoring: weights.clone(),
            budget: budget.clone(),
        },
    })
}

/// Reconstruct the binder from recorded pre-execution facts and raw metadata.
/// Checking a reason's text alone would allow a real action to be relabelled as another step.
pub fn validate_bindings(
    proposal: &crate::Proposal,
    attempt: &Attempt,
    pack: &KnowledgePack,
) -> Result<(), String> {
    let observation = attempt
        .observation
        .as_ref()
        .ok_or("missing binding observation")?;
    let mut map = BTreeMap::new();
    let mut index = 0;
    let mut started = false;
    let mut wanted = vec![];
    for prediction in &attempt.predictions {
        if index < proposal.steps.len()
            && started
            && projection_matches(&proposal.steps[index].after, &prediction.before_checkpoint)
        {
            let next = proposal.steps.get(index + 1);
            let frame = observation
                .events
                .iter()
                .find(|e| e.sequence == prediction.selected.prompt_id)
                .ok_or("missing binding frame")?;
            let trigger = next.is_some_and(|s| {
                s.kind == StepKind::Trigger
                    && prediction
                        .alternatives
                        .iter()
                        .any(|m| primary(s, m, pack, &map))
            });
            if frame.opcode == 11 || trigger {
                index += 1;
                started = false;
                wanted.clear();
            }
        }
        if prediction.semantic_step != index {
            return Err("semantic step progression mismatch".into());
        }
        let chosen = if let Some(step) = proposal.steps.get(index) {
            if !started {
                wanted = step
                    .costs
                    .iter()
                    .chain(&step.targets)
                    .filter(|r| r.instance != step.source.instance || r.location == 4)
                    .cloned()
                    .collect();
            }
            choose(step, started, &wanted, &prediction.alternatives, pack, &map)
        } else {
            prediction
                .alternatives
                .iter()
                .find(|m| {
                    matches!(
                        m.choice,
                        Choice::Command { command: 7, .. }
                            | Choice::Chain { index: None }
                            | Choice::YesNo { yes: false }
                            | Choice::Finish
                    )
                })
                .cloned()
        };
        let chosen = chosen.ok_or("recorded action cannot bind the semantic step")?;
        if chosen.choice != prediction.selected.choice {
            return Err("selected action/semantic binding mismatch".into());
        }
        if let Some(step) = proposal.steps.get(index) {
            if !started {
                if let Some(source) = &chosen.source {
                    map.insert(step.source.instance.clone(), source.clone());
                }
                started = true;
            }
            for c in &chosen.selected {
                if let Some(i) = wanted.iter().position(|r| matches_resource(r, c, &map)) {
                    let resource = wanted.remove(i);
                    map.insert(resource.instance, c.clone());
                }
            }
        }
        refresh(
            &mut map,
            observation
                .events
                .get(prediction.before_events..prediction.after_events)
                .ok_or("invalid binding event range")?,
        );
    }
    if attempt.goal_achieved && index != proposal.steps.len() {
        return Err("semantic plan did not complete".into());
    }
    Ok(())
}

#[cfg(test)]
mod regression {
    use super::*;
    #[test]
    fn hand_shuffle_rebinds_unique_cards_and_marks_duplicates_ambiguous() {
        let mut map = BTreeMap::new();
        map.insert(
            "boots".into(),
            CardReference {
                code: 36426778,
                player: 0,
                location: 2,
                sequence: 3,
                position: 1,
            },
        );
        let mut raw = vec![33, 0];
        raw.extend(2u32.to_le_bytes());
        raw.extend(1u32.to_le_bytes());
        raw.extend(36426778u32.to_le_bytes());
        let frame = decode_frame(1, &raw).unwrap();
        refresh(&mut map, &[frame]);
        assert_eq!(map["boots"].sequence, 1);
        let mut raw = vec![33, 0];
        raw.extend(2u32.to_le_bytes());
        raw.extend(36426778u32.to_le_bytes());
        raw.extend(36426778u32.to_le_bytes());
        refresh(&mut map, &[decode_frame(2, &raw).unwrap()]);
        assert_eq!(map["boots"].sequence, u32::MAX);
    }
}
