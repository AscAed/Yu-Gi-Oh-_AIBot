use ygo_engine_adapter::*;
use ygo_knowledge::first_turn::{verification::*, FirstTurnKnowledge};

#[test]
#[ignore = "opt-in: refreshed rule cases plus native Scythe Ash qualification; charged outside matrix"]
fn current_query_cases_and_actual_ash_response_grant_only_scoped_qualification() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let mut suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let ash: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-ash.json"
    ))
    .unwrap();
    suite.cases.extend(ash.cases);
    let dependencies: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-dependencies.json"
    ))
    .unwrap();
    suite.cases.extend(dependencies.cases);
    let assets = root.join("data/runtime/tournament-2026/frozen");
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    let environment = NativeEnvironment {
        engine,
        asset_root: &assets,
        store: &store,
        catalog_id: active["catalog_id"].as_str().unwrap(),
        banlist_id: active["banlist_id"].as_str().unwrap(),
    };
    let dir = std::env::var_os("YGO_RESUME_RULE_DIR")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| {
            root.join("data/runtime/tournament-2026/rule-audits")
                .join(format!(
                    "resource-ash-{}",
                    std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap()
                        .as_nanos()
                ))
        });
    let prior: usize = std::fs::read(dir.join("report.json"))
        .ok()
        .and_then(|bytes| serde_json::from_slice::<NativeVerificationReport>(&bytes).ok())
        .map(|r| r.cases.iter().map(|c| c.ledger.consumed).sum())
        .unwrap_or(0);
    let report = verify_cases(&pack, &suite, &environment, &dir).unwrap();
    std::fs::write(
        dir.join("report.json"),
        serde_json::to_vec_pretty(&report).unwrap(),
    )
    .unwrap();
    assert!(
        report.passed,
        "{:?}",
        report
            .cases
            .iter()
            .filter(|c| !c.passed)
            .map(|c| (&c.case_id, &c.error))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        report
            .cases
            .iter()
            .map(|c| c.ledger.consumed)
            .sum::<usize>(),
        93
    );
    let audit_dir = dir.join(format!(
        "independent-audit-{}",
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let view = ygo_knowledge::first_turn::certification::VerifiedKnowledge::audit(
        &pack,
        &suite,
        &report,
        &environment,
        &dir,
        &audit_dir,
    )
    .unwrap();
    assert_eq!(view.certificates().len(), 12);
    assert_eq!(
        view.verified_ash_effects()
            .iter()
            .map(|r| r.id.as_str())
            .collect::<Vec<_>>(),
        vec!["78449284:deck_special"]
    );
    assert!(view.require_verified_coverage().is_err());
    std::fs::write(
        audit_dir.join("report.json"),
        serde_json::to_vec_pretty(&view.audits()[0]).unwrap(),
    )
    .unwrap();
    std::fs::write(audit_dir.join("qualification.json"),serde_json::to_vec_pretty(&serde_json::json!({"id":view.id(),"certificates":view.certificates(),"knowledge_id":view.knowledge().id(),"scope":"runtime view constructed by fresh audit; diagnostic JSON cannot mint qualification"})).unwrap()).unwrap();
    println!(
        "native rule execution93 (new {}) + independent qualification93; reports={}",
        93usize.saturating_sub(prior),
        dir.display()
    );
}

fn case() -> NativeCase {
    serde_json::from_value(serde_json::json!({
        "id":"scythe-positive","rule_id":"78449284:deck_special","kind":"positive",
        "scope":"independent_rule_verification","deck":{"main":[],"extra":[],"side":[]},
        "opening_hand":[],"seed":1,"decisions":[],"focus":0,"observation":"own_main_window",
        "assertions":[{"kind":"count","card_id":46072770,"player":0,"location":4,"count":1}],
        "branch":"detach one material; summon a PK from deck","limitations":["other targets not covered"]
    })).unwrap()
}

#[test]
fn case_contract_requires_legal_inputs_focus_and_independent_assertions() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let mut c = case();
    assert!(c.validate(&pack).is_err());
    c.deck = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.deck.json"
    ))
    .unwrap();
    c.opening_hand = vec![83566725, 46072770, 25538345, 44088353, 99745551]
        .into_iter()
        .map(ygo_domain::CardId)
        .collect();
    c.decisions = vec![Decision {
        prompt_id: 1,
        player: 0,
        choice: Choice::Command {
            command: 5,
            index: 0,
        },
    }];
    c.validate(&pack).unwrap();
    c.assertions[0] = NativeAssertion::Count {
        card_id: 46072770,
        player: 2,
        location: 4,
        count: 0,
    };
    assert!(c.validate(&pack).is_err());
    c.assertions.clear();
    assert!(c.validate(&pack).is_err());
    let mut c = case();
    c.kind = CaseKind::Negative;
    c.focus = None;
    assert!(c.validate(&pack).is_err());
}

#[test]
fn an_ash_response_case_is_a_separate_branch_and_requires_an_ashable_target() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let mut suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let mut value = serde_json::to_value(&suite.cases[8]).unwrap();
    value["kind"] = serde_json::json!("ash_response");
    let c: NativeCase = serde_json::from_value(value).expect("explicit native Ash branch kind");
    c.validate(&pack).unwrap();
    suite.cases = vec![c.clone()];
    suite.validate(&pack).unwrap();
    let mut wrong = c;
    wrong.rule_id = "83566725:deck_set".into();
    assert!(
        wrong.validate(&pack).is_err(),
        "deck setting alone is not an Ash target"
    );
}

#[test]
fn event_assertions_use_raw_frames_not_forged_decoded_fields() {
    let assertion = NativeAssertion::Event {
        opcode: 50,
        fields: serde_json::json!({"code":14558127,"from":{"location":2},"to":{"location":16}}),
        count: 1,
    };
    let mut after = DuelResult::failure(WorkerError::new("test", "test", "test"));
    after.events.push(CoreEventFrame {
        sequence: 1,
        opcode: 50,
        raw: vec![50],
        supported: true,
        fields: serde_json::json!({"code":14558127,"from":{"location":2},"to":{"location":16}}),
    });
    assert!(assertion.check(&after, &after, 0).is_err());
}

#[test]
fn material_filter_evidence_requires_a_real_material_prompt_with_identified_candidates() {
    let v: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-resource.json"
    ))
    .unwrap();
    let raw: Vec<u8> = v["frames"]
        .as_array()
        .unwrap()
        .iter()
        .find(|raw| raw[0] == 26)
        .map(|raw| serde_json::from_value(raw.clone()).unwrap())
        .unwrap();
    let mut r = DuelResult::failure(WorkerError::new(
        "recorded",
        "test",
        "recorded parser case, not native qualification",
    ));
    r.events = vec![decode_frame(1, &raw).unwrap()];
    r.prompt = parse_prompt(1, &raw).unwrap();
    let positive = NativeAssertion::MaterialOption {
        card_id: 83566725,
        player: 0,
        offered: true,
    };
    positive.check(&r, &r, 0).unwrap();
    let absent = NativeAssertion::MaterialOption {
        card_id: 26692769,
        player: 0,
        offered: false,
    };
    absent.check(&r, &r, 0).unwrap();
    let wrong = NativeAssertion::MaterialOption {
        card_id: 83566725,
        player: 0,
        offered: false,
    };
    assert!(wrong.check(&r, &r, 0).is_err());
    r.events = vec![decode_frame(
        1,
        &serde_json::from_value::<Vec<u8>>(v["frames"][7].clone()).unwrap(),
    )
    .unwrap()];
    r.prompt = parse_prompt(1, &r.events[0].raw).unwrap();
    assert!(
        absent.check(&r, &r, 0).is_err(),
        "no material prompt cannot prove a continuous prohibition"
    );
}

#[test]
fn effect_resolution_requires_matching_activation_and_no_actual_negation() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let rule = pack.rule("78449284:deck_special").unwrap();
    let mut result = DuelResult::failure(WorkerError::new("test", "test", "test"));
    result.events = vec![CoreEventFrame {
        sequence: 1,
        opcode: 70,
        raw: vec![],
        supported: true,
        fields: serde_json::json!({"code":78449284,"description":rule.description,"chain":1,"player":0,"trigger_location":4}),
    }];
    assert!(resolution_witness(rule, &result, 0).is_err());
}

#[test]
fn a_partial_case_suite_never_claims_full_verified_coverage() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite = NativeCases {
        schema_version: 1,
        knowledge_id: pack.id(),
        cases: vec![],
    };
    assert!(suite.validate(&pack).is_err());
}

#[test]
fn continuous_rules_cannot_be_verified_by_an_absent_activation_option() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let mut c = suite
        .cases
        .iter()
        .find(|c| c.kind == CaseKind::Negative)
        .unwrap()
        .clone();
    c.rule_id = "42141493:shared_mulcharmy_activation_limit".into();
    assert!(c.validate(&pack).is_err());
    c.kind = CaseKind::ContinuousNegative;
    c.validate(&pack).unwrap();
    c.rule_id = "78449284:two_dark_level_three".into();
    assert!(c.validate(&pack).is_err());
}

#[test]
fn delayed_counterexamples_require_the_completed_end_phase_boundary() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let mut c = suite.cases[0].clone();
    c.rule_id = "42141493:end_phase_random_hand_reduction".into();
    c.kind = CaseKind::DelayedNegative;
    c.focus = None;
    assert!(c.validate(&pack).is_err());
    c.observation = Observation::EndPhaseComplete;
    c.validate(&pack).unwrap();
    c.kind = CaseKind::Continuous;
    assert!(c.validate(&pack).is_err());
}

#[test]
fn a_special_procedure_is_not_confused_with_a_legal_normal_summon() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let rule = pack.rule("83566725:empty_field_special").unwrap();
    let mut action = ActionMetadata {
        choice: Choice::Command {
            command: 0,
            index: 0,
        },
        source: Some(CardReference {
            code: 83566725,
            player: 0,
            location: 2,
            sequence: 0,
            position: 0,
        }),
        effect_description: None,
        selected: vec![],
        selection_group: None,
    };
    assert!(bind_test_choice(rule, &action, CaseKind::Procedure).is_none());
    action.choice = Choice::Command {
        command: 1,
        index: 0,
    };
    assert!(bind_test_choice(rule, &action, CaseKind::Procedure).is_some());
}

#[test]
fn generic_trigger_confirmation_remains_explicitly_pending_actual_chain_identity() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let rule = pack.rule("83566725:deck_set").unwrap();
    let action = ActionMetadata {
        choice: Choice::YesNo { yes: true },
        source: Some(CardReference {
            code: 83566725,
            player: 0,
            location: 4,
            sequence: 0,
            position: 1,
        }),
        effect_description: Some(221),
        selected: vec![],
        selection_group: None,
    };
    let binding = bind_test_choice(rule, &action, CaseKind::Positive).unwrap();
    assert_eq!(binding.kind, "generic_trigger_requires_chain_confirmation");
    assert_eq!(binding.expected_description, rule.description);
}

#[test]
fn native_report_contract_recomputes_provenance_coverage_and_call_roles() {
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    // Portable shape fixture, not a replacement for the independent native audit.
    let value: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let good: NativeVerificationReport = serde_json::from_value(value.clone()).unwrap();
    good.validate_contract(&pack, &suite).unwrap();
    for (path, replacement) in [
        (vec!["passed"], serde_json::json!(false)),
        (vec!["complete_coverage"], serde_json::json!(true)),
        (vec!["cases", "0", "before_call"], serde_json::json!(0)),
        (
            vec!["cases", "0", "replay_calls"],
            serde_json::json!([4, 3]),
        ),
        (
            vec!["cases", "0", "binding", "kind"],
            serde_json::json!("exact_effect_description"),
        ),
        (vec!["cases", "0", "branch"], serde_json::json!("invented")),
        (
            vec!["cases", "0", "ledger", "consumed"],
            serde_json::json!(513),
        ),
        (
            vec![
                "cases",
                "0",
                "runtime_request",
                "first_turn",
                "knowledge_id",
            ],
            serde_json::json!(format!("first-turn-knowledge-{}", "0".repeat(64))),
        ),
    ] {
        let mut changed = value.clone();
        let mut cursor = &mut changed;
        for component in &path[..path.len() - 1] {
            cursor = if let Ok(i) = component.parse::<usize>() {
                &mut cursor[i]
            } else {
                &mut cursor[*component]
            };
        }
        let last = path.last().unwrap();
        cursor[*last] = replacement;
        let report: NativeVerificationReport = serde_json::from_value(changed).unwrap();
        assert!(report.validate_contract(&pack, &suite).is_err(), "{path:?}");
    }
}

#[test]
fn new_case_and_report_json_reject_unknown_nested_legacy_fields() {
    let suite: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let mut changed = suite.clone();
    changed["cases"][0]["decisions"][0]["choice"]["invented_effect"] = true.into();
    assert!(serde_json::from_value::<NativeCases>(changed).is_err());
    let mut changed = suite;
    changed["cases"][0]["deck"]["injected_card"] = 14558127.into();
    assert!(serde_json::from_value::<NativeCases>(changed).is_err());
    let mut report: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    report["cases"][0]["runtime_request"]["versions"]["verified"] = true.into();
    assert!(serde_json::from_value::<NativeVerificationReport>(report).is_err());
}

#[test]
#[ignore = "opt-in: frozen independent 2026 assets; manual native cases, not planner coverage"]
fn resource_cases_resolve_replay_and_resume_without_extra_charges() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    let mut engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join(format!(
        "target/debug/ygo-engine-worker{}",
        std::env::consts::EXE_SUFFIX
    ));
    let assets = root.join("data/runtime/tournament-2026/frozen");
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let environment = NativeEnvironment {
        engine,
        asset_root: &assets,
        store: &store,
        catalog_id: pointer["catalog_id"].as_str().unwrap(),
        banlist_id: pointer["banlist_id"].as_str().unwrap(),
    };
    let output = root
        .join("data/runtime/tournament-2026/rule-audits")
        .join(format!(
            "resource-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let first = verify_cases(&pack, &suite, &environment, &output).unwrap();
    first.validate_contract(&pack, &suite).unwrap();
    for case in &first.cases {
        assert!(case.passed, "{}: {:?}", case.case_id, case.error);
    }
    assert!(first.passed);
    assert!(!first.complete_coverage);
    assert_eq!(first.missing_rules.len(), 80);
    assert_eq!(
        first.cases.iter().map(|c| c.ledger.consumed).sum::<usize>(),
        42
    );
    let resumed = verify_cases(&pack, &suite, &environment, &output).unwrap();
    assert_eq!(
        serde_json::to_value(&first).unwrap(),
        serde_json::to_value(&resumed).unwrap()
    );
    let audit_dir = output.join("independent-audit");
    let qualified = ygo_knowledge::first_turn::certification::VerifiedKnowledge::audit(
        &pack,
        &suite,
        &first,
        &environment,
        &output,
        &audit_dir,
    )
    .unwrap();
    assert_eq!(qualified.certificates().len(), 6);
    assert!(qualified.require_verified_coverage().is_err());
    assert!(qualified.verified_ash_effects().is_empty());
    assert_eq!(qualified.knowledge().id(), pack.id());
    let audit = &qualified.audits()[0];
    assert_eq!(
        audit.cases.iter().map(|c| c.ledger.consumed).sum::<usize>(),
        42
    );
    let qualified_repeat = ygo_knowledge::first_turn::certification::VerifiedKnowledge::audit(
        &pack,
        &suite,
        &first,
        &environment,
        &output,
        &audit_dir,
    )
    .unwrap();
    assert_eq!(qualified.id(), qualified_repeat.id());
    let repeat = &qualified_repeat.audits()[0];
    assert_eq!(
        repeat
            .cases
            .iter()
            .map(|c| c.ledger.consumed)
            .sum::<usize>(),
        84
    );
    let mut forged = first.clone();
    forged.cases[2].resolution_events[0] += 1;
    assert!(verify_report(
        &pack,
        &suite,
        &forged,
        &environment,
        &output,
        &output.join("forged-audit")
    )
    .is_err());
    assert!(!output.join("forged-audit").read_dir().unwrap().any(|f| f
        .unwrap()
        .path()
        .extension()
        .is_some_and(|e| e == "jsonl")));
    std::fs::write(
        output.join("report.json"),
        serde_json::to_vec_pretty(&resumed).unwrap(),
    )
    .unwrap();
}
