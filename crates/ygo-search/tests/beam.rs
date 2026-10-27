use ygo_engine_adapter::*;
use ygo_search::combo::*;
#[test]
fn evaluation_reports_uncovered_effects_and_config_changes_ranking() {
    let state = Checkpoint {
        cards: vec![
            StateCard {
                code: 84013237,
                type_flags: 0x800021,
                player: 0,
                location: 4,
                position: 1,
                overlay: vec![1, 2],
                ..Default::default()
            },
            StateCard {
                code: 999,
                type_flags: 0x21,
                player: 0,
                location: 2,
                ..Default::default()
            },
        ],
        ..Default::default()
    };
    let config = ScoringConfig::default();
    let e = evaluate(&state, 3, &config);
    assert_eq!(e.interaction, 2.0);
    assert!(e.coverage_gaps.iter().any(|s| s.contains("999")));
    let changed = ScoringConfig {
        board_interaction: 0.0,
        ..config
    };
    assert!(evaluate(&state, 3, &changed).total < e.total);
}
#[test]
fn cache_key_preserves_effect_history_and_runtime_versions() {
    let request = RunDuelRequest {
        protocol_version: 2,
        engine: ProcessEngineConfig::default(),
        deck: Default::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions: Default::default(),
        probe_only: false,
        scenario: None,
        interruption: None,
        first_turn: None,
        research_capture: None,
    };
    let mut other = request.clone();
    other.decisions.push(Decision {
        prompt_id: 1,
        player: 0,
        choice: Choice::YesNo { yes: true },
    });
    assert_ne!(prefix_key(&request), prefix_key(&other));
    other = request.clone();
    other.versions.catalog = "different".into();
    assert_ne!(prefix_key(&request), prefix_key(&other));
}
