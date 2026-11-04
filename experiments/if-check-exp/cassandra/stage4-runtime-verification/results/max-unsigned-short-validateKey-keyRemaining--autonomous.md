# max-unsigned-short-validateKey-keyRemaining--autonomous — stage-4 results  <!-- file: results/max-unsigned-short-validateKey-keyRemaining--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-unsigned-short-validateKey-keyRemaining--autonomous`](../../stage3-ai-deep-read/cases/max-unsigned-short-validateKey-keyRemaining--autonomous.md)
>
> **Status:** verdict filed (2026-10-26) - run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base repository commit `93d6365`; the case file is **untracked** (no commit holds it). **sha256 of the whole file after the audit's amendments (A3 note, B2i, B3i, 2026-10-26): `e079c396feadc578584d4e55c55043dd6fda841e285f718d3b8a0c5867197e86`**, frozen 2026-10-26 23:17 UTC, before the harness existed and before any reading. The file as filed by stage 3 (before the audit) was `9f5472e136ce174d2af81ad6663969dcee897f421abc65da0ab8afbb18f4a146`. **sha256 of the frozen prediction and conclusion text** (B2f, B2g, B2i, B3f, B3g, B3i, copied to `harness/max-unsigned-short-validateKey-keyRemaining--autonomous/frozen-prediction.txt`): `b61ddc2ecd86b494db269aae7c8ab4b573cd45a0dcb3638bb478eeee3f4a6861`. Section D (feedback) is filled after the runs; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/max-unsigned-short-validateKey-keyRemaining--autonomous/` (written after the freeze, before run 1; not committed; md5s at each run start in `max-unsigned-short-validateKey-keyRemaining--autonomous/run1/harness.md5.*`) |
| **Tiers and values** | Unit (B2): L in {0, 1, 1000, 65534, 65535, 65536, 70000, 1,000,000} through `Validation.validateKey` (and `QueryProcessor.validateKey` as the shadowing method); `Int32Type` order check; 100,000 streamed 65535-byte keys; hold 1,000 / 5,000 keys at L = 65535 and L = 1; OOM leg at `-Xmx256m`; `HeapPool` 64 MiB control. Cluster (B3): one node, heap_buffers, K in {1000, 65535, 65536}, N in {10,000, 100,000}; pools 256 MiB (life 1) and 128 MiB (life 2); Byteman trace of which validator sees which key. |
| **Audit bottom line** | **Ready after amendments** (A3 note, B2i, B3i) - 2026-10-26 |

### 1.1 Design audit

Estimate: **negative** (the constant bounds one key, not aggregate usage). Audited against `cassandra/cassandra-5.0.9/` (clean, `base.version` 5.0.9). Citations re-read: `Validation.java:45-72`, `FBUtilities.java:158`, `QueryProcessor.java:249-263`, `ModificationStatement.java:292, 369-376, 559, 746-806`, `BatchStatement.java:287, 312, 502`, `SelectStatement.java:732`, `TriggerExecutor.java:209`, `ByteBufferUtil.java:92, 363-368`, `ByteArrayUtil.java:229`, `NativeClustering.java:50`, `ClusteringPrefix.java:278-287`, `SortedTableWriter.java:169-172`, `CacheService.java:500-506`, `MemtablePool.java:151-155`, `MemtableAllocator.java:169-196`, `HeapPool.java`, `Int32Serializer.java:43`, `conf/cassandra.yaml:794-883`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of one key (heap as a side effect); B1 names total memory and disk usage. |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | A1: constant, not settable; B2b/B3b vary key length across the boundary and N; reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d measures the driver's own list; gap named in B2i.7. B3d real resources (flush-line pool usage, RssAnon, disk) added by B3i.6. |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c: boundary keys, 65535 x 100,000 = 6.55 GB over a 256 MiB pool; unit stream of 6.55 x 10^9 key bytes. |
| A. Core question | positive control for a negative estimate | Partly -> Met | B2e.4 named a pool but no way to use it; made specific in B2i.6 (`HeapPool` 64 MiB, 1,024 allocations). B3h `memtable_heap_space` 256 vs 128 MiB stands, with numbers in B3i.5. |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | B2f's "1 MB per 1,000 one-byte keys" is wrong by 10x (about 0.08 MB): B2i.3. B3f "roughly linear", "e.g. >= 6 GB", "flush frequency" had no bounds: B3i.5. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows exist for confirmed, refuted, wrong boundary, control did not move, limit not reached. No row for a mixed result (unit confirms, cluster does not); the generic rule applies: "Not confirmed (no matching row)". Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | The disallow branch of the target line (`Validation.java:51`) cannot fire through CQL: `ClusteringPrefix.validate` and `QueryProcessor.validateKey` reject the same key first (A3 note). Direct evidence of the target branch is the unit tier's; the cluster tier's evidence is which validator saw which key (Byteman: which validator saw which key, and the stack of each rejection, B3i.4). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: 1-byte keys, K = 1000 baseline, pool size change, same node config. |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | Paths, table metadata, memtable class and allocation type, random keys, fresh table per arm, B2e.4's control, the OOM leg: B2i.1-6, B3i.1-3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | Precheck and run order (B3i.3), numbers (B3i.5), observables and sampling (B3i.6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | `copy-source.sh` + `ant jar`, bundled Python driver, `nodetool`, Byteman jar from the build; driver, node script, writer and analyser are step-2 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | K = 65535 x 100,000 = 6.55 GB of keys against a 256 MiB pool; about 13 GB of Data+Index on 126 GB tmpfs; unit hold 328 MB under `-Xmx512m`; OOM leg ceiling 4,091 keys under `-Xmx256m`. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (1 finding) | All cited lines hold. Finding: `Validation.java:51-56` is shadowed on every CQL path, first by `ClusteringPrefix.validate` (`PartitionKeySingleRestrictionSet.java:67`), then by `QueryProcessor.validateKey` (A3 note). `CacheService.java:504` is a key-cache read corruption check, not a write-path backstop. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3 note: the reject branch at `Validation.java:51` is shadowed twice (`ClusteringPrefix.validate`, `QueryProcessor.validateKey`) | Applied, A3 note, 2026-10-26 | The case file's A3 reads as if this method rejects first; the cluster tier cannot show it firing. |
| 2 | Attribution observable (Byteman trace) and its prediction (B3i.4) | Applied | Cluster rejection text is identical from both methods; only a trace tells which fired. |
| 3 | Specific positive control for the unit tier (B2i.6) | Applied | B2e.4 was unusable as written. |
| 4 | B2f wrong number; OOM leg and stream with numbers (B2i.3-5) | Applied | 1 MB per 1,000 one-byte keys is wrong by 10x. |
| 5 | Paths, tmpfs, port slot 5, yaml lines, keys, fresh table per arm, run order, numbers, observables (B3i.1-7) | Applied | `/local/...` absent; zero-padded keys compress; truncate snapshots. |
| 6 | Conclusions row for mixed results | Left for stage 3 | The no-matching-row rule covers it. |

**Agreement criteria** - not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 23:37 UTC, cluster 23:38 to 23:45 UTC) | not done |
| Node (CloudLab name and type) | `pc12` (`node1.jason92-320876...`, 40 cores, 251 GiB), shared with other stage-4 agents running their own nodes at the same time (port slot 5: 127.0.5.1, JMX 7150, Byteman 19150) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant jar` once per tree (1 min 16 s and 1 min 18 s), no `ant` while a node ran | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b9-vk/u` (unit) and `~/s4-b9-vk/c` (node) by `copy-source.sh`, repository commit `93d6365` (tag `cassandra-5.0.9`, local baseline) | |
| Case-file commit / harness commit | the case file is untracked (sha256 in section 1); harness uncommitted | |
| Storage for node data | tmpfs `/dev/shm/s4-b9-vk/node/{data,commitlog,hints,saved_caches,logs}` (removed at the end); disk bytes are tmpfs bytes | |
| Full logs (path, outside the repo) | on `pc12`: `~/s4-b9-vk-logs/run1/{unit,cluster}/` (`summary.txt`, `session.log`, `system.log.life{1,2}`, `stdout.life{1,2}.txt`, `vk-life{1,2}.trace`, `samples-*.csv`, `arms.jsonl`, `selfcheck.out`); shakedowns `shake1`, `shake2` (unit) and `shake-c1`..`shake-c7` (cluster), build logs `build-{u,c}.log`. Node settings: JDK 11, `MAX_HEAP_SIZE=2G` (G1), `ulimit -n 100000`, one-node ring, default `skiplist` memtable, `memtable_allocation_type: heap_buffers`, `memtable_cleanup_threshold: 0.99`, `commitlog_total_space: 512MiB`, `auto_snapshot: false`, `memtable_heap_space` 256 MiB (life 1) and 128 MiB (life 2), Byteman agent with three trace rules | |

## 3. Runbook defects

The audit fixed the defects it found before run 1 (A3 note, B2i, B3i); they are listed for stage 3. The instrument check found one case-file error and three harness faults; the self-check found one wrong check.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | instrument check (cluster shakedown `shake-c2`) | A3 note, B3i.4 | the first A3 note named only `QueryProcessor.validateKey` as the shadowing method; the Byteman trace showed 0 oversize entries there with the 5 + 20 rejected writes still rejected, so an earlier method rejects: `PartitionKeySingleRestrictionSet.toByteBuffers` calls `ClusteringPrefix.validate()` (`:67`), which throws the same message (`ClusteringPrefix.java:279`) | A3 note and B3i.4 corrected (third rule on the exception constructor, stack check); tables re-frozen (section 1) before any run-1 reading | 2026-10-26 | untracked file (sha256 in section 1) |
| 2 | instrument check | harness | (a) `HeapPool` needs a non-null cleaner (`MemtablePool.java:57`); (b) Byteman `trace` writes no newline (use `traceln`); (c) a `\n` in the Python rule text became a real newline in the rules file (`newline in string` parse error, rule silently not installed); all three found by shakedowns `shake1`, `shake-c1`, `shake-c5` | fixed in `KeyLenDriver.java` / `cluster-run.py`; `-Dorg.jboss.byteman.verbose=true` (env `VK_BM_EXTRA`) used once to find (c) | 2026-10-26 | n/a (harness) |
| 3 | self-check | selfcheck.py | two checks assumed the directory read by the harness holds only the flushed sstables; in the two N = 100,000 arms at K = 65535 a compaction (6 and 8 `Compacting` lines) was running, so the directory held in-progress outputs beside their inputs (excess 2.85 and 2.64 GB over the flushed Data.db sum); the checks were wrong, not the run | replaced by a check that the excess is non-negative and that compactions ran, plus post-hoc checks on the node log's flushed Data.db sums (ratio 10.000 and 10.008 for N = 100k over 10k); the frozen prediction is **not** edited (section 4.2 part 6) | 2026-10-26 | n/a (harness) |


## 4. Run 1

**Scope:** unit tier (bounds, Int32 order, 100,000-key stream, holds at L = 65535 and 1, OOM leg, `HeapPool` control) and cluster tier (precheck, K = 1000 and 65535 at N = 10,000 and 100,000, K = 65536 x 100, the 128 MiB pool, Byteman trace). **Command logs:** `max-unsigned-short-validateKey-keyRemaining--autonomous/run1/unit/summary.txt`, `.../run1/cluster/summary.txt` (full logs on the node). The harness was checked by two unit shakedowns and seven cluster shakedowns (`shake-c1`..`shake-c7`, the last a 10,000-write K = 65535 arm) before run 1; they showed the same kind of numbers, so run 1's numbers are not independent of what the author had seen; the predictions were frozen first (section 1).

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`: 6 JVMs, 33 checks, 0 MISMATCH, all EXPECTED lines yes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `Validation.validateKey` (the target) and `QueryProcessor.validateKey`, L = 0 | rejected, "Key may not be empty" (both) | `unit/bounds.out` |
| L = 1, 1000, 65534, 65535 | accepted (both) | `unit/bounds.out` |
| L = 65536, 70000, 1,000,000 | rejected, exactly "Key length of L is longer than maximum of 65535" (both) | `unit/bounds.out` |
| `null` key | rejected, "Key may not be empty" | `unit/bounds.out` |
| `Int32Type` key: L = 65536 / 65535 / 4 | rejected with the length message / rejected by the type ("Expected 4 or 0 byte int (65535)", no "Key length") / accepted | `unit/bounds.out` |
| 100,000 fresh distinct 65535-byte keys through `Validation.validateKey`, none held | 100,000 accepted, 0 rejected, 6,553,500,000 key bytes validated in 1.2 s, heap after GC 13.3 MB (before 13.3 MB) | `unit/stream.out` |
| hold 1,000 / 5,000 keys of 65535 B (`-Xmx512m`) | retained 65,594,352 B and 328,067,192 B; slope 65,618.2 B per key | `unit/hold65535.out` |
| hold 1,000 / 5,000 keys of 1 B | slope 89.6 B per key (0.09 MB per 1,000 keys); slope ratio 733 | `unit/hold1.out`, `unit/summary.txt` |
| hold accepted 65535-byte keys under `-Xmx256m` | `OutOfMemoryError` after 3,662 held keys, 0 validation rejections | `unit/oom.out` |
| positive control: `HeapPool` 64 MiB, `allocate(65535)` | 1,024 allocations returned, `used` = 67,107,840 = 1,024 x 65,535, the 1,025th still WAITING after 2 s; meanwhile 100,000 further keys accepted by `Validation.validateKey`, 0 rejected | `unit/control.out` |

**Cluster tier** (`run1/cluster/arms.jsonl`, `summary.txt`: 30 EXPECTED lines, 29 yes, 1 NO). "Data+Index" = bytes of `*-Data.db` plus `*-Index.db` read from the table directory after the explicit flush; N x K is the key bytes written; "flushed Data.db" is the sum of the node's own "Completed flushing" sizes (`self-check`). `MEMTABLE_LIMIT` = flushes the memtable pool started.

| Arm (pool) | Writes accepted / rejected | Data+Index per N x K | Flushed Data.db per N x K | `MEMTABLE_LIMIT` flushes, logged on-heap usage | Evidence (file) |
|---|---|---|---|---|---|
| precheck K = 65535 (5) / 65536 (5) | 5 / 0 and 0 / 5 with the exact message | n/a | n/a | none | `cluster/summary.txt` |
| K = 1000, N = 10,000 (256 MiB) | 10,000 / 0 | 2.12 | 1.12 | 0 | `cluster/arms.jsonl` |
| K = 1000, N = 100,000 | 100,000 / 0 | 2.12 | 1.12 | 0 | same |
| K = 65535, N = 10,000 | 10,000 / 0 | 2.01 | 1.006 | 2 (254.2, 253.9 MiB) | same, `flush-lines.life1.txt` |
| K = 65535, N = 100,000 | 100,000 / 0 | 2.87 (a compaction was running) | 1.002 | 24 (median 253.9, max 255.0 MiB) | same |
| K = 65536, 100 attempts | 0 / 100, one message (the exact text) | 0 B; table directory and memtable unchanged | n/a | 0 | same |
| K = 65535, N = 100,000, pool 128 MiB (life 2) | 100,000 / 0 | 2.80 (compaction running) | 1.002 | 49 (median 127.1, max 128.0 MiB) | same, `flush-lines.life2.txt` |

Other cluster readings: flush-count ratio 49 / 24 = 2.04 and median logged usage ratio 253.9 / 127.1 = 2.00 for pools in the ratio 2; the commit log reached 537 MB (its 512 MiB cap) in both 100,000-key arms, yet every flush that the pool started carried the reason `MEMTABLE_LIMIT` (`flush-lines.life*.txt`); the pre-flush `tablestats` "Memtable data size" is 289,209 B for 10,000 partitions of 65535-byte keys (it does not count partition keys); heap used peaked at 1.75 GB of the 2 GB heap (`samples-k65535_n100k.csv`); no `ERROR` line in either `system.log`.

**Which line rejected (Byteman trace, `cluster/trace-counts.life{1,2}.txt`, `x1.txt`):** 105 `InvalidRequestException("Key length of ...")` constructions in life 1 (5 + 100), all for length 65536, every stack with `ClusteringPrefix.validate(ClusteringPrefix.java:279)` called from `PartitionKeySingleRestrictionSet.toByteBuffers(:67)` via `ModificationStatement.buildPartitionKeyNames(:372)`; 0 entries of `QueryProcessor.validateKey` above 65535; 0 entries of `Validation.validateKey` above 65535; `Validation.validateKey` entered 110,005 times with length 65535 and 110,000 with length 1000 in life 1, and 100,000 times with 65535 in life 2; no such exception in life 2.

### 4.2 Conclusion and logic

1. **Validity.** The key length was driven across the boundary at both tiers (65534, 65535, 65536, 70000, 1,000,000 at unit; 65535 and 65536 at cluster) [observed: `unit/bounds.out`, `cluster/summary.txt`]. The memtable pool was driven to its limit: 24 `MEMTABLE_LIMIT` flushes at 254 MiB in the 256 MiB pool arm and 49 at 127 MiB in the 128 MiB pool arm [observed: `cluster/flush-lines.life{1,2}.txt`]. Fixed settings held: same yaml tail in every arm of a life, `MAX_HEAP_SIZE=2G`, fresh table per arm, `auto_snapshot: false` [observed: `cluster/summary.txt` (yaml tail)]. The control moved (part 3). Valid.
2. **Readings.** Three surprises. (a) At the cluster tier `Validation.validateKey` never saw an oversize key: the rejection came from `ClusteringPrefix.validate` first, as the A3 note (as corrected) says [observed: trace]. (b) Data+Index of the K = 65535, N = 100,000 arm is 2.87 x N x K, not about 2.0, because a compaction was running when the directory was read (6 `Compacting` lines in the arm, "Compaction interrupted" at the drop) [observed: `system.log.life1`]; the node's flushed Data.db sums are 1.002 x N x K in both 100,000 arms [observed: `selfcheck.out`]. (c) The commit log hit its 512 MiB cap too, but the flushes that the pool started are all `MEMTABLE_LIMIT` [observed: `flush-lines.life1.txt`].
3. **Matched row.** Unit B2g row 1, "Rejection only at L>65535; heap grows ~N*65535 and no rejection (or OOM first)": the boundary is as predicted, 65535 accepted and 65536 rejected with the predicted message, directly by `Validation.validateKey` [observed: `unit/bounds.out`]; held keys retain L + 83 B each (65,618.2 B at L = 65535, 89.6 B at L = 1) and the OOM arrives after 3,662 held keys with 0 rejections [observed: `unit/hold*.out`, `unit/oom.out`]; 6.55 x 10^9 key bytes (100,000 times the per-key cap) were validated without a rejection [observed: `unit/stream.out`]; and the positive control, a real memtable pool, binds exactly at its limit (1,024 allocations of 65535 B in 64 MiB) while the validator accepts without limit [observed: `unit/control.out`]. Cluster B3g row 1, "Only L>65535 rejected; disk and heap scale with N and L<=65535, and the control knob moves memtable size/flush rate": 100 of 100 attempts at K = 65536 were rejected with the exact message and nothing reached the table directory or memtable [observed: `cluster/arms.jsonl`]; every write at K = 1000 and 65535 was accepted; flushed Data.db bytes are 1.002 x N x K at K = 65535 and 10.000 x as large at N = 100,000 as at N = 10,000 [observed: `selfcheck.out`]; the pool plateau followed `memtable_heap_space`: 24 flushes at 253.9 MiB against 49 flushes at 127.1 MiB (ratios 2.04 and 2.00 for a pool ratio of 2), with the same key size and workload [observed: `flush-lines.life{1,2}.txt`].
4. **Excluded rows.** Unit "Heap plateaus at a value tied to 65535 while N grows -> Refuted": retained heap grew 65.6 KB per key up to the OOM [observed]. "Keys of 65536+ accepted": the opposite [observed]. "Usage flat while the positive control also stays flat/blocked": the control bound at 1,024 allocations while the 1-byte hold moved 89.6 B per key against 65,618 B [observed]. "Control never reaches its limit, or heap never grows": the control reached it, and heap grew to an OOM [observed]. Cluster "Total disk/heap saturates near a value derived from 65535 independent of N -> Refuted": flushed bytes were 10.000 x for 10 x N; the only plateau is the pool's, which moved with the setting [observed]. "65536-byte keys accepted -> trace wrong": 0 of 100 accepted [observed]. "Control knob does not change memtable behaviour, or the memtable never reaches its limit -> Not confirmed": the knob halved the logged plateau and doubled the flush count, and the limit was reached in both lives [observed].
5. **Observed vs. inferred.** [inferred: "usage is bounded by the aggregate memtable limits, not by `MAX_UNSIGNED_SHORT`".] The constant cannot be varied, so "does not cap" rests on usage being linear in key bytes up to and including the boundary key, the pool moving the plateau, and 6.55 x 10^9 key bytes passing the check. [inferred: the unit heap readings are for the harness's own list of buffers.] They show the cost of holding that many accepted keys; the node's own accounting is the cluster tier. [inferred: tmpfs bytes stand for disk bytes.] [inferred: the excess of the 100,000-key directory readings over the flushed sums is an in-progress compaction]: supported by the compaction log lines and the exact flushed sums, not measured directly.
6. **Deviations and gaps.** (a) The shakedowns showed similar numbers before run 1. (b) **One frozen sub-prediction was not met:** B3i.5 said the N = 100,000 arm's Data+Index is 8 to 12 times the N = 10,000 arm's at K = 65535; the reading is 14.28 (2.87 against 2.01 times N x K) because of the running compaction (part 2b). The prediction is not edited; the same ratio from the flushed Data.db sums is 10.000, and at K = 1000 the directory ratio is 10.01 [observed: `selfcheck.out`, `summary.txt`]. The missed number concerns how disk bytes were read, not whether they follow N x K, so it does not match a Refuted row; it is recorded, not hidden. (c) The explicit-flush time reading of the directory should have been taken after compactions settled (`nodetool compactionstats`); not done. (d) The commit-log cap also bound in the 100,000-key arms (537 MB), so two known caps bound the node at once there; the flush reasons show the pool as the trigger, and the 128 MiB arm moved the plateau while the commit-log cap was unchanged. (e) The "which line rejects" prediction (B3i.4) was written after the first cluster shakedown showed a part of it wrong (section 3 row 1); it is a mechanism prediction, derived from source, and does not change B1, B2g or B3g. (f) `nodetool tablestats` "Memtable data size" excludes partition-key bytes; the flush-line usage includes them.
7. **Core question.** Usage follows the key bytes and the pool settings, not the constant: held heap, memtable pool usage and flushed bytes all grow linearly in N x K up to the boundary key (part 3), the key-size gate fires exactly at 65536 with the predicted text and writes nothing (part 3), and what a node holds is bounded only when the memtable pool reaches its configured limit, which moved with the pool setting while the key size stayed at the boundary (part 3, with the known-binding controls). The constant limits one key, not the aggregate: 6.55 x 10^9 key bytes passed `Validation.validateKey` in one JVM, and 6.55 GB went through a node. Through CQL the target line is never the one that rejects (parts 2a, 3).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 - confirmed (the claim: usage does not follow the 65535-byte key cap), with one missed numeric sub-prediction recorded in part 6b.

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/max-unsigned-short-validateKey-keyRemaining--autonomous/selfcheck.py` re-parses the raw files (`unit/*.out`; `cluster/session.log` writer outputs; `system.log.life{1,2}` flush lines and Data.db sizes; `vk-life{1,2}.trace`; `samples-*.csv`) with its own code; output `run1/selfcheck.out`: 78 parts hold, 0 do not hold (after replacing two wrong checks, section 3 row 3; one prediction check is reported as a deliberate "not met" check). Index.db bytes exist only in `arms.jsonl` (the files were dropped after each arm); that input is used as recorded. Data.db totals from the node's own "Completed flushing" lines agree with `arms.jsonl` within 1 percent where no compaction ran (K = 1000, K = 65535 N = 10,000) and are lower where one did.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: precheck 5/5 and 5/5; 24 and 49 `MEMTABLE_LIMIT` flushes near the pool size; no `ERROR`; no daemon of the run left and `/dev/shm/s4-b9-vk` gone. |
| 2. Readings | yes | The compaction explanation is a `selfcheck.out` pass (6 and 8 compactions, excess 2.85 and 2.64 GB) and is marked inferred. |
| 3. Matched row | yes | Bounds, stream, slope, OOM and control numbers recomputed from `unit/*.out`; flushed sums, flush counts and usage ratios from the node logs; trace counts from the trace files. |
| 4. Excluded rows | yes | Same files. |
| 5. Observed vs. inferred | yes | The inferences are named in 4.2 part 5; the raw files hold nothing stronger (the constant cannot be varied). |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6, including the missed 8..12 sub-prediction (`selfcheck.out` has it as an INFO line and as a check that it is not met). |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Per-key gate (unit, direct call) and aggregate growth plus pool plateau with controls (cluster) follow B1 and B3h; the trace shows which method gated the cluster writes. |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on exact boundary behaviour, a control that binds at an exact count, and numbers that the node's own logs reproduce. The one inference (that the plateau is the pool and not the constant) is what the control, which moved by the predicted factor, settles. A run 2 would repeat a 7 minute run and add nothing the logs do not already hold.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap): the constant bounds one key; what a node holds follows the memtable pool, the commit log and the number of keys.

**Claim tested (B1):** memory/disk usage of a node does not follow `MAX_UNSIGNED_SHORT`: it only rejects individual partition keys longer than 65535 bytes, and total usage with keys at or below the limit grows with the number of keys written without being bounded by it. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1; the control as in the pool-size comparison) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** at the unit tier a real memtable pool (`HeapPool` 64 MiB) bound at exactly 1,024 allocations of 65535 B while `Validation.validateKey` accepted 100,000 more keys; the 1-byte hold moved 89.6 B per key against 65,618 B (ratio 733). At the cluster tier the known-binding cap (`memtable_heap_space` 256 MiB to 128 MiB) moved the logged plateau from 253.9 to 127.1 MiB and the flush count from 24 to 49, with the same key size and workload.

**Side findings (do not change the verdict):** (1) The reject branch of `Validation.validateKey` (`Validation.java:51-56`) is never taken through CQL: `ClusteringPrefix.validate` (`PartitionKeySingleRestrictionSet.java:67`, `ClusteringPrefix.java:279`) rejects the key first, and `QueryProcessor.validateKey` (`QueryProcessor.java:259`) saw 0 oversize keys in the cluster run; redundant checks, a documentation candidate. The closely related closed case `max-unsigned-short-validate-key-remaining--autonomous` (`QueryProcessor.java:259`) likely has the same attribution for its cluster rejections; its verdict (the aggregate claim) is unaffected. (2) `tablestats` "Memtable data size" omits partition-key bytes (289,209 B for 10,000 partitions of 65535-byte keys). (3) A directory read right after `nodetool flush` can include in-progress compaction output (2.85 GB extra over 6.57 GB flushed).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (untracked file, sha256 below); the audit amendments (A3 note, B2i, B3i) are listed in section 1. Sha256 of the case file with D filled: `2074dde6d8e42da143e16873e0d7778cb7325c5a64e7d3d003a78fcebf76d28a`.
