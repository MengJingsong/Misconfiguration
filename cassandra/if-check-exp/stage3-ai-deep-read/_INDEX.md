# If-Check Cases — Master Index

Navigation hub and progress tracker for all case files of both agents.
See [README.md](README.md) for the format. Each case file is named `<stem>--guided.md`
or `<stem>--autonomous.md`; the Agent column repeats the suffix. Estimate is `positive`, `negative` or `undetermined` (a prediction from the source; stage 4 confirms or refutes it); Outcome class (true positive / false positive / true negative / false negative / undetermined, defined in [`../stage4-runtime-verification/README.md`](../stage4-runtime-verification/README.md#outcome-class)) compares the estimate with the stage-4 effect; Ground names the rule or reason for a negative. A column the
autonomous template does not ask for (decision point, module, object, pattern) is `—`
on an autonomous row.

**Source:** apache/cassandra @ tag `cassandra-5.0.9`
**Pattern legend** (README §3.2; the pattern is recorded in each guided case file's §1): **(a)** the capacity check is the decision · **(b)** the check sets a verdict (flag, enum, return value) that a separate decision point reads · **(c)** guard clause(s) before an allocation outside any branch

## 1. Master Index

The constraint name links to the case file and the Stage 4 cell to its results file. Since 2026-10-20 the table keeps only these columns (plus, since 2026-10-22, the outcome class); the capacity check, decision point, module, object, pattern, feed and ground of each case are in the case file (guided: §1, §3 and §10; autonomous: the header table and section A).

| Constraint (→ case file) | Agent | Estimate | Stage 4 | Outcome class |
|---|---|---|---|---|
| [`memtable_heap_space`](cases/memtable_heap_space-tryAllocate-limit--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--guided.md) | true positive |
| [`memtable_offheap_space`](cases/memtable_offheap_space-tryAllocate-limit--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/memtable_offheap_space-tryAllocate-limit--guided.md) | true positive |
| [`internode_application_receive_queue_capacity`](cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | true positive |
| [`native_transport_receive_queue_capacity`](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) | true positive |
| [`MAX_HINT_BUFFERS`](cases/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided.md) | true positive |
| [`cdc_total_space`](cases/cdc_total_space-processNewSegment-allowance--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/cdc_total_space-processNewSegment-allowance--guided.md) | true positive |
| [`DataDirectory_getAvailableSpace`](cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace--guided.md) | true positive |
| [`max_space_usable_for_compactions_in_percentage`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--guided.md) | true positive |
| [`column_index_cache_size`](cases/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) | true positive |
| [`max_hints_size_per_host`](cases/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_hints_size_per_host-shouldHint-maxHintsSize--guided.md) | true positive |
| [`file_cache_size`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | true positive |
| [`max_mutation_size`](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) | true positive |
| [`max_value_size`](cases/max_value_size-read-maxValueSize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/max_value_size-read-maxValueSize--guided.md) | true positive |
| [`CACHEABLE_MUTATION_SIZE_LIMIT`](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md) | true positive |
| [`local_read_size_fail_threshold`](cases/local_read_size_fail_threshold-addSize-failBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/local_read_size_fail_threshold-addSize-failBytes--guided.md) | true positive |
| [`row_index_read_size_fail_threshold`](cases/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/row_index_read_size_fail_threshold-checkSize-failThreshold--guided.md) | true positive |
| [`internode_application_send_queue_capacity`](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided.md) | true positive |
| [`repair_session_space`](cases/repair_session_space-split-maxsize--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/repair_session_space-split-maxsize--guided.md) | true positive |
| [`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`](cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md) | true positive |
| [`Integer_MAX_VALUE`](cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE--guided.md) | true positive |
| [`networking_cache_size`](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) | true positive |
| [`coordinator_read_size_fail_threshold`](cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) | true positive |
| [`repair_disk_headroom_reject_ratio`](cases/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio--guided.md) | true positive |
| [`DOB_MAX_RECYCLE_BYTES`](cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) | guided | positive | [Confirmed](../stage4-runtime-verification/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) | true positive |
| [`memtable_heap_space`](cases/memtable_heap_space-tryAllocate-limit--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/memtable_heap_space-tryAllocate-limit--autonomous.md) | true positive |
| [`max_space_usable_for_compactions_in_percentage`](cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md) | true positive |
| [`concurrent_compactors`](cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) | guided | negative | [**Refuted**](../stage4-runtime-verification/results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) | false negative |
| [`batch_size_fail_threshold`](cases/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md) | guided | negative | [**Confirmed** — does not cap](../stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md) | true negative |
| [`native_transport_max_message_size`](cases/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) | guided | negative | [**Refuted** — caps per request](../stage4-runtime-verification/results/native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided.md) | false negative |
| [`native_transport_max_concurrent_connections`](cases/native_transport_max_concurrent_connections-channelActive-limit--guided.md) | guided | negative | [**Refuted** (cluster; unit counts only) — caps indirectly](../stage4-runtime-verification/results/native_transport_max_concurrent_connections-channelActive-limit--guided.md) | false negative |
| [`native_transport_queue_max_item_age_threshold`](cases/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) | guided | negative | [**Refuted** — caps in throwing mode](../stage4-runtime-verification/results/native_transport_queue_max_item_age_threshold-hasQueueCapacity-oldestTaskQueueTime--guided.md) | false negative |
| [`prepared_statements_cache_size`](cases/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md) | true positive |
| [`internode_max_message_size` · `inferMessageSize`](cases/internode_max_message_size-inferMessageSize-size--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/internode_max_message_size-inferMessageSize-size--autonomous.md) | true positive |
| [`internode_max_message_size` · `enqueue`](cases/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md) | autonomous | positive | [Confirmed (bypass: refused write held on coordinator heap)](../stage4-runtime-verification/results/internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md) | true positive |
| [`max_mutation_size`](cases/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) | autonomous | positive | [Confirmed](../stage4-runtime-verification/results/max_mutation_size-allocateBytes-slabCapacity--autonomous.md) | true positive |
| [`WRITE_BUFFER_SIZE`](cases/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) | autonomous | negative | [**Confirmed** — does not cap](../stage4-runtime-verification/results/WRITE_BUFFER_SIZE-append-remaining--autonomous.md) | true negative |
| [`internode_application_receive_queue_capacity`](cases/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) | autonomous | positive | [Unit Confirmed; cluster partial (accounting capped, heap not for large messages)](../stage4-runtime-verification/results/internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md) | undetermined |
| [`maxHintsInProgress`](cases/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md) | autonomous | negative | [**Confirmed** — does not cap](../stage4-runtime-verification/results/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md) | true negative |
| [`concurrent_writes`](cases/concurrent_writes-takeWorkPermit-workPermits--autonomous.md) | autonomous | negative | [**Confirmed** — does not cap](../stage4-runtime-verification/results/concurrent_writes-takeWorkPermit-workPermits--autonomous.md) | true negative |
| [`maximumPoolSize`](cases/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md) | autonomous | negative | [Unit **Confirmed** — does not cap; cluster **Not confirmed** (BIND-5) — undetermined](../stage4-runtime-verification/results/maximumPoolSize-takeTaskPermit-workPermits--autonomous.md) | undetermined |
| [`index_summary_capacity`](cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md) | autonomous | positive | [**Confirmed** (unit caps; cluster caps only on some paths — bypass: new sstables between resize runs, table index intervals)](../stage4-runtime-verification/results/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md) | true positive |
| [`commitlog_total_space`](cases/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md) | autonomous | positive | [**Confirmed** — caps (soft; overshoot grows with write rate)](../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md) | true positive |
| [`tombstone_failure_threshold`](cases/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md) | autonomous | positive | [Unit **Confirmed** — caps per read; cluster **Not confirmed (partial)** — per-read buffer follows T, node heap peak not capped](../stage4-runtime-verification/results/tombstone_failure_threshold-countTombstone-tombstones--autonomous.md) | undetermined |
| [`commitlog_total_space` · `:259`](cases/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md) | autonomous | positive | [Unit **Confirmed** — caps (soft); line 259 picks just enough segments (added arm i5); cluster **Not confirmed (no matching row)** — undetermined (Jingsong override 2026-10-22: row 4c, added after a reading, struck)](../stage4-runtime-verification/results/commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md) | undetermined |
| [`index_summary_capacity` · `adjustSamplingLevels`](cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) | autonomous | positive | [**Confirmed** (unit caps, `:258` operand exact; cluster caps only on some paths — bypass: between runs, `max_index_interval` floor)](../stage4-runtime-verification/results/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) | true positive |
| [`internode_application_send_queue_capacity` · `releaseCapacity`](cases/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md) | autonomous | positive | [Unit **Confirmed** — caps; cluster partial — caps (plateau C + reserve and `:449` release exact; heap ≈ 3.3 × queued bytes + ~42 MiB, not proportional)](../stage4-runtime-verification/results/internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md) | true positive |
| [`memtable_heap_space` · `needsCleaning`](cases/memtable_heap_space-needsCleaning-nextClean--autonomous.md) | autonomous | positive | [**Confirmed** — caps (soft trigger at L·t exact; L itself not reached on the node)](../stage4-runtime-verification/results/memtable_heap_space-needsCleaning-nextClean--autonomous.md) | true positive |
| [`largestRatio`](cases/largestRatio-flushLargestMemtable-largestRatio--autonomous.md) | autonomous | negative | [Unit **Refuted** (ceiling held, but peak/L differs by selection); cluster **Confirmed** — does not cap](../stage4-runtime-verification/results/largestRatio-flushLargestMemtable-largestRatio--autonomous.md) | undetermined |
| [`NORMAL_CHUNK_SIZE` · `freeUnusedPortion`](cases/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md) | autonomous | negative | [Unit **Confirmed** — does not cap; cluster **Not confirmed** (K2b-4: cap never reached where the check runs) — undetermined; `OverflowSize` drifts to −14.7 GB](../stage4-runtime-verification/results/NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md) | undetermined |
| [`OTCP_LARGE_MESSAGE_THRESHOLD`](cases/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md) | autonomous | negative | [Unit **Not confirmed** (U9: pool peak spread 344 KiB > 300 KiB band) — undetermined; cluster **Confirmed** — does not cap](../stage4-runtime-verification/results/OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md) | undetermined |
| [`flushLowWaterMark`](cases/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md) | autonomous | negative | [Unit **Not confirmed** (no matching row) and cluster **Not confirmed** (row 5) — undetermined; readings flat in the low mark, move with the high mark](../stage4-runtime-verification/results/flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md) | undetermined |
| [`native_transport_max_request_data_in_flight` · `releaseItem`](cases/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md) | autonomous | positive | [**Confirmed** — caps (soft): peak = (⌊L/S⌋ + 1)·S exactly, + one request per connection](../stage4-runtime-verification/results/native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md) | true positive |
| [`memtable_heap_space` · `adjustMemtableSize`](cases/memtable_heap_space-adjustMemtableSize-0--autonomous.md) | autonomous | positive | [Unit **Confirmed** — caps (loose, ~3.5 × the charge held); cluster **Not confirmed** (no matching row: sawtooth under-sampled) — undetermined](../stage4-runtime-verification/results/memtable_heap_space-adjustMemtableSize-0--autonomous.md) | undetermined |
| [`internode_application_receive_queue_reserve_global_capacity` · `acquireCapacity`](cases/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md) | autonomous | positive | [**Confirmed** — caps: accounted peak ≤ Q + G at 4 and 32 MiB, throttled only below the default; memory held off-heap in the networking pool (1.4–1.5 × accounted)](../stage4-runtime-verification/results/internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md) | true positive |
| [`cdc_total_space` · `deleteOldLinkedCDCCommitLogSegment`](cases/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md) | autonomous | positive | [**Confirmed** — caps (soft): `cdc_raw` plateau = cap (blocking) or cap + ≤1 segment (non-blocking) at 64–512 MiB; 4096 MiB control uncapped](../stage4-runtime-verification/results/cdc_total_space-deleteOldLinkedCDCCommitLogSegment-bytesToFree--autonomous.md) | true positive |
| [`maxTasksQueued` · `takeTaskPermit`](cases/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md) | autonomous | negative | [Unit **Confirmed** — does not cap; cluster **Not confirmed** (C4: positive control did not move) — undetermined](../stage4-runtime-verification/results/maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md) | undetermined |
| [`maxTasksQueued` · `addTask`](cases/maxTasksQueued-addTask-taskPermits--autonomous.md) | autonomous | negative | [Unit **Confirmed** — does not cap; cluster **Not confirmed** (no matching row: peak Pending did not track the in-flight cap) — undetermined](../stage4-runtime-verification/results/maxTasksQueued-addTask-taskPermits--autonomous.md) | undetermined |
| [`maximumPoolSize` · `setMaximumPoolSize`](cases/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.md) | autonomous | negative | [Unit **Confirmed** — does not cap; cluster **Not confirmed** (no matching row: heap max/min 1.249 between the 1.15 and 1.5 bands) — undetermined](../stage4-runtime-verification/results/maximumPoolSize-setMaximumPoolSize-deltaWorkPermits--autonomous.md) | undetermined |

<!-- Add one row per case. -->

## 2. Coverage summary

| Metric | Count |
|--------|-------|
| Modules covered | 12 (guided files) |
| Total case files | 58 (29 guided, 29 autonomous) |
| of which negative estimates | 8 (5 guided, written up 2026-10-19 as the pilot of the `predicted-negative.md` write-up, and 3 autonomous: `WRITE_BUFFER_SIZE`, `maxHintsInProgress` and `concurrent_writes` (both filed 2026-10-21)); plus `maximumPoolSize` (autonomous, 2026-10-21). Of the four `predicted-negative.md` entries written up autonomously on 2026-10-21, three came back with a **positive** estimate (`index_summary_capacity`, `commitlog_total_space`, `tombstone_failure_threshold`) and stage 4 found usage follows the knob for all three, so stage 3's earlier negative entries for those lines do not hold. Second batch (2026-10-21/22): five `predicted-negative.md` lines written up autonomously; four came back **positive** (`commitlog_total_space` `:259`, `index_summary_capacity` `:258`, `internode_application_send_queue_capacity` `:449`, `memtable_heap_space` `MemtablePool.java:128`) and stage 4 found usage follows the knob for all four; one negative (`largestRatio`, `AbstractAllocatorMemtable.java:274`). Third batch (2026-10-22): five more §9 lines; three negative (`NORMAL_CHUNK_SIZE` `BufferPool.java:1521`, `OTCP_LARGE_MESSAGE_THRESHOLD` `OutboundConnection.java:767`, `flushLowWaterMark` `:871`) and two positive (`native_transport_max_request_data_in_flight` `PreV5Handlers.java:127`, `memtable_heap_space` `StorageAttachedIndex.java:1006`) |
| Found via feed 3b (raw source) | 13 |
| Found via feed 3a (stage 1/2) | **11** |
| Stage 4 closed (all tiers Confirmed; see `../stage4-runtime-verification/results/`) | **41** (24 guided positive, 1 guided negative, 16 autonomous), as of 2026-10-22 (fourth batch: `internode_application_receive_queue_reserve_global_capacity` · `acquireCapacity` — caps; `cdc_total_space` · `deleteOldLinkedCDCCommitLogSegment` — caps (soft); third batch: `native_transport_max_request_data_in_flight` · `releaseItem` — caps (soft); 2026-10-22, second `predicted-negative.md` batch: `index_summary_capacity` · `adjustSamplingLevels` — caps only on some paths (bypass) — and `memtable_heap_space` · `needsCleaning` — caps; 2026-10-21, first `predicted-negative.md` batch: `index_summary_capacity` — caps only on some paths (bypass) — and `commitlog_total_space` — caps (soft); 2026-10-21: `maxHintsInProgress` and `concurrent_writes` — both Confirmed, does not cap; 2026-10-20/21: `internode_max_message_size` · `inferMessageSize` and · `enqueue`, `batch_size_fail_threshold` and `WRITE_BUFFER_SIZE` — both Confirmed, does not cap — and `max_mutation_size` · `allocateBytes`) |
| Stage 4 closed, estimate refuted | **4**, all guided negative estimates: `concurrent_compactors` (2026-10-20; peak extra disk follows `min(n, 8)` × one compaction's output), `native_transport_max_message_size` (caps per request), `native_transport_max_concurrent_connections` (cluster; ≈ 1,330 B heap per idle connection), `native_transport_queue_max_item_age_threshold` (caps in throwing mode, default mode only slows growth) — all 2026-10-20; the estimates stay as filed (a refuted rejection is not re-judged) |
| Stage 4 closed, partial | **12** — fourth batch (2026-10-22): `maxTasksQueued` · `takeTaskPermit` and `· addTask` (unit Confirmed — does not cap; cluster Not confirmed), `maximumPoolSize` · `setMaximumPoolSize` (unit Confirmed — does not cap; cluster Not confirmed, heap ratio between bands); third batch (2026-10-22): `NORMAL_CHUNK_SIZE` (unit Confirmed — does not cap; cluster Not confirmed, cap never reached where the check runs), `OTCP_LARGE_MESSAGE_THRESHOLD` (unit Not confirmed, pool band missed; cluster Confirmed — does not cap), `memtable_heap_space` · `adjustMemtableSize` (unit Confirmed — caps, loose; cluster Not confirmed, no matching row); second batch (2026-10-22): `commitlog_total_space` · `:259` (unit Confirmed — caps (soft); cluster Not confirmed, no matching row — undetermined, by override 2026-10-22), `internode_application_send_queue_capacity` · `releaseCapacity` (unit Confirmed; cluster partial — byte cap exact, heap linear in C with a ~42 MiB offset), `largestRatio` (unit Refuted on the "same peak/L" sub-claim, ceiling held; cluster Confirmed — does not cap); earlier: `maximumPoolSize` (autonomous, 2026-10-21): unit Confirmed — does not cap; cluster Not confirmed (BIND-5): with the pool binding, heap follows running tasks × per-task bytes for large internode mutations only, the queue is bounded by the receive reserve; `tombstone_failure_threshold` (autonomous, 2026-10-21): unit Confirmed — caps per read; cluster partial — per-read buffer follows T, node heap peak not capped under 8 concurrent readers; `internode_application_receive_queue_capacity` · `releaseCapacity` (autonomous, 2026-10-21): unit Confirmed; cluster B3g row 3 — accounting capped exactly, heap does not track the cap for 512 KiB messages (they wait off heap in the networking pool) |
| Stage 4 closed, not confirmed (no tier Confirmed) | **1** — `flushLowWaterMark` (2026-10-22): unit and cluster Not confirmed — undetermined; each missed one frozen size prediction, readings point to "does not cap" |
| Outcome class (stage 4 taken as truth; all 58 closed) | **true positive 38**, **false positive 0**, **true negative 4**, **false negative 4**, **undetermined 12**. Of the 32 cases verified after 2026-10-16: 12 / 0 / 4 / 4 / 12 (the 26 earlier cases are all true positives) |
| Stage 4 not yet run | **0** (the five of the fourth `predicted-negative.md` batch run 2026-10-22; the five of the third `predicted-negative.md` batch run 2026-10-22; the five of the second `predicted-negative.md` batch run 2026-10-21/22; the last 7 run 2026-10-20/21; `maxHintsInProgress`, `concurrent_writes` and the four of the first `predicted-negative.md` batch filed and run 2026-10-21; no case has a run 2) |

> **Feed 3a has its first case, as of 2026-09-28.**
> `max_space_usable_for_compactions_in_percentage` was surfaced by the first
> stage-2 batch and is the first case established from that queue — and it is
> worth recording *how*: the row's own reported comparisons were both noise
> (`size() > 0`, `sstablesRemoved > 0`), and what made it a case was the
> **method name** on the helper row, which pointed the read two calls deeper.
> A 3a row's value is not always the comparison it reports.
>
> The other eight came from feed 3b — reading the source directly. That
> remains the main evidence 3b is not optional: it found the `cdc_total_space`
> ternary, which stage 1 cannot surface at all.
>
> Feed counts are not a progress bar. Only 3a has a denominator — its
> remaining work is sized in
> [`stage2-ai-preprocessing/README.md`](../stage2-ai-preprocessing/README.md)'s
> "Progress at a glance". 3b is unbounded, so there is no percentage for it.

## 3. Notes on Modules

### 3.0 compaction

- **`DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace`:** the
  folder's first **disk-scoped** case and first **pattern-(c)** case. A guard
  in `CompactionAwareWriter.getWriteDirectory()` refuses to start a compaction
  whose estimated output exceeds the target data directory's free space
  (device usable bytes minus the configurable `min_free_space_per_drive`,
  default 50MiB). Where reached, the disallow outcome is a clean
  `RuntimeException` before any writer or file exists.
  **Notable finding — the guard does not dominate the allocation.** Its only
  caller, `maybeSwitchLocation()`, consults it solely when the table has no
  disk boundaries; on the `diskBoundaries != null` path — the **default**,
  with `Murmur3Partitioner` on a node owning ranges — it selects a directory
  by key range and creates the `SSTableWriter` with **no disk-space check at
  all**. Flagged as Target-3-relevant; a stronger default-mode gap than the
  memtable or native-transport escape hatches, since the check is not
  overridden but never executed. Found via stage-3 feed **3b** (direct AI
  reading), which is also what exposed the non-domination — the CodeQL row
  alone shows only the comparison.

- **`max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction`:**
  the second compaction disk case, and **the folder's first case from feed
  3a**. An admission gate that runs *before* a compaction task starts: it sums
  this compaction's expected output with the remaining output of every
  compaction already in flight, per file store, and compares that against
  `(usable bytes − min_free_space_per_drive) × max_space_usable_for_compactions_in_percentage`
  (default 95%). Distinctive in two ways. Its disallow outcome is **not a
  refusal but a negotiation** — `reduceScopeForLimitedSpace()` drops the
  largest input SSTable and re-checks, repeatedly, so a node under disk
  pressure compacts in smaller units rather than stopping; the abort and its
  `RuntimeException` come only at the bottom of that ladder. And its
  dose-response **runs the opposite way to every other case here**: lowering
  the limit means less compaction, hence *more* data on disk, so the case must
  be judged on the shrink/abort metrics and admitted compaction size, not on
  `du`. Two escape hatches recorded: the check is skipped per table over JMX
  (`compactionDiskSpaceCheck`, `OperationType.COMPACTION` only), and an
  exception while computing it is **treated as allow** (fail-open).
  Complements rather than duplicates `DataDirectory_getAvailableSpace` — see
  that case's §11 for the axis-by-axis comparison.

### 3.1 memtable
Storage-engine module covering memtable memory allocation and pooling
(`utils/memory`, `db/memtable`). One case so far:
- **`memtable_heap_space-tryAllocate-limit`:** allocation cap in `SubPool.tryAllocate()`, gating `ByteBuffer.allocate()` for memtable writes via `HeapPool` (reached only under `memtable_allocation_type: unslabbed_heap_buffers`). Disallow parks the writer; a `markBlocking()` write overshoots the limit, so the cap is not hard. A unit test, `HeapPoolTest`, was run on 2026-09-16, before stage 4 existed — prior evidence, not a stage-4 result.
- **`memtable_offheap_space-tryAllocate-limit`:** sibling case, same `SubPool.tryAllocate()` if-check on the `offHeap` `SubPool`, reached via `NativeAllocator` — gates off-heap `Region`/native memory allocation instead of `ByteBuffer`. Note: accounting call is decoupled from the physical allocation call (see case notes). Verified via existing `NativeAllocatorTest.testBookKeeping()` (2026-09-16).

### 3.2 net
Internode messaging and native (CQL client) transport module covering inbound and outbound connection handling (`net/`, `transport/`). Three cases so far:
- **`internode_application_receive_queue_capacity-acquireCapacity-queueCapacity`:** per-connection byte cap in `AbstractMessageHandler.acquireCapacity()`, gating `Message` deserialization for inbound internode traffic. Disallow branch backpressures (registers on a wait queue) rather than dropping the message.
- **`native_transport_receive_queue_capacity-acquireCapacity-queueCapacity`:** the same `AbstractMessageHandler.acquireCapacity()` if-check as its internode sibling, reached via `CQLMessageHandler` for CQL client connections (default 1MiB vs. 4MiB). **Its disallow branch is config-dependent, and under the default it withholds nothing** — flagged as Target-3-relevant; the mechanism and both config paths are in [the case file](cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md) §5–§6b, which is authoritative. Established by deep-reading the source (feed 3b); stage 2's `transport` batch had also ranked this line. Written up 2026-09-18.
- **`internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes`:** the **send-side mirror** of the internode receive case: a per-connection byte allowance in `OutboundConnection.acquireCapacity()`, with the excess borrowed from a per-peer and a node-wide reserve (`ResourceLimits`), read by `enqueue()`. **Its disallow drops the message** and does not wait: the sender is not slowed, the request's callback is failed at once with `TIMEOUT`, and an ordinary write is **hinted** on the coordinator (a counter write is not). **Three findings that make the limit weaker than its name:** (1) the **per-peer reserve is read from the receive-side key** (`OutboundConnectionSettings:395`, with `withDefaults()` running before `withDefaultReserveLimits()`), so `internode_application_send_queue_reserve_endpoint_capacity` reaches no limit on the production path (derived from reading; unit step U10 and scenario C test it); (2) the ceiling is **per link** (`3·P·C` plus `min(P·E, G)`), and **at the defaults the reserves, not the capacity, are the large term** (12 MiB per peer against up to 128 MiB per peer and 512 MiB per node); (3) **expiry is lazy on a connected link:** a full link whose delivery is stalled refuses offers before `queue.add()`, where pruning otherwise runs, so its bytes stay pinned past the messages' deadlines. A peer that cannot be reached is the strictest case: no reserve is tried and the capacity is a hard cap. **Rule 3 holds in a weaker form than for the inbound twin:** the message exists before the check, so the branches diverge on its retention and serialization buffers, not its creation (§7 of the case). `ResourceLimits.Concurrent.tryAllocate():138` is cited as the mechanism, not filed (`undetermined.md` §5 item 3 stays open); the delivery's frame buffers come from the networking pool (`predicted-positive.md` item 10). Found via stage-3 feed **3a** (band A1, rows `OutboundConnection.java:398` and `:416`; `:416` turned out not to be a check); written up 2026-10-07.

### 3.3 hints
Hint buffering and dispatch module, covering writes stashed for temporarily-unreachable replicas (`hints/`). One case so far:
- **`MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS`:** cap (JVM system property, default 3) on how many off-heap `HintsBuffer`s the pool will ever allocate, in `HintsBufferPool.switchCurrentBuffer()`. Disallow branch blocks on `reserveBuffers.take()` until a buffer is recycled, rather than allocating a new one.

- **`max_hints_size_per_host-shouldHint-maxHintsSize`:** the other half of the
  hints story — this one bounds the **hint files on disk**, per destination
  host, where `MAX_HINT_BUFFERS` bounds the off-heap buffers. **Disabled by
  default** (`0B`, and `if (maxHintsSize > 0)` skips the comparison), which is
  a third kind of default-mode gap: not overridden like the memtable hatch, not
  unreached like the compaction guard, simply not switched on. Its disallow is
  the folder's first that **loses data** — the hint is silently skipped, the
  write still succeeds, and the replica stays short of the mutation until a
  repair. Also the first case whose pattern-(b) verdict is read at **seven**
  decision points. No metric fires on the disallow path, unlike the adjacent
  hint-window rejection four lines above.

### 3.4 commitlog
Storage-engine module covering the write-ahead commit log and its Change Data Capture (CDC) variant (`db/commitlog`). Two cases so far:
- **`cdc_total_space-processNewSegment-allowance`:** byte cap on total un-consumed CDC-hard-linked commit log segment data, compared in `CDCSizeTracker.processNewSegment()` (re-evaluated by `permitSegmentMaybe()`), which sets a per-segment `FORBIDDEN`/`PERMITTED` state read by the decision point `CommitLogSegmentManagerCDC.throwIfForbidden()` (pattern (b)). Disallow branch cleanly throws `CDCWriteException` — a real write rejection, unlike the memtable/hints/net cases' block-and-wait or backpressure semantics. `cdc_block_writes = false` turns off the rejection but not the cap: the tracker deletes the oldest un-consumed CDC links to stay under the allowance (stage 4, 2026-10-01), so data is lost instead of writes failing. Stage 4 closed this case 2026-10-01: with no consumer the node keeps `⌊limit/segmentSize⌋` links, or one more when the check's counter is stale (at most `limit + segmentSize` bytes).

- **`max_mutation_size-validateSize-MAX_MUTATION_SIZE`:** byte cap on **one commit-log entry**, compared in
  `Mutation.validateSize()` (second site `CounterMutation.validateSize()`) and enforced as the first statement of `CommitLog.add()`. Pattern (c), and
  **the guard dominates the allocation**: the off-heap serialization buffer and the segment reservation both come after it; disallow is a clean
  `InvalidRequestException`-family throw that reserves nothing. **A per-item bound, the folder's first:** it caps each entry, not any total, so the node-wide ceiling is
  `limit × N` (§8). Distinctive points: the same verdict is read at **five call sites** (coordinator, replica verb handler, commit log, read repair, virtual
  tables) of which only the commit-log one runs before new allocation, so the case rests on it; the limit is **frozen at class initialization**
  (an interface constant, restart-only) and **derived from `commitlog_segment_size / 2`** when unset, which also derives the CQL transport's message cap and
  the hints buffer size, so a sweep must hold them fixed; **at stock settings the transport's own caps equal it, so client writes are shadowed**; **replay is
  unguarded**; counter refusals are not metered. A logged batch is the client-reachable way to the commit-log site (the batchlog entry). Found via
  stage-3 feed **3a** (band A1, rows `Mutation.java:172` and `CounterMutation.java:94`); written up 2026-10-06.


### 3.5 sstable_index
On-disk index entries for wide partitions, the index summary and the key cache that holds them
(`io/sstable/format/big`, `io/sstable/indexsummary`, `cache`, `service/CacheService`). Three cases so far:
- **`column_index_cache_size-indexSamples-cacheSizeThreshold`:** byte
  threshold on one partition's serialized block index, deciding whether the
  index is retained on heap as an `IndexInfo[]` (`IndexedEntry`) or left on
  disk behind a file position (`ShallowIndexedEntry`). **The first case where
  both outcomes allocate** — the divergence is in retained size, not in
  existence, and the classes' own `unsharedHeapSize()` implementations state
  it directly. Three check sites on one constraint, and they are not all the
  same pattern: the two write-path sites are (b), while
  `RowIndexEntry$Serializer.deserialize():360` is **(a)** and is the site that
  governs steady-state heap. **The ceiling claim is per entry, not node-wide** —
  cached entries are charged their `unsharedHeapSize()` against
  `key_cache_size`, so raising the threshold buys fewer, fatter cache entries
  rather than more heap; the uncapped terms are the per-writer
  `DataOutputBuffer` of `2 × threshold` and transient flush/compaction
  entries. No flag-style escape hatch exists — but the check is
  **format-scoped** (BIG only; BTI does not reach it), and the read-path site
  reads config **live per deserialization**, so a JMX change alters the
  memory behaviour of already-written SSTables with no rewrite.

- **`row_index_read_size_fail_threshold-checkSize-failThreshold`:** byte limit on the **estimated in-memory size of one partition's
  index entry**, compared in `RowIndexEntry.Serializer.checkSize()` (pattern (c)) before `deserialize()` builds either an `IndexedEntry` or a
  `ShallowIndexedEntry`; a refusal throws, leaves nothing in the key cache and fails the read as `READ_SIZE`. **The folder's first guard on an
  estimate rather than a measured quantity,** and the estimate is made **before** `column_index_cache_size` decides whether the entry is built,
  so at stock settings it can refuse only entries that would have been shallow and bounds no heap; it binds heap only where that case's
  threshold is raised (the upstream test sets it to 1 GiB). **The guard dominates lexically and is inert conditionally:** it returns at once
  unless a `ReadCommand` is registered on the thread, which is true only while `executeLocally()` runs, so a key-cache hit, a reloaded key
  cache, an SSTable opened lazily after it returns (derived from the lower-bound merge, tested by an arm) and every range scan are not checked.
  **Off by default** (limit `null`, master switch false). The sibling of `local_read_size_fail_threshold` (same switch and reporting channel),
  but it does not require the coordinator's `trackWarnings` flag, so an unflagged read turns the abort into an `UNKNOWN` failure (derived).
  Its test design reads the **real weight** of what was built from the key cache (a refused read leaves it unchanged) and the check's own
  operands from a Byteman rule on a node. Found via stage-3 feed **3a** (band A1, row `RowIndexEntry.java:392`); written up 2026-10-06.

- **`Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE`:** the folder's first **type-bound** case. One BIG SSTable's off-heap index summary
  cannot hold more than 2^31−1 bytes of sampled entries (key + 8 B each), because entry offsets are 32-bit `int`s.
  `IndexSummaryBuilder.maybeAddEntry():204` refuses the first entry that would cross the bound, with one `ERROR` line, and **no later key is
  sampled** (the next sample position is not advanced); reads of uncovered keys still find them by scanning `Index.db` linearly from the last
  sample, so memory is traded for index reads and no data is lost. A second site, the constructor's `:108`, clamps the up-front reservation and
  raises the sampling interval when the *expected* summary (expected keys × the `cassandra.index_summary_expected_key_size` estimate, default
  64 B) would pass 2 GiB; that raised interval is persisted, so every restart rebuilds the summary (derived). No knob moves the limit, and it can
  only be lowered: the test design moves it with a Byteman offset on `getEntrySize()` and reaches the real 2 GiB unpatched with 60,000-byte keys
  at `min_index_interval` 1. Per SSTable; the node total belongs to `index_summary_capacity` (`undetermined.md` §5). BIG only. Found via stage-3
  feed **3b** (capacity-word pass), with the second site from band A2 (`IndexSummaryBuilder.java:108`); written up 2026-10-15.

### 3.6 buffer_pool
Off-heap buffer pooling for file reads and networking (`utils/memory/BufferPool`,
`utils/memory/BufferPools`). Two cases so far:
- **`file_cache_size-allocateMoreChunks-memoryUsageThreshold`:** byte ceiling on
  the `chunk-cache` pool's reserved off-heap memory, gating creation of its
  8 MiB macro chunks. **The folder's clearest pool-versus-resource case:** the
  disallow branch withholds the `Chunk`, but the caller then allocates the
  buffer straight from the OS via `ByteBuffer.allocateDirect`, counted as
  `overflowMemoryUsage` with **no ceiling of its own** — so `file_cache_size`
  bounds the pool, not the node's off-heap footprint. Uniquely well
  instrumented: `BufferPoolMetrics` publishes the limit (`Capacity`), the
  operand (`Size`) and the escape hatch (`OverflowSize`) as gauges, so §8's
  claim can be settled rather than merely predicted. Two config entries drive
  one check — the `networking_cache_size` sibling is a separate case (filed
  2026-10-15, below). Source bug noted: `MACRO_CHUNK_SIZE`'s comment says
  1 MiB, the arithmetic gives 8 MiB.
- **`networking_cache_size-allocateMoreChunks-memoryUsageThreshold`:** the same check on the
  `networking` pool (internode framing, streaming, native-protocol-v5 frames; v4 and older use
  Netty's own allocator), default `min(128MiB, heap/16)`, restart-only. Same escape as the sibling:
  a refusal becomes an unbounded `allocateDirect` overflow (no production code calls `tryGet` in
  either pool). **It differs in recycling:** `recyclePartially = false`, so a chunk returns only
  when fully free and the pool should grow to its peak demand, not fill to its limit as the
  sibling's did at stage 4 (derived, tested by U3 and scenario M). The knob therefore bounds the
  memory retained after a burst, not the burst itself. Its cluster tier drives the pool with a
  native-v5 client that stops reading: nothing in `transport` caps the response backlog. Derived and
  not observed: large (≥ 128 KiB) native-v5 requests never release their frame buffers
  (`CQLMessageHandler.onComplete()`), which arm L tests. Found via stage-3 feed **3b** (the
  capacity-word pass's second `BufferPool` instance); written up 2026-10-15.

### 3.7 marshal
Value types and their (de)serialization (`db/marshal`; the deserializers that call into it are in `db/rows`, `db` and `db/commitlog`). One case so far:
- **`max_value_size-read-maxValueSize`:** per-value sanity bound on a length decoded from a stream, compared in `AbstractType.read()` and enforced as a
  guard (pattern (c)) before `accessor.read(in, l)` allocates `new byte[l]` at full size, before any byte is read. **The guard dominates the allocation for every
  production caller** (four call sites, all passing the configured limit; the unguarded `readBuffer(in)` overload has no production caller) **but not the sibling
  primitives** (`ByteBufferUtil.readWithVIntLength` and `readWithLength`, 29 call sites with no limit, including the partition key of every inbound partition) **and
  not the write side**: nothing compares a value with it when it is written, so a value above the limit is accepted, held in the memtable and flushed, and fails only
  when read back — **as corruption**: the SSTable is marked suspect and left out of compaction, an inbound message is dropped, and a commit-log replay stops the node
  starting (replay **is** guarded, unlike `max_mutation_size`'s). **At stock settings a client cannot reach it:** the default 256 MiB is above every write-side cap, so it
  fires on damaged data only; and only the cell-value call site can fire on data a client wrote, since partition keys and the clustering values of row writes are limited to 64 KiB.
  A **per-item** bound like `max_mutation_size`; the node-wide ceiling is `limit × N` (§8). The first case whose test design measures the **bytes a thread allocates**
  across the check (`ThreadMXBean`, unit tier) and traces **allocation requests** with Byteman on a node. Found via stage-3 feed **3a** (band A1, row
  `AbstractType.java:594`); written up 2026-10-06.

### 3.8 mutation
The write object and its serialization (`db/Mutation`, `io/util/TeeDataInputPlus`). One case so far:
- **`CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT`:** byte threshold on **one mutation's serialized size**, deciding whether the mutation keeps a
  serialized copy on the heap (`CachedSerialization`, a `byte[]` of exactly that size) or only its size (`SizeOnlyCacheableSerialization`). **The second case where both outcomes
  allocate**, after `column_index_cache_size`: what the check withholds is a **copy** beside the mutation's own heap, and the divergence is in retained size. **Two check sites on one
  constraint, of different patterns:** `Mutation$MutationSerializer.serialization():451` is **(a)** and decides the copy for every mutation the node serializes; the receive side,
  `TeeDataInputPlus.maybeWrite():58`, is (a) for each write into a scratch buffer and sets a flag (`limitReached`) that `Mutation.deserialize():518` reads to decide the copy (b), and it is
  reached from every deserialization (network, commit-log replay, hints, batchlog, counters, schema). The two agree on the boundary: a copy is kept iff *T* < limit. **A per-copy bound:**
  the node-wide extra heap is about `limit × N`, *N* being the live mutations just under the limit, which nothing here or in the in-flight request caps bounds. **A JVM property,
  restart-only** (`cassandra.cacheable_mutation_size_limit_bytes`, default 1,000,000; no yaml key or JMX), frozen in a `static final` of `Mutation`. **The disallow is not a refusal:**
  the mutation is still sent, logged and applied; the node spends CPU, re-walking the partition updates at every later serialization, instead of memory. **An escape value:** a limit of
  0 or less caches nothing on the serialize side and **removes the bound on the receive side** (`limit <= 0` is the tee's "unbounded"), so the two sites read it in opposite senses.
  `validateSize()` reaches this check, so measuring a mutation below the limit builds its copy (`max_mutation_size`). Its node tier reaches the **receive site on a real node through
  commit-log replay**, holding writes in memory with a Byteman delay and counting live copies with a class histogram. Found via stage-3 feed **3a** (band A1, rows
  `Mutation.java:451` and `TeeDataInputPlus.java:58`); written up 2026-10-06.

### 3.9 read_path
Replica- and coordinator-side read and the guardrails wrapped around it (`db/ReadCommand`, `db/transform`, `service/reads/thresholds`, `cql3/statements/SelectStatement`, `cql3/selection/ResultSetBuilder`). Two cases so far:
- **`local_read_size_fail_threshold-addSize-failBytes`:** running total of the heap sizes of what **one local read command** pulls from storage,
  compared in `ReadCommand.QuerySizeTracking.addSize()` (pattern (c)); reaching the limit (`>=`) throws `LocalReadSizeTooLargeException`. **Per
  command, not per query:** each page of a paged query and each partition of an `IN` read has its own counter, so a query paged below the limit is
  never aborted. **A guard in a lazy pipeline:** it runs after the row that crosses the limit has been built (a one-row overshoot) and dominates
  every later row, but not a names-filter point read, which builds its rows into an `ImmutableBTreePartition` before the guard is attached. It
  **counts what storage yields before any filtering**, so a filtered read that returns nothing can still abort. **The disallow is swallowed by the
  replica, which answers empty with a note attached;** the coordinator decides whether the query fails (with a replica to spare it is only a
  warning). **Off by default** (limit `null`, master switch false) and **live-settable**. The first case whose cluster tier measures the bytes a
  replica thread allocates across the guard, with a Byteman rule on the read runnable. Found via stage-3 feed **3a** (band A1, row
  `ReadCommand.java:715`); written up 2026-10-06.
- **`coordinator_read_size_fail_threshold-shouldReject-thresholdBytes`:** running total of the **value bytes placed in one request's CQL
  `ResultSet`** on the coordinator, compared in `ResultSetBuilder.shouldReject()` (`size > thresholdBytes`) and read by
  `SelectStatement.maybeFail()`, which throws `ReadSizeAbortException` (pattern (b)). **Inside the result loop, after the replicas have
  answered:** the throw stops further rows being deserialized and added, the response frame (pooled direct) and, on a scan, later range
  requests, but every replica response of a single-partition read is already in memory, so that half is post hoc and recorded as not gated.
  **Permissive by one row:** it checks after the previous row is added and never checks the last, so a read of *n* rows of *s* bytes completes
  iff (*n*−1)·*s* ≤ limit. **Per request, so per page**, reset every page; aggregates count only output rows. **No exemptions:** system
  keyspaces, internal queries, superusers and driver metadata reads are refused like any client read, and the request fails outright (failure
  code 4 from protocol 5), with no replica to spare. **Off by default** (limit `null`, master switch false, shared with the replica guards) and
  **live-settable** (JMX `CoordinatorLargeReadAbortThreshold`, captured per request). Found via stage-3 feed **3b** (while writing up
  `local_read_size_fail_threshold`; stage 2 had banded the helper `shouldReject()` D); written up 2026-10-15.

### 3.10 repair
Anti-entropy repair: validation builds a Merkle tree per range and the coordinator compares the replicas' trees (`repair/`, `utils/MerkleTree`); admission of a repair (`service/ActiveRepairService`). Two cases so far:
- **`repair_session_space-split-maxsize`:** a ceiling on the **leaves of each validation's Merkle tree**, `maxsize` = 2^`min(ceil(log2 n), depth(space / RF × share), repair_session_max_tree_depth)`, compared in `MerkleTree.split()` (pattern (a)): at `size >= maxsize` no node is created and the sampling loop stops, so the cost moves to over-streaming. **The comparison runs only on the order-preserving partitioners** (with BIG SSTables); on the default Murmur3 the same `maxsize` is built in one step by `init()`, with no check. Named after `repair_session_space` (default heap / 16, live over JMX), not the queue's deprecated `repair_session_max_tree_depth`, which only caps the depth at 20; the budget binds below heaps of about 6 to 12 GiB at RF 3, the partition count on small tables. **The MiB-to-bytes conversion is 32-bit**, so from 2048 MiB (the default at a 32 GiB heap) every tree has two leaves. Per validation, not node-wide: sessions, tables and vnode ranges multiply it, and the coordinator holds trees sized by the replicas' settings. Found via stage-3 feed **3a** (band A1, row `MerkleTree.java:409`); written up 2026-10-13.
- **`repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio`:** an **admission check on data-disk usage**, `diskUsage + rejectRatio > 1` (pattern (b)). The coordinator reads it in `prepareForRepair()`, failing the repair before anything is registered; each participant reads it on `PREPARE_MSG`, answering `FAILURE_RSP` before registering; either way nothing is validated, snapshotted, streamed or anticompacted. `diskUsage` is recomputed at every call: the apparent bytes of the data directories (snapshots, backups and each hard link included) plus all memtables, over `min(used + usable, data_disk_usage_max_disk_size)`, rounded up to 5 decimals. It can exceed 1, so **the "disabled" default 0.0 still refuses above 100 %**. **Admission only:** an admitted repair's writes are neither counted nor checked again, so usage can pass `1 − ratio` by what it streams. **Every repair kind is checked**, preview and paxos-only included, despite the JMX name `IncrementalRepairDiskHeadroomRejectRatio`. The ratio is live over JMX, has no `nodetool` command, and a yaml value is not range-checked. Found via stage-3 feed **3a** (band B, row `ActiveRepairService.java:655` and its helper); written up 2026-10-15.

### 3.11 io_buffers
Reusable serialization buffers (`io/util/DataOutputBuffer` and its per-thread scratch instance), used by the commit log, mutation serialization, SSTable row writing and hints. One case so far:
- **`DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE`:** per-thread cap on the **idle** capacity of the scratch buffer. When the buffer is handed back (`DataOutputBuffer$1$1.close()`, a nested anonymous class), it is kept if it is at most the limit, otherwise it is freed at once and replaced by 128 bytes (pattern (a)). **Rule 3 is passed on retention, not withheld creation**: the buffer grows to fit the item whatever the limit, and the over-limit branch is the one that allocates (the refusal text is ready in the case's §11 if the rule is read strictly). A JVM property, restart-only (`cassandra.dob_max_recycle_bytes`, default 1 MiB, no range check), with buffers direct by default. Node-wide retention is threads × limit, and most of those threads are shared-pool workers that never time out. In-use size is up to 2(S − 1) at the commit log and unbounded at SSTable row writing. The cluster tier uses a Byteman ledger of every scratch buffer against the direct buffer-pool bean. Found via stage-3 feed **3a** (band C, row `DataOutputBuffer.java:73`); written up 2026-10-15.

### 3.12 sai
Storage-attached secondary indexes, including vector (ANN) search and its query planning (`index/sai/`). One case so far:
- **`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS`:** a **count** cap on the primary keys one **hybrid vector query** (`ORDER BY … ANN OF` plus another indexed restriction) materializes into a list on each replica, compared in `QueryController.materializeKeysAndCloseSource()` (pattern (a)); JVM property `cassandra.sai.vector_search.max_materialized_keys`, default 16,000, restart-only. **Its disallow re-plans rather than refuses:** at the (*L* + 1)-th key the list is dropped and the query switches to an ANN search of the whole index with the filter applied to each row read. The folder's first case whose disallow branch **has an unbounded cost of its own**: that plan keeps every rejected key in `processedKeys`, up to every non-matching row on the replica when the matches are far from the query vector, so lowering the limit can *raise* a query's heap; the knob caps one plan's memory, not the query's. Also: the allow plan sizes an `int` array by the whole list in every SSTable segment (about *S* × *M*, derived); memtable matches are collected before the check (references only); 0 and `Integer.MAX_VALUE` switch always and never. Per command per replica, multiplied by the hybrid queries in flight. Found via stage-3 feed **3b** (the 2026-09-22 capacity-word pass; also band-A row `QueryController.java:449`); queued as `MAX_MATERIALIZED_KEYS` and named after the `CassandraRelevantProperties` constant; written up 2026-10-14.

## 4. Autonomous files — sha256 at filing

The hash of each autonomous file as filed (before any stage-4 amendment). A later
dated amendment adds a line here with its date and the new hash.

| File | sha256 | Filed |
|---|---|---|
| `memtable_heap_space-tryAllocate-limit--autonomous.md` | `31f017feea820dd6d9df3db04ef0d5aa50a81c1733819850d1fd027795e46126` | 2026-10-05 (claude-sonnet-5) |
| `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction--autonomous.md` | `e8b505e1802722d76642c664e71a55ee2cbb23536bb88e1852edecce143ae7b1` | 2026-10-08 (claude-sonnet-5) |
| `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md` | `f086b0d230352fd2aa54016d6403a7d5d9e7a578ead3b5a32981059f36c59c3f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `prepared_statements_cache_size-storePreparedStatement-capacityToBytes--autonomous.md` | `b055bdde92e1f4861f05424defc1d19a994dd39ac4893fcceb7abe9232aba812` | 2026-10-19 stage-4 step-0 audit amendments (one cache entry per statement, test-yaml knob, live-heap instrument, two over-count rows); the frozen version | (hash above after the amendments; section D feedback added after the freeze, 2026-10-19) |
| `internode_max_message_size-inferMessageSize-size--autonomous.md` | `b204d619b862d6f9a78a9e9860ca7ebb41aabe94fe9dea083dce8c8ffe0777fb` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md` | `b8f001f77ddaae019ccb673e3a269edb3094e3c2de93734a1f85b5409b0e5b3f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `max_mutation_size-allocateBytes-slabCapacity--autonomous.md` | `47acc75811952dcd70e6b2ad0fd038833c1f0a2afe4da8e9fcde9a23c4cbf66f` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `WRITE_BUFFER_SIZE-append-remaining--autonomous.md` | `2ba8c54eb9f494ef6d6d74848ad558b2681634852e4693dcab51f2c489760e38` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md` | `239cf86ea5e682b82b6b8f0de86edeafada6a7bb03dae85c5f929c3a43a336a0` | 2026-10-19 (autonomous agent, rejected-entry write-up) | (hash after the 2026-10-19 Judgment → Estimate label rename) |
| `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md` | `9edf2196d46995984e00dd37d7497dc48fafc363bfc545e17196520f555154f0` | 2026-10-20 stage-4 step-0 audit amendments (R1–R5: default-value run, networking-pool gauges, wire/disk arithmetic, metric path, hints off); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_max_message_size-inferMessageSize-size--autonomous.md` | `46d2788e90644e4835d69e728ec6cac99769453d7dbf0f6f30ccfaca2e5eb437` | 2026-10-20 stage-4 step-0 audit amendments (R1–R4: default run R0, networking-pool gauges, hints off, keep derived client frame size); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_max_message_size-inferMessageSize-size--autonomous.md` | `5b2999dd79434b62bf7fc612ce3997fce27382a7d53b4d8ae84a159ff174e6df` | 2026-10-20 stage-4 runbook fix (B2h control limit `Integer.MAX_VALUE − 1`, B3d paged count; found in the shakedown before run 1, run 1 used it) and section D feedback, after the run | (not a new frozen version: the run used the frozen `46d2788e…` design with these two fixes) |
| `max_mutation_size-allocateBytes-slabCapacity--autonomous.md` | `8ecb18b22d2fe470942b0dbbb77bfb1636fddd9cda4c3f5b0058d467dfe352ca` | 2026-10-20 stage-4 step-0 audit amendments (R1–R3: `MAX_HINT_BUFFERS` and 17 MiB rows, 17 MiB bullet corrected, exact flush period); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `WRITE_BUFFER_SIZE-append-remaining--autonomous.md` | `55bf043e43ebcbb70b926e214b47356edd69ce76a20a9d4aee7d832563bc5ab6` | 2026-10-20 stage-4 step-0 audit amendments (R1–R3: memory-control row, truncate table between runs, citation); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md` | `b63484779685490d51411d3ac753f84f9cd78c29e146076c69d43940b7ddb631` | 2026-10-20 stage-4 step-0 audit amendments (R1–R5: mutation that must fail, ceilings Q + reserve, write timeout, backlog and disk plan); the frozen version | (hash above after the amendments; section D feedback added after the freeze, if any) |
| `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous.md` | `538cbfa9dd765a1f338f05c15df5474f9c3fc4cc18b6b64c0fb4a9c94baf71a3` | 2026-10-20/21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the frozen design above) |
| `max_mutation_size-allocateBytes-slabCapacity--autonomous.md` | `9fc9bca6116a207581f01b61f1df48e97dd98fd2ca1241e67228c2a73e7fcce2` | 2026-10-20/21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the frozen design above) |
| `WRITE_BUFFER_SIZE-append-remaining--autonomous.md` | `4a4b3b8680dbe3e5adefa0ebf6c9ee44e5504df01b5c899a4a5bc67a20ea20d6` | 2026-10-20/21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the frozen design above) |
| `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous.md` | `dd512ec51def6f1eaa85e37cc37e5383a6bfd4c9741763b32d7a37f445ea08da` | 2026-10-20/21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the frozen design above) |
| `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md` | `2cda58a133d25f3aa3b6546739289d9d525cfcc178557e647b4769f8249e39e4` | 2026-10-21 (autonomous agent, subagent) | (hash as filed) |
| `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md` | `af8d24c24d212b7c05896cec190eeeaa3eb6205ad75a378c0f69f80999dc3312` | 2026-10-21 stage-4 step-0 audit amendments (R1–R6: clones and test heap, compiling mutation builder, loopback addresses, stress `retries=0`, no node log line for the refusal, own-PID check); the frozen version | (hash above after the amendments) |
| `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous.md` | `a8405af450f7f934e88f5b869ece4b16f85ea9d4145525425ccb7ac699c15dd6` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the frozen design above) |
| `concurrent_writes-takeWorkPermit-workPermits--autonomous.md` | `559d1f85512a403b6cff0ee56fbf8e867ae4f9f4e9121416f2578a00d26076f8` | 2026-10-21 (autonomous agent, subagent) | (hash as filed) |
| `concurrent_writes-takeWorkPermit-workPermits--autonomous.md` | `af2af2e5a979c7073fcb6df22cabb0900b032f28294fc8928659517b6d59c454` | 2026-10-21 stage-4 step-0 audit amendments (R1–R6: stress `no-warmup`, one lifetime per steady run, PC0 reference arm, heap statistics and "rises with N", R0-below-cap row, unit repeat and terms); the frozen version (the unit tier ran on it) | (hash above after the amendments) |
| `concurrent_writes-takeWorkPermit-workPermits--autonomous.md` | `12fb743b3319bcccb80eb317b87fbae1a1162f9b22f69fd2e087b7a11ba896b2` | 2026-10-21 stage-4 runbook fixes D1–D2 (PC/PC0 receive queue 0B so the per-IP cap can bind; memtable-separated queue heap in R0), found by the cluster instrument check before run 1; B1 and B2f–B3g unchanged | (the version the cluster tier ran on) |
| `concurrent_writes-takeWorkPermit-workPermits--autonomous.md` | `beb9abf09c1103ae11c8a45a9b83847b0bb3712ad269649316db994bc5fe6186` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the versions above) |
| `maximumPoolSize-takeTaskPermit-workPermits--autonomous.md` | `dcfe1d905963f948c74f21d077660e70dfee02de42544d6abd78fe995e68c41e` | 2026-10-21 (autonomous agent, subagent; first `predicted-negative.md` batch) | (hash as filed) |
| `maximumPoolSize-takeTaskPermit-workPermits--autonomous.md` | `c004650ff618cd601bc3b7dd5def1409f8920f54fc8ba5446dc945c35e89213c` | 2026-10-21 stage-4 step-0 audit amendments (R1–R5: stress `no-warmup`, statistics and terms, drift repeat, unit Phase 4, bind arm with rows BIND-1–5); the frozen version | (hash above after the amendments) |
| `maximumPoolSize-takeTaskPermit-workPermits--autonomous.md` | `e50549b201956d904e89363d35f5f01beb45d8eee99398dbdd542d0aaee8b0dd` | 2026-10-21 stage-4 runbook fixes D1–D2 (unit JVM GC flags; Byteman 2 s hold at `MutationVerbHandler.doVerb` replaces group commit, reserve reading `using_bytes`); cluster tier restarted | (the version run 1 ran on) |
| `maximumPoolSize-takeTaskPermit-workPermits--autonomous.md` | `c5ab748a9bcd21985bc419cf7c0e5d3d516407123932d941e952d630b9dc6f11` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the versions above) |
| `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md` | `068aceefe840d89b516cafaa805e695242b4fd79214c935d864fac19cf9c6c82` | 2026-10-21 (autonomous agent, subagent; first `predicted-negative.md` batch) | (hash as filed) |
| `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md` | `5bc45c0d58fdd575b430537c561d50d4dfe94d830cbbd126af294e9d8e9a90b1` | 2026-10-21 stage-4 step-0 audit amendments (R1–R7: PROBE file, unit rows and mapping, default capacity value, RssAnon sampler and TRACE appender, cluster rows and Effect mapping, step 6 required, environment; the unit tier ran on it); the frozen version | (hash above after the amendments) |
| `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md` | `72266fd36376045df55fac0acc2da2d6f1522ff3038ed19b099a6d6b96c52941` | 2026-10-21 stage-4 runbook fixes D1–D3 (stress key population, ALTER names both intervals, R5 row compares only where ΔT ≥ 16 MiB); cluster attempt 2, the counted one, ran on it | (attempt 1 ran on an intermediate version after D1–D2, not counted) |
| `index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md` | `3c2498d3ef77398b7788d74de4e9e80158c4e601584c7f88699a4701641f8619` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the versions above) |
| `commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md` | `3c79fe51604d5153fb70a3953e0117a150b649426f1658e6bf04749d4326f76e` | 2026-10-21 (autonomous agent, subagent; first `predicted-negative.md` batch) | (hash as filed) |
| `commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md` | `6a58e10faa5efc74f005dbcb4c3aad12aeffd06ca2372c8ee55be15785f78a8d` | 2026-10-21 stage-4 step-0 audit amendments (R1–R4: 1 GiB test heap so `memtable_heap_space` 768 MiB, required `COMMITLOG_DIRTY` count and test-log path, verdict labels and three rows, cluster paths/ulimit/ps check); the frozen version | (hash above after the amendments) |
| `commitlog_total_space-maybeFlushToReclaim-unused--autonomous.md` | `86b89feea68ccd679cf03b2220814165e8da3b5ec3010d391e04fdd32e740328` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the versions above) |
| `tombstone_failure_threshold-countTombstone-tombstones--autonomous.md` | `1fc393050f3a350d255f5478fc5d4805372fcfdc6958457f36c21cc6e09f4bf7` | 2026-10-21 (autonomous agent, subagent; first `predicted-negative.md` batch) | (hash as filed) |
| `tombstone_failure_threshold-countTombstone-tombstones--autonomous.md` | `9e62de3a079dff64b91da43ece36e12c03ec93cffeb5709e3f6b140fed1f5c89` | 2026-10-21 stage-4 step-0 audit amendments (R1–R6: tombstones written by `UPDATE … SET v = null` (the filed `INSERT` null wrote live rows), test initialisation, timeouts and ulimit, decisive criteria, node-wide allocation reading, three conclusion rows); the frozen version | (hash above after the amendments) |
| `tombstone_failure_threshold-countTombstone-tombstones--autonomous.md` | `677b8abbe2e50fe4094fd6de070dbf6efc3724c779e0e7ef2939a0f0a7e318e4` | 2026-10-21 stage-4 runbook fix D1 (unit yaml read thresholds off); unit tier restarted | (the version the unit tier ran on) |
| `tombstone_failure_threshold-countTombstone-tombstones--autonomous.md` | `b509de1d184a2d23fe3cbe79c7c7011af9371ee5023fc71efb286aa58713041f` | 2026-10-21 stage-4 runbook fixes D2–D3 (old-generation rise under the shipped G1 options; JMX HeapPoll replaces `jstat`) | (the version the cluster tier ran on) |
| `tombstone_failure_threshold-countTombstone-tombstones--autonomous.md` | `f617adea89cdfb317d1d94c410c689ba96cf27d5d5e9c24daf75d719e4f1e1f5` | 2026-10-21 stage-4 section D feedback, after run 1 | (not a new frozen version: run 1 used the versions above) |
| `commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md` | `98750006112a1bd1f88b737545ca3fcc918aebfcab3e83f94bb77f0bfd025ffe` | 2026-10-21 (autonomous agent, subagent; second `predicted-negative.md` batch) | (hash as filed) |
| `commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md` | `c23bfe2636036d9594bc71f2baf48d54c23dc8c5a9213f4d17f07dfbfbd0f58c` | 2026-10-21 stage-4 step-0 audit amendments (R1–R5 + i5 line-259 arm, H1 instrument note); the frozen version | |
| `commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md` | `cf7a8ff999819f0e59498379e8dd8675ede51c7f8184fc85c207f826b0d05513` | 2026-10-21/22 stage-4 cluster row 4c added after attempt 1 (tier restarted; a post-reading change) | |
| `commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md` | `1879a522583739b1ce813e051f559cb27f9196d05eb812c7b4ac33d2bb72ef33` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md` | `b57c9c6b6804ad8e6d023ddedaebccf9bb5b622494a9b46ebb7944f69a28693c` | 2026-10-21 (autonomous agent, subagent; second `predicted-negative.md` batch) | (hash as filed) |
| `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md` | `fd6885707e04499847f692c40abd7e537db95b34964aec164fb53c0d1b95c1d1` | 2026-10-21 stage-4 step-0 audit amendments (R1–R8: forced-upsample restore, stress key population, RssAnon, Byteman operand reading, rows); the frozen version | |
| `index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md` | `49ad542e67dd2a23729efc24beda729148c5506cdc04b25937e0840ee07b7031` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md` | `49e904a2b820d8ee83baa9a9cdab3ce66925a6c8d86cf9cd11045a4c6b83bec9` | 2026-10-21 (autonomous agent, subagent; second `predicted-negative.md` batch) | (hash as filed) |
| `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md` | `658ca786eb99ac22c677789f4b233e81b74b06eef0cfafe941b27a3aba3f7f50` | 2026-10-21 stage-4 step-0 audit amendments (A1–A9: mutants, `native_transport_timeout`, JMX poller, heap noise rule, rows); the frozen version | |
| `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md` | `b48dd16e50617e76ade68f25651d03f566c658111b9eb15bff33bdcfd6db3479` | 2026-10-21/22 stage-4 runbook fix D2 (U2 blocks delivery by parking the event loop; unit tier restarted) | |
| `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous.md` | `e3594f1d5431c41672cad5f5f676a0fef16a0b537e4d55c114160a361aff8c42` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `memtable_heap_space-needsCleaning-nextClean--autonomous.md` | `ed2d18f332d25b6182e92e8fc58c4719647fd0067da682744bea4e6959bbaf1f` | 2026-10-21 (autonomous agent, subagent; second `predicted-negative.md` batch) | (hash as filed) |
| `memtable_heap_space-needsCleaning-nextClean--autonomous.md` | `0378bf7d45276199e3bb3971324e5b5224cd7fc636c2927a11fd676289500bad` | 2026-10-21 stage-4 step-0 audit amendments (U1–U2, K1 (O1 citation; Byteman pool trace), K3–K4); the frozen version | |
| `memtable_heap_space-needsCleaning-nextClean--autonomous.md` | `6ef2f91f872d02496b7003a52c249e5d1a866428686d9c3a017c9a6828daaf04` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `largestRatio-flushLargestMemtable-largestRatio--autonomous.md` | `d33bf316c3471b704783e5e2682011f8c69b1b69e88ada1c1c56b1d5c7102c3c` | 2026-10-21 (autonomous agent, subagent; second `predicted-negative.md` batch) | (hash as filed) |
| `largestRatio-flushLargestMemtable-largestRatio--autonomous.md` | `60974bb2f52e9e7cf598471e9fcb347e836f3ef1cde9a4fd40b06b64c81e2ab3` | 2026-10-21 stage-4 step-0 audit amendments (R1–R8: reworded same-peak claim, M-never cluster run, JMX poller, rows); the frozen version | |
| `largestRatio-flushLargestMemtable-largestRatio--autonomous.md` | `54e8da0e4277c0946d57ff469a9c15403b51253f6ee47b2f95fa3add0113d03d` | 2026-10-21/22 stage-4 runbook fix D1 (U2 attempts); cluster then ran on `45a1ce01d51a0cc1487d368c5465191115ffc8a62efb1b8603f7829f8a6af302` after D2 (old gen from gc.log) | |
| `largestRatio-flushLargestMemtable-largestRatio--autonomous.md` | `91e44954d85185e2b90992f4cbf1e595660b8bbc73f31ed4b708d8fc35aede67` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `commitlog_total_space-maybeFlushToReclaim-unused-2--autonomous.md` | `9f6d8a21399b177801003acd3eb39abd655a6aa5926d525f5eb809956b66b546` | 2026-10-22 Jingsong override recorded in section D and row 4c struck in B3g | (not a new frozen version) |
| `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md` | `af9a7512118d8b97ced5faa65874927fa68851170b36cf0fd6623750be958da5` | 2026-10-22 (autonomous agent, subagent; third `predicted-negative.md` batch) | (hash as filed) |
| `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md` | `b4a452ceeeaecb18b5b0091612d59443e48b728c364ec8c20ee2d604c5bdd94e` | 2026-10-22 stage-4 step-0 audit amendments (U1–U3, K1–K4: dSize, direct memory, Byteman slab trace, exact rows, workload sized); the frozen version | |
| `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md` | `e38add515e31dd6b0b83b216f8b0a31a9a086ee090924cda090b82de5f077995` | 2026-10-22 stage-4 runbook fix D1 (`fill()` reset under `-ea`) | |
| `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md` | `fcccaef08fac920f9b13dcd2f419bc0bbb72b88252b26cbf149bbd6a7aca5afc` | 2026-10-22 stage-4 runbook fix D2 (stdout from the console log); both counted tiers ran on this | |
| `NORMAL_CHUNK_SIZE-freeUnusedPortion-capacity--autonomous.md` | `72a15084e82cfb7881e3856e1815b988295100ce7ddc0d9bad44fd071903e8da` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md` | `d33cf16717796b29514e1a5231c07e58d59a493396b49a28acafa982ec0d426f` | 2026-10-22 (autonomous agent, subagent; third `predicted-negative.md` batch) | (hash as filed) |
| `OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md` | `6b3a899e9628ea09f183789915bd073767d8cc00ce0da890dd29df7862a105a3` | 2026-10-22 stage-4 step-0 audit amendments (S4-A1–A11: receive-side reserve key, stress pinned to n1, ordered rows U1–U9 / C1–C7, pool bound); the frozen version | |
| `OTCP_LARGE_MESSAGE_THRESHOLD-doRun-maxSendBytes--autonomous.md` | `f63b40250494cfb25d116e3fab952c0e09064234b3144e75496df307a7929884` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md` | `16b0da55a6454033fd77d712e0e921f2d331565af0dd9d9f6c6dc538f84295e9` | 2026-10-22 (autonomous agent, subagent; third `predicted-negative.md` batch) | (hash as filed) |
| `flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md` | `f754e36f8f7ab5edc281986809cf4291722348b29f732ba63c7ed0f7a8bcf69d` | 2026-10-22 stage-4 step-0 audit amendments (A1–A11: flip instrument, rows, timed stress, JMX sampler, Byteman stall/resume); the frozen version | |
| `flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md` | `b797d658c074694d4e0ed46386f63d414f519fb3f23f87840c1f57c0c864fb98` | 2026-10-22 stage-4 runbook fixes (socket buffers dropped, Byteman rule moved); the cluster tier ran on this | |
| `flushLowWaterMark-doRun-flushLowWaterMark--autonomous.md` | `42fbac8c0966f72c848024aae58fde81296b3bc8892600eb1340a6ba881bf119` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md` | `c60e0fd5e18f9e7240d2a5e850cfab2535f9f3047cc48154c4c01cef6572dbd9` | 2026-10-22 (autonomous agent, subagent; third `predicted-negative.md` batch) | (hash as filed) |
| `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md` | `7c7fa7a839d0d1568564436569197db31eff1d70fa9becbdd793f5684ad80ebd` | 2026-10-22 stage-4 step-0 audit amendments (R1–R7: default-value run, verdict lines U1–U5 / C1–C7, timeouts, citations); the frozen version | |
| `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md` | `f0f7942d101f81e2917547359c5727aa94003e3fbff9de13da0a2a718b92a451` | 2026-10-22 stage-4 runbook fix D1 (`commitlog_segment_size` 1536MiB, `max_mutation_size` 16MiB); both tiers ran on this | |
| `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous.md` | `1b2d84d3564ebba5509bae62f19550de5436e9a14b5b534df53a01954c7bae73` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `memtable_heap_space-adjustMemtableSize-0--autonomous.md` | `167458f9301dd6abac55d54685592393fbf2db4efbfe68dcc6d90b2c81f31724` | 2026-10-22 (autonomous agent, subagent; third `predicted-negative.md` batch) | (hash as filed) |
| `memtable_heap_space-adjustMemtableSize-0--autonomous.md` | `0600e3b3a0cd633b84e30ce24821ddb19797613322eaf750454e8efaa831c06d` | 2026-10-22 stage-4 step-0 audit amendments (A-U1–U2, A-K1–K5: default run, segment buffer 16MiB, JMX sampler, ordered tables); the frozen version | |
| `memtable_heap_space-adjustMemtableSize-0--autonomous.md` | `619815786b543db6429cde53915e26a75e81245c347ddb39667daeec8dccca81` | 2026-10-22 stage-4 runbook fix D1 (`CREATE INDEX IF NOT EXISTS`; cluster tier restarted before any load) | |
| `memtable_heap_space-adjustMemtableSize-0--autonomous.md` | `f8f20fdd8c4c51d73fe46d451e7bd47c68441c728c22a64a7c4a9ff92623791f` | 2026-10-22 stage-4 section D feedback, after run 1 | (not a new frozen version) |
| `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous.md` | `3a7804acd1f3b1830dc117f287b65208d377e1afb34ff1b4997cbedc9baecfb3` | 2026-10-22 stage-4 step-0 audit amendments (R1–R10, R4a); the frozen version (section D "none yet") | (the version run 1 used; on disk with section D filled: `c7a37e8a…5391`). The other four fourth-batch files' as-filed, frozen and run-time hashes are in their results files §1. |
