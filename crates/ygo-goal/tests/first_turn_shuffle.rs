//! Directed native identity experiment; not a tournament reachability baseline.
use ygo_engine_adapter::*;
use ygo_goal::*;
use ygo_knowledge::first_turn::FirstTurnKnowledge;

#[test]
#[ignore = "opt-in: duplicate hand reveal through frozen native engine; charged rule experiment"]
fn revealed_same_name_cost_does_not_swap_the_self_summoning_instance() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let portable: serde_json::Value = serde_json::from_str(include_str!(
        "../../../tests/fixtures/tournament-2026.rules-resource.contract.json"
    ))
    .unwrap();
    let mut q: RunDuelRequest =
        serde_json::from_value(portable["cases"][0]["runtime_request"].clone()).unwrap();
    q.engine = ProcessEngineConfig::from_toml(
        &std::fs::read_to_string(root.join("data/runtime/tournament-2026/engine-development.toml"))
            .unwrap(),
    )
    .unwrap();
    q.opening_hand = [46072770, 46072770, 25538345, 36426778, 83566725]
        .into_iter()
        .map(ygo_domain::CardId)
        .collect();
    q.decisions.clear();
    let path = root
        .join("data/runtime/tournament-2026/trace-audits")
        .join(format!(
            "reveal-{}-{}.jsonl",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
    let journal = CallJournal::open(
        &path,
        "duplicate-reveal-identity",
        &digest(&serde_json::to_vec(&q).unwrap()),
        512,
    )
    .unwrap();
    let adapter = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::RuleVerification,
    );
    let mut result = adapter.run(&q).unwrap();
    let metadata = prompt_metadata(
        result.prompt.as_ref().unwrap().id,
        &result.events.last().unwrap().raw,
    )
    .unwrap();
    let actor = metadata
        .iter()
        .filter(|m| {
            m.effect_description == Some(46072770u64 << 20)
                && matches!(m.choice, Choice::Command { command: 5, .. })
                && m.source
                    .as_ref()
                    .is_some_and(|s| s.code == 46072770 && s.location == 2)
        })
        .min_by_key(|m| m.source.as_ref().unwrap().sequence)
        .unwrap()
        .clone();
    let actor = actor.source.map(|s| (s, actor.choice)).unwrap();
    let original = format!("observed:0:2:{}:0", actor.0.sequence);
    let mut witnesses = vec![QueryWitness::capture(&result).unwrap()];
    q.decisions = result.resolved_decisions.clone();
    q.decisions.push(Decision {
        prompt_id: result.prompt.as_ref().unwrap().id,
        player: 0,
        choice: actor.1,
    });
    let mut revealed = false;
    let mut finished = false;
    for _ in 0..12 {
        let previous = result.events.clone();
        result = adapter.run(&q).unwrap();
        assert!(result.error.is_none(), "{:?}", result.error);
        assert_eq!(&result.events[..previous.len()], previous.as_slice());
        witnesses.push(QueryWitness::capture(&result).unwrap());
        let prompt = result.prompt.as_ref().unwrap();
        let ms = prompt_metadata(prompt.id, &result.events.last().unwrap().raw).unwrap();
        if prompt.opcode == 12
            && ms.iter().any(|m| {
                m.source
                    .as_ref()
                    .is_some_and(|s| s.code == 46072770 && s.location == 4)
            })
        {
            finished = true;
            break;
        }
        let choice=match prompt.opcode {
            15 if !revealed=>{revealed=true;ms.iter().find(|m|m.selected.len()==1&&m.selected[0].code==46072770&&m.selected[0].location==2&&m.selected[0].sequence!=actor.0.sequence).unwrap().choice.clone()},
            18=>prompt.actions.iter().find(|a|matches!(&a.choice,Choice::Place{zones} if zones.len()==1&&zones[0].player==0&&zones[0].location==4)).unwrap().choice.clone(),
            19=>Choice::Position{position:1},
            16=>Choice::Chain{index:None},
            _=>panic!("unexpected manual preparation prompt {prompt:?}"),
        };
        q.decisions = result.resolved_decisions.clone();
        q.decisions.push(Decision {
            prompt_id: prompt.id,
            player: 0,
            choice,
        });
    }
    assert!(finished && revealed);
    q.decisions = result.resolved_decisions.clone();
    let replay = adapter.run(&q).unwrap();
    assert_eq!(result.events, replay.events);
    assert_eq!(result.checkpoint, replay.checkpoint);
    assert_eq!(result.resolved_decisions, replay.resolved_decisions);
    let record = path.with_extension("record.json");
    std::fs::write(&record,serde_json::to_vec_pretty(&serde_json::json!({"scope":"native duplicate reveal identity; not autonomous or tournament baseline","request":q,"result":result,"witnesses":witnesses,"actor":original,"charged":journal.stats().unwrap().consumed})).unwrap()).unwrap();
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let trace = actual_trace_v6(&result, &Default::default(), &pack, &witnesses).unwrap();
    let current = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 46072770 && c.location == 4 && c.player == 0)
        .unwrap();
    assert!(current.identity_known);
    assert_eq!(current.instance, original);
    let other = trace
        .facts
        .cards
        .iter()
        .find(|c| c.code == 46072770 && c.location == 2 && c.player == 0)
        .unwrap();
    assert!(other.identity_known);
    assert_ne!(other.instance, current.instance);
    assert!(trace
        .facts
        .history
        .iter()
        .any(|h| h.kind == "special_summon"
            && h.card.instance == original
            && h.card.identity_known));
    let audited = verify_query_replays(&q, &result, &witnesses, journal.clone()).unwrap();
    assert!(audited.matches(&result, &witnesses));
    assert_eq!(journal.stats().unwrap().consumed, 12);
    std::fs::write(path.with_extension("audit.json"),serde_json::to_vec_pretty(&serde_json::json!({"actor":original,"query_calls":audited.call_ids,"charged":journal.stats().unwrap().consumed})).unwrap()).unwrap();
}
