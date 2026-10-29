# no_constraint-needfiltering-restriction_count--autonomous — stage-4 results  <!-- file: results/no_constraint-needfiltering-restriction_count--autonomous.md -->

> **Case:** [`no_constraint-needfiltering-restriction_count--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-needfiltering-restriction_count--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29. Unit tier filed: Not confirmed (frozen noise criterion W5 missed on one repeat spread; W1 to W4 held: the rejected query costs 13 kB at every N, the same query with ALLOW FILTERING scans and allocates 0.4 / 3.9 / 39.2 MB). Cluster tier `n/a`. No run 2.**
>
> **Outcome class:** **undetermined** (estimate `negative`; the tier is Not confirmed, so the effect is `undetermined`) — [definition](../README.md#outcome-class). What the readings show if the noise row were set aside is in section 8; it is not the verdict.
>
> **Agent:** autonomous. "§9a" means B2f/B2g (unit tier, as amended 2026-10-29); B3 is `n/a`; feedback is section D. One results file per case file; the shared Java class is not shared (one class per case).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `a254c929`; the case file is tracked but modified (uncommitted). **sha256 after the audit's amendments (B2/B3 and section D, dated 2026-10-29): `e431891847d22056b4d3ad05b4f4c9b3898b4f7648e2e885aab52bed853b7f2f`**, written to `~/s4-none-logs/freeze.sha` on `pc32` at 2026-10-29 04:14:41 UTC (supersedes the 04:09:41 UTC hash `7655036575255bf49c29cc9478699f1cfa226139777095deb668d9627e3da441`, recorded before the shakedown showed that the ALLOW FILTERING arm does not evaluate `needFiltering`; W1 was corrected before any allocation reading), before the run and before any allocation reading. |
| **Hash history** | Hash history (the first freeze to FREEZE5 were written before any allocation reading; FREEZE6 was written after the first complete attempt, see the next row; the file `freeze.sha` keeps every entry): first freeze 04:09:41 UTC `7655036575255bf49c29cc9478699f1cfa226139777095deb668d9627e3da441`; FREEZE2 04:14:41 UTC `e431891847d22056b4d3ad05b4f4c9b3898b4f7648e2e885aab52bed853b7f2f` (after the shakedown defect described in the disclosures); FREEZE4 04:18:33 UTC `a244a2a6b58e400d8ff6b2e54d0b7c62b35dc9b8d18e40f4e1a21e8f4f7d7e84` (runbook defect 1, section 3: the unit yaml's read-size guardrails aborted the first attempt of the first case at its control); FREEZE5 04:20:24 UTC `9c591601a2ed31b1ead1a1d5bef17e8952f62aff7d12f23f41a37a140ba2e536` (defect 1 completed: a `QueryOptions` caches the thresholds, so the second attempt aborted the same way; the raw output of both aborted attempts was not read and was moved to `~/s4-none/attempt1-aborted/`). |
| **Second-attempt note** | FREEZE6 is the hash of the second complete attempt of the unit tier (the one filed as run 1). It was written after the first complete attempt (`run1a`, 04:21-04:23 UTC), whose analysis had read the readings; the amendments since FREEZE5 are runbook defects 2 (30 warm-up calls instead of 3) and change no prediction or tolerance. FREEZE6 `b44a2b14add876cbb88831c399c6431f9b6d9b1cb6c4560502eedc72e388ea6c`. |
| **Harness** | `harness/no_constraint-needfiltering-restriction_count--autonomous/`: `NoneNeedFilteringAllocTest.java, NeedFilteringProbeTest.java, probe-run.sh`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; not committed. md5s at the start of the run: `no_constraint-needfiltering-restriction_count--autonomous/run1/harness.md5`. |
| **Tiers and values** | Unit only (B2 amended): N = 1,000 / 10,000 / 100,000 partitions, memtable; arms R (rejected), F (ALLOW FILTERING; windows Fp, Fx), controls C1 (all rows), C2 (LIMIT 10). Cluster: `n/a` (B3). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (git status clean for that folder). Operand kind: 2 (a count compared with 0, with another predicate); the draft agreed that it is not kind 1; the outcome gates a scan (`SelectStatement.java:1610`). Re-read: `StatementRestrictions.java:236-365, 590-720, 955-1000`, `SelectStatement.java:574-620, 975-995, 1595-1615`, `IndexRestrictions.java:70-110`, `ClusteringColumnRestrictions.java:180-205`, `TokenFilter.java:318-324`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Partly → Met | No constraint (A1); the quantity is the allocation of one query, and it is said that this is allocation volume, not live heap (B2i). |
| A | knob varied, >= 3 values, or other approach with reason | Partly → Met | No knob; B2 sweeps the data size under two arms (rejected, ALLOW FILTERING) at three sizes. |
| A | real resource measured, not only the counter (gap named) | Partly → Met | Thread-allocated bytes of prepare and execute; the gap (allocation versus live heap) is named. |
| A | usage driven to the limit and past it | n/a | No limit; 100,000 partitions are scanned in the largest arm. |
| A | positive control for a negative estimate | Not met → Met | Added: C2 (LIMIT 10) against C1 (all rows). |
| B | each step says what it establishes | Met | B2e. |
| B | prediction in numbers or a clear relation | Not met → Met | B2f W1-W5. |
| B | every outcome has a conclusions row | Not met → Met | B2g has five rows. |
| B | confirmation needs knob-follows and direct branch evidence | Met (adapted) | Direct evidence: the rejection text, the restriction flags (line 985 false), the Byteman line-992 count. |
| B | alternatives and controls | Met | B2h: Fp against R separates parse and prepare from the gate. |
| C | a human can follow it | Partly → Met | A2/A3 said nothing is allocated differently; corrected in section D (the helper decides a prepare-time rejection). |
| C | an AI can run it without re-deriving | Not met → Met | B2a-B2d. |
| C | exact values and commands | Not met → Met | B2b, B2c. |
| D | prerequisites exist | Met | JDK 11, Ant, built tree on `pc32`. |
| D | workload arithmetic reaches the limit | Met (n/a) | 100,000 partitions of 100 B. |
| D | citations spot-checked | Met | All held; the probe checked reachability. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Run the reachability probe before designing arms | Applied, probe run 2026-10-29 before the freeze (output `no_constraint-needfiltering-restriction_count--autonomous/run1/probe.txt`) | The gating question: 16 queries, line 992 decides a rejection for key-range queries restricted on clustering columns without a partition key. |
| 2 | Apply the operand-sweep design (arms R and F) as B2; keep B3 `n/a` with the heap-noise reason | Applied, 2026-10-29 |  |
| 3 | Correct W1: the ALLOW FILTERING arm never evaluates the helper (found at the shakedown; amended before any allocation reading) | Applied, 2026-10-29 |  |

**Disclosures.** (1) A pre-run shakedown (the unit test at N = 200 and 400, plain and Byteman mode) was run on `pc32` to check that the harness compiles, the arms return what B2b says, and the Byteman rules parse. It read `proof.txt` (branch proof, states) and the Byteman trace counts, never `raw.csv` (allocation); its output was deleted and is not used as a reading. It found one prediction defect, amended in the case file before any allocation reading (see recommendations above and the hash note in the table). (2) The numeric predictions were written in B2f before the harness existed and are not changed after any reading. (3) The reachability probe (`NeedFilteringProbeTest`) read restriction flags and exception text for 16 queries, no allocation; it is the gate the orchestrator asked for, run before the freeze, output in `{stem}--autonomous/run1/probe.txt`.

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
| 2 | first complete attempt `run1a`, all three cases | B2c warm-up | 3 warm-up calls leave the JIT unsettled: the noise criterion failed in the smallest cells and in the large-result controls (`no_constraint-needfiltering-restriction_count--autonomous/run1/run1a/analyze.out`: pass-to-pass up to 30 percent, repeat spread up to 32 percent) | 30 warm-up calls per cell; every prediction and tolerance unchanged; the tier restarted from its beginning; `run1a` is kept in `no_constraint-needfiltering-restriction_count--autonomous/run1/run1a/` and disclosed here | decided 2026-10-29 04:25 UTC, after `run1a`'s analysis had been read | case-file B2a/B2c/B2e (dated); uncommitted |

No further defect occurred in the filed attempt.

## 4. Run 1

**Scope:** unit tier only (B3 is `n/a`), two JVM runs: plain (instrument) and Byteman (counts). N partitions, N = 1,000 / 10,000 / 100,000, memtable; arm R (query rejected at prepare), arm F (ALLOW FILTERING: window Fp prepare, window Fx execute), controls C1 (all rows), C2 (LIMIT 10); per cell 30 warm-up repetitions and 7 timed, two passes. **Reachability probe** (before the freeze): `no_constraint-needfiltering-restriction_count--autonomous/run1/probe.txt`. **Command log:** `no_constraint-needfiltering-restriction_count--autonomous/run1/session-plain.log`, `session-bm.log`; analysis `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out`; first complete attempt (3 warm-ups) in `no_constraint-needfiltering-restriction_count--autonomous/run1/run1a/`.

### 4.1 Readings

Medians of the 14 timed values per cell (`no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out`, `no_constraint-needfiltering-restriction_count--autonomous/run1/raw.csv`), bytes allocated by the calling thread:

| Window | N = 1,000 | N = 10,000 | N = 100,000 |
|---|---|---|---|
| R: `getStatement(Q)`, throws | 13,480 | 13,384 | 13,384 |
| Fp: `getStatement(Q ALLOW FILTERING)` | 12,808 | 12,688 | 12,688 |
| Fx: `executeLocally` of F (1 row returned) | 398,144 | 3,925,912 | 39,205,864 |
| C1: whole table (N rows) | 980,176 | 9,933,968 | 98,885,952 |
| C2: LIMIT 10 | 14,688 | 14,896 | 14,896 |

| Prediction (B2f) | Result | Evidence |
|---|---|---|
| Known-answer (8 MiB `byte[]`) | 8,388,624 B, ok | `no_constraint-needfiltering-restriction_count--autonomous/run1/proof.txt` |
| W1 branch proof | **held**: at every N and pass, R threw `InvalidRequestException` with "Cannot execute this query as it might involve data filtering ..."; F had `needFiltering` true, `keyRange` true, `usesIndex` false, `line985` false (so line 992 decided), one row `ck = 5`. Byteman: every R cell reached line 992 and returned true at least 10 times and never false; F cells evaluated the helper at most once (the test's own proof call) | `no_constraint-needfiltering-restriction_count--autonomous/run1/proof.txt`, `no_constraint-needfiltering-restriction_count--autonomous/run1/trace-counts.txt`, `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out` |
| W2 rejected arm flat | **held**: 13.4 kB at every N, ratio 0.993 | `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out` |
| W3 accepted arm follows the data | **held**: Fx 39.2 MB at N = 100,000 (at least 10 MB), 98 times Fx at N = 1,000, 2,929 times R at N = 100,000; Fp is flat (12.7 kB) | `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out` |
| W4 controls | **held**: C1 grows 101 times; C2 is 0.015 percent of C1 at N = 100,000 and flat (ratio 1.01) | `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out` |
| W5 noise: passes within 5 percent, repeat spread within 10 percent | pass-to-pass **held** (largest 2.7 percent); repeat spread **missed**: largest 11.7 percent, one Fx cell at N = 1,000 (an outlier among 7 repeats; its pass medians differ by 0.1 percent) | `no_constraint-needfiltering-restriction_count--autonomous/run1/noise-detail.txt`, `no_constraint-needfiltering-restriction_count--autonomous/run1/analyze.out` |

**Cluster tier:** `n/a: operand has no size (kind 2)`; B3 gives the reason.

### 4.2 Conclusion and logic

1. **Validity.** Line 992 decided the rejection: for Q (`SELECT ck, v FROM t WHERE ck = 5`) `needFiltering` is true with the line-985 test false, the statement is a key range without an index, and without ALLOW FILTERING it is rejected at prepare time with the filtering message; with ALLOW FILTERING it is accepted and returns one row **[observed: `no_constraint-needfiltering-restriction_count--autonomous/run1/proof.txt`]**. The Byteman run counted line 992 reached and `needFiltering` true in every R cell and none from the production path of F **[observed: `no_constraint-needfiltering-restriction_count--autonomous/run1/trace-counts.txt`]**. The instrument passed its known-answer **[observed]**. The run is valid; W5's repeat-spread part was missed.
2. **Readings.** The rejected query allocates a constant 13.4 kB (parse, prepare, exception). The same query with ALLOW FILTERING allocates 0.4 MB (1,000 partitions), 3.9 MB, 39.2 MB (100,000 partitions), about 392 B per partition scanned, to return one row. The ALLOW FILTERING arm never evaluates `needFiltering` on the production path (`checkNeedsFiltering` is skipped), so the contrast is the rejection that line 992 causes against the client's opt-in.
3. **Matched row.** B2g: "W5 fails → **Not confirmed**; Effect `undetermined`". The readings would otherwise match the first row ("W1 to W5 hold: Refuted, `caps only on some paths (bypass)`").
4. **Excluded rows.** "Confirmed / does not cap" is excluded: the gated scan allocates 2,929 times what the rejected query does and follows N **[observed]**. "Invalid": excluded (W1 and W4 held).
5. **Observed vs inferred.** Inferred: that allocation volume of the scan is a fair proxy for the cost the gate avoids; a streaming scan keeps little live (stated in B2i). That the repeat-spread miss is a JIT outlier at N = 1,000 **[inferred]**: the pass medians of that cell differ by 0.1 percent.
6. **Deviations and gaps.** Two defects (section 3), the second restarting the tier; the first complete attempt `run1a` is kept (W1 to W4 held there too, W5 missed with pass-to-pass up to 15.5 percent). Allocation is not live heap. No cluster tier. The effect is a soft, opt-out gate (ALLOW FILTERING), not a limit.
7. **Core question.** The outcome at line 992 (with the ALLOW FILTERING parameter) refuses a scan whose allocation grows with the data by about 392 bytes per partition, at a fixed cost of 13 kB per rejected statement **[observed]**. No configured limit is involved and the client can bypass it. The verdict is nevertheless held at Not confirmed because one repeat spread exceeded the pre-registered 10 percent.

**Conclusion (one line):** B2g row "W5 fails" — **Not confirmed** (W1 to W4 held); Effect `undetermined`.

## 5. Self-check of run 1 — AI

Independent script `harness/.../selfcheck.py` (plain parsing, no `csv` module, does not import `analyze.py`; `no_constraint-needfiltering-restriction_count--autonomous/run1/selfcheck.out`): 8 hold, 1 fail; the failure is the repeat spread, which the analyser also reports as missed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | 6 rejections and 6 accepted-with-line-992 proof lines re-counted by regex; Byteman: every R cell reaches line 992 and returns true at least 10 times; F cells at most once |
| 2. Readings | yes | 15 windows, 7 timed values in each pass; Fx 1 row, C1 N rows, C2 10 rows in every timed call |
| 3. Matched row | yes | W2 to W4 recomputed and hold; the recomputed repeat spread is 0.1175 (pass-to-pass 0.027), so W5 stays missed and the row "W5 fails" applies |
| 4. Excluded rows | yes | Fx over R at N = 100,000 recomputed |
| 5. Observed vs inferred | yes | stated |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | steps follow B2e; the verdict follows the frozen row |

### 5.2 Run 2?

**No** (2026-10-29), for the reason given in the first case's results file.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2). Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **undetermined** (the unit tier is Not confirmed).

**Claim tested** (B1): `needFiltering(TableMetadata)` does not cap memory or disk usage: its result is a function of the query's restriction structure only and is independent of any size limit. "Confirmed" means this claim held. Unit-tier measurement of allocation volume per call; kind 2 operand; cluster tier `n/a`.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** ("W5 fails": one repeat spread of 11.7 percent against 10 percent) | `undetermined` | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: operand has no size (kind 2)` | n/a | B3 | 2026-10-29 |

**Positive control:** moved. C2 (LIMIT 10) is 0.015 percent of C1 at N = 100,000 and flat; C1 grows 101 times with N, under the same instrument.

**Reading if the noise row is set aside (not the verdict; for whoever overrules).** W1 to W4 held, and the pass-to-pass part of W5 held (2.7 percent); the readings match B2g's first row: **Refuted**, Effect `caps only on some paths (bypass)` (a soft gate that ALLOW FILTERING bypasses; allocation volume, not live heap), which would make the outcome class **false negative**. The estimate would stay `negative` (README). Stated for transparency.

**Feedback filed:** section D of the case file (dated 2026-10-29): A2 and A3 say nothing is allocated differently; the probe shows `:1610` rejects the scan. `_INDEX.md` and `writeup-set-A.csv` left to the orchestrator.

**Leftovers:** none running. On disk outside the repo: `~/s4-none/`, `~/s4-none-logs/`.

## Time spent

Wall-clock, this agent session on 2026-10-29 (UTC): reading protocol and the three case files and drafts, source audit, node build and reachability probe 03:55 to 04:09; amendments and freeze 04:09 to 04:15; harness, shakedown and defect fixes 04:15 to 04:25 (three aborted or superseded attempts); the filed attempt 04:25 to 04:30; analysis, self-check and filing about 25 minutes more. Not itemised per step.
