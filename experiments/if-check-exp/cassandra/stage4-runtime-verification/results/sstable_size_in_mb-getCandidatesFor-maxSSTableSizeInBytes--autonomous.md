# sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous — stage-4 results  <!-- file: results/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous`](../../stage3-ai-deep-read/cases/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous.md)
>
> **Status:** **Closed 2026-10-24 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); run 1 only, self-checked; no run 2
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (does not cap)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `f072a4d4a720c4e848236594f643606525ce7d5739c825220d87ca1bb87aceed` (`sha256sum`, run 2026-10-24 13:35 EDT, before any harness code, unit run or cluster run; no reading existed). Repository commit holding the file: not yet committed (the human commits); base commit `9e6ee79`. **Post-freeze amendment (2026-10-24, before any cluster reading, runbook defect D1, leaves every prediction and conclusions row unchanged):** C8 (the drain stop condition); sha256 after it `ccd9136ae4c776b1a0c4079ab47be936fe50e1e841eafbcd0910dd3be577c1e5`. The file is later changed only in section D (feedback). |
| **Harness** | `harness/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous/`: written after the freeze (step 1). |
| **Tiers and values** | Unit (B2): `sstable_size_in_mb` {1,5,160}; 6 overlapping L0 sstables ≈ 2 MiB plus one L1; output sizes at 5; 200-sstable L0 phase. Cluster (B3): N ∈ {5,160,1024}, 2 M rows each, plus the throttled N=160 secondary. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-disk bytes of the L0 candidate set against `maxSSTableSizeInBytes` (`LeveledManifest.java:557`); disk bytes of the table in B3. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {1,5,160}; B3b {5,160,1024} (default 160 included). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d `onDiskLength`; B3d `du -sb` and `tablestats`. The candidate set is a decision, not a resource; the gap is named in B2d. |
| A. Core question | usage driven to the limit and past it | Partly | B2c crosses the threshold (12 MiB vs 5 MiB) and phase 2 writes 200 MiB; B3 at N=1024 never reaches any level target with 2 GiB (the file has the "limit never reached" row). Accepted. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state the reading taken. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give flip points, "within ~10%" and "L0 > 640 MiB". |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g rows: flip, flat (Confirmed), follows N (Refuted), control not moving (Not confirmed), limit never reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmation needs flat total and the file-size positive control moving. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Met | B2h/B3h: output file size (binds, `MaxSSTableSizeWriter.java:78`) is the positive control; C7 adds truncate for the instrument. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3/B1 are clear. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | B2c did not say how the L1 sstable and overlap are made; **C1**, C3 fill it. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3e step 1-2 do not say how the table with N is created; **C4** does. Secondary "N=5 altered to 160" has no procedure (C6: not run). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Test class and sampler are step-1 work; tools exist. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | After C4/C5 each N ≈ 2 GiB on a 24 GiB tmpfs. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `LeveledManifest.java:185-193,199-302,495-573,667-688`, `LeveledCompactionStrategy.java:52-117,289,568-632`, `MaxSSTableSizeWriter.java:75-79`, `LeveledCompactionTask.java:46-54` re-read in the pinned tree; they match. `MockSchema` helpers not needed. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| C1 | Candidate set read from `LeveledManifest.create(...).getCompactionCandidates()`; key ranges chosen; L1 sstable by `mutateLevelAndReload(1)` | Applied 2026-10-24 | the file gave no mechanism for the overlap |
| C2 | Phase 2 as 200 L0 flushes, compaction off | Applied 2026-10-24 | makes the total measurable |
| C3 | Task for the size-5 case | Applied 2026-10-24 | unambiguous |
| C4 | tmpfs; 2 M rows; table created by cqlsh in the stress layout | Applied 2026-10-24 | time/disk-stall; stress cannot set the option |
| C5 | Drain with throughput 0 after the lag phase | Applied 2026-10-24 | 16 MiB/s drain takes hours |
| C6 | Define the secondary experiment; do not run the "alter mid-run" variant | Applied 2026-10-24 | no procedure/prediction |
| C7 | Truncate as instrument control | Applied 2026-10-24 | extra control, no row changed |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24: unit 13:39-13:41 EDT; cluster 14:08-14:21 EDT (discarded shakedowns of the shared runner 13:42-13:52) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the session ran on it directly; `pc12` not touched | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/cassandra-lcsC`, made by `copy-source.sh` from repository commit `9e6ee79` (`cassandra/cassandra-5.0.9` clean); `git describe` = `cassandra-5.0.9`; `ant build-test` BUILD SUCCESSFUL; the harness test class was copied into it | — |
| Case-file commit / harness commit | not committed (the human commits); case file sha256 at the freeze `f072a4d4…ceed`, after the run-time amendment C8 (defect D1) `ccd9136a…1e5`; harness = the files in [`harness/…/README.md`](../harness/sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous/README.md) | — |
| Storage for node data | cluster: dedicated tmpfs `/mnt/lcsrun` (24 GiB) for data, commit log, hints and saved caches; unit: the copy's `build/test/cassandra` on local `/dev/sda3` | — |
| Full logs (path, outside the repo) | unit `~/stage4-logs/lcs/C-unit/`; cluster `~/stage4-logs/lcs/cluster/C/<label>/`; chain log `~/stage4-logs/lcs/cluster/chain.log` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown (discarded) | B3e step 4 / C5 "0 pending" | `compactionstats` shows an estimate (6) while the only L0 sstable left has no partner (`LeveledManifest.java:569`), so "0 pending" cannot hold | "settled" = 3 reads 20 s apart with `CompactionExecutor` active + pending = 0 in `tpstats` and identical file bytes; amendment C8 (2026-10-24), made before any cluster reading; B3f/B3g unchanged | applied 2026-10-24 | not committed (human) |
| D2 | shakedown | harness | unquoted `-col size=FIXED(256) n=FIXED(4)` failed in the shell; the runner now quotes the tokens and stops if the stress output has no `Total errors` line | fixed in `cluster-run.py` | 2026-10-24 | n/a |
| D3 | cluster | harness quirk | `tablestats` prints `101/100` for an over-limit level and `parse_levels` strips the slash, so the snapshot JSON's `count` is wrong for such levels (none here); bytes and raw text are right | none needed | 2026-10-24 | n/a |
| D4 | cluster | B3e "stress creates the schema" | The table `ks.standard1` is created by `cqlsh` in the stress layout (amendment C4) because `cassandra-stress` cannot set `sstable_size_in_mb`; the filed name `ks.t` becomes `ks.standard1` | recorded as the deviation | 2026-10-24 | n/a |

## 4. Run 1

**Scope:** unit tier (B2): `sstable_size_in_mb` {1, 5, 160}, 3 repetitions; the 200-sstable phase at 1 and 160. Cluster tier (B3): N ∈ {5, 160, 1024} with 2,000,000 rows (≈ 2 GiB; 4 columns × 256 B), compaction 16 MiB/s, one compactor; plus the secondary N=160 run at 1 MiB/s. **Command log:** `sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous/run1/` (`unit/unit-run.log`, `cluster/<label>/commands.log`).

### 4.1 Readings

**Unit tier** (3 tests, 0 failures; `run1/unit/readings.txt`, `ant.log`, `analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Phase 1, N=1: 6 overlapping L0 sstables (≈ 12.2 MiB) + one L1 sstable | candidate set = all 7 (14.88 MB = 14.2 × N), L1 sstable included, output level 1, 3/3 reps | `readings.txt` `step3 N1.rep*` |
| Phase 1, N=5 | L0 total 2.43 × N; candidate set = all 7 (2.84 × N), L1 included, 3/3 | `step3 N5.rep*` |
| Phase 1, N=160 | L0 total 0.076 × N; candidate set = the 6 L0 sstables only, no L1, output level 0, 3/3 | `step3 N160.rep*` |
| Step 4: size-5 task on the 6 L0 sstables (12.2 MiB) | 3 output files: 2,268,442 / 5,242,945 / 5,243,337 B; outputs sum to the input ×1.0005; 3/3 | `step4 out5.rep*` |
| Step 4: one ≈ 12 MiB partition at N=5 | one output file of 12,344,824 B (11.8 MiB, 2.4 × N); 3/3 | `step4 big5.rep*` |
| Phase 2: 200 L0 sstables, compaction off | L0 = 212.41 MB at size 1 and 212.43 MB at size 160 (differ 0.006%), 200 sstables, none above level 0; 50.6× the size-1 L0 target (4 MiB) and 0.32× the size-160 one (640 MiB) | `step5 p1.rep*`, `p160.rep*` |
| Instrument control: `truncateBlocking()` | 0 bytes in 6/6 runs | `control` |

**Cluster tier** — 2,000,000 rows per run, 0 stress errors (`run1/cluster/<label>/stress-write.tail.txt`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N=5 (L0 target 20 MiB) | N5 | peak L0; settled bytes and files; peak file bytes | 1,833 MiB (91.7×); 2,055 MiB in 482 files, median Data.db 5.0 MiB, max 5.0 MiB; peak 2,859 MiB; drain 112 s | `N5/snapshot-*.json`, `N5/tablestats-*.txt` |
| N=160 (L0 target 640 MiB) | N160 | same | 1,832 MiB (2.86×); 2,047 MiB in 13 files, median 160.0 MiB; peak 3,944 MiB; drain 90 s | `N160/…` |
| N=1024 (L0 target 4,096 MiB) | N1024 | same | 2,009 MiB (**0.49×: limit not reached**); 2,049 MiB in 2 files (989.6 and 1,024.0 MiB); peak 3,376 MiB; drain 67 s | `N1024/…` |
| N=160, compaction 1 MiB/s throughout | S160 | peak L0; write errors | 2,007 MiB (3.14× the 640 MiB target), 204 L0 sstables, 0 errors; settled 2,047 MiB in 13 files | `S160/…` |
| all | all | `TRUNCATE` control | 0 live bytes and 0 file bytes afterwards | `*/snapshot-truncated.json` |

### 4.2 Conclusion and logic

1. **Validity** — Valid for N=5 and N=160 and S160, where the limit was exceeded (L0 at 91.7×, 2.86× and 3.14× its target) **[observed: `N5|N160|S160/snapshot-lag-end.json`]**. For N=1024 the level limit was **not** reached (2,009 of 4,096 MiB) — the filed "limit never reached" row, so that N says nothing about a cap **[observed: `N1024/snapshot-lag-end.json`]**. Hold-fixed settings: table options in each `commands.log`, 16 MiB/s and one compactor in each yaml, S160 throttled to 1 MiB/s by `setcompactionthroughput 1` right after start, drain boost in all four, 2,000,000 partitions and 0 errors in all stress outputs **[observed: `*/commands.log`, `*/yaml-keys.txt`, `*/stress-write.tail.txt`]**; unique keys **[inferred: one `write` with `-pop seq=1..2000000` per run]**.
2. **Readings** — Nothing contradicts another. As in the sibling files the stress finishes in under 40 s, so L0 at the end of the write holds almost all data. The prediction wording "at N=1024 files are bounded by the data volume itself" missed: the two files are the option size (1,024 MiB) and the remainder of the 2 GiB, not one file of the whole volume **[observed: `N1024/snapshot-settled-write.json`]**.
3. **Matched row** — Unit B2g: "L1 inclusion flips exactly where candidate total crosses the size" (N=1 and 5 include L1, N=160 does not), "Phase 2 L0 total is the same at size 1 and 160 and grows with the number of sstables written" (differ 0.006%), "Output file size follows the size (±1 partition) while total bytes are unchanged" (5.00 MiB files; outputs sum ×1.0005) **[observed: `run1/unit/readings.txt`]**. Cluster B3g: "Settled `du` the same for all N, while file size and count differ" (2,055 / 2,047 / 2,049 MiB, spread 0.4%; 482 / 13 / 2 files; median 5.0 / 160.0 / ≈ 1,007 MiB) and "L0 bytes exceed 4 × N with compaction throttled" (S160 3.14×) **[observed: `*/snapshot-settled-write.json`, `S160/snapshot-lag-end.json`]**.
4. **Excluded rows** — "Settled `du` differs materially (> 25%) and tracks N" (Refuted): spread 0.4% across 205-fold N. "L0 stays ≤ 4 × N under throttling" (Refuted): S160 at 3.14×. "File sizes do not follow N" (control not moved): files are 5.0 and 160.0 MiB at N=5 and 160. "Phase 2 L0 total held to a function of the size": no, 212.4 MB at both sizes. "Output files do not follow the size": 5.00 MiB. "`du` never approaches any level limit": true for N=1024 only, recorded above.
5. **Observed vs. inferred** — Inferred: that N=5 and 160 settled to the same bytes because the data are unique (no overwrite arm in this file); that the unit candidate-set logic (a manifest built by `LeveledManifest.create`) is the production logic.
6. **Deviations and gaps** — tmpfs instead of a disk filesystem; 2 M rows instead of 6 M; drain boost; table `ks.standard1` created by `cqlsh`; N=1024 never reached its limit; the "N=5 altered to 160 mid-run" secondary named in B3b has no procedure and was not run (C6); the unit tier shows the size-5 task only for N=5 (as filed), so "file size follows N" at the unit tier is one value; the cluster tier supplies the other two.
7. **Core question** — Usage did not follow the constraint. Raising `sstable_size_in_mb` by 205× changed the number and size of files (482 → 13 → 2; 5 → 160 → ≈ 1,000 MiB) and left the table's bytes within 0.4%, while L0 held 2.9-92× its target with no write refused and 200 MiB of L0 at size 1 was the same as at size 160 **[steps 1-4]**. The option is a file-granularity and candidate-selection threshold, not a cap on disk.

**Conclusion (one line):** unit B2g "Output file size follows the size while total bytes are unchanged … knob binds file size, not total usage" and cluster B3g "Settled `du` the same for all N, while file size and count differ — claim confirmed" — **confirmed, does not cap** (N=1024 an informational "limit never reached" point).

## 5. Self-check of run 1 — AI

`harness/…/selfcheck.py` (output `run1/selfcheck.txt`) re-derives every claim without the analysis scripts: the unit tier from the console echo of the readings in `ant.log` (156 readings identical to `readings.txt`), the cluster tier from Cassandra's own raw `tablestats` text (SSTable count, live bytes, per-level bytes), the sampler's raw tablestats text, `stress-write.txt`, `cassandra.yaml`, `commands.log` and `system.log`. All 18 claims hold. (Two claims in the first draft of the script were mis-written — C2's logic and C7's bound — and were corrected before this result was written; both corrections concern the script, not a reading.)

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | C1-C3 (options, yaml, throttle of S160, 0 errors, 2,000,000 partitions, no `ERROR`, clean stops); C8 (N=1024 peak L0 below 4,096 MiB), C9 (S160 peak 2,007 MiB). |
| 2. Readings | yes | U0 (file = console echo); C7 reads the two N=1024 files as the option size (mean 1,025 MiB of 2,049 MiB live). |
| 3. Matched row | yes | U1-U2 (L1 flip), U3 (5.00 MiB files, sum ×1.0005), U5 (p1 vs p160 within 0.1%), C4 (live spread 0.37%), C5 (count and mean follow N: 482/13/2; 4.3/157.5/1,024.7 MiB), C9. |
| 4. Excluded rows | yes | C4 excludes "follows N"; C9 excludes "L0 stays ≤ 4 × N"; C5/C6 exclude "control did not move". |
| 5. Observed vs. inferred | yes | The inferred "unique keys → equal bytes" is supported by C4/C10 only through the instrument; no overwrite arm exists in this file (gap recorded). |
| 6. Deviations and gaps | yes | All listed. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 (a) L0 unbounded with compaction held back = C9, (b) live data equal across values with file size and count differing = C4/C5. |

### 5.2 Run 2?

**No** — decided 2026-10-24. Both tiers match a Confirmed row with large margins (live spread 0.4% against a 10% tolerance; S160 at 3.14× against a "> 1×" criterion), the self-check holds, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** total disk usage of an LCS table does not follow `sstable_size_in_mb`; the option sets only a threshold for whether L0 candidates drag in L1 overlaps and the approximate size of output files, so with compaction held back L0 bytes grow without limit regardless of the value, and the live data size is the same at different values while the file size and count differ (B1). "Confirmed" means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "Phase 2 L0 total is the same at size 1 and 160 …" and "Output file size follows the size (±1 partition) while total bytes are unchanged" | does not cap | run 1 + self-check | 2026-10-24 |
| Cluster | Confirmed — B3g "Settled `du` the same for all N, while file size and count differ" and "L0 bytes exceed 4 × N with compaction throttled" (N=1024: limit not reached, informational) | does not cap | run 1 + self-check | 2026-10-24 |

**Positive control** (a negative-estimate file only): the output file size is the control the file names (a cap known to bind, `MaxSSTableSizeWriter.java:78`): unit — files of 5.00 MiB from a 12.2 MiB input at N=5; cluster — median Data.db 5.0 / 160.0 / ≈ 1,007 MiB at N = 5 / 160 / 1024 and file counts 482 / 13 / 2, while the table bytes stayed within 0.4%. `TRUNCATE` took 2 GiB of file bytes to 0 in all four runs. The control binds file size, not bytes; no byte cap binds on this resource in the workload.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the human commits), runbook amendment C8 in the case file; no other section amended. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` not touched.

**What stays on `pc07` after the session** (nothing is running): `~/cassandra-lcsC` (copy-source tree with built tests and the copied `LcsL0ThresholdProbeTest.java`), `~/stage4-logs/lcs/` (setup, chain, `C-unit/`, `cluster/C/<label>/` with node logs; all three cases together ≈ 115 MB), the shared `~/.m2`; the `/mnt/lcsrun` tmpfs is unmounted at the end of the session (see the last cluster case's results file).
