# max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous — stage-4 results  <!-- file: results/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous`](../../stage3-ai-deep-read/cases/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md)
>
> **Status:** verdict filed (2026-10-27 UTC; run on 2026-10-26 local) - run 1 done at both tiers, self-checked, no run 2
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap`) — [definition](../README.md#outcome-class)
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
| **Case-file version** | Base repository commit `93d6365`; the case file is **untracked** (no commit holds it). **sha256 of the whole file after the audit's amendments (B2i, B3i, 2026-10-26): `e5df4a19b2fa3e13b6662e3c67ce230578b6a52fdee9cace42b70af046476e5f`**, frozen 2026-10-26 before the harness existed and before any reading. **sha256 of the frozen prediction and conclusion tables** (B2f, B2g, B2i, B3f, B3g, B3i, copied to `harness/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/frozen-prediction.txt`): `363886fb540bf96d19f1fd376add1e6469e3a4344ec566bd13b09fbb0486d18c`. Section D is filled after the runs. |
| **Harness** | `harness/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/` (written after the freeze; not committed; md5s at each run start in `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/run1/harness.md5.*`) |
| **Tiers and values** | Unit (B2): S x N grid with exact messages, ArrayClustering cells, held series 10k-100k of 1000-byte clusterings (3 JVMs), S=1 and capped-list controls, 100,000 streamed 65535-byte clusterings. Cluster (B3): precheck (single and two-component), K=100/R=1e5, K=1000/R=1e5, K=1000/R=1e6, K=65535/R=1e4, K=65536/R=1e4 at 256 MiB pools; K=65535/R=1e4 at 64 MiB pools; probe (CAS insert, slice delete) outside B3g. |
| **Audit bottom line** | **Ready after amendments** (B2i, B3i) - 2026-10-26 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of one clustering component and of the clustering sum; B1 names key bytes in memtable and disk. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | A1: constant (not settable); B2b/B3b vary component size, component count and key size across the 65535 boundary; the reason is stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d measures the heap of the driver's own list (check retains nothing): gap named in B2i.6; B3d lists tablestats/heap_info only, key bytes are off-heap malloc: B3i.7 adds RssAnon, sstable bytes, flush log lines. |
| A. Core question | usage driven to the limit and past it | Met | B2c/B3c: 65535, 65536, 70000; 1 GB of keys vs 256 MiB pool (K=1000, R=1e6), 655 MB at K=65535. |
| A. Core question | positive control for a negative estimate | Partly -> Met | B2e.4 control (a list that stops at a count) unspecific: B2i.5 gives S=1 and a capped-list control with numbers. B3e.5 control ("small offheap space, show flushes") would be a different workload: B3i.5 reruns the K=65535 workload at 64 MiB pools. |
| B. Logic | each step says what it establishes | Met | B2e, B3e (with B2i/B3i). |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | B2f "about 1 KB per key" and B3f "roughly in proportion" had no bounds: B2i.3 (S+40..S+200 B per key), B3i.6 (1.0-3.0 x R x K, plateau at most 1.25 x pool). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows exist for confirmed, refuted, control failed, limit never reached, boundary wrong (B2g, B3g). No row for a mixed result (unit confirms, cluster plateau elsewhere): the generic "Not confirmed (no matching row)" applies. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly -> Met | B3g row 1 needs the boundary insert failing with the text (direct disallow) and usage growing with R x K; B3i.4 makes the disallow evidence the exact message plus the sum branch. |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h plus B2i.5, B3i.5: small keys, capped list, pool change, same node config. |
| C. Specific | a human can follow it from the intro and §9a | Met | A1-A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly -> Met | Paths (`/local/...`), pk values, random ck, fresh table per arm, tmpfs, port, extra yaml: B2i.1, B3i.1-2. Error found in A3: "batches" are not a bypass (they use addUpdates); the conditional write and range deletes are: B3i.8. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | Grid cells, arms, precheck/stop condition, sampling: B2i.2, B3i.3-4, B3i.7. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Tree by copy-source.sh + ant jar (done, 2 min); bundled Python driver; the unit driver, node script, writer and analyser are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 1 GB and 655 MB of key bytes against a 256 MiB pool; tmpfs 126 GB; 1e6 inserts at about 32 in flight is minutes; unit: 100 MB under -Xmx1g. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met (3 notes) | `ClusteringPrefix.java:272-288`, `:317`, `NativeClustering.java:50`, `ModificationStatement.java:815`, `FBUtilities.java:158` hold. Notes: the first-branch message reports `dataSize()` (the sum), not the offending size; `PartitionKeySingleRestrictionSet.java:67` also calls `validate()` (composite partition keys); the CAS path (`:573`) and slice deletes (`:762-787`) skip it, "batches" do not. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Tree path, tmpfs, port slot, extra yaml lines, pk values, random ck, fresh table per arm (B2i.1, B3i.1-2) | Applied, B2i.1 and B3i.1-2, 2026-10-26 | `/local/...` absent; zero-padded keys compress; drop snapshots by default |
| 2 | Exact boundary grid and message rule, ArrayClustering cell (B2i.2) | Applied | The first-branch message reports the sum of all components |
| 3 | Numbers for B2f and B3f (B2i.3, B3i.6) | Applied | "about 1 KB", "roughly in proportion" had no bounds |
| 4 | Aggregate stream and controls with numbers (B2i.4-5, B3i.5) | Applied | The check retains nothing; a control that cannot bind says nothing |
| 5 | Two-component sum precheck (B3i.4) | Applied | Traced line `:284` otherwise untested at cluster tier |
| 6 | Bypass probe: CAS insert and slice delete (B3i.8) | Applied as an informational probe outside B3g | A3 names bypasses imprecisely ("batches"); the source shows the conditional path and slice deletes |
| 7 | Add a conclusions row for mixed results | Left for stage 3 | The no-matching-row rule covers it |
| 8 | Correct A3 (batches; composite partition key also calls `validate()`) | Left for stage 3 (stated in B3i.8; A3 text not rewritten) | Not needed for a valid run |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-26 local (unit 19:51 EDT, cluster 19:52 to 20:00 EDT; timing log in UTC) | not done |
| Node (CloudLab name and type) | `pc07` (`node0.jason92-320876...`, 40 cores, 251 GiB), shared with other stage-4 agents running their own nodes at the same time (port slot 6: 127.0.6.1, JMX 7160) | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant jar` once (about 2 min), no `ant` while a node ran | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b9-cp` by `copy-source.sh`, repository commit `93d6365` (tag `cassandra-5.0.9`, local baseline); unit driver compiled outside the tree | |
| Case-file commit / harness commit | the case file is untracked (sha256 in section 1); harness uncommitted | |
| Storage for node data | tmpfs `/dev/shm/s4-b9-cp/node/{data,commitlog,hints,saved_caches,logs}` (removed at the end); disk bytes are tmpfs bytes | |
| Full logs (path, outside the repo) | on `pc07`: `~/s4-b9-cp-logs/run1/{unit,cluster}/` (`summary.txt`, `session.log`, `system.log.life{1,2}`, `samples-*.csv`, `arms.jsonl`); shakedowns `shake1` (unit) and `shake-c1` (cluster, 500 and 200 inserts plus the probe); `build.log`. Node settings: JDK 11, `MAX_HEAP_SIZE=1G`, `ulimit -n 100000`, one-node ring, `memtable_allocation_type: offheap_objects`, `memtable_cleanup_threshold: 0.99`, `auto_snapshot: false`, pools 256 MiB (life 1) and 64 MiB (life 2) | |

## 3. Runbook defects

The audit fixed the defects it found before run 1 (B2i, B3i). The instrument checks and the self-check found two harness faults; neither is a case-file error and neither changes a conclusion row.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | A3 / B3e | A3 lists "batches that do not go through `ModificationStatement`" as bypass; batches do go through `addUpdates` (`ModificationStatement.java:753-`). The skipped paths are the conditional write (`:573`, no `validate()`) and range deletes by slice (`:762-787`). `PartitionKeySingleRestrictionSet.java:67` also calls the method (composite partition keys). | B3i.8 states it and tests it as a probe; A3 text left for stage 3 | 2026-10-26 | untracked file (sha256 in section 1) |
| 2 | audit | B2e.4 / B3e.5 | unspecific controls; `/local/...` paths; no pk values; no numbers for "roughly in proportion" | B2i.1-6, B3i.1-7 | 2026-10-26 | same |
| 3 | run 1 (cluster) | harness, arm `k1000_r1e6` | four flushed sstables made the node start a size-tiered compaction (`system.log.life1`: `Compacting ... nb-1..nb-4`, then `Compaction interrupted ... 243808941 / 1015972182 bytes` when the table was dropped); the harness measured `*-Data.db` while its output was part-written, so `arms.jsonl` shows Data.db 1,229,642,429 B instead of 1,015,971,578 B (sum of the node's own "Completed flushing" sizes, which equals the compaction's 1,015,972,182 B input within 0.01 percent) | the flush-log figure is used for that arm; Data+Index with it is 1.054 x N*K; the other arms flushed fewer than 4 sstables and agree with their flush logs within 0.5 percent | 2026-10-27 | n/a (harness) |
| 4 | self-check | selfcheck.py | the "no daemon left" check matched the tool shell whose command line contained the path text, so it failed on a fresh run | match `CassandraDaemon` and the path together; 77 parts hold | 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier, whole grid, stream, held series (3 JVMs), S=1 and capped controls; cluster tier, precheck (single and two-component), five arms at 256 MiB pools, the 64 MiB control, and the probe. **Command logs:** `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/run1/unit/summary.txt`, `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/run1/cluster/summary.txt`, `session.log.head` (first 6 KB; full logs on the node). The harness was checked by one unit shakedown (`shake1`) and one cluster shakedown (`shake-c1`, including the probe) before run 1; they showed the same kind of numbers (slopes 1116.4 to 1116.7 B per key, the probe outcomes), so run 1's numbers are not independent of what the author had seen; the predictions (B2i, B3i) were frozen first.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`: 8 JVMs, 0 MISMATCH, all EXPECTED lines yes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| S x N grid, S in {1, 1000, 32767, 32768, 65534, 65535, 65536, 70000}, N in {1, 2, 3} (24 cells) | rejected exactly where a component exceeds 65535 or the sum does; the message reports the sum of all components (S=65535, N=2: 131070; S=32768, N=2: 65536); accepted: all N=1 cells up to S=65535, S=32767 up to N=2, S=1000 and S=1 | `unit/grid.out` |
| mixed cells | (65536,1) rejected, "Key length of 65537" (sum, not the offending size); (65535,1) rejected, 65536; (65535,0 B), (65535,null), (32768,32767) accepted; (null,65536), (1,70000) rejected; (1000 x 65) accepted, (1000 x 66) rejected with 66000 | `unit/grid.out` |
| `Clustering.EMPTY`, `STATIC_CLUSTERING`, `ArrayClustering` (65535 accepted, 65536 rejected) | as predicted | `unit/grid.out` |
| 100,000 fresh distinct 65535-byte clusterings, none held | 100,000 accepted, 0 rejected, 6,553,500,000 bytes validated in 1.3 s, heap after GC 12.9 MB (before 12.9 MB) | `unit/stream.out` |
| hold S=1000, 10k to 100k, three JVMs | slope 1116.7, 1116.7, 1116.8 B per key (S + 116.7); 100.5 MB growth from 10k to 100k; every 10k step within 10 percent of the mean; `validate()` never threw | `unit/series1000{a,b,c}.out` |
| positive control: hold S=1 | slope 124.7 B per key; ratio 1116.7 / 124.7 = 9.0 | `unit/series1.out`, `unit/summary.txt` |
| positive control: S=1000 with the newest 10,000 kept (a known cap) | heap at 100k within 42,744 B of heap at 10k (uncapped: +100.5 MB) | `unit/capped.out` |

**Cluster tier** (`run1/cluster/arms.jsonl`, `summary.txt`: 24 EXPECTED lines, 23 yes and 1 NO, explained below). Data+Index = bytes of `*-Data.db` plus `*-Index.db` after the flush; R x K is the key bytes written.

| Arm (pools) | Inserts accepted / rejected | Data+Index (Data.db / Index.db) | per R x K | `MEMTABLE_LIMIT` flushes (logged off-heap usage) | Evidence (file) |
|---|---|---|---|---|---|
| precheck, single ck: K = 65535 (5) / 65536 (5) | 5 / 0 and 0 / 5 with "Key length of 65536 is longer than maximum of 65535" | n/a | n/a | none | `cluster/summary.txt` |
| precheck, two ck: (32768, 32767) (3) / (32768, 32768) (3) / (70000, 10) (3) | 3 / 0; 0 / 3 with the 65536 text (sum branch); 0 / 3 with "Key length of 70010" (first branch, the sum) | n/a | n/a | none | `cluster/summary.txt` |
| k100_r1e5: K = 100, R = 100,000 (256 MiB) | 100,000 / 0 | 10,820,422 (10,774,843 / 45,579) | 1.08 | 0 | `cluster/arms.jsonl` |
| k1000_r1e5: K = 1000, R = 100,000 | 100,000 / 0 | 104,855,758 (101,624,363 / 3,231,395) | 1.05 | 0 | same |
| k1000_r1e6: K = 1000, R = 1,000,000 | 1,000,000 / 0 | Data.db 1,015,971,578 from the flush log (harness 1,229,642,429 includes a compaction in flight, section 3 row 3) + Index.db 37,780,052 | 1.05 | 3 (253.5, 253.4, 253.4 MiB, 99 percent), plus the forced flush | same, `flush-lines.life1.txt` |
| k65535_r1e4: K = 65535, R = 10,000 | 10,000 / 0 | 1,969,386,988 (658,487,470 / 1,310,899,518) | 3.005 (Data 1.00, Index 2.00) | 2 (254.0 MiB, 99 percent) | same |
| k65536_r1e4: K = 65536, R = 10,000 | 0 / 10,000, one message (the exact text) | 0 B; table directory and memtable unchanged | n/a | 0 | same |
| p64_k65535_r1e4: K = 65535, R = 10,000 (64 MiB, life 2) | 10,000 / 0 | 1,969,391,504 | 3.005 | 9 (63.5 to 64.0 MiB, 99 to 100 percent) | same, `flush-lines.life2.txt` |

Other cluster readings: first `MEMTABLE_LIMIT` usage, K = 65535 at 256 MiB over K = 65535 at 64 MiB: 254.0 / 64.0 = 3.97 for pools in the ratio 4; at K = 1000 the 1 GB of key bytes is 3.7 times the 256 MiB pool and the logged off-heap usage stayed at 253.5 MiB; the node's heap pool use stayed small (about 36 MiB at most); `nodetool tablestats` "Memtable data size" at K = 65535 was 122,766,560 B before the flush against 655 MB written (it covers only what was in the memtable then, after two limit flushes); RssAnon peaks 1.7 to 2.1 GiB (a 1 GiB-heap JVM, so not used as evidence).

**Probe, outside B3g** (`cluster/summary.txt`, `probe-errors.life2.txt`): (a) plain insert with a 65536-byte ck: rejected with the exact text. (b) `INSERT ... IF NOT EXISTS` with a 65536-byte ck: not rejected at statement level; the client got `WriteTimeout` (write_type CAS) after 20 s, and `system.log` shows `java.lang.AssertionError: Data size 65536 >= 65536` at `NativeClustering.<init>(NativeClustering.java:50)` in `MutationStage-1` (uncaught, `JVMStabilityInspector`). (c) `DELETE ... WHERE pk = ? AND ck > <70000-byte value>`: accepted; the later `nodetool flush` of that table failed in `MemtablePostFlush` with `AssertionError: Attempted serializing to buffer exceeded maximum of 65535 bytes: 70000` (`ByteBufferUtil.writeWithShortLength`, from `StatsMetadata` serialization, `ByteBufferUtil.java:366`). The node stayed alive.

### 4.2 Conclusion and logic

1. **Validity.** The boundary was driven across at both tiers: 65535, 65536 and 70000 in the grid [observed: `unit/grid.out`], and 65535, 65536, the two-component sum and the first branch at the cluster [observed: `cluster/summary.txt`]. The memtable pool was driven to its limit: at K = 1000 and R = 1,000,000 (1 GB of keys) and at K = 65535 the 256 MiB off-heap pool reached 253.5 and 254.0 MiB and triggered `MEMTABLE_LIMIT` flushes [observed: `cluster/flush-lines.life1.txt`]. Fixed settings held: same yaml tail and `MAX_HEAP_SIZE=1G` in every arm of a life, fresh table per arm, `auto_snapshot: false` [observed: `cluster/summary.txt` (yaml tail)]. The controls moved (part 3). Valid.
2. **Readings.** Surprises inside the traced path: (a) the first-branch message reports the sum of all components, not the offending one (65537 for (65536, 1)) [observed: `unit/grid.out`]; (b) Index.db holds the clustering again: 2.00 x R x K at K = 65535 (one index block per row; first and last name each), so Data+Index is 3.005 x R x K, just above the 3.0 bound of B3i.6 (the bound was an audit estimate; B3g's row is about growth with R x K) [observed: `cluster/arms.jsonl`]; (c) the `k1000_r1e6` Data.db reading was contaminated by a compaction in flight (section 3 row 3) [observed: `cluster/system.log.life1`].
3. **Matched row.** Unit B2g row 1, "Per-key throw only at the predicted S/N cells, heap grows linearly with M with no throw": the grid throws exactly at the predicted cells, with the exact text [observed: `unit/grid.out`]; the held heap grows by S + 116.7 B per key (1116.7 B at S = 1000, three JVMs within 0.01 percent) with `validate()` never throwing, and 6.55 x 10^9 bytes (100,000 times the per-key cap) were validated without a rejection [observed: `unit/series1000*.out`, `unit/stream.out`]. Cluster B3g row 1, "Boundary behaviour as predicted, and usage keeps growing with R beyond 65535 bytes": K = 65536 was rejected 10,000 of 10,000 times with the exact text and nothing reached the table directory or the memtable; K = 65535 and the two-component cases behaved as predicted [observed: `cluster/summary.txt`]; Data+Index grew 10.8 MB, 104.9 MB, about 1.05 GB (K = 1000, R = 1e6) and 1.97 GB (K = 65535, R = 1e4), 1.05 to 3.005 times R x K [observed: `cluster/arms.jsonl`, `flush-lines.life1.txt`], far above 65535 bytes, with no error from this check. Row 4 (control): "Memtable usage flat at the memtable cap in the control while disk keeps growing": the first `MEMTABLE_LIMIT` usage was 254.0 MiB at the 256 MiB pools and 64.0 MiB at the 64 MiB pools with the same workload (ratio 3.97), while Data+Index stayed 1.97 GB in both [observed: `cluster/flush-lines.life{1,2}.txt`, `cluster/arms.jsonl`].
4. **Excluded rows.** Unit "Heap flat while M grows (and the control grows) -> Refuted": the held heap grew 100.5 MB from 10k to 100k [observed]. "Heap flat in the control -> control failed": the S=1 control grew at 124.7 B per key (slope ratio 9.0) and the capped control stayed flat (42,744 B change) [observed], so the instrument tells capped from uncapped. "`validate()` never throws in the grid": it threw in 20 of the 37 grid cell lines [observed]. "Throws at S < 65535 with N=1 -> trace wrong": none thrown [observed]. Cluster "Usage plateaus near 65535 bytes total -> Refuted": usage was 1.97 GB [observed]. "Control does not flush at the small cap, or load never exceeds the limit -> Not confirmed": 9 `MEMTABLE_LIMIT` flushes at 64 MiB and 2 to 3 at 256 MiB [observed].
5. **Observed vs. inferred.** [inferred: "usage is bounded by the aggregate memtable limits, not by `MAX_UNSIGNED_SHORT`".] The cluster shows the logged plateau tracks the pool setting (3.97 for 4); the constant cannot be varied, so "does not cap" rests on usage being linear in key bytes up to the boundary key and the pool moving the plateau, not on varying the constant. [inferred: the unit heap readings are for the harness's own list of clusterings.] They show what holding that many accepted keys costs; the node's accounting is the cluster tier. [inferred: tmpfs bytes stand for disk bytes.] [inferred: the Data.db figure for `k1000_r1e6` from the flush log stands for the true size (it equals the compaction's input total).]
6. **Deviations and gaps.** (a) The shakedowns showed similar numbers before run 1. (b) The Data+Index ratio at K = 65535 is 3.005, 0.17 percent above the 3.0 bound of B3i.6, and one EXPECTED line reads NO for it; this changes no conclusion row. (c) `k1000_r1e6` Data.db measured during a compaction (section 3 row 3). (d) The B3h control changes both pools (key bytes are off-heap). (e) The probe was not part of the frozen tables; it is a side finding. (f) The probe ran only with `offheap_objects` memtables; behaviour of (b) with heap memtables was not tested. (g) The sample columns of `samples-*.csv` were not used as evidence (a 1 GiB-heap JVM's RssAnon is noisy and the table directory stays empty until a flush).
7. **Core question.** Usage follows the key bytes, not the constant: held heap, off-heap memtable space and disk bytes all grow with the number of keys and their sizes up to the boundary key (part 3), the disallow branch fires exactly at 65536 and at a sum above 65535, with the predicted text, and writes nothing (part 3), and what a node holds is bounded only when the memtable pool reaches its configured limit, which moved with the pool setting while the workload stayed the same (part 3, with the known-binding control). The constant limits one clustering key, not the aggregate: 6.55 x 10^9 bytes passed the check at unit tier and 1.97 GB landed in one table at the cluster tier.

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with row 4 for the control) - confirmed (the claim: the 65535-byte clustering limit does not bound total memory or disk usage).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/selfcheck.py` re-parses the raw files (`unit/*.out`; `cluster/session.log` writer outputs; `system.log.life{1,2}` flush lines, Data.db sizes, compaction and error lines; `samples-*.csv`) with its own code and its own re-implementation of the B2i.2 rule; output `run1/selfcheck.out`: 77 parts hold, 0 do not hold (after replacing the daemon-check pattern, section 3 row 4, and handling the compaction artefact, row 3). Index.db bytes exist only in `arms.jsonl` (the files were dropped after each arm); that input is used as recorded and marked.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: precheck 5/5 and 3/3 of each kind; `MEMTABLE_LIMIT` flushes at 253.5 and 254.0 MiB (256 MiB pools) and 64.0 MiB (64 MiB pools); no `ERROR` in life 1; in life 2 the first `ERROR` comes after the probe table was created; no daemon of the run left. |
| 2. Readings | yes | Index.db equal to 2.00 x R x K at K = 65535 and the compaction in flight at `k1000_r1e6` are both in the raw files. |
| 3. Matched row | yes | Grid cells (the 24 uniform and 10 mixed cells re-derived with the independent rule, plus EMPTY, STATIC and the ArrayClustering cells), slopes, stream, capped control and plateau ratio (3.97) recomputed from the raw files. |
| 4. Excluded rows | yes | Same files. |
| 5. Observed vs. inferred | yes | The inferences are named in 4.2 part 5; the raw files hold nothing stronger (the constant cannot be varied). |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6; the 3.005 ratio is reported by the self-check as OUTSIDE the frozen bracket, not hidden. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Per-key gate (unit) and aggregate growth plus pool plateau with control (cluster) follow B1 and B3h. |

### 5.2 Run 2?

**No** (2026-10-27). The conclusion rests on exact boundary behaviour and on numbers that the node's own logs reproduce; the one inference (the plateau is the pool, not the constant) is what the control, which moved by the predicted factor, settles. A run 2 would repeat a 9 minute run and add nothing the logs do not already hold.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap): the constant bounds one clustering key; the usage a node holds follows other limits.

**Claim tested (B1):** the 65535-byte clustering limit does not bound total memory or disk usage: a node's usage grows with the number of rows written (many keys each under the limit), and the limit only rejects single keys that are too large. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1) | does not cap | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row 1; row 4 for the control) | does not cap | run 1 + self-check | 2026-10-27 |

**Positive control:** at the unit tier, a known cap (newest 10,000 kept) held the heap flat (42,744 B change over 90,000 more keys) while the uncapped loop grew 100.5 MB, and 1-byte clusterings grew at 124.7 B per key against 1116.7 B (ratio 9.0); at the cluster tier the known-binding cap (both memtable pools 64 MiB instead of 256 MiB) moved the logged plateau from 254.0 to 64.0 MiB (3.97 for a pool ratio of 4) with the same key size and workload.

**Side findings (do not change the verdict):** (1) `INSERT ... IF NOT EXISTS` skips `ClusteringPrefix.validate()` (`ModificationStatement.java:573` takes the clustering without it); with `offheap_objects` a 65536-byte clustering then fails at `NativeClustering.java:50` (`assert dataSize <= MAX_UNSIGNED_SHORT`) in the mutation stage and the client waits for the 20 s write timeout instead of receiving the "Key length" error: upstream candidate (JIRA check first). (2) A range delete whose clustering bound is 70000 bytes passes statement validation (the slice branch `:762-787` never validates) and later makes the memtable flush fail (`ByteBufferUtil.writeWithShortLength` assertion during `StatsMetadata` serialization): a poison-pill candidate; whether the data returns after a restart or blocks commit-log replay was not tested. (3) The first-branch error message reports the sum of all components, not the oversize one (65537 for (65536, 1)). (4) Index.db repeats the clustering of each index block: 2.00 x R x K at K = 65535, so large clustering keys cost three times their size on disk (Data + Index). (5) `ClusteringPrefix.validate()` is also called for composite partition-key components (`PartitionKeySingleRestrictionSet.java:67`). (6) Four flushed sstables are enough to start a compaction inside a measurement window; measure sstable bytes from the flush log when 4 or more sstables are flushed.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (untracked file, sha256 recorded in the case file notes below), no other section amended beyond B2i and B3i (section 1).
Sha256 of the case file with D filled: `832951f38c86ec2bc6164137b1a03e77109d5c1ad0f9353ec41d68bdc63097b1`.

**Leftovers on the node (pc07):** no process of this run (checked by PID and by `CassandraDaemon` + path; the daemon seen on the host at shakedown time belongs to another agent, `s4-b9-bt`); tmpfs `/dev/shm/s4-b9-cp` removed. Left on disk: build tree `~/s4-b9-cp` (about 700 MB, built), logs `~/s4-b9-cp-logs/` (`run1`, `shake1`, `shake-c1`, `build.log`).
