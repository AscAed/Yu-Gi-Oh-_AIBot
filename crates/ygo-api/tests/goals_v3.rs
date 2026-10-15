#[test]
#[ignore = "opt-in frozen engine: v3 fact goals and replay"]
fn changed_goals_change_choices_and_keep_pre_execution_evidence() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let mut ids = vec![];
    for name in ["goal-rusty", "goal-cherubini"] {
        let q: ygo_api::planning_v3::PlanRequest = serde_json::from_slice(
            &std::fs::read(root.join(format!("tests/fixtures/{name}.request.json"))).unwrap(),
        )
        .unwrap();
        let r = ygo_api::planning_v3::plan(
            q,
            engine.clone(),
            &store,
            active["catalog_id"].as_str().unwrap(),
            &Default::default(),
            pack.clone(),
        )
        .unwrap();
        std::fs::write(
            root.join(format!("data/runtime/{name}-report.json")),
            serde_json::to_vec_pretty(&r).unwrap(),
        )
        .unwrap();
        assert!(
            !r.recommendations.is_empty(),
            "{name}: {:?}, proposals {}, executions {}",
            r.failure_summary,
            r.proposals.plans.len(),
            r.executions.len()
        );
        assert!(r.ledger.used_calls + r.ledger.reserved_calls <= 512);
        assert!(ygo_api::planning_v3::replay(&r, engine.clone(), &store).is_ok());
        ids.push(r.recommendations[0].execution_id.clone());
        std::fs::write(
            root.join(format!("data/runtime/{name}-report.json")),
            serde_json::to_vec_pretty(&r).unwrap(),
        )
        .unwrap();
        let mut bad = r.clone();
        bad.goal_id = "forged".into();
        assert!(ygo_api::planning_v3::validate_plan_contract(&bad).is_err());
    }
    assert_ne!(ids[0], ids[1]);
}
#[test]
#[ignore = "opt-in frozen engine: availability and bounded continuation"]
fn available_effect_and_consuming_continuation_have_separate_witnesses() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    for name in ["goal-availability", "goal-continuation"] {
        let q: ygo_api::planning_v3::PlanRequest = serde_json::from_slice(
            &std::fs::read(root.join(format!("tests/fixtures/{name}.request.json"))).unwrap(),
        )
        .unwrap();
        let r = ygo_api::planning_v3::plan(
            q,
            engine.clone(),
            &store,
            active["catalog_id"].as_str().unwrap(),
            &Default::default(),
            pack.clone(),
        )
        .unwrap();
        std::fs::write(
            root.join(format!("data/runtime/{name}-report.json")),
            serde_json::to_vec_pretty(&r).unwrap(),
        )
        .unwrap();
        assert!(
            !r.recommendations.is_empty(),
            "{name}: {:?}, primary {}, executions {}",
            r.failure_summary,
            r.proposals.plans.len(),
            r.executions.len()
        );
        assert!(r.recommendations[0]
            .probes
            .iter()
            .all(|p| p.result.result == ygo_goal::Truth::Yes));
        if name == "goal-continuation" {
            assert!(r.recommendations[0].gains["hand_gain"] >= 1);
            assert!(r.recommendations[0]
                .probes
                .iter()
                .any(|p| !p.lost_conditions.is_empty()));
            let rejects = |bad: &ygo_api::planning_v3::PlanReport| {
                assert!(ygo_api::planning_v3::validate_plan_contract(bad).is_err())
            };
            let mut bad = r.clone();
            bad.recommendations[0]
                .probes
                .last_mut()
                .unwrap()
                .lost_conditions
                .push("/forged/not".into());
            rejects(&bad);
            let mut bad = r.clone();
            bad.executions[0].trace.predictions[0].reason = "posthoc".into();
            rejects(&bad);
            let mut bad = r.clone();
            bad.forecasts
                .values_mut()
                .find(|fs| !fs.is_empty())
                .unwrap()[0]
                .missing_nodes
                .push("forged".into());
            rejects(&bad);
            let mut bad = r.clone();
            bad.recommendations[0]
                .probes
                .last_mut()
                .unwrap()
                .gains
                .insert("hand_gain".into(), 999);
            rejects(&bad);
            let branch = r.recommendations[0].probes.last().unwrap().best.unwrap();
            let mut bad = r.clone();
            bad.executions[branch].runtime.decisions.clear();
            rejects(&bad);
            let mut bad = r.clone();
            bad.executions[branch].facts.cards[0].rank = Some(999);
            rejects(&bad);
            let mut bad = r.clone();
            bad.witnesses.values_mut().next().unwrap().replay_verified = false;
            rejects(&bad);
            let mut bad = r.clone();
            bad.analysis.runtime_request.scenario = Some("ryu-ran".into());
            rejects(&bad);
            let mut bad = r.clone();
            bad.executions[0].trace.observation.as_mut().unwrap().steps[0]
                .bytes
                .push(255);
            rejects(&bad);
            let mut bad = r.clone();
            bad.catalog_projection
                .get_mut(&ygo_domain::CardId(25538345))
                .unwrap()
                .level = 9;
            rejects(&bad);
            let mut bad = r.clone();
            let main = bad.recommendations[0].execution;
            bad.recommendations[0].probes.last_mut().unwrap().best = Some(usize::MAX);
            bad.assessments
                .iter_mut()
                .find(|a| a.execution == main)
                .unwrap()
                .probes
                .last_mut()
                .unwrap()
                .best = Some(usize::MAX);
            rejects(&bad);
        }
        ygo_api::planning_v3::replay(&r, engine.clone(), &store).unwrap();
    }
}
#[test]
#[ignore = "opt-in frozen engine: goal positives, negatives and safe fallback"]
fn goal_matrix_covers_history_conditions_and_safe_fallback() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    for (name, success) in [
        ("goal-initial", true),
        ("goal-no-target", true),
        ("goal-no-discard", true),
        ("goal-used-effect", true),
        ("goal-break-history", true),
        ("goal-unsupported", false),
        ("goal-budget", false),
        ("goal-budget-partial", true),
        ("goal-short-continuation", false),
        ("goal-shared-resource", false),
    ] {
        let q: ygo_api::planning_v3::PlanRequest = serde_json::from_slice(
            &std::fs::read(root.join(format!("tests/fixtures/{name}.request.json"))).unwrap(),
        )
        .unwrap();
        let r = ygo_api::planning_v3::plan(
            q,
            engine.clone(),
            &store,
            active["catalog_id"].as_str().unwrap(),
            &Default::default(),
            pack.clone(),
        )
        .unwrap();
        if name == "goal-break-history" {
            check_raw_history_oracle(&r);
            let mut bad = r.clone();
            let h = bad
                .executions
                .iter_mut()
                .flat_map(|e| &mut e.facts.history)
                .find(|h| h.kind == "destroyed" && h.card.code == 62709239)
                .unwrap();
            h.card.materials.clear();
            assert!(ygo_api::planning_v3::validate_plan_contract(&bad).is_err());
        }
        std::fs::write(
            root.join(format!("data/runtime/{name}-report.json")),
            serde_json::to_vec_pretty(&r).unwrap(),
        )
        .unwrap();
        println!(
            "{name}: {} recommendations, {}+{} calls, {:?}",
            r.recommendations.len(),
            r.ledger.used_calls,
            r.ledger.reserved_calls,
            r.failure_summary
        );
        assert_eq!(!r.recommendations.is_empty(), success, "{name}");
        if success {
            ygo_api::planning_v3::replay(&r, engine.clone(), &store).unwrap();
        } else {
            if name == "goal-budget" {
                assert!(r
                    .failure_summary
                    .contains(&ygo_planner::v2::FailureKind::BudgetExhausted));
            } else if name == "goal-unsupported" {
                assert!(r
                    .failure_summary
                    .contains(&ygo_planner::v2::FailureKind::CoverageGap));
            } else {
                assert!(r.failure_summary.iter().any(|f| matches!(
                    f,
                    ygo_planner::v2::FailureKind::NoPlanFound
                        | ygo_planner::v2::FailureKind::BudgetExhausted
                )));
            }
        }
        if name == "goal-budget-partial" {
            assert!(r
                .failure_summary
                .contains(&ygo_planner::v2::FailureKind::BudgetExhausted));
            assert!(r.ledger.used_calls + r.ledger.reserved_calls <= 128);
        }
        if name == "goal-initial" {
            assert!(r.executions[0].proposal.steps.is_empty());
        }
        if name == "goal-break-history" {
            assert!(r.executions[r.recommendations[0].execution]
                .facts
                .history
                .iter()
                .any(|h| h.kind == "xyz_summon" && h.card.proper_xyz == Some(true)));
        }
    }
}

// Independent event oracle: count every member of each successful 62/63
// batch and check the known cost/destruction sequence, without actual_facts.
fn check_raw_history_oracle(r: &ygo_api::planning_v3::PlanReport) {
    let mut covered = 0;
    let mut boots_twice = false;
    for execution in &r.executions {
        if !execution.trace.execution_verified {
            continue;
        }
        let Some(obs) = &execution.trace.observation else {
            continue;
        };
        let Some(destroyed) = execution
            .facts
            .history
            .iter()
            .find(|h| h.kind == "destroyed" && h.card.code == 62709239)
        else {
            continue;
        };
        let mut pending = vec![];
        let mut boots = 0;
        for e in &obs.events {
            if e.opcode == 62 {
                pending.push(&e.fields);
            }
            if e.opcode == 63 {
                let recorded: Vec<_> = execution
                    .facts
                    .history
                    .iter()
                    .filter(|h| h.kind == "special_summon" && h.event == e.sequence)
                    .collect();
                assert_eq!(recorded.len(), pending.len());
                let mut instances = std::collections::BTreeSet::new();
                for raw in pending.drain(..) {
                    let h = recorded
                        .iter()
                        .find(|h| {
                            serde_json::json!(h.card.code) == raw["code"]
                                && serde_json::json!(h.card.player) == raw["location"]["player"]
                                && serde_json::json!(h.card.sequence) == raw["location"]["sequence"]
                        })
                        .unwrap();
                    assert!(instances.insert(&h.card.instance));
                    if h.card.code == 36426778 {
                        boots += 1;
                    }
                }
            }
        }
        assert_eq!(
            execution
                .facts
                .history
                .iter()
                .filter(|h| h.kind == "special_summon" && h.card.code == 36426778)
                .count(),
            boots
        );
        if boots >= 2 {
            boots_twice = true;
            let at_most_one = ygo_goal::Expr::History {
                kind: "special_summon".into(),
                filter: ygo_goal::Filter {
                    codes: vec![36426778],
                    ..Default::default()
                },
                effect_id: None,
                reason_mask: None,
                min: 0,
                max: Some(1),
            };
            assert_eq!(
                ygo_goal::evaluate(&at_most_one, &execution.facts, &Default::default()).result,
                ygo_goal::Truth::No
            );
        }
        let detached = obs
            .events
            .iter()
            .find(|e| {
                e.sequence < destroyed.event
                    && e.opcode == 50
                    && e.fields["from"]["location"] == 132
                    && e.fields["to"]["location"] == 16
            })
            .unwrap();
        let remaining: Vec<_> = obs
            .events
            .iter()
            .filter(|e| {
                e.sequence > destroyed.event
                    && e.opcode == 50
                    && e.fields["from"]["location"] == 144
                    && e.fields["to"]["location"] == 16
            })
            .take(1)
            .map(|e| e.fields["code"].as_u64().unwrap() as u32)
            .collect();
        assert_eq!(destroyed.card.materials, remaining);
        assert_eq!(remaining.len(), 1);
        assert!(detached.fields["reason"].as_u64().unwrap() & 128 != 0);
        for h in execution
            .facts
            .history
            .iter()
            .filter(|h| h.card.code == 62709239)
        {
            if h.kind == "effect_resolved" && h.effect_id.as_deref() == Some("62709239:destroy") {
                assert_eq!(
                    h.card.materials, remaining,
                    "CHAINED activation snapshot must follow the cost and precede destruction"
                );
            }
            if h.kind == "sent_to_grave" || (h.kind == "effect_resolved" && h.card.location == 16) {
                assert!(h.card.materials.is_empty());
            }
        }
        covered += 1;
    }
    assert!(covered > 0);
    assert!(boots_twice, "one line must cover Boots summon plus revival");
}
