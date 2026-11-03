//! Logical publish faults exercise real stores, transitions and HTTP projection.
use super::*;
use crate::workbench::{WorkbenchConfig, WorkbenchServer};
use crate::workbench_analysis::{
    operations::AnalysisOperationCommand, persistence::FaultPhase, tests::fixtures,
};
use std::path::PathBuf;

struct Fixture {
    root: PathBuf,
    service: Arc<AnalysisHttpService>,
    command: AnalysisOperationCommand,
}
impl Fixture {
    fn new() -> Self {
        Self::with_gate(None)
    }
    fn with_gate(gate: Option<(Arc<std::sync::Barrier>, Arc<std::sync::Barrier>)>) -> Self {
        let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22a-persistence-fault-tests/fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let command = AnalysisOperationCommand {
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
        let service = Arc::new(AnalysisHttpService {
            coordinator: Arc::new(
                DurableAnalysisCoordinator::open_operations(root.join("store")).unwrap(),
            ),
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
            freeze_gate: gate,
            response_fault: Mutex::new(None),
            freeze_control: None,
            accepting: AtomicBool::new(true),
            background: Mutex::new(Vec::new()),
        });
        Self {
            root,
            service,
            command,
        }
    }
    fn allocate(&self) -> AnalysisOperationRecordV1 {
        self.service
            .coordinator
            .allocate_operation(self.service.context.clone(), 100)
            .unwrap()
    }
    fn accepted(&self) -> AnalysisOperationRecordV1 {
        let op = self.allocate();
        self.service
            .coordinator
            .submit_operation(
                op.operation_id(),
                self.command.clone(),
                &self.service.context,
                101,
                &self.service.drafts,
                &self.service.snapshots,
                self.service.engine.clone(),
            )
            .unwrap()
    }
    fn inject(&self, chain: &str, state: &str, revision: u64, phase: FaultPhase) {
        self.service
            .coordinator
            .inject_logical_fault(chain, state, revision, phase);
    }
    fn get(&self, path: &str) -> (u16, Value) {
        self.service.route("GET", path, b"")
    }
}

fn snapshot(root: &std::path::Path) -> std::collections::BTreeMap<String, Vec<u8>> {
    fn scan(
        root: &std::path::Path,
        p: &std::path::Path,
        out: &mut std::collections::BTreeMap<String, Vec<u8>>,
    ) {
        for entry in std::fs::read_dir(p).unwrap() {
            let path = entry.unwrap().path();
            if path.is_dir() {
                out.insert(
                    format!("{}/", path.strip_prefix(root).unwrap().to_string_lossy()),
                    Vec::new(),
                );
                scan(root, &path, out)
            } else if path.file_name().unwrap() == ".ygo-analysis.lock" {
                out.insert(
                    path.strip_prefix(root)
                        .unwrap()
                        .to_string_lossy()
                        .into_owned(),
                    std::fs::metadata(&path)
                        .unwrap()
                        .len()
                        .to_le_bytes()
                        .to_vec(),
                );
            } else {
                out.insert(
                    path.strip_prefix(root)
                        .unwrap()
                        .to_string_lossy()
                        .into_owned(),
                    std::fs::read(path).unwrap(),
                );
            }
        }
    }
    let mut out = Default::default();
    scan(root, root, &mut out);
    out
}

#[test]
fn logical_publish_fault_matrix_stops_before_followup_and_preserves_reads() {
    let cases = [
        ("allocated", "operation", "allocated", 1),
        ("accepting", "operation", "accepting", 2),
        ("capacity_reject", "operation", "rejected", 2),
        ("context_reject", "operation", "rejected", 2),
        ("freeze_reject", "operation", "rejected", 3),
        ("bound_input", "operation", "accepting", 3),
        ("queued", "job", "queued", 1),
        ("accepted", "operation", "accepted", 4),
        ("running", "job", "running", 2),
        ("cancelled", "job", "cancelled", 2),
        ("failed", "job", "failed", 3),
        ("report_file", "report", "file", 0),
        ("report_terminal", "job", "completed", 3),
    ];
    let phases = [
        FaultPhase::BeforePublish,
        FaultPhase::AfterPublish,
        FaultPhase::Reread,
    ];
    let mut evidence = Vec::new();
    for (name, chain, state, revision) in cases {
        for (phase_index, phase) in phases.iter().enumerate() {
            let f = Fixture::new();
            let c = &f.service.coordinator;
            let mut op_id = None;
            let mut job_id = None;
            let result = match name {
                "allocated" => {
                    f.inject(chain, state, revision, *phase);
                    c.allocate_operation(f.service.context.clone(), 100)
                        .map(|_| ())
                        .map_err(|e| e.code())
                }
                "accepting" | "capacity_reject" | "context_reject" => {
                    if name == "capacity_reject" {
                        f.accepted();
                    }
                    let op = f.allocate();
                    op_id = Some(op.operation_id().to_owned());
                    let mut context = f.service.context.clone();
                    if name == "context_reject" {
                        context.configuration_sha256 = "b".repeat(64);
                    }
                    f.inject(chain, state, revision, *phase);
                    c.begin_operation(op.operation_id(), f.command.clone(), &context, 102)
                        .map(|_| ())
                        .map_err(|e| e.code())
                }
                "freeze_reject" | "bound_input" | "queued" | "accepted" => {
                    let op = f.allocate();
                    op_id = Some(op.operation_id().to_owned());
                    let mut command = f.command.clone();
                    if name == "freeze_reject" {
                        command.draft_revision = "b".repeat(64);
                    }
                    let begin = c
                        .begin_operation(op.operation_id(), command, &f.service.context, 101)
                        .unwrap();
                    job_id = begin.record.job_id().map(str::to_owned);
                    f.inject(chain, state, revision, *phase);
                    c.finish_operation(
                        begin.ticket.unwrap(),
                        102,
                        &f.service.drafts,
                        &f.service.snapshots,
                        f.service.engine.clone(),
                    )
                    .map(|_| ())
                    .map_err(|e| e.code())
                }
                _ => {
                    let op = f.accepted();
                    op_id = Some(op.operation_id().to_owned());
                    let job = op.job_id().unwrap();
                    job_id = Some(job.to_owned());
                    if name == "running" {
                        f.inject(chain, state, revision, *phase);
                        c.claim_next(103).map(|_| ()).map_err(|e| e.code())
                    } else if name == "cancelled" {
                        f.inject(chain, state, revision, *phase);
                        c.cancel(job, 1, 103).map(|_| ()).map_err(|e| e.code())
                    } else {
                        let ticket = c.claim_next(103).unwrap().unwrap();
                        f.inject(chain, state, revision, *phase);
                        if name == "failed" {
                            c.fail(&ticket, 104).map(|_| ()).map_err(|e| e.code())
                        } else {
                            let input = ticket.input();
                            let report = ygo_api::combo::AnalysisReport {
                                schema_version: 2,
                                request: input.request.clone(),
                                runtime_request: input.runtime_request.clone(),
                                search: ygo_search::combo::SearchReport {
                                    termination: "exhausted".into(),
                                    lines: Vec::new(),
                                    stats: Default::default(),
                                    diagnostics: Vec::new(),
                                    scoring: Default::default(),
                                    budget: input.request.search.clone(),
                                },
                                card_names: Default::default(),
                            };
                            c.publish_report(&ticket, &serde_json::to_vec(&report).unwrap(), 104)
                                .map(|_| ())
                                .map_err(|e| e.code())
                        }
                    }
                }
            };
            assert!(result.is_err(), "{name}/{phase_index} did not fail");
            assert_eq!(
                c.logical_fault_hits(),
                1,
                "{name}/{phase_index} target not entered"
            );
            let store = f.root.join("store");
            if name == "allocated" {
                let dirs: Vec<_> = std::fs::read_dir(store.join("operations"))
                    .unwrap()
                    .collect();
                if !dirs.is_empty() {
                    op_id = Some(
                        dirs[0]
                            .as_ref()
                            .unwrap()
                            .file_name()
                            .to_str()
                            .unwrap()
                            .to_owned(),
                    );
                }
            }
            let published = phase_index > 0;
            let target_path = if chain == "operation" {
                op_id.as_ref().map(|id| {
                    store
                        .join("operations")
                        .join(id)
                        .join("revisions")
                        .join(format!("{revision}.json"))
                })
            } else if chain == "job" {
                job_id.as_ref().map(|id| {
                    store
                        .join("jobs")
                        .join(id)
                        .join("revisions")
                        .join(format!("{revision}.json"))
                })
            } else {
                None
            };
            if let Some(path) = &target_path {
                assert_eq!(
                    path.exists(),
                    published,
                    "target persistence {name}/{phase_index}"
                );
                if published {
                    let value: Value =
                        serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
                    assert_eq!(
                        value["record"]["state"], state,
                        "saved target state {name}/{phase_index}"
                    );
                    assert_eq!(value["record"]["revision"], revision);
                }
            }
            let reports = std::fs::read_dir(store.join("reports")).unwrap().count();
            assert_eq!(
                reports,
                usize::from(name == "report_terminal" || name == "report_file" && published),
                "report count {name}/{phase_index}"
            );
            let stopped = c.is_stopped().unwrap();
            let expect_stopped =
                published || !matches!(name, "running" | "cancelled" | "failed" | "report_file");
            assert_eq!(stopped, expect_stopped, "stop policy {name}/{phase_index}");
            let active = c.active_snapshot_for_test().unwrap();
            assert_eq!(
                active.queued.is_some(),
                matches!(name, "capacity_reject" | "running" | "cancelled"),
                "retained queued slot {name}/{phase_index}"
            );
            assert_eq!(
                active.running.is_some(),
                matches!(name, "failed" | "report_file" | "report_terminal"),
                "retained running slot {name}/{phase_index}"
            );
            let before = snapshot(&store);
            let op_http = op_id
                .as_ref()
                .map(|id| f.get(&format!("/api/analysis-operations/{id}")));
            let job_http = job_id
                .as_ref()
                .map(|id| f.get(&format!("/api/analysis-jobs/{id}")));
            let result_http = job_id
                .as_ref()
                .map(|id| f.get(&format!("/api/analysis-jobs/{id}/result")));
            assert_eq!(snapshot(&store), before, "GET wrote {name}/{phase_index}");
            if let Some((status, _)) = &op_http {
                assert_eq!(
                    *status,
                    if name == "allocated" && !published {
                        503
                    } else {
                        200
                    },
                    "operation GET {name}/{phase_index}"
                );
            }
            let job_present = matches!(
                name,
                "accepted" | "running" | "cancelled" | "failed" | "report_file" | "report_terminal"
            ) || name == "queued" && published;
            if let Some((status, _)) = &job_http {
                assert_eq!(
                    *status,
                    if job_present { 200 } else { 404 },
                    "job GET {name}/{phase_index}"
                );
            }
            if let Some((status, _)) = &result_http {
                assert_eq!(
                    *status,
                    if !job_present {
                        404
                    } else if name == "report_terminal" && published {
                        200
                    } else {
                        409
                    },
                    "result GET {name}/{phase_index}"
                );
            }

            // No automatic operation, execution or replacement occurs after any fault.
            if c.is_stopped().unwrap() {
                assert!(c.claim_next(105).is_err());
            }
            let path = f.root.join("store").join(match chain {
                "operation" => "operations",
                "job" => "jobs",
                _ => "reports",
            });
            evidence.push(serde_json::json!({"case":name,"phase":format!("{phase:?}"),"target_entered":true,"error":result.unwrap_err(),"stopped":c.is_stopped().unwrap(),"operation_http":op_http.map(|x|x.0),"job_http":job_http.map(|x|x.0),"result_http":result_http.map(|x|x.0),"readonly_unchanged":true,"material_root_exists":path.exists(),"target_published":published,"target_revision":revision,"retained_queued":active.queued.is_some(),"retained_running":active.running.is_some(),"report_files":reports,"native_calls":0}));
        }
    }
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1h22a-persistence-fault-tests");
    std::fs::write(
        root.join("logical-matrix-results.json"),
        serde_json::to_vec_pretty(&evidence).unwrap(),
    )
    .unwrap();
}

#[test]
fn unknown_restart_classification_faults_preserve_certifiable_bytes() {
    let mut rows = Vec::new();
    for (index, phase) in [
        FaultPhase::BeforePublish,
        FaultPhase::AfterPublish,
        FaultPhase::Reread,
    ]
    .into_iter()
    .enumerate()
    {
        let f = Fixture::new();
        let op = f.accepted();
        let job = op.job_id().unwrap().to_owned();
        f.service.coordinator.claim_next(103).unwrap().unwrap();
        let root = f.root.join("store");
        drop(f);
        let (opened, hits) = DurableAnalysisCoordinator::open_operations_with_fault(
            root.clone(),
            "job",
            "unknown",
            3,
            phase,
        );
        assert_eq!(hits, 1, "unknown target not reached");
        assert!(opened.is_err());
        let path = root.join("jobs").join(&job).join("revisions/3.json");
        assert_eq!(path.exists(), index > 0);
        if index > 0 {
            let v: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
            assert_eq!(v["record"]["state"], "unknown");
        }
        // Reopening itself failed: no usable dispatch owner or executor was returned.
        rows.push(serde_json::json!({"case":"unknown","phase":format!("{phase:?}"),"target_hits":hits,"target_published":path.exists(),"dispatch_owner_returned":false,"error":opened.err().unwrap().code()}));
    }
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1h22a-persistence-fault-tests");
    std::fs::write(
        root.join("unknown-matrix-results.json"),
        serde_json::to_vec_pretty(&rows).unwrap(),
    )
    .unwrap();
}

fn submit_json(command: &AnalysisOperationCommand) -> Value {
    let mut v = serde_json::to_value(command).unwrap();
    v["schema_version"] = serde_json::json!(1);
    v["kind"] = serde_json::json!("analysis_submit");
    v
}
fn with_tcp(f: &Fixture, run: impl FnOnce(std::net::SocketAddr, &str)) {
    let mut config = WorkbenchConfig::local_default();
    config.drafts_dir = f.root.join("http-drafts");
    let mut server = WorkbenchServer::start(config).unwrap();
    server.analysis = Some(f.service.clone());
    let addr = server.local_addr();
    let token = server.token().to_owned();
    let stop = Arc::new(AtomicBool::new(false));
    let stopping = stop.clone();
    let handle = std::thread::spawn(move || server.serve_until(&stopping).unwrap());
    run(addr, &token);
    stop.store(true, Ordering::SeqCst);
    handle.join().unwrap();
}
#[test]
fn tcp_synchronous_faults_return_503_without_scheduling_freeze() {
    let mut rows = Vec::new();
    for name in [
        "allocated",
        "accepting",
        "capacity_reject",
        "context_reject",
        "cancelled",
    ] {
        for phase in [
            FaultPhase::BeforePublish,
            FaultPhase::AfterPublish,
            FaultPhase::Reread,
        ] {
            let f = Fixture::new();
            let mut path = "/api/analysis-operations".to_owned();
            let mut method = "POST";
            let mut body =
                serde_json::json!({"schema_version":1,"kind":"analysis_operation_allocate"});
            let (chain, state, revision) = if name == "allocated" {
                ("operation", "allocated", 1)
            } else if name == "cancelled" {
                let op = f.accepted();
                path = format!("/api/analysis-jobs/{}", op.job_id().unwrap());
                method = "DELETE";
                body = serde_json::json!({"schema_version":1,"kind":"analysis_cancel","expected_revision":1});
                ("job", "cancelled", 2)
            } else {
                if name == "capacity_reject" {
                    f.accepted();
                }
                let mut context = f.service.context.clone();
                if name == "context_reject" {
                    context.configuration_sha256 = "b".repeat(64);
                }
                let op = f
                    .service
                    .coordinator
                    .allocate_operation(context, 100)
                    .unwrap();
                path = format!("/api/analysis-operations/{}", op.operation_id());
                method = "PUT";
                body = submit_json(&f.command);
                (
                    "operation",
                    if name == "accepting" {
                        "accepting"
                    } else {
                        "rejected"
                    },
                    2,
                )
            };
            let freeze_before = f.service.coordinator.freeze_attempts_for_test();
            f.inject(chain, state, revision, phase);
            with_tcp(&f, |addr, token| {
                let response = super::tests::request(addr, token, method, &path, body);
                assert_eq!(response.0, 503, "{name}/{phase:?}: {}", response.1);
                assert_eq!(
                    response.1["error"]["code"],
                    if matches!(phase, FaultPhase::BeforePublish) {
                        "analysis_store_unverifiable"
                    } else {
                        "analysis_commit_uncertain"
                    }
                );
                assert!(f.service.background.lock().unwrap().is_empty());
                assert_eq!(
                    f.service.coordinator.freeze_attempts_for_test(),
                    freeze_before
                );
            });
            assert_eq!(f.service.coordinator.logical_fault_hits(), 1);
            assert!(f.service.background.lock().unwrap().is_empty());
            rows.push(serde_json::json!({"case":name,"phase":format!("{phase:?}"),"http":503,"target_hits":1,"scheduled_background_count":0,"freeze_attempts_before":freeze_before,"freeze_attempts_after":f.service.coordinator.freeze_attempts_for_test(),"actual_freeze_attempts":f.service.coordinator.freeze_attempts_for_test()-freeze_before}));
        }
    }
    std::fs::write(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22a-persistence-fault-tests/tcp-sync-matrix.json"),
        serde_json::to_vec_pretty(&rows).unwrap(),
    )
    .unwrap();
}
#[test]
fn tcp_202_background_faults_keep_persisted_state_and_stop() {
    let mut rows = Vec::new();
    for (name, chain, state, revision) in [
        ("bound_input", "operation", "accepting", 3),
        ("freeze_rejected", "operation", "rejected", 3),
        ("queued", "job", "queued", 1),
        ("accepted", "operation", "accepted", 4),
    ] {
        for phase in [
            FaultPhase::BeforePublish,
            FaultPhase::AfterPublish,
            FaultPhase::Reread,
        ] {
            let entered = Arc::new(std::sync::Barrier::new(2));
            let release = Arc::new(std::sync::Barrier::new(2));
            let f = Fixture::with_gate(Some((entered.clone(), release.clone())));
            let op = f.allocate();
            let path = format!("/api/analysis-operations/{}", op.operation_id());
            let mut cmd = f.command.clone();
            if name == "freeze_rejected" {
                cmd.draft_revision = "b".repeat(64);
            }
            f.inject(chain, state, revision, phase);
            with_tcp(&f, |addr, token| {
                let response = super::tests::request(addr, token, "PUT", &path, submit_json(&cmd));
                assert_eq!(response.0, 202);
                entered.wait();
                assert_eq!(f.service.coordinator.freeze_attempts_for_test(), 0);
                assert_eq!(f.service.background.lock().unwrap().len(), 1);
                assert_eq!(
                    f.service.coordinator.logical_fault_hits(),
                    0,
                    "freeze proceeded before release"
                );
                release.wait();
                for handle in f.service.background.lock().unwrap().drain(..) {
                    handle.join().unwrap();
                }
                assert_eq!(f.service.coordinator.logical_fault_hits(), 1);
                assert_eq!(f.service.coordinator.freeze_attempts_for_test(), 1);
                assert!(f.service.coordinator.is_stopped().unwrap());
                let before = snapshot(&f.root.join("store"));
                let get = super::tests::request(addr, token, "GET", &path, Value::Null);
                assert_eq!(get.0, 200);
                assert_eq!(
                    get.1["state"],
                    if !matches!(phase, FaultPhase::BeforePublish) && name == "accepted" {
                        "accepted"
                    } else if !matches!(phase, FaultPhase::BeforePublish)
                        && name == "freeze_rejected"
                    {
                        "rejected"
                    } else {
                        "accepting"
                    }
                );
                assert_eq!(snapshot(&f.root.join("store")), before);
                assert!(f.service.coordinator.claim_next(now().unwrap()).is_err());
                assert_eq!(f.service.coordinator.freeze_attempts_for_test(), 1);
                rows.push(serde_json::json!({"case":name,"phase":format!("{phase:?}"),"initial_http":202,"operation_http":get.0,"operation_state":get.1["state"],"scheduled_background_count":1,"actual_freeze_attempts":f.service.coordinator.freeze_attempts_for_test(),"target_hits":1,"stopped":true}));
            });
        }
    }
    std::fs::write(
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22a-persistence-fault-tests/tcp-background-matrix.json"),
        serde_json::to_vec_pretty(&rows).unwrap(),
    )
    .unwrap();
}

#[test]
fn tcp_cancel_and_claim_races_have_one_linearized_winner() {
    let mut results = Vec::new();
    for iteration in 0..16 {
        let f = Fixture::new();
        let operation = f.accepted();
        let job_id = operation.job_id().unwrap().to_owned();
        let job_path = format!("/api/analysis-jobs/{job_id}");
        let barrier = Arc::new(std::sync::Barrier::new(3));
        with_tcp(&f, |addr, token| {
            let claim_coordinator = f.service.coordinator.clone();
            let claim_barrier = barrier.clone();
            let claim = std::thread::spawn(move || {
                claim_barrier.wait();
                claim_coordinator.claim_next(now().unwrap()).unwrap()
            });
            let cancel_barrier = barrier.clone();
            let cancel_token = token.to_owned();
            let cancel_path = job_path.clone();
            let cancel = std::thread::spawn(move || {
                cancel_barrier.wait();
                super::tests::request(
                    addr,
                    &cancel_token,
                    "DELETE",
                    &cancel_path,
                    serde_json::json!({
                        "schema_version": 1,
                        "kind": "analysis_cancel",
                        "expected_revision": 1
                    }),
                )
            });
            barrier.wait();
            let ticket = claim.join().unwrap();
            let (status, response) = cancel.join().unwrap();
            let (expected_status, expected_state) = if let Some(ticket) = ticket {
                assert_eq!(
                    ticket.record().state(),
                    crate::workbench_analysis::jobs::AnalysisJobState::Running
                );
                assert_eq!(status, 409);
                assert_eq!(response["error"]["code"], "job_revision_conflict");
                f.service
                    .coordinator
                    .fail(&ticket, now().unwrap() + 1)
                    .unwrap();
                (200, "failed")
            } else {
                assert_eq!(status, 200);
                assert_eq!(response["state"], "cancelled");
                (200, "cancelled")
            };
            let (status, saved) = super::tests::request(addr, token, "GET", &job_path, Value::Null);
            assert_eq!(status, expected_status);
            assert_eq!(saved["state"], expected_state);
            results.push(serde_json::json!({
                "iteration": iteration,
                "claim_won": expected_state == "failed",
                "cancel_status": if expected_state == "cancelled" {200} else {409},
                "saved_state": expected_state,
                "native_calls": 0
            }));
        });
    }
    let output =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../target/w1h22b-concurrency-tests");
    std::fs::create_dir_all(&output).unwrap();
    std::fs::write(
        output.join("cancel-claim-races.json"),
        serde_json::to_vec_pretty(&results).unwrap(),
    )
    .unwrap();
}
