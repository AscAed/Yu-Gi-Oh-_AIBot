//! Independent, explicit human preparations. Never imported by the planner.
use ygo_engine_adapter::*;
use ygo_knowledge::first_turn::{verification::*, FirstTurnKnowledge};

#[test]
#[ignore = "opt-in: manually prepare Rusty material filter; requires YGO_WRITE_DEPENDENCY_CASES=1"]
fn prepare_rusty_material_filter_cases_from_the_independent_human_prefix() {
    assert_eq!(
        std::env::var("YGO_WRITE_DEPENDENCY_CASES").as_deref(),
        Ok("1")
    );
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let human: serde_json::Value =
        serde_json::from_slice(
            &std::fs::read(root.join(
                "data/runtime/tournament-2026/pilot-human/1792212553961543000/pass.report.json",
            ))
            .unwrap(),
        )
        .unwrap();
    let mut q: RunDuelRequest = serde_json::from_value(human["request"].clone()).unwrap();
    q.decisions.retain(|d| d.prompt_id < 138);
    let dir = root
        .join("data/runtime/tournament-2026/dependency-preparation")
        .join(format!(
            "rusty-filter-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    std::fs::create_dir_all(&dir).unwrap();
    let journal = CallJournal::open(
        dir.join("preparation.jsonl"),
        "rusty-material-filter",
        &pack.id(),
        512,
    )
    .unwrap();
    let adapter = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::RuleVerification,
    );
    let mut r = adapter.run(&q).unwrap();
    let intents = [(5, 46072770), (0, 25538345), (1, 65741786)];
    let mut stage = 0;
    for _ in 0..40 {
        assert!(r.error.is_none(), "{:?}", r.error);
        let p = r.prompt.as_ref().unwrap();
        if stage == intents.len() {
            break;
        }
        let metadata = prompt_metadata(p.id, &r.events.last().unwrap().raw).unwrap();
        let (command, code) = intents[stage];
        let chosen = metadata.iter().find(|m| {
            matches!(m.choice,Choice::Command{command:c,..}if c==command)
                && m.source.as_ref().is_some_and(|s| s.code == code)
        });
        let choice = if let Some(m) = chosen {
            stage += 1;
            m.choice.clone()
        } else if let Some(m) = metadata.iter().find(|m| {
            matches!(m.choice, Choice::Cards { .. })
                && m.selected.len() == 1
                && m.selected[0].code == 25538345
        }) {
            m.choice.clone()
        } else {
            p.actions
                .iter()
                .find(|a| {
                    matches!(
                        a.choice,
                        Choice::Chain { index: None }
                            | Choice::Place { .. }
                            | Choice::Position { position: 1 }
                            | Choice::YesNo { yes: false }
                    )
                })
                .unwrap_or_else(|| panic!("unexpected manual filter prep: {p:?}"))
                .choice
                .clone()
        };
        q.decisions = r.resolved_decisions.clone();
        q.decisions.push(Decision {
            prompt_id: p.id,
            player: p.player,
            choice,
        });
        r = adapter.run(&q).unwrap();
    }
    q.decisions = r.resolved_decisions.clone();
    std::fs::write(
        dir.join("observed.json"),
        serde_json::to_vec_pretty(
            &serde_json::json!({"request":q,"result":r,"ledger":journal.stats().unwrap()}),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(stage, 3);
    assert_eq!(
        r.prompt.as_ref().unwrap().opcode,
        26,
        "expected actual material filter"
    );
    let replay = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::Replay,
    )
    .run(&q)
    .unwrap();
    assert_eq!(r.events, replay.events);
    assert_eq!(r.checkpoint, replay.checkpoint);
    let count = |card_id, location, count| NativeAssertion::Count {
        card_id,
        player: 0,
        location,
        count,
    };
    let base=NativeCase{id:"rusty-link-material-prohibition-positive".into(),rule_id:"26692769:cannot_link_material".into(),kind:CaseKind::Continuous,scope:"independent_rule_verification".into(),deck:q.deck,opening_hand:q.opening_hand,seed:1,decisions:q.decisions,focus:None,observation:Observation::DecisionWindow,assertions:vec![count(26692769,4,1),count(46072770,4,1),count(25538345,4,1),count(65741786,64,1),NativeAssertion::MaterialOption{card_id:26692769,player:0,offered:false},NativeAssertion::MaterialOption{card_id:46072770,player:0,offered:true},NativeAssertion::MaterialOption{card_id:25538345,player:0,offered:true}],branch:"Rusty is present but excluded from the actual I:P material picker; two ordinary DARK bodies remain eligible".into(),limitations:vec!["Independent human preparation. Only the declared material-filter scope is tested; this does not certify I:P planning or the preparation effects.".into()]};
    base.validate(&pack).unwrap();
    let mut counter = base.clone();
    counter.id = "rusty-prohibition-does-not-ban-other-bodies".into();
    counter.kind = CaseKind::ContinuousNegative;
    counter.branch="the prohibition on Rusty does not prevent the actual picker offering Decayed Cloak and Torn Scales".into();
    counter.assertions.retain(|a| {
        !matches!(
            a,
            NativeAssertion::MaterialOption {
                card_id: 26692769,
                ..
            }
        )
    });
    let cases = [base, counter];
    let path = root.join("tests/fixtures/tournament-2026.rules-dependencies.json");
    let mut suite: NativeCases = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let ids = cases
        .iter()
        .map(|c| c.id.clone())
        .collect::<std::collections::BTreeSet<_>>();
    suite.cases.retain(|c| !ids.contains(&c.id));
    suite.cases.extend(cases);
    std::fs::write(
        path,
        format!("{}\n", serde_json::to_string_pretty(&suite).unwrap()),
    )
    .unwrap();
    let path = root.join("knowledge/tournament-2026.verification-registry.json");
    let mut value: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let list = value["cases"].as_array_mut().unwrap();
    list.retain(|c| !ids.contains(c["case_id"].as_str().unwrap()));
    for c in suite.cases.iter().filter(|c| ids.contains(&c.id)) {
        list.push(serde_json::json!({"case_id":c.id,"rule_id":c.rule_id,"kind":c.kind,"case_sha256":ygo_knowledge::hash(&serde_json::to_vec(c).unwrap())}));
    }
    std::fs::write(
        path,
        format!("{}\n", serde_json::to_string_pretty(&value).unwrap()),
    )
    .unwrap();
    println!(
        "manual material-filter preparation calls={}; evidence={}",
        journal.stats().unwrap().consumed,
        dir.display()
    );
}

#[test]
#[ignore = "opt-in: author declared manual cases; charged; requires YGO_WRITE_DEPENDENCY_CASES=1"]
fn prepare_normal_set_and_reveal_cases_using_only_actual_legal_prompts() {
    assert_eq!(
        std::env::var("YGO_WRITE_DEPENDENCY_CASES").as_deref(),
        Ok("1")
    );
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let template: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let mut base: RunDuelRequest =
        serde_json::from_value(template["cases"][0]["runtime_request"].clone()).unwrap();
    base.engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    base.decisions.clear();
    let dir = root
        .join("data/runtime/tournament-2026/dependency-preparation")
        .join(format!(
            "{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    std::fs::create_dir_all(&dir).unwrap();
    let count = |card_id, location, count| NativeAssertion::Count {
        card_id,
        player: 0,
        location,
        count,
    };
    let recipes = [
        (
            "soleret-normal-positive",
            83566725,
            0,
            true,
            false,
            vec![83566725, 46072770, 25538345, 44088353, 99745551],
            vec![
                count(83566725, 4, 1),
                NativeAssertion::Event {
                    opcode: 60,
                    fields: serde_json::json!({"code":83566725}),
                    count: 1,
                },
                NativeAssertion::Event {
                    opcode: 61,
                    fields: serde_json::json!({}),
                    count: 1,
                },
            ],
        ),
        (
            "soleret-normal-monster-set-positive",
            83566725,
            3,
            true,
            false,
            vec![83566725, 46072770, 25538345, 44088353, 99745551],
            vec![
                count(83566725, 4, 1),
                NativeAssertion::Instance {
                    card_id: 83566725,
                    player: 0,
                    location: 4,
                    sequence: 0,
                    level: None,
                    rank: None,
                    position: Some(8),
                    materials: None,
                    attribute: None,
                    status_all: None,
                },
            ],
        ),
        (
            "soleret-normal-used-negative",
            83566725,
            0,
            false,
            true,
            vec![83566725, 83566725, 46072770, 25538345, 44088353],
            vec![
                count(83566725, 2, 1),
                count(83566725, 4, 1),
                NativeAssertion::Event {
                    opcode: 60,
                    fields: serde_json::json!({"code":83566725}),
                    count: 1,
                },
            ],
        ),
        (
            "decay-reveal-special-positive",
            46072770,
            5,
            true,
            false,
            vec![83566725, 46072770, 25538345, 44088353, 99745551],
            vec![
                count(46072770, 4, 1),
                count(25538345, 2, 1),
                NativeAssertion::Event {
                    opcode: 31,
                    fields: serde_json::json!({"cards":[{"code":25538345,"location":2,"player":0,"sequence":3}],"player":1}),
                    count: 1,
                },
                NativeAssertion::Reason {
                    card_id: 46072770,
                    player: 0,
                    from: 2,
                    to: 4,
                    all_bits: 2048,
                    count: 1,
                },
            ],
        ),
    ];
    let mut cases = vec![];
    let mut calls = 0;
    for (id, code, command, positive, closed, hand, assertions) in recipes {
        let journal =
            CallJournal::open(dir.join(format!("{id}.jsonl")), id, &pack.id(), 512).unwrap();
        let adapter = JournaledAdapter::new(
            ProcessEngineAdapter::new(base.engine.clone()),
            journal.clone(),
            CallPurpose::RuleVerification,
        );
        let mut q = base.clone();
        q.opening_hand = hand.into_iter().map(ygo_domain::CardId).collect();
        let mut r = adapter.run(&q).unwrap();
        let focus = r.resolved_decisions.len();
        let mut started = false;
        let mut exposed = false;
        for _ in 0..40 {
            assert!(r.error.is_none(), "{id}: {:?}", r.error);
            let p = r
                .prompt
                .as_ref()
                .expect("manual preparation stopped before its witness");
            if started && (p.opcode == 11 || !closed && p.opcode == 12) {
                break;
            }
            let metadata = prompt_metadata(p.id, &r.events.last().unwrap().raw).unwrap();
            let semantic = metadata.iter().find(|m| {
                if !started {
                    matches!(m.choice,Choice::Command{command:c,..} if c==command)
                        && m.source.as_ref().is_some_and(|s| s.code == code)
                } else {
                    command == 5
                        && !exposed
                        && matches!(m.choice, Choice::Cards { .. })
                        && m.selected.len() == 1
                        && m.selected[0].code == 25538345
                }
            });
            let choice = if let Some(m) = semantic {
                if started {
                    exposed = true;
                } else {
                    started = true;
                }
                m.choice.clone()
            } else {
                p.actions
                    .iter()
                    .find(|a| {
                        matches!(
                            a.choice,
                            Choice::Chain { index: None }
                                | Choice::Place { .. }
                                | Choice::Position { position: 1 }
                                | Choice::YesNo { yes: false }
                        )
                    })
                    .unwrap_or_else(|| panic!("{id}: unexpected manual prompt {p:?}"))
                    .choice
                    .clone()
            };
            q.decisions = r.resolved_decisions.clone();
            q.decisions.push(Decision {
                prompt_id: p.id,
                player: p.player,
                choice,
            });
            r = adapter.run(&q).unwrap();
        }
        assert!(started);
        q.decisions = r.resolved_decisions.clone();
        let replay = JournaledAdapter::new(
            ProcessEngineAdapter::new(base.engine.clone()),
            journal.clone(),
            CallPurpose::Replay,
        )
        .run(&q)
        .unwrap();
        assert_eq!(replay.events, r.events);
        assert_eq!(replay.checkpoint, r.checkpoint);
        calls += journal.stats().unwrap().consumed;
        std::fs::write(
            dir.join(format!("{id}.json")),
            serde_json::to_vec_pretty(
                &serde_json::json!({"request":q,"result":r,"calls":journal.stats().unwrap()}),
            )
            .unwrap(),
        )
        .unwrap();
        let rule_id = if command == 5 {
            "46072770:reveal_and_special".to_owned()
        } else {
            format!("{code}:normal_summon_and_set")
        };
        let kind = if !positive {
            CaseKind::ProcedureNegative
        } else if command == 5 {
            CaseKind::Positive
        } else {
            CaseKind::Procedure
        };
        let case = NativeCase { id:id.into(),rule_id,kind,scope:"independent_rule_verification".into(),deck:q.deck,opening_hand:q.opening_hand,seed:1,decisions:q.decisions,focus:positive.then_some(focus),observation:if closed{Observation::OwnMainWindow}else{Observation::DecisionWindow},assertions,branch:format!("manual {id}; source and destination asserted from native events"),limitations:vec!["Independent rule preparation, not planner output or a tournament sample; other branches remain unverified.".into()] };
        case.validate(&pack).unwrap();
        cases.push(case);
    }
    // A hand with no other Phantom Knights card cannot pay the reveal cost.
    let negative = NativeCase {
        id: "decay-no-reveal-target-negative".into(),
        rule_id: "46072770:reveal_and_special".into(),
        kind: CaseKind::Negative,
        scope: "independent_rule_verification".into(),
        deck: base.deck.clone(),
        opening_hand: vec![46072770, 99745551, 99745551, 44088353, 10045474]
            .into_iter()
            .map(ygo_domain::CardId)
            .collect(),
        seed: 1,
        decisions: vec![],
        focus: None,
        observation: Observation::OwnMainWindow,
        assertions: vec![count(46072770, 2, 1)],
        branch: "Decayed Cloak in hand, no other Phantom Knights card to reveal".into(),
        limitations: vec!["Independent legal hand; not a tournament evaluation sample.".into()],
    };
    negative.validate(&pack).unwrap();
    cases.push(negative);
    let path = root.join("tests/fixtures/tournament-2026.rules-dependencies.json");
    let mut suite: NativeCases = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let new_ids = cases
        .iter()
        .map(|c| c.id.clone())
        .collect::<std::collections::BTreeSet<_>>();
    suite.cases.retain(|c| !new_ids.contains(&c.id));
    suite.cases.extend(cases);
    std::fs::write(
        &path,
        format!("{}\n", serde_json::to_string_pretty(&suite).unwrap()),
    )
    .unwrap();
    let registry = root.join("knowledge/tournament-2026.verification-registry.json");
    let mut value: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&registry).unwrap()).unwrap();
    let list = value["cases"].as_array_mut().unwrap();
    list.retain(|v| !new_ids.contains(v["case_id"].as_str().unwrap()));
    for c in suite.cases.iter().filter(|c| new_ids.contains(&c.id)) {
        list.push(serde_json::json!({"case_id":c.id,"rule_id":c.rule_id,"kind":c.kind,"case_sha256":ygo_knowledge::hash(&serde_json::to_vec(c).unwrap())}));
    }
    std::fs::write(
        registry,
        format!("{}\n", serde_json::to_string_pretty(&value).unwrap()),
    )
    .unwrap();
    println!("manual preparation+replay calls={calls}; native per-case assertions and qualification still required; evidence={}",dir.display());
}
