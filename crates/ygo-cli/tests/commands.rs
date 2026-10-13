use ygo_cli::Command;

#[test]
fn parses_engine_doctor_command() {
    assert_eq!(
        Command::parse(["engine", "doctor"]),
        Some(Command::EngineDoctor)
    );
}
#[test]
fn parses_knowledge_explanation_and_causal_planning_commands() {
    for (family, action) in [
        ("knowledge", "validate"),
        ("card", "explain"),
        ("combo", "plan"),
        ("combo", "plan-replay"),
    ] {
        assert!(
            ygo_cli::Command::parse([family, action]).is_some(),
            "{family} {action}"
        );
    }
}
