use std::process::Command;
#[test]
fn v2_plan_validates_explicit_scoring_before_engine_setup() {
    let output = Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
        .current_dir(std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
        .args([
            "combo",
            "plan",
            "--input",
            "tests/fixtures/break-sword.request.json",
            "--scoring",
            "missing-goal-scoring.toml",
        ])
        .output()
        .unwrap();
    assert!(!output.status.success());
    assert!(
        String::from_utf8_lossy(&output.stderr).contains("missing-goal-scoring.toml"),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
