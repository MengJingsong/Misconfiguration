# mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous — stage-4 results  <!-- file: results/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md -->

> **Case:** [`mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous`](../../stage3-ai-deep-read/cases/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous.md)
>
> **Status:** **Self-checked 2026-10-27 — unit Confirmed (caps), cluster Confirmed (caps) for the heap held per Mutation; three filed process-level heap sub-predictions of the cluster tier missed (a transient of about 0.5 GB on the receive/apply side that does not depend on N, and the sampler's cadence); a second cap on the same Mutation (`max_mutation_size`) turned the unthrottled and the 100000-row arms into failures; no run 2**
>
> **Outcome class:** true positive — stage-3 estimate `positive` against the stage-4 effect `caps` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (dated 2026-10-27): **unit tier** frozen at `cd21e2ee665526bb1419ade2806bd517c14139837358deca3a58ac40103facbf` (U1-U5, C1-C7) before attempt 1; after the runbook defect U6 (the dated fix, text only) `443ee733f606f31e451affa5e90ab591c3fdd5e5207e32db2f025580ec22147f`, the text on which the unit tier was run again; **cluster tier** frozen at `3eec471acc6472eab1a6af31c428b36bbd09ecfc717f7e546620063fd98f23e1` (adds C8 and the clarified per-row-heap sentence of C5) before the data was loaded and before any cluster reading. Repository HEAD of this session `6e6cf92`; case file, harness and results are uncommitted in the working tree. The frozen text is everything above section D. |
| **Harness** | [`harness/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous/`](../harness/mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous/README.md), uncommitted: `MutationRepairBatchProbeTest.java`, `unit-run.sh` (B2); `make-node.sh`, `node.sh`, `prep-data.sh`, `LoadWide.java`, `bm.btm`, `cluster-run.sh`, `chain.sh`, `analyze.py`, `selfcheck.py` (B3). **Instrument checks (not readings):** the upstream `ThrottledUnfilteredIteratorTest` in the run copy (7 run, 0 failures); a shakedown of the unit probe on 3000 and 600 rows (known answer: batch sizes equal N, N+1 in the tombstone variant; the retained heap matched `unsharedHeapSize` there); `TestScript` of `bm.btm` ("Type checked rule", no errors); a shakedown of the whole cluster path on 200,000 rows (`prep-data.sh` and one `cluster-run.sh` arm, N unset): its output was **seen before the cluster freeze and is not a reading**; it found three runbook defects (C8) and printed 2000 updates of 100 rows with 416.6 B of heap per row. |
| **Tiers and values** | Unit (B2): N in {0, 2, 100, 1000, 10000} on 100000 rows of 100-byte values, N in {0, 100, 1000} on 10-byte and on 1000-byte values, and the tombstone variant (20000 rows under one range tombstone) with N in {2, 100, 1000}. Cluster (B3): two nodes on loopback (A sender 127.0.0.2, B receiver 127.0.0.3, B at 2 GB heap), one partition of 2,000,000 rows of 200 bytes per table (428 MB per table), receiver property unset (default 100), 1000, 10000, 100000 and 0 on the CDC table `wide_cdc`, and 0 on the plain table `wide_plain` (negative control). Both tiers kept. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap held by one Mutation; the cap is a row count and A3 names the bytes as rows x row size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 0, 2, 100, 1000 (the property is static final, so the argument is the knob in the unit tier); B3b: 0, 100, 10000, each on a fresh node start. Added 1000 and 100000 (C3). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d had no peak heap ("not measured here"), B3d had `jstat`/histogram at the midpoint only. Added the retained heap of the largest update (U3) and, in the cluster, the per-update heap of every update built (Byteman, C4). |
| A. Core question | usage driven to the limit and past it | Met | B2c: 100000 rows against N = 2..10000; B3c: 2,000,000 rows (a 832 MB update at N = 0). |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f numbers were present for batch counts but not for heap; B3f gave "~20 KB for 100, ~2 MB for 10000" and "can OOM". Numbers added before the runs (U4, C5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | no row for a failed apply (C2/C6) nor for the retained-heap proxy gap (U5). Added. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | the disallow branch is `ThrottledUnfilteredIterator.throttle` returning the raw iterator (opt-out) vs wrapped (batches): the unit tier reads `sameObjectAsScanner`, the cluster tier reads `S4THROTTLE maxBatchSize` and one update per partition. |
| B. Logic | alternative explanations and their controls | Partly | B3h's plain-table control is kept (arm `p0`); added the memtable-heap confound as a named limit of the process-level heap readings (C4/C5). |
| C. Specific | a human can follow it from the intro and B1/B2g/B3g | Met | A1-A4, B1. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | B3c/B3e did not say how the 2,000,000-row partition is loaded, how two nodes run on one host, how node 2 gets the schema without bootstrapping, or how the receiver's property is set per start; supplied (C1, C3). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "jstat" replaced by the GC log and a histogram sampler; "per-Mutation size (use histogram instead)" replaced by the Byteman line per update (C4). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | written in step 1 (this session). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | **a second cap not foreseen by the file:** with a CDC table the Mutation goes through the commit log, and `max_mutation_size` (16 MiB at the default 32 MiB segment) rejects the 21 MB (N = 100000) and 426 MB (N = 0) Mutations after they have been materialised (C2). Disk: 428 MB per table per node plus about 410 MB of `cdc_raw` per arm, local `/`, 51 GB free; B at 2 GB heap holds the 832 MB update at N = 0. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra/cassandra-5.0.9`: `ThrottledUnfilteredIterator.java:61-68` (assert), `:146-149`, `:232-235`, `:251`; `CassandraStreamReceiver.java:63`, `:195-200` (`requiresWritePath`), `:202-228` (`sendThroughWritePath`: the filed `:218` is `:221`), `:236-245` (`finished()`); `CassandraRelevantProperties.java:410`; `CassandraOutgoingFile.java:181-196`. All as cited except that line number. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Retained heap of the largest update and counter of Unfilteds per batch (U3) | Applied 2026-10-27 | the filed unit tier recorded no heap |
| R2 | Numeric predictions for batch counts, N+1 and heap ratios (U4) | Applied | decidable |
| R3 | State how the data is loaded and the two nodes run (C1, C3) | Applied | not runnable as filed |
| R4 | The commit log caps the same Mutation (C2); arms 1000 and 100000 | Applied | N = 0 cannot "OOM" before it is rejected |
| R5 | Byteman per update and `S4THROTTLE` as the knob read-back (C4) | Applied | exact per-Mutation heap |
| R6 | For stage 3: the N = 0 opt-out on a CDC table is limited by `max_mutation_size` on the commit-log write; a wide-partition repair fails there rather than running out of heap | left for stage 3 | observed in the cluster tier |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (node clock UTC 2026-10-28 02:58-03:52; unit 03:05-03:20, cluster 03:36-03:52) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/c4-mrb` from `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92` (`copy-source.sh`, local tag `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL (about 1 min) |
| Case-file / harness commit | uncommitted (working tree of `6e6cf92`); case-file sha256 in section 1; harness md5s in `run1/unit/harness-unit.md5` (unit attempt 1) and `run1/cluster/harness-cluster.md5` |
| Storage for node data | `~/stage4-mrb/{A,B,A-backup}` on local `/dev/sda3` (63 GB, about 51 GB free), removed after each arm (the backup removed at the end); nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/mrb/run1/{unit,unit-attempt1-heldref-defect,cluster,prep}/` (per arm: `stdout-B.txt` with every `S4BATCH` line, `gc-B.log`, `system-B.log`, `repair.txt`, `samples.txt`); discarded shakedowns in `~/stage4-logs/mrb/{shake,shake-c}` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | unit attempt 1 | B2d (retained heap of the largest update) | the reference to the largest update was not used after the measurement; the JIT treated it as dead, so `retainedHeapOfLargestUpdate` was 3.5 MB for an update of 32 MB and negative elsewhere (`run1/unit-attempt1/unit.out`) | `held.rowCount()` is read after the measurement (column `heldRows`); case-file U6 (dated); the unit tier restarted from its beginning; the other columns of attempt 1 equal those of attempt 2 | 2026-10-27, claim, prediction and rows unchanged |
| D2 | cluster shakedown | B3 workload data, `cp -a <backup> <A>/data` | copied into an existing directory (nested copy), so node A started without the keyspace | copy `<backup>/.` | before the cluster freeze (C8b) |
| D3 | cluster shakedown | B3d (Byteman output) | in daemon mode `CassandraDaemon` closes `System.out` after start-up: 0 `S4BATCH` lines for a repair that had written 41 MB of CDC segments | nodes run with `bin/cassandra -f` (backgrounded by `node.sh`, which writes the pid file) | before the cluster freeze (C8a) |
| D4 | cluster shakedown | `LoadWide` build | Guava not on the class path; `Futures.addCallback` unusable with the shaded driver | `addListener`, Guava from `build/lib/jars` | before the cluster freeze (C8c) |
| D5 | cluster | B3d "row count on B" (`SELECT count(*)` of the 2,000,000-row partition) | `ReadTimeout` in every completed arm | not fixed; B's content is read from the `S4BATCH` row total (2,000,000) and from `tablestats` (`Space used (live)` 427.8 MB = A's table), both in `analysis.txt` | recorded; no effect on the verdict |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `mutation_repair_rows_per_batch-throttledunfilterediterator-maxbatchsize--autonomous/run1/` (`unit/unit.out`, `unit/ant-summary.txt`, `cluster/<arm>/{analysis.txt,cmdlog.txt,...}`, `cluster/chain.out`, `selfcheck.txt`). Abbreviations: update = the `PartitionUpdate` built by `PartitionUpdate.fromIterator` (what the receiver wraps in a Mutation); heap = `unsharedHeapSize()`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit.out`; 100000 rows, one partition, one sstable)

| Test or assertion | Result | Evidence |
|---|---|---|
| N = 0, values 10 / 100 / 1000 B | `sameObjectAsScanner=true`; 1 batch of 100000 Unfilteds and rows; heap 23,200,064 / 32,000,064 / 121,600,064 B; retained heap of that update 24.0 / 36.1 / 128.0 MB (ratios 1.03 / 1.13 / 1.05) | `RESULT variant=b10/b100/b1000 N=0` |
| N = 2 (100-B values) | 50000 batches, every batch exactly 2 Unfilteds; heap 704 B | `variant=b100 N=2` |
| N = 100 (10 / 100 / 1000 B) | 1000 batches of exactly 100; heap 23,264 / 32,064 / 121,664 B | `variant=b10/b100/b1000 N=100` |
| N = 1000 (10 / 100 / 1000 B) | 100 batches of exactly 1000; heap 232,064 / 320,064 / 1,216,064 B; retained/unshared 1.02 / 1.01 / 1.00 | same |
| N = 10000 (100 B) | 10 batches of exactly 10000; heap 3,200,064 B; retained/unshared 1.01 | `variant=b100 N=10000` |
| ratios (100-B values) | heap(1000)/heap(100) = 9.98; heap(10000)/heap(1000) = 10.00; heap(0)/heap(100) = 998; per row 320 B; per-row difference 1000-B minus 10-B values 984 B | computed from the lines above (`selfcheck.txt`) |
| tombstone variant (20000 rows under a range tombstone) | N = 2: 20000 batches of 3 Unfilteds (one row each); N = 100: 203 batches, largest 101, smallest 4; N = 1000: 21 batches, largest 1001 | `variant=tomb` |
| upstream `ThrottledUnfilteredIteratorTest` (known-answer) | 7 run, 0 failures | `upstream-ThrottledUnfilteredIteratorTest.summary` |

**Cluster tier** (`run1/cluster/<arm>/analysis.txt`). Node A holds the table (2,000,000 rows, 427.8 MB); node B starts empty; `nodetool repair -full ks <table>` on B.

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| unset (default 100) | `u100`, `wide_cdc` | `S4THROTTLE` value; updates; rows per update | `maxBatchSize=100`; 20000 updates, every one of 100 rows (total 2,000,000); heap 41,664 B each (416.6 B per row) | `s4throttle.txt`, `analysis.txt` |
| | | repair; B afterwards | completed in 29 s; 4 sstables, 427.8 MB (= A) | `repair-tail.txt`, `tablestats-B-after.txt` |
| | | live bytes (sampler, 4 s); G1 max after a pause | 516 MB; 678 MiB | `analysis.txt` |
| 1000 | `n1000` | updates; heap | `maxBatchSize=1000`; 2000 updates of 1000 rows; heap 416,064 B each; repair completed; sampler max 596 MB; G1 673 MiB | same |
| 10000 | `n10000` | updates; heap | `maxBatchSize=10000`; 200 updates of 10000 rows; heap 4,160,064 B each; repair completed; sampler 576 MB; G1 677 MiB | same |
| 100000 | `n100000` | updates; repair | `maxBatchSize=100000`; **1** update of 100000 rows, heap 41,600,064 B, then `MutationExceededMaxSizeException: Rejected an oversized mutation (21199999/16777216)`; stream failed, repair failed; B has no sstable; sampler 65 MB; G1 62 MiB | `analysis.txt`, `system-B-excerpt.txt`, `tablestats-B-after.txt` |
| 0 (opt-out) | `n0` | updates; repair | `maxBatchSize=0`; **1** update of 2,000,000 rows, heap 832,000,064 B (dataSize 490,000,029), then `MutationExceededMaxSizeException (425891207/16777216)`; repair failed; no OOM; sampler 92 MB; **G1 884 MiB** | same |
| 0 on a plain table | `p0`, `wide_plain` | `S4THROTTLE`, `S4BATCH` lines; repair | none, none; repair completed in 22 s; B 427.8 MB; sampler 65 MB; G1 67 MiB | `s4batch-count.txt` (0), `analysis.txt` |
| all arms | | JVM | B started with `-Xmx2G`, the Byteman agent, the GC log; A without the property (`proc-args-B.txt`) | `proc-args-B.txt`, `jvm-extra-B.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The run is valid. The write path was taken on the CDC table in all five arms [observed: `S4BATCH` lines in `u100`, `n1000`, `n10000`, `n100000`, `n0`] and not on the plain table [observed: 0 lines in `p0`]; the knob reached the check [observed: `S4THROTTLE maxBatchSize` = 100, 1000, 10000, 100000, 0 in the five arms, one call each]; the data was passed past the cap [observed: 2,000,000 rows in the partition against N of 100 to 100000]; B at 2 GB and G1 [observed: `proc-args-B.txt`, `gc-B.log`]; node A without the property [observed: `proc-args-B.txt` of A in `cmdlog.txt`: "A has the property (lines): 0"]; no leftover daemon [observed: `daemons left: 0` in each `cmdlog.txt`, and `ps` after the chain: 0].
2. **Readings.** (a) At N = 0 and N = 100000 the repair did not complete: the Mutation exceeded `max_mutation_size` (16 MiB) at the commit-log write after the update had been built [observed: `system-B-excerpt.txt`]. That is a second cap on the same object, not a failure of the throttle. (b) The filed process-level heap readings did not separate the arms the way the case predicted: the live bytes of the 4-second histogram sampler are 516-596 MB for the three completed arms (which also hold the received memtable data on the heap: 2,000,000 rows) and only 92 MB for N = 0, whose 832 MB update lived for a few seconds between two samples [observed: `analysis.txt`]; the G1 maximum after a pause is 678 / 673 / 677 MiB for the three completed arms, 884 MiB for N = 0, 62 MiB for N = 100000 and 67 MiB for the plain table [observed]. The sampler's maxima of the three completed arms are single transient samples (`u100`: 516 MB at one sample, 331 MB at the next, 145 MB at rest; `BufferCell` and `BTreeRow` 57.5 MB each at the peak sample, the remaining 340 MB in classes the sampler did not record) [observed: `u100/samples.txt`]. [inferred: receive/apply-side buffers and the memtable's on-heap objects of the 2,000,000 rows being applied and flushed (4 flushes); not attributed further, since the full histogram of the peak sample was not kept]. The updates of 41 KB to 4 MB at N = 100..10000 are far below that transient, so the process-level heap does not separate them; the 832 MB update at N = 0 exceeds it only in the G1 log. (c) `count(*)` on B timed out; the content of B is shown by the update row totals and `tablestats` instead (D5).
3. **Matched row.** Unit B2g row 1 "max rows per batch <= N+1 for N>1, and 1 batch with all rows for N=0 -> claim confirmed": N = 2, 100, 1000, 10000 give batches of exactly N Unfilteds (N + 1 = 3, 101, 1001 in the tombstone variant) and N = 0 returns the scanner itself with one batch of 100000 rows [observed: `unit.out`]. Cluster B3g row 1 "peak live heap(N=0) >> peak(N=100), and rising with N -> claim confirmed", read on the quantity the claim is about, the heap of the Mutation built by the streaming write path: 41.7 KB (100) < 416 KB (1000) < 4.16 MB (10000) < 41.6 MB (100000) < 832 MB (0, one Mutation of the whole partition), exactly 416 B per row in all arms [observed: `s4batch-first-last.txt`, `analysis.txt`], and the G1 maximum of the process rises from 67 MiB (no write path) to 884 MiB at N = 0 [observed]. The rows "N=0 OOM, N=100 completes" did not occur (no OOM at 2 GB), "peak heap equal across N" did not occur.
4. **Excluded rows.** B2g "a batch with more than N+1 Unfilteds for N>1": none, the maximum is N (N + 1 only with the open tombstone) [observed]; "N=0 still produces several batches": no, one [observed]; "heap per batch not growing with N": it grows linearly (9.98x per decade) [observed]; B3g "peak heap equal across N": the Byteman heaps differ by orders of magnitude [observed]; "repair did not stream or did not use the write path": it did in five arms [observed]; the plain-table control builds no update [observed].
5. **Observed vs. inferred.** Inferred: (i) that the transient process-level heap of the completed arms (about 0.5 GB) comes from the receive/apply side and the memtable and not from the updates (it is the same for N = 100, 1000 and 10000 within 80 MB, while the updates differ 100-fold); (ii) that the sampler missed the N = 0 peak because of its cadence (the G1 log has 884 MiB). Both only explain misses of the filed process-level predictions; the verdict rests on the per-update Byteman readings (exact) and the unit tier.
6. **Deviations and gaps.** The B3a text was extended (nodes, data, commit-log cap); `jstat` replaced by the GC log; the content of B at the end of each arm is read indirectly (D5); the 4-second full-GC sampler perturbs the run (each histogram forces a full GC; visible as "Heap Inspection Initiated GC" pauses). One run per arm, loopback nodes, one table shape (200-byte values). The byte size of a Mutation is not capped by the knob: a row-count cap of 100000 gives a 21 MB Mutation that the commit log rejects (A3's "counts rows, not bytes" bypass, seen). The N = 0 and N = 100000 arms do not show what the heap does when the write completes.
7. **Core question.** Does the constraint cap usage? Yes, in rows per Mutation and therefore in heap per Mutation: the unit tier shows every batch at exactly N Unfilteds (N + 1 with an open tombstone) and N = 0 returning the whole partition as one object with heap proportional to rows (320 B per row for 100-byte values; 998 times the N = 100 batch); the cluster tier shows the same on the real receive path, 416 B per row, 20000 / 2000 / 200 updates of 100 / 1000 / 10000 rows, and one 832 MB update at N = 0 (parts 3 and 4). The cap bounds the heap of the Mutation, not the heap of the process (the memtable holds the received rows) and not its bytes (rows, not bytes: part 6).

**Conclusion (one line):** Unit B2g row 1 — confirmed (caps); Cluster B3g row 1 — confirmed (caps) on the heap per Mutation, with the filed process-level sub-predictions (sampler maxima, N = 0 versus default by the sampler) missed and N = 0 / N = 100000 ending in `MutationExceededMaxSizeException`.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-27: `unit/unit.out` and every committed cluster excerpt were re-parsed by `harness/.../selfcheck.py` (independent of `analyze.py`; `run1/selfcheck.txt`: 53 PASS, 0 FAIL, "ALL PASS"), plus by hand `cluster/n0/system-B-excerpt.txt`, `cluster/n0/s4batch-first-last.txt`, `cluster/p0/s4batch-count.txt`, `cluster/n100000/analysis.txt`, `cluster/*/gc-pauses.txt`, and `ps` on the node for leftovers.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `s4throttle.txt` of the five CDC arms = 100 / 1000 / 10000 / 100000 / 0; `p0/s4batch-count.txt` = 0; `daemons left: 0` in the six `cmdlog.txt`. |
| 2. Readings | yes | `n0/system-B-excerpt.txt` shows `MutationExceededMaxSizeException ... (425891207/16777216)`; `gc-pauses.txt` of `n0` has the 884 MiB class of pause; `selfcheck.txt` quotes the sampler maxima. |
| 3. Matched row | yes | `selfcheck.txt`: unit exact batch sizes and ratios; cluster updates = ceil(2,000,000 / N) with total 2,000,000 rows for the three completed arms, 416 B per row in all five. |
| 4. Excluded rows | yes | no unit batch above N (N + 1 in the tombstone variant); `p0` has no `S4BATCH`. |
| 5. Observed vs. inferred | yes | inference (i) is the weakest: `u100/samples.txt` shows a one-sample transient of 516 MB with `BufferCell`/`BTreeRow` at 57.5 MB each and 145 MB at rest, so the attribution to the memtable is only partial (340 MB of the peak sample is in classes the sampler did not record); it does not enter the verdict, which rests on the per-update readings. |
| 6. Deviations and gaps | yes | listed. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | knob reaches the check (`S4THROTTLE`) -> write path taken (`S4BATCH`, absent for the plain table) -> rows per update <= N -> heap per update proportional -> N = 0 is one object. |

### 5.2 Run 2?

**No** (2026-10-27). Unit results are exact counts and ratios; the cluster results are exact per-update readings in five independent node starts, with a plain-table control; the misses concern process-level heap that does not enter the verdict. A run 2 could use an on-heap-free sink (a memtable that does not keep rows on the heap) to make the process-level heap precise.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): with N > 1 no Mutation built by the streaming write path holds more than N (N + 1) Unfilteds, so its heap is bounded by about N x row size; with N = 0 one Mutation holds the whole partition.

**Claim tested (B1):** with `maxBatchSize` = N > 1, no Mutation built by the streaming write path holds more than about N+1 Unfilteds of a partition (heap per Mutation bounded by N); with `maxBatchSize` = 0, one Mutation holds the whole partition, and peak heap grows with partition size.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1: batches of exactly N, N + 1 with an open tombstone, N = 0 one object; heap linear in N, retained heap = unshared heap) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1 on the heap per Mutation: 41.7 KB / 416 KB / 4.16 MB / 41.6 MB / 832 MB for N = 100 / 1000 / 10000 / 100000 / 0; plain-table control builds none); filed process-level sub-predictions missed (sampler maxima, N = 0 versus default by the sampler); N = 0 and N = 100000 failed on `max_mutation_size` | caps (rows per Mutation; the bytes of a Mutation are not capped, and the opt-out leaves one Mutation of the whole partition) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U6 (B2) and C1-C8 (B3), 2026-10-27. For stage 3: the `max_mutation_size` interplay (C2); and that the process-level heap of a repair through the write path has a transient of about 0.5 GB at the default N that the knob does not change (not attributed).
