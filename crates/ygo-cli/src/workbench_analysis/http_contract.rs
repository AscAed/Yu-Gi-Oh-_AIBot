//! Whitelisted local HTTP contracts; no runtime configuration is serialized.
use super::{
    jobs::{strict_json_value, AnalysisJobRecordV1},
    operations::{AnalysisOperationCommand, AnalysisOperationRecordV1},
};
use serde_json::{json, Value};
use ygo_api::combo::AnalysisReport;

const INVALID: &str = "analysis_request_invalid";
fn object(bytes: &[u8], kind: &str, fields: &[&str]) -> Result<Value, &'static str> {
    let value = strict_json_value(bytes).map_err(|_| INVALID)?;
    let map = value.as_object().ok_or(INVALID)?;
    if map.len() != fields.len()
        || fields.iter().any(|key| !map.contains_key(*key))
        || value["schema_version"].as_u64() != Some(1)
        || value["kind"] != kind
    {
        return Err(INVALID);
    }
    Ok(value)
}
pub fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}
pub fn parse_allocate(bytes: &[u8]) -> Result<(), &'static str> {
    object(
        bytes,
        "analysis_operation_allocate",
        &["schema_version", "kind"],
    )
    .map(|_| ())
}
pub fn parse_cancel(bytes: &[u8]) -> Result<u64, &'static str> {
    let value = object(
        bytes,
        "analysis_cancel",
        &["schema_version", "kind", "expected_revision"],
    )?;
    value["expected_revision"]
        .as_u64()
        .filter(|n| *n > 0)
        .ok_or(INVALID)
}
pub fn parse_submit(bytes: &[u8]) -> Result<AnalysisOperationCommand, &'static str> {
    let mut value = object(
        bytes,
        "analysis_submit",
        &[
            "schema_version",
            "kind",
            "draft_id",
            "draft_revision",
            "opening_hand",
            "seed",
            "rules",
            "catalog_id",
            "banlist_id",
            "as_of",
            "search",
        ],
    )?;
    let budget = value["search"].as_object().ok_or(INVALID)?;
    if budget.len() != 5
        || [
            "top_k",
            "node_budget",
            "beam_width",
            "max_depth",
            "time_limit_ms",
        ]
        .iter()
        .any(|k| !budget.get(*k).is_some_and(|n| n.as_u64().is_some()))
        || value["seed"].as_u64().is_none()
        || !value["opening_hand"].as_array().is_some_and(|cards| {
            cards
                .iter()
                .all(|n| n.as_u64().is_some_and(|n| n > 0 && n <= u32::MAX as u64))
        })
    {
        return Err(INVALID);
    }
    let map = value.as_object_mut().ok_or(INVALID)?;
    map.remove("schema_version");
    map.remove("kind");
    let command: AnalysisOperationCommand = serde_json::from_value(value).map_err(|_| INVALID)?;
    command.validate().map_err(|_| INVALID)?;
    Ok(command)
}
pub fn api_error(code: &str, operation_id: Option<&str>, job_id: Option<&str>) -> Value {
    json!({"schema_version":1,"kind":"analysis_api_error","error":{"code":code,"operation_id":operation_id,"job_id":job_id,"field":null}})
}
pub fn operation_dto(record: &AnalysisOperationRecordV1) -> Value {
    let error = record
        .error_code()
        .or_else(|| record.rejection().map(|r| r.error_code.as_str()));
    json!({"schema_version":1,"kind":"analysis_operation","operation_id":record.operation_id(),"revision":record.revision(),"created_at_ms":record.created_at_ms(),"updated_at_ms":record.updated_at_ms(),"state":record.state(),"command_sha256":record.command_sha256(),"job_id":record.job_id(),"frozen_binding_sha256":record.frozen_binding_sha256(),"error_code":error})
}
pub fn job_dto(record: &AnalysisJobRecordV1, service_state: &str) -> Value {
    json!({"schema_version":1,"kind":"analysis_job_status","job_id":record.job_id(),"revision":record.revision(),"created_at_ms":record.created_at_ms(),"updated_at_ms":record.updated_at_ms(),"state":record.state(),"input":record.input(),"report":record.report(),"error_code":record.error_code(),"service_state":service_state})
}
pub fn result_dto(
    record: &AnalysisJobRecordV1,
    report: &AnalysisReport,
) -> Result<Value, &'static str> {
    let reference = record.report().ok_or("job_result_unavailable")?;
    let mut lines = Vec::new();
    for line in &report.search.lines {
        let e = &line.evaluation;
        validate_evaluation(&line.id, e)?;
        let gaps: Vec<&str> = e
            .coverage_gaps
            .iter()
            .map(|_| "coverage_gap_unclassified")
            .collect();
        lines.push(json!({"id":line.id,"decisions":line.decisions,"evaluation":{"kind":e.kind,"profile_version":e.profile_version,"interaction":e.interaction,"resources":e.resources,"follow_up":e.follow_up,"decisions":e.decisions,"total":e.total},"status":line.result.status,"replay_verified":line.replay_verified,"coverage_gaps":gaps}));
    }
    let s = &report.search.stats;
    Ok(
        json!({"schema_version":1,"kind":"analysis_job_result","job_id":record.job_id(),"revision":record.revision(),"input_binding_sha256":record.input().binding_sha256,"report":reference,"budget":report.search.budget,"termination":reference.termination,"scoring":report.search.scoring,"stats":{"nodes":s.nodes,"engine_calls":s.engine_calls,"cache_hits":s.cache_hits,"pruned":s.pruned,"failed_branches":s.failed_branches,"elapsed_ms":s.elapsed_ms,"replay_ms":s.replay_ms,"peak_frontier":s.peak_frontier,"max_decision_depth":s.max_decision_depth,"completed_lines":s.completed_lines,"parent_peak_working_set_bytes":s.parent_peak_working_set_bytes,"worker_peak_working_set_bytes":s.worker_peak_working_set_bytes},"lines":lines,"evidence":{"report_contract_validated":true,"report_origin_authenticated":false,"search_complete":false,"global_optimality":false}}),
    )
}
fn validate_evaluation(id: &str, e: &ygo_search::combo::Evaluation) -> Result<(), &'static str> {
    // These labels are service-owned, never arbitrary report text.
    if e.kind != "heuristic"
        || e.profile_version != "rabbit-v1"
        || id.is_empty()
        || !id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        || [e.interaction, e.resources, e.follow_up, e.total]
            .iter()
            .any(|v| !v.is_finite())
    {
        return Err("analysis_projection_invalid");
    }
    Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_duplicate_and_non_integer_requests() {
        assert!(
            parse_allocate(br#"{"schema_version":1,"kind":"analysis_operation_allocate"}"#).is_ok()
        );
        assert!(parse_allocate(
            br#"{"schema_version":1,"schema_version":1,"kind":"analysis_operation_allocate"}"#
        )
        .is_err());
        for number in ["true", "1.0", "1e0", "0"] {
            let body = format!(
                r#"{{"schema_version":1,"kind":"analysis_cancel","expected_revision":{number}}}"#
            );
            assert!(parse_cancel(body.as_bytes()).is_err());
        }
    }
    #[test]
    fn rejects_projection_labels_paths_and_nonfinite_scores() {
        let mut e = ygo_search::combo::Evaluation {
            kind: "heuristic".into(),
            profile_version: "rabbit-v1".into(),
            interaction: 0.,
            resources: 0.,
            follow_up: 0.,
            decisions: 0,
            total: 0.,
            coverage_gaps: vec![],
            explanations: vec![],
        };
        assert!(validate_evaluation("line-1", &e).is_ok());
        assert!(validate_evaluation("C:\\private\\report", &e).is_err());
        e.profile_version = "C:\\private".into();
        assert!(validate_evaluation("line-1", &e).is_err());
        e.profile_version = "rabbit-v1".into();
        e.total = f64::NAN;
        assert!(validate_evaluation("line-1", &e).is_err());
    }
    #[test]
    fn rejects_missing_budget_fields_and_nullable_selection_omission() {
        let valid = json!({"schema_version":1,"kind":"analysis_submit","draft_id":"a".repeat(32),"draft_revision":"b".repeat(64),"opening_hand":[1,1,1,2,2],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":"latest-ocg","as_of":"2026-11-01","search":{"top_k":1,"node_budget":100,"beam_width":1,"max_depth":10,"time_limit_ms":100}});
        assert!(parse_submit(&serde_json::to_vec(&valid).unwrap()).is_ok());
        let mut missing = valid.clone();
        missing.as_object_mut().unwrap().remove("catalog_id");
        assert!(parse_submit(&serde_json::to_vec(&missing).unwrap()).is_err());
        let mut budget = valid;
        budget["search"].as_object_mut().unwrap().remove("top_k");
        assert!(parse_submit(&serde_json::to_vec(&budget).unwrap()).is_err());
    }
}
