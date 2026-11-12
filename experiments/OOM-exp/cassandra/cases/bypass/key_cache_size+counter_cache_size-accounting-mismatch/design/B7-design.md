# B7 design — key / counter cache accounting mismatch (run 1)

**Written 2026-11-11 19:40 MST, before any reading.** Campaign-plan row B7 (P2), `source: R3/R4 recheck`.
Direction: bypass · accounting mismatch. Node `apt149` (one agent, one victim JVM at a time).

## 1. Claim and contract (from the pinned source, read-only `systems/cassandra/source/`, 5.0.9)

- `CacheService.initKeyCache()` / `initCounterCache()` build `CaffeineCache.create(size_MiB × 2^20)` (the only two
  callers). `CaffeineCache.create(long)` = Caffeine 3.1.8 `maximumWeight(capacity)` with weigher
  `key.unsharedHeapSize() + value.unsharedHeapSize()`.
- Weights: `KeyCacheKey` = EMPTY_SIZE + `sizeOfArray(key)`; value `RowIndexEntry` (BIG, unindexed partition) =
  EMPTY_SIZE. `CounterCacheKey` = EMPTY_SIZE + `sizeOfArray(partitionKey)` + `sizeOfArray(cellName)`; value
  `ClockAndCount` = EMPTY_SIZE.
- Not charged, per entry: Caffeine's node (`PSMW`, 40 B in R4), the `ConcurrentHashMap$Node` (32 B), the hash-table
  slot (4 B refs, table a power of two ≥ entries/0.75 → 5.3–10.7 B/entry) and the frequency sketch (`long[]`,
  power-of-two ≥ entries → 8–16 B/entry). Predicted omitted overhead o ≈ 85–99 B/entry (R3/R4: 89–92 B).
- **Documented contract (unit).** `cassandra.yaml`: "Maximum size of the key cache in memory." / "Maximum size of
  the counter cache in memory." (defaults "auto (min(5% of Heap (in MiB), 100MiB))" / "(min(2.5% of Heap (in MiB),
  50MiB))"). `doc/.../metrics.adoc` Cache metrics: `Capacity` "Cache capacity in bytes", `Size` "Total size of
  occupied cache, in bytes". Nowhere is the unit documented as payload only. **C = the configured capacity in bytes
  of heap memory**; no documented soft overshoot (Caffeine evicts on the writing thread, `ImmediateExecutor`, so K
  stays ≤ C apart from a few in-flight writes). A stale code comment in `initKeyCache` ("48 = 40 bytes (average size
  of the key) + 8 bytes (size of value)") shows the weight was meant as a per-entry size estimate.
- Defaults (`DatabaseDescriptor`, `Runtime.totalMemory()` at startup; -Xms = -Xmx here): key
  `min(max(1, 5% heap), 100)` MiB, counter `min(max(1, 2.5% heap), 50)` MiB → 512 MiB heap: 25 / 12 MiB;
  2048 MiB: 100 / 50 MiB; auto heap on this node (7965 MiB): 100 / 50 MiB. Confirmed per arm from the startup log
  and the JMX `Capacity` gauge.

**Hypothesis.** Filled to its cap with small entries, each cache holds U ≈ K + n·o of heap with K ≈ C, so
U/C ≈ 1 + o/w (w = weight per entry): sustained **U > C, K ≤ C** (accounting omission), independent of the heap
once the default caps saturate (≥ 2 GiB). The ratio falls with entry size.

## 2. Protection map

| Field | Key cache | Counter cache |
|---|---|---|
| Allocation / owner | `KeyCacheKey` + copied key `byte[]` + `RowIndexEntry`, inserted by BIG-format reads (`SSTableReader` index lookup → `cacheKey`); owner `CacheService.keyCache` → Caffeine `BoundedLocalCache` | `CounterCacheKey` + 2 `byte[]` + `ClockAndCount`, inserted after each counter write (`CounterMutation.updateCounterCache`); owner `CacheService.counterCache` |
| Local contract | weight ≤ `key_cache_size` bytes (default auto) | weight ≤ `counter_cache_size` bytes (default auto) |
| Scope / multiplicity | one per process | one per process |
| Aggregate coverage | none (no check of caches + memtables against the heap) | none |
| Lifetime | standing; W-TinyLFU eviction at the weight cap; hash table and sketch never shrink | same |
| Budget | Java heap | Java heap |

U (physical) = objects exclusively reachable from the cache's `BoundedLocalCache` in a live heap dump (R4 parser
`hprof_holders.py`, validated against `GC.heap_info` within 0.4 % in R4), plus class-histogram trends.
K = Caffeine `weightedSize` (dump) and JMX `Cache.Size`; C = JMX `Cache.Capacity` and the startup log.

## 3. Configuration and budget audit

- Build: Cassandra 5.0.9 (`~/cassandra-c1`, git `7cb9cc77…` "cassandra-5.0.9", copied to `/mydata/b7/run-orig`);
  diagnostic build `/mydata/b7/run-patched` = same tree + `harness/b7-weigher-overhead.diff` (weigher adds 104 B per
  entry; `ant jar`, 1 file recompiled). Node apt149: Xeon E5-2450 2.1 GHz, 8 cores / 16 threads, 15.5 GiB RAM, 8 GiB
  swap, Ubuntu 22.04.2, kernel 5.15.0-198, cgroup v2, OpenJDK 11.0.33, G1 (shipped `jvm11-server.options`).
- `cassandra.yaml`: **shipped file, unchanged** in every arm (checked by `cmp` per arm): `key_cache_size` and
  `counter_cache_size` empty (auto), `memtable_allocation_type: heap_buffers`, memtable space auto (¼ heap), BIG
  sstables, keys cached ALL (table default). No supporting deviations. Schema: keyspace `b7` RF 1; `b7.kv (k blob
  PRIMARY KEY, v int)`, `b7.ctr (k blob PRIMARY KEY, c counter)`.
- **Budgets (V7, standing rule ≥ 512 MiB):** -Xms = -Xmx = 512 MiB (minimum acceptable), 2048 MiB (ideal) and
  **auto** (`cassandra-env.sh`: min(½ RAM, 15872 MiB) = 7965 MiB here, `MaxDirectMemorySize` ¼ RAM = 3982 MiB; the
  value this node resolves by itself = the largest budget). No cgroup limit. Labels: capacities **default**; budgets
  explicit deployment (512, 2048) and automatic/resolved (auto).
- Instrumentation: `jcmd GC.class_histogram`/`GC.heap_info`/`GC.heap_dump` (each forces a full GC) only after the
  fill, never during it; `nodetool sjk mx` JMX reads. The endpoint is a standing state, so forced GCs do not alter it.

## 4. Arms (each a clean start: empty data/commitlog/saved caches, fresh JVM)

`harness/b7-run.sh arm <name> <build> <heap> <cache> <keyBytes> <fill>`: start, create schema, read C, histogram
(base); calibration fill of 20,000 entries → weight/entry; fill to `fill × C` of weight (counter: distinct counter
updates; key: insert ≥ 1.6×-enough keys, flush, compact to one sstable, invalidate the key cache, then read distinct
keys once); wait 10 s; K; flush memtables; histogram + heap info (fill); live heap dump; idle 60 s → K + histogram
(sustained); full-fill arms: churn with fill/2 new keys → K + histogram; invalidate the cache → K + histogram; stop.
Key sizes L = 8, 64, 512 B (blob partition key; same L for both caches).

| Arm set | Build | Heap | Cache | L | Fill | n |
|---|---|---|---|---|---|---|
| S2 (main condition) | orig | 2048M | counter, key | 8 | 1.5 | 3 + 3 |
| size sweep | orig | 2048M | counter, key | 64, 512 | 1.5 | 3 each (12) |
| budget sweep | orig | 512M, auto | counter, key | 8 | 1.5 | 3 each (12) |
| V2 control (under-filled, same build/budget) | orig | 2048M | counter, key | 8 | 0.35 | 3 + 3 |
| V4 intervention (weigher + 104 B/entry) | patched | 2048M | counter, key | 8 | 1.5 | 3 + 3 |
| OOM contribution | orig | 512M | all defaults, R4 workload mix | — | — | 1 (3 if it OOMs or comes within 10 %) |

**Predictions** (o = 85–99 B; w from the calibration): counter L=8 w ≈ 110 B → U/K ≈ 1.8, L=64 w ≈ 170 → 1.55,
L=512 w ≈ 620 → 1.15; key L=8 w ≈ 80 → U/K ≈ 2.1, L=64 w ≈ 136 → 1.7, L=512 w ≈ 584 → 1.16. K/C ≥ 0.97 at full fill,
so U/C ≈ U/K, identical at 2048M and auto (same caps), and the same per-entry ratios at 512M (caps 25 / 12 MiB).
U stays > C after the idle window and under churn (standing pool; table/sketch never shrink). Under-filled control
(K ≈ 0.35 C): U/C ≈ 0.63 (counter) / 0.75 (key), i.e. U < C. Intervention: weight per entry w + 104 ≥ U per entry, so
U/C ≤ 1.0 (≈ 0.93–0.99) at full fill, with ≈ 45–55 % fewer entries cached at the same configured size (the cost).
OOM contribution: at defaults the uncounted excess is ≤ (U/K − 1)·C ≈ 1.15·25 + 0.8·12 ≈ 38 MiB at 512 MiB (≈ 7.5 % of
the heap) and ≈ 155 MiB at ≥ 2 GiB (7.6 % of 2 GiB, 1.9 % of 7965 MiB). An OOM in which this excess is decisive
needs the other domains within ≈ 7.5 % of -Xmx on their own, i.e. the other pools would already be at the edge;
predicted outcome of the 512M mixed arm: **no OOM**, live heap ≤ 80 %.

**Endpoint and classification.** Endpoint: sustained U > C with K ≤ C → `verified-gap · overshoot` if V1–V7 hold
(bypass, accounting omission). Interpretation: documented-unit mismatch (yaml/metrics say memory/bytes; the weight
is payload only). Any OOM needing other domains → mixed, with its own controls.

## 5. Stop conditions

Hard limits: **7 h wall time from the first arm (stop new arms after 02:45 MST 2026-11-12), ≤ 50 arm executions**.
Priority if behind: S2 → V2 control → V4 intervention → budget sweep → size sweep (drop to n=1) → OOM test.
No escalation after an OOM. Each arm stops its node and clients; a final `pgrep` check confirms nothing is left.
Raw data: apt149 `/mydata/b7/{logs,dumps}`.

## Amendments

- **2026-11-11 19:45 MST (validation, before the batch).** Validation arms showed sequential 8-byte keys collide in
  `Arrays.hashCode` and treeify the cache's `ConcurrentHashMap` (16,723 `TreeNode`s at 46,812 entries); keys are now
  SplitMix64-scrambled indices plus padding. Idle window shortened from 120 s to 60 s. Under-filled control set to
  0.35 × C (0.45 × C would put the key cache at U/C ≈ 0.97, too close to the endpoint).
- **2026-11-12 00:00 MST (resume after the session was cut off; before the mixed reruns).** The 43-arm batch had
  finished (all cache arms clean). The first mixed arm (mixed512-r1) lost its sampler and ended only at its 45-min
  `timeout`: a bare `wait` also waits for the `exec > >(tee …)` process substitution. Fix: wait for the three stress
  JVMs before sampling, bound `jcmd`/`nodetool` calls, wait for the stress JVMs by name. Added: mixed512-r2 (rerun)
  and mixed2048-r1 (a second budget for the OOM question, per the largest-failing-budget rule). Prediction unchanged:
  no OOM. Stop limit unchanged (no new arm after 02:45 MST).
