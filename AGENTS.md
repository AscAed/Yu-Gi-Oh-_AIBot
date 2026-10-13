# Repository Guidelines

## Project Structure & Module Organization

- `crates/` contains the Rust workspace: `ygo-domain` models cards and deck rules, `ygo-engine-adapter` integrates external EDOPro/ocgcore processes, `ygo-search` ranks Combo lines, `ygo-storage` stores snapshots, and `ygo-api`/`ygo-cli` expose service and command interfaces.
- `python/ygo_data` provides card-data validation/import tooling; `python/ygo_eval` is reserved for offline evaluation scripts.
- `schemas/` contains JSON contracts, `configs/` contains example runtime/scoring settings, and `data/` holds local raw, normalized, and snapshot data.
- Rust tests live beside each crate in `crates/*/tests`; shared fixtures are under `tests/fixtures`. Design and scope documentation is in `docs/`.

## Build, Test, and Development Commands

Run from the repository root:

```text
cargo fmt --all -- --check       # Verify Rust formatting
cargo clippy --workspace --all-targets -- -D warnings
cargo test --workspace           # Run all Rust unit/integration tests
py -m pip install -e .           # Install Python tools in editable mode
py -m ygo_data.cli validate --input tests/fixtures/cards.sample.json
cargo run -p ygo-cli -- engine doctor
```

Copy `configs/engine.example.toml` to the untracked `configs/engine.toml` and set the local EDOPro/ocgcore executable before running engine checks.

## Coding Style & Naming Conventions

Use Rust 2021 edition with `rustfmt`; keep public types and methods documented when their behavior is non-obvious. Use `PascalCase` for Rust types/enums, `snake_case` for functions, modules, fields, and test names. Python follows PEP 8, four-space indentation, `snake_case` functions, and type hints for public helpers. Keep comments short and explain decisions, not syntax.

## Testing Guidelines

Add focused tests before behavior changes. Name tests by observable behavior, such as `rejects_a_deck_with_a_banned_card`. Cover deck legality, engine adapter failures, deterministic search ordering, snapshot round trips, and schema/data validation. New rule or search behavior should include unit tests plus a regression fixture where practical.

## Commit & Pull Request Guidelines

History currently contains only `Initial commit`, so no project-specific convention is established. Use concise imperative subjects, for example `Add banlist snapshot validation`, and keep unrelated changes separate. Pull requests should describe behavior and scope, list verification commands and results, identify any external engine/data assumptions, and update `TASKS.md` or `docs/` when interfaces or workflow change. Do not commit engine binaries, card images, local paths, or unlicensed card databases.

## Architecture & Configuration Notes

Treat EDOPro/ocgcore as the authoritative effect executor. Convert external output into `EngineEvent` before search or API processing, and never label unsupported effects as engine-verified. Record rules, banlist, catalog, and engine versions with reproducible results.
