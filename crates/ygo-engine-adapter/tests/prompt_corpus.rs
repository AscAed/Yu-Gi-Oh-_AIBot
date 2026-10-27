use serde_json::json;
use ygo_engine_adapter::audit_prompt_corpus;

fn source(raw: Vec<u8>, historical: serde_json::Value) -> serde_json::Value {
    json!({"schema_version":1,"sources":[{"role":"synthetic","sha256":"a".repeat(64),"request_sha256":null,"origin":"synthetic_fixture","frames":[{"sequence":7,"raw":raw,"historical":historical}]}]})
}
#[test]
fn corpus_distinguishes_historical_omission_from_repaired_parser() {
    let mut raw = vec![11, 0];
    raw.extend([0; 24]);
    raw.extend([1, 1, 1]);
    let report = audit_prompt_corpus(source(raw, json!([[7, 0, 0, 0]]))).unwrap();
    let frame = &report["sources"][0]["frames"][0];
    assert_eq!(frame["current"]["status"], "matched");
    assert_eq!(frame["historical"]["status"], "mismatch");
    assert_eq!(
        frame["historical"]["audit"]["missing"],
        json!([[6, 0, 0, 0], [8, 0, 0, 0]])
    );
    assert_eq!(report["successful"], false);
}
#[test]
fn corpus_retains_unknown_truncated_and_unavailable_diagnostics() {
    for raw in [vec![200, 0], vec![19, 0, 1]] {
        let report = audit_prompt_corpus(source(raw, json!(null))).unwrap();
        assert_eq!(
            report["sources"][0]["frames"][0]["current"]["status"],
            "error"
        );
        assert_eq!(
            report["sources"][0]["frames"][0]["historical"]["status"],
            "unavailable"
        );
        assert_eq!(report["successful"], false);
    }
}
#[test]
fn corpus_preserves_duplicate_occurrences_and_detects_tampering() {
    let raw = vec![19, 0, 1, 0, 0, 0, 5];
    for historical in [
        json!([[1, 0, 0, 0]]),
        json!([[1, 0, 0, 0], [4, 0, 0, 0], [2, 0, 0, 0]]),
    ] {
        let mut input = source(raw.clone(), historical);
        let frame = input["sources"][0]["frames"][0].clone();
        input["sources"][0]["frames"]
            .as_array_mut()
            .unwrap()
            .push(frame);
        let report = audit_prompt_corpus(input).unwrap();
        assert_eq!(report["summary"]["frames"], 2);
        assert_eq!(report["summary"]["historical_mismatches"], 2);
        assert_eq!(report["summary"]["current_mismatches"], 0);
    }
    assert!(audit_prompt_corpus(json!({"schema_version":1,"sources":[]})).is_err());
}
#[test]
fn historical_forced_chain_pass_is_rejected() {
    let mut raw = vec![16, 0, 0, 1];
    raw.extend([0; 12]);
    let report = audit_prompt_corpus(source(raw, json!([[255, 255, 255, 255]]))).unwrap();
    assert_eq!(
        report["sources"][0]["frames"][0]["historical"]["status"],
        "mismatch"
    );
    assert_eq!(
        report["sources"][0]["frames"][0]["historical"]["audit"]["unexpected"],
        json!([[255, 255, 255, 255]])
    );
    assert_eq!(report["successful"], false);
}
