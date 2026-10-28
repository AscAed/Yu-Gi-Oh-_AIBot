# First-turn execution checkpoints

## Scope

`ExecutionCheckpointV1` is a durable progress cursor for a caller-driven,
one-decision-at-a-time execution path. It binds the starting request, forecast
plan, catalog, knowledge pack, goal, and runtime versions. The checkpoint stores
the current request and authenticated actual prefix, an explicit resource
snapshot, instance mapping, used selections, predictions, query witnesses,
budget state including reservation token ownership, and any pending action/intent.

The checkpoint is not a native qualification, search checkpoint, query receipt,
or success certificate. Deserializing it never recreates the runtime receipt
required by `PartialExecutionV2::verified`. The legacy synchronous execution
API and report contracts are unchanged. This API begins from an already charged
and completed initial `Execution` call; integrating it into the existing
monolithic native loop and proving that path with frozen real assets remain
future work.

## Library API

The planner exposes these operations from `ygo_planner::first_turn`:

- `begin_execution_v1`: authenticate the already-completed initial call and
  persist the first checkpoint. It performs no engine call.
- `ExecutionIntentV1::from_prompt`: derive one continuation from the exact
  current raw prompt, a legal menu choice, and the matching request decision.
- `persist_execution_semantics_v1`: save forecasts, selections, and instance
  mapping at a no-call boundary after checking visible instance identities.
- `advance_execution_v1`: persist immutable intent and pending state before
  making exactly one charged `Execution` call, then authenticate its journal
  result and update the progress checkpoint.
- `resume_execution_v1`: inspect read-only first, authenticate the checkpoint,
  prefix, budget, and any trailing intent/call, release the read view, then open
  the existing journal exclusively without repairing it and recheck the charged
  sequence before reconciling.

The explicit synthetic adapter hook exists only under `cfg(test)` and is not
exported by the public `first_turn` module.

## State transitions

| Current state | Event | Next state | Recovery rule |
|---|---|---|---|
| `ready` | Intent and pending checkpoint saved | `intent_persisted` | Intent is immutable and names the expected next call. |
| `intent_persisted` | Budget has no unreserved slot | `paused` | No adapter call starts; the persisted intent is retained. |
| `intent_persisted` | Charged call returns a valid decision prompt and query capture succeeds | `ready` | Result and query witness are authenticated from the journal. |
| `intent_persisted` | Engine returns terminal `engine_verified` | `completed_awaiting_audit` | No independent audit or qualification is created. |
| `intent_persisted` | Partial result | `paused` | Prefix is retained; caller must not assume another prompt exists. |
| Any in-flight state | Worker error, prefix mismatch, query-capture failure, unknown debit, or invalid evidence | `blocked` | Preserve debit and diagnostics; do not retry automatically. |
| Saved intent + completed trailing journal call | Process stopped before progress publication | Reconciled result state | Reuse the exact charged result; never charge a duplicate call. |
| Saved intent + unresolved trailing journal call | Process stopped during a call | Refused / `blocked` | Unknown consumption remains charged and prevents progress. |

`actual_resources` is duplicated from the trusted prefix checkpoint and checked
for exact equality during recovery. It is descriptive state, not a source of
engine truth independent of the charged result.

## Failure and safety matrix

| Condition | Behavior |
|---|---|
| Request, plan, catalog, knowledge, goal, or versions differ | Binding rejection before continuation. |
| Choice is absent from the observed prompt or prompt identity changed | Intent rejected before charge. |
| Plan prediction or instance map references an unobserved/duplicate step | Semantic snapshot rejected; no engine call. |
| Checkpoint differs from journal snapshot or budget prefix | Resume refuses to advance. |
| Journal is truncated, malformed, unknown, abandoned, or has a different context | Read-only inspection rejects; no repair or free retry. |
| A call was charged but result is incomplete/unknown | Stop and retain unknown consumption. |
| Call completed but checkpoint publication was interrupted | Authenticate purpose, request, result and intent, then reuse that result. |
| Another writer changes the journal between inspection and exclusive reopen | Strict reopen/sequence check rejects; strict open does not create or repair files. |
| Budget is exhausted before a continuation | Save a paused intent; adapter calls remain zero. |
| Result is terminal or contains an error | Preserve the result/diagnostic, but do not create a receipt or formal success. |

The recovery path is deliberately conservative. A failure leaves accounting in
the journal; it never refunds, silently retries, or treats a missing result as
zero consumption. The checkpoint records both aggregate ledger statistics and
the reservation token-to-count map. Resume compares that map with the journal's
checkpoint snapshot and current state before it can continue.

## Validation boundary

Synthetic tests compare continuous calls with pause/reopen calls for charged
sequence, actual prefix, query witnesses, resource snapshot, predictions, and
instance mappings. They also simulate a completed trailing call and an
unresolved debit. No native engine, runner, worker, or FFI call was made for
this implementation. Real execution pause/reopen, result persistence under
process termination, and independent replay are not yet certified.
