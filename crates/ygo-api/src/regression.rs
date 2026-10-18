//! Fixed hands and human-authored reference recipes, separate from planner proposals.
use crate::verification::{equivalent, matches, neutral, Instruction};
use serde::{Deserialize, Serialize};
use ygo_engine_adapter::*;
use ygo_knowledge::KnowledgePack;
use ygo_storage::SnapshotStore;
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Sample {
    pub id: String,
    pub group: String,
    pub request: crate::planning_v2::PlanRequest,
    pub baseline: Vec<Instruction>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Samples {
    pub schema_version: u16,
    pub samples: Vec<Sample>,
}
pub fn run(
    samples: Samples,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog: &str,
    pack: KnowledgePack,
) -> Result<serde_json::Value, String> {
    if samples.schema_version != 1 || samples.samples.len() != 16 {
        return Err("requires the fixed16 suite".into());
    }
    let mut results = vec![];
    let mut ids = std::collections::BTreeSet::new();
    for sample in samples.samples {
        if !ids.insert(sample.id.clone()) {
            return Err("duplicate sample id".into());
        }
        let reference = if !sample.baseline.is_empty() {
            Some(baseline(
                &sample.request,
                &sample.baseline,
                engine.clone(),
                store,
                catalog,
            )?)
        } else {
            None
        };
        let report = crate::planning_v2::plan(
            sample.request,
            engine.clone(),
            store,
            catalog,
            &Default::default(),
            pack.clone(),
        )?;
        let has_goal = !report.analysis.search.lines.is_empty();
        if sample.group == "positive" && (!has_goal || reference.is_none()) {
            return Err(format!(
                "positive {} has no planner goal/reference {:?}",
                sample.id,
                report
                    .attempts
                    .iter()
                    .map(|a| &a.discrepancies)
                    .collect::<Vec<_>>()
            ));
        }
        if sample.group == "limited" && has_goal {
            return Err(format!("limited {} unexpectedly reached goal", sample.id));
        }
        let replay = if has_goal {
            Some(crate::planning_v2::replay(&report, engine.clone(), store)?)
        } else {
            None
        };
        if sample.group == "fallback" {
            let expected = if sample.id.starts_with("unknown") {
                ygo_planner::v2::FailureKind::CoverageGap
            } else {
                ygo_planner::v2::FailureKind::BudgetExhausted
            };
            if !report.failure_summary.contains(&expected) {
                return Err(format!("wrong fallback classification {}", sample.id));
            }
        }
        if sample.group == "fallback" && has_goal {
            return Err(format!("fallback {} unexpectedly verified", sample.id));
        }
        let total = report.analysis.search.stats.engine_calls as u64
            + reference
                .as_ref()
                .and_then(|v| v["engine_calls"].as_u64())
                .unwrap_or(0)
            + replay
                .as_ref()
                .and_then(|v| v["engine_calls"].as_u64())
                .unwrap_or(0);
        if total > 512 {
            return Err("fixed case exceeded shared acceptance budget".into());
        }
        results.push(serde_json::json!({"id":sample.id,"group":sample.group,"goal_achieved":has_goal,"baseline":reference,"total_engine_calls":total,"engine_calls":report.analysis.search.stats.engine_calls,"failure_summary":report.failure_summary,"line_ids":report.analysis.search.lines.iter().map(|l|&l.id).collect::<Vec<_>>(),"replay":replay}));
    }
    Ok(
        serde_json::json!({"schema_version":1,"knowledge_id":pack.id(),"passed":true,"samples":results}),
    )
}
fn baseline(
    request: &crate::planning_v2::PlanRequest,
    steps: &[Instruction],
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog: &str,
) -> Result<serde_json::Value, String> {
    let (_, mut q, _) =
        crate::combo::prepare(request.analysis.clone(), engine.clone(), store, catalog)?;
    q.protocol_version = 3;
    q.versions.initializer = "fixed-opponent-v1".into();
    q.scenario = request.scenario.clone();
    let adapter = ProcessEngineAdapter::new(engine);
    let start = std::time::Instant::now();
    let mut calls = 0;
    let mut run = |q: &RunDuelRequest| -> Result<DuelResult, String> {
        let mut q = q.clone();
        let left = request
            .analysis
            .search
            .time_limit_ms
            .saturating_sub(start.elapsed().as_millis() as u64);
        if calls >= 512 || left == 0 {
            return Err("baseline budget exhausted".into());
        }
        calls += 1;
        q.engine.timeout_ms = q.engine.timeout_ms.min(left);
        adapter.run(&q).map_err(|e| e.message)
    };
    let mut actual = run(&q)?;
    let mut cursor = 0;
    for _ in 0..request.analysis.search.max_depth {
        if actual.status == DuelStatus::EngineVerified {
            break;
        }
        if actual.status == DuelStatus::Failed || !actual.coverage_gaps.is_empty() {
            return Err(format!(
                "baseline engine gap {:?} {:?}",
                actual.error, actual.coverage_gaps
            ));
        }
        let p = actual
            .prompt
            .as_ref()
            .ok_or("baseline ended unexpectedly")?;
        let f = actual
            .events
            .iter()
            .find(|e| e.sequence == p.id)
            .ok_or("missing prompt")?;
        let metadata = prompt_metadata(p.id, &f.raw)?;
        let action = steps
            .get(cursor)
            .and_then(|i| metadata.iter().find(|m| matches(i, m)))
            .cloned();
        let action = if let Some(m) = action {
            cursor += 1;
            m
        } else {
            if p.opcode == 11 {
                return Err(format!(
                    "baseline step {} unavailable {:?}",
                    cursor,
                    steps.get(cursor)
                ));
            }
            neutral(&metadata).ok_or("baseline binding failed")?
        };
        q.decisions = actual.resolved_decisions.clone();
        q.decisions.push(Decision {
            prompt_id: p.id,
            player: p.player,
            choice: action.choice,
        });
        actual = run(&q)?;
        for decision in actual.resolved_decisions.iter().skip(q.decisions.len()) {
            if let Some(i) = steps.get(cursor) {
                let f = actual
                    .events
                    .iter()
                    .find(|e| e.sequence == decision.prompt_id)
                    .ok_or("missing auto prompt")?;
                if prompt_metadata(f.sequence, &f.raw)?
                    .iter()
                    .any(|m| m.choice == decision.choice && matches(i, m))
                {
                    cursor += 1;
                }
            }
        }
    }
    if cursor != steps.len()
        || actual.status != DuelStatus::EngineVerified
        || !ygo_planner::v2::checkpoint_goal(&actual.checkpoint)
    {
        return Err("manual baseline did not complete goal".into());
    }
    q.decisions = actual.resolved_decisions.clone();
    let replay = run(&q)?;
    if !equivalent(&actual, &replay) {
        return Err("baseline replay mismatch".into());
    }
    Ok(
        serde_json::json!({"line_id":ygo_search::combo::prefix_key(&q),"engine_calls":calls,"replay_verified":true,"request":q,"result":actual}),
    )
}
