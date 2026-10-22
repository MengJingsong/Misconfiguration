# batch_size_fail_threshold-verifyBatchSize-failThreshold--guided — stage-4 results  <!-- file: results/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md; the stem ends in --guided or --autonomous -->
> **Case:** [`batch_size_fail_threshold-verifyBatchSize-failThreshold--guided`](../../stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md)
>
> **Status:** **Closed 2026-10-20 — verdict filed: unit Confirmed, cluster Confirmed — does not cap.** Estimate negative; claim under test: coordinator memory for a batch follows the batch size, not the threshold. A rejected batch's coordinator allocation is about 2.0–2.4 × its bytes at every threshold (medians within 1 %); the positive control (`native_transport_max_message_size` 512 KiB) cuts it to 0. Step-1 amendments R7, R8; one harness defect (§3), the cluster tier restarted; no run 2.
> 
> **Outcome class:** true negative — stage-3 estimate vs the stage-4 effect on the constraint
>
> **Agent:** guided (the suffix of the case-file stem). One results file per case file.

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
| **Case-file version** | Guided file, hash of §9's text after the audit's amendments (`sed -n '/^## 9\. /,/^## 10\. /p' <file> | git hash-object --stdin`): `ce9fe324dbdb69c9c358b3f8a6df117289f8294d`, computed 2026-10-20 before any harness or run. §9a is frozen at this version, including the dated block 9f. Commit holding the file: `cd7fec5` (the step-0 audit commit on `main`). **Re-frozen 2026-10-20 at step 1, before any run or reading, after the dated amendments R7 and R8 (9f): `a7fa623e135ae8a73c90ab9d5ee69604c76ce986`.** Run 1 used this version (not yet committed; the commit that holds it is the one that files this verdict). |
| **Harness** | [`harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/`](../harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/) — written 2026-10-20 (step 1): `Alloc.java` + `batch-alloc.btm` (Byteman allocation lines per request), `SendBatches.java` (v5 client), `BatchSizeAllocTest.java` + `unit-run.sh`, `cluster-run.py`, `analyze.py`, `make-node-yaml.sh`, `Jmx.java`. Instrument checks: `TestScript` 10 rules, no errors (`run1/unit/testscript.log`); `Alloc` known answer, 8 MiB `byte[]` read as 8,396,728 B (`run1/unit/summary.txt`); `Submit -l` 10 rules and a 10-s idle control with no trace line at each node start (`run1/cluster/summary.txt`). |
| **Tiers and values** | Unit (9c, as amended by R8: through `CQLTester`'s in-process server): thresholds 50 KiB · 500 KiB · 5 MiB × batches 1 · 4 · 16 MiB, `ctl16k`, control at 512 KiB, 20 batches per arm. Cluster (9e): one node, `-Xmx4G`, native v5, 64-partition unlogged batches of 1 · 4 · 16 MiB, positive control with `native_transport_max_message_size` 512 KiB. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-20 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | 9a Claim, 9d: heap bytes allocated on the coordinator for one batch. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 9b values 50 KiB (default, `Config.java:332`), 500 KiB, 5 MiB; batch sizes 1, 4, 16 MiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | 9d reads the executing thread's allocation only; netty decode and replica work are outside it (the trap is named). The control would read 0 trivially. **Amended** (R2): also the networking pool `Size` delta and heap high-water. |
| A. Core question | usage driven to the limit and past it | Partly | At 5 MiB the 1 and 4 MiB batches are accepted. The 16 MiB batch also exceeded the transport's 16 MiB default and the filed 256 MiB hold-fixed value would fail at startup with the default in-flight limits. **Amended** (R1, R5). |
| B. Logic | each step says what it establishes | Met | 9a "How this verifies" block matches steps, prediction and rows. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | "Within the noise band" and "falls" were not numeric. **Amended** (R3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows: tracks the batch size and the control cuts it (Confirmed), falls with the threshold (Refuted), flat in both (Not confirmed), control flat (Not confirmed), no batch reaches it (Invalid). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs the allocation to track the batch size, the rejection iff size > threshold (client error + log line, `BatchStatement.java:358`) and the control cutting it. |
| B. Logic | alternative explanations and their controls | Met | Control: a transport cap that binds before the build; fixed heap, one batch in flight, batch type fixed (9b). |
| C. Specific | a human can follow it from the intro and the prediction/conclusions | Met | Intro and 9a explain why the check runs after the build and what each row means. |
| C. Specific | an AI can run the runbook without re-deriving the code path | Partly | `send_batches.py` and the Byteman rule are named, not written (step 1); the control's discard needs protocol v5. **Amended** (R4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Transport settings and protocol were not exact (R1, R4); thread-allocation arithmetic is exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | `send_batches.py`, the Byteman allocation rule and a v5 client are step-1 work; the closed `native_transport_receive_queue_capacity` harness has a `SimpleClient` to reuse. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 20 batches × (1+4+16 MiB) × 3 thresholds is small against 4 GiB heap and 47 GB disk; with R1 the 16 MiB batch passes the transport. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked: `BatchStatement.java:340-358` (threshold compare `:352`, throw `:358`), `Config.java:332` default 50 KiB, `DatabaseDescriptor.java:2071`, `:911-915` and the derived default `:3237-3245`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Set `native_transport_max_request_data_in_flight` and `…_per_ip` to 256 MiB and `native_transport_max_message_size` to 64 MiB (control: 512 KiB) | Applied 2026-10-20 (9b, 9f) | the filed 256 MiB would refuse to start at `-Xmx4G`; the derived default (16 MiB) would refuse the 16 MiB batch |
| R2 | Control also reads the networking pool `Size` delta and heap high-water | Applied 2026-10-20 (9d, 9f) | a discarded request never reaches `execute`, so the thread reading is trivially 0 |
| R3 | Define "the same" (medians within 10 %) and "falls" (more than 50 % below) | Applied 2026-10-20 (9a, 9f) | numeric edges fixed before any reading |
| R4 | All arms on native protocol v5 via `SimpleClient` | Applied 2026-10-20 (9c, 9f) | the discard branch is the v5 large-message path |
| R5 | Read the prediction on the rejected pairs only; accepted pairs show the build | Applied 2026-10-20 (9a, 9f) | at 5 MiB the 1 and 4 MiB batches are accepted |
| R6 | Write `send_batches.py` and the Byteman allocation rule | Done 2026-10-20 (step 1): the client is `SendBatches.java` on `SimpleClient` (R4), the rules `batch-alloc.btm` | prerequisites, not design changes |
| R7 | Read "allocated bytes per request" as the decode thread's bytes in `BatchMessage$1.decode` plus the executing thread's bytes in `BatchMessage.execute`; keep the filed `BatchStatement.execute` reading as secondary | Applied 2026-10-20 at step 1, before any run or reading (9f) | source reading: the bound values are copied at decode, before `execute`. **Its stated rationale was partly wrong** (§4.2 part 2): the secondary reading also grows with the batch, because `getMutations` serializes every mutation for `Mutation.validateSize`. The amendment changed no row of the outcome: both readings select the same row |
| R8 | Unit tier through the in-process server (`CQLTester`, `SimpleClient` v5), the control by `setNativeTransportMaxMessageSizeInBytes` | Applied 2026-10-20 at step 1, before any run or reading (9f) | a direct `execute` call skips the decode and cannot run the control |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's runbook observables:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-20 (unit 20:09–20:12 MDT; cluster attempt 1 20:14–20:24, aborted, §3; cluster 20:27–20:39 MDT) | not done |
| Node (CloudLab name and type) | `node0.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu`, 40 cores, 251 GiB; a fresh node (JDK, Ant, clone and build set up this session, `environment.md` §1–§3) | — |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | — |
| JDK (`java -version`) | openjdk 11.0.32.1 | — |
| Ant (`ant -version`) | Apache Ant 1.10.12 | — |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54210d541339c2e7c17a794195cac0e67c2`), `ant build-test` successful in 1 min 55 s | — |
| Case-file commit / harness commit | `cd7fec5` + the R7/R8 amendments (§9 hash `a7fa623e…`) / uncommitted at run time (md5 in each `summary.txt`) | — |
| Storage for node data | `/dev/sda3` (local ext3), `~/stage4-bsf/data`; nothing on `/proj` | — |
| Full logs (path, outside the repo) | `~/stage4-logs/bsf/run1/unit/` (`ant.log`, `test.out`, `batch-alloc.trace`), `~/stage4-logs/bsf/run1/cluster/` (`session.log`, `summary.txt`, `requests.txt`, `trace-all.txt`, `system-*.log`, `poll-*.csv`, `heap-*.txt`), `~/stage4-logs/bsf/run1/cluster-attempt1/`, the diagnostic `~/stage4-logs/bsf/diag-jfr/` (`rec.jfr`) | — |

Cluster node: `-Xms4G -Xmx4G`, G1, `memtable_allocation_type: heap_buffers`, `batch_size_warn_threshold: 5KiB`, in-flight limits 256 MiB each, `native_transport_max_message_size` 64 MiB (main) / 512 KiB (control) (`run1/cluster/summary.txt`, the `jvm:` and `yaml` lines). Unit JVM: heap max 1,056,309,248 B, protocol v5 (`run1/unit/summary.txt`).

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster, attempt 1 | harness set-up check before the control lifetime (9e step 4) | Not a runbook step: `cluster-run.py`'s "another CassandraDaemon runs" check grepped every process's command line, and matched the operator's wait loop, which had the word in its own `grep` pattern. The run stopped before the control lifetime. The main lifetime had completed with every check passing (`run1/cluster-attempt1/summary.txt`). | The check matches only `java` processes whose arguments name `org.apache.cassandra.service.CassandraDaemon`. Then the whole cluster tier was run again from its beginning. Attempt 1's readings are kept as evidence and not used for the verdict; its medians agree with the counted run within 0.3 % at every rejected pair. | 2026-10-20 | none needed (harness only) |

Before run 1, at step 1: amendments R7 and R8 (§1.1, case file 9f). They were made from the source, with no reading, and the hash was re-frozen.

## 4. Run 1

**Scope:** unit tier (11 arms × 20 batches, one `ant testsome`) and cluster tier (lifetime `main`: idle control, `ctl16k`, thresholds 50 KiB · 500 KiB · 5 MiB × 1 · 4 · 16 MiB; lifetime `ctl`: 16 MiB batches with `native_transport_max_message_size` 512 KiB), 20 batches per arm. **Command log:** `batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/run1/` (`unit/summary.txt`, `unit/test.out`, `unit/analysis.txt`, `unit/reject-log-lines.txt`; `cluster/summary.txt`, `cluster/requests.txt`, `cluster/arms.csv`, `cluster/poll/`, `cluster/reject-log-lines.txt`, `cluster/control-log-lines.txt`; `selfcheck.py`, `selfcheck.txt`; `diag-jfr/validateSize-stack.txt`; `cluster-attempt1/summary.txt`).

### 4.1 Readings

The primary reading ("total") is the coordinator allocation per request (R7): the decode thread's bytes in `BatchMessage$1.decode` plus the executing thread's bytes in `BatchMessage.execute`. "bst" is the filed 9d reading, the executing thread's bytes in `BatchStatement.execute`. Each figure is the median of 20 requests. "size" is `IMutation.dataSize`, the check's operand, read at `verifyBatchSize`.

**Unit tier** (`run1/unit/analysis.txt`; test passed, 1 run, 0 failures)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Instrument: `Alloc` around an 8 MiB `byte[]` | 8,396,728 B (within [8,388,608, 8,454,144]) | `unit/summary.txt` |
| V1 rejected iff size > threshold (client "Batch too large" + `rej` line), all 200 non-control batches | 0 mismatches | `unit/analysis.txt`, `unit/test.out` |
| V3 one "exceeding specified threshold … (see batch_size_fail_threshold)" log line per rejection | 140 lines, 140 rejections | `unit/reject-log-lines.txt` |
| `ctl16k` (50 KiB, size 20,864): accepted | 20/20 ok; total 635,092; bst 538,032 | `unit/analysis.txt` |
| 1 MiB (size 1,053,056), rejected at 50 / 500 KiB | total 2,509,672 / 2,485,476 (spread 1.0 %); bst 1,380,072 / 1,361,264 | `unit/analysis.txt` |
| 4 MiB (size 4,198,784), rejected at 50 / 500 KiB | total 8,794,136 / 8,776,880 (0.2 %); bst 4,524,200 / 4,506,976 | `unit/analysis.txt` |
| 16 MiB (size 16,781,696), rejected at 50 / 500 / 5120 KiB | total 33,959,968 / 33,942,736 / 33,909,952 (0.1 %); bst 17,107,152 / 17,089,920 / 17,073,008 | `unit/analysis.txt` |
| Accepted at 5 MiB: 1 MiB, 4 MiB | total 2,679,392, 10,013,508; bst 1,560,520, 5,752,872 | `unit/analysis.txt` |
| Control C: 16 MiB at max message 512 KiB | 20/20 "CQL Message of size 16779337 bytes exceeds allowed maximum of 524288 bytes"; no dec/exe/bst/siz line; total 0 | `unit/test.out` |

**Cluster tier** (`run1/cluster/summary.txt`; heap and pool from `arms.csv` and `poll/`)

| Capacity value | Run (control / A / B / C) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| — | idle control | trace lines in 10 s with no batch | 0 (main), 0 (ctl) | `cluster/summary.txt` |
| 50 KiB (default; JMX read 50) | control `ctl16k` | outcome; total; bst; heap max − start | 20/20 ok; 602,824; 516,508; 83,886,080 | `cluster/summary.txt`, `arms.csv` |
| 50 KiB | A: 1 · 4 · 16 MiB | outcome; total; bst | all 60 rejected; 2,477,136 · 8,768,576 · 33,925,224; 1,358,912 · 4,504,624 · 17,078,360 | `cluster/summary.txt` |
| 500 KiB (set live, read back 500) | B: 1 · 4 · 16 MiB | outcome; total; bst | all 60 rejected; 2,467,928 · 8,713,288 · 33,879,144; 1,349,704 · 4,469,304 · 17,052,248 | `cluster/summary.txt` |
| 5 MiB (set live, read back 5120) | B: 1 · 4 MiB | outcome; total; bst | 40/40 accepted; 2,617,928 · 10,998,096; 1,519,808 · 6,754,248 | `cluster/summary.txt` |
| 5 MiB | B: 16 MiB | outcome; total; bst | 20/20 rejected; 33,879,128; 17,052,232 | `cluster/summary.txt` |
| all | disallow evidence | client error; `rej` lines; log lines | "Batch too large" ×140; 140; 140 "exceeding specified threshold … (see batch_size_fail_threshold)" | `cluster/requests.txt`, `cluster/reject-log-lines.txt`, `selfcheck.txt` |
| 16 MiB, rejected at 50 / 500 / 5120 KiB | heap high-water (R2, secondary) | heap max − start of arm | 738,197,504 / 687,865,856 / 704,643,072 (1 MiB: 67,108,864 at both rejecting thresholds) | `arms.csv` |
| 50 KiB, max message 512 KiB | C: 16 MiB | outcome; trace lines; total; pool `UsedSize` max; heap max − start | 20/20 "CQL Message of size 16779337 bytes exceeds allowed maximum of 524288 bytes"; 0; 0; 327,688 B (back to 0); 100,663,296 | `cluster/requests.txt`, `cluster/poll/poll-C-msg512k-b16m.csv`, `arms.csv` |
| main lifetime | networking pool (R2, side observation) | `UsedSize` / `OverflowSize` at the end of each arm | grows by count × batch size per large-batch arm and never falls: 21.1 MB after `t50k-b1m`, 105 MB, 441 MB, … 1,322,048,896 B (`OverflowSize` 1,321,246,080) after `t5120k-b16m` | `cluster/poll/`, `selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — valid on both tiers. The limit was reached and passed: 140 of 200 non-control batches per tier had `dataSize` above the threshold and were rejected [observed: `unit/analysis.txt`, `cluster/summary.txt` V1, V4]. The threshold took effect at each value: the `siz` line's `fail=` is 51,200 / 512,000 / 5,242,880 in the matching arms [observed: `selfcheck.txt`], and the cluster's JMX read-back was 50 / 500 / 5120 KiB [observed: `cluster/summary.txt`]. Hold-fixed settings: `-Xms4G -Xmx4G` [observed: `jvm:` line]; in-flight limits 256 MiB and max message 64 MiB [observed: yaml keys line]; UNLOGGED, 64 partitions (`siz n=64`) [observed: `cluster/trace-all.txt` on the node]; one connection, one batch in flight [inferred: `SendBatches` waits for each response before the next send].
2. **Readings** — no outlier changes a median. The per-arm maximum of total sits above the median only in the first request of an arm, or in an accepted arm where a GC or memtable work landed on the thread (e.g. unit `ctl16k` max 15,786,808) [observed: `unit/analysis.txt`]. **Correction to R7's rationale:** R7 said the build inside `BatchStatement.execute` cannot grow with the batch's bytes. The secondary reading shows it does: bst ≈ 1.02 × the batch, e.g. 17,078,360 for a 16,777,216-byte batch [observed]. The diagnostic JFR run (2 batches per arm, not part of run 1) puts 115.8 MB of the executing thread's large allocations at `DataOutputBuffer.toByteArray` ← `Mutation$MutationSerializer.serializedSize` ← `Mutation.validateSize:171` ← `SingleTableUpdatesCollector.toMutations:112` ← `BatchStatement.getMutations:323` [observed: `diag-jfr/validateSize-stack.txt`]. Every mutation is serialized once to check `max_mutation_size`, before `verifyBatchSize`. The coordinator therefore allocates the batch's bytes twice before the threshold is consulted: once at decode (dec ≈ 1.0 × the batch) and once in the build (bst ≈ 1.0 ×). This strengthens the file's ground (Rule 3, "the check does not gate object creation").
3. **Matched row** — "Rejected batches allocate about the same bytes at every threshold and the allocation grows with batch size; the control cuts it → **Confirmed** — the threshold does not bound coordinator memory." Each part:
   - The same at every threshold: rejected medians differ by 1.0 / 0.2 / 0.1 % (unit) and 0.4 / 0.6 / 0.1 % (cluster) at 1 / 4 / 16 MiB, all under R3's 10 % [observed: `analysis.txt` / `summary.txt` P1].
   - Grows with batch size: 2.48 → 8.77 → 33.93 MB at 50 KiB on the cluster, ratios 3.54 and 3.87 against nominal ratios of 4 [observed: P2].
   - The control cuts it: 0 bytes on either thread against 33.9 MB uncontrolled, with no `dec` line at all [observed: C1, C2].
   - Disallow evidence: client error, `rej` line and log line for each of the 140 rejections [observed: V1, V3].
   - The secondary bst reading satisfies the same row [observed: P1[bst], P2[bst]].
4. **Excluded rows** —
   - **Refuted** ("allocation per rejected batch falls with the threshold"): the 16 MiB median at 50 KiB is 1.001 × the median at 5 MiB, against R3's "more than 50 % below" [observed: R line]. It is ruled out on both readings and both tiers.
   - "Flat in both threshold and batch size" (Not confirmed): not flat in size, 16 MiB is 13.7 × 1 MiB [observed: F line].
   - "Flat but the control does not cut it" (Not confirmed): the control cut it to 0 [observed].
   - "No batch reaches the threshold" (Invalid): 140 rejections [observed].
5. **Observed vs. inferred** — the conclusion depends on these inferred statements:
   - (a) The two measured threads carry the coordinator's per-request heap allocation for a rejected batch. [inferred: a rejected batch never leaves `BatchStatement.execute` (`rej` before `bst exc=true`), so no other stage runs for it. The frame bytes are in the networking pool, which is direct memory, not heap. Heap high-water per arm also follows the batch size and not the threshold (16 MiB: 738 / 688 / 705 MB; 1 MiB: 67 / 67 MB), which agrees at the coarse G1 granularity.]
   - (b) Thread allocation counts bytes allocated, not bytes retained. [inferred: a rejected batch's buffers become garbage on return (heap after GC stays near 92–113 MB in every arm, `arms.csv`), so the claim is about memory spent per batch, which is what 9a asks.]
6. **Deviations and gaps** —
   - R7 and R8 changed the observable and the unit procedure before any reading. R7's stated reason was partly wrong (part 2), but both readings select the same row.
   - The cluster tier restarted once after a harness defect (§3).
   - The accepted batches' local apply (the `MUTATION` stage) and commit-log work were not measured; they do not bear on rejected batches.
   - The client is `SendBatches.java`, not the `send_batches.py` that 9c names (R4).
   - Side observation, outside the claim: in the main lifetime the networking pool's `OverflowSize` grew by count × batch size on every large-batch arm and never returned. That is 1.32 GB of direct memory held after 11 arms on one connection, whether the batch was accepted or rejected. It is the large-request retention the closed `networking_cache_size` case recorded (its arm L). The control lifetime, whose frames were consumed without buffering, ended at 0.
   - No run 2.
7. **Core question** — the coordinator's memory for a batch does not follow `batch_size_fail_threshold`, and the threshold does not cap it. The steps:
   - The check fires exactly when `dataSize` exceeds the threshold [part 1].
   - The allocation per rejected batch is the same within 1 % at 50 KiB, 500 KiB and 5 MiB, and scales with the batch at about 2 × its bytes: one copy at decode, one serialization for `max_mutation_size` [parts 2, 3].
   - A cap that binds before the decode (the transport's message size) cuts the same reading to 0, so the instrument can see a binding cap [part 3].
   - The threshold decides only whether the already-built batch reaches the replicas [parts 3, 4].

**Conclusion (one line):** "Rejected batches allocate about the same bytes at every threshold and the allocation grows with batch size; the control cuts it" — **Confirmed** on both tiers (the threshold does not bound coordinator memory).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` was written after the conclusion and re-derives every figure from the raw files alone (`selfcheck.txt`). It reads the Byteman trace in file order, independent of `SendBatches`' joining and of `analyze.py`. It cuts the trace into requests at each `exe` line (200 per tier, no line left over), assigns them to the arms in send order, and recomputes the medians, the `siz` operand and threshold and the `rej` count. It also counts the disallow log lines and re-reads the JMX poll files.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: `siz` threshold per arm equals the set value; `rej` = 20 exactly where size > threshold; log lines 140 = `rej` lines 140 on both tiers; `summary.txt` read-backs and `jvm:` line re-read |
| 2. Readings | yes | `diag-jfr/validateSize-stack.txt` re-read: the stack runs from `Mutation.validateSize:171` through `getMutations:323` to `BatchStatement.execute:428`; the bst medians from the raw trace (e.g. cluster 17,078,360 at 50 KiB/16 MiB) match §4.1 |
| 3. Matched row | yes | every recomputed total and bst median in `selfcheck.txt` equals §4.1's figure (unit and cluster); control: the trace holds no line for the `ctl` lifetime (the file was never created; `trace-all.txt` is the main lifetime's 940 lines) and `requests.txt` holds 20 transport errors |
| 4. Excluded rows | yes | ratios recomputed from the medians: 33,925,224 / 33,879,128 = 1.001; 33,925,224 / 2,477,136 = 13.7 |
| 5. Observed vs. inferred | yes | heap after GC per arm 92–113 MB and high-water per arm in `arms.csv` re-read; `rej` precedes `bst … exc=true` in all 140 rejected requests of each tier's raw trace, and every accepted request has `bst … exc=false` (checked by a one-off re-parse, 2026-10-20) |
| 6. Deviations and gaps | yes | the attempt-1 summary is kept (`cluster-attempt1/summary.txt`); the pool figures in `selfcheck.txt` (UsedSize last = max in every main arm, 0 at the end of the control) match the side observation |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | the logic steps (1)–(4) of 9a map to parts 1, 3 (threshold invariance and growth), 3 (control) and 4 |

### 5.2 Run 2?

**No** (2026-10-20). The conclusion rests on observed medians that two tiers reproduce independently: unit and cluster agree within 1.4 % at every rejected pair. Attempt 1 of the cluster tier also reproduced them within 0.3 %. The verdict confirms the file's own claim, and does not refute it or confirm a bypass. The one inferred statement that matters (part 5a) is supported by a second, coarser instrument (heap high-water).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative (Rule 3: the check runs after the batch's mutations are built, so it does not gate object creation).

**Claim tested:** `batch_size_fail_threshold` does not bound the coordinator memory spent on a batch; for a batch above the threshold, the heap allocated while handling it follows the batch's size, not the threshold. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — rejected batches allocate 2.51 / 8.79 / 33.96 MB at 1 / 4 / 16 MiB, the same within 1.0 % at every threshold; the control cuts it to 0 | does not cap | run 1 + self-check | 2026-10-20 |
| Cluster | **Confirmed** — 2.48 / 8.77 / 33.93 MB at 1 / 4 / 16 MiB, the same within 0.6 % at every threshold (16 MiB: 33.93 / 33.88 / 33.88 MB at 50 KiB / 500 KiB / 5 MiB); the control cuts it to 0 | does not cap | run 1 + self-check | 2026-10-20 |

**Positive control:** `native_transport_max_message_size` lowered to 512 KiB, a cap that binds before the decode. Under the same workload and instruments, the 16 MiB batch was refused at the transport ("CQL Message of size 16779337 bytes exceeds allowed maximum of 524288 bytes", 20/20 per tier). It wrote no `dec`, `exe`, `bst` or `siz` line, so its allocation on both threads was 0, against 33.9 MB without the control. The networking pool peaked at 327,688 B and returned to 0, against 335 MB retained for the same 20 batches without the control.

**Where the bytes go (for the case's §8):** a rejected batch costs the coordinator about 2 × its bytes of heap before the check: the bound values are copied at decode (`CBUtil.readBoundValue`), and every mutation is serialized again by `Mutation.validateSize` (`max_mutation_size`) inside `getMutations`. Its frames also sit in the networking pool (direct memory) until decoded. On a v5 connection those large-message frame buffers were not returned to the pool afterwards; that is the `networking_cache_size` finding, outside this claim.

**Feedback filed:** the case file's §10 "Stage-4 feedback" field and Notes updated (2026-10-20); 9f holds R7 and R8 as frozen; the correction to R7's rationale is recorded in §10, outside the hashed §9; `_INDEX.md` Stage 4 cell and coverage rows; `HANDOFF.md` state. Not committed.
