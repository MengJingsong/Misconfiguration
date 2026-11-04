# tombstone_failure_threshold — verification solution  <!-- file: cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/ReadCommand.java:591` (`if (tombstones > failureThreshold && respectTombstoneThresholds)` in `MetricRecording.countTombstone`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code agent (CLI version not exposed to the agent), 2026-10-21 |
| Estimate | `positive`. The check stops a read (it throws `TombstoneOverwhelmingException`) while the tombstones are still streaming into the on-heap `DataOutputBuffer` that holds the replica's response. Per read, the heap that response takes is therefore bounded by about (T+1) × the serialized size of one tombstone. The cap counts tombstones, not bytes. It applies to each read command (each page) separately, not to the whole node. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name:** `tombstone_failure_threshold` (called T below).
- **Kind:** configuration entry. It can also be changed at runtime through JMX.
- **Where it is declared:** `public volatile int tombstone_failure_threshold = 100000;` at `src/java/org/apache/cassandra/config/Config.java:535`. The shipped yaml sets the same value at `conf/cassandra.yaml:1815` (and `conf/cassandra_latest.yaml:1794`).
- **Unit:** a count of tombstones (int), not bytes.
- **Default:** 100000, a hard-coded literal. Nothing derives it from the heap size or any other setting.
- **How the code reads it:** `DatabaseDescriptor.getTombstoneFailureThreshold()` at `DatabaseDescriptor.java:2842-2845`. The setter is at `:2847-2850`.
- **Runtime setting:** the `StorageServiceMBean` attribute `TombstoneFailureThreshold` (`StorageServiceMBean.java:985-987`, `StorageService.java:6722-6731`, which logs "updated tombstone_failure_threshold to ..."). A runtime change needs no restart.
- **When a new value takes effect:** the value is copied once per read command, when the `MetricRecording` transformation is built (`ReadCommand.java:528`). So a change applies to read commands that start after it.
- **Companion setting:** `tombstone_warn_threshold`, default 1000 (`Config.java:534`), only warns.

**A2. What it caps.**
- **Operand:** the number of tombstones that one execution of one `ReadCommand` on one replica scans after merging and purging. This is the local variable `tombstones` (`ReadCommand.java:537`). Three kinds of item count toward it:
  - each non-live cell (`:558-565`);
  - each row whose only content is a row deletion (`:569-575`);
  - each range-tombstone bound or boundary marker (`:580-584`).
- **Resource:** heap. The yaml comment at `conf/cassandra.yaml:1805-1813` gives the reason for the threshold: "we need to keep the tombstones seen in memory so we can return them to the coordinator ... this can cause performance problems and even exaust the server heap".
- **The memory-significant object:** the response buffer. A data read serializes the whole merged result, tombstones included, into one heap buffer: `ReadResponse.LocalDataResponse.build` uses `new DataOutputBuffer()` at `ReadResponse.java:197-210`. This is reached through `ReadCommand.createResponse` (`ReadCommand.java:366-374`).
  - The local path calls it at `StorageProxy.java:2208-2212`.
  - The path for reads arriving from other nodes calls it at `ReadCommandVerbHandler.java:92-96`.
  - The buffer starts at 128 B (`DataOutputBuffer.java:57`). It doubles until it passes `cassandra.DOB_DOUBLING_THRESHOLD_MB` (64 MiB by default, `CassandraRelevantProperties.java:203`) and then grows by 1.5× (`DataOutputBuffer.java:158-182`). Each step copies the old buffer into a new one.
- **What the cap does not limit:** the threshold bounds how many tombstones go into that buffer for one read. It does not bound how big each tombstone is, and it does not bound how many reads run at once.

**A3. Mechanism.**
1. `ReadCommand.executeLocally` (`ReadCommand.java:421-504`) builds the iterator chain in this order:
   - the storage merge;
   - `withQuerySizeTracking` (`:457`);
   - `withQueryCancellation` (`:459`);
   - `withoutPurgeableTombstones` (`:460`, defined at `:868-886`);
   - `withMetricsRecording` (`:461`);
   - then the row filter (`:470`) and the limits (`:476-492`).

   Tombstones that are already purgeable are therefore removed before counting. Tombstones never count toward the row limit, so a page with no live rows scans every tombstone in its range.
2. `MetricRecording` reads T and the warn threshold once (`:528-529`). It sets `respectTombstoneThresholds = !SchemaConstants.isLocalSystemKeyspace(keyspace)` (`:531`).
3. For every row, static row and marker that streams through, `countTombstone` (`:587-602`) does `++tombstones`. If `tombstones > T` and the keyspace is not a local system keyspace (line 591), it:
   - writes a trace line and increments `TableMetrics.tombstoneFailures` (`:594-595`);
   - records `TOMBSTONE_FAIL` when warnings are tracked (`:596-600`);
   - throws `TombstoneOverwhelmingException(tombstones, ...)` (`:601`). The message says "Scanned over %d tombstones" (`TombstoneOverwhelmingException.java:29-33`).

   The exception unwinds through `UnfilteredPartitionIterators.serializerForIntraNode().serialize` inside `LocalDataResponse.build`. That abandons the partly filled `DataOutputBuffer`, which becomes garbage. So at most T+1 counted tombstones are ever serialized for one command.
4. **When the read is aborted:**
   - In `StorageProxy.LocalReadRunnable`, the exception is turned into `RequestFailureReason.READ_TOO_MANY_TOMBSTONES` and logged at ERROR (`StorageProxy.java:2243-2248`).
   - When warnings are tracked, a `RejectException` is turned into an empty response and the coordinator aborts the query with the client warning (`StorageProxy.java:2213-2220`, `ReadCommandVerbHandler.java:97+`).
   - The client receives a `ReadFailureException`.
   - `onClose` (`:620-650`) still records `TombstoneScannedHistogram`.
5. **When the read stays under T:** it completes. If the count is above `tombstone_warn_threshold`, it also warns (`:629-646`) and increments `TombstoneWarnings`.
6. **Paths that bypass the cap or overshoot it:**
   - **Local system keyspaces** are exempt (`:531`).
   - **Purgeable tombstones** (older than `gc_grace_seconds`) are neither counted nor serialized (`:460`). This is consistent, since they do not reach the buffer either.
   - **Partition-level deletions** are not counted (`applyToPartition`, `:542-546`), but each one serializes only once per partition.
   - **Size per tombstone is not limited.** Large clustering values make one tombstone large, so T tombstones can mean far more bytes than "T small tombstones".
   - **Per command, not per page or per node:** each page (a new command) and each replica starts at 0. With C reads running at once, the heap held is up to C × the per-read bound. The default `concurrent_reads` is 32 (`Config.java:179`).
   - **Overshoot by one:** the counter reaches T+1 before the throw.
   - **Digest reads** never build the buffer. They hash instead (`ReadCommand.java:371-373`).
   - **Not counted at all:** compaction, repair and streaming read tombstones outside this check.

**A4. Other consumers.**
The same heap is used by:
- memtables;
- the key and row caches;
- coordinator-side merging (`DataResolver`) and replica filtering protection (`cached_replica_rows_*` thresholds);
- other concurrent reads, compaction and SAI.

On-disk tombstones themselves are governed by `gc_grace_seconds` and compaction, not by this threshold.

A separate byte-based cap on the same object exists: `local_read_size_fail_threshold`, which compares `row.unsharedHeapSize()` (`ReadCommand.java:663-700`). It is active only when `read_thresholds_enabled: true`, and that setting defaults to false (`Config.java:526`, `conf/cassandra.yaml:2015`). The cluster tier keeps it at its default, unset.

**A5. Evidence beyond the source.**
- **History:** `CHANGES.txt:5101` records "drop queries exceeding a configurable number of tombstones (CASSANDRA-6117)" (https://issues.apache.org/jira/browse/CASSANDRA-6117). `CHANGES.txt:5142` records "Add tombstone debug threshold and histogram (CASSANDRA-6042, 6057)". `CHANGES.txt:1028` records CASSANDRA-16850, the client warnings and abort.
- **Docs:** the yaml comment `conf/cassandra.yaml:1805-1815`, and the metrics docs `doc/modules/cassandra/pages/managing/operating/metrics.adoc:181-188` (`TombstoneScannedHistogram`, `TombstoneWarnings`, `TombstoneFailures`).
- **Existing tests:** `test/unit/org/apache/cassandra/cql3/validation/miscellaneous/TombstonesTest.java` exercises the throw and the counters, but not memory.

## B. Verification solution

**B1. Claim under test.**
1. For one data read of a partition holding N non-purgeable tombstones (and no live rows), the replica stops after counting exactly min(N, T+1) tombstones. It throws `TombstoneOverwhelmingException` if and only if N > T.
2. The heap bytes that read allocates and holds for its response grow in proportion to min(N, T+1), not to N. Under concurrent reads, the node's peak heap grows by about C × that per-read amount.
3. The claim is refuted if lowering T below N leaves the response heap use unchanged.

### B2. Unit tier

**B2a. Environment and build.**
- **JDK and build:** JDK 11 and Ant. Use the runner's built clone `~/cassandra-run1` at tag `cassandra-5.0.9`, where `ant build-test` has already been run. Do not touch the shared source tree.
- **Test file:** add one file, `~/cassandra-run1/test/unit/org/apache/cassandra/db/TombstoneFailureThresholdMemoryTest.java`, listed in B2e.
- **Command:** `ant testsome -Dtest.name=org.apache.cassandra.db.TombstoneFailureThresholdMemoryTest`. The `testsome` target (`build.xml:1382-1392`) recompiles the tests and forks a JUnit JVM with `maxmemory=1024m` (`build.xml:1153`) and a 480 s timeout (`build.xml:125`).
- **JVM options:** no extra options are needed.
- **Where the data goes:** CQLTester puts its data under `~/cassandra-run1/build/test/cassandra`, about 60 MB here. Check that `~` is local disk with at least 2 GB free (`df -h ~`).

**B2b. Knobs.**

The test varies T with `DatabaseDescriptor.setTombstoneFailureThreshold(T)` before each read. The read command picks up the new value when its `MetricRecording` is built (`ReadCommand.java:528`). With N = 30,000:

| T | Why this value |
|---|---|
| 1,000 | far below N |
| 10,000 | below N |
| 20,000 | below N; together with 1,000 and 10,000, checks that usage scales with T |
| 29,999 = N−1 | boundary: should throw at 30,000 |
| 30,000 = N | boundary: should pass, because the check is strict `>` |
| 100,000 | the default, above N |
| `Integer.MAX_VALUE` | uncapped positive control |

The original value is restored in `@AfterClass`.

**B2c. Workload.**
- **Table:** `CREATE TABLE (pk int, ck text, v text, PRIMARY KEY (pk, ck))`, with the default `gc_grace_seconds` of 864000, so no tombstone is purgeable during the test.
- **Tombstone partition, pk=0:** N = 30,000 rows written as `INSERT (pk,ck,v) VALUES (0, ck_i, null)`. A null value writes a cell tombstone, which `countTombstone` counts once per row (`ReadCommand.java:558-565`).
- **Live control partition, pk=1:** the same N rows with `v=''`, which makes them live.
- **Clustering values:** `ck_i` is `%08d` of i, padded with `x` to 1,000 characters, so each serialized tombstone is about 1.0–1.05 KB.
- **Flush** to an SSTable after writing.
- **Expected sizes:** the full pk=0 response is about 30,000 × 1.02 KB ≈ 30–32 MB. With T=1,000, the read should stop after about 1 MB has been serialized. Every T < N is reached because the read scans all N tombstones unless it aborts.
- **The read:** `Util.cmd(cfs, pk).build()`, a single-partition command with `DataLimits.NONE`. It is run with `executeLocally` and then `createResponse`, the same calls as `StorageProxy.java:2208-2212`.
- **Repetitions:** 5 per (pk, T).

**B2d. Observables and instruments.**
1. **Outcome and operand.** Either OK, or `TombstoneOverwhelmingException`. On an exception, the count is parsed from the message "Scanned over (\d+) tombstones", which is the operand at the moment of the throw.
2. **Response bytes.** For OK reads: `ReadResponse.serializer.serializedSize(resp, MessagingService.current_version)`, the size of the on-heap response, plus the number of unfiltered rows in the response (iterated with `resp.makeIterator(cmd)`).
3. **Heap allocated by the read thread.** `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(currentThreadId)` is taken before and after the read plus response build. The read is synchronous on the test thread. The table reports the median of 5 repetitions.
4. **What cannot be observed directly:** for aborted reads, the abandoned buffer's size is not visible. It is inferred from item 3.

**B2e. Procedure.**
1. Run `df -h ~` and confirm `~/cassandra-run1` is on local disk.
2. Create the file below:

```java
package org.apache.cassandra.db;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.lang.management.ManagementFactory;
import java.util.Arrays;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.junit.AfterClass;
import org.junit.Test;

import org.apache.cassandra.Util;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;
import org.apache.cassandra.db.filter.TombstoneOverwhelmingException;
import org.apache.cassandra.db.partitions.UnfilteredPartitionIterator;
import org.apache.cassandra.db.rows.UnfilteredRowIterator;
import org.apache.cassandra.net.MessagingService;

public class TombstoneFailureThresholdMemoryTest extends CQLTester
{
    static final int N = 30_000;
    static final int CK_LEN = 1000;
    static final int REPS = 5;
    static final int ORIGINAL = DatabaseDescriptor.getTombstoneFailureThreshold();
    static final com.sun.management.ThreadMXBean TMX =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();
    static final Pattern P = Pattern.compile("Scanned over (\\d+) tombstones");

    @AfterClass
    public static void restore() { DatabaseDescriptor.setTombstoneFailureThreshold(ORIGINAL); }

    static String ck(int i)
    {
        StringBuilder sb = new StringBuilder(String.format("%08d", i));
        while (sb.length() < CK_LEN) sb.append('x');
        return sb.toString();
    }

    static long allocated() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    static int countUnfiltered(ReadResponse resp, ReadCommand cmd)
    {
        int n = 0;
        try (UnfilteredPartitionIterator pi = resp.makeIterator(cmd))
        {
            while (pi.hasNext())
                try (UnfilteredRowIterator ri = pi.next()) { while (ri.hasNext()) { ri.next(); n++; } }
        }
        return n;
    }

    @Test
    public void sweep() throws Throwable
    {
        createTable("CREATE TABLE %s (pk int, ck text, v text, PRIMARY KEY (pk, ck))");
        for (int i = 0; i < N; i++)
        {
            execute("INSERT INTO %s (pk, ck, v) VALUES (0, ?, null)", ck(i)); // cell tombstone
            execute("INSERT INTO %s (pk, ck, v) VALUES (1, ?, '')", ck(i));   // live row (control)
        }
        ColumnFamilyStore cfs = getCurrentColumnFamilyStore();
        Util.flush(cfs);

        int[] ts = { 1_000, 10_000, 20_000, N - 1, N, 100_000, Integer.MAX_VALUE };
        try (PrintWriter out = new PrintWriter(new FileWriter("build/test/tft-unit.tsv")))
        {
            out.println("pk\tT\toutcome\tcount_at_throw\tresp_bytes\tunfiltered_in_resp\talloc_median\talloc_min\talloc_max");
            for (int pk : new int[]{ 0, 1 })
                for (int t : ts)
                {
                    DatabaseDescriptor.setTombstoneFailureThreshold(t);
                    long[] alloc = new long[REPS];
                    String outcome = "?"; long count = -1, respBytes = -1; int unf = -1;
                    for (int r = 0; r < REPS; r++)
                    {
                        SinglePartitionReadCommand cmd = (SinglePartitionReadCommand) Util.cmd(cfs, pk).build();
                        long a0 = allocated();
                        try (ReadExecutionController ec = cmd.executionController();
                             UnfilteredPartitionIterator it = cmd.executeLocally(ec))
                        {
                            ReadResponse resp = cmd.createResponse(it, ec.getRepairedDataInfo());
                            alloc[r] = allocated() - a0;
                            respBytes = ReadResponse.serializer.serializedSize(resp, MessagingService.current_version);
                            unf = countUnfiltered(resp, cmd);
                            outcome = "OK";
                        }
                        catch (TombstoneOverwhelmingException e)
                        {
                            alloc[r] = allocated() - a0;
                            Matcher m = P.matcher(e.getMessage());
                            count = m.find() ? Long.parseLong(m.group(1)) : -2;
                            outcome = "TOE"; respBytes = -1; unf = -1;
                        }
                    }
                    Arrays.sort(alloc);
                    String line = pk + "\t" + t + "\t" + outcome + "\t" + count + "\t" + respBytes + "\t" + unf
                                  + "\t" + alloc[REPS / 2] + "\t" + alloc[0] + "\t" + alloc[REPS - 1];
                    out.println(line);
                    System.out.println("TFT " + line);
                }
        }
    }
}
```

3. Run `cd ~/cassandra-run1 && ant testsome -Dtest.name=org.apache.cassandra.db.TombstoneFailureThresholdMemoryTest`. It should take about 2–5 min.
4. Collect `~/cassandra-run1/build/test/tft-unit.tsv`. The same lines appear in `build/test/output/TEST-org.apache.cassandra.db.TombstoneFailureThresholdMemoryTest.xml` under `<system-out>`, prefixed `TFT`.
5. Clean up: delete the test file, `build/test/tft-unit.tsv` and `build/test/cassandra`. Run `pgrep -f TombstoneFailureThresholdMemoryTest` and expect nothing.

**B2f. Predictions.**

Let s be the bytes per serialized tombstone, about 1.0–1.05 KB. It is measured as `resp_bytes / N` at T=MAX.

**Tombstone partition (pk=0):**

| T | Outcome | count_at_throw | resp_bytes | Median allocation per read |
|---|---|---|---|---|
| 1,000 | TOE | 1,001 | — | A(1k) |
| 10,000 | TOE | 10,001 | — | A(10k) ≈ 10 × A(1k), within 7–13× |
| 20,000 | TOE | 20,001 | — | A(20k) ≈ 2 × A(10k), within 1.6–2.4× |
| 29,999 | TOE | 30,000 | — | about A(T=N) |
| 30,000 | OK | — | ≈ 30–32 MB | about A(T=N) |
| 100,000 | OK | — | same as T=30,000 | ≈ A(T=MAX), within ±10% |
| MAX | OK | — | same as T=30,000 | A(MAX) |

- For every OK read, `unfiltered_in_resp` = 30,000.
- Allocation per read: A(T) lies between 2 × s × min(T+1, N) and 6 × s × min(T+1, N). The factor covers the 1 KB clustering copy made when reading, the growth copies of the buffer (at most about 4× the content), and per-row objects.
- A(1k) should be about 2–6 MB. A(MAX) should be about 60–190 MB.
- The ordering A(1k) < A(10k) < A(20k) < A(29,999) ≈ A(30,000) ≈ A(100k) ≈ A(MAX) must hold.

**Live control (pk=1):**
- Every T gives OK, `resp_bytes` ≈ 30–32 MB and 30,000 unfiltered rows.
- The allocation is constant across T, within ±10%. The threshold does not count live rows.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| pk=0: the read throws exactly when T < N, with count = T+1; A(T) grows linearly in min(T+1, N) and is flat for T ≥ N; pk=1 is flat in T | Claim confirmed at unit level: the threshold bounds the response heap of one read in proportion to T |
| pk=0, T < N: the read throws, but A(T) ≈ A(MAX) | Claim refuted. The abort happens only after the full scan or serialization, so it does not cap memory |
| pk=0 never throws for T < N, or the count ≠ T+1 | The mechanism differs from the trace: the tombstones were purged or not counted (check `gc_grace_seconds`, and the keyspace is not a system one). The claim is not tested |
| pk=0 at T = MAX shows `resp_bytes` ≪ N × 1 KB | The tombstones are not in the response (for example, they were purged), so the threshold guards nothing here. Investigate before concluding |
| pk=1 allocation varies with T | The measurement is contaminated (JIT or GC noise). Rerun with more repetitions |
| The uncapped positive control (T=MAX) does not allocate more than T=1,000 | The workload does not exercise the memory path. Not confirmed |

**B2h. Controls.**
- **Live-row partition (pk=1):** same size, different kind of row. It isolates the effect to tombstones.
- **T=MAX (positive control):** shows that the workload really moves allocation when uncapped.
- **T = N−1 and T = N:** pin the strict `>` boundary.
- **Repetitions:** the median of 5 removes first-run and JIT effects. A single test thread, with allocation measured per thread, excludes background threads.
- **Flush before reading:** the read path is SSTable-based, as in production.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node:** one Linux node (40 cores, 251 GiB). Use `~/cassandra-run1` as `CASSANDRA_HOME`, which is already built. No rebuild is needed.
- **Run directory:** `RUN=/local/tft-run`, or any local-disk path with at least 20 GB free. Check with `df -h $RUN`, and do not put it on NFS or shared storage.
- **Configuration:**
  - Run `mkdir -p $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs,jfr}` and `cp -r ~/cassandra-run1/conf $RUN/conf`.
  - In `$RUN/conf/cassandra.yaml`, set:
    - `cluster_name: 'tft'`
    - `data_file_directories: [$RUN/data]`
    - `commitlog_directory: $RUN/commitlog`
    - `hints_directory: $RUN/hints`
    - `saved_caches_directory: $RUN/saved_caches`
    - `cdc_raw_directory: $RUN/cdc_raw`
    - `listen_address: 127.0.0.1`
    - `rpc_address: 127.0.0.1`
    - `seeds: "127.0.0.1:7100"`
    - `storage_port: 7100`
    - `ssl_storage_port: 7101`
    - `native_transport_port: 9142`
    - `read_request_timeout: 120000ms`
    - `range_request_timeout: 120000ms`. This keeps replica-side query cancellation (`ReadCommand.java:788-791`) from stopping the read first.
    - `tombstone_warn_threshold: 1000`
    - `tombstone_failure_threshold: <T>`
    - Leave `read_thresholds_enabled` unset, which means false.
  - In `$RUN/conf/cassandra-env.sh`, set `JMX_PORT="7299"`.
  - In `$RUN/conf/jvm11-server.options`, append `-Xlog:gc*,gc+heap=debug:file=/local/tft-run/logs/gc.log:time,uptime:filecount=10,filesize=50M`. G1 is the default (`jvm11-server.options:63`).
- **Heap:** `MAX_HEAP_SIZE=8G HEAP_NEWSIZE=800M`. With an 8 GiB heap, the G1 region is 4 MiB, so any buffer of 2 MiB or more is a humongous allocation, visible in the GC log and in jstat `OU`.
- **Client tools:** `~/cassandra-run1/bin/cqlsh` (uses the bundled driver zip), `bin/nodetool -p 7299`, `jstat`, `jcmd` and `jfr` from JDK 11.

**B3b. Knobs.**

The node is restarted with each yaml value. It could be changed live instead with `nodetool -p 7299 sjk mx -b org.apache.cassandra.db:type=StorageService -ms -f TombstoneFailureThreshold -v <T>`; verify any value with `-mg -f TombstoneFailureThreshold`. With N = 200,000:

| T | Why this value |
|---|---|
| 1,000 | very low |
| 20,000 | in the middle |
| 100,000 | the default |
| 300,000 | above N, so it should be the same as uncapped |
| 1,000,000 | uncapped positive control |

`concurrent_reads` stays at 32. The client sends C = 8 reads at once, so every read executes in parallel.

**B3c. Workload.**
1. **Schema:**
   - `CREATE KEYSPACE ks WITH replication={'class':'SimpleStrategy','replication_factor':1};`
   - `CREATE TABLE ks.t (pk int, ck text, v text, PRIMARY KEY (pk, ck));` with the default `gc_grace_seconds` of 864000.
2. **Data:**
   - **Partition pk=0:** N = 200,000 cell tombstones (v=null), each with a 1,000-character ck. That is about 200 MB to serialize when uncapped.
   - **Partition pk=1:** 20,000 live rows with the same kind of ck, as a control.
   - **Generating the data:** a Python 3 script writes `$RUN/ingest.cql`. It contains `BEGIN UNLOGGED BATCH` blocks of 20 inserts each (about 20.5 KB each, under `batch_size_fail_threshold` 50KiB at `conf/cassandra.yaml:1844`; this logs size warnings, which can be ignored): 10,000 batches for pk=0 and 1,000 for pk=1.
   - After loading, run `nodetool -p 7299 flush ks t`.
3. **Reads:** `CONSISTENCY ONE; SELECT * FROM ks.t WHERE pk=0;` with the default 5000-row page.
   - No live rows exist, so the first page scans all tombstones in one command.
   - Run C = 8 concurrent cqlsh processes, each issuing R = 5 sequential queries with `--request-timeout=180`. That is 40 reads per T value, lasting about 1–3 min.
   - Repeat the same for pk=1 at T=1,000 and T=1,000,000.
4. **Arithmetic:**
   - Per-read response content is s × min(T+1, N) with s ≈ 1.02 KB: about 1 MB, 20 MB, 102 MB, 204 MB and 204 MB for the five T values.
   - With 8 reads at once and buffer growth (old and new buffers both live during a copy, content × 1–3), the transient heap is about 8–25 MB, 0.16–0.5 GB, 0.8–2.4 GB, 1.6–4.9 GB and 1.6–4.9 GB.
   - All of these fit in 8 GiB, so the run should complete without out-of-memory errors.

**B3d. Observables and instruments.**
1. **Per-read response buffers (primary).** Use JFR from JDK 11: `jcmd <pid> JFR.start name=tft settings=profile filename=$RUN/jfr/T<T>.jfr`, run the storm, then `jcmd <pid> JFR.stop name=tft`. Then run `jfr print --events jdk.ObjectAllocationOutsideTLAB $RUN/jfr/T<T>.jfr` and keep the events whose stack contains `DataOutputBuffer.expandToFit` or `LocalDataResponse.build`. Per T, report:
   - the maximum `allocationSize` (the final buffer capacity, which is at least the content, at most 2× it, and 1.5× above 64 MiB);
   - the sum, divided by the 40 reads.
2. **Peak heap.** Run `jstat -gc <pid> 250` during the storm and take max(OU + EU) minus the idle baseline from the 30 s before. As a cross-check, take max(Humongous regions) × 4 MiB from `gc.log` (the `gc+heap=debug` lines "Humongous regions: a->b").
3. **Operand on the node:**
   - `system.log` lines "Scanned over <n> tombstones" (`StorageProxy.java:2247`);
   - `TombstoneFailures`, read with `nodetool -p 7299 sjk mx -b "org.apache.cassandra.metrics:type=Table,keyspace=ks,scope=t,name=TombstoneFailures" -mg -f Count`;
   - `TombstoneScannedHistogram`, with the same command using `name=TombstoneScannedHistogram`, field `Max`;
   - one traced query in cqlsh (`TRACING ON`), which shows "Read 0 live rows and <n> tombstone cells" or the abort trace.
4. **Client outcome:** `ReadFailure`/"tombstone" errors versus success, counted per T.
5. **What cannot be observed directly:** the heap retained by any single read in isolation. It is inferred from the allocation stack traces and from the concurrent peak.

**B3e. Procedure.**
1. Set up `$RUN` as in B3a with T=1,000,000. Check that ports 7100, 7101, 9142 and 7299 are free (`ss -ltn`).
2. Start the node: `CASSANDRA_CONF=$RUN/conf CASSANDRA_LOG_DIR=$RUN/logs MAX_HEAP_SIZE=8G HEAP_NEWSIZE=800M ~/cassandra-run1/bin/cassandra -p $RUN/cassandra.pid`. Wait for `nodetool -p 7299 status` to show UN.
3. Create the schema. Generate `ingest.cql` and run `bin/cqlsh 127.0.0.1 9142 --request-timeout=120 -f $RUN/ingest.cql`. Flush.
4. Check that all 200,000 tombstones are visible to the read:
   - run `TRACING ON; SELECT * FROM ks.t WHERE pk=0;` and expect "Read 0 live rows and 200000 tombstone cells";
   - check `du -sh $RUN/data`, about 0.2–0.3 GB.
5. For each T in {1,000,000; 300,000; 100,000; 20,000; 1,000}:
   1. Stop the node (`kill $(cat $RUN/cassandra.pid)`, then wait for the process to exit).
   2. Set T in the yaml and start the node again. Confirm T with `sjk mx -mg`.
   3. Do one warm-up read.
   4. Measure 30 s of idle `jstat`.
   5. Start JFR.
   6. Launch the 8 × 5 storm (`for i in $(seq 8); do (for r in $(seq 5); do bin/cqlsh 127.0.0.1 9142 --request-timeout=180 -e "CONSISTENCY ONE; SELECT * FROM ks.t WHERE pk=0;" > $RUN/logs/c_${T}_$i_$r.out 2>&1; done) & done; wait`) with `jstat -gc <pid> 250 > $RUN/logs/jstat_$T.txt` running alongside.
   7. Stop JFR. Record the metrics and the system.log lines.
6. Live control: at T=1,000 and T=1,000,000, run the same storm against pk=1.
7. Stop the node and check that `pgrep -f "$RUN"` returns nothing.

**B3f. Predictions.**

With s about 1.02 KB, N = 200,000 and C = 8:

| T | Client outcome | "Scanned over" n | Max response buffer (JFR) | Peak heap rise over baseline |
|---|---|---|---|---|
| 1,000 | all 40 fail | 1,001 | ≤ 2 MB (no humongous growth) | ≤ 0.1 GB |
| 20,000 | all 40 fail | 20,001 | about 20–41 MB | about 0.16–0.5 GB |
| 100,000 | all 40 fail | 100,001 | about 102–205 MB | about 0.8–2.4 GB |
| 300,000 | all 40 succeed (0 rows) | no failures; histogram Max = 200,000 | about 204–410 MB | about 1.6–4.9 GB |
| 1,000,000 | all 40 succeed (0 rows) | no failures; histogram Max = 200,000 | same as T=300,000 | same as T=300,000, within ±15% |

- `TombstoneFailures` grows by 40 for each of the three failing T values.
- JFR bytes allocated per read: ratio(20k : 1k) ≈ 20 (14–26); ratio(100k : 20k) ≈ 5 (3.5–6.5); ratio(1M : 300k) ≈ 1.
- The live control (pk=1) is identical at T=1,000 and T=1,000,000 (within ±15%). Every read succeeds and returns 5,000 rows on the first page.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| The buffer size and peak-heap rise follow min(T+1, N): they shrink about in proportion to T below N and are flat above N; the live control is flat | Confirmed: the threshold governs the replica's on-heap response memory for tombstone-heavy reads |
| Reads abort at T < N, but the JFR buffer sizes or peak heap equal those at T=1M | Refuted: the abort does not prevent the allocation |
| Reads succeed at T < N | The constraint is not applied: wrong config loaded, tombstones purged, or a system keyspace. Not tested; fix and rerun |
| The positive control (T=1M) shows no humongous allocations or heap rise over T=1,000 | The workload does not exercise the response buffer. Not confirmed |
| Peak heap rises with T, but by much more than C × 3 × content | Another consumer (for example, cqlsh paging state or the coordinator merge) dominates. The direction is still confirmed; report the extra |
| Out-of-memory or long GC pauses only at T ≥ 300k | Consistent with the claim: the default protects heap that an uncapped read would exhaust |

**B3h. Controls.**
- **Live-row partition:** same row size; not counted, so it should be unaffected.
- **T above N at two values (300k and 1M):** shows the plateau, so the effect is due to the cap rather than to T itself.
- **Measurement baseline:** a 30 s idle baseline, and a restart for every T so leftover garbage does not carry over.
- **Read path:** the request timeout is raised so cancellation does not cut reads short, and `read_thresholds_enabled` is off so the byte-based local read size cap does not interfere.
- **Data placement:** one node with RF=1, so the reads take the local path at `StorageProxy.java:2208-2212`.
- **Data state:** flushed SSTables, and compaction does not purge anything because `gc_grace_seconds` has not passed.

**B4. Risks and cleanup.**
- **Disk:** the unit tier uses about 60 MB under `~/cassandra-run1/build/test`. The cluster tier uses about 0.5 GB of data and commit log, plus up to 500 MB of GC logs and about 1 GB of JFR files, all under the local `$RUN`.
- **Shared storage:** nothing is written to the shared source tree or to shared storage.
- **Heap:** the uncapped T values are sized to fit in an 8 GiB heap. If an out-of-memory error occurs, the node dies and must be restarted. It touches only `$RUN`.
- **Leftover processes:** cqlsh background loops are joined by `wait`. Kill any stragglers with `pkill -f "cqlsh 127.0.0.1 9142"`.
- **Cleanup:**
  - stop the node with `kill $(cat $RUN/cassandra.pid)`;
  - check that `pgrep -f "$RUN"` and `pgrep -f TombstoneFailureThresholdMemoryTest` return nothing;
  - `rm -rf $RUN`;
  - remove the added test file and `build/test/tft-unit.tsv` from `~/cassandra-run1`.

**Audit amendments (stage 4 step 0, 2026-10-21).** Made before any run or reading; each leaves B1 and the claim as filed. Where an amendment changes a step, defines a term or adds a row, it says so, and it governs over the text above (the results file §1.1 gives the reason for each).

- **R1 (B2c, B2e test, B3c, B3e step 4, B3f: write the tombstones without a row marker).** An `INSERT` always writes the row's primary-key liveness info (`cql3/statements/UpdateStatement.java:73-74`), so `INSERT … VALUES (0, ck, null)` makes a **live** row that carries one cell tombstone (`BTreeRow.hasLiveData`). Live rows count toward the page limit, and `cqlsh` pages at **100** rows, not 5,000 (`pylib/cqlshlib/cqlshmain.py:362`, `:945`). Each command would then scan at most 100 tombstones and no T ≥ 100 could ever abort, so the cluster tier could not reach the limit; B1 also asks for "no live rows". **Fix, both tiers:** the tombstone partition is written with `UPDATE … SET v = null WHERE pk = 0 AND ck = ?` (a cell tombstone and no liveness info; still counted once per row at `ReadCommand.java:559-566`). In B2e the test line is `execute("UPDATE %s SET v = null WHERE pk = 0 AND ck = ?", ck(i));`; in B3c the generated batches hold `UPDATE ks.t SET v = null WHERE pk = 0 AND ck = '<ck>';`. The live control (pk = 1) keeps `INSERT … v = ''`. B3c's "default 5000-row page" reads "cqlsh's 100-row page (irrelevant for pk = 0, which has no live rows)"; B3f's pk = 1 line "returns 5,000 rows on the first page" reads "returns all 20,000 rows".
- **R2 (B2e test: static initialisation).** `static final int ORIGINAL = DatabaseDescriptor.getTombstoneFailureThreshold();` runs when the class loads, before `CQLTester.setUpClass()` → `daemonInitialization` (`CQLTester.java:403-414`); `DatabaseDescriptor.conf` is still null then (`DatabaseDescriptor.java:2842-2845`), so the class would fail with `ExceptionInInitializerError`. **Fix:** `ORIGINAL` becomes a non-final static set in a `@BeforeClass` method (JUnit runs the superclass's first). The test is otherwise as filed apart from R1; it is kept as `harness/…/TombstoneFailureThresholdMemoryTest.java`.
- **R3 (B3a: client and file limits).** Add `native_transport_timeout: 180s` to the yaml (default 12 s, `Config.java:1399`; an uncapped 200 MB read plus its coordinator-side decoding may approach it, and B3a already raises the read timeouts for the same reason). Start the node from a shell with `ulimit -n 100000` (the node's default soft limit is 1024).
- **R4 (B2f–B3g: statistics and the meaning of "follows").** Defined before any reading:
  - **Unit, B2g row 1** holds when: pk = 0 throws for exactly T ∈ {1k, 10k, 20k, 29,999} with count = T+1 in all 5 reps; A(1k) < A(10k) < A(20k) < A(29,999); A(1k) ≤ 0.10 × A(MAX); A(29,999), A(30,000) and A(100k) are each within ±10 % of A(MAX); every OK read has `unfiltered_in_resp` = 30,000; and pk = 1's max/min of A over the 7 T values ≤ 1.10. B2f's ratio bands (7–13×, 1.6–2.4×), the 2–6 × s × min(T+1, N) band and the MB figures are sub-predictions: reported, not decisive. **B2g row 2** ("A(T) ≈ A(MAX)") means A(1k) ≥ 0.5 × A(MAX).
  - **Cluster, "follows min(T+1, N)" in B3g row 1** means all of: (a) at T = 1k, 20k, 100k all 40 storm reads fail and each failing read logs "Scanned over T+1 tombstones", and at 300k and 1M all 40 succeed; (b) the per-T maximum JFR response buffer is strictly ordered 1k < 20k < 100k < 300k, with 1M within ±15 % of 300k, and for each failing T it is at most 2.2 × s × (T+1) (s = bytes per tombstone, taken from the unit tier as `resp_bytes / 30,000` at T = MAX, which has the same row layout); (c) the peak-heap rise is ordered 1k < 20k < 100k < 300k, with 1M within ±15 % of 300k; (d) the live control's maximum buffer and its peak-heap rise at T = 1k are within ±15 % of those at 1M (or both under 4 MiB). B3f's bands and ratios are sub-predictions.
  - **Peak-heap rise** = max(OU + EU) over the storm's `jstat` samples minus the **median** of OU + EU over the 30 s idle window before it; OU alone (where humongous buffers live) is reported beside it. **TombstoneFailures** is read after the warm-up read and after the storm; B3f's "+40" is that difference (the warm-up read of a failing T also fails and counts once).
  - **Order within a lifetime (B3e steps 5–6):** warm-up read, 30 s idle `jstat`, JFR, pk = 0 storm, JFR stop and metrics; then, in the T = 1M and T = 1k lifetimes only, a second 30 s idle window, a second JFR recording, the pk = 1 storm, and its stop.
- **R5 (B3d: supplementary observable).** JFR's `ObjectAllocationOutsideTLAB` events miss allocations that fit in a TLAB, so their sum under-counts small buffers (T = 1k). As the cluster analogue of B2d item 3, a JMX client reads `ThreadMXBean.getThreadAllocatedBytes` summed over all live threads of the node before and after each storm; divided by the 40 reads it is the **node allocation per read** (it also includes the coordinator's decoding and each `cqlsh` connection's own reads, constant across T). Reported with B3f's per-read ratios; it does not decide a row on its own.
- **R6 (B2g, B3g: added rows).**
  - B2g: | pk = 0 throws as predicted, but A(1k) lies between 0.10 and 0.50 × A(MAX), or the order A(1k) < A(10k) < A(20k) < A(29,999) is broken | Not confirmed: the abort saves only part of the allocation, or the instrument is too noisy to show the relation |
  - B3g: | (a) and (b) of R4 hold, but (c) does not (the peak-heap rise does not separate the T values) | Per-read cap confirmed, node-level peak not shown: **Not confirmed (partial)** for B1 item 2's second sentence; Effect "caps" (per read) |
  - B3g: | (a) holds but (b) does not (the maximum buffer does not follow T, or exceeds 2.2 × s × (T+1) at a failing T) | Not confirmed: the response buffer is not what the threshold bounds; check the JFR stacks for the allocating frame |

**Runbook fixes (stage 4, 2026-10-21; B1 and B2f–B3g unchanged; the affected tier restarts from its beginning).** Results file §3 has the evidence.

- **D1 (B2a/B2e: the unit JVM's read thresholds).** The unit tests' yaml enables the byte-based read thresholds (`test/conf/cassandra.yaml:63-69`: `read_thresholds_enabled: true`, `row_index_read_size_fail_threshold: 8192KiB`, `local_read_size_fail_threshold: 8192KiB`), unlike the node default (`Config.java:526`, false), which A4 and B3a assume. The 30,000-row partition's row index (≈ 12.6 MB estimated in memory, 6,000 entries of 1 KB clusterings) aborts every pk = 0 read at `RowIndexEntry.java:401` before the tombstone check is reached. **Fix:** the test calls `DatabaseDescriptor.setReadThresholdsEnabled(false)` in its `@BeforeClass` (restored in `@AfterClass`), which returns `RowIndexEntry.checkSize` at `:380` as on a default node. The unit tier restarts.

- **D2 (B3a/B3d, R4 (c): the shipped G1 options; found by the cluster instrument check, before any cluster reading).** B3a assumes G1's default sizing ("the G1 region is 4 MiB"), but the copied `conf/jvm11-server.options` sets `-XX:G1HeapRegionSize=16m` (`:66`) and `-XX:G1NewSizePercent=50` (`:70`). So with an 8 GiB heap the region is 16 MiB (an object is humongous from 8 MiB), and eden is at least 4 GiB. Max(EU + OU) over a storm is then bounded by eden filling with any garbage (a read allocates several times its buffer: every row is deserialized before it is serialized, and every growth step of the buffer copies it, `DataOutputBuffer.java:173-182`), so it measures allocation pressure rather than the buffers held. **Fix:** the node keeps the shipped options (B3a copies `conf/` as is); R4's criteria (c) and (d) are read on the **OU (old generation) peak rise**, where the response buffers of 8 MiB or more are allocated directly as humongous regions; the EU + OU rise is still reported and compared with B3f's bands as filed. The `gc.log` cross-check counts humongous regions × 16 MiB. B1 and B3f are unchanged; R6's added row (peak heap not shown) applies to the OU reading.

- **D3 (B3d item 2: `jstat` cannot attach).** The shipped `conf/jvm-server.options` sets `-XX:+PerfDisableSharedMem`, so `jstat -gc <pid>` fails with "MonitorException: <pid> not found" (seen in the cluster instrument check). **Fix:** the same two quantities, EU and OU, are read every 250 ms from the node's JMX memory pools (`G1 Eden Space`, `G1 Old Gen` usage) by the harness's `HeapPoll`; the idle window and the storm window are as in B3e and R4. B1 and B3f are unchanged.

Environment for run 1 (not an amendment): the clone is a fresh `~/cassandra-tft` at `cassandra-5.0.9` built with `ant build-test`, used for both tiers instead of `~/cassandra-run1`; `RUN=/local/tft-run` as filed (local `/dev/sda3`).

## C. Sources read

- src/java/org/apache/cassandra/db/ReadCommand.java
- src/java/org/apache/cassandra/db/ReadResponse.java
- src/java/org/apache/cassandra/db/ReadCommandVerbHandler.java
- src/java/org/apache/cassandra/service/StorageProxy.java
- src/java/org/apache/cassandra/service/StorageService.java
- src/java/org/apache/cassandra/service/StorageServiceMBean.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
- src/java/org/apache/cassandra/io/util/DataOutputBuffer.java
- src/java/org/apache/cassandra/db/filter/TombstoneOverwhelmingException.java
- src/java/org/apache/cassandra/schema/SchemaConstants.java
- src/java/org/apache/cassandra/db/partitions/PurgeFunction.java
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
- src/java/org/apache/cassandra/metrics/TableMetrics.java
- src/java/org/apache/cassandra/tools/nodetool/Sjk.java
- src/java/org/apache/cassandra/service/reads/thresholds/WarningsSnapshot.java
- conf/cassandra.yaml, conf/cassandra_latest.yaml, conf/cassandra-env.sh, conf/jvm11-server.options, conf/jvm-server.options
- bin/cassandra, bin/cassandra.in.sh
- build.xml
- CHANGES.txt, NEWS.txt
- doc/modules/cassandra/pages/managing/operating/metrics.adoc
- test/unit/org/apache/cassandra/cql3/validation/miscellaneous/TombstonesTest.java
- test/unit/org/apache/cassandra/Util.java
- https://issues.apache.org/jira/browse/CASSANDRA-6117 (cited from CHANGES.txt, not fetched)

## D. Stage-4 feedback

**2026-10-21 — run 1 closed: unit Confirmed — caps (per read); cluster Not confirmed (partial) — caps per read, node-level peak not shown** (the R6 row added to B3g by the audit; no run 2). Results: [`results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md`](../../stage4-runtime-verification/results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md); harness `stage4-runtime-verification/harness/tombstone_failure_threshold-countTombstone-tombstones--autonomous/`. Run on `pc13` from a fresh clone `~/cassandra-tft` (environment deviation E1). The unit tier ran on sha256 `677b8abb…` (after D1), the cluster tier on `b509de1d…` (after D2–D3).

- **Unit (B2g row 1).** T < 30,000 throws with exactly T+1 counted; allocation per read 4.10 · 53.36 · 106.68 · 126.39 MB at T = 1k · 10k · 20k · 29,999 against 125.89 MB at T ≥ N (s = 1,009.6 B per tombstone); the live control is flat (1.014). Missed: A(10k)/A(1k) = 13.01 (band 7–13).
- **Cluster.** (a) 40/40 reads abort with "Scanned over T+1" at T = 1k · 20k · 100k, 40/40 succeed at 300k · 1M. (b) The replica's response buffer (JFR, `DataOutputBuffer.expandToFit`) peaks at 1.0 · 32.1 · 144.3 · 216.4 · 216.4 MiB: B1 item 2's per-read part holds. (c) The node-level peak does not follow T beyond 20k: the old generation rose 0.25 · 4,009 · 6,050 · 6,015 · 6,262 MB, filled with humongous garbage from eight concurrent readers up to the GC trigger, so B1 item 2's node-level sentence is not shown. Every B3f peak-heap band missed; the JFR out-of-TLAB per-read ratio 20k:1k (174.6) and the node-allocation ratio (12.9, band 14–26) missed.
- **Defects in this file found by stage 4.**
  - Before run 1 (audit, applied above): R1 — `INSERT … null` writes live rows and `cqlsh` pages at 100 rows, so the cluster tier could never reach any T ≥ 100; R2 — the filed test cannot initialise (`DatabaseDescriptor.conf` is null in a static initialiser); R3–R6 timeouts, undefined statistics and missing rows.
  - Runbook fixes: D1 the unit test yaml's 8 MiB read thresholds abort the read first; D2 the shipped G1 options (16 MiB regions, ≥ 50 % young) make the EU + OU peak an allocation measure; D3 `jstat` cannot attach under `-XX:+PerfDisableSharedMem`.
  - Not applied (stage 3): S1 the `ReadCommand` citations `:528`, `:531`, `:558-565`, `:587-602` are one line low (the entry pointer `:591` is right); S2 at T = 1k the buffer is 1 MiB, not humongous; S3 a held-heap reading (a held read plus a class histogram) would be needed to test the node-level sentence.
- **Effect.** The threshold caps each read command's response memory at about (T+1) × one tombstone's serialized size (≈ 144 MiB at the default with 1 KB tombstones). It does not cap the node's heap under concurrent tombstone-heavy reads: at the default it churned the heap as much as uncapped reads did.
