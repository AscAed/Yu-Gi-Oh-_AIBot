use ygo_engine_adapter::*;
use ygo_goal::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;

fn captured() -> (DuelResult, Vec<QueryWitness>) {
    read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-resource.json"
    ))
}
fn read_capture(text: &str) -> (DuelResult, Vec<QueryWitness>) {
    let mut value: serde_json::Value = serde_json::from_str(text).unwrap();
    value["result"]["events"] = serde_json::json!([]);
    let mut result: DuelResult = serde_json::from_value(value["result"].clone()).unwrap();
    result.events = value["frames"]
        .as_array()
        .unwrap()
        .iter()
        .enumerate()
        .map(|(i, raw)| {
            decode_frame(
                i as u64 + 1,
                &serde_json::from_value::<Vec<u8>>(raw.clone()).unwrap(),
            )
            .unwrap()
        })
        .collect();
    let witnesses = serde_json::from_value(value["witnesses"].clone()).unwrap();
    (result, witnesses)
}
fn catalog() -> ygo_domain::Catalog {
    serde_json::from_value(serde_json::json!({
        "83566725":{"id":83566725,"name":"Soleret","kind":"monster","archetypes":[],"type_flags":33,"level":3,"attribute":32,"race":1},
        "85257384":{"id":85257384,"name":"Veil","kind":"trap","archetypes":[],"type_flags":4,"level":3,"attribute":32,"race":1},
        "78449284":{"id":78449284,"name":"Scythe","kind":"monster","archetypes":[],"type_flags":8388641,"level":3,"attribute":32,"race":1},
        "46072770":{"id":46072770,"name":"Decayed","kind":"monster","archetypes":[],"type_flags":33,"level":3,"attribute":32,"race":1}
    })).unwrap()
}

#[test]
fn new_registry_reconstructs_xyz_cost_and_effect_sources_from_raw_evidence() {
    let (result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let xyz = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 78449284 && c.player == 0 && c.location == 4)
        .unwrap();
    assert!(xyz.identity_known);
    assert_eq!(xyz.proper_xyz, Some(true));
    assert_eq!(xyz.rank, Some(3));
    assert_eq!(xyz.materials, vec![85257384]);
    let summon = trace
        .facts
        .history
        .iter()
        .find(|h| h.kind == "xyz_summon" && h.card.instance == xyz.instance)
        .unwrap();
    assert_eq!(summon.card.materials.len(), 2);
    let effect = trace
        .facts
        .history
        .iter()
        .find(|h| {
            h.kind == "effect_resolved" && h.effect_id.as_deref() == Some("78449284:deck_special")
        })
        .unwrap();
    assert_eq!(effect.card.materials, vec![85257384]);
    assert!(trace
        .facts
        .cards
        .iter()
        .all(|c| c.location != 1 && !(c.player == 1 && matches!(c.location, 2 | 64))));
    assert_eq!(trace.material_instances.len(), 1);
    assert_eq!(trace.material_instances[0].code, 85257384);
    assert!(trace
        .activations
        .iter()
        .any(|a| a.rule_id.as_deref() == Some("83566725:deck_set") && a.resolved && !a.negated));
}

#[test]
fn fake_query_prefix_or_decoded_event_is_rejected() {
    let (mut result, mut witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    witnesses[0].raw_prefix_sha256 = "0".repeat(64);
    assert!(actual_trace_v6(&result, &catalog(), &pack, &witnesses).is_err());
    let (_, witnesses) = captured();
    result.events[0].fields = serde_json::json!({"forged":true});
    assert!(actual_trace_v6(&result, &catalog(), &pack, &witnesses).is_err());
}

#[test]
fn actual_negation_keeps_cost_and_usage_but_never_records_the_negated_gain() {
    let (result, witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert_eq!(trace.window, TraceWindow::OwnMainAction);
    assert_eq!(trace.normal_remaining, Some(1));
    assert_eq!(trace.used.get("78449284:deck_special"), Some(&1));
    assert!(!trace
        .facts
        .history
        .iter()
        .any(|h| h.kind == "effect_resolved"
            && h.effect_id.as_deref() == Some("78449284:deck_special")));
    assert!(trace
        .facts
        .history
        .iter()
        .any(|h| h.kind == "effect_negated"
            && h.effect_id.as_deref() == Some("78449284:deck_special")
            && h.card.materials == vec![85257384]));
    assert!(trace
        .facts
        .cards
        .iter()
        .any(|c| c.code == 83566725 && c.location == 16));
    assert!(!trace
        .facts
        .cards
        .iter()
        .any(|c| c.code == 46072770 && c.location == 4));
    assert!(trace
        .facts
        .cards
        .iter()
        .any(|c| c.code == 14558127 && c.player == 1 && c.location == 16));
}

#[test]
fn a_summon_inside_an_unfinished_chain_is_not_a_recovery_window() {
    let (mut result, mut witnesses) = captured();
    result.events.truncate(82);
    result.prompt = None;
    result.status = DuelStatus::Partial;
    result.resolved_decisions.retain(|d| d.prompt_id <= 82);
    witnesses.retain(|w| w.event <= 82);
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert_eq!(trace.window, TraceWindow::Pending);
    assert!(!trace.facts.history_complete);
}

#[test]
fn a_chain_solved_frame_without_its_solving_event_does_not_prove_resolution() {
    use sha2::{Digest, Sha256};
    let (mut result, mut witnesses) = captured();
    let missing = result
        .events
        .iter()
        .find(|e| e.opcode == 72)
        .unwrap()
        .sequence;
    result.events[missing as usize - 1] = decode_frame(missing, &[1]).unwrap();
    for w in &mut witnesses {
        let raw: Vec<_> = result.events[..w.event as usize]
            .iter()
            .map(|e| &e.raw)
            .collect();
        w.raw_prefix_sha256 = format!("{:x}", Sha256::digest(serde_json::to_vec(&raw).unwrap()));
    }
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert!(
        !trace
            .activations
            .iter()
            .find(|a| a.rule_id.as_deref() == Some("83566725:deck_set"))
            .unwrap()
            .resolved
    );
    assert!(!trace.facts.history_complete);
}

#[test]
fn missing_material_evidence_is_unknown_while_legacy_serialization_stays_unchanged() {
    let legacy = FactCard::default();
    assert!(serde_json::to_value(&legacy)
        .unwrap()
        .get("materials_complete")
        .is_none());
    let card = FactCard {
        code: 78449284,
        player: 0,
        location: 4,
        materials_complete: Some(false),
        ..Default::default()
    };
    let condition = Filter {
        codes: vec![78449284],
        locations: vec![4],
        materials_min: Some(1),
        ..Default::default()
    };
    assert_eq!(condition.matches(&card), Truth::Unknown);
    assert_eq!(condition.matches(&card).negate(), Truth::Unknown);
}

#[test]
fn a_known_self_summoning_handler_recovers_identity_after_same_name_hand_shuffle() {
    let (result, witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-reveal.json"
    ));
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let actor = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 46072770 && c.location == 4)
        .unwrap();
    assert!(actor.identity_known);
    assert_eq!(actor.instance, "observed:0:2:0:0");
    let other = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 46072770 && c.location == 2)
        .unwrap();
    assert!(other.identity_known);
    assert_eq!(other.instance, "observed:0:2:2:0");
    assert!(trace
        .facts
        .history
        .iter()
        .any(|h| h.kind == "special_summon" && h.card.instance == actor.instance));
    assert_eq!(trace.identity_bindings.len(), 2);
    assert_eq!(
        trace.identity_bindings[0].basis,
        "known_handler_self_special_during_resolution"
    );
    assert_eq!(
        trace.identity_bindings[1].basis,
        "unique_unassigned_query_after_shuffle"
    );
}

#[test]
fn contradicting_a_known_activation_source_is_rejected_even_with_rehashed_frames() {
    use sha2::{Digest, Sha256};
    let (mut result, mut witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-reveal.json"
    ));
    let index = result.events.iter().position(|e| e.opcode == 70).unwrap();
    let event = &result.events[index];
    let mut raw = event.raw.clone();
    raw[7..11].copy_from_slice(&2u32.to_le_bytes());
    raw[17..21].copy_from_slice(&2u32.to_le_bytes());
    result.events[index] = decode_frame(event.sequence, &raw).unwrap();
    for w in &mut witnesses {
        let raw: Vec<_> = result.events[..w.event as usize]
            .iter()
            .map(|e| &e.raw)
            .collect();
        w.raw_prefix_sha256 = format!("{:x}", Sha256::digest(serde_json::to_vec(&raw).unwrap()));
    }
    assert!(actual_trace_v6(
        &result,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap(),
        &witnesses
    )
    .is_err());
}

#[test]
fn activation_source_and_paid_material_snapshot_are_separate() {
    let (result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let activation = trace
        .activations
        .iter()
        .find(|a| a.rule_id.as_deref() == Some("78449284:deck_special"))
        .unwrap();
    assert_eq!(activation.event, 67);
    assert_eq!(activation.source.materials, vec![85257384, 83566725]);
    assert_eq!(
        activation.after_cost.as_ref().unwrap().materials,
        vec![85257384]
    );
    let detach = trace.movements.iter().find(|m| m.event == 70).unwrap();
    assert_eq!(detach.reason, 128);
    assert_eq!(detach.from.location, 132);
    assert_eq!(detach.to.location, 16);
    assert!(trace
        .facts
        .history
        .iter()
        .any(|h| h.event == 70 && h.kind == "sent_to_grave" && h.reason == 128));
    assert!(!trace
        .facts
        .history
        .iter()
        .any(|h| h.event == 70 && h.kind == "effect_resolved"));
}

#[test]
fn material_identity_survives_the_extra_deck_host_moving_to_field() {
    let (result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let original = "observed:0:2:2:0";
    let grave = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 83566725 && c.location == 16)
        .unwrap();
    assert_eq!(grave.instance, original);
    assert!(grave.identity_known);
    let first = trace.movements.iter().find(|m| m.event == 55).unwrap();
    let detach = trace.movements.iter().find(|m| m.event == 70).unwrap();
    assert_eq!(first.instance, detach.instance);
    assert_eq!(first.epoch_after, 1);
    assert_eq!(detach.epoch_before, 1);
    assert_eq!(detach.epoch_after, 1);
    assert_eq!(trace.material_instances[0].instance, "observed:27");
    assert!(trace
        .movements
        .iter()
        .filter(|m| m.from.location == 1)
        .all(|m| m.from.sequence.is_none() && m.from.position.is_none()));
}

#[test]
fn witness_order_hidden_cards_and_actual_decisions_are_checked() {
    let (mut result, mut witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    witnesses.swap(1, 2);
    assert!(actual_trace_v6(&result, &catalog(), &pack, &witnesses).is_err());
    let (_, mut witnesses) = captured();
    witnesses[0].public.visible.cards[0].location = 1;
    assert!(actual_trace_v6(&result, &catalog(), &pack, &witnesses).is_err());
    let (_, witnesses) = captured();
    result.resolved_decisions[0].player = 1;
    assert!(actual_trace_v6(&result, &catalog(), &pack, &witnesses).is_err());
}

#[test]
fn historical_missing_dynamic_attributes_are_not_filled_from_final_query() {
    let (result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let summon = trace
        .facts
        .history
        .iter()
        .find(|h| h.kind == "special_summon" && h.card.code == 85257384)
        .unwrap();
    // Native special-summon frames do not contain the trap monster's level.
    // The later observed level is current evidence, not a past snapshot.
    assert_eq!(summon.card.level, None);
    let material = &trace.material_instances[0];
    assert_eq!(material.level, None);
    assert!(trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 78449284)
        .unwrap()
        .rank
        .is_some());
}

#[test]
fn final_public_facts_do_not_expose_opponent_facedown_cards() {
    let (mut result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    result.checkpoint.cards.push(StateCard {
        code: 25542642,
        player: 1,
        location: 8,
        sequence: 0,
        position: 10,
        ..Default::default()
    });
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert!(trace
        .facts
        .cards
        .iter()
        .all(|c| c.player == 0 || c.position & 5 != 0));
}

#[test]
fn native_procedure_and_activation_usage_are_rebuilt_without_predictions() {
    let (result, witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert_eq!(trace.normal_remaining, Some(1));
    for id in [
        "83566725:empty_field_special",
        "83566725:deck_set",
        "85257384:trap_monster_special",
        "78449284:deck_special",
        "46072770:monster_search",
    ] {
        assert_eq!(trace.used.get(id), Some(&1), "{id}");
    }
}

#[test]
fn an_observed_draw_creates_a_hand_instance_without_reading_deck_order() {
    let (mut result, mut witnesses) = captured();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    result.events.truncate(8);
    result.resolved_decisions.clear();
    witnesses.truncate(1);
    let mut raw = vec![90, 0];
    raw.extend(1u32.to_le_bytes());
    raw.extend(36426778u32.to_le_bytes());
    raw.extend(10u32.to_le_bytes());
    result.events.push(decode_frame(9, &raw).unwrap());
    let idle = result.events[7].raw.clone();
    result.events.push(decode_frame(10, &idle).unwrap());
    result.checkpoint = witnesses[0].public.visible.clone();
    result.checkpoint.cards.push(StateCard {
        code: 36426778,
        player: 0,
        location: 2,
        sequence: 5,
        position: 10,
        ..Default::default()
    });
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let card = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 36426778)
        .unwrap();
    assert!(card.identity_known);
    assert_eq!(card.instance, "draw:9:0");
    assert_eq!(trace.draws[0].cards, vec![36426778]);
}

#[test]
fn query_capture_binds_the_actual_stopped_prefix() {
    let (result, _) = captured();
    let witness = QueryWitness::capture(&result).unwrap();
    assert_eq!(witness.event, 105);
    assert_eq!(
        witness.public,
        ygo_engine_adapter::first_turn_public_state(&result.checkpoint)
    );
    let mut changed = result.clone();
    changed.prompt.as_mut().unwrap().id = 104;
    assert!(QueryWitness::capture(&changed).is_err());
}

#[test]
#[ignore = "opt-in: independent frozen 2026 assets; charged query audit, not autonomous planning"]
fn captured_queries_match_fresh_native_prefixes_and_complete_replay() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let (result, witnesses) = captured();
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
    let path = root
        .join("data/runtime/tournament-2026/trace-audits")
        .join(format!(
            "queries-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let journal = CallJournal::open(
        &path,
        "native-trace-query-audit",
        "frozen-resource-prefix",
        512,
    )
    .unwrap();
    let receipt = verify_query_replays(&request, &result, &witnesses, journal.clone()).unwrap();
    assert!(receipt.matches(&request, &result, &witnesses));
    assert_eq!(journal.stats().unwrap().consumed, 8);
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert_eq!(trace.used.get("78449284:deck_special"), Some(&1));
}

#[test]
#[ignore = "opt-in: independent frozen 2026 assets; charged Ash query audit, not recovery acceptance"]
fn captured_ash_anchor_queries_match_independent_native_replay() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let (result, witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
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
        .join("data/runtime/tournament-2026/trace-audits")
        .join(format!(
            "ash-queries-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let journal = CallJournal::open(
        &path,
        "native-ash-query-audit",
        "frozen-scythe-ash-prefix",
        512,
    )
    .unwrap();
    let receipt = verify_query_replays(&request, &result, &witnesses, journal.clone()).unwrap();
    assert!(receipt.matches(&request, &result, &witnesses));
    assert_eq!(journal.stats().unwrap().consumed, 7);
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    assert_eq!(trace.window, TraceWindow::OwnMainAction);
    assert_eq!(trace.used.get("78449284:deck_special"), Some(&1));
}

#[test]
fn opponent_usage_is_not_spent_from_our_same_name_counter() {
    let (result, witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &catalog(), &pack, &witnesses).unwrap();
    let ash_key = pack
        .rules
        .iter()
        .find(|r| r.card_id == 14558127 && r.description.is_some())
        .unwrap()
        .usage
        .key
        .as_ref()
        .unwrap();
    assert!(!trace.used.contains_key(ash_key));
    assert_eq!(trace.used.get(&format!("p1:{ash_key}")), Some(&1));
}

#[test]
fn invalid_raw_controller_coordinates_are_rejected_without_indexing_outside_resources() {
    use sha2::{Digest, Sha256};
    let (mut result, mut witnesses) = captured();
    let index = result.events.iter().position(|e| e.opcode == 50).unwrap();
    let event = &result.events[index];
    let mut raw = event.raw.clone();
    raw[5] = 2;
    result.events[index] = decode_frame(event.sequence, &raw).unwrap();
    for w in &mut witnesses {
        let raw: Vec<_> = result.events[..w.event as usize]
            .iter()
            .map(|e| &e.raw)
            .collect();
        w.raw_prefix_sha256 = format!("{:x}", Sha256::digest(serde_json::to_vec(&raw).unwrap()));
    }
    assert!(actual_trace_v6(
        &result,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap(),
        &witnesses
    )
    .is_err());
}

#[test]
fn actual_resource_container_relations_are_explicit_and_locks_are_not_assumed() {
    let (result, witnesses) = read_capture(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-ash.json"
    ));
    let trace = actual_trace_v6(
        &result,
        &catalog(),
        &FirstTurnKnowledge::builtin().unwrap(),
        &witnesses,
    )
    .unwrap();
    let host = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 78449284 && c.location == 4)
        .unwrap();
    assert_eq!(
        trace
            .material_hosts
            .get(&trace.material_instances[0].instance),
        Some(&host.instance)
    );
    assert_eq!(trace.restrictions.special_allowed, Some(true));
    assert_eq!(trace.restrictions.dark_only, Some(false));
    assert_eq!(trace.restrictions.extra_xyz_only, Some(false));
    assert!(trace.restrictions.unknown_rules.is_empty());
}
