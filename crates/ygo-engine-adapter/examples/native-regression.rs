//! One frozen execution/replay pair. All worker requests pass through the batch.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{fs, io::Write, path::PathBuf};
use ygo_engine_adapter::*;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    context: String,
    ledger: PathBuf,
    output: PathBuf,
    case_id: String,
    request: RunDuelRequest,
    expected_identity: Value,
    started_at: u64,
}
const CASES: [&str; 5] = [
    "rabbit-full",
    "tournament-full",
    "rabbit-empty",
    "rabbit-shuffle",
    "rabbit-end",
];
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    let verify_only = args.len() == 5 && args[4] == "--verify-recorded";
    let stats_only = args.len() == 5 && args[4] == "--stats";
    if (args.len() != 4 && !verify_only && !stats_only) || args[2] != "--input-sha" {
        return Err("input path --input-sha HASH [--verify-recorded] required".into());
    }
    let encoded = fs::read(&args[1])?;
    if digest(&encoded) != args[3] {
        return Err("frozen invocation content changed".into());
    }
    let input: Input = serde_json::from_slice(&encoded)?;
    safe(&input.output)?;
    safe(&input.ledger)?;
    if input.output.exists() && !verify_only && !stats_only {
        return Err("output already exists".into());
    }
    if verify_only && (!input.output.exists() || !input.ledger.exists()) {
        return Err("existing evidence and ledger required".into());
    }
    if stats_only && !input.ledger.exists() {
        return Err("existing ledger required".into());
    }
    for asset in [
        &input.request.engine.worker_path,
        &input.request.engine.ocgcore_path,
        &input.request.engine.catalog_path,
        &input.request.engine.scripts_path,
        &input.request.engine.script_manifest_path,
        &input.request.engine.engine_manifest_path,
    ] {
        let absolute = if asset.is_absolute() {
            asset.clone()
        } else {
            std::env::current_dir()?.join(asset)
        };
        if input.output.starts_with(&absolute)
            || absolute.starts_with(&input.output)
            || input.ledger.starts_with(&absolute)
        {
            return Err("output overlaps asset".into());
        }
    }
    if !CASES.contains(&input.case_id.as_str()) {
        return Err("unknown case".into());
    }
    let batch = NativeRegressionBatch::open_with_start(
        &input.ledger,
        &input.context,
        &CASES.map(str::to_owned),
        input.started_at,
    )
    .map_err(|e| e.message)?;
    if stats_only {
        batch.verify().map_err(|e| e.message)?;
        println!(
            "{}",
            json!({"native_calls":0,"ledger":batch.stats().map_err(|e|e.message)?})
        );
        return Ok(());
    }
    if let Some(saved) = batch.load_evidence(&input.case_id).map_err(|e| e.message)? {
        verify_saved(&batch, &input, &saved)?;
        if verify_only {
            let existing: Value = serde_json::from_slice(&fs::read(&input.output)?)?;
            verify_published(&batch, &input, &existing)?;
        } else {
            publish(&input.output, &saved)?;
        }
        println!(
            "{}",
            json!({"verified_recorded":true,"native_calls":0,"ledger":batch.stats().map_err(|e|e.message)?})
        );
        return Ok(());
    }
    if verify_only {
        return Err("journal evidence receipt missing".into());
    }
    // The persisted wall clock starts before the first current-asset precheck.
    // Restore paid outcomes first, including when a fresh precheck must refuse.
    let mut runs = recorded_runs(&batch, &input)?;
    let mut diagnostic = if runs.iter().any(|r| {
        r.as_ref().map_or(true, |v| {
            v.error.is_some() || v.status == DuelStatus::Failed
        })
    }) {
        Some("engine_or_journal_error")
    } else {
        None
    };
    let before = if batch.require_time().is_ok() {
        identity(&input.request).map_err(|_| "asset_precheck_failed")
    } else {
        diagnostic = Some("window_exhausted");
        Err("window_exhausted")
    };
    if diagnostic.is_none() && before.as_ref().ok() != Some(&input.expected_identity) {
        diagnostic = Some("asset_identity_drift");
    }
    if diagnostic.is_none() {
        for purpose in [CallPurpose::Execution, CallPurpose::Replay]
            .into_iter()
            .skip(runs.len())
        {
            let result = batch.run(
                ProcessEngineAdapter::new(input.request.engine.clone()),
                &input.case_id,
                &input.request,
                purpose,
            );
            let failed = result.as_ref().map_or(true, |r| {
                r.error.is_some() || r.status == DuelStatus::Failed
            });
            if result
                .as_ref()
                .is_err_and(|e| e.code == "regression_budget" || e.stage == "call_journal")
            {
                diagnostic = Some("budget_or_unresolved_consumption");
                break;
            }
            runs.push(result);
            if failed {
                diagnostic = Some("engine_or_journal_error");
                break;
            }
        }
    }
    // Paid outcomes remain publishable even when post-capture fails.
    let after = if batch.require_time().is_ok() {
        identity(&input.request).ok()
    } else {
        diagnostic = Some("window_exhausted");
        None
    };
    let assets_unchanged =
        before.as_ref().ok() == after.as_ref() && after.as_ref() == Some(&input.expected_identity);
    if !assets_unchanged && diagnostic.is_none() {
        diagnostic = Some("asset_identity_drift");
    }
    let replay_matches = matches_pair(&runs);
    if diagnostic.is_none() && !replay_matches {
        diagnostic = Some("independent_replay_mismatch");
    }
    let prompt_audits = audits(&runs);
    if prompt_audits
        .iter()
        .flatten()
        .any(|a| a["audit"]["Ok"]["matches"] != true)
        && diagnostic.is_none()
    {
        diagnostic = Some("prompt_response_audit_failed");
    }
    batch.verify().map_err(|e| e.message)?;
    let evidence = json!({"schema_version":1,"kind":"native_regression_pair","case_id":input.case_id,"context":input.context,"request":input.request,"runs":runs,"prompt_audits_by_run":prompt_audits,"assets_before":before.ok(),"assets_after":after,"assets_unchanged":assets_unchanged,"independent_replay_matches":replay_matches,"diagnostic":diagnostic,"ledger":batch.stats().map_err(|e|e.message)?,"ledger_sequence":batch.charged_sequence_id().map_err(|e|e.message)?,"started_at":batch.started_at(),"proof_ready":false,"complete_action_coverage":false,"global_optimality":false});
    batch
        .save_evidence(&input.case_id, &evidence)
        .map_err(|e| e.message)?;
    publish(&input.output, &evidence)?;
    println!(
        "{}",
        json!({"successful":diagnostic.is_none(),"ledger":evidence["ledger"]})
    );
    if diagnostic.is_some() {
        std::process::exit(1);
    }
    Ok(())
}
fn publish(path: &std::path::Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    safe(path)?;
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.sync_all()?;
    Ok(())
}
fn audits(runs: &[Result<DuelResult, WorkerError>]) -> Vec<Vec<Value>> {
    runs.iter().map(|run|match run {
        Ok(result)=>{
            if result.prompt.as_ref().is_some_and(|p| !result.events.iter().any(|f| f.sequence==p.id && recorded_prompt(f).ok().flatten().as_ref()==Some(p))) {
                return vec![json!({"audit":{"Err":"result prompt differs from recorded event"}})];
            }
            result.events.iter().filter(|f|matches!(f.opcode,11..=16|18|19|24|26)).map(|frame|{
            let actual=recorded_prompt(frame).and_then(|p|p.ok_or("missing recorded prompt".into())).and_then(|p|{
                if parse_prompt(frame.sequence,&frame.raw)?.as_ref()!=Some(&p) { return Err("native prompt differs from current protocol".into()); }
                Ok(p.actions.into_iter().map(|a|a.bytes).collect::<Vec<_>>())
            });
            let audit=actual.as_ref().map_err(Clone::clone).and_then(|a|audit_prompt_responses(&frame.raw,a));
            json!({"sequence":frame.sequence,"opcode":frame.opcode,"raw":frame.raw,"actual_response_bytes":actual,"audit":audit})
        }).collect()},Err(_)=>Vec::new()
    }).collect()
}
fn verify_saved(
    batch: &NativeRegressionBatch,
    input: &Input,
    saved: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    if saved["case_id"] != input.case_id
        || saved["context"] != input.context
        || saved["request"] != serde_json::to_value(&input.request)?
    {
        return Err("receipt binding differs".into());
    }
    let recorded: Vec<Result<DuelResult, WorkerError>> =
        serde_json::from_value(saved["runs"].clone())?;
    let mut actual = Vec::new();
    for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
        if let Some(value) = batch
            .load_outcome(&input.case_id, &input.request, purpose)
            .map_err(|e| e.message)?
        {
            actual.push(value);
        }
    }
    if serde_json::to_value(&actual)? != saved["runs"]
        || serde_json::to_value(audits(&recorded))? != saved["prompt_audits_by_run"]
        || json!(matches_pair(&recorded)) != saved["independent_replay_matches"]
    {
        return Err("journal outcome or recomputed audit differs".into());
    }
    batch.verify().map_err(|e| e.message)?;
    Ok(())
}
fn verify_published(
    batch: &NativeRegressionBatch,
    input: &Input,
    existing: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    let saved = batch
        .load_evidence(&input.case_id)
        .map_err(|e| e.message)?
        .ok_or("missing immutable evidence receipt")?;
    if *existing != saved {
        return Err("evidence differs from immutable journal receipt".into());
    }
    verify_saved(batch, input, &saved)
}
fn matches_pair(runs: &[Result<DuelResult, WorkerError>]) -> bool {
    match (runs.first(), runs.get(1)) {
        (Some(Ok(a)), Some(Ok(b))) => {
            a.error.is_none()
                && b.error.is_none()
                && a.status == b.status
                && a.events == b.events
                && a.checkpoint == b.checkpoint
                && a.prompt == b.prompt
                && a.loaded_scripts == b.loaded_scripts
                && a.resolved_decisions == b.resolved_decisions
        }
        _ => false,
    }
}
fn recorded_runs(
    batch: &NativeRegressionBatch,
    input: &Input,
) -> Result<Vec<Result<DuelResult, WorkerError>>, Box<dyn std::error::Error>> {
    let mut runs = Vec::new();
    for purpose in [CallPurpose::Execution, CallPurpose::Replay] {
        match batch
            .load_outcome(&input.case_id, &input.request, purpose)
            .map_err(|e| e.message)?
        {
            Some(value) => runs.push(value),
            None => break,
        }
    }
    Ok(runs)
}
fn identity(request: &RunDuelRequest) -> Result<Value, String> {
    let value = capture_engine_identity(&request.engine)?;
    if value["consistent"] != true {
        return Err("inconsistent assets".into());
    }
    let versions = serde_json::to_value(&request.versions).map_err(|e| e.to_string())?;
    for (role, key) in [
        ("dll", "engine_sha256"),
        ("cdb", "cdb_sha256"),
        ("script_manifest", "scripts_sha256"),
    ] {
        if value["roles"][role]["sha256"] != versions[key] {
            return Err("request asset mismatch".into());
        }
    }
    Ok(value)
}
fn safe(path: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    let base = std::env::current_dir()?.join("data/runtime");
    if !path.is_absolute()
        || !path
            .strip_prefix(base)?
            .components()
            .any(|c| c.as_os_str() == "research")
        || path
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err("dedicated absolute research output required".into());
    }
    let mut current = PathBuf::new();
    for part in path.components() {
        current.push(part);
        if let Ok(meta) = fs::symlink_metadata(&current) {
            if meta.file_type().is_symlink() {
                return Err("linked output".into());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if meta.file_attributes() & 0x400 != 0 {
                    return Err("reparse output".into());
                }
            }
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn failed_or_missing_results_never_qualify_as_replay() {
        assert!(!matches_pair(&[]));
        assert!(!matches_pair(&[Err(WorkerError::new(
            "error", "test", "test"
        ))]));
    }
    #[test]
    fn only_five_planned_pairs_are_available() {
        assert_eq!(CASES.len() * 2, 10);
        assert!(!CASES.contains(&"extra-probe"));
    }
    #[test]
    fn recorded_response_tampering_is_detected_before_oracle_qualification() {
        let mut raw = vec![11, 0];
        raw.extend([0; 24]);
        raw.extend([0, 1, 1]);
        let frame = decode_frame(19, &raw).unwrap();
        let mut result = DuelResult::failure(WorkerError::new("synthetic", "test", "fixture"));
        result.events = vec![frame];
        let current = audits(&[Ok(result.clone())]);
        assert_eq!(current[0][0]["audit"]["Ok"]["matches"], true);
        result.events[0].fields["prompt"]["actions"]
            .as_array_mut()
            .unwrap()
            .pop();
        assert!(audits(&[Ok(result)])[0][0]["audit"].get("Err").is_some());
    }
    #[test]
    fn forged_runs_audits_assets_and_ledger_are_rejected_without_native_calls() {
        struct Stub;
        impl EngineAdapter for Stub {
            fn doctor(&self) -> DoctorReport {
                panic!("unused")
            }
            fn run(&self, _: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
                let mut r = DuelResult::failure(WorkerError::new("synthetic", "test", "fixture"));
                r.error = None;
                r.status = DuelStatus::DecisionRequired;
                Ok(r)
            }
        }
        let directory = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../data/tmp");
        fs::create_dir_all(&directory).unwrap();
        let path = directory.join(format!(
            "native-receipt-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let batch =
            NativeRegressionBatch::open(&path, "frozen", &CASES.map(str::to_owned)).unwrap();
        let request:RunDuelRequest=serde_json::from_value(json!({"protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[],"seed":1,"decisions":[],"versions":RuntimeVersions::default()})).unwrap();
        let runs = [CallPurpose::Execution, CallPurpose::Replay]
            .map(|p| batch.run(Stub, "rabbit-full", &request, p));
        let input = Input {
            context: "frozen".into(),
            ledger: path,
            output: directory.join("unused.json"),
            case_id: "rabbit-full".into(),
            request,
            expected_identity: Value::Null,
            started_at: batch.started_at(),
        };
        let saved = json!({"case_id":"rabbit-full","context":"frozen","request":input.request,"runs":runs,"prompt_audits_by_run":audits(&runs),"independent_replay_matches":true,"ledger":batch.stats().unwrap(),"assets_unchanged":true});
        batch.save_evidence("rabbit-full", &saved).unwrap();
        assert!(verify_published(&batch, &input, &saved).is_ok());
        for (key, value) in [
            ("runs", json!([])),
            ("prompt_audits_by_run", json!([[{"forged":true}]])),
            ("ledger", json!({"consumed":0})),
            ("assets_unchanged", json!(false)),
            ("independent_replay_matches", json!(false)),
        ] {
            let mut forged = saved.clone();
            forged[key] = value;
            assert!(verify_published(&batch, &input, &forged).is_err(), "{key}");
        }
        assert_eq!(batch.stats().unwrap().consumed, 2);
        // Simulate a crash after the next execution, before fresh precheck/receipt.
        batch
            .run(Stub, "rabbit-empty", &input.request, CallPurpose::Execution)
            .unwrap();
        let partial_input = Input {
            case_id: "rabbit-empty".into(),
            ..input
        };
        let partial = recorded_runs(&batch, &partial_input).unwrap();
        assert_eq!(partial.len(), 1);
        let refused = json!({"case_id":"rabbit-empty","context":"frozen","request":partial_input.request,"runs":partial,"prompt_audits_by_run":audits(&partial),"independent_replay_matches":false,"diagnostic":"asset_identity_drift"});
        batch.save_evidence("rabbit-empty", &refused).unwrap();
        assert!(verify_published(&batch, &partial_input, &refused).is_ok());
        assert_eq!(batch.stats().unwrap().consumed, 3);
    }
}
