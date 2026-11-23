# Cassandra — stage 3-b client trigger check (analysis, 2026-11-23)

Rules: [`../../oom-agent-playbook.md`](../../oom-agent-playbook.md#stage-3-b--client-trigger-check). Every Cassandra
**true positive** (30) was checked against the client threat model: a Cassandra user, not an admin or developer;
`PasswordAuthenticator` + `CassandraAuthorizer` on; native CQL protocol only; all capacity constraints at defaults.
Four fresh agents walked every step of each verified test arm and cited the 5.0.9 code lines that decide privilege.
**Analysis only: nothing was run.**

**Default exposure.** 5.0.9 ships `AllowAllAuthenticator` (`conf/cassandra.yaml:198`), under which anyone who reaches
the native port is effectively a superuser.

## Counts

| Reach · lowest privilege | Cases |
|---|---|
| **Client-triggerable alone** | **22 / 30** |
| · pre-auth | 2 — B19, R13 (R13 from code reading only) |
| · data role | 15 — C2, S2, R12, R14, R20, U7, B17, U9, U10, R22, B16, R21, U12, B21, U15 |
| · DDL role | 5 — C9, U8, B20, C10, U14 |
| **Given an outside condition** (all data role) | **7 / 30** — node/replica event: B23, B6, B8; operator budget below the resolved one: C1, S1, U13, R1-V |
| **Not client-triggerable** | **1 / 30** — R18 (`nodetool import`) |

## Per case

| Case | Reach | Lowest privilege | Summary |
|---|---|---|---|
| [C2](C2.md) | alone | data role | alone · data role; coordinator, repeatable on every node |
| [S2](S2.md) | alone | data role | alone · data role; coordinator (2 GiB heap), repeatable on every node |
| [R12](R12.md) | alone | data role | alone · data role; replica by key (+coordinator), every node |
| [R14](R14.md) | alone | data role | alone · data role; coordinator, every node |
| [R20](R20.md) | alone | data role | alone · data role (any login, no grants); coordinator, every node |
| [U7](U7.md) | alone | data role | alone · data role (MODIFY); coordinator, every node |
| [B17](B17.md) | alone | data role | alone · data role; replicas by key + coordinator, every node |
| [U9](U9.md) | alone | data role | alone · data role (replicas by key; B2 arm) |
| [U10](U10.md) | alone | data role | alone · data role (data-read replica by key; ≤ 16 GiB heap) |
| [R22](R22.md) | alone | data role | alone · data role (hot-partition replicas; 15,872 MiB heap only) |
| [B16](B16.md) | alone | data role | alone · data role (data-read replica by key; up to 31,744 MiB) |
| [R21](R21.md) | alone | data role | alone · data role (hot-partition replicas) |
| [U12](U12.md) | alone | data role | alone · data role (row replicas, crash loop; ≤ ~3 GiB direct) |
| [B21](B21.md) | alone | data role | alone · data role — ANN SELECT needs only SELECT (+MODIFY to write 120 KiB rows) on a vector/SAI table; replica-side, ring-wide per query |
| [U15](U15.md) | alone | data role | alone · data role — slice DELETE with a 70,000-B bound (MODIFY only) poisons flushes; node-wide write stall, cross-tenant |
| [B19](B19.md) | alone | pre-auth | alone · pre-auth; one 22-byte frame, coordinator, every node |
| [R13](R13.md) | alone | pre-auth | alone · pre-auth (code reading); coordinator, every node |
| [C9](C9.md) | alone | DDL role | alone · DDL role (data role given an sstable backlog); every node holding the table |
| [U8](U8.md) | alone | DDL role | alone · DDL role (coordinator, any node) |
| [B20](B20.md) | alone | DDL role | alone · DDL role (all wide-partition replicas, one statement; likely crash loop) |
| [C10](C10.md) | alone | DDL role | alone · DDL role — own RF 1 keyspace + paged ALLOW FILTERING with an empty first sub-range; data role probable on N > RF (untested) |
| [U14](U14.md) | alone | DDL role | alone · DDL role — CREATE on one keyspace; empty tables until every node's heap is full (run as an ordinary role) |
| [B6](B6.md) | given a ≈ 30 s storage stall on a replica | data role | given replica storage stall · data role; stalled replica, service loss (OOM only with 60 s timeouts) |
| [B8](B8.md) | given a restart that replays more commit log than one memtable pool (commit-log restore / sstables lost) while flushes stall | data role | given restore-replay + flush stall · data role; restarting replica only, 1 GiB |
| [B23](B23.md) | given a replica down (within max_hint_window 3 h) | data role | given a replica down · data role — CL ONE 64 KB writes via a non-replica coordinator chosen by key; any live node |
| [C1](C1.md) | given an operator-set MaxDirectMemorySize ≤ 640 MiB | data role | given direct limit ≤ 640 MiB (rare) · data role; replica steerable by key |
| [S1](S1.md) | given an operator-set MaxDirectMemorySize ≤ 768 MiB and a down replica | data role | given direct ≤ 768 MiB (rare) + a down replica · data role; replica steerable by key (verified arm also used nodetool flush/compact) |
| [R1-V](R1-V.md) | given a small-node deployment (heap ≤ 1 GiB in a 2 × heap container, offheap_objects + file_cache_enabled) | data role | given small-node deployment with both off-heap pools on (rare) · data role; all replicas of written keys |
| [U13](U13.md) | given an explicit MaxDirectMemorySize <= heap/4 | data role | given explicit direct limit ≲ heap/4 · data role — long clustering keys into any SAI table; env.sh pairing survives |
| [R18](R18.md) | not client-triggerable | admin only | not client-triggerable (nodetool import); CQL analogue untested |

## Claims resting on code reading, not on a run

R13 (pre-auth), C9, B20, B21, U15, U14, U9, C10, R14 — details in each case file.

## 3-b confirm runs (optional, on the owner's word)

- To settle code-reading claims: R13, C9, B20, U14, B21, C10.
- Cheap, one node: B19, C2, R14, R20, U7, U8, U10, B16, R21, U12, U15, B17, R12, U9.
- Multi-node: S2, B23, C10. Costly: R22.
- Low value: B6, C1, S1, R1-V, U13, B8; R18 needs a new design.
