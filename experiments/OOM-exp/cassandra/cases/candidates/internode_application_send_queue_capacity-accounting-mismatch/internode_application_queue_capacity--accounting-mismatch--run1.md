# B6 run 1 — internode queues charge on-wire bytes; tiny-cell mutations hold ~17–20× that on heap

**Direction / sub-direction:** bypass · accounting mismatch (protocol *Classification by measurement*:
U > C while the control's counter K ≤ C). **Allocation domains:** (1) coordinator heap holding
`Mutation`s bound for a slow replica — in the send queue and, after flush, in the write callback;
(2) replica heap holding deserialized `Mutation`s waiting on `MutationStage` while charged to the
receive queue. **Capacity regime:** default internode queue capacities (4 MiB / 128 MiB / 512 MiB,
send and receive). **Budget regime:** deliberately tightened diagnostic heap (`-Xmx 2G`) on the
measured instance; others ample. **Pinned source:** cassandra-5.0.9 (`b5f2a54210`), local copy
`/mydata/b6/cassandra` (repository `8b83bbfb`). **Date:** 2026-11-10.
**Design:** [`design/B6-design.md`](design/B6-design.md) (amendments in §2).

__VERDICT__

---

## 1. Constraint, contract, protection map

| Field | Evidence |
|---|---|
| Control | Internode application queues. Send: `OutboundConnection.enqueue` charges `message.serializedSize()` (`OutboundConnection.java:330,1045–1048`) to per-link 4 MiB, then endpoint 128 MiB + global 512 MiB reserves; on failure prunes expired once, then **drops** (`:335–345`, `onOverloaded :456`). Receive: `AbstractMessageHandler.acquireCapacity` charges the frame size to the same three tiers; on failure the connection stops reading (back-pressure). |
| Contract | `cassandra.yaml`: "These limits are applied to the **on-wire size** of the message." Capacity per destination per link type: 4 + 128 = **132 MiB**. |
| Allocation / ownership | Sender: `Message<Mutation>` objects on heap while queued (serialized only at flush). After flush, the write handler keeps the `Mutation` as `hintOnFailure` (`Mutation.hintOnFailure()` returns `this`, `Mutation.java:158`; `AbstractWriteResponseHandler.java:81,309`) until the replica answers or the callback expires — even with hints disabled. Receiver: small messages are deserialized, then wait on `MutationStage` as heap objects; receive capacity is released only after processing. |
| Uncovered memory | Heap size of a `Mutation` is not its on-wire size. After flush, the sender's copy is charged to **no** sender counter (only to the replica's receive queue, in another JVM). |
| Lifetime | Until processed or expired. Expiry deadline = min(`write_request_timeout`, `native_transport_timeout` from client admission) (`Dispatcher.RequestTime.computeDeadline`, `Dispatcher.java:238–245`) — found during A0 (§2). |
| Budget | Java heap (`-Xmx`). |

C = 132 MiB on-wire per destination (one link type: these mutations are < 64 KiB → SMALL).
K = `internode_outbound.pending_bytes` (sender) / `internode_inbound.using_bytes` (receiver).
U = live heap from `jcmd GC.class_histogram` (full GC) minus the idle baseline.

## 2. Executed design and amendments (2026-11-10)

Single host `node0.jason92-325405` (32 cores, 125 GiB, Ubuntu 22.04, OpenJDK 11.0.33, Ant 1.10.12),
three instances on loopback, `GossipingPropertyFileSnitch`, one token each, hints off, key/counter
cache 0, keyspace `NetworkTopologyStrategy {v:1, f:1}`, CL=ONE:

| Instance | Address | Role | Notes |
|---|---|---|---|
| V | 127.0.0.11 dc=v | slow replica | Byteman 100 ms at `MutationVerbHandler.doVerb` entry, `concurrent_writes: 2` (drains ≈ 20 mutations/s) |
| F | 127.0.0.12 dc=f | fast replica, 8 GiB | acks CL=ONE so the client never waits on V |
| S | 127.0.0.13 dc=c | coordinator; client talks only to S | owns no replica |

Client: Python driver bundled with cqlsh, async prepared inserts, 256 in flight, to S only.
- **map (tiny cells):** `t_map(pk int PRIMARY KEY, m map<int,int>)`, 1000 entries per insert →
  **10.80 KiB on-wire** per mutation (`pending_bytes / pending_count`).
- **blob (control):** `t_blob(pk int PRIMARY KEY, b blob)`, 11000-byte blob → **10.80 KiB on-wire**
  (matched to 0.1%).

Harness: `harness/` (`ctl.sh`, `ring-up.sh`, `load.py`, `sample.sh`, `snap.sh`, `arm.sh`, `armx.sh`,
`analyze.sh`, `mutation-delay.btm`, `batch1.sh`, `batch2.sh`). Raw data `/mydata/b6/runs/<arm>/`.

**Configuration audit**

| Change | Class | Value |
|---|---|---|
| internode send/receive queue capacities | tested capacity (default) | 4 / 128 / 512 MiB (intervention arm: endpoint reserves 8 MiB) |
| measured instance `-Xmx` | budget (tightened diagnostic) | 2 GiB; 8 GiB in calibration |
| `write_request_timeout` | supporting deviation | 60 s (default 2 s); default in D arms |
| `native_transport_timeout` | supporting deviation | 60 s (default 12 s); default in D arms |
| V Byteman delay, `concurrent_writes: 2` | supporting deviation (intervention) | 100 ms |
| `hinted_handoff_enabled` | supporting deviation | false |
| addresses, snitch, dc, tokens, caches 0 | environment | — |

**Amendments.**
- *A0 (dropped):* with only `write_request_timeout` raised, V expired 77% of messages at a mean
  12.5 s cross-node latency. In 5.0 the message deadline is also capped by `native_transport_timeout`
  (12 s) from client admission; raised to 60 s on all instances.
- *A1:* the slow replica V (then 2 GiB heap) **died of heap OOM** while its receive queue held
  ≤ 129 MB from S (`throttled_count` 0) and `MutationStage` pending was 11 746. This receive-side
  instance of the same mismatch was not in the design; it is added as domain (2) with its own arms.
- `jstat` cannot attach (Cassandra sets `-XX:+PerfDisableSharedMem`); heap is sampled with
  `jcmd GC.heap_info` (no forced GC) and measured with `GC.class_histogram` (forced full GC).

__RESULTS__
