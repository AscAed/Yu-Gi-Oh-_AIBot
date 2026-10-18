use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use ygo_domain::{CardId, Catalog, Deck};
use ygo_knowledge::{KnowledgePack, Rule, Truth};
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
pub struct Resource {
    pub instance: String,
    pub code: u32,
    pub location: u8,
    pub level: u32,
    pub redirect: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
pub struct SymbolicState {
    pub cards: Vec<Resource>,
    pub used: BTreeSet<String>,
    pub normal_left: u8,
    pub pending: Vec<(u32, String)>,
    pub dark_only: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum StepKind {
    NormalSummon,
    SpecialSummon,
    Activate,
    Trigger,
    LinkSummon,
    Set,
    EndTurn,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct SemanticStep {
    pub kind: StepKind,
    pub effect_id: String,
    pub source: Resource,
    pub costs: Vec<Resource>,
    pub targets: Vec<Resource>,
    pub reason: String,
    pub after: SymbolicState,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Proposal {
    pub id: String,
    pub steps: Vec<SemanticStep>,
    pub goal_predicted: bool,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Proposals {
    pub plans: Vec<Proposal>,
    pub expansions: usize,
    pub termination: String,
    pub coverage_gaps: Vec<String>,
}
pub fn goal(state: &SymbolicState) -> bool {
    state
        .cards
        .iter()
        .any(|c| c.code == 26692769 && c.location == 4)
        && state
            .cards
            .iter()
            .any(|c| c.code == 25542642 && c.location == 8)
}
pub fn initial_state(
    deck: &Deck,
    hand: &[CardId],
    catalog: &Catalog,
) -> Result<SymbolicState, String> {
    ygo_domain::validate_hand(deck, hand)?;
    let mut cards = vec![];
    for (zone, ids) in [(1, &deck.main), (64, &deck.extra)] {
        for (i, id) in ids.iter().enumerate() {
            let c = catalog.get(id).ok_or("unknown symbolic card")?;
            cards.push(Resource {
                instance: format!("{zone}:{i}"),
                code: id.0,
                location: zone,
                level: c.level,
                redirect: false,
            });
        }
    }
    for id in hand {
        cards
            .iter_mut()
            .find(|c| c.code == id.0 && c.location == 1)
            .ok_or("hand multiplicity")?
            .location = 2;
    }
    Ok(SymbolicState {
        cards,
        used: BTreeSet::new(),
        normal_left: 1,
        pending: vec![],
        dark_only: false,
    })
}
fn is_pk(code: u32, cat: &Catalog) -> bool {
    cat.get(&CardId(code))
        .is_some_and(|c| c.setcodes.iter().any(|s| s & 0xfff == 0xdb))
}
fn field_monster(c: &Resource, cat: &Catalog) -> bool {
    c.location == 4
        && (c.code == 98827725
            || cat
                .get(&CardId(c.code))
                .is_some_and(|c| c.type_flags & 1 != 0))
}
fn move_to(s: &mut SymbolicState, card: &Resource, location: u8) {
    if let Some(c) = s.cards.iter_mut().find(|c| c.instance == card.instance) {
        c.location = if location == 16 && c.redirect {
            32
        } else {
            location
        };
    }
}
fn banish(s: &mut SymbolicState, c: &Resource, cat: &Catalog) {
    move_to(s, c, 32);
    if c.location == 16 && is_pk(c.code, cat) {
        for other in &s.cards {
            if other.code == 25538345 && other.location == 16 && !s.used.contains("25538345:revive")
            {
                s.pending.push((other.code, other.instance.clone()));
            }
        }
    }
}
fn special(s: &mut SymbolicState, c: &Resource, redirect: bool, cat: &Catalog) {
    move_to(s, c, 4);
    if let Some(c) = s.cards.iter_mut().find(|a| a.instance == c.instance) {
        c.redirect = redirect;
    }
    if is_pk(c.code, cat) && !s.used.contains("88544390:summon") {
        for other in &s.cards {
            if other.code == 88544390 && other.location == 2 {
                s.pending.push((other.code, other.instance.clone()));
            }
        }
    }
}
fn available(s: &SymbolicState, zone: u8) -> Vec<Resource> {
    s.cards
        .iter()
        .filter(|c| c.location == zone)
        .cloned()
        .collect()
}
// Keep the transition's explicit inputs together at this internal construction boundary.
#[allow(clippy::too_many_arguments)]
fn emit(
    out: &mut Vec<SemanticStep>,
    mut state: SymbolicState,
    source: &Resource,
    kind: StepKind,
    id: String,
    costs: Vec<Resource>,
    targets: Vec<Resource>,
    pack: &KnowledgePack,
) {
    let reason = if let Some(e) = pack.effect(&id) {
        if let Some(key) = &e.usage_key {
            state.used.insert(key.clone());
        }
        format!("目标 Rusty Bardiche 在场且 Fog Blade 盖放；{}：{}。条件：{}；费用：{}；限制：{}。此为执行前预测。",e.id,e.operations.join("；"),e.conditions.join("；"),e.costs.join("；"),e.restrictions.join("；"))
    } else {
        format!("目标 Rusty Bardiche 在场且 Fog Blade 盖放；{kind:?} {} 提供素材/场上资源，先预测再验证。",source.code)
    };
    state.pending.retain(|(code, instance)| {
        let required = if *code == 25538345 { 16 } else { 2 };
        let key = if *code == 25538345 {
            "25538345:revive"
        } else {
            "88544390:summon"
        };
        !state.used.contains(key)
            && state
                .cards
                .iter()
                .any(|c| &c.instance == instance && c.location == required)
    });
    if state.cards.iter().filter(|c| c.location == 4).count() > 5
        || state.cards.iter().filter(|c| c.location == 8).count() > 5
    {
        return;
    }
    out.push(SemanticStep {
        kind,
        effect_id: id,
        source: source.clone(),
        costs,
        targets,
        reason,
        after: state,
    });
}
/// Generate resource transitions; legality remains a hypothesis until the engine binds it.
pub fn successors(s: &SymbolicState, cat: &Catalog, pack: &KnowledgePack) -> Vec<SemanticStep> {
    let mut out = vec![];
    for c in &s.cards {
        let base = || {
            let mut n = s.clone();
            n.pending.clear();
            n
        };
        let metadata = cat.get(&CardId(c.code));
        if c.location == 2
            && s.normal_left > 0
            && metadata.is_some_and(|m| {
                m.type_flags & 1 != 0 && m.type_flags & 0x4800000 == 0 && m.level <= 4
            })
        {
            let mut n = base();
            n.normal_left -= 1;
            move_to(&mut n, c, 4);
            emit(
                &mut out,
                n,
                c,
                StepKind::NormalSummon,
                format!("{}:normal", c.code),
                vec![],
                vec![],
                pack,
            );
        }
        if c.location == 2 && matches!(c.code, 25542642 | 98827725) {
            let mut n = base();
            move_to(&mut n, c, 8);
            emit(
                &mut out,
                n,
                c,
                StepKind::Set,
                format!("{}:set", c.code),
                vec![],
                vec![],
                pack,
            );
        }
        if c.location == 64
            && matches!(c.code, 58699500 | 26692769)
            && (!s.dark_only || metadata.is_some_and(|m| m.attribute == 32))
        {
            let field: Vec<_> = s
                .cards
                .iter()
                .filter(|m| field_monster(m, cat) && m.code != 26692769)
                .cloned()
                .collect();
            for mask in 1usize..(1 << field.len()) {
                let materials: Vec<_> = field
                    .iter()
                    .enumerate()
                    .filter(|(i, _)| mask & (1 << i) != 0)
                    .map(|(_, c)| c.clone())
                    .collect();
                let valid = if c.code == 58699500 {
                    materials.len() == 2 && materials.iter().all(|c| c.level == 3)
                } else {
                    materials.len() >= 2
                        && materials.iter().all(|c| {
                            c.code == 98827725
                                || cat.get(&CardId(c.code)).is_some_and(|m| m.attribute == 32)
                        })
                        && {
                            let max: usize = materials
                                .iter()
                                .map(|m| if matches!(m.code, 58699500) { 2 } else { 1 })
                                .sum();
                            materials.len() <= 3 && max >= 3
                        }
                };
                if valid {
                    let mut n = base();
                    for m in &materials {
                        move_to(&mut n, m, 16);
                    }
                    special(&mut n, c, false, cat);
                    emit(
                        &mut out,
                        n,
                        c,
                        StepKind::LinkSummon,
                        format!("{}:link", c.code),
                        materials,
                        vec![],
                        pack,
                    );
                }
            }
        }
        let Some(knowledge) = pack.card(c.code) else {
            continue;
        };
        for e in knowledge.effects.iter().filter(|e| e.supported) {
            if e.usage_key.as_ref().is_some_and(|k| s.used.contains(k)) {
                continue;
            }
            let targets = |zone| {
                available(s, zone)
                    .into_iter()
                    .filter(|target| {
                        e.candidate_filter.as_ref().map_or(true, |f| {
                            f.matches(cat.get(&CardId(target.code))) == Truth::Yes
                        })
                    })
                    .collect::<Vec<_>>()
            };
            match e.rule {
                Rule::BootsSummon
                    if c.location == 2
                        && s.cards
                            .iter()
                            .any(|m| field_monster(m, cat) && is_pk(m.code, cat)) =>
                {
                    let mut n = base();
                    special(&mut n, c, false, cat);
                    emit(
                        &mut out,
                        n,
                        c,
                        StepKind::SpecialSummon,
                        e.id.clone(),
                        vec![],
                        vec![],
                        pack,
                    );
                }
                Rule::ScaleRevive | Rule::GreavesSummon
                    if s.pending.contains(&(c.code, c.instance.clone())) =>
                {
                    let mut n = base();
                    special(&mut n, c, e.rule == Rule::ScaleRevive, cat);
                    emit(
                        &mut out,
                        n,
                        c,
                        StepKind::Trigger,
                        e.id.clone(),
                        vec![],
                        vec![],
                        pack,
                    );
                }
                Rule::Brigandine
                    if c.location == 8
                        && !s.cards.iter().any(|m| {
                            m.location == 16
                                && cat
                                    .get(&CardId(m.code))
                                    .is_some_and(|m| m.type_flags & 4 != 0)
                        }) =>
                {
                    let mut n = base();
                    special(&mut n, c, false, cat);
                    if let Some(r) = n.cards.iter_mut().find(|r| r.instance == c.instance) {
                        r.level = 4;
                    }
                    emit(
                        &mut out,
                        n,
                        c,
                        StepKind::Activate,
                        e.id.clone(),
                        vec![],
                        vec![],
                        pack,
                    );
                }
                Rule::BootsSearch | Rule::CloakSearch | Rule::GlovesMill if c.location == 16 => {
                    for target in targets(1) {
                        let mut n = base();
                        banish(&mut n, c, cat);
                        move_to(
                            &mut n,
                            &target,
                            if e.rule == Rule::GlovesMill { 16 } else { 2 },
                        );
                        emit(
                            &mut out,
                            n,
                            c,
                            StepKind::Activate,
                            e.id.clone(),
                            vec![c.clone()],
                            vec![target],
                            pack,
                        );
                    }
                }
                Rule::ScaleMill if c.location == 4 => {
                    for cost in available(s, 2) {
                        for target in targets(1) {
                            let mut n = base();
                            move_to(&mut n, &cost, 16);
                            move_to(&mut n, &target, 16);
                            emit(
                                &mut out,
                                n,
                                c,
                                StepKind::Activate,
                                e.id.clone(),
                                vec![cost.clone()],
                                vec![target],
                                pack,
                            );
                        }
                    }
                }
                Rule::Rota | Rule::Fool if c.location == 2 => {
                    for target in targets(1) {
                        let mut n = base();
                        move_to(&mut n, c, 16);
                        move_to(&mut n, &target, if e.rule == Rule::Rota { 2 } else { 16 });
                        emit(
                            &mut out,
                            n,
                            c,
                            StepKind::Activate,
                            e.id.clone(),
                            vec![],
                            vec![target],
                            pack,
                        );
                    }
                }
                Rule::CherubiniMill if c.location == 4 => {
                    for cost in targets(1) {
                        let mut n = base();
                        move_to(&mut n, &cost, 16);
                        emit(
                            &mut out,
                            n,
                            c,
                            StepKind::Activate,
                            e.id.clone(),
                            vec![cost],
                            vec![c.clone()],
                            pack,
                        );
                    }
                }
                Rule::RustyMillSet if c.location == 4 => {
                    for target in targets(1) {
                        for trap in available(s, 1)
                            .into_iter()
                            .filter(|m| matches!(m.code, 25542642 | 98827725))
                        {
                            let mut n = base();
                            move_to(&mut n, &target, 16);
                            move_to(&mut n, &trap, 8);
                            emit(
                                &mut out,
                                n,
                                c,
                                StepKind::Activate,
                                e.id.clone(),
                                vec![],
                                vec![target.clone(), trap],
                                pack,
                            );
                        }
                    }
                }
                Rule::FogRevive if c.location == 16 => {
                    for target in targets(16).into_iter().filter(|t| {
                        t.instance != c.instance && !matches!(t.code, 26692769 | 62709239)
                    }) {
                        let mut n = base();
                        banish(&mut n, c, cat);
                        special(&mut n, &target, true, cat);
                        emit(
                            &mut out,
                            n,
                            c,
                            StepKind::Activate,
                            e.id.clone(),
                            vec![c.clone()],
                            vec![target],
                            pack,
                        );
                    }
                }
                Rule::GreavesRevive if c.location == 16 => {
                    for target in targets(2) {
                        let mut n = base();
                        banish(&mut n, c, cat);
                        special(&mut n, &target, false, cat);
                        emit(
                            &mut out,
                            n,
                            c,
                            StepKind::Activate,
                            e.id.clone(),
                            vec![c.clone()],
                            vec![target],
                            pack,
                        );
                    }
                }
                _ => (),
            }
        }
    }
    // A trigger window must be resolved before a new ignition action is proposed.
    // The first profile always takes its supported beneficial triggers.
    if !s.pending.is_empty() {
        out.retain(|step| step.kind == StepKind::Trigger);
    }
    out
}
fn priority(s: &SymbolicState) -> i32 {
    let field = |id| s.cards.iter().any(|c| c.code == id && c.location == 4);
    (if goal(s) { 50000 } else { 0 })
        + (if field(26692769) { 10000 } else { 0 })
        + (if field(58699500) { 2000 } else { 0 })
        + s.cards.iter().filter(|c| c.location == 4).count() as i32 * 100
        + s.pending.iter().filter(|(id, _)| *id == 25538345).count() as i32 * 1200
        + if s
            .cards
            .iter()
            .any(|c| c.code == 25538345 && c.location == 16)
            && s.cards.iter().any(|c| {
                c.location == 16
                    && matches!(c.code, 36426778 | 90432163 | 63821877 | 25542642 | 88544390)
            })
        {
            500
        } else {
            0
        }
}
pub fn propose(
    deck: &Deck,
    hand: &[CardId],
    catalog: &Catalog,
    pack: &KnowledgePack,
    max_plans: usize,
    max_steps: usize,
) -> Result<Proposals, String> {
    pack.validate()?;
    if max_plans == 0 || max_plans > 8 || max_steps == 0 || max_steps > 32 {
        return Err("planner limits: 1..8 proposals, 1..32 steps".into());
    }
    let initial = initial_state(deck, hand, catalog)?;
    let mut frontier = vec![(initial, Vec::<SemanticStep>::new())];
    let mut plans = vec![];
    let mut expansions = 0;
    let mut termination = "exhausted";
    let gaps = deck
        .main
        .iter()
        .chain(&deck.extra)
        .filter(|id| {
            !pack.cards.iter().any(|c| c.card_id == id.0)
                && catalog
                    .get(id)
                    .is_some_and(|c| c.type_flags & 0x20 != 0 || c.type_flags & 6 != 0)
        })
        .map(|id| format!("unknown effect semantics {}", id.0))
        .collect::<BTreeSet<_>>();
    'depth: for _ in 0..max_steps {
        let mut next = vec![];
        for (state, history) in frontier {
            if expansions >= 5000 {
                termination = "symbolic_node_budget";
                break 'depth;
            }
            expansions += 1;
            for step in successors(&state, catalog, pack) {
                // Only reject an exact ancestor cycle; never merge distinct histories.
                if history.iter().any(|s| s.after == step.after) {
                    continue;
                }
                let mut steps = history.clone();
                let after = step.after.clone();
                steps.push(step);
                if goal(&after) {
                    let id = ygo_knowledge::hash(
                        &serde_json::to_vec(&(pack.id(), &steps)).map_err(|e| e.to_string())?,
                    );
                    plans.push(Proposal {
                        id,
                        steps,
                        goal_predicted: true,
                    });
                    if plans.len() >= max_plans {
                        termination = "proposal_budget";
                        break 'depth;
                    }
                } else {
                    next.push((after, steps));
                }
            }
        }
        next.sort_by_cached_key(|(state, history)| {
            let actions: Vec<_> = history
                .iter()
                .map(|s| {
                    (
                        &s.effect_id,
                        &s.source.instance,
                        s.costs.iter().map(|r| &r.instance).collect::<Vec<_>>(),
                        s.targets.iter().map(|r| &r.instance).collect::<Vec<_>>(),
                    )
                })
                .collect();
            (
                std::cmp::Reverse(priority(state)),
                history.len(),
                ygo_knowledge::hash(&serde_json::to_vec(&actions).unwrap()),
            )
        });
        next.truncate(32);
        if next.is_empty() {
            termination = "exhausted";
            break;
        }
        frontier = next;
        termination = "symbolic_depth_budget";
    }
    Ok(Proposals {
        plans,
        expansions,
        termination: termination.into(),
        coverage_gaps: gaps.into_iter().collect(),
    })
}
