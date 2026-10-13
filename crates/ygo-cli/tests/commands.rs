use ygo_cli::Command;

#[test]
fn parses_engine_doctor_command() {
    assert_eq!(
        Command::parse(["engine", "doctor"]),
        Some(Command::EngineDoctor)
    );
}
