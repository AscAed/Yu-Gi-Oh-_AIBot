//! Independent negative cases exercise storage parsing and cross-chain checks.
use super::{
    jobs::AnalysisJobRecordV1,
    operations::{AnalysisOperationCommand, AnalysisOperationContext, AnalysisOperationRecordV1},
    persistence::{PersistenceError, PersistentAnalysisJobStore},
    tests::{fixtures, spec},
    *,
};
use serde_json::Value;
use std::path::PathBuf;
use ygo_search::combo::ScoringConfig;

fn root() -> PathBuf {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1h21-analysis-operation-tests/storage-negative")
        .join(ygo_storage::secure_random_hex(16).unwrap());
    fs::create_dir_all(&path).unwrap();
    path
}

fn allocated() -> AnalysisOperationRecordV1 {
    AnalysisOperationRecordV1::allocate(
        "c".repeat(32),
        AnalysisOperationContext {
            scoring: ScoringConfig::default(),
            default_catalog_id: format!("catalog-{}", "a".repeat(64)),
            configuration_sha256: "b".repeat(64),
        },
        100,
    )
    .unwrap()
}

#[test]
fn every_operation_envelope_field_is_required_including_explicit_null() {
    for field in [
        "schema_version",
        "kind",
        "operation_id",
        "revision",
        "previous_sha256",
        "record_sha256",
        "record",
    ] {
        let path = root();
        let store = PersistentAnalysisJobStore::open_unclassified(path.clone()).unwrap();
        let op = allocated();
        store.append_operation(&op).unwrap();
        let file = path
            .join("operations")
            .join(op.operation_id())
            .join("revisions/1.json");
        let mut envelope: Value = serde_json::from_slice(&fs::read(&file).unwrap()).unwrap();
        envelope.as_object_mut().unwrap().remove(field);
        fs::write(&file, serde_json::to_vec(&envelope).unwrap()).unwrap();
        assert_eq!(
            store.operation_history(op.operation_id()).unwrap_err(),
            PersistenceError::RecordInvalid,
            "{field}"
        );
    }
}

#[test]
fn individually_valid_chains_reject_different_frozen_job_binding() {
    let path = root();
    let fixture = path.join("fixtures");
    fs::create_dir_all(&fixture).unwrap();
    let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&fixture);
    let saved = drafts.create(draft.clone()).unwrap();
    let request = spec(saved.id, saved.revision, banlist, draft.main[..5].to_vec());
    let frozen = freeze_analysis_input(
        &drafts,
        request.clone(),
        engine.clone(),
        &snapshots,
        &catalog,
    )
    .unwrap();
    let mut different_request = request.clone();
    different_request.seed += 1;
    let different =
        freeze_analysis_input(&drafts, different_request, engine, &snapshots, &catalog).unwrap();
    let scoring = ScoringConfig::default();
    let job_id = "d".repeat(32);
    let job = AnalysisJobRecordV1::new(job_id.clone(), &frozen, scoring.clone(), 100).unwrap();
    let different_job =
        AnalysisJobRecordV1::new(job_id.clone(), &different, scoring.clone(), 100).unwrap();
    let context = AnalysisOperationContext {
        scoring,
        default_catalog_id: catalog,
        configuration_sha256: "b".repeat(64),
    };
    let command = AnalysisOperationCommand {
        draft_id: request.draft_id,
        draft_revision: request.expected_revision,
        opening_hand: request.opening_hand,
        seed: request.seed,
        rules: request.rules,
        catalog_id: request.catalog_id,
        banlist_id: request.banlist_id,
        as_of: request.as_of,
        search: request.search,
    };
    let store = PersistentAnalysisJobStore::open_unclassified(path.join("store")).unwrap();
    let allocated = AnalysisOperationRecordV1::allocate("c".repeat(32), context, 100).unwrap();
    let begun = allocated.begin(command, job_id.clone(), 101).unwrap();
    let bound = begun.bind_input(job.input().clone(), 102).unwrap();
    let accepted = bound.accept(103).unwrap();
    for op in [allocated, begun, bound, accepted.clone()] {
        store.append_operation(&op).unwrap();
    }
    store.append_initial(different_job).unwrap();
    assert_eq!(
        store
            .operation_history(accepted.operation_id())
            .unwrap()
            .len(),
        4
    );
    assert_eq!(store.history(&job_id).unwrap().len(), 1);
    assert_eq!(
        store.authenticate_operation_bindings().unwrap_err(),
        PersistenceError::InvalidChain
    );
}

#[cfg(unix)]
#[test]
fn operation_revision_symlink_is_rejected_without_reading_target() {
    let path = root();
    let store = PersistentAnalysisJobStore::open_unclassified(path.clone()).unwrap();
    let op = allocated();
    store.append_operation(&op).unwrap();
    let file = path
        .join("operations")
        .join(op.operation_id())
        .join("revisions/1.json");
    let outside = path.join("outside.json");
    fs::rename(&file, &outside).unwrap();
    std::os::unix::fs::symlink(&outside, &file).unwrap();
    assert_eq!(
        store.operation_history(op.operation_id()).unwrap_err(),
        PersistenceError::InvalidPath
    );
    assert!(outside.exists());
}
