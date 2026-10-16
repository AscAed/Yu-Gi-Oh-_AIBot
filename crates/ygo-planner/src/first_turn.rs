//! First-turn causal transitions. These are predictions, never native evidence.
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};
use ygo_domain::{CardId, Catalog};
use ygo_engine_adapter::{FirstTurnPublicState, StateCard};
use ygo_knowledge::{
    first_turn::{FirstTurnKnowledge, FirstTurnRule, Operation, Selection},
    Truth,
};

const IMPLEMENTED: [&str; 6] = [
    "83566725:empty_field_special",
    "83566725:deck_set",
    "85257384:trap_monster_special",
    "78449284:two_dark_level_three",
    "78449284:deck_special",
    "46072770:monster_search",
];

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KnownInstance {
    pub id: String,
    pub card: StateCard,
    pub printed: PrintedAttributes,
    pub host: Option<String>,
    pub epoch: u64,
    pub set_this_turn: Option<bool>,
    pub leave_field_banish: Option<bool>,
    pub proper_xyz: Option<bool>,
    pub rank_as_level: Option<bool>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PrintedAttributes {
    type_flags: u32,
    level: Option<u32>,
    rank: Option<u32>,
    attribute: Option<u32>,
    race: Option<u64>,
    attack: i32,
    defense: i32,
}
impl PrintedAttributes {
    fn for_catalog(base: &ygo_domain::Card) -> Self {
        let monster = base.type_flags & 1 != 0;
        let xyz = base.type_flags & 0x800000 != 0;
        let link = base.type_flags & 0x4000000 != 0;
        Self {
            type_flags: base.type_flags,
            level: Some(if monster && !xyz && !link {
                base.level
            } else {
                0
            }),
            rank: Some(if xyz { base.level } else { 0 }),
            attribute: Some(if monster { base.attribute } else { 0 }),
            race: Some(if monster { base.race } else { 0 }),
            attack: if monster { base.attack } else { 0 },
            defense: if monster && !link { base.defense } else { 0 },
        }
    }
    fn from(card: &StateCard) -> Self {
        Self {
            type_flags: card.type_flags,
            level: card.level,
            rank: card.rank,
            attribute: card.attribute,
            race: card.race,
            attack: card.attack,
            defense: card.defense,
        }
    }
    fn restore(&self, card: &mut StateCard) {
        card.type_flags = self.type_flags;
        card.level = self.level;
        card.rank = self.rank;
        card.attribute = self.attribute;
        card.race = self.race;
        card.attack = self.attack;
        card.defense = self.defense;
    }
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PendingTrigger {
    pub rule_id: String,
    pub source: String,
    pub eligibility: Truth,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CausalState {
    pub cards: Vec<KnownInstance>,
    /// No unobserved deck sequence or hypothetical deck instance is exposed.
    pub deck_counts: BTreeMap<u32, usize>,
    pub normal_remaining: Option<u8>,
    pub used: BTreeMap<String, usize>,
    pub pending: Vec<PendingTrigger>,
    pub special_allowed: Option<bool>,
    pub dark_only: Option<bool>,
    pub next_entity: u64,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SemanticSelection {
    pub role: String,
    pub stage: String,
    pub card_id: u32,
    pub instance: Option<String>,
    pub from: u8,
    pub host: Option<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Transition {
    pub kind: TransitionKind,
    pub rule_id: String,
    pub source: String,
    pub selections: Vec<SemanticSelection>,
    pub requirements: Vec<String>,
    pub after_cost: CausalState,
    pub after_resolution: CausalState,
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TransitionKind {
    Procedure,
    Activate,
    Trigger,
    DeclineTrigger,
}
#[derive(Default)]
pub struct Successors {
    pub transitions: Vec<Transition>,
    pub unknowns: Vec<String>,
    pub coverage_gaps: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ResourceComparison {
    pub result: Truth,
    pub differences: Vec<String>,
}
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
struct ResourceRow {
    code: u32,
    player: u8,
    zone: u8,
    slot: Option<u32>,
    position: Option<u32>,
    type_flags: u32,
    level: Option<u32>,
    rank: Option<u32>,
    attribute: Option<u32>,
    race: Option<u64>,
    attack: i32,
    defense: i32,
    materials: Vec<u32>,
}
fn row(card: &StateCard) -> ResourceRow {
    let mut materials = card.overlay.clone();
    materials.sort();
    ResourceRow {
        code: card.code,
        player: card.player,
        zone: card.location,
        slot: if matches!(card.location, 4 | 8) {
            Some(card.sequence)
        } else {
            None
        },
        position: if matches!(card.location, 4 | 8) {
            Some(card.position)
        } else {
            None
        },
        type_flags: card.type_flags,
        level: if card.type_flags & 0x4800000 == 0 {
            card.level
        } else {
            None
        },
        rank: if card.type_flags & 0x800000 != 0 {
            card.rank
        } else {
            None
        },
        attribute: card.attribute,
        race: card.race,
        attack: card.attack,
        defense: card.defense,
        materials,
    }
}
/// Resource projection only: this does not certify instance histories, usage or restrictions.
pub fn compare_resources(
    predicted: &CausalState,
    actual: &FirstTurnPublicState,
) -> ResourceComparison {
    let counts = |deck: &BTreeMap<u32, usize>| {
        deck.iter()
            .filter(|(_, n)| **n > 0)
            .map(|(c, n)| (*c, *n))
            .collect::<BTreeMap<_, _>>()
    };
    let mut differences = Vec::new();
    let mut known_mismatch = counts(&predicted.deck_counts) != counts(&actual.own_deck_counts);
    if known_mismatch {
        differences.push("unordered remaining deck counts differ".into());
    }
    let mut expected: Vec<_> = predicted
        .cards
        .iter()
        .filter(|c| c.card.player == 0 && c.card.location != 132)
        .map(|c| row(&c.card))
        .collect();
    let mut observed: Vec<_> = actual
        .visible
        .cards
        .iter()
        .filter(|c| c.player == 0)
        .map(row)
        .collect();
    expected.sort();
    observed.sort();
    if expected.len() != observed.len() {
        known_mismatch = true;
        differences.push("visible own resource counts differ".into());
    }
    let unknown = actual
        .visible
        .cards
        .iter()
        .filter(|c| c.player == 0)
        .any(|c| {
            c.attribute.is_none()
                || c.race.is_none()
                || if c.type_flags & 0x800000 != 0 {
                    c.rank.is_none()
                } else {
                    c.level.is_none()
                }
        });
    if expected != observed {
        differences
            .push("per-card levels, ranks, positions or host material multiset differ".into());
    }
    let shape = |rows: &[ResourceRow]| {
        let mut rows = rows.to_vec();
        for row in &mut rows {
            row.level = None;
            row.rank = None;
            row.attribute = None;
            row.race = None;
        }
        rows.sort();
        rows
    };
    known_mismatch |= shape(&expected) != shape(&observed);
    let result = if known_mismatch {
        Truth::No
    } else if differences.is_empty() {
        if unknown {
            Truth::Unknown
        } else {
            Truth::Yes
        }
    } else if unknown {
        Truth::Unknown
    } else {
        Truth::No
    };
    if unknown {
        differences
            .push("necessary native attributes are unknown; no resource match is certified".into());
    }
    ResourceComparison {
        result,
        differences,
    }
}

impl CausalState {
    pub fn validate(&self, catalog: &Catalog) -> Result<(), String> {
        let mut ids = BTreeSet::new();
        for c in &self.cards {
            if !ids.insert(&c.id)
                || c.card.player > 1
                || ![2, 4, 8, 16, 32, 64, 132].contains(&c.card.location)
            {
                return Err("duplicate instance or invalid resource domain".into());
            }
            let base = catalog
                .get(&CardId(c.card.code))
                .ok_or("missing printed card metadata")?;
            let effective = PrintedAttributes::for_catalog(base);
            if c.printed.type_flags != base.type_flags
                || c.printed
                    .attribute
                    .is_some_and(|v| Some(v) != effective.attribute)
                || c.printed.race.is_some_and(|v| Some(v) != effective.race)
                || c.printed.rank.is_some_and(|v| Some(v) != effective.rank)
                || c.printed.level.is_some_and(|v| Some(v) != effective.level)
                || c.printed.attack != effective.attack
                || c.printed.defense != effective.defense
            {
                return Err("printed source attributes differ from catalog".into());
            }
            if c.card.location == 132 {
                let host = c
                    .host
                    .as_ref()
                    .and_then(|id| lookup(self, id))
                    .ok_or("material lacks a known host instance")?;
                if host.id == c.id
                    || host.card.location != 4
                    || host.card.type_flags & 0x800000 == 0
                {
                    return Err("material host is not a current XYZ instance".into());
                }
            } else if c.host.is_some() {
                return Err("non-material resource retains a host".into());
            }
            let mut children: Vec<_> = self
                .cards
                .iter()
                .filter(|child| child.host.as_deref() == Some(&c.id))
                .map(|child| child.card.code)
                .collect();
            children.sort();
            let mut overlay = c.card.overlay.clone();
            overlay.sort();
            if children != overlay {
                return Err("host material multiset differs from known instances".into());
            }
        }
        Ok(())
    }
    /// Only for the untouched first own main window. Recovery needs event reconstruction.
    pub fn initial(public: &FirstTurnPublicState) -> Result<Self, String> {
        let c = &public.visible;
        if c.turn != 1
            || c.turn_player != 0
            || c.phase != 4
            || c.cards.iter().any(|v| {
                v.location == 1
                    || v.player != 0
                    || v.player == 0 && !matches!(v.location, 2 | 64)
                    || !v.overlay.is_empty()
            })
        {
            return Err(
                "initial causal state requires an untouched public first main window".into(),
            );
        }
        let mut ids = BTreeSet::new();
        let mut cards = Vec::new();
        for card in &c.cards {
            let id = format!(
                "observed:{}:{}:{}:0",
                card.player, card.location, card.sequence
            );
            if !ids.insert(id.clone()) {
                return Err("duplicate public instance slot".into());
            }
            cards.push(KnownInstance {
                id,
                printed: PrintedAttributes::from(card),
                card: card.clone(),
                host: None,
                epoch: 0,
                set_this_turn: Some(false),
                leave_field_banish: Some(false),
                proper_xyz: Some(false),
                rank_as_level: Some(false),
            });
        }
        Ok(Self {
            cards,
            deck_counts: public.own_deck_counts.clone(),
            normal_remaining: Some(1),
            used: BTreeMap::new(),
            pending: vec![],
            special_allowed: Some(true),
            dark_only: Some(false),
            next_entity: 0,
        })
    }
}

pub fn implemented_rules() -> BTreeSet<String> {
    IMPLEMENTED.into_iter().map(str::to_owned).collect()
}
fn own(card: &KnownInstance, zone: u8) -> bool {
    card.card.player == 0 && card.card.location == zone
}
fn faceup(card: &KnownInstance) -> bool {
    card.card.position & 5 != 0
}
fn free_main(s: &CausalState) -> Option<u32> {
    (0..5).find(|seq| !s.cards.iter().any(|c| own(c, 4) && c.card.sequence == *seq))
}
fn free_st(s: &CausalState) -> Option<u32> {
    (0..5).find(|seq| !s.cards.iter().any(|c| own(c, 8) && c.card.sequence == *seq))
}
fn usage_key(rule: &FirstTurnRule, source: &KnownInstance) -> Option<String> {
    rule.usage.key.as_ref().map(|key| {
        if rule.usage.scope == "instance_turn" {
            format!("{key}:{}:{}", source.id, source.epoch)
        } else {
            key.clone()
        }
    })
}
fn available(s: &CausalState, rule: &FirstTurnRule, source: &KnownInstance) -> bool {
    usage_key(rule, source).map_or(true, |key| {
        s.used.get(&key).copied().unwrap_or(0) < rule.usage.limit.unwrap_or(usize::MAX)
    })
}
fn consume(s: &mut CausalState, rule: &FirstTurnRule, source: &KnownInstance) {
    if let Some(key) = usage_key(rule, source) {
        *s.used.entry(key).or_default() += 1;
    }
}
fn lookup<'a>(s: &'a CausalState, id: &str) -> Option<&'a KnownInstance> {
    s.cards.iter().find(|c| c.id == id)
}
fn move_known(s: &mut CausalState, id: &str, zone: u8, position: u32) -> Result<(), String> {
    let old = lookup(s, id).ok_or("missing symbolic source")?.clone();
    let sequence = match zone {
        4 => free_main(s).ok_or("no main zone")?,
        8 => free_st(s).ok_or("no S/T zone")?,
        _ => 0,
    };
    let target = s.cards.iter_mut().find(|c| c.id == id).unwrap();
    if old.card.location == 4 && zone != 4 {
        target.epoch += 1;
        target.proper_xyz = Some(false);
        target.printed.restore(&mut target.card);
    }
    target.card.location =
        if old.card.location == 4 && zone == 16 && old.leave_field_banish == Some(true) {
            32
        } else {
            zone
        };
    target.card.position = position;
    target.card.sequence = sequence;
    target.host = None;
    if zone != 4 {
        target.leave_field_banish = Some(false);
        target.rank_as_level = Some(false);
    }
    if old.card.location == 132 {
        if let Some(host) = old.host {
            let codes: Vec<_> = s
                .cards
                .iter()
                .filter(|c| c.host.as_deref() == Some(&host))
                .map(|c| c.card.code)
                .collect();
            if let Some(h) = s.cards.iter_mut().find(|c| c.id == host) {
                h.card.overlay = codes;
            }
        }
    }
    Ok(())
}
fn deck_card(
    s: &mut CausalState,
    code: u32,
    zone: u8,
    catalog: &Catalog,
) -> Result<String, String> {
    let left = s
        .deck_counts
        .get_mut(&code)
        .ok_or("missing deck candidate")?;
    if *left == 0 {
        return Err("deck candidate exhausted".into());
    }
    *left -= 1;
    let base = catalog.get(&CardId(code)).ok_or("unknown deck candidate")?;
    let sequence = match zone {
        4 => free_main(s).ok_or("no summon zone")?,
        8 => free_st(s).ok_or("no set zone")?,
        _ => s.cards.iter().filter(|c| own(c, zone)).count() as u32,
    };
    s.next_entity += 1;
    let id = format!("revealed:{}:{code}", s.next_entity);
    let effective = PrintedAttributes::for_catalog(base);
    let card = StateCard {
        code,
        player: 0,
        location: zone,
        sequence,
        position: if zone == 8 { 10 } else { 1 },
        type_flags: base.type_flags,
        level: effective.level,
        rank: effective.rank,
        attribute: effective.attribute,
        race: effective.race,
        attack: effective.attack,
        defense: effective.defense,
        ..Default::default()
    };
    let printed = PrintedAttributes::from(&card);
    s.cards.push(KnownInstance {
        id: id.clone(),
        card,
        printed,
        host: None,
        epoch: 0,
        set_this_turn: Some(zone == 8),
        leave_field_banish: Some(false),
        proper_xyz: Some(false),
        rank_as_level: Some(false),
    });
    Ok(id)
}
fn queue_summon(s: &mut CausalState, id: &str, pack: &FirstTurnKnowledge, catalog: &Catalog) {
    let Some(source) = lookup(s, id) else {
        return;
    };
    let source = source.clone();
    let code = source.card.code;
    for rule in &pack.rules {
        if IMPLEMENTED.contains(&rule.id.as_str())
            && rule.card_id == code
            && matches!(
                rule.operation,
                Operation::DeckSet | Operation::SearchMonster
            )
        {
            if !available(s, rule, &source)
                || rule.operation == Operation::DeckSet && free_st(s).is_none()
            {
                continue;
            }
            let Some(selection) = rule.selections.iter().find(|v| v.role == "deck_result") else {
                continue;
            };
            let mut known = false;
            let mut unknown = false;
            for (code, count) in &s.deck_counts {
                if *count == 0 {
                    continue;
                }
                match selection.filter.matches(catalog.get(&CardId(*code))) {
                    Truth::Yes => known = true,
                    Truth::Unknown => unknown = true,
                    Truth::No => {}
                }
            }
            if !known && !unknown {
                continue;
            }
            s.pending.push(PendingTrigger {
                rule_id: rule.id.clone(),
                source: id.into(),
                eligibility: if known { Truth::Yes } else { Truth::Unknown },
            });
        }
    }
}
fn match_selection(c: &KnownInstance, selection: &Selection, catalog: &Catalog) -> Truth {
    if c.card.player != selection.controller || !selection.locations.contains(&c.card.location) {
        return Truth::No;
    }
    if c.card.location == 4 && !faceup(c) {
        return Truth::No;
    }
    let Some(base) = catalog.get(&CardId(c.card.code)) else {
        return Truth::Unknown;
    };
    if selection.filter.attribute.is_some() && c.card.attribute.is_none() {
        return Truth::Unknown;
    }
    if selection.filter.race.is_some() && c.card.race.is_none() {
        return Truth::Unknown;
    }
    if let Some(required) = selection.actual_level {
        let actual = if c.card.type_flags & 0x800000 != 0 {
            match c.rank_as_level {
                Some(true) => c.card.rank,
                Some(false) => return Truth::No,
                None => return Truth::Unknown,
            }
        } else {
            c.card.level
        };
        match actual {
            Some(level) if level == required => {}
            Some(_) => return Truth::No,
            None => return Truth::Unknown,
        }
    }
    let mut actual = base.clone();
    actual.type_flags = c.card.type_flags;
    actual.attribute = c.card.attribute.unwrap_or(base.attribute);
    actual.race = c.card.race.unwrap_or(base.race);
    if let Some(level) = c.card.level {
        actual.level = level;
    }
    selection.filter.matches(Some(&actual))
}
fn deck_options(s: &CausalState, selection: &Selection, catalog: &Catalog) -> Vec<u32> {
    s.deck_counts
        .iter()
        .filter(|(code, count)| {
            **count > 0 && selection.filter.matches(catalog.get(&CardId(**code))) == Truth::Yes
        })
        .map(|(code, _)| *code)
        .collect()
}
fn pick(role: &str, stage: &str, card: &KnownInstance) -> SemanticSelection {
    SemanticSelection {
        role: role.into(),
        stage: stage.into(),
        card_id: card.card.code,
        instance: Some(card.id.clone()),
        from: card.card.location,
        host: card.host.clone(),
    }
}
fn from_deck(code: u32) -> SemanticSelection {
    SemanticSelection {
        role: "deck_result".into(),
        stage: "resolution".into(),
        card_id: code,
        instance: None,
        from: 1,
        host: None,
    }
}
fn emit(
    out: &mut Successors,
    rule: &FirstTurnRule,
    source: &KnownInstance,
    selections: Vec<SemanticSelection>,
    after_cost: CausalState,
    after_resolution: CausalState,
) {
    out.transitions.push(Transition {
        kind: match rule.operation {
            Operation::EmptyFieldSpecial | Operation::XyzProcedure => TransitionKind::Procedure,
            Operation::DeckSet | Operation::SearchMonster => TransitionKind::Trigger,
            _ => TransitionKind::Activate,
        },
        rule_id: rule.id.clone(),
        source: source.id.clone(),
        selections,
        requirements: rule.conditions.clone(),
        after_cost,
        after_resolution,
    });
}
fn summon_allowed(s: &CausalState, attribute: Option<u32>) -> Truth {
    match (s.special_allowed, s.dark_only) {
        (Some(false), _) => Truth::No,
        (None, _) | (_, None) => Truth::Unknown,
        (Some(true), Some(true)) => match attribute {
            Some(32) => Truth::Yes,
            Some(_) => Truth::No,
            None => Truth::Unknown,
        },
        _ => Truth::Yes,
    }
}

/// Enumerate supported causal hypotheses without consulting hidden deck order.
pub fn successors(state: &CausalState, catalog: &Catalog, pack: &FirstTurnKnowledge) -> Successors {
    let mut out = Successors::default();
    if let Err(error) = state.validate(catalog) {
        out.unknowns.push(format!("invalid causal state: {error}"));
        return out;
    }
    for source in state
        .cards
        .iter()
        .filter(|c| c.card.player == 0 && c.host.is_none())
    {
        for rule in pack.rules.iter().filter(|r| {
            r.applicable
                && r.card_id == source.card.code
                && r.source_locations & source.card.location != 0
        }) {
            if !IMPLEMENTED.contains(&rule.id.as_str()) {
                out.coverage_gaps.push(rule.id.clone());
                continue;
            }
            if !available(state, rule, source) {
                continue;
            }
            let trigger = matches!(
                rule.operation,
                Operation::DeckSet | Operation::SearchMonster
            );
            if trigger {
                let pending = state
                    .pending
                    .iter()
                    .find(|p| p.rule_id == rule.id && p.source == source.id);
                let Some(pending) = pending else {
                    continue;
                };
                if pending.eligibility != Truth::Yes {
                    out.unknowns
                        .push(format!("{}: trigger availability unknown", rule.id));
                    continue;
                }
                let mut after = state.clone();
                after
                    .pending
                    .retain(|p| p.rule_id != rule.id || p.source != source.id);
                out.transitions.push(Transition {
                    kind: TransitionKind::DeclineTrigger,
                    rule_id: rule.id.clone(),
                    source: source.id.clone(),
                    selections: vec![],
                    requirements: vec![
                        "optional trigger may be declined without consuming its usage count".into(),
                    ],
                    after_cost: after.clone(),
                    after_resolution: after,
                });
            } else if !state.pending.is_empty() {
                continue;
            }
            match rule.operation {
                Operation::EmptyFieldSpecial => {
                    if state.cards.iter().any(|c| own(c, 4)) || free_main(state).is_none() {
                        continue;
                    }
                    match summon_allowed(state, source.card.attribute) {
                        Truth::Yes => {}
                        Truth::Unknown => {
                            out.unknowns
                                .push(format!("{}: summon restriction unknown", rule.id));
                            continue;
                        }
                        Truth::No => continue,
                    }
                    let mut after = state.clone();
                    consume(&mut after, rule, source);
                    let cost = after.clone();
                    if move_known(&mut after, &source.id, 4, 1).is_err() {
                        continue;
                    }
                    queue_summon(&mut after, &source.id, pack, catalog);
                    emit(&mut out, rule, source, vec![], cost, after);
                }
                Operation::DeckSet | Operation::SearchMonster => {
                    if rule.operation == Operation::DeckSet && free_st(state).is_none() {
                        continue;
                    }
                    let Some(selection) = rule.selections.iter().find(|s| s.role == "deck_result")
                    else {
                        out.unknowns.push(format!("{}: missing selection", rule.id));
                        continue;
                    };
                    for code in deck_options(state, selection, catalog) {
                        let mut after = state.clone();
                        consume(&mut after, rule, source);
                        after
                            .pending
                            .retain(|p| p.source != source.id || p.rule_id != rule.id);
                        let cost = after.clone();
                        let zone = if rule.operation == Operation::DeckSet {
                            8
                        } else {
                            2
                        };
                        if deck_card(&mut after, code, zone, catalog).is_err() {
                            continue;
                        }
                        emit(&mut out, rule, source, vec![from_deck(code)], cost, after);
                    }
                }
                Operation::TrapMonster => {
                    if free_main(state).is_none() {
                        continue;
                    }
                    let same_turn = source.set_this_turn;
                    let permitted = state.cards.iter().any(|c| {
                        c.card.player == 0
                            && matches!(c.card.location, 4 | 16)
                            && faceup(c)
                            && c.card.type_flags & 1 != 0
                            && catalog.get(&CardId(c.card.code)).is_some_and(|base| {
                                base.setcodes
                                    .iter()
                                    .any(|s| s & 0xfff == 0xdb && s & 0xf000 == 0x1000)
                            })
                    });
                    if same_turn == Some(true) && !permitted {
                        continue;
                    }
                    if same_turn.is_none() {
                        out.unknowns.push(format!("{}: set turn unknown", rule.id));
                        continue;
                    }
                    match summon_allowed(state, Some(32)) {
                        Truth::Yes => {}
                        Truth::Unknown => {
                            out.unknowns
                                .push(format!("{}: summon restriction unknown", rule.id));
                            continue;
                        }
                        Truth::No => continue,
                    }
                    let mut after = state.clone();
                    consume(&mut after, rule, source);
                    let cost = after.clone();
                    if move_known(&mut after, &source.id, 4, 4).is_err() {
                        continue;
                    }
                    let card = after.cards.iter_mut().find(|c| c.id == source.id).unwrap();
                    card.card.type_flags = 0x11;
                    card.card.level = Some(3);
                    card.card.rank = None;
                    card.card.attribute = Some(32);
                    card.card.race = Some(1);
                    card.card.attack = 0;
                    card.card.defense = 300;
                    emit(&mut out, rule, source, vec![], cost, after);
                }
                Operation::XyzProcedure => {
                    let Some(selection) = rule.selections.iter().find(|s| s.role == "material")
                    else {
                        continue;
                    };
                    if selection.min != 2 || selection.max != 2 {
                        out.coverage_gaps
                            .push(format!("{}: material arity", rule.id));
                        continue;
                    }
                    let mut materials = Vec::new();
                    for card in &state.cards {
                        match match_selection(card, selection, catalog) {
                            Truth::Yes => materials.push(card),
                            Truth::Unknown => out.unknowns.push(format!(
                                "{}: material {} attributes unknown",
                                rule.id, card.id
                            )),
                            Truth::No => {}
                        }
                    }
                    match summon_allowed(state, source.card.attribute) {
                        Truth::Yes => {}
                        Truth::No => continue,
                        Truth::Unknown => {
                            out.unknowns
                                .push(format!("{}: summon restriction unknown", rule.id));
                            continue;
                        }
                    }
                    for a in 0..materials.len() {
                        for b in a + 1..materials.len() {
                            let pair = [materials[a], materials[b]];
                            let mut after = state.clone();
                            for material in pair {
                                let children: Vec<_> = after
                                    .cards
                                    .iter()
                                    .filter(|c| c.host.as_deref() == Some(&material.id))
                                    .map(|c| c.id.clone())
                                    .collect();
                                for child in children {
                                    move_known(&mut after, &child, 16, 5)
                                        .expect("validated attached material exists");
                                }
                                let c = after
                                    .cards
                                    .iter_mut()
                                    .find(|c| c.id == material.id)
                                    .unwrap();
                                c.printed.restore(&mut c.card);
                                c.epoch += 1;
                                c.card.location = 132;
                                c.host = Some(source.id.clone());
                                c.leave_field_banish = Some(false);
                                c.proper_xyz = Some(false);
                                c.rank_as_level = Some(false);
                            }
                            if move_known(&mut after, &source.id, 4, 1).is_err() {
                                continue;
                            }
                            let host = after.cards.iter_mut().find(|c| c.id == source.id).unwrap();
                            host.card.overlay = pair.iter().map(|c| c.card.code).collect();
                            host.proper_xyz = Some(true);
                            emit(
                                &mut out,
                                rule,
                                source,
                                pair.iter()
                                    .map(|c| pick("material", "procedure", c))
                                    .collect(),
                                state.clone(),
                                after,
                            );
                        }
                    }
                }
                Operation::DeckSpecial => {
                    let Some(selection) = rule.selections.iter().find(|s| s.role == "deck_result")
                    else {
                        continue;
                    };
                    if free_main(state).is_none() {
                        continue;
                    }
                    for material in state
                        .cards
                        .iter()
                        .filter(|c| c.host.as_deref() == Some(&source.id))
                    {
                        for code in deck_options(state, selection, catalog) {
                            match summon_allowed(
                                state,
                                catalog.get(&CardId(code)).map(|c| c.attribute),
                            ) {
                                Truth::Yes => {}
                                Truth::No => continue,
                                Truth::Unknown => {
                                    out.unknowns
                                        .push(format!("{}: summon restriction unknown", rule.id));
                                    continue;
                                }
                            }
                            let mut cost = state.clone();
                            consume(&mut cost, rule, source);
                            if move_known(&mut cost, &material.id, 16, 5).is_err() {
                                continue;
                            }
                            let mut after = cost.clone();
                            let Ok(new) = deck_card(&mut after, code, 4, catalog) else {
                                continue;
                            };
                            queue_summon(&mut after, &new, pack, catalog);
                            emit(
                                &mut out,
                                rule,
                                source,
                                vec![pick("cost", "cost", material), from_deck(code)],
                                cost,
                                after,
                            );
                        }
                    }
                }
                _ => out.coverage_gaps.push(rule.id.clone()),
            }
        }
    }
    out.unknowns.sort();
    out.unknowns.dedup();
    out.coverage_gaps.sort();
    out.coverage_gaps.dedup();
    out.transitions.sort_by_key(|t| {
        (
            t.rule_id.clone(),
            t.source.clone(),
            t.selections
                .iter()
                .map(|s| (s.card_id, s.instance.clone()))
                .collect::<Vec<_>>(),
        )
    });
    out
}
