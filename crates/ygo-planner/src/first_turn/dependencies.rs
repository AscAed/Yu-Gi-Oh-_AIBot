//! Resource operators for the partial pilot; no human route is imported here.
use super::*;
pub(super) fn apply(
    out: &mut Successors,
    s: &CausalState,
    source: &KnownInstance,
    rule: &FirstTurnRule,
    cat: &Catalog,
    pack: &FirstTurnKnowledge,
) {
    match rule.operation {
        Operation::NormalSummonSet => {
            if s.normal_remaining != Some(1) || source.card.location != 2 || free_main(s).is_none()
            {
                return;
            }
            if source.card.type_flags & 1 == 0 || source.card.type_flags & 0x2000000 != 0 {
                return;
            }
            let Some(level) = source.card.level else {
                out.unknowns
                    .push(format!("{}: normal level unknown", rule.id));
                return;
            };
            if level > 4 {
                out.coverage_gaps
                    .push(format!("{}: tribute summon", rule.id));
                return;
            }
            for (position, kind) in [
                (1, TransitionKind::NormalSummon),
                (8, TransitionKind::SetMonster),
            ] {
                let mut after = s.clone();
                after.normal_remaining = Some(0);
                if move_known(&mut after, &source.id, 4, position).is_err() {
                    continue;
                }
                if position == 1 {
                    queue_summon(&mut after, &source.id, pack, cat);
                }
                out.transitions.push(Transition {
                    kind,
                    rule_id: rule.id.clone(),
                    source: source.id.clone(),
                    selections: vec![],
                    requirements: rule.conditions.clone(),
                    after_cost: s.clone(),
                    after_resolution: after,
                });
            }
        }
        Operation::RevealSpecial | Operation::PhantomFieldSpecial => {
            if free_main(s).is_none() {
                return;
            }
            match summon_allowed(
                s,
                source.card.attribute,
                source.card.location,
                source.card.type_flags,
            ) {
                Truth::No => return,
                Truth::Unknown => {
                    out.unknowns
                        .push(format!("{}: summon restrictions unknown", rule.id));
                    return;
                }
                Truth::Yes => {}
            }
            let mut costs = vec![None];
            if rule.operation == Operation::RevealSpecial {
                let Some(selection) = rule.selections.iter().find(|p| p.role == "reveal") else {
                    return;
                };
                costs.clear();
                for c in s.cards.iter().filter(|c| c.id != source.id) {
                    match (match_selection(c, selection, cat), c.card.is_public) {
                        (Truth::Yes, Some(false)) => costs.push(Some(pick("reveal", "cost", c))),
                        (Truth::Unknown, _) | (Truth::Yes, None) => out.unknowns.push(format!(
                            "{}: reveal identity/public status unknown",
                            rule.id
                        )),
                        _ => {}
                    }
                }
            } else if !s.cards.iter().any(|c| {
                own(c, 4)
                    && faceup(c)
                    && c.identity_known
                    && c.card.type_flags & 1 != 0
                    && cat.get(&CardId(c.card.code)).is_some_and(|b| {
                        b.setcodes
                            .iter()
                            .any(|v| v & 0xfff == 0xdb && v & 0x1000 != 0)
                    })
            }) {
                return;
            }
            for cost in costs {
                let mut after_cost = s.clone();
                consume(&mut after_cost, rule, source);
                let mut after = after_cost.clone();
                if move_known(&mut after, &source.id, 4, 1).is_err() {
                    continue;
                }
                queue_summon(&mut after, &source.id, pack, cat);
                emit(
                    out,
                    rule,
                    source,
                    cost.into_iter().collect(),
                    after_cost,
                    after,
                );
            }
        }
        Operation::DeckMillSet => {
            if free_st(s).is_none() {
                return;
            }
            let (Some(mill), Some(set)) = (
                rule.selections.iter().find(|v| v.role == "deck_result"),
                rule.selections.iter().find(|v| v.role == "deck_set"),
            ) else {
                return;
            };
            for code in deck_options(s, mill, cat) {
                let mut cost = s.clone();
                consume(&mut cost, rule, source);
                let mut sent = cost.clone();
                if deck_card(&mut sent, code, 16, cat).is_err() {
                    continue;
                }
                for set_code in deck_options(&sent, set, cat) {
                    let mut after = sent.clone();
                    if deck_card(&mut after, set_code, 8, cat).is_err() {
                        continue;
                    }
                    let mut selected = vec![from_deck(code), from_deck(set_code)];
                    selected[1].role = "deck_set".into();
                    emit(out, rule, source, selected, cost.clone(), after);
                }
            }
        }
        Operation::LinkProcedure => {
            let Some(selection) = rule.selections.iter().find(|v| v.role == "material") else {
                return;
            };
            let Some(rating) = source.card.link else {
                out.unknowns
                    .push(format!("{}: actual link rating unknown", rule.id));
                return;
            };
            let candidates = s
                .cards
                .iter()
                .filter(|c| {
                    match_selection(c, selection, cat) == Truth::Yes
                        && !pack.rules.iter().any(|r| {
                            r.card_id == c.card.code
                                && r.operation == Operation::LinkMaterialProhibition
                        })
                })
                .collect::<Vec<_>>();
            match summon_allowed(s, source.card.attribute, 64, source.card.type_flags) {
                Truth::No => return,
                Truth::Unknown => {
                    out.unknowns
                        .push(format!("{}: extra restrictions unknown", rule.id));
                    return;
                }
                _ => {}
            }
            for count in selection.min..=selection.max {
                let mut combos = vec![];
                combinations(&candidates, count, 0, &mut vec![], &mut combos);
                for combo in combos {
                    if !link_sum(&combo, rating, 0, 0) {
                        continue;
                    }
                    if combo.iter().any(|c| c.leave_field_banish.is_none()) {
                        out.unknowns
                            .push(format!("{}: material departure unknown", rule.id));
                        continue;
                    }
                    let mut after = s.clone();
                    for c in &combo {
                        let children = after
                            .cards
                            .iter()
                            .filter(|x| x.host.as_deref() == Some(&c.id))
                            .map(|x| x.id.clone())
                            .collect::<Vec<_>>();
                        for id in children {
                            move_known(&mut after, &id, 16, 5).unwrap();
                        }
                        move_known(&mut after, &c.id, 16, 5).unwrap();
                    }
                    // The pilot supports an available EMZ. Retaining an EMZ
                    // occupant needs linked-zone geometry, tracked as a gap.
                    if after
                        .cards
                        .iter()
                        .any(|c| own(c, 4) && c.card.sequence >= 5)
                    {
                        out.coverage_gaps
                            .push(format!("{}: retained EMZ geometry", rule.id));
                        continue;
                    }
                    let c = after.cards.iter_mut().find(|c| c.id == source.id).unwrap();
                    c.card.location = 4;
                    c.card.sequence = 5;
                    c.card.position = 1;
                    c.card.is_public = Some(true);
                    emit(
                        out,
                        rule,
                        source,
                        combo
                            .iter()
                            .map(|c| pick("material", "procedure", c))
                            .collect(),
                        s.clone(),
                        after,
                    );
                }
            }
        }
        _ => {}
    }
}
fn link_sum(cards: &[&KnownInstance], rating: u32, index: usize, sum: u32) -> bool {
    if index == cards.len() {
        return sum == rating;
    }
    if sum >= rating {
        return false;
    }
    link_sum(cards, rating, index + 1, sum + 1)
        || (cards[index].card.type_flags & 0x4000000 != 0
            && cards[index]
                .card
                .link
                .is_some_and(|n| n > 1 && link_sum(cards, rating, index + 1, sum + n)))
}
fn combinations<'a>(
    cards: &[&'a KnownInstance],
    left: usize,
    start: usize,
    selected: &mut Vec<&'a KnownInstance>,
    out: &mut Vec<Vec<&'a KnownInstance>>,
) {
    if left == 0 {
        out.push(selected.clone());
        return;
    }
    for i in start..cards.len() {
        selected.push(cards[i]);
        combinations(cards, left - 1, i + 1, selected, out);
        selected.pop();
    }
}
