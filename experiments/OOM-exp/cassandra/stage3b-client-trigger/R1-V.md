# R1-V — stage 3-b client trigger check (2026-11-23)

**Case file:** [`../cases/convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md`](../cases/convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md)
· **Stage 3-a:** [`../stage3-jira-check/R1-V.md`](../stage3-jira-check/R1-V.md) (`documented only`).
Analysis only (no node run). Code references are to the pinned 5.0.9 tree `systems/cassandra/source/`, paths below
`src/java/org/apache/cassandra/` unless a file under `conf/` is named.

**Mechanism.** Two off-heap pools sized from the heap at their defaults — off-heap memtable (heap/4 with
`offheap_objects`) and chunk cache (min(512 MiB, heap/4) with `file_cache_enabled: true`,
`config/DatabaseDescriptor.java:576-584`) — each within its cap, together with the heap and the JVM's native baseline
exceed a container limit of 2 × heap → kernel memcg OOM-kill.

**Condition assessed:** **A-768 on pc96** (`verified-OOM · deployment`): heap 768 MiB, direct 384, container 1,536 MiB
(L = 2 × heap), `memtable_allocation_type: offheap_objects` + `file_cache_enabled: true`, a `cassandra-stress` write load;
memcg kill 3/3 ≈ 15–25 s into the preload (also heap 1,024 / L 2,048 3/3). Condition B is withdrawn.

**Label: `client-triggerable given a small-node deployment (heap ≤ 1 GiB in a 2 × heap container, offheap_objects + chunk cache enabled) · data role; every replica of the written keys`**

Reach: given a condition (the operator's deployment choices and node size: rare). Lowest privilege: **data role** (MODIFY
on any table); the load is an ordinary bulk write.

## Test arm, step by step (condition A-768)

| Step | As run in stage 2 | Client-reachable? | Privilege | Why / code |
|---|---|---|---|---|
| Schema | `cassandra-stress` default keyspace/table (5 × 1 KiB columns), RF 1 | yes | data role on an existing table / DDL role to create one | `CreateTableStatement.java:164`; any table taking ≈ 5 KiB rows serves |
| Data / requests | preload `cassandra-stress write n=800000`, 32 threads (≈ 15.5–17.3 k writes/s); the kill came during the preload | yes | data role (MODIFY) | `ModificationStatement.java:249`; ordinary writes, no guardrail involved; no rate limit at defaults (`conf/cassandra.yaml:1076`) |
| Flush / compaction | natural, triggered by the write load (compaction reads fill the chunk cache) | yes (load-induced) | — | the later `flush` and `disableautocompaction` steps of the harness come after the kill point and are not needed |
| Settings: `offheap_objects`, `file_cache_enabled: true` | yaml, 2-line diff | **no** | — | operator configuration (documented, non-default, non-capacity settings) |
| Budget: heap 768 MiB in a 1,536 MiB container | `MAX_HEAP_SIZE`, cgroup `memory.max` | **no** | — | operator deployment; below the documented 2 GB minimum heap; 1,536 MiB heap / 3,072 container survives 0/3 |
| Platform | pc96 (fast preload, higher non-heap baseline); apt149 failed only 1/5 | — | — | platform-dependent |
| Diagnostic aids | none (NMT, JMX poller outside the cgroup) | — | — | — |

## Condition and how common

A node deployed in a container of 2 × heap with heap ≤ 1 GiB **and** both off-heap pools enabled: **rare**. Each setting
is documented, but the heap is below the documented 2 GB minimum and both options are opt-in. On such a node the client
only needs sustained write throughput; legitimate bulk loads would trigger it too.

## Blast radius

- **Which node:** every replica that receives the write load; the attacker chooses keys (or a whole token range) and the
  coordinators forward to all replicas, so all replicas of those ranges are loaded at once. With the same deployment on
  every node, writing across the ring loads every node.
- **Repeatable:** yes, on all nodes with this deployment; a whole replica set can be hit simultaneously.
- **Other tenants:** the killed node restarts only if the orchestrator restarts it; replica-set loss gives
  `UnavailableException` at QUORUM for the affected ranges; commit-log replay on restart.

## Operator visibility

High write rate in table metrics; memtable off-heap size and chunk-cache size metrics near their (fractional) caps; no
Cassandra log line before the kill (the kernel kills the process: `CONSTRAINT_MEMCG` in `dmesg`, no `OutOfMemoryError`).
Attribution to a role only via `system_views.clients` / audit log (off by default).

## 3-b confirm

Low value: the client side is a plain write load (cassandra-stress already used a non-privileged write path), and the
decisive conditions are the operator's settings and container size. If run: pc96, A-768 settings, `PasswordAuthenticator`
+ `CassandraAuthorizer`, the stress load under a role with MODIFY only on its table, a victim role reading another table.

## Reason

The verified load is an ordinary CQL write stream at ≈ 16 k writes/s that needs only MODIFY
(`ModificationStatement.java:249`); the kill happens during that load, before any operator command of the harness. The
steps no client can take are the deployment ones: enabling `offheap_objects` and the chunk cache and running a heap
≤ 1 GiB in a container of twice the heap. With those in place a data role can kill every replica of the keys it writes.
The condition is rare and outside the documented sizing guidance (3-a `documented only`), so the label is `given
<condition>`.
