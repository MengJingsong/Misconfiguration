# none-compose-buffer_remaining--autonomous — stage-4 results  <!-- file: results/none-compose-buffer_remaining--autonomous.md -->

> **Case:** [`none-compose-buffer_remaining--autonomous`](../../stage3-ai-deep-read/cases/none-compose-buffer_remaining--autonomous.md)
>
> **Status:** self-checked 2026-10-29 - unit Confirmed (does not cap); cluster `n/a`; no run 2
>
> **Outcome class:** true negative - stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (dated 2026-10-29, inserted between B2 and B3): `b91209d2c749fa2c97e148b6060c054e3686f60f4fcb09edefe9a048a565c24e`. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D (D reads `none yet` at the freeze). |
| **Harness** | [`harness/none-compose-buffer_remaining--autonomous/`](../harness/none-compose-buffer_remaining--autonomous/README.md), uncommitted (file list in its README). **Pre-run shakedown, disclosed in section 3:** the probe was compiled and run once on a single operand value before run 1 to see that it executes; no prediction was edited after it. |
| **Tiers and values** | Unit (B2 amended): L in {0, 1, 1 KiB, 1 MiB, 16 MiB, 64 MiB} on `BytesType` and `IntegerType`, `Int32Type` at 0 and 4, a null buffer, the 2048-length `read` control, passes A and B. Cluster (B3): `n/a: operand has no size` (amendment 2026-10-29). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

Operand kind: kind 2 (emptiness flag, corrected from the filed data-size reading): `buffer.remaining() == 0` combined with `isEmptyValueMeaningless()`; the branch differs only at length 0.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2 and U0: there is no constraint; the guarded quantity is the transient allocation of one call (heap bytes), named in U3. |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | U3: operand sweep over at least five values (none-type-design.md section 3) with the two branch arms; no knob exists (A1). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | U3: per-call allocated bytes (`getThreadAllocatedBytes`) and post-GC used heap; the Byteman counter proves only reach, and the gap (pass B allocation not used) is named. |
| A. Core question | usage driven to the limit and past it | Met | U3: both sides of the branch at every operand value (arms F and T / T,F,N,D / L = 0 pair). |
| B. Logic | each step says what it establishes | Met | U0 to U4. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f (amended): P1-P7 / Q1-Q6 / R1-R6 with byte bands, frozen below. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g (amended) has rows for Invalid, instrument failure, Confirmed, Refuted, undetermined. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly | No ceiling exists; the direct evidence is the branch counter and the per-branch difference (U3). Stated in U0. |
| B. Logic | alternative explanations and their controls | Partly | Instrument controls and the noise floor are in U3; no closed capping setting binds this resource (disclosed as the honest limit). |
| C. Specific | a human can follow it from the intro and B2f | Met | U0 explains kind and the meaning of "caps". |
| C. Specific | an AI can run B2a-B2e without re-deriving the code path | Met | U1-U3 give launcher, sweep, arms and order. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met | U3: values, K, repetitions, warm-up, passes. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Written in step 1 (this session): `harness/none-compose-buffer_remaining--autonomous/`; build copy on `pc41`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest cell is 4 MiB / 64 MiB per call against -Xmx512m / -Xmx1g; local disk use under 200 MB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | U1/U2 list every citation re-read in `cassandra/cassandra-5.0.9/`; corrections recorded as feedback in section D. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Kind corrected to 2; the sweep type for large L is `IntegerType` (meaningless when empty, any length), not `Int32Type` (4 bytes) | Applied (U0, U1b) | a long `Int32Type` buffer is not a valid value |
| R2 | Drop the yaml variants (`max_value_size`, frame limit): `compose` reads no config | Applied (U1c) | not a branch flip |
| R3 | Add the branch-flip pair at L = 0 and the Byteman reach counter at line 180 | Applied (U2, U3) | the check differs only at 0 |
| R4 | B3 declared `n/a: operand has no size` | Applied (B3 amendment) | below heap noise |
| R5 | Positive control: the 2048-length `BytesType.read` with max 1024 (AbstractType.java:594) must throw | Applied (U3) | a real size cap in the same harness |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 (node clock UTC 2026-10-29 04:10-04:16; the node shell is MDT, 2026-10-28 22:10-22:16) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL in 1 min 13 s; the probe is compiled outside the tree into `~/stage4-logs/none/compose/run1/classes` |
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `run1/summary.txt` |
| Storage for node data | no node is started; probe temp files under `~/stage4-logs/none/compose/run1/tmp` on local `/dev/sda3`, deleted by the probe; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/none/compose/run1/` (`test-A.out`, `test-B.out`, `jvm-*.log`, `summary.txt`, `analysis.txt`, `selfcheck.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | pre-run shakedown | B2 amended, U3 | none: the probe executed (single value, run name `shake`, `run1/shakedown-summary.txt`); its readings were looked at only to see that the harness ran. No prediction, band or sweep value was edited after it. The shakedown ran the whole sweep once (run name `shake`, mode full): the readings were within the later-frozen bands and run 1 reproduced them exactly. | none | 2026-10-29 |
| D2 | self-check | `selfcheck.py` log scan | the first version of the checker's "no exception/error line in the JVM logs" scan matched the probe's own `STAGE4 ...` result lines (a control prints "IOException" on purpose) | the scan skips lines that contain `STAGE4`; the checker was re-run on the same raw files; no reading changed | 2026-10-29 |

## 4. Run 1

**Scope:** the unit tier as amended (B2): cells (type, L) for `BytesType` and `IntegerType` at L in {0, 1, 1 KiB, 1 MiB, 16 MiB, 64 MiB}, `Int32Type` at 0 and 4, a null buffer, noise-floor repeats, C1 and the 2048-length control; passes A and B, one fresh JVM each (`-Xmx1g`). Cluster tier: not run (`n/a: operand has no size`). **Command log:** `none-compose-buffer_remaining--autonomous/run1/summary.txt`; readings `analysis.txt`; independent re-parse `selfcheck.txt`. This is a unit-tier measurement only (kind 2).

### 4.1 Readings

**Unit tier** (`run1/analysis.txt`; per-call allocation in bytes, the median of five repetition medians; pass B hits at `UDFDataType.java:180`)

| Cell | L | result | allocation | pass B hits / calls |
|---|---|---|---|---|
| null buffer | - | null | 0 | 0 / 1200 |
| `BytesType` | 0 | empty `HeapByteBuffer` | 48 | 1200 / 1200 |
| `IntegerType` | 0 | null | 0 | 0 / 1200 |
| `Int32Type` | 0 | null | 0 | 0 / 1200 |
| `BytesType` | 1 / 1 KiB / 1 MiB / 16 MiB / 64 MiB | `HeapByteBuffer` | 48 at every L | all hits = calls |
| `IntegerType` | 1 | `BigInteger` | 64 | 1200 / 1200 |
| `IntegerType` | 1 KiB | `BigInteger` | 1080 | 1200 / 1200 |
| `IntegerType` | 1 MiB / 16 MiB / 64 MiB | `BigInteger` | 1048632 / 16777272 / 67108920 | all hits = calls |
| `Int32Type` | 4 | `Integer` | 0 | 1200 / 1200 |

Other readings: repeats of the L = 0 cells and of `IntegerType` at 1 MiB equal the first readings exactly (noise floor 0 bytes); EMPTY 0 and 0; C1 `new byte[L]` = 24, 1048592, 67108880 for L = 1, 1 MiB, 64 MiB; the control `BytesType.read` of a 2048 vint with max 1024 threw `IOException` "Corrupt value length 2048 encountered, as it exceeds the maximum of 1024, which is set via max_value_size" (0 MISMATCH) [observed: `run1/test-A.out`, `test-B.out`, `analysis.txt`].

### 4.2 Conclusion and logic

1. **Validity.** Valid. Pass B counted line 180 reached in every call except the null buffer and the L = 0 calls of `IntegerType` and `Int32Type`, where the check returned null at line 178 (0 hits) [observed: `analysis.txt` R1: no violations; `test-B.out`]. The rule type-checked [observed: `testscript.log`].
2. **Readings.** All frozen predictions held (R1 to R6) [observed: `analysis.txt` ALL EXPECTED HOLD; `selfcheck.txt` 14 PASS, 0 FAIL]. `BytesType`'s allocation is 48 bytes at every L, i.e. the driver codec returns a view and does not copy (the case file's "unverified" copy question: it does not copy); `IntegerType`'s grows as L + 56 (the `BigInteger` copy), 1.00005 L at 1 MiB.
3. **Matched row.** B2g (amended) row "R1 to R6 hold": the check saves at most one small object at L = 0 (`BytesType` L = 0 allocates 48 bytes where `IntegerType` L = 0 allocates 0; the difference is 48 bytes, four orders below the 16 MiB heap noise) and changes nothing at L >= 1, where the allocation follows the codec and the data [observed: above].
4. **Excluded rows.** "Invalid": no (R1 holds, results as predicted). "Not confirmed (instrument)": C1 exact, the control threw, EMPTY 0. "Refuted: an L >= 1 difference attributable to the check, or an L = 0 difference above 1024": no (the L >= 1 difference between the types is the codec: 48 versus L + 56; the L = 0 difference is 48). "Not confirmed (below noise floor)": the noise floor is 0, the difference 48 is resolved.
5. **Observed vs. inferred.** Inferred: that the `IntegerType` growth is the codec's copy (not traced inside the driver); and that the L = 0 object saved by the check is the 48-byte empty buffer (observed as the allocation difference, not traced).
6. **Deviations and gaps.** (a) Kind 2: a unit-tier measurement only; the cluster tier is `n/a`. (b) The check can only gate a 48-byte object here; the positive control is the real size cap in the same harness (`max_value_size` at AbstractType.java:594), which refused a 2048-length value that `compose` has no counterpart for - a control for the instrument's ability to see a refusal, not a cap on this path. (c) UDFs were not enabled; only `compose` was exercised, as the case file's mechanism A3 describes. (d) One node, G1, one run.
7. **Core question.** The check compares the argument's length with zero. It changes the outcome only at L = 0 (null versus an empty value, 0 versus 48 bytes); for every L >= 1 both branches run line 180 and the allocation is the codec's, independent of the check (48 bytes for blobs, about L for varints). The check is a normalisation, not a limit, so it does not cap memory.

**Conclusion (one line):** Confirmed (B2g, R1 to R6 all hold) - does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `run1/test-A.out` and `run1/test-B.out` re-parsed by `harness/none-compose-buffer_remaining--autonomous/selfcheck.py` (own regexes, no shared code with `analyze.py`): 14 PASS, 0 FAIL (`run1/selfcheck.txt`). By hand: the `STAGE4 cell` lines for `integer` L = 0, `bytes` L = 0 and `integer` L = 67108864 in both passes, and the `STAGE4 control` line.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | pass B hits: 0 for null, `IntegerType` L = 0, `Int32Type` L = 0; hits = calls elsewhere. |
| 2. Readings | yes | `BytesType` 48 at all six L; `IntegerType` ratio 1.00005 / 1.00000 / 1.00000. |
| 3. Matched row | yes | R1-R6. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | two inferences, neither in the verdict. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29). Exact repeated readings; nothing in the verdict rests on an inference.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the check is an emptiness normalisation; it saves at most a 48-byte object at L = 0 and changes no allocation at L >= 1.

**Claim tested (B1):** the check at UDFDataType.java:177 does not limit memory: for a non-empty argument, heap allocated by `compose` grows with the argument size (through the codec), with no cap introduced at this line.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (R1 to R6 all hold) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: operand has no size` (B3 amendment) | (unit tier settles it) | - | 2026-10-29 |

**Positive control:** `BytesType.read` of a 2048-length value with max 1024 threw (AbstractType.java:594): a real size cap seen in the same harness. C1 `new byte[L]` read L + 16 rounded up to 8 bytes (24, 1048592, 67108880). Honest limit: this cap is on another path; `compose` has no cap to compare.

**Feedback filed:** section D of the case file (2026-10-29, no commit); B2 and B3 amended 2026-10-29. For stage 3: the filed sweep type `Int32Type` is 4 bytes, the right large-L type is `IntegerType`.
