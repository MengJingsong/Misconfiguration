# range_tombstone_list_growth_factor-grow-newLength--autonomous — stage-4 results  <!-- file: results/range_tombstone_list_growth_factor-grow-newLength--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`range_tombstone_list_growth_factor-grow-newLength--autonomous`](../../stage3-ai-deep-read/cases/range_tombstone_list_growth_factor-grow-newLength--autonomous.md)
>
> **Status:** verdict filed 2026-10-23 (run 1, unit then cluster, self-checked; no run 2). Estimate negative. Unit **Confirmed — does not cap**; cluster **Confirmed — does not cap**. Run by the autonomous stage-4 session on `pc07` (node0).
>
> **Outcome class:** **true negative** (stage-3 estimate `negative`; stage-4 effect on the constraint: `does not cap`, both tiers) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
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
| **Case-file version** | Autonomous file, untracked in the repository at HEAD `c765cea` (the file is not committed; the human closes that). As filed (2026-10-23): sha256 `8003a978d2439f4880cb26ff50f63b9451c861becf304ead7eae64841896e104`. After the step-0 audit amendments R1–R7 (section B5 of the case file, dated 2026-10-23, written before any reading): **`bec115be93c9515da3a9f5aa140e30ee86e352d9524f2e9b5b47550630db67fa`, the frozen version** (this is the hash for `_INDEX.md` §4). Written 2026-10-23 before any reading; no shakedown output had been looked at. **The unit tier ran on this version.** After the cluster-tier definitions R8 (case-file section B5, written 2026-10-23 after the unit tier ran and **before any cluster reading**; it defines words of B3f/B3g and fixes one arithmetic wording; no B2 text and no row's meaning changed): **`ecc4706fca98352c6adb93d3328a3644d962d52c0d175f0b566fc59fc95f3eea`, the version the cluster tier uses** (this is the hash for `_INDEX.md` §4). |
| **Harness** | [`harness/range_tombstone_list_growth_factor-grow-newLength--autonomous/`](../harness/range_tombstone_list_growth_factor-grow-newLength--autonomous/README.md), written 2026-10-23 after the freeze, not committed (the human commits): `RangeTombstoneGrowthProbeTest.java`, `unit-run.sh`, `unit-analyze.py`, `client.py`, `Jmx.java`, `HeapPoll.java`, `growth.btm`, `cluster-run.py`, `cluster-analyze.py`, `selfcheck.py`, `package-excerpts.sh`, `README.md`. **Instrument checks (shakedowns, not readings):** unit shakedown at 2,000 instead of 100,000 (renamed copy; `~/stage4-logs/rtl/n/shake1/`); cluster shakedowns at `RTL_SCALE=100` (`shake1`: found D1 and D3; `shake2`: found D2 and checked the analyzer end to end, its control rows failing at that scale as expected). |
| **Tiers and values** | Both tiers. unit: f ∈ {1.2,1.5,2.0,5.0,1.0,0.5,100} × c ∈ {1,1024} × n ∈ {1,10,1000,100k}, copy()+add ×1000, addAll, c>n control. Cluster: 50 × 20,000 range deletes at f 1.2,5.0,1.5,2.0 and reversed (one lifetime, JMX), control = restart at memtable_heap_space 256MiB, plus a plain-insert table. Working tree `~/cassandra-rtl-n` (copy-source.sh), node data `~/stage4-rtl-n/`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-23 (R1–R7 before the freeze; R8 after the unit tier and before any cluster reading) |

### 1.1 Design audit

Checked against the pinned source `cassandra/cassandra-5.0.9/` (this repository, read only; `git status cassandra/cassandra-5.0.9` empty).

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap, indirectly; a slot count with a derivable byte size (20 B with compressed oops, 28 B without: `starts`+`ends` references, `markedAts` 8 B, `delTimesUnsignedIntegers` 4 B; `RangeTombstoneList.java:60-63, 770-778`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b and B3b: four factors incl. the default 1.5 (unit), three or four in the cluster. JMX accepts only [1.2, 5.0] (`StorageService.java:6903-6915`), the unit setter any value (`DatabaseDescriptor.java:4654-4657`). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after R2/R5 | Unit: `unsharedHeapSize()` is the check's own accounting, the independent size is Jamm `measureDeep` (R2). Cluster: filed readings were the counter (`MemtableOnHeapDataSize`) and a histogram; R5 makes the live-heap histogram rows (`ClusteringBound[]`, `BufferClusteringBound`) the real resource and names the counter as the estimate, which over-counts the bounds (lines 178/766). |
| A. Core question | usage driven to the limit and past it | Partly → Met after R4/R5 | There is no limit to reach (A3 step 5: no refusal path); the 'binding condition' is the positive control. As filed, the cluster arithmetic reaches neither the workload nor a flush-free main cell: the flush starts at 1/3 of `memtable_heap_space` (R4) and the filed sizes were inconsistent or O(n²)-heavy (R5). Fixed by dated amendments. |
| A. Core question | positive control present (negative-estimate file) | Partly → Met after R7 | Cluster: `memtable_heap_space` binds on the same workload and instruments. Unit: a binding initial allocation / a bounded map, designated by R7. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list procedures; B1 is the hypothesis; refuted-if is the plateau row of B2g/B3g. Mapped as README says for an autonomous file; steps' purposes are stated in B2g/B3g rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after R3/R6 | B2f/B3f give sequences, bounds and ratios, but 'about', 'roughly', 'linearly', 'on the order of' were undefined (R3), and one numeric statement contradicts the source (R6). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover: grows with N (Confirmed), plateau at an f-dependent level (Refuted), gap above the slack bound, control did not move / limit not reached (Not confirmed). 'Usage exceeds the limit' does not apply (no limit); 'counter capped but real resource grows' is covered by the histogram-vs-counter rows added by R5's two readings. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after R5 | The claim is that no ceiling follows the knob and no disallow branch exists (A3 step 5). Direct evidence of the traced line: the Byteman trace of `growToFree` (capacity, `newLength`, factor) in the live node, plus the unit growth series. Absence of a refusal: every add is accepted (N+1 add, writes acknowledged, no error in `system.log`). |
| B. Logic | alternative explanations and their controls | Partly → Met after R7 | Counter vs real heap (histogram), flush resetting the lists (flush-free cell rule R3/R4), compaction noise (R7), probe blindness (positive controls named in R7: binding initial allocation / bounded map in the unit tier, `memtable_heap_space` in the cluster). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3 mechanism, B1, B2g/B3g rows. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after R5 | The unit test is described, not given; cluster tools (jmxterm, `jcmd` JMX) are not on the node. The harness supplies them (R5); no code-path re-derivation was needed. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after R3/R5 | Checkpoints, stop conditions and tolerances were missing; added. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | No harness existed: listed as step-1 work (unit probe, Jmx.java, client.py, Byteman rule, run and analyze scripts). Environment: JDK 11.0.32.1, Ant 1.10.12, `build-test` of the tree (`environment.md`), Jamm in the test JVM (`build.xml:1159`), Byteman in `build/lib/jars`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Not met as filed → Met after R4/R5 | Memtable flush at 1/3 of the pool, counter over-count, an O(n) copy per write (n² array traffic) and, for the filed sizes, either more tombstones than the heap (case 1) or a flush inside the main cells (cases 2, 3). Data volume is small (≤ a few hundred MB on local disk, 49 GB free). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (one wording error, R6) | Re-read: `RangeTombstoneList.java:60-63, 106-133, 157-179, 189-192 (addAll), 520-529 (copyArrays), 664-675, 680-689, 694-698, 700-739, 766, 770-778`; `MutableDeletionInfo.java:83, 117-120, 130-145, 249-254`; `BTreePartitionUpdater.java:120-121`; `Config.java:798, 802`; `DatabaseDescriptor.java:761-764, 4639-4657`; `StorageService.java:6898-6915`; `StorageServiceMBean.java:1172`; `conf/cassandra.yaml:794-825, 899-912`; `build.xml:1153, 1159`; `ObjectSizes.java:230`. The merge path trims on `copy()` and grows on the next add, as traced. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Use a `copy-source.sh` tree and local node data instead of `cp -r`, `/tmp`, `/local` | Applied 2026-10-23 (case file B5; not committed) | README safety rules |
| R2 | State the test JVM facts (Jamm agent present, 1024 MiB heap) and define the independent size | Applied 2026-10-23 | the filed JVM options do not apply to `ant testsome` |
| R3 | Define "about/roughly/linear/slack bound/plateau/on the order of/flush-free" | Applied 2026-10-23 | the conclusions would otherwise depend on the reader |
| R4 | Heap 8 GiB and a `memtable_heap_space` that keeps the main cells flush-free; control keeps its small value | Applied 2026-10-23 | flush at 1/3 of the pool and counter over-count |
| R5 | Cluster workload sizes, cells, checkpoints and instruments (Jmx.java, class histogram, Byteman trace, heap poll) | Applied 2026-10-23 | filed sizes inconsistent or too heavy; tools absent |
| R6 | Fix prediction wording the source contradicts (see the case file) | Applied 2026-10-23 | wording errors independent of any reading |
| R7 | Make the filed controls explicit; disable autocompaction | Applied 2026-10-23 | negative-estimate files need a positive control; compaction builds its own lists |
| S1 | The double count of `boundaryHeapSize` (lines 178/766) is stated as a possibility in the case file; the run measures it, it is not a prediction | Left for stage 3 | not load-bearing for the claim |
| S2 | The 500,000-per-partition shape is not run (R5); the claim does not need it | Left for stage 3 | cost

**Agreement criteria** — not applicable: run 2 was not chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-23 (node clock EDT): unit tier 11:50:27–11:50:58; cluster tier 12:06:08–12:38:21 (the three sibling files ran their cluster tiers at the same time, see deviation E2 below) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; `pc12` was not touched | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18); `jcmd` from the same JDK | — |
| Ant (`ant -version`) | 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/cassandra-rtl-n` made by `copy-source.sh` from repository HEAD `c765cea` (`git status cassandra/cassandra-5.0.9` empty), tag `cassandra-5.0.9` (local baseline commit; upstream `b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` BUILD SUCCESSFUL (log `~/stage4-logs/rtl/build-test-n.log`). The unit probe was copied in for the run and removed; `git status` of the tree is empty again. | — |
| Case-file commit / harness commit | case file untracked at HEAD `c765cea`: unit run on sha256 `bec115be93c9515da3a9f5aa140e30ee86e352d9524f2e9b5b47550630db67fa`, cluster run on `ecc4706fca98352c6adb93d3328a3644d962d52c0d175f0b566fc59fc95f3eea`; harness not committed (md5 of the unit files in `~/stage4-logs/rtl/n/run1/unit/summary.txt`, of the cluster files in `~/stage4-logs/rtl/n/run1/cluster/harness.md5`) | — |
| Storage for node data | `~/stage4-rtl-n/` on local `/dev/sda3` (47 GB free at the end); nothing on `/proj`. Cassandra heap 8 GiB (`MAX_HEAP_SIZE=8G`, G1, `AlwaysPreTouch`), ports 7230/7231/9262, JMX 7599 (storage / ssl / native), loopback 127.0.0.1. | — |
| Full logs (path, outside the repo) | `pc07:~/stage4-logs/rtl/n/run1/unit/` (ant.log, junit XML, `rtl-unit.txt`, `analysis.txt`, `selfcheck.txt`) and `…/run1/cluster/` (`session.log`, `cells.jsonl`, `readings.csv`, per cell `histo-*.txt` (raw `jcmd GC.class_histogram`), `series.csv`, `heap.txt`, `growth-trace.txt`, per lifetime `system-*.log`, `gc-*.log`, `rtl-*.trace`, `cassandra-*.yaml`); shakedowns `…/shake1`, `…/shake2` (not readings) | — |

**Environment deviations.** E1: the case file's paths (`~/cassandra-5.0.9`, `/tmp/ct`, `/local/...`) are replaced by the `copy-source.sh` tree and `~/stage4-rtl-n` (case-file B5 R1). E2: the three sibling files ran their cluster tiers **at the same time on this node**, each with its own tree, data directory, ports and logs (README says one run at a time per node; HANDOFF allows two cases on one node with separate trees, directories and ports). The readings are heap bytes and counters, not timings, so contention affects only the durations (the load seconds in `session.log`). E3: `RssAnon` is not a usable reading here: the heap is 8 GiB with `AlwaysPreTouch`, so `RssAnon` is about 9 GB from the start (`cells.jsonl`); the real resource is read from the class histogram (live bytes after a forced full collection) instead. E4: the unit tier runs in the `ant testsome` JVM (`-Xmx1024m`), not 2 GiB (case-file R2).

## 3. Runbook defects

Instrument defects found in the shakedowns (before any reading) and one found in the first analyzer pass; none changed a prediction or a conclusions row.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown 1 | B3b | `setRangeTombstoneListResizeGrowthFactor(double)` has no getter of the same name, so JMX exposes it as the write-only attribute `RangeTombstoneListResizeGrowthFactor`, not an operation: `invoke` failed with `No such operation`. | `Jmx.java setdouble` calls `setAttribute`; the read-back attribute is `RangeTombstoneResizeListGrowthFactor`. | 2026-10-23, instrument only (noted in the case file's R8) | none (case file untracked) |
| D2 | cluster shakedown 2 | B3d | the class-histogram parser dropped array rows (`[J`, `[I`) because they carry a trailing `(java.base@11...)` column. | rows with ≥ 4 fields are parsed. | 2026-10-23, before run 1 | none |
| D3 | cluster shakedown 1 | B3e | the `system.log` error filter matched the INFO line that lists `-XX:+HeapDumpOnOutOfMemoryError`. | filter is `^ERROR` or `java.lang.OutOfMemoryError`. | 2026-10-23, before run 1 | none |
| D4 | cluster shakedown 1 | B3c | the case-file wording about concurrency/tools (jmxterm, `jcmd` JMX) is not available on the node. | harness `Jmx.java`, `client.py`, `HeapPoll.java` (R5). | 2026-10-23 | R5 |
| D5 | unit run 1, analysis | R3 pair bound | the frozen R3 criterion '|unshared(f_a) − unshared(f_b)| ≤ 28 B × (ceil((f_max − 1)·N) + 1)' takes f_max = max(f_a, f_b), but for f ≤ 1.0 the line applies the fallback cap·3/2 + 1 (an effective factor 1.5), so the pairs that contain f = 0.5 or 1.0 against 1.2 exceed it: see §4.2 part 2. The criterion was written before any reading (R3) and is NOT amended after the readings. | reported as it is; a clearly labelled POST-HOC line in the analyzer repeats the check with f_eff (1.5 for f ≤ 1.0) | 2026-10-23 | none |
| D6 | self-check | §5 | the first cluster self-check counted the control cells (which flush by design) in the 'live tombstones == written' check. | controls excluded and printed instead. | 2026-10-23 | none |

## 4. Run 1

**Scope:** unit tier, the full grid of B2b/B2c; cluster tier as amended (R5), all cells listed in §4.1. **Command log:** `range_tombstone_list_growth_factor-grow-newLength--autonomous/run1/unit/summary.txt`, `range_tombstone_list_growth_factor-grow-newLength--autonomous/run1/cluster/session.log` (every command and its output; full logs on the node, §2).

### 4.1 Readings

**Unit tier — test or assertion, result, evidence** (`range_tombstone_list_growth_factor-grow-newLength--autonomous/run1/unit/rtl-unit.txt`, analysis in `analysis.txt`; sorted adds, s = 1, one run of the full grid; the table is a selection of 8 rows of the 309 lines)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Capacity series, event count, array lengths and size equal the iterated expression (112 runs: 7 factors × 2 initial capacities × 4 n × 2 repeats) | holds, 0 differ; f = 100.0, c = 1, n = 100,000 gives capacities 100, 10,000, 1,000,000 | `run1/unit/analysis.txt`, `rtl-unit.txt` |
| `DatabaseDescriptor` setter accepts 100.0, 0.5, 1.0 without error | holds, read back unchanged | `analysis.txt` |
| 1 ≤ capacity / n ≤ f (1.5 for the fallback) plus the ceiling's +1, n ≥ 1,000 | holds, 0 outside | `analysis.txt` |
| Deterministic: the repeat of every run is identical | holds, 56 of 56 | `analysis.txt` |
| `unsharedHeapSize()` ≥ 20 B × capacity in every run | holds | `analysis.txt` |
| Unshared ∝ n (n = 100,000 / 1,000 in [50, 150] at every (f, c)) | holds: 99.8 – 102.9 | `selfcheck.txt` check 8 |
| |unshared(f_a) − unshared(f_b)| ≤ 28 B × (ceil((f_max − 1)·N) + 1), all pairs (frozen R3) | **does not hold as written for 2 of 168 pairs** (c = 1, n = 100,000, f = 0.5 or 1.0 against 1.2: 649,552 B against 560,028 B); holds for all 168 pairs with the effective factor 1.5 for f ≤ 1.0 (POST-HOC); holds for every pair of legal factors | `analysis.txt`, `selfcheck.txt` check 7 |
| `copy()` + add × 1,000: capacity == size after `copy()`; after the add == `ceil(size·f)` (fallback rule), no bound | holds in all 1,000 iterations of 8 runs (e.g. f = 5.0: size 1,000 → capacity 5,000 … size 1,999 → 9,995) | `analysis.txt`, `selfcheck.txt` check 12 |
| `addAll` into an empty list (target line 696): capacity = max(c, src.size) in all four arrays, the same for every f (R6) | holds: 1,000 for c = 1, 1,024 for c = 1,024 | `analysis.txt` |
| Positive control: c = 1,024, n = 1,000 < c keeps capacity 1,024 at f = 1.2, 1.5, 2.0, 5.0; cells c = 1,024 with n = 1, 10, 1,000 never grow (21 of 21) | holds | `analysis.txt` |
| Observation: `unsharedHeapSize()` − Jamm deep size | = the sum of the true bound sizes (N = 100,000, f = 1.5: 23,999,872 B against 24,000,000 B); `boundaryHeapSize` = 2.000 × true bounds | `analysis.txt` |

Selected raw rows (sorted adds, s = 1; the full grid is in `run1/unit/rtl-unit.txt`):

| f | s (initial capacity) | N | growth events | final capacity (all four arrays) | slack = capacity − N | unsharedHeapSize() (B) | Jamm deep (B) | boundaryHeapSize / true bound sizes |
|---|---|---|---|---|---|---|---|---|
| 1.2 | 1 | 1,000 | 32 | 1,107 | 107 | 502,024 | 262,152 | 1.999 |
| 1.2 | 1 | 100,000 | 57 | 105,776 | 5,776 | 50,115,392 | 26,115,520 | 2.000 |
| 1.5 | 1 | 1,000 | 16 | 1,065 | 65 | 501,184 | 261,312 | 1.999 |
| 1.5 | 1 | 100,000 | 28 | 138,254 | 38,254 | 50,764,952 | 26,765,080 | 2.000 |
| 2.0 | 1 | 1,000 | 10 | 1,024 | 24 | 500,352 | 260,480 | 1.999 |
| 2.0 | 1 | 100,000 | 17 | 131,072 | 31,072 | 50,621,312 | 26,621,440 | 2.000 |
| 5.0 | 1 | 1,000 | 5 | 3,125 | 2,125 | 542,384 | 302,512 | 1.999 |
| 5.0 | 1 | 100,000 | 8 | 390,625 | 290,625 | 55,812,384 | 31,812,512 | 2.000 |

Analyzer output (frozen expectations; `12/13` hold):

```
EXPECTED: capacity series, event count, four array lengths and size equal the iterated expression (sorted and random order, every cell): PASS (112 runs, 0 differ)
EXPECTED: final capacity >= N and below the growth bound (ceil(f*N)+1 for 1.2<=f<=5.0; 1.5*N+2 for f<=1.0, R6): PASS (0 violations)
EXPECTED: unsharedHeapSize() grows ~linearly in N (R3: ratio of the largest to the smallest N within 0.5..1.5 x the N ratio), every (f, s) cell with growth: PASS (14 cells; cells outside: [])
EXPECTED: |unshared(f_a) - unshared(f_b)| <= 28 B x (ceil((f_max-1)*N)+1) for the same (s, N), all pairs of f: FAIL (168 pairs, 2 violations: [(1, 100000, 0.5, 1.2, 649552, 560028), (1, 100000, 1.0, 1.2, 649552, 560028)])
POST-HOC (not frozen): pair bound with f_eff (1.5 for f <= 1.0): PASS (168 pairs, 0 violations)
EXPECTED: DatabaseDescriptor setter takes f = 100.0, 0.5, 1.0 with no error and reads them back (no validation): PASS ([('100.0', '100.0', 'none'), ('0.5', '0.5', 'none'), ('1.0', '1.0', 'none')])
EXPECTED: f = 100.0, c = 1, N = 100000: capacities 1 -> 100 -> 10000 -> 1000000 (after the initial 1): PASS ([100, 10000, 1000000])
EXPECTED: N >= 1000 with growth: 1 <= capacity/N <= f (1.5 for the fallback), plus the +1 of the ceiling: PASS (0 outside)
EXPECTED: each capacity sequence is deterministic: the repeat of every run is identical: PASS (56 cells)
EXPECTED: unsharedHeapSize() >= 20 B x capacity in every run: PASS (0 below)
EXPECTED: copy()+add x1000: after each copy() capacity == size, after the add capacity == ceil(size*f) (fallback rule applied), no bound: PASS (8 runs)
EXPECTED: addAll into an empty list (target line 696): capacity == max(c, src.size) in all four arrays, the same for every f (R6): PASS (14 runs; capacities ['1000', '1024'])
EXPECTED: positive control: c = 1024, n = 1000 < c: capacity stays 1024 at f = 1.2, 1.5, 2.0, 5.0: PASS (['1024/1024/1024/1024', '1024/1024/1024/1024', '1024/1024/1024/1024', '1024/1024/1024/1024'])
EXPECTED: control cells c = 1024 with n = 1, 10, 1000: capacity stays 1024, no growth event: PASS (21 cells)
SUMMARY: 12/13 expectations hold
MATCHED ROW: B2g row 1 (capacity follows the iterated ceil(c*f), slack grows with n and f, no f stops growth) with the addAll row and the c>n control row -- with ONE frozen R3 criterion not holding (the pair bound; the violating pairs all contain a fallback factor f <= 1.0 against 1.2); the POST-HOC line shows the bound holds wi
```

**Cluster tier** — one row per cell and checkpoint (counter = `MemtableOnHeapDataSize`; live tombstones and allocated slots from the raw `jcmd GC.class_histogram`: `BufferClusteringBound` count / 2 and (`ClusteringBound[]` bytes − 16 × arrays) / 8 above the cell's baseline; evidence `range_tombstone_list_growth_factor-grow-newLength--autonomous/run1/cluster/readings.csv`, `cells.jsonl`, `<cell>/histo-*.txt`):

| Cell | f read back | space | cp | tombstones written | counter (B) | B / tombstone | live tombstones (histogram) | allocated slots (histogram) | slots / live | switch count |
|---|---|---|---|---|---|---|---|---|---|---|
| F-1.2-1 | 1.2 | 3072MiB | 1 | 250,000 | 125,887,200 | 504 | 250,000 | 300,000 | 1.200 | 0 |
| F-1.2-1 | 1.2 | 3072MiB | 2 | 500,000 | 251,887,200 | 504 | 500,000 | 600,000 | 1.200 | 0 |
| F-1.2-1 | 1.2 | 3072MiB | 3 | 1,000,000 | 503,887,200 | 504 | 1,000,000 | 1,200,000 | 1.200 | 0 |
| F-5.0-2 | 5.0 | 3072MiB | 1 | 250,000 | 144,883,200 | 580 | 250,000 | 1,249,800 | 4.999 | 1 |
| F-5.0-2 | 5.0 | 3072MiB | 2 | 500,000 | 289,883,200 | 580 | 500,000 | 2,499,800 | 5.000 | 1 |
| F-5.0-2 | 5.0 | 3072MiB | 3 | 1,000,000 | 579,883,200 | 580 | 1,000,048 | 5,000,018 | 5.000 | 1 |
| F-1.5-3 | 1.5 | 3072MiB | 1 | 250,000 | 127,387,200 | 510 | 250,000 | 375,000 | 1.500 | 2 |
| F-1.5-3 | 1.5 | 3072MiB | 2 | 500,000 | 254,887,200 | 510 | 500,000 | 750,000 | 1.500 | 2 |
| F-1.5-3 | 1.5 | 3072MiB | 3 | 1,000,000 | 509,887,200 | 510 | 1,000,001 | 1,499,834 | 1.500 | 2 |
| F-2.0-4 | 2.0 | 3072MiB | 1 | 250,000 | 129,885,600 | 520 | 250,000 | 499,900 | 2.000 | 3 |
| F-2.0-4 | 2.0 | 3072MiB | 2 | 500,000 | 259,885,600 | 520 | 500,000 | 999,900 | 2.000 | 3 |
| F-2.0-4 | 2.0 | 3072MiB | 3 | 1,000,000 | 519,885,600 | 520 | 1,000,000 | 1,999,900 | 2.000 | 3 |
| F-2.0-5 | 2.0 | 3072MiB | 1 | 250,000 | 129,885,600 | 520 | 250,000 | 499,900 | 2.000 | 4 |
| F-2.0-5 | 2.0 | 3072MiB | 2 | 500,000 | 259,885,600 | 520 | 500,000 | 999,900 | 2.000 | 4 |
| F-2.0-5 | 2.0 | 3072MiB | 3 | 1,000,000 | 519,885,600 | 520 | 1,000,000 | 1,999,900 | 2.000 | 4 |
| F-1.5-6 | 1.5 | 3072MiB | 1 | 250,000 | 127,387,200 | 510 | 250,000 | 375,000 | 1.500 | 5 |
| F-1.5-6 | 1.5 | 3072MiB | 2 | 500,000 | 254,887,200 | 510 | 500,000 | 750,000 | 1.500 | 5 |
| F-1.5-6 | 1.5 | 3072MiB | 3 | 1,000,000 | 509,887,200 | 510 | 1,000,000 | 1,500,000 | 1.500 | 5 |
| F-5.0-7 | 5.0 | 3072MiB | 1 | 250,000 | 144,883,200 | 580 | 250,000 | 1,249,800 | 4.999 | 6 |
| F-5.0-7 | 5.0 | 3072MiB | 2 | 500,000 | 289,883,200 | 580 | 500,000 | 2,499,800 | 5.000 | 6 |
| F-5.0-7 | 5.0 | 3072MiB | 3 | 1,000,000 | 579,883,200 | 580 | 1,000,000 | 4,999,800 | 5.000 | 6 |
| F-1.2-8 | 1.2 | 3072MiB | 1 | 250,000 | 125,887,200 | 504 | 250,000 | 300,000 | 1.200 | 7 |
| F-1.2-8 | 1.2 | 3072MiB | 2 | 500,000 | 251,887,200 | 504 | 500,000 | 600,000 | 1.200 | 7 |
| F-1.2-8 | 1.2 | 3072MiB | 3 | 1,000,000 | 503,887,200 | 504 | 1,000,000 | 1,200,000 | 1.200 | 7 |
| INS-1.5 | 1.5 | 3072MiB | 1 | 250,000 | 72,368,000 | 289 | 0 | 0 | 0.000 | 0 |
| INS-1.5 | 1.5 | 3072MiB | 2 | 500,000 | 144,739,600 | 289 | 0 | 0 | 0.000 | 0 |
| INS-1.5 | 1.5 | 3072MiB | 3 | 1,000,000 | 289,490,400 | 289 | 0 | 0 | 0.000 | 0 |
| C-1.5-256MiB | 1.5 | 256MiB | 1 | 250,000 | 37,783,690 | 151 | 74,309 | 111,418 | 1.499 | 1 |
| C-1.5-256MiB | 1.5 | 256MiB | 2 | 500,000 | 75,685,938 | 151 | 148,628 | 222,900 | 1.500 | 2 |
| C-1.5-256MiB | 1.5 | 256MiB | 3 | 1,000,000 | 61,872,090 | 62 | 121,545 | 182,272 | 1.500 | 5 |

Real heap against the check's counter at the last checkpoint (histogram total above the cell baseline, `analysis` of `histo-*.txt`):

```
F-1.2-1        f= 1.2 T=1,000,000 live-heap delta    277.2 MB =    277 B/tombstone; counter    503.9 MB =   504 B/tombstone; baseline total 67 MB
F-5.0-2        f= 5.0 T=1,000,000 live-heap delta    341.5 MB =    341 B/tombstone; counter    579.9 MB =   580 B/tombstone; baseline total 79 MB
F-1.5-3        f= 1.5 T=1,000,000 live-heap delta    272.1 MB =    272 B/tombstone; counter    509.9 MB =   510 B/tombstone; baseline total 80 MB
F-2.0-4        f= 2.0 T=1,000,000 live-heap delta    282.1 MB =    282 B/tombstone; counter    519.9 MB =   520 B/tombstone; baseline total 81 MB
F-2.0-5        f= 2.0 T=1,000,000 live-heap delta    282.1 MB =    282 B/tombstone; counter    519.9 MB =   520 B/tombstone; baseline total 82 MB
F-1.5-6        f= 1.5 T=1,000,000 live-heap delta    272.1 MB =    272 B/tombstone; counter    509.9 MB =   510 B/tombstone; baseline total 83 MB
F-5.0-7        f= 5.0 T=1,000,000 live-heap delta    342.1 MB =    342 B/tombstone; counter    579.9 MB =   580 B/tombstone; baseline total 84 MB
F-1.2-8        f= 1.2 T=1,000,000 live-heap delta    266.1 MB =    266 B/tombstone; counter    503.9 MB =   504 B/tombstone; baseline total 85 MB
```

Analyzer output (`14/14` expectations hold):

```
cells: main ['F-1.2-1', 'F-5.0-2', 'F-1.5-3', 'F-2.0-4', 'F-2.0-5', 'F-1.5-6', 'F-5.0-7', 'F-1.2-8']; controls ['C-1.5-256MiB']
EXPECTED: factor read back over JMX equals the factor set (yaml or JMX; cell J: 5.0 after the runtime change) before every cell: PASS (10 cells; mismatches [])
EXPECTED: every write was acknowledged: ok == tombstones (or rows) written, errors == 0, in every cell (no rejection at any f): PASS (10000000 acknowledged; bad [])
EXPECTED: main cells are flush-free: MemtableSwitchCount unchanged from the start of the cell to its last checkpoint (R3): PASS (bad [])
EXPECTED: no ERROR or OutOfMemoryError line in system.log of any lifetime: PASS ({'L1': 0, 'C-1.5-256MiB': 0})
EXPECTED: the tombstones are live in the memtable: BufferClusteringBound count delta == 2 x tombstones (1 %) and MemtableColumnsCount == tombstones, at every checkpoint of every main cell: PASS (bad [])
EXPECTED: Byteman trace on the live node: every sampled grow(i, newLength) (cap >= 20) has newLength == iterated expression at the cell factor, and every sampled growToFree line reads the cell factor: PASS (8986 grow lines checked (8998 sampled); bad [])
EXPECTED: counter grows with N at every main cell: rises at every checkpoint and last/first within [0.6, 1.4] x (tombstones last/first) (R3): PASS (8 cells; bad [])
EXPECTED: no plateau at any factor: NOT (last two checkpoints differ by less than 5 % while the tombstone counts differ by at least 1.5x) (R3): PASS (bad [])
EXPECTED: |counter(f_a) - counter(f_b)| <= 28 B x |f_a - f_b| x T + 1 MiB for every pair of main cells of the same shape at the last checkpoint (R3): PASS (28 pairs; bad [])
EXPECTED: live ClusteringBound[] bytes after the last checkpoint are ordered like the factor (non-decreasing in f) for every shape (R3): PASS (bad [])
EXPECTED: counter(5.0) - counter(1.2) (means of the repeats) is on the order of 76 MB: within [38, 152] MB (R8): PASS (76.0 MB)
EXPECTED: long[] bytes are ordered like f, and long[](5.0) - long[](1.2) in [0.5, 2] x 8 B x extra slots (R8): PASS (long[] {1.2: 19645824.0, 5.0: 50044780.0, 1.5: 22045496.0, 2.0: 26045212.0}; extra slots 3799927; diff 30398956)
EXPECTED: plain-insert table INS-1.5: live ClusteringBound[] bytes exceed the cell baseline by < 64 KiB (R8): PASS (0 B)
EXPECTED: positive control C-1.5-256MiB: MemtableSwitchCount rises above its start (main cells: no flush) and the counter series max <= 256 MiB (R8): PASS (switch 0->['1', '2', '5']; series max 84.6 MiB; main cells flush-free: True)
SUMMARY: 14/14 expectations hold
MATCHED ROW: B3g row 1 (usage rises with N at all factors; the factor changes it only within the slack bound; no cap tied to f) with the positive control moving (flush-bound memtable) while the factor stays flat -- Confirmed, does not cap
```

### 4.2 Conclusion and logic

Tag: **[observed: `<file>`]** or **[inferred: `<reason>`]**. Files are under `results/range_tombstone_list_growth_factor-grow-newLength--autonomous/run1/` unless noted.

1. **Validity.** The binding condition of each control was reached and the traced line was exercised: [observed: unit `analysis.txt`] growth beyond the initial allocation in every s ≤ 1 cell; [observed: `cluster/analysis.txt`] factor read back over JMX equals the factor set before every cell; every checkpoint load acknowledged all writes with 0 errors; main cells flush-free (`MemtableSwitchCount` unchanged during every main cell; `system.log` shows only my `USER_FORCED` flush at the end of each cell, at 1 – 18 % of the pool, below the 33 % trigger [observed: `selfcheck.txt` flush checks]); live tombstones (`BufferClusteringBound` / 2) equal tombstones written at every checkpoint; no `ERROR` / `OutOfMemoryError` in `system.log`; sampled Byteman `grow(i, newLength)` lines all equal the iterated expression at the cell factor. "Hold fixed" settings (heap 8 GiB, schema, load, one request in flight per partition, autocompaction off, `memtable_allocation_type: heap_buffers`) are in `cassandra-*-tail.yaml` and `session.log` [observed]. The run is valid.
2. **Readings.** **One frozen criterion did not hold as written**: the R3 pair bound for the unit tier fails for pairs that contain a fallback factor (f = 0.5 or 1.0, outside the legal range 1.2 – 5.0) against 1.2, because those factors act as 1.5 (`cap·3/2 + 1`); the excess is 649,552 B against 560,028 B at N = 100,000. This is a defect of the R3 wording found when reading, it is reported, not amended after the reading (README: predictions are not tuned to data); with the effective factor the bound holds (POST-HOC line) and for every pair of legal factors it holds as written [observed: `unit/analysis.txt`]. Nothing else unusual in the unit tier. Cluster: the counter over-counts the real live heap by roughly 215 – 240 B per tombstone (504 B counter against 266 – 279 B of live heap above the baseline at f = 1.2; 580 B against 341 – 367 B at f = 5.0, across the three files), about the double-counted bound size (240 B per tombstone) found in the unit tier [observed: real-heap block of §4.1; inferred that the gap is that double count: the numbers agree to within the histogram's baseline noise]. `RssAnon` is not informative (E3).
3. **Matched row.** Unit — B2g row 1: "Capacity follows the iterated `ceil(c*f)` and slack grows with n and f; no value of f stops growth → Claim confirmed: the knob is a growth rate and caps nothing" [observed: 112 of 112 runs; f = 100.0 grows ×100 each time and is accepted by the setter]. Row 2: "`unsharedHeapSize()` rises with n beyond any f-derived bound → usage follows n" [observed: ×99.8 – ×102.9 for ×100 in n]. Row 4: "`addAll` capacity is the same across f → target line 696 does not use the factor: confirmed" (with R6: max(c, src.size)) [observed: 14 of 14 runs]. Control: c = 1,024, n < c keeps capacity 1,024 at every f [observed]. Last row: the line 178 / 766 double count is real [observed]. Cluster — B3g row 1, "`MemtableOnHeapDataSize` and the histogram arrays rise with f for the same N, with no ceiling tied to f → Claim confirmed: usage follows the workload and f changes only the slack; it does not cap", with the filed control (lowering `memtable_heap_space` makes the node flush earlier and bounds the counter at any f) behaving as predicted in B3f: Usage followed the workload, not the factor. In eight interleaved cells (1.2, 5.0, 1.5, 2.0, then 2.0, 1.5, 5.0, 1.2) all 1,000,000 deletes were acknowledged and the live heap held exactly 1,000,000 tombstones; the counter rose ×4 with N (126 → 504 MB at 1.2; 145 → 580 MB at 5.0) and identical between the two repeats of each factor (0 B difference); the factor changed only the allocated slots (1.2, 1.5, 2.0 and 5.0 per live tombstone) and thereby the counter by 76.0 MB (mean of the repeats, 15.1 % of the f = 1.2 value) and the live `long[]` bytes by 30.4 MB (8 B × 3.8 M extra slots) [observed: `analysis.txt`, `readings.csv`]. The traced `grow(i, newLength)` lines show `newLength = ceil(cap·f)` at each cell's factor (8,986 sampled lines) [observed]. The plain-insert table adds no `ClusteringBound[]` bytes (0 B), so the arrays come from the range tombstones [observed]. The binding cap is the memtable pool: in the 256 MiB lifetime the node flushed five times and the counter stayed under 84.6 MiB (a third of 256 MiB) at f = 1.5, while no main cell flushed [observed].
4. **Excluded rows.** Unit: Row 3 (flat across f at the same n while the control moves): excluded, capacities differ with f exactly as predicted. Row 5 (setter throws or clamps): excluded, 100.0, 0.5 and 1.0 are accepted. Row 6 (capacity bounded by something that depends on f): excluded, f = 100.0 reaches 1,000,000 slots for 100,000 tombstones. Row 7 (never grows or the control does not move): excluded, every c = 1 cell with n ≥ 10 grows at least once and the c > n control keeps 1,024. Cluster: the "Refuted" rows — writes rejected or memtable plateau at an f-dependent value: excluded, 0 write errors and no plateau (no two checkpoints differ by less than 5 %); heap proportional to f as a whole rather than the arrays only: excluded, the live-heap difference between f = 5.0 and f = 1.2 is of the size of the added array bytes (this file's real-heap block in §4.1 against 20 B × the extra slots, within about ±20 %), and the live heap grows ×1.3 while f grows ×4.2, not proportionally [observed: real-heap block]; control did not move or limit never reached: excluded, the control flushed and was bounded, and the main cells reached 250 – 580 MB of counter [observed: `analysis.txt`].
5. **Observed vs. inferred.** The statement about the fallback pair bound (part 2) is [inferred: the effective ratio at f = 0.5 and f = 1.0 equals that of f = 1.5 in the capacity series]; the verdict does not rest on it. The statement that line 696 is on a path that does not read the factor rests on the observed addAll rows (capacity max(c, src.size) for every f) and on the source reading (`copyArrays` → `grow(int)` has no factor term) [inferred from both]. The cluster claim that the factor "does not cap" rests on observed ranges (1.2 – 5.0, the legal JMX range); a factor outside it is not reachable on a node over JMX, and the yaml path has no validation (`DatabaseDescriptor.java:4654-4657`), which was exercised only in the unit tier (f = 100.0, 0.5, 1.0) [inferred: the node reads the same field].
6. **Deviations and gaps.** E1 – E4 (§2). Not run: run 2. The 76 B per tombstone slack difference is the counter's estimate; the live-heap difference is read from one histogram per checkpoint (a forced full collection each), not a continuous series. The unit analyzer gained a labelled POST-HOC line and a `MATCHED ROW` suffix after the first run's output was seen; the probe, the grid and the readings are unchanged (md5 in `summary.txt` shows the analyzer at the first run; the final analyzer is in the harness folder).
7. **Core question.** Usage followed the workload, not the factor. In eight interleaved cells (1.2, 5.0, 1.5, 2.0, then 2.0, 1.5, 5.0, 1.2) all 1,000,000 deletes were acknowledged and the live heap held exactly 1,000,000 tombstones; the counter rose ×4 with N (126 → 504 MB at 1.2; 145 → 580 MB at 5.0) and identical between the two repeats of each factor (0 B difference); the factor changed only the allocated slots (1.2, 1.5, 2.0 and 5.0 per live tombstone) and thereby the counter by 76.0 MB (mean of the repeats, 15.1 % of the f = 1.2 value) and the live `long[]` bytes by 30.4 MB (8 B × 3.8 M extra slots) [observed: `analysis.txt`, `readings.csv`]. The traced `grow(i, newLength)` lines show `newLength = ceil(cap·f)` at each cell's factor (8,986 sampled lines) [observed]. The plain-insert table adds no `ClusteringBound[]` bytes (0 B), so the arrays come from the range tombstones [observed]. The binding cap is the memtable pool: in the 256 MiB lifetime the node flushed five times and the counter stayed under 84.6 MiB (a third of 256 MiB) at f = 1.5, while no main cell flushed [observed]. So the constraint does not cap usage, and the target line 696 path is not reached by the factor [unit part 3].

**Conclusion (one line):** B2g rows 1, 2 and 4, B3g row 1 — confirmed (the claim held): the factor does not cap usage — unit and cluster agree.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Done with `harness/range_tombstone_list_growth_factor-grow-newLength--autonomous/selfcheck.py`, which re-parses the raw files without importing the analyzers (own simulation of lines 683–686, whitespace parsing of `rtl-unit.txt`, the raw `jcmd` histograms, the `system.log` segments with flush reasons and times, the Byteman trace). Output: `run1/unit/selfcheck.txt` (14 checks, 0 do not hold) and `run1/cluster/selfcheck.txt` (17 checks, 0 do not hold after fix D6).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `cluster/session.log` (every load acknowledged: check 4), `system-*.log` (flush reasons and times, no ERROR), `<cell>/histo-*.txt` (live tombstones == written), `growth-trace.txt` (ratio newLength / cap within [f, f + 0.01]) |
| 2. Readings | yes, with the recorded failure of one frozen criterion | unit `selfcheck.txt` check 7 recomputes the pair bound independently: the violating pairs are exactly those that contain a fallback factor, none violates it with f_eff; the first cluster self-check wrongly included the control cells in a 'live == written' check (D6), fixed |
| 3. Matched row | yes | the §9a rows quoted in 4.2 part 3 are satisfied by the numbers re-derived from the raw files |
| 4. Excluded rows | yes | each excluded row is ruled out by a number in `selfcheck.txt` / `analysis.txt` |
| 5. Observed vs. inferred | yes | the inferred statements are listed in 4.2 part 5 and none carries the verdict |
| 6. Deviations and gaps | yes | E1–E4 and the not-run shapes are all stated |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's steps: the check does not refuse (all writes acknowledged), the factor only scales the arrays (slots per live tombstone = f), the real cap is the memtable pool (control) |

### 5.2 Run 2?

**No** — 2026-10-23. Both tiers measured the resource directly (unit: the array lengths and the Jamm size; cluster: live heap from the histogram), the readings match the audited prediction numerically (slots per tombstone equal f), the self-check re-derived them from the raw files, and the result neither refutes the case nor confirms a bypass. The one frozen criterion that did not hold as written is a wording defect for factors outside the legal range, and its effect is bounded by the in-range pairs and the POST-HOC line.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested:** unit — `range_tombstone_list_growth_factor` does not cap the memory a `RangeTombstoneList` uses: changing it changes the capacity slack (about (f − 1) × n slots) but sets no maximum; the target line 696 path (`copyArrays` → `grow(int)`) does not read the factor at all (B1). Cluster — `range_tombstone_list_growth_factor` does not cap the memory a memtable uses: memtable on-heap use rises with the factor only by the slack, with no ceiling tied to f, and `memtable_heap_space` is the binding cap (B1, B3f).
"Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1, 2 and 4 (capacity follows the iterated ceil(c*f); usage follows n; addAll capacity is the same across f) (with the recorded failure of the frozen pair bound for factors outside 1.2–5.0, §4.2 part 2) | does not cap | run 1 + self-check | 2026-10-23 |
| Cluster | **Confirmed** — B3g row 1 and the positive-control row | does not cap | run 1 + self-check | 2026-10-23 |

**Positive control** (a negative-estimate file only): the cluster cells at the small `memtable_heap_space` moved while the factor stayed unchanged — 256 MiB: 5 memtable-limit flushes, counter under 84.6 MiB, against no flush and 504 – 580 MB of counter at 3072 MiB. Unit: the c = 1,024, n < c cells (capacity stays 1,024 at every f).

**Feedback filed:** the case file's section D "Stage-4 feedback" field updated (case file untracked: no commit; it holds the dated summary and the amendments R1–R8 in section B5); no section amended beyond B5. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` were not edited (the human closes them); the sha256 to record in `_INDEX.md` §4 is the cluster version in §1.

### What stays on the node (`pc07`)

- Working trees `~/cassandra-rtl-n` (471 MB, built, probe removed, `git status` empty).
- Node data `~/stage4-rtl-n/` (data, commit log, `conf/`, `logs/`, Byteman traces) and full logs `~/stage4-logs/rtl/n/` (run1, shake1, shake2) plus `~/stage4-logs/rtl/*.out` driver outputs.
- Nothing is running: `ps -eo pid,args | grep -E '[C]assandraDaemon|[c]luster-run|[H]eapPoll|[J]mx '` printed nothing after the run (re-checked at the end of the session). No iptables rules, no `sudo`, nothing under `/proj` besides this repository's files. `pc12` was not touched.
