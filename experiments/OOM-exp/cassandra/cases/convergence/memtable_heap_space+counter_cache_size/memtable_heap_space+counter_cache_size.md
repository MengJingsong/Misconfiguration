# memtable_heap_space + counter_cache_size — memtable pool and counter cache share a 1 GiB heap

**Direction:** convergence · standing-pool, tagged **mixed** (the counter cache's physical bytes exceed its own
`counter_cache_size` at the OOM while its counter reads ≈ 63%: U > C, K ≤ C). **Regime:** custom capacities.
**Source:** Cassandra 5.0.9 (source tree `b796bcfd`). **Runs:** run 1 (2026-11-02, pre-protocol, 40-core node),
R3 recheck (2026-11-11, `apt149`); per-run records verbatim in [`history.md`](history.md). **Consolidated:** 2026-11-11.

| Condition | Status (protocol *Verification status*) |
|---|---|
| `memtable_heap_space=550MiB` + `counter_cache_size=300MiB`, `-Xmx1024M`, concurrent `write` + `counter_write` (recheck on `apt149`) | **`verified-OOM · diagnostic`** (mixed) |
| Same condition, run 1 on the 40-core node (14 caught throws, JVM survived) | superseded by the recheck; kept in [`history.md`](history.md#run-1) |

## Summary

- **Conclusion:** with the memtable pool at 550 MiB and the counter cache at 300 MiB in a 1 GiB heap, running a plain
  write load and a counter write load at the same time ends in a **Java heap `OutOfMemoryError` 3/3**, ≈ 5 min into
  the load; the JVM then spends ≈ 6.5 min in back-to-back Full GCs (≈ 100% stop-the-world) until the shipped
  `-XX:OnOutOfMemoryError=kill -9 %p` kills it after the heap dump. Either load alone (3/3 each) and the same pair with
  `counter_cache_size=50MiB` (3/3) finish with no OOM. The result needs a tightened 1 GiB heap and
  `memtable_cleanup_threshold: 0.99`, so it is **diagnostic**.
- **Root cause:** each pool enforces only its own limit: the memtable pool blocks writers at 550 MiB of charged
  buffers, and Caffeine evicts the counter cache at 300 MiB of *weigher* bytes. Nothing adds the two up against
  `-Xmx`. In addition, the counter-cache weigher counts only the key and value objects, not Caffeine's node, the map
  node, the hash table or the frequency sketch. Real heap is ≈ 1.75× the counted size, so at the OOM the cache held
  327–337 MiB of heap while reporting 185–190 MiB. Memtable ≈ 535 MiB plus cache ≈ 335 MiB plus ≈ 70 MiB of other
  live data filled 939–943 MiB of the 1024 MiB heap.
- **Causal test:** lowering `counter_cache_size` to 50 MiB under the same load removes the OOM 3/3. Peak live data
  after a Full GC is 715–719 MiB (70%), and throughput is as high as the converge arms reached before their OOM.
- **Interpretation:** a configuration-sizing/validation gap (no check that the pools fit the heap together). It is
  aggravated by an accounting omission in the counter cache. Under the yaml text (“size of the cache”), that
  omission is a documented-unit mismatch rather than a counter bug.

## 1. Constraints, contract, protection map

| Field | Memtable pool (M) | Counter cache (C) |
|---|---|---|
| Control | `memtable_heap_space` → `MemtablePool.SubPool.tryAllocate()` (`allocated + size > limit` → false, `MemtablePool.java:151–161`); writers block on `hasRoom()` (`MemtableAllocator.java:169–195`); `HeapPool.Allocator.allocate()` charges `onHeap()` then `ByteBuffer.allocate(size)` (`HeapPool.java:52–55`) | `counter_cache_size` → `CacheService.initCounterCache()` → `CaffeineCache.create(capacity)`: `maximumWeight(capacity)`, weigher = `key.unsharedHeapSize() + value.unsharedHeapSize()` (`CacheService.java:172–181`, `CaffeineCache.java:51–69`) |
| Contract C | 550 MiB of charged on-heap memtable bytes; flush at `memtable_cleanup_threshold` (0.99 here) releases it | 300 MiB of weigher bytes: `CounterCacheKey` shell + its two `byte[]` (`CounterCacheKey.java:152–157`) + `ClockAndCount` shell (`ClockAndCount.java:46–48`) = 120 B/entry here (2,621,440 entries at 300 MiB) |
| Not counted | small object overhead outside the charged buffers (measured U ≈ K) | Caffeine node (`PSMW`, 40 B), `ConcurrentHashMap$Node` (32 B), the hash table and frequency sketch (16 MiB each at ≈ 1.6 M entries, each just over one 16 MiB region, so 2 humongous regions each) |
| K (counter) | pool on-heap at flush, from `Enqueuing flush of … on-heap` | `nodetool info` → `Counter Cache : entries, size` |
| U (physical) | dump walk from each memtable's `partitions` map (rows, cells, `HeapByteBuffer` + `byte[]`, keys, map nodes) | dump walk from the counter cache's `SSMW` instance (nodes, map, keys, values, arrays, sketch); in alone arms `GC.class_histogram` |
| Lifetime | standing between flushes, refills continuously under the write load | standing; does not self-reclaim, LRU eviction at the weight cap |
| Budget | Java heap `-Xms1024M -Xmx1024M` (both) | |

Other live data (not bounded by either control): ≈ 55 MiB idle baseline plus in-flight requests of 320 client
threads, counter-mutation locks, compaction. Measured as live − U_M − U_C = 68–80 MiB at the OOM.

**Labels.** Capacities custom (`memtable_heap_space=550MiB`, `counter_cache_size=300MiB`); budget deliberately
tightened (1 GiB); supporting deviations: `memtable_cleanup_threshold: 0.99` (needed for the pool to reach its limit),
`memtable_allocation_type: unslabbed_heap_buffers` (an accepted value; it routes memtable data to the on-heap pool);
everything else shipped defaults, including `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError=kill -9 %p` →
**diagnostic**. Environment (recheck): `apt149` (Dell r320, 1 × E5-2450 8C/16T, 15.5 GiB, 8 GiB swap,
Ubuntu 22.04.2, kernel 5.15.0-198, cgroup v2), OpenJDK 11.0.33; run 1 was a 40-core / 251 GiB node with OpenJDK 11.0.32.1.

**Feasibility (Σ contract + baseline):** 550 + 300 + 57 = 907 MiB < 1024 MiB. If every pool held to its contract in
physical bytes, the pair would fit with ≈ 117 MiB to spare. The OOM therefore depends on bytes outside both
contracts: the counter cache's uncounted overhead and the unbounded other live data.

## 2. Verification design

The dated design was written before any reading on `apt149`, and the endpoint-evidence amendment was written before
converge_r3 and the intervention arms (both verbatim in [`history.md`](history.md#recheck-design)). Rule: campaign-plan
row R3 (pre-protocol recheck: same build, settings, workloads and harness, each arm ×3 from clean starts).

- **Build:** `~/cassandra-c1` on `apt149` (clean `cassandra-5.0.9`, tree `b796bcfd`), `cp -a` to
  `/mydata/oom-recheck/R3/cassandra`; all data, logs and dumps on local `/mydata`.
- **Harness:** run 1's `oom-run.sh` with minimal edits ([diff](recheck-2026-11-11/oom-run.sh.diff)):
  paths, pinned env (`MAX_HEAP_SIZE=1024M`; `HEAP_NEWSIZE`/`JVM_OPTS`/`JVM_EXTRA_OPTS` unset;
  `CASSANDRA_HEAPDUMP_DIR` per arm on `/mydata`), more heap samples, and added K readings (counter cache every 30 s,
  memtable flush lines), `VM.flags`, `GC.class_histogram` at the end, node logs incl. `gc.log`. Runner
  [`run-batch.sh`](recheck-2026-11-11/run-batch.sh), batch lists in [`logs/batch*.txt`](recheck-2026-11-11/logs/).
- **Arms:** `M_alone` (550 / 1 MiB, `write`), `C_alone` (32 / 300 MiB, `counter_write`), `converge` (550 / 300,
  both concurrent), `interv_C50` (550 / 50, both concurrent). Workloads unchanged:
  `cassandra-stress write n=3000000 no-warmup -col 'size=FIXED(1024)' -rate threads=256` and
  `cassandra-stress counter_write n=600000 no-warmup -rate threads=64`.
- **Endpoint (fixed):** a Java heap `OutOfMemoryError` thrown by the Cassandra JVM. Evidence: the
  `HeapDumpOnOutOfMemoryError` file (HotSpot creates it only in `report_java_out_of_memory()`) plus the GC log, and/or a
  `system.log` entry. The JVM's fate is recorded but is not part of the endpoint. `CassandraDaemon` closes stdout after
  start-up (`CassandraDaemon.java:738–739`), so HotSpot's own text report is not available (amendment).
- **Instruments:** 5 s `GC.heap_info`, GC log (STW fraction, Full-GC occupancy), K readings above, end-of-arm forced GC
  and class histogram, `dmesg`. Dumps analysed with a python HPROF parser written for this
  ([`tools/hprof_histo.py`](recheck-2026-11-11/tools/hprof_histo.py): class histogram, live set from GC roots and
  class statics, bounded reachability walks per domain; shallow sizes for compressed oops) and
  [`tools/hprof_oome_thread.py`](recheck-2026-11-11/tools/hprof_oome_thread.py) (the stack of the thread that threw the
  OOM, which HotSpot marks with a leading `OutOfMemoryError.<init>` frame).
- **Budget used:** 14 arm executions (baseline, modest-load validation, 12 recheck arms) of ≤ 20; wall ≈ 2 h 10 min of
  runs (14:46–16:33 EST) within the 5 h stop.

## 3. Results

Full table: [`logs/arm-table.tsv`](recheck-2026-11-11/logs/arm-table.tsv), GC windows:
[`logs/gc-window.txt`](recheck-2026-11-11/logs/gc-window.txt); per-arm summaries, stress tails, histograms and yaml
diffs under [`recheck-2026-11-11/logs/`](recheck-2026-11-11/logs/). Full logs and dumps:
`apt149:/mydata/oom-recheck/R3/{logs,dumps,analysis}`.

### 3.1 Per arm

| Arm × rep | Outcome | Peak live (max after Full GC) | Final forced-GC used | Full GCs / best 60 s STW | Throughput (op/s), client errors |
|---|---|---|---|---|---|
| baseline | idle | — | 55.5 MiB (5%) | — | — |
| validate (n = 200k / 50k, both) | completes; pool reached 95%, cache 250k entries | 626 MiB | 311 MiB (30%) | 8 / 6% | write 7,713, counter 1,903; 0 |
| M_alone r1/r2/r3 | completes, no OOM, 0 `ERROR` | 630 / 630 / 630 MiB (61.5%) | 88 / 91 / 89 MiB (memtable just flushed) | 127–134 / 11–12% | write 7,687 / 7,180 / 7,367; 0 |
| C_alone r1/r2/r3 | completes, no OOM, 0 `ERROR`; K_C = 300 MiB (2,621,440 entries) | 663 / 659 / 663 MiB | 628.5 / 628.1 / 627.7 MiB (61%) | 26–28 / 37–40% | counter 8,821 / 8,577 / 8,609; 0 |
| **converge r1/r2/r3** | **Java heap OOM 3/3** (dump begun 317 / 295 / 315 s after load start); JVM killed by `OnOutOfMemoryError` after the dump, 3/3; no kernel OOM-kill | 991 / 992 / 992 MiB (97%) | — (JVM gone) | 922 / 816 / 962 / **100%** | before the OOM: write 5,290 / 5,410 / 5,551, counter 1,112 / 1,198 / 1,177; both clients then fail (`BusyPool`/timeouts) |
| **interv_C50 r1/r2/r3** | **no OOM 3/3**; both workloads complete; K_C = 50 MiB (436,906 entries) | 715 / 719 / 716 MiB (70%) | 469 / 700 / 546 MiB | 259–266 / 26–29% | write 5,719 / 5,726 / 5,925, counter 1,119 / 1,126 / 1,169; 0 |

`ERROR` lines in the converge and intervention arms (22–46 and 83–102) are all
`CounterMutationStage` `WriteTimeoutException` (counter lock timeouts under overload, as in run 1), except r1's two
`OutOfMemoryError` entries. Memtable K at the last flush: 545–547 MiB (99–100%) alone, 532–533 MiB (97%) converge,
536–537 MiB (98%) intervention. `dmesg`: no OOM-kill lines in any arm.

**Alone levels vs run 1:** after a forced GC the C level is 628 MiB here vs 629 MiB in run 1. The M peak after a Full
GC is 630 MiB here vs 624 MiB at run 1's end. The filed sizing still gives "≈ 61% alone, exceeds together", so no
re-sizing amendment was needed.

### 3.2 Domains at the OOM (dump analysis, V3)

| Dump | Live (from roots) | U_M (memtable walk) | K_M (last flush) | U_C (counter-cache walk) | entries → K_C (× 120 B) | Other live |
|---|---|---|---|---|---|---|
| converge_r1 | 939.1 MiB (+29.4 unreachable) | 534.7 MiB | 532.6 MiB | **336.6 MiB** | 1,663,265 → 190.3 MiB | 67.8 MiB |
| converge_r2 | 942.6 MiB (+15.7) | 535.8 MiB | 533.2 MiB | **334.9 MiB** | 1,654,010 → 189.3 MiB | 71.9 MiB |
| converge_r3 | 943.0 MiB (+15.7) | 536.0 MiB | 532.0 MiB | **327.2 MiB** | 1,611,970 → 184.5 MiB | 79.8 MiB |

([`analysis/converge_r*-hprof.txt`](recheck-2026-11-11/analysis/); no object is in both walks.) The memtable domain is
`byte[]` values (438 MB in r1), `HeapByteBuffer`, `BufferCell`, `BTreeRow`, `AtomicBTreePartition`, keys and skip-list
nodes. The counter-cache domain is two `byte[]` per entry, `PSMW` node, `CounterCacheKey`, `ClockAndCount` and
`ConcurrentHashMap$Node`, each ≈ 1.6–1.66 M instances, plus a 16 MiB `ConcurrentHashMap$Node[]` table and a 16 MiB
`long[]` frequency sketch. Per entry: 120 B counted, ≈ 192 B physical, plus the fixed 32 MiB of table and sketch.

The same ratio holds without an OOM: in `C_alone` (K_C = 300 MiB) the end histograms give U_C ≈ 505–540 MiB, ≈ 1.7–1.8×
([`logs/C_alone_r1/class-histo-final-top30.txt`](recheck-2026-11-11/logs/C_alone_r1/class-histo-final-top30.txt)). In
the intervention (K_C = 50 MiB) U_C ≈ 88 MiB.

**Classification by measurement:** memtable U_M ≤ C_M (535–536 ≤ 550 MiB, U ≈ K). Counter cache U_C > C_C
(327–337 > 300 MiB) while K_C ≤ C_C (185–190 MiB): **accounting omission**. The contracts alone (907 MiB) fit the heap;
the OOM happened at 939–943 MiB live, so it needs both domains near their limits *and* the bytes outside the contracts
(cache overhead ≈ 143–146 MiB above K_C, other live data ≈ 70 MiB). Per the rule fixed in the design this is **mixed**
(convergence of two pools with a counter-cache accounting excess), not pure convergence. Whether the pair would still
OOM if the cache's 300 MiB bounded physical bytes (≈ 900 MiB live) was not tested.

### 3.3 Initiating failure (V5)

- **First OOM, thread and stack (from the dump):** r1 and r3 — a `Native-Transport-Requests` worker (`SEPWorker`)
  executing a client write: `StorageProxy.mutate:906 → AbstractWriteResponseHandler.get:127 → throwTimeout:149`
  (allocating the `WriteTimeoutException`). r2 — a compaction thread reading an sstable
  (`UnfilteredSerializer.deserialize … ByteArrayAccessor.read:102`). See
  [`analysis/converge_r*-oome-thread.txt`](recheck-2026-11-11/analysis/).
- **Timeline (r1):** first OOM at 13:28:49 MST (the dump file is created then). Back-to-back `Pause Full (G1 Evacuation
  Pause) 991M->991M` every ≈ 0.5–0.8 s follow, ≈ 100% STW, until the `HeapDumper` safepoint runs at 13:35:19. The dump is
  written by 13:35:26, then `kill -9`. The only `system.log` entry is from an `RMI TCP Connection` thread (the harness's
  `nodetool info`) at 13:35:19, which hit the same exhausted heap
  ([`logs/converge_r1/system-log-oom-excerpt.txt`](recheck-2026-11-11/logs/converge_r1/system-log-oom-excerpt.txt),
  [`gc-log-tail.txt`](recheck-2026-11-11/logs/converge_r1/gc-log-tail.txt)). r2 and r3 are the same, with a 6.3–6.7 min
  wait and no `system.log` entry before the kill.
- The heap-dump request waited ≈ 6.5 min behind GC operations, so the JVM stayed alive and unresponsive that long after
  the first OOM. This is a likely explanation for run 1's "JVM survived" record: run 1's harness forced a GC, then ran
  `nodetool drain`/`stopdaemon` during such a window. That is not verified (run 1's node was not touched).

### 3.4 Environment differences vs run 1 (disclosed)

Resolved on `apt149` (`VM.flags`, [`logs/vm-flags.txt`](recheck-2026-11-11/logs/vm-flags.txt)):
`ParallelGCThreads=16`, `ConcGCThreads=16` (run 1: 40/40, both set by `cassandra-env.sh` to the core count);
`MaxDirectMemorySize=3982M` (run 1: 15872M; derived from RAM, irrelevant to a heap OOM); G1 with 16 MiB regions,
`G1NewSizePercent=50` (young floor 512 MiB), `G1MaxNewSizePercent=60` (`MaxNewSize` 608 MiB), `MaxGCPauseMillis=300`,
IHOP 70, `MaxTenuringThreshold=2`, `AlwaysPreTouch`; JDK 11.0.33 vs 11.0.32.1. The client runs on the same 16 threads,
so throughput is lower (write alone 7.2–7.7k op/s vs 10.0k; counter alone 8.6–8.8k vs 11.2k). The 50% young floor plus
≈ 600 MiB of standing memtable makes M_alone Full-GC heavy (127–134 Full GCs, ≤ 12% STW in any 60 s window); run 1's
GC log was not kept, so this cannot be compared. Run 1 ended in caught throws with the JVM alive; here the JVM is killed
by the shipped `OnOutOfMemoryError` handler 3/3. Both are the same endpoint (Java heap OOM thrown).

## V1–V5

| | Requirement | Evidence | Met |
|---|---|---|---|
| V1 | endpoint ≥ 3 runs from clean starts | converge r1–r3: Java heap OOM 3/3 (dumps `cassandra-1794428565`, `-1794429334`, `-1794430074`; r1 also `system.log`) | yes, 3/3 |
| V2 | nearest control ×3, no endpoint | M_alone ×3 and C_alone ×3: 0 OOM, 0 `ERROR`, 0 client errors, forced-GC used ≤ 61%, peak after Full GC ≤ 663 MiB (65%) | yes |
| V3 | U apart from K per domain | dumps r1–r3 (§3.2): U_M 535–536 vs K_M 532–533; U_C 327–337 vs K_C 185–190 MiB; C_alone histograms U_C ≈ 505–540 at K_C 300 | yes |
| V4 | intervention ×3 | `counter_cache_size=50MiB`, same workloads: no OOM 3/3, peak after Full GC 715–719 MiB (70%, predicted ≈ 720), throughput ≥ converge's pre-OOM rate | yes |
| V5 | first error + holder at failure | OOM-throwing thread stacks from the dumps (§3.3); dump histograms with both holders (§3.2) | yes |

## 4. Conclusion and limits

The two pools converge on a 1 GiB heap: each stays within its own limit when alone, together they reach a Java heap OOM
3/3, and shrinking one of them removes it 3/3 at the same load. The counter cache adds a real accounting gap: its limit
counts ≈ 57% of the heap it uses at the OOM (120 of ≈ 192 B per entry, and none of the 32 MiB of table and sketch). At the OOM it therefore
held more heap than its 300 MiB setting while reporting ≈ 63% use. An operator who sizes
`memtable_heap_space + counter_cache_size + baseline` below `-Xmx` (907 < 1024 MiB here) is not protected. No check in
5.0.9 relates either setting to the heap or to each other.

Limits: diagnostic budget and `memtable_cleanup_threshold: 0.99`. One single-node host with client and server on the
same 16 threads. The OOM-throwing thread is incidental (a write request or compaction); the holders are the two pools.
`nodetool info` polling every 30 s added JMX allocations, but the domains account for ≈ 870 of ≈ 940 MiB live.
Shallow sizes assume compressed oops. The walks stop at classes outside each domain's allowlist (e.g. `ColumnMetadata`,
`TableMetadata`), so shared metadata is not attributed. The mixed tag rests on U_C > C_C at the dump. A counterfactual
with a physically bounded 300 MiB cache was not run. The 2026-11-02 result on the 40-core node (caught throws, JVM alive)
is not re-run on that node.
