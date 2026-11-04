# prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous — stage-4 results  <!-- file: results/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.md -->

> **Case:** [`prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous`](../../stage3-ai-deep-read/cases/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps** (B2g row 1). **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1 together with row 3: the cache's retained heap R stays below C and follows it; the whole-JVM live heap grows a further ≈ 14.2 MiB per 20,000 distinct PREPAREs whatever C is, held by the `system.prepared_statements` memtable). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/`](../harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> This session knew the sibling results of `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous`
> before the audit; the verdict is against this file's own predictions and conclusions only.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `c21b718` (sha256 `e650167c…1d61`). Frozen after the step-0 audit's sixteen amendments (2026-10-26, after the harness shakedown and before any run-1 reading): sha256 **`7363f6beb8d9bf2d46b355c56e01d7516e5d5a9c540f6ace59c69fabf6657d2d`** (new row in `_INDEX.md` §4; `run1/freeze.txt`). No runbook fix during run 1, so both tiers ran at this version. Not committed (no commit was asked for). |
| **Harness** | [`../harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/`](../harness/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/): `PreparedCacheCapProbeTest.java` (B2c's text; one line changed by amendment B2c), `unit-run.sh`; `prep.py` (bundled-driver client), `pscache.btm` (Byteman read/clear trigger, amendment B3d), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order and the C_ctl calibration). Instrument checks before run 1: `pscache.btm` type-checked with Byteman `TestScript` (`audit/btm-check.txt`: `TestScript: no errors`); the probe compiled against the run clone (`audit/probe-compile.txt`, rc 0); the Ant `unless` behaviour checked with a two-target build file (`audit/antcheck.txt`); shakedown of both harnesses at parameters not used in run 1 (unit 1 MiB, n = 200; cluster 4 MiB, 2,000 statements, control mode, 5 s wait; `shakedown/`), not evidence. Self-check: [`run1/selfcheck.py`](prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/run1/selfcheck.py), written before run 1 and tested on the shakedown files. |
| **Tiers and values** | Unit (B2): one `ant testsome` JVM per value, C ∈ {1 MiB, 4 MiB, auto = 10 MiB, 64 MiB (non-binding control)}, n = 3,000 distinct 20-column SELECTs prepared with no keyspace. Cluster (B3): one node, `-Xmx2G`, C ∈ {4 MiB, 32 MiB, auto = 10 MiB} with N = 20,000 distinct PREPAREs each, then the control at C_ctl = 236 MiB with N_ctl = 20,000 (computed from the 4 MiB run), sampled at N_ctl/2 and N_ctl. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: heap; the operand is the Caffeine weight `key.size() + pstmntSize`, `pstmntSize = measureDeep(prepared)` (`QueryProcessor.java:947-958`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Unit had 1/4 MiB and an optional 64 MiB; cluster 4/32 MiB and a control. The default (auto, `DatabaseDescriptor.java:795-798`) was in neither. Auto added to both; 64 MiB made required (amendments B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit reads only the weight (named in B2d). Cluster's direct measure was a MAT retained size; MAT is not on this host, so R = live bytes before − after an in-place clear of the cache, with a noise control R0 (amendment B3d). |
| A. Core question | usage driven to the limit and past it | Met | Unit n = 3,000 against ≤ 10 MiB at w ≥ 1 KiB (B2c arithmetic, rerun rule); cluster 20,000 statements against ≤ 32 MiB. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry what they show. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "about", "linearly" and the Prepared comparator had no exact form (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Missing: counter not following the cache, not proportional to C, failed control, WARN missing, Prepared held outside the cache, R's resolution. Added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Ceiling ∝ C plus evictions counted by the removal listener (`QueryProcessor.java:132-139`) and the per-minute WARN (`:120-126`). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: non-binding control, wipe between runs, no keyspace, forced GC; R0 added (amendment B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Paths, the `-Dprobe.n` route, the observable file, the order (amendments B2a–B2e, B3a, B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The test prints with `printf` (split lines in the test log); the C_ctl arithmetic in bytes; the control's halves "by editing the file" (amendments B2c, B3b, B3c). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | Four steps could not run as written here: `/local` paths; GNU `sed -i`; **`-Dno-build-test=false` skips building the probe** (Ant skips an `unless` target when the property is set to any value; `audit/antcheck.txt`); `PYTHONPATH=<driver zip>` cannot import `cassandra` (the package sits under `cassandra-driver-3.29.0/` in the zip). Fixed before the freeze (amendments B2a, B2e, B3a, B3c). |
| D. Runnable | workload arithmetic reaches the limit | Met | 3,000 × ≥ 1 KiB vs 1–10 MiB; 20,000 statements vs 4–32 MiB; 2 GiB heap holds the control's ≈ 120 MiB of weight; 137 GiB free disk. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `~/cassandra-src` at `cassandra-5.0.9`: `QueryProcessor.java:97, 107, 113-140, 147, 181, 208-213, 425-469, 728-779, 815-833, 947-958`, `QueryHandler.java:63`, `CQLMetrics.java:33-48`, `CQLMetricsTable.java:34-35, 67-68`, `SystemKeyspace.java:1874-1885`, `test/conf/cassandra.yaml:48`, `build.xml:94, 1013, 1153, 1159, 1192`. One mismatch, not load-bearing: A2 says `MD5Digest.size()` is 16; it is 16 + 4 (`MD5Digest.java:117-121`); the probe computes it. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and build | Amendment 2026-10-26 | Paths do not exist. |
| 2 | B2b: auto added; 64 MiB required | Amendment 2026-10-26 | Group A default. |
| 3 | B2c: one `println` per reading; `-Dprobe.n` via `-Dtest.jvm.args`; rerun rule also for auto | Amendment 2026-10-26 | Split log lines; a plain `-D` does not reach the forked JVM. |
| 4 | B2d: observable file | Amendment 2026-10-26 | Stdout lands in `build/test/logs`. |
| 5 | B2e: BSD `sed`; drop `-Dno-build-test=false`; order | Amendment 2026-10-26 | As written the probe never compiles. |
| 6 | B2f: auto ratio band; "linearly" exact | Amendment 2026-10-26 | Tolerances. |
| 7 | B2g: three rows | Amendment 2026-10-26 | Group B. |
| 8 | B3a: this host; Byteman agent; readiness | Amendment 2026-10-26 | Paths; instrument. |
| 9 | B3b: auto added; read-back; C_ctl arithmetic in bytes | Amendment 2026-10-26 | Group A; restart-only knob. |
| 10 | B3c: driver import, policies, retries, range arguments, schema call, trigger call | Amendment 2026-10-26 | Import fails as written; host lessons. |
| 11 | B3d: R and R0 instead of MAT; D recorded | Amendment 2026-10-26 | No MAT here. |
| 12 | B3e: order, waits, no heap dumps | Amendment 2026-10-26 | Baseline after the schema; instrument. |
| 13 | B3f: auto band; R ≤ C; Prepared bound against `I_end`; heap from the histogram total; control interval | Amendment 2026-10-26 | Exact forms; the heap_info instrument failed the shakedown known-answer check (§3 note). |
| 14 | B3g: R rows, row 1/row 3 combination and Effect rule, six rows | Amendment 2026-10-26 | Group B. |
| 15 | B3h: R0 control | Amendment 2026-10-26 | Instrument noise. |
| 16 | B4: this host | Amendment 2026-10-26 | Paths, clean clone. |
| 17 | A2: `MD5Digest.size()` is 20, not 16 | Left for stage 3 | Not load-bearing. |
| 18 | A4 lists `system.prepared_statements` as a disk consumer only; until a flush it is a heap memtable that grows per distinct statement | Left for stage 3 (and section D) | Found by run 1, not needed for a valid run. |
| 19 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Group B wording. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 12:46–12:47 EDT; cluster 12:47–13:01 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 137 GiB free at start; loopback 127.0.0.1–.3 present (one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run and after it (§8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forks (`maxmemory=1024m`). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), Byteman 4.0.20 agent (`listener:true`, `pscache.btm`) |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; driver bundled in the clone, `cassandra-driver-internal-only-3.29.0.zip`, protocol 5 |
| Local `cassandra-src` clone commit | `$W/cassandra-run30` = `~/Library/Caches/stage4/cassandra-run30`, fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`; `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` in 59 s |
| Case-file commit / harness commit | filed `c21b718`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-pscs/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/` — `clone-build-run30.log`, `antcheck/`, `checks/`, `shakedown/` (not evidence), `freeze.txt`, `unit/` (`ant-*.log`, `TEST-*.log`, `TEST-*.xml`, `probe-*.txt`, `commands.log`, `summary.txt`), `cluster/{k4,k32,kauto,ctl}/` (`node.out` with the `PSCACHE` lines, `system.log`, `samples.csv`, `histo-*.txt` full class histograms, `heapinfo-*.txt`, `summary.txt`, `commands.log`), `cluster/chain.out` |

**Machine facts relied on** (`environment-advisor.md` and earlier runs on this host): no `mkdir` in `$HOME` outside `$W`; `ant` needs `-Dlocal.repository=$W/m2`; no `setsid`, so the node runs as a tracked background `bin/cassandra -f`; `jstat` cannot attach, so heap is read with `jcmd GC.class_histogram`; the test JVM logs each `System.out` write as its own line (amendment B2c); the bundled driver with `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, `idle_heartbeat_interval=0` and reconnect-on-error (ENOBUFS on loopback; no retry was needed in run 1); Byteman rules type-checked with `TestScript` before use; the daemon pattern in the harness is split so the script's own command line never matches it; long steps ran in the background and were polled.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit (before any reading) | B2e step 2 | `-Dno-build-test=false` makes Ant skip `maybe-build-test` (`build.xml:1013`, `unless="no-build-test"`): Ant skips an `unless` target when the property is set to any value. Checked with a two-target build file (`audit/antcheck.txt`: with `-Dno-build-test=false` the guarded target did not run). The copied probe would never be compiled | flag dropped (amendment B2e) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3c | `PYTHONPATH=<driver zip>` cannot import `cassandra`: the zip holds the package under `cassandra-driver-3.29.0/` | import from inside the zip (amendment B3c) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B2a/B2e/B3a | `/local` paths, `--depth 1` network clone, GNU `sed -i` do not exist / fail on this host | this host's paths and BSD `sed` (amendments B2a, B2e, B3a) | 2026-10-26, before the freeze | uncommitted |
| A4 | audit | B3d | Eclipse MAT not installed (`run1/stepE.txt`) | R and R0 (amendment B3d) | 2026-10-26, before the freeze | uncommitted |

None during run 1: both tiers ran at the frozen version without a stop.

**Shakedown note (instrument check, not a reading of run 1):** the cluster shakedown (4 MiB, 2,000 statements, 680 resident) showed `GC.heap_info` used after `GC.run` + 5 s falling from 63.7 MB to 56.0 MB while the histogram live total rose by 8.4 MB and R was 3.5 MB (`shakedown/cluster-sd-k4-summary.txt`). It failed the known-answer check, so before the freeze the heap-increase relations were read from the histogram live total and heap_info kept as a record only (amendment B3f (4)). In run 1 the two agree within 0.2 MiB in the capped runs (`selfcheck.out`).

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/run1/unit/commands.log`, `prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/run1/cluster/<label>/commands.log`, `prepared_statements_cache_size-getSizeOfPreparedStatementForCache-pstmntSize--autonomous/run1/cluster/chain.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/probe-k*-n3000.txt`, `junit-TEST-*.txt`, `summary.txt`; one JVM per row; every `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`; no `IllegalStateException`, no `InvalidRequestException`; the rerun rule did not trigger)

| C | cap read back (B) | weight per statement (maxW) | first eviction at sample | max over samples of sumWeight − cap − maxW (≤ 0 predicted) | final resident | final sumWeight | evicted | resident + evicted | ratio to 1 MiB |
|---|---|---|---|---|---|---|---|---|---|
| 1 MiB | 1,048,576 | 6,204 | i = 200 | −6,304 | 169 | 1,048,476 | 2,831 | 3,000 | 1 |
| 4 MiB | 4,194,304 | 6,204 | i = 700 | −6,604 | 676 | 4,193,904 | 2,324 | 3,000 | 4.000 |
| auto | 10,485,760 | 6,204 | i = 1,700 | −7,204 | 1,690 | 10,484,760 | 1,310 | 3,000 | 10.000 |
| 64 MiB (control) | 67,108,864 | 6,204 | none | — | 3,000 (= i at all 30 samples) | 18,612,000 | 0 | 3,000 | — |

At 64 MiB `sumWeight / i` = 6,204.0 at every sample (spread 0 %).

**Cluster tier** (`run1/cluster/<label>/summary.txt`, `samples.csv`, `pscache-lines.txt`, `histo-*-lines.txt`, `discard-warnings.txt`, `readback-line.txt`; one node lifetime per row; 20,000 PREPAREs in 9.1–9.4 s (the control 5.3 + 4.3 s), 0 retries, 0 failures in every run). Heap figures are live totals of `jcmd GC.class_histogram`, in MiB.

| Value | Observable | Reading | Evidence |
|---|---|---|---|
| 4 MiB | read-back / count / evicted | `… with 4 MiB`; final count 679, evicted 19,321 (sum 20,000); Byteman count at end 679 | `k4/` |
| 4 MiB | Prepared / internal | `Prepared` 29 → 710; `I` 29 → 31; across the clear 710 → 31 | `k4/histo-*-lines.txt`, `pscache-lines.txt` |
| 4 MiB | R / R0 / heap | R = 3.518 MiB (R/C 0.879); R0 = −0.301 MiB; increase 17.98 MiB; left after the clear 14.68 MiB | `k4/histo-*-lines.txt` |
| 4 MiB | WARN / memtable | 1 line, `19321 prepared statements discarded … (4 MiB)`; `AtomicBTreePartition` and `BTreeRow` +20,001 | `k4/discard-warnings.txt`, `histo-2-end-lines.txt` |
| 32 MiB | count / evicted | `… with 32 MiB`; 5,436 / 14,564 (20,000); Byteman 5,436 | `k32/` |
| 32 MiB | Prepared / R / heap | 29 → 5,467 (`I` 29 → 31); R = 29.720 MiB (R/C 0.929), R0 = −0.385; increase 43.79; left after the clear 14.37 | `k32/` |
| 32 MiB | WARN / memtable | 1 line, `14564 … (32 MiB)`; partitions and rows +20,001 | `k32/` |
| auto | count / evicted | `… with 10 MiB`; 1,698 / 18,302 (20,000); Byteman 1,698 | `kauto/` |
| auto | Prepared / R / heap | 29 → 1,729 (`I` 29 → 31); R = 9.129 MiB (R/C 0.913), R0 = −0.217; increase 23.30; left after the clear 14.38 | `kauto/` |
| auto | WARN / memtable | 1 line, `18302 … (10 MiB)`; partitions and rows +20,001 | `kauto/` |
| control, 236 MiB, N_ctl 20,000 | calibration | w̄ = 4,194,304 / 679 = 6,177.2 B; N_ctl = min(20,000, 50,925) = 20,000; C_ctl = ⌈235.6⌉ = 236 MiB | `chain.out` |
| control | count / evicted | 10,000 / 0 at the half; 20,000 / 0 at the end (every sample evicted 0); no WARN | `ctl/samples.csv`, `discard-warnings.txt` |
| control | Prepared / heap | 29 → 10,030 (half) → 20,030 (end), `I` 29 → 30; live total +62.90 MiB at the half, +123.96 MiB at the end (ratio 1.971); R = 109.94 MiB (0.933 × N_ctl·w̄); left after the clear 14.23; partitions +10,001 at the half, +20,001 at the end | `ctl/` |

Derived (recomputed by `selfcheck.py`): count(32)/count(4) = 8.006; count(auto)/count(4) = 2.501; D = live(32) − live(4) at the end = 25.71 MiB (no prediction). Heap increase − R = 14.47 · 14.07 · 14.17 MiB at 4 · 32 · 10 MiB and 14.02 MiB in the uncapped control. `GC.heap_info` used (record only): +18.12 · +43.93 · +23.42 MiB.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit/probe-*.txt`, `yaml-diff-*.txt`] the cap read back as set in every JVM (1/4/10/64 MiB × 2^20); only the yaml line differed between JVMs; the limit was passed at all three capped values (evictions 1,310–2,831); the 64 MiB control met all three frozen conditions. Valid.
2. **Readings** — every statement weighs exactly 6,204 B, so the resident counts are exactly ⌊C/6,204⌋ (169, 676, 1,690). Nothing unusual.
3. **Matched row** — B2g row 1, "`sumWeight ≤ cap + maxW` at all samples, evictions > 0, resident scales with C" [observed: sumWeight never above the cap (max excess −6,304 to −7,204 B against cap + maxW); evicted 2,831 / 2,324 / 1,310; ratios 4.000 and 10.000 inside [3, 5] and [7.5, 12.5]; resident + evicted = 3,000 exactly; control as frozen].
4. **Excluded rows** — "sumWeight > cap + maxW": never. "evicted 0 at 1 MiB": 2,831. `IllegalStateException` (`:954`) and `InvalidRequestException` (`:825`): 0 hits in the test logs. Added rows: counter follows the cache (sum = n); ratios inside their bands; control not failed.
5. **Observed vs. inferred** — all observed.
6. **Deviations and gaps** — none in run 1. The unit tier reads the weight, not the retained heap (gap named in B2d).
7. **Core question** — the summed weight of the cache follows the knob exactly (⌊C/w⌋ entries at three values, ratios 4 and 10) and never exceeds it; the excess is evicted and counted. The `:954` guard never fired: every insert path measured `pstmntSize`.

**Unit tier conclusion:** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — [observed: `*/readback-line.txt`, `samples.csv`, `chain.out`] read-backs 4/32/10/236 MiB; the cap was passed at every capped value (evicted 14,564–19,321); the control's C_ctl/N_ctl recomputed from the 4 MiB count match; same heap flags and yaml except the knob (`yaml-diff.txt`, `jvmargs-excerpt.txt`); 0 client failures; R0 within ±0.39 MiB (|R0| = 0.301 MiB ≤ C/10 = 0.4 MiB at 4 MiB). Valid.
2. **Readings** — the whole-JVM live heap grows more than C + 5 MiB at every capped value (17.98 / 43.79 / 23.30 MiB), while R stays below C. The part not freed by clearing the cache is 14.2–14.7 MiB in every lifetime, the uncapped control included.
3. **Matched rows** — B3g row 1, "Retained cache heap ≤ C, evictions = N − count, count scales with C, control grows linearly" [observed: R/C = 0.879 / 0.929 / 0.913; count + evicted = 20,000 in each; ratios 8.006 and 2.501 inside [6, 10] and [1.875, 3.125]; Prepared within [count, count + I_end] (710 ≤ 679 + 31; 5,467 ≤ 5,436 + 31; 1,729 ≤ 1,698 + 31); one WARN each with the right MiB; control: evicted 0, count 20,000, Prepared +20,001 within [20,000, 20,001], heap ratio 1.971 within [1.6, 2.4], no WARN]; **and** B3g row 3, "Heap increase ≫ C but the cache ≤ C: the cap holds for the cache; growth comes from other consumers; record which" [observed: increase > C + 5 MiB at 4, 32 and 10 MiB; R < C; the remainder after clearing the cache is 14.68 / 14.37 / 14.38 / 14.23 MiB at 4 / 32 / 10 / 236 MiB; `AtomicBTreePartition` and `BTreeRow` +20,001 in every main lifetime and +10,001 at the control's half].
4. **Excluded rows** — "R > C": R ≤ 0.93 C at every value. "evicted = 0 at 4 MiB": 19,321. "Control heap flat": +62.90 → +123.96 MiB. Added rows: counter follows the cache; proportional; Prepared not held outside the cache and internal map (after the clear only the internal ones remain: 31, 31, 31, 30); WARN present; control passed; R resolves the smallest cap.
5. **Observed vs. inferred** — [inferred: from the class counts and the source] the ≈ 14.2 MiB not freed with the cache is the memtable of `system.prepared_statements`: each new cache insert writes one row keyed by the statement id (`QueryProcessor.java:831-833`, `SystemKeyspace.java:1874-1879`), an eviction adds a deletion to that partition (`:1882-1885`) rather than removing it, and the partition and row counts rise by exactly one per distinct statement (+10,001 at 10,000, +20,001 at 20,000) whatever C is; `probe.wide` receives no writes. The table holding those partitions was not read directly (no `nodetool tablestats` was taken). [inferred: definition of R] R is the heap retained by the cache's entries because clearing them frees exactly what only they hold, and `Prepared` instances drop to `I_end` across the clear.
6. **Deviations and gaps** — no heap dump or MAT: R stands in for the retained size (amendment B3d), read to ±0.4 MiB. The memtable was not flushed in a run this short, so its later move to disk was not observed. B3f's "heap increase ≤ C + 5 MiB" did not hold; under the frozen B3g amendment this selects row 3 together with row 1 and is not a refutation of B1, which is about the cache's retained heap.
7. **Core question** — the cache's retained heap follows the constraint and stays under it (R = 0.88–0.93 × C at three values, entries 1 : 2.5 : 8, the excess evicted and reported), and with a cap that does not bind the same workload retains ≈ 110 MiB. The knob does not bound all heap a flood of distinct PREPAREs uses: the persisted-statement memtable grows by ≈ 0.74 KB per distinct statement whatever the knob.

**Cluster tier conclusion:** B3g row 1 — **confirmed for the cache**; B3g row 3 — **other consumer recorded** (`system.prepared_statements` memtable), Effect "caps only on some paths (bypass)" by the frozen rule of the B3g amendment.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (written before run 1, separately from the harness; re-reads the raw `TEST-*.log`/`.xml`, each lifetime's `system.log`, `node.out`, `samples.csv`, full `histo-*.txt` and `heapinfo-*.txt` under the full-log root): **71 checks, 71 HOLD, 0 FAIL**, exit 0 (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | cap per JVM and read-back per lifetime from `system.log`; 30 PROBE lines per JVM; junit counts; PSCACHE sequences complete (7 per main lifetime, 8 for the control); C_ctl/N_ctl recomputed; R0 bound. |
| 2. Readings | yes | sumWeight checked at every sample after the first eviction; histogram totals and `Prepared` lines read from the full histograms; heap_info read and reported as a record. |
| 3. Matched row | yes | B2f and B3f relations tested against their frozen tolerances; row 3's trigger (increase > C + 5 MiB) reported per run as INFO with the class growth. |
| 4. Excluded rows | yes | every B2g/B3g row, including the added ones, addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | the memtable attribution rests on the class counts (+20,001 per main run, +10,001 at the control's half, re-read from `histo-*.txt`) and is labelled inferred; the verdict's "caps" for the cache does not depend on it, and the bypass rests on the observed remainder after the clear (14.2–14.7 MiB, constant over a 59× range of C). |
| 6. Deviations and gaps | yes | no MAT; no flush; heap_info not used for a bound (decided before the freeze). |
| 7. Core question — the steps follow the audited logic | yes | knob read back → evictions and WARN → count ∝ C → R ≤ C → Prepared bound → control moves heap, in B3e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-26). Every load-bearing figure (counts, evictions, read-backs, R, instance counts, warnings) is observed and recomputed by the self-check; the one inferred statement names the holder of the non-cache growth and is supported by exact class counts; the same pattern was measured independently for the sibling cases with different instruments.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** with `prepared_statements_cache_size = C`, preparing many distinct statements keeps (unit) the sum of `16 + pstmntSize` over resident cache entries at or below C, give or take at most one entry, and (cluster) the heap the cache retains after a full GC at or below C, while evictions grow as N − resident; with a cap large enough not to bind, the same workload grows retained heap roughly linearly in N. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1: sumWeight ≤ cap at every sample, resident ⌊C/6,204⌋ = 169 · 676 · 1,690 (ratios 4.000, 10.000), evicted = n − resident, 64 MiB control evicted 0 with sumWeight = 6,204 × i | caps | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1 with row 3: R = 0.879 · 0.929 · 0.913 × C at 4 · 32 · 10 MiB (R0 within ±0.39 MiB), count 679 · 5,436 · 1,698 (1 : 8.006 : 2.501), count + evicted = 20,000, `Prepared` ≤ count + `I_end`, one discard WARN each; control at 236 MiB: 20,000 resident, 0 evicted, heap +62.90 → +123.96 MiB, R = 109.94 MiB. The live heap also grows ≈ 14.2 MiB per 20,000 distinct statements whatever C is (`system.prepared_statements` memtable, +1 partition per distinct statement) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted). No section of the case was amended after run 1. Recommendations for stage 3, left unapplied: (1) A4 lists `system.prepared_statements` as a disk consumer only; until a flush it is an on-heap memtable that grows by one partition per distinct statement and is not bounded by the knob; (2) A2's `MD5Digest.size()` is 20 B, not 16; (3) B2e's `-Dno-build-test=false` skips building the probe on Ant 1.10 (it was fixed by amendment before the freeze).

**End of run:** no `CassandraDaemon` and no test JVM running, ports 7000/7199/9042/9091 free, `$W/node-pscs` wiped, `test/conf/cassandra.yaml` restored and the probe removed from `$W/cassandra-run30` (`git status` clean) — checked 2026-10-26 13:02 EDT.
