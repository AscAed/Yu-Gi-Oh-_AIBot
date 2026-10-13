//! ABI 11.0, copied by layout from the pinned ocgapi_types.h (see ENGINE_COMPATIBILITY).
use crate::*;
use std::{
    ffi::{c_char, c_void},
    path::Path,
};
pub type Duel = *mut c_void;
#[repr(C)]
#[derive(Default)]
pub struct CardData {
    pub code: u32,
    pub alias: u32,
    pub setcodes: *mut u16,
    pub type_flags: u32,
    pub level: u32,
    pub attribute: u32,
    pub race: u64,
    pub attack: i32,
    pub defense: i32,
    pub lscale: u32,
    pub rscale: u32,
    pub link_marker: u32,
}
#[repr(C)]
#[derive(Clone, Copy)]
pub struct Player {
    pub lp: u32,
    pub draw: u32,
    pub per_turn: u32,
}
#[repr(C)]
pub struct Options {
    pub seed: [u64; 4],
    pub flags: u64,
    pub first: Player,
    pub second: Player,
    pub reader: unsafe extern "C" fn(*mut c_void, u32, *mut CardData),
    pub payload1: *mut c_void,
    pub script: unsafe extern "C" fn(*mut c_void, Duel, *const c_char) -> i32,
    pub payload2: *mut c_void,
    pub log: unsafe extern "C" fn(*mut c_void, *const c_char, i32),
    pub payload3: *mut c_void,
    pub done: unsafe extern "C" fn(*mut c_void, *mut CardData),
    pub payload4: *mut c_void,
    pub unsafe_libs: u8,
}
#[repr(C)]
pub struct NewCard {
    pub team: u8,
    pub duelist: u8,
    pub code: u32,
    pub controller: u8,
    pub location: u32,
    pub sequence: u32,
    pub position: u32,
}
#[repr(C)]
pub struct Query {
    pub flags: u32,
    pub controller: u8,
    pub location: u32,
    pub sequence: u32,
    pub overlay_sequence: u32,
}
pub struct Api {
    _library: libloading::Library,
    pub create: unsafe extern "C" fn(*mut Duel, *const Options) -> i32,
    pub destroy: unsafe extern "C" fn(Duel),
    pub new_card: unsafe extern "C" fn(Duel, *const NewCard),
    pub start: unsafe extern "C" fn(Duel),
    pub process: unsafe extern "C" fn(Duel) -> i32,
    pub message: unsafe extern "C" fn(Duel, *mut u32) -> *const u8,
    pub response: unsafe extern "C" fn(Duel, *const u8, u32),
    pub load_script: unsafe extern "C" fn(Duel, *const c_char, u32, *const c_char) -> i32,
    pub query: unsafe extern "C" fn(Duel, *mut u32, *const Query) -> *const u8,
    pub query_count: unsafe extern "C" fn(Duel, u8, u32) -> u32,
    pub field: unsafe extern "C" fn(Duel, *mut u32) -> *const u8,
}
impl Api {
    pub fn load(path: &Path) -> Result<Self, WorkerError> {
        if std::mem::size_of::<CardData>() != 64
            || std::mem::size_of::<Options>() != 136
            || std::mem::size_of::<NewCard>() != 24
            || std::mem::size_of::<Query>() != 20
        {
            return Err(WorkerError::new(
                "abi_layout",
                "load",
                "worker requires x64 ABI",
            ));
        }
        // This entry point is called only by the isolated worker.
        unsafe {
            let lib = libloading::Library::new(path)
                .map_err(|e| WorkerError::new("dll_load_failed", "load", e.to_string()))?;
            macro_rules! sym {
                ($name:literal) => {
                    *lib.get(concat!($name, "\0").as_bytes()).map_err(|e| {
                        WorkerError::new("dll_symbol_missing", "load", e.to_string())
                    })?
                };
            }
            let version: unsafe extern "C" fn(*mut i32, *mut i32) = sym!("OCG_GetVersion");
            let (mut major, mut minor) = (0, 0);
            version(&mut major, &mut minor);
            if (major, minor) != (11, 0) {
                return Err(WorkerError::new(
                    "abi_version",
                    "load",
                    format!("expected 11.0, got {major}.{minor}"),
                ));
            }
            Ok(Self {
                create: sym!("OCG_CreateDuel"),
                destroy: sym!("OCG_DestroyDuel"),
                new_card: sym!("OCG_DuelNewCard"),
                start: sym!("OCG_StartDuel"),
                process: sym!("OCG_DuelProcess"),
                message: sym!("OCG_DuelGetMessage"),
                response: sym!("OCG_DuelSetResponse"),
                load_script: sym!("OCG_LoadScript"),
                query: sym!("OCG_DuelQuery"),
                query_count: sym!("OCG_DuelQueryCount"),
                field: sym!("OCG_DuelQueryField"),
                _library: lib,
            })
        }
    }
}
pub struct Guard<'a> {
    pub api: &'a Api,
    pub duel: Duel,
}
impl Drop for Guard<'_> {
    fn drop(&mut self) {
        unsafe {
            (self.api.destroy)(self.duel);
        }
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn matches_pinned_c_layout() {
        assert_eq!(std::mem::size_of::<CardData>(), 64);
        assert_eq!(std::mem::offset_of!(CardData, race), 32);
        assert_eq!(std::mem::offset_of!(Options, reader), 64);
        assert_eq!(std::mem::size_of::<Options>(), 136);
    }
}
