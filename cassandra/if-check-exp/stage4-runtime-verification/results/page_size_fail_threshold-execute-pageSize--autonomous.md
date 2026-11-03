# page_size_fail_threshold-execute-pageSize--autonomous — stage-4 results  <!-- file: results/page_size_fail_threshold-execute-pageSize--autonomous.md -->

> **Case:** [`page_size_fail_threshold-execute-pageSize--autonomous`](../../stage3-ai-deep-read/cases/page_size_fail_threshold-execute-pageSize--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/page_size_fail_threshold-execute-pageSize--autonomous/`](../harness/page_size_fail_threshold-execute-pageSize--autonomous/).
>
> **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1).
> - All 36 cells were as predicted, through both entry points (client `execute`, target `:338`; `executeLocally`, target `:602`).
> - A paged SELECT with page size P > fail is rejected: c2 at fail 10, and c5 at 10 and 1000.
> - Paging off (c3) and `LIMIT 2000` with P = 2000 (c4) return all 2000 rows in one response, with no rejection and no warning, at
>   fail 10 and fail 1000.
>
> **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1). One node, PasswordAuthenticator, non-superuser role `app`,
> 100,000 rows of 2 KiB in one partition.
> - At T = 1000, Q2 (fetch 2000) and Q5 (fetch 50,000, `LIMIT 50001`) are rejected 3/3 each. Their heap Δ median is 16 and 32 MiB.
> - At T = 1000, Q3 (paging off) returns 100,000 rows in one response, with heap Δ median 1,168 MiB; the bound was 195.3 MiB.
> - At T = 1000, Q4 (`LIMIT 50000`, fetch 50,000) returns 50,000 rows, with heap Δ median 704 MiB; the bound was 97.7 MiB.
> - Q3 and Q4 are the same at T = 10000 and at T = −1.
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
| **Case-file version** | Filed in commit `80daf71` (sha256 `19337bdf…270a9`). Frozen after the step-0 audit's seventeen amendments (2026-10-26, before any run-1 reading) at sha256 **`42872914bef8a3d2dfde36ce207b958061eb588816d7f6f3e95bb0a0086e2854`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX-advisor.md` §2. `run1/freeze.txt` holds this hash plus the harness and self-check hashes. Nothing committed: no commit was asked for. |
| **Harness** | [`../harness/page_size_fail_threshold-execute-pageSize--autonomous/`](../harness/page_size_fail_threshold-execute-pageSize--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM; (warn, fail) ∈ {(5, 10), (500, 1000), (−1, −1)} × entry {D, L} × c1–c6 = 36 cases, 2000 rows of 100-byte text. **Cluster (B3):** one node, heap 2G, G1; T ∈ {1000 (yaml), 10000, −1 (JMX)}; Q1–Q5 three times each = 45 queries; 100,000 rows × 2,048 B in one partition. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `PageSizeBranchProbeTest.java` (B2c as amended) and `unit-run.sh`.
- `PsJmx.java`: a JMX client that reads and sets thresholds, reads RowsRead, triggers GC, and polls the heap every 100 ms.
- `probe.py`: a bundled-driver client for setup, load, count and the queries.
- `cluster-run.sh`: one node lifetime after the load, and three threshold phases.
- `summarize.py`: builds the readings table.

**Note 2, instrument checks before the freeze:**
- **Unit shakedown:** 50 rows, fail 10 only (`shakedown/unit-rows50-thr5-10-summary.txt`).
- **Cluster shakedown 1:** 20,000 rows, BIG 10,000 (`shakedown/cluster1-*`). It found three harness problems, all fixed before the freeze. None was in the case file's predictions.
  - The RowsRead bean is not registered before the first non-system query. Its counters are created at class load (`ClientRequestSizeMetrics.java:39-42`). Fix: `PsJmx` reports 0 when the bean is absent.
  - Error text was cut at the `]` of `[Invalid query]`. Fix: the parsers.
  - The heap baseline drifted upward with no GC between queries, from 256 to 1,848 MiB. Fix: amendment B3h, an explicit GC before each pre-window.
  - Its T = 10000 Q5 was accepted only because the shakedown's BIG equalled T. `page size > T` is strict.
- **Cluster shakedown 2:** 40,000 rows, BIG 20,000, after the fixes (`shakedown/cluster2-*`).

**Note 3, self-check:** [`run1/selfcheck.py`](page_size_fail_threshold-execute-pageSize--autonomous/run1/selfcheck.py) was written before run 1 and tested on the shakedowns (`shakedown/selfcheck-on-shakedown.out`):
- Shakedown 2 scores 23/23.
- Shakedown 1 has 15 expected failures: the shakedown parameters and the pre-fix bugs.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the knob counts rows per page. Bytes are derivable: unit 100 B values, cluster 2,048 B values. The cluster tier measures coordinator heap. The unit tier counts rows only, a gap named in amendment B2d. |
| A. Core question | knob varied, ≥ 3 values incl. default | Not met → Met after amendment | Filed: unit (10, 1000); cluster 1000 plus "disabled" for Q2/Q5 only. Added: the default −1 in both tiers, and T = 10000 in the cluster tier, with all five queries at every T (amendments B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Cluster: heap used. `jstat` cannot attach on this host, so a JMX `HeapMemoryUsage` poller at 100 ms is used (amendment B3d). Unit: rows only (gap named). |
| A. Core question | usage driven to the limit and past it | Met | Page sizes and responses on both sides of each T: 100,000-row response vs T = 1000. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Blank cells ("—"), no column for the third value, "≈ 0" and "≥ 200 MiB" stated loosely. Made exact: full tables, heap bounds 50 MiB / 204,800,000 B / 102,400,000 B on the median of three, RowsRead Δ, ERROR-line count (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Added: Invalid (read-backs, superuser check, load, sampler), heap between the bounds, OOM, other cells off-prediction, verdict words, Effect rule (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Rejection boundary moves with T (Q2 rejected at 1000, accepted at 10000 and −1; Q5 rejected at 1000 and 10000, accepted at −1). Direct disallow evidence: the server's `InvalidRequest` text, RowsRead Δ 0, and the ERROR line, logged once per distinct message by `NoSpamLogger` (`Guardrail.java:47-48`; amendments B2d, B3d). |
| B. Logic | alternative explanations and their controls | Met | Superuser case c6, raised and disabled T, flushed data with a fresh JVM; amendment B3h adds the explicit GC before each baseline. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Query text missing: a query without `WHERE k = 0` would be a range read. Probe output format and log locations added (amendments B2d, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Heap Δ definition, per-query procedure, RowsRead bean, superuser wait (amendments B3c–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | The design assumes `/local`, `bin/cassandra -p` (no `setsid` here), `jstat` and `nodetool sjk mx`, and the unit yaml's read thresholds. Fixed before the freeze (amendments B2a, B2c, B3a, B3d, B4). The filed driver import works (`run1/stepE.txt`). |
| D. Runnable | workload arithmetic reaches the limit | Met | 200 MiB of data against 135 GiB free; 2G heap. A 205 MB single response vs the 5 s `read_request_timeout` was a risk, so the timeout was raised to 60 s (amendment B3a). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: see Note 4 below the recommendations. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and build; harness location | Amendment 2026-10-26 | `/local` does not exist here; `testsome` needs `build-test`. |
| 2 | B2b: third pair (−1, −1); set in the loop; read-back | Amendment 2026-10-26 | Group A; one test method loops over thresholds. |
| 3 | B2c: fixed text, 36 cases, read thresholds off | Amendment 2026-10-26 | Unit yaml enables read thresholds (another consumer, A4). |
| 4 | B2d: output format; NoSpamLogger-aware ERROR count; gap | Amendment 2026-10-26 | Group B/C. |
| 5 | B2e: `unit-run.sh` | Amendment 2026-10-26 | Clean clone. |
| 6 | B2f: full table incl. fail = −1 | Amendment 2026-10-26 | Blank cells. |
| 7 | B2g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 8 | B2h: (−1, −1) as control | Amendment 2026-10-26 | Group B. |
| 9 | B3a: host paths, tracked node, gc log, `read_request_timeout` 60 s | Amendment 2026-10-26 | No `setsid`; 205 MB single response. |
| 10 | B3b: T ∈ {1000, 10000, −1}, JMX client, read-backs | Amendment 2026-10-26 | Group A; sjk exits 0 on failure. |
| 11 | B3c: `WHERE k = 0` query text; load and superuser wait; order | Amendment 2026-10-26 | Missing query text. |
| 12 | B3d: JMX heap poller; heap Δ definition; RowsRead; disallow evidence | Amendment 2026-10-26 | `jstat` cannot attach; group B. |
| 13 | B3e: one script | Amendment 2026-10-26 | Order. |
| 14 | B3f: exact table for three T values | Amendment 2026-10-26 | Group B. |
| 15 | B3g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 16 | B3h: explicit GC before each pre-window | Amendment 2026-10-26 | Baseline drift (shakedown 1); B3h's stated intent. |
| 17 | B4: host paths and checks | Amendment 2026-10-26 | Paths. |
| 18 | Also measure heap per entry in the unit tier, the TopK and NODE_LOCAL (`-Dcassandra.enable_nodelocal_queries`) bypasses of A3 on a node, and a run with the heap baseline separated into retained vs transient (a GC inside the window) | Left for stage 3 | Not needed for B1's claim. |

**Note 4, citations checked:** `SelectStatement.java:280-361, 417-431, 505-540, 574-623, 881-924`; `Guardrail.java:47-48, 93-96, 120-141, 187-194`; `Threshold.java:100-147`; `Guardrails.java:56, 237-246, 862-876`; `Config.java:873-874`; `ClientState.java:594-605`; `QueryOptions.java:62-75`; `QueryProcessor.java:274-327`; `ReadResponse.java:182-207`; `AbstractQueryPager.java:185-238`; `DataLimits.java:139-142`; `ClientRequestSizeMetrics.java:37-44`; `SchemaConstants.java:59-68, 144-148`; `GuardrailTester.java:84-160`; `GuardrailPageSizeTest.java`; `test/conf/cassandra.yaml:63-67`; `conf/cassandra.yaml:198, 217, 1322, 2089-2090`; `cassandra-env.sh:75-133`; `jvm11-server.options:63-79`. All hold.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 14:25–14:26 EDT; cluster 14:26–14:37 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 135 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present (one node, 127.0.0.1). Ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms2G -Xmx2G`, G1 with 16 MiB regions (`HEAP_NEWSIZE=400M` set as filed, ignored under G1), no agent |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip` (subfolder import), protocol 5, `PlainTextAuthProvider` |
| Local `cassandra-src` clone | `$W/cassandra-run33` = `~/Library/Caches/stage4/cassandra-run33`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 58 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | filed `80daf71`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-psf/{data,commitlog,hints,saved_caches,cdc_raw,logs}` and `gc.log`, own `conf/`; wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/page_size_fail_threshold-execute-pageSize--autonomous/` (contents below) |

Full-log contents, under that directory:
- `clone-build-run33.log`, `stepE.txt`;
- `shakedown/`, which is not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `error-pagesize-lines.txt`, `commands.log`, `summary.txt`;
- `cluster/`: `node.out`, `system.log`, `gc.log`, `heap.tsv` (4,566 samples), `commands.log`, `summary.txt`, `readings.txt`, `syslog-T<T>-Q<n>-r<r>.txt` per query, `yaml-*`, `jmx.err`, `client.err` (empty);
- `cluster.out`.

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`, since there is no `mkdir` in `$HOME` outside it. Every `ant` call takes `-Dlocal.repository=$W/m2`. Commands touching `$W`, Java or the network run unsandboxed.
- **Node start:** there is no `setsid`, so the node is a tracked background `bin/cassandra -f`.
- **Unit test output:** the forked test JVM writes stdout and the server log to `build/test/logs/**/TEST-<class>.log`, one line per write.
- **Unit yaml:** it enables read thresholds (`test/conf/cassandra.yaml:63-67`), so they were turned off in the probe (amendment B2c).
- **Driver:** the bundled driver is imported from a subfolder of the zip, with `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False` and `idle_heartbeat_interval=0`. Schema metadata is also off. No reconnect was needed: `client.err` is empty.
- **Authentication:** this case is a guardrail. Under `AllowAllAuthenticator` every client is a superuser (`ClientState.java:603-605`), and superusers are exempt (`Guardrail.java:93-96`). The case file already specifies `PasswordAuthenticator` + `CassandraAuthorizer` and a non-superuser role `app`, so no auth amendment was needed. `app`'s `is_superuser=False` was read back. In the unit tier, `GuardrailTester` already enables authentication.
- **Heap instruments:** `jstat` cannot attach, so a JMX poller was used. `nodetool sjk mx` exits 0 on failure, so a JMX client was used. jmxterm and MAT are not available. `GC.heap_info` was not used.
- **Script hygiene:**
  - The daemon pattern in the scripts is split, so their command lines never match.
  - Long steps ran in the background and were polled.
  - Shakedowns ran before run 1.
  - Bounds were derived from source: rows × 2,048 B; the pager's exhaustion rule; `NoSpamLogger`'s interval.
  - The baseline was taken after ingest, flush, restart and an explicit GC.
  - `selfcheck.py` was written before run 1.
- Byteman was not needed.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | `/local` and `/path/to/shared` paths; `bin/cassandra -p` daemonizes and there is no `setsid` | host paths; tracked `bin/cassandra -f` (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3c | No query text; without `WHERE k = 0` the query is a range read (another path than B1's) | `SELECT k, c, v FROM p.wide WHERE k = 0 [LIMIT n]` (amendment B3c) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3d | `jstat` cannot attach on this host; `nodetool sjk mx` exits 0 on failure | JMX client `PsJmx` (heap poll, RowsRead, thresholds) (amendments B3b, B3d) | 2026-10-26, before the freeze | uncommitted |
| A4 | audit | B2b | "set in `@Before`" contradicts B2e's single loop over thresholds | set and read back inside the loop (amendment B2b) | 2026-10-26, before the freeze | uncommitted |

Run 1: none. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `page_size_fail_threshold-execute-pageSize--autonomous/run1/unit/commands.log`,
`page_size_fail_threshold-execute-pageSize--autonomous/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-probe-lines.txt` and `ant-tests-run.txt`.
- Ant: `Tests run: 2, Failures: 0, Errors: 0`.
- Setup line: `readThresholdsEnabled=false userOrdinary=true superOrdinary=false daemonInitialized=true`; `rows=2000`.
- Read-backs: 5/10, 500/1000, −1/−1.
- `PROBE done cases=36`.

The (D) and (L) lines are identical in all 18 pairs.

| Case | fail = 10 (warn 5) | fail = 1000 (warn 500) | fail = −1 |
|---|---|---|---|
| c1 P 3 | rows 3, hasMore true | rows 3, hasMore true | rows 3, hasMore true |
| c2 P 11 | **threw** `GuardrailViolatedException: … page size 11 exceeds fail threshold of 10.` | rows 11, hasMore true | rows 11, hasMore true |
| c3 paging off | rows 2000, hasMore false | rows 2000, hasMore false | rows 2000, hasMore false |
| c4 LIMIT 2000, P 2000 | rows 2000, hasMore false | rows 2000, hasMore false | rows 2000, hasMore false |
| c5 LIMIT 2001, P 2000 | **threw** `… page size 2000 exceeds fail threshold of 10.` | **threw** `… page size 2000 exceeds fail threshold of 1000.` | rows 2000, hasMore true |
| c6 P 11, superuser | rows 11, hasMore true | rows 11, hasMore true | rows 11, hasMore true |

Every non-throwing case has `pageSizeWarnings=0`, and each throwing case has `warnings=1` (its own fail message). There were 6 throws
in 36 cases. The test log has 3 `ERROR … Guardrail page_size violated` lines, one per distinct message (11/10, 2000/10, 2000/1000;
`run1/unit/test-log-error-pagesize-lines.txt`), and 0 WARN lines.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `readings.txt`, `config-lines.txt`, `error-pagesize-lines.txt`, `humongous-after-each-query.txt`.

Setup and validity:
- Read-backs: yaml `page_size_warn_threshold=500`, `page_size_fail_threshold=1000`, `PasswordAuthenticator`, `CassandraAuthorizer`, `read_request_timeout=60000ms`.
- JMX thresholds at the start and end of each phase: 500/1000, 5000/10000, −1/−1.
- `app_is_superuser=False`.
- Load: 100,000 ok, 0 failed, in 8.7 s; 2 sstables, 206,545,996 B live; `count(*)` 100,000.
- 0 other ERROR lines in the query phase. No `java.lang.OutOfMemoryError`.
- Heap baseline after the explicit GC: 59–106 MiB.
- No GC inside any query window. Each window ran from probe start to probe end + 3 s.

Heap Δ is the peak in the window minus the median of the 2 s before it, in MiB at 16 MiB resolution. "Humongous at next GC" is the
number of 16 MiB humongous regions present at the explicit GC after the query.

| T | Query | Client, each of 3 runs | RowsRead Δ | Heap Δ r1, r2, r3 (median) | B3f bound | Humongous at next GC |
|---|---|---|---|---|---|---|
| 1000 | Q1 fetch 500 | ok, 500 rows, has_more True | 500 | 32, 16, 16 (**16**) | < 50 | 0 |
| 1000 | Q2 fetch 2000 | **rejected** `InvalidRequest … Guardrail page_size violated: Aborting query for table wide, page size 2000 exceeds fail threshold of 1000.` | 0 | 32, 16, 16 (**16**) | < 50 | 0 |
| 1000 | Q3 paging off | ok, **100,000 rows**, has_more False | 100,000 | 1168, 1168, 1168 (**1168**) | ≥ 195.3 | 42 |
| 1000 | Q4 fetch 50,000, LIMIT 50,000 | ok, **50,000 rows**, has_more False | 50,000 | 704, 688, 704 (**704**) | ≥ 97.7 | 28 |
| 1000 | Q5 fetch 50,000, LIMIT 50,001 | **rejected** `… page size 50000 exceeds fail threshold of 1000.` | 0 | 32, 32, 16 (32) | — | 0 |
| 10000 | Q1 | ok, 500, True | 500 | 32, 32, 32 (**32**) | < 50 | 0 |
| 10000 | Q2 | ok, 2000, True | 2000 | 16, 16, 48 (**16**) | < 50 | 0 |
| 10000 | Q3 | ok, 100,000, False | 100,000 | 1168, 1152, 1168 (**1168**) | ≥ 195.3 | 42 |
| 10000 | Q4 | ok, 50,000, False | 50,000 | 688, 688, 688 (**688**) | ≥ 97.7 | 28 |
| 10000 | Q5 | **rejected** `… page size 50000 exceeds fail threshold of 10000.` | 0 | 16, 16, 16 (16) | — | 0 |
| −1 | Q1 | ok, 500, True | 500 | 32, 16, 16 (**16**) | < 50 | 0 |
| −1 | Q2 | ok, 2000, True | 2000 | 32, 32, 32 (**32**) | < 50 | 0 |
| −1 | Q3 | ok, 100,000, False | 100,000 | 1152, 1152, 1152 (**1152**) | ≥ 195.3 | 42 |
| −1 | Q4 | ok, 50,000, False | 50,000 | 688, 688, 688 (**688**) | ≥ 97.7 | 28 |
| −1 | Q5 | ok, **50,000 rows, has_more True** | 50,000 | 672, 688, 688 (**688**) | ≥ 97.7 | 28 (r1, r2; r3 is the last window) |

Every accepted query had 0 page-size warnings, in the response and in system.log. The query phase logged exactly 3 `ERROR …
Guardrail page_size violated` lines: 2000/1000, 50000/1000, 50000/10000.

Q3's client-side time was 15–17 s; Q4 and Q5 took 4 s.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/test-log-probe-lines.txt`, `ant-tests-run.txt`]
   - The setup line shows an ordinary user, a superuser that is not ordinary, an initialised daemon, and read thresholds off.
   - 2000 rows; the three read-backs equal the values set; 36 cases; the test passed.
   - The limit was passed at fail 10 and 1000: P = 11 and 2000; responses of 2000 rows.
2. **Readings** — Nothing unusual. Each throwing case carries one `ClientWarn` entry, its own fail message (`Guardrail.java:133`), as amendment B2d said.
3. **Matched row** — B2g row 1, "c2 and c5 throw while c3 and c4 return 2000 rows". [observed]
   - c2 threw at fail 10; c5 threw at 10 and 1000.
   - c3 and c4 returned 2000 rows with `hasMore=false`, no throw and no page-size warning at fail 10, 1000 and −1.
   - Every other cell of amended B2f held, through D and L.
4. **Excluded rows**
   - Row 2 (c3 or c4 throws or warns): no case.
   - Row 3 (c2 not thrown at fail 10): it threw, in D and in L.
   - Row 4 (D and L differ): identical in all 18 pairs.
   - Added Invalid row: setup, rows, read-backs and case count all hold.
   - Added Not-confirmed row: no cell off-prediction. c6 is exempt at every fail value; c5 at −1 is paged with `hasMore=true`.
5. **Observed vs. inferred** — Which branch ran is inferred from (a) and (d), as B2d says: the guard is the only consumer of the
   threshold. c5 at −1 with `hasMore=true` and c4 with `hasMore=false` agree with the predicate at `:338`/`:602`.
6. **Deviations and gaps** — None in the run. The unit tier counts rows, not heap bytes (named in amendment B2d).
7. **Core question** — On the paged branch the knob decides what is returned: P ≤ fail is served, P > fail is refused before any
   row is read. A query with paging off, or with LIMIT ≤ P, is never checked. It returned all 2000 rows in one response at fail = 10,
   200× the threshold.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect (amended B2g): **caps only on some paths (bypass)**.

**Cluster tier**

1. **Validity** — Valid. [observed: `cluster/config-lines.txt`, `summary.txt`, `error-warn-other.txt`; heap sampler coverage from
   self-check C7]
   - Read-backs at every phase, superuser check, load and count.
   - No node failure, no other ERROR line.
   - At least 19 pre-window samples per query, at about 9–10 samples per second.
   - T = 1000 rows was passed by 50× (Q4) and 100× (Q3).
2. **Readings** — Points worth noting:
   - No GC fell inside any query window. Each heap Δ is therefore everything the query allocated before the next explicit GC,
     live plus transient, not only what it kept. [observed: `readings.txt` `gcs=0`]
   - Q3's Δ (1,152–1,168 MiB) is 5.9–6.0× its value bytes; Q4's (688–704 MiB) is 7.0–7.2×.
   - One small-query repetition read 48 MiB (T 10000, Q2 r3), at the 16 MiB resolution. Its median is 16.
3. **Matched row** — B3g row 1, "Q2 and Q5 rejected; Q3 and Q4 succeed with large single responses and heap ≥ response size".
   [observed]
   - Q2 and Q5 rejected 3/3 at T = 1000, with the server's guardrail message and RowsRead Δ 0.
   - Q3 returned 100,000 rows in one page (`has_more False`, RowsRead Δ 100,000), heap median 1,168 MiB ≥ 195.3 MiB.
   - Q4 returned 50,000 rows, 704 MiB ≥ 97.7 MiB.
   - The T = 10000 and T = −1 columns hold as amended. In particular, Q2 is accepted at 10000; Q5 is rejected at 10000 and accepted
     at −1 with a 50,000-row page and 688 MiB.
4. **Excluded rows**
   - Row 2 (Q3 or Q4 rejected or truncated to ≤ T): 100,000 and 50,000 rows at every T.
   - Row 3 (Q2 not rejected): rejected 3/3.
   - Row 4 (Q3 < 50 MiB): 1,152–1,168 MiB.
   - Added rows: heap between the bounds (no); OOM (none); off-prediction cells (none); Invalid (all validity checks hold).
5. **Observed vs. inferred** — Two statements are inferred.
   - That the heap Δ of Q3/Q4 belongs to building and serialising the single response, [inferred: no other activity in the window
     (no compaction line, no other ERROR, the same query at three T gives the same Δ), and the source builds the whole local response
     in one heap buffer (`ReadResponse.java:197-203`)].
   - That the humongous regions present after Q3 (42 × 16 MiB) and Q4 (28) are those buffers, [inferred: objects ≥ 8 MiB; none
     after any small or rejected query].
   - The verdict rests on the observed bounds, rows and rejections, not on these two.
6. **Deviations and gaps** — None in the run.
   - The heap Δ measures allocation within the window, not retained heap. No GC fell inside a window, so the live part of a response
     is not separated from transient copies. The B3f bound ("at least the response size") is a lower bound and holds either way.
   - The per-response byte size on the server is not observed directly (B3d).
7. **Core question** — Coordinator heap does not follow T on the branches selected by `:338#1` (paging off) and `:338#2` (LIMIT ≤ page
   size):
   - The same Q3 allocates about 1.16 GiB at T = 1000, 10000 and −1; Q4 allocates 0.69 GiB.
   - Both stay far above what a 1000-row page would allow; a 1000-row page is about 2 MB of values.
   - On the paged branch the cap binds and the heap follows it: the 50,000-row page costs 688 MiB when allowed (T = −1) and 16–32 MiB
     when refused (T = 1000, 10000).

**Cluster tier conclusion:** B3g row 1 — **confirmed**. Effect (amended B3g): **caps only on some paths (bypass)**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, sha256 in `run1/freeze.txt`) re-reads the raw files and re-derives every amended B2f
and B3f condition:
- `unit/TEST.log` (the `PROBE` lines and the ERROR lines) and `unit/ant.log`;
- the cluster's `summary.txt`: every logged reading line;
- `heap.tsv`: it recomputes each baseline median and peak from the raw samples with its own code;
- the full `system.log`, sliced at the logged query-phase byte offset: it recounts the guardrail ERROR and WARN lines and their
  (P, T).

Output `run1/selfcheck.out`: **38 checks, 38 pass, 0 fail**:
- U0–U9: 15 unit checks;
- C0–C7: 8 cluster validity and evidence checks;
- C8: 15 cluster cells.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U4 and C1–C4, C7 pass; `config-lines.txt` and the `THRESHOLDS`/`PHASE-END` lines re-read |
| 2. Readings | yes | `readings.txt` re-read: `gcs=0` in all 45 windows; the 48 MiB repetition is T10000-Q2-r3 |
| 3. Matched row | yes | U5 (6 checks) and the 15 C8 cells pass; the rejection texts in `summary.txt` name the table, P and T |
| 4. Excluded rows | yes | No over-T truncation, no rejection of Q3/Q4, no Q3 Δ below 50 MiB, no OOM line |
| 5. Observed vs. inferred | yes | The two inferred statements are not used by the verdict; `humongous-after-each-query.txt` re-derived from `gc.log` |
| 6. Deviations and gaps | yes | Defects A1–A4 fixed before the freeze; the shakedown fixes touched only the harness and amendment B3h (no bound); no run-1 defect |
| 7. Core question | yes | The rejection boundary follows the knob at three values in both tiers, with direct disallow evidence (exception text, RowsRead Δ 0, ERROR line). The unpaged branches return the full result at every T, and their heap stays the same across T. |

### 5.2 Run 2?

**No** — 2026-10-26.
- Every verdict statement is observed.
- The self-check settles every part from run 1's files.
- The bypass confirmed is the design's own claim (B1), read directly in both tiers.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined. The expected partial result: capped on the paged branch, not capped on the branches these checks
select.

**Claim tested (B1):** for an ordinary user with `page_size_fail_threshold = T`:
- a paged SELECT with fetch size > T is rejected;
- one with fetch size ≤ T returns at most fetch-size rows per response;
- a SELECT with paging off, or with LIMIT L ≤ fetch size, is not checked against T, returns all its rows (up to L) in one response,
  and the coordinator heap grows with that response size, not with T.

"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | **caps only on some paths (bypass)** (row 1 below) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1) | **caps only on some paths (bypass)** (row 2 below) | run 1 + self-check | 2026-10-26 |

1. **Unit:** P > fail is rejected at fail 10 and 1000 through `:338` and `:602`. Paging off and `LIMIT 2000` with P = 2000 return
   2000 rows at fail 10.
2. **Cluster:**
   - Q2 and Q5 are rejected at T = 1000.
   - At every T, Q3 returns 100,000 rows in one response (heap Δ 1,152–1,168 MiB) and Q4 returns 50,000 (688–704 MiB).
   - The paged 50,000-row page costs 688 MiB only when T allows it.

**Positive control:** not required, since this is not a negative-estimate file. The paged-branch cells moved usage as required:
- Q2 rejected at 1000 and served at 10000 and −1;
- Q5 rejected at 1000 and 10000, and served at −1 with a 50,000-row page and 688 MiB;
- unit c2 rejected at 10 and served at 1000 and −1.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a–B2h, B3a–B3h and B4 are in the case file (uncommitted).
- `_INDEX-advisor.md`: §2 row `42872914…2854` added, and the §1 Stage 4 column filled.
- `HANDOFF.md` not edited (`HANDOFF-ADVISOR.md` §8).
