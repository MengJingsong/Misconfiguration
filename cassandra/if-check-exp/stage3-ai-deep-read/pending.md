# Stage 3 — qualified, pending write-up

Lines stage 3 has **read against the three rules and accepted**, but which do
not yet exist as case files in [`cases/`](cases/). They are findings, not a
queue: the judgement is made: what remains is the write-up (all nine
questions of [`../README.md` §5](../README.md#5-required-content-per-if-check-case),
citations checked against the pinned tag).

An entry leaves this file when its case file lands in `cases/` and its row is
added to [`_INDEX.md`](_INDEX.md). Nothing else belongs here — rows still
*awaiting* a read live in
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md),
which is stage 3's 3a queue.

> Moved here 2026-09-23 from `bands.md`. They had been recorded there
> because the capacity-word pass predates the stage folders — but they are stage-3
> judgements (source read, three rules applied), and a stage-2 file states in
> its own header that it never applies those rules.

### From the capacity-word pass, 2026-09-22 — 4 candidates, all pattern (a)

Deep-read against the three rules with the source open. Each passes all
three; none is written up as a case file yet.

| Candidate | Check | Divergence on object creation |
|---|---|---|
| **`BufferPool_memoryUsageThreshold`** | [`BufferPool$GlobalPool.allocateMoreChunks():443`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/memory/BufferPool.java#L443) — `cur + MACRO_CHUNK_SIZE > memoryUsageThreshold` | Disallow returns `null` and logs; allow CASes the counter then `new Chunk(null, allocateDirectAligned(MACRO_CHUNK_SIZE))`. Clean, textbook pattern (a). |
| **`MAX_MATERIALIZED_KEYS`** | [`QueryController.materializeKeysAndCloseSource():449`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/sai/plan/QueryController.java#L449) — `MAX_MATERIALIZED_KEYS < ++count` | Disallow returns `null`, discarding the `List<PrimaryKey>` built so far and forcing the caller onto an ORDER-BY-then-post-filter path; allow keeps accumulating and returns the list. |
| **`Integer_MAX_VALUE` (index summary)** | [`IndexSummaryBuilder.maybeAddEntry():204`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/indexsummary/IndexSummaryBuilder.java#L204) — `entries.length() + getEntrySize(key) <= Integer.MAX_VALUE` | Allow writes the key and offset into the growable `entries` buffer; disallow skips the entry and logs "Memory capacity of index summary exceeded (2GiB)". |
| **`TeeDataInputPlus_limit`** | [`TeeDataInputPlus.maybeWrite():58`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/util/TeeDataInputPlus.java#L58) — `teeBuffer.position() + length < limit` | Allow performs the write into `teeBuffer` (which grows); disallow sets `limitReached` and writes nothing. |

**Notes on these four.**

- `BufferPool` is the strongest: an explicit off-heap memory ceiling gating
  direct-buffer chunk allocation, with the allocation immediately after the
  guard. `memoryUsageThreshold` still needs tracing to its config source for
  the constraint name (§6.1) — that is the main open work.
- `Integer_MAX_VALUE` is unusual and worth keeping: the constraint is a
  **type bound**, not config or a named constant. Target 1 explicitly admits
  "variable types" as a constraint source, so it qualifies, but §6.1 naming
  will need a judgement call.
- `TeeDataInputPlus_limit` is the weakest of the four — it bounds bytes
  mirrored into a buffer, and `limit`'s origin needs tracing before it is
  clear how meaningful the ceiling is. Confirm before writing it up.

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
[`../stage2-ai-preprocessing/bands.md`](../stage2-ai-preprocessing/bands.md)'s
A1 list (feed **3a**). Each passes all three rules; none is written up yet.
The A1 pass's rejections are in [`rejected.md`](rejected.md) and its three
undecided rows in [`deferred.md`](deferred.md).

| Candidate | Check | Divergence on object creation | Pattern |
|---|---|---|---|
| **`max_hints_size_per_host`** | [`StorageProxy.shouldHint():2492`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L2492) — `actualTotalHintsSize > maxHintsSize` | Returns `false`, so no hint file is written for that host; allow writes the hint to disk. A **running total of on-disk bytes per destination host**, not a per-item bound. | (b) |
| **`max_value_size`** | [`AbstractType.read():594`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L594) — `l > maxValueSize` | Throws `IOException` before `accessor.read(in, l)`, which would allocate `l` bytes read straight from a length field on the wire/disk. | (c) |
| **`max_mutation_size`** | [`Mutation.validateSize():172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172) — `totalSize > MAX_MUTATION_SIZE`. Second site: [`CounterMutation.validateSize():94`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CounterMutation.java#L94) | Throws `MutationExceededMaxSizeException` from [`CommitLog.add():304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304), before the serialization scratch buffer is filled and before `segmentManager.allocate(mutation, totalSize)` at [`:311`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L311) reserves segment space. | (c) |
| **`CACHEABLE_MUTATION_SIZE_LIMIT`** | [`Mutation$Serializer:451`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L451) — `serializedSize < CACHEABLE_MUTATION_SIZE_LIMIT` | Allow builds a `CachedSerialization(dob.toByteArray())` — a byte array retained on heap; disallow builds a `SizeOnlyCacheableSerialization`, retaining nothing. **Both branches allocate**, as in `column_index_cache_size`. | (a) |
| **`local_read_size_fail_threshold`** | [`ReadCommand$...addSize():715`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/ReadCommand.java#L715) — `sizeInBytes >= failBytes` | Throws `LocalReadSizeTooLargeException`, aborting the query mid-read so no further rows are materialized. A **running total per query**. | (c) |
| **`row_index_read_size_fail_threshold`** | [`RowIndexEntry$Serializer.checkSize():392`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L392) — `estimatedMemory > failThreshold.toBytes()` | Throws `RowIndexEntryReadSizeTooLargeException` from [`:356`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L356), **before** the `new IndexedEntry(...)` at [`:362`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/io/sstable/format/big/RowIndexEntry.java#L362). | (c) |
| **`internode_application_send_queue_capacity`** | [`OutboundConnection.acquireCapacity():398`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L398) — `pendingBytes(next) <= pendingCapacityInBytes`. Reserve sub-check at [`:416`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L416). | On `INSUFFICIENT_*`, [`enqueue():343-344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/OutboundConnection.java#L343-L344) calls `onOverloaded(message)` and **returns** — `queue.add(message)` is never reached and the message is dropped. | (b) |
| **`repair_session_max_tree_depth`** | [`MerkleTree.split():409`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/utils/MerkleTree.java#L409) — `size >= maxsize` | Returns `false` without calling `splitHelper()`, so no new tree nodes are created; allow splits the range and allocates nodes. | (a) |

**Notes on these eight.**

- **`max_hints_size_per_host` is the strongest.** It is the only one of the
  eight whose usage side is a genuine running total against a configured
  ceiling, with a clean disallow that withholds a durable on-disk write. It
  also complements the filed `MAX_HINT_BUFFERS` case — that one bounds the
  off-heap *buffers*, this one bounds the *files on disk*, per host. Check
  whether `getTotalHintsSize` is exact or sampled before writing §9.
- **`max_value_size` does not dominate.** The no-argument overload
  [`AbstractType.readBuffer(in):566-569`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L566-L569)
  passes `Integer.MAX_VALUE`, disabling the guard for its callers. The guarded
  call sites pass `DatabaseDescriptor.getMaxValueSize()` explicitly — e.g.
  [`Cell.java:339`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/rows/Cell.java#L339),
  which is the hot path for every cell deserialized. Enumerate both sets when
  writing it up; non-domination is a finding, not a rejection.
- **`CACHEABLE_MUTATION_SIZE_LIMIT` settles an open question.** The same
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
- **`internode_application_send_queue_capacity` is the send-side mirror** of
  the two filed inbound cases, sharing the `ResourceLimits` reserve mechanism.
  **Its disallow differs from both:** inbound internode registers on a wait
  queue and keeps the message; this one calls `onOverloaded()` and drops it.
  Worth writing up for the contrast alone.
- **`repair_session_max_tree_depth` is A1 by a chain**, not directly:
  `maxsize` is a constructor parameter, set to `2^depth` at
  [`ValidationManager.java:80`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L80)
  where `depth = min(estimatedMaxDepth, getRepairSessionMaxTreeDepth())`
  ([`:76`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/repair/ValidationManager.java#L76)).
  Note the `min`: the config is a **cap on** the depth, not the depth, so on
  small ranges `estimatedMaxDepth` binds instead and the config does nothing.
  Establish which term binds before designing §9.
