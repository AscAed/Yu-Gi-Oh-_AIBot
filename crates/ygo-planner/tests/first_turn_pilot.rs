//! Independent human recipes. Never imported by the planner implementation.
use std::sync::Arc;
use ygo_domain::CardId;
use ygo_engine_adapter::*;
use ygo_goal::{actual_trace_v6, verify_query_replays, QueryWitness, TraceWindow};
use ygo_knowledge::first_turn::FirstTurnKnowledge;

#[derive(Clone, Debug)]
enum Human {
    Command(u8, u32),
    Yes(u32),
    Card(u32),
    Material(u32),
    End,
}
fn shared_opening() -> Vec<Human> {
    use Human::*;
    vec![
        Command(1, 83566725),
        Yes(83566725),
        Card(85257384),
        Command(5, 85257384),
        Command(1, 78449284),
        Material(83566725),
        Material(85257384),
        Command(5, 78449284),
        Card(83566725),
    ]
}
fn human_route(ash: bool) -> Vec<Human> {
    use Human::*;
    let mut v = shared_opening();
    if ash {
        v.extend([Command(5, 46072770), Card(25538345)]);
    } else {
        v.push(Card(46072770));
    }
    v.extend([
        Yes(46072770),
        Card(36426778),
        Command(1, 36426778),
        Command(1, 26692769),
        Material(78449284),
        Material(46072770),
        Material(36426778),
        Command(5, 26692769),
        Card(63821877),
        Card(25542642),
        End,
    ]);
    v
}
fn manual_choice(r: &DuelResult, intent: &Human) -> Option<Choice> {
    let p = r.prompt.as_ref()?;
    let ms = prompt_metadata(p.id, &r.events.last()?.raw).ok()?;
    ms.iter()
        .find(|m| match intent {
            Human::Command(command, code) => {
                matches!(m.choice,Choice::Command{command:c,..}if c==*command)
                    && m.source.as_ref().is_some_and(|s| s.code == *code)
            }
            Human::Yes(code) => {
                matches!(m.choice, Choice::YesNo { yes: true })
                    && m.source.as_ref().is_some_and(|s| s.code == *code)
            }
            Human::Card(code) => {
                matches!(m.choice, Choice::Cards { .. })
                    && m.selected.len() == 1
                    && m.selected[0].code == *code
            }
            Human::Material(code) => {
                matches!(m.choice, Choice::Toggle { .. })
                    && m.selection_group == Some(0)
                    && m.selected.len() == 1
                    && m.selected[0].code == *code
            }
            Human::End => matches!(m.choice, Choice::Command { command: 7, .. }),
        })
        .map(|m| m.choice.clone())
}
fn neutral(r: &DuelResult) -> Option<Choice> {
    let p = r.prompt.as_ref()?;
    p.actions
        .iter()
        .find(|a| {
            matches!(
                &a.choice,
                Choice::Chain { index: None }
                    | Choice::Place { .. }
                    | Choice::Position { .. }
                    | Choice::Finish
            )
        })
        .map(|a| a.choice.clone())
}
fn request(root: &std::path::Path, pack: &FirstTurnKnowledge) -> RunDuelRequest {
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
    q.opening_hand = [46072770, 99745551, 83566725, 25538345, 44088353]
        .into_iter()
        .map(CardId)
        .collect();
    q.decisions.clear();
    q.first_turn.as_mut().unwrap().knowledge_id = pack.id();
    q.interruption.as_mut().unwrap().effect_id = "78449284:deck_special".into();
    q
}
fn manual(
    q: &mut RunDuelRequest,
    journal: Arc<CallJournal>,
    ash: bool,
    path: &std::path::Path,
) -> (DuelResult, Vec<QueryWitness>) {
    q.interruption.as_mut().unwrap().policy = if ash { "ash_effect_once" } else { "pass" }.into();
    let adapter = JournaledAdapter::new(
        ProcessEngineAdapter::new(q.engine.clone()),
        journal.clone(),
        CallPurpose::RuleVerification,
    );
    let route = human_route(ash);
    let mut i = 0;
    let mut result = adapter.run(q).unwrap();
    let mut witnesses = vec![QueryWitness::capture(&result).unwrap()];
    for _ in 0..180 {
        std::fs::write(path,serde_json::to_vec_pretty(&serde_json::json!({"scope":"independently authored human tournament pilot; not autonomous","intent":format!("{:?}",route.get(i)),"request":q,"result":result,"witnesses":witnesses,"consumed":journal.stats().unwrap().consumed})).unwrap()).unwrap();
        assert!(result.error.is_none(), "{:?}", result.error);
        if result.status == DuelStatus::EngineVerified {
            break;
        }
        let intent = route
            .get(i)
            .expect("human recipe exhausted before end phase completion");
        let choice = if let Some(choice) = manual_choice(&result, intent) {
            i += 1;
            choice
        } else {
            neutral(&result).unwrap_or_else(|| {
                panic!("manual intent {intent:?} not offered: {:?}", result.prompt)
            })
        };
        let prompt = result.prompt.as_ref().unwrap().clone();
        if prompt.opcode == 11 && witnesses.last().unwrap().event != prompt.id {
            witnesses.push(QueryWitness::capture(&result).unwrap());
        }
        q.decisions = result.resolved_decisions.clone();
        q.decisions.push(Decision {
            prompt_id: prompt.id,
            player: prompt.player,
            choice,
        });
        let old = result.events.clone();
        result = adapter.run(q).unwrap();
        assert_eq!(&result.events[..old.len()], old.as_slice());
        // The worker may automatically take a singleton prompt. Match that
        // actual recorded decision, rather than inventing an extra choice.
        for d in result
            .resolved_decisions
            .iter()
            .filter(|d| d.prompt_id > prompt.id)
        {
            if let Some(intent) = route.get(i) {
                let event = &result.events[d.prompt_id as usize - 1];
                let mut stopped = result.clone();
                stopped.prompt = parse_prompt(d.prompt_id, &event.raw).unwrap();
                stopped.events = vec![event.clone()];
                if manual_choice(&stopped, intent) == Some(d.choice.clone()) {
                    i += 1;
                }
            }
        }
    }
    assert_eq!(i, route.len());
    assert_eq!(result.status, DuelStatus::EngineVerified);
    assert!(result
        .events
        .iter()
        .any(|e| e.opcode == 41 && e.fields["phase"] == 512));
    assert!(result
        .checkpoint
        .cards
        .iter()
        .any(|c| c.player == 0 && c.location == 4 && c.code == 26692769));
    assert!(result
        .checkpoint
        .cards
        .iter()
        .any(|c| c.player == 0 && c.location == 8 && c.code == 25542642 && c.position & 10 != 0));
    q.decisions = result.resolved_decisions.clone();
    let audit = verify_query_replays(q, &result, &witnesses, journal.clone()).unwrap();
    assert!(audit.matches(q, &result, &witnesses));
    std::fs::write(path,serde_json::to_vec_pretty(&serde_json::json!({"scope":"independently authored human tournament pilot; not autonomous","request":q,"result":result,"witnesses":witnesses,"audit_calls":audit.call_ids,"consumed":journal.stats().unwrap().consumed})).unwrap()).unwrap();
    (result, witnesses)
}
#[test]
#[ignore = "opt-in: charged independent human pass and Scythe-Ash recovery; not autonomous planning"]
fn independent_human_pilot_establishes_pass_and_real_ash_recovery_baselines() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let pack = FirstTurnKnowledge::builtin().unwrap();
    let base = request(&root, &pack);
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let dir = root.join(format!("data/runtime/tournament-2026/pilot-human/{stamp}"));
    std::fs::create_dir_all(&dir).unwrap();
    let mut outputs = vec![];
    for ash in [false, true] {
        let name = if ash { "scythe-ash" } else { "pass" };
        let mut q = base.clone();
        let journal =
            CallJournal::open(dir.join(format!("{name}.jsonl")), name, &pack.id(), 512).unwrap();
        let (result, witnesses) = manual(
            &mut q,
            journal.clone(),
            ash,
            &dir.join(format!("{name}.report.json")),
        );
        let trace = actual_trace_v6(&result, &Default::default(), &pack, &witnesses).unwrap();
        assert_eq!(trace.window, TraceWindow::OwnTurnEnded);
        assert_eq!(
            result
                .events
                .iter()
                .filter(|e| e.opcode == 70 && e.fields["code"] == 14558127)
                .count(),
            usize::from(ash)
        );
        if ash {
            assert!(result
                .events
                .iter()
                .any(|e| e.opcode == 76 && e.fields["chain"] == 1));
            assert!(!trace
                .facts
                .history
                .iter()
                .any(|h| h.kind == "effect_resolved"
                    && h.effect_id.as_deref() == Some("78449284:deck_special")));
        }
        println!(
            "{name}: {} calls, {} decisions, report {}",
            journal.stats().unwrap().consumed,
            result.resolved_decisions.len(),
            dir.display()
        );
        outputs.push(result);
    }
    let cut = outputs[0]
        .events
        .iter()
        .find(|e| e.opcode == 70 && e.fields["code"] == 78449284)
        .unwrap()
        .sequence;
    let own = |r: &DuelResult| {
        r.resolved_decisions
            .iter()
            .filter(|d| d.player == 0 && d.prompt_id <= cut)
            .cloned()
            .collect::<Vec<_>>()
    };
    assert_eq!(own(&outputs[0]), own(&outputs[1]));
}
