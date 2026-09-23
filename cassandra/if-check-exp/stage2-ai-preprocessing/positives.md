# Positives — rows stage 2 passes forward, with priority

Rows that stage 2 did **not** rule out, ranked by how promising the row looks.
This is a **work queue for stage 3**, not a list of qualified
cases: stage 2 works only from the row and never applies the three rules (see
[`README.md`](README.md)). A row here means "worth reading the source for,
in roughly this order" — nothing more.

Tiers (defined in [`playbook.md`](playbook.md)):

| Tier | Meaning |
|---|---|
| **P1** | Capacity-shaped name on one side **and** a compound usage side (`... + ...`) — the `current + requested vs limit` shape. Rare; read first. |
| **P2** | Capacity-shaped name on one side. |
| **P3** | Named operands on both sides, no capacity vocabulary — the long tail that the folder's rules deliberately refuse to exclude by keyword. |
| **P4** | Survived fast-reject but looks mechanical; parked at the bottom rather than refused. |

An entry moves to **Promoted** once a case file exists for it.

## Live candidates

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
| `HintsBuffer.allocateBytes():190` | Already rejected in `../stage3-ai-deep-read/_INDEX.md` (writer-rollover). Cited, not re-judged. |
| [`CommitLogSegmentManagerCDC.permitSegmentMaybe():200`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerCDC.java#L200) | **A second check site of the filed `cdc_total_space` case** — `sizeInProgress + getCommitLogSegmentSize() < getCDCTotalSpace()`, the re-permit path, setting the same `CDCState` verdict that `throwIfForbidden()` reads. Per README §6.1 "one case, several check sites", it belongs in that case file's Location section, which does not currently list it. **Open action.** |
| [`ResourceLimits$Basic.tryAllocate():213`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/net/ResourceLimits.java#L213) | `using + amount > limit` — the generic limiter class behind the two net cases' endpoint/global *reserve* sub-checks, which both case files already mention. Not a separate constraint; it is the mechanism. Worth linking from those cases rather than filing anew. |

## Promoted to case files

| Candidate | Promoted | Case file |
|---|---|---|
| `native_transport_receive_queue_capacity` — `AbstractMessageHandler.acquireCapacity():419` reached via `CQLMessageHandler` | 2026-09-18 | [`../net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md`](../stage3-ai-deep-read/cases/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `DataDirectory_getAvailableSpace` — `CompactionAwareWriter.getWriteDirectory():282` (pattern (c), disk) | 2026-09-22 | [`../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](../stage3-ai-deep-read/cases/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md) |

### Notes carried over from the promoted entry

`native_transport_receive_queue_capacity` was surfaced by the `transport/`
batch as a sibling of the already-filed
[`internode_application_receive_queue_capacity`](../stage3-ai-deep-read/cases/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md)
case: the **same** `acquireCapacity()` if-check, but reached via
`CQLMessageHandler` (CQL client connections) rather than
`InboundMessageHandler` (internode peers), with a different config source
(default 1MiB vs. 4MiB) and a different object created. This mirrors the
`memtable_heap_space` / `memtable_offheap_space` precedent — same check,
different pool instance and config — which is why it was filed as a distinct
case rather than a duplicate.

Writing it up surfaced a finding worth keeping visible: under the **default**
`native_transport_throw_on_overload=false`, this if-check's disallow branch
does not withhold object creation at all — the message is still decoded, and
only a client-visible overload flag is set. Only the non-default
`throwOnOverload=true` produces a clean reject (`OverloadedException`). That
is a stronger, default-mode version of the memtable cases' escape-hatch
pattern, and is flagged in the case file as Target-3-relevant.
