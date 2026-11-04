# no_constraint-hascomponent-i_nextsize--autonomous — stage-4 results  <!-- file: results/no_constraint-hascomponent-i_nextsize--autonomous.md -->

> **Case:** [`no_constraint-hascomponent-i_nextsize--autonomous`](../../stage3-ai-deep-read/cases/no_constraint-hascomponent-i_nextsize--autonomous.md)
>
> **Status:** **Self-checked 2026-10-29 — unit Confirmed (does not cap); cluster `n/a`; control B ran with an effective limit of 0 (setter granularity); no run 2**
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D). `none` type, operand kind 1 (count of held data) ([`none-type-design.md`](../none-type-design.md)); unit-tier measurement only.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendment (dated 2026-10-29, B2/B3 replaced), **frozen before any sweep reading: `10d0dd9b9ab8e8d3ca3951cb07f8db51505e4915417a38a29b886e882aabec83`**. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D; section D is filled after the verdict and its sha256 is recorded in section 8. |
| **Harness** | [`harness/no_constraint-hascomponent-i_nextsize--autonomous/`](../harness/no_constraint-hascomponent-i_nextsize--autonomous/README.md), uncommitted: `ClusteringHasComponentTest.java`, `rules.btm`, `unit-run.sh`, `analyze.py`, `selfcheck.py`. |
| **Tiers and values** | Unit (B2): (nextSize, S) = (1,1), (2,1), (2,2), (2,4), (4,2), (4,4), (4,8), (8,8), (8,16), (16,16) with 1,024-byte components; controls: 64 KiB components, `max_value_size` 512; two noise blocks at (4,4); 3 warm-up + 7 repeats each. Cluster (B3): `n/a` (reason in B3 and section 8). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2: the allocated `byte[]` components and `byte[nextSize][]`; the check bounds none. |
| A. Core question | knob varied, >= 3 values incl. default — or another approach | Not met -> Met | filed B2 was `n/a`; amended to the (nextSize, S) sweep, 10 points, S below / equal / above nextSize. |
| A. Core question | real resource measured, not only the counter | Met | bytes allocated by the calling thread around `compareNextTo`. |
| A. Core question | usage driven to the limit and past it | Met (adapted) | S above nextSize drives the check's false branch; no limit exists. |
| A. Core question | positive control for a negative claim | Met after amendment | component 64 KiB (allocation must move 50x or more); `max_value_size` set to 512 as a real limit acting on the same allocation. |
| B. Logic | each step says what it establishes | Met | B2e numbered. |
| B. Logic | prediction stated in numbers | Not met -> Met | 1,040 x min(S, nextSize), tolerances, noise-floor rule. |
| B. Logic | every plausible outcome has a conclusions row | Not met -> Met | B2g table. |
| B. Logic | confirmation needs direct disallow evidence | Met | Byteman count of the false return (once per call iff S > nextSize) and `deserializedSize`. |
| B. Logic | alternative explanations and their controls | Met | probe equals stored bytes (no early mismatch return); `prepare` outside the window. |
| C. Specific | human / AI can follow | Met after amendment | construction of the stream and the probe is given. |
| C. Specific | values, commands, observables exact | Met after amendment |  |
| D. Runnable | harness exists | Met | test class, rules, scripts. |
| D. Runnable | workload reaches the check | Met | `Deserializer` is public; `prepare(0x02, 0)` selects the marker branch; checked by the instrument run. |
| D. Runnable | citations spot-checked | Partly -> Met | five line errors in the case file (nextSize :617, deserializedSize :618/:670, nextValues :626, loop :634, readArray :674) corrected in the amendment; claim unaffected. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Fill B2 with the (nextSize, S) design; B3 `n/a: below heap noise` (amendment 2026-10-29) | Applied | filed `n/a: no constraint`; the operand is a count of held data (kind 1). |
| R2 | Correct the five citations in A1-A3 | Applied in the amendment note; the filed A-sections are left as filed (feedback in D) | claim unchanged. |

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
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `no_constraint-hascomponent-i_nextsize--autonomous/run1/harness.md5` |
| Storage for node data | none (no daemon); JUnit scratch under `~/stage4-logs/none/` on local `/dev/sda3` |
| Full logs (outside the repo) | `pc39:~/stage4-logs/none/no_constraint-hascomponent-i_nextsize--autonomous/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | run 1 | B2e step 6, control B | `DatabaseDescriptor.setMaxValueSize(512)` (DatabaseDescriptor.java:1933-1937) divides by 1 MiB, so the limit set was 0 bytes, not 512 (`getMaxValueSize()` reads 0). The prediction ("the call throws") still holds, but the limit was 0 | none; recorded as a deviation, the other readings are unaffected | 2026-10-29, prediction and table unchanged |

## 4. Run 1

**Scope:** the whole amended B2; B3 `n/a`. **Command log:** `no_constraint-hascomponent-i_nextsize--autonomous/run1/` (`session-plain.log`, `session-bm.log`, `analysis.txt`, `selfcheck.txt`, `raw-plain/raw.csv`, `raw-bm/trace.txt` head in `junit-stage4-lines-and-trace-heads.txt`).

### 4.1 Readings

**Unit tier** (bytes allocated by the calling thread around `compareNextTo`, median of 7; every range 0)

| Test or assertion | Result | Evidence |
|---|---|---|
| Instrument known-answer and empty window | 8,388,624 bytes (expected 8,388,608 to 8,454,144); empty window 0 | `junit-stage4-lines-and-trace-heads.txt` |
| (nextSize, S) = (1,1) (2,1) (2,2) (2,4) (4,2) | 1,040 / 1,040 / 2,080 / 2,080 / 2,080 (frozen 1,040 / 1,040 / 2,080 / 2,080 / 2,080) | `analysis.txt` |
| (4,4) (4,8) (8,8) (8,16) (16,16) | 4,160 / 4,160 / 8,320 / 8,320 / 16,640 (frozen the same) | same |
| `deserializedSize` after the call | min(S, nextSize) at every point, every repeat (1, 1, 2, 2, 2, 4, 4, 8, 8, 16) | same |
| Flip pairs (2,2)\|(2,4), (4,4)\|(4,8), (8,8)\|(8,16) | difference 0 bytes in each | same |
| Noise floor | 0 (two (4,4) blocks: 4,160 / 4,160, ranges 0) | same |
| False returns (Byteman JVM) | 10 per nextSize for nextSize 2, 4, 8 (exactly the points with S > nextSize, once per call), each with `i == nextSize`; `deserializeOne` entered 610 times (= 10 x (48 + 4 + 4) + 40 + 10) | `selfcheck.txt` |
| Control A, 64 KiB components (4,4) | 262,208 bytes (frozen 262,208), 63.0 x the 1 KiB reading | `analysis.txt` |
| Control B, `setMaxValueSize(512)` (effective limit 0, defect D1), 1 KiB components (4,4) | every call threw `IOException`; allocation 2,792 bytes (the exception and its message) instead of 4,160 | same |

**Cluster tier:** `n/a: below heap noise` (B3).

### 4.2 Conclusion and logic

1. **Validity** — valid. Both sides of the check were observed (one false return per call exactly when S > nextSize; none otherwise) [observed: `selfcheck.txt` F lines, `deserializedSize`], the probe never returned early on a mismatch (`deserializedSize` = min(S, nextSize) at every point) [observed], the instrument read its known answer, and control A moved 63 x [observed].
2. **Readings** — nothing unusual. All readings are exact multiples of 1,040 and have range 0, so the noise floor is 0.
3. **Matched row** — B2g row 1 (amended): allocation follows `min(S, nextSize) x 1,040` at all ten points, the three flip pairs differ by 0 bytes, both branches observed, control A moved.
4. **Excluded rows** — "flip pair differs by more than max(2 x noise, 256)" (Refuted): no, the differences are 0 [observed]; "something else allocates in the window": no, the totals equal the closed form exactly [observed]; "not resolved": no; "invalid": no (control A moved, false return observed for S > nextSize, `deserializedSize` as predicted). Numeric predictions all held; control B threw as predicted.
5. **Observed vs. inferred** — all observed. The interpretation that the operand is the data itself follows from the closed form (none-type-design.md section 6) [inferred]; it does not enter the verdict, which rests on the flip pairs.
6. **Deviations and gaps** — D1: control B's limit was 0, not 512 bytes (granularity of the setter); the conclusion needs only that a real limit acts on the same allocation, which it did. Unit tier only: one `compareNextTo` allocates at most 16,640 bytes here; the code path is not driven through a real sstable read; byte-array components only (`BytesType`).
7. **Core question** — Usage follows the stored component count and the probe's size through `min(S, nextSize)`, which is the data itself, and the false return of `hasComponent` at `i >= nextSize` changes no allocation: with S above `nextSize` the allocation equals that with S equal to it, and the limit that does act on the same allocation is `max_value_size` (control B).

**Conclusion (one line):** B2g row 1 (amended) — Confirmed: the check does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29 by `harness/no_constraint-hascomponent-i_nextsize--autonomous/selfcheck.py` (plain `split()` parsing, own expected counts, no use of `analyze.py`): `selfcheck.txt` "ALL PASS" (17 checks), plus a NOTE on control B.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | 98 rows; F lines 30 with `i == nextSize`; D lines 610 equal the count derived from the point list. |
| 2. Readings | yes | each point's median and `deserializedSize` recomputed. |
| 3. Matched row | yes | |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | |
| 6. Deviations and gaps | yes | D1 confirmed in the raw `maxValueSize` column (0). |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29): deterministic readings, exact closed form, independent re-parse passes.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** the check `i >= nextSize` / loop in `hasComponent` does not cap memory or disk usage; it is index-bounds and loop control. Measured as: its false return changes no allocation.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (amended B2g row 1) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: below heap noise` | not run | | 2026-10-29 |

**Positive control:** 64 KiB components moved the allocation 63 x (262,208 vs 4,160 bytes) on the same instrument; `max_value_size` (effective 0) made the call throw instead of allocating [observed].

**Noise floor:** 0 bytes (two identical blocks, range 0).

**Scope note (none-type-design.md section 6):** a unit-tier measurement of kind 1; the operand is the data, so "allocation follows nextSize" is expected and is not the finding; the finding is that the branch flip changes nothing.

**Feedback filed:** section D of the case file updated 2026-10-29 (no commit by this session); final sha256 of the case file with section D filled: `f66816df6f046b87ae727fc8c07ee2a5a62f2c89e2c42ce269d4f734185362cf`.
