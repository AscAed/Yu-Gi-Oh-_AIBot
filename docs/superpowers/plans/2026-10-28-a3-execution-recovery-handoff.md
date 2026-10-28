# A3 execution recovery handoff

## Delivered in this offline batch

- Added `ExecutionCheckpointV1`, `ExecutionIntentV1`, `begin_execution_v1`,
  `advance_execution_v1`, `persist_execution_semantics_v1`, and
  `resume_execution_v1` under `ygo_planner::first_turn`.
- Checkpoints bind request, plan, catalog, knowledge, goal and runtime-version
  identity. Progress stores stage/step, request and actual prefix, resource
  snapshot, mapping, used selections, forecasts, query witnesses, pending
  intent/action, call IDs, journal budget and reservation token ownership, and
  stable diagnostic text.
- Intent is saved immutably before a charged continuation. Completed trailing
  calls can be authenticated and reused after restart. Unknown or unresolved
  debits, malformed journals, binding mismatch, or concurrent journal changes
  stop progress without refund or retry.
- Added `CallJournal::open_existing_strict`: exclusive reopen of an existing,
  complete journal with no create/repair behavior. `resume_execution_v1`
  uses it after read-only authentication, then rechecks the charge sequence.
- Added schema `first-turn-execution-checkpoint-v1.json` and the state/failure
  contract in [`EXECUTION_RECOVERY.md`](../../EXECUTION_RECOVERY.md).

## Test coverage

Synthetic tests compare continuous execution with repeated pause/reopen for
charged sequence, current prefix, resources, predictions, mappings, query
witnesses and budget. Additional tests cover changed plan/request, exhausted
budget before adapter invocation, completed trailing result reuse, unresolved
debit refusal, repeated zero-call resume, and strict journal open rejecting a
torn tail without changing its bytes.

Evidence and logs are in the ignored `target/a3-resumable/` directory. No
native engine, runner, worker, FFI, doctor, or live-asset path was run. The
known C1 Tenki protected-source hash failure is unchanged and was not re-run as
part of this Rust-only batch.

## Current boundary and next work

This is an offline planner/journal API; it does not yet replace the legacy
monolithic `execute_partial_v2_with_backend` loop. The public `advance` API
calls the configured engine adapter, but this batch only exercised its
test-only synthetic backend. Do not treat synthetic results as native evidence
or qualification. Keep A3/R1b open until a separately authorized new scope
validates the real execution integration, process pause/reopen, unknown-debit
handling, and independent replay. No new scope, window, ledger, deployment,
commit, or push was created here.

## Accounting and preserved work

No new research calls were made. The certified subset remains 40, the policy
reserve 7, and planning basis 47; all-history actual consumption remains
unknown. Existing C1 and B2 uncommitted changes were preserved.
