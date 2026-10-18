# Repository Guidelines

开始工作先读 [`docs/INDEX.md`](docs/INDEX.md) 和 [`TASKS.md`](TASKS.md)。任务状态、架构和历史验证各有唯一事实源；不要从旧计划或过往对话推断当前实现。

## Project Structure & Module Organization

- `crates/` contains the Rust workspace. Core areas include `ygo-domain`, `ygo-engine-adapter`, `ygo-search`, `ygo-planner`, `ygo-goal`, `ygo-knowledge`, `ygo-storage`, `ygo-api`, and `ygo-cli`; use root `Cargo.toml` and crate dependencies as the authoritative map.
- `python/ygo_data` provides card-data validation/import tooling; `python/ygo_eval` provides offline evaluation utilities.
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

Use the local frozen assets and deployment scripts described in `docs/DEPLOYMENT.md`. The generated package binds to local absolute asset paths and is not portable by itself.

## Coding Style & Naming Conventions

Use Rust 2021 edition with `rustfmt`; keep public types and methods documented when their behavior is non-obvious. Use `PascalCase` for Rust types/enums, `snake_case` for functions, modules, fields, and test names. Python follows PEP 8, four-space indentation, `snake_case` functions, and type hints for public helpers. Keep comments short and explain decisions, not syntax.

## Testing Guidelines

Add focused tests before behavior changes. Name tests by observable behavior, such as `rejects_a_deck_with_a_banned_card`. Cover deck legality, engine adapter failures, deterministic search ordering, snapshot round trips, and schema/data validation. New rule or search behavior should include unit tests plus a regression fixture where practical.

## Commit & Pull Request Guidelines

Use concise imperative commit subjects and keep unrelated changes separate. Pull requests should describe behavior and scope, list verification commands and results, identify external engine/data assumptions, and update the normative docs when interfaces or workflow change. Do not commit engine binaries, card images, local paths, or unlicensed card databases.

## Architecture & Configuration Notes

Treat ocgcore as the authoritative effect executor. Convert external output into `EngineEvent` before search or API processing, and never label unsupported effects as engine-verified. Record rules, banlist, catalog, engine, knowledge and schema versions with reproducible results. Do not delete compatibility paths or local evidence until their consumers and retention purpose are checked.
