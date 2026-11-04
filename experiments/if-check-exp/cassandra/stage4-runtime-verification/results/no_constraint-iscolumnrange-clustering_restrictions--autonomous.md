# no_constraint-iscolumnrange-clustering_restrictions--autonomous — stage-4 results  <!-- file: results/no_constraint-iscolumnrange-clustering_restrictions--autonomous.md -->

> **Case:** [`no_constraint-iscolumnrange-clustering_restrictions--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-iscolumnrange-clustering_restrictions--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29. Unit tier filed: Not confirmed (frozen noise criterion U5 failed in two control cells; U1, U2 and U4 held, U3 missed equally for every arm). Cluster tier `n/a`. No run 2.**
>
> **Outcome class:** **undetermined** (estimate `negative`; the tier is Not confirmed, so the effect is `undetermined`) — [definition](../README.md#outcome-class). What the readings show if the noise row were set aside is in section 8; it is not the verdict.
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit tier, as amended 2026-10-29); B3 is `n/a`; feedback is section D. One results file per case file; the shared Java class is not shared (one class per case).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `a254c929`; the case file is tracked but modified (uncommitted). **sha256 after the audit's amendments (B2/B3 and section D, dated 2026-10-29): `37171657ef56cc5b33ebf35a743f8f261273e17a37cbe74f2227ab976e498ca1`**, written to `~/s4-none-logs/freeze.sha` on `pc32` (entry FREEZE6, 2026-10-29 04:25:27 UTC), before the run and before any allocation reading. |
| **Hash history** | Hash history (the first freeze to FREEZE5 were written before any allocation reading; FREEZE6 was written after the first complete attempt, see the next row; the file `freeze.sha` keeps every entry): first freeze 04:09:41 UTC `ced96f1242ba5fa0008d285dc47a9997627533af7df3a6a21d2080aebf089dfd`; FREEZE4 04:18:33 UTC `1cb6443b917c16754de7582362f90d898ce4d53b1b4e4898e6b48aa5e19eaaee` (runbook defect 1, section 3: the unit yaml's read-size guardrails aborted the first attempt of the first case at its control); FREEZE5 04:20:24 UTC `6bdd6ab078680893c4c07221f72ff622d4fb94bf7e1e7bab6d19a6987cb8133b` (defect 1 completed: a `QueryOptions` caches the thresholds, so the second attempt aborted the same way; the raw output of both aborted attempts was not read and was moved to `~/s4-none/attempt1-aborted/`). |
| **Second-attempt note** | FREEZE6 is the hash of the second complete attempt of the unit tier (the one filed as run 1). It was written after the first complete attempt (`run1a`, 04:21-04:23 UTC), whose analysis had read the readings; the amendments since FREEZE5 are runbook defects 2 (30 warm-up calls instead of 3) and change no prediction or tolerance. FREEZE6 `37171657ef56cc5b33ebf35a743f8f261273e17a37cbe74f2227ab976e498ca1`. |
| **Harness** | `harness/no_constraint-iscolumnrange-clustering_restrictions--autonomous/`: `NoneIsColumnRangeAllocTest.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; not committed. md5s at the start of the run: `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/harness.md5`. |
| **Tiers and values** | Unit only (B2 amended): N = 1,000 / 10,000 / 100,000; states memtable and sstable; arms F1, F2 (isColumnRange false), T1, T2, T3 (true), controls C1 (whole partition), C2 (LIMIT 10). Cluster: `n/a` (B3). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (git status clean for that folder). Operand kind: 2 (a boolean over the shape of the WHERE clause; the draft agreed). Re-read: `StatementRestrictions.java:98, 962-976`, `RestrictionSet.java:70, 146-149, 181, 362-365`, `SelectStatement.java:820-832, 970-978`, `ModificationStatement.java:484-490`, `AbstractReadCommandBuilder.java:194`, `TableMetadata.java:294-303`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly | There is no constraint (A1); the measured quantity is bytes allocated by one read, stated as a no-cap case. |
| A | knob varied, >= 3 values, or other approach with reason | Partly → Met | No knob. B2 (amended) sweeps both sides of the branch, two values per side, at three data sizes and two storage states (none-type-design 3). |
| A | real resource measured, not only the counter (gap named) | Partly → Met | B2c measures thread-allocated bytes of the read; the gap (allocation is not live heap) is named in B2i. |
| A | usage driven to the limit and past it | n/a | There is no limit; the data sizes reach 100,000 rows (about 17 MB). |
| A | positive control for a negative estimate | Not met → Met | Added: C2 (LIMIT 10) against C1 (whole partition), same instrument (B2h). |
| B | each step says what it establishes | Met | B2e (amended). |
| B | prediction in numbers or a clear relation | Not met → Met | Filed with none; B2f U1-U5 give ratios and tolerances. |
| B | every outcome has a conclusions row | Not met → Met | B2g gives six rows including a constant offset, noise and a control that does not move. |
| B | confirmation needs knob-follows and direct branch evidence | Met (adapted) | No knob; direct branch evidence is the filter class built by the production path (U1) and the Byteman return counts. |
| B | alternatives and controls | Met | B2h: text length and preparation outside the window, same result row, two storage states. |
| C | a human can follow it | Met | A1-A3, B1. |
| C | an AI can run it without re-deriving | Not met → Met | B2a-B2d give class, command, values, arms, instrument. |
| C | exact values and commands | Not met → Met | B2b, B2c. |
| D | prerequisites exist | Met | JDK 11, Ant 1.10.12 and an `ant build-test` tree on `pc32`; jamm and Byteman jars come with the build. |
| D | workload arithmetic reaches the limit | Met (n/a) | 100,000 rows x 100 B fit a 2 GiB heap. |
| D | citations spot-checked | Partly → Met | All held; one dead-code correction (`isStaticCompactTable()` is false in 5.0.9) and a flawed filed B3 control, both in section D. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Apply the operand-sweep design as B2; keep B3 `n/a` with the heap-noise reason | Applied, B2/B3 amendment 2026-10-29 | The filed B2 had no measurement. |
| 2 | Return the same row on every arm so the arms differ only in restriction shape | Applied, B2b | The filed B3 control compared different row counts. |
| 3 | Record that `isStaticCompactTable()` is always false in 5.0.9 (A1, line 964-971 is dead code) | Applied to section D; A1 left for stage 3 | Does not change the check. |

**Disclosures.** (1) A pre-run shakedown (the unit test at N = 200 and 400, plain and Byteman mode) was run on `pc32` to check that the harness compiles, the arms return what B2b says, and the Byteman rules parse. It read `proof.txt` (branch proof, states) and the Byteman trace counts, never `raw.csv` (allocation); its output was deleted and is not used as a reading. It found nothing that needed an amendment. (2) The numeric predictions were written in B2f before the harness existed and are not changed after any reading.

**Agreement criteria** — not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 UTC. The filed attempt ran 04:25 to 04:30 UTC (the node's shell shows MDT, 22:25 to 22:30); the first complete attempt `run1a` ran 04:17 to 04:23 UTC |
| Node | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 251 GiB; nothing else of this run's family on it; other agents used other nodes |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none/tree` made by `copy-source.sh` from `cassandra/cassandra-5.0.9/` (git status clean for that folder) at repository commit `a254c929`; `ant build-test` 1 min 8 s (`~/s4-none-logs/build.log`) |
| Case-file commit / harness commit | `a254c929` (case file modified, uncommitted) / not committed; sha256 in section 1 |
| Storage | local disk `/` (51 GB free); test data under `~/s4-none/run1/<case>/{plain,bm}/storage` |
| JVM | plain `java -Xmx2g` + `org.junit.runner.JUnitCore` (G1 default), jamm 0.4.0 attached; the second run adds Byteman 4.0.20 with `rules.btm` (counts only, not an instrument) |
| Full logs (outside the repo) | `~/s4-none/run1/<case>/` (`plain/`, `bm/`, `analyze.out`, `selfcheck.out`); first complete attempt `~/s4-none/run1a-attempt3/`; aborted attempts `~/s4-none/attempt1-aborted/`; freeze log `~/s4-none-logs/freeze.sha` |

## 3. Runbook defects

| # | Run | Step (B2) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | attempts 1 and 2 (the first case only; the chain stops at the first failure) | B2c, control C1 at N = 100,000 | The unit yaml (`test/conf/cassandra.yaml:64-69`) sets read-size guardrails (coordinator fail 4096 KiB, local fail 8192 KiB, row index fail 8192 KiB) that a default node does not have; `SelectStatement.maybeFail` (`:1077`) aborted the whole-partition read with `ReadSizeAbortException`. Attempt 2 aborted the same way because `QueryOptions.DEFAULT` caches the coordinator thresholds when it is built at class load (`QueryOptions.java:346`). | The test sets all six read-size thresholds to null and passes a `QueryOptions` built afterwards; applied to the other two cases before they ran | applied 2026-10-29 04:18 and 04:20 UTC; the raw output of both attempts was never read | case-file B2a (dated); uncommitted |
| 2 | first complete attempt `run1a`, all three cases | B2c warm-up | 3 warm-up calls leave the JIT unsettled: the noise criterion failed in the smallest cells and in the large-result controls (`no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/run1a/analyze.out`: pass-to-pass up to 30 percent, repeat spread up to 32 percent) | 30 warm-up calls per cell; every prediction and tolerance unchanged; the tier restarted from its beginning; `run1a` is kept in `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/run1a/` and disclosed here | decided 2026-10-29 04:25 UTC, after `run1a`'s analysis had been read | case-file B2a/B2c/B2e (dated); uncommitted |

No further defect occurred in the filed attempt.

## 4. Run 1

**Scope:** unit tier only (B3 is `n/a`), two JVM runs: plain (the instrument) and Byteman (return counts). N = 1,000 / 10,000 / 100,000, states memtable and sstable, arms F1, F2, T1, T2, T3, controls C1, C2; per cell 30 warm-up calls discarded and 7 timed calls, in two passes (A, B). **Command log:** `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/session-plain.log`, `session-bm.log`, `chain.log`; analysis `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out`; the first complete attempt (3 warm-ups) in `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/run1a/`.

### 4.1 Readings

Medians of the 14 timed values per cell (both passes), bytes allocated by the calling thread in one `executeLocally` call (`no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out`, `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/raw.csv`):

| State | Arm | N = 1,000 | N = 10,000 | N = 100,000 |
|---|---|---|---|---|
| memtable | F1 (names, `isColumnRange` false) | 5,496 | 5,328 | 5,256 |
| memtable | F2 (names, IN) | 5,496 | 5,400 | 5,256 |
| memtable | T1 / T2 (slice, true) | 5,048 | 4,912 | 4,840 |
| memtable | T3 (slice, true) | 5,052 | 4,928 | 4,864 |
| memtable | C1 whole partition | 271,504 | 2,173,360 | 21,285,344 |
| memtable | C2 LIMIT 10 | 7,184 | 6,576 | 6,576 |
| sstable | F1 / F2 | 6,992 | 12,424 | 14,488 |
| sstable | T1 / T2 | 6,648 | 12,000 | 14,064 |
| sstable | T3 | 6,672 | 12,024 | 14,088 |
| sstable | C1 | 573,752 | 5,803,448 | 57,580,840 |
| sstable | C2 | 11,112 | 11,432 | 11,432 |

| Prediction (B2f) | Result | Evidence |
|---|---|---|
| Instrument known-answer (8 MiB `byte[]`) | 8,388,624 B, ok | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/proof.txt` |
| U1 branch proof | **held**: 84 proof lines, F1 and F2 give `isColumnRange()` false and `ClusteringIndexNamesFilter`, T1, T2, T3 give true and `ClusteringIndexSliceFilter`, every F/T call returned the one row 5/7, C1 N rows, C2 10 rows; Byteman: 60 F/T cells, each only the expected return value, at least 10 returns per cell (2,292 true, 1,009 false in the whole run) | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/proof.txt`, `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out`, `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/trace-counts.txt` |
| U2 arms within 20 percent of F1 | **held**: largest difference 8.2 percent (memtable, N = 1,000, T1: 5,048 against 5,496); T arms are 320 to 448 B below F1, F2 equals F1 | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out` |
| U3 N = 100,000 over N = 1,000 within [0.5, 2] | **missed**: memtable arms 0.96 and 0.95; sstable arms 2.07 (F1, F2), 2.12 (T1, T2), 2.11 (T3). Every F and T arm grows alike in the sstable state (partition-level structures of a 100,000-row sstable partition are read) | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out` |
| U4 controls | **held**: C1 grows 78 times (memtable) and 100 times (sstable) with N and is 4,050 and 3,974 times F1 at N = 100,000; C2 (LIMIT 10) is 0.03 percent of C1 and flat (ratio 0.92 and 1.03) | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out` |
| U5 noise: passes within 5 percent, repeat spread within 10 percent | **missed in two cells, both controls at the smallest size**: memtable N = 1,000 C1 passes 291,504 and 251,504 (14.7 percent), C2 7,384 and 6,984 (5.6 percent). Repeat spread: largest 9.8 percent (held). Every F and T cell: pass-to-pass at most 2.9 percent | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/noise-detail.txt`, `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out` |
| D(N) = arm minus F1 grows with N | no: D is constant (T arms about -420 B, F2 0 to +72 B) in both states | `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out` |

**Cluster tier:** `n/a: operand has no size (kind 2)`; the reason is in B3 (the guarded quantity is a few kB of allocation, far below heap noise of about +-16 MiB).

### 4.2 Conclusion and logic

1. **Validity.** The check ran on the production path and chose the side each arm intends: the filter class built by `SelectStatement.makeClusteringIndexFilter` was a names filter for F1, F2 and a slice filter for T1, T2, T3 in all 84 proof lines **[observed: `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/proof.txt`]**, and the Byteman run saw only the expected `isColumnRange` return per cell **[observed: `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/trace-counts.txt`, `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out`]**. All arms returned the same row **[observed: proof lines]**. The instrument passed its known-answer **[observed]**. The run is valid; one prediction (U5) was missed.
2. **Readings.** In the sstable state every F/T arm grows about 2.1 times from 1,000 to 100,000 rows (U3), the same for both sides. C1 is the only reading that varies by more than 5 percent between passes (and only at N = 1,000, where it is 0.27 MB against 21 MB at N = 100,000). The slice arms allocate a constant 320 to 448 bytes less than the names arms.
3. **Matched row.** B2g: "U5 fails (noise above 5 percent) → **Not confirmed**: the effect is not resolved; Effect `undetermined`". The row "U1, U2, U4, U5 hold; U3 fails with every arm growing alike → Confirmed / does not cap" is the row the readings would match if U5 had held.
4. **Excluded rows.** "Refuted / caps" is excluded: no arm differs from F1 by more than 20 percent in either state, and D(N) does not grow with N **[observed: `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/analyze.out`]**. "Constant offset above 20 percent": excluded (largest 8.2 percent). "Invalid": excluded (branch proof held, both controls moved).
5. **Observed vs inferred.** Inferred: that the per-call allocation of one read is the quantity a cap on this predicate would change (a branch that bounded or released memory would show as growth of D(N); none appears). That the two noisy cells are JIT effects: they are control cells at the smallest size, their repeats in one pass are stable (spread 0), and 30 warm-ups did not remove the pass-to-pass difference **[inferred: not tested further; run1a with 3 warm-ups showed the same cell family]**.
6. **Deviations and gaps.** Two defects (section 3), the second restarting the tier. The filed attempt is the second complete attempt; the first (`run1a`) missed U3 and U5 too (U5: C1 13.7 percent at N = 10,000, spread 19 percent), and held U1, U2, U4. Allocation is not live heap. The cluster tier is `n/a`. The unit yaml's read-size guardrails were turned off for the controls (defect 1), so the controls are not run under the test yaml.
7. **Core question.** Usage here is the allocation of one read. The predicate chose the filter class, and the allocation of the two filter classes differs by a constant 320 to 448 bytes (4 to 8 percent), not growing with the data (1,000 to 100,000 rows), while a real row bound (LIMIT 10) and the data size (C1) move allocation by orders of magnitude under the same instrument **[observed]**. On the readings the predicate does not cap; the verdict is held at Not confirmed only because the pre-registered noise criterion was missed in two control cells.

**Conclusion (one line):** B2g row "U5 fails" — **Not confirmed** (U1, U2, U4 held; U3 missed equally for all arms); Effect `undetermined`.

## 5. Self-check of run 1 — AI

Independent script `harness/.../selfcheck.py` (plain line parsing, no `csv` module, does not import `analyze.py`; `no_constraint-iscolumnrange-clustering_restrictions--autonomous/run1/selfcheck.out`): 7 hold, 2 fail, and the two failures are the two predictions the analyser also reports as missed (the N-ratio and the noise floor). Everything else was recomputed from `raw.csv`, `proof.txt` and the Byteman trace.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | 60 F/T proof lines re-derived from the arm names (names filter for F, slice filter for T); Byteman cells re-counted independently: F cells only false, T cells only true |
| 2. Readings | yes | 42 cells, 7 timed values in each of 2 passes; row counts 1 / N / 10 in every timed call |
| 3. Matched row | yes | the recomputed largest arm-vs-F1 difference is 0.0815; the N-ratio of 2.07 to 2.12 is real, so U3 stays missed; noise 0.147 pass-to-pass, spread 0.098, so U5 stays missed and the row "U5 fails" applies |
| 4. Excluded rows | yes | no arm above 20 percent; D(N) constant |
| 5. Observed vs inferred | yes | the JIT explanation of the noisy cells is inferred and stated as such |
| 6. Deviations and gaps | yes | listed in 4.2 item 6 |
| 7. Core question | yes | steps follow B2e; the verdict follows the frozen row, not the reading's plain sense |

### 5.2 Run 2?

**No** (2026-10-29). A run 2 under the same frozen criteria would meet the same JIT variance at N = 1,000; changing the noise criterion after a reading is not allowed. The recommendation for stage 3 and the orchestrator is in section 8.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2). Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **undetermined** (the unit tier is Not confirmed).

**Claim tested** (B1): `isColumnRange()` does not cap memory or disk usage: its result depends only on restriction shape, and the bytes read or held by the query are independent of the predicate's value. "Confirmed" means this claim held. Unit-tier measurement of per-call allocation only; kind 2 operand; cluster tier `n/a`.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** ("U5 fails": two control cells above the 5 percent noise criterion) | `undetermined` | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: operand has no size (kind 2)`; allocation of one read is below the +-16 MiB heap noise of a node | n/a | B3 | 2026-10-29 |

**Positive control:** moved. C1 (whole partition) and C2 (LIMIT 10) under the same instrument: C2 is 0.03 percent of C1 at N = 100,000 and C1 grows 78 and 100 times with N, so "flat" arms are not an instrument that cannot see change.

**Reading if the noise row is set aside (not the verdict; for whoever overrules).** B2g's row "U1, U2, U4, U5 hold; U3 fails with every arm growing alike → Confirmed, `does not cap`" is the row the readings match apart from U5, which would make the outcome class **true negative**. The two cells that missed U5 are controls at N = 1,000; every F and T cell was within 2.9 percent pass to pass. This is stated for transparency; the verdict stays Not confirmed because the frozen table says so and the criterion is not edited after a reading. **Recommendation:** a small-cell absolute floor (for example 1 KiB or 5 percent, whichever is larger) is a reasonable stage-3 change to `none-type-design.md` section 3 step 6, for later cases.

**Feedback filed:** section D of the case file (dated 2026-10-29), B2/B3 amendments in the case file (audit, defects 1 and 2). `_INDEX.md` and `writeup-set-A.csv` left to the orchestrator.

**Leftovers:** none running (`ps` shows no `java` of this run on `pc32` after the chain). On disk outside the repo: `~/s4-none/` (tree, `run1`, `run1a-attempt3`, `attempt1-aborted`, `probe`), `~/s4-none-logs/`.

## Time spent

Wall-clock, this agent session on 2026-10-29 (UTC): reading protocol and the three case files and drafts, source audit, node build and reachability probe 03:55 to 04:09; amendments and freeze 04:09 to 04:15; harness, shakedown and defect fixes 04:15 to 04:25 (three aborted or superseded attempts); the filed attempt 04:25 to 04:30; analysis, self-check and filing about 25 minutes more. Not itemised per step.
