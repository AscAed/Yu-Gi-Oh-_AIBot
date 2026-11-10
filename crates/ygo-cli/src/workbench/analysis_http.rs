//! HTTP orchestration with a production executor enabled only by explicit configuration.
#[cfg(test)]
#[path = "fault_matrix_tests.rs"]
mod fault_matrix_tests;
#[cfg(test)]
#[path = "response_loss_tests.rs"]
mod response_loss_tests;
use super::{json_response, HttpRequest, HttpResponse};
#[cfg(test)]
use crate::workbench_analysis::AttemptReceiptContextV1;
use crate::workbench_analysis::{
    durable::{DurableAnalysisCoordinator, DurableCoordinatorError},
    http_contract as wire,
    operations::{
        AnalysisOperationContext, AnalysisOperationError, AnalysisOperationRecordV1,
        AnalysisOperationState,
    },
    AttemptReceiptEventV1, FrozenAnalysisInput, W1cAdmission,
};
use serde_json::Value;
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread::JoinHandle;
use ygo_api::combo::AnalysisReport;
use ygo_engine_adapter::{ProcessEngineAdapter, ProcessEngineConfig};
use ygo_search::combo::{ScoringConfig, SearchAttemptJournalEvent, SearchAttemptObservation};
use ygo_storage::{DeckDraftStore, SnapshotStore};

pub(super) trait AttemptJournalSink {
    fn record(&mut self, event: SearchAttemptJournalEvent) -> Result<(), String>;
}

impl<F> AttemptJournalSink for F
where
    F: FnMut(SearchAttemptJournalEvent) -> Result<(), String>,
{
    fn record(&mut self, event: SearchAttemptJournalEvent) -> Result<(), String> {
        self(event)
    }
}

pub(super) type AnalysisExecutor = Arc<
    dyn Fn(
            &FrozenAnalysisInput,
            &ScoringConfig,
            &mut dyn AttemptJournalSink,
        ) -> Result<AnalysisExecution, AnalysisExecutionFailure>
        + Send
        + Sync,
>;

pub(super) struct AnalysisExecution {
    pub(super) report: AnalysisReport,
    pub(super) attempt_observations: Vec<SearchAttemptObservation>,
}

impl AnalysisExecution {
    #[cfg(test)]
    fn report_only(report: AnalysisReport) -> Self {
        Self {
            report,
            attempt_observations: Vec::new(),
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub(super) enum AnalysisExecutionFailure {
    BeforeExecution,
    UncertainWithObservations(Vec<SearchAttemptObservation>),
}

#[cfg(test)]
type FreezeControl = (
    std::sync::mpsc::SyncSender<()>,
    Mutex<std::sync::mpsc::Receiver<()>>,
);

pub(super) struct AnalysisHttpService {
    pub(super) coordinator: Arc<DurableAnalysisCoordinator>,
    pub(super) context: AnalysisOperationContext,
    pub(super) drafts: Arc<DeckDraftStore>,
    pub(super) snapshots: SnapshotStore,
    pub(super) engine: ProcessEngineConfig,
    admission: Option<Arc<W1cAdmission>>,
    executor: Option<AnalysisExecutor>,
    dispatch_lock: Mutex<()>,
    #[cfg(test)]
    freeze_gate: Option<(Arc<std::sync::Barrier>, Arc<std::sync::Barrier>)>,
    #[cfg(test)]
    pub(super) response_fault: Mutex<Option<super::response_loss::ResponseFault>>,
    #[cfg(test)]
    freeze_control: Option<FreezeControl>,
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
    pub(super) fn open(
        store_dir: std::path::PathBuf,
        context: AnalysisOperationContext,
        drafts: Arc<DeckDraftStore>,
        snapshots: SnapshotStore,
        engine: ProcessEngineConfig,
        admission: Option<Arc<W1cAdmission>>,
    ) -> Result<Self, String> {
        let coordinator = DurableAnalysisCoordinator::open_operations(store_dir)
            .map_err(|error| format!("analysis_store_open_failed: {}", error.code()))?;
        Ok(Self {
            coordinator: Arc::new(coordinator),
            context,
            drafts,
            snapshots,
            engine,
            admission,
            executor: Some(process_analysis_executor()),
            dispatch_lock: Mutex::new(()),
            #[cfg(test)]
            freeze_gate: None,
            #[cfg(test)]
            response_fault: Mutex::new(None),
            #[cfg(test)]
            freeze_control: None,
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
        })
    }

    fn admission(&self) -> Option<&Arc<W1cAdmission>> {
        self.admission.as_ref()
    }

    pub(super) fn dispatch_pending(&self) -> Result<(), DurableCoordinatorError> {
        let Some(executor) = self.executor.as_ref() else {
            return Ok(());
        };
        let _dispatch = self
            .dispatch_lock
            .lock()
            .map_err(|_| DurableCoordinatorError::LockUnavailable)?;
        let ticket = self.coordinator.claim_next(durable_now()?)?;
        let Some(ticket) = ticket else {
            return Ok(());
        };
        if self.admission().is_some_and(|admission| {
            !admission.matches_frozen(ticket.input()) || admission.verify_package_files().is_err()
        }) {
            let settlement = self
                .coordinator
                .fail_asset_mismatch(&ticket, durable_now()?);
            let _ = self.coordinator.stop_dispatch();
            settlement?;
            return Err(DurableCoordinatorError::AssetMismatch);
        }
        #[cfg(test)]
        tests::ticket_return_checkpoint(&ticket);
        let receipt_context = match self.coordinator.attempt_receipt_context(&ticket) {
            Ok(context) => context,
            Err(error) => {
                let _ = self.coordinator.stop_dispatch();
                return Err(error);
            }
        };
        let mut journal = |event: SearchAttemptJournalEvent| {
            let event =
                AttemptReceiptEventV1::try_from(event).map_err(|error| error.code().to_owned())?;
            self.coordinator
                .append_attempt_receipt(&ticket, &receipt_context, event.clone())
                .map_err(|error| error.code().to_owned())?;
            #[cfg(test)]
            if matches!(&event, AttemptReceiptEventV1::Started { .. }) {
                tests::attempt_start_checkpoint(&ticket, &receipt_context, &event);
            }
            Ok(())
        };
        let outcome = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            executor(ticket.input(), &self.context.scoring, &mut journal)
        }));
        #[cfg(test)]
        tests::executor_return_checkpoint(&ticket, &outcome);
        match outcome {
            Ok(Ok(execution)) => {
                // Keep the observations alongside report publication. This
                // batch collects them in memory; durable receipt publication
                // remains a separate gate, so they never enter this report's
                // JSON contract.
                let AnalysisExecution {
                    report,
                    attempt_observations: _attempt_observations,
                } = execution;
                let bytes = match serde_json::to_vec(&report) {
                    Ok(bytes) => bytes,
                    Err(_) => {
                        self.mark_unknown(&ticket)?;
                        return Ok(());
                    }
                };
                let timestamp = self.completion_timestamp()?;
                if let Err(error) = self.coordinator.publish_report(&ticket, &bytes, timestamp) {
                    let _ = self.coordinator.stop_dispatch();
                    return Err(error);
                }
                Ok(())
            }
            Ok(Err(AnalysisExecutionFailure::BeforeExecution)) => {
                let timestamp = self.completion_timestamp()?;
                if let Err(error) = self.coordinator.fail(&ticket, timestamp) {
                    let _ = self.coordinator.stop_dispatch();
                    return Err(error);
                }
                Ok(())
            }
            Ok(Err(AnalysisExecutionFailure::UncertainWithObservations(attempt_observations))) => {
                self.mark_unknown(&ticket)?;
                drop(attempt_observations);
                Ok(())
            }
            Err(_) => {
                self.mark_unknown(&ticket)?;
                Ok(())
            }
        }
    }

    fn completion_timestamp(&self) -> Result<u64, DurableCoordinatorError> {
        match durable_now() {
            Ok(timestamp) => Ok(timestamp),
            Err(error) => {
                let _ = self.coordinator.stop_dispatch();
                Err(error)
            }
        }
    }

    fn mark_unknown(
        &self,
        ticket: &crate::workbench_analysis::queue::DispatchTicket,
    ) -> Result<(), DurableCoordinatorError> {
        let timestamp = match durable_now() {
            Ok(timestamp) => timestamp,
            Err(error) => {
                let _ = self.coordinator.stop_dispatch();
                return Err(error);
            }
        };
        self.coordinator.mark_unknown(ticket, timestamp).map(|_| ())
    }

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
                let existing = match self.coordinator.inspect_operation_optional(id) {
                    Ok(Some(op)) => op,
                    Ok(None) => {
                        return failure(404, "analysis_operation_not_found", Some(id), None)
                    }
                    Err(e) => return map_error(e),
                };
                if existing.state() == AnalysisOperationState::Allocated
                    && self
                        .admission()
                        .is_some_and(|admission| !admission.matches_command(&command))
                {
                    return failure(422, "analysis_profile_mismatch", Some(id), None);
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
                            #[cfg(test)]
                            if let Some((entered, release)) = &this.freeze_control {
                                let ready = entered.try_send(()).is_ok()
                                    && release.lock().is_ok_and(|rx| {
                                        rx.recv_timeout(std::time::Duration::from_secs(10)).is_ok()
                                    });
                                if !ready {
                                    let _ = this.coordinator.stop_dispatch();
                                    return;
                                }
                            }
                            let admission = this.admission().cloned();
                            let result = now().map_err(|_| ()).and_then(|_t| {
                                if let Some(admission) = admission {
                                    this.coordinator.finish_operation_with_clock_and_validator(
                                        ticket,
                                        || now().unwrap_or(0),
                                        &this.drafts,
                                        &this.snapshots,
                                        this.engine.clone(),
                                        move |input| admission.matches_frozen(input),
                                    )
                                } else {
                                    this.coordinator.finish_operation_with_clock(
                                        ticket,
                                        || now().unwrap_or(0),
                                        &this.drafts,
                                        &this.snapshots,
                                        this.engine.clone(),
                                    )
                                }
                                .map_err(|_| ())
                            });
                            match result {
                                Ok(operation)
                                    if operation.state() == AnalysisOperationState::Accepted
                                        && this.executor.is_some() =>
                                {
                                    if this.dispatch_pending().is_err() {
                                        let _ = this.coordinator.stop_dispatch();
                                    }
                                }
                                Ok(_) => {}
                                Err(_) => {
                                    let _ = this.coordinator.stop_dispatch();
                                }
                            }
                        }) {
                        Ok(job) => {
                            jobs.retain(|handle| !handle.is_finished());
                            jobs.push(job);
                        }
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

fn durable_now() -> Result<u64, DurableCoordinatorError> {
    now().map_err(|_| DurableCoordinatorError::Operation(AnalysisOperationError::TimeInvalid))
}

fn process_analysis_executor() -> AnalysisExecutor {
    Arc::new(|input, scoring, journal| {
        input
            .request
            .search
            .validate()
            .map_err(|_| AnalysisExecutionFailure::BeforeExecution)?;
        let adapter = ProcessEngineAdapter::new(input.runtime_request.engine.clone());
        let observed = ygo_search::combo::search_with_receipts(
            &adapter,
            &input.runtime_request,
            &input.request.search,
            scoring,
            || ygo_storage::secure_random_hex(16),
            |event| journal.record(event),
        );
        let search = match observed.report {
            Ok(search) => search,
            Err(_) => {
                return Err(AnalysisExecutionFailure::UncertainWithObservations(
                    observed.attempts,
                ));
            }
        };
        let card_names = input
            .catalog
            .values()
            .filter(|card| {
                input
                    .request
                    .deck
                    .main
                    .iter()
                    .chain(&input.request.deck.extra)
                    .chain(&input.request.deck.side)
                    .any(|id| *id == card.id)
                    || search.lines.iter().any(|line| {
                        line.result
                            .checkpoint
                            .cards
                            .iter()
                            .any(|state| state.code == card.id.0)
                    })
            })
            .map(|card| (card.id.0, card.name.clone()))
            .collect();
        Ok(AnalysisExecution {
            report: AnalysisReport {
                schema_version: 2,
                request: input.request.clone(),
                runtime_request: input.runtime_request.clone(),
                search,
                card_names,
            },
            attempt_observations: observed.attempts,
        })
    })
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
    use ygo_engine_adapter::ProcessRunObservation;
    use ygo_search::combo::{
        SearchAttemptFfiDirection, SearchAttemptFfiEntry, SearchAttemptFfiReturn,
        SearchAttemptFfiReturnStatus, SearchAttemptJournalEvent, SearchAttemptPhase,
        SearchAttemptResult, SearchAttemptStart,
    };
    include!("analysis_query_fault_tests.rs");
    use crate::{
        workbench::{WorkbenchConfig, WorkbenchServer},
        workbench_analysis::tests::fixtures,
    };
    use std::{
        io::{Read, Write},
        net::TcpStream,
        sync::Barrier,
    };
    pub(super) fn request(
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
        let mut received = 0;
        while received < length {
            match socket.read(&mut body[received..]) {
                Ok(0) => panic!("{method} {path}: response body EOF after {received}/{length} bytes: {:?}", &body[..received]),
                Ok(count) => received += count,
                Err(error) => panic!("{method} {path}: response body failed after {received}/{length} bytes: {:?}: {error}", &body[..received]),
            }
        }
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
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: Some((entered.clone(), release.clone())),
            response_fault: Mutex::new(None),
            freeze_control: None,
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
        let (status, capacity_rejection) = request(addr, &token, "PUT", &second_path, cmd.clone());
        assert_eq!(status, 409);
        assert_eq!(capacity_rejection["error"]["code"], "analysis_queue_full");
        let (status, rejected) = request(addr, &token, "GET", &second_path, Value::Null);
        assert_eq!(status, 200);
        assert_eq!(rejected["state"], "rejected");
        assert_eq!(rejected["error_code"], "analysis_queue_full");
        let (status, repeated_rejection) = request(addr, &token, "PUT", &second_path, cmd.clone());
        assert_eq!(status, 409);
        assert_eq!(repeated_rejection["error"]["code"], "analysis_queue_full");
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
    fn tcp_concurrent_duplicate_submissions_share_one_acceptance_and_freeze() {
        const DUPLICATES: usize = 16;
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22b-concurrency-tests/fixtures")
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
            drafts,
            snapshots,
            engine,
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: Some((entered.clone(), release.clone())),
            response_fault: Mutex::new(None),
            freeze_control: None,
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
        let completed_handle = std::thread::spawn(|| {});
        while !completed_handle.is_finished() {
            std::thread::yield_now();
        }
        service.background.lock().unwrap().push(completed_handle);
        let command = serde_json::json!({"schema_version":1,"kind":"analysis_submit","draft_id":saved.id,"draft_revision":saved.revision,"opening_hand":draft.main[..5],"seed":1,"rules":"ocg-mr5","catalog_id":null,"banlist_id":banlist,"as_of":"2026-10-30","search":ygo_search::combo::SearchBudget::default()});
        let (status, accepting) = request(addr, &token, "PUT", &operation_path, command.clone());
        assert_eq!(status, 202);
        entered.wait();
        assert_eq!(service.background.lock().unwrap().len(), 1);
        assert_eq!(coordinator.freeze_attempts_for_test(), 0);

        let start = Arc::new(Barrier::new(DUPLICATES + 1));
        let clients: Vec<_> = (0..DUPLICATES)
            .map(|_| {
                let start = start.clone();
                let token = token.clone();
                let path = operation_path.clone();
                let body = command.clone();
                std::thread::spawn(move || {
                    start.wait();
                    request(addr, &token, "PUT", &path, body)
                })
            })
            .collect();
        start.wait();
        for client in clients {
            let (status, repeated) = client.join().unwrap();
            assert_eq!(status, 202);
            assert_eq!(repeated, accepting);
        }
        assert_eq!(service.background.lock().unwrap().len(), 1);
        assert_eq!(coordinator.freeze_attempts_for_test(), 0);

        release.wait();
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        let (status, accepted) = request(addr, &token, "GET", &operation_path, Value::Null);
        assert_eq!(status, 200);
        assert_eq!(accepted["state"], "accepted");
        assert_eq!(coordinator.freeze_attempts_for_test(), 1);
        assert_eq!(service.background.lock().unwrap().len(), 0);

        let evidence_root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22b-concurrency-tests");
        std::fs::create_dir_all(&evidence_root).unwrap();
        std::fs::write(
            evidence_root.join("concurrent-duplicate-submissions.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "duplicate_requests": DUPLICATES,
                "all_replayed_acceptance": true,
                "background_jobs": 1,
                "freeze_attempts": 1,
                "final_state": accepted["state"],
                "native_calls": 0
            }))
            .unwrap(),
        )
        .unwrap();

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
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
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
    fn w1c_profile_rejects_non_fixed_command_before_acceptance() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-admission-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        let saved = drafts.create(draft.clone()).unwrap();
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(root.join("jobs-store")).unwrap());
        let context = AnalysisOperationContext {
            scoring: Default::default(),
            default_catalog_id: catalog,
            configuration_sha256: "a".repeat(64),
        };
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context: context.clone(),
            drafts: Arc::new(drafts),
            snapshots,
            engine,
            admission: Some(Arc::new(W1cAdmission::fixture_policy())),
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
        });
        let allocated = coordinator.allocate_operation(context, 100).unwrap();
        let body = serde_json::json!({
            "schema_version":1,
            "kind":"analysis_submit",
            "draft_id":saved.id,
            "draft_revision":saved.revision,
            "opening_hand":draft.main[..5],
            "seed":1,
            "rules":"ocg-mr5",
            "catalog_id":null,
            "banlist_id":banlist,
            "as_of":"2026-10-30",
            "search":ygo_search::combo::SearchBudget::default()
        });

        let (status, result) = service.route(
            "PUT",
            &format!("/api/analysis-operations/{}", allocated.operation_id()),
            &serde_json::to_vec(&body).unwrap(),
        );

        assert_eq!(status, 422);
        assert_eq!(result["error"]["code"], "analysis_profile_mismatch");
        let latest = coordinator
            .inspect_operation(allocated.operation_id())
            .unwrap()
            .pop()
            .unwrap();
        assert_eq!(latest.state(), AnalysisOperationState::Allocated);
        assert!(latest.job_id().is_none());
        assert!(coordinator.snapshot().unwrap().queued.is_none());
        assert_eq!(coordinator.freeze_attempts_for_test(), 0);
    }

    #[test]
    fn operation_allocation_store_failure_is_reported_and_stops_acceptance() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22-analysis-http-tests/fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, _, _) = fixtures(&root);
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(root.join("jobs-store")).unwrap());
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context: AnalysisOperationContext {
                scoring: Default::default(),
                default_catalog_id: catalog,
                configuration_sha256: "a".repeat(64),
            },
            drafts: Arc::new(drafts),
            snapshots,
            engine,
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
        });

        coordinator.inject_operation_failure_before_next_publish();
        let body = serde_json::to_vec(
            &serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"}),
        )
        .unwrap();
        let (status, error) = service.route("POST", "/api/analysis-operations", &body);
        assert_eq!(status, 503);
        assert_eq!(error["error"]["code"], "analysis_store_unverifiable");
        assert!(service.background.lock().unwrap().is_empty());
        assert!(coordinator.is_stopped().unwrap());

        let (status, stopped) = service.route("POST", "/api/analysis-operations", &body);
        assert_eq!(status, 503);
        assert_eq!(stopped["error"]["code"], "analysis_coordinator_stopped");
    }

    #[test]
    fn uncertain_cancel_commit_is_reported_and_stops_further_dispatch() {
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
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
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
        assert_eq!(
            request(addr, &token, "PUT", &operation_path, command).0,
            202
        );
        for handle in service.background.lock().unwrap().drain(..) {
            handle.join().unwrap();
        }
        let accepted = request(addr, &token, "GET", &operation_path, Value::Null).1;
        assert_eq!(accepted["state"], "accepted");
        let job_path = format!(
            "/api/analysis-jobs/{}",
            accepted["job_id"].as_str().unwrap()
        );

        coordinator.inject_uncertain_after_next_publish();
        let (status, uncertain) = request(
            addr,
            &token,
            "DELETE",
            &job_path,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1}),
        );
        assert_eq!(status, 503);
        assert_eq!(uncertain["error"]["code"], "analysis_commit_uncertain");

        let (status, saved_job) = request(addr, &token, "GET", &job_path, Value::Null);
        assert_eq!(status, 200);
        assert_eq!(saved_job["state"], "cancelled");
        assert_eq!(saved_job["service_state"], "stopped");
        assert!(matches!(
            coordinator.claim_next(now().unwrap()),
            Err(DurableCoordinatorError::Stopped)
        ));
        let (status, retry) = request(
            addr,
            &token,
            "DELETE",
            &job_path,
            serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1}),
        );
        assert_eq!(status, 503);
        assert_eq!(retry["error"]["code"], "analysis_coordinator_stopped");

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
            admission: None,
            executor: None,
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: Some((entered.clone(), release.clone())),
            response_fault: Mutex::new(None),
            freeze_control: None,
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

    fn dispatch_test_service(
        root: &std::path::Path,
        executor: AnalysisExecutor,
    ) -> (
        Arc<AnalysisHttpService>,
        Arc<DurableAnalysisCoordinator>,
        crate::workbench_analysis::jobs::AnalysisJobRecordV1,
        std::path::PathBuf,
    ) {
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(root, executor);
        let record = coordinator.inspect_job(&job_id).unwrap().remove(0);
        (service, coordinator, record, store)
    }

    #[test]
    fn executor_publishes_one_durable_report_without_reexecuting_completed_work() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-dispatch-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let executor_calls = calls.clone();
        let executor: AnalysisExecutor = Arc::new(move |input, scoring, _journal| {
            executor_calls.fetch_add(1, Ordering::SeqCst);
            Ok(AnalysisExecution::report_only(
                ygo_api::combo::AnalysisReport {
                    schema_version: 2,
                    request: input.request.clone(),
                    runtime_request: input.runtime_request.clone(),
                    search: ygo_search::combo::SearchReport {
                        termination: "exhausted".into(),
                        lines: Vec::new(),
                        stats: Default::default(),
                        diagnostics: Vec::new(),
                        scoring: scoring.clone(),
                        budget: input.request.search.clone(),
                    },
                    card_names: Default::default(),
                },
            ))
        });
        let (service, coordinator, queued, _) = dispatch_test_service(&root, executor);

        service.dispatch_pending().unwrap();
        service.dispatch_pending().unwrap();

        assert_eq!(calls.load(Ordering::SeqCst), 1);
        let completed = coordinator
            .inspect_job_optional(queued.job_id())
            .unwrap()
            .unwrap();
        assert_eq!(
            completed.state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Completed
        );
        assert!(completed.report().is_some());
        assert!(coordinator.inspect_report(queued.job_id()).is_ok());
    }

    #[test]
    fn search_attempt_journal_is_job_bound_durable_and_byte_stable_on_reopen() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-attempt-journal-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "d".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |input, scoring, journal| {
            journal
                .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            let observation = SearchAttemptObservation {
                ordinal: 1,
                attempt_id: attempt_id.clone(),
                phase: SearchAttemptPhase::Initial,
                result: SearchAttemptResult::DuelResult {
                    status: ygo_engine_adapter::DuelStatus::DecisionRequired,
                },
                process_observation: ProcessRunObservation::default(),
            };
            journal
                .record(SearchAttemptJournalEvent::Finished(observation.clone()))
                .map_err(|_| {
                    AnalysisExecutionFailure::UncertainWithObservations(vec![observation.clone()])
                })?;
            Ok(AnalysisExecution {
                report: ygo_api::combo::AnalysisReport {
                    schema_version: 2,
                    request: input.request.clone(),
                    runtime_request: input.runtime_request.clone(),
                    search: ygo_search::combo::SearchReport {
                        termination: "exhausted".into(),
                        lines: Vec::new(),
                        stats: Default::default(),
                        diagnostics: Vec::new(),
                        scoring: scoring.clone(),
                        budget: input.request.search.clone(),
                    },
                    card_names: Default::default(),
                },
                attempt_observations: vec![observation],
            })
        });
        let (service, coordinator, operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        service.dispatch_pending().unwrap();

        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        let first_bytes = std::fs::read(receipt_dir.join("1.json")).unwrap();
        let second_bytes = std::fs::read(receipt_dir.join("2.json")).unwrap();
        let first: Value = serde_json::from_slice(&first_bytes).unwrap();
        let second: Value = serde_json::from_slice(&second_bytes).unwrap();
        assert_eq!(first["context"]["operation_id"], operation_id);
        assert_eq!(first["context"]["job_id"], job_id);
        assert_eq!(first["context"]["source_bundle_identity"], Value::Null);
        assert_eq!(first["context"]["build_record_identity"], Value::Null);
        assert_eq!(first["sequence"], 1);
        assert_eq!(second["sequence"], 2);
        assert_eq!(second["previous_sha256"], first["event_sha256"]);
        let completed = coordinator.inspect_job(&job_id).unwrap().pop().unwrap();
        let report_id = &completed.report().unwrap().report_id;
        let report_bytes =
            std::fs::read(store.join("reports").join(format!("{report_id}.json"))).unwrap();
        let report_value: Value = serde_json::from_slice(&report_bytes).unwrap();
        assert!(report_value.get("attempt_observations").is_none());
        assert!(report_value.get("attempts").is_none());

        drop(service);
        drop(coordinator);
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Completed
        );
        assert!(reopened.inspect_report(&job_id).is_ok());
        drop(reopened);
        let reopened_again = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            std::fs::read(receipt_dir.join("1.json")).unwrap(),
            first_bytes
        );
        assert_eq!(
            std::fs::read(receipt_dir.join("2.json")).unwrap(),
            second_bytes
        );
        drop(reopened_again);

        let mut tampered: Value = serde_json::from_slice(&first_bytes).unwrap();
        tampered["event_sha256"] = Value::String("a".repeat(64));
        std::fs::write(
            receipt_dir.join("1.json"),
            serde_json::to_vec(&tampered).unwrap(),
        )
        .unwrap();
        assert!(matches!(
            DurableAnalysisCoordinator::open_operations(store),
            Err(DurableCoordinatorError::Persistence(
                crate::workbench_analysis::persistence::PersistenceError::InvalidChain
            ))
        ));
    }

    #[test]
    fn attempt_receipt_write_failure_stops_dispatch_and_restart_keeps_unknown() {
        for (successful_receipts, after_publish, expected_adapter_calls, expected_receipt_events) in [
            (0, false, 0, 0),
            (0, true, 0, 1),
            (1, false, 1, 1),
            (1, true, 1, 2),
        ] {
            let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../target/w1c-attempt-journal-failures")
                .join(ygo_storage::secure_random_hex(16).unwrap());
            let adapter_calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
            let observed_calls = adapter_calls.clone();
            let attempt_id = if successful_receipts == 0 {
                "f".repeat(32)
            } else {
                "e".repeat(32)
            };
            let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
                journal
                    .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                        ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        phase: SearchAttemptPhase::Initial,
                    }))
                    .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
                observed_calls.fetch_add(1, Ordering::SeqCst);
                let observation = SearchAttemptObservation {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::AdapterError {
                        code: "synthetic_result".into(),
                        stage: "test".into(),
                    },
                    process_observation: ProcessRunObservation::default(),
                };
                journal
                    .record(SearchAttemptJournalEvent::Finished(observation.clone()))
                    .map_err(|_| {
                        AnalysisExecutionFailure::UncertainWithObservations(vec![
                            observation.clone()
                        ])
                    })?;
                Err(AnalysisExecutionFailure::UncertainWithObservations(vec![
                    observation,
                ]))
            });
            let (service, coordinator, _operation_id, job_id, store) =
                prepare_operation_dispatch_service(&root, executor);
            coordinator.inject_attempt_receipt_failure_after(successful_receipts, after_publish);

            assert!(service.dispatch_pending().is_err());
            assert!(coordinator.is_stopped().unwrap());
            assert_eq!(adapter_calls.load(Ordering::SeqCst), expected_adapter_calls);
            drop(service);
            drop(coordinator);

            let before_recovery = persistent_store_material(&store);
            let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            let unknown = reopened.inspect_job(&job_id).unwrap().pop().unwrap();
            assert_eq!(
                unknown.state(),
                crate::workbench_analysis::jobs::AnalysisJobState::Unknown
            );
            assert!(unknown.report().is_none());
            assert!(reopened.claim_next(102).unwrap().is_none());
            let receipts = store.join("jobs").join(&job_id).join("attempt_receipts");
            let event_count = std::fs::read_dir(&receipts).unwrap().count();
            assert_eq!(event_count, expected_receipt_events);
            drop(reopened);
            let after_recovery = persistent_store_material(&store);
            assert_eq!(after_recovery.len(), before_recovery.len() + 1);
            for (path, bytes) in &before_recovery {
                assert_eq!(after_recovery.get(path), Some(bytes));
            }
            let reopened_again =
                DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
            assert_eq!(
                std::fs::read_dir(&receipts).unwrap().count(),
                expected_receipt_events
            );
            drop(reopened_again);
            assert_eq!(persistent_store_material(&store), after_recovery);
        }
    }

    #[test]
    fn nested_ffi_events_are_bound_to_attempt_and_lifo_paired_before_host_result() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "a".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |input, scoring, journal| {
            let start = SearchAttemptStart {
                ordinal: 1,
                attempt_id: attempt_id.clone(),
                phase: SearchAttemptPhase::Initial,
            };
            journal
                .record(SearchAttemptJournalEvent::Started(start))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            for event in [
                SearchAttemptJournalEvent::FfiEntered(SearchAttemptFfiEntry {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "b".repeat(32),
                    direction: SearchAttemptFfiDirection::HostToOcgcore,
                    name: "OCG_DuelProcess".into(),
                    ffi_ordinal: 1,
                }),
                SearchAttemptJournalEvent::FfiEntered(SearchAttemptFfiEntry {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "c".repeat(32),
                    direction: SearchAttemptFfiDirection::OcgcoreCallbackToHost,
                    name: "card_reader".into(),
                    ffi_ordinal: 2,
                }),
                SearchAttemptJournalEvent::FfiReturned(SearchAttemptFfiReturn {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "c".repeat(32),
                    status: SearchAttemptFfiReturnStatus::Returned,
                    result_sha256: Some("d".repeat(64)),
                }),
                SearchAttemptJournalEvent::FfiReturned(SearchAttemptFfiReturn {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "b".repeat(32),
                    status: SearchAttemptFfiReturnStatus::Returned,
                    result_sha256: Some("e".repeat(64)),
                }),
            ] {
                journal
                    .record(event)
                    .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            }
            journal
                .record(SearchAttemptJournalEvent::Finished(
                    SearchAttemptObservation {
                        ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        phase: SearchAttemptPhase::Initial,
                        result: SearchAttemptResult::DuelResult {
                            status: ygo_engine_adapter::DuelStatus::Failed,
                        },
                        process_observation: ProcessRunObservation::default(),
                    },
                ))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            Ok(AnalysisExecution::report_only(AnalysisReport {
                schema_version: 2,
                request: input.request.clone(),
                runtime_request: input.runtime_request.clone(),
                search: ygo_search::combo::SearchReport {
                    termination: "exhausted".into(),
                    lines: Vec::new(),
                    stats: Default::default(),
                    diagnostics: Vec::new(),
                    scoring: scoring.clone(),
                    budget: input.request.search.clone(),
                },
                card_names: Default::default(),
            }))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        service
            .dispatch_pending()
            .unwrap_or_else(|error| panic!("ffi journal dispatch failed: {error:?}"));

        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        let receipt_bytes = (1..=6)
            .map(|sequence| std::fs::read(receipt_dir.join(format!("{sequence}.json"))).unwrap())
            .collect::<Vec<_>>();
        let events = (1..=6)
            .map(|sequence| {
                let value: Value = serde_json::from_slice(
                    &std::fs::read(receipt_dir.join(format!("{sequence}.json"))).unwrap(),
                )
                .unwrap();
                assert_eq!(value["sequence"], sequence);
                value["event"].clone()
            })
            .collect::<Vec<_>>();
        assert_eq!(events[0]["event_type"], "started");
        assert_eq!(events[1]["event_type"], "ffi_entered");
        assert_eq!(events[1]["direction"], "host_to_ocgcore");
        assert_eq!(events[1]["name"], "OCG_DuelProcess");
        assert_eq!(events[2]["event_type"], "ffi_entered");
        assert_eq!(events[2]["direction"], "ocgcore_callback_to_host");
        assert_eq!(events[3]["event_type"], "ffi_returned");
        assert_eq!(events[3]["call_id"], "c".repeat(32));
        assert_eq!(events[4]["event_type"], "ffi_returned");
        assert_eq!(events[4]["call_id"], "b".repeat(32));
        assert_eq!(events[5]["event_type"], "host_result");
        assert!(coordinator.inspect_report(&job_id).is_ok());
        drop(service);
        drop(coordinator);

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Completed
        );
        drop(reopened);
        let reopened_again = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        for (index, expected) in receipt_bytes.iter().enumerate() {
            assert_eq!(
                std::fs::read(receipt_dir.join(format!("{}.json", index + 1))).unwrap(),
                *expected
            );
        }
        drop(reopened_again);
    }

    #[test]
    fn outer_ffi_return_before_nested_callback_is_rejected() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal-order")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "a".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
            for event in [
                SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }),
                SearchAttemptJournalEvent::FfiEntered(SearchAttemptFfiEntry {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "b".repeat(32),
                    direction: SearchAttemptFfiDirection::HostToOcgcore,
                    name: "OCG_DuelProcess".into(),
                    ffi_ordinal: 1,
                }),
                SearchAttemptJournalEvent::FfiEntered(SearchAttemptFfiEntry {
                    attempt_ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    call_id: "c".repeat(32),
                    direction: SearchAttemptFfiDirection::OcgcoreCallbackToHost,
                    name: "card_reader".into(),
                    ffi_ordinal: 2,
                }),
            ] {
                journal
                    .record(event)
                    .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            }
            assert!(journal
                .record(SearchAttemptJournalEvent::FfiReturned(
                    SearchAttemptFfiReturn {
                        attempt_ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        call_id: "b".repeat(32),
                        status: SearchAttemptFfiReturnStatus::Returned,
                        result_sha256: None,
                    }
                ))
                .is_err());
            Err(AnalysisExecutionFailure::UncertainWithObservations(
                Vec::new(),
            ))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        assert!(service.dispatch_pending().is_err());
        assert!(coordinator.is_stopped().unwrap());
        drop(service);
        drop(coordinator);
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        assert_eq!(std::fs::read_dir(&receipt_dir).unwrap().count(), 3);
        assert!(reopened.claim_next(107).unwrap().is_none());
    }

    #[test]
    fn dangling_ffi_entry_is_preserved_as_unknown_across_reopen() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal-interrupted")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "f".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
            journal
                .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            journal
                .record(SearchAttemptJournalEvent::FfiEntered(
                    SearchAttemptFfiEntry {
                        attempt_ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        call_id: "9".repeat(32),
                        direction: SearchAttemptFfiDirection::HostToOcgcore,
                        name: "OCG_DuelProcess".into(),
                        ffi_ordinal: 1,
                    },
                ))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            Err(AnalysisExecutionFailure::UncertainWithObservations(
                Vec::new(),
            ))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        service.dispatch_pending().unwrap();
        let history = coordinator.inspect_job(&job_id).unwrap();
        assert_eq!(
            history.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(coordinator.inspect_report(&job_id).is_err());
        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        assert_eq!(std::fs::read_dir(&receipt_dir).unwrap().count(), 2);
        let entered: Value =
            serde_json::from_slice(&std::fs::read(receipt_dir.join("2.json")).unwrap()).unwrap();
        assert_eq!(entered["event"]["event_type"], "ffi_entered");
        drop(service);
        drop(coordinator);

        let first_reopen = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert!(first_reopen.claim_next(103).unwrap().is_none());
        drop(first_reopen);
        let stable_bytes = std::fs::read(receipt_dir.join("2.json")).unwrap();
        let second_reopen = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            second_reopen
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(second_reopen.claim_next(104).unwrap().is_none());
        drop(second_reopen);
        assert_eq!(
            std::fs::read(receipt_dir.join("2.json")).unwrap(),
            stable_bytes
        );
    }

    #[test]
    fn host_result_cannot_close_an_unreturned_ffi_call() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal-invalid-close")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "f".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |_input, _scoring, journal| {
            journal
                .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            journal
                .record(SearchAttemptJournalEvent::FfiEntered(
                    SearchAttemptFfiEntry {
                        attempt_ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        call_id: "9".repeat(32),
                        direction: SearchAttemptFfiDirection::HostToOcgcore,
                        name: "OCG_DuelProcess".into(),
                        ffi_ordinal: 1,
                    },
                ))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            let invalid_close = journal.record(SearchAttemptJournalEvent::Finished(
                SearchAttemptObservation {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::DuelResult {
                        status: ygo_engine_adapter::DuelStatus::Failed,
                    },
                    process_observation: ProcessRunObservation::default(),
                },
            ));
            assert!(invalid_close.is_err());
            Err(AnalysisExecutionFailure::UncertainWithObservations(
                Vec::new(),
            ))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        assert!(service.dispatch_pending().is_err());
        assert!(coordinator.is_stopped().unwrap());
        drop(service);
        drop(coordinator);

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        assert_eq!(std::fs::read_dir(&receipt_dir).unwrap().count(), 2);
        let last: Value =
            serde_json::from_slice(&std::fs::read(receipt_dir.join("2.json")).unwrap()).unwrap();
        assert_eq!(last["event"]["event_type"], "ffi_entered");
        assert!(reopened.claim_next(105).unwrap().is_none());
    }

    #[test]
    fn ffi_call_ids_cannot_be_reused_across_attempts_in_one_job() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal-duplicate-call-id")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let first_attempt_id = "a".repeat(32);
        let second_attempt_id = "c".repeat(32);
        let expected_second_attempt_id = second_attempt_id.clone();
        let duplicate_call_id = "b".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
            for event in [
                SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: first_attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }),
                SearchAttemptJournalEvent::FfiEntered(SearchAttemptFfiEntry {
                    attempt_ordinal: 1,
                    attempt_id: first_attempt_id.clone(),
                    call_id: duplicate_call_id.clone(),
                    direction: SearchAttemptFfiDirection::HostToOcgcore,
                    name: "OCG_DuelProcess".into(),
                    ffi_ordinal: 1,
                }),
                SearchAttemptJournalEvent::FfiReturned(SearchAttemptFfiReturn {
                    attempt_ordinal: 1,
                    attempt_id: first_attempt_id.clone(),
                    call_id: duplicate_call_id.clone(),
                    status: SearchAttemptFfiReturnStatus::Returned,
                    result_sha256: None,
                }),
                SearchAttemptJournalEvent::Finished(SearchAttemptObservation {
                    ordinal: 1,
                    attempt_id: first_attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::DuelResult {
                        status: ygo_engine_adapter::DuelStatus::Failed,
                    },
                    process_observation: ProcessRunObservation::default(),
                }),
                SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 2,
                    attempt_id: second_attempt_id.clone(),
                    phase: SearchAttemptPhase::Replay,
                }),
            ] {
                journal
                    .record(event)
                    .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            }
            assert!(journal
                .record(SearchAttemptJournalEvent::FfiEntered(
                    SearchAttemptFfiEntry {
                        attempt_ordinal: 2,
                        attempt_id: second_attempt_id.clone(),
                        call_id: duplicate_call_id.clone(),
                        direction: SearchAttemptFfiDirection::HostToOcgcore,
                        name: "OCG_DuelProcess".into(),
                        ffi_ordinal: 1,
                    }
                ))
                .is_err());
            Err(AnalysisExecutionFailure::UncertainWithObservations(
                Vec::new(),
            ))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);

        assert!(service.dispatch_pending().is_err());
        assert!(coordinator.is_stopped().unwrap());
        drop(service);
        drop(coordinator);
        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        assert_eq!(std::fs::read_dir(&receipt_dir).unwrap().count(), 5);
        let last: Value =
            serde_json::from_slice(&std::fs::read(receipt_dir.join("5.json")).unwrap()).unwrap();
        assert_eq!(last["event"]["event_type"], "started");
        assert_eq!(last["event"]["attempt_id"], expected_second_attempt_id);
        assert!(reopened.claim_next(106).unwrap().is_none());
    }

    #[test]
    fn ffi_receipt_write_failure_stops_before_following_ffi_event() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-ffi-journal-write-failure")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let attempt_id = "a".repeat(32);
        let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
            journal
                .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: attempt_id.clone(),
                    phase: SearchAttemptPhase::Initial,
                }))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            journal
                .record(SearchAttemptJournalEvent::FfiEntered(
                    SearchAttemptFfiEntry {
                        attempt_ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        call_id: "b".repeat(32),
                        direction: SearchAttemptFfiDirection::HostToOcgcore,
                        name: "OCG_DuelProcess".into(),
                        ffi_ordinal: 1,
                    },
                ))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            journal
                .record(SearchAttemptJournalEvent::FfiEntered(
                    SearchAttemptFfiEntry {
                        attempt_ordinal: 1,
                        attempt_id: attempt_id.clone(),
                        call_id: "c".repeat(32),
                        direction: SearchAttemptFfiDirection::OcgcoreCallbackToHost,
                        name: "card_reader".into(),
                        ffi_ordinal: 2,
                    },
                ))
                .map_err(|_| AnalysisExecutionFailure::UncertainWithObservations(Vec::new()))?;
            Err(AnalysisExecutionFailure::UncertainWithObservations(
                Vec::new(),
            ))
        });
        let (service, coordinator, _operation_id, job_id, store) =
            prepare_operation_dispatch_service(&root, executor);
        coordinator.inject_attempt_receipt_failure_after(1, false);

        assert!(service.dispatch_pending().is_err());
        assert!(coordinator.is_stopped().unwrap());
        drop(service);
        drop(coordinator);

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(
            reopened
                .inspect_job(&job_id)
                .unwrap()
                .last()
                .unwrap()
                .state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        let receipt_dir = store.join("jobs").join(&job_id).join("attempt_receipts");
        assert_eq!(std::fs::read_dir(&receipt_dir).unwrap().count(), 1);
        let first: Value =
            serde_json::from_slice(&std::fs::read(receipt_dir.join("1.json")).unwrap()).unwrap();
        assert_eq!(first["event"]["event_type"], "started");
        assert!(reopened.claim_next(108).unwrap().is_none());
    }

    #[test]
    fn uncertain_executor_result_is_persisted_unknown_and_stops_dispatch() {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1c-dispatch-tests")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let executor_calls = calls.clone();
        let executor: AnalysisExecutor = Arc::new(move |_, _, _journal| {
            executor_calls.fetch_add(1, Ordering::SeqCst);
            Err(AnalysisExecutionFailure::UncertainWithObservations(vec![
                SearchAttemptObservation {
                    ordinal: 1,
                    attempt_id: "c".repeat(32),
                    phase: SearchAttemptPhase::Initial,
                    result: SearchAttemptResult::AdapterError {
                        code: "timeout".into(),
                        stage: "process".into(),
                    },
                    process_observation: ProcessRunObservation::default(),
                },
            ]))
        });
        let (service, coordinator, queued, store) = dispatch_test_service(&root, executor);

        service.dispatch_pending().unwrap();

        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert!(coordinator.is_stopped().unwrap());
        assert!(service.dispatch_pending().is_err());
        drop(service);
        drop(coordinator);

        let reopened = DurableAnalysisCoordinator::open_operations(store).unwrap();
        let unknown = reopened
            .inspect_job_optional(queued.job_id())
            .unwrap()
            .unwrap();
        assert_eq!(
            unknown.state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(unknown.report().is_none());
        assert!(reopened.claim_next(101).unwrap().is_none());
    }

    const RUNNING_EXECUTOR_CRASH_TEST: &str =
        "workbench::analysis_http::tests::running_job_crash_after_executor_started_recovers_unknown_once";
    const RUNNING_EXECUTOR_CRASH_MODE: &str = "YGO_H3_RUNNING_EXECUTOR_CRASH_CHILD";
    const RUNNING_EXECUTOR_CRASH_ROOT: &str = "YGO_H3_RUNNING_EXECUTOR_CRASH_ROOT";
    const RUNNING_EXECUTOR_CRASH_MARKER: &str = "YGO_H3_RUNNING_EXECUTOR_CRASH_MARKER";
    const RUNNING_EXECUTOR_CRASH_EVENTS: &str = "YGO_H3_CRASH_EVENTS";
    const EXECUTOR_RETURN_CRASH_TEST: &str = "workbench::analysis_http::tests::running_job_crash_after_executor_return_before_report_publish_recovers_unknown_once";
    const EXECUTOR_RETURN_CRASH_MODE: &str = "YGO_H3_EXECUTOR_RETURN_CRASH_CHILD";
    const EXECUTOR_RETURN_CRASH_ROOT: &str = "YGO_H3_EXECUTOR_RETURN_CRASH_ROOT";
    const EXECUTOR_RETURN_CRASH_MARKER: &str = "YGO_H3_EXECUTOR_RETURN_CRASH_MARKER";
    const TICKET_RETURN_CRASH_TEST: &str =
        "workbench::analysis_http::tests::running_job_crash_after_ticket_return_before_executor_call_recovers_unknown_once";
    const TICKET_RETURN_CRASH_MODE: &str = "YGO_H3_TICKET_RETURN_CRASH_CHILD";
    const TICKET_RETURN_CRASH_ROOT: &str = "YGO_H3_TICKET_RETURN_CRASH_ROOT";
    const TICKET_RETURN_CRASH_MARKER: &str = "YGO_H3_TICKET_RETURN_CRASH_MARKER";
    const REPORT_TEMP_CRASH_TEST: &str = "workbench::analysis_http::tests::running_job_crash_after_report_temp_sync_before_publish_recovers_unknown_once";
    const REPORT_TEMP_CRASH_MODE: &str = "YGO_H3_REPORT_TEMP_CRASH_CHILD";
    const REPORT_TEMP_CRASH_ROOT: &str = "YGO_H3_REPORT_TEMP_CRASH_ROOT";
    const REPORT_TEMP_CRASH_MARKER: &str = "YGO_H3_REPORT_TEMP_CRASH_MARKER";
    const STORAGE_REPORT_TEMP_CRASH_MARKER: &str = "YGO_STORAGE_H3_REPORT_TEMP_MARKER";
    const DISPATCH_ASSET_MISMATCH_CRASH_TEST: &str = "workbench::analysis_http::tests::dispatch_admission_asset_mismatch_crash_keeps_terminal_failure";
    const DISPATCH_ASSET_MISMATCH_CRASH_MODE: &str = "YGO_H3_DISPATCH_ASSET_MISMATCH_CRASH_CHILD";
    const DISPATCH_ASSET_MISMATCH_CRASH_ROOT: &str = "YGO_H3_DISPATCH_ASSET_MISMATCH_CRASH_ROOT";
    const DISPATCH_ASSET_MISMATCH_CRASH_MARKER: &str = "YGO_H3_CRASH_MARKER";
    const DISPATCH_ASSET_MISMATCH_CRASH_EVENTS: &str = "YGO_H3_CRASH_EVENTS";
    const DISPATCH_ASSET_MISMATCH_CHECKPOINT: &str =
        "dispatch_asset_mismatch_persisted_before_queue_update";

    struct CrashChild(std::process::Child);

    impl CrashChild {
        fn terminate(&mut self) -> std::process::ExitStatus {
            self.0
                .kill()
                .expect("kill checkpointed fake executor child");
            self.0
                .wait()
                .expect("reap checkpointed fake executor child")
        }
    }

    impl Drop for CrashChild {
        fn drop(&mut self) {
            if self.0.try_wait().ok().flatten().is_none() {
                let _ = self.0.kill();
                let _ = self.0.wait();
            }
        }
    }

    fn running_executor_crash_root() -> std::path::PathBuf {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/h3-running-executor-kill")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn publish_executor_checkpoint(path: &std::path::Path, value: &Value) {
        let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
        let bytes = serde_json::to_vec(value).unwrap();
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .unwrap();
        use std::io::Write;
        file.write_all(&bytes).unwrap();
        file.write_all(b"\n").unwrap();
        file.sync_all().unwrap();
        drop(file);
        std::fs::rename(temporary, path).unwrap();
    }

    fn append_executor_crash_event(event: &str) {
        let Some(path) = std::env::var_os(RUNNING_EXECUTOR_CRASH_EVENTS) else {
            return;
        };
        let mut file = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .unwrap();
        use std::io::Write;
        writeln!(file, "{event}").unwrap();
        file.sync_all().unwrap();
    }

    pub(super) fn attempt_start_checkpoint(
        ticket: &crate::workbench_analysis::queue::DispatchTicket,
        context: &AttemptReceiptContextV1,
        event: &AttemptReceiptEventV1,
    ) {
        let AttemptReceiptEventV1::Started {
            ordinal,
            attempt_id,
            phase,
        } = event
        else {
            return;
        };
        let Some(marker) = std::env::var_os(RUNNING_EXECUTOR_CRASH_MARKER) else {
            return;
        };
        assert_eq!(context.job_id, ticket.record().job_id());
        assert_eq!(context.running_job_revision, ticket.record().revision());
        let root = std::path::PathBuf::from(
            std::env::var_os(RUNNING_EXECUTOR_CRASH_ROOT).expect("attempt crash root"),
        );
        let receipt_path = root
            .join("jobs-store")
            .join("jobs")
            .join(&context.job_id)
            .join("attempt_receipts")
            .join("1.json");
        let receipt_bytes = std::fs::read(&receipt_path).expect("durable attempt-start receipt");
        let receipt: Value = serde_json::from_slice(&receipt_bytes).unwrap();
        assert_eq!(receipt["event"]["event_type"], "started");
        assert_eq!(receipt["event"]["attempt_id"], attempt_id.as_str());
        append_executor_crash_event("attempt_start_persisted");
        publish_executor_checkpoint(
            &std::path::PathBuf::from(marker),
            &serde_json::json!({
                "schema_version": 1,
                "kind": "h3_running_attempt_start_before_adapter_checkpoint",
                "pid": std::process::id(),
                "operation_id": context.operation_id,
                "job_id": context.job_id,
                "running_job_revision": context.running_job_revision,
                "command_sha256": context.command_sha256,
                "job_input_binding_sha256": context.job_input_binding_sha256,
                "input_sha256": context.input_sha256,
                "receipt_sequence": receipt["sequence"],
                "receipt_event_sha256": receipt["event_sha256"],
                "receipt_file_sha256": ygo_storage::hash(&receipt_bytes),
                "attempt_ordinal": ordinal,
                "attempt_id": attempt_id,
                "attempt_phase": phase,
                "executor_invocations": 1,
                "adapter_calls": 0,
                "worker_spawned": false,
                "engine_or_ffi_called": false,
            }),
        );
        loop {
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    }

    pub(super) fn executor_return_checkpoint(
        ticket: &crate::workbench_analysis::queue::DispatchTicket,
        outcome: &std::thread::Result<Result<AnalysisExecution, AnalysisExecutionFailure>>,
    ) {
        let Some(marker) = std::env::var_os(EXECUTOR_RETURN_CRASH_MARKER) else {
            return;
        };
        assert!(
            matches!(outcome, Ok(Ok(_))),
            "fake executor did not return a report"
        );
        assert_eq!(
            ticket.record().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert!(ticket.record().report().is_none());
        append_executor_crash_event("fake_executor_returned");
        publish_executor_checkpoint(
            std::path::Path::new(&marker),
            &serde_json::json!({
                "schema_version": 1,
                "kind": "h3_executor_return_checkpoint",
                "pid": std::process::id(),
                "job_id": ticket.record().job_id(),
                "job_revision": ticket.record().revision(),
                "input_binding_sha256": ticket.record().input().binding_sha256,
                "executor_result": "ok_report",
                "executor_returned": true,
                "executor_invocations": 1,
                "report_persisted": false,
                "worker_spawned": false,
                "engine_or_ffi_called": false,
            }),
        );
        loop {
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    }

    pub(super) fn ticket_return_checkpoint(
        ticket: &crate::workbench_analysis::queue::DispatchTicket,
    ) {
        let Some(marker) = std::env::var_os(TICKET_RETURN_CRASH_MARKER) else {
            return;
        };
        assert_eq!(
            ticket.record().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert!(ticket.record().report().is_none());
        append_executor_crash_event("ticket_returned_before_executor");
        publish_executor_checkpoint(
            std::path::Path::new(&marker),
            &serde_json::json!({
                "schema_version": 1,
                "kind": "h3_ticket_return_before_executor_checkpoint",
                "pid": std::process::id(),
                "job_id": ticket.record().job_id(),
                "job_revision": ticket.record().revision(),
                "input_binding_sha256": ticket.record().input().binding_sha256,
                "ticket_returned": true,
                "executor_invocations": 0,
                "report_persisted": false,
                "worker_spawned": false,
                "engine_or_ffi_called": false,
            }),
        );
        loop {
            std::thread::sleep(std::time::Duration::from_millis(20));
        }
    }

    fn prepare_operation_dispatch_service(
        root: &std::path::Path,
        executor: AnalysisExecutor,
    ) -> (
        Arc<AnalysisHttpService>,
        Arc<DurableAnalysisCoordinator>,
        String,
        String,
        std::path::PathBuf,
    ) {
        prepare_operation_dispatch_service_with_admission(root, executor, None)
    }

    fn prepare_operation_dispatch_service_with_admission(
        root: &std::path::Path,
        executor: AnalysisExecutor,
        admission: Option<Arc<W1cAdmission>>,
    ) -> (
        Arc<AnalysisHttpService>,
        Arc<DurableAnalysisCoordinator>,
        String,
        String,
        std::path::PathBuf,
    ) {
        std::fs::create_dir_all(root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(root);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let context = AnalysisOperationContext {
            scoring: Default::default(),
            default_catalog_id: catalog.clone(),
            configuration_sha256: "a".repeat(64),
        };
        let command = crate::workbench_analysis::operations::AnalysisOperationCommand {
            draft_id: saved.id,
            draft_revision: saved.revision,
            opening_hand: draft.main[..5].to_vec(),
            seed: 1,
            rules: "ocg-mr5".into(),
            catalog_id: None,
            banlist_id: banlist,
            as_of: "2026-10-30".into(),
            search: Default::default(),
        };
        let store = root.join("jobs-store");
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(store.clone()).unwrap());
        let allocated = coordinator
            .allocate_operation(context.clone(), 100)
            .unwrap();
        let operation_id = allocated.operation_id().to_owned();
        let accepted = coordinator
            .submit_operation(
                &operation_id,
                command,
                &context,
                101,
                &drafts,
                &snapshots,
                engine.clone(),
            )
            .unwrap();
        assert_eq!(accepted.state(), AnalysisOperationState::Accepted);
        let job_id = accepted.job_id().unwrap().to_owned();
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context,
            drafts: Arc::new(drafts),
            snapshots,
            engine,
            admission,
            executor: Some(executor),
            dispatch_lock: Mutex::new(()),
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
        });
        (service, coordinator, operation_id, job_id, store)
    }

    fn dispatch_asset_mismatch_crash_root() -> std::path::PathBuf {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/h3-dispatch-asset-mismatch-kill")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn execute_child_until_dispatch_asset_mismatch_checkpoint(root: &std::path::Path) {
        let admission = Arc::new(W1cAdmission::fixture_policy());
        let executor: AnalysisExecutor = Arc::new(|_, _, _journal| {
            append_executor_crash_event("executor_entered");
            panic!("executor must not run after dispatch admission rejects frozen input");
        });
        let (service, coordinator, _operation_id, job_id, _store) =
            prepare_operation_dispatch_service_with_admission(root, executor, Some(admission));
        let queued = coordinator.inspect_job(&job_id).unwrap();
        assert_eq!(queued.len(), 1);
        assert_eq!(
            queued[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        let _ = service.dispatch_pending();
        panic!("dispatch AssetMismatch checkpoint unexpectedly returned");
    }

    fn execute_child_until_fake_executor_checkpoint(root: &std::path::Path) {
        let executor: AnalysisExecutor = Arc::new(move |_, _, journal| {
            append_executor_crash_event("fake_executor_entered");
            journal
                .record(SearchAttemptJournalEvent::Started(SearchAttemptStart {
                    ordinal: 1,
                    attempt_id: "a".repeat(32),
                    phase: SearchAttemptPhase::Initial,
                }))
                .expect("attempt start must be durable before the fake adapter step");
            append_executor_crash_event("fake_adapter_entered");
            loop {
                std::thread::sleep(std::time::Duration::from_millis(20));
            }
        });
        let (service, _coordinator, _operation_id, _job_id, _store) =
            prepare_operation_dispatch_service(root, executor);
        service.dispatch_pending().unwrap();
        panic!("fake executor checkpoint unexpectedly returned");
    }

    fn persistent_store_material(
        root: &std::path::Path,
    ) -> std::collections::BTreeMap<String, Vec<u8>> {
        fn visit(
            base: &std::path::Path,
            current: &std::path::Path,
            files: &mut std::collections::BTreeMap<String, Vec<u8>>,
        ) {
            for entry in std::fs::read_dir(current).unwrap() {
                let entry = entry.unwrap();
                let path = entry.path();
                if path.is_dir() {
                    visit(base, &path, files);
                } else if entry.file_name() != ".ygo-analysis.lock" {
                    files.insert(
                        path.strip_prefix(base)
                            .unwrap()
                            .to_string_lossy()
                            .into_owned(),
                        std::fs::read(path).unwrap(),
                    );
                }
            }
        }
        let mut files = std::collections::BTreeMap::new();
        visit(root, root, &mut files);
        files
    }

    fn authenticated_operation_history(
        store: &std::path::Path,
        id: &str,
    ) -> Vec<crate::workbench_analysis::operations::AnalysisOperationRecordV1> {
        let revisions = store.join("operations").join(id).join("revisions");
        let mut paths = std::fs::read_dir(&revisions)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        paths.sort();
        let mut previous = None;
        let mut history = Vec::new();
        for (index, path) in paths.iter().enumerate() {
            let bytes = std::fs::read(path).unwrap();
            let envelope: Value = serde_json::from_slice(&bytes).unwrap();
            let revision = index as u64 + 1;
            assert_eq!(envelope["kind"], "workbench_analysis_operation_revision");
            assert_eq!(envelope["operation_id"], id);
            assert_eq!(envelope["revision"], revision);
            assert_eq!(envelope["previous_sha256"].as_str(), previous.as_deref());
            let record_bytes = serde_json::to_vec(&envelope["record"]).unwrap();
            let record =
                crate::workbench_analysis::operations::AnalysisOperationRecordV1::read_json(
                    &record_bytes,
                )
                .unwrap();
            assert_eq!(record.revision(), revision);
            assert_eq!(
                envelope["record_sha256"],
                ygo_storage::hash(&record.encode_json().unwrap())
            );
            previous = Some(ygo_storage::hash(&bytes));
            history.push(record);
        }
        history
    }

    fn authenticated_job_history(
        store: &std::path::Path,
        id: &str,
    ) -> Vec<crate::workbench_analysis::jobs::AnalysisJobRecordV1> {
        let revisions = store.join("jobs").join(id).join("revisions");
        let mut paths = std::fs::read_dir(&revisions)
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        paths.sort();
        let mut previous = None;
        let mut history = Vec::new();
        for (index, path) in paths.iter().enumerate() {
            let bytes = std::fs::read(path).unwrap();
            let envelope: Value = serde_json::from_slice(&bytes).unwrap();
            let revision = index as u64 + 1;
            assert_eq!(envelope["kind"], "workbench_analysis_job_revision");
            assert_eq!(envelope["job_id"], id);
            assert_eq!(envelope["revision"], revision);
            assert_eq!(envelope["previous_sha256"].as_str(), previous.as_deref());
            let record_bytes = serde_json::to_vec(&envelope["record"]).unwrap();
            let record =
                crate::workbench_analysis::jobs::AnalysisJobRecordV1::read_json(&record_bytes)
                    .unwrap();
            assert_eq!(record.revision(), revision);
            assert_eq!(
                envelope["record_sha256"],
                ygo_storage::hash(&record.encode_json().unwrap())
            );
            previous = Some(ygo_storage::hash(&bytes));
            history.push(record);
        }
        history
    }

    #[test]
    fn running_job_crash_after_executor_started_recovers_unknown_once() {
        if std::env::var_os(RUNNING_EXECUTOR_CRASH_MODE).is_some() {
            let root = std::path::PathBuf::from(
                std::env::var_os(RUNNING_EXECUTOR_CRASH_ROOT).expect("executor crash root"),
            );
            execute_child_until_fake_executor_checkpoint(&root);
        }

        let root = running_executor_crash_root();
        let marker = root.join("executor-checkpoint.json");
        let events = root.join("events.log");
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&events)
            .unwrap();
        let child_output = std::fs::File::create(root.join("child-output.log")).unwrap();
        let mut child = CrashChild(
            std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    RUNNING_EXECUTOR_CRASH_TEST,
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env_remove("YGO_H3_CRASH_CHECKPOINT")
                .env_remove("YGO_H3_CRASH_MARKER")
                .env(RUNNING_EXECUTOR_CRASH_MODE, "1")
                .env(RUNNING_EXECUTOR_CRASH_ROOT, &root)
                .env(RUNNING_EXECUTOR_CRASH_MARKER, &marker)
                .env(RUNNING_EXECUTOR_CRASH_EVENTS, &events)
                .stdout(std::process::Stdio::from(child_output.try_clone().unwrap()))
                .stderr(std::process::Stdio::from(child_output))
                .spawn()
                .unwrap(),
        );
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
        while !marker.is_file() && std::time::Instant::now() < deadline {
            if let Some(status) = child.0.try_wait().unwrap() {
                let output =
                    std::fs::read_to_string(root.join("child-output.log")).unwrap_or_default();
                panic!("child exited before fake executor checkpoint ({status}): {output}");
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(marker.is_file(), "child missed fake executor checkpoint");
        let checkpoint: Value = serde_json::from_slice(&std::fs::read(&marker).unwrap()).unwrap();
        assert_eq!(checkpoint["schema_version"], 1);
        assert_eq!(
            checkpoint["kind"],
            "h3_running_attempt_start_before_adapter_checkpoint"
        );
        assert_eq!(checkpoint["executor_invocations"], 1);
        assert_eq!(checkpoint["adapter_calls"], 0);
        assert_eq!(checkpoint["worker_spawned"], false);
        assert_eq!(checkpoint["engine_or_ffi_called"], false);
        let operation_id = checkpoint["operation_id"].as_str().unwrap();
        let job_id = checkpoint["job_id"].as_str().unwrap();
        let store = root.join("jobs-store");
        let operations = authenticated_operation_history(&store, operation_id);
        assert_eq!(operations.len(), 4);
        assert_eq!(operations[0].state(), AnalysisOperationState::Allocated);
        assert_eq!(operations[1].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[2].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[3].state(), AnalysisOperationState::Accepted);
        assert_eq!(operations[3].job_id(), Some(job_id));
        let jobs = authenticated_job_history(&store, job_id);
        assert_eq!(jobs.len(), 2);
        assert_eq!(
            jobs[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        assert_eq!(
            jobs[1].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert_eq!(
            jobs[0].input().binding_sha256,
            operations[3].frozen_input().unwrap().binding_sha256
        );
        let receipt_path = store
            .join("jobs")
            .join(job_id)
            .join("attempt_receipts")
            .join("1.json");
        let receipt_bytes = std::fs::read(&receipt_path).unwrap();
        let receipt: Value = serde_json::from_slice(&receipt_bytes).unwrap();
        assert_eq!(receipt["kind"], "w1c_search_attempt_journal_event");
        assert_eq!(receipt["sequence"], 1);
        assert_eq!(receipt["previous_sha256"], "0".repeat(64));
        assert_eq!(receipt["context"]["operation_id"], operation_id);
        assert_eq!(receipt["context"]["job_id"], job_id);
        assert_eq!(
            receipt["context"]["running_job_revision"],
            jobs[1].revision()
        );
        assert_eq!(
            receipt["context"]["command_sha256"],
            operations[3].command_sha256().unwrap()
        );
        assert_eq!(
            receipt["context"]["job_input_binding_sha256"],
            jobs[1].input().binding_sha256
        );
        assert_eq!(
            receipt["context"]["input_sha256"],
            jobs[1].input().identity.input_sha256
        );
        assert_eq!(
            receipt["context"]["assets"]["engine_sha256"],
            jobs[1].input().identity.engine_sha256
        );
        assert_eq!(
            receipt["context"]["assets"]["worker_sha256"],
            jobs[1].input().identity.worker_sha256
        );
        assert_eq!(
            receipt["context"]["assets"]["cdb_sha256"],
            jobs[1].input().identity.cdb_sha256
        );
        assert_eq!(
            receipt["context"]["assets"]["scripts_sha256"],
            jobs[1].input().identity.scripts_sha256
        );
        assert_eq!(
            receipt["context"]["assets"]["engine_manifest_sha256"],
            jobs[1].input().identity.engine_manifest_sha256
        );
        assert_eq!(receipt["context"]["source_bundle_identity"], Value::Null);
        assert_eq!(receipt["context"]["build_record_identity"], Value::Null);
        let context_sha256 = ygo_storage::hash(&serde_json::to_vec(&receipt["context"]).unwrap());
        assert_eq!(receipt["context_sha256"], context_sha256);
        let receipt_event_body = serde_json::json!({
            "context_sha256": context_sha256,
            "sequence": receipt["sequence"],
            "previous_sha256": receipt["previous_sha256"],
            "event": receipt["event"],
        });
        let receipt_event_sha256 =
            ygo_storage::hash(&serde_json::to_vec(&receipt_event_body).unwrap());
        assert_eq!(receipt["event_sha256"], receipt_event_sha256);
        assert_eq!(receipt["event"]["event_type"], "started");
        assert_eq!(receipt["event"]["ordinal"], checkpoint["attempt_ordinal"]);
        assert_eq!(receipt["event"]["attempt_id"], checkpoint["attempt_id"]);
        assert_eq!(receipt["event"]["attempt_id"], "a".repeat(32));
        assert_eq!(checkpoint["receipt_event_sha256"], receipt["event_sha256"]);
        assert_eq!(
            checkpoint["receipt_file_sha256"],
            ygo_storage::hash(&receipt_bytes)
        );
        assert_eq!(
            checkpoint["job_input_binding_sha256"],
            receipt["context"]["job_input_binding_sha256"]
        );
        assert_eq!(
            checkpoint["input_sha256"],
            receipt["context"]["input_sha256"]
        );
        assert_eq!(
            checkpoint["command_sha256"],
            receipt["context"]["command_sha256"]
        );
        assert_eq!(
            checkpoint["running_job_revision"],
            receipt["context"]["running_job_revision"]
        );
        assert_eq!(checkpoint["receipt_sequence"], 1);
        assert_eq!(checkpoint["attempt_phase"], "initial");
        let mut marker_keys = checkpoint
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        marker_keys.sort();
        let mut expected_marker_keys = [
            "adapter_calls",
            "attempt_id",
            "attempt_ordinal",
            "attempt_phase",
            "command_sha256",
            "engine_or_ffi_called",
            "executor_invocations",
            "input_sha256",
            "job_id",
            "job_input_binding_sha256",
            "kind",
            "operation_id",
            "pid",
            "receipt_event_sha256",
            "receipt_file_sha256",
            "receipt_sequence",
            "running_job_revision",
            "schema_version",
            "worker_spawned",
        ];
        expected_marker_keys.sort();
        assert_eq!(marker_keys, expected_marker_keys);
        assert!(checkpoint["pid"].as_u64().is_some_and(|pid| pid > 0));
        assert_eq!(checkpoint["pid"].as_u64(), Some(u64::from(child.0.id())));
        assert_eq!(std::fs::read_dir(store.join("jobs")).unwrap().count(), 1);
        assert_eq!(std::fs::read_dir(store.join("reports")).unwrap().count(), 0);
        let pre_kill = persistent_store_material(&store);

        let killed = child.terminate();
        assert!(!killed.success());
        let events_before_recovery = std::fs::read_to_string(&events).unwrap();
        assert_eq!(
            events_before_recovery
                .lines()
                .filter(|line| *line == "claim")
                .count(),
            1
        );
        assert_eq!(
            events_before_recovery
                .lines()
                .filter(|line| *line == "fake_executor_entered")
                .count(),
            1
        );
        assert_eq!(
            events_before_recovery
                .lines()
                .filter(|line| *line == "attempt_start_persisted")
                .count(),
            1
        );
        assert!(!events_before_recovery
            .lines()
            .any(|line| line == "fake_adapter_entered"));
        assert_eq!(persistent_store_material(&store), pre_kill);

        let recovered = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        let operation_history = recovered.inspect_operation(operation_id).unwrap();
        assert_eq!(operation_history.len(), 4);
        assert_eq!(
            operation_history.last().unwrap().state(),
            AnalysisOperationState::Accepted
        );
        let job_history = recovered.inspect_job(job_id).unwrap();
        assert_eq!(job_history.len(), 3);
        assert_eq!(job_history.last().unwrap().revision(), 3);
        assert_eq!(
            job_history.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(recovered.snapshot().unwrap().queued.is_none());
        assert!(recovered.snapshot().unwrap().running.is_none());
        assert!(recovered.claim_next(10_000).unwrap().is_none());
        assert!(recovered.inspect_report(job_id).is_err());
        drop(recovered);
        let after_recovery = persistent_store_material(&store);
        assert_eq!(after_recovery.len(), pre_kill.len() + 1);
        for (path, bytes) in &pre_kill {
            assert_eq!(after_recovery.get(path), Some(bytes));
        }

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(reopened.inspect_operation(operation_id).unwrap().len(), 4);
        let stable_job = reopened.inspect_job(job_id).unwrap();
        assert_eq!(stable_job.len(), 3);
        assert_eq!(
            stable_job.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        let stable = persistent_store_material(&store);
        assert_eq!(stable, after_recovery);
        let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
            files
                .iter()
                .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                .collect::<std::collections::BTreeMap<_, _>>()
        };
        std::fs::write(
            root.join("running-executor-crash-evidence.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": checkpoint,
                "child_exit": killed.to_string(),
                "events": events_before_recovery.lines().collect::<Vec<_>>(),
                "operation_revision_count_before_and_after": 4,
                "job_state_before_kill": "running",
                "job_state_after_reopen": "unknown",
                "unknown_revision_count": 3,
                "attempt_receipt_count_before_and_after": 1,
                "attempt_start_persisted_before_kill": true,
                "adapter_calls_before_kill": 0,
                "report_count_before_and_after": 0,
                "pre_kill_store_sha256": hash_map(&pre_kill),
                "recovered_store_sha256": hash_map(&after_recovery),
                "repeat_reopen_stable": true,
                "claim_after_recovery": false,
                "worker_process_started": false,
                "engine_or_ffi_called": false,
                "scope": "synthetic process kill during a test-only executor call; no production worker or engine evidence"
            })).unwrap(),
        ).unwrap();
    }

    fn executor_return_crash_root() -> std::path::PathBuf {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/h3-executor-return-kill")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn execute_child_until_executor_return_checkpoint(root: &std::path::Path) {
        let executor: AnalysisExecutor = Arc::new(|input, scoring, _journal| {
            append_executor_crash_event("fake_executor_entered");
            Ok(AnalysisExecution::report_only(AnalysisReport {
                schema_version: 2,
                request: input.request.clone(),
                runtime_request: input.runtime_request.clone(),
                search: ygo_search::combo::SearchReport {
                    termination: "exhausted".into(),
                    lines: Vec::new(),
                    stats: Default::default(),
                    diagnostics: Vec::new(),
                    scoring: scoring.clone(),
                    budget: input.request.search.clone(),
                },
                card_names: Default::default(),
            }))
        });
        let (service, _coordinator, _operation_id, _job_id, _store) =
            prepare_operation_dispatch_service(root, executor);
        service.dispatch_pending().unwrap();
        panic!("executor-return checkpoint unexpectedly returned");
    }

    #[test]
    fn running_job_crash_after_executor_return_before_report_publish_recovers_unknown_once() {
        if std::env::var_os(EXECUTOR_RETURN_CRASH_MODE).is_some() {
            let root = std::path::PathBuf::from(
                std::env::var_os(EXECUTOR_RETURN_CRASH_ROOT).expect("executor-return crash root"),
            );
            execute_child_until_executor_return_checkpoint(&root);
        }

        let root = executor_return_crash_root();
        let marker = root.join("executor-return-checkpoint.json");
        let events = root.join("events.log");
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&events)
            .unwrap();
        let child_output = std::fs::File::create(root.join("child-output.log")).unwrap();
        let mut child = CrashChild(
            std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    EXECUTOR_RETURN_CRASH_TEST,
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env_remove("YGO_H3_CRASH_CHECKPOINT")
                .env_remove("YGO_H3_CRASH_MARKER")
                .env_remove(RUNNING_EXECUTOR_CRASH_MODE)
                .env_remove(RUNNING_EXECUTOR_CRASH_ROOT)
                .env_remove(RUNNING_EXECUTOR_CRASH_MARKER)
                .env(EXECUTOR_RETURN_CRASH_MODE, "1")
                .env(EXECUTOR_RETURN_CRASH_ROOT, &root)
                .env(EXECUTOR_RETURN_CRASH_MARKER, &marker)
                .env(RUNNING_EXECUTOR_CRASH_EVENTS, &events)
                .stdout(std::process::Stdio::from(child_output.try_clone().unwrap()))
                .stderr(std::process::Stdio::from(child_output))
                .spawn()
                .unwrap(),
        );
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
        while !marker.is_file() && std::time::Instant::now() < deadline {
            if let Some(status) = child.0.try_wait().unwrap() {
                let output =
                    std::fs::read_to_string(root.join("child-output.log")).unwrap_or_default();
                panic!("child exited before executor-return checkpoint ({status}): {output}");
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(marker.is_file(), "child missed executor-return checkpoint");
        let checkpoint: Value = serde_json::from_slice(&std::fs::read(&marker).unwrap()).unwrap();
        assert_eq!(checkpoint["schema_version"], 1);
        assert_eq!(checkpoint["kind"], "h3_executor_return_checkpoint");
        assert_eq!(checkpoint["pid"].as_u64(), Some(u64::from(child.0.id())));
        assert_eq!(checkpoint["executor_result"], "ok_report");
        assert_eq!(checkpoint["executor_returned"], true);
        assert_eq!(checkpoint["executor_invocations"], 1);
        assert_eq!(checkpoint["report_persisted"], false);
        assert_eq!(checkpoint["worker_spawned"], false);
        assert_eq!(checkpoint["engine_or_ffi_called"], false);
        let job_id = checkpoint["job_id"].as_str().unwrap();
        let store = root.join("jobs-store");
        let operation_dirs = std::fs::read_dir(store.join("operations"))
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        assert_eq!(operation_dirs.len(), 1);
        let operation_id = operation_dirs[0]
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let operations = authenticated_operation_history(&store, &operation_id);
        assert_eq!(operations.len(), 4);
        assert_eq!(operations[0].state(), AnalysisOperationState::Allocated);
        assert_eq!(operations[1].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[2].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[3].state(), AnalysisOperationState::Accepted);
        assert_eq!(operations[3].job_id(), Some(job_id));
        let command = operations[3].command().unwrap();
        let command_sha256 = command.checksum(operations[3].context()).unwrap();
        assert_eq!(
            operations[3].command_sha256(),
            Some(command_sha256.as_str())
        );

        let jobs = authenticated_job_history(&store, job_id);
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].revision(), 1);
        assert_eq!(
            jobs[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        assert_eq!(jobs[1].revision(), 2);
        assert_eq!(
            jobs[1].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert!(jobs[1].report().is_none());
        assert_eq!(checkpoint["job_revision"], jobs[1].revision());
        assert_eq!(
            checkpoint["input_binding_sha256"],
            jobs[1].input().binding_sha256
        );
        assert_eq!(
            operations[3].frozen_binding_sha256(),
            Some(jobs[1].input().binding_sha256.as_str())
        );
        assert_eq!(
            operations[3].frozen_input().unwrap().binding_sha256,
            jobs[1].input().binding_sha256
        );
        assert_eq!(std::fs::read_dir(store.join("jobs")).unwrap().count(), 1);
        assert_eq!(std::fs::read_dir(store.join("reports")).unwrap().count(), 0);
        let pre_kill = persistent_store_material(&store);

        let killed = child.terminate();
        assert!(!killed.success());
        let events_before_recovery = std::fs::read_to_string(&events).unwrap();
        let event_lines = events_before_recovery.lines().collect::<Vec<_>>();
        for expected in [
            "freeze",
            "claim",
            "fake_executor_entered",
            "fake_executor_returned",
        ] {
            assert_eq!(
                event_lines
                    .iter()
                    .filter(|event| **event == expected)
                    .count(),
                1
            );
        }
        let position = |expected: &str| {
            event_lines
                .iter()
                .position(|event| *event == expected)
                .unwrap()
        };
        assert!(position("freeze") < position("claim"));
        assert!(position("claim") < position("fake_executor_entered"));
        assert!(position("fake_executor_entered") < position("fake_executor_returned"));
        assert_eq!(persistent_store_material(&store), pre_kill);

        let recovered = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(recovered.inspect_operation(&operation_id).unwrap().len(), 4);
        let job_history = recovered.inspect_job(job_id).unwrap();
        assert_eq!(job_history.len(), 3);
        assert_eq!(job_history.last().unwrap().revision(), 3);
        assert_eq!(
            job_history.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(job_history.last().unwrap().report().is_none());
        assert!(recovered.snapshot().unwrap().queued.is_none());
        assert!(recovered.snapshot().unwrap().running.is_none());
        assert!(recovered.claim_next(10_000).unwrap().is_none());
        assert!(recovered.inspect_report(job_id).is_err());
        drop(recovered);
        let after_recovery = persistent_store_material(&store);
        assert_eq!(after_recovery.len(), pre_kill.len() + 1);
        for (path, bytes) in &pre_kill {
            assert_eq!(after_recovery.get(path), Some(bytes));
        }

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(reopened.inspect_operation(&operation_id).unwrap().len(), 4);
        let stable_job = reopened.inspect_job(job_id).unwrap();
        assert_eq!(stable_job.len(), 3);
        assert_eq!(
            stable_job.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        let stable = persistent_store_material(&store);
        assert_eq!(stable, after_recovery);
        let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
            files
                .iter()
                .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                .collect::<std::collections::BTreeMap<_, _>>()
        };
        std::fs::write(
            root.join("executor-return-crash-evidence.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": checkpoint,
                "operation_id": operation_id,
                "job_id": job_id,
                "child_exit": killed.to_string(),
                "events": event_lines,
                "operation_revision_count_before_and_after": 4,
                "job_state_before_kill": "running",
                "job_state_after_reopen": "unknown",
                "unknown_revision_count": 3,
                "report_count_before_and_after": 0,
                "pre_kill_store_sha256": hash_map(&pre_kill),
                "recovered_store_sha256": hash_map(&after_recovery),
                "repeat_reopen_stable": true,
                "claim_after_recovery": false,
                "worker_process_started": false,
                "engine_or_ffi_called": false,
                "scope": "synthetic process kill after a test-only executor returned a report and before report publication; no production worker or engine evidence"
            })).unwrap(),
        ).unwrap();
    }

    fn ticket_return_crash_root() -> std::path::PathBuf {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/h3-ticket-return-kill")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn report_temp_crash_root() -> std::path::PathBuf {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/h3-report-temp-kill")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn execute_child_until_report_temp_sync(root: &std::path::Path) {
        let executor: AnalysisExecutor = Arc::new(|input, scoring, _journal| {
            append_executor_crash_event("fake_executor_entered");
            let report = AnalysisReport {
                schema_version: 2,
                request: input.request.clone(),
                runtime_request: input.runtime_request.clone(),
                search: ygo_search::combo::SearchReport {
                    termination: "exhausted".into(),
                    lines: Vec::new(),
                    stats: Default::default(),
                    diagnostics: Vec::new(),
                    scoring: scoring.clone(),
                    budget: input.request.search.clone(),
                },
                card_names: Default::default(),
            };
            append_executor_crash_event("fake_executor_returned");
            Ok(AnalysisExecution::report_only(report))
        });
        let (service, _coordinator, _operation_id, _job_id, _store) =
            prepare_operation_dispatch_service(root, executor);
        service.dispatch_pending().unwrap();
        panic!("report temporary-file checkpoint unexpectedly returned");
    }

    fn execute_child_until_ticket_return_checkpoint(root: &std::path::Path) {
        let executor: AnalysisExecutor = Arc::new(|_, _, _journal| {
            append_executor_crash_event("fake_executor_entered");
            panic!("executor must not be entered before the ticket-return checkpoint");
        });
        let (service, _coordinator, _operation_id, _job_id, _store) =
            prepare_operation_dispatch_service(root, executor);
        service.dispatch_pending().unwrap();
        panic!("ticket-return checkpoint unexpectedly returned");
    }

    #[test]
    fn running_job_crash_after_ticket_return_before_executor_call_recovers_unknown_once() {
        if std::env::var_os(TICKET_RETURN_CRASH_MODE).is_some() {
            let root = std::path::PathBuf::from(
                std::env::var_os(TICKET_RETURN_CRASH_ROOT).expect("ticket-return crash root"),
            );
            execute_child_until_ticket_return_checkpoint(&root);
        }

        let root = ticket_return_crash_root();
        let marker = root.join("ticket-return-checkpoint.json");
        let events = root.join("events.log");
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&events)
            .unwrap();
        let child_output = std::fs::File::create(root.join("child-output.log")).unwrap();
        let mut child = CrashChild(
            std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    TICKET_RETURN_CRASH_TEST,
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env_remove("YGO_H3_CRASH_CHECKPOINT")
                .env_remove("YGO_H3_CRASH_MARKER")
                .env_remove(RUNNING_EXECUTOR_CRASH_MODE)
                .env_remove(RUNNING_EXECUTOR_CRASH_ROOT)
                .env_remove(RUNNING_EXECUTOR_CRASH_MARKER)
                .env_remove(EXECUTOR_RETURN_CRASH_MODE)
                .env_remove(EXECUTOR_RETURN_CRASH_ROOT)
                .env_remove(EXECUTOR_RETURN_CRASH_MARKER)
                .env(TICKET_RETURN_CRASH_MODE, "1")
                .env(TICKET_RETURN_CRASH_ROOT, &root)
                .env(TICKET_RETURN_CRASH_MARKER, &marker)
                .env(RUNNING_EXECUTOR_CRASH_EVENTS, &events)
                .stdout(std::process::Stdio::from(child_output.try_clone().unwrap()))
                .stderr(std::process::Stdio::from(child_output))
                .spawn()
                .unwrap(),
        );
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
        while !marker.is_file() && std::time::Instant::now() < deadline {
            if let Some(status) = child.0.try_wait().unwrap() {
                let output =
                    std::fs::read_to_string(root.join("child-output.log")).unwrap_or_default();
                panic!("child exited before ticket-return checkpoint ({status}): {output}");
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(marker.is_file(), "child missed ticket-return checkpoint");
        let checkpoint: Value = serde_json::from_slice(&std::fs::read(&marker).unwrap()).unwrap();
        assert_eq!(checkpoint["schema_version"], 1);
        assert_eq!(
            checkpoint["kind"],
            "h3_ticket_return_before_executor_checkpoint"
        );
        assert_eq!(checkpoint["pid"].as_u64(), Some(u64::from(child.0.id())));
        assert_eq!(checkpoint["ticket_returned"], true);
        assert_eq!(checkpoint["executor_invocations"], 0);
        assert_eq!(checkpoint["report_persisted"], false);
        assert_eq!(checkpoint["worker_spawned"], false);
        assert_eq!(checkpoint["engine_or_ffi_called"], false);

        let job_id = checkpoint["job_id"].as_str().unwrap();
        let store = root.join("jobs-store");
        let operation_dirs = std::fs::read_dir(store.join("operations"))
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        assert_eq!(operation_dirs.len(), 1);
        let operation_id = operation_dirs[0]
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let operations = authenticated_operation_history(&store, &operation_id);
        assert_eq!(operations.len(), 4);
        assert_eq!(operations[0].state(), AnalysisOperationState::Allocated);
        assert_eq!(operations[1].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[2].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[3].state(), AnalysisOperationState::Accepted);
        assert_eq!(operations[3].job_id(), Some(job_id));
        let command = operations[3].command().unwrap();
        let command_sha256 = command.checksum(operations[3].context()).unwrap();
        assert_eq!(
            operations[3].command_sha256(),
            Some(command_sha256.as_str())
        );

        let jobs = authenticated_job_history(&store, job_id);
        assert_eq!(jobs.len(), 2);
        assert_eq!(jobs[0].revision(), 1);
        assert_eq!(
            jobs[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        assert_eq!(jobs[1].revision(), 2);
        assert_eq!(
            jobs[1].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert!(jobs[1].report().is_none());
        assert_eq!(checkpoint["job_revision"], jobs[1].revision());
        assert_eq!(
            checkpoint["input_binding_sha256"],
            jobs[1].input().binding_sha256
        );
        assert_eq!(
            operations[3].frozen_binding_sha256(),
            Some(jobs[1].input().binding_sha256.as_str())
        );
        assert_eq!(
            operations[3].frozen_input().unwrap().binding_sha256,
            jobs[1].input().binding_sha256
        );
        assert_eq!(std::fs::read_dir(store.join("jobs")).unwrap().count(), 1);
        assert_eq!(std::fs::read_dir(store.join("reports")).unwrap().count(), 0);
        let pre_kill = persistent_store_material(&store);

        let events_before_recovery = std::fs::read_to_string(&events).unwrap();
        let event_lines = events_before_recovery.lines().collect::<Vec<_>>();
        assert_eq!(
            event_lines,
            ["freeze", "claim", "ticket_returned_before_executor"]
        );
        assert!(!event_lines.contains(&"fake_executor_entered"));

        let killed = child.terminate();
        assert!(!killed.success());
        assert_eq!(
            std::fs::read_to_string(&events).unwrap(),
            events_before_recovery
        );
        assert_eq!(persistent_store_material(&store), pre_kill);

        let recovered = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(recovered.inspect_operation(&operation_id).unwrap().len(), 4);
        let job_history = recovered.inspect_job(job_id).unwrap();
        assert_eq!(job_history.len(), 3);
        assert_eq!(job_history.last().unwrap().revision(), 3);
        assert_eq!(
            job_history.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(job_history.last().unwrap().report().is_none());
        assert!(recovered.snapshot().unwrap().queued.is_none());
        assert!(recovered.snapshot().unwrap().running.is_none());
        assert!(recovered.claim_next(10_000).unwrap().is_none());
        assert!(recovered.inspect_report(job_id).is_err());
        drop(recovered);
        let after_recovery = persistent_store_material(&store);
        assert_eq!(after_recovery.len(), pre_kill.len() + 1);
        for (path, bytes) in &pre_kill {
            assert_eq!(after_recovery.get(path), Some(bytes));
        }

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(reopened.inspect_operation(&operation_id).unwrap().len(), 4);
        let stable_job = reopened.inspect_job(job_id).unwrap();
        assert_eq!(stable_job.len(), 3);
        assert_eq!(
            stable_job.last().unwrap().state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        let stable = persistent_store_material(&store);
        assert_eq!(stable, after_recovery);
        let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
            files
                .iter()
                .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                .collect::<std::collections::BTreeMap<_, _>>()
        };
        std::fs::write(
            root.join("ticket-return-crash-evidence.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": checkpoint,
                "operation_id": operation_id,
                "operation_revision_count_before_and_after": 4,
                "command_sha256": command_sha256,
                "job_id": job_id,
                "job_revision_before_kill": 2,
                "job_state_before_kill": "running",
                "job_state_after_reopen": "unknown",
                "unknown_revision": 3,
                "child_exit": killed.to_string(),
                "events": event_lines,
                "report_count_before_and_after": 0,
                "pre_kill_store_sha256": hash_map(&pre_kill),
                "recovered_store_sha256": hash_map(&after_recovery),
                "repeat_reopen_stable": true,
                "claim_after_recovery": false,
                "executor_invocations": 0,
                "worker_process_started": false,
                "engine_or_ffi_called": false,
                "scope": "synthetic process kill after durable ticket return and before executor invocation; no production worker or engine evidence"
            })).unwrap(),
        ).unwrap();
    }

    #[test]
    fn running_job_crash_after_report_temp_sync_before_publish_recovers_unknown_once() {
        if std::env::var_os(REPORT_TEMP_CRASH_MODE).is_some() {
            let root = std::path::PathBuf::from(
                std::env::var_os(REPORT_TEMP_CRASH_ROOT).expect("report-temp crash root"),
            );
            execute_child_until_report_temp_sync(&root);
        }

        let root = report_temp_crash_root();
        let marker = root.join("report-temp-checkpoint.json");
        let events = root.join("events.log");
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&events)
            .unwrap();
        let child_output = std::fs::File::create(root.join("child-output.log")).unwrap();
        let mut child = CrashChild(
            std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    REPORT_TEMP_CRASH_TEST,
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env_remove("YGO_H3_CRASH_CHECKPOINT")
                .env_remove("YGO_H3_CRASH_MARKER")
                .env_remove(RUNNING_EXECUTOR_CRASH_MODE)
                .env_remove(RUNNING_EXECUTOR_CRASH_ROOT)
                .env_remove(RUNNING_EXECUTOR_CRASH_MARKER)
                .env_remove(EXECUTOR_RETURN_CRASH_MODE)
                .env_remove(EXECUTOR_RETURN_CRASH_ROOT)
                .env_remove(EXECUTOR_RETURN_CRASH_MARKER)
                .env_remove(TICKET_RETURN_CRASH_MODE)
                .env_remove(TICKET_RETURN_CRASH_ROOT)
                .env_remove(TICKET_RETURN_CRASH_MARKER)
                .env_remove(REPORT_TEMP_CRASH_MODE)
                .env_remove(REPORT_TEMP_CRASH_ROOT)
                .env_remove(REPORT_TEMP_CRASH_MARKER)
                .env_remove(STORAGE_REPORT_TEMP_CRASH_MARKER)
                .env(REPORT_TEMP_CRASH_MODE, "1")
                .env(REPORT_TEMP_CRASH_ROOT, &root)
                .env(REPORT_TEMP_CRASH_MARKER, &marker)
                .env(STORAGE_REPORT_TEMP_CRASH_MARKER, &marker)
                .env(RUNNING_EXECUTOR_CRASH_EVENTS, &events)
                .stdout(std::process::Stdio::from(child_output.try_clone().unwrap()))
                .stderr(std::process::Stdio::from(child_output))
                .spawn()
                .unwrap(),
        );
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
        while !marker.is_file() && std::time::Instant::now() < deadline {
            if let Some(status) = child.0.try_wait().unwrap() {
                let output =
                    std::fs::read_to_string(root.join("child-output.log")).unwrap_or_default();
                panic!("child exited before report-temp checkpoint ({status}): {output}");
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(marker.is_file(), "child missed report-temp checkpoint");
        let checkpoint: Value = serde_json::from_slice(&std::fs::read(&marker).unwrap()).unwrap();
        assert_eq!(checkpoint["schema_version"], 1);
        assert_eq!(checkpoint["kind"], "h3_report_temp_synced_before_publish");
        assert_eq!(checkpoint["pid"].as_u64(), Some(u64::from(child.0.id())));
        let destination_name = checkpoint["destination_name"].as_str().unwrap();
        let report_id = destination_name.strip_suffix(".json").unwrap();
        assert_eq!(report_id.len(), 32);
        assert!(report_id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()));
        let temporary_name = checkpoint["temporary_name"].as_str().unwrap();
        let temporary_id = temporary_name
            .strip_prefix(".ygo-draft-")
            .and_then(|name| name.strip_suffix(".tmp"))
            .expect("recognized storage temporary name");
        assert_eq!(temporary_id.len(), 32);
        assert!(temporary_id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()));

        let store = root.join("jobs-store");
        let reports = store.join("reports");
        let temporary_path = reports.join(temporary_name);
        let report_path = reports.join(destination_name);
        let metadata = std::fs::symlink_metadata(&temporary_path).unwrap();
        assert!(metadata.is_file());
        assert!(!metadata.file_type().is_symlink());
        let temporary_bytes = std::fs::read(&temporary_path).unwrap();
        assert_eq!(
            checkpoint["bytes"].as_u64(),
            Some(temporary_bytes.len() as u64)
        );
        assert_eq!(checkpoint["sha256"], ygo_storage::hash(&temporary_bytes));
        assert!(!report_path.exists());
        assert_eq!(std::fs::read_dir(&reports).unwrap().count(), 1);

        let report: AnalysisReport = serde_json::from_slice(&temporary_bytes).unwrap();
        assert_eq!(report.schema_version, 2);
        let operation_dirs = std::fs::read_dir(store.join("operations"))
            .unwrap()
            .map(|entry| entry.unwrap().path())
            .collect::<Vec<_>>();
        assert_eq!(operation_dirs.len(), 1);
        let operation_id = operation_dirs[0]
            .file_name()
            .unwrap()
            .to_string_lossy()
            .into_owned();
        let operations = authenticated_operation_history(&store, &operation_id);
        assert_eq!(operations.len(), 4);
        assert_eq!(operations[0].state(), AnalysisOperationState::Allocated);
        assert_eq!(operations[1].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[2].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[3].state(), AnalysisOperationState::Accepted);
        let job_id = operations[3].job_id().unwrap();
        let command = operations[3].command().unwrap();
        let command_sha256 = command.checksum(operations[3].context()).unwrap();
        assert_eq!(
            operations[3].command_sha256(),
            Some(command_sha256.as_str())
        );
        let jobs = authenticated_job_history(&store, job_id);
        assert_eq!(jobs.len(), 2);
        assert_eq!(
            jobs[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        assert_eq!(
            jobs[1].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert!(jobs[1].report().is_none());
        assert_eq!(
            serde_json::to_value(&report.request).unwrap(),
            serde_json::to_value(&jobs[1].input().request).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&report.search.scoring).unwrap(),
            serde_json::to_value(&jobs[1].input().scoring).unwrap()
        );
        assert_eq!(
            serde_json::to_value(&report.search.budget).unwrap(),
            serde_json::to_value(&jobs[1].input().request.search).unwrap()
        );
        assert_eq!(
            jobs[1].input().binding_sha256,
            operations[3].frozen_input().unwrap().binding_sha256
        );
        assert_eq!(std::fs::read_dir(store.join("jobs")).unwrap().count(), 1);
        let event_lines = std::fs::read_to_string(&events)
            .unwrap()
            .lines()
            .map(str::to_owned)
            .collect::<Vec<_>>();
        assert_eq!(
            event_lines,
            [
                "freeze",
                "claim",
                "fake_executor_entered",
                "fake_executor_returned"
            ]
        );
        let pre_kill = persistent_store_material(&store);

        let killed = child.terminate();
        assert!(!killed.success());
        assert_eq!(persistent_store_material(&store), pre_kill);

        let recovered = match DurableAnalysisCoordinator::open_operations(store.clone()) {
            Ok(coordinator) => coordinator,
            Err(error) => {
                let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
                    files
                        .iter()
                        .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                        .collect::<std::collections::BTreeMap<_, _>>()
                };
                std::fs::write(
                    root.join("report-temp-crash-reproduction.json"),
                    serde_json::to_vec_pretty(&serde_json::json!({
                        "checkpoint": checkpoint,
                        "operation_id": operation_id,
                        "job_id": job_id,
                        "command_sha256": command_sha256,
                        "reopen_error": format!("{error:?}"),
                        "events": event_lines,
                        "temporary_report_sha256": ygo_storage::hash(&temporary_bytes),
                        "pre_kill_store_sha256": hash_map(&pre_kill),
                        "store_after_failed_reopen_sha256": hash_map(&persistent_store_material(&store)),
                        "scope": "synthetic child-process kill after report temp sync and before publication; fake executor only"
                    })).unwrap(),
                ).unwrap();
                panic!(
                    "reopen rejected synced orphan report temp; reproduction preserved: {error:?}"
                );
            }
        };
        assert_eq!(recovered.inspect_operation(&operation_id).unwrap().len(), 4);
        let job_history = recovered.inspect_job(job_id).unwrap();
        assert_eq!(job_history.len(), 3);
        assert_eq!(job_history[2].revision(), 3);
        assert_eq!(
            job_history[2].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Unknown
        );
        assert!(job_history[2].report().is_none());
        assert!(recovered.snapshot().unwrap().queued.is_none());
        assert!(recovered.snapshot().unwrap().running.is_none());
        assert!(recovered.claim_next(10_000).unwrap().is_none());
        assert!(recovered.inspect_report(report_id).is_err());
        drop(recovered);
        let after_recovery = persistent_store_material(&store);
        assert_eq!(after_recovery.len(), pre_kill.len() + 1);
        for (path, bytes) in &pre_kill {
            assert_eq!(after_recovery.get(path), Some(bytes));
        }
        assert_eq!(std::fs::read(&temporary_path).unwrap(), temporary_bytes);
        assert_eq!(std::fs::read_dir(&reports).unwrap().count(), 1);

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(reopened.inspect_operation(&operation_id).unwrap().len(), 4);
        assert_eq!(reopened.inspect_job(job_id).unwrap().len(), 3);
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        let stable = persistent_store_material(&store);
        assert_eq!(stable, after_recovery);

        let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
            files
                .iter()
                .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                .collect::<std::collections::BTreeMap<_, _>>()
        };
        std::fs::write(
            root.join("report-temp-crash-evidence.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": checkpoint,
                "operation_id": operation_id,
                "operation_revision_count_before_and_after": 4,
                "command_sha256": command_sha256,
                "job_id": job_id,
                "job_revision_before_kill": 2,
                "job_state_before_kill": "running",
                "job_state_after_reopen": "unknown",
                "unknown_revision": 3,
                "child_exit": killed.to_string(),
                "events": event_lines,
                "published_report_files_after_recovery": 0,
                "orphan_report_temp_preserved": true,
                "pre_kill_store_sha256": hash_map(&pre_kill),
                "recovered_store_sha256": hash_map(&after_recovery),
                "repeat_reopen_stable": true,
                "claim_after_recovery": false,
                "worker_process_started": false,
                "engine_or_ffi_called": false,
                "scope": "synthetic process kill after full report temp sync and before hard-link publication; no production worker or engine evidence"
            })).unwrap(),
        ).unwrap();
    }

    #[test]
    fn dispatch_admission_asset_mismatch_crash_keeps_terminal_failure() {
        if std::env::var_os(DISPATCH_ASSET_MISMATCH_CRASH_MODE).is_some() {
            let root = std::path::PathBuf::from(
                std::env::var_os(DISPATCH_ASSET_MISMATCH_CRASH_ROOT)
                    .expect("dispatch AssetMismatch crash root"),
            );
            execute_child_until_dispatch_asset_mismatch_checkpoint(&root);
        }

        let root = dispatch_asset_mismatch_crash_root();
        let marker = root.join("dispatch-asset-mismatch-checkpoint.txt");
        let events = root.join("events.log");
        std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&events)
            .unwrap();
        let child_output = std::fs::File::create(root.join("child-output.log")).unwrap();
        let mut child = CrashChild(
            std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    DISPATCH_ASSET_MISMATCH_CRASH_TEST,
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env(DISPATCH_ASSET_MISMATCH_CRASH_MODE, "1")
                .env(DISPATCH_ASSET_MISMATCH_CRASH_ROOT, &root)
                .env(
                    "YGO_H3_CRASH_CHECKPOINT",
                    DISPATCH_ASSET_MISMATCH_CHECKPOINT,
                )
                .env(DISPATCH_ASSET_MISMATCH_CRASH_MARKER, &marker)
                .env(DISPATCH_ASSET_MISMATCH_CRASH_EVENTS, &events)
                .env_remove(RUNNING_EXECUTOR_CRASH_MARKER)
                .env_remove(EXECUTOR_RETURN_CRASH_MARKER)
                .env_remove(TICKET_RETURN_CRASH_MARKER)
                .env_remove(REPORT_TEMP_CRASH_MARKER)
                .env_remove(STORAGE_REPORT_TEMP_CRASH_MARKER)
                .stdout(std::process::Stdio::from(child_output.try_clone().unwrap()))
                .stderr(std::process::Stdio::from(child_output))
                .spawn()
                .unwrap(),
        );
        let deadline = std::time::Instant::now() + std::time::Duration::from_secs(20);
        while !marker.is_file() && std::time::Instant::now() < deadline {
            if let Some(status) = child.0.try_wait().unwrap() {
                let output =
                    std::fs::read_to_string(root.join("child-output.log")).unwrap_or_default();
                panic!(
                    "child exited before dispatch AssetMismatch checkpoint ({status}): {output}"
                );
            }
            std::thread::sleep(std::time::Duration::from_millis(10));
        }
        assert!(
            marker.is_file(),
            "child missed dispatch AssetMismatch checkpoint"
        );
        assert_eq!(
            std::fs::read_to_string(&marker).unwrap().trim(),
            DISPATCH_ASSET_MISMATCH_CHECKPOINT
        );

        let store = root.join("jobs-store");
        let mut operation_ids = std::fs::read_dir(store.join("operations"))
            .unwrap()
            .map(|entry| entry.unwrap().file_name().to_string_lossy().into_owned())
            .collect::<Vec<_>>();
        operation_ids.sort();
        assert_eq!(operation_ids.len(), 1);
        let operation_id = operation_ids[0].clone();
        let operations = authenticated_operation_history(&store, &operation_id);
        assert_eq!(operations.len(), 4);
        assert_eq!(operations[0].state(), AnalysisOperationState::Allocated);
        assert_eq!(operations[1].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[2].state(), AnalysisOperationState::Accepting);
        assert_eq!(operations[3].state(), AnalysisOperationState::Accepted);
        let job_id = operations[3].job_id().unwrap().to_owned();
        assert!(operations[1..]
            .iter()
            .all(|operation| operation.job_id() == Some(job_id.as_str())));
        assert_eq!(
            operations[0]
                .begin(
                    operations[1].command().unwrap().clone(),
                    job_id.clone(),
                    operations[1].updated_at_ms(),
                )
                .unwrap()
                .encode_json()
                .unwrap(),
            operations[1].encode_json().unwrap()
        );
        assert_eq!(
            operations[1]
                .bind_input(
                    operations[2].frozen_input().unwrap().clone(),
                    operations[2].updated_at_ms(),
                )
                .unwrap()
                .encode_json()
                .unwrap(),
            operations[2].encode_json().unwrap()
        );
        assert_eq!(
            operations[2]
                .accept(operations[3].updated_at_ms())
                .unwrap()
                .encode_json()
                .unwrap(),
            operations[3].encode_json().unwrap()
        );
        let command_sha256 = operations[1].command_sha256().unwrap().to_owned();
        assert!(operations[1..]
            .iter()
            .all(|operation| operation.command_sha256() == Some(command_sha256.as_str())));
        let command = operations[1].command().unwrap();
        let command_bytes = serde_json::to_vec(&(
            "workbench-analysis-command-v1",
            &command.draft_id,
            &command.draft_revision,
            &command.opening_hand,
            command.seed,
            &command.rules,
            &command.catalog_id,
            &command.banlist_id,
            &command.as_of,
            &command.search,
            &operations[1].context().scoring,
            &operations[1].context().default_catalog_id,
        ))
        .unwrap();
        assert_eq!(command_sha256, ygo_storage::hash(&command_bytes));

        let jobs = authenticated_job_history(&store, &job_id);
        assert_eq!(jobs.len(), 3);
        assert_eq!(
            jobs[0].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Queued
        );
        assert_eq!(
            jobs[1].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Running
        );
        assert_eq!(
            jobs[2].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Failed
        );
        assert_eq!(
            jobs[2].error_code(),
            Some(crate::workbench_analysis::jobs::AnalysisJobFailure::AssetMismatch)
        );
        assert_eq!(
            jobs[0]
                .transition(
                    1,
                    crate::workbench_analysis::jobs::AnalysisJobEvent::Start,
                    jobs[1].updated_at_ms(),
                )
                .unwrap()
                .encode_json()
                .unwrap(),
            jobs[1].encode_json().unwrap()
        );
        assert_eq!(
            jobs[1]
                .transition(
                    2,
                    crate::workbench_analysis::jobs::AnalysisJobEvent::Fail(
                        crate::workbench_analysis::jobs::AnalysisJobFailure::AssetMismatch,
                    ),
                    jobs[2].updated_at_ms(),
                )
                .unwrap()
                .encode_json()
                .unwrap(),
            jobs[2].encode_json().unwrap()
        );
        assert_eq!(
            serde_json::to_value(operations[3].frozen_input().unwrap()).unwrap(),
            serde_json::to_value(jobs[0].input()).unwrap()
        );
        assert_eq!(std::fs::read_dir(store.join("jobs")).unwrap().count(), 1);
        assert_eq!(std::fs::read_dir(store.join("reports")).unwrap().count(), 0);

        let pre_kill = persistent_store_material(&store);
        let events_before_recovery = std::fs::read_to_string(&events).unwrap();
        assert_eq!(
            events_before_recovery.lines().collect::<Vec<_>>(),
            ["freeze", "claim", "dispatch_asset_mismatch_persisted"]
        );
        let killed = child.terminate();
        assert!(!killed.success());
        assert_eq!(persistent_store_material(&store), pre_kill);

        let recovered = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        let recovered_operations = recovered.inspect_operation(&operation_id).unwrap();
        assert_eq!(recovered_operations.len(), 4);
        assert_eq!(
            recovered_operations[3].state(),
            AnalysisOperationState::Accepted
        );
        let recovered_jobs = recovered.inspect_job(&job_id).unwrap();
        assert_eq!(recovered_jobs.len(), 3);
        assert_eq!(
            recovered_jobs[2].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Failed
        );
        assert_eq!(
            recovered_jobs[2].error_code(),
            Some(crate::workbench_analysis::jobs::AnalysisJobFailure::AssetMismatch)
        );
        assert!(recovered.snapshot().unwrap().queued.is_none());
        assert!(recovered.snapshot().unwrap().running.is_none());
        assert!(recovered.claim_next(10_000).unwrap().is_none());
        assert!(recovered.inspect_report(&job_id).is_err());
        drop(recovered);
        let after_recovery = persistent_store_material(&store);
        assert_eq!(after_recovery, pre_kill);

        let reopened = DurableAnalysisCoordinator::open_operations(store.clone()).unwrap();
        assert_eq!(reopened.inspect_operation(&operation_id).unwrap().len(), 4);
        let reopened_jobs = reopened.inspect_job(&job_id).unwrap();
        assert_eq!(reopened_jobs.len(), 3);
        assert_eq!(
            reopened_jobs[2].state(),
            crate::workbench_analysis::jobs::AnalysisJobState::Failed
        );
        assert!(reopened.claim_next(10_001).unwrap().is_none());
        drop(reopened);
        let stable = persistent_store_material(&store);
        assert_eq!(stable, after_recovery);

        let hash_map = |files: &std::collections::BTreeMap<String, Vec<u8>>| {
            files
                .iter()
                .map(|(path, bytes)| (path.clone(), ygo_storage::hash(bytes)))
                .collect::<std::collections::BTreeMap<_, _>>()
        };
        std::fs::write(
            root.join("dispatch-asset-mismatch-crash-evidence.json"),
            serde_json::to_vec_pretty(&serde_json::json!({
                "checkpoint": DISPATCH_ASSET_MISMATCH_CHECKPOINT,
                "operation_id": operation_id,
                "operation_revision_count": operations.len(),
                "command_sha256": command_sha256,
                "job_id": job_id,
                "job_states_before_kill": ["queued", "running", "failed"],
                "failure_before_and_after_reopen": "asset_mismatch",
                "child_exit": killed.to_string(),
                "events": events_before_recovery.lines().collect::<Vec<_>>(),
                "executor_invocations": 0,
                "published_reports": 0,
                "pre_kill_store_sha256": hash_map(&pre_kill),
                "recovered_store_sha256": hash_map(&after_recovery),
                "repeat_reopen_stable": true,
                "claim_after_recovery": false,
                "worker_process_started": false,
                "engine_or_ffi_called": false,
                "scope": "synthetic process kill in HTTP dispatch admission AssetMismatch settlement before in-memory queue update"
            })).unwrap(),
        ).unwrap();
    }
}
