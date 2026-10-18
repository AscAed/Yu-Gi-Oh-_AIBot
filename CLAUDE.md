# Agent guidance

Start with `docs/INDEX.md` and `TASKS.md`. Use source code, schemas, deployment scripts and latest dated verification as evidence; old plans and conversations are context only. Do not claim planned or locally simulated behavior as delivered capability.

## Repository facts

Consult `docs/INDEX.md` for the current module map and normative docs. This older file intentionally no longer duplicates architecture, supported scope, CLI contracts, or task status.

## Checks

```powershell
cargo fmt --all -- --check
cargo clippy --workspace --all-targets --offline -- -D warnings
cargo test --workspace --offline --locked
$env:PYTHONPATH='python'
py -m unittest discover -s tests -p 'test_*.py'
```

See `docs/DEPLOYMENT.md` for frozen assets and opt-in native checks. Preserve local evidence and compatibility paths until their consumers are checked. Never label a prediction or unsupported result as engine verified.
