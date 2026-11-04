# ExecuteMessage_literal_1000-traceQuery-1000--autonomous — stage-4 results  <!-- file: results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md -->

> **Case:** [`ExecuteMessage_literal_1000-traceQuery-1000--autonomous`](../../stage3-ai-deep-read/cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/ExecuteMessage_literal_1000-traceQuery-1000--autonomous/`](../harness/ExecuteMessage_literal_1000-traceQuery-1000--autonomous/).
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster) as amended; "§9b–§9e" means B2a–B2e / B3a–B3e;
> the feedback section is the case file's section D.
>
> **Session:** Claude Opus 5.5 (`claude-opus-5-5`), Claude Code CLI, 2026-10-27, on the advisor's Mac (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | filed with sha256 `c3068106…` (as filed, 2026-10-26); the 11 audit amendments of 2026-10-27 (U1–U4, C1–C7) are uncommitted in the working tree at the time of the run. Frozen sha256 after the amendments: `3b910462a6295b00624c89e3376a43ab84112ae39a9152c196dd86dcf0256466` (new row in `_INDEX.md` §4). Both tiers of run 1 ran at this version; section D was filled after this hash. |
| **Harness** | `harness/ExecuteMessage_literal_1000-traceQuery-1000--autonomous/`: `TraceBoundValueTruncationProbeTest.java` (B2's test, U2's lines), `unit-run.sh`, `probe.py` (B3c/B3d client, C2/C3), `cluster-run.sh` (uncommitted). `unit-run.sh` is adapted (sed of names, then edits) from the harness folder of `native_transport_max_concurrent_connections_per_ip-configureInitialPipeline-getNativeTransportMaxConcurrentConnectionsPerIp--autonomous`; the node conf/start/stop functions of `cluster-run.sh` from `harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/cluster-run.sh`, and the driver import line of `probe.py` from that folder's `bigwrite.py`. Cells, readings, JFR window and every expected value are new; every number here was derived from the pinned source, none taken from another case or results file. |
| **Tiers and values** | The constant cannot be set (A1); the varied input is the demand. Unit: prepared blob S = 100, 499, 500, 600, 65 536, 1 048 576; prepared text \|T\| = 998, 999; multi 8 × 65 536; control (unprepared QUERY) S = 500, 65 536. Cluster: cells P499, P500, P65536, P1M (prepared EXECUTE) and Q65536, Q1M (unprepared control), N = 200 per cell (20 at 1 MiB). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the per-bound-value chars persisted in `system_traces.sessions.parameters`; the cluster tier measures the table's bytes on disk. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: a hard-coded literal, not settable; B2b/B3b vary the demand S across the cut (4–6 values) and add a second arm (the unprepared path, no cut) as the uncapped comparison. The lesson "a constant can be varied only by patching or Byteman" was weighed: the design does not vary the constant and says why, which the README allows. |
| A. Core question | real resource measured, not only the counter | Partly → Met | Unit reads persisted string lengths only (gap named in B2d; U4 says disk is the cluster tier's). Cluster B3d reads sessions bytes on disk, but with Linux `du -sb` (C3: BSD byte sums plus tablestats live space). The memtable and commit-log copies are not measured (named as secondary in A2). |
| A. Core question | usage driven to the limit and past it | Met | S = 65 536 and 1 MiB give literals 131× and 2 097× the cap. |
| B. Logic | each step says what it establishes | Met | B2b and B2h name what the boundary pairs, the control and the multi row establish. |
| B. Logic | prediction stated in numbers | Partly → Met | B2f had M₀ as an unknown and the control `Lq` in terms of an unmeasured prefix; U3 gives exact values (R − digits(k) constant; Lq = 40 + \|tbl\| + 2S; ΔM = 130 072). B3f had exact disk bounds but the per-request lengths only as "about 40 chars"; C5 gives them exactly. |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met | B2g/B3g had no verdict wording, no order and no no-row-fits row; U4 and C6 add them. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | U4/C6 row C require every value of 1004 chars to end in `...'` and to equal the first 1000 chars of the literal expected from source (content match) — the direct evidence that the line-231 branch fired. |
| B. Logic | alternative explanations and their controls | Met | The unprepared control (same bytes, no cut) excludes "the driver or server dropped large values"; the 499/500 and 998/999 pairs pin the boundary; truncation between cells (C3 adds D0 = 0 as a check). |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 and A3 are clear. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2 named the test but not its output format, keys of the text/multi runs or seeds (U2); B3 named Linux commands and `bin/cassandra -p` (C1, C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | C2–C4 fix the per-cell procedure, the readings and when they are taken; the JFR window is the P1M cell (C3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met | `$WORK`, `/Users/yangwang/cassandra-src` as build dir, `du -sb`, `pgrep -f CassandraDaemon`: replaced by this host's paths and tools (U1, C1, C3, C7). |
| D. Runnable | workload arithmetic reaches the limit | Met | Peak ≈ 42 MB of trace rows + 21 MB of base rows per cell, against 119 GiB free and a 1 GiB heap (2 MiB strings). |
| D. Runnable | load-bearing citations spot-checked | Met | `ExecuteMessage.java:160-161, 213-240` (check `:231`, cut `:232`), `QueryMessage.java:135-144` (uncut `query` at `:138`), `BytesSerializer.java:47-50, 65-68`, `TypeSerializer.java:80-105`, `AbstractTextSerializer.java:80-84`, `TraceKeyspace.java:75-136`, `TracingImpl.java:53-66`, `Message.java:235-248`, `BatchMessage.java:249-251`, `Tracing.java:93-95`, `TraceCqlTest.java:46-58, 116-148`, `UntypedResultSet.java:471-475`, `conf/cassandra.yaml:1044, 1147, 1752, 1864` hold at the pinned clone. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | This host's clone `$W/cassandra-run57`, harness paths, `-Dlocal.repository`; read thresholds checked (left on: largest read 131 KB) | applied 2026-10-27 (uncommitted) | no `$WORK` here; unit-yaml thresholds |
| U2 | Exact sub-run order, keys, k values, seeds; `PROBE`/`MULTI`/`TRACEFAIL`/`END` lines with a content match against the literal expected from source | applied | runnable without re-deriving; direct disallow evidence |
| U3 | Exact predictions (R − digits(k) constant; R_multi ≤ 1004; Lq = 40 + \|tbl\| + 2S; ΔM = 130 072) | applied | prediction in numbers |
| U4 | B2g rows with verdicts (N0, N1, W1, W2, C, N2, N3) | applied | every outcome has a row |
| C1 | macOS node set-up (`$W/node-emt`, `bin/cassandra -f` tracked, `auto_snapshot: false`), bundled driver import | applied | this host |
| C2 | `probe.py` cell procedure with per-request content checks | applied | exact workload |
| C3 | BSD byte sums instead of `du -sb`; tablestats; scan; D0 empty-table control; JFR window = the P1M cell, T informational | applied | this host; exact readings |
| C4 | exact procedure; shakedown first | applied | exact sampling and stop conditions |
| C5 | exact per-request lengths; filed disk bounds in bytes | applied | prediction in numbers |
| C6 | B3g rows with verdicts (I, N0, N1, W1, C, N2) | applied | every outcome has a row |
| C7 | macOS clean-up | applied | this host |
| S1 | For stage 3: the claim's "per-value footprint capped" holds per value only; a case on the number of bind variables or on `query` length would bound the row — the file already names both as bypasses (A3 step 6) | left for stage 3 | outside B1's claim |
| S2 | For stage 3: the transient heap of the full literal (A3 step 6) could be a case of its own; the JFR reading here (T) shows it is real | left for stage 3 | outside B1's claim |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 07:40–07:42; cluster 07:44–07:46 local time, EDT; node logs in UTC) |
| Node | `yangwang-mbp`, the advisor's laptop, single host (Apple T6000, 10 cores, 32 GiB) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew); `jcmd`, `jfr` in its `bin/` |
| Ant | 1.10.18 |
| Python | 3.8.11 (system `python3`), bundled driver 3.29.0 from `lib/cassandra-driver-internal-only-3.29.0.zip` |
| Local clone commit | `$W/cassandra-run57` (`W=~/Library/Caches/stage4`), fresh clone of `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 51 s; `git status` clean after the run |
| Case-file commit / harness commit | uncommitted amendments on top of the filed file (sha256 `3b910462…`) / harness uncommitted |
| Storage for node data | internal SSD, APFS, 119 GiB free; node files `$W/node-emt`, fresh, removed at the end |
| Loopback / ports | 127.0.0.1–.3 on `lo0` (only .1 used); 7000, 7199, 9042, 9091 free before the run |
| Full logs | `$W/logs/ExecuteMessage_literal_1000-traceQuery-1000--autonomous/` (`clone.log`, `build-test.log`, `unit-shake/`, `unit-r1/`, `cluster-shake/`, `cluster-r1/` incl. `P1M/alloc.jfr` and `P1M/jfr-print.txt`) |

Machine facts relied on (from earlier runs on this Mac): no `mkdir` in `$HOME` outside `$W`; commands touching `$W`/Java run unsandboxed;
`-Dlocal.repository=$W/m2` on every `ant` call; no `setsid` (node started as a tracked background `bin/cassandra -f > log 2>&1 < /dev/null`);
BSD `stat -f %z` instead of `du -sb`; TRUNCATE leaves bytes in `snapshots/` under the default `auto_snapshot` (hence `auto_snapshot: false`, and
the byte sums exclude `snapshots/`/`backups/`); the unit yaml's read thresholds (checked against the largest read); CQLTester needs
`requireNetwork()`; test stdout lands in `build/test/logs/**/TEST-<class>.log`; a `-D` knob reaches the forked test JVM only via
`-Dtest.jvm.args` (the shakedown's `-Demt.shake=1`); the bundled Python driver with DCAware, `token_metadata_enabled=False`, heartbeat off
and raised timeouts; node `system.log` timestamps are UTC; the daemon class name kept out of `pkill` patterns; long steps in the background
and polled; shakedown before run 1; `selfcheck.py` written before run 1 and run end to end on both shakedowns (exit status checked).

## 3. Runbook defects

None. Both shakedowns (unit with `-Demt.shake=1`: S = 100, 700, |T| = 500, multi 8 × 700, control 700; cluster with N = 5 per cell) ran as
written and are not readings (`run1/shake/`). One self-check fix was made after the cluster shakedown and before run 1: its regex for
the `Node configuration:[…]` line stopped at the first inner `]`; it now takes the rest of the line (no runbook step or reading depends
on it). Self-check of the shakedowns: unit 41 checks, cluster 27 checks, 0 failed, exit 0 (`run1/shake/selfcheck-*-shake.out`).

## 4. Run 1

**Scope:** unit tier, all U2 sub-runs; cluster tier, cells P499, P500, P65536, P1M, Q65536, Q1M. **Command logs:** `run1/unit/commands.log`,
`run1/cluster/commands.log`. Raw excerpts: `run1/unit/TEST-excerpt.log` (the probe lines of the TEST log), `run1/unit/probe.txt`,
`run1/unit/ant-summary.txt`; `run1/cluster/summary.txt`, `node-config.txt`, `conf-lines.yaml`, and per cell `cell.out` (one `REQ` line per
request), `scan.out` (one `ROW` line per session row), `sess-files.txt`/`d0-files.txt`/`ev-files.txt`/`pt-files.txt` (size and path of every
file summed), `tablestats-*-excerpt.txt`; `P1M/jfr-event-example.txt` (one JFR event, verbatim).

### 4.1 Readings

**Unit tier** (`run1/unit/TEST-excerpt.log`; JUnit 1 test, 0 failures, `run1/unit/ant-summary.txt`; tbl = `cql_test_keyspace.table_probe_00`, 32 chars)

| kind | S or \|T\| | L (pred) | suffix (pred) | match | Lint | M | R (R − digits(k)) |
|---|---|---|---|---|---|---|---|
| prepared blob | 100 | 202 (202) | 0 (0) | 1 | 202 | 370 | 168 (165) |
| prepared blob | 499 | 1000 (1000) | 0 (0) | 1 | 1000 | 1168 | 168 (165) |
| prepared blob | 500 | 1004 (1004) | 1 (1) | 1 | 1004 | 1172 | 168 (165) |
| prepared blob | 600 | 1004 (1004) | 1 (1) | 1 | 1004 | 1172 | 168 (165) |
| prepared blob | 65 536 | 1004 (1004) | 1 (1) | 1 | 1004 | 1174 | 170 (165) |
| prepared blob | 1 048 576 | 1004 (1004) | 1 (1) | 1 | 1004 | 1176 | 172 (165) |
| prepared text | 998 | 1000 (1000) | 0 (0) | 1 | 1000 | 1172 | 172 |
| prepared text | 999 | 1004 (1004) | 1 (1) | 1 | 1004 | 1176 | 172 |
| multi, each of 8 | 65 536 | 1004 (1004) | 1 (1) | 1 | 1004 | 8353 | `MULTI` sumL = 8032, R_multi = 321 (≤ 1004) |
| control | 500 | Lq = 1072 (40 + 32 + 1000) | — | 1 | 1072 | 1146 | 74 |
| control | 65 536 | Lq = 131 144 (40 + 32 + 131 072) | — | 1 | 131 144 | 131 218 | 74 |

ΔM(control) = 131 218 − 1146 = 130 072 (predicted 130 072). No `TRACEFAIL`; `END` present.

**Cluster tier** (`run1/cluster/summary.txt`, raw files per cell). Dsess = bytes of the `system_traces.sessions` files after flush; D0 = the
same right after the cell's TRUNCATEs.

| Cell | N | requests ok / fail | stored value length min–max (pred) | `...'` suffix | content match | scan rows / nbv | D0 | Dsess (= tablestats live) | Dsess / N | Dev (context) | Dpt (context) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| P499 | 200 | 200 / 0 | 1000–1000 (1000) | 0 | 200 | 200 / 200 | 0 | 221 533 | 1108 | 26 237 | 111 069 |
| P500 | 200 | 200 / 0 | 1004–1004 (1004) | 200 | 200 | 200 / 200 | 0 | 220 882 | 1104 | 26 024 | 111 151 |
| P65536 | 200 | 200 / 0 | 1004–1004 (1004) | 200 | 200 | 200 / 200 | 0 | 220 148 | 1101 | 25 839 | 13 187 050 |
| P1M | 20 | 20 / 0 | 1004–1004 (1004) | 20 | 20 | 20 / 20 | 0 | 27 834 | 1392 | 7 623 | 21 082 413 |
| Q65536 (control) | 200 | 200 / 0 | `query` 131 109–131 111 (36 + digits(i) + 2S) | 0 | 200 | 200 / 0 | 0 | 25 491 511 | 127 458 | 25 529 577 | 13 187 054 |
| Q1M (control) | 20 | 20 / 0 | `query` 2 097 189–2 097 190 | 0 | 20 | 20 / 0 | 0 | 40 704 895 | 2 035 245 | 40 706 279 | 21 082 413 |

Ratios: Q65536 / P65536 = 115.8; P65536 / P500 = 1.00. Node configuration: `auto_snapshot=false`, `trace_type_query_ttl=1d`,
`memtable_allocation_type=heap_buffers`, `rpc_address=127.0.0.1` (`run1/cluster/node-config.txt`); 0 `ERROR` lines in `system.log`.
**T (informational, C3):** 60 `ObjectAllocationOutsideTLAB` events of ≥ 1 MiB with a `toCQLLiteral` frame during the 20 P1M requests
(3 per request); the example is a 4.0 MB `char[]` allocated in `Hex.bytesToHex` ← `BytesSerializer.toCQLLiteralNonNull` ←
`ExecuteMessage.traceQuery` line 230 (`run1/cluster/P1M/jfr-event-example.txt`).

### 4.2 Conclusion and logic

1. **Validity.** Unit: 18 `PROBE` lines, one `MULTI`, `END`, no `TRACEFAIL`; every line has Lint = L, so the driver's trace and the
   server-side read of the row agree [observed: `run1/unit/TEST-excerpt.log`]. Cluster: the node ran with `auto_snapshot=false` and
   the 1d trace TTL [observed: `run1/cluster/node-config.txt`]; every cell ran N requests with 0 failures, its scan found exactly N
   session rows, and D0 = 0 before every cell [observed: `run1/cluster/<cell>/cell.out`, `scan.out`, `d0-files.txt`]; the control cells
   stored 131 KB and 2 MB per row, far past the 1000-char cut [observed: `Q*/cell.out`]. Valid.
2. **Readings.** Nothing unusual. Dsess equals tablestats `Space used (live)` in every cell [observed: `run1/cluster/summary.txt`]. P1M's
   per-request bytes (1392) are higher than P500's (1104) because the fixed per-SSTable components (Statistics.db ≈ 5 KB etc.) are spread
   over 20 rows instead of 200 [inferred: `P1M/sess-files.txt` vs `P500/sess-files.txt`]; Q1M has two SSTables (16 files: a memtable flush
   during the cell) [observed: `Q1M/sess-files.txt`]. The control's stored bytes are 97 % of the uncut chars (25.49 MB of 26.22 MB
   `sumv`): random hex does not compress [observed: `Q65536/scan.out`, `summary.txt`].
3. **Matched row.** Unit **C (Confirmed — caps the persisted trace value per bound value; the cap is per value)**: every U3 cell holds —
   L = 202, 1000 below the cut, 1004 with `...'` from S = 500 and |T| = 999 on, content match on all 18 lines, R − digits(k) = 165 on
   all six prepared-blob lines (spread of R 4 ≤ 10), R_multi = 321 ≤ 1004 with each of the 8 values at 1004, control Lq = sent query and
   ΔM = 130 072 [observed: `run1/unit/TEST-excerpt.log`, recomputed in `run1/selfcheck-unit.out`]. Cluster **C (Confirmed — caps the
   trace disk usage per bound value)**: every stored `bound_var_1_v` is 1000 chars at S = 499 and exactly 1004 chars ending in `...'`
   and equal to the first 1000 chars of `0x`+hex at S ≥ 500 (client) and in the scan; Dsess(P65536) = 220 148 and Dsess(P1M) = 27 834
   < 1 048 576; P65536 ≤ 2 × P500 (ratio 1.00); Q65536 = 25 491 511 ≥ 13 107 400; Q1M = 40 704 895 ≥ 20 000 000; Q65536 / P65536 = 115.8 ≥ 10
   [observed: `run1/cluster/*/cell.out`, `scan.out`, `sess-files.txt`, recomputed in `run1/selfcheck.out`].
4. **Excluded rows.** Unit: N0 (no `TRACEFAIL`, all 19 lines, `END`); N1 (both control lines match, ΔM = 130 072 ≥ 130 062); W1 (no
   line above 1004); W2 (spread 4 ≤ 10, R_multi 321 ≤ 1004); N2/N3 (C fits). Cluster: I (D0 = 0, every cell N requests); N0 (no
   `REQFAIL`, nbv = N in every P cell); N1 (control cells above their bounds, all matched); W1 (max stored value 1004, P65536 = 0.22 MB
   < 5 MB); N2 (C fits). [observed: same files]
5. **Observed vs. inferred.** The conclusion depends on: (a) the 1004-char values were produced by the line-231 branch and not by the
   driver or another cut [inferred: each equals the first 1000 chars of the literal the source renders, plus `...'`, exactly the
   `:232` expression; the boundary falls exactly between 1000 and 1002/1001 chars; the same bytes through the unprepared path are
   stored uncut]; (b) the bytes of the sessions table are the resource the cap acts on, and the other copies (memtable, commit log,
   base table) are outside the claim [inferred: A2, B1].
6. **Deviations and gaps.** None from the frozen runbook. The memtable and commit-log copies of the trace rows were not measured
   (named in A2 as secondary). The cap is per value: the multi run shows 8 values cost 8 × 1004 chars, and the `query` text and the
   unprepared path are uncapped (A3 step 6; the control shows the latter at 127 KB and 2 MB per row). The transient heap is not capped:
   the informational T reading shows a 4 MB `char[]` per 1 MiB blob at line 230 before the check (S2).
7. **Core question.** The constant cannot be varied, so the design varies the demand: as the bound blob grows from 499 bytes to
   1 MiB (literals of 1000 to 2 097 154 chars), the persisted trace value stays at 1000 then exactly 1004 chars, cut by the line-231
   branch (parts 3, 5a), and the sessions table holds about 1.1 KB per traced request whatever S is (220 882 → 220 148 bytes for 200
   requests at S = 500 → 65 536; part 3), while the same bytes through the uncut unprepared path grow it linearly to 127 KB and 2 MB per
   request (parts 2, 3). So the constant caps the trace disk usage per bound value of a prepared EXECUTE; it does not cap the number of
   values, the query text, the unprepared path or the transient heap (part 6).

**Conclusion (one line):** unit — row C, confirmed; cluster — row C, confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1 and run end to end on both shakedowns, exit 0: `run1/shake/selfcheck-unit-shake.out`,
`run1/shake/selfcheck-cluster-shake.out`) re-reads the raw files — the TEST log's probe lines; every `cell.out`, `scan.out`, file list,
tablestats file and `jfr-print.txt` of the full log folder, and `system.log` — recomputes every reading without the run scripts' summary
lines (the expected values from the rule, the byte sums from the file lists, T by a different parse of the JFR print), cross-checks the
scripts' logged/summary lines, and matches the U4/C6 rows. Unit: 59 checks, 0 failed, row C (`run1/selfcheck-unit.out`, exit 0).
Cluster: 27 checks, 0 failed, row C (`run1/selfcheck.out`, exit 0).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `TEST-excerpt.log`: 18 PROBE, MULTI, END, Lint = L on each; `cluster/node-config.txt` `auto_snapshot=false trace_type_query_ttl=1d`; each `cell.out` has N `REQ` lines and `CELL … fail=0`; each `d0-files.txt` is empty. |
| 2. Readings | yes | `summary.txt` CELLSUM Dsess = LiveSess in all six cells; `P1M/sess-files.txt` Statistics.db and the other fixed components; `Q1M/sess-files.txt` lists two generations; `Q65536/scan.out` `sumv=26225890`. |
| 3. Matched row | yes | `selfcheck-unit.out` every cell "holds", R − digits(k) = 165 ×6, ΔM = 130 072; `selfcheck.out` per-request lengths as C5 in every cell and all disk conditions; row C both tiers. |
| 4. Excluded rows | yes | `selfcheck.py` evaluates U4 and C6 in order; no earlier row fires. |
| 5. Observed vs. inferred | yes | (a) every P-cell `REQ` line `match=1` (content equals `('0x'+hex)[:1000] + "...'"`), P499 `len=1000 suffix=0`, Q-cell `match=1` with the uncut query; unit text 998/999 pair. (b) from A2/B1, no reading needed. |
| 6. Deviations and gaps | yes | `commands.log` shows the frozen cells and N (`cells: P:499:200 … Q:1048576:20`), the JFR window around P1M only; `jfr-event-example.txt` shows the line-230 allocation. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Flat stored value and flat sessions bytes per request across S ≥ 500 with the cut evidenced per value, against a control that grows linearly with the same bytes — as B1 and C6 require. |

### 5.2 Run 2?

**No** — decided 2026-10-27. The readings are exact lengths and exact byte sums, every inferred statement has direct support in run 1's raw
files (the content match per request), the self-check settles every part, and the result confirms the case (no refutation, no bypass beyond
those the file records).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped to what is persisted).

**Claim tested:** (B1) For a traced prepared EXECUTE with one blob of S bytes, the stored `bound_var_*` value is 2S+2 chars when 2S+2 ≤ 1000
and exactly 1004 chars for every larger S, so the `system_traces.sessions` footprint per traced request stays flat as S grows; the same
value as an inline literal through an unprepared QUERY grows the stored `query` and the sessions table on disk linearly in S.
"Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (U4 row C): stored value 202 / 1000 / 1004 / 1004 / 1004 / 1004 chars at S = 100 / 499 / 500 / 600 / 65 536 / 1 MiB, text 1000 / 1004 at \|T\| = 998 / 999, each cut value = first 1000 chars + `...'`; the rest of the row constant (R − digits(k) = 165); 8 values cost 8 × 1004; the uncut control's row grows by exactly 130 072 chars | caps (per bound value, in the persisted trace row) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (C6 row C): every stored `bound_var_1_v` 1000 chars at S = 499 and exactly 1004 (with `...'`, content-matched) at S = 500, 65 536, 1 MiB; sessions on disk 220 882 / 220 148 B for 200 requests at S = 500 / 65 536 and 27 834 B for 20 at 1 MiB, against 25 491 511 B / 40 704 895 B for the unprepared control (115.8×) | caps (per bound value of a prepared EXECUTE; not the number of values, the query text, the unprepared path or the transient heap) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted, 2026-10-27); the amended sections are U1–U4 (B2a–B2h)
and C1–C7 (B3a–B4), applied before any reading. `_INDEX.md` §4 has the frozen-hash row and §1's Stage 4 column is filled.
