# Positives — survivors of stage-2 AI filtering

Rows that passed all three rules
([`../README.md` §3.4–§3.6](../README.md#3-core-concept-the-if-check-case)),
pending promotion to a full case file under a `<module>/` folder. See
[`README.md`](README.md) for how rows are judged and for batch coverage.

An entry stays here until its case file exists, then moves to the
**Promoted** section below with a link, so the promotion history is visible
without diffing.

**Current scope is pattern (a) only** ([`../README.md` §7.5](../README.md)).
A row that would qualify only under pattern (b) or (c) belongs in
[`deferred.md`](deferred.md), not here.

## Live candidates

_None currently._

The previously outstanding candidate,
`CompactionAwareWriter.getWriteDirectory():282`, was written up on
2026-09-22 via discovery method 1 — see the Promoted table below.

## Promoted to case files

| Candidate | Promoted | Case file |
|---|---|---|
| `native_transport_receive_queue_capacity` — `AbstractMessageHandler.acquireCapacity():419` reached via `CQLMessageHandler` | 2026-09-18 | [`../net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md`](../net/native_transport_receive_queue_capacity-acquireCapacity-queueCapacity.md) |
| `DataDirectory_getAvailableSpace` — `CompactionAwareWriter.getWriteDirectory():282` (pattern (c), disk) | 2026-09-22 | [`../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md`](../compaction/DataDirectory_getAvailableSpace-getWriteDirectory-availableSpace.md) |

### Notes carried over from the promoted entry

`native_transport_receive_queue_capacity` was surfaced by the `transport/`
batch as a sibling of the already-filed
[`internode_application_receive_queue_capacity`](../net/internode_application_receive_queue_capacity-acquireCapacity-queueCapacity.md)
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
