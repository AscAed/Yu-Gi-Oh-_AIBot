//! HTTP orchestration only; there is deliberately no production analysis executor.
use super::{json_response, HttpRequest, HttpResponse};
use crate::workbench_analysis::{
    durable::{DurableAnalysisCoordinator, DurableCoordinatorError},
    http_contract as wire,
    operations::{AnalysisOperationContext, AnalysisOperationRecordV1, AnalysisOperationState},
};
use serde_json::Value;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread::JoinHandle;
use ygo_engine_adapter::ProcessEngineConfig;
use ygo_storage::{DeckDraftStore, SnapshotStore};

pub(super) struct AnalysisHttpService {
    pub(super) coordinator: Arc<DurableAnalysisCoordinator>,
    pub(super) context: AnalysisOperationContext,
    pub(super) drafts: Arc<DeckDraftStore>,
    pub(super) snapshots: SnapshotStore,
    pub(super) engine: ProcessEngineConfig,
    #[cfg(test)]
    freeze_gate: Option<(Arc<std::sync::Barrier>, Arc<std::sync::Barrier>)>,
    accepting: AtomicBool,
    background: Mutex<Vec<JoinHandle<()>>>,
}

fn now() -> Result<u64, &'static str> {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .ok()
        .and_then(|x| u64::try_from(x.as_millis()).ok())
        .ok_or("analysis_clock_invalid")
}
fn failure(status: u16, code: &str, op: Option<&str>, job: Option<&str>) -> (u16, Value) {
    (status, wire::api_error(code, op, job))
}
fn map_error(e: DurableCoordinatorError) -> (u16, Value) {
    let (status, code) = match e {
        DurableCoordinatorError::Stopped => (503, "analysis_coordinator_stopped"),
        DurableCoordinatorError::Operation(
            crate::workbench_analysis::operations::AnalysisOperationError::Conflict,
        ) => (409, "analysis_operation_conflict"),
        DurableCoordinatorError::Queue(crate::workbench_analysis::queue::QueueError::NotFound) => {
            (409, "job_terminal")
        }
        DurableCoordinatorError::Queue(
            crate::workbench_analysis::queue::QueueError::LockUnavailable
            | crate::workbench_analysis::queue::QueueError::IdUnavailable,
        ) => (503, "analysis_store_unverifiable"),
        DurableCoordinatorError::Queue(q) => (409, q.code()),
        DurableCoordinatorError::Persistence(
            crate::workbench_analysis::persistence::PersistenceError::CommitUncertain,
        ) => (503, "analysis_commit_uncertain"),
        _ => (503, "analysis_store_unverifiable"),
    };
    failure(status, code, None, None)
}
fn operation_response(op: &AnalysisOperationRecordV1) -> (u16, Value) {
    match op.state() {
        AnalysisOperationState::Accepting => (202, wire::operation_dto(op)),
        AnalysisOperationState::Rejected => {
            let r = op.rejection().expect("validated rejection");
            failure(
                r.http_status,
                &r.error_code,
                Some(op.operation_id()),
                op.job_id(),
            )
        }
        AnalysisOperationState::Unknown => failure(
            503,
            "analysis_commit_uncertain",
            Some(op.operation_id()),
            op.job_id(),
        ),
        _ => (200, wire::operation_dto(op)),
    }
}
impl AnalysisHttpService {
    pub(super) fn shutdown(&self) {
        self.accepting.store(false, Ordering::SeqCst);
        if let Ok(mut jobs) = self.background.lock() {
            for job in jobs.drain(..) {
                if job.join().is_err() {
                    let _ = self.coordinator.stop_dispatch();
                }
            }
        } else {
            let _ = self.coordinator.stop_dispatch();
        }
    }
    fn route(self: &Arc<Self>, method: &str, path: &str, body: &[u8]) -> (u16, Value) {
        let parts: Vec<_> = path.trim_start_matches('/').split('/').collect();
        let id = parts.get(2).copied();
        if id.is_some_and(|id| !wire::valid_id(id)) {
            return failure(400, "analysis_request_invalid", None, None);
        }
        if method == "GET" && !body.is_empty() {
            return failure(400, "analysis_request_invalid", None, None);
        }
        let timestamp = match if method == "GET" { Ok(0) } else { now() } {
            Ok(t) => t,
            Err(e) => return failure(503, e, None, None),
        };
        if method != "GET" && !self.accepting.load(Ordering::SeqCst) {
            return failure(503, "analysis_coordinator_stopped", None, None);
        }
        if method != "GET" && self.coordinator.is_stopped().unwrap_or(true) {
            return failure(503, "analysis_coordinator_stopped", None, None);
        }
        match (method, parts.as_slice()) {
            ("POST", ["api", "analysis-operations"]) => {
                if let Err(e) = wire::parse_allocate(body) {
                    return failure(400, e, None, None);
                }
                self.coordinator
                    .allocate_operation(self.context.clone(), timestamp)
                    .map(|op| (201, wire::operation_dto(&op)))
                    .unwrap_or_else(map_error)
            }
            ("PUT", ["api", "analysis-operations", id]) => {
                let command = match wire::parse_submit(body) {
                    Ok(c) => c,
                    Err(e) => return failure(400, e, Some(id), None),
                };
                match self.coordinator.inspect_operation_optional(id) {
                    Ok(Some(_)) => {}
                    Ok(None) => {
                        return failure(404, "analysis_operation_not_found", Some(id), None)
                    }
                    Err(e) => return map_error(e),
                }
                let accepted = match self.coordinator.begin_operation(
                    id,
                    command,
                    &self.context,
                    timestamp,
                ) {
                    Ok(a) => a,
                    Err(DurableCoordinatorError::Persistence(
                        crate::workbench_analysis::persistence::PersistenceError::RevisionConflict,
                    )) => return failure(409, "analysis_operation_conflict", Some(id), None),
                    Err(e) => return map_error(e),
                };
                if let Some(ticket) = accepted.ticket {
                    let this = self.clone();
                    // Serialize registration with shutdown; no accepted work can escape joining.
                    let mut jobs = match self.background.lock() {
                        Ok(j) => j,
                        Err(_) => {
                            let _ = self.coordinator.stop_dispatch();
                            return failure(503, "analysis_commit_uncertain", Some(id), None);
                        }
                    };
                    if !self.accepting.load(Ordering::SeqCst) {
                        let _ = self.coordinator.stop_dispatch();
                        return failure(503, "analysis_commit_uncertain", Some(id), None);
                    }
                    match std::thread::Builder::new()
                        .name("analysis-freeze".into())
                        .spawn(move || {
                            #[cfg(test)]
                            if let Some((entered, release)) = &this.freeze_gate {
                                entered.wait();
                                release.wait();
                            }
                            let result = now().map_err(|_| ()).and_then(|_t| {
                                this.coordinator
                                    .finish_operation_with_clock(
                                        ticket,
                                        || now().unwrap_or(0),
                                        &this.drafts,
                                        &this.snapshots,
                                        this.engine.clone(),
                                    )
                                    .map_err(|_| ())
                            });
                            if result.is_err() {
                                let _ = this.coordinator.stop_dispatch();
                            }
                        }) {
                        Ok(job) => jobs.push(job),
                        Err(_) => {
                            let _ = self.coordinator.stop_dispatch();
                            return failure(503, "analysis_commit_uncertain", Some(id), None);
                        }
                    }
                }
                operation_response(&accepted.record)
            }
            ("GET", ["api", "analysis-operations", id]) => {
                match self.coordinator.inspect_operation_optional(id) {
                    Ok(h) => h
                        .as_ref()
                        .map(|op| (200, wire::operation_dto(op)))
                        .unwrap_or_else(|| {
                            failure(404, "analysis_operation_not_found", Some(id), None)
                        }),
                    Err(e) => map_error(e),
                }
            }
            ("GET", ["api", "analysis-jobs", id]) => {
                match self.coordinator.inspect_job_optional(id) {
                    Ok(h) => h
                        .as_ref()
                        .map(|job| {
                            (
                                200,
                                wire::job_dto(
                                    job,
                                    if self.coordinator.is_stopped().unwrap_or(true) {
                                        "stopped"
                                    } else {
                                        "ready"
                                    },
                                ),
                            )
                        })
                        .unwrap_or_else(|| failure(404, "job_not_found", None, Some(id))),
                    Err(e) => map_error(e),
                }
            }
            ("GET", ["api", "analysis-jobs", id, "result"]) => {
                let h = match self.coordinator.inspect_job_optional(id) {
                    Ok(h) => h,
                    Err(e) => return map_error(e),
                };
                let Some(job) = h.as_ref() else {
                    return failure(404, "job_not_found", None, Some(id));
                };
                if job.report().is_none() {
                    return failure(409, "job_result_unavailable", None, Some(id));
                }
                match self.coordinator.inspect_report(id) {
                    Ok(report) => wire::result_dto(job, &report)
                        .map(|v| (200, v))
                        .unwrap_or_else(|e| failure(503, e, None, Some(id))),
                    Err(e) => map_error(e),
                }
            }
            ("DELETE", ["api", "analysis-jobs", id]) => {
                let revision = match wire::parse_cancel(body) {
                    Ok(r) => r,
                    Err(e) => return failure(400, e, None, Some(id)),
                };
                let current = match self.coordinator.inspect_job_optional(id) {
                    Ok(Some(j)) => j,
                    Ok(None) => return failure(404, "job_not_found", None, Some(id)),
                    Err(e) => return map_error(e),
                };
                if current.revision() != revision {
                    return failure(409, "job_revision_conflict", None, Some(id));
                }
                use crate::workbench_analysis::jobs::AnalysisJobState;
                if current.state() == AnalysisJobState::Running {
                    return failure(409, "cannot_cancel_running", None, Some(id));
                }
                if current.state() != AnalysisJobState::Queued {
                    return failure(409, "job_terminal", None, Some(id));
                }
                self.coordinator
                    .cancel(id, revision, timestamp)
                    .map(|j| (200, wire::job_dto(&j, "ready")))
                    .unwrap_or_else(map_error)
            }
            _ => failure(404, "route_not_found", None, None),
        }
    }
}
pub(super) fn route(
    service: Option<&Arc<AnalysisHttpService>>,
    request: &HttpRequest,
    path: &str,
) -> HttpResponse {
    let (status, value) = match service {
        Some(s) => s.route(&request.method, path, &request.body),
        None => failure(503, "analysis_not_configured", None, None),
    };
    json_response(status, value).expect("fixed HTTP DTO encodes")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{
        workbench::{WorkbenchConfig, WorkbenchServer},
        workbench_analysis::tests::fixtures,
    };
    use std::{
        io::{Read, Write},
        net::TcpStream,
        sync::Barrier,
    };
    fn request(
        addr: std::net::SocketAddr,
        token: &str,
        method: &str,
        path: &str,
        body: Value,
    ) -> (u16, Value) {
        let body = if method == "GET" {
            String::new()
        } else {
            body.to_string()
        };
        request_raw(addr, token, method, path, &body)
    }
    fn request_raw(
        addr: std::net::SocketAddr,
        token: &str,
        method: &str,
        path: &str,
        body: &str,
    ) -> (u16, Value) {
        let mut socket = TcpStream::connect(addr).unwrap();
        socket
            .set_read_timeout(Some(std::time::Duration::from_secs(10)))
            .unwrap();
        let request = format!("{method} {path} HTTP/1.1\r\nHost: {addr}\r\nOrigin: http://{addr}\r\nAuthorization: Bearer {token}\r\nContent-Length: {}\r\n\r\n{body}",body.len());
        socket.write_all(request.as_bytes()).unwrap();
        socket
            .shutdown(std::net::Shutdown::Write)
            .expect("half-close after sending the complete request");
        // Read the framed response, not a second read waiting for TCP EOF.
        // Windows may reset a closed connection after a complete response.
        let mut header_bytes = Vec::new();
        while !header_bytes.ends_with(b"\r\n\r\n") {
            assert!(header_bytes.len() < 16 * 1024, "response headers too large");
            let mut byte = [0u8; 1];
            socket.read_exact(&mut byte).unwrap_or_else(|e| {
                panic!(
                    "{method} {path}: response header failed after {} bytes ({:?}): {e}",
                    header_bytes.len(),
                    String::from_utf8_lossy(&header_bytes)
                )
            });
            header_bytes.push(byte[0]);
        }
        let headers = std::str::from_utf8(&header_bytes).unwrap();
        let length: usize = headers
            .lines()
            .find_map(|line| {
                let (key, value) = line.split_once(':')?;
                key.eq_ignore_ascii_case("content-length")
                    .then(|| value.trim().parse().unwrap())
            })
            .expect("response content length");
        let mut body = vec![0u8; length];
        socket.read_exact(&mut body).unwrap();
        (
            headers.split_whitespace().nth(1).unwrap().parse().unwrap(),
            serde_json::from_slice(&body).unwrap(),
        )
    }
    #[test]
    fn tcp_async_submission_is_durable_idempotent_and_history_is_path_free() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22-analysis-http-tests/fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let drafts = Arc::new(drafts);
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(root.join("jobs-store")).unwrap());
        let entered = Arc::new(Barrier::new(2));
        let release = Arc::new(Barrier::new(2));
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context: AnalysisOperationContext {
                scoring: Default::default(),
                default_catalog_id: catalog,
                configuration_sha256: "a".repeat(64),
            },
            drafts: drafts.clone(),
            snapshots,
            engine,
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: Some((entered.clone(), release.clone())),
        });
        let mut config = WorkbenchConfig::local_default();
        config.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(config).unwrap();
        server.analysis = Some(service.clone());
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let server_thread = std::thread::spawn(move || server.serve_until(&stopping).unwrap());
        let allocation =
            serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"});
        let (status, op) = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            allocation.clone(),
        );
        assert_eq!(status, 201);
        let op_path = format!(
            "/api/analysis-operations/{}",
            op["operation_id"].as_str().unwrap()
        );
        assert_eq!(
            request_raw(
                addr,
                &token,
                "PUT",
                &op_path,
                r#"{"schema_version":1,"schema_version":1,"kind":"analysis_submit"}"#
            )
            .0,
            400
        );
        assert_eq!(request(addr,&token,"POST","/api/analysis-operations",serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate","extra":true})).0,400);
        assert_eq!(
            request(addr, &token, "GET", "/api/analysis-jobs/bad", Value::Null).0,
            400
        );
        assert_eq!(
            request(
                addr,
                &token,
                "GET",
                "/api/analysis-jobs/11111111111111111111111111111111",
                Value::Null
            )
            .0,
            404
        );
        assert_eq!(
            request(
                addr,
                &token,
                "GET",
                "/api/analysis-operations/11111111111111111111111111111111",
                Value::Null
            )
            .0,
            404
        );
        let cmd = serde_json::json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()});
        let (status, accepting) = request(addr, &token, "PUT", &op_path, cmd.clone());
        assert_eq!(status, 202, "{accepting}");
        entered.wait();
        assert_eq!(accepting["state"], "accepting");
        let (status, repeated) = request(addr, &token, "PUT", &op_path, cmd.clone());
        assert_eq!(status, 202);
        assert_eq!(accepting, repeated);
        let mut changed = cmd.clone();
        changed["seed"] = 2.into();
        assert_eq!(request(addr, &token, "PUT", &op_path, changed).0, 409);
        let second = request(addr, &token, "POST", "/api/analysis-operations", allocation).1;
        let second_path = format!(
            "/api/analysis-operations/{}",
            second["operation_id"].as_str().unwrap()
        );
        assert_eq!(
            request(addr, &token, "PUT", &second_path, cmd.clone()).0,
            409
        );
        release.wait();
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        let accepted = request(addr, &token, "GET", &op_path, Value::Null).1;
        assert_eq!(accepted["state"], "accepted");
        let job_id = accepted["job_id"].as_str().unwrap();
        let job_path = format!("/api/analysis-jobs/{job_id}");
        let (status, queued) = request(addr, &token, "GET", &job_path, Value::Null);
        assert_eq!(status, 200);
        assert_eq!(queued["state"], "queued");
        assert_eq!(
            request(
                addr,
                &token,
                "GET",
                &format!("{job_path}/result"),
                Value::Null
            )
            .0,
            409
        );
        let ticket = coordinator.claim_next(now().unwrap()).unwrap().unwrap();
        assert_eq!(request(addr,&token,"DELETE",&job_path,serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":2})).0,409);
        let spare = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .1;
        let spare_path = format!(
            "/api/analysis-operations/{}",
            spare["operation_id"].as_str().unwrap()
        );
        assert_eq!(request(addr, &token, "PUT", &spare_path, cmd).0, 202);
        entered.wait();
        release.wait();
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        let spare = request(addr, &token, "GET", &spare_path, Value::Null).1;
        let spare_job = format!("/api/analysis-jobs/{}", spare["job_id"].as_str().unwrap());
        coordinator.inject_failure_before_next_publish();
        let failed_cancel = request(
            addr,
            &token,
            "DELETE",
            &spare_job,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1}),
        );
        assert_eq!(failed_cancel.0, 503);
        assert_eq!(
            failed_cancel.1["error"]["code"],
            "analysis_store_unverifiable"
        );
        let queued_after_failed_cancel = request(addr, &token, "GET", &spare_job, Value::Null);
        assert_eq!(queued_after_failed_cancel.1["state"], "queued");
        let cancelled = request(
            addr,
            &token,
            "DELETE",
            &spare_job,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1}),
        );
        assert_eq!(cancelled.0, 200);
        assert_eq!(cancelled.1["state"], "cancelled");
        assert!(coordinator.claim_next(now().unwrap()).unwrap().is_none());
        assert_eq!(request(addr,&token,"DELETE",&spare_job,serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":2})).0,409);
        let terminal_cancel = request(
            addr,
            &token,
            "DELETE",
            &spare_job,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":2}),
        );
        assert_eq!(terminal_cancel.1["error"]["code"], "job_terminal");
        let running_cancel = request(
            addr,
            &token,
            "DELETE",
            &job_path,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":2}),
        );
        assert_eq!(running_cancel.1["error"]["code"], "cannot_cancel_running");

        // Race the HTTP cancellation path against the coordinator's claim path.
        // Exactly one transition can win while both observe the same queued revision.
        let race_op = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .1;
        let race_op_path = format!(
            "/api/analysis-operations/{}",
            race_op["operation_id"].as_str().unwrap()
        );
        assert_eq!(request(addr, &token, "PUT", &race_op_path, serde_json::json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()})).0, 202);
        entered.wait();
        release.wait();
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        let race_record = request(addr, &token, "GET", &race_op_path, Value::Null).1;
        let race_job_id = race_record["job_id"].as_str().unwrap();
        let race_job_path = format!("/api/analysis-jobs/{race_job_id}");
        let barrier = Arc::new(Barrier::new(3));
        let claim_coordinator = coordinator.clone();
        let claim_barrier = barrier.clone();
        let claim = std::thread::spawn(move || {
            claim_barrier.wait();
            claim_coordinator.claim_next(now().unwrap()).unwrap()
        });
        let cancel_barrier = barrier.clone();
        let cancel_token = token.clone();
        let cancel = std::thread::spawn(move || {
            cancel_barrier.wait();
            request(
                addr,
                &cancel_token,
                "DELETE",
                &race_job_path,
                serde_json::json!({
                    "schema_version": 1,
                    "kind": "analysis_cancel",
                    "expected_revision": 1
                }),
            )
        });
        barrier.wait();
        let claim_result = claim.join().unwrap();
        let cancel_result = cancel.join().unwrap();
        match (claim_result, cancel_result.0) {
            (None, 200) => assert_eq!(cancel_result.1["state"], "cancelled"),
            (Some(record), 409) => {
                assert_eq!(record.record().state(), crate::workbench_analysis::jobs::AnalysisJobState::Running);
                assert_eq!(cancel_result.1["error"]["code"], "job_revision_conflict");
            }
            (claim, status) => panic!("non-linearizable cancel/claim outcome: {claim:?}, {cancel_result:?}; status={status}"),
        }

        let frozen = ticket.input();
        let report = ygo_api::combo::AnalysisReport {
            schema_version: 2,
            request: frozen.request.clone(),
            runtime_request: frozen.runtime_request.clone(),
            search: ygo_search::combo::SearchReport {
                termination: "exhausted".into(),
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
                now().unwrap(),
            )
            .unwrap();
        let (status, result) = request(
            addr,
            &token,
            "GET",
            &format!("{job_path}/result"),
            Value::Null,
        );
        assert_eq!(status, 200, "{result}");
        assert!(result["lines"].as_array().unwrap().is_empty());
        assert!(!result
            .to_string()
            .contains(&root.to_string_lossy().to_string()));
        assert!(result.get("runtime_request").is_none());
        assert_eq!(
            request_raw(addr, &token, "GET", &format!("{job_path}/result"), "{}").0,
            400
        );
        coordinator.stop_dispatch().unwrap();
        let stopped = request(addr, &token, "GET", &job_path, Value::Null).1;
        assert_eq!(stopped["service_state"], "stopped");
        assert_eq!(
            request(
                addr,
                &token,
                "GET",
                &format!("{job_path}/result"),
                Value::Null
            )
            .0,
            200
        );
        stop.store(true, Ordering::SeqCst);
        server_thread.join().unwrap();
    }

    #[test]
    fn operation_store_failure_is_reported_without_inventing_a_job() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22-analysis-http-tests/fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        let saved = drafts.create(draft.clone()).unwrap();
        let drafts = Arc::new(drafts);
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(root.join("jobs-store")).unwrap());
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
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
        });
        let mut config = WorkbenchConfig::local_default();
        config.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(config).unwrap();
        server.analysis = Some(service.clone());
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let server_thread = std::thread::spawn(move || server.serve_until(&stopping).unwrap());

        let operation = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .1;
        let operation_path = format!(
            "/api/analysis-operations/{}",
            operation["operation_id"].as_str().unwrap()
        );
        let command = serde_json::json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()});

        coordinator.inject_operation_failure_before_next_publish();
        let failed = request(addr, &token, "PUT", &operation_path, command);
        assert_eq!(failed.0, 503);
        assert_eq!(failed.1["error"]["code"], "analysis_store_unverifiable");
        let unchanged = request(addr, &token, "GET", &operation_path, Value::Null);
        assert_eq!(unchanged.1["state"], "allocated");
        assert!(unchanged.1["job_id"].is_null());
        assert!(service.background.lock().unwrap().is_empty());
        stop.store(true, Ordering::SeqCst);
        server_thread.join().unwrap();
    }

    #[test]
    fn stale_draft_revision_is_saved_as_a_repeatable_http_rejection() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22-analysis-http-tests/fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        let saved = drafts.create(draft.clone()).unwrap();
        let drafts = Arc::new(drafts);
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(root.join("jobs-store")).unwrap());
        let entered = Arc::new(Barrier::new(2));
        let release = Arc::new(Barrier::new(2));
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context: AnalysisOperationContext {
                scoring: Default::default(),
                default_catalog_id: catalog,
                configuration_sha256: "a".repeat(64),
            },
            drafts: drafts.clone(),
            snapshots,
            engine,
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: Some((entered.clone(), release.clone())),
        });
        let mut config = WorkbenchConfig::local_default();
        config.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(config).unwrap();
        server.analysis = Some(service.clone());
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let server_thread = std::thread::spawn(move || server.serve_until(&stopping).unwrap());

        let operation = request(
            addr,
            &token,
            "POST",
            "/api/analysis-operations",
            serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .1;
        let operation_path = format!(
            "/api/analysis-operations/{}",
            operation["operation_id"].as_str().unwrap()
        );
        let command = serde_json::json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()});
        let (status, accepting) = request(addr, &token, "PUT", &operation_path, command.clone());
        assert_eq!(status, 202);
        entered.wait();

        let mut edited = saved.draft.clone();
        edited.title = "changed while freeze pending".into();
        let updated = drafts.update(&saved.id, &saved.revision, edited).unwrap();
        assert_ne!(updated.revision, saved.revision);
        release.wait();
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }

        let rejected = request(addr, &token, "GET", &operation_path, Value::Null).1;
        assert_eq!(rejected["state"], "rejected");
        assert_eq!(rejected["error_code"], "revision_conflict");
        let replayed = request(addr, &token, "PUT", &operation_path, command);
        assert_eq!(replayed.0, 409);
        assert_eq!(replayed.1["error"]["code"], "revision_conflict");
        let missing_job = request(
            addr,
            &token,
            "GET",
            &format!(
                "/api/analysis-jobs/{}",
                accepting["job_id"].as_str().unwrap()
            ),
            Value::Null,
        );
        assert_eq!(missing_job.0, 404);
        stop.store(true, Ordering::SeqCst);
        server_thread.join().unwrap();
    }
}
