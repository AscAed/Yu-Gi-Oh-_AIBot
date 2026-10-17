//! Explicit fixture maintenance: same raw duels, newly observed query fields.
use ygo_engine_adapter::*;
use ygo_goal::*;
#[test]
#[ignore = "opt-in: recapture unchanged raw prefixes with supplemental v6 query fields; charged"]
fn recapture_public_query_fields_without_rewriting_raw_duel_history() {
    assert_eq!(std::env::var("YGO_REFRESH_V6_CAPTURES").as_deref(), Ok("1"));
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let prototype: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = root.join(format!(
        "data/runtime/tournament-2026/query-public-refresh/{stamp}"
    ));
    std::fs::create_dir_all(&dir).unwrap();
    for name in ["resource", "ash", "reveal"] {
        let path = root.join(format!("tests/fixtures/tournament-2026.trace-{name}.json"));
        let bytes = std::fs::read(&path).unwrap();
        std::fs::write(dir.join(format!("{name}.before.json")), &bytes).unwrap();
        let mut v: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
        let expected = v["frames"]
            .as_array()
            .unwrap()
            .iter()
            .map(|r| serde_json::from_value::<Vec<u8>>(r.clone()).unwrap())
            .collect::<Vec<_>>();
        let decisions: Vec<Decision> =
            serde_json::from_value(v["result"]["resolved_decisions"].clone()).unwrap();
        let old: Vec<QueryWitness> = serde_json::from_value(v["witnesses"].clone()).unwrap();
        let mut q: RunDuelRequest =
            serde_json::from_value(prototype["cases"][0]["runtime_request"].clone()).unwrap();
        q.engine = engine.clone();
        if name == "reveal" {
            q.opening_hand = serde_json::from_value(v["opening_hand"].clone()).unwrap();
        }
        if name == "ash" {
            q.interruption.as_mut().unwrap().policy = "ash_effect_once".into();
            q.interruption.as_mut().unwrap().effect_id = "78449284:deck_special".into();
        }
        let journal = CallJournal::open(
            dir.join(format!("{name}.jsonl")),
            name,
            &digest(&bytes),
            512,
        )
        .unwrap();
        let adapter = JournaledAdapter::new(
            ProcessEngineAdapter::new(engine.clone()),
            journal.clone(),
            CallPurpose::Audit,
        );
        let mut witnesses = vec![];
        for w in old {
            q.decisions = decisions
                .iter()
                .filter(|d| d.prompt_id < w.event)
                .cloned()
                .collect();
            let actual = adapter.run(&q).unwrap();
            assert_eq!(
                actual.events.iter().map(|e| &e.raw).collect::<Vec<_>>(),
                expected[..w.event as usize].iter().collect::<Vec<_>>()
            );
            witnesses.push(QueryWitness::capture(&actual).unwrap());
        }
        q.decisions = decisions.clone();
        let result = adapter.run(&q).unwrap();
        assert_eq!(result.resolved_decisions, decisions);
        assert_eq!(
            result.events.iter().map(|e| &e.raw).collect::<Vec<_>>(),
            expected.iter().collect::<Vec<_>>()
        );
        assert!(result
            .checkpoint
            .cards
            .iter()
            .all(|c| c.is_public.is_some()));
        let receipt = verify_query_replays(&q, &result, &witnesses, journal.clone()).unwrap();
        assert!(receipt.matches(&q, &result, &witnesses));
        let mut saved = result.clone();
        saved.events.clear();
        saved.peak_working_set_bytes = None;
        v["result"] = serde_json::to_value(saved).unwrap();
        v["witnesses"] = serde_json::to_value(witnesses).unwrap();
        let mut output = serde_json::to_vec_pretty(&v).unwrap();
        output.push(b'\n');
        std::fs::write(&path, output).unwrap();
        println!(
            "{name}: {} charged calls; archive {}",
            journal.stats().unwrap().consumed,
            dir.display()
        );
    }
}
