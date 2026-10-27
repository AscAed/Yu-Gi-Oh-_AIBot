use std::{fs, process::Command};

#[test]
fn identity_output_cannot_overwrite_config_or_existing_evidence() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../data/tmp")
        .join(format!("cli-identity-output-{}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let root = root.canonicalize().unwrap();
    let config = root.join("engine.toml");
    let scripts = root.join("scripts");
    fs::create_dir_all(&scripts).unwrap();
    fs::write(
        &config,
        format!("scripts_path = '{}'\n", scripts.to_string_lossy()),
    )
    .unwrap();
    let run = |output: &std::path::Path| {
        Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
            .current_dir(&root)
            .args(["engine", "identity", "--config"])
            .arg(&config)
            .arg("--output")
            .arg(output)
            .output()
            .unwrap()
    };
    let original = fs::read(&config).unwrap();
    assert!(!run(&config).status.success());
    assert_eq!(fs::read(&config).unwrap(), original);
    let unsafe_output = scripts.join("new-evidence.json");
    assert!(!run(&unsafe_output).status.success());
    assert!(!unsafe_output.exists());
    let output = root.join("identity.json");
    let result = run(&output);
    assert!(
        result.status.success(),
        "{}",
        String::from_utf8_lossy(&result.stdout)
    );
    let report = fs::read(&output).unwrap();
    assert!(!run(&output).status.success());
    assert_eq!(fs::read(&output).unwrap(), report);
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn identity_output_cannot_populate_missing_runtime_assets() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../data/tmp")
        .join(format!("cli-identity-missing-{}", std::process::id()));
    fs::create_dir_all(&root).unwrap();
    let root = root.canonicalize().unwrap();
    let config = root.join("engine.toml");
    let mut text = String::new();
    let mut assets = Vec::new();
    for role in [
        "worker_path",
        "ocgcore_path",
        "catalog_path",
        "scripts_path",
        "script_manifest_path",
        "engine_manifest_path",
    ] {
        let path = root.join(role);
        text.push_str(&format!("{role} = '{}'\n", path.to_string_lossy()));
        assets.push(path);
    }
    fs::write(&config, text).unwrap();
    for path in assets {
        #[cfg(windows)]
        let outputs = vec![
            path.clone(),
            std::path::PathBuf::from(path.to_string_lossy().to_uppercase()),
        ];
        #[cfg(not(windows))]
        let outputs = vec![path.clone()];
        for output in outputs {
            let result = Command::new(env!("CARGO_BIN_EXE_ygo-cli"))
                .current_dir(&root)
                .args(["engine", "identity", "--config"])
                .arg(&config)
                .arg("--output")
                .arg(&output)
                .output()
                .unwrap();
            assert!(!result.status.success(), "output populated {output:?}");
            assert!(!path.exists());
        }
    }
    fs::remove_dir_all(root).unwrap();
}
