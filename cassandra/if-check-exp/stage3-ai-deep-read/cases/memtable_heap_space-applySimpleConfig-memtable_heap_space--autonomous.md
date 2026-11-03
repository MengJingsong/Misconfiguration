# memtable_heap_space (startup validation in applySimpleConfig) — verification solution  <!-- file: cases/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:588`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L588) (`588#1`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code (CLI version not obtainable: `claude --version` failed inside the sandbox), 2026-10-24, band D triage |
| Estimate | `positive`: the check at line 588 only rejects a zero value, but the entry it guards becomes the on-heap `SubPool.limit` of the global memtable pool, and writers block in `SubAllocator.allocate` when `allocated + size > limit`, so on-heap memtable memory is capped by it (with a bounded overshoot for writes that are already blocking a flush). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `memtable_heap_space`, configuration entry (`Config.memtable_heap_space`, a `DataStorageSpec.IntMebibytesBound`). Unit MiB. Commented in `conf/cassandra.yaml:797` (`# memtable_heap_space: 2048MiB`). Default when unset: `maxMemory / 4` MiB ([`DatabaseDescriptor.java:586-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L587)). Line 588 throws `ConfigurationException` when the value is 0 MiB, so a node will not start with 0. Read once into the static `MEMORY_POOL` ([`AbstractAllocatorMemtable.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L59), `81`), so a change needs a restart; there is no JMX setter in the pool path.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** JVM heap used by memtable data (the cell/row bytes that memtable allocators account to the on-heap sub-pool). Operand: `SubPool.allocated` (bytes accounted on-heap) vs `SubPool.limit` (= `memtable_heap_space << 20`).

**A3. Mechanism.**
1. `applySimpleConfig` sets default ([`DatabaseDescriptor.java:586-587`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L586-L587)), rejects 0 (`:588-589`), logs the threshold (`:590`).
2. `createMemtableAllocatorPool` reads `heapLimit = getMemtableHeapSpaceInMiB() << 20` ([`AbstractAllocatorMemtable.java:81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L81)) and builds `HeapPool`/`SlabPool`/`NativePool` with it for every allocation type (`:97-110`).
3. `MemtablePool` constructor builds `onHeap = new SubPool(limit, cleanThreshold)` ([`MemtablePool.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L59)).
4. Every memtable write allocates through `MemtableAllocator.SubAllocator.allocate` ([`MemtableAllocator.java:169-196`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L169-L196)): `tryAllocate` ([`MemtablePool.java:151-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L151-L161)) fails if `allocated + size > limit`; the writer then waits on `hasRoom` and retries.
5. Flushing is triggered earlier by the cleaner when `used > reclaiming + limit * memtable_cleanup_threshold` ([`MemtablePool.java:125-147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L125-L147)), which calls `flushLargestMemtable` ([`AbstractAllocatorMemtable.java:249`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java#L249)) with reason `MEMTABLE_LIMIT`; flushed memory is `released` and `hasRoom` is signalled ([`MemtablePool.java:192-197`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java#L192-L197)).
- Overshoot/bypass: when the op group is already blocking (a flush is waiting on it) the allocation is recorded without the check ([`MemtableAllocator.java:180-184`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java#L180-L184)), so `allocated` can exceed `limit` by the in-flight writes. Large values above `MAX_CLONED_SIZE` are still accounted ([`SlabAllocator.java:89-95`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/SlabAllocator.java#L89-L95)). Object overhead of the memtable data structures (skip-list/trie nodes) is accounted only through the allocators' estimates, so real heap differs from `allocated`.

**A4. Other consumers.** All other heap users: key/row caches, chunk cache (off-heap), prepared statements, read/compaction garbage, Netty buffers, Merkle trees, index summaries. The cap governs memtable accounting only, not total heap.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:790-825` comments; `MemtablePool.java` comment at `:96-100`. No external sources.

## B. Verification solution

**B1. Claim under test.** With `memtable_allocation_type: heap_buffers`, the global on-heap memtable usage (`MEMORY_POOL.onHeap.used()`, and the sum of `AllMemtablesOnHeapDataSize`) never exceeds `memtable_heap_space` by more than a few in-flight mutations, and its peak scales with the knob; a value of 0 is rejected at startup.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. `git clone --branch cassandra-5.0.9 /path/to/shared/cassandra-src /local/c509 && cd /local/c509 && ant jar build-test`. New test `test/unit/org/apache/cassandra/utils/memory/MemtableHeapCapTest.java` in the local clone only. Run with `ant testsome -Dtest.name=org.apache.cassandra.utils.memory.MemtableHeapCapTest`.

**Amendment 2026-10-24 (step-0 audit) — B2a, harness layout.** Three test classes in `org.apache.cassandra.utils.memory`, each run by its own `ant testsome`: `MemtableHeapCapTest` (B2e steps 1-2 and B2h), `MemtableHeapSpaceZeroTest` (step 3), `MemtableHeapSpaceDefaultTest` (step 4). Reason: `daemonInitialization` runs once per JVM and silently returns on a second call (`DatabaseDescriptor.java:257-260`), and `testsome` forks one JVM per test class (`build.xml:1126`, `:1153`), so each configuration case needs its own class; that is the "forked JVM" of B2b. `MemtableHeapCapTest` calls `DatabaseDescriptor.daemonInitialization()` (the test yaml) before it touches `AbstractAllocatorMemtable`, whose class initialiser builds `MEMORY_POOL` from `DatabaseDescriptor` (`AbstractAllocatorMemtable.java:59`, `:78-85`).

**B2b. Knobs.** `heapLimit` passed to `AbstractAllocatorMemtable.createMemtableAllocatorPoolInternal(heap_buffers, heapLimit, 0, 0.5f, cleaner)` with values 1 MiB, 4 MiB, 16 MiB. Separately, `memtable_heap_space` = `0MiB` and unset, via a `Config` object passed through `DatabaseDescriptor.daemonInitialization(() -> config)` in a forked JVM.

**B2c. Workload.** One `SlabAllocator` from `pool.newAllocator("t")`; a writer thread calls `allocator.allocate(1024, group)` with `group = new OpOrder().start()` repeatedly, 4×limit/1024 times. The cleaner is a no-op returning `ImmediateFuture.success(false)`, so nothing is released and the limit must be reached after limit/1024 calls (with 1 MiB slab regions the accounted size grows per region, not per call; accept either granularity).

**B2d. Observables and instruments.** `pool.onHeap.used()` and `pool.onHeap.limit`, sampled after each call by the writer and every 10 ms by the test thread; writer thread state (`Thread.getState() == WAITING`) after 2 s. For the config case: exception type/message.

**B2e. Procedure.** (1) For each limit: start writer; after 2 s record max `used()`, writer state, call count. (2) Call `pool.onHeap.released(limit/2)` via the allocator's `setDiscarded()`/`releaseAll` path, or directly through `SubAllocator.releaseAll()`; check the writer resumes. (3) Fork a JVM with `memtable_heap_space: 0MiB`, call `DatabaseDescriptor.daemonInitialization`; record exception. (4) Same with the key unset under `-Xmx1G`; read `getMemtableHeapSpaceInMiB()`.

**Amendment 2026-10-24 (step-0 audit) — B2e, exact steps.** Step 1: a fresh pool per limit; the writer stops at the first of (all 4×limit/1024 calls done) or (interrupt); the test reads after 2 s. Step 2: release by calling `pool.onHeap.released(limit/2)` directly (package-private, `MemtablePool.java:192-197`; the test is in the same package), wait 2 s, and record the call count, `used()` and writer state again; then interrupt the writer (the wait throws on interrupt) and join it. Step 3: `Config c = DatabaseDescriptor.loadConfig()` (the test yaml, which leaves `memtable_heap_space` unset), `c.memtable_heap_space = new DataStorageSpec.IntMebibytesBound("0MiB")`, then `DatabaseDescriptor.daemonInitialization(() -> c)`; record the exception class and message. Step 4: plain `DatabaseDescriptor.daemonInitialization()`; the junit fork's `maxmemory="1024m"` (`build.xml:1153`) is the `-Xmx1G`; record `Runtime.getRuntime().maxMemory()` with the value. Reason: B2e named alternatives for the release and left the config object's source open.

**B2f. Predictions.** Max `used()` ≤ limit for 1/4/16 MiB; writer `WAITING` after ≈limit/1024 calls (±1 slab region); resumes after release. Zero → `ConfigurationException("memtable_heap_space must be positive...")`. Unset with `-Xmx1G` → `getMemtableHeapSpaceInMiB()` = 256 (±1 for JVM `maxMemory` rounding, i.e. `maxMemory/4/1MiB`).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| `used()` plateaus at ≤ limit, writer blocks | mechanism works as traced (claim supported) |
| `used()` exceeds limit with a non-blocking op group | claim wrong |
| writer never blocks, `used()` grows to 4×limit | claim wrong |
| zero accepted at startup | line 588 not effective (claim wrong for the validation part) |

**B2h. Controls.** Same workload with `heapLimit = Long.MAX_VALUE`: writer finishes all calls without blocking (shows blocking is due to the limit). Repeat with `group` marked blocking (`OpOrder.Group` after `order.newBarrier().issue()`): `used()` may exceed limit, confirming the documented overshoot path.

**Amendment 2026-10-24 (step-0 audit) — B2h.** The blocking control needs `Barrier b = order.newBarrier(); b.issue(); b.markBlocking();` with `group` started from `order` before the barrier: `issue()` alone leaves `isBlocking` false (`OpOrder.java:319-335`, `:389`, `:407`). The controls are run with these sizes and expected outcomes: (i) `heapLimit = Long.MAX_VALUE`, 65,536 calls (4 × 16 MiB / 1024): all calls return, the writer is never `WAITING`, `used()` = 64 MiB; (ii) limit 1 MiB with the blocking group, 4,096 calls: all calls return without `WAITING`, `used()` = 4 MiB (> limit). Reason: B2h gave neither the sizes nor a call that makes the group blocking.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, local disk with ≥20 GB free at `/local/c509-node`. `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` in `conf/cassandra-env.sh` (or `conf/jvm-server.options`). `cassandra.yaml`: `data_file_directories: [/local/c509-node/data]`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` under `/local/c509-node`, `memtable_allocation_type: heap_buffers`, `concurrent_compactors: 1`.

**B3b. Knobs.** `memtable_heap_space`: `64MiB`, `256MiB`, and unset (default 512 MiB at 2 GiB heap). Each run is a fresh node start.

**B3c. Workload.** `tools/bin/cassandra-stress write n=3000000 cl=ONE -col n=FIXED(5) size=FIXED(200) -rate threads=64 -schema "replication(factor=1)"` → ≈3 GB of cell data, far above all three limits; ≈5-10 minutes.

**B3d. Observables and instruments.** Every 1 s: `nodetool sjk mx -b "org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize" -mg -f Value` (the `GlobalTableGauge` summing `ownsOnHeap` over all tables, `TableMetrics.java:506-512`; it counts memtables being flushed too); `nodetool sjk mx -b org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation -mg -f Count`; `grep "Flushing largest" logs/system.log`; `jstat -gc <pid> 1000` for old-gen occupancy.

**Amendment 2026-10-24 (step-0 audit) — B3d.** (1) Correction: `AllMemtablesOnHeapDataSize` sums the **current** memtable of each table and its indexes (`TableMetrics.java:506-512`, `:876-882`); it does **not** count memtables being flushed, so it reads at or below the pool's `allocated`. (2) Added observable, read from the log: the `Used total: <on>/<off>` field of each `Flushing largest` line, which is `MEMORY_POOL.onHeap.usedRatio()` = `allocated / limit` at the trigger, flushing memtables included (`AbstractAllocatorMemtable.java:289-295`, `MemtablePool.java:234-240`); the pool used in bytes is that ratio × knob. (3) The two MBean attributes are read every 1 s through one JMX connection (the harness sampler), because each `nodetool` call starts a JVM and two calls cannot keep a 1 s cadence; one `nodetool sjk mx` read of the gauge at the start and end of each run cross-checks the sampler. The sampler stops 10 s after stress exits. Reason: the parenthetical was a citation error found by reading the source, and B1 names `MEMORY_POOL.onHeap.used()`, which no MBean exposes.

**Runbook fix 2026-10-24 (stage 4, run 1, defect 1) — B3d, old-gen occupancy.** `jstat -gc <pid> 1000` cannot attach to the node: the node's `conf/jvm-server.options:137` sets `-XX:+PerfDisableSharedMem`, so jstat fails with `MonitorException: <pid> not found`. The same quantity is read every 1 s by the harness sampler over its JMX connection: `java.lang:type=MemoryPool,name=G1 Old Gen` `Usage.used` (old-gen occupancy, jstat's OU) and `CollectionUsage.used` (old gen after the last collection of it), plus `java.lang:type=Memory` `HeapMemoryUsage.used`. B3g's "jstat OU" row reads this `Usage.used`; B3f and the B3g rows are unchanged. The cluster tier restarts from its first run.

**B3e. Procedure.** (1) Configure, start `bin/cassandra -f`, wait for `nodetool status` UN. (2) Start sampler loop to a CSV. (3) Run stress. (4) Stop sampler, `nodetool drain`, stop node, record peak/median of `AllMemtablesOnHeapDataSize`, count of `Flushing largest ... MEMTABLE_LIMIT` lines, `BlockedOnAllocation` count. (5) Wipe `/local/c509-node`, change knob, repeat.

**B3f. Predictions.** Peak `AllMemtablesOnHeapDataSize` ≤ knob × 1.05 for each value (64 MiB, 256 MiB, 512 MiB); peaks ordered 64 < 256 < 512; "Flushing largest" lines present in every run; flushes more frequent at 64 MiB.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| peaks ≤ knob and ordered with the knob | claim confirmed |
| peak > knob by more than 5% in a sustained way | cap not binding (claim wrong) |
| peaks equal across knobs | usage governed by something else (claim wrong or limit never reached; check stress throughput) |
| `BlockedOnAllocation` > 0 only at 64 MiB | cap binds under pressure (supports claim) |

**Amendment 2026-10-24 (step-0 audit) — B3g, rows added; the four rows above are unchanged.** "Sustained" in row 2 means at least 3 consecutive 1 s samples. Row 1 ("claim confirmed") also needs, in every run, direct evidence that the limit acted: at least one `Flushing largest` line with `Reason: MEMTABLE_LIMIT` on its `Enqueuing flush` line, or `BlockedOnAllocation` > 0.

| Observation | Meaning |
|---|---|
| peaks ≤ knob × 1.05 and ordered, but a run has no `MEMTABLE_LIMIT` flush and `BlockedOnAllocation` = 0 | the limit was not shown to act in that run: not confirmed |
| `Used total` on-heap ratio > 1.05 in flush lines of a run | the pool exceeded the cap: cap not binding (claim wrong) |
| gauge ≤ knob × 1.05, but old-gen occupancy (`jstat` OU) reaches the heap maximum or the node logs `OutOfMemoryError` | counter capped but the real resource not: not confirmed for the real resource |
| stress reports errors or stops early, so the data written does not exceed the knob | invalid run |

Reason: group B of the audit requires a row for "counter capped but the real resource grows", "limit never reached" and direct evidence of the disallow effect.

**B3h. Controls.** The unset run is the reference with a known derived value. Check flush reason in logs (`MEMTABLE_LIMIT`) to rule out commit-log-driven flushes (`commitlog_total_space` default 8 GiB, well above data written per memtable). Same stress against `memtable_heap_space: 64MiB` but `memtable_allocation_type: offheap_objects` with `memtable_offheap_space: 64MiB` shows the on-heap gauge drops (data accounted elsewhere).

**B4. Risks and cleanup.** Data only under `/local/c509-node` (≈3-4 GB). After each run: `nodetool drain; pkill -f CassandraDaemon`, verify with `pgrep -f CassandraDaemon` (empty); `rm -rf /local/c509-node`. Unit tests write under `/local/c509/build/test`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (478, 583-594, 4040-4130)
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java (59, 78-112, 249-300)
src/java/org/apache/cassandra/utils/memory/MemtablePool.java (40-260)
src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java (165-200)
src/java/org/apache/cassandra/utils/memory/SlabPool.java, SlabAllocator.java (80-100)
src/java/org/apache/cassandra/metrics/TableMetrics.java (500-530)
conf/cassandra.yaml (790-825)

## D. Stage-4 feedback

**Stage 4 closed 2026-10-24** ([results](../../stage4-runtime-verification/results/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous.md)); Claude Opus 5.5 (claude-opus-5-5), advisor's machine; estimate `positive` held. **Unit tier: Confirmed — caps** (the writer stops at exactly 1 · 4 · 16 MiB after limit/1024 calls and resumes for exactly the released bytes; `0MiB` refused with `ConfigurationException`; controls: no limit → all calls, blocking group → 4 × limit). B2f's default number missed: 251 MiB, not 256, because the junit JVM's `maxMemory` is 1,007 MiB under `-Xmx1024m`; `maxMemory/4` held. **Cluster tier: Confirmed — caps** (`AllMemtablesOnHeapDataSize` peaks 25.6 · 85.4 · 170.2 MiB at 64 · 256 · 512 MiB, all ≤ knob; `MEMTABLE_LIMIT` flushes 254 · 63 · 31; `BlockedOnAllocation` 4,083 · 64 · 0; at 64 MiB the pool stood at the cap, `Used total: 1.00`). B3g row 4's "only at 64 MiB" did not hold (64 blocks at 256 MiB). Notes for stage 3, not applied: peaks sit near knob/3 because the default cleanup threshold is 1/3 and the gauge omits flushing memtables; at 256 and 512 MiB with a 2 GiB heap the load forced 2 and 7 full GCs (heap recovered to 123–473 MiB, no OOM), so the cap bounds memtable accounting, not GC pressure (A4/B4); the unit tier reads only the counter. Amendments of 2026-10-24 (B2a, B2e, B2h, B3d, B3g) were made at the step-0 audit and the B3d runbook fix during cluster run 1; the frozen hashes are in `_INDEX.md` §4, and this section was added after them.
