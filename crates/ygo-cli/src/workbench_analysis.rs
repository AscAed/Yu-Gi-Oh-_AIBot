//! Internal analysis-input freezing for the local workbench.
//!
//! This module validates and captures immutable input only. It deliberately
//! does not construct a process adapter or start a worker. A future execution
//! path must revalidate live asset identity before invoking the engine.

use serde::{Deserialize, Serialize};
use std::{fs, path::Path};
use ygo_api::combo::{prepare, ComboAnalyzeRequest};
use ygo_domain::{CardId, Catalog, Deck};
use ygo_engine_adapter::{ProcessEngineConfig, RunDuelRequest};
use ygo_search::combo::SearchBudget;
use ygo_storage::{hash, DeckDraftStore, SnapshotStore};

pub mod jobs;

#[cfg(test)]
#[path = "workbench_analysis/jobs_tests.rs"]
mod jobs_tests;

#[derive(Clone, Debug)]
pub struct AnalysisFreezeSpec {
    pub draft_id: String,
    pub expected_revision: String,
    pub opening_hand: Vec<CardId>,
    pub seed: u64,
    pub rules: String,
    pub catalog_id: Option<String>,
    pub banlist_id: String,
    pub as_of: String,
    pub search: SearchBudget,
}

#[derive(Clone, Debug, Eq, PartialEq, Serialize, Deserialize)]
pub struct FrozenAnalysisIdentity {
    pub input_sha256: String,
    pub rules: String,
    pub catalog_id: String,
    pub banlist_id: String,
    pub protocol_version: u16,
    pub engine_sha256: String,
    pub worker_sha256: String,
    pub cdb_sha256: String,
    pub scripts_sha256: String,
    pub engine_manifest_sha256: String,
    pub core_commit: String,
    pub initializer: String,
    pub catalog_source_sha256: String,
    pub banlist_source_sha256: String,
}

/// Owned, revision-bound analysis input. This runtime object intentionally
/// cannot be serialized: it contains local asset paths and a full catalog
/// copy. Retaining it does not certify that local engine assets are current.
#[derive(Clone, Debug)]
pub struct FrozenAnalysisInput {
    pub draft_id: String,
    pub draft_revision: String,
    pub request: ComboAnalyzeRequest,
    pub runtime_request: RunDuelRequest,
    pub catalog: Catalog,
    pub identity: FrozenAnalysisIdentity,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AnalysisFreezeError {
    DraftNotFound,
    DraftInvalid,
    RevisionConflict,
    RulesUnsupported,
    SearchBudgetInvalid,
    AnalysisDateInvalid,
    SnapshotUnavailable,
    BanlistNotEffective,
    DeckIllegal,
    OpeningHandInvalid,
    CatalogCdbMismatch,
    AssetUnavailable,
    AssetChanged,
    PreparationFailed,
}

impl AnalysisFreezeError {
    pub const fn code(self) -> &'static str {
        match self {
            Self::DraftNotFound => "draft_not_found",
            Self::DraftInvalid => "draft_invalid",
            Self::RevisionConflict => "revision_conflict",
            Self::RulesUnsupported => "rules_unsupported",
            Self::SearchBudgetInvalid => "search_budget_invalid",
            Self::AnalysisDateInvalid => "analysis_date_invalid",
            Self::SnapshotUnavailable => "snapshot_unavailable",
            Self::BanlistNotEffective => "banlist_not_effective",
            Self::DeckIllegal => "deck_illegal",
            Self::OpeningHandInvalid => "opening_hand_invalid",
            Self::CatalogCdbMismatch => "catalog_cdb_mismatch",
            Self::AssetUnavailable => "asset_unavailable",
            Self::AssetChanged => "asset_changed_during_freeze",
            Self::PreparationFailed => "preparation_failed",
        }
    }
}

impl std::fmt::Display for AnalysisFreezeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.code())
    }
}

impl std::error::Error for AnalysisFreezeError {}

/// Resolve a service-managed draft at one expected revision and capture the
/// validated, content-addressed analysis inputs. No worker or adapter runs.
pub fn freeze_analysis_input(
    drafts: &DeckDraftStore,
    spec: AnalysisFreezeSpec,
    engine: ProcessEngineConfig,
    snapshots: &SnapshotStore,
    active_catalog: &str,
) -> Result<FrozenAnalysisInput, AnalysisFreezeError> {
    if spec.rules != "ocg-mr5" {
        return Err(AnalysisFreezeError::RulesUnsupported);
    }
    spec.search
        .validate()
        .map_err(|_| AnalysisFreezeError::SearchBudgetInvalid)?;
    ygo_storage::validate_date(&spec.as_of)
        .map_err(|_| AnalysisFreezeError::AnalysisDateInvalid)?;

    let stored = drafts
        .load_at_revision(&spec.draft_id, &spec.expected_revision)
        .map_err(map_draft_error)?;
    let deck = Deck::new(
        stored.draft.main.clone(),
        stored.draft.extra.clone(),
        stored.draft.side.clone(),
    );

    let catalog_id = spec
        .catalog_id
        .clone()
        .unwrap_or_else(|| active_catalog.to_owned());
    let catalog_snapshot = snapshots
        .catalog(&catalog_id)
        .map_err(|_| AnalysisFreezeError::SnapshotUnavailable)?;
    let banlist_snapshot = if spec.banlist_id == "latest-ocg" {
        snapshots
            .latest_ocg(&spec.as_of)
            .map_err(|_| AnalysisFreezeError::SnapshotUnavailable)?
    } else {
        snapshots
            .banlist(&spec.banlist_id)
            .map_err(|_| AnalysisFreezeError::SnapshotUnavailable)?
    };

    ensure_engine_assets(&engine)?;
    let assets_before = asset_hashes(&engine)?;
    let request = ComboAnalyzeRequest {
        deck,
        opening_hand: spec.opening_hand,
        seed: spec.seed,
        rules: spec.rules,
        catalog_id: Some(catalog_snapshot.id.clone()),
        banlist_id: banlist_snapshot.id.clone(),
        as_of: spec.as_of,
        search: spec.search,
    };
    let (request, runtime_request, catalog) =
        prepare(request, engine, snapshots, &catalog_snapshot.id).map_err(map_prepare_error)?;

    let assets_after = asset_hashes(&runtime_request.engine)?;
    if assets_before != assets_after
        || assets_after.engine != runtime_request.versions.engine_sha256
        || assets_after.catalog != runtime_request.versions.cdb_sha256
        || assets_after.script_manifest != runtime_request.versions.scripts_sha256
    {
        return Err(AnalysisFreezeError::AssetChanged);
    }

    let identity_bytes = serde_json::to_vec(&(
        &request,
        &runtime_request.versions,
        &assets_after.worker,
        &assets_after.engine_manifest,
        &catalog_snapshot.source_sha256,
        &banlist_snapshot.source_sha256,
        &stored.id,
        &stored.revision,
    ))
    .map_err(|_| AnalysisFreezeError::PreparationFailed)?;
    let identity = FrozenAnalysisIdentity {
        input_sha256: hash(&identity_bytes),
        rules: request.rules.clone(),
        catalog_id: runtime_request.versions.catalog.clone(),
        banlist_id: runtime_request.versions.banlist.clone(),
        protocol_version: runtime_request.protocol_version,
        engine_sha256: runtime_request.versions.engine_sha256.clone(),
        worker_sha256: assets_after.worker,
        cdb_sha256: runtime_request.versions.cdb_sha256.clone(),
        scripts_sha256: runtime_request.versions.scripts_sha256.clone(),
        engine_manifest_sha256: assets_after.engine_manifest,
        core_commit: runtime_request.versions.core_commit.clone(),
        initializer: runtime_request.versions.initializer.clone(),
        catalog_source_sha256: catalog_snapshot.source_sha256,
        banlist_source_sha256: banlist_snapshot.source_sha256,
    };
    Ok(FrozenAnalysisInput {
        draft_id: stored.id,
        draft_revision: stored.revision,
        request,
        runtime_request,
        catalog,
        identity,
    })
}

fn ensure_engine_assets(engine: &ProcessEngineConfig) -> Result<(), AnalysisFreezeError> {
    for path in [
        &engine.worker_path,
        &engine.ocgcore_path,
        &engine.catalog_path,
        &engine.script_manifest_path,
        &engine.engine_manifest_path,
    ] {
        if !fs::metadata(path).is_ok_and(|metadata| metadata.is_file()) {
            return Err(AnalysisFreezeError::AssetUnavailable);
        }
    }
    if !fs::metadata(&engine.scripts_path).is_ok_and(|metadata| metadata.is_dir()) {
        return Err(AnalysisFreezeError::AssetUnavailable);
    }
    Ok(())
}

#[derive(Debug, Eq, PartialEq)]
struct AssetHashes {
    engine: String,
    worker: String,
    catalog: String,
    script_manifest: String,
    engine_manifest: String,
}

fn asset_hashes(engine: &ProcessEngineConfig) -> Result<AssetHashes, AnalysisFreezeError> {
    let hash_asset = |path: &Path| {
        ygo_storage::file_hash(path).map_err(|_| AnalysisFreezeError::AssetUnavailable)
    };
    Ok(AssetHashes {
        engine: hash_asset(&engine.ocgcore_path)?,
        worker: hash_asset(&engine.worker_path)?,
        catalog: hash_asset(&engine.catalog_path)?,
        script_manifest: hash_asset(&engine.script_manifest_path)?,
        engine_manifest: hash_asset(&engine.engine_manifest_path)?,
    })
}

fn map_draft_error(error: String) -> AnalysisFreezeError {
    if error == "revision_conflict" {
        AnalysisFreezeError::RevisionConflict
    } else if error.starts_with("draft_not_found:") {
        AnalysisFreezeError::DraftNotFound
    } else {
        AnalysisFreezeError::DraftInvalid
    }
}

fn map_prepare_error(error: String) -> AnalysisFreezeError {
    if error == "only ocg-mr5 is supported" {
        AnalysisFreezeError::RulesUnsupported
    } else if error.contains("search budget") {
        AnalysisFreezeError::SearchBudgetInvalid
    } else if error.contains("banlist not effective") {
        AnalysisFreezeError::BanlistNotEffective
    } else if error.contains("opening hand") || error.contains("hand contains") {
        AnalysisFreezeError::OpeningHandInvalid
    } else if error.contains("date") || error.contains("calendar") {
        AnalysisFreezeError::AnalysisDateInvalid
    } else if error.contains("catalog snapshot does not match engine CDB") {
        AnalysisFreezeError::CatalogCdbMismatch
    } else if serde_json::from_str::<serde_json::Value>(&error)
        .ok()
        .and_then(|value| value.get("violations").cloned())
        .and_then(|value| value.as_array().cloned())
        .is_some_and(|violations| !violations.is_empty())
    {
        AnalysisFreezeError::DeckIllegal
    } else if error.contains("snapshot") || error.contains("banlist") || error.contains("catalog") {
        AnalysisFreezeError::SnapshotUnavailable
    } else if error.contains("asset_missing") || Path::new(&error).is_absolute() {
        AnalysisFreezeError::AssetUnavailable
    } else {
        AnalysisFreezeError::PreparationFailed
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::{collections::BTreeMap, fs, ops::Deref, path::Path, path::PathBuf};
    use ygo_domain::{Banlist, Card, CardId, CardKind, DeckDocumentV1};
    use ygo_engine_adapter::ProcessEngineConfig;
    use ygo_search::combo::SearchBudget;
    use ygo_storage::{hash, DataSnapshot, DeckDraftStore, SnapshotStore};

    static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);

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
            "ygo-workbench-freeze-{}-{}",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(&path).unwrap();
        TempDir(path)
    }

    fn snapshot_id<T: Serialize>(
        kind: &str,
        source: &str,
        version: &str,
        source_sha: &str,
        date: &Option<String>,
        normalizer: &str,
        data: &T,
    ) -> String {
        let content = serde_json::to_vec(data).unwrap();
        let provenance = serde_json::to_vec(&(
            kind,
            &source,
            &version,
            &source_sha,
            date,
            normalizer,
            &content,
        ))
        .unwrap();
        format!("{kind}-{}", hash(&provenance))
    }

    pub(super) fn fixtures(
        root: &Path,
    ) -> (
        DeckDraftStore,
        SnapshotStore,
        ProcessEngineConfig,
        String,
        String,
        DeckDocumentV1,
    ) {
        let drafts = DeckDraftStore::open(root.join("drafts")).unwrap();
        let snapshots_dir = root.join("snapshots");
        fs::create_dir_all(&snapshots_dir).unwrap();
        let engine_dir = root.join("engine");
        fs::create_dir_all(&engine_dir).unwrap();
        let ocgcore_path = engine_dir.join("core.bin");
        let catalog_path = engine_dir.join("cards.cdb");
        let script_manifest_path = engine_dir.join("scripts.json");
        let worker_path = engine_dir.join("worker.exe");
        let engine_manifest_path = engine_dir.join("engine-manifest.json");
        let scripts_path = engine_dir.join("scripts");
        fs::write(&ocgcore_path, b"synthetic core").unwrap();
        fs::write(&catalog_path, b"synthetic cdb identity bytes").unwrap();
        fs::write(&script_manifest_path, b"synthetic script manifest").unwrap();
        fs::write(&worker_path, b"synthetic worker identity; never executed").unwrap();
        fs::write(&engine_manifest_path, b"synthetic engine manifest").unwrap();
        fs::create_dir_all(&scripts_path).unwrap();
        let engine = ProcessEngineConfig {
            worker_path,
            ocgcore_path,
            catalog_path: catalog_path.clone(),
            scripts_path,
            script_manifest_path,
            engine_manifest_path,
            ..ProcessEngineConfig::default()
        };

        let main: Vec<u32> = (1..=40).map(|n| ((n - 1) % 15) + 1).collect();
        let draft = DeckDocumentV1::new("Synthetic", main.clone(), vec![], vec![]).unwrap();
        let catalog = (1..=15)
            .map(|id| {
                (
                    CardId(id),
                    Card {
                        id: CardId(id),
                        name: format!("Card {id}"),
                        kind: CardKind::Monster,
                        type_flags: 1,
                        ..Default::default()
                    },
                )
            })
            .collect::<BTreeMap<_, _>>();
        let source = "synthetic".to_owned();
        let version = "fixture".to_owned();
        let source_sha = hash(&fs::read(&catalog_path).unwrap());
        let date = None;
        let normalizer = "normalizer-v1".to_owned();
        let catalog_id = snapshot_id(
            "catalog",
            &source,
            &version,
            &source_sha,
            &date,
            &normalizer,
            &catalog,
        );
        let catalog_snapshot = DataSnapshot {
            id: catalog_id.clone(),
            schema_version: 2,
            source: source.clone(),
            source_version: version.clone(),
            source_sha256: source_sha,
            effective_date: date.clone(),
            retrieved_at: "test".into(),
            license: "synthetic".into(),
            normalizer_version: normalizer.clone(),
            data: catalog,
        };
        fs::write(
            snapshots_dir.join(format!("{catalog_id}.json")),
            serde_json::to_vec(&catalog_snapshot).unwrap(),
        )
        .unwrap();

        let banlist = Banlist::ocg("fixture", Vec::<(CardId, ygo_domain::Limit)>::new());
        let ban_source_sha = hash(b"synthetic banlist");
        let ban_date = Some("2026-10-01".to_owned());
        let banlist_id = snapshot_id(
            "banlist",
            &source,
            &version,
            &ban_source_sha,
            &ban_date,
            &normalizer,
            &banlist,
        );
        let banlist_snapshot = DataSnapshot {
            id: banlist_id.clone(),
            schema_version: 2,
            source,
            source_version: version,
            source_sha256: ban_source_sha,
            effective_date: ban_date,
            retrieved_at: "test".into(),
            license: "synthetic".into(),
            normalizer_version: normalizer,
            data: banlist,
        };
        fs::write(
            snapshots_dir.join(format!("{banlist_id}.json")),
            serde_json::to_vec(&banlist_snapshot).unwrap(),
        )
        .unwrap();
        let store = SnapshotStore::new(snapshots_dir);
        store.catalog(&catalog_id).unwrap();
        store.banlist(&banlist_id).unwrap();
        (drafts, store, engine, catalog_id, banlist_id, draft)
    }

    pub(super) fn spec(
        draft_id: String,
        revision: String,
        banlist_id: String,
        hand: Vec<CardId>,
    ) -> AnalysisFreezeSpec {
        AnalysisFreezeSpec {
            draft_id,
            expected_revision: revision,
            opening_hand: hand,
            seed: 1,
            rules: "ocg-mr5".into(),
            catalog_id: None,
            banlist_id,
            as_of: "2026-10-30".into(),
            search: SearchBudget::default(),
        }
    }

    #[test]
    fn freeze_uses_locked_draft_revision_and_owned_snapshot_after_sources_change() {
        let root = temp_dir();
        let (drafts, snapshots, engine, catalog_id, banlist, draft) = fixtures(&root);
        let stored = drafts.create(draft.clone()).unwrap();
        let request = spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist,
            draft.main[..5].to_vec(),
        );
        let frozen =
            freeze_analysis_input(&drafts, request, engine, &snapshots, &catalog_id).unwrap();

        fs::remove_file(snapshots.root.join(format!("{catalog_id}.json"))).unwrap();
        fs::remove_file(
            snapshots
                .root
                .join(format!("{}.json", frozen.identity.banlist_id)),
        )
        .unwrap();
        let revised = DeckDocumentV1::new("Later edit", vec![99; 40], vec![], vec![]).unwrap();
        drafts
            .update(&stored.id, &stored.revision, revised)
            .unwrap();

        assert_eq!(frozen.draft_revision, stored.revision);
        assert_eq!(frozen.request.deck.main, draft.main);
        assert_eq!(frozen.runtime_request.deck.main, draft.main);
        assert_eq!(
            frozen.request.catalog_id.as_deref(),
            Some(frozen.identity.catalog_id.as_str())
        );
        assert_eq!(frozen.request.banlist_id, frozen.identity.banlist_id);
        assert_eq!(
            frozen.identity.cdb_sha256,
            frozen.runtime_request.versions.cdb_sha256
        );
        assert_eq!(frozen.request.search.node_budget, 10_000);
    }

    #[test]
    fn freeze_rejects_stale_revision_without_leaking_local_paths() {
        let root = temp_dir();
        let (drafts, snapshots, engine, catalog_id, banlist, draft) = fixtures(&root);
        let stored = drafts.create(draft.clone()).unwrap();
        let mut request = spec(
            stored.id,
            "stale-revision".into(),
            banlist,
            draft.main[..5].to_vec(),
        );
        request.catalog_id = None;
        let error =
            freeze_analysis_input(&drafts, request, engine, &snapshots, &catalog_id).unwrap_err();
        assert_eq!(error.code(), "revision_conflict");
        assert!(!error.to_string().contains(root.to_string_lossy().as_ref()));
    }

    #[test]
    fn freeze_rejects_invalid_hand_budget_and_catalog_cdb_mismatch() {
        let root = temp_dir();
        let (drafts, snapshots, engine, catalog_id, banlist, draft) = fixtures(&root);
        let stored = drafts.create(draft.clone()).unwrap();
        let short_hand = spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist.clone(),
            draft.main[..4].to_vec(),
        );
        assert_eq!(
            freeze_analysis_input(&drafts, short_hand, engine.clone(), &snapshots, &catalog_id)
                .unwrap_err()
                .code(),
            "opening_hand_invalid"
        );

        let mut invalid_budget = spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist.clone(),
            draft.main[..5].to_vec(),
        );
        invalid_budget.search.node_budget = 0;
        assert_eq!(
            freeze_analysis_input(
                &drafts,
                invalid_budget,
                engine.clone(),
                &snapshots,
                &catalog_id
            )
            .unwrap_err()
            .code(),
            "search_budget_invalid"
        );

        let mismatch_dir = root.join("mismatch");
        fs::create_dir_all(&mismatch_dir).unwrap();
        let mismatch_path = mismatch_dir.join("cards.cdb");
        fs::write(&mismatch_path, b"different cdb bytes").unwrap();
        let mismatch_engine = ProcessEngineConfig {
            catalog_path: mismatch_path,
            ..engine
        };
        let request = spec(
            stored.id,
            stored.revision,
            banlist,
            draft.main[..5].to_vec(),
        );
        assert_eq!(
            freeze_analysis_input(&drafts, request, mismatch_engine, &snapshots, &catalog_id)
                .unwrap_err()
                .code(),
            "catalog_cdb_mismatch"
        );
    }

    #[test]
    fn freeze_rejects_illegal_deck_ineffective_banlist_bad_date_and_missing_assets() {
        let root = temp_dir();
        let (drafts, snapshots, engine, catalog_id, banlist_id, draft) = fixtures(&root);
        let illegal = DeckDocumentV1::new(
            "Too small",
            draft.main[..39].iter().map(|id| id.0).collect(),
            vec![],
            vec![],
        )
        .unwrap();
        let illegal_stored = drafts.create(illegal.clone()).unwrap();
        let request = spec(
            illegal_stored.id,
            illegal_stored.revision,
            banlist_id.clone(),
            illegal.main[..5].to_vec(),
        );
        assert_eq!(
            freeze_analysis_input(&drafts, request, engine.clone(), &snapshots, &catalog_id)
                .unwrap_err()
                .code(),
            "deck_illegal"
        );

        let stored = drafts.create(draft.clone()).unwrap();
        let mut before_effective_date = spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist_id.clone(),
            draft.main[..5].to_vec(),
        );
        before_effective_date.as_of = "2026-09-30".into();
        assert_eq!(
            freeze_analysis_input(
                &drafts,
                before_effective_date,
                engine.clone(),
                &snapshots,
                &catalog_id
            )
            .unwrap_err()
            .code(),
            "banlist_not_effective"
        );

        let mut malformed_date = spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist_id.clone(),
            draft.main[..5].to_vec(),
        );
        malformed_date.as_of = "not-a-date".into();
        assert_eq!(
            freeze_analysis_input(
                &drafts,
                malformed_date,
                engine.clone(),
                &snapshots,
                &catalog_id
            )
            .unwrap_err()
            .code(),
            "analysis_date_invalid"
        );

        let missing_worker = ProcessEngineConfig {
            worker_path: root.join("missing-worker.exe"),
            ..engine
        };
        let request = spec(
            stored.id,
            stored.revision,
            banlist_id,
            draft.main[..5].to_vec(),
        );
        let error =
            freeze_analysis_input(&drafts, request, missing_worker, &snapshots, &catalog_id)
                .unwrap_err();
        assert_eq!(error.code(), "asset_unavailable");
        assert!(!error.to_string().contains(root.to_string_lossy().as_ref()));
    }
}

pub mod queue;
#[cfg(test)]
#[path = "workbench_analysis/queue_tests.rs"]
mod queue_tests;
