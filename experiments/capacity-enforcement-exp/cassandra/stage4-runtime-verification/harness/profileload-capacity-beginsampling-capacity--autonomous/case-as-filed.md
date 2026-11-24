# profileload sampler capacity (`-s` / `capacity`) — verification solution  <!-- file: cases/profileload-capacity-beginsampling-capacity--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place: the field `MaxSampler.capacity` is assigned), **linked**: [`MaxSampler.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L48) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive` — the sampler capacity bounds the number of `Sampler.Sample` objects (and the partition-key / CQL-string objects they reference) that a `MaxSampler` keeps on the heap: the queue is built with `maximumSize(max(1, capacity))` two lines above the given line, and Guava evicts on every add once full, so retained samples per sampler per table never exceed `max(1, capacity)`. Without the cap the queue would grow by one entry per sampled operation for the whole sampling window. |
| Ground | — |

> **Note on the given line.** Line 48 stores `capacity` in the field that `permitsValue` reads
> ([`MaxSampler.java:74`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L74)),
> an admission pre-filter. The hard bound on the container is set by the same argument at
> [`MaxSampler.java:46`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L46).
> Both come from the one constraint traced below; the solution tests the bound, and the unit tier
> includes a control that separates the two roles.

## A. Constraint trace

**A1. The constraint.**
- **Name:** sampler capacity — nodetool `profileload` / `toppartitions` option `-s` ("Capacity of the sampler, higher for more accuracy (Default: 256)"); the `capacity` argument of the JMX operations `ColumnFamilyStoreMBean.beginLocalSampling`, `StorageServiceMBean.samplePartitions` and `StorageServiceMBean.startSamplingPartitions`; and of `Sampler.beginSampling(int capacity, long durationMillis)`.
- **Kind:** runtime parameter supplied per sampling session (an operator-command / JMX-operation argument), not a yaml entry or `-D` property.
- **First declared:** as the user-facing option and default in [`ProfileLoad.java:53`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/nodetool/ProfileLoad.java#L53) (`private int capacity = 256;`, `@Option(name = "-s")` at `ProfileLoad.java:52`). `TopPartitions` is an empty subclass of `ProfileLoad` (`tools/nodetool/TopPartitions.java:25-27`), so it shares the option. Server-side the parameter enters at `ColumnFamilyStoreMBean.java:302` / `StorageServiceMBean.java:931,933,946` and the abstract `Sampler.beginSampling` (`metrics/Sampler.java:148-157`, javadoc: "Number of sample items to keep in memory ... understand the memory trade offs").
- **Unit:** number of sample entries (count of `Sampler.Sample` objects per sampler per table), not bytes.
- **Default and derivation:** 256, a literal in `ProfileLoad.java:53`. No server-side default: a JMX caller must pass a value.
- **Validation:** nodetool (client side) requires `topCount < capacity` and `capacity <= 1024` (`ProfileLoad.java:76-79`). Server side, only the scheduled path checks `0 < capacity <= 1024` and `count < capacity` (`service/StorageService.java:6577-6583`). The blocking paths `StorageService.samplePartitions` (`StorageService.java:6533-6542`) and `ColumnFamilyStore.beginLocalSampling` (`db/ColumnFamilyStore.java:2055-2059`) accept any `int`, including values far above 1024 or `<= 0`.
- **How set:** `nodetool profileload [ks table duration] -s N [-a SAMPLERS] [-k K] [-i interval]`, or a direct JMX invocation of the operations above. Takes effect at the next `beginSampling`; no restart. It is per call, not persisted.

**A2. What it caps.** Heap. For the five `MaxSampler` instances of each table (`metrics/TableMetrics.java:433-477`: `WRITE_SIZE`, `LOCAL_READ_TIME`, `READ_ROW_COUNT`, `READ_TOMBSTONE_COUNT`, `READ_SSTABLE_COUNT`), the quantity compared against the limit is `queue.size()`, the number of `Sample<T>` entries held in a Guava `MinMaxPriorityQueue`. Each entry retains a `Sample` (value, count, error; `Sampler.java:171-189`) and its `value`: the partition-key `ByteBuffer` (`ColumnFamilyStore.java:1482`, `ReadCommand.java:612,615`, `SinglePartitionReadCommand.java:917,1056`) or, for `LOCAL_READ_TIME`, the `String` from `command.toCQLString()` (`db/ReadExecutionController.java:236-243`).

**A3. Mechanism.**
1. nodetool parses `-s` (`ProfileLoad.java:52-53`) and checks it (`ProfileLoad.java:76-79`). With keyspace and table it calls `NodeProbe.getPartitionSample(ks, cf, capacity, ...)`, which invokes `ColumnFamilyStoreMBean.beginLocalSampling(sampler, capacity, durationMillis)` per sampler (`tools/NodeProbe.java:572-578`). Without a table it calls `StorageService.samplePartitions` (`NodeProbe.java:567-570` → `StorageService.java:6533-6542`). With `-i` it goes through `startSamplingPartitions` → `SamplingManager.register` → `cfs.beginLocalSampling` every interval (`StorageService.java:6569-6591`, `metrics/SamplingManager.java:107-121,194-216`).
2. `ColumnFamilyStore.beginLocalSampling` calls `metric.samplers.get(SamplerType.valueOf(sampler)).beginSampling(capacity, durationMillis)` (`ColumnFamilyStore.java:2056-2059`).
3. `MaxSampler.beginSampling` (`MaxSampler.java:40-49`) throws if a sampling session is still active (`:42-43`), sets the end time (`:44`), builds a new queue with `maximumSize(Math.max(1, capacity))` (**the bound**, [`MaxSampler.java:45-47`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L45-L47)) and then, at **the given line** [`MaxSampler.java:48`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L48), stores `capacity` in the field.
4. Producers call `Sampler.addSample(item, value)`, which submits `insert(item, value)` to the single-thread `samplerExecutor` (`Sampler.java:109-113`; the executor's queue holds at most 1000 tasks, extra tasks are dropped and counted as dropped `_SAMPLE` messages, `Sampler.java:100-105`).
5. `MaxSampler.insert` (`MaxSampler.java:66-70`) adds a new `Sample` only if the sampler is active and `permitsValue(value)` holds; `permitsValue` ([`MaxSampler.java:72-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/MaxSampler.java#L72-L75)) admits when `value > 0` and (queue empty, or `queue.size() < capacity` — the field set at line 48 —, or the smallest held count is below `value`).
6. When the queue is full and an admitted sample is added, Guava's `MinMaxPriorityQueue` with a maximum size removes its greatest element by the comparator; the comparator is `reverseOrder(comparing(count))` (`MaxSampler.java:37`), so the entry with the **smallest** count is evicted. Net: `queue.size() <= max(1, capacity)` after every `insert`.
- **Outcomes at the limit:** below the limit every positive sample is kept; at the limit a sample is either rejected by `permitsValue` (no allocation of a new queue entry; the `Sample` object is not even created) or added and the current minimum evicted. Memory stays at `max(1, capacity)` entries.
- **Edge values:** `capacity <= 0` → `maximumSize(1)` while the field is `<= 0`, so `queue.size() < capacity` is always false; the queue still holds exactly 1 entry. A JMX caller can pass e.g. `Integer.MAX_VALUE`, making the bound ineffective; the 1024 maximum is enforced only in nodetool and the scheduled path.
- **Bypass / overshoot:** (a) transiently `size+1` inside one `add` before Guava evicts (within the `synchronized insert`); (b) up to 1000 pending `insert` tasks in `samplerExecutor`, each holding an item reference, outside the queue and the cap (shared by all samplers in the JVM); (c) retention in time is not capped: `finishSampling` (`MaxSampler.java:52-63`) polls at most `count + 2` entries (the loop polls one more than it returns) and leaves the rest of the queue referenced by the sampler until the next `beginSampling` replaces it; a session whose duration expired without `finishSampling` also keeps its queue; (d) the cap is per sampler per table: profiling all tables (`profileload` without keyspace) multiplies it by (number of tables × enabled MaxSampler types).
- Guava's builder does not pre-size the heap array to `maximumSize` (default initial capacity 11, grown on demand), so a large capacity costs nothing until samples arrive.

**A4. Other consumers.**
- `FrequencySampler` (`READS`, `WRITES`, `CAS_CONTENTIONS`) receives the same `capacity` and passes it to stream-lib `StreamSummary(capacity)` (`metrics/FrequencySampler.java:55-61`); that bound is a separate mechanism, not this line.
- The `samplerExecutor` task queue (≤ 1000 tasks, A3 bypass b).
- The `CompositeData` result lists built at `finishLocalSampling` (`ColumnFamilyStore.java:2061-2077`) — bounded by `count`, short-lived.
- The workload itself: memtables (`memtable_allocation_type: heap_buffers`, `conf/cassandra.yaml:825`), key/row caches, client request buffers. These dominate heap and are outside this constraint; the cluster tier isolates the sampler's share by measuring it before and after releasing the queue.

**A5. Evidence beyond the source.**
- `CHANGES.txt:1763` "Add sampler for query time and expose with nodetool (CASSANDRA-14436)" (introduced `MaxSampler` / `profileload`): https://issues.apache.org/jira/browse/CASSANDRA-14436
- `CHANGES.txt:529` "Add row, tombstone, and sstable count to nodetool profileload (CASSANDRA-18022)": https://issues.apache.org/jira/browse/CASSANDRA-18022
- Existing tests `test/unit/org/apache/cassandra/metrics/MaxSamplerTest.java:55-80` (top-`capacity` retained) and `SamplerTest.java:229-241` (`waitForEmpty`).
- Guava 32.0.1 `MinMaxPriorityQueue.Builder.maximumSize`: "Configures this builder to build MinMaxPriorityQueue instances that are limited to maximumSize elements. Each time a queue grows beyond this bound, it immediately removes its greatest element (according to its comparator)" — https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/collect/MinMaxPriorityQueue.Builder.html (Guava version from `.build/parent-pom-template.xml:307-309`).

## B. Verification solution

**B1. Claim under test.** For a `MaxSampler` started with capacity `C`, the number of retained `Sampler.Sample` entries (and hence their heap) is at most `max(1, C)` however many samples arrive; the heap retained by the sampler grows with the number of sampled operations only until it reaches `max(1, C)` entries, and is roughly `min(max(1,C), N_sampled) × s` bytes for a per-entry size `s`.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11 (`java -version` → 11.x), Ant ≥ 1.10. Local working copy (never the shared tree):
```
export WORK=/mydata/<you>-s4/o123          # any local disk with >= 10 GB free
mkdir -p $WORK && rsync -a ~/cassandra-5.0.9/ $WORK/cassandra-5.0.9/
cd $WORK/cassandra-5.0.9 && ant jar build-test
```
Test source: `$WORK/cassandra-5.0.9/test/unit/org/apache/cassandra/metrics/MaxSamplerCapacityProbeTest.java` (same package, so the protected `insert` and package-private `queue` access via reflection work). `ant testsome` runs it with the jamm agent (`build.xml:510,1159`), which `ObjectSizes.measureDeep` uses. Default test JVM options from `build.xml`.

**B2b. Knobs.** `capacity` ∈ {−5, 0, 1, 10, 256, 1024, 10000, 100000}: −5/0 the edge (`max(1, C)`), 256 the nodetool default, 1024 the nodetool / scheduled-path maximum, 10000 a JMX-only value above 1024 that still binds, 100000 non-binding (> N; positive control). Set via `sampler.beginSampling(C, 3_600_000L)`. Second factor: value order ∈ {ASC (each new sample larger, so every sample is admitted by `permitsValue` — worst case for eviction), RANDOM (seed 42)}.

**B2c. Workload.** N = 50,000 direct `insert("k" + i, value)` calls per run (bypasses `samplerExecutor`, so no load shedding). ASC: `value = i + 1`; RANDOM: `value = 1 + rnd.nextInt(1_000_000)`. N exceeds every capacity except 100000, so the limit is reached (and passed by 49,999 … 0 samples) in all binding arms.

```java
package org.apache.cassandra.metrics;

import java.lang.reflect.Field;
import java.util.Random;
import com.google.common.collect.MinMaxPriorityQueue;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.utils.ObjectSizes;

public class MaxSamplerCapacityProbeTest
{
    static final int N = 50_000;
    static final int[] CAPS = { -5, 0, 1, 10, 256, 1024, 10_000, 100_000 };

    @BeforeClass
    public static void init() { DatabaseDescriptor.daemonInitialization(); }

    static MaxSampler<String> newSampler()
    {
        return new MaxSampler<String>() { public String toString(String v) { return v; } };
    }

    static MinMaxPriorityQueue<?> queue(MaxSampler<?> s) throws Exception
    {
        Field f = MaxSampler.class.getDeclaredField("queue"); f.setAccessible(true);
        return (MinMaxPriorityQueue<?>) f.get(s);
    }

    static void setField(MaxSampler<?> s, int v) throws Exception
    {
        Field f = MaxSampler.class.getDeclaredField("capacity"); f.setAccessible(true); f.setInt(s, v);
    }

    static void run(MaxSampler<String> s, boolean asc, int n)
    {
        Random r = new Random(42);
        for (int i = 0; i < n; i++)
            s.insert("k" + i, asc ? i + 1 : 1 + r.nextInt(1_000_000));
    }

    @Test
    public void probe() throws Exception
    {
        for (boolean asc : new boolean[]{ true, false })
            for (int cap : CAPS)
            {
                MaxSampler<String> s = newSampler();
                s.beginSampling(cap, 3_600_000L);
                run(s, asc, N);
                MinMaxPriorityQueue<?> q = queue(s);
                long bytes = ObjectSizes.measureDeep(q);
                int expected = Math.min(Math.max(1, cap), N);
                System.out.printf("RESULT order=%s cap=%d N=%d size=%d expected=%d bytes=%d bytesPerEntry=%.1f%n",
                                  asc ? "ASC" : "RND", cap, N, q.size(), expected, bytes, (double) bytes / q.size());
                Assert.assertEquals(expected, q.size());
            }
    }

    // Control: which line bounds the container. Field (line 48) forced huge after begin(10): bound must still be 10.
    @Test
    public void fieldVersusMaximumSize() throws Exception
    {
        MaxSampler<String> s = newSampler();
        s.beginSampling(10, 3_600_000L);
        setField(s, Integer.MAX_VALUE);
        run(s, false, N);
        System.out.printf("RESULT control=fieldHuge cap=10 size=%d%n", queue(s).size());
        Assert.assertEquals(10, queue(s).size());
    }

    // Baseline: no beginSampling -> inactive, nothing retained.
    @Test
    public void inactiveBaseline() throws Exception
    {
        MaxSampler<String> s = newSampler();
        run(s, true, N);
        System.out.printf("RESULT control=inactive queue=%s%n", queue(s));
        Assert.assertNull(queue(s));
    }
}
```

**B2d. Observables and instruments.** Per run: `q.size()` (the check's operand, read by reflection after the last insert), `ObjectSizes.measureDeep(q)` (deep heap bytes of the queue, its array, `Sample`s and their `String` values, via jamm), bytes per entry. Output: `RESULT` lines in `build/test/output/TEST-org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest.xml` (system-out) and the junit pass/fail. Not observable here: the real node's heap, executor load shedding.

**B2e. Procedure.**
1. B2a copy and build.
2. Write the class above to `$WORK/cassandra-5.0.9/test/unit/org/apache/cassandra/metrics/MaxSamplerCapacityProbeTest.java`.
3. `cd $WORK/cassandra-5.0.9 && ant testsome -Dtest.name=org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest`
4. `grep -o 'RESULT[^<]*' build/test/output/TEST-org.apache.cassandra.metrics.MaxSamplerCapacityProbeTest.xml`
5. `pgrep -f MaxSamplerCapacityProbeTest` → nothing (the forked JUnit JVM has exited).

**B2f. Predictions.**

| cap | expected `size` (ASC and RND) | `bytes` |
|---|---|---|
| −5, 0, 1 | 1 | < 1 KB |
| 10 | 10 | ~1–2 KB |
| 256 | 256 | ≈ 256 × s + fixed, s ≈ 70–110 B → ~18–30 KB |
| 1024 | 1024 | ~70–115 KB |
| 10000 | 10000 | ~0.7–1.1 MB |
| 100000 (non-binding) | 50000 (= N) | ~3.5–5.5 MB |

`bytesPerEntry` roughly constant (±20%) across binding arms with ≥ 256 entries; `bytes` scales linearly with `size`, not with N. Control `fieldHuge`: size 10. Baseline: queue `null`. The claim is wrong if any arm shows `size > max(1, cap)`, or `bytes` for cap 1024 is near the cap-100000 arm's.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `size == min(max(1,cap), N)` for every arm and both orders; bytes ∝ size | Claim confirmed at unit level: capacity caps retained entries. |
| any binding arm with `size > max(1,cap)` | Claim wrong: the cap does not bound the container. |
| cap 100000 arm `size == N` and bytes several MB (positive control moved) | Workload really drives usage when the cap does not bind; binding arms' flat size is due to the cap. |
| cap 100000 arm `size < N` | Workload/admission broken (e.g. sampler inactive, values ≤ 0); result not confirmed. |
| `fieldHuge` size 10 | The bound comes from `maximumSize` (line 46), the line-48 field only filters admission. |
| `fieldHuge` size > 10 | The field, not `maximumSize`, bounds the queue — amend A3. |
| cap −5/0 arm size 0 | Edge behaviour differs from A3 (`max(1,…)`); amend A3. |

**B2h. Controls.** Non-binding arm (positive control); inactive-sampler baseline (no retention without `beginSampling`); two value orders (rules out the cap holding only because later samples happened to be rejected); direct `insert` (rules out executor load shedding hiding growth); field-override control separating line 46 from line 48.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, the B2a copy (already `ant jar`). Data, commit log, hints and caches go to `$CASSANDRA_HOME/data` (default `cassandra_storagedir` from `bin/cassandra.in.sh`), which is inside `$WORK` on local disk; logs to `$WORK/cassandra-5.0.9/logs`. Stock `conf/cassandra.yaml` (single node, `127.0.0.1`, `memtable_allocation_type: heap_buffers`). JMX local, no auth (default `LOCAL_JMX=yes`, port 7199, `conf/cassandra-env.sh:228-244`). Start:
```
cd $WORK/cassandra-5.0.9
MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M bin/cassandra -p $WORK/cassandra.pid > $WORK/start.log 2>&1
until bin/nodetool status 2>/dev/null | grep -q '^UN'; do sleep 2; done
PID=$(cat $WORK/cassandra.pid)
```
JMX helper (JDK only, single-file launch; nodetool cannot pass `-s > 1024`):
```java
// $WORK/SamplerCtl.java
import javax.management.*; import javax.management.remote.*; import java.util.List;
public class SamplerCtl {
  public static void main(String[] a) throws Exception {
    try (JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"))) {
      MBeanServerConnection m = c.getMBeanServerConnection();
      ObjectName on = new ObjectName("org.apache.cassandra.db:type=Tables,keyspace=" + a[1] + ",table=" + a[2]);
      if (a[0].equals("begin"))
        m.invoke(on, "beginLocalSampling", new Object[]{ a[3], Integer.parseInt(a[4]), Integer.parseInt(a[5]) },
                 new String[]{ "java.lang.String", "int", "int" });
      else
        System.out.println("returned=" + ((List<?>) m.invoke(on, "finishLocalSampling", new Object[]{ a[3], Integer.parseInt(a[4]) },
                 new String[]{ "java.lang.String", "int" })).size());
    }
  }
}
```
Run as `java $WORK/SamplerCtl.java begin keyspace1 standard1 WRITE_SIZE <C> <durMs>` / `... finish keyspace1 standard1 WRITE_SIZE 10`.

**B3b. Knobs.** `capacity` C ∈ {256, 1024, 100000, 2000000}, sampler `WRITE_SIZE` only (a `MaxSampler`; one `Sample` per write, `ColumnFamilyStore.java:1481-1482`), duration 900000 ms (outlasts the workload). 256/1024 are nodetool's default/max; 100000 binds below N but is reachable only via JMX; 2000000 > N is the non-binding positive control. One extra check: `bin/nodetool profileload keyspace1 standard1 1000 -s 2000 -a WRITE_SIZE` must be rejected ("Capacity (-s) cannot exceed 1024.").

**B3c. Workload.** `cassandra-stress` writes, N = 1,000,000 distinct partitions per arm:
```
tools/bin/cassandra-stress write n=1000000 no-warmup cl=ONE -pop seq=1..1000000 -rate threads=32 -node 127.0.0.1 -log file=$WORK/stress-<C>.log
```
Every write's `update.dataSize() > 0`, so each write offers one sample; N = 1,000,000 > 100000, 1024, 256 (limit reached and passed by ≥ 900,000) and < 2,000,000 (control never binds). Duration ≈ 20–120 s at 10–50 k writes/s, inside the 900 s window. Schema is created once by a warm-up `write n=1000` before the first arm.

**B3d. Observables and instruments.**
- **Primary:** `jmap -histo:live $PID | grep 'org.apache.cassandra.metrics.Sampler\$Sample'` → instance count and bytes of `Sample` objects (forces a full GC, so only reachable ones count).
- **Actual heap:** `jcmd $PID GC.heap_info` right after each `jmap -histo:live` (used heap after full GC), taken before (M1) and after (M2) releasing the queue; the release delta M1−M2 is the heap the sampler held, with memtables unchanged (no writes in between; flush done before M1).
- Dropped samples: `bin/nodetool tpstats` "Dropped" section, row `_SAMPLE`, before and after each arm (executor load shedding, `Sampler.java:103-104`).
- Not directly observable: per-sampler share when several samplers/tables are active (avoided by enabling one sampler on one table); exact per-entry layout (inferred from histo bytes).

**B3e. Procedure.**
1. B3a: start node, `PID=...`; `tools/bin/cassandra-stress write n=1000 no-warmup -node 127.0.0.1` (creates `keyspace1.standard1`).
2. Baseline: `jmap -histo:live $PID | grep 'Sampler\$Sample'` (expect none); `bin/nodetool profileload keyspace1 standard1 1000 -s 2000 -a WRITE_SIZE` (expect rejection).
3. For each C in 256, 1024, 100000, 2000000:
   1. `D0=$(bin/nodetool tpstats | awk '$1=="_SAMPLE"{print $2}')`
   2. `java $WORK/SamplerCtl.java begin keyspace1 standard1 WRITE_SIZE $C 900000`
   3. Run the B3c stress command; then `sleep 10` (drain `samplerExecutor`).
   4. `D1=...` as in 3.1; `S = 1000000 − (D1 − D0)` samples offered to `insert`.
   5. `bin/nodetool flush keyspace1 standard1`
   6. M1: `jmap -histo:live $PID | grep 'Sampler\$Sample' ; jcmd $PID GC.heap_info`
   7. `java $WORK/SamplerCtl.java finish keyspace1 standard1 WRITE_SIZE 10` then `java $WORK/SamplerCtl.java begin keyspace1 standard1 WRITE_SIZE 1 1` (replaces and releases the queue), `sleep 2`.
   8. M2: same as 3.6. Record count1, bytes1, used1, count2, used2.
   9. `bin/nodetool truncate keyspace1 standard1` (keeps disk small; arms independent).
4. Stop: `kill $(cat $WORK/cassandra.pid)`; wait until `pgrep -f CassandraDaemon` is empty; `pgrep -f cassandra-stress` empty.

**B3f. Predictions.** Let s = per-entry retained heap (Sample ≈ 32 B + key `HeapByteBuffer` ≈ 48 B + 10-byte key array ≈ 32 B + array slot 4–8 B; expect 80–150 B).

| C | Sample count at M1 | Sample bytes (histo) | release delta used1−used2 |
|---|---|---|---|
| 256 | 256 | ~8 KB | below resolution (< 1 MB) |
| 1024 | 1024 | ~33 KB | below resolution (< 1 MB) |
| 100000 | 100000 | ~3.2 MB | ≈ 8–15 MB |
| 2000000 (control) | ≈ S (≈ 1,000,000 minus dropped `_SAMPLE`) | ~32 MB | ≈ 80–150 MB |

At M2 the count is ≤ 1 in every arm. Relation to test: count1 = min(C, S) exactly for the binding arms; the release delta for C = 100000 is ≈ (100000 / S) × that of the control. Claim wrong if a binding arm shows count1 > C, or its release delta is of the same order as the control's.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| count1 = C for C ∈ {256, 1024, 100000}; control count1 ≈ S; release deltas ∝ count1 | Confirmed: capacity caps the sampler's heap on a real node. |
| any binding arm count1 > C | Claim wrong. |
| control count1 ≈ S and release delta tens of MB (positive control moved) while binding arms stay at C | Usage follows workload only until the cap; the cap governs. |
| control count1 ≪ S, or `_SAMPLE` drops ≈ N | Workload did not reach the sampler (wrong table/sampler, inactive, or load shedding); not confirmed — lower `-rate threads` and repeat. |
| count2 > 1 | Queue not released by the replacing `beginSampling` (amend A3 retention note). |
| nodetool accepts `-s 2000` | Client-side 1024 check absent; amend A1. |

**B3h. Controls.** Baseline histo before any sampling (no `Sample` instances); non-binding control arm with the same workload; one sampler on one table (no cross-talk); flush before M1 and no writes between M1 and M2 (memtable heap constant, so the release delta isolates the sampler); `_SAMPLE` drop counts to account for samples that never reached `insert`; truncation between arms.

**B4. Risks and cleanup.** Unit tier: forked JVM exits with ant; the added test file lives only in `$WORK`. Cluster tier: disk ≤ ~2 GB per arm before truncation (1 M × ~200 B rows plus commit log) on local `$WORK`; no shared storage used. `jmap -histo:live` pauses the node (full GC) — acceptable on a dedicated test node. Kill the node with the pid file, check `pgrep -f CassandraDaemon` and `pgrep -f cassandra-stress` are empty, and `ss -ltnp | grep -E ':(7199|9042|7000)'` shows nothing. Finally `rm -rf $WORK` (or keep logs only).

## C. Sources read

- src/java/org/apache/cassandra/metrics/MaxSampler.java
- src/java/org/apache/cassandra/metrics/Sampler.java
- src/java/org/apache/cassandra/metrics/FrequencySampler.java
- src/java/org/apache/cassandra/metrics/SamplingManager.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java (lines 259-269, 420-485)
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (lines 553-584, 1470-1485, 2030-2080)
- src/java/org/apache/cassandra/db/ColumnFamilyStoreMBean.java (lines 296-306)
- src/java/org/apache/cassandra/db/ReadExecutionController.java (lines 225-243)
- src/java/org/apache/cassandra/db/ReadCommand.java (lines 600-620)
- src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (grep: lines 916-917, 1055-1056)
- src/java/org/apache/cassandra/service/StorageService.java (lines 6520-6600)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (lines 925-947)
- src/java/org/apache/cassandra/service/StorageProxy.java, service/paxos/Paxos.java (grep only)
- src/java/org/apache/cassandra/tools/nodetool/ProfileLoad.java
- src/java/org/apache/cassandra/tools/nodetool/TopPartitions.java
- src/java/org/apache/cassandra/tools/NodeProbe.java (lines 548-585)
- src/java/org/apache/cassandra/transport/CBUtil.java (lines 443-481)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (lines 27-45, 225-255)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (grep `cassandra.storagedir`)
- test/unit/org/apache/cassandra/metrics/MaxSamplerTest.java
- test/unit/org/apache/cassandra/metrics/SamplerTest.java
- conf/cassandra.yaml (grep), conf/cassandra-env.sh (lines 228-253)
- build.xml (grep test/jamm), .build/parent-pom-template.xml (Guava version)
- CHANGES.txt (grep)
- https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/collect/MinMaxPriorityQueue.Builder.html
- https://issues.apache.org/jira/browse/CASSANDRA-14436
- https://issues.apache.org/jira/browse/CASSANDRA-18022

## D. Stage-4 feedback

none yet
