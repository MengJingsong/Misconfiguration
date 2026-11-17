# Phase links — Cassandra

One row per verified OOM-exp case, by the [back-link playbook](../backlink-playbook.md): did phase 1
(`capacity-enforcement-exp`) hold a clue to the result **as filed before the case's first run**?
Classes: `flagged`, `recorded-untested`, `missed`, `no-case`, `out-of-scope` (defined in the
playbook, step 4). Questions E1–E4 are the guided playbook's
[§3.2](../capacity-enforcement-exp/stage3-ai-deep-read/playbook-guided.md#32-enforcement-properties-added-2026-11-16).
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

## What the first pass shows

- **Phase 1 saw almost every mechanism, but its verdicts absorbed them.** Six of seven cases are
  `recorded-untested` and one is `missed`; none is `no-case` or `out-of-scope`. The clue sits in an
  A3/A4 remark, a §8 aside or a stage-4 note, while the estimate stays positive or the stage-4 result
  is filed "caps" (B7 measured 2.17× and filed "Confirmed — caps"). This is what §10's new
  Real-memory estimate and §8a are for.
- **The clues were not where OOM-exp found its leads.** Only C1 and R1-V (and C2 in part) took their
  lead from phase 1; B6, B7, S1 and S2 came from OOM-exp's own traces and heap dumps. The flags file
  (`recheck-flags.md`) is the route meant to close that gap.
- **E1–E4 cover all seven; no new question is proposed.** E1 (B6, B7, S2), E2 (C2), E3 (C1, S1's U1)
  and E4 (R1-V, S1, C1's sum).
- **Sums across pools are the weakest spot.** Nothing in phase 1 adds defaults against a budget
  (R1-V, S1, C1). That is a cross-case check; one case file cannot answer it alone.

## Phase-1 files to recheck (back-link mode)

Guided playbook §5, `back-link` mode. 34 files; some serve several cases:

- **B6, C1:** `internode_max_message_size-inferMessageSize-size--autonomous`, `internode_max_message_size-enqueue-getInternodeMaxMessageSizeInBytes--autonomous`, `internode_application_send_queue_capacity-acquireCapacity-pendingCapacityInBytes--guided`, `internode_application_send_queue_capacity-releaseCapacity-pendingCapacityInBytes--autonomous`, `internode_application_receive_queue_capacity-acquireCapacity-queueCapacity--guided`, `internode_application_receive_queue_capacity-releaseCapacity-queueCapacity--autonomous`, `internode_application_receive_queue_reserve_global_capacity-acquireCapacity-actualExcess--autonomous`, `CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided`
- **B7:** `key_cache_size-create-size--autonomous`, `key_cache_size-applySimpleConfig-keyCacheSizeInMiB--autonomous`, `key_cache_size-setKeyCacheCapacityInMB-capacity--autonomous`, `counter_cache_size-applySimpleConfig-counterCacheSizeInMiB--autonomous`, `counter_cache_size-setCounterCacheCapacityInMB-capacity--autonomous`, `counter_cache_size-putcachedcounter-capacity--autonomous`
- **C2:** `networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided` (also C1, S1), `local_read_size_fail_threshold-addSize-failBytes--guided`, `native_transport_max_request_data_in_flight-releaseItem-globalInFlightBytesBelowLimit--autonomous` (also S2), `coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided`, `coordinator_read_size_fail_threshold-validateReadThresholds-fail--autonomous`, `native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous` (also S2)
- **R1-V:** `memtable_offheap_space-tryAllocate-limit--guided`, `file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided`, `memtable_offheap_space-applySimpleConfig-memtable_offheap_space--autonomous`, `memtable-offheap-space-allocate-size--autonomous`, `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous`
- **S1:** `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided`, `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided`, `MAX_HINT_BUFFERS-switchCurrentBuffer-MAX_ALLOCATED_BUFFERS--guided`, `hints-HintsBuffer-put-slabCapacity--autonomous` (plus the receive-queue and networking files above)
- **S2:** `concurrent_writes-takeWorkPermit-workPermits--autonomous`, `maxTasksQueued-takeTaskPermit-taskPermits--autonomous`, `maxTasksQueued-addTask-taskPermits--autonomous`, `maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous`, `sep_maximum_pool_size-takeWorkPermit-workPermits--autonomous` (plus the two in-flight files above)
