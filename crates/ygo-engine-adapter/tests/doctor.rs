use std::path::PathBuf;
use ygo_engine_adapter::*;
#[test]
fn doctor_reports_missing_worker_and_assets() {
    let mut c = ProcessEngineConfig::new(PathBuf::from("missing-worker.exe"));
    c.catalog_path = "missing.cdb".into();
    c.scripts_path = "missing-scripts".into();
    let r = ProcessEngineAdapter::new(c).doctor();
    assert!(!r.ready);
    assert!(!r.assets_ok);
    assert!(!r.abi_ok);
    assert_eq!(r.smoke_ok, None);
    assert!(r.issues.iter().any(|i| i.code == "worker_missing"));
    assert!(r.issues.iter().any(|i| i.code == "catalog_missing"));
}
#[test]
fn config_round_trip_and_legacy_gui_config_rejected() {
    let c = ProcessEngineConfig::default();
    let parsed = ProcessEngineConfig::from_toml(&c.to_toml().unwrap()).unwrap();
    assert_eq!(parsed.worker_path, c.worker_path);
    assert_eq!(parsed.timeout_ms, 30000);
    assert!(ProcessEngineConfig::from_toml("engine_path='EDOPro.exe'").is_err());
}
