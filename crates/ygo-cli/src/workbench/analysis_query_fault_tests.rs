// Included inside the private HTTP test module; no production fixture surface.
fn query_tree_snapshot(root: &std::path::Path) -> std::collections::BTreeMap<String, String> {
    fn visit(
        base: &std::path::Path,
        path: &std::path::Path,
        out: &mut std::collections::BTreeMap<String, String>,
    ) {
        let mut paths: Vec<_> = std::fs::read_dir(path)
            .unwrap()
            .map(|x| x.unwrap().path())
            .collect();
        paths.sort();
        for path in paths {
            let name = path
                .strip_prefix(base)
                .unwrap()
                .to_string_lossy()
                .into_owned();
            if path.is_dir() {
                out.insert(name, "directory".into());
                visit(base, &path, out);
            } else if path.file_name().and_then(|name| name.to_str()) == Some(".ygo-analysis.lock")
            {
                // Windows denies reads of the lock held by this coordinator.
                // Protect its presence and metadata without releasing the lock.
                let metadata = std::fs::metadata(&path).unwrap();
                out.insert(
                    name,
                    format!(
                        "held-lock:{}:{:?}",
                        metadata.len(),
                        metadata.modified().unwrap()
                    ),
                );
            } else {
                out.insert(name, ygo_storage::hash(&std::fs::read(path).unwrap()));
            }
        }
    }
    let mut out = std::collections::BTreeMap::new();
    visit(root, root, &mut out);
    out
}

#[test]
fn stopped_http_queries_authenticate_saved_material_without_writing() {
    let mut results = Vec::new();
    for case in [
        "healthy",
        "report_missing",
        "report_hash",
        "request",
        "identity",
        "scoring",
        "budget",
        "operation_chain",
        "job_chain",
    ] {
        let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("../../target/w1h22a-persistence-fault-tests/query-fixtures")
            .join(ygo_storage::secure_random_hex(16).unwrap());
        std::fs::create_dir_all(&root).unwrap();
        let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
        std::fs::write(&engine.script_manifest_path, b"{}").unwrap();
        let saved = drafts.create(draft.clone()).unwrap();
        let frozen = crate::workbench_analysis::freeze_analysis_input(
            &drafts,
            crate::workbench_analysis::AnalysisFreezeSpec {
                draft_id: saved.id,
                expected_revision: saved.revision,
                opening_hand: draft.main[..5].to_vec(),
                seed: 1,
                rules: "ocg-mr5".into(),
                catalog_id: None,
                banlist_id: banlist,
                as_of: "2026-10-30".into(),
                search: Default::default(),
            },
            engine.clone(),
            &snapshots,
            &catalog,
        )
        .unwrap();
        let store_root = root.join("jobs-store");
        let coordinator =
            Arc::new(DurableAnalysisCoordinator::open_operations(store_root.clone()).unwrap());
        let context = AnalysisOperationContext {
            scoring: Default::default(),
            default_catalog_id: catalog,
            configuration_sha256: "a".repeat(64),
        };
        let operation = coordinator
            .allocate_operation(context.clone(), now().unwrap())
            .unwrap();
        let job = coordinator
            .submit(frozen, Default::default(), now().unwrap())
            .unwrap();
        let ticket = coordinator.claim_next(now().unwrap()).unwrap().unwrap();
        let input = ticket.input();
        let report = ygo_api::combo::AnalysisReport {
            schema_version: 2,
            request: input.request.clone(),
            runtime_request: input.runtime_request.clone(),
            search: ygo_search::combo::SearchReport {
                termination: "exhausted".into(),
                lines: vec![],
                stats: Default::default(),
                diagnostics: vec![],
                scoring: Default::default(),
                budget: input.request.search.clone(),
            },
            card_names: Default::default(),
        };
        let (terminal, _) = coordinator
            .publish_report(
                &ticket,
                &serde_json::to_vec(&report).unwrap(),
                now().unwrap(),
            )
            .unwrap();
        coordinator.stop_dispatch().unwrap();
        let reference = terminal.report().unwrap();
        let report_path = store_root
            .join("reports")
            .join(format!("{}.json", reference.report_id));
        let revision_path = store_root
            .join("jobs")
            .join(job.job_id())
            .join("revisions/3.json");
        match case {
            "report_missing" => std::fs::remove_file(&report_path).unwrap(),
            "report_hash" => std::fs::write(&report_path, b"{}").unwrap(),
            "job_chain" => std::fs::write(&revision_path, b"{}").unwrap(),
            "operation_chain" => std::fs::write(
                store_root
                    .join("operations")
                    .join(operation.operation_id())
                    .join("revisions/1.json"),
                b"{}",
            )
            .unwrap(),
            "request" | "identity" | "scoring" | "budget" => {
                // Rebind the content hash to ensure rejection reaches semantic binding,
                // rather than being masked by a stale raw-file hash.
                let mut value = serde_json::to_value(&report).unwrap();
                match case {
                    "request" => {
                        value["request"]["seed"] = 2.into();
                        value["runtime_request"]["seed"] = 2.into();
                    }
                    "identity" => {
                        value["runtime_request"]["versions"]["engine_sha256"] =
                            "b".repeat(64).into()
                    }
                    "scoring" => value["search"]["scoring"]["follow_up"] = 99.into(),
                    "budget" => {
                        value["search"]["budget"]["node_budget"] = 1.into();
                        value["request"]["search"]["node_budget"] = 1.into();
                    }
                    _ => unreachable!(),
                }
                let bytes = serde_json::to_vec(&value).unwrap();
                std::fs::write(&report_path, &bytes).unwrap();
                let mut envelope: Value =
                    serde_json::from_slice(&std::fs::read(&revision_path).unwrap()).unwrap();
                envelope["record"]["report"]["sha256"] = ygo_storage::hash(&bytes).into();
                let rebound = crate::workbench_analysis::jobs::AnalysisJobRecordV1::read_json(
                    &serde_json::to_vec(&envelope["record"]).unwrap(),
                )
                .unwrap();
                envelope["record_sha256"] =
                    ygo_storage::hash(&rebound.encode_json().unwrap()).into();
                std::fs::write(&revision_path, serde_json::to_vec(&envelope).unwrap()).unwrap();
            }
            _ => (),
        }
        if matches!(case, "request" | "identity" | "scoring" | "budget") {
            assert_eq!(
                coordinator.inspect_report(job.job_id()).unwrap_err().code(),
                "job_report_binding_mismatch",
                "semantic boundary for {case}"
            );
        }
        let service = Arc::new(AnalysisHttpService {
            coordinator: coordinator.clone(),
            context,
            drafts: Arc::new(drafts),
            snapshots,
            engine,
            accepting: AtomicBool::new(true),
            background: Mutex::new(vec![]),
            freeze_gate: None,
            response_fault: Mutex::new(None),
            freeze_control: None,
        });
        let mut config = WorkbenchConfig::local_default();
        config.drafts_dir = root.join("http-drafts");
        let mut server = WorkbenchServer::start(config).unwrap();
        server.analysis = Some(service);
        let addr = server.local_addr();
        let token = server.token().to_owned();
        let stop = Arc::new(AtomicBool::new(false));
        let stopping = stop.clone();
        let thread = std::thread::spawn(move || server.serve_until(&stopping).unwrap());
        let before = query_tree_snapshot(&store_root);
        let path = format!("/api/analysis-jobs/{}", job.job_id());
        let result = request(addr, &token, "GET", &format!("{path}/result"), Value::Null);
        assert_eq!(
            result.0,
            if case == "healthy" { 200 } else { 503 },
            "{case}: {result:?}"
        );
        if case == "operation_chain" {
            assert_eq!(
                request(
                    addr,
                    &token,
                    "GET",
                    &format!("/api/analysis-operations/{}", operation.operation_id()),
                    Value::Null
                )
                .0,
                503
            );
        }
        if case != "healthy" {
            assert_eq!(request(addr, &token, "GET", &path, Value::Null).0, 503);
        }
        if case == "healthy" {
            let state = request(addr, &token, "GET", &path, Value::Null);
            assert_eq!(state.0, 200);
            assert_eq!(state.1["service_state"], "stopped");
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
                    &format!("/api/analysis-operations/{}", operation.operation_id()),
                    Value::Null
                )
                .0,
                200
            );
        }
        assert_eq!(
            before,
            query_tree_snapshot(&store_root),
            "GET mutated {case}"
        );
        assert!(coordinator.claim_next(now().unwrap()).is_err());
        stop.store(true, Ordering::SeqCst);
        thread.join().unwrap();
        results.push(serde_json::json!({"case":case,"status":result.0,"tree_unchanged":true}));
    }
    let output = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1h22a-persistence-fault-tests/query-matrix.json");
    std::fs::write(output, serde_json::to_vec_pretty(&results).unwrap()).unwrap();
}
