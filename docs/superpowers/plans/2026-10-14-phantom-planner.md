# Phantom Knights semantic planning implementation

Approved brief: the user's 2026-10-14 plan in this chat is the binding specification.

1. Establish a reviewed local source baseline, strengthen v2 report rejection tests, and verify a clean checkout against frozen assets.
2. Add ygo-knowledge: separately versioned, manually curated effect semantics for the twelve selected cards, source hashes, three-valued conditions and effect-specific coverage. No catalog snapshot migration.
3. Add raw prompt metadata without changing legacy Action/Choice serialization. Preserve effect descriptions and candidate instance locations.
4. Add ygo-planner: bounded causal proposals before engine execution, goal rusty-fog, resource/usage/restriction accounting, exact prompt binding, pre-execution reasons, discrepancy reporting and independent replay within shared budgets.
5. Add knowledge validate, card explain, combo plan and combo plan-replay, strict request/report schemas, fixed fixtures and negative/regression tests.
6. Compare the planner and existing beam at the same node budget, update deployment/testing/roadmap/tasks and review the whole patch.

Defaults: OCG/MR5 first turn, fixed five-card hand, passive opponent; at most eight proposals and 32 semantic steps. Rank goal completion, hand/field card resources, decision count, stable line ID. Grave resources are explained separately. No LLM, handtrap policy, deck optimizer or HTTP service in this delivery.

Compatibility: keep AnalysisReport v2 and existing worker byte responses. PlanReport v1 embeds the v2 report. Knowledge validation does not imply universal engine correctness; evidence is scoped to fixture cases.

Verification: cargo fmt/clippy/workspace tests offline; Python default and opt-in suites; legacy Rabbit report replay; Phantom live engine goal and negative cases; clean source checkout build/deployment/replay; fixed node comparisons. External assets stay ignored and terminal network operations set the specified local proxy in the same invocation.
