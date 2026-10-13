mod codec;
mod ffi;
mod process;
mod worker;
pub use codec::*;
pub use process::*;
use serde::{Deserialize, Serialize};
use sha2::Digest;
use std::{collections::BTreeMap, path::PathBuf};
pub use worker::{probe_request, runtime_request};
pub use worker::{run_worker, worker_main};
use ygo_domain::{CardId, Deck};
pub const PROTOCOL_VERSION: u16 = 2;
pub const CORE_COMMIT: &str = "38d04c9feb1a26617407091380634c87262fe3f8";
pub const INITIALIZER_VERSION: &str = "fixed-hand-shuffle-v1";
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ProcessEngineConfig {
    pub worker_path: PathBuf,
    pub ocgcore_path: PathBuf,
    pub catalog_path: PathBuf,
    pub scripts_path: PathBuf,
    pub script_manifest_path: PathBuf,
    pub engine_manifest_path: PathBuf,
    pub timeout_ms: u64,
}
impl Default for ProcessEngineConfig {
    fn default() -> Self {
        Self {
            worker_path: "target/debug/ygo-engine-worker.exe".into(),
            ocgcore_path: "data/runtime/engine/ocgcore.dll".into(),
            catalog_path: "data/runtime/cards.cdb".into(),
            scripts_path: "data/runtime/script".into(),
            script_manifest_path: "data/runtime/scripts.json".into(),
            engine_manifest_path: "data/runtime/engine/manifest.json".into(),
            timeout_ms: 30000,
        }
    }
}
impl ProcessEngineConfig {
    pub fn new(worker_path: PathBuf) -> Self {
        Self {
            worker_path,
            ..Default::default()
        }
    }
    pub fn from_toml(s: &str) -> Result<Self, toml::de::Error> {
        toml::from_str(s)
    }
    pub fn to_toml(&self) -> Result<String, toml::ser::Error> {
        toml::to_string_pretty(self)
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct RuntimeVersions {
    pub rules: String,
    pub catalog: String,
    pub banlist: String,
    pub engine_sha256: String,
    pub cdb_sha256: String,
    pub scripts_sha256: String,
    pub core_commit: String,
    #[serde(default)]
    pub initializer: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RunDuelRequest {
    pub protocol_version: u16,
    pub engine: ProcessEngineConfig,
    pub deck: Deck,
    pub opening_hand: Vec<CardId>,
    pub seed: u64,
    pub decisions: Vec<Decision>,
    pub versions: RuntimeVersions,
    #[serde(default)]
    pub probe_only: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Decision {
    pub prompt_id: u64,
    pub player: u8,
    pub choice: Choice,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Choice {
    Command { command: u8, index: u32 },
    Cards { indices: Vec<u32> },
    Toggle { index: u32 },
    Finish,
    YesNo { yes: bool },
    Option { index: u32 },
    Place { zones: Vec<Zone> },
    Position { position: u32 },
    Chain { index: Option<u32> },
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
pub struct Zone {
    pub player: u8,
    pub location: u8,
    pub sequence: u8,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Action {
    pub choice: Choice,
    pub label: String,
    pub card_ids: Vec<u32>,
    pub bytes: Vec<u8>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct Prompt {
    pub id: u64,
    pub player: u8,
    pub opcode: u8,
    pub actions: Vec<Action>,
}
impl Prompt {
    pub fn encode(&self, choice: &Choice) -> Result<Vec<u8>, String> {
        self.actions
            .iter()
            .find(|a| &a.choice == choice)
            .map(|a| a.bytes.clone())
            .ok_or_else(|| "choice not permitted by prompt".into())
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct CoreEventFrame {
    pub sequence: u64,
    pub opcode: u8,
    pub raw: Vec<u8>,
    pub supported: bool,
    pub fields: serde_json::Value,
}
#[derive(Clone, Debug, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct StateCard {
    pub code: u32,
    pub player: u8,
    pub location: u8,
    pub sequence: u32,
    pub position: u32,
    pub type_flags: u32,
    pub attack: i32,
    pub defense: i32,
    pub overlay: Vec<u32>,
}
#[derive(Clone, Debug, Serialize, Deserialize, Default, PartialEq, Eq)]
pub struct Checkpoint {
    pub turn: u32,
    pub turn_player: u8,
    pub phase: u16,
    pub lp: [u32; 2],
    pub cards: Vec<StateCard>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum DuelStatus {
    EngineVerified,
    DecisionRequired,
    Partial,
    Failed,
    ProbePassed,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkerError {
    pub code: String,
    pub stage: String,
    pub message: String,
}
impl WorkerError {
    pub fn new(code: &str, stage: &str, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            stage: stage.into(),
            message: message.into(),
        }
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DuelResult {
    pub protocol_version: u16,
    pub status: DuelStatus,
    pub events: Vec<CoreEventFrame>,
    pub prompt: Option<Prompt>,
    pub checkpoint: Checkpoint,
    pub error: Option<WorkerError>,
    pub versions: RuntimeVersions,
    pub loaded_scripts: BTreeMap<String, String>,
    pub steps: Vec<Action>,
    /// Includes deterministically completed prompts with a single legal action.
    #[serde(default)]
    pub resolved_decisions: Vec<Decision>,
    pub coverage_gaps: Vec<String>,
    #[serde(default)]
    pub peak_working_set_bytes: Option<u64>,
}
impl DuelResult {
    pub fn failure(error: WorkerError) -> Self {
        Self {
            protocol_version: 2,
            status: DuelStatus::Failed,
            events: vec![],
            prompt: None,
            checkpoint: Checkpoint::default(),
            error: Some(error),
            versions: RuntimeVersions::default(),
            loaded_scripts: BTreeMap::new(),
            steps: vec![],
            resolved_decisions: vec![],
            coverage_gaps: vec![],
            peak_working_set_bytes: None,
        }
    }
}
