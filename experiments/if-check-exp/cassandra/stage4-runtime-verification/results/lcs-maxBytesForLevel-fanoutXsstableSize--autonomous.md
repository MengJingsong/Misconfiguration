# lcs-maxBytesForLevel-fanoutXsstableSize--autonomous — stage-4 results  <!-- file: results/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`lcs-maxBytesForLevel-fanoutXsstableSize--autonomous`](../../stage3-ai-deep-read/cases/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous.md)
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `b84e2b625c39e011fc15292519cc25612063f8356702a87ba2b9da155e00cea0` (`sha256sum`, run 2026-10-24 13:35 EDT, before any harness code, unit run or cluster run; no reading existed). Repository commit holding the file: not yet committed (the human commits); base commit `9e6ee79`. **Post-freeze amendment (2026-10-24, before any cluster reading, runbook defect D1, leaves every prediction and conclusions row unchanged):** F8 (the drain stop condition); sha256 after it `cd5d79c7e09e261ba891e1212662d47d2a00a3ba405d5a5c23ca732b467b5105`. The file is later changed only in section D (feedback). |
| **Harness** | `harness/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous/`: written after the freeze (step 1); its README lists the files. |
| **Tiers and values** | Unit (B2): `sstable_size_in_mb` {1,2,4} × `fanout_size` {2,10}, 40 L0 flushes of ≈ 1 MiB; L8 case at size 1 / fanout 1; 5 MiB partition; overflow guard; `max_threshold` {4,32}. Cluster (B3): A = 10/10, B = 160/10, C = 10/2, D = STCS, A′ = 10/10 with fast compaction; ≈ 2 GiB each. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: SSTable bytes on disk per level and in total; the quantity compared is `remainingBytes / maxBytesForLevel` (`LeveledManifest.java:251-258`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {1,2,4} MiB × fanout {2,10}; B3b three option pairs (160/10 default) plus STCS reference. The knob is a table option, so it is varied by ALTER. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d use `du -sb` and level bytes (real disk). The file says the score and per-level bytes are "not observable"; they are (F4: `nodetool tablestats` prints per-level bytes). Memory is not claimed. |
| A. Core question | usage driven to the limit and past it | Met | B2c writes 10× the L0 target; B3c ≈ 50× (A, C) and ≈ 3× (B) the L0 target after F5. L8 is driven over target in B2e step 4 (F1). |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state the reading taken. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f give ratios (≈ 10×, ≈ 2.5×), "<15% across configs", exact overflow throw, ≤ max_threshold. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover follows-knob (Refuted), flat (Confirmed), write refused (Refuted), limit never reached and control not moving (Not confirmed). A usage-exceeds-limit row is the L0/L8 rows. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmation needs flat total across configs plus the over-target observation (the "disallow" branch of a negative claim is: nothing blocked and L8 warn only). |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Partly | B2h/B3h controls are weak for bytes (`max_threshold` bounds a count). **Added** F3 (truncate → level bytes 0) and F7 (A′ with fast compaction, truncate at the end). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 and B1 explain the scoring and why L0/L8 are uncapped. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Met | Harness steps in B2e/B3e are exact enough; F1-F3, F6 fix the gaps. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B2e step 4 (three L8 sstables) cannot work as written and the 6 GB workload and 5-min idle wait do not fit the time available; **fixed** F1, F5, F6. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Test class, sampler and run script are step-1 work; tools (`cassandra-stress`, `nodetool`) exist from `ant build-test`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | After F5 each run ≈ 2 GiB on a 24 GiB tmpfs; peaks 2-3×; four configs plus A′ ≈ 25 GiB written in total, not at once. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `LeveledManifest.java:185-193,199-302,495-573,667-688`, `LeveledCompactionStrategy.java:52-117,289,568-632`, `MaxSSTableSizeWriter.java:75-79`, `LeveledCompactionTask.java:46-54` re-read in the pinned tree; they match. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| F1 | One non-overlapping ≥ 2 MiB sstable at L8 | Applied 2026-10-24 (case file, amendment block) | three flushed sstables overlap and are sent to L0 (`LeveledGenerations.java:157-161`); total under 1 MiB would not score |
| F2 | Random values, unique keys | Applied 2026-10-24 | compressible values or repeated keys would change the ingest-to-disk relation |
| F3 | Drain definition; control by public `getCompactionCandidates()`; truncate control | Applied 2026-10-24 | `getCandidatesFor` is private |
| F4 | Per-level bytes from `nodetool tablestats` | Applied 2026-10-24 | 5.0 prints them (`TableStatsHolder.java:264`) |
| F5 | tmpfs of 24 GiB; 2 M rows instead of 6 M | Applied 2026-10-24 | time and disk-stall; arithmetic still reaches every limit |
| F6 | Drain with throughput 0 / 4 compactors after the lag phase | Applied 2026-10-24 | 8 MiB/s drain takes hours |
| F7 | A′ control run and truncate | Applied 2026-10-24 | a positive control that moves bytes |
| F8 | The "Sources read" list names a path outside the repository | left for stage 3 | no effect on the run |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24: unit 13:38-13:40 EDT; cluster 13:53-14:08 EDT (shakedowns 13:42-13:52, discarded) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the session ran on it directly; `pc12` not touched | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/cassandra-lcsF`, made by `copy-source.sh` from repository commit `9e6ee79` (`git status cassandra/cassandra-5.0.9` clean), `git describe` = `cassandra-5.0.9`; `ant build-test` BUILD SUCCESSFUL (1 min 8 s); the harness test class was copied into it | — |
| Case-file commit / harness commit | not committed (the human commits); case file sha256 at the freeze `b84e2b62…0cea0`, after the run-time amendment F8 (defect D1) `cd5d79c7…105`; harness = the files listed in [`harness/…/README.md`](../harness/lcs-maxBytesForLevel-fanoutXsstableSize--autonomous/README.md) | — |
| Storage for node data | cluster: dedicated tmpfs `/mnt/lcsrun` (24 GiB, `sudo mount -t tmpfs`) for data, commit log, hints and saved caches; unit: the copy's `build/test/cassandra` on local `/dev/sda3` | — |
| Full logs (path, outside the repo) | unit `~/stage4-logs/lcs/F-unit/` (`readings.txt`, `ant.log`); cluster `~/stage4-logs/lcs/cluster/F/<label>/` (node logs, conf, samples); chain log `~/stage4-logs/lcs/cluster/chain.log` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown (150,000 rows, discarded) | B3e step 4 / F6 "0 pending compactions" | `nodetool compactionstats` shows an estimate (6) while the only L0 sstable left has no partner (`LeveledManifest.java:569`), so "pending = 0" can never hold | drain done = 3 reads 20 s apart with `CompactionExecutor` active + pending = 0 in `tpstats` and identical file bytes; amendment F8 in the case file (2026-10-24), before any cluster reading; the claim, B3f and B3g are unchanged | applied 2026-10-24 | not committed (human) |
| D2 | shakedown | harness, not the case | `cassandra-stress -col size=FIXED(1000) n=FIXED(1)` unquoted made the shell fail (parentheses); the run script now quotes the tokens and stops if the stress output has no `Total errors` line | fixed in `cluster-run.py` | 2026-10-24 | n/a (harness) |
| D3 | cluster | harness quirk | `nodetool tablestats` prints `101/100` for a level over its limit; `parse_levels` in `cluster-run.py` strips the slash, so the `count` field of the snapshot JSON is wrong for those levels (Aprime lag-end). The byte fields and the raw `tablestats-*.txt` are right and are what the analysis and self-check use | none needed | 2026-10-24 | n/a |

## 4. Run 1

**Scope:** unit tier (B2): `sstable_size_in_mb` {1,2,4} × `fanout_size` {2,10}, 3 repetitions each; L8 case, 5 MiB partition, `max_threshold` control, arithmetic. Cluster tier (B3): A = 10/10, B = 160/10 (default size), C = 10/2, D = STCS, A′ = 10/10 with `concurrent_compactors 4` and `compaction_throughput 0` from the start; 2,000,000 rows each (≈ 1.9 GiB). **Command log:** `lcs-maxBytesForLevel-fanoutXsstableSize--autonomous/run1/` (`unit/unit-run.log`, `cluster/<label>/commands.log`).

### 4.1 Readings

**Unit tier** (5 tests, 0 failures; `run1/unit/readings.txt`, `ant.log`; `unit-analyze.py` output `run1/unit/analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Step 2: 40 L0 sstables × ≈ 1 MiB per knob pair, no compaction | L0 = 42.48 MB (40.5 MiB) in all 18 runs; ratio to the L0 target 10.13 (size 1), 5.06 (size 2), 2.53 (size 4); no write error | `readings.txt` `step2 *.L0bytes/.L0ratio/.writeError` |
| Step 3: drain with `getNextBackgroundTask` | 3-118 tasks per run; level bytes sum to 42.518 MB in all 18 runs (spread 0.004%); L1 reaches 0.91-1.00 of its target; nothing removed | `step3 *.sumLevelBytesAfter/.L1ratio` |
| Step 4: one 2.23 MB sstable at L8, size 1 / fanout 1 (target 1,048,576) | `getCompactionCandidates()` returned null, one WARN `L8 (maximum supported level) has 2230139 bytes while its maximum size is supposed to be 1048576 bytes`, bytes unchanged (3 reps) | `step4 l8.rep*` |
| Step 5: ≈ 5 MiB partition, size 1 | 2 outputs, largest 5,267,090 B (5.02 MiB) against a 1 MiB option (3 reps) | `step5 big.rep*.maxFile` |
| Step 6: arithmetic | `maxBytesForLevel(3,10,160 MiB)` = 167,772,160,000 = 10³ × 160 MiB; L0 = 4 × size; `(8,1000,2^40)` throws `RuntimeException` | `step6` |
| Step 7 control: 40 overlapping L0 sstables | candidates 4 with `max_threshold` 4 and 32 with 32 (3 reps each) | `step7` |
| Instrument control: `truncateBlocking()` | level bytes 0 after truncate in all 18 runs | `control *.sumLevelBytesAfterTruncate` |

**Cluster tier** — 2,000,000 rows per label, 0 stress errors in every run (`run1/cluster/<label>/stress-write.tail.txt`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 10 MiB / fanout 10 (L0 target 40 MiB) | A, 8 MiB/s | peak L0 bytes; settled bytes; per-level bytes after drain | 1,872 MiB (46.8×); 1,907.2 MiB; L1 100 MiB (1.00), L2 993 MiB (0.99), L3 780 MiB; drain 90 s | `A/snapshot-lag-end.json`, `A/snapshot-settled-write.json`, `A/tablestats-*.txt` |
| 160 MiB / fanout 10 (L0 target 640 MiB) | B, 8 MiB/s | same | 1,871 MiB (2.92×); 1,905.5 MiB; L1 1,553 MiB (0.97), L2 320 MiB; drain 67 s | `B/…` |
| 10 MiB / fanout 2 (L0 target 40 MiB) | C, 8 MiB/s | same | 1,870 MiB (46.8×); 1,905.4 MiB; L1-L5 at 1.00 of target, L6 0.99, L7 620 MiB (top); drain 135 s | `C/…` |
| STCS | D, 8 MiB/s | settled bytes | 1,907.6 MiB in 2 files | `D/…` |
| 10 / 10, fast compaction from the start | A′ | peak L0; settled bytes | 1,309 MiB (A: 1,872, −30%); 1,906.8 MiB; L1 0.98, L2 0.995 | `Aprime/…` |
| all | all | `TRUNCATE` control | 0 live bytes and 0 file bytes afterwards | `*/snapshot-truncated.json` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was exceeded: A and C hold 46.8× their L0 target at the end of the write and B 2.92× **[observed: `A|B|C/snapshot-lag-end.json`]**; each hold-fixed setting is confirmed: table options in the `CREATE TABLE` line of each `commands.log`, `compaction_throughput` 8 MiB/s (0 in A′) and `concurrent_compactors` 1 (4 in A′) in each `conf/cassandra.yaml` **[observed: `*/commands.log`, `*/yaml-keys.txt`]**, 2,000,000 partitions and 0 errors in every `stress-write` output **[observed: `*/stress-write.tail.txt`]**, unique keys (no overwrites) **[inferred: `-pop seq=1..2000000` with one `write` per run]**. The L8 limit was reached only at the unit tier (a built manifest); the cluster tier peaked at L7 (C, 620 MiB against its 1,280 MiB target).
2. **Readings** — Nothing contradicts another. The writes finish in 13-17 s (stress, unthrottled), so the "lag" is the whole ingest: L0 at the end of the write is ≈ all data in every label. A′ lowered the peak L0 by 30%, not to the target, because 4 compactors cannot keep up with a 14 s burst. Peaks are read from the end-of-write snapshot and from samples every 20 s, so a shorter peak between samples is not excluded.
3. **Matched row** — Unit B2g rows "L0 bytes ≈ 10× target, writes accepted (step 2)" (10.13×), "Per-level bytes after draining ≈ ingested bytes regardless of `sstable_size_in_mb`/`fanout_size`" (spread 0.004%), "L8 stays over target, warn logged, no task" (3 reps), "Output sstable ≈ 5 MiB with size=1" (5.02 MiB) **[observed: `run1/unit/readings.txt`]**. Cluster B3g rows "L0 bytes ≫ target while writes continue, total disk ≈ ingest for A/B/C/D" (settled 1,907.2 / 1,905.5 / 1,905.4 / 1,907.6 MiB, spread 0.12%) and "Under positive control (faster compaction) levels settle at their targets but total bytes unchanged" (A′ settled 1,906.8 MiB, L1 0.98 and L2 0.995 of target) **[observed: `*/snapshot-settled-write.json`]**.
4. **Excluded rows** — "Bytes in a level drop with a smaller target for the same data" (Refuted): C (fanout 2: targets 5× smaller at L1 and 5⁷ ≈ 78,000× at L7) holds 1,905.4 MiB against A's 1,907.2 MiB, and B (16× larger size) 1,905.5 MiB. "Write errors/timeouts once L0 > target" (Refuted): 0 errors with L0 at 46.8× target in A and C. "Pending compactions never rise / L0 never exceeds target": excluded by 46.8×. "Positive control shows no change / `max_threshold` fails to bound": excluded (candidates 4 and 32; A′ peak −30%). "L8 compacted or trimmed": excluded by the unit step 4.
5. **Observed vs. inferred** — Inferred: that A's and C's totals would be equal for any targets because the data are unique and no TTL or delete applies (no overwrite phase in this file); that the unit step 4's behaviour is the production behaviour at L8 (manifest built by `LeveledManifest.create`, `getCompactionCandidates()` is the production method).
6. **Deviations and gaps** — tmpfs instead of a disk filesystem; 2 M rows instead of 6 M; drain boost after the write (amendments F5, F6); the positive control moves the peak L0 and the instrument (truncate), but no known byte cap binds here: the control shows the workload and instruments could have shown an effect, not that a cap was found; L8 was not reached on the cluster; `max_threshold` control is unit-only (F7); the file's "Sources read" path outside the repository is left for stage 3.
7. **Core question** — Usage did not follow the constraint. The per-level target moved by a factor of 16 (size) and by 5× to ≈ 78,000× (fanout 2 against 10, L1 to L7) while the node's table bytes stayed within 0.12% of one another, L0 sat at 46.8× its target without any write being refused, and a level above its target at L8 produced only a WARN **[steps 1-4 above]**. The constraint is a compaction trigger, not a cap on disk usage.

**Conclusion (one line):** unit B2g "L0 bytes ≈ 10× target, writes accepted … claim confirmed" and cluster B3g "L0 bytes ≫ target while writes continue, total disk ≈ ingest … claim confirmed" — **confirmed, does not cap**.

## 5. Self-check of run 1 — AI

`harness/…/selfcheck.py` re-derives every claim without `unit-analyze.py` or `cluster-analyze.py`: the unit tier from the console echo of the readings in `ant.log` (491 readings identical to `readings.txt`) and the cluster tier from the raw `tablestats-*.txt`, the raw tablestats text embedded in every sample, `stress-write.txt`, `cassandra.yaml`, `commands.log` and `system.log`. Output: `run1/selfcheck.txt`, script `run1/selfcheck.py`. All 20 claims hold.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt` C1 (options, yaml, 0 errors, 2,000,000 partitions for all 5 labels), C2 (boost issued in A-D, not A′), C3 (rc 0, no `ERROR` in any `system.log`), C4 (peak L0 from the raw tablestats text: A 1,872, B 1,871 = 2.92×, C 1,870 MiB). |
| 2. Readings | yes | U0 (file = console echo), U1 (ratio recomputed from bytes: 10.13 / 5.06 / 2.53), C7 (live bytes before/after drain within 1%); the sampling-granularity caveat stands. |
| 3. Matched row | yes | U1-U5, U7 for the unit rows; C5 (peak and settled live spread 0.12%), C6 (after drain L0 empty, every level below the top ≤ target), C8 (A′ peak −30.1%, settled equal) for the cluster rows. |
| 4. Excluded rows | yes | C5 and C1 exclude "smaller target, less disk" and "write errors"; U7 and C8 exclude "control did not move"; U4 reads the WARN text itself (2,230,139 > 1,048,576). |
| 5. Observed vs. inferred | yes | The inferred "unique keys → totals equal for any target" is supported by C7 and C9 (truncate returns the instrument to 0), not independently by an overwrite arm; recorded as a gap. |
| 6. Deviations and gaps | yes | All listed deviations are in the results above; none changes a row. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | The chain fixed in B1 (over-target L0/L8 accepted, totals independent of target) is covered by U1/U4/U2 and C4/C5/C6. |

### 5.2 Run 2?

**No** — decided 2026-10-24. Both tiers matched a Confirmed row with margins far above any tolerance (ratio 46.8× against a "≥ 10×" criterion; spread 0.12% against 15%), the self-check re-parsed the raw files and every claim holds, and the result does not refute the case or confirm a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** the per-level size target `fanout_size^level × sstable_size_in_mb` does **not** cap the bytes a level or the table holds on disk: L0 and the sum over levels exceed their targets by a large factor without any write rejected; the highest level is only warned about; the size option is a soft per-file threshold; total disk tracks bytes ingested (B1). "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "L0 bytes ≈ 10× target, writes accepted" / "per-level bytes after draining ≈ ingested bytes regardless of the knobs" / "L8 stays over target, warn logged, no task" / "Output sstable ≈ 5 MiB with size=1" | does not cap | run 1 + self-check | 2026-10-24 |
| Cluster | Confirmed — B3g "L0 bytes ≫ target while writes continue, total disk ≈ ingest for A/B/C/D" and "positive control (faster compaction) → levels settle at their targets but total bytes unchanged" | does not cap | run 1 + self-check | 2026-10-24 |

**Positive control** (a negative-estimate file only): unit — `max_threshold` bounds the candidate batch (4 and 32 from 40 overlapping L0 sstables, 3 reps) and `truncateBlocking()` takes level bytes to 0 in 18/18 runs; cluster — A′ (4 compactors, no throttle) cut the peak L0 from 1,872 to 1,309 MiB (−30%) and pulled L1/L2 to 0.98/0.995 of target with the same 1,906.8 MiB total, and `TRUNCATE` took 1.9 GiB of file bytes to 0 in all 5 runs. Gap: no byte cap on this resource binds in this workload, so the control shows the instruments and workload can show an effect, not a cap.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the human commits), runbook amendment F8 in the case file; no other section amended. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` not touched (the human closes them).

**What stays on `pc07` after the session** (nothing is running): `~/cassandra-lcsF` (copy-source tree with the built tests and the copied `LeveledManifestCapTest.java`; delete with `rm -rf`), `~/stage4-logs/lcs/` (setup, chain, `F-unit/`, `cluster/F/<label>/` with node logs and per-run conf; all three cases together ≈ 115 MB), the shared `~/.m2`; the `/mnt/lcsrun` tmpfs is unmounted at the end of the session (see the last cluster case's results file).
