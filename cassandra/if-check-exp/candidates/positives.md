# Positives — rows stage 2 passes forward, with priority

Rows that stage 2 did **not** rule out, ranked by how promising the row looks.
This is a **work queue for the deep-read pass**, not a list of qualified
cases: stage 2 works only from the row and never applies the three rules (see
[`README.md`](README.md)). A row here means "worth reading the source for,
in roughly this order" — nothing more.

Tiers (defined in [`stage2-playbook.md`](stage2-playbook.md)):

| Tier | Meaning |
|---|---|
| **P1** | Capacity-shaped name on one side **and** a compound usage side (`... + ...`) — the `current + requested vs limit` shape. Rare; read first. |
| **P2** | Capacity-shaped name on one side. |
| **P3** | Named operands on both sides, no capacity vocabulary — the long tail that the folder's rules deliberately refuse to exclude by keyword. |
| **P4** | Survived fast-reject but looks mechanical; parked at the bottom rather than refused. |

An entry moves to **Promoted** once a case file exists for it.

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
