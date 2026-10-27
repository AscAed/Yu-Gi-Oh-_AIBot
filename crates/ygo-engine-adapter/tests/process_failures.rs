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
