use std::path::PathBuf;
use ygo_engine_adapter::*;
fn request() -> RunDuelRequest {
    RunDuelRequest {
        protocol_version: 2,
        engine: ProcessEngineConfig::default(),
        deck: Default::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions: Default::default(),
        probe_only: true,
        scenario: None,
        interruption: None,
        first_turn: None,
        research_capture: None,
    }
}

fn observed_fixture(
    mode: &str,
    timeout_ms: u64,
) -> (RunDuelRequest, ProcessObservedOutcome, PathBuf, PathBuf) {
    let directory = std::env::temp_dir().join(format!(
        "ygo-process-observation-{}-{mode}",
        std::process::id()
    ));
    std::fs::create_dir_all(&directory).unwrap();
    let path = directory.join(format!("fixture-{mode}{}", std::env::consts::EXE_SUFFIX));
    std::fs::copy(env!("CARGO_BIN_EXE_ygo-worker-fixture"), &path).unwrap();
    let mut request = request();
    request.engine.worker_path = path.clone();
    request.engine.timeout_ms = timeout_ms;
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    let outcome = adapter.run_process_observed(&request);
    (request, outcome, path, directory)
}

fn check(mode: &str, code: &str) {
    let directory = std::env::temp_dir().join(format!("ygo-process-{}-{mode}", std::process::id()));
    std::fs::create_dir_all(&directory).unwrap();
    let path = directory.join(format!("fixture-{mode}{}", std::env::consts::EXE_SUFFIX));
    std::fs::copy(env!("CARGO_BIN_EXE_ygo-worker-fixture"), &path).unwrap();
    let mut r = request();
    r.engine.worker_path = path.clone();
    r.engine.timeout_ms = if mode == "hang" { 200 } else { 2000 };
    let adapter = ProcessEngineAdapter::new(r.engine.clone());
    let start = std::time::Instant::now();
    let error = adapter.run(&r).unwrap_err();
    assert_eq!(error.code, code);
    assert!(start.elapsed().as_secs() < 3);
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}
#[test]
fn hanging_child_is_killed_and_reaped() {
    check("hang", "timeout");
}
#[test]
fn nonzero_exit_is_reported() {
    check("crash", "process_failed");
}
#[test]
fn malformed_output_is_rejected() {
    check("invalid", "invalid_response");
}
#[test]
fn large_stderr_cannot_deadlock_parent() {
    check("noise", "invalid_response");
}
#[test]
fn incompatible_worker_protocol_is_rejected() {
    check("protocol", "protocol_version");
}

#[test]
fn observed_run_captures_worker_request_response_and_exit() {
    let (r, observed, path, directory) = observed_fixture("valid", 2000);

    assert!(observed.result.is_ok());
    let observation = observed.observation;
    assert_eq!(observation.spawn_status, ProcessSpawnStatus::Spawned);
    assert!(observation.worker_pid.unwrap() > 0);
    assert_eq!(
        observation.worker_executable_sha256.as_deref(),
        Some(hash_file(&path).unwrap().as_str())
    );
    assert_eq!(observation.request_status, ProcessIoStatus::Complete);
    let mut request_bytes = serde_json::to_vec(&r).unwrap();
    request_bytes.push(b'\n');
    assert_eq!(
        observation.request_sha256.as_deref(),
        Some(digest(&request_bytes).as_str())
    );
    assert_eq!(observation.request_bytes, Some(request_bytes.len() as u64));
    assert_eq!(observation.response_status, ProcessIoStatus::Complete);
    let mut expected_result = DuelResult::failure(WorkerError::new("fixture", "test", ""));
    expected_result.protocol_version = 2;
    let mut response_bytes = serde_json::to_vec(&expected_result).unwrap();
    response_bytes.push(b'\n');
    assert_eq!(
        observation.response_sha256.as_deref(),
        Some(digest(&response_bytes).as_str())
    );
    assert_eq!(
        observation.response_bytes,
        Some(response_bytes.len() as u64)
    );
    assert_eq!(
        observation.response_validation,
        ProcessResponseValidation::Parsed
    );
    assert_eq!(observation.termination, ProcessTermination::Exited);
    assert_eq!(observation.exit_code, Some(0));

    let normal_adapter = ProcessEngineAdapter::new(r.engine.clone());
    assert_eq!(normal_adapter.run(&r).unwrap().status, DuelStatus::Failed);

    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn observed_run_preserves_distinct_exit_and_response_failures() {
    for (mode, error_code, termination, validation, exit_code) in [
        (
            "crash",
            "process_failed",
            ProcessTermination::Exited,
            ProcessResponseValidation::NotAttempted,
            Some(7),
        ),
        (
            "invalid",
            "invalid_response",
            ProcessTermination::Exited,
            ProcessResponseValidation::InvalidJson,
            Some(0),
        ),
        (
            "protocol",
            "protocol_version",
            ProcessTermination::Exited,
            ProcessResponseValidation::ProtocolVersionMismatch,
            Some(0),
        ),
        (
            "hang",
            "timeout",
            ProcessTermination::TimedOut,
            ProcessResponseValidation::NotAttempted,
            None,
        ),
    ] {
        let timeout_ms = if mode == "hang" { 200 } else { 2000 };
        let (_, outcome, path, directory) = observed_fixture(mode, timeout_ms);
        assert_eq!(outcome.result.unwrap_err().code, error_code, "{mode}");
        let observation = outcome.observation;
        assert_eq!(
            observation.spawn_status,
            ProcessSpawnStatus::Spawned,
            "{mode}"
        );
        assert!(observation.worker_pid.is_some(), "{mode}");
        assert!(observation.worker_executable_sha256.is_some(), "{mode}");
        assert_eq!(
            observation.response_status,
            ProcessIoStatus::Complete,
            "{mode}"
        );
        assert!(observation.response_sha256.is_some(), "{mode}");
        assert!(observation.response_bytes.is_some(), "{mode}");
        assert_eq!(observation.response_validation, validation, "{mode}");
        assert_eq!(observation.termination, termination, "{mode}");
        if mode != "hang" {
            assert_eq!(observation.exit_code, exit_code, "{mode}");
        }
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(directory).unwrap();
    }
}

#[test]
fn observed_spawn_failure_does_not_claim_pipe_or_response_io() {
    let directory = std::env::temp_dir().join(format!(
        "ygo-process-observation-spawn-failure-{}",
        std::process::id()
    ));
    std::fs::create_dir_all(&directory).unwrap();
    let mut request = request();
    request.engine.worker_path = directory.join(format!("missing{}", std::env::consts::EXE_SUFFIX));
    let adapter = ProcessEngineAdapter::new(request.engine.clone());

    let outcome = adapter.run_observed(&request);

    assert_eq!(outcome.result.unwrap_err().code, "spawn_failed");
    assert_eq!(outcome.observation.spawn_status, ProcessSpawnStatus::Failed);
    assert_eq!(outcome.observation.worker_pid, None);
    assert_eq!(outcome.observation.worker_executable_sha256, None);
    assert_eq!(
        outcome.observation.request_status,
        ProcessIoStatus::NotAttempted
    );
    assert_eq!(outcome.observation.request_sha256, None);
    assert_eq!(outcome.observation.request_bytes, None);
    assert_eq!(
        outcome.observation.response_status,
        ProcessIoStatus::NotAttempted
    );
    assert_eq!(outcome.observation.response_sha256, None);
    assert_eq!(outcome.observation.response_bytes, None);
    assert_eq!(
        outcome.observation.termination,
        ProcessTermination::NotStarted
    );

    std::fs::remove_dir(directory).unwrap();
}
