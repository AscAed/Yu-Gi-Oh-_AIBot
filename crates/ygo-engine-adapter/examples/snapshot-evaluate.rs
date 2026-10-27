#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    fn result(cards: Value, events: Value) -> Value {
        json!({"status":"engine_verified","error":null,"checkpoint":{"cards":cards},"events":events})
    }
    fn card(player: u8, position: u8, kind: u32, sequence: u8) -> Value {
        json!({"code":1,"player":player,"location":4,"sequence":sequence,"position":position,"type_flags":kind})
    }
    fn evaluate(value: Value) -> Value {
        evaluate_run(&json!({"Ok":value}), &json!({"1":8388609}), 0)
    }
    #[test]
    fn counts_only_own_face_up_xyz_and_rejects_conflicts() {
        assert_eq!(
            evaluate(result(
                json!([
                    card(0, 4, 8388609, 0),
                    card(1, 1, 8388609, 0),
                    card(0, 2, 8388609, 1)
                ]),
                json!([])
            ))["snapshot_count"],
            1
        );
        assert!(evaluate(result(json!([card(0, 1, 1, 0)]), json!([])))["snapshot_count"].is_null());
        assert!(evaluate(result(
            json!([card(0, 1, 8388609, 0), card(0, 1, 8388609, 0)]),
            json!([])
        ))["snapshot_count"]
            .is_null());
    }
    #[test]
    fn unknown_missing_overflow_and_material_records_remain_conservative() {
        let seven: Vec<_> = (0..7).map(|i| card(0, 1, 8388609, i)).collect();
        assert_eq!(
            evaluate(result(json!(seven), json!([])))["snapshot_count"],
            7
        );
        let eight: Vec<_> = (0..8).map(|i| card(0, 1, 8388609, i)).collect();
        assert!(evaluate(result(json!(eight), json!([])))["snapshot_count"].is_null());
        let mut unknown = card(0, 1, 8388609, 0);
        unknown["code"] = json!(999);
        assert!(evaluate(result(json!([unknown]), json!([])))["snapshot_count"].is_null());
        let mut missing = card(0, 1, 8388609, 0);
        missing.as_object_mut().unwrap().remove("type_flags");
        assert!(evaluate(result(json!([missing]), json!([])))["snapshot_count"].is_null());
        let mut monster = card(0, 1, 8388609, 0);
        monster["overlay"] = json!([1, 1, 1]);
        assert_eq!(
            evaluate(result(json!([monster]), json!([])))["snapshot_count"],
            1
        );
        assert_eq!(
            evaluate_run(
                &json!({"Ok":result(json!([card(0,1,1,0)]),json!([]))}),
                &json!({"1":1}),
                0
            )["snapshot_count"],
            0
        );
        assert!(
            evaluate_run(&json!({"Err":{"message":"private"}}), &json!({}), 0)["utility"].is_null()
        );
        assert!(evaluate(result(
            json!([]),
            json!([{"sequence":1,"opcode":5,"raw":[5,0,0]},{"sequence":2,"opcode":5,"raw":[5,0,0]}])
        ))["utility"]
            .is_null());
        let phase = evaluate(result(
            json!([]),
            json!([{"sequence":1,"opcode":41,"raw":[41,0,2]}]),
        ));
        assert_eq!(phase["termination"], "not_terminated");
        assert!(phase["utility"].is_null());
        assert!(evaluate(result(
            json!([]),
            json!([{"sequence":1,"opcode":5,"raw":[5,0,0]},{"sequence":2,"opcode":5,"raw":[5,1,0]}])
        ))["utility"]
            .is_null());
    }
    #[test]
    fn boundary_is_observed_but_checkpoint_is_unbound() {
        let value = evaluate(result(
            json!([]),
            json!([{"sequence":1,"opcode":40,"raw":[40,0]},{"sequence":2,"opcode":41,"raw":[41,0,2]},{"sequence":3,"opcode":40,"raw":[40,1]}]),
        ));
        assert_eq!(value["termination"], "next_turn_boundary_observed");
        assert!(value["utility"].is_null());
    }
    #[test]
    fn natural_end_requires_valid_unique_final_message_and_success() {
        for (winner, utility) in [(0, 8), (1, -2), (2, -1)] {
            assert_eq!(
                evaluate(result(
                    json!([]),
                    json!([{"sequence":1,"opcode":5,"raw":[5,winner,0]}])
                ))["utility"],
                utility
            );
        }
        for raw in [json!([5]), json!([5, 3, 0])] {
            assert!(evaluate(result(
                json!([]),
                json!([{"sequence":1,"opcode":5,"raw":raw}])
            ))["utility"]
                .is_null());
        }
        let mut successor = result(json!([]), json!([{"sequence":1,"opcode":5,"raw":[5,0,0]}]));
        successor["status"] = json!("decision_required");
        assert!(evaluate(successor.clone())["utility"].is_null());
        successor["prompt"] = json!({"id":2,"actions":[{}]});
        assert!(evaluate(successor)["utility"].is_null());
        let mut failed = result(json!([]), json!([{"sequence":1,"opcode":5,"raw":[5,0,0]}]));
        failed["status"] = json!("failed");
        assert!(evaluate(failed)["utility"].is_null());
        assert!(evaluate(result(
            json!([]),
            json!([{"sequence":1,"opcode":5,"raw":[5,0,0]},{"sequence":2,"opcode":40,"raw":[40,1]}])
        ))["utility"]
            .is_null());
    }
}
// Pure snapshot objective and raw terminal diagnostics. Never creates an adapter.
use serde_json::{json, Value};
use std::collections::BTreeSet;
use std::io::{Read, Write};
fn number(v: &Value, k: &str) -> Option<u64> {
    v.get(k)?.as_u64()
}
fn evaluate_run(run: &Value, catalog: &Value, own: u64) -> Value {
    let mut diagnostics = Vec::new();
    let Some(result) = run.get("Ok").filter(|v| v.is_object()) else {
        return json!({"snapshot_count":null,"termination":"execution_failed","utility":null,"diagnostics":["execution_failed"]});
    };
    let failed = result.get("error").is_some_and(|v| !v.is_null())
        || !matches!(
            result["status"].as_str(),
            Some("engine_verified" | "decision_required" | "partial")
        );
    let mut count = 0;
    let mut valid = true;
    let mut coords = BTreeSet::new();
    if let Some(cards) = result["checkpoint"]["cards"].as_array() {
        for c in cards {
            let (
                Some(player),
                Some(location),
                Some(sequence),
                Some(position),
                Some(kind),
                Some(code),
            ) = (
                number(c, "player"),
                number(c, "location"),
                number(c, "sequence"),
                number(c, "position"),
                number(c, "type_flags"),
                number(c, "code"),
            )
            else {
                valid = false;
                diagnostics.push("missing_card_query_metadata");
                continue;
            };
            if player > 1
                || !matches!(location, 1 | 2 | 4 | 8 | 16 | 32 | 64 | 128)
                || kind > u32::MAX as u64
                || code > u32::MAX as u64
            {
                valid = false;
                diagnostics.push("card_query_out_of_range");
                continue;
            }
            if !coords.insert((player, location, sequence)) {
                valid = false;
                diagnostics.push("duplicate_card_coordinate");
            }
            if location != 4 {
                continue;
            }
            if sequence > 6 || !matches!(position, 1 | 2 | 4 | 8) {
                valid = false;
                diagnostics.push("monster_query_out_of_range");
                continue;
            }
            let Some(frozen) = catalog.get(code.to_string()).and_then(Value::as_u64) else {
                valid = false;
                diagnostics.push("unknown_card_type");
                continue;
            };
            // Both sources must agree on objective-relevant classification; dynamic extra flags may differ.
            if frozen & 0x800001 != kind & 0x800001 || kind & 1 == 0 {
                valid = false;
                diagnostics.push("query_catalog_type_conflict");
                continue;
            }
            if player == own && position & 5 != 0 && kind & 0x800000 != 0 {
                count += 1;
            }
        }
    } else {
        valid = false;
        diagnostics.push("missing_checkpoint_cards");
    }
    if count > 7 {
        valid = false;
        diagnostics.push("snapshot_count_out_of_range");
    }
    let mut winner = None;
    let mut terminal_bad = false;
    let mut boundary = false;
    let mut saw_first = false;
    let mut last_sequence = None;
    if let Some(events) = result["events"].as_array() {
        for event in events {
            let Some(raw) = event["raw"].as_array().and_then(|a| {
                a.iter()
                    .map(|n| n.as_u64().filter(|n| *n <= 255))
                    .collect::<Option<Vec<_>>>()
            }) else {
                terminal_bad = true;
                continue;
            };
            let seq = number(event, "sequence");
            if seq.is_none()
                || last_sequence.is_some_and(|last| seq <= Some(last))
                || raw.is_empty()
                || event["opcode"].as_u64() != raw.first().copied()
            {
                terminal_bad = true;
            }
            last_sequence = seq;
            if winner.is_some() {
                terminal_bad = true;
                diagnostics.push("game_successor_after_natural_end");
            }
            match raw.first() {
                Some(5) => {
                    if raw.len() != 3 || raw[1] > 2 || winner.is_some() {
                        terminal_bad = true;
                        diagnostics.push("invalid_or_conflicting_natural_end");
                    } else {
                        winner = Some(raw[1]);
                    }
                }
                Some(40) => {
                    if raw.len() != 2 || raw[1] > 1 {
                        terminal_bad = true;
                    } else if saw_first && raw[1] != own {
                        boundary = true;
                    } else if raw[1] == own {
                        saw_first = true;
                    }
                }
                _ => {}
            }
        }
    } else {
        terminal_bad = true;
        diagnostics.push("missing_raw_events");
    }
    if winner.is_some() && result["status"] == "decision_required" {
        terminal_bad = true;
        diagnostics.push("unsupported_terminal_status");
    }
    if winner.is_some() && result.get("prompt").is_some_and(|p| !p.is_null()) {
        terminal_bad = true;
        diagnostics.push("game_successor_after_natural_end");
    }
    if failed {
        diagnostics.push("execution_failed");
    }
    if terminal_bad {
        diagnostics.push("raw_terminal_evidence_invalid");
    }
    let utility = if !failed && !terminal_bad {
        winner.map(|w| {
            if w == 2 {
                -1
            } else if w == own {
                8
            } else {
                -2
            }
        })
    } else {
        None
    };
    let termination = if failed {
        "execution_failed"
    } else if terminal_bad {
        "unknown"
    } else if winner.is_some() {
        "natural_end"
    } else if boundary {
        "next_turn_boundary_observed"
    } else {
        "not_terminated"
    };
    if winner.is_none() {
        diagnostics.push("checkpoint_not_bound_to_terminal_boundary");
    }
    diagnostics.sort();
    diagnostics.dedup();
    json!({"snapshot_count":if valid{Some(count)}else{None},"termination":termination,"utility":utility,"diagnostics":diagnostics})
}
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let input: Value = serde_json::from_str(&input)?;
    if input["schema_version"] != 1 || input["own_player"] != 0 {
        return Err("unsupported objective envelope".into());
    }
    let runs = input["runs"].as_array().ok_or("runs required")?;
    let output: Vec<_> = runs
        .iter()
        .map(|r| evaluate_run(r, &input["catalog_types"], 0))
        .collect();
    serde_json::to_writer(std::io::stdout().lock(), &json!({"evaluations":output}))?;
    std::io::stdout().write_all(b"\n")?;
    Ok(())
}
