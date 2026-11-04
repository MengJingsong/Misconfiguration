# no_constraint-resizeto-newcapacity--autonomous — stage-4 results  <!-- file: results/no_constraint-resizeto-newcapacity--autonomous.md -->

> **Case:** [`no_constraint-resizeto-newcapacity--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-resizeto-newcapacity--autonomous.md)
>
> **Status:** verdict filed (2026-10-29) — unit tier run 1 done and self-checked, cluster tier `n/a`, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class). Rests on one judgement written before the run (section 8, "Judgement").
>
> **Agent:** autonomous. "§9a" means B2f/B2g as amended (the B2 amendment of 2026-10-29, items e and g); "§9b-§9e" means B2a-B2e; feedback is section D. Design: [`none-type-design.md`](../none-type-design.md) (operand sweep), operand kind 3.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `a254c929`; the case file is uncommitted in the working tree. **sha256 after the audit's B2/B3 amendment (2026-10-29): `830b451be3e44238ac166fe95547a2b22b1f27cc85eceb13fe5517d2a618124a`**, written to `pc29:~/s4-none/logs/freeze.sha` (copy: `no_constraint-resizeto-newcapacity--autonomous/run1/freeze.sha`) at 2026-10-29 04:07:52 UTC, before the harness existed and before any reading. Section D was filled after the run; the sha256 of the file with D filled is `993ec0c50bf0c9029b0f97b6817d77e526d325b3d51bcc7f6b6d5c88ee83356f`. The frozen text is everything above section D. |
| **Harness** | `harness/no_constraint-resizeto-newcapacity--autonomous/`: `SafeMemoryResizeToTest.java`, `NativeLedger.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`; written after the freeze; uncommitted. md5s at run start: `run1/harness.md5`. **Pre-run shakedown (disclosed):** one JVM at C = 1024 with 1 repetition, written and read before the run to check that the rules fire and the test compiles; its output was seen (it matched the prediction) and deleted; no figure from it is used. |
| **Tiers and values** | Unit tier only: C in {1 KiB, 64 KiB, 1 MiB, 64 MiB, 512 MiB}, arms E / D / H / X, 5 repetitions after one discarded warm-up; control JVMs at C = 8 MiB with `DOB_DOUBLING_THRESHOLD_MB` default and 1. Cluster tier `n/a` (B3 amendment). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

Audited against `cassandra/cassandra-5.0.9/` (clean: `git status` printed nothing). Re-read: `SafeMemoryWriter.java` (all), `SafeMemory.java:55-100`, `Memory.java:55-80`, `DataOutputBuffer.java:40-52, 125-215`, `BufferedDataOutputStreamPlus.java:85-125`, `IndexSummaryBuilder.java:195-260`, `CassandraRelevantProperties.java:203`, `SafeMemoryWriterTest.java`. The draft in `none-type-drafts-kind3.md` §1 was read and corrected where noted.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | There is no constraint (A1); the quantity is the native bytes of one `SafeMemory`. Stated as a no-cap case, operand kind 3. |
| A. Core question | knob varied, ≥ 3 values, or another approach | Partly → Met | B2 as filed was `n/a`. The amendment varies the operand (C over five orders, both sides of the equality, plus the counterfactual X). |
| A. Core question | real resource measured, not only the counter | Partly → Met | `getThreadAllocatedBytes` cannot see the `Unsafe` malloc; the amendment adds a Byteman ledger on `Memory.<init>` line 65 and `MemoryTidy.tidy` (exact native bytes, peak, live), cross-checked with `capacity()`. |
| A. Core question | usage driven to the limit and past it | Partly | There is no limit; the sweep reaches 512 MiB, both sides of the equality. |
| A. Core question | positive control for a negative estimate | Partly | No setting caps the native bytes of a `SafeMemoryWriter`. The sibling `DOB_DOUBLING_THRESHOLD_MB` moves the same ledger by 4 MiB; stated as a growth knob, not a cap. |
| B. Logic | each step says what it establishes | Met | amendment items a-h |
| B. Logic | prediction stated in numbers | Not met → Met | B2 as filed had none; item e gives exact integers per arm and bounds for the residue. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met | item g (Confirmed / Refuted / Invalid / residue miss). |
| B. Logic | confirmation needs knob-follows and direct branch evidence | Met | The ledger shows the allocation count per arm (0 vs 1) and the copy count. |
| B. Logic | alternatives and controls | Partly → Met | Retained size vs transient is separated (peak vs live-after); the "gates an allocation" reading of design §4 row 2 is resolved in a stated judgement (item g). |
| C. Specific | human can follow | Met | A1-A3 and the amendment. |
| C. Specific | AI can run without re-deriving | Met after amendment | trigger class, package, rules, JVM flags given. |
| C. Specific | exact values and commands | Met after amendment | sweep, reps, heap, properties. |
| D. Runnable | prerequisites exist | Met | JDK 11, Ant, Byteman 4.0.20 in the build. |
| D. Runnable | arithmetic reaches the limit | Met | 512 MiB writer, 1 GiB transient; 125+ GiB RAM. |
| D. Runnable | citations spot-checked | Met | `SafeMemoryWriter.java:50-72, 89-92`; `Memory.java:62-65`; `SafeMemory.java:70-75`; `IndexSummaryBuilder.java:250-251`; all as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Fill B2 with the operand sweep, ledger, exact predictions and control | Applied, B2 amendment 2026-10-29 | design §3-§4 |
| 2 | Add arm X (what the true branch would do at the equal operand) | Applied | otherwise "equal" has no flipped counterpart |
| 3 | State the transient-vs-retained judgement before the run | Applied (item g) | design §4 row 2 read mechanically says `caps` |
| 4 | B3 stays `n/a` | Applied (B3 amendment) | equal branch needs an exactly full writer; transient is MiB scale in native memory |
| 5 | Record `AssertionError` for size 0 and the missing early return in `SafeMemoryWriter.expandToFit` | Applied (amendment text, section D) | accuracy of A3 |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 04:13 UTC (2026-10-28 22:13 MDT), 42 s for the whole unit tier |
| Node | `pc29` = `node3.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); other agents use other nodes |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none/cassandra` by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929`; `ant build-test` BUILD SUCCESSFUL in 1 min 8 s |
| Case-file commit / harness commit | uncommitted; sha256 in section 1 / uncommitted |
| Storage | no node data; all state is in the JVM and native memory |
| Full logs (outside the repo) | `pc29:~/s4-none/run1/no_constraint-resizeto-newcapacity--autonomous/` (per-JVM `junit.log`, `raw.csv`, `session.log`); excerpts in `run1/` |

## 3. Runbook defects

None. (`run-all.sh` was first written with an unquoted heredoc and did nothing; rewritten and rerun before any reading. Not a design defect.)

## 4. Run 1

**Scope:** unit tier, all values of the B2 amendment. **Command log:** `no_constraint-resizeto-newcapacity--autonomous/run1/session.log`; raw rows `run1/raw-all.csv`; judged by `run1/analyze.out`.

### 4.1 Readings

**Unit tier** (`run1/analyze.out`: 72 PASS, 6 FAIL; the 6 FAIL are all the on-heap residue of arm D, see part 2; `run1/selfcheck.out`: 351 hold, 0 fail)

| Test or assertion | Result | Evidence |
|---|---|---|
| Arm E (full writer, `trim()`), all five C | copies 0, allocations 0, allocated bytes 0, frees 0, peak = live after = capacity after = C; residue 0 B | `raw-all.csv` rows `sweep,<C>,E` |
| Arm D (C-1 bytes, `trim()`) | copies 1, allocations 1, allocated bytes C-1, freed C, **peak 2C-1**, live after = capacity after = C-1 (e.g. C = 512 MiB: 536,870,911 / 1,073,741,823); read-back bytes correct | rows `D` |
| Arm H (C/2 bytes) | allocated C/2, peak C + C/2, capacity after C/2 | rows `H` |
| Arm X (`copy(C)`: what the check skips) | allocated C, **peak 2C**, live after C, writer capacity C | rows `X` |
| Retained capacity E minus D | exactly 1 byte at every C, every repetition | `selfcheck.out` |
| Native figures over the five repetitions | identical (spread 0 bytes) | `analyze.out` noise-floor line |
| On-heap residue (thread-allocated) | E 0 B; H 3,976 B; X 3,912 B (after a warm-up rep of 18,584); D 3,976 B in repetitions 1, 3, 4 but 18,832 B (rep 2) and 17,432 B (rep 5) at every C | `raw-all.csv` column `heapBytes` |
| Control, default threshold | growth allocation 16,777,216 (2C), capacity after 16,777,216 | `raw-all.csv` rows `control` (default JVM) |
| Control, `DOB_DOUBLING_THRESHOLD_MB=1` | growth allocation 12,582,912 (1.5C); the two differ by exactly 4,194,304 | same |

### 4.2 Conclusion and logic

1. **Validity.** The check was reached and both branches observed: the ledger counted 0 copies for E and 1 copy for D, H and X at every C **[observed: `raw-all.csv`, `analyze.out`]**; the rules fired (D shows allocation count 1). The ledger's live-after equals `writer.capacity()` in all 20 counted rows per JVM **[observed: `selfcheck.out`]**. Hold-fixed settings: `-Xmx512m`, single thread, Byteman 4.0.20, one JVM per C **[observed: `session.log`]**. Valid.
2. **Readings.** One sub-prediction missed: the on-heap residue of arm D exceeded 16 KiB in two of five repetitions (18,832 B and 17,432 B) and the C-spread bound of 4 KiB fails because of them. The values are identical at every C, so the residue does not follow C **[observed]**; the cause (a JIT or first-use effect in the Byteman rule path) is **[inferred: same repetition indices at every C and a fresh JVM each, so not data-dependent]**. Per B2g's last row this does not change the verdict. All native-byte predictions held, exactly.
3. **Matched row.** B2g row 1: E allocates 0 bytes and makes 0 copies; X allocates C with peak 2C; D allocates C-1 with peak 2C-1; retained capacity is C (E, X) and C-1 (D); the control moved by 4 MiB; the ledger counted **[observed]**.
4. **Excluded rows.** Row 2 ("retained differs by more than 1 byte, or E allocates"): E allocated 0; retained E - D = 1 byte **[observed]**. Row 3 (control flat, rule did not fire, ledger disagrees with `capacity()`): control moved by exactly 4,194,304; D shows 1 allocation; ledger equals `capacity()` **[observed]**. Row 4 (residue miss with native figures holding) applies as a side note.
5. **Observed vs inferred.** Inferred: (a) the production caller (`IndexSummaryBuilder.prepareToCommit`) reaches the same `trim()` path (source reading, IndexSummaryBuilder.java:250-251; not run through the builder); (b) the cause of the residue outliers (part 2); (c) that "skipping a redundant same-size copy" is not a cap (the judgement of section 8).
6. **Deviations and gaps.** Unit tier only; no cluster run (B3 `n/a`). No setting caps the native bytes of a `SafeMemoryWriter`, so the positive control is a sibling growth knob that acts at `calculateNewSize`, not at line 52; it shows the instrument reads an allocation-size change of the right size, not a cap binding. The equal branch was driven through `trim()` on an exactly full writer, as in production; a `SafeMemoryWriter` never reaches the equal size by growth. Run 2 not done.
7. **Core question.** There is no limit at line 52: the compared values are the requested and the current size of one buffer. The size held after the call is the requested size on both branches (C for E and X, C-1 for D); usage follows the operand (expected: the operand is the size). The only thing the branch changes at equal operand is a redundant same-size copy (allocation C, transient peak 2C) that E avoids; it does not bound any retained size **[observed: parts 3-4; inferred: judgement]**.

**Conclusion (one line):** B2g row 1 — Confirmed (does not cap), with the residue sub-prediction missed.

## 5. Self-check of run 1 — AI

Independent script `harness/no_constraint-resizeto-newcapacity--autonomous/selfcheck.py` re-parses `raw-all.csv` with the `csv` module and derives its expectations from the operation (what a trim or copy of a region of capacity C holding f bytes allocates), not from `analyze.py`: 351 hold, 0 fail (`run1/selfcheck.out`). I also re-read `SafeMemoryWriter.java:50-72` and `SafeMemory.java:70-75` against the interpretation of arms E, D and X, and `Memory.java:62-65` for the rule's line.

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | ledger live-after equals `capacity()` in every counted row; free count balances allocation count |
| 2. Readings | yes | the residue outliers recur at the same repetition indices at every C (`raw-all.csv`) |
| 3. Matched row | yes | E/D/H/X figures equal the re-derived values |
| 4. Excluded rows | yes | E retained - D retained = 1 in all 25 pairs |
| 5. Observed vs inferred | yes | listed in 4.2 part 5 |
| 6. Deviations and gaps | yes | listed |
| 7. Core question | yes | steps follow the amendment's items b-g |

### 5.2 Run 2?

**No** (2026-10-29). Native figures are exact integers repeated in five fresh JVMs; the one open point is the judgement in section 8, which a rerun cannot settle.

## 6. Run 2 — fresh AI session (optional)

Not done. Sections 6 and 7 omitted.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap).

**Claim tested** (B1): the guard `newCapacity != capacity()` does not cap memory or disk usage; it only skips a same-size reallocation, and the writer's size is set by the written data and the growth policy. "Confirmed" means this held.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1; residue sub-prediction missed, recorded) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a` (B3 amendment: the equal branch needs an exactly full writer; the transient is native MiB-scale memory, below what a node-level sampler can resolve) | n/a | audit | 2026-10-29 |

**Judgement (stated in B2g before the run).** Design §4 row 2 read mechanically ("the branch gates an allocation") would say `caps`. The branch gates a **transient** copy of equal size and nothing retained: retained capacity after the call is identical for E and X (C). A reader who defines "caps" as "changes any allocation" would classify this case as a false negative; the figures for both readings are above (E 0 B vs X C B, peak C vs 2C).

**Positive control:** `DOB_DOUBLING_THRESHOLD_MB` 64 vs 1 moved the ledger's growth allocation from 16,777,216 to 12,582,912 (4,194,304 as predicted). It is a growth-policy knob at `calculateNewSize`, not a cap on the resize, and no cap binds this resource; the known answer (X allocates exactly C) and the ledger-equals-`capacity()` check are the other evidence that the instrument reads real size changes.

**Feedback filed:** section D of the case file (2026-10-29) and the B2/B3 amendments; `_INDEX.md`, `writeup-set-A.csv` and HANDOFF left to the orchestrator.

**Leftovers:** no process running (`ps` shows no `JUnitCore` or `CassandraDaemon`). On `pc29`, outside the repo: `~/s4-none/` (source copy `cassandra`, `logs`, `run1`).
