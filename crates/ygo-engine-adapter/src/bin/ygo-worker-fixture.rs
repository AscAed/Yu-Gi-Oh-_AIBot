//! Fault-injection helper for subprocess tests; never used for duel verification.
fn main() {
    let name = std::env::current_exe()
        .unwrap()
        .file_stem()
        .unwrap()
        .to_string_lossy()
        .into_owned();
    if name.contains("hang") {
        std::thread::sleep(std::time::Duration::from_secs(60));
    } else if name.contains("crash") {
        std::process::exit(7);
    } else if name.contains("noise") {
        use std::io::Write;
        std::io::stderr()
            .write_all(&vec![b'x'; 512 * 1024])
            .unwrap();
        println!("{{\"protocol_version\":99}}");
    } else if name.contains("protocol") {
        let mut result = ygo_engine_adapter::DuelResult::failure(
            ygo_engine_adapter::WorkerError::new("fixture", "test", ""),
        );
        result.protocol_version = 99;
        println!("{}", serde_json::to_string(&result).unwrap());
    } else {
        println!("not-json");
    }
}
