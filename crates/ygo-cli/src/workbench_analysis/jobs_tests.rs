use super::jobs::*;
use super::tests::{fixtures, spec};
use super::*;
use serde_json::{json, Value};
use std::sync::atomic::{AtomicU64, Ordering};
use ygo_search::combo::ScoringConfig;

static NEXT: AtomicU64 = AtomicU64::new(0);

fn frozen() -> FrozenAnalysisInput {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1b1-analysis-job-tests/fixtures")
        .join(format!(
            "{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::Relaxed)
        ));
    std::fs::create_dir_all(&root).unwrap();
    let (drafts, snapshots, engine, catalog_id, banlist_id, draft) = fixtures(&root);
    let stored = drafts.create(draft.clone()).unwrap();
    let frozen = freeze_analysis_input(
        &drafts,
        spec(
            stored.id.clone(),
            stored.revision.clone(),
            banlist_id,
            draft.main[..5].to_vec(),
        ),
        engine,
        &snapshots,
        &catalog_id,
    )
    .unwrap();
    let before = serde_json::to_value(&frozen.request).unwrap();
    let owned_job =
        AnalysisJobRecordV1::new("1".repeat(32), &frozen, ScoringConfig::default(), 100).unwrap();
    let before_job = owned_job.encode_json().unwrap();
    drafts
        .update(
            &stored.id,
            &stored.revision,
            ygo_domain::DeckDocumentV1::new("Later", vec![99; 40], vec![], vec![]).unwrap(),
        )
        .unwrap();
    std::fs::remove_dir_all(snapshots.root).unwrap();
    assert_eq!(serde_json::to_value(&frozen.request).unwrap(), before);
    assert_eq!(owned_job.encode_json().unwrap(), before_job);
    assert!(AnalysisJobRecordV1::read_json(&before_job).is_ok());
    frozen
}

fn queued() -> AnalysisJobRecordV1 {
    AnalysisJobRecordV1::new("1".repeat(32), &frozen(), ScoringConfig::default(), 100).unwrap()
}

fn report(termination: &str, lines: u64) -> AnalysisJobReportRefV1 {
    AnalysisJobReportRefV1 {
        report_id: "2".repeat(32),
        sha256: "a".repeat(64),
        termination: termination.into(),
        verified_lines: lines,
    }
}

#[test]
fn job_round_trip_copies_only_path_free_input_and_preserves_choices() {
    let frozen = frozen();
    let record =
        AnalysisJobRecordV1::new("1".repeat(32), &frozen, ScoringConfig::default(), 100).unwrap();
    let text = String::from_utf8(record.encode_json().unwrap()).unwrap();
    assert!(!text.contains("worker_path"));
    assert!(!text.contains("runtime_request"));
    assert!(!text.contains("Card 1"));
    assert!(!text.contains("synthetic worker"));
    assert!(!text.contains(
        &frozen
            .runtime_request
            .engine
            .worker_path
            .to_string_lossy()
            .to_string()
            .replace('\\', "\\\\")
    ));
    let restored = AnalysisJobRecordV1::read_json(text.as_bytes()).unwrap();
    assert_eq!(
        restored.encode_json().unwrap(),
        record.encode_json().unwrap()
    );
    assert_eq!(restored.input().request.deck, frozen.request.deck);
    assert_eq!(
        restored.input().identity.input_sha256,
        frozen.identity.input_sha256
    );
    assert_eq!(restored.state(), AnalysisJobState::Queued);
    assert_eq!(restored.revision(), 1);
}

#[test]
fn job_state_matrix_is_revision_checked_and_terminal_states_never_restart() {
    let q = queued();
    let running = q.transition(1, AnalysisJobEvent::Start, 101).unwrap();
    let completed = running
        .transition(
            2,
            AnalysisJobEvent::ReportPublished(report("exhausted", 1)),
            102,
        )
        .unwrap();
    assert_eq!(completed.state(), AnalysisJobState::Completed);
    let events = [
        AnalysisJobEvent::Start,
        AnalysisJobEvent::Cancel,
        AnalysisJobEvent::ClassifyRestart,
        AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
        AnalysisJobEvent::ReportPublished(report("exhausted", 1)),
    ];
    let terminals = [
        completed,
        q.transition(1, AnalysisJobEvent::Cancel, 101).unwrap(),
        q.transition(1, AnalysisJobEvent::ClassifyRestart, 101)
            .unwrap(),
        running
            .transition(2, AnalysisJobEvent::ClassifyRestart, 102)
            .unwrap(),
        running
            .transition(
                2,
                AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
                102,
            )
            .unwrap(),
        running
            .transition(
                2,
                AnalysisJobEvent::ReportPublished(report("node_budget:no_verified_lines", 0)),
                102,
            )
            .unwrap(),
    ];
    for terminal in terminals {
        let before = terminal.encode_json().unwrap();
        for event in &events {
            assert!(terminal
                .transition(terminal.revision(), event.clone(), 103)
                .is_err());
        }
        assert_eq!(terminal.encode_json().unwrap(), before);
    }
    assert_eq!(
        running
            .transition(1, AnalysisJobEvent::Cancel, 102)
            .unwrap_err()
            .code(),
        "job_revision_conflict"
    );
    assert_eq!(
        q.transition(1, AnalysisJobEvent::Start, 99)
            .unwrap_err()
            .code(),
        "job_time_invalid"
    );
    assert!(q
        .transition(
            1,
            AnalysisJobEvent::ReportPublished(report("exhausted", 1)),
            101
        )
        .is_err());
    assert!(q
        .transition(
            1,
            AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
            101
        )
        .is_err());
    assert!(running.transition(2, AnalysisJobEvent::Start, 102).is_err());
    assert!(running
        .transition(2, AnalysisJobEvent::Cancel, 102)
        .is_err());
    assert_eq!(q.revision(), 1);
}

#[test]
fn job_report_outcomes_bind_termination_and_empty_verified_lines() {
    let running = queued()
        .transition(1, AnalysisJobEvent::Start, 101)
        .unwrap();
    for (reason, state) in [
        ("exhausted", AnalysisJobState::Completed),
        ("node_budget", AnalysisJobState::BudgetLimited),
        ("time_budget", AnalysisJobState::BudgetLimited),
        ("depth_budget", AnalysisJobState::BudgetLimited),
    ] {
        assert_eq!(
            running
                .transition(2, AnalysisJobEvent::ReportPublished(report(reason, 1)), 102)
                .unwrap()
                .state(),
            state
        );
        let empty = running
            .transition(
                2,
                AnalysisJobEvent::ReportPublished(report(
                    &format!("{reason}:no_verified_lines"),
                    0,
                )),
                102,
            )
            .unwrap();
        assert_eq!(empty.state(), state);
    }
    for (reason, lines) in [
        ("exhausted", 0),
        ("exhausted:no_verified_lines", 1),
        ("unknown", 1),
    ] {
        assert!(running
            .transition(
                2,
                AnalysisJobEvent::ReportPublished(report(reason, lines)),
                102
            )
            .is_err());
    }
    let mut invalid = report("exhausted", 1);
    invalid.report_id = "C:/private/report.json".into();
    assert!(running
        .transition(2, AnalysisJobEvent::ReportPublished(invalid), 102)
        .is_err());
    assert!(running
        .transition(
            2,
            AnalysisJobEvent::ReportPublished(report("exhausted", 6)),
            102
        )
        .is_err());
}

#[test]
fn job_reader_rejects_defaults_unknowns_numbers_and_tampered_bindings() {
    let record = queued();
    let value: Value = serde_json::from_slice(&record.encode_json().unwrap()).unwrap();
    for pointer in [
        "/revision",
        "/created_at_ms",
        "/input/request/seed",
        "/input/request/search/top_k",
    ] {
        for number in [json!(true), json!(1.0), json!(-1), Value::Null] {
            let mut changed = value.clone();
            *changed.pointer_mut(pointer).unwrap() = number;
            assert!(
                AnalysisJobRecordV1::read_json(&serde_json::to_vec(&changed).unwrap()).is_err(),
                "{pointer}"
            );
        }
    }
    for pointer in [
        "/input/request",
        "/input/request/search",
        "/input/request/deck",
        "/input/identity",
        "",
    ] {
        let mut changed = value.clone();
        let obj = changed
            .pointer_mut(pointer)
            .unwrap()
            .as_object_mut()
            .unwrap();
        let key = obj.keys().next().unwrap().clone();
        obj.remove(&key);
        assert!(AnalysisJobRecordV1::read_json(&serde_json::to_vec(&changed).unwrap()).is_err());
        let mut changed = value.clone();
        changed
            .pointer_mut(pointer)
            .unwrap()
            .as_object_mut()
            .unwrap()
            .insert("path".into(), json!("C:/private"));
        assert!(AnalysisJobRecordV1::read_json(&serde_json::to_vec(&changed).unwrap()).is_err());
    }
    for (pointer, replacement) in [
        ("/input/request/seed", json!(99)),
        ("/input/identity/worker_sha256", json!("b".repeat(64))),
        ("/input/binding_sha256", json!("0".repeat(64))),
        ("/input/scoring/complexity", json!(-7.0)),
        ("/input/request/catalog_id", json!("latest")),
        ("/input/request/banlist_id", json!("latest-ocg")),
        ("/input/request/search/node_budget", json!(0)),
        ("/input/request/opening_hand", json!([99, 99, 99, 99, 99])),
        ("/state", json!("completed")),
        ("/report", json!({})),
    ] {
        let mut changed = value.clone();
        *changed.pointer_mut(pointer).unwrap() = replacement;
        assert!(
            AnalysisJobRecordV1::read_json(&serde_json::to_vec(&changed).unwrap()).is_err(),
            "{pointer}"
        );
    }
    let text = String::from_utf8(record.encode_json().unwrap()).unwrap();
    let repeated = text.replacen("\"seed\": 1", "\"seed\": 1, \"seed\": 1", 1);
    assert!(AnalysisJobRecordV1::read_json(repeated.as_bytes()).is_err());
    assert!(AnalysisJobRecordV1::read_json(&text.as_bytes()[..text.len() - 1]).is_err());
    assert!(AnalysisJobRecordV1::read_json(format!("{text} {{}}").as_bytes()).is_err());
    let scoring = ScoringConfig {
        complexity: f64::NAN,
        ..ScoringConfig::default()
    };
    assert!(AnalysisJobRecordV1::new("1".repeat(32), &frozen(), scoring, 100).is_err());
}

#[test]
fn job_shared_schema_corpus_checks_independent_golden_and_strict_rejections() {
    let corpus: Value = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/workbench-analysis-job-v1-cases.json"
    ))
    .unwrap();
    let golden = &corpus["golden"];
    // Hashes independently computed with Python hashlib over literal typed
    // tuples, not produced by the job constructor or checksum implementation.
    assert_eq!(
        golden["input"]["identity"]["input_sha256"],
        "03f1466acc8d6e14ec323e64e1a138c309e763863859aefebeac33391b803e37"
    );
    assert_eq!(
        golden["input"]["binding_sha256"],
        "725d95638712073d1f008bd0088c24cce088c8d21ecbb7024c2dc94b5fd92aa6"
    );
    for case in corpus["cases"].as_array().unwrap() {
        let mut value = golden.clone();
        for patch in case["patches"].as_array().unwrap() {
            let pointer = patch["pointer"].as_str().unwrap();
            let (parent, key) = pointer.rsplit_once('/').unwrap();
            let obj = value.pointer_mut(parent).unwrap().as_object_mut().unwrap();
            if patch["remove"].as_bool() == Some(true) {
                obj.remove(key).unwrap();
            } else {
                obj.insert(key.into(), patch["value"].clone());
            }
        }
        let mut text = serde_json::to_string(&value).unwrap();
        for replacement in case["replace"].as_array().unwrap() {
            let from = replacement[0].as_str().unwrap();
            assert!(text.contains(from), "{}", case["name"]);
            text = text.replacen(from, replacement[1].as_str().unwrap(), 1);
        }
        if let Some(suffix) = case["suffix"].as_str() {
            text.push_str(suffix);
        }
        assert_eq!(
            AnalysisJobRecordV1::read_json(text.as_bytes()).is_ok(),
            case["rust_valid"].as_bool().unwrap(),
            "{}",
            case["name"]
        );
    }
}

#[test]
fn job_constructor_checks_runtime_binding_and_all_scoring_weights() {
    let original = frozen();
    let scoring = ScoringConfig::default();
    let mut changed = original.clone();
    changed.runtime_request.seed += 1;
    assert!(AnalysisJobRecordV1::new("1".repeat(32), &changed, scoring.clone(), 0).is_err());
    let mut changed = original.clone();
    changed.runtime_request.versions.catalog = "latest".into();
    assert!(AnalysisJobRecordV1::new("1".repeat(32), &changed, scoring.clone(), 0).is_err());
    let mut changed = original.clone();
    changed.identity.initializer = "C:/private/initializer".into();
    assert!(AnalysisJobRecordV1::new("1".repeat(32), &changed, scoring.clone(), 0).is_err());
    for weight in 0..4 {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut scoring = scoring.clone();
            match weight {
                0 => scoring.board_interaction = bad,
                1 => scoring.resource_advantage = bad,
                2 => scoring.follow_up = bad,
                _ => scoring.complexity = bad,
            }
            assert!(AnalysisJobRecordV1::new("1".repeat(32), &original, scoring, 0).is_err());
        }
    }
    let q = AnalysisJobRecordV1::new("1".repeat(32), &original, scoring, u64::MAX).unwrap();
    assert!(q.transition(1, AnalysisJobEvent::Start, u64::MAX).is_ok());
    for invalid in [
        AnalysisJobFailure::ServiceRestarted,
        AnalysisJobFailure::CompletionUncertain,
    ] {
        assert!(q
            .transition(1, AnalysisJobEvent::Start, u64::MAX)
            .unwrap()
            .transition(2, AnalysisJobEvent::Fail(invalid), u64::MAX)
            .is_err());
    }
}

#[test]
fn job_finite_scoring_weights_round_trip_without_changing_the_digest() {
    let frozen = frozen();
    for weight in [
        f64::MAX,
        f64::MIN,
        f64::MIN_POSITIVE,
        f64::from_bits(1),
        -0.0,
        1.2345678901234567,
        1.0000000000000002,
        0.8455124082255701,
    ] {
        let scoring = ScoringConfig {
            complexity: weight,
            ..ScoringConfig::default()
        };
        let record = AnalysisJobRecordV1::new("1".repeat(32), &frozen, scoring, 0).unwrap();
        let read = AnalysisJobRecordV1::read_json(&record.encode_json().unwrap()).unwrap();
        assert_eq!(read.input().scoring.complexity.to_bits(), weight.to_bits());
    }
}

#[test]
fn job_finite_bit_pattern_scoring_round_trips() {
    let frozen = frozen();
    let mut bits = 0x1234_5678_9abc_def0u64;
    for _ in 0..4096 {
        bits = bits.wrapping_mul(6364136223846793005).wrapping_add(1);
        let weight = f64::from_bits(bits);
        if !weight.is_finite() {
            continue;
        }
        let scoring = ScoringConfig {
            complexity: weight,
            ..ScoringConfig::default()
        };
        let record = AnalysisJobRecordV1::new("1".repeat(32), &frozen, scoring, 0).unwrap();
        let result = AnalysisJobRecordV1::read_json(&record.encode_json().unwrap());
        assert!(result.is_ok(), "finite bits {bits:016x}: {result:?}");
        assert_eq!(result.unwrap().input().scoring.complexity.to_bits(), bits);
    }
}
