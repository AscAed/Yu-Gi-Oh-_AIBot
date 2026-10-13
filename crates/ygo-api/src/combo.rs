use serde::{Deserialize, Serialize};
use std::path::Path;
use ygo_domain::{validate_catalog_deck, validate_hand, CardId, Deck};
use ygo_engine_adapter::*;
use ygo_search::combo::*;
use ygo_storage::SnapshotStore;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ComboAnalyzeRequest {
    pub deck: Deck,
    pub opening_hand: Vec<CardId>,
    pub seed: u64,
    #[serde(default = "rules")]
    pub rules: String,
    #[serde(default)]
    pub catalog_id: Option<String>,
    #[serde(default = "latest")]
    pub banlist_id: String,
    pub as_of: String,
    #[serde(default)]
    pub search: SearchBudget,
}
fn rules() -> String {
    "ocg-mr5".into()
}
fn latest() -> String {
    "latest-ocg".into()
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AnalysisReport {
    pub schema_version: u16,
    pub request: ComboAnalyzeRequest,
    pub runtime_request: RunDuelRequest,
    pub search: SearchReport,
    pub card_names: std::collections::BTreeMap<u32, String>,
}
pub fn analyze(
    request: ComboAnalyzeRequest,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    active_catalog: &str,
    weights: &ScoringConfig,
) -> Result<AnalysisReport, String> {
    if request.rules != "ocg-mr5" {
        return Err("only ocg-mr5 is supported".into());
    }
    request.search.validate()?;
    ygo_storage::validate_date(&request.as_of)?;
    let catalog = store.catalog(request.catalog_id.as_deref().unwrap_or(active_catalog))?;
    let banlist = if request.banlist_id == "latest-ocg" {
        store.latest_ocg(&request.as_of)?
    } else {
        store.banlist(&request.banlist_id)?
    };
    if banlist
        .effective_date
        .as_deref()
        .map_or(true, |d| d > request.as_of.as_str())
    {
        return Err("banlist not effective for analysis date".into());
    }
    let legal = validate_catalog_deck(&request.deck, &banlist.data, &catalog.data);
    if !legal.is_legal() {
        return Err(serde_json::to_string(&legal).map_err(|e| e.to_string())?);
    }
    validate_hand(&request.deck, &request.opening_hand)?;
    let mut runtime = runtime_request(
        engine.clone(),
        request.deck.clone(),
        request.opening_hand.clone(),
        request.seed,
    )
    .map_err(|e| e.message)?;
    if catalog.source_sha256 != runtime.versions.cdb_sha256 {
        return Err("catalog snapshot does not match engine CDB".into());
    }
    runtime.versions.catalog = catalog.id.clone();
    runtime.versions.banlist = banlist.id.clone();
    let adapter = ProcessEngineAdapter::new(engine);
    let report = search(&adapter, &runtime, &request.search, weights)?;
    let card_names = catalog
        .data
        .values()
        .filter(|c| {
            request
                .deck
                .main
                .iter()
                .chain(&request.deck.extra)
                .chain(&request.deck.side)
                .any(|id| *id == c.id)
                || report
                    .lines
                    .iter()
                    .any(|l| l.result.checkpoint.cards.iter().any(|s| s.code == c.id.0))
        })
        .map(|c| (c.id.0, c.name.clone()))
        .collect();
    let mut resolved = request;
    resolved.catalog_id = Some(catalog.id);
    resolved.banlist_id = banlist.id;
    Ok(AnalysisReport {
        schema_version: 2,
        request: resolved,
        runtime_request: runtime,
        search: report,
        card_names,
    })
}
pub fn replay(
    report: &AnalysisReport,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
) -> Result<serde_json::Value, String> {
    validate_report_contract(report)?;
    if report.schema_version != 2 {
        return Err("report schema version mismatch".into());
    }
    let catalog = store.catalog(&report.runtime_request.versions.catalog)?;
    let banlist = store.banlist(&report.runtime_request.versions.banlist)?;
    if banlist
        .effective_date
        .as_deref()
        .map_or(true, |date| date > report.request.as_of.as_str())
    {
        return Err("report banlist not effective".into());
    }
    if catalog.source_sha256 != report.runtime_request.versions.cdb_sha256
        || !validate_catalog_deck(&report.runtime_request.deck, &banlist.data, &catalog.data)
            .is_legal()
    {
        return Err("report deck/catalog mismatch".into());
    }
    let adapter = ProcessEngineAdapter::new(engine.clone());
    let mut results = vec![];
    for line in &report.search.lines {
        let mut request = report.runtime_request.clone();
        request.engine = engine.clone();
        request.decisions = line.decisions.clone();
        let result = adapter
            .run(&request)
            .map_err(|e| format!("{}: {}", e.code, e.message))?;
        if result.status != line.result.status
            || result.checkpoint != line.result.checkpoint
            || result.events != line.result.events
            || result.loaded_scripts != line.result.loaded_scripts
            || result.resolved_decisions != line.decisions
            || result.steps != line.result.steps
        {
            return Err(format!("replay mismatch for {}", line.id));
        }
        let score = evaluate(
            &result.checkpoint,
            line.decisions.len(),
            &report.search.scoring,
        );
        if score != line.evaluation {
            return Err("evaluation version/content mismatch".into());
        }
        results.push(
            serde_json::json!({"id":line.id,"replay_verified":true,"verification":result.status}),
        );
    }
    if results.is_empty() {
        return Err("report contains no lines to replay".into());
    }
    Ok(serde_json::json!({"schema_version":2,"lines":results}))
}
/// Check internal provenance before reading assets or spawning a replay worker.
pub fn validate_report_contract(report: &AnalysisReport) -> Result<(), String> {
    let r = &report.runtime_request;
    let q = &report.request;
    ygo_storage::validate_date(&q.as_of)?;
    validate_hand(&r.deck, &r.opening_hand)?;
    if report.schema_version != 2
        || r.protocol_version != 2
        || r.probe_only
        || !r.decisions.is_empty()
        || q.deck != r.deck
        || q.opening_hand != r.opening_hand
        || q.seed != r.seed
        || q.rules != r.versions.rules
        || q.rules != "ocg-mr5"
        || q.catalog_id.as_deref() != Some(r.versions.catalog.as_str())
        || q.banlist_id != r.versions.banlist
    {
        return Err("report request/runtime contract mismatch".into());
    }
    for line in &report.search.lines {
        let mut prefix = r.clone();
        prefix.decisions = line.decisions.clone();
        if !line.replay_verified
            || !matches!(
                line.result.status,
                DuelStatus::EngineVerified | DuelStatus::Partial
            )
            || line.result.prompt.is_some()
            || line.result.error.is_some()
            || line.result.versions != r.versions
            || line.result.resolved_decisions != line.decisions
            || line.id != prefix_key(&prefix)
            || line.evaluation.decisions != line.decisions.len()
        {
            return Err("report line verification contract mismatch".into());
        }
    }
    Ok(())
}
pub fn read_report(path: &Path) -> Result<AnalysisReport, String> {
    serde_json::from_slice(&std::fs::read(path).map_err(|e| e.to_string())?)
        .map_err(|e| e.to_string())
}
