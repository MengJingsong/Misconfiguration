# cassandra.commitlog_max_outstanding_replay_bytes — verification solution  <!-- file: cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CommitLogReplayer.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L75) (where the limit `MAX_OUTSTANDING_REPLAY_BYTES` gets its value; the check is at [`CommitLogReplayer.java:525-530`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L525-L530)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`: during commit-log replay the reader thread blocks once the serialized bytes of submitted-but-not-yet-collected mutations exceed the limit, so the heap held by the in-flight (deserialized, not-yet-applied) replay mutations follows the knob, overshooting by at most one mutation. The bound is on serialized bytes and only binds when mutations are large enough that the companion count cap (1024) does not bind first. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cassandra.commitlog_max_outstanding_replay_bytes`, a JVM system property
declared in [`CassandraRelevantProperties.java:114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L114)
as `COMMITLOG_MAX_OUTSTANDING_REPLAY_BYTES`, default `convertToString(1024 * 1024 * 64)` = 67,108,864 bytes (64 MiB),
a hard-coded literal. Unit: bytes (a plain long, no unit suffix). It is read once, at class
initialisation of `CommitLogReplayer`, into the public static non-final field
`MAX_OUTSTANDING_REPLAY_BYTES` ([`CommitLogReplayer.java:75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L75),
`@VisibleForTesting`, so tests assign it directly, e.g. `RecoveryManagerTest.java:132-133`).
Settable only by `-Dcassandra.commitlog_max_outstanding_replay_bytes=<bytes>` on the JVM command
line (e.g. a line in `conf/jvm-server.options` or `JVM_EXTRA_OPTS`); not in `cassandra.yaml`, not via JMX/nodetool.
It matters only during commit-log replay, which happens at startup, so a change needs a restart.
Companion constraint: `cassandra.commitlog_max_outstanding_replay_count`, default 1024
(`CassandraRelevantProperties.java:115`, read at `CommitLogReplayer.java:79` into a `static final`).

**A2. What it caps.** Heap. The compared quantity is `pendingMutationBytes`
(`CommitLogReplayer.java:89`): the sum of the **serialized** sizes (the commit-log entry length,
`CommitLogReader.java:324`, passed as `size` at `CommitLogReader.java:478`) of mutations that the
replay reader has deserialized and submitted to the MUTATION stage but whose futures it has not yet
collected. Each such mutation is a fully deserialized `Mutation` object graph on the heap, held by the
runnable queued in the MUTATION stage (`CommitLogReplayer.java:290-331`). Cell values are copied into
fresh arrays on deserialization (`ByteBufferUtil.java:444-452`; they must be, because the reader reuses
one `byte[] buffer` for every entry, `CommitLogReader.java:365-367`), so for large-value mutations the
heap of the backlog is roughly its serialized size, plus object overhead that is significant only for
small mutations.

**A3. Mechanism.**
1. `CommitLog.recoverSegmentsOnDisk` (`CommitLog.java:182`, replay at `CommitLog.java:205-211`) runs at
   startup and calls `recoverFiles` → `CommitLogReplayer.replayFiles` → `replayPath`
   (`CommitLogReplayer.java:189-195`) → `CommitLogReader.readCommitLogSegment`, a single reader thread.
2. For each entry the reader reads `serializedSize` bytes into its buffer (`CommitLogReader.java:324-367`),
   deserializes a `Mutation` (`CommitLogReader.java:429-434`) and calls
   `handler.handleMutation(mutation, size, ...)` (`CommitLogReader.java:478`).
3. `handleMutation` (`CommitLogReplayer.java:512-531`) adds `size` to `pendingMutationBytes` (line 517)
   and enqueues the future returned by `mutationInitiator.initiateMutation` (lines 518-522), which
   submits a runnable to `Stage.MUTATION` with result `serializedSize` (`CommitLogReplayer.java:331`;
   stage size = `concurrent_writes`, `Stage.java:46`).
4. **The check**, [`CommitLogReplayer.java:525-530`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L525-L530):
   `while (futures.size() > MAX_OUTSTANDING_REPLAY_COUNT || pendingMutationBytes > MAX_OUTSTANDING_REPLAY_BYTES || (!futures.isEmpty() && futures.peek().isDone()))`
   `pendingMutationBytes -= FBUtilities.waitOnFuture(futures.poll());`
   - Over the byte limit: the reader thread **blocks** on the oldest future (FIFO) until it completes,
     subtracts its size, and repeats until the total is ≤ the limit. No data is dropped and nothing fails;
     replay is throttled.
   - Under the limit: completed futures at the head are reaped without blocking; reading continues.
5. At the end, `blockForWrites` waits for all remaining futures (`CommitLogReplayer.java:244-251`).

Overshoot: the size is added and the mutation is already deserialized and submitted *before* the check,
so momentarily `pendingMutationBytes ≤ limit + size(last mutation)`; the last mutation is at most
`max_mutation_size` (default half of `commitlog_segment_size`, `conf/cassandra.yaml:652-660`). Bypasses:
the count cap may bind first (with default 1024, for mutations smaller than 64 KiB the count limit is
tighter than the byte limit); serialized size understates heap size for small mutations (object overhead);
the check counts only the replay backlog, not the memtable the mutations are applied into.

**A4. Other consumers.** Memtables that replayed mutations are applied into (bounded by
`memtable_heap_space`/`memtable_offheap_space`, flushed when full; and a final flush in
`blockForWrites`, `CommitLogReplayer.java:253-272`); the reader's reusable buffer (≤ 1.2 × largest
entry, `CommitLogReader.java:365-366`); segment read/decompression buffers; mutations being applied
(still counted, they stay in `futures` until collected); everything else on the startup heap (schema,
system keyspace, caches, index summaries).

**A5. Evidence beyond the source.** `NEWS.txt:1292-1293` ("bound maximum in-flight commit log replay
mutation bytes to 64 megabytes tunable via cassandra.commitlog_max_outstanding_replay_bytes");
`CHANGES.txt:3241` (CASSANDRA-8639, https://issues.apache.org/jira/browse/CASSANDRA-8639);
`CHANGES.txt:4034` (count override, CASSANDRA-7533); `test/unit/org/apache/cassandra/db/RecoveryManagerTest.java:129-195`
(`testRecoverBlocksOnBytesOutstanding`: with the limit = 1 the reader blocks on an unfinished mutation).

## B. Verification solution

**B1. Claim under test.** During commit-log replay, the serialized bytes of in-flight replay mutations
never exceed `cassandra.commitlog_max_outstanding_replay_bytes` plus one mutation, and the live heap
held by not-yet-applied replay `Mutation` objects scales with that setting (≈ limit for large-value
mutations) when the count cap is not binding and the apply side is slower than the reader. The claim is
wrong if the backlog grows past limit + one mutation, or if the backlog heap does not change when the
limit changes while an unbounded run shows a much larger backlog.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk:
`rsync -a <shared>/cassandra-5.0.9/ /mydata/s4-o32/cassandra-5.0.9/` and work only there.
`cd /mydata/s4-o32/cassandra-5.0.9 && ant build-test` (or `ant jar` then `ant build-test`).
Add one test file `test/unit/org/apache/cassandra/db/commitlog/OutstandingReplayBytesProbeTest.java`
(in the copy). JVM options: the Ant defaults; the test config `test/conf/cassandra.yaml` uses
`commitlog_segment_size: 5MiB` (max mutation 2.5 MiB) and heap_buffers memtables.

**B2b. Knobs.** `CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES` assigned in the test (the
field the check reads) to 1 MiB (1,048,576), 4 MiB (4,194,304), 16 MiB (16,777,216), and 1 GiB
(1,073,741,824 = effectively unbounded for this workload, the positive control). The count cap stays at
its default 1024 and the workload has 1000 mutations, so the count cap can never bind (1000 < 1024).

**B2c. Workload.** Schema: keyspace `ReplayProbe` (simple, RF 1), table `SchemaLoader.standardCFMD("ReplayProbe","T")`.
Write 1000 mutations, each one row with partition key `"k"+i`, clustering `"c"`, `val` = a 60,000-character
ASCII string, via `new RowUpdateBuilder(metadata, 0, "k"+i).clustering("c").add("val", big).build().applyUnsafe()`.
Each serialized entry is ≈ 60,050–60,200 bytes (call it s), total ≈ 60 MB (≈ 12 test segments).
A probe `MutationInitiator` replaces the real one: it does **not** apply the mutation, it submits a task
to its own single-thread executor that sleeps 5 ms and returns `serializedSize`. The reader deserializes a
60 KB entry in well under 5 ms, so the reader outruns the consumer and the backlog grows until the check
blocks: limits of 1/4/16 MiB = 17/69/279 mutations ≪ 1000, so every finite limit is reached; with 1 GiB
the backlog can reach up to the whole 60 MB.

**B2d. Observables and instruments.** In the probe's `initiateMutation`, read the replayer's private
`pendingMutationBytes` by reflection (`Field f = CommitLogReplayer.class.getDeclaredField("pendingMutationBytes"); f.setAccessible(true)`)
— this is the operand right after line 517 adds the current mutation, i.e. the pre-drain peak — and keep
its maximum (`peakPending`). Also record `maxQueued` = maximum of the probe executor's not-yet-run task
count (in-flight mutations still referenced), and `s` (max `serializedSize`). Print one line per knob:
`LIMIT=<b> peakPending=<b> maxQueued=<n> s=<b> calls=<n>`. Not directly observable here: the heap bytes
of the queued `Mutation`s (cluster tier measures that).

**B2e. Procedure.**
1. Write the test class (JUnit4; `@BeforeClass`: `SchemaLoader.prepareServer(); SchemaLoader.createKeyspace(...)`).
   One `@Test` method loops over the four limits; for each:
   a. `CommitLog.instance.resetUnsafe(true);` truncate the table;
   b. write the 1000 mutations (B2c);
   c. `CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = limit; CommitLogReplayer.mutationInitiator = probe;` (reset probe counters);
   d. `CommitLog.instance.resetUnsafe(false);` — this restarts the commit log and replays the written segments (`CommitLog.java:516`, `567`);
   e. print the line; `assertEquals(1000, probe.calls)`;
   f. in `finally`, restore the original initiator and limit, shut down the probe executor.
2. `ant testsome -Dtest.name=org.apache.cassandra.db.commitlog.OutstandingReplayBytesProbeTest`
3. Read the lines from `build/test/output/TEST-org.apache.cassandra.db.commitlog.OutstandingReplayBytesProbeTest.txt` (or the console).

**B2f. Predictions.** For each finite limit L: `L − s < peakPending ≤ L + s` (i.e. ≈1.05 MB, 4.2 MB,
16.8 MB within one 60 KB entry) and `maxQueued ≤ floor(L/s) + 1` (≈ 18, 70, 280). For L = 1 GiB:
`peakPending` ≈ total written (≥ 30 MB, up to ≈ 60 MB) and `maxQueued` ≫ 280. `calls = 1000` in every run.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| peakPending ∈ (L − s, L + s] and maxQueued ≈ L/s for each finite L; 1 GiB run much larger | claim confirmed at unit level: the check caps the operand |
| peakPending > L + s for some finite L | claim wrong: the check does not bound the operand |
| peakPending ≪ L for finite L and the 1 GiB run also small | limit never reached (consumer too fast): not confirmed; raise the sleep to 20 ms and rerun |
| calls ≠ 1000 | workload did not replay as intended (segments skipped / filtered); result void |

**B2h. Controls.** The 1 GiB run is the positive control (same workload, cap not binding → large backlog).
1000 < 1024 rules out the count cap. Using a probe that does not apply mutations removes memtable/flush
timing; the reflection read is the exact operand of the check.

### B3. Cluster tier

**B3a. Environment and build.** One node, the stage-4 host (16 cores, ~14 GiB free). JDK 11.
Copy as in B2a; `ant jar` (and `ant stress-build` for `tools/bin/cassandra-stress`). All node
directories on local disk under `/mydata/s4-o32/node/` (`data_file_directories`, `commitlog_directory`,
`hints_directory`, `saved_caches_directory`, `cdc_raw_directory`; logs via `CASSANDRA_LOG_DIR=/mydata/s4-o32/node/logs`).
Heap: `MAX_HEAP_SIZE=6G HEAP_NEWSIZE=1200M` (G1, `conf/jvm11-server.options:63`). `cassandra.yaml` for
the **load** phase: `commitlog_total_space: 4096MiB`, `memtable_heap_space: 3072MiB`,
`memtable_allocation_type: heap_buffers`, default `commitlog_segment_size: 32MiB`, `listen/rpc_address: 127.0.0.1`.
For the **replay** phase change two lines: `concurrent_writes: 1` and `memtable_heap_space: 256MiB`
(slows the apply side: one applier, and it must wait for flushes), so the reader outruns appliers.
Add to `conf/jvm-server.options` for all replay runs: `-Dcassandra.commitlog_max_outstanding_replay_count=100000000`
(so only the byte cap can bind).

**B3b. Knobs.** `-Dcassandra.commitlog_max_outstanding_replay_bytes` in `conf/jvm-server.options`:
`16777216` (16 MiB), `67108864` (64 MiB, default), `268435456` (256 MiB), and `4294967296` (4 GiB,
unbounded for this workload: positive control). Plus one count-cap control run: bytes = 4 GiB and
`commitlog_max_outstanding_replay_count=16` (a cap known to bind: ≤ 17 mutations ≈ 1 MiB).
Each value needs a fresh start of the node.

**B3c. Workload.** Load phase (once): start the node, then
`tools/bin/cassandra-stress write n=24000 no-warmup -rate threads=16 -col n=FIXED(1) size=FIXED(65536) -node 127.0.0.1`
→ 24,000 × ≈64 KiB ≈ 1.5 GiB of mutations in ≈ 48 commit-log segments (below `commitlog_total_space` 4 GiB and
memtable 3 GiB, so nothing is flushed — verify `nodetool tablestats keyspace1.standard1` shows SSTable count 0).
Wait 15 s (periodic sync 10 s), then `kill -9` the node. Save the pristine state:
`rsync -a /mydata/s4-o32/node/ /mydata/s4-o32/pristine/`. Each replay run restores it first, so every run
replays the same ≈1.5 GiB. Replay of 1.5 GiB with each limit ≪ 1.5 GiB means every finite limit is reached
if appliers are slower than the reader; expected duration tens of seconds to a few minutes per run.

**B3d. Observables and instruments.**
- Backlog heap: `jcmd <pid> GC.class_histogram` every 2 s from JVM start until the log line
  `Log replay complete` (CommitLog.java:210); record instance count of `org.apache.cassandra.db.Mutation`
  (and `org.apache.cassandra.db.partitions.PartitionUpdate`). In-flight heap ≈ Mutation count × 65.6 KB
  (each holds one 64 KiB value array). `GC.class_histogram` forces a full GC, so counts are live objects.
- Total live heap: `jcmd <pid> GC.heap_info` at the same instants (used after the histogram's full GC).
- Timing: `Replaying ...` and `Log replay complete, N replayed mutations in M ms` in `system.log`.
- Not observable directly: `pendingMutationBytes` itself (private field; unit tier covers it); the heap of
  mutations by byte[] class (mixed with memtable slabs), hence the Mutation-count proxy.

**B3e. Procedure.**
1. Configure load-phase yaml; `bin/cassandra -p /mydata/s4-o32/node/pid`; wait for CQL port; run stress (B3c); check no SSTables; `sleep 15; kill -9 $(cat /mydata/s4-o32/node/pid)`; save pristine copy.
2. Switch yaml to replay-phase values; add the count property line.
3. For each knob value: `rsync -a --delete /mydata/s4-o32/pristine/ /mydata/s4-o32/node/`; set the bytes line in `conf/jvm-server.options`;
   `bin/cassandra -p /mydata/s4-o32/node/pid`; immediately loop
   `while ! grep -q "Log replay complete" /mydata/s4-o32/node/logs/system.log; do jcmd $(cat /mydata/s4-o32/node/pid) GC.class_histogram | grep -E " org.apache.cassandra.db.(Mutation|partitions.PartitionUpdate)$" ; jcmd $(cat ...pid) GC.heap_info | head -3; sleep 2; done > /mydata/s4-o32/run-<value>.txt`;
   record the replay line; check `N replayed mutations` ≈ 24,000 (plus system writes); `bin/nodetool stopdaemon` (or `kill`), confirm the process is gone.
4. Count-cap control run (B3b) the same way.
5. Compute per run: max Mutation count, max used heap.

**B3f. Predictions.** Let s ≈ 65.6 KB. Max live `Mutation` count during replay ≤ L/s + 1 (+ a handful of
small system mutations): 16 MiB → ≤ ~257; 64 MiB → ≤ ~1,024; 256 MiB → ≤ ~4,093. 4 GiB (unbounded):
a much larger count, ≥ 4× the 256 MiB run (order 10^4) if the reader outruns the single applier. Count
cap 16 → ≤ ~17. Max used heap rises with L roughly by (ΔMutation count × s): 256 MiB run ≥ 200 MB above
the 16 MiB run; the 4 GiB run higher still. Replay completes in every run with N ≈ 24,000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Max Mutation count ≈ L/s (within one + system mutations) for each finite L, unbounded run much larger, heap rises with L | claim confirmed: the knob governs the replay backlog heap |
| Max Mutation count > L/s + small slack for some finite L | claim wrong: the backlog is not capped by the byte limit |
| All runs, including 4 GiB, show small and similar counts (≪ 257) | limit never reached: appliers keep up; not confirmed — rerun with `memtable_heap_space: 64MiB` or more data |
| Count-cap control does not stay ≤ ~17 | instrument or workload wrong (positive control failed); result void |
| N replayed ≪ 24,000 | the commit log was flushed or not restored; result void |

**B3h. Controls.** The 4 GiB run (same workload, no binding byte cap) shows the workload can produce a
large backlog; the count = 16 run shows the instrument sees a cap that is known to bind. The pristine
restore makes all runs replay identical segments. The count cap is set to 10^8 so it cannot explain the
finite-L results. Memtable usage is held to 256 MiB in every run, so heap differences across runs come from
the backlog.

**B4. Risks and cleanup.** Disk: ≈1.5 GiB commit log + pristine copy ≈ 3.5 GiB plus flushed SSTables
≈ 1.5 GiB per run, all on `/mydata/s4-o32/` (local). Never build in the shared tree. 6 GiB heap fits in
14 GiB free; the 4 GiB-limit run could hold ≈1.5 GiB of backlog plus memtables, still under 6 GiB.
After every run and at the end: `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` must return
nothing (kill leftovers); unit-tier test JVMs exit with Ant. Finally `rm -rf /mydata/s4-o32/node /mydata/s4-o32/pristine`
(keep the run-*.txt files and logs).

## C. Sources read

/users/jason92/writeup-ext/playbook-autonomous.md
/users/jason92/writeup-ext/_TEMPLATE-autonomous.md
src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java
src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java
src/java/org/apache/cassandra/db/commitlog/CommitLog.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/concurrent/Stage.java
src/java/org/apache/cassandra/utils/ByteBufferUtil.java
src/java/org/apache/cassandra/io/util/DataInputBuffer.java
test/unit/org/apache/cassandra/db/RecoveryManagerTest.java
test/unit/org/apache/cassandra/SchemaLoader.java
test/unit/org/apache/cassandra/db/RowUpdateBuilder.java
test/conf/cassandra.yaml
conf/cassandra.yaml
conf/jvm11-server.options
build.xml
NEWS.txt
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-8639 (cited from CHANGES.txt; not fetched)

## D. Stage-4 feedback

**Stage 4, 2026-11-11 (results: `cassandra/stage4-runtime-verification/results/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md`; harness: `cassandra/stage4-runtime-verification/harness/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous/`).** Unit **Confirmed — caps** (B2g row 1); cluster **Confirmed — caps** (B3g row 1); outcome class **true positive**. Unit: `pendingMutationBytes` peaked within one 60,050-byte entry above L for L = 1, 4 and 16 MiB (overshoot 9-37 KB) and reached 58 MB of the 60 MB written with L = 1 GiB; maxQueued 18 / 70 / 288 (B2f's strict bound floor(L/s)+1 = 280 at 16 MiB was missed by 8, while 12 small system mutations also passed through the probe in that run). Cluster (6 GiB heap, 256 MiB memtable pool, 24,048 mutations of about 65.6 KB replayed from one pristine commit log in every run): the live replay `Mutation` count plateaued at 256 / 1024 / 4093 = L/s for 16 / 64 (default) / 256 MiB, reached 19,933 with 4 GiB, and stayed at 17 with the count cap 16; live heap 388 / 489 / 895 / 2,985 MB. The trace in A3 held. **Correction to A2 / B1 (not a refutation):** the backlog's heap is about **2 x** its serialized size for these mutations (about 132 KB per 65.6 KB mutation, from two independent run pairs), not "roughly its serialized size": `Mutation.serializer.deserialize` keeps a copy of the serialized bytes of every mutation under `CACHEABLE_MUTATION_SIZE_LIMIT` (2 MB) in `cachedSerializations` (`Mutation.java:490-519`), so the bound on heap is about 2 x the limit (plus overhead) for mutations under 2 MB.

**Stage-4 design-audit amendments, 2026-11-11** (made before run 1; none depends on a reading; they are recorded here only, the text of sections A-B is unchanged, and none changes B2f, B2g, B3f or B3g):
- **M1 (B2a, B3a, B3e, B4: paths and ports).** The working tree is a `copy-source.sh` copy, built on the stage-4 node; every path `/mydata/s4-o32/` reads `/mydata/jingsong-cass-s4/o32/` (the node is shared). The node uses `storage_port` 7300, `ssl_storage_port` 7301, JMX 7499 (`JMX_PORT` in `conf/cassandra-env.sh`), `native_transport_port` 9342; the stress command (B3c) adds `-port native=9342 jmx=7499`, and `nodetool` adds `-p 7499`. The node tree is a second copy built with `ant jar`, separate from the unit-tier tree.
- **M2 (B3a: `concurrent_writes: 1` cannot run).** `DatabaseDescriptor.java:565-567` refuses `concurrent_writes < 2` ("concurrent_writes must be at least 2"), so the replay phase sets `concurrent_writes: 2` (two appliers, the fewest the node accepts). B3f does not depend on the number of appliers; the "appliers keep up" outcome is B3g row 3.
- **M3 (B3a/B3c: the load would flush).** With the default `memtable_cleanup_threshold` = 1/(1 + 2 flush writers) = 0.33, a flush starts at about 1 GiB of the 3072 MiB pool, below the 1.5 GiB load, and a flush discards commit-log segments, so the "SSTable count 0" check of B3c would fail. The yaml sets `memtable_cleanup_threshold: 0.99` (the maximum accepted, `DatabaseDescriptor.java:772`) in the load phase; the replay phase keeps it (only the two lines of B3a change), so every replay run has the same 256 MiB pool that flushes when nearly full.
- **M4 (B2d/B2e.e: what `calls` counts).** Commit-log replay hands every mutation in the segments to `handleMutation`, including small `system` keyspace writes (for example the truncation record of step a). `calls` counts the probe's calls for keyspace `ReplayProbe` (the workload); the other calls are counted as `callsOther` with their largest size, and they still pass through `pendingMutationBytes` like any mutation. `s` is the largest `ReplayProbe` serialized size.
- **M5 (B3d/B3e.3: sampler).** The 2 s sampling loop of B3e.3 is a Python script (harness) that records, per sample, the epoch time, the instance counts and bytes of `org.apache.cassandra.db.Mutation` and `org.apache.cassandra.db.partitions.PartitionUpdate` (exact class-name match), the histogram `Total` bytes (live heap after the histogram's full GC) and the `GC.heap_info` used figure, until `Log replay complete` appears in `system.log`. "Max used heap" in B3f is read from `GC.heap_info` as filed; the histogram total is reported beside it. The node is stopped with SIGTERM to its recorded PID (then SIGKILL if it is still alive after 60 s); B3c's `kill -9` targets the recorded PID only.
- **M6 (B2c/B2e.1b: runbook defect D1, found by the instrument shakedown before run 1).** `Mutation.applyUnsafe()` is `apply(false)` (`Mutation.java:272-275`): durable writes off, so the 1000 mutations never reach the commit log and nothing is replayed (shakedown with L = 1 byte: `calls=0`, one 91-byte system mutation replayed). The workload uses `...build().apply()` (the keyspace's `durable_writes`, true for `KeyspaceParams.simple(1)`). Nothing else in B2 changes.
