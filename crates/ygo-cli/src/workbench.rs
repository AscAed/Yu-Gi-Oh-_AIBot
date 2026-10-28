use serde::Deserialize;
use serde_json::{json, Value};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    net::{IpAddr, Ipv4Addr, SocketAddr, TcpListener, TcpStream},
    path::PathBuf,
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc,
    },
    thread,
    time::Duration,
};
use ygo_domain::{Catalog, DeckDocumentV1};
use ygo_storage::{secure_random_hex, DeckDraftStore, SnapshotStore};

const MAX_HEADER_BYTES: usize = 16 * 1024;
const MAX_BODY_BYTES: usize = 1024 * 1024;
const MAX_CARD_RESULTS: usize = 50;
const MAX_CONNECTIONS: usize = 32;

#[derive(Clone, Debug)]
pub struct WorkbenchConfig {
    pub bind: SocketAddr,
    pub drafts_dir: PathBuf,
    pub snapshots_dir: PathBuf,
    pub catalog_id: Option<String>,
}

impl WorkbenchConfig {
    pub fn local_default() -> Self {
        Self {
            bind: SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0),
            drafts_dir: PathBuf::from("data/runtime/workbench/drafts"),
            snapshots_dir: PathBuf::from("data/snapshots"),
            catalog_id: None,
        }
    }
}

pub struct WorkbenchServer {
    listener: TcpListener,
    address: SocketAddr,
    token: String,
    drafts: Arc<DeckDraftStore>,
    catalog: Option<(String, Arc<Catalog>)>,
    active_connections: Arc<std::sync::atomic::AtomicUsize>,
}

impl WorkbenchServer {
    pub fn start(config: WorkbenchConfig) -> Result<Self, String> {
        if config.bind.ip() != IpAddr::V4(Ipv4Addr::LOCALHOST) {
            return Err("workbench_bind_must_be_127_0_0_1".into());
        }
        let drafts = Arc::new(DeckDraftStore::open(config.drafts_dir)?);
        let catalog = match config.catalog_id {
            Some(id) => {
                let snapshot = SnapshotStore::new(config.snapshots_dir).catalog(&id)?;
                Some((snapshot.id, Arc::new(snapshot.data)))
            }
            None => None,
        };
        let listener = TcpListener::bind(config.bind)
            .map_err(|error| format!("workbench_bind_failed: {error}"))?;
        listener
            .set_nonblocking(true)
            .map_err(|error| format!("workbench_listener_failed: {error}"))?;
        let address = listener
            .local_addr()
            .map_err(|error| format!("workbench_listener_failed: {error}"))?;
        let token = secure_random_hex(32)?;
        Ok(Self {
            listener,
            address,
            token,
            drafts,
            catalog,
            active_connections: Arc::new(std::sync::atomic::AtomicUsize::new(0)),
        })
    }

    pub fn local_addr(&self) -> SocketAddr {
        self.address
    }

    pub fn token(&self) -> &str {
        &self.token
    }

    pub fn browser_url(&self) -> String {
        format!(
            "http://127.0.0.1:{}/#token={}",
            self.address.port(),
            self.token
        )
    }

    pub fn serve_until(self, stop: &AtomicBool) -> Result<(), String> {
        let drafts = self.drafts;
        let catalog = self.catalog;
        let token = Arc::new(self.token);
        while !stop.load(Ordering::SeqCst) {
            match self.listener.accept() {
                Ok((stream, _peer)) => {
                    let active = self.active_connections.fetch_add(1, Ordering::SeqCst);
                    if active >= MAX_CONNECTIONS {
                        self.active_connections.fetch_sub(1, Ordering::SeqCst);
                        let mut stream = stream;
                        let _ =
                            write_json(&mut stream, 503, json!({"error":{"code":"server_busy"}}));
                        continue;
                    }
                    let drafts = drafts.clone();
                    let catalog = catalog.clone();
                    let token = token.clone();
                    let active_connections = self.active_connections.clone();
                    let port = self.address.port();
                    thread::spawn(move || {
                        let _guard = ConnectionGuard(active_connections);
                        let _ = handle_connection(stream, port, &token, &drafts, catalog.as_ref());
                    });
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    thread::sleep(Duration::from_millis(25));
                }
                Err(error) => return Err(format!("workbench_accept_failed: {error}")),
            }
        }
        Ok(())
    }
}

struct ConnectionGuard(Arc<std::sync::atomic::AtomicUsize>);

impl Drop for ConnectionGuard {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Ordering::SeqCst);
    }
}

pub fn execute(args: &[String]) -> Result<(), String> {
    if args.first().map(String::as_str) != Some("serve") {
        return Err("usage: ygo workbench serve [--drafts DIR] [--store DIR] [--catalog-id ID] [--port PORT]".into());
    }
    let values = parse_options(&args[1..])?;
    for key in values.keys() {
        if !["--drafts", "--store", "--catalog-id", "--port"].contains(&key.as_str()) {
            return Err(format!("unknown workbench flag: {key}"));
        }
    }
    let mut config = WorkbenchConfig::local_default();
    if let Some(path) = values.get("--drafts") {
        config.drafts_dir = PathBuf::from(path);
    }
    if let Some(path) = values.get("--store") {
        config.snapshots_dir = PathBuf::from(path);
    }
    config.catalog_id = values.get("--catalog-id").cloned();
    if let Some(port) = values.get("--port") {
        let port = port
            .parse::<u16>()
            .map_err(|_| "--port must be a valid u16")?;
        config.bind.set_port(port);
    }
    let server = WorkbenchServer::start(config)?;
    println!("工作台已启动：{}", server.browser_url());
    println!("按 Ctrl+C 停止。草稿目录由本服务独占锁定。\n");
    server.serve_until(&AtomicBool::new(false))
}

fn parse_options(args: &[String]) -> Result<BTreeMap<String, String>, String> {
    let mut output = BTreeMap::new();
    let mut index = 0;
    while index < args.len() {
        let key = &args[index];
        if !key.starts_with("--") || index + 1 >= args.len() || args[index + 1].starts_with("--") {
            return Err(format!("workbench flag requires a value: {key}"));
        }
        if output
            .insert(key.clone(), args[index + 1].clone())
            .is_some()
        {
            return Err(format!("duplicate workbench flag: {key}"));
        }
        index += 2;
    }
    Ok(output)
}

#[derive(Debug)]
struct HttpRequest {
    method: String,
    target: String,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

fn read_http_request(stream: &mut TcpStream) -> Result<HttpRequest, HttpFailure> {
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|_| HttpFailure::new(400, "request_timeout"))?;
    let mut header_bytes = Vec::new();
    let mut byte = [0u8; 1];
    while header_bytes.len() < MAX_HEADER_BYTES {
        let count = stream
            .read(&mut byte)
            .map_err(|_| HttpFailure::new(400, "request_read_failed"))?;
        if count == 0 {
            return Err(HttpFailure::new(400, "request_headers_truncated"));
        }
        header_bytes.push(byte[0]);
        if header_bytes.ends_with(b"\r\n\r\n") {
            break;
        }
    }
    if !header_bytes.ends_with(b"\r\n\r\n") {
        return Err(HttpFailure::new(431, "request_headers_too_large"));
    }
    let header_text = std::str::from_utf8(&header_bytes)
        .map_err(|_| HttpFailure::new(400, "request_headers_invalid_utf8"))?;
    let mut lines = header_text.split("\r\n");
    let request_line = lines
        .next()
        .ok_or_else(|| HttpFailure::new(400, "request_line_missing"))?;
    let mut request_parts = request_line.split_whitespace();
    let method = request_parts.next().unwrap_or_default();
    let target = request_parts.next().unwrap_or_default();
    if request_parts.next() != Some("HTTP/1.1") || method.is_empty() || !target.starts_with('/') {
        return Err(HttpFailure::new(400, "request_line_invalid"));
    }
    let mut headers = BTreeMap::new();
    for line in lines.filter(|line| !line.is_empty()) {
        let (name, value) = line
            .split_once(':')
            .ok_or_else(|| HttpFailure::new(400, "request_header_invalid"))?;
        let key = name.trim().to_ascii_lowercase();
        if key.is_empty() || headers.insert(key, value.trim().to_owned()).is_some() {
            return Err(HttpFailure::new(400, "request_header_duplicate"));
        }
    }
    if headers
        .get("transfer-encoding")
        .is_some_and(|value| !value.eq_ignore_ascii_case("identity"))
    {
        return Err(HttpFailure::new(400, "transfer_encoding_unsupported"));
    }
    let content_length = match headers.get("content-length") {
        Some(value) => value
            .parse::<usize>()
            .map_err(|_| HttpFailure::new(400, "content_length_invalid"))?,
        None => 0,
    };
    if content_length > MAX_BODY_BYTES {
        return Err(HttpFailure::new(413, "request_body_too_large"));
    }
    if matches!(method, "POST" | "PUT") && !headers.contains_key("content-length") {
        return Err(HttpFailure::new(411, "content_length_required"));
    }
    let mut body = vec![0u8; content_length];
    stream
        .read_exact(&mut body)
        .map_err(|_| HttpFailure::new(400, "request_body_truncated"))?;
    Ok(HttpRequest {
        method: method.to_owned(),
        target: target.to_owned(),
        headers,
        body,
    })
}

#[derive(Debug)]
struct HttpFailure {
    status: u16,
    code: &'static str,
}

impl HttpFailure {
    fn new(status: u16, code: &'static str) -> Self {
        Self { status, code }
    }
}

fn handle_connection(
    mut stream: TcpStream,
    port: u16,
    token: &str,
    drafts: &DeckDraftStore,
    catalog: Option<&(String, Arc<Catalog>)>,
) -> Result<(), String> {
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| error.to_string())?;
    let request = match read_http_request(&mut stream) {
        Ok(request) => request,
        Err(failure) => {
            return write_json(
                &mut stream,
                failure.status,
                json!({"error":{"code":failure.code}}),
            )
        }
    };
    let host = format!("127.0.0.1:{port}");
    if request.headers.get("host").map(String::as_str) != Some(host.as_str()) {
        return write_json(&mut stream, 400, json!({"error":{"code":"host_not_local"}}));
    }
    if request.target == "/" && request.method == "GET" {
        return write_asset(
            &mut stream,
            200,
            "text/html; charset=utf-8",
            include_str!("workbench/index.html"),
        );
    }
    if request.target == "/app.js" && request.method == "GET" {
        return write_asset(
            &mut stream,
            200,
            "text/javascript; charset=utf-8",
            include_str!("workbench/app.js"),
        );
    }
    if request.target == "/style.css" && request.method == "GET" {
        return write_asset(
            &mut stream,
            200,
            "text/css; charset=utf-8",
            include_str!("workbench/style.css"),
        );
    }
    if !request.target.starts_with("/api/") {
        return write_json(
            &mut stream,
            404,
            json!({"error":{"code":"route_not_found"}}),
        );
    }
    let expected_auth = format!("Bearer {token}");
    if !constant_time_eq(
        request
            .headers
            .get("authorization")
            .map(String::as_str)
            .unwrap_or(""),
        &expected_auth,
    ) {
        return write_json(
            &mut stream,
            403,
            json!({"error":{"code":"authorization_required"}}),
        );
    }
    if matches!(request.method.as_str(), "POST" | "PUT") {
        let expected_origin = format!("http://127.0.0.1:{port}");
        if request.headers.get("origin").map(String::as_str) != Some(expected_origin.as_str()) {
            return write_json(
                &mut stream,
                403,
                json!({"error":{"code":"origin_not_local"}}),
            );
        }
    }
    let (path, query) = split_target(&request.target);
    let response = route_request(&request, path, query, drafts, catalog);
    match response {
        Ok(response) => write_response(&mut stream, response),
        Err(failure) => write_json(
            &mut stream,
            failure.status,
            json!({"error":{"code":failure.code}}),
        ),
    }
}

struct HttpResponse {
    status: u16,
    content_type: &'static str,
    body: Vec<u8>,
    attachment: Option<&'static str>,
}

fn route_request(
    request: &HttpRequest,
    path: &str,
    query: &str,
    drafts: &DeckDraftStore,
    catalog: Option<&(String, Arc<Catalog>)>,
) -> Result<HttpResponse, HttpFailure> {
    match (request.method.as_str(), path) {
        ("GET", "/api/drafts") => {
            let list = drafts
                .list()
                .map_err(|_| HttpFailure::new(500, "draft_list_failed"))?;
            let entries = list.iter().map(|entry| json!({
                "id":entry.id,"revision":entry.revision,"title":entry.draft.title,
                "main_count":entry.draft.main.len(),"extra_count":entry.draft.extra.len(),"side_count":entry.draft.side.len()
            })).collect::<Vec<_>>();
            json_response(
                200,
                json!({"drafts":entries,"catalog_id":catalog.map(|c| c.0.as_str())}),
            )
        }
        ("POST", "/api/drafts") => {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Create {
                title: Option<String>,
            }
            let input: Create = parse_json(&request.body)?;
            let draft = DeckDocumentV1::new(
                input.title.unwrap_or_else(|| "未命名牌组".into()),
                vec![],
                vec![],
                vec![],
            )
            .map_err(|_| HttpFailure::new(400, "draft_invalid"))?;
            let stored = drafts
                .create(draft)
                .map_err(|_| HttpFailure::new(500, "draft_create_failed"))?;
            json_response(
                201,
                serde_json::to_value(stored)
                    .map_err(|_| HttpFailure::new(500, "response_encode_failed"))?,
            )
        }
        ("POST", "/api/import") => {
            let format = query_value(query, "format")
                .ok_or_else(|| HttpFailure::new(400, "import_format_required"))?;
            let text = std::str::from_utf8(&request.body)
                .map_err(|_| HttpFailure::new(400, "import_invalid_utf8"))?;
            let draft = match format.as_str() {
                "json" => DeckDocumentV1::import_json(text),
                "ydk" => DeckDocumentV1::from_ydk(text),
                _ => return Err(HttpFailure::new(400, "import_format_unsupported")),
            }
            .map_err(|_| HttpFailure::new(400, "import_invalid"))?;
            json_response(
                200,
                json!({"draft":draft,"saved":false,"legality":"not_checked"}),
            )
        }
        ("POST", "/api/export") => {
            let format = query_value(query, "format")
                .ok_or_else(|| HttpFailure::new(400, "export_format_required"))?;
            let draft: DeckDocumentV1 = parse_json(&request.body)?;
            draft
                .validate()
                .map_err(|_| HttpFailure::new(400, "draft_invalid"))?;
            let (content_type, body, filename) = match format.as_str() {
                "json" => (
                    "application/json; charset=utf-8",
                    draft
                        .to_json()
                        .map_err(|_| HttpFailure::new(400, "draft_invalid"))?
                        .into_bytes(),
                    "deck.json",
                ),
                "ydk" => (
                    "application/x-yugioh-deck; charset=utf-8",
                    draft.to_ydk().into_bytes(),
                    "deck.ydk",
                ),
                _ => return Err(HttpFailure::new(400, "export_format_unsupported")),
            };
            Ok(HttpResponse {
                status: 200,
                content_type,
                body,
                attachment: Some(filename),
            })
        }
        ("GET", path) if path.starts_with("/api/drafts/") => {
            let id = &path[12..];
            if id.contains('/') {
                return Err(HttpFailure::new(404, "draft_not_found"));
            }
            let stored = drafts
                .load(id)
                .map_err(|_| HttpFailure::new(404, "draft_not_found"))?;
            json_response(
                200,
                serde_json::to_value(stored)
                    .map_err(|_| HttpFailure::new(500, "response_encode_failed"))?,
            )
        }
        ("PUT", path) if path.starts_with("/api/drafts/") => {
            let id = &path[12..];
            if id.contains('/') {
                return Err(HttpFailure::new(404, "draft_not_found"));
            }
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Update {
                revision: String,
                draft: DeckDocumentV1,
            }
            let input: Update = parse_json(&request.body)?;
            let stored = drafts
                .update(id, &input.revision, input.draft)
                .map_err(|error| {
                    if error == "revision_conflict" {
                        HttpFailure::new(409, "revision_conflict")
                    } else {
                        HttpFailure::new(400, "draft_update_failed")
                    }
                })?;
            json_response(
                200,
                serde_json::to_value(stored)
                    .map_err(|_| HttpFailure::new(500, "response_encode_failed"))?,
            )
        }
        ("GET", "/api/cards") => {
            let needle = query_value(query, "q").unwrap_or_default();
            let Some((catalog_id, cards)) = catalog else {
                return json_response(
                    200,
                    json!({"status":"unverified","reason":"no_catalog_selected","catalog_id":null,"translation_status":"unverified","results":[]}),
                );
            };
            let needle_lower = needle.to_lowercase();
            let numeric = needle.parse::<u32>().ok();
            let mut results = cards
                .iter()
                .filter(|(id, card)| {
                    if let Some(numeric) = numeric {
                        id.0 == numeric
                    } else {
                        !needle.is_empty() && card.name.to_lowercase().contains(&needle_lower)
                    }
                })
                .take(MAX_CARD_RESULTS)
                .map(|(id, card)| {
                    json!({
                        "id":id.0,"name":card.name,"source":format!("local_catalog:{catalog_id}"),
                        "translation_status":"unverified"
                    })
                })
                .collect::<Vec<_>>();
            let status = if numeric.is_some() && results.is_empty() {
                "unknown_card_id"
            } else {
                "checked"
            };
            for item in &mut results {
                item["notice"] = Value::String("名称来自所选本地快照；中文译文未核验".into());
            }
            json_response(
                200,
                json!({"status":status,"catalog_id":catalog_id,"translation_status":"unverified","results":results}),
            )
        }
        _ => Err(HttpFailure::new(404, "route_not_found")),
    }
}

fn parse_json<T: serde::de::DeserializeOwned>(body: &[u8]) -> Result<T, HttpFailure> {
    serde_json::from_slice(body).map_err(|_| HttpFailure::new(400, "json_invalid"))
}

fn json_response(status: u16, value: Value) -> Result<HttpResponse, HttpFailure> {
    let body =
        serde_json::to_vec(&value).map_err(|_| HttpFailure::new(500, "response_encode_failed"))?;
    Ok(HttpResponse {
        status,
        content_type: "application/json; charset=utf-8",
        body,
        attachment: None,
    })
}

fn split_target(target: &str) -> (&str, &str) {
    target.split_once('?').unwrap_or((target, ""))
}

fn query_value(query: &str, key: &str) -> Option<String> {
    query
        .split('&')
        .filter_map(|part| part.split_once('='))
        .find_map(|(name, value)| {
            (percent_decode(name).ok()?.as_str() == key)
                .then(|| percent_decode(value).ok())
                .flatten()
        })
}

fn percent_decode(value: &str) -> Result<String, ()> {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'+' => {
                output.push(b' ');
                index += 1;
            }
            b'%' if index + 2 < bytes.len() => {
                let high = (bytes[index + 1] as char).to_digit(16).ok_or(())? as u8;
                let low = (bytes[index + 2] as char).to_digit(16).ok_or(())? as u8;
                output.push((high << 4) | low);
                index += 3;
            }
            b'%' => return Err(()),
            byte => {
                output.push(byte);
                index += 1;
            }
        }
    }
    String::from_utf8(output).map_err(|_| ())
}

fn constant_time_eq(left: &str, right: &str) -> bool {
    let mut difference = left.len() ^ right.len();
    let max_len = left.len().max(right.len());
    for index in 0..max_len {
        difference |= usize::from(
            left.as_bytes().get(index).copied().unwrap_or(0)
                ^ right.as_bytes().get(index).copied().unwrap_or(0),
        );
    }
    difference == 0
}

fn status_text(status: u16) -> &'static str {
    match status {
        200 => "OK",
        201 => "Created",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        409 => "Conflict",
        411 => "Length Required",
        413 => "Payload Too Large",
        431 => "Request Header Fields Too Large",
        500 => "Internal Server Error",
        _ => "Error",
    }
}

fn write_json(stream: &mut TcpStream, status: u16, value: Value) -> Result<(), String> {
    let body = serde_json::to_vec(&value).map_err(|error| error.to_string())?;
    write_response(
        stream,
        HttpResponse {
            status,
            content_type: "application/json; charset=utf-8",
            body,
            attachment: None,
        },
    )
}

fn write_asset(
    stream: &mut TcpStream,
    status: u16,
    content_type: &'static str,
    body: &str,
) -> Result<(), String> {
    write_response(
        stream,
        HttpResponse {
            status,
            content_type,
            body: body.as_bytes().to_vec(),
            attachment: None,
        },
    )
}

fn write_response(stream: &mut TcpStream, response: HttpResponse) -> Result<(), String> {
    let status = response.status;
    let mut headers = format!(
        "HTTP/1.1 {} {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nConnection: close\r\nCache-Control: no-store\r\nX-Content-Type-Options: nosniff\r\nReferrer-Policy: no-referrer\r\n",
        status, status_text(status), response.content_type, response.body.len()
    );
    if let Some(filename) = response.attachment {
        headers.push_str(&format!(
            "Content-Disposition: attachment; filename=\"{filename}\"\r\n"
        ));
    }
    if response.content_type.starts_with("text/html") {
        headers.push_str("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'\r\n");
    }
    headers.push_str("\r\n");
    stream
        .write_all(headers.as_bytes())
        .map_err(|error| error.to_string())?;
    stream
        .write_all(&response.body)
        .map_err(|error| error.to_string())?;
    stream.flush().map_err(|error| error.to_string())
}
