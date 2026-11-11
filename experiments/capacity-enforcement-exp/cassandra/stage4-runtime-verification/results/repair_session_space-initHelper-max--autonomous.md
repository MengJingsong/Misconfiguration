# repair_session_space-initHelper-max--autonomous — stage-4 results  <!-- file: results/repair_session_space-initHelper-max--autonomous.md -->

> **Case:** [`repair_session_space-initHelper-max--autonomous`](../../stage3-ai-deep-read/cases/repair_session_space-initHelper-max--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/repair_session_space-initHelper-max--autonomous/`](../harness/repair_session_space-initHelper-max--autonomous/).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-27, advisor's Mac (`advisor-run`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed `8befd498215f50002065d2a234c8881f9dd901bb2333c39902363564a0c91d6f` (commit `3ee383c`). Frozen after the audit's 12 amendments (U1–U4, C1–C8): `8aa77acf0c26c7423d77a96f1b957dff2b6f80640d3f6da5708f36c4f719280a`. After runbook-defect fix D1 (found by the unit shakedown, before any run-1 reading): **`d14bc66cbb25693cf393d62078ec61c60d89985732457483a8bae7308f5bfe0e`**; both tiers ran at this version. All three are rows in `_INDEX.md` §4. Not committed yet (working tree on `advisor-run`, HEAD `0c847e5`) |
| **Harness** | `harness/repair_session_space-initHelper-max--autonomous/`: `RepairSessionSpaceProbeTest.java`, `unit-run.sh`, `JmxAttr.java`, `KnownTree.java`, `make-node-conf.sh`, `cluster-run.sh`; `results/.../run1/selfcheck.py`. Not committed yet. Reused tools (numbers derived again here): the test's structure, `unit-run.sh`, `make-node-conf.sh` and the node mechanics of `cluster-run.sh` were adapted from `harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/` (those files were not changed). No value or derivation was taken from another case file or results file |
| **Tiers and values** | Unit: one table, 2^18 + 1 keys populated once, RF 1, S ∈ {1, 2, 4, 8, 16} MiB, control S = 64, four init-only controls. Cluster: three loopback nodes, RF 3, 3M stress partitions, `repair -full -pr`, S ∈ {default (128), 1, 4, 16, 64} MiB and control 1024 MiB, three repairs each |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: on-heap Merkle tree nodes (`OnHeapLeaf`/`OnHeapInner` + hash arrays + tokens) |
| A | knob varied, ≥ 3 values incl. default | Partly → Met after C2 | B2b 5 values + control; B3b 4 values + control but no default. C2 adds the node default (read back, 128 MiB) as a cluster value. In the unit JVM the default is 62 MiB (not run; the sweep brackets it) |
| A | real resource measured, not only the counter | Met (gap named) | Unit `measureDeep(tree)` plus a leaf count (U3); cluster live-object histogram of node2 (B3d). Gap: the cluster byte figure is the case's derived formula (shallow bytes + assumed 48 B hash arrays + 24 B tokens), not a deep measure; the instance counts are direct |
| A | usage driven to the limit and past it | Met | A sizing knob: the tree always fills 2^d leaves; partitions (2^18 unit, ~1M per range cluster) exceed 2^d for every S-bound value |
| B | each step says what it establishes | Met | B2g/B3g rows, B2h/B3h |
| B | prediction in numbers | Met | B2f exact 2^d_est and byte band; B3f N per S and byte bounds. C6 adds exact d from the unit JVM and the default's prediction |
| B | every plausible outcome has a row | Partly → Met after U4/C7 | Added Invalid / Not-confirmed rows (wrong d, leaf count ≠ size, uncaught tree, objects ≠ N, partition cap binding) |
| B | confirmation needs ceiling-follows-knob and direct branch evidence | Partly → Met after U4/C7 | Added: leaves = 2^d < partitions hashed, and inner count = N − 1 |
| B | alternative explanations and controls | Met | Same data for all S (U2, C3 disables autocompaction), RF=1 (unit), idle histogram subtracted (C4), control S=64/1024 |
| C | a human can follow it | Met | A3 + B1 |
| C | an AI can run it without re-deriving | Partly → Met after U2/U3/C3/C5 | Inclusive key range, populate once, output lines, exact commands, sequence, fallback |
| C | values, commands, observables exact | Partly → Met after C4 | B3d read N from the `ValidationManager.java:85` line, which is logged before `init()` and shows size 1 (`MerkleTree.java:110`); C4 moves N to `Validator.java:158`. `jstat` cannot attach here; dropped |
| D | prerequisites exist or are listed | Partly → Met after U1/C1 | `/local` and ccm do not exist here; host clone and a scripted loopback ring |
| D | workload arithmetic | Met | Unit: 2.6M rows in a 1 GiB heap (memtable flushes → 10 SSTables, handled by U2). Cluster: 3M × ~100 B × 3 ≈ 1 GB on 117 GiB free; 3 × 2 GiB heaps on 32 GiB; largest tree ≈ 200 MiB, its serialized size ≈ 2^20 × 43 B ≈ 45 MB < the 128 MiB internode message limit |
| D | citations spot-checked | Met (one off-by-six noted) | `MerkleTree.java:89, 110, 142-146, 151-160, 1520-1541`, `ValidationManager.java:54-91`, `Validator.java:120-158`, `DatabaseDescriptor.java:596-615, 4091-4100`, `ActiveRepairServiceMBean.java:50-51`, `CompactionsTest.java:120`. A3 step 3 cites `MerkleTree.java:136-137` for `sizedepth`/`depth`; they are at `:142-143` (not load-bearing) |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | host clone, build, test path, test JVM facts | applied 2026-10-27 | no `/local` |
| U2 | inclusive key range (2^18 hashed), populate once, multi-SSTable range, `estKeys`/`pc`, expected = 2^min(d_est,20,pc) | applied 2026-10-27 | exactness; same data for all S |
| U3 | output lines, leaf count by walking the tree, bytes before `rowCount`, init controls' range, `cluster_d` value lines | applied 2026-10-27 | `size()` is a field, not a node count |
| U4 | verdict words and rows (unit) | applied 2026-10-27 | B2g had no Invalid / Not-confirmed rows |
| C1 | three-node loopback ring from one clone, no ccm, `auto_bootstrap: false` | applied 2026-10-27 | host |
| C2 | knob as JMX attribute on all nodes; default added | applied 2026-10-27 | Group A; no restart needed |
| C3 | exact load, settle and repair commands; P > 2^19 check | applied 2026-10-27 | exactness |
| C4 | N from `Validator.java:158`; histogram minus idle; caught window | applied 2026-10-27 | `:85` logs size before `init()` |
| C5 | sequence, stop conditions, n=10M fallback | applied 2026-10-27 | exactness |
| C6 | exact d; default prediction; "double" = ×4 per x4 step; control band ±10% | applied 2026-10-27 | wording; no filed number changed |
| C7 | verdict words and rows (cluster) | applied 2026-10-27 | missing outcomes |
| C8 | host cleanup | applied 2026-10-27 | host |
| R1 | correct A3's `MerkleTree.java:136-137` to `:142-143` | left for stage 3 | not load-bearing |
| R2 | B2b expected the partition cap of 18 to bind at S = 64; the validation's estimate is 262,784 keys, so pc = 19 and S binds there (d_est = 18) | left for stage 3 | the reading 2^18 is the same; a note on B2b's reasoning |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 10:24, cluster 10:32–10:41 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), single host, 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 arm64 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Clone commit | `$W/cassandra-run60` (`W=~/Library/Caches/stage4`), `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `cassandra-5.0.9`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 50 s |
| Case-file / harness commit | uncommitted (repo HEAD `0c847e5`); case-file sha256 values in §1 |
| Storage | internal SSD, APFS, 117 GiB free; node dirs `$W/node-rssih/n1..n3` (wiped after) |
| Loopback | 127.0.0.1–.3 present on `lo0`, all three used |
| Full logs | `$W/logs/repair_session_space-initHelper-max--autonomous/` (`unit-instrument`, `unit-shake-D1-bop`, `unit-shake`, `unit-run`, `instrument-hist`, `cluster-shake`, `cluster-run1`) |

Machine lessons relied on: `$W` workspace and `env.sh`; every ant call with `-Dlocal.repository=$W/m2`; unsandboxed commands for `$W`/Java;
no setsid, so nodes ran as tracked background processes (`nohup … &; disown`); loopback aliases .2/.3 checked with `ifconfig lo0`;
`auto_bootstrap: false` (bootstrap streaming fails here); BSD `sed -i ''` and `stat -f %z`; `jstat` cannot attach, so `jcmd
GC.class_histogram` (live objects) was the heap instrument, checked first on a known tree (§4); a test option reaches the forked test JVM only
through `-Dtest.jvm.args`; test stdout is in `build/test/logs/**/TEST-<class>.log` (copied and cross-checked by the self-check); the forked
test JVM has `-XX:ActiveProcessorCount=2`; JMX for all nodes on 127.0.0.1 with per-node ports, through a small JMX client instead of `sjk`;
stress keys can collide (no exact row count demanded; P per range checked instead); `compactionstats` pending count not used (settled by
SSTable count + no active compaction); system.log timestamps are UTC; shakedown before run 1; selfcheck written before the readings and run
end to end on both shakedowns (exit 0); the daemon class name was not used in a pkill pattern; no foreground sleep near the tool timeout.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | B2c (copy `ValidatorTest` structure) | The unit yaml's partitioner is `ByteOrderedPartitioner` (`test/conf/cassandra.yaml:18`); the shakedown's config line showed it. B1/B2f assume Murmur3 (`LongToken`, c ≈ 200 B) | The test sets `DatabaseDescriptor.setPartitionerUnsafe(Murmur3Partitioner.instance)` after `prepareServer()` and before the keyspace is created, and prints the table's partitioner; a non-Murmur3 line makes the run Invalid. B2f/B2g unchanged | applied 2026-10-27; unit tier restarted from the shakedown | `d14bc66c…` |

No defect in the cluster tier.

## 4. Run 1

**Scope:** both tiers, all values. **Command logs:** `repair_session_space-initHelper-max--autonomous/run1/unit/commands.log`,
`run1/cluster/commands.log`.

**Instrument checks (before run 1).** Upstream `ValidatorTest` (6 tests, incl. `testSizeLimiting`: 2^12 leaves at 1 MiB) passed in the
clone with the probe compiled (`run1/unit/instrument-summary.txt`). Histogram known answer: a held Murmur3 tree with maxsize 2^12 shows
4,096 `OnHeapLeaf` (131,072 B) and 4,095 `OnHeapInner` (196,560 B) (`run1/instrument/knowntree-k12.txt`), and the harness parser reads the
same four numbers. JMX client: default read back 128 on all nodes; set/read back for each value (`run1/cluster/summary.txt` `SET`/`KNOB`).
Shakedowns (not judged): unit 2^12 keys (`run1/unit-shake/`), cluster 30,000 keys, one repair at default/1/1024 (`run1/cluster-shake/`).

### 4.1 Readings

**Unit tier** (`run1/unit/stage4.out`; table partitioner Murmur3; 10 SSTables; `estKeys` 262,784, so pc = 19)

| S (MiB) | d_est | expected | size | leaves | rowCount | bytes | limit | bytes/limit |
|---|---|---|---|---|---|---|---|---|
| 1 | 12 | 4,096 | 4,096 | 4,096 | 262,144 | 622,688 | 1,048,576 | 0.594 |
| 2 | 13 | 8,192 | 8,192 | 8,192 | 262,144 | 1,245,280 | 2,097,152 | 0.594 |
| 4 | 14 | 16,384 | 16,384 | 16,384 | 262,144 | 2,490,464 | 4,194,304 | 0.594 |
| 8 | 15 | 32,768 | 32,768 | 32,768 | 262,144 | 4,980,448 | 8,388,608 | 0.594 |
| 16 | 16 | 65,536 | 65,536 | 65,536 | 262,144 | 9,903,824 | 16,777,216 | 0.590 |
| 64 (control) | 18 | 262,144 | 262,144 | 262,144 | 262,144 | 35,208,416 | 67,108,864 | 0.525 |

| Init-only control (k, hashdepth) | size | leaves |
|---|---|---|
| (8, 126) | 256 | 256 |
| (12, 126) | 4,096 | 4,096 |
| (16, 126) | 65,536 | 65,536 |
| (12, 5) | 32 | 32 |

Value lines (`cluster_d`, budgets S·2^20/3): S = 1 → 10, 4 → 12, 16 → 14, 64 → 16, 127 → 17, 128 → 17, 1024 → 20.

**Cluster tier** (`run1/cluster/summary.txt`, per-repair folders; ring 3 × UN; stress 3,000,000 partitions, 0 errors; 4 SSTables per
node, partition estimate 2,956,512 per node; P (range estimate) 999,040 / 999,168 / 998,912 on n1 / n2 / n3 in every repair)

| S (MiB) | predicted N (2^d) | N on n1/n2/n3, 3 repairs | node2 peak leaves / inners (minus idle 0) | caught samples per repair | derived heap (B) | limit S/3 MiB (B) | ratio |
|---|---|---|---|---|---|---|---|
| default 128 | 131,072 | 131,072 everywhere | 131,072 / 131,071 | 3, 2, 2 | 26,214,280 | 44,739,243 | 0.586 |
| 1 | 1,024 | 1,024 everywhere | 1,024 / 1,023 | 3, 2, 2 | 204,680 | 349,525 | 0.586 |
| 4 | 4,096 | 4,096 everywhere | 4,096 / 4,095 | 2, 2, 3 | 819,080 | 1,398,101 | 0.586 |
| 16 | 16,384 | 16,384 everywhere | 16,384 / 16,383 | 3, 3, 3 | 3,276,680 | 5,592,405 | 0.586 |
| 64 | 65,536 | 65,536 everywhere | 65,536 / 65,535 | 3, 2, 3 | 13,107,080 | 22,369,621 | 0.586 |
| 1024 (control) | 1,048,576 | 1,048,576 everywhere | 1,048,576 / 1,048,575 | 3, 2, 3 | 209,715,080 (200.0 MiB) | 357,913,941 | band [188.7M, 230.7M] holds |

Every repair: exit 0, 3.2–4.2 s, five node2 samples (~0.8 s apart), one `Validator.java:158` line per node. The
`ValidationManager.java:85` line shows `size 1` in every repair (as C4 derived from source). n2 hashed 998,968 partitions into the
16,384-leaf tree at S = 16 (`Validator.java:229` line, `$W/logs/.../cluster-run1/s16-r1/n2-debug-segment.log`). Setting 1024 logged the
heap/4 warning on each node; its text names the previous value (`DatabaseDescriptor.java:4097` prints `conf.repair_session_space` before
the assignment), a log quirk outside this case's question.

### 4.2 Conclusion and logic

1. **Validity** — Unit: table partitioner Murmur3 [observed: `run1/unit/stage4.out` config line]; six validation lines and four init lines;
   read-backs equal S; `rowCount` 262,144 = 2^18 in every line; pc = 19 > d_est for S ≤ 16 [observed: same]. Cluster: three UN nodes, stress
   0 errors, read-backs equal on all nodes, three `:158` lines per repair, P ≈ 999k > 2^19 in every repair [observed: `run1/cluster/summary.txt`,
   `*/n?-prepared.txt`, `*/n?-created.txt`, `stress-excerpt.txt`]. Both runs valid.
2. **Readings** — No gap or outlier. The unit S = 16 ratio (0.590) and S = 64 (0.525) are lower than 0.594 because the tree's 65,536 /
   262,144 leaves hold on average 4 / 1 partitions, so some leaves (about e^-4 ≈ 2% / e^-1 ≈ 37% at random placement) receive none and
   keep the shared empty hash [inferred: `MerkleTree.java:1074-1078`, a leaf takes a hash array only from its first partition]. The cluster ratio is constant (0.586) because the derived formula counts hash arrays for every node.
3. **Matched row** — Unit, U4 Confirmed (rows 1 and 4): size = expected = 2^d_est for S = 1..16, leaves = size, doubling, 0.5·limit ≤
   bytes ≤ limit (0.590–0.594), S = 64 gives 2^18, init controls 2^8/2^12/2^16/32 [observed: `run1/unit/stage4.out`]. Direct :151 evidence:
   leaves (4,096…65,536) < 262,144 partitions hashed. Cluster, C7 Confirmed (rows 1 and 4): N = 2^d (C6) on all replicas in all 18 repairs, ×4 per
   ×4 step of S; every label caught with leaves = N, inners = N − 1; derived heap 0.586 × S/3 MiB for S ≤ 64 and default; control 2^20 and
   200.0 MiB in band, below 341.3 MiB [observed: `run1/cluster/*/hist-merkle-lines.txt`, `samples.csv`, `n?-prepared.txt`]. Direct :151
   evidence: N ≤ 131,072 < P ≈ 999k with inner count N − 1.
4. **Excluded rows** — Unit Refuted (flat size; init control wrong): sizes 4,096 → 65,536 and controls exact. Unit Refuted-caps (bytes > limit):
   max ratio 0.594. Unit Not confirmed: no size ≠ 2^d_est, leaves = size, no bytes < 0.5·limit, S = 64 = 2^18. Unit Invalid: excluded by part 1.
   Cluster Refuted (N flat): six distinct N. Cluster Refuted-caps: max ratio 0.586. Cluster Not confirmed: N = 2^d everywhere, all labels
   caught, peak instances inside the C4 window, control in band. Cluster Invalid: excluded by part 1. The n=10M fallback was not needed
   (`UNCAUGHT labels: none`).
5. **Observed vs. inferred** — Inferred: (a) the cluster derived bytes assume 48 B per hash array and 24 B per token (the case's formula); the
   instance counts are observed. (b) The cluster `cluster_d` predictions come from the unit JVM (same JDK, compressed oops); the node's N
   equalled them in every repair, so a layout difference would have shown as a mismatch. (c) The unit `bytes` figure is the tree before
   serialization (no inner hashes); a serialized-then-held tree would add one 48 B array per inner, which the cluster formula includes and
   still stays at 0.586 of the limit.
6. **Deviations and gaps** — No step skipped. Deviations are the dated amendments and D1 only. Gap: the cluster figure is derived from shallow
   counts, not a deep measure; per-validation scope only (one table, one range); the coordinator's off-heap copies (A3 step 6) were not
   measured (outside B3's observables). In the unit tier the default (62 MiB) was not run as a value; the sweep 1–64 brackets it.
7. **Core question** — Usage follows the constraint: the leaf count is 2^d with d set by `repair_session_space` (parts 3, 1), doubling per
   doubling of S in the unit tier and ×4 per ×4 in the cluster tier, and the real tree objects match it (part 3). The tree's heap stays below
   S/RF MiB at 0.52–0.59 of it (parts 3, 4). It stops growing only where the depth-20 / partition caps bind (S = 64 unit at d_est 18; 1024
   cluster at 20). The constraint caps the per-validation Merkle tree heap.

**Conclusion (one line):** unit U4 row "Confirmed" — confirmed; cluster C7 row "Confirmed" — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (written before the readings; run end to end on both shakedowns, exit 0) re-parses `stage4.out`, the copied test stdout
log, every raw `debug.log` segment and every raw histogram file (not the harness's `samples.csv` or `HIST` lines), recomputes pc, expected,
the per-sample counts, the derived bytes and the verdict. Unit: 17 checks, 0 failed, verdict "Confirmed — caps" (`run1/selfcheck-unit.out`).
Cluster: 9 checks, 0 failed, verdict "Confirmed — caps" (`run1/selfcheck-cluster.out`). Both exit 0.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `stage4.out` config line shows `table_partitioner=Murmur3Partitioner`; `summary.txt` RING, KNOB and STRESS lines; every repair folder has three `n?-prepared.txt` lines; P values re-read from the segments |
| 2. Readings | yes | Re-read `s16-r1/hist-merkle-lines.txt`: 16,384 leaves (524,288 B) and 16,383 inners (786,384 B) in three samples, none in idle; the empty-hash explanation of the lower unit ratios is inferred and does not affect any row |
| 3. Matched row | yes | Selfcheck recomputed every U4 and C7 condition from raw files |
| 4. Excluded rows | yes | Selfcheck's Refuted/Not-confirmed/Invalid checks all clear; `UNCAUGHT labels: none` |
| 5. Observed vs. inferred | yes | (a)–(c) listed; none changes a row: (a) is the case's own formula, (b) is confirmed by the match, (c) bounded by the cluster figure |
| 6. Deviations and gaps | yes | Amendments and D1 only; gaps named |
| 7. Core question | yes | The steps follow B1: d from S → leaves 2^d at :151 → heap ≤ S/RF |

One interpretation recorded: C7's direct evidence "N < P" is applied to the S-bound labels (default, 1–64); at 1024 the binding cap is depth
20, where N = 2^20 ≥ P ≈ 999k is expected by B3c, and the selfcheck applies it the same way.

### 5.2 Run 2?

**No** (2026-10-27). Both tiers match their Confirmed rows exactly, on counts the self-check re-derived from raw files; the inferred
statements do not carry the verdict; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** (B1) For a Murmur3 table validated in one repair session, the Merkle tree a replica builds has exactly `2^d` leaves,
`d = min(floor(log2(S*2^20/RF / c)), 20, ceil(log2 partitions))`; its heap footprint is at most `S/RF` MiB; doubling S doubles the tree
until the partition or depth-20 cap takes over.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (U4 row: B2g rows 1 and 4) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (C7 row: B3g rows 1 and 4) | caps | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (uncommitted); amendments U1–U4, C1–C8 and fix D1 in the case file (uncommitted);
`_INDEX.md` §4 rows (frozen `8aa77acf…`, D1 `d14bc66c…`) and §1 Stage 4 column filled.
