use serde::{Deserialize, Serialize};
use std::{fs, io, path::PathBuf};
use ygo_domain::Banlist;
mod import;
pub use import::*;
mod deck_drafts;
pub use deck_drafts::{
    acquire_store_lock, prepare_store_directory, publish_deck_document, publish_exclusive_file,
    read_deck_document, safe_store_metadata, secure_random_hex, DeckDraftStore, ExclusiveStoreLock,
    StoredDeckDraft,
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
    fn path(&self, version: &str) -> io::Result<PathBuf> {
        let mut bytes = version.bytes();
        let valid_start = bytes
            .next()
            .is_some_and(|byte| byte.is_ascii_alphanumeric());
        if !valid_start
            || version.len() > 128
            || !bytes.all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "banlist version must be a single ASCII identifier",
            ));
        }
        Ok(self.root.join(format!("banlist-{version}.json")))
    }

    fn reject_unsafe_destination(path: &std::path::Path) -> io::Result<()> {
        match fs::symlink_metadata(path) {
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
                Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "banlist snapshot destination is not a regular file",
                ))
            }
            Ok(_) => Ok(()),
            Err(error) if error.kind() == io::ErrorKind::NotFound => Ok(()),
            Err(error) => Err(error),
        }
    }
}

impl BanlistProvider for JsonSnapshotStore {
    fn save_banlist(&self, banlist: &Banlist, metadata: &SnapshotMetadata) -> io::Result<()> {
        let path = self.path(&banlist.version)?;
        fs::create_dir_all(&self.root)?;
        Self::reject_unsafe_destination(&path)?;
        let snapshot = BanlistSnapshot {
            metadata: metadata.clone(),
            banlist: banlist.clone(),
        };
        let data = serde_json::to_vec_pretty(&snapshot).map_err(io::Error::other)?;
        fs::write(path, data)
    }

    fn load_banlist(&self, version: &str) -> io::Result<Option<BanlistSnapshot>> {
        let path = self.path(version)?;
        match fs::symlink_metadata(&path) {
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_file() => {
                return Err(io::Error::new(
                    io::ErrorKind::InvalidInput,
                    "banlist snapshot source is not a regular file",
                ));
            }
            Ok(_) => {}
            Err(error) if error.kind() == io::ErrorKind::NotFound => return Ok(None),
            Err(error) => return Err(error),
        }
        let data = fs::read(path)?;
        serde_json::from_slice(&data)
            .map(Some)
            .map_err(io::Error::other)
    }
}
