use ygo_domain::*;
use ygo_knowledge::*;
use ygo_planner::*;
fn catalog() -> Catalog {
    let mut out = Catalog::new();
    for id in CORE {
        let monster = !matches!(id, 25542642 | 98827725 | 32807846 | 81439173);
        let extra = matches!(id, 26692769 | 58699500 | 62709239);
        out.insert(
            CardId(id),
            Card {
                id: CardId(id),
                name: id.to_string(),
                type_flags: if extra {
                    if id == 62709239 {
                        0x800021
                    } else {
                        0x4000021
                    }
                } else if monster {
                    33
                } else if matches!(id, 25542642 | 98827725) {
                    4
                } else {
                    2
                },
                level: if id == 26692769 {
                    3
                } else if id == 58699500 {
                    2
                } else {
                    3
                },
                setcodes: if matches!(id, 32807846 | 81439173 | 58699500) {
                    vec![]
                } else {
                    vec![0x10db]
                },
                attribute: 32,
                race: 1,
                ..Default::default()
            },
        );
    }
    for id in [2964201, 2971090] {
        out.insert(
            CardId(id),
            Card {
                id: CardId(id),
                type_flags: 17,
                level: 4,
                attribute: 16,
                ..Default::default()
            },
        );
    }
    out
}
fn deck() -> Deck {
    Deck::new(
        vec![
            25538345, 36426778, 90432163, 63821877, 88544390, 25542642, 25542642, 98827725,
            32807846, 81439173, 2964201, 2964201, 2971090,
        ]
        .into_iter()
        .map(CardId)
        .collect(),
        vec![CardId(26692769), CardId(58699500), CardId(62709239)],
        vec![],
    )
}
#[test]
fn proposes_a_causal_goal_before_any_engine_call() {
    let pack = KnowledgePack::builtin().unwrap();
    let hand = [25538345, 36426778, 2964201, 2964201, 2971090].map(CardId);
    let p = propose(&deck(), &hand, &catalog(), &pack, 8, 32).unwrap();
    assert!(!p.plans.is_empty());
    assert!(p
        .plans
        .iter()
        .all(|p| p.goal_predicted && p.steps.len() <= 32));
    assert!(p
        .plans
        .iter()
        .any(|p| p.steps.iter().any(|s| s.effect_id == "25538345:revive")));
    for p in &p.plans {
        assert!(goal(&p.steps.last().unwrap().after));
        assert!(p.steps.iter().all(|s| !s.reason.is_empty()));
    }
    let again = propose(&deck(), &hand, &catalog(), &pack, 8, 32).unwrap();
    assert_eq!(
        p.plans.iter().map(|p| &p.id).collect::<Vec<_>>(),
        again.plans.iter().map(|p| &p.id).collect::<Vec<_>>()
    );
}

fn state() -> SymbolicState {
    initial_state(
        &deck(),
        &[25538345, 36426778, 2964201, 2964201, 2971090].map(CardId),
        &catalog(),
    )
    .unwrap()
}
#[test]
fn mill_requires_cost_and_excludes_the_same_card_name() {
    let pack = KnowledgePack::builtin().unwrap();
    let mut s = state();
    for c in &mut s.cards {
        if c.code == 25538345 {
            c.location = 4;
        } else if c.location == 2 {
            c.location = 1;
        }
    }
    assert!(!successors(&s, &catalog(), &pack)
        .iter()
        .any(|s| s.effect_id == "25538345:mill"));
    s.cards
        .iter_mut()
        .find(|c| c.code == 2964201)
        .unwrap()
        .location = 2;
    let choices = successors(&s, &catalog(), &pack);
    assert!(choices.iter().any(|s| s.effect_id == "25538345:mill"));
    assert!(choices
        .iter()
        .filter(|s| s.effect_id == "25538345:mill")
        .all(|s| s.targets[0].code != 25538345 && s.costs.len() == 1));
}
#[test]
fn grave_presence_is_not_a_trigger_but_banish_cost_creates_a_window() {
    let pack = KnowledgePack::builtin().unwrap();
    let mut s = state();
    for c in &mut s.cards {
        if matches!(c.code, 25538345 | 90432163) {
            c.location = 16;
        }
    }
    let choices = successors(&s, &catalog(), &pack);
    assert!(!choices.iter().any(|s| s.effect_id == "25538345:revive"));
    let search = choices
        .iter()
        .find(|s| s.effect_id == "90432163:search")
        .unwrap();
    let triggers = successors(&search.after, &catalog(), &pack);
    assert!(triggers.iter().any(|s| s.effect_id == "25538345:revive"));
    assert!(triggers.iter().all(|s| s.kind == StepKind::Trigger));
}
#[test]
fn once_per_name_applies_across_copies_and_shade_checks_grave_traps() {
    let pack = KnowledgePack::builtin().unwrap();
    let mut s = state();
    s.cards
        .iter_mut()
        .find(|c| c.code == 25538345)
        .unwrap()
        .location = 4;
    s.used.insert("36426778:summon".into());
    assert!(!successors(&s, &catalog(), &pack)
        .iter()
        .any(|s| s.effect_id == "36426778:summon"));
    s.cards
        .iter_mut()
        .find(|c| c.code == 98827725)
        .unwrap()
        .location = 8;
    assert!(successors(&s, &catalog(), &pack)
        .iter()
        .any(|s| s.effect_id == "98827725:summon"));
    s.cards
        .iter_mut()
        .find(|c| c.code == 25542642)
        .unwrap()
        .location = 16;
    assert!(!successors(&s, &catalog(), &pack)
        .iter()
        .any(|s| s.effect_id == "98827725:summon"));
}
#[test]
fn link_materials_are_consumed_and_redirected_monsters_leave_to_banish() {
    let pack = KnowledgePack::builtin().unwrap();
    let mut s = state();
    for c in &mut s.cards {
        if matches!(c.code, 25538345 | 36426778) {
            c.location = 4;
            c.redirect = true;
        }
    }
    let choices = successors(&s, &catalog(), &pack);
    let link = choices
        .iter()
        .find(|s| s.effect_id == "58699500:link")
        .unwrap();
    assert_eq!(link.costs.len(), 2);
    assert!(link.costs.iter().all(|m| link
        .after
        .cards
        .iter()
        .any(|c| c.instance == m.instance && c.location == 32)));
    let mut rust = s.clone();
    rust.cards
        .iter_mut()
        .find(|c| c.code == 26692769)
        .unwrap()
        .location = 4;
    assert!(successors(&rust, &catalog(), &pack)
        .iter()
        .filter(|s| s.kind == StepKind::LinkSummon)
        .all(|s| s.costs.iter().all(|c| c.code != 26692769)));
}

#[test]
fn reviving_scales_during_resolution_does_not_leave_a_grave_trigger() {
    let pack = KnowledgePack::builtin().unwrap();
    let mut s = state();
    for c in &mut s.cards {
        if matches!(c.code, 25538345 | 25542642) {
            c.location = 16;
        }
    }
    let choices = successors(&s, &catalog(), &pack);
    let revive = choices
        .iter()
        .find(|step| step.effect_id == "25542642:revive" && step.targets[0].code == 25538345)
        .unwrap();
    assert!(revive.after.pending.is_empty());
    assert!(revive
        .after
        .cards
        .iter()
        .any(|c| c.code == 25538345 && c.location == 4 && c.redirect));
}
#[test]
fn curated_primary_rules_produce_the_declared_resource_changes() {
    let pack = KnowledgePack::builtin().unwrap();
    let cat = catalog();
    let cases: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/phantom.semantic-cases.json"
    ))
    .unwrap();
    for case in cases.as_array().unwrap() {
        let cards: Vec<Resource> = case["before"]
            .as_array()
            .unwrap()
            .iter()
            .enumerate()
            .map(|(i, p)| {
                let code = p[0].as_u64().unwrap() as u32;
                Resource {
                    instance: i.to_string(),
                    code,
                    location: p[1].as_u64().unwrap() as u8,
                    level: cat[&CardId(code)].level,
                    redirect: false,
                }
            })
            .collect();
        let pending = case["pending"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| {
                (
                    p[0].as_u64().unwrap() as u32,
                    p[1].as_u64().unwrap().to_string(),
                )
            })
            .collect();
        let before = SymbolicState {
            cards,
            used: Default::default(),
            normal_left: 0,
            pending,
            dark_only: false,
        };
        let choices = successors(&before, &cat, &pack);
        let step = choices
            .iter()
            .find(|s| s.effect_id == case["effect_id"].as_str().unwrap())
            .unwrap_or_else(|| panic!("{}", case["case_id"]));
        for expected in case["expected"].as_array().unwrap() {
            assert!(
                step.after
                    .cards
                    .iter()
                    .any(|c| c.code as u64 == expected[0].as_u64().unwrap()
                        && c.location as u64 == expected[1].as_u64().unwrap()),
                "{}",
                case["case_id"]
            );
        }
    }
}
#[test]
fn chosen_mill_explanation_names_the_next_resource_consumer() {
    use ygo_engine_adapter::{ActionMetadata, CardReference, Choice};
    let pack = KnowledgePack::builtin().unwrap();
    let mut before = state();
    before
        .cards
        .iter_mut()
        .find(|c| c.code == 25538345)
        .unwrap()
        .location = 4;
    let steps = successors(&before, &catalog(), &pack);
    let mill = steps
        .iter()
        .find(|s| s.effect_id == "25538345:mill" && s.targets[0].code == 63821877)
        .unwrap()
        .clone();
    let next = successors(&mill.after, &catalog(), &pack);
    let consumer = next
        .iter()
        .find(|s| s.effect_id == "63821877:mill")
        .unwrap()
        .clone();
    let plan = Proposal {
        id: "test".into(),
        steps: vec![mill, consumer],
        goal_predicted: false,
    };
    let i = 0;
    let target = &plan.steps[i].targets[0];
    let choice = Choice::Cards { indices: vec![0] };
    let metadata = vec![ActionMetadata {
        choice: choice.clone(),
        source: None,
        effect_description: None,
        selected: vec![CardReference {
            code: target.code,
            player: 0,
            location: 1,
            sequence: 0,
            position: 8,
        }],
        selection_group: None,
    }];
    let reasons = assess_alternatives(&plan, i, &metadata, &choice, &pack);
    assert_eq!(reasons.len(), 1);
    assert!(reasons[0].selected);
    assert!(!reasons[0].consumer_effects.is_empty());
}
#[test]
fn a_dead_hand_cannot_invent_a_starter_or_grave_trigger() {
    let d = Deck::new(vec![CardId(2964201); 5], vec![], vec![]);
    let p = propose(
        &d,
        &d.main,
        &catalog(),
        &KnowledgePack::builtin().unwrap(),
        8,
        32,
    )
    .unwrap();
    assert!(p.plans.is_empty());
    assert_ne!(p.termination, "not_implemented");
}
