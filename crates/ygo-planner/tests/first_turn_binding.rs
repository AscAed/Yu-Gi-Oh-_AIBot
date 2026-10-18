//! Binding checks use recorded raw prompts; these are not rule certificates.
use ygo_engine_adapter::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::*;
fn stopped(event: usize) -> DuelResult {
    let mut v: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.trace-resource.json"
    ))
    .unwrap();
    v["result"]["events"] = serde_json::json!([]);
    let mut r: DuelResult = serde_json::from_value(v["result"].clone()).unwrap();
    r.events = v["frames"].as_array().unwrap()[..event]
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
    r.prompt = parse_prompt(event as u64, &r.events.last().unwrap().raw).unwrap();
    r
}
#[test]
fn source_effect_and_instance_coordinates_must_all_match_the_raw_prompt() {
    let r = stopped(66);
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let rule = pack.rule("78449284:deck_special").unwrap();
    let mut source = StateCard {
        code: 78449284,
        player: 0,
        location: 4,
        sequence: 0,
        ..Default::default()
    };
    assert!(bind_start(&r, &source, rule, TransitionKind::Activate, false).is_ok());
    let mut wrong = rule.clone();
    wrong.description = wrong.description.map(|d| d + 1);
    assert!(bind_start(&r, &source, &wrong, TransitionKind::Activate, false).is_err());
    source.sequence = 1;
    assert!(bind_start(&r, &source, rule, TransitionKind::Activate, false).is_err());
}
#[test]
fn generic_trigger_text_cannot_authorize_a_start_without_an_observed_trigger() {
    let r = stopped(86);
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let rule = pack.rule("46072770:monster_search").unwrap();
    let source = StateCard {
        code: 46072770,
        player: 0,
        location: 4,
        sequence: 1,
        ..Default::default()
    };
    assert!(bind_start(&r, &source, rule, TransitionKind::Trigger, false).is_err());
    assert_eq!(
        bind_start(&r, &source, rule, TransitionKind::Trigger, true).unwrap(),
        Choice::YesNo { yes: true }
    );
}
#[test]
fn duplicate_overlay_costs_bind_the_actual_material_index() {
    let metadata = (0..2)
        .map(|index| ActionMetadata {
            choice: Choice::Cards {
                indices: vec![index],
            },
            source: None,
            effect_description: None,
            selected: vec![CardReference {
                code: 25538345,
                player: 0,
                location: 132,
                sequence: 0,
                position: index,
            }],
            selection_group: None,
        })
        .collect::<Vec<_>>();
    let pick = SemanticSelection {
        role: "cost".into(),
        stage: "cost".into(),
        card_id: 25538345,
        instance: Some("physical-second".into()),
        from: 132,
        host: Some("xyz-host".into()),
    };
    let actual = StateCard {
        code: 25538345,
        player: 0,
        location: 132,
        sequence: 0,
        position: 1,
        ..Default::default()
    };
    assert_eq!(
        bind_pick(&metadata, &pick, Some(&actual)).unwrap(),
        Choice::Cards { indices: vec![1] }
    );
    assert!(bind_pick(&metadata, &pick, None).is_err());
}
