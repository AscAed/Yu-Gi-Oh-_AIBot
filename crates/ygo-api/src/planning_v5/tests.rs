use super::*;
#[test]
#[ignore = "opt-in frozen engine: human preparations for all seven Ash response effects"]
fn seven_effects_have_actual_ash_negation_and_replayed_paid_prefixes() {
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    std::env::set_current_dir(&root).unwrap();
    let engine =
        ProcessEngineConfig::from_toml(&std::fs::read_to_string("configs/engine.toml").unwrap())
            .unwrap();
    let store = SnapshotStore::new(root.join("data/snapshots"));
    let active: serde_json::Value =
        serde_json::from_slice(&std::fs::read(store.root.join("active.json")).unwrap()).unwrap();
    let base: PlanRequest = serde_json::from_str(include_str!(
        "../../../../tests/fixtures/ash-strategy.request.json"
    ))
    .unwrap();
    let pack = KnowledgePack::read(&root.join("knowledge/phantom-v2.json")).unwrap();
    std::fs::create_dir_all("data/runtime/ash-strategy-cases").unwrap();
    for target in ASH_EFFECTS {
        let mut q = base.clone();
        if matches!(target, "32807846:search" | "81439173:mill") {
            q.analysis.opening_hand[2] = CardId(target.split_once(':').unwrap().0.parse().unwrap());
        }
        q.validate().unwrap();
        let (_, mut rt, cat) = crate::combo::prepare(
            q.analysis.clone(),
            engine.clone(),
            &store,
            active["catalog_id"].as_str().unwrap(),
        )
        .unwrap();
        rt.protocol_version = 5;
        rt.versions.initializer = "fixed-ash-strategy-v1".into();
        let mut op = q.opponent.clone();
        op.policy = "ash_effect_once".into();
        op.effect_id = target.into();
        rt.interruption = Some(op);
        let (code, description) = ash_effect_descriptor(target).unwrap();
        assert!(ygo_goal::matches_description(
            pack.effect(target).unwrap(),
            code,
            description
        ));
        let sequence: Vec<&str> = match target {
            "25538345:mill" => vec!["25538345:normal", target],
            "90432163:search" => vec!["25538345:normal", "25538345:mill", target],
            "36426778:search" | "63821877:mill" => vec![
                "25538345:normal",
                "36426778:summon",
                "58699500:link",
                "58699500:mill",
                target,
            ],
            "26692769:mill_set" => vec![
                "25538345:normal",
                "25538345:mill",
                "90432163:search",
                "36426778:summon",
                "88544390:summon",
                "26692769:link",
                target,
            ],
            _ => vec![target],
        };
        let mut state = initial(&q, &cat).unwrap();
        let mut steps = vec![];
        for effect in sequence {
            let step = v3::transitions(&state, &cat, &pack, &q.goal)
                .into_iter()
                .find(|s| {
                    s.effect_id == effect
                        && (effect != "25538345:mill"
                            || (s.costs.iter().any(|c| c.code == 2964201)
                                && s.targets.iter().any(|c| c.code == 90432163)))
                        && (effect != "90432163:search"
                            || s.targets.iter().any(|c| c.code == 88544390))
                        && (effect != "58699500:mill" || s.costs.iter().any(|c| c.code == 63821877))
                        && (effect != "63821877:mill"
                            || s.targets.iter().any(|c| c.code == 90432163))
                })
                .unwrap_or_else(|| panic!("manual transition {effect}"));
            state = step.after.clone();
            steps.push(step);
        }
        let p = Proposal {
            id: hash(&("human-ash-v5", target, &steps)),
            steps,
            goal_predicted: false,
        };
        let out = execute_general(
            &ProcessEngineAdapter::new(engine.clone()),
            &rt,
            Proposals {
                plans: vec![p.clone()],
                expansions: 0,
                termination: "human_preparation".into(),
                coverage_gaps: vec![],
            },
            &q.analysis.search,
            &Default::default(),
            &pack,
            true,
            |_| true,
        )
        .unwrap();
        let attempt = out.attempts.first().expect("manual attempt");
        let o = attempt.observation.clone().unwrap();
        assert!(response_hit(&o), "{target}: {:?}", attempt.discrepancies);
        assert_eq!(
            o.events
                .iter()
                .filter(|e| e.opcode == 70
                    && e.fields["code"] == 14558127u32
                    && e.fields["player"] == 1)
                .count(),
            1
        );
        let mut progress = FailedSettlement {
            selections: vec![],
            observation: o.clone(),
            used_calls: 0,
            replay_attempts: 0,
            error: String::new(),
        };
        let anchor = settle(
            rt.clone(),
            o.clone(),
            &cat,
            &pack,
            p.steps.len() + 1,
            32,
            512 - out.search.stats.engine_calls,
            &mut progress,
        )
        .unwrap_or_else(|e| panic!("{target}: {e}"));
        let facts = ygo_goal::actual_facts(&anchor.observation, &cat, &pack);
        assert!(facts
            .history
            .iter()
            .any(|h| h.kind == "effect_negated" && h.effect_id.as_deref() == Some(target)));
        assert!(!facts
            .history
            .iter()
            .any(|h| h.kind == "effect_resolved" && h.effect_id.as_deref() == Some(target)));
        assert!(anchor.observation.events.iter().any(|e| e.opcode == 50
            && e.fields["code"] == 14558127u32
            && e.fields["reason"].as_u64().unwrap_or(0) & 128 != 0));
        if matches!(
            target,
            "36426778:search" | "90432163:search" | "63821877:mill"
        ) {
            assert!(anchor.observation.events.iter().any(|e| e.opcode == 50
                && e.fields["code"] == code
                && e.fields["to"]["location"] == 32
                && e.fields["reason"].as_u64().unwrap_or(0) & 128 != 0));
        }
        if matches!(target, "32807846:search" | "81439173:mill") {
            assert_eq!(anchor.state.normal_left, 1);
        }
        let prompt = anchor.observation.prompt.as_ref().unwrap();
        let raw = anchor
            .observation
            .events
            .iter()
            .find(|e| e.sequence == prompt.id)
            .unwrap();
        assert!(
            !prompt_metadata(prompt.id, &raw.raw)
                .unwrap()
                .iter()
                .any(|m| m
                    .source
                    .as_ref()
                    .is_some_and(|s| s.player == 0 && s.code == code)
                    && m.effect_description == Some(description)
                    && matches!(m.choice, Choice::Command { command: 5, .. })),
            "consumed activation must not reappear: {target}"
        );
        if matches!(target, "36426778:search" | "63821877:mill") {
            assert!(anchor
                .state
                .cards
                .iter()
                .any(|c| c.player == 0 && c.code == 25538345 && c.location == 4 && c.redirect));
        }
        if target == "36426778:search" {
            let chained = o
                .events
                .iter()
                .find(|e| e.opcode == 70 && e.fields["code"] == 58699500u32)
                .unwrap();
            let solved = o
                .events
                .iter()
                .find(|e| {
                    e.sequence > chained.sequence
                        && e.opcode == 73
                        && e.fields["chain"] == chained.fields["chain"]
                })
                .unwrap();
            for raw in o
                .events
                .iter()
                .filter(|e| e.sequence > chained.sequence && e.sequence < solved.sequence)
            {
                if let Ok(ms) = prompt_metadata(raw.sequence, &raw.raw) {
                    assert!(!ms.iter().any(|m| m
                        .source
                        .as_ref()
                        .is_some_and(|s| s.player == 1 && s.code == 14558127)));
                }
            }
        }
        verify_witness(&anchor.witness, &engine).unwrap();
        assert!(out.search.stats.engine_calls + anchor.used_calls + anchor.reserved_calls <= 512);
        std::fs::write(format!("data/runtime/ash-strategy-cases/{}.json",target.replace(':',"-")),serde_json::to_vec_pretty(&serde_json::json!({"request":q,"human_proposal":p,"attempt":attempt,"anchor":anchor,"calls":out.search.stats.engine_calls+progress.used_calls+progress.selections.len()+1})).unwrap()).unwrap();
    }
}
