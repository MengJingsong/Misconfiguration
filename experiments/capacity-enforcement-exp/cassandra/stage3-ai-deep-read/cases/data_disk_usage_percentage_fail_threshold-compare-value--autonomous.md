# data_disk_usage_percentage_fail_threshold — verification solution  <!-- file: cases/data_disk_usage_percentage_fail_threshold-compare-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line, **linked**: [`MaxThreshold.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java#L52) (`return value > threshold;` in `MaxThreshold.compare`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code 2.1.330, 2026-11-24 |
| Estimate | `positive`. This shared comparison decides when the local node moves to the `FULL` disk-usage state for the `local_data_disk_usage` guardrail. Once a node is `FULL`, ordinary users' non-conditional CQL writes to any replica on that node are rejected, so data-directory usage stops near `fail%` of the counted total. The cap holds only with an authenticating authenticator and ordinary users, and it overshoots by up to one monitor interval of writes. Single-statement LWTs, superusers and internal/background writers bypass it (A3). |
| Ground | — |

> **Choice of constraint.** The given line is the comparison shared by every `MaxThreshold`
> guardrail (about 20 of them, listed in A4). Most cap a per-request count or schema size.
> `local_data_disk_usage` is the one whose job is to cap a resource directly: it caps disk used by
> the data directories, and its `FULL` decision is made on this line. This case therefore traces and
> tests `data_disk_usage_percentage_fail_threshold` through this line. The other users of the line
> are listed in A4 so the line is not double-counted.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `data_disk_usage_percentage_fail_threshold`, the fail half of the `local_data_disk_usage`
  guardrail (`PercentageThreshold extends MaxThreshold`, `db/guardrails/PercentageThreshold.java:32`).
  Its partners are `data_disk_usage_percentage_warn_threshold` and the denominator override
  `data_disk_usage_max_disk_size`.
- **Kind:** configuration entry (guardrail), live-updatable.
- **Declared:** [`Config.java:927`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L927)
  (`public volatile int data_disk_usage_percentage_fail_threshold = -1;`). The warn threshold is at
  `Config.java:926` and the max disk size at `Config.java:928`.
- **Unit:** integer percent of the "total" data-disk size (A2).
- **Default:** `-1`, meaning disabled. It is a literal default, not derived (`conf/cassandra.yaml:2201`).
  `MaxThreshold.failValue` maps `<= 0` to `Long.MAX_VALUE` (`MaxThreshold.java:56-60`). With both
  thresholds `<= 0`, `Threshold.enabled` returns false (`Threshold.java:85`), and the monitor then
  reports `NOT_AVAILABLE` (`DiskUsageMonitor.java:191-192`).
- **Valid range:** `[1,100]` or `-1`, with warn `<=` fail. This is checked at startup
  (`GuardrailsOptions.java:86`, `1111-1121`, `1176-1184`) and on every set
  (`GuardrailsOptions.java:741-752`).
- **How to set it:**
  - The yaml keys `data_disk_usage_percentage_warn_threshold` and `data_disk_usage_percentage_fail_threshold`.
  - JMX: `org.apache.cassandra.db:type=Guardrails`, `setDataDiskUsagePercentageThreshold(warn, fail)`
    (`Guardrails.java:1198-1200`).
  - `nodetool setguardrailsconfig data_disk_usage_percentage_threshold <fail> <warn>`. The fail
    value comes first, because the arguments are reversed at `tools/nodetool/GuardrailsConfigCommand.java:292`.
  - No restart is needed: the field is `volatile`, and the periodic task reads it on every run
    (`DiskUsageMonitor.java:82-93`).
  - The monitor period, JVM property `cassandra.disk_usage.monitor_interval_ms` (default 30000,
    `CassandraRelevantProperties.java:200`), is read once at `start` and needs a restart.

**A2. What it caps.**
- **Resource:** disk, namely the space under the configured data file directories.
- **Compared quantity:** `value = ceil(100 * used / total)` (`DiskUsageMonitor.java:107-108`). The
  parts are:
  - `used`: the sum of `Directories.DataDirectory.getRawSize()` over all data directories.
    `getRawSize()` is the recursive apparent size, `FileUtils.folderSize` → `attrs.size()`
    (`Directories.java:787-790`, `FileUtils.java:497-510`). It includes sstables, compaction
    temporaries, snapshots and backups under the data directories. **Plus** the live data size of
    all memtables (`DiskUsageMonitor.java:161-162`, `173-186`).
  - `total`: the raw on-disk part of `used`, plus `FileStore.getUsableSpace()` summed per distinct
    file store, capped by `data_disk_usage_max_disk_size` when that is set (`DiskUsageMonitor.java:144-159`).
    The ratio is rounded UP to 5 decimals (`DiskUsageMonitor.java:169`).
- **Not counted:** the commit log, hints, saved caches and CDC, unless they live inside a data
  directory (the yaml text at `conf/cassandra.yaml:2193-2195` says the same).

**A3. Mechanism.**
1. **Periodic task.** `StorageService` calls `DiskUsageBroadcaster.instance.startBroadcasting()`
   (`StorageService.java:1236`), which starts `DiskUsageMonitor.start` (`DiskUsageBroadcaster.java:90-99`).
   That schedules a fixed-rate task on `ScheduledExecutors.scheduledTasks` every
   `cassandra.disk_usage.monitor_interval_ms`, default 30 s (`DiskUsageMonitor.java:82-95`). The
   task runs whether or not the guardrail is enabled. While the guardrail is enabled, the task calls
   `updateLocalState(getDiskUsage(), notifier)` (`DiskUsageMonitor.java:91-94`).
2. **State decision.** `getState(percentageCeiling)` (`DiskUsageMonitor.java:188-201`) calls
   `Guardrails.localDataDiskUsage.failsOn(value, null)` (`DiskUsageMonitor.java:194`). That is
   `enabled(null) && compare(value, failValue(null))` (`Threshold.java:111-114`), and `compare` is
   **the given line,
   [`MaxThreshold.java:52`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java#L52)**,
   `return value > threshold;`.
   - **True** → `FULL`.
   - **False** → the same comparison against the warn value (`DiskUsageMonitor.java:197`,
     `MaxThreshold.java:52`). True there gives `STUFFED`, otherwise `SPACIOUS`.
   - The comparison is strict: usage of exactly `F%` is not `FULL`. Because `ceil(p) > F ⇔ p > F`
     for integer `F`, the node is `FULL` exactly when `used/total > F/100`, up to floating point.
     `percentage = usageRatio * 100` is a double, so for `F ∈ {7, 14, 28, 55, 56}` a ratio of
     exactly `F/100` gives `ceil(...) = F+1`. The node then turns `FULL` at exactly `F%`. This is a
     sub-1-point stricter edge, harmless to the cap and tested in B2.
3. **Logging.** `localDataDiskUsage.guard(value, state, false, null)` (`DiskUsageMonitor.java:112`)
   goes through `Threshold.guard` (`Threshold.java:128-143`), which calls the same `compare`. With
   `state == null`, `fail` only logs and emits a diagnostic event; it does not throw
   (`Guardrail.java:124-141`). Logging is rate-limited to once per
   `cassandra.disk_usage.notify_interval_ms`, default 30 min (`CassandraRelevantProperties.java:202`,
   `Guardrails.java:458-464`). Enforcement does not depend on the log.
4. **Propagation.** When the state changes, the notifier calls
   `Gossiper.addLocalApplicationState(DISK_USAGE, state)` (`DiskUsageBroadcaster.java:92-98`).
   That fires `onChange` locally and synchronously (`Gossiper.java:2245-2260`) and on peers through
   gossip. `DiskUsageBroadcaster.onChange` stores the per-endpoint state and sets
   `hasStuffedOrFullNode` (`DiskUsageBroadcaster.java:102-121`).
5. **Enforcement on writes.** The coordinator runs `ModificationStatement.validateDiskUsage`
   (`ModificationStatement.java:285-302`). If `replicaDiskUsage.enabled(state)` and some node is
   `STUFFED` or `FULL`, it checks every write replica of every partition key
   (`ReplicaLayout.forTokenWriteLiveAndDown`). `Guardrails.replicaDiskUsage.guard(endpoint, state)`
   (`Predicates.java:81-94`, `Guardrails.java:448-456`) then throws `GuardrailViolatedException`,
   an `InvalidRequestException`, with the message "Write request failed because disk usage exceeds
   failure threshold" when the replica is `FULL` (`Guardrail.java:139-140`).
   - Called from `executeWithoutCondition` (`ModificationStatement.java:517`).
   - Called for every statement of a `BatchStatement` (`BatchStatement.java:419-420`).
6. **Who is checked.** `Guardrail.enabled(state)` requires
   `DatabaseDescriptor.isDaemonInitialized() && (state == null || state.isOrdinaryUser())`
   (`Guardrail.java:93-96`). `isOrdinaryUser = !isSuper() && !isSystem()`
   (`ClientState.java:594-597`). `isSuper()` is **true for every client when the authenticator
   does not require authentication** (`ClientState.java:602-605`). With the default
   `authenticator: AllowAllAuthenticator` (`conf/cassandra.yaml:198`), no client write is ever
   rejected.
7. **Bypasses and overshoot.**
   - **Detection lag:** up to one monitor interval (30 s) of writes, plus gossip delay for remote
     coordinators, before rejection starts.
   - **Single-statement conditional writes (LWT)** take `executeWithCondition`
     (`ModificationStatement.java:501`, `538-554`), which never calls `validateDiskUsage`.
     Conditional statements inside a batch are checked (`BatchStatement.java:419-420`).
   - **Superusers, internal `ClientState`s and the AllowAll authenticator** are excluded (step 6).
   - **Writes that never pass through `ModificationStatement`:** hints replay, batchlog replay, read
     repair, materialized-view updates, streaming/repair/bootstrap, `sstableloader`, `nodetool import`,
     compaction output, and system-keyspace writes.
   - **Writes already in memtables** are flushed regardless. They were already counted in `used`.
   - **Compaction** can transiently add up to its input size in temporary files (counted in `used`
     but not prevented).
   - **The guardrail does not stop usage from rising** further from those other sources. It only
     stops new user mutations.

**A4. Other consumers.**
- **Same disk, outside this constraint:**
  - Compaction temporaries and outputs, streaming and repair data, snapshots (auto-snapshot on
    `DROP`/`TRUNCATE`, `nodetool snapshot`), incremental backups, and SAI/2i index files under the
    data directories.
  - Hints, the commit log, saved caches and CDC, if they share the file system. They shrink
    `usable`, which raises the ratio, but they are not in `used`.
  - Anything else on the same file system, which shrinks `usableSpace`. Without
    `data_disk_usage_max_disk_size` this changes `total`.
- **Other users of the given line** (`MaxThreshold.compare`, via `Threshold.guard`/`triggersOn`/
  `failsOn`/`warnsOn`), all declared in `db/guardrails/Guardrails.java`. These are not this case's
  constraint:
  - `keyspaces` (61), `tables` (75), `columns_per_table` (89), `secondary_indexes_per_table` (100),
    `materialized_views_per_table` (123).
  - `page_size` (237), `partition_keys_in_select` (251), `in_select_cartesian_product` (294).
  - `partition_size` (332), `partition_tombstones` (344), `column_value_size` (356),
    `collection_size` (368), `items_per_collection` (380).
  - `fields_per_udt` (392), `vector_dimensions` (419), `local_data_disk_usage` (432, this case).
  - `maximum_replication_factor` (481), `maximum_timestamp` (490), `sai_sstable_indexes_per_query` (508).
  - `sai_string_term_size` (520), `sai_frozen_term_size` (532), `sai_vector_term_size` (544).

**A5. Evidence beyond the source.**
- **CASSANDRA-17150**, "Add guardrail for data disk usage" (`CHANGES.txt:900`, 4.1-alpha1),
  https://issues.apache.org/jira/browse/CASSANDRA-17150
- **CASSANDRA-20787**, which fixed a first-boot crash with `data_disk_usage_max_disk_size` set before
  the data directory exists (`CHANGES.txt:129`, in 5.0.5, so fixed at the pinned tag),
  https://issues.apache.org/jira/browse/CASSANDRA-20787
- **`conf/cassandra.yaml:2193-2211`**, the yaml description: "the main purpose … is rejecting user
  writes when the disks are over the defined usage percentage".
- **`test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java`:** the state
  boundaries 90→`STUFFED`, 91→`FULL`; the ratio arithmetic with `max_disk_size`; memtable inclusion.
- **`test/distributed/org/apache/cassandra/distributed/test/guardrails/GuardrailDiskUsageTest.java`:**
  write rejection with injected `FULL` states. It uses a non-superuser because "the default
  superuser is excluded from guardrails".
- **Gap in the existing tests:** neither test drives real disk usage to the threshold. The states
  are injected or the ratio is mocked.

## B. Verification solution

**B1. Claim under test.** With `PasswordAuthenticator`, an ordinary (non-superuser) role, and
`data_disk_usage_percentage_fail_threshold = F`, non-conditional CQL writes are rejected once the
counted data usage (data directories plus live memtables) exceeds `F%` of `total`. The data
directory's size therefore stops growing at
`F% × total + (write rate × monitor interval) + small slack`, instead of following the attempted
write volume.

Three things are expected to escape the cap:
- single-statement LWTs;
- superusers;
- every client when the authenticator is `AllowAllAuthenticator`.

### B2. Unit tier

Drive the classes in-process: `DiskUsageMonitor`, `DiskUsageBroadcaster` and
`ModificationStatement` through `GuardrailTester`/`CQLTester`. That is one JVM with no separate
node and no gossip. The monitor task is replaced by explicit synchronous calls, so the operand is
recorded at every step.

**B2a. Environment and build.**
- Linux, JDK 11 (`java -version` must print 11.x), Apache Ant ≥ 1.10.
- Copy the tree to local disk: `export W=/mydata/$USER-o158; mkdir -p $W && rsync -a ~/cassandra-5.0.9/ $W/src/`
  (use any local scratch dir if `/mydata` is absent; at least 5 GiB free).
- Build with `cd $W/src && ant jar` here. The test classes are built in B2e step 2, after the probe
  test file exists (building them first and then running with `-Dno-build-test=true` would miss the
  new class).
- Test source: `$W/src/test/unit/org/apache/cassandra/db/guardrails/DiskUsageCapProbeTest.java`
  (B2e).
- JVM options: the ant `testsome` defaults (they include `-XX:ActiveProcessorCount=2` and the jamm
  agent). No extra options.

**B2b. Knobs.**
- **The fail threshold `F`**, one test method per value:
  - `probeFail50`: warn 40, fail 50.
  - `probeFail80`: warn 70, fail 80.
  - `probeDisabled`: -1/-1, the positive control.
  - Why these values: two distinct thresholds show that the stopping point moves with `F`, and
    `-1` shows the workload moves usage when no cap binds.
- **`data_disk_usage_max_disk_size = M`.** It is set per method to
  `M = max(ceil((used0 + 100 MiB)/MiB), ceil(10·used0/MiB))` MiB, so the baseline is at most 10% of
  `M` and the threshold is reached after tens of MiB, not hundreds of GiB. `used0` is the counted
  usage measured after table creation and a flush.
- **How each is set:** `Guardrails.instance.setDataDiskUsagePercentageThreshold(warn, fail)` and
  `Guardrails.instance.setDataDiskUsageMaxDiskSize(M + "MiB")`. These are the same setters JMX
  and nodetool use.
- **Boundary sub-test inside `probeFail80`:** direct `failsOn` and `getState` probes at
  `F-1`, `F`, `F+1`. Plus, with fail 55, `updateLocalState(0.55, …)`, which exercises the
  floating-point edge from A3.

**B2c. Workload.**
- **Table:** `CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false}`.
- **Row:** one 1 MiB (1 048 576-byte) random blob per row, inserted as the GuardrailTester ordinary
  user (`execute(userClientState, …)`).
- **Flush:** after every 8 rows, so both on-disk and memtable parts of `used` are exercised.
- **Loop bound:** `N = ceil(0.95·M − used0)/MiB + 20` rows, which goes past every threshold up to
  95%.
- **Why the limit is reached:** each row adds about 1 MiB to `used` (memtable live size first, then
  `Data.db` after flush, plus small index/filter components), and the threshold sits
  `F/100·M − used0 ≥ 0.4·M − 0.1·M` above the baseline.
- **After the loop**, in `probeFail50`/`probeFail80`, while the state is `FULL`:
  - one `INSERT … IF NOT EXISTS` (LWT) as the user;
  - one plain `INSERT` as the superuser (`superClientState`);
  - one as `systemClientState`;
  - one 2-statement `BEGIN BATCH … APPLY BATCH` as the user.

**B2d. Observables and instruments.** Per row, printed as one line
`PROBE <method> i used_bytes memtable_bytes total_bytes value state outcome` and appended to
`$W/src/build/test/probe-<method>.tsv`:
- `used_bytes`: the sum of `getRawSize()` over `Directories.dataDirectories.getAllDirectories()`,
  plus `getAllMemtableSize()`.
- `total_bytes`: `min(used_raw + usable, M)`.
- `value = ceil(100·getDiskUsage())`. This is the left operand of the given line.
- `state`: `DiskUsageMonitor.state()`.
- `outcome`: `ACCEPT`, or `REJECT` when `GuardrailViolatedException` is raised with the message
  containing "disk usage exceeds failure threshold".

Not observable here: gossip propagation to peers and the 30 s schedule. Both are replaced by
synchronous calls; B3 covers them.

**B2e. Procedure.**
1. Create the test file `DiskUsageCapProbeTest.java` in package `org.apache.cassandra.db.guardrails`
   (so it can use the package-private `guardrails()` and `GuardrailTester`):

```java
package org.apache.cassandra.db.guardrails;

import java.io.FileWriter;
import java.nio.ByteBuffer;
import java.util.Arrays;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Consumer;
import org.junit.Test;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.gms.ApplicationState;
import org.apache.cassandra.locator.InetAddressAndPort;
import org.apache.cassandra.service.StorageService;
import org.apache.cassandra.service.disk.usage.*;
import org.apache.cassandra.utils.FBUtilities;
import static org.junit.Assert.*;

public class DiskUsageCapProbeTest extends GuardrailTester
{
    static final long MiB = 1L << 20;
    final DiskUsageMonitor m = new DiskUsageMonitor();
    final InetAddressAndPort self = FBUtilities.getBroadcastAddressAndPort();
    final Consumer<DiskUsageState> notifier = s -> DiskUsageBroadcaster.instance.onChange(
        self, ApplicationState.DISK_USAGE, StorageService.instance.valueFactory.diskUsage(s.name()));

    long rawUsed() { long u = 0; for (Directories.DataDirectory d : Directories.dataDirectories.getAllDirectories()) u += d.getRawSize(); return u; }

    void run(String name, int warn, int fail) throws Throwable
    {
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob) WITH compression = {'enabled': false}");
        flush();
        long used0 = rawUsed() + m.getAllMemtableSize();
        long M = Math.max((used0 + 100 * MiB + MiB - 1) / MiB, (10 * used0 + MiB - 1) / MiB);
        guardrails().setDataDiskUsageMaxDiskSize(M + "MiB");
        guardrails().setDataDiskUsagePercentageThreshold(warn, fail);
        m.updateLocalState(m.getDiskUsage(), notifier);
        long n = (long) Math.ceil((0.95 * M * MiB - used0) / MiB) + 20;
        byte[] blob = new byte[(int) MiB];
        try (FileWriter out = new FileWriter("build/test/probe-" + name + ".tsv", true))
        {
            out.write(String.format("# used0=%d M_MiB=%d warn=%d fail=%d%n", used0, M, warn, fail));
            for (int i = 0; i < n; i++)
            {
                ThreadLocalRandom.current().nextBytes(blob);
                String outcome = "ACCEPT";
                try { execute(userClientState, "INSERT INTO %s (k, v) VALUES (?, ?)",
                              Arrays.asList(Int32Type.instance.decompose(i), ByteBuffer.wrap(blob))); }
                catch (GuardrailViolatedException e) { assertTrue(e.getMessage().contains("disk usage exceeds failure threshold")); outcome = "REJECT"; }
                if (i % 8 == 7) flush();
                double ratio = m.getDiskUsage();
                m.updateLocalState(ratio, notifier);          // stands in for the 30 s task
                String line = String.format("PROBE %s %d %d %d %d %d %s %s%n", name, i, rawUsed() + m.getAllMemtableSize(),
                                            m.getAllMemtableSize(), M * MiB, (long) Math.ceil(ratio * 100), m.state(), outcome);
                System.out.print(line); out.write(line);
            }
            if (fail > 0)
            {
                assertEquals(DiskUsageState.FULL, m.state());
                String[] q = { "INSERT INTO %s (k, v) VALUES (100001, 0x00) IF NOT EXISTS" };
                for (String[] c : new String[][]{ {"user-LWT", q[0]}, {"super", "INSERT INTO %s (k, v) VALUES (100002, 0x00)"},
                                                 {"user-batch", "BEGIN BATCH INSERT INTO %1$s (k, v) VALUES (100003, 0x00); INSERT INTO %1$s (k, v) VALUES (100004, 0x00); APPLY BATCH"} })
                {
                    String r;
                    try { execute(c[0].equals("super") ? superClientState : userClientState, c[1]); r = "ACCEPT"; }
                    catch (GuardrailViolatedException e) { r = "REJECT"; }
                    String line = String.format("BYPASS %s %s%n", c[0], r); System.out.print(line); out.write(line);
                }
                try { execute(systemClientState, "INSERT INTO %s (k, v) VALUES (100005, 0x00)"); out.write("BYPASS system ACCEPT\n"); }
                catch (GuardrailViolatedException e) { out.write("BYPASS system REJECT\n"); }
            }
        }
    }

    @Test public void probeFail50() throws Throwable { run("fail50", 40, 50); }
    @Test public void probeFail80() throws Throwable
    {
        guardrails().setDataDiskUsagePercentageThreshold(70, 80);
        assertFalse(Guardrails.localDataDiskUsage.failsOn(79, null));
        assertFalse(Guardrails.localDataDiskUsage.failsOn(80, null));   // value > threshold, strict
        assertTrue (Guardrails.localDataDiskUsage.failsOn(81, null));
        assertEquals(DiskUsageState.STUFFED, m.getState(80));
        assertEquals(DiskUsageState.FULL,    m.getState(81));
        guardrails().setDataDiskUsagePercentageThreshold(50, 55);
        m.updateLocalState(0.55, s -> {});                               // float edge: ceil(0.55*100) == 56
        System.out.println("EDGE fail55 ratio0.55 state=" + m.state());
        m.updateLocalState(0.80, s -> {});
        run("fail80", 70, 80);
    }
    @Test public void probeDisabled() throws Throwable { run("disabled", -1, -1); }
}
```

2. Build the test classes with the new file: `cd $W/src && ant build-test`. Then
   `rm -f build/test/probe-*.tsv`.
3. Run each method in its own JVM. `CQLTester` empties `build/test/cassandra/` at class start, so
   each method starts from an empty data directory:

```
ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.DiskUsageCapProbeTest -Dtest.methods=probeFail50 -Dno-build-test=true
ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.DiskUsageCapProbeTest -Dtest.methods=probeFail80 -Dno-build-test=true
ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.DiskUsageCapProbeTest -Dtest.methods=probeDisabled -Dno-build-test=true
```

   (`-Dno-build-test=true` is honoured by `testsome`, `build.xml:1002-1008`, `1382`; drop it to
   rebuild if the test file is edited.) The forked JUnit JVM runs in `$W/src`, so the relative
   path `build/test/probe-*.tsv` and the test yaml's `build/test/cassandra/data` resolve there.
4. Collect the results with `grep -h '^\(PROBE\|BYPASS\|EDGE\|#\)' build/test/probe-*.tsv build/test/output/TEST-*DiskUsageCapProbeTest*`.
5. For each method, record:
   - `i*`, the first rejected row;
   - `value` and `used_bytes` at row `i*−1`;
   - the final `used_bytes` after the loop;
   - the count of `ACCEPT`.

**B2f. Predictions** (stated before any run; `U = used0/MiB` and `M` from the `#` header line).
- **`probeFail80`.**
  - The boundary asserts hold.
  - The `EDGE` line prints `state=FULL` (`ceil(0.55·100)=56 > 55`).
  - All rows are accepted while the logged `value ≤ 80`.
  - `state` becomes `FULL` on the first row where `used_bytes > 0.80·M·MiB`.
  - Every later plain insert is `REJECT`.
  - Accepted rows ≈ `0.80·M − U` (within ±3 rows, which covers memtable/sstable component overhead).
  - Final `used_bytes ≤ 0.80·M·MiB + 2 MiB`.
  - The rejected inserts add 0 bytes, so `used_bytes` stays flat (±1 MiB) across all `REJECT` rows.
- **`probeFail50`.** As above with 50: accepted ≈ `0.50·M − U` (±3), and final `used_bytes ≤ 0.50·M·MiB + 2 MiB`.
- **Relation between them:** `accepted(80) − accepted(50) ≈ 0.30·M` (±5 rows).
- **`probeDisabled`.** All `N` rows `ACCEPT`, `state = NOT_AVAILABLE`, and the final
  `used_bytes ≈ used0 + N MiB`, which is `> 0.95·M·MiB`. `value` goes past 80.
- **Bypass lines** (both capped methods):
  - `user-LWT ACCEPT`, `super ACCEPT` and `system ACCEPT`: these paths are not checked.
  - `user-batch REJECT`.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Rejections begin on the first row after `value` first exceeds `F`; `used_bytes` then flat; accepted count ≈ `F/100·M − U` for both F | Claim confirmed at unit level: the given line decides `FULL`, and `FULL` stops user writes at the threshold |
| `probeDisabled` grows past `0.95·M` while the capped runs stop near `F%` | Positive control moved: the workload moves usage, and the cap is what stops it |
| Inserts still `ACCEPT` with logged `value > F` and `state=FULL` | **Claim wrong**: `FULL` does not reach the write path (enforcement broken) |
| `state` stays `SPACIOUS`/`STUFFED` with `value > F` | **Claim wrong** at the given line or in `getState` |
| Rejections start while `value ≤ F` (other than the 55-edge) | The comparison is not strict `>` as traced; amend A3 |
| `accepted(80) ≈ accepted(50)` | Usage does not follow the knob; claim refuted |
| `probeDisabled` stops below `0.95·M` or never passes `F` | Workload or arithmetic wrong; not confirmed, so fix `M` or the row size |
| `user-LWT REJECT` | The LWT bypass in A3 is wrong; amend A3 |
| `user-batch ACCEPT` | The batch check in A3 is wrong |
| `EDGE … state=STUFFED` | The floating-point edge does not occur; amend A3 (no effect on the claim) |

**B2h. Controls.**
- **Positive control:** `probeDisabled`, the same workload with no cap.
- **Two thresholds:** these separate "the stopping point follows `F`" from "something else stops
  the writes at a fixed size".
- **Exception filter:** only `GuardrailViolatedException` with the disk-usage message counts as
  `REJECT`. Any other exception fails the test, which rules out timeouts or OOM.
- **Clean start:** `CQLTester` cleans the data directories, so `used0` is small and measured, not
  assumed.
- **Fixed denominator:** `M` fixes `total`, so other activity on the host's file system cannot move
  the ratio.
- **Synchronous `updateLocalState`:** this removes scheduling lag, so a lag-free stop isolates the
  check itself. B3 measures the lag.

### B3. Cluster tier

A single real node (a second node is optional, see B3c) built from the tag, with real disk usage
driven by a client to the boundary.

**B3a. Environment and build.**
- **Build:** the same local copy `$W/src` as B2 (`ant jar` is enough if B2 was not run). JDK 11;
  `python3` 3.8–3.11 for `cqlsh`.
- **Layout:** all node data stays under `$CASSANDRA_HOME/data` = `$W/src/data/`, which is local
  disk. The data directory is `$W/src/data/data`; the commit log, hints and saved caches are in
  sibling directories, so they are not counted in `used`.
- **Ports** (chosen to avoid other users on a shared host; check them with `ss -ltn` first):
  native 19158, storage 17158, JMX 17159.
- **Configuration edits** (`cd $W/src`):

```
sed -i -e 's/^authenticator: AllowAllAuthenticator/authenticator: PasswordAuthenticator/' \
       -e 's/^native_transport_port: 9042/native_transport_port: 19158/' \
       -e 's/^storage_port: 7000/storage_port: 17158/' \
       -e 's/seeds: "127.0.0.1:7000"/seeds: "127.0.0.1:17158"/' \
       -e 's/^# data_disk_usage_max_disk_size:$/data_disk_usage_max_disk_size: 2048MiB/' \
       -e 's/^# data_disk_usage_percentage_warn_threshold: -1/data_disk_usage_percentage_warn_threshold: WARN_PH/' \
       -e 's/^# data_disk_usage_percentage_fail_threshold: -1/data_disk_usage_percentage_fail_threshold: FAIL_PH/' conf/cassandra.yaml
sed -i 's/^JMX_PORT="7199"/JMX_PORT="17159"/' conf/cassandra-env.sh
cp conf/cassandra.yaml conf/cassandra.yaml.tmpl
```

- The seed line must follow the storage port (`conf/cassandra.yaml:706`); otherwise the node is not
  its own seed and start-up stops with "Unable to contact any seeds" (`StorageService.java:2235`).
- `authorizer` stays `AllowAllAuthorizer` (`conf/cassandra.yaml:217`), so the ordinary role
  `stress` needs no GRANTs to create and write `keyspace1`.
- **JVM:** `export MAX_HEAP_SIZE=2G; unset HEAP_NEWSIZE` (G1 is the JDK 11 default,
  `conf/jvm11-server.options:63`, and ignores `HEAP_NEWSIZE`, `conf/cassandra-env.sh:126-136`), so
  the memtable space defaults to 512 MiB.
  For the interval variant only: `export JVM_EXTRA_OPTS="-Dcassandra.disk_usage.monitor_interval_ms=1000"` (appended to the JVM options at `conf/cassandra-env.sh:307`).

**B3b. Knobs.**

| Run | warn / fail | Monitor interval | Authenticator | Purpose |
|---|---|---|---|---|
| C50 | 40 / 50 | 30 s (default) | Password | cap at 1024 MiB |
| C80 | 70 / 80 | 30 s | Password | cap at 1638 MiB, so the stop point moves with F |
| C50-fast | 40 / 50 | 1 s | Password | overshoot shrinks with the interval |
| CDIS | -1 / -1 | 30 s | Password | **positive control**: no cap |
| CALLOW | 40 / 50 | 30 s | AllowAll (yaml line left at `AllowAllAuthenticator`, no login) | shows that all clients count as superusers, so no cap |

- `data_disk_usage_max_disk_size: 2048MiB` in all runs, so `total = 2048 MiB` whatever the host's
  disk.
- Each run uses a fresh node: wipe `$W/src/data`, then render the yaml template with
  `sed -e "s/WARN_PH/$WARN/" -e "s/FAIL_PH/$FAIL/" conf/cassandra.yaml.tmpl > conf/cassandra.yaml`.
  The thresholds can also be changed live with
  `bin/nodetool -p 17159 -u cassandra -pw cassandra setguardrailsconfig data_disk_usage_percentage_threshold <fail> <warn>`;
  it is not needed here.

**B3c. Workload.**
- **Tool:** `cassandra-stress` from the same build, run as the ordinary role `stress`:
  - one 1024-byte column per row (`-col n=FIXED(1) size=FIXED(1024)`), no compression (the stress
    default);
  - SimpleStrategy RF 1;
  - throttled to 4000 rows/s with 16 threads, about 4.1–4.4 MiB/s of data;
  - `n=2600000` rows, about 2.6–2.8 GiB attempted. That is above 0.8 × 2048 MiB = 1638 MiB, so
    both thresholds are crossed with margin, in about 11 min.
- **Errors:** `-errors ignore retries=0`, so rejected writes are counted and stress keeps going.
- **Autocompaction:** disabled on the stress table after the schema exists. This keeps compaction
  temporaries out of the reading; they are a known separate consumer (A4).
- **LWT probe after FULL:** 200 single-statement `INSERT … IF NOT EXISTS` with 64 KiB text values
  (12.5 MiB) as `stress`, then one plain insert as `stress`, then one plain insert as `cassandra`.
- **Optional second node:** this verifies the gossip path. Add node 2 with the same yaml (seeds =
  node 1) and RF 2; expect rejection on both coordinators when either node is `FULL`. It is not
  needed for the claim.

**B3d. Observables and instruments.**
- **Sampler**, every 5 s, to `$W/samples-<run>.csv`:
  - `date +%s`;
  - `du -sb $W/src/data/data`. This is the apparent size, the same measure as `folderSize`.
  - the sum of `Memtable data size` from `bin/nodetool -p 17159 -u cassandra -pw cassandra tablestats keyspace1.standard1`;
  - `nodetool … gossipinfo | grep DISK_USAGE`, which gives the `SPACIOUS`/`STUFFED`/`FULL` state.
- **Client side:** the stress log (`-log interval=5s file=$W/stress-<run>.log`) gives op rate and
  total, and the error count from stderr (`grep -c "disk usage exceeds failure threshold"`).
- **Server log:** `$W/src/logs/system.log`, line `Guardrail local_data_disk_usage violated: … will stop accepting writes`
  (once, because it is rate-limited).
- **End state:** `nodetool flush` then `du -sb` once more, which puts the memtable on disk.
- **Not observable directly:** the exact instant of each 30 s evaluation. It is inferred from the
  gossip state change in the 5 s samples.

**B3e. Procedure** (per run; `WARN`, `FAIL` and the optional `JVM_EXTRA_OPTS` set from B3b).
1. Run `pkill -f "CassandraDaemon" -u $USER` only if a previous run of yours left one. Then
   `rm -rf $W/src/data $W/src/logs` and render the yaml (B3b). For CALLOW, also run
   `sed -i 's/^authenticator: PasswordAuthenticator/authenticator: AllowAllAuthenticator/' conf/cassandra.yaml`.
2. Start the node and wait for it:
   `bin/cassandra -p $W/cassandra.pid > $W/start-<run>.out 2>&1`, then
   `until bin/nodetool -p 17159 status 2>/dev/null | grep -q '^UN'; do sleep 2; done`
   (nodetool JMX has no auth by default).
3. Create the role and the LWT table. Wait about 15 s for the default `cassandra` superuser to
   exist, then:

```
CQL="bin/cqlsh 127.0.0.1 19158 -u cassandra -p cassandra"   # CALLOW: bin/cqlsh 127.0.0.1 19158
$CQL -e "CREATE ROLE stress WITH PASSWORD='stress' AND LOGIN=true AND SUPERUSER=false;
         CREATE KEYSPACE cap WITH replication={'class':'SimpleStrategy','replication_factor':1};
         CREATE TABLE cap.t (k int PRIMARY KEY, v text) WITH compression={'enabled':'false'};"
```

4. Create the schema with a tiny stress run as `stress` (CALLOW: drop `user=… password=…`), then
   disable autocompaction:

```
S="tools/bin/cassandra-stress write cl=ONE -col n=FIXED(1) size=FIXED(1024) -schema replication(strategy=SimpleStrategy,factor=1) -mode native cql3 user=stress password=stress -node 127.0.0.1 -port native=19158 jmx=17159"
$S n=1000 -rate threads=1
bin/nodetool -p 17159 disableautocompaction keyspace1 standard1 && bin/nodetool -p 17159 flush
```

5. Start the sampler in the background, writing to `$W/samples-<run>.csv`:
   `while kill -0 $(cat $W/cassandra.pid) 2>/dev/null; do echo "$(date +%s),$(du -sb $W/src/data/data|cut -f1),$(bin/nodetool -p 17159 tablestats keyspace1.standard1 | awk '/Memtable data size/{s+=$NF} END{print s}'),$(bin/nodetool -p 17159 gossipinfo | grep -o 'DISK_USAGE:[^ ]*')"; sleep 5; done >> $W/samples-<run>.csv &`
6. Run the main load:
   `$S n=2600000 -rate threads=16 throttle=4000/s -errors ignore retries=0 -log interval=5s file=$W/stress-<run>.log 2> $W/stress-<run>.err`.
7. When stress ends, record the gossip state. For the capped runs, generate the LWT file and run
   it as `stress`, then try the two plain inserts:
   - `python3 -c "v='a'*65536; [print(f\"INSERT INTO cap.t (k,v) VALUES ({i},'{v}') IF NOT EXISTS;\") for i in range(200)]" > $W/lwt.cql`
   - `bin/cqlsh 127.0.0.1 19158 -u stress -p stress -f $W/lwt.cql > $W/lwt-<run>.out 2>&1; echo rc=$?`
   - `bin/cqlsh 127.0.0.1 19158 -u stress -p stress -e "INSERT INTO cap.t (k,v) VALUES (100001,'x');"`, expected to be rejected.
   - `$CQL -e "INSERT INTO cap.t (k,v) VALUES (100002,'x');"` as the superuser, expected to be accepted.
   - `$CQL -e "SELECT count(*) FROM cap.t;"`.
8. Run `bin/nodetool -p 17159 flush`, wait 10 s, and take a final `du -sb $W/src/data/data`. Then
   run `du -sb $W/src/data/data/cap`.
9. Stop the node with `bin/nodetool -p 17159 stopdaemon || kill $(cat $W/cassandra.pid)`. Confirm
   with `pgrep -u $USER -f CassandraDaemon` (no output) and `pgrep -u $USER -f cassandra-stress`
   (no output). The sampler loop exits on its own.
10. Save the run's files and repeat for the next run.

**B3f. Predictions** (`total = 2048 MiB`; write rate `R ≈ 4.3 MiB/s`; `T` = monitor interval).
- **C50.**
  - Gossip shows `STUFFED` after `du + memtable > 819 MiB` (40%), then `FULL` after the counted sum
    first exceeds 1024 MiB, within ≤ T + 5 s of the sample where it crosses.
  - From then on, essentially every stress op fails with "disk usage exceeds failure threshold",
    and the error rate ≈ the throttle.
  - Final `du` after flush ∈ [1024 MiB, 1024 + R·T + 64 MiB] ≈ [1024, 1220] MiB. That is far below
    the ≈ 2700 MiB attempted.
  - Accepted rows ≈ 0.95–1.15 M of 2.6 M.
- **C80.** Same shape at 1638 MiB. Final `du` ∈ [1638, 1835] MiB. The stopping point is about
  614 MiB (±130) higher than C50's.
- **C50-fast (T = 1 s).** Final `du` ∈ [1024, 1024 + 4.3 + 64] ≈ [1024, 1095] MiB. Overshoot above
  1024 MiB is smaller than C50's by about `R·(30−1) s` ≈ 125 MiB (allow ±40 MiB).
- **CDIS (positive control).** Gossip shows `NOT_AVAILABLE` (or no `DISK_USAGE` value), there are
  0 errors, and final `du` ≈ 2.6–2.9 GiB, which follows the attempted volume.
- **CALLOW.** The node turns `FULL` (gossip and log show it), but 0 stress errors, and final `du`
  ≈ CDIS.
- **LWT probe (C50/C80).**
  - All 200 LWT inserts are applied (`[applied] True`, count = 200), and `du …/cap` grows by about
    12.5 MiB after flush.
  - The plain `stress` insert fails with "Write request failed because disk usage exceeds failure
    threshold".
  - The superuser insert succeeds.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| C50 and C80 stop within their predicted bands, with stop points about 614 MiB apart; CDIS reaches about 2.7 GiB | **Claim confirmed**: data-directory usage follows `F`, with bounded overshoot |
| C50-fast overshoot smaller than C50's by roughly `R·29 s` | Overshoot is the monitor lag, as traced |
| C50/C80 `du` keeps rising to about the attempted volume with `FULL` in gossip | **Claim wrong**: the `FULL` state does not stop writes |
| No `FULL` while `du + memtable > F%·2048 MiB` for more than T + 10 s | **Claim wrong** at the given line or the monitor (or `total` is not as traced) |
| Stop points of C50 and C80 equal | Usage does not follow the knob; claim refuted |
| CDIS stops early or never passes 1638 MiB | Positive control did not move; not confirmed, so check stress or the disk |
| Final `du` exceeds the upper band by more than about 100 MiB in a capped run | Extra consumers (compaction, snapshots) or extra lag; investigate before concluding |
| CALLOW rejects writes | `isSuper()` under AllowAll is not as traced; amend A3 step 6 |
| LWT inserts rejected | The LWT bypass is wrong; amend A3 step 7 |

**B3h. Controls.**
- **CDIS** is the positive control: the same workload, with usage moving where no cap binds.
- **Two fail values plus the interval variant:** the stop point must move with `F` and the
  overshoot with `T`.
- **Fixed `total`:** `data_disk_usage_max_disk_size` fixes it, so other tenants of `/mydata` cannot
  change the ratio. The commit log and hints are outside the data directory, so they do not inflate
  `used`.
- **Autocompaction disabled:** compaction temporaries cannot cause or hide a plateau.
- **Error filter:** only errors carrying the guardrail message count. Timeouts or overload errors
  would show a different message.
- **Gossip state sampled alongside `du`:** this ties each rejection to the `FULL` decision.
- **Fresh data directory per run:** no carry-over.

**B4. Risks and cleanup.**
- **Disk:** at most about 3 GiB of node data per run, plus up to about 1 GiB of commit log
  segments (outside the data directory, recycled after flushes), plus about 2 GiB for the build, all under
  `$W` on local `/mydata`. Nothing is written to shared or NFS storage, and no file is added to
  `~/cassandra-5.0.9` or to the repository.
- **Processes:** the node (pidfile `$W/cassandra.pid`), stress and the sampler loop. After each
  run, step 9's `pgrep` checks must print nothing. If something is left, run
  `kill $(cat $W/cassandra.pid)` and `pkill -u $USER -f cassandra-stress`. The unit tier's test JVM
  exits with ant.
- **Ports:** non-default (19158/17158/17159). Check them with `ss -ltn` first, and if one is taken,
  move all three consistently.
- **Final cleanup:** copy the `samples-*`, `stress-*`, `lwt-*` and `src/build/test/probe-*.tsv`
  files out, then `rm -rf $W`.

## C. Sources read

- src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java
- src/java/org/apache/cassandra/db/guardrails/Threshold.java
- src/java/org/apache/cassandra/db/guardrails/PercentageThreshold.java
- src/java/org/apache/cassandra/db/guardrails/Guardrail.java
- src/java/org/apache/cassandra/db/guardrails/Predicates.java
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java
- src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/GuardrailsOptions.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java
- src/java/org/apache/cassandra/service/disk/usage/DiskUsageBroadcaster.java
- src/java/org/apache/cassandra/service/StorageService.java (line 1236)
- src/java/org/apache/cassandra/service/ClientState.java
- src/java/org/apache/cassandra/auth/AuthenticatedUser.java
- src/java/org/apache/cassandra/gms/Gossiper.java (addLocalApplicationStateInternal)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java
- src/java/org/apache/cassandra/cql3/statements/BatchStatement.java
- src/java/org/apache/cassandra/db/Directories.java (getRawSize)
- src/java/org/apache/cassandra/io/util/FileUtils.java (folderSize)
- src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java
- src/java/org/apache/cassandra/cql3/{Sets,Maps,Lists,UpdateParameters,CQL3Type}.java, restrictions/*, SelectStatement.java, index/sai/plan/QueryController.java, io/sstable/format/SortedTableWriter.java (call sites of the other MaxThreshold guardrails, from grep only)
- tools/stress/src/org/apache/cassandra/stress/settings/{SettingsErrors,SettingsMode,SettingsRate,SettingsSchema,SettingsColumn}.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailDiskUsageTest.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java, test/unit/org/apache/cassandra/ServerTestUtils.java (grep)
- test/distributed/org/apache/cassandra/distributed/test/guardrails/GuardrailDiskUsageTest.java
- test/conf/cassandra.yaml
- conf/cassandra.yaml, conf/cassandra-env.sh, conf/jvm11-server.options, bin/cassandra, bin/cassandra.in.sh
- tools/stress/src/org/apache/cassandra/stress/settings/SettingsPort.java, tools/stress/src/org/apache/cassandra/stress/Operation.java (retries semantics)
- build.xml (testsome target, no-build-test, junit fork)
- CHANGES.txt
- https://issues.apache.org/jira/browse/CASSANDRA-17150 (cited from CHANGES.txt, not fetched)
- https://issues.apache.org/jira/browse/CASSANDRA-20787 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

none yet
