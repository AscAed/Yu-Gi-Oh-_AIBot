use ygo_engine_adapter::*;

fn context() -> FirstTurnConfig {
    FirstTurnConfig {
        asset_group_id: format!("asset-group-{}", "a".repeat(64)),
        source_id: format!("tournament-source-{}", "b".repeat(64)),
        coverage_id: format!("coverage-{}", "c".repeat(64)),
        knowledge_id: format!("first-turn-knowledge-{}", "d".repeat(64)),
        ash_effects: vec![AshEffectDescriptor {
            effect_id: "78449284:deck_special".into(),
            card_id: 78449284,
            description: 78449284u64 << 20,
            source_locations: 4,
        }],
    }
}

#[test]
fn dynamic_effects_require_unique_exact_descriptors_and_source_identities() {
    let mut c = context();
    c.validate().unwrap();
    c.ash_effects.push(c.ash_effects[0].clone());
    assert!(c.validate().is_err());
    c = context();
    c.ash_effects[0].card_id = 83566725;
    assert!(c.validate().is_err());
    c = context();
    c.ash_effects[0].source_locations = 0;
    assert!(c.validate().is_err());
    c = context();
    c.asset_group_id = "unfrozen".into();
    assert!(c.validate().is_err());
}

#[test]
fn v6_opponent_resources_are_independent_of_our_deck_and_still_exact() {
    let mut i = InterruptionConfig {
        opponent_deck: ygo_domain::Deck {
            main: (100..113)
                .flat_map(|n| [ygo_domain::CardId(n); 3])
                .chain([ygo_domain::CardId(14558127)])
                .collect(),
            ..Default::default()
        },
        opponent_hand: vec![ygo_domain::CardId(14558127)],
        policy: "ash_effect_once".into(),
        effect_id: "78449284:deck_special".into(),
        occurrence: 1,
    };
    i.validate_v6(&context()).unwrap();
    i.occurrence = 2;
    assert!(i.validate_v6(&context()).is_err());
    i.occurrence = 1;
    i.effect_id = "83566725:deck_set".into();
    assert!(i.validate_v6(&context()).is_err());
    i.effect_id = "78449284:deck_special".into();
    i.opponent_hand.clear();
    assert!(i.validate_v6(&context()).is_err());
}

#[test]
fn old_runtime_serialization_does_not_gain_v6_identity_fields() {
    let mut r: RunDuelRequest = {
        serde_json::from_value(serde_json::json!({
            "protocol_version":2,"engine":{},"deck":{"main":[],"extra":[],"side":[]},
            "opening_hand":[],"seed":1,"decisions":[],"versions":{
                "rules":"", "catalog":"", "banlist":"", "engine_sha256":"",
                "cdb_sha256":"", "scripts_sha256":"", "core_commit":""
            }
        }))
        .unwrap()
    };
    assert!(serde_json::to_value(&r)
        .unwrap()
        .get("first_turn")
        .is_none());
    r.first_turn = Some(context());
    assert!(r.validate_protocol().is_err());
    r.protocol_version = 6;
    assert!(r.validate_protocol().is_err()); // Opponent and initializer still missing.
    r.protocol_version = 7;
    assert!(r.validate_protocol().is_err());
}

#[test]
fn planner_observes_deck_multisets_and_drawn_cards_but_never_deck_order() {
    let mut c = Checkpoint {
        cards: vec![
            StateCard {
                code: 83566725,
                player: 0,
                location: 1,
                sequence: 0,
                ..Default::default()
            },
            StateCard {
                code: 46072770,
                player: 0,
                location: 1,
                sequence: 1,
                ..Default::default()
            },
            StateCard {
                code: 14558127,
                player: 1,
                location: 2,
                sequence: 0,
                ..Default::default()
            },
        ],
        ..Default::default()
    };
    let a = first_turn_public_state(&c);
    c.cards[0].code = 46072770;
    c.cards[1].code = 83566725;
    assert_eq!(a, first_turn_public_state(&c));
    assert!(a.visible.cards.is_empty());
    c.cards[1].location = 2;
    let after_draw = first_turn_public_state(&c);
    assert_ne!(a, after_draw);
    assert_eq!(after_draw.visible.cards[0].code, 83566725);
    assert_eq!(after_draw.own_deck_counts.get(&83566725), None);
}

#[test]
#[ignore = "opt-in independent frozen 2026 assets; manual protocol case, not planner acceptance"]
fn scythe_has_actual_single_ash_cost_negation_anchor_and_independent_replay() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let config_path = std::env::var_os("YGO_TOURNAMENT_ENGINE")
        .map(std::path::PathBuf::from)
        .unwrap_or_else(|| root.join("data/runtime/tournament-2026/engine.toml"));
    let mut config =
        ProcessEngineConfig::from_toml(&std::fs::read_to_string(&config_path).unwrap()).unwrap();
    config.worker_path = env!("CARGO_BIN_EXE_ygo-engine-worker").into();
    let case: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.protocol-case.json"
    ))
    .unwrap();
    let deck = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.deck.json"
    ))
    .unwrap();
    let mut q = runtime_request(
        config.clone(),
        deck,
        serde_json::from_value(case["opening_hand"].clone()).unwrap(),
        1,
    )
    .unwrap();
    q.protocol_version = 6;
    q.versions.initializer = FIRST_TURN_INITIALIZER.into();
    q.versions.banlist =
        "banlist-c98f770b366fed87be0fb23357a63d704db58b31508fbb88133fda66575f3783".into();
    q.first_turn = Some(serde_json::from_value(case["first_turn"].clone()).unwrap());
    q.interruption = Some(InterruptionConfig {
        opponent_deck: serde_json::from_str(include_str!(
            "../../../tests/fixtures/tournament-2026.opponent.json"
        ))
        .unwrap(),
        opponent_hand: vec![ygo_domain::CardId(14558127)],
        policy: "pass".into(),
        effect_id: "78449284:deck_special".into(),
        occurrence: 1,
    });
    q.decisions = serde_json::from_value(case["pass_decisions"].clone()).unwrap();
    let journal_path = config_path.parent().unwrap().join("journals").join(format!(
        "scythe-protocol-{}-{}.jsonl",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let journal = CallJournal::open(
        &journal_path,
        "scythe-protocol-audit",
        &digest(&serde_json::to_vec(&q).unwrap()),
        512,
    )
    .unwrap();
    let adapter = JournaledAdapter::new(
        ProcessEngineAdapter::new(config),
        journal.clone(),
        CallPurpose::Audit,
    );
    let run = |request: &RunDuelRequest| adapter.run(request).unwrap();
    let pass = run(&q);
    assert_eq!(pass.status, DuelStatus::EngineVerified, "{:?}", pass.error);
    assert!(pass
        .checkpoint
        .cards
        .iter()
        .any(|c| c.code == 26692769 && c.player == 0 && c.location == 4));
    assert!(pass
        .checkpoint
        .cards
        .iter()
        .any(|c| c.code == 25542642 && c.player == 0 && c.location == 8 && c.position & 10 != 0));
    let replay = run(&q);
    assert_eq!(pass.events, replay.events);
    assert_eq!(pass.checkpoint, replay.checkpoint);
    assert_eq!(pass.resolved_decisions, replay.resolved_decisions);
    let activation = pass
        .events
        .iter()
        .find(|e| e.opcode == 70 && e.fields["code"] == 78449284u32)
        .unwrap();
    let point = q
        .decisions
        .iter()
        .position(|d| d.player == 1 && d.prompt_id > activation.sequence)
        .unwrap();
    q.decisions.truncate(point);
    q.interruption.as_mut().unwrap().policy = "ash_effect_once".into();
    let ash = run(&q);
    assert_eq!(ash.status, DuelStatus::DecisionRequired, "{:?}", ash.error);
    assert_eq!(ash.prompt.as_ref().unwrap().opcode, 11);
    assert_eq!(ash.checkpoint.phase, 4);
    let ash_activations: Vec<_> = ash
        .events
        .iter()
        .filter(|e| e.opcode == 70 && e.fields["player"] == 1 && e.fields["code"] == 14558127u32)
        .collect();
    assert_eq!(ash_activations.len(), 1);
    assert_eq!(ash_activations[0].fields["trigger_location"], 2);
    assert!(ash.events.iter().any(|e| e.opcode == 50
        && e.fields["code"] == 14558127u32
        && e.fields["from"]["player"] == 1
        && e.fields["from"]["location"] == 2
        && e.fields["to"]["location"] == 16
        && e.fields["reason"].as_u64().unwrap() & 128 != 0));
    assert!(ash
        .events
        .iter()
        .any(|e| e.opcode == 76 && e.fields["chain"] == 1));
    assert!(!ash.events.iter().any(|e| e.opcode == 50
        && e.fields["code"] == 46072770u32
        && e.fields["from"]["location"] == 1
        && e.fields["to"]["location"] == 4));
    let scythe = ash
        .checkpoint
        .cards
        .iter()
        .find(|c| c.code == 78449284 && c.player == 0 && c.location == 4)
        .unwrap();
    assert_eq!(scythe.overlay, vec![85257384]);
    assert_eq!(scythe.rank, Some(3));
    assert_eq!(scythe.attribute, Some(32));
    assert_eq!(scythe.owner, Some(0));
    assert_eq!(scythe.status.unwrap() & 8, 8); // Native STATUS_PROC_COMPLETE.
    assert!(ash
        .checkpoint
        .cards
        .iter()
        .any(|c| c.code == 83566725 && c.player == 0 && c.location == 16));
    let prompt = ash.prompt.as_ref().unwrap();
    let frame = ash.events.iter().find(|e| e.sequence == prompt.id).unwrap();
    assert!(!prompt_metadata(prompt.id, &frame.raw)
        .unwrap()
        .iter()
        .any(|m| m.source.as_ref().is_some_and(|c| c.code == 78449284)
            && m.effect_description == Some(78449284u64 << 20)));
    q.decisions = ash.resolved_decisions.clone();
    let replay = run(&q);
    assert_eq!(ash.events, replay.events);
    assert_eq!(ash.checkpoint, replay.checkpoint);
    assert_eq!(ash.resolved_decisions, replay.resolved_decisions);
    q.first_turn.as_mut().unwrap().asset_group_id = format!("asset-group-{}", "0".repeat(64));
    assert_eq!(run(&q).error.unwrap().code, "asset_group");
    assert_eq!(journal.stats().unwrap().consumed, 5);
    assert_eq!(journal.stats().unwrap().completed, 5);
    journal.verify().unwrap();
}
