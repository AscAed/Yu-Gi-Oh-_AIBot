use ygo_engine_adapter::*;
use ygo_goal::*;
#[test]
#[ignore = "opt-in: freshly generated real effect-verification.json and frozen engine"]
fn real_costs_and_shared_search_resource_do_not_become_independent_gains() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    let adapter = ProcessEngineAdapter::new(engine);
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let report: serde_json::Value = serde_json::from_slice(
        &std::fs::read(root.join("data/runtime/effect-verification.json")).unwrap(),
    )
    .unwrap();
    for effect in ["25538345:mill", "90432163:search"] {
        let case = report["cases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|c| c["effect_id"] == effect)
            .unwrap();
        assert_eq!(case["passed"], true);
        assert_eq!(case["independent_replay"], true);
        let mut q: RunDuelRequest =
            serde_json::from_value(case["runtime_request"].clone()).unwrap();
        let observation: DuelResult = serde_json::from_value(case["observation"].clone()).unwrap();
        let selected: Decision =
            serde_json::from_value(case["positive"]["selected"].clone()).unwrap();
        let i = observation
            .resolved_decisions
            .iter()
            .position(|d| d == &selected)
            .unwrap();
        q.engine = adapter.config.clone();
        q.decisions = observation.resolved_decisions[..i].to_vec();
        let before = adapter.run(&q).unwrap();
        assert_eq!(
            serde_json::to_value(&before.checkpoint).unwrap(),
            case["positive"]["before_checkpoint"]
        );
        q.decisions = observation.resolved_decisions.clone();
        let after = adapter.run(&q).unwrap();
        assert_eq!(after.events, observation.events);
        assert_eq!(after.checkpoint, observation.checkpoint);
        let a = actual_facts(&before, &Default::default(), &pack);
        let b = actual_facts(&after, &Default::default(), &pack);
        let delta = |f: &Filter| count(f, &b).unwrap() - count(f, &a).unwrap();
        let hand = Filter {
            locations: vec![2],
            ..Default::default()
        };
        if effect == "25538345:mill" {
            assert_eq!(delta(&hand), -1);
        } else {
            assert_eq!(delta(&hand), 1);
            assert!(
                delta(&Filter {
                    locations: vec![2, 16],
                    ..Default::default()
                }) <= 0
            );
            let boots = delta(&Filter {
                codes: vec![36426778],
                locations: vec![2],
                ..Default::default()
            });
            let scales = delta(&Filter {
                codes: vec![25538345],
                locations: vec![2],
                ..Default::default()
            });
            assert!(boots + scales <= 1);
            assert_ne!(
                Truth::all([
                    if boots >= 1 { Truth::Yes } else { Truth::No },
                    if scales >= 1 { Truth::Yes } else { Truth::No }
                ]),
                Truth::Yes
            );
        }
        assert!(case["engine_calls"].as_u64().unwrap() + 2 <= 512);
    }
}
