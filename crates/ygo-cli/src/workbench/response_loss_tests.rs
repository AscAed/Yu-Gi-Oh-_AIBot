//! Synthetic TCP acceptance; no engine or worker is executed.
use super::{tests::request, AnalysisHttpService};
use crate::workbench::{response_loss::ResponseFault, WorkbenchConfig, WorkbenchServer};
use crate::workbench_analysis::{
    durable::DurableAnalysisCoordinator, operations::AnalysisOperationContext, tests::fixtures,
};
use serde_json::{json, Value};
use std::{
    io::{Read, Write},
    net::{Shutdown, SocketAddr, TcpStream},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc, Arc, Mutex,
    },
    thread,
    time::Duration,
};

struct ReleaseFreeze(mpsc::Sender<()>);
impl Drop for ReleaseFreeze {
    fn drop(&mut self) {
        let _ = self.0.send(());
    }
}

fn snapshot(root: &Path) -> Vec<(PathBuf, Vec<u8>)> {
    fn visit(root: &Path, dir: &Path, out: &mut Vec<(PathBuf, Vec<u8>)>) {
        let mut entries = std::fs::read_dir(dir)
            .unwrap()
            .map(|e| e.unwrap().path())
            .collect::<Vec<_>>();
        entries.sort();
        for p in entries {
            if p.is_dir() {
                out.push((p.strip_prefix(root).unwrap().to_owned(), Vec::new()));
                visit(root, &p, out);
            } else {
                out.push((
                    p.strip_prefix(root).unwrap().to_owned(),
                    if p.extension().is_some_and(|x| x == "lock") {
                        let metadata = std::fs::metadata(&p).unwrap();
                        format!(
                            "length={};readonly={}",
                            metadata.len(),
                            metadata.permissions().readonly()
                        )
                        .into_bytes()
                    } else {
                        std::fs::read(p).unwrap()
                    },
                ));
            }
        }
    }
    let mut out = Vec::new();
    visit(root, root, &mut out);
    out
}

#[allow(clippy::too_many_arguments)]
fn lose<F: FnOnce()>(
    service: &AnalysisHttpService,
    addr: SocketAddr,
    token: &str,
    method: &str,
    path: &str,
    body: Value,
    truncate: bool,
    log: &Path,
    check: F,
) {
    let (entered_tx, entered_rx) = mpsc::sync_channel(1);
    let (release_tx, release_rx) = mpsc::channel();
    *service.response_fault.lock().unwrap() = Some(ResponseFault {
        method: method.into(),
        path: path.into(),
        remaining: 1,
        truncate,
        entered: entered_tx,
        release: release_rx,
    });
    let mut socket = TcpStream::connect(addr).unwrap();
    socket
        .set_read_timeout(Some(Duration::from_secs(12)))
        .unwrap();
    let body = if method == "GET" {
        String::new()
    } else {
        body.to_string()
    };
    write!(socket,"{method} {path} HTTP/1.1\r\nHost: {addr}\r\nOrigin: http://{addr}\r\nAuthorization: Bearer {token}\r\nContent-Length: {}\r\n\r\n{body}",body.len()).unwrap();
    socket.shutdown(Shutdown::Write).unwrap();
    let handshake_error = entered_rx
        .recv_timeout(Duration::from_secs(12))
        .err()
        .map(|e| format!("{e:?}"));
    // Preserve raw transport evidence even if routing never reaches the gate.
    if handshake_error.is_none() {
        check();
        release_tx.send(()).unwrap();
    }
    drop(release_tx);
    let mut bytes = Vec::new();
    let mut error = None;
    let mut declared = None;
    let mut split = None;
    loop {
        let mut byte = [0];
        match socket.read(&mut byte) {
            Ok(0) => break,
            Ok(_) => bytes.push(byte[0]),
            Err(e) => {
                error = Some(format!("{:?}", e.kind()));
                break;
            }
        }
        if bytes.ends_with(b"\r\n\r\n") {
            split = Some(bytes.len());
            let header = std::str::from_utf8(&bytes).unwrap();
            declared = header.lines().find_map(|line| {
                let (key, value) = line.split_once(':')?;
                key.eq_ignore_ascii_case("Content-Length")
                    .then(|| value.trim().parse::<usize>().unwrap())
            });
            break;
        }
        assert!(bytes.len() < 8192, "bounded response header");
    }
    if let Some(length) = declared {
        let offset = split.unwrap();
        while bytes.len() - offset < length {
            let mut chunk = vec![0; (length - (bytes.len() - offset)).min(4096)];
            match socket.read(&mut chunk) {
                Ok(0) => break,
                Ok(n) => bytes.extend_from_slice(&chunk[..n]),
                Err(e) => {
                    error = Some(format!("{:?}", e.kind()));
                    break;
                }
            }
        }
    }
    std::fs::write(log.with_extension("bytes"), &bytes).unwrap();
    std::fs::write(log.with_extension("json"),json!({"handshake_error":handshake_error,"stage":log.file_name().unwrap().to_string_lossy(),"method":method,"path":path,"truncate":truncate,"header":split.map(|n|String::from_utf8_lossy(&bytes[..n]).into_owned()),"declared_body":declared,"received_body":split.map(|n|bytes.len()-n),"received":bytes.len(),"error":error}).to_string()).unwrap();
    assert!(
        handshake_error.is_none(),
        "post-route gate: {method} {path} stage={} error={handshake_error:?}; raw bytes saved",
        log.display()
    );
    if truncate {
        let split = bytes
            .windows(4)
            .position(|w| w == b"\r\n\r\n")
            .expect("complete headers");
        let header = std::str::from_utf8(&bytes[..split]).unwrap();
        let expected_status = if matches!(
            log.file_name().unwrap().to_str(),
            Some("damaged-result" | "wrong-reference-result")
        ) {
            503
        } else {
            match method {
                "POST" => 201,
                "PUT" => 202,
                _ => 200,
            }
        };
        assert_eq!(
            header
                .lines()
                .next()
                .unwrap()
                .split_whitespace()
                .nth(1)
                .unwrap()
                .parse::<u16>()
                .unwrap(),
            expected_status,
            "{}",
            log.display()
        );
        let length = header
            .lines()
            .find_map(|line| {
                let (k, v) = line.split_once(':')?;
                k.eq_ignore_ascii_case("content-length")
                    .then(|| v.trim().parse::<usize>().unwrap())
            })
            .unwrap();
        assert!(
            bytes.len() - split - 4 > 0 && bytes.len() - split - 4 < length,
            "response must remain incomplete"
        );
    } else {
        assert!(bytes.is_empty());
    }
}

fn submit(
    service: &AnalysisHttpService,
    addr: SocketAddr,
    token: &str,
    command: Value,
    entered: &mpsc::Receiver<()>,
    release: &mpsc::Sender<()>,
) -> (String, Value) {
    let (status, allocation) = request(
        addr,
        token,
        "POST",
        "/api/analysis-operations",
        json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
    );
    assert_eq!(status, 201);
    let path = format!(
        "/api/analysis-operations/{}",
        allocation["operation_id"].as_str().unwrap()
    );
    assert_eq!(request(addr, token, "PUT", &path, command).0, 202);
    entered.recv_timeout(Duration::from_secs(12)).unwrap();
    release.send(()).unwrap();
    for handle in service.background.lock().unwrap().drain(..) {
        handle.join().unwrap();
    }
    let saved = request(addr, token, "GET", &path, Value::Null);
    assert_eq!(saved.0, 200);
    (path, saved.1)
}

#[test]
fn response_loss_preserves_allocation_accepting_cancellation_and_reads() {
    for truncate in [false, true] {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h322a-response-loss-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let drafts = Arc::new(drafts);
        let store = root.join("store");
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(store.clone()).unwrap());
        let (entered_tx, entered) = mpsc::sync_channel(1);
        let (release, release_rx) = mpsc::channel();
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context: AnalysisOperationContext {
                scoring: Default::default(),
                default_catalog_id: catalog,
                configuration_sha256: "a".repeat(64),
            },
            drafts,
            snapshots,
            engine,
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            freeze_gate: None,
            freeze_control: Some((entered_tx, Mutex::new(release_rx))),
            response_fault: Mutex::new(None),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
        });
        let mut cfg = WorkbenchConfig::local_default();
        cfg.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(cfg).unwrap();
        server.analysis = Some(service.clone());
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let server_thread = thread::spawn(move || server.serve_until(&stopping).unwrap());
        let allocate = json!({"schema_version":1,"kind":"analysis_operation_allocate"});
        lose(
            &service,
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            allocate,
            truncate,
            &root.join("allocation"),
            || {
                assert_eq!(
                    std::fs::read_dir(store.join("operations")).unwrap().count(),
                    1
                );
                assert!(coordinator.snapshot().unwrap().queued.is_none());
                assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            },
        );
        // This ID is recovered only by the test, never a client discovery feature.
        let id = std::fs::read_dir(store.join("operations"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .file_name()
            .into_string()
            .unwrap();
        let op_path = format!("/api/analysis-operations/{id}");
        assert_eq!(
            request(addr, &token, "GET", &op_path, Value::Null).1["state"],
            "allocated"
        );
        let command = json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()});
        let release_after_loss = ReleaseFreeze(release.clone());
        lose(
            &service,
            addr,
            &token,
            "PUT",
            &op_path,
            command.clone(),
            truncate,
            &root.join("accepting"),
            || {
                entered.recv_timeout(Duration::from_secs(12)).unwrap();
                assert_eq!(
                    request(addr, &token, "GET", &op_path, Value::Null).1["state"],
                    "accepting"
                );
                assert_eq!(
                    request(addr, &token, "PUT", &op_path, command.clone()).0,
                    202
                );
                let mut changed = command.clone();
                changed["seed"] = 2.into();
                assert_eq!(request(addr, &token, "PUT", &op_path, changed).0, 409);
                let spare = request(
                    addr,
                    &token,
                    "POST",
                    "/api/analysis-operations",
                    json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
                )
                .1;
                let spare_path = format!(
                    "/api/analysis-operations/{}",
                    spare["operation_id"].as_str().unwrap()
                );
                assert_eq!(
                    request(addr, &token, "PUT", &spare_path, command.clone()).0,
                    409
                );
                assert_eq!(coordinator.freeze_attempts_for_test(), 0);
            },
        );
        // The client has observed the missing/incomplete response while freezing
        // is still blocked. Closing that connection cannot cancel accepted work.
        assert_eq!(
            request(addr, &token, "GET", &op_path, Value::Null).1["state"],
            "accepting"
        );
        drop(release_after_loss);
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        assert_eq!(coordinator.freeze_attempts_for_test(), 1);
        let accepted = request(addr, &token, "GET", &op_path, Value::Null).1;
        assert_eq!(accepted["state"], "accepted");
        let job_path = format!(
            "/api/analysis-jobs/{}",
            accepted["job_id"].as_str().unwrap()
        );
        for path in [&op_path, &job_path] {
            let before = snapshot(&store);
            lose(
                &service,
                addr,
                &token,
                "GET",
                path,
                Value::Null,
                truncate,
                &root.join(if path == &op_path {
                    "operation-get"
                } else {
                    "job-get"
                }),
                || {},
            );
            assert_eq!(request(addr, &token, "GET", path, Value::Null).0, 200);
            assert_eq!(snapshot(&store), before);
        }
        lose(
            &service,
            addr,
            &token,
            "DELETE",
            &job_path,
            json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1}),
            truncate,
            &root.join("cancel"),
            || {
                assert_eq!(
                    request(addr, &token, "GET", &job_path, Value::Null).1["state"],
                    "cancelled"
                );
                assert_eq!(
                    request(addr, &token, "GET", &job_path, Value::Null).1["revision"],
                    2
                );
            },
        );
        let before = snapshot(&store);
        assert_eq!(
            request(
                addr,
                &token,
                "DELETE",
                &job_path,
                json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":2})
            )
            .0,
            409
        );
        assert_eq!(snapshot(&store), before);
        assert!(coordinator
            .claim_next(super::now().unwrap())
            .unwrap()
            .is_none());

        // The closed submitting connection does not cancel preparation failure.
        let allocation = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .1;
        let rejected_path = format!(
            "/api/analysis-operations/{}",
            allocation["operation_id"].as_str().unwrap()
        );
        let mut invalid = command.clone();
        invalid["draft_revision"] = json!("0".repeat(64));
        let release_after_loss = ReleaseFreeze(release.clone());
        lose(
            &service,
            addr,
            &token,
            "PUT",
            &rejected_path,
            invalid,
            truncate,
            &root.join("rejected-submit"),
            || {
                entered.recv_timeout(Duration::from_secs(12)).unwrap();
                assert_eq!(
                    request(addr, &token, "GET", &rejected_path, Value::Null).1["state"],
                    "accepting"
                );
            },
        );
        // The client has observed the missing/incomplete response while freezing
        // is still blocked. Closing that connection cannot cancel accepted work.
        assert_eq!(
            request(addr, &token, "GET", &rejected_path, Value::Null).1["state"],
            "accepting"
        );
        drop(release_after_loss);
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        assert_eq!(
            request(addr, &token, "GET", &rejected_path, Value::Null).1["state"],
            "rejected"
        );
        assert_eq!(coordinator.freeze_attempts_for_test(), 2);

        let mut result_paths = Vec::new();
        // Reports use the actual publisher and input-bound report validator.
        for (index, termination) in ["exhausted", "node_budget"].into_iter().enumerate() {
            let (_, accepted) = submit(&service, addr, &token, command.clone(), &entered, &release);
            assert_eq!(accepted["state"], "accepted");
            let job = accepted["job_id"].as_str().unwrap();
            let ticket = coordinator
                .claim_next(super::now().unwrap())
                .unwrap()
                .unwrap();
            let frozen = ticket.input();
            let report = ygo_api::combo::AnalysisReport {
                schema_version: 2,
                request: frozen.request.clone(),
                runtime_request: frozen.runtime_request.clone(),
                search: ygo_search::combo::SearchReport {
                    termination: termination.into(),
                    lines: Vec::new(),
                    stats: Default::default(),
                    diagnostics: Vec::new(),
                    scoring: Default::default(),
                    budget: frozen.request.search.clone(),
                },
                card_names: Default::default(),
            };
            coordinator
                .publish_report(
                    &ticket,
                    &serde_json::to_vec(&report).unwrap(),
                    super::now().unwrap(),
                )
                .unwrap();
            assert_eq!(
                request(
                    addr,
                    &token,
                    "GET",
                    &format!("/api/analysis-jobs/{job}"),
                    Value::Null
                )
                .1["state"],
                if index == 0 {
                    "completed"
                } else {
                    "budget_limited"
                }
            );
            assert_eq!(
                std::fs::read_dir(store.join("reports")).unwrap().count(),
                index + 1
            );
            let result_path = format!("/api/analysis-jobs/{job}/result");
            let before = snapshot(&store);
            lose(
                &service,
                addr,
                &token,
                "GET",
                &result_path,
                Value::Null,
                truncate,
                &root.join(format!("result-{index}")),
                || {},
            );
            let result = request(addr, &token, "GET", &result_path, Value::Null);
            assert_eq!(result.0, 200, "{}", result.1);
            assert!(result.1["lines"].as_array().unwrap().is_empty());
            assert!(!result
                .1
                .to_string()
                .contains(&root.to_string_lossy().to_string()));
            assert_eq!(snapshot(&store), before);
            result_paths.push(result_path);
        }
        // Controlled stop/reopen is deliberately separate from process killing.
        let (_, running_op) = submit(&service, addr, &token, command.clone(), &entered, &release);
        let running_path = format!(
            "/api/analysis-jobs/{}",
            running_op["job_id"].as_str().unwrap()
        );
        let claimed = coordinator
            .claim_next(super::now().unwrap())
            .unwrap()
            .unwrap();
        drop(claimed);
        let (_, queued_op) = submit(&service, addr, &token, command.clone(), &entered, &release);
        let queued_path = format!(
            "/api/analysis-jobs/{}",
            queued_op["job_id"].as_str().unwrap()
        );
        assert_eq!(coordinator.freeze_attempts_for_test(), 6);
        stop.store(true, Ordering::SeqCst);
        server_thread.join().unwrap();
        let old = Arc::try_unwrap(service)
            .ok()
            .expect("server releases service");
        let AnalysisHttpService {
            context,
            drafts,
            snapshots,
            engine,
            coordinator: old_coordinator,
            ..
        } = old;
        drop(old_coordinator);
        drop(coordinator);
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert!(reopened.snapshot().unwrap().running.is_none());
        assert!(reopened.snapshot().unwrap().queued.is_none());
        drop(reopened);
        let classified = snapshot(&store);
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(store.clone()).unwrap());
        assert_eq!(
            snapshot(&store),
            classified,
            "duplicate reopen must not append"
        );
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context,
            drafts,
            snapshots,
            engine,
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            freeze_gate: None,
            freeze_control: None,
            response_fault: Mutex::new(None),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
        });
        let mut cfg = WorkbenchConfig::local_default();
        cfg.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(cfg).unwrap();
        server.analysis = Some(service.clone());
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let server_thread = thread::spawn(move || server.serve_until(&stopping).unwrap());
        for (path, state) in [(&running_path, "unknown"), (&queued_path, "interrupted")] {
            lose(
                &service,
                addr,
                &token,
                "GET",
                path,
                Value::Null,
                truncate,
                &root.join(state),
                || {},
            );
            assert_eq!(
                request(addr, &token, "GET", path, Value::Null).1["state"],
                state
            );
        }
        assert_eq!(snapshot(&store), classified);
        assert_eq!(coordinator.freeze_attempts_for_test(), 0);
        // Stopping dispatch still permits authenticated historical result reads.
        coordinator.stop_dispatch().unwrap();
        let before = snapshot(&store);
        lose(
            &service,
            addr,
            &token,
            "GET",
            &result_paths[0],
            Value::Null,
            truncate,
            &root.join("stopped-result"),
            || {},
        );
        assert_eq!(
            request(addr, &token, "GET", &result_paths[0], Value::Null).0,
            200
        );
        assert_eq!(snapshot(&store), before);
        // A saved-byte change must never fall back to cached success.
        let report = std::fs::read_dir(store.join("reports"))
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .path();
        let saved_report = std::fs::read(&report).unwrap();
        std::fs::write(&report, b"{}").unwrap();
        let before = snapshot(&store);
        let damaged = result_paths
            .iter()
            .find(|path| request(addr, &token, "GET", path, Value::Null).0 == 503)
            .unwrap();
        lose(
            &service,
            addr,
            &token,
            "GET",
            damaged,
            Value::Null,
            truncate,
            &root.join("damaged-result"),
            || {},
        );
        assert_eq!(request(addr, &token, "GET", damaged, Value::Null).0, 503);
        assert_eq!(snapshot(&store), before);
        // Restore the synthetic report, then independently corrupt its saved
        // reference while retaining a structurally valid revision envelope.
        std::fs::write(&report, saved_report).unwrap();
        let first_job = result_paths[0].split('/').nth(3).unwrap();
        let revision_path = store.join("jobs").join(first_job).join("revisions/3.json");
        let mut envelope: Value =
            serde_json::from_slice(&std::fs::read(&revision_path).unwrap()).unwrap();
        envelope["record"]["report"]["sha256"] = "0".repeat(64).into();
        let rebound = crate::workbench_analysis::jobs::AnalysisJobRecordV1::read_json(
            &serde_json::to_vec(&envelope["record"]).unwrap(),
        )
        .unwrap();
        envelope["record_sha256"] = ygo_storage::hash(&rebound.encode_json().unwrap()).into();
        std::fs::write(&revision_path, serde_json::to_vec(&envelope).unwrap()).unwrap();
        let before = snapshot(&store);
        lose(
            &service,
            addr,
            &token,
            "GET",
            &result_paths[0],
            Value::Null,
            truncate,
            &root.join("wrong-reference-result"),
            || {},
        );
        assert_eq!(
            request(addr, &token, "GET", &result_paths[0], Value::Null).0,
            503
        );
        assert_eq!(snapshot(&store), before);
        std::fs::write(root.join("matrix.json"),serde_json::to_vec_pretty(&json!({
            "mode":if truncate {"partial_body"} else {"zero_bytes"},
            "cases":[
                {"case":"allocation","expected_status":201,"freeze":0,"execution":0,"report":0,"revisions":"allocated only","readonly":false},
                {"case":"accepting_duplicate","expected_status":202,"freeze":1,"execution":0,"revisions":"accepted once","readonly":false},
                {"case":"different_instruction","expected_status":409,"freeze":0,"execution":0,"revisions":"unchanged","readonly":true},
                {"case":"cancel","expected_status":200,"execution":0,"revisions":"cancelled once","readonly":false},
                {"case":"backend_rejected","expected_status":202,"freeze":1,"execution":0,"revisions":"rejected","readonly":false},
                {"case":"completed_empty_result","expected_status":200,"execution":0,"report":1,"revisions":"unchanged by GET","readonly":true},
                {"case":"budget_limited_empty_result","expected_status":200,"execution":0,"report":1,"revisions":"unchanged by GET","readonly":true},
                {"case":"controlled_reopen","expected_status":200,"freeze":0,"execution":0,"revisions":"queued interrupted;running unknown;repeat unchanged","readonly":true},
                {"case":"stopped_history","expected_status":200,"execution":0,"revisions":"unchanged","readonly":true},
                {"case":"wrong_report_reference","expected_status":503,"execution":0,"revisions":"unchanged","readonly":true},
                {"case":"damaged_report","expected_status":503,"execution":0,"revisions":"unchanged","readonly":true}
            ],"synthetic_only":true,"native_calls":0,"execution_count_meaning":"real engine/worker executions; reports are constructed synthetic publisher inputs","result":"passed"
        })).unwrap()).unwrap();
        stop.store(true, Ordering::SeqCst);
        server_thread.join().unwrap();
    }
}
