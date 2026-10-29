# none-addall-size--autonomous — stage-4 results  <!-- file: results/none-addall-size--autonomous.md -->

> **Case:** [`none-addall-size--autonomous`](../../stage3-ai-deep-read/cases/none-addall-size--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap, real usage); cluster `n/a`; the unsharedHeapSize() counter differs by branch (add() :178 double count), recorded as feedback; no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` (real memory); counter divergence recorded ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D). `none` type, operand kind 1 (counts of held data) ([`none-type-design.md`](../none-type-design.md)); unit-tier measurement only.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendment (dated 2026-10-29, B2/B3 replaced), **frozen before any sweep reading: `79b17d722064dab5ecade5c6a6ad522186d6381a7f6ed09803bdac638ebd27bc`**. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D; section D is filled after the verdict and its sha256 is recorded in section 8. |
| **Harness** | [`harness/none-addall-size--autonomous/`](../harness/none-addall-size--autonomous/README.md), uncommitted: `AddAllBranchTest.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`. |
| **Tiers and values** | Unit (B2): arms P (capacity n+m) and G (capacity n); S1: n = 10,000, m = 500, 999, 1000, 1001, 2000, 10000; S2: m = 1,000, n = 9999, 10000, 10001, 10010; equal-content twin (merge vs 1000 one-tombstone add() calls); growth-factor control 3.0; two noise blocks; 3 warm-up + 7 repeats each. Cluster (B3): `n/a` (reason in B3 and section 8). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the guarded quantity is the heap of one `RangeTombstoneList` (four arrays plus bound objects), a byte quantity derivable from counts; the check itself bounds none. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach, with the reason | Met (after amendment) | No knob: operand sweep (none-type-design.md section 3). B2 as filed had ratios 10m, 10m+1 and n = m; the amendment fixes S1 (6 values of m), S2 (4 values of n) and an equal-content twin. |
| A. Core question | real resource measured, not only the counter (gap named) | Not met -> Met | B2d read `unsharedHeapSize()` as retained heap; source shows that counter is branch dependent (`add()` :178 double count). Amended to per-call thread allocation and `ObjectSizes.measureDeep` (jamm), the counter reported separately. |
| A. Core question | usage driven to the limit and past it | Met (n/a for `none`) | there is no limit; both sides of the literal 10 are driven (m = 999 / 1000, n = 10000 / 10001). |
| A. Core question | positive control for a negative claim | Met | growth factor 3.0 vs 1.5 (DatabaseDescriptor.java:4654), B2f (vii); closed-case control (`memtable_heap_space`) not needed at unit tier. |
| B. Logic | each step says what it establishes | Met | B2 amended is numbered by purpose. |
| B. Logic | prediction stated in numbers or a clear relation | Not met -> Met | B2f filed had no numbers; amended: 20 bytes per slot, closed forms, tolerances, the counter difference 1000 x bsz. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly -> Met | rows added for the counter-only divergence, the noise band, invalid runs and missed arithmetic. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (adapted) | no ceiling exists; the check never disallows; both branches are observed with Byteman. |
| B. Logic | alternative explanations and their controls | Met | growth is common to both branches (arm P isolates the branch, arm G shows growth), content equality by the twin. |
| C. Specific | human can follow it | Met | A1-A3, B1, amendment. |
| C. Specific | AI can run it without re-deriving the code path | Met after amendment | trigger, bounds, sizes, windows and commands are exact. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after amendment | values listed; 3 warm-up + 7 repeats; no sampling. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | harness written in step 1; build copy on `pc39`. |
| D. Runnable | workload arithmetic reaches the limit | Met | largest list 20,000 tombstones, a few MB; `-Xmx2g`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | re-read in `cassandra/cassandra-5.0.9`; all of RangeTombstoneList.java 184-232, 520-529, 658-686, 770-778, MutableDeletionInfo.java 118/142, Config.java 798/802, DatabaseDescriptor.java 4654, StorageServiceMBean.java 1166/1172, RangeTombstoneListTest.java 235/263/281/719 are correct; the A2 sentence about `unsharedHeapSize()` is wrong (see below). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Retained size and per-call allocation instead of the counter alone; equal-content twin (amendment, B2) | Applied 2026-10-29 | `add()` :178 adds `boundaryHeapSize` a second time after `setInternal` :766 on every path but the first-element path, so `unsharedHeapSize()` differs by branch for equal content. |
| R2 | Numbers for B2f; sweeps fixed; noise floor and growth control (B2) | Applied | filed prediction had none. |
| R3 | B3 declared `n/a`: branch not togglable at scale (n > 1,000 takes add() in both phases), effect below heap noise | Applied | the filed phases both use add(). |
| R4 | For stage 3: A2's sentence on `unsharedHeapSize()` and B2d's `measureDeep` doubt are wrong (section D) | left for stage 3 (recorded in D) | feedback only. |

**Pre-run checks (instrument only, before the freeze, no sweep reading):** `javac` of the test against the build; `TestScript` parse of the Byteman rules (2 rules type-checked, no errors); the test's own instrument checks run in `checkonly` mode on the node: the known-answer window (8 MiB `byte[]` read as 8,388,624 bytes, expected 8,388,608 to 8,454,144) and the empty window (0 bytes). No point of the sweep was run before the freeze.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 |
| Node | `pc39` = `node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/s4-none` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL in 1 min 9 s |
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `none-addall-size--autonomous/run1/harness.md5` |
| Storage for node data | none (no daemon); JUnit scratch under `~/stage4-logs/none/` on local `/dev/sda3` |
| Full logs (outside the repo) | `pc39:~/stage4-logs/none/none-addall-size--autonomous/run1/` |

## 3. Runbook defects

None. (Deviation from the filed B2a: the plain `java` launcher with `JUnitCore` replaces `ant testsome`, and the default collector replaces `-XX:+UseSerialGC`; both are set by the 2026-10-29 amendment before the freeze.)

## 4. Run 1

**Scope:** the whole amended B2; B3 `n/a`. **Command log:** `none-addall-size--autonomous/run1/` (`session-plain.log`, `session-bm.log`, `analysis.txt`, `selfcheck.txt`, `raw-plain/raw.csv`, `raw-bm/raw.csv`, `trace-summary.txt`). Two JVM runs on `pc39`, the plain one for readings and the Byteman one for the branch trace.

### 4.1 Readings

**Unit tier** (T = threshold terms of B2f; bytes are per call of `addAll`, or per whole operation for the twin)

| Test or assertion | Result | Evidence |
|---|---|---|
| Instrument known-answer (8 MiB `byte[]`) and empty window | 8,388,624 bytes (expected 8,388,608 to 8,454,144); empty window 0 bytes | `junit-stage4-lines-and-trace-heads.txt` |
| Arm P (capacity n+m), every point of S1 and S2 | median 0 bytes at all 20 points, range 0 | `analysis.txt` (i) |
| Arm G (capacity n), S1 m = 500, 999, 1000, 1001, 2000 | 300,064 bytes each (capacity 15,000); m = 10,000: 750,128 (capacity 22,500) | `analysis.txt` (ii) |
| Arm G, S2 n = 9999, 10000, 10001, 10010 | 300,056 / 300,064 / 300,104 / 300,376 (frozen formula 300,044 / 300,064 / 300,104 / 300,364; +12 bytes at n = 9999 and 10010, array alignment) | same |
| Branch-adjacent pairs, arms P and G | S1 m = 999 vs 1000: 0 vs 0 (P), 300,064 vs 300,064 (G); S2 n = 10000 vs 10001: 0 vs 0 (P), 300,064 vs 300,104 (G; growth-adjusted difference 0); the differences are inside max(2 x floor, 1,024) | same, (iii) |
| Equal-content twin (n = 10,000, m = 1,000) | T-merge vs T-add: 0 vs 0 (P); 300,064 vs 300,064 (G). `measureDeep` 2,860,224 vs 2,860,224 (P) and 2,940,224 vs 2,940,224 (G); results `equals` the reference | same, (iii), (v); `selfcheck.txt` |
| Real retained size per element | `measureDeep - (20 x capacity + 64)` over `size()`: 240.01 to 240.02 bytes for every point (spread 0.003 percent) | `analysis.txt` (v) |
| Noise floor | 0 bytes in both arms (two blocks of 7: medians 0 / 0 in P, 300,064 / 300,064 in G, ranges 0) | `analysis.txt` NOISE |
| Branch per call (Byteman JVM) | ADD 20,080 calls, MRG 190 calls, no call contradicts `n > 10 m`; m = 500, 999 and n = 10001, 10010 only ADD; m = 1000, 1001, 2000, 10000 and n = 9999, 10000 only MRG; all 20,000 one-tombstone twin calls ADD | `trace-summary.txt`, `analysis.txt` (iv) |
| `size()` = n + m and `equals(reference)` | all 203 rows; `equals` true at every point's last repeat | `analysis.txt` (iv) |
| Counter, twin | `unsharedHeapSize()` T-add minus T-merge = 240,000 = 1000 x `bsz` (240) in both arms, capacity equal (11,000 and 15,000) | `analysis.txt` (vi) |
| Counter at the flip, arm P | m = 999 (add) 5,499,384 vs m = 1000 (merge) 5,259,872, while `measureDeep` is 2,859,976 vs 2,860,224 | `selfcheck.txt` NOTE |
| Control, growth factor 3.0 (arm G, n = 10,000, m = 1,000) | 600,064 bytes (capacity 30,000) vs 300,064 at 1.5 (ratio 2.00); `unsharedHeapSize()` rises by 300,000 | `analysis.txt` (vii) |

**Cluster tier:** `n/a: operand cannot be toggled at scale and the effect is below heap noise` (B3).

### 4.2 Conclusion and logic

1. **Validity** — valid. The check executed on both sides at the planned points [observed: `trace-summary.txt`], the results have n + m tombstones and equal the reference [observed: `analysis.txt` (iv)], the instrument read an 8 MiB known answer [observed], and the control moved [observed: 600,064 vs 300,064 bytes]. The plain run used no agent besides jamm.
2. **Readings** — nothing unusual: every deterministic allocation reading has range 0, so the noise floor is 0 and any difference above 0 bytes is a difference; the 12-byte excess over the closed form at n = 9999 and 10010 is array alignment [inferred: JVM object alignment of the two `int`/`long` arrays; within the frozen +-10 percent].
3. **Matched row** — B2g row 2 (amended): (iii), (iv), (v) and (vii) hold, and (vi) holds too: per-call allocation and `measureDeep` are the same on both sides of the literal (S1 m = 999|1000, S2 n = 10000|10001, the twin), growth is the same in both branches, and the control moved. The accounting divergence of `add()` :178 is real and exact: the add() branch reports 1000 x `bsz` more `unsharedHeapSize()` for the same content.
4. **Excluded rows** — "branch gates an allocation or retention" (Refuted): no, no difference in bytes allocated or `measureDeep` between branches [observed]; "not resolved": no, the floor is 0 and the differences are 0; "invalid": no, both branches observed, sizes right, control moved; "numeric miss": none apart from the +12 bytes inside tolerance.
5. **Observed vs. inferred** — everything above is observed except the alignment explanation in part 2 and the statement that the counter excess comes from :178 [inferred: the source reading in the amendment; the observed 240,000 = 1000 x 240 matches it exactly].
6. **Deviations and gaps** — unit tier only, one JVM per mode, one run; the counter divergence feeds `BTreePartitionUpdater.java:121` (memtable heap accounting) but the node-level effect (an inflated accounted heap flushing a memtable earlier) was not measured and cannot be at heap-noise resolution (B3); allocation is read for the calling thread only (no other thread allocates in `addAll`); a run of 10,000 to 20,000 tombstones is small next to a real memtable.
7. **Core question** — Usage follows the data (and the growth factor), not the check: allocation and retained size are equal on the two sides of `size > 10 * tombstones.size` and the growth factor moves them (parts 3 and 4). Flipping the branch changes only CPU work and, separately, the reported `unsharedHeapSize()` counter (by 1000 x `bsz` for 1000 tombstones) through the double count in `add()`.

**Conclusion (one line):** B2g row 2 (amended) — Confirmed: the check does not cap the real memory; the counter divergence in `add()` is recorded as feedback.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `raw-plain/raw.csv`, `raw-bm/trace.txt` re-parsed by `harness/none-addall-size--autonomous/selfcheck.py` (own growth arithmetic and expected call counts, no use of `analyze.py`): `selfcheck.txt` "ALL PASS" (25 checks).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: 203 rows, sizes n + m, equals true, ADD 20,080 / MRG 190 equal the count derived from the point list, no contradiction with `n > 10 m`. |
| 2. Readings | yes | closed forms recomputed independently; arm P all calls at most 4,096; floors 0. |
| 3. Matched row | yes | twin deep equal, counter difference 240,000 = 1000 x 240, control 600,064. |
| 4. Excluded rows | yes | no branch difference in bytes or deep size. |
| 5. Observed vs. inferred | yes | the two inferences affect no verdict row. |
| 6. Deviations and gaps | yes | listed; the node-level effect of the counter is the main limit. |
| 7. Core question | yes | follows the audited steps: branch proof, same content, bytes and retained size, control. |

### 5.2 Run 2?

**No** (2026-10-29): the readings are exact (range 0) in a deterministic single-thread test and were re-derived by an independent script; the only open point (node-level effect of the counter) is below what the unit tier resolves, so a second unit run adds nothing.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1, amended reading):** the real retained heap and the allocation of a `RangeTombstoneList` after `addAll` do not depend on whether the `size > 10 * tombstones.size` branch is taken, and no node-level memory follows the factor 10. (The filed B1 names `unsharedHeapSize()`; the audit found that counter is branch dependent and splits real size from counter.)

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (amended B2g row 2: equal allocation and retained size across the branch, both branches observed, control moved; counter divergence of exactly 1000 x `bsz` recorded) | does not cap (real usage); the `unsharedHeapSize()` counter is higher on the add() branch (:178 double count) | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: operand cannot be toggled at scale and the effect is below heap noise` | not run | | 2026-10-29 |

**Positive control** (negative-estimate file): `setRangeTombstoneListGrowthFactor(3.0)` moved allocation from 300,064 to 600,064 bytes (capacity 15,000 to 30,000) and `unsharedHeapSize()` by +300,000, on the same instrument [observed: `analysis.txt` (vii)].

**Noise floor:** 0 bytes (two identical blocks, range 0) [observed].

**Caveat on the class:** true negative holds for the check as a limit on real memory. The inflated counter feeds the memtable's accounted heap (`BTreePartitionUpdater.java:121`), so the branch can influence when a memtable is flushed; that second-order effect is not measured and is recorded in section D for stage 3.

**Feedback filed:** section D of the case file updated 2026-10-29 (no commit by this session); final sha256 of the case file with section D filled: `59f067a460eb6433b73c7653e6c7ece4ff2782bad1f155bbdf7cb5c30032826e`.
