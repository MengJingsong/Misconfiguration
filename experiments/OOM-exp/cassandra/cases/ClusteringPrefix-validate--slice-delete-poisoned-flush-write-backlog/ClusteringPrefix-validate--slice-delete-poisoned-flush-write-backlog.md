# U15 (from OC-291; provisional ID B24) — ClusteringPrefix.validate skipped by a slice DELETE: two poisoned flushes pin the memtable pool, every writer parks, and local writes queued on MutationStage exhaust the heap  <!-- file: cassandra/cases/ClusteringPrefix-validate--slice-delete-poisoned-flush-write-backlog/ClusteringPrefix-validate--slice-delete-poisoned-flush-write-backlog.md -->

| Field | Value |
|---|---|
| Case ID | `U15` (U = unprotected-accumulation case; README "ID prefixes"). Reserved as `B24` (B = bypass) when the row was picked; the design shows that the memory which reaches the budget has no control (§2.1, "Direction"), so the next free U number is used |
| From | `OC-291` of the phase-1 OOM candidate list (duplicate `OC-292` covered, §1.2) |
| Phase-1 case file | [`max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md) (OC-292: [`max-unsigned-short-validate-sum--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-validate-sum--autonomous.md)) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, last changed at `afcc43489`), build `pc72:/mydata/s4/cassandra-base`, OpenJDK 11.0.33, G1 as shipped |
| Stage 1 (design) | OOM-agent stage-1 session, 2026-11-21 ≈ 08:02–08:55 America/New_York, repository HEAD `08f0194a3` |
| Stage 2 (verify) | fresh OOM-agent session on `pc72`, 2026-11-21 08:16–10:10 America/New_York; 19 runs (shakedown + 18) |
| Verdict | **true positive** · `verified-OOM · deployment` (unprotected accumulation; stall from a validation bypass + failed-flush release defect) · largest budget with OOM 15,872 MiB, 3/3 |

## Summary

- **Conclusion:** true positive, a Java heap OOM at shipped defaults. On one Cassandra 5.0.9 node, two accepted slice
  DELETEs with a 70,000-byte clustering bound plus an ordinary stream of 1 MiB writes (48/s) killed the node in 3/3 runs
  at a 2 GiB heap (≈ 45 s after the load started) and in 3/3 at 15.5 GiB, the heap `cassandra-env.sh` picks for a
  128 GiB node (≈ 350 s); also at 4 and 8 GiB. The same load with a 65,000-byte bound (0/3) or with the missing check
  restored (0/3, only the poison refused) never stalled. One poison alone pins a memtable but does not stall (0/3).
  Status `verified-OOM · deployment`.
- **Root cause (confirmed):** a CQL slice DELETE (`… AND ck > ?`) never runs `ClusteringPrefix.validate()`,
  so a bound over 65,535 B is accepted and acknowledged. When that memtable flushes, `StatsMetadata` serialization fails
  an assertion; `Flush.run` only records the failure, so the memtable is never discarded and its share of the memtable
  pool stays counted as "reclaiming" for good. Two such flushes leave less than one cleanup threshold of room, the cleaner
  can never fire again, and every write parks forever in the pool allocator (32/32 MutationStage threads in every
  run). Nothing bounds the local writes that then queue on MutationStage (≈ 70 % of the heap in the dumps: 1,350
  queued 1 MiB writes at 2 GiB, 11,070 at 15.5 GiB), so the heap fills with their values. The conditional
  `INSERT … IF NOT EXISTS` route skips the check too and also poisons a flush (probe).

## 1. Candidate

### 1.1 The candidate row and its duplicate (quoted from `phase1-oom-candidates.md` and `runs/wave2.md`, 2026-11-21)

Candidate list row (Status as set by the session when the row was picked):

> | OC-291 | 2026-11-18 | `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous` | guided | Holder: a memtable whose flush failed. Stage 4 found two writes that skip ClusteringPrefix.validate(): a slice DELETE (ModificationStatement.java:762-787, no clustering.validate() on slice bounds) and a conditional write (:573). [details](runs/wave2.md#oc-291) | CP-14, CP-10, CP-5 | picked: B24 (2026-11-21) |

Full text (`runs/wave2.md#oc-291`):

> Holder: a memtable whose flush failed. Stage 4 found two writes that skip ClusteringPrefix.validate(): a slice DELETE (ModificationStatement.java:762-787, no clustering.validate() on slice bounds) and a conditional write (:573). Either accepts a clustering bound over 65535 B, and the later flush fails in StatsMetadata serialization (ByteBufferUtil.writeWithShortLength assert); the node stays up. Why nothing stops it: on a flush failure, Flush.run only records flushFailure (ColumnFamilyStore.java:1258-1264). replaceFlushed/reclaim (:1378-1379) are skipped, so the memtable stays marked flushing and its pool bytes are never released. Its commit-log segments are not discarded (:1149-1153), and on restart replay re-inserts the bad bound and fails again. Rough size at defaults: each failed flush pins about memtable_cleanup_threshold of the pool, about 1/3 of heap/4 (about 680 MB at 8 GiB). One bad delete per memtable pins the whole pool after about 3 flushes. All writes then block in the allocator, MutationStage threads block, and incoming mutations queue without a bound (JIRA 12689 shape).
>
> **Where:** src/java/org/apache/cassandra/db/ColumnFamilyStore.java:1255-1268, :1314-1325, :1378-1379; src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java:762-787, :573

Triage (`runs/triage-2026-11-18.md`, rank 14): "default-reachable yes · single ARM node · … The likely endpoint is service
loss, with heap OOM only through the queue. | The OOM leg overlaps S2 (unbounded MutationStage backlog). The
poisoned-flush trigger is new. Duplicates OC-292."

**Duplicate OC-292** (row Status `open`; full text `runs/wave2.md#oc-292`):

> Same mechanism as the ClusteringPrefix-validate-accessor-size stem; stage 4 for this case saw it too. Holder: a memtable whose flush failed. A conditional write (ModificationStatement.java:573) or a slice delete (:762-787) bypasses this sum check, and the flush fails in StatsMetadata writeWithShortLength. Why nothing stops it: Flush.run catches the failure and only sets flushFailure (ColumnFamilyStore.java:1258-1264). The memtable is never replaced or reclaimed (:1378-1379), so its memtable-pool share stays owned, its commit-log segments stay dirty, and replay at restart reproduces the failure. Rough size: about 1/3 of heap/4 pinned per failed flush. After about 3 the pool is exhausted, writes block and MutationStage queues grow without a bound.

### 1.2 What this design covers

- **Covered (main arms):** the slice-DELETE route shared by both rows (OC-291 and OC-292 name the same two skipped
  paths, the same failure site and the same holder chain; OC-292 differs only in which branch of `validate()` the phase-1
  case traced, the per-value `:278` versus the sum `:284`, and a one-component bound over 65,535 B fails both). A
  verdict here closes both rows; the stage-2 write-back names OC-292 as its duplicate (the row status is the session's
  call, not this file's).
- **Covered as a one-run probe (not counted):** the conditional-write route (`INSERT … IF NOT EXISTS`, `:573`) under the
  shipped `heap_buffers` memtables. Both stage-4 probes ran it only under `offheap_objects`, where it failed earlier
  (`NativeClustering.java:50`, client `WriteTimeout`) and never reached a flush.
- **Not covered:** the restart / commit-log replay leg ("replay fails again"): it needs a restart and its memory is the
  replay path, not the running node's queue; and the unbounded commit-log growth on disk (disk-only, skipped by protocol).
- **Correction to the row's arithmetic:** "after about 3" poisoned flushes. The cleaner fires only when
  `used > reclaiming + ⅓ × pool` (`MemtablePool.java:125-145`). After **two** pinned memtables (each ≈ ⅓ × pool +
  the writes admitted while it was being switched out), `reclaiming + ⅓ × pool` exceeds the pool's limit, so the
  third memtable can never trigger a flush at all, poisoned or not, and allocation stops at the limit (§2.1).

### 1.3 Phase-1 case and its stage-4 result

- Phase-1 case: [`max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md).
  Constraint: `FBUtilities.MAX_UNSIGNED_SHORT` (65,535 B) on one clustering value and on the sum of the components,
  checked by `ClusteringPrefix.validate()` (`ClusteringPrefix.java:272-288`), called for INSERT/UPDATE rows at
  `ModificationStatement.java:815`.
- Stage 4 ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md),
  run 2026-10-26 on `pc07`, 1 GiB heap, `offheap_objects`, 256 / 64 MiB pools): **true negative** for the constraint's
  own claim (the 65,535-B check bounds one key, not total memory). Side findings, quoted from its §8: "(1)
  `INSERT ... IF NOT EXISTS` skips `ClusteringPrefix.validate()` … with `offheap_objects` a 65536-byte clustering then
  fails at `NativeClustering.java:50` … in the mutation stage and the client waits for the 20 s write timeout … (2) A range
  delete whose clustering bound is 70000 bytes passes statement validation (the slice branch `:762-787` never validates)
  and later makes the memtable flush fail (`ByteBufferUtil.writeWithShortLength` assertion during `StatsMetadata`
  serialization): a poison-pill candidate; whether the data returns after a restart or blocks commit-log replay was not
  tested." The probe ran one `nodetool flush`; the node stayed alive. **Pool retention after the failure and the write
  stall were not measured** (one poisoned flush on a 256 MiB pool with `memtable_cleanup_threshold: 0.99`).
- OC-292's stage 4 ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/max-unsigned-short-validate-sum--autonomous.md),
  2 GiB heap): the same probe outcomes (`DELETE ... c2 > <70000 bytes>` accepted; "the later flush logged `AssertionError:
  Attempted serializing to buffer exceeded maximum of 65535 bytes: 70000` at `ByteBufferUtil.writeWithShortLength` from
  `StatsMetadata` serialization on MemtablePostFlush. The node stayed up").

### 1.4 Why an accepted client statement is not "corrupt input"

The playbook skips rows that "need corrupt input". That label is for bytes that violate a format the system reads:
a damaged sstable, commit-log or saved-cache file, a malformed protocol frame, a length field read as garbage (the
CASSANDRA-264 / 6260 / 4555 family). The trigger here is none of that:

1. **It is a well-formed CQL statement on the native protocol**, `DELETE FROM ks.t WHERE pk = ? AND ck > ?`, whose bound
   value is a valid value of the column's type (a 70,000-byte `blob`; CQL values may be up to 2 GiB, the default
   `max_value_size` is 256 MiB and `native_transport_max_frame_size` 16 MiB).
2. **The server's own admission accepts it and acknowledges success** (stage 4, twice). Cassandra does document and
   enforce a 64 KiB clustering limit, and it rejects oversized keys on the INSERT/UPDATE path with
   `InvalidRequestException: Key length of N is longer than maximum of 65535` (`ClusteringPrefix.java:276-286`;
   CASSANDRA-11882 added that check in 3.0.8 for exactly this assertion). The defect is that the slice path skips the
   check: the system is documented to reject such input and fails to. An unchecked path that lets the client's own valid
   request in is what a bypass is, not corrupt input.
3. **The rest of the workload is ordinary.** The poison is two small statements; the memory that reaches the budget is
   1 MiB writes from a normal application, well under `max_mutation_size` (16 MiB) and every native-transport limit.
4. **It is realistic.** An application that deletes a range by a value derived from user data (a long text or blob
   prefix) will send such a bound sooner or later; two of them, at any time and minutes or days apart, are enough (§2.1).

### 1.5 JIRA prior art (read only; nothing posted)

Sources: `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`, and the Apache JIRA REST API
(reachable; read-only `search` and `issue` GETs, 2026-11-21 ≈ 08:09 EST). Queries: text "Attempted serializing to
buffer exceeded maximum" (2 hits), `writeWithShortLength` (20), "Key length" + 65535 (1), "range delete" + 64k/65535 (0),
DELETE + clustering + 64k (21), "flush failure" + memtable (2), flush + AssertionError + StatsMetadata (5), and keys
8496, 10766, 20084, 21609.

| Issue | Status | Relevance |
|---|---|---|
| CASSANDRA-11882 "Clustering Key with ByteBuffer size > 64k throws Assertion Error" | Fixed 2.1.15/2.2.7/3.0.8 | added the `validate()` check for INSERT/SELECT clusterings; the slice-bound path was not covered |
| CASSANDRA-11943 "Allow value > 64K for clustering columns" | Open (7.x) | the 64 KiB limit is a known, intended format limit |
| CASSANDRA-14401 "Attempted serializing to buffer exceeded maximum of 65535 bytes" | Open | same assertion, different site (`RowFilter` serialization on a read, Lucene index plugin); "cluster becomes unresponsive"; no flush, no OOM |
| CASSANDRA-21620 "Stats metadata over-sizes the legacy minimum and maximum clustering values" | Patch Available | same `StatsMetadata` legacy min/max code, a size-accounting mismatch; not this failure |
| CASSANDRA-20084 "WaitQueue.Signal.awaitUninterruptibly() may stuck forever…" | Fixed 4.1.9/5.0.4 | **same endpoint chain, different trigger**: flushes stuck → memtable pool exhausted → writes block → node OOM (4.1.1, production). 5.0.9 has that fix; this case's trigger is independent of it |
| CASSANDRA-10766 "OOM from 22000 memtables" | Duplicate of 8496 | a failed flush (corrupt sstables) followed by OOM; maintainers: continuing past a failed flush would lose commit-log data |
| CASSANDRA-8496 "Remove MemtablePostFlusher" | Open (7.x) | the post-flush ordering design that keeps a failed flush's state |
| CASSANDRA-21609 "A failed flush can strand every thread that waits for it" | Patch Available (5.0.x) | the `Flush.run` catch path; only when `JVMStabilityInspector` itself throws (not here: an `AssertionError` passes through it, `JVMStabilityInspector.java:87-102`) |
| CASSANDRA-15368 "Failing to flush Memtable without terminating process results in permanent data loss" | Invalid | maintainers' view of non-fatal flush failures (commit-log side) |
| CASSANDRA-12689 "All MutationStage threads blocked, kills server" | Fixed 3.0.10/3.10 | the queue leg: blocked MutationStage threads, pending mutations pile up to a heap OOM (MV locks) |

**Verdict: `new`** for the trigger (no issue reports that a slice DELETE or a conditional write skips the 64 KiB
clustering check, or that such a bound poisons a flush); the endpoint chain is a **known shape** (20084, 12689: stalled
writers behind an unbounded stage queue), fixed only for other triggers. Not `known-fixed`, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Direction: unprotected accumulation (holder: the MutationStage local-write backlog), with a validation bypass as
the stall source.** Technique notes: [`bypass-playbook.md`](../../../bypass-playbook.md) for the trigger (a path that
skips the check), [`combo-playbook.md`](../../../combo-playbook.md) for the stall-plus-queue shape (as S2 and R22).
Why not `B`: the bypassed check (`ClusteringPrefix.validate`) guards an encoding limit, not memory; the memtable pool
that the failed flushes pin **counts** the pinned bytes and blocks at its limit (predicted U ≈ K ≤ C in that domain, so
by the protocol's measurement table it is not a pool bypass); the memory that reaches the budget is the queue, which no
control covers. The release defect (a failed flush never discards its memtable) is the stall source, inside a counted
pool.

**Step 1 — the unchecked path.** `ModificationStatement.addUpdates` with slices (`ModificationStatement.java:762-787`):
`createSlices(options)` (`:764`) builds the bounds from the bound values and adds a range tombstone per key
(`addUpdateForKey(updateBuilder, slice, params)`, `:786`) with no `validate()`; the row branch calls
`clustering.validate()` (`:815`). The conditional path takes its clustering at `:573` without it either. The commit log
and the memtable serialize clustering values with vint lengths, so the statement is applied and acknowledged.

**Step 2 — the flush fails.** At flush, `MetadataCollector` keeps the smallest start bound as `minClustering`
(`MetadataCollector.java:323-349`); with `storage_compatibility_mode: CASSANDRA_4` (shipped, `conf/cassandra.yaml:2320`)
sstables are written as `nb`, whose `StatsMetadata` carries the legacy min/max values written by
`ByteBufferUtil.writeWithShortLength` (`StatsMetadata.java:430-446`), which asserts `length <= 65535`
(`ByteBufferUtil.java:361-368`; `-ea` is shipped, `conf/jvm-server.options:109`). So the flush fails **when the
oversized bound is the memtable's smallest start bound**: the design makes every data clustering start with byte `0x01`
and the poison bound 70,000 bytes of `0x00`.

**Step 3 — the memtable is never released.** `Flush.run` (`ColumnFamilyStore.java:1225-1272`) marks the memtables
flushing (`:1240-1241`), and on any `Throwable` from `flushMemtable` only calls `JVMStabilityInspector.inspectThrowable`
(no action for an `AssertionError`) and sets `postFlush.flushFailure` (`:1258-1264`). `replaceFlushed` and `reclaim`
(`:1378-1380`) are skipped, so `memtable.discard()` → `allocator.setDiscarded()` → `releaseAll()`
(`AbstractAllocatorMemtable.java:168-171`, `MemtableAllocator.java:93-118`) never runs. `switchOut` had already called
`allocator.setDiscarding()` (`AbstractAllocatorMemtable.java:162-165`), which moves the memtable's bytes into the pool's
`reclaiming` (`MemtableAllocator.java:129-138`). The post-flush task skips the commit-log discard (`:1149-1153`) and
rethrows (`:1157-1161`); the sequential post-flush executor carries on with later flushes.

**Step 4 — two pinned memtables stall every writer.** The pool cleans when `used > nextClean`, with
`nextClean = reclaiming + limit × cleanThreshold` (`MemtablePool.java:125-145`); `cleanThreshold` = 1/(1 + 2 flush
writers) = 0.33333334 (`DatabaseDescriptor.java:753-763`), so `limit × cleanThreshold` = ⌈L/3⌉. The cleaner flushes the
largest live memtable (`AbstractAllocatorMemtable.java:249-310`). With a poison in each memtable: M0 is switched at
used ≈ L/3 + δ₀ (δ = writes admitted between the trigger and the switch) and pins it; M1 at used ≈ 2L/3 + δ₀ + δ₁
pins as much again; now `nextClean = reclaiming + ⌈L/3⌉ ≥ L + 1 + δ₀ + δ₁ > L`, while `tryAllocate` refuses any
allocation past L (`MemtablePool.java:150-161`). The live memtable M2 can never trigger the cleaner. Writers wait on
`hasRoom` with no timeout (`MemtableAllocator.java:169-197`), signalled only by `released()` (`MemtablePool.java:190-197`),
which nothing calls. Nothing else flushes M2 at defaults: the table's `memtable_flush_period_in_ms` is 0, and the
commit log (≈ L written) stays far below `commitlog_total_space` (8 GiB). **So two accepted poison DELETEs, at any
times, leave the node unable to apply a write until it restarts** (and the restart replays them, §1.2).

**Step 5 — the holder.** One node, RF 1, CL ONE: `StorageProxy.mutate` → `performLocally`
(`StorageProxy.java:1674-1690`) → `Stage.MUTATION.maybeExecuteImmediately`: with a free permit the request thread runs
the apply itself (and parks in the allocator), otherwise the `LocalMutationRunnable` (`StorageProxy$4`) joins the SEP
queue, which has no bound. At `write_request_timeout` (2 s) the request thread answers `WriteTimeout` and releases the
request's native in-flight bytes; the runnable stays queued, holding its `Mutation` and the bound value's fresh `byte[]`
(`CBUtil.readValue` → `readRawBytes`, `CBUtil.java:443-450`). Queued runnables are never dequeued (all 32 permits are
held by parked writers), so the expired-task path (`StorageProxy.java:2634-2656`) never runs. S2, R19 and R22 measured
this holder in dumps (`StorageProxy$4` → `byte[]`). **Arrivals** are bounded by the 128 request threads (less those
parked inline, ≤ 32) × the 2 s hold, by `native_transport_max_request_data_in_flight` (heap/10) and its per-IP value
(heap/40), and by the client.

### 2.2 Protection map

| Domain | Allocation and owner | Counter / limit (contract C) | Scope and multiplicity | Lifetime | At the limit |
|---|---|---|---|---|---|
| D0 clustering key check (trigger, not memory) | — | `ClusteringPrefix.validate()` 65,535 B per value / sum (`ClusteringPrefix.java:272-288`), INSERT/UPDATE rows only | per statement | — | `InvalidRequestException`; **skipped** on slice bounds (`:762-787`) and CAS (`:573`) |
| D1 pinned memtables (stall source) | `SkipListMemtable` of `u15.t` whose flush failed: 1 MiB `byte[]` values (`> MAX_CLONED_SIZE` 128 KiB, allocated outside slab regions but charged, `SlabAllocator.java:52`), partitions, rows | memtable pool on-heap `memtable_heap_space` = heap/4 (`heap_buffers`), counted as `reclaiming` | one per poisoned flush; 2 suffice | **forever** (release defect: `discard()` never runs) | counted; with ≥ 2 pinned, no clean can fire |
| D2 live memtable | current `u15.t` memtable | same pool; cleaner at `used > reclaiming + ⌈L/3⌉` | one | until flush (never, after the stall) | allocation refused at L; writers wait on `hasRoom` without a timeout |
| D3 local-write backlog (**claimed OOM holder**) | `StorageProxy$4` → `Mutation` → `PartitionUpdate` → 1 MiB `byte[]` (one per write) in the MutationStage SEP queue | **none** (queue unbounded; in-flight bytes and the request thread are released at the 2 s timeout) | every write that arrives after the stall | until applied: never | nothing |
| D4 requests in flight | native `Message` + decoded values; ≤ 32 of them parked inline for good | `native_transport_max_request_data_in_flight` heap/10, per IP heap/40 (wire bytes); 128 request threads | node / per source address | until the response (timeout) | backpressure (stop reading) |
| D5 commit log | mmap segments (tmpfs, not heap) | `commitlog_total_space` = min(8,192 MiB, ¼ volume) | node | the pinned memtables' segments are never discarded | flushes tables dirty in the oldest segment; does not reach the parked memtable (the live one holds no older data); not reached (≤ L written) |
| D6 baseline | caches, schema, metrics, Netty, client sessions | own caps | node | standing | — |

Budget: the Java heap. D1–D4 and D6 are heap; D5 is not. No container limit.

### 2.3 Configuration and budget audit

- **Source / build:** Cassandra 5.0.9 as pinned; built tree `pc72:/mydata/s4/cassandra-base`
  (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`). Stage 2 copies `bin conf lib build pylib tools` once to
  `/mydata/s4/u15/cassandra` (no `ant` there). Intervention build (§2.8): a full copy of `cassandra-base` to
  `/mydata/s4/u15/cassandra-patched`, the diff of §2.8 applied, `ant jar` (fallback: `javac` of the one file against the
  built jar + `lib/*.jar`, then `jar uf` of `ModificationStatement*.class` into the patched tree's jar). The diff is
  saved as `harness/validate-slice-bounds.diff`.
- **Node `pc72`** (checked read-only 2026-11-21 08:08 EST): `node2.jason92-326665`, x86_64, kernel 5.15.0-203, 40
  logical CPUs (2 × E5-2660 v2), 125 GiB RAM (124 GiB available), `/mydata` spinning, 714 GiB free; `/dev/shm` 63 GiB
  tmpfs, empty; no `CassandraDaemon` and no Java process; load 0.00; OpenJDK 11.0.33; `/usr/bin/ant`; `/mydata/s4/`
  holds only `cassandra-base` (R22's run directory is gone; its harness is in its case folder). Node clock MST; every
  time in this file is America/New_York.
- **Capacity constraints, all at shipped defaults (V6), resolved at H = 2,048 MiB:** `memtable_allocation_type:
  heap_buffers` (`cassandra.yaml:825`); memtable `SkipListMemtable` (`:783-786`); `memtable_heap_space` = heap/4 =
  **512 MiB** (L = 536,870,912 B); `memtable_flush_writers` = 2 (one data directory) → `memtable_cleanup_threshold` =
  0.33333334 → trigger ⌈L/3⌉ = **178,956,971 B (170.7 MiB)**; `concurrent_writes: 32`; `write_request_timeout:
  2000ms`; `native_transport_max_threads` 128; `native_transport_max_request_data_in_flight` heap/10 = 204.8 MiB,
  `…_per_ip` heap/40 = 51.2 MiB; `native_transport_max_frame_size` 16 MiB; `max_mutation_size` 16 MiB
  (`commitlog_segment_size: 32MiB`); `commitlog_total_space` → 8,192 MiB (¼ of the 63 GiB tmpfs is larger);
  `native_transport_rate_limiting_enabled: false`; `storage_compatibility_mode: CASSANDRA_4`; `disk_failure_policy:
  stop` (not triggered: an `AssertionError` is not an `FSError`); table options default (`memtable_flush_period_in_ms`
  0, STCS, LZ4); guardrails default (column value size unset). **Read back per run** from `system_views.settings`
  (as R22's `client.py settings`) and recorded; any mismatch with these values invalidates the run.
- **Budgets (V7):** main **2,048 MiB** heap (the ideal budget; ≥ 512 MiB, so V7 holds under the standing rule).
  Budget search upward (T arm only): **4,096, 8,192 and 15,872 MiB**, the last being what `cassandra-env.sh` resolves on
  this 125 GiB node (min(½ RAM, 15,872 MiB)), i.e. "a 128 GiB node at the stock heap". `MaxDirectMemorySize` as
  `cassandra-env.sh` resolves it for the hand-set heap (record). **No container memory limit**; `systemd-run --user
  --scope -p MemorySwapMax=0` only keeps swap away.
- **JVM as shipped:** G1, `G1HeapRegionSize=16m` (`jvm11-server.options:66`; a 1 MiB value is not humongous),
  `HeapDumpOnOutOfMemoryError`, `-XX:OnOutOfMemoryError="kill -9 %p"` (so Cassandra's printed histogram never appears:
  the `.hprof` is the histogram, R22 A1), `-ea`. `ParallelGCThreads`/`ConcGCThreads` as resolved (record).
- **Deviations (environment / instrumentation only; none changes a capacity setting):**
  - E1 one node on loopback, keyspace RF 1; ports storage **7720**, ssl 7721, native **9752**, JMX **7809** (if busy, the
    next free block, recorded); cluster `u15-<label>`.
  - E2 data, commit log, hints, saved caches, cdc on **`/dev/shm/u15/<label>/`** (tmpfs, deleted after each run): the disk
    spins, and a slow flush would change C's pool cycle. Logs, GC logs, histograms, thread dumps on
    `/mydata/s4/u15/<label>/`. Heap dumps to `/dev/shm/u15/dump-<label>/`; every 2 GiB T dump is moved to
    `/mydata/s4/u15/<label>/` (≈ 2 GB each, kept); a dump above 4 GiB is read by `hprofhist.py` (watcher `linkdump.sh`,
    as R22) and then deleted, except the first one of each budget.
  - E3 CPU: node under `taskset -c 24-31` (8 logical CPUs, as R22); data clients CPUs 12–15, poison client 16, poller 17;
    dump analysis on 0–3, `nice 19`.
  - E4 instrumentation: R22's GC log line (`-Xlog:gc*=info,gc+heap=debug,safepoint=info:file=<run>/logs/gc.log:…`). No
    Byteman, no patch outside arm I.
  - E5 client source addresses: the four data clients bind to **127.0.0.2, .3, .4, .5** (R22's `connect` wrapper), the
    poison client uses 127.0.0.1; checked per run in `system_views.clients`. One address would cap 4 × 32 MiB outstanding
    at the per-IP limit (51.2 MiB): a property of the test client, not of a deployment with several application servers.

### 2.4 Ceiling arithmetic (before any reading)

**Without a stall (C, I, D1):** pool ≤ L counted (live ≤ ⌈L/3⌉ + one or two flushing ≤ ⌈L/3⌉ each, recycled; D1: one
⅓ pinned) + in flight ≤ 128 MiB (4 × 32 × 1 MiB) + baseline 0.2–0.4 GiB ≈ **0.8–1.0 GiB at 2 GiB**: no OOM. The sum of
the contract capacities plus baseline stays below the budget at every heap (≈ 0.25 H + 0.13 + 0.3 GiB).

**With the stall (T):** D1 + D2 ≈ L (counted; plus object overhead, measured), D4 ≤ 160 MiB (128 waiting + ≤ 32 parked
inline), D6 0.2–0.4 GiB; the rest of the heap is left for D3, which grows at the arrival rate r_a:

- Offered: 4 data clients × 12/s × 1 MiB = 48 writes/s = **48 MiB/s**, ≤ 32 outstanding per client.
- After the stall each write holds a request thread 2 s: capacity ≥ (128 − 32) / 2 s = 48/s, and ≤ 32 outstanding per
  client sustains 16/s per client ≥ 12/s offered. So r_a ≈ **40–48 MiB/s** until GC pauses lengthen the holds
  (then the client caps slots; recorded as `capped`).
- Write time to the stall: ≈ L / 48 MiB/s (+ the third memtable's fill).

| H (MiB) | L | stall at W + | room for D3 (H − L − D4 − D6) | D3 fill at 40–48 MiB/s | predicted OOM at W + (central) | queued 1 MiB writes at OOM |
|---|---|---|---|---|---|---|
| 2,048 | 512 | 10–14 s | 1.08–1.28 GiB | 23–33 s | 35–180 s (≈ 50 s) | ≈ 1,100–1,300 |
| 4,096 | 1,024 | 21–27 s | 2.6–2.8 GiB | 55–72 s | 80–300 s (≈ 100 s) | ≈ 2,700–2,900 |
| 8,192 | 2,048 | 43–52 s | 5.6–5.8 GiB | 120–150 s | 170–600 s (≈ 200 s) | ≈ 5,700–5,900 |
| 15,872 | 3,968 | 83–100 s | 11.3–11.5 GiB | 240–295 s | 330–900 s (≈ 400 s) | ≈ 11,500–11,800 |

The late phase is slower than the constant-rate figure (R22: arrivals fall once full GCs dominate), hence the upper
bounds. Commit log at the stall ≈ L (≤ 4 GiB) < 8 GiB, so the protective commit-log flush never fires (and could not
reach the parked memtable anyway, §2.2 D5). Disk: T writes ≈ L of aborted sstables (deleted on abort) + L of commit log.

### 2.5 Workload and environment

- **Node and launch:** `pc72` (`ssh pc72`), as R22's `harness/run.sh` (paths, ports, CPUs, dump dir changed): `( setsid
  nohup systemd-run --user --scope -p MemorySwapMax=0 taskset -c 24-31 env CASSANDRA_CONF=… CASSANDRA_LOG_DIR=…
  MAX_HEAP_SIZE=<H> CASSANDRA_HEAPDUMP_DIR=… <cassandra>/bin/cassandra -f < /dev/null > <run>/logs/stdout.txt 2>&1 & )`;
  bounded wait for the native port (≤ 180 s); PID from the process list. **Before each run:** no other `java …
  CassandraDaemon` (leave other sessions' nodes alone; if one runs on `pc72`, wait and record), `free -m` ≥ H + 40 GiB
  available, `/dev/shm` ≥ 40 GiB free, ports free. **After each run:** kill node and clients by PID, copy readings,
  `rm -rf /dev/shm/u15/<label>` (and the dump directory once handled).
- **Client** (R22's `client.py`, adapted): Python 3 with the bundled driver, **protocol 4**,
  `WhiteListRoundRobinPolicy(['127.0.0.1'])`, `FallthroughRetryPolicy`, CL ONE, `token_metadata_enabled=False`, client
  request timeout 60 s; prepared statements; every response (ok, `WriteTimeout`, `InvalidRequest`, other error, client
  timeout) counted with its latency, per second, per process.
- **Schema:** `CREATE KEYSPACE u15 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u15.t (pk bigint, ck blob, v blob, PRIMARY KEY (pk, ck))`, all options default.
- **Data stream (all arms):** 4 processes bound to 127.0.0.2–.5; open loop **12/s each** (48/s total), **≤ 32
  outstanding each** (a slot that finds 32 outstanding is skipped and counted `capped`); statement
  `INSERT INTO u15.t (pk, ck, v) VALUES (?, ?, ?)` with pk = address index × 10⁹ + seq, **ck = `0x01` ‖ 8-byte seq**
  (every data clustering starts with `0x01`), v = one **1,048,576-byte** random value generated once per process.
- **Poison stream** (127.0.0.1, ≤ 4 outstanding, starts with the data stream; the first poison at W + 0 s):
  - **T, I:** `DELETE FROM u15.t WHERE pk = 0 AND ck > ?` bound to **70,000 bytes of `0x00`**, **1 per second** for the
    whole W (each memtable gets ≥ 2 poisons at 48 MiB/s; ≥ 2 pinned memtables are needed, §2.1 step 4).
  - **C:** the same statement and rate with **65,000 bytes of `0x00`** (≤ 65,535: legal to serialize).
  - **D1:** the 70,000-byte DELETE **once**, at W + 0 s, then nothing.
  - **P-CAS:** `INSERT INTO u15.t (pk, ck, v) VALUES (0, ?, 0x00) IF NOT EXISTS` with ck = 70,000 bytes of `0x00`, 1/s.
- **Phases per run:** start node → schema → settings read-back → Q (10 s idle, `jcmd <pid> GC.class_histogram` = L0, 10 s
  idle) → **W** (data + poison clients together) → stop rule → if the node lives, L1 histogram, then kill.
- **Stall check (all arms, recorded at W + 30 s for 2 GiB, W + 60/90/150 s for 4/8/15.5 GiB):** stalled ⇔ the table's
  `WriteLatency` count (applied writes) rose by < 5 over the last 10 s while ≥ 300 data writes were issued, and
  MutationStage active = 32. Plus **one `jcmd <pid> Thread.print`** at that time (all arms): count of threads in
  `MemtableAllocator$SubAllocator.allocate`.
- **Stop rules:** T at node death (OOM) or **W_T** = 600 s (2 and 4 GiB) / 900 s (8 and 15.5 GiB). C, I, D1, P-CAS at
  node death or **W_C** (fixed after T3: W_C = min(600, max(300, ⌈2 × the longest T time to OOM⌉)) s; 600 s if no T
  run reached OOM). A T run with no stall at its stall check is `invalid-T (no stall)` and runs on to W_T for its readings.
- **Stopping budget:** ≤ 20 runs plus one shakedown; no heap above 15,872 MiB; no constraint changed after a failure; no
  run starts after **13:15**; every process stopped and the case file written by **14:00**. A node silent on JMX and in
  its GC log for 180 s is `jcmd Thread.print`-ed once and killed by PID (`hung`, recorded).

### 2.6 Instruments (U independent of K)

- **Poller** (R22's `Poll.java`, keyspace/table `u15.t`, JMX every 1 s): heap pools (Eden/Survivor/Old, Old collection
  usage), GC counts/times; for `u15.t`: `MemtableOnHeapDataSize` (live, K_live), `AllMemtablesOnHeapDataSize` (live +
  flushing, K_all), `MemtableSwitchCount`, `PendingFlushes`, `WriteLatency` count (applied); MutationStage and
  Native-Transport-Requests active / pending / completed; `ClientRequest Write Timeouts`; `DroppedMessage MUTATION_REQ`;
  `CommitLog TotalCommitLogSize`. Plus `RssAnon` every 1 s. MBean names checked at the shakedown (−1 = missing,
  recorded).
- **system.log** (UTC): every `Enqueuing flush of u15.t, Reason: …`, `Flushing largest … Used total: a/b, live: c/d,
  flushing: e/f` (the pool's own used and reclaiming ratios: K for D1+D2), each `AssertionError: Attempted serializing to
  buffer exceeded maximum of 65535 bytes: 70000` with its thread and stack, `Completed flushing`, compaction lines.
- **Clients:** per second and process: issued, capped, ok, `WriteTimeout`, `InvalidRequest`, other, client timeouts,
  outstanding, latency p50/p99/max.
- **U per domain:**
  - **D3 (claimed holder):** backlog(t) = Σ data issued − Σ capped − applied (`WriteLatency`) − ok-before-stall
    adjustments (cross-checked: after the stall, applied is flat); U_D3 = backlog × 1 MiB. **Physical, at OOM:** the
    `.hprof` (`hprofhist.py`, shallow counts): instances of `StorageProxy$4`, `org.apache.cassandra.db.Mutation`,
    `PartitionUpdate`, and `byte[]` of length 1,048,576; K for D3: none.
  - **D1+D2:** K = K_all and the logged ratios; U = `byte[]` of 1,048,576 B in the dump minus queued and in-flight ones
    (count(1 MiB `byte[]`) − count(`StorageProxy$4`) − ≤ 160), × 1 MiB, compared with K_all; instances of
    `SkipListMemtable` (expected: 3 for `u15.t` + system tables' ones, against L0).
  - **Live heap:** heap after each `Pause Full` from the GC log; Old collection usage.
- **On OOM (V5):** first `java.lang.OutOfMemoryError` line in `stdout.txt`/`system.log`, the `.hprof` and its histogram,
  the last 60 s of the GC log, the last 30 poller rows, the thread dump from the stall check.

### 2.7 Predicted response, endpoints and verdict mapping

Predictions (before readings), main budget 2,048 MiB:

1. **T ×3:** two `MEMTABLE_LIMIT` flushes of `u15.t` (≈ W + 3–5 s and W + 6–9 s), each followed by the 70,000-B
   `AssertionError` from `StatsMetadata`; `Flushing largest` lines read flushing ≈ 0.33 then ≈ 0.67; **no third
   `MEMTABLE_LIMIT` flush** in the whole run; K_all reaches 0.97–1.0 × L (≥ 520 MB) by W + 15 s and stays; applied writes
   flat from ≈ W + 10–14 s; stall check passed (MutationStage active 32; ≥ 20 threads parked in
   `SubAllocator.allocate`, the rest of the 32 too if they are request threads); after the stall ≥ 95 % of data writes
   end in `WriteTimeout`, NTR active ≥ 90; backlog slope 35–48 MiB/s over the first 20 s after the stall; Old after
   full GC rising to > 1.9 GiB; **Java heap OOM in 3/3 at W + 35–180 s** (central ≈ 50 s). Dump: ≥ 900 `StorageProxy$4`
   (central 1,100–1,300) and as many 1 MiB `byte[]` above the memtables' ≈ 500, together ≥ 60 % of the heap; the pinned
   memtables ≈ 0.6–0.7 L of 1 MiB values reachable from two flushing `SkipListMemtable`s; U_D1+D2 within 10 % of K_all.
   Commit log ≤ 0.7 GiB.
2. **C ×3 (65,000-B bound):** flushes every ≈ 3.6 s, all `Completed flushing`, no `AssertionError`; K_all saw-tooth
   ≤ 0.67 L; applied ≈ 48/s, p99 < 1 s, 0 timeouts after W + 10 s; stall check fails; backlog ≈ 0; Old after GC ≤ 1.0
   GiB; **no OOM** in W_C.
3. **I ×3 (patched build, 70,000-B bound):** every poison answered `InvalidRequest` "Key length of 70000 is longer than
   maximum of 65535"; otherwise as C; **no OOM** in W_C. Useful work (data writes applied/s) equals C's.
4. **D1 ×3 (dose: one poison):** one failed flush, then flushes every ≈ 3.6 s at the higher trigger
   (`used > reclaiming + L/3`), K_all oscillating between ≈ 0.33 L and ≈ 0.67–1.0 L; no stall; **no OOM** in W_C.
5. **Budget search (T ×1 each, then repeats):** OOM at 4,096 and 8,192 MiB (times as §2.4); at 15,872 MiB OOM at W +
   330–900 s, or the run reaches W_T with the stall standing and the backlog still growing (then `boundary not reached in
   W_T`, not a negative).
6. **P-CAS ×1 (probe):** either the 70,000-B CAS insert is applied and poisons a flush like the DELETE (stall, OOM as T),
   or it fails before the memtable (an assertion or `InvalidRequest` on the Paxos path); recorded only.

Endpoints: Java heap OOM (first error, histogram from the dump); GC service loss (≥ 90 % STW over ≥ 60 s); write
service loss (the stall itself: 0 applied writes over ≥ 60 s while ≥ 90 % of offered writes are issued); kernel kill (not
expected); none.

Verdict mapping ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)):

- **true positive** — at 2,048 MiB (or another budget ≥ 512 MiB, all constraints at defaults), T reaches a Java heap
  OOM in ≥ 3 runs, C ×3 and I ×3 do not, the dump shows D3 (queued `StorageProxy$4` with 1 MiB `byte[]`) as the largest
  holder with the pinned memtables present and K_all ≈ L, and ≥ 2 failed flushes precede the stall in each T run.
  Status `verified-OOM · deployment` (E1–E5 are environment or instrumentation). Report the largest budget with OOM and
  its n/N.
- **retry** — T OOM in < 3 runs; OOM in C or I; a stall without OOM (write service loss or GC service loss only:
  `verified-gap` if V1–V5 hold); `invalid-T (no stall)` in ≥ 2 runs (e.g. the flush does not fail, or a third memtable
  flush happens); arrivals throttled below 50 % of offered before the heap fills (a client or native limit decides, name
  it).
- **false positive** — ≥ 3 valid T runs show the stall and arrivals ≥ 90 % of offered, but the backlog's growth stops
  below the room (slope ≤ 0 over the last 120 s, Old after full GC ≤ 0.9 H) at 2,048 MiB **and** at every budget run,
  i.e. something drains or drops the queued writes; name it from the dump.

### 2.8 Controls, intervention, time plan

- **Matched control C:** the same statement, rate, client addresses, data stream and initial state; only the poison
  bound differs (65,000 vs 70,000 bytes of `0x00`, both the memtable's smallest start bound). Isolates the oversize
  bound's flush failure as the cause from the DELETE load and the range tombstones.
- **Causal intervention I (×3):** restore the missing check on the bypassing paths, separate build, diff saved:
  ```diff
  --- a/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java
  +++ b/src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java
  @@ makeCasRequest (line 573)
           Clustering<?> clustering = Iterables.getOnlyElement(createClustering(options, clientState));
  +        clustering.validate(); // U15 intervention: same check as the row path (:815)
  @@ addUpdates, slice branch (line 764)
               Slices slices = createSlices(options);
  +            for (Slice slice : slices) // U15 intervention: validate slice bounds like clusterings (:815)
  +            {
  +                slice.start().validate();
  +                slice.end().validate();
  +            }
  ```
  The original failure is reproduced on the unmodified build (T). Throughput of the data stream is recorded so that
  "no OOM" is not bought by refusing useful work (only the poison statements are refused).
- **Dose arm D1 (×3, optional):** one poison only, unmodified build: shows that one pinned memtable is survivable and
  that the stall needs two (§2.1 step 4).
- **Probe P-CAS (×1, optional):** the conditional-write route of both rows under `heap_buffers`; not counted.
- **Shakedown** `shake` (T, 2 GiB, W 40 s; checks addresses, poison acceptance, the `AssertionError` lines, MBean names,
  stall check, thread dump; not a reading).
- **Time plan (America/New_York, 2026-11-21; stage 2 ≈ 09:00–14:00; no run starts after 13:15; every process stopped and
  the case file written by 14:00).** Per-run estimates at 2 GiB: start ≈ 1 min, schema + Q ≈ 0.5, W (T ≈ 1–3; C/I/D1 =
  W_C 5–10), dump + clean-up ≈ 1 → T ≈ 4–6 min, C/I/D1 ≈ 8–13 min.

  | Window | Work | Est. |
  |---|---|---|
  | 09:00–09:45 | freeze check; node check; copy the build to `/mydata/s4/u15/cassandra`; copy `cassandra-base` to `cassandra-patched`, apply the diff, `ant jar` (in the background); harness from R22's (`run.sh`: ports, dirs, stop rules, stall check + thread dump; `client.py`: 4 bound data clients, poison modes delete/cas/once and bound size; `Poll.java`: table `u15.t`, `AllMemtablesOnHeapDataSize`, `PendingFlushes`; `seq.sh` refusing starts after 13:15 or with a STOP file; `hprofhist.py`: 1 MiB `byte[]` and `StorageProxy$4` counts) | 45 min |
  | 09:45–09:55 | shakedown | 10 min |
  | 09:55–10:25 | T ×3 at 2,048 MiB → fix W_C | 15–30 min |
  | 10:25–11:35 | C1, I1, C2, I2, C3, I3 (W_C 300–600 s) | 50–80 min |
  | 11:35–12:35 | budget search: T at 4,096, 8,192, 15,872 MiB ×1 each (stop going up at the first budget without OOM) | 20–45 min |
  | 12:35–13:15 | repeats at the largest OOM budget (×2, for n/3) if it is above 2 GiB; then D1 ×3; then P-CAS ×1 | ≤ 40 min |
  | 13:15–14:00 | stop and clean; analysis, §3, §4, V1–V7 table, write-back (candidate rows OC-291/OC-292, `_INDEX.md`, retry list if needed) | 45 min |

  **Drop order** if late or runs overrun: P-CAS; D1; the repeats at the largest budget; the 15,872 MiB point; the 8,192
  MiB point; then W_C down to its 300 s floor. Never drop T ×3, C ×3, I ×3 at 2,048 MiB. If the patched build fails by
  10:25, use the `javac` + `jar uf` fallback (§2.3) and record it; if that fails too, I is `infeasible` (V4 unmet,
  status `(no intervention)`), and D1 ×3 runs in its slot.
- **Resources:** T at 2 GiB: heap 2 GiB + tmpfs ≤ 1 GiB + dump 2 GiB; C/I/D1: tmpfs ≤ 48 MiB/s × W_C ≤ 28 GiB + compaction
  ≤ 4 GiB; T at 15,872 MiB: heap 15.5 GiB + tmpfs ≤ 8 GiB + dump ≤ 17 GiB; all within 124 GiB RAM and the 63 GiB tmpfs.
  `/mydata` ≤ 25 GiB (kept dumps).
- **Left on the node at the end:** `/mydata/s4/u15/` (logs, kept dumps, the patched tree); `/dev/shm/u15` removed;
  nothing running.

`sha256 of §1–§2 at freeze: b67376440aa7d635e95b7ebfb844a4c66699e7f6a3da846848832481bd3ab990` (from the line "## 1. Candidate" through the line before this one, `sed -n
'23,434p' <file> | sha256sum`; 2026-11-21 08:15 America/New_York) · amendments after the freeze: §2.9 (stage 2; the hash
above was re-checked at 08:16 and matches; after stage 2 filled the Summary the same §1–§2 text is lines 30–441, `sed -n
'30,441p' <file> | sha256sum` gives the same hash)

### 2.9 Amendments (stage 2, dated, each made before the readings it affects)

- **A1 (2026-11-21 08:29 EST, after the shakedown, before T1): K for D1+D2.** §2.6 takes K_all from
  `AllMemtablesOnHeapDataSize` as "live + flushing". In the pinned 5.0.9 source that gauge sums only the **current**
  memtable (`TableMetrics.java:506-512` → `getMemoryUsageWithIndexes`, `:876-881`, `getCurrentMemtable()` only), so it
  cannot show pinned memtables (the shakedown read 169 MiB while the pool's own log line read "Used total 0.67 … flushing
  0.33"). The pool's counter is instead read from its own log lines: **K_D1+D2 = Σ `Enqueuing flush of u15.t … Usage:`
  of the poisoned memtables (the bytes moved to `reclaiming`) + K_live at the stall**, cross-checked with the last
  `Flushing largest … Used total / flushing` ratios. The JMX column is still recorded (as K_live+0, labelled "current
  memtable only"). No other step changes.
- **A2 (same time): dumps.** The stage-2 brief limits kept heap dumps to one representative. Every dump is read by
  `hprofhist.py` in place on tmpfs; only the first counted T dump at 2,048 MiB is kept on `/mydata` (§2.3 E2 said every
  2 GiB T dump is kept). Readings unchanged.

## 3. Runs (stage 2)

Stage 2 by a fresh OOM-agent session, 2026-11-21 08:16–10:10 America/New_York, node `pc72`. Every time below is
America/New_York unless marked UTC (`system.log`) or MST (node clock, GC log). W+ times are seconds after the data and
poison clients started.

### 3.1 Environment, build and harness

- **Freeze check:** `sed -n '23,434p' <file> | sha256sum` = `b67376440aa7d635e95b7ebfb844a4c66699e7f6a3da846848832481bd3ab990`
  at 08:16 (matches §2's line); re-checked after the §2.9 amendments were written (still matches).
- **Node `pc72`** (`node2.jason92-326665`): x86_64, kernel 5.15.0-203-generic, 40 logical CPUs, 125 GiB RAM, 8 GiB swap
  (kept at 0 for the node by `systemd-run --user --scope -p MemorySwapMax=0`), cgroup v2, `/dev/shm` 63 GiB tmpfs (empty
  at start), `/mydata` spinning 714 GiB free; OpenJDK 11.0.33+9 (Ubuntu). At 08:16 no `CassandraDaemon` and no Java
  process, load 0.00, `/mydata/s4/` held only `cassandra-base`. Nothing else ran on `pc72` during the session (each
  `run.sh` checks for any other `CassandraDaemon` before it starts; none was found).
- **Builds:** unmodified = `bin conf lib build pylib tools` of `pc72:/mydata/s4/cassandra-base` copied to
  `/mydata/s4/u15/cassandra` (jar `ModificationStatement.class` 47,012 B, 2026-11-17). Intervention = full copy to
  `/mydata/s4/u15/cassandra-patched`, [`harness/validate-slice-bounds.diff`](harness/validate-slice-bounds.diff) applied
  (exactly §2.8's two hunks), `ant jar` BUILD SUCCESSFUL in 54 s (no fallback needed; patched class 47,193 B; every run
  logs the class it ran).
- **Harness** ([`harness/`](harness/)): `run.sh` (one run: config, launch, Q, W, stall check, stop rules, dump handling),
  `seq.sh` (one run at a time; no start at/after 13:15 or with a STOP file), `client.py` (schema, settings read-back,
  4 bound data clients, poison modes delete/once/cas), `Poll.java` (JMX 1 s), `hprofhist.py` (dump histogram),
  `analyze.py` + `summary.py` (per-run readings), `excerpt.sh` (the excerpts in [`logs/`](logs/)). Adapted from R22's.
- **Resolved configuration, read back from `system_views.settings` in every run (identical in all 19 runs apart from the
  heap-derived values, which scale with the heap; no mismatch with §2.3):** `memtable_allocation_type heap_buffers`, table memtable default (`SkipListMemtable`),
  `memtable_heap_space` = heap/4 (512 / 1,024 / 2,048 / 3,968 MiB at 2,048 / 4,096 / 8,192 / 15,872 MiB),
  `memtable_cleanup_threshold 0.33333334`, `memtable_flush_writers 2`, `concurrent_writes 32`, `write_request_timeout
  2000ms`, `native_transport_timeout 12s`, `native_transport_max_threads 128`, `native_transport_max_request_data_in_flight`
  214,748,364 B (heap/10 at 2 GiB) / per IP 53,687,091 B, `native_transport_max_frame_size 16MiB`, `max_mutation_size
  16384KiB`, `max_value_size 256MiB`, `commitlog_segment_size 32MiB`, `commitlog_total_space 8192MiB`,
  `native_transport_rate_limiting_enabled false`, `storage_compatibility_mode CASSANDRA_4`, `disk_failure_policy stop`,
  `commit_failure_policy stop`, column-value-size guardrails unset, table `memtable_flush_period_in_ms 0`, STCS.
- **JVM (resolved, from the command line and `VM.flags`):** `-Xms=-Xmx=<H>`, G1, `G1HeapRegionSize=16m`, `-ea`,
  `HeapDumpOnOutOfMemoryError`, `-XX:OnOutOfMemoryError="kill -9 %p"`, **`MaxDirectMemorySize=15872M`** in every run
  (`cassandra-env.sh` derives it from RAM, not from the hand-set heap), `ParallelGCThreads=40` and `ConcGCThreads=40`
  (set by `cassandra-env.sh` from the host's CPU count; the JVM itself is pinned to 8 CPUs 24–31).
- **Config diff** (`logs/<run>/conf.diff`): cluster name, ports 7720/7721/9752/JMX 7809, data/commitlog/hints/caches/cdc
  directories on `/dev/shm/u15/<run>/`, the GC-log line. No capacity setting changed.
- **Client addresses** (E5, checked at the stall check in every run via `system_views.clients`): 127.0.0.2–.5 two
  connections each (data), 127.0.0.1 four (poison/control connections).
- **Deviations from §2:** amendments A1 (K for D1+D2 from the pool's log lines; the JMX gauge covers only the current
  memtable) and A2 (one kept dump), §2.9, both before T1. Otherwise as frozen: same budgets, rates, sizes, stop rules,
  drop order not needed (every planned run, including the optional ones, ended by 10:03).

### 3.2 Shakedown `shake` (T, 2,048 MiB, W 40 s; not a reading)

Poison accepted (12 ok before the stall), two `MEMTABLE_LIMIT` flushes of `u15.t` at W+4.9 and W+7.9, each followed by
the 70,000-B `AssertionError`; stall check passed at W+30 (32 parked); heap OOM ≈ W+43 (after the clients stopped at W+40;
the backlog was already queued). MBean names all resolved; the `AllMemtablesOnHeapDataSize` finding led to A1.

### 3.3 Arm T (unmodified build, 70,000-B poison 1/s), 2,048 MiB ×3 — the claimed failure

| Run (start) | 2 failed flushes: switch at W+, `Usage` (MiB) | pool log at 2nd trigger | applied flat from | stall check W+30 (Δapplied/10 s, Δissued, MutationStage active, parked in `SubAllocator.allocate`) | K_D1+D2 (A1) | backlog peak, slope first 20 s | MutationStage pending max / NTR active max | 1st Full GC; Old after Full GC | max STW / 60 s | commit log | **endpoint** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T1 (08:23) | 4.9, 7.9; 171.17 + 171.17 | used 0.67, live 0.33, flushing 0.33 | W+11 | 0, 480, 32, 32 (31 MutationStage + 1 NTR) | 511.5 MiB | 1,285; 48.0/s | 1,299 / 100 | W+29.2; 1,921 MiB | 11.5 % | 608 MiB | **heap OOM, node dead W+44.9** |
| T2 (08:25) | 4.4, 8.4; 172.17 + 171.17 | 0.67, 0.33, 0.34 | W+11 | 0, 480, 32, 32 (31 + 1) | 510.5 MiB | 1,239; 48.0/s | 1,261 / 100 | W+30.0; 1,917 MiB | 18.5 % | 608 MiB | **heap OOM, W+49.0** |
| T3 (08:27) | 5.0, 8.0; 172.17 + 171.17 | 0.67, 0.33, 0.34 | W+11 | 0, 480, 32, 32 (31 + 1) | 510.5 MiB | 1,273; 48.0/s | 1,280 / 100 | W+31.0; 1,914 MiB | 8.2 % | 608 MiB | **heap OOM, W+42.7** |

- **Flush failure, every T run:** `system.log` shows exactly two `Enqueuing flush of u15.t, Reason: MEMTABLE_LIMIT`, each
  followed by `Completed flushing …/u15/t-…/nb-N-big-Data.db (171 MiB)` and then, on `MemtablePostFlush`,
  `java.lang.AssertionError: Attempted serializing to buffer exceeded maximum of 65535 bytes: 70000` at
  `ByteBufferUtil.writeWithShortLength(ByteBufferUtil.java:366)` ← `StatsMetadata$StatsMetadataSerializer.serialize
  (StatsMetadata.java:436)` ← … ← `ColumnFamilyStore$Flush.flushMemtable(:1334)` ← `Flush.run(:1256)`
  ([`logs/T1/assertion-stack.txt`](logs/T1/assertion-stack.txt)). The `Flushing largest` lines read flushing 0.00 then
  0.33/0.34 (the first poisoned memtable still counted), and **no third flush of `u15.t` was ever enqueued** (the cleaner
  could not fire). The node stayed up after each failure; the poison client got 12 `ok` before the stall.
- **Stall:** applied writes of `u15.t` (`WriteLatency` count) froze at 523 from W+11 s to death; at W+30 all 32
  MutationStage permits were held by threads parked in `MemtableAllocator$SubAllocator.allocate(MemtableAllocator.java:195)`
  → `WaitQueue…await` (stack: `BTreePartitionUpdater.insert` → `BTreeRow.clone` → `SlabAllocator.allocate`;
  [`logs/T1/stallcheck-parked.txt`](logs/T1/stallcheck-parked.txt)); one of them a request thread running the write
  inline.
- **Clients:** offered 48/s; issued 1,945 / 1,960 / 1,954 (capped 283 / 460 / 174 slots: the client's 32-outstanding limit
  once requests waited the 2 s timeout), so arrivals stayed ≈ 85–90 % of offered (> 50 %: not throttled). Before the
  stall 511 ok per run (p50 ≈ 55 ms); after it every data write ended `WriteTimeout` (1,273 / 1,305 / 1,301; server
  `Write Timeouts` 1,235 / 1,193 / 1,214) until death; the 142–161 "errors" per run are all connection losses at or after
  the node's death (none earlier than death − 1 s).
- **Initiating failure (V5):** `stdout.txt`: `java.lang.OutOfMemoryError: Java heap space` → `Dumping heap to
  /dev/shm/u15/dump-T1/…hprof … Heap dump file created [2,068,086,004 bytes in 4.6 secs]` → `# -XX:OnOutOfMemoryError="kill
  -9 %p"` (T2: 2,047,912,539 B; T3: 2,060,993,907 B) ([`logs/T1/stdout-oom.txt`](logs/T1/stdout-oom.txt)). As in R22,
  HotSpot's own handler kills the JVM before Cassandra logs a stack, so the throwing thread is not recorded; the GC log
  before it shows back-to-back `Pause Full (G1 Evacuation Pause)` (T1: 100 of them) leaving 1,914–1,921 MiB of 2,048 MiB
  ([`logs/T1/gc-pauses-last.txt`](logs/T1/gc-pauses-last.txt)). Only the shakedown's `system.log` also caught a
  JVMStabilityInspector OOM line (`Native-Transport-Requests-97`).
- **Dumps (`hprofhist.py`, shallow sizes; [`logs/T1/dump-hist.txt`](logs/T1/dump-hist.txt)):**

  | Run | shallow total | `byte[]` of exactly 1,048,576 B | `StorageProxy$4` (queued/parked local writes) | `Mutation` / `PartitionUpdate` | U_D3 = `StorageProxy$4` × 1 MiB, share of heap | U_D1+D2 = (1 MiB arrays − `StorageProxy$4`) × 1 MiB vs K (A1) | `SkipListMemtable` (L0: 49) | 70,000-B `byte[]` |
  |---|---|---|---|---|---|---|---|---|
  | T1 | 1,940 MiB | 1,852 | 1,354 | 1,356 / 1,356 | 1,354 MiB, 69.8 % | 498 vs 511.5 MiB (0.97) | 51 | 32 |
  | T2 | 1,921 MiB | 1,847 | 1,347 | 1,347 / 1,347 | 1,347 MiB, 70.1 % | 500 vs 510.5 MiB (0.98) | 51 | 32 |
  | T3 | 1,934 MiB | 1,845 | 1,353 | 1,353 / 1,353 | 1,353 MiB, 70.0 % | 492 vs 510.5 MiB (0.96) | 51 | 32 |

  The 1 MiB values outside the queue (≈ 3 × 166) are the three `u15.t` memtables' cells: the two pinned ones and the live
  one, which is why `SkipListMemtable` rose from 49 to 51 (two new memtables for `u15.t`, none discarded). The queued
  writes (`StorageProxy$4`, i.e. `LocalMutationRunnable`s on the MutationStage SEP queue, each holding one `Mutation` with
  its fresh 1 MiB `byte[]`) are the largest holder, ≈ 70 % of the heap; no counter covers them (K for D3: none). The T1
  dump is kept: `pc72:/mydata/s4/u15/T1/cassandra-1795267405-pid235973.hprof` (2.0 GB); the others were read and deleted.

### 3.4 Arm C (65,000-B poison, unmodified build) and arm I (70,000-B poison, patched build), 2,048 MiB, W_C = 300 s

W_C fixed after T3 as min(600, max(300, ⌈2 × 49.0⌉)) = **300 s**.

| Run (start) | `u15.t` flushes enqueued / completed / `AssertionError` | stall check W+30 | applied writes/s over W | data issued / ok / timeouts / errors; ok p99 | poison ok / `InvalidRequest` | backlog peak | MutationStage active / pending max | Old max after GC | max STW / 60 s | L1 live heap | endpoint |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C1 (08:30) | 84 / 84 / 0 | no (Δapplied 490, active 0, 0 parked) | 48.2 | 14,356 / 14,356 / 0 / 0; 101 ms | 300 / 0 | 0 | 5 / 1 | 222 MiB | 1.5 % | 193 MiB | none (W_C reached) |
| I1 (08:36) | 84 / 84 / 0 | no (480, 1, 0) | 47.2 | 14,356 / 14,356 / 0 / 0; 84 ms | 0 / **300** | 0 | 1 / 0 | 246 MiB | 1.7 % | 216 MiB | none |
| C2 (08:43) | 84 / 84 / 0 | no (490, 0, 0) | 48.2 | 14,352 / 14,352 / 0 / 0; 72 ms | 299 / 0 | 0 | 4 / 1 | 264 MiB | 1.5 % | 182 MiB | none |
| I2 (08:49) | 84 / 84 / 0 | no (480, 0, 0) | 47.2 | 14,404 / 14,404 / 0 / 0; 84 ms | 0 / **301** | 32 (one sample) | 2 / 1 | 266 MiB | 1.4 % | 205 MiB | none |
| C3 (08:55) | 84 / 84 / 0 | no (440, 0, 0) | 48.2 | 14,402 / 14,402 / 0 / 0; 95 ms | 300 / 0 | 22 (one sample) | 3 / 1 | 188 MiB | 1.6 % | 72 MiB | none |
| I3 (09:02) | 84 / 84 / 0 | no (478, 0, 0) | 47.2 | 14,356 / 14,356 / 0 / 0; 84 ms | 0 / **300** | 0 | 2 / 1 | 217 MiB | 1.4 % | 217 MiB | none |

- C: the 65,000-B bound (the memtable's smallest start bound in every flush, as T's) serializes; every one of the 84
  `MEMTABLE_LIMIT` flushes completed (one every 3.6 s; `Flushing largest` always "flushing 0.00"), K_live saw-tooth ≤
  170 MiB, commit log ≤ 0.9–1.0 GiB. C's 48.2 applied/s = 47.2 data + 1 poison DELETE per second.
- I: every 70,000-B poison was refused at statement execution with `InvalidRequest: Key length of 70000 is longer than
  maximum of 65535` (the row path's own message); the data stream was applied in full at 47.2/s, the same useful
  throughput as C (no useful work refused). Full GCs in C/I are the L0 histogram's forced GC and an occasional
  evacuation-failure fallback with small live sets (≤ 266 MiB after).

### 3.5 Budget search (arm T ×1 at 4,096 and 8,192 MiB; ×3 at 15,872 MiB, the largest budget)

| Run (start) | H / L | failed flushes: switch W+; `Usage` | applied flat from | stall check (W+) | K_D1+D2 (A1) vs L | backlog peak; slope first 20 s / last 120 s | pending max | 1st Full GC; Old after | max STW / 60 s | commit log | node death (heap OOM) | dump: shallow, 1 MiB `byte[]`, `StorageProxy$4`, U_D1+D2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| B4096 (09:08) | 4,096 / 1,024 | 7.9, 14.9; 342.3 ×2 | W+21 | yes (W+60) | 1,023.8 | 2,690; 48.0 / 39.1 | 2,714 | W+66.3; 3,835 MiB | 17.7 % | 1,152 MiB | **W+89.9** | 3,854 MiB, 3,756, 2,782, 974 MiB |
| B8192 (09:11) | 8,192 / 2,048 | 14.9, 29.9; 684.5 + 683.5 | W+43 | yes (W+90) | 2,046.4 | 5,496; 48.0 / 47.7 | 5,617 | W+143.9; 7,697 MiB | 40.4 % | 2,208 MiB | **W+184.9** | 7,715 MiB, 7,602, 5,674, 1,928 MiB |
| B15872 (09:15) | 15,872 / 3,968 | 28.9, 55.9; 1,324.0 + 1,323.0 | W+83 | yes (W+150) | 3,965.9 | 10,727; 48.0 / 47.9 | 10,977 | W+288.2; 14,925 MiB | 43.9 % | 4,160 MiB | **W+340.3** | 14,949 MiB, 14,802, 11,065, 3,737 MiB |
| B15872b (09:22) | 15,872 / 3,968 | 28.9, 55.9; 1,323.0 + 1,324.0 | W+83 | yes (W+150) | 3,966.9 | 10,804; 48.0 / 47.9 | 10,982 | W+288.2; 14,920 MiB | 73.5 % | 4,160 MiB | **W+358.7** | 14,936 MiB, 14,798, 11,062, 3,736 MiB |
| B15872c (09:30) | 15,872 / 3,968 | 28.9, 55.9; 1,323.0 ×2 | W+83 | yes (W+150) | 3,967.9 | 10,805; 48.0 / 47.7 | 11,022 | W+287.7; 14,926 MiB | 62.2 % | 4,160 MiB | **W+352.9** | 14,939 MiB, 14,803, 11,073, 3,730 MiB |

Every budget run had exactly two failed flushes (70,000-B `AssertionError` ×2), no third `u15.t` flush, 32 threads
parked at its stall check, `MaxDirectMemorySize` 15,872 MiB, and ended in `java.lang.OutOfMemoryError: Java heap space`
+ heap dump (4.08 / 8.13 / 15.72 / 15.70 / 15.71 GB) + `kill -9`. At 15,872 MiB (what `cassandra-env.sh` resolves on this
125 GiB node) the queued local writes are 11,062–11,073 MiB of a 14.9 GiB live heap (74 %); the commit log (4.2 GiB) stayed
under its 8 GiB cap, so no commit-log-driven flush fired. GC service loss (≥ 90 % STW over 60 s) was **not** reached
before the OOM in any run (max 73.5 %). U_D1+D2 / K = 0.94 at 15,872 MiB (slab-region and object overhead counted by
the pool but not in the 1 MiB arrays). Dumps above 4 GiB were read in place and deleted (A2).

### 3.6 Dose arm D1 (one 70,000-B poison at W+0, unmodified build, 2,048 MiB, W_C 300 s) ×3

| Run (start) | `u15.t` flushes enqueued / completed / `AssertionError` | `Flushing largest` after the failure | stall check W+30 | applied/s | data issued / ok / timeouts; ok p99 | backlog peak | Old max after GC | L1 live heap | endpoint |
|---|---|---|---|---|---|---|---|---|---|
| D1a (09:37) | 84 / 84 / 1 | used 0.67, flushing 0.33 in 82/82 later triggers | no (Δapplied 480) | 47.2 | 14,354 / 14,354 / 0; 79 ms | 0 | 409 MiB | 384 MiB | none (W_C) |
| D1b (09:43) | 84 / 84 / 1 | 0.67 / 0.33 in 82/82 | no (480) | 47.2 | 14,354 / 14,354 / 0; 88 ms | 0 | 427 MiB | 372 MiB | none |
| D1c (09:50) | 84 / 84 / 1 | 0.67 / 0.33 in 82/82 | no (480) | 47.4 | 14,352 / 14,352 / 0; 98 ms | 0 | 362 MiB | 337 MiB | none |

One accepted poison fails the first flush (the single `AssertionError`), and that memtable is never released: every
later cleaner trigger reads "flushing 0.33" and fires at used 0.67 instead of 0.33 (the higher threshold `reclaiming +
L/3` of §2.1 step 4), and the live heap stays ≈ 150–200 MiB above C's (L1 337–384 vs 72–193 MiB). With one third of the
pool pinned the cleaner can still fire, so writes continue: **0/3 stall, 0/3 OOM** — the stall needs two.

### 3.7 Probe P-CAS (70,000-B `INSERT … IF NOT EXISTS` 1/s, unmodified build, 2,048 MiB, W_C 300 s) ×1 (not counted)

PCAS (09:56): all 300 `INSERT INTO u15.t (pk, ck, v) VALUES (0, <70,000 × 0x00>, 0x00) IF NOT EXISTS` answered without
error (the first one applied; the later ones found the row and wrote nothing). So under the shipped `heap_buffers` the
conditional route **also skips the 64 KiB check and is acknowledged** (stage 4 had seen it only under `offheap_objects`,
where it failed earlier at `NativeClustering.java:50`). The first `u15.t` flush then failed with the same
`AssertionError … 65535 bytes: 70000` at `StatsMetadata.java:436`; the 84 later flushes completed with "flushing
0.33/0.34" standing, i.e. one pinned memtable, as in D1. No stall (Δapplied 480 at W+30), 14,404/14,404 data writes ok,
Old max 436 MiB, no OOM in 300 s. Because `IF NOT EXISTS` writes the oversized row only once per partition key, this
probe poisoned one memtable; a CAS stream with a fresh partition key per statement would poison every memtable like the
DELETE (not run). (The "backlog 299" in its `analysis.json` is an artifact: not-applied CAS answers count as poison `ok`
but add no `WriteLatency`.)

**Side note (all runs with a failed flush):** right after each `AssertionError`, `MemtablePostFlush` also logs
`java.lang.NullPointerException` at `MemtableCleanerThread$Clean.apply(MemtableCleanerThread.java:97)`: the cleaner's
callback unboxes a null `Boolean res` when the flush future fails, so its re-signal and its own error log are skipped.
It does not decide anything here (later allocations re-trigger the cleaner, as D1 shows; with two pinned memtables
`needsCleaning()` is false anyway), but it is a second defect on the same failure path.

### 3.8 Logs

Full logs per run on `pc72:/mydata/s4/u15/<run>/` (`logs/system.log`, `debug.log`, `stdout.txt`, `gc.log*`, `poll.log`,
`rss.log`, client CSVs, `stallcheck-threads.txt`, `hist/`, `analysis.json`); the sequence log
`pc72:/mydata/s4/u15/seq.log` (copy: [`logs/seq.log`](logs/seq.log)). Excerpts per run in [`logs/<run>/`](logs/) (driver log, settings, conf diff, analysis,
`system.log` lines for `u15.t`, the first `AssertionError` stack, OOM lines from `stdout.txt`, poll rows of W, last GC
pauses, the parked-thread list, dump histogram).

**End of stage 2 (10:04):** no `CassandraDaemon`, poller, client or harness process left on `pc72` (`pgrep`), no
leftover `systemd-run` scope, `/dev/shm` empty.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** (unprotected accumulation; the stall source
is a validation bypass plus a release defect). Largest budget with OOM: **15,872 MiB, 3/3** (the heap `cassandra-env.sh`
resolves on this 125 GiB node; nothing larger was in scope); also 2,048 MiB 3/3, 4,096 MiB 1/1, 8,192 MiB 1/1.

**Reason.** On the unmodified 5.0.9 build with every capacity setting at its default, a slice `DELETE … WHERE pk = 0 AND ck
> <70,000 B>` sent once a second was accepted and acknowledged (12 `ok` before the stall), and each of the first two
`MEMTABLE_LIMIT` flushes of the table then failed on `MemtablePostFlush` with `AssertionError: Attempted serializing to
buffer exceeded maximum of 65535 bytes: 70000` at `StatsMetadata.java:436`. Neither memtable was released: the pool's own
lines read flushing 0.33 after the first and used 0.67 after the second, K_D1+D2 = 510.5–511.5 MiB of the 512 MiB pool
at 2 GiB (3,966–3,968 of 3,968 MiB at 15.5 GiB), and no third flush was ever enqueued. Applied writes froze at W+11 s
(W+83 s at 15.5 GiB) with all 32 MutationStage permits parked in `MemtableAllocator$SubAllocator.allocate:195`, while
the 1 MiB data writes kept arriving at 48/s and queued on the MutationStage SEP queue (backlog slope 48.0/s, pending
1,261–1,299 at 2 GiB and 10,977–11,022 at 15.5 GiB). The JVM died of `java.lang.OutOfMemoryError: Java heap space` in
**3/3 runs at 2,048 MiB (W+42.7–49.0 s)** and **3/3 at 15,872 MiB (W+340–359 s)**; the dumps show 1,347–1,354 (resp.
11,062–11,073) queued `StorageProxy$4` local writes, each with its `Mutation` and 1 MiB `byte[]`, i.e. 70 % (74 %) of the
live heap, beside the three `u15.t` memtables (≈ 500 MiB of 1 MiB values against K = 511 MiB). The matched control C
(same statement, rate and data, bound 65,000 B) completed all 84 flushes in 3/3 runs over 300 s with no stall, zero
timeouts and Old ≤ 264 MiB after GC; the intervention I (the slice-bound and CAS `validate()` restored) refused every
poison statement (300 / 301 / 300) and applied the data stream in full (47.2/s, as C) with no OOM in 3/3. The dose arm D1 (one
poison) pinned one memtable for good but did not stall (0/3 stall, 0/3 OOM; the 83 flushes after the one failure all completed, each fired at used 0.67 with flushing 0.33
standing), confirming that two pinned memtables are needed.

### 4.1 Per-condition status

| Condition | Runs | Endpoint | n/N |
|---|---|---|---|
| T, 2,048 MiB (main) | T1–T3 | Java heap OOM at W+42.7 / 44.9 / 49.0 s | **3/3** |
| C, 2,048 MiB (matched control, 65,000-B bound) | C1–C3 | none in 300 s | 0/3 |
| I, 2,048 MiB (patched build) | I1–I3 | none in 300 s; 300/301/300 poisons refused | 0/3 |
| T, 4,096 MiB | B4096 | Java heap OOM at W+89.9 s | 1/1 |
| T, 8,192 MiB | B8192 | Java heap OOM at W+184.9 s | 1/1 |
| T, 15,872 MiB (largest; `cassandra-env.sh` default for the node) | B15872, b, c | Java heap OOM at W+340.3 / 358.7 / 352.9 s | **3/3** |
| D1, 2,048 MiB (one poison) | D1a–c | one failed flush, one memtable pinned for good, no stall, no OOM in 300 s | 0/3 |
| P-CAS probe, 2,048 MiB | PCAS | the 70,000-B CAS insert accepted and poisons one flush (as D1); no stall, no OOM in 300 s | (not counted) |

### 4.2 V1–V7

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 Repetition | ≥ 3 runs from clean starts | T1–T3 3/3 at 2,048 MiB; B15872 ×3 3/3 at 15,872 MiB; every run on a fresh `/dev/shm/u15/<run>` (data, commit log, hints, caches; the poisoned commit log never replayed) | yes |
| V2 Matched control | nearest surviving control ×3, same budget/build | C1–C3 (65,000-B bound): 0/3, 84/84 flushes completed, no stall | yes |
| V3 Measurement | U independent of K per domain | D3: dump `StorageProxy$4` / `Mutation` / 1 MiB `byte[]` counts and the client-side backlog (no K exists); D1+D2: 1 MiB values outside the queue (≈ 492–500 MiB) vs the pool's own K (510.5–511.5 MiB, A1), `SkipListMemtable` +2 | yes |
| V4 Intervention | removes the endpoint ≥ 3 runs at matched load | I1–I3 0/3, the poison refused with the row path's own error, useful throughput = C's | yes |
| V5 Initiating failure | first error + dump showing the holder | `java.lang.OutOfMemoryError: Java heap space` + heap dump + `kill -9` in `stdout.txt` (every T run), GC log of back-to-back Full GCs at 1,914–1,921 / 2,048 MiB, dumps as §3.3/§3.5; the two flush `AssertionError`s with stack precede every stall. The throwing thread is not recorded (HotSpot's `OnOutOfMemoryError` kill, as in R22) | yes (thread name missing, stated) |
| V6 Default constraints | all constraints of the protection map at defaults | read back per run (§3.1): `heap_buffers`, `memtable_heap_space` heap/4, cleanup 0.33333334, 2 flush writers, `concurrent_writes 32`, 2 s write timeout, 128 NTR threads, in-flight heap/10 and heap/40, `max_mutation_size` 16 MiB, `commitlog_total_space` 8 GiB, `storage_compatibility_mode CASSANDRA_4`, `-ea` as shipped | yes |
| V7 Acceptable budget | ≥ 512 MiB standing rule; largest budget searched | 2,048 MiB (ideal) and up to 15,872 MiB = `cassandra-env.sh`'s own heap for this node; `MaxDirectMemorySize` 15,872 MiB; no container limit | yes |

Conditions label `deployment`: E1–E5 are environment or instrumentation (single node on loopback, tmpfs data, CPU pinning,
GC log, client source addresses); no Byteman, no patch outside arm I, no raised timeout.

### 4.3 Classification and limits

- **Direction:** unprotected accumulation (holder D3, the MutationStage local-write queue: no count or byte bound, and
  the 2 s write timeout releases only the request side, never the queued runnable). The stall source is (a) a validation
  bypass (`ModificationStatement.addUpdates` slice branch, `:762-787`, never calls `validate()` on slice bounds) and
  (b) a release defect inside a counted pool (`Flush.run` records the failure and skips `replaceFlushed`/`reclaim`, so the
  memtable's bytes stay in `reclaiming` for good; with two, `reclaiming + ⌈L/3⌉ > L` and the cleaner can never fire). The
  pool itself held (U ≈ K ≤ C), as §2.1 predicted: not a pool bypass.
- **Interpretation:** suspected implementation defect on the trigger (the 64 KiB clustering check exists and is applied
  on the row path; CASSANDRA-11882 added it for this assertion) and on the failed-flush release; the unbounded stage queue
  is the known by-design shape of CASSANDRA-12689/20084. JIRA (stage 1, read only): no report of this trigger.
- **Limits:** the throwing thread of the OOM is not recorded; U for D1+D2 is by subtraction (1 MiB arrays not in the
  queue), not by a reachability walk; one client host with four source addresses stands for several application
  servers; data on tmpfs (a spinning disk would only slow C's flush cycle); 4,096 and 8,192 MiB ran once each. Not tested:
  the restart / commit-log replay leg (§1.2; a restart would replay the poison and, by the same assertion, presumably fail
  again) and the disk-only commit-log growth. GC service loss (≥ 90 % STW over 60 s) was not reached before the OOM (max
  73.5 %), so the endpoint is the OOM itself.
- **Clue patterns:** covered by CP-10 (a path that skips the limit: the slice branch), CP-14 (release missing on the
  failed-flush path) and CP-5 (accepting queue behind stalled consumers); no new pattern.

### 4.4 Left on the node

`pc72:/mydata/s4/u15/` (2.7 GB: the T1 heap dump 2.0 GB, the two build trees 286 MB + 419 MB, harness, run logs ≈ 3–4 MB
per run); `/dev/shm/u15` removed; no process left running (checked at the end, §3.8).
