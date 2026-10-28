use serde_json::Value;
use std::{
    fs,
    ops::Deref,
    path::{Path, PathBuf},
    process::Command,
};
use ygo_domain::DeckDocumentV1;

struct TempDir(PathBuf);

impl Deref for TempDir {
    type Target = Path;

    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn temp_dir() -> TempDir {
    let path = std::env::temp_dir().join(format!(
        "ygo-deck-draft-test-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    TempDir(path)
}

fn cli(args: &[&str]) -> std::process::Output {
    Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
        .args(["deck", "draft"])
        .args(args)
        .output()
        .unwrap()
}

#[test]
fn creates_edits_shows_and_exports_an_incomplete_draft() {
    let dir = temp_dir();
    let draft = dir.join("draft.json");
    let created = cli(&[
        "create",
        "--output",
        draft.to_str().unwrap(),
        "--title",
        "Test",
    ]);
    assert!(
        created.status.success(),
        "{}",
        String::from_utf8_lossy(&created.stderr)
    );
    let value: Value = serde_json::from_slice(&fs::read(&draft).unwrap()).unwrap();
    assert_eq!(value["kind"], "deck_draft");
    assert_eq!(value["main"], serde_json::json!([]));
    let edited = cli(&[
        "edit",
        "--input",
        draft.to_str().unwrap(),
        "--output",
        draft.to_str().unwrap(),
        "--zone",
        "main",
        "--operation",
        "add",
        "--card",
        "777",
        "--count",
        "2",
        "--replace",
    ]);
    assert!(
        edited.status.success(),
        "{}",
        String::from_utf8_lossy(&edited.stderr)
    );
    let shown = cli(&["show", "--input", draft.to_str().unwrap()]);
    assert!(shown.status.success());
    let shown: Value = serde_json::from_slice(&shown.stdout).unwrap();
    assert_eq!(shown["draft"]["main"], serde_json::json!([777, 777]));
    assert_eq!(shown["card_check"]["status"], "unverified");
    let ydk = dir.join("draft.ydk");
    let exported = cli(&[
        "export",
        "--input",
        draft.to_str().unwrap(),
        "--output",
        ydk.to_str().unwrap(),
        "--format",
        "ydk",
    ]);
    assert!(
        exported.status.success(),
        "{}",
        String::from_utf8_lossy(&exported.stderr)
    );
    assert!(fs::read_to_string(ydk).unwrap().contains("777\n777\n"));
}

#[test]
fn import_and_export_round_trip_ydk_and_refuse_implicit_overwrite() {
    let dir = temp_dir();
    let ydk = dir.join("input.ydk");
    fs::write(&ydk, "#main\n1\n1\n#extra\n2\n!side\n3\n").unwrap();
    let json = dir.join("draft.json");
    let imported = cli(&[
        "import",
        "--input",
        ydk.to_str().unwrap(),
        "--output",
        json.to_str().unwrap(),
        "--format",
        "ydk",
    ]);
    assert!(imported.status.success());
    let before = fs::read(&json).unwrap();
    let refused = cli(&[
        "create",
        "--output",
        json.to_str().unwrap(),
        "--title",
        "overwrite",
    ]);
    assert!(!refused.status.success());
    assert_eq!(fs::read(&json).unwrap(), before);
    let output = dir.join("roundtrip.ydk");
    let exported = cli(&[
        "export",
        "--input",
        json.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
        "--format",
        "ydk",
    ]);
    assert!(exported.status.success());
    let round_trip = DeckDocumentV1::from_ydk(&fs::read_to_string(output).unwrap()).unwrap();
    let original = DeckDocumentV1::from_ydk(&fs::read_to_string(ydk).unwrap()).unwrap();
    assert_eq!(round_trip.main, original.main);
    assert_eq!(round_trip.extra, original.extra);
    assert_eq!(round_trip.side, original.side);
}

#[test]
fn failed_removal_does_not_replace_the_input_or_output() {
    let dir = temp_dir();
    let input = dir.join("input.json");
    fs::write(&input, r#"{"schema_version":1,"kind":"deck_draft","title":"keep","main":[8],"extra":[],"side":[]}"#).unwrap();
    let output = dir.join("output.json");
    fs::write(&output, "old output").unwrap();
    let result = cli(&[
        "edit",
        "--input",
        input.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
        "--zone",
        "main",
        "--operation",
        "remove",
        "--card",
        "8",
        "--count",
        "2",
        "--replace",
    ]);
    assert!(!result.status.success());
    assert!(String::from_utf8_lossy(&result.stderr).contains("fewer than 2 copies"));
    assert_eq!(
        fs::read_to_string(&input).unwrap(),
        r#"{"schema_version":1,"kind":"deck_draft","title":"keep","main":[8],"extra":[],"side":[]}"#
    );
    assert_eq!(fs::read_to_string(output).unwrap(), "old output");
}
