//! Curated, source-bound hypotheses, not a second rules engine.
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{collections::BTreeSet, fs, path::Path};
use ygo_domain::Card;
pub const CORE: [u32; 12] = [
    25538345, 36426778, 90432163, 63821877, 88544390, 98827725, 25542642, 32807846, 81439173,
    58699500, 62709239, 26692769,
];
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Truth {
    Yes,
    No,
    Unknown,
}
#[derive(Clone, Debug, Default, Serialize, Deserialize, Eq, PartialEq)]
#[serde(default, deny_unknown_fields)]
pub struct Filter {
    pub ids: Vec<u32>,
    pub excluded: Vec<u32>,
    pub setcodes: Vec<u16>,
    pub type_mask: u32,
    pub level: Option<u32>,
    pub max_level: Option<u32>,
    pub race: Option<u64>,
    pub attribute: Option<u32>,
}
impl Filter {
    pub fn matches(&self, card: Option<&Card>) -> Truth {
        let Some(c) = card else {
            return Truth::Unknown;
        };
        if (self.level.is_some() || self.max_level.is_some()) && c.type_flags & 0x4800000 != 0 {
            return Truth::No;
        }
        let yes = (self.ids.is_empty() || self.ids.contains(&c.id.0))
            && !self.excluded.contains(&c.id.0)
            && (self.setcodes.is_empty()
                || self.setcodes.iter().any(|set| {
                    c.setcodes.iter().any(|actual| {
                        actual & 0xfff == set & 0xfff
                            && (set & 0xf000 == 0 || actual & set & 0xf000 == set & 0xf000)
                    })
                }))
            && (self.type_mask == 0 || c.type_flags & self.type_mask != 0)
            && self.level.map_or(true, |v| c.level == v)
            && self.max_level.map_or(true, |v| c.level <= v)
            && self.race.map_or(true, |v| c.race == v)
            && self.attribute.map_or(true, |v| c.attribute == v);
        if yes {
            Truth::Yes
        } else {
            Truth::No
        }
    }
}
#[derive(Clone, Copy, Debug, Serialize, Deserialize, Eq, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum Rule {
    ScaleMill,
    ScaleRevive,
    BootsSummon,
    BootsSearch,
    CloakSearch,
    GlovesMill,
    GreavesSummon,
    GreavesRevive,
    Brigandine,
    FogRevive,
    Rota,
    Fool,
    CherubiniMill,
    RustyMillSet,
    BreakRevive,
    BreakDestroy,
    AshNegate,
    Unsupported,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Effect {
    pub id: String,
    pub description_index: Option<u64>,
    pub rule: Rule,
    pub supported: bool,
    pub conditions: Vec<String>,
    pub costs: Vec<String>,
    pub candidate_filter: Option<Filter>,
    pub operations: Vec<String>,
    pub trigger: Option<String>,
    pub usage_key: Option<String>,
    pub restrictions: Vec<String>,
    pub evidence_cases: Vec<String>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CardKnowledge {
    pub card_id: u32,
    pub name: String,
    pub text_sha256: String,
    pub script: String,
    pub script_sha256: String,
    pub effects: Vec<Effect>,
}
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KnowledgePack {
    pub schema_version: u16,
    pub profile_version: String,
    pub cdb_sha256: String,
    pub scripts_sha256: String,
    pub evidence_status: String,
    pub cards: Vec<CardKnowledge>,
}
impl KnowledgePack {
    /// Source-bound opponent knowledge, kept separate from the original twelve-card pack.
    pub fn ash_source(cdb: &Path, scripts: &Path) -> Result<CardKnowledge, String> {
        let db = Connection::open_with_flags(cdb, OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|e| e.to_string())?;
        let text: String = db
            .query_row("SELECT desc FROM texts WHERE id=14558127", [], |r| r.get(0))
            .map_err(|e| e.to_string())?;
        let script = "official/c14558127.lua";
        Ok(CardKnowledge { card_id:14558127, name:"Ash Blossom & Joyous Spring".into(), text_sha256:hash(text.as_bytes()), script:script.into(), script_sha256:hash(&fs::read(scripts.join(script)).map_err(|e|e.to_string())?), effects:vec![Effect {
            id:"14558127:negate".into(), description_index:Some(0), rule:Rule::AshNegate, supported:true,
            conditions:vec!["引擎提供可响应的手牌快速效果；目标连锁包含从牌库加入手牌、特殊召唤或送墓等脚本要求的操作".into()],
            costs:vec!["弃掉自身；无效不退还双方费用".into()], candidate_filter:None,
            operations:vec!["Duel.NegateEffect：无效效果，不无效发动，不破坏发动源".into()],
            trigger:Some("EVENT_CHAINING；首版仅响应 Torn Scales 第一次送墓".into()), usage_key:Some("player:1:14558127:negate".into()),
            restrictions:vec!["每个玩家同名一回合一次；不因 Cherubini 的费用送墓而合法响应".into()],
            evidence_cases:vec!["ash-scales-positive".into(),"ash-cherubini-negative".into()],
        }] })
    }
    pub fn explain_catalog(
        &self,
        id: u32,
        catalog: &ygo_domain::Catalog,
    ) -> Result<serde_json::Value, String> {
        let mut result = self.explain(id)?;
        let c = self.card(id).ok_or("card outside curated coverage")?;
        let candidates:Vec<_>=c.effects.iter().filter_map(|e|e.candidate_filter.as_ref().map(|filter| {
            let deck_source=matches!(e.rule,Rule::ScaleMill|Rule::BootsSearch|Rule::CloakSearch|Rule::GlovesMill|Rule::Rota|Rule::Fool|Rule::CherubiniMill|Rule::RustyMillSet);
            let cards:Vec<_>=catalog.values().filter(|c|filter.matches(Some(c))==Truth::Yes && (!deck_source || c.type_flags&0x4802040==0)).map(|c|serde_json::json!({"card_id":c.id.0,"name":c.name,"has_curated_semantics":self.card(c.id.0).is_some()})).collect();
            serde_json::json!({"effect_id":e.id,"cards":cards,"scope":"目录过滤结果；实际候选仍受牌库剩余数量、局面及引擎限制"})
        })).collect();
        let links = result["conditional_links"].as_array_mut().unwrap();
        links.retain(|link| {
            let from = link["from"].as_str().and_then(|id| self.effect(id));
            let to = link["to"]
                .as_str()
                .and_then(|id| id.split(':').next())
                .and_then(|id| id.parse::<u32>().ok());
            from.and_then(|e| e.candidate_filter.as_ref())
                .zip(to)
                .is_some_and(|(filter, id)| {
                    filter.matches(catalog.get(&ygo_domain::CardId(id))) == Truth::Yes
                })
        });
        result["catalog_candidates"] = serde_json::Value::Array(candidates);
        Ok(result)
    }
    pub fn builtin() -> Result<Self, String> {
        Self::read(Path::new(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/../../knowledge/phantom-v1.json"
        )))
    }
    pub fn read(path: &Path) -> Result<Self, String> {
        let p: Self = serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        p.validate()?;
        Ok(p)
    }
    pub fn id(&self) -> String {
        format!(
            "knowledge-{}",
            hash(&serde_json::to_vec(self).expect("serializable knowledge"))
        )
    }
    pub fn effect(&self, id: &str) -> Option<&Effect> {
        self.cards
            .iter()
            .flat_map(|c| &c.effects)
            .find(|e| e.id == id)
    }
    pub fn card(&self, id: u32) -> Option<&CardKnowledge> {
        self.cards.iter().find(|c| c.card_id == id)
    }
    pub fn validate(&self) -> Result<(), String> {
        let registry: Vec<serde_json::Value> =
            serde_json::from_str(if self.profile_version == "phantom-v2" {
                include_str!("../../../tests/fixtures/phantom-v2.semantic-cases.json")
            } else {
                include_str!("../../../tests/fixtures/phantom.semantic-cases.json")
            })
            .map_err(|e| e.to_string())?;
        let digest = |s: &str| {
            s.len() == 64
                && s.bytes()
                    .all(|b| b.is_ascii_hexdigit() && !b.is_ascii_uppercase())
        };
        if self.schema_version != 1
            || !matches!(self.profile_version.as_str(), "phantom-v1" | "phantom-v2")
            || self.evidence_status != "curated_hypotheses"
            || !digest(&self.cdb_sha256)
            || !digest(&self.scripts_sha256)
        {
            return Err("invalid knowledge provenance/version".into());
        }
        let mut cards = BTreeSet::new();
        let mut effects = BTreeSet::new();
        for c in &self.cards {
            if !cards.insert(c.card_id)
                || c.name.is_empty()
                || c.script != format!("official/c{}.lua", c.card_id)
                || !digest(&c.script_sha256)
                || !digest(&c.text_sha256)
                || c.effects.is_empty()
            {
                return Err("invalid card source/reference".into());
            }
            for e in &c.effects {
                if e.evidence_cases.iter().any(|id| {
                    !registry
                        .iter()
                        .any(|case| case["case_id"] == *id && case["effect_id"] == e.id)
                }) {
                    return Err("unknown effect test evidence reference".into());
                }
                if !effects.insert(e.id.clone())
                    || !e.id.starts_with(&format!("{}:", c.card_id))
                    || e.conditions.is_empty()
                    || e.operations.is_empty()
                    || e.supported == (e.rule == Rule::Unsupported)
                    || (e.supported && e.evidence_cases.is_empty())
                {
                    return Err("invalid effect coverage/reference".into());
                }
            }
        }
        if cards != CORE.into_iter().collect() {
            return Err("knowledge requires the fixed twelve-card coverage set".into());
        }
        Ok(())
    }
    pub fn validate_sources(
        &self,
        cdb: &Path,
        scripts: &Path,
        manifest: &Path,
    ) -> Result<(), String> {
        self.validate()?;
        if hash(&fs::read(cdb).map_err(|e| e.to_string())?) != self.cdb_sha256
            || hash(&fs::read(manifest).map_err(|e| e.to_string())?) != self.scripts_sha256
        {
            return Err("knowledge asset hash mismatch".into());
        }
        let db = Connection::open_with_flags(cdb, OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|e| e.to_string())?;
        for c in &self.cards {
            let text: String = db
                .query_row("SELECT desc FROM texts WHERE id=?", [c.card_id], |r| {
                    r.get(0)
                })
                .map_err(|e| e.to_string())?;
            if hash(text.as_bytes()) != c.text_sha256
                || hash(&fs::read(scripts.join(&c.script)).map_err(|e| e.to_string())?)
                    != c.script_sha256
            {
                return Err(format!("knowledge source changed for {}", c.card_id));
            }
        }
        Ok(())
    }
    pub fn explain(&self, id: u32) -> Result<serde_json::Value, String> {
        let c = self.card(id).ok_or("card outside curated coverage")?;
        let mut links = vec![];
        for e in c.effects.iter().filter(|e| {
            matches!(
                e.rule,
                Rule::ScaleMill
                    | Rule::GlovesMill
                    | Rule::Fool
                    | Rule::CherubiniMill
                    | Rule::RustyMillSet
            )
        }) {
            for next in self
                .cards
                .iter()
                .filter(|c| c.card_id != id)
                .flat_map(|c| &c.effects)
                .filter(|e| {
                    matches!(
                        e.rule,
                        Rule::BootsSearch
                            | Rule::CloakSearch
                            | Rule::GlovesMill
                            | Rule::FogRevive
                            | Rule::GreavesRevive
                    )
                })
            {
                links.push(serde_json::json!({"from":e.id,"to":next.id,"relation":"potential_grave_resource","conditions":"送墓对象须满足过滤器；后续主动效果需确认区域、费用、次数和目标，不是送墓自动触发"}));
            }
        }
        Ok(
            serde_json::json!({"knowledge_id":self.id(),"evidence_status":self.evidence_status,"card":c,"conditional_links":links}),
        )
    }
}
pub fn validate_builtin() -> Result<(), String> {
    KnowledgePack::builtin()?.validate()
}
