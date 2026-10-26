# hint buffer slab (max_mutation_size) — verification solution  <!-- file: cases/hints-HintsBuffer-put-slabCapacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/HintsBuffer.java:152` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-25 |
| Estimate | `positive`: off-heap (direct) memory held by the hint buffer pool is bounded by `MAX_HINT_BUFFERS (3) x max(2 x max_mutation_size, 32 MiB)`, which is 96 MiB by default; the entry line itself only caps one hint at half a slab. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** The check at `HintsBuffer.java:152` (`totalSize > slab.capacity() / 2`) compares against the slab size, which is not a setting of its own. It is derived from `max_mutation_size` (configuration entry) in `HintsService.java:110`: `bufferSize = Math.max(DatabaseDescriptor.getMaxMutationSize() * 2, MIN_BUFFER_SIZE)`, with `MIN_BUFFER_SIZE = 32 << 20` at `HintsService.java:79`. The number of slabs is capped by JVM property `cassandra.MAX_HINT_BUFFERS` (`CassandraRelevantProperties.java:351`, default `"3"`), read into `HintsBufferPool.MAX_ALLOCATED_BUFFERS` at `HintsBufferPool.java:41`.
- `max_mutation_size` is declared at `config/Config.java:407` (`IntKibibytesBound`, unit KiB). It is null by default. `DatabaseDescriptor.java:898-899` sets it to `commitlog_segment_size / 2`, and `conf/cassandra.yaml:660` has `commitlog_segment_size: 32MiB`, so the default is 16 MiB. `DatabaseDescriptor.java:900-901` rejects a config where the segment size is under twice `max_mutation_size`. Getter: `DatabaseDescriptor.java:2827-2829`.
- Default slab is therefore `max(2 x 16 MiB, 32 MiB) = 32 MiB`, and the per-hint cap is 16 MiB.
- Both settings are read at startup only (yaml key `max_mutation_size`, or `commitlog_segment_size`; `-Dcassandra.MAX_HINT_BUFFERS=n`), so changing them needs a restart. `IMutation.MAX_MUTATION_SIZE` is a static final (`IMutation.java:31`), so the value is frozen at class load.

**A2. What it caps.** Off-heap memory: each `HintsBuffer` slab is `ByteBuffer.allocateDirect(slabSize)` (`HintsBuffer.java:75-78`), so it counts against `-XX:MaxDirectMemorySize`. The quantity at line 152 is `hintSize + 12` against `slab.capacity()/2`. The aggregate quantity is the sum of the slab capacities the pool has created (`allocatedBuffers`, `HintsBufferPool.java:46,132`).

**A3. Mechanism.**
1. A write path runs `StorageProxy.submitHint` and the `HintRunnable`, which calls `HintsService.instance.write(hostIds, Hint.create(...))` (`StorageProxy.java:2811`). That goes to `HintsService.write` (`HintsService.java:161-170`) and then `HintsBufferPool.write` (`HintsBufferPool.java:59-66`).
2. `HintsBufferPool.write` computes `hintSize = Hint.serializer.serializedSize` (`HintsBufferPool.java:61`). That is 8 bytes of creation time, a vint of gcgs, and the mutation (`Hint.java:163-168`).
3. `HintsBuffer.allocate(hintSize)` (`HintsBuffer.java:148`) sets `totalSize = hintSize + ENTRY_OVERHEAD_SIZE` (12, `HintsBuffer.java:58`, `:150`). At `:152`, if `totalSize > capacity/2` it throws `IllegalArgumentException("Hint of ... bytes is too large")`. That hint is not stored, and the exception goes up through the `HintRunnable`.
4. Otherwise `allocateBytes` (`:183-196`) bumps the atomic `position`. If it passes capacity, it sets position to `Long.MIN_VALUE` (closed) and returns -1, so `allocate` returns null (`:171-180`).
5. On null, `HintsBufferPool.allocate` (`:68-84`) calls `switchCurrentBuffer(current)` and then `flushCallback.flush(current, this)` (`:79-80`). `switchCurrentBuffer` (`:107-128`) first polls `reserveBuffers` (`:112`). If that is empty and `allocatedBuffers >= MAX_ALLOCATED_BUFFERS`, it blocks on `reserveBuffers.take()` (`:113-118`) until a flush returns a buffer. Otherwise it creates a new slab (`:125,130-134`).
6. The flush runs asynchronously on `HintsWriteExecutor` (`HintsWriteExecutor.java:83`). `FlushBufferTask.run` (`:141-155`; recycle and offer at `:151-152`) waits for in-flight appends, writes the hints to disk, then calls `buffer.recycle()` (`HintsBuffer.java:96-100`, which reuses the same slab) and `bufferPool.offer` (`HintsBufferPool.java:86-90`). Slabs are never freed or shrunk while the service runs. `close()` frees only `currentBuffer` (`:136-139`).
- Outcomes at the limit: a single hint over half a slab is rejected (hint lost); slab full means rotate and flush; all 3 slabs in flight means the hint writer thread blocks (back-pressure, not more memory).
- Overshoot or bypass: (a) `HintsService.write` has no size gate of its own [Amended 2026-10-26, stage-4 audit, before any reading: verified: no gate in `HintsService.java:161-170` or `HintsBufferPool.java:59-66`];  The mutation size gate is `Mutation.validateSize` at `Mutation.java:169-177`, called from `CommitLog.java:304` and `MutationVerbHandler.java:54` with overhead 12. A hint adds 8 bytes plus the gcgs vint (3 bytes for the default gc_grace_seconds 864000, which lies in [16384, 2097152)) and 12 bytes of entry overhead, so a mutation of serialized size M is hinted iff `M + 23 <= slab/2` and passes the commit log iff `M + 12 <= max_mutation_size` [Amended 2026-10-26, stage-4 audit, before any reading: exact arithmetic; with the default config the window in which the commit log accepts and the hint is rejected is M from m-22 to m-12 inclusive, m = max_mutation_size in bytes]. With the default config (`max_mutation_size` = 16 MiB = half a slab), a mutation of 16 MiB minus 23 bytes up to 16 MiB minus 12 bytes passes commit-log validation but fails `:152`. This is a design-time inference; stage 4 should confirm it. (b) `HintsBufferPool` is created once with a fixed size (`HintsService.java:111`), so there is no runtime change. (c) A hint for N hosts is written once with N offsets (`HintsBuffer.java:199-206` `put`, `:225-230` `Allocation.write`, class doc `:50-53`) [Amended 2026-10-26, stage-4 audit, before any reading: cite was `:100-108`, which is `recycle()`/`free()`], so memory does not scale with replica count.

**A4. Other consumers.** Direct memory is also used by the chunk cache and buffer pool (`file_cache_size`), Netty direct buffers, the commit log segments (mmap, not direct), and compression/crypto buffers. `HintsWriteExecutor.writeBuffer` (a separate direct write buffer, `HintsWriteExecutor.java:53,60`, used at `:241`) is another small hint-path allocation. Hints on disk are bounded separately by `max_hints_size_per_host` (`Config.java:448`, 0 = disabled) and `max_hints_file_size` (`Config.java:447`); neither affects the slab. Heap holds the `ConcurrentLinkedQueue<Integer>` offsets per host (`HintsBuffer.java:63,100-108`), which are not bounded by the slab count in any obvious way but are bounded by slab capacity per queue (each hint needs at least 12 bytes).

**A5. Evidence beyond the source.** Tests `test/unit/org/apache/cassandra/hints/HintsBufferTest.java:69-70` (`testOverlyLargeAllocation`) and `HintsBufferPoolTest.java:49-55` (`testBackpressure`) exercise the oversized-hint rule and the 3-buffer back-pressure. They were located by filename and `@Test` lines only; bodies were not studied. No external links.

## B. Verification solution

**B1. Claim under test.** (1) A hint whose serialized size plus 12 exceeds half the slab is rejected with `IllegalArgumentException`, and one at or below that size is accepted, where the slab is `max(2 x max_mutation_size, 32 MiB)`. (2) The direct memory held by the hints pool never exceeds `MAX_HINT_BUFFERS x slab`, however many hints are written, so raising or lowering `max_mutation_size` or `MAX_HINT_BUFFERS` moves the ceiling proportionally. It is wrong if direct-memory growth for the pool passes `3 x slab` (plus a small tolerance), or if the threshold does not sit at `slab/2`.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`, never build in the shared tree). `cd /local/scratch/c509 && ant jar` (or `ant build-test`). [Amended 2026-10-26, stage-4 audit, before any reading: the copy is made with `copy-source.sh` into `~/s4-hb` and built with `ant build-test`.] The test file goes under `/local/scratch/c509/test/unit/org/apache/cassandra/hints/` as a new class `HintsSlabCapTest` that uses package-private `HintsBuffer` and `HintsBufferPool`. Run with `ant testsome -Dtest.name=org.apache.cassandra.hints.HintsSlabCapTest`. JVM options: `-XX:MaxDirectMemorySize=1g -Dcassandra.MAX_HINT_BUFFERS=<n>` (set via `-Dtest.jvm.args` or `<jvmarg>` in a copied build.xml target). The property must be set before `HintsBufferPool` is loaded, so use one forked JVM per value.

**B2b. Knobs.** (i) Slab size passed to `HintsBuffer.create(int)` / `new HintsBufferPool(int, cb)`: 1 MiB, 4 MiB, 32 MiB (small values keep the test fast; the check is size-independent). (ii) `cassandra.MAX_HINT_BUFFERS`: 1, 3 (default), 5. (iii) For the derivation, `max_mutation_size` = 4 MiB, 16 MiB, 24 MiB, 40 MiB (with `commitlog_segment_size` of at least twice that, e.g. 80 MiB) fed through `DatabaseDescriptor` config load, to confirm `HintsService.java:110`. [Amended 2026-10-26, stage-4 audit, before any reading: 24 MiB added (slab 48 MiB) because 4 MiB and 16 MiB both give the 32 MiB floor, so the three original values show only two distinct slabs. The derivation is read from the `bufferSize` of a real `HintsService` instance, built with `max_mutation_size` set on the raw config before construction.]

**B2c. Workload.** (1) Boundary: for slab S, create a `Hint` (or a bare size via a stub) with `hintSize = S/2 - 12` and with `S/2 - 11`; call `HintsBuffer.allocate(hintSize)`. (2) Pool: `new HintsBufferPool(S, flushCb)` where `flushCb` is a stub that, after a short delay, calls `pool.offer(buffer.recycle())`; write hints of S/4 bytes from 8 threads until 20 x S bytes have been written, so slabs rotate many times. [Amended 2026-10-26, stage-4 audit, before any reading: the stub's delay is 200 ms, so that the writers need all n slabs before the first comes back; S/4 is the mutation value size, the hint is a little larger and the slab holds 3 of them.] (3) Stall: use a `flushCb` that never returns buffers and write until the writer blocks.

**B2d. Observables and instruments.** Exceptions thrown at `allocate`; `HintsBufferPool.allocatedBuffers` (private, read by reflection) and the count of distinct slab capacities seen via the flush callback; `java.nio.Bits` reserved memory through `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` entry named `direct` (its `getMemoryUsed()`), sampled before and after, which is the operand-side proof of off-heap use. Thread state of the writer in the stall case via `Thread.getState()`. Not directly observable: the exact byte accounting of other direct users in the test JVM, so use the delta between before and after.

**B2e. Procedure.**
1. Build the copy and the test class.
2. Boundary test at each S: record accept/reject for `S/2 - 12`, `S/2 - 11`, and `S/2 + 1`.
3. Pool-rotation test at S = 4 MiB and `MAX_HINT_BUFFERS=3`: record `allocatedBuffers` and the `direct` pool delta after the full workload.
4. Repeat with `MAX_HINT_BUFFERS` of 1 and 5 (fresh JVM each). [Amended 2026-10-26, stage-4 audit, before any reading: at 1 the pool deadlocks by construction: `HintsBufferPool.allocate` calls `flushCallback.flush(current, this)` (`:79-80`) only after `switchCurrentBuffer` returns, and with `allocatedBuffers (1) >= MAX_ALLOCATED_BUFFERS (1)` and an empty reserve queue `switchCurrentBuffer` blocks in `take()` (`:113-118`) before the flush is ever requested. So the full-workload series is 2, 3, 5; n = 1 is run only as a stall observation (writer parked in `take()`, `allocatedBuffers == 1`, direct delta `S`).]
5. Stall test: confirm the writer thread is `WAITING` in `BlockingQueue.take` and the direct delta is `<= 3 x S`.
6. Derivation test: load configs with the three `max_mutation_size` values and compute `Math.max(DatabaseDescriptor.getMaxMutationSize()*2, 32<<20)`.

**B2f. Predictions.**
- Boundary: `S/2 - 12` accepted (`totalSize == S/2`); `S/2 - 11` and `S/2 + 1` rejected with the "too large" message.
- Direct delta after step 3 is `3 x 4 MiB = 12 MiB` (+/- 64 KiB), with `allocatedBuffers == 3`. For `MAX_HINT_BUFFERS=1` it is 4 MiB [Amended 2026-10-26, stage-4 audit, before any reading: reached only as a permanent stall, the workload cannot finish at n = 1; n = 2 gives 8 MiB with `allocatedBuffers == 2`]; for 5 it is 20 MiB only if the flush callback is slow enough to need 5 (otherwise fewer, never more).
- Stall: writer blocked, delta exactly `n x S`.
- Derivation: slab 32 MiB for 4 MiB and 16 MiB; 80 MiB for 40 MiB.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Threshold sits exactly at `S/2` as predicted | Line 152 works as traced |
| Accept at `S/2 - 11` or reject at `S/2 - 12` | Off-by-overhead; trace of `ENTRY_OVERHEAD_SIZE` wrong |
| Direct delta stays `<= n x S` while many times `n x S` bytes pass through | Memory is capped by the pool (claim 2 holds) |
| Direct delta over `n x S` plus tolerance, or `allocatedBuffers > n` | Claim refuted: the pool is not capped as traced |
| Writer never blocks in the stall case and keeps allocating | Back-pressure path (`:113-118`) does not work as traced |
| Slab size does not follow `max_mutation_size` | Derivation at `HintsService.java:110` wrong |

**B2h. Controls.** Run the same workload with `MAX_HINT_BUFFERS=1` versus 3 to show the delta tracks the knob (positive control for the cap). Run a baseline `direct` delta with no hint writes. Warm up and call `System.gc()` before sampling, so earlier garbage direct buffers do not distort the delta (direct buffers are freed only after GC, so also compare against the `allocateDirect` call count).

### B3. Cluster tier

**B3a. Environment and build.** One node is enough (a second node is useful for step 8). Build from the local copy (`ant jar`), JDK 11. Local-disk data, commitlog and hints directories on a volume of known size (at least 10 GiB free), e.g. `/local/scratch/node1/{data,commitlog,hints}`. JVM options: `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=1g`, and `-XX:NativeMemoryTracking=summary` for later reading. `hinted_handoff_enabled: true`, `max_hint_window: 3h`.

**B3b. Knobs.** `max_mutation_size` with `commitlog_segment_size` at twice it: (A) `max_mutation_size: 4MiB` with `commitlog_segment_size: 8MiB` -> slab 32 MiB; (B) `max_mutation_size: 40MiB` with `commitlog_segment_size: 80MiB` -> slab 80 MiB; (C) default. `-Dcassandra.MAX_HINT_BUFFERS` of 1, 3, 6. [Amended 2026-10-26, stage-4 audit, before any reading: (D) `max_mutation_size: 24MiB` with `commitlog_segment_size: 48MiB` -> slab 48 MiB, added so that the slab takes three distinct values (A and C both give 32 MiB). The series is 2, 3, 6, not 1, 3, 6: at 1 the hint path deadlocks (see B2e step 4), which would hold a Mutation-stage thread forever (`StorageProxy.java:2822-2826` runs the hint on `Stage.MUTATION`).] Each setting needs a restart. The two-node variant needs only the stopped peer.

**B3c. Workload.** Make hints pile up: two-node cluster (RF=2, `CONSISTENCY ANY`), stop node 2, then write to node 1 with `cassandra-stress` (`write n=2000000 cl=ANY -col size=FIXED(2000) -rate threads=200`, about 4 GB of hints) [Amended 2026-10-26, stage-4 audit, before any reading: the command is `-col n=FIXED(1) size=FIXED(2000)` (one column, so about 2.1 KB per row; the default is 5 columns), 500,000 rows (about 1 GB of hints, 10 x the 96 MiB ceiling at config A and 4 x the 240 MiB ceiling at config B), because the harness runs the node on a shared node with 55 GB free. A trigger is added so the pool is driven to its ceiling: the Byteman rule `hold-flush.btm` (reused from the closed MAX_HINT_BUFFERS case) delays every `FlushBufferTask.run` by 2000 ms in every arm, as the closed case did [Amended 2026-10-26, runbook defect found at cluster attempt 1 (results §3): 2000 ms is too short, the 1-process client offers about 12 MB/s so a 32 MiB slab fills every 2.7 s and the held flush returns before the next slab is needed (attempt 1, arm A3: 2 slabs, no waiting writer). The hold is 10000 ms in every arm, which is longer than the fill time of the 80 MiB slab (6.7 s) too, so every arm reaches the cap; B3f and B3g are unchanged and the cluster tier restarts from its beginning]; without it a fast disk can recycle slabs faster than the stress fills them (B3g row 4). The writer waiting at `take()` is traced by a Byteman rule (`hints-pool.btm`) and is the direct evidence that the disallow branch fired.]. Writes must exceed `3 x slab` many times over (`3 x 80 MiB = 240 MiB` for config B). Duration: until the data is written, 10 to 20 minutes. Large-hint variant: insert a blob of `max_mutation_size - 200 KiB` per row from cqlsh/driver. [Amended 2026-10-26, stage-4 audit, before any reading: the variant is a boundary test at config C on mutation sizes M (serialized size, traced at `HintsBuffer.allocate` entry: hintSize = M + 11): M = m-100 and m-23 (hinted), m-22 and m-15 and m-12 (passes the commit log, rejected at `:152`), m-11 (rejected by the commit log). The blob length is calibrated from a first trace line. Raising `native_transport_max_message_size` to 20MiB is a deviation: its default is `min(max_mutation_size, in-flight limits)` (`DatabaseDescriptor.java:3236-3244`), so a CQL request of M plus the query text exceeds it and never reaches the mutation.]

**B3d. Observables and instruments.** (1) `jcmd <pid> VM.native_memory summary` (NMT, category Internal/Other for direct buffers) and the `java.nio:type=BufferPool,name=direct` MBean (`MemoryUsed`, `Count`) read by `jmxterm` or `nodetool sjk mx`, sampled every 5 s. (2) `/proc/<pid>/status` VmRSS. (3) Heap via `nodetool info`. (4) Hints on disk via `du -sb hints/`. (5) Log lines "too large" (`grep` system.log). Not observable: per-pool attribution inside the `direct` MBean (it aggregates all direct buffers), so subtract the baseline taken at idle after startup, and cross-check with config C versus A versus B.

**B3e. Procedure.**
1. Copy source, `ant jar`, create the directories, and write cassandra.yaml with config A.
2. Start node(s), record baseline `direct` MemoryUsed and Count.
3. Stop node 2; start the stress write; sample every 5 s for the run.
4. After the run, record peak and final `direct` values, and `du` of hints.
5. Stop node 1, change to config B, repeat steps 2-4; then config C and the `MAX_HINT_BUFFERS` series (1, 3, 6) at config A. [Amended 2026-10-26, stage-4 audit, before any reading: series 2, 3, 6; config D added; one lifetime per arm, data wiped between arms.]
6. Large-hint test: with config C, send one row with a blob of 16 MiB minus 100 bytes, then one of 16 MiB minus 15 bytes; check system.log for "Hint of ... bytes is too large" and the stored count in `nodetool tablestats` / `nodetool statushandoff`. [Amended 2026-10-26, stage-4 audit, before any reading: read the Byteman trace and `TotalHints` instead (see B3f); `nodetool statushandoff` shows only whether hinted handoff is on.]
7. Stop all processes, `pgrep -f CassandraDaemon`, delete the scratch directories.

**B3f. Predictions.** Peak `direct` growth over baseline, from the hint path, is at most `n x slab`: config A with 3 buffers is about 96 MiB (32 MiB each), config B about 240 MiB (80 MiB each). `MAX_HINT_BUFFERS` of 1, 3, 6 gives about 32, 96, 192 MiB at config A (6 only if flush is slow enough to need them; never more). The curve is flat once the buffers have been allocated, while `du hints/` keeps growing to GBs. Large hints: the 16 MiB minus 100 bytes row is hinted; the 16 MiB minus 15 bytes row fails at line 152 (inferred). [Amended 2026-10-26, stage-4 audit, before any reading: read as mutation sizes M = m-100 and M = m-15, with the exact boundary m-23 / m-22 above. Config D: about 3 x 48 = 144 MiB. The series at config A: 2, 3, 6 gives about 64, 96, 192 MiB. The rejection is also read from the Byteman trace of the exception exit and the unchanged `TotalHints` counter (incremented at `HintsService.java:170`, after the write). [Corrected 2026-10-26 after cluster run 1: this amendment first said the rejection leaves no log line because `HintRunnable.run` wraps the exception (`StorageProxy.java:2718-2723`) and the `Stage.MUTATION.submit` future is unread; that was wrong, the node logs `ERROR ... RuntimeException: IllegalArgumentException: Hint of N bytes is too large` once per rejected hint, so the original grep of system.log works. No prediction or table was affected.]]

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Direct memory plateaus at about `n x slab` above baseline while hints on disk grow | Pool is capped as traced |
| Plateau moves proportionally with `max_mutation_size` and `MAX_HINT_BUFFERS` | Slab size and buffer count are the real knobs |
| Direct memory keeps growing past `n x slab` with the stress still running | Claim refuted (check other consumers first, see controls) |
| Peak lower than `n x slab` | Not enough hint pressure, flush kept up; not confirmed, raise load |
| Large-hint rows near the limit both stored | Overhead inference in A3 wrong |

**B3h. Controls.** Baseline run with the peer up (no hints): direct memory should stay at baseline. Positive control: the `MAX_HINT_BUFFERS` series, where the cap known to bind is the buffer count. Hold chunk cache (`file_cache_size`) and Netty settings fixed across runs. Compare by the difference from the no-hints run, not absolute values.

**B4. Risks and cleanup.** Disk: about 4 GB of hints per run on local disk of known size; `max_hints_size_per_host` can be set to bound it (e.g. 2GiB). Do not use shared storage, and never build in the shared tree. Memory: `MaxDirectMemorySize` set so a runaway cannot take the host. Cleanup: stop all Cassandra and stress processes, check with `pgrep -fl 'CassandraDaemon|cassandra-stress'`, then remove the scratch trees. Unit tier: forked JVMs end with the test.

## C. Sources read

- `~/writeup-A/playbook-autonomous.md`, `~/writeup-A/_TEMPLATE-autonomous.md`
- `src/java/org/apache/cassandra/hints/HintsBuffer.java`
- `src/java/org/apache/cassandra/hints/HintsBufferPool.java`
- `src/java/org/apache/cassandra/hints/HintsService.java`
- `src/java/org/apache/cassandra/hints/HintsWriteExecutor.java`
- `src/java/org/apache/cassandra/hints/Hint.java`
- `src/java/org/apache/cassandra/service/StorageProxy.java`
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java`, `Config.java`, `CassandraRelevantProperties.java`
- `src/java/org/apache/cassandra/db/Mutation.java`, `IMutation.java`
- `conf/cassandra.yaml`, `conf/cassandra-env.sh` (grep)
- `test/unit/org/apache/cassandra/hints/HintsBufferTest.java`, `HintsBufferPoolTest.java` (grep of test names only)

## D. Stage-4 feedback

Stage-4 run 1, 2026-10-26, results `stage4-runtime-verification/results/hints-HintsBuffer-put-slabCapacity--autonomous.md`. **Confirmed, caps (true positive), both tiers.**
- Unit: the threshold sits exactly at S/2 (S/2-12 accepted, S/2-11 and S/2+1 rejected) at S = 1, 4, 32 MiB; a pool of 4 MiB slabs fed 20.17 x S bytes holds exactly n slabs for n = 2, 3, 5 (direct delta 8, 12, 20 MiB exactly); a stalled writer parks in `take()` with the delta exactly n x S; a real `HintsService` derives `max(2m, 32 MiB)` for m = 4, 16, 24, 40 MiB and its pool takes the S/2-12 hint and rejects one byte more.
- Cluster: 1 GB of hints, pool bytes at the peak = n x slab within 2 MiB for n = 2, 3, 6 (32 MiB slabs) and for slabs 32, 32, 48, 80 MiB at n = 3; writers waited at `take()` in every hint arm; the peer-up control stayed at one slab. Large-hint boundary: M = m-23 hinted, M = m-22, m-15, m-12 rejected at `:152`.
- Amendments of the audit (all before any reading of the tier they touch): n = 1 replaced by 2 (n = 1 deadlocks, shown as a stall in the unit tier), config D (24 MiB) added, stress replaced by a one-column 500,000-row client workload, the exact hinted-versus-commit-log window, citations (`HintsBuffer.java:100-108` -> `:199-206`; `FlushBufferTask.run` `:141-155`). A runbook defect: the first cluster attempt held each flush 2 s, too short for the offered load (2 slabs, no waiting writer); it was changed to 10 s and the tier rerun. One audit statement was wrong (the rejection does log an ERROR line) and is corrected in place.
- Not in the filed design: the idle node already holds one slab (created by the periodic flush), so growth over the baseline is (n-1) x slab; B3f's "at most n x slab above baseline" holds, and the exact relation is on pool bytes.
- Surprises: `MAX_HINT_BUFFERS=1` deadlocks by construction (`HintsBufferPool.java:79-80, 113-118`); a mutation of m-11 bytes is refused at the CQL layer ("Request is too big") before the commit log.
