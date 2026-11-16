# Escape hatches and bypass paths from capacity-enforcement-exp, as OOM leads

*Written 2026-11-12.* Lead list, not a result: nothing here has been run. *Updated 2026-11-16: N1 and the
statuses in §2 reflect the 2026-11-12 results (C1, C2, C3).* Source of the notes:
the stage-3 case files of [`capacity-enforcement-exp`](../capacity-enforcement-exp/README.md)
(Cassandra 5.0.9: 304 files; Hadoop 3.4.2: 6 files), where bypass observations are recorded but
not pursued (README §4): the guided template's **Escape hatch / Target-3 note** row and the
autonomous template's **A3** "any path that bypasses it or overshoots it". Stage-4 results were
consulted where they exist. Companion to [`OOM-leads.md`](OOM-leads.md) (patterns S1–S6, leads
L1–L11) and the [Cassandra campaign plan](cassandra/campaign-plan.md) (IDs C/B/R).

## 1. Screening

About 260 Cassandra case files record some bypass or overshoot. Most are not usable for OOM:

| Excluded group | Examples | Why |
|---|---|---|
| Disk only | `cdc_total_space`, `commitlog_total_space`, `max_space_usable_for_compactions_in_percentage` (JMX flag, fail-open `catch`), `DataDirectory_getAvailableSpace` (unchecked on the default `diskBoundaries` path), `repair_disk_headroom_reject_ratio`, `max_hints_size_per_host` (0 = off by default; batchlog replay skips `shouldHint`), sstable/LCS sizes | Disk is out of scope for this campaign (campaign plan, *Scope*) |
| Guard off by default | `local_read_size_fail_threshold`, `row_index_read_size_fail_threshold`, `coordinator_read_size_fail_threshold`, `monitoring_max_operations < 0` | An unset limit is an **unprotected configuration**, not a bypass (protocol 2026-11-10) |
| Bounded by one item | overshoot "by one row / one segment / one frame / one add", Caffeine write-buffer lag, power-of-two rounding | Bounded by an object that another limit already caps |
| Needs corrupt input | `max_value_size` (24 unguarded `readWithVIntLength` sites), `hints-CompressedChecksummedDataInput` (header not validated) | Fault injection by corruption; JIRA J1 positive-control material (9530, 18513), not a default workload |
| Small, heap-derived cap | `streaming_state_size` (weight frozen at insert: 1.54× of 40 MiB at stage 4), `diagnostic_event_*` (off by default), `denylist_*` (operator-populated), `ip_cache`, `permissions_cache` | Excess is a few tens of MiB at most |

## 2. Already covered by OOM-exp

| Bypass / escape hatch (stage-3 case) | OOM-exp item | Status |
|---|---|---|
| Internode queues charge on-wire bytes; payload expands on deserialization (`internode_max_message_size-inferMessageSize`) | **B6** | verified (A gap, B/D OOM diagnostic) |
| Per-link send/receive allowance outside the global reserve, 3·N·C (`internode_application_send/receive_queue_capacity`) | **C1** | `verified-OOM · diagnostic` (run 4, 2026-11-12) |
| `BufferPool` overflow `allocateDirect` with no ceiling (`file_cache_size`, `networking_cache_size`) | **B3** (generic), **B1** (v5 large-request release) | B1 negative; B3 not started; N1's v4 workload is now covered by **C2** |
| Memtable `opGroup.isBlocking()` → `allocated(size)` past `limit` (`memtable_heap/offheap_space`, `largestRatio`, slab cases) | **B2** | not started |
| Caffeine weigher ignores node/table/sketch (`key_cache_size`, `counter_cache_size`) | **B7** | verified-gap · overshoot · deployment |
| Per-thread DOB / `DataOutputStreamPlus` temp buffer × thread count (`DOB_MAX_RECYCLE_BYTES`, `data_output_stream_plus_temp_buffer_size`) | **C3**, R2/R6 | C3 and R6-V `negative`; R2 `reproduced-OOM · diagnostic` (custom); side lead U1 |
| Compressed hints buffer retained per destination writer | **C5** | queued |
| Index summaries uncapped between periodic resizes (`index_summary_capacity`) | **R5**, C4/B5 | queued |
| OHC structures outside `row_cache_size` (yaml says so) | R5, OOM-leads S6 | — |
| Paxos weigher | OOM-leads **L2** | not run |

## 3. New leads (ranked)

Each has a default-reachable path unless stated. "Bound" is what still limits it.

| # | Lead (stage-3 case → stage 4) | Mechanism / playbook row | Bound at defaults | OOM plausibility |
|---|---|---|---|---|
| **N1** | **Covered by C2 for protocol v4 (2026-11-12, `verified-OOM · deployment`); v5 open.** **A native-protocol client that stops reading** ([`networking_cache_size`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/networking_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md) note 1; stage 4 held 192 MiB of response frames: the pool stopped at its cap and the rest went to overflow, a direct-memory rise of ~183 MiB *whatever the knob*) | pool fallback + stalled consumer (S2/S3, J2). The pipeline sets `WRITE_BUFFER_WATER_MARK` (8–32 KiB, `transport/PipelineConfigurator.java:139`), but nothing in `transport/` checks `isWritable()`, so responses keep being queued. The request in-flight limits release on processing and never count responses | None found in `transport`; only `MaxDirectMemorySize` (default = `-Xmx`) and the number of requests the client sends | **High.** One unprivileged client at default config. Pipeline reads that return ~1 MiB each and never read the socket; sweep connections and response size; budget 2 GiB and up (V7). **Check JIRA 14855/15013 and later Flusher changes first**: if a known fix should cover this, a reproduction is a regression |
| **N2** | **v4 force-allocation per connection × unlimited connections** ([`native_transport_max_request_data_in_flight_per_ip`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/native_transport_max_request_data_in_flight_per_ip-setNativeTransportMaxRequestDataInFlightPerIpInBytes-maxRequestDataInFlightInBytes--autonomous.md) (ii); stage 4: v5 strict, v4 soft with bypass) | exempt mode + multiplicity. `PreV5Handlers.java:182-186`: a refused request is still allocated with `allocate()`, then the connection pauses, so **each** connection overshoots by one request (plus requests already decoded in the same read). `native_transport_max_concurrent_connections` and `…_per_ip` default to −1. v5 adds 1 MiB per connection outside the global limit | Overshoot ≈ C × max message size, with max message = min(`max_mutation_size` 16 MiB, heap/10, heap/40) | **High.** Extends **OOM-leads L1**: C connections × 16 MiB on-wire × the B6 heap expansion (≈ 20× tiny-cell, 2.2× blob). At 2 GiB heap, 64 v4 connections can admit ~1 GiB on-wire beyond the limits before the expansion is counted. Use the B6 payload; slow the mutation stage with the B6 disk stall so admitted requests stay live |
| **N3** | **Uncounted serialized copy per mutation** ([`CACHEABLE_MUTATION_SIZE_LIMIT`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/CACHEABLE_MUTATION_SIZE_LIMIT-serialization-CACHEABLE_MUTATION_SIZE_LIMIT--guided.md); stage 4: bypass as recorded, the receive side kept 24 copies) | accounting mismatch (S1). Mutations under the limit carry a cached serialized copy that no in-flight counter charges; at value 0 the receive side (replica, replay, hints, batchlog) caches every mutation whole | Per mutation: one extra copy of its serialized size | **Amplifier, not standalone.** Add it as a term to B6/N2/L7 designs (held ÷ counted gains up to +1×) |
| **N4** | **Commit-log replay counts serialized bytes** ([`commitlog_max_outstanding_replay_bytes`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/commitlog_max_outstanding_replay_bytes-handlemutation-pendingmutationbytes--autonomous.md); [`max_mutation_size`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md): replay unguarded, observed at stage 4) | accounting mismatch + exempt path (S1 + S5). Replay bounds pending work at 64 MiB / 1024 mutations (`CassandraRelevantProperties.java:114-115`) **of serialized size**, and the mutation is deserialized before the check | ~64 MiB on-wire × expansion, + one mutation | **Medium–high; makes OOM-leads L7 concrete.** Tiny-cell mutations at ×20 put ~1.3 GiB of live heap in flight during startup replay. Run: fill the commit log with tiny-cell map writes, kill -9, restart at 1–2 GiB heap. Interacts with N3 (replay caches copies) |
| **N5** | **Merkle-tree budget per validation, not per node** ([`repair_session_space-initHelper`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/repair_session_space-initHelper-max--autonomous.md), [`repair_session_space-split`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/repair_session_space-split-maxsize--guided.md); stage 4: overflow observed, 2048 MiB → two-leaf trees) | multiplicity (S4, J5 19336, J3 14096/15202). Default heap/16 (`DatabaseDescriptor.java:609-610`) **per validation**; the coordinator holds the trees of all replicas, sized by **their** settings; a 32-bit overflow at `ValidationManager.java:62` | tables × ranges × replicas × concurrent sessions | **Medium.** Repair many tables in parallel (`nodetool repair -j 4`, several keyspaces) at default heap; count live trees on the coordinator. Check 19336's fix scope in 5.0.9 |
| **N6** | **SAI memtable index under-charge** ([`memtable_heap_space-adjustMemtableSize`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/memtable_heap_space-adjustMemtableSize-0--autonomous.md); stage 4: unit loose cap, cluster undetermined) | accounting mismatch (S1). Only 36 B/key is charged; `PrimaryKey`/`DecoratedKey`/token per row (~144 B, estimated), trie buffer doubling slack (up to 2×) uncharged; with `offheap_*` the SAI trie is off-heap but charged to the heap pool | memtable cap (heap/4 by default) × under-count | **Medium–low.** Stage 4 measured c_s ≈ 134 B/row charged vs c_t + c_s ≈ 646 B/row, so +144 B is ≈ 1.2×; B7-like, bounded by a heap-derived cap. Worth one histogram (several SAI indexes on one tiny-row table) before any OOM run |
| **N7** | **Vector ANN fallback keeps every rejected key** ([`SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/SAI_VECTOR_SEARCH_MAX_MATERIALIZE_KEYS-materializeKeysAndCloseSource-MAX_MATERIALIZED_KEYS--guided.md); stage 4: 245,256 keys held) | escape (disallow branch unbounded). Past *L* (16,000) the ANN plan's `processedKeys` grows with each rejected row, ≈ 148 B/key | rows read before the read timeout × `concurrent_reads` (32) | **Medium–low.** Stage 4 read ~115k rows per timeout window → 32 × 115k × 148 B ≈ 0.5 GiB. Strong only if the replica keeps reading after the timeout; check that first |
| **N8** | **Guardrails skipped for superusers, and the default authenticator makes every client a superuser** ([`items_per_collection`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/items_per_collection-doAdd-elements_size--autonomous.md); stage 4: caps only on some paths) | exempt caller. `ClientState.isSuper()` is true when the authenticator does not require auth (`ClientState.java:602-605`) | — | **Caveat, not a lead.** Any OOM design that relies on a guardrail (collection size, partition size, vector term size) as the protection does not hold at default auth; use `PasswordAuthenticator` and a non-superuser in controls |
| N9 | Single-partition / internal / virtual-table batches skip `batch_size_fail_threshold`; the whole batch is on the heap before the check ([case](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md)) | exempt caller | message size (16 MiB) | Low alone; a payload shape for N2/L3 |
| N10 | Vector update path skips `validateTermSize` ([`sai_vector_term_size_fail_threshold`](../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/sai_vector_term_size_fail_threshold-add-value--autonomous.md); stage 4: bypass confirmed) | exempt path | mutation size; charged to memtable | Low (a guardrail bypass, not a memory-pool bypass) |
| N11 | Slab-region tail waste uncharged (`max-region-size`, `slab-region-size`, `max_region_size` cases); `heap_buffers` is the 5.0.9 default (`cassandra.yaml:825`) | accounting mismatch | ≤ one cloned item per abandoned 1 MiB region | Low; one histogram with values just over the half-region boundary |
| N12 | Unbounded SEP / compaction executor queues (`maxTasksQueued`, `concurrent_writes`, `concurrent_compactors`); Paxos `ACTIVE` map unbounded | stalled consumer (S3) | admission upstream (native in-flight bytes, internode queues) | Supports OOM-leads L4; useful only on a path with no upstream admission (hint dispatch, batchlog replay) |

## 4. Hadoop (6 stage-3 cases)

No OOM-exp Hadoop cases exist yet ([`hadoop/README.md`](hadoop/README.md)). Of the bypasses recorded:

- **`fs.s3a.prefetch.block.count`**: files ≤ `block.size` (8 MiB) go to `S3AInMemoryInputStream`, one
  whole-file `ByteBuffer` that never uses the pool, and the pool is per stream with no JVM-wide cap. So
  N concurrent small-file streams hold N × file size. Multiplicity, heap; the only Hadoop item worth a
  convergence test, and it needs an S3 endpoint (a local S3 mock) on the stage-4 node.
- **`RawPathHandle_MAX_SIZE`**: per object 1 MiB, no total; the `PathHandle` constructor allocates with
  no bound. Needs many serialized handles; low.
- `DF_getAvailable`, `fs.s3a.prefetch.max.blocks.count`: disk. `MAX_KEY_SIZE`, YARN queue capacity: no
  memory bypass.

Wait for more Hadoop cases (queues in `capacity-enforcement-exp/hadoop/`) and the J2 JIRA survey before
starting Hadoop OOM runs.

## 5. Recommendation

1. ~~**N1 (slow-reading client) as the concrete B3 run.**~~ *Done for protocol v4 as **C2** (`verified-OOM ·
   deployment`, 2026-11-12). What remains is the v5 path (`CQLMessageHandler`, framed flusher via the
   networking `BufferPool`) and the JIRA check (14855, 15013) before any upstream report.*
2. **N2 + N3 folded into L1.** Same harness as B6; vary v4 connection count at a fixed per-IP limit.
   Report the force-allocation per connection as the bypass and the expansion ratio as the accounting
   mismatch (tag **mixed** if both contribute).
3. **N4 (replay)** next: a cheap kill -9/restart harness on the B6 payload, budget swept per V7.
4. N5–N7 only after a source re-check and a single held ÷ counted measurement each (OOM-leads rule 5).
