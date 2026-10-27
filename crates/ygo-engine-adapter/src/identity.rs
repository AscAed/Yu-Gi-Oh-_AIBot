//! Read-only content identity, independent of runtime version hashes.
use crate::{digest, ProcessEngineConfig};
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    fs,
    path::{Component, Path},
};

fn safe_metadata(path: &Path) -> Result<fs::Metadata, String> {
    // Reject links and Windows junctions at every component, including ancestors.
    let mut current = std::path::PathBuf::new();
    for component in path.components() {
        current.push(component);
        // A Windows drive/verbatim prefix alone is not a filesystem entry.
        if matches!(component, Component::Prefix(_)) {
            continue;
        }
        let metadata =
            fs::symlink_metadata(&current).map_err(|_| "asset inaccessible".to_string())?;
        if metadata.file_type().is_symlink() {
            return Err("asset link rejected".into());
        }
        #[cfg(windows)]
        {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 {
                return Err("asset reparse point rejected".into());
            }
        }
    }
    fs::symlink_metadata(path).map_err(|_| "asset inaccessible".into())
}

fn hash(path: &Path) -> Result<String, String> {
    if !safe_metadata(path)?.is_file() {
        return Err("asset is not a regular file".into());
    }
    fs::read(path)
        .map(|bytes| digest(&bytes))
        .map_err(|_| "asset unreadable".into())
}

fn walk(root: &Path, here: &Path, files: &mut BTreeMap<String, String>) -> Result<(), String> {
    if !safe_metadata(here)?.is_dir() {
        return Err("script root is not a directory".into());
    }
    for entry in fs::read_dir(here).map_err(|_| "script directory unreadable")? {
        let path = entry.map_err(|_| "script entry unreadable")?.path();
        let metadata = safe_metadata(&path)?;
        if metadata.is_dir() {
            walk(root, &path, files)?;
        } else if metadata.is_file() {
            let relative = path.strip_prefix(root).map_err(|_| "script path escape")?;
            let name = relative
                .to_str()
                .ok_or("non UTF-8 script path")?
                .replace('\\', "/");
            files.insert(name, hash(&path)?);
        } else {
            return Err("special script file rejected".into());
        }
    }
    Ok(())
}

fn sample(config: &ProcessEngineConfig) -> Result<Value, String> {
    let mut roles = BTreeMap::new();
    for (role, path) in [
        ("worker", &config.worker_path),
        ("dll", &config.ocgcore_path),
        ("cdb", &config.catalog_path),
        ("script_manifest", &config.script_manifest_path),
        ("engine_manifest", &config.engine_manifest_path),
    ] {
        let value = match hash(path) {
            Ok(value) => json!({"sha256":value,"status":"present"}),
            Err(_)
                if fs::symlink_metadata(path)
                    .is_err_and(|e| e.kind() == std::io::ErrorKind::NotFound) =>
            {
                json!({"sha256":null,"status":"missing"})
            }
            Err(error) => return Err(format!("{role}: {error}")),
        };
        roles.insert(role, value);
    }
    let expected: BTreeMap<String, String> = if config.script_manifest_path.exists() {
        serde_json::from_slice(
            &fs::read(&config.script_manifest_path).map_err(|_| "script manifest unreadable")?,
        )
        .map_err(|_| "invalid script manifest")?
    } else {
        BTreeMap::new()
    };
    for (name, sha) in &expected {
        if name.is_empty()
            || name.contains('\\')
            || name.contains(':')
            || name
                .split('/')
                .any(|s| s.is_empty() || s == "." || s == "..")
            || !Path::new(name)
                .components()
                .all(|c| matches!(c, Component::Normal(_)))
        {
            return Err("unsafe script manifest path".into());
        }
        if sha.len() != 64
            || !sha
                .bytes()
                .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase())
        {
            return Err("invalid script manifest hash".into());
        }
    }
    let mut actual = BTreeMap::new();
    let root_present = config.scripts_path.exists();
    if !root_present && fs::symlink_metadata(&config.scripts_path).is_ok() {
        return Err("script root link rejected".into());
    }
    if root_present {
        walk(&config.scripts_path, &config.scripts_path, &mut actual)?;
    }
    let missing: Vec<_> = expected
        .keys()
        .filter(|key| !actual.contains_key(*key))
        .collect();
    let extra: Vec<_> = actual
        .keys()
        .filter(|key| !expected.contains_key(*key))
        .collect();
    let mismatch: Vec<_> = expected
        .iter()
        .filter(|(key, sha)| actual.get(*key).is_some_and(|v| v != *sha))
        .map(|(key, _)| key)
        .collect();
    let consistent = root_present
        && roles.values().all(|v| v["status"] == "present")
        && missing.is_empty()
        && extra.is_empty()
        && mismatch.is_empty();
    Ok(
        json!({"schema_version":1,"kind":"engine_identity","roles":roles,"scripts":{"root_present":root_present,"actual":actual,"missing":missing,"extra":extra,"mismatch":mismatch},"timeout_ms":config.timeout_ms,"consistent":consistent}),
    )
}

/// Samples twice and refuses a consistency conclusion if any content changes.
pub fn capture_engine_identity(config: &ProcessEngineConfig) -> Result<Value, String> {
    let first = sample(config)?;
    let mut second = sample(config)?;
    if first != second {
        return Err("assets changed during identity capture".into());
    }
    second["identity"] = json!(digest(
        &serde_json::to_vec(&second).map_err(|_| "identity serialization failed")?
    ));
    Ok(second)
}
