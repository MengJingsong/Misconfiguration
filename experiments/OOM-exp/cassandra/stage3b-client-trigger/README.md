# Cassandra — stage 3-b client trigger check (analysis and confirm runs, 2026-11-23)

> **Scope correction (2026-11-23).** This check covered **30 of the 44** Cassandra true positives. The 14 wave 1–3 true
> positives (B9, B10, B12, B13, B15, C4, C5, C6, C7, C8, U2, U3, U4, R7; plus R15's condition B) write their verdict
> without bold in `_INDEX.md` and were missed by the count that selected the cases. They are pending.

Rules: [`../../oom-agent-playbook.md`](../../oom-agent-playbook.md#stage-3-b--client-trigger-check). Every Cassandra
**true positive** (30) was checked against the client threat model: a Cassandra user, not an admin or developer;
`PasswordAuthenticator` + `CassandraAuthorizer` on; native CQL protocol only; all capacity constraints at defaults.
Four fresh agents walked every step of each verified test arm and cited the 5.0.9 code lines that decide privilege.
The analysis was followed the same day by **confirm runs of 23 cases** (owner-approved; below), which changed four labels.

**Default exposure.** 5.0.9 ships `AllowAllAuthenticator` (`conf/cassandra.yaml:198`), under which anyone who reaches
the native port is effectively a superuser.

## Counts (after the confirm runs)

| Reach · lowest privilege | Cases |
|---|---|
| **Client-triggerable alone** | **22 / 30** |
| · pre-auth (no login) | 1 — B19 (confirmed) |
| · login role, no grants | 2 — R13 (pre-auth refuted by the runs), R20 (both confirmed) |
| · data role (SELECT/MODIFY on an existing table) | 15 — C2, S2, R12, R14, U7¹, B17, U9, U10, R22, B16, R21, U12, B21, U15, C10² |
| · DDL role (own keyspace/tables/indexes) | 4 — C9³, U8, B20, U14⁴ |
| **Given an outside condition** (all data role) | **7 / 30** — node/replica event: B23 (confirmed), B6, B8; operator budget below the resolved one: C1, S1, U13, R1-V |
| **Not client-triggerable** | **1 / 30** — R18 (`nodetool import`) |

¹ U7: with `CassandraAuthorizer` the request is aborted by the roles-cache reload timeout during the GC spiral, so the
coordinator suffers ≈ 2–3 min of GC service loss and recovers (OOM 0/3); stage 2's OOM was under `AllowAllAuthorizer`.
² C10 moved from DDL role to data role (an admin keyspace with RF < N read at a CL with blockFor = RF).
³ C9 also reaches the data role, given a table with ≈ 220+ intersecting sstables (2 GiB direct).
⁴ U14: OOM 1 of 2 runs within the 4 h cap (the other stopped at the case's 40-min DDL cap at 0.92 × heap).

**Confirm runs:** 23 cases, 10 nodes, authentication and `CassandraAuthorizer` on, attacker roles holding only the
labelled privilege, a victim role on the same node: **20 confirmed, 3 partly confirmed** (R13: confirmed at a login role,
not pre-auth; U7: privilege confirmed, endpoint GC service loss instead of OOM; U14: 1 OOM in 2 runs). In every run that
reached the endpoint the victim tenant on that node lost service. Not run as confirms: B6, B8, C1, S1, R1-V, U13 (outside
condition decides), R18. Still resting on code reading: repetition across several nodes (all cases), B21's ring-wide
fan-out, B20's and U14's cluster-wide reach. Evidence: each case file's "3-b confirm" section and `logs/<ID>/`.

## Per case

| Case | Reach (analysis) | Lowest privilege (analysis) | Label after the confirm runs |
|---|---|---|---|
| [C2](C2.md) | alone | data role | alone · data role; coordinator, every node (confirmed 1/1) |
| [S2](S2.md) | alone | data role | alone · data role (MODIFY only); coordinator, 2 GiB heaps (confirmed 1/1) |
| [R12](R12.md) | alone | data role | alone · data role; replica by key + coordinator (confirmed 2/2) |
| [R14](R14.md) | alone | data role | alone · data role; coordinator (confirmed 1/1) |
| [R20](R20.md) | alone | data role | alone · login role, no grants; coordinator (confirmed 1/1) |
| [U7](U7.md) | alone | data role | alone · data role (confirmed); with CassandraAuthorizer GC service loss with recovery, OOM 0/3 (roles-cache reload timeout aborts the request) |
| [B17](B17.md) | alone | data role | alone · data role; replicas by key + coordinator (confirmed 1/1) |
| [U9](U9.md) | alone | data role | alone · data role (MODIFY); replicas by key, crash loop (confirmed 1/1) |
| [U10](U10.md) | alone | data role | alone · data role; data-read replica by key (confirmed 1/1) |
| [R22](R22.md) | alone | data role | alone · data role; hot-partition replicas, 15,872 MiB heap (confirmed 1/1) |
| [B16](B16.md) | alone | data role | alone · data role; data-read replica by key (confirmed 2/2) |
| [R21](R21.md) | alone | data role | alone · data role; hot-partition replicas (confirmed 1/1) |
| [U12](U12.md) | alone | data role | alone · data role; row replicas, crash loop (confirmed 1/1) |
| [B21](B21.md) | alone | data role | alone · data role (SELECT only suffices); node scanned, tenant loses all service (confirmed 4/4) |
| [U15](U15.md) | alone | data role | alone · data role (MODIFY); node-wide write stall, cross-tenant (confirmed 1/1) |
| [B19](B19.md) | alone | pre-auth | alone · pre-auth; one 22-byte frame, coordinator (confirmed 1/1) |
| [R13](R13.md) | alone | pre-auth | alone · login role, no grants (pre-auth refuted: multi-frame v5 refused before auth); coordinator, needs ≥ 5 source addresses at 2 GiB (confirmed 3/3) |
| [C9](C9.md) | alone | DDL role | alone · DDL role (CQL only, no JMX), crash loop on restart; also data role given ≈ 220+ sstables (confirmed 3/3 each) |
| [U8](U8.md) | alone | DDL role | alone · DDL role; coordinator (confirmed 1/1) |
| [B20](B20.md) | alone | DDL role | alone · DDL role; one CREATE INDEX, crash loop on restart (confirmed 3/3) |
| [C10](C10.md) | alone | DDL role | alone · data role on an admin keyspace with RF < N (CL = RF), or DDL role with its own RF 1 keyspace; coordinator (confirmed 3/3 each) |
| [U14](U14.md) | alone | DDL role | alone · DDL role (CREATE on one keyspace); OOM 1/2 (the other run hit the 40-min cap at 0.92 × heap), restart does not recover (partly confirmed) |
| [B6](B6.md) | given a ≈ 30 s storage stall on a replica | data role | given replica storage stall · data role; stalled replica, service loss (OOM only with 60 s timeouts) |
| [B8](B8.md) | given a restart that replays more commit log than one memtable pool (commit-log restore / sstables lost) while flushes stall | data role | given restore-replay + flush stall · data role; restarting replica only, 1 GiB |
| [B23](B23.md) | given a replica down (within max_hint_window 3 h) | data role | given a replica down · data role (MODIFY); keys chosen off the coordinator on the shipped 16-vnode ring (confirmed 2/2) |
| [C1](C1.md) | given an operator-set MaxDirectMemorySize ≤ 640 MiB | data role | given direct limit ≤ 640 MiB (rare) · data role; replica steerable by key |
| [S1](S1.md) | given an operator-set MaxDirectMemorySize ≤ 768 MiB and a down replica | data role | given direct ≤ 768 MiB (rare) + a down replica · data role; replica steerable by key (verified arm also used nodetool flush/compact) |
| [R1-V](R1-V.md) | given a small-node deployment (heap ≤ 1 GiB in a 2 × heap container, offheap_objects + file_cache_enabled) | data role | given small-node deployment with both off-heap pools on (rare) · data role; all replicas of written keys |
| [U13](U13.md) | given an explicit MaxDirectMemorySize <= heap/4 | data role | given explicit direct limit ≲ heap/4 · data role — long clustering keys into any SAI table; env.sh pairing survives |
| [R18](R18.md) | not client-triggerable | admin only | not client-triggerable (nodetool import); CQL analogue untested |

