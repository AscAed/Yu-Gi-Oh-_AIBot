use ygo_storage::{parse_ocg_list, SnapshotStore};
#[test]
fn ocg_list_requires_a_dated_ocg_header_and_valid_limits() {
    assert!(parse_ocg_list("!2026.10 OCG\n1 0\n2 1\n").is_ok());
    assert!(parse_ocg_list("!2026.10 TCG\n1 0").is_err());
    assert!(parse_ocg_list("!2026.10 OCG\n1 4").is_err());
    assert!(parse_ocg_list("!2026.10 OCG\n1 0\n1 1").is_err());
    let root = std::env::temp_dir().join(format!("ygo-hash-{}", std::process::id()));
    let store = SnapshotStore::new(root.clone());
    let a = store
        .import_banlist("!2026.10 OCG\n1 0\n", "fixture", "abc")
        .unwrap();
    let path = root.join(format!("{}.json", a.id));
    std::fs::write(&path, "{}").unwrap();
    assert!(store.banlist(&a.id).is_err());
    std::fs::remove_file(path).unwrap();
    std::fs::remove_dir(root).unwrap();
}
