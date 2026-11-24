# cassandra.commitlog_max_outstanding_replay_count — verification solution  <!-- file: cases/commitlog_max_outstanding_replay_count-handlemutation-futures_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the static field that holds the cap is set here): [`CommitLogReplayer.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L79) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The count caps how many replayed mutations are in flight (deserialized `Mutation` + task + future, held on heap) during startup commit-log replay: after every `handleMutation` the queue is drained down to the cap (`futures.size() <= MAX_OUTSTANDING_REPLAY_COUNT`). This heap grows with the cap whenever the mutation stage lags the reader. The cap matters for memory only when the bytes cap does not bind first (average serialized mutation < 64 MiB / 1024 = 64 KiB at defaults). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cassandra.commitlog_max_outstanding_replay_count`, a JVM system property
(enum constant `COMMITLOG_MAX_OUTSTANDING_REPLAY_COUNT`), first declared at
[`CassandraRelevantProperties.java:115`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L115)
with default string `"1024"`. Unit: number of mutations (replay futures). The default is a literal; it
is read once with `getInt()` (`CassandraRelevantProperties.java:794-800`: `System.getProperty(key)`,
otherwise the default) into `private static final int MAX_OUTSTANDING_REPLAY_COUNT` at the given line,
[`CommitLogReplayer.java:79`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L79),
at class initialization. Set only with `-Dcassandra.commitlog_max_outstanding_replay_count=<n>` on the JVM
command line (for example through `JVM_EXTRA_OPTS` or `conf/jvm-server.options`). It is not in
`cassandra.yaml` and has no JMX setter. The field is `static final`, so a change needs a JVM restart. That is
no real limit, because the value is only used during startup replay. The sibling cap
`cassandra.commitlog_max_outstanding_replay_bytes` (default 64 MiB, `CassandraRelevantProperties.java:114`)
is read into the non-final, `@VisibleForTesting` public field `MAX_OUTSTANDING_REPLAY_BYTES`
(`CommitLogReplayer.java:75`). Tests can therefore override the bytes cap in-process but not the count cap.

**A2. What it caps.** It caps the JVM **heap**. The compared quantity is `futures.size()`, the length of the
`ArrayDeque<Future<Integer>>` of replay mutations submitted to `Stage.MUTATION` and not yet polled
(`CommitLogReplayer.java:82,106`). Each queued entry that has not yet run keeps reachable the deserialized
`Mutation` (with its `PartitionUpdate`s, rows, cells and key/value `ByteBuffer` copies), the anonymous
`WrappedRunnable` (`CommitLogReplayer$MutationInitiator$1`, `CommitLogReplayer.java:290-330`) and its
`FutureTask` in the MutationStage queue. After a task runs, `FutureTask.run()` clears `call`
(`src/java/org/apache/cassandra/concurrent/FutureTask.java:79`), so a finished entry still in the deque holds
only the small future. In-flight replay heap ≈ (entries not yet run) × (heap per deserialized mutation + task
overhead), and the cap bounds the number of entries.

**A3. Mechanism.**
1. Startup: `CassandraDaemon.setup()` → `CommitLog.instance.recoverSegmentsOnDisk()` (`CassandraDaemon.java:345`)
   → `recoverFiles` (`CommitLog.java:226-231`) → `CommitLogReplayer.replayFiles` (`CommitLogReplayer.java:197-209`)
   → `CommitLogReader.readCommitLogSegment` → for each entry, `readFully` into one reused `byte[]`
   (`CommitLogReader.java:365-366`), then `readMutation` deserializes a fresh `Mutation`, copying the values out
   of the reused buffer (`CommitLogReader.java:429-433`). The reader calls `handler.handleMutation(...)` only
   when the entry is past the global replay position (`CommitLogReader.java:477-478`).
2. `handleMutation` (`CommitLogReplayer.java:512-531`) adds `size` (serialized bytes) to `pendingMutationBytes`
   (`:517`). It calls `mutationInitiator.initiateMutation(...)`, which submits the runnable to `Stage.MUTATION`
   with the serialized size as the future's result (`:331`), and offers the future to `futures` (`:518`).
3. The check is
   [`CommitLogReplayer.java:525-527`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java#L525-L527):
   `while (futures.size() > MAX_OUTSTANDING_REPLAY_COUNT || pendingMutationBytes > MAX_OUTSTANDING_REPLAY_BYTES || (!futures.isEmpty() && futures.peek().isDone()))`.
   The body (`:529`) polls the head and **blocks the single replay (reader) thread** in
   `FBUtilities.waitOnFuture` until that mutation has been applied, then subtracts its size.
4. Outcomes. Under the cap, only completed head futures are drained and reading continues. When the cap is
   reached (`size` = cap + 1 right after the offer), the reader blocks on the oldest outstanding mutation until
   `size <= cap`. This is back-pressure, not rejection: nothing is dropped and no error is raised. Steady-state
   bound: at most `cap + 1` entries momentarily (between `:518` and `:525`) and at most `cap` after each call.
5. Bypasses and overshoot:
   - The bound is in entries, not bytes. Heap per entry depends on mutation shape, so `cap × heap-per-mutation` is
     unbounded in principle. One huge mutation is only bounded by the bytes cap and by the commit log's maximum
     mutation size.
   - The bytes cap (`:526`) is counted in **serialized** bytes. Deserialized heap per mutation is a multiple of that
     for small mutations, so the count cap is what limits object overhead when mutations are small.
   - `recoverPath` (`CommitLog.java:233-238`, `CommitLogReplayer.replayPath`) goes through the same
     `handleMutation`, so it is not a bypass.
   - Entries before `globalPosition` are deserialized but never reach `handleMutation` (`CommitLogReader.java:477`).
     They hold no queue memory.
   - The queue only grows when the MutationStage (`concurrent_writes` threads, `Stage.java:46`) applies more
     slowly than the single reader thread reads, checksums and deserializes. If the stage keeps up, the third
     condition drains continuously and the cap never binds.

**A4. Other consumers.** Other heap users during replay that this cap does not control:
- memtables filled by the replayed writes (bounded by `memtable_heap_space` / `memtable_offheap_space` and flushing);
- the reader's reused `byte[]` buffer (`CommitLogReader.java:67,366`, grows to 1.2 × the largest entry);
- the decompression and decryption buffers for compressed or encrypted segments;
- the MutationStage queue itself, whose tasks are exactly these entries (so it is covered);
- the `invalidMutations` map;
- the `cfPersisted` interval sets;
- view and batchlog work, and the final flushes in `blockForWrites` (`CommitLogReplayer.java:244-275`).

Disk is not involved: replay reads segments and later flushes sstables, and neither depends on this cap.

**A5. Evidence beyond the source.**
- `CHANGES.txt:4034` "Allow overriding MAX_OUTSTANDING_REPLAY_COUNT (CASSANDRA-7533)", https://issues.apache.org/jira/browse/CASSANDRA-7533
- `CHANGES.txt:3241` and `NEWS.txt:1291-1292` "bound maximum in-flight commit log replay mutation bytes to 64 megabytes" (CASSANDRA-8639, the sibling bytes cap), https://issues.apache.org/jira/browse/CASSANDRA-8639
- `test/unit/org/apache/cassandra/db/RecoveryManagerTest.java:129-196` (`testRecoverBlocksOnBytesOutstanding`): the template for overriding `mutationInitiator`. It tests only the bytes cap; no test exercises the count cap.

## B. Verification solution

**B1. Claim under test.** During commit-log replay, with the mutation stage slower than the reader and the bytes
cap out of the way, the number of replay mutations outstanding never exceeds
`cassandra.commitlog_max_outstanding_replay_count` + 1 and does reach it. The heap held by those in-flight
mutations therefore grows with the cap, about `cap × (heap per mutation)`. The claim is wrong if outstanding
entries exceed the cap, or if the live heap during replay does not grow with the cap while the bytes-cap control
does move it.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` shows 11), Ant.
- Copy the tree to local disk and never build in the shared copy:
  `export SRC=/mydata/$USER-s4/c509-unit; mkdir -p $(dirname $SRC); rsync -a <shared cassandra-5.0.9 source>/ $SRC/`.
- Build: `cd $SRC && ant clean jar build-test` (fetches the dependencies; needs network to Maven Central the first time).
- The test goes in `$SRC/test/unit/org/apache/cassandra/db/commitlog/ReplayOutstandingCountTest.java`. It uses the
  same package as `CommitLogReplayer`, so it can reach the package-private API and, by reflection, the private fields.
- JVM options are passed with `-Dtest.jvm.args=...` (`build.xml:94,1192`); the test harness already adds
  `-Dcassandra.skip_sync=true` (`build.xml:1390`).

**B2b. Knobs.**
- Count cap `C` = `-Dcassandra.commitlog_max_outstanding_replay_count` ∈ {16, 256, 4096}. Each is ≥ 16× the next
  smaller one, all are well below the workload N = 20000, and 4096 is 4× the default 1024. Set per JVM through
  `-Dtest.jvm.args`, because the field is `static final`.
- The bytes cap is set in-process to `Long.MAX_VALUE` through the public field (`replay.bytes_cap` property), so
  only the count can bind.
- Controls:
  - bytes cap = 4096 bytes with C = 4096 (known-binding cap);
  - consumer delay 0 with C = 4096 (no backlog).

**B2c. Workload.**
- N = 20000 single-row mutations (`Standard1`, key `key<i>`, clustering `c`, `val` = `"v"`), written through the
  normal `Mutation.apply()`, which writes to the commit log. Then `CommitLog.instance.resetUnsafe(false)` replays
  the segments.
- A replacement `MutationInitiator` completes each future on **one** consumer thread after `parkNanos(200 µs)`.
  It consumes ≤ ~5000 mutations/s, while the reader deserializes tens of thousands per second, so the queue fills.
- Arithmetic: 20000 > 4096, so every cap value is reached, and it is reached within the first ≤ 4096 entries,
  in milliseconds.
- Consumer time is about 20000 × ≥ 0.2 ms ≈ 4–6 s per run. Each mutation is ~40–60 serialized bytes, so the
  largest bytes total held, 4096 × 60 B ≈ 240 KB, is far below 64 MiB. The bytes cap would not bind even at its
  default.

**B2d. Observables and instruments.** In `initiateMutation`, called by `handleMutation` before the offer, the test
reads the following by reflection on the replayer passed in:
- `futures.size()`;
- `pendingMutationBytes`, which already includes the current mutation (`:517`).

It records:
- `peak_queue` = max(`futures.size()` + 1), the size right after the offer;
- `peak_pending_bytes`;
- `peak_not_yet_run`, the number of mutations whose consumer task has not run. Each task keeps its `Mutation`
  reachable until it runs, as the real `FutureTask` does;
- `handled`, the number of `handleMutation` calls.

It prints one line, `RESULT ...`. The heap per entry is not measured here; that is the cluster tier's job.

**B2e. Procedure.**
1. Create the test file:

```java
package org.apache.cassandra.db.commitlog;

import java.lang.reflect.Field;
import java.util.Queue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.locks.LockSupport;

import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.db.ColumnFamilyStore;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.db.Mutation;
import org.apache.cassandra.db.RowUpdateBuilder;
import org.apache.cassandra.schema.KeyspaceParams;
import org.apache.cassandra.utils.concurrent.AsyncPromise;

public class ReplayOutstandingCountTest
{
    static final String KS = "ReplayCountKS", CF = "Standard1";
    static final int N = Integer.getInteger("replay.n", 20000);
    static final long CONSUMER_NANOS = Long.getLong("replay.consumer_nanos", 200_000L);
    static final long BYTES_CAP = Long.getLong("replay.bytes_cap", Long.MAX_VALUE);

    @BeforeClass
    public static void schema()
    {
        SchemaLoader.prepareServer();
        SchemaLoader.createKeyspace(KS, KeyspaceParams.simple(1), SchemaLoader.standardCFMD(KS, CF));
    }

    static final class SlowInitiator extends CommitLogReplayer.MutationInitiator
    {
        final ExecutorService consumer = Executors.newSingleThreadExecutor();
        final AtomicInteger notYetRun = new AtomicInteger();
        final AtomicLong handled = new AtomicLong();
        volatile int peakQueue, peakNotYetRun;
        volatile long peakPendingBytes;
        final Field futuresF, pendingF;

        SlowInitiator() throws Exception
        {
            futuresF = CommitLogReplayer.class.getDeclaredField("futures");
            futuresF.setAccessible(true);
            pendingF = CommitLogReplayer.class.getDeclaredField("pendingMutationBytes");
            pendingF.setAccessible(true);
        }

        @Override
        protected org.apache.cassandra.utils.concurrent.Future<Integer> initiateMutation(Mutation m, long segmentId, int size,
                                                                                         int entryLocation, CommitLogReplayer clr)
        {
            try
            {
                int q = ((Queue<?>) futuresF.get(clr)).size() + 1;   // size right after the coming offer
                long pb = pendingF.getLong(clr);                      // already includes this mutation
                if (q > peakQueue) peakQueue = q;
                if (pb > peakPendingBytes) peakPendingBytes = pb;
            }
            catch (IllegalAccessException e) { throw new AssertionError(e); }
            handled.incrementAndGet();
            int nyr = notYetRun.incrementAndGet();
            if (nyr > peakNotYetRun) peakNotYetRun = nyr;
            final Mutation[] hold = { m };                            // reachable until run, like the real FutureTask
            final AsyncPromise<Integer> p = new AsyncPromise<>();
            consumer.execute(() -> {
                if (CONSUMER_NANOS > 0) LockSupport.parkNanos(CONSUMER_NANOS);
                hold[0] = null;
                notYetRun.decrementAndGet();
                p.trySuccess(size);
            });
            return p;
        }
    }

    @Test
    public void measure() throws Exception
    {
        CommitLog.instance.resetUnsafe(true);
        ColumnFamilyStore cfs = Keyspace.open(KS).getColumnFamilyStore(CF);
        for (int i = 0; i < N; i++)
            new RowUpdateBuilder(cfs.metadata(), 0, "key" + i).clustering("c").add("val", "v").build().apply();

        Field capF = CommitLogReplayer.class.getDeclaredField("MAX_OUTSTANDING_REPLAY_COUNT");
        capF.setAccessible(true);
        int countCap = capF.getInt(null);

        long origBytes = CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES;
        CommitLogReplayer.MutationInitiator orig = CommitLogReplayer.mutationInitiator;
        SlowInitiator s = new SlowInitiator();
        CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = BYTES_CAP;
        CommitLogReplayer.mutationInitiator = s;
        try
        {
            CommitLog.instance.resetUnsafe(false);   // stop without deleting segments, restart = replay
        }
        finally
        {
            CommitLogReplayer.mutationInitiator = orig;
            CommitLogReplayer.MAX_OUTSTANDING_REPLAY_BYTES = origBytes;
            s.consumer.shutdownNow();
        }
        System.out.printf("RESULT count_cap=%d bytes_cap=%d consumer_ns=%d N=%d handled=%d peak_queue=%d peak_not_yet_run=%d peak_pending_bytes=%d%n",
                          countCap, BYTES_CAP, CONSUMER_NANOS, N, s.handled.get(), s.peakQueue, s.peakNotYetRun, s.peakPendingBytes);
        Assert.assertTrue("replay did not see the workload", s.handled.get() >= N);
    }
}
```

2. Run each configuration, one JVM per run, and collect the `RESULT` line from the test output
   (`build/test/output/TEST-org.apache.cassandra.db.commitlog.ReplayOutstandingCountTest.xml`, `system-out`, or
   the console):

```bash
cd $SRC
T=org.apache.cassandra.db.commitlog.ReplayOutstandingCountTest
for C in 16 256 4096; do
  ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dcassandra.commitlog_max_outstanding_replay_count=$C" 2>&1 | tee run-C$C.log
  grep -h RESULT build/test/output/TEST-$T.xml run-C$C.log | head -1
done
# control 1: known-binding bytes cap
ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dcassandra.commitlog_max_outstanding_replay_count=4096 -Dreplay.bytes_cap=4096" 2>&1 | tee run-bytes.log
# control 2: no backlog
ant testsome -Dtest.name=$T -Dtest.jvm.args="-Dcassandra.commitlog_max_outstanding_replay_count=4096 -Dreplay.consumer_nanos=0" 2>&1 | tee run-fast.log
grep -h RESULT run-*.log build/test/output/TEST-$T.xml
```

3. Repeat each C run 3 times.
4. Check that no test JVM is left: `pgrep -f ReplayOutstandingCountTest` is empty.

**B2f. Predictions.**

| Run | `peak_queue` | `peak_not_yet_run` | `handled` |
|---|---|---|---|
| C = 16 | exactly 17 | ≤ 17 | ≥ 20000 |
| C = 256 | exactly 257 | ≤ 257 and ≥ 250 | ≥ 20000 |
| C = 4096 | exactly 4097 | ≤ 4097 and ≥ 4000 | ≥ 20000 |
| Control 1: bytes cap 4096 B, C = 4096 | ≈ 4096 / (avg entry size ≈ 40–60 B) + 1 ≈ 70–110, far below 4097 | — | — |
| Control 2: no consumer delay | ≪ 4097 (expected < 100) | — | — |

Control 1 also predicts `peak_pending_bytes` ≤ 4096 + one entry.

Runs repeat exactly: the peak is a deterministic consequence of the `while` condition once the backlog exists.
The claim is wrong if any `peak_queue` > C + 1 with the bytes cap at `Long.MAX_VALUE`, or if `peak_queue` stays
far below C + 1 while the consumer is slow.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `peak_queue` = C + 1 for all three C, and control 1 well below 4097 | Claim confirmed: the count bounds the outstanding entries, and the bytes cap binds when set low (positive control moves). |
| `peak_queue` > C + 1 for some C | Claim wrong: the count does not bound the queue (for example the property is not read, or another path enqueues). |
| `peak_queue` ≪ C + 1 for C = 4096, with `handled` ≥ 20000 and control 2 also small | The consumer is not slower than the reader. Not confirmed; raise `replay.consumer_nanos` to 1000000 and rerun. |
| `handled` < 20000 | The workload did not reach replay (segments not found, or filtered by position). Not confirmed; fix setup. |
| Control 1 `peak_queue` ≈ 4097 | The bytes override was not effective. The positive control failed; not confirmed. |

**B2h. Controls.**
- Control 1 (bytes cap 4 KiB) shows the instrument responds to a cap already shown to bind
  (`RecoveryManagerTest.testRecoverBlocksOnBytesOutstanding`).
- Control 2 (no consumer delay) shows the bound is reached only through backlog, not because of the measurement.
- The value of C is printed from the field itself (`count_cap=`), which rules out a property that was not applied.
- A fresh JVM per run rules out class-init caching across runs.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11, Ant and ≥ 4 GB free RAM and ≥ 2 GB free on a local disk.
- `export SRC=/mydata/$USER-s4/c509-node RUN=/mydata/$USER-s4/replay-count`.
- Copy and build:

```bash
rsync -a <shared cassandra-5.0.9 source>/ $SRC/
cd $SRC
ant clean jar stress-build build-test
```

- Byteman agent:
  `BM=$(find $SRC/build -name 'byteman-4.0.20.jar' | head -1)`. If that is empty:
  `curl -fLo $RUN/byteman-4.0.20.jar https://repo1.maven.org/maven2/org/jboss/byteman/byteman/4.0.20/byteman-4.0.20.jar; BM=$RUN/byteman-4.0.20.jar`.
  The version is from `.build/parent-pom-template.xml:40`.
- Check the anonymous class name:
  `unzip -l $(ls $SRC/build/apache-cassandra-*.jar | grep -v -e sources -e javadoc | head -1) | grep 'CommitLogReplayer\$MutationInitiator\$1.class'`.
- `mkdir -p $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs}`.
- Edit `$SRC/conf/cassandra.yaml`, the copy only:
  - `data_file_directories: [$RUN/data]`, plus `commitlog_directory`, `hints_directory`, `saved_caches_directory`
    and `cdc_raw_directory` under `$RUN`, all written as absolute paths;
  - `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`, `seeds: "127.0.0.1:7000"`;
  - `concurrent_writes: 4`;
  - `commitlog_sync: periodic`, `commitlog_sync_period: 1000ms`;
  - `memtable_heap_space: 2048MiB`, so the load does not flush.
- Before every start, check the ports are free: `ss -ltn | grep -E ':(7000|7199|9042)\b'` must print nothing.
  Otherwise change `storage_port`, `native_transport_port` and `JMX_PORT` in `cassandra-env.sh` consistently.
- Environment for every start:
  `export MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M CASSANDRA_LOG_DIR=$RUN/logs`.

**B3b. Knobs.**
- `-Dcassandra.commitlog_max_outstanding_replay_count` = C ∈ {1024 (default), 16384, 131072}, set in
  `JVM_EXTRA_OPTS` at each start. The values are spaced 16× and 8×; all are below the ~300k mutations in the log.
- The bytes cap is fixed at `-Dcassandra.commitlog_max_outstanding_replay_bytes=1099511627776` (1 TiB) so only
  the count binds.
- Fixed for all runs:
  - `-Dcassandra.replayList=system_auth`. Replay then skips applying `keyspace1` rows (the filter runs inside the
    task, `CommitLogReplayer.java:307`) while every mutation is still read and queued, which removes the memtable
    growth from the heap reading.
  - A Byteman rule that parks each replay task 1 ms, so with `concurrent_writes: 4` the stage applies at most
    ~4000 mutations/s.
- Positive control: C = 131072 with the bytes cap = 4194304 (4 MiB).
- No-backlog control: C = 131072 without Byteman.
- Sanity control: C = 1024 without `replayList`, to confirm the log holds the workload.

**B3c. Workload.**
- `cassandra-stress` writes 300000 rows to `keyspace1.standard1` with one 64-byte column (10-byte key). That is
  ~110–130 serialized bytes per mutation and ≈ 36 MB of commit log (two 32 MiB segments).
- The node is then killed with `kill -9`, so the rows exist only in the commit log, and the data plus commit-log
  directories are archived. Every run restores that archive and restarts the node, which replays ~300k mutations.
- Arithmetic:
  - The reader enqueues faster than 4000/s, so the queue reaches C within C / (read rate − 4000) seconds:
    < 1 s for 1024, and ≈ 10–60 s for 131072 at an assumed read rate of 6000–20000/s.
  - Replay lasts ≈ 300000 / 4000 ≈ 75 s, which leaves a plateau at C for the larger caps.
  - Bytes in flight at C = 131072 are ≈ 131072 × 120 B ≈ 15 MiB serialized, far below the 1 TiB bytes cap.
    Under the default 64 MiB bytes cap the count would still be the binding cap.
- Byteman rule file `$RUN/slow-replay.btm`:

```
RULE slow replay task
CLASS org.apache.cassandra.db.commitlog.CommitLogReplayer$MutationInitiator$1
METHOD runMayThrow
AT ENTRY
IF true
DO java.util.concurrent.locks.LockSupport.parkNanos(1000000L)
ENDRULE
```

**B3d. Observables and instruments.** Sample every 5 s between the `Replaying` and `Log replay complete` lines of
`$RUN/logs/system.log`, against the Cassandra pid in `$RUN/pid`:
- `jmap -histo:live $PID`, which forces a full GC. Keep the instance count and bytes of
  `org.apache.cassandra.db.commitlog.CommitLogReplayer$MutationInitiator$1` (tasks not yet run = outstanding
  entries holding a mutation) and of `org.apache.cassandra.db.Mutation`.
- `jcmd $PID GC.heap_info`, run right after the histogram. Record the G1 "used" figure, which is live heap after
  that full GC.
- `nodetool tpstats | grep MutationStage`. JMX starts before replay (`CassandraDaemon.java:246` before `:345`);
  record Pending.

Not directly observable: the private `futures.size()` (the cluster tier uses the not-yet-run task count, which is
`futures.size()` minus finished-but-unpolled entries, and is ≤ the cap) and the exact heap per entry. That is
computed as Δ live heap / Δ outstanding.

**B3e. Procedure.**
1. Load, done once:

```bash
cd $SRC
bin/cassandra -p $RUN/pid > $RUN/logs/out-load.log 2>&1
until grep -q "Starting listening for CQL clients" $RUN/logs/system.log; do sleep 2; done
tools/bin/cassandra-stress write n=1 no-warmup -rate threads=1 -col n=FIXED\(1\) size=FIXED\(64\) \
    -schema "replication(strategy=SimpleStrategy,factor=1)" -node 127.0.0.1
bin/nodetool flush                      # schema, system.local and the 1-row table go to sstables
tools/bin/cassandra-stress write n=300000 no-warmup -rate threads=32 -col n=FIXED\(1\) size=FIXED\(64\) -node 127.0.0.1
sleep 5                                 # > commitlog_sync_period
bin/nodetool tablestats keyspace1.standard1 | grep -E "SSTable count|Memtable cell count"
#   expect SSTable count: 1 (no flush during load) and memtable cell count ≈ 300000
kill -9 $(cat $RUN/pid); sleep 2; pgrep -f CassandraDaemon || echo stopped
tar -C $RUN -cf $RUN/snap.tar data commitlog hints saved_caches
```

2. Define one run:

```bash
run() {  # $1=label $2=extra JVM opts
  [ -f $RUN/pid ] && kill -9 $(cat $RUN/pid) 2>/dev/null; sleep 1   # only this run's own node, by pid
  rm -rf $RUN/{data,commitlog,hints,saved_caches}; tar -C $RUN -xf $RUN/snap.tar
  : > $RUN/logs/system.log
  JVM_EXTRA_OPTS="$2" bin/cassandra -p $RUN/pid > $RUN/logs/out-$1.log 2>&1
  until grep -q "Replaying" $RUN/logs/system.log; do sleep 1; done
  PID=$(cat $RUN/pid); : > $RUN/samples-$1.txt
  while ! grep -q "Log replay complete" $RUN/logs/system.log; do
    { date +%s; jmap -histo:live $PID | grep -E 'MutationInitiator\$1$| org\.apache\.cassandra\.db\.Mutation$';
      jcmd $PID GC.heap_info | head -3; bin/nodetool tpstats 2>/dev/null | grep MutationStage; } >> $RUN/samples-$1.txt
    sleep 5
  done
  grep "Log replay complete" $RUN/logs/system.log >> $RUN/samples-$1.txt
  kill $PID; sleep 10; kill -9 $PID 2>/dev/null; pgrep -f CassandraDaemon && echo "LEFTOVER"
}
```

3. Runs, each at least twice:

```bash
B="-javaagent:$BM=script:$RUN/slow-replay.btm -Dcassandra.replayList=system_auth -Dcassandra.commitlog_max_outstanding_replay_bytes=1099511627776"
run C1024   "$B -Dcassandra.commitlog_max_outstanding_replay_count=1024"
run C16384  "$B -Dcassandra.commitlog_max_outstanding_replay_count=16384"
run C131072 "$B -Dcassandra.commitlog_max_outstanding_replay_count=131072"
run ctlBytes "-javaagent:$BM=script:$RUN/slow-replay.btm -Dcassandra.replayList=system_auth -Dcassandra.commitlog_max_outstanding_replay_bytes=4194304 -Dcassandra.commitlog_max_outstanding_replay_count=131072"
run ctlFast  "-Dcassandra.replayList=system_auth -Dcassandra.commitlog_max_outstanding_replay_bytes=1099511627776 -Dcassandra.commitlog_max_outstanding_replay_count=131072"
run ctlFull  "-Dcassandra.commitlog_max_outstanding_replay_count=1024"
```

4. For each run, take the plateau as the samples in the middle 50% of the replay window. Report:
   - max and median `MutationInitiator$1` count;
   - median live heap;
   - Δheap / Δcount between C131072 and C1024.
5. Cleanup: `pgrep -f CassandraDaemon` is empty; `rm -rf $RUN $SRC` when stage 4 is done.

**B3f. Predictions.**

| Run | Outstanding entries (`MutationInitiator$1` count) | Live heap |
|---|---|---|
| C1024 | max ≤ 1025; plateau ≥ 900 | Baseline H₁ |
| C16384 | max ≤ 16385; plateau ≥ 14000 | H₁ + (15360 × e), with e ≈ 0.6–2 KB per entry → +9–31 MB |
| C131072 | max ≤ 131073; plateau ≥ 110000 (if the plateau is reached before replay ends) | H₁ + (130048 × e) → +78–260 MB |
| ctlBytes | ≈ 4 MiB / 120 B ≈ 30k–40k, clearly < 131072 | Heap between C16384 and C131072 |
| ctlFast | Far below 131072 (expected < 5000): no backlog without the delay | Near H₁ |
| ctlFull | — | — |

- `Mutation` instance counts track the `MutationInitiator$1` counts within a few hundred.
- Δheap / Δcount gives the same e for C16384 and C131072, within ±30%.
- ctlFull logs "Log replay complete, N replayed mutations" with N ≥ 300000.
- The claim is wrong if any run's count exceeds C + 1 plus a handful (finished-but-unpolled tasks hold no
  `MutationInitiator$1`, so they cannot inflate it), or if C131072's plateau heap is within 10 MB of C1024 while
  its count plateau is ≥ 110000.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Counts plateau at ≈ C, never above C + 1, and heap rises with C at a stable e; ctlBytes below 131072 | Claim confirmed: the count caps in-flight replay mutations and their heap. |
| Count for some run > C + 1 (beyond sampling noise of a few) | Claim wrong: the property does not bound outstanding work. |
| Counts follow C but heap is flat (Δ < 10 MB between C131072 and C1024) | The cap holds but bounds nothing memory-significant for this mutation shape. Report as count-confirmed, heap-negative. |
| C131072 count never exceeds ~ C16384's | The backlog was too short (replay ended before the plateau). Not confirmed; raise n to 600000 or the park to 2 ms and rerun. |
| ctlBytes count ≈ 131072 | The bytes property was not applied, so the positive control failed; recheck `JVM_EXTRA_OPTS` (`ps -o args -p $PID`). |
| ctlFull replays < 300000 | The log did not hold the workload (flushed during load); redo the load with a larger `memtable_heap_space`. |

**B3h. Controls.**
- `replayList` removes the memtable growth, so heap differences come from the queue.
- ctlBytes shows the instrument moves under a cap known to bind.
- ctlFast shows the plateau comes from back-pressure, not from the instrument.
- ctlFull shows the archived log really contains ~300k mutations.
- Every run starts from the same archive, so the content and order of the log are identical.
- `jmap -histo:live` forces a full GC before each heap reading, which removes garbage noise.
- `ps -o args -p $PID` confirms the `-D` values for each run.

**B4. Risks and cleanup.**
- Disk:
  - unit tier ≈ 1–2 GB (build plus test data under `$SRC/build`);
  - cluster tier ≈ 1.5 GB (build) + ~100 MB (archive, data and commit log), all under `/mydata/$USER-s4`.
  - The commit log and sstables never leave `$RUN`. Nothing is written to the shared source or shared storage.
- `jmap -histo:live` pauses the node for a full GC (< 1 s on 4 GB); it is harmless here because there is no client
  traffic.
- Byteman is loaded only into the replay test JVM, and the rule touches only the replay task class.
- Leftovers:
  - after each run, `pgrep -f CassandraDaemon` and `pgrep -f ReplayOutstandingCountTest` must be empty;
  - kill by pid from `$RUN/pid`.
- Ports 7000, 7199 and 9042 are released when the node stops.
- Finally: `rm -rf /mydata/$USER-s4/c509-unit /mydata/$USER-s4/c509-node /mydata/$USER-s4/replay-count`.

## C. Sources read

```
src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (lines 105-130, 785-815)
src/java/org/apache/cassandra/db/commitlog/CommitLogReader.java (lines 60-70, 340-480)
src/java/org/apache/cassandra/db/commitlog/CommitLog.java (lines 180-240, 516-567)
src/java/org/apache/cassandra/concurrent/Stage.java (lines 46, 130)
src/java/org/apache/cassandra/concurrent/SEPExecutor.java (lines 250-275)
src/java/org/apache/cassandra/concurrent/FutureTask.java (grep: run(), call = null)
src/java/org/apache/cassandra/service/CassandraDaemon.java (grep: maybeInitJmx, recoverSegmentsOnDisk)
src/java/org/apache/cassandra/db/Mutation.java (lines 250-275)
src/java/org/apache/cassandra/db/Keyspace.java (grep: apply signatures)
src/java/org/apache/cassandra/utils/FBUtilities.java (grep: waitOnFuture)
test/unit/org/apache/cassandra/db/RecoveryManagerTest.java (lines 60-200, 390-440)
test/unit/org/apache/cassandra/db/RowUpdateBuilder.java (grep: constructors)
test/unit/org/apache/cassandra/SchemaLoader.java (grep: standardCFMD)
test/conf/cassandra.yaml (grep: commitlog settings)
conf/cassandra.yaml (grep: concurrent_writes, commitlog, memtable, materialized views)
conf/cassandra-env.sh (grep: MAX_HEAP_SIZE, JVM_EXTRA_OPTS)
conf/jvm11-server.options (grep: GC)
build.xml (grep: test.jvm.args, testsome, stress-build, build-test)
.build/cassandra-deps-template.xml, .build/parent-pom-template.xml (grep: byteman)
CHANGES.txt (grep: outstanding replay), NEWS.txt (lines 1285-1298)
https://issues.apache.org/jira/browse/CASSANDRA-7533 (cited from CHANGES.txt, not fetched)
https://issues.apache.org/jira/browse/CASSANDRA-8639 (cited from CHANGES.txt, not fetched)
```

## D. Stage-4 feedback

`none yet`
