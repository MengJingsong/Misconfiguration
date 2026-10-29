# no_constraint-doesaggregation-aggregatefactories--autonomous — stage-4 results  <!-- file: results/no_constraint-doesaggregation-aggregatefactories--autonomous.md -->

> **Case:** [`no_constraint-doesaggregation-aggregatefactories--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-doesaggregation-aggregatefactories--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29. Unit tier filed: Not confirmed (frozen noise criterion V5 missed in three N = 1,000 cells; V1 to V4 held, the retained result is N rows against 1 row). Cluster tier `n/a`. No run 2.**
>
> **Outcome class:** **undetermined** (estimate `negative`; the tier is Not confirmed, so the effect is `undetermined`) — [definition](../README.md#outcome-class). What the readings show if the noise row were set aside is in section 8; it is not the verdict.
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit tier, as amended 2026-10-29); B3 is `n/a`; feedback is section D. One results file per case file; the shared Java class is not shared (one class per case).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `a254c929`; the case file is tracked but modified (uncommitted). **sha256 after the audit's amendments (B2/B3 and section D, dated 2026-10-29): `15447558442034a5e7a00325ee74dad0d4df579482fb8282d9d96b41fe583f0d`**, written to `~/s4-none-logs/freeze.sha` on `pc32` at 2026-10-29 04:14:41 UTC (supersedes the 04:09:41 UTC hash `9799096a07558432de3d262a0d38494f6df6f85d0151dd771938b39d5937b16a`, which was recorded before the shakedown found that the plain arm never evaluates the checked line; the amendment adding arm P2 was made before any allocation reading), before the run and before any allocation reading. |
| **Hash history** | Hash history (the first freeze to FREEZE5 were written before any allocation reading; FREEZE6 was written after the first complete attempt, see the next row; the file `freeze.sha` keeps every entry): first freeze 04:09:41 UTC `9799096a07558432de3d262a0d38494f6df6f85d0151dd771938b39d5937b16a`; FREEZE2 04:14:41 UTC `15447558442034a5e7a00325ee74dad0d4df579482fb8282d9d96b41fe583f0d` (after the shakedown defect described in the disclosures); FREEZE4 04:18:33 UTC `1196e2a439e70a5d88d9646ebca79e3195801675c621cf78c0edda6075dfa415` (runbook defect 1, section 3: the unit yaml's read-size guardrails aborted the first attempt of the first case at its control); FREEZE5 04:20:24 UTC `eef8cbf144b195e2f1e1bc9978e308a6ed2b4fba81778b7179c7fe7b3c6ff2a0` (defect 1 completed: a `QueryOptions` caches the thresholds, so the second attempt aborted the same way; the raw output of both aborted attempts was not read and was moved to `~/s4-none/attempt1-aborted/`). |
| **Second-attempt note** | FREEZE6 is the hash of the second complete attempt of the unit tier (the one filed as run 1). It was written after the first complete attempt (`run1a`, 04:21-04:23 UTC), whose analysis had read the readings; the amendments since FREEZE5 are runbook defects 2 (30 warm-up calls instead of 3) and 3 (retained size measured on a compact copy of the rows) and change no prediction or tolerance. FREEZE6 `51560ca94d4cab8497011a6f597ac4b19f42952e1410841c34280b0b29172ed0`. |
| **Harness** | `harness/no_constraint-doesaggregation-aggregatefactories--autonomous/`: `NoneDoesAggregationAllocTest.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; not committed. md5s at the start of the run: `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/harness.md5`. |
| **Tiers and values** | Unit only (B2 amended): N = 1,000 / 10,000 / 100,000, memtable; arms P (plain column), P2 (abs(v)), A1 (max), A2 (max, min); control C (LIMIT 100). Cluster: `n/a` (B3). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (git status clean for that folder). Operand kind: 2 (a count compared with 0 is a flag), whose branch gates result retention (the draft agreed). Re-read: `SelectorFactories.java:55-110, 150-165`, `Selection.java:455-495, 565-600`, `SelectStatement.java:520-545, 574-620, 1435-1455`, `ResultSetBuilder.java:40-175`, `AbstractFunctionSelector.java:136-146, 232-242`, `MultiElementFactory.java:58-68`, `AggregationQueryPager.java:40-140, 200-320, 395-470`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly → Met | No constraint (A1); the quantity is the retained result of one read (bytes), and thread allocation. |
| A | knob varied, >= 3 values, or other approach with reason | Partly → Met | No knob; B2 sweeps both sides (P, P2 / A1, A2) at three data sizes. |
| A | real resource measured, not only the counter (gap named) | Partly → Met | Deep size of `ResultSet.rows` (jamm) and thread-allocated bytes; allocation is not live heap (B2i). |
| A | usage driven to the limit and past it | n/a | No limit; the largest result is 100,000 rows. |
| A | positive control for a negative estimate | Not met → Met | Added: C (LIMIT 100) moves both quantities. |
| B | each step says what it establishes | Met | B2e. |
| B | prediction in numbers or a clear relation | Not met → Met | B2f V1-V5. |
| B | every outcome has a conclusions row | Not met → Met | B2g has four rows. |
| B | confirmation needs knob-follows and direct branch evidence | Met (adapted) | Direct branch evidence: `Selection.isAggregate()` per arm and the Byteman return counts of `doesAggregation`. |
| B | alternatives and controls | Met | B2h. |
| C | a human can follow it | Partly → Met | A2/A3 said nothing is held that the check bounds; corrected in section D (the branch decides one row against one per input row). |
| C | an AI can run it without re-deriving | Not met → Met | B2a-B2d. |
| C | exact values and commands | Not met → Met | B2b, B2c. |
| D | prerequisites exist | Met | JDK 11, Ant, built tree on `pc32`; jamm 0.4.0 and Byteman 4.0.20 in the build. |
| D | workload arithmetic reaches the limit | Met (n/a) | 100,000 int rows. |
| D | citations spot-checked | Partly → Met | Cited lines held; `aggregation_subpage_size_in_kb` does not exist in 5.0.9; the plain-selection arm never evaluates the checked line (found at the shakedown). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Apply the operand-sweep design as B2; keep B3 `n/a` with the heap-noise reason | Applied, 2026-10-29 | The filed B2 had no measurement. |
| 2 | Correct A2-A4: the branch gates result retention; `aggregation_subpage_size_in_kb` does not exist in 5.0.9 | Applied to section D; A-sections left for stage 3 | Stage 3 should re-read A2 and A4. |
| 3 | Add P2 (`abs(v)`) so that the false side of the line itself is evaluated | Applied, B2b/B2d/B2f, 2026-10-29 (before any allocation reading) | SimpleSelection.isAggregate() returns false without calling the line (Selection.java:460-463). |

**Disclosures.** (1) A pre-run shakedown (the unit test at N = 200 and 400, plain and Byteman mode) was run on `pc32` to check that the harness compiles, the arms return what B2b says, and the Byteman rules parse. It read `proof.txt` (branch proof, states) and the Byteman trace counts, never `raw.csv` (allocation); its output was deleted and is not used as a reading. It found one prediction defect, amended in the case file before any allocation reading (see recommendations above and the hash note in the table). (2) The numeric predictions were written in B2f before the harness existed and are not changed after any reading.

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
| 2 | first complete attempt `run1a`, all three cases | B2c warm-up | 3 warm-up calls leave the JIT unsettled: the noise criterion failed in the smallest cells and in the large-result controls (`no_constraint-doesaggregation-aggregatefactories--autonomous/run1/run1a/analyze.out`: pass-to-pass up to 30 percent, repeat spread up to 32 percent) | 30 warm-up calls per cell; every prediction and tolerance unchanged; the tier restarted from its beginning; `run1a` is kept in `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/run1a/` and disclosed here | decided 2026-10-29 04:25 UTC, after `run1a`'s analysis had been read | case-file B2a/B2c/B2e (dated); uncommitted |
| 3 | first complete attempt `run1a` | B2c retained-size instrument | `ObjectSizes.measureDeep(resultSet.rows)` read a constant 1,048,568 to 1,048,768 bytes in every arm including the one-row arms (a buffer in the rows is a view of a shared 1 MiB array); V2 and V4's retained sub-criteria could not be evaluated (`no_constraint-doesaggregation-aggregatefactories--autonomous/run1/run1a/analyze.out`) | retained size measured on a compact copy of the rows (every buffer copied to an exact-size heap buffer); the raw `measureDeep` is still written as column `retained_ref` | decided 2026-10-29 04:25 UTC with defect 2 | case-file B2c/B2f (dated); uncommitted |

No further defect occurred in the filed attempt.

## 4. Run 1

**Scope:** unit tier only (B3 is `n/a`), two JVM runs: plain (instrument) and Byteman (counts). One partition of N rows, N = 1,000 / 10,000 / 100,000, memtable; arms P (plain column), P2 (`abs(v)`), A1 (`max(v)`), A2 (`max(v), min(v)`), control C (P with LIMIT 100); per cell 30 warm-up calls and 7 timed calls, two passes. **Command log:** `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/session-plain.log`, `session-bm.log`; analysis `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out`; first complete attempt (3 warm-ups, raw `measureDeep`) in `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/run1a/`.

### 4.1 Readings

Medians of the 14 timed values per cell (`no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out`, `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/raw.csv`):

| Arm | Rows returned (N = 1,000 / 10,000 / 100,000) | Allocation per call, bytes | Retained result (compact copy), bytes |
|---|---|---|---|
| P | 1,000 / 10,000 / 100,000 | 251,504 / 2,173,360 / 21,285,344 | 124,040 / 1,240,040 / 12,400,040 |
| P2 (`abs`) | 1,000 / 10,000 / 100,000 | 355,904 / 2,893,792 / 28,485,776 | 124,040 / 1,240,040 / 12,400,040 |
| A1 (`max`) | 1 / 1 / 1 | 189,440 / 1,525,320 / 15,205,320 | 168 / 168 / 168 |
| A2 (`max, min`) | 1 / 1 / 1 | 205,696 / 1,525,576 / 15,205,576 | 240 / 240 / 240 |
| C (P, LIMIT 100) | 100 / 100 / 100 | 29,184 / 25,896 / 25,896 | 12,440 / 12,440 / 12,440 |

| Prediction (B2f) | Result | Evidence |
|---|---|---|
| Known-answers (alloc 8 MiB; `measureDeep` of `byte[1000000]`) | 8,388,624 B and 1,000,016 B, ok | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/proof.txt` |
| V1 branch proof | **held**: P and P2 `isAggregate()` false with N rows; A1, A2 true with 1 row; A1 value N-1, A2 values N-1 and 0 (30 proof lines). Byteman: `doesAggregation` true for A1/A2 only (prepare and run), false for P2, not evaluated for P (`SimpleSelection`); `AggregationQueryPager.fetchPageInternal` entered at least 10 times per A1/A2 cell and never for P, P2, C | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/proof.txt`, `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/trace-counts.txt`, `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out` |
| V2 retained result | **held**: P and P2 are 124 B per row (12,400,040 B at N = 100,000, 100 times the N = 1,000 value); A1 168 B, A2 240 B at every N (flat) | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out` |
| V3 allocation follows N in every arm; A1, A2 at least 0.3 of P2 | **held**: ratios N = 100,000 over N = 1,000: P 85, P2 80, A1 80, A2 74; A1 and A2 allocate 0.53 of P2 at N = 10,000 and 100,000 | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out` |
| V4 control C | **held**: 100 rows, retained 12,440 B (0.1 percent of P), allocation 25,896 B (0.12 percent of P) and flat | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out` |
| V5 noise: allocation passes within 5 percent, repeats within 10 percent, retained passes within 1 percent | **missed in the allocation part**: three cells at N = 1,000 differ between passes by 15.6 (A2), 15.9 (P) and 18.0 (P2) percent; P's repeat spread 13.7 percent. All cells at N = 10,000 and 100,000 are within 5 percent. Retained sizes of the two passes are identical (0.000000) | `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/noise-detail.txt` |

**Cluster tier:** `n/a: operand has no size (kind 2)`; B3 gives the reason (the largest retained result, 12.4 MB, is of the same order as heap noise of a node).

### 4.2 Conclusion and logic

1. **Validity.** The flag took the side each arm intends and the results are right (30 proof lines; A1 = 99,999 at N = 100,000, A2 = 99,999 and 0) **[observed: `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/proof.txt`]**; the Byteman run saw `doesAggregation` true only for the aggregate arms and the internal aggregation pager only for them **[observed: `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/trace-counts.txt`, `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/analyze.out`]**. Both instruments passed their known-answers **[observed]**. The run is valid; V5 was missed.
2. **Readings.** The retained result is exact and identical between the passes (rows N against 1 row: the row count is not an estimate). Allocation per call follows N in all arms (about 80 times for 100 times the rows), and the aggregate arms allocate about half of what P2 does for the same scan (0.53), so aggregating shrinks the per-call work too, not only what is held. P (no processing) allocates less than P2 (processing).
3. **Matched row.** B2g: "V1, V4 hold; V5 fails → **Not confirmed**: the effect is not resolved; Effect `undetermined`". The readings would otherwise match the first row ("V1, V4, V5 hold and V2 holds → Refuted, `caps only on some paths (bypass)`").
4. **Excluded rows.** "Confirmed / does not cap" is excluded: the retained result differs by branch by a factor of 74,000 at N = 100,000 (12,400,040 against 168 B) and grows with N on one side only **[observed]**. "Invalid": excluded (V1 and V4 held).
5. **Observed vs inferred.** Inferred: that the retained rows are the memory a query holds (a streaming read holds less; this is the result a client-facing query materializes in `ResultSet.rows`). That the V5 misses are JIT effects at N = 1,000 **[inferred]**; the retained sizes do not depend on them.
6. **Deviations and gaps.** Three defects (section 3), the last two restarting the tier; the first complete attempt `run1a` is kept. Allocation is not live heap. The retained size is measured on a compact copy (defect 3), which excludes buffers shared with the memtable; the raw `measureDeep` is in column `retained_ref`. No cluster tier.
7. **Core question.** The check itself is a flag. The branch it feeds decides whether the result of a read is held as one row per input row or folded into one row: 12.4 MB against 168 bytes for a 100,000-row partition, with the scan work done on both sides **[observed]**. There is no configured limit; the bound exists for aggregate queries only. The verdict is nevertheless held at Not confirmed because the noise criterion was missed in three cells at the smallest size.

**Conclusion (one line):** B2g row "V1, V4 hold; V5 fails" — **Not confirmed**; Effect `undetermined`.

## 5. Self-check of run 1 — AI

Independent script `harness/.../selfcheck.py` (plain parsing, no `csv` module, does not import `analyze.py`; `no_constraint-doesaggregation-aggregatefactories--autonomous/run1/selfcheck.out`): 8 hold, 1 fail; the failure is the noise floor, which the analyser also reports as missed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | 30 proof lines re-derived from the arm names (aggregate iff name starts with A, rows and values); Byteman counts re-derived per prepare and run mark |
| 2. Readings | yes | 15 cells, 7 timed values in each pass; row counts N, N, 1, 1, 100 |
| 3. Matched row | yes | V2, V3, V4 recomputed and hold; the noise recomputed to 0.180 pass-to-pass and 0.137 spread, so V5 stays missed and the row "V5 fails" applies |
| 4. Excluded rows | yes | retained P over A1 at N = 100,000 is 73,810 times |
| 5. Observed vs inferred | yes | stated |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | steps follow B2e; the verdict follows the frozen row |

### 5.2 Run 2?

**No** (2026-10-29), for the reason given in the first case's results file: the same frozen criteria would meet the same JIT variance at N = 1,000, and editing them after a reading is not allowed.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2). Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **undetermined** (the unit tier is Not confirmed).

**Claim tested** (B1): `doesAggregation()` does not cap memory or disk usage: its result depends only on the shape of the select clause, not on any size limit. "Confirmed" means this claim held. Unit-tier measurement of per-call allocation and retained result size; kind 2 operand; cluster tier `n/a`.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** ("V1, V4 hold; V5 fails": three N = 1,000 cells above the 5 percent noise criterion) | `undetermined` | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: operand has no size (kind 2)`; the largest retained result (12.4 MB) is the order of heap noise | n/a | B3 | 2026-10-29 |

**Positive control:** moved. C (LIMIT 100) drops the retained result from 12,400,040 B to 12,440 B and the allocation from 21,285,344 B to 25,896 B at N = 100,000, flat in N, under the same instruments.

**Reading if the noise row is set aside (not the verdict; for whoever overrules).** The readings match B2g's first row: **Refuted**, Effect `caps only on some paths (bypass)` (the result of an aggregate query is one row, a plain query holds one per input row; no configured limit), which would make the outcome class **false negative** (`negative`, `caps`). The retained sizes carry no noise (identical between passes), and the three noisy cells are allocation readings at N = 1,000. Stated for transparency; the verdict stays Not confirmed because the frozen table says so. **For the index:** if overruled to Refuted, the estimate stays `negative` (README) and the note should say "gate by query shape (result folded to one row), not a configured limit".

**Feedback filed:** section D of the case file (dated 2026-10-29); the B2 amendment, defects 1 to 3. Stage 3 should re-read A2 to A4 (corrections in section D). `_INDEX.md` and `writeup-set-A.csv` left to the orchestrator.

**Leftovers:** none running. On disk outside the repo: `~/s4-none/`, `~/s4-none-logs/`.

## Time spent

Wall-clock, this agent session on 2026-10-29 (UTC): reading protocol and the three case files and drafts, source audit, node build and reachability probe 03:55 to 04:09; amendments and freeze 04:09 to 04:15; harness, shakedown and defect fixes 04:15 to 04:25 (three aborted or superseded attempts); the filed attempt 04:25 to 04:30; analysis, self-check and filing about 25 minutes more. Not itemised per step.
