# Cassandra — stage 3-b client trigger check (analysis and confirm runs, 2026-11-23; 15 more analysed 2026-11-24; wave 7 and 16 confirm runs 2026-11-24, filed 2026-11-25)

> **Scope (2026-11-24).** The 2026-11-23 check covered **30 of the 44** Cassandra true positives. The 14 wave 1–3 true
> positives it missed (B9, B10, B12, B13, B15, C4, C5, C6, C7, C8, U2, U3, U4, R7; their verdicts are written without bold
> in `_INDEX.md`) and R15's condition B were analysed on 2026-11-24 under the same rules (analysis only, no confirm run).
> All **45** are now checked (44 true positives + R15-B).
>
> **Wave 7 (2026-11-24, filed 2026-11-25).** The 8 true positives of wave 7 (R23, R24, U17, B25, B26, B27, B28, B29) were
> analysed under the same rules, and **16 confirm runs** ran the same day (owner-approved): 11 of the 15 cases of
> 2026-11-24 (B9, B10, B12, B13, C4, C6, C8, U2, U3, U4, R15-B) and 5 of wave 7 (R24, U17, B27, B28, B29). All **53** are
> now checked (52 true positives + R15-B).

Rules: [`../../oom-agent-playbook.md`](../../oom-agent-playbook.md#stage-3-b--client-trigger-check). Every Cassandra
**true positive** (30 on 2026-11-23; the 14 missed ones and R15-B on 2026-11-24; the 8 of wave 7 on 2026-11-24) was checked against the client threat model: a Cassandra user, not an admin or developer;
`PasswordAuthenticator` + `CassandraAuthorizer` on; native CQL protocol only; all capacity constraints at defaults.
On 2026-11-23 four fresh agents walked every step of each verified test arm and cited the 5.0.9 code lines that decide privilege.
The analysis was followed the same day by **confirm runs of 23 cases** (owner-approved; below), which changed four labels.
The 15 cases of 2026-11-24 were analysed first; each file's "3-b confirm" section says whether a confirm run is worth
it (10 yes: B9, B10, B12, B13, C4, C6, C8, U3, U4, R15-B; low priority: U2; not worthwhile: B15, C5, C7, R7). The 11 yes and
low-priority ones were confirm-run on 2026-11-24 (owner-approved), with 5 of the 8 wave-7 cases (R24, U17, B27, B28, B29);
three labels moved to a lower privilege (B9, B13 pre-auth; B12 login role, no grants) and R24 gained a condition.

**Default exposure.** 5.0.9 ships `AllowAllAuthenticator` (`conf/cassandra.yaml:198`), under which anyone who reaches
the native port is effectively a superuser.

## Counts (after the confirm runs of 2026-11-23 and 2026-11-24)

| Reach · lowest privilege | Cases |
|---|---|
| **Client-triggerable alone** | **36 / 53** |
| · pre-auth (no login) | 4 — B19, U2, B9⁷, B13⁸ (all confirmed) |
| · login role, no grants | 6 — R13 (pre-auth refuted by the runs), R20, R15-B, B12⁹, U17, B28¹⁰ (all confirmed) |
| · data role (SELECT/MODIFY on an existing table) | 19 — C2, S2, R12, R14, U7¹, B17, U9, U10, R22, B16, R21, U12, B21, U15, C10²; B10, U3, U4¹¹; B27¹² |
| · DDL role (own keyspace/tables/indexes) | 7 — C9³, U8, B20, U14⁴; C4⁵, C6, C8⁶ |
| **Given an outside condition** | **16 / 53** — node/replica event (data role): B23 (confirmed), B6, B8, B15 (crash + restart at a smaller heap + disk stall), C5 (remote-DC outage of ≈ 50+ nodes, `hints_compression` on), R23 (point-in-time restore onto a slow data volume at heap ≤ 1,280 MiB), B29 (a replica that missed the attacker's writes; confirmed 4/4); small node or operator budget below the resolved one: C1, S1, U13, R1-V, R7 (data role); operator-run repair: C7 (DDL role); operator-run `nodetool profileload`: B25 (DDL role), B26 (data role; login role in an all-tables session by code reading); no other traffic on the coordinator: R24¹³ (data role, partly confirmed) |
| **Not client-triggerable** | **1 / 53** — R18 (`nodetool import`) |

¹ U7: with `CassandraAuthorizer` the request is aborted by the roles-cache reload timeout during the GC spiral, so the
coordinator suffers ≈ 2–3 min of GC service loss and recovers (OOM 0/3); stage 2's OOM was under `AllowAllAuthorizer`.
² C10 moved from DDL role to data role (an admin keyspace with RF < N read at a CL with blockFor = RF).
³ C9 also reaches the data role, given a table with ≈ 220+ intersecting sstables (2 GiB direct).
⁴ U14: OOM 1 of 2 runs within the 4 h cap (the other stopped at the case's 40-min DDL cap at 0.92 × heap).
⁵ C4: as run the arm is `not client-triggerable` (`nodetool import`, R18's step); the CQL substitute was confirmed on
2026-11-24 (own table `WITH min_index_interval = 1`, ≈ 0.47 GB of inserts; kill 1/1, restarts killed again 2/2).
⁶ C8: nodes whose resolved heap is ≤ 1.5 GiB (the fixed 1 GiB segment buffer); confirmed 2026-11-24 with the server's own
flushes and compaction (no `nodetool`).
⁷ B9: moved from "given direct ≤ 1,280 MiB" to alone: the confirm reached the endpoint with no credentials at the verified
direct 1,280 MiB, and a half-sent-frame variant also at the automatic 15,872 MiB (1/1).
⁸ B13: moved from data role to pre-auth (confirmed; the data role and a no-grant login role also confirmed).
⁹ B12: moved from data role to login role, no grants (SERIAL reads of absent 60 KiB keys in readable system tables).
¹⁰ B28: 2 connections at 2 GiB on x86 (stage 2), 4 from one address on aarch64 (confirm 2/2); heap ≤ 8 GiB.
¹¹ U4: the verified c = 3 survived 0/2 on pc91; the pre-declared c = 4 arm reached OOM 1/1.
¹² B27: SELECT only; silent (reserves ≈ 0, nothing refused). With 20 logged-in connections busy, 3,480 never-authenticated
connections supplied ≥ 99 % of the queued bytes (OOM 1/1); never-authenticated or no-grant connections alone did not.
¹³ R24: OOM 3/3 with auth on when no other client used the coordinator (4/4 counting diagnostics), 0/3 with the prescribed
victim at 20 ops/s on it (0/5 counting diagnostics). With system_auth at RF 2, the coordinator's death also refused every
tenant whose role lookup needed it (LOCAL_QUORUM).

**Confirm runs:** **39 cases** (23 on 2026-11-23, 16 on 2026-11-24), authentication and `CassandraAuthorizer` on, attacker
roles holding only the labelled privilege, a victim role on the same node: **35 confirmed, 4 partly confirmed** (R13:
confirmed at a login role, not pre-auth; U7: privilege confirmed, endpoint GC service loss instead of OOM; U14: 1 OOM in 2
runs; R24: OOM only with no other traffic on the coordinator). Three of 2026-11-24 lowered the privilege (B9 and B13 to
pre-auth, B12 to login role, no grants). In every run that reached the endpoint the victim tenant on that node lost
service. Not run as confirms (14): B6, B8, C1, S1, R1-V, U13, R18 (2026-11-23, low value); B15, C5, C7, R7 (not
worthwhile); R23, B25 (outside condition decides); B26 (worthwhile, not run: a low-cost privilege test of its login-role
path). Still resting on code reading: repetition across several nodes (all cases), B21's ring-wide fan-out, B20's and U14's
cluster-wide reach, B28's multi-node `system_traces` path, B27's `system_traces` no-grants path. Evidence: each case file's
"3-b confirm" section and `logs/<ID>/`.

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
| [B9](B9.md) | given a direct limit ≤ 1,280 MiB (operator override; the auto 15,872 MiB survived) | pre-auth (by code reading) | alone · pre-auth; coordinator, every node (confirmed 1/1 at direct 1,280 MiB; half-sent variant 1/1 at the auto 15,872 MiB) |
| [B10](B10.md) | alone | data role | alone · data role (SELECT); coordinator, every node (confirmed 1/1; pre-auth connections can supply ≥ 86 % of the queued bytes on a node already busy with slow requests) |
| [B12](B12.md) | alone | data role | alone · login role, no grants (SERIAL reads of absent keys in readable system tables); coordinator, every node; with SELECT on a blob/text-key table every replica of the chosen keys (confirmed) |
| [B13](B13.md) | alone | data role | alone · pre-auth; coordinator, every node (confirmed; data role and no-grant login role also confirmed) |
| [B15](B15.md) | given a crash, a restart at a smaller heap (≤ 1,280 MiB, log written at 8 GiB) and a data-disk stall during replay | data role | not worthwhile as a confirm (node-side steps decide); given crash + smaller-heap restart + replay disk stall · data role; restarting replica(s) only |
| [C4](C4.md) | alone (as run: not client-triggerable, `nodetool import`) | DDL role (CQL substitute, unverified) | alone · DDL role (own table WITH min_index_interval = 1, CQL inserts); attacker's replicas, crash loop on restart (confirmed 1/1, restarts 2/2) |
| [C5](C5.md) | given a remote-DC outage of ≈ 50+ nodes within the hint window (`hints_compression` on) | data role | not worthwhile as a confirm (outside condition decides); given remote-DC outage · data role; coordinator, every live coordinator |
| [C6](C6.md) | alone | DDL role | alone · DDL role; replicas of the attacker's keyspace, schema heap on every node; restart replays into the same OOM (confirmed 1/1) |
| [C7](C7.md) | given an operator-run repair covering the attacker's keyspace (routine) | DDL role | not worthwhile as a confirm (the repair decides); given an operator-run repair · DDL role; the repair coordinator |
| [C8](C8.md) | alone (nodes with heap ≤ 1.5 GiB) | DDL role | alone · DDL role; replicas of the attacker's table, heap ≤ 1.5 GiB (confirmed 1/1, server-side flushes and compaction) |
| [U2](U2.md) | alone | pre-auth | alone · pre-auth; coordinator, every node (confirmed 2/2: budget B and the automatic pairing, auth on, no role) |
| [U3](U3.md) | alone | data role | alone · data role; read replica (by key) + coordinator, OOM at heaps ≤ 8 GiB (confirmed 1/1; a SELECT-only role on grown data also OOMs) |
| [U4](U4.md) | alone | data role | alone · data role; read replica (by key) + coordinator, heap OOM at 2 GiB (confirmed 1/1 at c = 4; c = 3 0/2 on pc91) |
| [R7](R7.md) | given a small node (direct ≤ ≈ 1 GiB: the cassandra-env.sh value on a ≤ 4 GiB-RAM node, or explicit) | data role (MODIFY) | not worthwhile as a privilege confirm (questions are about the deployment); given a small node · data role (MODIFY); every replica of the written keys |
| [R15-B](R15-B.md) | alone | login role, no grants | alone · login role, no grants; coordinator, every node (confirmed 1/1: OOM +6.7 s naming an absent keyspace; pre-auth refused before the parse) |
| [R23](R23.md) | given a point-in-time restore from the commit-log archive onto a slow data volume (≈ 100 ms writes) at heap ≤ 1,280 MiB | data role | not worthwhile as a confirm (the restore and the volume decide); given PITR restore + slow data volume + heap ≤ 1,280 MiB (rare) · data role; restored replicas only |
| [R24](R24.md) | alone | data role | given an otherwise idle coordinator · data role; the coordinator the attacker connects to (any node), heap OOM at 2 GiB; with auth on its death also refuses every tenant whose role lookup needs it (system_auth quorum) (partly confirmed: 3/3 with no other traffic, 0/3 with a victim on the coordinator) |
| [U17](U17.md) | alone | login role, no grants | alone · login role, no grants; coordinator, every node (confirmed 1/1) |
| [B25](B25.md) | given an operator-run profileload/toppartitions of several of the attacker's tables, one after another (≈ 3.5 per GiB; rare) | DDL role | not worthwhile as a confirm (the operator step decides); as run not client-triggerable (`nodetool profileload`); given operator profileload · DDL role; profiled node only |
| [B26](B26.md) | given an operator-run profileload/toppartitions session covering a table the attacker can read (occasional; continuous under `-i`) | data role (SELECT only); login role, no grants, in an all-tables session (code reading) | not confirm-run (worthwhile, cheap: tests the login-role path); analysis: given an operator profileload session · data role; profiled node only, one 10 s session at 2 GiB |
| [B27](B27.md) | alone | data role (SELECT) | alone · data role (SELECT); coordinator, every node; silent, reserves ≈ 0 (confirmed 1/1; 20 logged-in + 3,480 never-authenticated connections also OOM 1/1, ≥ 99 % of the bytes pre-auth) |
| [B28](B28.md) | alone (heap ≤ 8 GiB) | login role, no grants | alone · login role, no grants; coordinator, every node, heap ≤ 8 GiB (confirmed 2/2 at 2 GiB with 4 connections from one address; 2 survived on aarch64) |
| [B29](B29.md) | given a replica that missed the attacker's writes (outage: hints pending, or > 3 h with no repair) | data role (SELECT + MODIFY on a table with a static column) | given a replica that missed the attacker's writes · data role; the stale replica as coordinator, repeatable after its restart until hints or repair catch up (confirmed 4/4, incl. 1/1 inside the hint window) |
