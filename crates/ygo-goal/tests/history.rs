use ygo_engine_adapter::*;
#[test]
fn effect_resolution_uses_pinned_lua_description_ids_and_needs_chain_solved() {
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut r = DuelResult::failure(WorkerError::new("test", "test", "test"));
    r.events.push(CoreEventFrame{sequence:1,opcode:70,raw:vec![],supported:true,fields:serde_json::json!({"code":90432163,"description":((90432163u64)<<20)+1,"chain":1,"location":{"player":0,"location":16,"sequence":0}})});
    let before = ygo_goal::actual_facts(&r, &Default::default(), &pack);
    assert!(before.history.is_empty());
    r.events.push(CoreEventFrame {
        sequence: 2,
        opcode: 73,
        raw: vec![],
        supported: true,
        fields: serde_json::json!({"chain":1}),
    });
    let after = ygo_goal::actual_facts(&r, &Default::default(), &pack);
    assert_eq!(
        after.history[0].effect_id.as_deref(),
        Some("90432163:search")
    );
}
#[test]
fn destruction_records_the_origin_zone_and_keeps_cost_distinct_from_effect() {
    let pack = ygo_knowledge::KnowledgePack::builtin().unwrap();
    let mut r = DuelResult::failure(WorkerError::new("test", "test", "test"));
    r.events.push(CoreEventFrame{sequence:1,opcode:50,raw:vec![],supported:true,fields:serde_json::json!({"code":62709239,"from":{"player":0,"location":4,"sequence":0,"position":1},"to":{"player":0,"location":16,"sequence":0,"position":5},"reason":65})});
    let facts = ygo_goal::actual_facts(&r, &Default::default(), &pack);
    let destroyed = facts
        .history
        .iter()
        .find(|h| h.kind == "destroyed")
        .unwrap();
    assert_eq!(destroyed.card.location, 4);
    assert_eq!(destroyed.reason & 128, 0);
    assert_eq!(
        facts
            .history
            .iter()
            .find(|h| h.kind == "sent_to_grave")
            .unwrap()
            .card
            .location,
        16
    );
}
