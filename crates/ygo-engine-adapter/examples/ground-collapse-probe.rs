//! One frozen Ground Collapse stage per invocation; all charged work passes
//! through its dedicated five-request journal.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
    time::Instant,
};
use ygo_engine_adapter::*;

fn charged_call_delta(before: usize, after: usize) -> Result<usize, &'static str> {
    let charged = after
        .checked_sub(before)
        .ok_or("ledger consumed count moved backwards")?;
    if charged > 1 {
        return Err("a single stage charged more than one call");
    }
    Ok(charged)
}

fn require_charged_stage(
    result: Result<DuelResult, WorkerError>,
    native_calls: usize,
) -> Result<Result<DuelResult, WorkerError>, String> {
    match native_calls {
        0 => Err(result
            .err()
            .map(|error| error.message)
            .unwrap_or_else(|| "stage returned without a charged ledger call".into())),
        1 => Ok(result),
        _ => Err("a single stage charged more than one call".into()),
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Input {
    context: String,
    ledger: PathBuf,
    output: PathBuf,
    stage: u8,
    request: RunDuelRequest,
    expected_identity: Value,
    started_at: u64,
}

fn research_root() -> Result<PathBuf, std::io::Error> {
    Ok(std::env::current_dir()?
        .join("data/runtime/p1-ground-collapse-opcode24-native-2026-11-03/research"))
}

fn safe(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let root = research_root()?;
    if !path.is_absolute()
        || path
            .components()
            .any(|component| matches!(component, std::path::Component::ParentDir))
        || path.parent() != Some(root.as_path())
    {
        return Err("dedicated Ground Collapse research path required".into());
    }
    for ancestor in path.ancestors() {
        if let Ok(metadata) = fs::symlink_metadata(ancestor) {
            if metadata.file_type().is_symlink() {
                return Err("symlink evidence path".into());
            }
            #[cfg(windows)]
            {
                use std::os::windows::fs::MetadataExt;
                if metadata.file_attributes() & 0x400 != 0 {
                    return Err("reparse evidence path".into());
                }
            }
        }
    }
    Ok(())
}

struct StrictValue(Value);
impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = StrictValue;
            fn expecting(&self, formatter: &mut std::fmt::Formatter) -> std::fmt::Result {
                formatter.write_str("JSON without duplicate keys")
            }
            fn visit_bool<E: serde::de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_i64<E: serde::de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_u64<E: serde::de::Error>(self, value: u64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_f64<E: serde::de::Error>(self, value: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(value)
                    .map(|number| StrictValue(Value::Number(number)))
                    .ok_or_else(|| E::custom("invalid number"))
            }
            fn visit_str<E: serde::de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_string<E: serde::de::Error>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(value)))
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut access: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(StrictValue(value)) = access.next_element::<StrictValue>()? {
                    values.push(value);
                }
                Ok(StrictValue(Value::Array(values)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut access: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = serde_json::Map::new();
                while let Some(key) = access.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate JSON key"));
                    }
                    let StrictValue(value) = access.next_value::<StrictValue>()?;
                    values.insert(key, value);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}

fn publish(path: &Path, value: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let mut file = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    file.write_all(&serde_json::to_vec_pretty(value)?)?;
    file.sync_all()?;
    Ok(())
}

fn identity(request: &RunDuelRequest) -> Result<Value, String> {
    let value = capture_engine_identity(&request.engine)?;
    if value["consistent"] != true {
        return Err("inconsistent assets".into());
    }
    let versions = serde_json::to_value(&request.versions).map_err(|error| error.to_string())?;
    for (role, key) in [
        ("dll", "engine_sha256"),
        ("cdb", "cdb_sha256"),
        ("script_manifest", "scripts_sha256"),
    ] {
        if value["roles"][role]["sha256"] != versions[key] {
            return Err("request asset mismatch".into());
        }
    }
    Ok(value)
}

fn output_matches(path: &Path, receipt: &Value) -> Result<(), Box<dyn std::error::Error>> {
    if path.exists() {
        let actual: Value = serde_json::from_slice(&fs::read(path)?)?;
        if actual != *receipt {
            return Err("published receipt differs from immutable evidence".into());
        }
    } else {
        publish(path, receipt)?;
    }
    Ok(())
}

fn verify_artifact(
    manifest: &Value,
    role: &str,
    actual_path: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let binding = manifest
        .get("artifacts")
        .and_then(|artifacts| artifacts.get(role))
        .ok_or("scope artifact binding missing")?;
    let expected_path = PathBuf::from(
        binding
            .get("path")
            .and_then(Value::as_str)
            .ok_or("scope artifact path missing")?,
    )
    .canonicalize()?;
    let actual_path = actual_path.canonicalize()?;
    if expected_path != actual_path {
        return Err("scope artifact path changed".into());
    }
    let expected_sha = binding
        .get("sha256")
        .and_then(Value::as_str)
        .ok_or("scope artifact hash missing")?;
    if digest(&fs::read(actual_path)?) != expected_sha {
        return Err("scope artifact hash changed".into());
    }
    Ok(())
}

fn verify_manifest_context(
    manifest: &mut Value,
    expected_context: &str,
    input_context: &str,
) -> Result<(), String> {
    let context = manifest
        .get("context")
        .and_then(Value::as_str)
        .ok_or("scope manifest context missing")?;
    if context != input_context || context != expected_context {
        return Err("scope manifest context differs".into());
    }
    manifest
        .as_object_mut()
        .ok_or("scope manifest must be an object")?
        .remove("context")
        .ok_or("scope manifest context missing")?;
    let bytes = serde_json::to_vec(manifest).map_err(|error| error.to_string())?;
    if digest(&bytes) != expected_context {
        return Err("scope manifest context hash mismatch".into());
    }
    Ok(())
}

fn verify_manifest(
    input: &Input,
    raw_input: &Value,
    runner_path: &Path,
) -> Result<(), Box<dyn std::error::Error>> {
    let root = research_root()?;
    let manifest_path = root.join("manifest.json");
    safe(&manifest_path)?;
    let manifest_bytes = fs::read(&manifest_path)?;
    let StrictValue(mut manifest) = serde_json::from_slice(&manifest_bytes)?;
    verify_manifest_context(&mut manifest, &input.context, &input.context)?;
    if manifest["kind"] != "ground_collapse_probe_manifest"
        || manifest["schema_version"] != 1
        || manifest["scope"] != GROUND_COLLAPSE_PROBE_SCOPE
        || manifest["request_limit"] != GROUND_COLLAPSE_PROBE_LIMIT
        || manifest["window_seconds"] != GROUND_COLLAPSE_PROBE_WINDOW_SECONDS
        || manifest["request_timeout_ms"] != GROUND_COLLAPSE_PROBE_TIMEOUT_MS
        || manifest["scope_authorized"] != true
        || manifest["preparation_execution_ready"] != true
        || manifest["started_at"] != input.started_at
        || manifest["output_path"] != root.to_string_lossy().as_ref()
        || manifest["expected_identity"] != input.expected_identity
        || manifest["proof_ready"] != false
        || manifest["complete_action_coverage"] != false
        || manifest["global_optimality"] != false
        || manifest["native_probability_verified"] != false
    {
        return Err("scope manifest gate or fixed binding mismatch".into());
    }
    let raw_request = raw_input.get("request").ok_or("stage request missing")?;
    if input.stage == 1
        && manifest["stage1_request_sha256"] != digest(&serde_json::to_vec(raw_request)?)
    {
        return Err("stage1 request differs from authorized manifest".into());
    }
    verify_artifact(&manifest, "runner", runner_path)?;
    verify_artifact(&manifest, "worker", &input.request.engine.worker_path)?;
    let build_path = PathBuf::from(
        manifest["artifacts"]["build_record"]["path"]
            .as_str()
            .ok_or("build record path missing")?,
    );
    verify_artifact(&manifest, "build_record", &build_path)?;
    let protected = manifest
        .get("protected_files")
        .and_then(Value::as_object)
        .ok_or("protected source inputs missing")?;
    for (path, expected) in protected {
        if !Path::new(path).is_absolute() {
            return Err("protected source path must be absolute".into());
        }
        if digest(&fs::read(path)?) != expected.as_str().ok_or("protected file hash missing")? {
            return Err("protected source input changed".into());
        }
    }
    let start_path = root.join("window-start.json");
    safe(&start_path)?;
    let StrictValue(start) = serde_json::from_slice::<StrictValue>(&fs::read(start_path)?)?;
    if start["scope"] != GROUND_COLLAPSE_PROBE_SCOPE
        || start["context"] != input.context
        || start["started_at"] != input.started_at
        || start["request_limit"] != GROUND_COLLAPSE_PROBE_LIMIT
        || start["window_seconds"] != GROUND_COLLAPSE_PROBE_WINDOW_SECONDS
    {
        return Err("persisted scope start differs".into());
    }
    Ok(())
}

fn execute() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    let verify = args.len() == 5 && args[4] == "--verify-recorded";
    let stats_only = args.len() == 5 && args[4] == "--stats";
    if (args.len() != 4 && !verify && !stats_only) || args[2] != "--input-sha" {
        return Err("input --input-sha HASH [--verify-recorded|--stats] required".into());
    }
    let raw = fs::read(&args[1])?;
    if digest(&raw) != args[3] {
        return Err("input SHA mismatch".into());
    }
    safe(Path::new(&args[1]))?;
    let StrictValue(value) = serde_json::from_slice(&raw)?;
    let input: Input = serde_json::from_value(value.clone())?;
    if input.context.len() != 64
        || !input
            .context
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
    {
        return Err("scope context must be a lowercase SHA-256".into());
    }
    if !(1..=GROUND_COLLAPSE_PROBE_LIMIT as u8).contains(&input.stage) {
        return Err("stage outside Ground Collapse request limit".into());
    }
    safe(&input.ledger)?;
    safe(&input.output)?;
    let root = research_root()?;
    if input.ledger != root.join("calls.jsonl")
        || input.output != root.join(format!("stage-{}.json", input.stage))
    {
        return Err("fixed Ground Collapse ledger/output filenames required".into());
    }
    verify_manifest(&input, &value, &std::env::current_exe()?)?;
    for asset in [
        &input.request.engine.worker_path,
        &input.request.engine.ocgcore_path,
        &input.request.engine.catalog_path,
        &input.request.engine.scripts_path,
        &input.request.engine.script_manifest_path,
        &input.request.engine.engine_manifest_path,
    ] {
        let asset = if asset.is_absolute() {
            asset.clone()
        } else {
            std::env::current_dir()?.join(asset)
        };
        if input.output.starts_with(&asset)
            || asset.starts_with(&input.output)
            || input.ledger.starts_with(&asset)
            || asset.starts_with(&input.ledger)
        {
            return Err("research evidence overlaps engine assets".into());
        }
    }
    if (verify || stats_only) && !input.ledger.exists() {
        return Err("existing Ground Collapse ledger required".into());
    }
    let batch = if verify || stats_only {
        GroundCollapseProbeBatch::inspect_existing(&input.ledger, &input.context, input.started_at)
    } else {
        GroundCollapseProbeBatch::open(&input.ledger, &input.context, input.started_at)
    }
    .map_err(|error| error.message)?;
    if stats_only {
        batch.verify().map_err(|error| error.message)?;
        let stats = batch.stats().map_err(|error| error.message)?;
        println!("{}", json!({"native_calls":0,"ledger":stats}));
        return Ok(());
    }
    if let Some(saved) = batch.evidence(input.stage).map_err(|error| error.message)? {
        batch
            .verify_evidence(input.stage, &saved)
            .map_err(|error| error.message)?;
        if verify && !input.output.exists() {
            return Err("published stage receipt missing".into());
        }
        output_matches(&input.output, &saved)?;
        println!(
            "{}",
            json!({"verified_recorded":true,"native_calls":0,
            "successful":saved["successful"],"ledger":batch.stats().map_err(|error| error.message)?})
        );
        return Ok(());
    }
    if verify {
        return Err("immutable stage receipt missing".into());
    }
    if input.output.exists() {
        return Err("stage output exists without an immutable receipt".into());
    }
    batch
        .validate_request(input.stage, &input.request)
        .map_err(|error| error.message)?;
    batch.require_time().map_err(|error| error.message)?;
    let before = identity(&input.request).map_err(|error| format!("asset precheck: {error}"))?;
    if before != input.expected_identity {
        return Err("asset identity drift".into());
    }
    batch
        .save_assets_before(input.stage, &before)
        .map_err(|error| error.message)?;
    batch.require_time().map_err(|error| error.message)?;
    let consumed_before = batch.stats().map_err(|error| error.message)?.consumed;
    let started = Instant::now();
    let result = batch.run(
        ProcessEngineAdapter::new(input.request.engine.clone()),
        input.stage,
        &input.request,
    );
    let elapsed_ms = started.elapsed().as_millis();
    let ledger = batch.stats().map_err(|error| error.message)?;
    let native_calls = charged_call_delta(consumed_before, ledger.consumed)?;
    let result = require_charged_stage(result, native_calls)?;
    let after = identity(&input.request).ok();
    let assets_unchanged =
        after.as_ref() == Some(&before) && after.as_ref() == Some(&input.expected_identity);
    let validation = result
        .as_ref()
        .map_err(|error| error.message.clone())
        .and_then(|value| validate_ground_collapse_result(&input.request, value));
    let replay_matches = if input.stage > 1 {
        let previous = batch
            .evidence(input.stage - 1)
            .map_err(|error| error.message)?
            .ok_or("replay/derivation parent missing")?;
        let previous_request: RunDuelRequest = serde_json::from_value(previous["request"].clone())?;
        if serde_json::to_value(&previous_request)? == serde_json::to_value(&input.request)? {
            let parent: Result<DuelResult, WorkerError> =
                serde_json::from_value(previous["result"].clone())?;
            json!(match (&parent, &result) {
                (Ok(left), Ok(right)) => ground_collapse_replay_matches(left, right),
                _ => false,
            })
        } else {
            Value::Null
        }
    } else {
        Value::Null
    };
    let successful = validation.is_ok()
        && assets_unchanged
        && (replay_matches.is_null() || replay_matches == Value::Bool(true))
        && batch.require_time().is_ok();
    let diagnostic = if result.as_ref().is_err() {
        Some("engine_or_journal_error")
    } else if validation.is_err() {
        Some("fixed_ground_route_validation_failed")
    } else if !assets_unchanged {
        Some("asset_identity_drift")
    } else if replay_matches == Value::Bool(false) {
        Some("independent_replay_mismatch")
    } else if !successful {
        Some("scope_window_exhausted")
    } else {
        None
    };
    let receipt = json!({
        "schema_version":1,
        "kind":"ground_collapse_probe_stage",
        "scope":GROUND_COLLAPSE_PROBE_SCOPE,
        "context":input.context,
        "stage":input.stage,
        "request":input.request,
        "result":result,
        "validation":validation,
        "assets_before":before,
        "assets_after":after,
        "assets_unchanged":assets_unchanged,
        "independent_replay_matches":replay_matches,
        "successful":successful,
        "diagnostic":diagnostic,
        "elapsed_ms":elapsed_ms,
        "ledger":ledger,
        "started_at":input.started_at,
        "native_calls":native_calls,
        "runner_process_calls":1,
        "worker_process_calls":native_calls,
        "ffi_calls":null,
        "proof_ready":false,
        "complete_action_coverage":false,
        "global_optimality":false,
        "native_probability_verified":false
    });
    batch
        .save_evidence(input.stage, &receipt)
        .map_err(|error| error.message)?;
    publish(&input.output, &receipt)?;
    println!(
        "{}",
        json!({"successful":successful,"native_calls":native_calls,
        "runner_process_calls":1,"worker_process_calls":native_calls,"ffi_calls":null,
        "ledger":receipt["ledger"]})
    );
    if !successful {
        std::process::exit(1);
    }
    Ok(())
}

fn main() {
    if let Err(error) = execute() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn charged_call_delta_matches_the_ledger_and_rejects_invalid_counts() {
        assert_eq!(charged_call_delta(0, 0), Ok(0));
        assert_eq!(charged_call_delta(4, 5), Ok(1));
        assert_eq!(
            charged_call_delta(4, 3),
            Err("ledger consumed count moved backwards")
        );
        assert_eq!(
            charged_call_delta(4, 6),
            Err("a single stage charged more than one call")
        );
    }

    #[test]
    fn uncharged_stage_errors_cannot_be_persisted_as_receipts() {
        let error = WorkerError::new("preflight", "ledger", "no call was charged");
        assert_eq!(
            require_charged_stage(Err(error), 0).unwrap_err(),
            "no call was charged"
        );

        let error = WorkerError::new("worker", "process", "charged worker failed");
        assert!(require_charged_stage(Err(error), 1).unwrap().is_err());
    }

    #[test]
    fn manifest_context_hash_covers_all_fields_except_context() {
        let mut manifest = json!({
            "kind": "ground_collapse_probe_manifest",
            "schema_version": 1,
            "scope_authorized": true
        });
        let expected_context = digest(&serde_json::to_vec(&manifest).unwrap());
        manifest["context"] = json!(expected_context);

        verify_manifest_context(&mut manifest, &expected_context, &expected_context).unwrap();
        assert_eq!(
            manifest,
            json!({
                "kind": "ground_collapse_probe_manifest",
                "schema_version": 1,
                "scope_authorized": true
            })
        );

        let mut changed = json!({
            "kind": "ground_collapse_probe_manifest",
            "schema_version": 1,
            "scope_authorized": true,
            "context": expected_context
        });
        changed["scope_authorized"] = json!(false);
        assert!(
            verify_manifest_context(&mut changed, &expected_context, &expected_context).is_err()
        );
    }

    #[test]
    fn scope_is_isolated_and_request_budget_is_five() {
        assert_eq!(
            GROUND_COLLAPSE_PROBE_SCOPE,
            "p1-ground-collapse-opcode24-reachability-v1"
        );
        assert_eq!(GROUND_COLLAPSE_PROBE_LIMIT, 5);
        assert_eq!(GROUND_COLLAPSE_PROBE_WINDOW_SECONDS, 1800);
        assert_eq!(GROUND_COLLAPSE_PROBE_TIMEOUT_MS, 30_000);
        let root = research_root().unwrap();
        assert!(safe(&root.join("stage-1.json")).is_ok());
        assert!(safe(&root.join("nested/stage-1.json")).is_err());
        assert!(safe(&root.join("../stage-1.json")).is_err());
    }

    #[test]
    fn duplicate_json_keys_are_refused_before_input_deserialization() {
        assert!(serde_json::from_str::<StrictValue>(r#"{"request":{"seed":1,"seed":2}}"#).is_err());
    }
}
