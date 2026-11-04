# commitlog_segment_size-allocate-endOfBuffer--autonomous — stage-4 results  <!-- file: results/commitlog_segment_size-allocate-endOfBuffer--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`commitlog_segment_size-allocate-endOfBuffer--autonomous`](../../stage3-ai-deep-read/cases/commitlog_segment_size-allocate-endOfBuffer--autonomous.md)
>
> **Status:** verdict filed (2026-10-23) — run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true positive** (estimate `positive`, effect `caps`) — [definition](../README.md#outcome-class)
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
| **Case-file version** | Base repository commit `c765cea` (the case file is **untracked** in the working tree at this date, so no commit holds it; the human closes the commit). **sha256 of the whole file after the audit's amendments (B2i, dated 2026-10-23): `90bef1e6a2eb1ed36cc8773149cffff99c211f59b150897dfba7ef395216d071`.** Recorded 2026-10-23 before any reading; the prediction tables (B2f, B2g, B3f, B3g, as amended) are frozen at this hash. The hash covers the file as it stood before section D (the stage-4 feedback) was filled; D is the only later change. |
| **Harness** | `harness/commitlog_segment_size-allocate-endOfBuffer--autonomous/`: `SegmentSizeCapTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.sh`, `cluster-chain.sh`, `sampler.py`, `loader.py`, `analyze_cluster.py`, `selfcheck.sh`, `README.md`; written after the freeze; not committed (md5s of the node copies: `commitlog_segment_size-allocate-endOfBuffer--autonomous/run1/harness.md5`) |
| **Tiers and values** | **Unit (B2):** `S` ∈ {1, 2, 8, 32} MiB × {mmap, LZ4 + standard}, `E` = 64 KiB (plus `E` = 16 KiB at `S` = 8), one repeat, boundary / exact-edge (B2i.4) / oversize probes. **Cluster (B3):** `S` ∈ {8, 32, 128} MiB (mmap), `commitlog_total_space` 4096 MiB; positive control `S` = 8 with `commitlog_total_space` 64 MiB; LZ4 arm at `S` = 32; compressible-value arm; idle baseline. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-23 |

### 1.1 Design audit

Estimate: **positive (scoped to one segment)**. The file's claim (B1) is that no segment reserves a byte at or beyond `commitlog_segment_size`; it does not claim a cap on the directory. Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `c765cea`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `Config.java:396-397`, `DatabaseDescriptor.java:891-901, 2875-2889, 664-675`, `CommitLogSegment.java:177, 201-255, 258-287, 421-424, 565-572, 609-620, 748-751`, `MemoryMappedSegment.java:62-63, 103-106`, `CompressedSegment.java:44-96, 113-117`, `EncryptedSegment.java:176`, `DirectIOSegment.java:201-219`, `CommitLog.java:304`, `Mutation.java:169-176`, `IMutation.java:31`, `CommitLogSegmentManagerStandard.java:47-60`, `AbstractCommitLogSegmentManager.java:296-335`: all hold at the cited lines (small range corrections noted in the amendments).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: segment file bytes (disk) and the segment buffer; the claim is explicitly per segment, not the directory. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 1, 2, 8, 32 MiB (32 = default); B3b: 8, 32, 128 MiB. |
| A. Core question | real resource measured, not only the counter | Met | B2d file lengths, `buffer.capacity()`; B3d `stat` of files and `/proc/<pid>/maps` (B2i.5). The check's operand `allocatePosition` is read too; the gap (operand is bytes of plaintext stream) is named in A2. |
| A. Core question | usage driven to the limit and past it | Met | B2c: ≥ 3 × S of entries, exact-edge probes at `next == capacity - 1` and `== capacity` (B2i.4); B3c: 600 MiB against S = 8, 32, 128 (75, 19, 4.7 rollovers). |
| B. Logic | each step says what it establishes | Met | B2e / B3e list steps with purpose; B1 states what is and is not claimed. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met | B2f / B3f are numeric; three predictions contradicted the source (compressed file length, retired-segment positions or direct capacity) and are amended in B2i before any reading. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly → Met | B2g / B3g cover refute, flat, workload-too-small; B2i adds the compressed expansion rows. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2f/B2g: offsets below `S` for every `S` and the rollover (disallow) count growing as `S` shrinks; B2i adds the exact-edge probe on the `>=` itself. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: vary only the knob, `E` variation, positive control `commitlog_total_space`, compressed vs mmap. |
| C. Specific | a human can follow it from the intro and B1 | Met | A3 and B1 are clear. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly → Met | The setter-vs-yaml pitfall, closed-segment `buffer == null`, and the exact payload sizes were not stated; supplied in B2i. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met | Commands use `/users/jason92/cassandra-5.0.9` or `/tmp` paths that do not exist here; the runs use a `copy-source.sh` tree and `$HOME/stage4-seg/`. Not a design change (environment deviation, §2). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `ant build-test` tree, `cassandra-stress`, `nodetool sjk`, bundled Python driver, `jcmd`; unit test and scripts are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | See group A. Disk on pc12 `/` (53 GB free): at most about 4 GiB per cluster arm; spinning disk, so cluster rates are modest. |
| D. Runnable | load-bearing citations spot-checked | Met | List above. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Set the knob through a per-arm yaml, not `setCommitLogSegmentSize`; one JVM per arm | Applied, B2i.1, 2026-10-23 (case file untracked; sha256 above) | The setter leaves `max_mutation_size` at the test yaml's value and `IMutation.MAX_MUTATION_SIZE` is static final. |
| 2 | Read retired-segment `endOfBuffer` and the add return positions; record `capacity` at first sight | Applied, B2i.2 | `discardUnusedTail()` assigns `endOfBuffer = prev` after setting `allocatePosition = old endOfBuffer + 1`; a closed segment's `buffer` is null. |
| 3 | Compressed-mode file length is not capped by `S`; bound is the plaintext cap plus LZ4 expansion | Applied, B2i.3 | Incompressible blocks expand; B2f / B2g / B3f would otherwise Refute on a source-predictable effect. |
| 4 | Add the exact-edge probe (`next == capacity - 1` stays, `next == capacity` rolls) | Applied, B2i.4 | The target line is `>=`; B2c only reached "within E". |
| 5 | Payload sizes made exact; cluster file-size reading tolerant of a not-yet-mapped file; off-heap via maps/NMT | Applied, B2i.5 | Ambiguity in the filed text. |
| 6 | Paths in B2a/B3a refer to nonexistent trees; commit-ready sections of the file refer to `~/writeup-A` | Left for stage 3 | Cosmetic for this case. |
| 7 | The filed estimate calls the segment size a cap on "memory" for compressed modes; the compressed file is not capped by it (B2i.3) | Left for stage 3 | Wording. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-23 (unit 09:44–09:47 MDT, cluster chain 09:50–10:10 MDT, one arm re-run 10:06–10:09) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/stage4-seg/treeA` made by `copy-source.sh` from repository commit `c765cea` (source rsynced to `~/stage4-seg/src`; tree baseline `git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 10 s; `SegmentSizeCapTest.java` added and compiled (11 s). The cluster node ran from this tree's `build/`. Nothing built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `c765cea` (sha256 `90bef1e6…d071`, §1); harness uncommitted (final md5s of the node copy in `run1/harness.md5`; `harness.md5.at-chain-start` is the earlier set, before the loader fix to `cluster-run.sh`) | |
| Storage for node data | `/dev/sda3`, ext3, rotational, 63 GB (53 GB free); node data and commit log under `~/stage4-seg/nodeA`, unit commit log under `treeA/build/test/cassandra` | |
| Full logs (path, outside the repo) | `pc12:~/stage4-seg/runA/{unit,cluster}/` (full `system.log`, `debug.log.gz`, stress logs), `pc12:~/stage4-seg/logs/` (builds); excerpts in `commitlog_segment_size-allocate-endOfBuffer--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed paths (`/users/jason92/cassandra-5.0.9`, `/tmp/...`, `/local/work/...`) do not exist; the tree and data are under `~/stage4-seg/` on local disk. (2) The cluster yaml adds `memtable_cleanup_threshold: 0.9` (B3a gives 2048 MiB of memtable heap to avoid flushes, but the default threshold of 0.5 would flush at 1 GiB); no non-system flush occurred in the three uncontrolled mmap arms (§4.1). (3) Stress values are `size=FIXED(1000)` (1,000-byte blobs; B3c says 1 KiB). (4) The unit yaml sets `memtable_heap_space: 600MiB`, `memtable_cleanup_threshold: 0.95`, `commitlog_sync_period: 1h` (B2i.4 needs a quiet sync thread); no unit flush and no deleted segment occurred (`reasons.txt`, 11 arms). (5) The CommitLog `OversizedMutations` MBean named in B3d was not found (`oversized.txt`); the oversize probe is read from the unit tier only. (6) `ulimit -n` was raised to 100000 in the shell that starts the node.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, cluster | B2i.5 compressible arm (`loader.py`) | The first attempt (`attempt1-lz4zero-s32-loader-import-failed/`) died with `ModuleNotFoundError: cassandra`: the bundled driver zip nests the package under `cassandra-driver-3.29.0/`, so the zip itself is not a path entry. No row was read from it. | The zip is unpacked once to `~/stage4-seg/driver/` and `loader.py` gets the inner directory (harness only, `cluster-run.sh`). The arm was re-run from its beginning. | 2026-10-23: harness fix, case file unchanged | none (harness) |
| 2 | 1, unit | B2g "Rollover count does not grow as S shrinks … not confirmed" | B2c sizes the adds as `ceil(3 S / E) + 10`, so the main workload rolls about 3 times at every `S`; with the five probe segments the count is 8 at every `S`. The row's literal condition is met by the filed workload, while its stated cause (the limit was not reached) is not. | None: the frozen row is not edited. §4.2 part 4 addresses it with direct evidence that every retired segment was retired by `allocate()` failing at the limit. Reported to stage 3 in section D. | 2026-10-23 | none |
| 3 | 1, cluster | B3d `OversizedMutations` metric | `MBean not found: ...type=CommitLog,name=OversizedMutations`. | None; the unit tier reads `oversizedMutations` from `CommitLog.instance.metrics`. | 2026-10-23 | none |

## 4. Run 1

**Scope:** unit tier, 11 arms (S = 1, 2, 8, 32 MiB × mmap and LZ4+standard at E = 64 KiB; S = 8 mmap with E = 16 KiB; S = 8 LZ4 with repeated-byte payload; a repeat of S = 8 mmap); cluster tier, 7 arms (S = 8, 32, 128 mmap at total space 4096 MiB; control S = 8 at total space 64 MiB; LZ4 at S = 32; compressible-value LZ4 at S = 32; idle at S = 32). **Command log:** `commitlog_segment_size-allocate-endOfBuffer--autonomous/run1/unit/session.log`, `run1/chain.log`, `run1/cluster/<arm>/session.log`; analyzer output `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/analyze_unit.out`, `run1/unit/<arm>/seg.csv`, `seg.summary`). Every arm: 8 segments, `violations=0` (no returned end offset ≥ capacity), JUnit 1 test, 0 failures, no flush, no deleted segment.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `buffer.capacity() == S·2^20` for every segment, S = 1, 2, 8, 32, both modes | holds in all 11 arms (88 segments) | `unit/*/seg.csv` col `capacity` |
| Every add's returned end offset < capacity; max observed | 1,048,575 / 2,097,151 / 8,388,607 / 33,554,431 = `S·2^20 − 1` in all modes | `unit/*/seg.summary`, `seg.csv` col `maxEnd` |
| Retired segments: `endOfBuffer < capacity`, `allocatePosition == capacity + 1`, `isStillAllocating()` false | holds for every retired segment in all arms | `seg.csv` cols `endOfBuffer`, `allocatePosition`, `stillAllocating` |
| mmap `fileLength == onDiskSize() == S·2^20` for every segment | holds (S = 1, 2, 8, 32, E = 16 KiB, repeat) | `seg.csv` cols `fileLength`, `onDiskSize` |
| LZ4 `fileLength` against `S·2^20 + ceil(S·2^20/255) + 32·blocks + 64` | within the bound in all arms; above `S·2^20` in 1 segment (S = 1, 2, 8) and 6 segments (S = 32), by at most 0.39 % (max 33,686,042 B at S = 32, 1.0039 × S); repeated-byte payload: max 43,142 B at S = 8 (0.5 % of S) | `seg.csv`, `analyze_unit.out` |
| Max-accepted mutation (total = `max_mutation_size` = S/2) | accepted in all arms | `seg.summary` `PROBE max-accepted` |
| Oversize (S/2 + 1) | `MutationExceededMaxSizeException`, `oversizedMutations` +1, `allocatePosition` unchanged, same segment, all arms | `PROBE oversize` |
| Exact-edge (a): entry total = `remaining − 1` | stays in the segment, `allocatePosition == capacity − 1` in all 11 arms | `PROBE edge-a` |
| Exact-edge (b): entry total = `remaining` | refused, the add returned a position in the next segment, old `endOfBuffer == capacity − remaining`, old `allocatePosition == capacity + 1` in all 11 arms | `PROBE edge-b` |
| Scaling | capacity and max offset scale 1 : 2 : 8 : 32 with the knob | `analyze_unit.out` |
| Control assertion `capacity == (S+1) MiB` | false in all arms | `analyze_unit.out` |
| Repeat (`s8-mmap` vs `s8-mmap-rep`) | identical capacity, max offset, file lengths, segment count; the edge probes' `remaining` differ by 8 B (one more sync marker allocated before the probe) | `unit/s8-mmap*/seg.summary` |

**Cluster tier** (`run1/analyze_cluster.out`; sampler every 0.25 s, `stat` sizes):

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| S = 8 MiB, total 4096 | A | largest file; files created; peak files; peak total (stat = JMX) | 8,388,608 B (= S); 82 created; 84; 672 MiB (= 84 × 8) | `cluster/s8/` |
| S = 32 MiB, total 4096 | A | same | 33,554,432 B (= S); 20 created; 22; 704 MiB (= 22 × 32) | `cluster/s32/` |
| S = 128 MiB, total 4096 | A | same | 134,217,728 B (= S); 5 created; 7; 896 MiB (= 7 × 128) | `cluster/s128/` |
| three values | A | ratio of largest file | 1 : 4 : 16 | `analyze_cluster.out` |
| S = 8 MiB, total 64 | control | peak files / peak dir (stat) / JMX peak / non-system flushes | 16 files; 128 MiB; 88 MiB; 11 `COMMITLOG_DIRTY` flushes of `keyspace1.standard1`; largest file 8 MiB | `cluster/ctl-s8-t64/` |
| S = 32, LZ4 (stress values, partly compressible) | B | largest file | 32,601,662 B (31.09 MiB, below S); 20 created; no mappings in `/proc/<pid>/maps` | `cluster/lz4-s32/` |
| S = 32, LZ4, repeated-byte values | B | largest file | 674,417 B (0.64 MiB, 2 % of S); 18 created; attempt 1 failed (defect 1) | `cluster/lz4zero-s32/` |
| S = 32, no load | idle baseline | files at rest | 2 files of 33,554,432 B (active + prepared); JMX 64 MiB | `cluster/idle-s32/` |
| mmap arms | A | `/proc/<pid>/maps` `CommitLog-*.log` mappings | peak 3 × 8 MiB, 2 × 32 MiB, 2 × 128 MiB | `ds.csv` cols `maps_*` |

Non-system flushes in the uncontrolled mmap and LZ4 arms: none (`counts.txt`); stress `Total errors: 0` in all stress arms.

### 4.2 Conclusion and logic

1. **Validity** — valid. The knob took effect: `commitlog_segment_size=<S>MiB` in each node's `system.log` and the unit `capacity` equals it [observed: the CONFIG lines in `cluster/*/session.log`; `unit/*/seg.csv`]. The limit was reached: every retired segment ended at `endOfBuffer < capacity` with `allocatePosition == capacity + 1`, i.e. it was closed after a failed `allocate()`, and exact-edge probe (a) filled a segment to `capacity − 1` [observed: `seg.csv`, `PROBE edge-a`]. Held-fixed settings: sync period, memtable limits and total space as in §2; no flush and no deleted segment in the unit arms and no non-system flush in the uncontrolled cluster arms [observed: `reasons.txt`, `counts.txt`].
2. **Readings** — one analyzer parse miss and one loader import failure, both in the harness and fixed before the readings used (shakedown; defect 1). The control arm's peak (128 MiB) is above its frozen prediction (part 4).
3. **Matched row** — unit B2g row 1 (*All `maxPosition < S·2^20`, `capacity == S·2^20`, mmap `fileLength == S·2^20` → claim supported*): max offset `S·2^20 − 1` in 11 of 11 arms, capacity exact, mmap file length exact [observed], with the amended compressed rows (B2i.3): LZ4 files above `S·2^20` stay within the stated bound, so they are expected expansion, not a refutation. The amended exact-edge predictions (B2i.4 a and b) hold [observed]. Cluster B3g row 1 (*max file = S MiB in all three runs → claim supported at the real resource*): 8 / 32 / 128 MiB, ratio 1 : 4 : 16, no larger file in any sample of any arm [observed: `analyze_cluster.out`]. B3g "directory total > S: expected, not a refutation" also matches (672, 704, 896 MiB, whole multiples of S).
4. **Excluded rows** — *any `maxPosition ≥ S·2^20` or file > S (mmap)*: none; `violations=0` and `maxEnd` < capacity in 88 segments; the largest cluster file equals S. *`capacity != S·2^20`*: none. *Compressed file above the bound*: none (max 1.0039 × S against the allowed 1 + 1/255 + 32 B per sync). *Rollover count does not grow as S shrinks / limit not reached* (unit B2g row 5): the count is 8 at every S because B2c scales `n` with S (defect 2); the stated cause is excluded because every retired segment was closed by a failed `allocate()` at the limit, and cluster rolls (82, 20, 5) match the frozen "about 75, 19, 5". *Oversize mutation accepted*: it was refused. *Max file same across S* (cluster): no, 1 : 4 : 16. *Control total unchanged vs uncontrolled* (cluster row 6): no, 128 MiB against 672 MiB, so the workload does move usage. The cluster control row "≈ 64 MiB + spare" is only partly met: the frozen prediction was "up to about 80 MiB" and the peak directory was 128 MiB by `stat` (88 MiB by the JMX gauge sampled at 1 s), a miss of the control's magnitude (a 2 × overshoot of the soft total; reclaim lags a 40 MB/s writer), not of the claim; reported, not tuned.
5. **Observed vs. inferred** — **[inferred: the maximum offset `S·2^20 − 1` shows the `>=` test is what stops writes]**; the exact-edge probes make this direct: an entry ending at `capacity − 1` is accepted and one ending at `capacity` is refused [observed]. **[inferred: the cluster files are the segments the unit tier measured]**: same code path, different harness. **[inferred: no transient file larger than S between samples]**: the sampler is 0.25 s; the inference rests on mmap files being created at S by `channel.map` (`MemoryMappedSegment.java:62`) and no sample ever showing a larger one.
6. **Deviations and gaps** — §2 deviations 1 to 6 and §3. Direct I/O is not in this file's B2 (it is in the sibling case). The `OversizedMutations` gauge could not be read. The LZ4 cluster arm's stress data compressed slightly (31.09 MiB files), so LZ4 file expansion was observed only in the unit tier. Peak counts and totals are of live files at 0.25 s resolution.
7. **Core question** — Usage followed the constraint. In 88 unit segments and every cluster sample, no segment reserved or held a byte at or beyond `commitlog_segment_size` (mmap file length exactly S; offsets at most S − 1; the edge probe stops at `next == capacity`), and the largest file scaled 1 : 4 : 16 with the knob (parts 1 and 3). The constraint caps the per-segment resource. It does not cap the directory (672 to 896 MiB at 8 to 128 MiB segments), which is B1's explicit non-claim, and in LZ4 mode it caps the plaintext offset while the file can exceed S by up to the LZ4 expansion (0.39 % observed).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (per-segment cap holds; amended compressed and exact-edge rows hold) — confirmed; the cluster control's magnitude is outside its frozen prediction, recorded.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the unit and cluster numbers from the raw CSVs, `final-ls.txt` and `system.log` with awk / grep (no shared code with `analyze_*.py`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: `conf: commitlog_segment_size=<S>MiB` in each unit log and `segment_size=<S>MiB` in each node `system.log`; `FLUSHES 0` and `SEGMENT_DELETED_LINES 0` in all 11 `reasons.txt`; no non-system flush reasons outside the control arm; stress errors 0. |
| 2. Readings | yes | awk: unit `cap!=S:0 maxEnd>=cap:0 retiredBad:0` for all 11 arms; `files>S` is 0 for mmap and the zero-fill LZ4 arm, 1 / 1 / 1 / 6 for LZ4 at 1 / 2 / 8 / 32 MiB (the analyzer's counts); cluster maxfile / peak files / peak total equal the analyzer's for every arm. |
| 3. Matched row | yes | Rows quoted from the case file's B2g / B3g as amended; each part cited is in the raw files (`seg.csv`, `seg.summary`, `ds.csv`, `final-ls.txt`). |
| 4. Excluded rows | yes | The "rollover" row is addressed by direct evidence (retired-segment states) rather than by its own cause; the control row is not excused (stated as a miss of magnitude). |
| 5. Observed vs. inferred | yes | The edge probes turn the `>=` inference into an observation; the transient-file inference is stated with its basis. |
| 6. Deviations and gaps | yes | All listed; the missing oversize gauge does not affect B1 (the unit tier reads it). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 is per segment and the readings are per segment; the directory non-claim is checked against the 672 to 896 MiB totals. |

### 5.2 Run 2?

**No** — decided 2026-10-23. The conclusion rests on direct measurements at both tiers (exact offsets, exact file sizes, an exact-edge probe on the `>=` itself); the self-check re-derived them with independent code; the repeat arm reproduced the unit numbers; and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped to one segment). **Outcome class:** **true positive** (positive, caps).

**Claim tested:** B1 — with `commitlog_segment_size = S`, no segment accepts an entry that would place its end at or beyond `S` bytes; the in-segment write offset never reaches `S`, a new segment is started instead, and (mmap, direct) the file size never exceeds `S`. Per segment; not a claim about the directory. As amended 2026-10-23 for compressed modes (cap on the plaintext offset; file length within the LZ4 expansion).

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (+ amended compressed and exact-edge rows) | caps | run 1 + self-check | 2026-10-23 |
| Cluster | Confirmed — B3g row 1 (control magnitude outside its frozen prediction, recorded) | caps | run 1 + self-check | 2026-10-23 |

**Positive control** (a negative-estimate file only): not required (positive estimate). The file's own control (`commitlog_total_space` 64 MiB at S = 8) moved the directory from 672 MiB (uncontrolled) to a 128 MiB peak, showing the workload and sampler can see a binding limit; the per-segment maximum stayed 8 MiB in both.

**Feedback filed:** the case file's section D updated (the case file is untracked; no commit). No section amended beyond the audit's B2i. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` were not touched (the human closes them).

## 9. What stays on pc12 for this case

No `CassandraDaemon`, `ant`, sampler or stress process (checked 2026-10-23 after the last arm). Kept: `~/stage4-seg/treeA` (source copy, build, the test class, the last unit arm's commit logs under `build/test/cassandra`), `~/stage4-seg/src`, `~/stage4-seg/driver`, `~/stage4-seg/harnessA`, `~/stage4-seg/runA` (unit and cluster logs), `~/stage4-seg/logs`, `~/stage4-seg/shakeA`. The node data directory `~/stage4-seg/nodeA` was wiped by the script. The listed `~/stage4-seg/` folders are shared with the sibling case's tree (`treeB`, `runB`, `harnessB`).
