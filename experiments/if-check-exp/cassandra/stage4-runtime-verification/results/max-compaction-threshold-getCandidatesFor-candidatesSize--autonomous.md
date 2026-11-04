# max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous — stage-4 results  <!-- file: results/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous`](../../stage3-ai-deep-read/cases/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous.md)
>
> **Status:** **Closed 2026-10-26 (local time) — unit Confirmed, cluster Confirmed — caps only on some paths (bypass)** (estimate negative; Outcome class false negative); run 1 (cluster observable partly unmatched) plus a run 2 with a better sampler (same session, same fixtures); self-checked
>
> **Outcome class:** false negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (`caps only on some paths (bypass)` counts as caps, [definition](../README.md#outcome-class)); see §8 for the reading that makes this overrulable
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
| **Case-file version** | Autonomous file, sha256 of the whole file after the audit's amendments (U1-U5, C1-C5): `7e0097f5848e4ccc254f74787f6fd3ef9186f5a7f5940808cb9dab04ca1b53f3` (`sha256sum`, 2026-10-27 00:43 UTC = 2026-10-26 evening EDT, before any harness code, build, unit run or cluster run; no reading existed). Frozen tables (text of B2f through B2g, from `**B2f.` to the line before `**B2h.`): sha256 `4a650bd5af6719dd2dc4240d9d83562a60255e7c871eaa9b3d105b65b1c21723`; (B3f through B3g, to the line before `**B3h.`): `f1208563fd47d89ee567c420477e0c10a8556bd8761474adeaaba6741fd1e68b`. These tables are unchanged by the amendments (U2, C3, C4, C5 govern where they differ, as stated in the case file). Repository commit holding the file: not committed (the orchestrator commits); base commit `93d6365`. |
| **Harness** | `harness/max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous/` (README there): `LcsMaxThresholdProbeTest.java`, `unit-run.sh`, `unit-analyze.py`, `lcmt_cluster.py`, `LcDisable.java`, `lcmt_chain.sh`, `lcmt_cluster_analyze.py`, `selfcheck.py`, `excerpt.sh`; written and instrument-checked after the freeze and before run 1 (the unit and cluster analysers were written before the corresponding run 1 readings). Not committed (the orchestrator commits). |
| **Tiers and values** | Unit (B2): max_threshold {4, 8, 32, 64} (+ 100 reference), two L0 size classes, fixtures F and G, STCS control. Cluster (B3): LCS N {32, 4, 64, 16} on 100 L0 + about 10 L1, STCS control N {32, 4, 64, 16} on 100 L0. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. **Post-freeze amendment (2026-10-26, before any cluster reading, runbook defects D3 and D4, leaves every prediction and conclusions row unchanged):** C6 (lone L0 sstable after phase 1; JMX helper for enable/disable); the frozen-table hashes above were re-computed afterwards and are unchanged; the whole-file sha256 after C6 was `e719f54bd57230487516e9f9d3850dc728e24b4cf02fc2abec2bd0f49eca296f`; the file is later changed only in section D (feedback); sha256 after the section D feedback was filed: `f07a3142f543e48d2f41ba4de7f194fb99e3a58864f6d4ee31139b3b88078cff`. |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A2/B1: the operand is a count (`candidates.size()`, `LeveledManifest.java:548`); its byte cost is derivable (sstable bytes of the candidate set, transient disk of the task). B1 names peak compaction input bytes and transient disk. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b {4, 8, 32, 64}, B3b {4, 16, 32, 64}; default 32 included. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d measures sstable bytes of the decision (a proxy; heap/disk not observable at the unit tier, named). B3d measures table-directory bytes, heap (`jstat`) and, by amendment C3, `RssAnon`; G1 used heap includes garbage (gap named in C3). |
| A. Core question | usage driven to the limit and past it | Met | 100 L0 sstables against N up to 64 (past the limit for every N < 100); N = 100 in B2h(iv) is the no-trim reference. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps state the reading. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f's gate figure at N = 8 sits exactly at 160 MiB and its GiB figures cannot hold at the unit tier: **U2** restates them as a rule on measured bytes. B3f's L1 offset becomes the measured L1 (**C3**). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | B2g/B3g rows: refuted, confirmed, L0 count > N, limit never reached, control did not move. The "overshoot" row of B3g is unreachable by the code (**C4**). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmation needs the L0 count at N (the trim fired at `:548`) plus the L1 addition beyond N and the STCS control scaling. |
| B. Logic | alternative explanations and their controls (positive control for a negative file) | Partly | B2h/B3h give the STCS selector as positive control, but on a mixed LCS fixture STCS would have two buckets and an arbitrary pick: **C5** moves it to a separate L0-only fixture; B2h(iii) was vague: **U4**. |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | A3 walks the code path; B1 is one sentence. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | B2c did not say how the 10 disjoint L1 sstables are made (**U1**); B3c did not say how L1 or the 64 MiB flushes are produced, nor how a restart avoids autocompaction (**C1**, **C2**). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3e's stop point ("first task finished") and the restore/restart procedure: **C2**. `disable_stcs_in_l0` repeat: **U3**. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | A sibling harness (`sstable_size_in_mb-getCandidatesFor-maxSSTableSizeInBytes--autonomous`) supplies the node runner pattern; the test class and the fixture builder are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | After **C1**: 1.5 GiB L1 + 6.4 GiB L0 = 7.9 GiB, plus a copy (7.9), plus the largest task output (about 5.5 GiB) fits a 40 GiB tmpfs; the unit large class is 2 GiB on the local disk. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | `LeveledManifest.java:548,551,557,562-567,243,304-317,62`, `CompactionParams.java:80,175-181`, `ColumnFamilyStore.java:3086-3094`, `DatabaseDescriptor.java:223,2594`, `SizeTieredCompactionStrategy.java:116-131`, `LeveledGenerations.java:154-161` re-read in `cassandra/cassandra-5.0.9` (read-only): they match. Line 211 of `LeveledCompactionStrategy.java` (`level == 0 ? Long.MAX_VALUE`) is at about 210. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| U1 | Fixture F: 100 overlapping L0 sstables, 10 disjoint L1 sstables by token band, created with `mutateLevelAndReload(1)` and `LeveledManifest.create`; L1 small at the unit tier | Applied 2026-10-26 (case file, audit amendments) | B2c gave no mechanism; overlapping L1 would be sent to L0 |
| U2 | N = 8 gate and GiB figures: restate as a rule on measured bytes | Applied 2026-10-26 | the filed figure sits on the strict gate; a reading cannot tell the gate from rounding |
| U3 | `disable_stcs_in_l0` via `DatabaseDescriptor.setDisableSTCSInL0`; prediction: no change | Applied 2026-10-26 | the filed repeat had no stated expectation |
| U4 | Fixture G: 25 groups of 4 overlapping L0 sstables | Applied 2026-10-26 | B2h(iii) was undefined |
| U5 | STCS control by `getBuckets` + `mostInterestingBucket` on the fixture | Applied 2026-10-26 | calling form was missing |
| C1 | tmpfs 40 GiB; table created `enabled:false`; fixture phases (1.5 M rows into L1, then 100 flushes of 65,536 rows); data dir copied | Applied 2026-10-26 | no way to get a populated L1 plus exactly 100 L0 sstables, nor to stop compaction at restart |
| C2 | per-N procedure: restart, `setcompactionthreshold`, enable, stop at the first task | Applied 2026-10-26 | the "first task" boundary and the JMX override lost at restart |
| C3 | predictions in the measured L1 offset; heap proxy plus `RssAnon` | Applied 2026-10-26 | L1 will not be exactly 1.6 GiB |
| C4 | unreachable "overshoot" row; the "N = 32 with 20 L0" reference not run | Applied 2026-10-26 | the code trims; no prediction exists for the reference |
| C5 | STCS control on a separate L0-only fixture | Applied 2026-10-26 | two buckets on the mixed fixture make the pick arbitrary |
| C6 | lone L0 sstable after phase 1 counts toward the 100; JMX helper for enable/disable | Applied 2026-10-26 (post-freeze, before any cluster reading) | found in shakedowns (D3, D4) |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

Filled 2026-10-26 after run 1's readings and before run 2 started (run 2 = same fixtures and harness, sampler v2 only; same session, so it is a re-measurement, not an independent session).

| Observable | Must match | Tolerance |
|---|---|---|
| first task's input count and L0/L1 split (from the `Compacting (` line) | exactly | none |
| first task's input bytes | exactly | none (same fixture files, sizes from the file list) |
| LCS input-bytes and peak-bytes fit (offset and slope against N) | in shape | offset within 20% (input) / 30% (peak) of the fixture's L1 bytes; slope within 5% of the other run |
| peak table bytes above baseline of the STCS control | in shape | within 5% where the task lasts 8 s or more; N=4 of run 1 (2 s task, 1.5 s sampler) is under-sampled and not required to match |
| heap | not compared | the two runs use different instruments (run 1 `GC.heap_info` used, run 2 class-histogram live heap); each is judged on its own against P5 |
## 2. Environment

| Field | Run 1 | Run 2 (same session, sampler v2) |
|---|---|---|
| Date | 2026-10-26 (local MDT): unit 19:00; cluster fixtures 19:20-19:42, runs 19:42-19:56 (UTC 2026-10-27 01:xx) | cluster runs 19:58-20:12 |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), reached over ssh from the session; other cases ran on the node at the same time (own ports and directories) | same |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | same |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | same |
| Ant (`ant -version`) | Apache Ant 1.10.12 | same |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b10-lc` (cluster node runs from it) and `~/s4-b10-lc-unit` (unit tier), both made by `copy-source.sh` from repository commit `93d6365` (`cassandra/cassandra-5.0.9` clean); `git describe` = `cassandra-5.0.9`; `ant build-test` BUILD SUCCESSFUL in both | same trees and fixtures |
| Case-file commit / harness commit | not committed (the orchestrator commits); case file sha256 at the freeze `7e0097f5…3f3`, after C6 `e719f54b…296f` (section 1); harness = the files in `harness/…/README.md` | same |
| Storage for node data | cluster: a 40 GiB tmpfs `/mnt/s4lc` (data, commit log, hints, saved caches), fixtures `fx-lcs` (8.68 GB) and `fx-stcs` (7.18 GB) on it, a fresh copy per run; unit: the copy's `build/test/cassandra` on local `/dev/sda3` | same fixtures |
| Node settings | slot 5: `127.0.5.1` (LCS) and `127.0.5.2` (STCS control), JMX 7150/7151, native 9042; `-Xms2g -Xmx2g` G1, `concurrent_compactors: 1`, `compaction_throughput: 0MiB/s`, `num_tokens: 1`, `auto_snapshot: false` (`run-*/cassandra.yaml.tail.txt`) | same |
| Full logs (path, outside the repo) | `pc12:~/s4-b10-lc-logs/` : `unit-run1/`, `cluster/` (run 1 and the two fixture builds), `cluster-aborted1/` (a first chain, stopped by hand before any reading, see D3), `shake/`, `unit-shake*/` (discarded shakedowns) | `~/s4-b10-lc-logs/cluster2/` |

## 3. Runbook defects

All but D7 were found in discarded shakedowns, before any reading of run 1.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown | B2c / U1 | the key bands were computed with Murmur3 tokens, but the unit-test yaml uses `ByteOrderedPartitioner`, so the 10 L1 sstables overlapped each other (45 pairs) and no L0 sstable overlapped an L1 sstable | bands are lexical bands of the key (`k%06d_%03d`); the fixture's overlap pair counts (4,950 L0-L0, 1,000 L0-L1, 0 L1-L1; groups 150) are an instrument check recorded in every run | 2026-10-26 | harness only; U1 unchanged |
| D2 | cluster shakedown | B3e start | the start check treated the substring "running" of `statusbinary`'s "not running" as up, and `cqlsh` was refused | exact line match `running` | 2026-10-26 | harness only |
| D3 | cluster shakedown / first chain | B3c phase 1-2 | a lone L0 sstable stays after phase 1 (`LeveledManifest.java:569`), and a stress round can add two sstables; a fixed 100 rounds would not give 100 L0 sstables (a first chain was stopped by hand at flush 20 for this and restarted; logs `cluster-aborted1/`) | rounds continue until `tablestats` shows exactly 100 in L0; fixture sizes recorded | 2026-10-26 | C6(a) |
| D4 | cluster shakedown | B3e step 3 | `nodetool disableautocompaction` (a JVM, about 2 s) is slower than a small first task (a second task started) | JMX helper `LcDisable.java` (about 60 ms) | 2026-10-26 | C6(b) |
| D5 | cluster shakedown | B3d heap | `jstat` is unusable (`-XX:+PerfDisableSharedMem`) | `jcmd GC.heap_info` in run 1 (used heap, includes garbage); run 2 uses the live heap from `GC.class_histogram` | 2026-10-26 | harness only (C3 named the gap) |
| D6 | cluster shakedown | harness | another session's broad `pkill -f cluster-run.py` killed the first runner | the script is named `lcmt_cluster.py` | 2026-10-26 | none |
| D7 | run 1, after reading | B3d | (a) the 1 s sampler (about 1.5 s per sample with `jcmd`) under-read the 2 s STCS N=4 task: peak delta 123 MiB against 269 MiB of input; (b) the heap used includes garbage and rose with task length in both LCS and the control | no prediction, row or run-1 reading is changed; run 2 re-measures with a 0.25 s byte sampler and the live heap | 2026-10-26 | none (predictions untouched) |

## 4. Run 1

**Scope:** unit tier (B2) in full: schema path N 4/8/32/64 (2 reps), setter path N 4/8/32/64/100 with STCS-in-L0 on and off and gate 160 and 1 MiB, large class N 4/6/8/12/32/64/100, 20-sstable variant, 25-group fixture, STCS selector control. Cluster tier (B3): N 32, 4, 64, 16 for LCS (100 L0 + 9 L1 sstables) and the STCS control (100 L0 sstables). **Command log:** `max-compaction-threshold-getCandidatesFor-candidatesSize--autonomous/run1/` (`unit/unit-run.log`, `cluster/run-*/commands.log`). Run 2 (§6) is in `run2/`.

### 4.1 Readings

**Unit tier** (5 tests, 0 failures; `run1/unit/readings.txt`, `analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Fixture F (100 overlapping L0 + 10 disjoint L1), schema path N = 4, 8, 32, 64, 2 reps, gate 160 MiB | candidate set = the N oldest L0 sstables only (L0 4.1 / 8.1 / 32.4 / 64.8 MiB at N = 4 / 8 / 32 / 64), no L1; 8/8 | `step3 small.schemaN*.rep*.gate160` |
| Same, gate 1 MiB | L0 = N and all 10 L1: count 14 / 18 / 42 / 74 = N + 10; output level 1; 8/8 | `step3 small.schemaN*.rep*.gate1` |
| Setter path N = 4 … 100, small class | same as the schema path; N = 100: L0 = 100 (no trim), no L1 at gate 160 | `step3 small.setterN*` |
| Large class (L0 sstables 21.3 MiB), N = 4 / 6 | L0 = 4 / 6 (81.1 / 121.6 MiB), no L1, count 4 / 6, output level 0 | `step3 large.setterN4, N6` |
| Large class, N = 8 / 12 / 32 / 64 / 100 | L0 = N (162.2 / 243.3 / 648.7 / 1,297.5 / 2,027.3 MiB) plus all 10 L1 (3.0 MiB): count 18 / 22 / 42 / 74 / 110, output level 1; the gate (160 MiB, strict) is crossed between N = 6 and 8 | `step3 large.setterN*` |
| STCS-in-L0 on versus off, all probes with both | identical candidate sets | `step3 *.stcsL0On/Off` (analysis P3) |
| 20 L0 sstables, N = 4 / 8 / 32 | L0 = 4 / 8 / 20 | `step3 small20.*` |
| Group fixture (25 groups of 4), N = 4 … 100 | L0 = min(N, 100) | `step3 groups.*` |
| STCS selector (positive control), small and large class, N = 4 … 100 | one bucket; chosen bucket = N sstables, bytes = N x the sstable size (large: 81.1 MiB at N = 4 … 2,027.3 MiB at N = 100) | `control *.stcs.N*` |
| Instrument: fixture overlaps, truncate | 4,950 / 1,000 / 0 pairs as designed (groups 150); truncate takes 106,236 B to 0 | `fixture`, `control truncate.*` |

**Cluster tier** — LCS fixture: 100 L0 sstables (97 of 67.3 MiB, one of 17.4, two of 92.5 and 101.8 MiB) and 9 L1 sstables (1,401.2 MiB); STCS fixture: 100 sstables of 67.3 MiB. Each row is the first task of a restored copy; sizes in MiB; "peak delta" = peak table-directory bytes in the task window minus the idle baseline (LCS 8,278; STCS 6,848).

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 4 | LCS | task inputs; bytes; peak delta; heap used | 13 = 4 L0 + 9 L1; 1,680.2 (L0 279.0, L1 1,401.2); 1,649; 908 | `run-lcs-N4/system-log-compaction-lines.txt`, `samples.jsonl` |
| N = 16 | LCS | same | 25 = 16 + 9; 2,488.0 (1,086.7 + 1,401.2); 2,441; 1,186 | `run-lcs-N16/…` |
| N = 32 | LCS | same | 41 = 32 + 9; 3,565.0 (2,163.7 + 1,401.2); 3,528; 1,282 | `run-lcs-N32/…` |
| N = 64 | LCS | same | 73 = 64 + 9; 5,719.0 (4,317.7 + 1,401.2); 5,828; 1,289 | `run-lcs-N64/…` |
| N = 4 / 16 / 32 / 64 | STCS control | inputs; bytes; peak delta; heap used | 4 / 16 / 32 / 64 = N; 269.2 / 1,077.0 / 2,154.0 / 4,308.0; 123 (under-sampled, D7) / 1,103 / 2,144 / 4,321; 892 / 1,018 / 1,216 / 1,281 | `run-stcs-N*/…` |
| all LCS | LCS | fit of input bytes against N | slope 67.3 MiB per N, offset 1,411 MiB (L1 bytes 1,401); peak delta slope 69.8, offset 1,337 | `analysis.txt` P3, P4 |
| all | both | which sstables were chosen | the LCS L0 inputs are the N lowest-generation L0 sstables; all 9 L1 sstables are inputs; exactly one task started before the first ended | `selfcheck.txt` C2, C3 |

Analysis output (`run1/cluster/analysis.txt`, as filed by the pre-written analyser): P1-P4, P6-P8, P10 pass; P5 (heap used spread 908-1,289 MiB, over 25%) and P9 (STCS N=4 peak delta per N 30.8 MiB against 65-69) fail; its coarse row mapping printed "STCS control does not move", which is wrong (P7, P8, P10 show it moves); see 4.2.

### 4.2 Conclusion and logic

1. **Validity** — Unit: valid; the fixtures are as designed (overlap counts) **[observed: `run1/unit/readings.txt` `fixture`]** and the instrument control (truncate) works **[observed: `control truncate.*`]**. Cluster: every restored fixture had 100 L0 + 9 L1 sstables (LCS) or 100 sstables (STCS), one compactor, throughput 0, threshold N read back **[observed: `run-*/tablestats-before.txt`, `cassandra.yaml.tail.txt`, `getcompactionthreshold.txt`]**; the LCS first tasks were L0 tasks with output level 1 and the limit was exceeded (100 L0 sstables against N <= 64) **[observed: `system-log-compaction-lines.txt`]**; 98 + 1 and 100 stress runs with 0 errors **[observed: `build-*/stress-errors.txt`]**. L1 held 9 sstables, not "about 10" (C3 states the offset as measured).
2. **Readings** — Unit: nothing unusual. Cluster: the heap (used, `GC.heap_info`) rose 908 → 1,289 MiB with N in the LCS runs and 892 → 1,281 in the STCS control, flattening at N = 32-64 near 1.28 GiB: a garbage ceiling, not live data **[observed: `samples.jsonl`; inferred: G1 used includes uncollected garbage]**. The STCS N=4 peak delta (123 MiB) is below its own input (269 MiB): the sampler took about one sample per 1.5 s over a 2.0 s task **[observed: `run-stcs-N4/samples.jsonl`, `meta.json`; inferred: sampling gap]**.
3. **Matched row** — Unit B2g row 2: "L0 count = N but total count > N and bytes include an L1 jump not proportional to N, while the STCS control's count stays <= N and its bytes scale as N x size" **[observed: `run1/unit/readings.txt`, `analysis.txt`: P1-P8 pass]**. Cluster B3g: the Confirmed row asks for "LCS count = N + about 10 and peak disk has the fixed L1 offset, heap about flat across N, while STCS control scales with N". Count = N + 9 and the fixed offset (1,411 MiB against L1 1,401; peak 1,337) hold, the control scales **[observed: `analysis.txt` P1-P4, P7, P8]**, but the heap reading (used, with garbage) is not flat. **Run 1 therefore has no fully matching cluster row: Not confirmed (no matching row)**; the unmatched part is an instrument limit (D7), settled by run 2 in §6.
4. **Excluded rows** — Unit: "count <= N and bytes <= N x size" (Refuted): counts reach N + 10 and the L1 bytes are added beyond N x size **[observed: `step3 *.candidateCount`]**; "L0 count > N": never (58 probes); "L0 count < N / gate never crossed": the gate is crossed in 23 probes; "STCS control does not scale": it equals N. Cluster: "task input count <= N and peak delta <= N x file size" (Refuted): counts 13 / 25 / 41 / 73 > N and peak delta exceeds N x 67.3 MiB by about 1.4 GiB **[observed: `analysis.txt` P2, P6]**; "fewer than N L0 files overlap or a higher-level first task": no (L0 inputs = N, output level 1); "STCS control does not move with N": it moves (count = N, 67.3 MiB per N).
5. **Observed vs. inferred** — Inferred: that the heap used is garbage-dominated (D7); that the STCS N=4 delta is a sampling gap; that the L0 candidate bytes in the unit tier, the same code with small L1 files, carry to the cluster tier (the cluster tier reads the real task).
6. **Deviations and gaps** — tmpfs instead of a disk filesystem; L1 = 9 sstables of the fixture (not 10); L0 sstables not equal (17.4 / 92.5 / 101.8 MiB beside 97 of 67.3); table created by `cqlsh` in the stress layout; the "N = 32 with 20 L0 files" reference not run (C4); STCS control on a separate fixture (C5); the task window is taken from the `Compacting`/`Compacted` log lines (millisecond stamps) and the sampler is 1.5 s coarse; heap is a proxy in run 1.
7. **Core question** — Raising N from 4 to 64 raised the task's input and peak transient bytes about linearly (67-70 MiB per N, the same slope as the STCS control), so the knob does bound the L0 part. But the compaction always appended all 9 L1 sstables (1.4 GiB), a fixed offset the knob does not touch, and the input count was N + 9 at every N **[steps 1-4]**. The constraint caps the L0 sstable count, not the task: it caps on the L0 path and is bypassed by the L1 overlap.

**Conclusion (one line):** unit B2g row 2 — Confirmed; cluster B3g — **Not confirmed (no matching row)** at run 1 (heap-used proxy not flat); settled by run 2 (§6, §8).

## 5. Self-check of run 1 — AI

`harness/…/selfcheck.py` (output `run1/selfcheck-run1.txt`) re-derives the claims without the analysis scripts: the unit tier from the console echo of the readings in `ant.log` (772 readings identical to `readings.txt`) and the pinned source lines 548/551/557/567; the cluster tier from the raw `system.log` `Compacting (` entries (levels split, generation order of the chosen L0 sstables), `tablestats-before.txt`, `files-before.json`, `cassandra.yaml.used`, `getcompactionthreshold.txt`, `samples.jsonl` and the stress outputs. all unit claims (U0-U8) and, in every cluster run, C0-C3 hold, as do the fits C4 and C5 and the build checks C7-C8; **C6 (STCS control peak bytes per N constant) does not hold in run 1** (N=4: 30.8 MiB per N against 65-69), the sampling gap of D7, cleared in run 2 (`run2/selfcheck-run2.txt`: C6 holds).

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0-U1, U7 (readings and fixtures), C0-C2 (settings, restored fixture, one task), C7-C8 (stress, clean stops). |
| 2. Readings | yes | The unit readings equal the console echo (U0). The cluster oddities (heap used, STCS N=4 delta) are real features of the samples, recorded as D7; C6 does not hold, as stated. |
| 3. Matched row | yes | U2-U6 (unit row 2), C3 (count = N + 9 and the oldest N), C4/C5 (offset), C3 stcs. The unmatched heap clause is the reason for "Not confirmed (no matching row)" at run 1. |
| 4. Excluded rows | yes | U2, U4 (counts above N), C3, C4 (bytes above N x size by the L1 offset). |
| 5. Observed vs. inferred | yes | The garbage-dominated heap is inferred; run 2 measures the live heap directly. |
| 6. Deviations and gaps | yes | All listed in 4.2 part 6 and §3. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1: L0 part capped by count (P1), L1 added beyond N (P2), offset fixed (P3/P4), control scales (P7/P8). |

### 5.2 Run 2?

**Yes** — decided 2026-10-26 after run 1's readings. It is cheap (about 15 min, the fixtures still on the tmpfs) and clearly needed: the Confirmed row of B3g needs a flat heap and the run-1 heap instrument cannot read live data, and one control reading was under-sampled (D7). Scope: the same fixtures, the same four N values and order, the same protocol, with only the sampler changed (0.25 s bytes, `RssAnon`, live heap by `GC.class_histogram` every 2-3 s). No prediction or row was changed. It is the same session, so it re-measures but is not an independent reading of the reasoning.

## 6. Run 2 — same session, sampler v2

**Scope:** cluster tier only (the unit tier has no heap or timing observable and needs no re-run), N = 32, 4, 64, 16, LCS and STCS control. **Command log:** `run2/cluster/run-*/commands.log`.

### 6.1 Readings

**Cluster tier** (sizes in MiB; baseline LCS 8,278, STCS 6,848; live heap idle baseline 82.7)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| N = 4 / 16 / 32 / 64 | LCS | inputs; peak delta; live heap peak; task seconds | 13 / 25 / 41 / 73 (= N + 9); 1,709 / 2,533 / 3,619 / 5,841; 90.1 / 91.0 / 92.8 / 96.6; 13.1 / 23.5 / 41.0 / 86.9 | `run2/cluster/run-lcs-N*/` |
| N = 4 / 16 / 32 / 64 | STCS control | inputs; peak delta; live heap peak; task seconds | 4 / 16 / 32 / 64 (= N); 263 / 1,099 / 2,197 / 4,414; 85.8 / 88.2 / 88.7 / 89.6; 2.8 / 9.6 / 21.2 / 60.3 | `run2/cluster/run-stcs-N*/` |
| fit | LCS | input bytes; peak delta | slope 67.3 MiB per N, offset 1,411 MiB; peak slope 68.9, offset 1,429 (L1 1,401) | `run2/cluster/analysis.txt` |
| per N | STCS control | peak delta per N | 65.8 / 68.7 / 68.7 / 69.0 | `analysis.txt` P9 |

### 6.2 Matched row

B3g Confirmed: "LCS task input count = N + L1 count and peak disk has the fixed L1 offset, heap about flat across N, while STCS control scales with N" — all of P1-P10 pass in run 2 (`run2/cluster/analysis.txt`, `selfcheck-run2.txt`: all hold, C9 live heap 90-97 MiB, spread 7%, far below the 2 GiB heap).

## 7. Comparison — only if run 2 was done

| Observable | Run 1 | Run 2 | Criterion (§1) | Agree? |
|---|---|---|---|---|
| first-task inputs (LCS) | 13 / 25 / 41 / 73 | 13 / 25 / 41 / 73 | exactly | yes |
| first-task inputs (STCS) | 4 / 16 / 32 / 64 | 4 / 16 / 32 / 64 | exactly | yes |
| input bytes | 1,680.2 / 2,488.0 / 3,565.0 / 5,719.0 | same | exactly | yes |
| LCS input fit | slope 67.3, offset 1,411 | slope 67.3, offset 1,411 | within 5% | yes |
| LCS peak delta fit | slope 69.8, offset 1,337 | slope 68.9, offset 1,429 | offset within 30% of L1; slope 5% | yes (slope 1.3%) |
| STCS peak delta N = 16 / 32 / 64 | 1,103 / 2,144 / 4,321 | 1,099 / 2,197 / 4,414 | 5% | yes (largest 2.2%) |
| STCS peak delta N = 4 | 123 (under-sampled) | 263 | not required (D7) | not compared |
| heap | 908-1,289 used | 90-97 live | not compared | n/a |

**Same §9a row?** The cluster tier moves from "no matching row" (run 1, heap-used proxy) to B3g Confirmed (run 2, live heap). The cause of the difference is the heap instrument (D7), not the workload: the counts, bytes and offsets are identical.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** false negative (negative, `caps only on some paths (bypass)` counts as caps). This class is the least certain part of the verdict: see "Overrule point".

**Claim tested:** raising or lowering `max_threshold` does not make the peak compaction input bytes (and so the peak transient disk and the compaction heap) track it: the L0 part is bounded only in count and the L1 overlap is added on top; a compaction selected with N can contain more than N sstables and more bytes than N times the L0 sstable size (B1). "Confirmed" means this claim held (as the B2g and B3g rows word it: count N + L1, a fixed L1 offset, flat heap, and a control that scales).

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g "L0 count = N but total count > N and bytes include an L1 jump not proportional to N, while the STCS control's count stays <= N and its bytes scale as N x size" | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed — B3g "LCS task input count = N + L1 count and peak disk has the fixed L1 offset, heap about flat across N, while STCS control scales with N" (run 1: Not confirmed, no matching row, heap-used proxy; run 2: all clauses hold) | caps only on some paths (bypass) | run 1 + run 2 + self-check | 2026-10-26 |

**Positive control** (a negative-estimate file only): the STCS selector with the same workload and instruments moved with N: unit bucket size = N for N = 4 … 100 (81.1 → 2,027.3 MiB large class); cluster input count = N, 67.3 MiB per N, peak bytes 65.8-69.0 MiB per N, live heap flat. The same slope appears in the LCS L0 part (67.3 MiB per N), so the count cap does bind there; what the control does not show is a cap on the L1 term.

**Overrule point.** The measured usage is 68.9 MiB x N + 1.43 GiB: it follows N linearly (the L0 part is capped) with an additive 1.4 GiB the knob never limits (all L1 sstables overlapped by the L0 inputs, up to the L1 target of 10 x `sstable_size_in_mb`; the L0 sstable size is also unbounded). I classed this as `caps only on some paths (bypass)`, which the outcome-class rule counts as caps, so the negative estimate is a false negative. If the reader weighs the unbounded L1 offset and the unbounded L0 size more than the linear L0 term, the effect would be `does not cap` and the class true negative; the readings do not change either way.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the orchestrator commits); amendments U1-U5, C1-C6 in the case file, all before any reading of their tier; no other section amended. `_INDEX.md`, `predicted-negative.md`, `writeup-set-A.csv`, HANDOFF files not touched.

**What stays on `pc12` after the session** (nothing is running; the `/mnt/s4lc` tmpfs is unmounted and its directory is empty): `~/s4-b10-lc` (475 MB, the built tree the cluster node ran from), `~/s4-b10-lc-unit` (473 MB, the unit-test tree), `~/s4-b10-lc-logs/` (91 MB: `unit-run1/`, `cluster/`, `cluster2/`, `cluster-aborted1/`, `shake/`, `unit-shake*/`, `compile/`, build and chain logs), the shared `~/.m2`.
