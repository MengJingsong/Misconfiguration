# NativeCell per-cell off-heap size cap (Integer.MAX_VALUE) — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/rows/NativeCell.java:100` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `negative`. The line is a constant 2^31-1 guard on one cell's allocation size. It bounds neither the aggregate off-heap memtable footprint nor any size the write path can reach, because upstream limits (max_value_size, max_mutation_size) stop a cell long before. |
| Ground | The operand is a single object's byte count, compared against a hard-coded int range limit that exists to make `(int) size` (line 104) safe. Total off-heap use is governed by a different constraint (`memtable_offheap_space`, a soft flush trigger), and the per-cell size is capped by mutation/value limits of at most 256 MiB by default. Usage therefore does not follow this constant. |

## A. Constraint trace

**A1. The constraint.** Name: the literal `Integer.MAX_VALUE` in `if (size > Integer.MAX_VALUE) throw new IllegalStateException()` (`NativeCell.java:100-101`). Kind: constant (hard-coded, no config entry). First declared there; not settable by yaml, `-D` or JMX, changes only by recompiling. Unit: bytes (2^31-1, about 2 GiB). Default derivation: none, it is the int range, forced by `allocator.allocate((int) size, writeOp)` at line 104 and `NativeAllocator.allocate(int size, ...)` (`utils/memory/NativeAllocator.java:138`). The related, actually configurable limits that sit upstream:
- `max_value_size`, default 256MiB, must be < 2048 MiB (`config/Config.java:310`, `config/DatabaseDescriptor.java:944-948`). It is enforced when deserializing values (`db/rows/Cell.java:339`, `AbstractType.java:596`).
- `max_mutation_size`, default commitlog_segment_size/2 = 16 MiB with the default 32MiB segment (`DatabaseDescriptor.java:898-901`; `conf/cassandra.yaml:652-660`).
- `native_transport_max_frame_size`, default 16MiB (`Config.java:285`).
- `memtable_offheap_space`, default maxMemory/4 (`DatabaseDescriptor.java:583-584`), used only with `memtable_allocation_type: offheap_objects` (`conf/cassandra.yaml:825`, default `heap_buffers`).

**A2. What it caps.** Resource: off-heap (native malloc) memory, for one cell in an `offheap_objects` memtable. The compared quantity is `size` = 21-byte header (`VALUE`, line 42) + `value.remaining()` (line 90) + for complex columns 4 + path length (line 97), as a long.

**A3. Mechanism.**
1. `NativeAllocator$CloningBTreeRowBuilder.addCell` (`NativeAllocator.java:90`) and `NativeAllocator` line 128 construct `new NativeCell(...)`. These are the only two production call sites (grep of `src/java`).
2. The constructor computes `size` (lines 90-98) in a long. `value.remaining()` is an int, so size exceeds 2^31-1 only when the value is within 21 bytes of 2 GiB (or more with a path).
3. If `size > Integer.MAX_VALUE`, an `IllegalStateException` is thrown (lines 100-101). Otherwise `allocator.allocate((int) size, writeOp)` (line 104) first calls `offHeap().allocate(size, opGroup)` (`NativeAllocator.java:141`), which charges the pool and may block on `parent.hasRoom()` (`MemtableAllocator.java:169-196`). It then calls `MemoryUtil.allocate` (malloc) directly for sizes > 128 KiB (`MAX_CLONED_SIZE`, `NativeAllocator.java:47,144-145,186-190`), or carves from a region of at most 1 MiB.
4. Bypass or overshoot: the pool limit is checked in `tryAllocate` (`MemtablePool.java:151-160`), but when the op group is blocking the allocation is recorded anyway (`MemtableAllocator.java:177-181`), so the off-heap total can overshoot `memtable_offheap_space`. The line-100 check is independent of all of this.
5. Reaching line 100 is blocked earlier: `Mutation.validateSize` rejects mutations over `max_mutation_size` (`Mutation.java:169-176`; called from `MutationVerbHandler.java:54`, `CommitLog.java:304`, `SingleTableUpdatesCollector.java:112`, `BatchUpdatesCollector.java:149`). Default is 16 MiB, so a cell above that never reaches the memtable through the normal path. Only `max_mutation_size` raised toward 1 GiB (with `commitlog_segment_size` >= 2x, itself bounded by the int range) plus `max_value_size` just below 2048 MiB would make the guard reachable, and even then the frame/message limits apply on the client path.

**A4. Other consumers.** Other off-heap users: partition keys and clustering (`NativeDecoratedKey`, `NativeClustering`) in the same pool; Netty direct buffers; chunk cache; bloom filters, index summaries, compression metadata; OS page cache. None is controlled by line 100.

**A5. Evidence beyond the source.** none (code and `conf/cassandra.yaml` comments only).

## B. Verification solution

**B1. Claim under test.** The `Integer.MAX_VALUE` guard at `NativeCell.java:100` does not bound off-heap memory use in a meaningful way: with default or any practical settings it is never reached, a cell is limited much earlier (by `max_mutation_size`, 16 MiB default), and the aggregate off-heap footprint is determined by what is written and by `memtable_offheap_space`, not by this constant. The guard only prevents an int overflow for a hypothetical cell of about 2 GiB.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`), `cd /local/c509 && ant jar` (or `ant build-test`). Write a JUnit test `test/unit/org/apache/cassandra/db/rows/NativeCellSizeProbeTest.java` in the local copy, run with `ant testsome -Dtest.name=NativeCellSizeProbeTest`. JVM options: `-Xmx4g -XX:MaxDirectMemorySize=1g` plus the test defaults. The test uses `DatabaseDescriptor.daemonInitialization()` with `memtable_allocation_type=offheap_objects` and `memtable_offheap_space=64MiB`.

**B2b. Knobs.**
- Value length L passed to `new NativeCell(allocator, group, column, ts, ttl, ldt, ByteBuffer.allocate(L), null)`: 1 KiB, 200 KiB (above `MAX_CLONED_SIZE`, 128 KiB), 16 MiB, 255 MiB. All fit the heap and are far below the guard.
- Guard probe: L = Integer.MAX_VALUE - 20 (size = 2^31-1, passes) and Integer.MAX_VALUE - 19 (size = 2^31, throws). A `ByteBuffer` that large is unrealistic on heap, so use a mocked `ByteBuffer` subclass or a `ByteBuffer.allocateDirect` view with `remaining()` overridden (or mmap of a sparse file). If that is not possible, record the arithmetic and skip the two probe cases.
- Setting `max_mutation_size`: not applicable in this tier (no Mutation).

**B2c. Workload.** Create a `NativePool(heapLimit=0, offHeapLimit=64MiB, 0.25f, cleaner)` then `pool.newAllocator("t")` (`AbstractAllocatorMemtable.java:108` shows the construction) and construct N cells of each L. Arithmetic: for L=200 KiB, 64 MiB / (200 KiB + 21) = about 327 cells fill the pool, so N=400 exceeds it. Total native bytes = N * (L + 21).

**B2d. Observables and instruments.**
- `allocator.offHeap().owns()` (pool accounting) and `cell.offHeapSize()` (`NativeCell.java:196`), sampled after each construction.
- Actual native memory: `jcmd <pid> VM.native_memory summary` (needs `-XX:NativeMemoryTracking=summary`) or `/proc/self/status` VmRSS before and after.
- Exceptions thrown (type, line from stack trace).
Not observable directly: malloc overhead per allocation.

**B2e. Procedure.**
1. Build as in B2a.
2. For each L in {1 KiB, 200 KiB, 16 MiB, 255 MiB}, construct 10 cells with a blocking-safe `OpOrder.Group` and record `offHeapSize()` of each and the `owns()` delta.
3. Run the guard probe from B2b (or the arithmetic fallback), recording the exception for size = 2^31.
4. Run the positive control: the same cells with `offHeapLimit=8MiB` and a non-blocking group; record that `owns()` exceeds the limit (the soft cap overshoot) and that a blocking group waits on `hasRoom()` (use a separate thread and a timeout).
5. Free: `allocator.setDiscarding(); setDiscarded()`.

**B2f. Predictions** (before any run).
- Each cell: `offHeapSize() == L + 21` (no path), exactly; `owns()` grows by the same amount.
- No `IllegalStateException` for any L up to 255 MiB.
- The guard probe: size 2^31-1 passes the check; size 2^31 throws `IllegalStateException` with no message, thrown before any allocation (`owns()` unchanged). This is the only value where line 100 acts.
- Positive control: `owns()` stays <= the limit while the group is non-blocking and room exists, and tracks the sum of cell sizes, not the guard.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `owns()` and `offHeapSize()` equal L+21 for all L; guard throws only at size >= 2^31 | Claim confirmed: line 100 is a pure overflow guard, no practical cap. |
| An exception at line 100 for any L <= 255 MiB | Claim refuted: the guard binds in the practical range. |
| `owns()` drops below the sum of cell sizes or is flat as N grows, while the positive control moves | Usage not following per-cell size; would need explanation (refutes the accounting model). |
| Total tracks N * (L+21) and is limited only by the pool limit (blocking) | Confirmed: the aggregate cap is the pool limit, not line 100. |
| Probe not constructible and positive control did not move | Not confirmed; rely on arithmetic only. |

**B2h. Controls.** Same code with `memtable_allocation_type=heap_buffers` (no `NativeCell` is built, `owns()` of off-heap pool stays 0) shows the cell path is what is measured. Repeat a size twice to rule out region reuse effects (`RACE_ALLOCATED`, `NativeAllocator.java:51`). Run once without NMT to exclude NMT overhead.

**B2i. Audit amendments (2026-10-25, stage-4 step 0, before any run; B2f and B2g keep their meaning, numbers and rows are added).**
1. *Arithmetic fix.* `size = 21 + L` (+ path). `L = Integer.MAX_VALUE - 20` gives size 2^31 (throws), not 2^31-1. The passing probe is **L = Integer.MAX_VALUE - 21** (size = 2^31-1 = `Integer.MAX_VALUE`); the throwing probe is **L = Integer.MAX_VALUE - 20** (size = 2^31). The B2f sentence (2^31-1 passes, 2^31 throws) stands.
2. *The probe is a real buffer, no mock.* `ByteBuffer` cannot be subclassed, so the probe uses `ByteBuffer.allocateDirect(Integer.MAX_VALUE - 20)` (about 2 GiB, native) with `limit()` set to the wanted L; the test JVM gets `-XX:MaxDirectMemorySize=6g` through `-Dtest.jvm.args`. The 16 MiB and 255 MiB sources are direct buffers too (the test JVM heap is 1 GiB). The unit class lives in package `org.apache.cassandra.utils.memory` so it can call the package-private `SubAllocator.released(long)`. Only the no-path cell is probed; the path term (line 97) is arithmetic only.
3. *Real resource.* `RssAnon` from `/proc/self/status` (not `VmRSS`), env `MALLOC_ARENA_MAX=1 MALLOC_MMAP_THRESHOLD_=65536 MALLOC_TRIM_THRESHOLD_=0`, baseline taken after the source buffer is allocated and filled.
4. *Arms (all in one test class).* **S** (sizes): pool limit 8 GiB, non-blocking group, 10 cells for each L in {1 KiB, 200 KiB, 16 MiB, 255 MiB}. **G1** (guard, big pool): pool 8 GiB, L = MAX-20 (expect throw), then L = MAX-21 (expect pass). **G2** (guard, small pool): pool 8 MiB, a blocking group (barrier `issue()` then `markBlocking()` as in `NativeAllocatorTest`), the same two L. **P** (positive control, the pool limit): cell L = 1 MiB, pool limit P in {8, 16, 32} MiB, non-blocking group: construct cells one by one in a worker thread until one does not return within 2 s; then call `allocator.offHeap().released(1 MiB + 21)` and require the blocked cell to complete within 5 s; with a blocking group the next cell must return at once. **O** (overshoot): pool 8 MiB, blocking group, one cell of 16 MiB. **H** (heap control): a heap `BufferCell` with a 16 MiB value built next to the same allocator; `owns()` stays unchanged. **R** (repeat): S with L = 200 KiB run twice. After each arm: `setDiscarding(); setDiscarded()`.
5. *Added numeric predictions (frozen with B2f).* (a) S: for all 40 cells `offHeapSize() == L + 21`; `owns()` after n cells equals the sum of the `offHeapSize()` values exactly; no exception; for L = 16 MiB and 255 MiB the `RssAnon` rise over the ten cells is within [0.90, 1.15] x 10 x (L + 21), and returns to within 10% of that rise plus 64 MiB after `setDiscarded()`. (b) G1/G2 throwing probe: `IllegalStateException`, `getMessage() == null`, the top stack frame is `NativeCell.<init>` at `NativeCell.java:101`, `owns()` unchanged, `RssAnon` rise below 64 MiB. G1/G2 passing probe: no exception, `offHeapSize() == 2147483647`, `owns()` rises by exactly 2147483647, and under G2 that is more than 255 times the 8 MiB pool limit. (c) P: the number of cells that complete before the first blocked cell is `floor(P / (1 MiB + 21))` = 7, 15, 31 for P = 8, 16, 32 MiB; `owns()` at the block equals that count x (1 MiB + 21); the blocked cell completes after the release; with a blocking group the next cell returns in under 1 s and `owns()` exceeds P. (d) O: the 16 MiB cell is accepted, `owns() == 16 MiB + 21`, which is more than 2x the pool limit. (e) H: `owns()` unchanged (a heap array's pages count in `RssAnon`, so its RSS rise is reported, not predicted). Amended 2026-10-25, before the harness, from a draft that predicted an RSS bound.
6. *Added rows for B2g.* (i) A throw at line 101 for any L <= 255 MiB, or admitted cells deviating from `floor(P / (1 MiB + 21))`: **Refuted**. (ii) The probe at L = MAX-21 throws, or the L = MAX-20 probe passes: the guard does not sit where B1 says; **Refuted** (or **Invalid** if the buffer could not be built). (iii) The big buffer cannot be allocated, or the P arm does not block at all: **Not confirmed**. (iv) `RssAnon` rise outside the band while the counters match: the resource and the counter diverge; **Not confirmed**, explain from the raw series.
7. *Source facts found by the audit (independent of any reading).* Citations re-read in `cassandra-5.0.9`: `NativeCell.java:90,97,100-101,104,196-201`, `NativeAllocator.java:47,51,90,128,138-145,186-197`, `MemtableAllocator.java:169-196`, `MemtablePool.java:151-160`, `Mutation.java:169-176`, `DatabaseDescriptor.java:583-584,898-901,943-948`, `Config.java:285,310,397,407,524`: all hold (the `allocate` loop is `MemtableAllocator.java:169-195`). Not as filed in A3.5: the `validateSize` calls are in `cql3/statements/SingleTableUpdatesCollector.java:112` and `BatchUpdatesCollector.java:149` (correct), but **the guard is unreachable by any production write**: `commitlog_segment_size` must be below 2048 MiB (`DatabaseDescriptor.java:890-895`) and at least twice `max_mutation_size` (`:898-901`), so a mutation, and with it a cell, is under 1 GiB, below the 2^31-21 byte values the guard needs; `max_value_size` below 2048 MiB is not the binding limit. A3.5's sentence that raising `max_mutation_size` toward 1 GiB plus `max_value_size` makes the guard reachable is wrong; B1 is unchanged and is strengthened.

### B3. Cluster tier

**B3a. Environment and build.** One node (second optional for RF=2), Linux, JDK 11, built from the local copy (`ant jar`). `cassandra.yaml` changes: `memtable_allocation_type: offheap_objects`, `memtable_offheap_space: 256MiB`, `memtable_heap_space: 256MiB`, defaults otherwise (`max_mutation_size` 16 MiB, `max_value_size` 256MiB, `native_transport_max_frame_size` 16MiB). `data_file_directories`, `commitlog_directory`, `hints_directory` on a local disk of known size (>= 20 GB free). JVM: `-Xmx2g -Xms2g -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=2g`. Disable auto-compaction effects by `nodetool disableautocompaction` and keep `nodetool` flushes explicit.

**B3b. Knobs.**
- (a) Blob size per cell S: 1 MiB, 8 MiB, 15 MiB (below max_mutation_size), 17 MiB (above it).
- (b) `max_mutation_size` default 16 MiB vs raised to 64 MiB with `commitlog_segment_size: 128MiB` and `native_transport_max_frame_size: 128MiB` (needs restart; yaml), to probe whether any setting moves the effective per-cell cap.
- (c) `memtable_offheap_space`: 256MiB vs 128MiB, to show the aggregate responds to a different knob.

**B3c. Workload.** Table `ks.t(pk int PRIMARY KEY, v blob)`, via cqlsh or a driver at CL=ONE, 1 writer thread (a script generating random blobs). Phase 1: write 100 rows of each S in turn; arithmetic: 100 x 15 MiB = 1.5 GB, well above 256 MiB, so flushes occur and the offheap pool limit is crossed several times. Phase 2: write one row of 17 MiB to see the rejection. Duration about 10 minutes per configuration. Positive control: the same write volume with `memtable_offheap_space=128MiB` shows off-heap usage moving with the pool knob.

**B3d. Observables and instruments.**
- Off-heap memtable use: `nodetool tablestats ks.t` ("Memtable off heap memory used") and the JMX metric `org.apache.cassandra.metrics:type=Table,name=MemtableOffHeapSize`, sampled every 2 s via `jmxterm`/`nodetool sjk mx`.
- Process memory: `jcmd <pid> VM.native_memory summary` and `/proc/<pid>/status` VmRSS every 5 s.
- Client result: error text and server log `grep -n "exceeds maximum allowed" logs/system.log` (`MutationExceededMaxSizeException`); metric `CommitLog.oversizedMutations` (`Mutation.java:173`).
- `grep IllegalStateException logs/system.log` for line 100 (expected absent).
Not observable: per-allocation malloc overhead and fragmentation.

**B3e. Procedure.**
1. Copy the tree to local disk, `ant jar`, set the yaml as B3a, start with `bin/cassandra -f` in a tmux session, wait for "Starting listening for CQL clients".
2. Create the keyspace (SimpleStrategy, RF=1) and table; start the sampler.
3. For S in {1, 8, 15 MiB}: insert 100 rows; record peak MemtableOffHeapSize, peak RSS and any error.
4. Insert one 17 MiB row; record the error and that off-heap memtable use does not change.
5. Change (b): stop the node, edit yaml, restart, repeat steps 3-4 with S = 17 and 60 MiB; record acceptance.
6. Change (c): halve `memtable_offheap_space`, restart, repeat step 3 for S = 8 MiB.
7. Stop the node (`nodetool drain`, then kill), confirm `pgrep -f CassandraDaemon` is empty, and delete the data directories.

**B3f. Predictions.**
- S <= 15 MiB: all writes succeed; no `IllegalStateException`; peak MemtableOffHeapSize hovers near, and may transiently exceed, `memtable_offheap_space` (soft cap), then falls after each flush.
- S = 17 MiB at default: rejected by `validateSize` (`MutationExceededMaxSizeException`, `oversizedMutations` +1); off-heap use unchanged. The rejection arrives before `NativeCell`, so line 100 is never reached.
- With the raised mutation size: 17 MiB and 60 MiB writes succeed; still no line-100 exception (60 MiB << 2 GiB).
- Halving `memtable_offheap_space` lowers the steady-state peak by about half, while changing nothing about per-cell acceptance.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| No line-100 exception anywhere; 17 MiB refused by mutation limit; peak off-heap tracks `memtable_offheap_space` | Claim confirmed: line 100 does not cap usage; other limits do. |
| An `IllegalStateException` with the line-100 stack frame at S <= 60 MiB | Claim refuted. |
| Peak off-heap use flat when `memtable_offheap_space` is halved | Positive control did not move; claim not confirmed (the pool may not be in use, check `memtable_allocation_type` and the log line "Memtables allocating with off-heap objects"). |
| Peak off-heap use halves with the pool knob and per-cell acceptance does not change | Confirmed: the aggregate is governed by the pool knob, the per-cell size by the mutation limit. |
| RSS grows far beyond `memtable_offheap_space` + heap | Other consumers (A4) dominate; the cap is soft and not this constant. |

**B3h. Controls.** Run with `memtable_allocation_type: heap_buffers` once: MemtableOffHeapSize must be 0 for the same workload, showing `NativeCell` is the source of the off-heap figure. Compare RSS and NMT deltas to attribute growth to the memtable rather than the chunk cache or Netty. Idle baseline for 2 minutes before writes.

**B3i. Audit amendments (2026-10-25, stage-4 step 0, before any run; B3f and B3g keep their meaning, numbers and rows are added).**
1. *Request-size limit on the wire.* With the CQL driver on protocol v4 (used here: native-v5 large requests leave unreturned direct buffers, see HANDOFF Lessons), a request over `native_transport_max_frame_size` is refused by `Envelope.java:197,484` ("Request is too big: length N exceeds maximum allowed length 16777216.") before any mutation exists. So at the defaults a 17 MiB write is refused by the frame limit, not by `validateSize`. To reach `Mutation.validateSize` (B3f's second bullet) the frame limit is raised while `max_mutation_size` stays default. B3b(b)'s `native_transport_max_frame_size: 128MiB` is kept for the raised run. `native_transport_max_message_size` defaults to `min(max_mutation_size, in-flight, per-IP in-flight)` (`DatabaseDescriptor.java:3237-3245`) and is only used by the v5 handler (`CQLMessageHandler.java:551`).
2. *In-flight limits fixed in every arm.* At `-Xmx2g` the per-IP limit defaults to heap/40 = 51 MiB (`DatabaseDescriptor.java:654-656`), below the 60 MiB write. Every arm sets `native_transport_max_request_data_in_flight: 512MiB` and `native_transport_max_request_data_in_flight_per_ip: 256MiB`.
3. *Arms.* All: one node, `memtable_allocation_type: offheap_objects` (except `hb`), `-Xmx2g -Xms2g -XX:+AlwaysPreTouch`, `memtable_heap_space: 256MiB`, table `ks.t(pk int PRIMARY KEY, v blob)`, compression off, one writer thread, protocol v4, random blobs, `MemtableOffHeap` read by a JMX sampler every 100 ms (`AllMemtablesOffHeapSize` and `MemtableOffHeapSize` of `ks.t`, `CommitLog` `OverSizedMutations` Count) and `RssAnon` of the node PID every 100 ms. **A** (defaults for mutation and frame limit; offheap 256 MiB): 100 rows each of S = 1, 8 and 15 MiB, then one 17 MiB row. **A2** (frame 64 MiB, `max_mutation_size` default): one 17 MiB row. **B** (`max_mutation_size: 64MiB`, `commitlog_segment_size: 128MiB`, frame 128 MiB, offheap 256 MiB): 5 rows of 17 MiB and 5 rows of 60 MiB. **K64, K128, K256, K512** (`memtable_offheap_space` in MiB; 512 is the default at a 2 GiB heap, `DatabaseDescriptor.java:583-584`): 100 rows of 8 MiB (800 MiB written) each. **hb**: `heap_buffers`, 100 rows of 8 MiB. A node restart between arms; the data directory is emptied between arms. The optional second node is not used.
4. *Added numeric predictions (frozen with B3f).* (a) A: 300 inserts succeed with 0 errors; `grep -c IllegalStateException system.log` is 0 and no `NativeCell.<init>` frame is logged; the 17 MiB row is refused with the "Request is too big" text, `OverSizedMutations` Count stays 0 and `AllMemtablesOffHeapSize` does not change by more than 1 MiB. (b) A2: the 17 MiB row is refused with a `MutationExceededMaxSizeException` ("oversized mutation" text in the client error or `system.log`) and `OverSizedMutations` Count is exactly 1. (c) B: all 10 inserts succeed; 0 `IllegalStateException`. (d) K arms: peak `AllMemtablesOffHeapSize` P(k) satisfies P(k) <= k + 16 MiB for every k (soft cap, one-cell slack); P(k) >= 0.30 x k for k >= 128 (the cleaner starts at 1/3 of the limit, `memtable_cleanup_threshold = 1/(1+2)`, `DatabaseDescriptor.java:753-763`); P(64) < P(128) < P(256) < P(512); P(256) / P(64) >= 2.0. (e) The `RssAnon` peak minus the pre-write baseline in K256 is at least 0.80 x P(256). (f) hb: `AllMemtablesOffHeapSize` stays 0 for the whole run, and its `RssAnon` rise is below half of K256's.
5. *Added rows for B3g.* (i) Any `IllegalStateException` with a `NativeCell` frame, or a 60 MiB / 15 MiB insert failing for a reason other than the request limits: **Refuted** (or **Not confirmed** if a non-line-100 failure). (ii) P(k) does not increase with k (violating P4 in (d)) while the K arms ran with the pool in use: the aggregate does not follow the pool knob; **Not confirmed**, and the pool-in-use evidence ("Memtables allocating with off-heap objects"-style startup line and nonzero `MemtableOffHeapSize`) is cited. (iii) P(k) > k + 16 MiB: the pool is not even a soft cap on this path; **Refuted** for the "aggregate governed by the pool" part, recorded as such. (iv) The 17 MiB refusals show a different text than predicted: record the actual text; the claim holds if the refusal is before any cell (counter unchanged). (v) Readings fitting no row: **Not confirmed**.
6. *The guard cannot be reached on the cluster tier under any allowed setting* (B2i.7): the largest cell the node can accept is below 1 GiB. The cluster tier therefore shows only that the practical range (15 to 60 MiB, and the refusals above) never reaches line 100; the guard's own behaviour at 2^31 is the unit tier's. No cluster arm above 60 MiB is run.

**B4. Risks and cleanup.** Disk: the workload writes under 5 GB of data plus a commitlog (32 MiB segments, 128 MiB in the raised run); use local disk with >= 20 GB free, never shared storage. Memory: 2 GB heap + 256 MiB off-heap + direct buffers; run on a machine with >= 6 GB free. The unit tier uses at most about 1.2 GB. Do not build in the shared tree. Cleanup: kill the node and any `jmxterm`/sampler processes, `pgrep -fl "CassandraDaemon|jmxterm|ant"` shows nothing, delete `/local/c509` data, commitlog, hints, and logs.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/db/rows/NativeCell.java
- src/java/org/apache/cassandra/utils/memory/NativeAllocator.java (grep and excerpt, lines 130-205)
- src/java/org/apache/cassandra/utils/memory/MemtableAllocator.java (excerpt)
- src/java/org/apache/cassandra/utils/memory/MemtablePool.java (excerpt)
- src/java/org/apache/cassandra/utils/memory/MemoryUtil.java (excerpt)
- src/java/org/apache/cassandra/db/memtable/AbstractAllocatorMemtable.java (lines 95-125)
- src/java/org/apache/cassandra/db/memtable/SkipListMemtable.java (excerpt)
- src/java/org/apache/cassandra/db/Mutation.java (lines 160-178)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep and excerpts)
- src/java/org/apache/cassandra/config/Config.java (grep)
- conf/cassandra.yaml (grep)

## D. Stage-4 feedback

**2026-10-25, stage-4 run 1 (both tiers), results in [`results/nativecell-int-max-size-NativeCell-size--autonomous.md`](../../stage4-runtime-verification/results/nativecell-int-max-size-NativeCell-size--autonomous.md). Verdict: Confirmed, does not cap (both tiers); outcome class true negative.**

- **Claim held.** Unit (B2g row 1 and the pool row): every cell was exactly `L + 21` off-heap bytes for L = 1 KiB to 255 MiB, no exception; the guard threw `IllegalStateException` (no message, `NativeCell.<init>` line 101, nothing charged) only at size 2^31 and accepted size 2^31-1 (a real 2 GiB cell was built, resident memory +2.0 GiB, with an 8 MiB pool it overshot the pool limit 256-fold). The pool limit, not the constant, was what made a non-blocking allocation wait (7, 15, 31 one-MiB cells admitted at 8, 16, 32 MiB). Cluster (B3g rows 1 and 4): 300 writes of 1 to 15 MiB and 10 writes of 17 and 60 MiB all succeeded with no line-100 exception; peak `AllMemtablesOffHeapSize` followed `memtable_offheap_space` (16, 40, 80, 168 MiB at 64, 128, 256, 512 MiB), about one third of the limit plus at most one cell, as the cleaner threshold predicts; `heap_buffers` gave 0.
- **Amendments made at the audit (2026-10-25, B2i and B3i), all independent of any reading.** (1) Off-by-one: the passing probe is L = `Integer.MAX_VALUE - 21`, the throwing probe `- 20`. (2) A3.5 is wrong: raising `max_mutation_size` and `max_value_size` cannot make line 100 reachable, because `commitlog_segment_size` < 2048 MiB and at least twice `max_mutation_size`, so a cell stays below 1 GiB; the guard is unreachable for any production write (dead code on the write path). (3) Under protocol v4 a 17 MiB write at defaults is refused by the frame limit (`Envelope.java:197,484`, "Request is too big"), not by `validateSize`; `validateSize` was reached with `native_transport_max_frame_size: 64MiB` ("Rejected an oversized mutation", `OverSizedMutations` +1). (4) At `-Xmx2g` the per-IP in-flight limit defaults to 51 MiB, below a 60 MiB write; the in-flight limits are set explicitly. (5) The pool default at a 2 GiB heap is 512 MiB, added as a fourth value. (6) A draft prediction that a heap array leaves `RssAnon` flat was removed before the harness existed.
- **Limits of the result.** The guard does bound one cell at 2^31-1 bytes (unit tier, exact); "does not cap" is about the resource as the experiment defines it (practical and configurable usage), which the guard cannot affect. The cluster tier cannot reach the guard under any allowed setting, so it supports only the practical range (at most 60 MiB tested). The path term (line 97) was not probed. Cluster peaks are sampled every 100 ms against a sawtooth of about 300 ms, so each is a lower bound by up to one 8 MiB cell. The `RssAnon` signal at 200 KiB x 10 is below the test JVM's noise floor (reported, not used).
- **Runbook defects:** none beyond the amendments above. Instruments: [`harness/nativecell-int-max-size-NativeCell-size--autonomous/`](../../stage4-runtime-verification/harness/nativecell-int-max-size-NativeCell-size--autonomous/).
