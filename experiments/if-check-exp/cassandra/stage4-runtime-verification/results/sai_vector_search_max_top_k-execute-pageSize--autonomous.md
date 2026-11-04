# sai_vector_search_max_top_k-execute-pageSize--autonomous — stage-4 results  <!-- file: results/sai_vector_search_max_top_k-execute-pageSize--autonomous.md -->

> **Case:** [`sai_vector_search_max_top_k-execute-pageSize--autonomous`](../../stage3-ai-deep-read/cases/sai_vector_search_max_top_k-execute-pageSize--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/`](../harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/).
>
> **Unit: Confirmed — caps** (B2g row 1).
> - All 15 cells were as predicted at `max_top_k` V = 100, 1000 (default) and 1500.
> - At every V, an ANN query with client page size 10 and LIMIT V returned V rows in one page with the Top-K page-size warning;
>   LIMIT V+1 threw `InvalidRequestException: … not greater than V. LIMIT was V+1`.
> - Paging off (P = −1) returned V rows with no warning; P = 5000 > LIMIT 50 returned 50 rows with no warning.
>
> **Cluster: Confirmed — caps** (B3g row 1). One node, 20,000 rows of 8 KiB, fetch size 10, three restarts with V = 1000, 5000, 10000.
> - LIMIT V returned V rows in the first page (`has_more_pages` False) at each V, 3/3; LIMIT V+1 was rejected with ANN_LIMIT_ERROR
>   naming V, 3/3.
> - Coordinator heap Δ median at LIMIT V: **48, 368, 656 MiB** at V = 1000, 5000, 10000 (bounds ≥ 7.8, 39.1, 78.1 MiB; 656 ≥ 5 × 48).
> - The same LIMIT 1000 at V = 5000 and 10000: 64 and 80 MiB, within the 32 MiB tolerance of 48 MiB (the second at its edge).
>
> No run 2.
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster). "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> An earlier stage-3 session wrote the case file; this session did not.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `80daf71` (sha256 `c0ed4528…edd0f`). Frozen after the step-0 audit's seventeen amendments (2026-10-26, before any run-1 reading) at sha256 **`7124f4a0160c13b81f7dae21fb4a7a6c22b129b3ea4c40db496ba799773d717d`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX.md` §4. `run1/freeze.txt` holds this hash plus the harness and self-check hashes. Nothing committed: no commit was asked for. |
| **Harness** | [`../harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/`](../harness/sai_vector_search_max_top_k-execute-pageSize--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** three `ant testsome` JVMs, `max_top_k` V ∈ {100, 1000 (default), 1500}; 5 (P, L) cases each = 15 cases; 2000 rows, `vector<float, 4>`. **Cluster (B3):** one node, heap 2G, G1; V ∈ {1000 (default), 5000, 10000}, one restart per V on the same data; 8 (V, L) cells × 3 repetitions = 24 queries; 20,000 rows × 8,192 B, `vector<float,16>`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `TopKProbeBase.java` (abstract, extends `SAITester`; the B2c workload and cases), `TopKProbe100Test.java`, `TopKProbeDefaultTest.java`,
  `TopKProbe1500Test.java` (each only a static block setting the property, and the expected value), `unit-run.sh`.
- `TkJmx.java`: a JMX client that triggers a full GC, reads the knob from the runtime MXBean's input arguments, and polls the heap
  every 100 ms.
- `probe.py`: a bundled-driver client for setup, load, count and the ANN query.
- `cluster-run.sh`: load at V = 1000, then one node lifetime per V.
- `summarize.py`: builds the readings table.

**Note 2, instrument checks before the freeze:**
- **Unit shakedown:** the V = 100 class alone (`shakedown/unit1-V100-summary.txt`). Ran as written; the clone was clean after it.
- **Cluster shakedown 1:** 6,000 rows, V ∈ {1000, 5000}, one repetition (`shakedown/cluster1-*`). It found three problems, all fixed
  before the freeze. None touched a prediction.
  - 207 of 6,000 writes failed: `IllegalStateException: Number of outstanding pooled objects has gone beyond the limit of 11`
    (`shakedown/cluster1-load-failure-cause.txt`). JVector's graph builder allows `availableProcessors() + 1` concurrent memtable
    inserts (`jvector-1.0.2.jar` `PoolingSupport$ThreadPooling`, read with `javap`), 11 on this 10-core host, and the filed load used
    32. Fix: load concurrency 8, written into amendment B3c before the freeze.
  - The OOM count matched `Ljava/lang/OutOfMemoryError` in a JVM line of `node.out` (`grep` regex dot). Fix: fixed-string match, in
    the script and in `selfcheck.py`.
  - The JVM rotates `gc.log` at each start, so only the last lifetime's file was copied. Fix: copy `gc.log*`; humongous lookup
    limited to the next query's GC.
- **Cluster shakedown 2:** the same parameters after the fixes (`shakedown/cluster2-*`): load 6000/6000, no ERROR line.

**Note 3, self-check:** [`run1/selfcheck.py`](sai_vector_search_max_top_k-execute-pageSize--autonomous/run1/selfcheck.py) was written
before run 1 and tested on the shakedowns: 33/33 on unit shakedown + cluster shakedown 2 (`shakedown/selfcheck-on-shakedown.out`).

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the knob counts rows (the ANN LIMIT); bytes = rows × row size. The cluster tier fixes the row at 8 KiB and measures coordinator heap. The unit tier counts rows only (gap named in amendment B2d). |
| A. Core question | knob varied, ≥ 3 values incl. default | Not met → Met after amendment | Filed: two values per tier. Added: 1500 in the unit tier, 5000 in the cluster tier (amendments B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Cluster: heap used. `jstat` cannot attach on this host, so a JMX poller at 100 ms with an explicit GC before each baseline (amendments B3d, B3h). Unit: rows only. |
| A. Core question | usage driven to the limit and past it | Met | L = V and V+1 at every V in both tiers. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Filed cells "same", "≈ 8–30 MiB", "≥ 80 MiB" and the unstated warning for (10, V+1) were made exact: full tables, warning and rejection texts, heap bounds in bytes, the "same" tolerance (32 MiB = two G1 regions), and "scales with V" as a strict order (amendments B2f, B3f). "≈ 8–30 MiB" was kept as an estimate that is reported but is not a verdict condition. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Added: Invalid rows, fewer rows than L (the search is approximate), heap between bounds, off-prediction cells, verdict words, Effect rule (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The rejection boundary moves with V; direct disallow evidence: the server's `ANN_LIMIT_ERROR` text naming V and L (`StorageAttachedIndex.java:141, 503-504`). |
| B. Logic | alternative explanations and their controls | Met | (5000, 50) and (−1, V) in the unit tier; V-isolation at L = 1000 in the cluster tier; flushed data, fresh JVM per V; amendment B3h adds the explicit GC. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Insert statement, `requireNetwork()` for the range read, probe output format, load concurrency and the `ann.py` = `probe.py q` mapping added (amendments B2a, B2c, B2d, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Heap Δ definition, sampling, read-backs three ways (amendments B3b, B3d). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | Linux, `$WORK`, `bin/cassandra -p` (no `setsid` here), `jstat`, and `ant jar` (no test classes) did not fit this host (amendments B2a, B3a, B3d, B4). The filed driver import works and has `VectorType` (`run1/stepE.txt`). |
| D. Runnable | workload arithmetic reaches the limit | Met → amended | 160 MiB of data against 134 GiB free; 2G heap. The ANN query is a range read with a 10 s `range_request_timeout` and an 80 MiB single response, so the timeouts were raised to 60 s (amendment B3a). The filed load concurrency failed on this host (shakedown 1; amendment B3c). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: see Note 4. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and `build-test`; harness classes; `requireNetwork()` | Amendment 2026-10-26 | `testsome` needs test classes; the ANN query is a range read. |
| 2 | B2b: third value 1500 | Amendment 2026-10-26 | Group A. |
| 3 | B2c: insert text, read thresholds off, 15 cases | Amendment 2026-10-26 | Unit yaml enables read thresholds (A4). |
| 4 | B2d: output format; rows-only gap | Amendment 2026-10-26 | Group B/C. |
| 5 | B2e: `unit-run.sh` | Amendment 2026-10-26 | Clean clone. |
| 6 | B2f: full table with exact texts, warning at (10, V+1) | Amendment 2026-10-26 | `:322-328` runs before `:332`. |
| 7 | B2g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 8 | B2h: 1500 as upward control | Amendment 2026-10-26 | Group B. |
| 9 | B3a: host paths, tracked node, timeouts 60 s, no auth needed | Amendment 2026-10-26 | Range read timeout; no `setsid`; `MAX_TOP_K` is not a guardrail. |
| 10 | B3b: V = 5000; read-backs three ways | Amendment 2026-10-26 | Group A. |
| 11 | B3c: load details, concurrency 8, query text, L per V, arithmetic | Amendment 2026-10-26 | JVector pool limit (shakedown 1). |
| 12 | B3d: JMX heap poller; heap Δ; humongous; rejection evidence | Amendment 2026-10-26 | `jstat` cannot attach. |
| 13 | B3e: one script | Amendment 2026-10-26 | Order. |
| 14 | B3f: exact table for three V | Amendment 2026-10-26 | Group B. |
| 15 | B3g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 16 | B3h: explicit GC before each baseline; second V-isolation control | Amendment 2026-10-26 | Baseline drift on this host (earlier runs). |
| 17 | B4: host paths and checks | Amendment 2026-10-26 | Paths. |
| 18 | Test the A3.5 overshoots (unbounded row size, tombstones outside the queue), the partition-restricted ANN path (`getSliceCommands`, `SelectStatement.java:740`), and the replica-side top-K heap apart from the coordinator's | Left for stage 3 | Not needed for B1's claim. |
| 19 | The "≈ 8–30 MiB" estimate for L = 1000 does not account for coordinator copies; size estimates as a multiple of the value bytes | Left for stage 3 | Estimate only; see §4.2 part 2. |

**Note 4, citations checked:** `SelectStatement.java:115-123, 280-361, 395-416, 540-552, 730-742, 800-808`; `ReadCommand.java:405-415`;
`Index.java:681-683, 987-990`; `StorageAttachedIndex.java:118, 141, 496-505`; `IndexWriterConfig.java:57`;
`CassandraRelevantProperties.java:479`; `VectorTopKProcessor.java:75-123`; `VectorIndexSegmentSearcher.java:113-124`;
`OptimizeFor.java:43-46`; `VectorMemoryIndex.java:156-245`; `OnHeapGraph.java:111, 190`; `PartitionRangeReadCommand.java:292-294`;
`ReadCallback.java:130`; `Dispatcher.java:270`; `Config.java:145, 526, 1399`; `conf/cassandra.yaml:42, 1322, 1326, 2015-2030`;
`test/conf/cassandra.yaml:63-67`; `CQLTester.java:613-636, 1593-1596`; `SAITester.java:118, 155-161`; `QueryOptions.java:82-92`;
`jvm11-server.options:63, 66`. All hold.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 14:58–14:59 EDT; cluster 14:59–15:06 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 134 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present (one node, 127.0.0.1). Ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms2G -Xmx2G`, G1 with 16 MiB regions (`HEAP_NEWSIZE=400M` set as filed, ignored under G1), no agent |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip` (subfolder import, `VectorType` present), protocol 5, no auth |
| Local `cassandra-src` clone | `$W/cassandra-run34` = `~/Library/Caches/stage4/cassandra-run34`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 53 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | filed `80daf71`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-topk/{data,commitlog,hints,saved_caches,cdc_raw,logs}` and `gc.log*`, own `conf/`; wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/sai_vector_search_max_top_k-execute-pageSize--autonomous/` (contents below) |

Full-log contents, under that directory:
- `clone-build-run34.log`, `stepE.txt`, `unit.out`, `cluster.out`;
- `shakedown/` (`unit1/`, `cluster1/`, `cluster2/`, `selfcheck-on-shakedown.out`), which is not evidence;
- `unit/`: `ant-<V>.log`, `TEST-<V>.log`, `TEST-<V>.xml`, `probe-<V>.txt` for V = 100, 1000, 1500, `commands.log`, `summary.txt`;
- `cluster/`: `node.out`, `system.log`, `gc.log*` (four lifetimes), `heap-V<V>.tsv`, `commands.log`, `summary.txt`, `readings.txt`,
  `syslog-V<V>-L<L>-r<r>.txt` per query, `yaml-*`, `jvm-server-options-added-V<V>.txt`, `error-warn.txt`, `jmx.err` and
  `client.err` (both empty).

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`; every `ant` call takes `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the
  network ran unsandboxed.
- **Node start:** no `setsid`, so the node is a tracked background `bin/cassandra -f`.
- **Unit test output:** `build/test/logs/**/TEST-<class>.log`, one line per write. `DatabaseDescriptor.daemonInitialization()` runs
  once per JVM, so each V ran in its own JVM; the property was set in a static block before any SAI class loaded, and the first check
  read `IndexWriterConfig.MAX_TOP_K` back.
- **Unit yaml:** read thresholds on (`test/conf/cassandra.yaml:63-67`), turned off in the probe. `CQLTester.requireNetwork()` was
  called (the ANN query is a range read). `formatQuery` takes one `%s`; `parseStatement(String, ClientState)` returns the prepared
  statement.
- **Driver:** bundled driver, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off; it has `VectorType`, so the
  load binds vectors in a prepared statement. No reconnect was needed (`client.err` empty).
- **Authentication:** `max_top_k` is a system property read into a `static final` (`IndexWriterConfig.java:57`), checked in
  `StorageAttachedIndex.validate` with no client-state test, so it is not a guardrail and has no superuser exemption.
  `AllowAllAuthenticator` was kept.
- **Heap instruments:** `jstat` cannot attach, so a JMX poller; an explicit GC before each baseline; `GC.heap_info`, jmxterm,
  `nodetool sjk mx` and MAT not used.
- **Script hygiene:** the daemon pattern in the scripts is split; long steps ran in the background and were polled; shakedowns ran
  before run 1; bounds derived from source (rows × 8,192 B, 16 MiB regions); baselines after ingest, flush, restart and a GC;
  `selfcheck.py` written before run 1. Byteman was not needed.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | Linux, `$WORK`, `ant jar` (no test classes), `bin/cassandra -p` (no `setsid` here) | host paths; `build-test`; tracked `bin/cassandra -f` (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3d | `jstat` cannot attach on this host | JMX client `TkJmx` (heap poll, GC, knob read-back) (amendments B3d, B3h) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3a | The ANN query has no partition key, so it is a range read bounded by `range_request_timeout` (10 s) with an 80 MiB response | timeouts 60 s (amendment B3a) | 2026-10-26, before the freeze | uncommitted |
| A4 | shakedown 1 | B3c | Load at concurrency 32 fails on a 10-core host: JVector's builder pool limit is `availableProcessors() + 1` = 11 | concurrency 8 (amendment B3c) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |

Run 1: none. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `sai_vector_search_max_top_k-execute-pageSize--autonomous/run1/unit/commands.log`,
`sai_vector_search_max_top_k-execute-pageSize--autonomous/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-probe-lines-<V>.txt`, `ant-tests-run-<V>.txt`, `summary.txt`.
- Ant: `Tests run: 1, Failures: 0, Errors: 0` for each of the three classes.
- Setup: `MAX_TOP_K=100 expected=100 property=100`; `MAX_TOP_K=1000 expected=1000 property=null`; `MAX_TOP_K=1500 expected=1500
  property=1500`. `readThresholdsEnabled=false`, `rows=2000`, `done cases=5` in each.

| Case (P, L) | V = 100 | V = 1000 (default) | V = 1500 |
|---|---|---|---|
| (10, 50) | rows 50, single page, warning 1 | rows 50, single page, warning 1 | rows 50, single page, warning 1 |
| (10, V) | rows **100**, single page, warning 1 | rows **1000**, single page, warning 1 | rows **1500**, single page, warning 1 |
| (10, V+1) | **threw** `InvalidRequestException: … not greater than 100. LIMIT was 101`; warning 1 | **threw** `… 1000. LIMIT was 1001`; warning 1 | **threw** `… 1500. LIMIT was 1501`; warning 1 |
| (−1, V) | rows 100, single page, warning 0 | rows 1000, single page, warning 0 | rows 1500, single page, warning 0 |
| (5000, 50) | rows 50, single page, warning 0 | rows 50, single page, warning 0 | rows 50, single page, warning 0 |

Each warning is exactly "Top-K queries do not support paging and the page size is set to 10, which is less than LIMIT L. The page
size has been set to L to match the LIMIT." with the case's L, and it is the only warning.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `readings.txt`, `jvm-server-options-added.txt`, `yaml-overrides.txt`,
`syslog-slices-counts.txt`, `error-warn.txt`.

Setup and validity:
- Read-backs at each start, three ways (`ps -o args`, the `JVM Arguments` line, the runtime MXBean): 1000, 5000, 10000. Timeouts
  `range_request_timeout=60000ms read_request_timeout=60000ms native_transport_timeout=60s`, `read_thresholds_enabled=false`.
- Load: 20,000 ok, 0 failed, at concurrency 8 in 4.3 s; flush; 2 sstables, 170,927,295 B live; `count(*)` 20,000; compactions idle
  before each query phase.
- 0 ERROR lines in the whole log and in all 24 query slices; no `java.lang.OutOfMemoryError`; `client.err` and `jmx.err` empty.
- Heap baseline after the explicit GC: 60–93 MiB. 18–19 samples in each pre-window. No GC inside any query window.

Heap Δ is the peak in the window minus the median of the 2 s before it, in MiB at 16 MiB resolution. "Humongous" is the number of
16 MiB humongous regions at the explicit GC after the query (— for the last query of a lifetime).

| V | L | Client, each of 3 runs | Heap Δ r1, r2, r3 (median) | Amended B3f | Humongous |
|---|---|---|---|---|---|
| 1000 | 1000 | ok, **1000 rows**, has_more False, the warning 10/1000 | 80, 48, 32 (**48**) | ≥ 7.8 MiB | 1 |
| 1000 | 1001 | **rejected** `InvalidRequest … Use of ANN OF in an ORDER BY clause requires a LIMIT that is not greater than 1000. LIMIT was 1001` | 32, 0, 16 (16) | — | 0 |
| 5000 | 1000 | ok, 1000 rows, has_more False, the warning | 80, 64, 64 (**64**) | within 32 of 48 | 1 |
| 5000 | 5000 | ok, **5000 rows**, has_more False, the warning 10/5000 | 416, 368, 352 (**368**) | ≥ 39.1 MiB | 14 |
| 5000 | 5001 | **rejected** `… not greater than 5000. LIMIT was 5001` | 8, 16, 16 (16) | — | 0 |
| 10000 | 1000 | ok, 1000 rows, has_more False, the warning | 80, 64, 80 (**80**) | within 32 of 48 | 1 |
| 10000 | 10000 | ok, **10000 rows**, has_more False, the warning 10/10000 | 720, 656, 640 (**656**) | ≥ 78.1 MiB and ≥ 5 × 48 | 23 |
| 10000 | 10001 | **rejected** `… not greater than 10000. LIMIT was 10001` | 16, 16, 32 (16) | — | 0 |

Every accepted response had distinct keys equal to its row count and value bytes = rows × 8,192. Client time: 0.4–0.7 s at L = 1000,
0.8–1.2 s at 5000, 3.1–3.4 s at 10000; 0.3–0.4 s for a rejection.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/test-log-probe-lines-<V>.txt`, `ant-tests-run-<V>.txt`]
   - `MAX_TOP_K` read back equal to V in each JVM, before the table was created; read thresholds off; 2000 rows; 5 cases; the test passed.
   - The limit was reached (L = V) and passed (L = V+1) at each V.
2. **Readings** — Nothing unusual. The (10, V+1) cases carry the page-size warning before the throw, as amended B2f derived from
   `:322-328` preceding `:332`.
3. **Matched row** — B2g row 1, "rows equal L up to max_top_k in one page, and L = max_top_k+1 is rejected". [observed]
   - (10, V) returned V rows with `pagingState == null` at V = 100, 1000, 1500.
   - (10, V+1) threw `ANN_LIMIT_ERROR` naming V and V+1 at each V.
   - Every other cell of amended B2f held: the warning in the P < L cases only; P = −1 and P = 5000 without it.
4. **Excluded rows**
   - Row 2 (rows capped at P = 10, more pages): every accepted case was one page with L rows.
   - Row 3 (L > V accepted): rejected at all three V.
   - Row 4 / added Invalid (property not applied, rows ≠ 2000, cases missing): all hold.
   - Added Not confirmed (fewer rows than L, a cell off): no case.
5. **Observed vs. inferred** — The effective page size is inferred from the row count plus the warning, as B2d says; both are observed.
6. **Deviations and gaps** — None in the run. The unit tier counts rows, not bytes (named in amendment B2d).
7. **Core question** — The largest ANN response follows the knob: 100, 1000 and 1500 rows at V = 100, 1000, 1500, in one page whatever
   the client's page size, and one row more is refused before execution.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect (amended B2g): **caps**.

**Cluster tier**

1. **Validity** — Valid. [observed: `cluster/summary.txt` READBACK, LOAD, COUNT, ERRORS lines; heap sampler coverage from self-check C5]
   - V read back three ways at each lifetime; timeouts read back; load and count 20,000; no ERROR, no OOM, no timeout.
   - The limit was reached and passed at each V (L = V accepted, L = V+1 refused).
2. **Readings** — Points worth noting:
   - The first L = 1000 query after each start read 80 MiB; later repetitions 32–80. [observed: `readings.txt`] The 80 MiB first
     reading in all three lifetimes suggests a first-query cost after a restart [inferred: same position, same value, three times].
     The medians therefore have a 16–32 MiB spread across V.
   - The V = 10000, L = 1000 control's median (80) is 32 MiB from Δ(1000, 1000) (48): inside the amended tolerance, at its edge.
   - The filed estimate "≈ 8–30 MiB" for L = 1000 was not met: 32–80 MiB, median 48. Amended B3f (made before any reading) kept it as
     an estimate, not a verdict condition. The coordinator allocates 6–9× the value bytes: 48/7.8, 368/39.1, 656/78.1.
   - No GC fell inside any window, so each Δ is all allocation by the query up to the next explicit GC, live plus transient.
3. **Matched row** — B3g row 1, "max response rows and heap delta scale with V, and L > V is rejected". [observed]
   - Max response rows: 1000, 5000, 10000 at V = 1000, 5000, 10000, one page each, 3/3.
   - L = V+1 rejected at each V with the server's text naming V, 3/3.
   - Heap Δ median at L = V: 48 < 368 < 656 MiB, each above its byte bound; 656 ≥ 5 × 48 = 240.
   - The controls at L = 1000 held (64 and 80 vs 48, tolerance 32), and the warnings were as predicted.
4. **Excluded rows**
   - Row 2 (L > V accepted): rejected 9/9.
   - Row 3 (first page 10 rows, more pages): every accepted response was L rows with `has_more_pages` False.
   - Row 4 (flat): Δ(10000, 10000) − Δ(1000, 1000) = 608 MiB > 32.
   - Added rows: heap between bounds (no); fewer than V rows (no; distinct keys = rows); a control or warning off (no); Invalid (all
     validity conditions hold).
5. **Observed vs. inferred** — Two statements are inferred; the verdict uses neither.
   - That the heap Δ at L = V is the coordinator building and sending one response [inferred: no other activity in the window (no ERROR,
     no compaction line, compactions idle), and the same L = 1000 gives about the same Δ at three V].
   - That the humongous regions after L = 5000 (14) and 10000 (23) are the response buffers [inferred: objects ≥ 8 MiB; 1 after
     L = 1000, 0 after a rejection].
6. **Deviations and gaps** — None in the run.
   - Heap Δ measures allocation in the window, not retained heap; the B3f bounds ("at least the value bytes") are lower bounds and hold
     either way.
   - Replica-side and coordinator-side top-K structures are not separated on one node.
   - Bytes per row are fixed by the workload; the unbounded row size of A3.5 is not tested.
7. **Core question** — Usage follows the constraint: the largest ANN response is exactly V rows at each of three values, the
   coordinator heap for it grows with V (48 → 368 → 656 MiB), and a query one row past V is refused with no heap growth beyond
   16 MiB. The same LIMIT at different V costs the same within the tolerance, so V, not the query, sets the ceiling.

**Cluster tier conclusion:** B3g row 1 — **confirmed**. Effect (amended B3g): **caps**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, sha256 in `run1/freeze.txt`) re-reads the raw files and re-derives every amended B2f and
B3f condition:
- `unit/TEST-<V>.log` (the `PROBE` lines, not `probe-<V>.txt`) and `unit/ant-<V>.log`;
- the cluster's `summary.txt` (RUN, READBACK, LOAD, COUNT, QUERY, ERRORS lines);
- `heap-V<V>.tsv`: it recomputes each baseline median and peak from the raw samples with its own code (not `summarize.py`);
- the full `system.log` and `node.out`: `JVM Arguments` lines per V, OOM count.

Output `run1/selfcheck.out`: **64 checks, 64 pass, 0 fail**:
- U0–U5: 30 unit checks (10 per V);
- C0–C5b: 13 cluster validity checks;
- C6/C6b: 13 cell checks (8 cells; 5 supporting distinct-key/byte checks on the accepted cells);
- C7–C9: 8 heap checks (bounds, the two controls, 5×, not flat, strict order).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U4, C0–C5b pass; READBACK lines re-read: three sources agree at each V |
| 2. Readings | yes | `readings.txt` re-read: r1 of L = 1000 is 80 MiB in all three lifetimes; `gcs=0` in all 24 windows; the V = 10000 control is exactly 32 MiB from Δ(1000, 1000) (C8 passes with ≤) |
| 3. Matched row | yes | U5 (15 checks) and C6 (8 cells) pass; C7 bounds and order pass |
| 4. Excluded rows | yes | No acceptance over V, no paging, C9 (not flat) passes, no OOM or ERROR |
| 5. Observed vs. inferred | yes | The two inferred statements are not used by the verdict |
| 6. Deviations and gaps | yes | Defects A1–A4 fixed before the freeze; the shakedown fixes touched the harness, `selfcheck.py` and the load concurrency only, no prediction; no run-1 defect |
| 7. Core question | yes | The ceiling on rows follows the knob at three values in both tiers, with direct disallow evidence (the server's `ANN_LIMIT_ERROR` text); the cluster heap at L = V rises with V |

### 5.2 Run 2?

**No** — 2026-10-26.
- Every verdict statement is observed.
- The self-check settles every part from run 1's files.
- The result confirms the file's own claim; it is neither a refutation nor a bypass.
- One condition (the V = 10000 control) passed at the edge of its tolerance; it is a control, not the ceiling, and the ceiling
  readings are far from their bounds.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):**
- an ANN query with LIMIT L ≤ `max_top_k` returns min(L, matching rows) rows in a single response, whatever the client fetch size;
- an ANN query with L > `max_top_k` is rejected;
- so per-response rows and coordinator heap scale with `max_top_k`.

"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | **caps** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1) | **caps** | run 1 + self-check | 2026-10-26 |

1. **Unit:** LIMIT V returns V rows in one page at V = 100, 1000, 1500 with page size 10; LIMIT V+1 is refused with `ANN_LIMIT_ERROR`.
2. **Cluster:** LIMIT V returns V rows in one page at V = 1000, 5000, 10000; LIMIT V+1 is refused; coordinator heap Δ median 48, 368,
   656 MiB at LIMIT V. Bytes per row are not bounded by the knob (A3.5, not tested): the cap is on rows.

**Positive control:** not required, since this is not a negative-estimate file.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a–B2h, B3a–B3h and B4 are in the case file (uncommitted).
- `_INDEX.md`: §2 row `7124f4a0…717d` added, and the §1 Stage 4 column filled.
- `HANDOFF.md` not edited (`HANDOFF-ADVISOR.md` §8).
