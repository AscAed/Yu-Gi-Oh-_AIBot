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
API and report contracts are unchanged. The resumable loop begins from an
already charged and completed initial `Execution` call. Its current phase is
one of semantic execution, End Phase, independent query audit, complete, or
blocked. Semantic state includes the operation's before-state, event boundary,
selected transition, used selection indices, predictions, instance mapping,
decision evidence, and interruption diagnostics.

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
- `begin_resumable_partial_execution_v1`: create a versioned outer loop cursor
  around the A3 per-call cursor. Callers provide prior query witnesses and a
  matching `AuditedQueries` capability created by independent replay; the
  capability must bind the exact initial request, charged result, and complete
  witness list (including the current prompt). Unverified history cannot affect
  semantic choices. An empty semantic plan may be used to process an already
  observed prompt through End Phase.
- `advance_resumable_partial_execution_v1`: select one step through the same
  `successors`, `same_action`, `bind_start`, `follow_choice`, resource comparison,
  and instance-map helpers as the synchronous loop, persist the full loop intent,
  then delegate exactly one charged action to `advance_execution_v1`.
- `advance_resumable_query_audit_v1`: advance one witness-prefix or
  terminal-root audit call, using a separate `Witness` purpose reservation and
  a separately persisted audit cursor. The synthetic adapter hook is test-only;
  neither path constructs an `AuditedQueries` capability or a
  `PartialExecutionV2` report.
- `resume_resumable_partial_execution_v1`: authenticate the outer state and
  journal read-only first, then release it and strictly reopen the journal.
  A completed trailing execution or witness call is reused after request,
  purpose, result and sequence checks. A proven uncharged intent can be cleared
  for a later caller-driven advance; unresolved or unknown consumption blocks.

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
| Query-audit reservation was written before its progress checkpoint | Accept only the exact expected reservation for the saved query cursor, then publish the journal snapshot before continuing. |
| Another writer changes the journal between inspection and exclusive reopen | Strict reopen/sequence check rejects; strict open does not create or repair files. |
| Budget is exhausted before a continuation | Save a paused intent; adapter calls remain zero. |
| Result is terminal or contains an error | Preserve the result/diagnostic, but do not create a receipt or formal success. |
| Outer semantic phase, mapping, selection, or query cursor differs from its saved boundary | Reject before the next adapter call. |
| Query audit has a completed trailing witness/root call | Authenticate and reuse it; do not charge a duplicate audit call. |
| Query audit has a charged but unresolved tail or changed reservation | Keep the accounting unknown and refuse further work. |

The recovery path is deliberately conservative. A failure leaves accounting in
the journal; it never refunds, silently retries, or treats a missing result as
zero consumption. The checkpoint records both aggregate ledger statistics and
the reservation token-to-count map. Resume compares that map with the journal's
checkpoint snapshot and current state before it can continue.

## Validation boundary

Synthetic tests exercise both an empty-plan End Phase/query-audit recovery and a
non-empty two-action semantic route. The latter uses the frozen repository trace
fixture for an XYZ procedure and consecutive prompts, then a synthetic normal
summon result, End Phase, and query audit. Continuous and prompt-boundary
pause/reopen runs compare decision evidence, predictions, instance mapping,
used selections, 13 witnesses, actual prefix, reservations, and the ordered
26-call ledger (12 `Execution`, 14 `Witness`). The query-audit cursor's own
pause/reopen remains covered by a separate End Phase/query-audit test.

Test-only interruption hooks cover failure while publishing a semantic
snapshot and while publishing the outer call intent; both fail before the next
adapter invocation and leave the existing debit intact. Another injected stop
occurs after a completed result is in the journal but before its progress
checkpoint is published. Recovery authenticates and reuses that trailing result
without a duplicate charge. Existing A3 coverage also refuses unresolved
consumption. A deterministic competing-writer test appends a valid synthetic
call after the outer read-only inspection releases its handle and before inner
recovery; the new unbound ledger entry is retained and resume refuses to
continue. A separately held exclusive writer also prevents resume. These tests
exercise the real `CallJournal` parser, locks, accounting and checkpoint code
with synthetic results; they do not simulate OS process death at every
filesystem write boundary.

No native engine, runner, worker, FFI or research-budget call was made. The
synthetic adapter does not mint `PartialExecutionV2`, `AuditedQueries`, or any
native qualification. Real process pause/reopen, OS-level crash injection,
replay against frozen live assets, and formal independent replay remain
uncertified.
