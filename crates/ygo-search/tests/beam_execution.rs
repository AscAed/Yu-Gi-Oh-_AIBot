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
            terminal_observation: None,
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
        scenario: None,
        interruption: None,
        first_turn: None,
        research_capture: None,
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

struct IdleLoop(std::sync::atomic::AtomicUsize);
impl EngineAdapter for IdleLoop {
    fn doctor(&self) -> DoctorReport {
        unreachable!("offline stub never diagnoses a worker")
    }
    fn run(&self, r: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        let mut raw = vec![11, 0];
        raw.extend([0; 24]);
        raw.extend([0, 1, 1]);
        let prompt = parse_prompt(r.decisions.len() as u64, &raw)
            .unwrap()
            .unwrap();
        for decision in &r.decisions {
            assert_eq!(
                prompt.encode(&decision.choice).unwrap(),
                match decision.choice {
                    Choice::Command {
                        command: 7,
                        index: 0,
                    } => vec![7, 0, 0, 0],
                    Choice::Command {
                        command: 8,
                        index: 0,
                    } => vec![8, 0, 0, 0],
                    _ => panic!("unexpected idle command"),
                }
            );
        }
        if r.decisions
            .last()
            .is_some_and(|d| matches!(d.choice, Choice::Command { command: 8, .. }))
        {
            self.0.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
        }
        let ended = r
            .decisions
            .last()
            .is_some_and(|d| matches!(d.choice, Choice::Command { command: 7, .. }));
        let mut result = DuelResult::failure(WorkerError::new("stub", "test", "unused"));
        result.protocol_version = r.protocol_version;
        result.versions = r.versions.clone();
        result.error = None;
        result.status = if ended {
            DuelStatus::EngineVerified
        } else {
            DuelStatus::DecisionRequired
        };
        result.checkpoint = Checkpoint::default();
        result.prompt = if ended { None } else { Some(prompt) };
        result.resolved_decisions = r.decisions.clone();
        Ok(result)
    }
}
#[test]
fn added_shuffle_branch_preserves_choice_encoding_and_budget_termination() {
    let adapter = IdleLoop(std::sync::atomic::AtomicUsize::new(0));
    let budget = SearchBudget {
        beam_width: 2,
        node_budget: 8,
        max_depth: 3,
        ..Default::default()
    };
    let report = search(&adapter, &request(), &budget, &ScoringConfig::default()).unwrap();
    assert!(report.stats.nodes <= 8);
    assert!(report.stats.max_decision_depth <= 3);
    assert!(!report.lines.is_empty());
    assert!(report.lines.iter().all(|line| line.replay_verified));
    assert!(adapter.0.load(std::sync::atomic::Ordering::Relaxed) > 0);
}
