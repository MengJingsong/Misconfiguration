# BatchlogManager replay page budget (`DEFAULT_PAGE_SIZE` = 128 rows, 4 MiB target) — verification solution  <!-- file: cases/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BatchlogManager.java:254`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L254) (`averageRowSize <= 0`) and `:296#1` (`++positionInPage == pageSize`). Both targets share this constraint, so this one file covers both |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available), 2026-10-26, stage-3 autonomous, Band D triage |
| Estimate | `positive`, with a known overshoot. The count cap holds every time: replay never keeps more than `pageSize` ≤ 128 deserialized batches at once (`:296`), so replay heap follows `pageSize`. The byte target (about 4 MiB per page, `:257`) holds only when the SSTable statistics match the batches being replayed. If they are memtable-only, `:254` falls back to 128 whatever the batch size. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** A compound hard-coded constant: the batchlog replay page size.
- `DEFAULT_PAGE_SIZE = 128` (rows, meaning batches), declared at [`BatchlogManager.java:91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L91) (package-private `static final int`).
- An inline byte budget of `4 * 1024 * 1024` (4 MiB) at [`BatchlogManager.java:257`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L257).
- The page size is computed once per replay run at `:216` by `calculatePageSize` (`:251-258`): if `store.getMeanPartitionSize() <= 0`, use 128 (`:254-255`). Otherwise use `max(1, min(128, 4 MiB / meanPartitionSize))` (`:257`).
- `getMeanPartitionSize()` ([`ColumnFamilyStore.java:3123-3134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3123-L3134)) averages the estimated-partition-size histograms of the **canonical SSTables only**. It returns 0 if `system.batches` has no SSTables, and memtable contents are never counted.
- Unit: rows (batches) and bytes. Neither part can be set: there is no yaml key, `-D` property or JMX setter. Changing either needs a code change and a restart. The only lever an operator has is indirect: whether and what `system.batches` has flushed (`nodetool flush system batches`), and the batch size (`batch_size_fail_threshold`, `conf/cassandra.yaml:1844`, checked in `BatchStatement.verifyBatchSize`, [`BatchStatement.java:331-359`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L331-L359)).


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** Heap held by one batchlog replay pass on the `BatchlogTasks` thread. Two things are held:
- The materialized page of raw rows (`id`, `mutations list<blob>`, `version`). `UntypedResultSet.FromPager` fetches `pageSize` rows and turns them into a list (`src/java/org/apache/cassandra/cql3/UntypedResultSet.java:227-231`).
- Up to `pageSize` `ReplayingBatch` objects in `unfinishedBatches` (`BatchlogManager.java:263,280`). Each holds deserialized `Mutation`s (`:341,392-418`) and its replay handlers (`:344,365`).

The quantities compared are `positionInPage` against `pageSize` (`:296`, a count of batch rows), and `averageRowSize` against 0 (`:254`). The 4 MiB divisor sets the byte target per page.

**A3. Mechanism.**
1. `replayFailedBatches` (`:200`) runs every 10 s (`:90,114-117`), or on demand through `nodetool replaybatchlog` (`src/java/org/apache/cassandra/tools/nodetool/ReplayBatchlog.java`, `NodeProbe.replayBatchlog` → `forceBatchlogReplay`, [`BatchlogManager.java:183-186`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L183-L186)).
2. It computes `pageSize = calculatePageSize(store)` once (`:216`) and opens a paged internal query using that page size (`:220-223`, `QueryProcessor.executeInternalWithPaging`, [`QueryProcessor.java:573-602`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L573-L602)).
3. `processBatchlogEntries` (`:260-317`) iterates the rows. For each row it builds a `ReplayingBatch`, which deserializes all of its mutations (`:277,346-352,392-405`), then sends the replays (`:365`) and rate-limits (`:367`).
   - If any replay handler was created, the batch is added to `unfinishedBatches` (`:278-281`).
   - Otherwise the batch is removed immediately (`:284`) and nothing is retained.
4. **`:296` check.** When `++positionInPage == pageSize`, `finishAndClearBatches` waits for every handler and hints the failures (`:319-330`, `:372-390`), then clears the list (`:329`). That frees the page's `ReplayingBatch`es before the next row, and so before the next page fetch. The comment at `:298-299` gives the intent: "To avoid keeping more than a page of mutations in memory".
5. `:306` drains the last, partial page after the loop. It does not enforce the limit.
6. **`:254` check.** Its outcome decides which bound applies. With no SSTables, or a mean of 0, the page is 128 rows whatever the row size. Otherwise the page aims for about 4 MiB.

Bypasses and overshoots:
- **(a) Memtable-only batchlog.** Batches live briefly and are usually deleted before a flush. `system.batches` has `memtable_flush_period` = 1 h and `gc_grace_seconds` = 0 (`src/java/org/apache/cassandra/db/SystemKeyspace.java:211-221,527-533`). The mean is then 0 and the page is 128 × the batch size. Example: 128 × 1 MiB = 128 MiB of raw rows plus about the same again deserialized, against a 4 MiB target.
- **(b) Stale or diluted statistics.** The mean comes from whatever SSTables exist, which may be old small batches or tombstone-only partitions, not the batches about to be replayed. Small flushed batches next to large unflushed ones still give 128.
- **(c) Raw rows of the current page.** These stay reachable through `FromPager.currentPage` until the next page is fetched, in addition to the `ReplayingBatch`es.
- **(d) Per-pass sets.** `replayedBatches` and `hintedNodes` grow for the whole pass, not per page (`:265-266,325`), but each entry is small (a UUID).
- **(e) Per-batch bound.** A single batch can be as large as `max_mutation_size` (default `commitlog_segment_size/2` = 16 MiB, [`DatabaseDescriptor.java:898-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L901)). The worst case under the count cap is therefore about 128 × 16 MiB × 2 (raw plus deserialized).

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — A3, derived from the source.** (i) **When replay runs.** `BatchlogManager.start()` ([`BatchlogManager.java:111-118`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/batchlog/BatchlogManager.java#L111-L118)) is called once, from `StorageService` when the node has joined ([`StorageService.java:1238`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L1238), next to the hints dispatch). It schedules `replayFailedBatches` with an initial delay of `RING_DELAY_MILLIS` (30 s by default, property `cassandra.ring_delay_ms`) and then every 10 s after the previous pass ends (`:90`, `scheduleWithFixedDelay`). `forceBatchlogReplay` (MBean `org.apache.cassandra.db:type=BatchlogManager`; `nodetool replaybatchlog` → `NodeProbe.replayBatchlog`, [`NodeProbe.java:2319-2323`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tools/NodeProbe.java#L2319-L2323)) and `performInitialReplay` (tests) submit the same method to the same single-thread executor `BatchlogTasks` and wait for it (`:183-198`). So a forced pass runs after any pass already in progress, and passes never overlap. A plain unit JVM never calls `start()`, so only explicit passes run there. A pass returns at once if the token ring is empty (`:206-211`); the unit setup fills it. (ii) **Which batches a pass reads.** Rows with `token(id) > token(lastReplayedUuid)` and `token(id) ≤ token(maxAtUnixMillis(now − getBatchlogTimeout()))` (`:214-223`). `system.batches` uses `LocalPartitioner(TimeUUIDType)` ([`SystemKeyspace.java:219`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/SystemKeyspace.java#L219)), so token order is batch-id time order. `getBatchlogTimeout()` returns `BATCHLOG_REPLAY_TIMEOUT`, which is 2 × `write_request_timeout` = 4 s at the default 2000 ms (`:96`, `:332-335`). `lastReplayedUuid` is an instance field, set to the limit after every pass (`:98`, `:225`). Within one JVM, a later pass therefore skips any batch whose id is older than an earlier pass's limit, so the unit tier must reset it between cases (B2c amendment). A pass deletes the replayed batches only after the whole pass (`:312-313`). The page bound therefore concerns the decoded batches and the materialised raw page, not the contents of `system.batches`. (iii) **What `getMeanPartitionSize()` returns.** It sums `mean() × count` over the estimated-partition-size histograms of the canonical SSTables and divides by the total count ([`ColumnFamilyStore.java:3123-3134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ColumnFamilyStore.java#L3123-L3134)). With no SSTable it returns 0, and memtable contents never count. Each SSTable's `mean()` is the ceiling of the count-weighted mean of the **upper bucket offsets** ([`EstimatedHistogram.java:235-258`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/EstimatedHistogram.java#L235-L258)). The offsets start at 1 and grow by ×1.2, rounded (`:91-108`; 155 buckets, [`MetadataCollector.java:66-70`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/metadata/MetadataCollector.java#L66-L70)). For identical partitions, the mean is therefore the upper offset of their bucket:
  - a 64 KiB batch row (≈ 65.6 kB serialized, bucket (61,214, 73,457]) gives 73,457, so `pageSize` = ⌊4,194,304 / 73,457⌋ = **57**;
  - a 1 MiB batch row (≈ 1,048,8xx B, bucket (943,127, 1,131,752]) gives 1,131,752, so `pageSize` = **3**;
  - any row up to 16,400 B gives **128**.

  The bucket bounds leave more than 4 kB (64 KiB rows) and more than 80 kB (1 MiB rows) of margin for serialization overhead. Because the mean is an upper bound of the row size, `pageSize × (decoded bytes per batch) ≤ 4 MiB` whenever the statistics describe the replayed batches. `nodetool tablestats` "Compacted partition mean bytes" is the same sum with integer division ([`TableMetrics.java:729-741`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/metrics/TableMetrics.java#L729-L741)). (iv) **Read thresholds do not apply.** The replay read is internal (`QueryProcessor.executeInternalWithPaging`, `:592-602`), and `trackWarnings()` is set only on the client path ([`SelectStatement.java:334-335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L334-L335)). The unit yaml's `local_read_size_fail_threshold: 8192KiB` (`test/conf/cassandra.yaml:63-67`) therefore cannot abort an 8 MiB page. (v) **Every decoded batch of a page is held until `:296`.** On a single node each mutation gets a handler with no remote contacts (`blockFor` = 0, `:536-540`). `replay` then returns the number of mutations (> 0), and the batch is added to `unfinishedBatches` (`:278-281`). The raw rows stay referenced by `FromPager.currentPage` ([`UntypedResultSet.java:213-231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L213-L231)) until the next page is fetched, and that happens only after `:296` has cleared the list. With pages of P rows of S bytes, replay holds about P × S raw plus up to P × S decoded. (vi) **How the cluster design keeps batches until replay without changing the replay path.** A client LOGGED batch with more than one partition is stored in the coordinator's batchlog ([`StorageProxy.java:1223`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1223), `:1286-1306`). After all its mutations are acknowledged, `BatchlogCleanup` deletes it through `asyncRemoveFromBatchlog` (`:1205-1207`, `:1308-1320`). Rule 1 returns at the entry of `asyncRemoveFromBatchlog` only. The replay path deletes with `BatchlogManager.remove` directly (`:284`, `:291`, `:313`) and is not touched. The method's other caller, the view path at `:1041`, is not used (no views). Rule 2 changes the value of `getBatchlogTimeout()` only while the flag file is absent. Its callers are `:214` and decommission ([`StorageService.java:5376`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L5376), not used). Once the flag exists the method returns its own value, so the pass that reads the batches runs unmodified code. Rules 3 and 4 only print. Reason: the audit needs these derivations (when replay runs, what the mean returns, how batches are kept) for exact predictions.

**Amendment 2026-10-26 (stage 4 unit run 1, runbook defect 1; Claude Opus 5.5, claude-opus-5-5) — A3, correction of the A3 amendment's item (iv).** Item (iv) is wrong for the coordinator read-size check. `trackWarnings()` governs only the local read-size and row-index checks. The coordinator read-size check, `SelectStatement.maybeFail`/`maybeWarn` ([`SelectStatement.java:1040-1075`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L1040-L1075), called per row from `processPartition`, `:1132`), runs inside `select.process`. That method is also called by the internal pager ([`UntypedResultSet.java:230`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L230)), and it depends only on `options.isReadThresholdsEnabled()`, which comes from `DatabaseDescriptor` ([`QueryOptions.java:247-250`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L247-L250)). With the unit yaml (`read_thresholds_enabled: true`, `coordinator_read_size_fail_threshold: 4096KiB`, `test/conf/cassandra.yaml:63-67`), a replay page over 4 MiB reaches `maybeFail`. Its message builder `loggableTokens` then throws `IndexOutOfBoundsException` on the internal statement's unbound markers, and the replay pass fails (unit run 1, attempt 0, all four cases). A node has read thresholds disabled by default ([`Config.java:526`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L526)), so the replay path under test is the one with thresholds off. The stage-3 observation that a node with `read_thresholds_enabled: true` and a coordinator fail threshold below one replay page cannot replay its batchlog is recorded in section D; it is not tested here. Reason: a wrong source statement, found when the unit tier could not run as written; it does not depend on any reading of the page budget.

**A4. Other consumers.** Other heap users during replay:
- Memtables of the replayed tables. `mutation.apply()` runs inline for locally owned keys (`:485-486`).
- Outbound `MUTATION_REQ` messages for remote replicas (`:507-509`).
- Hints written for down or timed-out replicas (`:443,499`). These go to hint buffers and disk under the hints subsystem's own limits.
- The `system.batches` memtable itself.

None of these is governed by `pageSize`.

**A5. Evidence beyond the source.**
- `test/unit/org/apache/cassandra/batchlog/BatchlogManagerTest.java:130-202` stores batches, flushes `system.batches` ("see CASSANDRA-6822") and replays them. It does not test `calculatePageSize`.
- No test references `calculatePageSize` or `DEFAULT_PAGE_SIZE` (grep of `test/`).
- No other evidence was used.

## B. Verification solution

**B1. Claim under test.**
- (i) During one batchlog replay pass, the number of live `ReplayingBatch` objects never exceeds `pageSize`, and `pageSize` ≤ 128. Replay heap therefore grows with `pageSize` × the batch size.
- (ii) `pageSize` follows `floor(4 MiB / mean SSTable partition size of system.batches)` when SSTables exist, and is 128 when `system.batches` is memtable-only. In the memtable-only case the bytes held per page exceed 4 MiB by about `128 × S / 4 MiB`, so the byte target is not a cap.
- The claim is wrong if more than `pageSize` batches are live at once, or if heap during replay does not drop when `pageSize` drops (flushed versus unflushed).

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B1, why the arms answer "does it cap usage?", and the two findings.** Neither `DEFAULT_PAGE_SIZE` nor the 4 MiB divisor can be set (A1). The design therefore varies the only inputs of `calculatePageSize`, which are whether `system.batches` has SSTables and the size of the rows in them, while the batches to be replayed stay the same. Each pair of arms differs in one condition:
- Unit A vs B and cluster A vs B: the same batches, flushed or not. This moves the effective page size from 128 to 57 (unit) and from 128 to 3 (cluster).
- Unit B vs D: both flushed, 64 KiB vs 1 MiB batches. This tests that the page size follows the row size.
- Unit and cluster C: a small-row SSTable next to large unflushed batches. This tests the statistics source.

Every arm replays at least two pages of batches, so the bound is driven to its limit and past it. This is a dose-response on the effective page size instead of on a knob: three values in the unit tier (128, 57, 3) and two on the node (128, 3).

The results are reported as **two findings, kept apart**:
1. **Count cap.** At most `pageSize` ≤ 128 decoded batches (`ReplayingBatch`es) are held at once, and the heap held by replay follows `pageSize`. The count is read as the largest list size at `finishAndClearBatches` and, on the node, as live `ReplayingBatch` instances.
2. **The 4 MiB byte target.** Decoded bytes per page are ≤ 4 MiB when the SSTable statistics describe the batches being replayed (unit B and D, cluster B). They exceed 4 MiB, by a factor of `128 × S / 4 MiB`, when the statistics do not (memtable-only A, diluted C).

Finding 1 can confirm "caps". Finding 2 decides whether the byte target is a cap or "caps only on some paths (bypass)". Reason: the README requires the design for an un-settable constant to say why its arms answer the core question, and the filed text did not separate the two findings.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant.
- Clone to local disk: `git clone --branch cassandra-5.0.9 --depth 1 <shared-clone-path> /local/c509-bl && cd /local/c509-bl && ant jar build-test`. The shared clone is never built in.
- Add one test file: `/local/c509-bl/test/unit/org/apache/cassandra/batchlog/BatchlogPageBudgetTest.java`. It is in package `org.apache.cassandra.batchlog` so it can call the package-private `calculatePageSize` and `DEFAULT_PAGE_SIZE`.
- Use `@RunWith(org.jboss.byteman.contrib.bmunit.BMUnitRunner.class)`. This is the same mechanism as `test/unit/org/apache/cassandra/locator/AssureSufficientLiveNodesTest.java:53-71`; Byteman 4.0.20 is already a test dependency (`.build/parent-pom-template.xml:40`).
- No extra JVM options are needed. The test config `test/conf/cassandra.yaml` has `commitlog_segment_size: 5MiB`, so `max_mutation_size` is 2.5 MiB and every batch below must stay under 2.5 MiB.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2a, this host.** Run clone `$W/cassandra-run28` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run28`, a full clone at `b5f2a54210`, then `ant -Dlocal.repository=$W/m2 build-test`), macOS arm64, JDK 11.0.32.1, Ant 1.10.18. The test class lives at `stage4-runtime-verification/harness/<stem>/BatchlogPageBudgetTest.java`. `unit-run.sh` copies it into the clone's `test/unit/org/apache/cassandra/batchlog/`. Instrument check at the audit: the class compiles in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, `$W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/audit-compile.log`). The test yaml is not changed. Reason: B2a named a CloudLab path.

**B2b. Knobs.** The limit cannot be set, so the test varies the inputs to `:254`/`:257`, which are the batch size and the flush state:

| Case | Batch size S (2 mutations × S/2 blob) | Count N | SSTable state of `system.batches` before replay | Why |
|---|---|---|---|---|
| A | 64 KiB | 260 | none (memtable only) | `:254` fallback, so 128 |
| B | 64 KiB | 260 | flushed | `:257` gives about 4096/64 = 64 |
| C | 260 large batches of 64 KiB unflushed, after 500 tiny batches (1 mutation of about 100 B, timestamps older) flushed | 760 | small-batch SSTable only | statistics dilution, so 128 for the large ones |
| D | 1 MiB | 12 | flushed | `:257` gives about 4; tests the floor near the budget |

- Set the throttle off with `DatabaseDescriptor.setBatchlogReplayThrottleInKiB(0)` (`DatabaseDescriptor.java:3687`), so that `:241` gives `Double.MAX_VALUE` and the test is not rate-paced.
- Truncate `system.batches` between cases (as `BatchlogManagerTest.setUp` does).

**B2c. Workload.**
- Copy the setup from `BatchlogManagerTest` (`:74-103`): `DatabaseDescriptor.daemonInitialization()`, Murmur3 partitioner switch, `SchemaLoader.prepareServer()`, a keyspace `BLP` with `SchemaLoader.standardCFMD(BLP, "T", 1, BytesType.instance)`, and a token for 127.0.0.1 with a host id.
- For each batch `i`, build two `RowUpdateBuilder(cfm, ts, bytes(2*i+j)).clustering("c").add("val", <random ByteBuffer of S/2 bytes>).build()` mutations (j = 0,1). Store them with `BatchlogManager.store(Batch.createLocal(atUnixMillis(old, i), old*1000, mutations))`, where `old = currentTimeMillis() - 2*BatchlogManager.getBatchlogTimeout()`. All batches are then due for replay.
- Arithmetic:
  - A: 260 = 2×128 + 4 rows, giving two full pages and one partial. Bytes per full page ≈ 128 × 64 KiB = 8 MiB, which is 2× the 4 MiB target.
  - B: ≈ 64 per page, so ≈ 4 MiB.
  - D: 12 MiB in total, ≈ 4 per page.
  - Total live data in any case is ≤ 50 MiB, well inside the test heap and below any memtable flush trigger. Verify with the precondition check in B2e.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2c, the workload as run.** (i) The table is `standardCFMD(BLP, "T", 1, BytesType.instance, BytesType.instance)`, so the random blob goes into a `blob` column, not the default ASCII one. (ii) Batch ids are `TimeUUID.Generator.atUnixMillis(ts, 0)` with `ts = now − 2 × getBatchlogTimeout() − 60 s + i`, so every batch is due and ids are in store order. In case C the tiny batches use `base + i` and the large ones `base + 1000 + i`, so the tiny ones are older and are replayed first. Blobs come from `new Random(42)`. (iii) **Before each case, `BatchlogManager.instance.lastReplayedUuid` is reset by reflection to `TimeUUID.minAtUnixMillis(0)`**, the value of a fresh instance. Without the reset, a case's batches could be older than the previous case's replay limit and would be skipped (A3 amendment (ii)). The reset is state set-up only: the replay code is not changed. (iv) All four cases run in one JVM (`daemonInitialization()` runs once per JVM), each starting with `truncateBlocking()` of `system.batches`. Case C: 500 tiny batches (1 mutation, 100 B blob) flushed, then 260 × 64 KiB unflushed, N = 760. Page arithmetic (rows in id order): A 128, 128, 4; B (page 57) 57, 57, 57, 57, 32; C 128 × 5, 120, where page 4 holds 116 tiny + 12 large and pages 5 and 6 are all large; D (page 3) 3, 3, 3, 3. Reason: the replay cursor survives between passes in one JVM, and the filed table schema would have put binary values into an ASCII column.

**Amendment 2026-10-26 (stage 4 unit run 1, runbook defect 1; Claude Opus 5.5, claude-opus-5-5) — B2c, read thresholds off in the unit JVM.** The test's `@BeforeClass` calls `DatabaseDescriptor.setReadThresholdsEnabled(false)` right after `daemonInitialization()`, and the setup line prints the value. This is the node default (`Config.java:526`). The unit yaml enables the thresholds, and the coordinator read-size check aborted the internal replay read of every case in attempt 0 (A3 correction above). B2f–B2h are unchanged, and the unit tier restarts from r1. Reason: B2 could not run as written on this build.

**B2d. Observables and instruments.**
1. `BatchlogManager.calculatePageSize(store)`, called directly just before replay. Also record `store.getMeanPartitionSize()`.
2. A Byteman rule, `@BMRule(name="page", targetClass="BatchlogManager", targetMethod="finishAndClearBatches", targetLocation="AT ENTRY", action="org.apache.cassandra.batchlog.BatchlogPageBudgetTest.record($1)")`.
   - The static `record(List<?> l)` stores `l.size()`.
   - It also sums the private `int replayedBytes` field of each element by reflection (`getDeclaredField("replayedBytes")`, `setAccessible(true)`). That field is the serialized size of the batch's mutations (`BatchlogManager.java:342,351,397`).
   - It keeps `calls`, `maxCount`, `maxBytes` and the list of per-call counts.
3. `BatchlogManager.instance.getTotalBatchesReplayed()` delta, and `countAllBatches()` after the replay (expected 0).

Not observable directly: the retained heap of the raw-row page inside `FromPager`. The test uses `replayedBytes` as its proxy, a lower bound of about one copy.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2d, where each reading is read, and one added observable.** The unit JVM routes `System.out` to the test log, so every reading is read from `build/test/logs/**/TEST-org.apache.cassandra.batchlog.BatchlogPageBudgetTest.log` (the lines start with `BLP `), not from the XML. Added: a second Byteman rule, `replayPs`, on `calculatePageSize` AT EXIT, which records the page size computed **inside** the replay pass (`:216`). The page size the replay used is then observed, not only the one the test computed just before. Also printed: the live SSTable count of `system.batches` before replay, the number of stored batches (`countAllBatches()`), and the per-call byte sums. Reason: the output location in B2e is wrong for this build (closed cases on this machine), and the filed design read the page size only outside the pass.

**B2e. Procedure.**
1. Write the test with four `@Test` methods (A–D). Each method does the following:
   - Truncate `system.batches`, reset the counters and set the throttle to 0.
   - Store the batches.
   - Flush only if the case requires it, with `store.forceBlockingFlush(ColumnFamilyStore.FlushReason.UNIT_TESTS)`.
   - Precondition: assert `store.getLiveSSTables().isEmpty()` for A. For C, assert the live SSTables contain only the tiny-batch flush: store the tiny ones, flush, record the SSTable count, store the large ones, assert the count is unchanged.
   - Record `ps = calculatePageSize(store)`.
   - Run `BatchlogManager.instance.performInitialReplay()`.
   - Print `ps, mean, calls, maxCount, maxBytes, per-call counts`.
2. Run `ant testsome -Dtest.name=org.apache.cassandra.batchlog.BatchlogPageBudgetTest -Dno-build-test=false` from `/local/c509-bl`.
3. Collect the printed lines from `build/test/output/TEST-org.apache.cassandra.batchlog.BatchlogPageBudgetTest.xml` (or the console).

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2e, the procedure as run.** `harness/<stem>/unit-run.sh r1`, then `r2` and `r3` (three runs of the same test, one JVM each). Each run copies the class, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.batchlog.BatchlogPageBudgetTest`, and copies the JUnit XML and the test log to `$W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/unit-<run>/` (with `stdout.txt` holding the `BLP ` lines). The four `@Test` methods are as in B2e, with the changes of the B2c and B2d amendments. Reason: B2e's output location and the reset of B2c.

**B2f. Predictions.**

| Case | mean | ps | calls | maxCount | maxBytes |
|---|---|---|---|---|---|
| A | 0 | 128 | 3 (128, 128, 4) | 128 | ≈ 8 MiB (128 × about 64 KiB plus serialization overhead; between 8.0 and 9.0 MiB) |
| B | ≈ 64 KiB (±20%, histogram buckets) | 50–80 | ⌈260/ps⌉ | = ps | ≈ ps × 64 KiB, in 3.2–5.2 MiB |
| C | ≈ 100–300 B | 128 | ⌈760/128⌉ = 6 | 128 | ≈ 8 MiB (pages made entirely of large batches) |
| D | ≈ 1 MiB | 3–5 | ⌈12/ps⌉ | = ps | ≈ 3–5 MiB |

In every case `maxCount ≤ ps ≤ 128`, and the replayed delta equals N.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2f, exact values derived at the audit** (A3 amendment (iii)). The filed bands stay the conditions; the exact values are the derived expectation and have their own rows in B2g.

| Case | mean | ps = replayPs | calls and per-call counts | maxCount | maxBytes (replayedBytes of one page) |
|---|---|---|---|---|---|
| A | 0 | 128 = [128] | 3: 128, 128, 4 | 128 | in [8.0, 9.0] MiB (128 × (64 KiB + overhead)) |
| B | 73,457 | 57 = [57] | 5: 57, 57, 57, 57, 32 | 57 | in [3.5625, 4.0] MiB (≥ 57 × 64 KiB; ≤ 4 MiB because the mean bounds the row) |
| C | ≤ 16,400 (tiny rows) | 128 = [128] | 6: 128 × 5, 120 | 128 | in [8.0, 9.0] MiB (page 5: 128 large) |
| D | 1,131,752 | 3 = [3] | 4: 3, 3, 3, 3 | 3 | in [3.0, 4.0] MiB |

In every case: stored = N, `replayedDelta` = N, `afterCount` = 0, the precondition asserts pass, and the three runs print the same counts. **Finding 1 (count cap):** maxCount ≤ ps ≤ 128 in all four cases. **Finding 2 (byte target):** maxBytes ≤ 4 MiB in B and D (statistics match), and in [8.0, 9.0] MiB, about 2 × the target, in A and C. Reason: the filed band for B (50–80) and D (3–5) can be narrowed to exact values from the histogram's bucket offsets. No filed value is widened.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| `maxCount ≤ ps` in all cases, B's `ps` < A's `ps` and B's `maxBytes` ≈ 4 MiB | The count cap works. The byte target works when statistics exist. Claim (i) and the B half of (ii) are confirmed |
| A or C: `ps` = 128 and `maxBytes` ≈ 8 MiB (> 4 MiB) | The byte target is bypassed by memtable-only or diluted statistics. The overshoot half of (ii) is confirmed |
| `maxCount > ps` in any case | Claim (i) is wrong: the `:296` boundary does not bound the retained batches |
| B or D `ps` does not move from 128 after the flush | The `:257` branch is not reached. Check the precondition (SSTable present) before concluding |
| `calls` = 0 or replayed delta < N | The workload did not reach the check (batches not due, or removed as expired at `:362`). Not confirmed; fix the timestamps |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B2g, rows by finding.** The filed rows stay. They are read as follows, and the audit adds the rows marked +.

*Finding 1: count cap (≤ `pageSize` ≤ 128 decoded batches per page)*

| Observation | Meaning |
|---|---|
| maxCount ≤ ps ≤ 128 in A–D, replayPs = ps, in all three runs | Count cap holds: claim (i), unit. **Confirmed** for finding 1 |
| maxCount > ps in any case | Claim (i) refuted: **Refuted** |
| + maxCount ≤ ps, but the per-call counts differ from the page arithmetic of B2f | The cap holds, but pages are not formed as derived. Finding 1 stands; the page arithmetic is **Not confirmed** and the cause is reported |
| + replayPs ≠ ps (the replay used another page size than the one read before it) | The pre-replay reading does not describe the pass: judge with replayPs, and report it |

*Finding 2: the 4 MiB byte target*

| Observation | Meaning |
|---|---|
| B and D: ps < 128 (57, 3) and maxBytes ≤ 4 MiB | The byte target holds when the statistics describe the batches (the B half of claim (ii)) |
| A and C: ps = 128 and maxBytes > 4 MiB (in [8.0, 9.0] MiB) | The byte target is bypassed by memtable-only or diluted statistics (the overshoot half of (ii)): **caps only on some paths (bypass)** |
| + B or D: maxBytes > 4 MiB | The target is missed even with matching statistics: the B half of (ii) is **Refuted** |
| B or D: ps = 128 after the flush | `:257` not reached: check the precondition; **Not confirmed** for finding 2 |
| + A or C: ps < 128 | The statistics are not those the arm needs (a stray SSTable): **Not confirmed** for that arm |

*Validity (both findings)*

| Observation | Meaning |
|---|---|
| calls = 0, replayedDelta < N, or afterCount > 0 | The workload did not reach the check: **Not confirmed** |
| + a precondition assert fails, the test fails, or the runs disagree in any count | **Not confirmed** (or invalid run) for the case concerned |

The unit verdict is **Confirmed** when finding 1's first row and both first rows of finding 2 hold. It is reported with two Effects: count cap `caps`; byte target `caps only on some paths (bypass)` (or whichever row matched). Reason: the README asks for a row for every plausible outcome, and the caller asked for the two findings to be kept apart.

**B2h. Controls.**
- Case B against case A is the positive control. The same workload with only the flush state changed should move `ps` and `maxBytes`.
- The throttle is set to 0 so pacing cannot hide anything.
- `replayedBytes` is read from the actual objects in the list, not computed.
- The precondition asserts tie each case to the intended `:254` branch.
- Expiry cannot interfere: the tables have the default `gc_grace_seconds` of 864000, so `:362` does not drop batches written only seconds ago.

### B3. Cluster tier

**B3a. Environment and build.**
- One Linux node with JDK 11, built from `/local/c509-bl` (`ant jar`, plus `ant build-test` so the Byteman jars are present). Run it from that tree.
- Data, commitlog, hints and saved caches go under `/local/bl-run/{data,commitlog,hints,saved_caches}` on local disk with at least 10 GiB free.
- `conf/cassandra.yaml` edits in the local tree:

  ```yaml
  cluster_name: blpage
  num_tokens: 16
  seeds: "127.0.0.1"
  listen_address: 127.0.0.1
  rpc_address: 127.0.0.1
  data_file_directories: [/local/bl-run/data]
  commitlog_directory: /local/bl-run/commitlog
  hints_directory: /local/bl-run/hints
  saved_caches_directory: /local/bl-run/saved_caches
  batch_size_warn_threshold: 2048KiB
  batch_size_fail_threshold: 4096KiB
  memtable_allocation_type: offheap_objects   # keep memtable cell data off heap, so heap reflects replay
  memtable_heap_space: 512MiB
  memtable_offheap_space: 2048MiB
  memtable_cleanup_threshold: 0.9
  batchlog_replay_throttle: 1024KiB           # default, kept so replay is paced at ~1 batch/s and sampleable
  ```

- JVM: `export MAX_HEAP_SIZE=4G` (G1).
- `export JVM_EXTRA_OPTS="-Xlog:gc*:file=/local/bl-run/gc.log:time,uptime -javaagent:$BMJAR=script:/local/bl-run/bl.btm -Dorg.jboss.byteman.transform.all=true"`. `cassandra-env.sh:307` appends `JVM_EXTRA_OPTS`.
- `BMJAR=$(find /local/c509-bl/build -name 'byteman-4.0.20.jar' | head -1)`. This is the agent jar, not `-bmunit`, `-submit` or `-install`.
- `/local/bl-run/bl.btm`:

  ```
  RULE suppress coordinator batchlog cleanup (so batches stay in system.batches)
  CLASS org.apache.cassandra.service.StorageProxy
  METHOD asyncRemoveFromBatchlog
  AT ENTRY
  IF true
  DO return
  ENDRULE

  RULE hold replay until flag file exists
  CLASS org.apache.cassandra.batchlog.BatchlogManager
  METHOD getBatchlogTimeout
  AT ENTRY
  IF !(new java.io.File("/local/bl-run/go").exists())
  DO return 86400000L
  ENDRULE

  RULE trace page size
  CLASS org.apache.cassandra.batchlog.BatchlogManager
  METHOD calculatePageSize
  AT EXIT
  IF true
  DO traceln("BLPAGESIZE " + $!)
  ENDRULE

  RULE trace page finish
  CLASS org.apache.cassandra.batchlog.BatchlogManager
  METHOD finishAndClearBatches
  AT ENTRY
  IF true
  DO traceln("BLPAGE unfinished=" + $1.size())
  ENDRULE
  ```

  The first rule is fault injection. It only stops the coordinator deleting the batchlog entry after a successful write (`StorageProxy.java:1206-1207,1308-1320`). The client path, the batchlog store (`:1286-1306`) and replay are untouched. The second rule keeps the scheduled 10 s replay from consuming batches while they are loaded. `getBatchlogTimeout` is read at `BatchlogManager.java:214`.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3a, this host.** One node on `127.0.0.1` from the run clone `$W/cassandra-run28` (its `build-test` includes the jar, the stress classes and `build/lib/jars/byteman-4.0.20.jar`). The conf is rebuilt for each case by `harness/<stem>/make-node-conf.sh` under `$W/node-bl/n1/`: the tag's `cassandra.yaml` with B3a's keys, and directories under `$W/node-bl/n1/`. **B3a's top-level `seeds: "127.0.0.1"` is not a `cassandra.yaml` key and would stop start-up; the shipped `seed_provider` (`127.0.0.1:7000`) is kept instead.** JMX is on 7199 (the tag's `cassandra-env.sh`). The node runs with `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (G1, the shipped `jvm11-server.options`). `JVM_EXTRA_OPTS="-javaagent:$W/cassandra-run28/build/lib/jars/byteman-4.0.20.jar=script:<harness>/bl.btm,listener:true -Dorg.jboss.byteman.transform.all=true"` is scoped to the `bin/cassandra` command only. The extra `-Xlog:gc*` is dropped: `cassandra-env.sh:81-83` already writes `gc.log` in the node's log directory, which is recorded only. The node is started with `nohup bin/cassandra -f > node.out` (macOS has no `setsid`) and stopped with `nodetool drain` then `kill`. The rules are `harness/<stem>/bl.btm`: rules 1 and 2 as filed, with the flag file at `$W/node-bl/go` written out in full; rules 3 and 4 as filed, with ` t=<epoch ms>` appended to the printed text. About 135 GiB is free on the SSD. Reason: B3a named CloudLab paths and a key the yaml loader rejects.

**Amendment 2026-10-26 (stage 4 cluster shakedown, before cluster run 1, runbook defect 3; Claude Opus 5.5, claude-opus-5-5) — B3a, the hold rule's condition.** The filed rule 2 condition `IF !(new java.io.File("…/go").exists())` does not parse in Byteman 4.0.20: `org.jboss.byteman.check.TestScript` reports `ParseException … invalid expression`. The agent then silently skips that rule while injecting the other three. In the shakedown, the scheduled pass replayed the batches before `go` (live `ReplayingBatch` instances in the baseline histograms, and the first `BLPAGE` line belonged to a pass that began before `go`). The rule now binds the file first: `BIND flag:java.io.File = new java.io.File("…/go")` then `IF !flag.exists()`, with the same action `DO return 86400000L`. This is the same condition with the same effect, and it type-checks against the build (`TestScript: no errors`). `cluster-run.sh` now runs this check before any node starts and aborts if it fails. Nothing in B3f–B3h changes, and the shakedown is repeated. Reason: B3 could not run as written; the fix leaves the claim, prediction and rows unchanged.

**B3b. Knobs.** As in the unit tier, the flush state and the batch-size mix of `system.batches` are varied. Each case uses a fresh node: wipe `/local/bl-run/{data,commitlog,hints,saved_caches}` first.
- **A:** 256 batches of about 1 MiB (2 partitions × 512 KiB blob), no flush of `system.batches`. `:254` gives 128.
- **B:** the same 256 batches, then `nodetool flush system batches`. `:257` gives about 4.
- **C:** 2000 tiny batches (2 partitions × 16 B), then `nodetool flush system batches`, then 256 batches of about 1 MiB, unflushed. The diluted mean gives 128.

**B3c. Workload.** Uses cassandra-stress (`tools/bin/cassandra-stress`) through the native protocol. LOGGED is the default batch type (`tools/stress/src/org/apache/cassandra/stress/StressProfile.java:612-616`).
- Profile `/local/bl-run/big.yaml`:

  ```yaml
  keyspace: bl
  keyspace_definition: CREATE KEYSPACE bl WITH replication = {'class':'SimpleStrategy','replication_factor':1};
  table: t
  table_definition: CREATE TABLE t (k bigint PRIMARY KEY, v blob)
  columnspec:
    - name: k
      population: seq(1..100000000)
    - name: v
      size: fixed(524288)
  insert:
    partitions: fixed(2)
    batchtype: LOGGED
    select: fixed(1)/1
  ```

- `small.yaml` is the same with `size: fixed(16)` and `population: seq(200000001..300000000)`.
- Load: `tools/bin/cassandra-stress user profile=/local/bl-run/big.yaml "ops(insert=1)" n=256 -rate threads=4 -node 127.0.0.1`. For small: `n=2000`.
- Arithmetic: each batch is about 1 MiB of data, under the 4 MiB fail threshold and the 16 MiB `max_mutation_size`. The batchlog holds about 256 MiB.
  - A: one page = 128 batches, about 128 MiB raw plus about 128 MiB deserialized.
  - B: about 4 batches, about 8 MiB.
- At the default throttle of 1 MiB/s on a single endpoint (`BatchlogManager.java:237-245,367`), replay advances about 1 batch per second, so 256 batches take about 4–5 min. That is long enough to sample.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3c, the stress counts.** `cassandra-stress` `n=` counts **partitions**, not batches: each insert takes `partitions` permits from a fixed pool of n (`tools/stress/.../operations/PartitionOperation.java:91-94`, `WorkManager.java:42-53`). A warm-up phase also writes 25% more operations unless `no-warmup` is given (`StressAction.java:70-71`, `:105-107`). The loads are therefore `user profile=<harness>/big.yaml "ops(insert=1)" n=512 no-warmup -rate threads=4 -node 127.0.0.1`, giving 256 batches of 2 × 512 KiB, and the same with `small.yaml n=4000`, giving 2,000 batches of 2 × 16 B. Each runs with its working directory in `$W`. Every batch has 2 partitions (`SchemaInsert.java:78-106` builds one `BatchStatement` of all rows of the op's partitions), so it is a multi-partition LOGGED batch and goes through the batchlog. The batch is ≈ 1 MiB: under `batch_size_fail_threshold` 4096 KiB, the 16 MiB `max_mutation_size` and the native message limit. The number actually written is read as `count(*)` before replay (B3e step 7), and B3f's page arithmetic uses that measured N. Reason: the filed `n=256` would write 128 batches (one page in A) plus a warm-up, so the workload would not reach two pages.

**Amendment 2026-10-26 (stage 4 cluster shakedown, before cluster run 1, runbook defect 2; Claude Opus 5.5, claude-opus-5-5) — B3c, the stress profiles.** `cassandra-stress user` rejects a profile without a `queries` map (`StressProfile.java:156`, `AssertionError: queries map is required in yaml file`). `big.yaml` and `small.yaml` therefore end with `queries: {}`. The loads run `ops(insert=1)` only, so no query is used. Nothing else in the profiles, and nothing in B3f–B3h, changes. Reason: B3c could not run as written.

**B3d. Observables and instruments.**
1. **Primary: actual heap.**
   - `jmap -histo:live <pid>` every 10 s during replay. It forces a full GC. Record the instance counts of `org.apache.cassandra.batchlog.BatchlogManager$ReplayingBatch` and `org.apache.cassandra.db.Mutation`, and the total live bytes (last line).
   - Also `jcmd <pid> GC.heap_info` every 2 s.
   - Post-GC occupancy is parsed from `gc.log`.
2. **Operand traces.** `BLPAGESIZE` and `BLPAGE unfinished=` lines on the node's stdout (`bin/cassandra -f` output, redirected to `/local/bl-run/stdout.log`).
3. **State checks.**
   - `nodetool tablestats system.batches`: SSTable count, memtable data size, and "Compacted partition mean bytes".
   - `bin/cqlsh 127.0.0.1 -e "SELECT count(*) FROM system.batches"`.

Not directly observable: retained bytes per object. The live-heap delta during replay against the pre-replay baseline is used for that.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3d, instruments on this host.**
1. `jmap -histo:live` is replaced by `jcmd <pid> GC.class_histogram`, which also forces a full GC and counts live objects; its `Total` bytes is the live-heap reading. Samples are taken every 10 s from `go` until `nodetool replaybatchlog` returns, and once more after it ("post"). Read from each sample: `Total`, and instances of `org.apache.cassandra.batchlog.BatchlogManager$ReplayingBatch` and `org.apache.cassandra.db.Mutation`.
2. `GC.heap_info` every 2 s is recorded only, because its `used` counts young regions (closed cases on this machine). The shipped `gc.log` is also recorded only.
3. The trace lines carry wall-clock milliseconds. Scheduled passes print a `BLPAGESIZE` line every 10 s before and after `go` (a pass with nothing to replay still computes the page size). The **governing page size** is therefore the last `BLPAGESIZE` line before the first `BLPAGE` line in the part of `node.out` written after `go`, which is cut at the byte offset recorded just before `touch go`. `BLPAGE` lines can appear only in a pass that read at least one row; any line before `go` means the hold rule failed.
4. Before replay, `nodetool tablestats system.batches` is read: `SSTable count`, `Memtable data size` and "Compacted partition mean bytes" (m). It gives the derived page size min(128, ⌊4,194,304 / m⌋), or 128 if m = 0, which is compared with the governing `BLPAGESIZE`.
5. `count(*)` of `system.batches` uses `cqlsh --request-timeout=300`.

Reason: `jmap`/`heap_info` are not the live heap on this JDK, and the filed trace could not tell the replay pass's page size from the scheduled passes'.

**B3e. Procedure.** Run once per case.
1. `rm -rf /local/bl-run/{data,commitlog,hints,saved_caches,go} && mkdir -p /local/bl-run/{data,commitlog,hints,saved_caches}`.
2. Start the node: `cd /local/c509-bl && bin/cassandra -f > /local/bl-run/stdout.log 2>&1 &`. Wait until `nodetool status` shows UN. Record the PID with `pgrep -f CassandraDaemon`.
3. For C only: run the `small.yaml` load (n=2000), then `nodetool flush system batches`.
4. Run the `big.yaml` load (n=256).
5. Run `nodetool flush bl`, which flushes user data only, so the data memtable does not mix in.
6. For B only: `nodetool flush system batches`.
7. Check the preconditions:
   - `SELECT count(*) FROM system.batches` should be 256 (C: 2256). If stress sent a different number of batches, record it and use it in the arithmetic.
   - `nodetool tablestats system.batches`: SSTable count 0 for A, ≥1 for B and C.
8. Take the baseline: three `jmap -histo:live` samples 10 s apart.
9. Start the samplers in the background:
   - `while sleep 10; do date +%s; jmap -histo:live $PID | egrep 'ReplayingBatch|db.Mutation$|Total'; done > /local/bl-run/histo.log`
   - `while sleep 2; do date +%s; jcmd $PID GC.heap_info | head -3; done > /local/bl-run/heap.log`
10. Trigger the replay: `touch /local/bl-run/go && time nodetool replaybatchlog`.
11. When it returns, check that `count(*)` of `system.batches` is 0, then stop the samplers.
12. Stop the node with `nodetool stopdaemon`, then `pkill -f CassandraDaemon` if needed. Kill the sampler loops. Check that `pgrep -f 'CassandraDaemon|cassandra-stress'` is empty.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3e, the procedure as run** (`harness/<stem>/cluster-run.sh run1 512 4000 A B C`). Pre-checks: no `CassandraDaemon`, and ports 7000, 7199, 9042, 9091 free. For each case, on a fresh node (`$W/node-bl` wiped):
1. Rebuild the conf, start the node with the agent, and wait for `UN` and `statusbinary` `running` (≤ 360 s).
2. C only: the small load, then `nodetool flush system batches`.
3. The big load, then `nodetool flush bl`.
4. B only: `nodetool flush system batches`.
5. Preconditions: `count(*)` (count_before) and `tablestats system.batches`; no `BLPAGE` line yet.
6. Baseline: three class histograms 10 s apart. Baseline = their median `Total`; drift = max − min.
7. Note the `node.out` byte offset. Start the samplers (class histogram every 10 s, `GC.heap_info` every 2 s), then `touch $W/node-bl/go` and run `nodetool replaybatchlog`, waiting for it to return.
8. Stop the samplers. Read `count(*)` (count_after), take a post histogram, read `tablestats`, and cut the `node.out` text after the offset.
9. `nodetool drain`, `kill`, wait for exit, and check that no `CassandraDaemon` is left.

At the end: wipe `$W/node-bl`, and check that no `CassandraDaemon` and no stress JVM is left. A shakedown of the same script with small loads (`shake 40 40 A B C`: 20 batches each) runs before run 1 to check every step. It is not judged. Reason: B3e's order of reads, drift control and stop conditions were open.

**B3f. Predictions.** "Live delta" means peak post-full-GC live heap minus baseline.

| Case | BLPAGESIZE | max `BLPAGE unfinished` | peak `ReplayingBatch` count in histo | live-heap delta during replay |
|---|---|---|---|---|
| A | 128 | 128 | 100–128 (10 s sampling of a ramp that climbs about 1/s and resets every page) | ≥ 150 MiB; expected about 200–300 MiB (128 MiB raw page plus deserialized mutations) |
| B | 3–5 | = BLPAGESIZE | ≤ 5 | ≤ 30 MiB |
| C | 128 | 128 | 100–128 during the large-batch pages | ≥ 150 MiB, like A |

Relations: A ≈ C ≫ B by more than 5×. The `ReplayingBatch` count never exceeds BLPAGESIZE in any case.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3f, exact values derived at the audit** (A3 amendment (iii), (v)). N is count_before: expected 256 in A and B, and 2,256 in C. The filed bands stay the conditions.

| Case | governing BLPAGESIZE (= derived from m) | `BLPAGE` lines and values | peak `ReplayingBatch` in any sample | live delta = max sample Total − baseline |
|---|---|---|---|---|
| A | 128 (m = 0, no SSTable) | ⌈N/128⌉ lines of 128, the last N mod 128 if non-zero: for N = 256, 128, 128 | in [100, 128] | ≥ 150 MiB; expected ≈ 128 MiB raw page + up to 128 MiB decoded, a peak near 250 MiB |
| B | 3 (m = 1,131,752) | ⌈N/3⌉ lines of 3, the last N mod 3: for N = 256, 85 × 3 and one of 1 (86 lines) | ≤ 3 | ≤ 30 MiB (≈ 3 MiB raw + ≤ 3 MiB decoded per page) |
| C | 128 (m of the 2,000-tiny SSTable ≤ 16,400) | for N = 2,256, 17 × 128 and one of 80 (18 lines) | in [100, 128] (pages 17–18 are large batches) | ≥ 150 MiB |

In every case: the `ReplayingBatch` instances in every sample are ≤ the governing BLPAGESIZE; the maximum `BLPAGE` value equals it; count_after = 0; no `BLPAGE` line appears before `go`; and baseline drift ≤ 10 MiB (otherwise that case's heap reading is invalid). Relation: delta(A) and delta(C) are each more than 5 × delta(B). Replay takes ≈ 1 s per large batch (1024 KiB/s throttle, one endpoint, ≈ 1 MiB `replayedBytes` per batch); this is recorded only. **Finding 1 (count cap):** the instance and `BLPAGE` relations, and A, C ≫ B. **Finding 2 (byte target):** B's page of 3 batches (≈ 3 MiB ≤ 4 MiB) against A's and C's page of 128 (≈ 128 MiB, 32 × the target). Reason: the filed table did not give page counts, a baseline rule or a drift tolerance. No filed value is widened.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| B's delta is small and A's delta is large, with the histo count ≤ BLPAGESIZE | Replay heap follows `pageSize`. The count cap binds on a real node. Claim (i) is confirmed |
| A or C delta ≫ 4 MiB × 2 with BLPAGESIZE = 128 | The 4 MiB byte target is not a cap when `system.batches` is memtable-only or has diluted statistics. The overshoot in (ii) is confirmed |
| histo count of `ReplayingBatch` > BLPAGESIZE | Claim (i) is wrong |
| A and B deltas about equal, with BLPAGESIZE differing | Page size does not govern heap; another consumer dominates. Claim refuted, or confounded: check A4 consumers via the histo top entries |
| `count(*)` far below 256 before replay, or no BLPAGE lines | Batches were not retained, or the replay did not run (Byteman rules not applied: check stdout for "Byteman" rule-injection lines). Not confirmed |

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B3g, rows by finding.** The filed rows stay. They are read as follows, and the audit adds the rows marked +.

*Finding 1: count cap (≤ `pageSize` ≤ 128 decoded batches per page; replay heap follows `pageSize`)*

| Observation | Meaning |
|---|---|
| `BLPAGE` max = governing BLPAGESIZE ≤ 128 and `ReplayingBatch` ≤ BLPAGESIZE in every sample of A, B, C; delta(A), delta(C) ≥ 150 MiB, delta(B) ≤ 30 MiB, each ratio > 5 | The count cap binds on a node and replay heap follows `pageSize`: claim (i) **Confirmed** |
| `BLPAGE` value or `ReplayingBatch` count > BLPAGESIZE | Claim (i) **Refuted** |
| delta(A) ≈ delta(B) (ratio ≤ 2) with BLPAGESIZE differing | Page size does not govern heap: **Refuted** or confounded (check the top histogram entries for an A4 consumer) |
| + the count relations hold and each ratio > 5, but a delta is outside its band | Count cap holds; heap follows `pageSize` in shape, not within the frozen bands: **Not confirmed** for the heap bands |

*Finding 2: the 4 MiB byte target*

| Observation | Meaning |
|---|---|
| A and C: BLPAGESIZE = 128 with delta ≫ 8 MiB (≥ 150 MiB) | The byte target is not a cap when `system.batches` is memtable-only or its statistics are diluted: **caps only on some paths (bypass)** |
| + B: BLPAGESIZE = 3 (= derived from m) and delta ≤ 30 MiB | The target holds when the statistics describe the batches |
| + B: BLPAGESIZE = 128, or A/C: BLPAGESIZE < 128 | The flush state is not what the arm needs: **Not confirmed** for that arm |

*Validity*

| Observation | Meaning |
|---|---|
| count_before far below N, or no `BLPAGE` lines after `go`, or count_after > 0 | Batches not kept, or the replay did not run or finish: **Not confirmed** |
| + a `BLPAGE` line before `go` | The hold rule failed: that case is invalid |
| + baseline drift > 10 MiB | The heap reading of that case is invalid; the count readings stand |

The cluster verdict is **Confirmed** when finding 1's first row and both first rows of finding 2 hold. It is reported with two Effects, as in B2g. Reason: the README asks for a row for every plausible outcome, and the caller asked for the two findings to be kept apart.

**B3h. Controls.**
- Case B is the positive control for A: the identical workload and node, with only the flush state differing, which is the only input to `:254`/`:257`.
- `memtable_allocation_type: offheap_objects` and `nodetool flush bl` before replay remove the main competing heap consumer: the inline `mutation.apply()` at `:486` still adds memtable objects, but the cell data goes off heap.
- A single node means there are no remote sends or hints (`:488-510` find no remote replicas), so A4 consumers stay quiet.
- Baseline samples are taken before `touch go`.
- The Byteman trace lines tie the heap readings to the operand values.

**B4. Risks and cleanup.**
- All data lives under `/local/bl-run` (about 1 GiB at most) and `/local/c509-bl`. Nothing is written in the shared clone.
- `jmap -histo:live` causes full-GC pauses. That is acceptable on a test node.
- After each tier, check that `pgrep -f 'CassandraDaemon|cassandra-stress|JUnitTestRunner'` is empty, then `rm -rf /local/bl-run /local/c509-bl` when done.
- The Byteman agent is only on the test node and is removed with the tree.

**Amendment 2026-10-26 (step-0 audit, Claude Opus 5.5, claude-opus-5-5) — B4, this host.** Unit: after the three runs, remove `test/unit/org/apache/cassandra/batchlog/BatchlogPageBudgetTest.java` and `build/test/cassandra` from the run clone, and check that `git -C $W/cassandra-run28 status` shows no change to tracked files (the test yaml is never edited). Cluster: `cluster-run.sh` stops the node after each case (`nodetool drain`, `kill`, wait), wipes `$W/node-bl` before each case and at the end, and checks that `ps -eo command | grep '[C]assandraDaemon'` and the stress JVM search are empty. Full logs stay under `$W/logs/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries/`. Reason: B4 named CloudLab paths.

## C. Sources read

- src/java/org/apache/cassandra/batchlog/BatchlogManager.java
- src/java/org/apache/cassandra/db/ColumnFamilyStore.java (3123-3147, 1855)
- src/java/org/apache/cassandra/cql3/QueryProcessor.java (573-602)
- src/java/org/apache/cassandra/cql3/UntypedResultSet.java (188-242)
- src/java/org/apache/cassandra/db/SystemKeyspace.java (151-221, 527-534)
- src/java/org/apache/cassandra/service/StorageProxy.java (1173-1320, 1398-1419)
- src/java/org/apache/cassandra/service/BatchlogResponseHandler.java (30-117)
- src/java/org/apache/cassandra/locator/ReplicaPlans.java (238-268)
- src/java/org/apache/cassandra/cql3/statements/BatchStatement.java (331-446)
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java (631, 898-901, 2061-2075, 2827, 3682-3687)
- src/java/org/apache/cassandra/config/CassandraRelevantProperties.java (65)
- src/java/org/apache/cassandra/tools/nodetool/ReplayBatchlog.java; src/java/org/apache/cassandra/tools/NodeProbe.java (2319-2324)
- src/java/org/apache/cassandra/db/commitlog/CommitLogReplayer.java (241-267)
- src/java/org/apache/cassandra/batchlog/Batch.java (60-63)
- test/unit/org/apache/cassandra/batchlog/BatchlogManagerTest.java
- test/unit/org/apache/cassandra/locator/AssureSufficientLiveNodesTest.java (53-71)
- test/conf/cassandra.yaml; conf/cassandra.yaml; conf/cassandra-env.sh; build.xml; .build/parent-pom-template.xml
- tools/stress/src/org/apache/cassandra/stress/StressProfile.java (600-630); tools/cqlstress-example.yaml

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 (Claude Opus 5.5, claude-opus-5-5), on the advisor's machine.** Results: [`stage4-runtime-verification/results/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.md`](../../stage4-runtime-verification/results/batchlog_DEFAULT_PAGE_SIZE-processBatchlogEntries-positionInPage--autonomous.md). Uncommitted.

**Version history.** The file was frozen after fifteen audit amendments at sha256 `d04e9c87…f056`. The unit tier then ran at `e39a7514…2ea3` (defect 1) and the cluster tier at `70b0f972…2226` (defects 2 and 3). No prediction changed.

**Verdicts.**
- **Unit: Confirmed.** maxCount = ps in every case: 128 (memtable-only), 57 (64 KiB flushed; mean 73,457), 128 (diluted; mean 215) and 3 (1 MiB flushed; mean 1,131,752). The per-call counts were exact in three runs. Bytes per page were 3.57 and 3.00 MiB with matching statistics, and 8.01 MiB with ps = 128.
- **Cluster: Confirmed.** The `BLPAGE` maximum and the live `ReplayingBatch` count were ≤ BLPAGESIZE (128, 3, 128). Live heap above baseline was 378.6 MiB (A), 9.6 MiB (B) and 386.4 MiB (C) for the same 256 batches of 1 MiB.
- **Effect:** the count cap **caps**; the 4 MiB byte target **caps only on some paths (bypass)**.

**Runbook defects.**
1. The unit yaml's read thresholds abort the internal replay read. The A3 amendment's item (iv) was wrong; fixed by a dated correction and amendment.
2. The stress profiles need `queries: {}`.
3. The filed Byteman hold rule's `IF !(new java.io.File(…).exists())` does not parse in Byteman 4.0.20 and is silently skipped.

**For stage 3.**
- (a) On a node with `read_thresholds_enabled: true` and a `coordinator_read_size_fail_threshold` below one replay page, batchlog replay fails. The coordinator read-size check runs in `SelectStatement.process` for the internal pager, and `loggableTokens` throws on the unbound markers. This was seen in unit attempt 0 and is not tested on a node.
- (b) The node held about 3 MiB of live heap per decoded 1 MiB batch, not the 2 MiB the design assumed. The extra copy is not identified.
