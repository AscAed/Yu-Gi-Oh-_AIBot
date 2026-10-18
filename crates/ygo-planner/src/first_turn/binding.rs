//! Instance/effect-aware binding. This module never selects a semantic action.
use super::*;
use ygo_engine_adapter::{prompt_metadata, ActionMetadata, Choice, DuelResult};
fn source_matches(s: &ygo_engine_adapter::CardReference, c: &StateCard) -> bool {
    s.code == c.code && s.player == c.player && s.location == c.location && s.sequence == c.sequence
}
pub fn bind_start(
    result: &DuelResult,
    source: &StateCard,
    rule: &FirstTurnRule,
    kind: TransitionKind,
    trigger_proved: bool,
) -> Result<Choice, String> {
    let p = result
        .prompt
        .as_ref()
        .ok_or("missing actual start prompt")?;
    let raw = &result.events.last().ok_or("missing raw start prompt")?.raw;
    if p.player != 0 {
        return Err("semantic start is not our decision".into());
    }
    let candidates = prompt_metadata(p.id, raw)?
        .into_iter()
        .filter(|m| m.source.as_ref().is_some_and(|s| source_matches(s, source)))
        .filter(|m| match kind {
            TransitionKind::Procedure => matches!(m.choice, Choice::Command { command: 1, .. }),
            TransitionKind::NormalSummon => matches!(m.choice, Choice::Command { command: 0, .. }),
            TransitionKind::SetMonster => matches!(m.choice, Choice::Command { command: 3, .. }),
            TransitionKind::Activate => {
                matches!(m.choice, Choice::Command { command: 5, .. })
                    && m.effect_description == rule.description
            }
            TransitionKind::Trigger => {
                trigger_proved
                    && matches!(m.choice, Choice::YesNo { yes: true })
                    && (m.effect_description == rule.description
                        || m.effect_description == Some(221))
            }
            TransitionKind::DeclineTrigger => {
                trigger_proved
                    && matches!(m.choice, Choice::YesNo { yes: false })
                    && (m.effect_description == rule.description
                        || m.effect_description == Some(221))
            }
        })
        .collect::<Vec<_>>();
    if candidates.len() != 1 {
        return Err(format!(
            "{}: start binding matched {} actions",
            rule.id,
            candidates.len()
        ));
    }
    Ok(candidates[0].choice.clone())
}
/// Deck selections bind an exposed candidate; observed instances additionally
/// bind full coordinates, including the overlay index in position.
pub fn bind_pick(
    metadata: &[ActionMetadata],
    selection: &SemanticSelection,
    instance: Option<&StateCard>,
) -> Result<Choice, String> {
    let candidates = metadata
        .iter()
        .filter(|m| {
            matches!(m.choice, Choice::Cards { .. } | Choice::Toggle { .. })
                && m.selection_group != Some(1)
                && m.selected.len() == 1
        })
        .filter(|m| {
            let c = &m.selected[0];
            c.player == 0
                && c.code == selection.card_id
                && c.location == selection.from
                && instance.map_or(selection.instance.is_none(), |actual| {
                    source_matches(c, actual)
                        && (actual.location & 128 == 0 || c.position == actual.position)
                })
        })
        .collect::<Vec<_>>();
    if candidates.is_empty() {
        return Err(format!(
            "{}:{}: no legal instance selection",
            selection.stage, selection.role
        ));
    }
    if instance.is_some() && candidates.len() != 1 {
        return Err("instance selection is ambiguous".into());
    }
    Ok(candidates[0].choice.clone())
}
