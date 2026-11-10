#[path = "p4_r1b3/harness.rs"]
mod harness;

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    env,
    fs::{self, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Arc,
    thread,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};
use ygo_engine_adapter::{
    CallJournal, CallPurpose, DuelResult, EngineAdapter, JournaledAdapter, LedgerStats,
    ProcessEngineAdapter, RunDuelRequest,
};
use ygo_goal::{verify_query_replays, AuditedQueries, Goal, QueryWitness};
use ygo_planner::first_turn::{
    advance_resumable_partial_execution_v1, advance_resumable_query_audit_v1,
    begin_resumable_partial_execution_v1, execute_partial, replay_partial_execution,
    resume_resumable_partial_execution_v1, ForecastPlan, PartialExecution, ResumableAuditStatusV1,
    ResumableExecutionPhaseV1, ResumablePartialExecutionV1,
};

const JOURNAL_LIMIT: usize = harness::SCOPE_LIMIT;
const MARKER_WAIT: Duration = Duration::from_secs(harness::MAX_HANDSHAKE_SECONDS);
const CHECKPOINT_PREFIX: &str = "execution-loop-v1/";

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
struct SourceFileIdentity {
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
struct SourceIdentity {
    head: String,
    tracked_diff_sha256: String,
    cargo_lock_sha256: String,
    participating_sources: Vec<SourceFileIdentity>,
    rustc: String,
    cargo: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct RunManifest {
    schema_version: u16,
    run_id: String,
    run_dir: PathBuf,
    output_root: PathBuf,
    resume_scope: String,
    replay_scope: String,
    resume_context: String,
    replay_context: String,
    input_identity: harness::InputIdentity,
    source_identity: SourceIdentity,
    worker_sha256: String,
    driver_sha256: String,
    request: RunDuelRequest,
    plan: ForecastPlan,
    goal: Goal,
    queries: Vec<QueryWitness>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
struct BlobIdentity {
    path: String,
    bytes: u64,
    sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
struct JournalSnapshot {
    journal_bytes: u64,
    journal_sha256: String,
    blobs: Vec<BlobIdentity>,
    stats: LedgerStats,
    reservations: BTreeMap<String, usize>,
    unresolved_calls: Vec<u64>,
    charged_sequence_id: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct PauseMarker {
    schema_version: u16,
    run_id: String,
    scope: String,
    context: String,
    request_sha256: String,
    plan_sha256: String,
    plan_id: String,
    worker_sha256: String,
    asset_tree_sha256: String,
    execution_id: String,
    checkpoint_sha256: String,
    phase: ResumableExecutionPhaseV1,
    semantic_step: usize,
    pending: Option<Value>,
    worker_in_flight: bool,
    journal: JournalSnapshot,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ScopeProjection {
    scope: String,
    context: String,
    input_identity: harness::InputIdentity,
    plan: ForecastPlan,
    state: Value,
    result: DuelResult,
    journal: JournalSnapshot,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct ReplayProjection {
    scope: String,
    context: String,
    input_identity: harness::InputIdentity,
    plan: ForecastPlan,
    report: PartialExecution,
    audited_query_call_ids: Vec<u64>,
    journal: JournalSnapshot,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
struct Comparison {
    schema_version: u16,
    run_id: String,
    plan_equal: bool,
    semantic_steps_equal: bool,
    choices_and_mapping_history_equal: bool,
    predictions_equal: bool,
    query_witnesses_equal: bool,
    final_result_same_native: bool,
    recovery_ledger: JournalSnapshot,
    replay_ledger: JournalSnapshot,
    qualification: String,
}

fn repo_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|error| error.to_string())
}

fn now_epoch_seconds() -> Result<u64, String> {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_secs())
        .map_err(|error| format!("system clock is before Unix epoch: {error}"))
}

fn unique_run_id() -> Result<String, String> {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_nanos();
    Ok(format!("p4-r1b3-{}-{nanos}", std::process::id()))
}

fn command_output(root: &Path, program: &str, args: &[&str]) -> Result<String, String> {
    let output = Command::new(program)
        .args(args)
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to run {program}: {error}"))?;
    if !output.status.success() {
        return Err(format!(
            "{program} {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr).trim()
        ));
    }
    String::from_utf8(output.stdout)
        .map(|value| value.trim().to_owned())
        .map_err(|error| format!("{program} output is not UTF-8: {error}"))
}

fn source_identity(root: &Path) -> Result<(SourceIdentity, Vec<u8>), String> {
    let head = command_output(root, "git", &["rev-parse", "HEAD"])?;
    let diff = Command::new("git")
        .args(["diff", "--binary", "HEAD"])
        .current_dir(root)
        .output()
        .map_err(|error| format!("failed to capture tracked source diff: {error}"))?;
    if !diff.status.success() {
        return Err(format!(
            "git diff failed: {}",
            String::from_utf8_lossy(&diff.stderr).trim()
        ));
    }
    let mut source_paths = vec![
        "crates/ygo-planner/Cargo.toml",
        "crates/ygo-planner/examples/p4-r1b3-native-resume.rs",
        "crates/ygo-planner/examples/p4_r1b3/harness.rs",
        "crates/ygo-planner/tests/p4_r1b3_harness.rs",
    ];
    source_paths.sort_unstable();
    let participating_sources = source_paths
        .into_iter()
        .map(|relative| {
            let bytes = fs::read(root.join(relative))
                .map_err(|error| format!("cannot hash participating source {relative}: {error}"))?;
            Ok(SourceFileIdentity {
                path: relative.to_owned(),
                sha256: harness::digest(&bytes),
            })
        })
        .collect::<Result<Vec<_>, String>>()?;
    let cargo_lock = fs::read(root.join("Cargo.lock"))
        .map_err(|error| format!("cannot hash Cargo.lock: {error}"))?;
    let rustc = command_output(root, "rustc", &["--version"])?;
    let cargo = command_output(root, "cargo", &["--version"])?;
    Ok((
        SourceIdentity {
            head,
            tracked_diff_sha256: harness::digest(&diff.stdout),
            cargo_lock_sha256: harness::digest(&cargo_lock),
            participating_sources,
            rustc,
            cargo,
        },
        diff.stdout,
    ))
}

fn require_source_identity(root: &Path, expected: &SourceIdentity) -> Result<(), String> {
    let (found, _) = source_identity(root)?;
    if &found == expected {
        Ok(())
    } else {
        Err(format!(
            "source/build identity changed: expected {expected:?}, found {found:?}"
        ))
    }
}

fn write_new(path: &Path, bytes: &[u8]) -> Result<(), String> {
    harness::reject_existing_symlink(path)?;
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
        harness::reject_existing_symlink(parent)?;
    }
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)
        .map_err(|error| format!("cannot create {}: {error}", path.display()))?;
    file.write_all(bytes).map_err(|error| error.to_string())?;
    file.sync_all().map_err(|error| error.to_string())
}

fn write_new_json<T: Serialize>(path: &Path, value: &T) -> Result<Vec<u8>, String> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    write_new(path, &bytes)?;
    Ok(bytes)
}

fn write_atomic_new_json<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let bytes = serde_json::to_vec_pretty(value).map_err(|error| error.to_string())?;
    harness::reject_existing_symlink(path)?;
    if path.exists() {
        return Err(format!(
            "refusing to replace existing marker {}",
            path.display()
        ));
    }
    let parent = path.parent().ok_or("marker has no parent directory")?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let temp = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("marker"),
        unique_run_id()?
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("cannot create marker staging file: {error}"))?;
    file.write_all(&bytes).map_err(|error| error.to_string())?;
    file.sync_all().map_err(|error| error.to_string())?;
    drop(file);
    if path.exists() {
        return Err(format!(
            "refusing to replace existing marker {}",
            path.display()
        ));
    }
    fs::rename(&temp, path).map_err(|error| format!("atomic marker rename failed: {error}"))
}

fn create_run_dir(path: &Path) -> Result<(), String> {
    harness::reject_existing_symlink(path)?;
    let parent = path.parent().ok_or("run directory has no parent")?;
    fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    harness::reject_existing_symlink(parent)?;
    fs::create_dir(path).map_err(|error| {
        format!(
            "run directory already exists or cannot be created {}: {error}",
            path.display()
        )
    })
}

fn collect_blob_identities(
    root: &Path,
    dir: &Path,
    found: &mut Vec<BlobIdentity>,
) -> Result<(), String> {
    if !dir.exists() {
        return Ok(());
    }
    if fs::symlink_metadata(dir)
        .map_err(|error| error.to_string())?
        .file_type()
        .is_symlink()
    {
        return Err(format!(
            "journal blob root symlink is forbidden: {}",
            dir.display()
        ));
    }
    for entry in fs::read_dir(dir).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let kind = entry.file_type().map_err(|error| error.to_string())?;
        if kind.is_symlink() {
            return Err(format!(
                "journal blob symlink is forbidden: {}",
                entry.path().display()
            ));
        }
        if kind.is_dir() {
            collect_blob_identities(root, &entry.path(), found)?;
        } else if kind.is_file() {
            let bytes = fs::read(entry.path()).map_err(|error| error.to_string())?;
            let relative = entry
                .path()
                .strip_prefix(root)
                .map_err(|error| error.to_string())?
                .to_string_lossy()
                .replace('\\', "/");
            found.push(BlobIdentity {
                path: relative,
                bytes: bytes.len() as u64,
                sha256: harness::digest(&bytes),
            });
        } else {
            return Err(format!(
                "unexpected journal blob entry: {}",
                entry.path().display()
            ));
        }
    }
    Ok(())
}

fn journal_snapshot(
    path: &Path,
    scope: &str,
    context: &str,
    limit: usize,
) -> Result<JournalSnapshot, String> {
    let readonly = CallJournal::inspect_existing(path, scope, context, limit)
        .map_err(|error| error.message)?
        .ok_or_else(|| format!("journal missing: {}", path.display()))?;
    readonly.verify().map_err(|error| error.message)?;
    let stats = readonly.stats().map_err(|error| error.message)?;
    let reservations = readonly
        .reservation_state()
        .map_err(|error| error.message)?;
    let unresolved_calls = readonly.unresolved_calls().map_err(|error| error.message)?;
    let charged_sequence_id = readonly
        .charged_sequence_id()
        .map_err(|error| error.message)?;
    drop(readonly);
    let journal_bytes = fs::read(path).map_err(|error| error.to_string())?;
    let mut blobs = Vec::new();
    let mut blob_root_name = path.as_os_str().to_owned();
    blob_root_name.push(".blobs");
    let blob_root = PathBuf::from(blob_root_name);
    collect_blob_identities(&blob_root, &blob_root, &mut blobs)?;
    blobs.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(JournalSnapshot {
        journal_bytes: journal_bytes.len() as u64,
        journal_sha256: harness::digest(&journal_bytes),
        blobs,
        stats,
        reservations,
        unresolved_calls,
        charged_sequence_id,
    })
}

fn same_native(left: &DuelResult, right: &DuelResult) -> bool {
    let mut left = left.clone();
    let mut right = right.clone();
    left.peak_working_set_bytes = None;
    right.peak_working_set_bytes = None;
    serde_json::to_value(left).ok() == serde_json::to_value(right).ok()
}

fn checkpoint_value(journal: &CallJournal, execution_id: &str) -> Result<Value, String> {
    journal
        .checkpoint(&format!("{CHECKPOINT_PREFIX}{execution_id}"))
        .map_err(|error| error.message)?
        .ok_or_else(|| "resumable execution checkpoint missing".into())
}

fn checkpoint_state_from_value(value: Value) -> Result<ResumablePartialExecutionV1, String> {
    serde_json::from_value(value).map_err(|error| error.to_string())
}

fn check_window(run_dir: &Path) -> Result<(), String> {
    let start: Value = serde_json::from_slice(
        &fs::read(run_dir.join("window-start.json")).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;
    let started = start
        .get("epoch_seconds")
        .and_then(Value::as_u64)
        .ok_or("window start timestamp missing")?;
    let now = now_epoch_seconds()?;
    if now < started {
        return Err("system clock moved backwards during the experiment".into());
    }
    if now - started > harness::MAX_WINDOW_SECONDS {
        return Err("the single experiment window expired".into());
    }
    Ok(())
}

fn assert_accounting(snapshot: &JournalSnapshot) -> Result<(), String> {
    if snapshot.stats.consumed != snapshot.stats.completed
        || snapshot.stats.unknown != 0
        || snapshot.stats.reserved != 0
        || snapshot.stats.abandoned != 0
        || !snapshot.reservations.is_empty()
        || !snapshot.unresolved_calls.is_empty()
    {
        return Err(format!(
            "ledger has unresolved or unknown consumption: {snapshot:?}"
        ));
    }
    Ok(())
}

fn manifest_path(run_dir: &Path) -> PathBuf {
    run_dir.join("manifest.json")
}

fn load_manifest(path: &Path) -> Result<RunManifest, String> {
    let bytes = fs::read(path).map_err(|error| error.to_string())?;
    serde_json::from_slice(&bytes).map_err(|error| error.to_string())
}

fn saved_queries_match_current_except_opponent_counts(
    saved: &[QueryWitness],
    current: &[QueryWitness],
) -> bool {
    saved.len() == current.len()
        && saved.iter().zip(current).all(|(saved, current)| {
            saved.event == current.event
                && saved.raw_prefix_sha256 == current.raw_prefix_sha256
                && saved.decisions_sha256 == current.decisions_sha256
                && saved.public.visible == current.public.visible
                && saved.public.own_deck_counts == current.public.own_deck_counts
        })
}

fn inspect_initial_run(root: &Path, run_dir: &Path) -> Result<Value, String> {
    harness::reject_existing_symlink(run_dir)?;
    let manifest_file = manifest_path(run_dir);
    let manifest = load_manifest(&manifest_file)?;
    let actual_run_dir = run_dir.canonicalize().map_err(|error| error.to_string())?;
    let recorded_run_dir = manifest
        .run_dir
        .canonicalize()
        .map_err(|error| error.to_string())?;
    if actual_run_dir != recorded_run_dir || manifest.schema_version != 1 {
        return Err("run directory or manifest version does not match".into());
    }
    let prepared = harness::prepare_for_run(root, &manifest.output_root, &manifest.run_id)?;
    let saved_input_identity_matches = prepared.identity == manifest.input_identity;
    let saved_plan_matches_current = serde_json::to_value(&prepared.plan)
        .map_err(|error| error.to_string())?
        == serde_json::to_value(&manifest.plan).map_err(|error| error.to_string())?;
    let mut saved_identity_with_current_reconstruction = manifest.input_identity.clone();
    saved_identity_with_current_reconstruction.queries_sha256 =
        prepared.identity.queries_sha256.clone();
    saved_identity_with_current_reconstruction.start_observation_sha256 =
        prepared.identity.start_observation_sha256.clone();
    saved_identity_with_current_reconstruction.plan_sha256 = prepared.identity.plan_sha256.clone();
    saved_identity_with_current_reconstruction.plan_id = prepared.identity.plan_id.clone();
    let saved_identity_matches_except_reconstruction =
        saved_identity_with_current_reconstruction == prepared.identity;
    let saved_request_matches_current = serde_json::to_value(&prepared.request)
        .map_err(|error| error.to_string())?
        == serde_json::to_value(&manifest.request).map_err(|error| error.to_string())?;
    let saved_query_prefixes_match =
        saved_queries_match_current_except_opponent_counts(&manifest.queries, &prepared.queries);
    if !saved_identity_matches_except_reconstruction
        || !saved_request_matches_current
        || !saved_query_prefixes_match
    {
        return Err(format!(
            "saved run differs from fixed native query inputs: identity_core={saved_identity_matches_except_reconstruction}, request={saved_request_matches_current}, query_prefixes={saved_query_prefixes_match}"
        ));
    }
    let journal_path = &prepared.resume_journal_path;
    let readonly = CallJournal::inspect_existing(
        journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?
    .ok_or("saved resume ledger missing")?;
    readonly.verify().map_err(|error| error.message)?;
    let snapshot = journal_snapshot(
        journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&snapshot)?;
    if snapshot.stats.consumed != 1
        || snapshot.stats.completed != 1
        || readonly.call_purpose(1).map_err(|error| error.message)? != CallPurpose::Execution
    {
        return Err(format!(
            "saved initial ledger has unexpected accounting: {snapshot:?}"
        ));
    }
    let outcome = readonly
        .load_outcome(1, &prepared.request)
        .map_err(|error| error.message)?
        .ok_or("initial execution result is not complete")?;
    let result = outcome.map_err(|error| format!("initial execution ended with {}", error.code))?;
    harness::validate_initial_result(&prepared, &result)?;
    let result_bytes = fs::read(prepared.run_dir.join("resume/initial-result.json"))
        .map_err(|error| error.to_string())?;
    let stored_result: DuelResult =
        serde_json::from_slice(&result_bytes).map_err(|error| error.to_string())?;
    if !same_native(&stored_result, &result) {
        return Err("saved result projection differs from the authenticated journal result".into());
    }
    let (current_source, _) = source_identity(root)?;
    let current_driver = env::current_exe().map_err(|error| error.to_string())?;
    let current_driver_sha256 = harness::sha256_file(root, &current_driver)?;
    let journal_text = fs::read_to_string(journal_path).map_err(|error| error.to_string())?;
    Ok(json!({
        "run_id": manifest.run_id,
        "run_dir": actual_run_dir,
        "read_only_journal_chain_and_blobs_verified": true,
        "ledger": snapshot,
        "initial_event49_witness_matches_fixed_fixture": true,
        "saved_input_identity_matches_current_fixed_inputs": saved_input_identity_matches,
        "saved_input_identity_matches_except_reconstructed_query_observation_and_plan": saved_identity_matches_except_reconstruction,
        "saved_plan_matches_current_reconstructed_plan": saved_plan_matches_current,
        "saved_queries_match_current_trace_witnesses_except_opponent_counts": true,
        "saved_event49_opponent_deck_count": manifest.queries.iter().find(|query| query.event == 49).map(|query| query.public.opponent_deck_count),
        "current_event49_opponent_deck_count": prepared.queries.iter().find(|query| query.event == 49).map(|query| query.public.opponent_deck_count),
        "saved_event49_opponent_hand_count": manifest.queries.iter().find(|query| query.event == 49).map(|query| query.public.opponent_hand_count),
        "current_event49_opponent_hand_count": prepared.queries.iter().find(|query| query.event == 49).map(|query| query.public.opponent_hand_count),
        "initial_result_sha256": harness::digest(&result_bytes),
        "journal_record_lines": journal_text.lines().count(),
        "current_source_matches_saved_run": current_source == manifest.source_identity,
        "current_driver_sha256": current_driver_sha256,
        "current_driver_matches_saved_run": current_driver_sha256 == manifest.driver_sha256,
        "pause_marker_exists": manifest.run_dir.join("pause-marker.json").exists(),
        "coordinator_kill_record_exists": manifest.run_dir.join("coordinator-termination.json").exists(),
        "replay_scope_exists": prepared.replay_journal_path.exists(),
        "internal_ffi_call_count": "unavailable",
        "mode": "read_only_inspection",
    }))
}

fn write_failure(run_dir: &Path, scope: &str, stage: &str, error: &str) {
    let record = json!({
        "schema_version": 1,
        "scope": scope,
        "stage": stage,
        "error": error,
        "recorded_epoch_seconds": now_epoch_seconds().ok(),
    });
    let _ = write_new_json(
        &run_dir.join(format!("{scope}-{stage}-failure.json")),
        &record,
    );
}

fn expected_manifest(
    root: &Path,
    prepared: &harness::Prepared,
) -> Result<(RunManifest, Vec<u8>), String> {
    let (source_identity, diff) = source_identity(root)?;
    let worker_sha256 = harness::sha256_file(root, &prepared.worker_path)?;
    let driver_path = env::current_exe().map_err(|error| error.to_string())?;
    let driver_sha256 = harness::sha256_file(root, &driver_path)?;
    let resume_scope = format!("{}-resume", prepared.run_id);
    let replay_scope = format!("{}-replay", prepared.run_id);
    let resume_context = format!(
        "p4-r1b3-resume:{}:{}",
        prepared.run_id, prepared.identity.request_sha256
    );
    let replay_context = format!(
        "p4-r1b3-replay:{}:{}",
        prepared.run_id, prepared.identity.request_sha256
    );
    Ok((
        RunManifest {
            schema_version: 1,
            run_id: prepared.run_id.clone(),
            run_dir: prepared.run_dir.clone(),
            output_root: prepared.output_root.clone(),
            resume_scope,
            replay_scope,
            resume_context,
            replay_context,
            input_identity: prepared.identity.clone(),
            source_identity,
            worker_sha256,
            driver_sha256,
            request: prepared.request.clone(),
            plan: prepared.plan.clone(),
            goal: prepared.goal.clone(),
            queries: prepared.queries.clone(),
        },
        diff,
    ))
}

fn prepare_only(root: &Path, output_root: &Path) -> Result<Value, String> {
    let prepared = harness::prepare(root, output_root)?;
    let result = prepared.summary();
    println!(
        "{}",
        serde_json::to_string_pretty(&result).map_err(|error| error.to_string())?
    );
    Ok(result)
}

fn run_initial_and_query_audit(
    prepared: &harness::Prepared,
    journal: Arc<CallJournal>,
    evidence_dir: &Path,
) -> Result<(DuelResult, AuditedQueries, u64), String> {
    let next = journal.stats().map_err(|error| error.message)?.consumed + 1;
    if next != 1 {
        return Err(format!(
            "fresh scope expected initial call 1, found next call {next}"
        ));
    }
    let initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(prepared.request.engine.clone()),
        journal.clone(),
        CallPurpose::Execution,
    )
    .run(&prepared.request)
    .map_err(|error| {
        format!(
            "initial native call failed: {}: {}",
            error.code, error.message
        )
    })?;
    write_new_json(&evidence_dir.join("initial-result.json"), &initial)?;
    if let Err(error) = harness::validate_initial_result(prepared, &initial) {
        write_failure(
            &prepared.run_dir,
            "resume",
            "initial-result-mismatch",
            &error,
        );
        return Err(error);
    }
    let initial_call = 1;
    let receipt = verify_query_replays(
        &prepared.request,
        &initial,
        &prepared.queries,
        journal.clone(),
    )?;
    if !receipt.matches(&prepared.request, &initial, &prepared.queries) {
        return Err("initial query replay receipt does not bind the fixed input".into());
    }
    write_new_json(
        &evidence_dir.join("initial-query-audit.json"),
        &json!({
            "query_events": prepared.queries.iter().map(|query| query.event).collect::<Vec<_>>(),
            "call_ids": receipt.call_ids,
            "root_bound": true,
        }),
    )?;
    let stats = journal.stats().map_err(|error| error.message)?;
    if stats.unknown != 0 || stats.reserved != 0 || stats.consumed != stats.completed {
        return Err(format!(
            "initial query audit left uncertain accounting: {stats:?}"
        ));
    }
    Ok((initial, receipt, initial_call))
}

fn verify_manifest_runtime(
    root: &Path,
    manifest: &RunManifest,
) -> Result<harness::Prepared, String> {
    require_source_identity(root, &manifest.source_identity)?;
    let prepared = harness::prepare_for_run(root, &manifest.output_root, &manifest.run_id)?;
    if harness::sha256_file(root, &prepared.worker_path)? != manifest.worker_sha256 {
        return Err("isolated worker executable hash changed".into());
    }
    let current_exe = env::current_exe().map_err(|error| error.to_string())?;
    if harness::sha256_file(root, &current_exe)? != manifest.driver_sha256 {
        return Err("experiment driver executable hash changed".into());
    }
    if prepared.identity != manifest.input_identity
        || serde_json::to_value(&prepared.request).map_err(|error| error.to_string())?
            != serde_json::to_value(&manifest.request).map_err(|error| error.to_string())?
        || serde_json::to_value(&prepared.plan).map_err(|error| error.to_string())?
            != serde_json::to_value(&manifest.plan).map_err(|error| error.to_string())?
    {
        return Err("reconstructed fixed input or forecast differs from the run manifest".into());
    }
    Ok(prepared)
}

fn stop_requested(run_dir: &Path) -> bool {
    run_dir.join("stop-request").exists()
}

fn run_resume_child(manifest_file: &Path) -> Result<(), String> {
    let manifest = load_manifest(manifest_file)?;
    let root = repo_root()?;
    check_window(&manifest.run_dir)?;
    let prepared = verify_manifest_runtime(&root, &manifest)?;
    let journal = CallJournal::open(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?;
    let (initial, receipt, initial_call) =
        run_initial_and_query_audit(&prepared, journal.clone(), &prepared.run_dir.join("resume"))?;
    check_window(&manifest.run_dir)?;
    if stop_requested(&manifest.run_dir) {
        return Err("parent requested a safe stop before the semantic pause marker".into());
    }
    let mut state = begin_resumable_partial_execution_v1(
        &prepared.request,
        initial_call,
        &prepared.queries,
        &receipt,
        &prepared.plan,
        &prepared.catalog,
        &prepared.pack,
        &prepared.goal,
        journal.clone(),
    )?;
    if state
        .inner
        .progress
        .last_completed_result
        .as_ref()
        .map_or(true, |value| !same_native(value, &initial))
    {
        return Err("begin checkpoint does not bind the charged initial result".into());
    }
    while state.semantic_step < 1 {
        check_window(&manifest.run_dir)?;
        if stop_requested(&manifest.run_dir) {
            return Err("parent requested a safe stop before the first semantic action".into());
        }
        if state.phase != ResumableExecutionPhaseV1::Semantic {
            return Err(format!("unexpected phase before pause: {:?}", state.phase));
        }
        advance_resumable_partial_execution_v1(
            &mut state,
            &prepared.plan,
            &prepared.catalog,
            &prepared.pack,
            &prepared.goal,
            journal.clone(),
        )?;
        if state.phase == ResumableExecutionPhaseV1::Blocked {
            return Err(format!(
                "first semantic action blocked: {:?}",
                state.diagnostic
            ));
        }
        if state.semantic_step > 1 {
            return Err("first advance crossed the approved semantic pause boundary".into());
        }
    }
    if state.phase != ResumableExecutionPhaseV1::Semantic
        || state.semantic_step != 1
        || state.pending.is_some()
        || state.predictions.len() != 1
        || state.predictions[0].selected.rule_id != prepared.expected_route[0]
    {
        return Err("resumable state did not stop at the exact first semantic boundary".into());
    }
    let stats = journal.stats().map_err(|error| error.message)?;
    if stats.consumed != stats.completed
        || stats.unknown != 0
        || stats.reserved != 0
        || !journal
            .unresolved_calls()
            .map_err(|error| error.message)?
            .is_empty()
    {
        return Err(format!(
            "pause boundary has unresolved accounting: {stats:?}"
        ));
    }
    let execution_id = state.execution_id.clone();
    let saved = checkpoint_value(&journal, &execution_id)?;
    if saved != serde_json::to_value(&state).map_err(|error| error.to_string())? {
        return Err("persisted pause checkpoint differs from live state".into());
    }
    drop(journal);
    let journal = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&journal)?;
    let marker = PauseMarker {
        schema_version: 1,
        run_id: manifest.run_id.clone(),
        scope: manifest.resume_scope.clone(),
        context: manifest.resume_context.clone(),
        request_sha256: manifest.input_identity.request_sha256.clone(),
        plan_sha256: manifest.input_identity.plan_sha256.clone(),
        plan_id: manifest.input_identity.plan_id.clone(),
        worker_sha256: manifest.worker_sha256.clone(),
        asset_tree_sha256: manifest.input_identity.asset_tree_sha256.clone(),
        execution_id,
        checkpoint_sha256: harness::hash_json(&saved)?,
        phase: state.phase,
        semantic_step: state.semantic_step,
        pending: state
            .pending
            .as_ref()
            .map(serde_json::to_value)
            .transpose()
            .map_err(|error| error.to_string())?,
        worker_in_flight: false,
        journal,
    };
    if stop_requested(&manifest.run_dir) {
        write_failure(
            &manifest.run_dir,
            "resume",
            "handshake-stopped",
            "stop requested before marker publication",
        );
        return Err("parent requested stop before marker publication".into());
    }
    write_atomic_new_json(&manifest.run_dir.join("pause-marker.json"), &marker)?;
    let mut byte = [0u8; 1];
    std::io::stdin()
        .read_exact(&mut byte)
        .map_err(|error| format!("pause gate closed before parent decision: {error}"))?;
    Ok(())
}

fn authenticate_pause_marker(
    manifest: &RunManifest,
    prepared: &harness::Prepared,
) -> Result<PauseMarker, String> {
    let marker_path = manifest.run_dir.join("pause-marker.json");
    let marker_bytes = fs::read(&marker_path).map_err(|error| error.to_string())?;
    let marker: PauseMarker =
        serde_json::from_slice(&marker_bytes).map_err(|error| error.to_string())?;
    if marker.schema_version != 1
        || marker.run_id != manifest.run_id
        || marker.scope != manifest.resume_scope
        || marker.context != manifest.resume_context
        || marker.request_sha256 != manifest.input_identity.request_sha256
        || marker.plan_sha256 != manifest.input_identity.plan_sha256
        || marker.plan_id != manifest.input_identity.plan_id
        || marker.worker_sha256 != manifest.worker_sha256
        || marker.asset_tree_sha256 != manifest.input_identity.asset_tree_sha256
        || marker.phase != ResumableExecutionPhaseV1::Semantic
        || marker.semantic_step != 1
        || marker.pending.is_some()
        || marker.worker_in_flight
    {
        return Err("pause marker identity or settled-boundary fields differ".into());
    }
    let live_snapshot = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&live_snapshot)?;
    if live_snapshot != marker.journal {
        return Err("read-only journal authentication differs from pause marker".into());
    }
    let readonly = CallJournal::inspect_existing(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?
    .ok_or("resume journal missing during marker authentication")?;
    readonly.verify().map_err(|error| error.message)?;
    let value = readonly
        .checkpoint(&format!("{CHECKPOINT_PREFIX}{}", marker.execution_id))
        .map_err(|error| error.message)?
        .ok_or("pause checkpoint missing during marker authentication")?;
    let state = checkpoint_state_from_value(value.clone())?;
    if harness::hash_json(&value)? != marker.checkpoint_sha256
        || state.execution_id != marker.execution_id
        || state.phase != ResumableExecutionPhaseV1::Semantic
        || state.semantic_step != 1
        || state.pending.is_some()
        || state.predictions.len() != 1
        || state.predictions[0].selected.rule_id != prepared.expected_route[0]
        || state.inner.progress.ledger != marker.journal.stats
    {
        return Err("authenticated journal checkpoint does not match the settled marker".into());
    }
    Ok(marker)
}

fn request_safe_child_stop(child: &mut Child, run_dir: &Path) {
    let _ = write_new(run_dir.join("stop-request").as_path(), b"stop\n");
    if let Some(stdin) = child.stdin.as_mut() {
        let _ = stdin.write_all(&[1]);
        let _ = stdin.flush();
    }
}

fn wait_for_pause_marker(
    child: &mut Child,
    manifest: &RunManifest,
    prepared: &harness::Prepared,
) -> Result<PauseMarker, String> {
    let start = Instant::now();
    loop {
        if manifest.run_dir.join("pause-marker.json").is_file() {
            match authenticate_pause_marker(manifest, prepared) {
                Ok(marker) if start.elapsed() <= MARKER_WAIT => return Ok(marker),
                Ok(_) => {
                    request_safe_child_stop(child, &manifest.run_dir);
                    let _ = child.wait();
                    return Err("pause marker arrived after the bounded handshake timeout".into());
                }
                Err(error) => {
                    request_safe_child_stop(child, &manifest.run_dir);
                    let _ = child.wait();
                    return Err(format!("pause marker authentication failed: {error}"));
                }
            }
        }
        if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
            return Err(format!(
                "pause coordinator exited before marker with {status}"
            ));
        }
        if start.elapsed() > MARKER_WAIT {
            request_safe_child_stop(child, &manifest.run_dir);
            let stop_deadline = Instant::now() + Duration::from_secs(180);
            loop {
                if let Some(status) = child.try_wait().map_err(|error| error.to_string())? {
                    return Err(format!(
                        "pause handshake timed out; child exited safely with {status}"
                    ));
                }
                if Instant::now() >= stop_deadline {
                    return Err("pause handshake timed out; child did not reach a safe stop; process left for inspection".into());
                }
                thread::sleep(Duration::from_millis(100));
            }
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn launch_and_kill_at_pause(
    manifest: &RunManifest,
    prepared: &harness::Prepared,
) -> Result<PauseMarker, String> {
    let executable = env::current_exe().map_err(|error| error.to_string())?;
    if harness::sha256_file(&prepared.root, &executable)? != manifest.driver_sha256 {
        return Err(
            "driver binary changed immediately before launching the pause coordinator".into(),
        );
    }
    let mut child = Command::new(executable)
        .arg("--resume-child")
        .arg(manifest_path(&manifest.run_dir))
        .current_dir(&prepared.root)
        .stdin(Stdio::piped())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("cannot start pause coordinator: {error}"))?;
    let marker = match wait_for_pause_marker(&mut child, manifest, prepared) {
        Ok(marker) => marker,
        Err(error) => {
            write_failure(&manifest.run_dir, "resume", "pause-handshake", &error);
            return Err(error);
        }
    };
    // The complete marker and live read-only journal were authenticated above;
    // the child has dropped its exclusive journal handle and has no worker in flight.
    child
        .kill()
        .map_err(|error| format!("authenticated coordinator kill failed: {error}"))?;
    let status = child.wait().map_err(|error| error.to_string())?;
    write_new_json(
        &manifest.run_dir.join("coordinator-termination.json"),
        &json!({
            "authenticated_pause_marker": true,
            "marker_sha256": harness::digest(&fs::read(manifest.run_dir.join("pause-marker.json")).map_err(|error| error.to_string())?),
            "termination_status": status.to_string(),
            "termination_boundary": "semantic_step_1_settled_no_worker_in_flight",
        }),
    )?;
    Ok(marker)
}

fn continue_recovery_scope(
    manifest: &RunManifest,
    prepared: &harness::Prepared,
) -> Result<(ResumablePartialExecutionV1, JournalSnapshot), String> {
    check_window(&manifest.run_dir)?;
    let before_reopen = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&before_reopen)?;
    if before_reopen.stats.consumed >= JOURNAL_LIMIT {
        return Err("resume scope has no remaining charged call capacity".into());
    }
    let mut state = resume_resumable_partial_execution_v1(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
        &prepared.request,
        &prepared.plan,
        &prepared.catalog,
        &prepared.pack,
        &prepared.goal,
    )?;
    let after_reopen = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    if after_reopen != before_reopen {
        return Err(
            "resume reopen changed ledger bytes, blobs, accounting, or charged sequence".into(),
        );
    }
    let journal = CallJournal::open_existing_strict(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?
    .ok_or("resume scope disappeared after reopen")?;
    journal.verify().map_err(|error| error.message)?;
    let saved = checkpoint_value(&journal, &state.execution_id)?;
    if saved != serde_json::to_value(&state).map_err(|error| error.to_string())? {
        return Err("resume returned state differs from the authenticated checkpoint".into());
    }
    let mut call_index = 0usize;
    while state.phase != ResumableExecutionPhaseV1::Complete {
        check_window(&manifest.run_dir)?;
        let stats = journal.stats().map_err(|error| error.message)?;
        if stats.consumed >= JOURNAL_LIMIT {
            return Err(format!("resume scope exhausted its fixed limit: {stats:?}"));
        }
        if stats.unknown != 0
            || stats.reserved != 0
            || state.phase == ResumableExecutionPhaseV1::Blocked
        {
            return Err(format!(
                "resume scope reached an unsafe state: {state:?}; {stats:?}"
            ));
        }
        match state.phase {
            ResumableExecutionPhaseV1::Semantic | ResumableExecutionPhaseV1::EndPhase => {
                advance_resumable_partial_execution_v1(
                    &mut state,
                    &prepared.plan,
                    &prepared.catalog,
                    &prepared.pack,
                    &prepared.goal,
                    journal.clone(),
                )?;
            }
            ResumableExecutionPhaseV1::QueryAudit => {
                if state.audit.status != ResumableAuditStatusV1::Running {
                    return Err("query audit phase is not running".into());
                }
                advance_resumable_query_audit_v1(&mut state, journal.clone())?;
            }
            ResumableExecutionPhaseV1::Complete => break,
            ResumableExecutionPhaseV1::Blocked => return Err("resume loop became blocked".into()),
        }
        call_index += 1;
        check_window(&manifest.run_dir)?;
        let progress = json!({
            "phase": state.phase,
            "semantic_step": state.semantic_step,
            "audit_next_query": state.audit.next_query,
            "stats": journal.stats().map_err(|error| error.message)?,
            "state_sha256": harness::hash_json(&state)?,
        });
        write_new_json(
            &manifest
                .run_dir
                .join("resume")
                .join(format!("progress-{call_index:03}.json")),
            &progress,
        )?;
    }
    if state.audit.status != ResumableAuditStatusV1::Complete
        || state.semantic_step != prepared.plan.steps.len()
        || state.predictions.len() != prepared.plan.steps.len()
    {
        return Err(
            "resume scope completed without all fixed semantic steps and query audit".into(),
        );
    }
    let final_result = state
        .inner
        .progress
        .last_completed_result
        .clone()
        .ok_or("resume scope lacks a final native result")?;
    if final_result.status != ygo_engine_adapter::DuelStatus::EngineVerified {
        return Err(format!(
            "resume scope final result is not terminal: {:?}",
            final_result.status
        ));
    }
    let snapshot = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&snapshot)?;
    if snapshot.stats.consumed > JOURNAL_LIMIT {
        return Err("resume scope exceeded its fixed charged-call limit".into());
    }
    let projection = ScopeProjection {
        scope: manifest.resume_scope.clone(),
        context: manifest.resume_context.clone(),
        input_identity: manifest.input_identity.clone(),
        plan: prepared.plan.clone(),
        state: serde_json::to_value(&state).map_err(|error| error.to_string())?,
        result: final_result,
        journal: snapshot.clone(),
    };
    let projection_path = manifest.run_dir.join("resume/recovery-report.json");
    let projection_bytes = write_new_json(&projection_path, &projection)?;
    drop(journal);

    let stable_before = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    let reopened = CallJournal::open_existing_strict(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?
    .ok_or("resume scope missing on final stability reopen")?;
    reopened.verify().map_err(|error| error.message)?;
    let reopened_state =
        checkpoint_state_from_value(checkpoint_value(&reopened, &state.execution_id)?)?;
    if serde_json::to_value(&reopened_state).map_err(|error| error.to_string())?
        != serde_json::to_value(&state).map_err(|error| error.to_string())?
    {
        return Err("final resume checkpoint differs after a fresh strict reopen".into());
    }
    let reopened_projection = ScopeProjection {
        scope: manifest.resume_scope.clone(),
        context: manifest.resume_context.clone(),
        input_identity: manifest.input_identity.clone(),
        plan: prepared.plan.clone(),
        state: serde_json::to_value(&reopened_state).map_err(|error| error.to_string())?,
        result: reopened_state
            .inner
            .progress
            .last_completed_result
            .clone()
            .ok_or("final reopen lost the final result")?,
        journal: stable_before.clone(),
    };
    let reopened_projection_bytes =
        serde_json::to_vec_pretty(&reopened_projection).map_err(|error| error.to_string())?;
    let stored_projection = fs::read(&projection_path).map_err(|error| error.to_string())?;
    let stable_after = journal_snapshot(
        &prepared.resume_journal_path,
        &manifest.resume_scope,
        &manifest.resume_context,
        JOURNAL_LIMIT,
    )?;
    if stable_before != snapshot
        || stable_after != stable_before
        || stored_projection != projection_bytes
        || reopened_projection_bytes != projection_bytes
    {
        return Err("resume ledger or report projection changed across final reopen".into());
    }
    drop(reopened);
    Ok((state, snapshot))
}

fn run_initial_only(
    prepared: &harness::Prepared,
    journal: Arc<CallJournal>,
    evidence_dir: &Path,
) -> Result<DuelResult, String> {
    if journal.stats().map_err(|error| error.message)?.consumed != 0 {
        return Err("replay scope was not empty before its initial call".into());
    }
    let initial = JournaledAdapter::new(
        ProcessEngineAdapter::new(prepared.request.engine.clone()),
        journal.clone(),
        CallPurpose::Execution,
    )
    .run(&prepared.request)
    .map_err(|error| {
        format!(
            "replay initial native call failed: {}: {}",
            error.code, error.message
        )
    })?;
    write_new_json(&evidence_dir.join("initial-result.json"), &initial)?;
    harness::validate_initial_result(prepared, &initial)?;
    Ok(initial)
}

fn continue_replay_scope(
    manifest: &RunManifest,
    prepared: &harness::Prepared,
) -> Result<(PartialExecution, Vec<u64>, JournalSnapshot), String> {
    check_window(&manifest.run_dir)?;
    let checked = verify_manifest_runtime(&prepared.root, manifest)?;
    check_window(&manifest.run_dir)?;
    if checked.identity != prepared.identity {
        return Err("pre-replay input, plan, or frozen asset identity changed".into());
    }
    let prepared = &checked;
    require_source_identity(&prepared.root, &manifest.source_identity)?;
    if harness::sha256_file(&prepared.root, &prepared.worker_path)? != manifest.worker_sha256 {
        return Err("worker binary changed before replay scope".into());
    }
    let replay_dir = manifest.run_dir.join("replay");
    let journal = CallJournal::open(
        &prepared.replay_journal_path,
        &manifest.replay_scope,
        &manifest.replay_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?;
    let initial = run_initial_only(prepared, journal.clone(), &replay_dir)?;
    check_window(&manifest.run_dir)?;
    let report = execute_partial(
        &prepared.request,
        &initial,
        &prepared.queries,
        &prepared.plan,
        &prepared.catalog,
        &prepared.pack,
        &prepared.goal,
        journal.clone(),
    )?;
    check_window(&manifest.run_dir)?;
    write_new_json(&replay_dir.join("continuous-report.json"), &report)?;
    if report.failure.is_some()
        || report.plan_id != prepared.plan.id
        || report.predictions.len() != prepared.plan.steps.len()
        || report.choices.len() != prepared.plan.steps.len()
        || !report.terminal
        || report.result.status != ygo_engine_adapter::DuelStatus::EngineVerified
    {
        return Err(format!(
            "continuous replay did not complete the fixed route: {report:?}"
        ));
    }
    for (index, prediction) in report.predictions.iter().enumerate() {
        if prediction.selected.rule_id != prepared.expected_route[index] {
            return Err(format!(
                "continuous replay selected an unexpected rule at step {index}: {}",
                prediction.selected.rule_id
            ));
        }
    }
    let receipt = replay_partial_execution(
        &report,
        &prepared.plan,
        &prepared.catalog,
        &prepared.pack,
        &prepared.goal,
        &journal,
        journal.clone(),
    )?;
    check_window(&manifest.run_dir)?;
    if !receipt.matches(&report.request, &report.result, &report.queries) {
        return Err("independent replay receipt does not bind the continuous report".into());
    }
    write_new_json(
        &replay_dir.join("independent-replay.json"),
        &json!({"call_ids": receipt.call_ids, "queries": report.queries.len(), "root": true}),
    )?;
    let snapshot = journal_snapshot(
        &prepared.replay_journal_path,
        &manifest.replay_scope,
        &manifest.replay_context,
        JOURNAL_LIMIT,
    )?;
    assert_accounting(&snapshot)?;
    if snapshot.stats.consumed > JOURNAL_LIMIT {
        return Err("replay scope exceeded its fixed charged-call limit".into());
    }
    let projection = ReplayProjection {
        scope: manifest.replay_scope.clone(),
        context: manifest.replay_context.clone(),
        input_identity: manifest.input_identity.clone(),
        plan: prepared.plan.clone(),
        report: report.clone(),
        audited_query_call_ids: receipt.call_ids.clone(),
        journal: snapshot.clone(),
    };
    let projection_path = replay_dir.join("replay-report.json");
    let projection_bytes = write_new_json(&projection_path, &projection)?;
    drop(journal);

    let stable_before = journal_snapshot(
        &prepared.replay_journal_path,
        &manifest.replay_scope,
        &manifest.replay_context,
        JOURNAL_LIMIT,
    )?;
    let reopened = CallJournal::open_existing_strict(
        &prepared.replay_journal_path,
        &manifest.replay_scope,
        &manifest.replay_context,
        JOURNAL_LIMIT,
    )
    .map_err(|error| error.message)?
    .ok_or("replay scope missing on final stability reopen")?;
    reopened.verify().map_err(|error| error.message)?;
    let reopened_projection = ReplayProjection {
        scope: manifest.replay_scope.clone(),
        context: manifest.replay_context.clone(),
        input_identity: manifest.input_identity.clone(),
        plan: prepared.plan.clone(),
        report: report.clone(),
        audited_query_call_ids: receipt.call_ids.clone(),
        journal: stable_before.clone(),
    };
    let reopened_projection_bytes =
        serde_json::to_vec_pretty(&reopened_projection).map_err(|error| error.to_string())?;
    let stored_projection = fs::read(&projection_path).map_err(|error| error.to_string())?;
    let stable_after = journal_snapshot(
        &prepared.replay_journal_path,
        &manifest.replay_scope,
        &manifest.replay_context,
        JOURNAL_LIMIT,
    )?;
    if stable_before != snapshot
        || stable_after != stable_before
        || stored_projection != projection_bytes
        || reopened_projection_bytes != projection_bytes
    {
        return Err("replay ledger or report projection changed across final reopen".into());
    }
    drop(reopened);
    Ok((report, receipt.call_ids, snapshot))
}

fn compare_runs(
    manifest: &RunManifest,
    prepared: &harness::Prepared,
    recovery: &ResumablePartialExecutionV1,
    recovery_ledger: JournalSnapshot,
    replay: &PartialExecution,
    replay_calls: Vec<u64>,
    replay_ledger: JournalSnapshot,
) -> Result<Comparison, String> {
    let recovery_result = recovery
        .inner
        .progress
        .last_completed_result
        .as_ref()
        .ok_or("recovery result missing during comparison")?;
    let plan_equal = recovery.inner.plan_id == prepared.plan.id
        && replay.plan_id == prepared.plan.id
        && serde_json::to_value(&prepared.plan).map_err(|error| error.to_string())?
            == serde_json::to_value(&manifest.plan).map_err(|error| error.to_string())?;
    let semantic_steps_equal = recovery.semantic_step == prepared.plan.steps.len()
        && recovery.predictions.len() == prepared.plan.steps.len()
        && replay.predictions.len() == prepared.plan.steps.len()
        && recovery
            .predictions
            .iter()
            .map(|prediction| prediction.selected.rule_id.as_str())
            .eq(replay
                .predictions
                .iter()
                .map(|prediction| prediction.selected.rule_id.as_str()));
    let choices_and_mapping_history_equal = serde_json::to_value(&recovery.choices)
        .map_err(|error| error.to_string())?
        == serde_json::to_value(&replay.choices).map_err(|error| error.to_string())?;
    let predictions_equal = serde_json::to_value(&recovery.predictions)
        .map_err(|error| error.to_string())?
        == serde_json::to_value(&replay.predictions).map_err(|error| error.to_string())?;
    let query_witnesses_equal = serde_json::to_value(&recovery.inner.progress.queries)
        .map_err(|error| error.to_string())?
        == serde_json::to_value(&replay.queries).map_err(|error| error.to_string())?;
    let final_result_same_native = same_native(recovery_result, &replay.result);
    let comparison = Comparison {
        schema_version: 1,
        run_id: manifest.run_id.clone(),
        plan_equal,
        semantic_steps_equal,
        choices_and_mapping_history_equal,
        predictions_equal,
        query_witnesses_equal,
        final_result_same_native,
        recovery_ledger,
        replay_ledger,
        qualification: if plan_equal
            && semantic_steps_equal
            && choices_and_mapping_history_equal
            && predictions_equal
            && query_witnesses_equal
            && final_result_same_native
            && !replay_calls.is_empty()
        {
            "one_fixed_scenario_passed".into()
        } else {
            "comparison_failed; evidence_preserved".into()
        },
    };
    write_new_json(&manifest.run_dir.join("comparison.json"), &comparison)?;
    if comparison.qualification != "one_fixed_scenario_passed" {
        return Err(format!(
            "independent semantic comparison failed: {comparison:?}"
        ));
    }
    Ok(comparison)
}

fn run_native(root: &Path, output_root: &Path) -> Result<PathBuf, String> {
    let prepared = harness::prepare(root, output_root)?;
    if !prepared.worker_path.is_file() {
        return Err(format!(
            "isolated worker is missing: {}",
            prepared.worker_path.display()
        ));
    }
    let (manifest, diff) = expected_manifest(root, &prepared)?;
    create_run_dir(&manifest.run_dir)?;
    write_new(&manifest.run_dir.join("tracked-source-diff.bin"), &diff)?;
    write_new_json(&manifest_path(&manifest.run_dir), &manifest)?;
    write_new_json(
        &manifest.run_dir.join("fixed-request.json"),
        &manifest.request,
    )?;
    write_new_json(&manifest.run_dir.join("forecast-plan.json"), &manifest.plan)?;
    write_new_json(
        &manifest.run_dir.join("query-witnesses.json"),
        &manifest.queries,
    )?;
    write_new_json(
        &manifest.run_dir.join("asset-identities.json"),
        &json!({
            "assets": prepared.asset_identities,
            "trace_fixture_sha256": prepared.trace_sha256,
            "frozen_core_sha256": prepared.core_sha256,
        }),
    )?;
    let start_epoch = now_epoch_seconds()?;
    write_new_json(
        &manifest.run_dir.join("window-start.json"),
        &json!({"epoch_seconds": start_epoch, "window_seconds": harness::MAX_WINDOW_SECONDS}),
    )?;
    // The final full fixture/asset scan occurs after the one-time clock anchor,
    // immediately before the child can create its first charged call.
    let final_prepared = verify_manifest_runtime(root, &manifest)?;
    if final_prepared.identity != prepared.identity {
        return Err(
            "final pre-call asset or fixture scan differs from the prepared identity".into(),
        );
    }
    check_window(&manifest.run_dir)?;
    if let Err(error) = launch_and_kill_at_pause(&manifest, &final_prepared) {
        write_failure(&manifest.run_dir, "resume", "coordinator", &error);
        return Err(format!(
            "resume scope stopped at pause boundary: {error}; evidence: {}",
            manifest.run_dir.display()
        ));
    }
    let (recovery, recovery_ledger) = match continue_recovery_scope(&manifest, &final_prepared) {
        Ok(value) => value,
        Err(error) => {
            write_failure(&manifest.run_dir, "resume", "recovery", &error);
            return Err(format!(
                "resume scope failed after authenticated pause: {error}; evidence: {}",
                manifest.run_dir.display()
            ));
        }
    };
    if recovery_ledger.stats.unknown != 0 || recovery_ledger.stats.reserved != 0 {
        let error = format!(
            "resume scope has uncertain consumption: {:?}",
            recovery_ledger.stats
        );
        write_failure(&manifest.run_dir, "resume", "recovery-accounting", &error);
        return Err(error);
    }
    // The replay scope is deliberately gated on the completed, stable recovery.
    require_source_identity(root, &manifest.source_identity)?;
    let (replay, replay_calls, replay_ledger) =
        match continue_replay_scope(&manifest, &final_prepared) {
            Ok(value) => value,
            Err(error) => {
                write_failure(&manifest.run_dir, "replay", "independent-run", &error);
                return Err(format!(
                    "independent replay scope stopped: {error}; evidence: {}",
                    manifest.run_dir.display()
                ));
            }
        };
    let comparison = compare_runs(
        &manifest,
        &final_prepared,
        &recovery,
        recovery_ledger,
        &replay,
        replay_calls,
        replay_ledger,
    )?;
    println!(
        "{}",
        serde_json::to_string_pretty(&comparison).map_err(|error| error.to_string())?
    );
    Ok(manifest.run_dir)
}

fn parse_cli(args: &[String]) -> Result<(String, Option<PathBuf>), String> {
    match args {
        [] => Ok(("--prepare-only".into(), None)),
        [mode] if mode == "--prepare-only" || mode == "--run-native" => Ok((mode.clone(), None)),
        [mode, flag, path]
            if (mode == "--prepare-only" || mode == "--run-native") && flag == "--output-root" =>
        {
            Ok((mode.clone(), Some(PathBuf::from(path))))
        }
        _ => Err(
            "usage: p4-r1b3-native-resume [--prepare-only|--run-native] [--output-root PATH]"
                .into(),
        ),
    }
}

fn dispatch() -> Result<(), String> {
    let args = env::args().skip(1).collect::<Vec<_>>();
    if args.first().is_some_and(|arg| arg == "--resume-child") {
        if args.len() != 2 {
            return Err("internal resume child requires one manifest path".into());
        }
        return run_resume_child(Path::new(&args[1]));
    }
    if args
        .first()
        .is_some_and(|arg| arg == "--inspect-initial-run")
    {
        if args.len() != 2 {
            return Err("read-only inspector requires one run directory".into());
        }
        let root = repo_root()?;
        let result = inspect_initial_run(&root, Path::new(&args[1]))?;
        println!(
            "{}",
            serde_json::to_string_pretty(&result).map_err(|error| error.to_string())?
        );
        return Ok(());
    }
    let (mode, output_arg) = parse_cli(&args)?;
    let root = repo_root()?;
    let output_root = output_arg.unwrap_or_else(|| harness::default_output_root(&root));
    match mode.as_str() {
        "--prepare-only" => {
            let result = prepare_only(&root, &output_root)?;
            if result["scope_created"] != false
                || result["worker_processes_started"] != 0
                || result["native_calls"] != 0
            {
                return Err("prepare-only unexpectedly created or charged a native scope".into());
            }
            Ok(())
        }
        "--run-native" => run_native(&root, &output_root).map(|_| ()),
        _ => Err("unknown execution mode".into()),
    }
}

fn main() {
    if let Err(error) = dispatch() {
        eprintln!("P4-R1b-3 stopped: {error}");
        std::process::exit(1);
    }
}
