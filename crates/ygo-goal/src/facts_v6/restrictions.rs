//! Actual restriction reconstruction, never a predicted step.after state.
use super::*;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ActualRestrictions {
    pub special_allowed: Option<bool>,
    pub dark_only: Option<bool>,
    pub extra_xyz_only: Option<bool>,
    pub leave_field_banish: BTreeMap<String, Option<bool>>,
    pub rank_as_level: BTreeMap<String, Option<bool>>,
    pub unknown_rules: Vec<String>,
}

pub(super) fn reconstruct(
    result: &DuelResult,
    pack: &FirstTurnKnowledge,
    facts: &Facts,
    activations: &[ActivationWitness],
    movements: &[MovementWitness],
    epochs: &BTreeMap<String, u64>,
) -> ActualRestrictions {
    let mut state = ActualRestrictions {
        special_allowed: Some(true),
        dark_only: Some(false),
        extra_xyz_only: Some(false),
        leave_field_banish: facts
            .cards
            .iter()
            .map(|c| (c.instance.clone(), Some(false)))
            .collect(),
        rank_as_level: facts
            .cards
            .iter()
            .map(|c| (c.instance.clone(), Some(false)))
            .collect(),
        unknown_rules: vec![],
    };
    for activation in activations {
        let Some(rule) = activation.rule_id.as_deref().and_then(|id| pack.rule(id)) else {
            state
                .unknown_rules
                .push(format!("activation:{}", activation.event));
            continue;
        };
        match rule.operation {
            // These frozen operations do not install an ongoing summon lock.
            Operation::DeckSet
            | Operation::TrapMonster
            | Operation::DeckSpecial
            | Operation::SearchMonster
            | Operation::RevealSpecial
            | Operation::DiscardMill
            | Operation::DeckMillSet
            | Operation::SearchSpellTrap
            | Operation::Mill
            | Operation::AshNegate => {}
            Operation::DestroyedXyzRevive => {
                // Frozen Lua registers this after processing, even if all of
                // the selected monsters have ceased to be valid by resolution.
                if activation.resolved {
                    state.dark_only = Some(true);
                }
            }
            Operation::ForceRankUp => {
                if activation.resolved {
                    state.extra_xyz_only = Some(true);
                }
            }
            Operation::ReviveOnBanish | Operation::DetachSelfSpecial => {
                if !activation.resolved {
                    continue;
                }
                let (Some(begin), Some(end)) =
                    (activation.solving_event, activation.resolution_event)
                else {
                    state.unknown_rules.push(rule.id.clone());
                    continue;
                };
                let source = &activation.source;
                let summoned = facts.history.iter().find(|h| {
                    h.kind == "special_summon"
                        && h.card.instance == source.instance
                        && h.event > begin
                        && h.event < end
                        && h.card.identity_known
                });
                let Some(summoned) = summoned else {
                    continue;
                };
                let move_in = movements.iter().rev().find(|m| {
                    m.instance == source.instance
                        && m.to.location == 4
                        && m.event < summoned.event
                        && m.event > begin
                });
                let Some(move_in) = move_in else {
                    state.unknown_rules.push(rule.id.clone());
                    continue;
                };
                let left = movements.iter().any(|m| {
                    m.instance == source.instance
                        && m.event > move_in.event
                        && m.from.location == 4
                        && m.to.location != 4
                });
                let reset_by_set = result
                    .events
                    .iter()
                    .filter(|e| {
                        e.opcode == 53
                            && e.sequence > summoned.event
                            && e.fields["position"].as_u64().is_some_and(|p| p & 10 != 0)
                    })
                    .any(|e| {
                        movements
                            .iter()
                            .rev()
                            .find(|m| m.instance == source.instance && m.event < e.sequence)
                            .is_some_and(|at| {
                                e.fields["player"] == at.to.player
                                    && e.fields["location"] == at.to.location
                                    && e.fields["sequence"].as_u64()
                                        == at.to.sequence.map(u64::from)
                            })
                    });
                if !left
                    && !reset_by_set
                    && epochs.get(&source.instance) == Some(&move_in.epoch_after)
                {
                    state
                        .leave_field_banish
                        .insert(source.instance.clone(), Some(true));
                }
            }
            _ => state.unknown_rules.push(rule.id.clone()),
        }
    }
    for card in facts
        .cards
        .iter()
        .filter(|c| c.location == 4 && c.position & 5 != 0)
    {
        for rule in pack
            .rules
            .iter()
            .filter(|r| r.card_id == card.code && r.operation == Operation::OphionLock)
        {
            if !card.materials.is_empty() || card.materials_complete == Some(false) {
                state.unknown_rules.push(rule.id.clone());
            }
        }
    }
    state.unknown_rules.sort();
    state.unknown_rules.dedup();
    if !facts.history_complete || !state.unknown_rules.is_empty() {
        state.special_allowed = None;
        if state.dark_only != Some(true) {
            state.dark_only = None;
        }
        if state.extra_xyz_only != Some(true) {
            state.extra_xyz_only = None;
        }
    }
    state
}

#[cfg(test)]
mod tests {
    use super::*;
    fn resolved(id: &str) -> ActivationWitness {
        ActivationWitness {
            event: 1,
            chain: 1,
            rule_id: Some(id.into()),
            source: FactCard {
                instance: "actor".into(),
                identity_known: true,
                ..Default::default()
            },
            after_cost: None,
            resolved: true,
            negated: false,
            activation_negated: false,
            solving_event: Some(2),
            resolution_event: Some(3),
        }
    }
    #[test]
    fn break_dark_lock_does_not_depend_on_a_successful_revive_and_negation_does_not_install_it() {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let result =
            DuelResult::failure(ygo_engine_adapter::WorkerError::new("unit", "unit", "unit"));
        let facts = Facts {
            history_complete: true,
            ..Default::default()
        };
        let mut activation = resolved("62709239:destroyed_xyz_two_revive_dark_lock");
        let locks = reconstruct(
            &result,
            &pack,
            &facts,
            &[activation.clone()],
            &[],
            &BTreeMap::new(),
        );
        assert_eq!(locks.dark_only, Some(true));
        activation.resolved = false;
        activation.negated = true;
        let locks = reconstruct(&result, &pack, &facts, &[activation], &[], &BTreeMap::new());
        assert_eq!(locks.dark_only, Some(false));
    }
    #[test]
    fn an_unhandled_ongoing_operation_never_becomes_an_assumed_absence_of_restrictions() {
        let pack = FirstTurnKnowledge::builtin().unwrap();
        let result =
            DuelResult::failure(ygo_engine_adapter::WorkerError::new("unit", "unit", "unit"));
        let facts = Facts {
            history_complete: true,
            ..Default::default()
        };
        let rule = pack
            .rules
            .iter()
            .find(|r| r.operation == Operation::MulcharmyObserver)
            .unwrap();
        let locks = reconstruct(
            &result,
            &pack,
            &facts,
            &[resolved(&rule.id)],
            &[],
            &BTreeMap::new(),
        );
        assert_eq!(locks.special_allowed, None);
        assert_eq!(locks.dark_only, None);
        assert_eq!(locks.unknown_rules, vec![rule.id.clone()]);
    }
}
