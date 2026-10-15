use std::process::Command;
use std::sync::atomic::{AtomicU64, Ordering};
static NEXT_FILE: AtomicU64 = AtomicU64::new(0);
fn invoke(action: &str, value: serde_json::Value) -> String {
    let path = std::env::temp_dir().join(format!(
        "ygo-goal-version-{}-{}-{}.json",
        std::process::id(),
        NEXT_FILE.fetch_add(1, Ordering::Relaxed),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    std::fs::write(&path, serde_json::to_vec(&value).unwrap()).unwrap();
    let result = Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
        .env_remove("YGO_SCORING_CONFIG")
        .args(["combo", action, "--input", path.to_str().unwrap()])
        .output()
        .unwrap();
    std::fs::remove_file(path).unwrap();
    assert!(!result.status.success());
    String::from_utf8_lossy(&result.stderr).into_owned()
}
#[test]
fn replay_routes_v3_envelopes_to_the_goal_contract() {
    let error = invoke("plan-replay", serde_json::json!({"schema_version":3}));
    assert!(error.contains("planner_profile"), "{error}");
}
#[test]
fn unknown_versions_are_rejected_before_legacy_parsing() {
    for action in ["plan", "plan-replay"] {
        let error = invoke(action, serde_json::json!({"schema_version":99}));
        assert!(
            error.contains("unsupported planning schema_version"),
            "{error}"
        );
    }
}

#[test]
fn replay_routes_v4_envelopes_to_the_recovery_contract() {
    let error = invoke("plan-replay", serde_json::json!({"schema_version":4}));
    assert!(error.contains("planner_profile"), "{error}");
}
