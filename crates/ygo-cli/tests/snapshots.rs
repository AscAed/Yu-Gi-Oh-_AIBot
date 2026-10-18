use std::process::Command;
use ygo_storage::SnapshotStore;
#[test]
fn explicit_snapshot_ids_bypass_active_and_store_imports_are_isolated() {
    let root = std::env::temp_dir().join(format!("ygo-cli-snapshots-{}", std::process::id()));
    std::fs::create_dir_all(&root).unwrap();
    let store = SnapshotStore::new(root.join("store"));
    let text = "!2026.10 OCG\n1 0\n";
    let snapshot = store.import_banlist(text, "fixture", "abc").unwrap();
    let global = root.join("global.json");
    let out = Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
        .env("YGO_ACTIVE_SNAPSHOT", &global)
        .args([
            "banlist",
            "status",
            "--store",
            store.root.to_str().unwrap(),
            "--id",
            &snapshot.id,
        ])
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    std::fs::write(&global, "{\"sentinel\":true}").unwrap();
    let input = root.join("ocg.conf");
    std::fs::write(&input, text).unwrap();
    let out = Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
        .env("YGO_ACTIVE_SNAPSHOT", &global)
        .args([
            "banlist",
            "import",
            "--store",
            store.root.to_str().unwrap(),
            "--input",
            input.to_str().unwrap(),
            "--commit",
            &"0".repeat(40),
        ])
        .output()
        .unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    assert_eq!(
        std::fs::read_to_string(&global).unwrap(),
        "{\"sentinel\":true}"
    );
    assert!(store.root.join("active.json").is_file());
    std::fs::remove_dir_all(root).unwrap();
}
