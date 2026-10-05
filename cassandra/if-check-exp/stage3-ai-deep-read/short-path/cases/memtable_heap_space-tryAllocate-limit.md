# memtable_heap_space (MemtablePool.SubPool.tryAllocate hard cap) — verification solution  <!-- file: cases/memtable_heap_space-tryAllocate-limit.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-sonnet-5, 2.1.272 (Claude Code), 2026-10-05, attempt 1 |

## A. Constraint trace

**A1. The constraint.**
Name: **`memtable_heap_space`** (on-heap sibling: `memtable_offheap_space`). Kind: `cassandra.yaml` configuration entry, parsed into a `DataStorageSpec.IntMebibytesBound` field.
First declared: `src/java/org/apache/cassandra/config/Config.java:186-189`:
```
186: @Replaces(oldName = "memtable_heap_space_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
187: public DataStorageSpec.IntMebibytesBound memtable_heap_space;
188: @Replaces(oldName = "memtable_offheap_space_in_mb", converter = Converters.MEBIBYTES_DATA_STORAGE_INT, deprecated = true)
189: public DataStorageSpec.IntMebibytesBound memtable_offheap_space;
```
Unit: mebibytes (`DataStorageSpec.IntMebibytesBound`, `src/java/org/apache/cassandra/config/DataStorageSpec.java:404-464`).
Default, when the yaml key is absent, computed in `DatabaseDescriptor.applyAll()`:
```
src/java/org/apache/cassandra/config/DatabaseDescriptor.java:583-587
  conf.memtable_offheap_space = Runtime.getRuntime().maxMemory() / (4*1048576)  (MiB)
  conf.memtable_heap_space    = Runtime.getRuntime().maxMemory() / (4*1048576)  (MiB)
```
i.e. 1/4 of the JVM's max heap (`-Xmx`) each, by default. A value of 0 MiB is rejected (`DatabaseDescriptor.java:588-589`).
Settable: only via `cassandra.yaml` (`memtable_heap_space: <N>MiB`, min unit MiB — documented at `conf/cassandra.yaml:791-799`). There is no `-D` system property, no JMX setter (`grep` for `setMemtableHeapSpace*` in `DatabaseDescriptor.java` returns nothing), and no nodetool command. The value is read once into a **static final** pool object:
```
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:59
  public static final MemtablePool MEMORY_POOL = AbstractAllocatorMemtable.createMemtableAllocatorPool();
```
so a change requires a **full node restart**; it is not reloadable.

**A2. What it caps.**
Heap (or, with `offheap_buffers`/`offheap_objects` allocation types, off-heap) memory used by **memtable data across the whole node** — not per table. `MEMORY_POOL` is one process-wide singleton; every table's memtable allocator is obtained from it (`AbstractAllocatorMemtable.java:118`: `MEMORY_POOL.newAllocator(...)`). The quantity compared against the limit is `SubPool.allocated` (`MemtablePool.java:111,156`), the running total of bytes acquired by all live/flushing memtable allocators on the node.
It does **not** cap disk; it only indirectly influences disk I/O by forcing flushes.

**A3. Mechanism.**
1. Write path reaches `MemtableAllocator.SubAllocator.allocate(size, opGroup)` (`MemtableAllocator.java:169-197`).
2. It calls `parent.tryAllocate(size)` → `MemtablePool.SubPool.tryAllocate` (`MemtablePool.java:151-161`), the entry pointer: `if ((cur = allocated) + size > limit) return false;` (line 156) else CAS `allocated += size` and return true.
3. **If it succeeds**: the allocator records ownership (`acquired()`/`allocated()`), and `SubPool.maybeClean()` is invoked, which checks `needsCleaning()` (`MemtablePool.java:125-129`): `used() > nextClean`, where `nextClean = reclaiming + limit*cleanThreshold` (`MemtablePool.java:137-147`). `cleanThreshold` defaults to `1/(1+memtable_flush_writers)` (`DatabaseDescriptor.java:763`; `memtable_flush_writers` defaults to 2 with one data directory, `DatabaseDescriptor.java:755`, giving `cleanThreshold≈0.33`). Crossing this **soft** threshold triggers `MemtableCleanerThread.trigger()` → `AbstractAllocatorMemtable.flushLargestMemtable()` (`AbstractAllocatorMemtable.java:249` ff.), which async-flushes the largest memtable to free `allocated`.
4. **If `tryAllocate` fails** (the hard cap, line 156) and the calling `OpOrder.Group` is not itself `isBlocking()`, the writer thread registers on `hasRoom` wait queue and blocks (`MemtableAllocator.java:180-196`), i.e. **the write stalls** until a flush completes and calls `SubPool.released()` (`MemtablePool.java:192-197`), which signals the queue. This is the documented behavior: `conf/cassandra.yaml:792-794`: *"Cassandra will stop accepting writes when the limit is exceeded until a flush completes."* The `blockedOnAllocating` `Timer` (`MemtablePool.java:50,63,252-255`) records exactly this stall.
5. **Bypass/overshoot path**: if the `OpOrder.Group` the write belongs to is already marked `isBlocking` (set via `Barrier.markBlocking()`, `OpOrder.java:155-167` — used for in-flight writes on a memtable that a flush is already waiting to drain, to avoid deadlocking the flush barrier), `MemtableAllocator.allocate` takes the other branch: `allocated(size)` is called unconditionally (`MemtableAllocator.java:182`, `204-206`), which calls `SubPool.allocated()` → `adjustAllocated()` (`MemtablePool.java:167-175`), **bypassing the `limit` check entirely** (doc comment at `MemtablePool.java:163-165`: *"bypassing any limits or constraints"*). This is a narrow, deliberate escape valve for operations that must not deadlock a flush already in progress, not a general loophole for ordinary writes.

**A4. Other consumers.**
Everything else competing for the same JVM heap is outside this constraint's control: read-path objects, row/key/chunk caches, bloom filters (on-heap portion), compaction merge buffers, client/Netty request buffers, JVM/GC overhead, secondary-index build structures, repair Merkle trees, and off-heap: direct byte buffers used by `offheap_buffers`/`offheap_objects` allocation types are counted, but SSTable-level off-heap structures (bloom filters, compression metadata when off-heap, `file_cache_size`/chunk cache) are governed by separate, unrelated settings and are not limited by `memtable_offheap_space`.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:791-825` (shipped docs for `memtable_heap_space`, `memtable_offheap_space`, `memtable_cleanup_threshold`, `memtable_allocation_type`) — read as part of pinned tree, cited above.
- No external issue/history was consulted beyond the pinned tree, per the brief's "read nothing else" instruction.

## B. Verification solution

**B1. Claim under test.**
(1) With `memtable_allocation_type: heap_buffers` (default) and `memtable_heap_space` set to `L` MiB, the node-wide sum of memtable on-heap ownership never sustainedly exceeds `L` MiB while a write workload that would otherwise allocate heap faster than it can be flushed is applied; instead throughput collapses to the flush-drain rate and writer threads measurably block. (2) Lowering `L` while holding the workload fixed increases blocking (count and time) monotonically and proportionally sooner. If allocation is observed to climb substantially and durably past `L` under sustained write pressure (not just a single `isBlocking`-bypass transient), the claim is false.

**B2. Environment and build.**
- 1 Linux node (can extend to 2-3 identical nodes with independent data dirs to show the cap is per-node, not cluster-wide; single node suffices for the core claim).
- `git clone <local path to this repo> /data/local/cassandra-build` (clone to local disk, never build in the shared clone); `git checkout cassandra-5.0.9`.
- JDK 11, Ant: `ant jar` from `/data/local/cassandra-build`.
- Data/commitlog/hints directories on local disk of known size, e.g. `/data/local/ccm-node/{data,commitlog,hints,saved_caches}`, sized ≥ 2 GiB free (never shared storage).
- JVM options in `jvm11-server.options` / `cassandra-env.sh`: fix `-Xms512M -Xmx512M` so the default 1/4-heap derivation is irrelevant (we set the cap explicitly, see B3) and heap behavior is reproducible.
- `cassandra.yaml` changes:
  - `memtable_allocation_type: heap_buffers` (default; exercises `SlabPool`, `MemtablePool.java:156` directly on-heap).
  - `memtable_heap_space: 64MiB` (explicit `L`, overriding the derived default so the cap is a known, controlled number).
  - `memtable_offheap_space: 64MiB` (unused by `heap_buffers`, set only so startup logging/validation is uniform).
  - `memtable_flush_writers: 1` ⇒ default `memtable_cleanup_threshold = 1/(1+1) = 0.5` (soft-flush trigger at 50% of `L`).
  - `commitlog_sync: periodic`, default `commitlog_sync_period: 10000ms` (keep commitlog off the critical path so memtable allocation, not commitlog fsync, is the bottleneck being measured).
  - Create keyspace with `durable_writes = false` for the test table only if isolating memtable pressure from commitlog is desired (optional control, see B9).

**B3. Knobs.**
- `L = memtable_heap_space`: test with **64 MiB** and **16 MiB** (4× smaller) to show the observed ceiling tracks `L`. Set via `cassandra.yaml`, requires node restart (A1).
- `memtable_cleanup_threshold` (via `memtable_flush_writers: 1` ⇒ 0.5): held fixed across both `L` values so the soft/hard-limit ratio is identical, isolating `L` as the only variable.
- Write concurrency: `cassandra-stress` thread count, swept at 50 and 200 threads, to confirm blocking (not just flush-triggering) appears once offered write rate exceeds flush-drain rate.

**B4. Workload.**
Single keyspace/table, one column of fixed-size blob, inserted with unique partition keys so no overwrites are compacted away in-memory (each insert adds new, not updates existing, allocated bytes).
- Row payload: 4 KiB blob + key/overhead ≈ 4.2 KiB allocated per row (on-heap `SlabAllocator`, `SlabAllocator.java:78-114`).
- To fill `L=64MiB` once: 64 MiB / 4.2 KiB ≈ 15,600 rows — reachable in well under a second of CPU-bound insert, so a workload of **2,000,000 rows** (≈ 8.4 GB raw data, ~128× the 64 MiB cap) forces on the order of 100+ flush cycles, giving a long steady-state window in which allocation should plateau at ≤ `L` rather than grow unbounded.
- Driver: `tools/bin/cassandra-stress write n=2000000 cl=ONE -rate threads=50 -node 127.0.0.1 -col size=FIXED(4096)` (adjust column spec to the user-defined schema so payload ≈4 KiB).
- Duration: expect several minutes; stop early once steady-state blocking is observed for ≥60s.

**B5. Observables and instruments.**
- **`AllMemtablesOnHeapDataSize` (global table gauge)**, JMX ObjectName `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize` (`TableMetrics.java:505-512`, aggregated by `GlobalTableGauge`, `TableMetrics.java:1331-1349`). Sampled every 1s via `jmxterm`/`jconsole`/a small JMX poller. This is the closest available proxy for `SubPool.allocated` at `MemtablePool.java:111`; there is no MBean exposing `allocated` directly, so this is an approximation (note as limitation).
- **`BlockedOnAllocation` timer**, JMX `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` (`MemtablePool.java:50,63`). Count and mean/max duration sampled every 1s — direct evidence of code path A3 step 4 executing.
- **`PendingFlushTasks` gauge**, JMX `org.apache.cassandra.metrics:type=MemtablePool,name=PendingFlushTasks` (`MemtablePool.java:51,64-65`).
- `nodetool tablestats <ks>.<table>` for `Memtable cell count`, `Memtable data size`, `Memtable switch count` (corroborating flush cadence) and `nodetool tpstats` for `MemtableFlushWriter` pending/active counts.
- cassandra-stress's own reported op/s over time (expect a drop once the cap is first hit, recovering in a sawtooth as flushes complete).
- Cannot be observed directly: the exact instant an individual thread enters the CAS loop at `MemtablePool.java:151-161`; only the aggregate effect (gauge plateau, timer increments) is visible without attaching a debugger/async-profiler to that method.

**B6. Procedure.**
1. Build: `cd /data/local/cassandra-build && ant jar`.
2. Configure node A with `memtable_heap_space: 64MiB` as in B2/B3; start: `bin/cassandra -f`.
3. Create schema: `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (k uuid PRIMARY KEY, v blob);`
4. Start JMX pollers for the three MBeans above at 1 Hz, logging to local files.
5. Run cassandra-stress workload from B4 at 50 threads; let run until ≥5 full flush cycles observed (`Memtable switch count` increments) and the on-heap gauge shows a repeating sawtooth.
6. Record steady-state max of `AllMemtablesOnHeapDataSize`, final value and trend of `BlockedOnAllocation` count/mean, and stress op/s over time.
7. Repeat steps 2-6 with `memtable_heap_space: 16MiB` (restart required, A1), same workload and thread count.
8. Repeat step 5 at 200 threads for the 64 MiB config to confirm blocking appears/intensifies once offered rate increases.
9. Stop cassandra-stress, `nodetool flush`, `nodetool drain`, stop the Cassandra process (`kill <pid>`, confirm via `ps` that no `CassandraDaemon`/cleaner-thread JVM remains), remove the local data/commitlog/hints directories created in B2.

**B7. Predictions.**
- `L=64MiB`: `AllMemtablesOnHeapDataSize` plateaus with peaks close to but not sustainedly above ≈64 MiB (allowing for an overshoot bounded by the size of one in-flight allocation request, since the CAS check at line 156 only prevents the *next* allocation once `cur+size>limit` — overshoot per flush cycle should be at most a few hundred KiB, i.e. roughly one row's worth, not megabytes).
- `L=16MiB`: plateau ≈16 MiB, i.e. roughly 1/4 of the 64 MiB run's peak — a linear relation to `L`.
- `BlockedOnAllocation` count: ≈0 or near-0 at low thread count (50) if flush keeps up; count should become clearly >0 and growing once offered write rate exceeds flush/disk drain rate (200 threads), and mean blocked time should be on the order of one flush's duration (seconds, not microseconds).
- Stress op/s: sustained rate converges to the flush+disk drain rate once the cap is first reached, independent of client thread count beyond that point (adding threads at 200 should not raise sustained throughput much further versus 50, since the ceiling is now the SlabPool allocator, not client concurrency).
- `Memtable switch count` should increase roughly every time `AllMemtablesOnHeapDataSize` crosses ~50% of `L` (the `cleanThreshold=0.5` soft trigger), i.e. flush-cycle count for the 2,000,000-row run on 64 MiB ≈ 8.4GB / (64MiB×0.5) ≈ 260 cycles (order-of-magnitude; exact count depends on per-row overhead not fully known ahead of time — stated as a relation, not an exact figure).

**B8. Readings.**

| Observation | Meaning |
|---|---|
| `AllMemtablesOnHeapDataSize` plateaus at ≈`L` (±one row), sawtooth with period matching flush cycles | Claim holds: `memtable_heap_space` caps node-wide memtable heap via `tryAllocate` |
| `BlockedOnAllocation` count increases once offered rate > drain rate, stays flat when rate ≤ drain rate | Confirms the hard-limit blocking mechanism (A3 step 4) is what enforces the cap under pressure |
| Gauge for `L=16MiB` plateaus at ≈1/4 of the `L=64MiB` plateau | Confirms the limit, not some other fixed ceiling (e.g. GC/heap size), governs the observed cap |
| Gauge grows **without bound** past `L` (e.g. to several hundred MiB) while workload continues, with no corresponding plateau | **Claim is false** — either the cap is not enforced on this path, or some other code path (e.g. large unslabbed allocations, `SlabAllocator.java:92-100`, bypassing the per-region accounting) adds memory uncounted |
| Gauge tracks `L` but stress op/s never drops (no blocking, `BlockedOnAllocation` stays 0 even at 200 threads) | Would suggest the workload never actually pressured the limit (control failure — raise thread count/row size rather than concluding the cap is absent) |
| Node OOMs / GC death spiral despite gauge showing values at or below `L` | Would indicate the cap value itself is set too high relative to `-Xmx` for the non-memtable consumers in A4, not that the mechanism failed — distinguishes "cap doesn't stop OOM" from "cap doesn't cap memtable memory" |

**B9. Controls.**
- Fixed `-Xmx` across both `L` values isolates `memtable_heap_space` as the only changed input; if the plateau didn't scale with `L`, JVM heap limits (GC) rather than this constraint would be suspected.
- Per-row size and unique keys (no updates) rule out compaction/overwrite coalescing as an alternative explanation for a lower-than-expected plateau.
- `durable_writes=false` option isolates the memtable allocator from commitlog fsync latency, ruling out "blocking is due to commitlog, not memtable cap" as a confound (run once with and once without durable writes if that ambiguity needs resolving).
- Running at both 50 and 200 stress threads with the same `L` separates "offered-rate-independent ceiling" (supports the claim) from "ceiling rises with more client threads" (would indicate the cap is not actually hard).

**B10. Risks and cleanup.**
- Risk: filling local disk with the 2,000,000-row workload (~8.4 GB raw before compaction) — pre-check free space ≥ 2× that figure before running; abort and truncate table if disk usage approaches the local partition's limit.
- Risk: leaving the stress/cassandra JVMs running — step 9 explicitly stops both and verifies via `ps`/`jps` that no `CassandraDaemon` or lingering `MemtableFlushWriter`/cleaner thread JVM remains.
- Risk: OOM-killing the node under the 200-thread run if `-Xmx` is too tight relative to non-memtable heap use (A4) — keep `-Xmx` at 512M only with the small 16/64 MiB caps used here; do not scale workload row size up without re-checking headroom.
- Cleanup: remove the locally cloned build and the local `ccm-node` data/commitlog/hints directories; nothing is written outside the node's local disk per B2.

## C. Paths read

src/java/org/apache/cassandra/utils/memory/MemtablePool.java
src/java/org/apache/cassandra/utils/memory/HeapPool.java
src/java/org/apache/cassandra/utils/memory/NativePool.java
src/java/org/apache/cassandra/utils/memory/SlabPool.java
src/java/org/apache/cassandra/utils/memory/MemtableCleanerThread.java
src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
src/java/org/apache/cassandra/utils/memory/SlabAllocator.java
src/java/org/apache/cassandra/utils/concurrent/OpOrder.java
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/DataStorageSpec.java
src/java/org/apache/cassandra/metrics/DefaultNameFactory.java
src/java/org/apache/cassandra/metrics/TableMetrics.java
conf/cassandra.yaml
