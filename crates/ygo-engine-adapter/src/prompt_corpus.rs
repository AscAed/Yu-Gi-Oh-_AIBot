//! Pure protocol comparisons. This module never opens a worker or call journal.
use crate::{audit_prompt_responses, parse_prompt};
use serde::Deserialize;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Corpus {
    schema_version: u8,
    sources: Vec<Source>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    role: String,
    sha256: String,
    request_sha256: Option<String>,
    origin: String,
    frames: Vec<Frame>,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Frame {
    sequence: u64,
    raw: Vec<u8>,
    historical: Option<Vec<Vec<u8>>>,
    #[serde(default)]
    historical_error: bool,
}
fn comparison(raw: &[u8], actual: Option<Result<Vec<Vec<u8>>, String>>) -> Value {
    match actual {
        None => {
            json!({"status":"unavailable","audit":null,"diagnostic":"historical_response_set_not_recorded"})
        }
        Some(actual) => match actual.and_then(|actual| audit_prompt_responses(raw, &actual)) {
            Ok(audit) => {
                json!({"status":if audit.matches {"matched"} else {"mismatch"},"audit":audit,"diagnostic":null})
            }
            Err(error) => json!({"status":"error","audit":null,"diagnostic":error}),
        },
    }
}
/// Audit supplied frame bytes without executing any engine operation.
/// Caller binds these bytes to source files and the actual auditor build.
pub fn audit_prompt_corpus(input: Value) -> Result<Value, String> {
    let corpus: Corpus = serde_json::from_value(input).map_err(|_| "invalid corpus envelope")?;
    if corpus.schema_version != 1 || corpus.sources.is_empty() {
        return Err("nonempty corpus v1 required".into());
    }
    let mut sources = Vec::new();
    let mut roles = std::collections::BTreeSet::new();
    let (mut total, mut current_mismatches, mut historical_mismatches, mut errors, mut unavailable) =
        (0usize, 0usize, 0usize, 0usize, 0usize);
    for source in corpus.sources {
        let hash_ok = |s: &str| {
            s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        };
        if source.role.is_empty()
            || !source
                .role
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
            || !roles.insert(source.role.clone())
            || !hash_ok(&source.sha256)
            || source.request_sha256.as_ref().is_some_and(|v| !hash_ok(v))
            || !matches!(
                source.origin.as_str(),
                "historical_report" | "synthetic_fixture"
            )
            || source.frames.is_empty()
        {
            return Err("invalid corpus source binding".into());
        }
        let mut frames = Vec::new();
        for frame in source.frames {
            let actual = parse_prompt(frame.sequence, &frame.raw)
                .and_then(|p| p.ok_or("unsupported production opcode".into()))
                .map(|p| p.actions.into_iter().map(|a| a.bytes).collect());
            let current = comparison(&frame.raw, Some(actual));
            let mut historical = comparison(&frame.raw, frame.historical.map(Ok));
            if frame.historical_error && historical["status"] == "unavailable" {
                historical["diagnostic"] = json!("historical_parser_failed");
            }
            total += 1;
            current_mismatches += usize::from(current["status"] == "mismatch");
            historical_mismatches += usize::from(historical["status"] == "mismatch");
            errors += usize::from(current["status"] == "error")
                + usize::from(historical["status"] == "error");
            unavailable += usize::from(historical["status"] == "unavailable");
            frames.push(json!({"sequence":frame.sequence,"opcode":frame.raw.first(),"raw_sha256":format!("{:x}",Sha256::digest(&frame.raw)),"current":current,"historical":historical}));
        }
        sources.push(json!({"role":source.role,"sha256":source.sha256,"request_sha256":source.request_sha256,"origin":source.origin,"frames":frames}));
    }
    Ok(
        json!({"sources":sources,"summary":{"frames":total,"current_mismatches":current_mismatches,"historical_mismatches":historical_mismatches,"errors":errors,"historical_unavailable":unavailable},"successful":current_mismatches+historical_mismatches+errors+unavailable==0}),
    )
}
