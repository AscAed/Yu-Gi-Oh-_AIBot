//! Rebuild supported rule state from actual events, never proposal.after.
use super::*;
#[derive(Clone)]
struct Tracked {
    id: String,
    code: u32,
    player: u8,
    location: u8,
    sequence: u32,
    position: u32,
    epoch: u32,
    redirect: bool,
}
fn n(v: &serde_json::Value, k: &str) -> u32 {
    v[k].as_u64().unwrap_or(0) as u32
}
pub fn reconstruct(
    r: &DuelResult,
    cat: &Catalog,
    pack: &KnowledgePack,
) -> Result<SymbolicState, String> {
    if r.protocol_version != 5 {
        return Err("recovery requires protocol v5".into());
    }
    rebuild(r, cat, pack)
}
fn rebuild(r: &DuelResult, cat: &Catalog, pack: &KnowledgePack) -> Result<SymbolicState, String> {
    for frame in &r.events {
        if !frame_matches_raw(frame)? {
            return Err("raw recovery event mismatch".into());
        }
    }
    if r.status != DuelStatus::DecisionRequired
        || r.error.is_some()
        || !r.coverage_gaps.is_empty()
        || r.checkpoint.turn != 1
        || r.checkpoint.turn_player != 0
        || r.checkpoint.phase != 4
        || !r
            .prompt
            .as_ref()
            .is_some_and(|p| p.player == 0 && p.opcode == 11)
        || !r
            .events
            .iter()
            .rev()
            .find(|e| matches!(e.opcode, 70 | 74))
            .is_some_and(|e| e.opcode == 74)
    {
        return Err("recovery_coverage_gap: no settled own operation window".into());
    }
    let facts = ygo_goal::actual_facts(r, cat, pack);
    if !facts.history_complete {
        return Err("recovery_coverage_gap: incomplete actual history".into());
    }
    let mut tracked: Vec<Tracked> = vec![];
    let mut used = BTreeSet::new();
    let mut dark_only = false;
    let mut activation_epochs = BTreeMap::new();
    for e in &r.events {
        if e.opcode == 50 {
            let from = &e.fields["from"];
            let to = &e.fields["to"];
            let code = n(&e.fields, "code");
            let found = tracked.iter().position(|c| {
                c.code == code
                    && c.player == n(from, "player") as u8
                    && c.location == n(from, "location") as u8
                    && c.sequence == n(from, "sequence")
                    && (c.location & 128 == 0 || c.position == n(from, "position"))
            });
            let mut c = found.map(|i| tracked.remove(i)).unwrap_or(Tracked {
                id: format!("observed:{}", e.sequence),
                code,
                player: n(from, "player") as u8,
                location: n(from, "location") as u8,
                sequence: n(from, "sequence"),
                position: n(from, "position"),
                epoch: 0,
                redirect: false,
            });
            if c.location == 4 && n(to, "location") != 4 && n(to, "location") & 128 == 0 {
                c.epoch += 1;
                c.redirect = false;
            }
            if n(to, "location") & 128 != 0 {
                c.redirect = false;
            }
            if code == 36426778 && c.player == 0 && c.location == 2 && n(to, "location") == 4 {
                let inherent = r
                    .resolved_decisions
                    .iter()
                    .filter(|d| d.prompt_id < e.sequence && d.player == 0)
                    .rev()
                    .find_map(|d| {
                        r.events
                            .iter()
                            .find(|f| f.sequence == d.prompt_id && f.opcode == 11)
                            .and_then(|f| prompt_metadata(f.sequence, &f.raw).ok())
                            .and_then(|ms| ms.into_iter().find(|m| m.choice == d.choice))
                    })
                    .is_some_and(|m| {
                        matches!(m.choice, Choice::Command { command: 1, .. })
                            && m.source.is_some_and(|s| s.code == code && s.location == 2)
                    });
                if inherent {
                    used.insert("36426778:summon".into());
                }
            }
            for other in &mut tracked {
                if other.player == n(from, "player") as u8
                    && other.location == n(from, "location") as u8
                    && matches!(other.location, 1 | 2 | 16 | 32 | 64)
                    && other.sequence > n(from, "sequence")
                {
                    other.sequence -= 1;
                }
                if other.location & 128 != 0
                    && other.player == n(from, "player") as u8
                    && other.location & 127 == n(from, "location") as u8
                    && other.sequence == n(from, "sequence")
                {
                    other.location = n(to, "location") as u8 | 128;
                    other.sequence = n(to, "sequence");
                }
                if other.location & 128 != 0
                    && other.player == n(from, "player") as u8
                    && other.location == n(from, "location") as u8
                    && other.sequence == n(from, "sequence")
                    && other.position > n(from, "position")
                {
                    other.position -= 1;
                }
            }
            c.player = n(to, "player") as u8;
            c.location = n(to, "location") as u8;
            c.sequence = n(to, "sequence");
            c.position = n(to, "position");
            tracked.push(c);
        }
        if e.opcode == 33 {
            let codes = e.fields["cards"].as_array().ok_or("unknown hand shuffle")?;
            for c in tracked
                .iter_mut()
                .filter(|c| c.player == n(&e.fields, "player") as u8 && c.location == 2)
            {
                let pos: Vec<_> = codes
                    .iter()
                    .enumerate()
                    .filter(|(_, x)| x.as_u64() == Some(c.code as u64))
                    .map(|(i, _)| i as u32)
                    .collect();
                c.sequence = if pos.len() == 1 { pos[0] } else { u32::MAX };
            }
        }
        if e.opcode == 70 {
            let loc = &e.fields["location"];
            if let Some(c) = tracked.iter().find(|c| {
                c.code == n(&e.fields, "code")
                    && c.player == n(loc, "player") as u8
                    && c.location == n(loc, "location") as u8
                    && c.sequence == n(loc, "sequence")
            }) {
                activation_epochs.insert(n(&e.fields, "chain"), c.epoch);
            }
        }
        for h in facts.history.iter().filter(|h| {
            h.event == e.sequence
                && h.card.player == 0
                && matches!(
                    h.kind.as_str(),
                    "effect_resolved" | "effect_negated" | "activation_negated"
                )
        }) {
            let id = h.effect_id.as_deref().ok_or("unknown activated effect")?;
            let effect = pack.effect(id).ok_or("unknown supported effect")?;
            if !effect.supported {
                return Err("recovery_coverage_gap: unsupported prior effect".into());
            }
            if let Some(k) = &effect.usage_key {
                used.insert(k.clone());
            }
            if matches!(effect.rule, ygo_knowledge::Rule::BreakDestroy) {
                let epoch = activation_epochs
                    .get(&n(&e.fields, "chain"))
                    .copied()
                    .ok_or("unknown per-appearance usage epoch")?;
                used.insert(format!("break:{}:{}", h.card.instance, epoch));
            }
            if h.kind == "effect_resolved" {
                if matches!(effect.rule, ygo_knowledge::Rule::ScaleRevive) {
                    let c = tracked
                        .iter_mut()
                        .find(|c| c.id == h.card.instance && c.location == 4)
                        .ok_or("unknown revived source")?;
                    c.redirect = true;
                }
                if matches!(effect.rule, ygo_knowledge::Rule::BreakRevive) {
                    dark_only = true;
                }
            }
        }
    }
    let normals = facts
        .history
        .iter()
        .filter(|h| h.card.player == 0 && h.kind == "normal_summon")
        .count();
    if normals > 1 {
        return Err("unknown normal summon allowance".into());
    }
    let mut cards = vec![];
    for c in &facts.cards {
        let meta = cat.get(&CardId(c.code)).ok_or("unknown catalog card")?;
        let t = tracked.iter().find(|t| t.id == c.instance);
        let untouched_hand = c.location == 2
            && t.is_none()
            && !tracked
                .iter()
                .any(|t| t.player == c.player && t.location == 2 && t.code == c.code);
        let untouched_opponent = c.player == 1 && t.is_none() && meta.type_flags & 0x10 != 0;
        if !matches!(c.location, 1 | 64)
            && !untouched_hand
            && !untouched_opponent
            && (!c.identity_known || t.is_none())
        {
            return Err(format!(
                "recovery_coverage_gap: ambiguous active identity {} {} {}",
                c.code, c.location, c.instance
            ));
        }
        cards.push(Resource {
            instance: c.instance.clone(),
            code: c.code,
            location: c.location,
            level: c.level.ok_or("unknown actual level")?,
            base_level: if meta.type_flags & 0x4800000 == 0 {
                meta.level
            } else {
                0
            },
            player: c.player,
            overlay_host: None,
            xyz_summoned: c.proper_xyz.unwrap_or(false),
            epoch: t.map_or(0, |t| t.epoch),
            redirect: t.is_some_and(|t| t.redirect),
        });
    }
    for m in tracked.iter().filter(|c| c.location & 128 != 0) {
        let host = cards
            .iter()
            .find(|h| {
                h.player == m.player
                    && h.location == 4
                    && facts
                        .cards
                        .iter()
                        .any(|f| f.instance == h.instance && f.sequence == m.sequence)
            })
            .ok_or("unknown overlay host")?;
        let host_id = host.instance.clone();
        let meta = cat.get(&CardId(m.code)).ok_or("unknown material")?;
        cards.push(Resource {
            instance: m.id.clone(),
            code: m.code,
            location: m.location,
            level: meta.level,
            base_level: meta.level,
            player: m.player,
            overlay_host: Some(host_id),
            xyz_summoned: false,
            epoch: m.epoch,
            redirect: false,
        });
    }
    for host in &facts.cards {
        let mut actual: Vec<_> = cards
            .iter()
            .filter(|m| m.overlay_host.as_deref() == Some(host.instance.as_str()))
            .map(|m| m.code)
            .collect();
        let mut expected = host.materials.clone();
        actual.sort();
        expected.sort();
        if actual != expected {
            return Err("recovery_coverage_gap: material multiset mismatch".into());
        }
    }
    Ok(SymbolicState {
        cards,
        used,
        normal_left: (1 - normals) as u8,
        pending: vec![],
        dark_only,
        destroyed_xyz: BTreeSet::new(),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    fn load(text: &str) -> (DuelResult, Catalog, KnowledgePack) {
        let v: serde_json::Value = serde_json::from_str(text).unwrap();
        let r = serde_json::from_value(v["observation"].clone()).unwrap();
        let cat = serde_json::from_value(v["catalog"].clone()).unwrap();
        let pack =
            serde_json::from_str(include_str!("../../../../knowledge/phantom-v2.json")).unwrap();
        (r, cat, pack)
    }
    #[test]
    fn paid_cost_and_untouched_duplicate_hand_are_separate_instances() {
        let (r, cat, pack) = load(include_str!(
            "../../../../tests/fixtures/ash-v5-anchor.events.json"
        ));
        let s = reconstruct(&r, &cat, &pack).unwrap();
        assert_eq!(s.normal_left, 0);
        assert!(s.used.contains("25538345:mill"));
        let copies: Vec<_> = s
            .cards
            .iter()
            .filter(|c| c.player == 0 && c.code == 2964201 && matches!(c.location, 2 | 16))
            .collect();
        assert_eq!(copies.len(), 2);
        assert_ne!(copies[0].instance, copies[1].instance);
        assert!(copies.iter().any(|c| c.location == 2));
        assert!(copies.iter().any(|c| c.location == 16));
        let mut bad = r.clone();
        bad.events
            .iter_mut()
            .find(|e| e.opcode == 50 && e.fields["reason"].as_u64().unwrap_or(0) & 128 != 0)
            .unwrap()
            .fields["reason"] = serde_json::json!(0);
        assert!(reconstruct(&bad, &cat, &pack).is_err());
    }
    #[test]
    fn material_instances_and_xyz_history_come_from_raw_engine_moves() {
        let (mut r, cat, pack) = load(include_str!(
            "../../../../tests/fixtures/break-material-anchor.events.json"
        ));
        assert_eq!(r.protocol_version, 3);
        r.protocol_version = 5;
        let s = rebuild(&r, &cat, &pack).unwrap();
        let host = s
            .cards
            .iter()
            .find(|c| c.code == 62709239 && c.location == 4)
            .unwrap();
        assert!(host.xyz_summoned);
        let mats: Vec<_> = s
            .cards
            .iter()
            .filter(|m| m.overlay_host.as_deref() == Some(&host.instance))
            .collect();
        assert_eq!(mats.len(), 2);
        assert_ne!(mats[0].instance, mats[1].instance);
    }
    #[test]
    fn revived_levels_dark_lock_and_soft_usage_do_not_reset_at_anchor() {
        let (mut r, cat, pack) = load(include_str!(
            "../../../../tests/fixtures/break-restored-anchor.events.json"
        ));
        assert_eq!(r.protocol_version, 3);
        r.protocol_version = 5;
        let s = rebuild(&r, &cat, &pack).unwrap();
        assert!(s.dark_only);
        assert_eq!(
            s.cards
                .iter()
                .filter(|c| c.player == 0 && c.location == 4 && c.level == 4 && c.base_level == 3)
                .count(),
            2
        );
        let host = s
            .cards
            .iter()
            .find(|c| c.code == 62709239 && c.location == 16)
            .unwrap();
        assert_eq!(host.epoch, 1);
        assert!(s.used.contains(&format!("break:{}:0", host.instance)));
        assert!(!s.used.contains(&format!("break:{}:1", host.instance)));
        assert!(!s
            .cards
            .iter()
            .any(|m| m.overlay_host.as_deref() == Some(&host.instance)));
    }
}
