# commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous — stage-4 results  <!-- file: results/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous`](../../stage3-ai-deep-read/cases/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous.md)
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
| **Case-file version** | Base repository commit `c765cea` (the case file is **untracked** in the working tree at this date, so no commit holds it; the human closes the commit). **sha256 of the whole file after the audit's amendments (B2i, dated 2026-10-23): `df551bcd9ea44616670d3a9bb14016f8fa1d51c8edf7b7a18f726c48e48276fc`.** Recorded 2026-10-23 before any reading; the prediction tables (B2f, B2g, B3f, B3g, as amended) are frozen at this hash. The hash covers the file as it stood before section D (the stage-4 feedback) was filled; D is the only later change. |
| **Harness** | `harness/commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous/`: `SegmentCapProbeTest.java`, `unit-run.sh`, `analyze_unit.py`, `cluster-run.sh`, `cluster-chain.sh`, `sampler.py`, `analyze_cluster.py`, `selfcheck.sh`, `README.md` (`loader.py` copied, unused); written after the freeze; not committed (md5s of the node copies: `commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous/run1/harness.md5`) |
| **Tiers and values** | **Unit (B2):** `n` ∈ {1, 4, 32} MiB × {mmap, LZ4 + standard, direct if the volume supports it}, 64 random-payload adds per arm, boundary and oversize mutations. **Cluster (B3):** `n` ∈ {8, 32, 64} MiB (mmap), `commitlog_total_space` 1024 MiB, stress `n` = 2,000,000; LZ4 series at 32; positive control `commitlog_total_space` 256 MiB at 32. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-23 |

### 1.1 Design audit

Estimate: **positive (scoped to one segment)**. The file's claim (B1) is that no segment reserves a byte at or beyond `commitlog_segment_size`; it does not claim a cap on the directory. Audited against `cassandra/cassandra-5.0.9/` (`git status` of it clean at `c765cea`; `build.xml` `base.version` 5.0.9). Citations re-read in the pinned source: `Config.java:396-397`, `DatabaseDescriptor.java:891-901, 2875-2889, 664-675`, `CommitLogSegment.java:177, 201-255, 258-287, 421-424, 565-572, 609-620, 748-751`, `MemoryMappedSegment.java:62-63, 103-106`, `CompressedSegment.java:44-96, 113-117`, `EncryptedSegment.java:176`, `DirectIOSegment.java:201-219`, `CommitLog.java:304`, `Mutation.java:169-176`, `IMutation.java:31`, `CommitLogSegmentManagerStandard.java:47-60`, `AbstractCommitLogSegmentManager.java:296-335`: all hold at the cited lines (small range corrections noted in the amendments).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: segment file size and the per-segment buffer (off-heap or heap); the claim is per segment, the total is stated as only softly bounded. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 1, 4, 32 MiB; B3b: 8, 32 (default), 64 MiB. |
| A. Core question | real resource measured, not only the counter | Met | B2d file lengths, `buffer.capacity()`, `endOfBuffer`, `allocatePosition`; B3d file sizes, `TotalCommitLogSize`, `pmap`/NMT (B2i.7). |
| A. Core question | usage driven to the limit and past it | Met | B2c: 64 adds of `n/16` = 4 × the cap in total, plus the boundary mutation; B3c: 2.1 GiB against 1 GiB total space, 34 to 270 rolls. |
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
| 2 | Retired-segment prediction `allocatePosition == capacity + 1`, `endOfBuffer < capacity` (B2f said `endOfBuffer + 1`) | Applied, B2i.2 | `discardUnusedTail()` assigns `endOfBuffer = prev` after setting `allocatePosition = old endOfBuffer + 1`; a closed segment's `buffer` is null. |
| 3 | Compressed-mode file length is not capped by `S`; bound is the plaintext cap plus LZ4 expansion | Applied, B2i.3 | Incompressible blocks expand; B2f / B2g / B3f would otherwise Refute on a source-predictable effect. |
| 4 | Direct-mode capacity is exactly `n MiB` (asserted); arm is n/a if direct I/O is unsupported | Applied, B2i.4 | DirectIOSegment asserts limit == capacity == segmentSize. |
| 5 | Payload sizes made exact; cluster file-size reading tolerant of a not-yet-mapped file; off-heap via maps/NMT | Applied, B2i.5 and 7 | Ambiguity in the filed text. |
| 6 | Paths in B2a/B3a refer to nonexistent trees; commit-ready sections of the file refer to `~/writeup-A` | Left for stage 3 | Cosmetic for this case. |
| 7 | A3.5 correctly says the target line `isStillAllocating()` gates retirement, not size; the size cap is `allocate()`. The case measures the claim the line does not itself enforce. | Left for stage 3 | Wording. |

**Agreement criteria** — not applicable unless run 2 is chosen (§5.2).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-23 (unit 10:09–10:11 MDT, cluster chain 10:11–10:23 MDT) | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/stage4-seg/treeB`, a separate tree from the sibling case's, made by `copy-source.sh` from repository commit `c765cea` (`git describe` = `cassandra-5.0.9`); `ant build-test` 1 min 10 s; `SegmentCapProbeTest.java` added and compiled (10 s). The cluster node ran from this tree's `build/`. Nothing built in the repository's `cassandra/cassandra-5.0.9/`. | |
| Case-file commit / harness commit | case file untracked at `c765cea` (sha256 `df551bcd…76fc`, §1); harness uncommitted (md5s in `run1/harness.md5`) | |
| Storage for node data | `/dev/sda3`, ext3, rotational, 63 GB; node data and commit log under `~/stage4-seg/nodeB`, unit commit log under `treeB/build/test/cassandra` | |
| Full logs (path, outside the repo) | `pc12:~/stage4-seg/runB/{unit,cluster}/` (full `system.log`, `debug.log.gz`, stress logs), `pc12:~/stage4-seg/logs/`; excerpts in `commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous/run1/` | |

**Environment deviations (none changes B1):** (1) the filed paths (`/users/jason92/cassandra-5.0.9`, `/tmp/cass-ut`, `/tmp/cass-node`) do not exist; tree and data are under `~/stage4-seg/` on local disk. (2) The unit yaml sets `commitlog_sync_period: 1h`, `memtable_heap_space: 600MiB`, `memtable_cleanup_threshold: 0.95`; the cluster yaml follows B3a/B3b (sync 10 s, 2 GiB heap, `memtable_heap_space` and `memtable_offheap_space` 1024 MiB). (3) Direct I/O worked on the ext3 volume (`accessMode=direct` in `seg.summary`, file lengths are multiples of 4096), so the direct arm is run, not n/a. (4) B3c's `-schema keyspace=ks1 replication(factor=1)` and `-col size=FIXED(1024) n=FIXED(1)` were used as filed; 64 threads. (5) The `OversizedMutations` MBean was not found on the node (`oversized.txt`), not needed by B1. (6) The off-heap reading by NMT is not separable (§4.2 part 6). (7) `ulimit -n` was raised to 100000 in the shell that starts the node.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1, unit | B2f (retired-segment positions; compressed and direct file/capacity predictions) | Three predictions contradicted the source before any run (B2i.2 to 4). | Amended before run 1; sha256 in §1 is after them. | 2026-10-23 | untracked file |
| 2 | 1, cluster | B3f soft predictions (peak file counts; control 8–10 files) | Not a step that failed to run: the readings fell below the soft file counts and the control did not bind (§4.1). No frozen row covers "count below the soft prediction" or "control did not bind". | None: frozen rows are not edited; reported in section D as feedback to stage 3. | 2026-10-23 | none |
| 3 | 1, cluster | B3d `OversizedMutations` | `MBean not found`. | None; the unit tier reads `oversizedMutations`. | 2026-10-23 | none |

## 4. Run 1

**Scope:** unit tier, 10 arms (n = 1, 4, 32 MiB × mmap, LZ4+standard, direct; a repeat of n = 4 mmap); cluster tier, 5 arms (n = 8, 32, 64 MiB mmap at total space 1024 MiB with stress `n = 2,000,000`; LZ4 at n = 32; control n = 32 at total space 256 MiB). **Command log:** `commitlog_segment_size-isStillAllocating-endOfBuffer--autonomous/run1/unit/session.log`, `run1/go.log`, `run1/cluster/<arm>/session.log`; `run1/analyze_unit.out`, `run1/analyze_cluster.out`; independent self-check `run1/selfcheck.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/<arm>/seg.csv`, `seg.summary`, `analyze_unit.out`). Every arm: 64 adds of `n/16` random bytes, 5 segments (4 retired, 1 active), JUnit 1 test with 0 failures, `FLUSHES 0`, `SEGMENT_DELETED_LINES 0`, `ERRORS 0`.

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `buffer.capacity() == n·2^20` for every segment, all three modes (direct included, exactly) | holds in 10 of 10 arms (50 segments) | `seg.csv` col `capacity` |
| Every add's end offset < capacity; the largest per arm | mmap 985,856 / 3,934,976 / 31,460,127 B for n = 1 / 4 / 32 (LZ4 and direct within 50 B of these); `violations=0` | `seg.summary` `SUMMARY`, `seg.csv` col `maxEnd` |
| Retired segments (4 per arm): `isStillAllocating()` false, `allocatePosition == capacity + 1`, `endOfBuffer < capacity` | holds in all 40 | `seg.csv` cols `stillAllocating`, `allocatePosition`, `endOfBuffer` |
| The active segment (1 per arm): `isStillAllocating()` true, `allocatePosition < endOfBuffer == capacity` | holds in all 10 | `seg.csv` |
| mmap `fileLength == onDiskSize() == n·2^20` | holds in the 4 mmap arms | `seg.csv` |
| LZ4 `fileLength` against `n·2^20 + ceil(n·2^20/255) + 32·blocks + 64` | within the bound; none above `n·2^20` (max 0.9436 × n, because a segment is retired with about 2 payloads' worth of tail unused) | `analyze_unit.out` |
| direct `fileLength` | multiple of 4096 and ≤ `n·2^20` in all 3 arms (for example 3,936,256 B at n = 4) | `seg.csv` |
| Max-accepted mutation (total = `max_mutation_size` = n/2) | accepted in all arms | `PROBE max-accepted` |
| Oversize (n/2 + 1) | `MutationExceededMaxSizeException`, `oversizedMutations` +1, `allocatePosition` unchanged | `PROBE oversize` |
| Scaling | capacity and the largest offset scale 1 : 4 : 32 | `analyze_unit.out` |
| Control assertion `capacity == (n+1) MiB` | false in all arms | `analyze_unit.out` |
| Repeat (`mmap-4` vs `mmap-4-rep`) | identical capacities, offsets, file lengths | `unit/mmap-4*/seg.csv` |

**Cluster tier** (`run1/analyze_cluster.out`; sampler 0.25 s):

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| n = 8, total 1024 | A | largest file; files created; peak live files; peak total (stat = JMX) | 8,388,608 B (= n); 265; 95; 760 MiB | `cluster/n8/` |
| n = 32, total 1024 | A | same | 33,554,432 B (= n); 66; 26; 832 MiB | `cluster/n32/` |
| n = 64, total 1024 | A | same | 67,108,864 B (= n); 33; 15; 960 MiB | `cluster/n64/` |
| three values | A | ratio of largest file | 1 : 4 : 8 | `analyze_cluster.out` |
| n = 32, LZ4 | B | largest file; peak total (stat / JMX) | 32,629,174 B (31.1 MiB, below n); 66 created; 502 / 529 MiB for about 2.1 GB written | `cluster/lz4-n32/` |
| n = 32, total 256 | control | peak live files; peak dir; flush reasons | 24 files (predicted 8–10); 768 MiB; 8 `COMMITLOG_DIRTY` + 1 `MEMTABLE_LIMIT`; largest file 32 MiB | `cluster/ctl-n32-t256/` |
| mmap arms | A | `/proc/<pid>/maps` | each mapping is one segment (152 MiB / 19 = 8; 352 / 11 = 32; 448 / 7 = 64 MiB) | `ds.csv` cols `maps_*` |
| LZ4 and mmap arms | A, B | NMT `Other` after the load | 1.39 GiB (mmap) and 1.52 GiB (LZ4) of malloc, not separable from the other direct-buffer users | `nmt-after-load.txt` |

Flushes in the uncontrolled arms: 8 `MEMTABLE_LIMIT` of `ks1.standard1` each, no `COMMITLOG_DIRTY` (`counts.txt`); stress `Total errors: 0` in all arms; segments created ≥ 33 in every arm.

### 4.2 Conclusion and logic

1. **Validity** — valid. The knob took effect: `commitlog_segment_size=<n>MiB` in each node's `system.log` and the unit `capacity` equals it [observed: `cluster/*/session.log` CONFIG lines; `unit/*/seg.csv`]. The limit was reached: at least 33 segments were created in every cluster arm (B3g's floor is 30) and 4 of 5 unit segments per arm were retired by a failed `allocate()` (`allocatePosition == capacity + 1`) [observed]. Held-fixed settings are in §2; no unit flush or deleted segment [observed: `reasons.txt`].
2. **Readings** — the cluster soft predictions did not hold (peak files below the filed counts; the control did not bind) and the NMT reading is not separable; all other readings are as predicted.
3. **Matched row** — unit B2g row 1 (*all offsets < n MiB and file lengths ≤ n MiB, or ≤ the aligned bound for direct, in every mode → claim holds in the unit tier*), in its amended form: capacity exactly n in all three modes, every end offset < capacity, retired and active `isStillAllocating()` as amended, mmap length exactly n, direct lengths ≤ n and block multiples, LZ4 lengths within the expansion bound [observed]. Cluster B3g row 1 (*all files ≤ configured size at all three values; file size tracks the knob → claim holds in the cluster tier*): 8 / 32 / 64 MiB, ratio 1 : 4 : 8 [observed]. B3g "directory total > n: expected" also matches (760 to 960 MiB).
4. **Excluded rows** — *any allocation with `position + size ≥ capacity` or a file longer than n (mmap, direct)*: none (`violations=0`, largest cluster file = n). *Compressed length above the amended bound*: none, and in the unit tier none above n at all. *Capacity does not change with n*: it scales 1 : 4 : 32. *Only one segment although the payload exceeds n*: 5 per unit arm, 33 to 265 per cluster arm. *File size identical across the knob*: no. *Fewer than about 30 rolls*: no (33 to 265). *Peak count ≫ 1024/n + 2* and *peak TotalCommitLogSize far over 1024 MiB*: no, the counts were below the soft prediction (95 / 26 / 15 against 129–130 / 33–34 / 17–18) and the totals were 760 to 960 MiB, because 8 memtable-limit flushes reclaimed segments before the total space was reached [observed: `counts.txt`]; this is the reverse of the overshoot row and no frozen row covers it. *Control*: the frozen prediction (peak about 8 to 10 files) was **not met**: 24 files and 768 MiB, 3 × its 256 MiB total space and close to the uncontrolled 26 files and 832 MiB; the writer at about 90 MB/s outran the reactive reclaim. The control therefore did not show a binding limit in this workload; it is reported as a miss, not tuned, and it does not enter the per-segment claim (the file is a positive estimate and requires no control).
5. **Observed vs. inferred** — **[inferred: `isStillAllocating()` itself gates retirement and does not enforce a size]** (A3.5): the readings show it false exactly for the segments closed by a failed `allocate()` and true for the open one, which agrees but does not by itself prove the line is not the cap; the size cap is shown by the offsets and file lengths. **[inferred: the cluster files are the segments the unit tier measured]**. **[inferred: no transient file larger than n between 0.25 s samples]**, resting on mmap files being created at n by `channel.map` (`MemoryMappedSegment.java:62`).
6. **Deviations and gaps** — §2 deviations 1 to 7 and §3. The B3f/B3d off-heap statement (about one segment size per active or prepared segment) is partly observed: each mmap mapping equals n and up to 19 mappings were live in the n = 8 arm (retired but not yet recycled segments stay mapped); the NMT reading for the compressed series could not be separated from other direct-buffer use, so the compressed-series off-heap claim is not tested. The LZ4 expansion that the amendment predicted was not exercised in this file's unit tier (payloads of n/16 leave a tail, max 0.9436 × n); it was seen in the sibling case's run.
7. **Core question** — Usage followed the constraint. In 50 unit segments and every cluster sample no segment held or reserved a byte at or beyond `commitlog_segment_size`: capacity was n exactly in mmap, LZ4 and direct modes; the largest end offset stayed below n; mmap files were exactly n; direct files were block multiples at most n; and the largest live file scaled 1 : 4 : 8 with the knob (parts 1 and 3). The constraint caps each segment (disk, and the per-segment buffer); it does not cap the directory (760 to 960 MiB at 1024 MiB total space, 768 MiB at 256), which the file states.

**Conclusion (one line):** unit B2g row 1 (amended) and cluster B3g row 1 — confirmed; the cluster file-count and control predictions are outside their frozen values, recorded.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.out` re-derives the unit and cluster numbers from the raw CSVs, `final-ls.txt` and `system.log` with awk / grep (no shared code with `analyze_*.py`), including the active-segment state.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: `commitlog_segment_size=<n>MiB` in each unit log and `segment_size=<n>MiB` in each node `system.log`; 10 unit arms with `Failures: 0, Errors: 0` (`unit/session.log`); stress errors 0; names seen 35 to 267 per arm. |
| 2. Readings | yes | awk: `cap!=S:0 maxEnd>=cap:0 retiredBad:0 activeBad:0 active:1 files>S:0` for all 10 unit arms; cluster maxfile, peak files, peak total and flush reasons equal the analyzer's for every arm. (`names seen` is 1 to 2 higher than the analyzer's created count because it includes the baseline files.) |
| 3. Matched row | yes | Rows quoted from the case file's B2g / B3g as amended; every cited number is in `seg.csv`, `ds.csv`, `final-ls.txt`. |
| 4. Excluded rows | yes | The misses (soft counts below prediction, control not binding) are stated and not folded into a row. |
| 5. Observed vs. inferred | yes | The `isStillAllocating` inference is flagged as agreeing, not proving. |
| 6. Deviations and gaps | yes | The NMT gap and the unexercised LZ4 expansion are stated. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 is per segment; readings are per segment; the directory non-claim is checked against the totals. |

### 5.2 Run 2?

**No** — decided 2026-10-23. Direct measurements at both tiers; independent re-derivation agrees; the repeat arm reproduced the unit numbers; the result neither refutes the case nor confirms a bypass. The misses are about soft predictions that the claim does not depend on.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped to one segment). **Outcome class:** **true positive** (positive, caps).

**Claim tested:** B1 — for every commit log segment the highest byte offset reserved by any mutation stays below `commitlog_segment_size` (so segment files, and the segment buffers where one exists, never exceed it), whatever the mutation sizes and rates; writes that do not fit move to a new segment. As amended 2026-10-23 for compressed modes (cap on the plaintext offset; file length within the LZ4 expansion bound).

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — B2g row 1 (as amended) | caps | run 1 + self-check | 2026-10-23 |
| Cluster | Confirmed — B3g row 1 (soft file-count and control predictions missed, recorded) | caps | run 1 + self-check | 2026-10-23 |

**Positive control** (a negative-estimate file only): not required (positive estimate). The file's own control (`commitlog_total_space` 256 MiB at n = 32) did not bind within its prediction (24 files against 8–10), so it does not demonstrate a moving limit in this file; the per-segment claim does not rest on it.

**Feedback filed:** the case file's section D updated (the case file is untracked; no commit). Sections amended: the audit's B2i only. `_INDEX.md`, `writeup-set-A.csv` and `predicted-negative.md` were not touched (the human closes them).

## 9. What stays on pc12 for this case

No `CassandraDaemon`, `ant`, sampler or stress process (checked 2026-10-23 after the last arm). Kept: `~/stage4-seg/treeB` (source copy, build, test class, last unit arm's commit logs under `build/test/cassandra`), `~/stage4-seg/harnessB`, `~/stage4-seg/runB` (unit and cluster logs) and `~/stage4-seg/logs`, plus the folders shared with the sibling case (`src`, `driver`). The node data directory `~/stage4-seg/nodeB` was wiped by the script.
