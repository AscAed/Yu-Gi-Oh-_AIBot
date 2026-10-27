//! Independent, pure-data verification of research terminal observations.
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeSet;

fn hash(value: &Value) -> String {
    format!("{:x}", Sha256::digest(serde_json::to_vec(value).unwrap()))
}
fn bytes(value: &Value) -> Result<Vec<u8>, &'static str> {
    value
        .as_array()
        .ok_or("invalid_raw_bytes")?
        .iter()
        .map(|n| {
            n.as_u64()
                .and_then(|n| u8::try_from(n).ok())
                .ok_or("invalid_raw_bytes")
        })
        .collect()
}
fn byte_hash(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn frames(raw: &[u8]) -> Result<Vec<Vec<u8>>, &'static str> {
    let mut cursor = 0;
    let mut output = Vec::new();
    while cursor < raw.len() {
        let header = raw
            .get(cursor..cursor + 4)
            .ok_or("truncated_message_batch")?;
        let length = u32::from_le_bytes(header.try_into().unwrap()) as usize;
        cursor += 4;
        if length == 0 || length > 16 * 1024 * 1024 {
            return Err("invalid_message_length");
        }
        output.push(
            raw.get(cursor..cursor + length)
                .ok_or("truncated_message_batch")?
                .to_vec(),
        );
        cursor += length;
    }
    Ok(output)
}

fn query_fields(raw: &[u8]) -> Result<Option<(u32, u32, u32)>, &'static str> {
    if raw.is_empty() {
        return Ok(None);
    }
    let mut cursor = 0;
    let mut seen = BTreeSet::new();
    let (mut code, mut position, mut kind) = (None, None, None);
    let mut ended = false;
    while cursor < raw.len() {
        let header = raw.get(cursor..cursor + 2).ok_or("truncated_query_tlv")?;
        let length = u16::from_le_bytes(header.try_into().unwrap()) as usize;
        cursor += 2;
        let field = raw
            .get(cursor..cursor + length)
            .ok_or("truncated_query_tlv")?;
        cursor += length;
        if field.len() < 4 {
            return Err("invalid_query_tlv_size");
        }
        let flag = u32::from_le_bytes(field[..4].try_into().unwrap());
        if !seen.insert(flag) {
            return Err("duplicate_query_field");
        }
        if flag == 0x80000000 {
            if field.len() != 4 || cursor != raw.len() {
                return Err("query_tail_after_end");
            }
            ended = true;
            break;
        }
        // The pinned core emits this field even when flags 1|2|8 are requested.
        // It is not an objective input, but its wire shape must still be valid.
        if flag == 0x100000 {
            if field.len() != 5 || field[4] > 1 {
                return Err("invalid_query_public_flag");
            }
            continue;
        }
        if !matches!(flag, 1 | 2 | 8) || field.len() != 8 {
            return Err("unexpected_query_field");
        }
        let number = u32::from_le_bytes(field[4..8].try_into().unwrap());
        match flag {
            1 => code = Some(number),
            2 => position = Some(number),
            8 => kind = Some(number),
            _ => unreachable!(),
        }
    }
    if !ended {
        return Err("missing_query_end");
    }
    let values = (
        code.ok_or("missing_query_code")?,
        position.ok_or("missing_query_position")?,
        kind.ok_or("missing_query_type")?,
    );
    if values.0 == 0 || !matches!(values.1, 1 | 2 | 4 | 8) {
        return Err("query_value_out_of_range");
    }
    Ok(Some(values))
}

/// Recompute a terminal objective from request, raw processing batches and all monster queries.
/// A valid binding is structural evidence only; it does not authenticate its producer.
pub fn evaluate_terminal_run(request: &Value, run: &Value, catalog: &Value) -> Value {
    let failed = run.get("Err").is_some()
        || run.get("Ok").is_some_and(|r| {
            r.get("error") != Some(&Value::Null)
                || !matches!(
                    r["status"].as_str(),
                    Some("engine_verified" | "partial" | "decision_required")
                )
        });
    if let Some(outcome) = natural_utility(request, run) {
        return match outcome {
            Ok(utility) => {
                json!({"binding_valid":false,"snapshot_count":null,"termination":"natural_end","utility":utility,"diagnostics":[]})
            }
            Err(reason) => {
                json!({"binding_valid":false,"snapshot_count":null,"termination":if failed{"execution_failed"}else{"unknown"},"utility":null,"diagnostics":[reason]})
            }
        };
    }
    match validate(request, run, catalog) {
        Ok(count) => {
            json!({"binding_valid":true,"snapshot_count":count,"termination":"terminal_boundary_bound","utility":count,"diagnostics":[]})
        }
        Err(reason) => {
            json!({"binding_valid":false,"snapshot_count":null,"termination":if failed{"execution_failed"}else{"unknown"},"utility":null,"diagnostics":[reason]})
        }
    }
}
fn natural_utility(request: &Value, run: &Value) -> Option<Result<i32, &'static str>> {
    let result = run.get("Ok")?;
    let events = result["events"].as_array()?;
    if !events.iter().any(|e| e["opcode"] == 5 || e["raw"][0] == 5) {
        return None;
    }
    let check = || -> Result<i32, &'static str> {
        if run.as_object().map_or(true, |o| o.len() != 1)
            || result.get("error") != Some(&Value::Null)
            || !matches!(
                result["status"].as_str(),
                Some("engine_verified" | "partial")
            )
            || result.get("prompt").is_some_and(|p| !p.is_null())
        {
            return Err("execution_failed_or_pending_prompt");
        }
        if !matches!(request["protocol_version"].as_u64(), Some(1 | 2)) {
            return Err("unsupported_capture_request");
        }
        if !request["research_capture"].is_null() {
            validate_capture_request(request)?;
        }
        if request["versions"]["cdb_sha256"]
            .as_str()
            .map_or(true, |h| {
                h.len() != 64
                    || !h
                        .bytes()
                        .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
            })
            || result["versions"]["cdb_sha256"] != request["versions"]["cdb_sha256"]
            || result["terminal_observation"]["status"] == "bound"
        {
            return Err("conflicting_terminal_evidence");
        }
        let mut winner = None;
        for (i, event) in events.iter().enumerate() {
            let raw = bytes(&event["raw"])?;
            if raw.is_empty() || event["sequence"] != i + 1 || event["opcode"] != raw[0] {
                return Err("raw_terminal_evidence_invalid");
            }
            if winner.is_some() {
                return Err("game_successor_after_natural_end");
            }
            match raw[0] {
                1 => return Err("engine_retry_message"),
                5 => {
                    if raw.len() != 3 || raw[1] > 2 {
                        return Err("invalid_natural_end");
                    }
                    winner = Some(raw[1]);
                }
                40 => {
                    if raw.len() != 2 || raw[1] > 1 {
                        return Err("malformed_new_turn");
                    }
                }
                41 if raw.len() != 3 => return Err("malformed_phase"),
                _ => {}
            }
        }
        Ok(match winner.ok_or("missing_natural_end")? {
            0 => 8,
            1 => -2,
            _ => -1,
        })
    };
    Some(check())
}
fn validate_capture_request(request: &Value) -> Result<(), &'static str> {
    if request["protocol_version"] != 2
        || request.get("probe_only").is_some_and(|v| v != false)
        || request["opening_hand"].as_array().map_or(true, |h| {
            h.len() != 5
                || h.iter()
                    .any(|c| c.as_u64().map_or(true, |n| n == 0 || n > u32::MAX as u64))
        })
        || ["scenario", "interruption", "first_turn"]
            .iter()
            .any(|key| request.get(key).is_some_and(|v| !v.is_null()))
        || request["research_capture"]
            != json!({"schema_version":1,"objective":"rabbit-own-face-up-xyz-v1","boundary":"first-next-turn-process-return-v1"})
    {
        return Err("unsupported_capture_request");
    }
    Ok(())
}
fn validate(request: &Value, run: &Value, catalog: &Value) -> Result<u32, &'static str> {
    if run
        .as_object()
        .map_or(true, |o| o.len() != 1 || !o.contains_key("Ok"))
    {
        return Err("execution_failed");
    }
    let result = run.get("Ok").ok_or("execution_failed")?;
    if result.get("error") != Some(&Value::Null)
        || !matches!(
            result["status"].as_str(),
            Some("engine_verified" | "partial")
        )
        || result.get("prompt").is_some_and(|p| !p.is_null())
    {
        return Err("execution_failed_or_pending_prompt");
    }
    validate_capture_request(request)?;
    let observation = &result["terminal_observation"];
    if observation.is_null() {
        return Err("checkpoint_not_bound_to_terminal_boundary");
    }
    if observation["schema_version"] != 1
        || observation["status"] != "bound"
        || observation.get("phase") != Some(&Value::Null)
        || observation["request_sha256"] != hash(request)
        || observation["turn_index"] != 2
        || observation["turn_source"] != "raw_new_turn_events"
    {
        return Err("invalid_observation_request_binding");
    }
    if result["versions"]["cdb_sha256"] != request["versions"]["cdb_sha256"]
        || request["versions"]["cdb_sha256"]
            .as_str()
            .map_or(true, |s| s.len() != 64)
    {
        return Err("query_catalog_binding_mismatch");
    }
    let events = result["events"].as_array().ok_or("missing_event_prefix")?;
    if observation["event_prefix_sha256"] != hash(&json!(events)) {
        return Err("event_prefix_hash_mismatch");
    }
    let batches = observation["batches"]
        .as_array()
        .ok_or("missing_processing_batches")?;
    let mut sequence = 0usize;
    let (mut first_turn, mut end_phase, mut boundary) = (false, false, None);
    let mut next_player = None;
    for (index, batch) in batches.iter().enumerate() {
        let raw = bytes(&batch["raw"])?;
        if batch["index"] != index
            || batch["sha256"] != byte_hash(&raw)
            || batch["start_sequence"] != sequence + 1
            || !matches!(batch["status"].as_i64(), Some(1 | 2))
        {
            return Err("processing_batch_binding_mismatch");
        }
        let decoded = frames(&raw)?;
        if index + 1 == batches.len() && decoded.iter().any(|f| (10..=26).contains(&f[0])) {
            return Err("pending_prompt_in_terminal_batch");
        }
        for (within, frame) in decoded.iter().enumerate() {
            let event = events.get(sequence).ok_or("batch_event_prefix_mismatch")?;
            if event["sequence"] != sequence + 1
                || bytes(&event["raw"])? != *frame
                || event["opcode"] != frame[0]
            {
                return Err("batch_event_prefix_mismatch");
            }
            if boundary.is_some() {
                return Err("game_successor_after_terminal_boundary");
            }
            match frame[0] {
                1 => return Err("engine_retry_message"),
                5 => return Err("conflicting_natural_end"),
                40 => {
                    if frame.len() != 2 || frame[1] > 1 {
                        return Err("malformed_new_turn");
                    }
                    if !first_turn {
                        if frame[1] != 0 {
                            return Err("unexpected_first_turn");
                        }
                        first_turn = true;
                    } else {
                        if !end_phase || within + 1 != decoded.len() || index + 1 != batches.len() {
                            return Err("terminal_boundary_not_at_process_return");
                        }
                        boundary = Some((index, sequence + 1));
                        next_player = Some(frame[1]);
                    }
                }
                41 => {
                    if frame.len() != 3 {
                        return Err("malformed_phase");
                    }
                    if first_turn {
                        end_phase = frame[1..] == [0, 2];
                    }
                }
                _ => {}
            }
            sequence += 1;
        }
        if batch["end_sequence"] != sequence {
            return Err("processing_batch_binding_mismatch");
        }
    }
    let (batch, seq) = boundary.ok_or("terminal_boundary_not_observed")?;
    if sequence != events.len()
        || observation["boundary_batch_index"] != batch
        || observation["boundary_sequence"] != seq
        || batches[batch]["status"] != 2
        || observation["turn_player"].as_u64() != next_player.map(u64::from)
    {
        return Err("terminal_boundary_reference_mismatch");
    }
    let queries = observation["queries"]
        .as_array()
        .ok_or("missing_goal_queries")?;
    if queries.len() != 14
        || observation["capture_query_count"] != 14
        || observation["queries_sha256"] != hash(&json!(queries))
    {
        return Err("goal_queries_binding_mismatch");
    }
    let mut coordinates = BTreeSet::new();
    let mut cards = Vec::new();
    let mut count = 0;
    for query in queries {
        let player = query["controller"]
            .as_u64()
            .ok_or("missing_query_coordinate")?;
        let seq = query["sequence"]
            .as_u64()
            .ok_or("missing_query_coordinate")?;
        if player > 1
            || seq > 6
            || query["location"] != 4
            || query["flags"] != 11
            || query.get("error").map_or(true, |e| !e.is_null())
            || !coordinates.insert((player, seq))
        {
            return Err("invalid_or_duplicate_query_coordinate");
        }
        let raw = bytes(&query["raw"])?;
        if query["sha256"] != byte_hash(&raw) {
            return Err("query_raw_hash_mismatch");
        }
        if let Some((code, position, kind)) = query_fields(&raw)? {
            let frozen = catalog
                .get(code.to_string())
                .and_then(Value::as_u64)
                .filter(|v| *v <= u32::MAX as u64)
                .ok_or("unknown_frozen_card_type")?;
            // This candidate does not model dynamic type transformations. Any disagreement
            // with the frozen source remains unknown rather than silently projecting bits.
            if frozen != u64::from(kind) || kind & 1 == 0 || kind & 6 != 0 {
                return Err("query_catalog_type_conflict");
            }
            if player == 0 && position & 5 != 0 && kind & 0x800000 != 0 {
                count += 1;
            }
            cards.push(json!({"code":code,"player":player,"location":4,"sequence":seq,"position":position,"type_flags":kind}));
        }
    }
    if count > 7 {
        return Err("snapshot_count_out_of_range");
    }
    if observation["snapshot"] != json!(cards)
        || observation["snapshot_sha256"] != hash(&json!(cards))
    {
        return Err("goal_snapshot_binding_mismatch");
    }
    Ok(count)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn fixture() -> (Value, Value, Value) {
        let request = json!({"protocol_version":2,"opening_hand":[1,2,3,4,5],"research_capture":{"schema_version":1,"objective":"rabbit-own-face-up-xyz-v1","boundary":"first-next-turn-process-return-v1"},"versions":{"cdb_sha256":"a".repeat(64)}});
        let frames = [vec![40, 0], vec![41, 0, 2], vec![40, 1]];
        let raw: Vec<u8> = frames
            .iter()
            .flat_map(|f| {
                (f.len() as u32)
                    .to_le_bytes()
                    .into_iter()
                    .chain(f.iter().copied())
            })
            .collect();
        let events: Vec<_> = frames
            .iter()
            .enumerate()
            .map(|(i, f)| json!({"sequence":i+1,"opcode":f[0],"raw":f}))
            .collect();
        let mut queries = Vec::new();
        let mut card_raw = Vec::new();
        for (flag, value) in [(1u32, 42u32), (2, 1), (8, 8388609)] {
            card_raw.extend(8u16.to_le_bytes());
            card_raw.extend(flag.to_le_bytes());
            card_raw.extend(value.to_le_bytes());
        }
        card_raw.extend(4u16.to_le_bytes());
        card_raw.extend(0x80000000u32.to_le_bytes());
        for player in 0..2 {
            for sequence in 0..7 {
                let r = if player == 0 && sequence == 0 {
                    card_raw.clone()
                } else {
                    vec![]
                };
                queries.push(json!({"controller":player,"location":4,"sequence":sequence,"flags":11,"raw":r,"sha256":byte_hash(&r),"error":null}));
            }
        }
        let cards = json!([{"code":42,"player":0,"location":4,"sequence":0,"position":1,"type_flags":8388609}]);
        let observation = json!({"schema_version":1,"status":"bound","request_sha256":hash(&request),"batches":[{"index":0,"status":2,"raw":raw,"sha256":byte_hash(&raw),"start_sequence":1,"end_sequence":3}],"event_prefix_sha256":hash(&json!(events)),"boundary_batch_index":0,"boundary_sequence":3,"phase":null,"turn_index":2,"turn_player":1,"turn_source":"raw_new_turn_events","queries":queries,"capture_query_count":14,"queries_sha256":hash(&json!(queries)),"snapshot":cards,"snapshot_sha256":hash(&cards)});
        (
            request,
            json!({"Ok":{"status":"engine_verified","error":null,"prompt":null,"versions":{"cdb_sha256":"a".repeat(64)},"events":events,"terminal_observation":observation}}),
            json!({"42":8388609}),
        )
    }
    #[test]
    fn independently_decodes_goal_and_rejects_self_consistent_type_conflict() {
        let (request, run, catalog) = fixture();
        let result = evaluate_terminal_run(&request, &run, &catalog);
        assert_eq!(result["utility"], 1);
        assert_eq!(result["binding_valid"], true);
        assert!(evaluate_terminal_run(&request, &run, &json!({"42":1}))["utility"].is_null());
        assert!(evaluate_terminal_run(&request, &run, &json!({}))["utility"].is_null());
    }
    #[test]
    fn rejects_modified_binding_fields_duplicate_coordinates_and_query_failure() {
        let (request, run, catalog) = fixture();
        for field in [
            "request_sha256",
            "event_prefix_sha256",
            "snapshot_sha256",
            "queries_sha256",
        ] {
            let mut changed = run.clone();
            changed["Ok"]["terminal_observation"][field] = json!("f".repeat(64));
            assert_eq!(
                evaluate_terminal_run(&request, &changed, &catalog)["binding_valid"],
                false
            );
        }
        for field in ["error", "sequence", "flags"] {
            let mut changed = run.clone();
            let o = &mut changed["Ok"]["terminal_observation"];
            o["queries"][1][field] = match field {
                "error" => json!("failed"),
                "sequence" => json!(0),
                _ => json!(3),
            };
            o["queries_sha256"] = json!(hash(&o["queries"]));
            assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        }
    }
    #[test]
    fn rejects_boundary_followup_and_missing_phase_even_when_hashes_recomputed() {
        let (request, run, catalog) = fixture();
        for replacement in [vec![40, 0], vec![5, 0, 0]] {
            let mut changed = run.clone();
            let result = &mut changed["Ok"];
            result["events"][1]["raw"] = json!(replacement);
            result["events"][1]["opcode"] = json!(replacement[0]);
            let events = result["events"].as_array().unwrap();
            let raw: Vec<u8> = events
                .iter()
                .flat_map(|e| {
                    let f = bytes(&e["raw"]).unwrap();
                    (f.len() as u32).to_le_bytes().into_iter().chain(f)
                })
                .collect();
            result["terminal_observation"]["event_prefix_sha256"] = json!(hash(&result["events"]));
            result["terminal_observation"]["batches"][0]["raw"] = json!(raw);
            result["terminal_observation"]["batches"][0]["sha256"] = json!(byte_hash(&raw));
            assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        }
        let mut missing = run;
        missing["Ok"]
            .as_object_mut()
            .unwrap()
            .remove("terminal_observation");
        assert!(evaluate_terminal_run(&request, &missing, &catalog)["utility"].is_null());
    }
    #[test]
    fn rejects_malformed_queries_missing_fields_and_forged_status() {
        let (request, run, catalog) = fixture();
        for replacement in [
            vec![0u8],
            vec![4, 0, 0, 0, 0, 128],
            vec![8, 0, 1, 0, 0, 0, 42, 0, 0, 0, 4, 0, 0, 0, 0, 128],
        ] {
            let mut changed = run.clone();
            let o = &mut changed["Ok"]["terminal_observation"];
            o["queries"][0]["raw"] = json!(replacement);
            o["queries"][0]["sha256"] = json!(byte_hash(&replacement));
            o["queries_sha256"] = json!(hash(&o["queries"]));
            assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        }
        for field in ["phase", "request_sha256", "turn_source"] {
            let mut changed = run.clone();
            changed["Ok"]["terminal_observation"]
                .as_object_mut()
                .unwrap()
                .remove(field);
            assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        }
        let mut changed = run.clone();
        changed["Ok"]["error"] = json!("error");
        assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        changed = run.clone();
        changed["Ok"]["terminal_observation"]["batches"][0]["status"] = json!(0);
        assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
        changed = run.clone();
        changed
            .as_object_mut()
            .unwrap()
            .insert("Err".into(), json!({}));
        assert!(evaluate_terminal_run(&request, &changed, &catalog)["utility"].is_null());
    }
    #[test]
    fn natural_outcomes_do_not_require_normal_boundary_binding() {
        let (request, run, catalog) = fixture();
        for (winner, utility) in [(0, 8), (1, -2), (2, -1)] {
            let mut natural = run.clone();
            natural["Ok"]
                .as_object_mut()
                .unwrap()
                .remove("terminal_observation");
            natural["Ok"]["events"] = json!([{"sequence":1,"opcode":5,"raw":[5,winner,0]}]);
            let result = evaluate_terminal_run(&request, &natural, &catalog);
            assert_eq!(result["termination"], "natural_end");
            assert_eq!(result["utility"], utility);
            assert_eq!(result["binding_valid"], false);
            for bad in [
                json!([{"sequence":1,"opcode":5,"raw":[5,3,0]}]),
                json!([{"sequence":1,"opcode":5,"raw":[5]}]),
                json!([{"sequence":1,"opcode":5,"raw":[5,winner,0]},{"sequence":2,"opcode":40,"raw":[40,1]}]),
                json!([{"sequence":1,"opcode":5,"raw":[5,winner,0]},{"sequence":2,"opcode":5,"raw":[5,winner,0]}]),
            ] {
                natural["Ok"]["events"] = bad;
                assert!(evaluate_terminal_run(&request, &natural, &catalog)["utility"].is_null());
            }
            natural["Ok"]["events"] = json!([{"sequence":1,"opcode":5,"raw":[5,winner,0]}]);
            natural["Ok"]["error"] = json!({"code":"failure"});
            assert!(evaluate_terminal_run(&request, &natural, &catalog)["utility"].is_null());
        }
    }
    #[test]
    fn rejects_unsupported_requests_even_with_recomputed_observation_hash() {
        let (request, run, catalog) = fixture();
        for (key, value) in [
            ("probe_only", json!(true)),
            ("opening_hand", json!([1])),
            ("scenario", json!({})),
            ("interruption", json!({})),
            ("first_turn", json!({})),
            ("protocol_version", json!(3)),
        ] {
            let mut changed = request.clone();
            changed[key] = value;
            let mut evidence = run.clone();
            evidence["Ok"]["terminal_observation"]["request_sha256"] = json!(hash(&changed));
            assert_eq!(
                evaluate_terminal_run(&changed, &evidence, &catalog)["binding_valid"],
                false
            );
        }
        let mut evidence = run;
        evidence["Ok"]["events"][0] = json!({"sequence":1,"opcode":1,"raw":[1]});
        let events = evidence["Ok"]["events"].as_array().unwrap();
        let raw: Vec<u8> = events
            .iter()
            .flat_map(|e| {
                let f = bytes(&e["raw"]).unwrap();
                (f.len() as u32).to_le_bytes().into_iter().chain(f)
            })
            .collect();
        evidence["Ok"]["terminal_observation"]["event_prefix_sha256"] =
            json!(hash(&evidence["Ok"]["events"]));
        evidence["Ok"]["terminal_observation"]["batches"][0]["raw"] = json!(raw);
        evidence["Ok"]["terminal_observation"]["batches"][0]["sha256"] = json!(byte_hash(&raw));
        assert_eq!(
            evaluate_terminal_run(&request, &evidence, &catalog)["diagnostics"],
            json!(["engine_retry_message"])
        );
    }
    #[test]
    fn rejects_full_type_conflicts_despite_matching_monster_xyz_bits() {
        let (request, run, _) = fixture();
        for frozen in [8388611u32, 8388613, 8388641] {
            assert_eq!(
                evaluate_terminal_run(&request, &run, &json!({"42":frozen}))["diagnostics"],
                json!(["query_catalog_type_conflict"])
            );
        }
    }
    #[test]
    fn independently_accepts_optional_is_public_tlv_with_exact_boolean_encoding() {
        // Handwritten TLV bytes: code42,position1,type8388609,IS_PUBLIC1,END.
        let valid = [
            8, 0, 1, 0, 0, 0, 42, 0, 0, 0, 8, 0, 2, 0, 0, 0, 1, 0, 0, 0, 8, 0, 8, 0, 0, 0, 1, 0,
            128, 0, 5, 0, 0, 0, 16, 0, 1, 4, 0, 0, 0, 0, 128,
        ];
        assert_eq!(query_fields(&valid), Ok(Some((42, 1, 8388609))));
        let mut invalid = valid;
        invalid[36] = 2;
        assert!(query_fields(&invalid).is_err());
        let mut invalid = valid.to_vec();
        invalid.splice(37..37, [5, 0, 0, 0, 16, 0, 1]);
        assert!(query_fields(&invalid).is_err());
        let mut invalid = valid;
        invalid[30] = 6;
        assert!(query_fields(&invalid).is_err());
    }
    #[test]
    fn independently_checks_known_core_query_and_rejects_missing_or_truncated_end() {
        let raw = [
            8, 0, 1, 0, 0, 0, 181, 240, 1, 5, 8, 0, 2, 0, 0, 0, 1, 0, 0, 0, 8, 0, 8, 0, 0, 0, 33,
            0, 128, 0, 5, 0, 0, 0, 16, 0, 1, 4, 0, 0, 0, 0, 128,
        ];
        assert_eq!(query_fields(&raw), Ok(Some((84013237, 1, 8388641))));
        assert!(query_fields(&raw[..37]).is_err());
        assert!(query_fields(&raw[..42]).is_err());
        let mut trailing = raw.to_vec();
        trailing.push(0);
        assert!(query_fields(&trailing).is_err());
        let mut not_public = raw;
        not_public[36] = 0;
        assert_eq!(query_fields(&not_public), Ok(Some((84013237, 1, 8388641))));
        let mut absent = raw[..30].to_vec();
        absent.extend_from_slice(&raw[37..]);
        assert_eq!(query_fields(&absent), Ok(Some((84013237, 1, 8388641))));
    }
    #[test]
    fn failed_result_has_no_count_utility_or_successful_terminal_classification() {
        let (request, mut run, catalog) = fixture();
        run["Ok"]["status"] = json!("failed");
        run["Ok"]["error"] = json!({"code":"query_failed"});
        let result = evaluate_terminal_run(&request, &run, &catalog);
        assert_eq!(result["termination"], "execution_failed");
        assert!(result["utility"].is_null());
        assert!(result["snapshot_count"].is_null());
        assert_eq!(result["binding_valid"], false);
    }
}
