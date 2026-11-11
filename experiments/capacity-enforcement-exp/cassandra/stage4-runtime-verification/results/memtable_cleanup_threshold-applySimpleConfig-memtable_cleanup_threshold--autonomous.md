# memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous — stage-4 results  <!-- file: results/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md -->

> **Case:** [`memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous`](../../stage3-ai-deep-read/cases/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — does not cap. Cluster: Confirmed (B3g row 1b) — does not cap.**
>
> **Outcome class:** undetermined — the stage-3 estimate (`undetermined`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/`](../harness/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `09178ab0…dcc5`). Frozen after the step-0 audit's eleven amendments (2026-10-24, before any reading): sha256 **`d556e7d30d87fff606daf972e0f7c98426b57b3b53e4973e377cedec88065e41`**, a new row in `_INDEX.md` §4. The amendments are not committed (no commit was asked for). No runbook fix was needed; both tiers ran at this version. |
| **Harness** | [`../harness/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/`](../harness/memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/): `CleanupThresholdTest.java`, `CleanupThresholdLowTest.java`, `CleanupThresholdHighTest.java`, `CleanupThresholdConfigTest.java`, `unit-run.sh` (unit); `Sampler.java`, `cluster-run.sh`, `cluster-chain.sh`, `summarize.py` (cluster). Not committed. Checks before run 1: the four test classes compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, log `$W/logs/memtable_cleanup_threshold-applySimpleConfig/instrument-compile.log`); `Sampler.java` compiled by `javac` at the start of each cluster run; a **shakedown** of the cluster harness (t = 0.33, 20,000 + 60,000 partitions, and a 0.005 start) found two harness defects, fixed before run 1 (§3); its readings are not used. Each cluster run cross-checks the sampler's `BlockedOnAllocation` against a `nodetool sjk mx` read at the end (equal in all four, §5). |
| **Tiers and values** | Unit (B2): pool scenarios t ∈ {0.11, 0.33, 0.5, 0.9} at a 16 MiB heap pool; control t = 0.99 with limit `Long.MAX_VALUE`; config path 0.005, 0.995 and (control) 0.5, each in its own JVM. Cluster (B3): `memtable_cleanup_threshold` ∈ {0.11, 0.33, 0.6} at `memtable_heap_space: 256MiB`, `heap_buffers`, `memtable_flush_writers: 2`, phase 1 (fixed 5,000 op/s) then phase 2 (128 threads); C4 positive control 128 MiB, t = 0.11, phase 2 only; startup with 0.005. 0.33 stands for the default (1/(1+2) = 0.333…). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: memtable pool bytes (`SubPool.used()` against `reclaiming + limit × t`). The knob is a ratio; the bytes it governs are `t × memtable_heap_space`. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b four values; B3b 0.11 / 0.33 / 0.6, where 0.33 is the default 1/(1+2) to within 0.003, below the two-decimal resolution of the `Used total` log field (`DatabaseDescriptor.java:761-764`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | The pool's own `used` is read from the `Flushing largest` lines (amendment B3d); JVM heap used is sampled but mixes garbage and other users, so no row rests on it (named gap). |
| A. Core question | usage driven to the limit and past it | Met | B3c ≈ 2 GB of values per phase against a 256 MiB pool; B2c offers 2× the limit (after amendment; as written the writer stopped exactly at the limit). |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f "within one 1 MiB slab region" and B3f "≈ t ± 0.05", "approaches 256 MiB" made exact (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | B2g had three rows, B3g three; no row for "flushing never lagged", partial tolerance, hard limit exceeded, control failure, startup case. Added (amendments B2g, B3g). Both "usage follows the threshold" (phase 1) and "usage passes the threshold when flushing lags" (phase 2) now have rows with their controls. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | For a trigger the "disallow" is the cleaner firing: unit row 1 needs the first invocation inside (T, T + 1 MiB] and the writer `WAITING` at exactly the limit; cluster row 1 needs ≥ 90 % of lines with `Used − flushing ≥ t − 0.01` and `MEMTABLE_LIMIT` flushes (C2). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B3h had the 128 MiB repeat without t or expected values and an undefined "not commit-log driven"; C1–C4 defined (amendment B3h). Unit: config control 0.5 added (B2h) to tie the entry to the live pool. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Initialisation order and JVM split (B2a), writer size and pacing (B2c), phases and log cutting (B3d), stop conditions (B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | 1 s `nodetool` cadence not achievable (sampler, B3d); startup-failure definition (B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Clone, build, test classes; mapped to this machine (§2). |
| D. Runnable | workload arithmetic reaches the limit | Met | 2,000,000 × 5 × 200 B ≈ 2 GB per phase; phase 1 ≈ 400 s at 5,000 op/s; ≈ 4.4 GB on disk per run against 153 GiB free; 2 GiB heap on 32 GiB RAM. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `DatabaseDescriptor.java:753-775`, `AbstractAllocatorMemtable.java:59,78-110,249-300`, `MemtablePool.java:125-161`, `MemtableCleanerThread.java:73-97` match. Errors: B3d/B3f treat `AllMemtablesOnHeapDataSize` as pool usage, but it counts only current memtables (`TableMetrics.java:506-512,876-883`), so phase 2's predicted rise to 256 MiB cannot appear in it; B2c's "up to 16 MiB" equals the limit, which `tryAllocate` admits, so the writer would never block. Both corrected (amendments B3d/B3f, B2c). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B1: say "usage" is pool usage and "up to the hard limit" means bounded by it | Amendment 2026-10-24 (uncommitted) | B3f and B3g read it differently. |
| 2 | B2a: `daemonInitialization` first; config cases in separate JVMs | Amendment 2026-10-24 | `MEMORY_POOL` class init; once per JVM. |
| 3 | B2c/B2e: offer 2× the limit; pace 50 µs; readings at 3 s | Amendment 2026-10-24 | As written the block could not occur; cleaner on its own thread. |
| 4 | B2f: exact T and intervals | Amendment 2026-10-24 | Approximate. |
| 5 | B2g: six rows | Amendment 2026-10-24 | Audit group B. |
| 6 | B2h: control sizes; config control 0.5 → `MEMORY_POOL` | Amendment 2026-10-24 | Nothing tied the entry to the pool. |
| 7 | B3d: gauge scope; `Used total`/`flushing`/`live`; sampler; phase cutting; read-backs | Amendment 2026-10-24 | Citation error; cadence; undefined phases. |
| 8 | B3e: order, waits, startup-failure definition | Amendment 2026-10-24 | Open. |
| 9 | B3f: relations (i)–(vii) | Amendment 2026-10-24 | Approximate; phase-2 sentence on an observable that cannot show it. |
| 10 | B3g: nine rows | Amendment 2026-10-24 | Missing outcomes. |
| 11 | B3h: C1–C4 with expected values | Amendment 2026-10-24 | Undefined. |
| 12 | A continuous reading of `MEMORY_POOL.onHeap.used()` (no MBean exists; `Used total` is printed only when the cleaner fires) | Left for stage 3 | Would need a patched build or an agent. |
| 13 | B3a: `HEAP_NEWSIZE` has no effect under G1 | Left for stage 3 | Harmless. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit 22:56–22:57 EDT; cluster 23:01–23:29 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 153 GiB free at start; loopback 127.0.0.1–.3 present (one node used, 127.0.0.1); ports 7000/7199/9042/9091 free before and after |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVMs: junit forks with the build's JDK 11 test flags. Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`) |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `$W/cassandra-run8` = `~/Library/Caches/stage4/cassandra-run8`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` |
| Case-file commit / harness commit | filed `f361777`; amendments and harness uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-mct/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each run; ≈ 4.1 GB data per run; default `conf/cassandra.yaml` otherwise (SkipList memtable, `concurrent_compactors` default) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/memtable_cleanup_threshold-applySimpleConfig/` — `clone-build-run8.log`, `instrument-compile.log`, `unit/` (ant logs, JUnit XML, `stage4.out`), `shakedown/` (not evidence), `cluster/{k011,k033,k060,ctl-hs128,startfail-0005}/` (`system.log`, `gc.log*`, `stress-p1.log`, `stress-p2.log`, `samples.csv`, `markers.txt`, `flush-lines-p*.txt`, `node.out`, `commands.log`, `summary.txt`), `cluster/chain.out` |

## 3. Runbook defects

None in the case file. Harness defects found by the shakedown (before run 1, harness only, §9a unchanged):

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| H1 | shakedown | B3e startup with 0.005 | `cluster-run.sh` exited in `startfail` mode before writing `summary.txt` | call `summarize.py` in that branch | 2026-10-24 |
| H2 | shakedown | B3e startup with 0.005 | the message grep also matched the `Node configuration` line (it contains `memtable_cleanup_threshold=`), burying the exception | exclude that line | 2026-10-24 |

Note: `cluster-chain.sh`'s final line printed `WARNING: CassandraDaemon left`. It was a false positive: its `ps -eo command | grep '[C]assandraDaemon'` matched the command line of this session's concurrent wait loop (which contains that text). `pgrep -f org.apache.cassandra.service.CassandraDaemon` was empty right after, every run's own stop check logged `no CassandraDaemon left` and `no cassandra-stress left`, and the ports were free (`run1/cluster/*/commands.log`).

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command log:** `memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/run1/unit/{commands.log,summary.txt,stage4.out}`; `run1/cluster/<run>/{commands.log,summary.txt,config-readback.txt,markers.txt,samples.csv,flush-lines-p1-keyspace1.txt,flush-lines-p2-keyspace1.txt,stress-p*-results.txt,sjk-blocked-end.txt,yaml-overrides.txt}`; `run1/cluster/startfail-0005/{commands.log,startfail.txt,node-out-tail.txt,summary.txt}`; `run1/cluster/chain.out`.

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; JUnit 2 + 1 + 1 + 1 tests, 0 failures, `run1/unit/summary.txt`)

| Scenario | T (B2f) | `used` at first cleaner invocation | Writer at 3 s | Evidence |
|---|---|---|---|---|
| t = 0.11 | 1,845,493 | **1,847,296** (= T + 1,803; the first 4,096-multiple above T, 451 calls) | `WAITING`, 4,096 calls, `used` 16,777,216 | `stage4.out` |
| t = 0.33 | 5,536,481 | **5,537,792** (T + 1,311) | `WAITING`, 4,096, 16,777,216 | same |
| t = 0.5 | 8,388,608 | **8,392,704** (T + 4,096) | `WAITING`, 4,096, 16,777,216 | same |
| t = 0.9 | 15,099,494 | **15,101,952** (T + 2,458) | `WAITING`, 4,096, 16,777,216 | same |
| control t = 0.99, limit `Long.MAX_VALUE` | 9.13 × 10^18 | no invocation | `TERMINATED`, 8,192 calls, `used` 33,554,432 | same |
| config 0.005 | — | `ConfigurationException`: `memtable_cleanup_threshold must be >= 0.01, but was 0.005` | — | same |
| config 0.995 | — | `ConfigurationException`: `memtable_cleanup_threshold must be <= 0.99, but was 0.995` | — | same |
| config control 0.5 | — | initialised; `getMemtableCleanupThreshold()` 0.5; `MEMORY_POOL` `SlabPool`, `onHeap/offHeap.cleanThreshold` 0.5 | — | same |

Cleaner invocations by 3 s: 7.3–7.7 × 10^7 per scenario (the cleaner loop re-fires while `used > T`; no prediction). Every blocked writer ended `stopped:UncheckedInterruptedException` on interrupt.

**Cluster tier** (`memtable_heap_space` 256 MiB unless stated; lines = `Flushing largest` lines of `keyspace1.standard1`; `Used total`, `flushing`, `live` are the on-heap ratios printed in them)

| Value | Phase | Observable | Reading | Evidence (file) |
|---|---|---|---|---|
| all | — | C1 read-back | `Node configuration`: `memtable_cleanup_threshold=0.11 / 0.33 / 0.6 / 0.11`, `memtable_heap_space=256MiB` (128MiB in C4), `memtable_flush_writers=2`, `memtable_allocation_type=heap_buffers`; deprecation warning in each | `cluster/<run>/config-readback.txt` |
| all | each | C3 stress | 2,000,000 partitions, 0 errors in all seven phases; phase 1 4,989–4,993 op/s (6 min 40 s); phase 2 79.9–82.3k op/s (24–25 s); C4 69.8k op/s | `stress-p*-results.txt` |
| all | each | C2 flush reasons of the table | only `MEMTABLE_LIMIT`; `Enqueuing … MEMTABLE_LIMIT` count = line count in every phase; `COMMITLOG_DIRTY` 0, `MEMTABLE_PERIOD_EXPIRED` 0 | `flush-lines-p*-keyspace1.txt`, `summary.txt` |
| 0.11 | 1 | lines; `Used total` median (min–max) | 130; **0.110** (0.11–0.33); `Used − flushing ≥ 0.10` in 130/130 | `k011/flush-lines-p1-keyspace1.txt` |
| 0.33 | 1 | same | 43; **0.330** (0.33–0.33); 43/43 | `k033/…` |
| 0.6 | 1 | same | 23; **0.600** (0.60–0.60); 23/23 | `k060/…` |
| 0.11 / 0.33 / 0.6 | 1 | gauge median / peak (420–421 samples at 1 s) | **14.71 / 40.22 / 78.72 MiB**; peaks 28.13 / 84.30 / 153.43 MiB | `<run>/samples.csv` |
| 0.11 | 2 | lines; `Used total` max and its line | 133; **max 0.76** (`flushing` 0.65, `live` 0.11; 194.6 MiB); median 0.22; 80 lines with `Used ≥ 0.21` and `flushing ≥ 0.10` | `k011/flush-lines-p2-keyspace1.txt` |
| 0.33 | 2 | same | 43; max **0.66** (`flushing` 0.33, `live` 0.33; 169.0 MiB) | `k033/…` |
| 0.6 | 2 | same | 24; max **0.60** (`flushing` 0.00 at every line) | `k060/…` |
| 0.11 / 0.33 / 0.6 | 2 | `BlockedOnAllocation` during phase 2 | 0 / 0 / **160** (sampler = `nodetool sjk`) | `samples.csv`, `sjk-blocked-end.txt` |
| 0.11 / 0.33 / 0.6 | 2 | `live` max over lines; gauge peak | 0.11 / 0.33 / 0.60; 27.64 / 80.33 / 138.07 MiB | `flush-lines-p2-keyspace1.txt`, `samples.csv` |
| 0.11 / 0.33 / 0.6 | 1 + 2 | `PendingFlushTasks` max | 6 / 1 / 1 | `samples.csv` |
| C4: 128 MiB, 0.11 | 2 | lines; `Used total` max; `flushing` max; blocked | 252; **1.00** (128.0 MiB), 51 lines ≥ 0.90; `flushing` max 0.89; `BlockedOnAllocation` **1,807**; `PendingFlushTasks` max 8 | `ctl-hs128/…` |
| C4 | 2 | "halves the peak": C4 pool peak / t = 0.11 phase-2 pool peak | 128.0 / 194.6 = **0.658** (no prediction: t = 0.11 did not meet (vii)) | same, `k011/…` |
| 0.005 | start | startup | daemon exited ≈ 4 s after launch (rc 3); `node.out` and `system.log`: `memtable_cleanup_threshold must be >= 0.01, but was 0.005` | `startfail-0005/startfail.txt`, `commands.log` |
| all | — | node health | no `OutOfMemoryError`; full GCs 0 / 1 / 3 / 0 (k011 / k033 / k060 / C4) | `summary.txt`; `gc.log*` (outside repo) |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — four JVMs, 5 tests, no failures [observed: `run1/unit/summary.txt`]; every pool scenario reached the limit (4,096 calls, `used` 16,777,216) [observed: `stage4.out`]. Valid.
2. **Readings** — each first-invocation reading is exactly the first 4,096-byte multiple above T [observed: `stage4.out`; recomputed in `selfcheck.out`].
3. **Matched row** — B2g row 1 "trigger at ≈ t·limit, block at limit for all t", with the amended requirements: first invocation in (T, T + 1 MiB] for all four t (excess 1,311–4,096 B), writer `WAITING` at exactly 16 MiB in all four, both config cases throw the stated messages, controls as stated [observed: `stage4.out`].
4. **Excluded rows** — "writer blocks at ≈ t·limit": blocks at 16 MiB for every t [observed]. "Trigger independent of t": 1.85 / 5.54 / 8.39 / 15.10 MB [observed]. Added rows: no first invocation ≤ T; none above T + 1 MiB; every scenario had invocations; every writer `WAITING`; config cases threw; control (i) 0 invocations, 8,192 calls, `TERMINATED`; control (ii) `MEMORY_POOL` thresholds 0.5 [observed].
5. **Observed vs. inferred** — none load-bearing.
6. **Deviations and gaps** — the pool scenarios bypass the config path; the 0.5 control covers that link.
7. **Core question** — the cleaner fires at the first allocation past `limit × t`, following t over 0.11–0.9, and the writer is stopped only by the hard limit, whatever t is.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — C1: each run's `Node configuration` shows the intended t, heap space, two flush writers and `heap_buffers`, with the deprecation warning [observed: `config-readback.txt`]. C3: 2,000,000 partitions, 0 errors in each phase [observed: `stress-p*-results.txt`]. C2: every flush of the table was `MEMTABLE_LIMIT`, none `COMMITLOG_DIRTY` or periodic [observed: `flush-lines-p*-keyspace1.txt`]. ≥ 23 phase-1 lines per run; no OOM [observed: `summary.txt`]. C4 held (below). Valid.
2. **Readings** — at t = 0.6 writers blocked 160 times in phase 2 although no line shows `Used total` above 0.60 [observed: `k060/samples.csv`, `flush-lines-p2-keyspace1.txt`]. [inferred: once one 0.60 memtable is switched out, the next trigger point is `reclaiming + 0.6 × limit` ≥ 1.2 × limit (`MemtablePool.java:134-142`), so the cleaner cannot fire again before that flush completes, and the new memtable fills the remaining 0.40 to the limit; `Used total` is printed only when the cleaner fires (`AbstractAllocatorMemtable.java:285-295`), so lines miss that peak.] At t = 0.11 phase 1 two lines show `flushing` 0.22 at moderate load [observed]; (ii) still holds for them.
3. **Matched row** — B3g **row 1b**: "as row 1, but (vii) fails for some t — Confirmed for B1; B3f (vii) not met". Phase 1 follows t: medians 0.110 / 0.330 / 0.600, all within t ± 0.05 (i) and strictly ordered (iii); 100 % of lines with `Used − flushing ≥ t − 0.01` (ii); gauge medians 14.71 < 40.22 < 78.72 MiB, peaks ≤ 256 MiB (iv) [observed]. Phase 2 passes the threshold: at t = 0.11, `Used total` 0.76 with `flushing` 0.65 (80 qualifying lines) (v) [observed: `k011/flush-lines-p2-keyspace1.txt`]. Hard limit held: max `Used total` 0.76 / 0.66 / 0.60 and 1.00 in C4, all ≤ 1.02 (vi) [observed]. (vii) holds at 0.6 (blocked 160) and fails at 0.11 (max 0.76, blocked 0) and 0.33 (max 0.66, blocked 0) [observed]. C1–C4 hold.
4. **Excluded rows** — Row 1: (vii) fails at 0.11 and 0.33 [observed]. Row 2 (no lag at 0.11): 80 lines with `flushing` ≥ 0.10 [observed]. Row 3 (threshold caps while flushing): `Used total` reached 0.76 > 0.16 on lines with `flushing` ≥ 0.10 [observed]. Row 4 (medians not ordered): ordered [observed]. Row 5 (tolerance): (i) and (ii) hold for all t [observed]. Row 6 (> 1.02): none [observed]. Row 7 (C1–C3, < 3 lines, OOM): none [observed]. Row 8 (C4 fails): C4 `Used total` ≤ 1.00 [observed]. Row 9 (0.005 starts): it exited with the stated message [observed: `startfail.txt`].
5. **Observed vs. inferred** — the explanation of the t = 0.6 block (part 2) is inferred and not needed by the matched row (row 1b uses only the observed blocked count for (vii)). That the pool's peak lies between cleaner firings, so `Used total` maxima are lower bounds on the pool's peak, is inferred from the source; it affects only (vii), which already counts blocked allocations as the alternative evidence.
6. **Deviations and gaps** — (i) pool usage is seen only at cleaner firings (no MBean for `MEMORY_POOL.onHeap.used()`); between firings it is unobserved except through `BlockedOnAllocation`. (ii) Heap used (sampled, max 1,280–1,592 MiB of 2,048 MiB) is not a memtable reading; no row rests on it. (iii) C4 ran phase 2 on a fresh node without phase 1, unlike the main runs (as amended). (iv) Full GCs: 1 at 0.33 and 3 at 0.6 (none at 0.11 or C4), no OOM; they do not affect any row. (v) The gauge, as corrected in B3d, peaked near `t × 256 MiB` in phase 2 too (27.6 / 80.3 / 138.1 MiB), i.e. the current memtable stayed at the threshold while the excess was in memtables being flushed.
7. **Core question** — under moderate load the pool's usage at each flush sat exactly at the threshold (0.11, 0.33, 0.60 of 256 MiB), so held memtable memory follows the knob; when flushing lagged, usage passed it (0.76 at t = 0.11, all of it beyond `live` in memtables being flushed), and only `memtable_heap_space` bounded it (1.00 and 1,807 blocked allocations at 128 MiB). The threshold is a flush trigger, not a cap.

**Conclusion (cluster tier):** B3g row 1b — **confirmed** (B1 held; the B3f (vii) sub-prediction "approaches 256 MiB for all t" was not met at 0.11 and 0.33).

## 5. Self-check of run 1 — AI

Script: [`run1/selfcheck.py`](memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/run1/selfcheck.py), run as `python3 -I selfcheck.py ~/Library/Caches/stage4/logs/memtable_cleanup_threshold-applySimpleConfig`. It re-reads `stage4.out` and the JUnit XML, recomputes T in float32, and for the cluster re-cuts the **full** `system.log` of each run at the byte offsets in `markers.txt` (not the harness's flush excerpts), re-parses the `Node configuration` line, `samples.csv`, the stress logs, the `sjk` read and `node.out`. Output: [`run1/selfcheck.out`](memtable_cleanup_threshold-applySimpleConfig-memtable_cleanup_threshold--autonomous/run1/selfcheck.out) — **78 checks hold, 0 do not hold**; the (vii) and C4-ratio lines are informational.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit XML counts; config read-back from each `system.log`; 2,000,000 / 0 in each stress log; no `COMMITLOG_DIRTY`/periodic flush and `MEMTABLE_LIMIT` = lines in each phase; no OOM. |
| 2. Readings | yes | The t = 0.6 blocked count 160 is in both the sampler and `sjk`; its explanation is marked inferred. |
| 3. Matched row | yes | (i)–(vi) recomputed from the raw log; (vii) recomputed: fails at 0.11 (0.76, blocked 0) and 0.33 (0.66, 0), holds at 0.6 (blocked 160) → row 1b, not row 1. |
| 4. Excluded rows | yes | Row 3's condition re-evaluated: lines with `flushing` ≥ 0.10 exist and not all have `Used ≤ 0.16`. Startup 0.005: exited, message present. |
| 5. Observed vs. inferred | yes | The two inferred statements are named and the matched row does not need them. |
| 6. Deviations and gaps | yes | Full-GC counts re-read by hand (`grep -c 'Pause Full' gc.log*`, not in `selfcheck.py`; outside the repo); C4 phase-2-only per the amendment. |
| 7. Core question | yes | Uses only parts 1–4. |

### 5.2 Run 2?

**No** — 2026-10-24. Every self-check part holds; the result neither refutes the file nor confirms a bypass, and the matched rows rest on observed readings.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** undetermined.

**Claim tested (B1, with the amendment's reading):** the cleaner first fires when the pool's used bytes exceed `threshold × limit` (± one allocation), so under moderate write load memtable usage scales with the threshold; under write load exceeding flush throughput, pool usage rises above `threshold × limit`, bounded by the hard limit (`memtable_heap_space`) — the threshold does not cap. Values outside [0.01, 0.99] fail startup.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 — **Confirmed** (first cleaner invocation at the first allocation past `limit × t` for t = 0.11 / 0.33 / 0.5 / 0.9; writer blocked only at the 16 MiB limit for every t; 0.005 and 0.995 rejected with the stated messages; 0.5 reaches `MEMORY_POOL`) | does not cap | run 1 + self-check | 2026-10-24 |
| Cluster | B3g row 1b — **Confirmed** (phase-1 `Used total` medians 0.110 / 0.330 / 0.600 for t = 0.11 / 0.33 / 0.6; phase 2 at t = 0.11 reached 0.76 with 0.65 flushing; ≤ 1.00 everywhere, C4 at 128 MiB 1.00 with 1,807 blocked allocations; 0.005 fails startup; sub-prediction "approaches 256 MiB for all t" met only at 0.6) | does not cap | run 1 + self-check | 2026-10-24 |

**Positive control:** C4 (`memtable_heap_space: 128MiB`, t = 0.11, phase 2): the same workload and instruments show a binding cap — `Used total` 1.00 (128.0 MiB), 51 lines ≥ 0.90, 1,807 blocked allocations.

**Feedback filed:** the case file's section D (uncommitted); the eleven amendments of 2026-10-24 in the case file; `_INDEX.md` §1 Stage 4 column, §2 a new sha256 row, §3 coverage line. Notes for stage 3, not applied: the `AllMemtables*DataSize` gauges cannot show usage above the threshold (they omit flushing memtables); at t > 0.5 the cleaner cannot fire again while one flush is in progress (`reclaiming + t × limit` > limit), so writers block at the hard limit with the log showing only `Used total` = t; `Used total` is printed only when the cleaner fires and so understates the pool's peak.
