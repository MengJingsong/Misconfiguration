# none-checklimit-length--autonomous — stage-4 results  <!-- file: results/none-checklimit-length--autonomous.md -->

> **Case:** [`none-checklimit-length--autonomous`](../../stage3-ai-deep-read/cases/none-checklimit-length--autonomous.md)
>
> **Status:** self-checked 2026-10-29 - unit Confirmed (does not cap); cluster `n/a`; no run 2
>
> **Outcome class:** true negative - stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (dated 2026-10-29, inserted between B2 and B3): `572860035b34328acad83d6efafb6849ebdaa9a9def84371314ac583d34f20b4`. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D (D reads `none yet` at the freeze). |
| **Harness** | [`harness/none-checklimit-length--autonomous/`](../harness/none-checklimit-length--autonomous/README.md), uncommitted (file list in its README). **Pre-run shakedown, disclosed in section 3:** the probe was compiled and run once on a single operand value before run 1 to see that it executes; no prediction was edited after it. |
| **Tiers and values** | Unit (B2 amended): S in {1 KiB, 64 KiB, 1 MiB, 16 MiB, 64 MiB}, arms F, T, N, D with F2/T2 as noise floor, passes A and B. Cluster (B3): `n/a: the cluster tier cannot resolve the effect` (amendment 2026-10-29). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

Operand kind: kind 3 (requested length): operand `length`, the byte count of a pending read, against the bytes left in the record.

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
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Written in step 1 (this session): `harness/none-checklimit-length--autonomous/`; build copy on `pc41`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest cell is 4 MiB / 64 MiB per call against -Xmx512m / -Xmx1g; local disk use under 200 MB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | U1/U2 list every citation re-read in `cassandra/cassandra-5.0.9/`; corrections recorded as feedback in section D. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | State that in the buffer iterator the limit and the read take the same `size`, so the true branch is not reached on a well-formed record; arm T forces the disagreement with `limit(S - 1)` | Applied (U1c) | otherwise a reader would take arm T for a production case |
| R2 | Verify "primitive reads do not reach checkLimit": grep shows three call sites only | Applied (U1b) | the case file marked it unverified |
| R3 | Drop the config variants and the write-side `max_hints_file_size` control; use the liveness gate (arm D) and `new byte[S]` as controls | Applied (U1d, U3) | the check reads no config; the write-side cap acts on file length, a different statement |
| R4 | B3 declared `n/a` with the reason (no branch to flip on well-formed hints; transient at the heap noise) | Applied (B3 amendment) | the filed two-node run restates the operand effect |
| R5 | Positive control is a liveness gate of the same method, not a configured cap; no configured cap binds this read | Stated (U3) | disclosed |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 (node clock UTC 2026-10-29 04:10-04:16; the node shell is MDT, 2026-10-28 22:10-22:16) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL in 1 min 13 s; the probe is compiled outside the tree into `~/stage4-logs/none/checklimit/run1/classes` |
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `run1/summary.txt` |
| Storage for node data | no node is started; probe temp files under `~/stage4-logs/none/checklimit/run1/tmp` on local `/dev/sda3`, deleted by the probe; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/none/checklimit/run1/` (`test-A.out`, `test-B.out`, `jvm-*.log`, `summary.txt`, `analysis.txt`, `selfcheck.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | pre-run shakedown | B2 amended, U3 | none: the probe executed (single value, run name `shake`, `run1/shakedown-summary.txt`); its readings were looked at only to see that the harness ran. No prediction, band or sweep value was edited after it. The shakedown ran S = 1 MiB only (passes A and B); T - F was 672 and the hit counts 3/3/3/2, inside the bands later frozen and reproduced in run 1. | none | 2026-10-29 |
| D2 | self-check | `selfcheck.py` log scan | the first version of the checker's "no exception/error line in the JVM logs" scan matched the probe's own `STAGE4 ...` result lines (a control prints "IOException" on purpose) | the scan skips lines that contain `STAGE4`; the checker was re-run on the same raw files; no reading changed | 2026-10-29 |

## 4. Run 1

**Scope:** the unit tier as amended (B2), every value: S in {1 KiB, 64 KiB, 1 MiB, 16 MiB, 64 MiB}, passes A and B, one fresh JVM each (10 JVMs, `-Xmx1g`). Cluster tier: not run (`n/a`, B3 amendment). **Command log:** `none-checklimit-length--autonomous/run1/summary.txt`; readings `analysis.txt`; independent re-parse `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`run1/analysis.txt`; bytes; medians of the five repetition medians, pass A unless stated)

| S | F1 (limit S) | T1 (limit S-1) | T1 - F1 | N (no limit) | D (dead hint) | C1 `new byte[S]` | `checkLimit` hits per call F / T / N / D (pass B) | T outcome | retained change F / T |
|---|---|---|---|---|---|---|---|---|---|
| 1 KiB | 1208 | 1880 | 672 | 1208 | 120 | 1040 | 3 / 3 / 3 / 2 | threw 1400 of 1400 | - |
| 64 KiB | 65720 | 66392 | 672 | 65720 | 120 | 65552 | 3 / 3 / 3 / 2 | threw 1400 of 1400 | - |
| 1 MiB | 1048760 | 1049432 | 672 | 1048760 | 120 | 1048592 | 3 / 3 / 3 / 2 | threw 140 of 140 | 2092320 / -528 |
| 16 MiB | 16777400 | 16778072 | 672 | 16777400 | 120 | 16777232 | 3 / 3 / 3 / 2 | threw 18 of 18 | 17799984 / 9960 |
| 64 MiB | 67109048 | 67109720 | 672 | 67109048 | 120 | 67108880 | 3 / 3 / 3 / 2 | threw 7 of 7 | 68171096 / 6456 |

Other readings: F2 = F1 and T2 = T1 exactly at every S (noise floor 0 and 0 bytes); EMPTY 0 and 0; F and N returned a buffer of exactly S bytes, T threw `IOException` "Digest mismatch exception" on every call, D returned null (5 checks per JVM, 0 MISMATCH); the retained change for F is S plus G1's humongous-region rounding (2.09 MB for the 1 MiB buffer, 17.8 MB for 16 MiB, 68.2 MB for 64 MiB), for T under 10 kB [observed: `run1/test-A.out`, `analysis.txt`].

### 4.2 Conclusion and logic

1. **Validity.** Valid. The check ran as designed: pass B counted 3 entries of `checkLimit` per call in F, T and N and 2 in D, at every S [observed: `run1/test-B.out`, `analysis.txt` Q1]; T threw the check's own exception on every call and F, N returned S bytes [observed: `STAGE4 arm` lines `threw=`, `lastCap=`, `lastMsg=`]. The record is exactly S bytes with a live header (`liveLen`) [observed: `STAGE4 info` lines]. The rule type-checked [observed: `testscript.log`]. As stated in the case file (U1c), the true branch is forced by `limit(S - 1)`; on a well-formed record in the production buffer iterator it is never true [inferred: HintsReader.java:340-342 passes the same `size` to `limit` and to `readBufferIfLive`].
2. **Readings.** All frozen predictions held (Q1 to Q6): F in [S + 16, S + 2048] (S + 184); N equal to F; T in [S + 16, S + 6144] (S + 856) and T - F = 672 at every S; D = 120 bytes at every S (at most S/8 for S >= 64 KiB); noise floor 0; retained as predicted; C1 = S + 16 [observed: `analysis.txt`: ALL EXPECTED HOLD; `selfcheck.txt`: 37 PASS, 0 FAIL]. Nothing unusual except G1's humongous rounding in the retained reading, which the band allowed.
3. **Matched row.** B2g (amended) row "Q1 to Q6 all hold": the check rejects the read after the allocation: T allocates S + 856, at least as much as F (S + 184); the 672-byte difference is the exception and its stack trace; nothing is retained after the throw (6.5-10 kB, noise); usage follows the record's size [observed: above].
4. **Excluded rows.** "Invalid": no (Q1, Q2 hold). "Not confirmed (instrument)": C1 exact, D dropped the allocation from S + 184 to 120 bytes (the instrument sees an allocation-gating branch), EMPTY 0. "Refuted caps: T below S": no, T = S + 856. "Refuted: |T - F| above 6144": no, 672 [observed: `analysis.txt`].
5. **Observed vs. inferred.** Inferred: that the 672 bytes are the exception object and its stack trace (not separately measured), and that production never takes the true branch on a well-formed record (source reading). Neither changes the verdict.
6. **Deviations and gaps.** (a) Arm T is forced (U1c); a corrupt hint whose inner lengths exceed the record is the only way the check fires in production. (b) The positive control (D) is a liveness gate in the same method, not a configured cap; no configured cap binds this read, and the write-side `max_hints_file_size` control of the filed text was dropped (U1d). (c) The cluster tier was not run (B3 amendment). (d) One node, G1. (e) Sizes above the 16 MiB default `max_mutation_size` (the 64 MiB cell) are a unit-tier extrapolation: a real hint cannot be that large.
7. **Core question.** The operand is the pending read's length against the record's remainder. Flipping the branch (limit S versus S - 1) changes the allocation by 672 bytes and nothing else: both arms allocate the full `byte[S]` first (T = S + 856), and the throw leaves nothing retained. The liveness gate in the same method, by contrast, cuts the allocation to 120 bytes, so the instrument could have shown a gating check. The limit check therefore rejects a read but does not bound what is allocated, and it does not cap memory.

**Conclusion (one line):** Confirmed (B2g, Q1 to Q6 all hold) - does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `run1/test-A.out` and `run1/test-B.out` re-parsed by `harness/none-checklimit-length--autonomous/selfcheck.py` (own parser; recomputes each arm median from the five raw `rep` lines): 37 PASS, 0 FAIL (`run1/selfcheck.txt`). By hand: the S = 67108864 `STAGE4 arm` lines for F1, T1 and D in both passes and the `STAGE4 retained` lines.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | pass B `hitsPerCall` 3.0, 3.0, 3.0, 2.0 at all S; T `threw` equals `calls`. |
| 2. Readings | yes | `selfcheck.txt` Q3 lines: F - S = 184, T - S = 856, D = 120. |
| 3. Matched row | yes | all bands. |
| 4. Excluded rows | yes | T >= S at every S; D far below F. |
| 5. Observed vs. inferred | yes | two inferences, neither in the verdict. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | |

### 5.2 Run 2?

**No** (2026-10-29). Exact repeated readings (F1 = F2, T1 = T2), the check's counters match the source reading, and no inferred statement carries the verdict.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the check rejects an over-long read after the `byte[size]` is allocated; it bounds neither the allocation nor the retained size.

**Claim tested (B1):** the `limit` checked at ChecksummedDataInput.java:161 is not a configured memory or disk cap: it equals the record's own declared `size`, so memory used while reading a hint tracks the file's `size` field and is not changed by any configuration knob.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (Q1 to Q6 all hold) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: the cluster tier cannot resolve the effect` (B3 amendment) | (unit tier settles it) | - | 2026-10-29 |

**Positive control:** arm D (dead hint) cut the same method's allocation from S + 184 to 120 bytes, so the instrument sees a check that gates the allocation; C1 `new byte[S]` read S + 16. Honest limit: D is a liveness test, not a configured cap, and no configured cap binds this read.

**Feedback filed:** section D of the case file (2026-10-29, no commit); B2 and B3 amended 2026-10-29. For stage 3: the true branch is unreachable on a well-formed record in the buffer iterator (limit and read share `size`), so this `none` case is a forced-flip measurement.
