use serde_json::Value;
use std::{
    fs,
    ops::Deref,
    path::{Path, PathBuf},
    process::Command,
    sync::atomic::{AtomicU64, Ordering},
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
    static NEXT_TEMP_DIR_ID: AtomicU64 = AtomicU64::new(0);
    loop {
        let id = NEXT_TEMP_DIR_ID.fetch_add(1, Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("ygo-deck-draft-test-{}-{id}", std::process::id()));
        match fs::create_dir(&path) {
            Ok(()) => return TempDir(path),
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(error) => panic!("create test temp directory failed: {error}"),
        }
    }
}

#[test]
fn temp_dirs_are_unique_when_allocated_concurrently() {
    const THREADS: usize = 32;
    const ROUNDS: usize = 16;
    let barrier = std::sync::Arc::new(std::sync::Barrier::new(THREADS));
    let directories = std::thread::scope(|scope| {
        let handles = (0..THREADS)
            .map(|_| {
                let barrier = std::sync::Arc::clone(&barrier);
                scope.spawn(move || {
                    let mut directories = Vec::with_capacity(ROUNDS);
                    for _ in 0..ROUNDS {
                        barrier.wait();
                        directories.push(temp_dir());
                    }
                    directories
                })
            })
            .collect::<Vec<_>>();

        handles
            .into_iter()
            .flat_map(|handle| handle.join().unwrap())
            .collect::<Vec<_>>()
    });
    let unique_paths = directories
        .iter()
        .map(|directory| directory.0.clone())
        .collect::<std::collections::HashSet<_>>();

    assert_eq!(unique_paths.len(), THREADS * ROUNDS);
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
fn imports_legacy_bare_json_as_v1_and_preserves_destination_on_rejection() {
    let dir = temp_dir();
    let input = dir.join("legacy.json");
    let output = dir.join("draft.json");
    let legacy = include_str!("../../../tests/fixtures/deck-draft-legacy-bare-v0.json");
    fs::write(&input, legacy).unwrap();

    let imported = cli(&[
        "import",
        "--input",
        input.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
        "--format",
        "json",
    ]);
    assert!(
        imported.status.success(),
        "{}",
        String::from_utf8_lossy(&imported.stderr)
    );
    let stored = DeckDocumentV1::from_json(&fs::read_to_string(&output).unwrap()).unwrap();
    let expected = DeckDocumentV1::from_json(include_str!(
        "../../../tests/fixtures/deck-draft-legacy-bare-v0.expected-v1.json"
    ))
    .unwrap();
    assert_eq!(stored, expected);
    let destination_before_rejections = fs::read(&output).unwrap();

    let overwrite = cli(&[
        "import",
        "--input",
        input.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
        "--format",
        "json",
    ]);
    assert!(!overwrite.status.success());
    assert_eq!(fs::read(&output).unwrap(), destination_before_rejections);

    let invalid_input = dir.join("invalid.json");
    let invalid_bytes = br#"{"main":[0],"extra":[],"side":[]}"#;
    fs::write(&invalid_input, invalid_bytes).unwrap();
    let invalid = cli(&[
        "import",
        "--input",
        invalid_input.to_str().unwrap(),
        "--output",
        output.to_str().unwrap(),
        "--format",
        "json",
        "--replace",
    ]);
    assert!(!invalid.status.success());
    assert_eq!(fs::read(&invalid_input).unwrap(), invalid_bytes);
    assert_eq!(fs::read(&output).unwrap(), destination_before_rejections);
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
