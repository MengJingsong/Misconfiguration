# writeQueue capacity (SSTableSimpleUnsortedWriter hand-off queue) — verification solution  <!-- file: cases/writequeue_capacity-put-writequeue--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (the `offer` check in `put`), **linked**: [`SSTableSimpleUnsortedWriter.java:170`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L170) — `if (writeQueue.offer(buffer, 1, TimeUnit.SECONDS))` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. The queue that hands full buffers from the producer to the single `DiskWriter` thread has capacity 0 (a `SynchronousQueue`), so the check at :170 only succeeds when the disk writer is idle. As a result, one `CQLSSTableWriter` (unsorted) holds at most two full row buffers on heap: one being written and one waiting to be handed off. The size of each buffer is set by the separate `maxSSTableSizeInMiB` limit. The memory bound is therefore about 2 x buffer size x (heap/serialized ratio) per writer instance. It does not depend on how many rows the caller pushes. |
| Ground | — |

> Naming: constraint `writequeue_capacity` (the hard-coded capacity of `writeQueue`), function
> `put`, operand `writequeue` (the queue whose `offer` is checked).

## A. Constraint trace

**A1. The constraint.**
- **Name:** capacity of `SSTableSimpleUnsortedWriter.writeQueue`, the queue that carries full `Buffer`s
  (`TreeMap<DecoratedKey, PartitionUpdate.Builder>`, `SSTableSimpleUnsortedWriter.java:204`) from the
  producer thread to the `DiskWriter` thread.
- **Kind:** a hard-coded constant (a constructor argument). It is not configuration.
- **Declared at:** [`SSTableSimpleUnsortedWriter.java:68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L68),
  `private final BlockingQueue<Buffer> writeQueue = newBlockingQueue(0);`. The value 0 is turned into a
  queue type at [`BlockingQueues.java:45`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java#L45):
  `capacity == 0 ? new SynchronousQueue<>() : new LinkedBlockingQueue<>(capacity)`. So the queue is a
  `SynchronousQueue`, a pure hand-off with no storage slot.
- **Unit:** buffers (a count). Capacity 0 means no buffer can wait in the queue. At most one buffer is
  in the `DiskWriter` and one in the producer's `put`.
- **Default and derivation:** literally `0`, with no derivation.
- **How it can be set:** it cannot be set: there is no yaml key, `-D` property, JMX attribute or builder
  method. Changing it means editing line 68 and recompiling. (The test simulator can intercept
  `newBlockingQueue` through `@Intercept`, `BlockingQueues.java:42`, but that is not a user-facing knob.)
- **Companion limit (it sets the size of each buffer this constraint counts):** `maxSSTableSizeInMiB`, a
  `CQLSSTableWriter.Builder` option (`withMaxSSTableSizeInMiB(int)` at `CQLSSTableWriter.java:537`, and
  the deprecated `withBufferSizeInMiB`/`withBufferSizeInMB` at :564/:584). It defaults to
  `DEFAULT_BUFFER_SIZE_IN_MIB_FOR_UNSORTED = 128` (`CQLSSTableWriter.java:395`, applied at :679). It is
  converted to bytes at `SSTableSimpleUnsortedWriter.java:74` and is set per writer instance when the
  writer is built.

**A2. What it caps.**
- **Resource:** JVM **heap** of the process that uses `CQLSSTableWriter` in unsorted mode (a bulk-load
  client, or `compaction-stress write` through `StressCQLSSTableWriter`, `tools/stress/.../StressCQLSSTableWriter.java:590`).
  No running Cassandra node constructs this class. In `src/`, the only construction site is
  `CQLSSTableWriter.java:740`.
- **Quantity compared:** the check does not compare numbers. `SynchronousQueue.offer(e, 1s)` succeeds
  only if a consumer (the `DiskWriter` blocked in `take()`, :216) receives the buffer within 1 s. The
  compared quantity is therefore "buffers already in flight vs. hand-off capacity". In effect, the
  producer may hand over a new buffer only when the previous one has been fully written.
- **Resulting bound:** at most **2 full buffers** live per writer instance: one owned by `DiskWriter`
  (between :216 and the end of :220–226) and one held by the producer while blocked in `put`. Each buffer
  is just over `maxSSTableSizeInMiB` of *serialized* row size (see A3). The heap cost per buffer is that
  size times a heap/serialized factor `k`, which is not measured in the source.

**A3. Mechanism.**
1. `CQLSSTableWriter.rawAddRow` (`CQLSSTableWriter.java:265`) calls `writer.getUpdateFor(key)` for each
   partition key (:297/:306).
2. `getUpdateFor` (`SSTableSimpleUnsortedWriter.java:81-94`): for a key that is new in the current
   buffer, it adds the serialized size of an empty partition update to `currentSize` (:89). It then
   inserts a new `PartitionUpdate.Builder` into `buffer` (:90-91).
3. Each row added to that builder goes through the anonymous `add` override (:126-131): `super.add(row)`,
   then `countRow` (adds `UnfilteredSerializer.serializedSize`, :103), then `maybeSync` (:106).
4. `maybeSync`: `if (currentSize > maxSStableSizeInBytes) sync();` (:110). This is the buffer-size check
   that decides *when* a buffer is full.
5. `sync` (:153-161): it returns if the buffer is empty. Otherwise it calls `put(buffer)`. Only after
   `put` returns does it do `buffer = new Buffer(); currentSize = 0;` (:159-160).
6. `put` (:163-178) runs an infinite loop: `checkForWriterException()` (:167), then
   **[the check, :170](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java#L170)**
   `if (writeQueue.offer(buffer, 1, TimeUnit.SECONDS)) break;`.
   - **true:** the `DiskWriter` was waiting in `take()` and now owns the buffer. The producer returns
     to `sync`, starts a fresh buffer and continues accepting rows.
   - **false (1 s timeout):** the `DiskWriter` is still writing the previous buffer. The loop repeats,
     so the producer thread (the caller of `addRow`) **blocks** holding its full buffer and cannot
     add rows. It wakes every second only to check for a disk-writer failure.
   - **InterruptedException:** rethrown as `UncheckedInterruptedException` (:175).
   - **Disk writer failed:** `checkForWriterException` (:180-193) throws. `maybeSync` wraps the
     `IOException` in `SyncException` (:116-118), and `rawAddRow` unwraps and rethrows it
     (`CQLSSTableWriter.java:311-316`).
7. `DiskWriter.run` (:210-236): `take()` (:216). On `SENTINEL` (:217) it exits. Otherwise it writes every
   partition of the buffer through an `SSTableTxnWriter` (:220-223), finishes it (:224) and calls the
   produced-listener (:225). The buffer `b` stays reachable until that iteration ends. Any `Throwable`
   is stored (first one only, :232) and the loop continues.
8. `close()` (:136-151): `sync()`, then `put(SENTINEL)`, then `join` the disk writer.

**Bypasses and overshoot.**
- **Per-buffer overshoot:** the size check (:110) runs *after* a row has been added. A buffer therefore
  exceeds `maxSSTableSizeInMiB` by up to one row plus one partition header. A single huge row makes one
  buffer arbitrarily large (`CQLSSTableWriterTest.testSyncWithinPartition`, test file :220-246, relies
  on rows > 1 MiB).
- **Serialized vs. heap:** `currentSize` counts serialized size, not heap. The authors say so
  themselves (:96-102). The heap per buffer is `k` times larger (object headers, `ByteBuffer` wrappers,
  `BTreeRow`, `DecoratedKey`, `TreeMap` entries).
- **Transient copies during write:** while `DiskWriter` writes a buffer, `entry.getValue().build()`
  (:223) creates a `PartitionUpdate` per partition. This is transient and limited to one partition at
  a time.
- **Per instance, not per process:** each `CQLSSTableWriter` has its own queue and `DiskWriter`. The
  class Javadoc allows many instances in parallel (`CQLSSTableWriter.java:123-125`), and
  `compaction-stress write -t N` creates N of them (`CompactionStress.java:315-320`). Process heap is
  therefore up to about N x 2 buffers.
- **Sorted mode:** `sorted()` uses `SSTableSimpleWriter` (`CQLSSTableWriter.java:739`), which does not
  use this queue (no buffering).
- **No escape from a stuck writer:** if the `DiskWriter` hangs without throwing, the producer blocks
  forever. The 1 s timeout only polls for exceptions; it never drops or overflows.
- **Stale local reference:** while `DiskWriter` waits in `take()`, an interpreted frame may still
  reference the previous `b`. At that moment the producer is only filling one buffer, so the maximum
  stays 2.

**A4. Other consumers.**
Same JVM heap, outside this constraint:
- the schema/keyspace metadata the client creates;
- `SSTableTxnWriter` component builders (bloom filter, index, compression buffers);
- SAI index building when `withIndexes` is used (`CQLSSTableWriter.java:744-749`);
- `SSTableReader`s the listener keeps when `openSSTableOnProduced()` is used;
- the caller's own data, and the stress generator in `compaction-stress`.

Disk: every buffer becomes an sstable on disk. Total disk use equals the data written, and this
constraint does not cap disk.

**A5. Evidence beyond the source.**
- `CHANGES.txt:6329`: "Use separate writer thread in SSTableSimpleUnsortedWriter (CASSANDRA-3619)",
  the origin of the hand-off design.
- `CHANGES.txt:4402`: CASSANDRA-7360 (sync within partitions, i.e. the overshoot fix).
- `CHANGES.txt:4072-4073`: CASSANDRA-8807 (close terminates if the disk writer crashed; matches the
  `checkForWriterException` polling in `put`).
- `CHANGES.txt:386` (CASSANDRA-18941), `:210` (CASSANDRA-19800, listener), `:842` and NEWS.txt:573
  (CASSANDRA-17675).
- Builder Javadoc `CQLSSTableWriter.java:549-558`: "The default is 128MiB, which should be reasonable
  for a 1GiB heap. If you experience OOM while using the writer, you should lower this value."
- JDK 11 `SynchronousQueue` Javadoc
  (https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/SynchronousQueue.html):
  `offer(e, timeout, unit)` waits up to the timeout "for another thread to receive it". The queue has
  no capacity. Cited from prior knowledge; not fetched in this session.
- Existing tests: `test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java` (buffer-size
  tests with `withBufferSizeInMB(1)`). None of them measures buffers in flight.

## B. Verification solution

**B1. Claim under test.**
For one unsorted `CQLSSTableWriter`, the producer blocks at `SSTableSimpleUnsortedWriter.java:170`
whenever the disk writer is still busy. As a result, at most 2 row buffers (each just over
`maxSSTableSizeInMiB` serialized) are live on heap at any time. The writer's retained heap therefore
scales with `maxSSTableSizeInMiB` and stays flat no matter how many rows are offered or how slow the
disk writer is. With the capacity changed to unbounded, retained heap instead grows with the rows
offered.

### B2. Unit tier

**B2a. Environment and build.**
- One Linux node, JDK 11 (`java -version` shows 11), Ant 1.10, at least 20 GiB free on local disk.
- `WORK=/local/s3-wq` is any directory on **local** disk. Never use the shared source tree or NFS.

```bash
export WORK=/local/s3-wq; mkdir -p $WORK/runs $WORK/probe $WORK/probe-classes
rsync -a ~/cassandra-5.0.9/ $WORK/c509/                       # stock copy
rsync -a ~/cassandra-5.0.9/ $WORK/c509-unbounded/             # ablation copy
sed -i 's/newBlockingQueue(0);/newBlockingQueue();/' \
    $WORK/c509-unbounded/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java
grep -n 'newBlockingQueue' $WORK/c509-unbounded/src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java
#   expect exactly: 68:    private final BlockingQueue<Buffer> writeQueue = newBlockingQueue();
(cd $WORK/c509 && ant -Dno-checkstyle=true jar)
(cd $WORK/c509-unbounded && ant -Dno-checkstyle=true jar)
```

Classpaths and JVM options:

```bash
cp_of() { echo "$1/build/classes/main:$1/build/lib/jars/*:$1/lib/*"; }
JOPTS="$(grep -h '^-' $WORK/c509/conf/jvm-clients.options $WORK/c509/conf/jvm11-clients.options | tr '\n' ' ')"
```

The probe program is `$WORK/probe/QueueProbe.java` (outside the tree; the source is given below). It
is compiled once against the stock copy and run against either copy. The only changed class is
`SSTableSimpleUnsortedWriter`, so the probe is binary-compatible with both.

```java
import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.nio.ByteBuffer;
import java.util.Random;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.config.CassandraRelevantProperties;
import org.apache.cassandra.config.Config;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.db.Keyspace;
import org.apache.cassandra.io.sstable.CQLSSTableWriter;
import org.apache.cassandra.io.util.File;

/** args: sizeMiB  stall|free  totalRows  outDir  [holdSeconds=30] */
public class QueueProbe
{
    static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static boolean inPut(Thread t)
    {
        Thread.State s = t.getState();
        if (s != Thread.State.TIMED_WAITING && s != Thread.State.WAITING) return false;
        for (StackTraceElement e : t.getStackTrace())
            if (e.getClassName().equals("org.apache.cassandra.io.sstable.SSTableSimpleUnsortedWriter")
                && e.getMethodName().equals("put"))
                return true;
        return false;
    }

    public static void main(String[] args) throws Exception
    {
        final int sizeMiB = Integer.parseInt(args[0]);
        final boolean stall = args[1].equals("stall");
        final long totalRows = Long.parseLong(args[2]);
        final String outDir = args[3];
        final int hold = args.length > 4 ? Integer.parseInt(args[4]) : 30;
        System.out.println("PID=" + ProcessHandle.current().pid());

        File dir = new File(outDir);
        dir.tryCreateDirectories();
        DatabaseDescriptor.clientInitialization(true, () -> {
            Config c = new Config(); c.data_file_directories = new String[]{ outDir }; return c; });
        CassandraRelevantProperties.FORCE_LOAD_LOCAL_KEYSPACES.setBoolean(true);
        Keyspace.setInitialized();

        CountDownLatch gate = new CountDownLatch(stall ? 1 : 0);
        AtomicInteger produced = new AtomicInteger();
        CQLSSTableWriter w = CQLSSTableWriter.builder()
            .inDirectory(dir)
            .forTable("CREATE TABLE probe_ks.t (k int PRIMARY KEY, v blob)")
            .using("INSERT INTO probe_ks.t (k, v) VALUES (?, ?)")
            .withMaxSSTableSizeInMiB(sizeMiB)
            .withSSTableProducedListener(s -> {           // runs on the DiskWriter thread (:225)
                produced.incrementAndGet();
                try { gate.await(); } catch (InterruptedException e) { throw new RuntimeException(e); }
            })
            .build();

        Field wf = CQLSSTableWriter.class.getDeclaredField("writer"); wf.setAccessible(true);
        Object inner = wf.get(w);
        Field cs = inner.getClass().getDeclaredField("currentSize"); cs.setAccessible(true);
        Field mx = inner.getClass().getDeclaredField("maxSStableSizeInBytes"); mx.setAccessible(true);
        System.out.println("WRITER=" + inner.getClass().getName() + " maxBytes=" + mx.getLong(inner));

        final long base = usedAfterGc();
        System.out.printf("BASE heapMiB=%.1f%n", base / 1048576.0);
        AtomicLong accepted = new AtomicLong();
        Thread producer = new Thread(() -> {
            Random r = new Random(42);
            byte[] b = new byte[1024];
            try
            {
                for (int i = 0; i < totalRows; i++)
                {
                    r.nextBytes(b);
                    w.addRow(i, ByteBuffer.wrap(b.clone()));
                    accepted.incrementAndGet();
                }
            }
            catch (Exception e) { throw new RuntimeException(e); }
        }, "probe-producer");
        long t0 = System.nanoTime();
        producer.start();

        if (stall)
        {
            int hits = 0;
            while (hits < 3 && producer.isAlive() && System.nanoTime() - t0 < 300_000_000_000L)
            {
                Thread.sleep(100);
                hits = inPut(producer) ? hits + 1 : 0;
            }
            System.out.println("STATE " + (hits >= 3 ? "blocked-in-put" : producer.isAlive() ? "timeout" : "producer-finished"));
            for (int t = 0; t <= hold; t += 5)
            {
                long h = usedAfterGc();
                System.out.printf("HOLD t=%ds accepted=%d currentSize=%d produced=%d inPut=%b heapDeltaMiB=%.1f%n",
                                  t, accepted.get(), cs.getLong(inner), produced.get(), inPut(producer), (h - base) / 1048576.0);
                Thread.sleep(5000);
            }
            gate.countDown();
        }
        else
        {
            while (producer.isAlive())
            {
                long h = ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
                System.out.printf("FREE t=%.1fs accepted=%d currentSize=%d produced=%d inPut=%b heapUsedMiB=%.1f%n",
                                  (System.nanoTime() - t0) / 1e9, accepted.get(), cs.getLong(inner), produced.get(), inPut(producer), h / 1048576.0);
                Thread.sleep(1000);
            }
        }
        producer.join();
        w.close();
        System.out.printf("RESULT accepted=%d produced=%d%n", accepted.get(), produced.get());
        System.exit(0);
    }
}
```

```bash
javac -cp "$(cp_of $WORK/c509)" -d $WORK/probe-classes $WORK/probe/QueueProbe.java
```

JVM options for every run:
`-Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc:file=$RUN/gc.log $JOPTS -Dcassandra.logdir=$RUN -Dlogback.configurationFile=$WORK/c509/conf/logback-tools.xml`.

**B2b. Knobs.**
- **Varied:** `maxSSTableSizeInMiB` S in {4, 16, 64}, passed as the probe's first argument (set through
  `withMaxSSTableSizeInMiB`). These three values cover a 16x range, so linear scaling is visible, and
  even S=64 with two buffers stays well under a 2 GiB heap.
- **Mode:** `stall` makes the listener block the `DiskWriter` after its first sstable, so the
  hand-off can only succeed if the queue had room. `free` gives a normal run.
- **Queue capacity:** stock copy (0, under test) vs. `c509-unbounded` (unbounded `LinkedBlockingQueue`,
  ablation). Capacity is not a runtime knob; it is selected by the build.

**B2c. Workload.**
- Single-row partitions `(k int, v blob)` with `v` = 1024 random bytes (incompressible, a fresh array
  per row). Keys `0..totalRows-1` are hashed by Murmur3, so the input is unsorted relative to token
  order.
- `totalRows = 8 x S x 1024` (S=4: 32,768; S=16: 131,072; S=64: 524,288), about 8 x S MiB of raw
  values.
- Serialized size per row (A3 steps 2-3) = 1024 value bytes + row/cell framing + one partition header.
  The design assumes it lies in [1040, 1300] bytes.
- A buffer is full after about `S x 2^20 / per-row` rows, i.e. S x 806–1008 rows. Two buffers, the
  in-flight bound, take S x 1613–2016 rows. That is 1/5 to 1/4 of the offered rows, so in `stall` mode
  the limit is reached and the producer is left with at least 6 x S MiB still to add.

**B2d. Observables and instruments.**
1. **The check's outcome:** whether the producer thread is parked in `SSTableSimpleUnsortedWriter.put`
   (the probe's `inPut`, from `Thread.getStackTrace`). The probe samples it every 100 ms until it is
   seen 3 times in a row, then every 5 s in `HOLD` lines.
2. **Buffers in flight:** live instances of `org.apache.cassandra.io.sstable.SSTableSimpleUnsortedWriter$Buffer`,
   counted with `jmap -histo:live <PID>` (this forces a full GC). The count includes the static
   `SENTINEL`, so "2 in flight" reads as **3**.
3. **Rows accepted** before the block (`accepted`), and `currentSize` read by reflection (the
   size-check operand, :62) at the block.
4. **Retained heap:** heap used after 3 x `System.gc()` minus the baseline taken after `build()` and
   before any row (`heapDeltaMiB`).
5. **Sstables produced:** the listener count, and the number of `*-Data.db` files after `close()`.

Not directly observable: the per-buffer heap/serialized factor `k`. It is derived as
`heapDeltaMiB / (2 x S)` in `stall` mode. The number of failed `offer` calls is also not observable;
the parked state stands in for it.

**B2e. Procedure.**
For each `(copy, S, mode)` in this list:
- `(c509, 4|16|64, stall)`
- `(c509, 4|16|64, free)`
- `(c509-unbounded, 16, stall)`
- `(c509-unbounded, 16, free)`

```bash
COPY=$WORK/c509; S=16; MODE=stall; ROWS=$((8*S*1024))
RUN=$WORK/runs/$(basename $COPY)-S$S-$MODE; rm -rf $RUN; mkdir -p $RUN
timeout 900 java -Xms2g -Xmx2g -XX:+UseG1GC -Xlog:gc:file=$RUN/gc.log $JOPTS \
  -Dcassandra.logdir=$RUN -Dlogback.configurationFile=$WORK/c509/conf/logback-tools.xml \
  -cp "$WORK/probe-classes:$(cp_of $COPY)" QueueProbe $S $MODE $ROWS $RUN/data 30 > $RUN/out.txt 2>&1 &
JPID=$!
# stall: one histogram mid-hold
if [ $MODE = stall ]; then
  until grep -q '^HOLD t=5s' $RUN/out.txt || ! kill -0 $JPID 2>/dev/null; do sleep 1; done
  jmap -histo:live $JPID | grep 'SSTableSimpleUnsortedWriter\$Buffer' > $RUN/histo.txt
else
  # free: histogram every 2 s for the whole run
  while kill -0 $JPID 2>/dev/null; do
    jmap -histo:live $JPID 2>/dev/null | grep 'SSTableSimpleUnsortedWriter\$Buffer' >> $RUN/histo.txt; sleep 2; done
fi
wait $JPID; echo "exit=$?" >> $RUN/out.txt
find $RUN/data -name '*-Data.db' | wc -l > $RUN/datadb-count.txt
du -sm $RUN/data >> $RUN/datadb-count.txt
rm -rf $RUN/data                                     # keep logs only
pgrep -f QueueProbe && echo "LEFTOVER" || echo "clean"
```

Record from each run:
- from `out.txt`: `STATE`, every `HOLD`/`FREE` line, and `RESULT`;
- the `#instances` column of `histo.txt` (max over samples in `free` mode);
- `datadb-count.txt`.

**B2f. Predictions (stated before any run).**

| Run | Producer state | `accepted` at block | `currentSize` at block | live `Buffer` (incl. SENTINEL) | `heapDeltaMiB` | Data.db after close |
|---|---|---|---|---|---|---|
| stock, S=4, stall | `blocked-in-put`, `inPut=true` in every HOLD line | 6,452–8,066, identical in all HOLD lines | in (4,194,304, 4,195,604] | 3 | ≈ 2·4·k; flat ±5 % over the 30 s hold | 9–11 |
| stock, S=16, stall | same | 25,808–32,264, constant | in (16,777,216, 16,778,516] | 3 | ≈ 2·16·k; flat | 9–11 |
| stock, S=64, stall | same | 103,232–129,056, constant | in (67,108,864, 67,110,164] | 3 | ≈ 2·64·k; flat | 9–11 |
| stock, S ∈ {4,16,64}, free | not persistently in put; `accepted` reaches 8·S·1024 | — | resets toward 0 after each sync | ≤ 3 in every sample | peak heap-after-GC ≤ baseline + 2·S·k (+10 %) | 9–11 |
| unbounded, S=16, stall | **never** blocks: `STATE producer-finished`, `accepted` = 131,072 | — | — | 10–12 | ≈ k·(130–163) MiB, i.e. ≥ 4× the stock S=16 stall value | 9–11 |
| unbounded, S=16, free | not blocked | — | — | ≤ 3 most of the time (more only if producer outruns writer) | similar to stock free | 9–11 |

Relations that must hold:
- `heapDeltaMiB(S=64)/heapDeltaMiB(S=16)` lies in [3.2, 4.8], and `(S=16)/(S=4)` lies in [3.2, 4.8]
  (linear in S, ±20 %).
- `k = heapDeltaMiB/(2S)` is roughly the same for all S and lies in [1.2, 3.0].
- `produced` = 1 throughout every stall hold.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Stock stall: producer parked in `put`, `accepted` constant over the hold, live `Buffer` = 3, `heapDeltaMiB` flat and ∝ S | Claim confirmed: the capacity-0 hand-off at :170 stops intake at two buffers. |
| Stock stall: `accepted` keeps rising or reaches `totalRows` while `produced` = 1 | Claim **wrong**: rows are accepted while the disk writer is busy, so the hand-off does not bound intake. |
| Stock: live `Buffer` > 3 in any sample | Claim **wrong**: more than two buffers are in flight. |
| Stock stall: `heapDeltaMiB` grows during the hold, or does not scale with S (ratio outside [3.2, 4.8]) | Claim wrong or incomplete: something other than the two buffers holds the heap (look at A4 items). |
| Stock stall: `STATE timeout` (never blocked) and `accepted` small | Limit never reached, so not confirmed; check that the listener really blocks (thread dump of the `DiskWriter`). |
| Unbounded stall: producer finishes, `Buffer` 10–12, heap ≥ 4× stock | Positive control passed: the same workload moves heap when the hand-off is removed, so capacity 0 is what binds. |
| Unbounded stall behaves like stock (blocks at about 2 buffers) | The ablation did not take effect (check the grep in B2a), or something else bounds intake; result not conclusive. |
| `currentSize` at block ≤ S·2^20 | Mis-trace of the size check (:110); revisit A3. |

**B2h. Controls.**
- **Free vs. stall:** the producer blocks only when the `DiskWriter` is held. This shows that the
  hand-off, not CPU or GC, stops intake.
- **Unbounded ablation:** the same probe, data, seed and heap with only line 68 changed. It is the
  positive control that the instruments see growth when the cap is gone.
- **S sweep:** retained heap tracks S, so the heap reading measures the buffers and not fixed overhead.
- **Measurement noise:** the baseline is taken after `build()` (schema and keyspace already created).
  `-Xms = -Xmx` keeps the heap size stable, 3 explicit full GCs are run before every heap reading,
  and values are random and cloned per row, so nothing is shared or interned.
- `produced` = 1 during the hold confirms the `DiskWriter` is parked inside the listener, holding
  buffer B1.

### B3. Cluster tier

**n/a (as a cluster):** no running Cassandra node constructs `SSTableSimpleUnsortedWriter`. The only
users are the offline client `CQLSSTableWriter` (`CQLSSTableWriter.java:740`) and the stress tool's
`StressCQLSSTableWriter` (`tools/stress/.../StressCQLSSTableWriter.java:590`). A node's heap or disk
cannot be governed by this constraint, and pushing a cluster's configuration changes nothing here.

**Alternative that answers the same question at the "real resource" level:** a whole-process tier. It
runs a shipped tool that goes through this exact class, `tools/bin/compaction-stress write` (which uses
`StressCQLSSTableWriter` → `SSTableSimpleUnsortedWriter`). It measures the tool JVM's actual live heap
while it writes gigabytes of sstables to local disk, with and without a slowed disk writer. The
subsections below describe this alternative.

**B3a. Environment and build.**
- Same node and copies as B2a, plus the stress tool and test jars (for Byteman):

```bash
(cd $WORK/c509 && ant -Dno-checkstyle=true stress-build build-test)
(cd $WORK/c509-unbounded && ant -Dno-checkstyle=true stress-build)
BYTEMAN=$(ls $WORK/c509/build/test/lib/jars/byteman-[0-9]*.jar | head -1); echo $BYTEMAN
```

If no Byteman jar is present, download `org.jboss.byteman:byteman:4.0.20` from Maven Central into
`$WORK/lib/`.

- Stress profile `$WORK/s3probe.yaml`:

```yaml
keyspace: s3probe
keyspace_definition: |
  CREATE KEYSPACE s3probe WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};
table: t
table_definition: |
  CREATE TABLE t (k bigint PRIMARY KEY, v blob) WITH compression = {'enabled': false};
columnspec:
  - name: v
    size: fixed(1024)
insert:
  partitions: fixed(1)
  batchtype: UNLOGGED
  select: fixed(1)/1
queries:
  simple1:
    cql: select * from t where k = ?
    fields: samerow
```

- Byteman rule `$WORK/slow-diskwriter.btm`. It only delays the disk writer, with no code change:

```
RULE slow DiskWriter before finish
CLASS org.apache.cassandra.io.sstable.SSTableSimpleUnsortedWriter$DiskWriter
METHOD run
AT INVOKE org.apache.cassandra.io.sstable.SSTableTxnWriter.finish
IF true
DO java.lang.Thread.sleep(3000L)
ENDRULE
```

- JVM: `JVM_OPTS="-Xms4g -Xmx4g -XX:+UseG1GC -Xlog:gc:file=$RUN/gc.log"`. Add
  `-javaagent:$BYTEMAN=script:$WORK/slow-diskwriter.btm` for throttled runs. `tools/bin/cassandra.in.sh`
  appends `conf/jvm-clients.options` to `JVM_OPTS` (:120-130).
- `CASSANDRA_HOME` = the local copy, so the commit log and other storage dirs are created under
  `$CASSANDRA_HOME/data` (`-Dcassandra.storagedir`, `tools/bin/compaction-stress`), which is on local
  disk.

**B3b. Knobs.**
- `-b` (`--buffer-size-mb`, i.e. `maxSSTableSizeInMiB`, `CompactionStress.java:296`) S in {16, 64, 128}.
  128 is the shipped default.
- `-t 1`: one writer, so the bound is a single 2-buffer pair. A variant with `-t 2` checks the
  per-instance multiplication.
- Throttle: none, or the Byteman 3 s delay per sstable.
- Build: stock, or unbounded (ablation, throttled only).

**B3c. Workload.**
- `compaction-stress write -d $RUN/data -p $WORK/s3probe.yaml -g G -t T -b S -c 4000000`.
- Each operation inserts one partition with a 1 KiB blob; `-c 4000000` keeps keys distinct within a
  run.
- Unthrottled: `G=2` (about 2 GiB on disk, i.e. 2048/S buffers: 128 for S=16, 16 for S=128). That
  passes the 2-buffer bound many times over. Expected duration 1–5 min.
- Throttled: `G=1`, S=64. That is 16 sstables x at least 3 s each, so the writer drains at most
  64 MiB / 3 s, about 21 MiB/s. The stress generator is expected to produce faster than that, so the
  hand-off binds. The jstack fraction in B3d verifies this. Duration is about 1–3 min.
- Ablation (unbounded build, throttled, S=64, `G=1`) uses the same arithmetic. The backlog grows by
  (producer rate − about 21 MiB/s) x elapsed time.

**B3d. Observables and instruments.**
- `PID=$(pgrep -n -f org.apache.cassandra.stress.CompactionStress)`.
- Every 10 s, `jcmd $PID GC.class_histogram`:
  - `$Buffer` `#instances` (bound: ≤ 2·T + 1);
  - the `Total` bytes line = live heap after a full GC, the actual resource.
- Every 1 s, `jstack $PID | grep -c 'SSTableSimpleUnsortedWriter.put'` = writer threads blocked at the
  hand-off. The fraction of samples > 0 shows whether the check binds.
- `/proc/$PID/status` `VmRSS` every 10 s (informational).
- The GC log, for an independent peak heap-after-GC.
- `ls -l $RUN/data/*/*/*-Data.db` sizes at the end, giving the per-buffer on-disk size (≈ S).

Not directly observable: which buffer a given byte belongs to. The per-buffer heap size is inferred
from Total-bytes differences across S.

**B3e. Procedure.**

```bash
cd $WORK/c509          # or $WORK/c509-unbounded for the ablation
export CASSANDRA_HOME=$PWD
S=64; T=1; G=2; TAG=stock-S$S-T$T-free         # set per run
RUN=$WORK/runs/b3-$TAG; rm -rf $RUN; mkdir -p $RUN/data
export JVM_OPTS="-Xms4g -Xmx4g -XX:+UseG1GC -Xlog:gc:file=$RUN/gc.log"
# throttled runs only: export JVM_OPTS="$JVM_OPTS -javaagent:$BYTEMAN=script:$WORK/slow-diskwriter.btm"
timeout 1800 tools/bin/compaction-stress write -d $RUN/data -p $WORK/s3probe.yaml \
    -g $G -t $T -b $S -c 4000000 > $RUN/out.txt 2>&1 &
sleep 5; PID=$(pgrep -n -f org.apache.cassandra.stress.CompactionStress); echo $PID > $RUN/pid
( while kill -0 $PID 2>/dev/null; do
    date +%s >> $RUN/histo.txt
    jcmd $PID GC.class_histogram 2>/dev/null | grep -E 'SSTableSimpleUnsortedWriter\$Buffer|^Total' >> $RUN/histo.txt
    grep VmRSS /proc/$PID/status >> $RUN/rss.txt 2>/dev/null
    sleep 10; done ) &
( while kill -0 $PID 2>/dev/null; do
    jstack $PID 2>/dev/null | grep -c 'SSTableSimpleUnsortedWriter.put' >> $RUN/inPut.txt; sleep 1; done ) &
wait
ls -l $RUN/data/*/*/*-Data.db | awk '{print $5}' > $RUN/datadb-sizes.txt
rm -rf $RUN/data $CASSANDRA_HOME/data
pgrep -f CompactionStress && echo LEFTOVER || echo clean
```

Run matrix, in order:

| # | Build | S | T | G | Throttle |
|---|---|---|---|---|---|
| 1 | stock | 16 | 1 | 2 | none |
| 2 | stock | 64 | 1 | 2 | none |
| 3 | stock | 128 | 1 | 2 | none |
| 4 | stock | 64 | 2 | 2 | none |
| 5 | stock | 64 | 1 | 1 | Byteman |
| 6 | unbounded | 64 | 1 | 1 | Byteman |

**B3f. Predictions (stated before any run).**
Let `P(run)` be the maximum histogram `Total` over the run, and `P0` the first sample taken before the
first sstable completes (≈ fixed overhead).
- Runs 1–3:
  - `$Buffer` instances ≤ 3 in every sample.
  - `P` is flat after the first 2 samples (±10 %) for the whole run, not growing with GB written.
  - `P(128) − P(16)` lies in 2·k·112 MiB ≈ 270–670 MiB (k in [1.2, 3.0]), and `P(64) − P(16)` in
    ≈ 115–290 MiB.
  - Data.db files ≈ S MiB each (±10 %, uncompressed), except the last.
- Run 4 (T=2): `$Buffer` ≤ 5; `P(4) − P0(4)` ≈ 2 x (`P(2) − P0(2)`) (±25 %).
- Run 5 (throttled):
  - `inPut.txt` > 0 in at least 50 % of samples (the hand-off binds).
  - `$Buffer` ≤ 3.
  - `P(5)` within 15 % of `P(2)`: a slower disk does not raise heap.
- Run 6 (ablation, throttled):
  - `inPut.txt` = 0 throughout.
  - `$Buffer` count increases over time well beyond 3.
  - `Total` grows roughly linearly with time. It ends at ≥ 2 x `P(5)`, or the JVM fails with
    `OutOfMemoryError` before writing 1 GiB.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Runs 1–3 and 5: `$Buffer` ≤ 3, `P` flat over time, `P` ∝ S; run 5 blocked in `put` most of the time with `P(5)` ≈ `P(2)` | Claim confirmed in the real tool: heap follows the buffer size × 2, not the data volume or disk speed. |
| `$Buffer` > 2·T+1, or `P` grows with GB written in a stock run | Claim **wrong**. |
| Run 5 shows `inPut` ≈ 0 | Limit not reached (the producer was slower than the throttled writer). Raise the Byteman delay to 10 s and rerun; not confirmed until it binds. |
| `P` does not change with S | The buffers are not the dominant heap user (A4 items dominate). The claim about the cap's effect on real heap is unsupported. |
| Run 6: heap and `$Buffer` grow, `inPut` = 0 | Positive control passed: the same workload with the cap removed lets heap follow the backlog. |
| Run 6 looks like run 5 | Ablation not effective, or another bound exists; not conclusive. |
| Run 4 not ≈ 2× | The per-instance multiplication (A3 bypass) is mis-traced; note it. |

**B3h. Controls.**
- **Run 6 vs. run 5:** the same tool, profile, size and throttle, differing only in line 68.
- **Runs 1–3:** the S sweep separates buffer heap from fixed overhead.
- **Run 4:** checks the per-instance scaling.
- **Run 5 vs. run 2:** isolates disk speed.
- The full-GC-based histogram avoids counting garbage. The GC log gives an independent cross-check.
- Compression is off, so on-disk size tracks serialized size and the Data.db sizes validate the
  buffer accounting.

**B4. Risks and cleanup.**
- **Disk:**
  - The unit tier writes at most about 11 x 64 MiB ≈ 0.7 GiB per run.
  - The process tier writes ≤ 2 GiB per run plus a commit log under `$CASSANDRA_HOME/data`.
  - All of it goes under `$WORK` on local disk, and data dirs are deleted after each run.
  - The `-g` stop condition is checked every 3 s (`CompactionStress.java:338-347`), so expect up to a
    few hundred MiB of overshoot.
- **Shared storage:** nothing is built or written in `~/cassandra-5.0.9` or under `/proj`. Builds
  happen only in `$WORK/c509*`.
- **Hangs:**
  - A stall-mode probe that dies before `gate.countDown()` leaves the JVM waiting forever. `timeout 900`
    bounds it.
  - The ablation can OOM. `timeout 1800` and `-Xmx4g` bound the process-tier runs.
- **Processes:** after every run, check `pgrep -f QueueProbe` and `pgrep -f CompactionStress`, and
  `kill` any PID left. The background samplers end when the target PID exits. Also check no `jcmd` or
  `jmap` is left (`pgrep -f 'jmap|jcmd'`).
- **Final cleanup:** `rm -rf $WORK/runs/*/data $WORK/c509/data $WORK/c509-unbounded/data`. Keep
  `out.txt`, `histo.txt`, `inPut.txt`, `gc.log` and `datadb-*` for stage 4. When stage 4 is done,
  remove `$WORK`.

## C. Sources read

- src/java/org/apache/cassandra/io/sstable/SSTableSimpleUnsortedWriter.java
- src/java/org/apache/cassandra/utils/concurrent/BlockingQueues.java
- src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
- src/java/org/apache/cassandra/io/sstable/AbstractSSTableSimpleWriter.java (lines 90-125)
- src/java/org/apache/cassandra/io/sstable/SSTableTxnWriter.java (lines 100-115)
- src/java/org/apache/cassandra/io/sstable/SSTableSimpleWriter.java (grep: class comment)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 319-368, clientInitialization)
- src/java/org/apache/cassandra/db/rows/EncodingStats.java (grep: NO_STATS, TIMESTAMP_EPOCH)
- tools/stress/src/org/apache/cassandra/io/sstable/StressCQLSSTableWriter.java (grep)
- tools/stress/src/org/apache/cassandra/stress/CompactionStress.java
- tools/stress/src/org/apache/cassandra/stress/operations/userdefined/SchemaInsert.java (lines 145-200)
- tools/bin/compaction-stress, tools/bin/cassandra.in.sh
- tools/cqlstress-example.yaml
- conf/jvm-clients.options, conf/jvm11-clients.options, conf/ (listing)
- test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterTest.java (setup, testSyncWithinPartition)
- test/unit/org/apache/cassandra/io/sstable/CQLSSTableWriterClientTest.java
- build.xml (testsome, build/jar targets, version), .build/build-resolver.xml, .build/build-checkstyle.xml (grep)
- CHANGES.txt, NEWS.txt (grep for the writer and the CASSANDRA tickets cited)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/SynchronousQueue.html (cited from prior knowledge, not fetched)

## D. Stage-4 feedback

none yet
