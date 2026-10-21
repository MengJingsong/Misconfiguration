# WRITE_BUFFER_SIZE (hints write aggregation buffer) — verification solution  <!-- file: cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/HintsWriter.java:237` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-19 |
| Estimate | `negative`. The operand `buffer.remaining()` is bounded by a fixed 256 KiB constant (`WRITE_BUFFER_SIZE`) that is a flush-batching size, not a limit on memory or disk: a hint larger than the buffer is still written (via a temporary heap buffer in this test-only overload, or directly from the hint buffer in the production overload), and the real hint memory/disk bounds are elsewhere (`HintsBuffer` slab, `max_hints_size_per_host`). The line itself is in `append(Hint)`, which only tests call. |

## A. Constraint trace

**A1. The constraint.** `HintsWriteExecutor.WRITE_BUFFER_SIZE`, a `static final int` constant, `256 << 10` = 262144 bytes (`hints/HintsWriteExecutor.java:50`). It is allocated once per `HintsWriteExecutor` as a direct buffer (`HintsWriteExecutor.java:60`, `ByteBuffer.allocateDirect(WRITE_BUFFER_SIZE)`), and handed to every `HintsWriter.Session` as the aggregation `buffer` (`HintsWriteExecutor.java:241` -> `HintsWriter.newSession` `HintsWriter.java:136` -> `Session` ctor `:174`). Kind: constant. Unit: bytes. Default = the literal; not derived. Not settable by yaml, `-D`, or JMX; changing it needs a source edit and rebuild. The line-237 comparison operand is `buffer.remaining()`, which starts at 262144 (`buffer.clear()` in ctor `:176`) and shrinks as bytes are put.

**A2. What it caps.** Nominally: off-heap (direct) memory of the single shared write buffer (a fixed 256 KiB, one per node) and the batch size of each `channel.write`. The quantity compared at `:237` is `totalSize = serializedSize + 12` (`HintsBuffer.ENTRY_OVERHEAD_SIZE`, `HintsBuffer.java:58`) against `buffer.remaining()`. It does not bound disk (file size is bounded by `max_hints_file_size`, `HintsWriteExecutor.java:239,247`; per-host disk by `max_hints_size_per_host`, `StorageProxy.java:2488-2497`) and does not bound the size of an individual hint.

**A3. Mechanism.**
1. `append(Hint)` (`HintsWriter.java:232`) computes `hintSize` and `totalSize` (`:234-235`).
2. `:237-238`: if `totalSize > buffer.remaining()`, `flushBuffer()` (`:277`) writes the buffered bytes to the channel and clears the buffer.
3. `:240-242`: if it now fits, serialize into `buffer`; otherwise `ByteBuffer.allocate(totalSize)` is a fresh heap buffer of the full hint size. So a hint with `totalSize > 262144` overshoots the 256 KiB figure and costs heap equal to `totalSize`.
4. `:259-262`: if it went into `buffer`, count bytes; else `append(hintBuffer.flip())`, i.e. the `ByteBuffer` overload (`:200-222`), which at `:205-209` flushes, then at `:219-220` `writeBuffer(hint)` straight to the channel.
Production path: `HintsWriteExecutor.flushInternal` calls only the `append(ByteBuffer)` overload (`HintsWriteExecutor.java:245`) with slices of the `HintsBuffer` slab; no allocation occurs there, and an oversize hint is written directly. The `append(Hint)` overload (doc: "Used mainly by tests", `:228`) is called only from tests (e.g. `test/unit/.../hints/HintsStoreTest.java:173`, `HintWriteTTLTest.java:105`, `HintsMaker.java:193`).
Outcomes at limit: flush (no failure, no drop, no error). Bypass/overshoot: any hint > 256 KiB bypasses the buffer. The maximum hint size is `slab.capacity()/2` (`HintsBuffer.java:150-158`), where slab = `max(max_mutation_size*2, 32 MiB)` (`HintsService.java:79,110`); `max_mutation_size` defaults to `commitlog_segment_size/2` = 16 MiB (`DatabaseDescriptor.java:898-899`), so hints up to 16 MiB are legal, 64x the buffer.

**A4. Other consumers.** The actual hint-memory consumers: the `HintsBuffer` slabs, direct, 32 MiB each (default), up to `MAX_HINT_BUFFERS` (default 3, `CassandraRelevantProperties.java:351`, `HintsBufferPool.java:41,113`) = 96 MiB total, and bigger if `max_mutation_size` > 16 MiB; the Netty/direct pool, chunk cache, memtables, etc. share `MaxDirectMemorySize`. Compressed/encrypted writers add their own buffers (`CompressedHintsWriter`, `EncryptedHintsWriter`). Disk: hints files share the hints directory with other data; bounded only by `max_hints_file_size` (per file) and `max_hints_size_per_host`.

**A5. Evidence beyond the source.** none (class comment at `HintsWriteExecutor.java:40-46` and `HintsWriter.java:163-166` read as context only).

## B. Verification solution

**B1. Claim under test.** `WRITE_BUFFER_SIZE` does not cap hint memory or disk: (a) a hint larger than 256 KiB is written in full and costs extra heap equal to its size in the `append(Hint)` overload (none extra in the production overload), and (b) node-level direct/heap memory attributable to hint writing does not stay within 256 KiB plus a constant and is governed instead by the `HintsBuffer` slabs and hint size, while disk growth is stopped only by `max_hints_size_per_host`.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. `git clone /proj/misconfiguration-PG0/git-repos/cassandra-src $HOME/work/c509 && cd $HOME/work/c509 && git checkout cassandra-5.0.9` (local disk; never build in the shared clone). `ant jar` (or `ant build-test`). Add one test class `test/unit/org/apache/cassandra/hints/WriteBufferProbeTest.java` in the local clone only (package `org.apache.cassandra.hints`, needed because `HintsWriter`, `Session`, `HintsWriteExecutor.WRITE_BUFFER_SIZE` are package-private). Run: `ant testsome -Dtest.name=WriteBufferProbeTest -Dtest.methods=...`. JVM options: defaults of build.xml plus `-Xmx1g -Xlog:gc*:file=$WORK/gc.log`.

**B2b. Knobs.** The constant is not settable, so the varied quantity is the hint size relative to it. Sizes (serialized hint payload, one cell value): 1 KiB, 100 KiB, 255 KiB, 257 KiB, 1 MiB, 4 MiB, 15 MiB. They straddle 262144-12 and go up to the 16 MiB legal maximum. A second variant uses a copy of the test with `buffer = ByteBuffer.allocateDirect(64 << 10)` passed to `newSession` (the session accepts any buffer) to show the threshold follows the buffer capacity, not a cap.

**B2c. Workload.** Per size S: create a keyspace-less `Mutation` as in `HintsStoreTest.createHint`/`HintsMaker` with one blob cell of S bytes (value limited by the legal maximum 16 MiB, so need `max_mutation_size` default; for 15 MiB the test calls `DatabaseDescriptor.daemonInitialization()` with defaults), wrap with `Hint.create(m, now)`. Make a `HintsDescriptor` (`new HintsDescriptor(UUID, now)`), `HintsWriter.create(tmpDir, descriptor)`, `try (Session s = w.newSession(ByteBuffer.allocateDirect(HintsWriteExecutor.WRITE_BUFFER_SIZE)))`. Call `s.append(hint)` N times so total bytes >> 256 KiB: for S <= 255 KiB use N = 64 (e.g. 100 KiB x 64 = 6.25 MiB = 25 buffers); for larger S use N = 8. Arithmetic: `totalSize > 262144 - position` triggers the line-237 flush; with S = 100 KiB two hints (204800 + 24) fit, the third triggers it.

**B2d. Observables and instruments.** (1) `buffer.capacity()` and `buffer.remaining()` after each append (direct read). (2) `session.getBytesWritten()` (`HintsWriter.java:184`) and the file length on disk after close, expected to equal sum of totalSize + descriptor header. (3) Heap bytes allocated by the calling thread around each `append`: `((com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean()).getThreadAllocatedBytes(Thread.currentThread().getId())` before/after, with a warmup of 20 appends discarded. (4) Count of channel writes: wrap not required; infer from `-Xlog` absent; instead use `strace -c -e trace=write -f` optional, or compute `flushBuffer` calls as (position jumps of file length via `channel.size()` sampled after each append). Not directly observable: the JIT's escape analysis may remove tiny allocations; hence the threshold test uses differences of at least S bytes.

**B2e. Procedure.**
1. Clone, checkout, `ant jar`, add the test file.
2. For each S in B2b: run the loop of B2c with the 256 KiB buffer, record per append: heap-alloc delta, `buffer.remaining()` after, `channel.size()`.
3. Repeat with the 64 KiB buffer variant for S = 100 KiB.
4. Also call the production overload: for the same S, build the serialized entry once into a heap ByteBuffer (as `HintsBuffer.Allocation.write` would) and call `session.append(ByteBuffer)`, recording the same heap-alloc delta.
5. Close the session; verify file size and that `Hint` can be read back with `HintsReader` (confirms the data was fully written).
6. Delete the temp dir.

**B2f. Predictions (before any run).**
- S <= 255 KiB: per-append heap delta is small and independent of S (< 8 KiB, CRC32 object and wrapper only); buffer capacity stays 262144; remaining drops by ~S+12 each append and resets after a flush.
- S >= 257 KiB: the heap delta per append is >= S+12 (a fresh `ByteBuffer.allocate(totalSize)`); buffer capacity still 262144; file grows by the full S+12 per hint (nothing refused or truncated). So the "cap" is exceeded by up to 64x (S = 15 MiB).
- `append(ByteBuffer)` overload: heap delta approximately zero for every S, including > 256 KiB; the hint is written straight to the channel.
- 64 KiB variant: the allocation threshold moves to ~64 KiB, showing it is a batching size.
- Claim is wrong if: any S larger than the buffer is rejected, truncated, or throws; or the heap delta for S >= 257 KiB is small (no temporary buffer); or file bytes are less than the sum of entries.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| S >= 257 KiB written in full, heap delta >= S in `append(Hint)`, ~0 in `append(ByteBuffer)` | Claim confirmed: the 256 KiB constant does not bound memory/size; overshoot is the hint size |
| Same plus threshold moves with the 64 KiB variant | The number is only a flush threshold |
| Usage (heap delta or file bytes) stays at <= 262144 for all S | Claim refuted: the constant caps usage |
| S >= 257 KiB throws or truncates | Claim refuted; the line enforces a size limit |
| Heap delta not measurable (all ~0, JIT) even for 15 MiB | Not confirmed; repeat with `-XX:-DoEscapeAnalysis` and larger N |
| Positive control (see B2h) does not stop at its limit | Not confirmed; the harness cannot show a binding cap |

**B2h. Controls.** Positive control where a cap is known to bind: `HintsBuffer.allocate` rejects a hint over `slab.capacity()/2` (`HintsBuffer.java:150-158`). In the same test class create `HintsBuffer.create(1 << 20)` and call `allocate(S)` for S = 400 KiB (`IllegalArgumentException`, "too large - the maximum size is 524288") versus S = 100 KiB (ok); the same sizes pass through the 256 KiB write buffer without error. This shows the harness distinguishes a binding limit from the flush size. Also run S = 1 KiB as a no-overshoot baseline and run each case twice to check variance; the JIT warmup is discarded.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on one Linux host (or two hosts), built from the local clone (`ant jar`; run from `bin/cassandra -f` in the build tree copy), each with local data dirs on local disk of known size (>= 20 GiB free; check with `df`). Node A (coordinator, the node whose hints are measured) and node B (to be stopped). Settings in `conf/cassandra.yaml` for both: `num_tokens: 1`, `hinted_handoff_enabled: true`, `max_hint_window: 3h`, `hints_directory: $RUN/A/hints`, `max_hints_file_size: 128MiB`, `hints_flush_period: 1000ms` (so flushes happen during the run; default is 10000ms), `max_hints_size_per_host: 0MiB` for the baseline. JVM (`conf/jvm11-server.options` copy, `-Xms2g -Xmx2g -XX:MaxDirectMemorySize=1g -XX:NativeMemoryTracking=summary`, `-Xlog:gc*:file=$RUN/A/gc.log`). Replication: keyspace `k` with RF=2 `SimpleStrategy`, CL=ONE.

**B3b. Knobs.** (1) Value size per write: 100 KiB, 1 MiB, 8 MiB (all below the default `max_mutation_size` of 16 MiB), to span below and above 256 KiB. (2) `max_hints_size_per_host`: 0 (disabled) and 64MiB, as a positive control for a cap that binds (settable in yaml or via `nodetool` / `StorageProxyMBean` `setMaxHintsSizePerHostInMiB`, `StorageProxy.java:2413`). (3) `-Dcassandra.MAX_HINT_BUFFERS` 3 (default) versus 1 to show that hint memory follows the slab count and not the 256 KiB constant. `WRITE_BUFFER_SIZE` itself has no knob.

**B3c. Workload.** Stop node B (`nodetool drain; kill`) after the cluster is up. On A, write rows with a blob column through `cassandra-stress` user profile or `cqlsh` / driver script, CL=ONE, RF=2, so each write creates a hint for B. Volume per run: 2 GiB of values (e.g. 20480 x 100 KiB; 2048 x 1 MiB; 256 x 8 MiB), single thread then 8 threads. Arithmetic: 2 GiB of hints exceed the 32 MiB slab ~64 times and exceed 128 MiB hints file size ~16 times; with `max_hints_size_per_host=64MiB` the cap should engage after ~64 MiB. Duration is bounded by write speed, typically a few minutes per run; keep node B down for the entire run (well inside the 3 h window).

**B3d. Observables and instruments.** (1) Direct memory: JMX MBean `java.nio:type=BufferPool,name=direct` (Count, MemoryUsed, TotalCapacity) sampled each second (`jmxterm` or `jcmd <pid> VM.native_memory summary` diff against a baseline). Expected hint contributions: 1 x 256 KiB write buffer + 1..3 x 32 MiB slabs. (2) Heap: `jcmd <pid> GC.class_histogram` and the GC log for allocation rate (`-Xlog:gc*`), plus `jstat -gcutil <pid> 1000`. (3) Disk: `du -sb $RUN/A/hints` every second and `nodetool` hints metrics `org.apache.cassandra.metrics:type=Storage,name=TotalHints`/`TotalHintsInProgress`. (4) Per-host hint size: log trace line "reached to the max hints size" (`StorageProxy.java:2495`). Not directly observable: the attribution of the 256 KiB write buffer inside the direct-pool total (it is one of several buffers); we infer it from the differences between runs.

**B3e. Procedure.**
1. Clone and build locally; create `$RUN` on local disk; configure A and B; start both; create keyspace/table; sanity write.
2. Stop B. Record baselines of direct pool, `du`, heap.
3. Run workload for value size 100 KiB, then 1 MiB, then 8 MiB, each with `max_hints_size_per_host=0`; sample instruments once a second; after each, record peak direct-pool `MemoryUsed`, peak heap-used, final `du` of the hints dir. Between runs, restart B? No: keep it down; instead `nodetool truncatehints` on A and wait for `du` to return to baseline.
4. Repeat 1 MiB with `-Dcassandra.MAX_HINT_BUFFERS=1`.
5. Set `max_hints_size_per_host=64MiB` (live via JMX), repeat the 1 MiB run; record where `du` stops growing and the trace/log message.
6. Stop all nodes; check `pgrep -f CassandraDaemon` is empty; remove `$RUN`.

**B3f. Predictions (before any run).**
- With the default `MAX_HINT_BUFFERS=3`, peak direct memory attributable to hints is ~32-96 MiB (slabs) plus 256 KiB, independent of value size once the slab count saturates; peak does not track 256 KiB, i.e. it exceeds 256 KiB by >= 100x. With `MAX_HINT_BUFFERS=1`: <= ~32 MiB + 256 KiB (about one third lower), showing the slab, not the write buffer, governs.
- Hints disk grows to ~2 GiB (+ per-file overhead) for every value size when the per-host limit is 0, in files of ~128 MiB each; value size does not change the total; 100 KiB, 1 MiB, 8 MiB hints are all stored in full though the last two exceed 256 KiB.
- With `max_hints_size_per_host=64MiB`, disk growth stops near 64 MiB (plus at most one in-flight file/buffer overshoot, up to ~128 MiB file + 1 slab, because the check is on writes and the limit is checked before buffering, `StorageProxy.java:2488-2497`); writes still succeed at CL=ONE.
- Claim is wrong if direct memory attributable to hints is bounded by 256 KiB-scale values (peaks within ~1 MiB of baseline), or if hints larger than 256 KiB are dropped or refused, or if disk growth stops near 256 KiB multiples.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Hint dir grows to ~2 GiB in all three sizes; direct pool peak is tens of MiB, tied to `MAX_HINT_BUFFERS` | Claim confirmed: usage does not follow `WRITE_BUFFER_SIZE` |
| Disk stops at ~64 MiB with the per-host limit on while the same workload with limit 0 continues | Positive control: a binding cap moves usage (confirms the harness can see a cap) |
| Direct pool peak lies within ~1 MiB of baseline and does not change with `MAX_HINT_BUFFERS` | Claim refuted (hint memory is bounded near the write buffer) |
| 1 MiB and 8 MiB hints missing/dropped while 100 KiB hints are stored | Claim refuted: the buffer size limits hint size |
| Neither disk growth nor direct-pool change between runs, or the per-host limit does not bind | Not confirmed; hints were not generated (check B is down, hint window, `nodetool statushandoff`) |

**B3h. Controls.** Baseline run with B up (no hints are produced; `du` hints stays ~0). Per-host limit as positive control (above). Repeat each size twice. Check `nodetool statushandoff` reports running and that `TotalHints` increases, so that the growth really is hints. Keep other memory users constant: no reads, same table, `-Xmx` fixed, record direct pool before the workload to subtract Netty/chunk-cache baseline.

**B4. Risks and cleanup.** Disk: up to ~2 GiB of hints per run on local disk; use `nodetool truncatehints` or `rm -rf $RUN` after; never place `$RUN` on shared storage, and keep `df` free space >= 10 GiB. Memory: JVM limited by `-Xmx2g` and `MaxDirectMemorySize=1g`; 8 MiB hints with 8 threads use at most 3 slabs. Processes: stop both Cassandra JVMs, any `jmxterm`/`jstat`/stress client, and confirm with `pgrep -f 'CassandraDaemon|jstat|jmxterm'` empty. Unit tier writes only to a tmp dir deleted at the end. The probe test exists only in the local clone; the shared source tree is untouched.

**Audit amendments (stage 4 step 0, 2026-10-20).** Made before any run or reading; each leaves B1, the predictions and the readings tables as filed, except where it says it adds a row or corrects a number (results file §1.1 gives the reason for each). Where an amendment corrects text above, the amendment governs.

- **R1 (B3g: added row).** The memory-side positive control (B3b item 3, `MAX_HINT_BUFFERS=1`) has no row for a control that does not move. Add: | `MAX_HINT_BUFFERS=1` peak direct-pool delta is not lower than the default run's | The memory-side control did not move; the instrument or the workload cannot show a cap on memory: Not confirmed |
- **R2 (B3e step 3: reset).** Between value-size runs also truncate the table (`TRUNCATE ks.t`) or recreate the keyspace: `nodetool truncatehints` clears only the hints, and each run leaves about 2 GiB of table data and commit log on node A.
- **R3 (B3b item 2: live setter).** `setMaxHintsSizePerHostInMiB` is at `StorageProxy.java:2418` (cited as 2413).

## C. Sources read

- `src/java/org/apache/cassandra/hints/HintsWriter.java`
- `src/java/org/apache/cassandra/hints/HintsWriteExecutor.java`
- `src/java/org/apache/cassandra/hints/HintsBuffer.java`
- `src/java/org/apache/cassandra/hints/HintsBufferPool.java`
- `src/java/org/apache/cassandra/hints/HintsService.java`
- `src/java/org/apache/cassandra/config/Config.java` (hints entries, lines 444-448)
- `src/java/org/apache/cassandra/config/DatabaseDescriptor.java` (lines 898-901, 2827, 3592-3603, 3715-3720)
- `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java` (MAX_HINT_BUFFERS)
- `src/java/org/apache/cassandra/service/StorageProxy.java` (2480-2500)
- `conf/cassandra.yaml` (hints section), `conf/jvm-server.options`
- `test/unit/org/apache/cassandra/hints/` (callers of `session.append`: grep only)

## D. Stage-4 feedback

**2026-10-21 — run 1 closed: unit Confirmed, cluster Confirmed — does not cap** (the negative estimate held; no run 2). Results: [`results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md`](../../stage4-runtime-verification/results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md); harness `stage4-runtime-verification/harness/WRITE_BUFFER_SIZE-append-remaining--autonomous/`. Run on `pc07`, both nodes on loopback (environment deviation; the design is unchanged).

- **Unit (B2g rows 1–2):** hints of 257 KiB–15 MiB written in full and read back. `append(Hint)` allocates `totalSize` + ≤ 638 B per append above the buffer and 56 B below it; `append(ByteBuffer)` allocates 0 B. With a 64 KiB buffer, 100 KiB moves from 56 B to 102,592 B.
- **Cluster (B3g rows 1–2):** 2 GiB of hints reach disk at 100 KiB, 1 MiB and 8 MiB alike (1.0000–1.0007 × the values, 16–17 files of 128 MiB). Every entry above 256 KiB is written to the channel directly. Hint memory is 3 slabs (96.25 MiB) by default and 1 slab (32.25 MiB) with `MAX_HINT_BUFFERS=1`. Disk stops at 72/78 MiB only under `max_hints_size_per_host` 64 MiB, with every refusal's operand above it.
- **Missed sub-prediction:** B3f's "writes still succeed at CL=ONE" in the limit arms held for 2,040 of 2,048 writes. The 8 timeouts per arm came during back-to-back memtable flushes (inferred), not from the limit.
- **Defects in this file found by stage 4 (no B2f–B3g change):**
  - B2h's positive-control size: 400 KiB + 12 B is below `capacity/2` = 512 KiB, so it cannot refuse. The harness added 600 KiB and the `capacity/2` boundary pair.
  - B3e step 3 (and R2): `nodetool truncatehints` never deletes the file the writer has open (`HintsStore.java:167-181`). Each arm needs a restart of A before truncation; the cluster tier was rerun so.
  - B3b item 3: `MAX_HINT_BUFFERS=1` can never recycle a buffer (`HintsBufferPool.java:79-80`, `:112-118`). After one slab (31 × 1 MiB hints) the hint writer waits forever, all 32 `MutationStage` threads stall, client writes time out and `stopdaemon` does not return. Its memory reading is still valid, but the arm is a stall, not a load at a lower cap.
