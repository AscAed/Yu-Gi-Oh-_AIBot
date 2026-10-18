use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeMap,
    fs,
    path::{Path, PathBuf},
};
use ygo_domain::{Banlist, Card, CardId, CardKind, Catalog, Limit};
pub fn hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
pub fn file_hash(path: &Path) -> Result<String, String> {
    fs::read(path).map(|b| hash(&b)).map_err(|e| e.to_string())
}
pub fn validate_date(date: &str) -> Result<(), String> {
    let b = date.as_bytes();
    if b.len() != 10
        || !b.iter().enumerate().all(|(i, c)| {
            if i == 4 || i == 7 {
                *c == b'-'
            } else {
                c.is_ascii_digit()
            }
        })
    {
        return Err("date must be YYYY-MM-DD".into());
    }
    let y = date[..4].parse::<u32>().map_err(|e| e.to_string())?;
    let m = date[5..7].parse::<usize>().map_err(|e| e.to_string())?;
    let d = date[8..].parse::<u32>().map_err(|e| e.to_string())?;
    let leap = y % 4 == 0 && (y % 100 != 0 || y % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    if y == 0 || !(1..=12).contains(&m) || d == 0 || d > days[m - 1] {
        return Err("invalid calendar date".into());
    }
    Ok(())
}
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct DataSnapshot<T> {
    pub id: String,
    pub schema_version: u16,
    pub source: String,
    pub source_version: String,
    pub source_sha256: String,
    pub effective_date: Option<String>,
    pub retrieved_at: String,
    pub license: String,
    pub normalizer_version: String,
    pub data: T,
}
#[derive(Clone)]
pub struct SnapshotStore {
    pub root: PathBuf,
}
impl SnapshotStore {
    pub fn new(root: PathBuf) -> Self {
        Self { root }
    }
    fn save<T: Serialize + serde::de::DeserializeOwned>(
        &self,
        kind: &str,
        data: T,
        source: &str,
        version: &str,
        raw_hash: String,
        date: Option<String>,
    ) -> Result<DataSnapshot<T>, String> {
        let content = serde_json::to_vec(&data).map_err(|e| e.to_string())?;
        let provenance = serde_json::to_vec(&(
            kind,
            source,
            version,
            &raw_hash,
            &date,
            "normalizer-v1",
            &content,
        ))
        .map_err(|e| e.to_string())?;
        let id = format!("{kind}-{}", hash(&provenance));
        let snapshot = DataSnapshot {
            id: id.clone(),
            schema_version: 2,
            source: source.into(),
            source_version: version.into(),
            source_sha256: raw_hash,
            effective_date: date,
            retrieved_at: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_secs()
                .to_string(),
            license: "local-only; consult source notices".into(),
            normalizer_version: "normalizer-v1".into(),
            data,
        };
        fs::create_dir_all(&self.root).map_err(|e| e.to_string())?;
        let path = self.root.join(format!("{id}.json"));
        if path.exists() {
            return self.load(&id);
        }
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)
            .map_err(|e| e.to_string())?;
        serde_json::to_writer_pretty(&mut file, &snapshot).map_err(|e| e.to_string())?;
        Ok(snapshot)
    }
    pub fn load<T: serde::de::DeserializeOwned + Serialize>(
        &self,
        id: &str,
    ) -> Result<DataSnapshot<T>, String> {
        let (kind, digest) = id.split_once('-').ok_or("invalid snapshot ID")?;
        if !matches!(kind, "catalog" | "banlist")
            || digest.len() != 64
            || !digest.bytes().all(|b| b.is_ascii_hexdigit())
        {
            return Err("invalid snapshot ID".into());
        }
        let s: DataSnapshot<T> = serde_json::from_slice(
            &fs::read(self.root.join(format!("{id}.json"))).map_err(|e| e.to_string())?,
        )
        .map_err(|e| e.to_string())?;
        let content = serde_json::to_vec(&s.data).map_err(|e| e.to_string())?;
        let provenance = serde_json::to_vec(&(
            kind,
            &s.source,
            &s.source_version,
            &s.source_sha256,
            &s.effective_date,
            &s.normalizer_version,
            &content,
        ))
        .map_err(|e| e.to_string())?;
        if s.id != id || hash(&provenance) != digest || s.schema_version != 2 {
            return Err("snapshot hash/version mismatch".into());
        }
        Ok(s)
    }
    pub fn catalog(&self, id: &str) -> Result<DataSnapshot<Catalog>, String> {
        self.load(id)
    }
    pub fn banlist(&self, id: &str) -> Result<DataSnapshot<Banlist>, String> {
        self.load(id)
    }
    pub fn latest_ocg(&self, as_of: &str) -> Result<DataSnapshot<Banlist>, String> {
        validate_date(as_of)?;
        let mut found = Vec::new();
        for e in fs::read_dir(&self.root).map_err(|e| e.to_string())? {
            let name = e
                .map_err(|e| e.to_string())?
                .file_name()
                .to_string_lossy()
                .into_owned();
            if let Some(id) = name
                .strip_suffix(".json")
                .filter(|s| s.starts_with("banlist-"))
            {
                let s = self.banlist(id)?;
                if s.data.region == "OCG" && s.effective_date.as_deref().is_some_and(|d| d <= as_of)
                {
                    found.push(s);
                }
            }
        }
        found.sort_by(|a, b| {
            a.effective_date
                .cmp(&b.effective_date)
                .then_with(|| a.id.cmp(&b.id))
        });
        found
            .pop()
            .ok_or_else(|| "no effective OCG snapshot".into())
    }
    pub fn import_catalog(&self, path: &Path) -> Result<DataSnapshot<Catalog>, String> {
        if path.file_name().and_then(|s| s.to_str()) != Some("cards.cdb") {
            return Err("only official cards.cdb is supported".into());
        }
        let raw_hash = file_hash(path)?;
        let c = Connection::open_with_flags(path, OpenFlags::SQLITE_OPEN_READ_ONLY)
            .map_err(|e| e.to_string())?;
        let mut q=c.prepare("SELECT d.id,t.name,d.alias,d.type,d.setcode,d.level,d.attribute,d.race,d.atk,d.def FROM datas d JOIN texts t ON t.id=d.id WHERE (d.ot & 1)!=0 AND (d.type & 134217728)=0 ORDER BY d.id").map_err(|e|e.to_string())?;
        let cards = q
            .query_map([], |r| {
                let bits = r.get::<_, u32>(3)?;
                let sc = r.get::<_, i64>(4)? as u64;
                let packed = r.get::<_, u32>(5)?;
                Ok(Card {
                    id: CardId(r.get(0)?),
                    name: r.get(1)?,
                    alias: r.get(2)?,
                    type_flags: bits,
                    setcodes: (0..4)
                        .map(|n| ((sc >> (n * 16)) & 0xffff) as u16)
                        .filter(|n| *n != 0)
                        .collect(),
                    kind: if bits & 2 != 0 {
                        CardKind::Spell
                    } else if bits & 4 != 0 {
                        CardKind::Trap
                    } else {
                        CardKind::Monster
                    },
                    level: packed & 0xff,
                    lscale: (packed >> 24) & 0xff,
                    rscale: (packed >> 16) & 0xff,
                    attribute: r.get(6)?,
                    race: r.get::<_, i64>(7)? as u64,
                    attack: r.get(8)?,
                    defense: if bits & 0x4000000 != 0 { 0 } else { r.get(9)? },
                    link_marker: if bits & 0x4000000 != 0 { r.get(9)? } else { 0 },
                    archetypes: Vec::new(),
                })
            })
            .map_err(|e| e.to_string())?;
        let mut catalog = BTreeMap::new();
        for card in cards {
            let card = card.map_err(|e| e.to_string())?;
            catalog.insert(card.id, card);
        }
        if catalog.is_empty() {
            return Err("empty OCG catalog".into());
        }
        if file_hash(path)? != raw_hash {
            return Err("CDB changed during import".into());
        }
        self.save(
            "catalog",
            catalog,
            "local official cards.cdb",
            "local",
            raw_hash,
            None,
        )
    }
    pub fn import_banlist(
        &self,
        text: &str,
        source: &str,
        commit: &str,
    ) -> Result<DataSnapshot<Banlist>, String> {
        let (date, limits) = parse_ocg_list(text)?;
        self.save(
            "banlist",
            Banlist::ocg(&date, limits),
            source,
            commit,
            hash(text.as_bytes()),
            Some(date),
        )
    }
}
pub fn parse_ocg_list(text: &str) -> Result<(String, BTreeMap<CardId, Limit>), String> {
    let header = text
        .lines()
        .find(|s| s.starts_with('!'))
        .ok_or("list header missing")?;
    let stamp = header
        .trim_start_matches('!')
        .strip_suffix(" OCG")
        .ok_or("requires dated OCG list")?;
    let (year, month) = stamp.split_once('.').ok_or("invalid date")?;
    let year = year.parse::<u32>().map_err(|_| "invalid year")?;
    let month = month.parse::<u32>().map_err(|_| "invalid month")?;
    if !(2000..=2100).contains(&year) || !(1..=12).contains(&month) {
        return Err("invalid effective date".into());
    }
    let mut limits = BTreeMap::new();
    for line in text
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty() && !s.starts_with(['#', '!']))
    {
        let mut tokens = line.split_whitespace();
        let id = tokens
            .next()
            .ok_or("missing ID")?
            .parse::<u32>()
            .map_err(|_| "invalid ID")?;
        let n = tokens
            .next()
            .ok_or("missing limit")?
            .parse::<u8>()
            .map_err(|_| "invalid limit")?;
        let limit = match n {
            0 => Limit::Forbidden,
            1 => Limit::Limited,
            2 => Limit::SemiLimited,
            3 => Limit::Unlimited,
            _ => return Err("invalid limit".into()),
        };
        if id == 0 || limits.insert(CardId(id), limit).is_some() {
            return Err("zero or duplicate card ID".into());
        }
    }
    if limits.is_empty() {
        return Err("empty banlist".into());
    }
    Ok((format!("{year:04}-{month:02}-01"), limits))
}
