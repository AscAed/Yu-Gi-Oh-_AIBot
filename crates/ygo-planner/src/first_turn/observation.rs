//! Actual-prefix state construction. Imported results must be independently
//! replayed by the caller; this constructor does not grant native verification.
use super::*;
use ygo_engine_adapter::{first_turn_public_state, DuelResult};
use ygo_goal::{actual_trace_v6, FirstTurnTrace, QueryWitness, TraceWindow};

pub struct ObservedState {
    pub state: CausalState,
    pub trace: FirstTurnTrace,
    pub public: FirstTurnPublicState,
}

pub fn actual_state(
    result: &DuelResult,
    witnesses: &[QueryWitness],
    catalog: &Catalog,
    pack: &FirstTurnKnowledge,
) -> Result<ObservedState, String> {
    let trace = actual_trace_v6(result, catalog, pack, witnesses)?;
    if trace.window != TraceWindow::OwnMainAction {
        return Err("actual state requires a closed own main action window".into());
    }
    if !trace.facts.history_complete || trace.normal_remaining.is_none() {
        return Err("incomplete actual history cannot establish recovery resources".into());
    }
    if !trace.restrictions.unknown_rules.is_empty() {
        return Err(format!(
            "unmodeled actual restrictions: {}",
            trace.restrictions.unknown_rules.join(",")
        ));
    }
    let public = first_turn_public_state(&result.checkpoint);
    let mut cards = Vec::new();
    for card in &public.visible.cards {
        let base = catalog
            .get(&CardId(card.code))
            .ok_or_else(|| format!("missing printed card metadata: {}", card.code))?;
        let fact = trace
            .facts
            .cards
            .iter()
            .find(|f| {
                f.player == card.player
                    && f.location == card.location
                    && f.sequence == card.sequence
                    && f.code == card.code
            })
            .ok_or("query card lacks its actual identity record")?;
        let set_this_turn = if card.location == 8 {
            trace
                .movements
                .iter()
                .rev()
                .find(|m| m.instance == fact.instance && m.to.location == 8)
                .map(|m| m.to.position.is_some_and(|p| p & 10 != 0))
        } else {
            Some(false)
        };
        cards.push(KnownInstance {
            id: fact.instance.clone(),
            identity_known: fact.identity_known,
            attributes_known: card.type_flags != 0
                && card.level.is_some()
                && card.rank.is_some()
                && card.attribute.is_some()
                && card.race.is_some(),
            card: card.clone(),
            printed: PrintedAttributes::for_catalog(base),
            host: None,
            epoch: trace.epochs.get(&fact.instance).copied().unwrap_or(0),
            set_this_turn,
            leave_field_banish: trace
                .restrictions
                .leave_field_banish
                .get(&fact.instance)
                .copied()
                .unwrap_or(None),
            proper_xyz: fact.proper_xyz,
            rank_as_level: trace
                .restrictions
                .rank_as_level
                .get(&fact.instance)
                .copied()
                .unwrap_or(None),
        });
    }
    for material in &trace.material_instances {
        let host = trace
            .material_hosts
            .get(&material.instance)
            .ok_or("actual material lacks its host identity")?;
        let parent = cards
            .iter()
            .find(|c| c.id == *host && c.card.location == 4)
            .ok_or("actual material host is not currently on field")?;
        let base = catalog
            .get(&CardId(material.code))
            .ok_or_else(|| format!("missing printed card metadata: {}", material.code))?;
        cards.push(KnownInstance {
            id: material.instance.clone(),
            identity_known: material.identity_known,
            attributes_known: false,
            card: StateCard {
                code: material.code,
                player: parent.card.player,
                location: 132,
                sequence: parent.card.sequence,
                position: material.position,
                ..Default::default()
            },
            printed: PrintedAttributes::for_catalog(base),
            host: Some(host.clone()),
            epoch: trace.epochs.get(&material.instance).copied().unwrap_or(0),
            set_this_turn: Some(false),
            leave_field_banish: Some(false),
            proper_xyz: material.proper_xyz,
            rank_as_level: Some(false),
        });
    }
    let state = CausalState {
        cards,
        deck_counts: public.own_deck_counts.clone(),
        normal_remaining: trace.normal_remaining,
        used: trace.used.clone(),
        pending: vec![],
        special_allowed: trace.restrictions.special_allowed,
        dark_only: trace.restrictions.dark_only,
        extra_xyz_only: trace.restrictions.extra_xyz_only,
        next_entity: 0,
    };
    state.validate(catalog)?;
    let initial = &witnesses[0].public;
    let total = |visible: &FirstTurnPublicState| -> Option<usize> {
        let cards = visible
            .visible
            .cards
            .iter()
            .filter(|c| c.player == 0)
            .try_fold(0usize, |n, c| {
                n.checked_add(1)?.checked_add(c.overlay.len())
            })?;
        visible
            .own_deck_counts
            .values()
            .try_fold(cards, |n, k| n.checked_add(*k))
    };
    if total(initial).is_none() || total(initial) != total(&public) {
        return Err("actual own-card resource conservation differs from initial witness".into());
    }
    Ok(ObservedState {
        state,
        trace,
        public,
    })
}
