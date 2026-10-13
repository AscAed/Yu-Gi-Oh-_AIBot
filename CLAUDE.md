# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Run from the repository root:

```bash
cargo fmt --all -- --check
```
```bash
cargo clippy --workspace --all-targets -- -D warnings
```
```bash
cargo test --workspace
```
```bash
cargo test -p ygo-domain
```
```bash
cargo run -p ygo-cli -- engine doctor
```
```bash
py -m pip install -e .
```
```bash
py -m ygo_data.cli validate --input tests/fixtures/cards.sample.json
```

Before running engine checks, copy `configs/engine.example.toml` to the untracked `configs/engine.toml` and set the local EDOPro/ocgcore executable path.

## Architecture

The system is five layers, with a strict dependency direction: Data → Domain → Engine Adapter → Search/Scoring → API/CLI.

**Rust workspace** (`crates/`):
- `ygo-domain` — Core value types: `CardId`, `Deck`, `BanlistSnapshot`, `DeckValidationReport`, `EngineEvent`, `ComboResult`. No external engine coupling; keeps rule logic strictly to OCG MR5/2020 deck legality (main 40–60, extra ≤15, side ≤15, same-name ≤3, banlist).
- `ygo-engine-adapter` — Translates EDOPro/ocgcore external process I/O into `EngineEvent` streams. This is the only layer allowed to speak the engine protocol. Effect resolution authority lives here, not in search.
- `ygo-search` — Read-only consumer of `EngineEvent` and domain state. Expands candidate builds + opening hands + opponent scenarios into a scored state graph. Weights are in `configs/scoring.toml`. Depends only on `ygo-domain`.
- `ygo-storage` — Snapshot metadata persistence (SQLite, not yet implemented).
- `ygo-api` / `ygo-cli` — Stable public surfaces. `ygo-cli` includes the `engine doctor` sub-command for health checks.

**Python package** (`python/`):
- `ygo_data` — Card data validation/import CLI (`ygo-data` entry point). Validates JSON against `schemas/card.schema.json` and `schemas/banlist.schema.json`.
- `ygo_eval` — Reserved for offline evaluation scripts; currently empty.

**Configuration** (`configs/`):
- `default.toml` — Runtime defaults (`rule_set`, `banlist`, `top_k`, `search_budget`, `engine_adapter`).
- `scoring.toml` — Search scoring weights (end-board interaction, resources, hand-trap resilience, opponent draw count, play complexity).
- `engine.toml` — Local engine path; **not tracked**; copy from `engine.example.toml`.

**Schemas** (`schemas/`) — JSON contracts for `card`, `banlist`, `deck-request`, and `combo-result`. All inter-component data must conform; results must carry `rules`, `banlist`, `catalog`, and `engine` versions.

## Key invariants

- **Engine is the rule authority.** Never label an effect as engine-verified unless `ygo-engine-adapter` confirmed it. Unsupported or heuristic effects must be tagged `unsupported` or `heuristic` in `ComboResult`.
- **No silent success.** Unsupported card effects or engine protocol failures must surface as explicit errors, not be swallowed as successful outcomes.
- **Versioned results.** Every `ComboResult` must record `rules`, `banlist`, `catalog`, and available `engine` version so outputs are reproducible.
- **Combo branches are separate.** Search outputs for no-handtrap, Maxx "C", Droll & Lock Bird, negation-point, and board-breaker scenarios must remain distinct; they must not be merged into an unconditional success conclusion.
- **No committed binaries or card data.** Do not commit engine binaries, card images, local paths, or unlicensed card databases. `data/raw/`, `data/normalized/`, `data/snapshots/` hold local-only files.

## Scope

- **Rules:** OCG only, Master Rule 2020 / MR5 (effective 2020-04-01). GENESYS, TCG, and version-unbound rulings are out of scope.
- **Platform:** Windows-primary; keep paths and process calls cross-platform where practical.
- **Toolchain:** Rust stable (see `rust-toolchain.toml`), Python ≥ 3.10.

## Testing

Rust integration tests live in `crates/*/tests/`; shared fixtures in `tests/fixtures/`. Name tests by observable behavior (`rejects_a_deck_with_a_banned_card`). New rule or search behavior requires unit tests plus a regression fixture where practical. Cover: deck legality, engine adapter failures, deterministic search ordering, snapshot round-trips, schema/data validation.
