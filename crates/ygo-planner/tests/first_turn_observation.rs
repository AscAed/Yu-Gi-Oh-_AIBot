use ygo_engine_adapter::*;
use ygo_goal::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;

fn capture(text: &str) -> (DuelResult, Vec<QueryWitness>) {
    let mut v: serde_json::Value = serde_json::from_str(text).unwrap();
    v["result"]["events"] = serde_json::json!([]);
    let mut r: DuelResult = serde_json::from_value(v["result"].clone()).unwrap();
    r.events = v["frames"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
        .map(|(i, b)| {
            decode_frame(
                i as u64 + 1,
                &serde_json::from_value::<Vec<u8>>(b.clone()).unwrap(),
            )
            .unwrap()
        })
        .collect();
    (r, serde_json::from_value(v["witnesses"].clone()).unwrap())
}

#[test]
fn pending_triggers_are_not_usable_as_recovery_action_windows() {
    let (r, w) = capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-reveal.json"
    ));
    let error = actual_state(
        &r,
        &w,
        &Default::default(),
        &FirstTurnKnowledge::builtin().unwrap(),
    )
    .err()
    .unwrap();
    assert!(error.contains("own main action window"), "{error}");
}

#[test]
fn missing_printed_metadata_does_not_get_invented_from_the_visible_field() {
    let (r, w) = capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
    let error = actual_state(
        &r,
        &w,
        &Default::default(),
        &FirstTurnKnowledge::builtin().unwrap(),
    )
    .err()
    .unwrap();
    assert!(error.contains("printed card"), "{error}");
}

#[test]
#[ignore = "opt-in: frozen CDB metadata and fresh charged query replay; not autonomous recovery"]
fn actual_ash_resources_usage_and_materials_drive_the_causal_state() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let (result, witnesses) = capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let catalog = store
        .catalog(active["catalog_id"].as_str().unwrap())
        .unwrap();
    let report: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let mut request: RunDuelRequest =
        serde_json::from_value(report["cases"][0]["runtime_request"].clone()).unwrap();
    request.engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    request.interruption.as_mut().unwrap().policy = "ash_effect_once".into();
    request.interruption.as_mut().unwrap().effect_id = "78449284:deck_special".into();
    let path = root
        .join("data/runtime/tournament-2026/state-audits")
        .join(format!(
            "ash-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let journal = CallJournal::open(&path, "actual-state-native-audit", &pack.id(), 512).unwrap();
    let receipt = verify_query_replays(&request, &result, &witnesses, journal.clone()).unwrap();
    assert!(receipt.matches(&request, &result, &witnesses));
    let observed = actual_state(&result, &witnesses, &catalog.data, &pack).unwrap();
    let state = &observed.state;
    assert_eq!(
        compare_resources(state, &first_turn_public_state(&result.checkpoint)).result,
        ygo_knowledge::Truth::Yes
    );
    assert_eq!(state.normal_remaining, Some(1));
    assert_eq!(state.used.get("78449284:deck_special"), Some(&1));
    assert_eq!(
        state
            .cards
            .iter()
            .filter(|c| c.card.player == 0 && c.card.location == 2)
            .count(),
        4
    );
    assert!(state
        .cards
        .iter()
        .any(|c| c.card.code == 83566725 && c.card.location == 16 && c.id == "observed:0:2:2:0"));
    assert!(!state
        .cards
        .iter()
        .any(|c| c.card.code == 46072770 && c.card.location == 4));
    let host = state
        .cards
        .iter()
        .find(|c| c.card.code == 78449284 && c.card.location == 4)
        .unwrap();
    assert_eq!(host.card.overlay, vec![85257384]);
    assert_eq!(host.proper_xyz, Some(true));
    assert!(state
        .cards
        .iter()
        .any(|c| c.host.as_deref() == Some(&host.id)
            && c.card.code == 85257384
            && c.identity_known));
    assert!(!successors(state, &catalog.data, &pack)
        .transitions
        .iter()
        .any(|t| t.rule_id == "78449284:deck_special"));
    assert_eq!(journal.stats().unwrap().consumed, 7);
}

#[test]
fn generic_yes_no_uses_actual_summon_history_and_unique_handler_not_its_label() {
    let (r, w) = capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-reveal.json"
    ));
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let mut trace = actual_trace_v6(&r, &Default::default(), &pack, &w).unwrap();
    let pending = observed_summon_trigger(&r, &trace, &pack).unwrap();
    assert_eq!(pending.rule_id, "46072770:monster_search");
    assert_eq!(pending.source, "observed:0:2:0:0");
    trace.facts.history.clear();
    assert!(observed_summon_trigger(&r, &trace, &pack).is_err());
}
