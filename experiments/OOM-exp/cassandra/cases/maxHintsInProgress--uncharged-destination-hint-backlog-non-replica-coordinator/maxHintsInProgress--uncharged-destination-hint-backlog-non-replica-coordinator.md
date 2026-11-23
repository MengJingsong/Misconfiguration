# B23 (OC-147) — maxHintsInProgress: the per-destination counter is never charged, so hint tasks queued behind the parked hint writer exhaust a non-replica coordinator's heap  <!-- file: cassandra/cases/maxHintsInProgress--uncharged-destination-hint-backlog-non-replica-coordinator/maxHintsInProgress--uncharged-destination-hint-backlog-non-replica-coordinator.md -->

| Field | Value |
|---|---|
| Case ID | `B23` (B = bypass case; README "ID prefixes") |
| From | `OC-147` of the phase 1 OOM candidate list (11-18 triage rank 15), with its duplicates (§1.2) |
| Phase-1 case file | [`maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md) (stage-4 results: [`results/…--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md)) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`), build `/mydata/s4/cassandra-base` on `pc75` (`apache-cassandra-5.0.9-SNAPSHOT.jar`), OpenJDK 11.0.33, G1 as shipped |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-21 ≈ 08:00–09:00 America/New_York, repository HEAD `08f0194a3` |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (fresh session, Claude Opus 5.5): runs 2026-11-21 08:16–10:30 America/New_York on `pc75` (session cut off before the write-up); §3–§4 written 2026-11-23 by a second stage-2 session (Claude Opus 5.5) from the node's logs, nothing re-run; harness `harness/`, excerpts `logs/`, raw data `pc75:/mydata/s4/b23/` |
| Verdict | **true positive** (`verified-OOM · deployment`, bypass · enforcement failure) |

## Summary

- **Design intent:** a coordinator that is **not** a replica of the written partitions forwards CL=ONE writes of
  64,000 B to one live replica (which acks) while the other replica is down. Every write leaves one `HintRunnable`
  holding its whole `Mutation` on the coordinator's unbounded MutationStage queue. The single hint writer parks once
  the 3 × 32 MiB hint slabs are full and drains at the local disk's fsync'd speed, so the backlog grows at the
  difference between the client rate and the hint-disk rate. The only control that claims to cap it,
  `checkHintOverload` (128 × cores = 5,120 hint tasks), never fires because its per-destination term reads a fresh
  zero counter. Predicted endpoint at a 2 GiB heap: **Java heap OOM with ≈ 11–15 k queued hint tasks (≈ 2.2–2.9 × the
  5,120-task cap) and 0 refusals**. Matched control (all replicas up): no hints, no OOM. Intervention (the counter
  fixed with a `LoadingCache`): refusals start at 5,120 tasks and the backlog stays ≤ ≈ 0.7 GiB, no OOM.
- **Conclusion (stage 2):** **true positive** (`verified-OOM · deployment`). At shipped defaults and a 2 GiB
  coordinator heap, CL=ONE 64,000 B writes through a non-replica coordinator with one replica down end in a Java heap
  OOM 3/3 (thrown 16–18 s into the load) with `TotalHintsInProgress` at 15,304–15,439 (3.0 × the 5,120-task limit) and
  **0 refusals**; the dumps hold 15.6 k queued hint tasks (`StorageProxy$7`) whose 64 KB arrays are 94 % of the heap.
  All replicas up: 0/3 OOM. The same check with a working counter (`LoadingCache`): refusals start at K = 5,121,
  old gen after GC ≤ 730 MiB, 0/3 OOM. The OOM also happens at 4 GiB (3/3), 8 GiB (3/3) and at 15,872 MiB, the heap
  `cassandra-env.sh` picks on this node (3/3, K ≈ 128–131 k): largest failing budget = the largest tested. Condition X
  (1 MiB values): even the fixed check OOMs 3/3 at K ≈ 1,800 < 5,120, because the limit counts tasks, not bytes (a
  configuration-sizing finding). Topology stand-in: 3 instances on one host, single tokens placing every write off the
  coordinator.
- **Root cause (confirmed by the intervention):** `hintsInProgress` is a bare Guava `CacheLoader`, not a `LoadingCache`
  (`StorageProxy.java:202-208`); `getHintsInProgressFor` calls `load()` directly (`:2768`), so every increment,
  decrement and read lands on a new `AtomicInteger(0)` and the `&&` in `checkHintOverload` (`:1592-1593`)
  short-circuits to false. Hint tasks are charged to no byte counter once the client's ack has gone, and they queue on
  the unbounded MutationStage while the single hint writer is parked at the 3 × 32 MiB slab cap. Even when fixed, the
  limit counts tasks (128 × cores), not bytes, so it cannot protect a 2 GiB heap at 1 MiB writes (condition X).

## 1. Candidate

### 1.1 The candidate row (quoted from `phase1-oom-candidates.md`, Status as of 2026-11-21)

> | OC-147 | 2026-11-17 | `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous` | guided | Holder: HintRunnables queued on the unbounded MutationStage, each holding its Mutation. [details](runs/wave1.md#oc-147) | CP-6, CP-2, CP-5 | picked: B23 (2026-11-21) |

Details (`runs/wave1.md#oc-147`, quoted):

> Holder: HintRunnables queued on the unbounded MutationStage, each holding its Mutation. Why nothing stops it:
> hintsInProgress is a bare Guava CacheLoader, not a LoadingCache. load() returns a new AtomicInteger(0) on every call
> (StorageProxy.java:203-209, :2766-2768), so the per-destination term in checkHintOverload is always 0 and the &&
> short-circuits: the overload exception can never be thrown (:1592-1593). Even if fixed, the limit counts tasks, not
> bytes: 128 × cores (:202) × up to 16 MiB per mutation. Rough size at defaults: stage 4 saw 0 refusals at limits 1,
> 128 and MAX, with 1.15 GB of hints written. A fixed counter at 16 cores would still allow 2,048 × 16 MiB ≈ 32 GiB.
>
> **Where:** src/java/org/apache/cassandra/service/StorageProxy.java:1592-1593 (:202-209, :2766-2768, :2822-2827)

Triage 2026-11-18 (`runs/triage-2026-11-18.md`, rank 15, quoted):

> | 15 | OC-147 | yes | two-node | hintsInProgress is a bare CacheLoader that returns a fresh AtomicInteger(0) on every
> call, so checkHintOverload can never throw, and even a working limit would count 128 x cores tasks, not bytes. The
> timeout and failure paths skip the check altogether. With one replica down and 1-16 MiB mutations at CL=ONE,
> HintRunnables each holding a whole Mutation pile up on MutationStage once the hint writer parks at the 3 x 32 MiB
> slab cap. Stage 4 saw 0 refusals with 1.15 GB of hints written; 2 GiB of queued hints is about 2,000 x 1 MiB. |
> Overlaps S2 (MutationStage backlog) and S1 (hint slabs). Duplicates the legacy OC-19 (open) and OC-65, OC-77, OC-133,
> OC-135, OC-145, OC-148, OC-220, OC-235, OC-327, OC-332, OC-333. |

Triage 2026-11-20 (`runs/triage-2026-11-20.md`) attaches three more rows: "OC-493, OC-510, OC-523 go with OC-147 (hint
tasks on MutationStage past the count brake, rank 15). OC-510 and OC-523 add that the timeout/failure hint path skips
checkHintOverload."

### 1.2 Duplicates named by the triage (rows quoted from `phase1-oom-candidates.md`) and what this design covers

| Row | Quoted text (summary cell) | Covered by B23? |
|---|---|---|
| OC-19 (legacy, `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided`) | "[L11; lead list, back-link, E2, new] The hint backpressure added by JIRA 10972 (and 10971's for the compressed commit log) parks the writer in `take()` inside the synchronized `switchCurrentBuffer()` at the buffer cap, so hint writers on MutationStage hold the monitor and write permits while queued hint tasks and local writes keep whole mutations on heap, bounded only by a hint count (128 × cores), not bytes." | **Yes for the hint tasks** (the parked writer and the queued hint tasks are the mechanism here). Not for "local writes": the coordinator here is not a replica, so it has none (that part is S2/R22). |
| OC-65 (`MAX_HINT_BUFFERS-…--guided`) | "At the buffer cap, the hint writer parks in reserveBuffers.take() while it holds the HintsBufferPool monitor, so every other MutationStage thread that writes a hint blocks on the monitor (stage 4: 1 parked and 31 blocked)." | **Yes, as a reading** (one thread dump in the calibration run, §2.5); it is the stall that makes the queue grow, not a separate claim. |
| OC-77 (`MAX_HINT_BUFFERS-…--guided`) | "Holder: whole mutations on the heap inside hint tasks queued on MutationStage, plus local writes queued behind them." | **Yes for the hint tasks**; local writes not (as OC-19). |
| OC-133 (`maxHintsInProgress-…--autonomous`) | "Holder: HintRunnables on MutationStage, each holding its Mutation until HintsService.write runs." | **Yes** (the same holder). |
| OC-135 (`max_mutation_size-allocateBytes-slabCapacity--autonomous`) | "Holder: hint Mutations waiting upstream of the slab pool, as HintRunnables on MutationStage." | **Yes.** |
| OC-145 (`max_mutation_size-allocateBytes-slabCapacity--autonomous`) | "Holder: the MutationStage queue: local writes, replica mutations and HintRunnables, each holding a Mutation." | **Yes for the HintRunnables** only; local writes and replica mutations are not on the victim's queue here. |
| OC-148 (`maxHintsInProgress-…--autonomous`) | "Holder: hints created off the write-entry path, each a Mutation queued on MutationStage." | **No.** Hints from timeouts, failures, expired local writes (self) and Paxos are not driven: the live replica is kept fast so writes do not time out. Any such hints that appear are counted (§2.5) but not claimed. Self-hints are S2/R22's path. |
| OC-220 (`hints-HintsBuffer-put-slabCapacity--autonomous`) | "Heap backlog in front of the capped slab pool. Each hint is a HintRunnable on the unbounded MUTATION stage queue, and it pins its whole Mutation until HintsBufferPool.write returns." | **Yes.** |
| OC-235 (`hints-HintsBuffer-put-slabCapacity--autonomous`) | "Holder: the MUTATION stage threads and their queue. Hint writes run as tasks on Stage.MUTATION (StorageProxy.java:2827)." | **Yes.** |
| OC-327 (`hints_write_buffer_size-append-hint_remaining--autonomous`) | "Hint tasks queued on the MutationStage can pile up without a limit. The in-flight hint check (checkHintOverload, max 128 x cores) runs only on the coordinator send paths (StorageProxy.java:796, :1505)." | **Yes** for the pile-up on the send path (`:1505`); the "only on send paths" part is OC-148's (not covered). |
| OC-332 (`write_buffer_size-append-hint--autonomous`) | "Hint tasks queued on the MutationStage can pile up without a limit. Hints created on write timeout or failure (AbstractWriteResponseHandler.onFailure) and on local mutation expiry call submitHint without checkHintOverload, which is only called at StorageProxy.java:796 and :1505." | **Pile-up: yes. Timeout/failure/expiry path: no** (as OC-148). |
| OC-333 (`hints_write_buffer_size-append-hint_remaining--autonomous`) | "Holder: hint tasks queued on the MUTATION stage (StorageProxy.submitHint), each keeping its whole Mutation on heap until HintsService.write copies it into a slab." | **Yes.** |
| OC-493 (11-20 attachment, `hints_buffer_size-allocateBytes-prev--autonomous`) | "Hints waiting behind a full buffer pool are limited by count, not bytes. HintsBufferPool blocks the writing thread in reserveBuffers.take() once 3 slabs (3 x 32 MiB) are full and not yet flushed." | **Yes**; "count, not bytes" also by optional condition X (§2.8). |
| OC-510, OC-523 (11-20 attachments, `max_hints_size_per_host-shouldHint-maxHintsSize--autonomous`) | OC-510: "Holder: HintRunnable tasks queued on the MUTATION stage, each holding its Mutation on the heap until it is serialized into a hint buffer." OC-523: "Holder: HintRunnable tasks queued on the MUTATION stage. Each task captures a full Mutation until the hint is written." | **Holder: yes.** Their added timeout/failure point: no (as OC-148). |

So B23 covers the shared holder of OC-19, 65, 77, 133, 135, 145, 220, 235, 327, 333, 493, 510, 523 (the hint-task part),
and the "counts tasks, not bytes" point by condition X if time allows. It does **not** cover OC-148 and the
timeout/failure/expiry/Paxos hint paths that OC-332, OC-510 and OC-523 add; those need a design where the live replica
times out (a second case).

### 1.3 Phase-1 case and its stage-4 result

The phase-1 case (`maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous`, autonomous, 2026-10-21)
estimated **negative** for the capacity check: the per-destination counter is a bare `CacheLoader`, so
`checkHintOverload` never throws and `maxHintsInProgress` caps nothing. Constraint: `maxHintsInProgress`, a static field
(not a yaml key), default `128 × FBUtilities.getAvailableProcessors()` (5,120 on a 40-core host), settable only by JMX
`setMaxHintsInProgress` or indirectly by `-Dcassandra.available_processors`; unit: hint tasks, not bytes; intended
resource: heap ("avoid OOMing due to excess hints", `StorageProxy.java:1587`).

Stage 4 (closed 2026-10-21, `pc07`, two nodes on loopback, n2 down, coordinator n1 **is a replica**, 1,050,000 writes of
1 KiB at 400 stress threads, unit and cluster tiers): **Confirmed, does not cap.** Original build at L = 1 · 128 · MAX:
0 Unavailables, 0 refusals, peak `TotalHintsInProgress` 129 in all three (above L = 1 and 128), MutationStage pending ≤ 255,
1,150,800,378 B of hints on disk each, peak heap 1.76–2.0 GiB of a default heap with one Full GC each, no OOM. Patched
build (`hintsInProgress-LoadingCache.diff`) at L = 1: 833,479 writes refused with "Too many in flight hints", hint bytes
0.206 ×, pending 4. Finding (1) of its verdict: in-flight hints plateaued at **129 at any L, plausibly bounded by the
128 native request threads**, so the host default (5,120) was out of reach of that workload. The reason (this design's
reading): with the coordinator a replica, each client ack waits for its local write, which is queued behind its own hint
in the same FIFO, so the client is coupled to the hint path; and 1 KiB hints never filled the slabs. B23 removes both:
a non-replica coordinator (ack from the live remote replica) and 64,000 B values.

### 1.4 JIRA prior art (read only; nothing posted)

Queries: `jira-oom-survey.csv` rows mentioning hints; Apache JIRA REST (reachable 2026-11-21 ≈ 08:07 America/New_York),
`project=CASSANDRA AND (text ~ "hintsInProgress" OR text ~ "checkHintOverload" OR text ~ "Too many in flight hints")`
(10 hits).

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-10972 "File based hints don't implement backpressure and can OOM" | Fixed 3.0.4 / 3.4 | Added the slab cap whose `take()` parks the writer (the stall here). The fix bounds slabs, not the queued tasks in front of them. |
| CASSANDRA-3440 "local writes timing out cause attempt to hint to self" | Fixed 1.0.4 | Origin of the self-hint path (OC-148; not covered). |
| CASSANDRA-10825 "OverloadedException is untested" | **Open** (2015) | Says nothing tests that `OverloadedException` is ever thrown; consistent with a check that cannot fire. Does not name the `CacheLoader`. |
| CASSANDRA-14736 "checkHintOverload will fully reject a write or paxosCommit when only one of the recipients has a hint backlog" | **Open** (2018) | Design complaint about the check's scope; assumes it can fire. |
| CASSANDRA-9318 "Bound the number of in-flight requests at the coordinator" | Fixed 3.10 | The native in-flight byte limit, released at the client response (does not cover hint tasks after the ack). |
| CASSANDRA-9092 (Not A Problem), 8285 (Fixed 2.0.12), 3624 (Fixed 1.0.7) | — | Older hint-related OOMs (huge hint partitions, hint tasks on a shared executor, hint delivery); different holders. |

Verdict: **new** (no issue reports that `hintsInProgress` is a bare `CacheLoader` or that `checkHintOverload` cannot fire;
the nearest are 10825 and 14736, both open). Not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism (direction: **bypass — enforcement failure** of `maxHintsInProgress`)

Technique note: [`bypass-playbook.md`](../../../bypass-playbook.md), row "Failed reservation but admitted work" /
"Accounting mismatch": the check's per-destination operand is never charged, so admission never fails; compare the
suspect path (original build) with the protected path (the same check with a working counter).

1. **Entry.** `StorageProxy.sendToHintedReplicas` loops over `plan.contacts()` (live and down replicas) and calls
   `checkHintOverload(destination)` first for each (`StorageProxy.java:1503-1505`). For a down replica it marks the
   handler expired and, if `shouldHint` (`:2442-…`: hints enabled, not self, inside `max_hint_window` 3 h,
   `max_hints_size_per_host` 0 = unlimited), adds it to `endpointsToHint` (`:1550-1559`), then `submitHint(mutation, …)`
   (`:1563-1564`, `requestTime.shouldSendHints()` is true with `enforce_native_deadline_for_hints: false`,
   `Dispatcher.java:258-261`). The live remote replica gets the message (`:1572-1576`, `sendWriteWithCallback`); at CL=ONE its ack completes the
   client request, which releases the native request thread and the request's native in-flight bytes.
2. **Holder.** `submitHint` (`:2781-2820`) builds an anonymous `HintRunnable` capturing the `Mutation` and the response
   handler; `submitHint(HintRunnable)` (`:2822-2827`) increments `StorageMetrics.totalHintsInProgress` (K) and the
   per-destination counter, then `Stage.MUTATION.submit(runnable)`: the SEP queue has no count or byte bound
   (`SEPExecutor.java:68`, `addTask` `:119-123`, `getMaxTasksQueued` = `Integer.MAX_VALUE` `:103-106`). The task keeps the whole `Mutation` until `HintsService.write`
   (`HintsService.java:161-169`) has copied it into a slab and `HintRunnable.run`'s `finally` decrements the counters
   (`:2719-2732`). The bound value is a fresh heap `byte[]` (`CBUtil.readValue` → `readRawBytes`, as R22 confirmed), and
   `prepareSerializedBuffer` (`:1501`) caches a serialized copy for every mutation below `CACHEABLE_MUTATION_SIZE_LIMIT`
   1,000,000 B (`Mutation.java:423-463`): a queued 64,000 B write holds **≈ 2 × 64 KB ≈ 129 KB** of heap.
3. **Stall (drain rate D).** `HintsBufferPool.write` (`HintsBufferPool.java:59-66`, `allocate` `:68-84`) allocates in the current slab; on a
   full slab it calls the `synchronized switchCurrentBuffer` (`:107-127`), which, with `MAX_ALLOCATED_BUFFERS` = 3
   (`MAX_HINT_BUFFERS`, `CassandraRelevantProperties.java:351`) already allocated and no flushed slab returned, **parks
   in `reserveBuffers.take()` holding the monitor**; every other MutationStage thread with a hint blocks on the monitor
   (OC-65: 1 parked, 31 blocked). Slabs are 32 MiB direct (`max(2 × max_mutation_size, MIN)`, `HintsService.java:110`;
   `HintsBuffer.java:75-77`). They are emptied by the single `HintsWriteExecutor` thread (`HintsWriteExecutor.java:61`,
   `:83-85`), which writes them to the hints file and **fsyncs every `trickle_fsync_interval` = 10 MiB**
   (`HintsWriter.java:289-293`, regardless of `trickle_fsync: false`). So hint tasks leave the queue at D = the local
   disk's fsync'd write rate (`pc75`: one rotational volume behind a PERC H710P), while the client's rate λ is set by the
   live replica.
4. **The check that should stop it.** `checkHintOverload` (`:1585-1599`) throws `OverloadedException` only if
   `totalHintsInProgress > maxHintsInProgress` **and** `getHintsInProgressFor(dest).get() > 0 && shouldHint(dest)`. The
   per-destination counter is `CacheLoader<…, AtomicInteger> hintsInProgress` whose `load()` returns `new
   AtomicInteger(0)` (`:202-208`), and `getHintsInProgressFor` calls `hintsInProgress.load(destination)` (`:2764-2768`):
   every increment (`:2826`), decrement (`:2731`) and read hits a new zero counter, so the second operand is always
   false and the check **never fires**, while K itself is counted correctly. With a `LoadingCache` (stage-4 diff), the
   down replica's counter would be > 0 whenever its hints are queued, so writes would be refused once K > 5,120.
5. **Growth.** With λ·s > D, the queue grows at (λ − D/s) tasks/s and nothing charged sees it: the native in-flight
   limit released the bytes at the ack, `maxHintsInProgress` never fires, the slab cap bounds only the 96 MiB of slabs.
   At a 2 GiB heap the queue reaches the heap at ≈ 11–15 k tasks, 2.2–2.9 × the 5,120-task contract.

**Classification claim:** U (heap held by queued hint tasks) > C (contract: 5,120 tasks ≈ 630 MiB at 129 KB each) and
K (`TotalHintsInProgress`) > C with **0 refusals** → **bypass, enforcement failure** (protocol table row "U > C, K > C").
Interpretation: suspected implementation defect (bare `CacheLoader`). The "counts tasks, not bytes" point is a separate
configuration-sizing gap (condition X, optional).

**Why a non-replica coordinator, and why three instances (deviation from the brief's two).** With two instances and
RF=2 the coordinator is itself the acking replica: its local write is queued behind its own hint in the same FIFO
(`performLocally` → `maybeExecuteImmediately`, `SEPExecutor.java:218-224`, queues once the 32 permits are held by blocked
hint threads), so each client request waits for the hint path and the backlog is bounded by the client's in-flight
requests (≤ `native_transport_max_request_data_in_flight` = heap/10 = 205 MiB) unless writes time out — which turns it
into S2/R22's local-write backlog, not this holder. Stage 4 saw exactly that coupling (plateau at 129). A coordinator
that is not a replica of the partition is the ordinary case whenever N > RF and clients are not token-aware; three
instances (coordinator, live replica, down replica) is the smallest ring that has it. All three run on `pc75` on loopback.

### 2.2 Protection map (victim n1, the coordinator)

| Domain | Allocation / owner / release | Contract (counter, limit, unit) | Scope, multiplicity | At the limit | Covers B23's bytes? |
|---|---|---|---|---|---|
| D1 **Queued hint tasks** (claimed) | anonymous `HintRunnable` + `Mutation` (value `byte[]` + cached serialization), heap; created `StorageProxy.java:2786`, queued `:2827`, freed after `HintsService.write` | `checkHintOverload`: K = `TotalHintsInProgress` > `maxHintsInProgress` (5,120 tasks) **and** per-destination counter > 0 → `OverloadedException` at write entry | per coordinator, all destinations | **never fires** (per-destination operand is a fresh 0) | claims to; does not |
| D2 Hint slabs | `HintsBuffer` 32 MiB `allocateDirect`, `HintsBufferPool`; reused after flush | `MAX_ALLOCATED_BUFFERS` = 3 → 96 MiB direct | per process | writer parks in `take()` holding the monitor | bounded (in contract); the stall source |
| D3 MutationStage queue | SEP `ConcurrentLinkedQueue` (`SEPExecutor.java:68`) | none (32 work permits bound running tasks only) | per process | always adds | no |
| D4 Native in-flight request bytes | request frames/decoded messages until the response | `native_transport_max_request_data_in_flight` = heap/10 (204.8 MiB at 2 GiB), per IP heap/40 (51.2 MiB) | per process / per client IP | pauses reading | released at the ack; hint tasks outlive it |
| D5 Outbound messages to n2 | internode send queue (`Message` referencing the same `Mutation`) | 4 MiB per connection + 128 MiB endpoint + 512 MiB global reserve | per peer | overload/expire | bounded; not claimed (n2 is fast) |
| D6 Hints on disk | `hints/` files | `max_hints_size_per_host` 0 = unlimited | per host | — | disk, not memory (714 GiB free) |
| Baseline | schema, gossip, caches (empty), metrics | — | — | — | measured idle |

### 2.3 Configuration and budget audit

All capacity constraints at shipped 5.0.9 defaults (V6). Values resolved on `pc75` (40 cores, 125 GiB RAM):

| Setting | Default (source) | Resolved at the planned budget |
|---|---|---|
| `maxHintsInProgress` | `128 × getAvailableProcessors()` (`StorageProxy.java:201`), no `cassandra.available_processors` set | **5,120** (read it over JMX `MaxHintsInProgress` in every run) |
| `MAX_HINT_BUFFERS` | 3 (`CassandraRelevantProperties.java:351`) | 3 × 32 MiB = 96 MiB direct |
| `max_mutation_size` | `commitlog_segment_size`/2 = 16 MiB | slab 32 MiB (`HintsService.java:110`) |
| `concurrent_writes` | 32 (`cassandra.yaml:723`) | 32 MutationStage permits |
| `hinted_handoff_enabled`, `max_hint_window`, `max_hints_size_per_host`, `max_hints_file_size`, `hints_flush_period`, `hints_compression` | true, 3 h, 0 (unlimited), 128 MiB, 10 s, none | same |
| `trickle_fsync_interval` | 10240 KiB (`cassandra.yaml:956`) | hint writer fsyncs every 10 MiB |
| `enforce_native_deadline_for_hints` | false (`Config.java:1400`) | hints always sent |
| `write_request_timeout` | 2000 ms | same |
| `native_transport_max_threads` | 128 | same |
| `native_transport_max_request_data_in_flight` (/`_per_ip`) | heap/10 (heap/40) (`DatabaseDescriptor.java:649-656`) | 204.8 MiB (51.2 MiB) at 2 GiB |
| `CACHEABLE_MUTATION_SIZE_LIMIT` | 1,000,000 B | 64,000 B writes keep a cached serialization |
| G1, `G1HeapRegionSize` | shipped `jvm11-server.options:63,66` | 16 MiB regions (64 KB values are not humongous) |
| `HeapDumpOnOutOfMemoryError` | on (`jvm-server.options:120`) | `-XX:HeapDumpPath=/mydata/s4/B23/<run>/dump` (location only) |

**Budget (V7).** n1 heap **2 GiB** (`MAX_HEAP_SIZE=2G`, ≥ 512 MiB standing rule, the ideal value); direct limit as
`cassandra-env.sh` resolves it on `pc75` (record the value from the command line; HANDOFF: it sizes
`MaxDirectMemorySize` from RAM even with a hand-set heap); **no cgroup memory limit** (`systemd-run --user --scope -p
MemorySwapMax=0` only, to keep swap at 0). Node claimed: a 125 GiB, 40-core node, for which `cassandra-env.sh` resolves
min(½ RAM, 15,872 MiB) = **15,872 MiB**: the budget search (§2.9) climbs 2 → 4 → 8 → 15,872 MiB.

**Environment / supporting deviations (disclosed; none changes a capacity constraint of n1):**

- E1 **three instances on one host, loopback**: n1 `127.0.0.31` (victim coordinator), n2 `127.0.0.32` (live replica,
  seed), n3 `127.0.0.33` (replica stopped before the load); separate ports (`storage_port` 7000 per address; JMX
  7231/7232/7233; native 9042 per address), separate dirs under `/mydata/s4/B23/<run>/`.
- E2 **token placement**: `num_tokens: 1` with `initial_token` n2 = −2, n3 = −1, n1 = 0 and `SimpleStrategy` RF = 2 for
  `keyspace1`. Ranges: (0, −2] (all but two tokens) → {n2, n3}; (−2, −1] → {n3, n1}; (−1, 0] → {n1, n2}. So
  practically every write has replicas {n2, n3} and n1 coordinates without being a replica. Default snitch
  (`SimpleSnitch`), one DC. With vnodes the same path occurs for (N − RF)/N of writes at each coordinator; the placement
  only makes every write take it.
- E3 **n2 and n3 data and commit log on a tmpfs** (`/mydata/s4/B23/tmpfs`, `size=64g`), heap 8 GiB each: they are
  supporting peers, not the victim; HANDOFF lesson "several local nodes applying every write stall on a spinning disk:
  put data on a tmpfs". This keeps the live replica's ack path off the disk n1's hint writer uses. **n1's data, commit
  log and `hints_directory` stay on `/mydata` (the node's local disk), as a deployment would have them.** No disk fault is
  injected: the hint writer runs at the disk's normal speed (not a disk-exhaustion or injected-slowness experiment).
- E4 client: `cassandra-stress` from the build on `pc75` (same host; 40 cores shared). Recorded as environment.

### 2.4 Ceiling arithmetic (heap of n1, 2 GiB)

Per queued write: value `byte[]` 64,016 B + cached serialization ≈ 64,1xx B + `Mutation`/`PartitionUpdate`/row/cell/
`HintRunnable`/handler objects ≈ 1 KB → **m ≈ 129 KB** (the dump in K1 replaces this estimate; ±15 %).

- With the check working (the contract): D1 ≤ 5,120 × 129 KB ≈ **630 MiB** (+ ≤ 128 native threads of overshoot) + D4
  ≤ 205 MiB (shares the same mutations, not additive in practice) + baseline ≈ 200–300 MiB + D5 small ⇒ **≈ 0.9–1.1 GiB
  < 2 GiB**: a working check would protect a 2 GiB heap at 64,000 B. (At ≥ 1 MiB writes it would not: 5,120 MiB > 2 GiB,
  condition X.)
- Without it: D1 unbounded; OOM when D1 ≈ 2,048 − baseline − in-flight − G1 headroom ≈ 1.4–1.8 GiB ⇒ **K ≈ 11–15 k
  tasks** at failure.

### 2.5 Workload, instruments

**Cluster per run (fresh, all three wiped):** start n2 (seed), n3, n1 (n1 last, `auto_bootstrap` default; empty ring, no
streaming); wait for `UN` ×3; create the schema with a 1,000-op stress write (all up); `nodetool -p 7233 stopdaemon` on
n3 (or SIGTERM; record which), wait until n1's `nodetool status` shows n3 `DN` (≤ 30 s); hints dir of n1 empty.

**Load (all arms):**
`tools/bin/cassandra-stress write n=<N> cl=ONE -schema "replication(strategy=SimpleStrategy,factor=2)" -col "size=FIXED(64000)" "n=FIXED(1)" -rate threads=200 -errors ignore retries=0 -mode native cql3 protocolVersion=4 -node whitelist 127.0.0.31 -log interval=1 file=…`
(`cl=ONE` explicitly: stress's default `LOCAL_ONE` also works here but keep the frozen form; `retries=0` so refused
writes are not re-sent; protocol 4 per HANDOFF lesson; whitelist so every request goes to n1). N = 200,000 at 2 GiB
(12.8 GB offered); N = 400,000 for budgets ≥ 8 GiB. Stage 2 may raise `threads` (≤ 400) or add a second stress process
in K1 only (§2.7 gate), then freezes it for every arm.

**Instruments (synchronized timestamps, 1 s unless stated):**

| What | How | Measures |
|---|---|---|
| K | JMX n1 `org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress` (Count); `MaxHintsInProgress` attribute of `org.apache.cassandra.db:type=StorageProxy` once per run | the control's counter; the contract value |
| Refusals | JMX n1 `ClientRequest,scope=Write,name=Unavailables` delta (counts `OverloadedException`, stage-4 R5); stress error lines with "Too many in flight hints" | admissions refused |
| Queue | JMX n1 `ThreadPools,path=request,scope=MutationStage` `PendingTasks`, `ActiveTasks`, `CompletedTasks` | queued tasks (independent of K) |
| D (drain) | `du -sb` of n1's `hints/` every 1 s; `HintsService` created-hints meter if exposed | hint-disk bytes/s |
| λ | stress per-second ops; n2 JMX `ClientRequest`/`MutationStage CompletedTasks` | client rate, live replica's applies |
| Timeouts | n1 `ClientRequest,scope=Write,name=Timeouts`; n2 dropped mutations | off-entry hints (OC-148 path; not claimed) |
| U (heap) | n1 G1 Old Gen `Usage.used` and `CollectionUsage.used` over JMX (jstat cannot attach: stage-4 D1); GC log (shipped `-Xlog:gc…`); `RssAnon` from `/proc/<pid>/status` | physical heap, independent of K |
| U (attribution) | **heap dump on OOM** (shipped flag) → `harness/hprofhist.py` (from R22) extended to count instances of the `HintRunnable` subclass created in `submitHint(Mutation, …)` (identify its `StorageProxy$<n>` name with `javap -p` on the build), `Mutation`, and `byte[]` of 64,000–64,500 B with total bytes | U for D1 |
| Stall shape (K1 only) | one `jstack` of n1 when K ≥ 5,120: threads parked in `HintsBufferPool.switchCurrentBuffer` → `take()` and BLOCKED on its monitor | OC-65 reading |
| Histogram (K1 only) | one `jcmd <n1> GC.class_histogram` at K ≥ 8,000 (forces a full GC; calibration only) | m per task |
| tmpfs | `df` of the tmpfs every 5 s | safety stop |

Excluded: intrusive histograms or Byteman in counted arms.

### 2.6 Predicted response

| Arm | Build (n1) | n3 | Prediction (2 GiB, N = 200,000) |
|---|---|---|---|
| **T** test | original | down | λ·s ≥ 300 MB/s, D ≤ 200 MB/s; K passes 5,120 within ≈ 10 s of load with **0 refusals**; MutationStage pending tracks K; old gen after GC rises monotonically; **Java heap OOM** at K ≈ 11–15 k, within ≈ 30–120 s of load start (later if GC slows n1's intake). Dump: ≥ 10 k hint tasks holding ≥ 1.2 GiB of 64 KB `byte[]`. **3/3.** |
| **C** control | original | up (no fault) | No hints (K = 0); old gen after GC ≤ 0.6 GiB; all 200,000 writes complete; **no OOM 0/3**. |
| **I** intervention | `hintsInProgress-LoadingCache.diff` (stage-4 positive control) | down | Refusals start when K > 5,120 (Unavailables > 0, "Too many in flight hints"); K plateaus at ≤ ≈ 5,300 (5,120 + ≤ 128 native threads + the check's stage-4 overshoot); old gen after GC ≤ ≈ 1.1 GiB; completed writes ≈ D/s; **no OOM 0/3**. |

If T survives with K > 5,120 and 0 refusals but no OOM (plateau when GC throttles intake to D), that is a
**verified-gap (U > C, K > C)** → retry with a longer/larger load; service loss is recorded by the default criterion.

### 2.7 Stopping budget and validity gates

- **Per run:** stop at the first of: n1 OOM (`OutOfMemoryError` in `system.log`/stdout + dump written + process exit);
  stress done + 60 s watch of K/old gen; **600 s** from load start; tmpfs > 56 GiB; n2 down or n2 MutationStage timeouts
  > 1 % of writes (→ run **invalid**, not counted).
- **K1 calibration gate (before any counted run; one run, T configuration):** valid if λ·s ≥ 1.5 × D (measured) and K
  > 5,120. If not: **one** dated amendment allowed — `threads=400`, then a second identical stress process; re-run K1
  once. If K still stays ≤ 5,120 for 120 s at full load, stop the case as **retry** ("hint path keeps up on this
  node; needs a slower hint disk or a faster replica tier"), not a false positive.
- **Repetitions:** T, C, I ×3 each from clean starts; if T is mixed (1/3 or 2/3), add 2 runs (max 5).
- **Attempts:** at most 2 invalid runs per arm before the arm is declared blocked.

### 2.8 Controls, intervention and the optional condition X

- **V2 matched control C:** same build, budget, load, topology and timing; only the fault is removed (n3 running). It
  removes the suspect path's consumer (no hints) while keeping total client concurrency and payloads.
- **V4 intervention I:** the protected path — the same check with its per-destination counter working. Build: `cp -a
  /mydata/s4/cassandra-base /mydata/s4/B23/cassandra-fix`, apply the stage-4 diff
  (`capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/maxHintsInProgress-…/hintsInProgress-LoadingCache.diff`,
  save a copy in `harness/`), delete `build/classes/main/org/apache/cassandra/service/StorageProxy*.class`, `ant jar`;
  only n1 runs it (n2, n3 original). Record throughput and refusals so a refusal-only "fix" is visible.
- **Condition X (optional, "counts tasks, not bytes"):** values `size=FIXED(1048576)` (1 MiB, above
  `CACHEABLE_MUTATION_SIZE_LIMIT`, so ≈ 1 MiB per task, below the 8 MiB humongous threshold), N = 20,000:
  X-T (original) ×1 and X-I (fixed build) ×1–3. Prediction: **both OOM** at K ≈ 1,500–1,800 < 5,120, i.e. even a working
  check cannot protect a 2 GiB heap (5,120 MiB > 2 GiB). Reported as a configuration-sizing finding, not as part of
  V1–V4.

### 2.9 Budget search (V7, largest failing budget)

T at **4 GiB ×1, 8 GiB ×1, 15,872 MiB ×1** (N = 400,000 from 8 GiB), stepping up only while the previous budget failed;
a budget that survives N is the boundary (record K, old-gen peak). If 4 or 8 GiB fails, repeat it ×2 more only if time
allows (drop order). Predicted: OOM at 4 and 8 GiB (backlog ≈ 30 k and 60 k tasks needs ≈ 60–150 k excess writes, within
N); 15,872 MiB needs ≈ 120 k queued tasks — fails only if λ·s − D ≥ ≈ 200 MB/s for ≈ 60 s; otherwise boundary.

### 2.10 Time plan (America/New_York, 2026-11-21) and drop order

| Window | Step |
|---|---|
| 09:00–09:45 | read and hash-check; node check; harness (`harness/`: `run.sh` per arm, JMX poller, du/df sampler, `hprofhist.py` adapted, `summary.py`); tmpfs mount; fixed build; smoke (cluster up, schema, n3 down, 5,000 writes) |
| 09:45–10:05 | K1 calibration (gate §2.7; jstack and histogram) |
| 10:05–10:40 | T ×3 |
| 10:40–11:15 | C ×3 |
| 11:15–11:50 | I ×3 |
| 11:50–12:40 | budget search 4 → 8 → 15,872 MiB |
| 12:40–13:15 | condition X (optional); extra T if mixed |
| **13:15** | no run starts after this |
| 13:15–14:00 | §3–§4, write-back, cleanup (stop all JVMs started, unmount tmpfs, leave `/mydata/s4/B23/` logs) |

Each run ≈ 3 min setup + ≤ 10 min load + 1 min cleanup. **Drop order (first dropped first):** condition X → budget
15,872 MiB → budget 8 GiB → K1 histogram/jstack → budget 4 GiB. T ×3, C ×3, I ×3 are never dropped; if they cannot all
finish, the case is retry with the reason.

`sha256 of §1–§2 at freeze: 7bcbfda717fd73a30d7731bcfdf1ffc3849b467a93883ad8ac0e025c8ee64d74` (lines 30–341 of this file, from "## 1. Candidate" through the line before this one: `sed -n '30,341p' <file> | sha256sum`; 2026-11-21 08:13 America/New_York) · amendments after the freeze: none

## 3. Runs (stage 2)

**Sessions.** The runs were made by a fresh stage-2 OOM-agent session (Claude Opus 5.5) on 2026-11-21, 08:16–10:30
America/New_York, on `pc75`; that session was cut off before it wrote §3–§4 and had copied only the smoke, K1, T, C, I
and B4G excerpts and a `seq.log` that stopped at the B8G start. A second stage-2 session (Claude Opus 5.5) wrote §3–§4
on 2026-11-23 from the node's raw logs (`pc75:/mydata/s4/b23/`), copied the remaining excerpts and the full `seq.log`,
and ran nothing (no Cassandra, no stress). Times below are New York (`seq.log`, `driver.log`); the node's clock and
file times are MST (= New York − 2 h); Cassandra logs are UTC. Freeze hash re-checked on 2026-11-23 over "## 1.
Candidate" through the line before the hash line: `7bcbfda7…ee64d74`, **matches** (the Summary edit moved the line
numbers; the content is unchanged). No amendment to the design; deviations are listed below.

**Environment (as run).** `pc75` (node3.jason92-326665, 2 × Xeon E5-2660 v2, 40 cores, 125 GiB RAM, 8 GiB swap,
`/mydata` = one rotational volume `sda4` 765 GiB, Ubuntu 22.04, kernel 5.15.0, cgroup v2), OpenJDK 11.0.33, G1 as
shipped (`G1HeapRegionSize=16777216`, `ParallelGCThreads=40`). Builds: original `/mydata/s4/cassandra-base` (jar sha256
`570b5249…0176e`); fixed `/mydata/s4/b23/cassandra-fix` = a copy with `harness/hintsInProgress-LoadingCache.diff`
(identical to the stage-4 diff) and `ant jar` (`build-fix.log` ends `BUILD-DONE`; jar `b4b587dd…75edd3`), used only by
n1 in arms I and X-I. n1 command line in every run: `-Xms<budget> -Xmx<budget> -XX:MaxDirectMemorySize=15872M
-XX:+UseG1GC -XX:+HeapDumpOnOutOfMemoryError -XX:OnOutOfMemoryError=kill -9 %p` (shipped flags; `logs/*/n1-cmdline-excerpt.txt`);
`MaxHintsInProgress` read over JMX before every load: **5,120** (`driver.log`). No cgroup memory limit (`systemd-run
--user --scope -p MemorySwapMax=0`). n1 config diff (`logs/*/n1-conf.diff`): only `cluster_name`, `num_tokens: 1`,
`initial_token`, seeds, `listen_address`/`rpc_address`, the five directories (on `/mydata`), `JMX_PORT` and a GC-log line
(`-Xlog:gc*,gc+heap=debug,safepoint`). n2/n3: 8 GiB heap, original build, data on `/dev/shm/b23/<run>`.

**Harness** (`harness/`, identical to the node copy, sha256-checked): `run.sh` (one fresh 3-instance cluster per run:
start n2, n3, n1; `3 × UN`; schema by a 1,000-op stress write; `nodetool stopdaemon` of n3 except in C; wait for `DN`
at n1; pollers; load; stop rule; stop all; wipe data), `Poll.java` (1 s JMX of n1 and n2: old gen `Usage`/`CollectionUsage`,
GC counts, direct, MutationStage active/pending/completed, native-transport counts, `TotalHintsInProgress` K,
`TotalHints`, Write `Unavailables`/`Timeouts`/`Failures`/latency count, dropped mutations), 1 s `du -sb` of n1 `hints/`
and `RssAnon`, 5 s `df` of `/dev/shm`; `seq.sh`, `budget.sh`, `after-budget.sh` (the run order), `dumpproc.sh` +
`hprofhist.py` (holder counts, then the dump is deleted except T1's), `hprofstacks.py` (thread stacks in a dump),
`summary.py`, `excerpt.sh`, `build-fix.sh`.

**Deviations from the written design (environment / procedure; no constraint, budget, workload, arm or verdict rule
changed).**
1. Work directory `/mydata/s4/b23/` (lower case) instead of `/mydata/s4/B23/`.
2. n2/n3 data on the node's existing `/dev/shm` tmpfs (64 GiB) under `/dev/shm/b23/<run>/` instead of a separate
   `size=64g` mount; same purpose (E3). Peak use 41 GiB (C1) < the 56 GiB stop; emptied after every run.
3. `cassandra-stress` runs a **warm-up of min(N/4, 50,000) writes** before the N measured ones (its default; the frozen
   command does not disable it). So the offered load is 250,000 writes at N = 200,000 (450,000 at N = 400,000; 25,000 for
   X). In every 2 GiB T run n1 threw OOM inside the warm-up (≈ 41–43 k writes completed); the 200,000 measured writes
   then all failed in the client with `NoHostAvailableException` (n1 unresponsive). Readings are therefore taken from
   n1's JMX and logs, not from stress's summary.
4. "n1 OOM" in the stop rule is detected as n1 process death (the shipped `-XX:OnOutOfMemoryError=kill -9 %p`), plus the
   `OutOfMemoryError` grep after the run. In B4G the JVM did not kill itself before the run's watch window closed
   (below); the grep recorded the OOM and `budget.sh` stepped up on it.
5. Dumps were reduced with `hprofhist.py` and deleted after reading (`dumpproc.sh`); T1's dump is kept
   (`pc75:/mydata/s4/b23/T1/dump/cassandra-1795267755-pid150633.hprof`, 2.17 GB) and its stacks read with
   `hprofstacks.py`. The K1 class histogram (`jcmd GC.class_histogram`) and `jstack` were both taken at L+10 when K
   first read ≥ 5,120 in the driver's 1 s check (K = 8,534 then).
6. All optional work ran (none dropped): budget repeats ×2 at 4 GiB, 8 GiB and 15,872 MiB (§2.9 "if time allows"),
   condition X with X-T ×1 and X-I ×3. Everything finished by 10:30, well before the 13:15 limit.
7. The hint drain rate D is reported from the 1 s `du` of n1's `hints/` as two numbers: the peak 10 s rate and the
   average to the last growth of the directory (the average falls when GC starves the hint writer). The I arm, whose
   heap stays healthy, gives the disk's sustained rate: 126–132 MB/s.

**smoke (not a reading), 08:18–08:22.** T configuration, N = 5,000: 3 × UN, n3 `DN` at n1, `MaxHintsInProgress=5120`,
6,250 writes acked, 6,250 hints, K ≤ 1, 400 MB of hints on n1's disk, no OOM.

**K1 calibration, 08:22–08:27 (T configuration, 2 GiB, N = 200,000, 200 threads).** λ = 3,817 writes/s ≈ 244 MB/s;
D peak 156 MB/s → λ·s = **1.57 × D** (≥ 1.5 required); K > 5,120 at **L+10.4**. **Gate passed** without amendment
(200 threads, one stress process frozen for every arm). Readings at L+10 (K = 8,534): `jstack` shows **1 MutationStage
thread parked in `LinkedBlockingQueue.take` ← `HintsBufferPool.switchCurrentBuffer:118` holding the pool's monitor and
31 threads BLOCKED on it** (OC-65's reading; `logs/K1/jstack-K5120-excerpt.txt`); class histogram: 12,343
`StorageProxy$7` (the `HintRunnable` built in `submitHint(Mutation, …)`) and 1.60 GB of `byte[]` ≈ **130 KB per queued
task** (design m ≈ 129 KB; `hist-K8000-head.txt`). K1 then OOMed like T (thrown ≈ L+18, K max 15,274, n1 death L+90);
it is calibration, not counted in V1.

**Readings** (n1; times from load start L; "OOM thrown" = when the first `OutOfMemoryError` was raised, derived from
the dump's own wait-plus-write time and the `HeapDumper` safepoint in `gc.log`; "death" = the JVM's `kill -9` hook;
refusals = Write `Unavailables` (counts `OverloadedException`); old gen = max `Usage` / max `CollectionUsage` (after
GC); D = n1 hint-disk rate, peak 10 s / average; λ = completed client writes per second during load; n1 timeouts =
coordinator write timeouts; n2 drops = dropped `MUTATION_REQ` on the live replica. All runs valid: n2 never died,
n2 drops ≤ 108 (≤ 0.06 % of writes, gate 1 %), `/dev/shm` ≤ 41 GiB, every cluster `3 × UN` first time, n3 `DN` at n1
in every n3-down run (`nodetool stopdaemon`, no SIGTERM needed). Excerpts: `logs/<run>/` (`summary.txt`,
`driver.log`, `poll1-every5s.log`, `hints-rss-every5s.log`, `hprofhist.txt`, `oom-grep.txt`, `n1-oom-context.txt`,
`stress-tail.txt`, `n1-fullgc-count.txt`, …).

| Run | Arm / heap / value / N | Outcome | K max (at) | Refusals | Old gen max / after GC (MiB) | D peak / avg (MB/s) | λ (writes/s) | Notes |
|---|---|---|---|---|---|---|---|---|
| T1 | T / 2 GiB / 64,000 B / 200,000 | **heap OOM**, thrown ≈ L+18, death L+109 | 15,304 (L+14) | **0** | 1,962 / 1,962 | 152 / 15 | 3,749 | MutationStage pending max 15,230; n1 timeouts 0; 1,118 full GCs; dump kept |
| T2 | T / 2 GiB / 64,000 B / 200,000 | **heap OOM**, ≈ L+17, death L+97 | 15,439 (L+15) | **0** | 1,944 / 1,944 | 167 / 106 | 4,448 | pending max 15,319; timeouts 0; 998 full GCs |
| T3 | T / 2 GiB / 64,000 B / 200,000 | **heap OOM**, ≈ L+16, death L+51 | 15,353 (L+14) | **0** | 1,958 / 1,958 | 158 / 106 | 4,678 | pending max 15,272; timeouts 0; 382 full GCs |
| C1 | C (n3 up) / 2 GiB / 64,000 B / 200,000 | survived (stress done L+46, +60 s) | 0 | 0 | 1,436 / 353 | 4 / 2 | 6,667 | 250,000 writes acked, 0 errors; 1,156 hints (see below); 10 full GCs |
| C2 | C / 2 GiB | survived (L+46) | 0 | 0 | 1,273 / 269 | 0 / 0 | 6,669 | 250,000 acked, 0 errors, 0 hints; 6 full GCs |
| C3 | C / 2 GiB | survived (L+47) | 0 | 0 | 1,305 / 329 | 11 / 3 | 6,669 | 250,000 acked, 0 errors; 1,693 hints; 6 full GCs |
| I1 | I (fixed n1) / 2 GiB / 64,000 B / 200,000 | survived (stress done L+34, +60 s) | **5,121** (L+10) | **178,208** | 1,714 / 730 | 188 / 126 | — | 71,792 writes hinted and acked, refusals "Too many in flight hints"; pending max 5,089; 30 full GCs; 4.60 GB of hints written |
| I2 | I / 2 GiB | survived (L+34) | 5,121 (L+10) | 176,973 | 1,940 / 724 | 189 / 132 | — | 73,027 hinted; 28 full GCs |
| I3 | I / 2 GiB | survived (L+35) | 5,121 (L+10) | 176,366 | 1,891 / 723 | 192 / 130 | — | 73,634 hinted; 30 full GCs |
| B4G | T / **4 GiB** / 64,000 B / 200,000 | **heap OOM thrown ≈ L+33**, JVM not self-killed in the window: stopped by the harness (SIGTERM L+159, `kill -9` ≈ L+189) | 31,612 (L+23) | 0 | 3,967 / 3,967 | 192 / 15 | 4,002 | see "B4G" below; 1,603 full GCs; dump 4.33 GB complete |
| B4G-2 | T / 4 GiB | **heap OOM**, ≈ L+46, death L+62 | 31,559 (L+19) | 0 | 4,041 / 4,031 | 164 / 35 | 2,302 | n1 timeouts 190; n2 drops 16 |
| B4G-3 | T / 4 GiB | **heap OOM**, ≈ L+39, death L+120 | 31,817 (L+23) | 0 | 4,027 / 4,031 | 160 / 52 | 3,685 | timeouts 220; drops 6 |
| B8G | T / **8 GiB** / 64,000 B / 400,000 | **heap OOM**, ≈ L+127, death L+190 | 64,508 (L+63) | 0 | 8,029 / 8,044 | 191 / 21 | 2,030 | timeouts 874; drops 66 |
| B8G-2 | T / 8 GiB | **heap OOM**, ≈ L+146, death L+161 | 66,987 (L+96) | 0 | 8,056 / 8,057 | 197 / 25 | 1,346 | timeouts 2,585; drops 58 |
| B8G-3 | T / 8 GiB | **heap OOM**, ≈ L+125, death L+177 | 66,742 (L+46) | 0 | 7,944 / 7,944 | 185 / 30 | 2,984 | timeouts 357; drops 49 |
| B15872M | T / **15,872 MiB** / 64,000 B / 400,000 | **heap OOM**, ≈ L+285, death L+394 | 127,794 (L+101) | 0 | 15,718 / 15,730 | 188 / 17 | 2,309 | timeouts 2,753; drops 89; 2,084 full GCs |
| B15872M-2 | T / 15,872 MiB | **heap OOM**, ≈ L+359, death L+389 | 130,856 (L+103) | 0 | 15,612 / 15,614 | 163 / 12 | 3,572 | timeouts 991; drops 103 |
| B15872M-3 | T / 15,872 MiB | **heap OOM**, ≈ L+317, death L+416 | 127,660 (L+86) | 0 | 15,752 / 15,766 | 161 / 11 | 2,408 | timeouts 2,948; drops 108; first logged error `Native-Transport-Requests-32` |
| XT1 | X-T (original) / 2 GiB / **1 MiB** / 20,000 | **heap OOM**, ≈ L+19, death L+35 | **1,800** (L+17) | 0 | 1,897 / 1,897 | 177 / 105 | 312 (≈ 327 MB/s) | — |
| XI1 | X-I (fixed) / 2 GiB / 1 MiB / 20,000 | **heap OOM**, ≈ L+29, death L+34 | **1,797** (L+28) | **0** | 1,870 / 1,870 | 183 / 120 | 222 | K never reached 5,120, so the working check never fired |
| XI2 | X-I / 2 GiB | **heap OOM**, ≈ L+20, death L+34 | 1,807 (L+18) | 0 | 1,879 / 1,879 | 180 / 106 | 294 | — |
| XI3 | X-I / 2 GiB | **heap OOM**, ≈ L+20, death L+25 | 1,814 (L+17) | 0 | 1,887 / 1,887 | 173 / 101 | 266 | — |

In every T and budget run K passed 5,120 at L+10.4 and MutationStage pending tracked K (within 1–3 %). λ in the I arm
is not shown: refused writes return at once, so the client rate (≈ 9,850 completions/s) is not comparable; the useful
throughput there is the hinted-and-acked writes, ≈ 72–74 k in ≈ 34 s ≈ 2,100/s ≈ 135 MB/s ≈ D (the design's
"completed writes ≈ D/s").

**B4G: OOM without process death (the `alive=1` anomaly).** B4G is recorded `alive=1 why=stress done + 60 s`, but its
`oom-grep` shows `java.lang.OutOfMemoryError: Java heap space` (`stdout.txt:548`). Reconstruction
(`logs/B4G/oom-timeline.txt`, from the node's `gc.log`, `stdout.txt`, `driver.log`):
- The heap filled by L+20 (old gen 4,108 MB, K 31,021) and the first `OutOfMemoryError` was thrown at **≈ L+32–33**
  (09:14:27; `system.log` ends at 14:14:27.8 UTC with a GC `StatusLogger` dump; JMX polling and the client stalled the
  same second: K frozen at 31,612, `wr_done` at 69,879 from L+30 on).
- With `HeapDumpOnOutOfMemoryError` the throwing thread requests the dump as a VM operation, then the
  `OnOutOfMemoryError` command (`kill -9`) as a second one. Both need a safepoint from the VM thread, which was busy
  with back-to-back full GCs requested by other allocating threads (`Pause Full … 4054M->4054M(4096M)` every
  ≈ 0.2–0.25 s, 241–290 per minute; application threads stopped 157 s of the 157 s from the OOM to the kill). The
  `HeapDumper` operation got its safepoint only at **L+142** (07:16:17 MST) and wrote the 4.33 GB dump in 5.8 s
  (HotSpot reports "114.472 secs", wait included).
- The `kill -9` operation had not run by L+157, when the harness's "stress done + 60 s" window closed (stress gave up
  at L+97 with all measured writes failed). The harness read `alive=1` at L+159, sent SIGTERM (which the starved JVM
  did not finish within 30 s) and `kill -9` at ≈ L+189 (`gc.log` ends mid-full-GC at 07:17:04 MST). No
  "Executing /bin/sh -c kill -9" line appears in `stdout.txt`; T1 and B4G-2 show it.
- The other runs show the same mechanism at smaller scale: the dump waited 1–69 s for its safepoint and the hook ran
  5–109 s after the OOM (T1: thrown L+18, death L+109). B4G's dump wait (109 s) was the longest, so its hook missed the
  window. Not a harness kill hook and not a lost error: an OOM in the JVM whose self-kill was starved by full-GC thrash.

How it counts: **B4G is an OOM run** (heap `OutOfMemoryError` raised, a complete dump of the claimed holder written —
32,046 `StorageProxy$7`, 3,915 MiB of 64 KB arrays, 96 % of the heap — and the node in continuous stop-the-world GC with
no write completed for the ≈ 125 s until it was killed). It misses one clause of the stop rule's OOM definition
("process exit"), which the JVM would have met later; the exit was the harness's. It does not enter V1 (that is the
2 GiB T arm, 3/3 with self-exit); for the budget search 4 GiB is **3/3 OOM** (2/3 with the JVM's own exit). `budget.sh`
stepped up on its OOM line, as the frozen procedure requires.

**Hints in the control.** C1 and C3 created 1,156 and 1,693 hints with every replica up (C2: 0), with K ≤ 1 in every
1 s sample and 0 client timeouts. Their source was not traced (consistent with the response-expiry hint path of
OC-148, which this design does not claim); they are 0.5–0.7 % of the writes and drained at once (n1 hint disk ≤ 108 MB).

**Initiating failure and dumps (V5).** Every OOM is `java.lang.OutOfMemoryError: Java heap space` on n1, printed by
HotSpot with the dump line (`logs/<run>/n1-oom-context.txt`); n2 and n3 never OOMed. The `kill -9` hook usually ran
before Cassandra logged the error; in T1's kept dump the throwing thread is a native-transport request worker:
`OutOfMemoryError.<init>` ← `StorageProxy.updateCoordinatorWriteLatencyTableMetric(StorageProxy.java:1269)` ←
`StorageProxy.mutate:955` ← `ModificationStatement.execute` (`logs/T1/hprofstacks.txt`), i.e. an ordinary write-path
allocation that found the heap full; B15872M-3's `system.log` names `Native-Transport-Requests-32` the same way. The
same dump shows the stall: 31 MutationStage threads in `HintsBufferPool.switchCurrentBuffer:109` (BLOCKED on the
monitor) and one in `take()` at `:118`. Dumps (`hprofhist.py`, shallow sizes; `logs/<run>/hprofhist.txt`):

| Dump | Shallow heap | `StorageProxy$7` (queued hint tasks) | `Mutation` | `byte[]` 64,000–64,500 B (value + cached serialization) | share of heap |
|---|---|---|---|---|---|
| K1 (2 GiB) | 2,024 MiB | 15,588 | 15,588 | 31,176 = 1,904 MiB | 94 % |
| T1 | 2,023 MiB | 15,572 | 15,573 | 31,146 = **1,902 MiB** | **94 %** |
| T2 | 2,025 MiB | 15,588 | 15,588 | 31,176 = 1,904 MiB | 94 % |
| T3 | 2,023 MiB | 15,568 | 15,571 | 31,144 = 1,902 MiB | 94 % |
| B4G (4 GiB) | 4,075 MiB | 32,046 | 32,046 | 64,096 = 3,915 MiB | 96 % |
| B4G-2 | 4,081 MiB | 32,520 | 32,049 | 64,104 = 3,915 MiB | 96 % |
| B4G-3 | 4,076 MiB | 32,525 | 32,040 | 64,100 = 3,915 MiB | 96 % |
| B8G (8 GiB) | 8,188 MiB | 66,834 | 65,058 | 130,126 = 7,947 MiB | 97 % |
| B8G-2 | 8,183 MiB | 67,820 | 65,051 | 130,103 = 7,946 MiB | 97 % |
| B8G-3 | 8,183 MiB | 67,084 | 65,060 | 130,124 = 7,947 MiB | 97 % |
| B15872M | 15,897 MiB | 131,308 | 126,941 | 253,888 = 15,506 MiB | 98 % |
| B15872M-2 | 15,881 MiB | 131,017 | 126,939 | 253,874 = 15,505 MiB | 98 % |
| B15872M-3 | 15,884 MiB | 131,155 | 126,961 | 253,934 = 15,509 MiB | 98 % |
| XT1 (1 MiB values) | 1,924 MiB | 1,825 | 1,825 | — (1 MiB values: all `byte[]` 1,843 MiB) | 96 % (`byte[]`) |
| XI1 / XI2 / XI3 (fixed build) | 1,909 / 1,915 / 1,915 MiB | 1,820 / 1,830 / 1,825 | same | `byte[]` 1,838 / 1,848 / 1,843 MiB | 96 % |

Each queued 64,000 B write holds two ≈ 64 KB arrays (the bound value and the cached serialized mutation), 125 KiB per
task, as the design modelled. In the budget runs there are 1.8–4.4 k more `StorageProxy$7` than `Mutation`s: second
hint tasks for the *live* replica on writes whose n2 response timed out while n1 thrashed (n1 write timeouts 190–2,948),
sharing the same `Mutation`; these off-entry hints (OC-148's path) are ≤ 3.4 % of the holder and appear only after the
heap is already full. At 2 GiB there are none (0 timeouts).

**Time line** (New York, 2026-11-21): fixed build 08:16–08:17; smoke 08:18–08:22; K1 08:22–08:27; T1–T3 08:27–08:41;
C1–C3 08:41–08:56; I1–I3 08:56–09:11; B4G 09:11–09:17; B8G 09:17–09:23; B15872M 09:23–09:33; B4G-2/-3 09:33–09:43;
B8G-2/-3 09:43–09:55; B15872M-2/-3 09:55–10:15; XT1, XI1–3 10:15–10:30 (`logs/seq.log`).

**Left on `pc75`** (checked 2026-11-23 09:28 MST): no Cassandra, stress or poller process; `/dev/shm` empty;
`/mydata/s4/b23/` 3.8 GB (per-run raw logs with n1 `gc.log`/`system.log`/`stdout.txt`, `cassandra-fix`, the T1 dump
2.17 GB, `excerpts/`); `/mydata/s4/cassandra-base` untouched. Nothing was deleted by the write-up session.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`**, direction **bypass · enforcement failure**
(U > C, K > C, 0 refusals). Endpoint: Java heap OOM on the coordinator.

| Condition | Status | n/N |
|---|---|---|
| 2 GiB n1 heap, direct 15,872M, all constraints at defaults, one replica down, 64,000 B CL=ONE writes through a non-replica coordinator (T) | `verified-OOM · deployment` | **3/3** OOM (and K1 1/1) |
| 4 GiB (budget search) | OOM | 3/3 (B4G without the JVM's own exit, see §3) |
| 8 GiB (budget search) | OOM | 3/3 |
| 15,872 MiB = the heap `cassandra-env.sh` resolves on this node with G1 (budget search) | OOM — **largest failing budget, the top of the search** | 3/3 |
| Condition X: 1 MiB values, 2 GiB, original (X-T) / fixed counter (X-I) | OOM in both: configuration-sizing finding, not part of V1–V4 | 1/1, 3/3 |

| Item | Evidence |
|---|---|
| V1 Repetition | T1–T3: heap OOM 3/3, thrown 16–18 s after load start, n1 dead at L+51–109, each from a fresh 3-instance cluster. |
| V2 Matched control | C1–C3 (same build, budget, topology, stress command; n3 left running): 0/3 OOM, all 250,000 writes acked with 0 errors, K = 0, old gen after GC 269–353 MiB. |
| V3 Measurement | U independently of K: JMX old gen reached the heap (1,944–1,962 MiB) and the dumps hold 15,568–15,588 `StorageProxy$7` with 1,902–1,904 MiB of 64 KB arrays (94 % of the heap) at 2 GiB, up to 131 k tasks / 15.5 GiB (98 %) at 15,872 MiB; K (`TotalHintsInProgress`) 15,304–15,439 agrees with the dump counts and with MutationStage pending; C = 5,120 tasks ≈ 630 MiB → U/C ≈ 3.0 at 2 GiB, ≈ 25 at 15,872 MiB. |
| V4 Intervention | I1–I3 (same load, n1 with the per-destination counter as a `LoadingCache`, nothing else changed): 0/3 OOM; refusals from K = 5,121 (176–178 k `OverloadedException` "Too many in flight hints", 71 % of the offered writes), K plateau 5,121, pending ≤ 5,089, old gen after GC ≤ 730 MiB, 28–30 full GCs (T: 382–1,118). Useful work recorded: 72–74 k writes hinted and acked in ≈ 34 s (≈ the hint disk's 126–132 MB/s), against ≈ 41–43 k acked before T died. |
| V5 Initiating failure | `java.lang.OutOfMemoryError: Java heap space` on n1 in every T run (`stdout.txt`), throwing thread in T1's dump a native-transport request worker in `StorageProxy.mutate` → `updateCoordinatorWriteLatencyTableMetric`; the dumps at failure show the claimed holder (table in §3) and the parked hint writer with 31 blocked MutationStage threads (T1 dump, K1 `jstack`). |
| V6 Default constraints | `maxHintsInProgress` 5,120 (= 128 × 40 cores, read over JMX each run), `MAX_HINT_BUFFERS` 3, `max_mutation_size` 16 MiB (32 MiB slabs), `concurrent_writes` 32, hints on with 3 h window and unlimited size per host, `trickle_fsync_interval` 10 MiB, `enforce_native_deadline_for_hints` false, `native_transport_max_threads` 128, native in-flight limits heap/10 and heap/40, timeouts default (n1 `conf.diff`: no capacity setting changed). Only arm I / X-I changes the build. |
| V7 Acceptable budget | 2 GiB heap (≥ 512 MiB standing rule; 2 GiB is the ideal), direct 15,872 MiB as `cassandra-env.sh` resolves it with a hand-set heap, no container limit. Upward search: OOM at 4 GiB, 8 GiB and 15,872 MiB (3/3 each); 15,872 MiB is this node's automatic G1 heap, so no larger default budget exists here. |

**Against the frozen predictions (§2.6, §2.7, §2.9).**
- **T:** predicted K past 5,120 within ≈ 10 s with 0 refusals (observed L+10.4, 0), pending tracks K (yes), OOM at K ≈
  11–15 k (observed 15.3–15.4 k, at the top edge: 125 KiB per task rather than 129 KB, so a few more fit), within ≈ 30–120 s
  (thrown earlier, at 16–18 s; the JVM died at 51–109 s), dump ≥ 10 k tasks holding ≥ 1.2 GiB of 64 KB arrays (15.6 k,
  1.86 GiB), 3/3 (yes). λ·s was 240–299 MB/s, a little under the predicted ≥ 300 MB/s, and D ≤ 200 MB/s held (peak
  152–197); the K1 gate (λ·s ≥ 1.5 × D) passed at 1.57.
- **C:** K = 0, all writes complete, no OOM 0/3: as predicted; old gen after GC 269–353 MiB ≤ 0.6 GiB. A few hints
  appeared in C1/C3 (§3), not "no hints" literally; they never queued (K ≤ 1).
- **I:** refusals from K > 5,120, K plateau ≤ ≈ 5,300 (5,121), old gen after GC ≤ ≈ 1.1 GiB (≤ 730 MiB), completed
  writes ≈ D/s, 0/3: all as predicted.
- **Budget search:** predicted OOM at 4 and 8 GiB (backlog ≈ 30 k / 60 k tasks): observed 31.6–31.8 k and 64.5–67.0 k,
  3/3 each. At 15,872 MiB the design allowed either outcome; observed OOM 3/3 at K ≈ 128–131 k (L+285–359), because
  GC slowed n1's intake but never down to the hint disk's rate.
- **Condition X:** predicted both arms OOM at K ≈ 1,500–1,800 < 5,120: observed XT1 1,800 and XI1–3 1,797–1,814
  (the top edge), 0 refusals in X-I.
- No §2.7 retry trigger fired (the gate passed; no invalid run; T was 3/3, not mixed, so no extra T runs).

**Reason.** With one replica down and the coordinator not a replica of the written partitions, each CL=ONE write is
acked by the live replica and leaves one `HintRunnable` (`StorageProxy$7`) holding its whole mutation (two ≈ 64 KB
arrays) on n1's MutationStage queue. The single hint writer parks at the 3 × 32 MiB slab cap (one thread in `take()`
holding the `HintsBufferPool` monitor, 31 blocked behind it) and drains at the local disk's fsync'd ≈ 130 MB/s, while
the client offers 240–300 MB/s; the queue grows by ≈ 1,000 tasks/s and nothing charged sees it: the native in-flight
bytes are released at the ack, and `checkHintOverload` never fires because its per-destination operand is read from a
new `AtomicInteger(0)` on every call. K, which is counted correctly, passes the 5,120-task limit at L+10 and reaches
3.0 × the limit when the 2 GiB heap is full of hint tasks (94 % of the dump), 3/3. With all replicas up there are no
hint tasks and n1 survives 3/3; with the counter fixed the same check refuses writes at 5,121 tasks and n1 survives 3/3
with ≤ 730 MiB live. Larger heaps only take longer: the default G1 heap for this node, 15,872 MiB, fills with 131 k
hint tasks in ≈ 5–6 min of load. Root cause: `StorageProxy.hintsInProgress` is a bare `CacheLoader` (not a
`LoadingCache`), so the per-destination hint counter is never charged and the `maxHintsInProgress` enforcement can
never refuse a write; the queued hint tasks are bounded by no other control.

**Condition X (configuration-sizing finding).** With 1 MiB values the fixed check would not help either: the heap
fills at ≈ 1,800 queued tasks (96 % `byte[]`), far below the 5,120-task limit, so XI1–3 OOM 3/3 with 0 refusals, as
does XT1. `maxHintsInProgress` = 128 × cores counts tasks, not bytes: on a 40-core node it admits up to 5,120 ×
`max_mutation_size` (16 MiB) of queued hints, and already 5,120 × 1 MiB = 5 GiB > a 2 GiB heap. This is the "counts
tasks, not bytes" point of OC-147/OC-493 confirmed at defaults; it is a sizing gap of the shipped default, separate
from the counter defect, and is not used for V1–V4.

**Limits of attribution and caveats.**
- **Topology (deployment label; owner to confirm).** Three instances on one host stand in for a cluster with N > RF and
  a non-token-aware client; `num_tokens: 1` with `initial_token` (E2) makes practically every write take the
  non-replica-coordinator path. With the default 16 vnodes and token-aware clients only a fraction of writes would,
  and the hint rate needed to outrun the disk would need a larger λ. These are topology choices recorded in the frozen
  design (no capacity constraint, timeout or timing aid is changed; the fault is an external process stop), so the
  status is filed as `deployment`, following S2 (`verified-OOM · deployment` on a single-token ring) and C10's three-instance stand-in.
  The owner may rule that E2 (and the tmpfs peers of E3, which keep the live replica fast) make it `diagnostic`; the
  verdict (true positive) would not change.
- **Coupling to the client.** The 63 + 19 + 5 native request threads in T1's dump waiting in
  `AbstractWriteResponseHandler.get` show requests still waiting for n2's ack at the end; the decoupling the design
  relies on (ack from the live remote replica) held until n1 itself was in GC thrash (0 timeouts before the OOM at
  2 GiB).
- **OOM timing and the stop rule.** The `kill -9` hook needs a safepoint and was delayed 5–109 s by full-GC thrash
  after every OOM; in B4G it had not run when the watch window closed (§3). This does not affect V1 (the 2 GiB T runs
  all exited on their own). For later cases a watch window that starts at the first `OutOfMemoryError` would avoid it.
- **Not covered.** The timeout/failure/expiry/Paxos hint paths (OC-148, and those parts of OC-332, OC-510, OC-523) were
  not driven; they showed up only as ≤ 3.4 % of the holder in the budget runs after the heap was full, and as 0.5–0.7 %
  hints in C. Local writes queued behind hint tasks (the "local writes" part of OC-19, OC-77, OC-145) are not on this
  coordinator.
- **Pattern.** Covered by CP-6 (nothing refuses before the JVM's own `OutOfMemoryError`: the check exists but cannot
  fire), CP-5 (accepting queue in front of a stalled consumer: the parked hint writer) and CP-2 (task count, not bytes:
  condition X). No new clue pattern is needed.
- **New holder:** none. Every dump is dominated by the claimed holder.
