# memtable_heap_space-LeafBuilder-allocated--autonomous — stage-4 results  <!-- file: results/memtable_heap_space-LeafBuilder-allocated--autonomous.md -->

> **Case:** [`memtable_heap_space-LeafBuilder-allocated--autonomous`](../../stage3-ai-deep-read/cases/memtable_heap_space-LeafBuilder-allocated--autonomous.md)
>
> **Status:** verdict filed (2026-10-27). **Unit: Confirmed — caps** and **Cluster: Confirmed — caps** (re-run "run 1b" of 2026-10-27/28 at the
> re-frozen versions `fe0ac095…` (unit) and `cde29303…` (cluster, after fix D3), after the user-authorised amendments of B2a/U1/U5, B2h,
> U4 rows 1 and 6 and of C6 (4), C7 row 6, C1/C5; in one cluster run the amended band holds only through its rewrite allowance, §7.6).
> Run 1's verdicts (both Not confirmed — caps, row 7) are kept in §4 and §8 unchanged. The re-run is §7.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/memtable_heap_space-LeafBuilder-allocated--autonomous/`](../harness/memtable_heap_space-LeafBuilder-allocated--autonomous/).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-27, advisor's Mac (`advisor-run`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed `226e3073790b0fcd5b43e22115adbc2dad00435663ba87a4408b7360d964b262` (in HEAD `bfe5ee0`). Frozen after the audit's 13 amendments (U1–U5, C1–C8): `943cd61e21cde270ea8da3058266741d2a81dce784e105947ae569d5eca936ac`. After runbook-defect fixes D1 (unit shakedown) and D2 (cluster shakedowns), both before any run-1 reading: **`1f881f11bc7ca0ad7090e70da1bc7de048d011a4fa1e0c6ed5ea05d4a7adfc05`**; both tiers ran at this version. All three are rows in `_INDEX-advisor.md` §2. Not committed (working tree on `advisor-run`, HEAD `bfe5ee0`) |
| **Harness** | `harness/memtable_heap_space-LeafBuilder-allocated--autonomous/`: `WideMemtableSizeTest.java`, `WideLeafCounters.java`, `unit-counters.btm`, `v1-patch.sh`, `unit-run.sh`; `Sampler.java`, `node-counters.btm`, `wide-single.yaml`, `wide-batch.yaml`, `cluster-run.sh`, `cluster-chain.sh`; `results/.../run1/selfcheck.py`. Not committed. Reused (numbers derived again here): the test is a copy of upstream `MemtableSizeTestBase`/`MemtableSizeUnslabbedTest` as the case says; `Sampler.java`'s connection loop and the node start/stop mechanics of `cluster-run.sh` are adapted from `harness/memtable_heap_space-applySimpleConfig-memtable_heap_space--autonomous/` (those files were not changed); `unit-run.sh`'s shape follows `harness/repair_session_space-initHelper-max--autonomous/unit-run.sh`. No value or derivation was taken from another case file or results file |
| **Tiers and values** | Unit: 5,000 partitions; classes `skiplist`, `skiplist_sharded`, `trie`; rows {4, 256} x mode {single, batch} on V0, rows 256 x both modes on V1; `memtable_heap_space` default (1,019 MiB in the 4 GiB CMS test JVM). Cluster: one node, 2 GiB heap, `memtable_heap_space` ∈ {64 MiB, 256 MiB, default 512 MiB} x {single, batch} on V0, and 64 MiB x both modes on V1 (eight runs) |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: JVM heap of memtables; the operand is `SubPool.allocated`, fed by per-write `heapSize` that includes the leaf arrays counted at lines 2683/2736 |
| A | knob varied, ≥ 3 values incl. default — or another approach | Unit: Met (other approach); cluster: Partly → Met after C2 | Unit varies the build (V0/V1) and the partition width at the default limit, because claim (a) is about the accuracy of the operand, not the cap; cluster had 64/256 MiB only, C2 adds the default (512 MiB at 2 GiB) |
| A | real resource measured, not only the counter | Met (gaps named) | Unit: jamm `measureDeep` of the memtable; cluster: live-object histogram totals. Gap: a 2-s sampler cannot see a transient above the limit between samples; the "Flushing largest" log line gives the pool's used ratio at each trigger |
| A | usage driven to the limit and past it | Unit: n/a by design (no flush allowed, B2b); cluster: Partly → Met after C3 | As written the cluster workload reaches the limit but not the target lines: ≈ 5 rows per partition per memtable at 64 MiB with 20,000 partitions (C3); amended to 1,000 partitions x 8,192 rows |
| B | each step says what it establishes | Met | B2h/B3h |
| B | prediction stated in numbers or a clear relation | Partly → Met after U3/C6 | B2c/B2f's counts were mis-derived (U3: 13 events per partition, not ~7; V0 − V1 exactly 88·n2683 + 144·n2736); B3f's "about 4x" and "within ~5%" given bands (C6) |
| B | every plausible outcome has a row | Partly → Met after U4/C7 | Added the control row, the strong over-count row, Invalid rows, and the ordering |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after C6/C7 | Cluster: flush trigger at `live ≥ 0.50` and `Used total ≤ 1.00` from the cleaner's log line, `BlockedOnAllocation` recorded; unit: per-event counters show the branch fired |
| B | alternative explanations and their controls | Met | 4-row baseline, V1, unslabbed allocator, same JVM flags (Byteman agent in every run), idle histogram control (C5) |
| C | a human can follow it | Met | A3 and B1 |
| C | an AI can run it without re-deriving the code path | Partly → Met after U2/U5/C5 | Test structure, output lines, exact sequences |
| C | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after U1–U5, C1–C5 | No `wide.yaml` text, no sampler for `sjk` on this host, batch `n` would have been 640 M rows |
| D | harness and environment prerequisites exist or are listed | Partly → Met after U1/C1 | `/local` does not exist here; `-Dtest.jvm.args=-Xmx2G` is overridden by `build.xml:1153` (checked with `ant -verbose`), so `_JAVA_OPTIONS` |
| D | workload arithmetic reaches the limit | Partly → Met after U1/C3 | Unit: ≈ 316 B per row from source, 1.28 M rows ≈ 386 MiB, over a 1 GiB heap's flush point (204.8 MiB) and close to 2 GiB's (409.6 MiB): 4 GiB. Cluster: ≈ 1.5 GB accounted per run, ≈ 47 / 12 / 6 flushes |
| D | load-bearing citations spot-checked | Met (one count error) | `BTree.java:341-398, 2517, 2629-2643, 2663-2686, 2731-2775, 2880-2881, 2937-2938, 3040, 3057-3063, 3100, 3338, 3446, 3457-3458, 3642`; `BTreePartitionUpdater.java:60-183`; `MemtableAllocator.java:160-197`; `MemtablePool.java:121-200`; `AbstractAllocatorMemtable.java:59-92, 249-293`; `DatabaseDescriptor.java:583-594, 761-774`; `TableMetrics.java:492-532`. A3 step 4 says line 2682 runs "on every 32nd append"; it runs on every 17th after row 32 (U3). A3 step 4's "branches add theirs (2880-2881, 2937-2938)" is right, but the branch rebuilt by `drain()`/`drainAndPropagate` (`BTree.java:3040, 3057-3063`) is never counted (R2) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | host clones, V1 as a second patched clone (`allocated += 0;` keeps the line's bytecode), 4 GiB heap via `_JAVA_OPTIONS` | applied 2026-10-27 | no `/local`; `-Xmx` in `test.jvm.args` does not win; 1 and 2 GiB too small |
| U2 | test details (three classes, output lines), observe-only Byteman counters at lines 2683/2736 on the test thread, synthetic known answer | applied 2026-10-27 | B2d's per-event counts without a third build |
| U3 | corrected counts (65,000 / 0 single, 0 / 20,000 batch) and exact V0 − V1 amounts; traced structural errors | applied 2026-10-27 | B2c/B2f derivation error, found from source before any reading |
| U4 | verdict order, ±1% for V0 − V1, control row | applied 2026-10-27 | missing outcomes |
| U5 | exact sequence and stop condition | applied 2026-10-27 | exactness |
| C1 | host node, G1 default, gc.log in the log dir, compaction disabled as a table option | applied 2026-10-27 | host |
| C2 | default value 512 MiB added; eight runs | applied 2026-10-27 | group A |
| C3 | 1,000 partitions x 8,192 rows, `no-warmup`, batch n = 40,000 | applied 2026-10-27 | target lines unreachable at 20,000 partitions; 640 M rows |
| C4 | JMX sampler, "Flushing largest" ratios, histogram totals, node Byteman counters | applied 2026-10-27 | `sjk`/`jstat` unusable here; lines-reached evidence |
| C5 | exact per-run procedure with idle control and a 0.25 x limit tail | applied 2026-10-27 | a random final fill can be near empty, below the noise |
| C6 | exact bands | applied 2026-10-27 | B3f relations made decidable |
| C7 | verdict order | applied 2026-10-27 | missing outcomes |
| C8 | host cleanup | applied 2026-10-27 | host |
| R1 | A3 step 4: line 2682 runs every 17th append after row 32 (not every 32nd) | left for stage 3 | U3 carries the corrected count |
| R2 | A3 step 4/6: the branch nodes rebuilt by `BranchBuilder.drain`/`drainAndPropagate` (`BTree.java:3040, 3057-3063, 3100`) are never counted; the root of a wide partition is reallocated on every update, so its growth (8–16 B per added child) is missed | left for stage 3 | a second, opposite-sign imprecision next to the one A3 step 6 names |
| R3 | B2c's total-heap estimate (≈ 100–150 B per row) is about half of the source layout (≈ 316 B) | left for stage 3 | U1 sized the heap from the layout |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 11:20–11:25 EDT; cluster from 11:27 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), single host, 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Clone commit | `$W/cassandra-run61` (V0) and `$W/cassandra-run61v1` (V1, `v1-patch.sh`), both `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `cassandra-5.0.9` (`W=~/Library/Caches/stage4`); `ant -Dlocal.repository=$W/m2 build-test` succeeded (V0 in 50 s) |
| Case-file / harness commit | uncommitted (repo HEAD `bfe5ee0`); case-file sha256 values in §1 |
| Storage | internal SSD, APFS, 117 GiB free; node dir `$W/node-mhslb` (wiped after each run) |
| Unit test JVM | forked by Ant, CMS (`build.xml` JDK 11 test args), `-XX:ActiveProcessorCount=2`, `_JAVA_OPTIONS=-Xmx4g` (maxMemory 4,277,534,720 B) |
| Cluster node JVM | `MAX_HEAP_SIZE=2G`, G1 (`conf/jvm11-server.options:63`), Byteman agent `node-counters.btm` |
| Full logs | `$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/` (`build-test.log`, `instrument-upstream/`, `unit-instrument/`, `unit-shake*/`, `unit-v0/`, `unit-v1/`, `cluster/<label>/`, `cluster-chain.out`) |

Machine lessons relied on: `$W` workspace and `env.sh`; every ant call with `-Dlocal.repository=$W/m2`; unsandboxed commands for `$W`/Java;
BSD `sed -i ''`; no setsid (the node runs as a tracked background process); a test option reaches the forked JVM only through
`-Dtest.jvm.args` (and `-Xmx` there loses to `maxmemory`, hence `_JAVA_OPTIONS`); test stdout in `build/test/logs/**/TEST-<class>.log`
(deleted before each run because it appends, copied and compared line by line with `stage4.out` by the self-check); `jstat` cannot
attach and `sjk` is unreliable, so a small JMX client and `jcmd GC.class_histogram` totals (full GC, live objects); heap baselines
drift, so an idle control and baselines taken after ingest; Byteman rules type-checked with `TestScript`; the constant-free V1 variant
done by a patched clone because a line can only be removed by patching; `cassandra-stress` needs `no-warmup` for an exact op count
and a `queries` map in a user profile; `compaction ... 'enabled':'false'` as a table option; system.log timestamps are UTC;
shakedown before run 1; selfcheck written before the readings and run end to end on the shakedowns (exit 0); the daemon class name
not used literally in a kill pattern; no foreground sleep near the tool timeout (one 240-s foreground sleep was killed at 120 s;
nothing else was affected).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | U1 / U4 row 1 | The forked test JVM is CMS; with `-Xmx4g` it reports `maxMemory` 4,277,534,720 B, so the default limit is 1,019 MiB and U4 row 1's "maxMemory not 4 GiB" would call every run Invalid | U4 row 1 reads "`maxMemory` < 4 GiB − 64 MiB or limit ≠ `floor(maxMemory/2^22)`"; U1's 1,024 / 819.2 MiB read 1,019 / 815.2 MiB. Predictions unchanged | applied 2026-10-27; unit tier restarted from its shakedown | `1f881f11…` |
| D2 | cluster shakedowns (before run 1) | C5 retained delta | `end1 − end2` includes the new SSTable's on-heap reader objects in `end2` (+0.99 / +0.86 MB over `idle2` in the two shakedowns), which the empty-memtable idle flush does not create, so it under-reads the memtable | retained delta = `end1 − idle2`; `end1 − end2` and `end2 − idle2` reported as information. Bands and rows unchanged | applied 2026-10-27; cluster run 1 used it | `1f881f11…` |

Harness fixes during the shakedowns (not case defects): the stress user profile needs a `queries` map (added a read query that is
never run); leading sampler errors before stress creates `ks.t` are not counted; the appended `TEST-<class>.log` is deleted before
each unit run.

Re-freeze after run 1 (R1, a case-file amendment authorised by the user), the defect it brought (D3) and harness changes for the re-run
(added 2026-10-27 by the re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | run 1, both tiers (readings, not a runbook defect) | Unit: B2a/U1/U5, B2h, U4 rows 1 and 6. Cluster: C6 (4), C7 row 6, C1/C5 | Unit Not confirmed (U4 row 7): the skiplist V0 − V1 differences were 35,000 B short, the per-JVM row-overhead estimate (187 vs 194 B) entering V0 − V1. Cluster Not confirmed (C7 row 7): `v0-def-single` tail `delta/G_end` 0.915 | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** two dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)`. Unit: `-Dcassandra.memtable.row_overhead_size=190` in every V0/V1 JVM (`SkipListMemtable.java:72-80,121-125`), 190 B derived from the layouts; pin check added to U4 row 1; row 6 restated. Cluster: a rewritten row raises the gauge by its 8-B value and leaves the live heap unchanged (source in §7.1); C6 (4) one-sided `+ 8 × W_tail`. Fresh clones `$W/cassandra-run70`/`run70v1`; both tiers re-run from the beginning (§7). B1, B2f, B2g, B3f, B3g and the relations that held unchanged | user, 2026-10-27 | `fe0ac09502e8420779f5cab9bfcbf7b15b96f4a9d2c97e7fbcbdb32555794831` (uncommitted) |
| D3 | cluster re-run shakedown (before any re-run reading) | the amendment's `W_tail` | The amendment counted one row per single-mode op; the shakedown's stress log showed 13,742 rows/s at 10,054 ops/s. cassandra-stress's user-mode iterator emits each of the 8,192 rows with chance p and forces the window's last row if none was emitted (`PartitionIterator.java:259-283,444-450,562`): 8,192·p + (1 − p)^8,192 rows per op = 1.367857 (single), 128 (batch) | `W_tail` = 1.367857 × `n_tail` (single), 128 × `n_tail` (batch); definition and everything else unchanged. With it **run 1 would meet the amended C6 (4)** (stated in the fix and in §7.1); also corrects the amendment's run-1 histogram statement | applied 2026-10-27 23:38 EDT, before the cluster re-run; the unit re-run (at `fe0ac095…`) is not affected | `cde29303844533420537c26cf8d61376f0e00aa4f13d3417e789789041426c8a` (uncommitted) |
| H1 | both re-runs | harness | Run 1's runners hard-code run 1's clones and log folders, and the unit runner cannot pass the pinned property | `unit-run.sh`: env `C0`, `C1`, `LBASE`, `ROWOVH` (adds `-Dcassandra.memtable.row_overhead_size=$ROWOVH` to `-Dtest.jvm.args`); `cluster-run.sh`: env `C0`, `C1`, `LBASE`; defaults reproduce run 1. `WideMemtableSizeTest.java`: the config line also prints `row_overhead_property` and `skiplist_row_overhead` (`SkipListMemtable.ROW_OVERHEAD_HEAP_SIZE`). Nothing else changed (sha256 in `run1b-unit/harness-sha-run2.txt`) | AI, 2026-10-27 | n/a (harness) |
| H2 | both re-runs | self-check | `run1/selfcheck.py` evaluates run 1's wording | `run1b-unit/selfcheck.py` (and `run1b-cluster/selfcheck.py`, the same plus the `node.out` block of §7.7) copies it and adds `--relations run1\|amended`: the pin checks of amended U4 row 1, the amended C6 (4) with D3's `W_tail`, and information lines (live `BTreeRow`s per histogram, stress row/op ratio, expected rewrites from the generator). Under `--relations run1` it reproduces run 1's verdicts and check counts on run 1's raw files (45 and 72 checks, 0 failed). `run1/selfcheck.py` unchanged | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `memtable_heap_space-LeafBuilder-allocated--autonomous/run1/unit-v0/commands.log`,
`run1/unit-v1/commands.log`, `run1/cluster/<label>/commands.log` (labels `v0-64-single`, `v0-64-batch`, `v0-256-single`,
`v0-256-batch`, `v0-def-single`, `v0-def-batch`, `v1-64-single`, `v1-64-batch`).

**Instrument checks (before run 1).** Upstream `MemtableSizeUnslabbedTest` (3 classes) passed in the V0 clone; `ant -verbose` showed
`'-Xmx4g'` from `-Dtest.jvm.args` followed by `'-Xmx1024m'` (`run1/instrument/xmx-order-ant-verbose.txt`). Byteman `TestScript`: no
errors for both rule files on both clones (`run1/instrument/testscript-*.txt`); the V1 patch keeps bytecode at lines 2683/2736
(`javap -l`) and changes only the two statements (`run1/instrument/v1-patch.txt`). Shakedowns (not judged): unit 200 partitions on
V0 and V1 (`run1/unit-shake/`, selfcheck exit 0), cluster 64 MiB single (400,000 ops) and batch (4,000 ops) (`run1/cluster-shake/`,
selfcheck exit 0).

### 4.1 Readings

**Unit tier** (`run1/unit-v0/stage4.out`, `run1/unit-v1/stage4.out`; both JVMs: maxMemory 4,277,534,720, limit 1,019 MiB, cleanup 0.8,
`HeapPool`, unslabbed, Murmur3; `MIN_KEYS` 15, `MAX_KEYS` 31, `sizeOfReferenceArray(15/17/31)` = 80/88/144 B; known answers
`ka single256` 13/0 and `ka batch2x128` 0/4 in both JVMs; 18/18 tests passed; no memtable flushed)

| Variant | Class | Rows | Mode | owns (B) | trie unused | expected (B) | actual − expected | pct | n2683 | n2736 | flushed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 | skiplist | 4 | single | 8,215,000 | 0 | 8,220,232 | −5,232 | −0.064 | 0 | 0 | false |
| V0 | skiplist | 4 | batch | 8,215,000 | 0 | 8,222,584 | −7,584 | −0.092 | 0 | 0 | false |
| V0 | skiplist | 256 | single | 422,295,000 | 0 | 418,938,360 | +3,356,640 | +0.801 | 65,000 | 0 | false |
| V0 | skiplist | 256 | batch | 417,575,000 | 0 | 417,817,832 | −242,832 | −0.058 | 0 | 20,000 | false |
| V0 | skiplist_sharded | 4 | single | 8,215,000 | 0 | 8,218,144 | −3,144 | −0.038 | 0 | 0 | false |
| V0 | skiplist_sharded | 4 | batch | 8,215,000 | 0 | 8,222,176 | −7,176 | −0.087 | 0 | 0 | false |
| V0 | skiplist_sharded | 256 | single | 422,295,000 | 0 | 418,937,712 | +3,357,288 | +0.801 | 65,000 | 0 | false |
| V0 | skiplist_sharded | 256 | batch | 417,575,000 | 0 | 417,821,608 | −246,608 | −0.059 | 0 | 20,000 | false |
| V0 | trie | 4 | single | 7,636,800 | 200,768 | 7,840,560 | −2,992 | −0.038 | 0 | 0 | false |
| V0 | trie | 4 | batch | 7,636,800 | 200,768 | 7,840,560 | −2,992 | −0.038 | 0 | 0 | false |
| V0 | trie | 256 | single | 421,716,800 | 200,768 | 418,560,560 | +3,357,008 | +0.802 | 65,000 | 0 | false |
| V0 | trie | 256 | batch | 416,996,800 | 200,768 | 417,440,560 | −242,992 | −0.058 | 0 | 20,000 | false |
| V1 | skiplist | 256 | single | 416,610,000 | 0 | 418,938,144 | −2,328,144 | −0.556 | 65,000 | 0 | false |
| V1 | skiplist | 256 | batch | 414,730,000 | 0 | 417,823,352 | −3,093,352 | −0.740 | 0 | 20,000 | false |
| V1 | skiplist_sharded | 256 | single | 416,610,000 | 0 | 418,940,472 | −2,330,472 | −0.556 | 65,000 | 0 | false |
| V1 | skiplist_sharded | 256 | batch | 414,730,000 | 0 | 417,819,928 | −3,089,928 | −0.740 | 0 | 20,000 | false |
| V1 | trie | 256 | single | 415,996,800 | 200,768 | 418,560,560 | −2,362,992 | −0.565 | 65,000 | 0 | false |
| V1 | trie | 256 | batch | 414,116,800 | 200,768 | 417,440,560 | −3,122,992 | −0.748 | 0 | 20,000 | false |

| Class, mode | owns(V0) − owns(V1) | 88·n2683 + 144·n2736 | ratio | U4 ±1% |
|---|---|---|---|---|
| skiplist single | 5,685,000 | 5,720,000 | 0.9939 | holds |
| skiplist batch | 2,845,000 | 2,880,000 | 0.9878 | **fails** |
| skiplist_sharded single | 5,685,000 | 5,720,000 | 0.9939 | holds |
| skiplist_sharded batch | 2,845,000 | 2,880,000 | 0.9878 | **fails** |
| trie single | 5,720,000 | 5,720,000 | 1.0000 | holds |
| trie batch | 2,880,000 | 2,880,000 | 1.0000 | holds |

Both skiplist classes differ from the traced amount by −35,000 B in both modes. The two JVMs logged different SkipListMemtable
per-partition overhead estimates: "Estimated SkipListMemtable row overhead: 187" (V0) and "194" (V1) (`run1/unit-v*/row-overhead-line.txt`;
`SkipListMemtable.java:72-80, 216-240`: estimated at class load from 100 random keys, because the test JVM has
`-Dcassandra.memtable_row_overhead_computation_step=100`, and charged once per partition at `SkipListMemtable.java:124`). 7 B x 5,000
partitions = 35,000 B, so the corrected differences are 5,720,000 and 2,880,000 exactly (`run1/selfcheck-unit.out`, lines marked
"post-reading explanation"). The trie memtable has no such estimate and matches exactly.

**Cluster tier** (`run1/cluster/<label>/`; every run: start-up line "Global memtable on-heap threshold is enabled at" 64 / 256 / 512 MiB
as set, stress errors 0, no OOM, no memtable switch during the tail; `samples.csv` 2-s rows; "Flushing largest" lines from `system.log`)

| Run | s_main | flush lines (ks.t) | min `live` | max `Used total` | max sample ks.t / all tables (÷ limit) | Blocked | G_end (B) | delta = end1 − idle2 (B) | delta / G_end | idle noise (B) | c2683 / c2736 (node, total) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 64 MiB single | 46 | 46 | 0.50 | 0.99 | 0.498 / 0.499 | 67 | 16,693,904 | 17,256,848 | 1.034 | 7,192 | 127,239 / 0 |
| V0 64 MiB batch | 45 | 45 | 0.50 | 0.56 | 0.485 / 0.485 | 1,344 | 16,058,896 | 15,699,104 | 0.978 | 7,256 | 37,127 / 41,149 |
| V0 256 MiB single | 11 | 11 | 0.50 | 0.50 | 0.494 / 0.497 | 0 | 64,968,040 | 64,514,072 | 0.993 | 784 | 201,435 / 0 |
| V0 256 MiB batch | 11 | 11 | 0.50 | 0.50 | 0.402 / 0.404 | 160 | 63,528,576 | 62,810,200 | 0.989 | 704 | 121,585 / 53,676 |
| V0 default (512) single | 5 | 5 | 0.50 | 0.50 | 0.497 / 0.498 | 0 | 127,319,888 | 116,497,808 | **0.915** | 4,576 | 216,544 / 0 |
| V0 default (512) batch | 5 | 5 | 0.50 | 0.50 | 0.389 / 0.391 | 32 | 125,474,056 | 122,735,192 | 0.978 | 3,416 | 168,444 / 37,594 |
| V1 64 MiB single | 46 | 46 | 0.50 | 0.99 | 0.498 / 0.500 | 32 | 16,718,312 | 17,166,104 | 1.027 | 7,592 | 128,491 / 0 |
| V1 64 MiB batch | 44 | 44 | 0.50 | 0.51 | 0.492 / 0.492 | 1,344 | 16,106,992 | 16,333,104 | 1.014 | 8,088 | 16,719 / 21,415 |

Switch ratios (main stress): single 46/11 = 4.18, 11/5 = 2.20, 46/5 = 9.20; batch 45/11 = 4.09, 11/5 = 2.20, 45/5 = 9.00 (all inside
C6's bands). Every sample of both gauges is at or below 0.50 of the limit; every ks.t trigger line shows `live` 0.50. V1 vs V0 at
64 MiB: switches 46 vs 46 (single) and 44 vs 45 (batch); tail gap `G_end − delta` V0 −562,944 / V1 −447,792 B (single) and
V0 +359,792 / V1 −226,112 B (batch), against 36,608 and 21,712 B removed by V1 in the tail epoch (information, below the noise of
the histogram difference). Information: `end1 − end2` and `end2 − idle2` per run in `run1/selfcheck-cluster.out`; post-young-GC heap
(`gc-postgc.txt`) median 78–104 MiB at 64 MiB and 420–462 MiB at 256/512 MiB, with to-space exhaustion and a full GC back to 60 /
185 MiB live in the 256 and 512 single runs (old-gen garbage under G1 with `G1NewSizePercent=50`; the live heap stayed as the
histograms show).

The `v0-def-single` tail added 382,008 live `BTreeRow`s for 425,000 stress ops (`hist-idle2`/`hist-end1`), i.e. 333 accounted B per
live row, against 52,657 / 53,000, 209,376 / 212,000 and 402,721 rows in the other single and default-batch tails at 310–319 B per
row (G_end / live rows added; computed from the raw histograms).

### 4.2 Conclusion and logic

1. **Validity** — Unit: all 18 readings present, no flush, config lines as amended (D1), known answers 13/0 and 0/4 in both JVMs,
   and the counts equal U3's derivation in every case [observed: `run1/unit-v*/stage4.out`]. Cluster: every node started with the set
   limit, stress 0 errors, no OOM, the tail never switched the memtable, 45–46 / 11 / 5 switches reached the limit at every value
   [observed: `run1/cluster/*/summary.txt`, `once.txt`, `flush-largest-lines.txt`]. Both runs valid.
2. **Readings** — Unit: the V0 errors sit exactly where U3 traced them: +3.36 MB in single mode = 51.6 B per line-2683 event (traced
   64 − 8 − 0/8 ≈ 52), −0.24 MB in batch = 48.6 B per partition (traced 48); V1: −35.8 B per event and −624.6 B per partition (trie;
   traced −36 and −624) [observed: table; inferred: U3 arithmetic]. The 4-row errors are within ±0.1%. Cluster: one outlier,
   `v0-def-single` delta/G_end 0.915 (the accounting is 9.3% above the live heap the tail added); the other seven runs are within
   0.978–1.034 [observed: `run1/selfcheck-cluster.out`].
3. **Matched row** — Unit: U4 row 7 "**Not confirmed** — anything else (for example V1 lower by an amount outside ±1% of the traced
   one)": every V0 case within ±3% (max +0.802%), counts as derived, V0 − V1 within ±1% of the traced amount in four of six pairs; the
   two skiplist batch pairs are at −1.22% [observed: `run1/selfcheck-unit.out`]. Cluster: C7 row 7 "**Not confirmed** — anything else
   (for example a delta between the 5% and the 10% bands)": C6 (1)–(3) hold in all eight runs; (4) holds in seven and fails in
   `v0-def-single` (|delta − G_end| = 10,822,080 B > 5% x G_end + noise = 6,370,570 B, but delta ≤ 1.10 x G_end) [observed:
   `run1/selfcheck-cluster.out`].
4. **Excluded rows** — Unit: Invalid (no flush, readings complete, config as D1); control (4-row cases within ±0.1%, counts 0);
   lines not reached (n2683 = 65,000 or n2736 = 20,000 in every 256-row case; owns(V0) ≠ owns(V1)); Refuted under-count (min V0
   256-row pct −0.059); Refuted over-count (max +0.802); Confirmed (excluded by the two skiplist batch pairs). Cluster: Invalid (part
   1); limit never reached (46 switches at 64 MiB); Refuted bypass (no sample above limit + 2 MiB; max `Used total` 0.99); Refuted
   leaky (max delta/G_end 1.034 < 1.10); lines not reached (c2683 + c2736 > 0 in every run); Confirmed (excluded by `v0-def-single`).
5. **Observed vs. inferred** — Inferred: (a) the cause of the −35,000 B in the skiplist pairs is the per-JVM row-overhead estimate
   (187 vs 194 B); the log lines and the arithmetic are observed, and the trie pairs (no estimate) are exact; (b) U3's structural
   explanation of the V0/V1 errors (per-event and per-partition amounts) is inferred from source and matches within 1 B; (c) the
   cluster outlier coincides with more in-memtable rewrites (425,000 ops for 382,008 live rows) but its cause is not isolated; (d) the
   2-s sampler cannot see a transient above the limit, which the trigger lines (`Used total` ≤ 0.99) and the absence of any OOM bound
   only at trigger times.
6. **Deviations and gaps** — No step skipped. Deviations are the dated amendments and fixes D1, D2. Gaps: the cluster's retained
   delta is the whole live-heap change of the tail, not the memtable alone; per-event counts on the node are node-wide (other tables
   included, small); the V1 effect on the cluster (≈ 0.2% of G_end) is below the resolution of the histogram difference, so the
   cluster tier links the target lines to the cap only through the counts (lines reached) and the unit tier.
7. **Core question** — The target lines feed the operand: removing them lowers the accounted heap by exactly 88 B per line-2683 event
   and 144 B per line-2736 event (trie exact; skiplist exact after the per-JVM partition-overhead difference), and with them the
   accounting is within +0.8% of jamm's deep size for 256-row partitions (parts 2, 3). On the node, flushes start at 0.50 of the
   limit, the pool never reported more than 0.99 of it, writers blocked when it filled, and switches scale as 1/limit across 64, 256
   and 512 MiB (parts 1, 3). `memtable_heap_space` caps the memtable heap; the measured accounting errors are small and mostly on the
   conservative side (over-count). Neither tier reaches its Confirmed row because of one frozen band each: ±1% on V0 − V1 (missed by
   0.22 points through a per-JVM estimate outside the target lines) and 5% on the 512 MiB single-mode tail (8.5%, over-count).

**Conclusion (one line):** unit U4 row 7 — not confirmed; cluster C7 row 7 — not confirmed. Effect on both tiers: caps.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before the readings; run end to end on the unit and cluster shakedowns, exit 0) re-parses `stage4.out`,
the copied test stdout logs (line-by-line equality), the ant logs, every raw `samples.csv`, `once.txt`, the four raw histograms of each
run (row sums recomputed against their `Total` lines), the raw `system.log` (trigger lines re-extracted), `node.out` (Byteman lines)
and the stress logs; it recomputes every U4 and C7 condition. Unit: 45 checks, 0 failed, verdict "Not confirmed"
(`run1/selfcheck-unit.out`). Cluster: 72 checks, 0 failed, verdict "Not confirmed" (`run1/selfcheck-cluster.out`). Both exit 0. After
the readings one information block was added to the unit part (the per-JVM row-overhead lines and the corrected differences); it does
not enter the verdict.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `stage4.out` config lines (maxMemory 4,277,534,720, limit 1,019); `ant-excerpt.txt` "Picked up _JAVA_OPTIONS: -Xmx4g" and 12/6 tests; cluster `summary.txt` START lines and stress lines; tail switch 0 in `once.txt` |
| 2. Readings | yes | Re-read `unit-v0/stage4.out` skiplist 256 single: owns 422,295,000, expected 418,938,360, n2683 65,000. Re-read `cluster/v0-def-single/once.txt` (ENDTAIL `t_all_on` 127,319,888) and the summary HIST lines (`end1` 182,714,536, `idle2` 66,216,728) |
| 3. Matched row | yes | Selfcheck recomputed U4 and C7 from raw files; both land on row 7 |
| 4. Excluded rows | yes | Every Refuted / Invalid / not-reached condition clear in the selfcheck output |
| 5. Observed vs. inferred | yes | (a)–(d) listed; (a) re-read in `row-overhead-line.txt`; none of them is needed for the matched rows, which follow from the frozen bands alone |
| 6. Deviations and gaps | yes | Amendments, D1, D2 only; gaps named |
| 7. Core question | yes | The steps follow B1: lines feed `allocated` (unit) → `allocated` is compared with the limit and flushes/blocks follow it (cluster) |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers are Not confirmed on a frozen band, with the failing quantity re-read from raw files and its size
known; a run 2 by the same runbook would meet the same bands (the skiplist estimate varies per JVM; the 512 MiB tail is the same
workload). What would settle each tier is a user-authorised re-freeze (section 8), not a repeat.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Unit and cluster re-run ("run 1b") after the user-authorised amendments — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5[1m]), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed (only the status line at the top was updated, and rows were added to §3
and §8). Run 1's excerpts under `run1/` are untouched. Both tiers were re-run from the beginning (shakedowns first). Excerpts:
[`run1b-unit/`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/) and
[`run1b-cluster/`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/).

### 7.1 Frozen version, amendments and harness

| Field | Content |
|---|---|
| **Why** | Run 1 left both tiers Not confirmed on one frozen band each (§4.2): unit U4 row 7 (V0 − V1 35,000 B short of 88·n2683 + 144·n2736 for both skiplist classes, −1.22 % on the two batch pairs, through the per-JVM skiplist partition-overhead estimate, 187 vs 194 B); cluster C7 row 7 (`v0-def-single` tail `delta/G_end` 0.915, outside the 5 % band). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of both tiers on 2026-10-27. |
| **Unit amendment** | `Amendment 2026-10-27 (after run 1, authorised by the user) — B2a/U1/U5, B2h and U4 rows 1 and 6 (the per-JVM skiplist partition charge)`, after fix D1 in B2. **Source:** a skiplist memtable charges each new partition `token.getHeapSize() + ROW_OVERHEAD_HEAP_SIZE` once (`SkipListMemtable.java:121-125`; `ShardedSkipListMemtable.java:366`); the constant is set at class initialisation from `cassandra.memtable.row_overhead_size` if > 0 (`SkipListMemtable.java:72-80`, `CassandraRelevantProperties.java:356`), otherwise estimated from a `ConcurrentSkipListMap` of 100 random keys in the test JVM (`SkipListMemtable.java:216-240`, `build.xml:1174`), whose JDK 11 index levels are random (`ConcurrentSkipListMap.java:658-672`), so P × (o_V0 − o_V1) entered V0 − V1. **Design:** every V0 and V1 JVM gets `-Dcassandra.memtable.row_overhead_size=190`, so the per-partition charge is identical and cancels exactly. 190 B is the estimator's expectation from the object layouts (Node 24 + BufferDecoratedKey 24 + LongToken 24 + cloned 8-B heap buffer 72, + 0.5 × 24 B of index nodes + ≈ 2 B per-map objects ≈ 158 B; − 24 token + 32 `AtomicBTreePartition.EMPTY_SIZE` + 32 `BTreePartitionData.UNSHARED_HEAP_SIZE` − 8, `SkipListMemtable.java:229-235`); it does not enter V0 − V1. **Rows:** U4 row 1 (Invalid) adds "config line without `row_overhead_property=190 skiplist_row_overhead=190`, or an estimate line in a test log"; row 6 (Confirmed) restated with the pin; rows 2–5, 7, B2f and B2g unchanged. |
| **Cluster amendment** | `Amendment 2026-10-27 (after run 1, authorised by the user) — C6 (4) and C7 row 6 (the rewrite term), C1/C5 (paths)`, after C7, and **fix D3** after it. **Source:** a tail write to a (pk, ck) already in the memtable is merged (`BTreePartitionUpdater.java:136-157`, `BTreeRow.java:583-623`, `ColumnData.java:111-118`, `Cells.java:79-84`): the new cell is cloned through the allocator, which charges the value's 8 B (`AbstractCell.java:108-111`, `ByteBufferCloner.java:70-82`, `MemtableBufferAllocator.java:33-43`, `HeapPool.java:52-55`); the cell's structural delta is 0 (`BufferCell.java:156-158`), the row's cell tree and the partition leaf are charged net 0 (`BTree.java:362-374, 2773-2774`), and nothing is released for the replaced objects, which become garbage of the same size. So a rewritten row raises the gauge by exactly 8 B and leaves the live heap unchanged. **Amended C6 (4):** `-(5% G_end + noise) ≤ G_end − delta ≤ 5% G_end + noise + 8 × W_tail`, `W_tail` = rows written by the tail (an upper bound on rewrites). **Fix D3** (found by the re-run's cluster shakedown, before any re-run reading): cassandra-stress's user-mode iterator writes 8,192·p + (1 − p)^8,192 rows per op (`PartitionIterator.java:259-283, 444-450, 562`; `SchemaInsert.java:80-86`), 1.367857 per single-mode op and 128 per batch op, not 1 / 128 as the amendment said; `8 × W_tail` = 579,971 / 2,319,885 / 4,650,714 B (single) and 424,960 / 1,699,840 / 3,399,680 B (batch) at 64 / 256 / 512 MiB. C7 row 4 and the other rows unchanged. **Why a term:** the frozen workload stays, so switch ratios, trigger lines and the V1 comparison keep their meaning. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's readings were known** when the amendments were written (§4–§5): unit — every reading, the skiplist deficits of exactly 35,000 B, the trie pairs exact, the logged estimates 187 and 194 B (190 is derived from the layouts, not their mean 190.5); cluster — every reading, `delta/G_end` 0.915 and the 333 vs 310–319 accounted B per live row; while looking for the rewrite count the session also read the `BTreeRow` lines of run 1's raw histograms (4,920–41,779 live `BTreeRow`s at `idle2` with an empty memtable; the amendment's "12,000–42,000" is corrected in D3); those counts are not used. **Unit, would run 1 pass?** No as run: it did not pin the property and its logs carry two estimate lines, so it is **Invalid** under the amended row 1 ([`run1b-unit/selfcheck-known-answer-run1-unit-relations-amended.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/selfcheck-known-answer-run1-unit-relations-amended.out)); with the logged per-JVM term subtracted its six differences are exact, so its skiplist readings meet the restated relation. **Cluster, would run 1 pass?** As first written (one row per single op): no, `v0-def-single` failed by 1.05 MB. **After fix D3: yes** — run 1 meets the amended C6 (4) in all eight runs and C7 row 6 ([`run1b-cluster/selfcheck-known-answer-run1-cluster-relations-amended.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/selfcheck-known-answer-run1-cluster-relations-amended.out): 72 checks, 0 failed, Confirmed), `v0-def-single` by 199,202 B (10,822,080 ≤ 11,021,282). It passes through the bound's slack: `8 × W_tail` assumes every tail row is a rewrite; the expected rewrites from the same generator are about 166,000 in that tail (1.33 MB, information in the self-check), which does not explain the 10.8 MB excess. Fix D3 corrects a miscount that does not depend on any re-run reading (the stress source; the shakedown's row/op ratio 1.367 revealed it; run 1's stress logs show the same ratio). |
| **Case-file version** | Amendments: sha256 **`fe0ac09502e8420779f5cab9bfcbf7b15b96f4a9d2c97e7fbcbdb32555794831`** (hashed 23:21:34 EDT, before the fresh clones (23:21:54) and before any re-run reading), the version the **unit re-run** ran at. Fix D3: sha256 **`cde29303844533420537c26cf8d61376f0e00aa4f13d3417e789789041426c8a`** (hashed 23:38:07 EDT, after the cluster shakedown, before the cluster re-run's first run at 23:38:50), the version the **cluster re-run** ran at; D3 touches only C6 (4)'s `W_tail` and the run-1 statements, not the unit sections. Both are new rows in `_INDEX-advisor.md` §2 ("re-frozen after run 1 for unit and cluster re-run (…), authorised by the user", and the D3 row); the earlier rows (`226e3073…`, `943cd61e…`, `1f881f11…`) are kept. Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `600bfc6`; nothing committed. |
| **Harness** | Changed only where the amendments require (§3 H1): `unit-run.sh` (env `C0`/`C1` clones, `LBASE` log folder, `ROWOVH` adds `-Dcassandra.memtable.row_overhead_size` to every test JVM; defaults reproduce run 1), `WideMemtableSizeTest.java` (config line prints `row_overhead_property` and `skiplist_row_overhead`), `cluster-run.sh` (env `C0`/`C1`, `LBASE`; defaults reproduce run 1). Unchanged: `WideLeafCounters.java`, `unit-counters.btm`, `node-counters.btm`, `Sampler.java`, `v1-patch.sh`, `wide-*.yaml`, `cluster-chain.sh`. sha256 before/after in [`run1b-unit/harness-sha-run2.txt`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/harness-sha-run2.txt). Self-check: `run1b-unit/selfcheck.py` and `run1b-cluster/selfcheck.py` (H2; the cluster copy has one block added after the readings, §7.7). Commands: `C0=$W/cassandra-run70 C1=$W/cassandra-run70v1 LBASE=$W/logs/<stem>/unit-run2 ROWOVH=190 unit-run.sh instrument|shake|shake1|v0|v1`; `C0=… C1=… LBASE=$W/logs/<stem>/cluster-run2 cluster-run.sh shake-64-single V0 64MiB single 400000 53000`, `… shake-64-batch V0 64MiB batch 4000 415`, then `cluster-chain.sh` (C2's eight runs, C3's `n_main`, C5's `n_tail`). |

### 7.2 Environment

Same host and storage as run 1 (§2); free disk 109 GiB. Fresh clones from `~/cassandra-src` at `b5f2a54210d541339c2e7c17a794195cac0e67c2`
(tag `cassandra-5.0.9`): `$W/cassandra-run70` (V0, no local change) and `$W/cassandra-run70v1` (V1, `v1-patch.sh apply`: lines 2683/2736 →
`allocated += 0;`, the diff in [`run1b-unit/instrument/clone-run70.txt`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/instrument/clone-run70.txt)),
both `ant -Dlocal.repository=$W/m2 build-test` `BUILD SUCCESSFUL` (53 s, 52 s); Byteman `TestScript: no errors` for both rule files on both
clones (`run1b-unit/instrument/`). Unit: instrument 23:22:12–23:24:01 EDT, shakedowns 23:24:22–23:25:17, re-run V0 23:26:22–23:28:54,
V1 23:28:54–23:31:15; test JVM as run 1 (CMS, `_JAVA_OPTIONS=-Xmx4g`, maxMemory 4,277,534,720) plus the pinned property.
Cluster: shakedowns 2026-10-27 23:32–23:36:42 EDT, re-run chain 23:38:50 EDT (2026-10-27) – 00:34:10 EDT (2026-10-28); one node, 2 GiB, G1,
Byteman `node-counters.btm`, from `$W/cassandra-run70` (V0) and `$W/cassandra-run70v1` (V1; patched until after the last run), node dir
`$W/node-mhslb` wiped after each run; `127.0.0.1`, ports 7000/7199/9042 free before each run.
Full logs: `$W/logs/memtable_heap_space-LeafBuilder-allocated--autonomous/unit-run2/` (`clone-build.sh`, `clone.log`, `instrument/`,
`shake/`, `shake1/`, `v0/`, `v1/`, each with `summary.txt`, `commands.log`, `stage4.out`, the ant log and the copied test log) and
`…/cluster-run2/` (`shake-64-single/`, `shake-64-batch/`, the eight run folders, `cluster-chain.out`, `tools/excerpt.sh`).

### 7.3 Unit re-run — readings

**Shakedown** (200 partitions, V0 12 cases and V1 6 cases; not judged; [`run1b-unit/shake/`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/shake/),
[`shake1/`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/shake1/)): both config lines `row_overhead_property=190
skiplist_row_overhead=190`, no estimate line; V0 − V1 = 228,800 (single) and 115,200 B (batch) for all three classes, equal to
88 × 2,600 and 144 × 800. Self-check 45 of 45, exit 0.

**Re-run** ([`run1b-unit/v0/stage4.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/v0/stage4.out),
[`v1/stage4.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/v1/stage4.out); both JVMs: maxMemory 4,277,534,720,
limit 1,019 MiB, cleanup 0.8, `HeapPool`, unslabbed, Murmur3, `row_overhead_property=190 skiplist_row_overhead=190`, no "Estimated
SkipListMemtable row overhead" line in either test log (`row-overhead-lines.txt`); `MIN_KEYS` 15, `MAX_KEYS` 31, sizes 80/88/144 B;
known answers 13/0 and 0/4 in both; 12 + 6 tests passed; no memtable flushed)

| Variant | Class | Rows | Mode | owns (B) | trie unused | expected (B) | actual − expected | pct | n2683 | n2736 | flushed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 | skiplist | 4 | single | 8,230,000 | 0 | 8,224,504 | +5,496 | +0.067 | 0 | 0 | false |
| V0 | skiplist | 4 | batch | 8,230,000 | 0 | 8,219,704 | +10,296 | +0.125 | 0 | 0 | false |
| V0 | skiplist | 256 | single | 422,310,000 | 0 | 418,940,088 | +3,369,912 | +0.804 | 65,000 | 0 | false |
| V0 | skiplist | 256 | batch | 417,590,000 | 0 | 417,820,472 | −230,472 | −0.055 | 0 | 20,000 | false |
| V0 | skiplist_sharded | 4 | single | 8,230,000 | 0 | 8,221,480 | +8,520 | +0.104 | 0 | 0 | false |
| V0 | skiplist_sharded | 4 | batch | 8,230,000 | 0 | 8,217,688 | +12,312 | +0.150 | 0 | 0 | false |
| V0 | skiplist_sharded | 256 | single | 422,310,000 | 0 | 418,945,224 | +3,364,776 | +0.803 | 65,000 | 0 | false |
| V0 | skiplist_sharded | 256 | batch | 417,590,000 | 0 | 417,820,552 | −230,552 | −0.055 | 0 | 20,000 | false |
| V0 | trie | 4 | single | 7,636,800 | 200,768 | 7,840,480 | −2,912 | −0.037 | 0 | 0 | false |
| V0 | trie | 4 | batch | 7,636,800 | 200,768 | 7,840,480 | −2,912 | −0.037 | 0 | 0 | false |
| V0 | trie | 256 | single | 421,716,800 | 200,768 | 418,560,560 | +3,357,008 | +0.802 | 65,000 | 0 | false |
| V0 | trie | 256 | batch | 416,996,800 | 200,768 | 417,440,560 | −242,992 | −0.058 | 0 | 20,000 | false |
| V1 | skiplist | 256 | single | 416,590,000 | 0 | 418,942,872 | −2,352,872 | −0.562 | 65,000 | 0 | false |
| V1 | skiplist | 256 | batch | 414,710,000 | 0 | 417,819,464 | −3,109,464 | −0.744 | 0 | 20,000 | false |
| V1 | skiplist_sharded | 256 | single | 416,590,000 | 0 | 418,941,528 | −2,351,528 | −0.561 | 65,000 | 0 | false |
| V1 | skiplist_sharded | 256 | batch | 414,710,000 | 0 | 417,820,288 | −3,110,288 | −0.744 | 0 | 20,000 | false |
| V1 | trie | 256 | single | 415,996,800 | 200,768 | 418,560,560 | −2,362,992 | −0.565 | 65,000 | 0 | false |
| V1 | trie | 256 | batch | 414,116,800 | 200,768 | 417,440,560 | −3,122,992 | −0.748 | 0 | 20,000 | false |

| Class, mode | owns(V0) − owns(V1) | 88·n2683 + 144·n2736 | ratio | amended U4 row 6 (±1 %) |
|---|---|---|---|---|
| skiplist single | 5,720,000 | 5,720,000 | 1.0000 | holds |
| skiplist batch | 2,880,000 | 2,880,000 | 1.0000 | holds |
| skiplist_sharded single | 5,720,000 | 5,720,000 | 1.0000 | holds |
| skiplist_sharded batch | 2,880,000 | 2,880,000 | 1.0000 | holds |
| trie single | 5,720,000 | 5,720,000 | 1.0000 | holds |
| trie batch | 2,880,000 | 2,880,000 | 1.0000 | holds |

Every count equals U3's derivation. Against run 1, the skiplist `owns` moved by exactly P × (190 − o_run1): V0 +15,000 B (5,000 × (190 − 187)),
V1 −20,000 B (5,000 × (190 − 194)); the trie readings are identical to run 1's.

### 7.4 Unit re-run — conclusion and logic

1. **Validity** — 18 readings, none flushed; config lines as amended (D1 and the pin) in both JVMs; no estimate line; known answers as
   derived [observed: `run1b-unit/v*/stage4.out`, `row-overhead-lines.txt`, `ant-excerpt.txt` ("Picked up _JAVA_OPTIONS: -Xmx4g",
   the `-Dcassandra.memtable.row_overhead_size=190` argument)]. Valid.
2. **Readings** — V0 within −0.058 … +0.804 % of jamm's deep size (4-row cases −0.037 … +0.150 %); V0 − V1 = 5,720,000 / 2,880,000 B
   for every class, ratio 1.0000 [observed: table].
3. **Matched row** — U4 row 6 as amended, **Confirmed**: every V0 case within ±3 %, and for each class and 256-row mode
   `owns(V0) − owns(V1)` = `88 × n2683 + 144 × n2736` exactly (within ±1 %), counts equal in V0 and V1, n > 0, both JVMs pinned at
   190 B [observed: `run1b-unit/selfcheck.out`].
4. **Excluded rows** — Invalid (part 1); control (4-row within ±0.15 %, counts 0); lines not reached (65,000 / 20,000 events; owns
   differ); Refuted under-count (min 256-row V0 −0.058 %); Refuted over-count beyond the band (max +0.804 %); row 7 (nothing else).
5. **Observed vs. inferred** — Inferred: that the run-1 deficit was the per-JVM term (now observed indirectly: with the term pinned the
   deficit is gone, and run 1's skiplist `owns` differ from the re-run's by exactly P × (190 − o)). The V0 errors (+51.6 to +51.8 B per line-2683
   event in single mode; −48.6 B per partition in batch mode for `trie`, −46.1 B for the skiplist classes, whose per-partition
   charge is now the pinned 190 B) are as run 1 and as U3 traced.
6. **Deviations and gaps** — The two amendments (§7.1) and harness change H1; no step skipped. Gap as in run 1: jamm measures the
   memtable object graph, the per-event counts come from observe-only rules.
7. **Core question** — The target lines feed the operand exactly: removing them lowers the accounted heap by 88 B per line-2683 event
   and 144 B per line-2736 event in all three memtable classes, and with them the accounting stays within +0.81 % of jamm's deep size
   for 256-row partitions. Effect: caps (the operand that the limit is compared with includes the wide-partition leaf arrays).

**Conclusion (one line):** unit re-run — U4 row 6 (amended), **Confirmed**. Effect: caps.

### 7.5 Cluster re-run — readings

**Shakedowns** (V0 64 MiB, single 400,000 / 53,000 ops and batch 4,000 / 415 ops; not judged;
[`run1b-cluster/shakedown/`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/shakedown/)): both nodes started at 64 MiB,
3 and 4 switches, no tail switch, `G_end − delta` −473,112 and −116,488 B; the single-mode stress log showed 13,742 rows/s at 10,054
ops/s, which revealed defect D3 (§3). Self-check (after D3) 20 of 20, exit 0, verdict line Confirmed
([`shakedown/selfcheck.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/shakedown/selfcheck.out)).

**Re-run** (`run1b-cluster/cluster/<label>/`; every run: start-up line "Global memtable on-heap threshold is enabled at" 64 / 256 / 512 MiB
as set, stress errors 0 in all 16 stress runs, OOM 0, no ERROR/WARN line, no memtable switch during the tail; 2-s samples; trigger
lines from the raw `system.log` — for `v0-256-single`, which spanned local midnight so logback rolled `system.log` at 00:00
(`conf/logback.xml:35-42`), from `node.out`, the console copy of the same log stream (INFO, `conf/logback.xml:74-81`;
`cluster/v0-256-single/node-out-start-and-trigger-lines.txt`; §7.7 deviation))

| Run | s_main | trigger lines (ks.t) | min `live` | max `Used total` | max sample ks.t / all (÷ limit) | Blocked | G_end (B) | delta = end1 − idle2 (B) | delta / G_end | idle noise (B) | G_end − delta (B) | amended (4) upper bound (B) | c2683 / c2736 (node) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 64 MiB single | 46 | 46 | 0.50 | 0.50 | 0.498 / 0.500 | 0 | 16,841,552 | 17,377,040 | 1.032 | 8,128 | −535,488 | 1,430,174 | 127,203 / 0 |
| V0 64 MiB batch | 45 | 45 | 0.50 | 0.52 | 0.499 / 0.500 | 1,376 | 16,139,216 | 16,143,480 | 1.000 | 9,120 | −4,264 | 1,241,041 | 37,156 / 41,142 |
| V0 256 MiB single | 11 | 11 | 0.50 | 0.50 | 0.504 / 0.506 | 0 | 64,524,928 | 64,048,384 | 0.993 | 408 | +476,544 | 5,546,542 | 201,109 / 0 |
| V0 256 MiB batch | 11 | 11 | 0.50 | 0.51 | 0.499 / 0.499 | 288 | 63,553,504 | 58,959,928 | **0.928** | 3,864 | **+4,593,576** | 4,881,379 | 122,041 / 53,412 |
| V0 default (512) single | 5 | 5 | 0.50 | 0.50 | 0.498 / 0.498 | 0 | 127,988,376 | 123,017,072 | 0.961 | 408 | +4,971,304 | 11,050,539 | 216,705 / 0 |
| V0 default (512) batch | 5 | 5 | 0.50 | 0.50 | 0.241 / 0.241 | 64 | 125,456,568 | 122,086,296 | 0.973 | 3,280 | +3,370,272 | 9,675,788 | 168,088 / 37,626 |
| V1 64 MiB single | 46 | 46 | 0.50 | 0.50 | 0.496 / 0.498 | 0 | 16,701,848 | 17,211,648 | 1.031 | 2,928 | −509,800 | 1,417,988 | 128,298 / 0 |
| V1 64 MiB batch | 44 | 44 | 0.50 | 0.51 | 0.485 / 0.485 | 1,312 | 16,139,160 | 16,178,800 | 1.002 | 4,952 | −39,640 | 1,236,870 | 16,713 / 21,394 |

Upper bound = 5 % × G_end + noise + 8 × `W_tail` (`W_tail` 72,496 / 289,986 / 581,339 rows single, 53,120 / 212,480 / 424,960 rows batch);
lower bound −(5 % × G_end + noise), the closest being −850,206 B (V0 64 single, reading −535,488). Switch ratios (main stress): single
46/11 = 4.18, 11/5 = 2.20, 46/5 = 9.20; batch 45/11 = 4.09, 11/5 = 2.20, 45/5 = 9.00 (inside C6's bands). V1 vs V0 at 64 MiB: switches
46 vs 46 and 44 vs 45; tail gaps V0 −535,488 / V1 −509,800 B (single) and V0 −4,264 / V1 −39,640 B (batch), against 34,408 and 21,768 B
removed by V1 in the tail epoch (information). Stress tail row/op ratios 1.366–1.375 (single) and 127.9–128.9 (batch), as D3 derives.
Post-young-GC heap (`gc-postgc.txt`) as in run 1, including to-space exhaustion and full GCs in the 256/512 MiB runs (no OOM).

**Information, not a verdict condition** (`run1b-cluster/selfcheck.out`): live `BTreeRow`s in the full-GC histograms with an empty
memtable are 5,051–48,865 at `idle2` and differ at `end2` (for example 28,873 → 23,688 in `v0-256-batch`, whose `end2 − idle2` is
−499,120 B, the only negative one). `W_tail − (end1 − idle2)`, the rewrite count if no non-memtable row changed, is 19,436 / 82,143 /
177,973 in the single runs against 18,674 / 79,731 / 166,226 expected from the stress generator (D3's model), but 3,383 / 21,135 / 24,410
in the batch runs against 172 / 2,732 / 10,834 expected: in `v0-256-batch` about 18,000 fewer live rows were added than the generator
predicts, the size of the gauge's 4.6 MB lead at ≈ 300 B per row.

### 7.6 Cluster re-run — conclusion and logic

1. **Validity** — every node started with the set limit, 16 stress runs with 0 errors, no OOM, no tail switch, all readings present
   (the `v0-256-single` start-up and trigger lines from `node.out`, §7.7) [observed: `run1b-cluster/cluster/*/summary.txt`, `once.txt`,
   `oom-count.txt`, `node-out-start-and-trigger-lines.txt`]. Valid.
2. **Readings** — C6 (1): no sample above limit + 2 MiB (max 0.506 of the limit), max `Used total` 0.52; (2): all 213 ks.t trigger
   lines at `live` 0.50; (3): ratios as above; (4) amended: `G_end − delta` within its bounds in all eight runs, the closest
   `v0-256-batch` (+4,593,576 ≤ 4,881,379, margin 287,803 B) [observed: `run1b-cluster/selfcheck.out`].
3. **Matched row** — C7 row 6 (C6 (1)–(3) and the amended (4) in every run), **Confirmed**.
4. **Excluded rows** — Invalid (part 1); limit never reached (46 switches at 64 MiB); Refuted bypass (no two consecutive samples above
   limit + 2 MiB, max `Used total` 0.52); Refuted leaky (max delta/G_end 1.032 < 1.10); lines not reached (c2683 + c2736 > 0 in every
   run); row 7 (nothing else failed).
5. **Observed vs. inferred** — The amended (4) holds in `v0-256-batch` only through the rewrite allowance's slack: its gauge leads the
   live heap by 7.2 %, above the 5 % band; `8 × W_tail` (1.70 MB) assumes every tail row is a rewrite, while the generator predicts about
   2,700 rewrites there (21.9 kB). So that run's lead is **not** explained by rewrites; it coincides with fewer live rows added than
   predicted and with non-memtable `BTreeRow`s released between `idle2` and `end2` (information above; cause not isolated). Under run 1's
   wording the re-run itself would fail (4) in `v0-256-batch` and be Not confirmed
   ([`selfcheck-rerun-under-run1-relations.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/selfcheck-rerun-under-run1-relations.out));
   run 1's outlier run (`v0-def-single`) is within 3.9 % here. The 2-s sampler cannot see a transient above the limit between samples
   (as run 1).
6. **Deviations and gaps** — The amendments, D3 and H1/H2 (§3, §7.1); the `node.out` source for one run (§7.7). Gaps as run 1: the
   retained delta is the whole live-heap change of the tail; V1's tail effect (≈ 0.2 % of G_end) is below the histogram difference's
   resolution, so the cluster links the target lines to the cap through the counts and the unit tier.
7. **Core question** — On the node, flushes start at 0.50 of the limit in all 213 trigger lines, the pool never reported more than 0.52
   of it, writers blocked when it filled, the gauges never exceeded the limit, and switches scale as 1/limit across 64, 256 and 512 MiB:
   `memtable_heap_space` caps the memtable heap. The accounting of a 0.25 × limit tail is within 3.9 % of the live-heap change in seven
   runs and 7.2 % above it in one, inside the amended band.

**Conclusion (one line):** cluster re-run — C7 row 6 with the amended C6 (4), **Confirmed**. Effect: caps.

### 7.7 Self-check of the re-run — AI

`run1b-unit/selfcheck.py` (= `run1b-cluster/selfcheck.py` except one later block, below) re-reads the raw files under `unit-run2/` and
`cluster-run2/` (never `summary.txt`): `stage4.out` against the copied test logs line by line, the ant logs, the test logs' estimate
lines, every `samples.csv`, `once.txt`, the four raw histograms of each run (row sums recomputed against their `Total` lines), the raw
`system.log`/`node.out` trigger lines, `node.out` Byteman lines and the stress logs; it recomputes every U4 and C7 condition under
`--relations amended` and, for information, `--relations run1`.

- **Before the readings.** Written from `run1/selfcheck.py` before the unit re-run; known-answer pass on run 1's raw files: under
  `--relations run1` it reproduces run 1's verdicts and counts (unit 45 checks, Not confirmed; cluster 72 checks, Not confirmed);
  under `--relations amended` run 1's unit is Invalid (no pin) and, after D3, run 1's cluster is Confirmed (§7.1). Shakedowns end to
  end: unit 45 of 45, exit 0; cluster 20 of 20, exit 0. The cluster `W_tail` was corrected for D3 (and an information line added) after
  the cluster shakedown and before the cluster re-run; the unit outputs were regenerated with that version (identical).
- **After the readings (deviation).** The cluster part could not read `v0-256-single`'s start-up line, because logback rolled
  `system.log` at local midnight and the copied file held only the part after 00:00 (`FAIL … start-up limit line None`). A block was
  added (2026-10-28 00:3x): when `system.log` lacks the start-up line, read the start-up and trigger lines from `node.out`, and check
  that the rolled `system.log`'s trigger messages are the last ones of `node.out`; for every other run, check that the two sources carry
  identical trigger messages. No relation changed; the check passes in all eight runs and the shakedowns, and on run 1's raw files the
  output is unchanged apart from the eight new checks.
- **Results:** unit [`run1b-unit/selfcheck.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-unit/selfcheck.out) 45 of 45,
  exit 0, **Confirmed**; cluster [`run1b-cluster/selfcheck.out`](memtable_heap_space-LeafBuilder-allocated--autonomous/run1b-cluster/selfcheck.out)
  80 of 80, exit 0, **Confirmed**. Informational: under run 1's wording the re-run gives unit Confirmed and cluster Not confirmed
  (`selfcheck-rerun-under-run1-relations.out` in each folder).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1b-unit/v0/stage4.out` config line (`maxMemory=4277534720 … row_overhead_property=190 skiplist_row_overhead=190`), `row-overhead-lines.txt` (no estimate line), `ant-excerpt.txt` (`Picked up _JAVA_OPTIONS: -Xmx4g`, the pinned argument); cluster `summary.txt` START lines (`v0-256-single` also `node-out-start-and-trigger-lines.txt`), stress lines, `once.txt` tail switch 0 |
| 2. Readings | yes | Re-read `run1b-unit/v1/stage4.out` skiplist 256 batch: owns 414,710,000 vs V0 417,590,000 = 2,880,000 = 144 × 20,000. Re-read `run1b-cluster/cluster/v0-256-batch/once.txt` (ENDTAIL `t_all_on` 63,553,504) and the HIST lines (`end1` and `idle2` of `summary.txt` = the raw histograms' Totals in the self-check) |
| 3. Matched row | yes | Both tiers land on their Confirmed rows under the amended relations, recomputed from the raw files |
| 4. Excluded rows | yes | Every Invalid / Refuted / not-reached condition clear in both outputs |
| 5. Observed vs. inferred | yes, with the caveat recorded | Unit: the pin removes the per-JVM term (observed: no estimate line, equal constants, exact differences). Cluster: `v0-256-batch` passes through the rewrite allowance's slack, not through rewrites (§7.6 part 5); this is how the amended, frozen band reads and is stated with the verdict |
| 6. Deviations and gaps | yes | Amendments, D3, H1, H2 and the `node.out` source for one run; gaps named |
| 7. Core question | yes | Unit: the target lines feed the operand exactly; cluster: the operand is compared with the limit and flushes/blocks follow it, switches scale 1/limit |

### 7.8 Verdicts of the re-run

**Unit tier (re-run at `fe0ac095…`): Confirmed — U4 row 6 as amended. Effect: caps.**
**Cluster tier (re-run at `cde29303…`): Confirmed — C7 row 6 with the amended C6 (4). Effect: caps.** In one run (`v0-256-batch`)
the amended band holds only through its rewrite allowance (the gauge leads the live heap by 7.2 %, which rewrites do not explain);
the verdict is the frozen row's.
Run 1's verdicts (both Not confirmed, row 7) stay in §4 and in §8 as the results at `1f881f11…`; the re-run's verdicts are the tiers'
current verdicts.

**End of the re-run:** no `CassandraDaemon`, `cassandra-stress`, sampler or test JVM process; ports 7000/7199/9042 free; `$W/node-mhslb`
removed by the runner after each run; V1 patch reverted (`v1-patch.sh $W/cassandra-run70v1 revert`: lines 2683/2736 as shipped); copied
test files removed; `git status` of `$W/cassandra-run70` and `$W/cassandra-run70v1`: 0 entries; no `cassandra.logdir_IS_UNDEFINED/`
folder; `run1/` unchanged.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** (B1) (a) For wide partitions (more than 31 rows), the memtable's accounted on-heap usage, including the leaf arrays
counted at `BTree.java:2683/2736`, matches the measured retained heap within a few percent; (b) total memtable heap stays at or below
`memtable_heap_space`: writes block or a flush occurs, so live heap does not grow past the limit plus one in-flight memtable's overshoot.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Not confirmed (U4 row 7: two of six V0 − V1 pairs at −1.22%, outside ±1%; all V0 within ±0.81%; the deficit is the per-JVM SkipListMemtable partition-overhead estimate, 7 B x 5,000) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Not confirmed (C7 row 7: C6 (1)–(3) hold in all eight runs; (4) fails in the 512 MiB single-mode run, delta/G_end 0.915, an over-count) | caps | run 1 + self-check | 2026-10-27 |
| Unit (re-run at `fe0ac095…`, after the user-authorised B2a/U1/U5, B2h, U4 rows 1 and 6 amendment) | **Confirmed** (U4 row 6 as amended): with `cassandra.memtable.row_overhead_size` pinned to 190 B in both JVMs, `owns(V0) − owns(V1)` = 88·n2683 + 144·n2736 exactly for all three memtable classes (5,720,000 B single, 2,880,000 B batch; counts 65,000 / 20,000 as derived); every V0 case within −0.058 … +0.804 % of jamm's deep size; no flush; self-check 45 of 45 | caps | unit re-run (§7) + self-check | 2026-10-27 |
| Cluster (re-run at `cde29303…`, after the user-authorised C6 (4), C7 row 6, C1/C5 amendment and fix D3) | **Confirmed** (C7 row 6 with the amended C6 (4)): flushes at `live` 0.50 in all 213 trigger lines, max `Used total` 0.52, gauges ≤ 0.506 of the limit, writers blocked at 64 MiB, switches 46/11/5 and 45/11/5 (1/limit), target lines counted on the node in every run; tail `G_end − delta` within −(5 % G_end + noise) … 5 % G_end + noise + 8·W_tail in all eight runs (seven within 3.9 %; `v0-256-batch` 7.2 %, inside only through the rewrite allowance, which rewrites do not explain, §7.6 part 5); self-check 80 of 80 | caps | cluster re-run (§7) + self-check | 2026-10-28 |

**Open asks for the user (re-runs need authorisation; not done):** (1) unit: re-freeze U4 with
`-Dcassandra.memtable.row_overhead_size=<fixed>` in both JVMs (`CassandraRelevantProperties.java:356`, read at
`SkipListMemtable.java:75-77`), which removes the per-JVM term from V0 − V1; (2) cluster: the 512 MiB single-mode over-count (333 vs
310–319 accounted B per live row) is a finding about the accounting outside the target lines (rewritten rows in a long-lived
memtable); a re-freeze would need a band derived from source for rewrites, which this session did not derive.

**Feedback filed:** the case file's section D updated (uncommitted); amendments U1–U5, C1–C8 and fixes D1, D2 in the case file
(uncommitted); `_INDEX-advisor.md` §2 rows (frozen `943cd61e…`, fixes `1f881f11…`) and §1 Stage 4 column filled.

**Feedback filed for the re-run (2026-10-27/28):** the two amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` (B2: the pinned skiplist partition charge, U4 rows 1 and 6; B3: the rewrite term in C6 (4), C7 row 6, paths) and runbook-defect fix D3 (`W_tail` per single-mode op 1.367857) in the case file; two new `_INDEX-advisor.md` §2 rows (`fe0ac095…`, `cde29303…`); the case file's section D (new entry, run-1 text kept); the §1 Stage 4 column (run-1 text kept, re-run verdicts appended). The coverage section is not touched. No refutation, so no other case section is amended. Run-1 findings kept as observations: A3 step 4's "every 32nd append" is every 17th after row 32; the branch nodes rebuilt by `BranchBuilder.drain`/`drainAndPropagate` are never counted. New observations: in single mode cassandra-stress writes 1.37 rows per op and about 37 % of ops rewrite the partition's last row (forced row); live `BTreeRow`s not belonging to the memtable (5,000–49,000) sit in the idle node's heap and change between the idle and the end histograms, which moves the tail's live-heap delta by up to several MB (cause not isolated); a run that spans local midnight has its `system.log` rolled, so a harness should read the console copy or the rolled archive.
