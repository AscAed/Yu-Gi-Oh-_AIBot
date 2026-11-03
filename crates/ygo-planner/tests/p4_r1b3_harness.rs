#[path = "../examples/p4_r1b3/harness.rs"]
#[allow(dead_code)]
mod harness;

use std::{path::PathBuf, sync::OnceLock};
use ygo_domain::Catalog;
use ygo_engine_adapter::{CallJournal, RunDuelRequest, StateCard};
use ygo_goal::{AuditedQueries, Goal, QueryWitness};
use ygo_knowledge::first_turn::FirstTurnKnowledge;
use ygo_planner::first_turn::{
    begin_resumable_partial_execution_v1, ForecastPlan, ResumablePartialExecutionV1,
};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn prepared_fixture() -> &'static (harness::Prepared, PathBuf) {
    static PREPARED: OnceLock<(harness::Prepared, PathBuf)> = OnceLock::new();
    PREPARED.get_or_init(|| {
        let output_root = std::env::temp_dir().join(format!(
            "p4-r1b3-prepare-only-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        assert!(!output_root.exists());
        let prepared = harness::prepare(&repo_root(), &output_root).unwrap();
        (prepared, output_root)
    })
}

#[test]
fn prepare_only_does_not_create_scope_or_charge_calls() {
    let (prepared, output_root) = prepared_fixture();
    assert!(!output_root.exists());
    let expected_worker = std::env::current_exe()
        .unwrap()
        .parent()
        .unwrap()
        .parent()
        .unwrap()
        .join(format!("ygo-engine-worker{}", std::env::consts::EXE_SUFFIX));
    assert_eq!(prepared.worker_path, expected_worker);
    assert_eq!(
        prepared.expected_route,
        vec![
            "78449284:two_dark_level_three".to_owned(),
            "25538345:normal_summon_and_set".to_owned(),
        ]
    );
    assert_eq!(prepared.summary()["worker_processes_started"], 0);
    assert!(!prepared.resume_journal_path.exists());
    assert!(!prepared.replay_journal_path.exists());
}

#[test]
fn prepare_only_rejects_changed_fixture_assets_or_route() {
    let (prepared, _) = prepared_fixture();
    assert!(harness::validate_digest("fixture", &prepared.trace_sha256, &"0".repeat(64)).is_err());
    assert!(harness::validate_digest("asset", &prepared.core_sha256, &"0".repeat(64)).is_err());

    let mut changed = prepared.plan.clone();
    changed.steps[0].rule_id = "unapproved:route".into();
    assert!(harness::validate_route(&changed).is_err());
}

#[test]
fn event49_gate_compares_public_witness_not_private_checkpoint_encoding() {
    let (prepared, _) = prepared_fixture();
    let witness = prepared
        .queries
        .iter()
        .find(|query| query.event == 49)
        .expect("fixed event-49 witness");
    assert_eq!(witness.public.opponent_deck_count, 39);
    assert_eq!(witness.public.opponent_hand_count, 1);

    let mut native = prepared.expected_result.clone();
    native.checkpoint.cards.push(StateCard {
        code: 14558127,
        player: 1,
        location: 64,
        position: 8,
        ..Default::default()
    });
    assert!(harness::validate_initial_result(prepared, &native).is_ok());

    native.checkpoint.lp[0] += 1;
    assert!(harness::validate_initial_result(prepared, &native).is_err());
}

#[test]
fn absolute_windows_path_prefix_is_not_checked_as_a_filesystem_entry() {
    let path = repo_root()
        .canonicalize()
        .unwrap()
        .join("target/p4-r1b3/path-check/nonexistent");
    let result = harness::reject_existing_symlink(&path);
    assert!(
        result.is_ok(),
        "extended path prefix handling failed: {result:?}"
    );
}

#[test]
#[allow(clippy::type_complexity)]
fn production_begin_requires_live_audited_queries() {
    #[allow(clippy::too_many_arguments)]
    fn begin_with_receipt(
        request: &RunDuelRequest,
        initial_call: u64,
        initial_queries: &[QueryWitness],
        receipt: &AuditedQueries,
        plan: &ForecastPlan,
        catalog: &Catalog,
        pack: &FirstTurnKnowledge,
        goal: &Goal,
        journal: std::sync::Arc<CallJournal>,
    ) -> Result<ResumablePartialExecutionV1, String> {
        begin_resumable_partial_execution_v1(
            request,
            initial_call,
            initial_queries,
            receipt,
            plan,
            catalog,
            pack,
            goal,
            journal,
        )
    }

    let _: fn(
        &RunDuelRequest,
        u64,
        &[QueryWitness],
        &AuditedQueries,
        &ForecastPlan,
        &Catalog,
        &FirstTurnKnowledge,
        &Goal,
        std::sync::Arc<CallJournal>,
    ) -> Result<ResumablePartialExecutionV1, String> = begin_with_receipt;
}
