# none — verification solution  <!-- file: cases/none-allocateoversize-peer--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`NativeAllocator.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L194) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the checked line is an assertion on the allocator's own offset arithmetic and caps nothing; the oversize region it guards is malloc'd directly and is bounded only indirectly, by the accounting at NativeAllocator.java:141, not by this line. |
| Ground | The `-1` branch cannot be reached for a fresh region sized exactly `size` (NativeAllocator.java:190, 269-277), so the line enforces no memory or disk limit. The oversize path (`size > MAX_CLONED_SIZE`, 128 KiB) does allocate real off-heap memory outside the slab regions, and the amount is counted against `memtable_offheap_space` by the call at line 141 before the malloc, which is a different mechanism from the line under test. |

> **Link rule.** Followed: the declaration (A1) and the if statement (Entry pointer, A3) are permalinks at `cassandra-5.0.9`.

## A. Constraint trace

**A1. The constraint.** There is no constraint at the target line. The line is
[`NativeAllocator.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L194)
(`if ((peer = region.allocate(size)) == -1)`), followed by `throw new AssertionError();` at line 195, inside `allocateOversize(int size)` (lines 186-198). The earlier trace's line numbers for the method and the check are correct; its claim that the Region's `allocate` is at "269-277" is also correct (verified).

Nearest related items, all verified against the tree:

- `MAX_CLONED_SIZE = 128 * 1024` declared at [`NativeAllocator.java:47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L47). Kind: constant. Unit: bytes. Default: literal, not derived. Settable: no (no yaml key, `-D` property or JMX; a code edit and rebuild would be needed; a restart is irrelevant). It only routes allocations larger than 128 KiB to `allocateOversize` (line 144-145) instead of the shared regions. It bounds the size of an object placed in a slab; it does not bound total usage.
- `MAX_REGION_SIZE = 1 MiB` ([`NativeAllocator.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L46)) and `MIN_REGION_SIZE = 8 KiB` (line 48): slab sizing constants, not settable, not caps on total usage.
- The memory-significant limit on this path is `memtable_offheap_space` (yaml key; type `DataStorageSpec.IntMebibytesBound`, declared at [`Config.java:189`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L189)). Unit: MiB. Default: `maxMemory() / (4 * 1048576)` MiB, i.e. one quarter of the max heap, set in DatabaseDescriptor.java:583-584. Set in `cassandra.yaml` (`memtable_offheap_space`, commented at conf/cassandra.yaml:799) and needs a restart (read once when the pool is created, AbstractAllocatorMemtable.java:81-83 and 59). It is only used when `memtable_allocation_type` is `offheap_objects` (the only type that builds a `NativePool`, AbstractAllocatorMemtable.java:106-108); the default type is `heap_buffers` (Config.java:524, conf/cassandra.yaml:825), under which `NativeAllocator` is never instantiated. Whether a Config-level declaration of `memtable_offheap_space` is "first declared" at Config.java:189 is verified; the default is applied in DatabaseDescriptor.

**A2. What it caps.** The line caps nothing. It checks that an allocation of `size` bytes fits in a region of capacity `size`: the operand is the region's `nextFreeOffset` plus `size` versus `capacity` (NativeAllocator.java:271-273). The resource that the surrounding path touches is off-heap (native) memory of memtables under `offheap_objects`. The quantity compared against `memtable_offheap_space` is `SubPool.allocated + size` versus `limit` (MemtablePool.java:156), reached through `offHeap().allocate(size, opGroup)` (NativeAllocator.java:141, MemtableAllocator.java around 160-190).

**A3. Mechanism.**
1. `NativeAllocator.allocate(int size, OpGroup)` calls `offHeap().allocate(size, opGroup)` first (NativeAllocator.java:141). That `SubAllocator.allocate` loops: `parent.tryAllocate(size)` succeeds if `allocated + size <= limit` (MemtablePool.java:151-161); if not and the op group is blocking, it records the bytes anyway (overshoot) via `allocated(size)`; otherwise it waits on `hasRoom` until a flush frees space (MemtableAllocator.java, the `allocate` method, `parent.hasRoom().register(...)` and `signal.awaitThrowUncheckedOnInterrupt()`). Line numbers inside MemtableAllocator for this method: not individually re-verified beyond the method body shown above.
2. If `size > MAX_CLONED_SIZE` (line 144) the call goes to `allocateOversize` (line 145).
3. `allocateOversize` calls `MemoryUtil.allocate(size)` (a native malloc of exactly `size`) and wraps it in `new Region(peer, size)` (line 190), adds it to `regions` (line 191), then asks the region for `size` bytes.
4. The if statement is [`NativeAllocator.java:194`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java#L194). `Region.allocate` does `getAndAdd(size)` on `nextFreeOffset` (starting at 0, line 250) and returns -1 only if `newOffset + size > capacity` (lines 269-277). With `newOffset == 0` and `capacity == size` the test is `size > size`, false, so `-1` cannot occur here. Outcome when true: `AssertionError`, i.e. a bug in the allocator; outcome when false (always): the native address is returned (line 197).
5. Memory is released only when the memtable is discarded: `setDiscarded` frees every region in `regions` (lines 200-206) and then `super.setDiscarded()` releases the accounting. An oversize region is never freed or reused before that.

Bypasses and overshoots: (a) the blocking-op-group path in step 1 lets `allocated` exceed `limit` temporarily so that a flush can begin (MemtableAllocator.java, comment at `setDiscarding`, "permit any outstanding allocations to temporarily overshoot"); (b) the accounted size is the requested `size`, not the malloc'd chunk including allocator overhead, so real RSS can exceed the accounted value (reasoning from the code; the size of the gap not verified); (c) slab regions are accounted per allocation (line 141) not per region, but real slab memory is whole regions up to 1 MiB each (trySwapRegion, lines 158-184), and race-lost regions are stashed up to 8 per size (line 212), so actual native memory is somewhat above the accounted amount; (d) the per-region `size` cast `(int) size` in NativeCell.java:104 means a single cell is limited to what an `int` and the write-path size limits allow.

**A4. Other consumers.** Off-heap memory used outside `memtable_offheap_space`: the chunk cache and buffer pool (not traced), bloom filters and index summaries, compression metadata, direct buffers for networking, and the commit log's mapped segments. On-heap per-memtable overhead for `offheap_objects` (the `NativeAllocator` constructor also creates an on-heap `SubAllocator`, NativeAllocator.java:65) is bounded by `memtable_heap_space` (Config.java:187). Not verified in detail: which of these are significant for the chosen workload.

**A5. Evidence beyond the source.** None relied on. The unit test `test/unit/org/apache/cassandra/utils/memory/NativeAllocatorTest.java` exists in the tree; its content was not read.

## B. Verification solution

**B1. Claim under test.** Under `memtable_allocation_type: offheap_objects`, the line at NativeAllocator.java:194 never fires and does not bound native memory: allocations larger than 128 KiB are served by one direct malloc each, regardless of how many exist, and the only thing that limits their total is the pre-allocation accounting against `memtable_offheap_space` (which can overshoot), not the check at line 194. Falsified if the `AssertionError` is ever thrown, or if native memory of oversize allocations is shown to stop growing because of anything at line 194.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tag to local disk (e.g. `/local/cass-build`), never build in the shared tree. `ant jar` then a small Java program or a JUnit test under the copied tree's `test/unit` that is compiled with `ant build-test`. JVM options: `-Xmx1g -XX:MaxDirectMemorySize` not needed (the native allocator uses `Unsafe` malloc, not direct buffers; stated from the `MemoryUtil.allocate` use at line 190, implementation not read). Add `-Dcassandra.config=file:///local/cass-build/conf/cassandra.yaml` with `memtable_allocation_type: offheap_objects`.

**B2b. Knobs.** Two values of the pool's off-heap limit passed to `new NativePool(maxOnHeap, maxOffHeap, cleanThreshold, cleaner)` (NativePool.java:23): (1) large, 1 GiB; (2) small, 16 MiB. Allocation size: 64 KiB (below `MAX_CLONED_SIZE`), 128 KiB (equal, still a slab since the test is `>`, line 144), 128 KiB + 1, 1 MiB, 4 MiB (oversize). Set by constructor arguments and by the size argument of `allocate`.

**B2c. Workload.** Create a pool and `pool.newAllocator("t")` (NativePool.java:29), then call `allocator.allocate(size, group)` with an `OpOrder.Group` from a fresh `OpOrder` (`new OpOrder().start()`), N times. For limit 16 MiB and size 1 MiB, 16 allocations reach the limit (16 x 1 MiB = 16 MiB), allocation 17 should block unless the group is blocking. Run the loop in a separate thread with a timeout to observe blocking. For slab sizes, 100 allocations of 64 KiB = 6.25 MiB.

**B2d. Observables and instruments.** (1) The sub-pool's `allocated` and `limit` (package-private fields, read by placing the test class in package `org.apache.cassandra.utils.memory` or by reflection; MemtablePool.java:105, 111). (2) The number and capacity of `regions` entries (private; reflection). (3) Whether `AssertionError` is thrown (catch `Throwable`). (4) Process RSS of the test JVM from `/proc/<pid>/status` (VmRSS) before and after. Cannot be observed directly: the true malloc overhead per chunk.

**B2e. Procedure.**
1. `rsync -a /users/jason92/cassandra-5.0.9/ /local/cass-build/` then `cd /local/cass-build && ant jar build-test`.
2. Write the test class in the copied tree, run with `ant testsome -Dtest.name=<Class>` or `java -cp build/classes/main:build/test/classes:lib/* <Class>`.
3. For each (limit, size) pair: build a fresh pool, allocate N times, record `allocated`, region count, RSS, exceptions; then `allocator.setDiscarding()` and `setDiscarded()` and record again.
4. Positive control: repeat with `size` = 64 KiB under the same limit and show `allocated` grows by `size` per call up to the limit and the next call blocks (limit binding).
5. Repeat the oversize case with a blocking `OpOrder.Group` (one whose `isBlocking()` is true, produced by calling `order.newBarrier()` ... `issue()` while the group is open) to show the overshoot path.

**B2f. Predictions.** (stated before any run)
- No `AssertionError` for any size or limit.
- For oversize sizes: region count rises by exactly 1 per call, each with capacity equal to the size, and `allocated` rises by exactly `size` per call.
- With limit 16 MiB and 1 MiB oversize allocations: calls 1-16 return immediately, call 17 blocks (accounting binds), but the check at line 194 plays no part; with a blocking group call 17 returns and `allocated` exceeds `limit`.
- RSS grows by at least the sum of allocated bytes only once memory is touched; untouched malloc'd memory may not appear in RSS (expectation, not verified), so also touch the memory (write a byte per page) when measuring RSS.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| No `AssertionError` in any run; region count = number of oversize calls | Line 194 is a sanity check only; claim confirmed for the mechanism. |
| `AssertionError` thrown at line 195 | Claim wrong: the branch is reachable (investigate size/overflow). |
| `allocated` stays at or below `limit` and call 17 blocks while the small-slab positive control behaves the same | Accounting at line 141 (not line 194) limits oversize allocations; line 194 irrelevant. |
| Oversize usage tracks the limit only through `allocated`, flat with respect to anything in line 194, while the positive control (64 KiB allocations) moves `allocated` and blocks at the limit | Claim (usage does not follow the check at 194) confirmed. |
| Oversize allocations with a blocking group push `allocated` above `limit` | Documented overshoot path exists. |
| Positive control does not move `allocated`, or the limit is never reached | Not confirmed (workload too small or wrong allocation type). |

**B2h. Controls.** The 64 KiB / 128 KiB slab sizes as positive control; same pool and limit; fresh pool per run so that earlier regions do not carry over; `System.gc()` before RSS reads; run each pair twice.

### B3. Cluster tier

**B3a. Environment and build.** One node on Linux, JDK 11, Ant, built from a local copy (`/local/cass-build`, `ant jar`). Local data, commitlog, hints and saved_caches directories on local disk of known free size (at least 20 GiB). `cassandra.yaml`: `memtable_allocation_type: offheap_objects`, `memtable_offheap_space: 256MiB` (also run with `1024MiB`), `memtable_heap_space: 256MiB`, `commitlog_segment_size: 32MiB`, `max_mutation_size` left at default (half of segment size; derivation not re-verified here). JVM: `-Xms1g -Xmx1g` in `conf/jvm11-server.options` (heap kept fixed so off-heap is separable). Disable auto-compaction pressure is not needed.

**B3b. Knobs.** `memtable_offheap_space` = 64MiB, 256MiB, 1024MiB; cell value size = 64 KiB (slab path) versus 512 KiB (oversize path, `> 128 KiB`); `memtable_allocation_type` = `offheap_objects` versus `heap_buffers` (negative control for the whole mechanism). Each set in `cassandra.yaml`, restart required.

**B3c. Workload.** Table `t(k int, c int, v blob, PRIMARY KEY (k, c))` with `caching = {'keys':'NONE','rows_per_partition':'NONE'}`. Use `cassandra-stress` or a driver script to write blobs through CQL `INSERT` at consistency ONE, with the node's flush disabled by large limits where possible, or simply measure across flushes. Arithmetic: with limit 256 MiB and 512 KiB cells, 512 inserts = 256 MiB, so 2000 inserts (about 1 GiB) is about 4x the limit; with 64 KiB cells, 4096 inserts = 256 MiB, 16000 inserts about 4x. Duration: minutes; stop after the data volume is written plus 2 minutes for flush to settle.

**B3d. Observables and instruments.** (1) Process RSS and native memory: `/proc/<pid>/status` VmRSS sampled every second; `jcmd <pid> VM.native_memory summary` if the node is started with `-XX:NativeMemoryTracking=summary` (note: `Unsafe` malloc may show under "Other"; not verified). (2) Heap via `jstat -gc`. (3) Memtable accounting via JMX/nodetool: `nodetool tablestats` fields "Memtable off heap memory used", and `nodetool tpstats` for flush activity; metrics `org.apache.cassandra.metrics:type=MemtablePool,name=BlockedOnAllocation` (registered in MemtablePool.java:63). (4) `system.log` lines "Global memtable off-heap threshold is enabled at" (DatabaseDescriptor.java:594) to confirm the knob took effect. (5) Any `AssertionError` in `system.log`. Cannot observe directly: per-region layout.

**B3e. Procedure.**
1. Build the copy; set the yaml and JVM options; create data directories under `/local/...`.
2. Start the node; confirm the log line for `memtable_offheap_space`.
3. Create keyspace/table; record baseline RSS and tablestats.
4. For each (limit, cell size, allocation type): reset the node (stop, wipe data dirs, start), write the workload, sample as above, then `nodetool flush` and sample again.
5. Positive control run: `memtable_allocation_type: offheap_objects`, 64 KiB cells, limit 64 MiB, showing memtable off-heap memory used rising and being capped by flushes.
6. Stop the node; confirm no `CassandraDaemon` process remains.

**B3f. Predictions.** (stated before any run)
- No `AssertionError` in any log.
- With 64 KiB cells (positive control) the "Memtable off heap memory used" value rises toward the configured limit and then drops after flushes; it does not stay far above the limit for long.
- With 512 KiB cells the same relation holds through the pre-allocation accounting (line 141), so the memtable flushes when the accounted amount nears the limit; the check at line 194 plays no visible role. RSS growth beyond the accounted number is expected to be modest (malloc overhead and in-flight writes) and to scale with the number of concurrent writes, not with line 194.
- With `heap_buffers`, off-heap memtable usage is near zero whatever `memtable_offheap_space` is (negative control).
- Raising `memtable_offheap_space` from 64 to 1024 MiB raises the peak accounted off-heap memtable value roughly proportionally (expectation).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| No `AssertionError`; peak memtable off-heap tracks `memtable_offheap_space` for both cell sizes | Usage follows the accounting limit, not line 194; claim confirmed. |
| `AssertionError` from `allocateOversize` in a log | Claim wrong: line 194 branch reachable. |
| Peak memtable off-heap flat when the limit is varied 64 to 1024 MiB while the 64 KiB positive control moves | Limit does not govern oversize usage; strong support that oversize bypasses the accounting. |
| Peak RSS much higher than the accounted value for 512 KiB cells and growing with write concurrency | Overshoot path confirmed (A3 bypass a/b). |
| Positive control does not move memtable off-heap usage, or the limit is never reached | Not confirmed; check allocation type and workload size. |
| Under `heap_buffers`, off-heap memtable usage stays near zero | Control passes: `NativeAllocator` is only active under `offheap_objects`. |

**B3h. Controls.** `heap_buffers` run; 64 KiB-cell run as slab-path positive control; identical heap size and workload across runs; wipe data between runs; verify the yaml log line each start; compare RSS with and without data written so that baseline off-heap use (A4) is subtracted.

**B4. Risks and cleanup.** Disk: workload writes about 1 GiB plus commitlog per run; keep data dirs on local disk of known size (>= 20 GiB) and delete after each run. Never build or add files in the shared tree; use the copy. Leftover processes: stop the node (`nodetool drain` then kill the PID), stop `jstat`/sampling loops, then check `pgrep -f CassandraDaemon` and `pgrep -f jstat` return nothing. Unit tier: the test JVM exits on completion; confirm with `pgrep -f <test class>`. Remove `/local/cass-build` and data directories when done.

## C. Sources read

- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/INSTRUCTIONS.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/playbook-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-docs/_TEMPLATE-autonomous.md
- /tmp/claude-20001/-proj-misconfiguration-PG0-git-repos-Misconfiguration/d3cfd622-d93d-5998-b33d-926864ab48d4/scratchpad/agent-in/159.md
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativeAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtablePool.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/NativePool.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep lines 185-190, 524)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 580-596, grep of getters)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/NativeCell.java, db/NativeClustering.java, db/NativeDecoratedKey.java (grep of allocate calls)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (lines 794-825)

## D. Stage-4 feedback

`none yet`
