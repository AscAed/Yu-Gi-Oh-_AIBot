use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path, PathBuf},
};
use ygo_domain::Catalog;
use ygo_engine_adapter::{
    decode_frame, parse_prompt, DuelResult, DuelStatus, RunDuelRequest, StateCard,
};
use ygo_goal::{Goal, QueryWitness};
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::{actual_state, propose_partial, ForecastPlan, SearchLimits};
use ygo_storage::SnapshotStore;

pub const SCOPE_LIMIT: usize = 64;
pub const WORKER_TIMEOUT_MS: u64 = 30_000;
pub const MAX_WINDOW_SECONDS: u64 = 7_200;
pub const MAX_HANDSHAKE_SECONDS: u64 = 600;

const EXPECTED_ASSETS_CONFIG: &str =
    "25ac37254b4f04336320f621d8f010e4a7cbfa90026407b1a376718e15ea05ad";
const EXPECTED_SOURCE_CONFIG: &str =
    "d458804dce80c01fc27f5863c0b0ec821624627a61c0fd982dded04f41bc6aff";
const EXPECTED_RULES_FIXTURE: &str =
    "db79e2f51a7c724bc3c72a78e96e0c7f6f544ceb59ffbd61a4a6ef9084ec5a87";
const EXPECTED_TRACE_FIXTURE: &str =
    "cc98145d68dd560863c40b4ac218220ebb0ee4e5069c26e91a572beee1d3032d";
const EXPECTED_FROZEN_MANIFEST: &str =
    "2131d85669dc307a2cb0a82096b6460acba3ecbd63eca3852bf0158f450d1a2c";
const EXPECTED_CDB: &str = "3530f406ba92b0f8d5699aa107e95158a1f1b4816f8f5ca2dd82c490301ef632";
const EXPECTED_CORE: &str = "446f26df7a2fb35d94374d74f5f5a5ef200d5454322d372b325e46b4e083d7a9";
const EXPECTED_ENGINE_MANIFEST: &str =
    "2028d6b7d5bf6878c11107760e73f33cf8dcfcf977d312c86ff98640c736e457";
const EXPECTED_SCRIPT_MANIFEST: &str =
    "26c44946c7aba56900ededc5358e163fce71d5b99182f0d0fa910739bc3d9c94";
const EXPECTED_CATALOG: &str =
    "catalog-de71e6b4683795a9cb83c44ba85bf1cc43d635ce8da032fff9f8b055b60e31b9";
const EXPECTED_BANLIST: &str =
    "banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783";
const EXPECTED_ASSET_GROUP: &str =
    "asset-group-228cca96b5cf16a5e8d8f397cb30db073b483e75ddb0536d7d5f6f28783af340";
const EXPECTED_SOURCE_ID: &str =
    "tournament-source-d458804dce80c01fc27f5863c0b0ec821624627a61c0fd982dded04f41bc6aff";
const EXPECTED_ROUTE: [&str; 2] = [
    "78449284:two_dark_level_three",
    "25538345:normal_summon_and_set",
];
const FIXED_GOAL: &str = r#"{"version":1,"expr":{"op":"all","args":[{"op":"count","filter":{"codes":[78449284],"locations":[4]},"min":1},{"op":"count","filter":{"codes":[25538345],"locations":[4]},"min":1}]}}"#;

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct AssetIdentity {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct InputIdentity {
    pub assets: BTreeMap<String, String>,
    pub asset_tree_sha256: String,
    pub catalog_id: String,
    pub banlist_id: String,
    pub asset_group_id: String,
    pub source_id: String,
    pub request_sha256: String,
    pub start_observation_sha256: String,
    pub queries_sha256: String,
    pub plan_sha256: String,
    pub plan_id: String,
    pub limits_sha256: String,
    pub goal_sha256: String,
}

pub struct Prepared {
    pub root: PathBuf,
    pub output_root: PathBuf,
    pub run_id: String,
    pub run_dir: PathBuf,
    pub request: RunDuelRequest,
    pub expected_result: DuelResult,
    pub queries: Vec<QueryWitness>,
    pub catalog: Catalog,
    pub pack: FirstTurnKnowledge,
    pub goal: Goal,
    pub plan: ForecastPlan,
    pub expected_route: Vec<String>,
    pub worker_path: PathBuf,
    pub resume_journal_path: PathBuf,
    pub replay_journal_path: PathBuf,
    pub trace_sha256: String,
    pub core_sha256: String,
    pub identity: InputIdentity,
    pub asset_identities: Vec<AssetIdentity>,
}

impl Prepared {
    pub fn summary(&self) -> Value {
        json!({
            "run_id": self.run_id,
            "output_directory": self.run_dir,
            "route": self.expected_route,
            "scope_limit_each": SCOPE_LIMIT,
            "aggregate_call_limit": 128,
            "worker_timeout_ms": WORKER_TIMEOUT_MS,
            "window_seconds": MAX_WINDOW_SECONDS,
            "identity": self.identity,
            "worker_path": self.worker_path,
            "worker_exists": self.worker_path.is_file(),
            "worker_processes_started": 0,
            "scope_created": false,
            "native_calls": 0,
        })
    }
}

pub fn validate_initial_result(prepared: &Prepared, result: &DuelResult) -> Result<(), String> {
    if result.protocol_version != prepared.request.protocol_version
        || result.status != DuelStatus::DecisionRequired
        || result.error.is_some()
        || result.prompt.as_ref().map(|prompt| prompt.id) != Some(49)
        || result.events.len() != 49
        || result.events.last().map(|event| event.sequence) != Some(49)
        || serde_json::to_value(&result.versions).map_err(|error| error.to_string())?
            != serde_json::to_value(&prepared.request.versions)
                .map_err(|error| error.to_string())?
    {
        return Err("native initial result did not stop at the fixed event-49 prompt".into());
    }
    let expected = prepared
        .queries
        .iter()
        .find(|query| query.event == 49)
        .ok_or("fixed event-49 query witness missing")?;
    let fixture_capture = QueryWitness::capture(&prepared.expected_result)?;
    if serde_json::to_value(&fixture_capture).map_err(|error| error.to_string())?
        != serde_json::to_value(expected).map_err(|error| error.to_string())?
    {
        return Err("prepared event-49 fixture result and witness differ".into());
    }
    let captured = QueryWitness::capture(result)?;
    if serde_json::to_value(&captured).map_err(|error| error.to_string())?
        != serde_json::to_value(&fixture_capture).map_err(|error| error.to_string())?
    {
        return Err(
            "native event-49 prompt, raw prefix, decisions, or public observation differs".into(),
        );
    }
    Ok(())
}

pub fn default_output_root(repo_root: &Path) -> PathBuf {
    repo_root.join("data/runtime/p4-r1b3")
}

pub fn validate_digest(label: &str, actual: &str, expected: &str) -> Result<(), String> {
    if actual == expected {
        Ok(())
    } else {
        Err(format!(
            "{label} SHA-256 mismatch: expected {expected}, found {actual}"
        ))
    }
}

pub fn validate_route(plan: &ForecastPlan) -> Result<(), String> {
    let found = plan
        .steps
        .iter()
        .map(|step| step.rule_id.as_str())
        .collect::<Vec<_>>();
    if found == EXPECTED_ROUTE {
        Ok(())
    } else {
        Err(format!(
            "forecast route differs: expected {:?}, found {:?}",
            EXPECTED_ROUTE, found
        ))
    }
}

pub fn prepare(repo_root: &Path, output_root: &Path) -> Result<Prepared, String> {
    let run_id = unique_run_id()?;
    prepare_for_run(repo_root, output_root, &run_id)
}

pub fn prepare_for_run(
    repo_root: &Path,
    output_root: &Path,
    run_id: &str,
) -> Result<Prepared, String> {
    let root = repo_root.canonicalize().map_err(|e| e.to_string())?;
    if run_id.is_empty()
        || run_id.len() > 128
        || !run_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-')
    {
        return Err("invalid run ID".into());
    }
    let output_root = if output_root.is_absolute() {
        output_root.to_path_buf()
    } else {
        root.join(output_root)
    };
    reject_existing_symlink(&output_root)?;

    let mut assets = BTreeMap::new();
    let mut verified_fixtures = BTreeMap::new();
    for (name, relative, expected) in [
        (
            "assets_config",
            "configs/tournament-2026.assets.json",
            EXPECTED_ASSETS_CONFIG,
        ),
        (
            "source_config",
            "configs/tournament-2026.source.json",
            EXPECTED_SOURCE_CONFIG,
        ),
        (
            "rules_fixture",
            "tests/fixtures/tournament-2026.rules-resource.contract.json",
            EXPECTED_RULES_FIXTURE,
        ),
        (
            "trace_fixture",
            "tests/fixtures/tournament-2026.trace-resource.json",
            EXPECTED_TRACE_FIXTURE,
        ),
        (
            "frozen_manifest",
            "data/runtime/tournament-2026/frozen/manifest.json",
            EXPECTED_FROZEN_MANIFEST,
        ),
    ] {
        let path = root.join(relative);
        let bytes = read_checked(&root, &path)?;
        let actual = digest(&bytes);
        validate_digest(name, &actual, expected)?;
        assets.insert(name.to_owned(), actual);
        if matches!(name, "rules_fixture" | "trace_fixture") {
            verified_fixtures.insert(name.to_owned(), bytes);
        }
    }

    let rules_bytes = verified_fixtures
        .get("rules_fixture")
        .ok_or("verified rules fixture missing")?;
    let trace_bytes = verified_fixtures
        .get("trace_fixture")
        .ok_or("verified trace fixture missing")?;
    let rules: Value = serde_json::from_slice(rules_bytes).map_err(|e| e.to_string())?;
    let trace: Value = serde_json::from_slice(trace_bytes).map_err(|e| e.to_string())?;
    let case = rules
        .get("cases")
        .and_then(Value::as_array)
        .and_then(|cases| cases.first())
        .ok_or("rules fixture has no cases[0]")?;
    if case.get("case_id").and_then(Value::as_str) != Some("soleret-empty-positive") {
        return Err("fixed tournament case identity differs".into());
    }

    let mut request: RunDuelRequest = serde_json::from_value(
        case.get("runtime_request")
            .cloned()
            .ok_or("fixed case runtime_request missing")?,
    )
    .map_err(|e| e.to_string())?;
    request.validate_protocol()?;
    if request.protocol_version != 6
        || request.seed != 1
        || request.opening_hand
            != [83566725, 46072770, 25538345, 44088353, 99745551]
                .into_iter()
                .map(ygo_domain::CardId)
                .collect::<Vec<_>>()
        || request.deck.main.len() != 41
        || request.deck.extra.len() != 15
        || request.versions.catalog != EXPECTED_CATALOG
        || request.versions.banlist != EXPECTED_BANLIST
        || request
            .first_turn
            .as_ref()
            .map(|cfg| cfg.asset_group_id.as_str())
            != Some(EXPECTED_ASSET_GROUP)
        || request
            .first_turn
            .as_ref()
            .map(|cfg| cfg.source_id.as_str())
            != Some(EXPECTED_SOURCE_ID)
        || request.engine.timeout_ms != WORKER_TIMEOUT_MS
    {
        return Err("fixed case request, versions or asset context differs".into());
    }

    let worker_path = worker_path_for_current_executable(&root)?;
    request.engine.worker_path = worker_path.clone();
    let engine_paths = [
        ("cdb", request.engine.catalog_path.as_path(), EXPECTED_CDB),
        ("core", request.engine.ocgcore_path.as_path(), EXPECTED_CORE),
        (
            "script_manifest",
            request.engine.script_manifest_path.as_path(),
            EXPECTED_SCRIPT_MANIFEST,
        ),
        (
            "engine_manifest",
            request.engine.engine_manifest_path.as_path(),
            EXPECTED_ENGINE_MANIFEST,
        ),
    ];
    for (name, path, expected) in engine_paths {
        let full = resolve_under_root(&root, path)?;
        let actual = digest(&read_checked(&root, &full)?);
        validate_digest(name, &actual, expected)?;
        assets.insert(name.to_owned(), actual);
    }
    let scripts_path = resolve_under_root(&root, &request.engine.scripts_path)?;
    let (tree_sha256, tree_files) = directory_identity(&root, &scripts_path)?;
    if tree_files == 0 {
        return Err("frozen script directory is empty".into());
    }
    assets.insert("script_tree".into(), tree_sha256.clone());

    let store_root = root.join("data/runtime/tournament-2026/snapshots");
    let store = SnapshotStore::new(store_root);
    let catalog_snapshot = store.catalog(&request.versions.catalog)?;
    let banlist_snapshot = store.banlist(&request.versions.banlist)?;
    if catalog_snapshot.id != EXPECTED_CATALOG || banlist_snapshot.id != EXPECTED_BANLIST {
        return Err("snapshot IDs differ from the frozen request".into());
    }
    let catalog = catalog_snapshot.data;
    let pack = FirstTurnKnowledge::builtin()?;
    if pack.id() != request.first_turn.as_ref().unwrap().knowledge_id {
        return Err("built-in knowledge identity differs from the frozen request".into());
    }

    let mut decisions: Vec<ygo_engine_adapter::Decision> =
        serde_json::from_value(trace["result"]["resolved_decisions"].clone())
            .map_err(|e| e.to_string())?;
    decisions.retain(|decision| decision.prompt_id < 49);
    if decisions.len() != 16 {
        return Err(format!(
            "event-49 fixed prefix must have 16 decisions, found {}",
            decisions.len()
        ));
    }
    request.decisions.clear();
    request.decisions = decisions;

    let expected_result = result_at(&trace, &request, 49)?;
    let queries = [8, 17, 49]
        .into_iter()
        .map(|event| {
            result_at(&trace, &request, event).and_then(|result| QueryWitness::capture(&result))
        })
        .collect::<Result<Vec<_>, _>>()?;
    if serde_json::to_value(queries.last()).map_err(|e| e.to_string())?
        != serde_json::to_value(QueryWitness::capture(&expected_result)?)
            .map_err(|e| e.to_string())?
    {
        return Err("event-49 query witness reconstruction differs".into());
    }

    let observed = actual_state(&expected_result, &queries, &catalog, &pack)?;
    let goal: Goal = serde_json::from_str(FIXED_GOAL).map_err(|e| e.to_string())?;
    let limits = SearchLimits::default();
    let plans = propose_partial(&observed.state, &catalog, &pack, &goal, &limits)?;
    let plan = plans
        .plans
        .iter()
        .find(|candidate| validate_route(candidate).is_ok())
        .cloned()
        .ok_or_else(|| {
            let routes = plans
                .plans
                .iter()
                .map(|candidate| {
                    candidate
                        .steps
                        .iter()
                        .map(|step| step.rule_id.as_str())
                        .collect::<Vec<_>>()
                })
                .collect::<Vec<_>>();
            format!("public propose_partial did not produce the fixed route: {routes:?}")
        })?;
    validate_route(&plan)?;

    let run_id = run_id.to_owned();
    let run_dir = output_root.join(&run_id);
    let resume_journal_path = run_dir.join("resume/calls.jsonl");
    let replay_journal_path = run_dir.join("replay/calls.jsonl");
    let goal_sha256 = hash_json(&goal)?;
    let limits_sha256 = hash_json(&limits)?;
    let request_sha256 = hash_json(&request)?;
    let start_observation_sha256 = hash_json(&observed.state)?;
    let queries_sha256 = hash_json(&queries)?;
    let plan_sha256 = hash_json(&plan)?;
    let asset_tree_sha256 = hash_json(&assets)?;
    let identity = InputIdentity {
        assets,
        asset_tree_sha256,
        catalog_id: catalog_snapshot.id,
        banlist_id: banlist_snapshot.id,
        asset_group_id: EXPECTED_ASSET_GROUP.into(),
        source_id: EXPECTED_SOURCE_ID.into(),
        request_sha256,
        start_observation_sha256,
        queries_sha256,
        plan_sha256,
        plan_id: plan.id.clone(),
        limits_sha256,
        goal_sha256,
    };
    let asset_identities = identity
        .assets
        .iter()
        .map(|(path, sha256)| AssetIdentity {
            path: path.clone(),
            sha256: sha256.clone(),
        })
        .collect();

    Ok(Prepared {
        root,
        output_root,
        run_id,
        run_dir,
        request,
        expected_result,
        queries,
        catalog,
        pack,
        goal,
        plan,
        expected_route: EXPECTED_ROUTE.iter().map(|s| (*s).to_owned()).collect(),
        worker_path,
        resume_journal_path,
        replay_journal_path,
        trace_sha256: EXPECTED_TRACE_FIXTURE.into(),
        core_sha256: EXPECTED_CORE.into(),
        identity,
        asset_identities,
    })
}

pub fn resolve_under_root(root: &Path, path: &Path) -> Result<PathBuf, String> {
    let full = if path.is_absolute() {
        path.to_path_buf()
    } else {
        root.join(path)
    };
    let canonical_root = root.canonicalize().map_err(|e| e.to_string())?;
    let normalized = normalize_existing_prefix(&full)?;
    if !normalized.starts_with(&canonical_root) {
        return Err(format!("path escapes repository: {}", full.display()));
    }
    Ok(full)
}

pub fn worker_path_for_current_executable(root: &Path) -> Result<PathBuf, String> {
    let executable = std::env::current_exe().map_err(|error| error.to_string())?;
    let cargo_debug_dir = executable
        .parent()
        .and_then(Path::parent)
        .ok_or("current executable is not under a Cargo profile subdirectory")?;
    let worker = cargo_debug_dir.join(format!("ygo-engine-worker{}", std::env::consts::EXE_SUFFIX));
    let worker = resolve_under_root(root, &worker)?;
    reject_existing_symlink(&worker)?;
    Ok(worker)
}

pub fn read_checked(root: &Path, path: &Path) -> Result<Vec<u8>, String> {
    let resolved = resolve_under_root(root, path)?;
    reject_path_symlinks(root, &resolved)?;
    fs::read(&resolved).map_err(|e| format!("{}: {e}", resolved.display()))
}

pub fn reject_existing_symlink(path: &Path) -> Result<(), String> {
    let mut current = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => {
                current.push(prefix.as_os_str());
                continue;
            }
            Component::RootDir => {
                current.push(component.as_os_str());
                continue;
            }
            Component::CurDir => continue,
            Component::ParentDir => current.push(".."),
            Component::Normal(part) => current.push(part),
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "symbolic link is not allowed: {}",
                    current.display()
                ))
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(error) => return Err(format!("{}: {error}", current.display())),
        }
    }
    Ok(())
}

pub fn directory_identity(root: &Path, directory: &Path) -> Result<(String, usize), String> {
    reject_path_symlinks(root, directory)?;
    if !directory.is_dir() {
        return Err(format!("asset directory missing: {}", directory.display()));
    }
    let mut files = Vec::new();
    collect_files(root, directory, &mut files)?;
    files.sort_by(|a, b| a.0.cmp(&b.0));
    if files.is_empty() {
        return Err(format!("asset directory empty: {}", directory.display()));
    }
    let identity = files
        .iter()
        .map(|(relative, hash)| (relative.replace('\\', "/"), hash.clone()))
        .collect::<Vec<_>>();
    Ok((hash_json(&identity)?, identity.len()))
}

pub fn sha256_file(root: &Path, path: &Path) -> Result<String, String> {
    Ok(digest(&read_checked(root, path)?))
}

pub fn hash_json<T: Serialize>(value: &T) -> Result<String, String> {
    serde_json::to_vec(value)
        .map(|bytes| digest(&bytes))
        .map_err(|e| e.to_string())
}

pub fn digest(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}

fn result_at(trace: &Value, request: &RunDuelRequest, event: usize) -> Result<DuelResult, String> {
    let frames = trace["frames"].as_array().ok_or("trace frames missing")?;
    if event == 0 || event > frames.len() {
        return Err(format!("event {event} is outside the trace"));
    }
    let decisions: Vec<ygo_engine_adapter::Decision> =
        serde_json::from_value(trace["result"]["resolved_decisions"].clone())
            .map_err(|e| e.to_string())?;
    let witness = trace["witnesses"]
        .as_array()
        .and_then(|items| {
            items
                .iter()
                .filter(|item| item["event"].as_u64() == Some(event as u64))
                .max_by_key(|item| item["event"].as_u64().unwrap_or(0))
        })
        .ok_or_else(|| format!("trace witness event {event} missing"))?;
    let mut base = trace["result"].clone();
    base["events"] = json!([]);
    let mut result: DuelResult = serde_json::from_value(base).map_err(|e| e.to_string())?;
    result.events = frames[..event]
        .iter()
        .enumerate()
        .map(|(index, frame)| {
            let raw: Vec<u8> = serde_json::from_value(frame.clone()).map_err(|e| e.to_string())?;
            decode_frame(index as u64 + 1, &raw)
        })
        .collect::<Result<Vec<_>, _>>()?;
    let raw: Vec<u8> =
        serde_json::from_value(frames[event - 1].clone()).map_err(|e| e.to_string())?;
    result.prompt = parse_prompt(event as u64, &raw)?;
    result.checkpoint =
        serde_json::from_value(witness["public"]["visible"].clone()).map_err(|e| e.to_string())?;
    if let Some(deck) = witness["public"]["own_deck_counts"].as_object() {
        for (code, count) in deck {
            let code = code.parse::<u32>().map_err(|e| e.to_string())?;
            let count = count.as_u64().ok_or("invalid own_deck_counts entry")?;
            for _ in 0..count {
                result.checkpoint.cards.push(StateCard {
                    code,
                    player: 0,
                    location: 1,
                    ..Default::default()
                });
            }
        }
    }
    for (field, location) in [("opponent_deck_count", 1), ("opponent_hand_count", 2)] {
        let count = witness["public"][field]
            .as_u64()
            .ok_or_else(|| format!("invalid {field}"))?;
        for _ in 0..count {
            result.checkpoint.cards.push(StateCard {
                player: 1,
                location,
                ..Default::default()
            });
        }
    }
    result.resolved_decisions = decisions
        .into_iter()
        .filter(|decision| decision.prompt_id < event as u64)
        .collect();
    result.status = DuelStatus::DecisionRequired;
    result.error = None;
    result.versions = request.versions.clone();
    let captured = QueryWitness::capture(&result)?;
    let expected: QueryWitness =
        serde_json::from_value(witness.clone()).map_err(|e| e.to_string())?;
    if serde_json::to_value(&captured).map_err(|e| e.to_string())?
        != serde_json::to_value(&expected).map_err(|e| e.to_string())?
    {
        return Err(format!(
            "event-{event} trace witness differs from reconstructed result"
        ));
    }
    Ok(result)
}

fn unique_run_id() -> Result<String, String> {
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_nanos();
    Ok(format!("p4-r1b3-{nanos}-{}", std::process::id()))
}

fn normalize_existing_prefix(path: &Path) -> Result<PathBuf, String> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(path)
    };
    let mut missing = Vec::new();
    let mut existing = absolute.as_path();
    while !existing.exists() {
        let name = existing
            .file_name()
            .ok_or_else(|| format!("path has no existing ancestor: {}", path.display()))?;
        missing.push(name.to_os_string());
        existing = existing
            .parent()
            .ok_or_else(|| format!("path has no parent: {}", path.display()))?;
    }
    let mut result = existing.canonicalize().map_err(|e| e.to_string())?;
    for part in missing.iter().rev() {
        result.push(part);
    }
    Ok(result)
}

fn reject_path_symlinks(root: &Path, path: &Path) -> Result<(), String> {
    let canonical_root = root.canonicalize().map_err(|e| e.to_string())?;
    let absolute_root = if root.is_absolute() {
        root.to_path_buf()
    } else {
        std::env::current_dir()
            .map_err(|e| e.to_string())?
            .join(root)
    };
    let absolute_path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        absolute_root.join(path)
    };
    let relative = absolute_path
        .strip_prefix(&absolute_root)
        .or_else(|_| absolute_path.strip_prefix(&canonical_root))
        .map_err(|_| format!("path escapes repository: {}", path.display()))?;
    let mut current = canonical_root;
    for component in relative.components() {
        match component {
            Component::Normal(part) => current.push(part),
            Component::CurDir => continue,
            Component::ParentDir | Component::Prefix(_) | Component::RootDir => {
                return Err(format!("path escapes repository: {}", path.display()));
            }
        }
        match fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() => {
                return Err(format!(
                    "symbolic link is not allowed: {}",
                    current.display()
                ))
            }
            Ok(_) => {}
            Err(error) => return Err(format!("{}: {error}", current.display())),
        }
    }
    Ok(())
}

fn collect_files(
    root: &Path,
    directory: &Path,
    output: &mut Vec<(String, String)>,
) -> Result<(), String> {
    reject_path_symlinks(root, directory)?;
    let entries = fs::read_dir(directory).map_err(|e| e.to_string())?;
    for entry in entries {
        let entry = entry.map_err(|e| e.to_string())?;
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path).map_err(|e| e.to_string())?;
        if metadata.file_type().is_symlink() {
            return Err(format!("symbolic link is not allowed: {}", path.display()));
        }
        if metadata.is_dir() {
            collect_files(root, &path, output)?;
        } else if metadata.is_file() {
            let relative = path
                .strip_prefix(root)
                .map_err(|e| e.to_string())?
                .to_string_lossy()
                .into_owned();
            output.push((
                relative,
                digest(&fs::read(&path).map_err(|e| e.to_string())?),
            ));
        } else {
            return Err(format!("unexpected asset entry: {}", path.display()));
        }
    }
    Ok(())
}

#[cfg(test)]
mod path_security_tests {
    use super::*;

    #[test]
    #[cfg_attr(
        windows,
        ignore = "requires Windows permission to create directory symlinks"
    )]
    fn read_checked_rejects_in_repository_symlink_components() {
        let root = std::env::temp_dir().join(format!(
            "p4-r1b3-symlink-check-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let target = root.join("target");
        let link = root.join("link");
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("asset.bin"), b"asset").unwrap();

        #[cfg(windows)]
        let link_result = std::os::windows::fs::symlink_dir(&target, &link);
        #[cfg(unix)]
        let link_result = std::os::unix::fs::symlink(&target, &link);

        link_result.unwrap_or_else(|error| panic!("failed to create symlink fixture: {error}"));

        let result = read_checked(&root, &link.join("asset.bin"));
        assert!(result.is_err(), "symlink component was accepted");
        fs::remove_dir_all(root).unwrap();
    }
}
