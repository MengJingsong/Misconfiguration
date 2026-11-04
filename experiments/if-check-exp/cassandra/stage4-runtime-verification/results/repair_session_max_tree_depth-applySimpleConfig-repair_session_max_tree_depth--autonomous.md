# repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous — stage-4 results  <!-- file: results/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous.md -->

> **Case:** [`repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous`](../../stage3-ai-deep-read/cases/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — caps. Cluster: Confirmed — caps.**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/`](../harness/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `6976b6d7…d741`). Frozen after the step-0 audit's fifteen amendments (2026-10-24): sha256 **`a79238ce1fa987b4b4d5be6f0a9fb662ee652805ca67ab625b667b5bba498e80`** (new row in `_INDEX.md` §4). Both tiers ran at this version; no runbook fix was needed. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/`](../harness/repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/): `ValidatorDepthCapTest.java`, `unit-run.sh` (unit); `make-node-conf.sh`, `cluster-run.sh` (cluster), adapted from case 3's harness on this host. Not committed. Instrument checks before run 1: (i) `unit-run.sh instrument` — the test class compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`) and upstream `ValidatorTest` passed, 6 tests, 0 failures (incl. `testSizeLimiting`, 2^12 leaves at 1 MiB) ([`run1/unit-instrument/summary.txt`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/run1/unit-instrument/summary.txt)); (ii) a cluster shakedown with a 30,000-partition load ran every step: JMX attribute sets and read-backs, `Prepared` lines, histograms, control, startup with 9 refused, cleanup ([`shakedown/summary.txt`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/shakedown/summary.txt)). It found no case defect and no harness bug; its readings are not used (at 10,000 partitions per range the data term binds at 14, and repairs of ≈ 1.4 s left no histogram sample with tree objects). |
| **Tiers and values** | Unit (B2): `repair_session_max_tree_depth` 10, 12, 14, 16, 20 (20 = the default) at `repair_session_space` 256 MiB, 2^16 + 1 keys, one range, RF 1; control 1 MiB at depth 20; rejection of 9. Cluster (B3): three nodes on this host (127.0.0.1–.3), RF 3, 2,000,000 partitions, `repair_session_space: 1024MiB`; the default (unset, 20), then 10, 14, 18 set over JMX; control depth 18 at 4 MiB; startup with `repair_session_max_tree_depth: 9` on n1. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the same commit as the run clones. Depth values that the predictions depend on were computed at the audit by calling `MerkleTree.estimatedMaxDepthForBytes` from the built run clone (`$W/audit-run7/Depth.java`), before any reading.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of the Merkle trees of one validation; leaves = 2^depth, each with a fixed byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | B2b five values incl. 20 (the default). B3b 10, 14, 18 without the default; an unset run with a read-back added (amendment B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: `ObjectSizes.measureDeep` of the real trees. Cluster: B3d's serialized size B is read before `init()` (below) and the histogram was named only for instance counts; amended to histogram bytes and instance counts of the tree node classes (shallow; gap named) — B3d amendment. |
| A. Core question | usage driven to the limit and past it | Met (after the B3a amendment) | Data term 16–17 (unit) / 20 (cluster) above every set depth ≤ 16 / ≤ 18, so the entry binds. As filed, the cluster's space term at 256 MiB is 17, so d = 18 could not bind; raised to 1024 MiB (space term 19). |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g; left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f exact but assumes the exact partition count, while the code uses an estimate (`CassandraValidationIterator.java:227-236`): 2^16 at d = 20 holds only if D = 16; B3f's 2^18 at d = 18 fails at 256 MiB; control values and the default absent. Amended (B2d, B2f, B2h, B3f, B3h). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: formula mismatch, heap not following, rejection with value changed, data/space term binds, control fails, knob not taken, instrument silent. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 now needs exact leaves = 2^min(D, d) / S = 3 × 2^d (entry below the space and data terms) plus the rejection of 9 (setter, unit; startup, cluster). |
| B. Logic | alternative explanations and their controls | Met | Space-term control in both tiers (B2h, B3h); data and space terms recorded; GC noise by forced-GC histograms. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Range, keyspace, tree construction, initiator open in B2c; ring, tokens, ports, stress validity, compaction between repairs open in B3a/B3c. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Not met → Met after amendment | B3b's `sjk … -mc -op setRepairSessionMaxTreeDepth` cannot run (the getter/setter pair `StorageServiceMBean.java:484`, `:490` is the JMX attribute `RepairSessionMaxTreeDepth`); same for B3h's `setRepairSessionSpaceInMiB` (`ActiveRepairServiceMBean.java:50-51`). B3d's S at `ValidationManager.java:85` is logged before `trees.init()` (`Validator.java:120-124`), so it equals R whatever the knob; S is in `Validator.java:158`. No bounds or test for "starts" (B3e). All amended (B3b, B3d, B3e, B3h). These are the two case-3 defects, caught here at the audit. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a list clone, build, test class; mapped to this host (§2): one clone per node, loopback aliases present. |
| D. Runnable | workload arithmetic reaches the limit | Partly → Met after amendment | Unit: 655 k rows, ≈ 1–2 s per load. Cluster: 2 M partitions × ≈ 84 B ≈ 170 MB per node (RF 3), ≈ 70 s of stress; three 2 GiB heaps on 32 GiB; ≈ 667 k partitions per range (data depth 20); the space term (17 at 256 MiB) fixed by B3a. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `DatabaseDescriptor.java:596-607`, `:4070-4084`, `Config.java:206-208`, `ValidationManager.java:54-89`, `MerkleTree.java:1520-1541`, `StorageService.java:4979-4990`, `StorageServiceMBean.java:484-490` match. `ValidatorTest.java:245` (B2h) is a blank line; the comment is at `:246` and the assertion at `:278` (used in the amendments). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, build, harness copy, instrument check | Amendment 2026-10-24 (uncommitted) | CloudLab path. |
| 2 | B2c: keys 0..2^16 inclusive, keyspace/RF/partitioner, range over all live sstables (left-open → `rowCount` 65,536), `evenTreeDistribution = true`, remote initiator, 60 s | Amendment 2026-10-24 | Not exact. |
| 3 | B2d: data term from the validation's estimate (D = ceil log2 estKeys), printed; space terms printed (20 at 256 MiB, 12 at 1 MiB, computed at the audit) | Amendment 2026-10-24 | B2f assumed the exact count. |
| 4 | B2e: order, control's place, timeout, read-backs, value after d = 9 | Amendment 2026-10-24 | Open. |
| 5 | B2f: leaves = 2^min(D, d) (2^D at d = 20); `measureDeep` ratio band [3.8, 4.2]; control 4,096; exact message and value 20 after d = 9 | Amendment 2026-10-24 | Source shows the estimate; values missing. Changes the d = 20 prediction before any reading. |
| 6 | B2g: six rows added; row 1 needs exact leaves and the rejection | Amendment 2026-10-24 | Audit group B. |
| 7 | B2h: control value 4,096 derived | Amendment 2026-10-24 | Control expectation must be frozen. |
| 8 | B3a: one clone per node, equal-thirds `initial_token`, ports, directories, 2 GiB heap; `repair_session_space` 256 → 1024 MiB (space depth 17 → 19) | Amendment 2026-10-24 | One host; d = 18 cannot bind at 256 MiB. |
| 9 | B3b: JMX attribute set (`-ms -f RepairSessionMaxTreeDepth -v <d>`), read-backs, default added | Amendment 2026-10-24 | Command cannot run; default missing. |
| 10 | B3c: exact stress command and validity; compaction wait; `disableautocompaction`; repair coordinator and bound | Amendment 2026-10-24 | Stable estimates. |
| 11 | B3d: S from `Validator.java:158`; B replaced by histogram H and Lmax; `jstat` not used | Amendment 2026-10-24 | `:85` is before `init()`. |
| 12 | B3e: full sequence, bounds, "fails"/"starts" tests with exact text, cleanup | Amendment 2026-10-24 | No bounds. |
| 13 | B3f: S = 3 × 2^d (3,072 / 49,152 / 786,432), ×16; default 1,572,864; Lmax = S; H ratio [15, 17]; control 6,144 | Amendment 2026-10-24 | Three ranges; absolute values. |
| 14 | B3g: definitions and seven rows added | Amendment 2026-10-24 | Audit group B. |
| 15 | B3h: control set as a JMX attribute; S = 6,144 derived (space depth 11 at 4 MiB) | Amendment 2026-10-24 | Command cannot run; value missing. |
| 16 | B1: say that "partitions" is the validation's estimate, and that the entry binds only below the per-range space depth (which depends on RF and the range's share) | Left for stage 3 | Wording; the amendments use the exact terms. |
| 17 | Test line 601 (a value > 20 only warns) at startup and over JMX | Left for stage 3 | Not in B1's claim. |
| 18 | Measure the coordinator's off-heap received trees | Left for stage 3 | Not needed for B3g. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit instrument 22:31, unit run 22:32 EDT; cluster shakedown 22:34–22:37; cluster run 1 22:38–22:43 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 155 GiB free at start (154 GiB at the cluster run); loopback 127.0.0.1, .2, .3 present on `lo0` (checked at start and by the harness); ports 7000, 7199, 7299, 7399, 9042 free; no `CassandraDaemon` before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork (`maxMemory` 1,056,309,248). Nodes: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), shipped `jvm-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`) in all three: n1 and unit `$W/cassandra-run7` (`ant -Dlocal.repository=$W/m2 build-test`, 50 s), n2 `$W/cassandra-run7-n2`, n3 `$W/cassandra-run7-n3` (`ant jar`, 49 s / 51 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | filed `f361777`; amendments and harness uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-rsmtd/{n1,n2,n3}/{data,commitlog,hints,saved_caches,cdc_raw}` (≈ 169 MB live data per node), wiped before and after; JMX 7199 / 7299 / 7399 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/repair_session_max_tree_depth-applySimpleConfig/` — `clone.log`, `build-test-run7.log`, `jar-run7-n{2,3}.log`, `unit-instrument/`, `unit/` (ant log, JUnit XML, `stage4.out`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `stress.log`, `n{1,2,3}/{system,debug,gc}.log`, `<label>/{hist/*.txt,samples.csv,repair.log,n*-debug-segment.log,n*-prepared.txt,n*-created.txt}`, `startup-depth9/`) |

## 3. Runbook defects

None. The two command/observable problems known from case 3 (JMX attribute vs operation; S logged before `init()`) were found in
this file at the audit and fixed by amendments B3b, B3d, B3h before the freeze; the shakedown found nothing further.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stage4.out`, `junit-testsuite.txt`); [`run1/cluster/`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `stress-results.txt`; per label `repair.log`, `samples.csv`, `n*-prepared.txt`, `n*-created.txt`, `n*-idle-histo-lines.txt`; `startup-depth9/lines.txt`).

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; JUnit 1 test, 0 failures, 0 errors; `ByteOrderedPartitioner`, RF 1; 3 sstables per load; estKeys 65,536 so D = 16 every time; `rowCount` 65,536; space term 20 at 256 MiB)

| depth d | read-back (d / space) | leaves (one tree) | 2^min(D, d) | `measureDeep(trees)` B | ratio to previous | serialized B |
|---|---|---|---|---|---|---|
| 10 | 10 / 256 | **1,024** | 1,024 | 125,744 | — | 14,825 |
| 12 | 12 / 256 | **4,096** | 4,096 | 498,176 | 3.962 | 57,289 |
| 14 | 14 / 256 | **16,384** | 16,384 | 1,976,672 | 3.968 | 219,657 |
| 16 | 16 / 256 | **65,536** | 65,536 | 7,877,984 | 3.985 | 860,681 |
| 20 (default) | 20 / 256 | **65,536** | 65,536 (D = 16) | 7,877,984 | 1.000 (predicted 2^(D−16) = 1) | 860,681 |
| control: 20 at 1 MiB | 20 / 1 | **4,096** | 4,096 (space term 12) | 498,176 | — | 57,289 |
| 9 | — | `ConfigurationException`: `Cannot set repair_session_max_tree_depth to 9 which is < 10, doing nothing`; value afterwards **20** | | | | |

Value lines (re-print of the audit's computed values): ByteOrdered space depth 20 at 256 MiB and 12 at 1 MiB; Murmur3 per-range space depth 11 / 17 / 19 at 4 / 256 / 1024 MiB, unchanged at 0.95× and 1.05×.

**Cluster tier** (stress: 2,000,000 partitions, 0 errors, 30,228 op/s, 66 s; each node 3 sstables, 169 MB live, ≈ 1.97 M partitions estimated; every repair exit 0, 5.0–8.2 s, `Repair completed successfully`; per node one `Prepared` and one `Created` line per repair, `Created 3 merkle trees … 2000128 partitions`; 5–8 histogram samples per node per repair, 3–7 with tree objects; idle histograms with no tree objects before every repair; startup warning `A repair_session_space of 1024MiB mebibytes is likely to cause heap pressure` on each node, as expected)

| Capacity value | Run | Read-back depth / space (n1, n2, n3) | S per node (n1 = n2 = n3) | predicted S | Lmax | H_max per node (B) | Evidence |
|---|---|---|---|---|---|---|---|
| default (unset) | A | 20 / 1024 on all | **1,572,864** | 3 × 2^19 = 1,572,864 (space term) | 1,572,864 | 125,828,976 | `cluster/default/` |
| 10 | A | 10 / 1024 on all | **3,072** | 3 × 2^10 = 3,072 | 3,072 | 245,616 | `cluster/d10/` |
| 14 | A | 14 / 1024 on all | **49,152** | 3 × 2^14 = 49,152 | 49,152 | 3,932,016 | `cluster/d14/` |
| 18 | A | 18 / 1024 on all | **786,432** | 3 × 2^18 = 786,432 | 786,432 | 62,914,416 | `cluster/d18/` |
| 18 at 4 MiB | control | 18 / 4 on all | **6,144** | 3 × 2^11 = 6,144 | 6,144 | 491,376 | `cluster/ctl-s4-d18/` |
| `repair_session_max_tree_depth: 9` (n1 yaml) | startup | — | — | — | — | — | process exited after 2 s; `ConfigurationException … repair_session_max_tree_depth should not be < 10, but was 9`; no `Startup complete` (`startup-depth9/lines.txt`) |

S(14)/S(10) = S(18)/S(14) = 16 on every node; H(14)/H(10) = 16.009, H(18)/H(14) = 16.000. H_max = 80 B × S − 144 B at every value.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — the test ran to the end with no failure [observed: `run1/unit/summary.txt`, `junit-testsuite.txt`]; every read-back equals the set value, one tree per validation, `rowCount` 65,536, D = 16 ≥ every d ≤ 16, space term 20 [observed: `stage4.out`]. Valid.
2. **Readings** — nothing unusual; estKeys is exactly 65,536 here, so D = 16 and the d = 20 value equals the d = 16 value [observed].
3. **Matched row** — B2g row 1, "leaves follow 2^min(16, d) — cap works as traced", read with the amendment as 2^min(D, d): leaves = 1,024 · 4,096 · 16,384 · 65,536 · 65,536 at d = 10 · 12 · 14 · 16 · 20 exactly; `measureDeep` ratios 3.962, 3.968, 3.985 in [3.8, 4.2] and 1.000 = 2^(D−16) for 16 → 20; d = 9 rejected with the exact message and the value unchanged (20) [observed: `stage4.out`].
4. **Excluded rows** — "leaves = 2^16 at d = 10": 1,024 [observed]. "Leaves < 2^min(16, d) (space term)": none [observed]. "d = 9 accepted": exception [observed]. Added rows: formula mismatch — none; `measureDeep` out of band — none; rejection with value changed — 20 after; data term binds — D = 16; control ≠ 4,096 — 4,096; timeout / tree count / `rowCount` / read-back — none [observed].
5. **Observed vs. inferred** — none load-bearing.
6. **Deviations and gaps** — `ByteOrderedPartitioner` (the test yaml's); the cluster tier uses Murmur3.
7. **Core question** — the entry sets the tree depth exactly: leaves are 2^d while d is below the data term, and the trees' full deep size grows ≈ 4× per +2 (halves per unit decrease); below 10 the setter refuses and leaves the value unchanged.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — stress wrote 2,000,000 partitions with 0 errors [observed: `cluster/stress-results.txt`]; every read-back equals the intended depth and space on all three nodes, including the unset default 20 [observed: `summary.txt` `KNOB` lines]; R = 3 and P = 2,000,128 per node in every `Created` line, so P/3 ≈ 666,709 > 2^19 (data depth 20) [observed: `n*-created.txt`]; every repair exited 0 with `Repair completed successfully` [observed: `repair.log`]; three `UN` nodes with the equal-thirds tokens [observed: `summary.txt` `RING`, `YAML`]. Valid.
2. **Readings** — the three nodes agree exactly at every value [observed]. The repairs took 5–8 s, so the 1 s sampler caught the trees in 3–7 samples per node [observed: `samples.csv`].
3. **Matched row** — B3g row 1, "S = 2^d per range — claim confirmed", read with the amendment: on every node S = 3 × 2^d at d = 10, 14, 18 (3,072 · 49,152 · 786,432), ×16 per +4; H ratios 16.009 and 16.000 in [15, 17]; Lmax = S at every value; S(default) = 1,572,864; startup with 9 refused with the exact message [observed: `n*-prepared.txt`, `samples.csv`, `summary.txt`, `startup-depth9/lines.txt`].
4. **Excluded rows** — "S constant": ×16, ×16 [observed]. "S below 2^d for d = 18 (space term)": 786,432 = 3 × 2^18 [observed]. "Node starts with 9": exited after 2 s, no `Startup complete` [observed]. Added rows: S ≠ 3 × 2^d — none; H ratio out of band or Lmax ≠ S — none; S(default) ≠ 1,572,864 — equal; read-back / R / line missing / repair failed / stress errors — none; data term binds — P/3 > 2^19; control ≠ 6,144 — 6,144 on every node; no sample with tree objects — 3–7 per node per repair [observed].
5. **Observed vs. inferred** — that H measures the replica's own validation tree [inferred: one validation per node per repair, and the coordinator's received trees are off heap by default, `Config.java:212`; consistent with Lmax = S exactly]. The match does not need it beyond Lmax = S, which is observed.
6. **Deviations and gaps** — (i) `repair_session_space` 1024 MiB instead of the filed 256 MiB (amendment B3a, before the run, for a source-computed reason); it is above heap/4 and logs a warning at startup, nothing else. (ii) H counts shallow node objects only; the unit tier's `measureDeep` gives the full size. (iii) The coordinator's off-heap received trees were not measured. (iv) All three nodes on one host.
7. **Core question** — the tree each replica builds follows the entry exactly: three ranges of 2^10, 2^14, 2^18 leaves at d = 10, 14, 18, the depth set by the entry while the data (20) and the budget (19) would allow more, and its heap (node objects) scales ×16 per +4 with it. At the default 20 the budget, not the entry, binds (19). The startup check refuses 9. The entry caps the Merkle-tree heap of a validation whenever it is below the budget-derived depth.

**Conclusion (cluster tier):** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/run1/selfcheck.py) (independent of the harness: it re-reads `unit/stage4.out` and the JUnit XML, recomputing D from estKeys; each node's **whole** `debug.log` for every `Prepared` and `Created` line in file order; the **raw `jcmd` histogram files** of every sample, re-parsed; `repair.log`, `stress.log`, the startup `system.log`/`node.out`; and the read-back lines in `commands.log`) recomputes every amended B2f/B3f prediction: **192 checks, 0 failed**, exit 0 ([`run1/selfcheck.out`](repair_session_max_tree_depth-applySimpleConfig-repair_session_max_tree_depth--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Stress totals from `stress.log`; read-backs from `commands.log`; R, P from the raw `debug.log`; data term per label and node; unit read-backs, D, `rowCount`. |
| 2. Readings | yes | Five `Prepared` and five `Created` lines per node, in label order; the three nodes equal. |
| 3. Matched row | yes | S = 3 × 2^d and ×16 per node; S(default); Lmax and H re-derived from the raw histogram files; H ratios in band; startup text in the raw logs; unit leaves = 2^min(D, d), `measureDeep` ratios, the d = 9 line. |
| 4. Excluded rows | yes | Control 6,144 on every node and 4,096 in the unit tier; idle histograms without tree objects; samples with tree objects in every repair; the `:85` size field equals R in all 15 lines. |
| 5. Observed vs. inferred | yes | The inference in part 5 is not needed by the matched row. |
| 6. Deviations and gaps | yes | Stated; none bears on the matched rows. |
| 7. Core question | yes | Entry → depth (exact) → heap reading ×4 per +2 (unit) / ×16 per +4 (cluster); startup and setter rejections as traced. |

### 5.2 Run 2?

**No** — decided 2026-10-24. Every reading is an exact count matched to an exact prediction on three nodes and at the unit tier, the
conclusion rests on no inferred statement, and the independent self-check holds with no failures. The result confirms the case's claim
(no refutation, no bypass).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "With `repair_session_space` large enough not to bind, the number of leaves per validation tree equals
`2^min(ceil(log2(partitions)), repair_session_max_tree_depth)`, and the trees' heap size halves for each unit decrease of the entry; values
< 10 are rejected." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: leaves = 2^min(16, d) exactly at d = 10–20; `measureDeep` ×3.96–3.99 per +2; control 4,096; 9 rejected, value unchanged) | caps | run 1 + self-check | 2026-10-24 |
| Cluster | **Confirmed** (row 1: S = 3,072 · 49,152 · 786,432 = 3 × 2^d at d = 10 · 14 · 18 on all three nodes, ×16 per +4; histogram bytes ×16.0; control 6,144; default 20 → space term 19; startup with 9 refused) | caps | run 1 + self-check | 2026-10-24 |

**Feedback filed:** the case file's section D (uncommitted); the fifteen step-0 amendments are in the case file, dated, with the frozen
sha256 as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column and the coverage line updated. No section was
amended for a refutation (none occurred).
