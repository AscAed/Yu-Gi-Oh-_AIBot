use std::{
    fs,
    ops::Deref,
    path::{Path, PathBuf},
    sync::Arc,
    thread,
};
use ygo_domain::DeckDocumentV1;
use ygo_storage::DeckDraftStore;

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
    let root = std::env::temp_dir().join(format!(
        "ygo-workbench-store-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&root).unwrap();
    TempDir(root)
}

fn draft(title: &str, main: Vec<u32>) -> DeckDocumentV1 {
    DeckDocumentV1::new(title, main, vec![7], vec![9]).unwrap()
}

#[test]
fn managed_store_preserves_order_duplicates_and_detects_stale_edits() {
    let root = temp_dir();
    let store = DeckDraftStore::open(root.to_path_buf()).unwrap();
    let created = store.create(draft("test", vec![4, 2, 4])).unwrap();
    assert_eq!(
        created.draft.main.iter().map(|id| id.0).collect::<Vec<_>>(),
        [4, 2, 4]
    );
    let updated = store
        .update(
            &created.id,
            &created.revision,
            draft("updated", vec![4, 8, 4]),
        )
        .unwrap();
    assert_ne!(updated.revision, created.revision);
    assert!(store
        .update(&created.id, &created.revision, draft("stale", vec![]))
        .unwrap_err()
        .contains("revision_conflict"));
    assert_eq!(store.load(&created.id).unwrap(), updated);
    assert_eq!(store.list().unwrap().len(), 1);
}

#[test]
fn managed_store_creation_is_exclusive_and_concurrent_ids_do_not_collide() {
    let root = temp_dir();
    let store = Arc::new(DeckDraftStore::open(root.to_path_buf()).unwrap());
    let mut workers = Vec::new();
    for _ in 0..12 {
        let store = store.clone();
        workers.push(thread::spawn(move || {
            store.create(draft("parallel", vec![])).unwrap()
        }));
    }
    let entries = workers
        .into_iter()
        .map(|worker| worker.join().unwrap())
        .collect::<Vec<_>>();
    let ids = entries
        .iter()
        .map(|entry| entry.id.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(ids.len(), 12);
    assert_eq!(store.list().unwrap().len(), 12);
    assert!(
        DeckDraftStore::open(root.to_path_buf()).is_err(),
        "second service must not own the same draft directory"
    );
}

#[test]
fn managed_store_rejects_non_generated_ids_and_preserves_existing_bytes_on_conflict() {
    let root = temp_dir();
    let store = DeckDraftStore::open(root.to_path_buf()).unwrap();
    let created = store.create(draft("keep", vec![11])).unwrap();
    let path = root.join(format!("{}.json", created.id));
    let before = fs::read(&path).unwrap();
    assert!(store.load("../../outside").is_err());
    assert_eq!(fs::read(path).unwrap(), before);
}

#[test]
fn concurrent_updates_using_the_same_revision_allow_only_one_writer() {
    let root = temp_dir();
    let store = Arc::new(DeckDraftStore::open(root.to_path_buf()).unwrap());
    let created = store.create(draft("initial", vec![1])).unwrap();
    let barrier = Arc::new(std::sync::Barrier::new(3));
    let mut workers = Vec::new();
    for card in [2, 3] {
        let store = store.clone();
        let barrier = barrier.clone();
        let id = created.id.clone();
        let revision = created.revision.clone();
        workers.push(thread::spawn(move || {
            barrier.wait();
            store.update(&id, &revision, draft("race", vec![card]))
        }));
    }
    barrier.wait();
    let outcomes = workers
        .into_iter()
        .map(|worker| worker.join().unwrap())
        .collect::<Vec<_>>();
    assert_eq!(outcomes.iter().filter(|result| result.is_ok()).count(), 1);
    assert_eq!(
        outcomes
            .iter()
            .filter(|result| result
                .as_ref()
                .is_err_and(|error| error == "revision_conflict"))
            .count(),
        1
    );
}
