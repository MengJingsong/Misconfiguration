# max_unsigned_short-validateindexedvalue-value_remaining--autonomous — stage-4 results  <!-- file: results/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`max_unsigned_short-validateindexedvalue-value_remaining--autonomous`](../../stage3-ai-deep-read/cases/max_unsigned_short-validateindexedvalue-value_remaining--autonomous.md)
>
> **Status:** verdict filed (2026-10-28) - run 1 done at both tiers, self-checked, no run 2
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
| **Case-file version** | Base repository commit `b68711e5`; the case file is modified/untracked in the working tree (no commit holds the audited version). **sha256 of the whole file after the audit amendments (B2i, B3i, 2026-10-28): `647419b263d52189abf76a655b899a06e85dd3957c5ee6c10afa5a0858624882`**, frozen 2026-10-28 before the harness existed and before any reading. B2f, B2g, B3f, B3g are unchanged by the audit; B2i and B3i only give numbers and exact procedures. Section D is filled after the runs; the file's sha256 with D filled is in section 8. |
| **Harness** | `harness/max_unsigned_short-validateindexedvalue-value_remaining--autonomous/` (written after the freeze; not committed; md5s at each run start in `max_unsigned_short-validateindexedvalue-value_remaining--autonomous/run1/harness.md5.*`) |
| **Tiers and values** | Unit (B2): S in {1000, 65533, 65534, 65535, 65536} on a regular text column; clustering blob column at 65535 and 65536; N in {100, 1000, 4000} at S = 65534; pools 2048 MiB and 64 MiB; no-index control. Cluster (B3): S = 65534 at N in {1000, 4000, 16000}, S = 65535 (N = 200), no-index control, small-value control, `memtable_offheap_space` 512 MiB and 256 MiB. |
| **Audit bottom line** | **Ready after amendments** (B2i, B3i) - 2026-10-28 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

Estimate: **negative**. Audited against `cassandra/cassandra-5.0.9/` (clean, `base.version` 5.0.9). Citations re-read: `CassandraIndex.java:181, 225, 320-338, 580-627`, `FBUtilities.java:158`, `SingleTableUpdatesCollector.java:105-112`, `PartitionUpdate.java:543-549`, `SecondaryIndexManager.java:1340-1350`, `ClusteringPrefix.java:272-287`, `Validation.java:45-56`, `QueryProcessor.java:249-262`, `AbstractAllocatorMemtable.java:125, 190`, `SkipListMemtable.java:363`, `build.xml:1255`, `test/conf/cassandra.yaml`. All hold; the earlier `Validation.java` path correction is right.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly -> Met | A2: the constant bounds one value's bytes (a format limit); B1 names memtable and index-table disk bytes growing with rows. |
| A. Core question | knob varied, >= 3 values incl. default - or another approach, with the reason | Met | A1: not settable; B2b/B3b vary value size S across the boundary (5 values) and N (3 values), reason stated. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly -> Met | B2d accessor names unverified; B2i.3 fixes them (`getLiveDataSize` does not count partition keys, which hold the value in the index table; use pool-accounted `owns()`), B3i.4 adds real files and log lines. |
| A. Core question | usage driven to the limit and past it | Met | S = 65534 / 65535 / 65536 at unit; N x S = 262 MB (unit) and 1.05 GB (cluster) is above a 64 MiB / 256 MiB / 512 MiB pool. |
| A. Core question | positive control for a negative estimate | Partly -> Met | B2h/B3h named a pool cap "not verified in source"; B2i.5 and B3i.5 make it exact; `AbstractAllocatorMemtable.java:59-84` shows the pool limit comes from `memtable_heap_space`/`memtable_offheap_space`. |
| B. Logic | each step says what it establishes | Met | B2e, B3e. |
| B. Logic | prediction stated in numbers or a clear relation | Partly -> Met | "about linearly", "near 4" given bounds (B2i.4, B3i.5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | Rows exist for confirmed, boundary wrong, plateau, control did not move; no row for a mixed result; the generic rule "Not confirmed (no matching row)" applies. Left for stage 3. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2g/B3g row 1 + the rejection text at 65535. |
| B. Logic | alternative explanations and their controls | Met | no-index control, small-value control, pool control (B2h/B3h, B2i.2, B2i.5). |
| C. Specific | a human can follow it from the intro and B1 | Met | A1-A3, B1. |
| C. Specific | an AI can run B2/B3 without re-deriving the code path | Partly -> Met | launcher, yaml, paths, instruments, drivers were open or wrong (`/users/.../cassandra-5.0.9`, `-Dtest.jvm.args` unverified, `/local` absent): B2i.1-3, B3i.1-2. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly -> Met | B2i.6-7, B3i.3-5. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | build copy, bundled Python driver, `nodetool`, `jcmd`; the test class, node script, analyser are step-1 work. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 4000 x 65534 = 262 MB per table, two tables on a 4 GB heap (unit); 16000 x 65534 = 1.05 GB per table on tmpfs (cluster), above the 512 MiB and 256 MiB pools. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | see above; the "partition key blob" second table cannot show the boundary (single-column PK cannot be indexed; composite key is rejected earlier): replaced by a clustering column, B2i.2. |
| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Launcher, yaml and local paths (B2i.1, B3i.1) | Applied, 2026-10-28 | `/users/.../cassandra-5.0.9`, `/local`, `-Dtest.jvm.args` do not exist or are unverified |
| 2 | Replace the partition-key second table by a clustering column (B2i.2) | Applied | PK index cannot reach 65535 |
| 3 | Pool-accounted memtable instrument (B2i.3) | Applied | `getLiveDataSize` does not count the partition keys that hold the indexed value |
| 4 | Numbers for "about linearly", "near 4", the pool control (B2i.4-5, B3i.5) | Applied | prediction needs bounds |
| 5 | Arms, drivers, observables for the cluster tier (B3i) | Applied | fresh table per N, log lines, tmpfs |
| 6 | Add a conclusions row for mixed results | Left for stage 3 | the no-matching-row rule covers it |
**Agreement criteria** - not applicable (run 2 not planned).

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-28 (unit 12:29 to 12:31 MDT; cluster 12:31 to 12:37 MDT) | not done |
| Node (CloudLab name and type) | `pc32` (`node2.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB); other stage-4 agents ran on other nodes | not done |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-198-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | Apache Ant 1.10.12; `ant build-test` once (1 min 7 s) | |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-b2/c` by `copy-source.sh`, repository commit `b68711e5` (tag `cassandra-5.0.9`, local baseline); one tree for both tiers, one run at a time | |
| Case-file commit / harness commit | the case file is not committed (sha256 in section 1); harness uncommitted | |
| Storage for node data | unit: local disk `~/s4-b2-store/run1-a-*` (removed after each JVM); cluster: tmpfs `/dev/shm/s4-b2/node/{data,commitlog,hints,saved_caches,logs}` (removed at the end), so disk bytes are tmpfs bytes | |
| Full logs (path, outside the repo) | on `pc32`: `~/s4-b2-logs/run1-a/{unit,cluster}/` (`summary.txt`, `*.out`, `*.junit.log`, `session.log`, `system.log.life{1,2}`, `samples-*.csv`, `arms.jsonl`); shakedowns `~/s4-b2-logs/shake1/` (unit quick: N = 100, 1000; cluster quick: 300 and 50 inserts). Unit: JUnitCore, `-Xmx4g`, test yaml (`heap_buffers`, 5 MiB commit log segments), `memtable_heap_space` 2048 MiB (bounds, scale_default) or 64 MiB (scale_pool64). Node: JDK 11, `MAX_HEAP_SIZE=2G`, one node 127.0.2.1, `offheap_objects`, `memtable_cleanup_threshold: 0.99`, `auto_snapshot: false`, `commitlog_total_space: 1GiB`, `memtable_offheap_space` 512 MiB (life 1) and 256 MiB (life 2) | |

## 3. Runbook defects

The audit fixed what it found before run 1 (B2i, B3i); those are listed for stage 3. Run 1 found no step that could not run as written.

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | audit | B2d / B2b | `getLiveDataSize()` does not count partition keys, which hold the indexed value in the index table; the second table "index on the partition key" cannot show the boundary (a single-column PK cannot be indexed; a composite key is rejected by the key-length check first: `Key length of 65539 ...` in `unit/bounds.out`) | pool-accounted `owns()`; clustering column path (B2i.2, B2i.3) | 2026-10-28 | untracked file (sha256 in section 1) |
| 2 | audit | B2a / B3a | paths `/users/jason92/cassandra-5.0.9`, `/local`, `-Dtest.jvm.args` unverified | B2i.1, B3i.1 | 2026-10-28 | same |
| 3 | audit | B2h / B3h | "positive control" named a pool cap "not verified in source" and gave no numbers | B2i.5, B3i.5 | 2026-10-28 | same |
| 4 | self-check | harness (`selfcheck.py`) | one check compared the Data.db bytes of the `s100` arm in `arms.jsonl` (after background compactions) to the sum of the node's "Completed flushing" sizes (all flushes); the two are different quantities when compactions run between flush and measurement | compared to the node's own `Space used (live)` instead (1.0 percent apart); the first output is kept as `run1/selfcheck-first.out`; 33 parts hold | 2026-10-28 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier (bounds; scale at 2048 MiB with N = 100 / 1000 / 4000 indexed and unindexed; control at 64 MiB with N = 4000 indexed and unindexed) and cluster tier (precheck; n1000 / n4000 / n16000 at 512 MiB; s65535; no-index; small-value; n16000 at 256 MiB). **Command logs:** `max_unsigned_short-validateindexedvalue-value_remaining--autonomous/run1/unit/summary.txt`, `run1/cluster/summary.txt`, `run1/cluster/session.log.head` (first 6 KB; the full logs are on the node). The harness was checked by a unit shakedown (N = 100, 1000) and a cluster shakedown (300 inserts, 50 rejected) before run 1; they showed the same kind of numbers (ratio 2.0 of index disk bytes to N x S), so run 1's numbers are not independent of what the author had seen; the thresholds of B2i and B3i were frozen first.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`: 3 JVMs, JUnit OK each, all EXPECTED lines yes)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Regular text column with index: S = 1000, 65533, 65534 | accepted | `unit/bounds.out` |
| Same, S = 65535 and 65536 | rejected, "Cannot index value of size S for index table_probe_00_v_idx on cql_test_keyspace.table_probe_00(v) (maximum allowed size=65535)" | `unit/bounds.out` |
| Same column without the index, S = 65534, 65535, 65536 | accepted (so the rejection comes from line 618) | `unit/bounds.out` |
| Clustering blob column with index: 65534 accepted; 65535 rejected with the same index message; 65536 rejected with "Key length of 65536 is longer than maximum of 65535" (clustering validator, not the index); without the index 65535 accepted | as stated | `unit/bounds.out` |
| Composite partition key, index on `k`: 65500 accepted; 65535 rejected "Key length of 65539 ..." (key check, information) | as stated | `unit/bounds.out` |
| Scale at 2048 MiB, S = 65534, index backing-table disk bytes after flush: N = 100 / 1000 / 4000 | 13,345,606 / 132,100,354 / 528,128,039 B = 2.04 / 2.02 / 2.01 x N x S; ratios 9.90 (1000/100) and 4.00 (4000/1000); no rejected insert | `unit/scale_default.out` |
| Peak index memtable `owns()` at N = 4000 (2048 MiB) | 477,700,740 B (N x S = 262,136,000); peak pool on-heap 790,577,112 B (754.0 MiB); no sstable before the explicit flush | `unit/scale_default.out` |
| Unindexed table, N = 4000: base disk bytes | 263,636,597 B against 263,642,129 B for the indexed table's base | `unit/scale_default.out` |
| Control, `memtable_heap_space` 64 MiB, N = 4000 indexed | peak pool on-heap 67,254,088 B (64.1 MiB); 7 index-table sstables and 4 base sstables before the explicit flush; index disk bytes 528,928,097 B (2.02 x N x S); no rejection | `unit/scale_pool64.out` |

**Cluster tier** (`run1/cluster/arms.jsonl`, `summary.txt`: 21 EXPECTED lines, all yes). "idx" = `*-Data.db` plus `*-Index.db` of the hidden index directory `.idx_<table>` after `nodetool flush`; "live" = `nodetool tablestats` "Space used (live)" of the index table after the flush.

| Arm (pool) | Inserts accepted / rejected | idx bytes (glob) | idx live | per N x S | MEMTABLE_LIMIT flushes; first logged usage (on-heap, off-heap) | Evidence (file) |
|---|---|---|---|---|---|---|
| precheck, S = 65534 (5) / 65535 (5) (512 MiB) | 5 / 0 and 0 / 5, "Cannot index value of size 65535 for index idx_t_pre on ks.t_pre(v) (maximum allowed size=65535)" | n/a | n/a | n/a | none | `cluster/summary.txt` |
| n1000 (512 MiB) | 1000 / 0 | 131,403,847 | 132,100,360 | 2.01 | 0 | `cluster/arms.jsonl` |
| n4000 | 4000 / 0 | 525,615,554 | 527,992,435 | 2.01 | 0 | same |
| n16000 | 16000 / 0 | 2,195,224,212 | 2,111,836,643 | 2.09 (glob), 2.01 (live) | 3: 256.656 MiB / 507.170 MiB, then 507.670 and 508.046 off-heap | same, `cluster/flush-lines.life1.txt` |
| s65535, N = 200 | 0 / 200, all with the index message | 0 | 0 | n/a | 0; memtable empty; base and index dirs 0 B | same |
| noidx4000 | 4000 / 0 | n/a (base 263,487,957 B = 1.005 x N x S) | n/a | n/a | 0 | same |
| s100, N = 655,340 (S = 100) | 655,340 / 0 | 139,586,680 | 141,042,736 | 2.13 (2.15 live) | 1: 506.893 MiB on-heap (99 percent), 136.641 MiB off-heap | same |
| p256_n16000 (256 MiB, life 2) | 16000 / 0 | 3,034,828,752 (compactions in flight, see 4.2 part 6) | 2,112,515,199 | 2.01 (live) | 7: 129.405 MiB / 255.961 MiB first, off-heap 253.6 to 256.0 | same, `cluster/flush-lines.life2.txt` |

Other cluster readings: the first logged `MEMTABLE_LIMIT` off-heap usage was 507.170 MiB at the 512 MiB pool and 255.961 MiB at the 256 MiB pool (ratio 1.98); `nodetool tablestats` "Memtable data size" of the base table was 262,332,000 B at n4000 (the values), while the index table's was 132,000 B (the keys are not counted) and its "Memtable off heap memory used" 262,196,000 B; no `ERROR` line in either `system.log`.

### 4.2 Conclusion and logic

1. **Validity.** The boundary was driven across at both tiers (65534 / 65535 / 65536) [observed: `unit/bounds.out`, `cluster/summary.txt`]. The pool cap was reached: 64.1 MiB of a 64 MiB pool at the unit tier, 508.0 MiB of 512 MiB and 256.0 MiB of 256 MiB off-heap at the cluster tier, with the workload (262 MB unit, 1.05 GB per table cluster) larger than the pool [observed: `unit/scale_pool64.out`, `cluster/flush-lines.life{1,2}.txt`]. Fixed settings held: same yaml in every arm of a life; fresh table per arm; `auto_snapshot: false`; random distinct values [observed: `cluster/summary.txt` (yaml tail), harness]. The control moved (part 3). Valid.
2. **Readings.** (a) The index backing table costs about 2.0 x N x S on disk: the value is the partition key, stored in Data.db and again in Index.db [observed: `cluster/arms.jsonl`: idx_data 263,451,588 and idx_index 262,163,966 at N = 4000]. (b) Index memtable `owns()` is 1.82 x N x S at N = 4000 in the unit tier (477.7 MB for 262.1 MB), [observed: `unit/scale_default.out`]; why it is above 1.0 x (the key is probably held more than once on the heap) was not examined [inferred]. (c) The `s100` arm's pool usage reached 99 percent on-heap (many small rows), not off-heap [observed: `flush-lines.life1.txt`]. (d) The glob reading of the index directory overcounts when compactions are in flight (p256_n16000: 3.03e9 against 2.11e9 live): see part 6.
3. **Matched row.** Unit B2g row 1, "Index size grows with N, no rejection at S=65534 -> Claim confirmed: not an aggregate cap": 65534 accepted and 65535 / 65536 rejected with the predicted message [observed: `unit/bounds.out`]; index disk bytes grow 13.3 MB, 132.1 MB, 528.1 MB for N = 100, 1000, 4000 (ratios 9.90 and 4.00, inside [8, 12] and [3.5, 4.5]) with no rejection, 2.0 x N x S each, and 528 MB (about 8,000 times the single-value limit) were accepted [observed: `unit/scale_default.out`]. The control row of B2h holds as well: with a 64 MiB pool the peak pool usage was 64.1 MiB against 754.0 MiB at 2048 MiB (ratio 11.8), 7 index sstables were flushed before the explicit flush, yet the index still held 528,928,097 B (2.02 x N x S, 0.15 percent from the 2048 MiB arm): the pool bounds memory in flight, nothing bounds the bytes written [observed: `unit/scale_pool64.out`]. Cluster B3g row 1, "Index table space grows with N, writes succeed at 65534 -> Claim confirmed (negative)": live index space 132.1 MB, 528.0 MB, 2,111.8 MB at N = 1000, 4000, 16000 (ratios 4.00 and 4.00), 16000 of 16000 inserts accepted, 200 of 200 inserts at 65535 rejected with the index message and 0 B reached the table or index directory [observed: `cluster/arms.jsonl`]. The binding-cap control (B3g rows 3 and 4) holds: the first logged `MEMTABLE_LIMIT` off-heap usage followed the pool (507.2 MiB at 512 MiB, 256.0 MiB at 256 MiB; 3 against 7 flushes) while the index's live space was 2,111,836,643 B and 2,112,515,199 B (0.03 percent apart) [observed: `cluster/flush-lines.life{1,2}.txt`, `cluster/arms.jsonl`].
4. **Excluded rows.** Unit "Rejection at S=65534 or acceptance at 65535": the opposite [observed]. "Index size plateaus below N x S while writes succeed": the 64 MiB arm plateaued the pool (64.1 MiB) but the index bytes did not (2.02 x N x S) [observed]. "Control table does not move, or N too small to flush": the control moved (peak pool 64.1 MiB against 754.0 MiB; 7 index sstables flushed early) [observed]. Cluster "65534 rejected or 65535 accepted": precheck 5 / 5 the right way [observed]. "Index space saturates while writes succeed": ratios 4.00 and 4.00 across a 16-fold range of N [observed]. "Control memtable does not move or load too small": 3 and 7 pool-triggered flushes [observed].
5. **Observed vs. inferred.** [inferred: "does not cap" rests on usage being linear in N x S with S fixed at the boundary and the pool, not the constant, setting the plateau; the constant itself cannot be varied, so the dose-response is over N and over the pool.] [inferred: tmpfs bytes stand for disk bytes.] [inferred: unit `owns()` on-heap stands for the memtable's heap use; it is the pool's own accounting, `AbstractAllocatorMemtable.java:190`.] [inferred: a single-value cap that is not an aggregate does not cap usage in the paths not run: index build, streaming, hints, sstable import (A3 "Bypasses").]
6. **Deviations and gaps.** (a) Shakedowns showed the same kind of numbers before run 1. (b) The B3h control lowered `memtable_offheap_space` only, as written; the heap pool was left at its default. (c) The directory-glob reading counts files of compactions in flight: n16000 is 4 percent above `Space used (live)` and p256_n16000 44 percent above (the node log shows `Compacting` and `Compaction interrupted` lines for that table, interrupted by the DROP TABLE); the frozen ratio checks were met on the glob (4.18 and 4.00) and on the live figure (4.00 and 4.00) alike, and p256's index bytes were not an EXPECTED line. (d) The read-side check (`>` at line 225) and the non-client paths were not run. (e) One `selfcheck.py` check was wrong and was replaced (section 3, row 4). (f) The optional second build was not applicable (the constant is not varied). (g) `getLiveDataSize` / `Memtable data size` do not include partition keys, so they under-report this index by 2000 times (132,000 B for 4000 keys of 65534 B); anyone sizing from that line would miss it.
7. **Core question.** Usage follows the number of rows and their bytes, not the constant: index disk and memtable bytes grew linearly with N at S = 65534 (4.00 per 4-fold N, unit and cluster), with 528 MB (unit) and 2.1 GB (cluster) of index keys accepted through a check that only compares one value to 65535 (part 3). The disallow branch fires exactly at 65535, writes nothing, and is the only effect of the constant (part 3). The ceiling a node reaches is set by the memtable pool, which moved with its own setting (64 versus 2048 MiB, 512 versus 256 MiB) while the bytes written did not (part 3, with the known-binding control).

**Conclusion (one line):** unit B2g row 1 and cluster B3g row 1 (with the control rows) - confirmed (the claim: usage does not follow `MAX_UNSIGNED_SHORT`).

## 5. Self-check of run 1 - AI

### 5.1 Check of run 1's conclusion

`harness/max_unsigned_short-validateindexedvalue-value_remaining--autonomous/selfcheck.py` re-parses the raw files (`unit/*.out`; `arms.jsonl`; the node's `system.log.life{1,2}` for `MEMTABLE_LIMIT` usage and "Completed flushing" sizes; `summary.txt`) with its own code; output `run1/selfcheck.out`: 33 parts hold, 0 do not hold (after replacing one wrong check, section 3 row 4; the first output with that one failure is `run1/selfcheck-first.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: precheck 5 / 5 and boundary lines; pool peaks 64.1 MiB, 508.0 MiB, 256.0 MiB from the node log; no `ERROR`; no daemon of the run left and `/dev/shm/s4-b2` gone. |
| 2. Readings | yes | The 2.0 x N x S cost is the Data.db plus Index.db sizes; the node's "Completed flushing" Data.db sizes agree within 5 percent for n1000, n4000, n16000. The glob / live gap is explained by compaction lines in the node log (p256). |
| 3. Matched row | yes | Ratios recomputed from `unit/scale_*.out` (9.90, 4.00) and from the node's live figures (4.00, 4.00); the control (64.1 MiB, 7 sstables; live space 0.03 percent apart across pools) recomputed. |
| 4. Excluded rows | yes | Same files. |
| 5. Observed vs. inferred | yes | The inferences are named in 4.2 part 5; the raw files hold nothing stronger (the constant cannot be varied). |
| 6. Deviations and gaps | yes | Listed in 4.2 part 6. |
| 7. Core question - the steps from reading to answer follow the audited logic | yes | Per-value gate (bounds) and aggregate growth plus pool plateau with control follow B1, B2h, B3h. |

### 5.2 Run 2?

**No** (2026-10-28). The conclusion rests on exact boundary behaviour and on numbers that the node's own logs reproduce (live space, flush usage); the one inference (the plateau is the pool and not the constant) is what the control, which moved by the predicted factor, settles. A run 2 would repeat a six minute cluster run and add nothing the logs do not hold.

## 6. Run 2 - fresh AI session (optional)

Not done.

## 7. Comparison - only if run 2 was done

Not applicable.

## 8. Verdict - AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (negative, does not cap): the constant bounds one indexed value; the memory and disk a node uses for a secondary index follow the rows and bytes written and the memtable pool.

**Claim tested (B1):** indexed-value validation caps only the size of a single value; the memory and disk used by the secondary index keep growing with the number of rows whose values are just under 65534 bytes, so usage does not follow `MAX_UNSIGNED_SHORT`. Sub-claim: values of 65534 bytes are accepted and 65535 bytes are rejected. "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 1; B2h control) | does not cap | run 1 + self-check | 2026-10-28 |
| Cluster | **Confirmed** (B3g row 1; B3h control) | does not cap | run 1 + self-check | 2026-10-28 |

**Positive control:** a known-binding cap moved: at the unit tier `memtable_heap_space` 64 MiB held the pool at 64.1 MiB (7 early index flushes) against 754.0 MiB at 2048 MiB, with the same 528 MB of index bytes written; at the cluster tier `memtable_offheap_space` 256 MiB instead of 512 MiB moved the first logged off-heap flush usage from 507.2 to 256.0 MiB (3 against 7 flushes) with the same 2.11 GB of index live space.

**Side findings (do not change the verdict):** (1) The index table stores each indexed value twice on disk (Data.db and Index.db), so an indexed value of S bytes costs about 2 x S in the index plus S in the base table. (2) `Memtable data size` / `getLiveDataSize()` of the index table excludes the partition keys that hold the value (132,000 B for 4000 x 65534 B), so tools that report it under-count secondary-index memory. (3) A composite partition key cannot reach the index check at 65535 bytes; the key-length check rejects first ("Key length of 65539 ..."). (4) The `Cannot index value` read-side twin uses `>` (line 225), not run.

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (untracked file; sha256 below); the audit amendments B2i and B3i are listed in section 1. Sha256 of the case file with D filled: `4f374363298781f37365b2159b034ce00771cd78633aff6e73720221b7ac530a`.
