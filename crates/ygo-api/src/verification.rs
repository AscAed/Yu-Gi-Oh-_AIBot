//! Real-engine effect cases. Recipes are authored separately from the symbolic planner.
use serde::{Deserialize, Serialize};
use ygo_engine_adapter::*;
use ygo_knowledge::KnowledgePack;
use ygo_storage::SnapshotStore;
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Instruction {
    pub kind: String,
    #[serde(default)]
    pub code: u32,
    #[serde(default)]
    pub index: u64,
    #[serde(default)]
    pub cards: Vec<u32>,
    #[serde(default)]
    pub player: u8,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Assertion {
    pub code: u32,
    pub zone: u8,
    #[serde(default)]
    pub player: u8,
    pub count: usize,
    #[serde(default)]
    pub level: Option<u32>,
    #[serde(default)]
    pub rank: Option<u32>,
    #[serde(default)]
    pub overlay: Option<usize>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Case {
    pub id: String,
    pub effect_id: String,
    pub request: crate::planning_v2::PlanRequest,
    pub steps: Vec<Instruction>,
    pub activation_step: usize,
    pub assertions: Vec<Assertion>,
    pub negative_reason: String,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Cases {
    pub schema_version: u16,
    pub cases: Vec<Case>,
}
pub(crate) fn matches(i: &Instruction, m: &ActionMetadata) -> bool {
    let source = m
        .source
        .as_ref()
        .is_some_and(|s| s.code == i.code && s.player == i.player);
    match i.kind.as_str() {
        "end" => matches!(m.choice, Choice::Command { command: 7, .. }),
        "normal" => source && matches!(m.choice, Choice::Command { command: 0, .. }),
        "special" => source && matches!(m.choice, Choice::Command { command: 1, .. }),
        "set" => source && matches!(m.choice, Choice::Command { command: 4, .. }),
        "effect" if i.code == 36426778 && i.index == 0 => {
            source
                && m.source.as_ref().is_some_and(|s| s.location == 2)
                && matches!(m.choice, Choice::Command { command: 1, .. })
        }
        "effect" => {
            source
                && (m.effect_description == Some(((i.code as u64) << 20) + i.index)
                    || (m.effect_description == Some(0)
                        && matches!(i.code, 32807846 | 81439173 | 98827725))
                    || (m.effect_description == Some(221)
                        && matches!(m.choice, Choice::YesNo { yes: true })))
                && matches!(
                    m.choice,
                    Choice::Command { command: 5, .. }
                        | Choice::Chain { index: Some(_) }
                        | Choice::YesNo { yes: true }
                )
        }
        "cards" => {
            matches!(m.choice, Choice::Cards { .. })
                && m.selected.iter().all(|c| c.player == i.player)
                && m.selected.iter().map(|c| c.code).collect::<Vec<_>>() == i.cards
        }
        "material" => {
            matches!(m.choice, Choice::Toggle { .. })
                && m.selection_group != Some(1)
                && m.selected
                    .iter()
                    .any(|c| c.code == i.code && c.player == i.player)
        }
        "yes" => matches!(m.choice, Choice::YesNo { yes: true }),
        _ => false,
    }
}
pub(crate) fn neutral(metadata: &[ActionMetadata]) -> Option<ActionMetadata> {
    metadata
        .iter()
        .find(|m| {
            matches!(
                m.choice,
                Choice::Chain { index: None }
                    | Choice::YesNo { yes: false }
                    | Choice::Place { .. }
                    | Choice::Position { position: 1 }
                    | Choice::Finish
            )
        })
        .cloned()
}
pub(crate) fn equivalent(a: &DuelResult, b: &DuelResult) -> bool {
    a.status == b.status
        && a.events == b.events
        && a.checkpoint == b.checkpoint
        && a.resolved_decisions == b.resolved_decisions
        && a.versions == b.versions
        && a.loaded_scripts == b.loaded_scripts
        && a.steps == b.steps
}
pub fn verify(
    cases: Cases,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog_id: &str,
    pack: KnowledgePack,
) -> Result<serde_json::Value, String> {
    if cases.schema_version != 1 || cases.cases.is_empty() || cases.cases.len() > 128 {
        return Err("invalid effect case limits/version".into());
    }
    pack.validate_sources(
        &engine.catalog_path,
        &engine.scripts_path,
        &engine.script_manifest_path,
    )?;
    let mut ids = std::collections::BTreeSet::new();
    let mut outputs = vec![];
    for case in cases.cases {
        if !ids.insert(case.id.clone())
            || case.activation_step >= case.steps.len()
            || case.negative_reason.is_empty()
            || !pack.effect(&case.effect_id).is_some_and(|e| e.supported)
        {
            return Err("invalid effect case identity/coverage".into());
        }
        let outcome = verify_case(&case, engine.clone(), store, catalog_id, &pack);
        outputs.push(match outcome {Ok(v)=>v,Err(e)=>serde_json::json!({"case_id":case.id,"effect_id":case.effect_id,"passed":false,"error":e})});
    }
    Ok(
        serde_json::json!({"schema_version":1,"knowledge_id":pack.id(),"sources_verified":true,"passed":outputs.iter().all(|v|v["passed"]==true),"cases":outputs}),
    )
}
fn verify_case(
    case: &Case,
    engine: ProcessEngineConfig,
    store: &SnapshotStore,
    catalog_id: &str,
    pack: &KnowledgePack,
) -> Result<serde_json::Value, String> {
    case.request.validate()?;
    if case.steps[case.activation_step].kind != "effect" {
        return Err("activation must name a native effect choice".into());
    }
    let effect = pack.effect(&case.effect_id).ok_or("unknown effect")?;
    let activation = &case.steps[case.activation_step];
    if case
        .effect_id
        .split(':')
        .next()
        .and_then(|s| s.parse::<u32>().ok())
        != Some(activation.code)
        || effect.description_index != Some(activation.index)
    {
        return Err("activation/effect identity mismatch".into());
    }
    let (_, mut q, catalog) = crate::combo::prepare(
        case.request.analysis.clone(),
        engine.clone(),
        store,
        catalog_id,
    )?;
    q.protocol_version = 3;
    q.versions.initializer = "fixed-opponent-v1".into();
    q.scenario = case.request.scenario.clone();
    let adapter = ProcessEngineAdapter::new(engine);
    let start = std::time::Instant::now();
    let mut calls = 0;
    let budget = &case.request.analysis.search;
    let mut run = |q: &RunDuelRequest| -> Result<DuelResult, String> {
        let left = budget
            .time_limit_ms
            .saturating_sub(start.elapsed().as_millis() as u64);
        if calls >= budget.node_budget || left == 0 {
            return Err("shared case budget exhausted".into());
        }
        calls += 1;
        let mut request = q.clone();
        request.engine.timeout_ms = request.engine.timeout_ms.min(left);
        adapter
            .run(&request)
            .map_err(|e| format!("{}: {}", e.code, e.message))
    };
    let mut actual = run(&q)?;
    let mut cursor = 0;
    let mut witness = None;
    let mut selected = None;
    let mut predictions = vec![];
    for _ in 0..budget.max_depth {
        if actual.status == DuelStatus::Failed || !actual.coverage_gaps.is_empty() {
            return Err(format!(
                "engine gap/failure: {:?} {:?}",
                actual.error, actual.coverage_gaps
            ));
        }
        q.decisions = actual.resolved_decisions.clone();
        let prompt = actual
            .prompt
            .as_ref()
            .ok_or("case ended before assertions")?;
        if cursor == case.steps.len() && prompt.opcode == 11 {
            break;
        }
        let raw = actual
            .events
            .iter()
            .find(|e| e.sequence == prompt.id)
            .ok_or("missing native prompt")?;
        let metadata = prompt_metadata(raw.sequence, &raw.raw)?;
        let instruction = case.steps.get(cursor);
        let action = instruction
            .and_then(|i| metadata.iter().find(|m| matches(i, m)))
            .cloned();
        let action = if let Some(action) = action {
            if cursor == case.activation_step {
                let state = symbolic_before(&actual, &catalog, &case.effect_id)?;
                predictions = ygo_planner::v2::successors(&state, &catalog, pack)
                    .into_iter()
                    .filter(|s| s.effect_id == case.effect_id)
                    .collect();
                if predictions.is_empty() {
                    return Err("symbolic model rejects native legal effect".into());
                }
                witness = Some(actual.clone());
                selected = Some(Decision {
                    prompt_id: prompt.id,
                    player: prompt.player,
                    choice: action.choice.clone(),
                });
            }
            cursor += 1;
            action
        } else {
            if prompt.opcode == 11 && instruction.is_some() {
                return Err(format!("recipe {} unavailable: {:?}", cursor, instruction));
            }
            neutral(&metadata).ok_or_else(|| {
                format!(
                    "unbound recipe prompt {} opcode {} step {}",
                    prompt.id, prompt.opcode, cursor
                )
            })?
        };
        q.decisions.push(Decision {
            prompt_id: prompt.id,
            player: prompt.player,
            choice: action.choice,
        });
        actual = run(&q)?;
        for decision in actual.resolved_decisions.iter().skip(q.decisions.len()) {
            if let Some(i) = case.steps.get(cursor) {
                let frame = actual
                    .events
                    .iter()
                    .find(|e| e.sequence == decision.prompt_id)
                    .ok_or("missing auto prompt")?;
                if prompt_metadata(frame.sequence, &frame.raw)?
                    .iter()
                    .any(|m| m.choice == decision.choice && matches(i, m))
                {
                    cursor += 1;
                }
            }
        }
    }
    if cursor != case.steps.len() || !actual.prompt.as_ref().is_some_and(|p| p.opcode == 11) {
        return Err("recipe/depth not completed".into());
    }
    for check in &case.assertions {
        let cards: Vec<_> = actual
            .checkpoint
            .cards
            .iter()
            .filter(|c| {
                c.code == check.code && c.player == check.player && c.location == check.zone
            })
            .collect();
        if cards.len() != check.count
            || cards.iter().any(|c| {
                check.level.is_some_and(|v| c.level != Some(v))
                    || check.rank.is_some_and(|v| c.rank != Some(v))
                    || check.overlay.is_some_and(|v| c.overlay.len() != v)
            })
        {
            return Err(format!(
                "resource assertion failed {:?}; actual {:?}",
                check, cards
            ));
        }
    }
    let prediction = predictions
        .iter()
        .find(|p| ygo_planner::v2::matches_checkpoint(&p.after, &actual.checkpoint))
        .ok_or("symbolic/actual resource projection mismatch")?;
    let p = actual.prompt.as_ref().unwrap();
    let raw = actual.events.iter().find(|e| e.sequence == p.id).unwrap();
    if prompt_metadata(p.id, &raw.raw)?
        .iter()
        .any(|m| matches(activation, m))
    {
        return Err("negative case still offers the effect".into());
    }
    let before = witness.ok_or("missing activation witness")?;
    let selected = selected.ok_or("missing selected effect")?;
    q.decisions = actual.resolved_decisions.clone();
    let replay = run(&q)?;
    if !equivalent(&actual, &replay) {
        return Err("independent case replay mismatch".into());
    }
    let index = actual
        .resolved_decisions
        .iter()
        .position(|d| d == &selected)
        .ok_or("activation absent from actual decisions")?;
    let mut prefix = q.clone();
    prefix.decisions = actual.resolved_decisions[..index].to_vec();
    let replay_before = run(&prefix)?;
    if !equivalent(&before, &replay_before) {
        return Err("activation prefix witness mismatch".into());
    }
    Ok(
        serde_json::json!({"case_id":case.id,"effect_id":case.effect_id,"passed":true,"positive":{"selected":selected,"before_checkpoint":before.checkpoint,"before_events":before.events.len(),"assertions":case.assertions,"symbolic_prediction":prediction},"negative":{"failure_kind":"rules_rejected","reason":case.negative_reason,"prompt_id":p.id,"effect_offered":false},"runtime_request":q,"observation":actual,"independent_replay":true,"prefix_witness_verified":true,"engine_calls":calls}),
    )
}
fn symbolic_before(
    actual: &DuelResult,
    cat: &ygo_domain::Catalog,
    effect: &str,
) -> Result<ygo_planner::v2::SymbolicState, String> {
    use ygo_planner::v2::*;
    let mut cards = vec![];
    for c in &actual.checkpoint.cards {
        if c.player == 1 && !matches!(c.location, 4 | 8 | 16 | 32) {
            continue;
        }
        let base = cat
            .get(&ygo_domain::CardId(c.code))
            .ok_or("unknown checkpoint card")?;
        let instance = format!("runtime:{}:{}:{}", c.player, c.location, c.sequence);
        let xyz = c.code == 62709239
            && actual.resolved_decisions.iter().any(|d| {
                actual
                    .events
                    .iter()
                    .find(|e| e.sequence == d.prompt_id)
                    .and_then(|e| prompt_metadata(e.sequence, &e.raw).ok())
                    .is_some_and(|m| {
                        m.iter().any(|m| {
                            m.choice == d.choice
                                && m.source
                                    .as_ref()
                                    .is_some_and(|s| s.code == 62709239 && s.location == 64)
                                && matches!(m.choice, Choice::Command { command: 1, .. })
                        })
                    })
            });
        let xyz = xyz
            && actual
                .events
                .iter()
                .rev()
                .find(|e| {
                    e.opcode == 50 && e.fields["code"] == c.code && e.fields["to"]["location"] == 4
                })
                .is_some_and(|e| e.fields["from"]["location"] == 64);
        cards.push(Resource {
            instance: instance.clone(),
            code: c.code,
            location: c.location,
            level: c.level.ok_or("v3 level missing")?,
            redirect: false,
            player: c.player,
            overlay_host: None,
            xyz_summoned: xyz,
            base_level: if base.type_flags & 0x4800000 == 0 {
                base.level
            } else {
                0
            },
            epoch: 0,
        });
        for (i, code) in c.overlay.iter().enumerate() {
            let m = cat
                .get(&ygo_domain::CardId(*code))
                .ok_or("unknown material")?;
            cards.push(Resource {
                instance: format!("{instance}:overlay:{i}"),
                code: *code,
                location: 128,
                level: m.level,
                redirect: false,
                player: c.player,
                overlay_host: Some(instance.clone()),
                xyz_summoned: false,
                base_level: m.level,
                epoch: 0,
            });
        }
    }
    let mut state = SymbolicState {
        cards,
        used: Default::default(),
        normal_left: 0,
        pending: vec![],
        dark_only: false,
        destroyed_xyz: Default::default(),
    };
    let code = effect
        .split(':')
        .next()
        .and_then(|s| s.parse::<u32>().ok())
        .ok_or("invalid effect id")?;
    if matches!(
        effect,
        "25538345:revive" | "88544390:summon" | "62709239:revive"
    ) {
        let range = if code == 88544390 { 2 } else { 16 };
        for c in state
            .cards
            .iter()
            .filter(|c| c.code == code && c.location == range)
        {
            state.pending.push((code, c.instance.clone()));
            if code == 62709239 && c.xyz_summoned {
                state.destroyed_xyz.insert(c.instance.clone());
            }
        }
    }
    Ok(state)
}
