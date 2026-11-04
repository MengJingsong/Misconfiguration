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

### B2 amendment: design audit, 2026-10-29 (stage 4; applies `stage4-runtime-verification/none-type-design.md` sections 3 and 4)

The estimate (`negative`) is unchanged. This block supersedes B2a-B2h where they differ; the filed text stays as the record.

**U0. Kind and the meaning of "caps" here.** Kind 3: the operand is `length`, the byte count of a pending read (`b.length` at ChecksummedDataInput.java:192, `len` at 199), compared with the bytes left in the record (`limit`, set by `limit(size)` at 130-134 from the record's own 4-byte `size`). "Usage follows the operand" is expected and is not a finding; the finding is the difference the branch causes at equal operand. "caps" is used only if the true branch reduces or refuses the guarded allocation (`new byte[size]`, Hint.java:239) or bounds retained bytes. A branch that throws after the allocation does not cap that allocation.

**U1. Audit corrections to the filed B2 (citations re-read in `cassandra/cassandra-5.0.9/`).** (a) Confirmed: ChecksummedDataInput.java:48-49, 130-134, 153-157, 159-163, 189-201; HintsReader.java:210-211, 224, 232-234, 240, 316-317, 330, 338-342, and the `FSReadError` rethrows at 198-201 and 304-307; Hint.java:221-243 (`readBufferIfLive`: header `byte[]` at 224, `new byte[size]` at 239, `readFully` at 241); `max_mutation_size` default `commitlog_segment_size / 2` (DatabaseDescriptor.java:898-901). (b) The case file's "not verified" on primitive reads is now verified: `checkLimit` has exactly three call sites (ChecksummedDataInput.java:192 and 199, HintsReader.java:240), so `readInt`/`readLong` and the skip methods never reach it; the guard covers byte-array reads only. (c) New fact: in the buffer iterator (HintsReader.java:340-342) the limit and `readBufferIfLive` take the same `size`, so for a well-formed record the third `checkLimit` sees `position + len == limit` and the check is never true. The true branch is reached only when the declared size and the content disagree (the hint iterator's `deserializeIfLive`, HintsReader.java:239, with inner lengths beyond the record). Arm T below forces that disagreement with `limit(S - 1)` on a record of S bytes; it does not occur on well-formed hints, and the results file says so. (d) The filed B2b(iii) and B2e steps 3-4 (`max_hints_file_size` and `max_mutation_size` variants, the write-side file-length control) are dropped as not discriminating: the check reads no configuration (A1) and the write-side cap acts on a different statement and a different quantity (file length). The positive control becomes the liveness gate of the same method (arm D). (e) The filed 16 MiB top size becomes 64 MiB to go beyond the default `max_mutation_size` (16 MiB at the default 32 MiB segment); the unit tier has no frame limit.

**U2. Launcher.** Plain `java -Xmx1g` (G1), not `ant testsome`, `-Dcassandra.config=` the copy's `test/conf/cassandra.yaml`, the JDK 11 module flags of `conf/jvm11-server.options`; the probe is compiled by `javac` into a separate directory against the copy's classes (package `org.apache.cassandra.hints`, for the package-private constructor and `Hint.serializer.readBufferIfLive`), never copied into a tree. One fresh JVM per size S for pass A (no agent) and one for pass B (Byteman agent, a rule at entry of `ChecksummedDataInput.checkLimit` calling a static counter `stage4.Count.hit()`). Build: `copy-source.sh ~/s4-none`, `ant build-test`, on `pc41` only.

**U3. Sweep, arms, instruments.** Record size S in {1 KiB, 64 KiB, 1 MiB, 16 MiB, 64 MiB} (five orders). The input file holds exactly S bytes: a live header (`creationTime` = the call's `now`, `gcgs` = 864000 as an unsigned vint) then zeros. Arms (each call opens a fresh `ChecksummedDataInput.open(file)`, calls `limit(...)` at position 0, then makes one window `getThreadAllocatedBytes` before and after `Hint.serializer.readBufferIfLive(in, now, S, MessagingService.current_version)`; the open and the limit call are outside the window): **F** `limit(S)` (check false at all three reads, returns a `ByteBuffer` of S bytes); **T** `limit(S - 1)` (the header reads pass, `new byte[S]` is allocated, the third read is the check that throws); **N** no `limit` call (limit `Long.MAX_VALUE`, the filed negative control); **D** (positive control, the liveness gate of the same method, Hint.java:232-236) a dead hint (`creationTime` = 1, `gcgs` = 0) with `limit(S)`: `readBufferIfLive` returns null before `new byte[S]`. Order in one JVM: EMPTY (two readings with nothing between), F1, T1, F2, T2 (F2 and T2 repeat the same input: the noise floor), N, D; 5 repetitions per arm, 3 warm-up calls (S <= 1 MiB: 200). Each call records: threw or returned, the exception message, the returned capacity, the allocation. Retained: for F one result is held while the post-GC used heap (three `System.gc()` calls) is read before and after; for T the same read after the exception.
Controls (pass A): C1 `new byte[S]` through the same window; C3 the EMPTY window; arm D is the positive control (an allocation-gating branch the instrument must see; honest limit: it gates the same allocation but is a liveness test, not a configured cap, and no configured cap binds on this read; the write-side `max_hints_file_size` of the filed text is not used, see U1(d)).

**B2f (amended). Frozen predictions.** All figures bytes, medians of the five repetitions at each S, pass A.
- Q1 (pass B, `checkLimit` entry hits per call): F 3, T 3, N 3, D 2 (two for the header read, `readFully(byte[])` then the `read` it calls, and one for `readFully(bytes, off, len)`; D skips with no check).
- Q2 (outcome): F and N return a buffer of capacity S; T throws `IOException` with message `Digest mismatch exception`; D returns null.
- Q3 (allocation): F in [S + 16, S + 2048]; N within 256 of F; T in [S + 16, S + 6144] and |T - F| at most 6144, at every S (the allocation precedes the throwing read); D at most 4096 at every S and, for S >= 64 KiB, at most S / 8.
- Q4 (noise floor): |F1 - F2| at most 256; |T1 - T2| at most 1024; EMPTY at most 16.
- Q5 (retained, S >= 1 MiB): F's post-GC change in [0.9 S, 1.1 S + 1 MiB]; T's within 2 MiB (plus or minus).
- Q6 (controls): C1 in [S + 16, S + 32]; D moves as in Q3 (the instrument sees an allocation-gating branch).

**B2g (amended). Conclusions table.** The first matching row, in this order.

| Reading | Meaning | Verdict | Effect on the constraint |
|---|---|---|---|
| Pass B hit counts differ from Q1 for F or T at any S, or the outcomes differ from Q2 | the check did not run as designed, or the branch was not flipped | Invalid | undetermined |
| C1 outside Q6, EMPTY above 16, or D does not drop to Q3's bound | the instrument could not show an effect | Not confirmed | undetermined |
| Q1 to Q6 all hold | the check rejects the read after the allocation: T allocates at least S like F, so it does not reduce what is allocated, and nothing is retained after the throw; usage follows the record's own size | Confirmed | does not cap |
| T's allocation below S (by more than the noise floor) at some S | the check precedes the allocation (not as traced) | Refuted | caps |
| T minus F above 6144 and not explained by the exception | the branch costs more than the traced exception | Refuted | undetermined |

**B2h (amended). Controls.** C1, C3, arm D (positive), arm N (negative: no limit, no throw), the identical re-runs F2 and T2.

**U4. Unit-tier limit.** The unit tier measures one call exactly. The hint replay path holds one transient `byte[size]` per hint in flight (up to the mutation size), below the heap noise of about 16 MiB except at 16 MiB mutations, and the check does not fire on well-formed hints, so a cluster run has no branch to flip (see B3).

### B3. Cluster tier

**B3 amendment, 2026-10-29: `n/a: the cluster tier cannot resolve the effect.`** On a well-formed hint the check is never true (U1(c)): the limit and the read take the same `size`, so a hint-replay workload has no branch to flip. The replay heap is one transient `byte[size]` per in-flight hint, at most the mutation size (16 MiB at the defaults), which sits at the heap noise of about 16 MiB with G1; the filed two-node run (600 x 1 MiB hints) restates that heap follows the hint size, which is the expected operand effect and not a finding. The filed B3a-B3h below are not run; they stay as the record. The unit tier alone settles this case.


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

`done 2026-10-29` (unit tier only; B3 amended `n/a`). Results: [`results/none-checklimit-length--autonomous.md`](../../stage4-runtime-verification/results/none-checklimit-length--autonomous.md). **Verdict: Confirmed - does not cap; outcome class true negative** (estimate `negative`, effect `does not cap`). S = 1 KiB .. 64 MiB: with `limit(S)` `readBufferIfLive` allocates S + 184 and returns the buffer; with `limit(S - 1)` it allocates S + 856 (the `byte[S]` precedes the throwing read) and throws "Digest mismatch exception"; the 672-byte difference is the exception; `checkLimit` entered 3 times per call (2 for the dead-hint control); noise floor 0; retained after the throw under 10 kB; the dead-hint control (liveness gate, the same method) cuts the allocation to 120 bytes. All frozen predictions held.

Audit feedback for stage 3 (2026-10-29): (1) in the buffer iterator the limit and `readBufferIfLive` take the same `size` (HintsReader.java:340-342), so on a well-formed record the check never fires; arm T forces it with `limit(S - 1)`, and a corrupt record is the only production path. (2) "Primitive reads do not reach checkLimit" is verified: three call sites only (ChecksummedDataInput.java:192, 199; HintsReader.java:240). (3) The config variants and the write-side `max_hints_file_size` control of the filed B2 were dropped (the check reads no configuration; a different statement and quantity); the control is the liveness gate. (4) B3 is `n/a`. Citations held (`max_mutation_size` default is `commitlog_segment_size / 2`, DatabaseDescriptor.java:898-901).
