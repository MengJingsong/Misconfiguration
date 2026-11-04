# batch_size_fail_threshold-verifyBatchSize-mutations--autonomous — stage-4 results  <!-- file: results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md -->

> **Case:** [`batch_size_fail_threshold-verifyBatchSize-mutations--autonomous`](../../stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1: at F = 50, 100
> and 200 KiB, a multi-partition batch is rejected if and only if its measured `dataSize` exceeds 1024·F, and a rejected batch
> leaves 0 rows and 0 memtable bytes; all 18 single-partition batches, up to 209,015 B at F = 50, are accepted).
> **Cluster: Confirmed — caps only on some paths (bypass)** (B3g rows 1 and 3: `multi 30` puts 0 B on disk at 50 KiB and
> 12.31 MB at 100 and 200 KiB; `multi 60` puts 0 B at 50 and 100 KiB and 24.60 MB at 200 KiB; `single 30` puts 12.31 MB on disk
> at every F, including 50 KiB). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/`](../harness/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> The case file was written by an earlier stage-3 session; this session did not write it.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `80daf71` (sha256 `18f8f934…f050d`). Frozen after the step-0 audit's fifteen amendments (2026-10-26, before any run-1 reading): sha256 **`0e9c927f0d918b9eb0c8f02ff809b9a11a7958b59e5c978903e30ab75bb2016a`**. Both tiers' readings were taken at this version. New row in `_INDEX.md` §4; `run1/freeze.txt` (with the harness and self-check hashes). Not committed (no commit was asked for). |
| **Harness** | [`../harness/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/`](../harness/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/): `BatchFailThresholdProbeTest.java` (B2c with amendment B2c), `unit-run.sh`; `batch.py` (bundled-driver client), `cluster-run.sh` (three node lifetimes, F = 50, 100, 200). Instrument checks before the freeze: unit shakedown at F = 8, 16 KiB and B = 2, 5 KiB (`shakedown/unit-f8-16-b2-5-summary.txt`); cluster shakedown with N = 10 batches per run (`shakedown/cluster-n10-summary.txt`). The shakedowns found two harness bugs, both fixed before the freeze and neither in the case file: the probe's helper `list(...)` clashed with `CQLTester.list(Object...)` (compile error), and `cluster-run.sh`'s client wrapper echoed its log line into the captured result (the first cluster shakedown is kept outside the repo as `shakedown/cluster1-clientlog-bug/`). Self-check [`run1/selfcheck.py`](batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/run1/selfcheck.py) was written before run 1 and tested on the shakedown files (`shakedown/selfcheck-on-shakedown.out`: 27/27). |
| **Tiers and values** | Unit (B2): one `ant testsome` JVM; F ∈ {50, 100, 200} KiB (warn 1 KiB) × B ∈ {10, 24, 26, 60, 98, 102} KiB × {multi, single} = 36 cases. Cluster (B3): one node, heap 2G, warn 5KiB; F ∈ {50, 100, 200} KiB from the yaml with a restart; runs `multi 30`, `multi 10`, `single 30`, `multi 60`, N = 200 logged batches each. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: the operand is `IMutation.dataSize` in bytes (`IMutation.java:63-72`); usage read as memtable bytes, rows and sstable bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | B2b/B3b had two values (50, 200). F = 100 added in both tiers, and a `multi 60` run so the cluster boundary falls between workloads at F = 100 (amendments B2b, B3b, B3c). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit reads the memtable's accounting (gap named, amendment B2d); cluster reads sstable bytes on disk (real). Commit-log bytes and the coordinator heap overshoot (A3) are not measured; named in B3d and amendment B2d. |
| A. Core question | usage driven to the limit and past it | Met | Batches on both sides of each F (B2c, B3c). |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "about", "≈ 12 MiB", tolerance only on one cell (amendments B2f, B3f: exact rule on the measured operand, ±15 % on disk bytes, ERROR count = rejections). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Missing: Invalid (read-back, operand, connection), rejected for another reason, ERROR count mismatch, partial application, disk not tracking data, no row fits; verdict words and Effect rule (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | The boundary moves with F (B2g/B3g row 1); direct disallow evidence added: the ERROR line at `BatchStatement.java:356-357` counted per run (amendments B2d, B3d). |
| B. Logic | alternative explanations and their controls | Met | Raised F as positive control; `multi 10`; compression off; RF 1. Amendments add the automatic-flush check. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Observable file, per-run log window, client form (amendments B2d, B2e, B3c–B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | `du -sb`; the run's ERROR window; snapshot bytes after TRUNCATE (amendment B3d). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | As written the probe does not run: `formatQuery` takes one argument (`CQLTester.java:1598-1602`), so two `%s` throw; `parseStatement(String, ClientState)` returns a prepared statement with no `prepare` (`QueryProcessor.java:372-375`); `executeNet` needs `requireNetwork()`. Host: `/local`, `bin/cassandra -p` without `setsid`, BSD `du`. Fixed before the freeze (amendments B2a, B2c, B3a, B3d, B3e, B4). The filed `PYTHONPATH` import works (`run1/stepE.txt`). |
| D. Runnable | workload arithmetic reaches the limit | Met | Operand 2048·B + tens of bytes brackets every F; largest run 24.6 MB against 135 GiB free; memtable flush trigger far above 25 MB at 2G heap. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: `BatchStatement.java:269-324, 332-366, 405-445`, `IMutation.java:63-72`, `PartitionUpdate.java:346-349`, `AbstractCell.java:120-127`, `BTreeRow.java:522-529`, `DatabaseDescriptor.java:2069-2091`, `Config.java:329-332`, `conf/cassandra.yaml:1147, 1840-1844`, `CQLTester.java:613-616, 1524-1527, 1593-1602`, `QueryProcessor.java:372-375`, `BatchQueryOptions.java:45-48, 99-102`. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and build | Amendment 2026-10-26 | `/local` does not exist here. |
| 2 | B2b: third value F = 100; read-back line | Amendment 2026-10-26 | Group A. |
| 3 | B2c: `%1$s`, `requireNetwork()`, cast instead of `prepare`, fixed seed, one `println` per case | Amendment 2026-10-26 | The probe does not run as written. |
| 4 | B2d: observable file; ERROR-line count as disallow evidence; gaps named | Amendment 2026-10-26 | Stdout lands in `build/test/logs`; group B. |
| 5 | B2e: procedure via `unit-run.sh` | Amendment 2026-10-26 | Paths, clean clone. |
| 6 | B2f: exact rule on the measured operand; 8 of 36 rejected | Amendment 2026-10-26 | Group B. |
| 7 | B2g: verdict words, five rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 8 | B3a: this host; tracked `bin/cassandra -f`; readiness | Amendment 2026-10-26 | Paths; no `setsid`. |
| 9 | B3b: F = 100 added; read-back from the startup configuration line | Amendment 2026-10-26 | Group A. |
| 10 | B3c: `multi 60`; client form | Amendment 2026-10-26 | Group A at F = 100. |
| 11 | B3d: bytes skipping `snapshots/`; per-run ERROR window; tablestats timing; automatic-flush check | Amendment 2026-10-26 | BSD `du`; `auto_snapshot: true` with TRUNCATE. |
| 12 | B3e: one script, three lifetimes | Amendment 2026-10-26 | Order. |
| 13 | B3f: exact forms for 12 cells | Amendment 2026-10-26 | Group B. |
| 14 | B3g: verdict words, six rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 15 | B4: this host | Amendment 2026-10-26 | Paths. |
| 16 | The design could also show the other bypasses A3 lists (a conditional batch, an over-F single-partition batch near `max_mutation_size`) | Left for stage 3 | Not needed for B1's claim. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 13:55–13:57 EDT; cluster 13:57–14:00 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro, T6000); 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 135 GiB free; loopback 127.0.0.1–.3 present (one node, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before; none after |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), no agent |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip` (subfolder import), protocol 5, no auth |
| Local `cassandra-src` clone commit | `$W/cassandra-run32` = `~/Library/Caches/stage4/cassandra-run32`, fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` in 58 s; `git status` clean after both tiers |
| Case-file commit / harness commit | filed `80daf71`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-bsf/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, own `conf/`; kept across the three restarts, wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/` — `clone-build-run32.log`, `stepE.txt`, `shakedown/` (not evidence), `unit/` (`ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `error-fail-lines.txt`, `commands.log`, `summary.txt`), `cluster/` (`node.out`, `system.log`, `commands.log`, `summary.txt`, `syslog-F<F>-<shape>-<B>.txt` per run, `yaml-*.txt`, `flush-lines.txt`, `error-warn-other.txt`), `cluster.out` |

**Machine facts relied on** (`environment-advisor.md` and earlier runs on this host): every file under `$W` (no `mkdir` in `$HOME`
outside it); every `ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run unsandboxed; no
`setsid`, so the node is a tracked background `bin/cassandra -f`; the forked test JVM writes stdout and the server log to
`build/test/logs/**/TEST-<class>.log`, one line per write (amendment B2d); `CQLTester` needs `requireNetwork()` (amendment B2c);
the unit yaml's read thresholds (`test/conf/cassandra.yaml:63-67`) were checked and do not bind (each read is a `count(*)` over at
most two rows of ≤ 104 KiB, below the 1024 KiB warn), so no change was made; BSD `du` (amendment B3d); the bundled driver under a
subfolder of the zip, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0` (no reconnect was
needed: 0 other errors); **`batch_size_fail_threshold` is a plain configuration check in `verifyBatchSize`, not a guardrail, so
it has no superuser exemption** (`BatchStatement.java:332-366`) and the default `AllowAllAuthenticator` was kept (no amendment);
the daemon pattern in the scripts is split so their command lines never match; long steps ran in the background and were
polled; shakedowns before run 1; bounds derived from source (the operand bound 2048·B to 2048·B + 256 before any reading);
`selfcheck.py` written before run 1. `jstat`, MAT, jmxterm, Byteman: not needed.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2c | `formatQuery` is `String.format(query, table)` with one argument (`CQLTester.java:1598-1602`); the filed batch text has two `%s` → `MissingFormatArgumentException` | `%1$s` in both inserts (amendment B2c item 1) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B2d(i) | `QueryProcessor.parseStatement(String, ClientState)` returns an already prepared `CQLStatement` (`QueryProcessor.java:372-375`); `.prepare(...)` does not compile | cast the result (amendment B2c item 3) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B2c | `executeNet` needs the native server; the filed test does not start it | `@BeforeClass requireNetwork()` (amendment B2c item 2) | 2026-10-26, before the freeze | uncommitted |
| A4 | audit | B2a/B3a/B3d/B3e | `/local` paths; `bin/cassandra -p` daemonizes and there is no `setsid`; BSD `du -sb`; TRUNCATE with `auto_snapshot` keeps the bytes in `snapshots/`, which `du` of the table directory counts | host paths, tracked `bin/cassandra -f`, byte sum skipping `snapshots/` (amendments B2a, B3a, B3d, B3e, B4) | 2026-10-26, before the freeze | uncommitted |

Run 1: none. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/run1/unit/commands.log`, `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/test-log-probe-lines.txt`, `ant-tests-run.txt`: `Tests run: 1, Failures: 0, Errors: 0`; read-backs
`failBytes` 51,200 / 102,400 / 204,800 and `warnBytes` 1,024; `PROBE done cases=36`). The operand is the same at every F:

| B (KiB) | multi: mutations / dataSize (B) | single: mutations / dataSize (B) | F = 50 (51,200) multi | F = 100 (102,400) multi | F = 200 (204,800) multi | single, every F |
|---|---|---|---|---|---|---|
| 10 | 2 / 20,628 | 1 / 20,599 | accepted, rows 2, memDelta 20,586 | accepted | accepted | accepted, rows 2, memDelta 20,578 |
| 24 | 2 / 49,300 | 1 / 49,271 | accepted, memDelta 49,258 | accepted | accepted | accepted |
| 26 | 2 / 53,396 | 1 / 53,367 | **rejected** `Batch too large`, rows 0, memDelta 0 | accepted, memDelta 53,354 | accepted | accepted |
| 60 | 2 / 123,028 | 1 / 122,999 | **rejected**, 0 / 0 | **rejected**, 0 / 0 | accepted, memDelta 122,986 | accepted |
| 98 | 2 / 200,852 | 1 / 200,823 | **rejected**, 0 / 0 | **rejected**, 0 / 0 | accepted, memDelta 200,810 | accepted |
| 102 | 2 / 209,044 | 1 / 209,015 | **rejected**, 0 / 0 | **rejected**, 0 / 0 | **rejected**, 0 / 0 | accepted, memDelta 208,994 |

Every accepted case has rows = 2 and memDelta ≥ 2048·B; dataSize − 2048·B is 148 (multi) and 119 (single) for every B. 8 of
36 cases rejected; 8 `ERROR … (see batch_size_fail_threshold)` lines in the test log, each naming the case's size and F
(`run1/unit/test-log-error-fail-lines.txt`).

**Cluster tier** (`run1/cluster/summary.txt`, `commands.log`, `config-lines.txt`, `syslog-*-error-excerpt.txt`; read-backs
`batch_size_fail_threshold=50KiB/100KiB/200KiB`, `batch_size_warn_threshold=5KiB`; heap `-Xms2G -Xmx2G`; `compression={'enabled': 'false'}`;
0 other errors in every run; 0 `Flushing largest`; 0 other ERROR lines in `system.log`). N = 200 per run; Δ = change in the run.

| F | Run | Client ok / rejected | Memtable data size before → after (B) | Local write count Δ | `count(*)` | Disk Δ (B), Data.db Δ | ERROR lines in the run |
|---|---|---|---|---|---|---|---|
| 50 | multi 30 | 0 / 200 | 0 → 0 | 0 | 0 | 0, 0 | 200 (`is of size 60.145KiB, exceeding … 50.000KiB`) |
| 50 | multi 10 | 200 / 0 | 0 → 4,117,200 | +400 | 400 | 4,120,744 (1.006 × 4,096,000), +1 | 0 |
| 50 | single 30 | 200 / 0 | 0 → 12,307,600 | +200 | 400 | 12,307,754 (1.002 × 12,288,000), +1 | 0 |
| 50 | multi 60 | 0 / 200 | 0 → 0 | 0 | 0 | 0, 0 | 200 (`120.145KiB … 50.000KiB`) |
| 100 | multi 30 | 200 / 0 | 0 → 12,309,200 | +400 | 400 | 12,314,190 (1.002), +1 | 0 |
| 100 | multi 10 | 200 / 0 | 0 → 4,117,200 | +400 | 400 | 4,120,736 (1.006), +1 | 0 |
| 100 | single 30 | 200 / 0 | 0 → 12,307,600 | +200 | 400 | 12,307,757 (1.002), +1 | 0 |
| 100 | multi 60 | 0 / 200 | 0 → 0 | 0 | 0 | 0, 0 | 200 (`120.145KiB … 100.000KiB`) |
| 200 | multi 30 | 200 / 0 | 0 → 12,309,200 | +400 | 400 | 12,314,191 (1.002), +1 | 0 |
| 200 | multi 10 | 200 / 0 | 0 → 4,117,200 | +400 | 400 | 4,120,736 (1.006), +1 | 0 |
| 200 | single 30 | 200 / 0 | 0 → 12,307,600 | +200 | 400 | 12,307,757 (1.002), +1 | 0 |
| 200 | multi 60 | 200 / 0 | 0 → 24,597,200 | +400 | 400 | 24,602,969 (1.001 × 24,576,000), +1 | 0 |

Each accepted multi run also wrote 200 `WARN … Batch for [b.t]` lines (above the 5 KiB warn threshold); the single runs wrote
none (one mutation, `BatchStatement.java:334`).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit/test-log-probe-lines.txt`, `ant-tests-run.txt`] read-backs equal 1024·F and 1024; every
   operand has the expected mutation count (2 / 1) and lies in [2048·B, 2048·B + 256]; 36 cases ran; the test passed. The limit
   was passed at every F (dataSize up to 209,044 B against 51,200–204,800). Valid.
2. **Readings** — nothing unusual. memDelta is 42 B (multi) or 21 B (single) below dataSize in every accepted case; the B2f
   bound (≥ 2048·B) holds.
3. **Matched row** — B2g row 1, "The rejection boundary sits at dataSize ≈ F for both F values, and rejected batches leave rows
   and memtable unchanged" [observed: rejected iff mutations = 2 and dataSize > 1024·F at all three F (boundaries between
   49,300 and 53,396 at F = 50, between 53,396 and 123,028 at F = 100, between 200,852 and 209,044 at F = 200); each rejection
   `Batch too large` with rows 0 and memDelta 0; 8 ERROR lines = 8 rejections]. Single-partition part of B1 [observed: all 18
   single cases accepted, including dataSize 209,015 at F = 50].
4. **Excluded rows** — row 2 (over-F multi accepted or leaving rows/bytes): no case. Row 3 (single rejected): no case. Row 4
   (boundary does not move): it moves at each F. Added rows: Invalid (read-back, operand, case count all hold); rejected
   at or below F: none; message other than `Batch too large`: none; ERROR count mismatch: 8 = 8; partial application: none.
5. **Observed vs. inferred** — all observed.
6. **Deviations and gaps** — none in the run. The memtable reading is the memtable's accounting, not the live heap; the
   coordinator heap that holds the built mutations before the check is not measured (gap named, amendment B2d).
7. **Core question** — usage follows the constraint for multi-partition batches: the largest accepted batch rises with F
   (49,300 → 53,396 → 200,852 B) and every batch above 1024·F is refused before it adds a row or a memtable byte. A
   single-partition batch is never checked, whatever its size.

**Unit tier conclusion:** B2g row 1 — **confirmed**. Effect (amended B2g): **caps only on some paths (bypass)**.

**Cluster tier**

1. **Validity** — [observed: `cluster/config-lines.txt`, `summary.txt`, `flush-lines.txt`, `error-warn-other.txt`] read-backs
   50/100/200 KiB and warn 5 KiB; 0 other errors and 0 connection failures in every run; no automatic flush; no other ERROR
   line; compression off; `yaml-diff-F*.txt` show only the B3a overrides. Valid.
2. **Readings** — nothing unusual. Local write count rises by 2 per accepted multi batch and 1 per single batch (one mutation
   per partition).
3. **Matched row** — B3g row 1, "`multi 30` gives zero bytes at 50KiB and about 12 MiB at 200KiB" [observed: 0 B, no
   Data.db, 0 rows at 50; 12,314,191 B at 200 and 12,314,190 B at 100], with the added F and run following the same rule
   (`multi 60`: 0 B at 50 and 100, 24,602,969 B at 200), and every rejected run 200/200 rejected with memtable 0 → 0, write
   count +0 and 200 ERROR lines naming that lifetime's F. **And** B3g row 3, "`single 30` at 50KiB gives about 12 MiB"
   [observed: 200 accepted, 400 rows, 12,307,754 B].
4. **Excluded rows** — row 2 (`multi 30` at 50 leaves rows or bytes): 0 rows, 0 B. Row 4 (`single 30` rejected): 0 rejected
   at each F. Row 5 (`multi 10` rejected at 50): 200 accepted. Added rows: Invalid (read-backs, no node failure, no other
   error, no automatic flush); predicted-accepted run rejected: none; `multi 60` accepted at 50 or 100: no; ERROR count
   mismatch: 200 per rejected run, 0 per accepted run; disk Δ outside ±15 %: largest deviation +0.6 %.
5. **Observed vs. inferred** — all verdict statements are observed. Not observed: commit-log bytes per batch (B3d says why);
   that rejected batches add none is inferred from the order in the source (`verifyBatchSize` before `mutateWithTriggers`,
   `BatchStatement.java:439-445`) and from local write count +0; the verdict does not rest on it.
6. **Deviations and gaps** — none in the run.
7. **Core question** — disk follows the constraint for multi-partition batches: the same 60 KiB workload stores 0 B at
   F = 50 and 12.3 MB at F = 100 and 200; the 120 KiB workload stores 0 B at 50 and 100 and 24.6 MB at 200. Single-partition
   batches of 60 KiB store 12.3 MB at every F, so the cap holds only on the multi-partition path.

**Cluster tier conclusion:** B3g rows 1 and 3 — **confirmed**. Effect (amended B3g): **caps only on some paths (bypass)**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before run 1, sha256 in `run1/freeze.txt`) re-reads `unit/TEST.log` and `unit/ant.log`, the
cluster's `commands.log` (every logged reading) and the full `system.log`, in which it splits the three lifetimes at their
startup configuration lines and recounts the fail-threshold ERROR lines by the size and threshold printed in each line. It
re-derives every B2f and B3f condition. Output `run1/selfcheck.out`: **28 checks, 28 pass, 0 fail** (U0–U10, C0–C4 and one
check per cluster cell).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0–U3, C0, C1, C3, C4 pass; `config-lines.txt` shows the three F with warn 5KiB |
| 2. Readings | yes | `test-log-probe-lines.txt` re-read: overhead 148 / 119 B at every B; `summary.txt` write-count steps 400 / 200 |
| 3. Matched row | yes | U4–U10 and all twelve cluster cells pass; C2: ERROR lines exist only for (50, 30), (50, 60), (100, 60), 200 each, each naming its lifetime's F |
| 4. Excluded rows | yes | No rejection in any predicted-accepted case or run; no case or run where an over-F multi batch left rows or bytes |
| 5. Observed vs. inferred | yes | The one inferred statement (no commit-log bytes) is not used by any verdict |
| 6. Deviations and gaps | yes | Defects A1–A4 fixed before the freeze; the two harness bugs found by the shakedowns did not touch the case file; no run-1 defect |
| 7. Core question | yes | Ceiling follows the knob at three values in both tiers with direct disallow evidence (client error and ERROR line per batch); the single-partition bypass is read directly |

### 5.2 Run 2?

**No** — 2026-10-26. Every verdict statement is observed, the self-check settles every part from run 1's files, and the
bypass confirmed is the design's own claim (B1's single-partition exemption), read directly in both tiers.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped: multi-partition batches capped; single-partition batches exempt).

**Claim tested (B1):** for a non-conditional CQL batch spanning two or more partitions, the data the node persists from that
batch follows `batch_size_fail_threshold`: at most F summed `dataSize` is applied in full; above F nothing reaches the memtable,
the commit log or an sstable. A batch on a single partition is not subject to F at all. "Confirmed" below means this claim held.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1, with every single-partition case accepted) | **caps only on some paths (bypass)** — multi-partition batches above 1024·F rejected with 0 rows and 0 memtable bytes at F = 50, 100, 200; single-partition batches up to 209,015 B accepted at F = 50 | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g rows 1 and 3) | **caps only on some paths (bypass)** — disk follows F for multi-partition batches (0 B when over F; 4.1, 12.3 and 24.6 MB when under); `single 30` stores 12.3 MB at F = 50 | run 1 + self-check | 2026-10-26 |

**Positive control:** not required (not a negative-estimate file); the raised-F runs moved usage as required (`multi 30`
12.3 MB at F = 100 and 200; `multi 60` 24.6 MB at F = 200; unit B = 26 accepted at F = 100, B = 60 and 98 at F = 200).

**Feedback filed:** the case file's section D updated (uncommitted); amendments B2a–B2g, B3a–B3g, B4 in the case file
(uncommitted); `_INDEX.md` §4 row `0e9c927f…016a`, §1 Stage 4 column filled. `HANDOFF.md` not edited
(`HANDOFF-ADVISOR.md` §8).
