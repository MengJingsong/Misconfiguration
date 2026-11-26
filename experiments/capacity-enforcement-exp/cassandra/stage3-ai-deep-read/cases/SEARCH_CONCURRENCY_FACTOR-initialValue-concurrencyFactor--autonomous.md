# SEARCH_CONCURRENCY_FACTOR — verification solution  <!-- file: cases/SEARCH_CONCURRENCY_FACTOR-initialValue-concurrencyFactor--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the SASI per-thread search-pool switch and size, **linked**: [`TermIterator.java:57-59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/TermIterator.java#L57-L59) (`concurrencyFactor <= 1 ? ImmediateExecutor.INSTANCE : executorFactory().pooled(currentThread + "-SEARCH-", concurrencyFactor)`) |
| Pinned source | `cassandra-5.0.9` |
| Lead source | config-first |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code via Agent SDK (CLI version not exposed to the agent), 2026-11-26 |
| Estimate | `positive`, for thread memory only: the value is the maximum thread count of a SASI search pool, and each calling thread (a ReadStage worker) gets one such pool. So the number of `-SEARCH-` threads, and their native stack and thread memory, is capped at N per calling thread and rises with N (none at N ≤ 1). It does **not** bound the heap that SASI search results use. The same per-SSTable iterators are kept whatever N is, and the number of calling threads is not limited by this entry. |
| Ground | — |

> **Scope of the claim.** The memory this entry governs is native thread memory (stack reservation plus
> JVM per-thread structures, NMT category `Thread`), not heap or disk. The cap is **per calling thread**. The
> node-wide total is N × W, where W is the number of distinct threads that ran a SASI search in the last
> keep-alive minute. W is set by the SharedPool/ReadStage, not by this entry.

## A. Constraint trace

**A1. The constraint.** `SEARCH_CONCURRENCY_FACTOR` is a JVM system property, `-Dcassandra.search_concurrency_factor`.
It is declared at
[`CassandraRelevantProperties.java:483`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L483)
as `SEARCH_CONCURRENCY_FACTOR("cassandra.search_concurrency_factor", "1")`.
- Unit: a count of threads (the maximum pool size of one SASI search executor).
- Default: `"1"`, a literal string default. It is parsed by `getInt()` at `CassandraRelevantProperties.java:794-800`, which uses the system property if set and otherwise the default. A non-integer value throws when `DatabaseDescriptor` is class-initialised.
- How to set it: only with `-D` at JVM start (`JVM_EXTRA_OPTS` or `conf/jvm-server.options`). It is not in `cassandra.yaml` and has no JMX or nodetool setter.
- Restart needed: yes. The value is read once into `private static final int searchConcurrencyFactor` at `DatabaseDescriptor.java:220`. Each search pool is also built only once per calling thread (A3), so the pools of a running node never change size.

**A2. What it caps.**
- Resource: native (off-heap, non-`direct`) memory for threads. Each pool thread has a stack reservation (`-Xss256k`, `conf/jvm-server.options:123`) that is only partly committed, plus JVM thread structures. Linux counts it in RSS and NMT counts it under `Thread`.
- Quantity compared with the limit: the pool's `poolSize`, i.e. the number of live worker threads in one `ThreadPoolExecutor`. The JDK `ThreadPoolExecutor` compares `workerCount` with `corePoolSize` / `maximumPoolSize` on each `execute()`. Here both are N (A3), so a pool never has more than N threads.
- The switch is `N <= 1`. In that case no pool exists, and the searches run inline on the calling thread (`ImmediateExecutor`).

**A3. Mechanism.**
1. `DatabaseDescriptor.java:220`: `searchConcurrencyFactor = SEARCH_CONCURRENCY_FACTOR.getInt()`. `DatabaseDescriptor.java:4392-4395` is its getter, `searchConcurrencyFactor()`.
2. `TermIterator.java:48-61`: `SEARCH_EXECUTOR` is a `FastThreadLocal<ExecutorService>`, so every thread that runs a SASI search gets **its own** executor in `initialValue()`. Line 53 reads the factor and line 55 logs `Search Concurrency Factor is set to {} for {}` at INFO, once per calling thread.
3. **The check:** [`TermIterator.java:57-59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sasi/TermIterator.java#L57-L59).
   - If `concurrencyFactor <= 1`, it uses `ImmediateExecutor.INSTANCE` and creates no threads.
   - Otherwise it calls `executorFactory().pooled(currentThread + "-SEARCH-", concurrencyFactor)`.
4. `ExecutorFactory.java:281` leads to `ThreadPoolExecutorBuilder.pooled(ThreadPoolExecutorPlus::new, …, name, threads)` (`ThreadPoolExecutorBuilder.java:57-60`). The builder settings are:
   - `coreThreads() = threads` (`:175-178`) and `maxThreads() = threads` (`:180-183`).
   - An unbounded queue, `Integer.MAX_VALUE` (`:160-168`).
   - `keepAlive = 1 MINUTES` and `allowCoreThreadTimeouts = true` (`:73-75`), applied at `ThreadPoolExecutorBase.java:75-76`.

   So each pool has core = max = N, threads idle for more than 60 s exit, and task N+1 onward waits in the queue instead of getting a thread.
5. `TermIterator.build` (`TermIterator.java:79-163`) is called once per expression from `QueryController.getIndexes` (`QueryController.java:146`). For each `SSTableIndex` that matches the term (`View.match`, `View.java:94-97`), it references the index (`:108`) and submits one task (`:118`) that runs `index.search(e)` (`:123`). The calling thread then blocks on a latch (`:147`). With M matching SSTables there are M tasks. Because the JDK `ThreadPoolExecutor` creates a new thread on each `execute()` while `poolSize < corePoolSize`, the first query brings the pool to **min(N, M)** threads.
6. **Which threads own pools.** Range reads (all SASI queries without a partition-key restriction) run locally as `Stage.READ.execute(new LocalReadRunnable(...))` (`RangeCommandIterator.java:207`). These run on SharedPool workers (`SEPWorker`), which take the name `ReadStage-<workerId>` while they serve ReadStage (`SEPWorker.java:124-125`; `SET_SEP_THREAD_NAME` defaults to true, `CassandraRelevantProperties.java:492`). So pools are named `ReadStage-<id>-SEARCH-` and their threads `ReadStage-<id>-SEARCH-:<k>` (`NamedThreadFactory.java:112`). ReadStage runs at most `concurrent_reads` (default 32, `conf/cassandra.yaml:722`; `Stage.java:45`) tasks at a time. SEP workers are parked, not ended, when idle (`SharedExecutorPool.java:85`; they end only at shutdown, `:170`), so over time more distinct workers than `concurrent_reads` can own a pool.
7. **Bypass and overshoot.**
   - The cap applies **per pool**. The entry does not limit the number of pools, and pools are never shut down; only their threads time out. The node-wide search-thread count is ≤ N × W, where W is the number of distinct workers that searched within the last 60 s. That W is bounded only by the SharedPool size.
   - Queued tasks beyond N are small `Runnable`s held in an unbounded queue. There are at most M per build, and they are not bounded by N.
   - The heap used by search results is **not** affected. `tokens` (`:81`, `:130`) collects every SSTable's iterator before the union is built (`:152`), whatever N is.

**A4. Other consumers.** The same native thread memory is also used by every other JVM thread: the SharedPool/SEP workers (ReadStage, MutationStage, …), Native-Transport-Requests, compaction, memtable flush, GC and JIT threads. Their counts are bounded by `concurrent_reads`, `concurrent_writes`, `native_transport_max_threads`, `concurrent_compactors` and the JVM's own settings, not by this entry. SASI's search-result heap and its memory-mapped index files (page cache, not counted against the JVM heap) are also outside this entry.

**A5. Evidence beyond the source.**
- `doc/SASI.md:567-570` and `doc/modules/cassandra/pages/developing/cql/SASI.adoc:548-550`: "SASI also supports concurrently iterating terms for the same index across SSTables. The concurrency factor is controlled by the `cassandra.search_concurrency_factor` system property. The default is `1`."
- JDK 11 `ThreadPoolExecutor` Javadoc (core/max pool sizes, new thread per submission below core, `allowCoreThreadTimeOut`): https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html
- JDK 11 Native Memory Tracking (NMT `Thread` category): https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html
- No test in the tree sets this property: `grep -rn search_concurrency_factor test` returns nothing.

## B. Verification solution

**B1. Claim under test.**
- With `-Dcassandra.search_concurrency_factor=N`, every SASI search pool holds **at most N threads** and reaches min(N, M) threads under a query touching M SSTables. At N ≤ 1 no search thread exists.
- So the node's search-thread count, and the NMT `Thread` memory above baseline, grows in proportion to N × W (W = distinct calling threads) and returns to baseline after 60 s idle.
- The claim is wrong if any pool exceeds N threads, if N > 1 creates no pool threads, if N = 1 creates any, or if thread memory does not scale with the search-thread count.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Copy the tree to local disk and build in the copy only: `rsync -a <shared>/cassandra-5.0.9/ /mydata/scf/src/ && cd /mydata/scf/src && ant build-test`.
- The probe below goes into the **copy**, at `/mydata/scf/src/test/unit/org/apache/cassandra/index/sasi/SearchConcurrencyFactorProbeTest.java`.
- `test/conf/cassandra.yaml:52` already has `sasi_indexes_enabled: true`.
- The property must be on the JVM command line, because it is read into a `static final` when `DatabaseDescriptor` initialises, which `CQLTester` does before the test body runs. Pass it through `test.jvm.args`, which `build.xml:1192` adds to the test JVM.

**B2b. Knobs.** N = `cassandra.search_concurrency_factor`, run at {1, 4, 16, 64, 128}, one JVM per value.
- 1 is the default: no pool.
- 4, 16 and 64 test proportionality.
- 128 is above M = 64, which separates "the cap is N" from "threads = tasks".

Set each value with `-Dtest.jvm.args="-Dcassandra.search_concurrency_factor=N -Dprobe.out=/mydata/scf/unit/probe-N.txt"`.

**B2c. Workload.**
- One table with a SASI index on `v` and compaction disabled.
- M = 64 flushes of 50 rows each, so 64 SSTables (3 200 rows in total).
- Each SSTable holds exactly one row with `v = 'hot'`, so every SSTable index matches the term and `TermIterator.build` submits 64 tasks per query.
- Q = 20 `SELECT k FROM %s WHERE v = 'hot'` queries.

Arithmetic: tasks per build = 64 ≥ N for N ≤ 64, so the pool must reach exactly N threads. For N = 128 it reaches 64 (task-limited), while `getMaximumPoolSize()` reports 128. `CQLTester.execute` runs through `QueryProcessor.executeInternal` (`CQLTester.java:1634-1643`) on the calling (JUnit `main`) thread, so there is exactly one pool, `main-SEARCH-`, and W = 1.

**B2d. Observables and instruments.**
- (1) The calling thread's executor, read by reflection on `TermIterator.SEARCH_EXECUTOR` after the queries, in the same thread: its class, `getLargestPoolSize()`, `getMaximumPoolSize()` and `getCorePoolSize()`.
- (2) A 2 ms sampler over `Thread.getAllStackTraces()` that records the peak count and the distinct names of threads whose names contain `-SEARCH-`.
- (3) `getPoolSize()` 75 s after the last query, to check that the keep-alive releases the threads.
- (4) `DatabaseDescriptor.searchConcurrencyFactor()`, to confirm that the property took effect.

Native memory is not measured in this tier (see B3).

Probe source:
```java
package org.apache.cassandra.index.sasi;

import java.io.FileWriter;
import java.lang.reflect.Field;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import io.netty.util.concurrent.FastThreadLocal;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.CQLTester;

public class SearchConcurrencyFactorProbeTest extends CQLTester
{
    private static final int M = 64, ROWS = 50, Q = 20;

    @Test
    @SuppressWarnings("unchecked")
    public void probe() throws Throwable
    {
        int n = DatabaseDescriptor.searchConcurrencyFactor();
        createTable("CREATE TABLE %s (k int PRIMARY KEY, v text)");
        createIndex("CREATE CUSTOM INDEX ON %s (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode': 'PREFIX'}");
        disableCompaction();
        for (int s = 0; s < M; s++)
        {
            for (int r = 0; r < ROWS; r++)
                execute("INSERT INTO %s (k, v) VALUES (?, ?)", s * 1000 + r, r == 0 ? "hot" : "v" + s + "_" + r);
            flush();
        }
        int live = getCurrentColumnFamilyStore().getLiveSSTables().size();

        AtomicBoolean stop = new AtomicBoolean();
        AtomicInteger peak = new AtomicInteger();
        Set<String> names = ConcurrentHashMap.newKeySet();
        Thread sampler = new Thread(() -> {
            while (!stop.get())
            {
                int c = 0;
                for (Thread t : Thread.getAllStackTraces().keySet())
                    if (t.getName().contains("-SEARCH-")) { c++; names.add(t.getName()); }
                peak.accumulateAndGet(c, Math::max);
                try { Thread.sleep(2); } catch (InterruptedException e) { return; }
            }
        }, "probe-sampler");
        sampler.start();
        int rows = -1;
        for (int i = 0; i < Q; i++)
            rows = execute("SELECT k FROM %s WHERE v = 'hot'").size();
        stop.set(true);
        sampler.join();

        Field f = TermIterator.class.getDeclaredField("SEARCH_EXECUTOR");
        f.setAccessible(true);
        ExecutorService ex = ((FastThreadLocal<ExecutorService>) f.get(null)).get();
        boolean tpe = ex instanceof ThreadPoolExecutor;
        int largest = tpe ? ((ThreadPoolExecutor) ex).getLargestPoolSize() : 0;
        int max = tpe ? ((ThreadPoolExecutor) ex).getMaximumPoolSize() : 0;
        int core = tpe ? ((ThreadPoolExecutor) ex).getCorePoolSize() : 0;
        Thread.sleep(75_000);
        int after = tpe ? ((ThreadPoolExecutor) ex).getPoolSize() : 0;

        String line = String.format("PROBE N=%d M=%d liveSSTables=%d rows=%d executor=%s core=%d max=%d largestPoolSize=%d peakSearchThreads=%d distinctSearchThreadNames=%d poolSizeAfter75s=%d%n",
                                    n, M, live, rows, ex.getClass().getName(), core, max, largest, peak.get(), names.size(), after);
        System.out.print(line);
        try (FileWriter w = new FileWriter(System.getProperty("probe.out"), true)) { w.write(line); }
    }
}
```

**B2e. Procedure.**
1. Run `mkdir -p /mydata/scf/unit && cd /mydata/scf/src`, and check free space with `df -h /mydata`. The test writes under `build/test/` in the copy, less than 200 MB.
2. Run `ant build-test` once.
3. For N in 1 4 16 64 128, run:
   `ant testsome -Dtest.name=org.apache.cassandra.index.sasi.SearchConcurrencyFactorProbeTest -Dno-build-test=true -Dtest.jvm.args="-Dcassandra.search_concurrency_factor=$N -Dprobe.out=/mydata/scf/unit/probe-$N.txt"`
4. Run `cat /mydata/scf/unit/probe-*.txt`. Also check the test log under `build/test/logs/` for `Search Concurrency Factor is set to N for main` (it appears only for N > 1 runs that reach the pool; for N = 1 it still logs, with N = 1).
5. Positive and instrument control (B2h): run the probe again at N = 16 with `M` edited to 8 (or a copy of the class with `M = 8`). This gives an expected `largestPoolSize = 8`.
6. Run `pgrep -f 'junit.*SearchConcurrencyFactorProbeTest'` and check that it returns nothing.

**B2f. Predictions.**

| N | executor | core = max | largestPoolSize | peakSearchThreads | distinct names | poolSizeAfter75s |
|---|---|---|---|---|---|---|
| 1 | `ImmediateExecutor` | 0 | 0 | 0 | 0 | 0 |
| 4 | `ThreadPoolExecutorPlus` | 4 | 4 | 4 | 4 | 0 |
| 16 | `ThreadPoolExecutorPlus` | 16 | 16 | 16 | 16 | 0 |
| 64 | `ThreadPoolExecutorPlus` | 64 | 64 | ≤ 64 (sampler may miss a few) | 64 | 0 |
| 128 | `ThreadPoolExecutorPlus` | 128 | 64 (task-limited) | ≤ 64 | 64 | 0 |
| 16, M = 8 (control) | `ThreadPoolExecutorPlus` | 16 | 8 | ≤ 8 | 8 | 0 |

In every run `rows = M` and `liveSSTables = M`. In general, `largestPoolSize = min(N, M)` and it is never greater than N.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| largestPoolSize = min(N, M) for every N, and 0 / `ImmediateExecutor` at N = 1 | The mechanism works as traced: N caps the per-pool thread count (claim supported). |
| largestPoolSize or distinct names > N for any N | **The claim is wrong.** Something other than this pool creates search threads, or the cap leaks. |
| N > 1 but executor is `ImmediateExecutor` / no `-SEARCH-` threads | **The claim is wrong** for this build, or the property did not reach the JVM. Check `searchConcurrencyFactor()` in the PROBE line. |
| PROBE line shows N different from the value passed | The property was not applied. The run is invalid, so re-run. |
| liveSSTables < M or rows < M | The workload did not reach the boundary (compaction or flush issue), so the run is not conclusive. |
| poolSizeAfter75s > 0 | The keep-alive did not release the threads. The cap still holds, but the "returns to baseline" part of B1 is wrong. |
| Control (M = 8) gives largestPoolSize = 8 while N = 16 gives 16 | The instruments see pool size move with the number of tasks. This shows the N-runs measure N, not a fixed count. |

**B2h. Controls.**
- N = 1 is the zero baseline: the same workload with no pool.
- N = 128 > M separates the cap from the number of tasks.
- The M = 8 control shows the instrument moving with a different, known bound (submitted tasks).
- The PROBE line records `searchConcurrencyFactor()`, which excludes a property that was set but not read.
- One fresh JVM per N, because the value is `static final` and pools are per thread and never rebuilt.
- The sampler filters on the literal `-SEARCH-`. No other executor in the tree uses that suffix (`grep -rn '"-SEARCH-"' src` matches only `TermIterator.java:59`).

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11 and at least 8 GB RAM. Build from the local copy at `/mydata/scf/src` with `ant jar`. Run data goes on local disk under `/mydata/scf/node/`.
- In the copy, edit `conf/cassandra.yaml`:
  - `sasi_indexes_enabled: true`
  - `data_file_directories: [/mydata/scf/node/data]`
  - `commitlog_directory: /mydata/scf/node/commitlog`
  - `saved_caches_directory: /mydata/scf/node/saved_caches`
  - `hints_directory: /mydata/scf/node/hints`
  - `cdc_raw_directory: /mydata/scf/node/cdc_raw`
  - Keep `concurrent_reads: 32` (the default).
- Leave the listen and RPC addresses at localhost. If `ss -ltn` shows 7000, 9042 or 7199 in use, set `storage_port: 7010` and `native_transport_port: 9142`, and `JMX_PORT=7299` in `conf/cassandra-env.sh`.
- Logs: `export CASSANDRA_LOG_DIR=/mydata/scf/node/logs`.
- Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=200M`.
- JVM options per run: `export JVM_EXTRA_OPTS="-Dcassandra.search_concurrency_factor=$N -XX:NativeMemoryTracking=summary"`. `-Xss256k` stays as in `conf/jvm-server.options:123`.

**B3b. Knobs.** N ∈ {1, 4, 16, 64}, one node restart per value, set with `JVM_EXTRA_OPTS` as above. These cover none, small, medium and the case where per-pool threads equal M. Two further runs act as controls (B3h), both with N = 16:
- `-Xss512k` added to `JVM_EXTRA_OPTS` (the stack-size control).
- Client concurrency of 8 instead of 32 (the W control).

**B3c. Workload.** Schema (cqlsh):
```
CREATE KEYSPACE scf WITH replication = {'class':'SimpleStrategy','replication_factor':1};
CREATE TABLE scf.t (k int PRIMARY KEY, v text, pad text)
  WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'};
CREATE CUSTOM INDEX t_v ON scf.t (v) USING 'org.apache.cassandra.index.sasi.SASIIndex' WITH OPTIONS = {'mode':'PREFIX'};
```
The compaction option persists across restarts. `nodetool disableautocompaction` would not.

Load:
- M = 64 rounds. Each round inserts 200 rows (one with `v='hot'`, the rest `v='v<s>_<r>'`, `pad` = 100 chars) and then runs `nodetool flush scf t`.
- The total is 12 800 rows and well under 50 MB on disk.
- Check `nodetool tablestats scf.t | grep 'SSTable count'` = 64.

The load is done once, with N = 1. The SSTables are kept for all N runs.

Query load per run:
- 32 parallel `cqlsh` clients. Each runs a file of 400 lines `SELECT k FROM scf.t WHERE v = 'hot';`.
- That is 12 800 queries in total, each a range read that reaches 64 SSTable indexes, so 64 tasks per build ≥ N.
- With 32 concurrent client queries, ReadStage keeps up to 32 workers busy, so W ≥ the number of concurrently searching workers.
- Expected duration is 1 to 3 minutes. Sampling continues for 90 s after the clients finish.

Arithmetic: per-pool threads = min(N, 64) = N. Peak search threads S = N × P, where P is the number of distinct `ReadStage-<id>-SEARCH-` prefixes observed (expected around 32, possibly more because of worker rotation). At N = 64 and P ≈ 32, S ≈ 2 048 threads, about 512 MiB of stack reservation. That is reachable on an 8 GB node and well below the default `ulimit -u` / `threads-max`. Check `ulimit -u` ≥ 8192 first.

**B3d. Observables and instruments.** Sample at 1 Hz from 30 s before the query load to 90 s after it, using the PID from `/mydata/scf/node/cassandra.pid`:
- (1) `jcmd $PID Thread.print`, from which the sampler extracts thread names containing `-SEARCH-`. It derives:
  - S, the total count;
  - P, the number of distinct prefixes (name up to `-SEARCH-`);
  - `perPoolMax`, the largest count sharing one prefix.
- (2) `jcmd $PID VM.native_memory summary`, from which it takes the `Thread (reserved=…KB, committed=…KB)` line and `(thread #T)`.
- (3) `/proc/$PID/status`: `Threads:` and `VmRSS:`.
- (4) `grep -c 'Search Concurrency Factor is set to' /mydata/scf/node/logs/system.log`, which gives the number of pools created (one INFO line per calling thread).

What cannot be observed directly is the committed stack per thread. NMT reports only the category total, so the per-thread committed figure is taken as Δcommitted / ΔT.

Sampler script (`/mydata/scf/sample.sh`):
```bash
#!/bin/bash
# usage: sample.sh PID OUTFILE SECONDS
PID=$1; OUT=$2; END=$(( $(date +%s) + $3 ))
echo "ts,S,P,perPoolMax,nmt_thread_reserved_kb,nmt_thread_committed_kb,nmt_threads,proc_threads,rss_kb" > "$OUT"
while [ "$(date +%s)" -lt "$END" ] && kill -0 "$PID" 2>/dev/null; do
  TD=$(jcmd "$PID" Thread.print 2>/dev/null | grep -o '^"[^"]*-SEARCH-[^"]*"')
  S=$(printf '%s\n' "$TD" | grep -c SEARCH)
  P=$(printf '%s\n' "$TD" | sed -n 's/^"\(.*\)-SEARCH-.*/\1/p' | sort -u | grep -c .)
  PM=$(printf '%s\n' "$TD" | sed -n 's/^"\(.*\)-SEARCH-.*/\1/p' | sort | uniq -c | awk 'BEGIN{m=0}{if($1>m)m=$1}END{print m}')
  NMT=$(jcmd "$PID" VM.native_memory summary 2>/dev/null | grep -A1 -E '^-[[:space:]]+Thread ')
  R=$(echo "$NMT" | sed -n 's/.*reserved=\([0-9]*\)KB.*/\1/p' | head -1)
  C=$(echo "$NMT" | sed -n 's/.*committed=\([0-9]*\)KB.*/\1/p' | head -1)
  T=$(echo "$NMT" | sed -n 's/.*thread #\([0-9]*\).*/\1/p' | head -1)
  PT=$(awk '/^Threads:/{print $2}' /proc/$PID/status); RSS=$(awk '/^VmRSS:/{print $2}' /proc/$PID/status)
  echo "$(date +%s),$S,$P,$PM,$R,$C,$T,$PT,$RSS" >> "$OUT"
  sleep 1
done
```

**B3e. Procedure.**
1. Check the node: `df -h /mydata` must show ≥ 5 GB free; `ulimit -u`; `ss -ltn | grep -E ':(7000|9042|7199)\b'`; `pgrep -f CassandraDaemon` must return nothing of yours.
2. Copy and build: `rsync -a <shared>/cassandra-5.0.9/ /mydata/scf/src/ && cd /mydata/scf/src && ant jar`. Apply the B3a yaml edits, then `mkdir -p /mydata/scf/node/{data,commitlog,saved_caches,hints,cdc_raw,logs} /mydata/scf/results`.
3. Start with N = 1: `export CASSANDRA_LOG_DIR=/mydata/scf/node/logs MAX_HEAP_SIZE=2G HEAP_NEWSIZE=200M JVM_EXTRA_OPTS="-Dcassandra.search_concurrency_factor=1 -XX:NativeMemoryTracking=summary"; bin/cassandra -p /mydata/scf/node/cassandra.pid`. Wait until `bin/nodetool status` shows `UN`.
4. Create the schema from B3c with `bin/cqlsh -f /mydata/scf/schema.cql`. Then load:
   `for s in $(seq 0 63); do awk -v s=$s 'BEGIN{for(r=0;r<200;r++){v=(r==0)?"hot":"v" s "_" r; printf "INSERT INTO scf.t (k,v,pad) VALUES (%d,%c%s%c,%c%0100d%c);\n", s*1000+r,39,v,39,39,r,39}}' > /mydata/scf/load.cql; bin/cqlsh -f /mydata/scf/load.cql; bin/nodetool flush scf t; done`.
   Verify that the SSTable count is 64.
5. Create the query file: `yes "SELECT k FROM scf.t WHERE v = 'hot';" | head -400 > /mydata/scf/q.cql`. Warm up with one `bin/cqlsh -e "SELECT k FROM scf.t WHERE v = 'hot';"`, which should return 64 rows.
6. For each N in 1 4 16 64:
   - a. If the node is not already running with this N, restart it: `kill $(cat /mydata/scf/node/cassandra.pid)`, wait until `pgrep -f CassandraDaemon` is empty, export `JVM_EXTRA_OPTS` with the new N, start as in step 3 and wait for `UN`. Then wait 60 s more.
   - b. `PID=$(cat /mydata/scf/node/cassandra.pid); bash /mydata/scf/sample.sh $PID /mydata/scf/results/N$N.csv 400 &`
   - c. `sleep 30; CL=""; for i in $(seq 1 32); do bin/cqlsh -f /mydata/scf/q.cql > /dev/null 2>&1 & CL="$CL $!"; done; wait $CL; sleep 90`. Then wait for the sampler to end, or kill it by PID.
   - d. `grep -c 'Search Concurrency Factor is set to' /mydata/scf/node/logs/system.log > /mydata/scf/results/N$N.pools` (the count is cumulative per node start, and the restart resets the JVM, not the log). Also record `grep 'Search Concurrency Factor is set to' … | tail -3`.
7. Controls (B3h), at N = 16: (i) restart with `JVM_EXTRA_OPTS` plus `-Xss512k` and repeat step 6b–d into `N16-xss512.csv`; (ii) restart with plain N = 16 and repeat with 8 clients instead of 32 into `N16-c8.csv`.
8. Stop the node: `kill $(cat /mydata/scf/node/cassandra.pid)`, wait, and check that `pgrep -f CassandraDaemon`, `pgrep -f cqlsh` and `pgrep -f sample.sh` all return nothing.
9. Summarise each CSV: baseline = median of the first 25 rows; peak = max S and the row where S is maximal; tail = the last 10 rows. Report `perPoolMax`, P, S, ΔT, Δreserved, Δcommitted and ΔRSS.

**B3f. Predictions.** Stated before any run.

| N | perPoolMax | S at peak | `Search Concurrency Factor` log lines | Δ NMT Thread reserved (peak − baseline) | after 75 s idle |
|---|---|---|---|---|---|
| 1 | 0 | 0 | one per calling thread (pool = `ImmediateExecutor`) | ≈ 0; only SEP/transport growth, same as the other runs' non-SEARCH part | S = 0 |
| 4 | **= 4, never > 4** | 4·P | P or more | ≈ 4·P × 256–260 KiB | S = 0, reserved back to baseline ± 5 % |
| 16 | **= 16, never > 16** | 16·P | P or more | ≈ 16·P × 256–260 KiB | S = 0 |
| 64 | **= 64, never > 64** | 64·P | P or more | ≈ 64·P × 256–260 KiB (≈ 512 MiB at P = 32) | S = 0 |

Relations to hold across runs:
- (a) `perPoolMax == N` for N > 1.
- (b) S / P == N, within ±1 for sampling skew.
- (c) Δreserved / S ≈ 256 KiB + a few KiB, constant across N within ±10 %.
- (d) Δcommitted / S is roughly constant across N, within ±30 % of the N = 4 value. Its absolute value is not predicted; it is expected to be tens of KiB.
- (e) ΔRSS grows monotonically with S.
- (f) P is between about 32 (concurrent_reads) and the SharedPool worker count. It may differ between runs, which is why (b) normalises by P.
- (g) The `-Xss512k` control at N = 16 gives Δreserved / S ≈ 512 KiB.
- (h) The 8-client control at N = 16 gives perPoolMax = 16 with a smaller P (about 8 to 16) and a proportionally smaller S.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| (a)–(e) hold: perPoolMax = N, S ∝ N·P, Δreserved and Δcommitted ∝ S, back to baseline after idle | **Claim confirmed:** N caps search-thread memory per calling thread, and native thread memory follows N. |
| perPoolMax > N in any sample | **The claim is wrong:** the per-pool cap does not hold. |
| N > 1 and S = 0 throughout, with 64 SSTables and rows returned | **The claim is wrong:** the entry does not reach the search path on a node, for example because queries run another path. Check the log line and the SSTable count. |
| S ∝ N but NMT Thread reserved and committed do not move | The thread-count cap holds, but the memory claim is wrong. Threads would then be memory-insignificant (or NMT is misattributing). Cross-check with the `-Xss512k` control. |
| Control `-Xss512k` doubles Δreserved / S while N = 16 is unchanged | The instruments attribute stack memory to the search threads, which shows the memory reading is real (the positive control moved). |
| 8-client control: S falls by about the ratio of P, while perPoolMax stays 16 | The node-wide total is N × W as traced: N caps each pool, and W comes from ReadStage concurrency. |
| SSTable count < 64, or queries return < 64 rows | The boundary was not reached, so the run is not conclusive. Fix the load and repeat. |
| S stays > 0 more than 75 s after the load ends | The keep-alive did not release the threads. The cap holds, but the "returns to baseline" part of B1 is wrong. |
| Heap (from `nodetool info`) differs strongly between N values | Not part of this claim (A3.7 predicts no heap effect). Report it as a finding for a separate case. |

**B3h. Controls.**
- N = 1 is the zero baseline: the same data and the same client load with no pool.
- `-Xss512k` at N = 16 is the positive control: a known per-thread memory setting that must move Δreserved/S under the identical workload, which shows the NMT reading follows the search threads.
- 8 clients at N = 16 separate the per-pool cap (N) from the pool count (W).
- The same SSTables are used for every run, compaction is disabled in the table schema, and the SSTable count is checked before each run.
- One restart per N, because the value is `static final` and the pools are per thread.
- A 60 s settle after start and a 30 s pre-load baseline separate the startup threads from the search threads.
- The `-SEARCH-` name suffix is unique to `TermIterator.java:59`.

**B4. Risks and cleanup.**
- Disk:
  - Unit tier: under `build/test/` of the local copy, < 200 MB.
  - Cluster tier: under `/mydata/scf/node/`, < 200 MB including logs and commitlog. Nothing goes on shared storage.
  - The source copy is about 1.5 GB after the build.
- Threads: at N = 64 the node may run about 2 000+ extra threads for a minute. Check `ulimit -u` first, and if it is below 8192, cap the run at N = 16 and say so.
- Memory: about 512 MiB of stack is reserved at N = 64, and less is committed. The heap is fixed at 2 GB.
- Leftover processes: after each tier, `pgrep -f CassandraDaemon`, `pgrep -f cqlsh`, `pgrep -f sample.sh` and `pgrep -f 'junit.*SearchConcurrencyFactorProbeTest'` must all return nothing of yours. Kill any that remain, by PID.
- Cleanup: `rm -rf /mydata/scf/node /mydata/scf/src`. Keep `/mydata/scf/results` and `/mydata/scf/unit` until the results are filed. The shared source tree is never modified; the probe test file lives only in the copy.

## Config-first: places found

1. `src/java/org/apache/cassandra/config/CassandraRelevantProperties.java:483`: the declaration, default `"1"`. It is read with `getInt()` (`:794-800`). It restricts nothing by itself.
2. `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:220`: copied once into `static final int searchConcurrencyFactor`. This is a pass-through, and the reason a restart is needed.
3. `src/java/org/apache/cassandra/config/DatabaseDescriptor.java:4392-4395`: the getter `searchConcurrencyFactor()`. This is a pass-through. Its only caller is `TermIterator.java:53`.
4. **`src/java/org/apache/cassandra/index/sasi/TermIterator.java:57-59`**: the switch and the pool size. At N ≤ 1 no search threads exist. Otherwise each calling thread gets a `ThreadPoolExecutorPlus` with core = max = N threads (1-minute core timeout, unbounded queue). This **restricts the number of SASI search threads (native stack and thread memory) per calling thread**, and it is the only place that restricts memory. It is the subject of this case file.
5. `src/java/org/apache/cassandra/index/sasi/TermIterator.java:96,118`: one task per matching SSTable index is submitted to that pool. Tasks beyond N wait in the unbounded queue. N bounds how many searches run at once, not how many results are kept: `tokens` (`:81`, `:130`) holds every result. This is not a memory restriction.

There is no other reader of the property or its getter in `src/`. The `concurrencyFactor` in `service/reads/range/RangeCommands.java` and `RangeCommandIterator.java` is a different setting (`MAX_CONCURRENT_RANGE_REQUESTS`) and is unrelated.

## C. Sources read

- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (L475-490, L492, L794-800)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (L130, L215-225, L4392-4395)
- src/java/org/apache/cassandra/index/sasi/TermIterator.java (whole file)
- src/java/org/apache/cassandra/index/sasi/plan/QueryController.java (L120-160)
- src/java/org/apache/cassandra/index/sasi/conf/view/View.java (L94-112)
- src/java/org/apache/cassandra/concurrent/ExecutorFactory.java (L43-55, L227-240, L281)
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBuilder.java (L25-80, L160-200)
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorBase.java (L30-95)
- src/java/org/apache/cassandra/concurrent/ThreadPoolExecutorPlus.java (L33)
- src/java/org/apache/cassandra/concurrent/SEPWorker.java (L36-180)
- src/java/org/apache/cassandra/concurrent/SharedExecutorPool.java (L65-110, L159-180)
- src/java/org/apache/cassandra/concurrent/NamedThreadFactory.java (L37-42, L112)
- src/java/org/apache/cassandra/concurrent/Stage.java (L45)
- src/java/org/apache/cassandra/service/reads/range/RangeCommandIterator.java (L80-176, L207, L225-230), RangeCommands.java (L85-112), for the unrelated `concurrencyFactor`
- src/java/org/apache/cassandra/service/reads/AbstractReadExecutor.java (L165)
- src/java/org/apache/cassandra/service/StorageProxy.java (L2178-2190)
- test/unit/org/apache/cassandra/index/sasi/SASICQLTest.java (L41-131, index creation and SASI enablement)
- test/unit/org/apache/cassandra/cql3/CQLTester.java (L748, L775-803, L1622-1660)
- test/unit/org/apache/cassandra/service/reads/range/RangeCommandsTest.java (L54-105, via grep only)
- test/conf/cassandra.yaml (L52)
- conf/cassandra.yaml (L722, L1985-1992)
- conf/jvm-server.options (L118-126), conf/jvm11-server.options (L58)
- conf/cassandra-env.sh (L61-67, L307)
- build.xml (L62, L74, L81, L94, L125, L1185-1195, L1382-1392)
- doc/SASI.md (L555-580); doc/modules/cassandra/pages/developing/cql/SASI.adoc (grep hit L549)
- .build/cassandra-deps-template.xml, .build/parent-pom-template.xml (grep for the driver artifact)
- https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html (cited from knowledge, not fetched)
- https://docs.oracle.com/en/java/javase/11/vm/native-memory-tracking.html (cited from knowledge, not fetched)

## D. Stage-4 feedback

none yet
