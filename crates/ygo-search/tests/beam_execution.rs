use std::sync::atomic::{AtomicUsize, Ordering};
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

struct ObservedTree {
    calls: AtomicUsize,
    error_stage: &'static str,
}

impl ObservedTree {
    fn new() -> Self {
        Self {
            calls: AtomicUsize::new(0),
            error_stage: "process",
        }
    }

    fn with_error_stage(error_stage: &'static str) -> Self {
        Self {
            calls: AtomicUsize::new(0),
            error_stage,
        }
    }
}

impl EngineAdapter for ObservedTree {
    fn doctor(&self) -> DoctorReport {
        unreachable!("synthetic observed adapter does not probe a worker")
    }

    fn run(&self, r: &RunDuelRequest) -> Result<DuelResult, WorkerError> {
        if r.decisions.last().is_some_and(|decision| {
            decision.choice
                == Choice::Command {
                    command: 3,
                    index: 0,
                }
        }) {
            return Err(WorkerError::new(
                "fixture_exit",
                self.error_stage,
                "synthetic exit",
            ));
        }
        Tree.run(r)
    }
}

impl ProcessObservedAdapter for ObservedTree {
    fn run_process_observed(&self, r: &RunDuelRequest) -> ProcessObservedOutcome {
        let call = self.calls.fetch_add(1, Ordering::SeqCst);
        let result = self.run(r);
        let failed = result.is_err();
        ProcessObservedOutcome {
            result,
            observation: ProcessRunObservation {
                worker_executable_sha256: Some("a".repeat(64)),
                spawn_status: ProcessSpawnStatus::Spawned,
                worker_pid: Some(1000 + call as u32),
                request_status: ProcessIoStatus::Complete,
                request_sha256: Some(format!("{call:064x}")),
                request_bytes: Some(1),
                response_status: ProcessIoStatus::Complete,
                response_sha256: Some(format!("{:064x}", call + 1)),
                response_bytes: Some(2),
                response_validation: if failed {
                    ProcessResponseValidation::NotAttempted
                } else {
                    ProcessResponseValidation::Parsed
                },
                termination: ProcessTermination::Exited,
                exit_code: Some(if failed { 7 } else { 0 }),
                elapsed_ms: call as u64,
            },
        }
    }
}

#[test]
fn observed_search_orders_unique_attempts_across_exploration_failure_and_replay() {
    let adapter = ObservedTree::new();
    let budget = SearchBudget {
        beam_width: 4,
        node_budget: 100,
        max_depth: 5,
        ..Default::default()
    };
    let mut next_id = 0u64;
    let outcome = search_with_observations(
        &adapter,
        &request(),
        &budget,
        &ScoringConfig::default(),
        || {
            next_id += 1;
            Ok(format!("{next_id:032x}"))
        },
    );

    let report = outcome.report.expect("synthetic search completes");
    assert!(report.lines.iter().any(|line| line.replay_verified));
    assert_eq!(outcome.attempts.len(), report.stats.engine_calls);
    assert_eq!(
        outcome
            .attempts
            .iter()
            .map(|attempt| attempt.ordinal)
            .collect::<Vec<_>>(),
        (1..=outcome.attempts.len() as u64).collect::<Vec<_>>()
    );
    let ids = outcome
        .attempts
        .iter()
        .map(|attempt| attempt.attempt_id.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    assert_eq!(ids.len(), outcome.attempts.len());
    assert_eq!(outcome.attempts[0].phase, SearchAttemptPhase::Initial);
    assert!(outcome
        .attempts
        .iter()
        .any(|attempt| attempt.phase == SearchAttemptPhase::Baseline));
    let failed_exploration = outcome
        .attempts
        .iter()
        .position(|attempt| {
            attempt.phase == SearchAttemptPhase::Exploration
                && matches!(
                    attempt.result,
                    SearchAttemptResult::AdapterError { ref code, .. } if code == "fixture_exit"
                )
        })
        .expect("one exploratory adapter failure is recorded");
    assert!(outcome.attempts[failed_exploration + 1..]
        .iter()
        .any(|attempt| attempt.phase == SearchAttemptPhase::Replay));
    assert!(outcome.attempts.iter().all(|attempt| {
        attempt.process_observation.worker_pid.is_some()
            && attempt.process_observation.request_sha256.is_some()
    }));
}

#[test]
fn observed_search_rejects_reused_attempt_id_before_another_adapter_call() {
    let adapter = ObservedTree::new();
    let outcome = search_with_observations(
        &adapter,
        &request(),
        &SearchBudget::default(),
        &ScoringConfig::default(),
        || Ok("b".repeat(32)),
    );

    assert!(outcome.report.is_err());
    assert_eq!(outcome.attempts.len(), 1);
    assert_eq!(adapter.calls.load(Ordering::SeqCst), 1);
}

#[test]
fn observed_adapter_reserved_stage_is_not_misclassified_as_receipt_gate() {
    let adapter = ObservedTree::with_error_stage("attempt_receipt");
    let budget = SearchBudget {
        beam_width: 4,
        node_budget: 100,
        max_depth: 5,
        ..Default::default()
    };
    let mut next_id = 0u64;
    let outcome = search_with_observations(
        &adapter,
        &request(),
        &budget,
        &ScoringConfig::default(),
        || {
            next_id += 1;
            Ok(format!("{next_id:032x}"))
        },
    );

    let report = outcome
        .report
        .expect("adapter errors are search diagnostics, not receipt failures");
    assert!(report.stats.failed_branches > 0);
    assert_eq!(report.stats.engine_calls, outcome.attempts.len());
    assert_eq!(adapter.calls.load(Ordering::SeqCst), outcome.attempts.len());
    assert!(outcome.attempts.iter().any(|attempt| {
        attempt.phase == SearchAttemptPhase::Exploration
            && matches!(
                attempt.result,
                SearchAttemptResult::AdapterError { ref code, ref stage }
                    if code == "fixture_exit" && stage == "attempt_receipt"
            )
    }));
}

#[test]
fn receipt_callbacks_bracket_adapter_calls_and_stop_on_persistence_failure() {
    let adapter = ObservedTree::new();
    let mut next_id = 0u64;
    let mut events = Vec::new();
    let outcome = search_with_receipts(
        &adapter,
        &request(),
        &SearchBudget {
            beam_width: 2,
            node_budget: 20,
            max_depth: 3,
            ..Default::default()
        },
        &ScoringConfig::default(),
        || {
            next_id += 1;
            Ok(format!("{next_id:032x}"))
        },
        |event| {
            events.push(event);
            Ok(())
        },
    );

    assert!(outcome.report.is_ok());
    assert_eq!(events.len(), outcome.attempts.len() * 2);
    for pair in events.chunks_exact(2) {
        assert!(matches!(pair[0], SearchAttemptJournalEvent::Started(_)));
        assert!(matches!(pair[1], SearchAttemptJournalEvent::Finished(_)));
    }

    let start_failure_adapter = ObservedTree::new();
    let start_failure = search_with_receipts(
        &start_failure_adapter,
        &request(),
        &SearchBudget::default(),
        &ScoringConfig::default(),
        || Ok("d".repeat(32)),
        |_| Err("receipt start write failed".to_owned()),
    );
    assert!(start_failure.report.is_err());
    assert_eq!(start_failure_adapter.calls.load(Ordering::SeqCst), 0);
    assert!(start_failure.attempts.is_empty());

    let finish_failure_adapter = ObservedTree::new();
    let finish_failure = search_with_receipts(
        &finish_failure_adapter,
        &request(),
        &SearchBudget::default(),
        &ScoringConfig::default(),
        || Ok("e".repeat(32)),
        |event| match event {
            SearchAttemptJournalEvent::Started(_)
            | SearchAttemptJournalEvent::FfiEntered(_)
            | SearchAttemptJournalEvent::FfiReturned(_) => Ok(()),
            SearchAttemptJournalEvent::Finished(_) => Err("receipt result write failed".into()),
        },
    );
    assert!(finish_failure.report.is_err());
    assert_eq!(finish_failure_adapter.calls.load(Ordering::SeqCst), 1);
    assert_eq!(finish_failure.attempts.len(), 1);
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
