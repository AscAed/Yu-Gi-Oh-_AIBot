use crate::{codec::Reader, ffi::*, *};
use rusqlite::{Connection, OpenFlags};
use std::{
    collections::BTreeMap,
    ffi::{c_char, c_void, CStr, CString},
    fs,
    io::{BufRead, Write},
    path::{Component, Path},
    ptr,
};

struct Context<'a> {
    api: &'a Api,
    db: Connection,
    root: PathBuf,
    expected: BTreeMap<String, String>,
    loaded: BTreeMap<String, String>,
    setcodes: BTreeMap<u32, Vec<u16>>,
    errors: Vec<String>,
}
unsafe extern "C" fn card_reader(payload: *mut c_void, code: u32, out: *mut CardData) {
    let ctx = &mut *(payload as *mut Context<'_>);
    let row = ctx.db.query_row(
        "SELECT alias,setcode,type,level,attribute,race,atk,def FROM datas WHERE id=?1",
        [code],
        |r| {
            Ok((
                r.get::<_, u32>(0)?,
                r.get::<_, i64>(1)? as u64,
                r.get::<_, u32>(2)?,
                r.get::<_, u32>(3)?,
                r.get::<_, u32>(4)?,
                r.get::<_, i64>(5)? as u64,
                r.get::<_, i32>(6)?,
                r.get::<_, i32>(7)?,
            ))
        },
    );
    match row {
        Ok((alias, sc, t, l, a, race, atk, def)) => {
            let mut sets = (0..4)
                .map(|i| ((sc >> (i * 16)) & 0xffff) as u16)
                .filter(|v| *v != 0)
                .collect::<Vec<_>>();
            sets.push(0);
            let sets = ctx.setcodes.entry(code).or_insert(sets);
            *out = CardData {
                code,
                alias,
                setcodes: sets.as_mut_ptr(),
                type_flags: t,
                level: l & 255,
                attribute: a,
                race,
                attack: atk,
                defense: if t & 0x4000000 != 0 { 0 } else { def },
                lscale: (l >> 24) & 255,
                rscale: (l >> 16) & 255,
                link_marker: if t & 0x4000000 != 0 { def as u32 } else { 0 },
            };
        }
        Err(e) => {
            ctx.errors.push(format!("card {code}: {e}"));
            *out = CardData::default();
        }
    }
}
unsafe extern "C" fn card_done(_: *mut c_void, _: *mut CardData) {}
unsafe extern "C" fn logger(payload: *mut c_void, message: *const c_char, kind: i32) {
    if kind == 0 {
        let ctx = &mut *(payload as *mut Context<'_>);
        ctx.errors
            .push(CStr::from_ptr(message).to_string_lossy().into_owned());
    }
}
unsafe extern "C" fn script_reader(payload: *mut c_void, duel: Duel, name: *const c_char) -> i32 {
    let ctx = &mut *(payload as *mut Context<'_>);
    let name = CStr::from_ptr(name).to_string_lossy().into_owned();
    if name == "c0.lua" {
        return 0;
    } // Core's synthetic temporary card has no script.
    let path = Path::new(&name);
    if path
        .components()
        .any(|c| !matches!(c, Component::Normal(_)))
    {
        ctx.errors.push(format!("unsafe script path {name}"));
        return 0;
    }
    let relative = if ctx.expected.contains_key(&name) {
        name.clone()
    } else {
        format!("official/{name}")
    };
    let candidate = ctx.root.join(&relative);
    let result = (|| -> Result<i32, String> {
        let resolved = candidate.canonicalize().map_err(|e| e.to_string())?;
        if !resolved.starts_with(&ctx.root) {
            return Err("script outside configured root".into());
        }
        let bytes = fs::read(resolved).map_err(|e| e.to_string())?;
        let hash = digest(&bytes);
        if ctx.expected.get(&relative) != Some(&hash) {
            return Err("script content hash mismatch".into());
        }
        ctx.loaded.insert(relative.clone(), hash);
        Ok((ctx.api.load_script)(
            duel,
            bytes.as_ptr() as *const c_char,
            bytes.len() as u32,
            CString::new(name.clone())
                .map_err(|e| e.to_string())?
                .as_ptr(),
        ))
    })();
    match result {
        Ok(1) => 1,
        other => {
            // Plain normal monsters have no initial_effect script by design.
            let normal = name
                .strip_prefix('c')
                .and_then(|s| s.strip_suffix(".lua"))
                .and_then(|s| s.parse::<u32>().ok())
                .and_then(|id| {
                    ctx.db
                        .query_row("SELECT type FROM datas WHERE id=?1", [id], |r| {
                            r.get::<_, u32>(0)
                        })
                        .ok()
                })
                .is_some_and(|t| t & 0x10 != 0 && t & 0x1000000 == 0);
            if !normal || ctx.expected.contains_key(&relative) || candidate.exists() {
                ctx.errors.push(format!("script {name}: {other:?}"));
            }
            0
        }
    }
}
pub fn probe_request(engine: ProcessEngineConfig) -> Result<RunDuelRequest, WorkerError> {
    let mut versions = RuntimeVersions {
        rules: "ocg-mr5".into(),
        core_commit: CORE_COMMIT.into(),
        initializer: INITIALIZER_VERSION.into(),
        ..Default::default()
    };
    versions.engine_sha256 = hash_file(&engine.ocgcore_path)
        .map_err(|e| WorkerError::new("asset_missing", "versions", e))?;
    versions.cdb_sha256 = hash_file(&engine.catalog_path)
        .map_err(|e| WorkerError::new("asset_missing", "versions", e))?;
    versions.scripts_sha256 = hash_file(&engine.script_manifest_path)
        .map_err(|e| WorkerError::new("asset_missing", "versions", e))?;
    Ok(RunDuelRequest {
        protocol_version: 2,
        engine,
        deck: Deck::default(),
        opening_hand: vec![],
        seed: 1,
        decisions: vec![],
        versions,
        probe_only: true,
        scenario: None,
    })
}
pub fn runtime_request(
    engine: ProcessEngineConfig,
    deck: Deck,
    hand: Vec<CardId>,
    seed: u64,
) -> Result<RunDuelRequest, WorkerError> {
    let mut r = probe_request(engine)?;
    r.deck = deck;
    r.opening_hand = hand;
    r.seed = seed;
    r.probe_only = false;
    Ok(r)
}
fn verify(r: &RunDuelRequest) -> Result<(), WorkerError> {
    if !matches!(r.protocol_version, 2 | 3)
        || (r.protocol_version == 2 && r.scenario.is_some())
        || r.scenario.as_ref().is_some_and(|s| s != "ryu-ran")
    {
        return Err(WorkerError::new(
            "protocol_version",
            "input",
            "expected protocol v2",
        ));
    }
    if r.versions.rules != "ocg-mr5"
        || r.versions.core_commit != CORE_COMMIT
        || r.versions.initializer
            != if r.protocol_version == 3 {
                "fixed-opponent-v1"
            } else {
                INITIALIZER_VERSION
            }
    {
        return Err(WorkerError::new(
            "version_mismatch",
            "input",
            "unsupported rules/core",
        ));
    }
    for (path, expected) in [
        (&r.engine.ocgcore_path, &r.versions.engine_sha256),
        (&r.engine.catalog_path, &r.versions.cdb_sha256),
        (&r.engine.script_manifest_path, &r.versions.scripts_sha256),
    ] {
        if &hash_file(path).map_err(|e| WorkerError::new("asset_missing", "verify", e))? != expected
        {
            return Err(WorkerError::new(
                "asset_hash",
                "verify",
                path.display().to_string(),
            ));
        }
    }
    let bytes = fs::read_to_string(&r.engine.engine_manifest_path)
        .map_err(|e| WorkerError::new("engine_manifest", "verify", e.to_string()))?;
    let v: serde_json::Value = serde_json::from_str(bytes.trim_start_matches('\u{feff}'))
        .map_err(|e| WorkerError::new("engine_manifest", "verify", e.to_string()))?;
    if v["core_commit"] != CORE_COMMIT
        || v["lua_commit"] != "6e22fedb74cf0c9b6656e9fce8b7331db847c605"
        || v["architecture"] != "x64"
        || v["api"] != "11.0"
        || v["sha256"] != r.versions.engine_sha256
        || v["abi_probe_passed"] != true
        || v["source_verified"] != true
    {
        return Err(WorkerError::new(
            "engine_manifest",
            "verify",
            "unverified engine build",
        ));
    }
    Ok(())
}
unsafe fn buffer(ptr: *const u8, length: u32) -> Result<Vec<u8>, String> {
    if length > 16 * 1024 * 1024 || length > 0 && ptr.is_null() {
        return Err("invalid native buffer".into());
    }
    if length == 0 {
        Ok(vec![])
    } else {
        Ok(std::slice::from_raw_parts(ptr, length as usize).to_vec())
    }
}
fn checkpoint(
    api: &Api,
    duel: Duel,
    turn: u32,
    player: u8,
    phase: u16,
    extended: bool,
) -> Result<Checkpoint, String> {
    let mut state = Checkpoint {
        turn,
        turn_player: player,
        phase,
        ..Default::default()
    };
    unsafe {
        let mut len = 0;
        let ptr = (api.field)(duel, &mut len);
        let raw = buffer(ptr, len)?;
        let mut r = Reader::new(&raw);
        r.u32()?;
        for p in 0..2 {
            state.lp[p] = r.u32()?;
            for _ in 0..7 {
                if r.u8()? != 0 {
                    r.u8()?;
                    r.u32()?;
                }
            }
            for _ in 0..8 {
                if r.u8()? != 0 {
                    r.u8()?;
                    r.u32()?;
                }
            }
            for _ in 0..6 {
                r.u32()?;
            }
        }
        for p in 0..2 {
            for zone in [1u32, 2, 4, 8, 16, 32, 64] {
                let count = if zone == 4 {
                    7
                } else if zone == 8 {
                    8
                } else {
                    (api.query_count)(duel, p, zone)
                };
                if count > 4096 {
                    return Err("invalid card count".into());
                }
                for seq in 0..count {
                    let query = Query {
                        flags: 1
                            | 2
                            | 8
                            | 0x100
                            | 0x200
                            | 0x10000
                            | if extended { 0x10 | 0x20 } else { 0 },
                        controller: p,
                        location: zone,
                        sequence: seq,
                        overlay_sequence: 0,
                    };
                    let mut len = 0;
                    let ptr = (api.query)(duel, &mut len, &query);
                    let bytes = buffer(ptr, len)?;
                    if bytes.is_empty() {
                        continue;
                    }
                    let mut r = Reader::new(&bytes);
                    let mut card = StateCard {
                        player: p,
                        location: zone as u8,
                        sequence: seq,
                        ..Default::default()
                    };
                    let mut ended = false;
                    while r.pos < bytes.len() {
                        let size = r.u16()? as usize;
                        let mut field = Reader::new(r.take(size)?);
                        let flag = field.u32()?;
                        match flag {
                            1 => card.code = field.u32()?,
                            2 => card.position = field.u32()?,
                            0x10 => card.level = Some(field.u32()?),
                            0x20 => card.rank = Some(field.u32()?),
                            8 => card.type_flags = field.u32()?,
                            0x100 => card.attack = field.u32()? as i32,
                            0x200 => card.defense = field.u32()? as i32,
                            0x10000 => {
                                for _ in 0..field.count()? {
                                    card.overlay.push(field.u32()?);
                                }
                            }
                            0x80000000 => {
                                ended = true;
                                break;
                            }
                            _ => (),
                        }
                    }
                    if !ended || card.code == 0 {
                        return Err("incomplete card query".into());
                    }
                    state.cards.push(card);
                }
            }
        }
    }
    Ok(state)
}
fn shuffle_initial_deck(cards: &mut [CardId], mut seed: u64) {
    // Versioned SplitMix64 initialization only; later randomness belongs to core.
    for i in (1..cards.len()).rev() {
        let bound = (i + 1) as u64;
        let limit = u64::MAX - u64::MAX % bound;
        let value = loop {
            seed = seed.wrapping_add(0x9e3779b97f4a7c15);
            let mut z = seed;
            z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
            z ^= z >> 31;
            if z < limit {
                break z;
            }
        };
        cards.swap(i, (value % bound) as usize);
    }
}
fn execute(request: RunDuelRequest) -> Result<DuelResult, WorkerError> {
    verify(&request)?;
    let api = Api::load(&request.engine.ocgcore_path)?;
    let mut result = DuelResult::failure(WorkerError::new("not_started", "create", ""));
    result.error = None;
    result.versions = request.versions.clone();
    result.protocol_version = request.protocol_version;
    if request.probe_only {
        result.status = DuelStatus::ProbePassed;
        return Ok(result);
    }
    let mut remaining = ygo_domain::validate_hand(&request.deck, &request.opening_hand)
        .map_err(|e| WorkerError::new("invalid_hand", "input", e))?;
    let root = request
        .engine
        .scripts_path
        .canonicalize()
        .map_err(|e| WorkerError::new("scripts_missing", "input", e.to_string()))?;
    let expected: BTreeMap<String, String> = serde_json::from_slice(
        &fs::read(&request.engine.script_manifest_path)
            .map_err(|e| WorkerError::new("scripts_missing", "input", e.to_string()))?,
    )
    .map_err(|e| WorkerError::new("script_manifest", "input", e.to_string()))?;
    let db = Connection::open_with_flags(
        &request.engine.catalog_path,
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )
    .map_err(|e| WorkerError::new("catalog_missing", "input", e.to_string()))?;
    let mut ctx = Context {
        api: &api,
        db,
        root,
        expected,
        loaded: BTreeMap::new(),
        setcodes: BTreeMap::new(),
        errors: vec![],
    };
    let payload = &mut ctx as *mut Context<'_> as *mut c_void;
    let seed_bytes = sha2::Sha256::digest(request.seed.to_le_bytes());
    let mut seeds = [0; 4];
    for (i, chunk) in seed_bytes.chunks_exact(8).enumerate() {
        seeds[i] = u64::from_le_bytes(chunk.try_into().unwrap());
    }
    shuffle_initial_deck(&mut remaining, seeds[0]);
    let mut opponent_deck = request.deck.main.clone();
    shuffle_initial_deck(&mut opponent_deck, seeds[1]);
    if request.scenario.is_some() {
        let index = opponent_deck
            .iter()
            .position(|c| c.0 == 2964201)
            .ok_or_else(|| {
                WorkerError::new(
                    "scenario_card_missing",
                    "input",
                    "opponent deck requires Ryu-Ran",
                )
            })?;
        opponent_deck.remove(index);
    }
    let options = Options {
        seed: seeds,
        flags: 0x2e800,
        first: Player {
            lp: 8000,
            draw: 0,
            per_turn: 1,
        },
        second: Player {
            lp: 8000,
            draw: 0,
            per_turn: 1,
        },
        reader: card_reader,
        payload1: payload,
        script: script_reader,
        payload2: payload,
        log: logger,
        payload3: payload,
        done: card_done,
        payload4: payload,
        unsafe_libs: 0,
    };
    let mut duel = ptr::null_mut();
    unsafe {
        let code = (api.create)(&mut duel, &options);
        if code != 0 || duel.is_null() {
            return Err(WorkerError::new(
                "create_failed",
                "create",
                format!("status {code}"),
            ));
        }
    }
    let guard = Guard { api: &api, duel };
    let execution = (|| -> Result<(), WorkerError> {
        unsafe {
            for name in ["constant.lua", "utility.lua"] {
                let name = CString::new(name).unwrap();
                script_reader(payload, duel, name.as_ptr());
            }
            for (p, zone, cards) in [
                (0, 1, &remaining),
                (0, 2, &request.opening_hand),
                (0, 64, &request.deck.extra),
                (1, 1, &opponent_deck),
            ] {
                for (seq, id) in cards.iter().enumerate() {
                    (api.new_card)(
                        duel,
                        &NewCard {
                            team: p,
                            duelist: 0,
                            code: id.0,
                            controller: p,
                            location: zone,
                            sequence: seq as u32,
                            position: if zone == 2 { 1 } else { 8 },
                        },
                    );
                }
            }
            if request.scenario.is_some() {
                (api.new_card)(
                    duel,
                    &NewCard {
                        team: 1,
                        duelist: 0,
                        code: 2964201,
                        controller: 1,
                        location: 4,
                        sequence: 0,
                        position: 1,
                    },
                );
            }
            (api.start)(duel);
        }
        let (mut turn, mut player, mut phase, mut used) = (0, 0, 0, 0usize);
        let start = std::time::Instant::now();
        loop {
            if start.elapsed().as_millis() >= request.engine.timeout_ms as u128 {
                return Err(WorkerError::new("timeout", "duel", "worker deadline"));
            }
            let status = unsafe { (api.process)(duel) };
            let mut length = 0;
            let ptr = unsafe { (api.message)(duel, &mut length) };
            let bytes = unsafe { buffer(ptr, length) }
                .map_err(|e| WorkerError::new("native_buffer", "messages", e))?;
            let mut prompt = None;
            let mut finished = false;
            for raw in split_frames(&bytes)
                .map_err(|e| WorkerError::new("malformed_frame", "messages", e))?
            {
                let seq = result.events.len() as u64 + 1;
                let frame = decode_frame(seq, raw).map_err(|e| {
                    WorkerError::new("malformed_message", "decode", format!("{e}; raw={raw:?}"))
                })?;
                if frame.opcode == 1 {
                    return Err(WorkerError::new(
                        "engine_retry",
                        "response",
                        "core rejected response",
                    ));
                }
                if frame.opcode == 40 {
                    turn += 1;
                    player = raw[1];
                    if turn > 1 {
                        finished = true;
                    }
                }
                if frame.opcode == 41 {
                    phase = u16::from_le_bytes([raw[1], raw[2]]);
                }
                if !frame.supported {
                    result
                        .coverage_gaps
                        .push(format!("opcode {}", frame.opcode));
                }
                if let Some(p) = parse_prompt(seq, raw)
                    .map_err(|e| WorkerError::new("unsupported_prompt", "decode", e))?
                {
                    prompt = Some(p);
                }
                // Reserved selection opcodes must never be treated as informational.
                if matches!(frame.opcode,10|20..=23|25|27..=29) {
                    result.events.push(frame.clone());
                    return Err(WorkerError::new(
                        "unsupported_prompt",
                        "decode",
                        format!("opcode {}", frame.opcode),
                    ));
                }
                result.events.push(frame);
            }
            if !ctx.errors.is_empty() {
                return Err(WorkerError::new(
                    "callback_failed",
                    "callbacks",
                    ctx.errors.join("; "),
                ));
            }
            if finished || status == 0 {
                if used != request.decisions.len() {
                    return Err(WorkerError::new(
                        "extra_decisions",
                        "replay",
                        "unused decisions",
                    ));
                }
                result.checkpoint =
                    checkpoint(&api, duel, 1, 0, 512, request.protocol_version == 3)
                        .map_err(|e| WorkerError::new("query_failed", "checkpoint", e))?;
                result.status = if result.coverage_gaps.is_empty() {
                    DuelStatus::EngineVerified
                } else {
                    DuelStatus::Partial
                };
                break;
            }
            if let Some(p) = prompt {
                result.prompt = Some(p.clone());
                let choice = if p.player == 1 {
                    p.actions
                        .iter()
                        .find(|a| matches!(a.choice, Choice::Chain { index: None }))
                        .map(|a| a.choice.clone())
                        .ok_or_else(|| {
                            WorkerError::new(
                                "opponent_decision",
                                "policy",
                                "opponent has mandatory response",
                            )
                        })?
                } else if let Some(decision) = request.decisions.get(used) {
                    if decision.prompt_id != p.id || decision.player != p.player {
                        return Err(WorkerError::new(
                            "prompt_mismatch",
                            "replay",
                            "prompt ID/player changed",
                        ));
                    }
                    used += 1;
                    decision.choice.clone()
                } else if p.actions.len() == 1 && result.resolved_decisions.len() < 1024 {
                    p.actions[0].choice.clone()
                } else {
                    result.checkpoint = checkpoint(
                        &api,
                        duel,
                        turn,
                        player,
                        phase,
                        request.protocol_version == 3,
                    )
                    .map_err(|e| WorkerError::new("query_failed", "checkpoint", e))?;
                    result.prompt = Some(p);
                    result.status = DuelStatus::DecisionRequired;
                    break;
                };
                let bytes = p
                    .encode(&choice)
                    .map_err(|e| WorkerError::new("invalid_decision", "response", e))?;
                if p.player == 0 {
                    result.resolved_decisions.push(Decision {
                        prompt_id: p.id,
                        player: p.player,
                        choice: choice.clone(),
                    });
                }
                result.steps.push(
                    p.actions
                        .iter()
                        .find(|a| a.choice == choice)
                        .unwrap()
                        .clone(),
                );
                unsafe {
                    (api.response)(duel, bytes.as_ptr(), bytes.len() as u32);
                }
                result.prompt = None;
            } else if status == 1 {
                return Err(WorkerError::new(
                    "missing_prompt",
                    "messages",
                    "core awaiting unknown response",
                ));
            }
            if result.events.len() > 100000 {
                return Err(WorkerError::new("event_budget", "messages", "event limit"));
            }
        }
        Ok(())
    })();
    if let Err(error) = execution {
        result.status = DuelStatus::Failed;
        result.error = Some(error);
    }
    result.loaded_scripts = ctx.loaded.clone();
    result.peak_working_set_bytes = peak_working_set_bytes();
    result.coverage_gaps.sort();
    result.coverage_gaps.dedup();
    drop(guard);
    Ok(result)
}
pub fn run_worker<R: BufRead, W: Write>(mut input: R, mut output: W) -> std::io::Result<()> {
    let mut line = String::new();
    std::io::Read::take(&mut input, 16 * 1024 * 1024 + 1).read_line(&mut line)?;
    let result = if line.len() > 16 * 1024 * 1024 {
        DuelResult::failure(WorkerError::new("request_size", "input", "request limit"))
    } else {
        match serde_json::from_str::<RunDuelRequest>(&line) {
            Ok(r) => {
                let protocol = r.protocol_version;
                let versions = r.versions.clone();
                execute(r).unwrap_or_else(|e| {
                    let mut result = DuelResult::failure(e);
                    if protocol == 3 {
                        result.protocol_version = 3;
                        result.versions = versions;
                    }
                    result
                })
            }
            Err(e) => {
                DuelResult::failure(WorkerError::new("invalid_request", "input", e.to_string()))
            }
        }
    };
    serde_json::to_writer(&mut output, &result)?;
    output.write_all(b"\n")?;
    output.flush()
}
pub fn worker_main() -> std::io::Result<()> {
    run_worker(std::io::stdin().lock(), std::io::stdout().lock())
}
