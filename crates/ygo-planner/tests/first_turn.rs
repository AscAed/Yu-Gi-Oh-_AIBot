use ygo_domain::{Card, CardId, Catalog};
use ygo_engine_adapter::{first_turn_public_state, Checkpoint, StateCard};
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;

fn catalog() -> Catalog {
    [
        (83566725, 0x21, 3, vec![0x10db]),
        (46072770, 0x21, 3, vec![0x10db]),
        (36426778, 0x21, 3, vec![0x10db]),
        (25538345, 0x21, 3, vec![0x10db]),
        (85257384, 4, 3, vec![0x10db]),
        (25542642, 4, 0, vec![0xdb]),
        (78449284, 0x800021, 3, vec![0x10db]),
    ]
    .into_iter()
    .map(|(code, type_flags, level, setcodes)| {
        (
            CardId(code),
            Card {
                id: CardId(code),
                name: format!("card{code}"),
                type_flags,
                level,
                setcodes,
                attribute: if type_flags & 1 != 0 || code == 85257384 {
                    32
                } else {
                    0
                },
                race: if type_flags & 1 != 0 || code == 85257384 {
                    1
                } else {
                    0
                },
                defense: if code == 85257384 { 300 } else { 0 },
                ..Default::default()
            },
        )
    })
    .collect()
}
fn state() -> CausalState {
    let cat = catalog();
    let mut checkpoint = Checkpoint {
        turn: 1,
        turn_player: 0,
        phase: 4,
        ..Default::default()
    };
    for (code, zone, seq) in [
        (83566725, 2, 0),
        (83566725, 2, 1),
        (78449284, 64, 0),
        (85257384, 1, 0),
        (25542642, 1, 1),
        (46072770, 1, 2),
        (36426778, 1, 3),
    ] {
        let c = cat.get(&CardId(code)).unwrap();
        checkpoint.cards.push(StateCard {
            code,
            player: 0,
            location: zone,
            sequence: seq,
            position: if zone == 2 { 10 } else { 8 },
            type_flags: c.type_flags,
            level: if c.type_flags & 0x800000 == 0 {
                Some(c.level)
            } else {
                None
            },
            rank: if c.type_flags & 0x800000 != 0 {
                Some(c.level)
            } else {
                None
            },
            attribute: Some(32),
            race: Some(1),
            ..Default::default()
        });
    }
    CausalState::initial(&first_turn_public_state(&checkpoint)).unwrap()
}
fn choose(state: &CausalState, id: &str) -> Transition {
    successors(state, &catalog(), &FirstTurnKnowledge::builtin().unwrap())
        .transitions
        .into_iter()
        .find(|s| s.rule_id == id && s.kind != TransitionKind::DeclineTrigger)
        .unwrap()
}

#[test]
fn soleret_procedure_preserves_normal_opportunity_and_uses_a_name_scoped_limit() {
    let original = state();
    let step = choose(&original, "83566725:empty_field_special");
    assert_eq!(step.after_resolution.normal_remaining, Some(1));
    assert_eq!(
        step.after_resolution
            .cards
            .iter()
            .filter(|c| c.card.code == 83566725 && c.card.location == 4)
            .count(),
        1
    );
    assert_eq!(
        step.after_resolution
            .cards
            .iter()
            .filter(|c| c.card.code == 83566725 && c.card.location == 2)
            .count(),
        1
    );
    let mut again = step.after_resolution;
    again.pending.clear();
    for card in &mut again.cards {
        if card.card.location == 4 {
            card.card.location = 16;
        }
    }
    assert!(
        !successors(&again, &catalog(), &FirstTurnKnowledge::builtin().unwrap())
            .transitions
            .iter()
            .any(|s| s.rule_id == "83566725:empty_field_special")
    );
}

#[test]
fn deck_set_filter_does_not_treat_fog_as_the_phantom_knights_and_requires_a_trigger() {
    let initial = state();
    assert!(!successors(
        &initial,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap()
    )
    .transitions
    .iter()
    .any(|s| s.rule_id == "83566725:deck_set"));
    let summoned = choose(&initial, "83566725:empty_field_special").after_resolution;
    let options = successors(
        &summoned,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap(),
    );
    let sets: Vec<_> = options
        .transitions
        .iter()
        .filter(|s| s.rule_id == "83566725:deck_set" && s.kind == TransitionKind::Trigger)
        .collect();
    assert_eq!(sets.len(), 1);
    assert_eq!(sets[0].selections[0].card_id, 85257384);
    assert_eq!(
        sets[0]
            .after_resolution
            .deck_counts
            .get(&85257384)
            .copied()
            .unwrap_or(0),
        0
    );
    assert_eq!(
        sets[0].after_resolution.deck_counts.get(&25542642),
        Some(&1)
    );
}

#[test]
fn xyz_materials_and_detach_cost_are_distinct_from_effect_special_summon() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let xyz = choose(&s, "78449284:two_dark_level_three");
    assert_eq!(
        xyz.after_resolution
            .cards
            .iter()
            .filter(|c| c.card.location == 16)
            .count(),
        0
    );
    let summon = successors(
        &xyz.after_resolution,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap(),
    )
    .transitions
    .into_iter()
    .find(|s| {
        s.rule_id == "78449284:deck_special"
            && s.selections
                .iter()
                .any(|v| v.stage == "resolution" && v.card_id == 46072770)
    })
    .unwrap();
    assert_eq!(
        summon
            .selections
            .iter()
            .filter(|s| s.stage == "cost")
            .count(),
        1
    );
    assert_eq!(
        summon
            .after_cost
            .cards
            .iter()
            .filter(|c| c.card.code == 46072770 && c.card.location == 4)
            .count(),
        0
    );
    assert_eq!(
        summon
            .after_resolution
            .cards
            .iter()
            .filter(|c| c.card.code == 46072770 && c.card.location == 4)
            .count(),
        1
    );
    let cost = summon
        .selections
        .iter()
        .find(|s| s.stage == "cost")
        .unwrap();
    assert_eq!(
        summon
            .after_cost
            .cards
            .iter()
            .find(|c| c.id == cost.instance.clone().unwrap())
            .unwrap()
            .card
            .location,
        16
    );
    let host = summon
        .after_cost
        .cards
        .iter()
        .find(|c| c.card.code == 78449284)
        .unwrap();
    assert_eq!(host.card.overlay.len(), 1);
    let search = choose(&summon.after_resolution, "46072770:monster_search");
    assert!(search
        .after_resolution
        .cards
        .iter()
        .any(|c| c.card.location == 2 && c.card.code == 36426778));
}

#[test]
fn unknown_level_or_attribute_does_not_satisfy_xyz_material_requirements() {
    let mut s = choose(&state(), "83566725:empty_field_special").after_resolution;
    s.pending.clear();
    let mut other = s
        .cards
        .iter()
        .find(|c| c.card.location == 2)
        .unwrap()
        .clone();
    other.id = "unknown-level".into();
    other.card.location = 4;
    other.card.sequence = 1;
    other.card.position = 1;
    other.card.level = None;
    s.cards.retain(|c| c.id != other.id);
    s.cards.push(other);
    let result = successors(&s, &catalog(), &FirstTurnKnowledge::builtin().unwrap());
    assert!(!result
        .transitions
        .iter()
        .any(|s| s.rule_id == "78449284:two_dark_level_three"));
    assert!(!result.unknowns.is_empty());
}

#[test]
fn same_name_materials_keep_separate_instances_and_unknown_locks_do_not_pass() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let mut s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let first = s
        .cards
        .iter()
        .find(|c| c.card.location == 4 && c.card.code == 83566725)
        .unwrap()
        .clone();
    let other = s
        .cards
        .iter_mut()
        .find(|c| c.card.location == 4 && c.card.code == 85257384)
        .unwrap();
    let id = other.id.clone();
    let slot = other.card.sequence;
    *other = first.clone();
    other.id = id;
    other.card.sequence = slot;
    let xyz = choose(&s, "78449284:two_dark_level_three");
    let host = xyz
        .after_resolution
        .cards
        .iter()
        .find(|c| c.card.code == 78449284)
        .unwrap();
    assert_eq!(host.card.overlay, vec![83566725, 83566725]);
    let detach = choose(&xyz.after_resolution, "78449284:deck_special");
    assert_eq!(
        detach
            .after_cost
            .cards
            .iter()
            .filter(|c| c.card.location == 16 && c.card.code == 83566725)
            .count(),
        1
    );
    assert_eq!(
        detach
            .after_cost
            .cards
            .iter()
            .filter(|c| c.card.location == 132 && c.card.code == 83566725)
            .count(),
        1
    );
    s.special_allowed = None;
    let unknown = successors(&s, &catalog(), &FirstTurnKnowledge::builtin().unwrap());
    assert!(!unknown
        .transitions
        .iter()
        .any(|s| s.rule_id == "78449284:two_dark_level_three"));
    assert!(unknown
        .unknowns
        .iter()
        .any(|r| r.contains("summon restriction")));
}

#[test]
fn projection_comparison_keeps_levels_and_materials_bound_to_the_same_host() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let s = choose(&s, "78449284:two_dark_level_three").after_resolution;
    let mut actual = Checkpoint {
        turn: 1,
        turn_player: 0,
        phase: 4,
        ..Default::default()
    };
    actual.cards = s
        .cards
        .iter()
        .filter(|c| c.card.location != 132)
        .map(|c| c.card.clone())
        .collect();
    for (code, count) in &s.deck_counts {
        for seq in 0..*count {
            actual.cards.push(StateCard {
                code: *code,
                player: 0,
                location: 1,
                sequence: seq as u32,
                ..Default::default()
            });
        }
    }
    assert_eq!(
        compare_resources(&s, &first_turn_public_state(&actual)).result,
        ygo_knowledge::Truth::Yes
    );
    actual
        .cards
        .iter_mut()
        .find(|c| c.code == 78449284)
        .unwrap()
        .overlay
        .pop();
    assert_eq!(
        compare_resources(&s, &first_turn_public_state(&actual)).result,
        ygo_knowledge::Truth::No
    );
}

#[test]
fn optional_triggers_can_be_declined_and_exhausted_targets_do_not_open_a_window() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let options = successors(&s, &catalog(), &FirstTurnKnowledge::builtin().unwrap());
    let decline = options
        .transitions
        .iter()
        .find(|s| s.rule_id == "83566725:deck_set" && s.kind == TransitionKind::DeclineTrigger)
        .unwrap();
    assert!(decline.after_resolution.pending.is_empty());
    assert_eq!(decline.after_resolution.used.get("83566725:deck_set"), None);
    let mut depleted = state();
    depleted.deck_counts.insert(85257384, 0);
    let summoned = choose(&depleted, "83566725:empty_field_special");
    assert!(summoned.after_resolution.pending.is_empty());
}

#[test]
fn untouched_initializer_rejects_a_visible_opponent_or_already_used_resources() {
    let mut public = ygo_engine_adapter::FirstTurnPublicState {
        visible: Checkpoint {
            turn: 1,
            turn_player: 0,
            phase: 4,
            ..Default::default()
        },
        own_deck_counts: Default::default(),
        opponent_deck_count: 39,
        opponent_hand_count: 1,
    };
    public.visible.cards.push(StateCard {
        code: 14558127,
        player: 1,
        location: 16,
        position: 5,
        ..Default::default()
    });
    assert!(CausalState::initial(&public).is_err());
}

#[test]
fn trap_monster_printed_attributes_are_restored_when_it_becomes_material_or_is_detached() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let xyz = choose(&s, "78449284:two_dark_level_three").after_resolution;
    let material = xyz.cards.iter().find(|c| c.card.code == 85257384).unwrap();
    assert_eq!(material.card.location, 132);
    assert_eq!(material.card.type_flags, 4);
    let detach = successors(&xyz, &catalog(), &FirstTurnKnowledge::builtin().unwrap())
        .transitions
        .into_iter()
        .find(|s| {
            s.rule_id == "78449284:deck_special"
                && s.selections
                    .iter()
                    .any(|s| s.stage == "cost" && s.card_id == 85257384)
        })
        .unwrap();
    let grave = detach
        .after_cost
        .cards
        .iter()
        .find(|c| c.card.code == 85257384)
        .unwrap();
    assert_eq!(grave.card.location, 16);
    assert_eq!(grave.card.type_flags, 4);
    assert_eq!(grave.card.level, Some(0));
    assert_eq!(grave.card.attribute, Some(0));
}

#[test]
fn known_resource_mismatch_is_false_even_when_an_unrelated_attribute_is_unknown() {
    let predicted = state();
    let mut actual = Checkpoint {
        turn: 1,
        turn_player: 0,
        phase: 4,
        ..Default::default()
    };
    actual.cards = predicted.cards.iter().map(|c| c.card.clone()).collect();
    actual.cards[0].level = None;
    // Remaining deck counts are certainly wrong, independently of the missing level.
    assert_eq!(
        compare_resources(&predicted, &first_turn_public_state(&actual)).result,
        ygo_knowledge::Truth::No
    );
}

#[test]
fn inconsistent_material_instances_are_rejected_before_planning() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let mut s = choose(&s, "78449284:two_dark_level_three").after_resolution;
    s.cards
        .iter_mut()
        .find(|c| c.card.location == 132)
        .unwrap()
        .host = None;
    assert!(s.validate(&catalog()).is_err());
    let result = successors(&s, &catalog(), &FirstTurnKnowledge::builtin().unwrap());
    assert!(result.transitions.is_empty());
    assert!(!result.unknowns.is_empty());
}

#[test]
fn normal_xyz_using_an_xyz_as_material_sends_its_old_materials_to_grave() {
    let s = choose(&state(), "83566725:empty_field_special").after_resolution;
    let s = choose(&s, "83566725:deck_set").after_resolution;
    let s = choose(&s, "85257384:trap_monster_special").after_resolution;
    let mut s = choose(&s, "78449284:two_dark_level_three").after_resolution;
    let old = s
        .cards
        .iter_mut()
        .find(|c| c.card.code == 78449284)
        .unwrap();
    old.rank_as_level = Some(true);
    let mut second = old.clone();
    second.id = "second-extra-scythe".into();
    second.card.location = 64;
    second.card.sequence = 1;
    second.card.overlay.clear();
    second.proper_xyz = Some(false);
    second.rank_as_level = Some(false);
    s.cards.push(second);
    let other = s.cards.iter_mut().find(|c| c.card.location == 2).unwrap();
    other.card.location = 4;
    other.card.sequence = 1;
    other.card.position = 1;
    s.normal_remaining = Some(0);
    let transition = successors(&s, &catalog(), &FirstTurnKnowledge::builtin().unwrap())
        .transitions
        .into_iter()
        .find(|s| s.rule_id == "78449284:two_dark_level_three" && s.source == "second-extra-scythe")
        .unwrap();
    transition.after_resolution.validate(&catalog()).unwrap();
    assert_eq!(
        transition
            .after_resolution
            .cards
            .iter()
            .filter(|c| c.card.location == 16)
            .count(),
        2
    );
    let host = transition
        .after_resolution
        .cards
        .iter()
        .find(|c| c.id == "second-extra-scythe")
        .unwrap();
    assert_eq!(host.card.overlay.len(), 2);
    let nested = transition
        .after_resolution
        .cards
        .iter()
        .find(|c| c.card.code == 78449284 && c.id != "second-extra-scythe")
        .unwrap();
    assert_eq!(nested.card.location, 132);
    assert!(nested.card.overlay.is_empty());
}

#[test]
#[ignore = "opt-in: six causal forecasts against independently authored native preparation; not autonomous planning"]
fn resource_predictions_are_recorded_before_native_execution_and_independently_replayed() {
    use ygo_engine_adapter::*;
    use ygo_knowledge::first_turn::verification::NativeCases;
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let suite: NativeCases = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.json"
    ))
    .unwrap();
    suite.validate(&pack).unwrap();
    let store =
        ygo_storage::SnapshotStore::new(root.join("data/runtime/tournament-2026/snapshots"));
    let pointer: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let catalog = store
        .catalog(pointer["catalog_id"].as_str().unwrap())
        .unwrap();
    let banlist = store
        .banlist(pointer["banlist_id"].as_str().unwrap())
        .unwrap();
    let mut engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine.toml")).unwrap(),
    )
    .unwrap();
    engine.worker_path = root.join(format!(
        "target/debug/ygo-engine-worker{}",
        std::env::consts::EXE_SUFFIX
    ));
    pack.validate_sources(engine.catalog_path.parent().unwrap())
        .unwrap();
    let first = &suite.cases[0];
    assert!(
        ygo_domain::validate_catalog_deck(&first.deck, &banlist.data, &catalog.data).is_legal()
    );
    let mut q = runtime_request(
        engine.clone(),
        first.deck.clone(),
        first.opening_hand.clone(),
        1,
    )
    .unwrap();
    q.protocol_version = 6;
    q.versions.initializer = FIRST_TURN_INITIALIZER.into();
    q.versions.catalog = catalog.id;
    q.versions.banlist = banlist.id;
    let descriptors: Vec<_> = pack
        .potential_ash_effects()
        .iter()
        .map(|r| AshEffectDescriptor {
            effect_id: r.id.clone(),
            card_id: r.card_id,
            description: r.description.unwrap(),
            source_locations: r.source_locations,
        })
        .collect();
    q.interruption = Some(InterruptionConfig {
        opponent_deck: serde_json::from_str(include_str!(
            "../../../tests/fixtures/tournament-2026.opponent.json"
        ))
        .unwrap(),
        opponent_hand: vec![CardId(14558127)],
        policy: "pass".into(),
        effect_id: descriptors[0].effect_id.clone(),
        occurrence: 1,
    });
    q.first_turn = Some(FirstTurnConfig {
        asset_group_id: pack.asset_group_id.clone(),
        source_id: pack.source_id.clone(),
        coverage_id: pack.coverage_id.clone(),
        knowledge_id: pack.id(),
        ash_effects: descriptors,
    });
    let path = root
        .join("data/runtime/tournament-2026/model-audits")
        .join(format!(
            "resources-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let context = digest(&serde_json::to_vec(&(&suite, &q.versions)).unwrap());
    let journal = CallJournal::open(&path, "manual-resource-forecast", &context, 512).unwrap();
    let execute = JournaledAdapter::new(
        ProcessEngineAdapter::new(engine.clone()),
        journal.clone(),
        CallPurpose::RuleVerification,
    );
    let replay = JournaledAdapter::new(
        ProcessEngineAdapter::new(engine),
        journal.clone(),
        CallPurpose::Replay,
    );
    let native = execute.run(&q).unwrap();
    let check = replay.run(&q).unwrap();
    assert_eq!(native.events, check.events);
    assert_eq!(native.checkpoint, check.checkpoint);
    let mut state = CausalState::initial(&first_turn_public_state(&native.checkpoint)).unwrap();
    for (index, id) in [
        "soleret-empty-positive",
        "soleret-set-positive",
        "veil-trap-monster-positive",
        "scythe-xyz-positive",
        "scythe-deck-special-positive",
        "decayed-search-positive",
    ]
    .iter()
    .enumerate()
    {
        let case = suite.cases.iter().find(|c| c.id == *id).unwrap();
        let transition = successors(&state, &catalog.data, &pack)
            .transitions
            .into_iter()
            .find(|s| {
                s.rule_id == case.rule_id
                    && (*id != "soleret-set-positive"
                        || s.selections
                            .iter()
                            .any(|v| v.stage == "resolution" && v.card_id == 85257384))
                    && (*id != "scythe-deck-special-positive"
                        || s.selections
                            .iter()
                            .any(|v| v.stage == "resolution" && v.card_id == 46072770)
                            && s.selections
                                .iter()
                                .any(|v| v.stage == "cost" && v.card_id == 83566725))
                    && (*id != "decayed-search-positive"
                        || s.selections
                            .iter()
                            .any(|v| v.stage == "resolution" && v.card_id == 36426778))
            })
            .unwrap();
        // The frozen human recipe is separate from the model; the forecast is persisted first.
        journal
            .save_checkpoint(
                &format!("forecast-{index}"),
                &serde_json::to_value(&transition).unwrap(),
            )
            .unwrap();
        if *id == "scythe-deck-special-positive" {
            let alternate = successors(&state, &catalog.data, &pack)
                .transitions
                .into_iter()
                .find(|s| {
                    s.rule_id == case.rule_id
                        && s.selections
                            .iter()
                            .any(|v| v.stage == "cost" && v.card_id == 85257384)
                        && s.selections
                            .iter()
                            .any(|v| v.stage == "resolution" && v.card_id == 46072770)
                })
                .unwrap();
            journal
                .save_checkpoint(
                    "forecast-veil-detach-cost",
                    &serde_json::to_value(&alternate).unwrap(),
                )
                .unwrap();
            let mut alternate_cost = q.clone();
            alternate_cost.decisions = case.decisions[..27].to_vec();
            alternate_cost.decisions.last_mut().unwrap().choice =
                Choice::Cards { indices: vec![0] };
            let actual_cost = execute.run(&alternate_cost).unwrap();
            let cost_replay = replay.run(&alternate_cost).unwrap();
            assert_eq!(actual_cost.events, cost_replay.events);
            assert_eq!(actual_cost.checkpoint, cost_replay.checkpoint);
            let compared = compare_resources(
                &alternate.after_cost,
                &first_turn_public_state(&actual_cost.checkpoint),
            );
            assert_eq!(
                compared.result,
                ygo_knowledge::Truth::Yes,
                "Veil detach: {:?}",
                compared.differences
            );
            let veil = actual_cost
                .checkpoint
                .cards
                .iter()
                .find(|c| c.player == 0 && c.location == 16 && c.code == 85257384)
                .unwrap();
            assert_eq!(veil.type_flags, 4);
            assert_eq!(veil.level, Some(0));
            assert_eq!(veil.attribute, Some(0));
            let mut cost = q.clone();
            cost.decisions = case.decisions[..27].to_vec();
            let paid = execute.run(&cost).unwrap();
            let paid_replay = replay.run(&cost).unwrap();
            assert_eq!(paid.events, paid_replay.events);
            assert_eq!(paid.checkpoint, paid_replay.checkpoint);
            let compared = compare_resources(
                &transition.after_cost,
                &first_turn_public_state(&paid.checkpoint),
            );
            assert_eq!(
                compared.result,
                ygo_knowledge::Truth::Yes,
                "{:?}",
                compared.differences
            );
            assert!(paid.events.iter().any(|e| e.opcode == 50
                && e.fields["code"] == 83566725
                && e.fields["from"]["location"] == 132
                && e.fields["to"]["location"] == 16
                && e.fields["reason"] == 128));
            assert!(!paid
                .checkpoint
                .cards
                .iter()
                .any(|c| c.code == 46072770 && c.player == 0 && c.location == 4));
        }
        q.decisions = case.decisions.clone();
        let actual = execute.run(&q).unwrap();
        let independent = replay.run(&q).unwrap();
        assert_eq!(actual.events, independent.events);
        assert_eq!(actual.checkpoint, independent.checkpoint);
        assert_eq!(actual.resolved_decisions, independent.resolved_decisions);
        let compared = compare_resources(
            &transition.after_resolution,
            &first_turn_public_state(&actual.checkpoint),
        );
        assert_eq!(
            compared.result,
            ygo_knowledge::Truth::Yes,
            "{id}: {:?}",
            compared.differences
        );
        state = transition.after_resolution;
    }
    assert_eq!(journal.stats().unwrap().consumed, 18);
    journal.verify().unwrap();
}
