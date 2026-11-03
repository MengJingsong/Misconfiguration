# bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous — stage-4 results  <!-- file: results/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md -->

> **Case:** [`bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous`](../../stage3-ai-deep-read/cases/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/`](../harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-27, advisor's Mac (`advisor-run`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed `4ffd060f7a3c2e37f930dc914e09b18723d2aa1c1d0cd048ff2b4951cdacb928` (commit `77f1387` holds it as filed). Frozen after the audit's 11 amendments (U1–U5, C1–C6): **`7a71bbb7ac5935baed7e3bdb7044156d4099dc07558bfd559a6a931f2a1f90a7`**; the unit tier ran on this version. After runbook-defect fix D1 (cluster tier only): **`d9feb24d02b07759343bb9da3ace36d7fc1dbd6912dfc3fef253ac717369bc57`**; the cluster tier ran on this version. Both are rows in `_INDEX-advisor.md` §2. Not committed yet (uncommitted working tree on `advisor-run`) |
| **Harness** | `harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/`: `BloomFpChanceSizeTest.java`, `bf-unit.btm`, `bf-node.btm`, `unit-run.sh`, `cluster-run.sh`, `make-node-conf.sh`; `results/.../run1/selfcheck.py`. Not committed yet. Reused tools (with numbers derived again here): `make-node-conf.sh` copied, and the `BA/BC/A/F` Byteman rules and the node mechanics of `cluster-run.sh` and `unit-run.sh` adapted, from `harness/bloom_filter_fp_chance-computeBloomSpec-maxFalsePosProb--autonomous/` (those files were not changed). No value or derivation was taken from another case file or results file |
| **Tiers and values** | Unit: `FilterFactory.getFilter(N, fp)`, N ∈ {1M, 2M} × fp ∈ {0.001, 0.01, 0.1, 0.39, 0.5, 0.9999, 1.0}, two reps (28 cells). Cluster: one node, `keyspace1.standard1` with 2M stress partitions, fp 0.01 (default) → 0.001 → 0.1 → 0.5 → 1.0 → 0.01 by `upgradesstables -a`; ALTER-to-1.0 + restart check; control `ks_ctl` with 4M partitions at 0.01 |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap bit-set bytes and `Filter.db` bytes |
| A | knob varied, ≥ 3 values incl. default | Met | B2b 7 values; B3b 5 values incl. the STCS default 0.01 |
| A | real resource measured, not only the counter | Partly → Met after U3/C2 | Filed: `offHeapSize()`/the gauge plus NMT. NMT cannot see JNA `Native.malloc` (`MemoryUtil.java:81-84`). U3/C2 add observe-only Byteman rules on `MemoryUtil.allocate` / `OffHeapBitSet`. Gap named: whether the OS commits the pages is not observed |
| A | usage driven to the limit and past it | Partly | This is a per-key sizing knob, not a ceiling. The filed design explains that sizes are fixed at construction. "Limit reached" becomes the N check (`totalRows` within ±10%, C5) |
| B | each step says what it establishes | Met | B2g/B3g rows; B2h/B3h controls |
| B | prediction in numbers | Met | B2f exact bytes; B3f MB and ratios. U4 fixes K for fp 0.01 (5, not 6): a derivation error found before any reading; K is used by no verdict row |
| B | every plausible outcome has a row | Partly → Met after U5/C5 | Added rows: invalid conditions, out of band but moving, counter not backed by allocation, step-5 outcomes |
| B | confirmation needs ceiling-follows-knob and direct branch evidence | Partly → Met after C2/C5 | Added: `GF` return-class evidence of the `== 1.0` branch, and no bit set constructed in the 1.0 rewrite |
| B | alternative explanations and controls | Met | N axis / `ks_ctl` (instrument live), reps (determinism), SSTable count, return to 0.01 |
| C | a human can follow it | Met | A3 + B1 |
| C | an AI can run it without re-deriving | Partly → Met after U2/C3 | Exact keys, grid, output lines, sequence, idle and stop conditions |
| C | values, commands, observables exact | Partly → Met after C2/C4 | `du -b` → `stat -f %z`; bands stated |
| D | prerequisites exist or are listed | Met after U1/C1/C6 | `/local` paths replaced by `$W`; tmux replaced by a tracked background process |
| D | workload arithmetic | Met | 2M + 4M rows ≈ 0.9 GB on 118 GiB free; 2 GB heap on 32 GiB |
| D | citations spot-checked | Met | `FilterFactory.java:61-75`, `BloomCalculations.java:44-67,140-173,180-189`, `OffHeapBitSet.java:39-48,139-142`, `BloomFilterSerializer.java:65-69`, `SortedTableWriter.java:445,501`, `FilterComponent.java:43-44,99-144`, `CompactionAwareWriter.java:84,235`, `DefaultCompactionWriter.java:62-65`, `BloomFilterMetrics.java:60-72`, `TableStatsHolder.java:362-367` |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | host paths and build for the unit tier | applied 2026-10-27 | no `/local` on this host |
| U2 | exact keys, grid, reps, output lines | applied 2026-10-27 | runnable without guessing |
| U3 | NMT step replaced by Byteman `MemoryUtil.allocate` / `OffHeapBitSet` in the test JVM | applied 2026-10-27 | NMT is blind to JNA malloc |
| U4 | K for fp 0.01 = 5; exact 2M bytes; serialized = offheap + 8 | applied 2026-10-27 | derivation error, independent of readings |
| U5 | matching rules and verdict words (unit) | applied 2026-10-27 | B2g had no Invalid / Not-confirmed rows |
| C1 | node paths, background start, Byteman `bf-node.btm` | applied 2026-10-27 | host; real-memory and branch instruments |
| C2 | `stat -f %z`; live bit-set bytes (≥ 64 KiB); `GF` lines | applied 2026-10-27 | BSD tools; real-memory reading |
| C3 | exact sequence, up/idle/abort conditions | applied 2026-10-27 | exactness |
| C4 | bands (±10% filed, ratios, exact space = offheap + 8, step 5) | applied 2026-10-27 | bands stated; no predicted value changed |
| C5 | verdict words and added rows (cluster) | applied 2026-10-27 | missing outcomes |
| C6 | cleanup paths | applied 2026-10-27 | host |
| R1 | the A5 doc claim ("about three times") could be corrected in the Cassandra docs | left for stage 3 | out of scope |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 09:53, cluster 09:59–10:04 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), single host, 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 arm64 (T6000) |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Clone commit | `$W/cassandra-run59` (`W=~/Library/Caches/stage4`), `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `cassandra-5.0.9`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 50 s |
| Case-file / harness commit | uncommitted (repo HEAD `77f1387`); case-file sha256 values in §1 |
| Storage | internal SSD, APFS, 118 GiB free; node dir `$W/node-bfgf` (wiped after) |
| Loopback | 127.0.0.1–.3 present (only .1 used) |
| Full logs | `$W/logs/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/` (`unit-shake`, `unit-r1`, `cluster-shake`, `cluster-r1-attempt1` (aborted, D1), `cluster-r1`) |

Machine lessons relied on: workspace `$W` and `env.sh`, every ant call with `-Dlocal.repository=$W/m2`, unsandboxed commands; no setsid, so the
node runs as a tracked background process (`nohup … &; disown`); BSD `stat -f %z` (no `du -b`); NMT does not track JNA `Native.malloc`, so
Byteman on `MemoryUtil.allocate/free` was used; a unit-test JVM option reaches the forked JVM only via `-Dtest.jvm.args`; test stdout is in
`build/test/logs/**/TEST-<class>.log`; `disableautocompaction` does not survive a restart (harmless here: one SSTable); stress keys can
collide (`totalRows` 1,999,966 of 2M, so no exact row count was demanded); `nodetool compactionstats` prints `pending tasks` without a
colon; shakedown before run 1; selfcheck written before the readings and run end to end on the shakedown (exit status checked); the daemon
class name was not used literally in pkill patterns.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | run 1, cluster (attempt 1) | B3e step 2 / C3 "idle" | After `nodetool disableautocompaction`, `pending tasks` stayed at 1 with one SSTable left and no compaction running. `getNextBackgroundTask` returns at `CompactionStrategyManager.java:203` before STCS recomputes `estimatedRemainingTasks` (`SizeTieredCompactionStrategy.java:89`), so the idle wait could never finish. The shakedown (200k keys, fewer flushed SSTables) did not show it. The session aborted the attempt at 09:58, before any sample (`run1/cluster-attempt1/`) | "Idle" = SSTable count 1 and no active task in `compactionstats`, then 5 s. B3f/B3g unchanged | fixed 2026-10-27; cluster tier restarted from the beginning | `d9feb24d…` |

Shakedown note (not a defect): at 200k keys the fp-0.5 bit set (24,872 B) is below C2's 65,536-byte counting threshold, so `C-real F0.5`
failed in the cluster shakedown (74/75). At run-1 scale the smallest filter is 246,544 B, as C2 anticipated.

## 4. Run 1

**Command logs:** `bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/TEST-org.apache.cassandra.utils.BloomFpChanceSizeTest.log`, `run1/unit/summary.txt`). `ant` exit 0; 28 `BFP` lines; `END cells=28`; 48 `BMBF` lines. Both reps are identical.

| fp | class | K | offheap N=1M | offheap N=2M | serialized | Byteman malloc on the test thread (1M / 2M) |
|---|---|---|---|---|---|---|
| 0.001 | BloomFilter | 7 | 1,875,008 | 3,750,008 | offheap + 8 | 1,875,008 / 3,750,008 |
| 0.01 | BloomFilter | 5 | 1,250,008 | 2,500,008 | offheap + 8 | 1,250,008 / 2,500,008 |
| 0.1 | BloomFilter | 3 | 625,008 | 1,250,008 | offheap + 8 | 625,008 / 1,250,008 |
| 0.39 | BloomFilter | 1 | 375,008 | 750,008 | offheap + 8 | 375,008 / 750,008 |
| 0.5 | BloomFilter | 2 | 125,008 | 250,008 | offheap + 8 | 125,008 / 250,008 |
| 0.9999 | BloomFilter | 2 | 125,008 | 250,008 | offheap + 8 | 125,008 / 250,008 |
| 1.0 | AlwaysPresentFilter | – | 0 | 0 | 0 | none / none |

**Cluster tier** (`run1/cluster/<sample>/tablestats.txt`, `filter-files.txt`, `sstablemetadata-excerpt.txt`, `node/node.out`, `node/node2.out`, `summary.txt`). Every sample shows 1 SSTable, format `big` (`nb-`). Stress: 2,000,000 writes, 0 errors; `totalRows` 1,999,966. Every rewrite was sized from the HLL estimate 1,972,278 (`GF` lines). `ks_ctl`: 4,000,000 writes, `totalRows` 3,999,917, estimate 3,967,638. system.log has 0 `ERROR` lines.

| Sample | fp (read back) | Off-heap gauge | Space used | Filter.db (files / bytes) | Live bit-set bytes (Byteman) | Off-heap / B3f value | Ratio to R0 |
|---|---|---|---|---|---|---|---|
| R0 | 0.01 | 2,465,352 | 2,465,360 | 1 / 2,465,360 | 2,465,352 | 0.9861 | 1 |
| F0.001 | 0.001 | 3,698,024 | 3,698,032 | 1 / 3,698,032 | 3,698,024 | 0.9861 | 1.50000 |
| F0.1 | 0.1 | 1,232,680 | 1,232,688 | 1 / 1,232,688 | 1,232,680 | 0.9861 | 0.50000 |
| F0.5 | 0.5 | 246,544 | 246,552 | 1 / 246,552 | 246,544 | 0.9861 | 0.10000 |
| F1.0 | 1 | 0 | 0 | 0 / 0 | 0 | — | 0 |
| F0.01 | 0.01 | 2,465,352 | 2,465,360 | 1 / 2,465,360 | 2,465,352 | 0.9861 | 1 |
| S5a (ALTER 1.0, no rewrite) | 1 | 2,465,352 | 2,465,360 | 1 / 2,465,360 | 2,465,352 | — | — |
| S5b (after restart) | 1 | 0 | 0 | 1 / 2,465,360 | 0 | — | — |
| CTRL `ks_ctl` | 0.01 | 4,959,552 | 4,959,560 | 1 / 4,959,560 | 4,959,552 | 0.9919 | 2.0117 |

Branch evidence (`node/node.out`): one `GF` line per rewrite. `BMBF GF 1972278 1.0 AlwaysPresentFilter` (line 1023), with no bit set
≥ 64 KiB constructed in that window; every other rewrite returned `BloomFilter` and constructed exactly one bit set of the gauge's size.
Each reading equals `ceil((1,972,278·b + 20)/64)·8` for b = 10/15/5/1, e.g. b = 10 gives 2,465,352.

### 4.2 Conclusion and logic

1. **Validity.** Unit: all 28 cells printed, `END cells=28`, Byteman live [observed: `run1/unit/TEST-…log`]. Cluster: `totalRows`
   1,999,966 and 3,999,917, both within ±10% [observed: `sstablemetadata-excerpt.txt`]; SSTable count 1 and read-back fp equal to the set
   value at every sample [observed: `tablestats.txt`, `readback-*.txt`]; no step aborted in the restarted tier [observed: `summary.txt`].
   The first cluster attempt was aborted for D1 before any sample; it is not used. Valid.
2. **Readings.** All non-1.0 cluster readings are 0.9861 of the B3f value because the filter is sized from the HLL estimate (1,972,278),
   not the 2M keys, as A3 step 1 notes [observed: `GF` lines; inferred: `CompactionAwareWriter.java:84` gives the key count]. No outliers.
   `pending tasks 1` persisted throughout (D1) [observed: `commands.log`].
3. **Matched rows.** Unit, B2g row 1 "sizes match the table, 0 at 1.0", with row 3 "0.9999 gives non-zero, 1.0 gives 0" [observed: unit
   table, exact equality in 28/28 cells, and the U3 reading equals `offheap` in all 24 BloomFilter cells]. Cluster, B3g row 1 "off-heap
   tracks the predicted ratios, 0 at 1.0" [observed: every C4 band, ratios 1.5/0.5/0.1 exact to 5 digits, `F1.0` = 0 with no
   `Filter.db`, live bit-set bytes equal to the gauge, and `GF` → `AlwaysPresentFilter` at 1.0].
4. **Excluded rows.** Unit row 2 / row 5 (Refuted): offheap differs across fp at fixed N (1,875,008 … 125,008). Unit Not confirmed: no
   cell differs and malloc equals offheap. Cluster row 2 (Refuted): readings span 0.1–1.5 × R0, not flat. Row 4 (0.5 = 0.1): 246,544 vs
   1,232,680. Row 3 (Not confirmed, control flat): CTRL = 2.01 × R0. Row 6 (ratio ~3): F0.01/F0.1 = 2.0000. Live vs gauge: equal at
   every sample.
5. **Inferred statements the conclusion depends on.** (a) The Byteman `MemoryUtil.allocate` size is the native memory the filter takes.
   It is the malloc request; page commit is not observed (named gap, U3). (b) The 1.4% shortfall against B3f comes from the HLL key
   estimate, shown by the `GF` numElements argument (1,972,278) and the exact formula match.
6. **Deviations and gaps.** D1 (idle condition) was fixed and the tier restarted. The optional NMT step was replaced (U3). RSS and NMT
   are recorded for information only. The first B3d "Bloom filter space used ≈ off-heap + header" holds exactly (+8 per SSTable).
7. **Core question.** Usage follows the knob: at fixed N the bit set takes b(fp) bits per key, 15/10/5/3/1 for fp
   0.001/0.01/0.1/0.39/≥0.393, measured as malloc bytes and the gauge (parts 3, 5a). At fp = 1.0 the `FilterFactory.java:63` branch
   returns `AlwaysPresent` and nothing is allocated or written (parts 3, 4). It is a per-key sizing control: total usage still grows with
   the partition count (`ks_ctl` doubles at the same fp; part 3). So the knob caps bits per key, not total bytes.

**Conclusion (one line):** unit B2g row 1 (+ row 3) — confirmed; cluster B3g row 1 — confirmed. Step 5: the load-time `AlwaysPresent` path is confirmed (unchanged before restart, 0 after, `Filter.db` still on disk).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw test log, the per-sample `tablestats.txt` / `filter-files.txt` / `sstablemetadata.txt` /
read-backs and `node.out` byte ranges. It re-implements `computeBloomSpec` and the bit-set sizing on its own and judges against
B2f/U4 and B3f/C4. **Unit 89/89 pass, exit 0** (`run1/selfcheck-unit.out`); **cluster 82/82 pass, exit 0** (`run1/selfcheck-cluster.out`).
Shakedown runs: unit 89/89 exit 0; cluster 74/75 exit 1 (scale artefact, §3).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `sstablemetadata.txt` totalRows 1,999,966 / 3,999,917; `tablestats.txt` SSTable count 1 in 9/9 samples; read-backs match |
| 2. Readings | yes | `GF` lines show numElements 1,972,278 in all 5 rewrites; `tablestats` "Number of partitions (estimate)" is the same |
| 3. Matched row | yes | Re-read `F0.5/tablestats.txt` (246,544 / 246,552), `F1.0/filter-files.txt` (empty), `S5b/filter-files.txt` (one 2,465,360-B file) |
| 4. Excluded rows | yes | Ratios computed from the raw gauges; CTRL/R0 2.0117; F0.01/F0.1 2.0000 |
| 5. Observed vs inferred | yes | (a) is the named gap of U3; (b) is checked by the exact formula with the logged numElements |
| 6. Deviations and gaps | yes | D1 recorded with source cause; the aborted attempt is kept in `run1/cluster-attempt1/` |
| 7. Core question | yes | Logic follows B1: per-key size follows b(fp), 0 at 1.0, branch evidence direct |

### 5.2 Run 2?

**No** (2026-10-27). The conclusion rests on observed exact equalities in both tiers. The only inferred statement (malloc request = memory
held) is a named instrument gap that a second run with the same instruments would not settle. The result neither refutes the case nor
confirms a bypass.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** for a fixed number of partition keys N in an SSTable, the Bloom filter's off-heap bytes (and `Filter.db` size) equal
`ceil((N·b(fp)+20)/64)·8` with b(0.001)=15, b(0.01)=10, b(0.1)=5, b(0.5)=1, and are 0 when fp = 1.0; so off-heap usage follows
`bloom_filter_fp_chance`.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1, row 3) | caps (per key: b(fp) bits/key; 0 at 1.0) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row 1; step 5 also confirmed) | caps (per key; total grows with partitions) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** case file section D updated (2026-10-27, uncommitted). No section amended by the result; the audit amendments
U1–U5, C1–C6 and the defect fix D1 are in the case file. `_INDEX-advisor.md` §1 Stage 4 column and the §2 rows were filled.
