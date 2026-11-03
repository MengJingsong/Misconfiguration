# memtable_cleanup_threshold (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:770`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L770) (`770#1`), `:772` (`772#1`), `:774` (`774#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `undetermined`: the ratio sets the point at which the memtable cleaner starts flushing the largest memtable (`used > reclaiming + limit × threshold`), so it shapes how much memtable memory is normally held, but it is a trigger, not a cap: the hard bound is `memtable_heap_space`/`memtable_offheap_space`, and usage rises above `threshold × limit` whenever flushing lags writes. Whether usage follows it depends on load. Lines 770/772 reject values outside [0.01, 0.99]; line 774 only warns below 0.1. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `memtable_cleanup_threshold`, configuration entry (`Config.memtable_cleanup_threshold`, `Float`), dimensionless ratio, commented at `conf/cassandra.yaml:812` (deprecated). Default when unset: `1 / (1 + memtable_flush_writers)` ([`DatabaseDescriptor.java:761-764`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L761-L764)), e.g. 0.33 with the default 2 flush writers for one data directory (`:753-756`); a set value logs a deprecation warning (`:765-768`). Validation: `< 0.01` throws (`:770-771`), `> 0.99` throws (`:772-773`), `< 0.1` warns (`:774-775`). Read once into static `MEMORY_POOL` ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), `83`): restart required.


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` validates the ratio against a literal range (`< 0.01`), not usage against a capacity ([README §6](../README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Nothing directly; it governs when memtable memory (heap or off-heap sub-pool) is reclaimed by flushing. Operand: `SubPool.used()` vs `nextClean = reclaiming + limit × cleanThreshold` (`MemtablePool.java:125-147`).

**A3. Mechanism.**
1. Passed into every pool type ([`AbstractAllocatorMemtable.java:83-110`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L83-L110)) and both sub-pools ([`MemtablePool.java:59-60`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L59-L60), field `:108`).
2. After each allocation, `maybeClean` → `needsCleaning` → `updateNextClean` ([`MemtablePool.java:125-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L125-L147), `177-185`); if `used > reclaiming + limit·threshold`, `cleaner.trigger()`.
3. `MemtableCleanerThread` calls the cleaner while `pool.needsCleaning()` ([`MemtableCleanerThread.java:73-97`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java#L73-L97)); cleaner is `flushLargestMemtable` ([`AbstractAllocatorMemtable.java:84`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L84), `249-300`), which logs "Flushing largest … Used total: …" with the used/live/flushing ratios (`:289-295`) and flushes with reason `MEMTABLE_LIMIT`.
4. The hard limit is `tryAllocate` against `limit` ([`MemtablePool.java:151-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L151-L161)); writers block there, not at the threshold.
- Because `reclaiming` (memory being flushed) is added to the trigger point, held memory can reach `threshold·limit + reclaiming`, up to `limit`.

**A4. Other consumers.** Periodic/commit-log-driven flushes (`memtable_flush_period_in_ms`, `commitlog_total_space`), manual `nodetool flush`, all non-memtable heap.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:800-815` comments (deprecated; default derived from flush writers). None external.

## B. Verification solution

**B1. Claim under test.** The cleaner first fires when the sub-pool's used bytes exceed `threshold × limit` (± one allocation), so under moderate write load the median memtable usage scales with the threshold; under write load exceeding flush throughput, usage rises above `threshold × limit` up to the hard limit (i.e. the threshold does not cap). Values outside [0.01, 0.99] fail startup.

**Amendment 2026-10-24 (step-0 audit) — B1, reading of two phrases (claim unchanged).** "Usage" in "rises above `threshold × limit`" is the pool's own usage, `MEMORY_POOL.onHeap.used()` (allocated bytes, memtables being flushed included), not the `AllMemtables*DataSize` gauge, which counts only current memtables (`TableMetrics.java:506-512`, `:876-883`). "Up to the hard limit" means bounded by `memtable_heap_space` (`MemtablePool.java:151-161`), not necessarily reaching it; whether the pool reaches the limit is recorded as a sub-prediction (B3f (vii)). Refuted-if: the trigger fires at a point that does not follow `t` (B2g/B3g "independent of t" rows), or usage stays at `t × limit` while memory is being flushed (B3g row 3), or a value outside [0.01, 0.99] starts. Reason: B1 named neither the observable for "usage" nor whether "up to" means "reaching" or "bounded by"; B3f and B3g read differently on it.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509`, JDK 11, `ant jar build-test`. Test `test/unit/org/apache/cassandra/utils/memory/CleanupThresholdTest.java`; `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.CleanupThresholdTest`.

**Amendment 2026-10-24 (step-0 audit) — B2a, initialisation and classes.** `CleanupThresholdTest` calls `DatabaseDescriptor.daemonInitialization()` (test yaml) in `@BeforeClass` before touching `AbstractAllocatorMemtable`, whose class initialiser builds `MEMORY_POOL` from `DatabaseDescriptor` (`AbstractAllocatorMemtable.java:59`, `:78-85`). `daemonInitialization` runs once per JVM (`DatabaseDescriptor.java:258-260`), so the config-path cases are three further classes, each its own `ant testsome` (own forked JVM): `CleanupThresholdLowTest` (0.005), `CleanupThresholdHighTest` (0.995) and `CleanupThresholdConfigTest` (0.5, the B2h config control); each passes `DatabaseDescriptor.daemonInitialization(() -> { Config c = DatabaseDescriptor.loadConfig(); c.memtable_cleanup_threshold = v; return c; })` (`DatabaseDescriptor.java:250`, `:391`). Reason: B2a left the order and the JVM split open.

**B2b. Knobs.** `createMemtableAllocatorPoolInternal(heap_buffers, 16 MiB, 0, t, cleaner)` with t ∈ {0.11, 0.33, 0.5, 0.9}; config-path cases 0.005 and 0.995 through `DatabaseDescriptor.daemonInitialization` in separate JVMs (separate test classes).

**B2c. Workload.** One allocator, `allocate(4096, new OpOrder().start())` repeatedly up to 16 MiB. `cleaner` records `pool.onHeap.used()` on its first invocation into an `AtomicLong` and returns `ImmediateFuture.success(false)` (does not free memory).

**Amendment 2026-10-24 (step-0 audit) — B2c and B2e, writer size, pacing and readings.** (1) The writer offers 8,192 calls of 4,096 B (32 MiB, twice the limit): "up to 16 MiB" is exactly the limit, which `tryAllocate` admits (`cur + size > limit` is false at 16 MiB, `MemtablePool.java:151-161`), so the writer would finish without blocking and B2f's "writer blocks" could not be observed. (2) The writer parks 50 µs between calls (`LockSupport.parkNanos(50_000)`): the cleaner runs on its own thread, woken by a signal (`MemtableCleanerThread.java:73-97`, `:128-132`), so an unpaced writer would add its progress during the wake-up to the cleaner's `used()` reading. (3) The cleaner keeps returning `ImmediateFuture.success(false)`; it is invoked again for as long as `used > threshold` (the loop re-checks `needsCleaning()`), so the invocation count is recorded without a prediction. (4) The writer stops at the first of (all 8,192 calls) or (interrupt). At 3 s the test records: invocation count, `used()` recorded by the cleaner at its first invocation, the writer's call count, `pool.onHeap.used()`, and the writer's `Thread.State`; then it interrupts and joins the writer and calls `pool.shutdownAndWait`. Reason: as written the hard-limit block could not occur, and the trigger reading had no defined resolution.

**B2d. Observables and instruments.** `used()` at first cleaner invocation; number of invocations; `used()` at which the writer blocks.

**B2e. Procedure.** For each t: new pool, run writer for up to 3 s, record observables, `pool.shutdownAndWait(1, SECONDS)`.

**B2f. Predictions.** First invocation at `used` ≈ t × 16 MiB (within one 1 MiB slab region): ≈ 1.8, 5.3, 8, 14.4 MiB. Writer blocks at ≈ 16 MiB in every case (threshold does not cap). 0.005/0.995 → `ConfigurationException` ("must be >= 0.01" / "must be <= 0.99").

**Amendment 2026-10-24 (step-0 audit) — B2f, exact values.** The trigger point is `T = (long)(limit × t)` in float arithmetic (`MemtablePool.java:139`, `nextClean` = `reclaiming` + that, with `reclaiming` = 0 here): 1,845,493 / 5,536,481 / 8,388,608 / 15,099,494 B for t = 0.11 / 0.33 / 0.5 / 0.9. "Within one 1 MiB slab region" means `T < used at first invocation ≤ T + 1,048,576` (strictly above `T`: `needsCleaning` uses `>`, `:127-131`). "Writer blocks at ≈ 16 MiB" means writer `WAITING` with exactly 4,096 calls done and `used()` = 16,777,216 (4,096 B divides the limit). Config cases: 0.005 throws `ConfigurationException` with message `memtable_cleanup_threshold must be >= 0.01, but was 0.005` (`DatabaseDescriptor.java:770-771`); 0.995 throws `… must be <= 0.99, but was 0.995` (`:772-773`). Reason: B2f's tolerances were approximate.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| trigger at ≈ t·limit, block at limit for all t | threshold is a trigger, not a cap (supports trace) |
| writer blocks at ≈ t·limit | threshold acts as a cap (estimate should become positive) |
| trigger point independent of t | threshold not used (claim wrong) |

**Amendment 2026-10-24 (step-0 audit) — B2g, rows added; the three rows above are unchanged.** Row 1 needs, for every t, the first-invocation reading inside B2f's interval **and** the writer `WAITING` at exactly 16 MiB (the direct evidence that the hard limit, not the threshold, stops the writer), plus both config cases throwing as stated and both B2h controls as stated. Added rows:

| Observation | Meaning |
|---|---|
| first invocation at `used ≤ T` for some t | trigger earlier than traced: claim wrong |
| first-invocation readings ordered with t but one or more above `T + 1 MiB` | trigger follows t but outside the stated resolution: not confirmed |
| no cleaner invocation for some t although `used` reached 16 MiB | threshold not reached by the trigger path: claim wrong |
| writer neither `WAITING` nor finished at 3 s, or ended with an exception other than the interrupt | invalid scenario |
| a config case starts (no exception) or throws with another message | the startup-validation claim is wrong (`refuted` for that part) |
| a B2h control differs from its stated outcome | the events cannot be attributed to the configured values: invalid tier |

**B2h. Controls.** Pool with t = 0.99 and limit `Long.MAX_VALUE`: no trigger, no block, showing both events come from the configured values.

**Amendment 2026-10-24 (step-0 audit) — B2h, sizes and an added config control.** (i) `t = 0.99`, limit `Long.MAX_VALUE`, the same 8,192 paced calls: 0 cleaner invocations, writer `TERMINATED` with 8,192 calls, `used()` = 33,554,432. (ii) Added: `CleanupThresholdConfigTest` with 0.5 through `daemonInitialization` (B2a amendment): initialisation succeeds, `DatabaseDescriptor.getMemtableCleanupThreshold()` = 0.5 and `AbstractAllocatorMemtable.MEMORY_POOL.onHeap.cleanThreshold` = `offHeap.cleanThreshold` = 0.5 — the pool scenarios call `createMemtableAllocatorPoolInternal` directly, so this is what shows the configured knob reaches the live pool (`AbstractAllocatorMemtable.java:78-85`, `MemtablePool.java:59-60`). Reason: B2h gave no sizes and nothing tied the config entry to the pool.

### B3. Cluster tier

**B3a. Environment and build.** One node from `/local/c509`, `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, dirs under `/local/c509-node`, `memtable_allocation_type: heap_buffers`, `memtable_heap_space: 256MiB`, `memtable_flush_writers: 2`.

**B3b. Knobs.** `memtable_cleanup_threshold` ∈ {`0.11`, `0.33`, `0.6`} (restart each); startup with `0.005`.

**B3c. Workload.** Two phases per knob: (1) moderate, `cassandra-stress write n=2000000 cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=8 fixed=5000/s`; (2) heavy, same with `-rate threads=128` (unthrottled). ≈2 GB per phase, ≫ 256 MiB.

**B3d. Observables and instruments.** `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value` every 1 s; "Flushing largest … Used total: X/Y" lines in `logs/system.log` (record X at each flush); `MemtablePool` `BlockedOnAllocation` count (`MemtablePool.java:63`).

**Amendment 2026-10-24 (step-0 audit) — B3d, gauge scope, pool readings, sampler, phases, read-backs.** (1) Correction: `AllMemtablesOnHeapDataSize` sums the **current** memtable of each table and its indexes (`TableMetrics.java:506-512`, `:876-883`); memtables being flushed are not in it. The pool's usage is read from each `Flushing largest … Used total: <on>/<off>, live: …, flushing: …, this: …` line (`AbstractAllocatorMemtable.java:285-295`, INFO in `system.log`): on-heap `Used total` = `MEMORY_POOL.onHeap.usedRatio()` (allocated / limit, flushing memtables included), `flushing` = `reclaimingRatio()`, `live` = sum of current memtables' ratios; pool bytes = ratio × `memtable_heap_space`. (2) The gauge, `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` `Count`, `…name=PendingFlushTasks` `Value` and `java.lang:type=Memory` `HeapMemoryUsage.used` are read every 1 s over one JMX connection (harness `Sampler.java`), because each `nodetool` call starts a JVM; one `nodetool sjk mx` read of `BlockedOnAllocation` at the end cross-checks the sampler. (3) Phases are cut by `system.log` byte offsets: phase 1 = from phase-1 stress start to phase-2 stress start; phase 2 = from phase-2 stress start to 10 s after phase-2 stress exits. Only lines of the table `keyspace1.standard1` count (`Flushing largest` names it as `CFS(Keyspace='keyspace1', ColumnFamily='standard1')`, `Enqueuing flush` as `keyspace1.standard1`). (4) Knob read-back: the `Node configuration:[…]` line (`Config.java:1371`) shows `memtable_cleanup_threshold=<t>` and `memtable_heap_space`, and the deprecation warning (`DatabaseDescriptor.java:765-768`) is present. (5) Flush reasons from `Enqueuing flush of keyspace1.standard1, Reason: <R>` (`ColumnFamilyStore.java:1055`). (6) Real resource: the JVM's heap used is sampled and recorded; it mixes memtable bytes with garbage and other heap users, so no row rests on it (named gap). Reason: B3d's gauge cannot show flushing memory, which is exactly what B3f's phase-2 prediction is about; `nodetool` cannot keep a 1 s cadence; the phases and read-backs were undefined.

**B3e. Procedure.** Configure → start → sampler → phase 1 → phase 2 → stop sampler → drain → stop → wipe → next knob. Then attempt start with 0.005 and record failure.

**Amendment 2026-10-24 (step-0 audit) — B3e, exact steps and stop conditions.** Order: 0.11, 0.33, 0.6 (each: fresh node, phase 1 then, 10 s after it, phase 2), then the B3h control, then 0.005. "Started" means `nodetool status` shows `UN 127.0.0.1` and `nodetool statusbinary` prints `running`, within 360 s (abort otherwise). The sampler starts after startup and stops 10 s after phase 2; then `nodetool drain` (bounded 60 s), stop, `kill -9` if still alive, wipe. Startup with 0.005: launch as above and wait up to 120 s; it counts as "fails" if the daemon exits and `node.out` or `system.log` holds `memtable_cleanup_threshold must be >= 0.01`; if it reaches "started" instead it is stopped. Every run ends with no `CassandraDaemon` and no `cassandra-stress` process. Reason: B3e gave no wait bounds or failure definition.

**B3f. Predictions.** Phase 1: "Used total" at flush ≈ t (0.11, 0.33, 0.6 ± 0.05); median gauge ordered with t; peak ≤ 256 MiB. Phase 2: peak gauge approaches 256 MiB for all t (> t·256 MiB, at least for 0.11), `BlockedOnAllocation` may be > 0. 0.005: startup fails.

**Amendment 2026-10-24 (step-0 audit) — B3f, exact relations (pool usage = on-heap `Used total` of B3d (1); lines of `keyspace1.standard1` only).** Phase 1, each t: (i) the median `Used total` over phase-1 lines is within t ± 0.05; (ii) at least 90 % of phase-1 lines have `Used total − flushing ≥ t − 0.01` (the cleaner fires only past `reclaiming + t × limit`, `MemtablePool.java:134-142`; 0.01 covers the two-decimal print); (iii) the three medians are strictly ordered 0.11 < 0.33 < 0.6; (iv) the phase-1 gauge medians are strictly ordered with t and every gauge sample ≤ 256 MiB. Phase 2: (v) at t = 0.11, the largest `Used total` is ≥ 0.21 (t + 0.10) on a line whose `flushing` is ≥ 0.10 (the excess over the threshold is memory being flushed); (vi) in every run and phase, every `Used total` ≤ 1.02 (the hard limit; 0.02 covers the `isBlocking` overshoot at `MemtableAllocator.java:180-184` and rounding); (vii) sub-prediction "approaches 256 MiB for all t": for each t, phase-2 max `Used total` ≥ 0.90 or `BlockedOnAllocation` rises during phase 2 — recorded, and it decides between rows 1 and 1b of B3g. Correction: the gauge is not predicted to approach 256 MiB in phase 2 (it omits flushing memtables, B3d (1)); "peak gauge" in the sentence above is read as pool usage. 0.005: startup fails with the B2f message. Reason: B3f's relations were approximate, and its phase-2 sentence named an observable that cannot show the predicted effect (a source fact, independent of any reading).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| phase 1 median ∝ t, phase 2 peak ≈ limit regardless of t | usage follows the threshold only under moderate load; not a cap (resolves estimate toward negative-for-cap) |
| phase 2 peak stays ≈ t·256 MiB | threshold effectively caps (resolves toward positive) |
| no dependence on t in either phase | threshold not governing (negative) |

**Amendment 2026-10-24 (step-0 audit) — B3g, conditions and rows; the three rows above stay and are made exact here.** Controls C1–C4 are those of the B3h amendment. "Phase 1 follows t" = B3f (i)–(iv) all hold. "Phase 2 passes the threshold" = B3f (v). "Hard limit held" = B3f (vi).

| # | Observation | Meaning |
|---|---|---|
| 1 | phase 1 follows t; phase 2 passes the threshold; hard limit held; (vii) holds for every t; C1–C4 hold | **Confirmed** (row 1 above): the threshold sets the flush point, usage passes it when flushing lags, up to the hard limit — Effect: does not cap |
| 1b | as row 1, but (vii) fails for some t | **Confirmed** for B1 (passes the threshold, bounded by the limit); B3f (vii) "approaches 256 MiB" not met, recorded — Effect: does not cap |
| 2 | phase 1 follows t; at t = 0.11 no phase-2 line has `flushing` ≥ 0.10 | **Not confirmed**: flushing never lagged, so "passes the threshold when flushing lags" was not exercised (limit-never-reached analogue) — Effect: undetermined |
| 3 | phase 1 follows t; at t = 0.11 some phase-2 line has `flushing` ≥ 0.10, but every phase-2 `Used total` ≤ t + 0.05 | **Refuted** (row 2 above): the threshold holds usage even while memory is being flushed — Effect: caps |
| 4 | phase-1 medians not strictly ordered with t, with C1 holding | **Refuted** (row 3 above): the threshold does not govern the flush point — Effect: does not cap |
| 5 | medians strictly ordered but (i) or (ii) fails for some t | **Not confirmed**: usage follows t outside the stated tolerance — Effect: undetermined |
| 6 | any `Used total` > 1.02 in a main run | **Refuted** for B1's "up to the hard limit" (usage exceeds the hard limit) — Effect: does not cap |
| 7 | C1, C2 or C3 fails in a run, or fewer than 3 phase-1 lines in a run, or a node `OutOfMemoryError` | **Invalid** (tier) |
| 8 | C4 (positive control) fails | **Invalid** (tier): the instruments do not show a known binding cap |
| 9 | 0.005 starts, or fails with another message | **Refuted** for the startup-validation part of B1 |

Reason: B3g had no rows for no-lag, partial tolerance, limit exceeded, control failure or the startup case, and its row 1 rested on the gauge.

**B3h. Controls.** The `memtable_heap_space` limit is the known binding cap: phase 2 reaching ≈ 256 MiB shows the workload is heavy enough; repeating phase 2 with `memtable_heap_space: 128MiB` should halve the peak. Check flush reasons are `MEMTABLE_LIMIT`, not commit-log driven.

**Amendment 2026-10-24 (step-0 audit) — B3h, controls with expected values.** C1 (knob read-back, each run): the `Node configuration` line shows `memtable_cleanup_threshold=<t>`, `memtable_heap_space=256MiB` (128MiB in the C4 run), `memtable_flush_writers=2`, `memtable_allocation_type=heap_buffers`, and the deprecation warning is logged. C2 (flush cause, each phase): no `keyspace1.standard1` flush with reason `COMMITLOG_DIRTY` or `MEMTABLE_PERIOD_EXPIRED` (expected 0: `commitlog_total_space` defaults to 8,192 MiB on this disk, `DatabaseDescriptor.java:664-674`, against ≈ 4.4 GB written per run; the stress table has no flush period), and the table's `Enqueuing flush … Reason: MEMTABLE_LIMIT` lines number at least 90 % of its `Flushing largest` lines (the cleaner requests a `MEMTABLE_LIMIT` flush after each such line, `AbstractAllocatorMemtable.java:297`; a memtable already switched logs no `Enqueuing` line, `ColumnFamilyStore.java:1014-1022`). C3 (workload): each stress phase reports 2,000,000 partitions and 0 errors. C4 (positive control, the "128 MiB" repeat): fresh node, `memtable_heap_space: 128MiB`, t = 0.11, phase 2 only; expected every `Used total` ≤ 1.02 (relative to 128 MiB: pool bytes ≤ 130.6 MiB, `MemtablePool.java:151-161`). "Halves the peak" is recorded as the ratio of C4's pool peak bytes to the t = 0.11 run's phase-2 pool peak bytes, expected ≤ 0.65 only if that run met (vii); otherwise recorded without a prediction. Reason: B3h gave no t for the repeat, no expected values and no criterion for "commit-log driven".

**B4. Risks and cleanup.** ≈ 4 GB per knob under `/local/c509-node`; stop node/stress, check `pgrep`, `rm -rf /local/c509-node`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (753-775, 4124-4127)
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java (59, 78-112, 249-300)
src/java/org/apache/cassandra/utils/memory/MemtablePool.java (55-260)
src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java (40-135)
conf/cassandra.yaml (790-825, 899-912)

## D. Stage-4 feedback

**2026-10-24, run 1 (Claude Opus 5.5, claude-opus-5-5), advisor's machine** — results: [`../../stage4-runtime-verification/results/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md`](../../stage4-runtime-verification/results/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md). Frozen version sha256 `d556e7d3…5e41` (eleven step-0 amendments of 2026-10-24 above; uncommitted). Estimate left as filed (`undetermined`).

- **Unit: B2g row 1 — Confirmed — does not cap.** The cleaner's first invocation came at the first allocation past `limit × t` for t = 0.11 / 0.33 / 0.5 / 0.9 (1,803 / 1,311 / 4,096 / 2,458 B past T); the writer blocked only at the 16 MiB limit for every t; 0.005 and 0.995 threw the stated `ConfigurationException`s; 0.5 through the config path reached `MEMORY_POOL`.
- **Cluster: B3g row 1b — Confirmed — does not cap.** Phase 1 `Used total` medians 0.110 / 0.330 / 0.600 for t = 0.11 / 0.33 / 0.6; phase 2 at t = 0.11 reached 0.76 with 0.65 of it being flushed; at most 1.00 everywhere (C4 at 128 MiB: 1.00, 1,807 blocked allocations); 0.005 fails startup. B3f (vii) "approaches 256 MiB for all t" was met only at 0.6 (160 blocked allocations); at 0.11 and 0.33 phase 2 peaked at 0.76 and 0.66 without blocking.
- Notes for stage 3 (not applied): the `AllMemtables*DataSize` gauges omit flushing memtables and so cannot show usage above the threshold; for t > 0.5 the trigger point `reclaiming + t × limit` exceeds the limit while one flush is running, so the cleaner cannot fire again and writers block at the hard limit while the log shows only `Used total` = t; `Used total` is printed only when the cleaner fires and understates the pool's peak.
