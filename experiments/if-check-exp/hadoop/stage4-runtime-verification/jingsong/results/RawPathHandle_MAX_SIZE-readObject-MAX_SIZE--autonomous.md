# RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous — stage-4 results  <!-- file: results/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md -->

> **Case:** [`RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous.md)
>
> **Status:** verdict filed (2026-11-06): audited 14:13 EST, run 1 14:17–14:20 EST (node clock 12:17–12:20 MST), self-checked; no run 2
>
> **Outcome class:** **true positive** — estimate `positive`; unit Confirmed — caps, cluster Confirmed — caps
>
> **Agent:** autonomous (the suffix of the case-file stem). "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Layout.** Hadoop, Jingsong's share: this file is in `hadoop/stage4-runtime-verification/jingsong/results/`; the case file is in
`hadoop/stage3-ai-deep-read/jingsong/cases/`; the harness is in `../harness/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/`; the protocol is
[`../../../../stage4-runtime-verification/README.md`](../../../../stage4-runtime-verification/README.md#the-run-protocol);
the node is described in [`../environment.md`](../environment.md).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, repository HEAD `38acb6bf` plus the uncommitted case file (untracked at audit time). sha256 at filing (`_INDEX.md`, queue order 2): `e99136da0175e31016987efb9f946a52fa922efbcef6761ead69800776974127` (checked before the audit). After the audit's amendments A1–A7 (section D1), 2026-11-06 14:13 EST, before any harness run or reading: whole-file sha256 **`67839a9231a4532c540103453d5c76d7f183f657b12c753dba57ef9da961836d`** (frozen version). Frozen prediction, conclusions and controls: sha256 of the text from `**B2f.` up to `**B2h.` (B2f + A4, B2g + A5) `75d4bb4973dad6c4577a28d3a567d3c8cfcacd688ac4c3c17fefbafbd34cacba`; from `**B2f.` up to `### B3.` (adds B2h + A6) `30b23a929bace72273ea27d611f727d5afe5eaf8852ecc5a0eea219594ffb40a`; the B3 section (with A7) from `### B3.` up to `**B4.` `5ce4a8a899acc560d25e7e5fa302a1e0dae971cbbb35a4c960e3276e2109fcc0`; the knob section B2b + A2 `22be5a12b8f47ed455c19b98ee90cfb30dc29914f2dc4f4e31f631644b7623c2`. Section D takes the feedback after the run, so the whole-file hash changes then; these text hashes do not. |
| **Harness** | `../harness/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/` (written after this freeze, before run 1). Uncommitted at run time (the parent session commits); md5 of each file in the run logs. |
| **Tiers and values** | Unit (B2): three builds of `MAX_SIZE` (arms K16 = 65,536, D = 1,048,576 as shipped, K24 = 16,777,216), declared lengths per A2 around and far past each M; JavaSerialization path J3/J4; positive control `UncheckedHandle` C5/C8/C9/C6. Cluster (B3 as amended by A7): the shipped distribution jar via `hadoop jar`, no daemons, `-Xmx128m`, rows R1/R3/R4/R5/R6 and controls X5/X9/X6, 1,000 iterations each. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-06 |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap bytes of the payload `byte[]` allocated per deserialized handle (`RawPathHandle.java:110`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly → Met | B2b varied only the declared length (operand sweep) and made the `1<<16` build optional. **Amended** (A2): three builds of the constant (64 KiB, 1 MiB default, 16 MiB) plus the length sweep in each. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: thread-allocated bytes (HotSpot) around `readObject`, not `len`; gap named: `len` itself is not observable outside the method. |
| A. Core question | usage driven to the limit and past it | Met | B2b: M−1, M, M+1, 16×, 2048× and −1; A2 adds a 64 MiB truncated claim. |
| A. Core question | positive control (required only for a negative estimate) | Partly → Met | B2h had the unchecked twin but mixed the truncated and genuine L5 shapes. **Amended** (A6): four control rows with numbers, one with the same input as L8. |
| B. Logic | each step says what it establishes | Met | B2c–B2h: genuine streams rule out malformed input; content check rules out empty buffers; control proves the instrument and that the workload can move heap. |
| B. Logic | prediction stated in numbers or a clear relation | Met → Met (extended) | B2f gave ranges for L0–L7; **amended** (A4) for the new arms and rows. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g lacked verdict words, the "missed bound but flat" row, the knob-does-not-move row and the invalid rows. **Amended** (A5). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met | Disallow branch observed by its exact message (B2f); ceiling-follows-knob needed the three builds (A2/A4). |
| B. Logic | alternative explanations and their controls | Met | B2h: baseline subtraction, per-thread counter, content check, genuine serializer, unchecked twin. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A3 steps 1–4, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met | B2a paths (`~/hadoop-3.4.2`, `/mydata/<you>/hadoop-s4`) do not exist; `install -am` build unnecessary. **Amended** (A1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Measurement window (with or without stream construction) and baseline per arm were unstated; B3 had "≈", "≪", "about equal" and an L1 row not in its knob list. **Amended** (A3, A7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Test class, run scripts and probe are step-1 work. JDK 8 (`1.8.0_504`), Maven 3.6.3, `~/.m2` 3.4.2 and the built distribution are present on `pc39` (checked 14:10). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Largest live arrays: K24 genuine 16 MiB+1 (source, stream ≤ 32 MiB buffer, result) ≈ 100 MiB under `-Xmx256m`; C8 64 MiB fits; C9 512 MiB is meant to OOM. Cluster: X5 = 1,000 × 16 MiB ≈ 16 GiB churn at 128m heap, seconds. Disk: < 100 MiB stream files on `/mydata`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `systems/hadoop/source/` (clean): `RawPathHandle.java:40` (constant), `:42` (transient `fd`), `:48-52`, `:58-65` (constructors), `:91-101` (`writeObject`, no check), `:103-113` (`readObject`: `readInt` 106, check 107, throw 108, alloc 110, `readFully` 111); `JavaSerialization.java:41-63` (no-header OIS); `hadoop-project/pom.xml:187, 2469`, `hadoop-common/pom.xml:1035` (argLine); `FinalizedProvidedReplica.java:55-56`, `ProvidedVolumeImpl.java:186`, `AbstractContractPathHandleTest.java:247`, `PathHandle.java:34`. All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 (A1) | Node paths, no install build, surefire options through `maven-surefire-plugin.argLine` (drops the heap-dump flag), read surefire counts | Applied 2026-11-06 (uncommitted; frozen sha256 above) | filed paths do not exist; a control OOM would otherwise dump a heap into the module |
| R2 (A2) | Vary the constant in three builds; add L8 (64 MiB truncated claim) | Applied 2026-11-06 | ≥ 3 knob values; ceiling-follows-knob; same-input comparison with the control |
| R3 (A3) | Window excludes stream construction; per-arm baseline; instrument known-answer; CSV | Applied 2026-11-06 | unambiguous reading |
| R4 (A4, A5, A6) | Numbers for every arm; verdict per row incl. missing rows; control in numbers | Applied 2026-11-06 | every plausible outcome needs a row before any reading |
| R5 (A7) | B3 n/a re-checked for daemons; run the stated `hadoop jar` alternative as the cluster tier with numeric predictions | Applied 2026-11-06 | a tier is never silently dropped; B3 as filed was not exact |
| R6 | The Estimate line's "per-handle" cap and the absence of any total bound (N × 1 MiB per stream) are correct but not tested here (no multi-object stream row) | Left for stage 3 | outside the per-call claim B1 |

**Agreement criteria** — only if run 2 is chosen (see 5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-06, 14:17–14:20 EST (node clock MST: 12:17:57–12:19:53) | not done |
| Node (CloudLab name and type) | `pc39` (`node1`, experiment `jason92-323989`, UMass), 40 cores, 251 GiB RAM | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` | |
| JDK (`java -version`) | OpenJDK `1.8.0_504` (`/usr/lib/jvm/java-8-openjdk-amd64`); default `java` on the node is 11, not used | |
| Ant (`ant -version`) | n/a (Hadoop: Maven 3.6.3) | |
| Local source copy (from `systems/hadoop/source/` at repository commit …) | `/mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/src`, `copy-source.sh` from `systems/hadoop/source/` at `38acb6bf` (clean), tag `rel/release-3.4.2`; only the test file added, `RawPathHandle.java` patched per arm and restored (`git status` after the run: the test file only) | |
| Case-file commit / harness commit | case file uncommitted, frozen sha256 `67839a92…2109fcc0` (§1); harness uncommitted, md5 `TestRawPathHandleMaxSize.java` c52090ea…, `unit-run.sh` 9b3663ec…, `analyze.py` cb5bd16b… (in `unit-run.log`); `RawPathHandleProbe.java`, `cluster-run.sh` md5 in `cluster-run.log` | |
| Storage for node data | `/mydata` (local, 708 GB free); run folder 1.5 GB (source copy, `target/`, distribution copy) | |
| Full logs (path, outside the repo) | `/mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/logs/{unit,cluster}/` (surefire output per arm, `mvn-test-<arm>.log`, GC logs per probe read) | |

Instrument checks before run 1 (not readings of any row): `unit-run.sh --compile-only` (BUILD SUCCESS, test class compiled;
`logs/unit/unit-run.compile-check.log`), and `cluster-run.sh --check` (distribution copied, `javap` of the shipped `readObject` shows
`ldc 1048576; if_icmple` before `newarray byte`, probe compiled, a 10-iteration known-answer read returned 10 objects from the
distribution jar at `-Xmx128m`; `logs/cluster/cluster-run.check.log`).

## 3. Runbook defects

None during run 1. During the instrument check (before run 1), `cluster-run.sh` failed at `javac -d` because the output directory did not
exist; the harness was fixed (`mkdir -p`) before run 1. Not a case-file defect.

## 4. Run 1

**Scope:** unit tier, arms D, K16, K24 (all rows of A2, J3/J4, controls C5/C8/C9/C6); cluster tier (A7), rows R1, R3, R4, R5, R6 and
controls X5, X9, X6, 1,000 iterations each. **Command logs:** [`RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/unit/unit-run.log`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/unit/unit-run.log),
[`RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/cluster/cluster-run.log`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/cluster/cluster-run.log).

### 4.1 Readings

**Unit tier** — b = median Δ of the arm's len = 0 row = 1,168 bytes in every arm; 25 iterations per row (20 measured; controls C9/C6: 3),
same outcome in every iteration of every row; median = min = max for every RawPathHandle row. Source: [`ifchk-all.csv`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/unit/ifchk-all.csv),
evaluated in [`analysis.txt`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/unit/analysis.txt) (141 PASS, 0 FAIL).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument (each arm) | counter supported+enabled; known answer for `new byte[1 MiB]` = 1,048,592; `maxMemory` 259,522,560; JVM args `-Xmx256m -XX:+UseSerialGC -Difchk.arm=<arm> -Difchk.max=<M>`; `MAX_SIZE` (reflection) = 1,048,576 / 65,536 / 16,777,216 | `ifchk-all.csv` (`IFCHK,instr`) |
| Arm D accepted: L0 0, L1 1,024, L2 1,048,575, L3 1,048,576, J3 1,048,576 | object, `remaining()` = len, content equal; med−b = 0, 1,024, 1,048,576, 1,048,576, 1,048,656 | `ifchk-all.csv` |
| Arm D rejected: L4 1,048,577, L5 16,777,216, L6 2^31−1, L7 −1, L8 64 MiB, J4 1,048,577 | `IOException` "Illegal buffer length <len>" (exact); med−b = max−b = 2,224 / 2,224 / 2,224 / 2,208 / 2,224 / 2,304; no OOM | `ifchk-all.csv` |
| Arm K16 (M = 65,536) | accepted 0, 1,024, 65,535, 65,536 (med−b 0, 1,024, 65,536, 65,536); rejected 65,537, **1,048,576**, 2^31−1, −1 (med−b 2,216, 2,224, 2,224, 2,208) | `ifchk-all.csv` |
| Arm K24 (M = 16,777,216) | accepted 0, 1,024, 16,777,215, **16,777,216** (med−b 0, 1,024, 16,777,216, 16,777,216); rejected 16,777,217, 64 MiB, 2^31−1, −1 (med−b 2,224, 2,224, 2,224, 2,208) | `ifchk-all.csv` |
| Largest accepted len per arm | 65,536 (K16), 1,048,576 (D), 16,777,216 (K24) = M | `analysis.txt` |
| Control C5 (unchecked, genuine 16 MiB) | object ×25, med−b 16,777,376 | `ifchk-all.csv` |
| Control C8 (unchecked, truncated 64 MiB claim; same input shape as L8) | `EOFException` ×25, med−b 67,111,048 (L8: 2,224; ratio ≈ 30,000) | `ifchk-all.csv` |
| Control C9 (unchecked, 512 MiB claim) | `OutOfMemoryError: Java heap space` ×3 | `ifchk-all.csv` |
| Control C6 (unchecked, 2^31−1 claim) | `OutOfMemoryError: Requested array size exceeds VM limit` ×3 | `ifchk-all.csv` |
| Surefire counts | D: 4/0/0/0; K16, K24: 4/0/0/2 (JavaSerialization and control tests skip outside D, as designed) | [`surefire-D.txt`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/unit/surefire-D.txt), `surefire-K16.txt`, `surefire-K24.txt` |

**Cluster tier** — shipped `hadoop-common-3.4.2.jar` of the built distribution (copy), `hadoop jar`, `-Xmx128m`, 1,000 iterations; no daemons, no ports.
Source: [`probe-results.csv`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/cluster/probe-results.csv), evaluated in [`analysis.txt`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/cluster/analysis.txt) (34 PASS, 0 FAIL).

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| MAX_SIZE 1 MiB (shipped) | R1 g 1,024 keep | outcomes; total allocated; VmHWM | 1,000 objects kept, content ok; total 4,888,680 B; VmHWM 119,436 kB | `probe-results.csv` |
| same | R3 g 1,048,576 | same | 1,000 objects; total 1,052,425,896 B (= 1,000 × 1,052,426); VmHWM 124,536 kB; 35 young GCs | `probe-results.csv`, `gc-R3.log` (node) |
| same | R4 g 1,048,577 | same | 1,000 `IOException` "Illegal buffer length 1048577"; total 5,089,872 B; VmHWM 116,252 kB; no OOM | `probe-results.csv` |
| same | R5 g 16,777,216 | same | 1,000 `IOException` "… 16777216"; total 5,090,360 B; VmHWM 129,892 kB (the 16 MiB stream file is held in memory) | `probe-results.csv` |
| same | R6 p 2^31−1 | same | 1,000 `IOException` "… 2147483647"; total 5,089,680 B; VmHWM 116,092 kB; no OOM | `probe-results.csv` |
| unchecked control | X5 g 16,777,216 | same | 1,000 objects; total 16,781,034,688 B; 510 young GCs | `probe-results.csv`, `gc-X5.log` (node) |
| unchecked control | X9 p 512 MiB | OOM | `OutOfMemoryError: Java heap space` at iteration 1 (2 full GCs before it) | `probe-results.csv`, `gc-X9.log` (node) |
| unchecked control | X6 p 2^31−1 | OOM | `OutOfMemoryError: Requested array size exceeds VM limit` at iteration 1 | `probe-results.csv` |
| — | all reads | code source, heap | `file:<run>/hadoop/share/hadoop/common/hadoop-common-3.4.2.jar`; `maxMemory` 128,974,848–133,693,440 (≤ 128 MiB); shipped bytecode `ldc 1048576; if_icmple` before `newarray` | `probe-results.csv`, [`javap-readObject.txt`](RawPathHandle_MAX_SIZE-readObject-MAX_SIZE--autonomous/run1/cluster/javap-readObject.txt) |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. Instrument check passed in each arm (known answer 1,048,592 ∈ [1,048,576, 1,052,672]; `-Xmx256m` applied; `MAX_SIZE` = M) [observed: `ifchk-all.csv`]. Each arm compiled the patched source: reflection read the arm's M, and the `git diff` in the log shows the one-line patch and its undo [observed: `unit-run.log`]. All four controls moved [observed: `ifchk-all.csv`]. Surefire 4/0/0/0 and 4/0/0/2 [observed: `surefire-*.txt`].
2. **Readings** — nothing unusual. Every row's 20 measured deltas are identical (median = min = max) except C5 (max−b 16,787,368, 10 KB above its median, one iteration) [observed: `ifchk-all.csv`]. Accepted rows give med−b = len rounded up to 8 bytes (65,535 → 65,536; 16,777,215 → 16,777,216): the array header is in the baseline (L0 allocates a `byte[0]`) [inferred: object alignment, same 16-byte header in both].
3. **Matched row** — A5 row 1: "Every A4 reading holds in all three arms and J3/J4; the A6 controls move → Confirmed — caps". Accepted iff 0 ≤ len ≤ M in every arm, with med−b ∈ [len, len+4,096]; every rejected row throws `IOException` "Illegal buffer length <len>" with med−b ≤ 2,304 < 65,536 and no OOM; the largest accepted len equals M for M = 65,536 / 1,048,576 / 16,777,216 (ceiling follows the knob); C5 ≥ 16 MiB, C8 ≥ 64 MiB and ≥ 1,000 × L8, C9/C6 OOM [observed: `analysis.txt`, 141 PASS / 0 FAIL].
4. **Excluded rows** — row 2 (flagged overhead): every rejected med−b < 65,536. Row 3 (flagged accepted): every accepted med−b ≤ len + 80. Row 4 (**Refuted — does not cap**): no len > M returned an object, the largest rejected med−b is 2,304 (≪ min(len/2, 1 MiB)), no OOM on any RawPathHandle row. Row 5 (**Refuted**, boundary): len = M accepted and M+1 rejected in all arms. Row 6 (Not confirmed): the boundary moved with M. Rows 7–8 (Invalid): instrument and controls passed, sentinel unique (no assertion failure), outcomes stable [observed: `ifchk-all.csv`, `surefire-*.txt`].
5. **Observed vs. inferred** — the conclusion rests on observed values; the one inference is that thread-allocated bytes count the payload array (supported by the known answer 1,048,592 for a 1 MiB array and by C5/C8 tracking len).
6. **Deviations and gaps** — none from the frozen runbook. The unit tier runs the module's compiled classes (`target/classes`), not the jar; the cluster tier covers the shipped jar. Not tested (outside B1): the total across many handles in one stream (R6 of the audit).
7. **Core question** — usage follows the constraint: the per-call payload allocation is the declared length up to `MAX_SIZE` and ≈ 2.2 KB (the exception) above it, and the boundary sits at `MAX_SIZE` for each of the three builds (parts 3, 4). The disallow branch fired with its exact message (part 3), and the unchecked twin allocates 64 MiB on the same input where the check allocates 2.2 KB (part 3). The constraint caps per-handle deserialization heap.

**Conclusion (one line):** A5 row 1 (B2g) — confirmed: `MAX_SIZE` caps the per-handle deserialization buffer.

**Cluster tier**

1. **Validity** — valid: code source is the distribution's `hadoop-common-3.4.2.jar` in every read, heap ≤ 128 MiB, shipped bytecode has the check, controls X5/X9/X6 moved [observed: `probe-results.csv`, `javap-readObject.txt`, `analysis.txt`].
2. **Readings** — VmHWM of R5 (129,892 kB) is 13.6 MB above R4's because the probe holds the 16 MiB stream file; R6 (74 KB stream) is equal to R4 within 160 kB [observed: `probe-results.csv`]. Per-iteration overhead ≈ 4.9–5.1 KB (stream creation + exception) [inferred: total / 1,000].
3. **Matched row** — A7 "All predictions hold → Confirmed — caps": R1 total 4,888,680 ∈ [1,024,000, 66,560,000]; R3 1,052,425,896 ∈ [1,048,576,000, 1,114,112,000]; R4/R5/R6 1,000 `IOException`s with the exact message, totals ≈ 5.09 MB < 67,108,864, no OOM; VmHWM(R6) ≤ VmHWM(R4) + 32 MiB; X5 16,781,034,688 ≥ 16,777,216,000; X9, X6 OOM at iteration 1 [observed: `analysis.txt`, 34 PASS / 0 FAIL].
4. **Excluded rows** — Refuted (does not cap): no R4–R6 object, totals ≈ 5 KB/iteration ≪ 1,000 × min(len/2, 1 MiB), no OOM. Refuted (boundary): R3 accepted, R4 rejected. Flagged: no bound missed. Invalid: code source, heap and controls as required [observed: `probe-results.csv`].
5. **Observed vs. inferred** — all observed; GC counts (R3 35 young GCs, R4/R6 1, X5 510) independently corroborate the allocation totals [observed: GC logs on the node].
6. **Deviations and gaps** — none from A7. The knob is not varied in this tier (shipped constant), as A7 states; no daemon path exists to exercise (A7 re-check).
7. **Core question** — with the shipped jar, 1,000 reads of a 1 MiB handle allocate 1.05 GB while 1,000 reads claiming 1 MiB+1, 16 MiB or 2 GiB allocate 5 MB in total and never OOM, whereas the unchecked twin allocates 16.8 GB for 16 MiB and OOMs on 512 MiB and 2 GiB claims. The cap holds in the distribution.

**Conclusion (one line):** A7 / B3g "All predictions hold" — confirmed: caps.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-read on the node (2026-11-06, after the run): the raw surefire output files, not the derived CSV, and the GC logs.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `surefire-<arm>.txt`: 4/0/0/0, 4/0/0/2, 4/0/0/2. `IFCHK,instr` lines in the raw `surefire-output-<arm>.txt` show `-Xmx256m`, `MAX_SIZE` = M. `unit-run.log` shows the patch diff before K16/K24 and an empty `git diff --stat` after each restore. `probe-results.csv`: code source and `maxMemory` per read. |
| 2. Readings | yes | The `IFCHK` lines grepped from each raw `surefire-output-<arm>.txt` are byte-identical to `ifchk-<arm>.csv` (md5 6e0fab2e…, 6206a9d1…, 51ab90d0…); six "Illegal buffer length" messages in arm D's raw output (L4–L8, J4), as listed. |
| 3. Matched row | yes | Re-derived by hand from `ifchk-all.csv`: largest accepted len per arm = M; max rejected med−b 2,304; C8/L8 = 67,111,048 / 2,224. `analysis.txt` 0 FAIL in both tiers. |
| 4. Excluded rows | yes | No RawPathHandle row has outcome `object` with len > M or an `Error` class; boundary rows KM/KMp1, L3/L4 as stated. |
| 5. Observed vs. inferred | yes | Counter inference checked against independent GC logs: `gc-R3.log` 35 young GCs, `gc-R4.log`/`gc-R6.log` 1 (startup), `gc-X5.log` 510, `gc-X9.log` 2 full GCs before the OOM. |
| 6. Deviations and gaps | yes | No step skipped; instrument-check runs are logged separately (`*.check.log`, `*.compile-check.log`) and contribute no reading. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Ceiling follows the knob (three builds) + direct disallow evidence (message) + control moving on the same input — the A5 row 1 conjunction. |

### 5.2 Run 2?

**No** — 2026-11-06. The conclusion rests on observed readings (one corroborated inference), every self-check part holds, and the result
confirms the case's own claim (no refutation, no bypass confirmed). Readings are deterministic (median = min = max).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps).

**Claim tested:** (B1) Java-deserializing a `RawPathHandle` allocates a payload `byte[]` of exactly the declared length when
0 ≤ len ≤ 1,048,576, and for any declared length outside that range allocates no payload array and throws
`IOException("Illegal buffer length <len>")`. "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g/A5 row 1 (ceiling = `MAX_SIZE` in three builds: 64 KiB, 1 MiB, 16 MiB; rejected calls allocate ≈ 2.2 KB; exact disallow message) | caps | run 1 + self-check | 2026-11-06 |
| Cluster | **Confirmed** — B3g/A7 "all predictions hold" (shipped jar, `-Xmx128m`, 1,000 reads per row) | caps | run 1 + self-check | 2026-11-06 |

**Positive control** (required only for a negative estimate; run here as A6/A7): the unchecked twin allocated 16,777,376 B per
genuine 16 MiB read (unit) and 16.78 GB over 1,000 reads (cluster), 67,111,048 B on the truncated 64 MiB claim where `RawPathHandle`
allocated 2,224 B, and threw `OutOfMemoryError` on 512 MiB and 2^31−1 claims in both tiers.

**Scope of the cap.** Per handle, per `readObject` call only: the constructors (`RawPathHandle.java:48-65`) and the total over many
handles in one stream are not bounded (A3 step 4), and no stock daemon Java-deserializes a `RawPathHandle` (A7).

**Feedback filed:** the case file's section D (D2, 2026-11-06, uncommitted; the parent session commits) — no section amended by the
result (A1–A7 are the audit's, before the freeze).

**Left on the node `pc39`:** `/mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/` (1.5 GB: `src/` with the test
file and `target/`, `hadoop/` distribution copy, `probe/` with `probe.jar` and classes — stream files deleted —, `logs/`, `tmp/`,
`pids/` empty). No process: no surefire JVM, no probe JVM, no Hadoop daemon of this case (checked with `ps`/`jps` after the run;
the `s3proxy` JVM on the node belongs to the other Jingsong case). Undo: `rm -rf /mydata/jingsong-s4/RawPathHandle_MAX_SIZE-readObject-MAX_SIZE-run1/`.
