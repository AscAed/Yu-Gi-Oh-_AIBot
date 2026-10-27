//! Execute a Python-validated batch, or recover recorded calls without starting a worker.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{fs, path::PathBuf};
use ygo_engine_adapter::*;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    context: String,
    ledger: PathBuf,
    output: PathBuf,
    cases: Vec<Case>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Case {
    case_id: String,
    request: RunDuelRequest,
}
#[derive(Debug, PartialEq)]
enum Mode {
    Execute,
    Recover(u64),
    Authorized(String),
}
fn parse_mode(args: &[String]) -> Result<Mode, String> {
    match args {
        [_, _] => Ok(Mode::Execute),
        [_, _, flag, value] if flag == "--recover" => value
            .parse()
            .map(Mode::Recover)
            .map_err(|_| "invalid call ID".into()),
        [_, _, flag, value] if flag == "--authorized-window" => Ok(Mode::Authorized(value.clone())),
        _ => Err("expected input JSON [--recover CALL_ID | --authorized-window ID]".into()),
    }
}
fn continuation_progress(base: usize, consumed: usize) -> Result<usize, String> {
    consumed
        .checked_sub(base)
        .filter(|count| *count <= 2)
        .ok_or_else(|| "consumption outside authorized continuation".into())
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    let mode = parse_mode(&args)?;
    let input: Input =
        serde_json::from_slice(&fs::read(args.get(1).ok_or("input JSON path required")?)?)?;
    let recover = match mode {
        Mode::Recover(id) => Some(id),
        _ => None,
    };
    if input.cases.is_empty()
        || input.cases.len() > 8
        || (mode != Mode::Execute && input.cases.len() != 1)
    {
        return Err("one to eight cases; recovery requires one case".into());
    }
    safe_output(&input.output)?;
    safe_output(&input.ledger)?;
    for case in &input.cases {
        if case.case_id.is_empty()
            || !case
                .case_id
                .bytes()
                .all(|c| c.is_ascii_alphanumeric() || c == b'-')
        {
            return Err("invalid case id".into());
        }
        for asset in [
            &case.request.engine.worker_path,
            &case.request.engine.ocgcore_path,
            &case.request.engine.catalog_path,
            &case.request.engine.scripts_path,
            &case.request.engine.script_manifest_path,
            &case.request.engine.engine_manifest_path,
        ] {
            let absolute = if asset.is_absolute() {
                asset.clone()
            } else {
                std::env::current_dir()?.join(asset)
            };
            if input.output.starts_with(&absolute)
                || absolute.starts_with(&input.output)
                || input.ledger == absolute
                || input.ledger.starts_with(&absolute)
            {
                return Err("research output overlaps runtime asset".into());
            }
        }
    }
    fs::create_dir_all(&input.output)?;
    let batch = match &mode {
        Mode::Authorized(id) => ResearchBatch::open_authorized_window(
            &input.ledger,
            &input.context,
            id,
            &input.cases[0].case_id,
        ),
        _ => ResearchBatch::open(&input.ledger, &input.context),
    }
    .map_err(|e| e.message)?;
    let window = batch.authorized_window();
    let progress = match &window {
        Some(value) => continuation_progress(
            value["base_consumed"]
                .as_u64()
                .ok_or("invalid window base")? as usize,
            batch.stats().map_err(|e| e.message)?.consumed,
        )?,
        None => 0,
    };
    let mut summaries = Vec::new();
    for case in input.cases {
        let mut diagnostic = None;
        let before = if recover.is_some() || progress > 0 {
            None
        } else {
            match checked_identity(&case.request) {
                Ok(value) => Some(value),
                Err(error) => {
                    diagnostic = Some(error);
                    None
                }
            }
        };
        let mut runs = Vec::new();
        if progress > 0 {
            let base = window.as_ref().ok_or("missing window")?["base_consumed"]
                .as_u64()
                .ok_or("invalid window base")?;
            for offset in 0..progress {
                runs.push(
                    batch
                        .load_outcome(base + offset as u64 + 1, &case.request)
                        .map_err(|e| e.message)?
                        .ok_or("recorded continuation outcome unknown")?,
                );
            }
        }
        let mut stop = diagnostic.is_some();
        if !stop {
            for (offset, purpose) in [CallPurpose::Execution, CallPurpose::Replay]
                .into_iter()
                .enumerate()
                .skip(progress)
            {
                let result = if let Some(start) = recover {
                    batch
                        .load_outcome(start + offset as u64, &case.request)
                        .map_err(|e| e.message)?
                        .ok_or("recorded call outcome unknown")?
                } else {
                    batch.run(
                        ProcessEngineAdapter::new(case.request.engine.clone()),
                        &case.case_id,
                        &case.request,
                        purpose,
                    )
                };
                stop = result
                    .as_ref()
                    .is_err_and(|e| e.code == "research_budget" || e.stage == "call_journal");
                runs.push(result);
                if stop {
                    break;
                }
            }
        }
        let replay_matches = replay_matches(&runs);
        let mut audits = Vec::new();
        if let Some(Ok(result)) = runs.first() {
            for frame in &result.events {
                if matches!(frame.opcode, 11..=16 | 18 | 19 | 24 | 26) {
                    let actual = parse_prompt(frame.sequence, &frame.raw)
                        .and_then(|p| p.ok_or("production unsupported".into()))
                        .map(|p| p.actions.into_iter().map(|a| a.bytes).collect::<Vec<_>>());
                    let audit = actual
                        .as_ref()
                        .map_err(Clone::clone)
                        .and_then(|actual| audit_prompt_responses(&frame.raw, actual));
                    audits.push(json!({"sequence":frame.sequence,"opcode":frame.opcode,"raw":frame.raw,"actual_response_bytes":actual,"audit":audit}));
                }
            }
        }
        let after = if recover.is_some() || before.is_none() {
            None
        } else {
            match checked_identity(&case.request) {
                Ok(value) => Some(value),
                Err(error) => {
                    diagnostic = Some(error);
                    stop = true;
                    None
                }
            }
        };
        let assets_unchanged = before.is_some() && before == after;
        if recover.is_none() && !assets_unchanged {
            stop = true;
        }
        let observed = audits
            .iter()
            .filter_map(|v| v["opcode"].as_u64())
            .collect::<std::collections::BTreeSet<_>>();
        let unobserved = [11u64, 12, 13, 14, 15, 16, 18, 19, 24, 26]
            .into_iter()
            .filter(|v| !observed.contains(v))
            .collect::<Vec<_>>();
        let evidence = json!({"schema_version":1,"case_id":case.case_id,"request":case.request,"runs":runs,"prompt_audits":audits,"independent_replay_matches":replay_matches,"global_optimality":false,"assets_unchanged":assets_unchanged,"asset_identity_sha256":before.as_ref().map(|v|digest(&serde_json::to_vec(v).unwrap())),"asset_capture_diagnostic":diagnostic,"recovered_call_ids":recover.map(|start|[start,start+1]),"unobserved_opcodes":unobserved,"search_gaps":["choices_per_parent truncation","bounded search frontier","unreached opcodes remain unqualified","ordering_equivalence_unproven","idle_shuffle_semantics_unaudited"],"ledger_sequence":batch.charged_sequence_id().map_err(|e|e.message)?});
        let stem = format!(
            "{}-{}",
            case.case_id,
            batch.stats().map_err(|e| e.message)?.consumed
        );
        let name =
            write_evidence_new(&input.output, &stem, &serde_json::to_vec_pretty(&evidence)?)?;
        summaries.push(json!({"case_id":case.case_id,"evidence":name,"replay_matches":replay_matches,"assets_unchanged":assets_unchanged,"diagnostic":diagnostic}));
        if stop {
            break;
        }
    }
    batch.verify().map_err(|e| e.message)?;
    let summary = json!({"schema_version":1,"cases":summaries,"ledger":batch.stats().map_err(|e|e.message)?,"authorized_window":batch.authorized_window(),"global_optimality":false});
    write_evidence_new(
        &input.output,
        &format!("summary-{}", batch.stats().map_err(|e| e.message)?.consumed),
        &serde_json::to_vec_pretty(&summary)?,
    )?;
    println!("{}", serde_json::to_string_pretty(&summary)?);
    Ok(())
}
fn replay_matches(runs: &[Result<DuelResult, WorkerError>]) -> bool {
    match (runs.first(), runs.get(1)) {
        (Some(Ok(a)), Some(Ok(b))) => {
            a.events == b.events
                && a.checkpoint == b.checkpoint
                && a.loaded_scripts == b.loaded_scripts
        }
        _ => false,
    }
}
fn checked_identity(request: &RunDuelRequest) -> Result<Value, String> {
    let identity = capture_engine_identity(&request.engine)?;
    if identity["consistent"] != true {
        return Err("inconsistent runtime assets".into());
    }
    let versions = serde_json::to_value(&request.versions).map_err(|e| e.to_string())?;
    for (role, key) in [
        ("dll", "engine_sha256"),
        ("cdb", "cdb_sha256"),
        ("script_manifest", "scripts_sha256"),
    ] {
        if identity["roles"][role]["sha256"] != versions[key] {
            return Err(format!("request {key} differs from actual asset identity"));
        }
    }
    Ok(identity)
}
fn safe_output(path: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    let base = std::env::current_dir()?.join("data/runtime");
    let relative = path
        .strip_prefix(&base)
        .map_err(|_| "research output must be below workspace data/runtime")?;
    if !relative.components().any(|c| c.as_os_str() == "research")
        || path
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
    {
        return Err("dedicated research output required".into());
    }
    let mut current = PathBuf::new();
    for component in path.components() {
        current.push(component);
        if let Ok(meta) = fs::symlink_metadata(&current) {
            if meta.file_type().is_symlink() {
                return Err("linked research output rejected".into());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if meta.file_attributes() & 0x400 != 0 {
                    return Err("reparse research output rejected".into());
                }
            }
        }
    }
    Ok(())
}
fn write_evidence_new(
    directory: &std::path::Path,
    stem: &str,
    bytes: &[u8],
) -> Result<String, Box<dyn std::error::Error>> {
    use std::io::Write;
    if !stem.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'-') {
        return Err("invalid evidence stem".into());
    }
    safe_output(directory)?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)?
        .as_nanos();
    for attempt in 0..1000 {
        let name = format!("{stem}-{stamp}-{attempt}.json");
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(directory.join(&name))
        {
            Ok(mut file) => {
                file.write_all(bytes)?;
                file.sync_all()?;
                return Ok(name);
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err("cannot allocate evidence filename".into())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn explicit_modes_reject_unknown_or_extra_arguments() {
        let parse =
            |args: &[&str]| parse_mode(&args.iter().map(|s| s.to_string()).collect::<Vec<_>>());
        assert_eq!(parse(&["runner", "input"]).unwrap(), Mode::Execute);
        assert_eq!(
            parse(&["runner", "input", "--recover", "5"]).unwrap(),
            Mode::Recover(5)
        );
        assert_eq!(
            parse(&["runner", "input", "--authorized-window", "resume"]).unwrap(),
            Mode::Authorized("resume".into())
        );
        for args in [
            vec!["runner"],
            vec!["runner", "input", "unknown"],
            vec!["runner", "input", "--recover"],
            vec!["runner", "input", "--authorized-window", "resume", "extra"],
        ] {
            assert!(parse(&args).is_err());
        }
    }
    #[test]
    fn resumed_progress_restores_execution_without_charging_it_twice() {
        assert_eq!(continuation_progress(7, 7).unwrap(), 0);
        assert_eq!(continuation_progress(7, 8).unwrap(), 1);
        assert_eq!(continuation_progress(7, 9).unwrap(), 2);
        assert!(continuation_progress(7, 6).is_err());
        assert!(continuation_progress(7, 10).is_err());
    }
    #[test]
    fn repeated_zero_charge_evidence_never_overwrites_original() {
        std::env::set_current_dir(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
            .unwrap();
        let path = std::env::current_dir()
            .unwrap()
            .join("data/runtime/research")
            .join(format!("evidence-test-{}", std::process::id()));
        fs::create_dir_all(&path).unwrap();
        let original = write_evidence_new(&path, "case-512", b"original").unwrap();
        let later = write_evidence_new(&path, "case-512", b"budget-exhausted").unwrap();
        assert_ne!(original, later);
        assert_eq!(fs::read(path.join(original)).unwrap(), b"original");
        assert!(write_evidence_new(&path, "../escape", b"x").is_err());
        assert!(
            safe_output(&std::env::current_dir().unwrap().join("data/runtime/script")).is_err()
        );
        assert!(!replay_matches(&[]));
        assert!(!replay_matches(&[Err(WorkerError::new(
            "research_budget",
            "research",
            "stopped"
        ))]));
    }
}
