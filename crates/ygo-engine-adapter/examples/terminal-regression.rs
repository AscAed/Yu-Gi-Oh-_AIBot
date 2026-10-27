//! One frozen execution/replay pair. All worker requests pass through the batch.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{fs, io::Write, path::PathBuf};
use ygo_engine_adapter::*;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    #[serde(default)]
    batch_kind: Option<String>,
    context: String,
    ledger: PathBuf,
    output: PathBuf,
    case_id: String,
    request: RunDuelRequest,
    expected_identity: Value,
    started_at: u64,
    catalog_types: Value,
    expected_count: u64,
}
fn smoke(input: &Input) -> bool {
    input.batch_kind.as_deref() == Some("terminal-smoke-v1")
}
fn followup(input: &Input) -> bool {
    input.batch_kind.as_deref() == Some("terminal-followup-v1")
}
fn strict(input: &Input) -> bool {
    smoke(input) || followup(input)
}
fn pair_kind(input: &Input) -> &'static str {
    if followup(input) {
        "terminal_followup_pair"
    } else if smoke(input) {
        "terminal_smoke_pair"
    } else {
        "terminal_regression_pair"
    }
}
fn before_replay<T>(
    checks: impl FnOnce() -> Result<(), &'static str>,
    next: impl FnOnce() -> T,
) -> Result<T, &'static str> {
    checks()?;
    Ok(next())
}
fn smoke_assets_ready(
    expected: &Value,
    scan: impl FnOnce() -> Result<Value, &'static str>,
    mut time: impl FnMut() -> Result<(), &'static str>,
) -> Result<(), &'static str> {
    time()?;
    let current = scan()?;
    time()?;
    if current != *expected {
        return Err("asset_identity_drift");
    }
    Ok(())
}
fn smoke_run_ready(
    input: &Input,
    run: &Result<DuelResult, WorkerError>,
) -> Result<(), &'static str> {
    let result = run.as_ref().map_err(|_| "engine_or_journal_error")?;
    if result.status != DuelStatus::EngineVerified
        || result.error.is_some()
        || result.prompt.is_some()
        || result.resolved_decisions != input.request.decisions
    {
        return Err("incomplete_execution");
    }
    if !terminal_ok(input, run)
        || result.terminal_observation.as_ref().map_or(true, |o| {
            o["capture_query_count"] != 14
                || o["queries"].as_array().map_or(true, |q| q.len() != 14)
        })
    {
        return Err("terminal_binding_or_utility_failed");
    }
    if audits(std::slice::from_ref(run))
        .iter()
        .flatten()
        .any(|a| a["audit"]["Ok"]["matches"] != true)
    {
        return Err("prompt_response_audit_failed");
    }
    Ok(())
}
const CASES: [&str; 3] = [
    "terminal-rabbit",
    "terminal-tournament",
    "terminal-shuffle-end",
];
fn terminal_audit(input: &Input, runs: &[Result<DuelResult, WorkerError>]) -> Vec<Value> {
    runs.iter()
        .map(|run| {
            evaluate_terminal_run(
                &serde_json::to_value(&input.request).unwrap(),
                &serde_json::to_value(run).unwrap(),
                &input.catalog_types,
            )
        })
        .collect()
}
fn terminal_ok(input: &Input, result: &Result<DuelResult, WorkerError>) -> bool {
    let report = terminal_audit(input, std::slice::from_ref(result));
    report[0]["binding_valid"] == true
        && report[0]["snapshot_count"] == input.expected_count
        && report[0]["utility"] == input.expected_count
}
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
    if input
        .batch_kind
        .as_deref()
        .is_some_and(|v| v != "terminal-smoke-v1" && v != "terminal-followup-v1")
        || (smoke(&input) && input.case_id != "terminal-rabbit")
        || (followup(&input)
            && !["terminal-tournament", "terminal-shuffle-end"].contains(&input.case_id.as_str()))
    {
        return Err("invalid batch kind or smoke case".into());
    }
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
    if input.request.research_capture.is_none()
        || input.expected_count
            != if input.case_id == "terminal-rabbit" {
                1
            } else {
                0
            }
    {
        return Err("capture policy or expected value differs".into());
    }
    let open = if smoke(&input) {
        NativeRegressionBatch::open_terminal_smoke_with_start
    } else if followup(&input) {
        NativeRegressionBatch::open_terminal_followup_with_start
    } else {
        NativeRegressionBatch::open_terminal_with_start
    };
    let cases = if smoke(&input) {
        vec!["terminal-rabbit".to_owned()]
    } else if followup(&input) {
        vec![
            "terminal-tournament".to_owned(),
            "terminal-shuffle-end".to_owned(),
        ]
    } else {
        CASES.map(str::to_owned).to_vec()
    };
    let batch =
        open(&input.ledger, &input.context, &cases, input.started_at).map_err(|e| e.message)?;
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
    if diagnostic.is_none() && runs.iter().any(|run| !terminal_ok(&input, run)) {
        diagnostic = Some("terminal_binding_or_utility_failed");
    }
    if strict(&input) && diagnostic.is_none() {
        diagnostic = runs
            .iter()
            .find_map(|run| smoke_run_ready(&input, run).err());
    }
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
            let result = before_replay(
                || {
                    if strict(&input) && purpose == CallPurpose::Replay {
                        smoke_run_ready(&input, &runs[0])?;
                        smoke_assets_ready(
                            &input.expected_identity,
                            || identity(&input.request).map_err(|_| "asset_precheck_failed"),
                            || batch.require_time().map_err(|_| "window_exhausted"),
                        )?;
                    }
                    Ok(())
                },
                || {
                    batch.run(
                        ProcessEngineAdapter::new(input.request.engine.clone()),
                        &input.case_id,
                        &input.request,
                        purpose,
                    )
                },
            );
            let result = match result {
                Ok(value) => value,
                Err(reason) => {
                    diagnostic = Some(reason);
                    break;
                }
            };
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
            let bound = terminal_ok(&input, &result);
            runs.push(result);
            if strict(&input) {
                if let Err(reason) = smoke_run_ready(&input, runs.last().unwrap()) {
                    diagnostic = Some(reason);
                    break;
                }
            }
            if !bound && !failed {
                diagnostic = Some("terminal_binding_or_utility_failed");
                break;
            }
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
    if strict(&input) && batch.require_time().is_err() {
        diagnostic = Some("window_exhausted");
    }
    let assets_unchanged =
        before.as_ref().ok() == after.as_ref() && after.as_ref() == Some(&input.expected_identity);
    if !assets_unchanged && diagnostic.is_none() {
        diagnostic = Some("asset_identity_drift");
    }
    let replay_matches = matches_pair(&runs);
    if diagnostic.is_none() && !replay_matches {
        diagnostic = Some("independent_replay_mismatch");
    }
    let terminal_audits = terminal_audit(&input, &runs);
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
    let evidence = json!({"schema_version":1,"kind":pair_kind(&input),"case_id":input.case_id,"context":input.context,"request":input.request,"runs":runs,"terminal_audits":terminal_audits,"prompt_audits_by_run":prompt_audits,"assets_before":before.ok(),"assets_after":after,"assets_unchanged":assets_unchanged,"independent_replay_matches":replay_matches,"diagnostic":diagnostic,"ledger":batch.stats().map_err(|e|e.message)?,"ledger_sequence":batch.charged_sequence_id().map_err(|e|e.message)?,"started_at":batch.started_at(),"proof_ready":false,"complete_action_coverage":false,"global_optimality":false});
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
        || (strict(input) && saved["kind"] != pair_kind(input))
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
        || json!(terminal_audit(input, &recorded)) != saved["terminal_audits"]
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
                && serde_json::to_value(&a.terminal_observation).ok()
                    == serde_json::to_value(&b.terminal_observation).ok()
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
    fn synthetic_smoke() -> (Input, Result<DuelResult, WorkerError>) {
        fn hash(value: &Value) -> String {
            digest(&serde_json::to_vec(value).unwrap())
        }
        let mut request: RunDuelRequest = serde_json::from_value(json!({"protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},"opening_hand":[1,2,3,4,5],"seed":1,"decisions":[],"versions":RuntimeVersions::default(),"research_capture":{"schema_version":1,"objective":"rabbit-own-face-up-xyz-v1","boundary":"first-next-turn-process-return-v1"}})).unwrap();
        request.versions.cdb_sha256 = "a".repeat(64);
        let mut prompt = vec![11, 0];
        prompt.extend([0; 24]);
        prompt.extend([0, 1, 1]);
        let frames = [vec![40, 0], prompt, vec![41, 0, 2], vec![40, 1]];
        let events: Vec<_> = frames
            .iter()
            .enumerate()
            .map(|(i, f)| decode_frame((i + 1) as u64, f).unwrap())
            .collect();
        let batches: Vec<_> = [(0,2,1), (2,4,2)].into_iter().enumerate().map(|(index,(start,end,status))| {
            let raw:Vec<u8> = frames[start..end].iter().flat_map(|f| (f.len() as u32).to_le_bytes().into_iter().chain(f.iter().copied())).collect();
            json!({"index":index,"status":status,"raw":raw,"sha256":digest(&raw),"start_sequence":start+1,"end_sequence":end})
        }).collect();
        let mut card = Vec::new();
        for (flag, value) in [(1u32, 42u32), (2, 1), (8, 8388609)] {
            card.extend(8u16.to_le_bytes());
            card.extend(flag.to_le_bytes());
            card.extend(value.to_le_bytes());
        }
        card.extend(4u16.to_le_bytes());
        card.extend(0x80000000u32.to_le_bytes());
        let mut queries = Vec::new();
        for player in 0..2 {
            for sequence in 0..7 {
                let raw = if player == 0 && sequence == 0 {
                    card.clone()
                } else {
                    vec![]
                };
                queries.push(json!({"controller":player,"location":4,"sequence":sequence,"flags":11,"raw":raw,"sha256":digest(&raw),"error":null}));
            }
        }
        let cards = json!([{"code":42,"player":0,"location":4,"sequence":0,"position":1,"type_flags":8388609}]);
        let observation = json!({"schema_version":1,"status":"bound","request_sha256":hash(&serde_json::to_value(&request).unwrap()),"batches":batches,"event_prefix_sha256":hash(&json!(events)),"boundary_batch_index":1,"boundary_sequence":4,"phase":null,"turn_index":2,"turn_player":1,"turn_source":"raw_new_turn_events","queries":queries,"capture_query_count":14,"queries_sha256":hash(&json!(queries)),"snapshot":cards,"snapshot_sha256":hash(&cards)});
        let mut run = DuelResult::failure(WorkerError::new("synthetic", "test", "fixture"));
        run.error = None;
        run.status = DuelStatus::EngineVerified;
        run.versions = request.versions.clone();
        run.events = events;
        run.terminal_observation = Some(observation);
        let input = Input {
            batch_kind: Some("terminal-smoke-v1".into()),
            context: "synthetic".into(),
            ledger: PathBuf::new(),
            output: PathBuf::new(),
            case_id: "terminal-rabbit".into(),
            request,
            expected_identity: json!({"frozen":true}),
            started_at: 0,
            catalog_types: json!({"42":8388609}),
            expected_count: 1,
        };
        (input, Ok(run))
    }
    #[test]
    fn followup_zero_requires_complete_bound_queries_before_replay() {
        let (mut input, mut valid) = synthetic_smoke();
        input.batch_kind = Some("terminal-followup-v1".into());
        input.case_id = "terminal-tournament".into();
        input.expected_count = 0;
        input.catalog_types = json!({"42":67108897});
        let observation = valid
            .as_mut()
            .unwrap()
            .terminal_observation
            .as_mut()
            .unwrap();
        // Synthetic Link monster, not an empty or failed checkpoint.
        observation["queries"][0]["raw"][26] = json!(33);
        observation["queries"][0]["raw"][27] = json!(0);
        observation["queries"][0]["raw"][28] = json!(0);
        observation["queries"][0]["raw"][29] = json!(4);
        let raw: Vec<u8> =
            serde_json::from_value(observation["queries"][0]["raw"].clone()).unwrap();
        observation["queries"][0]["sha256"] = json!(digest(&raw));
        observation["snapshot"][0]["type_flags"] = json!(67108897);
        observation["queries_sha256"] = json!(digest(
            &serde_json::to_vec(&observation["queries"]).unwrap()
        ));
        observation["snapshot_sha256"] = json!(digest(
            &serde_json::to_vec(&observation["snapshot"]).unwrap()
        ));
        assert!(strict(&input));
        assert_eq!(pair_kind(&input), "terminal_followup_pair");
        assert!(
            smoke_run_ready(&input, &valid).is_ok(),
            "{:?}",
            terminal_audit(&input, std::slice::from_ref(&valid))
        );
        for mode in 0..3 {
            let mut run = valid.clone();
            let result = run.as_mut().unwrap();
            match mode {
                0 => {
                    result.terminal_observation = None;
                }
                1 => {
                    result.terminal_observation.as_mut().unwrap()["queries"]
                        .as_array_mut()
                        .unwrap()
                        .pop();
                }
                _ => {
                    result.status = DuelStatus::Failed;
                }
            }
            let calls = std::cell::Cell::new(0);
            assert!(before_replay(
                || smoke_run_ready(&input, &run),
                || calls.set(calls.get() + 1)
            )
            .is_err());
            assert_eq!(calls.get(), 0);
        }
    }
    #[test]
    fn actual_smoke_gate_rejects_queries_prompts_decisions_and_audit_before_replay() {
        let (input, valid) = synthetic_smoke();
        assert!(
            smoke_run_ready(&input, &valid).is_ok(),
            "{:?}",
            terminal_audit(&input, std::slice::from_ref(&valid))
        );
        for mutation in 0..4 {
            let mut run = valid.clone();
            let result = run.as_mut().unwrap();
            match mutation {
                0 => {
                    result.terminal_observation.as_mut().unwrap()["queries"]
                        .as_array_mut()
                        .unwrap()
                        .pop();
                }
                1 => {
                    result.events[1].fields["prompt"]["actions"]
                        .as_array_mut()
                        .unwrap()
                        .pop();
                    let events = serde_json::to_value(&result.events).unwrap();
                    result.terminal_observation.as_mut().unwrap()["event_prefix_sha256"] =
                        json!(digest(&serde_json::to_vec(&events).unwrap()));
                }
                2 => {
                    result.prompt = recorded_prompt(&result.events[1]).unwrap();
                }
                _ => {
                    result.resolved_decisions.push(serde_json::from_value(json!({"prompt_id":2,"player":0,"choice":{"kind":"command","command":7,"index":0}})).unwrap());
                }
            }
            let calls = std::cell::Cell::new(0);
            assert!(
                before_replay(
                    || smoke_run_ready(&input, &run),
                    || calls.set(calls.get() + 1)
                )
                .is_err(),
                "mutation {mutation}"
            );
            assert_eq!(calls.get(), 0);
        }
    }
    #[test]
    fn actual_asset_gate_checks_scan_and_postscan_clock_before_replay() {
        let expected = json!({"frozen":true});
        for mode in 0..3 {
            let calls = std::cell::Cell::new(0);
            let clocks = std::cell::Cell::new(0);
            let result = before_replay(
                || {
                    smoke_assets_ready(
                        &expected,
                        || {
                            if mode == 0 {
                                Err("asset_precheck_failed")
                            } else if mode == 1 {
                                Ok(json!({"frozen":false}))
                            } else {
                                Ok(expected.clone())
                            }
                        },
                        || {
                            clocks.set(clocks.get() + 1);
                            if mode == 2 && clocks.get() == 2 {
                                Err("window_exhausted")
                            } else {
                                Ok(())
                            }
                        },
                    )
                },
                || calls.set(calls.get() + 1),
            );
            assert!(result.is_err());
            assert_eq!(calls.get(), 0);
        }
        let calls = std::cell::Cell::new(0);
        before_replay(
            || smoke_assets_ready(&expected, || Ok(expected.clone()), || Ok(())),
            || calls.set(calls.get() + 1),
        )
        .unwrap();
        assert_eq!(calls.get(), 1);
    }
    #[test]
    fn query_audit_and_asset_gate_failures_never_call_replay_stub() {
        for reason in [
            "terminal_binding_or_utility_failed",
            "prompt_response_audit_failed",
            "asset_identity_drift",
            "window_exhausted",
        ] {
            let calls = std::cell::Cell::new(0);
            let result = before_replay(|| Err(reason), || calls.set(calls.get() + 1));
            assert_eq!(result, Err(reason));
            assert_eq!(calls.get(), 0);
        }
        let calls = std::cell::Cell::new(0);
        before_replay(|| Ok(()), || calls.set(calls.get() + 1)).unwrap();
        assert_eq!(calls.get(), 1);
    }
    #[test]
    fn failed_or_missing_results_never_qualify_as_replay() {
        assert!(!matches_pair(&[]));
        assert!(!matches_pair(&[Err(WorkerError::new(
            "error", "test", "test"
        ))]));
    }
    #[test]
    fn only_three_planned_pairs_are_available() {
        assert_eq!(CASES.len() * 2, 6);
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
            .map(|p| batch.run(Stub, "terminal-rabbit", &request, p));
        let input = Input {
            batch_kind: None,
            context: "frozen".into(),
            ledger: path,
            output: directory.join("unused.json"),
            case_id: "terminal-rabbit".into(),
            request,
            expected_identity: Value::Null,
            catalog_types: json!({}),
            expected_count: 1,
            started_at: batch.started_at(),
        };
        let saved = json!({"case_id":"terminal-rabbit","context":"frozen","request":input.request,"runs":runs,"terminal_audits":terminal_audit(&input, &runs),"prompt_audits_by_run":audits(&runs),"independent_replay_matches":true,"ledger":batch.stats().unwrap(),"assets_unchanged":true});
        batch.save_evidence("terminal-rabbit", &saved).unwrap();
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
            .run(
                Stub,
                "terminal-tournament",
                &input.request,
                CallPurpose::Execution,
            )
            .unwrap();
        let partial_input = Input {
            case_id: "terminal-tournament".into(),
            ..input
        };
        let partial = recorded_runs(&batch, &partial_input).unwrap();
        assert_eq!(partial.len(), 1);
        let refused = json!({"case_id":"terminal-tournament","context":"frozen","request":partial_input.request,"runs":partial,"terminal_audits":terminal_audit(&partial_input,&partial),"prompt_audits_by_run":audits(&partial),"independent_replay_matches":false,"diagnostic":"asset_identity_drift"});
        batch
            .save_evidence("terminal-tournament", &refused)
            .unwrap();
        assert!(verify_published(&batch, &partial_input, &refused).is_ok());
        assert_eq!(batch.stats().unwrap().consumed, 3);
    }
}
