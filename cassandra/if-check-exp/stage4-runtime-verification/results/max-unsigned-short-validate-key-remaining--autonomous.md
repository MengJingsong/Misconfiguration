# max-unsigned-short-validate-key-remaining--autonomous — stage-4 results  <!-- file: results/max-unsigned-short-validate-key-remaining--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-unsigned-short-validate-key-remaining--autonomous`](../../stage3-ai-deep-read/cases/max-unsigned-short-validate-key-remaining--autonomous.md)
>
> **Status:** verdict filed (2026-10-26) - run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
>
> **Agent:** autonomous. For an autonomous
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
| **Case-file version** | Base repository commit `93d6365`; the case file is **untracked** (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i, B3i, 2026-10-26): `3796ef2940889bc6ffd554174535bd15e9b61106f0f601e03fe25afbb5542452`**, first frozen 2026-10-26 19:41 UTC (`e821ab87...`, table hash `c138a223...`), before the harness existed; **re-frozen 2026-10-26 19:55 UTC** after one correction to B2i.2 found by the instrument check (the first unit shakedown, `shake1`, showed that `UNSET_BYTE_BUFFER` is an empty buffer: a source fact, `ByteBufferUtil.java:92`; the item is not in B2f/B2g). No cluster run and no run-1 reading existed at the re-freeze. **sha256 of the frozen prediction and conclusion tables** (B2f, B2g, B2i, B3f, B3g, B3i, copied to `harness/max-unsigned-short-validate-key-remaining--autonomous/frozen-prediction.txt`): `887a9b357ad887abaab2f8bcced6bbf38a37a7957ed7707b383a897850a5d73e`. Section D (feedback) is filled after the runs; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/max-unsigned-short-validate-key-remaining--autonomous/` (written after the freeze; not committed; md5s at each run start in `max-unsigned-short-validate-key-remaining--autonomous/run1/harness.md5.*`) |
| **Tiers and values** | Unit (B2): L in {0, 1, 1000, 65534, 65535, 65536, 70000, 1,000,000}, both methods; 100,000 streamed 65535-byte keys; 1,000 / 5,000 held keys at L=65535 and L=1. Cluster (B3): one node, K in {16, 1024, 32768, 65535, 65536} at N=10,000, small-key control K=16 N=650,000, binding-cap control K=32768 at pools 128 MiB (main pools 512 MiB). |
| **Audit bottom line** | **Ready after amendments** (B2i, B3i) - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

Estimate: **negative** (the constant bounds one key, not aggregate usage). Audited against `cassandra/cassandra-5.0.9/` (clean, `base.version` 5.0.9). Citations re-read: `QueryProcessor.java:245-263`, `FBUtilities.java:155-158`, `Validation.java:45-72`, `ModificationStatement.java:368-376, 775-805`, `SelectStatement.java:725-735`, `TriggerExecutor.java:205-212`, `CacheService.java:498-508`, `ClusteringPrefix.java:278-287`, `SortedTableWriter.java:169-172`, `conf/cassandra.yaml:660, 780-830, 1044, 1844, 1864`, `TableMetrics.java:493-502`.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of one key (heap as a side effect); B1 names total key bytes in memtable and disk. |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | A1: constant, not settable; B2b/B3b vary the key length (7 and 5 values) across the boundary, reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d measures heap of the driver's own list (the check retains nothing): gap named in B2i.5; B3d real resources (off-heap, disk, RssAnon) added by B3i.7. |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c: keys at 65534, 65535, 65536, 70000, 1,000,000; the memtable pools are driven to their limit at K=65535 (655 MB > 512 MiB). |
| A. Core question | positive control for a negative estimate | Partly -> Met | B2h: 1-byte keys move with key bytes; B3h: smaller pool. The B3h pool control as written (K=1 KB, N=10,000 = 10 MB under a 128 MiB pool) could not bind and lowered only the heap pool while the key bytes are off-heap: fixed in B3i.5 (K=32768, both pools). |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | B2f's 1 MB per 1,000 one-byte keys is wrong by 10x (about 0.08 MB): B2i.3 restates as a relation. B3f "roughly linear" and "near the configured space" given bounds in B3i.6. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows exist for confirmed, refuted, wrong boundary, control did not move, limit not reached. No row for a mixed result (unit confirms, cluster plateau at an unexpected level); the generic rule applies: "Not confirmed (no matching row)". Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2g/B3g row 1 needs the boundary rejection text (direct disallow) and usage scaling with N x K and plateau set by memtable pools. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: 1-byte keys, same-bytes small-key arm (re-specified in B3i.5), pool size change, same node config. |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | Paths `/local/...`, TableMetadata construction, memtable class, the need for random keys (compression) and a fresh table per arm were not stated: B2i.1, B3i.1-3. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | Boundary precheck and stop condition (B3i.4), numbers for B3f (B3i.6), observables and sampling (B3i.7). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Build trees by `copy-source.sh` + `ant jar`; bundled Python driver, `nodetool`; the driver, node script and analyser are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly -> Met | K=65535 x 10,000 = 655 MB exceeds a 512 MiB pool; K=1 KB under 128 MiB did not (fixed). Unit: 5,000 x 65.6 KB = 330 MB under `-Xmx1g`. tmpfs holds about 3 GB per life. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (2 notes) | All cited lines hold. `yaml:1044` and `:1864` are commented-out defaults; `CacheService.java:504` is a key-cache read corruption check, not a write-path backstop (recorded in section D of the case file). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | Local paths, tmpfs, port slot, extra yaml lines (B3i.1) | Applied, B3i.1, 2026-10-26 | `/local/...` absent; auto_snapshot and cleanup threshold affect the arms. |
| 2 | Random keys, fresh table per arm (B3i.2-3) | Applied | Zero-padded keys compress; truncate snapshots. |
| 3 | Boundary precheck as first trigger and run order (B3i.4) | Applied | Stop when the traced boundary is wrong. |
| 4 | Binding-cap control that can bind (B3i.5) | Applied | 10 MB cannot reach a 128 MiB pool; the key bytes sit in the off-heap pool. |
| 5 | Numbers for B3f (B3i.6) | Applied | "roughly linear", "near" had no bounds. |
| 6 | Observables: RssAnon, flush log lines (B3i.7) | Applied | Memtable regions are JNA malloc; the off-heap gauge is mis-registered. |
| 7 | B2f heap number, aggregate streaming, empty-key rows, leftover check (B2i.2-6) | Applied | 1 MB per 1,000 one-byte keys is wrong; the check's aggregate behaviour needs a stream much larger than one key. |
| 8 | Add a conclusions row for mixed results | Left for stage 3 | The no-matching-row rule covers it. |

**Agreement criteria** - not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 (unit 19:45 UTC, cluster 19:48 to 19:55 UTC) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876...`, 40 cores, 251 GiB), shared with other stage-4 agents running their own nodes at the same time (port slot 7: 127.0.7.1, JMX 7170) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant jar` once per tree (1 min 18 s each), no `ant` while a node ran | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b8-uk/u` (unit) and `~/s4-b8-uk/c` (node) by `copy-source.sh`, repository commit `93d6365` (tag `cassandra-5.0.9`, local baseline) | |
| Case-file commit / harness commit | the case file is untracked (sha256 in section 1); harness uncommitted | |
| Storage for node data | tmpfs `/dev/shm/s4-b8-uk/node/{data,commitlog,hints,saved_caches,logs}` (removed at the end); disk bytes are tmpfs bytes | |
| Full logs (path, outside the repo) | on `pc07`: `~/s4-b8-uk-logs/run1/{unit,cluster}/` (`summary.txt`, `session.log`, `system.log.life{1,2}`, `samples-*.csv`, `arms.jsonl`); shakedowns `shake1`..`shake3` (unit) and `shake-c1` (cluster, 500 and 200 writes), build logs `build-{u,c}.log`. Node settings: JDK 11, `MAX_HEAP_SIZE=2G` (G1), `ulimit -n 100000`, one-node ring, default `skiplist` memtable, `memtable_allocation_type: offheap_objects`, `memtable_cleanup_threshold: 0.99`, `auto_snapshot: false`, pools 512 MiB (life 1) and 128 MiB (life 2) | |

## 3. Runbook defects

The audit fixed the defects it found before run 1 (B2i, B3i); they are listed for stage 3. The instrument check found two harness faults and one case-file error.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2f | 1 MB per 1,000 one-byte keys is wrong by 10x (a heap `ByteBuffer.allocate(1)` costs about 72 B) | relation `L + 40..120` B per key, B2i.3 | 2026-10-26 | untracked file (sha256 in section 1) |
| 2 | audit | B3e.5 / B3f | the K = 1 KB, N = 10,000 control (10 MB) could not reach a 128 MiB pool, and `offheap_objects` puts key bytes in the off-heap pool, which the heap-pool control would not touch | K = 32768 and both pools, B3i.5 | 2026-10-26 | same |
| 3 | audit | B3a/B3c/B3e | `/local/...` paths, zero-padded keys that compress, truncate that snapshots, `pgrep -u $USER java` (matches other agents), numbers for "roughly linear" | B3i.1-4, B3i.6-8 | 2026-10-26 | same |
| 4 | instrument check | B2i.2 | the amendment claimed `UNSET_BYTE_BUFFER` is rejected with "Key may not be unset"; the constant is an empty buffer (`ByteBufferUtil.java:92`), so the "empty" check fires first and `QueryProcessor.java:255` is unreachable for it | text corrected, driver expectation fixed, tables re-frozen (section 1) before any cluster run | 2026-10-26 | same |
| 5 | instrument check | harness | `hold` with L=1 called `putInt` on a 1-byte buffer (`IndexOutOfBounds`) | `put(0, byte)` for L < 4 | 2026-10-26 | n/a (harness) |
| 6 | self-check | selfcheck.py | one self-check expected the sampled table directory to grow before the flush; memtable data is in memory and the directory stays empty until a flush (k32768 has no flush during the writes), so the check was wrong, not the run | check replaced by an RssAnon information line; 46 parts hold | 2026-10-26 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier, all L, both methods, streaming of 100,000 keys, hold at L=65535 and L=1; cluster tier, boundary precheck, five key sizes at N=10,000, small-key control (N=650,000) and the 128 MiB-pool control. **Command logs:** `max-unsigned-short-validate-key-remaining--autonomous/run1/unit/summary.txt`, `max-unsigned-short-validate-key-remaining--autonomous/run1/cluster/summary.txt`, `session.log.head` (first 6 KB; full logs on the node). The harness was checked by three unit shakedowns and a 700-write cluster shakedown (`shake-c1`) before run 1; they showed the same kind of numbers (the unit slopes 90.1 and 65617 B per key), so run 1's numbers are not independent of what the author had seen; the predictions (including the numbers of B2i and B3i) were frozen first.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`: 4 JVMs, 24 checks, 0 MISMATCH, all EXPECTED lines yes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `QueryProcessor.validateKey` and `Validation.validateKey`, L = 0 | rejected, "Key may not be empty" (both) | `unit/bounds.out` |
| L = 1, 1000, 65534, 65535 | accepted (both) | `unit/bounds.out` |
| L = 65536, 70000, 1,000,000 | rejected, exactly "Key length of L is longer than maximum of 65535" (both) | `unit/bounds.out` |
| `null` key; `UNSET_BYTE_BUFFER` | rejected, "Key may not be empty" (the unset branch is not reached) | `unit/bounds.out` |
| 100,000 fresh distinct 65535-byte keys through both methods, none held | 200,000 calls accepted, 0 rejected, 6,553,500,000 key bytes validated in 1.7 s, heap after GC 19.9 MB (before 13.4 MB) | `unit/stream.out` |
| hold 1,000 / 5,000 keys of 65535 B | retained 72,138,640 B at 1,000 and 334,607,888 B at 5,000 (the first value includes a baseline offset); slope 65,612.6 B per key | `unit/hold65535.out` |
| positive control: hold 1,000 / 5,000 keys of 1 B | slope 90.1 B per key (0.09 MB per 1,000 keys); slope ratio 728 | `unit/hold1.out`, `unit/summary.txt` |

**Cluster tier** (`run1/cluster/arms.jsonl`, `summary.txt`: 16 EXPECTED lines, all yes). "Data+Index" = bytes of `*-Data.db` plus `*-Index.db` after the flush; N x K is the key bytes written.

| Arm (pools) | Writes accepted / rejected | Data+Index | per N x K | Memtable pool flushes (`MEMTABLE_LIMIT`, logged off-heap usage) | Evidence (file) |
|---|---|---|---|---|---|
| boundary precheck, K = 65535 (5) / 65536 (5) | 5 / 0 and 0 / 5 with "Key length of 65536 is longer than maximum of 65535" | n/a | n/a | none | `cluster/summary.txt` |
| k16, N = 10,000 (512 MiB) | 10,000 / 0 | 442,528 B | per-row overhead dominates | 0 | `cluster/arms.jsonl` |
| k1024 | 10,000 / 0 | 20,691,686 B | 2.02 | 0 | same |
| k32768 | 10,000 / 0 | 657,193,102 B | 2.01 (Data.db 1.00) | 0 (pre-flush off-heap 328,010,000 B) | same, `flush-lines.life1.txt` |
| k65535 | 10,000 / 0 | 1,314,019,113 B | 2.01 (Data.db 1.00) | 1: 507.435 MiB (99 percent) off-heap | same |
| k65536 | 0 / 10,000, one message (the exact text) | 0 B; table directory and memtable unchanged | n/a | 0 | same |
| c16big: K = 16, N = 650,000 | 650,000 / 0 | 31,139,124 B | 3.0 (more than k1024) | 0 | same |
| p128_k32768: K = 32768, N = 10,000 (128 MiB pools, life 2) | 10,000 / 0 | 657,187,151 B | 2.01 | 2: 127.628 and 127.034 MiB (100 and 99 percent) off-heap | same, `flush-lines.life2.txt` |

Other cluster readings: first `MEMTABLE_LIMIT` usage ratio, K = 65535 at 512 MiB over K = 32768 at 128 MiB, 507.435 / 127.628 = 3.98; the `tablestats` "Memtable data size" is 530,000 B for 10,000 partitions at every K (it does not count partition keys), while the off-heap figure follows key bytes (10.57 MB at K = 1024, 328.0 MB at K = 32768); no `ERROR` line in either `system.log`; no flush before the explicit one at K <= 32768 and 512 MiB.

### 4.2 Conclusion and logic

1. **Validity.** The key length was driven across the boundary at both tiers (65534, 65535, 65536, 70000, 1,000,000 at unit; 65535 and 65536 at cluster) [observed: `unit/bounds.out`, `cluster/summary.txt`]. The memtable pool was driven to its limit: at K = 65535 (655 MB of keys) the 512 MiB off-heap pool reached 507.4 MiB (99 percent) and triggered a `MEMTABLE_LIMIT` flush [observed: `cluster/flush-lines.life1.txt`]. Fixed settings held: same yaml tail and `MAX_HEAP_SIZE=2G` in every arm of a life, fresh table per arm, `auto_snapshot: false` [observed: `cluster/summary.txt` (yaml tail), `session.log.head`]. The control moved (part 3). Valid.
2. **Readings.** One surprise inside the traced path: `UNSET_BYTE_BUFFER` is an empty buffer, so the unset branch cannot be reached through it (section 3, row 4). Another: Index.db is as large as Data.db for these keys (the key is stored in both), which is why Data+Index is 2.0 x N x K, not 1.0 [observed: `cluster/arms.jsonl`: data 658,595,161 and index 655,423,952 B at K = 65535]. The `c16big` arm took 149 s because it is 65 times as many writes.
3. **Matched row.** Unit B2g row 1, "Boundary behaves as in B2f, heap scales with key count x length": the boundary is as predicted, 65535 accepted and 65536 rejected, with the predicted message, at both methods [observed: `unit/bounds.out`]; heap grows by L + 82 B per accepted key held (65,612.6 B at L = 65535, 90.1 B at L = 1; ratio 728) with nothing bounding it below `-Xmx` [observed: `unit/hold*.out`], and 6.55 x 10^9 key bytes (100,000 times the per-key cap) were validated without a rejection [observed: `unit/stream.out`]. Cluster B3g row 1, "Disk and memtable use scale with N x K up to 65535, 65536 rejected, plateau set by `memtable_*_space`": Data+Index grows 442 kB, 20.7 MB, 657 MB, 1,314 MB for K = 16, 1024, 32768, 65535 [observed: `cluster/arms.jsonl`]; 10,000 of 10,000 writes at K = 65536 were rejected with the exact message and nothing reached the table directory or memtable [observed: `cluster/summary.txt`]; the memtable pool reached its limit at 507.4 MiB at 512 MiB pools and 127.6 MiB at 128 MiB pools, a ratio of 3.98 for pools in the ratio 4 [observed: `cluster/flush-lines.life{1,2}.txt`]. Row 4 (the plateau moves with the pool setting while usage across K stays per-byte-of-key) also holds: Data.db is 1.00 x N x K at K = 32768 and 65535 in the same logs.
4. **Excluded rows.** Unit "Heap stays flat or capped as the number of accepted keys grows -> Refuted": the retained heap grew 65.6 KB per key [observed]. "65536 accepted or 65535 rejected": the opposite [observed]. "Usage flat while the positive control also stays flat": the 1-byte control moved 90 B per key against 65,613 B [observed]. "Limit never reached because the driver fails earlier": all four JVMs exited 0 [observed: `unit/summary.txt`]. Cluster "Usage plateaus at a level that depends on 65535 and not on memtable settings -> Refuted": the plateau followed the pool (507 MiB versus 128 MiB, both near 100 percent of the pool) and disk grew with N x K [observed]. "No flush or plateau seen, or the control plateau does not move": a `MEMTABLE_LIMIT` flush occurred at K = 65535 (512 MiB) and twice in the control (128 MiB) [observed].
5. **Observed vs. inferred.** [inferred: "usage is bounded by the aggregate memtable limits, not by `MAX_UNSIGNED_SHORT`".] The cluster shows the usage plateau tracks the pool setting; the key cap's value was not changed (it is a constant), so "does not cap" rests on usage being linear in key bytes up to and including the boundary key, and the pool moving the plateau, not on varying the constant. [inferred: the unit heap readings are for the harness's own list of buffers.] They show what holding that many accepted keys costs; the node's own accounting is the cluster tier. [inferred: tmpfs bytes stand for disk bytes.]
6. **Deviations and gaps.** (a) The shakedowns showed similar numbers before run 1. (b) The B3h control lowered both memtable pools instead of `memtable_heap_space` alone (B3i.5), because the key bytes sit in the off-heap pool. (c) The sample columns of `samples-*.csv` were not used as evidence (the directory stays empty until a flush; `RssAnon` growth in a 2 GiB-heap JVM is noisy). (d) The `MEMTABLE_LIMIT` flush at K = 65535 ran before the explicit flush, so Data+Index for that arm covers two sstables. (e) `native_memory summary` was not used (memtable regions are malloc'd). (f) `nodetool tablestats` "Memtable data size" excludes partition keys; the off-heap figure and the pool accounting include them.
7. **Core question.** Usage follows the key bytes, not the constant: heap held, off-heap memtable space and disk bytes all grow linearly in N x K up to the boundary key (part 3), the disallow branch fires exactly at 65536 with the predicted text and writes nothing (part 3), and the total that a node holds is bounded only when the memtable pool reaches its configured limit, which moved with the pool setting while the key size stayed at the boundary (part 3, with the known-binding control). The constant limits one key, not the aggregate: 6.55 x 10^9 key bytes passed the check (part 3).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with row 4 for the control) - confirmed (the claim: usage does not follow the 65535-byte cap).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/max-unsigned-short-validate-key-remaining--autonomous/selfcheck.py` re-parses the raw files (`unit/*.out`; `cluster/session.log` writer outputs; `system.log.life{1,2}` flush lines and Data.db sizes; `samples-*.csv`) with its own code; output `run1/selfcheck.out`: 46 parts hold, 0 do not hold (after replacing one wrong check, section 3 row 6). Index.db bytes exist only in `arms.jsonl` (the files were dropped after each arm); that input is used as recorded. The harness's Data.db totals agree with the sum of the node's own "Completed flushing" sizes within 0.5 percent.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: precheck 5/5 and 5/5; a `MEMTABLE_LIMIT` flush in k65535 (507.4 MiB) and p128 (127.6, 127.0 MiB); no `ERROR`; no daemon of the run left. |
| 2. Readings | yes | Index.db equal to Data.db size is in `arms.jsonl`; Data.db ratio 1.000 to the flush log. |
| 3. Matched row | yes | Bounds, stream and slope numbers recomputed from `unit/*.out`; Data.db, flush usage and plateau ratio (3.98) recomputed from the node logs. |
| 4. Excluded rows | yes | Same files. |
| 5. Observed vs. inferred | yes | The inferences are named in 4.2 part 5; the raw files hold nothing stronger (the constant cannot be varied). |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Per-key gate (unit) and aggregate growth plus pool plateau with control (cluster) follow B1 and B3h. |

### 5.2 Run 2?

**No** (2026-10-26). The conclusion rests on exact boundary behaviour and on numbers that the node's own logs reproduce; the one inference (that the plateau is the pool and not the constant) is what the control, which moved by the predicted factor, settles. A run 2 would repeat a 7 minute run and add nothing the logs do not already hold.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap): the constant bounds one key; the usage that a node holds follows other limits.

**Claim tested (B1):** node memory and disk usage do not follow the 65535-byte key cap: with the cap fixed, usage for a fixed number of partitions grows in proportion to total key bytes (up to 64 KB per key) and is bounded by the aggregate limits (memtable space, etc.), not by `MAX_UNSIGNED_SHORT`; the cap only rejects any single key above 65535 bytes. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 1; row 4 for the control) | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control:** the 1-byte-key run moved 90 B per key against 65,613 B at the unit tier (ratio 728), and at the cluster tier the known-binding cap (both memtable pools 128 MiB instead of 512 MiB) moved the logged plateau from 507.4 to 127.6 MiB (3.98 for a pool ratio of 4) with the same key size and workload.

**Side findings (do not change the verdict):** (1) `QueryProcessor.validateKey`'s "Key may not be unset" branch (`QueryProcessor.java:255`) is unreachable for `UNSET_BYTE_BUFFER` because that constant is an empty buffer (`ByteBufferUtil.java:92`) and the "empty" check at line 251 fires first: dead code, an upstream candidate (JIRA check first). (2) `nodetool tablestats` "Memtable data size" does not include partition-key bytes (530,000 B for 10,000 partitions at every K), while the memtable pool and the off-heap figure do; anyone sizing memtables from that line under-counts large keys. (3) Index.db holds the key again, so large keys cost twice on disk (2.0 x N x K for Data+Index).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (untracked file, sha256 below), no further section amended; the audit amendments B2i and B3i are listed in section 1. Sha256 of the case file with D filled: `62068d9d37fc94cd24508dac7183b206d15e9e558cd37b7b0d614ccf1bf892b3`.
