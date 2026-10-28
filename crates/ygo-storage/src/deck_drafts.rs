use serde::{Deserialize, Serialize};
use std::{
    fs::{self, File, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::Mutex,
};
use ygo_domain::DeckDocumentV1;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct StoredDeckDraft {
    pub id: String,
    pub revision: String,
    pub draft: DeckDocumentV1,
}

/// A directory-scoped draft store. Opening a second writer fails until this
/// value is dropped; individual updates are guarded by content revisions.
pub struct DeckDraftStore {
    root: PathBuf,
    _lock: DirectoryLock,
    operation: Mutex<()>,
}

impl DeckDraftStore {
    pub fn open(root: PathBuf) -> Result<Self, String> {
        fs::create_dir_all(&root).map_err(|error| format!("draft_store_open_failed: {error}"))?;
        let root = root
            .canonicalize()
            .map_err(|error| format!("draft_store_canonicalize_failed: {error}"))?;
        let metadata = fs::symlink_metadata(&root)
            .map_err(|error| format!("draft_store_metadata_failed: {error}"))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err("draft_store_root_not_directory".into());
        }
        let lock_path = root.join(".ygo-workbench.lock");
        let lock_file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(lock_path)
            .map_err(|error| format!("draft_store_lock_open_failed: {error}"))?;
        let lock = DirectoryLock::try_acquire(lock_file)
            .map_err(|error| format!("draft_store_already_locked: {error}"))?;
        Ok(Self {
            root,
            _lock: lock,
            operation: Mutex::new(()),
        })
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    pub fn create(&self, draft: DeckDocumentV1) -> Result<StoredDeckDraft, String> {
        let _guard = self.operation.lock().map_err(|_| "draft_store_poisoned")?;
        draft.validate()?;
        for _ in 0..8 {
            let id = random_hex(16)?;
            let stored = make_stored(id.clone(), draft.clone())?;
            match publish_file(&self.path(&id), &encode_stored(&stored)?, false) {
                Ok(()) => return Ok(stored),
                Err(error) if error == "output_exists" => continue,
                Err(error) => return Err(error),
            }
        }
        Err("draft_id_collision_limit".into())
    }

    pub fn list(&self) -> Result<Vec<StoredDeckDraft>, String> {
        let _guard = self.operation.lock().map_err(|_| "draft_store_poisoned")?;
        let mut output = Vec::new();
        for entry in
            fs::read_dir(&self.root).map_err(|error| format!("draft_store_list_failed: {error}"))?
        {
            let entry = entry.map_err(|error| format!("draft_store_list_failed: {error}"))?;
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.ends_with(".json") {
                continue;
            }
            let id = name.trim_end_matches(".json");
            if !valid_id(id) {
                return Err("draft_store_unmanaged_json_file".into());
            }
            output.push(self.load_unlocked(id)?);
        }
        output.sort_by(|left, right| left.id.cmp(&right.id));
        Ok(output)
    }

    pub fn load(&self, id: &str) -> Result<StoredDeckDraft, String> {
        let _guard = self.operation.lock().map_err(|_| "draft_store_poisoned")?;
        self.load_unlocked(id)
    }

    fn load_unlocked(&self, id: &str) -> Result<StoredDeckDraft, String> {
        let path = self.path(id);
        let metadata =
            fs::symlink_metadata(&path).map_err(|error| format!("draft_not_found: {error}"))?;
        if !metadata.is_file() || metadata.file_type().is_symlink() {
            return Err("draft_file_not_regular".into());
        }
        let bytes = fs::read(path).map_err(|error| format!("draft_read_failed: {error}"))?;
        let stored: StoredDeckDraft = serde_json::from_slice(&bytes)
            .map_err(|error| format!("draft_json_invalid: {error}"))?;
        if stored.id != id || !valid_id(&stored.id) {
            return Err("draft_identity_mismatch".into());
        }
        stored.draft.validate()?;
        if revision(&stored.draft)? != stored.revision {
            return Err("draft_revision_mismatch".into());
        }
        Ok(stored)
    }

    pub fn update(
        &self,
        id: &str,
        expected_revision: &str,
        draft: DeckDocumentV1,
    ) -> Result<StoredDeckDraft, String> {
        let _guard = self.operation.lock().map_err(|_| "draft_store_poisoned")?;
        if !valid_id(id) {
            return Err("draft_id_invalid".into());
        }
        draft.validate()?;
        let current = self.load_unlocked(id)?;
        if current.revision != expected_revision {
            return Err("revision_conflict".into());
        }
        let updated = make_stored(id.to_owned(), draft)?;
        publish_file(&self.path(id), &encode_stored(&updated)?, true)?;
        Ok(updated)
    }

    fn path(&self, id: &str) -> PathBuf {
        if !valid_id(id) {
            return self.root.join(".invalid-draft-id");
        }
        self.root.join(format!("{id}.json"))
    }
}

pub fn read_deck_document(path: &Path) -> Result<DeckDocumentV1, String> {
    let text = fs::read_to_string(path).map_err(|error| format!("{}: {error}", path.display()))?;
    DeckDocumentV1::import_json(&text).map_err(|error| format!("{}: {error}", path.display()))
}

/// Shared safe publisher for the CLI and managed workbench drafts.
pub fn publish_deck_document(
    destination: impl AsRef<Path>,
    bytes: &[u8],
    replace: bool,
) -> Result<(), String> {
    publish_file(destination.as_ref(), bytes, replace).map_err(|error| {
        if error == "output_exists" {
            "deck_draft_output_exists: output already exists; pass --replace to replace it".into()
        } else {
            format!("deck_draft_publish_failed: {error}")
        }
    })
}

fn make_stored(id: String, draft: DeckDocumentV1) -> Result<StoredDeckDraft, String> {
    Ok(StoredDeckDraft {
        id,
        revision: revision(&draft)?,
        draft,
    })
}

fn revision(draft: &DeckDocumentV1) -> Result<String, String> {
    draft.validate()?;
    let bytes = serde_json::to_vec(draft).map_err(|error| error.to_string())?;
    Ok(hash(&bytes))
}

fn encode_stored(stored: &StoredDeckDraft) -> Result<Vec<u8>, String> {
    serde_json::to_vec_pretty(stored).map_err(|error| error.to_string())
}

fn hash(bytes: &[u8]) -> String {
    use sha2::{Digest, Sha256};
    format!("{:x}", Sha256::digest(bytes))
}

fn valid_id(id: &str) -> bool {
    id.len() == 32
        && id
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase())
}

fn random_hex(count: usize) -> Result<String, String> {
    let mut bytes = vec![0u8; count];
    os_random(&mut bytes)?;
    Ok(bytes.iter().map(|byte| format!("{byte:02x}")).collect())
}

pub fn secure_random_hex(count: usize) -> Result<String, String> {
    random_hex(count)
}

fn os_random(bytes: &mut [u8]) -> Result<(), String> {
    #[cfg(unix)]
    {
        use std::io::Read;
        File::open("/dev/urandom")
            .and_then(|mut file| file.read_exact(bytes))
            .map_err(|error| format!("secure_random_unavailable: {error}"))
    }
    #[cfg(windows)]
    {
        use std::ffi::c_void;
        #[link(name = "bcrypt")]
        extern "system" {
            fn BCryptGenRandom(
                algorithm: *mut c_void,
                buffer: *mut u8,
                length: u32,
                flags: u32,
            ) -> i32;
        }
        let length = u32::try_from(bytes.len()).map_err(|_| "secure_random_length_invalid")?;
        // BCRYPT_USE_SYSTEM_PREFERRED_RNG
        let status = unsafe {
            BCryptGenRandom(std::ptr::null_mut(), bytes.as_mut_ptr(), length, 0x00000002)
        };
        if status >= 0 {
            Ok(())
        } else {
            Err("secure_random_unavailable".into())
        }
    }
}

fn publish_file(destination: &Path, bytes: &[u8], replace: bool) -> Result<(), String> {
    publish_file_with(destination, bytes, replace, |from, to| fs::rename(from, to))
}

fn publish_file_with(
    destination: &Path,
    bytes: &[u8],
    replace: bool,
    mut rename: impl FnMut(&Path, &Path) -> std::io::Result<()>,
) -> Result<(), String> {
    let parent = destination
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .unwrap_or(Path::new("."));
    if !parent.is_dir() {
        return Err("output_parent_not_directory".into());
    }
    let existing = match fs::symlink_metadata(destination) {
        Ok(metadata) => {
            if metadata.file_type().is_symlink() || !metadata.is_file() {
                return Err("output_not_regular_file".into());
            }
            true
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => false,
        Err(error) => return Err(format!("output_metadata_failed: {error}")),
    };
    if existing && !replace {
        return Err("output_exists".into());
    }
    let temp_name = format!(".ygo-draft-{}.tmp", random_hex(16)?);
    let temp = parent.join(temp_name);
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| format!("temporary_create_failed: {error}"))?;
    let write_result = (|| {
        file.write_all(bytes)
            .map_err(|error| format!("temporary_write_failed: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("temporary_sync_failed: {error}"))?;
        drop(file);
        if !existing {
            fs::hard_link(&temp, destination).map_err(|error| {
                if error.kind() == std::io::ErrorKind::AlreadyExists {
                    "output_exists".into()
                } else {
                    format!("exclusive_publish_failed: {error}")
                }
            })?;
            return Ok(());
        }
        replace_file(&temp, destination, &mut rename)?;
        Ok(())
    })();
    let _ = fs::remove_file(&temp);
    write_result
}

fn replace_file(
    temp: &Path,
    destination: &Path,
    rename: &mut impl FnMut(&Path, &Path) -> std::io::Result<()>,
) -> Result<(), String> {
    #[cfg(unix)]
    {
        rename(temp, destination).map_err(|error| format!("atomic_replace_failed: {error}"))
    }
    #[cfg(windows)]
    {
        let backup = destination.with_extension(format!("json.{}.bak", random_hex(8)?));
        rename(destination, &backup)
            .map_err(|error| format!("replacement_backup_failed: {error}"))?;
        match rename(temp, destination) {
            Ok(()) => {
                let _ = fs::remove_file(backup);
                Ok(())
            }
            Err(error) => match rename(&backup, destination) {
                Ok(()) => Err(format!("atomic_replace_failed_rolled_back: {error}")),
                Err(restore_error) => Err(format!(
                    "atomic_replace_failed_backup_retained: {error}; restore failed: {restore_error}"
                )),
            },
        }
    }
}

struct DirectoryLock {
    file: File,
    #[cfg(windows)]
    overlapped: Overlapped,
}

impl DirectoryLock {
    fn try_acquire(file: File) -> std::io::Result<Self> {
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            extern "C" {
                fn flock(fd: i32, operation: i32) -> i32;
            }
            const LOCK_EX: i32 = 2;
            const LOCK_NB: i32 = 4;
            if unsafe { flock(file.as_raw_fd(), LOCK_EX | LOCK_NB) } != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(Self { file })
        }
        #[cfg(windows)]
        {
            use std::ffi::c_void;
            use std::os::windows::io::AsRawHandle;
            let mut lock = Self {
                file,
                overlapped: Overlapped::default(),
            };
            #[link(name = "kernel32")]
            extern "system" {
                fn LockFileEx(
                    file: *mut c_void,
                    flags: u32,
                    reserved: u32,
                    low: u32,
                    high: u32,
                    overlapped: *mut Overlapped,
                ) -> i32;
            }
            const LOCKFILE_FAIL_IMMEDIATELY: u32 = 1;
            const LOCKFILE_EXCLUSIVE_LOCK: u32 = 2;
            let ok = unsafe {
                LockFileEx(
                    lock.file.as_raw_handle().cast(),
                    LOCKFILE_FAIL_IMMEDIATELY | LOCKFILE_EXCLUSIVE_LOCK,
                    0,
                    1,
                    0,
                    &mut lock.overlapped,
                )
            };
            if ok == 0 {
                Err(std::io::Error::last_os_error())
            } else {
                Ok(lock)
            }
        }
    }
}

impl Drop for DirectoryLock {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            extern "C" {
                fn flock(fd: i32, operation: i32) -> i32;
            }
            const LOCK_UN: i32 = 8;
            let _ = unsafe { flock(self.file.as_raw_fd(), LOCK_UN) };
        }
        #[cfg(windows)]
        {
            use std::ffi::c_void;
            use std::os::windows::io::AsRawHandle;
            #[link(name = "kernel32")]
            extern "system" {
                fn UnlockFileEx(
                    file: *mut c_void,
                    reserved: u32,
                    low: u32,
                    high: u32,
                    overlapped: *mut Overlapped,
                ) -> i32;
            }
            let _ = unsafe {
                UnlockFileEx(
                    self.file.as_raw_handle().cast(),
                    0,
                    1,
                    0,
                    &mut self.overlapped,
                )
            };
        }
    }
}

#[cfg(windows)]
#[repr(C)]
#[derive(Default)]
struct Overlapped {
    internal: usize,
    internal_high: usize,
    offset: u32,
    offset_high: u32,
    event: *mut std::ffi::c_void,
}

#[cfg(windows)]
unsafe impl Send for Overlapped {}
#[cfg(windows)]
unsafe impl Sync for Overlapped {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn failed_replace_restores_original_and_reports_stable_diagnostic() {
        let root = std::env::temp_dir().join(format!(
            "ygo-draft-publish-failure-{}-{}",
            std::process::id(),
            random_hex(8).unwrap()
        ));
        fs::create_dir_all(&root).unwrap();
        let destination = root.join("draft.json");
        fs::write(&destination, b"original").unwrap();
        let error = publish_file_with(&destination, b"replacement", true, |from, to| {
            if to == destination && from.extension().and_then(|value| value.to_str()) == Some("tmp")
            {
                return Err(std::io::Error::other("injected publish failure"));
            }
            fs::rename(from, to)
        })
        .unwrap_err();
        #[cfg(windows)]
        assert!(
            error.starts_with("atomic_replace_failed_rolled_back:"),
            "{error}"
        );
        #[cfg(not(windows))]
        assert!(error.starts_with("atomic_replace_failed:"), "{error}");
        assert_eq!(fs::read(destination).unwrap(), b"original");
        assert!(!fs::read_dir(root).unwrap().any(|entry| {
            entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .ends_with(".tmp")
        }));
    }
}
