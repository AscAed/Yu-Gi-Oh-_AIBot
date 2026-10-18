use ygo_domain::{CardId, EngineEvent};
use ygo_search::{CandidateLine, Scenario, SearchConfig, Searcher};

#[test]
fn ranks_candidates_by_score_then_id_deterministically() {
    let candidates = vec![
        CandidateLine::new("beta", Scenario::NoInterruption, vec![]).with_metrics(2, 1, 0, 0),
        CandidateLine::new("alpha", Scenario::NoInterruption, vec![]).with_metrics(2, 1, 0, 0),
        CandidateLine::new(
            "gamma",
            Scenario::MaxxC,
            vec![EngineEvent::SpecialSummon { card: CardId(1) }],
        )
        .with_metrics(3, 1, 2, 0),
    ];

    let results = Searcher::new(SearchConfig::default()).rank(candidates);

    assert_eq!(results[0].id, "alpha");
    assert_eq!(results[1].id, "beta");
    assert_eq!(results[2].id, "gamma");
}

#[test]
fn maxx_c_penalizes_opponent_draws() {
    let safe = CandidateLine::new("safe", Scenario::MaxxC, vec![]).with_metrics(2, 1, 0, 0);
    let greedy = CandidateLine::new("greedy", Scenario::MaxxC, vec![]).with_metrics(4, 1, 3, 0);

    let results = Searcher::new(SearchConfig::default()).rank(vec![greedy, safe]);

    assert_eq!(results[0].id, "safe");
}
