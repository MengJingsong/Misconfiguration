# SelectStatement.DEFAULT_PAGE_SIZE — verification solution  <!-- file: cases/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SelectStatement.java:901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L901) (`if (pageSize <= 0) pageSize = DEFAULT_PAGE_SIZE;`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string n/a), 2026-10-26; Band D triage mode |
| Estimate | `positive` (scoped to GROUP BY). When client paging is off, a GROUP BY query gets `rowLimit = DEFAULT_PAGE_SIZE` (10000) in its `CQLGroupByLimits`. Each internal sub-page read then stops after 10000 rows, so the per-read response the coordinator materializes is bounded by 10000 rows, "to avoid OOM" (comment at `:899`). Aggregates without GROUP BY (`AGGREGATE_EVERYTHING`) and DISTINCT never use this value, so they are not capped. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `SelectStatement.DEFAULT_PAGE_SIZE`, a constant.
- `public static final int DEFAULT_PAGE_SIZE = 10000;` ([`SelectStatement.java:114`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L114)).
- The unit is rows.
- It cannot be set. The only substitute is the client page size, which replaces it when > 0 (`:899-902`).


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the number of rows read per internal sub-page of a GROUP BY query when the client disables paging. Each sub-page is one `StorageProxy.read`, whose replica response is materialized in memory: a local data response is serialized into a `DataOutputBuffer` (`src/java/org/apache/cassandra/db/ReadResponse.java:197-203`). The resource is heap on the coordinator and on the replica.

**A3. Mechanism.**
1. `execute` computes `limit = getDataLimits(userLimit, perPartitionLimit, pageSize, aggregationSpec)` (`:296`).
2. In `getDataLimits` (`:881-921`), target `:901` replaces pageSize ≤ 0 with 10000. For a GROUP BY spec (`:906`) that value becomes the third argument `rowLimit` of `DataLimits.groupByLimits(groupLimit, groupPerPartitionLimit, rowLimit, spec)` (`:911-914`; [`DataLimits.java:116-121`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java#L116-L121)). `limits.toString()` prints `LIMIT 10000` ([`DataLimits.java:797-800`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java#L797-L800)).
3. At `:338`, `aggregationSpec != null`, so the paged branch runs even with paging off. `getPager` wraps the pager in `AggregationQueryPager` (`:625-633`). `GroupByPartitionIterator` turns pageSize ≤ 0 into `NO_LIMIT` groups ([`AggregationQueryPager.java:193-198`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java#L193-L198)) and fetches sub-pages in a loop (`:225-251`).
4. Each sub-page keeps `rowLimit` ([`DataLimits.java:718-722`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java#L718-L722), `:740-744`), and the counter stops after `rowLimit` rows ([`DataLimits.java:986`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/filter/DataLimits.java#L986)). The next sub-page resumes from the last group ([`AggregationQueryPager.java:246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java#L246), `:267-275`).
5. Paths that are not capped:
   - `AGGREGATE_EVERYTHING` (aggregates without GROUP BY) takes `cqlLimits(NO_LIMIT, ...)` (`:906`, `:920`). With paging off, `AggregationPartitionIterator` uses a sub-page size of `NO_LIMIT` ([`AggregationQueryPager.java:406-443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java#L406-L443)), so there is a single unbounded read (hypothesis to test).
   - DISTINCT takes `distinctLimits` (`:908-909`, `:917-918`).
   - With paging on, the client page size P replaces 10000. A huge P, such as `Integer.MAX_VALUE`, removes internal sub-paging, and only the `page_size` guardrail (ordinary users) limits P.
   - Row size is unbounded.

**A4. Other consumers.**
- Other queries.
- Memtables.
- Read-size thresholds (if enabled).
- Tombstone thresholds.

**A5. Evidence beyond the source.** None beyond the code comments at `SelectStatement.java:899-900` and `AggregationQueryPager.java:36-38`.

## B. Verification solution

**B1. Claim under test.**
- A GROUP BY query run with paging off issues about ceil(N / 10000) internal reads for N scanned rows, and its peak per-read memory is bounded by about 10000 rows × row size, not by N.
- The same scan as an aggregate without GROUP BY, also with paging off, is not split: one read, with memory that grows with N.

### B2. Unit tier

**B2a. Environment and build.**
1. Clone to local disk (`$WORK/cassandra`, checkout `cassandra-5.0.9`), use JDK 11, run `ant jar`.
2. Add the test file `test/unit/org/apache/cassandra/cql3/GroupByInternalPagingProbeTest.java`, which extends `CQLTester`.
3. Run `ant testsome -Dtest.name=org.apache.cassandra.cql3.GroupByInternalPagingProbeTest`.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** `$WORK/cassandra` on the advisor's machine is `$W/cassandra-run35` (`W=~/Library/Caches/stage4`), a fresh
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run35`, built with `ant -Dlocal.repository=$W/m2 build-test`
> (`testsome` needs the test classes; `ant jar` does not build them). The probe source lives in `stage4-runtime-verification/harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/`
> and `unit-run.sh` copies it into the clone, runs it, and removes it and its classes, so the clone's `git status` stays clean.

**B2b. Knobs.** The constant cannot be changed, so the varied input is the client page size P ∈ {-1 (off), 1000, 50000}, plus the row count N ∈ {25,000, 50,000}. With P > 0, P replaces the constant, so the boundary is expected to move with P.

**B2c. Workload.**
- `CREATE TABLE %s (k int, g int, c int, v blob, PRIMARY KEY (k, g, c))`.
- One partition k=0 with G=50 groups and N/G rows each; v = 16 bytes.
- Insert with `execute()`, then `flush()`.
- Queries:
  - Qg: `SELECT k, g, max(v) FROM %s WHERE k=0 GROUP BY k, g`
  - Qa: `SELECT max(v) FROM %s WHERE k=0`
- Run each through the client path: `((SelectStatement) QueryProcessor.parseStatement(formatQuery(q), ClientState.forInternalCalls())).execute(QueryState.forInternalCalls(), QueryOptions.create(ConsistencyLevel.ONE, List.of(), false, P, null, null, ProtocolVersion.CURRENT, KEYSPACE), Dispatcher.RequestTime.forImmediateExecution())`.

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).**
> 1. The probe calls `requireNetwork()` in `@BeforeClass`, so the client path through `StorageProxy.read` runs against a started
>    node service, as on a node.
> 2. The unit yaml enables read thresholds (`test/conf/cassandra.yaml:63-67`: local read size fail 8192 KiB, coordinator 4096 KiB),
>    while a node's defaults leave them unset (`conf/cassandra.yaml:2021-2026`). They are another consumer (A4) that can abort a read,
>    so the probe calls `DatabaseDescriptor.setReadThresholdsEnabled(false)` first and prints the read-back.
> 3. Rows: for each N a fresh table (`createTable`), g ∈ [0, 50), c ∈ [0, N/50), v = 16 bytes from a `Random(42)`, inserted in (g, c)
>    order; then `flush()` and a `count(*)` read-back that must equal N.
> 4. `max(blob)` is valid: `max` is declared for any type (`AggregateFcts.java:65-71`, `:845-847`).

**B2d. Observables and instruments.**
- (i) The operand: `stmt.getQuery(options, FBUtilities.nowInSeconds()).limits().toString()`. Expect `LIMIT 10000` for Qg with P=-1 (`SelectStatement.java:368-379`).
- (ii) The number of reads issued: the delta of `ClientRequestsMetricsHolder.readMetrics.latency.getCount()`, which is updated once per `StorageProxy.read` (`src/java/org/apache/cassandra/service/StorageProxy.java:2053-2054`).
- (iii) As a cross-check, the delta of `getCurrentColumnFamilyStore().metric.readLatency.latency.getCount()`, which is updated per local single-partition command (`src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java:484`).
- (iv) Result groups: `rows.result.size()`, expected to be 50 for Qg.
- Per-read row count is not observed directly. It is inferred as N divided by the number of reads.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** One line per cell, to stdout (it lands in `build/test/logs/**/TEST-<class>.log`):
> `PROBE cell N=<N>,query=<Qg|Qa>,P=<P>,limits=[<limits>],reads=<ii>,localReads=<iii>,groups=<iv>,hasMore=<paging state != null>`,
> plus `PROBE setup …`, `PROBE load N=… rows=…` and `PROBE done cells=8`. Rows per read stay inferred (N / reads), as filed: the
> unit tier counts reads, not bytes; the cluster tier measures the bytes (amendment B3d).

**B2e. Procedure.**
1. For each N: create the table, load and flush it.
2. For each (query, P), record limits, reads and groups. Print `N,query,P,limits,reads,localReads,groups`.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Run `stage4-runtime-verification/harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/unit-run.sh` with no argument (one `ant testsome` JVM). It logs each command and keeps
> `ant.log`, `TEST.log`, `probe.txt` and `summary.txt` under `$W/logs/<stem>/unit/`.

**B2f. Predictions** (reads may be one higher than shown, for a final empty sub-page):

| Query | P | limits | N=25k reads | N=50k reads | Notes |
|---|---|---|---|---|---|
| Qg | -1 | `LIMIT 10000` | 3 (or 4) | 5 (or 6) | 50 groups returned |
| Qg | 1000 | `LIMIT 1000` row limit | ≈ 25 | ≈ 50 | 50 groups; only the first page if the result has more pages |
| Qg | 50000 | — | 1 (or 2) | 1 (or 2) | |
| Qa | -1 | no row limit | 1 | 1 | |

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** Exact form of the table above, derived from source. A sub-page that counts exactly R rows (R = the row
> limit in force) is not exhausted (`DataLimits.java:806-808`: `rowsCounted < rowLimit`), so the pager issues one more sub-page,
> which returns 0 rows (`AggregationQueryPager.java:237-247`; `SinglePartitionPager.java:86-94` never returns null). So the derived
> count for one partition of N rows is ⌊N/R⌋ + 1, and the acceptance band is the filed one, {⌈N/R⌉, ⌈N/R⌉ + 1}:
>
> | Query | P | R | limits | reads N=25k (band; derived) | reads N=50k (band; derived) | groups | hasMore |
> |---|---|---|---|---|---|---|---|
> | Qg | −1 | 10000 | `LIMIT 10000` | {3, 4}; 3 | {5, 6}; 6 | 50 | false |
> | Qg | 1000 | 1000 | `LIMIT 1000` | {25, 26}; 26 | {50, 51}; 51 | 50 | false (50 groups fit the 1000-group page) |
> | Qg | 50000 | 50000 | `LIMIT 50000` | {1, 2}; 1 | {1, 2}; 2 | 50 | false |
> | Qa | −1 | none | empty (`DataLimits.java:547-561` prints nothing for `NO_LIMIT`) | 1 | 1 | 1 | false |
>
> `localReads` equals `reads` in every cell (one replica).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Qg with P=-1 reads scale as N/10000 while Qa stays at 1 | Constant caps rows per read for GROUP BY only; confirmed |
| Qg with P=-1 does 1 read at N=50k | No internal paging; claim wrong |
| Qa with P=-1 does more than 1 read | Aggregate path is also paged; the uncapped-path part of the claim is wrong |
| `limits` is not `LIMIT 10000` | Trace wrong |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words and added rows:
> - Row 1 (all eight cells in the amended B2f bands, limits as shown) → **Confirmed**.
> - Row 2 (Qg P=−1 does 1 read at N=50k) → **Refuted** (does not cap).
> - Row 3 (Qa P=−1 does more than 1 read) → **Refuted** for the uncapped-path part of B1.
> - Row 4 (`limits` of Qg P=−1 is not `LIMIT 10000`) → **Refuted** (trace wrong).
> - Added, **Invalid**: the test fails, a load read-back differs from N, read thresholds are not off, or fewer than 8 cells print.
> - Added, **Not confirmed**: rows 2–4 do not apply but some cell is outside its band (the cell is named).
> - **Effect rule:** row 1 → **caps only on some paths (bypass)**: rows per read follow the constant for GROUP BY with paging off,
>   while the aggregate without GROUP BY (named in the same comment at `SelectStatement.java:899`) reads everything in one read.
>   Row 2 or 4 → **does not cap**. Row 3 with Qg as in row 1 → **caps**. Invalid or Not confirmed → **undetermined**.

**B2h. Controls.**
- P=1000 and P=50000 show the reads follow whatever row limit is in force, so the count tracks the row limit and not some other splitting.
- Two N values show proportionality.

### B3. Cluster tier

**B3a. Environment and build.**
1. One Linux node from the local clone, with all node directories under `$WORK/node` on local disk (at least 5 GiB free).
2. Heap: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
3. In `conf/jvm-server.options`, add `-Xlog:gc*:file=<abs>/gc.log:time,uptime`.
4. Start with `bin/cassandra -p $WORK/node/pid`.
5. Client: python3 with `PYTHONPATH=$WORK/cassandra/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`, or a venv with `cassandra-driver==3.29.0`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (macOS, arm64; no `setsid`, no `/local`):
> - `$WORK/cassandra` is `$W/cassandra-run35` after the unit tier (probe removed). The node uses its own `CASSANDRA_CONF` copy and
>   directories under `$W/node-dps`, local SSD, wiped before and after; heap dumps on OOM land in `$W/node-dps/logs`.
> - `bin/cassandra -p` daemonizes, so the node runs as a tracked background `bin/cassandra -f`, stopped with `nodetool stopdaemon`
>   and then by pid.
> - The gc log line goes into the copy's `jvm-server.options`.
> - Yaml overrides besides paths: `read_request_timeout: 60000ms` and `native_transport_timeout: 60s`. A local read's deadline is
>   min(start + `read_request_timeout`, enqueue + `native_transport_timeout`) (`Dispatcher.java:238-245`, `StorageProxy.java:2204-2205`),
>   and one request time covers every sub-page of a query (`AggregationQueryPager.java:163`, `:297`). At the defaults (5 s, 12 s) a
>   400 MiB single read, or the last sub-pages of a long GROUP BY, could time out, and a timed-out read has no B3g row.
> - The Byteman agent (amendment B3d) is passed in `JVM_EXTRA_OPTS` to `bin/cassandra` only, never to client JVMs.
> - Client: the filed `PYTHONPATH` form works (bundled driver 3.29.0, a subfolder of the zip); protocol 5, `DCAwareRoundRobinPolicy`,
>   token and schema metadata off, heartbeat off, request timeout 120 s.

**B3b. Knobs.**
- The constant is fixed.
- Paging is varied per query: off (`fetch_size=None` and `session.default_fetch_size=None`) or fetch 1000.
- Query shape: GROUP BY (capped) against an aggregate without GROUP BY (control).

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** The row limit in force takes three values on the same data, so per-read bytes can be compared across
> them (group A): **10000** (paging off: the constant), **1000** (fetch 1000) and **50000** (fetch 50000, added). The aggregate without
> GROUP BY (paging off) is the uncapped arm. Runs: Qg-off, Qg-1000, Qg-50000, Qa-off.

**B3c. Workload.**
- Schema: `CREATE KEYSPACE g WITH replication={'class':'SimpleStrategy','replication_factor':1}` and `CREATE TABLE g.t (k int, g int, c int, v blob, PRIMARY KEY (k,g,c)) WITH compression={'enabled':false}`.
- One partition: k=0, 50 groups × 2000 rows = N = 100,000 rows; v = 4 KiB of `os.urandom`. That is about 400 MiB. Then `nodetool flush g t`.
- Queries, each run 3 times:
  - Qg: `SELECT k, g, max(v) FROM g.t WHERE k=0 GROUP BY k, g`
  - Qa: `SELECT max(v) FROM g.t WHERE k=0`
- Arithmetic: a GROUP BY sub-page is 10000 × 4 KiB ≈ 40 MiB, against ≈ 400 MiB if one read materializes everything.
- If `max(blob)` is rejected, use `count(v)`. It still has to read v cells, and liveness alone would not move heap, so check the heap result with care.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).** `stage4-runtime-verification/harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/probe.py`: `setup` (keyspace and table as above, compression read back), `load 50 2000 32`
> (prepared INSERT, v = `os.urandom(4096)`, concurrency 32), `count` (must be 100,000), and `q <qg|qa> <off|fetch>`, which reads all
> pages and prints rows, pages, value bytes and times. `max(blob)` is valid (`AggregateFcts.java:65-71`), so the `count(v)` fallback
> is not used.

**B3d. Observables and instruments.**
- Coordinator read count per query: `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=ClientRequest,scope=Read,name=Latency -mg -f Count` before and after.
- Local read count: `nodetool tablestats g.t`, "Local read count".
- Heap: `jstat -gc <pid> 100` during each query; take the peak of (S0U+S1U+EU+OU) minus the pre-query median. Also G1 humongous regions in `gc.log`.
- Client: the result rows and the elapsed time.

> **Amendment B3d (2026-10-26, stage-4 audit, before any run-1 reading; item 1's per-table counters and the rules' `table=` field
> follow cluster shakedown 1, an instrument check at 20,000 rows that showed the driver's and the batchlog's own reads in the global
> counter and in the trace).** Instruments on this host (`jstat` cannot attach; `nodetool sjk mx` exits 0 on failure):
> 1. **Reads** from a small JMX client (`DpJmx`), before and after each query: the table's `CoordinatorReadLatency` count (one per
>    `StorageProxy.read` of a `g.t` command, `StorageProxy.java:2056-2057`) and its `ReadLatency` count (local reads; the counter
>    behind "Local read count"). The global `ClientRequest` Read count is also logged, but it includes the driver's own reads of system
>    tables on each new connection, so it is not the read count.
> 2. **M1, bytes each read materializes** (primary memory observable): a Byteman rule at the exit of the `LocalDataResponse`
>    constructor that `ReadCommand.createResponse` uses (`ReadCommand.java:374`, `ReadResponse.java:46-48`, `:183-203`) prints
>    `BM-RESP … table=<ks.table> remaining=<serialized bytes> capacity=<length of the heap byte[]>`. This is the heap buffer B1 means.
> 3. **M2, rows per sub-page:** a Byteman rule at the exit of `AbstractQueryPager.Pager.onClose` (`AbstractQueryPager.java:179-201`)
>    prints `BM-PAGE … table=… rows=<rowsCounted> groups=<counted> limits=[<page limits>]`. Both rules only print; they are
>    type-checked with Byteman's `TestScript` before the run.
> 4. **Heap:** a JMX poller of `HeapMemoryUsage` used (= S0U+S1U+EU+OU) and GC counts every 100 ms. Before each query an explicit
>    full GC runs over JMX (amendment B3h). **H_alloc** = peak used in [probe start, probe end + 3 s] minus the median of the 2 s before
>    (the filed definition). With no GC inside the window it counts every byte allocated since the explicit GC, which for Qg-off is
>    the sum over all sub-pages (each read allocates a new buffer, `ReadResponse.java:197-203`), not what one read holds; so H_alloc is
>    reported but carries no bound. **H_live** = the largest heap-after-GC (`gc.log`, `Pause … A->B(C)`, not the explicit
>    `System.gc()` pauses) of any GC inside the window, minus the heap after the explicit GC before it; observable only when a GC falls
>    inside the window. Humongous region counts from `gc.log` are reported.
> 5. Client: outcome, rows, pages, elapsed time.

**B3e. Procedure.**
1. Start the node and load and flush the data. Restart and wait 30 s.
2. For each (query, paging) pair (Qg-off, Qg-1000, Qa-off) and each of 3 reps: start jstat, wait 2 s, run the query, wait 3 s, stop jstat, read the counters.
3. Stop the node.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `stage4-runtime-verification/harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/cluster-run.sh`: start the node (agent loaded), setup, load, flush, `count`; restart;
> wait 30 s; start the heap poller; then Qg-off ×3, Qg-1000 ×3, Qg-50000 ×3, Qa-off ×3 (Qa last, since it may OOM the node). Per
> query: explicit GC; read counts; 2 s; the query; 3 s; read counts; the query's slices of `node.out` (Byteman lines) and `system.log`.
> Then stop the node, copy `system.log` and `gc.log`, wipe `$W/node-dps`.

**B3f. Predictions.**

| Run | Reads | Heap peak delta | Result |
|---|---|---|---|
| Qg-off | 10 or 11 | ≤ about 150 MiB (a few × 40 MiB) | 50 rows |
| Qg-1000 | ≈ 100 for the full result | ≤ about 50 MiB | — |
| Qa-off | 1 | ≥ 400 MiB; it may even OOM on 2 GiB | — |

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** Exact predictions for N = 100,000 rows of 4,096-byte values. A full sub-page of R rows serializes to at
> least R × 4,096 B of values and, with row overhead under 5 %, at most R × 4,096 × 1.05 B. Reads are counted on `g.t` only; bands as in
> amendment B2f ({⌈N/R⌉, ⌈N/R⌉ + 1}, derived ⌊N/R⌋ + 1):
>
> | Run | R | Reads (coordinator = local) | M1 `g.t` responses | M2 `g.t` pages | H_live (if a GC falls in the window) | Client |
> |---|---|---|---|---|---|---|
> | Qg-off | 10000 | {10, 11}; derived 11 | one per read; every one ≤ 43,008,000 B; ⌊N/R⌋ = 10 of them ≥ 40,960,000 B | rows ≤ 10000 each | ≤ 150 MiB | ok, 50 rows |
> | Qg-1000 | 1000 | {100, 101}; derived 101 | every one ≤ 4,300,800 B | rows ≤ 1000 each | ≤ 50 MiB | ok, 50 rows, 1 page |
> | Qg-50000 | 50000 | {2, 3}; derived 3 | every one ≤ 215,040,000 B; 2 of them ≥ 204,800,000 B | rows ≤ 50000 each | reported | ok, 50 rows |
> | Qa-off | none | 1 | one, ≥ 409,600,000 B | one page, 100,000 rows | reported (whether a GC falls while the buffer is live is not controlled) | ok, 1 row |
>
> The filed "heap peak delta" bounds (≤ 150 MiB, ≤ 50 MiB, ≥ 400 MiB) move to M1 and H_live as above: H_alloc cannot carry them
> (amendment B3d). Each cell must hold in each of the 3 repetitions.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Qg-off reads ≈ 10 with bounded heap, while Qa-off does 1 read with heap ≥ 400 MiB | Heap follows the constant for GROUP BY and not for the uncapped aggregate; confirmed. Qa-off is also the positive control: usage moves with N where no cap binds |
| Qg-off does 1 read or uses heap ≥ 400 MiB | The constant does not cap; claim wrong |
| Qa-off is also split and bounded | The aggregate path is capped too; the uncapped-path part is wrong |
| Neither query moves heap | The workload does not materialize v; not confirmed (switch the aggregate or enlarge v) |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words and added rows:
> - Row 1 → **Confirmed** when, in all 3 repetitions: Qg-off reads ∈ {10, 11}, every Qg-off M1 response ≤ 43,008,000 B with 10 of them
>   ≥ 40,960,000 B; Qa-off does 1 read whose response is ≥ 409,600,000 B (or Qa-off fails with `java.lang.OutOfMemoryError` in the
>   node's log, row 1b, also Confirmed); and the controls Qg-1000 and Qg-50000 are in their amended B3f cells.
> - Row 2 → **Refuted** (does not cap): Qg-off does 1 read, or any Qg-off response exceeds 43,008,000 B.
> - Row 3 → **Refuted** for the uncapped-path part: Qa-off does more than 1 read and each response is ≤ 43,008,000 B.
> - Row 4 → **Not confirmed**: Qa-off's response is < 409,600,000 B (the workload did not materialize v).
> - Added, heap: if H_live is observable for Qg-off in at least 2 of 3 repetitions and exceeds 150 MiB in at least 2, the verdict is
>   **Not confirmed** (per-read buffers bounded, but the heap is not).
> - Added, **Invalid**: `count` ≠ 100,000; no `BM-` lines (agent not loaded); a JMX read-back fails; a query errors or times out
>   other than Qa-off with an OOM; the node dies outside Qa-off.
> - Added, **Not confirmed**: rows 2–4 do not apply but a control cell (Qg-1000, Qg-50000) is outside its amended B3f cell.
> - **Effect rule:** as amendment B2g (row 1 → **caps only on some paths (bypass)**; row 2 → **does not cap**; row 3 with Qg as in
>   row 1 → **caps**; otherwise **undetermined**).

**B3h. Controls.**
- Data is flushed and the JVM restarted, so memtables are excluded.
- RF=1 on one node, so there is no digest/data mismatch traffic.
- Qg-1000 shows that the read count follows the row limit in force.

> **Amendment B3h (2026-10-26, stage-4 audit, before any reading).** An explicit full GC (JMX `java.lang:type=Memory` `gc()`) runs before each query's 2-s pre-window, so each
> baseline starts from the same live heap (earlier runs on this host saw the baseline drift between queries without it).

**B4. Risks and cleanup.**
- About 400 MiB of data under `$WORK/node`.
- Qa-off may OOM the node. That is acceptable: it is local, and the reading is recorded. Restart if needed.
- Kill the node by pid, check `pgrep -f CassandraDaemon` is empty, then `rm -rf $WORK/node`.
- Nothing is written in the shared clone.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** About 400 MiB of data under `$W/node-dps` (local SSD, ~134 GiB free). Stop the node with `nodetool stopdaemon`,
> then by tracked pid; check that no `CassandraDaemon` process is left; wipe `$W/node-dps`; check that the clone's `git status` is clean.

## C. Sources read

src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java
src/java/org/apache/cassandra/db/filter/DataLimits.java
src/java/org/apache/cassandra/db/ReadResponse.java
src/java/org/apache/cassandra/db/SinglePartitionReadCommand.java (grep)
src/java/org/apache/cassandra/service/StorageProxy.java
src/java/org/apache/cassandra/metrics/ClientRequestsMetricsHolder.java
src/java/org/apache/cassandra/metrics/TableMetrics.java (grep)

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** (advisor's machine; [results](../../stage4-runtime-verification/results/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.md);
frozen at sha256 `7393d4f3…3317` after fifteen audit amendments; uncommitted).
- **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1).
  - GROUP BY with paging off carries `LIMIT 10000` and takes 3 and 6 reads at N = 25,000 and 50,000.
  - P = 1000 and P = 50000 give 26/51 and 1/2 reads. Every count equals ⌊N/R⌋ + 1.
  - The aggregate without GROUP BY takes 1 read.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1). 100,000 rows of 4 KiB, three repetitions.
  - With paging off, Qg takes 11 reads; each local response is at most 41.1 MB (10,000 rows).
  - With paging off, Qa takes 1 read with a 411 MB response in a 514 MB heap array.
  - Bytes per read follow the row limit at 1,000, 10,000 and 50,000 rows.
- **Audit findings for stage 3:**
  - The filed heap Δ (peak minus baseline, with no GC in the window) sums allocation over all sub-pages, so it cannot show a per-read
    bound. It read 1.3–1.6 GiB for GROUP BY, the same as the uncapped aggregate. The run used Byteman response sizes and heap after GC
    instead.
  - The default `read_request_timeout` (5 s) and `native_transport_timeout` (12 s) bound the whole multi-sub-page query, because
    one request time covers every sub-page.
- **Open reading:** in one of the three Qg-off repetitions, the heap after an in-window Young GC was 528 MiB above baseline, against
  129–132 MiB in the other two. 28 old regions were promoted, and the humongous regions fell to one buffer. Under B3g's heap row
  (2 of 3) this does not change the verdict. What held the heap is not known; a class histogram at a held point would tell.
