use ygo_storage::validate_date;
#[test]
fn rejects_impossible_analysis_dates() {
    for date in [
        "2026-00-01",
        "2026-02-29",
        "2026-04-31",
        "2026-13-01",
        "2026-10-00",
        "2026-1-01",
    ] {
        assert!(validate_date(date).is_err(), "{date}");
    }
    for date in ["2026-10-07", "2024-02-29"] {
        assert!(validate_date(date).is_ok());
    }
}
