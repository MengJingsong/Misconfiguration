# Stage 3 — qualified, pending write-up

Lines stage 3 has **read against the three rules and accepted**, but which do
not yet exist as case files in [`cases/`](cases/). They are findings, not a
queue: the judgement is made: what remains is the write-up (all eight
questions of [`../README.md` §5](../README.md#5-required-content-per-if-check-case),
citations checked against the pinned tag).

An entry leaves this file when its case file lands in `cases/` and its row is
added to [`_INDEX.md`](_INDEX.md). Nothing else belongs here — rows still
*awaiting* a read live in
[`../stage2-ai-preprocessing/positives.md`](../stage2-ai-preprocessing/positives.md),
which is stage 3's 3a queue.

> Moved here 2026-09-23 from `positives.md`. They had been recorded there
> because the P1 pass predates the stage folders — but they are stage-3
> judgements (source read, three rules applied), and a stage-2 file states in
> its own header that it never applies those rules.

### From the P1 pass, 2026-09-22 — 4 candidates, all pattern (a)

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

P1 also surfaced five rows that belong to existing records:

| Row | Disposition |
|---|---|
| `MemtablePool.tryAllocate():156` | The two filed memtable cases (verified). Served as calibration — P1 found them. |
| `AbstractMessageHandler.acquireCapacity():419` | The two filed `*_receive_queue_capacity` cases. Also calibration. |
| `HintsBuffer.allocateBytes():190` | Already rejected in `rejected.md` (writer-rollover). Cited, not re-judged. |
| [`CommitLogSegmentManagerCDC.permitSegmentMaybe():200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200) | **A second check site of the filed `cdc_total_space` case** — `sizeInProgress + getCommitLogSegmentSize() < getCDCTotalSpace()`, the re-permit path, setting the same `CDCState` verdict that `throwIfForbidden()` reads. Per README §6.1 "one case, several check sites", it belongs in that case file's Location section — **applied; verified present 2026-09-23.** |
| [`ResourceLimits$Basic.tryAllocate():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ResourceLimits.java#L213) | `using + amount > limit` — the generic limiter class behind the two net cases' endpoint/global *reserve* sub-checks, which both case files already mention. Not a separate constraint; it is the mechanism. Worth linking from those cases rather than filing anew. |
