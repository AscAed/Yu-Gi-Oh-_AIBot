use ygo_domain::*;
use ygo_knowledge::CORE;
use ygo_planner::v2::*;
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

#[test]
fn break_sword_requires_an_opponent_and_tracks_detach_destroy_and_revival() {
    let cat = catalog();
    let pack = ygo_knowledge::KnowledgePack::read(std::path::Path::new(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../knowledge/phantom-v2.json"
    )))
    .unwrap();
    let hand = vec![
        CardId(25538345),
        CardId(36426778),
        CardId(88544390),
        CardId(2964201),
        CardId(2971090),
    ];
    let deck = Deck::new(
        hand.clone(),
        vec![CardId(62709239), CardId(26692769)],
        vec![],
    );
    let mut state = initial_state(&deck, &hand, &cat).unwrap();
    for c in state
        .cards
        .iter_mut()
        .filter(|c| matches!(c.code, 25538345 | 36426778 | 88544390))
    {
        c.location = 4;
    }
    let xyz = successors(&state, &cat, &pack)
        .into_iter()
        .find(|s| s.kind == StepKind::XyzSummon)
        .unwrap();
    assert_eq!(
        xyz.after.cards.iter().filter(|c| c.location == 128).count(),
        2
    );
    assert!(!successors(&xyz.after, &cat, &pack)
        .iter()
        .any(|s| s.effect_id == "62709239:destroy"));
    let mut enemy = state
        .cards
        .iter()
        .find(|c| c.code == 2964201)
        .unwrap()
        .clone();
    enemy.instance = "enemy".into();
    enemy.player = 1;
    enemy.location = 4;
    let mut field = xyz.after.clone();
    field.used.insert("88544390:summon".into());
    field.cards.push(enemy);
    let destroy = successors(&field, &cat, &pack)
        .into_iter()
        .find(|s| s.effect_id == "62709239:destroy" && s.targets[0].code == 62709239)
        .unwrap();
    assert_eq!(destroy.costs.len(), 1);
    assert_eq!(
        destroy
            .after
            .cards
            .iter()
            .filter(|c| c.location == 128)
            .count(),
        0
    );
    assert!(destroy.after.destroyed_xyz.contains(&xyz.source.instance));
    let revive = successors(&destroy.after, &cat, &pack)
        .into_iter()
        .find(|s| s.effect_id == "62709239:revive")
        .unwrap();
    assert!(revive.after.dark_only);
    assert_eq!(revive.targets.len(), 2);
    assert!(revive.targets.iter().all(|c| revive
        .after
        .cards
        .iter()
        .any(|r| r.instance == c.instance && r.location == 4 && r.level == 4)));
    let mut invalid = destroy.after.clone();
    invalid.destroyed_xyz.clear();
    assert!(!successors(&invalid, &cat, &pack)
        .iter()
        .any(|s| s.effect_id == "62709239:revive"));
}
