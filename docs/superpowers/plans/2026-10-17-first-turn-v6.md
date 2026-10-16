# First-turn v6 completion implementation plan

Binding spec: the user-approved plan "补齐v6语义闭环，完成48手固定评估" in this chat.

Goal: preserve the legal Aug17 main41/extra15 original deck and both frozen asset groups;
complete first-turn knowledge, causal planning/recovery and the fixed 16+32 evaluation.

Execution: inline using executing-plans and TDD. Preserve the existing dirty tree.
Source baseline 0fcdc2e; pre-existing work is copied to the ignored implementation-start snapshot.

## Global constraints

- OCG/MR5, frozen October2026 banlist, seed1, Rusty on field + Fog set.
- Single opponent Ash, independent legal main40/hand1/deck39; no other opponent responses.
- Planning/runtime/analysis v6, phantom-first-turn-v1, fixed-ash-first-turn-v1.
- Old v1-v5 contracts/identities remain unchanged; no card edits, core upgrades, HTTP or extra handtraps.
- At most8 proposals,5000 expansions,frontier32; per-cell512 calls,64 semantic steps including prefix/response/triggers.
- Charge execution/probes/witnesses/first replay together, discovery in corresponding pass cells.
- Explicitly allowed independent legal rule-verification decks never prove tournament reachability.
- Classifications are not implementations; successful lines are not proof of every effect.
- External shell requests use the required same-invocation127.0.0.1:7897 proxy.

## Task1: integrated, source-bound foundation

- Reproduce the missing knowledge-module test failure; implement the five declared interfaces.
- Validate complete card/rule coverage, exact descriptions, source hashes and evidence references.
- Keep curated/implemented/verified/excluded distinct; no fabricated verified entries.
- Finish portable LF identities; refresh source receipts without overwriting raw historical evidence.
- Default Rust, Python, fmt, Clippy; commit.

## Task2: persistent engine debit layer before bulk verification

- Durable debit before spawn; completed content-addressed result after run; write failure prevents call.
- Unknown calls stay charged; reservations are not consumption; retries are new charges.
- Per-scope budgets and safe checkpoints; preserve candidate order and complete search state.
- Test crash boundaries and tampering; commit with reusable Rust adapter and isolated audit scopes.

## Task3: first-turn effects and real cases

- New PK resource transitions, summon/material/rank/locks, then chains/draw/end-phase handling.
- Start from102 classified rules/86 inside; reclassification requires source/evidence and a recorded reason.
- Each activation has actual resolution positive and condition/resource negative; procedures/continuous rules use raw observable assertions.
- Human preparation uses engine actions, never forged state; every case cap512 including replay.
- Source/structure validation and semantic verification remain separate. Only verified effects produce Ash columns.
- Groups have independent commits and source-bound evidence; no goal-based exclusion.

## Task4: autonomous v6 planning, recovery and contracts

- New schemas/API/CLI dispatch; preserve legacy paths and scoring precedence.
- Goal-driven symbolic operators, instance/role-aware binding, actual-prefix state reconstruction.
- Pre-execution reasons; public observation without hidden deck order; observe and replan after draws.
- Freeze up to2 different first-sensitive openings before policy experiments.
- Distinguish unreached/illegal/countered/effective Ash and ineffective own responses.
- Re-evaluate actual terminal after all chains/triggers/end-phase returns; independently replay dependencies.
- Identity binds source/assets/coverage/knowledge/goal/strategies/limits/bilateral decisions.
- Test real autonomous new-PK goal line and post-Ash recovery, report forgeries and budget truncation; commit.

## Task5: immutable 16+32 suite, evaluation and final acceptance

- Preserve old16; functional8 reachable+4 constrained+4 unsupported/budget.
- Tournament32, eight input-feature strata of4, exact original deck and five-card hands.
- Freeze suite/labels/manual baselines before formal results: at least16 pass goal recipes,8 actual-Ash response/recovery recipes.
- Python run --suite --output-dir and verify --input, suite/reportv1, hashed child references.
- Matrix max16*8192+32*2*(P+1)*512; case, deployment and repeat audit costs separate.
- Safe checkpoint resume equal semantic outcomes/IDs/charged sequence; in-call crash differences disclosed.
- All existing16 effect/16 hand/14 goal/v4-v5 and historical report regressions.
- Final fmt/Clippy/default/live/Python and clean-checkout dual-asset offline build/deploy/doctor/replay/repeat.
- Fresh whole-branch review, fixes, docs and final commits; only then mark full acceptance.

## Review focus

- Caller-supplied hashes/statuses cannot substitute for verified registry contents and replay.
- Same-name instance ambiguity and source snapshots around costs/material transfer.
- Raw events/prompt metadata must not reintroduce hidden deck order into planning.
- Mandatory chain/end-phase processing and opponent forced choices after effect rewriting.
- Debit/result/checkpoint crash atomicity, denominator and bounded-failure classification.
