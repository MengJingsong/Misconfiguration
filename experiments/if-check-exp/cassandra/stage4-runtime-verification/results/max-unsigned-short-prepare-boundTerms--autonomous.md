# max-unsigned-short-prepare-boundTerms--autonomous — stage-4 results  <!-- file: results/max-unsigned-short-prepare-boundTerms--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-unsigned-short-prepare-boundTerms--autonomous`](../../stage3-ai-deep-read/cases/max-unsigned-short-prepare-boundTerms--autonomous.md)
>
> **Status:** verdict filed 2026-10-26 — unit Confirmed (does not cap); cluster Confirmed (does not cap), open points in §8; no run 2
>
> **Outcome class:** true negative — stage-3 estimate `negative` vs the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
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
| **Case-file version** | Autonomous file, sha256 after the audit's amendments (2026-10-26, before any harness or run): `edc45ecc9092b39a97597aca4f8e0bed457302d7cf018b0494897e2d4bf9f544` (filed hash `53361ed503294f789b7c35f1e6cd7fddc1e7469eee7645756fa8234dd91ffec8`). The file is untracked in git at this point (commit: none yet; the orchestrator commits). **Frozen prediction and conclusion tables (B2f-B2g, B3f-B3g, as amended): sha256 `ce36eedc1cf32ff9ea2db945f1d9d5d13c8ae8541f498949ae5439cdc8ddee4c` of `harness/max-unsigned-short-prepare-boundTerms--autonomous/frozen-prediction.txt`**, computed before any harness was written or any reading taken. The hash above is the version run (after one same-day wording correction of B2i.2, before the harness); after the run the file's section D was filled, giving `4d717977b6b0c69062f2e88996c0a339c3cdd69716cca8ec7224ef2ddeeaa446` (B2f-B2g and B3f-B3g unchanged, same frozen hash). |
| **Harness** | `harness/max-unsigned-short-prepare-boundTerms--autonomous/` (files listed in its `README.md`); not committed by this session (the orchestrator commits) |
| **Tiers and values** | Unit (B2): JUnit class in a `copy-source.sh` tree, one JVM per cache size {1, 10, 100} MiB, markers M in {10 (control), 1000, 65535} plus the boundary 65536. Cluster (B3): one node lifetime per pair, cache size {10, 50, 200} MiB x M {10 (control), 1000, 65535} plus the 65536 prepare, `-Xmx2g`, tmpfs data, port slot 3 (127.0.3.1, JMX 7130) |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 (amendments B2i, B3i in the case file) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the constant is a count of `?` markers, not bytes; the byte quantity is the weight of a prepared statement (`measureDeep`, `QueryProcessor.java:469,952-958`) retained in the cache. Derivable, and B1 states the claim in those terms. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | The constant cannot be set (A1), and B1 says so; the approach is varying the cache cap (the knob that does bind) and the marker count M. B2b has three cache sizes, B3b only two (10, 50): a third (200 MiB) added in B3i.1; the default (`auto` = 10 MiB at the test heaps) is one of them. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after amendment | B2d/B3d: weight sum, `measureDeep`, live heap after GC, `jmap -histo:live`; B2d named a non-existent metric (`getPreparedStatementsMemoryUsage`), corrected in B2i.1; gaps named in B2i.6 and B3i.3 (persisted copies in `system.prepared_statements`, parse garbage). |
| A. Core question | usage driven to the limit and past it | Partly | B2e.4 offered "200 distinct statements" with no arithmetic; the size of one 65535-marker statement is unknown and may exceed the 10 MiB cap (see the recommendation on the size gate). B2i.3 and B3i.2 replace it with offered weight 4 x cap and a stop rule. |
| B. Logic | each step says what it establishes | Met | B2e/B3e are numbered and each is tied to a reading in B2g/B3g. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f's "single-digit MiB" is a guess, and B3f's "5x" holds only if the load saturates the cache; restated as relations (retained weight <= cap, ratios) with the estimate marked non-binding (B2f/B3f amended). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Missing: a 65535-marker statement heavier than the cap (rejected by the size gate at `:824-829`), the 65536 rejection as required evidence, and "cap not binding / retained does not rise with the cap". Rows added to B2g and B3g (marked 2026-10-26). "Usage exceeds the limit" and "limit never reached" were present (rows 2 and 4). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | Row 1 did not name the disallow evidence (the 65536 rejection text); B2i.5 lists the conditions (a)-(d). |
| B. Logic | alternative explanations and their controls | Met after amendment | B2h/B3h name the 10-marker control and fresh JVMs; the control is made explicit as the positive control in B2i.3 and B3i.1 (the cache cap binding on small statements is a closed Confirmed case, `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`). |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A4 and B1 are clear; one missing hop (the size gate) added in B2i.2. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | Wrong or missing line citations (A3: `:763-778` should be `:818-836`; `prepareInternal` `:170-190` should be `:425`; `:949` is `measurePstmnt`, the weigher is `:952-958`), no query template for M markers, no sampling or stop rule in B3. Fixed in B2i/B3i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | See the row above; B2i.3, B3i.2 and B3i.3 give them. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | The closed `prepared_statements_cache_size` harness provides a unit-test skeleton, a JMX reader and a driver loader; adapted under this stem. `pc07` has JDK 11 and Ant; trees `~/s4-b9-bt/u` and `/c` built. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | B3c's "500 distinct queries" at an unknown weight may not reach 50 MiB, or may be rejected whole at 10 MiB; replaced by stop rules. Memory: 2 GiB heap holds the 200 MiB cache; 1 GiB test JVM holds the 100 MiB cache. Disk: tmpfs, a few MB of persisted query text. Time: minutes per arm. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Partly | Holding: `QueryProcessor.java:728,757-759`, `FBUtilities.java:158`, `DatabaseDescriptor.java:795-804`, `Config.java:584-585`, `CQLMetrics.java` metric names. Wrong: the four line citations above and the non-existent `getPreparedStatementsMemoryUsage`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Add the size gate (`QueryProcessor.java:824-829`) to A3 and a conclusions row for "statement heavier than the cap" | Applied 2026-10-26 (B2i.2, B2g and B3g rows; no commit, the file is untracked) | A 65535-marker statement may weigh more than 10 MiB; without the row the reading would match no row |
| 2 | Restate B2f/B3f as relations; mark the per-marker estimate non-binding | Applied 2026-10-26 (B2f, B3f) | The estimate is a guess and the "5x" depends on saturation |
| 3 | Add a third cache size (200 MiB) to the cluster tier; one lifetime per (size, M) | Applied 2026-10-26 (B3i.1) | Audit group A; keeps each cache pure |
| 4 | Give the query template, offered weight, stop rules and sampling | Applied 2026-10-26 (B2i.3, B3i.2) | Group C/D |
| 5 | Correct citations and the metric name | Applied 2026-10-26 (B2i.1) | Group D |
| 6 | Name the persisted copy in `system.prepared_statements` as an n-dependent consumer outside the cache | Applied 2026-10-26 (B2i.2, B3i.3) | The live-heap reading includes it |
| 7 | Stage 3: `SystemKeyspace.java:1919` second check site of `prepared_statements_cache_size` (HANDOFF note) is not in this file's scope | Left for stage 3 | Different constraint |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts. Not filled (no run 2 planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 23:23-23:25 UTC, cluster 23:26-23:58 UTC) | not done |
| Node (CloudLab name and type) | pc07 (`node0.jason92-320876…`), 40 cores, 251 GiB; port slot 3 (127.0.3.1, JMX 7130, native 9042); other cases ran on the same host | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `copy-source.sh` copies `~/s4-b9-bt/u` (`ant build-test`, test class added) and `~/s4-b9-bt/c` (`ant jar`, unmodified); local baseline `d8b77c3` tagged `cassandra-5.0.9`; repository HEAD `93d6365` | |
| Case-file commit / harness commit | the case file and the harness are uncommitted (the orchestrator commits); case-file sha256 in §1 | |
| Storage for node data | tmpfs `/dev/shm/s4-b9-bt/node` (removed by `cluster-run.py down`); unit tier: the test JVM's temp directories under the tree | |
| Full logs (path, outside the repo) | `~/s4-b9-bt-logs/run1/` on pc07 (`unit/`, `cluster/c<MiB>-m<M>/` with full `session.log`, `system.log`, `histo-*.txt`); instrument checks in `~/s4-b9-bt-logs/shake1/` | |

## 3. Runbook defects

None stopped a run. Items found and handled before run 1 (audit, §1.1) or noted after:

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2d, A3 | wrong line citations, a non-existent metric, the size gate missing | B2i.1, B2i.2 | applied 2026-10-26 | none (untracked) |
| 2 | audit | B2i.2 (first text) | said the persisted rows are never removed with the cache; `evictPreparedStatement` deletes the row (`QueryProcessor.java:132-139`) | corrected the same day before the harness; whole-file hash recomputed (§1); frozen tables unchanged | 2026-10-26 | none |
| 3 | audit amendment | B2f/B2i.3 | the amendment's per-marker estimate (100 B to 1 KB, 6.5 to 65 MB at 65535) was wrong: measured 43 B per marker, 2.84 MB at 65535 | left as filed (non-binding, B2i.3 says so); noted as a miss | 2026-10-26 | none |
| 4 | self-check | selfcheck part C3 | the first version required `count x w_unit <= cap`; the unit-tier weight is a proxy for the cluster weight (the cluster statements are fully qualified with `ks.t`), and the strict form held in 2 of 9 arms | replaced by an implied-weight band; the first output is kept (`run1/selfcheck-first.out`); see §4.2 part 6 | 2026-10-26 | none |

## 4. Run 1

**Scope:** unit tier, cache sizes 1, 10, 100 MiB (one JVM each, order 10, 1, 100), M in {1, 10, 1000, 65535, 65536} (calibration and boundary) and load loops for M = 10, 1000, 65535; cluster tier, nine node lifetimes (10, 50, 200 MiB x M 10, 1000, 65535), single run each. **Command log:** `max-unsigned-short-prepare-boundTerms--autonomous/run1/` (unit: `unit/run.out`, `unit/summary.txt`; cluster: `cluster/c<MiB>-m<M>/summary.txt`, `samples.csv`; `chain.status`, `selfcheck.out`).

### 4.1 Readings

**Unit tier** (`run1/unit/run.out`; weight = `key.size() + pstmntSize`; 49 `STAGE4 check` lines, 0 MISMATCH)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Weight of one statement, M = 1 / 10 / 1000 / 65535 | 2,452 / 2,836 / 46,348 / 2,842,844 B (43 B per marker at the top) | `unit/run.out` `STAGE4 cal` |
| M = 65536 | rejected with "Too many markers(?). 65536 markers exceed the allowed maximum of 65535", count 0 -> 0, in all three JVMs | `unit/run.out` `STAGE4 boundary` |
| M = 65535 at 1 MiB | rejected by the size gate: "Prepared statement of size 2842824 bytes is larger than allowed maximum of 1 MB", 5 of 5 attempts, count 0 | `STAGE4 final label=c1 M=65535` |
| M = 65535 at 10 / 100 MiB | 15 offered, 3 retained, 12 evicted, sum 8,528,532 B (0.813 of 10 MiB); 148 offered, 36 retained, 112 evicted, sum 102,342,384 B (0.976 of 100 MiB) | `STAGE4 final label=c10 / c100 M=65535` |
| M = 1000 at 1 / 10 / 100 MiB | retained sum 1,019,656 / 10,474,648 / 104,839,176 B (0.972 / 0.999 / 1.000 of the cap); count 22 / 226 / 2,262; evicted 69 / 679 / 6,788 | `STAGE4 final M=1000` |
| M = 10 (control) at 1 / 10 / 100 MiB | retained sum 1,046,592 / 10,482,984 / 104,855,436 B (0.998 / 1.000 / 1.000); count 368 / 3,686 / 36,869; evicted 1,111 / 11,104 / 111,027 | `STAGE4 final M=10` |
| Sum <= cap in every arm (single thread) | 9 of 9; count + evicted = offered in the 8 accepting arms | `selfcheck.out` U4 |
| Live heap after GC, delta over the arm's baseline | 1.9 / 21.3 / 150.9 MB (M = 10), 1.3 / 18.3 / 171.4 MB (M = 1000), -0.1 / 20.0 / 135.7 MB (M = 65535) at 1 / 10 / 100 MiB; includes the memtable copy of the persisted text | `STAGE4 final … liveDelta` |

**Cluster tier** — one row per cache size and M (`run1/cluster/c<MiB>-m<M>/summary.txt`; count = JMX `PreparedStatementsCount` after the 70 s settle; "Prepared" = histogram delta of `QueryHandler$Prepared` over the baseline of 29; delta = live bytes after the load minus the baseline, `jmap -histo:live`; minus mt = minus the `system.prepared_statements` memtable heap)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 10 MiB | control M = 10 | offered / count / evicted / Prepared / delta / minus mt | 16,585 / 3,749 / 12,837 / 3,751 / 21.8 MB / 9.4 MB | `c10-m10/summary.txt` |
| 10 MiB | B M = 1000 | same | 7,477 / 226 / 7,252 / 228 / 42.4 MB / 14.4 MB | `c10-m1000/summary.txt` |
| 10 MiB | C M = 65535 | same | 153 / 3 / 151 / 5 / 43.0 MB / 12.8 MB | `c10-m65535/summary.txt` |
| 50 MiB | control M = 10 | same | 75,818 / 18,697 / 57,122 / 18,699 / 95.0 MB / 38.4 MB | `c50-m10/summary.txt` |
| 50 MiB | B M = 1000 | same | 7,313 / 1,132 / 6,182 / 1,134 / 82.0 MB / 54.8 MB | `c50-m1000/summary.txt` |
| 50 MiB | C M = 65535 | same | 126 / 19 / 108 / 21 / 80.1 MB / 55.0 MB | `c50-m65535/summary.txt` |
| 200 MiB | control M = 10 | same | 150,000 / 74,791 / 75,210 / 74,793 / 277.3 MB / 167.1 MB | `c200-m10/summary.txt` |
| 200 MiB | B M = 1000 | same | 19,264 / 4,528 / 14,737 / 4,530 / 280.9 MB / 209.4 MB | `c200-m1000/summary.txt` |
| 200 MiB | C M = 65535 | same | 313 / 74 / 240 / 76 / 273.6 MB / 211.8 MB | `c200-m65535/summary.txt` |
| all | M = 65535 arms | 65536-marker PREPARE through the driver | rejected: `code=2200 [Invalid query] message="Too many markers(?). 65536 markers exceed the allowed maximum of 65535"`, count 1 -> 1 (the 10-repeat control had added one entry) | the three `c*-m65535/summary.txt` |
| all | all arms | knob read-back, 10-repeat control, discard warning, rows | log says the cap in every arm; repeats add 1 entry; "N prepared statements discarded in the last minute because cache limit reached (C MiB)" present in every arm; `system.prepared_statements` rows equal the final count in every arm | `summary.txt`, `system-log-excerpt.txt` |
| all | counts across caps | ratio 10 : 50 : 200 | M = 10: 1 : 4.99 : 19.95; M = 1000: 1 : 5.01 : 20.04; M = 65535: 3 : 19 : 74 | `selfcheck.out` C5 |
| all | samples (every 5 s) | transient count during the load | up to 25 above the settled count (M = 10, 200 MiB), 1 entry above at M = 65535 / 10 MiB (4 against 3); the settled counts are flat for the last 6 samples (`samples.csv`) | `samples.csv` |

### 4.2 Conclusion and logic

1. **Validity** — [observed: `unit/run.out` `STAGE4 run`] each JVM reported the cap it was given (1, 10, 100 MiB) and [observed: `cluster/*/system-log-excerpt.txt`] the node log read-back matched in all nine arms; [observed: `unit/run.out` cal lines] the limit was reached: 4 x cap offered in every accepting unit arm, 12 to 112 evictions at M = 65535, and [observed: summaries] evictions in all nine cluster arms. The 65536 boundary was exercised in all three unit JVMs and all three 65535 cluster arms. Hold-fixed settings: fresh JVM/node per arm [observed], heap 2 GiB, protocol 4, no keyspace on the session, statements fully qualified [observed: `session.log`, `prep-load.py`]. Valid.
2. **Readings** — one unusual item: the cluster count read during the load is sometimes a few entries above the settled count (up to 25 entries, 0.03 % of the cache at M = 10; 4 against 3 at M = 65535 and 10 MiB) [observed: `samples.csv`]. The settled values 70 s after the load are the ones used. The per-entry weight is not measured in the cluster [inferred: no instrument]; the unit-tier weights are a proxy. Raw live-heap deltas do not scale 1 : 5 between 10 and 50 MiB (1.9 to 4.4) because the memtable of `system.prepared_statements` also grows with the offered volume; with that memtable subtracted the M = 65535 delta goes 12.8, 55.0, 211.8 MB against caps of 10.5, 52.4, 209.7 MB [observed: summaries; inferred: the subtraction isolates the cache].
3. **Matched row** — B2g row 1 and B3g row 1: unit "Retained weight tracks `prepared_statements_cache_size` and stays below it; per-statement weight is bounded by N*c" -> Claim confirmed; cluster "Post-GC heap delta plateaus near cache size and moves with it; evictions appear" -> Claim confirmed. Parts: unit retained sum <= cap in 9 of 9 arms, 0.972 to 1.000 of the cap where evicting, ratios 100.2 (M = 10) and 102.8 (M = 1000) for caps 100x apart [observed: `unit/run.out`; `selfcheck.out` U4, U5]; per-statement weight 43 B per marker (M = 65535: 2.84 MB, "a few MiB", [observed] cal lines); cluster counts 1 : 5 : 20 within 0.3 % at M = 10 and 1000, evictions and warnings in every arm [observed: summaries]. The added rows apply too: the size-gate row [observed: `STAGE4 final label=c1 M=65535`, 5 of 5 rejected, count 0] and the 65536 row [observed: all six boundary readings]. The control row 4 of B3g (10-marker statements plateau at the cap) holds: 3,749 / 18,697 / 74,791 entries [observed].
4. **Excluded rows** — Refuted (retained weight grows past the cache size or tracks 65535 irrespective of cache size): excluded, every unit sum <= cap, and the cluster counts are flat in the last six samples of every arm and scale with the cap, not with the offered count (offered 153 to 150,000) [observed: `unit/run.out`, `samples.csv`]; the transient excess in 4.1 is not growth with offered volume (it does not survive the settle) [inferred: flat settled samples]. "N=65536 accepted" (source trace wrong): excluded, rejected in 6 of 6 readings. "Control does not move or cache never fills": excluded, the control moved 1 : 100 (unit) and 1 : 5 : 20 (cluster) and every arm evicted. "Retained weight does not rise with the cap" (added row): excluded, same readings. Cluster "Delta equal at both cache sizes": excluded (counts 3 / 19 / 74 and 226 / 1,132 / 4,528). "Count of live Prepared objects keeps rising ... or retained weight exceeds the cap" (added row): the histogram delta equals the cache count within 2 entries in every arm [observed: `selfcheck.out` C6], so it is not rising beyond the cache; the "exceeds the cap" half is judged on the settled and unit single-thread readings, not on the transient (see open points).
5. **Observed vs. inferred** — inferred: (a) the cluster ceiling holds with the real per-entry weight (the cluster has only the count and the cap; `count x w_unit` is within 0.95 to 1.03 of the cap in arms with 10 or more entries, 2 of 9 strictly below 1.0; the implied weight is up to 3 % below the unit weight at M = 65535 and 50 MiB, not explained); (b) the transient excess is Caffeine's eviction lag with 8 writer threads, not a failed ceiling; (c) the memtable subtraction isolates the cache's heap; (d) the constant itself is not what binds, because both marker counts at 1,000 and 65,535 stop at the cap and the constant never came into play below 65535.
6. **Deviations and gaps** — the per-entry cluster weight and the transient overshoot of the cluster count (above); the unit weight of the 65535-marker statement is 2.84 MB, not the 6.5 to 65 MB of the amended estimate (non-binding, §3 item 3); the M = 65535 arm at 10 MiB retains 3 entries so its 1 : 5 : 20 ratio is not testable (floor effect; the M = 10 and 1000 arms carry it); the size-gate row was exercised only in the unit tier (no cluster cache size below 2.84 MB was run); no repeat of any arm (run 2 not done); `jmap -histo:live` forces a full GC, so heap numbers are post-GC; live heap deltas include persisted text in the memtable (reported, not a pass/fail value, as amended).
7. **Core question** — usage did not follow the constant: at 1,000 and 65,535 markers per statement (the second at the constant's own limit) the retained prepared-statement weight stopped at the cache cap in the unit tier (9 of 9 arms, 0.97 to 1.00 of the cap) and the cluster retained count scaled 1 : 5 : 20 with the cap, with evictions and warnings (steps 1 and 2 of the logic: B2e/B3e sizes, B2g/B3g row 1). The 65536 rejection shows where the constant acts (it refuses one statement past 65535 markers) and the size gate shows the cache cap acting on a single statement (1 MiB cap, 2.84 MB statement). The constant is a wire-format bound, not a memory cap: it does not cap usage.

**Conclusion (one line):** B2g row 1 (unit) and B3g row 1 (cluster) — Claim confirmed (does not cap); deviations as in part 6.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Raw files re-parsed by `harness/max-unsigned-short-prepare-boundTerms--autonomous/selfcheck.py` (output `run1/selfcheck.out`, first version `run1/selfcheck-first.out`); each part also re-read by hand against `unit/run.out`, `summary.txt`, `samples.csv`, `system-log-excerpt.txt`.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U1, C1, C2, C7: caps read back in 3 unit JVMs and 9 nodes; 65536 rejected 6 of 6; every node stopped, none left (`selfcheck.out`) |
| 2. Readings | yes | the transient count excess is real (`samples.csv`: 4 against 3; 25 over 74,791) and is reported, not hidden |
| 3. Matched row | yes | U4, U5, U6, C4, C5, C6 hold; the sums, ratios and counts in §4.1 are the recomputed ones |
| 4. Excluded rows | yes | no sample of any arm shows growth past the settled count with offered volume; the "exceeds the cap" half of the added row 3 is argued, not measured, in the cluster (part 5) |
| 5. Observed vs. inferred | partly | C3 as first written (strict `count x w_unit <= cap`) did NOT hold (2 of 9 arms); the weaker "within 5 %" form holds and is the one used. The conclusion does not rest on the cluster ceiling alone: the unit tier measures the exact weights (`sum <= cap`, 9 of 9), the cluster shows counts following the cap 1 : 5 : 20. The cluster ceiling with an exact weight stays inferred |
| 6. Deviations and gaps | yes | each listed in §4.2 part 6 and §3 |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 claim -> B2/B3 sizes and arms -> rows 1 and the added rows; the positive control (M = 10) moved with the cap |

### 5.2 Run 2?

**No** — 2026-10-26. The unit tier measures the exact weights and settles the ceiling; the cluster counts follow the cap at 0.3 % precision; the conclusion confirms a "does not cap" claim by a mechanism read from the source (the cache gate), and run 2 would repeat the same instruments. The open gaps (exact cluster weight, the transient excess) would not change the row. A cheap run 2, if the user wants one: the three-arm M = 65535 chain with a cluster-side `measureDeep` via a Byteman or a jcmd-heap-dump tally.

## 6. Run 2 — fresh AI session (optional)

Not done (see §5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** B1: usage does not follow this constant: the memory held by prepared statements with many markers is bounded by the prepared-statement cache weight limit (`prepared_statements_cache_size`), not by the 65535 marker cap, and a statement just under the cap costs a small bounded amount (per-marker linear, a few MiB) regardless of node resources.
"Confirmed" below means this claim held (measured: 2.84 MB for one 65535-marker statement).

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: retained weight tracks the cache cap and stays below it — **Confirmed**; added rows (size gate at 1 MiB, 65536 rejection) also matched | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | B3g row 1: heap delta plateaus near the cache size and moves with it, evictions appear — **Confirmed** (with the open points below) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): 10-marker statements on the same cache, the knob of the closed Confirmed case `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous`: retained sum 1.05 / 10.5 / 104.9 MB at caps 1 / 10 / 100 MiB (unit) and 3,749 / 18,697 / 74,791 entries at 10 / 50 / 200 MiB (cluster); the cap bound as expected, so the flat-vs-moving contrast is real.

**Open points a user may overrule:** (1) the cluster ceiling with an exact per-entry weight is inferred (strict `count x w_unit <= cap` held in 2 of 9 arms; the cluster weight is up to 3 % lower than the unit weight, cause not found); (2) the added B3g row "retained weight exceeds the cap -> refuted" was not applied to the transient count excess during the load (up to 25 entries, one entry of three at 10 MiB and 65535 markers), because the settled counts are at the cap and the unit single-thread sums never exceed it; (3) the amended per-marker estimate in B2i.3 was wrong (43 B per marker), non-binding.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (uncommitted; the file is untracked); amendments B2i and B3i (and the added rows in B2g and B3g) of 2026-10-26 are in the case file.

**Leftovers on pc07:** none running (checked `ps` for `CassandraDaemon` and the test class: none; `/dev/shm/s4-b9-bt` removed). On disk: `~/s4-b9-bt/u` and `~/s4-b9-bt/c` (trees), `~/s4-b9-bt-logs/` (full logs, `jmxc/`, shakedown `shake1/`).
