use super::jobs::*;
use super::queue::*;
use super::tests::{fixtures, spec};
use super::*;
use std::sync::{Arc, Barrier};
use ygo_search::combo::ScoringConfig;
fn frozen() -> FrozenAnalysisInput {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../target/w1b2-analysis-queue-tests")
        .join(ygo_storage::secure_random_hex(16).unwrap());
    std::fs::create_dir_all(&root).unwrap();
    let (drafts, snapshots, engine, catalog, banlist, draft) = fixtures(&root);
    let saved = drafts.create(draft.clone()).unwrap();
    freeze_analysis_input(
        &drafts,
        spec(saved.id, saved.revision, banlist, draft.main[..5].to_vec()),
        engine,
        &snapshots,
        &catalog,
    )
    .unwrap()
}
#[test]
fn capacity_cancel_and_settlement_preserve_binding() {
    let q = AnalysisJobQueue::default();
    let f = frozen();
    let first = q.enqueue(f.clone(), ScoringConfig::default(), 100).unwrap();
    assert!(q.enqueue(f.clone(), ScoringConfig::default(), 100).is_err());
    assert!(q.claim_next(99).is_err());
    let ticket = q.claim_next(101).unwrap().unwrap();
    assert_eq!(ticket.input().request.deck, first.input().request.deck);
    let second = q.enqueue(f.clone(), ScoringConfig::default(), 102).unwrap();
    assert!(q.enqueue(f.clone(), ScoringConfig::default(), 102).is_err());
    assert!(q.cancel(first.job_id(), 2, 103).is_err());
    assert!(q.cancel(second.job_id(), 2, 103).is_err());
    assert_eq!(
        q.cancel(second.job_id(), 1, 103).unwrap().state(),
        AnalysisJobState::Cancelled
    );
    assert!(q.claim_next(104).unwrap().is_none());
    assert!(q.settle(&ticket, AnalysisJobEvent::Cancel, 104).is_err());
    q.settle(
        &ticket,
        AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
        104,
    )
    .unwrap();
    assert!(q
        .settle(&ticket, AnalysisJobEvent::ClassifyRestart, 105)
        .is_err());
    for (reason, lines) in [
        ("exhausted", 1),
        ("exhausted:no_verified_lines", 0),
        ("node_budget", 1),
    ] {
        q.enqueue(f.clone(), ScoringConfig::default(), 106).unwrap();
        let t = q.claim_next(107).unwrap().unwrap();
        let mut bad = t.clone();
        bad.tamper_for_test();
        assert!(q
            .settle(&bad, AnalysisJobEvent::ClassifyRestart, 108)
            .is_err());
        assert!(q
            .settle(&t, AnalysisJobEvent::ClassifyRestart, 100)
            .is_err());
        let invalid = AnalysisJobReportRefV1 {
            report_id: "bad".into(),
            sha256: "b".repeat(64),
            termination: reason.into(),
            verified_lines: lines,
        };
        assert!(q
            .settle(&t, AnalysisJobEvent::ReportPublished(invalid), 108)
            .is_err());
        q.settle(
            &t,
            AnalysisJobEvent::ReportPublished(AnalysisJobReportRefV1 {
                report_id: "a".repeat(32),
                sha256: "b".repeat(64),
                termination: reason.into(),
                verified_lines: lines,
            }),
            108,
        )
        .unwrap();
    }
    q.enqueue(f, ScoringConfig::default(), 110).unwrap();
    let t = q.claim_next(111).unwrap().unwrap();
    assert_eq!(
        q.settle(&t, AnalysisJobEvent::ClassifyRestart, 112)
            .unwrap()
            .state(),
        AnalysisJobState::Unknown
    );
    assert!(q.snapshot().unwrap().running.is_none());
}
#[test]
fn cancel_and_claim_are_linearizable() {
    for _ in 0..8 {
        let q = Arc::new(AnalysisJobQueue::default());
        let r = q.enqueue(frozen(), ScoringConfig::default(), 1).unwrap();
        let b = Arc::new(Barrier::new(3));
        let a = {
            let q = q.clone();
            let b = b.clone();
            std::thread::spawn(move || {
                b.wait();
                q.claim_next(2).unwrap()
            })
        };
        let c = {
            let q = q.clone();
            let b = b.clone();
            std::thread::spawn(move || {
                b.wait();
                q.cancel(r.job_id(), 1, 2)
            })
        };
        b.wait();
        let t = a.join().unwrap();
        let cancelled = c.join().unwrap();
        assert_eq!(t.is_none(), cancelled.is_ok());
        assert!(q.claim_next(3).unwrap().is_none());
    }
}
#[test]
fn concurrent_admission_claim_and_settlement_have_one_winner() {
    let q = Arc::new(AnalysisJobQueue::default());
    let f = frozen();
    let b = Arc::new(Barrier::new(3));
    let handles: Vec<_> = (0..2)
        .map(|_| {
            let q = q.clone();
            let f = f.clone();
            let b = b.clone();
            std::thread::spawn(move || {
                b.wait();
                q.enqueue(f, ScoringConfig::default(), 1)
            })
        })
        .collect();
    b.wait();
    assert_eq!(
        handles
            .into_iter()
            .filter(|h| h.thread().id() != std::thread::current().id())
            .map(|h| h.join().unwrap().is_ok() as usize)
            .sum::<usize>(),
        1
    );
    let b = Arc::new(Barrier::new(3));
    let hs: Vec<_> = (0..2)
        .map(|_| {
            let q = q.clone();
            let b = b.clone();
            std::thread::spawn(move || {
                b.wait();
                q.claim_next(2).unwrap()
            })
        })
        .collect();
    b.wait();
    let ts: Vec<_> = hs.into_iter().filter_map(|h| h.join().unwrap()).collect();
    assert_eq!(ts.len(), 1);
    let t = ts[0].clone();
    let b = Arc::new(Barrier::new(3));
    let hs: Vec<_> = (0..2)
        .map(|_| {
            let q = q.clone();
            let b = b.clone();
            let t = t.clone();
            std::thread::spawn(move || {
                b.wait();
                q.settle(
                    &t,
                    AnalysisJobEvent::Fail(AnalysisJobFailure::AnalysisFailed),
                    3,
                )
            })
        })
        .collect();
    b.wait();
    assert_eq!(
        hs.into_iter()
            .map(|h| h.join().unwrap().is_ok() as usize)
            .sum::<usize>(),
        1
    );
    let r = q.enqueue(f, ScoringConfig::default(), 4).unwrap();
    assert_ne!(r.job_id(), t.record().job_id());
    let next = q.claim_next(5).unwrap().unwrap();
    assert!(q.settle(&t, AnalysisJobEvent::ClassifyRestart, 6).is_err());
    q.settle(&next, AnalysisJobEvent::ClassifyRestart, 6)
        .unwrap();
}
#[test]
fn cancelled_tasks_never_execute_and_settlement_does_not_dispatch() {
    let q = AnalysisJobQueue::default();
    let f = frozen();
    let first = q.enqueue(f.clone(), ScoringConfig::default(), 1).unwrap();
    q.cancel(first.job_id(), 1, 2).unwrap();
    let calls = std::sync::atomic::AtomicUsize::new(0);
    if q.claim_next(3).unwrap().is_some() {
        calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
    }
    assert_eq!(calls.load(std::sync::atomic::Ordering::SeqCst), 0);
    for (reason, expected) in [
        ("exhausted", AnalysisJobState::Completed),
        ("exhausted:no_verified_lines", AnalysisJobState::Completed),
        ("time_budget", AnalysisJobState::BudgetLimited),
        ("depth_budget", AnalysisJobState::BudgetLimited),
    ] {
        q.enqueue(f.clone(), ScoringConfig::default(), 4).unwrap();
        let t = q.claim_next(5).unwrap().unwrap();
        let waiting = q.enqueue(f.clone(), ScoringConfig::default(), 6).unwrap();
        let before = q.snapshot().unwrap();
        assert!(q.cancel(waiting.job_id(), 999, 7).is_err());
        let after = q.snapshot().unwrap();
        assert_eq!(
            before.queued.unwrap().encode_json().unwrap(),
            after.queued.unwrap().encode_json().unwrap()
        );
        assert_eq!(
            before.running.unwrap().encode_json().unwrap(),
            after.running.unwrap().encode_json().unwrap()
        );
        let lines = if reason.ends_with("no_verified_lines") {
            0
        } else {
            1
        };
        let done = q
            .settle(
                &t,
                AnalysisJobEvent::ReportPublished(AnalysisJobReportRefV1 {
                    report_id: "a".repeat(32),
                    sha256: "b".repeat(64),
                    termination: reason.into(),
                    verified_lines: lines,
                }),
                7,
            )
            .unwrap();
        assert_eq!(done.state(), expected);
        let s = q.snapshot().unwrap();
        assert!(s.running.is_none());
        assert_eq!(s.queued.unwrap().revision(), 1);
        q.cancel(waiting.job_id(), 1, 8).unwrap();
    }
}

