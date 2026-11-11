# B6 design — coordinator send-queue: on-wire charge vs heap footprint (2026-11-10)

**Direction · sub-direction:** bypass · accounting mismatch (protocol *Classification by
measurement*: U > C with K ≤ C). Secondary path recorded separately: write-callback retention
after flush. **Source:** cassandra-5.0.9 (`b5f2a54210`), local copy `/mydata/b6/cassandra`.
**Origin:** C1 discussion 2026-11-10 — the receive side is capped (N·Q + G) and pushes back to
senders, so the sender side is the next place memory can accumulate.

## 1. Control and contract (source-verified)

- `OutboundConnection.enqueue` (`OutboundConnection.java:325–357`) charges each message
  `canonicalSize = message.serializedSize(current_version)` (`:1045–1048`) against the
  per-link queue (4 MiB), then the per-destination reserve (128 MiB) and the global reserve
  (512 MiB). When both fail it **drops** the message (`onOverloaded`, `:456`), after one
  `maybePruneExpired` retry (`:341`). There is also a pending-count cap (`isMaxPendingCount`).
- **Contract (cassandra.yaml, internode section):** "These limits are applied to the
  **on-wire size** of the message." So the counter K is on-wire bytes by design.
- Queued messages are **heap objects** (`Message<Mutation>`); they are serialized only when
  flushed. Heap per message depends on object shape; on-wire size does not.
- **Second path:** the coordinator's write handler keeps the `Mutation` as `hintOnFailure`
  (`Mutation.hintOnFailure()` returns `this`, `Mutation.java:158`;
  `AbstractWriteResponseHandler.java:81,309`), reachable from the callback map until every
  replica answers or the callback expires (`write_request_timeout`). This holds even with
  hints disabled. After a message is flushed it is no longer charged to the sender's queue,
  but its `Mutation` stays on the coordinator heap while the slow replica holds it (charged
  only to the *replica's* receive queue, in another JVM).

**Contract capacity C (one slow destination, one link type):** 4 MiB + 128 MiB = 132 MiB
on-wire. **K** = `system_views.internode_outbound.pending_bytes` (+ `using_reserve_bytes`) at
the coordinator for the slow peer. **U** = live coordinator heap attributable to queued and
in-flight mutations (heap after full GC minus idle baseline; class histogram).

## 2. Hypothesis and predictions

Mutations made of many tiny cells serialize to a few bytes per cell but occupy far more heap
(row/cell objects, `ByteBuffer`s, B-tree arrays). Let R = U / (on-wire bytes held).
- **Tiny-cell payload:** R ≫ 1. With the sender queue at its cap, U ≈ R × (132 MiB queued +
  up to 132 MiB flushed and held at the slow replica). Prediction: R in 5–20.
- **Matched control — one blob cell of the same on-wire size:** R ≈ 1–2.
- A coordinator heap that survives the blob control at full queue OOMs under the tiny-cell
  payload while K stays ≤ C → bypass (accounting mismatch), interpretation **documented
  accounting unit / sizing gap**, not automatically a defect (the contract says on-wire).

## 3. Topology (single host, node0 `jason92-325405`, 32 cores / 125 GiB)

Three instances on loopback addresses, `GossipingPropertyFileSnitch`, `num_tokens: 1`,
explicit tokens, hints off on all, key/counter cache 0:

| Instance | Address | dc | Role | Heap |
|---|---|---|---|---|
| V | 127.0.0.11 | v | slow replica: Byteman 100 ms at `MutationVerbHandler.doVerb` entry, `concurrent_writes: 2` | 2 GiB |
| F | 127.0.0.12 | f | fast replica, satisfies CL=ONE so the client never waits on V | 8 GiB |
| **S** | 127.0.0.13 | c | **measured coordinator**, owns no replica; the client talks only to S | budget (below) |

Keyspace `NetworkTopologyStrategy {v:1, f:1}`, CL=ONE (run-3 decoupling). Every write goes
S→F (fast) and S→V (slow). V fills its receive queue from S (4 + 128 MiB), stops reading,
TCP backs up, S's send queue to V fills to C and then drops (`overload_count` rises).

Client: Python (driver bundled with cqlsh) on the same host, async prepared inserts to S only.
- **Tiny-cell payload:** `t_map(pk int PRIMARY KEY, m map<int,int>)`, one row per insert
  with a K-entry map (calibrate K ≈ 1000).
- **Blob control:** `t_blob(pk int PRIMARY KEY, b blob)` with a blob sized so the on-wire
  mutation size matches the tiny-cell mutation (measured from `pending_bytes/pending_count`).

## 4. Configuration audit

| Change | Class | Value | Why |
|---|---|---|---|
| send/receive queue capacities | tested capacity (default) | 4 / 128 / 512 MiB | the control under test |
| S `-Xmx` | budget | 8 GiB calibration; frozen diagnostic budget for the OOM stage | stopping budget |
| S `write_request_timeout` | supporting deviation | 60 s (default 2 s) | let queues fill at modest client rate; a default-timeout arm follows if positive |
| V Byteman delay, `concurrent_writes: 2` | supporting deviation (intervention) | 100 ms | slow replica (as C1) |
| `hinted_handoff_enabled` | supporting deviation | false | remove hint memory from S |
| snitch/dc/tokens/addresses, caches 0 | environment | — | single-host 3-instance ring |

## 5. Stages and stop rules

- **A — calibration (S heap 8 GiB).** Reachability: S→V `pending_bytes` reaches ~C and
  `overload_count` > 0 while F keeps up and the client gets acks. Then hold the load, take
  `jcmd GC.class_histogram` on S at full queue and at idle (after callbacks expire). Compute
  R for tiny-cell and blob. **Stop and file negative if R(tiny) < 3** (the effect would be
  inside ordinary headroom).
- **B — boundary (frozen S heap).** Pick the S heap so the blob control at full queue keeps
  ≥ 30% free; run tiny-cell vs blob at that heap, ≥ 3 clean starts each. Record heap OOM,
  K at failure, overload/expired counts.
- **C — intervention.** Shrink the S send-queue endpoint reserve so R × charged fits (or
  restore the default 2 s timeout) and show the tiny-cell OOM disappears at matched load.

Raw data: `/mydata/b6/runs/<arm>/`. Limit: about 4 hours of runs for this session; nothing
left running afterwards.
