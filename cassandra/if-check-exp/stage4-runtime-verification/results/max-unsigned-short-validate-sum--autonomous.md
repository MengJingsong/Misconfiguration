# max-unsigned-short-validate-sum--autonomous — stage-4 results  <!-- file: results/max-unsigned-short-validate-sum--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-unsigned-short-validate-sum--autonomous`](../../stage3-ai-deep-read/cases/max-unsigned-short-validate-sum--autonomous.md)
>
> **Status:** verdict filed (2026-10-26; run 1 + self-check; no run 2)
>
> **Outcome class:** true negative (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
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
| **Case-file version** | Base repository commit `93d6365`; the case file is **untracked** (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i, B3i, 2026-10-26): `e847e2d2d3c493f383ea1ba41abfeb0aa39485bd1ce88a9699147d8dbe347324`**, frozen 2026-10-26 before the harness existed and before any reading. **sha256 of the frozen prediction and conclusion tables** (B2f, B2g, B2i, B3f, B3g, B3i, copied to `harness/max-unsigned-short-validate-sum--autonomous/frozen-prediction.txt`): `e4aef73e79db59f6bcb813ed81e9c03615cbcd2c93f0fe0a0d4fdbe1204d872d`. Section D is filled after the runs. |
| **Harness** | `harness/max-unsigned-short-validate-sum--autonomous/` (written after the freeze; not committed): `ClusterKeyDriver.java`, `unit-run.sh`, `cluster-run.py`, `writer.py`, `selfcheck.py`, `frozen-prediction.txt`; md5s in `max-unsigned-short-validate-sum--autonomous/run1/harness.md5` (`cluster-run.py` changed once, see section 3). |
| **Tiers and values** | Unit (B2): two-or-more-component boundary grid with exact messages (sum branch `:284`), held series of 32768+32767-byte clusterings (3 JVMs), 8+8-byte contrast, capped control, 100,000 streamed at-limit clusterings. Cluster (B2): precheck, S=16/1024/32768/65535/65536 at 256 MiB pools, S=65535 at 64 MiB pools (control), S=65535 with heap_buffers, probe. |
| **Audit bottom line** | **Ready after amendments** (B2i, B3i) - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of the clustering sum; B1 names memtable and disk bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: hard-coded constant, not settable; B2b/B3b vary component sizes, count and key size across the boundary. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d measures the heap of the driver's own list (the check retains nothing; gap named, B2i.7). B3d lists tablestats/`nodetool info`/`jcmd`, but clustering bytes are off-heap malloc: B3i.7 adds RssAnon, sstable bytes, flush log lines. |
| A. Core question | usage driven to the limit and past it | Partly -> Met | B2c's N = 1e5 at S = 65535 (6.5 GB) cannot be held in 1 GiB: B2i.3 (held series to 655 MB, stream of 6.55 GB). B3c's 4 GiB per arm is more than needed: B3i.3 (655 MB to 1 GB against 256 MiB pools). |
| A. Core question | positive control for a negative estimate | Partly -> Met | B2e step 2 contrast (S = 16) is a contrast, not a known cap: B2i.6 adds a capped list. B3g names the pool control; B3i.5 pins it to the same workload at 64 MiB. |
| B. Logic | each step says what it establishes | Met | B2e, B3e with B2i/B3i. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | "about 10 +-5 %" and "1.0-1.2 x" lacked a base and a bound; B2f's "(>=32768, N=2)" is exact only from S = 32768. B2i.2, B2i.4, B3i.6. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows exist for confirmed, refuted, trace wrong, control failed, limit never reached. No row for unit-confirms/cluster-mixed; the generic "Not confirmed (no matching row)" applies. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | B3g row 1 includes the 65536 rejection; B3i.4 makes the disallow evidence the exact message through the sum branch (two components), so the target line, not `:278`, is the trigger. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus B2i.6, B3i.5: small keys, capped list, pool change. The per-value branch is excluded by design (every component at most 65535). |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met | `/local/scratch`, `ant testsome`, "1000 partitions", garbled "R = 262144 for S=16 KiB scaled...", missing yaml keys: B2i.1, B3i.1-3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B2i.2, B3i.2-4, B3i.7. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Tree via copy-source.sh + `ant jar` on pc12; Python driver bundled; the unit driver and node script are step-1 work, adapted from a closed sibling's harness. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met | As A (limit). With B3i.3: at most 1 GB per arm on tmpfs (126 GB free), 1e6 small inserts in minutes. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (2 notes) | `ClusteringPrefix.java:272-288` (target `:284`), `:317-326` `dataSize()`, `NativeClustering.java:50,59`, `ModificationStatement.java:815`, `FBUtilities.java:158` hold. Notes: the first-branch message reports `dataSize()` (the sum), not the offending size; `PartitionKeySingleRestrictionSet.java:67` also calls `validate()`; A3 names no batch bypass, correctly (batches use `addUpdates`); the CAS path (`:573`) and slice deletes skip the call. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Tree path, tmpfs, port slot 7, extra yaml, 2 GiB heap, two-component keys, fresh table per arm (B2i.1, B3i.1-2) | Applied, 2026-10-26 | `/local/...` absent; the sum branch needs components each at most 65535 |
| 2 | Exact boundary grid and message rule (B2i.2) | Applied | message reports the sum of all components |
| 3 | Held-series and stream sizes that fit the JVM, numbers for B2f/B3f (B2i.3-5, B3i.6) | Applied | N = 1e5 x 65535 B cannot be held |
| 4 | Capped and small-key controls; pool control pinned (B2i.6, B3i.5) | Applied | positive control for a negative case |
| 5 | Arms and arithmetic for B3c (B3i.3), precheck (B3i.4), observables (B3i.7) | Applied | B3c's 4 GiB per arm unneeded, counters differ from the real resource |
| 6 | Probe of the CAS path and slice delete (B3i.8) | Applied as informational | A3 says other paths skip the check |
| 7 | Add a conclusions row for unit-confirms / cluster-mixed | Left for stage 3 | does not depend on a reading, but is a generic case |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 17:55 MDT; cluster 18:05-18:30 MDT) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876`, control 198.22.255.22), 40 cores, 251 GiB; other cases ran on the same node in parallel (own dirs, ports) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-187-generic | |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 (`ant jar`, 1 min 10 s) | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b9-cs` by `copy-source.sh` from repository commit `93d6365` (`git describe`: cassandra-5.0.9, local baseline) | |
| Case-file commit / harness commit | case file untracked (sha256 in section 1) / harness untracked | |
| Storage for node data | tmpfs `/dev/shm/s4-b9-cs/node` (126 GB free; stands for disk bytes); unit driver: heap only | |
| Full logs (path, outside the repo) | `pc12:~/s4-b9-cs-logs/run1/{unit,cluster}/` (attempt 1 of the cluster tier: `run1/cluster-attempt1/`, `cluster-run1-attempt1.out`) | |

Cluster set-up (B3i.1): offheap_objects (life 1, 2), heap_buffers (life 3), `MAX_HEAP_SIZE=2G`, pools 256 MiB (life 1, 3) and 64 MiB (life 2), `memtable_cleanup_threshold: 0.99`, `commitlog_total_space: 1GiB`, `auto_snapshot: false`, port slot 7 (127.0.7.1, JMX 7170), protocol 4, CL ONE, RF 1.

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | Cluster tier, attempt 1 | B3e.3 / B3i.7 (flush log lines are the real-resource observable) | logback rolled `system.log` at 00:00 UTC (18:00 MDT) during the S=1024 arm; its three `MEMTABLE_LIMIT` flush lines went into the zipped log, which the harness did not read, so the arm read "0 MEMTABLE_LIMIT flushes" (a false NO) although the table directory had grown past the pool; the zip was deleted with the run directory. Instrument defect, found from the arm's own `Deleting sstable`/`nb-4` lines, independent of what the prediction says. | `cluster-run.py` now fails the tier if a rolled zip appears or the log shrinks, and refuses to start within 20 minutes of 00:00 UTC. The whole tier was run again from its beginning (the rerun is "run 1" below). Attempt 1's other arms had the same values (data+index within 0.1 percent; the same two numeric misses, section 4.2 part 6). | 2026-10-26 | none needed: B3g unchanged, no case-file text affected |

## 4. Run 1

**Scope:** unit tier in full (grid, stream, three held series, contrast, capped control); cluster tier in full (precheck, five arms at 256 MiB, control at 64 MiB, heap_buffers arm, probe). **Command log:** `max-unsigned-short-validate-sum--autonomous/run1/` (`unit-summary.txt`, `unit-readings.txt`, `cluster-summary.txt`, `arms.jsonl`, `samples-thinned.csv`, `memtable-limit-lines.txt`, `probe-excerpt.txt`, `selfcheck.txt`, `attempt1-note.txt`, `harness.md5`); full logs on `pc12:~/s4-b9-cs-logs/run1/`.

### 4.1 Readings

**Unit tier** (`unit-summary.txt`, `unit-readings.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Grid: 39 checks (S in {1, 1000, 32767, 32768, 65534, 65535, 65536, 70000} x N in 1-3, N = 65/66 of 1000, mixed cells, empty/static, ArrayClustering) | 0 mismatches against the rule of B2i.2; 21 cells rejected, 16 accepted. (32768, 32767) accepted; (32768, 32768) rejected `Key length of 65536 ...` (sum branch); S=65535, N=2 rejected with n = 131070; (32767, 32768, 1) rejected with 65536; ArrayClustering the same | unit-readings.txt, selfcheck.txt |
| Stream: 100,000 distinct (32768 + 32767)-byte clusterings validated, none held | 100,000 accepted, 0 rejected; 6,553,500,000 bytes validated; heap after GC 13,264,272 B (before: 13,255,136 B) | unit-readings.txt |
| Held series, M = 1,000 to 10,000 in steps of 1,000, (32768 + 32767) bytes, three JVMs | slopes 65,723.8 / 65,726.1 / 65,713.9 B per key (spread 0.02 percent); retained 197,231,448 B at M=3,000 and 657,256,192 B at M=10,000; every step within 10 percent of the mean; `validate()` threw 0 times | unit-readings.txt, selfcheck.txt |
| Contrast series (8 + 8 bytes), M = 10,000 to 100,000 | slope 196.6 B per key; ratio big over small 334 | unit-summary.txt |
| Capped control (newest 2,000 kept) | heap 144,786,352 B at M=3,000 and 144,766,744 B at M=10,000 (delta -19,608 B); the uncapped series grows 460,024,744 B over the same points | unit-readings.txt |

**Cluster tier** (`arms.jsonl`, `cluster-summary.txt`, `memtable-limit-lines.txt`, `samples-thinned.csv`)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| precheck (two components) | A | client result | (32768, 32767) x3 accepted; (32768, 32768) x3 rejected `Key length of 65536 is longer than maximum of 65535`; (65535, 65535) x3 rejected with 131070; (70000, 10) x3 rejected with 70010 | cluster-summary.txt |
| S=16, R=200,000 (3.2 MB), pools 256 MiB | control | flush log, sstable bytes | 0 `MEMTABLE_LIMIT` flushes; Data+Index 4.58 MB (no index blocks: 2,000 rows per partition) | arms.jsonl |
| S=1,024, R=1,000,000 (1.02 GB) | A | same | 3 `MEMTABLE_LIMIT` flushes at 253.5 MiB off-heap, 1 forced; flush logs sum to 994 MiB of Data.db; the harness figure Data+Index 1.30 GB includes an in-flight compaction output (self-check part 2) | memtable-limit-lines.txt, selfcheck.txt |
| S=32,768, R=20,000 (655 MB) | A | same | 2 `MEMTABLE_LIMIT` flushes at 253.5 MiB; Data+Index 1.321 GB (2.02 x R*S) | arms.jsonl |
| S=65,535, R=10,000 (655 MB) | A | same | all 10,000 accepted; 2 `MEMTABLE_LIMIT` flushes at 253.6 to 253.8 MiB off-heap; Data.db 658,517,069 B (1.005 x R*S), Index.db 1,310,959,504 B; Data+Index 1.9695 GB = 3.005 x R*S; RssAnon 3,030 MiB before, 3,152 MiB peak | arms.jsonl, samples-thinned.csv |
| S=65,536, R=10,000 | A | client result, table directory | 10,000 of 10,000 rejected with the exact message; 0 B in the table directory; memtable data 0 | arms.jsonl, cluster-summary.txt |
| S=65,535, R=10,000, pools 64 MiB (life 2) | control | flush log | 9 `MEMTABLE_LIMIT` flushes at 63.8 MiB off-heap; Data+Index 1.9695 GB; RssAnon 2,649 MiB before, 2,741 MiB peak | memtable-limit-lines.txt, arms.jsonl |
| S=65,535, R=10,000, heap_buffers, pools 256 MiB (life 3, informational) | A' | flush log | 2 `MEMTABLE_LIMIT` flushes at 253.9 MiB on-heap; Data+Index 1.9695 GB | arms.jsonl |
| probe (informational, outside B3g) | | client result, log | (a) plain insert with (32768, 32768): rejected, exact text. (b) `IF NOT EXISTS` with the same key: not rejected by `:284`; client WriteTimeout; the node logged `AssertionError: Data size 65536 >= 65536` at `NativeClustering.<init>(NativeClustering.java:50)` on a MutationStage thread. (c) `DELETE ... c2 > <70000 bytes>`: accepted; the later flush logged `AssertionError: Attempted serializing to buffer exceeded maximum of 65535 bytes: 70000` at `ByteBufferUtil.writeWithShortLength` from `StatsMetadata` serialization on MemtablePostFlush. The node stayed up | probe-excerpt.txt |

### 4.2 Conclusion and logic

1. **Validity.** The traced branch fired: the precheck's (32768, 32768) key, whose components are each below 65,536, was rejected with n = 65,536 [observed: cluster-summary.txt, selfcheck.txt], which only the sum branch `:284` can produce. The limit was passed by orders of magnitude: 6.55 x 10^9 bytes validated in the stream, 655 MB to 1.02 GB inserted against a 65,535-byte per-key limit and 256 MiB pools [observed: unit-readings.txt, arms.jsonl]. The "hold fixed" settings (pools, allocation type, heap) are in the node's yaml tail and logs [observed: cluster-summary.txt `yaml tail`, system.log.life*]. The harness changed once (section 3) and the tier was run again.
2. **Readings.** The S=16 arm shows a Data+Index of 4.58 MB because its partitions are small (no index blocks). The s1024 harness total is inflated by a compaction tmp output; the log's own flush lines give 994 MiB Data.db (selfcheck.txt). Life 2's two `AssertionError` lines are the probe's (b) and (c), after all arms [observed: probe-excerpt.txt]. The `RssAnon` rise during an arm is 92 to 325 MiB (about 120 MiB for the S=65,535 arms), below the 655 MB to 1.02 GB written [observed: arms.jsonl].
3. **Matched row.** Unit B2g row 2: "Per-key throw only at the predicted S/N cells, heap grows linearly with M with no throw -> Claim confirmed: the limit bounds one key, not the aggregate": throws only at the predicted cells (grid, 0 mismatches), heap linear in M (slope 65,720 B per key = 65,535 + about 190 B overhead; 460 MB over M = 3,000 to 10,000) and `validate()` never threw in the series [observed: unit-readings.txt]. Cluster B3g row 1: "Boundary behaviour as predicted, and usage keeps growing with R beyond 65535 bytes -> Claim confirmed": the 65,536 key is rejected with the exact text and 65,535 accepted, and bytes on disk (1.97 GB for 655 MB of keys) and flushed memtables grow with R x S far beyond 65,535 B with no error from this check [observed: arms.jsonl, cluster-summary.txt]. The "memtable usage flat at the memtable cap" row (positive control bound) also holds: first `MEMTABLE_LIMIT` flush at 253.6 MiB off-heap with 256 MiB pools and at 63.8 MiB with 64 MiB pools (ratio 3.97) while the disk total stayed 1.9695 GB [observed: memtable-limit-lines.txt, arms.jsonl].
4. **Excluded rows.** Refuted ("heap flat while M grows", "usage plateaus near 65535 bytes"): heap grew 460 MB over 7,000 keys and disk 1.97 GB [observed]. "Control failed / flat in the control": the S=16 slope is 197 B against 65,720 B, and the capped series is flat (-19,608 B) [observed: unit-readings.txt]. "validate() never throws" and "throws at S < 65535 with N=1": the grid has rejections exactly at the predicted cells [observed]. "S=65536 accepted": 10,000 of 10,000 rejected [observed]. "Control does not flush at the small cap, or load never exceeds the limit": 9 flushes at 64 MiB; the key bytes written exceeded the pool by 2.4 to 9.8 times [observed].
5. **Observed vs. inferred.** Inferred: that tmpfs bytes stand for disk bytes [inferred: same file sizes; the node writes the same sstables]; that the plateau at the pool is the memtable cap and not an effect of the constant [inferred: the plateau moves with `memtable_*_space` (253.6 to 63.8 MiB) while the constant is unchanged]; that the heap numbers for the held list say nothing about the memtable accounting (gap named, B2i.7) [inferred]; that a "caps" effect would show as a plateau of usage near 65,535 bytes per node, not per key [inferred from the claim in B1].
6. **Deviations and gaps.** Two numeric sub-predictions of B3i.6 did not hold, and they are not part of any B3g row: (i) Data+Index for S=65,535 is 3.005 x R*S against the band 1.0 to 3.0 (Index.db holds the key at the start and end of each index block, 2.0 x R*S here); (ii) the order "Data+Index of S=1,024 (R=1e6) > S=65,535 (R=1e4)" was wrong, since 1,024-byte keys put one index entry per many rows (39.7 MB of Index.db), so the S=65,535 arm (1.97 GB) exceeds S=1,024 (1.04 GB of flushed Data plus 39.7 MB). Both are errors of the audit's arithmetic, found by the run, not a change to the claim; the per-row ratio (8,602) held. The same two misses appeared in attempt 1. No `nodetool tablestats` figure is used as evidence (it omits off-heap key bytes). One node, one table per arm, one run. A second flush reason (`COMMITLOG_DIRTY`) never occurred for the arms (commit log peaked at 352 MiB of 1 GiB).
7. **Core question.** Usage did not follow the constraint. The constant limits one key to 65,535 bytes (the sum branch rejects 65,536 at both tiers), but with that bound respected, held heap grew linearly with the number of keys (460 MB over 7,000 keys), and a node accepted 10,000 keys of 65,535 bytes and wrote 1.97 GB, 30,000 times the per-key limit. What bounded memtable memory was `memtable_heap_space` and `memtable_offheap_space` (a different constraint: flush at 253.6 MiB and 63.8 MiB), not this one. So the constant does not cap memory or disk usage: the logic steps of B1 (limits one key; row count unbounded; pool is the cap) are each supported by parts 3 and 4.

**Conclusion (one line):** unit B2g row 2 and cluster B3g row 1 - Confirmed (the constraint does not cap usage).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Done with `harness/max-unsigned-short-validate-sum--autonomous/selfcheck.py`, which re-parses the raw `.out` files, `system.log.life*`, `session.log` and `samples-*.csv` itself (output in `run1/selfcheck.txt`), not the harness summaries.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `grid.out`: (32768, 32768) is rejected with 65536 and (32768, 32767) accepted; `session.log` has the exact messages for 65536 (8 repeats), 131070 and 70010, so the sum branch fired. `system.log.life1` has no ERROR line during the arms. |
| 2. Readings | yes, with one correction | The harness's Data+Index for s1024 (1.299 GB) counts the temporary output of a running compaction (attempt 1's log shows a compaction interrupted by the table drop); the independent sum of "Completed flushing" lines is 994 MiB. For s32768, s65535, p64 and hb the flush sums (625 MiB) match the harness Data.db (628 MiB) within 0.5 percent. The correction does not change a row. |
| 3. Matched row | yes | Unit and cluster rows re-matched from the raw numbers: slope 65,714 to 65,726 B; the 10 percent steady-step checks printed `ok`; rejections 10,000 of 10,000 at S=65,536. |
| 4. Excluded rows | yes | Capped list delta -19,608 B and S=16 slope 196.6 B re-read; flush lines: 253.5 to 253.8 MiB at 256 MiB pools, 63.845 MiB at 64 MiB pools (9 lines). |
| 5. Observed vs. inferred | yes | The inferred items are the same as listed; none contradicts a raw file. |
| 6. Deviations and gaps | yes | The two missed numeric bands are shown as misses by the harness (`NO` lines) and by the re-parse (Index.db 1.311 GB = 2.0 x R*S). |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's steps map to: per-key limit (grid, precheck), row count unbounded (series, arms), pool is the only cap (flush lines at two pool sizes). |

### 5.2 Run 2?

**No** (decided 2026-10-26). The conclusion rests on direct readings (exact rejection messages, per-arm flush lines, linear heap, a capped control) and both tiers agree; the only inferred step (tmpfs for disk) does not bear on a "does not cap" verdict, and the one run-1 defect was repaired by rerunning the tier. A run 2 would not change the result.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its
date and reason.

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested:** "The constant caps only the size of one clustering key (<= 65535 B total); it does NOT cap memory or disk used by a node: memtable and on-disk usage grow linearly with the number of rows of maximal-size clustering keys, with no ceiling imposed by the constant." "Confirmed" below always means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 2: Claim confirmed (limit bounds one key, not the aggregate) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | B3g row 1: Claim confirmed (constant bounds one key, not usage); positive control bound | does not cap | run 1 (rerun after one instrument fix) + self-check | 2026-10-26 |

**Positive control:** the same workload (S=65,535, R=10,000) with both memtable pools lowered from 256 MiB to 64 MiB moved the usage ceiling: the first `MEMTABLE_LIMIT` flush came at 253.6 MiB off-heap against 63.8 MiB (ratio 3.97, 2 flushes against 9), while the bytes on disk stayed at 1.9695 GB. In the unit tier the capped list (newest 2,000 kept) stayed flat while the uncapped list grew 460 MB, and the S=16 contrast moved the slope 334-fold.

**Feedback filed:** the case file's section D updated (case file untracked, no commit). Estimate not changed. No section of the case file amended beyond the audit's B2i and B3i.

**Side findings (outside the verdict; candidates for JIRA check, upstream or Target 3):** (1) a conditional write (`INSERT ... IF NOT EXISTS`) with a clustering whose components sum to 65,536 skips `ClusteringPrefix.validate()` and fails on the `NativeClustering.java:50` assert on a MutationStage thread (client WriteTimeout; assertion-enabled builds); (2) a `DELETE ... WHERE ... c2 > <70000-byte value>` is accepted, and flushing that memtable fails with `AssertionError ... writeWithShortLength` from `StatsMetadata` serialization on MemtablePostFlush; (3) the message of the per-value branch (`:278-281`) reports `dataSize()`, the sum of all components, not the offending size; (4) `PartitionKeySingleRestrictionSet.java:67` calls the same `validate()`, so it is not clustering-only.

**Leftovers on the node (`pc12`):** `~/s4-b9-cs` (source copy with `build/`, 471 MB) and `~/s4-b9-cs-logs/` (1.4 MB, including `run1/cluster-attempt1`); `/dev/shm/s4-b9-cs` removed; no process of this case running (the node's PID was checked after each life and at the end).
