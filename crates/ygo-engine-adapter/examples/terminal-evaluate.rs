//! Pure data terminal binding checker; does not instantiate an adapter.
use serde_json::{json, Value};
use std::io::{Read, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let value: Value = serde_json::from_str(&input)?;
    if value["schema_version"] != 2 || value["own_player"] != 0 {
        return Err("unsupported terminal objective envelope".into());
    }
    let runs = value["runs"].as_array().ok_or("runs required")?;
    let evaluations: Vec<_> = runs
        .iter()
        .map(|run| {
            ygo_engine_adapter::evaluate_terminal_run(
                &value["request"],
                run,
                &value["catalog_types"],
            )
        })
        .collect();
    serde_json::to_writer(
        std::io::stdout().lock(),
        &json!({"evaluations":evaluations}),
    )?;
    std::io::stdout().write_all(b"\n")?;
    Ok(())
}
