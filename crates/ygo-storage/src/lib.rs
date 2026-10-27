use serde::{Deserialize, Serialize};
use std::{fs, io, path::PathBuf};
use ygo_domain::Banlist;
mod import;
pub use import::*;
mod deck_drafts;
pub use deck_drafts::{
    publish_deck_document, read_deck_document, secure_random_hex, DeckDraftStore, StoredDeckDraft,
};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SnapshotMetadata {
    pub source: String,
    pub version: String,
    pub kind: String,
}

impl SnapshotMetadata {
    pub fn new(
        source: impl Into<String>,
        version: impl Into<String>,
        kind: impl Into<String>,
    ) -> Self {
        Self {
            source: source.into(),
            version: version.into(),
            kind: kind.into(),
        }
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct BanlistSnapshot {
    pub metadata: SnapshotMetadata,
    pub banlist: Banlist,
}

pub trait BanlistProvider {
    fn save_banlist(&self, banlist: &Banlist, metadata: &SnapshotMetadata) -> io::Result<()>;
    fn load_banlist(&self, version: &str) -> io::Result<Option<BanlistSnapshot>>;
}

pub struct JsonSnapshotStore {
    root: PathBuf,
}

impl JsonSnapshotStore {
    pub fn new(root: PathBuf) -> Self {
        Self { root }
    }
    fn path(&self, version: &str) -> PathBuf {
        self.root.join(format!("banlist-{version}.json"))
    }
}

impl BanlistProvider for JsonSnapshotStore {
    fn save_banlist(&self, banlist: &Banlist, metadata: &SnapshotMetadata) -> io::Result<()> {
        fs::create_dir_all(&self.root)?;
        let snapshot = BanlistSnapshot {
            metadata: metadata.clone(),
            banlist: banlist.clone(),
        };
        let data = serde_json::to_vec_pretty(&snapshot).map_err(io::Error::other)?;
        fs::write(self.path(&banlist.version), data)
    }

    fn load_banlist(&self, version: &str) -> io::Result<Option<BanlistSnapshot>> {
        let path = self.path(version);
        if !path.is_file() {
            return Ok(None);
        }
        let data = fs::read(path)?;
        serde_json::from_slice(&data)
            .map(Some)
            .map_err(io::Error::other)
    }
}
