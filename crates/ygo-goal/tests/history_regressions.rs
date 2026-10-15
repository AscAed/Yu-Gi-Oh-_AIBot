use ygo_engine_adapter::*;
use ygo_goal::*;

fn event(r: &mut DuelResult, opcode: u8, fields: serde_json::Value) {
    r.events.push(CoreEventFrame {
        sequence: r.events.len() as u64 + 1,
        opcode,
        raw: vec![],
        supported: true,
        fields,
    });
}
fn result() -> DuelResult {
    let mut r = DuelResult::failure(WorkerError::new("test", "test", "test"));
    r.error = None;
    r.status = DuelStatus::DecisionRequired;
    r
}
fn moved(r: &mut DuelResult, code: u32, from: (u8, u32, u32), to: (u8, u32, u32), reason: u32) {
    event(
        r,
        50,
        serde_json::json!({"code":code,
        "from":{"player":0,"location":from.0,"sequence":from.1,"position":from.2},
        "to":{"player":0,"location":to.0,"sequence":to.1,"position":to.2},"reason":reason}),
    );
}
fn summon(r: &mut DuelResult, code: u32, sequence: u32) {
    event(
        r,
        62,
        serde_json::json!({"code":code,"location":{"player":0,"location":4,"sequence":sequence,"position":1}}),
    );
}
fn facts(r: &DuelResult) -> Facts {
    actual_facts(
        r,
        &Default::default(),
        &ygo_knowledge::KnowledgePack::builtin().unwrap(),
    )
}
#[test]
fn simultaneous_summons_commit_every_distinct_instance_only_on_success() {
    for codes in [[36426778, 88544390], [36426778, 36426778]] {
        let mut r = result();
        for (i, code) in codes.into_iter().enumerate() {
            moved(&mut r, code, (16, 0, 5), (4, i as u32, 1), 0);
            summon(&mut r, code, i as u32);
        }
        assert!(facts(&r).history.iter().all(|h| h.kind != "special_summon"));
        assert!(
            !facts(&r).history_complete,
            "unfinished summon cannot prove a negative history"
        );
        event(&mut r, 63, serde_json::json!({}));
        let f = facts(&r);
        let h: Vec<_> = f
            .history
            .iter()
            .filter(|h| h.kind == "special_summon")
            .collect();
        assert_eq!(h.len(), 2);
        assert_ne!(h[0].card.instance, h[1].card.instance);
        assert_eq!(
            h.iter().map(|h| h.card.sequence).collect::<Vec<_>>(),
            vec![0, 1]
        );
        assert!(f.history_complete);
    }
}
#[test]
fn missing_summon_identity_does_not_invent_a_successful_instance() {
    let mut missing_begin = result();
    event(&mut missing_begin, 63, serde_json::json!({}));
    assert!(!facts(&missing_begin).history_complete);
    let mut r = result();
    summon(&mut r, 36426778, 0);
    event(&mut r, 63, serde_json::json!({}));
    assert!(facts(&r).history.is_empty());
    assert!(!facts(&r).history_complete);
    let mut failed = result();
    moved(&mut failed, 36426778, (16, 0, 5), (4, 0, 1), 0);
    summon(&mut failed, 36426778, 0);
    moved(&mut failed, 36426778, (4, 0, 1), (16, 0, 5), 0);
    event(&mut failed, 63, serde_json::json!({}));
    assert!(facts(&failed)
        .history
        .iter()
        .all(|h| h.kind != "special_summon"));
}
#[test]
fn historical_materials_use_origin_destination_and_activation_time() {
    for mats in [[36426778, 25538345], [36426778, 36426778]] {
        let mut r = result();
        moved(&mut r, 62709239, (64, 0, 5), (4, 0, 1), 0);
        for (i, code) in mats.into_iter().enumerate() {
            moved(&mut r, code, (4, i as u32 + 1, 1), (132, 0, i as u32), 0);
        }
        summon(&mut r, 62709239, 0);
        event(&mut r, 63, serde_json::json!({}));
        event(
            &mut r,
            70,
            serde_json::json!({"code":62709239,"description":62709239u64<<20,"chain":1,"location":{"player":0,"location":4,"sequence":0}}),
        );
        moved(&mut r, mats[0], (132, 0, 0), (16, 0, 5), 128);
        event(&mut r, 71, serde_json::json!({"chain":1}));
        moved(&mut r, 62709239, (4, 0, 1), (16, 1, 5), 65);
        moved(&mut r, mats[1], (144, 1, 0), (16, 2, 5), 1536);
        event(&mut r, 73, serde_json::json!({"chain":1}));
        event(
            &mut r,
            70,
            serde_json::json!({"code":62709239,"description":(62709239u64<<20)+1,"chain":1,"location":{"player":0,"location":16,"sequence":1}}),
        );
        event(&mut r, 73, serde_json::json!({"chain":1}));
        moved(&mut r, 62709239, (16, 1, 5), (4, 0, 1), 0);
        summon(&mut r, 62709239, 0);
        event(&mut r, 63, serde_json::json!({}));
        let f = facts(&r);
        let get = |kind: &str| {
            f.history
                .iter()
                .find(|h| h.kind == kind && h.card.code == 62709239)
                .unwrap()
        };
        assert_eq!(get("special_summon").card.materials, mats);
        let returned = f
            .history
            .iter()
            .rev()
            .find(|h| h.kind == "special_summon")
            .unwrap();
        assert!(returned.card.materials.is_empty());
        assert_eq!(returned.card.proper_xyz, Some(false));
        assert_eq!(get("destroyed").card.materials, vec![mats[1]]);
        assert!(get("sent_to_grave").card.materials.is_empty());
        let effects: Vec<_> = f
            .history
            .iter()
            .filter(|h| h.kind == "effect_resolved")
            .collect();
        assert_eq!(
            effects[0].card.materials,
            vec![mats[1]],
            "activation snapshot follows material cost, not later destruction"
        );
        assert!(
            effects[1].card.materials.is_empty(),
            "grave activation has no materials"
        );
    }
}
#[test]
fn missing_chained_frame_cannot_prove_post_cost_material_conditions() {
    let mut r = result();
    moved(&mut r, 62709239, (64, 0, 5), (4, 0, 1), 0);
    moved(&mut r, 36426778, (4, 1, 1), (132, 0, 0), 0);
    event(
        &mut r,
        70,
        serde_json::json!({"code":62709239,"description":62709239u64<<20,"chain":1,"location":{"player":0,"location":4,"sequence":0}}),
    );
    assert!(!facts(&r).history_complete);
    event(&mut r, 73, serde_json::json!({"chain":1}));
    let f = facts(&r);
    assert!(!f.history_complete);
    let expr = Expr::History {
        kind: "effect_resolved".into(),
        filter: Filter {
            codes: vec![62709239],
            materials_min: Some(1),
            ..Default::default()
        },
        effect_id: None,
        reason_mask: None,
        min: 1,
        max: None,
    };
    assert_eq!(
        evaluate(&expr, &f, &Default::default()).result,
        Truth::Unknown
    );
}
