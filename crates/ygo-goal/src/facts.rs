use crate::{FactCard, Facts, HistoryFact};
use std::collections::BTreeMap;
use ygo_domain::{CardId, Catalog};
use ygo_engine_adapter::{prompt_metadata, Choice, DuelResult};
use ygo_knowledge::KnowledgePack;

fn snapshot(card: &FactCard, tracked: &[FactCard]) -> FactCard {
    let mut c = card.clone();
    c.materials = tracked
        .iter()
        .filter(|m| {
            c.location == 4 && m.player == c.player && m.location == 132 && m.sequence == c.sequence
        })
        .map(|m| m.code)
        .collect();
    c
}

/// Reconstruct instance history from raw decoded moves and successful summon/chain events.
/// Unresolvable identities remain unknown; proposal history is never consulted.
pub fn actual_facts(result: &DuelResult, cat: &Catalog, pack: &KnowledgePack) -> Facts {
    let mut tracked: Vec<FactCard> = vec![];
    let mut history = vec![];
    let mut chains: BTreeMap<u64, (FactCard, Option<String>)> = BTreeMap::new();
    let mut summoning: Vec<(FactCard, bool, u64)> = vec![];
    let mut opaque_summon = false;
    let mut pending_activations: Vec<(u32, u64, FactCard)> = vec![];
    for e in &result.events {
        let n = |v: &serde_json::Value, k: &str| v[k].as_u64().unwrap_or(0) as u32;
        if let Some(d) = result
            .resolved_decisions
            .iter()
            .find(|d| d.prompt_id == e.sequence)
        {
            if let Ok(ms) = prompt_metadata(e.sequence, &e.raw) {
                if let Some(m) = ms.iter().find(|m| {
                    m.choice == d.choice
                        && matches!(
                            m.choice,
                            Choice::Command { command: 5, .. }
                                | Choice::Chain { index: Some(_) }
                                | Choice::YesNo { yes: true }
                        )
                }) {
                    if let (Some(source), Some(desc)) = (&m.source, m.effect_description) {
                        let c = tracked
                            .iter()
                            .find(|c| {
                                c.code == source.code
                                    && c.player == source.player
                                    && c.location == source.location
                                    && c.sequence == source.sequence
                            })
                            .cloned()
                            .unwrap_or_else(|| FactCard {
                                instance: format!("activation:{}", e.sequence),
                                code: source.code,
                                player: source.player,
                                location: source.location,
                                sequence: source.sequence,
                                ..Default::default()
                            });
                        pending_activations.push((source.code, desc, c));
                    }
                }
            }
        }
        if e.opcode == 50 {
            let code = n(&e.fields, "code");
            let from = &e.fields["from"];
            let to = &e.fields["to"];
            let old = tracked.iter().position(|c| {
                c.code == code
                    && c.player == n(from, "player") as u8
                    && c.location == n(from, "location") as u8
                    && c.sequence == n(from, "sequence")
                    && (c.location & 128 == 0 || c.position == n(from, "position"))
            });
            let mut c = old.map(|i| tracked.remove(i)).unwrap_or_else(|| FactCard {
                instance: format!("observed:{}", e.sequence),
                identity_known: !tracked.iter().any(|c| {
                    c.code == code
                        && c.player == n(from, "player") as u8
                        && c.location == n(from, "location") as u8
                        && c.sequence == u32::MAX
                }),
                code,
                proper_xyz: Some(false),
                ..Default::default()
            });
            // Initial hand cards need not have a preceding MOVE. Pin a source
            // observed in its legal prompt to its subsequent exact MOVE, rather
            // than abandoning that identity or guessing by card name at CHAINING.
            for (activation_code, _, source) in &mut pending_activations {
                if !source.identity_known
                    && *activation_code == code
                    && source.player == n(from, "player") as u8
                    && source.location == n(from, "location") as u8
                    && source.sequence == n(from, "sequence")
                {
                    source.instance = c.instance.clone();
                    source.identity_known = c.identity_known;
                }
            }
            // Destruction observes the origin before overlays follow their host.
            let mut origin = snapshot(&c, &tracked);
            origin.player = n(from, "player") as u8;
            origin.location = n(from, "location") as u8;
            origin.sequence = n(from, "sequence");
            origin.position = n(from, "position");
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
            c = snapshot(&c, &tracked);
            if c.location == 4 && n(from, "location") != 4 {
                c.proper_xyz = Some(false);
            }
            let reason = n(&e.fields, "reason");
            if c.location == 16 {
                history.push(HistoryFact {
                    kind: "sent_to_grave".into(),
                    card: c.clone(),
                    effect_id: None,
                    reason,
                    reason_complete: true,
                    event: e.sequence,
                });
            }
            if reason & 1 != 0 {
                history.push(HistoryFact {
                    kind: "destroyed".into(),
                    card: origin,
                    effect_id: None,
                    reason,
                    reason_complete: true,
                    event: e.sequence,
                });
            }
            tracked.push(c);
        }
        if matches!(e.opcode, 60 | 62) {
            let loc = &e.fields["location"];
            let candidates: Vec<_> = tracked
                .iter()
                .filter(|c| {
                    c.code == n(&e.fields, "code")
                        && c.player == n(loc, "player") as u8
                        && c.location == n(loc, "location") as u8
                        && c.sequence == n(loc, "sequence")
                })
                .collect();
            if candidates.len() == 1 && candidates[0].identity_known {
                summoning.push((
                    snapshot(candidates[0], &tracked),
                    e.opcode == 62,
                    e.sequence,
                ));
            } else {
                opaque_summon = true;
            }
        }
        if matches!(e.opcode, 61 | 63) {
            if summoning.is_empty() {
                opaque_summon = true;
            }
            let mut seen = std::collections::BTreeSet::new();
            for (source, special, begin) in std::mem::take(&mut summoning) {
                if special != (e.opcode == 63) || !seen.insert(source.instance.clone()) {
                    opaque_summon = true;
                    continue;
                }
                let materials = snapshot(&source, &tracked).materials;
                if let Some(c) = tracked.iter_mut().find(|c| {
                    c.instance == source.instance
                        && c.player == source.player
                        && c.sequence == source.sequence
                        && c.location == 4
                }) {
                    let code = c.code;
                    let last_move = result.events.iter().rev().find(|f| {
                        f.sequence < begin
                            && f.opcode == 50
                            && f.fields["code"].as_u64() == Some(code as u64)
                            && f.fields["to"]["location"] == 4
                            && f.fields["to"]["player"] == source.player
                            && f.fields["to"]["sequence"] == source.sequence
                    });
                    let from_extra = last_move.is_some_and(|f| f.fields["from"]["location"] == 64);
                    let procedure = from_extra
                        && result
                            .resolved_decisions
                            .iter()
                            .filter(|d| d.prompt_id < begin)
                            .rev()
                            .find_map(|d| {
                                result
                                    .events
                                    .iter()
                                    .find(|f| f.sequence == d.prompt_id && f.opcode == 11)
                                    .and_then(|f| prompt_metadata(f.sequence, &f.raw).ok())
                                    .and_then(|ms| ms.into_iter().find(|m| m.choice == d.choice))
                            })
                            .is_some_and(|m| {
                                matches!(m.choice, Choice::Command { command: 1, .. })
                                    && m.source.is_some_and(|s| s.code == code && s.location == 64)
                            });
                    let flags = cat.get(&CardId(code)).map_or_else(
                        || {
                            result
                                .checkpoint
                                .cards
                                .iter()
                                .find(|c| c.code == code)
                                .map_or(0, |c| c.type_flags)
                        },
                        |c| c.type_flags,
                    );
                    let known_xyz = pack.card(code).is_some_and(|k| {
                        k.effects.iter().any(|e| {
                            matches!(
                                e.rule,
                                ygo_knowledge::Rule::BreakDestroy
                                    | ygo_knowledge::Rule::BreakRevive
                            )
                        })
                    });
                    let known_link = pack.card(code).is_some_and(|k| {
                        k.effects.iter().any(|e| {
                            matches!(
                                e.rule,
                                ygo_knowledge::Rule::CherubiniMill
                                    | ygo_knowledge::Rule::RustyMillSet
                            )
                        })
                    });
                    if procedure
                        && ((flags & 0x800000 != 0 && !known_xyz)
                            || (flags & 0x4000000 != 0 && !known_link))
                    {
                        opaque_summon = true;
                    }
                    let xyz = special && procedure && flags & 0x800000 != 0 && known_xyz;
                    let link = special && procedure && flags & 0x4000000 != 0 && known_link;
                    c.proper_xyz = if flags & 0x800000 != 0 && !known_xyz {
                        None
                    } else {
                        Some(xyz)
                    };
                    c.type_flags = flags;
                    c.materials = materials;
                    history.push(HistoryFact {
                        kind: if special {
                            "special_summon"
                        } else {
                            "normal_summon"
                        }
                        .into(),
                        card: c.clone(),
                        effect_id: None,
                        reason: 0,
                        reason_complete: true,
                        event: e.sequence,
                    });
                    if xyz || link {
                        history.push(HistoryFact {
                            kind: if xyz { "xyz_summon" } else { "link_summon" }.into(),
                            card: c.clone(),
                            effect_id: None,
                            reason: 0,
                            reason_complete: true,
                            event: e.sequence,
                        });
                    }
                } else {
                    opaque_summon = true;
                }
            }
        }
        if e.opcode == 70 {
            let code = n(&e.fields, "code");
            let desc = e.fields["description"].as_u64().unwrap_or(0);
            let id = pack
                .card(code)
                .and_then(|c| {
                    c.effects
                        .iter()
                        .find(|x| matches_description(x, code, desc))
                })
                .map(|x| x.id.clone());
            let loc = &e.fields["location"];
            let pending = pending_activations
                .iter()
                .rposition(|(c, d, _)| {
                    *c == code
                        && (*d == desc
                            || id.as_ref().is_some_and(|eid| {
                                pack.effect(eid)
                                    .is_some_and(|effect| matches_description(effect, code, *d))
                            }))
                })
                .map(|i| pending_activations.remove(i).2);
            let mut c = pending
                .or_else(|| {
                    tracked
                        .iter()
                        .find(|c| {
                            c.code == code
                                && c.player == n(loc, "player") as u8
                                && c.location == n(loc, "location") as u8
                                && c.sequence == n(loc, "sequence")
                        })
                        .cloned()
                })
                .unwrap_or_else(|| FactCard {
                    instance: format!("chain:{}", e.sequence),
                    code,
                    player: n(loc, "player") as u8,
                    location: n(loc, "location") as u8,
                    sequence: n(loc, "sequence"),
                    ..Default::default()
                });
            // Keep the pre-cost source identity/activation zone, but sample
            // materials after cost payment at CHAINING, not at summon time.
            if let Some(current) = tracked.iter().find(|x| x.instance == c.instance) {
                c.materials = snapshot(current, &tracked).materials;
            } else {
                c.materials.clear();
                c.identity_known = false;
                opaque_summon = true;
            }
            chains.insert(e.fields["chain"].as_u64().unwrap_or(0), (c, id));
        }
        if e.opcode == 73 {
            if let Some((c, id)) = chains.remove(&e.fields["chain"].as_u64().unwrap_or(0)) {
                history.push(HistoryFact {
                    kind: "effect_resolved".into(),
                    card: c,
                    effect_id: id,
                    reason: 0,
                    reason_complete: true,
                    event: e.sequence,
                });
            }
        }
        if matches!(e.opcode, 75 | 76) {
            chains.remove(&e.fields["chain"].as_u64().unwrap_or(0));
        }
        if e.opcode == 33 {
            for c in tracked
                .iter_mut()
                .filter(|c| c.location == 2 && c.player == n(&e.fields, "player") as u8)
            {
                let codes = e.fields["cards"].as_array().cloned().unwrap_or_default();
                let positions: Vec<_> = codes
                    .iter()
                    .enumerate()
                    .filter(|(_, code)| code.as_u64() == Some(c.code as u64))
                    .map(|(i, _)| i as u32)
                    .collect();
                c.sequence = if positions.len() == 1 {
                    positions[0]
                } else {
                    c.identity_known = false;
                    u32::MAX
                };
            }
        }
    }
    let cards = result
        .checkpoint
        .cards
        .iter()
        .map(|c| {
            let matches: Vec<_> = tracked
                .iter()
                .filter(|x| {
                    x.code == c.code
                        && x.player == c.player
                        && x.location == c.location
                        && x.sequence == c.sequence
                })
                .collect();
            let known = if matches.len() == 1 {
                Some(matches[0])
            } else {
                None
            };
            FactCard {
                instance: known.map_or_else(
                    || format!("checkpoint:{}:{}:{}", c.player, c.location, c.sequence),
                    |x| x.instance.clone(),
                ),
                identity_known: known.is_some_and(|c| c.identity_known),
                type_flags: c.type_flags,
                code: c.code,
                player: c.player,
                location: c.location,
                sequence: c.sequence,
                position: c.position,
                level: c.level,
                rank: c.rank,
                proper_xyz: known.and_then(|c| c.proper_xyz),
                materials: c.overlay.clone(),
            }
        })
        .collect();
    let known_effects = pack
        .cards
        .iter()
        .flat_map(|c| c.effects.iter())
        .filter(|e| e.description_index.is_some())
        .map(|e| e.id.clone())
        .collect();
    Facts {
        known_effects,
        cards,
        history,
        history_complete: !opaque_summon
            && summoning.is_empty()
            && result.coverage_gaps.is_empty()
            && result.error.is_none()
            && result.status != ygo_engine_adapter::DuelStatus::Failed,
    }
}

/// The frozen Lua runtime uses code << 20; non-described spell activations use zero.
pub fn matches_description(effect: &ygo_knowledge::Effect, code: u32, description: u64) -> bool {
    effect
        .description_index
        .is_some_and(|i| description == ((code as u64) << 20) + i)
        || (description == 0
            && matches!(
                effect.rule,
                ygo_knowledge::Rule::Rota
                    | ygo_knowledge::Rule::Fool
                    | ygo_knowledge::Rule::Brigandine
            ))
}
