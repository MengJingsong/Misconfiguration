# seed_count_warn_threshold-getseeds-seeds_size--autonomous — stage-4 results  <!-- file: results/seed_count_warn_threshold-getseeds-seeds_size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`seed_count_warn_threshold-getseeds-seeds_size--autonomous`](../../stage3-ai-deep-read/cases/seed_count_warn_threshold-getseeds-seeds_size--autonomous.md)
>
> **Status:** verdict filed 2026-10-27 — unit and cluster Confirmed (does not cap), positive control moved in both; no run 2
>
> **Outcome class:** true negative (stage-3 estimate `negative`, stage-4 effect `does not cap`)
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); the feedback section is section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 after the audit's amendments, taken before any run: `9dfc9412510f29f929e4727adf1342c226c469bb13c1cb0fb244519b83395251`. File committed at `6e6cf92`; amendments uncommitted. After the first unit attempt a dated runbook-fix note (B2) and section D were added (claim, predictions, rows unchanged): final sha256 `c46efebd46b6b399c72eac5de0561c15307779aa5f99cda727016128c7911b42`. |
| **Harness** | `harness/seed_count_warn_threshold-getseeds-seeds_size--autonomous/` (uncommitted): `SeedCountFootprintTest.java`, `unit-run.sh`, `cluster-run.py`, `chain.sh`. |
| **Tiers and values** | Unit: K = 25, 1000, 20000 x {U with T default 20, U with T = 2K, P with T default}, 3 repetitions (27 cells). Cluster: one node, K = 25 and 1000, U default / U T = 2K, P default (6 starts, 150 s each). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note |
|---|---|---|---|
| A | quantity is memory or disk bytes | Partly -> Met | The file says "no constraint". Amended to name the heap of the seed list (and what a node builds per seed). |
| A | knob varied (>= 3 values incl. default) | Not met -> Met | Both tiers were `n/a`. Unit and cluster now vary K and T (default 20, 2K). |
| A | real resource measured | Not met -> Met | Deep size, live heap per copy, `jmap -histo:live` totals and instance counts. |
| A | driven to the limit and past it | Not met -> Met | K of 25 to 20000 against T = 20. |
| A | positive control (negative claim) | **Not met** -> Met | None possible from the source alone; arm P (copy that truncates the list to the threshold) is a real cap on the same object. |
| B | steps establish; prediction stated; rows for every outcome; disallow evidence; alternatives | Not met -> Met | B2f/B2g/B3f/B3g written (amendment). Disallow evidence = WARN line and the returned size. |
| C | human / AI can follow; exact values | Partly -> Met | Seeds as unrouted IP literals, JVM property vs yaml, one JVM per cell (static final), all stated. |
| D | harness exists | Met | Written in step 1; `~/s4-base`, `~/s4-seed-b` built (`ant build-test` 1 min 20 s / 1 min 16 s). |
| D | workload reaches the limit | Met | Deep size 2.6 MB at K = 20000; 1000-seed node (about 34 MB more heap); 251 GiB RAM, 53 GB disk. |
| D | citations | Met | `SimpleSeedProvider.java:43, 57, 81, 110-115`, `CassandraRelevantProperties.java:490`, `DatabaseDescriptor.java:2920-2922` match the pinned source. A3's caller list (`StorageService.java:879...`) also matches. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Promote the optional check to real tiers | Applied (amendment 2026-10-27 at B2, B3) | Negative claim needs a positive control |
| R2 | Patched copy truncating the list as control | Applied | Same |
| R3 | Predictions and rows in numbers | Applied | Group B |
| R4 | A3 says the list is "returned to the caller"; also note `getSeeds()` is uncached and re-reads the yaml per call, and the gossiper builds a connection set per seed | Left for stage 3 (found in the run, section D) | Understanding |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 20:3x to 21:0x MDT, cluster after) |
| Node | `pc29` (`node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB |
| OS / kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source | `~/s4-base` (arm U) and `~/s4-seed-b` (arm P, `run1/arm-P.patch`: one line at `SimpleSeedProvider.java:115`), from `copy-source.sh` of `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92` |
| Case-file / harness commit | `6e6cf92` (uncommitted amendments) / uncommitted |
| Node data | local disk `~/s4-seed` (removed) |
| Full logs | `pc29:~/stage4-logs/seed/` (accepted run), `seed-attempt1/`, `seed-attempt2-reps1/` (kept) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit attempt 1 | B2d | `heapPerCopy` polluted by the DEBUG lines each `getSeeds()` logs (375 KB per copy for a 132 KB list; arm P, 20 entries, still 245 KB) | logger to WARN after the first call, 2 s drain; note in B2 | applied, tier restarted (`run1/attempts/attempt1-run.out`) | uncommitted |
| 2 | unit attempt 2 | B2c (harness) | 20000 seeds as one argv exceed the 128 KB argument limit; the K = 20000 cells did not run (`attempt2-reps1-run.out` has the cells that did) | seed string via a file | applied, tier restarted from the beginning | uncommitted |
| 3 | cluster, 1st chain | harness | `cluster-run.py` f-string syntax error: all six starts failed at once, nothing started | fixed, chain rerun | no node was started in that attempt | n/a |
| 4 | cluster | harness | the `GETSEEDS count` line in `summary.txt` has a wrong regex (prints 0) | the count is taken from the raw `getseeds.txt` (excerpts, `selfcheck.py`) | left as is; `summary.txt` line ignored | n/a |

## 4. Run 1

**Scope:** both tiers, all values above. **Command log:** `run1/unit/summary.txt`, `run1/cluster/<start>/summary.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`; 27 cells; the three repetitions agree on every exact column, `heapPerCopy` within 0.3 %).

| K | arm / threshold | returned | WARN lines | deepBytes | heapPerCopy (bytes, 3 reps) |
|---|---|---|---|---|---|
| 25 | U, default 20 | 25 | 1 | 3,368 | about -42,450 (offset) |
| 25 | U, T = 50 | 25 | 0 | 3,368 | about -42,450 |
| 25 | P, default | 20 | 1 | 2,704 | about -43,100 |
| 1000 | U, default | 1000 | 1 | 132,064 | 113,621 to 113,744 |
| 1000 | U, T = 2000 | 1000 | 0 | 132,064 | 113,778 to 114,028 |
| 1000 | P, default | 20 | 1 | 2,704 | about -43,000 |
| 20000 | U, default | 20000 | 1 | 2,640,064 | 2,634,728 to 2,636,759 |
| 20000 | U, T = 40000 | 20000 | 0 | 2,640,064 | 2,634,725 to 2,634,827 |
| 20000 | P, default | 20 | 1 | 2,704 | -599; -538; -2,239 |

`DatabaseDescriptor.getSeeds().size()` equals `returned` in every cell.

**Cluster tier** (`run1/cluster/<start>/summary.txt`, `excerpt.txt`; threshold property read back from `/proc/<pid>/cmdline`; K includes the node itself).

| Start | WARN lines in 150 s | `nodetool getseeds` peers | live bytes (`jmap -histo:live`) | `InetAddressAndPort` | `OutboundConnections` |
|---|---|---|---|---|---|
| U, K = 25, default | 12 | 24 | 65,950,312 | 27 | 24 |
| U, K = 25, T = 50 | 0 | 24 | 65,988,216 | 27 | 24 |
| U, K = 1000, default | 12 | 999 | 99,614,856 | 1002 | 999 |
| U, K = 1000, T = 2000 | 0 | 999 | 99,614,008 | 1002 | 999 |
| P, K = 1000, default | 12 | 19 | 65,785,576 | 22 | 19 |
| P, K = 25, default | 12 | 19 | 65,801,272 | 22 | 19 |

### 4.2 Conclusion and logic

1. **Validity.** The warn branch was taken exactly where T < K (WARN 1 per unit cell, 12 per 150 s start) and not where T > K **[observed: `run1/unit/run.out`, `cluster/*/summary.txt`]**; the threshold property was read back in each start **[observed: `READBACK` lines]**; arm P's patch is the one line **[observed: `run1/arm-P.patch`]**; usage was driven: 20000 seeds in the unit tier, 999 peers on the node **[observed]**. Valid.
2. **Readings.** `heapPerCopy` has a constant offset of about -43 KB at small K (baseline after the first call's garbage) and is read in shape only; `deepBytes` is exact. The `GETSEEDS` line in `summary.txt` is wrong (defect 4); the counts come from `getseeds.txt` **[observed: `excerpt.txt`]**.
3. **Matched row.** Unit B2g: *Arm U identical across T at each K (returned = K, deepBytes equal, heapPerCopy within 20 %), WARN present only for T below K, arm P smaller by the factors above* — Confirmed. Returned = K in all 18 arm U cells; deepBytes equal across T (3368; 132,064; 2,640,064); 20000:1000 deep ratio 19.99; arm P returns 20 with 2,704 B (below 1/100 of arm U at K = 20000, heapPerCopy -0.5 to -2.2 KB vs 2.63 MB) **[observed]**. Cluster B3g: *U equal across T at each K, WARN only for T < K, P's counts far below U's at K = 1000* — Confirmed: live bytes 99,614,856 vs 99,614,008, `OutboundConnections` 999 in both, 19 for P; K = 1000 holds 33.7 MB more than K = 25 **[observed]**.
4. **Excluded rows.** *Refuted* (U follows T): all U pairs identical, excluded. *Control failed*: P shrinks on every measure, excluded. *Branch wrong*: WARN counts as predicted. *Not driven far enough*: 999 peers contacted, excluded.
5. **Observed vs. inferred.** Inferred: that the 34 KB per seed at K = 1000 is the `OutboundConnections` sets **[inferred: instance count equals K-1 and bytes in the histogram head are shallow only; the 33.7 MB was not attributed by a dump]**; this does not affect the verdict, which compares U across T.
6. **Deviations and gaps.** The first two unit attempts and the first cluster chain were restarted (defects 1 to 3). Only IP literals were used (no DNS). The cluster tier read 150 s of gossip once per cell (no repetition); the unit tier three repetitions.
7. **Core question.** Neither the size nor the memory of anything built from the seed list changes with the threshold: the returned list, its deep size, the node's live heap and its per-seed connection objects are the same for T below and above K, and they all scale with K (unit 20:1000 deep ratio 20; node +33.7 MB for 975 more seeds). The control, a copy that does truncate at the threshold, moves all of them. So the threshold caps nothing and only logs.

**Conclusion (one line):** unit and cluster: Confirmed — the threshold does not cap (positive control moved).

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (output `run1/selfcheck.out`) re-parses `unit/run.out`, `cluster/*/summary.txt` and `excerpt.txt`: 34 PASS, 0 FAIL.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | WARN/no-WARN split, read-back, 999 peers: re-read in `selfcheck.out`. |
| 2. Readings | yes | Offset and the wrong `GETSEEDS` line stated; counts re-taken from the raw file. |
| 3. Matched row | yes | All numeric criteria of B2f/B3f re-tested by the script. |
| 4. Excluded rows | yes | Same. |
| 5. Observed vs. inferred | yes | The only inference does not carry the verdict. |
| 6. Deviations | yes | Listed in §3. |
| 7. Core question | yes | Follows the B1/B2/B3 logic: U across T, P as control. |

### 5.2 Run 2?

No — 2026-10-27. The verdict compares identical numbers across T (exact in the unit tier) and the control moved; no inferred statement carries it.

## 6. Run 2 — optional

Not done.

## 7. Comparison

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative.

**Claim tested:** the check at `SimpleSeedProvider.java:110` does not cap memory or disk: with more seeds than the threshold the full list is still returned and only a WARN line is logged.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (arm U identical across T; arm P moved) | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (U identical across T; P moved) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** arm P, a source copy that returns `subList(0, threshold)` when the list is longer than the threshold: returned 20 of 25/1000/20000, deep size 2,704 B vs 2.64 MB; on a node 19 peers and 65.8 MB live heap vs 999 peers and 99.6 MB. The control is an artificial cap on the same object and the same instruments; no closed Confirmed case exists on this knob.

**Feedback filed:** section D of the case file (uncommitted); B2/B3 amendments and the runbook-fix note (uncommitted).
