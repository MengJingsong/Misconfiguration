# tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous — stage-4 results  <!-- file: results/tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous`](../../stage3-ai-deep-read/cases/tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous.md)
>
> **Status:** **verdict filed 2026-10-26** — unit **Confirmed** (does not cap), cluster **Confirmed** (does not cap). Claim tested: disk usage does not follow `tombstone_threshold`; the threshold is only one gate of a single-SSTable compaction trigger. Run 1 only, no run 2.
>
> **Outcome class:** **true negative** — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** guided / autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | FROZEN 2026-10-26 (before any reading; retaken once after amendment A8, see below): repository HEAD `93d6365` plus the uncommitted file; whole-file sha256 `9e03fc41b28a7560bfde88cfdd0f6da0374c7822fe2ac8d36947db76f87488ab` (first freeze, before A8: whole file `07ca08663b8baf292d5e1bb7459c8f367b19842f41c9ca517d195c3484913fb2`, B2f-B2g `213c17eb2bbf28129a9ce5b532a6bdd65bac826584e621a34c82717a1c06bea0`; A8 changed one clause of P2 after a unit-test shakedown showed the X=0.0 overlap cell is true by `:444`, a source-logic correction made before run 1; B3f-B3g unchanged; filed version before all amendments: `23d93853c2f8d6056fed9929ca8818a11566159426fc11d764d0fe230db2c942`); sha256 of the text of B2f-B2g (from `**B2f.` up to `**B2h.`) `e6cbf2449071215e4712ae709bc8f3dc0526c792d80575dd584d762c326546fa`; of B3f-B3g (from `**B3f.` up to `**B3h.`) `da532791686b9b503fc196cad974123c227d03f929f9cba35d78862d7e169f4c`. Template note: **Guided file:** the commit that holds the case file, and the hash of §9's text (`sed -n '/^## 9\. /,/^## 10\. /p' <case file> \| git hash-object --stdin`), recorded after the audit's amendments; §9a is frozen at this version. **Autonomous file:** the commit that holds the file, and the sha256 of the whole file (`sha256sum`) recorded after the audit's amendments; this hash goes in `_INDEX.md` (column sha256) |
| **Harness** | `harness/tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous/` (written after the first freeze, before run 1; uncommitted, the orchestrator commits) |
| **Tiers and values** | Unit: X in {0.0, 0.2, 0.5, 0.9, 1.5} x f in {0.1, 0.3, 0.6, 0.9}, gates open and closed, byte step, forced-compaction control. Cluster: one node, 14 tables (X in {0.05, 0.2, 0.4, 0.7, 1.5} at 50 % and 15 % droppable, default, interval gate, overlap gate, `nodetool compact` control). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: table disk bytes held by droppable cells; the check compares a cell ratio (counter), honest in A2 that no byte bound exists. Real bytes: `onDiskLength` (unit), `du -sb` (cluster). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | B2b five values with 0.2 the default; B3b five values plus a no-option table. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d read bytes and the ratio; the filed workload would not have produced r = f (A1 of D1). **Amended**. The strategy's value at decision time is read by `sstablemetadata` (proxy, named). |
| A. Core question | usage driven to the limit and past it | Not met → fixed | the filed delete-into-second-SSTable gives r near 1 and 0, and purge is blocked by the overlapping data SSTable (D1 A1); X=0.5 vs r = 0.5 is a coin flip (D1 A5). **Amended**. Negative file: positive control present in B2g/B3g but too loosely defined; **amended** (forced compaction, `pc`). |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered, each tied to a row (after the amendments). |
| B. Logic | prediction stated in numbers or a clear relation | Not met → fixed | B2f/B3f named no tolerance or range; the boolean oracle ignored the float promotion. **Amended** (D1 A2, A6). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Not met → fixed | overlapping rows; no row for a gate that fails, an instrument that cannot move disk, or end sizes that follow X. **Amended** (D1 A3). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (after A3) | for a negative file: closed-gate table keeps r > X while its open sibling falls (the disallow-branch-absent evidence) and the control moves. |
| B. Logic | alternative explanations and their controls | Partly → fixed | never-purge control was a system property that cannot be switched in one JVM (D1 A2); noise by repeat only if ambiguous. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 mechanism and B1 are clear; D1 A4 states how the claim is read. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → fixed | the ratio construction, the way to trigger STCS's check and the wait arithmetic were missing (D1 A1, A5). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → fixed | paths, row counts, TTL/wait, sampling interval fixed in B3a-B3e (D1 A5, A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | unit test, node yaml builder, loader and runner are step-1 work (harness folder); `ant build-test`/`ant jar` done on the node, Python driver bundled with the tree. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met (after A5) | 14 x 45 MB on tmpfs (126 GiB free), wait 210 s + 300 s; unit 8 x 1 MB tables. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `AbstractCompactionStrategy.java:69, 75, 86, 117-118, 397-446, 408, 448-465`, `SizeTieredCompactionStrategy.java:91-105`, `LeveledCompactionStrategy.java:523-545`, `TimeWindowCompactionStrategy.java:163`, `StatsMetadata.java:166-174`, `SSTableMetadataViewer.java:362-363` re-read: hold (D1 A7). TWCS can set `disableTombstoneCompactions` (`:78`); outside the STCS tiers run here. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | TTL'd `UPDATE` cells in one SSTable for the ratio (A1) | Applied 2026-10-26 | filed construction gives r near 1 and 0, not f |
| R2 | Float-aware oracle, never-purge via `setNeverPurgeTombstones`, tolerance, numbers (A2, A6) | Applied 2026-10-26 | prediction must be decidable |
| R3 | Rewrite conclusion rows without overlap (A3) | Applied 2026-10-26 | every outcome one row |
| R4 | State how the claim is read (A4) | Applied 2026-10-26 | the residual ratio is bounded by X with all gates open |
| R5 | Cluster table set, waits, autocompaction enable (A5) | Applied 2026-10-26 | STCS's tombstone check only runs on a submitted check; histogram rounding |
| R6 | TWCS and LCS use the same check; LCS (`:539`) re-tests the threshold before the call | Left for stage 3 | no tier for them here |


**Agreement criteria** — only if run 2 is chosen; not chosen (see 5.2).
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 20:56 EDT; cluster 20:56 to 21:21 EDT) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; port slot 3 (127.0.3.1, JMX 7130); other sessions ran on the node at the same time | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | two copies from `copy-source.sh` at repository HEAD `93d6365` (tag `cassandra-5.0.9`): `~/s4-b10-td-u` (`ant build-test`, 1 min 27 s; unit tier) and `~/s4-b10-td-n` (`ant jar`, 1 min 26 s; node) | — |
| Case-file commit / harness commit | `93d6365` + the uncommitted amendments D1 (sha256 in §1) / uncommitted; md5 (first 12 hex): `TombstoneThresholdProbeTest.java` ca476c0469ec, `analyze-unit.py` 167ce294c643, `cluster-run.py` f4cd88c2dea1, `load.py` 8aea4bbdeaf7, `make-node-yaml.sh` 30615fbf016a; `analyze-cluster.py` and `selfcheck.py` were edited after the cluster run (see §3, D3, D4) | — |
| Storage for node data | `/dev/shm/s4-b10-td` (tmpfs, removed afterwards); nothing on `/proj` | — |
| Full logs (path, outside the repo) | `~/s4-b10-td-logs/run1/{unit,cluster}/` (node `pc07`; `session.log`, `system.log`, `debug.log` are only there); plumbing shakedowns in `~/s4-b10-td-logs/shake/` and `shake-unit.out` (small scale, not readings, not cited) | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | audit | B2c, B3c | the filed workload (delete a fraction into a second SSTable) cannot give r = f and cannot purge | amendments A1, A5 (TTL'd `UPDATE` cells in one SSTable) | 2026-10-26, before any run | uncommitted (orchestrator) |
| D2 | unit shakedown | B2f P2 | the prediction said the overlap cell at X=0.0 is false; `:444` makes it true | amendment A8, freeze retaken (§1); made before run 1; the shakedown output is not cited | 2026-10-26, before run 1 | uncommitted |
| D3 | cluster run 1 | B3c / harness | memtable flushes at the memory limit (`Reason: MEMTABLE_LIMIT`, 3 parallel loaders, 14 tables) split every table into two SSTables of 19.6 and 24.5 MiB (a05 as example) instead of one; both of each table carry r = 0.5 (or 0.15), so each compacts alone and the B3f numbers are unaffected. The harness EXPECTED line "every table except go has exactly 1 sstable" read NO, and the analyzer's H3 (one Compacted line per table) first read NO for the same reason | analyzer H3 changed to "one line per sstable"; no prediction or row touched (H3 is not in B3f/B3g); the run was not restarted | 2026-10-26, after the run, claim-neutral | none (harness only) |
| D4 | self-check | harness | the first self-check script for the cluster counted `Compacted` lines by regexes that did not match the 5.0 log format (size units, trailing comma) and expected one SSTable per table | regexes and expectation fixed on the shakedown log before run 1's logs were checked against it | 2026-10-26 | none (harness only) |

Run 1 was not restarted for a defect.

## 4. Run 1

**Scope:** both tiers in full. **Command log:** `tombstone-threshold-worthDroppingTombstones-droppableRatio--autonomous/run1/` (`unit/{summary.txt,analysis.txt,test.out,selfcheck-unit.txt}`, `cluster/{summary.txt,analysis.txt,du.csv,ratios.csv,schema-readback.txt,ks-compactions-and-limit-flushes.txt,selfcheck-cluster.txt,load.out}`).

### 4.1 Readings

**Unit tier** (N = 10000 partitions, 100 B values; `unit/summary.txt`, `unit/test.out`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ant: 1 test, 0 failures, 0 errors | as expected | `unit/summary.txt`, `selfcheck-unit.txt` |
| instrument I1: strategy `tombstoneThreshold` equals the float of X after each of 40 ALTERs | yes | `unit/analysis.txt` I1 |
| instrument I2: r = 0.100000 / 0.300000 / 0.600000 / 0.900000 for f = 0.1 / 0.3 / 0.6 / 0.9 | yes | `unit/test.out` `info` lines |
| instrument I3: X = 0.0, gates open: worth true for every f | yes | I3 |
| P1: gates open, worth == (r > float32(X)) in all 20 cells (X = 0.9 with f = 0.9: true); X = 1.5 false for every f; a task from `getNextBackgroundTask` exactly when worth is true | holds, 0 mismatches | P1, P1b, P1c |
| P2: interval 86400: worth false in all 5 cells (r > X in 3); overlap + unchecked false at f = 0.6: false for X = 0.2, 0.5, 0.9, 1.5 (r > X for 0.2, 0.5), true at X = 0.0; unchecked false, no overlap: as open; never-purge: false in all 5 | holds | P2a-P2d |
| P3: executed tasks: after/before = 0.689 (f 0.3, X 0.2), 0.392 (0.6, 0.2), 0.097 (0.9, 0.2), 0.098 (0.9, 0.9); no task: bytes identical before and after at f 0.1 (X 0.2, 0.9), f 0.3 (X 0.9), f 0.6 (X 0.9) although 10, 30, 60 % of the cells were droppable | holds | P3a-P3c |
| P4 positive control: `forceMajorCompaction` at X = 1.5, worth false: after/before = 0.895 / 0.690 / 0.390 / 0.097 | holds | P4 |

**Cluster tier** (one node, 14 tables x 200,000 partitions of 200 B, about 44.7 MB each; `cluster/summary.txt`, `du.csv`, `ratios.csv`)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| X = 0.05 / 0.2 / 0.4 / default 0.2, 50 % TTL'd, gates open | `a05, a20, a40, adef` | `sstablemetadata` ratio before the enable; `du` at the end of 300 s as a share of the peak; ratio after | 0.500; 0.483 / 0.483 / 0.484 / 0.483; 0.009 or 0.000 | `ratios.csv`, `du.csv`, C1, S1 |
| X = 0.7 / 1.5, 50 % | `a70, a150` | the same | 0.500; 1.000 over all samples; 0.500 | H1 |
| X = 0.05, 15 % | `b05` | the same | 0.150; 0.842; 0.000 | C2 |
| X = 0.2 / 0.4 / 0.7 / 1.5, 15 % | `b20, b40, b70, b150` | the same | 0.150; 1.000; 0.150 | H1 |
| X = 0.05, interval 86400 (gate closed) | `gi` | the same | 0.500; 1.000; 0.500 (ten times X) | H1, H2 |
| X = 0.05, interval 60, unchecked false, overlapping SSTable | `go` | the same | 0.500 (first SSTables) / 0.000 (overlap SSTable); 1.000; unchanged | H1, H2 |
| X = 1.5, then `nodetool compact` | `pc` | `du` over the window; after the compact | 1.000 over the window; 44,722,986 -> 21,610,349 B (0.483) | K1 |
| all | all | `Compacted` lines in `system.log`: 2 per compacting table (two SSTables each, one-SSTable input each), 0 in the eight holding tables, 1 in `pc` (the manual one); output/input 0.479-0.480 (group A) and 0.841 (`b05`) | consistent with du | H3, `ks-compactions-and-limit-flushes.txt` |
| all | all | SSTables per table at the flush | 2 (a05: 19.555 and 24.484 MiB), `go` 2 + the overlap SSTable | D3 |

### 4.2 Conclusion and logic

1. **Validity** — **[observed: `cluster/summary.txt`]** the node was UN with the native port running, heap `-Xms2G -Xmx2G`, the 14 tables carry the B3b options and gc_grace 10 (`schema-readback.txt`), `r` = 0.500 for group A, `adef`, `gi`, `go`, `pc` and 0.150 for group B before the enable (R1, R2) so the limit (r above the lower X values) was reached, no compaction ran before the enable (du equal to the peak), the autocompaction check was submitted once for all tables. Unit **[observed: `unit/summary.txt`]**: the instruments I1-I3 hold. Deviation D3 (two SSTables per table) is recorded; **[inferred: both SSTables of each table have the same r, each is compacted alone, and the share of bytes removed is the same]**.
2. **Readings** — **[observed]** nothing contradicts another. One anomaly: the `du.csv` row at t = 0 (taken right after the enable) shows 44.75 MB for `a05`, the old SSTable plus output in flight; all later rows are final.
3. **Matched row** — Unit, B2g row 1 ("P1 holds ..., P2 holds, P3 holds and P4 holds") **[observed: `unit/analysis.txt`]**: P1, P2, P3, P4 hold. Cluster, B3g row 1: `gi` and `go` keep a ratio of 0.5 (X = 0.05) and 1.000 of the peak while `a05` (same data and X, gates open) falls to 0.483; `a70`/`a150` stay at 1.000; `a05, a20, a40, adef` end within 0.001 of each other; `pc` falls to 0.483 after `nodetool compact` **[observed: `cluster/analysis.txt` R1 to S1, `selfcheck-cluster.txt`]**.
4. **Excluded rows** — Refuted (gate does not hold): `gi` and `go` never compacted (no `Compacted` line, du 1.000 in all 11 samples) **[observed: H1, H3]**. Refuted (follows X): the end sizes of `a05, a20, a40` differ by at most 0.001 (S1), and the unit bytes track f, not X (P3a: the same 0.097 at X = 0.2 and 0.9 for f = 0.9) **[observed]**. Not confirmed: r was inside the ranges, `a05` moved, `pc` moved after `nodetool compact` **[observed: R1, R2, C1, K1]**.
5. **Observed vs. inferred** — Inferred: (a) the closed gate is the reason `gi` and `go` do not compact: `gi` differs from `a05` only in the interval and `go` in `unchecked`/the overlap SSTable **[inferred: same data, one option changed, B3b; the unit tier shows the same boolean values at the check itself]**; (b) the threshold has an effect only as a gate and not on the amount reclaimed **[inferred: end sizes the same at 0.05, 0.2, 0.4 and default]**; (c) the 2 SSTables per table do not change the result (D3) **[inferred]**.
6. **Deviations and gaps** — D3. One node and one run of the cluster tier, no repeat (the readings are well inside the ranges). STCS only: the same check in LCS (`:539`) and TWCS (`:163`) is not exercised, and TWCS sets `disableTombstoneCompactions` (`TimeWindowCompactionStrategy.java:78`). The cluster tier did not drive the disk to an external limit; the claim is about the threshold and the table's own bytes. The nodetool enable was the trigger for the check; in normal operation the check runs on each flush and compaction completion, so a drop can be delayed by the interval (60 s here) but not removed.
7. **Core question** — At every threshold the amount reclaimed was set by the droppable share f (0.1 to 0.9) and by the gates, not by X: with all gates open an SSTable is compacted if and only if its ratio is above X (unit P1, cluster `a05` to `a150`), and then falls by f (0.483 for f = 0.5, 0.842 for 0.15); below X nothing is reclaimed although up to 60 % (unit) or 50 % (cluster) of the cells are droppable. With the interval gate closed (`gi`) or the overlap gate engaged (`go`) a droppable share ten times X (0.5 vs 0.05) stayed on disk for the whole window, so the residual ratio is not bounded by X. There is no byte-denominated limit. The threshold therefore does not cap disk (steps 3, 4, 5 and 6 above).

**Conclusion (one line):** unit — B2g row 1 (**Confirmed**, does not cap); cluster — B3g row 1 (**Confirmed**, does not cap).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-parsed with `harness/.../selfcheck.py` (its own parsers: float32 oracle and the ant XML for the unit tier; for the cluster tier the `system.log` `Compacted` lines with input/output sizes, `du.csv`, the raw `sstablemetadata` values in `session.log`, and the schema read-back), output in `run1/unit/selfcheck-unit.txt` (16/16 hold) and `run1/cluster/selfcheck-cluster.txt` (36/36 hold).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | schema options read back, ratio 0.500 / 0.150 before the enable, ant XML 1 test 0 failures, no ERROR line in `system.log`, no `Compacted` line before the enable |
| 2. Readings | yes | the `Compacted` lines' output/input (0.479-0.480, 0.841) match the du shares (0.483, 0.842) within 0.005 |
| 3. Matched row | yes | all P1-P4 and R1-S1 hold; B2g/B3g row 1 requires nothing else |
| 4. Excluded rows | yes | no compaction in `gi`/`go` for 11 samples over 300 s; end sizes independent of X |
| 5. Observed vs. inferred | yes | inference (a) is backed by the unit tier's boolean at the check (closed-gate cells with r > X are false); (b) by four equal end sizes; (c) by the per-SSTable output/input ratios equal for the two SSTables of each table |
| 6. Deviations and gaps | yes | D3 recorded; H3 and the self-check were changed after the run only in how they count `Compacted` lines (no prediction or row) |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | steps 1-7 of §4.2 follow B1 as read in A4: a conclusion of `does not cap` needs a gated table above X, which was observed |

### 5.2 Run 2?

**No** — decided 2026-10-26. Every prediction held with wide margins in both tiers, the cluster readings were within 0.002 of the expectation, the check is deterministic at the unit tier, and the one deviation (two SSTables per table) does not touch a row. The result neither refutes the case nor confirms a bypass of a byte limit.

## 6. Run 2 — fresh AI session (optional)

Not done (see 5.2).

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** disk usage of a table does not follow `tombstone_threshold`: lowering the threshold below the ratio only makes SSTables eligible for single-SSTable compaction; where other gates apply (interval, gc_grace, overlap) disk stays high independent of the threshold, and no byte-denominated cap exists. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (P1-P4 hold) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** — B3g row 1 (gated tables keep r = 0.5 at X = 0.05 and 100 % of their bytes; open sibling falls to 0.483; X = 0.7 and 1.5 keep 100 %; end sizes equal at X = 0.05 / 0.2 / 0.4; `pc` falls after `nodetool compact`) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** unit: `forceMajorCompaction` at X = 1.5 (worth false) frees (1-f) of the bytes (0.895 / 0.690 / 0.390 / 0.097 of before); cluster: `nodetool compact` on `pc` (X = 1.5, ratio 0.5, untouched by the enable) took 44,722,986 B to 21,610,349 B (0.483), and `a05` (same data, gates open) reached the same 0.483 by the threshold path, so the workload and instruments can show a drop, and the flat tables are not a workload limit.

**Note on the bound with all gates open:** with interval, overlap and gc_grace gates open, an SSTable above X is rewritten, so its residual droppable share is at most X (cluster `a70`: 0.5 < 0.7 stays; `a05`: 0.009 after). This is a bound on a ratio of one SSTable's cells that holds only on that path; it is not a byte bound and it does not hold under the closed gates (A4 of D1). The outcome class takes the effect of the threshold on the table's bytes as `does not cap`.

**Feedback filed:** the case file's section D2 updated (uncommitted; commit by the orchestrator); amendments D1 A1-A8 filed before the run. Upstream or documentation candidates are in D2.

**Leftovers:** no process of this run is running; `/dev/shm/s4-b10-td` removed. On the node (not in the repo): trees `~/s4-b10-td-u`, `~/s4-b10-td-n`, node conf `~/s4-b10-td-node`, driver `~/s4-b10-td-drv`, logs `~/s4-b10-td-logs/`.
