# cassandra.parent_repair_status_cache_size — verification solution  <!-- file: cases/parent_repair_status_cache_size-ActiveRepairService-repairStatusByCmd--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (capacity-set place: the `repairStatusByCmd` cache is built with a maximum size), **linked**: [`ActiveRepairService.java:242`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L242) (the builder chain runs to the `.maximumSize(...)` call at [`:247`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L247)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive` (count cap, not a byte cap). The JVM property sets Guava `maximumSize` on the per-repair-command status cache, so the cache never holds more than N entries. The heap it retains therefore stays at or below about N × (size of one entry). The entry size is not bounded: it depends on the message strings, which can include the full range list. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `cassandra.parent_repair_status_cache_size`. Kind: JVM system property, held as the enum constant `PARENT_REPAIR_STATUS_CACHE_SIZE` and declared at
[`CassandraRelevantProperties.java:392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L392)
as `PARENT_REPAIR_STATUS_CACHE_SIZE("cassandra.parent_repair_status_cache_size", "100000")`.
- Unit: number of cache entries. There is one entry per repair command number (`cmd`).
- Default: the literal string `"100000"`, parsed by `getLong()` (`CassandraRelevantProperties.java:806-812`; the value comes from `System.getProperty`, falling back to the default string).
- How to set it: only with `-Dcassandra.parent_repair_status_cache_size=<n>` on the JVM command line (for example in `JVM_EXTRA_OPTS` or `conf/jvm-server.options`). There is no yaml key and no JMX setter.
- When it is read: once, in the `ActiveRepairService` constructor (`ActiveRepairService.java:247`). That constructor runs once per JVM through the lazy `Holder` singleton (`ActiveRepairService.java:174-182`). A change therefore needs a restart.
- Invalid values: a negative value makes Guava's `maximumSize` throw `IllegalArgumentException`, which would fail `ActiveRepairService` construction. `0` is legal and means "store nothing".
- Companion property: entries also expire after `cassandra.parent_repair_status_expiry_seconds` (default 1 day, `CassandraRelevantProperties.java:393`, used at `ActiveRepairService.java:243`).

**A2. What it caps.**
- Resource: JVM heap.
- Quantity compared against the limit: the number of entries in `ActiveRepairService.repairStatusByCmd`, a `Cache<Integer, Pair<ParentRepairStatus, List<String>>>` (`ActiveRepairService.java:226`).
- What one entry holds: the `Integer` cmd key, a `Pair`, an `ImmutableList` of message `String`s, and Guava's per-entry node (an access/write entry plus a value reference).
- The comment at `:244-246` explains the design: entries are assumed to be "not much more than 100 bytes", so the authors chose a count bound rather than a weigher.

**A3. Mechanism.**
1. The cache is built at [`ActiveRepairService.java:242-248`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L242-L248): `CacheBuilder.newBuilder().expireAfterWrite(PARENT_REPAIR_STATUS_EXPIRY_SECONDS.getLong(), SECONDS).maximumSize(PARENT_REPAIR_STATUS_CACHE_SIZE.getLong()).build()`.
2. The only writer is `recordRepairStatus(cmd, status, messages)` → `repairStatusByCmd.put(...)` (`ActiveRepairService.java:525-528`). It is called from `RepairCoordinator`:
   - `IN_PROGRESS` with an empty list at the start of every coordinated repair (`RepairCoordinator.java:293`);
   - `COMPLETED` with `[msg]` from `success()`, including skips (`RepairCoordinator.java:208-209`, `197-202`);
   - `FAILED` with `[reason, "Repair command #N finished with error"]` from `fail()` (`RepairCoordinator.java:236-237`).
   
   The same `cmd` key is overwritten, so each repair command leaves one entry.
3. Commands reach this code through `StorageService.repair(...)`. That method returns cmd `0` and records nothing when there are no ranges or the keyspace RF is below 2 (`StorageService.java:4797-4798`). Otherwise it takes `cmd = nextRepairCommand.incrementAndGet()` and submits a `RepairCoordinator` (`StorageService.java:4800-4801`, `4848-4869`).
4. Readers: `getRepairStatus` → `getIfPresent` (`ActiveRepairService.java:532-535`), exposed over JMX as `StorageServiceMBean.getParentRepairStatus(int)` (`StorageService.java:4969-4974`). `nodetool repair` (`RepairRunner.queryForCompletedRepair`, `tools/RepairRunner.java:148-175`) uses it when JMX notifications are lost.
5. Enforcement is done by Guava 32.0.1-jre (`.build/parent-pom-template.xml:307-309`), not by Cassandra:
   - On each `put`, the owning segment evicts least-recently-accessed entries until its weight is at or below its share of `maximumSize`. This happens synchronously under the segment lock.
   - With the default `concurrencyLevel` of 4, the cap is split across up to 4 segments, and the shares add up to exactly N. Each segment can therefore start evicting before the total reaches N.
   - Once every segment is full (after many more than N distinct keys), the total equals N.
   - There is no overshoot across operations.
   - Outcome when the limit is reached: an older status is silently dropped, and `getParentRepairStatus(oldCmd)` then returns `null`. Nothing is rejected.
6. Bypass and overshoot:
   - The cap counts entries, not bytes.
   - Message strings are unbounded. For example, the skip message for `--ignore-unreplicated-keyspaces` embeds the whole range set (`RepairCoordinator.java:405-407`), and failure reasons embed exception messages. Retained bytes can therefore far exceed N × 100 B.
   - Expiry (1 day by default) removes entries independently of the cap. Guava cleans expired entries lazily, during writes and some reads.

**A4. Other consumers.**
- Per-repair state outside this cap:
  - `repairs` and `participates` caches of `CoordinatorState`/`ParticipateState`, bounded by `repair_state_size` (default 100 000, `Config.java:958`) and `repair_state_expires` (3 d, `Config.java:957`) (`ActiveRepairService.java:250-260`; registration `RepairCoordinator.java:132`).
  - `parentRepairSessions` and `sessions` maps (unbounded but cleaned on completion).
  - The `Repair-Task` executor queue: unbounded when `repair_command_pool_full_strategy: queue` (`ActiveRepairService.java:208-218`, `Config.java:672-673`).
- `CoordinatorState` keeps the same message `String` object as the status entry, so the two caches can share bytes.
- On disk:
  - repair logging (`RepairCoordinator.java:159, 193, 252, 368, 391`), which goes to `system.log`/`debug.log`;
  - `system_distributed.parent_repair_history` (not reached on the skip path used below).

**A5. Evidence beyond the source.**
- CASSANDRA-13480, "Nodetool repair can hang forever if we lose the notification for the repair completing/failing" (`CHANGES.txt:2044`), https://issues.apache.org/jira/browse/CASSANDRA-13480. It introduced the parent repair status query.
- The existing unit test `test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java:266-285` (`testParentRepairStatus`) covers record and lookup but not the cap.
- Guava `CacheBuilder.maximumSize` documentation: https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html#maximumSize(long). It says "the cache may evict an entry before this limit is exceeded", and that a size of 0 evicts each entry right after it is loaded or stored.
- Guava CachesExplained (cited in the code comment): https://github.com/google/guava/wiki/CachesExplained.

## B. Verification solution

**B1. Claim under test.** On a node started with `-Dcassandra.parent_repair_status_cache_size=N`:
- the parent-repair status cache holds `min(N, number of repair commands issued within the expiry window)` entries;
- the heap it retains is about that count × the per-entry size (that is, it follows N, not the number of repairs);
- at a fixed N, the retained heap scales with the message size, because the cap counts entries rather than bytes.

### B2. Unit tier

**B2a. Environment and build.**
- Setup: Linux, JDK 11 (`java -version` shows 11.x), Ant ≥ 1.10. Copy the tag to local disk: `rsync -a <shared-tag-copy>/ $RUN/cassandra-5.0.9/`, where `$RUN` is a local-disk directory with ≥ 10 GB free.
- Build: `cd $RUN/cassandra-5.0.9 && ant jar && ant build-test`.
- New test: `test/unit/org/apache/cassandra/service/ParentRepairStatusCapTest.java`, placed in the copy only. The `testsome` target already adds the jamm javaagent and appends `${test.jvm.args}` (`build.xml:1159`, `1192`).

```java
package org.apache.cassandra.service;

import java.lang.reflect.Field;
import java.util.Arrays;
import com.google.common.cache.Cache;
import com.google.common.collect.ImmutableList;
import org.junit.BeforeClass;
import org.junit.Test;
import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.utils.ObjectSizes;

public class ParentRepairStatusCapTest
{
    @BeforeClass
    public static void setup() { SchemaLoader.prepareServer(); }

    @Test
    public void sweep() throws Exception
    {
        int m = Integer.getInteger("o127.m", 50000);
        int len = Integer.getInteger("o127.len", 1000);
        int every = Integer.getInteger("o127.every", 5000);
        ActiveRepairService ars = ActiveRepairService.instance();   // first touch: reads the -D now
        Field f = ActiveRepairService.class.getDeclaredField("repairStatusByCmd");
        f.setAccessible(true);
        Cache<Integer, ?> cache = (Cache<Integer, ?>) f.get(ars);
        char[] pad = new char[len]; Arrays.fill(pad, 'x');
        String base = new String(pad);
        System.out.println("O127 cap=" + System.getProperty("cassandra.parent_repair_status_cache_size", "default")
                           + " m=" + m + " len=" + len + " i=0 size=" + cache.size() + " deep=" + ObjectSizes.measureDeep(cache));
        for (int i = 1; i <= m; i++)
        {
            String msg = i + base;                                  // distinct String per entry
            ars.recordRepairStatus(i, ActiveRepairService.ParentRepairStatus.COMPLETED, ImmutableList.of(msg));
            if (i % every == 0)
            {
                cache.cleanUp();
                System.out.println("O127 i=" + i + " size=" + cache.size() + " deep=" + ObjectSizes.measureDeep(cache));
            }
        }
        cache.cleanUp();
        int present = 0, presentLastN = 0;
        long cap = Long.getLong("cassandra.parent_repair_status_cache_size", 100000L);
        for (int i = 1; i <= m; i++)
            if (ars.getRepairStatus(i) != null) { present++; if (i > m - cap) presentLastN++; }
        System.out.println("O127 FINAL size=" + cache.size() + " present=" + present + " presentInLastN=" + presentLastN
                           + " deep=" + ObjectSizes.measureDeep(cache));
    }
}
```

**B2b. Knobs.**
- Main sweep: `cassandra.parent_repair_status_cache_size` ∈ {0, 1, 1000, 10000, unset (default 100000)}, with `o127.m=50000` and `o127.len=1000`.
  - 0 and 1 are the edges.
  - 1000 and 10000 are below M, so the cap binds.
  - The default is above M, so the cap does not bind. This is the positive control: the same workload grows usage freely.
- Entry-size sweep: N=1000 with `o127.len` ∈ {100, 10000}, to show that the cap counts entries, not bytes.
- Invalid edge: N=-1, which should fail at `ActiveRepairService.instance()`.
- How each is set: `-Dtest.jvm.args="..."`. Each run is a fresh JVM, so the singleton reads the new value.

**B2c. Workload.**
- M = 50 000 calls to `recordRepairStatus` with distinct keys 1..M. These are the same calls `RepairCoordinator` makes.
- Each value is `Pair(COMPLETED, [String of len+digits chars])`.
- Why the limit is reached: M ≥ 5 × N for every binding N, so every Guava segment fills and evicts.
- Per-entry size estimate, with compressed oops and Latin-1 strings:

  | Part | Bytes |
  |---|---|
  | String | 24 |
  | byte[] | 16 + len |
  | Pair | 24 |
  | Singleton `ImmutableList` | 16 |
  | `Integer` key | 16 |
  | Guava access/write entry | ≈ 64 |
  | Value reference | 16 |
  | Table slot | ≈ 4–8 |
  | **Total** | **≈ len + 185 B** |

  For len=1000 that is ≈ 1.19 KB per entry; for len=10000, ≈ 10.2 KB.

**B2d. Observables and instruments.**
- `cache.size()` after `cleanUp()`: the check's own operand.
- `present`: how many cmds are still retrievable through the public read path.
- `presentInLastN`: whether the survivors are the most recent cmds.
- `ObjectSizes.measureDeep(cache)`: jamm deep size of the whole Guava cache object graph, in bytes.
- Sampling: at i=0 and every 5000 puts.
- Not observable here: GC-level heap occupancy. That is covered in B3.

**B2e. Procedure.**
1. Copy the test file into the copy, then run `ant build-test`.
2. For each knob value, run:
   ```
   ant testsome -Dtest.name=org.apache.cassandra.service.ParentRepairStatusCapTest \
     -Dtest.jvm.args="-Dcassandra.parent_repair_status_cache_size=<N> -Do127.m=50000 -Do127.len=<L>"
   ```
   For the default run, omit the `-Dcassandra...` part.
3. Collect the results: `grep -h 'O127' build/test/output/TEST-org.apache.cassandra.service.ParentRepairStatusCapTest.xml`. Copy the `O127` lines into a results table, one row per (N, len).
4. For N=-1, record the exception class and message from the same XML.

**B2f. Predictions.** With m=50000 and len=1000 unless stated otherwise:

| N | len | final `size` = `present` | final `deep` |
|---|---|---|---|
| 0 | 1000 | 0 | ≈ empty-cache baseline B0 (a few KB) |
| 1 | 1000 | 1 | B0 + ~1.2 KB |
| 1000 | 1000 | exactly 1000 | B0 + ≈ 1.2 MB (1.1–1.4 MB) |
| 10000 | 1000 | exactly 10000 | B0 + ≈ 12 MB (11–14 MB) |
| default | 1000 | 50000 (cap not binding) | B0 + ≈ 60 MB (55–70 MB) |
| 1000 | 100 | 1000 | B0 + ≈ 0.29 MB |
| 1000 | 10000 | 1000 | B0 + ≈ 10.2 MB |

- Per-checkpoint shape: `size` rises in step with i until it approaches N, then stays flat at ≤ N. It may flatten slightly below N before i ≫ N, because of per-segment eviction. It reaches exactly N by i = 5N.
- `presentInLastN` is close to `present`, ≥ 90 % of N: survivors are mostly the newest cmds. It is not exactly N, because segments evict independently.
- N=-1 fails with `IllegalArgumentException` (from `maximumSize`, wrapped in an initializer error).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Final `size` = min(N, M) for every N, and `deep` flat after i ≈ N while i keeps rising | Claim confirmed at unit level: the cap bounds entries and therefore the cache's bytes |
| `size` > N at any checkpoint after `cleanUp()` | Claim wrong: the cap does not hold |
| `size` grows to 50000 for N=1000 or 10000 | Claim wrong: property not applied, or the cache was built before the -D was read; check that the `O127 cap=` line echoes N |
| Default run reaches 50000 entries and ≈ 60 MB while N=1000 stays ≈ 1.2 MB | Positive control moved; instrument and workload are sensitive |
| Default run also stuck near 1000 | Control failed; the result is not interpretable (wrong cache, or reflection hit another field) |
| At N=1000, `deep` scales ≈ ×35 between len=100 and len=10000 while `size` stays 1000 | Confirms count-not-bytes |
| `deep` roughly the same for both lengths | Contradicts the per-entry model; investigate whether strings are shared or deduplicated |
| N=0 retains entries | Guava semantics differ from the docs; claim wrong for the edge |

**B2h. Controls.**
- The default-N run is the positive control.
- The `O127 cap=` header line confirms which value the JVM saw.
- `cleanUp()` before every reading rules out pending-eviction artefacts.
- Distinct `String` instances rule out interning or sharing, which would hide the bytes.
- Expiry (86 400 s) cannot fire within a run of under 8 min, so eviction is attributable to size.
- `measureDeep` on an empty cache gives baseline B0.

### B3. Cluster tier

**B3a. Environment and build.**
- Node and build: one Linux node, JDK 11. Use the build from B2a (`ant jar` in `$RUN/cassandra-5.0.9`) and run from `bin/`.
- A single node is enough: repair status is recorded on the coordinator. A keyspace with RF=2 passes the RF<2 short-circuit (`StorageService.java:4797`) but has no neighbours, so the `ignoreUnreplicatedKeyspaces` option makes each repair finish through the skip path (`RepairCoordinator.java:384-408`). That path records `IN_PROGRESS`, then `COMPLETED` with the long skip message.
- `conf/cassandra.yaml` changes, in the copy:
  - `num_tokens: 256`: 256 ranges, so each skip message is ≈ 11.3 KB.
  - Comment out `allocate_tokens_for_local_replication_factor`.
  - `data_file_directories: [$RUN/data]`, `commitlog_directory: $RUN/commitlog`, `hints_directory: $RUN/hints`, `saved_caches_directory: $RUN/saved_caches`.
  - `repair_state_size: 10`: pins the `CoordinatorState` cache, the other consumer, to ≤ 10 entries.
  - `listen_address` and `rpc_address`: `127.0.0.1`.
- Environment variables: `export CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
- JMX: local JMX on 127.0.0.1:7199, with no authentication by default (`LOCAL_JMX=yes`).
- Driver: a single-file Java program `$RUN/Drive.java`, run with `java Drive.java <mode> ...` (JDK 11 source launcher):

```java
import javax.management.*; import javax.management.remote.*; import java.util.*;
public class Drive {
  public static void main(String[] a) throws Exception {
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
    MBeanServerConnection s = c.getMBeanServerConnection();
    ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
    String[] sigR = {String.class.getName(), Map.class.getName()}, sigS = {"int"};
    if (a[0].equals("repair")) {               // repair <M> <batch>
      int m = Integer.parseInt(a[1]), batch = Integer.parseInt(a[2]); int last = 0;
      Map<String,String> o = new HashMap<>(); o.put("ignoreUnreplicatedKeyspaces","true"); o.put("columnFamilies","t");
      for (int i = 1; i <= m; i++) {
        last = (Integer) s.invoke(ss, "repairAsync", new Object[]{"o127", o}, sigR);
        if (last == 0) throw new IllegalStateException("cmd 0: RF<2 short-circuit, no status recorded");
        if (i % batch == 0 || i == m) {        // wait for this batch to finish
          while (true) { List<?> st = (List<?>) s.invoke(ss, "getParentRepairStatus", new Object[]{last}, sigS);
            if (st != null && !"IN_PROGRESS".equals(st.get(0))) break; Thread.sleep(50); }
          System.out.println("DRIVE issued=" + i + " lastCmd=" + last);
        }
      }
    } else if (a[0].equals("count")) {         // count <firstCmd> <lastCmd>
      int lo = Integer.parseInt(a[1]), hi = Integer.parseInt(a[2]), present = 0, completed = 0;
      for (int i = lo; i <= hi; i++) { List<?> st = (List<?>) s.invoke(ss, "getParentRepairStatus", new Object[]{i}, sigS);
        if (st != null) { present++; if ("COMPLETED".equals(st.get(0))) completed++; } }
      System.out.println("COUNT present=" + present + " completed=" + completed);
    }
    c.close();
  }
}
```

  If a batch's last cmd is evicted before it is polled (possible only when N is very small, such as N=0), the wait loop polls forever. For those runs, replace the wait with `nodetool tpstats | grep Repair-Task` until Active and Pending are both 0.

**B3b. Knobs.**
- Main sweep: `JVM_EXTRA_OPTS="-Dcassandra.parent_repair_status_cache_size=N"` with N ∈ {100, 10000, unset = 100000}.
  - N=100: the cap binds hard.
  - N=10000: the cap binds, with a mid-size footprint.
  - Default: does not bind at M=30000. This is the positive control.
- Optional extra: N=0, run with the tpstats wait.
- Each value needs a node restart (property read once at construction). Wipe `$RUN/data`, `$RUN/commitlog`, `$RUN/hints` and `$RUN/saved_caches` between values so every run starts identically.

**B3c. Workload.**
- Schema:
  ```
  CREATE KEYSPACE o127 WITH replication = {'class':'NetworkTopologyStrategy','datacenter1':2};
  CREATE TABLE o127.t (k int PRIMARY KEY, v int);
  ```
  RF 2 on one node raises a warning but is allowed. No data is needed.
- Drive: `java Drive.java repair 30000 500`, which issues M = 30 000 repair commands through JMX `repairAsync` in batches of 500.
- Per-entry size: each repair leaves one `COMPLETED` entry whose message is "Nothing to repair for [<256 ranges>] in o127 - unreplicated keyspace is ignored …".
  - Each `Range` prints as `(a,b]` with two Murmur3 longs, ≈ 44 chars with the separator.
  - 256 × 44 + ~120 ≈ 11.4 KB Latin-1.
  - Entry overhead ≈ 0.2 KB, so ≈ 11.6 KB per entry.
- Expected retained bytes:

  | N | Entries kept | Retained |
  |---|---|---|
  | 100 | 100 | ≈ 1.2 MB |
  | 10000 | 10000 | ≈ 116 MB |
  | default | 30000 | ≈ 350 MB |

  The heap is 2 GB, so 350 MB is reachable without OOM.
- Duration: about 5–30 min per value. Each skip repair computes neighbours for 256 ranges.

**B3d. Observables and instruments.**
- Live heap:
  - `jcmd <pid> GC.class_histogram > hist-<phase>.txt` forces a full GC and lists live objects. Record the `Total` bytes line and the `[B` (byte[]) row.
  - Also run `jcmd <pid> GC.heap_info` after `jcmd <pid> GC.run`.
- Retained-entry count: `java Drive.java count 1 30000` reports `present` (the JMX read path of the cache). Run it after the histogram, because `getIfPresent` only touches existing entries.
- Optional precise attribution: `jcmd <pid> GC.heap_dump $RUN/dump-<N>.hprof`, then read the retained size of `ActiveRepairService.repairStatusByCmd` with Eclipse MAT (dominator tree, filtered on `LocalCache`). The dump is ≤ 2 GB on `$RUN`.
- Sampling points:
  - **base**: after startup and schema creation, before any repair;
  - **after**: after the driver finishes and `tpstats` shows Repair-Task Active=0 and Pending=0;
  - **after+60s**: repeat after 60 s, to check stability.
- Not observable directly: the cache's bytes separately from other live objects, except through MAT. The histogram delta `after − base` is attributed to the cache because the other per-repair holders are pinned (see B3h).

**B3e. Procedure.**
1. Edit `cassandra.yaml` as in B3a. `mkdir -p $RUN/{data,commitlog,hints,saved_caches,logs}`.
2. For each N:
   1. Start the node: `JVM_EXTRA_OPTS="-Dcassandra.parent_repair_status_cache_size=N" bin/cassandra -p $RUN/pid`. For the default run, omit the property.
   2. Wait for `bin/nodetool status` to show `UN`.
   3. Confirm the property was read: `grep -c parent_repair_status_cache_size $RUN/logs/system.log`. The JVM arguments line in the startup log lists it.
   4. Apply the schema: `bin/cqlsh 127.0.0.1 -e "<B3c schema>"`.
   5. Quiet the logs: `bin/nodetool setlogginglevel org.apache.cassandra.repair WARN`. This avoids ~256 INFO lines per repair (`RepairCoordinator.java:391`).
   6. Take the base samples: `jcmd $(cat $RUN/pid) GC.class_histogram > $RUN/hist-N-base.txt`, then `jcmd $(cat $RUN/pid) GC.run; jcmd $(cat $RUN/pid) GC.heap_info`.
   7. Drive: `java $RUN/Drive.java repair 30000 500 | tee $RUN/drive-N.txt`.
   8. Wait until `bin/nodetool tpstats | grep Repair-Task` shows Active 0 and Pending 0.
   9. Take the after samples: histogram to `hist-N-after.txt`, plus heap_info. Repeat 60 s later.
   10. Count: `java $RUN/Drive.java count 1 30000`.
   11. Stop the node: `bin/nodetool stopdaemon` (or `kill $(cat $RUN/pid)`), then confirm `pgrep -f CassandraDaemon` prints nothing.
   12. Wipe `$RUN/{data,commitlog,hints,saved_caches}/*`.
3. Tabulate per N: `present`, ΔTotal (after − base), Δ`[B`.

**B3f. Predictions.** Stated before any run, M = 30 000, entry ≈ 11.6 KB:

| N | `present` | ΔTotal live heap (after − base) | Δ `[B` |
|---|---|---|---|
| 100 | 100 | ≈ 1 MB plus noise. Below 30 MB in all cases, given noise from other activity | ≈ +1.1 MB |
| 10000 | 10000 | ≈ +116 MB (100–140 MB) | ≈ +114 MB |
| default (100000) | 30000 | ≈ +350 MB (300–400 MB) | ≈ +342 MB |

- Ratio check: ΔTotal(default) / ΔTotal(10000) ≈ 3 (= 30000 / 10000).
- The after and after+60s readings agree within 10 %.
- What would show the claim wrong:
  - `present` > N;
  - ΔTotal at N=10000 near the default run's value;
  - ΔTotal growing with M rather than with N in a capped run.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `present` = min(N, 30000) and ΔTotal ≈ present × 11.6 KB for every N | Claim confirmed: the property caps the status cache's heap at N entries |
| N=10000 and N=100 runs both ≈ +350 MB, or `present` = 30000 | Claim wrong: the cap did not bind (property not read, or a different holder retains the messages) |
| `present` = N, but ΔTotal still ≈ +350 MB at N=100 | The cap holds for its own cache, but heap does not follow it because another holder retains the strings. Check `repair_state_size` and use MAT to find the holder; the claim is not confirmed for heap |
| Default run +300–400 MB while N=100 ≈ flat | Positive control moved; the workload and instruments are sensitive |
| Default run also ≈ flat | Control failed: entries were not created (check `DRIVE lastCmd` ≠ 0, and that `getParentRepairStatus(last)` is COMPLETED with a long message); not interpretable |
| ΔTotal far below prediction in all runs, with `present` correct | Entry-size model wrong (for example, fewer ranges than 256). Check one entry's message length with `getParentRepairStatus`; the count claim still stands |

**B3h. Controls.**
- The default-N run is the positive control: same workload, cap not binding.
- `repair_state_size: 10` pins the `CoordinatorState` cache, which shares message strings. That isolates `repairStatusByCmd`.
- The driver waits for each batch, so executor-queue backlog is not in the reading, and tpstats confirms it is empty.
- The skip path happens before `prepare`, so no `ParentRepairSession` or streaming exists. Confirm with `bin/nodetool repair_admin list`, which shows none.
- Expiry of 1 day exceeds the run time.
- Full-GC histograms remove garbage.
- Fresh data directories and a restart per N give an identical base.
- The optional MAT retained size attributes bytes to the cache object directly.

**B4. Risks and cleanup.**
- Disk:
  - logs go to `$RUN/logs`; logback caps each rolling log at 5 GB, and with repair at WARN the expected size is ≪ 1 GB;
  - heap dumps are ≤ 2 GB each, so delete them after analysis;
  - data dirs hold almost nothing (no rows).
- Placement: everything goes under `$RUN` on local disk. Nothing is built in the shared tree; the test file is added to the local copy only.
- Processes:
  - after each run, `pgrep -f CassandraDaemon` and `pgrep -f Drive.java` should print nothing; `kill` any leftovers;
  - Ant unit runs end their forked JVM, so check `pgrep -f ParentRepairStatusCapTest`.
- Final cleanup: `rm -rf $RUN/{data,commitlog,hints,saved_caches,logs,*.hprof}`, then remove `$RUN/cassandra-5.0.9` if it is no longer needed.
- Port use: 7000/7199/9042 on 127.0.0.1 only. Make sure no other Cassandra on the node uses them, or change `storage_port`/`native_transport_port`/`JMX_PORT`.

## C. Sources read

src/java/org/apache/cassandra/service/ActiveRepairService.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/repair/RepairCoordinator.java
src/java/org/apache/cassandra/repair/messages/RepairOption.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/tools/RepairRunner.java
src/java/org/apache/cassandra/dht/Range.java
src/java/org/apache/cassandra/utils/ObjectSizes.java
test/unit/org/apache/cassandra/service/ActiveRepairServiceTest.java
conf/cassandra.yaml
conf/logback.xml
build.xml
.build/parent-pom-template.xml
CHANGES.txt
https://issues.apache.org/jira/browse/CASSANDRA-13480
https://guava.dev/releases/32.0.1-jre/api/docs/com/google/common/cache/CacheBuilder.html
https://github.com/google/guava/wiki/CachesExplained

## D. Stage-4 feedback

none yet
