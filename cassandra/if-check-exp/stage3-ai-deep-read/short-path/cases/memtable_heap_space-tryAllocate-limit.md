# memtable_heap_space (MemtablePool on-heap limit) — verification solution  <!-- file: cases/memtable_heap_space-tryAllocate-limit.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/utils/memory/MemtablePool.java:156` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-sonnet-5, 2.1.272 (Claude Code), 2026-10-05, attempt 2 |

## A. Constraint trace

**A1. The constraint.**
`memtable_heap_space` — a `cassandra.yaml` configuration entry, type `DataStorageSpec.IntMebibytesBound`, declared at `src/java/org/apache/cassandra/config/Config.java:187` (with a deprecated legacy alias `memtable_heap_space_in_mb`, `Config.java:186`). Unit: mebibytes (the class stores/validates MiB-granularity sizes; see `DataStorageSpec.IntMebibytesBound` at `src/java/org/apache/cassandra/config/DataStorageSpec.java:404`). It is the on-heap counterpart of the companion off-heap entry `memtable_offheap_space` (`Config.java:188-189`).

Default: if the yaml key is omitted, `DatabaseDescriptor.applyMemtableConfig` sets it to ¼ of the JVM max heap: `conf.memtable_heap_space = new DataStorageSpec.IntMebibytesBound((int) (Runtime.getRuntime().maxMemory() / (4 * 1048576)))` (`src/java/org/apache/cassandra/config/DatabaseDescriptor.java:586-587`), and it must be `> 0` or startup fails (`DatabaseDescriptor.java:588-589`). Documented in `conf/cassandra.yaml:794-799` ("If omitted, Cassandra will set both to 1/4 the size of the heap").

Set via the yaml key `memtable_heap_space: <N>MiB` (or legacy `memtable_heap_space_in_mb: <N>`). There is no `-D` system property and no JMX setter: `DatabaseDescriptor.getMemtableHeapSpaceInMiB()` (`DatabaseDescriptor.java:4055-4057`) only reads the parsed config, and the value is consumed exactly once at class-init time into a `static final` field (see A3). **A changed value requires a full process restart** — it cannot be reloaded live.

**A2. What it caps.** On-heap bytes occupied by live (not-yet-flushed) memtables across the whole node (all tables), i.e. JVM heap memory. The quantity compared against the limit is `SubPool.allocated` (`MemtablePool.java:111`, read at `MemtablePool.java:156`), the running total of bytes acquired by all `MemtableAllocator`s attached to this `SubPool`, exposed via `SubPool.used()` (`MemtablePool.java:216-219`).

**A3. Mechanism.** Step by step:
1. At class-load, `AbstractAllocatorMemtable.MEMORY_POOL` is built once: `createMemtableAllocatorPool()` reads `DatabaseDescriptor.getMemtableHeapSpaceInMiB() << 20` into `heapLimit` and `getMemtableCleanupThreshold()` into `memtableCleanupThreshold` (`src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java:78-86`), then picks a pool implementation by `memtable_allocation_type` (`AbstractAllocatorMemtable.java:89-112`). The default type is `heap_buffers` (`Config.java:524`), which builds `new SlabPool(heapLimit, 0, memtableCleanupThreshold, cleaner)` (`AbstractAllocatorMemtable.java:102`); `heapLimit` becomes `MemtablePool.onHeap.limit` (`MemtablePool.java:55-60,117-121`).
2. Every table's active `Memtable` gets a `MemtableAllocator` from this single pool (`AbstractAllocatorMemtable.java:118`, `MemtablePool.newAllocator`), so `onHeap` is shared cluster-wide-per-node across all keyspaces/tables.
3. Each write path allocation goes through `MemtableAllocator.SubAllocator.allocate(size, opGroup)` (`src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java:169-197`), which first calls `parent.tryAllocate(size)` — this is the CAS loop at the entry pointer: `if ((cur = allocated) + size > limit) return false;` else CAS `allocated` to `cur+size` (`MemtablePool.java:151-161`).
4. **If `tryAllocate` succeeds** (limit not exceeded), the allocation is accepted and `acquired(size)` runs, which calls `SubPool.acquired()` → `maybeClean()` → `needsCleaning()` (`MemtablePool.java:125-135,187-190`), comparing `used()` against a cached threshold `nextClean = reclaiming + limit*cleanThreshold` (`MemtablePool.java:137-147`); if crossed, it fires `cleaner.trigger()`, which schedules `AbstractAllocatorMemtable.flushLargestMemtable()` on a dedicated `MemtableCleanerThread` to flush the largest memtable and free heap (`MemtableAllocator.java:177`, `AbstractAllocatorMemtable.java:249-318`).
5. **If `tryAllocate` fails** (over limit) and the caller's `OpOrder.Group` is **not** `isBlocking()`, the thread registers on `hasRoom` wait queue and blocks until a release (flush completing calls `SubPool.released()` → `hasRoom.signalAll()`, `MemtablePool.java:192-197`), re-tries `tryAllocate`, and only proceeds once there is room (`MemtableAllocator.java:180-196`). This is the actual backpressure that caps heap growth.
6. **Overshoot/bypass path:** if the op-order group is already marked `isBlocking()` (meaning a flush barrier is waiting on this very operation to finish before it can start flushing — see `OpOrder.java:157-167,319-335`), `allocate()` takes the `allocated(size)` branch instead, which calls `SubPool.allocated(size)` (`MemtablePool.java:177-185`) — this *unconditionally* adds to `allocated` via `adjustAllocated`, **bypassing the `tryAllocate` limit check entirely** (the Javadoc at `MemtablePool.java:163-166` says "bypassing any limits or constraints"), to avoid deadlocking the in-flight write against the flush it would otherwise need to finish. This is a deliberate, bounded overshoot: it only happens for writes already in flight when a flush barrier is raised, not for new writes.

**A4. Other consumers.** The same JVM heap is also used by: SSTable read/compaction buffers (if `memtable_allocation_type` is on-heap, `offheap_buffers`/`offheap_objects` move only payload data off-heap but key/metadata structures stay on-heap), the row cache/key cache/chunk cache, compaction, hints, gossip, client request processing, JVM/GC bookkeeping, and any off-heap `memtable_offheap_space`-controlled allocation reported through the sibling `MemtablePool.offHeap` SubPool (independent limit, same class). None of these are capped by `memtable_heap_space`; it only caps the `onHeap` `SubPool.allocated` total.

**A5. Evidence beyond the source.**
- `conf/cassandra.yaml:794-812` — the shipped documentation for `memtable_heap_space`/`memtable_offheap_space`/`memtable_cleanup_threshold`.
- `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java:32-157` — existing unit test that drives a `MemtablePool` subclass (`NativePool`) directly with an explicit small limit and shows both the blocking path and the discarding/overshoot path (`allocator.allocate(30, group)` after `setDiscarding()` at lines 141-148 overshoots the limit of 100 to reach 110, exactly the A3 step-6 bypass).
- `test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java:86-105,166-200` — existing integration-style unit test that reconfigures `memtable_allocation_type`/`memtable_cleanup_threshold` via reflection on `DatabaseDescriptor` and measures `Memtable.getMemoryUsage(memtable).ownsOnHeap` against a `MemoryMeter` deep-size measurement — precedent for the unit-tier instrumentation used below.
- `test/unit/org/apache/cassandra/utils/memory/MemtableCleanerThreadTest.java:40-179` — shows how `MemtablePool.needsCleaning()`/cleaner triggering is unit-tested with a mocked pool.

## B. Verification solution

**B1. Claim under test.** (1) `memtable_heap_space` (as `MemtablePool.onHeap.limit`) is the value that `SubPool.tryAllocate` (`MemtablePool.java:151-161`) compares `allocated` against, and crossing `allocated + size > limit` makes new, non-blocking memtable allocations stall until a flush releases space — i.e. the mechanism throttles on-heap memtable growth as traced in A3. (2) On a running node, setting `memtable_heap_space` to a small value and writing continuously causes the **sum of live memtables' on-heap footprint** to stay close to that bound (modulo the bounded A3-step-6 overshoot and modulo other on-heap consumers in A4), rather than growing unboundedly.

### B2. Unit tier

**B2a. Environment and build.**
```
git clone <local-path-to-pinned-clone> /tmp/cass509-unit   # clone to local disk, not the shared tree
cd /tmp/cass509-unit && git checkout cassandra-5.0.9
export JAVA_HOME=/usr/lib/jvm/java-11-openjdk   # JDK 11
ant jar
```
Add a new test file (do not edit shared clone) `test/unit/org/apache/cassandra/utils/memory/MemtablePoolLimitTest.java`, modeled directly on the existing `NativeAllocatorTest` (`test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java:32-157`), but using `SlabPool` to mirror the production default (`memtable_allocation_type: heap_buffers`). No `DatabaseDescriptor`/`CQLTester`/node bootstrap is needed — `MemtablePool` and `MemtableAllocator` have no dependency on a running server.
Run with: `ant test -Dtest.name=MemtablePoolLimitTest`, default test JVM heap (`-Xmx` as set by `build.xml`'s unit target, typically 1–2 GiB) — large enough since test limits are only tens of bytes.

**B2b. Knobs.**
- `limit` passed straight into `new SlabPool(limit, 0, cleanThreshold, cleaner)` — the in-process analogue of `memtable_heap_space` (bytes, not MiB, since this bypasses `DatabaseDescriptor` entirely). Values: `100` and `1000` bytes — small enough to cross with a handful of `allocate()` calls, large enough to leave headroom to observe both success and failure before the limit.
- `cleanThreshold`: `0.75f` (matches `NativeAllocatorTest.java:55`) so the cleaner fires before the hard limit, letting us observe the clean/flush-trigger path separately from the hard block.
- `opGroup.isBlocking()` state — flipped explicitly via `OpOrder.Barrier.markBlocking()` to exercise the A3-step-6 overshoot deliberately, not accidentally.

**B2c. Workload.** Drive `allocator.allocate(size, group)` with a sequence of sizes that sum past `limit`:
- With `limit=100`: `allocate(60)` (60 ≤ 100, succeeds, `used()==60`), then `allocate(60)` again (60+60=120 > 100) — call this from a **second thread** (via the test's own `ScheduledExecutorService`, as in `NativeAllocatorTest.java:48,145-146`) so the call blocks instead of deadlocking the test thread; main thread asserts it is still blocked after e.g. 200 ms, then releases 60 bytes (`allocator.released(60)` or completing a mock flush), and asserts the blocked call returns and `used()==120-60=60... ` — concretely reproduce the arithmetic: start `used=60`; release `60` → `used=0`; blocked `allocate(60)` unblocks → `used=60`. This shows the exact boundary `cur+size>limit` at `MemtablePool.java:156`.
- Separately, to exercise overshoot: `allocator.allocate(90, group)` (used=90, under 100), `setDiscarding()` (marks it reclaiming), then `allocate(30, group)` with the group's barrier `markBlocking()`'d first — expect `used()` to jump to `120`, i.e. **past** `limit=100`, confirming the bypass at `MemtablePool.java:177-185`.

**B2d. Observables and instruments.** Direct method calls, no external tool needed: `pool.onHeap.used()` (`MemtablePool.used()`, `MemtablePool.java:216-219`), `allocator.onHeap().owns()` (`MemtableAllocator.java:280-283`), `allocator.onHeap().getReclaiming()`, and whether the test thread calling `allocate()` is blocked (checked with `Future.get(timeout)` from the driving executor, as `NativeAllocatorTest` does with `exec.submit(test).get()` and `Uninterruptibles.sleepUninterruptibly`). Cannot be observed directly: actual JVM heap bytes consumed by the allocation (this tier never allocates real buffers of that size — `allocate()`'s `size` argument here is just an accounting integer, not a real buffer); that is left to the cluster tier.

**B2e. Procedure.**
1. Clone pinned tag to local disk, build with `ant jar` (B2a).
2. Add `MemtablePoolLimitTest.java` under `test/unit/org/apache/cassandra/utils/memory/`.
3. `ant test -Dtest.name=MemtablePoolLimitTest -Dtest.methods=testHardLimitBlocks`
4. `ant test -Dtest.name=MemtablePoolLimitTest -Dtest.methods=testDiscardingOvershoots`
5. Inspect JUnit XML/console output under `build/test/output/` for assertion results and the logged `used()` values at each step (add `System.out.println` or assert messages, since this is an ad hoc test, not shipped).

**B2f. Predictions.**
- `testHardLimitBlocks`, `limit=100`: after first `allocate(60)`, `used()==60`. Second `allocate(60)` from worker thread does **not** return within 200 ms (blocked), and `used()` stays `60` while blocked. After main thread calls `released(60)`, the worker's `allocate(60)` returns within the test timeout (≤5 s) and final `used()==60`.
- `testDiscardingOvershoots`, `limit=100`: after `allocate(90)`, `used()==90`. After `setDiscarding()` + `allocate(30)` while the op-group `isBlocking()`, the call returns **immediately** (no block) and `used()==120`, i.e. `used() > limit`, confirmed `>` by exactly `20`.
- If instead the second scenario shows `used()` capped at `100` or the call blocks, the traced bypass (A3 step 6) does not exist as read, and the claim is wrong.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `used()==60` after first allocate, second allocate blocks until release, then `used()==60` again | `tryAllocate`'s `cur+size>limit` check works as traced; it is the enforcement point |
| Second allocate does **not** block, `used()` silently exceeds 100 without `markBlocking()`/`setDiscarding()` | contradicts claim — some other path besides A3 step 6 bypasses the check; re-trace |
| `testDiscardingOvershoots`: `used()==120 > limit=100` with no blocking | confirms the deliberate, bounded overshoot of A3 step 6 |
| `testDiscardingOvershoots`: call blocks or `used()` stays ≤100 | the bypass path does not exist as read from `MemtableAllocator.java:180-184`; claim about mechanism is wrong on this point |

**B2h. Controls.** Run each scenario twice with `limit` doubled (`200` instead of `100`, sizes doubled too) to confirm the blocking/overshoot boundary scales with `limit`, not some hidden constant. Run `testHardLimitBlocks` with the second `allocate` on the *same* thread as a negative control (expect deadlock/timeout — demonstrates why the test must use a second thread, and that blocking is real, not a no-op). No `DatabaseDescriptor`, no yaml, no CQL involved, so results are attributable only to `MemtablePool`/`MemtableAllocator`, not to config parsing or table/compaction code.

### B3. Cluster tier

**B3a. Environment and build.**
```
git clone <local-path-to-pinned-clone> /tmp/cass509-cluster1   # one clone per node, all on local disk
cd /tmp/cass509-cluster1 && git checkout cassandra-5.0.9 && JAVA_HOME=<jdk11> ant jar
```
Single node is enough (the limit is per-node); use 1 node to keep the blast radius minimal, optionally 2 nodes (RF=1 each) only to confirm the limit is per-node, not cluster-wide. Local directories (not shared storage): `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` all under `/tmp/cass509-cluster1/data/*` on local disk; cap `/tmp` usage by pre-creating a dedicated local volume/dir of known size, e.g. 2 GiB, and setting `commitlog_total_space_in_mb: 512` to keep commitlog bounded.
`cassandra.yaml` edits (local clone only):
```
memtable_heap_space: 64MiB
memtable_allocation_type: heap_buffers
memtable_cleanup_threshold: 0.5
```
JVM: in `conf/jvm11-server.options` (or `-D`/`-X` override at startup) set `-Xmx512m -Xms512m` so the 64 MiB memtable cap is a clearly distinguishable fraction of total heap, and so JFR/JMX heap histograms are small enough to read quickly. Start with `bin/cassandra -f` (foreground, so the process is easy to track and stop).

**B3b. Knobs.**
- `memtable_heap_space`: `64MiB` (boundary value, small enough to hit within seconds of writes) vs. a control run at `512MiB` (large enough that the same workload never approaches it, to show the flush-triggering behavior disappears) — both well under `-Xmx512m` so GC pressure doesn't confound the reading.
- `memtable_cleanup_threshold`: `0.5` (flush triggers at 50% of the heap-space cap, i.e. 32 MiB for the 64 MiB run), to get an early, clearly-visible flush point distinct from the hard cap.
- `memtable_allocation_type: heap_buffers` (the default; keeps everything on-heap so the heap reading is the full signal, no off-heap component to separate).

**B3c. Workload.** A single table with wide values, written through `cassandra-stress` or `cqlsh`/driver, sized to comfortably exceed 64 MiB of live (serialized + object-overhead) data before any flush would occur if the cap didn't work, and to require several flush cycles if it does:
- Table: `CREATE TABLE ks.t (k int PRIMARY KEY, v blob)`.
- Write 20,000 rows of a 8 KiB blob each = 20,000 × 8 KiB ≈ 156 MiB of raw cell data (plus per-row/object overhead, typically 2-3×, so expected live heap footprint before any flush is roughly 300-470 MiB) — well past the 64 MiB on-heap cap, and past even the 512 MiB `-Xmx` if unthrottled, so if the cap is not enforced the node will visibly approach OOM or at minimum accumulate far more than 64 MiB of memtable heap.
- Drive with: `cassandra-stress write n=20000 cl=ONE -schema 'replication(factor=1)' -col 'size=FIXED(8192)' -rate threads=4` (or an equivalent `cqlsh` `COPY`/batch script), run against the single node.
- Duration: a few minutes; monitor continuously during the run, not just at the end, to see memtable heap rise and fall with each flush.

**B3d. Observables and instruments.**
- `nodetool tablestats ks.t` / `nodetool cfstats` — "Memtable data size" and "Memtable off heap memory used" per flush, sampled every 5 s during the run via a loop (`watch -n5 nodetool cfstats ks.t`).
- JMX attribute `org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=MemtableOnHeapDataSize` (or the global `AllMemtablesOnHeapDataSize`) polled via `jmxterm`/`nodetool` at the same cadence — this is the clearest proxy for `SubPool.used()` observed from outside the process.
- JFR or `jcmd <pid> GC.heap_info` / `jstat -gcutil <pid> 1000` for actual JVM heap occupancy, to confirm the *real* resource (not just the accounting metric) stays bounded.
- `system.log` lines "Flushing largest ... to free up room" (emitted at `AbstractAllocatorMemtable.java:293-295`) — confirms the cleaner fired, and at roughly what heap fraction.
- Cannot observe directly: the exact moment `tryAllocate` returns `false` inside the JVM (internal CAS, not instrumented/logged) — inferred only from the flush log line and from JMX metrics staying near the configured cap rather than growing unbounded.

**B3e. Procedure.**
1. Clone+build per B3a; create local data dirs; edit yaml (64 MiB run).
2. `bin/cassandra -f > /tmp/cass509-cluster1/node.log 2>&1 &` ; record PID.
3. `bin/cqlsh -e "CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE ks.t (k int PRIMARY KEY, v blob);"`
4. Start a background poller: `while true; do date; nodetool tablestats ks.t | grep -i "memtable"; done | tee /tmp/cass509-cluster1/poll.log &` (sample every 5s via a sleep in the loop).
5. Run the stress workload from B3c.
6. Tail `/tmp/cass509-cluster1/node.log` for "Flushing largest" lines during the run.
7. After the run, `jstat -gcutil <pid>` once more; stop the poller.
8. Repeat steps 1-7 with `memtable_heap_space: 512MiB` (control) in a fresh local clone/data dir.
9. Stop the node(s): `nodetool stopdaemon` or `kill <pid>`; confirm with `ps -ef | grep cassandra` that nothing remains; `rm -rf /tmp/cass509-cluster1 /tmp/cass509-cluster2` (or wherever local dirs were placed) once results are recorded.

**B3f. Predictions.**
- 64 MiB run: "Memtable data size" in `nodetool tablestats` should rise, peak **in the tens of MiB** (roughly 30-65 MiB, i.e. around the 32 MiB cleanup threshold up through the 64 MiB hard cap, with brief, bounded overshoot per A3 step 6), then drop sharply (flush) and repeat in a sawtooth — never sustained far above ~64 MiB for more than the time it takes one flush to complete. At least 2-3 "Flushing largest" log lines should appear given ~300+ MiB of total write volume against a 64 MiB cap.
- 512 MiB control run: same total write volume (~300-470 MiB) stays under the cap the whole time; "Memtable data size" should rise roughly monotonically to the final total with **zero or very few** "Flushing largest ... MEMTABLE_LIMIT" log lines (periodic/size-triggered flushes from unrelated causes aside).
- If instead the 64 MiB run's memtable data size climbs past, say, 200+ MiB with no corresponding flush log lines, or the node OOMs, that falsifies the claim that `memtable_heap_space` bounds actual on-heap memtable usage.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Memtable data size sawtooths in the 30-65 MiB band, with periodic "Flushing largest" log lines, 64 MiB run | cap is enforced on real heap usage as traced |
| Memtable data size grows unbounded past ~100 MiB with no flush triggered, 64 MiB run | cap is not enforced; contradicts claim |
| 512 MiB control shows no flush triggers for the same workload | isolates that the 64 MiB run's flushing is caused by the cap, not by unrelated flush policies (e.g. periodic flush, commitlog size) |
| `jstat`/`jcmd` heap occupancy roughly tracks `nodetool` memtable data size plus a stable baseline | confirms the JMX/nodetool metric reflects real JVM heap, not just internal bookkeeping disconnected from actual memory |
| Node OOMs or GC overhead limit exceeded during the 64 MiB run | strong evidence the cap failed to bound real usage |

**B3h. Controls.** The 512 MiB control run with identical workload isolates the effect of the knob (same table, same stress command, same JVM flags, only `memtable_heap_space` differs) from unrelated flush triggers (`memtable_flush_period_in_ms`, commitlog segment flushing, `nodetool flush` calls) — none of which are invoked in this procedure. Confirming flush log lines explicitly say `MEMTABLE_LIMIT` as the `FlushReason` (`ColumnFamilyStore.FlushReason.MEMTABLE_LIMIT`, used at `AbstractAllocatorMemtable.java:297`) rather than `MEMTABLE_PERIOD_EXPIRED` or `SCHEMA_CHANGE` rules out other flush causes explaining the sawtooth.

**B4. Risks and cleanup.** Both tiers run entirely from local-disk clones (`/tmp/cass509-unit`, `/tmp/cass509-cluster1[/2]`), never inside the shared pinned source tree, and never write test data anywhere but those local dirs. Disk: cap commitlog/data dirs with `commitlog_total_space_in_mb` and bound the write workload (~300-470 MiB raw, well under the pre-allocated 2 GiB local volume). Leftover processes: track the `bin/cassandra` PID explicitly at start, stop it with `nodetool stopdaemon`/`kill` at the end of each run, and verify with `ps -ef | grep cassandra` that no JVM remains before deleting the local directories; also kill any background `nodetool`/polling loop (`kill %1` or by PID) started in B3e step 4. Delete the local clones and data directories once results are recorded (`rm -rf /tmp/cass509-unit /tmp/cass509-cluster1 /tmp/cass509-cluster2`).

## C. Paths read

```
src/java/org/apache/cassandra/utils/memory/MemtablePool.java
src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
src/java/org/apache/cassandra/utils/memory/SlabPool.java
src/java/org/apache/cassandra/utils/concurrent/OpOrder.java
src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/DataStorageSpec.java
conf/cassandra.yaml
test/unit/org/apache/cassandra/db/memtable/MemtableSizeTestBase.java
test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java
test/unit/org/apache/cassandra/utils/memory/MemtableCleanerThreadTest.java
```
