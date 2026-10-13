use ygo_api::combo::*;
use ygo_engine_adapter::*;
use ygo_search::combo::*;
fn report() -> AnalysisReport {
    let mut request: ComboAnalyzeRequest =
        serde_json::from_str(include_str!("../../../tests/fixtures/rabbit.request.json")).unwrap();
    request.catalog_id = Some("catalog-test".into());
    request.banlist_id = "banlist-test".into();
    let runtime = RunDuelRequest {
        protocol_version: 2,
        engine: Default::default(),
        deck: request.deck.clone(),
        opening_hand: request.opening_hand.clone(),
        seed: request.seed,
        decisions: vec![],
        versions: RuntimeVersions {
            rules: request.rules.clone(),
            catalog: "catalog-test".into(),
            banlist: "banlist-test".into(),
            ..Default::default()
        },
        probe_only: false,
    };
    let mut result = DuelResult::failure(WorkerError::new("fake", "test", ""));
    result.status = DuelStatus::EngineVerified;
    result.error = None;
    result.versions = runtime.versions.clone();
    let line = ComboLine {
        id: prefix_key(&runtime),
        decisions: vec![],
        evaluation: evaluate(&result.checkpoint, 0, &ScoringConfig::default()),
        result,
        replay_verified: true,
    };
    AnalysisReport {
        schema_version: 2,
        request,
        runtime_request: runtime,
        search: SearchReport {
            termination: "exhausted".into(),
            lines: vec![line],
            stats: Default::default(),
            diagnostics: vec![],
            scoring: Default::default(),
            budget: Default::default(),
        },
        card_names: Default::default(),
    }
}
#[test]
fn refuses_partial_prompt_or_falsely_verified_report_contracts() {
    let mut r = report();
    assert!(validate_report_contract(&r).is_ok());
    r.search.lines[0].result.status = DuelStatus::DecisionRequired;
    assert!(validate_report_contract(&r).is_err());
    r = report();
    r.search.lines[0].id = "fabricated".into();
    assert!(validate_report_contract(&r).is_err());
    r = report();
    r.request.seed += 1;
    assert!(validate_report_contract(&r).is_err());
    r = report();
    r.search.lines[0].result.resolved_decisions.push(Decision {
        prompt_id: 1,
        player: 0,
        choice: Choice::Finish,
    });
    assert!(validate_report_contract(&r).is_err());
}

#[test]
fn refuses_engine_verified_lines_with_unparsed_evidence() {
    let mut r = report();
    r.search.lines[0]
        .result
        .coverage_gaps
        .push("unknown opcode".into());
    assert!(validate_report_contract(&r).is_err());
}

#[test]
fn refuses_mismatched_search_budget_and_fabricated_score() {
    let mut r = report();
    r.search.budget.node_budget += 1;
    assert!(validate_report_contract(&r).is_err());
    r = report();
    r.search.lines[0].evaluation.total += 100.0;
    assert!(validate_report_contract(&r).is_err());
}
