# prepared_statements_cache_size — verification solution  <!-- file: cases/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`QueryProcessor.java:954`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L954) (`value.pstmntSize < 0`, in the cache weigher) and `src/java/org/apache/cassandra/cql3/QueryProcessor.java:122#1` (`count > 0`, the once-a-minute "discarded because cache limit reached" warning). Both targets serve the same constraint, so this one file covers both |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string not available), 2026-10-26; stage-3 autonomous, Band D triage |
| Estimate | `positive`. The prepared-statement cache is a Caffeine cache bounded by `maximumWeight(prepared_statements_cache_size in bytes)`, and each entry weighs `key.size() + pstmntSize`, where `pstmntSize` is a jamm `measureDeep` of the `Prepared` object. Because `measureDeep` also counts shared objects and the same `Prepared` is stored under two keys, the weights overstate what is actually retained, so the real heap the cache holds should stay at or below the cap |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `prepared_statements_cache_size`, a configuration entry.
- Declared at [`Config.java:584-585`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L584-L585): `DataStorageSpec.LongMebibytesBound prepared_statements_cache_size = null`. The old name `prepared_statements_cache_size_mb` is still accepted (`@Replaces`).
- Unit: MiB (`conf/cassandra.yaml:505-508`, "Min unit: MiB").
- Default: `null`, meaning "auto", which resolves to `max(10, maxHeapMiB / 256)` at [`DatabaseDescriptor.java:795-798`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L795-L798). A value of 0 is rejected (`DatabaseDescriptor.java:800-801, 806-810`). The resolved value is read back through `DatabaseDescriptor.getPreparedStatementsCacheSizeMiB()` ([`DatabaseDescriptor.java:4178`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L4178)).
- How to set it: the yaml key in `cassandra.yaml`. There is no JMX setter. The byte value is captured once in a static field, `QueryProcessor.PREPARED_STATEMENT_CACHE_SIZE_BYTES` ([`QueryProcessor.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L107)), when the class initializes, and is passed to `maximumWeight` ([`QueryProcessor.java:115`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L115)). A change therefore needs a restart.
- The unit-test config already sets it: `test/conf/cassandra.yaml:48` is `prepared_statements_cache_size: 1MiB`.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap. Specifically, the total *weight* of entries in the
`QueryProcessor.preparedStatements` Caffeine cache, where weight =
`MD5Digest.size()` (16) + `Prepared.pstmntSize` (`QueryProcessor.java:952-958`).
`pstmntSize` is `ObjectSizes.measureDeep(prepared)` (`QueryProcessor.java:947-950`), computed
once when the statement is parsed (`QueryProcessor.java:468-469`). It starts at -1
(`src/java/org/apache/cassandra/cql3/QueryHandler.java:63`).

**A3. Mechanism.**
1. Cache construction ([`QueryProcessor.java:113-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L113-L118)): `Caffeine.newBuilder().executor(ImmediateExecutor.INSTANCE).maximumWeight(PREPARED_STATEMENT_CACHE_SIZE_BYTES).weigher(QueryProcessor::getSizeOfPreparedStatementForCache).removalListener(...)`.
2. Weigher (target `:954#1`): if `pstmntSize < 0`, the size was never computed, and the weigher throws `IllegalStateException` ([`QueryProcessor.java:954-955`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L954-L955)). Otherwise it returns `key.size() + pstmntSize` (`:957`). Every path that inserts into the cache goes through `parseAndPrepare(..., measure=true)`: client prepare ([`QueryProcessor.java:754`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L754), which calls the three-argument overload at `:436-439`, which sets `measure=true`), and preload (`:181`). So in practice the throwing branch only fires if a non-measured `Prepared` is put into the cache. That is a guard against a programming error, not a limit.
3. Per-statement rejection: `storePreparedStatement` throws `InvalidRequestException` when a single statement's weight is larger than the whole cap ([`QueryProcessor.java:825-829`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L825-L829)). Otherwise `preparedStatements.get(id, ...)` inserts it (`:831`) and the statement is also persisted to `system.prepared_statements` (`:832-833`).
4. Eviction: when the total weight is over `maximumWeight`, Caffeine evicts entries (by W-TinyLFU, so the newly added candidate may be the one evicted). Maintenance runs on the caller thread because of `ImmediateExecutor`. The removal listener `evictPreparedStatement` ([`QueryProcessor.java:132-140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L132-L140)) handles causes where `wasEvicted()` is true: it increments `metrics.preparedStatementsEvicted`, increments `lastMinuteEvictionsCount`, and deletes the row from `system.prepared_statements`.
5. Warning (target `:122#1`): a task runs every minute ([`QueryProcessor.java:120-126`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L120-L126)). It reads and resets `lastMinuteEvictionsCount` and, if the count is above 0, logs `WARN "<n> prepared statements discarded in the last minute because cache limit reached (<cap> MiB)"`. This check only reports evictions and does not enforce anything. It is a log-visible sign that the cap is binding.
6. Overshoot and bypass paths:
   - Caffeine evicts on an amortized schedule, so the total can exceed the cap for a short time (by roughly one write-buffer drain).
   - Startup preload ([`QueryProcessor.java:171-200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L171-L200)) stops early only after loading more than 110% of the cap ([`SystemKeyspace.java:1904-1922`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L1904-L1922)). Eviction still applies during the load.
   - `pstmntSize` is measured once and never re-measured.
   - The weights overstate retained memory. `measureDeep` counts everything reachable from the object, including shared objects such as table metadata ([`ObjectSizes.java:225-233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/ObjectSizes.java#L225-L233)). Also, one `Prepared` instance is stored under two ids, with and without keyspace ([`QueryProcessor.java:761-779`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L761-L779)), and each id carries the full weight.

**A4. Other consumers.**
- `internalStatements` is an unbounded `ConcurrentHashMap` for internally prepared statements (`QueryProcessor.java:97, 425-433`). The cap does not cover it.
- `system.prepared_statements` on disk receives one write per newly cached statement plus a delete per eviction (`QueryProcessor.java:833, 138`). The cap does not bound this disk usage directly.
- Client-side driver caches (outside the node).
- The rest of the heap: memtables, key cache and so on.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/cql3/PstmtPersistenceTest.java:348-400` (`testPreloadPreparedStatementsUntilCacheFull`) and its eviction counting (`:403-405`).
- CASSANDRA-19703 (prepared statement cache leak) and CASSANDRA-19986 (precomputed size), both cited in comments at `SystemKeyspace.java:1915-1921` and `QueryHandler.java:62`: https://issues.apache.org/jira/browse/CASSANDRA-19703, https://issues.apache.org/jira/browse/CASSANDRA-19986.
- Caffeine size-based eviction docs: https://github.com/ben-manes/caffeine/wiki/Eviction.

## B. Verification solution

**B1. Claim under test.** With `prepared_statements_cache_size = C`, preparing many
distinct statements keeps (unit) the sum of `16 + pstmntSize` over resident cache
entries at or below `C`, give or take at most one entry, and (cluster) the heap the
cache retains after a full GC at or below `C`, while evictions grow as `N − resident`. With a cap large
enough not to bind, the same workload grows retained heap roughly linearly in `N`.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Clone the tag to local disk:
`git clone --branch cassandra-5.0.9 --depth 1 <shared clone path> /local/$USER/c509 && cd /local/$USER/c509 && ant build-test`.
Tests run with the jamm agent that `build.xml` adds (`build.xml:1159`). Without it, `measureDeep` would not work.

**Amendment 2026-10-26 (step-0 audit) — B2a, this host.** Clone `C=$W/cassandra-run30` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $C`, HEAD `b5f2a54210`), built with `source $W/env.sh; cd $C && ant -Dlocal.repository=$W/m2 build-test` (macOS 27 arm64, JDK 11.0.32.1, Ant 1.10.18; every `ant` call passes `-Dlocal.repository=$W/m2`). `/local/$USER/c509` reads `$C`; `/local/$USER/probe-*.log` reads `$W/logs/<stem>/unit/`. Reason: B2a's Linux paths and network clone do not exist on this host.

**B2b. Knobs.** `prepared_statements_cache_size` in the **local clone's**
`test/conf/cassandra.yaml:48`. Use `1MiB` (the shipped test value) and `4MiB`.
Optionally also `64MiB` as the non-binding control (see B2h). Set the value by editing
that line before each run. The cap is fixed at class initialization, so each value
needs a separate JVM, which happens automatically because each `ant testsome` run
starts a new JVM.

**Amendment 2026-10-26 (step-0 audit) — B2b, the default added; the 64 MiB control made required.** Values, in this order: `1MiB`, `4MiB`, auto (the line deleted), `64MiB`. Auto resolves to `max(10, ⌊maxMemory/2^20/256⌋)` (`DatabaseDescriptor.java:795-798`) = 10 MiB in the `testsome` JVM (`maxmemory="1024m"`, `build.xml:1153`); the test prints `cap`, so the resolved value is read back in every JVM. `64MiB` is run, not optional (B2e step 3 already runs it). Reason: group A asks for at least three values including the default.

**B2c. Workload.** Create the file `test/unit/org/apache/cassandra/cql3/PreparedCacheCapProbeTest.java` in the local clone:

```java
package org.apache.cassandra.cql3;

import java.util.Map;
import org.junit.Test;
import org.apache.cassandra.service.ClientState;
import org.apache.cassandra.utils.MD5Digest;

public class PreparedCacheCapProbeTest extends CQLTester
{
    @Test
    public void probe() throws Throwable
    {
        StringBuilder cols = new StringBuilder();
        for (int i = 0; i < 20; i++) cols.append(", v").append(i).append(" text");
        createTable("CREATE TABLE %s (k int, c int" + cols + ", PRIMARY KEY (k, c))");
        QueryProcessor.clearPreparedStatements(true);           // EXPLICIT removals, not counted as evictions
        long cap = QueryProcessor.PREPARED_STATEMENT_CACHE_SIZE_BYTES;
        long ev0 = QueryProcessor.metrics.preparedStatementsEvicted.getCount();
        int n = Integer.getInteger("probe.n", 3000);
        ClientState cs = ClientState.forInternalCalls();        // raw keyspace null -> one cache id per statement
        long maxW = 0;
        for (int i = 1; i <= n; i++)
        {
            String q = String.format("SELECT * FROM %s.%s WHERE k = ? AND c = %d", keyspace(), currentTable(), i);
            QueryProcessor.instance.prepare(q, cs);
            if (i % 100 == 0 || i == n)
            {
                long sum = 0; int cnt = 0;
                for (Map.Entry<MD5Digest, QueryHandler.Prepared> e : QueryProcessor.instance.getPreparedStatements().entrySet())
                {
                    long w = e.getKey().size() + e.getValue().pstmntSize;
                    sum += w; cnt++; maxW = Math.max(maxW, w);
                }
                System.out.printf("PROBE i=%d cap=%d resident=%d sumWeight=%d maxW=%d evicted=%d%n",
                                  i, cap, cnt, sum, maxW,
                                  QueryProcessor.metrics.preparedStatementsEvicted.getCount() - ev0);
            }
        }
    }
}
```

Arithmetic: `C = 1 MiB = 1,048,576 B`. Any per-statement weight of 1 KiB or more,
which is certain because a `SelectStatement` graph plus a query string of about
70 characters is already more than 1 KiB, means at most about 1,000 entries fit.
`n = 3000` is therefore at least 3× past the limit for `C = 1 MiB`, and with
`C = 4 MiB` it is past the limit whenever the mean weight is above about 1.4 KiB. If
`resident == n` at 4 MiB, rerun with `-Dprobe.n=20000`.

**Amendment 2026-10-26 (step-0 audit) — B2c, one write per reading and how `n` is passed.** The probe's text is kept verbatim at `harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/PreparedCacheCapProbeTest.java` except one line: `System.out.printf("PROBE …%n", …)` becomes `System.out.println(String.format("PROBE …", …))` with the same format string and arguments (the test JVM logs each `System.out` write as its own log line, and `printf` writes a line in several pieces). `-Dprobe.n=<n>` reaches the forked test JVM only through `-Dtest.jvm.args="-Dprobe.n=<n>"` (`build.xml:94, 1192`). The rerun rule applies to auto as well as 4 MiB: if `resident == n` at the end at 4 MiB or auto, that value is rerun with `n = 20000`. Reason: the readings must be one line each to be read; a plain `-D` on the `ant` command line does not reach the test JVM.

**B2d. Observables and instruments.** The `PROBE` lines in the test output
(`build/test/output/TEST-org.apache.cassandra.cql3.PreparedCacheCapProbeTest.xml`
or the console). These give `sumWeight` (the check's own operand, summed), `resident`,
`maxW` and `evicted`. Not directly observable: Caffeine's internal `weightedSize`.
The sum computed by the test is the same quantity, because the weigher is deterministic.

**Amendment 2026-10-26 (step-0 audit) — B2d, where the lines are.** The `PROBE` lines are read from `$C/build/test/logs/**/TEST-org.apache.cassandra.cql3.PreparedCacheCapProbeTest.log` (and the `system-out` of `$C/build/test/output/TEST-org.apache.cassandra.cql3.PreparedCacheCapProbeTest.xml`), copied to the log folder after each JVM. Reason: on this tree stdout lands in the test log, not only the console.

**B2e. Procedure.**
1. `sed -i 's/^prepared_statements_cache_size:.*/prepared_statements_cache_size: 1MiB/' test/conf/cassandra.yaml`
2. `ant testsome -Dtest.name=org.apache.cassandra.cql3.PreparedCacheCapProbeTest -Dno-build-test=false 2>&1 | tee /local/$USER/probe-1MiB.log`
3. Repeat steps 1 and 2 with `4MiB`, then `64MiB`.
4. `grep PROBE` each log and tabulate.


**Amendment 2026-10-26 (step-0 audit) — B2e, commands on this host.** Step 1 uses BSD `sed`: `sed -i '' 's/^prepared_statements_cache_size:.*/prepared_statements_cache_size: <v>/' test/conf/cassandra.yaml` (auto: `sed -i '' '/^prepared_statements_cache_size:/d' …`); `git checkout -- test/conf/cassandra.yaml` before each value and after the last. Step 2 is `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.PreparedCacheCapProbeTest` **without `-Dno-build-test=false`**: `maybe-build-test` is `unless="no-build-test"` (`build.xml:1013`), and Ant skips an `unless` target when the property is set to any value, `false` included (checked with a two-target build file: with `-Dno-build-test=false` the guarded target did not run), so as written the copied probe would never be compiled. Order: 1 MiB, 4 MiB, auto, 64 MiB. Reason: GNU `sed -i` syntax fails on macOS, and the build flag skips compiling the probe.

**B2f. Predictions.**
- For C = 1 MiB and 4 MiB, at every sample after the first eviction: `sumWeight ≤ cap + maxW`.
- At the end of the run, `resident + evicted == n` (± 0; each statement has exactly one id in this setup).
- `resident(4 MiB) / resident(1 MiB)` should be about 4 (between 3 and 5).
- `evicted > 0` for both.
- For 64 MiB with n = 3000: `evicted = 0` and `sumWeight` grows linearly with `i`.


**Amendment 2026-10-26 (step-0 audit) — B2f, tolerances (prediction unchanged in substance).** Auto (10 MiB) has the same predictions as 1 and 4 MiB, and `resident(auto) / resident(1 MiB)` lies in [7.5, 12.5] (the ±25 % band B2f gives for 4: 3–5). "Grows linearly" at 64 MiB means: `evicted = 0` and `resident = i` at every sample, and `sumWeight / i` varies by at most 5 % across samples. Reason: auto added (B2b); "linearly" had no tolerance.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `sumWeight ≤ cap + maxW` at all samples, evictions > 0, resident scales with C | Mechanism works as traced (claim supported at unit level) |
| `sumWeight` greater than `cap + maxW` at the end of the run (after a full drain) | Claim wrong: the weigher or the eviction does not enforce the cap |
| `evicted == 0` and `resident == n` at 1 MiB | The limit was never reached (workload too small, or weights tiny). Not confirmed; raise n |
| `IllegalStateException("Precomputed prepared statement size not available")` | `:954` branch fired: some insert path skipped measuring. This is a bug in the mechanism, so report it |
| `InvalidRequestException ... larger than allowed maximum` | A single statement is larger than C (`:825`); lower the column count |


**Amendment 2026-10-26 (step-0 audit) — B2g, rows added (the rows above are unchanged).** Row 1 needs B2f at 1 MiB, 4 MiB and auto and the 64 MiB control as predicted. Added rows:

| Observation | Meaning |
|---|---|
| `resident + evicted ≠ n` at the end at a capped value | The eviction counter does not follow the cache. Not confirmed |
| `sumWeight ≤ cap + maxW` and evictions > 0, but a ratio outside its band (`resident(4)/resident(1)` outside 3–5, or `resident(auto)/resident(1)` outside 7.5–12.5) | Usage does not follow the knob in proportion. Not confirmed |
| At 64 MiB: `evicted > 0`, or `resident ≠ i` at a sample, or `sumWeight / i` varies by more than 5 % | The non-binding control failed. Not confirmed (the capped values cannot be told from the workload) |

Reason: group B asks for a row for every plausible outcome, including a counter that does not follow, "flat across values" and a failed control.

**B2h. Controls.** The 64 MiB run is the non-binding control: the same workload
with no evictions shows that `sumWeight` follows the workload when the cap does not
bind. `clearPreparedStatements(true)` at the start removes entries left over from
CQLTester setup. The counter baseline `ev0` removes earlier evictions.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node. Build in the local clone with
`ant jar` (no test classes needed). Use a working directory on local disk with at least 10 GB free,
`W=/local/$USER/pscache` (check with `df -h /local`). In
`conf/cassandra.yaml` of the local clone set:
- `data_file_directories: [$W/data]`
- `commitlog_directory: $W/commitlog`
- `saved_caches_directory: $W/saved_caches`
- `hints_directory: $W/hints`
- `cdc_raw_directory: $W/cdc`
- `listen_address`, `rpc_address` and seeds: `127.0.0.1`
- `prepared_statements_cache_size: <knob>`

Set the heap through the environment: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. Logs
go to `$W/logs` (`export CASSANDRA_LOG_DIR=$W/logs`).

**Amendment 2026-10-26 (step-0 audit) — B3a, this host.** Clone `$W/cassandra-run30` (B2a amendment; `build-test` is a superset of `ant jar`; no `ant` while a node runs from it). Node directory `N=$W/node-pscs` (B3a's `$W/pscache`): `conf/` copied from the clone, `cassandra.yaml` = the shipped file with the directory keys, `listen_address`, `rpc_address` and `prepared_statements_cache_size` removed and re-added at the end (`data_file_directories: [$N/data]`, `commitlog_directory`, `saved_caches_directory`, `hints_directory`, `cdc_raw_directory` under `$N/`, `listen_address: 127.0.0.1`, `rpc_address: 127.0.0.1`; the shipped seed is already `127.0.0.1:7000`). `CASSANDRA_CONF=$N/conf CASSANDRA_LOG_DIR=$N/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`, plus the Byteman agent of the B3d amendment in `JVM_EXTRA_OPTS` (scoped to the `bin/cassandra` command). The node is started as a tracked background `bin/cassandra -f > node.out 2>&1 < /dev/null` (macOS has no `setsid`; `-p` is not used); ready when `nodetool status` shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`; the script fails at once if the daemon dies. Before each lifetime no `CassandraDaemon` runs and ports 7000/7199/9042/9091 are free; `$N` is wiped before and after. Reason: B3a's Linux paths do not exist here.

**B3b. Knobs.** `prepared_statements_cache_size` = `4MiB` and `32MiB`, plus a
non-binding control `C_ctl`. Choose `C_ctl` after the 4 MiB run with this calibration: `w̄ = 4 MiB / resident_at_4MiB` (resident read from
`prepared_statements_count`). Then set `C_ctl = 2 × N_ctl × w̄`, rounded up to a whole
MiB, with `N_ctl = min(N, floor(600 MiB / w̄ / 2))` so that the control's weighted
total stays under about 600 MiB on a 2 GiB heap. Restart the node for each value,
after wiping `$W/data`, `$W/commitlog` and so on, so that the preload starts empty.

**Amendment 2026-10-26 (step-0 audit) — B3b, the default added, read-back, and the control's arithmetic.** Values, in this order: `4MiB`, `32MiB`, auto (the line left empty) = `max(10, ⌊maxMemory/2^20/256⌋)` = 10 MiB at `-Xmx2G` (`DatabaseDescriptor.java:795-798`), then `C_ctl`. Auto has the same predictions as 4 and 32 MiB (B3f amendment). Every started value is read back from the `Initialized prepared statement caches with <n> MiB` line of this start (`QueryProcessor.java:128-129`); a mismatch stops the run. `C_ctl` and `N_ctl` are computed by the harness from the 4 MiB run's final `prepared_statements_count`: `w̄ = 4,194,304 / count`, `N_ctl = min(20000, ⌊629,145,600 / w̄ / 2⌋)`, `C_ctl = ⌈2 × N_ctl × w̄ / 1,048,576⌉` MiB. Reason: group A asks for the default; restart-only knob (A1) needs a read-back.

**B3c. Workload.** Use `prep.py`, run with the driver bundled in the tree:
`PYTHONPATH=/local/$USER/c509/lib/cassandra-driver-internal-only-3.29.0.zip python3 prep.py <N> <outcsv>`.

```python
import sys, time, csv
from cassandra.cluster import Cluster
N = int(sys.argv[1]); out = csv.writer(open(sys.argv[2], 'w'))
s = Cluster(['127.0.0.1'], protocol_version=5).connect()          # no keyspace -> one cache id per statement
s.execute("CREATE KEYSPACE IF NOT EXISTS probe WITH replication = {'class':'SimpleStrategy','replication_factor':1}")
cols = ", ".join("v%d text" % i for i in range(20))
s.execute("CREATE TABLE IF NOT EXISTS probe.wide (k int, c int, %s, PRIMARY KEY (k, c))" % cols)
def metrics():
    return {r.name: r.value for r in s.execute("SELECT name, value FROM system_views.cql_metrics")}
out.writerow(['i', 't', 'count', 'evicted'])
for i in range(1, N + 1):
    s.prepare("SELECT * FROM probe.wide WHERE k = ? AND c = %d" % i)
    if i % 1000 == 0 or i == N:
        m = metrics(); out.writerow([i, time.time(), m['prepared_statements_count'], m['prepared_statements_evicted']])
```

Use `N = 20000` for the 4 MiB and 32 MiB runs and `N_ctl` for the control. If
`w̄ ≥ 1 KiB`, 4 MiB holds at most about 4,000 entries, so N = 20000 is at least 5× past the cap.
The run takes a few minutes. Keep the node up for at least 2 more minutes so that the
minute-tick warning (`:122`) fires.

**Amendment 2026-10-26 (step-0 audit) — B3c, client.** `prep.py` is kept at `harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/prep.py`. The workload is unchanged (keyspace `probe`, table `probe.wide (k int, c int, v0 text … v19 text, PRIMARY KEY (k, c))`, statement i = `SELECT * FROM probe.wide WHERE k = ? AND c = <i>`, no session keyspace, samples of `system_views.cql_metrics` every 1,000 prepares and at the end). Changes: (1) the driver is imported from inside the zip (`<zip>/cassandra-driver-3.29.0/`), because the zip holds the package under that folder and `PYTHONPATH=<zip>` cannot import `cassandra`; (2) `DCAwareRoundRobinPolicy(local_dc='datacenter1')`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0`; (3) a failed prepare is retried up to 5 times on a new session (macOS loopback can drop a connection with `ENOBUFS`), and retries and final failures are counted and printed; (4) the script takes the range of `i` (`load <from> <to>`), so the control's halves use `1 … N_ctl/2` and `N_ctl/2+1 … N_ctl` (B3e step 7) without editing the file, and the schema is created by a separate `schema` call before the baseline (B3e amendment); (5) a `trigger <name>` call executes the instrument query of the B3d amendment. Reason: the driver import as written fails, and the lessons of earlier runs on this host.

**B3d. Observables and instruments.**
- `system_views.cql_metrics` rows `prepared_statements_count` and `prepared_statements_evicted`, sampled every 1,000 prepares by the script.
- Live `QueryHandler$Prepared` instances: `jcmd $PID GC.class_histogram | grep 'cql3.QueryHandler\$Prepared'`. This command forces a full GC first. Take it before the workload and after it.
- Heap after a full GC: `jcmd $PID GC.run; sleep 5; jcmd $PID GC.heap_info`. Record "used" before the workload (baseline) and after it.
- Retained size of the cache, which is the direct measure: `jcmd $PID GC.heap_dump $W/h.hprof`, then in Eclipse MAT (on the same machine, headless: `ParseHeapDump.sh $W/h.hprof org.eclipse.mat.api:suspects` or interactive) find the retained heap of the static `QueryProcessor.preparedStatements` (a `BoundedLocalCache` instance).
- `grep "prepared statements discarded in the last minute" $W/logs/system.log`.
- Not directly observable: Caffeine's weighted size. The ratio `C / count` stands in for the mean weight.


**Amendment 2026-10-26 (step-0 audit) — B3d, the retained size without MAT.** Eclipse MAT is not installed on this host, so the heap dump is not taken. The retained heap of the cache's entries is read as **R = live bytes before − live bytes after clearing the cache in place**: two `jcmd $PID GC.class_histogram` totals (each forces a full GC), with `QueryProcessor.clearPreparedStatements(true)` between them. The clear is done by a Byteman rule (`harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/pscache.btm`, agent `build/lib/jars/byteman-4.0.20.jar` loaded at start with `listener:true`) that fires when the node parses exactly `SELECT key FROM system.local WHERE key = 'stage4-pscache-clear'`; `memoryOnly=true` invalidates every entry with cause EXPLICIT, so no eviction is counted and nothing is deleted from `system.prepared_statements` (`QueryProcessor.java:132-139, 208-213`). A second rule fires on `… WHERE key = 'stage4-pscache-read'` and only prints `PSCACHE` with the cache's entry count (`QueryProcessor.preparedStatementsCount()`, `:147`) and the size of `internalStatements` (`I`, `:97, 215-218`). The rules print to the node's stdout. **R0**, the same two-histogram reading with the clear taken at the baseline (the cache is empty), is the instrument's noise; R is read to ± |R0|. `D = live(32 MiB) − live(4 MiB)` at the end is also recorded, without a prediction. Reason: the case's direct measure needs MAT, which this host lacks; clearing the entries frees exactly what they retain.

**B3e. Procedure.**
1. Clear the directories: `rm -rf $W/{data,commitlog,saved_caches,hints,cdc,logs}; mkdir -p $W/logs`.
2. Set the knob in the yaml. Start the node: `bin/cassandra -p $W/pid`. Wait until `bin/nodetool status` shows `UN`. Set `PID=$(cat $W/pid)`.
3. Take the baseline: class histogram, `GC.run` plus `GC.heap_info`, and a cql_metrics snapshot.
4. Run `prep.py 20000 $W/run-<C>.csv`. Wait 120 s.
5. Take the post-workload class histogram, `GC.run` plus `heap_info`, a heap dump (only for 4 MiB and the control, to save disk), and grep the log.
6. Stop the node with `bin/nodetool stopdaemon`, then confirm with `pgrep -f CassandraDaemon || echo gone`.
7. Repeat for 32 MiB. Then compute `C_ctl` and `N_ctl` from the 4 MiB result and repeat for the control with `prep.py N_ctl`. Add an extra sample: in the control, record heap and histogram at `N_ctl/2` by running the script twice, first with N_ctl/2 and then again (`IF NOT EXISTS` keeps the table), using a different literal range. To do that, edit the range to `range(N_ctl//2+1, N_ctl+1)`.


**Amendment 2026-10-26 (step-0 audit) — B3e, order on this host.** Per lifetime: wipe `$N`, write the yaml, start, read-back, `prep.py schema`, `trigger read` (`I_base`), baseline (`GC.class_histogram`, `GC.run` + 5 s + `GC.heap_info`, one cql_metrics snapshot), R0 (histogram, `trigger clear`, histogram), the load, wait 120 s, `trigger read` (`I_end`, count), final class histogram, `GC.run` + 5 s + `GC.heap_info`, `grep` of the start's `system.log` for the discard warning, then R (histogram, `trigger clear`, histogram, `trigger read`), stop (`nodetool stopdaemon`; if the daemon is still alive after 60 s, `kill`, then `kill -9`), check no `CassandraDaemon` is left, wipe. Order: 4 MiB, 32 MiB, auto, control. The control's half point takes `trigger read`, the class histogram and `GC.run` + `GC.heap_info` (no clear), and R is taken only at its end. No heap dumps (B3d amendment). Reason: the schema is part of the baseline (taken after ingest), the instrument of the B3d amendment, and the restart-only knob.

**B3f. Predictions.**
- **4 MiB and 32 MiB:**
  - Evictions start, and the final `count + evicted = 20000` (± 0).
  - `count(32) / count(4)` is about 8 (between 6 and 10).
  - Live `Prepared` instances ≤ `count` + (baseline instances), where the baseline instances are internal statements.
  - The MAT retained size of the cache is ≤ C.
  - The increase in heap after GC over baseline is ≤ C + 5 MiB. The 5 MiB allows for the driver connection, the schema and the system.prepared_statements memtable.
  - The WARN line appears at least once with `(4 MiB)` / `(32 MiB)`.
- **Control:** `evicted = 0`. `count = N_ctl`. Live `Prepared` instances grow by about `N_ctl`. The heap increase at `N_ctl` is between 1.6× and 2.4× the increase at `N_ctl/2`, which shows the workload moves heap when nothing caps it. No WARN line.


**Amendment 2026-10-26 (step-0 audit) — B3f, exact relations (prediction unchanged in substance).** (1) Auto has the 4 MiB / 32 MiB predictions, with `count(auto)/count(4)` in [1.875, 3.125] (the ±25 % band B3f gives for 8: 6–10). (2) "The MAT retained size of the cache is ≤ C" is read as R ≤ C, with R known to ± |R0|. (3) "Live `Prepared` instances ≤ count + (baseline instances)" is read as `count ≤ Prepared_end ≤ count + I_end`, where `I_end` is the size of `internalStatements` at the end: the baseline instances are internal statements, and the workload itself adds internal statements after the baseline (each first eviction or insert runs `SystemKeyspace.removePreparedStatement`/`writePreparedStatement`, whose `executeInternal` text is prepared into `internalStatements` on first use, `SystemKeyspace.java:1874-1885`, `QueryProcessor.java:425-433`), so the baseline count is not the right comparator. (4) The heap increase (here and in the control's ratio) is the live total of `jcmd $PID GC.class_histogram` (end) − (baseline); `GC.run` + `GC.heap_info` is still taken and recorded as written but not used for a bound, because it failed the harness's known-answer check: in the shakedown (4 MiB, 2,000 statements, 680 entries resident, not a reading of run 1) `used` after `GC.run` + 5 s fell from 63.7 MB at the baseline to 56.0 MB at the end, while the histogram's live total rose by 8.4 MB and R was 3.5 MB (`$W/logs/<stem>/shakedown/cluster/sd-k4/`); the histogram counts only live objects after its own full GC. (5) Control: `evicted = 0` and `count = N_ctl` exactly; "live `Prepared` grows by about `N_ctl`" is read as `N_ctl ≤ Prepared_end − Prepared_base ≤ N_ctl + (I_end − I_base)`. Reason: "about" and the comparator had no exact form. This session knew, before the audit, the readings of the sibling case `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous` (a different file); (3) is derived from the source lines above, and no other bound here is taken from those readings.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Retained cache heap ≤ C, evictions = N − count, count scales with C, control grows linearly | Claim confirmed: the constraint caps the cache's heap |
| Retained cache heap > C (beyond the brief overshoot) at 4 or 32 MiB | Claim wrong: the weights understate real size, or eviction fails |
| Heap increase ≫ C but MAT shows the cache ≤ C | The cap holds for the cache. Growth comes from other consumers (A4: `internalStatements`, memtables). Record which ones |
| `evicted = 0` at 4 MiB | The limit was not reached. Not confirmed; raise N |
| Control heap flat while count grows | The heap instrument is too coarse. Use the MAT retained size instead |


**Amendment 2026-10-26 (step-0 audit) — B3g, the MAT rows read with R, and rows added (the rows above are unchanged).** "Retained cache heap" and "MAT" in the rows above read R (B3d amendment). "Heap increase ≫ C" means heap increase > C + 5 MiB (B3f's allowance). Row 1 needs every B3f prediction except the heap-increase bound at 4 MiB, 32 MiB and auto, and the control as predicted. If row 1 holds and the heap increase exceeds C + 5 MiB, row 3 also applies: the verdict is Confirmed for the cache, and the Effect is "caps only on some paths (bypass)" when the other consumer named from the class histogram grows with the number of distinct statements whatever C is, otherwise "caps". Added rows:

| Observation | Meaning |
|---|---|
| `count + evicted ≠ N` at a capped value | The eviction counter does not follow the cache. Not confirmed |
| Evictions > 0 and R ≤ C, but `count(32)/count(4)` outside 6–10 or `count(auto)/count(4)` outside 1.875–3.125 | Usage does not follow the knob in proportion. Not confirmed |
| `Prepared_end > count + I_end` at a capped value | `Prepared` objects are held outside the cache and the internal map. Not confirmed; record the holder if it can be named |
| No discard WARN line in a capped run with evictions | The minute task did not report. Not confirmed (the prediction lists it) |
| Control: `evicted > 0`, or `count ≠ N_ctl`, or the heap-increase ratio outside 1.6–2.4 | The control failed. Not confirmed |
| The absolute value of R0 larger than C/10 at 4 MiB | R cannot resolve the smallest cap. Not confirmed for the R part |

Reason: group B asks for a row for every plausible outcome; the R instrument needs a resolution row.

**B3h. Controls.**
- The non-binding control (C_ctl) shows that the workload moves heap.
- Wiping the data directories between runs removes preload effects (`QueryProcessor.java:171-200`).
- Connecting without a keyspace avoids double-keyed entries.
- Forced full GC before each heap reading removes garbage.
- Comparing 4 MiB with 32 MiB gives a dose-response check.


**Amendment 2026-10-26 (step-0 audit) — B3h, the noise control.** R0 (B3d amendment) is the control for R: the same two-histogram reading with nothing in the cache. Auto adds a third point to the 4 MiB / 32 MiB dose-response check.

**B4. Risks and cleanup.**
- Never build in the shared clone, and never add the probe test there.
- All node files go under `$W` on local disk. Heap dumps are up to about 2 GB each, so delete them after MAT analysis.
- After each run: `bin/nodetool stopdaemon`, `pgrep -f CassandraDaemon` (kill any leftover), and `pgrep -f "ant|junit"` for unit runs.
- At the end: `rm -rf $W /local/$USER/c509` if no longer needed.


**Amendment 2026-10-26 (step-0 audit) — B4, this host.** Paths are those of the B2a/B3a amendments; no heap dumps are taken; `$N` is wiped after each lifetime; the probe test is removed from `$C` and `test/conf/cassandra.yaml` restored after the unit tier, so the clone's `git status` is clean at the end. The clone is kept (other runs' clones are kept the same way).

## C. Sources read

- src/java/org/apache/cassandra/cql3/QueryProcessor.java (lines 95-200, 236-247, 359-370, 400-475, 686-840, 851-865, 940-1010, 1065-1080)
- src/java/org/apache/cassandra/cql3/QueryHandler.java (50-75)
- src/java/org/apache/cassandra/config/Config.java (584-585)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (790-815, 4178)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (1890-1930)
- src/java/org/apache/cassandra/db/virtual/CQLMetricsTable.java (33-85)
- src/java/org/apache/cassandra/metrics/CQLMetrics.java (33-50)
- src/java/org/apache/cassandra/utils/ObjectSizes.java (225-250)
- conf/cassandra.yaml (505-508), test/conf/cassandra.yaml (48), build.xml (164, 1159)
- test/unit/org/apache/cassandra/cql3/PstmtPersistenceTest.java (outline, 348-405)
- https://github.com/ben-manes/caffeine/wiki/Eviction ; CASSANDRA-19703 ; CASSANDRA-19986 (cited from code comments)

## D. Stage-4 feedback

**2026-10-26, run 1 (Claude Opus 5.5, claude-opus-5-5), advisor's machine** — results: [`../../stage4-runtime-verification/results/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.md`](../../stage4-runtime-verification/results/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.md). Frozen version sha256 `7363f6be…7d2d` (sixteen step-0 amendments of 2026-10-26 above); no runbook fix during run 1; uncommitted. Estimate left as filed (`positive`).

- **Unit: Confirmed — caps** (B2g row 1). Every statement weighs 6,204 B; resident 169 · 676 · 1,690 at 1 · 4 · 10 (auto) MiB, sumWeight never above the cap, evicted = 3,000 − resident; 64 MiB control evicted 0. The `:954` guard never fired.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1 with row 3). The cache's retained heap R (in-place clear, amendment B3d) is 0.879 · 0.929 · 0.913 × C at 4 · 32 · 10 MiB; count 679 · 5,436 · 1,698; one discard WARN per run; uncapped control (236 MiB) retains 109.94 MiB for 20,000 statements. The live heap also grows ≈ 14.2 MiB per 20,000 distinct PREPAREs whatever C is: the `system.prepared_statements` memtable gains one partition per distinct statement (an eviction adds a deletion, it does not remove the partition).
- Runbook defects found at the audit and fixed before the freeze: B2e's `-Dno-build-test=false` skips building the probe (Ant skips an `unless` target when the property is set to any value); B3c's `PYTHONPATH=<zip>` cannot import the bundled driver; MAT is not available on this host.
- For stage 3 (not applied): A4 should name the `system.prepared_statements` memtable as a heap consumer that the knob does not bound; A2's `MD5Digest.size()` is 20 B, not 16.
