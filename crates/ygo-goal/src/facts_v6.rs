//! Protocol v6 reconstruction; legacy history/identity paths remain unchanged.
use crate::{FactCard, Facts, HistoryFact};
use std::collections::BTreeMap;
use ygo_domain::{CardId, Catalog};
use ygo_engine_adapter::{prompt_metadata, Choice, DuelResult};
use ygo_knowledge::first_turn::{FirstTurnKnowledge, Operation};
mod evidence;
pub use evidence::*;
use evidence::{from_query, public_location, reconcile, validate_evidence};

fn snapshot(card: &FactCard, tracked: &[FactCard], hosts: &BTreeMap<String, String>) -> FactCard {
    let mut c = card.clone();
    c.materials = tracked
        .iter()
        .filter(|m| c.location == 4 && hosts.get(&m.instance) == Some(&c.instance))
        .map(|m| m.code)
        .collect();
    c
}

/// Reconstruct instance history from raw decoded moves and successful summon/chain events.
/// Unresolvable identities remain unknown; proposal history is never consulted.
pub fn actual_trace_v6(
    result: &DuelResult,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
    witnesses: &[QueryWitness],
) -> Result<FirstTurnTrace, String> {
    validate_evidence(result, witnesses)?;
    let first = &witnesses[0];
    let mut tracked: Vec<FactCard> = first
        .public
        .visible
        .cards
        .iter()
        .map(|c| {
            from_query(
                c,
                format!("observed:{}:{}:{}:0", c.player, c.location, c.sequence),
                true,
                Some(false),
            )
        })
        .collect();
    let mut hosts: BTreeMap<String, String> = BTreeMap::new();
    let mut activations = vec![];
    let mut chain_activation = BTreeMap::new();
    let mut movements = vec![];
    let mut draws = vec![];
    let mut hand_count = [5usize, first.public.opponent_hand_count];
    let mut epochs = tracked
        .iter()
        .map(|c| (c.instance.clone(), 0u64))
        .collect::<BTreeMap<_, _>>();
    let mut history = vec![];
    let mut chains: BTreeMap<u64, (FactCard, Option<String>)> = BTreeMap::new();
    let mut finalized_chains = std::collections::BTreeSet::new();
    let mut negated_chains = std::collections::BTreeSet::new();
    let mut summoning: Vec<(FactCard, bool, u64)> = vec![];
    let mut opaque_summon = false;
    let mut pending_activations: Vec<(u32, u64, FactCard)> = vec![];
    let mut chain_open = false;
    for e in result.events.iter().filter(|e| e.sequence >= first.event) {
        if e.opcode == 70 {
            chain_open = true;
        }
        if e.opcode == 74 {
            chain_open = false;
        }
        if let Some(w) = witnesses.iter().find(|w| w.event == e.sequence) {
            reconcile(&mut tracked, &w.public.visible.cards);
        }
        let n = |v: &serde_json::Value, k: &str| v[k].as_u64().unwrap_or(0) as u32;
        if e.opcode == 90 {
            let player = n(&e.fields, "player") as u8;
            let cards = e.fields["cards"]
                .as_array()
                .ok_or("draw lacks card records")?;
            if player > 1 {
                return Err("invalid draw player".into());
            }
            let mut exposed = vec![];
            for (i, raw) in cards.iter().enumerate() {
                if player == 0 {
                    let code = n(raw, "code") & 0x7fffffff;
                    let instance = format!("draw:{}:{i}", e.sequence);
                    tracked.push(FactCard {
                        instance: instance.clone(),
                        identity_known: code != 0,
                        code,
                        player,
                        location: 2,
                        sequence: hand_count[0] as u32,
                        position: n(raw, "position"),
                        proper_xyz: Some(false),
                        ..Default::default()
                    });
                    epochs.insert(instance, 0);
                    exposed.push(code);
                }
                hand_count[player as usize] += 1;
            }
            draws.push(DrawWitness {
                event: e.sequence,
                player,
                count: cards.len(),
                cards: exposed,
            });
        }
        if e.opcode == 53 {
            for c in tracked.iter_mut().filter(|c| {
                c.code == n(&e.fields, "code")
                    && c.player == n(&e.fields, "player") as u8
                    && c.location == n(&e.fields, "location") as u8
                    && c.sequence == n(&e.fields, "sequence")
            }) {
                c.position = n(&e.fields, "position");
            }
        }
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
                                materials_complete: Some(false),
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
            for (loc, entering) in [(from, false), (to, true)] {
                if n(loc, "location") == 2 {
                    let count = &mut hand_count[n(loc, "player") as usize];
                    if entering {
                        *count += 1;
                    } else {
                        *count = count.saturating_sub(1);
                    }
                }
            }
            let old = tracked.iter().position(|c| {
                c.code == code
                    && c.player == n(from, "player") as u8
                    && c.location == n(from, "location") as u8
                    && c.sequence == n(from, "sequence")
                    && (c.location & 128 == 0 || c.position == n(from, "position"))
            });
            let mut c = old.map(|i| tracked.remove(i)).unwrap_or_else(|| FactCard {
                materials_complete: Some(false),
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
            if result.protocol_version >= 4 {
                for (source, _) in chains.values_mut() {
                    if !source.identity_known
                        && source.code == code
                        && source.player == n(from, "player") as u8
                        && source.location == n(from, "location") as u8
                        && source.sequence == n(from, "sequence")
                    {
                        source.instance = c.instance.clone();
                        source.identity_known = c.identity_known;
                    }
                }
            }
            // Destruction observes the origin before overlays follow their host.
            let mut origin = snapshot(&c, &tracked, &hosts);
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
                    && other.location == n(from, "location") as u8
                    && other.sequence == n(from, "sequence")
                    && other.position > n(from, "position")
                {
                    other.position -= 1;
                }
            }
            if n(to, "location") & 128 != 0 {
                let targets = tracked
                    .iter()
                    .filter(|h| {
                        h.player == n(to, "player") as u8
                            && h.location == (n(to, "location") as u8 & 127)
                            && h.sequence == n(to, "sequence")
                    })
                    .collect::<Vec<_>>();
                if targets.len() == 1 && targets[0].identity_known {
                    hosts.insert(c.instance.clone(), targets[0].instance.clone());
                } else {
                    c.identity_known = false;
                    opaque_summon = true;
                }
            } else {
                hosts.remove(&c.instance);
            }
            if matches!(n(to, "location"), 4 | 64) {
                for child in tracked
                    .iter_mut()
                    .filter(|m| hosts.get(&m.instance) == Some(&c.instance))
                {
                    child.player = n(to, "player") as u8;
                    child.location = n(to, "location") as u8 | 128;
                    child.sequence = n(to, "sequence");
                }
            }
            let epoch = epochs.entry(c.instance.clone()).or_default();
            let previous_epoch = *epoch;
            if n(from, "location") == 4 && n(to, "location") != 4 {
                *epoch += 1;
            }
            movements.push(MovementWitness {
                instance: c.instance.clone(),
                identity_known: c.identity_known,
                event: e.sequence,
                reason: n(&e.fields, "reason"),
                from: public_location(from),
                to: public_location(to),
                epoch_before: previous_epoch,
                epoch_after: *epoch,
            });
            if n(from, "location") != n(to, "location") {
                c.level = None;
                c.rank = None;
                c.type_flags = 0;
            }
            c.player = n(to, "player") as u8;
            c.location = n(to, "location") as u8;
            c.sequence = n(to, "sequence");
            c.position = n(to, "position");
            c = snapshot(&c, &tracked, &hosts);
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
                    snapshot(candidates[0], &tracked, &hosts),
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
                let materials = snapshot(&source, &tracked, &hosts).materials;
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
                    let known_xyz = pack.rules.iter().any(|r| {
                        r.card_id == code && r.applicable && r.operation == Operation::XyzProcedure
                    });
                    let known_link = pack.rules.iter().any(|r| {
                        r.card_id == code && r.applicable && r.operation == Operation::LinkProcedure
                    });
                    if procedure
                        && ((flags & 0x800000 != 0 && !known_xyz)
                            || (flags & 0x4000000 != 0 && !known_link))
                    {
                        opaque_summon = true;
                    }
                    let xyz = special && procedure && flags & 0x800000 != 0 && known_xyz;
                    let link = special && procedure && flags & 0x4000000 != 0 && known_link;
                    c.proper_xyz =
                        if flags & 0x800000 != 0 && (!known_xyz || (from_extra && !procedure)) {
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
            let loc = &e.fields["location"];
            let pending_index = pending_activations
                .iter()
                .rposition(|(c, d, _)| *c == code && *d == desc);
            // CHAINING carries the original trigger range separately from the
            // handler's current location after paying a banish/discard cost.
            let source_location = n(&e.fields, "trigger_location") as u8;
            let matching = pack
                .rules
                .iter()
                .filter(|r| {
                    r.applicable
                        && r.card_id == code
                        && r.description == Some(desc)
                        && r.source_locations & source_location != 0
                })
                .collect::<Vec<_>>();
            let id = (matching.len() == 1).then(|| matching[0].id.clone());
            let pending = pending_index.map(|i| pending_activations.remove(i).2);
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
                    materials_complete: Some(false),
                    instance: format!("chain:{}", e.sequence),
                    code,
                    player: n(loc, "player") as u8,
                    location: n(loc, "location") as u8,
                    sequence: n(loc, "sequence"),
                    ..Default::default()
                });
            // Bind identity/activation zone at CHAINING. CHAINED below is
            // emitted after cost and target selection and finalizes materials.
            if let Some(current) = tracked.iter().find(|x| x.instance == c.instance) {
                c.materials = snapshot(current, &tracked, &hosts).materials;
            } else {
                c.materials.clear();
                c.materials_complete = Some(false);
                c.identity_known = false;
                // V4 may observe CHAINING before a hand source pays its cost.
                // Finalization at CHAINED must still resolve that exact instance.
                if result.protocol_version < 4 {
                    opaque_summon = true;
                }
            }
            // A spell offered in hand activates in the spell/trap zone.
            // Preserve its pinned identity, not the pre-command coordinates.
            let before_cost = c.clone();
            c.player = n(&e.fields, "player") as u8;
            c.location = source_location;
            c.sequence = n(&e.fields, "sequence");
            let chain = e.fields["chain"].as_u64().unwrap_or(0);
            chain_activation.insert(chain, activations.len());
            activations.push(ActivationWitness {
                event: e.sequence,
                chain,
                rule_id: id.clone(),
                source: before_cost,
                after_cost: None,
                resolved: false,
                negated: false,
                activation_negated: false,
                solving_event: None,
                resolution_event: None,
            });
            if id.is_none() {
                opaque_summon = true;
            }
            chains.insert(chain, (c, id));
        }
        if e.opcode == 71 {
            let chain = e.fields["chain"].as_u64().unwrap_or(0);
            if let Some((source, _)) = chains.get_mut(&chain) {
                if let Some(current) = tracked.iter().find(|x| x.instance == source.instance) {
                    source.materials = snapshot(current, &tracked, &hosts).materials;
                    finalized_chains.insert(chain);
                } else if source.location == 2 {
                    // A hand trigger without a cost moves only during resolution.
                    // MOVE must still pin its exact identity before CHAIN_SOLVED.
                    source.materials.clear();
                    finalized_chains.insert(chain);
                } else {
                    source.materials.clear();
                    source.materials_complete = Some(false);
                    source.identity_known = false;
                    opaque_summon = true;
                }
            } else {
                opaque_summon = true;
            }
        }
        if e.opcode == 71 {
            let chain = e.fields["chain"].as_u64().unwrap_or(0);
            if let (Some(i), Some((source, _))) = (chain_activation.get(&chain), chains.get(&chain))
            {
                activations[*i].after_cost = Some(
                    tracked
                        .iter()
                        .find(|c| c.instance == source.instance)
                        .map(|c| snapshot(c, &tracked, &hosts))
                        .unwrap_or_else(|| source.clone()),
                );
            }
        }
        if e.opcode == 72 {
            if let Some(i) = chain_activation.get(&e.fields["chain"].as_u64().unwrap_or(0)) {
                activations[*i].solving_event = Some(e.sequence);
            } else {
                opaque_summon = true;
            }
        }
        if e.opcode == 73 {
            let chain = e.fields["chain"].as_u64().unwrap_or(0);
            if result.protocol_version >= 4 && negated_chains.remove(&chain) {
                continue;
            }
            if !chain_activation
                .get(&chain)
                .is_some_and(|i| activations[*i].solving_event.is_some())
            {
                opaque_summon = true;
                chains.remove(&chain);
                finalized_chains.remove(&chain);
                continue;
            }
            if let Some((mut c, id)) = chains.remove(&chain) {
                if !finalized_chains.remove(&chain) {
                    c.materials.clear();
                    c.materials_complete = Some(false);
                    opaque_summon = true;
                }
                if result.protocol_version == 5 && !c.identity_known {
                    opaque_summon = true;
                }
                if let Some(i) = chain_activation.get(&chain) {
                    activations[*i].resolved = true;
                    activations[*i].resolution_event = Some(e.sequence);
                }
                history.push(HistoryFact {
                    kind: "effect_resolved".into(),
                    card: c,
                    effect_id: id,
                    reason: 0,
                    reason_complete: true,
                    event: e.sequence,
                });
            } else {
                opaque_summon = true;
            }
        }
        if matches!(e.opcode, 75 | 76) {
            let chain = e.fields["chain"].as_u64().unwrap_or(0);
            if let Some(i) = chain_activation.get(&chain) {
                activations[*i].negated = true;
                activations[*i].activation_negated = e.opcode == 75;
                activations[*i].resolution_event = Some(e.sequence);
            }
            if result.protocol_version >= 4 {
                if !finalized_chains.contains(&chain) {
                    opaque_summon = true;
                }
                if let Some((c, id)) = chains.get(&chain) {
                    history.push(HistoryFact {
                        kind: if e.opcode == 76 {
                            "effect_negated"
                        } else {
                            "activation_negated"
                        }
                        .into(),
                        card: c.clone(),
                        effect_id: id.clone(),
                        reason: 0,
                        reason_complete: true,
                        event: e.sequence,
                    });
                    negated_chains.insert(chain);
                } else {
                    opaque_summon = true;
                }
            }
            chains.remove(&chain);
            finalized_chains.remove(&chain);
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
    let public = ygo_engine_adapter::first_turn_public_state(&result.checkpoint);
    let cards = public
        .visible
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
                materials_complete: Some(true),
            }
        })
        .collect();
    let known_effects = pack
        .rules
        .iter()
        .filter(|r| r.applicable && r.description.is_some())
        .map(|r| r.id.clone())
        .collect();
    let material_instances = tracked
        .iter()
        .filter(|c| c.location == 132)
        .cloned()
        .collect();
    let (normal_remaining, used) = usage_from_trace(result, pack, &activations);
    let closed = !chain_open && chains.is_empty() && summoning.is_empty();
    let window = if !closed {
        TraceWindow::Pending
    } else if result.error.is_none()
        && result.status == ygo_engine_adapter::DuelStatus::DecisionRequired
        && result.prompt.as_ref().is_some_and(|p| {
            p.player == 0
                && p.opcode == 11
                && result.events.last().is_some_and(|e| e.sequence == p.id)
        })
        && result.checkpoint.turn == 1
        && result.checkpoint.turn_player == 0
        && result.checkpoint.phase == 4
    {
        TraceWindow::OwnMainAction
    } else if result.status == ygo_engine_adapter::DuelStatus::EngineVerified
        && result.error.is_none()
        && result
            .events
            .iter()
            .any(|e| e.opcode == 41 && e.fields["phase"] == 512)
        && result
            .events
            .iter()
            .any(|e| e.opcode == 40 && e.fields["player"] == 1)
    {
        TraceWindow::OwnTurnEnded
    } else {
        TraceWindow::Unknown
    };
    Ok(FirstTurnTrace {
        facts: Facts {
            known_effects,
            cards,
            history,
            history_complete: !opaque_summon
                && closed
                && result.coverage_gaps.is_empty()
                && result.error.is_none()
                && result.status != ygo_engine_adapter::DuelStatus::Failed,
        },
        material_instances,
        activations,
        movements,
        epochs,
        normal_remaining,
        used,
        draws,
        window,
    })
}

fn usage_from_trace(
    result: &DuelResult,
    pack: &FirstTurnKnowledge,
    activations: &[ActivationWitness],
) -> (Option<u8>, BTreeMap<String, usize>) {
    let mut used = BTreeMap::new();
    let mut normal = Some(1u8);
    for a in activations {
        let Some(rule) = a.rule_id.as_deref().and_then(|id| pack.rule(id)) else {
            normal = None;
            continue;
        };
        let key = match rule.usage.scope.as_str() {
            "name_use" => rule.usage.key.clone(),
            "name_activation" if !a.activation_negated => rule.usage.key.clone(),
            "shared_mulcharmy_activation" => Some("shared_mulcharmy_activation".into()),
            _ => None,
        };
        if let Some(key) = key {
            *used.entry(key).or_default() += 1;
        }
    }
    for e in &result.events {
        if e.opcode == 60 && e.fields["location"]["player"] == 0 {
            normal = normal.map(|v| v.saturating_sub(1));
        }
        if !matches!(e.opcode, 54 | 62) {
            continue;
        }
        let Some(m) = result
            .resolved_decisions
            .iter()
            .filter(|d| d.prompt_id < e.sequence && d.player == 0)
            .rev()
            .find_map(|d| {
                let event = &result.events[d.prompt_id as usize - 1];
                (event.opcode == 11)
                    .then(|| prompt_metadata(event.sequence, &event.raw).ok())
                    .flatten()
                    .and_then(|ms| ms.into_iter().find(|m| m.choice == d.choice))
            })
        else {
            continue;
        };
        let Some(source) = m.source else {
            continue;
        };
        if source.code as u64 != e.fields["code"].as_u64().unwrap_or(0)
            || source.location != 2
            || e.fields["location"]["player"] != 0
        {
            continue;
        }
        if e.opcode == 54 && matches!(m.choice, Choice::Command { command: 3, .. }) {
            normal = normal.map(|v| v.saturating_sub(1));
        }
        if e.opcode == 62 && matches!(m.choice, Choice::Command { command: 1, .. }) {
            let rules = pack
                .rules
                .iter()
                .filter(|r| {
                    r.card_id == source.code && r.usage.scope == "name_procedure" && r.applicable
                })
                .collect::<Vec<_>>();
            if rules.len() == 1 {
                if let Some(key) = &rules[0].usage.key {
                    *used.entry(key.clone()).or_default() += 1;
                }
            }
        }
    }
    (normal, used)
}
