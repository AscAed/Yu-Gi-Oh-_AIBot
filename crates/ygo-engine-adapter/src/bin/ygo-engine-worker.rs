fn main() {
    if let Err(error) = ygo_engine_adapter::worker_main() {
        eprintln!("worker protocol failure: {error}");
        std::process::exit(1);
    }
}
