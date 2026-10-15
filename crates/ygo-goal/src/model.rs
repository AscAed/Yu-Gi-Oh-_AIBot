use crate::Truth;
use serde::{Deserialize, Serialize};
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(default, deny_unknown_fields)]
pub struct Filter {
    pub codes: Vec<u32>,
    pub player: u8,
    pub locations: Vec<u8>,
    pub position_mask: Option<u32>,
    pub instance: Option<String>,
    pub level: Option<u32>,
    pub rank: Option<u32>,
    pub proper_xyz: Option<bool>,
    pub materials_min: Option<usize>,
    pub material_codes: Vec<u32>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Gain {
    pub id: String,
    pub filter: Filter,
    pub min_delta: i64,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum Expr {
    All {
        args: Vec<Expr>,
    },
    Any {
        args: Vec<Expr>,
    },
    Not {
        arg: Box<Expr>,
    },
    Count {
        filter: Filter,
        min: usize,
        #[serde(default)]
        max: Option<usize>,
    },
    History {
        kind: String,
        #[serde(default)]
        filter: Filter,
        #[serde(default)]
        effect_id: Option<String>,
        #[serde(default)]
        reason_mask: Option<u32>,
        min: usize,
        #[serde(default)]
        max: Option<usize>,
    },
    Available {
        effect_id: String,
        filter: Filter,
        window: String,
    },
    Continuation {
        goal: Box<Expr>,
        #[serde(default)]
        gains: Vec<Gain>,
        #[serde(default)]
        max_steps: Option<usize>,
    },
}
fn four() -> usize {
    4
}
fn eight() -> usize {
    8
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Goal {
    pub version: u16,
    pub expr: Expr,
    #[serde(default = "four")]
    pub continuation_steps: usize,
    #[serde(default = "eight")]
    pub max_aux_candidates: usize,
    #[serde(default)]
    pub gain_order: Vec<String>,
}
impl Goal {
    pub fn validate(&self) -> Result<(), String> {
        if self.version != 1
            || !(1..=8).contains(&self.continuation_steps)
            || !(1..=8).contains(&self.max_aux_candidates)
        {
            return Err("invalid goal version/limits".into());
        }
        let mut nodes = 0;
        let mut gains = BTreeSet::new();
        fn walk(
            e: &Expr,
            depth: usize,
            nested: bool,
            nodes: &mut usize,
            gains: &mut BTreeSet<String>,
        ) -> Result<(), String> {
            *nodes += 1;
            if depth > 8 || *nodes > 64 {
                return Err("goal exceeds 64 nodes/8 levels".into());
            }
            let check_filter = |f: &Filter| -> Result<(), String> {
                if f.codes.len() > 120
                    || f.locations.len() > 7
                    || f.material_codes.len() > 60
                    || f.player > 1
                    || f.codes.contains(&0)
                    || f.locations
                        .iter()
                        .any(|z| !matches!(z, 1 | 2 | 4 | 8 | 16 | 32 | 64))
                    || f.position_mask.is_some_and(|m| m == 0 || m & !15 != 0)
                    || f.materials_min.is_some_and(|n| n > 60)
                {
                    return Err("invalid goal filter".into());
                }
                Ok(())
            };
            match e {
                Expr::All { args } | Expr::Any { args } => {
                    if args.is_empty() {
                        return Err("empty boolean goal".into());
                    }
                    for x in args {
                        walk(x, depth + 1, nested, nodes, gains)?;
                    }
                }
                Expr::Not { arg } => walk(arg, depth + 1, nested, nodes, gains)?,
                Expr::Count { filter, min, max } => {
                    check_filter(filter)?;
                    if *min > 120 || max.is_some_and(|m| m < *min || m > 120) {
                        return Err("invalid count range".into());
                    }
                }
                Expr::History {
                    kind,
                    filter,
                    min,
                    max,
                    ..
                } => {
                    check_filter(filter)?;
                    if ![
                        "normal_summon",
                        "special_summon",
                        "link_summon",
                        "xyz_summon",
                        "destroyed",
                        "sent_to_grave",
                        "effect_resolved",
                    ]
                    .contains(&kind.as_str())
                        || max.is_some_and(|m| m < *min)
                    {
                        return Err("invalid history goal".into());
                    }
                }
                Expr::Available {
                    filter,
                    effect_id,
                    window,
                } => {
                    check_filter(filter)?;
                    if nested || effect_id.is_empty() || window.is_empty() {
                        return Err("invalid/nested availability goal".into());
                    }
                }
                Expr::Continuation {
                    goal,
                    gains: gs,
                    max_steps,
                } => {
                    *nodes += gs.len();
                    if *nodes > 64 {
                        return Err("goal exceeds 64 nodes including gain predicates".into());
                    }
                    if nested || max_steps.is_some_and(|n| !(1..=8).contains(&n)) {
                        return Err("invalid/nested continuation".into());
                    }
                    for g in gs {
                        check_filter(&g.filter)?;
                        if g.id.is_empty() || !gains.insert(g.id.clone()) {
                            return Err("duplicate/empty gain ID".into());
                        }
                    }
                    walk(goal, depth + 1, true, nodes, gains)?;
                }
            }
            Ok(())
        }
        walk(&self.expr, 1, false, &mut nodes, &mut gains)?;
        let order: BTreeSet<_> = self.gain_order.iter().cloned().collect();
        if order.len() != self.gain_order.len() || order != gains {
            return Err("gain_order must name every gain exactly once".into());
        }
        Ok(())
    }
    pub fn id(&self) -> String {
        let mut normalized = self.clone();
        fn filter(f: &mut Filter) {
            f.codes.sort_unstable();
            f.codes.dedup();
            f.locations.sort_unstable();
            f.locations.dedup();
            f.material_codes.sort_unstable();
        }
        fn visit(e: &mut Expr) {
            match e {
                Expr::All { args } | Expr::Any { args } => {
                    for x in args {
                        visit(x)
                    }
                }
                Expr::Not { arg } => visit(arg),
                Expr::Count { filter: f, .. }
                | Expr::History { filter: f, .. }
                | Expr::Available { filter: f, .. } => filter(f),
                Expr::Continuation { goal, gains, .. } => {
                    visit(goal);
                    for g in gains {
                        filter(&mut g.filter);
                    }
                }
            }
        }
        visit(&mut normalized.expr);
        format!(
            "goal-{}",
            ygo_knowledge::hash(&serde_json::to_vec(&normalized).expect("goal serialization"))
        )
    }
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct FactCard {
    pub instance: String,
    pub identity_known: bool,
    pub type_flags: u32,
    pub code: u32,
    pub player: u8,
    pub location: u8,
    pub sequence: u32,
    pub position: u32,
    pub level: Option<u32>,
    pub rank: Option<u32>,
    pub proper_xyz: Option<bool>,
    pub materials: Vec<u32>,
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct HistoryFact {
    pub kind: String,
    pub card: FactCard,
    pub effect_id: Option<String>,
    pub reason: u32,
    pub reason_complete: bool,
    pub event: u64,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Facts {
    pub known_effects: Vec<String>,
    pub cards: Vec<FactCard>,
    pub history: Vec<HistoryFact>,
    pub history_complete: bool,
}
impl Filter {
    pub fn matches(&self, c: &FactCard) -> Truth {
        if c.player != self.player
            || (!self.codes.is_empty() && !self.codes.contains(&c.code))
            || (!self.locations.is_empty() && !self.locations.contains(&c.location))
        {
            return Truth::No;
        }
        let mut values = vec![];
        if self.level.is_some() {
            if c.type_flags != 0 && (c.type_flags & 1 == 0 || c.type_flags & 0x4800000 != 0) {
                return Truth::No;
            }
            if c.type_flags == 0 {
                values.push(Truth::Unknown);
            }
        }
        if self.rank.is_some() {
            if c.type_flags != 0 && c.type_flags & 0x800000 == 0 {
                return Truth::No;
            }
            if c.type_flags == 0 {
                values.push(Truth::Unknown);
            }
        }
        if let Some(id) = &self.instance {
            values.push(if !c.identity_known {
                Truth::Unknown
            } else if id == &c.instance {
                Truth::Yes
            } else {
                Truth::No
            });
        }
        if let Some(mask) = self.position_mask {
            values.push(if c.position == 0 {
                Truth::Unknown
            } else if c.position & mask != 0 {
                Truth::Yes
            } else {
                Truth::No
            });
        }
        for (wanted, actual) in [(self.level, c.level), (self.rank, c.rank)] {
            if let Some(w) = wanted {
                values.push(actual.map_or(Truth::Unknown, |a| {
                    if w == a {
                        Truth::Yes
                    } else {
                        Truth::No
                    }
                }));
            }
        }
        if let Some(w) = self.proper_xyz {
            values.push(c.proper_xyz.map_or(Truth::Unknown, |a| {
                if w == a {
                    Truth::Yes
                } else {
                    Truth::No
                }
            }));
        }
        if self.materials_min.is_some_and(|n| c.materials.len() < n) {
            return Truth::No;
        }
        let mut mats = c.materials.clone();
        for code in &self.material_codes {
            let Some(i) = mats.iter().position(|c| c == code) else {
                return Truth::No;
            };
            mats.remove(i);
        }
        Truth::all(values)
    }
}
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct Evaluation {
    pub node: String,
    pub result: Truth,
    pub observed: Option<i64>,
    pub matches: Vec<String>,
    pub reason: String,
    pub children: Vec<Evaluation>,
}
/// Conditions for explanation. A negated expression is one condition;
/// its positive operand must never be reported as an objective contribution.
pub fn condition_values(expr: &Expr, value: &Evaluation) -> BTreeMap<String, Truth> {
    match expr {
        Expr::All { args } | Expr::Any { args } => args
            .iter()
            .zip(&value.children)
            .flat_map(|(x, e)| condition_values(x, e))
            .collect(),
        _ => BTreeMap::from([(value.node.clone(), value.result)]),
    }
}
pub fn evaluate(expr: &Expr, facts: &Facts, probes: &BTreeMap<String, Evaluation>) -> Evaluation {
    fn go(e: &Expr, f: &Facts, p: &BTreeMap<String, Evaluation>, path: String) -> Evaluation {
        let mut out = Evaluation {
            node: path.clone(),
            result: Truth::Unknown,
            observed: None,
            matches: vec![],
            reason: String::new(),
            children: vec![],
        };
        match e {
            Expr::All { args } | Expr::Any { args } => {
                out.children = args
                    .iter()
                    .enumerate()
                    .map(|(i, x)| go(x, f, p, format!("{path}/{i}")))
                    .collect();
                out.result = if matches!(e, Expr::All { .. }) {
                    Truth::all(out.children.iter().map(|x| x.result))
                } else {
                    Truth::any(out.children.iter().map(|x| x.result))
                };
            }
            Expr::Not { arg } => {
                let child = go(arg, f, p, format!("{path}/0"));
                out.result = child.result.negate();
                out.children.push(child);
            }
            Expr::Count { filter, min, max } => {
                let xs: Vec<_> = f.cards.iter().map(|c| (c, filter.matches(c))).collect();
                out.matches = xs
                    .iter()
                    .filter(|(_, t)| *t == Truth::Yes)
                    .map(|(c, _)| c.instance.clone())
                    .collect();
                let n = out.matches.len();
                let u = xs.iter().filter(|(_, t)| *t == Truth::Unknown).count();
                out.observed = Some(n as i64);
                out.result = range(n, u, *min, *max);
                out.reason = format!("observed {n}, uncertain {u}, required {min}..{max:?}");
            }
            Expr::History {
                kind,
                filter,
                effect_id,
                reason_mask,
                min,
                max,
            } => {
                if effect_id.as_ref().is_some_and(|id| {
                    !f.known_effects.contains(id)
                        && !f.history.iter().any(|h| h.effect_id.as_ref() == Some(id))
                }) {
                    out.reason = "effect description cannot be bound in the supplied ledger".into();
                    return out;
                }
                let xs: Vec<_> = f
                    .history
                    .iter()
                    .filter(|h| {
                        h.kind == *kind
                            && effect_id
                                .as_ref()
                                .map_or(true, |id| h.effect_id.as_ref() == Some(id))
                    })
                    .map(|h| {
                        let reason = reason_mask.map_or(Truth::Yes, |m| {
                            if h.reason & m == m {
                                Truth::Yes
                            } else if h.reason_complete {
                                Truth::No
                            } else {
                                Truth::Unknown
                            }
                        });
                        (h, Truth::all([filter.matches(&h.card), reason]))
                    })
                    .collect();
                out.matches = xs
                    .iter()
                    .filter(|(_, t)| *t == Truth::Yes)
                    .map(|(h, _)| format!("event:{}:{}", h.event, h.card.instance))
                    .collect();
                let n = out.matches.len();
                let u = if f.history_complete {
                    xs.iter().filter(|(_, t)| *t == Truth::Unknown).count()
                } else {
                    usize::MAX / 2
                };
                out.observed = Some(n as i64);
                out.result = range(n, u, *min, *max);
                out.reason = "history count uses the supplied ledger; its evidence scope is recorded by the owner".into();
            }
            Expr::Available { .. } | Expr::Continuation { .. } => {
                if let Some(v) = p.get(&path) {
                    return v.clone();
                }
                out.reason = "requires an engine witness at the main-end window".into();
            }
        }
        out
    }
    go(expr, facts, probes, "/goal".into())
}
fn range(n: usize, u: usize, min: usize, max: Option<usize>) -> Truth {
    if max.is_some_and(|m| n > m) || n.saturating_add(u) < min {
        Truth::No
    } else if n >= min && max.map_or(true, |m| n.saturating_add(u) <= m) {
        Truth::Yes
    } else {
        Truth::Unknown
    }
}
pub fn count(f: &Filter, facts: &Facts) -> Option<i64> {
    let xs: Vec<_> = facts.cards.iter().map(|c| f.matches(c)).collect();
    if xs.contains(&Truth::Unknown) {
        None
    } else {
        Some(xs.iter().filter(|t| **t == Truth::Yes).count() as i64)
    }
}
pub fn probe_nodes(e: &Expr) -> Vec<(String, &Expr)> {
    fn visit<'a>(e: &'a Expr, path: String, out: &mut Vec<(String, &'a Expr)>) {
        match e {
            Expr::All { args } | Expr::Any { args } => {
                for (i, x) in args.iter().enumerate() {
                    visit(x, format!("{path}/{i}"), out)
                }
            }
            Expr::Not { arg } => visit(arg, format!("{path}/0"), out),
            Expr::Available { .. } | Expr::Continuation { .. } => out.push((path, e)),
            _ => {}
        }
    }
    let mut out = vec![];
    visit(e, "/goal".into(), &mut out);
    out
}
