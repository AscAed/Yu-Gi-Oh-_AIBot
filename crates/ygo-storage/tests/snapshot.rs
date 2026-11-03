use ygo_domain::{Banlist, CardId, Limit};
use ygo_storage::{BanlistProvider, JsonSnapshotStore, SnapshotMetadata};

#[test]
fn stores_and_loads_a_versioned_banlist_snapshot() {
    let root = std::env::temp_dir().join(format!("ygo-storage-test-{}", std::process::id()));
    let store = JsonSnapshotStore::new(root.clone());
    let banlist = Banlist::ocg("2026-09", [(CardId(1), Limit::Limited)]);
    let metadata = SnapshotMetadata::new("ocg-local", "2026-09", "fixture");

    store.save_banlist(&banlist, &metadata).unwrap();
    let loaded = store.load_banlist("2026-09").unwrap().unwrap();

    assert_eq!(loaded.banlist.limit_for(CardId(1)), Limit::Limited);
    std::fs::remove_dir_all(root).unwrap();
}

#[test]
fn banlist_versions_cannot_escape_the_snapshot_directory() {
    let root =
        std::env::temp_dir().join(format!("ygo-storage-traversal-test-{}", std::process::id()));
    std::fs::create_dir_all(root.join("banlist-x")).unwrap();
    let outside_name = format!("ygo-storage-traversal-outside-{}", std::process::id());
    let outside = root.parent().unwrap().join(format!("{outside_name}.json"));
    let sentinel = b"leave this file unchanged";
    std::fs::write(&outside, sentinel).unwrap();

    let store = JsonSnapshotStore::new(root.clone());
    let malicious_version = format!("x/../../{outside_name}");
    let malicious = Banlist::ocg(
        malicious_version.clone(),
        std::iter::empty::<(CardId, Limit)>(),
    );
    let metadata = SnapshotMetadata::new("test", "test", "fixture");

    assert_eq!(
        store
            .save_banlist(&malicious, &metadata)
            .unwrap_err()
            .kind(),
        std::io::ErrorKind::InvalidInput
    );
    assert_eq!(
        store.load_banlist(&malicious_version).unwrap_err().kind(),
        std::io::ErrorKind::InvalidInput
    );
    assert_eq!(std::fs::read(&outside).unwrap(), sentinel);

    std::fs::remove_file(outside).unwrap();
    std::fs::remove_dir_all(root).unwrap();
}
