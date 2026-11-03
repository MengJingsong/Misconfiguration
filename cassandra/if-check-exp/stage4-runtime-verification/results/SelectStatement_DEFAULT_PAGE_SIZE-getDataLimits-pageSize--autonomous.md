# SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous — stage-4 results  <!-- file: results/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.md -->

> **Case:** [`SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous`](../../stage3-ai-deep-read/cases/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/`](../harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/).
>
> **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1).
> - All 8 cells were in their bands, and each read count equals the count derived from source, ⌊N/R⌋ + 1.
> - GROUP BY with paging off carries `LIMIT 10000` and takes 3 reads at N = 25,000 and 6 at N = 50,000. With P = 1000 it takes
>   26 and 51 reads; with P = 50000, 1 and 2.
> - The aggregate without GROUP BY takes 1 read at both N.
>
> **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1). One node, 100,000 rows of 4 KiB in one partition.
> - With paging off, the GROUP BY makes 11 reads. Each read builds a response of at most 41,130,020 B (10,000 rows); 10 of the
>   responses are full and the last is empty.
> - With paging off, the aggregate makes 1 read whose response is 411,281,225 B (100,000 rows), in a 513,589,248-byte heap array.
> - Bytes per read follow the row limit in force: 4.11 MB at 1,000 rows, 41.1 MB at 10,000 (the constant), 205.7 MB at 50,000, and
>   411 MB when there is no limit.
> - Heap left after a GC inside the query window (H_live): Qg-1000 4–7 MiB; Qg-off 129, 132 and **528** MiB; Qg-50000 648–673 MiB;
>   Qa-off 864 MiB. The single 528 MiB reading is reported in §4.2; under the frozen B3g heap row (2 of 3 needed) it does not change
>   the row.
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
| **Case-file version** | Filed in commit `80daf71` (sha256 `528d625a…e761`). Frozen after the step-0 audit's fifteen amendments (2026-10-26, before any run-1 reading) at sha256 **`7393d4f3f235ebd782ac19f0e6f4cecb2133c4d5548947cc59a1667fa9c53317`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX-advisor.md` §2. `run1/freeze.txt` holds this hash, the harness hashes and the self-check hash. Nothing was committed, because no commit was asked for. |
| **Harness** | [`../harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/`](../harness/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM. N ∈ {25,000, 50,000} rows of 16 B in 50 groups. Cells (Qg, P = −1 → R = 10000), (Qg, 1000), (Qg, 50000) and (Qa, −1). **Cluster (B3):** one node, heap 2G, G1. N = 100,000 rows of 4,096 B in one partition, 50 groups. Runs Qg-off (R = 10000, the constant), Qg-1000, Qg-50000 and Qa-off, three times each. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `GroupByInternalPagingProbeTest.java` (B2c as amended) and `unit-run.sh`.
- `rules.btm`: two Byteman rules that only print.
  - `BM-RESP` prints the table, the serialized bytes and the capacity of the heap array of each local read's response.
  - `BM-PAGE` prints the rows, groups and limits of each page or sub-page.
- `DpJmx.java`: a JMX client. It reads the per-table coordinator and local read counts and the global read count, triggers GC,
  and polls the heap every 100 ms.
- `probe.py`: a client on the bundled driver, for setup, load, count and the queries.
- `cluster-run.sh`: two node lifetimes (load, then a restart for the queries), with the agent loaded in both.
- `summarize.py`: builds the readings table.

**Note 2, instrument checks before the freeze:**
- **Byteman:** `TestScript` type-checks both rules with no errors.
- **Unit shakedown:** N = 2,500 (`shakedown/unit-n2500-summary.txt`). This N cannot reach the 10,000 boundary.
- **Cluster shakedown 1:** 20,000 rows (`shakedown/cluster1-rows20000-query-lines.txt`). It found two instrument problems, both
  fixed before the freeze, and nothing in the case file's predictions:
  - The global `ClientRequest` read count includes the driver's own system-table reads on each new connection (Δ 5 against 3
    local reads). Fix: per-table counters (amendment B3d item 1).
  - The trace included batchlog and system-table reads. Fix: a `table=` field in both rules.
  - Script false positives in the "agent errors" and OOM counters (JVM-argument and CompileCommand lines). Fix: the patterns.
- **Cluster shakedown 2:** 20,000 rows, after the fixes (`shakedown/cluster2-*`).
- **Harness fix after the unit tier, before any cluster reading:** `cluster-run.sh` stopped at its first line. Bash's
  read-only `GROUPS` variable killed the assignment line before the node was started. The variable was renamed `NGROUPS`; nothing
  else changed. The new hash is in `run1/freeze.txt`.

**Note 3, self-check:** [`run1/selfcheck.py`](SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/run1/selfcheck.py)
was written before run 1. On the two shakedowns (`SHAKEDOWN=1`) it scores 22/22 (`shakedown/selfcheck-on-shakedown.out`). It does not
use `summarize.py` or the per-query `bm-*.txt` slices. Instead it re-slices `node.out` by each trace line's own timestamp.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly → Met after amendment | A2/B1: rows per internal read, and so the bytes each read materializes. As filed, the unit tier counts reads only (gap named, B2d). In the cluster tier, the heap Δ as filed could not see per-read memory (see "real resource" below). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met after amendment | The constant cannot be set (A1). The client page size P replaces it, and the filed design compares a capped arm (GROUP BY) with an uncapped arm (aggregate without GROUP BY). The unit tier already has three row limits (10000, 1000, 50000). The cluster tier had two; fetch 50000 was added (amendment B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Not met → Met after amendment | The filed heap Δ is the peak minus the baseline, with no GC in the window. It counts every byte allocated since the baseline: for Qg-off, all ten sub-page buffers (`ReadResponse.java:197-203`, a new buffer per read). So it would read about N × row size for both arms, a false "does not cap". Amendment B3d adds the size of each read's heap response buffer (Byteman `BM-RESP`) as the primary observable, and H_live (heap after a GC inside the window). H_alloc is kept as reported only. |
| A. Core question | usage driven to the limit and past it | Met | N = 100,000 = 10 × 10000 in the cluster tier; N = 25,000 and 50,000 in the unit tier. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈ 25", "≈ 100", "—" and loose heap bounds. Made exact: read-count bands ⌈N/R⌉..⌈N/R⌉ + 1 with the derived ⌊N/R⌋ + 1 (`DataLimits.java:806-808`), byte bounds per response, and H_live bounds (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Added: Invalid (load, agent, JMX, errors), Not confirmed (control off band, heap not bounded), OOM during Qa-off (row 1b), verdict words, Effect rule (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Direct evidence that the constant stopped a read: `BM-PAGE rows=10000 limits=[LIMIT 10000]` on every full sub-page, the limits string in the unit tier, and a response size that follows R at three values (amendments B3b, B3d). |
| B. Logic | alternative explanations and their controls | Met | Flush and restart (memtables), RF = 1, P = 1000 and 50000 as row-limit controls. Amendment B3h adds an explicit GC before each baseline. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Probe output format, `requireNetwork()`, read thresholds, the client commands and log locations were added (amendments B2c–B2e, B3c, B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Heap definitions, per-query procedure and order (Qa last) (amendments B3d, B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | The filed design assumes a Linux node, `ant jar` (no test classes), `bin/cassandra -p`, `jstat` and `nodetool sjk mx`, and the unit yaml's read thresholds. All were fixed before the freeze (amendments B2a, B2c, B3a, B3d, B4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly → Met after amendment | 400 MiB of data against 134 GiB free. The largest response buffer is 432–486 MiB, and two arrays are live while it grows, against a 2 GiB heap. A local read's deadline is min(start + 5 s, enqueue + 12 s) (`Dispatcher.java:238-245`, `StorageProxy.java:2204-2205`), and one request time covers every sub-page (`AggregationQueryPager.java:163`, `:297`). So both timeouts were raised to 60 s (amendment B3a). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: see Note 4 below the recommendations. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and `build-test`; harness location | Amendment 2026-10-26 | `ant jar` builds no test classes; no Linux node here |
| 2 | B2c: `requireNetwork()`, read thresholds off, row values, `max(blob)` check | Amendment 2026-10-26 | Unit yaml thresholds (`test/conf/cassandra.yaml:63-67`) are another consumer (A4) |
| 3 | B2d: output format | Amendment 2026-10-26 | Group C |
| 4 | B2e: `unit-run.sh` | Amendment 2026-10-26 | Clean clone |
| 5 | B2f: exact bands and derived counts | Amendment 2026-10-26 | Group B |
| 6 | B2g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B |
| 7 | B3a: host paths, tracked node, timeouts 60 s, agent scope | Amendment 2026-10-26 | No `setsid`; timeouts from source |
| 8 | B3b: third row limit (fetch 50000) | Amendment 2026-10-26 | Group A |
| 9 | B3c: probe commands | Amendment 2026-10-26 | Group C |
| 10 | B3d: per-table JMX counters, Byteman M1/M2, H_alloc vs H_live | Amendment 2026-10-26 | `jstat`/`sjk`; the filed heap Δ counts allocation (group A) |
| 11 | B3e: one script, order | Amendment 2026-10-26 | Group C |
| 12 | B3f: exact table | Amendment 2026-10-26 | Group B |
| 13 | B3g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B |
| 14 | B3h: explicit GC before each baseline | Amendment 2026-10-26 | Baseline drift on this host |
| 15 | B4: host paths and checks | Amendment 2026-10-26 | Paths |
| 16 | Observe bytes per read in the unit tier too (the same Byteman rules under `BMUnitRunner`). Cover DISTINCT and the multi-partition range path. Find out what holds heap at a GC inside a GROUP BY window (a class histogram at a held point), because one Qg-off repetition left 528 MiB (§4.2). | Left for stage 3 | Not needed for B1's claim; the last item follows a run-1 reading |

**Note 4, citations checked:**
- `SelectStatement.java:114, 280-361, 368-379, 505-552, 574-633, 881-921`;
- `AggregationQueryPager.java:33-63, 163, 180-299, 401-443`;
- `AbstractQueryPager.java:47-93, 139-238`; `SinglePartitionPager.java:59-94`;
- `DataLimits.java:110-142, 547-561, 640-808, 986`;
- `ReadResponse.java:46-53, 181-205, 224-236`; `ReadCommand.java:374`;
- `StorageProxy.java:2040-2060, 2178-2212`; `SinglePartitionReadCommand.java:482-485`; `TableMetrics.java:115, 628`;
- `Dispatcher.java:160-250`; `Config.java:144-145, 1384-1399`;
- `DataOutputBuffer.java:48, 57, 94, 118-182`; `CassandraRelevantProperties.java:203`;
- `AggregateFcts.java:65-71, 845-847`; `QueryProcessor.java:372-375`; `QueryOptions.java:82-92`;
- `test/conf/cassandra.yaml:63-67`; `conf/cassandra.yaml:1322, 2017-2026`; `conf/jvm11-server.options:63-79`; `conf/jvm-server.options:120`.

All hold. The filed A3 citations hold as well.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 15:29–15:30 EDT; cluster 15:32–15:36 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 134 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present; one node on 127.0.0.1. Ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the `ant testsome` forked JVM. Node: `-Xms2G -Xmx2G`, G1 with 16 MiB regions (`HEAP_NEWSIZE=400M` set as filed and ignored under G1), and the Byteman 4.0.20 agent (`script:` only, no listener) |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip` (subfolder import), protocol 5 |
| Local `cassandra-src` clone | `$W/cassandra-run35` = `~/Library/Caches/stage4/cassandra-run35`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 55 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | filed `80daf71`; amendments, harness and results uncommitted (sha256 in §1 and `run1/freeze.txt`) |
| Storage for node data | local SSD under `$W/node-dps/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, plus `gc.log` and its own `conf/`; wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/` |

Full-log contents, under that directory:
- `clone-build-run35.log`, `stepE.txt`, `unit-run.out`, `cluster.out`;
- `shakedown/`, which is not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `commands.log`, `summary.txt`;
- `cluster/`:
  - `node.out` (the Byteman lines), `system.log`, `gc.log`, `heap.tsv` (846 samples);
  - `commands.log`, `summary.txt`, `readings.txt`;
  - `bm-<run>-r<n>.txt` and `syslog-<run>-r<n>.txt` for each query;
  - `yaml-*`, and `jmx.err` and `client.err` (both empty).

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`, since there is no `mkdir` in `$HOME` outside it. Every `ant` call takes `-Dlocal.repository=$W/m2`. Commands touching `$W`, Java or the network ran unsandboxed.
- **Node start:** there is no `setsid`, so the node is a tracked background `bin/cassandra -f`. `JVM_EXTRA_OPTS` (the Byteman agent) is scoped to that command only.
- **Unit tests:**
  - Test stdout lands in `build/test/logs/**/TEST-<class>.log`.
  - `CQLTester` needs `requireNetwork()`.
  - `parseStatement(String, ClientState)` already returns the prepared statement.
  - The unit yaml enables read thresholds, so they were turned off.
- **Driver:** the bundled driver is imported from a zip subfolder, with `DCAwareRoundRobinPolicy`, token and schema metadata off and heartbeat off; no reconnect was needed (`client.err` empty).
- **Authentication:** no guardrail is on this path. The constant is read unconditionally at `SelectStatement.java:901`. `Guardrails.pageSize` checks the page size, not this constant, and exempts superusers. So the default `AllowAllAuthenticator` was kept.
- **Heap instruments:**
  - `jstat` cannot attach and `nodetool sjk mx` exits 0 on failure, so a JMX client was used. jmxterm and MAT are not available.
  - `GC.heap_info` was not used; heap after GC was read from `gc.log`.
  - A heap Δ with no GC in the window counts allocation, not retention. This lesson drove amendment B3d.
- **Constants and Byteman:** the constant is not varied by patching. P replaces it, as the filed design says. The Byteman rules only observe, and `TestScript` type-checked them.
- **Script hygiene:** the daemon pattern in the scripts is split; long steps ran in the background and were polled; shakedowns ran before run 1; bounds were derived from source; baselines were taken after ingest, flush, restart and an explicit GC; `selfcheck.py` was written before run 1.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | `ant jar` builds no test classes. `$WORK` and a Linux node are assumed. `bin/cassandra -p` daemonizes, and this host has no `setsid`. | `build-test`, host paths, a tracked `bin/cassandra -f` (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3d | `jstat` cannot attach on this host; `nodetool sjk mx` exits 0 on failure | JMX client `DpJmx` (amendment B3d) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3d/B3f | The filed heap Δ (peak minus baseline, with no GC in the window) counts allocation summed over all sub-pages, so it cannot carry the per-read bound B1 states | M1 (Byteman response bytes) as the primary observable, H_live for heap retention, H_alloc reported (amendments B3d, B3f) | 2026-10-26, before the freeze; a §9a change, made in the audit for a reason that depends on no reading | uncommitted |
| A4 | audit | B3a | At the default timeouts a 400 MiB single read, or a long run of sub-pages, can exceed the read deadline (source in §1.1 D), and a timeout has no B3g row | `read_request_timeout` 60000ms, `native_transport_timeout` 60s | 2026-10-26, before the freeze | uncommitted |
| H1 | run 1 | B3e (harness) | `cluster-run.sh` stopped at its first line (bash's read-only `GROUPS` variable); no node started, no reading | variable renamed `NGROUPS`; the case file is unchanged | 2026-10-26 | none (harness only; `run1/freeze.txt`) |

Run 1: no case-file defect. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:**
`SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/run1/unit/commands.log` and
`SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-probe-lines.txt` and `ant-tests-run.txt`.
- Ant: `Tests run: 1, Failures: 0, Errors: 0`.
- Setup line: `readThresholdsEnabled=false DEFAULT_PAGE_SIZE=10000 daemonInitialized=true`.
- Loads: 25,000 and 50,000 rows read back; `PROBE done cells=8`.

| N | Query | P | limits | reads (= localReads) | band | derived ⌊N/R⌋+1 | groups | hasMore |
|---|---|---|---|---|---|---|---|---|
| 25,000 | Qg | −1 | `LIMIT 10000` | **3** | {3, 4} | 3 | 50 | false |
| 25,000 | Qg | 1000 | `LIMIT 1000` | 26 | {25, 26} | 26 | 50 | false |
| 25,000 | Qg | 50000 | `LIMIT 50000` | 1 | {1, 2} | 1 | 50 | false |
| 25,000 | Qa | −1 | (empty) | **1** | {1} | — | 1 | false |
| 50,000 | Qg | −1 | `LIMIT 10000` | **6** | {5, 6} | 6 | 50 | false |
| 50,000 | Qg | 1000 | `LIMIT 1000` | 51 | {50, 51} | 51 | 50 | false |
| 50,000 | Qg | 50000 | `LIMIT 50000` | 2 | {1, 2} | 2 | 50 | false |
| 50,000 | Qa | −1 | (empty) | **1** | {1} | — | 1 | false |

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `readings.txt`, `bm-g.t-lines.txt`, `gc-pauses-and-regions-query-phase.txt`.

Setup and validity:
- Read-backs, at both starts: `read_request_timeout=60000ms`, `native_transport_timeout=60s`, `read_thresholds_enabled=false`, size
  thresholds `null`. JVM: `-Xms2G -Xmx2G`, G1 with 16 MiB regions, the gc log, and the Byteman agent with `rules.btm`.
- Load: 100,000 ok and 0 failed, in 10.5 s. 4 sstables, 411,861,611 B live, compression off; `count` 100,000.
- No query error. No ERROR line in the query phase; the 7 WARN lines are start-up notices. No `java.lang.OutOfMemoryError`. The
  node was alive at the end.
- At least 19 pre-window heap samples per query. Baseline after the explicit GC: 56–59 MiB.

The reads are the per-table counters, and the coordinator count equals the local count in every query. The global `ClientRequest`
count was 2 higher each time: the driver's own reads. The M1 numbers are serialized bytes in `g.t` responses. H_alloc and H_live
are as defined in amendment B3d.

| Run (R) | Client, each of 3 | Reads r1/r2/r3 | M1: responses, max, full ones | M2 rows per page | H_alloc MiB r1/r2/r3 | H_live MiB r1/r2/r3 (GC in window) |
|---|---|---|---|---|---|---|
| Qg-off (10000) | ok, 50 rows, 1 page | **11 / 11 / 11** | 11; max **41,130,020** B (capacity 67,682,304); 10 ≥ 40,960,000 B, the 11th 2 B | 10000 ×10, then 0; limits `LIMIT 10000` | 1648 / 1360 / 1360 | 132 / 129 / **528** (one Young pause each) |
| Qg-1000 (1000) | ok, 50 rows, 1 page | 101 / 101 / 101 | 101; max 4,113,020 B (cap 4,230,144); 100 full | 1000 ×100, then 0 | 752 / 960 / 672 | 6 / 4 / 7 (one Young pause each) |
| Qg-50000 (50000) | ok, 50 rows, 1 page | 3 / 3 / 3 | 3; max 205,650,020 B (cap 228,427,776); 2 full | 50000, 50000, 0 | 1488 / 1056 / 864 | 673 / 648 / 648 (Young 443M after, then Remark and Cleanup) |
| Qa-off (none) | ok, 1 row | **1 / 1 / 1** | 1; **411,281,225** B (capacity **513,589,248**) | 100000 (one page, limits empty) | 1312 / 1312 / 1312 | 864 / 864 / 864 (Young 395M after, then Remark 892M and Cleanup) |

The trace was identical in all three repetitions: the same byte counts and the same rows per page.

Detail of the Qg-off GCs, from `gc-pauses-and-regions-query-phase.txt`:
- r1: GC(7), a Young pause on a humongous allocation: 1876M → 188M; humongous regions 72 → 8; old 10 → 10.
- r2: GC(9), a Young pause on a humongous allocation: 1869M → 186M; humongous 72 → 8; old 10 → 10.
- r3: GC(11), a Young evacuation pause: 1945M → 585M; humongous 77 → 5; survivor 0 → 0; **old 10 → 38**.

Elapsed time on the client: 0.2–0.5 s for every query.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/test-log-probe-lines.txt`, `ant-tests-run.txt`]
   - Read thresholds were off, the loads read back 25,000 and 50,000, 8 cells printed, and the test passed.
   - The limit was passed: N = 2.5 and 5 times R = 10000.
2. **Readings** — Nothing unusual. Every read count equals the derived ⌊N/R⌋ + 1, the low or high edge of its band as source
   predicts. `localReads` equals `reads` in every cell. [observed]
3. **Matched row** — B2g row 1: "Qg with P=-1 reads scale as N/10000 while Qa stays at 1". [observed]
   - Qg with P = −1 carries `LIMIT 10000` and takes 3 → 6 reads as N doubles.
   - Qa takes 1 read at both N.
   - P = 1000 and P = 50000 move the count to 26/51 and 1/2.
4. **Excluded rows**
   - Row 2 (1 read at 50k): 6 reads.
   - Row 3 (Qa > 1 read): 1 at both N.
   - Row 4 (limits not `LIMIT 10000`): it is `LIMIT 10000`.
   - Invalid: every validity check holds.
   - Not confirmed: no cell is outside its band.
5. **Observed vs. inferred** — Rows per read are inferred as N / reads, as B2d says. With 50 groups and in-order rows, ⌊N/R⌋ full reads
   and one empty read is the only split consistent with both the counts and the `LIMIT` string. The cluster tier observes the rows
   directly.
6. **Deviations and gaps** — None in the run. The unit tier counts reads, not bytes (named in B2d).
7. **Core question** — With paging off, the constant sets the row limit of every internal GROUP BY read. The number of reads follows
   N / 10000. When P replaces the constant, it follows N / P. The aggregate without GROUP BY ignores the constant and reads
   everything in one read.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect (amended B2g): **caps only on some paths (bypass)**.

**Cluster tier**

1. **Validity** — Valid. [observed: `cluster/summary.txt`; self-check C00–C4, C7, C8]
   - Read-backs at both starts, the load and the count are as required.
   - The agent loaded: 738 `g.t` trace lines, and no agent error.
   - No query failed and no OOM occurred.
   - The constant's limit was passed tenfold (N = 100,000 against R = 10000).
2. **Readings** — Points worth noting:
   - H_alloc is 1.3–1.6 GiB for Qg-off, about the same as Qa-off's 1.3 GiB. This is the allocation-summing effect that amendment B3d
     predicted from source. It is why H_alloc carries no bound. [observed: `readings.txt`]
   - **One Qg-off repetition left 528 MiB after its in-window GC (r3), against 129–132 MiB in r1 and r2.** [observed:
     `gc-pauses-and-regions-query-phase.txt`]
     - That GC was a Young evacuation pause, not a humongous-allocation pause. It promoted 28 old regions (about 448 MiB), and the
       survivor space stayed at 0 regions.
     - Humongous regions fell from 77 to 5. Five 16 MiB regions are one 67.7 MB sub-page buffer.
     - So what remained was not sub-page buffers but promoted ordinary objects. What they were is not observable from run 1: there is
       no class histogram. [inferred: from the region counts]
   - H_live for Qg-50000 and Qa-off includes Remark and Cleanup pauses, as the frozen definition allows. These pauses report occupancy
     without evacuating. With Young pauses only, H_live would be about 385 MiB for Qg-50000 and about 337 MiB for Qa-off. Neither run
     feeds the verdict through H_live. [observed: `readings.txt`]
3. **Matched row** — B3g row 1. [observed: `readings.txt`, `bm-g.t-lines.txt`]
   - In all 3 repetitions, Qg-off makes 11 reads, in the band {10, 11}.
   - Every Qg-off response is ≤ 41,130,020 B, against the bound of 43,008,000 B, and 10 are ≥ 40,960,000 B. Each full sub-page stopped
     at `rows=10000` under `limits=[LIMIT 10000]`.
   - Qa-off makes 1 read, with a single 411,281,225 B response (≥ 409,600,000 B).
   - Controls: Qg-1000 makes 101 reads with responses ≤ 4,113,020 B, and H_live 4–7 MiB (≤ 50). Qg-50000 makes 3 reads with responses
     ≤ 205,650,020 B (≤ 215,040,000), 2 of them full.
4. **Excluded rows**
   - Row 2 (Qg-off 1 read, or a response > 43,008,000 B): 11 reads, max 41.13 MB.
   - Row 3 (Qa-off split): 1 read.
   - Row 4 (Qa response < 409,600,000 B): 411,281,225 B.
   - Heap row (Qg-off H_live > 150 MiB in at least 2 of 3): only 1 of 3 (r3, 528 MiB). The row does not fire.
   - Invalid: every validity check holds.
   - Control row: both controls are in their cells.
5. **Observed vs. inferred**
   - Inferred: that the `BM-RESP` buffer is the dominant heap a read holds. It is the only array of that size per read (one per local
     read, `ReadResponse.java:197-203`), and the humongous regions left after the in-window GCs agree in size: 8 after r1 and r2, 5 after r3, where one 67.7 MB buffer takes 5.
   - Inferred: that the r3 retention came from promoted ordinary objects, not from buffers (point 2).
   - The verdict rests on the observed reads, response sizes and rows per page.
6. **Deviations and gaps**
   - **The B3f cell "Qg-off H_live ≤ 150 MiB" did not hold in r3 (528 MiB).** Amended B3f says each cell must hold in each
     repetition, and this cell did not hold once. The frozen B3g decides what that means: its heap row asks for 2 of 3 before the
     verdict becomes Not confirmed, so the row stays 1. The reading is not explained by run 1's evidence. It is recorded here and in
     section D, and a follow-up is recommended (§1.1 recommendation 16).
   - H_alloc measures allocation, not retention, as stated before the run.
   - The capacity of the response array is 1.03–1.65 × its serialized bytes, from `DataOutputBuffer`'s growth rule. M1's bounds are
     on serialized bytes, as amended.
7. **Core question** — Per-read memory follows the row limit, and with paging off that limit is the constant:
   - With paging off, each internal GROUP BY read materializes at most 10,000 rows (41.1 MB here), whatever N is: 11 reads for
     100,000 rows.
   - The same scan as an aggregate without GROUP BY materializes all 100,000 rows in one 411 MB response, in a 514 MB heap array.
   - Response size per read follows the row limit at 1,000, 10,000 and 50,000 rows (4.1, 41.1 and 205.7 MB).
   - H_live follows it in shape (about 5, 130 and 650 MiB), apart from the one 528 MiB Qg-off repetition.
   - So the constant caps per-read memory for GROUP BY with paging off, and not for the aggregate path.

**Cluster tier conclusion:** B3g row 1 — **confirmed**. Effect (amended B3g): **caps only on some paths (bypass)**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1; sha256 in `run1/freeze.txt`) re-reads the raw files with its own parsers:
- `unit/ant.log` and the `PROBE` lines of `unit/TEST.log`;
- from `cluster/summary.txt`: the RUN, READBACK, JVMARGS, LOAD, COUNT and QUERY lines (windows, client results, JMX counters);
- `cluster/node.out`: every `BM-` line, re-sliced by its own timestamp into each query window, not through the harness's `bm-*.txt`;
- `heap.tsv` (pre-window samples), `gc.log` (pauses in each window, explicit GC before it) and `system.log`.

Output `run1/selfcheck.out`: **34 checks, 34 pass, 0 fail**. It names `UNIT-ROW row 1 Confirmed` and `CLUSTER-ROW row 1 Confirmed`.
- U0–U5: 13 unit checks, including the 8 cells.
- C00–C9: 21 cluster checks, including 12 query cells.

C9 applies the frozen B3g heap row (2 of 3), so it passes with Qg-off H_live = [132, 129, 528]. The per-repetition B3f cell for r3
is the deviation recorded in §4.2 part 6.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U3, C00–C4, C7 and C8 pass; `summary.txt` read-backs and `error-warn-all.txt` (7 start-up WARN lines) re-read |
| 2. Readings | yes | `gc-pauses-and-regions-query-phase.txt` re-read: GC(11) old 10 → 38, humongous 77 → 5, survivor 0 → 0; GC(7) and GC(9) old 10 → 10, humongous 72 → 8. The H_alloc values match `readings.txt`. |
| 3. Matched row | yes | All 12 C6 cells pass. `bm-g.t-lines.txt` shows `rows=10000 … limits=[LIMIT 10000]` for the first Qg-off sub-page and `GROUP LIMIT … LIMIT 10000` for the later ones. |
| 4. Excluded rows | yes | Max Qg-off response is 41,130,020 B; Qa-off has a single read; the heap row counts 1 of 3 |
| 5. Observed vs. inferred | yes | The two inferred statements are not used by the verdict. The r3 explanation is marked as inferred and left open. |
| 6. Deviations and gaps | yes | The r3 cell miss is recorded with its consequence under B3g. Defects A1–A4 were fixed before the freeze; H1 touched only the harness, before any cluster reading. |
| 7. Core question | yes | Bytes per read follow R at three values. With paging off the constant is R, and the trace shows the counter stop at 10,000 rows. The uncapped arm materializes N rows in one read in both tiers. |

### 5.2 Run 2?

**No** — 2026-10-26.
- The verdict rests on observed values: read counts, trace bytes and rows per page. These were identical in three repetitions, and the
  self-check settles them from run 1's files.
- The bypass confirmed is the design's own claim (B1).
- The one open reading (Qg-off r3 H_live) is a heap-retention question that a by-hand repeat of the same runbook would not answer:
  that runbook has no class histogram. It is left to stage 3 as recommendation 16.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped to GROUP BY).

**Claim tested (B1):**
- A GROUP BY query run with paging off issues about ceil(N / 10000) internal reads for N scanned rows. Its peak per-read memory is
  bounded by about 10000 rows × row size, not by N.
- The same scan as an aggregate without GROUP BY, also with paging off, is not split: one read, with memory that grows with N.

"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | **caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1) | **caps only on some paths (bypass)** | run 1 + self-check | 2026-10-26 |

1. **Unit:**
   - With paging off, GROUP BY carries `LIMIT 10000` and takes 3 and 6 reads at N = 25,000 and 50,000.
   - The aggregate takes 1 read.
   - P = 1000 and P = 50000 move the counts to 26/51 and 1/2.
2. **Cluster:**
   - With paging off, GROUP BY takes 11 reads of at most 10,000 rows. Each response is at most 41.1 MB.
   - The aggregate takes 1 read of 100,000 rows, a 411 MB response in a 514 MB heap array.
   - Response bytes follow the row limit at 1,000, 10,000 and 50,000 rows.
   - The single Qg-off H_live of 528 MiB (r3) is recorded and does not change the row under the frozen B3g.

**Positive control:** not required, since this is not a negative-estimate file. The uncapped arm moved usage: one 411 MB response
against 41 MB per read under the constant.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a, B2c–B2g, B3a–B3h and B4 are in the case file (uncommitted).
- `_INDEX-advisor.md`: the §2 row `7393d4f3…3317` was added, and the §1 Stage 4 column filled.
- `HANDOFF.md` was not edited (`HANDOFF-ADVISOR.md` §8).
