# max_shard_split-getnumshards-count--autonomous — stage-4 results  <!-- file: results/max_shard_split-getnumshards-count--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max_shard_split-getnumshards-count--autonomous`](../../stage3-ai-deep-read/cases/max_shard_split-getnumshards-count--autonomous.md)
>
> **Status:** verdict filed 2026-10-28 — unit Confirmed (does not cap; overflow bypass for base >= 2048), cluster Not confirmed (positive control did not bind); no run 2
>
> **Outcome class:** undetermined (stage-3 estimate `negative`; unit effect `does not cap`, cluster effect `undetermined`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before run 1 and before any run-1 reading: `41ebd4fadfccfa2f68171b80b41bdfa2c078c926c657b826bac054fcd91547d6`. File committed at `b68711e5` (HEAD); the amendments of 2026-10-28 are uncommitted. After run 1, section D (stage-4 feedback) was filled; claim, predictions and rows unchanged: final sha256 `3b5b9e7569cc435463f7ca3837af6006e995f1ab5f559a80d76b23f0aac4cd68`. |
| **Harness** | `harness/max_shard_split-getnumshards-count--autonomous/` (uncommitted; README there) |
| **Tiers and values** | Unit: `getNumShards` over `sstable_growth` {0, 0.333, 1} x target {1 MiB, 1 GiB} x base {1, 4, 2047, 2048, 4096} x 11 densities (K/4 ... +Inf, NaN, 0), `min_sstable_size` control, `BoundaryTracker` retained heap at 4 / 1024 / 2^20 shards. Cluster: one node, table `ks.t` (UCS), Config A (target 1 MiB, growth 0, base 1) dense and control arms, Config B (target 1 GiB, growth 0.333) dense and control arms, positive control `max_sstables_to_compact` 4 vs 32. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-28 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Partly | The constant clamps a count of shards (A2), not bytes; the claim is that bytes of heap and disk do not follow it, and B2/B3 measure those bytes (tracker heap, `Space used`, post-GC heap). |
| A | knob varied (>= 3 values incl. default) or other approach | Met | Hard-coded (A1): the clamp is crossed by varying the density through `target_sstable_size`, `base_shard_count` and the data, in three growth modes. |
| A | real resource measured | Met | Tracker heap (unit); post-GC heap, `Space used`, `du` and sstable counts (cluster); RSS in the sampler. |
| A | driven to the limit and past it | Partly -> Met | Unit sweeps density across the knee K. The cluster tier as filed could not reach the clamp (R1): amended to a Murmur3 key window. |
| A | positive control (negative claim) | Met | Unit: the `min_sstable_size` branch moves the shard count; cluster: `max_sstables_to_compact` 4 vs 32 (B3h) and the control arm. |
| B | steps establish; prediction numeric; rows for every outcome; disallow evidence | Partly -> Met | Numbers and rows are explicit. B3f's "default target 1 GiB: shard count stays near 1 in both arms" depended on the (wrong) density assumption; amended with arithmetic only (R2). |
| B | alternatives and controls | Met | NaN, 0 and Inf cells, growth 1 as a fixed-count control, repeated calls for state. |
| C | human / AI can follow; values exact | Partly -> Met | B3c's BOP key recipe is replaced by an exact key generator and value size (amendment). |
| D | harness exists | Met | Written in step 1 (`ShardCapProbeTest`, `KeyGen`, `cluster-run.py`, `workload.py`, selfcheck); `~/s4-ms` on `pc39`. |
| D | workload reaches the limit | Met | Dense-arm density about 8.8e12 B against K = 7.8e11 B; 512 MiB per arm; 53 GB free. |
| D | citations | Partly -> Met | `Controller.java:139-141, 169, 264-343`, `ShardManager.java:42, 147-165`, `ShardManagerNoDisks.java:104-121`, `UnifiedCompactionStrategy.java:272-274`, `UnifiedCompactionTask.java:57-58` match. A5 wrongly says no upstream test asserts the clamp (`ControllerTest.java:290-292` etc. do, for base 3): amended. `ByteOrderedPartitioner` has no splitter, which the filed B3a missed (R1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Replace `ByteOrderedPartitioner` by Murmur3 and a key search (window 2^-14, 16 KiB values) | Applied (B3b amendment, 2026-10-28) | BOP has no splitter, so `ShardManagerTrivial` gives span 1 and density = bytes; the clamp was unreachable |
| R2 | B3f default-target sentence: dense arm about 2^9, control 1, clamp not reached | Applied (B3f amendment, arithmetic only) | Follows from R1's density |
| R3 | A5 test-coverage sentence | Applied (A5, dated) | Source shows the assertions |
| R4 | Tracker heap by retained-heap delta (JOL not on the classpath); `null` cfs; `daemonInitialization()` | Applied (B2e amendment) | Group C |
| R5 | Repeat every cluster arm once more for noise (B3h) | Left for stage 3 | Recorded as a deviation in §4.2 part 6 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-28 |
| Node | `pc39` (`node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores |
| OS / kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-ms` (`copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `b68711e5`, `ant build-test`; the probe test is copied into this copy's `test/unit/`) |
| Case-file / harness commit | `b68711e5` with the uncommitted amendments (sha256 in §1) / uncommitted |
| Node data | local disk `~/stage4-tmp/ms/node` (removed afterwards; `/` had 53 GB free) |
| Full logs | `pc39:~/stage4-logs/ms/` (`run1/`, `shake/`) |

**Instrument checks before run 1** (readings, not run 1): the unit probe was run once in full (`shake1.log`: 330 cells, tracker heap) and the cluster script twice with 2 batches instead of 8 (`shake/sh1`, `sh2`). They showed that the dense key window reaches the clamp (a logged shard count of 1,048,576), that `TRUNCATE` snapshots inflated `du` (harness: `auto_snapshot: false`), and that a background compaction can be running when a snapshot is taken (harness: wait for idle). The case file's predictions were not edited after these readings; the one prediction amendment (B3f) is arithmetic from the density and was made before the first cluster reading.

## 3. Runbook defects

| # | Run | Step (B2/B3) | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | run 1 start (before any reading) | B2a | `-Dtest.jvm.args="-Xmx1g -XX:+UseSerialGC"` aborts the test JVM ("Multiple garbage collectors selected": `build.xml` already selects G1) | the probe runs with `-Xmx1g` and G1; readings are taken after a full GC (`System.gc()`) | harness-only; prediction unchanged | none |
| 2 | run 1 | B3h (positive control), B3e (5) | `max_sstables_to_compact` 4 vs 32 never binds: `nodetool compact` ran all 8 sstables in one task under both settings (`run1/cluster/compacting-ctl-max4.summary`, `...max32...`), and the peak table-directory bytes were equal (1,084.2 vs 1,084.3 MB). An exploratory second try (after run 1, `harness/.../ctl-explore.py`: autocompaction on, no `nodetool compact`) gave at most 4 inputs per task under both settings (110 tasks each), because UCS `scaling_parameters` T2 never gathers more than 4. So the filed control is not a cap that binds on this workload | none applied: a cap that binds needs a design change (e.g. `scaling_parameters` T8 or higher with the cap at 4, untested) | left to stage 3; §9a would change if the control changes, so back to the audit | none |
| 3 | audit (before run 1) | B3a/B3b/B3c | `ByteOrderedPartitioner` has no splitter, so the key window cannot raise the density | amended at the audit (Murmur3 and `KeyGen`) | applied, dated | uncommitted |
| 4 | two discarded starts of the cluster tier (my harness, not the case file) | harness | (a) `wait_idle` looked for `pending tasks: 0` but `nodetool compactionstats` prints `pending tasks   0`, so it waited the full 900 s; (b) a first aborted chain left a Python process alive that later stopped the node of the next start; both runs discarded (`pc39:~/stage4-logs/ms/aborted-*`), the cluster tier restarted from its beginning with the fixes | harness fixes | no effect on the case | none |

## 4. Run 1

**Scope:** unit tier, two probe JVMs (330 cells each) plus the upstream `ControllerTest#testGetNumShards`; cluster tier, one node start with Config A and B, dense and control arms, and the `max_sstables_to_compact` control. **Command log:** `max_shard_split-getnumshards-count--autonomous/run1/chain.log`; unit `run1/unit/unit-1.out`, `unit-2.out`; cluster `run1/cluster/{readings.txt,snaps.jsonl,*.summary,samples-every-12th.csv}`; checker `harness/.../selfcheck.py`, output `run1/selfcheck.out` (47 PASS, 1 FAIL: the file's own "control arm 512 or less", see below). Full logs: `pc39:~/stage4-logs/ms/run1/`.

### 4.1 Readings

**Unit tier** (identical in both JVMs and in the repeated call of each cell; `K` = 2^20 x sqrt(0.5) x target x base):

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| growth 0, target 1 MiB, base 1: d = K/4, K/2, 0.99K | 262,144; 524,288; 524,288 (below 2^20, powers of two) | `unit-1.out` |
| growth 0, base 1: d = 1.01K, 2K, 2^10 K, 2^40 K, `MAX_VALUE`, +Inf | 1,048,576 for all (flat at the clamp) | `unit-1.out` |
| growth 0, base 4 / 2047: d >= 1.01K | 4,194,304 / 2,146,435,072 (= base x 2^20, flat) | `unit-1.out` |
| growth 0, base 2048 / 4096: d >= 1.01K | **-2,147,483,648 / 0** (int overflow: the cap is not enforced); base 4096 is already -2,147,483,648 at d = K/2 and 0.99K (base 4096 x 2^19 = 2^31) | `unit-1.out` |
| NaN and 0, every growth/target/base | `baseShardCount` | `selfcheck.out` |
| growth 1, every density | `baseShardCount` | `selfcheck.out` |
| growth 0.333, huge density (2^40 K, `MAX_VALUE`, +Inf) | base << 20 (1,048,576 for base 1; -2,147,483,648 at 2048; 0 at 4096) | `selfcheck.out` info lines |
| target 1 GiB, base 1, growth 0.333 / 0 at the same huge densities | the clamp again (1,048,576): the clamp is reachable at the default target only at densities of 7.6e14 and above | `unit-1.out` |
| positive control, base 4, target 1 GiB, growth 0: `min_sstable_size` 100 MiB vs 0 | d = 0 / 5e7 / 1.5e8 / 2.2e8 / 4.5e8 / 1e9 B gives 1, 1, 1, 2, 4, 4 against 4, 4, 4, 4, 4, 4 | `unit-1.out` control-min |
| `BoundaryTracker` retained heap, 20,000 trackers, shards 4 / 1,024 / 1,048,576 | 76.0 B per tracker at all three (reps 1 and 2, both JVMs); rep 0 (cold) read 75.5 / 76.0 / 76.1 in JVM 1 and 5.8 / 76.0 / 76.1 in JVM 2 | `unit-*.out`, `selfcheck.out` |
| upstream `ControllerTest#testGetNumShards` | passed | `chain.log` |

**Cluster tier** (Murmur3, 2 GiB G1 heap, table `ks.t`, 8 batches of 4,096 rows x 16 KiB = 512 MiB per arm, flush after each batch; every snapshot taken with no compaction pending or running; `Controller` DEBUG "Shard count" lines per phase; `readings.txt`, `snaps.jsonl`, `*.summary`):

| Arm (config; keys) | Logged shard counts, compaction phase | Logged, flush phase (includes background compactions) | sstables after flush -> after `compact` | `Space used (live)` after compact | Post-GC heap after compact |
|---|---|---|---|---|---|
| A dense (target 1 MiB, growth 0; 2^-14 token window) | **1,048,576** (64 lines) | 1; 64; 1,048,576 | 84 -> 64 | 542,212,327 B | 82.4 MB |
| A control (same; random keys) | 512 (208 lines), 1,024 (1 line) | 64; 128; 256; 512 | 538 -> 513 | 544,459,290 B | 92.6 MB |
| B dense (target 1 GiB, growth 0.333) | 512 | 1; 128; 256; 512 | 1 -> 1 | 541,830,809 B | 84.7 MB |
| B control | 1 | 1 | 1 -> 1 | 541,830,888 B | 85.9 MB |
| positive control `max_sstables_to_compact` 4 / 32 (config A, dense data) | 1,048,576 | n/a | 8 sstables, one compaction task with **8** inputs under both | n/a | peak table-dir bytes 1,084,222,661 / 1,084,336,286 |

Other readings: key search for the dense arm tried 539,738,240 random keys to find 32,768 with a token in the 2^-14 window (window span fraction 6.1e-5; `readings.txt` KEYGEN); the node ran with `-Xms2G -Xmx2G`, `unified_compaction.base_shard_count=1`, `sstable_growth=0`, `min_sstable_size=0MiB` (`jvm-extra.txt`, `proc-args.txt`); `RssAnon` was 2.80 to 2.85 GB in every snapshot (AlwaysPreTouch of the 2 GiB heap dominates it; `snaps.jsonl`).

### 4.2 Conclusion and logic

1. **Validity.** The clamp was reached: unit d >= 1.01K gives exactly base x 2^20 for base <= 2047 [observed: `unit-1.out`]; in the cluster the dense arm logged 1,048,576 in 64 of 64 compaction-phase lines [observed: `shardlines-A-dense-compact.summary`]. "Hold fixed" settings confirmed: JVM args [observed: `proc-args.txt`], Config A/B options passed to `ALTER` (re-read in the node's schema via the `Shard count ... times target 1.000 MiB` lines of the DEBUG log) [observed: `shardlines-*`], the same keys in both configs, snapshots at idle [observed: `readings.txt` IDLE lines]. The cluster run is **not valid on one count**: the positive control did not bind (part 2).
2. **Readings.** (a) The positive control `max_sstables_to_compact` is identical at 4 and 32 (8 inputs in one task; the exploratory background-compaction try gave a maximum of 4 inputs under both settings) [observed: `compacting-ctl-max*.summary`, `pc39:~/stage4-logs/ms/explore/ctl.out`]. (b) The control arm's logged counts reach 1,024 once, above the frozen "512 or less" [observed: `shardlines-A-control-compact.summary`]; a compaction of sstables that span only a part of the ring has a higher density per covered span. (c) Base 4096 overflows from d = K/2, not only above K (extends B2f, which lists only d >= K) [observed: `unit-1.out`]. (d) The dense arm of Config B has 1 sstable, not a shard-count-sized number, because the data sits in 1/32 of one shard [inferred: shard width 2^-9, window 2^-14].
3. **Matched row.** Unit B2g row 1, "Shards flat at base x 2^20 for all d above K, and tracker size constant across shard counts": 1,048,576 / 4,194,304 / 2,146,435,072 flat for d >= 1.01K, base 1 / 4 / 2047, and 76.0 B per tracker at 4 / 1,024 / 1,048,576 shards [observed]; and the bypass row, "base 2048 or 4096 returns negative/0 → overflow bypass confirmed": -2,147,483,648 and 0 [observed]. Cluster: B3g row 5, "positive control does not move disk usage → the workload does not drive usage; result not valid": matched by the `max_sstables_to_compact` control [observed]. The readings otherwise fit B3g row 1 (dense arm logs 2^20 = 1,048,576 against at most 1,024 in the control arm; live bytes 542.2 MB vs 544.5 MB, within 0.5%; post-GC heap 82.4 MB vs 92.6 MB, no growth with a 1,024-fold larger shard count), but that row cannot be taken with row 5 matched.
4. **Excluded rows.** Unit: "shards keep growing past base x 2^20" (not seen: flat); "tracker size grows with shard count" (76.0 B at all three); "d never above K" (d up to +Inf); "min-size control does not change the shard count" (it did). Cluster: "heap or disk grows in proportion to the logged shard count" (no: bytes within 0.5%, heap lower in the dense arm); "logged shards never exceed the control arm" (1,048,576 vs at most 1,024); "sstable count explodes beyond data-bounded counts" (64, against 513 in the control arm). No Refuted row applies.
5. **Observed vs. inferred.** Inferred: why the control arm logged 1,024 once (2(b)); that the dense arm's single compaction-phase value 1,048,576 comes from the whole-table compaction of `nodetool compact` rather than background tasks (the flush phase also logs it, from background compactions) **[inferred: the compaction-phase file has 64 lines of the same value]**; that an uncapped path through `getNumShards` would not change bytes **[inferred: the output bytes of the same data are equal across 64 and 513 sstables]**. The cluster verdict does not depend on these; it depends on the control.
6. **Deviations and gaps.** Murmur3 and a key search instead of `ByteOrderedPartitioner` (audit amendment); values 16 KiB and 4,096 rows per batch (amendment); each arm run once, not twice (B3h "repeat each arm once"); post-GC heap is one full-GC reading per snapshot on a G1 heap with 2 GiB pre-touched, so RSS carries no information; the shard-count boundary tracker was not exercised in the cluster beyond its construction in the writers; the overflow (negative or 0 shard count) was observed only in `getNumShards`, not followed into `boundaries(...)`, so whether a table with base >= 2048 would fail at flush or compaction is untested; no run 2; the unit tier used G1 (defect 1).
7. **Core question.** Usage did not follow the shard count: at the clamp (1,048,576 shards) the same 512 MiB occupies 542.2 MB, against 544.5 MB at 512 to 1,024 shards, and the post-GC heap is no larger; a tracker is 76 B at any shard count; the number of sstables is bounded by the data, not by the clamp. The clamp therefore does not cap bytes of disk or heap, and for base >= 2048 it does not even cap the count (overflow). But the cluster tier's own positive control (`max_sstables_to_compact`) did not bind, so by the file's rule the cluster result cannot be Confirmed.

**Conclusion (one line):** unit B2g row 1 (and the overflow bypass row) — Confirmed (does not cap); cluster B3g row 5 — Not confirmed (positive control did not bind; the other readings point the same way).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit-1.out`, `unit-2.out`, `chain.log` and the cluster `snaps.jsonl`, `shardlines-*`, `readings.txt` and recomputes every unit cell from a model of `Controller.getNumShards` written from the source (not from the run): 660 of 660 cells equal the model, the repeated calls and the two JVMs agree, and all B2f statements re-test; cluster: 47 PASS and 1 FAIL in all (`run1/selfcheck.out`). The one FAIL is the frozen prediction "control arm 512 or less" (observed 1,024 once), kept as a FAIL on purpose: the prediction is not edited.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes, with the stated invalid control | JVM args, options and idle snapshots re-read; the control failure is part of the conclusion. |
| 2. Readings | yes | the 1,024 and the base-4096 extension are stated. |
| 3. Matched row | yes | unit rows 1 and bypass by the model check; cluster row 5 by `compacting-ctl-*.summary`. |
| 4. Excluded rows | yes | each re-tested from `snaps.jsonl` and the shard-line summaries. |
| 5. Observed vs. inferred | yes | the verdict does not rest on the inferences. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | dose-response by density across the clamp (unit) and by arm (cluster); the cluster's control failure is carried into the verdict. |

### 5.2 Run 2?

No — 2026-10-28. The unit tier is exact (660 cells, two JVMs); the cluster tier's gap is a design problem of the control (a run 2 would only repeat it), which goes back to stage 3 as feedback.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** undetermined (the unit tier settles `does not cap`; the cluster tier could not, because its positive control did not bind).

**Claim tested:** raising or lowering the quantity that `MAX_SHARD_SPLIT` clamps (the shard count) does not change the bytes of heap or disk the node uses for the same data; the clamp only changes the sstable count, and is reached only at density above `2^20 x sqrt(0.5) x target_sstable_size x base_shard_count`.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (row 1: flat at base x 2^20, tracker 76.0 B at any shard count; plus the overflow bypass row for base 2048 and 4096) | does not cap (bytes); the count clamp itself is bypassed at base >= 2048 | run 1 + self-check | 2026-10-28 |
| Cluster | Not confirmed (row 5: the positive control `max_sstables_to_compact` did not bind; readings otherwise fit row 1) | undetermined | run 1 + self-check | 2026-10-28 |

**Positive control:** unit: `min_sstable_size` 100 MiB moved the shard count (1, 1, 1, 2, 4, 4 against 4 throughout) on the same function and instruments. Cluster: none that bound. `max_sstables_to_compact` 4 vs 32 gave 8 inputs per task under both, and peak table-directory bytes equal; the exploratory background-compaction try also gave a maximum of 4 inputs under both. The arm contrast (shard counts 1,048,576 vs 512 to 1,024, 64 vs 513 sstables, bytes within 0.5%) shows the instruments see a change in shard and sstable counts, but it is not a cap on bytes, so the file cannot reach Confirmed at the cluster tier.

**Feedback filed:** section D of the case file (2026-10-28, uncommitted); audit amendments in A5, B2e, B3b and B3f (dated, uncommitted); new sha256 in the final report; `_INDEX.md` is for the orchestrator.
