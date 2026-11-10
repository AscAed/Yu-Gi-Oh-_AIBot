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
    r.engine.timeout_ms = if mode == "hang" { 200 } else { 10_000 };
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
    let (r, observed, path, directory) = observed_fixture("valid", 10_000);

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
        let timeout_ms = if mode == "hang" { 200 } else { 10_000 };
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

fn stream_fixture(name: &str) -> (RunDuelRequest, ProcessEngineAdapter, PathBuf, PathBuf) {
    use std::sync::atomic::{AtomicU64, Ordering};
    static NEXT: AtomicU64 = AtomicU64::new(0);
    let directory = std::env::temp_dir().join(format!(
        "ygo-stream-observation-{}-{}-{name}",
        std::process::id(),
        NEXT.fetch_add(1, Ordering::Relaxed)
    ));
    std::fs::create_dir_all(&directory).unwrap();
    let path = directory.join(format!("fixture-{name}{}", std::env::consts::EXE_SUFFIX));
    std::fs::copy(env!("CARGO_BIN_EXE_ygo-worker-fixture"), &path).unwrap();
    let mut request = request();
    request.engine.worker_path = path.clone();
    request.engine.timeout_ms = 10_000;
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    (request, adapter, path, directory)
}

#[test]
fn stream_supervisor_persists_nested_events_before_acknowledging() {
    let (request, adapter, path, directory) = stream_fixture("stream-valid");
    let mut events = Vec::new();
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "a".repeat(32).as_str(), &mut |event| {
            events.push(event);
            Ok(())
        });

    assert!(outcome.result.is_ok());
    assert_eq!(events.len(), 4);
    assert!(matches!(
        &events[0],
        FfiReceiptEvent::Entered { sequence: 1, .. }
    ));
    assert!(matches!(
        &events[1],
        FfiReceiptEvent::Entered { sequence: 2, .. }
    ));
    assert!(matches!(
        &events[2],
        FfiReceiptEvent::Returned { sequence: 2, .. }
    ));
    assert!(matches!(
        &events[3],
        FfiReceiptEvent::Returned { sequence: 1, .. }
    ));
    assert_eq!(outcome.observation.termination, ProcessTermination::Exited);

    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_kills_worker_when_receipt_persistence_fails() {
    let (request, adapter, path, directory) = stream_fixture("stream-valid");
    let mut events = 0;
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "b".repeat(32).as_str(), &mut |_| {
            events += 1;
            Err("simulated durable append failure".into())
        });

    assert_eq!(
        outcome.result.unwrap_err().code,
        "host_receipt_callback_failed"
    );
    assert_eq!(events, 1);
    assert_eq!(outcome.observation.termination, ProcessTermination::Exited);

    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_rejects_out_of_order_frames() {
    let (request, adapter, path, directory) = stream_fixture("stream-invalid");
    let mut events = 0;
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "c".repeat(32).as_str(), &mut |_| {
            events += 1;
            Ok(())
        });

    assert_eq!(outcome.result.unwrap_err().code, "event_order");
    assert_eq!(events, 0);

    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_reports_oversized_event_frames_separately() {
    let (request, adapter, path, directory) = stream_fixture("stream-oversized-event");
    let mut events = 0;
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "c".repeat(32).as_str(), &mut |_| {
            events += 1;
            Ok(())
        });

    assert_eq!(outcome.result.unwrap_err().code, "event_frame_size");
    assert_eq!(events, 0);
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_times_out_when_receipt_persistence_exceeds_deadline() {
    let (mut request, _, path, directory) = stream_fixture("stream-valid");
    request.engine.timeout_ms = 5000;
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    let mut events = 0;
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "d".repeat(32).as_str(), &mut |_| {
            events += 1;
            std::thread::sleep(std::time::Duration::from_millis(5100));
            Ok(())
        });

    assert_eq!(outcome.result.unwrap_err().code, "timeout");
    assert_eq!(events, 1);
    assert_eq!(
        outcome.observation.termination,
        ProcessTermination::TimedOut
    );
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_deadline_covers_a_blocked_request_pipe_write() {
    let (mut request, _, path, directory) = stream_fixture("stream-no-read");
    request.engine.timeout_ms = 200;
    request.engine.ocgcore_path = PathBuf::from(format!("{}.dll", "x".repeat(8 * 1024 * 1024)));
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    let start = std::time::Instant::now();
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "9".repeat(32).as_str(), &mut |_| Ok(()));

    assert_eq!(outcome.result.unwrap_err().code, "timeout");
    assert!(start.elapsed().as_secs() < 3);
    assert_eq!(outcome.observation.request_status, ProcessIoStatus::Unknown);
    assert_eq!(
        outcome.observation.termination,
        ProcessTermination::TimedOut
    );
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_classifies_exit_after_entered_as_unresolved() {
    let (request, adapter, path, directory) = stream_fixture("stream-exit-after-entry");
    let mut events = Vec::new();
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "e".repeat(32).as_str(), &mut |event| {
            events.push(event);
            Ok(())
        });

    let error = outcome.result.unwrap_err();
    assert!(
        matches!(error.code.as_str(), "worker_eof" | "ack_write_failed"),
        "unexpected unresolved worker exit error: {}",
        error.code
    );
    assert_eq!(events.len(), 1);
    assert!(matches!(
        events.first(),
        Some(FfiReceiptEvent::Entered { sequence: 1, .. })
    ));
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_rejects_data_after_result() {
    let (request, adapter, path, directory) = stream_fixture("stream-after-result");
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "f".repeat(32).as_str(), &mut |_| Ok(()));

    assert_eq!(outcome.result.unwrap_err().code, "frame_after_result");
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_accepts_result_without_ffi_events() {
    let (request, adapter, path, directory) = stream_fixture("stream-no-events");
    let mut events = 0;
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "0".repeat(32).as_str(), &mut |_| {
            events += 1;
            Ok(())
        });

    assert!(outcome.result.is_ok());
    assert_eq!(events, 0);
    assert_eq!(
        outcome.observation.response_validation,
        ProcessResponseValidation::Parsed
    );
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_rejects_result_with_mismatched_protocol_version() {
    let (mut request, _, path, directory) = stream_fixture("stream-protocol-mismatch");
    request.protocol_version = 4;
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "1".repeat(32).as_str(), &mut |_| Ok(()));

    assert_eq!(outcome.result.unwrap_err().code, "protocol_version");
    assert_eq!(
        outcome.observation.response_validation,
        ProcessResponseValidation::ProtocolVersionMismatch
    );
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}

#[test]
fn stream_supervisor_rejects_nonfailure_result_with_mismatched_runtime_versions() {
    let (mut request, _, path, directory) = stream_fixture("stream-runtime-mismatch");
    request.protocol_version = 4;
    request.versions.rules = "rules-v1".into();
    let adapter = ProcessEngineAdapter::new(request.engine.clone());
    let outcome =
        adapter.run_process_observed_with_ffi(&request, "2".repeat(32).as_str(), &mut |_| Ok(()));

    assert_eq!(outcome.result.unwrap_err().code, "version_mismatch");
    assert_eq!(
        outcome.observation.response_validation,
        ProcessResponseValidation::RuntimeVersionMismatch
    );
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(directory).unwrap();
}
