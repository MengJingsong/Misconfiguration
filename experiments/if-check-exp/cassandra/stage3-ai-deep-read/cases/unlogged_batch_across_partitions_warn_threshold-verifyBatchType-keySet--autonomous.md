<!-- file: cases/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.md -->
# unlogged_batch_across_partitions_warn_threshold — verification solution  <!-- file: cases/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/cql3/statements/BatchStatement.java:388` |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code CLI, 2026-10-26 |
| Estimate | `negative`: the threshold only triggers a log line and a client warning; the batch is executed regardless, so it bounds neither heap nor disk. |
| Ground | The check at line 388 has no reject, truncate or throttle branch (lines 388-395); execution continues at `BatchStatement.java:442-444`. The only memory-bounding batch limit is the separate `batch_size_fail_threshold` (`BatchStatement.java:352-359`), which applies to serialized size, not to partition count. |

## A. Constraint trace

**A1. The constraint.** `unlogged_batch_across_partitions_warn_threshold`; configuration entry. Declared at `src/java/org/apache/cassandra/config/Config.java:334` (`public Integer ... = 10`), exposed through `DatabaseDescriptor.getUnloggedBatchAcrossPartitionsWarnThreshold()` (`DatabaseDescriptor.java:2079-2082`). Unit: number of distinct partition keys in one batch. Default 10, a literal in Config.java and repeated in `conf/cassandra.yaml:1847` and `conf/cassandra_latest.yaml:1826`. Set via the yaml key; no JMX setter seen in the tree (only a getter in DatabaseDescriptor), so a change needs a restart.

**A2. What it caps.** Nothing in memory or disk. The compared quantity is `keySet.size()`, the count of distinct `DecoratedKey`s across all mutations of an UNLOGGED batch (`BatchStatement.java:373-384`).

**A3. Mechanism.**
1. `executeWithoutConditions` (`BatchStatement.java:434`) builds mutations, then calls `verifyBatchSize` (:439) and `verifyBatchType` (:440), then `StorageProxy.mutateWithTriggers` (:443).
2. `verifyBatchType` (:369) returns immediately if the batch is logged or has at most one mutation (:371).
3. Otherwise it collects partition keys and table names (:373-384).
4. If `keySet.size() > threshold` (:388) it emits a rate-limited WARN (`NoSpamLogger`, once per minute, :390) and a `ClientWarn` (:393). Nothing else.
Outcome at the limit: warning only. There is no exception, so there is no bypass to find: the limit is never enforced. Overshoot is unlimited by this setting. Batch memory is bounded only by `batch_size_fail_threshold` (default 50KiB, `Config.java:332`; `BatchStatement.java:349-358`), checked in `verifyBatchSize` on `IMutation.dataSize`. Conditional batches (`hasConditions`, :422) return before this path and are never checked by it, and virtual-table batches (:425) skip it too.

**A4. Other consumers.** Batch payload on the coordinator heap (the parsed statements, the mutations), write-path memtables, commit log and hints are all consumers outside this constraint's control. The size-based thresholds and `native_transport_max_request_data_in_flight` bound them instead.

**A5. Evidence beyond the source.** In-code comment at :386-387 cites CASSANDRA-11529 (log only above a key threshold) and CASSANDRA-9282 (original warning). The yaml comment (`conf/cassandra.yaml:1846`) says "Log WARN". No further sources.

## B. Verification solution

**B1. Claim under test.** Raising or lowering `unlogged_batch_across_partitions_warn_threshold` changes only whether a warning is emitted; it does not change the coordinator heap or disk used by an unlogged batch, and a batch with more partitions than the threshold is still accepted and written in full (subject to the size fail threshold).

### B2. Unit tier

**B2a. Environment and build.** JDK 11, Ant. Copy the tree to local disk (`rsync -a ~/cassandra-5.0.9/ /local/c509/`), `ant jar` there. Write a small JUnit test in a copy of the tree (for example `test/unit/org/apache/cassandra/cql3/UnloggedBatchWarnTest.java`, extending `CQLTester`) and run `ant testsome -Dtest.name=UnloggedBatchWarnTest`. JVM options: the default `test` settings, `-Xmx1g`.

**B2b. Knobs.** `DatabaseDescriptor.getRawConfig().unlogged_batch_across_partitions_warn_threshold` set in-test to 1, 10 (default), 1000. Also `batch_size_warn_threshold` and `batch_size_fail_threshold` both fixed at a large value (1000KiB via `DatabaseDescriptor.setBatchSizeWarnThresholdInKiB(1000)` and `setBatchSizeFailThresholdInKiB(1000)`) so only partition count differs. *[Amended 2026-10-26, A1: the size check in `verifyBatchSize` runs only when the batch is larger than the warn threshold (`BatchStatement.java:338-340`; default 5KiB), so the warn threshold must be set with the fail threshold, here and in the control.]* Values bracket the count of keys used (N=50).

**B2c. Workload.** Create `ks.t (k int PRIMARY KEY, v text)`. Execute one `BEGIN UNLOGGED BATCH` of N=50 inserts to 50 distinct keys (about 50 x 100 B = 5 KB, below the fail threshold) through `QueryProcessor`/`executeFormattedQuery`. 50 exceeds thresholds 1 and 10 and not 1000. Also run N=5 as a below-threshold reference, and a LOGGED batch of 50 as a control.

**B2d. Observables and instruments.** (1) `ClientWarn.instance.getWarnings()` after each batch, for the text "Unlogged batch covering 50 partitions"; (2) a log appender or log file for the WARN; (3) row count `SELECT count(*)` after the batch; (4) heap used via `Runtime` totalMemory-freeMemory after a forced GC before and after (coarse); (5) memtable live size from `ColumnFamilyStore.metric.allMemtablesLiveDataSize`. Not directly observable: coordinator-transient allocation of the batch.

**B2e. Procedure.** For each threshold in {1, 10, 1000}: set it; clear warnings; run the N=50 batch; record warnings, the log line, count(*), memtable size; repeat the N=5 batch and the LOGGED control. Run the 50-batch twice within one minute to confirm `NoSpamLogger` suppresses the second log line while `ClientWarn` still fires.

**B2f. Predictions.** Thresholds 1 and 10: one warning "covering 50 partitions", count(*) = 50. Threshold 1000: no warning, count(*) = 50. Memtable live data size after the batch is the same within 5% across all three thresholds (same data written). N=5: no warning at 10 or 1000, a warning at 1 only if keys > 1 (yes, 5 > 1). The LOGGED control never produces this warning.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| Warning appears only when keys > threshold, count(*) = 50 in all cases, memtable size equal across thresholds | Claim confirmed: warn-only, no cap |
| Batch rejected or truncated (count < 50, exception) when keys > threshold | Claim refuted: the threshold enforces something |
| Memtable/heap size differs materially (over 5%) with threshold | Claim refuted: usage follows the knob |
| Usage flat while the positive control moves (with `batch_size_warn_threshold` and `batch_size_fail_threshold` both lowered to 1KiB the same batch is rejected with "Batch too large", count = 0) *[Amended 2026-10-26, A1: warn threshold added]* | Claim confirmed, control proves the harness can see a binding cap |
| No warning at thresholds below 50, or the positive control does not reject | Not confirmed: limit not reached or harness faulty |

**B2h. Controls.** Positive control: `batch_size_warn_threshold` = 1KiB and `batch_size_fail_threshold` = 1KiB with the same batch (known to throw at `BatchStatement.java:358`; the fail check is reached only above the warn threshold, A1). Negative controls: N=5 batch and LOGGED batch. Identical payload bytes across thresholds so only the count knob changes. Fresh table per run.

### B3. Cluster tier

**B3a. Environment and build.** One node (three optional) built from the local copy (`ant jar`), data, commit log and hints directories on local disk of known size (at least 20 GB free), `-Xms2g -Xmx2g`, JDK 11, G1. Config changes via `cassandra.yaml`: `unlogged_batch_across_partitions_warn_threshold`, `batch_size_fail_threshold: 1000KiB`, `batch_size_warn_threshold: 1000KiB` so the size checks stay out of the way. Client protocol 4 (the v5 large-request path, a batch above 131,071 B, leaves direct buffers unreturned; HANDOFF lessons). *[Amended 2026-10-26, A3: protocol 4.]*

**B3b. Knobs.** Threshold 1, 10, 100000, one node restart each (restart is required). Positive control run: `batch_size_warn_threshold: 10KiB` and `batch_size_fail_threshold: 20KiB` with the 10 setting (the batch is about 115 KB, above both; with the warn threshold left at 1000KiB the fail check is never reached, A1). *[Amended 2026-10-26, A1: warn threshold added.]*

**B3c. Workload.** `cassandra-stress` or a Python driver loop: 8 client threads, each sending UNLOGGED batches of 500 distinct-partition inserts (value 200 B, about 100 KB payload per batch, below the 1000KiB fail threshold), 250 batches per thread (8 x 250 x 500 = 1,000,000 rows per run, about 200 MB logical) *[Amended 2026-10-26, A2: the filed 2000 batches per thread gives 8,000,000 rows and about 1.6 GB, contradicting the stated 1,000,000 rows, B3f and B4]*. 500 keys exceeds thresholds 1 and 10 and not 100000. Duration about 5 to 10 minutes per setting.

**B3d. Observables and instruments.** Heap used and GC time via `jstat -gcutil <pid> 1000`; memtable size via `nodetool tablestats ks.t` ("Memtable data size"); on-disk size via `du -sb` of the data and commitlog directories and `nodetool tablestats` "Space used (live)"; warning count via `grep -c "Unlogged batch covering" system.log`; client warnings from the driver response. Not observable: per-request transient heap on the coordinator, except through the GC trace.

**B3e. Procedure.** For each threshold: wipe data dirs; set yaml; start node; create schema; start `jstat` and a `du` sampler at 1 s; run the workload; `nodetool flush`; record readings; stop node; verify with `pgrep -f CassandraDaemon` that none remains. Then the control run.

**B3f. Predictions.** Rows written equal 1,000,000 in every run (`SELECT count(*)` or `nodetool tablestats` partition estimate). Peak heap, GC time and disk bytes agree across the three thresholds within run-to-run noise (about 10%). System.log has WARN lines (at most one per minute) for thresholds 1 and 10 and none for 100000; client warnings present for 1 and 10 only. Control run: the batches fail with "Batch too large", rows written 0.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Heap, memtable and disk the same across thresholds (within 10%), all rows written, warnings differ | Claim confirmed |
| Fewer rows, errors, or lower heap/disk when threshold is low | Claim refuted: usage follows the knob |
| Usage flat while the size-threshold control moves (rows 0, writes rejected, lower disk) | Claim confirmed with a working positive control |
| No warnings at threshold 1, or the control does not reject | Not confirmed: limit not reached or the control did not move |

**B3h. Controls.** Same data volume, same schema, wiped state each run, same JVM options; positive control via `batch_size_fail_threshold`; one repeat of the middle setting to measure run-to-run noise.

**B4. Risks and cleanup.** Disk: about 1 GB per run on local disk, delete data/commitlog/hints dirs afterwards. Build only in the local copy, never the shared tree. Stop every node, `jstat` and stress process and check with `pgrep -fl 'CassandraDaemon|jstat|stress'`. WARN log volume is bounded by `NoSpamLogger` (1 per minute).

## C. Sources read

- /users/jason92/writeup-A/playbook-autonomous.md
- /users/jason92/writeup-A/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/cql3/statements/BatchStatement.java (lines 83-90, 320-450)
- src/java/org/apache/cassandra/config/Config.java (grep, lines 329-334)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (lines 2075-2084)
- conf/cassandra.yaml (lines 1840-1847), conf/cassandra_latest.yaml (grep)

## D. Stage-4 feedback

Audit amendments (stage 4, 2026-10-26, before run 1):
- A1. The size check in `verifyBatchSize` runs only when `size > batch_size_warn_threshold` (`BatchStatement.java:338-340`; default 5KiB); the fail branch (:349-358) sits inside it. The filed positive control lowered only the fail threshold (unit 1KiB, cluster 20KiB) while the cluster yaml kept warn at 1000KiB, so the control would not have rejected anything. B2b, B2g, B2h, B3b: warn threshold set with the fail threshold (non-control arms 1000KiB/1000KiB; unit control 1KiB/1KiB; cluster control warn 10KiB, fail 20KiB). The control's expected outcome (rejected, rows 0) is unchanged.
- A2. B3c: 2000 batches per thread x 8 threads x 500 = 8,000,000 rows, not the stated 1,000,000; set to 250 batches per thread.
- A3. B3c: client protocol 4 (batch payload of about 115 KB is near the 131,071 B large-message threshold).
- Prediction tables B2f, B2g (wording of the control row only), B3f and B3g otherwise unchanged. Frozen hashes: see the results file.

Stage-4 result (2026-10-26, `stage4-runtime-verification/results/unlogged_batch_across_partitions_warn_threshold-verifyBatchType-keySet--autonomous.md`; run 1, no run 2): unit tier **Confirmed**, does not cap; cluster tier **Confirmed**, does not cap. Outcome class: true negative.
- Unit: warning only above the key count (thresholds 1, 10, 1000 with 50 keys: 1, 1, 0 warnings), count(*) 50 and memtable live data size 7,450 B at every threshold; the size control (warn = fail = 1 KiB) rejected the same batch.
- Cluster (1,000,000 rows per arm, thresholds 1, 10, 100000, a repeat of 10): all rows written at every threshold, client warning on 2000 of 2000 batches at 1 and 10 and none at 100000, one WARN log line (NoSpamLogger); heap peak within 7%, memtable data size after load within 0.3%, space live after flush and data dir within 0.2%; the control (warn 10KiB, fail 20KiB) rejected 2000 of 2000 batches, 0 rows.
- The estimate stands: the key-count threshold bounds neither heap nor disk; only the size thresholds do, and `verifyBatchSize` runs its fail check only above `batch_size_warn_threshold` (:338-340).
- Runbook defects: R1 `SELECT count(*)` over 1,000,000 partitions timed out at the default read timeouts (harness fix: node timeouts 600s; the cluster tier restarted); R2 `jstat` cannot attach (node runs with `-XX:+PerfDisableSharedMem`; heap by `jcmd GC.heap_info`). Neither changed B3f or B3g.
- Note for the filing: the WARN log line is rate-limited (one per minute, shared by all batches), so a log count says little; the client warning fires on every batch.
