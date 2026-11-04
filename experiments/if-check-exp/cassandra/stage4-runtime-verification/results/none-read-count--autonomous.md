# none-read-count--autonomous — stage-4 results  <!-- file: results/none-read-count--autonomous.md -->

> **Case:** [`none-read-count--autonomous`](../../stage3-ai-deep-read/cases/none-read-count--autonomous.md)
>
> **Status:** self-checked 2026-10-29 - unit Confirmed (does not cap); cluster `n/a`; no run 2; frozen sub-predictions P3 (N = 131072, 1048576) and P7 (C2 at N = 32) missed, disclosed
>
> **Outcome class:** true negative - stage-3 estimate `negative` against the stage-4 effect `does not cap` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (dated 2026-10-29, inserted between B2 and B3): `470e98d5a22f12031b1cde82db608d3596f844fd490b3bd45c2a02acec6116f3`. Repository HEAD of this session `a254c929`; case file, harness and results uncommitted. The frozen text is everything above section D (D reads `none yet` at the freeze). |
| **Harness** | [`harness/none-read-count--autonomous/`](../harness/none-read-count--autonomous/README.md), uncommitted (file list in its README). **Pre-run shakedown, disclosed in section 3:** this case's probe is the same source file as the float twin's, which was compiled and run once on a single operand value (N = 1536) before run 1 to see that it executes; this case itself had no separate shakedown; no prediction was edited after it. |
| **Tiers and values** | Unit (B2 amended): N in {32, 128, 1536, 16384, 131072, 1048576} ints, arms F and T, F2 and T2 as noise floor, passes A and B. Cluster (B3): `n/a: the cluster tier cannot resolve the effect` (amendment 2026-10-29). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-29 |

Operand kind: kind 3 (requested length): operand `count` (ints) against the ints left in the current mmap region.

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
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Written in step 1 (this session): `harness/none-read-count--autonomous/`; build copy on `pc41`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest cell is 4 MiB / 64 MiB per call against -Xmx512m / -Xmx1g; local disk use under 200 MB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | U1/U2 list every citation re-read in `cassandra/cassandra-5.0.9/`; corrections recorded as feedback in section D. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Replace the filed 1000-call average and counts 1..1024 by a one-call window and six values over four orders (U2, U3); the filed segment sizes 4096 and 16384 are replaced by one lowered size (65536) so the start offset is identical in both arms | Applied 2026-10-29 | equal start offset isolates the branch |
| R2 | Seek before every read (EMPTY holder throws on `intBuffer()`) | Applied (U2a) | the filed workload would have failed |
| R3 | Verify the jvector callers with `javap -c` (`read([III)V` in `OnDiskGraphIndex$OnDiskView`) | Applied (U0) | the case file left the caller unverified |
| R4 | B3 declared `n/a` with the reason (needs a graph file above 2 GiB; transient is 4 x count bytes) | Applied (B3 amendment) | the filed B3 cannot reach the true branch and cannot resolve its effect |
| R5 | No closed capping setting binds this transient allocation: positive control limited to C1/C2 and T minus F equal to the copy | Stated (U3 honest limit) | disclosed, not invented |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-29 (node clock UTC 2026-10-29 04:10-04:16; the node shell is MDT, 2026-10-28 22:10-22:16) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` |
| JDK / Ant | openjdk 11.0.32.1 (2026-08-18) / Apache Ant 1.10.12 |
| Local source copy | `~/s4-none` from `cassandra/cassandra-5.0.9/` at repository commit `a254c929` (`copy-source.sh`), `ant build-test` BUILD SUCCESSFUL in 1 min 13 s; the probe is compiled outside the tree into `~/stage4-logs/none/read-count/run1/classes` |
| Case-file / harness commit | uncommitted (working tree of `a254c929`); sha256 in section 1; harness md5s in `run1/summary.txt` |
| Storage for node data | no node is started; probe temp files under `~/stage4-logs/none/read-count/run1/tmp` on local `/dev/sda3`, deleted by the probe; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/none/read-count/run1/` (`test-A.out`, `test-B.out`, `jvm-*.log`, `summary.txt`, `analysis.txt`, `selfcheck.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | pre-run shakedown | B2 amended, U3 | none: the probe executed (single value, run name `shake`, `run1/shakedown-summary.txt`); its readings were looked at only to see that the harness ran. No prediction, band or sweep value was edited after it. No separate shakedown was run for this case: its probe is the same file as the float case, whose one-value shakedown (N = 1536) had executed. | none | 2026-10-29 |
| D2 | self-check | `selfcheck.py` log scan | the first version of the checker's "no exception/error line in the JVM logs" scan matched the probe's own `STAGE4 ...` result lines (a control prints "IOException" on purpose) | the scan skips lines that contain `STAGE4`; the checker was re-run on the same raw files; no reading changed | 2026-10-29 |

## 4. Run 1

**Scope:** the unit tier as amended (B2), every value: N in {32, 128, 1536, 16384, 131072, 1048576} ints, passes A and B, one fresh JVM each (12 JVMs). Cluster tier: not run (`n/a`, B3 amendment). **Command log:** `none-read-count--autonomous/run1/summary.txt`; readings `analysis.txt`; independent re-parse `selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`run1/analysis.txt`; bytes; medians of the five repetition medians; pass A unless stated)

| N | F1 | T1 | T1 - F1 | 4N | T1 - F1 - 4N | pass B hits at line 120: F / T (calls) | retained change after M calls: F / T |
|---|---|---|---|---|---|---|---|
| 32 | 56 | 392 | 336 | 128 | 208 | 0 / 14000 (14000) | -3496 / 0 |
| 128 | 56 | 776 | 720 | 512 | 208 | 0 / 14000 (14000) | -10488 / 38472 |
| 1536 | 56 | 6408 | 6352 | 6144 | 208 | 0 / 14000 (14000) | 0 / -33496 |
| 16384 | 56 | 65800 | 65744 | 65536 | 208 | 0 / 3500 (3500) | 0 / -26576 |
| 131072 | 56 | 525168 | 525112 | 524288 | 824 | 0 / 700 (700) | -6992 / -62872 |
| 1048576 | 56 | 4200112 | 4200056 | 4194304 | 5752 | 0 / 140 (140) | 0 / 138416 |

Other readings (all N): F2 = F1 and T2 = T1 exactly (noise floor 0 and 0 bytes); the EMPTY window 0 and 0; every content and file-pointer check `ok` (4 per JVM, 0 MISMATCH); F1 = 56 at every N (spread 0); C1 (`new int[N]`) = 4N + 16 at every N (144, 528, 6160, 65552, 524304, 4194320); C2 (about 100 MiB of arrays kept alive): 37.0 MB (35.3 MiB) at N = 32 (250000 arrays), 104.9-208.9 MB at the other N [observed: `run1/test-A.out` lines `STAGE4 c1`, `STAGE4 c2`].

### 4.2 Conclusion and logic

Tags: **[observed: file]** or **[inferred: reason]**.

1. **Validity.** Valid. The true branch was taken exactly when designed: pass B counted 0 hits at line 120 in F1 and F2 and as many hits as calls in T1 and T2 at every N (14000, 14000, 14000, 3500, 700, 140) [observed: `run1/test-B.out` `STAGE4 arm` lines; `analysis.txt` P1 lines]. Both arms start at the same offset inside region 0 [observed: `STAGE4 info ... start=`; inferred: same code path, lines 52-58 / 100-107]; the file contents and the file pointer were checked in every arm [observed: `STAGE4 check ... data` lines, 0 MISMATCH]. The agent run's rule type-checked [observed: `run1/testscript.log`].
2. **Readings.** Frozen sub-predictions that missed (nothing was edited): **P3** (T - F within 4N + 16 .. 4N + 640) held at N = 32 .. 16384 (excess over 4N: 208, 208, 208, 208) and missed at N = 131072 (excess 824) and N = 1048576 (excess 5752) [observed: `analysis.txt`, `selfcheck.txt` NOTE lines]. [inferred: the lowered segment size of arm T (65536) makes a read of 4N bytes cross about 4N / 65536 region boundaries, and each boundary costs one `reBuffer()` (a `ByteBuffer` duplicate, about 90-100 bytes): 8 boundaries at N = 131072, 64 at N = 1048576, 90 bytes per boundary; I had priced the region switch as a constant. The excess is 0.14 percent of 4N at the large end.] **P7** (C2 raising the post-GC heap by at least 90 MiB) missed at N = 32 only: the design capped the array count at 250000, so 250000 arrays of 144 bytes can hold 35 MiB, and it read 37.0 MB (35.3 MiB) [observed: `analysis.txt`]; the control moved by 18 times the 2 MiB band and every other N reached 105-209 MB. All other predictions held: P1, P2 (F = 56 at all six N, spread 0), P4, P5, P6 (retained change under 140 kB in every block), P7 for C1 at every N [observed: `analysis.txt`, `selfcheck.txt`: 91 PASS, 3 FAIL, the 3 being the items above].
3. **Matched row.** None matches the frozen text letter for letter: the Confirmed row of B2g needs "P1 to P7 all hold" and P3 (two N) and P7 (C2 at N = 32) did not hold. Everything the Confirmed row stands for did hold: the branch ran, the true branch costs one transient copy of the requested size (T - F = 4N + 208 for N up to 16384, and 4N plus about 90 bytes per region crossed above), F does not follow N, nothing is retained, the allocation instrument and the retention instrument both moved [observed: above]. I file the case under the Confirmed row with the two misses recorded, not as a fit.
4. **Excluded rows.** "Invalid" (branch not as designed or data wrong): no, P1 and P5 hold. "Not confirmed: C1 or C2 outside P7 or EMPTY above 16": C1 is exact at every N, C2 moved by 35.3 MiB at its weakest and 100 MiB or more elsewhere, EMPTY 0. "Not confirmed: T - F below 4N + 16": no, T - F is at least 4N + 208. "Refuted" needs F to follow N (no, spread 0), or T - F above 4N + 640 *growing faster than 4N*, or retained change above 2 MiB: T - F is above the band at two N, but it is linear in the number of regions crossed (the slope of T - F against 4N is 1.0013 between N = 16384 and N = 131072, computed by hand from `analysis.txt`: 459368 / 458752), the excess is an artefact of the 64 KiB segment, and retained change is under 140 kB (`analysis.txt`), so I do not read this as the code costing more than the traced copy [inferred: the per-region cost is the `reBuffer()` of the traced step A3.5].
5. **Observed vs. inferred.** Inferred: the cause of the P3 excess (per-region `reBuffer`), and that a production straddle (one boundary at a 2 GiB region end) costs 4N plus about 200 bytes; neither enters the verdict, which rests on the branch counters, F flat in N, T - F tracking 4N, and the retained change.
6. **Deviations and gaps.** (a) The true branch needed `MAX_SEGMENT_SIZE` lowered to 65536; at the default (about 2 GiB regions) a graph file under 2 GiB never takes it (B3 amendment). (b) No closed capping setting binds this transient allocation, so the positive control is the instrument pair C1/C2 (allocation seen exactly, retention seen) and the branch difference itself, not a cap (disclosed in U3). (c) One probe on one node; G1 collector; the int variant of the other case was run separately. (d) The cluster tier was not run. (e) The P3 and P7 misses above.
7. **Core question.** The operand is the caller's requested int count; usage follows it only through the copy the true branch makes (T - F = 4N plus a few hundred bytes), F is flat (56 bytes) whatever N, and nothing is retained after 140 to 20000 calls (change under 140 kB). The check selects between a zero-copy read and a copying read; it never reduces, refuses or bounds an allocation, so it does not cap usage. [Steps: knob-free sweep (4.1) -> branch counters (part 1) -> branch difference (part 2) -> controls (part 2, 6b).]

**Conclusion (one line):** Confirmed (Unit B2g Confirmed row, with the sub-predictions P3 at N = 131072 and 1048576 and P7's C2 at N = 32 missed) - does not cap.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-29: `run1/test-A.out` and `run1/test-B.out` re-parsed by `harness/none-read-count--autonomous/selfcheck.py` (its own parser; it recomputes every arm median from the five raw `rep` lines and re-evaluates P1-P7): `run1/selfcheck.txt` 91 PASS, 3 FAIL (the three misses above, printed with NOTE lines). By hand: the `STAGE4 arm` lines of pass B for N = 1048576 (`hits=140 calls=140` for T1, `hits=0` for F1) and the `STAGE4 branch` line (`T1-F1=4200056`).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `test-B.out` hits equal calls in T and 0 in F at all six N; `testscript.log` 1 rule type checked; no daemon left (`ps` 0). |
| 2. Readings | yes | `selfcheck.txt`: the three FAIL lines are the three misses listed; P3 excess recomputed 208 / 824 / 5752. |
| 3. Matched row | yes, with the caveat | The Confirmed row's literal condition is not met (P3, P7 misses); recorded as such in part 3. |
| 4. Excluded rows | yes | slope of T - F against 4N recomputed by hand from `analysis.txt` (459368 / 458752 = 1.0013); `selfcheck.txt` prints the excess per N (208 / 824 / 5752). |
| 5. Observed vs. inferred | yes | the per-region cost is the only inference of weight. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question | yes | counters -> difference -> retained -> controls. |

### 5.2 Run 2?

**No** (2026-10-29). Every figure is exact and repeated (F1 = F2, T1 = T2 in 12 JVMs); the misses are about secondary bands, not the effect.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap): the check at line 117 selects the copying read; the true branch adds one transient `4 x count` copy and nothing is retained.

**Claim tested (B1):** usage does not follow the line-117 check: the check only selects the read path, the extra heap allocation on the slow path is one transient `4 * N` bytes per call independent of any configuration entry, and no retained memory or disk grows because a vector crosses a region boundary.

| Tier | Verdict (B2g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g Confirmed row; P3 missed at N = 131072 and 1048576, P7's C2 missed at N = 32, both explained and not edited) | does not cap | run 1 + self-check | 2026-10-29 |
| Cluster | not run: `n/a: the cluster tier cannot resolve the effect` (B3 amendment, 2026-10-29) | (unit tier settles it) | - | 2026-10-29 |

**Positive control:** no closed capping setting binds this transient allocation. The instrument was shown to see an allocation (C1 exact at 4N + 16 for every N), retention (C2 raised the post-GC heap by 35 to 209 MB) and a branch difference (T - F = 4N + a few hundred bytes with F = 56 bytes constant). The unit tier is a measurement of one call, as the design says; "does not cap" rests on the true branch never reducing or refusing an allocation, which is a statement about the code path the counters prove was taken.

**Feedback filed:** the case file's section D updated (dated 2026-10-29, no commit by this session); amendments B2 and B3 dated 2026-10-29. For stage 3 / the none-type design: price a lowered-segment crossing per region, not as a constant; cap the C2 array count above 100 MiB / (16 + 4N).
