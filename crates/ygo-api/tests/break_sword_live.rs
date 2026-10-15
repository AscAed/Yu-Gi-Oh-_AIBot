use ygo_api::planning_v2::*;
#[test]
#[ignore = "opt-in: frozen local engine"]
fn break_sword_full_chain_is_planned_and_replayed() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join("target/release/ygo-engine-worker.exe");
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let q: PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/break-sword.request.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let r = plan(
        q,
        engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack,
    )
    .unwrap();
    std::fs::write(
        root.join("data/runtime/break-sword-report.json"),
        serde_json::to_vec_pretty(&r).unwrap(),
    )
    .unwrap();
    for a in &r.attempts {
        println!("{} {:?}", a.status, a.discrepancies);
    }
    assert!(
        !r.analysis.search.lines.is_empty(),
        "{}",
        r.analysis.search.termination
    );
    assert!(r.attempts.iter().filter(|a| a.goal_achieved).any(|a| a
        .predictions
        .iter()
        .any(|p| p.effect_id == "62709239:revive")));
    println!("{}", replay(&r, engine.clone(), &store).unwrap());
    let mut altered = r.clone();
    altered.request.scenario = None;
    assert!(validate_plan_contract(&altered).is_err());
    for field in ["level", "rank"] {
        let mut value = serde_json::to_value(&r).unwrap();
        value["attempts"][0]["predictions"][0]["before_checkpoint"]["cards"][0][field] = 999.into();
        let altered: PlanReport = serde_json::from_value(value).unwrap();
        assert!(replay(&altered, engine.clone(), &store).is_err());
    }
    for field in ["xyz_summoned", "overlay_host"] {
        let mut value = serde_json::to_value(&r).unwrap();
        let step = value["proposals"]["plans"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .flat_map(|p| p["steps"].as_array_mut().unwrap())
            .find(|s| s["kind"] == "xyz_summon")
            .unwrap();
        step["after"]["cards"][0][field] = if field == "xyz_summoned" {
            (!step["after"]["cards"][0][field].as_bool().unwrap()).into()
        } else {
            "forged-host".into()
        };
        let altered: PlanReport = serde_json::from_value(value).unwrap();
        assert!(validate_plan_contract(&altered).is_err());
    }
}

#[test]
#[ignore = "opt-in local catalog debug"]
fn symbolic_break_paths() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let a: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let cat = store.catalog(a["catalog_id"].as_str().unwrap()).unwrap();
    let q: PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/break-sword.request.json"
    ))
    .unwrap();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let p = ygo_planner::v2::propose(
        &q.analysis.deck,
        &q.analysis.opening_hand,
        &cat.data,
        &pack,
        8,
        32,
        Some("ryu-ran"),
    )
    .unwrap();
    assert!(p
        .plans
        .iter()
        .any(|p| p.steps.iter().any(|s| s.effect_id == "62709239:revive")));
}
#[test]
#[ignore = "opt-in: duplicate XYZ material identity"]
fn duplicate_boots_materials_plan_and_replay() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    let mut engine = ygo_engine_adapter::ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("configs/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join("target/release/ygo-engine-worker.exe");
    let store = ygo_storage::SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let mut q: PlanRequest = serde_json::from_str(include_str!(
        "../../../tests/fixtures/break-sword.request.json"
    ))
    .unwrap();
    q.analysis.opening_hand = vec![36426778, 36426778, 88544390, 2964201, 2971090]
        .into_iter()
        .map(ygo_domain::CardId)
        .collect();
    let pack = ygo_knowledge::KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    let r = plan(
        q,
        engine.clone(),
        &store,
        active["catalog_id"].as_str().unwrap(),
        &Default::default(),
        pack.clone(),
    )
    .unwrap();
    std::fs::write(
        root.join("data/runtime/break-duplicate-report.json"),
        serde_json::to_vec_pretty(&r).unwrap(),
    )
    .unwrap();
    assert!(
        r.attempts.iter().any(|a| a.goal_achieved
            && a.predictions
                .iter()
                .any(|p| p.effect_id == "62709239:revive")),
        "{:?}",
        r.attempts
            .iter()
            .map(|a| &a.discrepancies)
            .collect::<Vec<_>>()
    );
    let catalog = store
        .catalog(active["catalog_id"].as_str().unwrap())
        .unwrap();
    let mut checked = false;
    for attempt in r.attempts.iter().filter(|a| {
        a.goal_achieved
            && a.predictions
                .iter()
                .any(|p| p.effect_id == "62709239:revive")
    }) {
        let obs = attempt.observation.as_ref().unwrap();
        let facts = ygo_goal::actual_facts(obs, &catalog.data, &pack);
        let mut pending = vec![];
        for frame in &obs.events {
            if frame.opcode == 62 {
                pending.push(&frame.fields);
            }
            if frame.opcode == 63 {
                if pending.len() == 2 && pending.iter().all(|c| c["code"] == 36426778) {
                    let revivals: Vec<_> = facts
                        .history
                        .iter()
                        .filter(|h| h.kind == "special_summon" && h.event == frame.sequence)
                        .collect();
                    assert_eq!(revivals.len(), 2);
                    assert_ne!(revivals[0].card.instance, revivals[1].card.instance);
                    assert_ne!(revivals[0].card.sequence, revivals[1].card.sequence);
                    checked = true;
                }
                pending.clear();
            }
        }
        assert_eq!(
            facts
                .history
                .iter()
                .find(|h| h.kind == "destroyed" && h.card.code == 62709239)
                .unwrap()
                .card
                .materials,
            vec![36426778]
        );
    }
    assert!(
        checked,
        "real engine must prove both same-name revivals and the remaining material"
    );
    assert_eq!(
        replay(&r, engine, &store).unwrap()["prediction_references_verified"],
        true
    );
}
