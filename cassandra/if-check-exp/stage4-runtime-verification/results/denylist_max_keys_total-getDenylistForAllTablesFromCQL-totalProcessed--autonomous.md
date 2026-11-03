# denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous — stage-4 results  <!-- file: results/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.md -->

> **Case:** [`denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous`](../../stage3-ai-deep-read/cases/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps only on some paths (bypass). Cluster: Confirmed — caps only on some paths (bypass).**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/`](../harness/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `e6f222a6…71eb` (schema batch). Frozen after the step-0 audit's fifteen amendments (2026-10-26): sha256 **`61bab98197d593452905523956f5f83d5a766eac291fef540a2e3e286da728f9`**, at which the unit tier's run 1 ran. Runbook fix 1 (the B3f/B3g amendments' ΔLongToken condition, found by the cluster shakedown before cluster run 1; claim, values, `[B` bands and rows unchanged) gave **`a7f6dec7efa369a2facf990ce8c17bb54a63691730194d7addafbc3e2cfdcc2b`**, at which the cluster tier's run 1 ran. Both are new rows in `_INDEX-advisor.md` §2. Section D was filled after the second hash. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/`](../harness/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/): `DenylistTotalCapProbeTest.java` (B2c–B2e as amended), `unit-run.sh`; `make-node-conf.sh` (the sister case's `denylist_max_keys_total-setDenylistMaxKeysTotal-value`, clone, node paths and cluster name changed), `insert_dl.py` (B3c, bundled driver), `cluster-run.sh` (B3e as amended). Not committed. Instrument checks: (i) the test class compiled in the run clone (`BUILD SUCCESSFUL`, [`run1/unit/compile-summary.txt`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/run1/unit/compile-summary.txt)); (ii) a unit shakedown (`DLP_SHAKE=1`: 20 rows and per table 20, T = 1, 30, 10000, phase 2 at T = 15) ran every step ([`shakedown/unit-shake-summary.txt`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/shakedown/unit-shake-summary.txt)); (iii) a cluster shakedown (100 keys per table, P = 100, T = 1, 100, 250, 10000, phase 2 at T = 100, waits 20 s / 30 s) ran every step and exposed defect 1 ([`shakedown/cluster-shake-summary.txt`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/shakedown/cluster-shake-summary.txt)); (iv) `run1/selfcheck.py` was written before any run-1 reading and its parsers were exercised on both shakedowns. Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): ByteOrdered, 4 tables × 200 keys of 1024 B, per table 200; control (flag off, `initialLoad`); phase 1 T = 1, 150, 450, 799, 800, 10000 (refresh 3600 s); phase 2 T = 150 with refresh 1 s and 30 polls. Cluster (B3): one node, 2 GiB heap, `offheap_buffers`, 4 tables × 1000 keys of 32 KiB, per table 1000; a restart per configuration with the knob in the yaml: B0a (denylist off), T = 1, 1000, 2500, 10000, phase 2 (T = 1000, refresh 20 s, two read rounds), B0b (denylist off, drift control). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**What the source says, derived at the audit.**
- *The check* (`PartitionDenylist.java:484`): in `getDenylistForAllTablesFromCQL` (`:463-513`), per table in `SELECT DISTINCT` order, if `total − totalProcessed <= 0` an empty entry and one `Hit limit …` ERROR (`:486`); else `limit = min(P, total − processed)` (`:497`), `getDenylistForTableFromCQL(tid, limit)` reads `LIMIT limit+1` (`:404`) and logs `… exceeded the global allowance of (T)` when more rows than `limit` exist and `limit != P` (`:425`); `totalProcessed += keys.size()` (`:500`). Only the full `load()` (`:222-238`) runs it: startup `initialLoad` (`:132-163`, from `StorageService.java:1349` on every start that finishes joining the ring) and JMX `loadPartitionDenylist` (`StorageProxy.java:3068-3071`).
- *The flag* `partition_denylist_enabled` is read by `initialLoad` (`:134-135`) and `isKeyPermitted` (`:312`) but **not** by `load()`: the filed control "enabled=false must give K = 0" holds only on the startup path.
- *Bypasses*: the timed reload (`refreshAfterWrite`, `:185`; `reload`, `:201-213`), the cache-miss load (`:190-198`) and `refreshTableDenylist` (`:515-528`) read with the per-table limit only (`:388-391`).
- *Heap per key*: the key is the clustering value, read into a new exact-size `byte[]` (`ByteArrayAccessor.java:100-105` via `ClusteringPrefix.java:517`) and wrapped (`:132-136`, `SelectStatement.java:1143`), returned as is by `getBlob` (`UntypedResultSet.java:363-366`): R = B in the unit tier; on the node (Murmur3, `LongToken` without arrays) Δ`[B` = 32,784 B per 32 KiB key.
- *Instruments vs quantities*: every predicted quantity is persistent (the cache holds it until the next load or refresh); the refresh is transient and is read from persistent traces (replaced entry objects, read counts, the READS sampler).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: keys held in the heap cache, a count with a byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: six values incl. 10000; B3b: four values incl. 10000. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: counts plus B and R (bytes held); cluster: live `[B` after a full GC, with the memtable slabs moved off heap so `[B` sees the cache. |
| A. Core question | usage driven to the limit and past it | Met | 800 rows vs T up to 800 and 10000; 4000 rows vs 1, 1000, 2500, 10000. |
| B. Logic | each step says what it establishes | Met | B2e / B3e steps and B2h / B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | Per-table counts, R, ERROR lines per segment; cluster bands widened by the file's own 2 MiB allowance; ΔLongToken made numeric. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Rows had meanings without verdicts; added rows for control, log lines, partial refresh, drift, read errors, setup. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Exact `Hit limit` and `global allowance` lines required for row 1. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Bypass part was not falsifiable without refresh evidence (unit `replaced`/`reloadReads`, cluster READS sampler); cross-restart baseline noise (B0b, offheap memtable slabs). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Control step, poll loop, output location, insert script. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Baseline and phase-2 sampling; `[B` column match. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | Linux paths, `-p pid`, `/tmp` clone mapped to this host. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit 800 KiB; node 125 MiB in a 2 GiB heap, 129 GiB free disk. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `PartitionDenylist.java:92-111`, `:132-238`, `:302-329`, `:396-513`; `Config.java:759-780`; `DatabaseDescriptor.java:4808-4830`; `StorageProxy.java:213`, `:3060-3071`; `StorageService.java:1349`; `QueryProcessor.java:377-392`; `UntypedResultSet.java:363-366`. All match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and runner | Amendment 2026-10-26 (uncommitted) | `/tmp` and Linux paths. |
| 2 | B2c: ByteOrdered order t1..t4; read thresholds stay (200 KiB reads); no early access; schema as in the copied `@BeforeClass` | Amendment 2026-10-26 | Decides B2f; removes confounders. |
| 3 | B2d: `DLP` lines and markers; K, tokens, B, R, entries; `replaced`, `reloadReads`; ERROR texts | Amendment 2026-10-26 | Attribution per T; bypass part needs refresh evidence. |
| 4 | B2e: control on `initialLoad` first; T order; fixed 30-poll loop | Amendment 2026-10-26 | `load()` does not read the flag; open stop condition. |
| 5 | B2f: exact per-table counts, B, R = B, ERROR lines per T and phase 2 | Amendment 2026-10-26 | Derived. |
| 6 | B2g, B2h: verdicts per row; added rows; controls' evidence | Amendment 2026-10-26 | Group B. |
| 7 | B3a: this host; `memtable_allocation_type: offheap_buffers` | Amendment 2026-10-26 | Paths; heap 1 MiB memtable slabs would move `[B` across restarts. |
| 8 | B3c: setup with the denylist off; bundled-driver insert script; row check | Amendment 2026-10-26 | Paths; makes "limit never reached" observable. |
| 9 | B3d: `[B` column match; sampling for baseline and phase 2; B0b drift control; READS sampler; MAT not run | Amendment 2026-10-26 | Open. |
| 10 | B3e: order and scripts; shakedown | Amendment 2026-10-26 | `-p pid`, Linux paths. |
| 11 | B3f: Δ`[B` 32,784 B/key; bands = filed ranges ± 2 MiB; ΔLongToken bands; log lines; drift ≤ 2 MiB; sampler ≥ 4 | Amendment 2026-10-26 | Derived; filed lower bounds left no room for baseline noise. |
| 12 | B3g, B3h, B4: verdicts per row; added rows; controls; host paths | Amendment 2026-10-26 | Group B. |
| 13 | Test the add/remove refresh path and the cache-miss path against the total | Left for stage 3 | B1 names only the timed refresh. |
| 14 | A1/B2h could say that `partition_denylist_enabled` gates `initialLoad` and the access paths but not `load()` | Left for stage 3 (section D) | Found at the audit; not in B1. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (clone 19:39, build 19:39–19:40; audit and freeze to 19:47; compile check 19:47; unit shakedown 19:48; cluster shakedown 19:50–19:59; unit run 1 20:00:53–20:01:31; cluster run 1 20:02:25–20:18:34) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 129 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork, 1 GiB. Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G -XX:+UseG1GC`, read from `JVM Arguments` at each start) |
| Ant | 1.10.18 |
| Python | 3.8.11; the driver bundled in the clone (`lib/cassandra-driver-internal-only-*.zip`) |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run41` (fresh clone, `ant -Dlocal.repository=$W/m2 build-test`, 52 s); `W=~/Library/Caches/stage4`; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-dl41` (data, commit log, hints), wiped before and after each cluster run |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed/` — `clone.log`, `build-test-run41.log`, `unit-compile/`, `unit-shake/`, `unit-r1/` (ant log, JUnit XML, test log, `stdout.txt`, `denylist-lines.txt`, `summary.txt`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`; `setup/`; per start `B0a`, `T1`, `T1000`, `T2500`, `T10000`, `P2`, `B0b`: `node/` logs, `yaml-tail.txt`, `settings.txt`, three `hist-*.txt` (P2: `H0-*`, `H1-*`); P2 also `profileload.txt`, `access.txt`, `tablestats-r{0,1}.txt`, `offset-after-H0.txt`, `segment-after-H0.log`) |

Machine facts relied on (from `environment-advisor.md` and the session brief): all files under `$W` (no `mkdir` in `$HOME`; cqlsh run with `HOME=$W/home`); every `ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run outside the tool sandbox; no `setsid` (node started as a tracked `nohup … -f &` process, pid from `$!`, stopped by drain and `kill <pid>`; the daemon name split in the scripts' patterns); `jstat` not used (class histograms); `[B` matched as the 4th column; the bundled driver with `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off and reconnect-retry; the unit yaml's read thresholds checked (left on: 200 KiB reads); `CQLTester.prepareServer()` without `requireNetwork()` (no network session used); test stdout from `build/test/logs/**/TEST-<class>.log`; no foreground sleep near the tool timeout (long steps in the background, polled); shakedowns before run 1; bounds derived from source; `selfcheck.py` written before readings; with read thresholds on an aborted load leaves an empty entry (here ruled out by size and by the `Error reading` check).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster shakedown, before cluster run 1 | B3f/B3g amendments, ΔLongToken as a row-1 condition | With the denylist off, the instance count of `Murmur3Partitioner$LongToken` was 156 at B0a and 276 at B0b; with each start's K subtracted it ranged 156–266 over the seven starts ([`shakedown/cluster-shake-summary.txt`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/shakedown/cluster-shake-summary.txt), `HIST` lines). The background of `LongToken` objects (decorated keys of system-table partitions each start writes or reads) moves across restarts by about the ±100 band the audit added for T = 1 and T = 1000, so that band cannot separate K from background. | ΔLongToken recorded and compared with its band, no longer a condition of any B3g row; `[B` bands, log lines, rows, settings, drift control, values, claim and rows unchanged. `selfcheck.py` changed accordingly (recorded only). The unit tier (already run) is unaffected. | 2026-10-26 | sha256 `a7f6dec7…cc2b` |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stdout.txt`, `denylist-lines.txt`, `junit-testsuite.txt`, `compile-summary.txt`); [`run1/cluster/`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/run1/cluster/) (`commands.log`, `summary.txt`; `setup/` `insert.txt`, `rows-t*.txt`, `yaml-tail.txt`; per start `settings.txt`, `yaml-tail.txt`, `system-log-lines.txt`, histogram excerpts; `P2/` `profileload.txt`, `access.txt`, `tablestats-localreadcount.txt`, `offset-after-H0.txt`).

### 4.1 Readings

**Unit tier** (ByteOrderedPartitioner; `rows tN=200` for t1…t4; JUnit 1 test, 0 failures, 0 errors; one run)

| Test or assertion | Reading | Predicted (B2f amendment) | Evidence |
|---|---|---|---|
| control (flag off, `initialLoad`) | K = 0, `cacheEntries` = 0, no `Loaded` line in its segment | same | `run1/unit/stdout.txt`, `denylist-lines.txt` |
| T = 1: per table / K / B / R | 1/0/0/0 / 1 / 1,024 / 1,024 | same | `stdout.txt` |
| T = 150 | 150/0/0/0 / 150 / 153,600 / 153,600 | same | `stdout.txt` |
| T = 450 | 200/200/50/0 / 450 / 460,800 / 460,800 | same | `stdout.txt` |
| T = 799 | 200/200/200/199 / 799 / 818,176 / 818,176 | same | `stdout.txt` |
| T = 800 | 200 × 4 / 800 / 819,200 / 819,200 | same | `stdout.txt` |
| T = 10000 | 200 × 4 / 800 / 819,200 / 819,200 | same | `stdout.txt` |
| tokens = keys, `noArray`, entries | equal per table; 0; 4 after every load | same | `stdout.txt` |
| `Hit limit` lines per segment | T = 1: 3 (`Processed 1`, t2, t3, t4); 150: 3 (`Processed 150`); 450: 1 (`Processed 450`, t4); 799, 800, 10000: 0 | same | `denylist-lines.txt` |
| `global allowance` lines | T = 1: t1 (1); 150: t1 (150); 450: t3 (450); 799: t4 (799); 800, 10000: none; no `per-table` line; no `Error reading` line | same | `denylist-lines.txt` |
| phase 2 after load (T = 150, refresh 1 s) | K = 150 (150/0/0/0); 3 `Hit limit … Processed 150` + 1 global (t1, 150); one `Loaded` | same | `stdout.txt`, `denylist-lines.txt` |
| phase 2 polls | K = 800 from poll 1 (2.5 s) to poll 30 (17.2 s) | K reaches 800 within the loop | `stdout.txt` |
| phase 2 end | 200 × 4, K = 800, B = R = 819,200; `replaced=4`; `reloadReads=56`; no denylist line in the poll segment | `replaced=4`, `reloadReads ≥ 4`, no line | `stdout.txt`, `denylist-lines.txt` |

**Cluster tier** (one node, Murmur3; setup: `INS total ok=4000 failed=0 retries=0`, `count` 1000 for t1…t4; settings read back at every start: per table 1000, CL ONE, `file_cache_size` 32MiB, `memtable_allocation_type` offheap_buffers, enabled / total / refresh as configured. Medians of 3 class histograms; Δ against B0a: `[B` 10,685,448 B, `LongToken` 156)

| Start | Observable | Reading | Band / prediction | Evidence |
|---|---|---|---|---|
| B0a (off) | `[B` / log | 10,685,448 B; no `Loaded`, no denylist line | — | `run1/cluster/B0a/` |
| T = 1 | Δ`[B` | **+62,464 B (0.06 MiB)** | \|Δ\| < 2 MiB | `T1/hist-*-excerpt.txt` |
| T = 1 | log lines | 3 `Hit limit` (`Processed 1`: t4, t3, t2), 1 `global allowance of (1)` (t1), one `Loaded` | same | `T1/system-log-lines.txt` |
| T = 1000 | Δ`[B` | **+32,832,928 B (31.31 MiB)** | [29, 38] MiB (derived 31.27) | `T1000/` |
| T = 1000 | log lines | 3 `Hit limit` (`Processed 1000`: t4, t3, t2), no `exceeded`, one `Loaded` | same | `T1000/system-log-lines.txt` |
| T = 2500 | Δ`[B` | **+81,978,392 B (78.18 MiB)** | [76, 92] MiB (derived 78.16) | `T2500/` |
| T = 2500 | log lines | 1 `Hit limit` (`Processed 2500`: t2), 1 `global allowance of (2500)` (t3), one `Loaded` | same | `T2500/system-log-lines.txt` |
| T = 10000 | Δ`[B` | **+131,169,224 B (125.09 MiB)** | [123, 147] MiB (derived 125.06) | `T10000/` |
| T = 10000 | log lines | none; one `Loaded` | same | `T10000/system-log-lines.txt` |
| P2 (T = 1000, refresh 20 s) | H0 Δ`[B` | **+32,822,912 B (31.30 MiB)** | [29, 38] MiB | `P2/H0-*-excerpt.txt` |
| P2 | load log lines | 3 `Hit limit` (`Processed 1000`), no `exceeded`, one `Loaded`; after H0: no denylist line | same | `P2/system-log-lines.txt` |
| P2 | refresh evidence | READS sampler: dl:t1…t4 two reads each (8); 8 reads exit 0; `Local read count` 1 → 27 (recorded) | sampler ≥ 4 | `P2/profileload.txt`, `access.txt` |
| P2 | H1 Δ`[B` | **+131,282,736 B (125.20 MiB)** | [123, 147] MiB | `P2/H1-*-excerpt.txt` |
| B0b (off) | drift `[B`(B0b) − `[B`(B0a) | **+9,096 B** | ≤ 2 MiB | `B0b/` |
| all (recorded, runbook fix 1) | ΔLongToken | T1 +32, T1000 +1,066, T2500 +2,610, T10000 +4,043, H0 +1,078, H1 +4,078 (all inside the bands of the B3f amendment); ΔHeapByteBuffer +85, +1,132, +2,446, +4,080, +1,128, +4,133; `DenylistEntry` 4 after each load, 13 at H1 | recorded | `*/hist-*-excerpt.txt` |

Per key: Δ`[B`/K = 32,833 B (T = 1000), 32,791 B (T = 2500), 32,792 B (T = 10000), 32,821 B (H1); derived 32,784 B. Within each start the three samples differ by at most 4,456 B. Token order of the four `(dl, tN)` partitions on the node, from the log lines: t1, t4, t3, t2.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 1 test, 0 failures, 0 errors [observed: `run1/unit/junit-testsuite.txt`]; `rows tN=200`, per-table getter 200 and refresh 3600 at each phase-1 T, refresh 1 at phase 2 [observed: `stdout.txt`]; no `Error reading` line [observed: `denylist-lines.txt`]. The limit is reached: 800 rows against T < 800 and T = 10000. Valid.
2. **Readings** — nothing unusual. The polls show K = 800 already at the first poll (2.5 s after the load, 1 s refresh), so the rise happened within the first access round [observed: `stdout.txt`].
3. **Matched row** — B2g row 1, "K = min(T, 800) for every T, and B = 1024·K", with the B2f amendment's (i)–(iii): control K = 0; per-table counts, K, B and R = B exactly as derived at all six T; the exact `Hit limit` and `global allowance` lines per segment; and the phase-2 row "K rises to 800" with `replaced=4` and `reloadReads=56`, the phase-2 load lines as predicted and no line in the poll segment [observed: `stdout.txt`, `denylist-lines.txt`].
4. **Excluded rows** — "K > T for some T < 800": K = T at 1, 150, 450, 799 [observed]. "K stays at 800 at T = 150": 150 [observed]. "K at T = 10000 < 800": 800 [observed]. "R ≫ B": R = B [observed]. "Phase 2: K stays at 150": 800 with `replaced=4` [observed]. Added rows: partial refresh — 200 × 4; K > 800 — no; ERROR lines off — exact; control — K = 0; `Error reading` — none; compile/test failure — none [observed].
5. **Observed vs. inferred** — that phase 2's 800 keys come from the per-table reload ignoring the total is inferred from the source (`:206` → `:388-391`); it is supported by the four replaced entry objects, the 56 reads of `partition_denylist` in the poll loop, and the absence of any ERROR line in that segment (a reload with limit = P = 200 against 200 rows exceeds nothing).
6. **Deviations and gaps** — instruments added at the audit (markers, R, refresh evidence); the control runs on `initialLoad` because `load()` does not read the flag. One run (the file asks for one). The add/remove and cache-miss paths are derived, not run.
7. **Core question** — right after a full load the total caps the cache exactly: K and the bytes held follow T (1 → 150 → 450 → 799 → 800 keys; 1 KiB → 819,200 B), the excess is cut first-come in token order with one ERROR per emptied table and one `global allowance` line per partly loaded table, and T = 10000 is bounded only by the per-table cap. After one second of refresh interval, access to the tables reloads each with the per-table cap only and K returns to 800 at T = 150 (5.3× the total). The total caps usage only on the full-load path.

**Conclusion (unit tier):** B2g row 1 with phase-2 "K rises to 800" — **confirmed** (both parts of B1).

**Cluster tier**

1. **Validity** — node up at every start with the 2 GiB G1 heap [observed: `summary.txt` `JVM` lines]; settings read back as configured at all seven starts [observed: `*/settings.txt`]; 4000 rows inserted with no failure and 1000 per table [observed: `setup/insert.txt`, `setup/rows-t*.txt`]; exactly one `Loaded` line at each enabled start and none in B0a/B0b, no `Error reading` line [observed: `*/system-log-lines.txt`]; drift +9,096 B [observed: `B0a/`, `B0b/` excerpts]; all 8 phase-2 reads exit 0 [observed: `P2/access.txt`]. The limit is reached (4000 rows against T = 1, 1000, 2500). Valid.
2. **Readings** — nothing unusual; Δ`[B` per key is within 0.15 % of the derived 32,784 B at every T [observed].
3. **Matched row** — B3g row 1, "Δ[B] tracks min(T, 4000) x 32 KiB within the ranges, and is flat between 10000 and larger T" (as amended: T = 10000 at the 4000-key level), with the B3f amendment's conditions: Δ`[B` 0.06 / 31.31 / 78.18 / 125.09 MiB in their bands; the exact log lines; rows; settings; drift. And the phase-2 row "H1 ≫ H0, about the 10000 level": H0 31.30 MiB, H1 125.20 MiB in [123, 147], sampler 8 dl reads [observed: the files of 4.1].
4. **Excluded rows** — row 2 (Δ1000 ≈ Δ10000): 31.31 vs 125.09 MiB [observed]. Row 3 (Δ10000 ≈ 0): 125.09 MiB [observed]. Row 4 (slope ≫ 32 KiB/key): 32,792–32,833 B/key [observed]. Phase-2 "H1 ≈ H0": 125.20 ≠ 31.30 MiB [observed]. Added rows: drift — 9 KB; rows/settings — as designed; log lines — exact; `Error reading` — none; outside a band — none; H1 between bands — no; node failure — none [observed].
5. **Observed vs. inferred** — that the cache holds exactly the predicted keys is inferred from `[B` (bytes) and supported by ΔLongToken and ΔHeapByteBuffer, which track K (ΔLongToken within 1–8 %, ΔHeapByteBuffer within 14 % of K) [observed, recorded]; that phase 2's growth is the per-table reload is inferred from the source and supported by the sampler's 8 dl reads and no ERROR line after H0.
6. **Deviations and gaps** — `offheap_buffers` instead of the tag's `heap_buffers` (audit, to keep memtable slabs out of `[B`); B0b added; runbook fix 1 (ΔLongToken recorded only; all its readings fell inside the band anyway); MAT not run (not installed; optional). The add/remove and cache-miss paths are not run.
7. **Core question** — on a node started with the knob in the yaml, the startup load keeps min(T, 4000) keys: the live heap above the denylist-off baseline is 0.06 / 31.3 / 78.2 / 125.1 MiB for T = 1 / 1000 / 2500 / 10000, i.e. 32.8 KB per key, with one `Hit limit` ERROR per emptied table. With T = 1000 and a 20-s refresh, two rounds of reads to the four tables reload each with the per-table cap only, and the heap rises from 31.3 to 125.2 MiB — four times the total — and stays there until the next full load.

**Conclusion (cluster tier):** B3g row 1 with phase-2 "H1 ≫ H0" — **confirmed** (both parts of B1 on a node).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/run1/selfcheck.py), written before any run-1 reading and independent of the harness (it re-reads the raw JUnit XML and test log, splitting the log at the `DLP MARK` lines; the raw class histograms, each start's raw `system.log`, the cqlsh settings and count outputs, the insert output, the sampler and access files; and checks that phase 2's after-H0 segment is a verbatim tail of `system.log`): **113 checks, 0 failed** (unit 73, cluster 40); unit row "row 1 + phase 2 K rises to 800 → Confirmed, caps only on some paths (bypass)", cluster row "row 1 + phase 2 H1 at the 10000 level → Confirmed, caps only on some paths (bypass)" ([`run1/selfcheck.out`](denylist_max_keys_total-getDenylistForAllTablesFromCQL-totalProcessed--autonomous/run1/selfcheck.out)). One change after it was written, before cluster run 1 and after unit run 1: ΔLongToken is printed as recorded instead of checked (runbook fix 1). No bound was changed; it was not changed after cluster run 1.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts; rows, settings, `Loaded` lines, drift, access exits from the raw files. |
| 2. Readings | yes | Per-key `[B` re-derived from the raw histograms; sample spread ≤ 4.5 KB. |
| 3. Matched row | yes | Unit: every row-1 and phase-2 check passes. Cluster: bands, log lines per start, rows, settings, drift, sampler. |
| 4. Excluded rows | yes | Each excluded row's reading re-read (K at T < 800, R, phase-2 K; Δ1000 vs Δ10000, slope, H1 vs H0). |
| 5. Observed vs. inferred | yes | The inferred mechanism of the bypass is supported by persistent traces (replaced entries, read counts, sampler), not used alone. |
| 6. Deviations and gaps | yes | Stated; none changes a reading's meaning. |
| 7. Core question | yes | Knob → `limit = min(P, T − processed)` at load → held keys (exact counts, ERRORs) → heap (R = B exactly; node `[B` within 0.15 % per key); then reload with `limit = P` → per-table sum, with the reload shown to have run. |

### 5.2 Run 2?

**No** — decided 2026-10-26. Both tiers rest on exact (unit) or near-exact (node, ≤ 0.15 % per key) readings, observed directly with refresh evidence, and the self-check holds in every part. The bypass confirmed here is documented in the source (`PartitionDenylist.java:74-82`) and was confirmed independently by the sister case `denylist_max_keys_total-setDenylistMaxKeysTotal-value` on the JMX path.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped: the full load caps; refreshes bypass the total).

**Claim tested:** "Right after a full `load()`, the number of denylisted keys in the cache equals `min(denylist_max_keys_total, sum over tables of min(per_table, rows))`. Heap retained by the cache grows linearly with that count, times the key size. Secondary (bypass) claim: once each table entry has been refreshed after `denylist_refresh`, the count rises to `sum over tables of min(per_table, rows)`, whatever the total is." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: K = 1 · 150 · 450 · 799 · 800 · 800 for T = 1 · 150 · 450 · 799 · 800 · 10000 with the derived per-table split, B = R = 1024·K, the exact `Hit limit` and `global allowance` lines, control K = 0; phase 2: K 150 → 800 with all four entries replaced) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (row 1: Δ`[B` = 0.06 / 31.31 / 78.18 / 125.09 MiB for T = 1 / 1000 / 2500 / 10000 at startup load, 32.8 KB per key, exact log lines, drift 9 KB; phase 2: H0 31.30 → H1 125.20 MiB after 8 sampled refresh reads) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted); the fifteen step-0 amendments and runbook fix 1 are in the case file, dated, with the two sha256 values as new rows in `_INDEX-advisor.md` §2; `_INDEX-advisor.md` §1 Stage 4 column updated. The Estimate line is left as filed (it already says positive with the bypass). No section was amended for a refutation (none occurred).
