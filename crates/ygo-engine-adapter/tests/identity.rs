use std::fs;
use ygo_engine_adapter::{capture_engine_identity, ProcessEngineConfig};

#[test]
fn identity_detects_asset_drift_and_manifest_escape() {
    let root = std::env::temp_dir().join(format!("ygo-identity-{}", std::process::id()));
    fs::create_dir_all(root.join("scripts")).unwrap();
    for file in ["worker", "dll", "cdb", "engine.json"] {
        fs::write(root.join(file), b"asset").unwrap();
    }
    fs::write(root.join("scripts/a.lua"), b"a").unwrap();
    fs::write(
        root.join("scripts.json"),
        format!("{{\"a.lua\":\"{}\"}}", ygo_engine_adapter::digest(b"a")),
    )
    .unwrap();
    let cfg = ProcessEngineConfig {
        worker_path: root.join("worker"),
        ocgcore_path: root.join("dll"),
        catalog_path: root.join("cdb"),
        scripts_path: root.join("scripts"),
        script_manifest_path: root.join("scripts.json"),
        engine_manifest_path: root.join("engine.json"),
        timeout_ms: 30000,
    };
    let a = capture_engine_identity(&cfg).unwrap();
    assert_eq!(a["consistent"], true);
    assert_eq!(a, capture_engine_identity(&cfg).unwrap());
    assert!(!a.to_string().contains(&root.to_string_lossy().to_string()));
    fs::write(root.join("scripts/a.lua"), b"changed").unwrap();
    let b = capture_engine_identity(&cfg).unwrap();
    assert_ne!(a["identity"], b["identity"]);
    assert_eq!(b["scripts"]["mismatch"][0], "a.lua");
    fs::write(root.join("scripts/extra.lua"), b"extra").unwrap();
    fs::remove_file(root.join("scripts/a.lua")).unwrap();
    let c = capture_engine_identity(&cfg).unwrap();
    assert_eq!(c["consistent"], false);
    assert_eq!(c["scripts"]["missing"][0], "a.lua");
    assert_eq!(c["scripts"]["extra"][0], "extra.lua");
    fs::write(root.join("worker"), b"changed worker").unwrap();
    let d = capture_engine_identity(&cfg).unwrap();
    assert_ne!(c["roles"]["worker"], d["roles"]["worker"]);
    fs::remove_file(root.join("worker")).unwrap();
    assert_eq!(
        capture_engine_identity(&cfg).unwrap()["roles"]["worker"]["status"],
        "missing"
    );
    fs::write(root.join("scripts.json"), b"{\"../outside\":\"bad\"}").unwrap();
    assert!(capture_engine_identity(&cfg).is_err());
    fs::remove_dir_all(root).unwrap();
}
