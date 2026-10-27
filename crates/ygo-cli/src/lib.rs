#[derive(Clone, Debug, Eq, PartialEq)]
pub enum Command {
    CatalogSync,
    CatalogImport,
    CatalogStatus,
    BanlistImport,
    BanlistStatus,
    DeckValidate,
    DeckOptimize,
    ComboAnalyze,
    ComboReplay,
    EngineDoctor,
    EngineIdentity,
    EngineSmoke,
    EngineWorker,
    EvalRun,
    KnowledgeValidate,
    KnowledgeVerify,
    CardExplain,
    ComboPlan,
    ComboPlanReplay,
}

impl Command {
    pub fn parse<I, S>(args: I) -> Option<Self>
    where
        I: IntoIterator<Item = S>,
        S: AsRef<str>,
    {
        let args: Vec<String> = args
            .into_iter()
            .map(|arg| arg.as_ref().to_string())
            .collect();
        match &args[..args.len().min(2)] {
            [a, b] if a == "knowledge" && b == "verify" => Some(Self::KnowledgeVerify),
            [a, b] if a == "knowledge" && b == "validate" => Some(Self::KnowledgeValidate),
            [a, b] if a == "card" && b == "explain" => Some(Self::CardExplain),
            [a, b] if a == "combo" && b == "plan" => Some(Self::ComboPlan),
            [a, b] if a == "combo" && b == "plan-replay" => Some(Self::ComboPlanReplay),
            [a, b] if a == "catalog" && b == "import" => Some(Self::CatalogImport),
            [a, b] if a == "banlist" && b == "import" => Some(Self::BanlistImport),
            [a, b] if a == "banlist" && b == "status" => Some(Self::BanlistStatus),
            [a, b] if a == "combo" && b == "replay" => Some(Self::ComboReplay),
            [a, b] if a == "engine" && b == "smoke" => Some(Self::EngineSmoke),
            [a, b] if a == "catalog" && b == "sync" => Some(Self::CatalogSync),
            [a, b] if a == "catalog" && b == "status" => Some(Self::CatalogStatus),
            [a, b] if a == "deck" && b == "validate" => Some(Self::DeckValidate),
            [a, b] if a == "deck" && b == "optimize" => Some(Self::DeckOptimize),
            [a, b] if a == "combo" && b == "analyze" => Some(Self::ComboAnalyze),
            [a, b] if a == "engine" && b == "doctor" => Some(Self::EngineDoctor),
            [a, b] if a == "engine" && b == "identity" => Some(Self::EngineIdentity),
            [a, b] if a == "engine" && b == "worker" => Some(Self::EngineWorker),
            [a, b] if a == "eval" && b == "run" => Some(Self::EvalRun),
            _ => None,
        }
    }
}
