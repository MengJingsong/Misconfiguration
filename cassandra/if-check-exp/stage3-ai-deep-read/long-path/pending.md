# Stage 3 — qualified, pending write-up

Lines stage 3 has **read against the three rules and accepted**, but which do
not yet exist as case files in [`cases/`](cases/). They are findings, not a
queue: the judgement is made: what remains is the write-up (all nine
questions of [`../../README.md` §5](../../README.md#5-required-content-per-if-check-case),
citations checked against the pinned tag).

An entry leaves this file when its case file lands in `cases/` and its row is
added to [`_INDEX.md`](_INDEX.md). Nothing else belongs here — rows still
*awaiting* a read live in
[`../../stage2-ai-preprocessing/bands.md`](../../stage2-ai-preprocessing/bands.md),
which is stage 3's 3a queue.

> Moved here 2026-09-23 from `bands.md`. They had been recorded there
> because the capacity-word pass predates the stage folders — but they are stage-3
> judgements (source read, three rules applied), and a stage-2 file states in
> its own header that it never applies those rules.

## Write-up queue (updated 2026-10-15)

**No candidate case** is qualified and unwritten: items 1–13 are filed (item 8, `MAX_MATERIALIZED_KEYS`, on 2026-10-14 as `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`; items 9–13 on 2026-10-15). (Items 1 to 5, `max_mutation_size`, `max_value_size`, `CACHEABLE_MUTATION_SIZE_LIMIT`, `local_read_size_fail_threshold` and `row_index_read_size_fail_threshold`, were filed 2026-10-06, item 6, `internode_application_send_queue_capacity`, on 2026-10-07, item 7 on 2026-10-13 as `repair_session_space`, and items 9 to 13 on 2026-10-15: `Integer_MAX_VALUE`, `networking_cache_size`, `coordinator_read_size_fail_threshold` (judged and qualified as (b) the same day), `repair_disk_headroom_reject_ratio` and `DOB_MAX_RECYCLE_BYTES`; all are struck below.) Details of each are in the sections below.
Filed entries stay in the section tables, struck through, only as a trail; the index of
filed cases is [`_INDEX.md`](_INDEX.md). Suggested order is cheapest and clearest first.

| # | Candidate (constraint name, §6.1) | Rows | Pattern | Notes for the write-up |
|---|---|---|---|---|
| 1 | ~~`max_mutation_size`~~ **— FILED 2026-10-06**, [case](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) | `Mutation:172`, `CounterMutation:94` | (c) | Throws before `CommitLog.add():311` reserves segment space; the two sites are one constraint. |
| 2 | ~~`max_value_size`~~ **— FILED 2026-10-06**, [case](cases/max_value_size-read-maxValueSize.md) | `AbstractType:594` | (c) | **Does not dominate**: `readBuffer(in)` passes `Integer.MAX_VALUE`; list both call-site sets. *(Corrected in the case, §5 and §10: that overload has no production caller; the non-domination is the sibling primitives and the write side.)* |
| 3 | ~~`CACHEABLE_MUTATION_SIZE_LIMIT`~~ **— FILED 2026-10-06**, [case](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md) | `Mutation:451`, `TeeDataInputPlus:58` | (a) | **One case** (serialize and deserialize sides); JVM property `cassandra.cacheable_mutation_size_limit_bytes`. Both branches allocate. *(In the case: the receive site is split, (a) for the buffer writes and (b) for the copy; `limit <= 0` is unbounded on the receive side and "cache nothing" on the serialize side, so a value of 0 is an escape value; §5 and §10.)* |
| 4 | ~~`local_read_size_fail_threshold`~~ **— FILED 2026-10-06**, [case](cases/local_read_size_fail_threshold-addSize-failBytes.md) | `ReadCommand:715` | (c) | Per-query running total; aborts. The warn twin is already rejected (Rule 3). *(In the case: the total is per **command**, not per query; the check runs after the row that crosses the limit is built; a names-filter point read builds its rows before the guard; it counts before the row filter; the replica swallows the abort and answers empty, and the coordinator decides; §5, §6b and §10. The warn twin, `ReadCommand:724`, was not in `rejected.md` and is recorded there now.)* |
| 5 | ~~`row_index_read_size_fail_threshold`~~ **— FILED 2026-10-06**, [case](cases/row_index_read_size_fail_threshold-checkSize-failThreshold.md) | `RowIndexEntry:392` | (c) | Sibling of 4; throws before `new IndexedEntry` at `:362`; cross-link with the filed `column_index_cache_size`. *(In the case: the estimate is made **before** `column_index_cache_size` decides whether the entry is built, so at stock settings it refuses only entries that would have been shallow; the guard is inert unless a `ReadCommand` is registered on the thread, so key-cache hits, SSTables opened lazily after `executeLocally()` returns (derived) and scans are not checked; §4, §5, §8 and §10.)* |
| 6 | ~~`internode_application_send_queue_capacity`~~ **— FILED 2026-10-07**, [case](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md) | `OutboundConnection:398`, `:416` | (b) | Send-side mirror of the two inbound cases; disallow **drops** the message (`onOverloaded`). *(In the case: `:416` is not a check, the reserve comparison is `:419` into `ResourceLimits:138`; the drop also fails the request's callback at once and, for a plain mutation, submits a hint; **the per-peer reserve is read from the receive-side key** `internode_application_receive_queue_reserve_endpoint_capacity` on the production path (derived, tested by unit step U10 and scenario C); the ceiling is per link, `3·P·C + min(P·E, G)`, with the reserves the large term at the defaults; a connected, full, non-draining link sheds no expired message by itself; Rule 3 holds in a weaker form, retention rather than creation; §1, §4, §6b, §7, §8 and §10.)* |
| 7 | ~~`repair_session_max_tree_depth`~~ **— FILED 2026-10-13 as `repair_session_space`**, [case](cases/repair_session_space-split-maxsize.md) | `MerkleTree:409` | (a) | The knob is a `min` cap on depth: establish which term binds before designing §9. *(In the case: all three terms of the `min` bind in different regimes, and the case is named after `repair_session_space`, the budget a user tunes, since `repair_session_max_tree_depth` is deprecated and only caps the depth at 20; the comparison runs only on order-preserving partitioners, `init()` sizes the tree on Murmur3; and the MiB-to-bytes conversion overflows from 2048 MiB, giving two-leaf trees. §4, §5, §10.)* |
| 8 | ~~`MAX_MATERIALIZED_KEYS`~~ **— FILED 2026-10-14 as `SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`**, [case](cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS.md) | `QueryController:449` | (a) | Returns `null`, discarding the list; forces a different query path. Trace its constant. *(In the case: the constant is the JVM property `cassandra.sai.vector_search.max_materialized_keys` (`CassandraRelevantProperties.SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`, default 16,000), which names it; pattern (a), with the caller's `null` test recorded as the plan switch; reached only by hybrid top-k queries, once per query per replica; the list stops at *L* + 1 keys, but the ANN-then-filter plan it switches to keeps every rejected key, a cost the limit does not bound; §4, §5, §6b, §8 and §10.)* |
| 9 | ~~`Integer_MAX_VALUE` (index summary)~~ **— FILED 2026-10-15**, [case](cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE.md) | `IndexSummaryBuilder:204`, `:108` | (a) | Constraint is a **type bound**; §6.1 naming needs a judgement call; both sites in Location. *(In the case: the refusal at `:204` writes nothing and does not advance the next sample position, so no later key is sampled — one ERROR per summary — but uncovered keys stay readable through a linear `Index.db` scan from the last sample, so memory is traded for index reads; `:108`'s raised interval is stored in `Summary.db` and disagrees with the table's, so every restart rebuilds that summary (derived); the writers are at `:126-127`; the ERROR advises a nonexistent `min_sampling_level`; named `Integer_MAX_VALUE` as the class-qualified JDK constant, §4; the limit is moved in §9 by a Byteman offset on `getEntrySize()`. §4, §5, §6b, §10.)* |
| 10 | ~~`networking_cache_size`~~ **— FILED 2026-10-15**, [case](cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold.md) | none | (a) | Same check as the filed `file_cache_size`, second pool; shorter write-up, point to the sibling. The outbound delivery's off-heap frames (`FrameEncoder.Payload`, [`FrameEncoder.java:32`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L32) and [`:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/FrameEncoder.java#L64)) draw from this pool; the filed `internode_application_send_queue_capacity` case records them as outside its byte count (§7). *(In the case: the same check, but this pool has `recyclePartially = false`, so the sibling's fill-to-the-limit finding should not carry over and the knob bounds post-burst retained memory, not the peak; `FrameEncoder.Payload` is one caller among several (Netty read buffers on internode and native-v5 channels, frame stashes, LZ4 frames, streaming), and v4 clients do not use the pool; no production code calls `tryGet` in either pool; the native-v5 response backlog has no cap, and large (≥ 128 KiB) v5 requests appear never to release their frame buffers (derived, arm L); §5, §6, §8 and §10.)* |
| 11 | ~~`coordinator_read_size_fail_threshold`~~ **— FILED 2026-10-15**, [case](cases/coordinator_read_size_fail_threshold-shouldReject-thresholdBytes.md) | `SelectStatement.maybeFail():1057-1080`, called at `:1092`, `:1104`, `:1132` | (b) | **Unjudged; found 2026-10-06 while writing items 4 and 5, and not surfaced by stage 2 (feed `3b`).** The coordinator-side sibling of item 4: `ResultSetBuilder.shouldReject()` (`size > threshold`, `ResultSetBuilder.java:95-98`) compares the sum of the selected value lengths, and `maybeFail()` runs after each row is added to the result (`:1126-1132`), so it may be post hoc (Rule 3), as `BatchStatement:352` was. Read the result-builder path, and decide (b)/(c) or refuse, before designing a §9. *(Judged and filed 2026-10-15, pattern (b): `shouldReject():97` returns the verdict and `maybeFail()` throws. It is post hoc only in half: every replica response of a single-partition read is resident before the first check, but the throw withholds the rest of the result set, the response frame and later range batches. The check runs after the previous row is added, not "after each row", and the last row is never checked, so a result can exceed the limit by one row. It is per request (per page), exempts neither system keyspaces nor internal queries, and fails the request with no replica to spare. "Not surfaced by stage 2" is loose: the helper `shouldReject()` is a band-D row (batch 35). §5, §8 and §10.)* |
| 12 | ~~`repair_disk_headroom_reject_ratio`~~ **— FILED 2026-10-15**, [case](cases/repair_disk_headroom_reject_ratio-verifyDiskHeadroomThreshold-rejectRatio.md) | `ActiveRepairService:655`, helper `verifyDiskHeadroomThreshold()` | (b) | **Qualified by the band-B pass, 2026-10-13 (feed `3a`).** `diskUsage + rejectRatio > 1` ([`ActiveRepairService.java:655`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L655)) returns `false`; two decision points read it before any streaming or anticompaction: the coordinator's `prepareForRepair()` fails the repair ([`:667-668`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/ActiveRepairService.java#L667-L668)), a participant answers `PREPARE_MSG` with a failure ([`RepairMessageVerbHandler.java:117-123`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/RepairMessageVerbHandler.java#L117-L123)). Disk, not memory. **Write-up questions:** (1) default `0.0`, i.e. **off** ([`Config.java:352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L352)), range [0, 1] (`DatabaseDescriptor.java:5347`); (2) **admission only**: nothing re-checks a repair once admitted, so usage can pass `1 − ratio` by what that repair writes; predict the overshoot; (3) `diskUsage` is `DiskUsageMonitor.getDiskUsage()` ([`:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/disk/usage/DiskUsageMonitor.java#L138)): data-directory bytes **plus all memtables**, over used + usable, with the total capped by `data_disk_usage_max_disk_size` (`:158`), which makes the limit moveable on a big disk for §9; (4) the JMX names say "incremental", but the check runs for **every** repair; check preview repairs. Sibling of the filed compaction case's admission check; the pending-compactions check beside it (`:641`) is refused (count). *(In the case: the default 0.0 is not off. It refuses whenever `getDiskUsage()` exceeds 1, which happens because memtables are added after the cap; the upstream test uses 1.5. The [0, 1] range is enforced only by the JMX setter, and a yaml value is never validated. The cap is `:157-159`. The usage is recomputed at every call (a directory walk of apparent sizes, counting snapshots, backups and hard links, not the commit log or hints), so it is never stale and never -1. The check is admission only (two callers) and runs for every repair kind, including preview, validate and paxos-only. A non-preview repair writes its `parent_repair_history` row before the check. Each node judges only its own disk. §4, §5, §8, §10.)* |
| 13 | ~~`DOB_MAX_RECYCLE_BYTES`~~ **— FILED 2026-10-15**, [case](cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE.md) | `DataOutputBuffer:73` | (a) | **Qualified by the band-C pass, 2026-10-13 (feed `3a`; band A3 pointed to it).** In the thread-local `scratchBuffer`'s `close()` ([`DataOutputBuffer.java:63-81`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/DataOutputBuffer.java#L63-L81)), `buffer.capacity() <= MAX_RECYCLE_BUFFER_SIZE` keeps the buffer for the thread's next use; otherwise it is freed (`setBuffer()` cleans a direct buffer, `:186`) and replaced by a 128-byte one. The limit is the JVM property `cassandra.dob_max_recycle_bytes`, default 1 MiB ([`CassandraRelevantProperties.java:204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/CassandraRelevantProperties.java#L204)); buffers are **direct** unless `cassandra.dob.allocate_type` says otherwise (`:183`). Users: `CommitLog.add():306` (every write), `Mutation.java:453`, `:491`, `UnfilteredSerializer.java:195`, `HintsWriter.java:77`, `SystemKeyspace.java:774`. **Rule 3** is passed on README §3.6's failing condition ("zero observable effect"): the branches differ in what stays resident, though neither withholds creation; flag this reading in the write-up. **Write-up questions:** (1) it bounds **idle retention only**: while in use the buffer grows to the item (up to about twice `max_mutation_size`, A3's growth rows), so the case's ceiling is threads × limit *between* uses; (2) count the threads that touch the scratch buffer (mutation, read, hints, transport stages), since node-wide retention is that count × limit; (3) measure with the `direct` `BufferPoolMXBean` or NMT, not RSS; (4) cross-link the two filed cases that already describe this recycle (`max_mutation_size` §5, `CACHEABLE_MUTATION_SIZE_LIMIT`). *(In the case: the check is in `DataOutputBuffer$1$1.close()`, not `$1`; Rule 3 holds only in the retention form, since the over-limit branch is the one that allocates and creation is never withheld; the in-use capacity is exactly 2(S − 1) for a mutation serialized field by field and S for a cached one, bounded by 2(M − 13) only at the commit log, not at SSTable row writing; the "stages" are mostly one shared pool whose workers never time out; buffers of dead pooled threads are freed only at GC; the recycle is described in `max_mutation_size`'s §6a and §7, not its §5; the property has no range check (below 128 every close reallocates, at `MAX_ARRAY_SIZE` or above trimming is off); §1, §5, §7, §10.)* |

**Undecided rows to settle first or alongside** (cheap; they may add sites to the above):
`IndexSummaryRedistribution:341` (with `:258`, joined by band B), `SystemKeyspace:1919`, `ResourceLimits:138`
([`deferred.md`](deferred.md) §5), `Envelope:429` (with `:441`; §6) and `ReplicaFilteringProtection:323`
(§7, from band B: a count cap on held rows that needs a Rule 2 ruling). Settle each by the question
named there; the first can become a second site of the `index_summary_capacity` constraint,
the second of `prepared_statements_cache_size`'s pool, the fourth a per-connection memory cap.

**Work each candidate** per [`README.md`](README.md) §2.2 and [`playbook.md`](playbook.md):
re-read the source with the clone open (do not trust the one-line rows below), write all nine
fields, design **both tiers** in the §9a to §9e layout, verify every `file:line`, then move the
candidate to `cases/` and `_INDEX.md` and strike it here.

### From the capacity-word pass, 2026-09-22 — 4 candidates, all pattern (a)

Deep-read against the three rules with the source open. Each passes all
three; none is written up as a case file yet.

| Candidate | Check | Divergence on object creation |
|---|---|---|
| ~~`BufferPool_memoryUsageThreshold`~~ **— FILED 2026-09-28** as [`file_cache_size`](cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md); its `networking_cache_size` sibling is **still open** (same check, second pool) | [`BufferPool$GlobalPool.allocateMoreChunks():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) — `cur + MACRO_CHUNK_SIZE > memoryUsageThreshold` | Disallow returns `null` and logs; allow CASes the counter then `new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE))`. Clean, textbook pattern (a). |
| ~~`MAX_MATERIALIZED_KEYS`~~ **— FILED 2026-10-14** as [`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`](cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS.md) | [`QueryController.materializeKeysAndCloseSource():449`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449) — `MAX_MATERIALIZED_KEYS < ++count` | Disallow returns `null`, discarding the `List<PrimaryKey>` built so far and forcing the caller onto an ORDER-BY-then-post-filter path; allow keeps accumulating and returns the list. |
| ~~`Integer_MAX_VALUE` (index summary)~~ **— FILED 2026-10-15**, [case](cases/Integer_MAX_VALUE-maybeAddEntry-Integer_MAX_VALUE.md) | [`IndexSummaryBuilder.maybeAddEntry():204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204) — `entries.length() + getEntrySize(key) <= Integer.MAX_VALUE` | Allow writes the key and offset into the growable `entries` buffer; disallow skips the entry and logs "Memory capacity of index summary exceeded (2GiB)". |
| ~~`TeeDataInputPlus_limit`~~ **— FILED 2026-10-06** with `CACHEABLE_MUTATION_SIZE_LIMIT` (same constant; second site), [case](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md) | [`TeeDataInputPlus.maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) — `teeBuffer.position() + length < limit` | Allow performs the write into `teeBuffer` (which grows); disallow sets `limitReached` and writes nothing. |

**Notes on these four.**

- `BufferPool` is the strongest: an explicit off-heap memory ceiling gating
  direct-buffer chunk allocation, with the allocation immediately after the
  guard. `memoryUsageThreshold` still needs tracing to its config source for
  the constraint name (§6.1) — that is the main open work.
- `Integer_MAX_VALUE` is unusual and worth keeping: the constraint is a
  **type bound**, not config or a named constant. Target 1 explicitly admits
  "variable types" as a constraint source, so it qualifies, but §6.1 naming
  will need a judgement call.
  **Second check site, found by the band-A2 pass (2026-09-29):**
  [`IndexSummaryBuilder.java:108`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L108)
  — `maxExpectedEntriesSize > Integer.MAX_VALUE` in the constructor. When the
  *expected* summary would pass 2GiB, it raises the effective
  `min_index_interval` (logging a warning), so fewer keys are sampled and the
  `SafeMemoryWriter`s at `:125-126` are sized smaller. Both branches build the
  builder; the divergence is retained size, as in `column_index_cache_size`.
  `:108` is the up-front clamp on an estimate, `:204` the hard stop per entry —
  list both in the case's Location section (README §6.1, "one case, several
  check sites").
- `TeeDataInputPlus_limit` is the weakest of the four — it bounds bytes
  mirrored into a buffer, and `limit`'s origin needs tracing before it is
  clear how meaningful the ceiling is. Confirm before writing it up.
  *(Settled and filed 2026-10-06: its `limit` is `CACHEABLE_MUTATION_SIZE_LIMIT`, so it is
  the second site of that case, not a case of its own; the case adds that `limit <= 0` is the
  tee's "unbounded" setting.)*

### Already covered — cite, do not re-file

The same pass surfaced five rows that belong to existing records:

| Row | Disposition |
|---|---|
| `MemtablePool.tryAllocate():156` | The two filed memtable cases (verified). Served as calibration — the pass found them. |
| `AbstractMessageHandler.acquireCapacity():419` | The two filed `*_receive_queue_capacity` cases. Also calibration. |
| `HintsBuffer.allocateBytes():190` | Already rejected in `rejected.md` (writer-rollover). Cited, not re-judged. |
| [`CommitLogSegmentManagerCDC.permitSegmentMaybe():200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200) | **A second check site of the filed `cdc_total_space` case** — `sizeInProgress + getCommitLogSegmentSize() < getCDCTotalSpace()`, the re-permit path, setting the same `CDCState` verdict that `throwIfForbidden()` reads. Per README §6.1 "one case, several check sites", it belongs in that case file's Location section — **applied; verified present 2026-09-23.** |
| [`ResourceLimits$Basic.tryAllocate():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ResourceLimits.java#L213) | `using + amount > limit` — the generic limiter class behind the two net cases' endpoint/global *reserve* sub-checks, which both case files already mention. Not a separate constraint; it is the mechanism. Worth linking from those cases rather than filing anew. |

### From the band-A1 pass, 2026-09-28 — 8 candidates

Deep-read against the three rules with the source open, from
[`../../stage2-ai-preprocessing/bands.md`](../../stage2-ai-preprocessing/bands.md)'s
A1 list (feed **3a**). Each passes all three rules; none is written up yet.
The A1 pass's rejections are in [`rejected.md`](rejected.md) and its three
undecided rows in [`deferred.md`](deferred.md).

| Candidate | Check | Divergence on object creation | Pattern |
|---|---|---|---|
| ~~`max_hints_size_per_host`~~ **— FILED 2026-09-28**, [case](cases/max_hints_size_per_host-shouldHint-maxHintsSize.md) | [`StorageProxy.shouldHint():2492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492) — `actualTotalHintsSize > maxHintsSize` | Returns `false`, so no hint file is written for that host; allow writes the hint to disk. A **running total of on-disk bytes per destination host**, not a per-item bound. | (b) |
| ~~`max_value_size`~~ **— FILED 2026-10-06**, [case](cases/max_value_size-read-maxValueSize.md) | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) — `l > maxValueSize` | Throws `IOException` before `accessor.read(in, l)`, which would allocate `l` bytes read straight from a length field on the wire/disk. | (c) |
| ~~`max_mutation_size`~~ **— FILED 2026-10-06**, [case](cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE.md) | [`Mutation.validateSize():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172) — `totalSize > MAX_MUTATION_SIZE`. Second site: [`CounterMutation.validateSize():94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L94) | Throws `MutationExceededMaxSizeException` from [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304), before the serialization scratch buffer is filled and before `segmentManager.allocate(mutation, totalSize)` at [`:311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) reserves segment space. | (c) |
| ~~`CACHEABLE_MUTATION_SIZE_LIMIT`~~ **— FILED 2026-10-06**, [case](cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT.md) | [`Mutation$Serializer:451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) — `serializedSize < CACHEABLE_MUTATION_SIZE_LIMIT` | Allow builds a `CachedSerialization(dob.toByteArray())` — a byte array retained on heap; disallow builds a `SizeOnlyCacheableSerialization`, retaining nothing. **Both branches allocate**, as in `column_index_cache_size`. | (a) |
| ~~`local_read_size_fail_threshold`~~ **— FILED 2026-10-06**, [case](cases/local_read_size_fail_threshold-addSize-failBytes.md) | [`ReadCommand$...addSize():715`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715) — `sizeInBytes >= failBytes` | Throws `LocalReadSizeTooLargeException`, aborting the query mid-read so no further rows are materialized. A **running total per query**. | (c) |
| ~~`row_index_read_size_fail_threshold`~~ **— FILED 2026-10-06**, [case](cases/row_index_read_size_fail_threshold-checkSize-failThreshold.md) | [`RowIndexEntry$Serializer.checkSize():392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L392) — `estimatedMemory > failThreshold.toBytes()` | Throws `RowIndexEntryReadSizeTooLargeException` from [`:356`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L356), **before** the `new IndexedEntry(...)` at [`:362`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L362). | (c) |
| ~~`internode_application_send_queue_capacity`~~ **— FILED 2026-10-07**, [case](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md) | [`OutboundConnection.acquireCapacity():398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L398) — `pendingBytes(next) <= pendingCapacityInBytes`. Reserve sub-check at [`:416`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L416). | On `INSUFFICIENT_*`, [`enqueue():343-344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L343-L344) calls `onOverloaded(message)` and **returns** — `queue.add(message)` is never reached and the message is dropped. | (b) |
| ~~`repair_session_max_tree_depth`~~ **— FILED 2026-10-13 as `repair_session_space`**, [case](cases/repair_session_space-split-maxsize.md) | [`MerkleTree.split():409`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409) — `size >= maxsize` | Returns `false` without calling `splitHelper()`, so no new tree nodes are created; allow splits the range and allocates nodes. | (a) |

**Notes on these eight.**

- **`max_hints_size_per_host` is the strongest.** It is the only one of the
  eight whose usage side is a genuine running total against a configured
  ceiling, with a clean disallow that withholds a durable on-disk write. It
  also complements the filed `MAX_HINT_BUFFERS` case — that one bounds the
  off-heap *buffers*, this one bounds the *files on disk*, per host. Check
  whether `getTotalHintsSize` is exact or sampled before writing §9.
- **`max_value_size` does not dominate.** *(Filed 2026-10-06; the case corrects this note: the overload below has no production caller, see its §5 and §10. The non-domination is the sibling length-prefixed read primitives and the unguarded write side.)* The no-argument overload
  [`AbstractType.readBuffer(in):566-569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L566-L569)
  passes `Integer.MAX_VALUE`, disabling the guard for its callers. The guarded
  call sites pass `DatabaseDescriptor.getMaxValueSize()` explicitly — e.g.
  [`Cell.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L339),
  which is the hot path for every cell deserialized. Enumerate both sets when
  writing it up; non-domination is a finding, not a rejection.
- **`CACHEABLE_MUTATION_SIZE_LIMIT` settles an open question.** *(Filed 2026-10-06 as one case, as proposed here.)* The same
  constant is the `limit` passed to `TeeDataInputPlus` at
  [`Mutation.java:493`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L493),
  which is the `TeeDataInputPlus_limit` candidate already in this file. So
  that candidate's limit **is** a real constraint (a JVM system property,
  `cassandra.cacheable_mutation_size_limit_bytes`, default 1,000,000) — unlike
  its near-namesake `TrackedDataInputPlus_limit`, refused on 2026-09-28
  because its limit is the row's own serialized length. **Write the two up as
  one case**, the serialize and deserialize sides of one constraint.
- **The two read guardrails are siblings.** `local_read_size_fail_threshold`
  and `row_index_read_size_fail_threshold` are both per-query heap ceilings
  that abort rather than degrade, and both have a `*_warn_threshold` twin that
  only logs (the warn twin fails Rule 3 — see `rejected.md`). Consider one
  case file per threshold, cross-linked, rather than one combined.
  *(Filed 2026-10-06 as two cases, [local read](cases/local_read_size_fail_threshold-addSize-failBytes.md) and [row index](cases/row_index_read_size_fail_threshold-checkSize-failThreshold.md). They correct this note: the local-read total is per **command**, not per query, and the row-index figure is an **estimate** for one index entry, per SSTable opened. Both are off by default; the row-index guard is inert on several paths, and the local-read guard is not on a names-filter read.)*
- **`internode_application_send_queue_capacity` is the send-side mirror** of
  the two filed inbound cases, sharing the `ResourceLimits` reserve mechanism.
  **Its disallow differs from both:** inbound internode registers on a wait
  queue and keeps the message; this one calls `onOverloaded()` and drops it.
  Worth writing up for the contrast alone.
  *(Filed 2026-10-07 as [one case](cases/internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes.md). It corrects this note and the row above in four places: `:416` is bookkeeping, not a reserve check, and the reserve comparison is `:419`; the drop does more than count and log, it fails the request's callback at once and hints a plain write; the per-peer reserve is built from the **receive-side** endpoint key, so the send-side key is inert on the production path; and a connected, full, non-draining link does not shed expired messages by itself. §1, §4, §6b and §10.)*
- **`repair_session_max_tree_depth` is A1 by a chain**, not directly:
  `maxsize` is a constructor parameter, set to `2^depth` at
  [`ValidationManager.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L80)
  where `depth = min(estimatedMaxDepth, getRepairSessionMaxTreeDepth())`
  ([`:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L76)).
  Note the `min`: the config is a **cap on** the depth, not the depth, so on
  small ranges `estimatedMaxDepth` binds instead and the config does nothing.
  Establish which term binds before designing §9.
  *(Filed 2026-10-13 as [`repair_session_space`](cases/repair_session_space-split-maxsize.md). `estimatedMaxDepth` comes from `repair_session_space`, the non-deprecated budget, which binds below heaps of about 6 to 12 GiB at RF 3; the depth key caps it at 20 above that; the partition count binds on small ranges.)*
