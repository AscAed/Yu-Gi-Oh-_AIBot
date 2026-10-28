use std::{
    collections::BTreeMap,
    fs,
    io::{Read, Write},
    net::TcpStream,
    ops::Deref,
    path::{Path, PathBuf},
    sync::{atomic::AtomicBool, Arc},
    thread,
    time::Duration,
};
use ygo_cli::workbench::{WorkbenchConfig, WorkbenchServer};
use ygo_domain::{Card, CardId, CardKind};
use ygo_storage::{hash, DataSnapshot};

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
        "ygo-workbench-http-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    fs::create_dir_all(&path).unwrap();
    TempDir(path)
}

fn request(addr: std::net::SocketAddr, raw: &str) -> String {
    let mut stream = TcpStream::connect(addr).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(2)))
        .unwrap();
    stream.write_all(raw.as_bytes()).unwrap();
    let mut response = String::new();
    stream.read_to_string(&mut response).unwrap();
    response
}

#[test]
fn local_workbench_authenticates_mutations_and_supports_draft_round_trip() {
    let root = temp_dir();
    let config = WorkbenchConfig {
        bind: "127.0.0.1:0".parse().unwrap(),
        drafts_dir: root.join("drafts"),
        snapshots_dir: root.join("snapshots"),
        catalog_id: None,
        language_status_path: None,
    };
    let server = WorkbenchServer::start(config.clone()).unwrap();
    let addr = server.local_addr();
    let token = server.token().to_owned();
    let stop = Arc::new(AtomicBool::new(false));
    let server_stop = stop.clone();
    let thread = thread::spawn(move || server.serve_until(&server_stop).unwrap());

    let no_token = request(
        addr,
        &format!(
            "GET /api/drafts HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nConnection: close\r\n\r\n",
            addr.port()
        ),
    );
    assert!(no_token.starts_with("HTTP/1.1 403"));

    let body = r#"{"title":"工作草稿"}"#;
    let create = format!(
        "POST /api/drafts HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        addr.port(), addr.port(), token, body.len(), body
    );
    let created = request(addr, &create);
    assert!(created.starts_with("HTTP/1.1 201"), "{created}");
    let payload = created.split("\r\n\r\n").nth(1).unwrap();
    let created: serde_json::Value = serde_json::from_str(payload).unwrap();
    let id = created["id"].as_str().unwrap();
    let revision = created["revision"].as_str().unwrap();

    let draft = serde_json::json!({"schema_version":1,"kind":"deck_draft","title":"工作草稿","main":[42,42],"extra":[7],"side":[9]});
    let update_body = serde_json::json!({"revision":revision,"draft":draft.clone()}).to_string();
    let update = format!(
        "PUT /api/drafts/{id} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        addr.port(), addr.port(), token, update_body.len(), update_body
    );
    assert!(request(addr, &update).starts_with("HTTP/1.1 200"));

    let get = format!(
        "GET /api/drafts/{id} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        addr.port(), token
    );
    let loaded = request(addr, &get);
    assert!(loaded.contains("\"main\":[42,42]"));

    let stale_update_body =
        serde_json::json!({"revision":revision,"draft":draft.clone()}).to_string();
    let stale_update = format!(
        "PUT /api/drafts/{id} HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        addr.port(), addr.port(), token, stale_update_body.len(), stale_update_body
    );
    assert!(request(addr, &stale_update).starts_with("HTTP/1.1 409"));

    let exported_body = draft.to_string();
    let export = format!(
        "POST /api/export?format=ydk HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        addr.port(), addr.port(), token, exported_body.len(), exported_body
    );
    let exported = request(addr, &export);
    assert!(exported.starts_with("HTTP/1.1 200"));
    assert!(
        exported.contains("#main\n42\n42\n#extra\n7\n!side\n9\n"),
        "{exported:?}"
    );

    let ydk = "#main\n42\n42\n#extra\n7\n!side\n9\n";
    let import = format!(
        "POST /api/import?format=ydk HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: text/plain\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        addr.port(), addr.port(), token, ydk.len(), ydk
    );
    let imported = request(addr, &import);
    assert!(imported.starts_with("HTTP/1.1 200"));
    assert!(imported.contains("\"main\":[42,42]"));

    let no_catalog = format!(
        "GET /api/cards?q=42 HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        addr.port(), token
    );
    let cards = request(addr, &no_catalog);
    assert!(cards.contains("\"status\":\"unverified\""));

    stop.store(true, std::sync::atomic::Ordering::SeqCst);
    thread.join().unwrap();
}

#[test]
fn local_workbench_rejects_foreign_host_origin_and_oversized_body() {
    let root = temp_dir();
    let config = WorkbenchConfig {
        bind: "127.0.0.1:0".parse().unwrap(),
        drafts_dir: root.join("drafts"),
        snapshots_dir: root.join("snapshots"),
        catalog_id: None,
        language_status_path: None,
    };
    let server = WorkbenchServer::start(config).unwrap();
    let addr = server.local_addr();
    let token = server.token().to_owned();
    let stop = Arc::new(AtomicBool::new(false));
    let server_stop = stop.clone();
    let thread = thread::spawn(move || server.serve_until(&server_stop).unwrap());

    let foreign_host = format!("GET /api/drafts HTTP/1.1\r\nHost: evil.test:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n", addr.port(), token);
    assert!(request(addr, &foreign_host).starts_with("HTTP/1.1 400"));
    let foreign_origin = format!("POST /api/drafts HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://evil.test\r\nAuthorization: Bearer {}\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{{}}", addr.port(), token);
    assert!(request(addr, &foreign_origin).starts_with("HTTP/1.1 403"));
    let invalid_input = format!("POST /api/drafts HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: 1\r\nConnection: close\r\n\r\nx", addr.port(), addr.port(), token);
    assert!(request(addr, &invalid_input).starts_with("HTTP/1.1 400"));
    let oversized = format!("POST /api/drafts HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nOrigin: http://127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nContent-Length: 1048577\r\nConnection: close\r\n\r\n", addr.port(), addr.port(), token);
    assert!(request(addr, &oversized).starts_with("HTTP/1.1 413"));

    stop.store(true, std::sync::atomic::Ordering::SeqCst);
    thread.join().unwrap();
}

#[test]
fn selected_snapshot_is_verified_and_card_results_disclose_name_source_and_translation_state() {
    let root = temp_dir();
    let snapshots_dir = root.join("snapshots");
    fs::create_dir_all(&snapshots_dir).unwrap();
    let catalog = BTreeMap::from([(
        CardId(42),
        Card {
            id: CardId(42),
            name: "Raw catalog name".into(),
            kind: CardKind::Monster,
            ..Default::default()
        },
    )]);
    let source = "synthetic local catalog".to_owned();
    let version = "fixture".to_owned();
    let raw_hash = "a".repeat(64);
    let content = serde_json::to_vec(&catalog).unwrap();
    let provenance = serde_json::to_vec(&(
        "catalog",
        &source,
        &version,
        &raw_hash,
        &Option::<String>::None,
        "normalizer-v1",
        &content,
    ))
    .unwrap();
    let id = format!("catalog-{}", hash(&provenance));
    let snapshot = DataSnapshot {
        id: id.clone(),
        schema_version: 2,
        source,
        source_version: version,
        source_sha256: raw_hash,
        effective_date: None,
        retrieved_at: "test".into(),
        license: "test only".into(),
        normalizer_version: "normalizer-v1".into(),
        data: catalog,
    };
    fs::write(
        snapshots_dir.join(format!("{id}.json")),
        serde_json::to_vec(&snapshot).unwrap(),
    )
    .unwrap();

    let config = WorkbenchConfig {
        bind: "127.0.0.1:0".parse().unwrap(),
        drafts_dir: root.join("drafts"),
        snapshots_dir,
        catalog_id: Some(id.clone()),
        language_status_path: None,
    };
    let server = WorkbenchServer::start(config).unwrap();
    let addr = server.local_addr();
    let token = server.token().to_owned();
    let stop = Arc::new(AtomicBool::new(false));
    let server_stop = stop.clone();
    let thread = thread::spawn(move || server.serve_until(&server_stop).unwrap());
    let query = format!(
        "GET /api/cards?q=42 HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        addr.port(), token
    );
    let response = request(addr, &query);
    assert!(response.contains("Raw catalog name"));
    assert!(response.contains(&id));
    assert!(
        response.contains("\"translation_status\":\"unverified\""),
        "{response:?}"
    );

    stop.store(true, std::sync::atomic::Ordering::SeqCst);
    thread.join().unwrap();
}

#[test]
fn language_status_endpoint_exposes_field_states_without_translation_text_and_degrades_safely() {
    let root = temp_dir();
    let status_path = root.join("language-status.json");
    let source_fields = |source: &str| {
        serde_json::json!({
            "name":{"status":"candidate","source":source,"reason":"candidate_not_semantically_reviewed","candidate_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},
            "text":{"status":"missing","source":source,"reason":"candidate_value_absent"},
            "alias":{"status":"unknown","source":source,"reason":"localized_alias_mapping_not_defined"},
            "archetypes":{"status":"unknown","source":source,"reason":"localized_archetype_mapping_not_defined"}
        })
    };
    let language_report = serde_json::json!({
        "schema_version":1,
        "kind":"language_field_review",
        "qualified":false,
        "cards":[{"card_id":42,"sources":{
            "mycard-zh-CN-217ae165":{"fields":source_fields("mycard-zh-CN-217ae165")},
            "mycard-zh-SC-217ae165":{"fields":source_fields("mycard-zh-SC-217ae165")}
        }}],
        "translation_payload":"must not reach browser"
    });
    fs::write(&status_path, serde_json::to_vec(&language_report).unwrap()).unwrap();
    let config = WorkbenchConfig {
        bind: "127.0.0.1:0".parse().unwrap(),
        drafts_dir: root.join("drafts"),
        snapshots_dir: root.join("snapshots"),
        catalog_id: None,
        language_status_path: Some(status_path.clone()),
    };
    let server = WorkbenchServer::start(config.clone()).unwrap();
    let addr = server.local_addr();
    let token = server.token().to_owned();
    let stop = Arc::new(AtomicBool::new(false));
    let server_stop = stop.clone();
    let thread = thread::spawn(move || server.serve_until(&server_stop).unwrap());
    let query = format!(
        "GET /api/language-status?ids=42,99 HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        addr.port(), token
    );
    let response = request(addr, &query);
    assert!(response.contains("\"status\":\"available\""), "{response}");
    assert!(response.contains("\"card_id\":42"), "{response}");
    assert!(response.contains("\"status\":\"candidate\""), "{response}");
    assert!(!response.contains("must not reach browser"), "{response}");

    stop.store(true, std::sync::atomic::Ordering::SeqCst);
    thread.join().unwrap();

    fs::write(&status_path, "not-json").unwrap();
    let unavailable_server = WorkbenchServer::start(config.clone()).unwrap();
    let unavailable_addr = unavailable_server.local_addr();
    let unavailable_token = unavailable_server.token().to_owned();
    let unavailable_stop = Arc::new(AtomicBool::new(false));
    let server_stop = unavailable_stop.clone();
    let unavailable_thread =
        thread::spawn(move || unavailable_server.serve_until(&server_stop).unwrap());
    let unavailable_query = format!(
        "GET /api/language-status?ids=42 HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        unavailable_addr.port(), unavailable_token
    );
    let unavailable = request(unavailable_addr, &unavailable_query);
    assert!(
        unavailable.contains("\"status\":\"unverified\""),
        "{unavailable}"
    );
    assert!(!unavailable.contains("candidate"), "{unavailable}");
    unavailable_stop.store(true, std::sync::atomic::Ordering::SeqCst);
    unavailable_thread.join().unwrap();

    let mut invalid_report = language_report;
    invalid_report["cards"][0]["sources"]["mycard-zh-CN-217ae165"]["fields"]["name"]
        .as_object_mut()
        .unwrap()
        .remove("candidate_sha256");
    fs::write(&status_path, serde_json::to_vec(&invalid_report).unwrap()).unwrap();
    let invalid_server = WorkbenchServer::start(config).unwrap();
    let invalid_addr = invalid_server.local_addr();
    let invalid_token = invalid_server.token().to_owned();
    let invalid_stop = Arc::new(AtomicBool::new(false));
    let server_stop = invalid_stop.clone();
    let invalid_thread = thread::spawn(move || invalid_server.serve_until(&server_stop).unwrap());
    let invalid_query = format!(
        "GET /api/language-status?ids=42 HTTP/1.1\r\nHost: 127.0.0.1:{}\r\nAuthorization: Bearer {}\r\nConnection: close\r\n\r\n",
        invalid_addr.port(), invalid_token
    );
    let invalid = request(invalid_addr, &invalid_query);
    assert!(invalid.contains("\"status\":\"unverified\""), "{invalid}");
    invalid_stop.store(true, std::sync::atomic::Ordering::SeqCst);
    invalid_thread.join().unwrap();
}
