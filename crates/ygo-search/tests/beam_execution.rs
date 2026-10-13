use ygo_engine_adapter::*;
use ygo_search::combo::*;
struct Tree;
impl EngineAdapter for Tree {
    fn doctor(&self) -> DoctorReport {
        unreachable!()
    }
    fn run(&self, r: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        let path = &r.decisions;
        let good = path.first().is_some_and(|d| {
            d.choice
                == Choice::Command {
                    command: 0,
                    index: 0,
                }
        });
        let ended = path
            .iter()
            .any(|d| matches!(d.choice, Choice::Command { command: 7, .. }));
        let choices = match path.len() {
            0 => vec![
                Choice::Command {
                    command: 7,
                    index: 0,
                },
                Choice::Command {
                    command: 0,
                    index: 0,
                },
                Choice::Command {
                    command: 3,
                    index: 0,
                },
            ],
            1 => (0..3).map(|index| Choice::Option { index }).collect(),
            _ => vec![Choice::Command {
                command: 7,
                index: 0,
            }],
        };
        let mut state = Checkpoint::default();
        let n = if good && !ended {
            1
        } else if path.len() > 1 {
            5
        } else {
            0
        };
        state.cards = (0..n)
            .map(|i| StateCard {
                code: 100 + i,
                location: 2,
                ..Default::default()
            })
            .collect();
        if good && ended {
            state.cards.push(StateCard {
                code: 84013237,
                location: 4,
                position: 1,
                overlay: vec![1, 2],
                ..Default::default()
            });
        }
        Ok(DuelResult {
            protocol_version: 2,
            status: if ended {
                DuelStatus::EngineVerified
            } else {
                DuelStatus::DecisionRequired
            },
            events: vec![],
            prompt: if ended {
                None
            } else {
                Some(Prompt {
                    id: path.len() as u64,
                    player: 0,
                    opcode: 11,
                    actions: choices
                        .into_iter()
                        .map(|choice| Action {
                            choice,
                            label: String::new(),
                            card_ids: vec![],
                            bytes: vec![],
                        })
                        .collect(),
                })
            },
            checkpoint: state,
            error: None,
            versions: r.versions.clone(),
            loaded_scripts: Default::default(),
            steps: vec![],
            resolved_decisions: path.clone(),
            coverage_gaps: vec![],
            peak_working_set_bytes: None,
        })
    }
}
fn request() -> RunDuelRequest {
    RunDuelRequest {
        protocol_version: 2,
        engine: Default::default(),
        deck: Default::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions: Default::default(),
        probe_only: false,
    }
}
#[test]
fn beam_keeps_a_costly_setup_branch_and_independently_replays_results() {
    let budget = SearchBudget {
        beam_width: 2,
        node_budget: 100,
        max_depth: 5,
        ..Default::default()
    };
    let a = search(&Tree, &request(), &budget, &ScoringConfig::default()).unwrap();
    assert!(a.lines[0].evaluation.interaction > 0.0);
    assert!(a.lines.iter().all(|l| l.replay_verified));
    let b = search(&Tree, &request(), &budget, &ScoringConfig::default()).unwrap();
    assert_eq!(
        a.lines.iter().map(|l| &l.id).collect::<Vec<_>>(),
        b.lines.iter().map(|l| &l.id).collect::<Vec<_>>()
    );
    let c = search(
        &Tree,
        &request(),
        &budget,
        &ScoringConfig {
            board_interaction: 0.0,
            resource_advantage: -1.0,
            follow_up: 0.0,
            complexity: -0.25,
        },
    )
    .unwrap();
    assert_ne!(a.lines[0].id, c.lines[0].id);
    assert_eq!(c.lines[0].evaluation.interaction, 0.0);
}
