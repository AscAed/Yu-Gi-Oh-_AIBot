use super::FrozenAnalysisInput;
use crate::workbench_analysis::operations::AnalysisOperationCommand;
use serde_json::Value;
use std::path::{Path, PathBuf};
use ygo_api::combo::ComboAnalyzeRequest;
use ygo_engine_adapter::{capture_engine_identity, ProcessEngineConfig, INITIALIZER_VERSION};
use ygo_search::combo::SearchBudget;
use ygo_storage::{file_hash, hash, SnapshotStore};

const REQUEST_SHA256: &str = "bd5f0427dbd68583b203702a9c8950e2263791c3a62b2685ca89773ea1631378";
const YDK_SHA256: &str = "028760778e47d46c3f366f0345957f597ee820774641e6e2800a718763bbd9fa";
const CATALOG_ID: &str = "catalog-1b0564fd61eec4730828fea1d48391aa1598bca3157c255454a8dcf487485d6d";
const CATALOG_SNAPSHOT_SHA256: &str =
    "3c0fa6249f4e5172488bf325f8d659070cfefb3d93115b7ec690e0486da4cbf7";
const BANLIST_ID: &str = "banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783";
const BANLIST_SNAPSHOT_SHA256: &str =
    "a6344cd77c4db6dcfab02d03110954fa1c2717422f71da302970f427564506c9";
const CDB_SHA256: &str = "c49a077285e1d999f32056cb65303b75e311e859b4486c48f41772a193069225";
const CORE_SHA256: &str = "446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9";
const ENGINE_MANIFEST_SHA256: &str =
    "3fadb68cd22e9e01d8083c581ffd442f64e6af65a6c2827544b19e5bab14aa00";
const SCRIPT_MANIFEST_SHA256: &str =
    "69bf6f9d3fe444fd53890c60bde877f97b753f8d3e218a6349615d09f6740d91";
const ENGINE_TIMEOUT_MS: u64 = 30_000;

const RABBIT_REQUEST: &[u8] = include_bytes!("../../../../tests/fixtures/rabbit.request.json");
const RABBIT_YDK: &[u8] = include_bytes!("../../../../tests/fixtures/rabbit.ydk");

#[derive(Clone)]
struct RuntimeIdentity {
    executable_path: PathBuf,
    executable_sha256: String,
    worker_sha256: String,
    config_path: PathBuf,
    config_sha256: String,
    snapshots_dir: PathBuf,
    engine: ProcessEngineConfig,
}

/// Restricts the explicitly enabled production workbench to the documented
/// one-run Rabbit input and the frozen local asset set.
#[derive(Clone)]
pub(crate) struct W1cAdmission {
    expected: ComboAnalyzeRequest,
    runtime: Option<RuntimeIdentity>,
}

impl W1cAdmission {
    // Used by the non-test CLI binary; unit tests exercise the policy with the
    // pinned fixtures and synthetic durable inputs instead.
    #[allow(dead_code)]
    pub(crate) fn load(
        config_path: &Path,
        config_bytes: &[u8],
        snapshots_dir: &Path,
        selected_catalog_id: &str,
        engine: &ProcessEngineConfig,
    ) -> Result<Self, String> {
        let expected = fixed_request()?;
        if selected_catalog_id != CATALOG_ID {
            return Err("workbench_analysis_profile_mismatch".into());
        }
        if config_bytes.is_empty() || engine.timeout_ms != ENGINE_TIMEOUT_MS {
            return Err("workbench_analysis_profile_mismatch".into());
        }

        let snapshots = SnapshotStore::new(snapshots_dir.to_path_buf());
        let catalog = snapshots.catalog(CATALOG_ID)?;
        let banlist = snapshots.banlist(BANLIST_ID)?;
        if catalog.id != CATALOG_ID
            || banlist.id != BANLIST_ID
            || banlist.effective_date.as_deref() != Some("2026-10-01")
            || file_hash(&snapshots_dir.join(format!("{CATALOG_ID}.json")))?
                != CATALOG_SNAPSHOT_SHA256
            || file_hash(&snapshots_dir.join(format!("{BANLIST_ID}.json")))?
                != BANLIST_SNAPSHOT_SHA256
        {
            return Err("workbench_analysis_snapshot_identity_mismatch".into());
        }

        let executable_path =
            std::env::current_exe().map_err(|_| "workbench_analysis_package_unavailable")?;
        let executable_path = executable_path
            .canonicalize()
            .map_err(|_| "workbench_analysis_package_unavailable")?;
        let target_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../..")
            .join("target/w1c-executor/cargo")
            .canonicalize()
            .map_err(|_| "workbench_analysis_isolated_target_required")?;
        if !executable_path.starts_with(&target_root) {
            return Err("workbench_analysis_isolated_target_required".into());
        }
        let executable_dir = executable_path
            .parent()
            .ok_or("workbench_analysis_package_unavailable")?;
        let worker_dir = engine
            .worker_path
            .canonicalize()
            .map_err(|_| "workbench_analysis_worker_unavailable")?
            .parent()
            .map(Path::to_path_buf)
            .ok_or("workbench_analysis_worker_unavailable")?;
        if executable_dir != worker_dir {
            return Err("workbench_analysis_package_mismatch".into());
        }

        let engine_identity = capture_engine_identity(engine)
            .map_err(|_| "workbench_analysis_asset_identity_unavailable")?;
        validate_engine_identity(&engine_identity)?;
        let config_sha256 = hash(config_bytes);
        let config_path = config_path
            .canonicalize()
            .map_err(|_| "workbench_analysis_config_unavailable")?;
        if file_hash(&config_path).map_err(|_| "workbench_analysis_config_unavailable")?
            != config_sha256
        {
            return Err("workbench_analysis_config_changed".into());
        }
        let worker_sha256 = role_hash(&engine_identity, "worker")
            .ok_or("workbench_analysis_asset_identity_unavailable")?
            .to_owned();

        Ok(Self {
            expected,
            runtime: Some(RuntimeIdentity {
                executable_sha256: file_hash(&executable_path)
                    .map_err(|_| "workbench_analysis_package_unavailable")?,
                executable_path,
                worker_sha256,
                config_path,
                config_sha256,
                snapshots_dir: snapshots_dir
                    .canonicalize()
                    .map_err(|_| "workbench_analysis_snapshot_unavailable")?,
                engine: engine.clone(),
            }),
        })
    }

    pub(crate) fn matches_command(&self, command: &AnalysisOperationCommand) -> bool {
        command.opening_hand == self.expected.opening_hand
            && command.seed == self.expected.seed
            && command.rules == self.expected.rules
            && command.catalog_id.as_deref() == Some(CATALOG_ID)
            && command.banlist_id == BANLIST_ID
            && command.as_of == self.expected.as_of
            && same_budget(&command.search, &self.expected.search)
    }

    pub(crate) fn matches_frozen(&self, input: &FrozenAnalysisInput) -> bool {
        let request = &input.request;
        self.matches_request(request)
            && input.identity.catalog_id == CATALOG_ID
            && input.identity.banlist_id == BANLIST_ID
            && input.identity.engine_sha256 == CORE_SHA256
            && input.identity.cdb_sha256 == CDB_SHA256
            && input.identity.scripts_sha256 == SCRIPT_MANIFEST_SHA256
            && input.identity.engine_manifest_sha256 == ENGINE_MANIFEST_SHA256
            && input.identity.core_commit == ygo_engine_adapter::CORE_COMMIT
            && input.identity.initializer == INITIALIZER_VERSION
            && input.identity.protocol_version == ygo_engine_adapter::PROTOCOL_VERSION
            && self.runtime.as_ref().map_or(true, |runtime| {
                input.identity.worker_sha256 == runtime.worker_sha256
                    && same_engine_config(&input.runtime_request.engine, &runtime.engine)
            })
    }

    fn matches_request(&self, request: &ComboAnalyzeRequest) -> bool {
        request.deck.main == self.expected.deck.main
            && request.deck.extra == self.expected.deck.extra
            && request.deck.side == self.expected.deck.side
            && request.opening_hand == self.expected.opening_hand
            && request.seed == self.expected.seed
            && request.rules == self.expected.rules
            && request.catalog_id.as_deref() == Some(CATALOG_ID)
            && request.banlist_id == BANLIST_ID
            && request.as_of == self.expected.as_of
            && same_budget(&request.search, &self.expected.search)
    }

    /// Rechecks the running package and pinned snapshots after the durable
    /// coordinator's claim path has rehashed the complete engine asset tree.
    pub(crate) fn verify_package_files(&self) -> Result<(), &'static str> {
        let Some(runtime) = self.runtime.as_ref() else {
            return Ok(());
        };
        let executable = std::env::current_exe().map_err(|_| "analysis_package_mismatch")?;
        if executable.canonicalize().ok().as_deref() != Some(runtime.executable_path.as_path())
            || file_hash(&runtime.executable_path).ok().as_deref()
                != Some(runtime.executable_sha256.as_str())
            || file_hash(&runtime.config_path).ok().as_deref()
                != Some(runtime.config_sha256.as_str())
            || file_hash(&runtime.engine.worker_path).ok().as_deref()
                != Some(runtime.worker_sha256.as_str())
        {
            return Err("analysis_package_mismatch");
        }
        let snapshots = &runtime.snapshots_dir;
        if file_hash(&snapshots.join(format!("{CATALOG_ID}.json")))
            .ok()
            .as_deref()
            != Some(CATALOG_SNAPSHOT_SHA256)
            || file_hash(&snapshots.join(format!("{BANLIST_ID}.json")))
                .ok()
                .as_deref()
                != Some(BANLIST_SNAPSHOT_SHA256)
        {
            return Err("analysis_snapshot_identity_mismatch");
        }
        Ok(())
    }

    #[cfg(test)]
    pub(crate) fn fixture_policy() -> Self {
        Self {
            expected: fixed_request().unwrap(),
            runtime: None,
        }
    }
}

fn fixed_request() -> Result<ComboAnalyzeRequest, String> {
    if hash(RABBIT_REQUEST) != REQUEST_SHA256 || hash(RABBIT_YDK) != YDK_SHA256 {
        return Err("workbench_analysis_fixture_identity_mismatch".into());
    }
    let mut request: ComboAnalyzeRequest =
        serde_json::from_slice(RABBIT_REQUEST).map_err(|_| "workbench_analysis_fixture_invalid")?;
    request.catalog_id = Some(CATALOG_ID.into());
    request.banlist_id = BANLIST_ID.into();
    Ok(request)
}

fn same_budget(left: &SearchBudget, right: &SearchBudget) -> bool {
    left.top_k == right.top_k
        && left.node_budget == right.node_budget
        && left.beam_width == right.beam_width
        && left.max_depth == right.max_depth
        && left.time_limit_ms == right.time_limit_ms
}

fn same_engine_config(left: &ProcessEngineConfig, right: &ProcessEngineConfig) -> bool {
    left.worker_path == right.worker_path
        && left.ocgcore_path == right.ocgcore_path
        && left.catalog_path == right.catalog_path
        && left.scripts_path == right.scripts_path
        && left.script_manifest_path == right.script_manifest_path
        && left.engine_manifest_path == right.engine_manifest_path
        && left.timeout_ms == right.timeout_ms
}

fn role_hash<'a>(identity: &'a Value, role: &str) -> Option<&'a str> {
    identity.get("roles")?.get(role)?.get("sha256")?.as_str()
}

fn validate_engine_identity(identity: &Value) -> Result<(), String> {
    if identity.get("consistent").and_then(Value::as_bool) != Some(true)
        || role_hash(identity, "dll") != Some(CORE_SHA256)
        || role_hash(identity, "cdb") != Some(CDB_SHA256)
        || role_hash(identity, "script_manifest") != Some(SCRIPT_MANIFEST_SHA256)
        || role_hash(identity, "engine_manifest") != Some(ENGINE_MANIFEST_SHA256)
        || identity.get("timeout_ms").and_then(Value::as_u64) != Some(ENGINE_TIMEOUT_MS)
    {
        return Err("workbench_analysis_asset_identity_mismatch".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use ygo_domain::CardId;

    struct TempRoot(PathBuf);

    impl TempRoot {
        fn new() -> Self {
            let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../target/w1c-executor/cargo/admission-tests")
                .join(ygo_storage::secure_random_hex(16).unwrap());
            std::fs::create_dir_all(&path).unwrap();
            Self(path)
        }

        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn package_fixture(root: &Path) -> (W1cAdmission, PathBuf, PathBuf, PathBuf) {
        let config_path = root.join("analysis.toml");
        let worker_path = root.join("worker.exe");
        let snapshots_dir = root.join("snapshots");
        std::fs::create_dir_all(&snapshots_dir).unwrap();
        std::fs::write(&config_path, b"w1c-analysis-config").unwrap();
        std::fs::write(&worker_path, b"test-worker").unwrap();

        let repository = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        for id in [CATALOG_ID, BANLIST_ID] {
            std::fs::copy(
                repository.join("data/snapshots").join(format!("{id}.json")),
                snapshots_dir.join(format!("{id}.json")),
            )
            .unwrap();
        }

        let executable_path = std::env::current_exe().unwrap().canonicalize().unwrap();
        let engine = ProcessEngineConfig {
            worker_path: worker_path.clone(),
            ..ProcessEngineConfig::default()
        };
        let runtime = RuntimeIdentity {
            executable_sha256: file_hash(&executable_path).unwrap(),
            executable_path,
            worker_sha256: file_hash(&worker_path).unwrap(),
            config_path: config_path.canonicalize().unwrap(),
            config_sha256: file_hash(&config_path).unwrap(),
            snapshots_dir: snapshots_dir.canonicalize().unwrap(),
            engine,
        };
        (
            W1cAdmission {
                expected: fixed_request().unwrap(),
                runtime: Some(runtime),
            },
            config_path,
            worker_path,
            snapshots_dir,
        )
    }

    fn command() -> AnalysisOperationCommand {
        let expected = fixed_request().unwrap();
        AnalysisOperationCommand {
            draft_id: "a".repeat(32),
            draft_revision: "b".repeat(64),
            opening_hand: expected.opening_hand,
            seed: expected.seed,
            rules: expected.rules,
            catalog_id: expected.catalog_id,
            banlist_id: expected.banlist_id,
            as_of: expected.as_of,
            search: expected.search,
        }
    }

    #[test]
    fn pins_rabbit_request_and_ydk_fixture_content() {
        let profile = W1cAdmission::fixture_policy();
        assert_eq!(profile.expected.deck.main.len(), 40);
        assert_eq!(profile.expected.deck.extra.len(), 3);
        assert!(profile.expected.deck.side.is_empty());
        assert_eq!(profile.expected.catalog_id.as_deref(), Some(CATALOG_ID));
        assert_eq!(profile.expected.banlist_id, BANLIST_ID);
        assert!(profile.matches_request(&profile.expected));
        let mut changed = fixed_request().unwrap();
        changed.deck.main[0] = CardId(1);
        assert!(!profile.matches_request(&changed));
        let mut changed = fixed_request().unwrap();
        changed.deck.side.push(CardId(1));
        assert!(!profile.matches_request(&changed));
    }

    #[test]
    fn command_admission_requires_fixed_hand_snapshots_date_and_budget() {
        let profile = W1cAdmission::fixture_policy();
        let valid = command();
        assert!(profile.matches_command(&valid));

        let mut changed = command();
        changed.catalog_id = None;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.banlist_id = "latest-ocg".into();
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.seed += 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.opening_hand[0] = CardId(1);
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.search.node_budget -= 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.search.top_k -= 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.search.beam_width -= 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.search.max_depth -= 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.search.time_limit_ms -= 1;
        assert!(!profile.matches_command(&changed));
        let mut changed = command();
        changed.as_of = "2026-10-08".into();
        assert!(!profile.matches_command(&changed));
    }

    #[test]
    fn package_recheck_detects_config_worker_and_snapshot_drift() {
        let root = TempRoot::new();
        let (profile, config_path, worker_path, snapshots_dir) = package_fixture(root.path());

        assert_eq!(profile.verify_package_files(), Ok(()));
        std::fs::write(&config_path, b"changed-config").unwrap();
        assert_eq!(
            profile.verify_package_files(),
            Err("analysis_package_mismatch")
        );
        std::fs::write(&config_path, b"w1c-analysis-config").unwrap();
        std::fs::write(&worker_path, b"changed-worker").unwrap();
        assert_eq!(
            profile.verify_package_files(),
            Err("analysis_package_mismatch")
        );
        std::fs::write(&worker_path, b"test-worker").unwrap();
        std::fs::write(
            snapshots_dir.join(format!("{CATALOG_ID}.json")),
            b"changed-catalog",
        )
        .unwrap();
        assert_eq!(
            profile.verify_package_files(),
            Err("analysis_snapshot_identity_mismatch")
        );
    }
}
