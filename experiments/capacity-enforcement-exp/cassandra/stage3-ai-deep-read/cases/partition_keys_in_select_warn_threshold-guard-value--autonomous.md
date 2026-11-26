# partition_keys_in_select_warn_threshold — verification solution  <!-- file: cases/partition_keys_in_select_warn_threshold-guard-value--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the warn comparison of the guardrail, the place closest to a restriction (no place restricts memory or disk, see the notes): [`Threshold.java:141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L141), reached only from [`SelectStatement.java:720-723`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L720-L723) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Code stage-3 autonomous agent, model `claude-opus-5-5` (CLI version not recorded), 2026-11-26 |
| Estimate | `negative`. The warn threshold only decides whether a warning text is logged and returned to the client when an `IN` query names more partition keys than the threshold; the query then runs exactly as it would with the guardrail off, so heap use for the query does not depend on the value. |
| Ground | The only branch the value controls (`Threshold.java:141-142`) calls `triggerWarn` → `Guardrail.warn` (`Guardrail.java:103-117`), which logs, adds one string to `ClientWarn`, traces and emits a diagnostic event, and returns normally; it throws nothing and changes no size, count or capacity. `SelectStatement.getSliceCommands` then builds and runs one read per key (`SelectStatement.java:725-745`) whatever the warn value. Only the sibling **fail** threshold (`Threshold.java:134-137`, a separate case) aborts the query. The warn path adds a constant, small allocation (one message string) and does not cap anything. |

## A. Constraint trace

**A1. The constraint.** `partition_keys_in_select_warn_threshold`, a cassandra.yaml configuration entry
(guardrail), declared as `public volatile int partition_keys_in_select_warn_threshold = -1;` at
[`Config.java:875`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L875).
Unit: a count of partition keys selected by an `IN` restriction on the partition key. Default `-1` (disabled);
the default is the Java field initializer, and `conf/cassandra.yaml:2096-2099` documents it commented out
("The two thresholds default to -1 to disable"). Valid values: `-1`, or `1..Integer.MAX_VALUE`; `0` and other
negatives are rejected, and if both are set, warn must be ≤ fail (`GuardrailsOptions.java:73`, via
`validateMaxIntThreshold` `GuardrailsOptions.java:1123-1128`, `validatePositiveNumeric` `:1092-1109`,
`validateWarnLowerThanFail` `:1176-1184`). Set it by:
- yaml key `partition_keys_in_select_warn_threshold: <n>` (read at startup; change needs a restart);
- JMX at runtime, no restart: MBean `org.apache.cassandra.db:type=Guardrails`
  (`Guardrails.java:50`, registered `:561`), operation `setPartitionKeysInSelectThreshold(int warn, int fail)`
  (`Guardrails.java:904-907` → `GuardrailsOptions.java:216-226`); read with
  `getPartitionKeysInSelectWarnThreshold` (`Guardrails.java:892-895`);
- `nodetool setguardrailsconfig` / `getguardrailsconfig` (`GuardrailsConfigCommand.java:55`, `:172`), which
  call the same MBean. (The setter's help text says "first for failure, second for warning" while the MBean
  signature is `(warn, fail)`; this design does not rely on nodetool for setting, only for reading back.)
No `-D` property.

**A2. What it caps.** Nothing. The quantity compared is `keys.size()`, the number of partition keys an `IN`
restriction selects in a single-partition-style `SELECT` (`SelectStatement.java:716`, `:722`). When the count
exceeds the warn value, a warning is emitted; the query is not stopped, shortened or paged differently. The
resource that the count is a proxy for is coordinator heap (one `DecoratedKey`, one
`SinglePartitionReadCommand` and one read executor per key, and, with paging off, all their results at once),
but the warn value does not bound it.

**A3. Mechanism.**
1. Startup: `DatabaseDescriptor` builds `GuardrailsOptions` from `Config`; the constructor validates the pair
   (`GuardrailsOptions.java:73`). Getter `GuardrailsOptions.java:205-208` returns the field.
2. Guardrail object: `Guardrails.partitionKeysInSelect` is a `MaxThreshold` named `partition_keys_in_select`
   whose warn supplier reads the getter (`Guardrails.java:251-262`, warn supplier at `:254`). `MaxThreshold.warnValue`
   maps any value ≤ 0 to `Long.MAX_VALUE`, i.e. never triggers (`MaxThreshold.java:62-67`); `compare` is
   `value > threshold` (`MaxThreshold.java:49-53`).
3. Enabling: `Threshold.enabled` is true only if `Guardrail.enabled` holds (daemon initialized and the client
   is an ordinary user: not superuser, not system, `Guardrail.java:93-96`) **and** warn > 0 or fail > 0
   (`Threshold.java:80-86`). `ClientState.isSuper()` is true for everyone when the authenticator does not
   require authentication (`ClientState.java:602-605`), so with the default `AllowAllAuthenticator`
   (`conf/cassandra.yaml:198`) the guardrail never fires for any client.
4. Call site, the only one: `SelectStatement.getSliceCommands`, `if (restrictions.keyIsInRelation())
   Guardrails.partitionKeysInSelect.guard(keys.size(), table.name, false, state);`
   ([`SelectStatement.java:720-723`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L720-L723)).
   `keys` is already materialized by `restrictions.getPartitionKeys` (`SelectStatement.java:716`,
   `StatementRestrictions.java:811-814`).
5. `Threshold.guard` (`Threshold.java:128-143`): fail is checked first (`:133-138`, throws via `Guardrail.fail`
   `Guardrail.java:139-140`). Then the **if statement** for this entry,
   [`Threshold.java:141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L141):
   `if (compare(value, warnValue)) triggerWarn(...)`.
   - True (count > warn): `triggerWarn` (`Threshold.java:151-155`) → `Guardrail.warn` (`Guardrail.java:103-117`):
     `NoSpamLogger` WARN line (`:110`, logger rate-limited per message, `Guardrail.java:47-48`), one string added
     to the request's `ClientWarn` list (`:113`; `ClientWarn.java:75-80`, capped at 65535 entries of ≤65535
     chars each), a trace event if tracing (`:115`), a diagnostic event if `diagnostic_events_enabled` (`:116`).
     Returns normally.
   - False: nothing.
   Either way control returns to `getSliceCommands`, which clones and decorates every key
   (`SelectStatement.java:731-736`), creates one command per key (`:738-739`) and returns the group; execution
   then reads all keys (`StorageProxy.java:2106-2146`, one read executor per command, all sent at once) either
   unpaged (`SelectStatement.java:338-341`) or through `MultiPartitionPager` (`SelectStatement.java:344`,
   `SinglePartitionReadQuery.java:253-259`).
6. Bypasses: superusers, system/internal queries, and every client when authentication is off (step 3);
   range and secondary-index reads (`SelectStatement.java:401-413`) never reach the call site; a query that
   restricts the partition key with `=` (no `IN`) skips it (`keyIsInRelation`, `StatementRestrictions.java:445-448`).
   Overshoot is unbounded by construction: a warning does not stop a query of any size.

**A4. Other consumers.** Of the same heap (per-query coordinator memory for multi-key reads): the sibling
`partition_keys_in_select_fail_threshold` (aborts at `Threshold.java:134-137`, after the key list is built but
before commands are created and reads run); `in_select_cartesian_product_{warn,fail}_threshold`, checked on the
partition key while the key list is being built (`PartitionKeySingleRestrictionSet.java:95-96`); paging
(`fetch_size`) through `MultiPartitionPager`; `native_transport_max_frame_size` (`conf/cassandra.yaml:1044`),
which bounds the request text and hence the literal `IN` list length; read-size thresholds and the native
transport in-flight limits. Disk: none of this path writes to disk.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/db/guardrails/GuardrailPartitionKeysInSelectTest.java` (warn=3, fail=5:
  4 keys → `assertWarns`, query succeeds; 6 keys → `assertFails`), and the harness `GuardrailTester.java`
  (`setUpClass` `:113-132`, ordinary user `:137-150`, `execute(ClientState, …)` `:489-530`).
- `CHANGES.txt:949`: "Add guardrail for SELECT IN terms and their cartesian product (CASSANDRA-17187)",
  https://issues.apache.org/jira/browse/CASSANDRA-17187 (not fetched; cited for provenance only).

## B. Verification solution

**B1. Claim under test.** Setting `partition_keys_in_select_warn_threshold` below the number of keys in an
`IN` query does not reduce the heap the query allocates or holds, nor the rows and bytes it returns: for a fixed
`IN` query of N keys, per-query allocation and result size are the same (within noise) for warn = disabled,
warn ≥ N and warn < N, and the only difference is the warning text. The claim is wrong if per-query
allocation or result size falls (or rises) systematically when warn < N.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk (not the shared copy):
`rsync -a /users/jason92/cassandra-5.0.9/ $W/src/` where `$W` is a local directory with ≥ 5 GB free
(e.g. `/mydata/<user>-s4/pkis-warn`). Build: `cd $W/src && ant jar && ant build-test`.
Test source: new file `$W/src/test/unit/org/apache/cassandra/db/guardrails/PartitionKeysInSelectWarnUsageTest.java`
(below). It extends `GuardrailTester`, which starts an in-process node with authentication on, a network
server, and an ordinary-user `ClientState` (`GuardrailTester.java:113-150`), so `Guardrail.enabled` is true.
JVM options: those of `ant testsome` (unchanged).

**B2b. Knobs.** `(warn, fail)` set at runtime with `Guardrails.instance.setPartitionKeysInSelectThreshold(warn, fail)`
(same path as JMX, `Guardrails.java:904-907`), in this order, with N = 1000 keys per query:

| Setting | warn | fail | Why |
|---|---|---|---|
| S0 | -1 | -1 | guardrail off: baseline |
| S1 | 2000 | -1 | guardrail on, count ≤ warn: not triggered |
| S2 | 500 | -1 | triggered, count = 2 × warn |
| S3 | 10 | -1 | triggered, count = 100 × warn |
| C1 | -1 | 500 | positive control: same check, fail side, aborts |
| S0' | -1 | -1 | baseline repeated at the end (drift) |

**B2c. Workload.** Table `(k int, c int, v blob, PRIMARY KEY (k, c))`, 2000 partitions with one row each,
`v` = 16384 random bytes; flushed to an SSTable. Query: `SELECT k, c, v FROM <t> WHERE k IN (0,1,…,999)`,
executed as the ordinary user with internal-call options (page size -1, i.e. unpaged,
`QueryOptions.java:72-75`, `:540`). Count = 1000 > warn for S2, S3 (500, 10) and > fail for C1 (500);
1000 ≤ 2000 for S1. Expected payload per successful query = 1000 × 16384 = 16,384,000 bytes.
5 warm-up queries, then 20 measured queries per setting.

**B2d. Observables and instruments.**
- Operand: the key count, read from the warning text ("number of partition keys 1000"); for S0/S1 it is
  N by construction (no warning).
- Result: rows per query and Σ `v.remaining()` (payload bytes) from `ResultMessage.Rows.result.rows`.
- Warnings: `ClientWarn.instance.captureWarnings()/getWarnings()/resetWarnings()` around each query.
- Heap allocation per query, all threads: `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(getAllThreadIds())`
  summed before and after each query; report the median of the 20 deltas. Threads that end during a query are
  lost from the sum (pooled stage threads normally do not end), so the figure is a slight underestimate,
  equally for every setting.
- Not observable here: retained (live) heap per query; the cluster tier covers peak heap.

**B2e. Procedure.**
1. Create the test file:
```java
package org.apache.cassandra.db.guardrails;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.*;
import java.util.stream.*;
import org.junit.Test;
import org.apache.cassandra.service.ClientWarn;
import org.apache.cassandra.transport.messages.ResultMessage;

public class PartitionKeysInSelectWarnUsageTest extends GuardrailTester
{
    static final int PARTITIONS = 2000, N = 1000, BLOB = 16384, WARMUP = 5, ITER = 20;
    static final com.sun.management.ThreadMXBean TMX =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static long allocatedAllThreads()
    {
        long s = 0;
        for (long a : TMX.getThreadAllocatedBytes(TMX.getAllThreadIds())) if (a > 0) s += a;
        return s;
    }

    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))");
        Random r = new Random(42);
        for (int k = 0; k < PARTITIONS; k++)
        {
            byte[] b = new byte[BLOB]; r.nextBytes(b);
            execute("INSERT INTO %s (k, c, v) VALUES (?, 0, ?)", k, ByteBuffer.wrap(b));
        }
        flush();
        String q = "SELECT k, c, v FROM %s WHERE k IN (" +
                   IntStream.range(0, N).mapToObj(Integer::toString).collect(Collectors.joining(",")) + ")";
        String[] names = { "S0", "S1", "S2", "S3", "C1", "S0'" };
        int[][] set = { {-1,-1}, {2000,-1}, {500,-1}, {10,-1}, {-1,500}, {-1,-1} };
        for (int i = 0; i < set.length; i++)
        {
            Guardrails.instance.setPartitionKeysInSelectThreshold(set[i][0], set[i][1]);
            long[] alloc = new long[ITER]; long rows = 0, bytes = 0; int failed = 0; String warn = "-";
            for (int j = 0; j < WARMUP + ITER; j++)
            {
                ClientWarn.instance.captureWarnings();
                long a0 = allocatedAllThreads();
                long rr = 0, bb = 0;
                try
                {
                    ResultMessage.Rows res = (ResultMessage.Rows) execute(userClientState, q);
                    for (List<ByteBuffer> row : res.result.rows) { rr++; bb += row.get(2).remaining(); }
                }
                catch (Exception e) { if (j >= WARMUP) failed++; warn = "EXC:" + e.getMessage(); }
                long a1 = allocatedAllThreads();
                List<String> w = ClientWarn.instance.getWarnings();
                ClientWarn.instance.resetWarnings();
                if (j >= WARMUP)
                {
                    alloc[j - WARMUP] = a1 - a0; rows += rr; bytes += bb;
                    if (w != null && !w.isEmpty()) warn = w.size() + ":" + w.get(0);
                }
            }
            Arrays.sort(alloc);
            System.out.printf("RESULT %s warn=%d fail=%d rowsPerQuery=%d bytesPerQuery=%d failed=%d medianAlloc=%d minAlloc=%d maxAlloc=%d warning=%s%n",
                              names[i], set[i][0], set[i][1], rows / ITER, bytes / ITER, failed,
                              alloc[ITER / 2], alloc[0], alloc[ITER - 1], warn);
        }
        Guardrails.instance.setPartitionKeysInSelectThreshold(-1, -1);
    }
}
```
2. Run: `cd $W/src && ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.PartitionKeysInSelectWarnUsageTest`
3. Collect: `grep -h '^RESULT\|RESULT ' build/test/output/TEST-org.apache.cassandra.db.guardrails.PartitionKeysInSelectWarnUsageTest*.xml`
   (stdout is captured in the JUnit XML under `build/test/output/`).
4. Sanity: the existing `ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.GuardrailPartitionKeysInSelectTest`
   passes (warn path and enabling work in this build).

**B2f. Predictions.**
- S0, S1, S2, S3, S0': `rowsPerQuery=1000`, `bytesPerQuery=16384000`, `failed=0`.
- Warnings: S0, S1, S0' `warning=-`; S2 `1:Guardrail partition_keys_in_select violated: Query with partition keys in IN clause on table …, with number of partition keys 1000 exceeds warning threshold of 500.`; S3 same with `threshold of 10`.
- `medianAlloc` of S1, S2, S3 each within ±15% of the mean of S0 and S0' (and S0 vs S0' within ±15%);
  no ordering S3 < S2 < S1.
- C1: `failed=20`, `rowsPerQuery=0`, `warning=EXC:…number of partition keys 1000 exceeds fail threshold of 500.`,
  `medianAlloc` ≤ 20% of the S0/S0' mean (no reads run; only parse and key list).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| S2/S3 rows or bytes < 16,384,000, or S2/S3 `medianAlloc` more than 15% below baseline while S1 is not | usage follows the warn value: **claim refuted** |
| S1–S3 rows, bytes and `medianAlloc` within ±15% of baseline, warnings present only in S2/S3, and C1 allocation ≤ 20% of baseline | usage flat while the positive control moves: **claim confirmed** |
| No warning in S2/S3 (limit never reached: guardrail not enabled, e.g. user treated as superuser) | **not confirmed**; fix enabling (ordinary user, authentication on) and rerun |
| C1 does not fail, or C1 allocation > 20% of baseline | control did not move: instrument or harness cannot see a cap that binds; **not confirmed** |
| S0 and S0' differ by > 15% | drift dominates; increase ITER to 50 and rerun before judging |

**B2h. Controls.** C1 uses the same guardrail object, call site and query, differing only in which side of
`guard` fires, so it shows the instrument resolves a binding limit. S0/S0' bracket drift (JIT, caches). S1
separates "guardrail enabled" from "guardrail triggered". Fixed seed and fixed table data; reads served from
one flushed SSTable plus the chunk cache, identical for every setting after warm-up.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node (a second node adds nothing: the check runs on the
coordinator only), JDK 11, Ant, Python 3 (for the bundled driver), ≥ 4 GB RAM free, local disk `$W` with
≥ 5 GB free.
1. `rsync -a /users/jason92/cassandra-5.0.9/ $W/node/ && cd $W/node && ant jar`.
2. Edit `$W/node/conf/cassandra.yaml`: `authenticator: PasswordAuthenticator` (required: with
   `AllowAllAuthenticator` every client is a superuser and the guardrail never fires, `ClientState.java:602-605`);
   `data_file_directories: [$W/data/data]`, `commitlog_directory: $W/data/commitlog`,
   `saved_caches_directory: $W/data/saved_caches`, `hints_directory: $W/data/hints`,
   `cdc_raw_directory: $W/data/cdc_raw` (write `$W` expanded); listen/rpc on `127.0.0.1`. If 9042/7000/7199 are
   taken (`ss -ltn`), change `native_transport_port`, `storage_port`, and `JMX_PORT` in `conf/cassandra-env.sh`.
3. Heap: `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M` before starting (G1 is the default, `conf/jvm11-server.options:63`).
4. Start: `bin/cassandra -p $W/cassandra.pid > $W/start.log 2>&1`; wait until `bin/nodetool status` shows `UN`
   and `bin/cqlsh -u cassandra -p cassandra -e 'SELECT now() FROM system.local'` works (the default superuser is
   created a few seconds after startup).

**B3b. Knobs.** Append to the end of `conf/cassandra.yaml` (they are commented out by default) and restart the
node for each setting; N = 2000 keys per query:

| Setting | `partition_keys_in_select_warn_threshold` | `partition_keys_in_select_fail_threshold` | Query keys | Why |
|---|---|---|---|---|
| S0 | -1 | -1 | 2000 | baseline |
| S1 | 4000 | -1 | 2000 | enabled, not triggered |
| S2 | 1000 | -1 | 2000 | triggered, 2 × warn |
| S3 | 10 | -1 | 2000 | triggered, 200 × warn |
| C1 | -1 | 1000 | 2000 | positive control: cap that binds (fail side) |
| C2 | -1 | -1 | 200 | load-sensitivity control: 10× less result |
| S0' | -1 | -1 | 2000 | repeated baseline |

After each restart verify: `bin/nodetool getguardrailsconfig -c thresholds --expand | grep partition_keys_in_select`.

**B3c. Workload.** Setup once (as superuser `cassandra`):
```
CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE ks.t (k int, c int, v blob, PRIMARY KEY (k, c));
CREATE ROLE app WITH PASSWORD = 'app_pw' AND LOGIN = true AND SUPERUSER = false;
```
Load 4000 partitions × 1 row × 8192 random bytes (≈ 33 MB on disk), then `bin/nodetool flush ks t`.
Query (as `app`, an ordinary user): `SELECT k, c, v FROM ks.t WHERE k IN (0,…,N-1)` with paging off
(`fetch_size=None`). Result per query = 2000 × 8192 = 16,384,000 bytes of `v` (1,638,400 for C2).
4 client threads, 20 s warm-up (discarded) then 60 s measured, per setting.

Client script `$W/load.py` (uses the driver bundled for cqlsh, `lib/cassandra-driver-internal-only-3.29.0.zip`):
```python
import sys, os, time, threading
sys.path.insert(0, sys.argv[1])
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
from cassandra.query import SimpleStatement
mode, N, dur, threads = sys.argv[2], int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
user, pw = ('cassandra', 'cassandra') if mode == 'load' else ('app', 'app_pw')
cl = Cluster(['127.0.0.1'], auth_provider=PlainTextAuthProvider(user, pw))
s = cl.connect(); s.default_timeout = 120
if mode == 'load':
    ins = s.prepare("INSERT INTO ks.t (k, c, v) VALUES (?, 0, ?)")
    for k in range(4000): s.execute(ins, (k, os.urandom(8192)))
    sys.exit(0)
q = SimpleStatement("SELECT k, c, v FROM ks.t WHERE k IN (%s)" % ",".join(map(str, range(N))), fetch_size=None)
st = {'ok': 0, 'fail': 0, 'rows': 0, 'bytes': 0, 'warned': 0, 'warn': '-', 'err': '-'}
lock = threading.Lock(); end = time.time() + dur
def run():
    while time.time() < end:
        try:
            rs = s.execute(q); rows = list(rs); w = rs.response_future.warnings
            with lock:
                st['ok'] += 1; st['rows'] += len(rows); st['bytes'] += sum(len(r.v) for r in rows)
                if w: st['warned'] += 1; st['warn'] = w[0]
        except Exception as e:
            with lock: st['fail'] += 1; st['err'] = str(e)[:200]
ts = [threading.Thread(target=run) for _ in range(threads)]
[t.start() for t in ts]; [t.join() for t in ts]
n = max(st['ok'], 1)
print("CLIENT ok=%d fail=%d rowsPerQuery=%d bytesPerQuery=%d warned=%d warn=%s err=%s" %
      (st['ok'], st['fail'], st['rows'] // n, st['bytes'] // n, st['warned'], st['warn'], st['err']))
cl.shutdown()
```
Load: `python3 $W/load.py $W/node/lib/cassandra-driver-internal-only-3.29.0.zip load 0 0 0`.

**B3d. Observables and instruments.**
- Heap allocation (actual resource): `jstat -gc -t <pid> 250` written to a file during the 60 s window;
  allocated KB estimated with
  ```
  awk 'NR==1{next}{ec=$6;eu=$7;ou=$9;y=$14;u=$4+$5+$7+$9;
   if(s){ if(y==py){d=eu-peu;if(d>0)a+=d;d=ou-pou;if(d>0)a+=d} else {a+=(pec-peu)+eu} }
   if(u>pk)pk=u; peu=eu;pec=ec;pou=ou;py=y;s=1}
   END{printf "alloc_KB=%.0f peak_used_KB=%.0f ygc_end=%d\n",a,pk,py}' jstat.txt
  ```
  (columns of JDK 11 `jstat -gc -t`: Timestamp S0C S1C S0U S1U EC EU OC OU … YGC at field 14). Per-query
  allocation = alloc_KB × 1024 / (ok + fail). Peak heap used = max(S0U+S1U+EU+OU).
- Client: rows and bytes per query, warnings received, failures (from `load.py`).
- Node log: `grep -c 'Guardrail partition_keys_in_select violated' $W/node/logs/system.log` per setting
  (NoSpamLogger may print a repeated identical message only once per 10 minutes, so ≥ 1 is the expectation).
- Disk: `du -sb $W/data/data/ks` before and after each setting (reads only; should not change).
- Not observable: per-query retained heap; off-heap Netty buffers for the response (not on the warn path either).

**B3e. Procedure.** For each setting in the order of B3b:
1. `kill $(cat $W/cassandra.pid)`; wait until the pid is gone; set the two yaml lines; start as in B3a.4;
   verify with `getguardrailsconfig`.
2. Warm-up: `python3 $W/load.py $W/node/lib/cassandra-driver-internal-only-3.29.0.zip query <N> 20 4`.
3. `PID=$(cat $W/cassandra.pid); jstat -gc -t $PID 250 > $W/jstat-<setting>.txt & JS=$!`
4. `python3 $W/load.py $W/node/lib/cassandra-driver-internal-only-3.29.0.zip query <N> 60 4 | tee $W/client-<setting>.txt`
5. `kill $JS`; run the awk above on `$W/jstat-<setting>.txt`; record log grep count and `du -sb`.
Record a row per setting: ok, fail, rows/q, bytes/q, warned, alloc per query, peak heap used, YGC count, log count.

**B3f. Predictions.**
- S0, S1, S2, S3, S0': `fail=0`, `rowsPerQuery=2000`, `bytesPerQuery=16384000`.
- `warned`: 0 in S0, S1, S0'; equal to `ok` in S2 and S3, with text "…number of partition keys 2000 exceeds
  warning threshold of 1000." (S2) / "…of 10." (S3); system.log count ≥ 1 in S2 and S3, 0 in S0, S1, S0'.
- Per-query allocation of S1, S2, S3 each within ±15% of the S0/S0' mean; peak heap used shows no ordering by
  warn value (S3 not lower than S1 beyond ±15%).
- C1: `ok=0`, every query fails with "Aborting query with partition keys in IN clause on table t, number of
  partition keys 2000 exceeds fail threshold of 1000."; per-query allocation ≤ 20% of baseline.
- C2: `rowsPerQuery=200`, `bytesPerQuery=1638400`, per-query allocation between 5% and 25% of baseline.
- Disk: `du -sb` unchanged within each setting.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| S2/S3 return fewer rows/bytes, fail, or have per-query allocation or peak heap > 15% below baseline while S1 does not | usage follows the warn value: **claim refuted** |
| S1–S3 per-query allocation and result size within ±15% of baseline, warnings only in S2/S3, C1 ≤ 20% and C2 in 5–25% of baseline | usage flat while the positive controls move: **claim confirmed** |
| No warnings in S2/S3 (guardrail not active: authentication off, or `app` is a superuser) | limit never reached: **not confirmed**; fix B3a.2 / role and rerun |
| C1 queries succeed, or C1/C2 allocation not separated from baseline as predicted | control did not move, the instrument cannot resolve the effect: **not confirmed**; raise blob size or query count and rerun |
| S0 vs S0' differ > 15% | drift; extend the window to 120 s and rerun |

**B3h. Controls.** C1 (same check, aborting side) is the cap known to bind on this workload; C2 shows the
allocation instrument follows a 10× change in result size. S1 separates enabled from triggered. Restart before
each setting removes carry-over of heap state; warm-up equalizes JIT and the chunk cache; the data set (33 MB)
fits in the OS page cache, so disk I/O does not differ between settings. Same client, thread count and duration
for every setting.

**B4. Risks and cleanup.** All files under `$W` on local disk (source copies, ≈ 33 MB data, logs); nothing in
the shared tree or shared storage. Unit tier: the test JVM exits with `ant`; check `pgrep -f PartitionKeysInSelectWarnUsageTest`
is empty. Cluster tier: after the last setting `kill $(cat $W/cassandra.pid)`, kill any `jstat` left
(`pkill -f "jstat -gc -t"` for this user only), confirm `pgrep -u $USER -f CassandraDaemon` and
`pgrep -u $USER -f load.py` are empty, then `rm -rf $W/data` (and `$W` when results are copied out). A
fully unpaged 2000-key query holds ≈ 16 MB of values per in-flight query; with 4 threads and a 1 GB heap this
leaves wide margin, so no OOM is expected; if `system.log` shows long GC pauses, reduce threads to 2.

## C. Sources read

- src/java/org/apache/cassandra/config/Config.java (860-890)
- src/java/org/apache/cassandra/config/GuardrailsOptions.java (60-80, 200-230, 1092-1194)
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java (50-56, 240-262, 294-297, 561, 892-907)
- src/java/org/apache/cassandra/db/guardrails/GuardrailsConfig.java (102, 107)
- src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java (355-369)
- src/java/org/apache/cassandra/db/guardrails/Threshold.java
- src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java
- src/java/org/apache/cassandra/db/guardrails/Guardrail.java (40-200)
- src/java/org/apache/cassandra/db/guardrails/GuardrailViolatedException.java
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (320-415, 690-760, 1800-1880)
- src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (445-448, 800-830)
- src/java/org/apache/cassandra/cql3/restrictions/PartitionKeySingleRestrictionSet.java (90-98)
- src/java/org/apache/cassandra/cql3/QueryOptions.java (72-75, 540)
- src/java/org/apache/cassandra/db/SinglePartitionReadQuery.java (253-259)
- src/java/org/apache/cassandra/service/pager/MultiPartitionPager.java (48, 58)
- src/java/org/apache/cassandra/service/StorageProxy.java (1858, 2106-2146)
- src/java/org/apache/cassandra/service/ClientState.java (594-620)
- src/java/org/apache/cassandra/service/ClientWarn.java
- src/java/org/apache/cassandra/transport/messages/ResultMessage.java (196)
- src/java/org/apache/cassandra/cql3/ResultSet.java (49)
- src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java (55-80, 165-240)
- test/unit/org/apache/cassandra/db/guardrails/GuardrailPartitionKeysInSelectTest.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java (82-150, 186-260, 489-530)
- test/unit/org/apache/cassandra/db/guardrails/ThresholdTester.java (41-44)
- conf/cassandra.yaml (198, 217, 232, 1044, 2090-2102); conf/cassandra_latest.yaml (2070-2071)
- conf/cassandra-env.sh (55-150); conf/jvm11-server.options (41, 63)
- build.xml (62, 608-609, 1382-1385); CHANGES.txt (949); lib/ (driver zip name)
- https://issues.apache.org/jira/browse/CASSANDRA-17187 (cited, not fetched)

## D. Stage-4 feedback

none yet

## Config-first: places found

Every place the value of `partition_keys_in_select_warn_threshold` flows to, in order. **None restricts memory
or disk**; the closest is place 9 (the Entry pointer).

1. [`Config.java:875`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L875) — declaration, default -1; restricts nothing.
2. `GuardrailsOptions.java:73` (with `:1123-1128`, `:1092-1109`, `:1176-1184`) — startup validation: -1 or 1..Integer.MAX_VALUE, warn ≤ fail; rejects bad values, restricts nothing.
3. `GuardrailsOptions.java:205-208` — getter `getPartitionKeysInSelectWarnThreshold`; restricts nothing.
4. `GuardrailsOptions.java:216-226` — runtime setter (validates, then writes the volatile field with logging); restricts nothing.
5. `Guardrails.java:251-262` (warn supplier `:254`) — the `MaxThreshold` guardrail `partition_keys_in_select`; restricts nothing by itself.
6. `Guardrails.java:892-907` / `GuardrailsMBean.java:355-369` / `GuardrailsConfigCommand.java:55,172` — JMX and nodetool read/write; restricts nothing.
7. `MaxThreshold.java:62-67` — `warnValue`: ≤ 0 becomes `Long.MAX_VALUE` (never warns); restricts nothing.
8. `Threshold.java:80-86` — `enabled`: warn > 0 (or fail > 0) turns the guardrail on, subject to `Guardrail.java:93-96` (ordinary users only); a switch for a warning, not for a limit.
9. [`Threshold.java:141`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L141) — `if (value > warn) triggerWarn(...)` → `Guardrail.warn` (`Guardrail.java:103-117`): log line, one `ClientWarn` string, trace, diagnostic event; the query continues; restricts nothing (adds a small constant allocation).
10. [`SelectStatement.java:720-723`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L720-L723) — the only call site, `value = keys.size()` for `IN` on the partition key; `getSliceCommands` builds and runs all keys afterwards regardless (`:725-745`); restricts nothing.

Places beyond three for a later unit: none (no place restricts memory or disk; one case file written per addendum rule 3).
