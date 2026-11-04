# no_constraint-isempty-size--autonomous — stage-4 results  <!-- file: results/no_constraint-isempty-size--autonomous.md -->

> **Case:** [`no_constraint-isempty-size--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-isempty-size--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap), one numeric bound missed (B(0)); cluster `n/a`; no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D). `none` type, operand kind 1 (count of held data) ([`none-type-design.md`](../none-type-design.md)); unit-tier measurement only.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendment (dated 2026-10-29, B2/B3 replaced), **frozen before any sweep reading: `bf9c54c4cab4165d88b7ea46dcc5c676efb394ceb57f3758362a35e1a374becc`**. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D; section D is filled after the verdict and its sha256 is recorded in section 8. |
| **Harness** | [`harness/no_constraint-isempty-size--autonomous/`](../harness/no_constraint-isempty-size--autonomous/README.md), uncommitted: `ResultSetIsEmptyTest.java`, `Alloc.java` (copied from the `batch_size_fail_threshold` harness), `rules-alloc.btm`, `rules-count.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`. |
| **Tiers and values** | Unit (B2): N = 0, 1, 1,000, 20,000 rows in one partition, arms A (`SELECT count(*)`) and B (plain `SELECT v`), two noise blocks of arm A at N = 0, 3 warm-up + 7 repeats each; Alloc mode and count mode. Cluster (B3): `n/a` (reason in B3 and section 8). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the `rows` list of a result set (heap); the check bounds none. |
| A. Core question | knob varied, >= 3 values incl. default, or another approach | Not met -> Met | filed B2 was `n/a`; amended to the row-count sweep 0 / 1 / 1,000 / 20,000 in two arms. |
| A. Core question | real resource measured, not only the counter | Met | thread allocation of `ResultSetBuilder.build()` and of the whole query. |
| A. Core question | usage driven past the branch point | Met (adapted) | N = 0 is the only true-side value; N = 1 the adjacent false-side value. |
| A. Core question | positive control for a negative claim | Met | whole-query allocation of the plain select grows with N (B2f (d)). |
| B. Logic | prediction in numbers | Not met -> Met | (a)-(e) in B2f. |
| B. Logic | every plausible outcome has a row | Not met -> Met | B2g. |
| B. Logic | direct evidence the branch executed | Met | count mode: every `isEmpty()` return value per query. |
| C. Specific | AI can run it | Met after amendment | tables, queries, repeats, modes exact. |
| D. Runnable | prerequisites; citations | Met | citations re-read, all correct; one design correction (see the amendment): `build()` alone does not scale with rows, so the draft's "growth equals rows added" for `build()` is replaced by the whole-query control. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Fill B2 with the two-arm row sweep; B3 `n/a: below heap noise` (amendment 2026-10-29) | Applied | filed `n/a: no constraint`. |
| R2 | Expected result is what the source already says; low value | recorded | the case was run only because the CQLTester harness was cheap. |

**Pre-run checks (instrument only, before the freeze, no sweep reading):** `javac` of the test against the build; `TestScript` parse of the Byteman rules (`rules-alloc.btm` 2 rules, `rules-count.btm` 1 rule, no errors); bring-up of the in-process CQLTester node under `JUnitCore`; the test's own instrument checks run in `checkonly` mode on the node: the known-answer window (8 MiB `byte[]` read as 8,388,624 bytes, expected 8,388,608 to 8,454,144) and the empty window (0 bytes). No point of the sweep was run before the freeze.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 |
| Node | `pc39` = `node1.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/s4-none` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL in 1 min 9 s |
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `no_constraint-isempty-size--autonomous/run1/harness.md5` |
| Storage for node data | none (no daemon); JUnit scratch under `~/stage4-logs/none/` on local `/dev/sda3` |
| Full logs (outside the repo) | `pc39:~/stage4-logs/none/no_constraint-isempty-size--autonomous/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | run 1 attempt 1 | B2d, attribution | the trace lines written after the last `mark` (teardown of the in-process node also runs `build()`) were attributed to the last query: 13 `build()` and 13 `isEmpty()` lines for one query, so (a) and the noise floor (e) failed as an artifact | the test writes a closing `mark block=end`, `analyze.py` ignores lines after it; the unit tier restarted from its beginning (attempt 1 kept on the node as `run1-attempt1-no-end-mark`) | 2026-10-29, predictions and table unchanged |

## 4. Run 1

**Scope:** the whole amended B2 (attempt 2, after D1); B3 `n/a`. **Command log:** `no_constraint-isempty-size--autonomous/run1/` (`session-alloc.log`, `session-count.log`, `analysis.txt`, `selfcheck.txt`, `raw-alloc/raw.csv`, trace heads in `junit-stage4-lines-and-trace-heads.txt`).

### 4.1 Readings

**Unit tier** (`build()` bytes are `stage4.Alloc` between ENTRY and EXIT of `ResultSetBuilder.build()`, median of 7, all ranges 0)

| Test or assertion | Result | Evidence |
|---|---|---|
| Instrument known-answer | 8,388,624 bytes (expected 8,388,608 to 8,454,144) | `junit-stage4-lines-and-trace-heads.txt` |
| `isEmpty()` per query (count mode) | exactly one per query, 100 queries; true if and only if N = 0 | `analysis.txt` (a), `selfcheck.txt` |
| Result rows | arm A: 1 at every N; arm B: 0, 1, 1,000, 20,000 | `analysis.txt` (b) |
| `build()` allocation, arm A at N = 0 / 1 / 1,000 / 20,000 | 1,384 / 1,448 / 1,472 / 1,440 bytes | `analysis.txt` |
| `build()` allocation, arm B at N = 0 / 1 / 1,000 / 20,000 | 1,176 / 1,280 / 1,248 / 1,248 bytes | same |
| A(0) minus B(0); A(0) minus A(1) | +208 bytes (frozen 100 to 1,000); -64 bytes (frozen within 512) | same |
| Flat for N >= 1 | arm A range 32 bytes, arm B range 32 bytes (frozen within 512) | same |
| B(0) | **1,176 bytes; the frozen bound was at most 512: missed** (see 4.2 part 2) | same |
| Noise floor (A at N = 0, two blocks) | 0 (1,384 / 1,384, ranges 0) | same |
| Whole-query allocation (control) | B: 7,584 / 8,744 / 295,520 / 5,701,792 bytes; A: 8,056 / 9,272 / 161,264 / 1,449,256; B(20,000)/B(1,000) = 19.29 (frozen 10 to 25) | same |

**Cluster tier:** `n/a: below heap noise` (B3).

### 4.2 Conclusion and logic

1. **Validity** — valid. `isEmpty()` ran once per query and returned true exactly for the empty partition [observed: count mode], both arms returned the predicted row counts [observed], the instrument read its known answer, the control moved 19 x [observed].
2. **Readings** — one frozen numeric bound missed: B(0) = 1,176 bytes against at most 512. Arm B at N = 0 adds nothing in `build()`, so those bytes are the window's own overhead (the `Alloc` map, the Byteman rule and `$!.size()`) [inferred: the same 1.2 to 1.5 KB is present at every N and in both arms]. The whole-query reading of arm A at N = 20,000 differed between attempt 1 (1,071,368) and attempt 2 (1,449,256) while every `build()` reading was identical, so whole-query allocation is noisier than the window (its noise floor was not measured); it is used only as a control with a ten-fold-wide band.
3. **Matched row** — B2g row "numeric ranges of (c)/(e) missed while the relations hold -> Confirmed, with the miss recorded": (a), (b), (d), (e) hold and (c) holds except the B(0) bound; the true branch accounts for +208 bytes (A(0) over B(0)) and the same single row costs A(0) 1,384 vs A(1) 1,448 bytes on the non-empty path, a difference of -64 bytes.
4. **Excluded rows** — "build() lower at N >= 1 than at N = 0 by dropped rows" (Refuted): no, `build()` is higher by 56 to 104 bytes at N >= 1 [observed]; "A(0) minus B(0) below the noise floor": no, floor 0 [observed]; "invalid": no.
5. **Observed vs. inferred** — the overhead explanation in part 2 is inferred; it does not enter the verdict.
6. **Deviations and gaps** — A(0) over B(0) compares two different queries (aggregate vs plain), so +208 bytes is an upper estimate of the branch's own cost; the cleaner pair is A(0) vs A(1) (-64 bytes); unit tier only, one in-process node; whole-query noise not characterized. Low-value case by the design's own note: the source already says the true branch only adds one row.
7. **Core question** — `isEmpty()` only decides whether one output row is added for an empty aggregate; `build()` allocates the same (within 104 bytes) with 0, 1, 1,000 or 20,000 rows, and the data's growth shows only in the whole query. The check removes or bounds nothing.

**Conclusion (one line):** B2g "numeric ranges missed while the relations hold" — Confirmed, with the B(0) bound missed: the check does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29 by `harness/no_constraint-isempty-size--autonomous/selfcheck.py` (regex parsing of the traces, no use of `analyze.py`): `selfcheck.txt` "ALL PASS" (9 checks) plus NOTEs on the medians and on B(0).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | 100 attributed queries in each trace, one `bld` and one `empty` line per query, true iff N = 0. |
| 2. Readings | yes | each (arm, N) has 7 equal readings; B(0) = 1,176 recomputed. |
| 3. Matched row | yes | |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | |
| 6. Deviations and gaps | yes | |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29): exact, repeatable `build()` readings; the case is low value by design.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** `ResultSet.isEmpty()` does not cap memory or disk usage: it returns `rows.size() == 0` and no resource usage is bounded by it.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed, with the B(0) numeric bound missed (amended B2g, "numeric ranges missed while the relations hold") | does not cap | run 1 (attempt 2) + self-check | 2026-10-29 |
| Cluster | not run: `n/a: below heap noise` | not run | | 2026-10-29 |

**Positive control:** the whole-query allocation of the plain select grew 19.3 x from 1,000 to 20,000 rows on the same thread-allocation instrument [observed]; the check's true branch is the only thing varied at N = 0 vs N >= 1 in `build()`.

**Noise floor:** 0 bytes for `build()` (two blocks, range 0); whole-query noise not measured.

**Feedback filed:** section D of the case file updated 2026-10-29 (no commit by this session); final sha256 of the case file with section D filled: `f4bf46cdaf0f6e49077e574c1bff8f02499a6d59dd21c578dedbab83f2a370fd`.
