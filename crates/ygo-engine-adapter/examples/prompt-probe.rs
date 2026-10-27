//! One frozen Tenki stage per invocation; all native work passes the dedicated journal.
use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    fs,
    io::Write,
    path::{Path, PathBuf},
};
use ygo_engine_adapter::*;
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
fn safe(path: &Path) -> Result<(), Box<dyn std::error::Error>> {
    let root = research_root()?;
    if !path.is_absolute()
        || path
            .components()
            .any(|c| matches!(c, std::path::Component::ParentDir))
        || path.parent() != Some(root.as_path())
    {
        return Err("dedicated research path required".into());
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
fn research_root() -> Result<PathBuf, std::io::Error> {
    Ok(std::env::current_dir()?.join("data/runtime/p1-tenki-probe-native-2026-10-21/research"))
}
struct StrictValue(Value);
impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: serde::Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct Visitor;
        impl<'de> serde::de::Visitor<'de> for Visitor {
            type Value = StrictValue;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("JSON without duplicate keys")
            }
            fn visit_bool<E: serde::de::Error>(self, v: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(v)))
            }
            fn visit_i64<E: serde::de::Error>(self, v: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(v)))
            }
            fn visit_u64<E: serde::de::Error>(self, v: u64) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(v)))
            }
            fn visit_f64<E: serde::de::Error>(self, v: f64) -> Result<Self::Value, E> {
                serde_json::Number::from_f64(v)
                    .map(|n| StrictValue(Value::Number(n)))
                    .ok_or_else(|| E::custom("invalid number"))
            }
            fn visit_str<E: serde::de::Error>(self, v: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(v)))
            }
            fn visit_string<E: serde::de::Error>(self, v: String) -> Result<Self::Value, E> {
                Ok(StrictValue(json!(v)))
            }
            fn visit_unit<E: serde::de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_seq<A: serde::de::SeqAccess<'de>>(
                self,
                mut a: A,
            ) -> Result<Self::Value, A::Error> {
                let mut out = Vec::new();
                while let Some(StrictValue(v)) = a.next_element::<StrictValue>()? {
                    out.push(v);
                }
                Ok(StrictValue(Value::Array(out)))
            }
            fn visit_map<A: serde::de::MapAccess<'de>>(
                self,
                mut a: A,
            ) -> Result<Self::Value, A::Error> {
                let mut out = serde_json::Map::new();
                while let Some(key) = a.next_key::<String>()? {
                    if out.contains_key(&key) {
                        return Err(serde::de::Error::custom("duplicate JSON key"));
                    }
                    let StrictValue(v) = a.next_value::<StrictValue>()?;
                    out.insert(key, v);
                }
                Ok(StrictValue(Value::Object(out)))
            }
        }
        deserializer.deserialize_any(Visitor)
    }
}
fn publish(path: &Path, v: &Value) -> Result<(), Box<dyn std::error::Error>> {
    let mut f = fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(path)?;
    f.write_all(&serde_json::to_vec_pretty(v)?)?;
    f.sync_all()?;
    Ok(())
}
fn identity(request: &RunDuelRequest) -> Result<Value, String> {
    let v = capture_engine_identity(&request.engine)?;
    if v["consistent"] != true {
        return Err("inconsistent assets".into());
    }
    let versions = serde_json::to_value(&request.versions).map_err(|e| e.to_string())?;
    for (role, key) in [
        ("dll", "engine_sha256"),
        ("cdb", "cdb_sha256"),
        ("script_manifest", "scripts_sha256"),
    ] {
        if v["roles"][role]["sha256"] != versions[key] {
            return Err("request asset mismatch".into());
        }
    }
    Ok(v)
}
fn verify_saved(
    batch: &PromptProbeBatch,
    input: &Input,
    v: &Value,
) -> Result<(), Box<dyn std::error::Error>> {
    batch
        .verify_evidence(input.stage, v)
        .map_err(|e| e.message)?;
    if v["context"] != input.context
        || v["request"] != serde_json::to_value(&input.request)?
        || v["assets_before"] != input.expected_identity
    {
        return Err("receipt input binding differs".into());
    }
    Ok(())
}
fn main() {
    if let Err(error) = execute() {
        eprintln!("{error}");
        std::process::exit(2);
    }
}
fn execute() -> Result<(), Box<dyn std::error::Error>> {
    let args = std::env::args().collect::<Vec<_>>();
    let verify = args.len() == 5 && args[4] == "--verify-recorded";
    let stats = args.len() == 5 && args[4] == "--stats";
    if (args.len() != 4 && !verify && !stats) || args[2] != "--input-sha" {
        return Err("input --input-sha HASH [--verify-recorded|--stats] required".into());
    }
    let raw = fs::read(&args[1])?;
    if digest(&raw) != args[3] {
        return Err("input SHA mismatch".into());
    }
    safe(Path::new(&args[1]))?;
    let StrictValue(value) = serde_json::from_slice(&raw)?;
    let input: Input = serde_json::from_value(value)?;
    prompt_probe_purpose(input.stage).map_err(|e| e.message)?;
    safe(&input.ledger)?;
    safe(&input.output)?;
    let root = research_root()?;
    if input.ledger != root.join("calls.jsonl")
        || input.output != root.join(format!("stage-{}.json", input.stage))
    {
        return Err("fixed ledger/output filenames required".into());
    }
    if input.ledger == input.output
        || input.output.starts_with(&input.ledger)
        || input.ledger.starts_with(&input.output)
    {
        return Err("ledger/output overlap".into());
    }
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
            return Err("evidence overlaps assets".into());
        }
    }
    if (stats || verify) && !input.ledger.exists() {
        return Err("existing ledger required".into());
    }
    let batch = PromptProbeBatch::open(&input.ledger, &input.context, input.started_at)
        .map_err(|e| e.message)?;
    if stats {
        batch.verify().map_err(|e| e.message)?;
        println!(
            "{}",
            json!({"native_calls":0,"ledger":batch.stats().map_err(|e|e.message)?})
        );
        return Ok(());
    }
    if let Some(saved) = batch.evidence(input.stage).map_err(|e| e.message)? {
        verify_saved(&batch, &input, &saved)?;
        if input.output.exists() {
            let actual: Value = serde_json::from_slice(&fs::read(&input.output)?)?;
            if actual != saved {
                return Err("published receipt differs".into());
            }
        } else if verify {
            return Err("published receipt missing".into());
        } else {
            publish(&input.output, &saved)?;
        }
        println!(
            "{}",
            json!({"verified_recorded":true,"native_calls":0,"successful":saved["successful"],"ledger":batch.stats().map_err(|e|e.message)?})
        );
        return Ok(());
    }
    if verify {
        return Err("immutable stage receipt missing".into());
    }
    if input.output.exists() {
        return Err("output already exists".into());
    }
    batch
        .validate_request(input.stage, &input.request)
        .map_err(|e| e.message)?;
    let recorded = batch
        .load_outcome(input.stage, &input.request)
        .map_err(|e| e.message)?;
    let before = if recorded.is_some() {
        batch
            .assets_before(input.stage)
            .map_err(|e| e.message)?
            .ok_or("charged precheck receipt missing")?
    } else {
        batch.require_time().map_err(|e| e.message)?;
        let before = identity(&input.request).map_err(|e| format!("asset precheck: {e}"))?;
        if before != input.expected_identity {
            return Err("asset identity drift".into());
        }
        batch
            .save_assets_before(input.stage, &before)
            .map_err(|e| e.message)?;
        before
    };
    let native_calls = usize::from(recorded.is_none());
    let result = match recorded {
        Some(r) => r,
        None => {
            batch.require_time().map_err(|e| e.message)?;
            batch.run(
                ProcessEngineAdapter::new(input.request.engine.clone()),
                input.stage,
                &input.request,
            )
        }
    };
    let after = identity(&input.request).ok();
    let assets_unchanged =
        after.as_ref() == Some(&before) && after.as_ref() == Some(&input.expected_identity);
    let validation = result
        .as_ref()
        .map_err(|e| e.message.clone())
        .and_then(|r| validate_prompt_probe_result(input.stage, &input.request, r));
    let mut replay_matches = Value::Null;
    if input.stage == 4 || input.stage == 6 {
        let receipt = batch
            .evidence(input.stage - 1)
            .map_err(|e| e.message)?
            .ok_or("replay parent missing")?;
        let parent: Result<DuelResult, WorkerError> =
            serde_json::from_value(receipt["result"].clone())?;
        let matched = match (&parent, &result) {
            (Ok(a), Ok(b)) => prompt_probe_replay_matches(a, b),
            _ => false,
        };
        replay_matches = json!(matched);
    }
    // A post-check failure remains a paid, immutable failed stage.
    let successful = validation.is_ok()
        && assets_unchanged
        && replay_matches != false
        && batch.require_time().is_ok();
    let diagnostic = if result.as_ref().is_err() || result.as_ref().is_ok_and(|r| r.error.is_some())
    {
        Some("engine_or_journal_error")
    } else if validation.is_err() {
        Some("unexpected_intermediate_prompt")
    } else if !assets_unchanged {
        Some("asset_identity_drift")
    } else if replay_matches == false {
        Some("independent_replay_mismatch")
    } else if !successful {
        Some("window_exhausted")
    } else {
        None
    };
    let evidence = json!({"schema_version":1,"kind":"tenki_prompt_probe_stage","scope":PROMPT_PROBE_SCOPE,"stage":input.stage,"context":input.context,"request":input.request,"result":result,"validation":validation,"assets_before":before,"assets_after":after,"assets_unchanged":assets_unchanged,"independent_replay_matches":replay_matches,"successful":successful,"diagnostic":diagnostic,"ledger":batch.stats().map_err(|e|e.message)?,"started_at":input.started_at,"proof_ready":false,"complete_action_coverage":false,"global_optimality":false});
    batch
        .save_evidence(input.stage, &evidence)
        .map_err(|e| e.message)?;
    publish(&input.output, &evidence)?;
    println!(
        "{}",
        json!({"successful":successful,"native_calls":native_calls,"ledger":evidence["ledger"]})
    );
    if !successful {
        std::process::exit(1);
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn nested_json_duplicates_are_rejected() {
        assert!(
            serde_json::from_str::<StrictValue>(r#"{"expected_identity":{"a":1,"a":2}}"#).is_err()
        );
        assert!(serde_json::from_str::<StrictValue>(r#"{"a":[{"x":1,"x":2}]}"#).is_err());
        assert!(serde_json::from_str::<StrictValue>(r#"{"a":[{"x":1},{"x":2}]}"#).is_ok());
    }
    #[test]
    fn output_paths_are_fixed_to_one_research_directory() {
        let root = research_root().unwrap();
        assert!(safe(&root.join("stage-1.json")).is_ok());
        assert!(safe(&root.join("nested/stage-1.json")).is_err());
        assert!(safe(&root.join("../stage-1.json")).is_err());
        assert!(safe(
            &std::env::current_dir()
                .unwrap()
                .join("data/runtime/other/research/stage-1.json")
        )
        .is_err());
    }
}
