# Phase links — Cassandra

One row per verified OOM-exp case, by the [back-link playbook](../backlink-playbook.md): did phase 1
(`capacity-enforcement-exp`) hold a clue to the result **as filed before the case's first run**?
Classes: `flagged`, `recorded-untested`, `missed`, `no-case`, `out-of-scope` (defined in the
playbook, step 4). Questions E1–E4 are the guided playbook's
[§3.2](../capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md#32-enforcement-properties-oom-lead-patterns-added-2026-11-16-named-2026-11-17).
Phase-1 paths are under `capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/` unless
stated; `s4/` is `capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/`.

**First pass: 2026-11-16**, all seven cases verified by that date. Read by three agents, one or more
cases each, with read-only git history checks; quotes spot-checked against the files. In every case the
phase-1 text was unchanged between the version before the first run and HEAD (only renames and link
fixes), so nothing below was written with hindsight.

## Links

| Case | Mechanism | Class | Clue as filed (best phase-1 file) | Lead source was phase 1? | Question |
|---|---|---|---|---|---|
| **B6** internode queues × tiny-cell mutations | Queues charge on-wire bytes; queued tiny-cell mutations take ≈ 17–20× that on the heap, and the coordinator keeps flushed mutations uncounted until the replica answers | `recorded-untested` | `internode_max_message_size-inferMessageSize-size--autonomous.md` A3 bypass (a): a payload that "expands during deserialization … can use more heap than its wire size"; its own stage-4 note: "A3 bypass (a) … is not tested". Estimate positive. Also `internode_application_send_queue_capacity-releaseCapacity-…--autonomous.md` stage 4: 3.27 heap bytes per counted byte, filed "caps" | No (`flow:coordinator-write`, from the C1 discussion) | E1 |
| **C1** receive queue × peers (run 4) | Per-link allowance N·Q plus the endpoint/global reserves, all in direct memory, never compared with `MaxDirectMemorySize` | `recorded-untested` | `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided.md` §8: worst case "(peers × connection_types × queueCapacity) + … + globalReserve"; stage 4 confirmed the per-peer sum as a cap. `…reserve_global_capacity-…--autonomous.md` A3: "queueCapacity (4MiB x connections) is outside the reserves". No file compares the sum with the direct budget | Yes (if-check inventory; `_constraint-groups.md` links these files) | E3, and E4 for the direct-budget sum (the main term in run 4) |
| **B7** key + counter cache weigher | The Caffeine weigher counts key + value only; node, table and sketch overhead are not weighed (2.14× / 1.80× the cap) | `recorded-untested` | `key_cache_size-create-size--autonomous.md` bypass (i): real heap per entry is weight plus node and sketch overhead "which the weigher does not count" (2026-10-25, before R3). `s4/key_cache_size-applySimpleConfig…`: run 1 measured ≈ 2.17×; the band was then re-derived and the result filed "Confirmed — caps" | No (R3/R4 heap dumps) | E1 |
| **C2** concurrent reads × slow clients | v4 responses are encoded into Netty's pooled direct allocator; nothing checks `isWritable()`; in-flight limits count requests only; unsent responses are bounded only by `MaxDirectMemorySize` | `recorded-untested` | `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md` escape hatch (1) and §8: a client that stops reading makes the server hold every response frame, "bounded by nothing but `-XX:MaxDirectMemorySize`"; stage 4 held ≈ 183 MiB "whatever the knob". But the file scopes itself to v5 ("Not this pool: native protocol v4"). For v4, side notes only: `local_read_size_fail_threshold-addSize-failBytes--guided.md` §8, `native_transport_max_request_data_in_flight-releaseItem-…--autonomous.md` A4 | Partly (the read-size thresholds; the slow-reader file was not cited) | E2, with E3 |
| **R1-V** off-heap memtable + chunk cache at defaults | Both pools at their default 512 MiB, each under its cap, plus the heap exceed the container | `missed` | `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous.md` A4 lists the chunk cache among other native memory, "None governed by this entry"; the guided files treat the other pool as something to hold fixed. No file adds the defaults against a heap, RAM or container budget | Yes (two true positives), but the pairing came from OOM-exp's convergence design | E4 |
| **S1** direct-memory combo | Default direct-memory pools stack; the excess comes from 32 MutationStage threads each growing DOB scratch to 15–30 MiB in `CommitLog.add` (U1); no pool is reconciled with `MaxDirectMemorySize` | `recorded-untested` (decisive holder U1); joint stacking `missed` | U1: `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md` §8: the instantaneous peak is "the in-use buffers of the threads busy"; `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md` §8: transient "max_mutation_size × N … 512 MiB", §9 "not tested". Other holders: kept scratch D `flagged` (DOB escape hatch: "Thread count is the multiplier and is not limited here"), pool P `flagged`, receive queue R `recorded-untested`, hint slabs H `missed`. Stacking: only a generic "all of these share `-XX:MaxDirectMemorySize`" | No (`source: C1, C2, C3, R6-V, B1`; U1 from an R6-V side finding) | E4 for the case; E1 + E3 for U1 |
| **S2** coordinator local-write backlog | The coordinator's own local write waits on MutationStage's unbounded queue; at CL=ONE a faster replica's ack releases the client slot, the in-flight charge and the request thread first | `recorded-untested` | `concurrent_writes-takeWorkPermit-workPermits--autonomous.md` A4: a waiting mutation "stops being counted after the timeout, even though it is still on the heap" (negative, "does not cap"); `maxTasksQueued-takeTaskPermit-taskPermits--autonomous.md` stage 4: the counted bytes "are not held while the mutation waits in the executor queue". Both shown only at non-default settings; at defaults the files claim a bound of ≈ 128 through blocked request threads, which the early ack removes. No file mentions the CL=ONE early ack | No (`source: B6, B7, R3/R4`; holder found from a heap dump) | E1 (counter released before memory is freed), with E2 |
| **B8** commit-log replay (condition S, diagnostic; added 2026-11-17) | Replay bounds its queue at 64 MiB of **serialized** entry bytes / 1,024 mutations, which are counted after deserialization. Queued tiny-cell mutations hold 15× that on the heap (0.93 MiB vs 63.7 KiB; 947 MiB at the bound), and the bound is not scaled with the heap. At defaults the memtable pool caps what is left to replay (A negative 0/10). With restore emulation and a flush stall the queue fills, and a 1 GiB node OOMs in replay | `recorded-untested` | `commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md` A3 "Bypasses": "serialized size understates heap size for small mutations (object overhead); the check counts only the replay backlog, not the memtable the mutations are applied into". A2: "plus object overhead that is significant only for small mutations". Estimate positive. Stage 4 (`s4/commitlog_max_outstanding_replay_bytes-…`) used 64 KiB single-value rows only and measured 2× (the cached copy), filed "Confirmed — caps"; tiny cells not tested. Its amendment M3 needed `memtable_cleanup_threshold: 0.99` because default flushing discards segments: the reason B8's A is negative. No phase-1 file compares the fixed bound's real heap with a small heap. Only file in the class (no `entry-restriction-exp` file); text unchanged since 2026-11-12, before B8 run 1 (2026-11-16) | Yes (`source: N4`, which cites this file and `max_mutation_size`; the 15–20× figure came from B6, the unit question from JIRA 8639 via pattern-leads L7) | E1, with E4 (fixed bound against a small heap shared with replay-filled memtables) |

## What the first pass shows

- **Phase 1 saw almost every mechanism, but its verdicts absorbed them.** Six of seven cases are
  `recorded-untested` and one is `missed`; none is `no-case` or `out-of-scope`. The clue sits in an
  A3/A4 remark, a §8 aside or a stage-4 note, while the estimate stays positive or the stage-4 result
  is filed "caps" (B7 measured 2.17× and filed "Confirmed — caps"). This is what §10's new
  Real-memory estimate and §8a are for.
- **The clues were not where OOM-exp found its leads.** Only C1 and R1-V (and C2 in part) took their
  lead from phase 1; B6, B7, S1 and S2 came from OOM-exp's own traces and heap dumps. The flags file
  (`oom-lead-list.md`) is the route meant to close that gap.
- **E1–E4 cover all seven; no new question is proposed.** E1 (B6, B7, S2), E2 (C2), E3 (C1, S1's U1)
  and E4 (R1-V, S1, C1's sum).
- **Sums across pools are the weakest spot.** Nothing in phase 1 adds defaults against a budget
  (R1-V, S1, C1). That is a cross-case check; one case file cannot answer it alone.
- **B8 (added 2026-11-17).** The eighth verified case fits the pattern. It is `recorded-untested` (now seven
  of eight; one `missed`). Its lead came from phase 1 (now C1, R1-V and B8, and C2 in part). E1 covers
  it with E4, so still no new question. The phase-1 file also held the reason B8's deployment condition
  was negative: its stage 4 had to raise `memtable_cleanup_threshold` to keep a log to replay.

## Phase-1 files to recheck (back-link mode)

Guided playbook §5, `back-link` mode. 34 files; some serve several cases:

- **B6, C1:** `internode_max_message_size-inferMessageSize-size--autonomous`, `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous`, `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided`, `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous`, `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided`, `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous`, `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous`, `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided`
- **B7:** `key_cache_size-create-size--autonomous`, `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous`, `key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous`, `counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous`, `counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous`, `counter_cache_size-putcachedcounter-capacity--autonomous`
- **C2:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` (also C1, S1), `local_read_size_fail_threshold-addSize-failBytes--guided`, `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` (also S2), `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided`, `coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous`, `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` (also S2)
- **R1-V:** `memtable_offheap_space-tryAllocate-limit--guided`, `file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`, `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous`, `memtable-offheap-space-allocate-size--autonomous`, `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous`
- **S1:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`, `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`, `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided`, `hints-HintsBuffer-put-slabCapacity--autonomous` (plus the receive-queue and networking files above)
- **S2:** `concurrent_writes-takeWorkPermit-workPermits--autonomous`, `maxTasksQueued-takeTaskPermit-taskPermits--autonomous`, `maxTasksQueued-addTask-taskPermits--autonomous`, `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous`, `sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous` (plus the two in-flight files above)
- **B8 (added 2026-11-17; not in the 34):** `commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous` (rechecked 2026-11-17, back-link), plus a short replay addendum to `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided` (B6's recheck did not cover the replay holder). `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided` (N4's second source, for unguarded replay of oversized entries) was not rechecked again: B8 did not exercise that path

## Blind recheck pilot (2026-11-16)

Owner-approved pilot of guided playbook §5 in `blind` mode: 20 phase-1 case files outside the back-link
list (12 true positives, mostly config; 4 false negative / undetermined / weak; 4 true negatives), four
agents with 5 cases each, plus one cross-case **budget ledger**
([`budget-ledger.md`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/budget-ledger.md)). Agents did
not open OOM-exp, this file, the handoffs or git history. All flags are in
[`oom-lead-list.md`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/oom-lead-list.md). The comparison
with OOM-exp below was made afterwards by the orchestrator, which can read both.

**Per-case rechecks.** 8 of 20 cases flagged (7 distinct mechanisms; the slab-region tail was flagged twice):
5 of 12 true positives, 2 of 4 FN/undetermined/weak, 1 of 4 true negatives. Appended sections only (359
lines added, 0 removed).

| Flag (case) | Q | Already in OOM-exp? |
|---|---|---|
| Slab-region tails ≈ 1 MiB per written table (`memtable_heap_space`, `max-cloned-size`) | E1/E3 | Known as N11 (phase1-bypass-leads, low); the per-table current-region term is new |
| Refused single-frame v5 requests dispatched anyway; release drives `queueSize` negative (`native_transport_receive_queue_capacity`) | E2 | **New** (N2 is the v4 force-allocation path); source-checked: `CQLMessageHandler.java:223,245-260,509`, `AbstractMessageHandler.java:396-408,461` |
| Coordinator Merkle trees per job, no scheduler limit (`repair_session_space`) | E3 | Known: N5, JIRA 19336 |
| Partial pre-STARTUP envelopes up to 16 MiB per connection, connections unlimited (`…_per_ip`) | E3 | **New**; source-consistent (`Envelope.java` decoder, `PipelineConfigurator.java:265`) |
| Index summaries built at full sampling between hourly runs (`index_summary_capacity`) | E2 | Known: R5 / C4 / B5 |
| Decode copies bound values to heap, ~15× the wire bytes (`native_transport_max_message_size`) | E1 | Known family (L1/N2, the B6 expansion idea); the v5 BATCH shape is new |
| Stored collection read whole, ~200 B/item, no read guard at defaults (`items_per_collection`) | E1 | **New** (N8 covers only the guardrail exemption) |

**Ledger.** 17 flags. Most restate mechanisms behind OOM-exp results (C1/S1 reserves and DOB scratch in
direct memory, C2 slow readers, B7 weighers, S2 stage queues, R1-V off-heap pools, N5 repair). New:
SAI `segment_write_buffer_size` (fixed 1024 MiB, `StorageAttachedIndexOptions.java:26`) at small heaps;
inbound compressed-stream buffers; and `cassandra-env.sh` sizing `MaxDirectMemorySize` from `free -m`
even for a hand-set heap (`conf/cassandra-env.sh:58-66`; seen on ms0625 as `-Xmx2G` with 15872M).

**Caveat on blindness.** The agents read guided playbook §3.2, whose example column names OOM-exp cases
and their mechanisms (B6, B7, C1, C2, R1-V, S1, S2). So the ledger's rediscovery of those mechanisms is
**not** independent evidence that phase 1 predicts phase 2. The per-case flags on other constraints are
less affected. For the full run, blind agents should get §3.2 without the example column.

**Next (owner's decision):** run the remaining ~139 pool cases in blind mode (with the example column
withheld), the 34 back-link rechecks, and/or hand the new flags to OOM-exp as leads.

## Blind recheck of the remaining pool (2026-11-16/17)

The other 139 pool cases, blind, with [`recheck-blind.md`](../capacity-enforcement-exp/stage3-ai-deep-read/recheck-blind.md)
as the agents' whole instruction (§3.2's questions **without** the column naming OOM-exp results). Three
waves, 20 agents, append-only (1,803 lines added, 0 removed). Headings are dated 2026-11-16 (wave 1) and
2026-11-17 (waves 2–3, UTC).

| Wave | Cases | Flagged | Rate |
|---|---|---|---|
| 1 — true positives | 53 | 18 | 34 % |
| 2 — true negatives | 57 | 6 | 11 % |
| 3 — false negative / weak / undetermined / not run | 29 | 9 | 31 % |
| **Total** | **139** | **33** | **24 %** |

With the pilot (8 of 20), 41 of the 159 pool cases carry a flag. Flags are leads, not results.

**Mechanism clusters** (several agents often reached the same mechanism from different constraints;
the count is the number of flagged case files):

| Cluster | Flags | Already in OOM-exp? |
|---|---|---|
| Partial pre-login envelopes up to 16 MiB per connection, connections unlimited at defaults | 5 (pilot + 4) | New (step 3 hands it over) |
| Read limits that count rows or tombstones, not bytes, with read-size thresholds off by default (page sizes, GROUP BY, unpaged aggregates, SAI top-K, range sub-requests, tombstone thresholds, `cached_rows`) | 11 | Partly: the "no byte limit on concurrent reads" side of C2; the per-limit forms are new |
| Coordinator Merkle trees per (session, table), no scheduler limit | 5 | Known: N5, JIRA 19336 |
| Slab-region tails, ≈ 1 MiB per written table under `heap_buffers` | 4 | Known as N11; per-table term new |
| Memtable pool overshoot (update overhead charged after merge, no-op waste lock, `isBlocking`) | 2 | Known family (B2) |
| Index summaries (full sampling between runs; upsampled buffers never trimmed) | 2 | Known: R5; the upsample buffer is new |
| Denylist refresh skips the total cap | 2 | New (operator-populated, opt-in) |
| Per-connection receive capacity charged before the reserves (v5 dispatch-anyway; 1 MiB per connection) | 2 | New (N2 is the v4 path) |
| Coordinator-local write left on the unbounded MutationStage queue after the client is answered (`maximumPoolSize`) | 1 | **Verified: S2**, found blind |
| Decode or trace copies of request values on heap (≈ 6–15× wire bytes) | 2 | Known family (L1/N2, the B6 idea) |
| Others, one each: stored-collection read, Paxos empty-entry weight, index-build page skew, streamed chunk index, trie shard state | 5 | New |

**What this says about phase 1 predicting phase 2.** With the example column withheld, one blind flag
matches a verified case outright (S2, from `maximumPoolSize`), and the read-limit cluster matches the
"concurrent reads, no byte limit" side of C2. That is a weak test: the pool excluded the 34 back-link
files, which are exactly the files nearest the verified cases, so most verified mechanisms could not be
rediscovered here. The stronger test is forward: how many of the new clusters OOM-exp verifies.

## Back-link rechecks (2026-11-17)

The 34 files listed above, rechecked in `back-link` mode (guided playbook §5): seven agents, one per
verified case, each allowed to read its OOM case. Append-only (659 lines added, 0 removed); every file now
ends with `## Recheck — enforcement properties (guided, 2026-11-17, back-link)`. 56 flag rows in
[`oom-lead-list.md`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/oom-lead-list.md): **37 restate
what the OOM case showed** (now written into the phase-1 file where the clue was), **19 go beyond it**.

| Case | Files | Rows | Beyond the OOM case (one line each) |
|---|---|---|---|
| B6 | 4 | 8 | large tiny-cell mutations expand per busy stage thread (32 × 16 MiB × R); refused writes held by their callback until timeout (non-default limits); the cached serialized copy alone ≈ 2× on-wire; send + receive global reserves on one heap ≈ 17–20 GiB at B6's ratio |
| C1 | 4 | 8 | the 512 MiB send global reserve is not heap-scaled (overlaps the budget ledger) |
| B7 | 6 | 8 | after a runtime shrink Caffeine's table and sketch stay at the old size (+17.3 MB measured for the key cache) |
| C2 | 6 | 9 | the v5 slow-reader path (v4 is C2); the request side itself under-counted (≈ 1.2 GiB + 2.1 × counted bytes); per-IP bound excludes a 1 MiB v5 queue per connection (overlaps N13) |
| R1-V | 5 | 10 | the caps alone commit 7/8 of RAM under `cassandra-env.sh`; the chunk-cache pool fills even with the cache off; `cassandra_latest.yaml` ships `offheap_objects`; trie buffers charged by used position; uncapped pool overflow |
| S1 | 4 | 7 | counter and view stages add 64 more writers filling DOB scratch (≈ 3 GiB ceiling, producibility unchecked); hint writers park holding the switch monitor while queued hints are bounded by count, not bytes |
| S2 | 5 | 6 | a per-destination hint counter could not shed the backlog (self-hints are never counted) |

Read with the first-pass table above: the 37 restating rows are the phase-1 files' answers to the questions
their clue was missing, so a later reader of those files now sees the gap. Back-link rows explain results
after the fact and do not count as prediction; the 19 "beyond" rows are new leads like any other flag.

## Stage-4 runs of rescan claims, batch 1 (2026-11-17)

*Called "recheck claims" when run; renamed 2026-11-17 ([stage-4 README](../capacity-enforcement-exp/stage4-runtime-verification/README.md#rescan-claims-added-2026-11-17)).*
Owner-approved: five recheck "Stage-4 claim to add" lines, run under the stage-4 protocol (design appended to the
case file and frozen, audit, run 1, self-check, verdict), one fresh agent per case on the new x86 nodes
`pc91`/`pc84`/`pc72`/`pc99`/`pc75`. Each was a scaled measurement inside a recorded cgroup budget (swap 0), not an
OOM test. Results: `stage4-runtime-verification/results/<case>--recheck-2026-11-17.md`.

| Node | Case (lead) | Verdict | Counted vs real (key reading) |
|---|---|---|---|
| pc99 | `items_per_collection` (N15) | **Confirmed — does not cap** | one read of a set holds ≈ 150 B/item on heap (19× serialized, 38× on disk), linear to 10⁷ items (1.53 GB held, 3.52 GB allocated per read); with the read-size threshold on, the replica still builds the whole row before the check; the item guardrail is bypassed by appends |
| pc84 | `native_transport_max_frame_size` (N14) | **Confirmed — does not cap the node** | each stalled pre-login connection holds exactly 16 MiB of Netty direct memory (512 connections: +9.2 GiB, plus ≈ 1 GiB of per-arena chunks); Cassandra counts 0 bytes and refuses nothing |
| pc72 | `native_transport_receive_queue_capacity` (N13) | **Confirmed — does not cap** (heap; direct undetermined) | decoded in-flight requests 312 / 468 / 624 MB at 20 / 30 / 40 v5 connections (1.45–2.91× heap/10, 15.6 MB per connection) while the counters stay at 75–96 MB; every connection's `queueSize` ends at exactly minus its uncharged bytes; throwing-mode and multi-frame controls hold the bound |
| pc75 | `cql-row-limit` (read-limit cluster) | **Confirmed — does not cap** | one `LIMIT N` read or N-row page holds 2.0–2.4 × N × W (replica buffer and coordinator `ResultSet` live together): 512 × 1 MiB rows → 1,241 MiB; a 40 MiB `local_read_size_fail_threshold` aborts larger reads at ≈ 65 MiB held |
| pc91 | `slab-region-size` (slab-tail cluster) | **Confirmed — does not cap** (run 1b, 2026-11-17; supersedes run 1's Not confirmed) | 0.9999 MiB of real heap per written table vs 1.49 KiB counted, the same at 64 / 256 / 2048 MiB limits; 400 tables held 400 MiB, 6.25 × a 64 MiB limit, with no flush; unslabbed control ≈ 1 KB per table. Run 1 missed one frozen sub-prediction that bounded the global memtable gauge (system tables included); the owner approved a dated amendment bounding the test tables only, and run 1b matched the Confirmed row |

All five nodes were left with nothing running; run copies and full logs stay under `/mydata/s4/` on each node.
Four of the five measured mechanisms are new to OOM-exp (N13, N14, N15, the read-limit cluster) and are now
measured at phase-1 scale; whether any reaches an OOM at defaults and an acceptable budget is OOM-exp's question.
