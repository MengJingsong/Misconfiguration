<!-- file: cases/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md -->
# batch_size_warn_threshold — verification solution

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:340` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI via Agent SDK, 2026-10-26 |
| Estimate | `negative`. Crossing the warn threshold only logs a WARN and adds a client warning (`BatchStatement.java:360-365`); it never rejects, truncates or evicts anything, so it does not cap memory or disk. |
| Ground | The check at line 340 is advisory. The only hard cap on batch size is the separate `batch_size_fail_threshold` (line 352-358), and that is not the target. Batch size is also not checked at all on the CAS path and the virtual-table path (A3). |

## A. Constraint trace

**A1. The constraint.** `batch_size_warn_threshold`; configuration entry. Declared at `src/java/org/apache/cassandra/config/Config.java:329-330` as `DataStorageSpec.IntKibibytesBound`, default `"5KiB"` (a literal in the field initializer; also written in `conf/cassandra.yaml:1840`). It replaces the old `batch_size_warn_threshold_in_kb` (`Config.java:329`). Unit: KiB in config, converted to bytes by `DatabaseDescriptor.getBatchSizeWarnThreshold()` (`DatabaseDescriptor.java:2059-2062`, `toBytes()`, int). Startup validation that the value fits in an int of bytes: `DatabaseDescriptor.java:631`. Settable: yaml key (restart), and at runtime via the StorageService MBean `setBatchSizeWarnThresholdInKiB` (`StorageService.java:6868-6880`, which calls `DatabaseDescriptor.setBatchSizeWarnThresholdInKiB`, `DatabaseDescriptor.java:2085-2088`); the field is `volatile` so a change applies without restart. No `-D` property.

**A2. What it caps.** Nominally the size of a multi-partition batch (heap on the coordinator while the batch is held and sent). The quantity compared is `IMutation.dataSize(mutations)` (`IMutation.java:63-72`): the sum over all `PartitionUpdate.dataSize()` (`PartitionUpdate.java:346-349`), i.e. the serialized-style data size of rows (clustering, liveness, deletion, cells: `BTreeRow.java:522-529`, `AbstractCell.java:120`). It is not heap size (`unsharedHeapSize`) and not on-wire size. In fact it caps nothing: see A3.

**A3. Mechanism.**
1. `BatchStatement.execute` -> `executeWithoutConditions` (`:434`) calls `verifyBatchSize(mutations)` at `:439` after `getMutations(...)` (`:428`) has already built every mutation in memory.
2. `verifyBatchSize` (`:331`): returns immediately if `mutations.size() <= 1` (`:334`), so single-partition batches are never checked.
3. `size = IMutation.dataSize(mutations)` (`:338`), compared `size > warnThreshold` at `:340` (target).
4. If the warn threshold is exceeded and size is also over the fail threshold (`:352`), it throws `InvalidRequestException("Batch too large")` (`:358`). That is the fail threshold's effect, not the warn threshold's.
5. Otherwise (`:360-365`) it does `logger.warn(...)` and `ClientWarn.instance.warn(...)`. Execution continues to `StorageProxy.mutateWithTriggers` (`:446`). So at the warn limit the outcome is only a log line and a client warning; the batch is applied in full.
Bypasses: (a) `executeWithConditions` (CAS, `:455`+) never calls `verifyBatchSize`; (b) `executeInternalWithoutCondition` (`:569-577`, virtual tables and internal execution) never calls it; (c) single-mutation batches (`:334`); (d) the mutations are fully materialized before the check, so the memory is already spent when the check runs (the check cannot prevent that allocation). Overshoot: with the warn threshold set above the fail threshold, the warn branch is unreachable for sizes over fail, since the fail branch is taken first (`:352`). No cross-validation of warn vs. fail was found in `DatabaseDescriptor` (only `:631` checks the byte conversion).

**A4. Other consumers.** Coordinator heap is also used by the parsed statement, bound values, the native-transport request buffers (`native_transport_max_frame_size`, `conf/cassandra.yaml:1044`; in-flight request limits), the memtable on replicas, commit log segments (`max_mutation_size`, `conf/cassandra.yaml:652`), and the batchlog table for logged batches (disk). None are governed by the warn threshold.

**A5. Evidence beyond the source.** Comment text in `conf/cassandra.yaml:1836-1844` ("Log WARN on any multiple-partition batch size exceeding this value"). CASSANDRA-10876 (referenced at `BatchStatement.java:333`, warn only for multi-mutation batches). CASSANDRA-17668 (MBean setter renaming, `StorageServiceMBean.java:1047`). Unit tests that touch the setter: `test/unit/org/apache/cassandra/service/StorageServiceTest.java:303`, `test/unit/org/apache/cassandra/config/DatabaseDescriptorTest.java:343`.

## B. Verification solution

**B1. Claim under test.** Raising or lowering `batch_size_warn_threshold` does not change the memory or disk a multi-partition batch uses: a batch larger than the threshold is still fully executed (only a WARN and a client warning appear), and node heap/disk use for a given workload is the same for warn = 5KiB and warn = very large. Falsified if usage or acceptance changes with the warn value alone (fail threshold held constant).

> *Amended 2026-10-26 (D, A3):* the claim is read for warn <= fail, the documented relation (`conf/cassandra.yaml:1844`, "10x warn"). With warn > fail the fail check is skipped (`:340` gates `:352`); the extra inversion arm records that and is not part of the claim.

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/scratch/c509/`), build there: `ant jar`. Add a JUnit test (e.g. `test/unit/org/apache/cassandra/cql3/BatchWarnThresholdProbeTest.java`, extends `CQLTester`) in the copy only. Run: `ant testsome -Dtest.name=BatchWarnThresholdProbeTest`. JVM opts: default test opts, `-Xmx1g`.

**B2b. Knobs.** `DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(n)` with n in {1, 5, 1024, 65536}; fail threshold fixed at 100000 KiB via `DatabaseDescriptor.setBatchSizeFailThresholdInKiB(100000)` so that warn is the only variable. 1 and 5 put the threshold below the batch; 1024 and 65536 above.

**B2c. Workload.** Table `ks.t (k int, c int, v blob, PRIMARY KEY (k, c))`. A LOGGED batch of 20 INSERTs into 20 different partitions, each with a 1 KiB blob, so `dataSize` ~ 20 KiB plus overhead (> 5 KiB, < 1024 KiB). A second batch of 200 inserts of 1 KiB (~200 KiB). Single-partition batch of the same 20 KiB as a control for the `:334` early return.

**B2d. Observables and instruments.** (1) The return of `IMutation.dataSize(mutations)` for the batch, obtained by calling `batchStatement.getMutations(...)` via reflection or by running the statement through `QueryProcessor` and reading `ClientWarn` warnings (`ClientWarn.instance.getWarnings()`); (2) whether the call throws; (3) rows present afterwards (`SELECT count(*)`); (4) heap before/after via `Runtime` after `System.gc()` and the `ClientWarn` warning count; (5) log capture of the WARN line. Cannot observe: coordinator transient heap precisely (only after GC, indirect).

**B2e. Procedure.** 1. Build as in B2a. 2. In the test, for each warn value: set knobs, execute the 20-partition batch, record warnings, exception, row count, dataSize. *Amended 2026-10-26 (D, A1):* the batch is sent through CQLTester's in-process native server with a protocol-v4 `SimpleClient` LOGGED batch, not `execute(...)` (which calls `executeLocally` and never reaches `verifyBatchSize`); warnings come from the response, dataSize and the branch from Byteman rules at `verifyBatchSize`. 3. Repeat for the 200-insert batch and the single-partition control. 4. Record `Runtime.totalMemory()-freeMemory()` after GC before and after each execution. 5. ~~Also run a CAS batch over the same 20 partitions.~~ *Amended 2026-10-26 (D, A5):* not run; a CAS batch is single-partition by construction (`BatchStatement.java:229-239`), so it cannot tell the CAS bypass from the single-mutation early return.

**B2f. Predictions (stated before any run).** warn=1 and 5 KiB: warning present, no exception, all 20 rows written. warn=1024 and 65536: no warning, 20 rows written. The 200 KiB batch: warn at 1, 5; no warn at 1024, 65536; no exception at any value (fail=100000 KiB). Row counts and the measured dataSize are identical across all warn values. Post-GC heap delta identical within noise (< 1 MiB). Single-partition control: never a warning.
*Amended 2026-10-26 (D, A2, A3):* (a) "Post-GC heap delta" is replaced by the allocation of the coordinator thread inside `BatchStatement.execute` (Byteman `bst` line): per-arm medians for one batch size differ by at most 10 % of the larger median or 16 KiB, whichever is larger (the WARN branch allocates a few KiB). (b) Inversion arm `inv` (warn 200 KiB, fail 10 KiB, the 20 KiB batch): accepted, no warning, no `Batch too large`, 20 rows written, no `rej` line.

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| Warning present below threshold, rows all written, dataSize equal across values | Claim confirmed at unit level: the warn check is advisory |
| Exception "Batch too large" at a warn-only value | Claim refuted (but check fail threshold interaction first) |
| Row count or dataSize varies with warn | Claim refuted |
| Positive control: lowering the fail threshold to 10 KiB with warn constant rejects the 20 KiB batch with 0 rows written | Cap exists where fail binds; control moved, so the flat warn reading is meaningful |
| Fail=10 KiB (warn held at 5 KiB, below fail) does not reject | Control did not move; not confirmed, check the batch is multi-partition and above 10 KiB |
| dataSize never exceeds the smaller thresholds | Limit never reached; not confirmed |
| *(added 2026-10-26, A2)* Allocation medians for one batch size differ by more than the B2f band, tracking the warn value | Claim refuted (usage follows the knob) |
| *(added 2026-10-26, A3)* Inversion arm `inv` accepted with no warning, no `rej` line | Recorded finding, not a verdict row: the warn value gates the fail check; the claim about the warn value as a cap is unaffected |
| *(added 2026-10-26, A3)* Inversion arm `inv` rejected | Recorded: contradicts A3's reading of `:340`/`:352`; the tier is Not confirmed for A3 only, main rows unaffected |

**B2h. Controls.** Fail-threshold positive control (above; *amended 2026-10-26, A4:* warn 5 KiB < fail 10 KiB, else the warn gate skips the fail check); single-partition batch (early return); identical data across runs (fixed blob content and keys); fresh table per run to rule out earlier state.

### B3. Cluster tier

**B3a. Environment and build.** One node (second node optional for batchlog replication), JDK 11, built from the local copy (`ant jar`; run from `/local/scratch/c509/bin/cassandra -f` with `-Dcassandra.storagedir=/local/scratch/node1`). Heap `-Xms2G -Xmx2G` (set in `conf/jvm11-server.options`). Data, commitlog, hints and batchlog on a local disk with >= 20 GiB free. `conf/cassandra.yaml`: `batch_size_fail_threshold: 100000KiB`, `native_transport_max_frame_size: 64MiB`, `max_mutation_size` default.

> *Amended 2026-10-26 (D, A6, A8):* paths are the working tree and a tmpfs under the stage-4 work directory (no `/local/scratch` on the node); also set `native_transport_max_message_size: 64MiB` and the two in-flight limits to 128MiB (the derived message-size default is 16 MiB, `DatabaseDescriptor.java:3237-3245`); clients speak protocol v4.

**B3b. Knobs.** `batch_size_warn_threshold` in {5KiB (default), 90000KiB}, set in yaml per run (restart), and once at runtime through JMX `StorageService.setBatchSizeWarnThresholdInKiB` (`nodetool` has no direct setter in this tree; use `jmxterm`/`jconsole`) to show no restart is needed. Positive control: `batch_size_fail_threshold` in {100000KiB, 20KiB}.

**B3c. Workload.** Using cqlsh/Python driver, loop of 2000 LOGGED batches, each 50 inserts across 50 partitions with 1 KiB blobs (~50 KiB per batch, i.e. 10x the default warn, under the 100000 KiB fail), at 4 concurrent clients, ~100 MB of data total; then a large-batch run: 20 batches of 20 MiB (20000 inserts of 1 KiB) to push the batch into the MiB range at warn=5KiB and at 90000KiB. Duration ~5 min per run.

> *Amended 2026-10-26 (D, A6, A8):* the 20 MiB batches are UNLOGGED (a LOGGED one writes its whole content as one batchlog mutation, over `max_mutation_size` 16 MiB, and would fail for that reason); one client connection with one batch in flight (the Byteman lines are read per arm); each of the two workloads is run twice per node lifetime (B3h noise estimate).

**B3d. Observables and instruments.** `nodetool info` (heap used), `jcmd <pid> GC.heap_info` and a GC log (`-Xlog:gc*`) sampled every 5 s; peak heap from the GC log; `nodetool tablestats ks.t` and `du -sk` of data and batchlog directories (disk); `nodetool tpstats`; `system.log` WARN count for "Batch for [...] is of size"; client-side count of driver warnings and errors; JMX `org.apache.cassandra.metrics:type=Table,name=...` partitions-per-logged-batch histogram. Cannot be observed directly: coordinator per-request transient allocation (inferred from GC log allocation rate). *Amended 2026-10-26 (D, A7):* it is observed, by the Byteman `bst` line (bytes the coordinator thread allocated inside `BatchStatement.execute`).

**B3e. Procedure.** 1. Build and start node with warn=5KiB. 2. Run the 2000-batch workload; record peak heap, GC allocation, disk, WARN count, client errors. 3. `nodetool flush`; record disk. 4. Stop; wipe the data dir; restart with warn=90000KiB; repeat steps 2-3. 5. Repeat the 20 MiB batch run at both values. 6. Runtime-change run: start at 5KiB, run half the workload, set to 90000KiB via JMX, run the second half; check WARN lines stop. 7. Positive control: fail=20KiB, same 50 KiB workload; expect rejections. 8. Stop the node and verify (`pgrep -f CassandraDaemon`) none remains.

**B3f. Predictions.** warn=5KiB: ~2000 WARN lines (the logger is not rate-limited here, `:362`), 0 client errors, all rows present. warn=90000KiB: 0 batch WARN lines, 0 errors, all rows present. Peak heap and total disk equal between the two within +/-10% (run-to-run noise); GC allocation rate the same. Large-batch run: same acceptance and the same heap peak at both warn values (the 20 MiB batch has already been materialized before the check). Fail=20KiB control: every batch rejected with "Batch too large", disk growth ~0.
*Amended 2026-10-26 (D, A6, A7):* counts: at warn 5 KiB, 2 x (2000 + 20) = 4040 "Batch for" WARN lines and 4040 client warnings per node lifetime; at warn 90000KiB, 0 and 0. "Peak heap" is read as the largest post-collection occupancy in the GC log of the arm's window; per-batch coordinator allocation (`bst`) medians and the data directory bytes after `nodetool flush` must match between the two lifetimes within 10 %, and the server write count must be equal. The control has warn at 5 KiB (A4). Inversion arm `inv` (fail 20 KiB, warn set live to 200 KiB, 50 KiB batches): accepted, no WARN, no rejection.

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| WARN lines only differ; heap peak, disk, accepted rows within noise | Claim confirmed: warn threshold does not bound the resource |
| Peak heap or disk differs by more than the noise band (> 25%) tracking the warn value | Claim refuted, usage follows the knob |
| Batches rejected at warn=5KiB | Claim refuted (re-check fail value in effect) |
| Fail=20KiB control: rejections and flat disk while warn runs are flat | Positive control moved where a cap binds; confirms the instruments can see a cap |
| Fail control also accepts everything | Control did not move; not confirmed (batches below 20KiB or wrong config loaded) |
| Heap never approaches the 2 GiB limit and batches stay small | Limit never reached under load; not confirmed, enlarge the batches. *Amended 2026-10-26 (D, A7):* "limit reached" means the `siz` line shows a dataSize above the warn value of the smaller-warn lifetime; heap fill is not the test |
| *(added 2026-10-26, A7)* Allocation, disk or post-GC occupancy differ between the lifetimes by 10 to 25 % | Not confirmed (no matching row): noise too large to call it flat, rerun |
| *(added 2026-10-26, A3)* Inversion arm `inv` accepted with no WARN | Recorded finding, not a verdict row: the warn value gates the fail check |

**B3h. Controls.** Repeat each run twice to estimate noise; same heap, same data, fresh data directory and `nodetool drain` between runs; fail-threshold positive control; confirm via `nodetool` or JMX read of `getBatchSizeWarnThresholdInKiB` that the intended value was in effect.

**B4. Risks and cleanup.** Large batches can OOM a 2 GiB heap; keep to 20 MiB with 4 clients max, stop on `OutOfMemoryError`. All data, commitlog, hints, batchlog and saved caches under `/local/scratch/node1` only; never in the shared source tree; check `df` before each run. Cleanup: stop Cassandra and clients, `pgrep -f "CassandraDaemon|cqlsh|jmxterm"` must be empty, then `rm -rf /local/scratch/node1 /local/scratch/c509`.

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cql3/statements/BatchStatement.java
- src/java/org/apache/cassandra/config/Config.java (lines 329-332)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 625-640, 2056-2100)
- src/java/org/apache/cassandra/service/StorageService.java (lines 6828-6882)
- src/java/org/apache/cassandra/service/StorageServiceMBean.java (grep)
- src/java/org/apache/cassandra/db/IMutation.java
- src/java/org/apache/cassandra/db/partitions/PartitionUpdate.java (lines 346-349)
- src/java/org/apache/cassandra/db/rows/BTreeRow.java (dataSize)
- src/java/org/apache/cassandra/db/rows/AbstractCell.java (dataSize, grep)
- conf/cassandra.yaml (lines 652, 1044, 1836-1846)
- test/unit/.../StorageServiceTest.java, DatabaseDescriptorTest.java (grep only)

## D. Stage-4 feedback

### D1. Step-0 amendments, 2026-10-26 (before any harness run or reading)

Made by the stage-4 audit ([results file](../../stage4-runtime-verification/results/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md) section 1). None depends on a reading. The claim (B1), the main predictions and the main conclusion rows are unchanged; amendments add instruments, tolerances, one extra arm and rows for outcomes the tables did not cover.

| # | Where | Amendment | Reason |
|---|---|---|---|
| A1 | B2e step 2, B2d | Unit tier sends the batches through CQLTester's in-process native server (`requireNetwork()`), protocol v4 `SimpleClient`, LOGGED `BatchMessage`, test class in `org.apache.cassandra.transport`. Warnings are read from the response; dataSize, threshold and branch from Byteman rules at `verifyBatchSize` entry and throw (`siz`, `rej`). | `CQLTester.execute` runs `QueryProcessor.executeInternal`, which calls `BatchStatement.executeLocally` -> `executeInternalWithoutCondition` (`BatchStatement.java:559-577`); that path never calls `verifyBatchSize` (`:439`, only in `executeWithoutConditions`). The filed procedure would never have produced a warning. |
| A2 | B2d(4), B2f | Heap reading: coordinator thread allocation inside `BatchStatement.execute` (Byteman `bst`, `ThreadMXBean.getThreadAllocatedBytes`), not a post-GC heap delta. Tolerance: medians per batch size differ by at most 10 % or 16 KiB, whichever is larger. | A post-GC delta in a JVM that also runs the test framework is noise at the 1 MiB scale, and the check's cost is per request; allocation per request is deterministic. The 16 KiB allowance covers the WARN branch's own message and `HashSet`. |
| A3 | B1, B2f, B2g, B3f, B3g | Claim read for warn <= fail. Added inversion arm `inv` in both tiers (unit: warn 200 KiB, fail 10 KiB, 20 KiB batch; cluster: fail 20 KiB, warn set live to 200 KiB, 50 KiB batches) with prediction (accepted, no warning, no rejection) and rows. It is a recorded finding about the fail threshold, not a verdict row for this claim. | `:340` gates `:352`: with warn > fail a batch between the two is never checked against fail. The filed A3 mentions this only for sizes above both. |
| A4 | B2g control row, B2h, B3f | Positive control keeps warn (5 KiB) below fail (10 KiB unit, 20 KiB cluster). | With warn >= fail the control batch is not checked at all (A3), so the control would not move for a reason that has nothing to do with the instruments. |
| A5 | B2e step 5 | CAS batch step dropped. | CAS batches are single-partition (`BatchStatement.java:229-239`): the step cannot separate the CAS bypass from the `:334` early return. The bypass stays a source-level statement (A3 of the file), not a measured one. |
| A6 | B3a, B3c, B3f | Large-batch run: UNLOGGED batches of 20 MiB, protocol v4. Yaml adds `native_transport_max_message_size: 64MiB`, in-flight limits 128MiB (both), `native_transport_max_frame_size: 64MiB`. Expected counts fixed: at warn 5 KiB, 2 x (2000 + 20) WARN lines per lifetime. | The derived message-size default is min(`max_mutation_size` 16 MiB, in-flight limits) = 16 MiB (`DatabaseDescriptor.java:3237-3245`), so a 20 MiB request would be discarded before the check. A LOGGED 20 MiB batch would also exceed `max_mutation_size` as one batchlog mutation. Lessons: v5 large requests leave direct buffers. |
| A7 | B3d, B3f, B3g | "Peak heap" = largest post-collection occupancy in the GC log (`-Xlog:gc`) inside the arm's time window; disk = bytes in the data directory after `nodetool flush`; write count from `nodetool tablestats`; coordinator allocation from `bst`. Bands: equal within 10 %, refuted above 25 % tracking the knob, Not confirmed between (new row). "Limit never reached" means dataSize above the warn value, not heap fill (row text amended). | A fixed-size G1 heap peaks at whatever the collector allows regardless of the workload; the warn limit is a size threshold, not a heap level. The filed bands left 10-25 % without a row. |
| A8 | B3a, B3b, B3c, B3e | Paths: working tree and tmpfs under `~/s4-b9-bs*` and `/dev/shm`. Node lifetimes: L1 yaml warn 5 KiB (live switch to 90000KiB by JMX after the repeat runs), L2 yaml warn 90000KiB, L3 control (warn 5 KiB, fail 20 KiB, then `inv`). One client connection, one batch in flight (not 4 clients). | `/local/scratch` does not exist on the nodes; per-arm Byteman lines are joined by time window and need one request at a time. |
| A9 | A1, A5 | Citation nits, no consequence: the DatabaseDescriptor setter is `:2084-2087` (filed `:2085-2088`); the unit tests that touch the setters are `StorageServiceTest.java:291-310` and `DatabaseDescriptorTest.java:342-354`. All other load-bearing lines were re-read and hold: `BatchStatement.java:331, 334, 340, 352, 358, 360-365, 434, 439`; `Config.java:329-330`; `conf/cassandra.yaml:1840, 1844`; `DatabaseDescriptor.java:631, 2059`; `IMutation.java:63`; `PartitionUpdate.java:346`. | spot-check against the pinned tree |

### D2. Stage-4 result, 2026-10-26

Results: [`results/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md`](../../stage4-runtime-verification/results/batch_size_warn_threshold-verifyBatchSize-size--autonomous.md). Run 1 only, no run 2. Outcome class **true negative** (estimate `negative`, effect `does not cap`).

- **Unit: Refuted (does not cap).** Every prediction on acceptance held (warning at warn 1 and 5 KiB only, no throw, all rows written, dataSize identical), but the coordinator's allocation inside `BatchStatement.execute` is 20 % (20 partitions) and 19 % (200 partitions) higher in the arms where the warn branch runs, outside the band of B2f.
- **Cluster: Not confirmed (does not cap).** warn 5 KiB vs 90000 KiB (yaml, and live over JMX): 4040 vs 0 WARN lines, identical rows (100,000 and 409,600 per phase), identical data-directory bytes (within 0.03 %, 1.08 GB), all 40 batches of 21 MiB and 4000 batches of 53.6 KiB accepted at warn 5 KiB; coordinator allocation +14 % (21 MiB batches) to +20 % (53.6 KiB batches), stable across repeats and gone after the live switch.
- **The claim B1 needs one more word:** the warn value does not *reduce* memory or disk; it adds about 1.1 to 2 KB of transient coordinator allocation per mutation once exceeded (likely the per-mutation `TableMetadata.toString()` at `BatchStatement.java:342-346`; inferred, not isolated). A3 should say "allocates more", not "the same".
- **A3's inversion note is confirmed and is a bypass of the fail threshold:** with warn above fail (200 KiB vs 10 / 20 KiB) a batch over the fail threshold is accepted, silently (unit 20/20, cluster 200/200). Nothing validates warn <= fail. Carry to Target 3 and to a documentation candidate (the yaml says fail is 10x warn but does not require it).
- **Positive control (fail threshold, warn kept below it):** unit 20/20 rejected, 0 rows; cluster 2000/2000 rejected, 0 writes, 100 B on disk against 106 MB for the same accepted workload.
- **Upstream candidates:** warn above fail disables the fail check without a message (add a startup validation or move the fail test out of the warn gate); `verifyBatchSize` formats a table name per mutation before it needs only the distinct tables.

