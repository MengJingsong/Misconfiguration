# R22 (retry of R17 / U11) — RangeTombstoneList of a hot memtable partition: a forced 32-writer copy thrash stalls MutationStage, and 12 MiB local writes queued behind it exhaust the heap  <!-- file: cassandra/cases/range-tombstone-list--forced-thrash-queues-large-local-writes/range-tombstone-list--forced-thrash-queues-large-local-writes.md -->

| Field | Value |
|---|---|
| Case ID | `R22` (a new attempt at `R17`, itself a retry of `U11`; README "ID prefixes") |
| From | retry-list row `R17` (retry of `U11`; cluster `OC-206` primary, `OC-200`, `OC-201`, `OC-202`, `OC-368`) |
| Phase-1 case files | [`range_tombstone_list_growth_factor-addInternal-capacity--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-addInternal-capacity--autonomous.md), [`range_tombstone_list_growth_factor-grow-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-grow-newLength--autonomous.md), [`range_tombstone_list_growth_factor-growToFree-newLength--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-growToFree-newLength--autonomous.md), [`none-addall-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/none-addall-size--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, unchanged since R17's `581de552`), build `/mydata/s4/cassandra-base` on `pc72`, OpenJDK 11.0.33, G1 as shipped |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-21 ≈ 01:50–02:50 America/New_York, repository HEAD `26a8ebe4` |
| Stage 2 (verify) | fresh OOM-agent session on `pc72`, 2026-11-21 02:04–05:16 America/New_York (runs 02:08–05:13) |
| Verdict | **true positive** — `verified-OOM · deployment` (main condition, 15,872 MiB, defaults): Java heap OOM 3/3; C 0/3, I 0/3 |

## Summary

- **Design intent:** R17 showed the holder at 15,872 MiB (≈ 9–10 GiB of queued local writes behind a stalled
  MutationStage, 12,898 queued `Mutation`s, no OOM) and named three reasons it stopped short: the thrash was entered only
  by accident (never at ≤ 8 GiB), the blob client's 32-outstanding cap throttled arrivals once GC held each request
  past its 2 s timeout, and 450 s was too short. R22 enters the thrash on purpose (two bursts of 64 hot writes), then
  keeps the hot stream paced and closed-loop (≤ 40 outstanding, ≤ 16/s), and gives the remaining request threads to
  **12 MiB** blob writes (open loop 4/s, ≤ 84 outstanding from three loopback source addresses), W ≤ 900 s, at the heap
  `cassandra-env.sh` resolves on this node (**15,872 MiB**). Predicted endpoint: **Java heap OOM at ≈ 220–600 s of W**
  (central ≈ 300 s), before the default 8 GiB commit-log cap would flush the hot table.
- **Secondary (U11/R17 retry item 4):** GC service loss at 512 MiB with C and I that now run the full 150 s (the hot
  client is paced so C and I do not reach their memtable flush) and a D arm with histograms for D1.
- **Conclusion (stage 2):** **true positive**, `verified-OOM · deployment`. At the heap `cassandra-env.sh` resolves for a
  128 GiB node (15,872 MiB) and every constraint at its default, the forced thrash on one range-tombstone partition held
  all 32 MutationStage writers (2–4 hot applies/s), 12 MiB local writes queued behind it at ≈ 2.5 blobs/s, and the node
  died of **Java heap OOM in 3/3 runs at W+446, ≈ 530 and 580 s** with 885–891 queued-or-memtable 12 MiB blob arrays
  (≈ 14.2 GiB of 16 MiB humongous regions) in the dump. The same load over 1,000 partitions (C) or with one writer (I)
  ran 725 s with backlog ≤ 6 blobs and ≤ 0.52 GiB live, 0/3 each. The secondary S512 service-loss reading was not
  reproduced (the paced client never entered the thrash at 512 MiB); B8 (8 GiB) did not enter the thrash either.
- **Root cause:** nothing bounds the MutationStage SEP queue in bytes: a local write that times out at 2 s releases its
  request thread and native in-flight bytes but stays queued (and is re-submitted as a hint runnable when it expires,
  `checkHintOverload` exempting self), while a per-attempt `RangeTombstoneList` copy × 32 contending writers, charged to
  no counter, slows the stage to a few writes per second. Unprotected accumulation × unprotected accumulation; pattern
  CP-5 (with CP-4).

## 1. Candidate

### 1.1 The retry row (quoted from `phase2-retry-list.md`, Status as of 2026-11-21)

| Case | Verdict date | Why retry (what was shown, what was missing) | What a better design should change | Status |
|---|---|---|---|---|
| [R17](../range-tombstone-list--copy-thrash-stalls-local-write-backlog/range-tombstone-list--copy-thrash-stalls-local-write-backlog.md) (retry of U11) | 2026-11-20 | pc96, defaults. Design: U11's RangeTombstoneList copy thrash stalls MutationStage so a second 4 MiB blob stream piles up unbounded (expired local writes re-submitted as hints, `checkHintOverload` skips self). OOM 0/13. At 2/4/8 GiB the 48/s open-loop hot stream never entered the thrash (one writer handles a hot write in ≈ 12.5 ms) and the 8 GiB commit-log cap flushed the hot table at ≈ 150 s. At 15,872 MiB the stall formed (≈ 9 GiB of queued blobs, old gen 11.6–11.9 of 15.5 GiB, STW ≤ 0.875) but GC thrash held NTR threads (126/128) and the client's 32-outstanding cap skipped 2,460 of 5,400 blob sends, so growth stopped at ≈ 76 % of heap in the 450 s cap. S512 service loss 3/3 (STW 0.908–0.910) but C/I flushed after 5 s / 26–27 s | (1) Enter the thrash on purpose: start with U11's closed loop (64 hot writes in flight ≈ 15 s), then hold 32 in flight or open-loop just above the thrash rate (≈ 10/s at 15,872 MiB, 20–25/s at 8 GiB); (2) give request threads to memory: hot writes ≤ 32 of 128 NTR, ≈ 96 to blobs, from 2–3 loopback addresses (per-IP limit heap/40), ≈ 12 MiB values; (3) run W ≥ 900 s at 15,872 MiB; (4) for the 512 MiB service-loss reading let C and I run ≥ 60 s and add D-arm histograms | picked again: R22 (2026-11-21) |

### 1.2 Earlier cases and verdicts

| Case | Node, date | Verdict (detail) | What it established for this design |
|---|---|---|---|
| [`U11`](../range-tombstone-list--per-write-full-copy-x-writers/range-tombstone-list--per-write-full-copy-x-writers.md) | `pc96`, 2026-11-18 | **retry** (`candidate`) | The per-attempt full copy of the hot partition's `RangeTombstoneList` (≈ 50 B × n per attempt, uncounted) × 32 MutationStage writers: 219–302 MiB of in-flight copies at 2 GiB, 949 MiB at 8 GiB, GC thrash, ≈ 25 % write timeouts, but live heap 0.19–0.37 × H, no OOM 0/6. Thrash hot-write rate μ_h ≈ 41/s at n ≈ 300 k, ≈ 7.8/s at 1.19 M (∝ n^-1.2). Timed-out local writes are applied late, not dropped; MutationStage pending 6,434 at 8 GiB. `setconcurrency MutationStage 1` removes the thrash (8.2 × T's rate). |
| [`R17`](../range-tombstone-list--copy-thrash-stalls-local-write-backlog/range-tombstone-list--copy-thrash-stalls-local-write-backlog.md) | `pc96`, 2026-11-20 | **retry** (`candidate`) | Stacked U11's stall with a 4 MiB blob stream. At 2/4/8 GiB the open-loop 48/s hot stream never entered the thrash (one writer ≈ 12.5 ms per write at n = 640 k, μ_h = λ_h, 0 timeouts) and every run, C and I included, ended at ≈ 150 s with the 8 GiB commit-log cap flush (`COMMITLOG_DIRTY`). At **15,872 MiB** (n₀ = 1.23 M, ≈ 25 ms per single-writer write) the stall formed at once: active 31.8/32, μ_h 4.95/s, blob applies 1.40/s, pending 12,776, backlog 2,310 blobs ≈ 9.0 GiB; histogram 5 s after W: 12,898 `Mutation` / `PartitionUpdate` / `StorageProxy$4`, 2,466 `LocalMutationRunnable$1` (re-submitted expired writes), `[B` +10.3 GiB, RTL arrays +1.04 GiB; Old after full GC 11.6–11.9 of 15.5 GiB, STW60 0.875. Growth flattened (≈ 420 → ≈ 30 blobs/min) because **arrivals** fell: the blob client's 32-outstanding cap was full while each request was held far past 2 s (2,460 of 5,400 blob slots capped; NTR active up to 126/128), so per-minute blob sends fell from ≈ 520 to ≈ 60. Commit log at 450 s: 2.9 GiB. S512 (U11 workload, 512 MiB): STW60 0.908/0.908/0.910 in T; C and I flushed after 5 s and 26–27 s, so no 60 s window for V2/V4; D1 not measured at 512 MiB. |

### 1.3 Phase-1 cases and stage-4 evidence

The four phase-1 case files (header) were filed by stage 4 as **true negative** ("does not cap") for their capacity
checks (U11 §1.3): the memtable counter charges ≈ 504–510 B per tombstone at growth factor 1.5 on the `add()` branch
(live ≈ 272–363 B); growth allocates 20 B × capacity; single-writer cost ≈ 18–20 ns per slot. No stage-4 run had more than
one request in flight per partition, and none stacked a second holder.

### 1.4 JIRA prior art (re-checked read only, 2026-11-21 ≈ 02:00; nothing posted)

Survey file `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (605 rows; grep
`RangeTombstoneList|MutationStage|LocalMutationRunnable|durable_writes|humongous`):

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-21492 | Unresolved (*Triage Needed*) | per-write `RangeTombstoneList.copy()` as an O(N²) allocation cost; no OOM, no concurrency (the stall source) |
| CASSANDRA-11460 "memory leak" | Won't Fix | heap OOM with the MutationStage SEP queue holding 60+ GB under a write rate above node capacity (the backlog half, as generic overload) |
| CASSANDRA-13213 | Unresolved | node OOMs from pending mutations after compaction metrics hang (another stall source for the same backlog) |
| CASSANDRA-12689 | Fixed 3.0.10 | all MutationStage threads blocked on MV locks; pending mutations pile up (another stall source, fixed for MV only) |
| CASSANDRA-5039 | Won't Fix | "Make sure all instances of BlockingQueue have configurable and sane limits" — the executor-queue bound the project declined |
| CASSANDRA-3440, 4753, 6510 | Fixed (1.0.4, 1.2.1, 2.0.4) | 6510 "Don't drop local mutations without a hint": the 5.0.9 re-submission of an expired local write (§2.1) |

JIRA REST (anonymous GET `issues.apache.org/jira/rest/api/2/search`, reachable, 2026-11-21 ≈ 02:00):

| Query (JQL) | Hits | Relevant |
|---|---|---|
| `key=CASSANDRA-21492` | 1 | still *Triage Needed*, no fix version (updated 2026-10-04) |
| `project=CASSANDRA AND text ~ "RangeTombstoneList" AND created >= 2026-11-18` | 0 | nothing new since R17 |
| `project=CASSANDRA AND text ~ "MutationStage" AND text ~ "pending" AND created >= 2026-11-01` | 0 | nothing new |
| `key in (CASSANDRA-19958, CASSANDRA-13235, CASSANDRA-11460)` | 3 | 19958 "Local Hints are stepping on local mutations" *Needs Committer*; 13235 "All thread blocked and writes pending" *Open*; 11460 Won't Fix |

**Verdict: `new`** (unchanged from R17 §1.4). Each half is known separately — the copy cost `known-open` (21492), an
overloaded MutationStage queue reaching OOM closed Won't Fix (11460, 5039) or open (13213, 13235), the local re-submission
by design (6510) with an open follow-up (19958) — but no issue reports that one range-tombstone hot partition at shipped
defaults stalls every local write on the node until the heap is gone. Not known-fixed, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism (direction: **combo — unprotected accumulation (stall source) × unprotected accumulation (holder)**)

Technique note: [`combo-playbook.md`](../../../combo-playbook.md) (a bounded per-instance holder whose multiplicity
starves a shared executor, stacked with the executor's unbounded queue). The mechanism is R17's (§2.1 there), re-read
against the pinned source (unchanged since `581de552`); only the workload changes.

**Stall source (D1).** A write carrying a range tombstone runs `AtomicBTreePartition.Updater.addAll`
(`AtomicBTreePartition.java:146-186`); per optimistic attempt `BTreePartitionUpdater.merge` →
`existing.mutableCopy().add(update.clone(HeapCloner.instance))` (`BTreePartitionUpdater.java:120`) copies the partition's
four RTL arrays at size n and `growToFree` reallocates them at 1.5 n (`RangeTombstoneList.java:106-114, 664-739`). With ≥ 32
hot writes in the stage, 32 writers repeat the O(n) copy on lost CAS rounds; the counter charges only the size delta. At
n = 1.23 M (15,872 MiB) one writer needs ≈ 25 ms per write on `pc96` (single-writer capacity ≈ 40/s) but 32 contending
writers complete only μ_h ≈ 5/s (R17). The two states are **bistable**: an uncongested start at a rate below the
single-writer capacity stays uncongested (R17 T8), and a start with ≥ 32 hot writes in the stage at once stays
congested as long as λ_h > μ_h (R17 B15872, U11).

**Holder (D3).** On a one-node RF 1 keyspace at CL ONE, every local write — any table — goes through the same stage:
`StorageProxy.mutate` → `performLocally` (`StorageProxy.java:1674-1690`) wraps the apply in a `LocalMutationRunnable` and
calls `Stage.MUTATION.maybeExecuteImmediately`; with no free permit it joins the SEP queue, which has **no bound**. The
request thread waits in `responseHandler.get()` and at `write_request_timeout` (2 s) answers `WriteTimeout`, releasing the
thread and the request's native in-flight bytes; the runnable stays queued. When dequeued after its deadline,
`LocalMutationRunnable.run` (`StorageProxy.java:2634-2656`) records a self-drop and, because `shouldSendHints()` is true
(`enforce_native_deadline_for_hints: false`), re-submits the same apply as a `HintRunnable` at the tail (`submitHint`);
`checkHintOverload` never fires for self (`shouldHint(self)` false). Each queued write holds its decoded `Mutation`; the
bound blob value is a fresh `byte[]` from `CBUtil.readValue` → `readRawBytes` (`CBUtil.java:443-450`). Mutations above
`CACHEABLE_MUTATION_SIZE_LIMIT` (1,000,000 B) keep no cached serialization, so a queued 12 MiB write holds one 12 MiB
array — which G1 (`G1HeapRegionSize=16m`, shipped `jvm11-server.options:66`) allocates as a **humongous object in its own
16 MiB region**: each queued blob takes 16 MiB of heap regions (the 4 MiB tail is unusable by other objects in JDK 11).
Nothing counts these bytes.

**Rates (FIFO model, confirmed by R17 at 15,872 MiB: predicted blob applies 1.14/s, measured 1.40/s).** With hot arrivals
λ_h, blob arrivals r_b and the stage completing μ_h hot writes/s, blob applies are fast and interleaved in queue order, so
the stage applies ≈ μ_h r_b / λ_h blobs/s and the **blob backlog grows at r_b (1 − μ_h/λ_h)**. The applied blobs fill the
commit log; the queued ones fill the heap. Their ratio is **(λ_h − μ_h) : μ_h**, so λ_h must stay several times μ_h for the
heap to fill before the 8 GiB commit-log cap flushes the hot table (§2.4). Arrivals are bounded only by the 128 request
threads × the time each is held (≥ 2 s; R17: far longer under GC thrash).

**What R22 changes (from R17's measured failure modes, §1.2):**

1. **Thrash entry on purpose:** two unpaced bursts of 64 hot writes (at W + 0 s and W + 20 s), so ≥ 32 hot writes are in
   the stage at once, then a paced closed loop. Same client and bursts in every arm.
2. **Hot paced, not open loop:** ≤ 40 outstanding and ≤ 16 issues/s. 16/s is below the single-writer capacity (so the
   intervention arm, one writer, keeps up: §2.4) and ≥ 3 × the thrash μ_h (so the blob backlog grows ≥ 0.7 r_b and the
   commit log stays below its cap). This departs from the row's "≤ 32 in flight / ≈ 10/s" on purpose: at λ_h ≈ 10/s and
   μ_h ≈ 5/s only half the blobs would queue, and the applied half (≈ 12 GiB of applies per 12 GiB queued) would reach
   the 8 GiB commit-log cap before the heap fills (§2.4).
3. **Request threads to memory:** blob writes of **12 MiB** (12,582,912 B; below `max_mutation_size` 16 MiB and the 16 MiB
   frame), open loop **4/s** (48 MiB/s, R17's byte rate), ≤ **84** outstanding (28 per source address × 3), so the blob
   stream tolerates request holds up to 21 s before a slot is skipped (R17: 32 slots for 12/s tolerated 2.7 s). Hot 40 +
   blob 84 = 124 ≤ 128 request threads. The open-loop rate (not a closed loop of 96, as the row suggests) keeps the offered
   load identical in C and I, where requests complete in milliseconds; a closed loop of 96 × 12 MiB would offer GB/s there
   and fill the tmpfs in minutes.
4. **W ≤ 900 s** at 15,872 MiB; the run stops at OOM, at 900 s, or 60 s after a switch of the hot table's memtable.
5. **512 MiB service loss (secondary):** paced hot client so C and I run 150 s without their memtable flush; D arm.

Why the RTL copies are the cause and not just load: the same streams with the same tombstone count spread over 1,000
partitions are applied as they arrive (C), and bounding the copies' multiplicity to one writer lets the stage keep up (I).

### 2.2 Protection map

| Domain | Allocation and owner | Counter / limit | Scope and multiplicity | Lifetime | At the limit |
|---|---|---|---|---|---|
| D1 in-flight RTL copy (stall source) | `RangeTombstoneList.copy()` + `grow` on a MutationStage thread (`BTreePartitionUpdater.java:120`) | **none** (failed attempts charge 0) | ≤ 32 permits (`concurrent_writes`) on the hot partition | `mutableCopy()` → CAS | nothing |
| D2 retained hot-partition RTL | memtable `DeletionInfo` of `r22.rt` | memtable pool `memtable_heap_space` = heap/4, ≈ 508 B counted / ≈ 290 B live per tombstone | one memtable | until flush | cleaner flushes the **largest** memtable when used > reclaiming + ⅓ × pool (`MemtablePool.java:125-145`, `AbstractAllocatorMemtable.java:249-300`) |
| D3 local-write backlog (claimed OOM holder) | `LocalMutationRunnable` (`StorageProxy$4`) / re-submitted `HintRunnable` (`LocalMutationRunnable$1`) → `Mutation` → 12 MiB `byte[]` (humongous, one 16 MiB region) in the MutationStage SEP queue | **none**: queue unbounded; native in-flight bytes and the request thread released at the 2 s timeout; `checkHintOverload` exempts self | every write not yet applied; grows at r_b (1 − μ_h/λ_h) | until applied (second pass after expiry) | nothing |
| D4 blob memtable | memtable of `r22.blob` (12 MiB values > `MAX_CLONED_SIZE` 128 KiB, `HeapCloner` → `ByteBuffer.allocate`, one humongous region each) | the same pool | one live + one flushing | until flush | flushed as the largest memtable (K₀ keeps D2 below half the trigger, §2.4) |
| D5 requests in flight | native `Message` + decoded values (≤ 84 blob + ≤ 40 hot + bursts) | `native_transport_max_request_data_in_flight` heap/10 = 1,587 MiB, per IP heap/40 = 397 MiB (wire bytes); 128 request threads | node / per source address | until the response (success or timeout) | backpressure (stop reading); not reached by design at 15,872 MiB (28 × 12 MiB = 336 MiB per address; 1,008 MiB total) |
| D6 commit log | mmap segments (page cache / tmpfs, not heap) | `commitlog_total_space` = min(8 GiB, ¼ volume) = 8,192 MiB on the 63 GiB `/dev/shm` | node | until every table dirty in a segment is flushed | forces a flush of the tables dirty in the oldest segment → flushes `r22.rt`, n resets, **the stall ends** (protective event, §2.4) |
| D7 baseline | caches, schema, metrics, Netty | own caps | node | standing | — |

Budget: the Java heap (`-Xmx`). D1–D5 and D7 are heap; D6 is not (listed because its cap flushes D2).
`memtable_allocation_type: heap_buffers`; protocol 4 (large requests do not use v5 direct frame buffers, HANDOFF "Lessons").

### 2.3 Configuration and budget audit

- **Source / build:** Cassandra 5.0.9, `systems/cassandra/source/` unchanged since `581de552` (checked: `git log
  581de552..26a8ebe4 -- systems/cassandra/source` empty); built tree `pc72:/mydata/s4/cassandra-base`
  (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`). Stage 2 copies `bin conf lib build pylib tools` once to
  `/mydata/s4/r22/cassandra` and never runs `ant` there.
- **Node `pc72`** (checked read-only 2026-11-21 01:58 EST): `node2.jason92-326665`, x86_64, **40 logical CPUs** (2 ×
  Xeon E5-2660 v2 @ 2.2 GHz, 10 cores × 2 threads per socket; NUMA node0 = even CPUs, node1 = odd), **125 GiB RAM (124
  GiB available)**, 8 GiB swap (unused); `/mydata` on a **spinning** RAID volume (`sda` PERC H710P, `ROTA 1`, ext4 on LVM),
  714 GiB free; **`/dev/shm` tmpfs 63 GiB, empty**; no Java process running; load 0.00; ports 7710/7711/9742/7799 free;
  JDK 11.0.33; `/mydata/s4/` holds only `cassandra-base`. Node clock is MST (UTC−7); every time in this file is
  America/New_York (`TZ=America/New_York date`). Difference from R17's `pc96` (E5-2667 v2 @ 3.3 GHz, 32 CPUs, same
  generation, same disk type, same tmpfs size): ≈ 0.67 × the clock, so single-writer and thrash rates are expected
  ≈ 0.67–1.0 × R17's (§2.4 uses that range).
- **Capacity constraints, all at shipped defaults (V6):** `concurrent_writes: 32`; `range_tombstone_list_growth_factor`
  1.5; `initial_range_tombstone_list_allocation_size` 1; `memtable_heap_space` → heap/4 (3,968 MiB);
  `memtable_cleanup_threshold` → ⅓; `memtable_flush_writers` 2; `memtable_allocation_type: heap_buffers`;
  `max_mutation_size` → 16 MiB (`commitlog_segment_size: 32MiB`); `commitlog_total_space` → min(8,192 MiB, ¼ of 63 GiB) =
  **8,192 MiB**; `native_transport_max_threads` 128; `native_transport_max_request_data_in_flight` heap/10,
  `…_per_ip` heap/40; `native_transport_max_frame_size` 16 MiB; `write_request_timeout: 2000ms`; `native_transport_timeout`
  12 s; `cql_start_time: REQUEST`; `hinted_handoff_enabled: true`; `enforce_native_deadline_for_hints: false`;
  `max_hints_in_progress` 128 × processors (not applicable to self); `compaction_throughput` 64 MiB/s; guardrails default;
  caches default; `durable_writes` default (true) on both keyspaces. **Read back per run** from `system_views.settings`
  (as R17's `client.py settings`) and JMX `StorageProxy.MaxHintsInProgress`.
- **Budgets (V7):** main **15,872 MiB** heap — exactly what `cassandra-env.sh` resolves by itself on this 125 GiB node
  (min(½ RAM, 15,872 MiB)), so the claimed deployment is "a 128 GiB node at the stock heap"; ≥ 512 MiB, so V7 is met
  under the standing rule. Secondary **512 MiB** (S512, the standing minimum; U11/R17's service-loss condition).
  Optional boundary point **8 GiB** (B8). `MaxDirectMemorySize` as `cassandra-env.sh` resolves it (R17 on `pc96`: 15872M):
  record. **No container memory limit**; `systemd-run --user --scope -p MemorySwapMax=0` only keeps swap away.
- **JVM as shipped:** G1, `G1HeapRegionSize=16m` (992 regions at 15,872 MiB), `G1NewSizePercent=50`,
  `MaxTenuringThreshold=2`, `MaxGCPauseMillis=300`, IHOP 70, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`,
  `OnOutOfMemoryError="kill -9 %p"`; `ParallelGCThreads`/`ConcGCThreads` as resolved (record; R17: 32/32).
- **Deviations (environment / instrumentation only; none changes a capacity setting):**
  - E1 one node on loopback (`rpc_address` default `localhost`), keyspaces RF 1; ports storage **7710**, ssl 7711, native
    **9742**, JMX **7799** (if busy, the next free block, recorded); cluster `r22-<label>`.
  - E2 data, commit log, hints, saved caches, cdc on **`/dev/shm/r22/<label>/`** (tmpfs; deleted after each run) — the disk
    spins, and a disk stall would build the same backlog in C and I. The 63 GiB tmpfs keeps `commitlog_total_space` at its
    8 GiB value (same as R17). Logs, GC logs, histograms on `/mydata/s4/r22/<label>/`. Heap dumps
    (`CASSANDRA_HEAPDUMP_DIR`) on `/dev/shm/r22/dump-<label>/` (fast write; the first T dump is then moved to
    `/mydata/s4/r22/<label>/`, later ones deleted after the printed histogram is saved).
  - E3 CPU: node under `taskset -c 24-31` (8 logical CPUs, 4 on each NUMA node — the same CPU count and list as R17, so
    rates compare); hot client CPU 12, blob clients CPUs 13, 14, 15, poller CPU 16; analysis/dump moves on 0–3. Record
    the JVM's processor count.
  - E4 instrumentation: R17's GC log line (`-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=<run>/logs/gc.log:…`),
    `-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`. No Byteman, no patch.
  - E5 client source addresses: the three blob processes bind their sockets to **127.0.0.2, 127.0.0.3, 127.0.0.4**
    before connecting to 127.0.0.1:9742 (Python: a `socket.socket.connect` wrapper that calls `bind((src, 0))` first; the
    hot client and schema/fill use 127.0.0.1). Checked per run from `system_views.clients` (address column) and `ss -tn`.
    Purpose: the per-IP in-flight limit (heap/40) is a per-client-address protective control; one address would cap 84 ×
    12 MiB at 397 MiB, which is a property of the test client, not of a deployment with several application servers.
  - E6 the only runtime change: `nodetool -p <jmx> setconcurrency MutationStage 1` (two-argument form) in arm I.

### 2.4 Ceiling arithmetic (before any reading)

**Fill target (all arms at a heap H):** pool = H/4; trigger T_tr = ⅓ × H/4; **K₀ = 0.45 × T_tr** counted, so the blob
memtable, not the hot one, is the largest when the trigger fires. At 15,872 MiB: T_tr = 1,322.7 MiB (1,386.9 MB), K₀ =
624.1 MB, **n₀ ≈ 1.23 M** (508 B per tombstone; R17 B15872: 1.23 M, 624.9 MB).

**Rates at 15,872 MiB (T):** μ_h = 2.5–6/s (R17 4.95/s on `pc96`; `pc72`'s clock 0.67 ×). λ_h: paced ≤ 16/s, and ≤ 40
outstanding / hold (≥ 2 s) ≤ 20/s, so λ_h ≈ 12–16/s while holds stay ≤ 2.5 s, falling later. r_b = 4/s offered.

| Quantity | Formula | Low – central – high |
|---|---|---|
| μ_h/λ_h | — | 0.16 – 0.28 – 0.45 |
| blob applies (to memtable and commit log) | r_b μ_h/λ_h | 0.6 – 1.1 – 1.8 /s (7 – 13 – 22 MiB/s) |
| blob backlog growth | r_b (1 − μ_h/λ_h) | 2.2 – 2.9 – 3.4 /s (35 – 46 – 54 MiB/s of 16 MiB regions) |
| non-D3 live | D2 + baseline 0.4–0.5 GiB; D1 0.6–1.4 GiB (R17 1.04); D4 ≤ 60 blobs live + one flushing ≤ 1.9 GiB of regions (typically ≤ 1 GiB); hot backlog < 0.05 GiB | 1.5 – 2.4 – 3.8 GiB |
| D3 needed for OOM | 15.5 GiB − non-D3 | 11.7 – 13.1 – 14.0 GiB ≈ 750 – 840 – 900 queued blobs (≈ 8.8–10.5 GiB of `[B` at 12 MiB each) |
| time to OOM (constant rates) | D3 / growth | 220 – 290 – 410 s |
| commit log at that time | 0.06 GiB fill + applies × t | 1.6 – 3.7 – 8.8 GiB |

Late-phase slowdown (R17: arrivals fell once STW > 0.8): with 84 slots the blob stream keeps 4/s until holds exceed 21 s
(R17's late holds, from 32 slots at ≈ 2 sends/s: ≈ 16 s), and μ_h falls with the GC share as fast as arrivals do, so the
ratio (1 − μ_h/λ_h) stays ≥ 0.7. Predicted time to OOM **220–600 s of W, central ≈ 300 s**.

Checks against protective events:

- **Commit-log cap (D6):** reached at 8 GiB of applied blob bytes ≈ 630 s at the central apply rate (≈ 370 s at the high
  rate). The design reaches OOM first unless μ_h/λ_h ≳ 0.45 together with a late OOM; that outcome is a valid
  `no OOM · protective flush` reading (stop rule §2.5) and is named in the verdict mapping. (R17's row asked to "mind" it:
  this is why λ_h is 16/s, not 10/s. At λ_h 10/s and μ_h 5/s the applied bytes equal the queued bytes, and 8 GiB of
  applies would come before 12 GiB of queue.)
- **Memtable trigger:** total memtables > T_tr when the blob memtable holds ≈ 1,323 − 595 = 727 MiB counted (≈ 60 blobs),
  then larger than D2 (595 MiB), so the blob memtable is flushed; D2 grows by μ_h × W ≤ 5,400 tombstones × 508 B ≤ 2.7 MB
  over 900 s, never the largest.
- **Native limits:** per address ≤ 28 × 12 MiB = 336 MiB < 397 MiB (heap/40); total 1,008 MiB + hot < 1,587 MiB (heap/10).
  Not reached. (At 8 GiB the per-address limit is 205 MiB ≈ 17 blobs: in B8 it binds, recorded.)
- **Request threads:** 40 + 84 = 124 ≤ 128; the bursts (64) come when blob holds are short (≤ 2 s × 4/s = 8 slots).
- **I arm (one writer):** single-writer cost at n₀ ≈ 25 ms (`pc96`) – 37 ms (`pc72` at 0.67 ×) → capacity 27–40/s;
  hot 16/s × 25–37 ms = 0.40–0.59, blobs 4/s × ≈ 10–15 ms (12 MiB clone + commit-log write on tmpfs) ≈ 0.05; utilization
  0.45–0.65, so no queue after the bursts. A burst of 64 on one writer drains in 1.6–2.4 s: ≤ ≈ 10 burst timeouts
  (recorded, not an endpoint). I applies blobs at 48 MiB/s, so **I's commit log reaches the 8 GiB cap at ≈ 170 s and
  flushes `r22.rt`** (as every R17 I8 run did at ≈ 150 s); from then on I has no hot partition. V4 is therefore read both
  over the whole W (no OOM) and **at matched W times before I's first `r22.rt` switch** (backlog ≈ 0 in I vs ≥ 300 blobs
  in T at ≈ 150 s).
- **C arm:** n ≈ 2,150 per partition (K₀ at ≈ 291 B per tombstone ≈ 2.15 M tombstones over 1,000 partitions; R17 C8:
  291 B); D1 per attempt ≈ 107 KB; stage keeps up; blobs applied at 48 MiB/s; commit-log cap flushes from ≈ 170 s
  (harmless in C, recorded).

So the OOM is reachable at defaults only through D3, and only while D1's multiplicity keeps μ_h ≪ λ_h. Without the stall
(C, I) the sum of contract capacities plus baseline stays ≤ ≈ 0.25 × H (pool 4 GiB counted at most ⅓ used + one
flushing + in-flight ≤ 1 GiB + baseline).

**S512 (secondary), 512 MiB:** pool 128 MiB, T_tr = 42.67 MiB (44.7 MB); F to **0.75 × T_tr** = 33.5 MB (R17/U11:
67 k tombstones, 506 B each). W: hot only, paced ≤ 110/s (T's R17 rate was 94/s): over 150 s ≤ 16.5 k more tombstones —
T and I ≤ 8.4 MB (→ ≤ 42.3 MB < 44.7 MB), C ≤ 4.8 MB (291–502 B each) — so **no arm reaches the memtable trigger** in its
150 s (R17's C/I reached it in 5 s / 26 s at 6,300/s and 1,000/s unpaced).

### 2.5 Workload and environment

- **Node:** `pc72` (from the local node with `ssh pc72`). Run directory `/mydata/s4/r22/<label>/` (`conf/` copy with
  E1–E4, `logs/`, `hist/`) and `/dev/shm/r22/<label>/` (`data/`, `commitlog/`, `hints/`, `saved_caches/`, `cdc_raw/`), plus
  `/dev/shm/r22/dump-<label>/`, all fresh per run. Launch as R17's `harness/run.sh` (the model; R17's run directory was
  deleted, its harness is in its case folder): `( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c
  24-31 env CASSANDRA_CONF=… CASSANDRA_LOG_DIR=… MAX_HEAP_SIZE=<H> CASSANDRA_HEAPDUMP_DIR=… JVM_EXTRA_OPTS=…
  <cassandra>/bin/cassandra -f < /dev/null > <run>/logs/stdout.txt 2>&1 & )`; bounded wait for the native port (≤ 180 s);
  PID from the process list. **Before each run:** `ps -eo pid,cmd | grep '[C]assandraDaemon'` (leave other sessions'
  nodes alone), `free -m` (≥ H + 50 GiB available), `df -m /dev/shm` (≥ 50 GiB free), ports free. **After each run:** kill
  node and clients by PID, copy readings, `rm -rf /dev/shm/r22/<label>` (and the dump directory once handled).
- **Client:** Python 3 with the bundled driver (`lib/cassandra-driver-internal-only-*.zip`, as R17's `client.py`),
  **protocol 4**, `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `FallthroughRetryPolicy`, CL ONE,
  `token_metadata_enabled=False`, client request timeout **60 s** (R17: 30 s; a client-side timeout would free a slot the
  server still holds). Processes in W: **one hot client** (127.0.0.1) and **three blob clients** (127.0.0.2/3/4, E5), each
  with its own `Cluster`. Every response (ok, `WriteTimeout`, error, client timeout) is counted **with its latency** (R17
  recorded latency only for ok responses).
- **Schema:** `CREATE KEYSPACE r22 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE r22.rt (pk int, ck int, v int, PRIMARY KEY (pk, ck))`; `CREATE TABLE r22.blob (k bigint PRIMARY KEY, v blob)`;
  all options default. Hot statement S = `DELETE FROM r22.rt WHERE pk = ? AND ck > ? AND ck < ?` bound to `(pk, 4i, 4i+2)`;
  blob statement B = `INSERT INTO r22.blob (k, v) VALUES (?, ?)` with a fresh k per write (k = address index × 10⁹ + seq)
  and one **12,582,912 B** random value generated once per process.
- **Phase F (fill):** T/I/D: unlogged single-partition `BatchStatement`s of 1,000 S to `pk = 0`, i ascending, one in
  flight (R17). **C: batches of 1,000 S to one partition, pk round-robin over 0..999, i ascending per partition, ≤ 8
  batches in flight** (R17's C at 8 GiB took 664 s with batches of 100; the target state — K₀, ≈ 2,150 tombstones per
  partition — is what is matched, not the fill speed). Read `MemtableOnHeapDataSize` of `r22.rt` every 10 batches; stop at
  **K₀ = 0.45 × memtable_cleanup_threshold × memtable_heap_space** (resolved values read at start); check
  `MemtableSwitchCount` = 0. Predicted F ≤ 4 min (T/I at 15,872 MiB; R17 125 s on the faster CPU), ≤ 3 min (C).
- **Quiesce Q:** 10 s idle, `jcmd <pid> GC.class_histogram` (L0), 20 s idle. Arm I: `setconcurrency MutationStage 1` here
  (read back with `getconcurrency`).
- **Phase W (main design, mode R):**
  - **hot client:** at W + 0 s and W + 20 s issue a **burst of 64** S at once (exempt from the caps); otherwise a closed loop
    with **≤ 40 outstanding** and **≤ 16 issues/s** (token bucket; an issue slot that finds 40 outstanding waits, it is not
    skipped). T/I/D: `pk = 0`, fresh ascending i above the fill range; C: `pk = i mod 1000`.
  - **blob clients (×3):** open loop, each **4/3 per s** (total 4/s, 48 MiB/s), **≤ 28 outstanding each** (an issue slot
    that finds 28 outstanding is skipped and counted `capped`). Start together with the hot client.
  - Timeouts and errors are counted, never retried.
  - **T/D stop:** first of node death (OOM), **900 s**, or **60 s after** a `MemtableSwitchCount` rise of `r22.rt`
    (the 60 s read the drain; the stall ended at the switch). Read the flush reason from `system.log`: `COMMITLOG_DIRTY` →
    valid `no OOM · protective flush`; `MEMTABLE_LIMIT` of `r22.rt` → `invalid-T` (K₀ wrong).
  - **C/I stop:** node death or **W_CI** (fixed before the first C run: W_CI = min(900, max(300, ⌈1.25 × the longest
    T time to OOM⌉)) s; W_CI = 600 s if no T run reached OOM). A switch of `r22.rt` in C or I is recorded and does not stop
    the run.
  - After W: 5 s, histogram L1 if the node lives, then kill.
  - **Thrash-entry check (all arms, recorded):** MutationStage active ≥ 30 and pending ≥ 100 at W + 40 s. A T run that
    fails it is `invalid-T (no entry)` (expected never at 15,872 MiB; R17 entered even open loop).
- **Arms (main heap 15,872 MiB):**
  - **T (test):** hot partition `pk = 0`, **×3**.
  - **C (matched control):** the same K₀, the same W streams, caps, bursts and pacing; hot statements spread over 1,000
    partitions (n ≈ 2,150 each). **×3**.
  - **I (intervention: bound D1's multiplicity):** as T plus `setconcurrency MutationStage 1` in Q. **×3**. (If the node
    refuses 1, use 2 and record it.)
  - **B8 (optional boundary point, T only, ×1):** 8 GiB, same client (per-address limit 205 MiB binds; recorded).
    Predicted: thrash μ_h ≈ 10–20/s at n₀ ≈ 640 k, so μ_h/λ_h ≥ 0.6, and the commit-log cap flush (≈ 250 s) comes before
    an OOM — `no OOM · protective flush` (or late OOM).
- **Secondary S512 (mode S, 512 MiB, hot client only, W = 150 s):** F to 0.75 × T_tr (batches of 100; T/I/D to `pk = 0`;
  C round-robin over `pk = 0..999`, as R17); W: one burst of 64 at W + 0 s, then closed loop ≤ 64 outstanding, ≤ 110 issues/s
  (all arms). T/D stop on an `r22.rt` switch; C/I record it and continue. Arms **S512-T, S512-C, S512-I ×3 each** and
  **S512-D ×1** (as T, plus `jcmd GC.class_histogram` every 30 s of W; intrusive, never counted for V1/V2).
- **Stopping budget:** ≤ 900 s of W per main run, 150 s per S512 run; ≤ 22 runs plus one shakedown; no heap above
  15,872 MiB; no change of any constraint after a failure; no run **starts after 06:45** EST 2026-11-21; every process
  stopped by **07:00**, case file written by **07:30**. A node whose JMX gives no sample for 180 s while its GC log is also
  silent is `jcmd Thread.print`-ed once and killed by PID (recorded as `hung`); a JMX gap during an active GC log is
  recorded and the run continues to its stop rule.

### 2.6 Instruments (U independent of K)

- **Poller** (R17's `Poll.java`, JMX every 1 s, unchanged MBean set): G1 Eden/Survivor/Old usage and Old collection
  usage; GC counts/times; for `r22.rt` and `r22.blob` `MemtableOnHeapDataSize`, `MemtableSwitchCount`, `WriteLatency`
  Count; `AllMemtablesOnHeapDataSize`; `MutationStage` and `Native-Transport-Requests` active/pending/completed;
  `TotalHintsInProgress`, `TotalHints`; `DroppedMessage MUTATION_REQ`; `ClientRequest Write Timeouts`;
  `CommitLog TotalCommitLogSize`. Plus `RssAnon` of the JVM every 1 s.
- **Clients:** per second and per process: issued, capped, ok, server timeouts, client timeouts, errors, outstanding,
  latency of every response (p50/p99/max); per-process source address.
- **U per domain:**
  - **D3 (claimed holder):** backlog_blob(t) = Σ blob issued − Σ capped − `r22.blob` WriteLatency Count (applied);
    U_D3 = backlog × 12 MiB (bytes) and × 16 MiB (regions). Physical check: the OOM-time histogram printed by Cassandra
    (`[B` bytes above L0; counts of `org.apache.cassandra.db.Mutation`, `PartitionUpdate`, `StorageProxy$4`,
    `StorageProxy$LocalMutationRunnable$1`), the GC log's humongous region count (`gc+heap=debug`, "Humongous regions:
    a->b") in the last minute, and the kept `.hprof` (R17's `hprofhist.py`, run niced after the sequence if time allows).
    K for D3: none; the nearest counter, native in-flight bytes, is read from the clients' outstanding × size (≤ 1,008 MiB).
  - **D1:** `ClusteringBound[]` + `long[]` + `int[]` above L0 in the OOM/L1 histograms and in S512-D's series.
  - **Live heap:** heap after each `Pause Full` and humongous regions from the GC log; Old collection usage.
- **On OOM (V5):** first `java.lang.OutOfMemoryError` line and its thread from `system.log`/`stdout.txt`, the printed
  histogram, the `.hprof` (first T dump kept), the last 60 s of the GC log, the poller's last 30 rows.
- **Derived per run:** μ_h, λ_h, blob issued/applied per s, backlog slope (MiB/s, per minute and least squares over W),
  time to OOM, commit-log size at the end, STW share per 60 s window (max = STW60), share of writes timed out per 60 s.

### 2.7 Predicted response, endpoints and verdict mapping

Predictions (before readings):

1. **F:** K₀ with `MemtableSwitchCount` 0; n₀ = 1.23 M ± 5 % (T/I), K/n ≈ 508 B; C ≈ 2.1–2.2 M tombstones over 1,000
   partitions, K/n ≈ 291 B. S512: 67 k ± 5 %.
2. **T ×3 (15,872 MiB):** entry check passed by W + 40 s (active 32, pending ≥ 100); μ_h 2.5–6/s; λ_h 12–16/s in the
   first 3 min; ≥ 90 % of hot and blob writes time out after the first minute; blob applies 0.6–1.8/s; blob issued ≥ 95 %
   of offered until the last minute; backlog slope 35–54 MiB/s (regions) over the first 3 min; Old after full GC rising
   past 12 GiB; NTR active ≤ 124; no `Overloaded` errors; **Java heap OOM in 3/3 at 220–600 s of W (central ≈ 300 s)**,
   with commit log < 8 GiB (central ≈ 3.7 GiB) and no `r22.rt` switch. OOM histogram: `[B` ≥ 8.5 GiB above L0, ≥ 700 queued
   blob `Mutation`s (plus the small hot ones), D1 arrays 0.5–1.4 GiB; humongous regions ≥ 700. Secondary: STW60 ≥ 0.90
   in the last 60–120 s before the OOM in ≥ 2/3.
3. **C ×3:** entry check fails (active mean < 2, pending < 50 after the bursts); hot applies 16/s, blob applies 4/s,
   p99 < 1 s, 0 timeouts after W + 30 s; backlog ≈ 0; Old after GC ≤ 3 GiB; commit-log flushes from ≈ 170 s; **no OOM**
   for W_CI.
4. **I ×3:** active 1; ≤ 10 hot timeouts from the bursts, then 0; hot 16/s, blob 4/s (useful work not reduced); pending
   ≤ 64 during bursts, ≤ 5 otherwise; backlog ≤ 5 blobs at every second before I's first `r22.rt` switch (predicted at
   ≈ 150–200 s, `COMMITLOG_DIRTY`); Old after GC ≤ 3 GiB; **no OOM** for W_CI.
5. **B8 (optional):** thrash entered; `COMMITLOG_DIRTY` flush of `r22.rt` before an OOM (≈ 200–300 s); no OOM.
6. **S512:** T STW60 ≥ 0.90 in ≥ 2/3 (R17 0.908–0.910; marginal), full GCs ≥ 400 per 150 s, live after full GC
   120–170 MiB, no `r22.rt` switch; C STW60 ≤ 0.02 and I ≤ 0.15, both running the full 150 s without a switch; S512-D:
   D1 arrays ≥ 30 % of live heap in ≥ 3 of its 5 histograms (U11 arm D at 2 GiB: 219–302 MiB of copies), memtable counter
   moving < 1 MB per histogram interval (K).

Endpoints: Java heap OOM on any thread (first error + thread, histogram, dump); GC service loss (default criterion ≥ 90 %
STW over ≥ 60 s, from the GC log); kernel kill (not expected; no container); protective flush (`COMMITLOG_DIRTY` of
`r22.rt`); none.

Verdict mapping ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)):

- **true positive** — at 15,872 MiB, T reaches a Java heap OOM in ≥ 3 runs (n/N reported), C ×3 and I ×3 do not, the
  OOM histogram/dump shows the D3 backlog (queued blob `Mutation`s / `[B`) as the largest holder with D1 arrays present,
  and every constraint is at its default (V1–V7). Status `verified-OOM · deployment` (deviations E1–E6 are environment or
  instrumentation; tmpfs data favours the controls; distinct client addresses model several application hosts).
  An OOM thrown on a thread other than a MutationStage or request thread still counts when the histogram attributes the
  heap to D3 (as R14's ruling).
- **retry** — T OOM in < 3 runs; OOM also in C or I; T ended by the commit-log cap flush before OOM in ≥ 2 runs while the
  backlog was still growing (the cap then decides, and a better design is named from μ_h/λ_h); GC service loss without OOM
  (main or S512; `verified-gap · service-loss` if V1–V5 hold for S512); an invalid T (no entry, `MEMTABLE_LIMIT`, disk,
  another node on the host).
- **false positive** — every valid T run (≥ 3) ran its 900 s or ended by the cap flush with the stall measured and **the
  backlog's growth stopped** below the headroom (backlog slope over the last 300 s ≤ 0 with blob arrivals ≥ 90 % of
  offered, i.e. not throttled by the client), Old after full GC ≤ 0.9 × H, **and** S512-T gives no service loss (≤ 1/3
  runs ≥ 0.90): neither endpoint is reachable at defaults with this holder.

### 2.8 Controls, intervention, time plan

- **Matched control C:** same K₀ trajectory, same offered load (bursts, ≤ 40 / ≤ 16/s hot, 4 × 12 MiB/s blob from the same
  three addresses), same caps and writer count; only n per partition differs (≈ 2,150 vs ≈ 1.23 M). Isolates D1's
  multiplicity on one partition as the cause from the blob load, the hot write count and D2's size.
- **Causal intervention I:** bound D1's multiplicity to 1 (`setconcurrency MutationStage 1`), runtime, I arms only;
  throughput of both streams recorded so a stage that stops useful work is not mistaken for protection.
- **Time plan (America/New_York, 2026-11-21; stage 2 starts ≈ 03:00; no run starts after 06:45; all stopped by 07:00;
  case file by 07:30).** Per-run estimates: T ≈ 1.5 (start) + 3 (F) + 0.5 (Q) + W (≈ 5, ≤ 15) + 1.5 (dump/cleanup) ≈ 12
  min (≤ 22); C/I ≈ 6–7 + W_CI; S512 ≈ 4.5 min.

  | Window | Work | Est. |
  |---|---|---|
  | 03:00–03:40 | freeze check; node check; copy build to `/mydata/s4/r22/cassandra`; harness from R17's (`run.sh`: paths, ports, CPUs, dump dir, W rules; `client.py`: source binding, burst + paced closed-loop hot mode, 3-process 12 MiB blob mode, latency of every response, C fill ≤ 8 in flight; `analyze.py`: humongous regions, per-address counts, W_CI; `seq.sh`: refuse to start after 06:45 or with a STOP file); compile `Poll.java` | 40 min |
  | 03:40–03:50 | shakedown `shake-15872` (T, W 60 s; checks addresses, bursts, entry, counters; not a reading) | 10 min |
  | 03:50–04:30 | T ×3 (≈ 12 min each, ≤ 22) → fix W_CI | 36–66 min |
  | 04:30–05:40 | C1, I1, C2, I2, C3, I3 (W_CI 300–600 s → 11–17 min each) | 66–100 min |
  | 05:40–06:25 | S512: T ×3, C ×3, I ×3, D ×1 (≈ 4.5 min each) | 45 min |
  | 06:25–06:45 | B8 ×1 if it can start by 06:30 | ≤ 15 min |
  | 06:45–07:30 | stop/clean; analysis, §3, §4, V1–V7 table, write-back (retry list, `_INDEX.md`, candidate rows) | 45 min |

  **Drop order** if late or runs overrun: B8; then S512-D; then S512 C and I and T as a block (a T-only S512 adds nothing
  to R17); then W_CI down to its 300 s floor. Never drop T ×3, C ×3, I ×3 at 15,872 MiB. If T1 and T2 both end without
  OOM, still run T3 (V1/false-positive needs three valid runs), and use W_CI = 600 s.
- **Resources:** T: heap 15.5 GiB + native ≈ 2 GiB + tmpfs ≤ 12 GiB data/log + 16 GiB dump ≈ 46 GiB; C/I: tmpfs ≤ 48 MiB/s ×
  W_CI ≤ 28 GiB + 8 GiB log + compaction ≤ 6 GiB ≈ 42 GiB + heap ≈ 60 GiB, of 124 GiB available; `/mydata` ≤ 16 GiB (one
  kept dump); CPU 8 for the node + 5.
- **Left on the node at the end:** `/mydata/s4/r22/` with logs and at most one `.hprof`; `/dev/shm/r22` removed; nothing
  running.

`sha256 of §1–§2 at freeze: d05d9f92d8a25810559deb3e589fd4e065dc07f4ae3bb92532957ea8b4ff9134` (lines 27–423 of this file, from "## 1. Candidate" through the line before this one: `sed -n '27,423p' <file> | sha256sum`; 2026-11-21 02:03 America/New_York) · amendments after the freeze: none

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session on `pc72` (`node2.jason92-326665`), 2026-11-21 02:04–05:16 America/New_York.
Freeze check at 02:04: `sed -n '27,423p' <file> | sha256sum` =
`d05d9f92d8a25810559deb3e589fd4e065dc07f4ae3bb92532957ea8b4ff9134` (matches §2's last line). Stage 2 extended the Summary
above §1, so §1–§2 now sit at lines 38–434; `sed -n '38,434p' <file> | sha256sum` gives the same hash (rechecked 05:15).
Every time below is America/New_York; the node clock is MST and `system.log` is written in UTC.

### 3.0 Dated notes and amendments

- **Start earlier than planned (clock only).** Stage 2 began at 02:04, not ≈ 03:00 (§2.8). The order of §2.8 was kept
  (shakedown, T ×3, then C/I alternating, S512, B8); the 06:45 / 07:30 limits were kept.
- **Harness fixes before any reading was used:** (1) `run.sh`'s "another `CassandraDaemon`" check matched the
  launching `ssh` shell's own command line and refused the first shakedown start (02:08); the check now matches
  only `java` processes. (2) The OOM-line grep matched a `CompileCommand … java/lang/OutOfMemoryError` line of
  `stdout.txt`; it is now a fixed-string match on `java.lang.OutOfMemoryError` (02:13, between runs). (3)
  `analyze.py` (analysis only, after the runs it reads): `system.log` timestamps are UTC with a `T`; rows where the
  poller got no JMX answer (`-1`) are skipped; the OOM time is read from the GC log (the ≥ 10 s gap a heap dump
  leaves, or the last GC event) because the JVM's own `java.lang.OutOfMemoryError` line carries no timestamp.
- **A1 (2026-11-21 02:24, before T2's W) — dump histogram during the sequence.** Cassandra's printed histogram
  (`-Dcassandra.printHeapHistogramOnOutOfMemoryError`) never appeared: the shipped `-XX:OnOutOfMemoryError="kill -9
  %p"` ends the JVM right after the HotSpot heap dump, before `JVMStabilityInspector` runs. The `.hprof` is therefore
  the only histogram at failure (V5), and `run.sh` deletes later dumps on the assumption that the printed one exists.
  So `hprofhist.py` ran on T1's kept dump at once (02:24, `nice 19`, `ionice` idle, CPUs 0–3, away from the node's
  24–31 and the clients' 12–16; ≈ 1 min) instead of after the sequence, and for T3 (02:37, before its W) a watcher
  (`linkdump.sh`) hard-linked the dump on the tmpfs so `hprofhist.py` could read it before it was deleted. T2's dump
  (16.9 GB) was deleted unread. `hprofhist.py` was extended (02:51) to count `int[]` ≥ 1 M elements (G1 fills the
  unused tail of a humongous region with an `int[]` filler), re-run on T1's dump.
- **Instrument limit (not a change):** the JMX poller (R17's `Poll.java`, unchanged) exits on its first refused JMX
  connection. Under the late GC thrash the node refused it at W+390 s (T1), W+484 s (T2), W+335 s (T3); after that
  the GC log, the client CSVs and the dump carry the trend. The hung rule (no JMX **and** no GC log for 180 s) never
  fired.
- **Client-side load loss in T3 (recorded):** from W+421 s (blob 127.0.0.2) / W+451 s (hot) / W+481 s (127.0.0.3/4) to
  the end, the driver failed requests in < 0.1 s without sending them (it had marked the node down during long
  GC pauses; error class not recorded): 1,132 hot and 286 blob requests. T1 and T2 had only the 8–17 fast errors of
  node death itself.
- **W_CI fixed after T3 (02:50):** times to OOM 445.8, ≈ 530, 579.7 s → W_CI = min(900, max(300, ⌈1.25 × 579.7⌉)) =
  **725 s**.
- **Shakedown** `shake-15872` (T, W 60 s; 02:08–02:12) checked addresses (`system_views.clients`: 127.0.0.1 ×4,
  127.0.0.2/3/4 ×2 each), bursts, entry (active 32, pending 444 at W+40) and counters; not a reading.

### 3.1 Environment

- Node `pc72`: x86_64, 40 logical CPUs (2 × E5-2660 v2), 125 GiB (`free -m` total 128,850 MiB, 124 GiB available at every
  start), 8 GiB swap unused, kernel 5.15.0-203-generic, cgroup v2, OpenJDK 11.0.33, G1. Before the first run: no Java
  process, load 0.00, `/dev/shm` (63 GiB tmpfs) empty, ports 7710/7711/9742/7799 free. `run.sh` re-checked other
  `CassandraDaemon`s, memory (≥ H + 50 GiB available), `/dev/shm` (≥ 50 GiB free) and ports before every run (logged
  in each `driver.log`); no other session's process ran on `pc72` during the session.
- Build: `bin conf lib build pylib tools` copied once from `/mydata/s4/cassandra-base` to `/mydata/s4/r22/cassandra`
  (`apache-cassandra-5.0.9-SNAPSHOT.jar`); no `ant`. Poller compiled to `/mydata/s4/r22/classes`.
- E1 ports 7710/7711/9742/7799, cluster `r22-<label>`, RF 1, one node on loopback. E2 data, commit log, hints, saved
  caches, cdc on `/dev/shm/r22/<label>/` (deleted after each run); heap dumps to `/dev/shm/r22/dump-<label>/`. E3 node
  under `taskset -c 24-31` (JVM affinity 24-31; `MaxHintsInProgress` = 1024 = 128 × 8 processors), hot client CPU 12,
  blob clients 13/14/15, poller 16. E4 GC log line in `jvm-server.options`, `printHeapHistogramOnOutOfMemoryError`. E5 blob
  clients bound to 127.0.0.2/3/4 (checked at W+40 of every main run from `system_views.clients` and `ss -tn`). E6
  `nodetool -p 7799 setconcurrency MutationStage 1` in I arms (read back `MutationStage 0 1`). Node under
  `systemd-run --user --scope -p MemorySwapMax=0`; no container memory limit. Config diff (`logs/<label>/conf.diff`):
  only ports, cluster name, directories, JMX port, GC log line.
- **Resolved values (V6/V7):** `-Xmx15872M` (main, as `cassandra-env.sh` resolves for this node), `-Xmx512M` (S512),
  `-Xmx8G` (B8); **`MaxDirectMemorySize` = 15872M** in every run (`cassandra-env.sh` sets it to the hand-set heap
  path's `MAX_DIRECT_MEMORY_SIZE`; same as R17); `ParallelGCThreads` = 40, `ConcGCThreads` = 40 (resolved from the 40
  CPUs of `/proc/cpuinfo`, not the 8-CPU affinity; R17 on `pc96`: 32/32); `G1HeapRegionSize` 16 MiB (992 regions at
  15,872 MiB). From `system_views.settings` (15,872 MiB): `concurrent_writes` 32, `memtable_heap_space` 3968MiB (heap/4),
  `memtable_cleanup_threshold` 0.33333334, `memtable_flush_writers` 2, `memtable_allocation_type` heap_buffers,
  `range_tombstone_list_growth_factor` 1.5, `initial_range_tombstone_list_allocation_size` 1, `max_mutation_size`
  16384KiB, `commitlog_segment_size` 32MiB, **`commitlog_total_space` 8192MiB**, `native_transport_max_threads` 128,
  `native_transport_max_request_data_in_flight` 1664299827B (heap/10), `…_per_ip` 416074956B (heap/40),
  `native_transport_max_frame_size` 16MiB, `write_request_timeout` 2000ms, `native_transport_timeout` 12s,
  `cql_start_time` REQUEST, `hinted_handoff_enabled` true, `enforce_native_deadline_for_hints` false,
  `native_transport_rate_limiting_enabled` false, `compaction_throughput` 64MiB/s, key cache 100MiB, counter cache 50MiB,
  row cache 0MiB, column-value guardrails unset. **Every capacity setting at its shipped default (V6).**
- Harness ([`harness/`](harness/)): `run.sh`, `seq.sh` (refuses to start after 06:45 or with a STOP file), `client.py`
  (schema, settings, clients, fill with ≤ N batches in flight, paced closed-loop `hot` with bursts, open-loop `blob`
  bound to a source address; every response logged with its latency), `Poll.java` (R17's, keyspace `r22`),
  `analyze.py`, `excerpt.sh`, `hprofhist.py`, `linkdump.sh`, `summary.py`, `backlog_at.py`.
- Full logs: `pc72:/mydata/s4/r22/<label>/` (`logs/driver.log, poll.log, hot.csv, hot-resp.csv, blob0..2.csv,
  blob0..2-resp.csv, gc.log*, system.log, debug.log, stdout.txt, rss.log, settings.json, fill.json, *.json,
  flushes.txt`, `hist/L0.txt, L1.txt[, D*.txt, hprof-hist*.txt]`); T1's dump
  `pc72:/mydata/s4/r22/T1/cassandra-1795245166-pid73301.hprof` (17.1 GB, kept as the representative). Excerpts:
  [`logs/<label>/`](logs/) (`analysis.json`, poll every 10 s + last 30 rows, client CSVs every 10 s, GC pause
  excerpt, last humongous-region lines, histogram heads, flush lines, OOM context).

### 3.2 Main condition, 15,872 MiB: T (hot partition)

All three T runs: F to K₀ (1,231,000 tombstones in `pk = 0`, K = 625,380,152 B, **508.0 B per tombstone**, no switch;
51–102 s), Q, W with bursts at W+0/W+20, hot paced ≤ 16/s ≤ 40 out, blobs 3 × 4/3 per s ≤ 28 out each.

| | T1 | T2 | T3 |
|---|---|---|---|
| W start | 02:15:45 | 02:26:53 | 02:39:22 |
| entry check W+40 (active / pending) | 32 / 438 | 32 / 241 | 32 / 411 |
| MutationStage active, mean after W+30 | 32.0 | 31.8 | 32.0 |
| hot issued per min, min 1–3 (λ_h) | 834 / 759 / 651 | 473 / 451 / 486 | 802 / 766 / 740 |
| μ_h (applied hot writes/s, to last JMX sample) | 3.31 | 2.04 | 3.81 |
| blob applies/s (to last JMX sample) | 0.91 | 0.94 | 1.06 |
| blob backlog at W+60 / 120 / 180 / 300 s (queued 12 MiB writes) | 153 / 313 / 471 / 754 | 112 / 281 / n/a / 701 | 141 / 290 / 458 / n/a |
| backlog slope, first 180 s (MiB/s of 16 MiB regions) | 42.8 | 41.8 | 41.3 |
| backlog at the last JMX sample (W+s) | 850 (390) | 851 (484) | 809 (335) |
| blob slots: issued / capped (of 4/s offered) | 1,337 / 571 | 1,405 / 812 | 1,749 / 654 |
| blob issued per min from min 4–5 on | ≈ 84 (cap of 3 × 28 full) | ≈ 84 | ≈ 84–216 |
| hot writes: ok / server timeout / error | 58 / 4,065 / 61 | 54 / 3,352 / 59 | 61 / 3,923 / 1,172 |
| NTR active max / pending max | 81 / 28 | 114 / 35 | 73 / 39 |
| commit log (max read) | 5,568 MiB | 6,304 MiB | 5,568 MiB |
| `r22.rt` switches | 0 | 0 | 0 |
| G1 pauses / Full GCs in W | 1,581 / 327 | 1,416 / 308 | 1,969 / 534 |
| heap after the last 5 Full GCs (MiB of 15,872) | 15,545–15,726 | 15,494–15,656 | 15,682–15,712 |
| humongous regions (GC log) quartiles / max (of 992) | 671 / 811 / 901 / **921** | 740 / 871 / 901 / **921** | 727 / 903 / 915 / **923** |
| STW share, max over 60 s / whole W | 0.972 / 0.716 | 0.977 / 0.703 | 0.987 / 0.773 |
| RssAnon max | 17,282 MiB | 17,625 MiB | 17,324 MiB |
| **endpoint** | **Java heap OOM at W+445.8 s** | **Java heap OOM at ≈ W+530 s** | **Java heap OOM at W+579.7 s** |
| heap dump | 17.14 GB in 21.6 s; node gone W+477 | 16.85 GB in 24.3 s; node gone W+554.5 | 17.10 GB in 17.9 s; node gone W+601 |

OOM time: the start of the GC-log gap the dump leaves (T1 20.7 s, T3 17.0 s gaps). T2's GC log ends with the dump
(last GC event W+534.2 s; node gone W+554.5 s − 24.3 s dump ≈ W+530 s).

**Initiating failure (V5).** In each run `stdout.txt` holds `java.lang.OutOfMemoryError: Java heap space`, `Dumping heap
to /dev/shm/r22/dump-T<n>/… .hprof`, `Heap dump file created`, then `-XX:OnOutOfMemoryError="kill -9 %p"` (excerpt
[`logs/T1/oom-stdout.txt`](logs/T1/oom-stdout.txt)). HotSpot prints no thread for this message and the `kill -9`
precedes Cassandra's own handler, so the throwing thread is not recorded (the design counts an OOM on any thread when
the histogram attributes the heap to D3). The last GC lines before it are back-to-back `Pause Full (G1 Humongous
Allocation)` / `(G1 Evacuation Pause)` with 15.5–15.7 GiB live after each.

**Dump histograms** (`hprofhist.py`, shallow bytes; [`logs/T1/hprof-hist.txt`](logs/T1/hprof-hist.txt),
[`logs/T1/hprof-hist2.txt`](logs/T1/hprof-hist2.txt), [`logs/T3/hprof-hist.txt`](logs/T3/hprof-hist.txt)):

| | T1 | T3 | L0 (before W) |
|---|---|---|---|
| total | 15,751 MiB | 15,746 MiB | 382 MiB (`jcmd` histogram) |
| `byte[]` ≥ 12,000,000 B (12 MiB blob values) | **885 arrays, 10,620 MiB** | **891 arrays, 10,692 MiB** | — |
| `int[]` ≥ 1 M elements (G1 humongous-tail fillers) | 936 arrays, 3,837 MiB | (not counted) | — |
| `int[]` all | 3,872 MiB | 3,864 MiB | small |
| `ClusteringBound[]` + `long[]` (RTL arrays: D2 + in-flight D1 copies) | 480 + 411 = 891 MiB | 447 + 376 = 823 MiB | 24 MiB `long[]` |
| `Mutation` / `PartitionUpdate` / `StorageProxy$4` (queued local writes) | 3,564 / 3,564 / 3,564 | 3,396 / 3,396 / 3,395 | 0 |
| `StorageProxy$LocalMutationRunnable$1` (expired writes re-submitted) | 1,194 | 1,512 | 0 |

So ≈ 885 × 16 MiB = 14.2 GiB of the 15.5 GiB heap is regions of 12 MiB blob values (10.4 GiB of bytes plus 3.5 GiB of
humongous-tail filler), of which ≈ 825–830 are queued writes (the rest the ≤ 60-blob live memtable): D3 is the
dominant holder; D1/D2 arrays ≈ 0.8–0.9 GiB are present.

### 3.3 Main condition, 15,872 MiB: C (matched control) and I (intervention); W_CI = 725 s

Same K₀, the same W streams (bursts, ≤ 40 / ≤ 16/s hot, 3 × 4/3 per s × 12 MiB blobs from 127.0.0.2/3/4, same caps),
the same writer count; C spreads the hot statements over 1,000 partitions, I runs T with `setconcurrency
MutationStage 1` in Q.

| | C1 | C2 | C3 | I1 | I2 | I3 |
|---|---|---|---|---|---|---|
| W start | 02:52:39 | 03:22:38 | 03:51:35 | 03:08:11 | 03:37:05 | 04:07:07 |
| F: tombstones / partitions / K / K per tombstone / s | 1,473,000 / 1,000 / 625.5 MB / 424.6 B / 47 | 1,475,000 / 1,000 / 626.0 MB / 424.4 B / 40 | 1,471,000 / 1,000 / 625.0 MB / 424.9 B / 43 | 1,231,000 / 1 / 625.4 MB / 508.0 B / 103 | same / 38 | same / 102 |
| entry check W+40 (active / pending) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 | 1 / 0 | 1 / 0 |
| MutationStage pending max after W+30 | 1 | 1 | 1 | 8 | 13 | 7 |
| hot issued / ok / timeouts (λ_h) | 11,708 / 11,708 / 0 (16.15/s) | 11,709 / 11,709 / 0 (16.14/s) | 11,712 / 11,712 / 0 (16.15/s) | 11,653 / 11,653 / 0 (16.07/s) | 11,684 / 11,684 / 0 (16.13/s) | 11,694 / 11,694 / 0 (16.14/s) |
| hot latency p50 / p99 / max (ms) | 1.2 / 6.3 / 106 | 1.2 / 5.6 / 741 | 1.2 / 4.2 / 1,315 | 1.4 / 548 / 1,459 | 1.3 / 576 / 1,458 | 1.4 / 510 / 1,421 |
| μ_h (applied/s) | 16.13 | 16.12 | 16.13 | 16.07 | 16.11 | 16.12 |
| blob issued / ok / capped / timeouts (applies/s) | 2,898 / 2,898 / 0 / 0 (3.99) | 2,901 / 2,901 / 0 / 0 (3.99) | 2,901 / 2,901 / 0 / 0 (4.00) | 2,898 / 2,898 / 0 / 0 (4.00) | 2,895 / 2,895 / 0 / 0 (3.99) | 2,898 / 2,898 / 0 / 0 (3.99) |
| blob backlog max (W+60 / 140 / 300 s) | 3 (0 / 0 / 0) | 3 (0 / 0 / 0) | 3 (≤ 0) | 6 (0 / 0 / ≤ 0) | 4 (≤ 0) | 4 (0 / ≤ 0 / 0) |
| first `r22.rt` switch (`COMMITLOG_DIRTY`) / switches in W | W+147 / 5 | W+150 / 5 | W+143 / 5 | W+145 / 4 | W+147 / 5 | W+150 / 5 |
| commit log max | 8,320 MiB | 8,384 MiB | 8,320 MiB | 8,352 MiB | 8,320 MiB | 8,288 MiB |
| G1 pauses / Full GCs | 42 / 0 | 42 / 0 | 42 / 0 | 47 / 0 | 46 / 0 | 47 / 0 |
| heap after pause, max (GC log) | 2,558 MiB | 2,565 MiB | 2,531 MiB | 11,254 MiB | 11,251 MiB | 11,632 MiB |
| STW share, max over 60 s | 0.004 | 0.004 | 0.005 | 0.014 | 0.015 | 0.015 |
| live heap 5 s after W (L1 `jcmd` total) | 453 MiB | 501 MiB | 519 MiB | 391 MiB | 312 MiB | 376 MiB |
| endpoint | none (725 s) | none | none | none | none | none |

Blob backlog matched against T at W+140 s (before I's first switch at W+143–150): **T 363 / 345 / 344 queued blobs
(4.0–4.3 GiB of values, 5.4–5.8 GiB of regions)** vs C 0 / 0 / ≤ 0 and I 0 / ≤ 0 / ≤ 0. Useful work in I is not reduced:
both streams complete at the offered rates with 0 timeouts (the one writer also absorbed both 64-write bursts without a
timeout; p99 0.5–0.6 s). I's heap after a young pause reaches 11.3–11.6 GiB because the single writer's per-write
copies of the 1.23 M-entry RTL (≈ 7–15 MB arrays, humongous) go straight to old regions until a concurrent cycle
frees them; no Full GC ran and live heap at the end is ≤ 0.4 GiB.

### 3.4 Secondary condition S512 (512 MiB, hot client only, W = 150 s)

F to 0.75 × T_tr: 67,100 tombstones (T/I/D `pk = 0`: K = 33,978,152 B, 506.4 B each; C over 671 partitions: 33,652,663 B,
501.5 B each), batches of 100; W: burst of 64 at W+0, then ≤ 64 outstanding, ≤ 110 issues/s.

| Run | W start | μ_h / hot ok per s | MutationStage active max / mean | hot timeouts | p99 / max latency (ms) | pauses / Full GCs | STW60 max | `r22.rt` switch | live after W (L1) |
|---|---|---|---|---|---|---|---|---|---|
| S512-T1 | 04:21:33 | 110.0 / 110.4 | 5 / 0.2 | 0 | 80 / 242 | 323 / 0 | 0.113 | no | 85 MiB |
| S512-T2 | 04:26:18 | 109.3 / 110.3 | 17 / 0.4 | 0 | 117 / 1,119 | 340 / 2 | 0.114 | no | 83 MiB |
| S512-T3 | 04:31:03 | 109.5 / 110.4 | 7 / 0.4 | 0 | 94 / 826 | 281 / 2 | 0.099 | no | 82 MiB |
| S512-C1 | 04:35:45 | 109.5 / 110.4 | 2 / 0.0 | 0 | 1.4 / 59 | 2 / 0 | 0.001 | no | 85 MiB |
| S512-C2 | 04:40:27 | 109.4 / 110.4 | 1 / 0.0 | 0 | 1.4 / 58 | 2 / 0 | 0.001 | no | 85 MiB |
| S512-C3 | 04:45:11 | 109.9 / 110.4 | 1 / 0.0 | 0 | 1.3 / 42 | 2 / 0 | 0.001 | no | 85 MiB |
| S512-I1 | 04:49:58 | 109.8 / 110.4 | 1 / 0.2 | 0 | 63 / 133 | 221 / 0 | 0.078 | no | 88 MiB |
| S512-I2 | 04:54:46 | 109.8 / 110.4 | 1 / 0.2 | 0 | 63 / 188 | 211 / 0 | 0.079 | no | 87 MiB |
| S512-I3 | 04:59:34 | 109.8 / 110.4 | 1 / 0.1 | 0 | 63 / 160 | 209 / 0 | 0.075 | no | 87 MiB |
| S512-D1 (histogram every 30 s) | 05:04:19 | 100.3 / 100.5 | 32 / 6.0 | 121 | 1,661 / 6,452 | 564 / 77 | 0.481 | no | 88 MiB |

The paced client at ≤ 110/s never put S512-T into the thrash: a 64-write burst on a 67 k-entry partition drained
(active mean ≤ 0.4, μ_h = λ_h), so T looked like I. Only S512-D1, whose forced full GCs (the `jcmd` histograms) stall the
stage for a moment, tipped into partial thrash (active 32 at times, 77 Full GCs, 121 timeouts, STW60 0.481). Its five
histograms show D1 arrays (`ClusteringBound[]`/`long[]`/`int[]` above L0) of only 0.1–0.4 MiB in 82–88 MiB live
(predicted ≥ 30 % of live heap; a class histogram runs after a full GC at a safepoint, when few copies are in flight).

### 3.5 B8 (optional boundary point, 8 GiB, T ×1)

`B8` (W start 05:09:15): F 641,000 tombstones, K 324.5 MB (506.2 B each, K₀ at 8 GiB), 48 s. **Entry check failed**
(active 0, pending 0 at W+40; active mean 0.8 after W+30): with n₀ = 641 k one writer clears a 64-write burst fast
enough that the stage never stayed congested — the same bistability R17 saw at 8 GiB. Hot 16.4/s applied (11 burst
timeouts, p99 1.6 s), blobs 4.0/s applied, backlog ≤ 6, STW60 0.324 (humongous RTL-copy garbage), 1 Full GC; `r22.rt`
flushed for `COMMITLOG_DIRTY` at W+146 s and the run stopped at W+206 s (stop rule). No OOM. Live heap 5 s after W: 764
MiB. As §2.5 says for T, a run without entry is not a reading of the mechanism; B8 only shows that at 8 GiB this
workload does not enter the stall.

### 3.6 Totals and clean-up

21 runs (shakedown + 20 readings), all ended by their stop rules; sequence done at 05:13:06. After every run `run.sh`
killed the node, poller and clients by PID and removed `/dev/shm/r22/<label>` and the dump directory; the empty
`/dev/shm/r22` was removed at 05:14. At the end no `java`, client, poller or harness process of this session runs on
`pc72`, `/dev/shm` is empty. Left on `pc72`: `/mydata/s4/r22/` (17 GB: T1's kept dump 16 GB, run logs ≈ 0.1 GB, the
286 MB build copy, harness, excerpts).

## 4. Conclusion (stage 2)

**Verdict: true positive** — status **`verified-OOM · deployment`** (unprotected accumulation × unprotected
accumulation: a stall source with no memory bound feeding an executor queue with no bound), for the main condition
(15,872 MiB heap, every constraint at its default). The secondary condition (S512 service loss) was **not reproduced**
with the paced client (detail below); it was not needed for the verdict.

| Condition | Runs | Endpoint | Status |
|---|---|---|---|
| Main, 15,872 MiB (`cassandra-env.sh`'s own heap for this node), defaults | T ×3, C ×3, I ×3 | T: Java heap OOM **3/3** (W+445.8, ≈ 530, 579.7 s); C 0/3, I 0/3 over 725 s | **`verified-OOM · deployment`** |
| S512, 512 MiB, paced hot client only | T ×3, C ×3, I ×3, D ×1 | no service loss: STW60 T 0.099–0.114, C 0.001, I 0.075–0.079 (D1 0.481, intrusive); no switch; no OOM | `negative` within the tested range (the stall never formed) |
| B8, 8 GiB (boundary point) | T ×1 | no thrash entry (active 0 at W+40); `COMMITLOG_DIRTY` flush at W+146 s; no OOM | invalid as a T reading (no entry); boundary: the stall is not entered at 8 GiB with this client |

| Item | Met | Evidence |
|---|---|---|
| V1 Repetition | yes, 3/3 | T1–T3 each end in `java.lang.OutOfMemoryError: Java heap space` from clean starts (fresh run and data directories, fresh JVM) |
| V2 Matched control | yes, 0/3 | C1–C3: same K₀, same streams, caps and bursts, hot writes over 1,000 partitions; no stall (active ≤ 1), backlog ≤ 3 blobs, 0 timeouts, STW60 ≤ 0.005, live heap ≤ 0.52 GiB after 725 s (W_CI = 1.25 × the slowest T) |
| V3 Measurement | yes | D3 (no counter K exists): backlog = client-issued − applied (`r22.blob` WriteLatency count), 809–851 queued 12 MiB writes at the last JMX sample; physically in the dumps 885 / 891 `byte[]` of 12 MiB (10.4 GiB) plus their humongous-region tails (936 `int[]` fillers, 3.7 GiB) and 3,396–3,564 queued `Mutation`/`StorageProxy$4`; GC-log humongous regions 921–923 of 992. D1 arrays (`ClusteringBound[]` + `long[]`) 0.8–0.9 GiB in the dumps; MutationStage active 32 with ≤ 3.8 hot applies/s |
| V4 Intervention | yes, 0/3 | I1–I3 (`setconcurrency MutationStage 1`): both streams at the offered rates (16.1 hot/s, 4.0 blobs/s, 0 timeouts), backlog ≤ 6 blobs at every second; at W+140 s (before I's first `COMMITLOG_DIRTY` switch at W+143–150) T held 344–363 queued blobs, I and C 0. No OOM over 725 s |
| V5 Initiating failure | yes (thread not recorded) | `stdout.txt` OOM line + `Dumping heap` + `kill -9` per run; GC log: back-to-back `Pause Full (G1 Humongous Allocation)` with 15.5–15.7 GiB live; dump histograms T1, T3 (above). HotSpot's message names no thread and `OnOutOfMemoryError` kills the JVM before Cassandra logs one; the design accepts an OOM on any thread when the histogram attributes the heap to D3 |
| V6 Default constraints | yes | every capacity setting read back at its shipped default (§3.1): `concurrent_writes` 32, growth factor 1.5, memtable pool heap/4 and ⅓ threshold, `commitlog_total_space` 8 GiB, NTR 128 threads, in-flight limits heap/10 and heap/40, `write_request_timeout` 2 s, hints on, `enforce_native_deadline_for_hints` false |
| V7 Acceptable budget | yes | heap 15,872 MiB = what `cassandra-env.sh` resolves on this 125 GiB node (and its cap for any node ≥ 31 GiB); `MaxDirectMemorySize` 15,872 MiB as resolved; no container limit. ≥ 512 MiB (standing rule). The design forbids heaps above 15,872 MiB, so 15,872 MiB is the largest budget tested and it reaches the endpoint 3/3 |

**Reason.** On a one-node RF 1 keyspace, one hot partition with 1.23 M range tombstones (624 MB counted, below the
memtable trigger) was put into U11's copy thrash on purpose (two bursts of 64 writes): every one of the 32 MutationStage
writers then copies the partition's `RangeTombstoneList` per optimistic attempt, and the stage completed only 2.0–3.8
hot writes/s (single writer: > 16/s) while the paced client offered 6–14/s. Every other local write on the node waits
in the same unbounded SEP queue: 12 MiB blob writes arrived at the offered 4/s for 3–4 min and at ≈ 1.4/s once the client's 84 slots were full
(2.5–2.9/s over W),
the stage applied 0.9–1.1/s, and the request threads gave up after 2 s while the queued `Mutation`s, and the expired
ones re-submitted as `LocalMutationRunnable$1` (1,194 / 1,512 in the dumps), stayed. The queue grew at 41–43 MiB/s of
16 MiB humongous regions for the first 3 min, reached 809–851 queued blobs by the last JMX sample, and the heap ended
with 885–891 blob arrays (≈ 14.2 GiB of regions) of 15.5 GiB: Java heap OOM 3/3 at W+446–580 s, with STW over 60 s at
0.97–0.99 just before, the commit log at 5.6–6.3 GiB (below its 8 GiB cap, which would have flushed the hot table) and
no `r22.rt` switch. The same load spread over 1,000 partitions (C) or with one writer (I) was applied as offered (16.1
hot/s, 4.0 blobs/s, backlog ≤ 6, STW60 ≤ 0.015, live heap ≤ 0.52 GiB) for 725 s. Nothing in 5.0.9 bounds the
local-write queue in bytes: the native in-flight limits are released at the 2 s timeout, `checkHintOverload` exempts
self, and the commit-log cap acts only on applied writes. Pattern: **CP-5** (accepting queue with a stalled consumer;
JIRA 12689, phase 2 S2) with CP-4 (lifetime ended by a timeout that does not free the queued write).

**Root cause.** Two unbounded accumulations at shipped defaults: (1) the per-attempt O(n) copy of a range-tombstone
partition × 32 contending writers is charged nowhere and turns one hot partition into a stall of the whole
MutationStage (U11/R17); (2) the MutationStage SEP queue has no bound, and a local write that times out at the client is
kept (and re-submitted as a hint runnable when it expires), so the heap — not any capacity control — is what stops the
backlog. Interpretation: an unprotected accumulation that the project treats as overload by design (CASSANDRA-5039,
11460 Won't Fix), triggered here by a data shape (range tombstones in one partition, CASSANDRA-21492 open) rather than
by a write rate above the node's capacity: the same byte rate is absorbed with ≤ 0.5 % of wall time in GC pauses when the tombstones
are spread out.

**Deviations and limits.** Environment/instrumentation only (E1–E6): one node on loopback, data and commit log on
tmpfs (favours the controls; a spinning disk would stall them too), three client source addresses (the per-IP limit,
heap/40 = 397 MiB, is a per-client control a deployment with several application hosts does not hit; it never bound
here), the node pinned to 8 CPUs with `ParallelGCThreads` resolved to 40 from the 40-CPU host. The workload enters the
thrash with two bursts of 64 hot writes, a load an application can produce (64 concurrent requests on one partition);
the blob size (12 MiB) is below `max_mutation_size` and the frame limit. The blob client's 84-slot cap filled after
≈ 3–4 min (request holds > 21 s under GC), cutting blob arrivals to ≈ 1.4/s (2.5–2.9/s over W, not the predicted
≥ 3.8/s); the OOM came anyway, later than the central prediction (446–580 s vs ≈ 300 s, inside the 220–600 s range).
In T3 the driver failed 1,132 hot and 286 blob requests client-side from W+421–481 s (node marked down during
pauses); the OOM came at W+580 s regardless. The throwing thread is not recorded (V5 above). The JMX poller stopped at
W+335–484 s (refused connection); trends after that are from the GC log, client logs and dumps. T2's dump was deleted
unread (A1); the T1 dump is kept on `pc72`.

**Secondary (S512).** Not reproduced. The design paced the S512 hot client (≤ 110/s, ≤ 64 out) so that C and I would run 150 s without their memtable flush; they did (no switch, STW60 0.001 / 0.075–0.079), but the pacing also kept S512-T out of the thrash: μ_h = λ_h ≈ 110/s, active mean ≤ 0.4, STW60 0.099–0.114 (R17's unpaced closed loop of 64 gave 0.908–0.910). The 512 MiB service-loss reading therefore stays as R17 left it (T 3/3, but without valid 60 s C/I windows); D1 at 512 MiB was not seen in class histograms (≤ 0.4 MiB). This does not affect the main verdict.

**Predictions vs readings (§2.7).** F as predicted for T/I (n₀ 1.231 M, 508.0 B per tombstone, no switch); C reached
K₀ with 1.47 M tombstones at 424–425 B each (predicted 2.1–2.2 M at ≈ 291 B; batches of 1,000 per partition give
partitions of 1,000–2,000 entries instead of ≈ 2,150) — the matched quantity, K₀, was met. T: entry passed 3/3, μ_h
2.0–3.8/s (predicted 2.5–6), λ_h 8–14/s in the first 3 min (predicted 12–16; T2 ≈ 8), blob applies 0.9–1.1/s (0.6–1.8),
slope 41–43 MiB/s (35–54), blob issued ≥ 95 % of offered only for the first 3–4 min (predicted until the last minute),
commit log < 8 GiB and no switch, Java heap OOM 3/3 inside 220–600 s, STW60 ≥ 0.90 before OOM 3/3, humongous regions
≥ 700 (921–923), D1 arrays 0.8–0.9 GiB (0.5–1.4). C and I: as predicted, except I's heap-after-pause (≈ 11 GiB of
humongous copy garbage, see §3.3; predicted "Old after GC ≤ 3 GiB" — live heap ≤ 0.4 GiB) and I had 0 burst timeouts
(predicted ≤ 10). First switch in C/I at W+143–150 s (predicted ≈ 150–200 s).
