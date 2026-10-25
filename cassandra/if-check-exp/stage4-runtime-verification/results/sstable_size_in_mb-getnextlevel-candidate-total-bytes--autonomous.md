# sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous — stage-4 results  <!-- file: results/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous`](../../stage3-ai-deep-read/cases/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous.md)
>
> **Status:** **Closed 2026-10-24 — unit Confirmed, cluster Confirmed — does not cap** (estimate negative, matched); one sub-prediction missed (L1+ over quota under throttling) and one arm not applicable (N=160 large partition); run 1 only, self-checked; no run 2
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments: `ce2bd950c1e03c8b0b3d23c70bb6bd9051f1828bf6993aa198444a50ab88b7ca` (`sha256sum`, run 2026-10-24 13:35 EDT, before any harness code, unit run or cluster run; no reading existed). Repository commit holding the file: not yet committed (the human commits); base commit `9e6ee79`. **Post-freeze amendment (2026-10-24, before any cluster reading, runbook defect D1, leaves every prediction and conclusions row unchanged):** N8 (the drain stop condition); sha256 after it `97bb71648a425a3b645e621c466e5911a55a8419a3ca82a91d9c95c82b15d648`; a second runbook fix N6 (batches of 10 rows in the large-partition writer) was made in the same window, final sha256 before the runs `60ffdae096f749dba97e689f7d56df5568b83738d3830df2760ec5fd7d7c9adf`. The file is later changed only in section D (feedback). |
| **Harness** | `harness/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous/`: written after the freeze (step 1). |
| **Tiers and values** | Unit (B2): N ∈ {1,5,20,160}; Sets A/B real flushes, boundary by MockSchema sstables, mixed and all-L1; Set B compaction; 15 MiB partition. Cluster (B3): N ∈ {5,20,160}, 2 M rows, overwrite, large-partition table, throttled N=20, STCS reference. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-24 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-disk bytes of the compaction inputs against the size (`LeveledManifest.java:678`), and table disk bytes in B3. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {1,5,20,160}; B3b {5,20,160} (default included). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d `getTotalBytes`/`onDiskLength`; B3d `du -sb`, `tablestats`. The level decision is a decision, not a resource; named in B2d. |
| A. Core question | usage driven to the limit and past it | Met | B2c Set A below, Set B above N; B3 N=5 reaches several levels with 2 GiB; N=160 rows are the file's "limit never reached" rows. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps each state the reading taken. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact (`< N MiB` → 0, `≥` → 1, mixed → 1, all-L1 → 2); B3f <10% and counts ∝ 1/N. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g cover flip, bigger-than-N output, flat total (Confirmed), total follows N (Refuted), control not moving, never reached. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmation needs flat total and sstable count moving (positive control). |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Partly | B2h control is output count; B3h control (TRUNCATE/TTL) is a data change, not a cap. Accepted: **N5/N7** keep truncate and add an STCS reference. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3/B1 are clear. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | "total == N MiB" cannot be built from flushed sstables; **N1** uses MockSchema sstables. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | The large-partition table and the overwrite phase lacked commands; **N4-N6** supply them. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | Test class and sampler are step-1 work; tools exist. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | After N4 each run ≈ 2 GiB on a 24 GiB tmpfs; six runs (3 N + throttled + STCS + overwrite) in sequence. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `LeveledManifest.java:185-193,199-302,495-573,667-688`, `LeveledCompactionStrategy.java:52-117,289,568-632`, `MaxSSTableSizeWriter.java:75-79`, `LeveledCompactionTask.java:46-54` re-read in the pinned tree; they match. `MockSchema.java:153` also checked. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| N1 | Exact boundary with MockSchema sstables | Applied 2026-10-24 | real flushes cannot hit the byte |
| N2 | Random values, unique keys, mixed-level and all-L1 construction | Applied 2026-10-24 | unambiguous |
| N3 | Set B task execution defined | Applied 2026-10-24 | unambiguous |
| N4 | tmpfs; 2 M rows; table creation and stress command | Applied 2026-10-24 | time/disk-stall |
| N5 | Stable definition and supplementary overwrite phase | Applied 2026-10-24 | overwrite is not in B3f |
| N6 | Large-partition table by Python script | Applied 2026-10-24 | stress cannot make 40 MiB partitions simply |
| N7 | Throttled run at N=20; STCS reference run; truncate control | Applied 2026-10-24 | the file left them optional |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-24: unit attempt 1 13:41, unit (counted) 13:54-13:55 EDT; cluster 14:21-15:07 EDT (N5 attempt 1 14:21-14:29, not counted, D6; N20 14:29, N160 14:38, T20 14:44, STCS 14:53, N5 rerun 14:57-15:07) | not done |
| Node (CloudLab name and type) | `pc07` = `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB); the session ran on it directly; `pc12` not touched | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/cassandra-lcsN`, made by `copy-source.sh` from repository commit `9e6ee79` (`cassandra/cassandra-5.0.9` clean); `git describe` = `cassandra-5.0.9`; `ant build-test` BUILD SUCCESSFUL; the harness test class was copied into it | — |
| Case-file commit / harness commit | not committed (the human commits); case file sha256 at the freeze `ce2bd950…b7ca`, after the run-time fixes (N8, N6 batch size) `60ffdae0…9adf`; harness = the files in [`harness/…/README.md`](../harness/sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous/README.md) | — |
| Storage for node data | cluster: dedicated tmpfs `/mnt/lcsrun` (24 GiB) for data, commit log, hints and saved caches; unit: the copy's `build/test/cassandra` on local `/dev/sda3` | — |
| Full logs (path, outside the repo) | unit `~/stage4-logs/lcs/N-unit/` (attempt 1: `N-unit-attempt1/`); cluster `~/stage4-logs/lcs/cluster/N/<label>/` (N5 attempt 1: `N5-attempt1/`); chain log `~/stage4-logs/lcs/cluster/chain.log` | — |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | shakedown (discarded) | B3e step 4 / N5 "0 pending" | `compactionstats` shows an estimate while the only L0 sstable left has no partner (`LeveledManifest.java:569`), so "0 pending" cannot hold | "stable" = 3 reads 20 s apart with `CompactionExecutor` active + pending = 0 in `tpstats` and identical file bytes; amendment N8, before any cluster reading; B3f/B3g unchanged | applied 2026-10-24 | not committed (human) |
| D2 | shakedown | harness | unquoted `-col size=FIXED(256) n=FIXED(4)` failed in the shell; the runner now quotes the tokens and stops without a `Total errors` line | fixed in `cluster-run.py` | 2026-10-24 | n/a |
| D3 | cluster | harness quirk | `tablestats` prints `18/4` for an over-limit level and `parse_levels` strips the slash, so the snapshot JSON's `count` is wrong for such levels; bytes and raw text are right | none; the self-check parses the raw text | 2026-10-24 | n/a |
| D4 | cluster | B3e step 2 "stress creates the schema" | table `ks.standard1` created by `cqlsh` (N4), because `cassandra-stress` cannot set `sstable_size_in_mb` | deviation recorded | 2026-10-24 | n/a |
| D5 | unit attempt 1 | B2h "positive control: the output count must grow as N shrinks **for the same input**" | the sets scale with N (0.8 N, 1.5 N), so the counts compared different inputs; the control as filed was not implemented | added `sameInputControl` (the same ≈ 30 MiB input compacted at every N); the unit tier was re-run from its start; attempt 1 (`N-unit-attempt1`) kept; no prediction or row changed | 2026-10-24 | n/a (harness) |
| D6 | cluster N5 attempt 1 | N6 large-partition table | `big-writer.py` failed (`No module named 'cassandra'`: the bundled driver is under `cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`) and the run script did not stop (the pipeline hid the exit status), so N5 attempt 1 had no large-partition reading | path fixed and the runner now stops unless the writer prints `payload bytes`; labels N20-STCS ran with the fix; **N5 was re-run in full** (14:57-15:07) and the re-run is the N5 reading; attempt 1 is kept and agrees with it (settled 2,054.9 MiB in 516 files vs 2,054.6 MiB in 508; level bytes within 1%) | 2026-10-24 | n/a |

## 4. Run 1

**Scope:** unit tier (B2): N ∈ {1, 5, 20, 160}, 3 repetitions; exact boundary, Sets A/B, Set B compaction, the same-input control, a ≈ 15 MiB partition. Cluster tier (B3): N ∈ {5, 20, 160} (compaction unthrottled, 1 compactor), T20 (N=20 at 16 MiB/s) and the STCS reference; each with 2,000,000 rows (4 × 256 B; ≈ 2 GiB), then the supplementary overwrite phase, then the large-partition table. **Command log:** `sstable_size_in_mb-getnextlevel-candidate-total-bytes--autonomous/run1/`.

### 4.1 Readings

**Unit tier** (4 tests, 0 failures; `run1/unit/readings.txt`, `ant.log`, `analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Boundary (MockSchema sstables), N = 1/5/20/160 | `getNextLevel` = 0 at N MiB − 1, **1 at N MiB**, 1 at N MiB + 1 (single and 3-way split; totals exactly N·1048576 + {−1, 0, +1}); {L0, L1} → 1; {L1, L1} → 2 | `boundary N*` |
| Sets A and B (real flushes) | A = 0.791 × N → level 0; B = 1.483 × N → level 1 (N = 1, 5, 20, 3/3 reps); at N=160 both sets (0.099 and 0.185 × N) → level 0 | `sets N*.set*.rep*` |
| Set B compaction | N=1: 2 files (1,048,930 and 507,051 B), level 1; N=5: 2 files (5,243,242 and 2,534,192 B); N=20: 2 files (20.0005 MiB max); N=160: 1 file of 29.7 MiB at level 0 | `sets N*.setB.*` |
| Same-input control (≈ 28.9 MiB at every N) | output files 29 / 6 / 2 / 1 at N = 1 / 5 / 20 / 160 (3/3 reps); outputs sum to the input ×1.0001 | `same same.N*` |
| ≈ 15 MiB partition at N=5 | one output file of 15,636,778 B (14.9 MiB, 3.0 × N) and one small file (3/3) | `big big5.rep*` |

**Cluster tier** — 2,000,000 rows per label, 0 stress errors in write and overwrite (`run1/cluster/<label>/stress-*.tail.txt`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N=5 | N5 (re-run) | peak L0; settled bytes and files; large-partition table | 1,425 MiB (71× the 20 MiB target); 2,054.6 MiB in 508 files, median and max Data.db 5.0 MiB; large table: 3 files of 39.2 MiB (one per ≈ 39 MiB partition); supplementary overwrite: 2,631.6 MiB | `N5/snapshot-*.json`, `N5/tablestats-*.txt` |
| N=20 | N20 | same | 1,324 MiB (16.6× the 80 MiB target); 2,050.5 MiB in 112 files, median/max 20.0 MiB; large table: 1 file of 117.7 MiB (the flush output, see 4.2); overwrite 2,333.3 MiB | `N20/…` |
| N=160 | N160 | same | 1,935 MiB (3.0× the 640 MiB target); 2,049.0 MiB in 13 files, median/max 160.0 MiB; large table: 1 file of 117.7 MiB, smaller than N (**arm not applicable**); overwrite 2,737.1 MiB | `N160/…` |
| N=20, compaction 16 MiB/s | T20 | quotas under throttling | write window: L0 17.8× its quota, L1 0.87× (no level above L0 over quota); whole run: L1 5.12× (in the unthrottled overwrite phase); settled 2,050.0 MiB in 102 files; overwrite 2,357.3 MiB | `T20/samples-standard1.jsonl`, `T20/tablestats-lag-end.txt` |
| STCS | STCS | reference | 2,049.4 MiB in 3 files; overwrite 4,183.2 MiB | `STCS/…` |
| all | all | `TRUNCATE` control | 0 live bytes and 0 file bytes afterwards | `*/snapshot-truncated.json` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The level limits were exceeded: L0 at 71×, 16.6× and 3.0× its quota in N5, N20, N160 **[observed: `*/samples-standard1.jsonl`, `*/tablestats-lag-end.txt`]**; the exact-boundary unit points hit the line-678 comparison at its threshold **[observed: `run1/unit/readings.txt` `boundary`]**. Hold-fixed settings: table options in each `CREATE TABLE` line, `compaction_throughput` 0 (16 MiB/s for T20) and one compactor in each yaml, 2,000,000 partitions and 0 errors in all stress outputs **[observed: `*/commands.log`, `*/yaml-keys.txt`, `*/stress-*.tail.txt`]**; unique keys in the write phase **[inferred: one `write` with `-pop seq=1..2000000`]**.
2. **Readings** — (a) The write phases finish in about 30 s, so L0 at the end of the write holds most of the data in every label. (b) N20's and N160's large-partition tables ended as one file of 117.7 MiB: the three ≈ 39 MiB partitions were flushed together into one L0 sstable with no partner, so that file is the flush output (a flush is not split by the option), not a compaction-writer overshoot **[observed: `N20/snapshot-settled-big.json`]**; only N5's three 39.2 MiB files (one per partition, 7.8 × N) come from compaction splitting. (c) The supplementary overwrite phase left more bytes than the live data in every LCS run (2,333-2,737 MiB against 2,050) and 4,183 MiB under STCS, non-monotone in N (N=20 lowest, N=160 highest) **[observed: `*/snapshot-settled-overwrite.json`]**.
3. **Matched row** — Unit B2g: "`getNextLevel` flips 0 to 1 exactly at total = N MiB for each N" (exact for all four N: N MiB − 1 → 0, N MiB → 1), "Output sstable larger than N (oversized partition)" (14.9 MiB at N=5), "Sum of output bytes about equal across N" (×1.0001 at every N; same-input control), with the positive control moving (29 / 6 / 2 / 1 files) **[observed: `run1/unit/readings.txt`]**. Cluster B3g: "Settled live bytes about equal across N, sstable count scales inversely with N" (2,054.6 / 2,050.5 / 2,049.0 MiB, spread 0.3%; 508 / 112 / 13 files: ×4.5 then ×8.6) and "Max sstable > N on the large-partition table" (N = 5 and 20) **[observed: `*/snapshot-settled-write.json`, `*/snapshot-settled-big.json`]**. B3g "Levels above `fanout^level × N` under throttled compaction": L0 over its 4 N quota in all runs (T20 17.8× in the throttled window) **[observed: `T20/samples-standard1.jsonl`]**; see item 6 for L1+.
4. **Excluded rows** — "Settled live bytes scale with N" (Refuted): spread 0.3% over a 32-fold range of N, and the STCS reference (2,049.4 MiB) is the same. "All sstables ≤ N even with 50 MiB partitions" (claim wrong for the per-sstable cap): N5's 39.2 MiB files are 7.8 × N; at N=160 the arm is not applicable (partitions below N). "Positive control does not move usage": `TRUNCATE` took 2 GiB to 0 in 5/5 runs and the same-input file count moved 29 → 1 with N. "Settled bytes never approach any level quota": excluded for N5 and N20 and N160 (L0 3.0×).
5. **Observed vs. inferred** — Inferred: that the settled bytes of the write phase are equal because the data are unique (the overwrite phase tests a different state and is only supplementary); that the unit candidate/level logic (manifest built by `LeveledManifest.create`, MockSchema sstables for the byte boundary) is the production logic.
6. **Deviations and gaps** — tmpfs; 2 M rows; unthrottled main runs as filed; the **B3f bullet "with throttled compaction, L1+ levels exceed `fanout^level × N` while a backlog exists" was not met in the throttled write window**: L0 was 17.8× its quota but L1 peaked at 0.87× (T20, `T20/samples-standard1.jsonl`); L1 exceeded its quota only later, in the unthrottled overwrite phase (T20 5.12×; N5 27×; N20 7×), so the point "a quota is a trigger" is shown there, not in the filed window. The **large-partition arm at N=160 cannot show an oversized file**: its three ≈ 39 MiB partitions are smaller than N (my amendment N6 sized them without checking this against N=160). The overwrite phase is one repetition; its non-monotone 14-34% residue over the live data is compaction state (dead rows below a level's quota stay until it triggers), not tested further. The filed `default_time_to_live` control is not run (N7). The N5 attempt 1 and the re-run agree on settled bytes (2,054.9 vs 2,054.6 MiB), files (516 vs 508) and level bytes (within 1%).
7. **Core question** — Usage did not follow the constraint. Across N = 5, 20, 160 the node's table bytes after compaction were 2,054.6 / 2,050.5 / 2,049.0 MiB (0.3% apart) and the STCS table held 2,049.4 MiB, while the number of files moved 508 → 112 → 13 and the file size followed N exactly (5.0 / 20.0 / 160.0 MiB) **[items 3-4]**. The comparison at `LeveledManifest.java:678` only picks the level (exact at the byte), and a partition larger than N still lands in one file **[unit boundary; N5 large table]**. The option sets file granularity and level quotas, not disk usage.

**Conclusion (one line):** unit B2g "`getNextLevel` flips 0 to 1 exactly at total = N MiB … Sum of output bytes about equal across N … claim confirmed" and cluster B3g "Settled live bytes about equal across N, sstable count scales inversely with N — claim confirmed" — **confirmed, does not cap**, with one B3f bullet missed (L1+ over quota under throttling) and one arm not applicable (N=160 large partition).

## 5. Self-check of run 1 — AI

`harness/…/selfcheck.py` (output `run1/selfcheck.txt`) re-derives every claim without the analysis scripts: the unit tier from the console echo of the readings in `ant.log` (300 readings identical to `readings.txt`), the cluster tier from Cassandra's own raw `tablestats` text, the sampler's raw tablestats text per 20 s, `stress-*.txt`, `cassandra.yaml`, `commands.log` and `system.log`. All 18 claims hold (C7 was first written as "L1 over quota under throttling" and failed; it was rewritten to state the observed fact, which is that it did not occur in the throttled window — the rewrite concerns the claim in the script, the reading is unchanged).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | C1 (options, yaml, 0 errors in write and overwrite stress, 2,000,000 partitions), C2 (clean stops, no `ERROR`), C7b (N5 and N20 L1 over quota at some sample); U1 (byte-exact boundary). |
| 2. Readings | yes | C6 (the large-partition files from the sampler record: N5 106.1 MiB at its peak sample, N20 117.7); the settled listing shows 39.2 MiB × 3 at N5. Both are above 5 MiB; the flush-output reading is stated in 4.2 item 2b. |
| 3. Matched row | yes | U1-U5; C3 (live spread 0.27%, STCS within 0.3%), C4 (counts 508/112/13, ratios 4.5 and 8.6), C5 (mean file 4.04 / 18.31 / 157.62 MiB), U5 (29/6/2/1). |
| 4. Excluded rows | yes | C3 excludes "scales with N"; C9 and U5 exclude "control did not move"; C6 excludes "all ≤ N" at N=5, 20 and records N=160 as not applicable. |
| 5. Observed vs. inferred | yes | The inferred "unique keys → equal bytes" is supported only by C3/C9 through the instruments; the overwrite arm (`INFO` line) is the one place unique keys are not true and bytes differ by up to 17% across N (non-monotone); recorded as a gap. |
| 6. Deviations and gaps | yes | C7 states the throttling bullet as missed in the write window; C6 the N=160 arm as not applicable. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's (a) unit threshold exactness = U1; (b) equal totals with moving file count = C3/C4/U5. |

### 5.2 Run 2?

**No** — decided 2026-10-24. Both tiers match a Confirmed row with large margins (write-phase spread 0.3% against a 10% tolerance; byte-exact boundary), the self-check holds, and the result neither refutes the case nor confirms a bypass. One thing a run 2 or a follow-up could settle is the overwrite phase (single repetition, 14-34% residue, non-monotone in N); it is supplementary and no row depends on it.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** a node's or table's on-disk size does not follow `sstable_size_in_mb`: the option sets only the target size of each compacted sstable and the level quotas, so for the same data total table disk after compaction settles to nearly the same value across option values (within about 10%), and individual sstables can be larger than the option; the line-678 check only picks a level (B1). "Confirmed" means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "`getNextLevel` flips 0 to 1 exactly at total = N MiB for each N", "Output sstable larger than N (oversized partition)", "Sum of output bytes about equal across N" | does not cap | run 1 + self-check | 2026-10-24 |
| Cluster | Confirmed — B3g "Settled live bytes about equal across N, sstable count scales inversely with N" and "Max sstable > N on the large-partition table" (N = 5, 20); sub-prediction missed: L1+ over quota under throttling (seen only in the overwrite phase) | does not cap | run 1 + self-check | 2026-10-24 |

**Positive control** (a negative-estimate file only): unit — the same ≈ 28.9 MiB input compacted at N = 1/5/20/160 gives 29/6/2/1 files with the output bytes unchanged (×1.0001); cluster — the file count 508/112/13 and file size 5.0/20.0/160.0 MiB follow N while the table bytes stay within 0.3%, the STCS table matches, and `TRUNCATE` takes 2 GiB of file bytes to 0 in all 5 runs. The control binds file size and the instrument sees real change; no byte cap binds on this resource in this workload.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the human commits), runbook amendments N8 and the N6 batch-size fix in the case file; no other section amended. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` not touched.

**What stays on `pc07` after the session** (nothing is running; the `/mnt/lcsrun` tmpfs is unmounted and empty): `~/cassandra-lcsN` (copy-source tree with built tests and the copied `LcsNextLevelProbeTest.java`), `~/stage4-logs/lcs/` (setup, `chain.sh`/`chain2.sh`, `N-unit/`, `N-unit-attempt1/`, `cluster/N/<label>/` and `N5-attempt1/` with node logs; all three cases together ≈ 115 MB), the shared `~/.m2`; also `~/cassandra-lcsF` and `~/cassandra-lcsC` of the two sibling files.
