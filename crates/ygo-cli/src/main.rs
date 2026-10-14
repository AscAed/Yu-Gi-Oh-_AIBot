use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};
use ygo_api::combo::*;
use ygo_cli::Command;
use ygo_engine_adapter::*;
use ygo_search::combo::ScoringConfig;
use ygo_storage::SnapshotStore;
fn engine() -> Result<ProcessEngineConfig, String> {
    let path = std::env::var_os("YGO_ENGINE_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|| "configs/engine.toml".into());
    let text = fs::read_to_string(&path).map_err(|e| {
        format!(
            "{}: {e}; copy configs/engine.example.toml first",
            path.display()
        )
    })?;
    ProcessEngineConfig::from_toml(&text).map_err(|e| format!("config v2 required: {e}"))
}
fn json(v: &serde_json::Value) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string_pretty(v).map_err(|e| e.to_string())?
    );
    Ok(())
}
fn scoring(opts: &BTreeMap<String, String>) -> Result<ScoringConfig, String> {
    let path = opts
        .get("--scoring")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("YGO_SCORING_CONFIG").map(PathBuf::from));
    if let Some(path) = path {
        ScoringConfig::from_toml(
            &fs::read_to_string(&path).map_err(|e| format!("{}: {e}", path.display()))?,
        )
    } else {
        Ok(ScoringConfig::default())
    }
}
fn knowledge(opts: &BTreeMap<String, String>) -> Result<ygo_knowledge::KnowledgePack, String> {
    let path = opts
        .get("--knowledge")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("YGO_KNOWLEDGE_CONFIG").map(PathBuf::from))
        .unwrap_or_else(|| "knowledge/phantom-v1.json".into());
    ygo_knowledge::KnowledgePack::read(&path)
}
fn knowledge_v2(opts: &BTreeMap<String, String>) -> Result<ygo_knowledge::KnowledgePack, String> {
    let path = opts
        .get("--knowledge")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("YGO_KNOWLEDGE_V2_CONFIG").map(PathBuf::from))
        .unwrap_or_else(|| "knowledge/phantom-v2.json".into());
    ygo_knowledge::KnowledgePack::read(&path)
}
fn output(opts: &BTreeMap<String, String>, value: &serde_json::Value) -> Result<(), String> {
    if let Some(path) = opts.get("--output") {
        fs::write(
            path,
            serde_json::to_vec_pretty(value).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())
    } else {
        json(value)
    }
}
fn options(args: &[String]) -> Result<BTreeMap<String, String>, String> {
    let mut opts = BTreeMap::new();
    for pair in args.chunks(2) {
        if pair.len() != 2 || !pair[0].starts_with("--") {
            return Err("flags require --name value".into());
        }
        if opts.insert(pair[0].clone(), pair[1].clone()).is_some() {
            return Err(format!("duplicate flag {}", pair[0]));
        }
    }
    Ok(opts)
}
fn need<'a>(opts: &'a BTreeMap<String, String>, key: &str) -> Result<&'a str, String> {
    opts.get(key)
        .map(String::as_str)
        .ok_or_else(|| format!("missing {key}"))
}
fn active(path: &Path) -> Result<serde_json::Value, String> {
    let value: serde_json::Value = serde_json::from_slice(
        &fs::read(path).map_err(|e| format!("import catalog and banlist first: {e}"))?,
    )
    .map_err(|e| e.to_string())?;
    if !value.is_object() {
        return Err("active snapshot pointer must be an object".into());
    }
    Ok(value)
}
fn save_active(path: &Path, key: &str, value: &str) -> Result<(), String> {
    if let Some(parent) = path.parent().filter(|p| !p.as_os_str().is_empty()) {
        fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let mut v = if path.exists() {
        active(path)?
    } else {
        serde_json::json!({})
    };
    v[key] = serde_json::Value::String(value.into());
    fs::write(
        path,
        serde_json::to_vec_pretty(&v).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())
}
fn execute(args: &[String]) -> Result<(), String> {
    let command = Command::parse(args).ok_or(
        "usage: ygo <engine|catalog|banlist|deck|combo> <command> [--input path] [--output path]",
    )?;
    if command == Command::EngineWorker {
        return worker_main().map_err(|e| e.to_string());
    }
    let opts = options(&args[2..])?;
    let allowed = match command {
        Command::KnowledgeVerify => vec!["--cases", "--output", "--knowledge", "--store"],
        Command::KnowledgeValidate => vec!["--knowledge"],
        Command::CardExplain => vec!["--knowledge", "--id", "--output", "--store"],
        Command::ComboPlan => vec!["--input", "--output", "--store", "--scoring", "--knowledge"],
        Command::ComboPlanReplay => vec!["--input", "--store"],
        Command::CatalogImport => vec!["--input", "--store"],
        Command::BanlistImport => vec!["--input", "--store", "--commit"],
        Command::CatalogStatus | Command::BanlistStatus => vec!["--store", "--id"],
        Command::DeckValidate => vec![
            "--input",
            "--store",
            "--catalog-id",
            "--banlist-id",
            "--as-of",
        ],
        Command::ComboAnalyze | Command::EngineSmoke => {
            vec!["--input", "--output", "--store", "--scoring"]
        }
        Command::ComboReplay => vec!["--input", "--store"],
        Command::EngineDoctor => vec![],
        _ => return Err("command not supported in Combo MVP".into()),
    };
    for flag in opts.keys() {
        if !allowed.contains(&flag.as_str()) {
            return Err(format!("unknown flag {flag}"));
        }
    }
    let store = SnapshotStore::new(
        opts.get("--store")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("YGO_SNAPSHOT_STORE").map(PathBuf::from))
            .unwrap_or_else(|| "data/snapshots".into()),
    );
    let pointer_path = if opts.contains_key("--store") {
        store.root.join("active.json")
    } else {
        std::env::var_os("YGO_ACTIVE_SNAPSHOT")
            .map(PathBuf::from)
            .unwrap_or_else(|| store.root.join("active.json"))
    };
    match command {
        Command::KnowledgeVerify => {
            let cases = serde_json::from_slice(
                &fs::read(need(&opts, "--cases")?).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            let p = active(&pointer_path)?;
            let pack = knowledge_v2(&opts)?;
            let report = ygo_api::verification::verify(
                cases,
                engine()?,
                &store,
                p["catalog_id"].as_str().ok_or("catalog not imported")?,
                pack,
            )?;
            output(&opts, &report)?;
            if report["passed"] != true {
                return Err("effect verification failed; see case evidence".into());
            }
        }
        Command::KnowledgeValidate => {
            let k = knowledge(&opts)?;
            let cfg = engine()?;
            k.validate_sources(
                &cfg.catalog_path,
                &cfg.scripts_path,
                &cfg.script_manifest_path,
            )?;
            json(
                &serde_json::json!({"schema_version":1,"knowledge_id":k.id(),"cards":k.cards.len(),"sources_verified":true,"semantic_status":k.evidence_status}),
            )?;
        }
        Command::CardExplain => {
            let k = knowledge(&opts)?;
            let cfg = engine()?;
            k.validate_sources(
                &cfg.catalog_path,
                &cfg.scripts_path,
                &cfg.script_manifest_path,
            )?;
            let id = need(&opts, "--id")?
                .parse::<u32>()
                .map_err(|_| "card ID must be an unsigned integer")?;
            let pointer = active(&pointer_path)?;
            let catalog = store.catalog(
                pointer["catalog_id"]
                    .as_str()
                    .ok_or("catalog not imported")?,
            )?;
            if catalog.source_sha256 != k.cdb_sha256 {
                return Err("explanation catalog/source mismatch".into());
            }
            let mut explanation = k.explain_catalog(id, &catalog.data)?;
            explanation["catalog_id"] = catalog.id.into();
            output(&opts, &explanation)?;
        }
        Command::ComboPlan => {
            let weights = scoring(&opts)?;
            let value: serde_json::Value = serde_json::from_slice(
                &fs::read(need(&opts, "--input")?).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            if ![
                serde_json::json!(1),
                serde_json::json!(2),
                serde_json::json!(3),
            ]
            .contains(&value["schema_version"])
            {
                return Err("unsupported planning schema_version".into());
            }
            if value["schema_version"] == 3 {
                let q: ygo_api::planning_v3::PlanRequest =
                    serde_json::from_value(value).map_err(|e| e.to_string())?;
                let id = q
                    .analysis
                    .catalog_id
                    .clone()
                    .or_else(|| {
                        active(&pointer_path)
                            .ok()
                            .and_then(|v| v["catalog_id"].as_str().map(String::from))
                    })
                    .ok_or("catalog not imported")?;
                let r = ygo_api::planning_v3::plan(
                    q,
                    engine()?,
                    &store,
                    &id,
                    &weights,
                    knowledge_v2(&opts)?,
                )?;
                return output(&opts, &serde_json::to_value(r).map_err(|e| e.to_string())?);
            }
            if value["schema_version"] == 2 {
                let q: ygo_api::planning_v2::PlanRequest =
                    serde_json::from_value(value).map_err(|e| e.to_string())?;
                let id = q
                    .analysis
                    .catalog_id
                    .clone()
                    .or_else(|| {
                        active(&pointer_path)
                            .ok()
                            .and_then(|v| v["catalog_id"].as_str().map(String::from))
                    })
                    .ok_or("catalog not imported")?;
                let pack = knowledge_v2(&opts)?;
                let r = ygo_api::planning_v2::plan(q, engine()?, &store, &id, &weights, pack)?;
                eprintln!(
                    "v2 planning: {} lines, {} engine calls",
                    r.analysis.search.lines.len(),
                    r.analysis.search.stats.engine_calls
                );
                return output(&opts, &serde_json::to_value(r).map_err(|e| e.to_string())?);
            }

            let q: ygo_api::planning::PlanRequest = serde_json::from_slice(
                &fs::read(need(&opts, "--input")?).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            let catalog_id = if let Some(id) = q.analysis.catalog_id.clone() {
                id
            } else {
                active(&pointer_path)?["catalog_id"]
                    .as_str()
                    .ok_or("catalog not imported")?
                    .to_string()
            };
            let weights = if let Some(path) = opts
                .get("--scoring")
                .map(PathBuf::from)
                .or_else(|| std::env::var_os("YGO_SCORING_CONFIG").map(PathBuf::from))
            {
                ScoringConfig::from_toml(&fs::read_to_string(path).map_err(|e| e.to_string())?)?
            } else {
                ScoringConfig::default()
            };
            let r = ygo_api::planning::plan(
                q,
                engine()?,
                &store,
                &catalog_id,
                &weights,
                knowledge(&opts)?,
            )?;
            eprintln!(
                "因果规划：{} 个预测方案，{} 条目标达成且独立重放成功线路；{} 次引擎调用；{}。",
                r.proposals.plans.len(),
                r.analysis.search.lines.len(),
                r.analysis.search.stats.engine_calls,
                r.analysis.search.termination
            );
            output(&opts, &serde_json::to_value(r).map_err(|e| e.to_string())?)?;
        }
        Command::ComboPlanReplay => {
            let value: serde_json::Value = serde_json::from_slice(
                &fs::read(need(&opts, "--input")?).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            if ![
                serde_json::json!(1),
                serde_json::json!(2),
                serde_json::json!(3),
            ]
            .contains(&value["schema_version"])
            {
                return Err("unsupported planning schema_version".into());
            }
            if value["schema_version"] == 3 {
                let r: ygo_api::planning_v3::PlanReport =
                    serde_json::from_value(value).map_err(|e| e.to_string())?;
                return json(&ygo_api::planning_v3::replay(&r, engine()?, &store)?);
            }
            if value["schema_version"] == 2 {
                let r: ygo_api::planning_v2::PlanReport =
                    serde_json::from_value(value).map_err(|e| e.to_string())?;
                return json(&ygo_api::planning_v2::replay(&r, engine()?, &store)?);
            }

            let r: ygo_api::planning::PlanReport = serde_json::from_slice(
                &fs::read(need(&opts, "--input")?).map_err(|e| e.to_string())?,
            )
            .map_err(|e| e.to_string())?;
            json(&ygo_api::planning::replay(&r, engine()?, &store)?)?;
        }
        Command::EngineDoctor => {
            let r = ProcessEngineAdapter::new(engine()?).doctor();
            json(&serde_json::to_value(&r).map_err(|e| e.to_string())?)?;
            if !r.ready {
                return Err("engine doctor failed; smoke not executed".into());
            }
        }
        Command::CatalogImport => {
            let s = store.import_catalog(&PathBuf::from(need(&opts, "--input")?))?;
            save_active(&pointer_path, "catalog_id", &s.id)?;
            json(
                &serde_json::json!({"id":s.id,"count":s.data.len(),"source_sha256":s.source_sha256}),
            )?;
        }
        Command::BanlistImport => {
            let path = need(&opts, "--input")?;
            let commit = need(&opts, "--commit")?;
            if commit.len() != 40 || !commit.bytes().all(|b| b.is_ascii_hexdigit()) {
                return Err("--commit requires full source commit SHA".into());
            }
            let s = store.import_banlist(
                &fs::read_to_string(path).map_err(|e| e.to_string())?,
                "https://github.com/ProjectIgnis/LFLists",
                commit,
            )?;
            save_active(&pointer_path, "banlist_id", &s.id)?;
            json(
                &serde_json::json!({"id":s.id,"effective_date":s.effective_date,"count":s.data.limits.len()}),
            )?;
        }
        Command::CatalogStatus | Command::BanlistStatus => {
            let pointer = if opts.contains_key("--id") {
                serde_json::json!({})
            } else {
                active(&pointer_path)?
            };
            let key = if command == Command::CatalogStatus {
                "catalog_id"
            } else {
                "banlist_id"
            };
            let id = opts
                .get("--id")
                .map(String::as_str)
                .or_else(|| pointer[key].as_str())
                .ok_or("snapshot not imported")?;
            if command == Command::CatalogStatus {
                let s = store.catalog(id)?;
                json(
                    &serde_json::json!({"id":s.id,"count":s.data.len(),"source_sha256":s.source_sha256}),
                )?;
            } else {
                let s = store.banlist(id)?;
                json(
                    &serde_json::json!({"id":s.id,"effective_date":s.effective_date,"count":s.data.limits.len()}),
                )?;
            }
        }
        Command::DeckValidate => {
            let deck = ygo_domain::parse_deck(
                &fs::read_to_string(need(&opts, "--input")?).map_err(|e| e.to_string())?,
            )?;
            let pointer = if opts.contains_key("--catalog-id") {
                serde_json::json!({})
            } else {
                active(&pointer_path)?
            };
            let id = opts
                .get("--catalog-id")
                .map(String::as_str)
                .or_else(|| pointer["catalog_id"].as_str())
                .ok_or("catalog missing")?;
            let c = store.catalog(id)?;
            let as_of = opts.get("--as-of").ok_or("--as-of YYYY-MM-DD required")?;
            ygo_storage::validate_date(as_of)?;
            let b = match opts.get("--banlist-id").map(String::as_str) {
                Some(id) if id != "latest-ocg" => store.banlist(id)?,
                _ => store.latest_ocg(as_of)?,
            };
            if b.effective_date
                .as_deref()
                .map_or(true, |d| d > as_of.as_str())
            {
                return Err("banlist not effective".into());
            }
            let r = ygo_domain::validate_catalog_deck(&deck, &b.data, &c.data);
            json(
                &serde_json::json!({"legal":r.is_legal(),"report":r,"catalog":c.id,"banlist":b.id}),
            )?;
            if !r.is_legal() {
                return Err("illegal deck".into());
            }
        }
        Command::ComboAnalyze | Command::EngineSmoke => {
            let smoke = std::env::var("YGO_SMOKE_REQUEST")
                .unwrap_or_else(|_| "tests/fixtures/rabbit.request.json".into());
            let input = opts.get("--input").map(String::as_str).unwrap_or(&smoke);
            let mut request: ComboAnalyzeRequest =
                serde_json::from_slice(&fs::read(input).map_err(|e| e.to_string())?)
                    .map_err(|e| e.to_string())?;
            if command == Command::EngineSmoke {
                request.search.node_budget = 500;
                request.search.top_k = 3;
                request.search.max_depth = 24;
                request.search.time_limit_ms = 30000;
            }
            let pointer = if request.catalog_id.is_some() {
                serde_json::json!({})
            } else {
                active(&pointer_path)?
            };
            let catalog = request
                .catalog_id
                .as_deref()
                .or_else(|| pointer["catalog_id"].as_str())
                .ok_or("catalog missing")?
                .to_owned();
            let scoring_path = std::env::var("YGO_SCORING_CONFIG")
                .unwrap_or_else(|_| "configs/scoring.toml".into());
            let scoring = ScoringConfig::from_toml(
                &fs::read_to_string(
                    opts.get("--scoring")
                        .map(String::as_str)
                        .unwrap_or(&scoring_path),
                )
                .map_err(|e| e.to_string())?,
            )?;
            let report = analyze(request, engine()?, &store, &catalog, &scoring)?;
            let value = serde_json::to_value(&report).map_err(|e| e.to_string())?;
            if let Some(path) = opts.get("--output") {
                fs::write(
                    path,
                    serde_json::to_vec_pretty(&value).map_err(|e| e.to_string())?,
                )
                .map_err(|e| e.to_string())?;
            } else {
                json(&value)?;
            }
            eprintln!(
                "推演完成：{} 条可重放线路，节点 {}，耗时 {} ms，终止原因 {}",
                report.search.lines.len(),
                report.search.stats.nodes,
                report.search.stats.elapsed_ms,
                report.search.termination
            );
            for (i, line) in report.search.lines.iter().enumerate() {
                eprintln!(
                    "线路 {}：评分 {:.2}（启发式），验证 {:?}",
                    i + 1,
                    line.evaluation.total,
                    line.result.status
                );
                for step in &line.result.steps {
                    let names = step
                        .card_ids
                        .iter()
                        .map(|id| {
                            format!(
                                "{} ({id})",
                                report
                                    .card_names
                                    .get(id)
                                    .map(String::as_str)
                                    .unwrap_or("未知卡")
                            )
                        })
                        .collect::<Vec<_>>();
                    eprintln!("  {} {}", step.label, names.join(", "));
                }
                let end = line
                    .result
                    .checkpoint
                    .cards
                    .iter()
                    .filter(|c| c.player == 0 && matches!(c.location, 4 | 8))
                    .map(|c| {
                        format!(
                            "{} ({})",
                            report
                                .card_names
                                .get(&c.code)
                                .map(String::as_str)
                                .unwrap_or("未知卡"),
                            c.code
                        )
                    })
                    .collect::<Vec<_>>();
                eprintln!("  终场：{}", end.join(", "));
            }
            if command == Command::EngineSmoke
                && !report
                    .search
                    .lines
                    .iter()
                    .any(|l| l.replay_verified && l.result.status == DuelStatus::EngineVerified)
            {
                return Err("smoke failed: no fully verified line".into());
            }
        }
        Command::ComboReplay => {
            let r = read_report(&PathBuf::from(need(&opts, "--input")?))?;
            json(&replay(&r, engine()?, &store)?)?;
        }
        _ => return Err("unsupported command".into()),
    }
    Ok(())
}
fn main() {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if let Err(message) = execute(&args) {
        eprintln!(
            "{}",
            serde_json::json!({"error":{"code":"command_failed","message":message}})
        );
        std::process::exit(2);
    }
}
