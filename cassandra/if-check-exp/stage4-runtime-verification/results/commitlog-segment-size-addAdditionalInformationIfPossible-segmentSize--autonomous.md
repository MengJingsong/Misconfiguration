# commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous — stage-4 results  <!-- file: results/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous.md -->

> **Case:** [`commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous`](../../stage3-ai-deep-read/cases/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous.md)
>
> **Status:** verdict filed (2026-10-26), run 1 only, self-checked, no run 2
>
> **Outcome class:** true negative (estimate negative; stage-4 effect: does not cap). Unit tier Confirmed; cluster tier Confirmed in the standard (LZ4) arms, not confirmed in the default mmap arms (node killed by SIGBUS first).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file is untracked in the repository (written by the stage-3 autonomous agent; repository HEAD at audit time `93d6365`). sha256 of the whole file after the audit's amendments (D-R1, D-R3, D-R4, D-R5, all 2026-10-26): `9d2e596a600a2dbb205e43c4a244a2db9c07852d631581d907e344e489733cd8`. sha256 of the prediction and conclusion tables, frozen before any reading: B2f..B2g (from `**B2f.` up to `**B2h.`, exclusive) `ae3784e4b65cb45d805d1119c50f6ec13a7fdf5c51b576cdc03e972fcab1487b`; B3f..B3g (from `**B3f.` up to `**B3h.`, exclusive) `c2ce917ee7ced6c30c7b1d66aa55e9b520bd8816947522117f5faec26abbe724`. After the run only section D received text (the verdict and notes); the whole-file sha256 is then `fef07b3f5fcdc3a21c4fb3c3719ac0ce5432c94fa6449a1c7f755b20912a435e`, and both table hashes were re-computed unchanged. |
| **Harness** | `harness/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous/`: `SgAddInfoProbeTest.java`, `unit-run.sh`, `cluster-run.sh`, `analyze.py`, `selfcheck.py`, `README.md`. Uncommitted at the time of writing (the orchestrator commits). |
| **Tiers and values** | Unit: `commitlog_segment_size` 8, 16, 17, 32, 1024, 2047 MiB (B2b's four plus the 16/17 MiB boundary) on a 4 GiB tmpfs and a 16 MiB tmpfs, each empty and full; nonexistent paths; `handleCommitError` under `stop_commit` and `ignore`; positive control = segment file length at 8, 32, 64 MiB. Cluster: arms A1..A5 (64/16 MiB commit-log tmpfs, 32 or 8 MiB segments, mmap or LZ4, filler leaving 4 or 2 MiB or none) and Z32, Z8 (1 GiB tmpfs, no filler; positive control of the cap that binds). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: disk bytes of one segment file; the operand is a byte count from `FileStore`. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 8, 32 (default), 1024, 2047 MiB; amendment adds 16 and 17 MiB. The cluster tier varies 8 and 32 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d compares the operand with `df`; B3d uses `df`, `du`, `TotalCommitLogSize`. The internal `unallocatedSpace` is only visible through the logged number (named in B3d). |
| A. Core question | usage driven to the limit and past it | Partly | B3c's "third segment cannot be allocated" argument is wrong for mmap (sparse segments, `MemoryMappedSegment.java:62`). Fixed by D-R3 (filler leaving 4 or 2 MiB free). |
| B. Logic | each step says what it establishes | Met | B2e and B3e give the purpose of each step. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f gives exact values (16777216, total vs `df`); B3f gives total against segment size. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B3g had no row for a node that dies or hangs without an error line; added as D-R5. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | For a does-not-cap claim: B2g/B3g rows pair "text absent while free space is below the segment size" with the capacity-follows-knob relation and the positive control. |
| B. Logic | alternative explanations and their controls | Met | B2h, B3h (roomy volume, `stop_commit`, heap); positive control is the segment file length (unit) and the `commitlog_total_space` plateau (cluster, Z arms). |
| C. Specific | a human can follow it from the intro and §9a | Met | The Estimate and Ground lines and A1 to A5 state the claim. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The unit tier and the cluster volume sizes were exact; the "unresolvable path" arm (B2b d) cannot be built (D-R1); the cluster arms were not enumerated (D-R3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3c's stress size and stop condition were "10 minutes"; D-R3 fixes n, threads, 180 s cap and the settle time (harness). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` for the unit tree, `ant jar` for the node tree; `sudo mount -t tmpfs` works on pc07; `fallocate` present. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | With the filler, 200000 x 1000 B rows (about 200 MB of commit-log traffic) exceed 4 MiB or 2 MiB of free space by a large factor (D-R3). Z arms: 2.2 GB through a 64 MiB total. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked: `CommitLog.java:570-573, 606-614`; `PathUtils.java:572-581, 782-822`; `DatabaseDescriptor.java:668, 891-901, 2875-2887`; `Config.java:389-397`; `MemoryMappedSegment.java:62-63`; `AbstractCommitLogSegmentManager.java:206`; `AbstractCommitLogService.java:220`. All as cited, except the unresolvable-path claim. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Replace the "unresolvable path" arm and its prediction (0 / augmented) by nonexistent paths under each volume | Applied, 2026-10-26 (case file D-R1) | `findExistingAncestor` walks to `/`; the 0 return is unreachable for a directory string. |
| R3 | Make exhaustion explicit with a filler; list the arms; add a compressed (`standard` mode) variant; add the roomy-volume positive control arms; withdraw the third-segment / first-segment argument | Applied, 2026-10-26 (D-R3) | mmap segments are sparse; exhaustion arrives as a page fault, not as `IOException`. |
| R4 | State the error as the two `handleCommitError` call sites a full volume reaches | Applied, 2026-10-26 (D-R4) | B3f named only the manager call site. |
| R5 | Add a B3g row for a node that dies or hangs without an error line | Applied, 2026-10-26 (D-R5) | A shakedown was not needed to foresee it: a full mmap volume gives SIGBUS. |
| R6 | (stage 3) The estimate line and A3 say the branch "is almost never taken". It is taken whenever the commit-log volume's total size is below the segment size, which is the only case where it adds text. Candidate wording only. | Left for stage 3 | The claim is not affected. |

**Agreement criteria** — not applicable (no run 2 planned at the time of freezing).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 21:01 local; cluster arms 21:04 to 21:35 local, i.e. 01:04 to 01:35 UTC on 2026-10-27) |
| Node | pc07 (`node0.jason92-320876...`), 40 cores, 251 GiB; port slot 2 (127.0.2.1, JMX 7120) |
| OS and kernel | Ubuntu 22.04, `5.15.0-187-generic` |
| JDK / Ant | OpenJDK 11.0.32.1 / Apache Ant 1.10.12 |
| Local source copy | `~/s4-b10-sg-u` (unit, `ant build-test`) and `~/s4-b10-sg-n` (cluster, `ant jar`), both by `copy-source.sh` from `cassandra/cassandra-5.0.9/` at repository commit `93d6365` (local baseline commit `9bb60fd` tagged `cassandra-5.0.9`) |
| Case-file / harness commit | uncommitted when run (orchestrator commits); case-file sha256 in §1 |
| Storage for node data | Commit log on a dedicated tmpfs per arm (`sudo mount -t tmpfs -o size=16m/64m/1024m`, `df` size checked equal to the nominal size); node data, hints and caches on `/dev/shm/s4-b10-sg-node`; unit tier: a 4 GiB and a 16 MiB tmpfs. Nothing written to `/proj` except the committed excerpts. |
| Full logs | `~/s4-b10-sg-logs/run1/{unit,cluster}/` on pc07 (full `system.log`, `debug.log`, `stress.log` gzipped per arm); shakedowns in `~/s4-b10-sg-logs/{unit-shake1,cl-shake}` (not readings) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B3c | "third segment cannot be allocated" / "first segment cannot be created": mmap segments are sparse, the claim does not hold | filler arms (D-R3) | 2026-10-26, before any reading | uncommitted |
| 2 | audit | B2b d, B2e 4 | unresolvable path unreachable | D-R1 | 2026-10-26, before any reading | uncommitted |
| 3 | shakedown | harness | unit JVM killed by `JVMStabilityInspector` on `handleCommitError` (daemon setup not complete); fixed with `KillerForTests`. Cluster shakedown: `hs_err` landed in the launching directory, `analyze.py` read local time and a wrong timestamp pattern, umount raced with the JVM exit (first chain of 7 arms failed at its first check, no data). All harness-only; none of them touches B2f, B2g, B3f, B3g. | harness edits | 2026-10-26 | n/a |

## 4. Run 1

**Scope:** unit tier (all of B2e); cluster tier arms A1, A2, A3, A4, A5, Z32, Z8 as listed in the case file's B3b (D-R3), then, **after reading those seven**, two added arms: **A5L** (A5 with `commitlog_compression: LZ4`) and **ZH** (Z32 with `commitlog_total_space: 512MiB`). They were added because the mmap arms A1, A3 and A5 ended in a JVM crash (so the frozen A5 prediction had no handled-path reading) and because Z8 overshot the control's pre-fixed bound; neither addition changes any prediction or conclusion row, and both are reported as additions. **Command log:** `commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous/run1/` (`unit/session.log`, `cluster/<arm>-r1/session.log`, `selfcheck.out`).

### 4.1 Readings

**Unit tier** (`run1/unit/probe.out`; 28 PASS lines, `RESULT DONE failures=0`; every operand compared with `df -B1` in the same call)

| Test or assertion | Result | Evidence |
|---|---|---|
| S1: 16 MiB tmpfs, empty, seg 32 MiB | text appended; `only` = 16777216 = `df` size | probe.out S1 |
| S2/S3: 4 GiB tmpfs, empty, seg 8, 32, 1024, 2047 MiB | message unchanged; `CommitLog.freeDiskSpace()` = 4294967296 = `df` size | probe.out S2, S3 |
| S4: 4 GiB tmpfs, filled to 32768 B free, seg 8, 32, 1024, 2047 MiB | message unchanged; operand still 4294967296 (avail 32768) | probe.out S4 |
| S5: 16 MiB tmpfs, filled to 262144 B free, seg 32 | text appended; `only` = 16777216 (avail 262144) | probe.out S5 |
| S6: same full 16 MiB tmpfs, seg 8, 16, 17, 1024 | no text, no text, text, text (flip between 16 and 17 MiB: total 16777216 against segment) | probe.out S6 |
| S7: nonexistent path under the 4 GiB / 16 MiB tmpfs, seg 32 | operand is the ancestor volume's total (not 0); not augmented / augmented | probe.out S7 |
| S8: `CommitLog.handleCommitError` with `stop_commit` and `ignore`, log line captured | text in the logged message on the 16 MiB volume only | probe.out S8 |
| C1 (positive control): segment file length after `resetUnsafe` at seg 8, 32, 64 MiB | 8388608, 33554432, 67108864 = segment size | probe.out C1 |

**Cluster tier** (`run1/cluster/<arm>-r1/`; every arm: volume `df` size = nominal, effective yaml values read from the node's config dump)

| Arm | Setup | handleCommitError lines | "bytes required" text | Other |
|---|---|---|---|---|
| A1 | 64 MiB, seg 32, mmap, filler leaving 4 MiB | 0 | 0 | JVM died of SIGBUS in `Native-Transport-Requests` (`hs_err.head`); stress: 200000 of 200000 failed |
| A2 | 64 MiB, seg 32, LZ4, filler leaving 4 MiB | 9 ("Failed to persist commits to disk", sync thread, every ~10 s) | 0 | node alive; df avail 4194304 then 0, volume total 67108864 |
| A3 | 16 MiB, seg 32, mmap, no filler | 0 | 0 | JVM died of SIGBUS |
| A4 | 16 MiB, seg 32, LZ4, no filler | 9 | 9: "33554432 bytes required ... only 16777216 bytes available" | `df` avail 16752640 at the first line, 0 at the third; node alive |
| A5 | 16 MiB, seg 8, mmap, filler leaving 2 MiB | 0 | 0 | JVM died of SIGBUS |
| A5L (added) | 16 MiB, seg 8, LZ4, filler leaving 2 MiB | 22 | 0 | df avail 2097152 at the first line (below the 8 MiB segment) |
| Z32 | 1 GiB, seg 32, mmap, no filler, 2.2 M rows | 0 | 0 | `TotalCommitLogSize` 64 to 96 MiB (max 100663296); 92 flushes, all reason COMMITLOG_DIRTY |
| Z8 | 1 GiB, seg 8, mmap, no filler | 0 | 0 | `TotalCommitLogSize` 56 to 104 MiB (max 109051904); 47 flushes, all COMMITLOG_DIRTY |
| ZH (added) | as Z32 with `commitlog_total_space: 512MiB` | 0 | 0 | max 234881024 (224 MiB); 37 flushes, all MEMTABLE_LIMIT |

### 4.2 Conclusion and logic

1. **Validity.** Unit: the `df` sizes of the two tmpfs equal 4294967296 and 16777216 [observed: `unit/session.log`, `probe.out` KA lines]; the big volume was filled to 32768 B free and the small to 262144 B [observed: KA lines]. Cluster: each arm's `session.log` records the volume size check, the effective `commitlog_segment_size`, `commitlog_total_space=64MiB` (512MiB for ZH), `commit_failure_policy=ignore`, the commit-log directory, and, for the filler arms, the avail after the filler (4194304 or 2097152, both below the segment size) [observed: each `session.log`]. The limit (free space below one segment) was reached in A2, A4, A5L: errors were logged [observed: `analyze.out`]. In A1, A3, A5 the volume filled (df used = size) and the node died, so those arms reached the limit but not the logging path [observed: `hs_err.head`, `session.log`].
2. **Readings.** A1, A3 and A5 gave no `handleCommitError` line because the JVM took SIGBUS on a touched mmap page of a full tmpfs [observed: `hs_err.head`: `SIGBUS ... BUS_ADRERR`, thread `Native-Transport-Requests-n`]. The first sync error in the LZ4 arms is an `AssertionError` at `CompressedSegment.java:83` (**[inferred: a short `channel.write` at ENOSPC trips `assert channel.position() - lastWrittenPos == compressedBuffer.limit()`]**), later ones `IOException: No space left on device` [observed: `errors-head.txt`]; the node also logged `Stopping transports as disk_failure_policy is stop` from a failed memtable post-flush [observed]. Neither changes what was measured: the text is built in `handleCommitError` before any of that. Z8's `TotalCommitLogSize` sawtooth reaches 104 MiB, more than the pre-fixed bound of total + one segment (72 MiB) [observed: `jmx.csv`].
3. **Matched row.** *Unit:* B2g row 1 ("Large volume, free near 0, message unchanged, printed value equals total size: Claim confirmed"): S4, and S1/S5 for the printed value on the small volume. Also the row "Augmentation flips with segment size only when segment > total": S6. Positive control row ("Usage moves with the knob where the control binds"): C1. *Cluster:* B3g row 1 ("Disk full on 64 MiB volume, error logged, no 'bytes required' text: Claim confirmed"): A2 [observed: A2 `analyze.out`: 9 lines, 0 text; avail 4194304 against segment 33554432]; row 3 ("Text appears on the 16 MiB volume with 'only' equal to the volume total: confirms the operand is capacity"): A4 [observed: only=16777216, df size 16777216]; the 8 MiB-on-16 MiB prediction of B3f: A5L (error logged, no text, avail 2 MiB < 8 MiB segment). The positive-control row ("plateau at commitlog_total_space while the target line is silent"): Z32 and Z8, see 6. The D-R5 row ("node dies or hangs with no handleCommitError line"): A1, A3, A5, **Not confirmed for those arms**.
4. **Excluded rows.** "Disk full and the text appears with 'only' near avail" (the Refuted row): excluded by A2 and A5L (no text with avail < segment) and by A4, whose `only` equals the volume total 16777216 while df avail was 16752640 at the first line and 0 at the third [observed]. "No commit-log error ever raised, or control does not plateau": excluded for A2, A4, A5L (errors) and Z (bounded). "Commit-log bytes grow with the segment size independent of this line": not separately tested at cluster scale (C1 covers the file size).
5. **Observed vs. inferred.** Inferred: (a) that the default `legacy` mode on a full disk always kills the node (three of three arms did; one shakedown also did); (b) that Z's bounded `TotalCommitLogSize` is caused by `commitlog_total_space` rather than another limiter: supported by the flush reasons (COMMITLOG_DIRTY only, in Z32 and Z8; MEMTABLE_LIMIT only in ZH with the cap raised) and by ZH's higher maximum; (c) that the sync-thread error would be the same in mmap mode had the node survived: `AbstractCommitLogService.java:220` is the same call.
6. **Deviations and gaps.** (i) The mmap arms did not reach the logging path, so the default configuration is verified only by the unit tier and by the crash; the claim that the check does not track free space is verified at cluster scale in `standard` mode only. (ii) Positive control: Z32 satisfied the bound fixed before run 1 (`max <= total + one segment`: 100663296 = 96 MiB, exactly the bound); **Z8 did not** (104 MiB against 72 MiB): the overshoot is the segments in flight before the asynchronous flush frees them (5 segments of 8 MiB), not a failure of the cap, but the frozen sentence "stays at or below the commitlog_total_space value" is literally false in both Z arms (the cap is a reclaim target). Both arms are bounded at 1.5 to 1.6 times the cap against about 2.2 GB of values written, and flush for COMMITLOG_DIRTY; with the cap raised to 512 MiB the same workload reached 224 MiB and flushed for MEMTABLE_LIMIT. (iii) A5L and ZH were added after reading A1..Z8. (iv) The `Total errors` in the LZ4 arms (155654, 158906 of 200000) are stress writes refused after the transports stopped; they are not part of the argument.
7. **Core question.** The check at `CommitLog.java:609` compares the volume's **total** capacity (`FileStore::getTotalSpace`) with the segment size: on a full 4 GiB volume it never fires at any segment size (unit S4), on a 64 MiB volume with 4 MiB free it did not fire although the node was failing to write (A2), and on a 16 MiB volume it fires with `only` equal to the capacity while `df` showed 0 to 16 MiB free (A4, S5, S6 around 16 to 17 MiB). It also gates nothing (it only extends a log string), and the knob does bind elsewhere (C1 segment file size; the Z arms' bounded commit log through `commitlog_total_space`). So usage does not follow this constraint at this line: it does not cap.

**Conclusion (one line):** unit B2g row 1 (large volume, free near 0, unchanged message, operand equal to total) with the positive control row: **Confirmed — does not cap**; cluster B3g rows 1 and 3 (A2, A4, A5L) with the plateau control (Z32, Z8, ZH): **Confirmed — does not cap** for the standard (LZ4) arms; the default mmap arms A1, A3, A5 **Not confirmed** (node killed by SIGBUS before any line).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/commitlog-segment-size-addAdditionalInformationIfPossible-segmentSize--autonomous/selfcheck.py` re-parsed `probe.out`, the raw `system.log` (from the recorded byte offset), `du.csv` and `jmx.csv` by a different code path than `analyze.py`; output in `run1/selfcheck.out`. It reproduced every count (2 CHECK NOT OK lines, both expected: A3, whose node died, and Z8's pre-fixed bound).

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `session.log` of each arm: df size, effective yaml, filler avail; `hs_err.head` of A1, A3, A5 (SIGBUS) re-read. |
| 2. Readings | yes | `errors-head.txt` of A2, A4, A5L re-read for the AssertionError and the `No space left` stack; Z8 sawtooth re-read in `jmx.csv`. |
| 3. Matched row | yes | A2 9 lines / 0 text; A4 9 lines / 9 text, only=16777216 (selfcheck.out); unit S4/S6/C1 lines re-read. |
| 4. Excluded rows | yes | selfcheck: no arm shows text with `only` below the volume total. |
| 5. Observed vs. inferred | yes | Inference (b) rests on `flush-reasons.txt` of Z32, Z8, ZH, re-read. (a) is a count of three. |
| 6. Deviations and gaps | yes | Z8's miss of the pre-fixed bound is stated, not hidden; the added arms are labelled. |
| 7. Core question | yes | The steps follow the audited logic: knob (segment size) varied; operand shown to be capacity; disallow branch (text) shown to depend on total vs segment; positive control shown to bind. |

### 5.2 Run 2?

**No** (2026-10-26). The unit tier is exact and deterministic; the cluster conclusions rest on direct log lines in three arms and on a bounded-control argument whose inference (b) is supported by flush reasons. A rerun of the mmap arms would only repeat the crash; settling the Z8 bound is a statement about the frozen wording, not a measurement. Not cheap enough to be clearly needed.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** usage does not follow this check: whether the "bytes required ... only M bytes available" text is appended depends on the volume's total capacity relative to `commitlog_segment_size`, not on free space, and the check has no effect on how much disk the commit log uses.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — large volume, free near 0, message unchanged, printed value equals total size (S4); flips at segment > total (S6) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (standard/LZ4 arms A2, A4, A5L; text absent with free < segment on a 64 MiB volume, present with only = total on a 16 MiB volume). Default mmap arms A1, A3, A5: **Not confirmed** (SIGBUS kills the node; no line) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** unit: the segment file length equals `commitlog_segment_size` at 8, 32, 64 MiB (the knob binds at segment creation, not at the target line). Cluster: with `commitlog_total_space` 64 MiB the commit log stayed in a 56 to 104 MiB sawtooth and flushed for COMMITLOG_DIRTY (Z32, Z8); with 512 MiB the same workload reached 224 MiB and flushed for MEMTABLE_LIMIT (ZH). Caveat: Z8 exceeded the bound fixed before the run (§4.2 part 6).

**Findings for stage 3 and upstream (candidates, JIRA check first):**
- `CommitLog.freeDiskSpace()` (`CommitLog.java:570-573`) uses `FileStore::getTotalSpace`; the error text reports total capacity as "bytes available" and the comparison fires only when the volume is smaller than the segment. Probably meant `getUsableSpace`. Runtime: A4 printed 16777216 with df avail 0.
- Default `commitlog_disk_access_mode: legacy` (mmap): a full commit-log volume kills the JVM with SIGBUS instead of reaching `commit_failure_policy` (A1, A3, A5).
- `CompressedSegment.write` (`CompressedSegment.java:83`): the `assert` on the written length fires on a short write at ENOSPC, before the IOException surfaces (the shipped JVM options run with `-ea`).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (amendments D-R1, D-R3, D-R4, D-R5 and the run-1 verdict); the case file is untracked, so no commit yet. `_INDEX.md`, `HANDOFF*.md`, `predicted-negative.md` and `writeup-set-A.csv` were not edited (orchestrator).

**Leftovers on pc07:** no process, no mount, no `/dev/shm` data of this case. Kept: `~/s4-b10-sg-u`, `~/s4-b10-sg-n` (source copies), `~/s4-b10-sg-logs/` (full logs).
