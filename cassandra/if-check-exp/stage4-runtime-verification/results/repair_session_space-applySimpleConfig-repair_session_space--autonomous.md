# repair_session_space-applySimpleConfig-repair_session_space--autonomous — stage-4 results  <!-- file: results/repair_session_space-applySimpleConfig-repair_session_space--autonomous.md -->

> **Case:** [`repair_session_space-applySimpleConfig-repair_session_space--autonomous`](../../stage3-ai-deep-read/cases/repair_session_space-applySimpleConfig-repair_session_space--autonomous.md)
>
> **Status:** verdict filed, 2026-10-24. **Unit: Confirmed — caps. Cluster: Confirmed — caps.**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/`](../harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-24, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `f361777` (sha256 `0d1f8b0a…5929`). Frozen after the step-0 audit's twelve amendments (2026-10-24): sha256 **`1eb83d35f53742826a77f6843dceb8d8cb8331893f4ee5eee1adce05d450c121`** (new row in `_INDEX-advisor.md` §2). The unit tier ran at this version. Two runbook fixes (B3b, B3d; §3), found by the harness shakedown before cluster run 1 and leaving B3f/B3g unchanged, give **`ad89b5b4aa200d68e11a6d5d69b4d66d542f1423d274fd964f4d5eb84f5ad8b3`** (another new row); the cluster tier ran at this version. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/`](../harness/repair_session_space-applySimpleConfig-repair_session_space--autonomous/): `ValidatorSpaceCapTest.java`, `unit-run.sh` (unit); `make-node-conf.sh`, `cluster-run.sh` (cluster). Not committed. Instrument checks before run 1: (i) `unit-run.sh instrument` — the test class compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`) and the upstream known-answer test `ValidatorTest` passed, 6 tests, 0 failures (incl. `testSizeLimiting`, 2^12 leaves at 1 MiB) ([`run1/unit-instrument/summary.txt`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/run1/unit-instrument/summary.txt)); (ii) a cluster shakedown with a 30,000-partition load, three attempts: it found the two runbook defects of §3 and three harness bugs (compaction-wait regex; `stop_node` stopping the wrong node under bash 3.2; a sample counter), all fixed before run 1; attempt 3 ran every step ([`shakedown/`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/shakedown/)). |
| **Tiers and values** | Unit (B2): `repair_session_space` 1, 2, 4, 8, 16 MiB with `repair_session_max_tree_depth` 20, 2^18 + 1 keys, one range, RF 1; control 16 MiB with depth 12; rejection of 0. Cluster (B3): three nodes on this host (127.0.0.1–.3), RF 3, 3,000,000 partitions; the default (unset, 64 MiB at a 1 GiB heap), then 4, 16, 64 MiB set over JMX; control depth 10 at 4, 16, 64 MiB; startup with `0MiB` and `300MiB` on n1. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`git describe --tags`), the same commit as the run clones.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap of the Merkle trees of one validation; leaves are a count with a derivable byte size (`estimatedMaxDepthForBytes`, `MerkleTree.java:1520-1541`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | B2b five values (no default; acceptable for the unit tier). B3b 4, 16, 64 MiB — 64 is the default at a 1 GiB heap but only set explicitly; an unset run with a read-back added (amendment B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: `ObjectSizes.measureDeep` of the real trees (full deep size). Cluster: class-histogram bytes of the tree node classes (shallow; hash `byte[]` and tokens not attributed) and the coordinator's off-heap received trees not seen — named in the B3d amendment; live-heap `Total` kept as support. |
| A. Core question | usage driven to the limit and past it | Met | The data would need depth 18 (unit) / 20 (cluster) against budget depths ≤ 16 / ≤ 15, so the budget is the binding term at every value; "past it" means the tree cannot grow beyond the budget-derived depth whatever the data. |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g rather than stated per step. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f exact except the control's value and the value after rejection; B3f "×4" only, no absolute value, and the control's "S = 2^10" ignores that the repair has three ranges (S is a sum). Amended (B2f, B3f; B3f takes d from the unit harness, printed before the cluster run). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: formula mismatch, partial scaling, data term binds, control fails, knob not taken, instrument silent, startup outcomes. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 now requires exact leaves = 2^d (the budget, not the data, set the size) and the rejection of 0 (setter, unit; startup, cluster). |
| B. Logic | alternative explanations and their controls | Met | Depth-cap control (B2h, B3h); data term recorded (amended B2d/B3f); GC noise by forced-GC histograms. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 and the tables read on their own. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Range, keyspace, initiator (on-heap capture) and "clear" open in B2c; ring layout, tokens, ports, stress validity, compaction between repairs open in B3a/B3c. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | No bounds or tests for "fails"/"starts" (B3e); sampling window of the histogram undefined (B3d); `jstat` cannot attach on this host (`-XX:+PerfDisableSharedMem`, `conf/jvm-server.options:137`), replaced (B3d). Two command defects were not caught here and surfaced in the shakedown (§3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | B2a/B3a list clone, build, test class; mapped to this host (§2): one clone per node, loopback aliases present. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit: 2.6 M rows, ≈ 5 s per load. Cluster: 3 M partitions × ≈ 84 B ≈ 253 MB per node (RF 3), ≈ 100 s of stress; three 1 GiB heaps on 32 GiB; ≈ 1 M partitions per range (depth 20 by data) against budget depths 11–15. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Partly | `DatabaseDescriptor.java:596-615`, `:4085-4101`, `Config.java:206-212`, `ValidationManager.java:54-89`, `MerkleTree.java:1520-1541`, `ActiveRepairServiceMBean.java:27`, `:50-51`, `ValidatorTest.java:234-283`, `CompactionsTest.java:111-128`, `CassandraValidationIterator.java:227-236` match. Not caught at the audit: `:85` logs the trees before `init()` (defect 2), and `setRepairSessionSpaceInMiB` is an attribute setter (defect 1). B1's formula drops the `+ inner` term of `estimatedMaxDepthForBytes` (`(T + I)/(L + I)`, `MerkleTree.java:1539`) and the range-owning ratio (`ValidationManager.java:71`); harmless here (B2d/B3f use the method itself), left for stage 3. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2c: keys 0..2^18 inclusive; keyspace and RF; range over all live sstables; remote initiator so trees are captured on heap | Amendment 2026-10-24 (uncommitted) | B2c not exact. |
| 2 | B2d: measure the response's `MerkleTrees`; d(s) with RF; record `rowCount` (data term); print Murmur3 d for the cluster budgets | Amendment 2026-10-24 | Object and data term undefined; B3f needs d. |
| 3 | B2e: order, control's place, 60 s timeout, read-backs, value after s = 0 | Amendment 2026-10-24 | Open. |
| 4 | B2f: control 4,096; message and unchanged value at s = 0 | Amendment 2026-10-24 | Not stated. |
| 5 | B2g: six rows added; row 1 needs exact 2^d and the rejection | Amendment 2026-10-24 | Audit group B. |
| 6 | B3a: one clone per node, equal-thirds `initial_token`, `auto_bootstrap: false`, ports, directories; logback unchanged (`:132` DEBUG) | Amendment 2026-10-24 | One host; random tokens make depths unpredictable. |
| 7 | B3b: add the default (unset) with read-back; read back every set; control via `StorageService` | Amendment 2026-10-24 | Group A; knob-taken evidence. |
| 8 | B3c: exact stress command and validity; compaction wait and `disableautocompaction`; repair coordinator and bound | Amendment 2026-10-24 | Stable estimates between repairs. |
| 9 | B3d: S is a sum over R ranges; H defined; `jstat` → histogram `Total`; gaps named | Amendment 2026-10-24 | Undefined observables; `jstat` cannot attach here. |
| 10 | B3e: full sequence, bounds, tests for "fails" / "starts" with exact texts, cleanup | Amendment 2026-10-24 | No bounds or tests. |
| 11 | B3f: S(64)/S(16) = S(16)/S(4) = 4; S = 3 × 2^d; data term; H ≤ s; control S = 3,072 | Amendment 2026-10-24 | Three ranges; absolute values. |
| 12 | B3g: definitions and seven rows added | Amendment 2026-10-24 | Audit group B. |
| 13 | B1: state the exact formula `floor(log2((T + I)/(L + I)))` with `T = ratio × space × 2^20 / RF` | Left for stage 3 | Wording; B2d/B3f use the method. |
| 14 | B3: measure the coordinator's off-heap received trees (direct memory) as a second real-resource reading | Left for stage 3 | Not needed for B3g; the budget's own rationale ("the coordinator must hold RF trees", `ValidationManager.java:60-61`) is about them. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-24 (unit 16:54–16:56 EDT; cluster shakedown 16:57 and 20:39–20:47 EDT; cluster run 1 20:49–20:55 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 159 GiB free at start (158 GiB at the cluster run); loopback 127.0.0.1, .2, .3 present on `lo0` (checked at start and by the harness) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork `-Xmx1024m` (`maxMemory` 1,056,309,248; default `repair_session_space` 62 MiB there). Nodes: G1, `-Xms1G -Xmx1G` (`MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`), shipped `jvm-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`) in all three: n1 and unit `$W/cassandra-run4` (`ant -Dlocal.repository=$W/m2 build-test`, 52 s), n2 `$W/cassandra-run4-n2`, n3 `$W/cassandra-run4-n3` (`ant jar`, 57 s / 52 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | filed `f361777`; amendments, fixes and harness uncommitted (sha256 values in §1) |
| Storage for node data | local SSD, `$W/node-rss/{n1,n2,n3}/{data,commitlog,hints,saved_caches,cdc_raw}` (≈ 253 MB live data per node), wiped before and after; JMX 7199 / 7299 / 7399; ports 7000, 7199, 7299, 7399, 9042 free before; no `CassandraDaemon` before or after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/repair_session_space-applySimpleConfig/` — `clone.log`, `build-test-run4.log`, `jar-run4-n{2,3}.log`, `unit-instrument/`, `unit/` (ant log, JUnit XML, `stage4.out`), `cluster-shake/` (attempt 3 only), `cluster-run1/` (`commands.log`, `summary.txt`, `stress.log`, `n{1,2,3}/{system,debug,gc}.log`, `<label>/{hist/*.txt,samples.csv,repair.log,n*-debug-segment.log,n*-prepared.txt,n*-created.txt}`, `startup-0MiB/`, `startup-300MiB/`) |

## 3. Runbook defects

Both found by the harness shakedown (step 1), before cluster run 1; neither changes B3f or B3g. Each was fixed in the case file (dated
"Runbook fix 2026-10-24") and the cluster tier then ran from its beginning. Evidence: [`shakedown/defects-evidence.txt`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/shakedown/defects-evidence.txt) (attempt 2's lines, copied during the session; attempt 3 overwrote that folder).

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | shakedown attempt 2 | B3b (and the amendment that repeated it) | `nodetool sjk mx -b …RepairService -mc -op setRepairSessionSpaceInMiB -a 4` fails: `Operation setRepairSessionSpaceInMiB/1 not found` (the setter belongs to the JMX attribute `RepairSessionSpaceInMiB`); `nodetool` exits 0, the knob stays 64 | Set with `sjk mx … -ms -f RepairSessionSpaceInMiB -v <s>`; the control's depth with `-ms -f RepairSessionMaxTreeDepth -v 10` | Fixed 2026-10-24; cluster tier started after it | none (uncommitted; sha256 `ad89b5b4…d8b3`) |
| 2 | shakedown attempt 2 | B3d | The line at `ValidationManager.java:85` is logged before `trees.init()`: "size 3, … 268 bytes" at every value (R one-leaf trees). The observable S as written cannot move with the knob | S read from `Prepared AEService trees of size {S}` (`Validator.java:158`, after `init()` at `:120-124`); R and P still from `:85` | Fixed 2026-10-24 | same |

Harness bugs fixed in the shakedown (not case defects): the compaction wait grepped a 4.x output format; `stop_node` used a global `$n` under bash 3.2 and stopped n3 instead of n1, so a node was left running at the end of attempt 2 (killed by hand, checked gone); the samples-with-tree counter read the timestamp column.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stage4.out`, `junit-testsuite.txt`); [`run1/cluster/`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `stress-results.txt`; per label `repair.log`, `samples.csv`, `n*-prepared.txt`, `n*-created.txt`, `n*-idle-histo-lines.txt`; `startup-0MiB/lines.txt`, `startup-300MiB/lines.txt`).

### 4.1 Readings

**Unit tier** (all from `run1/unit/stage4.out`; JUnit 1 test, 0 failures, 0 errors; partitioner `ByteOrderedPartitioner`, RF 1; 10 sstables per load, `rowCount` 262,144 every time)

| s (MiB) | depth cap | read-back | d(s) | leaves (one tree) | 2^d | `measureDeep(trees)` B | limit B | ratio |
|---|---|---|---|---|---|---|---|---|
| 1 | 20 | 1 | 12 | **4,096** | 4,096 | 498,128 | 1,048,576 | 0.475 |
| 2 | 20 | 2 | 13 | **8,192** | 8,192 | 991,376 | 2,097,152 | 0.473 |
| 4 | 20 | 4 | 14 | **16,384** | 16,384 | 1,976,624 | 4,194,304 | 0.471 |
| 8 | 20 | 8 | 15 | **32,768** | 32,768 | 3,943,712 | 8,388,608 | 0.470 |
| 16 | 20 | 16 | 16 | **65,536** | 65,536 | 7,877,936 | 16,777,216 | 0.470 |
| control 16 | 12 | 16 | 16 | **4,096** | (cap 2^12) | 498,128 | — | — |
| 0 | — | — | — | `ConfigurationException`: `Cannot set repair_session_space to 0 < 1 mebibyte`; value afterwards **16** | | | | |

Value lines for B3f (printed by the same run, before the cluster tier): Murmur3 d = 11, 13, 15 at the per-range budgets for 4, 16, 64 MiB (466,033 / 1,864,135 / 7,456,540 B), unchanged at 0.95× and 1.05×.

**Cluster tier** (stress: 3,000,000 partitions, 0 errors, 30,140 op/s, 99 s; each node 3 sstables, 253 MB live, ≈ 2.96 M partitions estimated; every repair exit 0, 7.3–8.0 s; per node one `Created` and one `Prepared` line per repair, `Created 3 merkle trees … 3000192 partitions`; 8 histogram samples per node per repair, 6–7 with tree objects; idle histograms with no tree objects before every repair)

| Capacity value | Run | Read-back (n1/n2/n3) | S per node (n1 = n2 = n3) | predicted S | H_max per node (B) | limit (B) | live-heap Δ per node (support) | Evidence |
|---|---|---|---|---|---|---|---|---|
| default | A | 64 / 64 / 64, depth 20 | **98,304** | 3 × 2^15 = 98,304 | 7,864,176 | 67,108,864 | 15.2–17.3 MB | `cluster/default/`, `summary.txt` |
| 4 MiB | A | 4 / 4 / 4, depth 20 | **6,144** | 3 × 2^11 = 6,144 | 491,376 | 4,194,304 | 0.93–1.14 MB | `cluster/s4/` |
| 16 MiB | A | 16 / 16 / 16, depth 20 | **24,576** | 3 × 2^13 = 24,576 | 1,965,936 | 16,777,216 | 3.59–3.85 MB | `cluster/s16/` |
| 64 MiB | A | 64 / 64 / 64, depth 20 | **98,304** | 3 × 2^15 = 98,304 | 7,864,176 | 67,108,864 | 14.4–14.7 MB | `cluster/s64/` |
| 4 MiB | control, depth 10 | 4 / 4 / 4, depth 10 | **3,072** | 3,072 | 245,616 | 4,194,304 | 0.47–0.66 MB | `cluster/ctl-s4/` |
| 16 MiB | control, depth 10 | 16 / 16 / 16, depth 10 | **3,072** | 3,072 | 245,616 | 16,777,216 | 0.47–0.66 MB | `cluster/ctl-s16/` |
| 64 MiB | control, depth 10 | 64 / 64 / 64, depth 10 | **3,072** | 3,072 | 245,616 | 67,108,864 | 0.47–0.66 MB | `cluster/ctl-s64/` |
| `0MiB` (n1 yaml) | startup | — | — | — | — | — | — | process exited after 2 s; `ConfigurationException … repair_session_space must be > 0, but was 0MiB`; no `Startup complete` (`startup-0MiB/lines.txt`) |
| `300MiB` (n1 yaml) | startup | 300 | — | — | — | — | — | `UN` and binary `running`; `WARN … DatabaseDescriptor.java:615 - A repair_session_space of 300MiB mebibytes is likely to cause heap pressure`; `Startup complete` (`startup-300MiB/lines.txt`) |

H_max = 80 B × S − 144 B at every value (`OnHeapLeaf` 32 B × S + `OnHeapInner` 48 B × (S − 3)). Depth restored to 20 on all nodes after the control (read back).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — one JVM, the test ran to the end with no failure [observed: `run1/unit/summary.txt`]; each read-back equals s, one tree per validation, and `ceil(log2 262,144)` = 18 > d(s) ≤ 16, so the data term never bound [observed: `stage4.out`]. Valid.
2. **Readings** — nothing unusual; every count is exact. `measureDeep` is 0.470–0.475 of the limit at every s [observed].
3. **Matched row** — B2g row 1, "leaves double with s, `measureDeep` ≤ s MiB — claim confirmed", with the amended requirements: leaves = 2^d(s) exactly at all five values (4,096 … 65,536), doubling per doubling; `measureDeep` ≤ s MiB at every s; s = 0 rejected with the predicted message and the value unchanged (16) [observed: `stage4.out`].
4. **Excluded rows** — "`measureDeep` > s MiB": max ratio 0.475 [observed]. "Leaves constant": ×2 per doubling [observed]. "s = 0 accepted": exception [observed]. Added rows: formula mismatch — none (2^d at every s) [observed]; partial scaling — none [observed]; rejection with value changed — value 16 afterwards [observed]; data term binds — 2^18 > 2^16 [observed]; control ≠ 4,096 — 4,096 [observed]; timeout / tree count / read-back — none [observed].
5. **Observed vs. inferred** — none load-bearing.
6. **Deviations and gaps** — `ByteOrderedPartitioner` (the test yaml's), not the cluster's Murmur3; the cluster tier uses Murmur3's own d.
7. **Core question** — the knob sets the tree's leaf count exactly to the budget-derived 2^d(s), doubling per doubling, with the real deep size under the budget (≈ 0.47 of it); 0 is refused.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — stress wrote 3,000,000 partitions with 0 errors [observed: `cluster/stress-results.txt`, `summary.txt`]; every read-back equals the intended value on all three nodes, including the unset default 64 [observed: `summary.txt` `KNOB` lines]; R = 3 and P = 3,000,192 per node in every `Created` line, so P/3 ≈ 1,000,064 > 2^15 (data depth 20) [observed: `n*-created.txt`]; every repair exited 0 with `Repair completed successfully` [observed: `repair.log`]; ring of three `UN` nodes with the equal-thirds tokens [observed: `summary.txt` `RING`, `YAML`]. Valid.
2. **Readings** — the three nodes agree exactly at every value [observed]. The 300 MiB warning comes from line `:615` (the run's line numbers match the source) [observed: `startup-300MiB/lines.txt`]. The repairs took 7–8 s, so the 1 s sampler caught the trees in 6–7 of 8 samples per node [observed: `samples.csv`].
3. **Matched row** — B3g row 1, "S ∝ s, histogram ≤ s — claim confirmed", with the amended requirements: on every node S(16)/S(4) = 24,576/6,144 = 4 and S(64)/S(16) = 98,304/24,576 = 4; S = 3 × 2^d at each s (6,144 / 24,576 / 98,304) and S(default) = S(64); H_max ≤ s MiB (0.49 / 1.97 / 7.86 MB against 4 / 16 / 64 MiB); startup with `0MiB` refused with the exact message and `300MiB` started with the exact warning [observed: `n*-prepared.txt`, `samples.csv`, `startup-*/lines.txt`].
4. **Excluded rows** — "S constant": ×4, ×4 [observed]. "Histogram ≫ s" (H > s MiB): H_max/limit ≤ 0.12 [observed]. "Not ×4 or S ≠ 3 × 2^d": exact [observed]. "Startup with 0 completes": exited, no `Startup complete` [observed]. "300 refused": started [observed]. "Read-back ≠ s / R ≠ 3 / line missing / repair failed / stress errors": none [observed]. "Data term binds": P/3 ≈ 10^6 > 2^15 [observed]. "Control S ≠ 3,072": 3,072 at 4, 16, 64 MiB on every node [observed]. "No histogram sample with tree objects": 6–7 per node per repair [observed].
5. **Observed vs. inferred** — that H measures the replica's own validation tree [inferred: one validation per node per repair, and the coordinator's received trees are off heap by default, `Config.java:212`; consistent with H_max = 80 B × S − 144 exactly]. The match does not depend on it: S alone satisfies the S rows, and H ≤ s holds by a wide margin.
6. **Deviations and gaps** — (i) Two runbook fixes before run 1 (§3). (ii) H counts shallow node objects only (80 B per leaf and inner pair); the live-heap rise during the repair (support) was ≈ 0.93 / 3.6 / 14.5 MB per node at 4 / 16 / 64 MiB, i.e. it follows the knob and stays below s/RF (1.4 / 5.6 / 22.4 MiB), and the unit tier's `measureDeep` gives the full deep size (≈ 0.47 × budget). (iii) The coordinator's off-heap received trees (three per repair) were not measured. (iv) All three nodes on one host (amendment B3a).
7. **Core question** — the tree each replica builds follows the knob exactly: three ranges of 2^11, 2^13, 2^15 leaves at 4, 16, 64 MiB, the depth set by the budget (the data would allow 2^20), and its heap (node objects, and the live-heap rise) scales with the knob and stays under it. The startup check refuses 0 and only warns above heap/4. The constraint caps the Merkle-tree heap of a validation.

**Conclusion (cluster tier):** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/run1/selfcheck.py) (independent of the harness: it re-reads `unit/stage4.out` and the JUnit XML; each node's **whole** `debug.log` for every `Created` and `Prepared` line in file order; the **raw `jcmd` histogram files** of every sample, re-parsed; `repair.log`, `stress.log`, both startup `system.log`/`node.out`; and the read-back lines in `commands.log`) recomputes every amended B2f/B3f prediction: **266 checks, 0 failed**, exit 0 ([`run1/selfcheck.out`](repair_session_space-applySimpleConfig-repair_session_space--autonomous/run1/selfcheck.out)).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Stress totals from `stress.log`; read-backs (from `commands.log`, the one input written by the harness's own `sjk` reads); R, P from the raw `debug.log`; data term per label and node. |
| 2. Readings | yes | Seven `Prepared` and seven `Created` lines per node, in label order; the three nodes equal. |
| 3. Matched row | yes | S = 3 × 2^d recomputed with the unit run's printed d; ×4 ratios and S(default) = S(64) per node; H re-derived from 168 raw histogram files ≤ s MiB; startup texts found in the raw logs; unit leaves = 2^d, doubling, `measureDeep` ≤ limit, the s = 0 line. |
| 4. Excluded rows | yes | Control 3,072 on every node at every s; idle histograms without tree objects; samples with tree objects in every repair; the `:85` size field equals R in all 21 lines (defect 2 confirmed in run 1). |
| 5. Observed vs. inferred | yes | The inference in part 5 is not needed by the matched row. |
| 6. Deviations and gaps | yes | Stated; none bears on the matched rows. |
| 7. Core question | yes | Knob → S (exact) → heap reading under the knob; startup check as traced. |

### 5.2 Run 2?

**No** — decided 2026-10-24. Every reading is an exact count matched to an exact prediction on three nodes and at the unit tier, the
conclusion rests on no inferred statement, and the independent self-check over the raw files holds with no failures. The result confirms
the case's claim (no refutation, no bypass).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "With `repair_session_max_tree_depth` = 20, the leaves per single-range validation tree equal
`2^min(ceil(log2 partitions), floor(log2(space·2^20/RF / (leaf+inner bytes))))`, so tree heap is ≤ the budget and halves when the budget halves;
a value of 0 is rejected." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: leaves = 2^d(s) exactly at 1–16 MiB, doubling; `measureDeep` 0.47 × limit; 0 rejected, value unchanged; control 2^12) | caps | run 1 + self-check | 2026-10-24 |
| Cluster | **Confirmed** (row 1: S = 6,144 · 24,576 · 98,304 at 4 · 16 · 64 MiB and the default, ×4 per ×4 on all three nodes; H ≤ 0.12 × s; control 3,072; `0MiB` refused at startup, `300MiB` warns and starts) | caps | run 1 + self-check | 2026-10-24 |

**Feedback filed:** the case file's section D (uncommitted); the twelve step-0 amendments and two runbook fixes are in the case file, dated,
with their sha256 rows in `_INDEX-advisor.md` §2; `_INDEX-advisor.md` §1 Stage 4 column and the coverage line updated. No section was
amended for a refutation (none occurred).
