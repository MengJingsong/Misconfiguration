# cassandra.sai.vector_search.max_top_k — verification solution  <!-- file: cases/sai_vector_search_max_top_k-execute-pageSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SelectStatement.java:322`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L322) (`pageSize > 0`) and `:322#2` (`pageSize < limit.count()`), in `if (pageSize > 0 && pageSize < limit.count())` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string n/a), 2026-10-26; Band D triage mode |
| Estimate | `positive`. For Top-K (ANN) queries, the target raises the page size to LIMIT, and `:338` then runs the query unpaged, so all LIMIT rows are materialized in one response. The only bound on LIMIT is `MAX_TOP_K` (`-Dcassandra.sai.vector_search.max_top_k`, default 1000), which the code says exists "to avoid ... OOM when filtering top-k". So rows per ANN response, and the top-K heap structures, follow that property. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- The JVM system property `cassandra.sai.vector_search.max_top_k`, declared as `SAI_VECTOR_SEARCH_MAX_TOP_K` with default `"1000"` ([`CassandraRelevantProperties.java:479`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L479)).
- It is read once into `public static final int MAX_TOP_K` ([`IndexWriterConfig.java:57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java#L57)).
- The unit is rows (the ANN LIMIT).
- It is set with `-D` at JVM start. Because the field is `static final`, a change needs a restart. There is no yaml key and no JMX setter.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the LIMIT of an ANN query (`command.limits().count()`). That bounds:
- (i) the rows the coordinator returns in the single unpaged response;
- (ii) the replica and coordinator top-K structures: the priority queue of size limit+1 in `VectorTopKProcessor` (`src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java:81`, `:91-123`) and the graph search top-K (`index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java:121-124`).

The resource is heap. The cap is a row count, so bytes = rows × row size.

**A3. Mechanism.**
1. In `SelectStatement.execute`, `restrictions.isTopK()` (`:299`) triggers checks: there must be a LIMIT (`:318`) and no per-partition limit (`:320`).
2. Target `:322`: if the client page size P satisfies 0 < P < LIMIT, then `pageSize = limit.count()` and the options are rewritten (`:324-327`), and the client is warned with `TOPK_PAGE_SIZE_WARNING` (`:328`, text at `:122-123`). So the client fetch size cannot shrink the response below LIMIT.
3. `getQuery` (`:332`) builds the command and calls `maybeValidateIndex()` (`:740`, `:807`; [`ReadCommand.java:410-414`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L410-L414)). That reaches `StorageAttachedIndex.validate`: `if (command.limits().count() > MAX_TOP_K) throw InvalidRequestException(ANN_LIMIT_ERROR)`, with the comment "to avoid overflow of the vector graph internal data structure and avoid OOM when filtering top-k" ([`StorageAttachedIndex.java:497-505`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L497-L505); message at `:141`).
4. `:338`: `query.isTopK()` sends the query to the unpaged `execute` (`:340`), and the paged path never sets more pages for Top-K (`:549`). The whole LIMIT-row result is built in one `ResultMessage.Rows`.
5. Bypasses and overshoot:
   - Each row's size is unbounded.
   - Tombstones are kept outside the queue ([`VectorTopKProcessor.java:110-115`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java#L110-L115)).
   - Non-vector indexes skip the check ([`StorageAttachedIndex.java:499-500`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java#L499-L500)).

**A4. Other consumers.**
- Vector graph memory in memtables (SAI memtable indexes).
- `SAI_VECTOR_SEARCH_*` brute-force settings.
- Other queries.
- Read-size thresholds (if enabled).

**A5. Evidence beyond the source.** `test/unit/org/apache/cassandra/index/sai/cql/VectorInvalidQueryTest.java:204-205` asserts that `LIMIT 1001` fails with `ANN_LIMIT_ERROR` at the default `MAX_TOP_K`.

## B. Verification solution

**B1. Claim under test.**
- An ANN query with LIMIT L ≤ `max_top_k` returns min(L, matching rows) rows in a single response, whatever the client fetch size.
- An ANN query with L > `max_top_k` is rejected.
- So per-response rows and coordinator heap scale with `max_top_k`: raising it lets the node materialize proportionally more in one response.

### B2. Unit tier

**B2a. Environment and build.**
1. Clone to local disk (`$WORK/cassandra`, checkout `cassandra-5.0.9`), use JDK 11, run `ant jar`.
2. Add two test classes under `test/unit/org/apache/cassandra/index/sai/cql/`, `TopKProbe100Test` and `TopKProbeDefaultTest`. Both extend `org.apache.cassandra.index.sai.SAITester`, or `CQLTester` if that is not usable.
   - `TopKProbe100Test` has `static { System.setProperty("cassandra.sai.vector_search.max_top_k", "100"); }`. This runs before `IndexWriterConfig` is loaded, because SAI classes load on index creation.
   - The first assertion in each test is `assertEquals(expected, IndexWriterConfig.MAX_TOP_K)`, so a property read too late is detected.
3. Run each class separately in its own JVM with `ant testsome -Dtest.name=org.apache.cassandra.index.sai.cql.TopKProbe100Test` (and likewise for the default class).

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (`environment-advisor.md`):
> - `$WORK/cassandra` is `$W/cassandra-run34` (`W=~/Library/Caches/stage4`), a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`
>   (`b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test`; `ant testsome` needs the test classes, which `ant jar` does not build.
> - The probe classes live in `stage4-runtime-verification/harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/`. `unit-run.sh`
>   copies them into `test/unit/org/apache/cassandra/index/sai/cql/` of the clone, runs them, and removes them and their class files.
> - The shared body is in an abstract class `TopKProbeBase extends SAITester` (not a test: `testsome` runs only the named class). Each
>   test class (`TopKProbe100Test`, `TopKProbeDefaultTest`, `TopKProbe1500Test`, amendment B2b) holds only its static block, which sets
>   the property (the default class sets nothing) and the expected value. The static block runs at class initialisation, before
>   `@BeforeClass`, so before any index is created; the `MAX_TOP_K` assertion stays the first check.
> - A `@BeforeClass` calls `requireNetwork()`: the ANN query has no partition key, so it is a range read through
>   `StorageProxy`, which needs the server's token metadata (`CQLTester.java:613-636` runs `StorageService.instance.initServer()`).

**B2b. Knobs.** `max_top_k` ∈ {100, 1000 (the default)}.

> **Amendment B2b (2026-10-26, stage-4 audit, before any reading).** A third value, **`max_top_k` = 1500**, is added (class `TopKProbe1500Test`), so the knob takes three
> values including the default (group A): {100, 1000 (default), 1500}. 1500 + 1 = 1501 ≤ 2000 rows, so every value can be driven to
> its limit and past it with the filed data.

**B2c. Workload.**
- `CREATE TABLE %s (k int PRIMARY KEY, v vector<float, 4>, p text)` and `CREATE INDEX ON %s(v) USING 'sai'`.
- Insert 2000 rows with k=i, v=[1+i%7, 2+i%11, 3+i%13, 1], p = a 50-char string.
- Query `SELECT k FROM %s ORDER BY v ANN OF [1,2,3,1] LIMIT L`, executed directly: `((SelectStatement) QueryProcessor.parseStatement(formatQuery(q), ClientState.forInternalCalls())).execute(QueryState.forInternalCalls(), QueryOptions.create(ConsistencyLevel.ONE, List.of(), false, P, null, null, ProtocolVersion.CURRENT, KEYSPACE), Dispatcher.RequestTime.forImmediateExecution())`.
- (P, L) pairs: (10, 50), (10, max_top_k), (10, max_top_k+1), (-1, max_top_k), and (5000, 50) as a control.

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).**
> 1. Rows are inserted with `execute("INSERT INTO %s (k, v, p) VALUES (i, [a, b, c, 1], 'abcdefghij' × 5)")` with the literal
>    vector written into the query text (a = 1 + i%7, b = 2 + i%11, c = 3 + i%13), and counted with `SELECT count(*)` before the cases.
> 2. Read thresholds are turned off first (`DatabaseDescriptor.setReadThresholdsEnabled(false)`): the unit yaml enables them
>    (`test/conf/cassandra.yaml:63-67`), a node's default does not (`Config.java:526`). They are an "other consumer" (A4).
> 3. The (P, L) pairs are run for each class with L written from that class's `max_top_k` V: (10, 50), (10, V), (10, V+1), (−1, V),
>    (5000, 50). 15 cases in all. Each case parses its own statement (`QueryProcessor.parseStatement(String, ClientState)` already
>    returns the prepared `SelectStatement`).

**B2d. Observables and instruments.**
- `rows.result.size()`.
- `rows.result.metadata.getPagingState()` (null means a single page).
- Warnings, via `ClientWarn.instance.captureWarnings()` before and `getWarnings()` after.
- The exception and its message.
- The effective page size cannot be seen directly; it is inferred from row count plus the warning.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** Output, one stdout line per item (it lands in `build/test/logs/**/TEST-<class>.log`):
> - `PROBE setup class=<c> MAX_TOP_K=<IndexWriterConfig.MAX_TOP_K> expected=<V> property=<System property> readThresholdsEnabled=<b>`;
> - `PROBE table rows=<count(*)>`;
> - per case: `PROBE case maxTopK=<V> P=<P> L=<L> rows=<n> singlePage=<pagingState == null> warnedTopKPageSize=<number of warnings
>   starting "Top-K queries do not support paging"> warnings=<all warnings> exception=[<class>: <message>] warntext=[...]`
>   (`rows=-1 singlePage=na` when it throws);
> - `PROBE done cases=<n>`.
>
> The warning is captured with `ClientWarn.instance.captureWarnings()` before and `getWarnings()` after, then `resetWarnings()`.
> Gap: the unit tier counts rows, not bytes; bytes per row are fixed (an int `k`) so rows are the only quantity it can show.

**B2e. Procedure.**
1. Run each class. It prints `maxTopK,P,L,rows,singlePage,warnedTopKPageSize,exception` per case.
2. Collect the output.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/unit-run.sh`, runs the
> three classes in three `ant -Dlocal.repository=$W/m2 testsome` JVMs (100, default, 1500), logs every command, keeps each class's
> `ant-<V>.log`, `TEST-<V>.log` and `probe-<V>.txt` under `$W/logs/<stem>/unit/`, and leaves the clone's `git status` clean.

**B2f. Predictions.**

| Case | max_top_k = 100 | max_top_k = 1000 |
|---|---|---|
| (10, 50) | rows 50, single page, Top-K page-size warning | same |
| (10, max_top_k) | rows 100 + warning | rows 1000 + warning |
| (10, max_top_k+1) | InvalidRequestException "...LIMIT that is not greater than 100. LIMIT was 101" | same with 1000 / 1001 |
| (-1, max_top_k) | rows = max_top_k, no warning | same |
| (5000, 50) | rows 50, no warning | same |

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** The table gets a third column, and the cells are made exact. The same for every V ∈ {100, 1000, 1500},
> with 2000 matching rows:
>
> | Case | rows | singlePage | warnedTopKPageSize | exception |
> |---|---|---|---|---|
> | (10, 50) | 50 | true | 1, text "Top-K queries do not support paging and the page size is set to 10, which is less than LIMIT 50. The page size has been set to 50 to match the LIMIT." (`SelectStatement.java:122-123, 328`) | none |
> | (10, V) | V | true | 1 (page size 10, LIMIT V) | none |
> | (10, V+1) | — | — | 1: the rewrite (`:322-328`) runs before `getQuery` (`:332`), so the warning is issued before the throw | `InvalidRequestException: Use of ANN OF in an ORDER BY clause requires a LIMIT that is not greater than V. LIMIT was V+1` (`StorageAttachedIndex.java:141, 503-504`) |
> | (−1, V) | V | true | 0 (`pageSize > 0` false) | none |
> | (5000, 50) | 50 | true | 0 (`pageSize < limit` false) | none |
>
> Validity: `MAX_TOP_K` equals V in each class, `rows=2000`, read thresholds off, 5 cases per class, and Ant reports no failure.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Rows equal L up to max_top_k in one page, and L = max_top_k+1 is rejected, for both values | Confirmed |
| Rows capped at P = 10 (more pages) | The target does not override paging; trace wrong |
| L > max_top_k accepted | Cap does not bind; claim wrong |
| `MAX_TOP_K` assertion fails | Property not applied; not confirmed, so fix the harness |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows. Every row is judged per class and over all three classes.
> - Row 1 is **Confirmed**: every cell of amended B2f holds for all three V. Rows 2 and 3 are **Refuted**. Row 4 is **Invalid** (fix the harness).
> - Added, **Not confirmed**: a case returns fewer rows than min(L, 2000) in a single page (the ANN search is approximate), or any other
>   cell of amended B2f is off (a warning count, the message text). The rejection boundary and row counts are reported as read.
> - Added, **Invalid**: `rows` ≠ 2000, read thresholds on, a class missing its cases, or a test error outside the cases.
> - **Effect rule:** row 1 gives **caps** (rows per ANN response follow `max_top_k` and LIMIT > `max_top_k` is refused). Row 3 (L > V
>   accepted) gives **does not cap**. Row 2 (the client's page size, not the knob, bounds the response) gives **undetermined**.
>   Not confirmed gives **caps** if the rejection boundary moved with V at all three values and no response exceeded V, else
>   **undetermined**. Invalid gives **undetermined**.

**B2h. Controls.**
- The (5000, 50) case shows the page-size rewrite fires only when P < L.
- The two `max_top_k` values show the boundary moves with the knob.

> **Amendment B2h (2026-10-26, stage-4 audit, before any reading).** The third value (1500, above the default) shows the boundary moving upward from the default as well as
> downward (100), with the same data and cases.

### B3. Cluster tier

**B3a. Environment and build.**
1. One Linux node from the local clone, with all node directories under `$WORK/node` on local disk (at least 5 GiB free).
2. Heap: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
3. Add `-Dcassandra.sai.vector_search.max_top_k=<V>` to `conf/jvm-server.options`.
4. Add `-Xlog:gc*:file=<abs path>/gc.log:time,uptime`.
5. Start with `bin/cassandra -p $WORK/node/pid`.
6. Client: python3 with the bundled driver (`PYTHONPATH=$WORK/cassandra/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`), or a venv with `cassandra-driver==3.29.0`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine (macOS arm64, not Linux; `environment-advisor.md`):
> - `$WORK/cassandra` is `$W/cassandra-run34` (amendment B2a; no probe left in it). `$WORK/node` is `$W/node-topk`, with its own copy of
>   `conf/` (`CASSANDRA_CONF`) and `CASSANDRA_LOG_DIR=$W/node-topk/logs`, on the internal SSD (134 GiB free).
> - Appended to the node's yaml: the directories, `listen_address`/`rpc_address: 127.0.0.1`, and **`range_request_timeout: 60000ms`,
>   `read_request_timeout: 60000ms`, `native_transport_timeout: 60s`**. The ANN query has no partition key, so it is a range read whose
>   coordinator waits `range_request_timeout` (10000 ms, `conf/cassandra.yaml:1326`; `PartitionRangeReadCommand.java:292-294`,
>   `ReadCallback.java:130`) for one local response of about 80 MiB at L = 10000; the client deadline is `native_transport_timeout`
>   after enqueue (`Dispatcher.java:270`). A timeout fits no B3g row. None of these settings changes what `MAX_TOP_K` checks. Read
>   thresholds stay off (node default, `Config.java:526`). The driver's request timeout is 120 s.
> - Step 3: `-Dcassandra.sai.vector_search.max_top_k=<V>` and step 4: `-Xlog:gc*:file=$W/node-topk/gc.log:time,uptime` (literal path) go
>   into the node's `jvm-server.options`. The node runs G1 with 16 MiB regions (`jvm11-server.options:63, 66`); G1 ignores `HEAP_NEWSIZE`.
> - Step 5: there is no `setsid` on this host, so the node is a tracked background `bin/cassandra -f > node.out 2>&1 < /dev/null`, ready
>   when `nodetool status` shows `UN` and `nodetool statusbinary` prints `running`.
> - Step 6: the filed `PYTHONPATH` form imports the bundled driver 3.29.0, which has `VectorType` (`run1/stepE.txt`). Protocol 5,
>   `DCAwareRoundRobinPolicy`, token and schema metadata off, heartbeat off. `max_top_k` is a plain system property read into a
>   `static final` (`IndexWriterConfig.java:57`), not a guardrail, so no superuser exemption applies and the default
>   `AllowAllAuthenticator` is kept.

**B3b. Knobs.** V ∈ {1000 (the default), 10000}, each with a restart. Check the effective value in `ps -o args` for the JVM.

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** A third value, **V = 5000**, is added between the two filed values, so V ∈ {1000 (default), 5000, 10000}
> (group A), each with a restart on the same data directory. Read-backs for each V: the value in `ps -o args` of the daemon, the
> `-Dcassandra.sai.vector_search.max_top_k=` argument in the startup `JVM Arguments` line of `system.log`, and V in the rejection
> message of L = V+1.

**B3c. Workload.**
- Schema:
  - `CREATE KEYSPACE v WITH replication={'class':'SimpleStrategy','replication_factor':1}`;
  - `CREATE TABLE v.vt (k int PRIMARY KEY, e vector<float,16>, p blob) WITH compression={'enabled':false}`;
  - `CREATE INDEX ON v.vt(e) USING 'sai'`.
- Load 20,000 rows: e = 16 random floats in (0.1, 1), p = 8 KiB of `os.urandom`. That is about 160 MiB. Then `nodetool flush v vt`, and wait for the index build (`nodetool compactionstats` idle).
- Query `SELECT k, p FROM v.vt ORDER BY e ANN OF [0.5,...×16] LIMIT L` at CL ONE with fetch_size 10, as `ann.py <L>`:
  - V = 1000: L ∈ {1000, 1001};
  - V = 10000: L ∈ {1000, 10000, 10001}.
- Arithmetic: L=1000 gives about 8 MiB per response; L=10000 gives about 80 MiB.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).**
> - Load: `probe.py load 20000 8` with a prepared `INSERT INTO v.vt (k, e, p) VALUES (?, ?, ?)`, k = 0..19,999, e = 16 floats from
>   `random.Random(34).uniform(0.1, 1.0)`, p = `os.urandom(8192)`, **concurrency 8**; then `nodetool flush v vt`, `count(*)` = 20,000
>   (fetch 5000), and `nodetool compactionstats` with no pending task before the restart.
> - Why 8: JVector's graph builder pools one scratch object per inserting thread and refuses more than
>   `Runtime.availableProcessors() + 1` at once (`jvector-1.0.2.jar`, `PoolingSupport$ThreadPooling`, called from
>   `GraphIndexBuilder.addGraphNode` via `OnHeapGraph.add`, `OnHeapGraph.java:111, 190`). That is 11 on this 10-core host, so 32
>   concurrent inserts into the memtable vector index fail with `IllegalStateException` (seen in the cluster shakedown, 207 of
>   6000 writes). The load is not a measured step; the row count and the queries are unchanged.
> - The filed `ann.py <L>` is `probe.py q <L>`. Query text exactly `SELECT k, p FROM v.vt ORDER BY e ANN OF [0.5, …, 0.5] LIMIT L` (16 × 0.5), CL ONE, `fetch_size=10`; the
>   client reads only the first page (`rs.current_rows`) and prints rows, `has_more_pages`, the warnings, the sum of `len(p)`, and any
>   error.
> - L per V: V = 1000: {1000, 1001}; V = 5000: {1000, 5000, 5001}; V = 10000: {1000, 10000, 10001}; three repetitions each, in that
>   order (all repetitions of one L before the next).
> - Arithmetic: value bytes per response = rows × 8192 B: 8,192,000 B (7.8 MiB) at 1000, 40,960,000 B (39.1 MiB) at 5000,
>   81,920,000 B (78.1 MiB) at 10000. The filed "about 80 MiB" is this 78.1 MiB.

**B3d. Observables and instruments.**
- Client: the row count of the first page, `has_more_pages`, `rs.response_future.warnings`, and any exception.
- Server heap: `jstat -gc <pid> 100` during each query; take the peak of (S0U+S1U+EU+OU) minus the pre-query median. Also G1 humongous allocations in `gc.log`.
- Three repetitions per query.

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).**
> 1. `jstat` cannot attach on this host, so heap is read with a JMX client (`TkJmx`) that polls `java.lang:type=Memory`
>    `HeapMemoryUsage.used` (S0U+S1U+EU+OU) and the G1 collection counts every 100 ms for the whole query phase of each V.
> 2. Before each query's 2-s pre-window, an explicit full GC runs over JMX (`Memory.gc()`; amendment B3h).
> 3. **Heap Δ** of a query = the peak of `used` in [probe start, probe end + 3 s] minus the median of `used` in the 2 s before probe
>    start; the median over the three repetitions is the reading. G1's `used` moves in 16 MiB regions, so Δ has that resolution.
> 4. Humongous regions: the count before the explicit GC that follows each query (from `gc.log`, `Humongous regions: a->b`), as
>    supporting evidence only.
> 5. Rejection evidence: the client's `InvalidRequest` text with V and L in it; the response row count; the Top-K warning text.

**B3e. Procedure.**
1. With V=1000: start the node, load and flush the data, restart, and wait 30 s.
2. Run each L three times under jstat.
3. Stop the node. Set V=10000 and restart on the same data directory.
4. Repeat step 2.
5. Stop the node.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/cluster-run.sh`: fresh node
> dir; V = 1000 start, load, flush, count, compactionstats, restart; then for each V in 1000, 5000, 10000: (re)start with V, read back V,
> wait 30 s, start the heap poller, run the queries of amended B3c, stop the poller, stop the node. Logs every command and a
> `summary.txt` line per reading; stops the node on any exit, copies `system.log` and `gc.log`, and wipes the node dir.

**B3f. Predictions.**

| V | L | Outcome | Heap peak delta |
|---|---|---|---|
| 1000 | 1000 | 1000 rows in the first page despite fetch 10; has_more false; Top-K page-size warning | ≈ 8–30 MiB |
| 1000 | 1001 | rejected with ANN_LIMIT_ERROR | — |
| 10000 | 10000 | 10000 rows in one page | ≥ 80 MiB, and ≥ 5× the V=1000/L=1000 delta |
| 10000 | 10001 | rejected | — |
| 10000 | 1000 | same as V=1000/L=1000 | — |

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** Exact predictions. Heap Δ as in amendment B3d (median of three); MiB = 1,048,576 B.
>
> | V | L | Client, each run | Heap Δ (median) |
> |---|---|---|---|
> | 1000 | 1000 | 1000 rows in the first page, `has_more_pages` False, one warning "Top-K queries do not support paging and the page size is set to 10, which is less than LIMIT 1000. The page size has been set to 1000 to match the LIMIT." | ≥ 8,192,000 B (the value bytes). The filed "≈ 8–30 MiB" is an estimate: reported, not a verdict condition |
> | 1000 | 1001 | rejected: "Use of ANN OF in an ORDER BY clause requires a LIMIT that is not greater than 1000. LIMIT was 1001" | — |
> | 5000 | 1000 | as V = 1000, L = 1000 | within 32 MiB (two regions) of Δ(1000, 1000) |
> | 5000 | 5000 | 5000 rows in the first page, `has_more_pages` False, the warning with 10 / 5000 | ≥ 40,960,000 B |
> | 5000 | 5001 | rejected, "… not greater than 5000. LIMIT was 5001" | — |
> | 10000 | 1000 | as V = 1000, L = 1000 | within 32 MiB of Δ(1000, 1000) |
> | 10000 | 10000 | 10000 rows in the first page, `has_more_pages` False, the warning with 10 / 10000 | ≥ 81,920,000 B and ≥ 5 × Δ(1000, 1000) |
> | 10000 | 10001 | rejected, "… not greater than 10000. LIMIT was 10001" | — |
>
> "Heap delta scales with V" (B3g row 1) means: Δ(1000, 1000) < Δ(5000, 5000) < Δ(10000, 10000), with the bounds above.
> Validity: V read back three ways (amendment B3b), load 20,000 ok and `count(*)` 20,000, no timeout, no `OutOfMemoryError`, at
> least 10 heap samples in every pre-window.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Max response rows and heap delta scale with V, and L > V is rejected | Usage follows the constraint; confirmed |
| L > V accepted | Cap does not bind; claim wrong |
| First page has 10 rows and more pages | The target's override did not apply; trace wrong |
| Heap delta flat between L=1000 and L=10000 | Rows are not materialized together; the heap side is wrong |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows:
> - Row 1 is **Confirmed**: every cell of amended B3f holds. Rows 2, 3 and 4 are **Refuted** ("flat" in row 4: Δ(10000, 10000) within
>   32 MiB of Δ(1000, 1000)).
> - Added, **Not confirmed**: rows, pages and rejections as predicted, but a heap condition of amended B3f fails without being flat.
> - Added, **Not confirmed**: a query at L = V returns fewer than V rows in one page (the ANN search is approximate), or a warning or
>   control cell is off.
> - Added, **Invalid**: a validity condition of amended B3f fails (V not read back, load short, timeout, OOM, sampler gap).
> - **Effect rule:** row 1 gives **caps**. Row 2 gives **does not cap**. Rows 3 and 4 give **undetermined**. Not confirmed gives
>   **caps** if L = V+1 was refused at all three V and no response exceeded V rows, else **undetermined**. Invalid gives **undetermined**.
>   Bytes per row are not bounded by the knob (A3.5); this run holds the row size fixed and does not test that.

**B3h. Controls.**
- V=10000 with L=1000 isolates V from L: same L, different cap, same usage.
- Data is flushed and the index built before measuring.
- RF=1 on a single node, so there is no reconciliation. (Top-K is downgraded to ONE anyway, `:308-316`.)

> **Amendment B3h (2026-10-26, stage-4 audit, before any reading).** An explicit full GC over JMX before each pre-window, so each baseline starts from the live set after the
> previous query (heap baselines drift between queries on this host without it, as earlier runs here found). V = 5000 with L = 1000 is
> a second V-isolation control next to V = 10000 with L = 1000.

**B4. Risks and cleanup.**
- About 200 MiB of data plus SAI index under `$WORK/node`.
- Kill the node by pid, confirm with `pgrep -f CassandraDaemon`, then `rm -rf $WORK/node`.
- Nothing is written in the shared clone.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** Everything lives under `W=~/Library/Caches/stage4`: node dir `$W/node-topk` (about 200 MiB of data plus the
> SAI index), logs `$W/logs/sai_vector_search_max_top_k-execute-pageSize--autonomous/`. The node is stopped through its tracked launcher
> (`nodetool stopdaemon`, then `kill`), checked with `pgrep -f` on the daemon class (pattern split in the scripts), and `$W/node-topk` is
> wiped. The clone's `git status` is checked clean after the unit tier.

## C. Sources read

src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/index/sai/disk/v1/IndexWriterConfig.java
src/java/org/apache/cassandra/index/sai/StorageAttachedIndex.java
src/java/org/apache/cassandra/index/sai/plan/VectorTopKProcessor.java
src/java/org/apache/cassandra/index/sai/disk/v1/segment/VectorIndexSegmentSearcher.java (grep only)
src/java/org/apache/cassandra/db/ReadCommand.java
test/unit/org/apache/cassandra/index/sai/cql/VectorInvalidQueryTest.java

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1** ([results](../../stage4-runtime-verification/results/sai_vector_search_max_top_k-execute-pageSize--autonomous.md),
advisor's machine, uncommitted). Frozen at sha256 `7124f4a0…717d` after seventeen audit amendments (B2a–B2h, B3a–B3h, B4); no run-1 defect.
- **Unit: Confirmed — caps** (B2g row 1). At `max_top_k` 100, 1000 and 1500, page size 10 with LIMIT V returned V rows in one page with
  the Top-K page-size warning, and LIMIT V+1 threw `ANN_LIMIT_ERROR`; all 15 cells as predicted.
- **Cluster: Confirmed — caps** (B3g row 1). At V = 1000, 5000, 10000 (one node, 20,000 rows of 8 KiB, fetch size 10), LIMIT V returned
  V rows in one page and LIMIT V+1 was rejected, 3/3 each; coordinator heap Δ median 48, 368, 656 MiB at LIMIT V; LIMIT 1000 cost
  48–80 MiB at every V.
- For stage 3: the filed "≈ 8–30 MiB" for L = 1000 understated the coordinator's allocation (6–9× the value bytes); the filed load
  concurrency 32 fails on a host with fewer than 31 cores (JVector's builder pool allows `availableProcessors() + 1` concurrent memtable
  inserts); the ANN query without a partition key is a range read bounded by `range_request_timeout`. Not tested: the A3.5 overshoots
  (row size, tombstones), the partition-restricted ANN path, and replica-side vs coordinator-side heap.
