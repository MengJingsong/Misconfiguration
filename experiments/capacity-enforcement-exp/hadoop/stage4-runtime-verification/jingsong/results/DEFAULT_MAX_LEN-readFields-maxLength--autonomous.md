# DEFAULT_MAX_LEN-readFields-maxLength--autonomous — stage-4 results  <!-- file: results/DEFAULT_MAX_LEN-readFields-maxLength--autonomous.md -->

> **Case:** [`DEFAULT_MAX_LEN-readFields-maxLength--autonomous`](../../../stage3-ai-deep-read/jingsong/cases/DEFAULT_MAX_LEN-readFields-maxLength--autonomous.md) (Jingsong's queue, order 7; `Text.java:357`)
>
> **Status:** verdict filed (run 1 + self-check; no run 2) — 2026-11-25
>
> **Outcome class:** true positive — estimate `positive`, effect `caps` on both tiers
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the feedback field is section D.

Written outside the repository (stage-4 worker for Jingsong, node `pc82`). Paths below are relative to
`~/writeup-hadoop/out/o7/`: `run1/` holds the small logs copied off the node, `harness/` the instruments,
`case-amended.md` the case file with the dated amendments and section D filled.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository commit `cd9e1cded` holds the file as filed (sha256 `0a2eabc8…a258ddf`, as in `_INDEX.md`). After the audit's amendments A1–A2 (unit tier and first cluster attempt ran on this version): sha256 `41aba02c81b1f0378c00b26a05d2c879d8789384cffb78ed6213ac9da2f0b2b9`. After runbook-defect fix A3 (cluster tier restarted on this version): sha256 `8755de1ce16ff8ea0eb5396fec8ff072a9d8f5693c0750376c879c128a5c797d` — the frozen version for `_INDEX.md`. Section D was filled after that (feedback only). |
| **Harness** | `harness/unit/TestTextMaxLenProbe.java`, `harness/unit/run-unit.sh`; `harness/cluster/NnTokenProbe.java`, `harness/cluster/JfrCount.java`, `harness/cluster/run-cluster.sh`. Not committed (the run was told not to edit the repository); to be placed under `hadoop/stage4-runtime-verification/jingsong/harness/DEFAULT_MAX_LEN-readFields-maxLength--autonomous/` when filed. |
| **Tiers and values** | Unit: `maxLength` M ∈ {1024, 1048576, 67108864} × claimed L ∈ {M−1, M, M+1, 1 GiB}; real caller (web `DelegationTokenIdentifier`) owner L ∈ {524288, 1048575, 1048576, 1 GiB}; writer/reader mismatch; uncapped control L ∈ {256 MiB, 1 GiB}; 5 reps each, `-Xmx512m`. Cluster: NameNode only, `-Xmx512m`, G1 1 MiB regions, `cancelDelegationToken` with A = 8 and L ∈ {600000 ×200, 1048575 ×200, 1048576 ×200, 1073741824 ×5}. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-25 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap bytes of the `byte[]` that `readWithKnownLength` allocates per field. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: constant, not settable. B2b varies the `maxLength` argument (1024, 1 MiB = default, 64 MiB) on the same code; the real caller is held at the default and the claim is varied. B3 varies the claim against the fixed cap (stated reason: constant). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d thread-allocated bytes; B3d JFR allocation events + GC log + heap_info. Gap named (B2d/B3d "not directly observable"). |
| A. Core question | usage driven to the limit and past it | Met | L = M−1, M, M+1, 1 GiB (B2b); 1048575/1048576/1 GiB (B3b). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps; B2h/B3h say what each control rules out. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f tables with sizes, messages and thresholds (< 64 KiB). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g: confirmed, allocation ≥ L or OOM above cap (refuted), off-by-one, rejection with large allocation, control not moving / below-cap arms 0 events (not confirmed), RPC not reaching the check. "Flat across values" is covered by the bound-follows-M row. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Allocation ≈ L below M for three M; the `maxLength = M` message is the disallow evidence (B2f/B3f). |
| B. Logic | alternative explanations and their controls | Met | B2h uncapped control (short input alone does not prevent the allocation), baseline, three M; B3h below-cap arms as positive control, fixed A, message ties rejection to this line not the IPC limit. |
| C. Specific | a human can follow it from the intro and §9a | Met | B1 + B2f/B3f. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Exact byte layouts, classes, call chain with lines. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B2a uses `-am install` and B3a a fresh dist build where the node already has the equivalent build (A1, A2); B3d did not say how the class name appears through the JFR consumer API (found in run 1, A3). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Probe classes listed as step-1 work (B2e.2, B3a); JDK 8 + JDK 11 (with `jcmd`, `jfr`) present on `pc82`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 1 GiB claim > 512 MiB heap in both tiers; 64 MiB stream fits 512 MiB; 200 × 1 MiB humongous allocations collectable. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `systems/hadoop/source`: Text.java:346-362 (both overloads, check at 357), 319-335 `ensureCapacity`, 383-388 `readWithKnownLength`, 549 `DEFAULT_MAX_LEN`; AbstractDelegationTokenIdentifier.java:190-198 and 219-227; AbstractDelegationTokenSecretManager.java:654-659 (`readFields` before any owner check); FSNamesystem.java:6402-6420; NameNodeRpcServer.java:781-784; hadoop-project/pom.xml:187, 2469. Run 1's server stacks match these lines (`run1/cluster/jfr-sample-stack-1048575.txt`). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: skip `-am install`; run `mvn -pl hadoop-common test` against the node's `~/.m2` 3.4.2 artifacts (environment.md §3) | Applied, A1 (2026-11-25, `case-amended.md` B2a) | Same source; avoids overwriting the shared `~/.m2` build. |
| 2 | B3a: use a `cp -a` copy of the node's base distribution; set `HADOOP_PID_DIR` under the run folder; write `hadoop.security.authentication=simple` | Applied, A2 (2026-11-25, B3a) | Environment rules (environment.md §4); keeps all state in the run folder. |
| 3 | B2d: measure the baseline on the same call type as each arm (an exception baseline for rejected arms) | Left for stage 3; harness measured an `L = 0` baseline per call type (direct, identifier, uncapped) | The < 64 KiB threshold absorbs exception cost either way. |
| 4 | B3f: sizes are JVM-aligned (`16 + L` rounded up to 8) | Left for stage 3 | "≈" in B3f already covers 1048591 vs 1048592. |

**Agreement criteria** — not applicable (no run 2).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-25 (unit 02:06–02:06:38 MST; cluster attempt 0 02:07–02:08:25; cluster run 02:09–02:09:33) |
| Node | `pc82` (`node1.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu`), 40 cores, 125 GiB RAM; node lock `/mydata/s4/NODE-LOCK` held throughout |
| OS and kernel | Ubuntu 22.04, `5.15.0-203-generic` |
| JDK | Unit: OpenJDK `1.8.0_514` (build + surefire). Cluster: NameNode, probe and JFR counter on OpenJDK 11 (`/usr/lib/jvm/java-11-openjdk-amd64`, `jcmd`/`jfr` present), as B3a specifies |
| Build tool | Maven 3.6.3 |
| Local source copy | `copy-source.sh` from `systems/hadoop/source` at repository commit `cd9e1cded` → `/mydata/jingsong-s4/DEFAULT_MAX_LEN-readFields-maxLength--autonomous-run1/hadoop-src` (`rel/release-3.4.2`, `git status` clean before and after) |
| Distribution (cluster) | `cp -a` of `/mydata/jingsong-s4/hadoop-base/hadoop-dist/target/hadoop-3.4.2` (built 2026-11-24, BUILD SUCCESS) |
| Case-file commit / harness | `cd9e1cded` / harness outside the repo (`harness/`) |
| Storage | `/mydata` (local, 656 GB free); nothing on `/proj` |
| Full logs | `run1/` here (1.7 MB); on the node only `/mydata/jingsong-s4/DEFAULT_MAX_LEN-readFields-maxLength--autonomous-run1/` small logs (2.2 MB) remain; the source copy, distribution copy, name/tmp dirs and JFR files on the node were deleted |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | Run 1, cluster attempt 0 | B3d / B3e.3 | The harness counter `JfrCount` filtered `objectClass` by the name `byte[]`; through `jdk.jfr.consumer`, `RecordedClass.getName()` is `[B`. All arms read 0 matching events, including the below-cap positive-control arms — B3g row "below-cap arms show 0 events → instrument not seeing the allocation; not confirmed — fix before reading the at-cap arms" (`run1/attempt0-instrument-defect/cluster/readings.txt`). `jfr print` on the same file showed 200 `byte[]` events of 586 kB. | `JfrCount` accepts `[B` or `byte[]`. Known-answer check on attempt 0's recordings: 200/200 events via `Text.readWithKnownLength` in the below-cap arms, sizes 600016 and 1048592 (`run1/instrument-check/jfrcount-recheck-of-aborted-attempt.txt`). Case file B3d clarified (A3). | Cluster tier restarted from B3e.1 (fresh format, new NameNode) — 2026-11-25. Attempt 0 is not used as evidence. B3f/B3g unchanged. | sha256 `8755de1c…5c797d` |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** `run1/unit/run-unit.log` (+ `run1/unit/mvn-test.log`),
`run1/cluster/run-cluster.log` (= `run1/cluster-driver.out`).

### 4.1 Readings

**Unit tier** (median of 5 reps; `net` = allocated bytes minus the `L = 0` baseline of the same call type; every rep is listed in `run1/unit/probe-lines.txt`; spread across reps ≤ 272 bytes except where noted)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Baselines (`L = 0`) | direct 552 B; identifier 656 B; uncapped 552 B | `run1/unit/probe-lines.txt` `BASELINE` |
| M = 1024: L = 1023 complete | OK, length 1023; net 1064 B | `SUMMARY directLimit M=1024 L=1023` |
| M = 1024: L = 1024 / 1025 / 1 GiB (A = 8) | `IOException: tried to deserialize <L> bytes of data, but maxLength = 1024`; net 1880 / 1880 / 1904 B | `SUMMARY directLimit M=1024 …` |
| M = 1048576: L = 1048575 complete | OK, 1048575; net 1048632 B | `SUMMARY directLimit M=1048576 L=1048575` |
| M = 1048576: L = 1048576 / 1048577 / 1 GiB | `IOException … maxLength = 1048576`; net 1904 / 1904 / 1928 B | `SUMMARY directLimit M=1048576 …` |
| M = 67108864: L = 67108863 complete | OK, 67108863; net 67108920 B | `SUMMARY directLimit M=67108864 L=67108863` |
| M = 67108864: L = 67108864 / 67108865 / 1 GiB | `IOException … maxLength = 67108864`; net 1928 / 1928 / 2232 B; no OOM | `SUMMARY directLimit M=67108864 …` |
| Real caller, owner 524288 / 1048575 complete | OK, owner length 524288 / 1048575; net 524344 / 1048632 B | `SUMMARY realCaller …` |
| Real caller, owner 1048576 / 1 GiB (A = 8) | `IOException: tried to deserialize 1048576 (resp. 1073741824) bytes of data, but maxLength = 1048576`; net 1904 / 1928 B; no OOM | `SUMMARY realCaller …` |
| Writer/reader mismatch, owner = 1048576 bytes | `write()` OK (1048589 bytes written); `readFields` → `IOException … 1048576 bytes of data, but maxLength = 1048576`; alloc 2560 B | `MISMATCH` line |
| Control: uncapped `readFields(DataInput)`, L = 256 MiB, A = 8 | `EOFException`; net 268436568 B (= 256 MiB + 344 B), all 5 reps | `SUMMARY uncappedControl … L=268435456` |
| Control: uncapped, L = 1 GiB, A = 8 | `OutOfMemoryError: Java heap space`, all 5 reps | `SUMMARY uncappedControl … L=1073741824` |
| Surefire | 4 tests run, 0 failures/errors; BUILD SUCCESS; no `.hprof` written | `run1/unit/mvn-test.log`, `run1/unit/run-unit.log` |

**Cluster tier** (NameNode pid 1237153 throughout; `-Xms512m -Xmx512m -XX:+UseG1GC -XX:G1HeapRegionSize=1m` confirmed by `jcmd VM.command_line`/`VM.flags` in `run1/cluster/run-cluster.log`)

| Claimed L | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 600000 | positive control (below cap) | client tally | 200 × `java.io.EOFException` | `run1/cluster/readings.txt`, `probe-600000.log` |
| 600000 | | JFR `byte[]` ≥ 500000 via `Text.readWithKnownLength` | 200 events, all size 600016; 0 other large `byte[]` | `jfrcount-600000.txt` |
| 1048575 | positive control (largest accepted) | client tally | 200 × `java.io.EOFException` | `readings.txt`, `probe-1048575.log` |
| 1048575 | | JFR | 200 events, all size 1048592; stack `ensureCapacity:331 ← readWithKnownLength:384 ← readFields(DataInput,int):361 ← AbstractDelegationTokenIdentifier.readFields:196 ← AbstractDelegationTokenSecretManager.cancelToken:659 ← FSNamesystem.cancelDelegationToken:6414 ← NameNodeRpcServer:784` | `jfrcount-1048575.txt`, `jfr-sample-stack-1048575.txt` |
| 1048575 | | GC log | 6 new "humongous" lines during the arm (e.g. `Pause Young (Concurrent Start) (G1 Humongous Allocation)`) | `readings.txt`, `gc-humongous-excerpt.txt` |
| 1048576 | at cap | client tally | 200 × `java.io.IOException: tried to deserialize 1048576 bytes of data, but maxLength = 1048576` | `readings.txt`, `probe-1048576.log` |
| 1048576 | | JFR | 0 large `byte[]` events (7 outside-TLAB events in total, none ≥ 500000 B) | `jfrcount-1048576.txt` |
| 1073741824 | 2 × NN heap | client tally | 5 × `IOException: tried to deserialize 1073741824 bytes of data, but maxLength = 1048576` | `readings.txt`, `probe-1073741824.log` |
| 1073741824 | | JFR | 0 outside-TLAB events at all | `jfrcount-1073741824.txt` |
| 1073741824 | | heap used after arm | 263544 K (262520 K after the 1048576 arm): +1 MiB, noise | `heap-after-1048576.txt`, `heap-after-1073741824.txt` |
| all | | NN health | NN alive (same pid) after every arm; 0 `OutOfMemoryError` lines in NN logs; 205 NN log entries "tried to deserialize" (200 + 5) | `readings.txt`, `run-cluster.log` |

### 4.2 Conclusion and logic

1. **Validity.** Unit: the limit was reached and passed for every M (L = M−1, M, M+1, 1 GiB) [observed: `run1/unit/probe-lines.txt`]; the 512 MiB test heap is in force, since the 1 GiB uncapped allocation threw `OutOfMemoryError` while the 256 MiB one succeeded, which the default `-Xmx2048m` would not do [observed: `probe-lines.txt`; inferred: from the default in hadoop-project/pom.xml:187]. Each case used fresh `Text`/identifier objects (B2h.4) [observed: harness source]. Cluster: same NN pid across arms, safe mode OFF before the arms, A = 8 in every arm (`identifierBytes` 13–14) [observed: `run-cluster.log`, `probe-*.log`]; the RPC reached the check in every call (server stacks pass through `cancelToken:659` → `readFields:196`) [observed: `jfr-sample-stack-1048575.txt`, NN log stack in `run1/logs/…namenode….log.gz`]. Valid.
2. **Readings.** No gaps or outliers. Rejected-arm allocations are 1.9–2.2 KiB net, far under the 64 KiB threshold [observed: `probe-lines.txt`]. The cluster's 1048575 arm shows JFR sizes of 1048592 rather than the predicted ≈ 1048591 — object alignment [inferred: 16-byte array header + L rounded up to 8]. The GC-log humongous delta for the 600000 arm is 0 although JFR shows 200 humongous-sized allocations: no young GC fell inside that arm, and the GC log only reports humongous regions at a GC [inferred: GC log prints "Humongous regions" per pause]; the GC log is secondary in B3d, JFR is primary.
3. **Matched row.** Unit (B2g): "Allocation ≈ L below the limit, < 64 KiB at/above it, for all three M — claim confirmed; the bound moves with maxLength": below the limit net ≈ L for M = 1024 (1064 vs 1023), 1 MiB (1048632 vs 1048575), 64 MiB (67108920 vs 67108863) and for the real caller (524344 / 1048632); at/above the limit < 2.3 KiB for all three M and the real caller, with the `maxLength = M` message [observed: `probe-lines.txt`]. Cluster (B3g): "Events ≈ count at sizes ≈ L below the cap; 0 at/above; NN alive — claim confirmed on the daemon": 200/200 events at 600016 and 1048592 B; 0 events at 1048576 and 1 GiB; NN alive, no OOM [observed: `jfrcount-*.txt`, `readings.txt`].
4. **Excluded rows.** Unit: "Allocation ≈ L (or OOM) for some L ≥ M" (Refuted) — excluded, every L ≥ M arm < 2.3 KiB, no OOM in any capped arm. "L = M−1 rejected" (Refuted) — excluded, L = M−1 succeeded for all three M and the real caller (1048575). "Rejection, but allocation ≫ 64 KiB" (Refuted) — excluded, max 2232 B. "Uncapped control does not allocate ≈ 256 MiB / OOM" (Not confirmed) — excluded, 268436568 B and OOM. Cluster: "Events or OOM in the 1048576 / 1 GiB arms" (Refuted) — excluded, 0 events, 0 OOM lines. "1048575 arm rejected with the maxLength message" (Refuted) — excluded, 200 × EOFException. "Below-cap arms show 0 events" (Not confirmed) — excluded in the restarted run (200 each); it was the reading of attempt 0, caused by the counter (defect 1), not used. "Messages other than EOF/maxLength" — excluded, only those two messages in the tallies.
5. **Observed vs. inferred.** The conclusion depends on: (a) the surefire JVM ran with 512 MiB (inferred from the control's OOM; strong — no other explanation for a 1 GiB allocation failing under the 2 GiB default with nothing else live); (b) the thread-allocated-bytes delta is dominated by the single `byte[L]` (inferred from size: net − L ≤ 57 B in every accepted arm); (c) JFR outside-TLAB events capture every allocation ≥ 512 KiB under 1 MiB regions (observed: 200/200 in both below-cap arms, matching the call count exactly).
6. **Deviations and gaps.** A1/A2 (prebuilt artifacts and distribution from the same source; no effect on the code under test). Cluster tier restarted once after defect 1; attempt 0's readings agree with the restarted run once re-counted (`instrument-check/`), but only the restarted run is evidence. Not observed: per-call allocation outside JFR's ≥ 500000 B filter (other RPC buffers) — irrelevant to the claim because A is fixed. The bypasses in A3 (uncapped `readFields(DataInput)`, per-field rather than per-identifier cap, protobuf YARN identifiers) are outside B1's claim; the uncapped control shows the first bypass would allocate the claim in full.
7. **Core question.** Usage follows the constraint: below the cap the heap allocated for the field equals the claimed length (unit, three values of M; daemon, 600000 vs 1048575 → 600016 vs 1048592 B per call) (parts 3, 1), and at or above the cap nothing is allocated — the `maxLength = M` rejection fires before `ensureCapacity`, even for a 1 GiB claim against a 512 MiB heap, where the same input through the uncapped overload allocates 256 MiB or throws OOM (parts 3, 4, B2h). So `Text.DEFAULT_MAX_LEN` caps the per-field identifier allocation at < 1 MiB, in the unit and on a running NameNode's `cancelDelegationToken` path.

**Conclusion (one line):** Unit — B2g row 1 "claim confirmed; the bound moves with maxLength" — **Confirmed**. Cluster — B3g row 1 "claim confirmed on the daemon" — **Confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `run1/unit/probe-lines.txt` (OOM 5/5 at 1 GiB uncapped, EOF + 268436568 B at 256 MiB); `run1/cluster/run-cluster.log` (`MaxHeapSize=536870912`, `G1HeapRegionSize=1048576`, safe mode OFF, NN pid 1237153 in every "NN alive" line); `probe-*.log` `identifierBytes=13/14`. |
| 2. Readings | yes | `jfrcount-1048575.txt` "SIZE 1048592 x200", `jfrcount-600000.txt` "SIZE 600016 x200"; `readings.txt` gcLogHumongousLinesDelta 0/6/0/0. |
| 3. Matched row | yes | `SUMMARY` lines re-read for all 3 M and the real caller; cluster tallies and JFR counts re-read per arm. |
| 4. Excluded rows | yes | Max net in rejected arms is 2232 B (M = 64 MiB, L = 1 GiB); no `OutOfMemoryError` outside the uncapped control (6 matches = 5 PROBE + 1 SUMMARY, all `uncappedControl`); `readings.txt` "OutOfMemoryError lines in NN logs: 0". |
| 5. Observed vs. inferred | yes | (a)–(c) as stated; (c) checked by the exact 200/200 counts, which also confirm the defect-1 fix. |
| 6. Deviations and gaps | yes | Attempt 0 kept under `run1/attempt0-instrument-defect/` and labelled not-evidence; re-count in `run1/instrument-check/`. |
| 7. Core question | yes | Follows B1: allocation follows claim below cap, none at/above, controls move. |

### 5.2 Run 2?

**No** — 2026-11-25. The conclusion rests on direct observations (allocation byte counts, JFR events with stacks, error messages), both tiers agree, the result neither refutes the case nor confirms a bypass, and every self-check part holds from run 1's files.

## 6. Run 2 — not done

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps on both tiers).

**Claim tested (B1):** When an `AbstractDelegationTokenIdentifier` is deserialized, the heap allocated for its owner field follows the claimed length up to 1048575 bytes and is not allocated at all for a claimed length ≥ 1048576 (`Text.DEFAULT_MAX_LEN`), however large the claim; in a running NameNode, a 1 GiB claim in a cancel-token RPC is rejected with the `maxLength = 1048576` message and causes no ~1 GiB allocation or `OutOfMemoryError`.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (bound moves with `maxLength`: net ≈ L below M for M = 1024 / 1 MiB / 64 MiB, < 2.3 KiB at/above; uncapped control 256 MiB / OOM) | caps | run 1 + self-check | 2026-11-25 |
| Cluster | Confirmed — B3g row 1 (200/200 JFR `byte[]` allocations via `Text.readWithKnownLength` at 600016 / 1048592 B below the cap; 0 at 1048576 and 1 GiB; NN alive, no OOM) | caps | run 1 + self-check (after one restart for harness defect 1) | 2026-11-25 |

**Positive control:** not required (positive estimate); present anyway — B2h uncapped overload (256 MiB allocated, 1 GiB OOM) and B3h below-cap arms.

**Feedback filed:** `case-amended.md` — amendments A1 (B2a), A2 (B3a), A3 (B3d, from defect 1) and section D filled. Not written to the repository (this run was told not to edit it); to file: copy `case-amended.md` over the case file, this file to `hadoop/stage4-runtime-verification/jingsong/results/DEFAULT_MAX_LEN-readFields-maxLength--autonomous.md`, small logs to `results/DEFAULT_MAX_LEN-readFields-maxLength--autonomous/run1/`, `harness/` to `harness/DEFAULT_MAX_LEN-readFields-maxLength--autonomous/`, and update the `_INDEX.md` row (stage 4: Confirmed — caps (unit + cluster), TP; sha256 `8755de1c…`), `queue.csv` order 7 and `FLOWCHART.md` counts.
