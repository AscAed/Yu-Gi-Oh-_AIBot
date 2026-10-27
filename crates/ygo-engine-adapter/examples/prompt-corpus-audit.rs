//! stdin JSON -> stdout JSON. Never starts an engine or opens a call ledger.
use std::io::{Read, Write};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    std::io::stdin().read_to_string(&mut input)?;
    let report = ygo_engine_adapter::audit_prompt_corpus(serde_json::from_str(&input)?)?;
    serde_json::to_writer(std::io::stdout().lock(), &report)?;
    std::io::stdout().write_all(b"\n")?;
    if report["successful"] != true {
        std::process::exit(1);
    }
    Ok(())
}
