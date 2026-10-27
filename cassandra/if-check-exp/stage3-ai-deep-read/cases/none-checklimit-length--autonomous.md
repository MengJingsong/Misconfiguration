# none — verification solution  <!-- file: cases/none-checklimit-length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ChecksummedDataInput.java:161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/ChecksummedDataInput.java#L161) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code CLI (Agent-tool subagent), 2026-10-27 |
| Estimate | `negative`: the check compares a read position with a per-hint bound taken from the hint file itself; it is not a configured cap on memory or disk. |
| Ground | `limit` is never read from configuration. It is `Long.MAX_VALUE` after `resetLimit()` and otherwise `position-at-record-start + size`, where `size` is the 4-byte length field of the record being read (validated only by a CRC, not by any limit). The check is a framing guard. The nearest real disk cap, `max_hints_file_size`, is enforced on the write side in a different class. |

> **Link rule.** Declaration and if statement are linked below.

## A. Constraint trace

**A1. The constraint.** There is no configured memory or disk constraint on this line. The relevant "limit" is the instance field `limit` of `ChecksummedDataInput`, declared at [`ChecksummedDataInput.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/ChecksummedDataInput.java#L48) (`private long limit;`, with `limitMark` at line 49). Kind: runtime-computed object field (not a yaml entry, not a `-D` property, not a constant). Unit: bytes, as an absolute position in the (uncompressed) view of the file. Default: `Long.MAX_VALUE`, set in `resetLimit()` (ChecksummedDataInput.java:153-157); `limitMark` is -1 there. Set by `limit(long newLimit)` (ChecksummedDataInput.java:130-134): `limitMark = getPosition(); limit = limitMark + newLimit`. Not settable by the operator; no restart question applies.

The earlier trace is confirmed in substance. Corrections: the CRC validation of `size` is at HintsReader.java:224 (hint iterator) and HintsReader.java:330 (buffer iterator), not 218-219; the callers that set the limit are HintsReader.java:234 (`readHint`) and HintsReader.java:340 (`readBuffer`), as claimed; `checkLimit(0)` after deserialization is at HintsReader.java:240, as claimed. The `max_hints_file_size` details are also right: declared at Config.java:447 (`128MiB`, `@Replaces` the old `_in_mb` name at Config.java:446), listed in conf/cassandra.yaml:106, read via DatabaseDescriptor.java:3720. I did not check how a yaml entry is reloaded; it is read as a yaml entry at startup and I did not find a setter for it (not verified).

**A2. What it caps.** Nothing in memory or disk terms. The quantity compared is `getPosition() + length` (ChecksummedDataInput.java:161), the stream position after the pending read, against `limit`, the end of the current record. It bounds how far one hint's deserialization may read, so a hint whose contents run past its declared `size` fails instead of consuming the next record. It does not bound how large `size` is.

**A3. Mechanism.**
1. Per record, `computeNextInternal` calls `input.resetCrc()` and `input.resetLimit()` (HintsReader.java:210-211 for hints; 316-317 for raw buffers), so `limit = Long.MAX_VALUE`.
2. It reads `size` with `readInt()` (HintsReader.java:213 / 319), handles `size == 0` (214-221 / 320-327), and requires `checkCrc()` over the length field (HintsReader.java:224 / 330).
3. `readHint(size)` / `readBuffer(size)` acquire `size` permits from the optional rate limiter (HintsReader.java:232-233 / 338-339) and call `input.limit(size)` (HintsReader.java:234 / 340).
4. Deserialization reads via `readFully(byte[])` (ChecksummedDataInput.java:189-194) and `read(byte[],int,int)` (196-201); both call `checkLimit(n)` first.
5. The check: [`ChecksummedDataInput.java:161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/hints/ChecksummedDataInput.java#L161) `if (getPosition() + length > limit)`. True: `IOException("Digest mismatch exception")` (line 162). False: the read proceeds. Primitive reads such as `readInt`/`readLong` go through the `RebufferingInputStream` buffer rather than these two overrides; I did not verify whether they reach `checkLimit` (not verified), so the guard may not cover every read.
6. After deserializing a hint, HintsReader.java:240 calls `checkLimit(0)`, which fails if the position is already beyond the record end. In the hint iterator the IOException is caught as `IOException` and rethrown as `FSReadError` (HintsReader.java:198-201); `readBuffer` path at 304-307 likewise.

Outcome when reached: the read aborts with an exception and replay of that file fails. Overshoot/bypass: with `limit == Long.MAX_VALUE` (before step 3, and for any read outside `readHint`/`readBuffer`) the check never fires. The check does not stop a large allocation: `Hint.serializer.readBufferIfLive` allocates `new byte[size]` (Hint.java:239) with `size` taken from the file, after only the 4-byte CRC check. Therefore the heap used while reading one raw hint is about `size` bytes, bounded by what the file says, not by a configured cap (the bound on what the writer can have written is the mutation-size limit, Config.java:406-407, DatabaseDescriptor.java:898-899; I did not trace that the hint writer enforces it, not verified).

**A4. Other consumers.** The input's own off-heap buffer of `RandomAccessReader.DEFAULT_BUFFER_SIZE` (4096, RandomAccessReader.java:34), allocated at ChecksummedDataInput.java:56 with `BufferType.OFF_HEAP` (line 70 delegation). Heap used by deserialized `Mutation` objects (Hint.java:206) and the `byte[size]` copy (Hint.java:239). The hint write path uses its own buffers (HintsBuffer.java:77 `allocateDirect(slabSize)`; HintsWriter.java:242). Disk: hint files are capped separately by `max_hints_file_size` (HintsWriteExecutor.java:239, 247: after an append, `session.position() >= maxHintsFileSize` makes `flushInternal` return false; the cap is checked after the append, so a file can exceed it by up to one write) and `max_hints_size_per_host` (Config.java:448, default `0B` = disabled; used at StorageProxy.java:2488, enforcement semantics not traced, not verified).

**A5. Evidence beyond the source.** none. (The cassandra.yaml comments for `max_hints_file_size` at conf/cassandra.yaml:106 were the only documentation read.)

## B. Verification solution

**B1. Claim under test.** The `limit` checked at ChecksummedDataInput.java:161 is not a configured memory or disk cap: it equals the record's own declared `size`, so memory used while reading a hint tracks the file's `size` field and is not changed by any configuration knob, while an actual cap (`max_hints_file_size`) does move on-disk hint file size. Falsified if some configuration knob changes the value of `limit` or the heap used while reading a hint of fixed size.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`cp -r /users/jason92/cassandra-5.0.9 $WORK/src`), `ant jar` there (or `ant build-test` for JUnit). Test class placed under `$WORK/src/test/unit/org/apache/cassandra/hints/` in package `org.apache.cassandra.hints` (needed, since `limit`/`bufferOffset` are private/protected and the constructor is package-private, ChecksummedDataInput.java:52). Run with `ant testsome -Dtest.name=ChecksumLimitProbeTest`, JVM `-Xmx512m`. Never build in the shared tree.

**B2b. Knobs.** (i) `size` field in a handcrafted hint file record: 1 KiB, 1 MiB, 8 MiB, 16 MiB (the last near the default `max_mutation_size`, default derived at DatabaseDescriptor.java:899 from `commitlog_segment_size`, assumed 32 MiB giving 16 MiB; not verified). (ii) Actual content length vs declared `size`: equal, 1 byte more, 1 byte less. (iii) Configuration knobs `max_hints_file_size` (0 MiB-ish small value 1MiB vs 128MiB via `DatabaseDescriptor` test setup) and `max_mutation_size`, to show they do not alter the check. Set via the test's `DatabaseDescriptor.daemonInitialization()` with a modified `Config`.

**B2c. Workload.** Write a file with `HintsWriter` (or hand-write: CRC-protected int `size`, then `size` bytes) containing one record per case. Read it through `HintsReader` iterators and directly via `ChecksummedDataInput.open(file)`, calling `limit(size)` then `readFully(new byte[n])` for n = size-1, size, size+1. The limit is reached exactly when position+n > start+size, i.e. n > size, so the n = size+1 case must throw.

**B2d. Observables and instruments.** (1) Whether `checkLimit` throws `IOException("Digest mismatch exception")` per case. (2) The reflected value of `limit` and `limitMark` (via `java.lang.reflect.Field.setAccessible`) after `limit(size)`: expected `limitMark + size`. (3) Heap allocated while `readBufferIfLive` runs: `ThreadMXBean` (`com.sun.management.ThreadMXBean.getThreadAllocatedBytes`) delta around the call, plus `-Xlog:gc` or `jcmd GC.class_histogram` for `byte[]`. Not observable: a "limit" configuration value, since none exists.

**B2e. Procedure.**
1. Copy tree, build, create the test class and the files above in `$WORK/tmp` (local disk).
2. For each `size` and each (declared, actual) pair: open input, `resetLimit()`, `limit(size)`, read; record throw/no-throw, reflected `limit - limitMark`, and thread-allocated-bytes delta.
3. Repeat step 2 for the configuration knob values in B2b(iii).
4. Positive control (see B2h): write a hint file via `HintsWriteExecutor`-like loop (`HintsWriter.Session.append` with `session.position()` compared to `DatabaseDescriptor.getMaxHintsFileSize()`, as at HintsWriteExecutor.java:243-248) with `max_hints_file_size=1MiB` and 128MiB and record resulting file lengths.

**B2f. Predictions.** Throw iff actual read length exceeds declared `size` (n = size+1 throws; n = size does not). Reflected `limit - limitMark == size` for every config value. `readBufferIfLive` allocation delta is at least `size` bytes and roughly equal to it plus a constant (header and boxing), identical across `max_hints_file_size` and `max_mutation_size` values. Positive control: file length with `max_hints_file_size=1MiB` is about 1 MiB (plus at most one append) and is much smaller than with 128MiB for the same input stream.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `limit - limitMark == size` regardless of config; throw only when read exceeds `size`; allocation tracks `size` not config | Claim confirmed |
| `limit` or allocation changes when `max_hints_file_size` or `max_mutation_size` changes | Claim refuted: a configured value feeds the check |
| Allocation flat across config while positive control file size moves | Confirmed (usage does not follow a constraint here, while a real cap binds elsewhere) |
| Positive control file size does not change with `max_hints_file_size` | Not confirmed: control did not move, setup wrong |
| n = size never throws, or n = size+1 does not throw | Mechanism misread (A3 wrong) |
| `size` too large to allocate with the chosen `-Xmx` | Limit not reached; lower `size` or raise heap |

**B2h. Controls.** Positive control: the write-side cap `max_hints_file_size` (HintsWriteExecutor.java:247) shown to bound file size for the same appended data. Negative control: a read of `size` bytes with `limit` reset to `Long.MAX_VALUE` (no `limit()` call) never throws, showing the throw comes from the per-record limit only. Repeat each case in a fresh JVM to avoid allocation-counter carry-over.

### B3. Cluster tier

**B3a. Environment and build.** Two nodes on local disk, JDK 11, built from a local copy (`ant jar`). Each node: its own `data_file_directories`, `commitlog_directory`, `hints_directory` on a local volume of known free space (at least 5 GiB), `-Xms1G -Xmx1G`, `hinted_handoff_enabled: true`, `max_hint_window: 3h` (default, conf/cassandra.yaml:80). Hint compression off (default) so the position is the file position.

**B3b. Knobs.** `max_hints_file_size` in {1MiB, 128MiB} (yaml, restart needed; the positive control, since it bounds hint file size on disk). `max_mutation_size` default vs reduced (yaml). Value size per write: 1 KiB, 1 MiB, 8 MiB (hint size follows mutation size). No knob exists for `limit`.

**B3c. Workload.** Create RF=2 keyspace and table `(k int primary key, v blob)`. Stop node 2 (`nodetool stopdaemon` or `kill`), write 600 rows of 1 MiB blobs at CL=ONE via `cqlsh`/`cassandra-stress` against node 1: hint payload about 600 MiB, enough to cross 1 MiB and 128 MiB file boundaries (arithmetic: 600 x ~1 MiB = ~600 MiB, so 128MiB gives about 5 files, 1MiB gives hundreds; the 1MiB setting rolls after every append). Then restart node 2 so node 1 dispatches the hints (read path through `HintsReader`, with `ChecksummedDataInput`). Duration about 10 minutes per configuration.

**B3d. Observables and instruments.** Disk: `ls -l` and `du -sb` of node 1's hints directory, file count and per-file size. Heap on node 1 during replay: `jstat -gc <pid> 1000`, `jcmd <pid> GC.class_histogram` (the `[B` class), GC log. Off-heap: `nodetool info`. Hint counters via `nodetool tpstats` / JMX hints metrics. Not directly observable: the value of `limit` in the running node (a private field; use a heap dump with `jcmd GC.heap_dump` only if needed).

**B3e. Procedure.**
1. Start both nodes with `max_hints_file_size: 128MiB`; create schema; stop node 2.
2. Run the 1 MiB-blob workload; after it, record hints directory file sizes. Keep a copy of the sample time series.
3. Restart node 2; during replay sample `jstat -gc` on node 1 every second; record peak heap.
4. Wait until the hints directory is empty; stop both nodes; wipe data.
5. Repeat with `max_hints_file_size: 1MiB`; then with 8 MiB blobs (default `max_mutation_size`) at 128MiB.
6. Check no `java` process is left: `pgrep -f CassandraDaemon`.

**B3f. Predictions.** Hint file sizes: with 128MiB every file except the last is about 128 MiB (at most one hint over); with 1MiB each file is about 1-2 MiB (one hint over) and there are hundreds of files. Peak heap during replay does not depend on `max_hints_file_size` (same 1 MiB hints in both runs, within noise) and scales with the individual hint size (8 MiB blobs: higher transient allocation per hint than 1 MiB), not with any cap on the check. No configuration changes the check's behaviour.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| File sizes follow `max_hints_file_size`; replay peak heap flat across it, rising only with hint size | Claim confirmed (negative estimate holds) |
| Replay peak heap changes with `max_hints_file_size` at fixed hint size | Claim refuted (but first rule out file count effects on caching) |
| File sizes do not follow `max_hints_file_size` | Positive control failed; run not confirmed |
| Hints never dispatched (node 2 never replayed), or heap sampling shows no replay window | Limit/read path not reached; not confirmed |
| Replay fails with `FSReadError` / "Digest mismatch exception" on an undamaged file | A3 wrong on how the check can fire; investigate |

**B3h. Controls.** Positive control: `max_hints_file_size` moving file size (it binds at HintsWriteExecutor.java:247). Same data, same replay, only that knob changed. Run a baseline with no node 2 outage (no hints) to see heap without replay. Repeat each configuration twice with a fresh data directory.

**B4. Risks and cleanup.** Disk: 600 MiB of hints per node-1 run plus data, on local volume; never use shared storage. Heap 1 GiB per node. Leftover processes: `pkill -f CassandraDaemon` for the run's own pids only, then `pgrep -f CassandraDaemon`. Delete `$WORK` data, commitlog and hints directories and the copied source when done. Unit tier writes only under `$WORK/tmp`.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/ChecksummedDataInput.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsReader.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/Hint.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriteExecutor.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java (grep lines 406-407, 446-448)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java (grep lines 898-901, 3590-3598, 3720)
- /users/jason92/cassandra-5.0.9/conf/cassandra.yaml (grep lines 80-106)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/RandomAccessReader.java (grep line 34)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/hints/HintsWriter.java and HintsBuffer.java (grep lines only)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java (grep lines only)

## D. Stage-4 feedback

`none yet`
