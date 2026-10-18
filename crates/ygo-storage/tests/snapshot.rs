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
