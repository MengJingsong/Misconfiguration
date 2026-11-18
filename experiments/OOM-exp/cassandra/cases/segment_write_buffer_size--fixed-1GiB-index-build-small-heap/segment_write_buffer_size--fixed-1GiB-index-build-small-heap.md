# C8 — sai_options.segment_write_buffer_size: a fixed 1 GiB of heap for SAI index builds, not scaled to the heap  <!-- file: cassandra/cases/segment_write_buffer_size--fixed-1GiB-index-build-small-heap/segment_write_buffer_size--fixed-1GiB-index-build-small-heap.md -->

| Field | Value |
|---|---|
| Case ID | `C8` (C = convergence, the ID assigned with the pick; README "ID prefixes". Predicted class by the protocol's measurement table: **convergence** — the SAI builder domain stays within its contract (U ≤ C = 1,024 MiB) and the sum with the memtable pool and the baseline exceeds the heap; if the build alone reaches the endpoint (branch (c) in §2.7), the label is convergence of one fixed pool with the baseline, interpretation *configuration-sizing gap*. Stage 2 labels it from the readings) |
| From | `OC-24` of the phase 1 OOM candidate list |
| Phase-1 case file | [`segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md); stage-4 evidence: [results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`; on pc96 `/mydata/s4/cassandra-base`, jar `build/apache-cassandra-5.0.9-SNAPSHOT.jar`), OpenJDK 11.0.33, G1 (`conf/jvm11-server.options:63`) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow), 2026-11-18 ≈ 08:00–08:45 America/New_York; nothing run on a node (read-only checks of pc96: `free`, `df`, `ps`, `ss`; one 1-second Lucene probe in the scratchpad, §2.1) |
| Stage 2 (verify) | fresh OOM-agent stage-2 session (workflow), 2026-11-18 08:10–10:15 America/New_York, pc96 (local); 16 runs, §3 |
| Verdict | **`true positive`** — `verified-OOM · deployment` (heap OOM 3/3 at a 1.5 GiB heap, all capacities at defaults; §4) |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`). On a stock 5.0.9 node with a 1.5 GiB heap (what
  `cassandra-env.sh` picks on a 3 GiB machine) and every capacity at its default, building one SAI index over 2,000,000 existing
  rows while writes run ended in a **Java heap OOM in 3/3 runs**; the build alone (0/3), the writes alone (0/2) and the same
  build + writes with the SAI limit at H/8 (0/3, both builds complete) did not. At a 2 GiB heap the same load did not OOM (0/3)
  but held 93 % of the heap after full GCs. Direction: convergence (possibly mixed, see the key cache below).
- **Root cause (measured):** the SAI segment builder held its full fixed 1,024 MiB contract (983–994 MiB live in the dumps,
  counter 977–987 MiB), two thirds of the heap, next to the memtable pool (≈ 230 MiB, within its 384 MiB) and the key cache that
  the build itself fills (≈ 190 MiB held while its weigher counts ≈ 70 MB of a 76 MiB cap). No control ties the SAI limit to
  the heap or reserves heap before a term is added.
- **Root cause (hypothesis, stage 1):** SAI index builds outside memtable flush (`CREATE INDEX` on existing data, `nodetool rebuild_index`,
  every compaction of an SAI-indexed table) buffer their segments on heap under one global soft limit,
  `sai_options.segment_write_buffer_size`, whose default is a fixed **1,024 MiB** whatever the heap. Every other large heap pool
  is derived from the heap (memtable H/4, key cache 5 % ≤ 100 MiB, native in-flight H/10). On a small but accepted heap
  (≤ 2 GiB, what `cassandra-env.sh` picks on a ≤ 4 GiB node) the build's 1 GiB plus the memtable pool under a write load plus
  the baseline is at or above the heap, and nothing ties the SAI limit to free heap.
- **Design in one line:** on pc96, restore one sstable of 2,000,000 rows with a unique 32-character text value per row, start a
  stock node with a 2 GiB heap, run an unthrottled `cassandra-stress` write load into another table and build an SAI index on
  the text column (`CREATE INDEX`, then `rebuild_index`); expect a Java heap OOM while the builder holds ≈ 1 GiB; controls are
  the build alone and the writes alone, the intervention is `segment_write_buffer_size` = heap/8; a frozen ladder steps the
  heap down to 1.5 and 1 GiB if 2 GiB survives and up to 2.5 GiB if it fails.

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, line 33):**

> | OC-24 | 2026-11-16 | `segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous` | legacy | [lead list, budget ledger heap, blind, E4; N18] SAI's segment-build budget is a fixed, soft 1,024 MiB of heap (`StorageAttachedIndexOptions.java:26`; builders flush only past limit ÷ building indexes, `SSTableIndexWriter.java:245-248`); with memtable H/4, request H/10, the two 512 MiB internode reserves and the caches, the defaults exceed H for every H below ≈ 3.4 GiB (+937 MiB at 2 GiB) while SAI indexes build. | CP-8 | picked: C8 |

**Phase-1 constraint and check.** The phase-1 entry is the hard-coded `MAXIMUM_SEGMENT_BUFFER_MB = 32768`
(`StorageAttachedIndexOptions.java:29`), checked once at startup by `validate()` (`:39-45`, called from
`DatabaseDescriptor.java:1022`). Its estimate was `negative` (a startup sanity ceiling, does not cap memory). The operand that
matters here is the setting itself: `segment_write_buffer_size` default `DEFAULT_SEGMENT_BUFFER_MB = 1024`
(`StorageAttachedIndexOptions.java:26`, `:35`), commented out in the shipped `conf/cassandra.yaml:1790-1794` ("Total permitted
memory allowed for writing SAI index segments. This memory is split between all SAI indexes being built so more indexes will
mean smaller segment sizes."). Nothing in the yaml text or the code relates it to the heap.

**What stage 4 measured (2026-10-28, pc32, 4 GiB heap, one 1.29 GB sstable, `CREATE INDEX` + `rebuild_index`).** Outcome
class *true negative* for the constant. Readings that matter for this case: the limiter gauge reached the configured limit
exactly (peak `SegmentBufferSpaceUsedBytes` 1,073,744,152 B at the default 1,024 MiB; 64.0 / 256.0 MiB at 64 / 256), 16
memory-limit flushes per build at 1,024 MiB (`Current builder usage is 1.000GiB for 376084 cells`, ≈ 2,855 B per 400-byte
term), and an `int` saturation caps any setting ≥ 2,048 MiB at 2 GiB − 1 B (`V1OnDiskFormat.java:126`, `DataStorageSpec`
`toBytes()`). The node did **not** fail at a 4 GiB heap with the default (sampled heap peak 3,912 MiB, garbage included;
no ERROR lines). No heap below 4 GiB, no concurrent write load and no live-heap (histogram) reading were taken.

**JIRA prior art (read only; nothing posted).**
- Local survey `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`: SAI-related rows are
  CASSANDRA-20752 (Fixed 5.0.6: switched sstable writers kept their SAI segment builders unflushed under UCS sharding —
  a different mechanism, its fix `onSSTableWriterSwitched` is in 5.0.9, `SSTableIndexWriter.java:104-113`), CASSANDRA-18673
  (Fixed 5.0-alpha1, component sizes; limiter refactor only in passing). SASI-era relatives (CASSANDRA-11383, 12662, 16071)
  concern SASI, which ships disabled.
- Apache JIRA REST search (reachable, 2026-11-18): `text ~ "segment_write_buffer_size"` (59 hits, none about SAI build memory),
  `text ~ "SegmentBuilder"` (14), `text ~ "NamedMemoryLimiter"` (3: 18673, 18598, 19367), `text ~ "minimumFlushBytes"` (0),
  `component = "Feature/SAI" AND (text ~ OutOfMemoryError OR OOM OR "heap pressure")` (2: 20752, 18673),
  `component = "Feature/SAI" AND text ~ segment AND text ~ memory` (10; none reports a heap OOM from the fixed default or asks
  to derive it from the heap).
- **Verdict: `new`** (no issue reports the fixed 1 GiB SAI build buffer against small heaps; not documented as by design beyond
  the yaml comment quoted above).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism and direction

1. **The budget.** `V1OnDiskFormat.java:126-128` builds one static `NamedMemoryLimiter` from
   `DatabaseDescriptor.getSAISegmentWriteBufferSpace().toBytes()` (`DatabaseDescriptor.java:5264-5266`): 1,073,741,824 B at the
   default. The limiter is a counter only (`NamedMemoryLimiter.java:53-75`: `usageExceedsLimit()` is `bytesUsed > limitBytes`,
   no blocking, no reservation). It is global: every SSTable-based build in the JVM shares it.
2. **Who uses it.** `V1OnDiskFormat.newPerColumnIndexWriter` (`:168-189`) returns an `SSTableIndexWriter` whenever the operation
   is not a memtable FLUSH (or the index's initial build has not started): initial build after `CREATE INDEX`
   (`StorageAttachedIndexBuildingSupport` → `StorageAttachedIndexBuilder.build()`), `nodetool rebuild_index`, and every
   compaction of an SAI-indexed table.
3. **What is held.** `SSTableIndexWriter.addTerm` (`SSTableIndexWriter.java:205-243`) adds each term to the current
   `SegmentBuilder.TrieSegmentBuilder` and charges `limiter.increment(bytes)` with the builder's own estimate
   (`SegmentBuilder.java:168-199`). The builder is a `SegmentTrieBuffer` (`SegmentTrieBuffer.java:46-78`): an `InMemoryTrie`
   whose buffers are on heap under the default `memtable_allocation_type: heap_buffers` (`:48`, `toBufferType()`), and per
   distinct term one Lucene `PackedLongValues.Builder` for its postings (`:124-146`). The charge is `trie.sizeOnHeap()` delta
   (counts `allocatedPos`, not the allocated buffer capacity, `InMemoryTrie.java:975-981`; buffers grow by doubling,
   `:140-160`) plus the builder's `ramBytesUsed()` delta. **Measured in stage 1 (scratchpad probe, lucene-core 9.7.0):** an
   empty `deltaPackedBuilder(COMPACT)` reports `ramBytesUsed() = 2,352 B` (a `long[256]` pending page), so each **distinct**
   term costs ≈ 2.35 KB plus its trie bytes, whatever its length (stage 4: ≈ 2,855 B per 400-byte term). 1 GiB is reached after
   ≈ 437,000 distinct short terms.
4. **When it is released.** `shouldFlush` (`SSTableIndexWriter.java:245-262`) flushes the current segment when the global
   usage is above the limit **and** this builder holds at least `minimumFlushBytes`; the memory is released only after the
   segment is written (`flushSegment`, `:264-307`, `release()` at `:294`). `minimumFlushBytes` is a **static** field
   (`SegmentBuilder.java:52`) set to `limit / active builders` (`:149`, `:234`), so concurrent builders share one threshold and
   the counted total stays ≈ the limit (checked: no multi-builder amplification beyond a few terms per builder; the OC-24 row's
   "limit ÷ building indexes" is this rule). So the builder domain is bounded **softly at ≈ 1 GiB counted**, plus uncounted
   trie-buffer and content-array capacity slack (≤ 2× of the trie part, a few % for short terms) and the flush's temporaries.
5. **Why it can exceed the heap.** The limit is not derived from the heap, while the other heap pools are: memtable heap pool
   H/4 (`DatabaseDescriptor.java:586-587`), key cache min(5 % of heap, 100 MiB) (`:815-816`), native in-flight reserve H/10
   (`:651`). At H = 2 GiB the build alone is 50 % of the heap; with the memtable pool filled by a concurrent write load
   (contract 512 MiB, flushes start at 1/3 of it, `memtable_cleanup_threshold` = 1/(1+2), `:753-763`) and the baseline,
   the sum approaches or exceeds the heap (§2.4). Nothing reserves heap before a term is added.

**Direction:** convergence (several pools within their own contracts exceed a shared heap budget), technique note
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (fixed absolute default occupies a larger
fraction of a smaller budget; multiplicity/overlap dial before budget dial). **Interpretation:** configuration-sizing gap
(a fixed absolute default for a heap pool on a heap-scaled system), not an implementation defect.

**Not tested here (named so a later design can add them):** the OC-24 row's two 512 MiB internode reserves and the native
H/10 request reserve need peers / large concurrent requests; this design is a single node. The row's "≈ 3.4 GiB" boundary
therefore is not the predicted boundary here (§2.4).

### 2.2 Protection map

| Domain | Allocation and owner | Local contract (counter K, limit C) | Scope / multiplicity | Aggregate coverage | Lifetime | At the limit |
|---|---|---|---|---|---|---|
| D1 SAI segment builders | `SegmentTrieBuffer` (on-heap `InMemoryTrie` buffers + one `PackedLongValues.Builder` ≈ 2.35 KB per distinct term), built by `SSTableIndexWriter` on the compaction executor | K = `SegmentBufferSpaceUsedBytes` gauge (limiter `bytesUsed`); C = 1,024 MiB fixed, **soft** (flush at the next add after K > C and own ≥ C/N) | global, all SSTable-based builds; N concurrent builders share one threshold; `concurrent_index_builders` 2, `concurrent_compactors` 2 at one data dir (`DatabaseDescriptor.java:777-778`) | none beyond the limiter; no heap check | until the segment flush completes | flush segment to disk, then release; no blocking |
| D2 memtable heap pool | memtable slab regions (1 MiB on-heap regions, `heap_buffers`) and partition objects | K = pool on-heap owns (`AllMemtablesOnHeapDataSize` global gauge); C = H/4 | per node, all tables | writers block on allocation at C (`MemtablePool` `BlockedOnAllocation`); flush at cleanup threshold 1/3·C | until the flushed memtable is discarded | writes wait; flush |
| D3 key cache | Caffeine cache | C = min(5 % H, 100 MiB) (`:815-816`) | node | weigher | eviction | evict; not exercised (no reads) |
| D4 native in-flight | decoded requests | C = H/10 | node | reserve | until response | backpressure; not reached (stress requests ≈ 4 KB × ≤ 32 threads) |
| D5 baseline | schema, metrics, threads, buffers, sstable readers | none | node | none | standing | — (measured as B0) |
| D6 write path transient | mutations in flight, response objects | bounded by `concurrent_writes` 32, `native_transport_max_threads` 128 | node | executor bounds | per request | queueing |

Budget: Java heap H (−Xms = −Xmx); the JVM direct limit is set to what `cassandra-env.sh` resolves for the claimed node
(H/2, §2.3) and is not a claimed domain; no cgroup memory limit (swap pinned to 0 only).

### 2.3 Configuration and budget audit

- **Build:** stock 5.0.9 copied from `/mydata/s4/cassandra-base` to `/mydata/s4/c8-w1/cassandra` (`cp -a`; record
  `git describe --tags` and the jar sha256; never run `ant` there). No patches, no Byteman, no agents.
- **Tested capacities (all at shipped defaults, unset in the yaml):** `sai_options.segment_write_buffer_size` 1,024 MiB
  (except the intervention arm); `memtable_heap_space` H/4; `memtable_allocation_type: heap_buffers` (shipped
  `conf/cassandra.yaml:825`); `memtable_flush_writers` 2, `memtable_cleanup_threshold` 1/3; `key_cache_size`
  min(5 % H, 100 MiB); `native_transport_max_request_data_in_flight` H/10; `concurrent_index_builders` 2;
  `concurrent_compactors` 2; `commitlog_total_space` 8,192 MiB. Resolved values per heap (record from the startup log):

  | H (heap) | D1 SAI | D2 memtable C (flush at 1/3) | D3 key cache | D4 in-flight | direct limit set (H/2) |
  |---|---|---|---|---|---|
  | 1,024 MiB | 1,024 | 256 (85) | 51 | 102 | 512 MiB |
  | 1,536 MiB | 1,024 | 384 (128) | 76 | 154 | 768 MiB |
  | 2,048 MiB | 1,024 | 512 (171) | 100 | 205 | 1,024 MiB |
  | 2,560 MiB | 1,024 | 640 (213) | 100 | 256 | 1,280 MiB |

- **Budget (V7):** heap 2 GiB is the ideal value and the first arm; the ladder goes to 1.5 and 1 GiB only if 2 GiB does not
  reach the endpoint, and to 2.5 GiB if it does. All are ≥ 512 MiB (standing rule, no per-case review). Claimed node: a
  node with 2H of RAM (4 GiB for H = 2 GiB), for which `cassandra-env.sh:57-66` resolves heap = ½ RAM and
  `MaxDirectMemorySize` = ¼ RAM = H/2; the runs set `MAX_HEAP_SIZE=<H>M` and `MAX_DIRECT_MEMORY_SIZE=<H/2>M` to reproduce
  that resolution on pc96 (pc96 itself would resolve 15,872 / 7,936 MiB). No container limit; swap 0 via
  `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`).
- **Environment changes (disclosed, not capacities):** single node on loopback `127.0.0.8`, `storage_port 7008`,
  `native_transport_port 9048`, `JMX_PORT=7208` (edited in the copied `conf/cassandra-env.sh:235`, because other sessions on
  pc96 may run nodes on the defaults), `cluster_name: c8`, seeds `127.0.0.8:7008`; data, commit log, hints, saved caches and
  cdc under the run's instance directory on `/mydata`; node pinned with `taskset -c 0-15`, stress with `taskset -c 16-23`
  (shared machine; `ParallelGCThreads` is still set from `/proc/cpuinfo` = 32 by `cassandra-env.sh:183` — record it).
- **Supporting deviations:** none. Logging stays at the shipped `logback.xml` (DEBUG to `debug.log`, which carries the
  limiter flush lines). GC log is the shipped `-Xlog:gc…` (`cassandra-env.sh:81-83`). `-XX:+HeapDumpOnOutOfMemoryError` and
  `-XX:OnOutOfMemoryError="kill -9 %p"` are shipped (`jvm-server.options:120`, `cassandra-env.sh:209`); `CASSANDRA_HEAPDUMP_DIR`
  points into the instance directory.
- **Schema/workload variables (disclosed):** keyspace `c8` RF 1 with `c8.big (pk bigint PRIMARY KEY, v text)` and
  `c8.small (pk bigint PRIMARY KEY, v text)`, default table options (STCS, LZ4); one SAI index per arm, default options;
  `cassandra-stress` default schema `keyspace1.standard1` RF 1.

### 2.4 Ceiling arithmetic (contract capacities + baseline vs heap)

Baseline B0 (live heap after node start with the seed restored, before any arm) is measured per run; estimate 150–250 MiB.
Peak live per condition = B0 + D1 + D2 + D6 (D3, D4 not exercised):

| H | B alone: B0 + 1,024 (+≤ 5 % slack) | W alone: B0 + D2 ≤ C | BW: B0 + 1,024 + D2 (171…C) | prediction |
|---|---|---|---|---|
| 1,024 MiB | 1,200–1,330 (**> H**) | 300–510 | — | B alone OOM (certain if the builder reaches 1 GiB) |
| 1,536 MiB | 1,200–1,330 (78–87 %) | 330–640 | 1,370–1,710 (89–111 %) | B survives (GC stress); BW OOM likely |
| 2,048 MiB | 1,200–1,330 (59–65 %) | 350–760 | 1,370–1,840 (67–90 %), + D6 and G1 headroom | B survives; W survives; BW OOM **if** D2 stays near C while D1 is near 1 GiB |
| 2,560 MiB | 1,200–1,330 | 400–890 | 1,410–1,970 (55–77 %) | survives (feasibility margin > 20 %) |

Feasibility: at 2 GiB Σ contracts + baseline (1,024 + 512 + 100 + 205 + 200 ≈ 2,041 MiB) ≈ H, so OOM at 2 GiB is reachable
only with D2 near its cap at the same time as D1 at its peak; at 1.5 GiB the sum exceeds H by ≈ 25 %. The OC-24 row's
≈ 3.4 GiB needs the internode reserves (not in this design); the expected largest failing heap here is 2 GiB, else 1.5 GiB.

### 2.5 Workload and environment (pc96 only, run locally)

- **Node check first:** `ps -eo pid,cmd | grep '[C]assandraDaemon'`, `ss -ltn | grep -E ':(9048|7008|7208)\b'` (must be
  empty), `df -h /mydata` (≥ 150 GiB free before every W/BW run), `uptime`. Do not touch `/mydata/s4/c4-w1`,
  `/mydata/s4/r7-w1` or any process not started by this case.
- **Layout:** `B=/mydata/s4/c8-w1`: `cassandra/` (build copy), `seed/` (restored data), `inst/<run>/` (conf copy, data,
  commitlog, hints, logs, dumps; deleted after each run), `runs/<run>/` (logs, csv, histograms, outcome), `runs/summary.txt`.
  Harness sources in the case folder `harness/`, copied to `$B/h/`.
- **Seed (once, preparation, not a reading):** start a node from `$B/cassandra` with `MAX_HEAP_SIZE=8G` (defaults otherwise,
  same environment yaml); create keyspace `c8` (SimpleStrategy RF 1), tables `big` and `small`; load `big` with
  **2,000,000 rows** `pk = i`, `v = md5_hex("big-" + i)` (32 characters, all distinct) and `small` with **200,000 rows**
  (`md5_hex("small-" + i)`), using the bundled Python driver (`lib/cassandra-driver-internal-only-*.zip`, as in the stage-4
  harness `cluster-run.py:113-123`), `execute_concurrent_with_args`, concurrency 128, CL ONE; create the stress schema with
  `tools/bin/cassandra-stress write n=1000 cl=ONE -schema 'replication(factor=1)' -node 127.0.0.8 -port native=9048 jmx=7208`;
  `nodetool -h 127.0.0.1 -p 7208 flush`; `nodetool … compact c8 big`; `nodetool … compact c8 small` (one sstable each; check
  with `nodetool tablestats`); `nodetool … drain`; stop; copy `data/` and `commitlog/` to `$B/seed/`. Record row counts and
  sstable sizes.
- **Per run:** fresh `inst/<run>/` from `seed/`, conf from `$B/cassandra/conf` plus the yaml diff of §2.3 (and, in arm I,
  `sai_options: { segment_write_buffer_size: <H/8>MiB }`), start with
  `CASSANDRA_CONF=$I/conf CASSANDRA_LOG_DIR=$I/logs CASSANDRA_HEAPDUMP_DIR=$I/dumps MAX_HEAP_SIZE=<H>M
  MAX_DIRECT_MEMORY_SIZE=<H/2>M systemd-run --user --scope -p MemorySwapMax=0 --unit c8-<run> taskset -c 0-15
  $B/cassandra/bin/cassandra -f` launched as `( setsid nohup … < /dev/null > $I/logs/launch.log 2>&1 & )`; wait for
  `nodetool statusbinary` = running (bounded poll ≤ 180 s). Then:
  1. Sampler (§2.6) started; B0: `jcmd <pid> GC.class_histogram > hist-B0.txt` (one forced GC, before the arm).
  2. The arm:
     - **W (writes alone):** `taskset -c 16-23 tools/bin/cassandra-stress write duration=300s cl=ONE no-warmup
       -col 'size=fixed(1024)' 'n=fixed(4)' -rate threads=32 -node 127.0.0.8 -port native=9048 jmx=7208 -mode native cql3
       -log interval=1 file=$R/stress.log` (unthrottled; the memtable pool, not the client, is meant to be the limit).
     - **B (build alone):** `CREATE INDEX v_idx ON c8.big (v) USING 'sai'` (cqlsh against 127.0.0.8 9048); wait for the
       initial build to finish (poll every 2 s: `debug.log`/`system.log` "Index build of … complete" or
       `nodetool compactionstats` without an index build, ≤ 8 min); then `nodetool … rebuild_index c8 big v_idx` (blocking,
       ≤ 8 min). Two full passes over the 2,000,000-term sstable ≈ 9 limiter cycles of 0 → 1 GiB.
     - **BW (build + writes):** start W with `duration=600s`; after 60 s run B; when B finishes, the node dies, or the 12-min
       cap is reached, stop stress (kill its PID).
     - **BS (branch (c) control, build below the limit):** B on `c8.small` (`CREATE INDEX vs_idx ON c8.small (v) USING 'sai'`,
       then `rebuild_index c8 small vs_idx`): ≈ 200,000 × 2.4 KB ≈ 470 MiB, the builder never reaches the limit.
     - **I (intervention):** the branch's test arm (BW or B) with `segment_write_buffer_size: <H/8>MiB` (256 MiB at 2 GiB,
       192 at 1.5 GiB, 128 at 1 GiB).
  3. Stop: stress PID, then `nodetool stopdaemon` (≤ 60 s) else kill the node PID; confirm no `java` process with
     `$I` in its command line and `systemctl --user stop c8-<run>.scope`; move any `dumps/*.hprof` to `runs/<run>/`; copy
     `system.log`, `debug.log`, `gc.log*`, `launch.log`, `hs_err*`; write `outcome.txt`; `rm -rf $I`.
- **Hard cap per run:** 12 min wall from node start. **Expected durations:** node start ≈ 20 s, B ≈ 2 × 1–2 min, BW ≈ 5 min,
  W 5 min, stop/collect ≤ 1 min (+ ≈ 20 s for a 2 GiB dump) → ≈ 6 min per run.
- **CPU:** node on 16 cores, stress 32 threads on 8 cores, Python helpers `nice -n 19`; hprof parsing in the background with
  `nice -n 19` on one core.

### 2.6 Instruments and readings (U measured independently of K)

- **Sampler (every 500 ms, JMX 127.0.0.1:7208):** the stage-4 `Sampler.java` (copy from
  `capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/segment_write_buffer_size-validate-maximum_segment_buffer_mb--autonomous/`)
  extended with: `org.apache.cassandra.metrics:type=Table,name=AllMemtablesOnHeapDataSize` (K_D2),
  `type=MemtablePool,name=BlockedOnAllocation` (count), `type=MemtablePool,name=PendingFlushTasks`; columns: epoch ms,
  K_D1 (`SegmentBufferSpaceUsedBytes`), `SegmentBufferSpaceLimitBytes`, `ColumnIndexBuildsInProgress`, heap used, heap
  committed, K_D2, blocked count, pending flushes. Process `RssAnon` from `/proc/<pid>/status` every 1 s.
- **Live heap independent of the counters (U):**
  - GC log: heap occupancy after each young/mixed/full GC (`gc.log`, shipped config) → peak and trend of live heap per run;
    full-GC count and STW time per 60 s window (service-loss criterion, default: ≥ 90 % STW over ≥ 60 s).
  - Heap dump at OOM (shipped `HeapDumpOnOutOfMemoryError`): class histogram with `hprofhist.py` (copy from
    `cases/cql-row-limit--wide-row-default-pages/harness/`): D1 U = instances of
    `org.apache.lucene.util.packed.PackedLongValues$Builder` × their shallow + `long[256]` (2,080 B each) + `byte[]` held by
    the trie buffers (`InMemoryTrie` chunks: power-of-two `byte[]` of 256 B … 2^k); D2 U =
    `org.apache.cassandra.utils.memory.SlabAllocator$Region` count × 1 MiB (as C6 measured with `hprof_scan.py`). Parse at
    least one dump per failing condition (all if time allows).
  - Survivor arms (control and intervention, **not** the test arm): one `jcmd <pid> GC.class_histogram` the first time K_D1 ≥
    0.95 × the limit (B, BS never reaches it: take it at K_D1 peak − 5 % instead, i.e. after the build's last limiter
    flush line or at ≥ 400 MiB), and in W at t = 240 s. One forced GC per run; record its time.
- **Log lines:** limiter flushes `Global limit of … exceeded. Current builder usage is … for N cells` (debug.log) → count and
  bytes per cell; `Starting a compaction index build. Global segment memory usage` (system.log); the first
  `OutOfMemoryError` with its thread and stack (system.log / launch.log; the dump records no throwing frame, so take the
  thread from the log); stress op rate per second (`stress.log`).
- **Outcome line per run** (`runs/summary.txt`): run, arm, H, SAI limit, endpoint (heap OOM / direct OOM / kill / none /
  invalid), time from arm start to endpoint, peak K_D1, peak K_D2, peak heap used, peak post-GC occupancy, B0, builds
  completed, flush lines, stress mean op/s, histogram key counts.
- **Self-check:** `selfcheck.py` re-parses `gauges.csv`, `gc.log*`, `debug.log` and `system.log` of every run and reproduces
  each outcome line in Python (no ad hoc `awk`).

### 2.7 Predicted response, decision ladder and stopping budget

**Predictions.** Limit gauge = 1,073,741,824 at defaults (H/8 in I). In B and BW, K_D1 rises to ≈ 1 GiB and drops after
each limiter flush (sawtooth, ≈ 9 peaks in two builds). B alone at 2 GiB: live peak B0 + ≈ 1.05 GiB, survives. W alone:
K_D2 oscillates up to ≤ H/4, survives. **BW at 2 GiB: Java heap OOM** in a mutation, flush or index-build thread while
K_D1 is within 10 % of 1 GiB and K_D2 ≥ 171 MiB; the dump holds ≥ 400,000 `PackedLongValues$Builder` instances
(≥ 0.9 GiB) plus ≥ 150 slab regions. I at 2 GiB (256 MiB): no OOM, both builds complete (more segments). At 1 GiB heap B alone
OOMs. Expected largest failing heap: 2 GiB (BW), else 1.5 GiB (BW).

**Ladder (frozen; each step's runs are counted as repetitions of their condition when the condition is unchanged).**

- **S1 (calibration at 2 GiB):** B@2G, BW@2G, W@2G, one run each, in this order (no forced histograms except B0).
- **Branch (a)** — BW@2G OOM and B@2G no OOM: H* = 2 GiB, test = BW. Add BW ×2 (V1 n/3), B ×2 (V2, the build is the nearest
  component), I (BW, 256 MiB) ×3 (V4), W ×2 if time (component check, otherwise W 1/1 is reported as supporting).
  Then the upward search: BW@2.5G ×1 (if it OOMs, BW@3G ×1). Report the largest failing heap with n/N.
- **Branch (b)** — BW@2G no OOM: run B@1.5G and BW@1.5G (one each). If BW@1.5G OOMs and B@1.5G survives: branch (a) at
  1.5 GiB (I = 192 MiB), and BW@2G stays reported as the boundary (0/1, add 2 more BW@2G runs only if time remains after V1,
  V2, V4). If both OOM at 1.5 GiB: branch (c) at 1.5 GiB. If neither OOMs: run B@1G (one run) → branch (c) at 1 GiB.
- **Branch (c)** — the build alone OOMs at H (B@H OOM): test = B ×3 at H; control = BS ×3 at H (same build, schema, heap;
  data below the limit); intervention = B with H/8 ×3. Upward search: B at the next heap up the ladder (1.5 → 2 GiB) ×1.
  The direction is then convergence of D1 with the baseline (no second pool needed) — record it so.
- **Branch (d)** — B@1G does not OOM: stop the ladder; the readings decide (likely `retry`: the builder's live heap is
  below its counter, or the build does not reach the limit; check U vs K from the histograms).

**Outcome rows.**

| Observation | Meaning |
|---|---|
| test condition OOMs ≥ 3/3 (or n/3 stated), control 0/3, intervention 0/3, dump shows D1 ≈ 1 GiB (+ D2) | endpoint reached at defaults; candidate for `verified-OOM · deployment` (stage 2 checks V1–V7) |
| test OOMs but the dump's D1 U is far below 1 GiB (< 0.6 GiB) and something else dominates | OOM not attributed to the claimed holder: `retry` with the holder found |
| K_D1 reaches 1 GiB but heap post-GC stays < 80 % in BW at every heap down to 1.5 GiB and B@1G survives | U ≪ K or flush overlap smaller than predicted; `false positive` only if the ladder ran to 1 GiB and §2.4's sum was reached |
| GC service loss (≥ 90 % STW ≥ 60 s) without OOM | `verified-gap · service-loss` candidate → verdict `retry` |
| node exits with a direct-memory OOM | different endpoint; record, `retry` (direct limit H/2 is the claimed node's own) |
| K_D1 never reaches the limit in B | invalid run (workload); fix the data and rerun once |

**Stopping budget (time plan, America/New_York, 2026-11-18).** Stage 2 starts ≈ 08:45–09:00. Setup and seed ≤ 35 min
(by ≈ 09:30). S1 ≈ 20 min. Branch runs ≈ 6 min each; (a) needs ≈ 9 more runs (≈ 55 min) + 1–2 up-search runs; (b)/(c)
add ≈ 12–20 min, paid for by dropping the up-search and extra W runs. **No new run starts after 10:25; every process of this
case is stopped by 10:35; §3/§4 and write-backs are finished by 10:58.** Priority when time runs short: V1 test repetitions
> V2 control repetitions > V4 intervention runs > W component runs > upward search. No escalation after an OOM beyond the
ladder. Disk: each W/BW run writes ≤ ≈ 60 GB and is deleted at run end; keep ≥ 150 GiB free; hprof files (≈ H each) are
deleted after their histogram is saved, except one per failing condition.

### 2.8 Controls and intervention

- **Matched control (V2):** branch (a)/(b): B at H* (the SAI build alone, same data, heap, build and node state; ≥ 3 runs),
  plus W at H* (writes alone) as a component check; branch (c): BS at H* (same build on 200,000 terms, below the limit;
  ≥ 3 runs). Safe-alone margin target: control live peak ≤ 70 % of H (30 % margin); a control with a smaller margin is reported
  with its number.
- **Intervention (V4):** `sai_options.segment_write_buffer_size: <H/8>MiB` in the test arm, ≥ 3 runs: bounds D1 to a
  heap-proportional value (the "add a bound" intervention). Throughput record: both builds must complete (segments written,
  index queryable: `SELECT count(*) FROM c8.big WHERE v = '<a known value>'` returns 1), and stress op/s within 30 % of the test
  arm before its endpoint, so that the intervention is not "stopping useful work".
- **Repetitions:** every condition from a clean start (fresh instance from the seed). n/N and peak distributions reported.

`sha256 of §1–§2 at freeze: 48dded06c29ef0c050a3466eda0f406c6a7bbd0be52d3f85cbee1426bc22bf52` (computed as `awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <this file> | sha256sum`, i.e. from the `## 1. Candidate` line up to, not including, this line; 2026-11-18) · amendments after the freeze: none in stage 1; stage-2 amendments A1–A2 and deviations are in §3.4 (2026-11-18).

## 3. Runs (stage 2)

*Stage-2 OOM-agent session (workflow, fresh), 2026-11-18 08:10–10:15 America/New_York, pc96 only (local).* Freeze hash
checked before any run: `48dded06…bf52` recomputed with the command in §2's last line, **matches**.

Harness: [`harness/`](harness/) (`c8.py` orchestrator: setup, seed, run, queue; `C8Sampler.java` JMX sampler; `selfcheck.py`
outcome line per run; `oomtail.py` last-sample/build-start reader; `excerpts.sh` log excerpts; `hprofhist.py` and
`hprofstacks.py` copied from `cql-row-limit--wide-row-default-pages/harness/`). Full logs, gauges, GC logs and the three OOM
heap dumps stay on pc96 under `/mydata/s4/c8-w3/runs/<run>/`; excerpts per run in [`logs/`](logs/) (`logs/<run>.txt`,
`logs/summary-recomputed.txt`, `logs/queue.log`, seed listing).

### 3.1 Environment and configuration as run

- **Node:** pc96, Linux 5.15.0-198-generic, cgroup v2, 2 × Xeon E5-2667 v2 (32 logical CPUs), 125 GiB RAM, node swap 8 GiB
  (measured process in `systemd-run --user --scope -p MemorySwapMax=0`, no `MemoryMax`). Before the first start no
  `CassandraDaemon` ran on the node and ports 7008/9048/7208 were free; other sessions' directories `/mydata/s4/c4-w1`,
  `/mydata/s4/r7-w1` untouched. Load average 2–12 from other sessions during the runs.
- **Build:** `cp -a /mydata/s4/cassandra-base /mydata/s4/c8-w3/cassandra`; jar `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e` (identical to the base). No patches, agents or Byteman.
  OpenJDK 11.0.33, G1 with the shipped `jvm11-server.options` (`G1HeapRegionSize=16m`, `AlwaysPreTouch`); `cassandra-env.sh`
  set `ParallelGCThreads=32`, `ConcGCThreads=32`.
- **Budget as resolved (startup log / JVM arguments):** H = 2,048 MiB → `-Xms/-Xmx2048M`, `MaxDirectMemorySize=1024M`; H =
  1,536 MiB → `-Xmx1536M`, `MaxDirectMemorySize=768M` (the claimed node's ¼ RAM = H/2, §2.3). Memtable on-heap threshold
  512 / 384 MiB; key cache "capacity of 100 / 76 MiBs"; SAI limit gauge `SegmentBufferSpaceLimitBytes` 1,073,741,824 (192 MiB =
  201,326,592 in arm I). `memtable_allocation_type: heap_buffers`, `concurrent_index_builders` 2, `concurrent_writes` 32 (all
  shipped). Config diff per run = environment lines only (`logs/<run>.txt` "yaml.diff"), plus `sai_options` in arm I.
- **Seed (preparation, 08:14–08:24):** `c8.big` 2,000,000 rows loaded in 380 s, `c8.small` 200,000 rows (count checked), stress
  schema `keyspace1.standard1` (1,000 rows); flush + `compact` → one sstable each (`big` Data.db 92,297,862 B, 2,011,666
  partitions estimated; `small` 8,957,547 B), drain, copied to `/mydata/s4/c8-w3/seed` (133 MiB).
- **Run start:** 16–20 s to `statusbinary = running`; B0 (forced-GC histogram before the arm) **70 MiB** in every run.

### 3.2 Runs

Order as run (queue log in `logs/queue.log`). Endpoint from `launch.log`/`system.log`; "post-Full" = the largest heap
occupancy after a full GC (`gc.log`), STW = largest stop-the-world share in a 60 s window; K_D1 = SAI limiter gauge;
D1 U = `long[]` + `DeltaPackedLongValues$Builder` + `PackedInts$Reader[]` (live histogram for survivors, OOM dump for OOMs).

| # | Run | Arm (role) | H / direct | SAI limit | Load reached | Endpoint | Key readings |
|---|---|---|---|---|---|---|---|
| 1 | `s1-B-2048` | B (S1) | 2,048 / 1,024 | 1,024 | 2/2 builds (63 s + 52 s), 8 limiter flushes, query = 1 | none | K_D1 peak 1,024 MiB; live histogram at K_D1 ≥ 0.95 C: 1,153 MiB total, D1 U 984 MiB (434,043 builders); post-Full 1,376 MiB (67 %); 49 full GCs; STW 21 % |
| 2 | `s1-BW-2048` | BW (S1 test) | 2,048 / 1,024 | 1,024 | 18,597 op/s mean; 2/2 builds (175 s + 166 s) | none | post-Full **1,905 MiB (93 %)**; 323 full GCs; STW 52 %; writers blocked on memtable allocation 2,449× |
| 3 | `s1-W-2048` | W (S1) | 2,048 / 1,024 | — | 23,093 op/s for 300 s | none | post-Full 603 MiB; STW 4 %; histogram at t = 240 s 433 MiB |
| 4 | `b-B-1536` | B (branch b; then V2 control 1/3) | 1,536 / 768 | 1,024 | 2/2 builds (77 s + 68 s), query = 1 | none | post-Full 1,308 MiB (85 %); 118 full GCs; STW 40 %; live histogram 1,153 MiB, D1 U 984 MiB |
| 5 | `b-BW-1536` | BW (branch b; then V1 test 1/3) | 1,536 / 768 | 1,024 | 11,266 op/s; initial build in progress | **Java heap OOM** at arm + 273 s (build + 163 s) | K_D1 978 MiB at the last sample, 1 limiter flush done; post-Full 1,504 MiB; 398 full GCs; STW 99 %; dump: D1 U 984 MiB (425,578 builders), memtable 1 MiB regions 215 (216 MiB), key cache 872,097 entries (≈ 192 MiB) |
| 6 | `a-BW-1536-r2` | BW (V1 test 2/3) | 1,536 / 768 | 1,024 | 10,353 op/s; initial build in progress | **Java heap OOM** at arm + 305 s (build + 186 s) | K_D1 987 MiB; post-Full 1,504 MiB; STW ≈ 100 %; dump: D1 U 994 MiB (429,800 builders), 206 regions (207 MiB), key cache 876,421 entries; OOM thrown in `SlabAllocator.getRegion` (memtable write) |
| 7 | `a-B-1536-r2` | B (V2 control 2/3) | 1,536 / 768 | 1,024 | 2/2 builds, query = 1 | none | post-Full 1,309 MiB; STW 41 %; live histogram 1,178 MiB, D1 U 1,008 MiB; key cache K 76 MiB / 996,148 entries |
| 8 | `a-I-BW-1536-r1` | I-BW (V4 1/3) | 1,536 / 768 | **192** | 20,091 op/s; 2/2 builds (48 limiter flushes), query = 1 | none | K_D1 peak 192 MiB; post-Full 852 MiB (55 %); STW 32 %; live histogram at K_D1 ≥ 0.95 C 551 MiB, D1 U 191 MiB |
| 9 | `a-BW-1536-r3` | BW (V1 test 3/3) | 1,536 / 768 | 1,024 | 10,680 op/s; initial build in progress | **Java heap OOM** at arm + 245 s (build + 140 s) | K_D1 977 MiB; post-Full 1,503 MiB; STW 100 %; dump: D1 U 983 MiB (425,065 builders), 216 regions (217 MiB), key cache 871,052 entries (K = 69.2 MB, StatusLogger); OOM thrown in `SlabAllocator$Region.<init>` (memtable write) |
| 10 | `a-B-1536-r3` | B (V2 control 3/3) | 1,536 / 768 | 1,024 | 2/2 builds, query = 1 | none | post-Full 1,305 MiB; STW 41 %; live histogram 1,148 MiB, D1 U 977 MiB |
| 11 | `a-I-BW-1536-r2` | I-BW (V4 2/3) | 1,536 / 768 | **192** | 18,812 op/s; 2/2 builds, query = 1 | none | post-Full 852 MiB; STW 33 % |
| 12 | `a-I-BW-1536-r3` | I-BW (V4 3/3) | 1,536 / 768 | **192** | 19,432 op/s; 2/2 builds, query = 1 | none | post-Full 855 MiB; STW 36 % |
| 13 | `a-W-1536-r1` | W (component) | 1,536 / 768 | — | 23,827 op/s for 300 s | none | post-Full 484 MiB; STW 6 % |
| 14 | `a-BW-2048-r2` | BW (boundary 2/3) | 2,048 / 1,024 | 1,024 | 19,886 op/s; 2/2 builds, query = 1 | none | post-Full 1,911 MiB (93 %); 426 full GCs; STW 55 %; key cache K 100 MiB / 1,310,594 entries |
| 15 | `a-BW-2048-r3` | BW (boundary 3/3) | 2,048 / 1,024 | 1,024 | 20,069 op/s; 2/2 builds (218 s + 172 s), query = 1 | none | post-Full 1,901 MiB (93 %); 397 full GCs; STW 61 %; key cache K 100 MiB / 1,310,606 entries |
| 16 | `a-W-1536-r2` | W (component) | 1,536 / 768 | — | 23,004 op/s for 300 s | none | post-Full 482 MiB; STW 7 % |

**Per condition (n/N, clean starts):**

| Condition | H | n/N endpoint | Peak post-Full GC occupancy | Max STW / 60 s |
|---|---|---|---|---|
| BW (test) | 1,536 MiB | **3/3 Java heap OOM** (arm + 245 / 273 / 305 s) | 1,503–1,504 MiB (98 %) | 99–100 % |
| B (control: the build alone) | 1,536 MiB | 0/3 | 1,305–1,309 MiB (85 %) | 40–41 % |
| W (component: writes alone) | 1,536 MiB | 0/2 | 482–484 MiB (31 %) | 6–7 % |
| I-BW (intervention, SAI limit 192 MiB) | 1,536 MiB | 0/3, 2/2 builds each, query = 1 | 852–855 MiB (56 %) | 32–36 % |
| BW (boundary) | 2,048 MiB | 0/3 (both builds complete in each) | 1,901–1,911 MiB (93 %) | 52–61 % |
| B | 2,048 MiB | 0/1 | 1,376 MiB (67 %) | 21 % |
| W | 2,048 MiB | 0/1 | 603 MiB (29 %) | 4 % |

### 3.3 Readings per domain (U measured independently of K)

- **D1 SAI segment builder (claimed holder).** K_D1 rose to the limit and dropped at each limiter flush (8 cycles over two
  builds at 1,024 MiB, ≈ 48 at 192 MiB); flush lines `Global limit of 1.000GiB and minimum flush size of 1.000GiB exceeded.
  Current builder usage is 1.000GiB for 444924 cells` (≈ 2,413 B per distinct 32-character term). U from the three OOM dumps:
  `long[]` 919.5–929.5 MiB + `DeltaPackedLongValues$Builder` 30.8–31.2 MiB + `PackedInts$Reader[]` 32.4–32.8 MiB =
  **983–994 MiB** (425,065–429,800 builders), plus two `byte[]` ≥ 8 MiB (24 MiB, trie buffers); K_D1 at the last sample before
  each OOM 977–987 MiB. Survivor histograms at K_D1 ≥ 0.95 C: 977–1,008 MiB in B (K 977–992 MiB at the trigger), 170–191 MiB in I-BW (C 192 MiB). So **U ≈ K ≤ C** (no D1 bypass; the builder held
  its full contract when the heap ran out, on its second segment after one flush).
- **D2 memtable pool.** U from the dumps: 206–216 `byte[]` of 1 MiB (slab regions, 207–217 MiB) + ≈ 20 MiB of cells/rows;
  contract 384 MiB at H = 1,536 (**U ≤ C**). Writers blocked on allocation 1,329–1,486 times before the OOM. The sampled
  `AllMemtablesOnHeapDataSize` gauge (97–142 MiB) counts memtable data, not the pool's slab ownership, so it is reported
  but not used as K_D2. Two of the three OOMs were thrown in a memtable write allocating a new 1 MiB region
  (`SlabAllocator.getRegion` ← `MemtableBufferAllocator` ← `ByteBufferCloner.clone`); the third in an idle request-stage
  worker (`SEPWorker.doWaitSpin` → `ConcurrentSkipListMap.unlinkNode`). The builder thread was in
  `StorageAttachedIndexBuilder.indexSSTable` (`SSTableReader.getPosition`) in every dump.
- **D3 key cache (not in the frozen map as exercised; found in stage 2).** The SAI build reads every partition through
  `SSTableReader.getPosition`, which fills the key cache. In the OOM dumps: 871,052–876,421 entries;
  `ConcurrentHashMap$TreeNode` 62.5 + Caffeine `PSMW` 49.9 + `KeyCacheKey` 39.9 + `RowIndexEntry` 20.0 MiB shallow, plus the
  key `byte[]`s (≈ 20 MiB) ≈ **190 MiB held**, while the cache's own weighted size (StatusLogger at the OOM, gauge from run 7 on)
  was 69.2–70.1 MB of its 79.7 MB capacity: **U ≈ 2.5 × C with K ≤ C** (≈ 80 B counted per entry vs ≈ 225 B held; CP-1,
  the same shape as B7's weigher gap). In B and I-BW the cache reached its 76 MiB weighted cap with ≈ 996,000 entries.
- **Sum at the OOM (H = 1,536 MiB):** D1 ≈ 1,005 MiB + D2 ≈ 230 MiB + D3 ≈ 190 MiB + baseline/other ≈ 110 MiB ≈ the heap
  (dump shallow totals 1,559–1,560 MiB, an over-estimate by the 16-byte header approximation). GC log before each OOM:
  back-to-back `Pause Full (G1 Evacuation Pause) 1501M->1501M(1536M)` of 340–620 ms. In B alone D2 is absent (post-Full
  ≤ 1,309 MiB); with SAI = 192 MiB D1 drops by ≈ 830 MiB (post-Full ≤ 855 MiB).

### 3.4 Deviations from the design and amendments (dated 2026-11-18, stage 2)

- **A1 (environment):** run directory `/mydata/s4/c8-w3` instead of the design's `c8-w1` (the stage-2 task named this
  directory). The copied build is not a git checkout, so `git describe` could not be recorded; the jar sha256 is.
- **A2 (instrument added, from run 7 on):** key-cache gauges `type=Cache,scope=KeyCache,name=Size/Entries` appended to the
  sampler after the first OOM dump showed ≈ 872,000 key-cache entries (D3 above). For runs 1–6 the cache's weighted size is read from the
  `StatusLogger` lines in `system.log`, printed only after long GC pauses (so present for the BW runs, not for the B runs at
  2 GiB). No change to the workload or configuration.
- **Parser fixes (no reading changed):** the first `selfcheck.py` matched a `CompileCommand … OutOfMemoryError;)V` line as an OOM
  (run 1's original `summary.txt` line says `OOM:OutOfMemoryError;)V`; the node did not fail, both builds completed), looked
  for `PackedLongValues$Builder` (the class is `DeltaPackedLongValues$Builder`), and did not sort rotated GC files before the
  STW window (run 2's original line says 212 %). Fixed after runs 1–2; every outcome line was recomputed with the final
  parser (`logs/summary-recomputed.txt`; its `hprof=0` for runs 6 and 9 reflects the later dump deletion, see below);
  `summary.txt` on the node keeps the original lines.
- **Timing of B within BW:** the `CREATE INDEX` was issued at arm + 60 s as designed, but under the write load the statement
  itself took 35–58 s at 1.5 GiB (it flushes the base table first), so the build started at arm + 105–122 s (63–129 s at 2 GiB).
- **Ladder path:** S1 (runs 1–3) → branch (b): BW@2G did not OOM → B@1.5G (run 4, survived) and BW@1.5G (run 5, OOM) →
  branch (a) at H* = 1.5 GiB with I = 192 MiB (= H/8): BW ×2, B ×2, I ×3, W ×2, and BW@2G ×2 more (the design's "add 2 more
  BW@2G runs only if time remains after V1, V2, V4"). The 2.5 GiB step was not run (it belongs to branch (a) at 2 GiB only).
  Runs 4 and 5 count as repetitions of their conditions (frozen ladder rule).
- **Not done:** no histogram at the D1 peak in the test arm (by design); no key-cache intervention arm (not in the design);
  no bisection between 1.5 and 2 GiB (not in the ladder).

**Left on the node:** `/mydata/s4/c8-w3/` (build copy `cassandra/` 419 MiB, `seed/` 133 MiB, `runs/` with all logs, gauges, GC logs, histograms and
one OOM dump, `runs/b-BW-1536/cassandra-1795009351-pid4067936.hprof`, 1.76 GB; the dumps of runs 6 and 9 were deleted after their
histograms and stacks were saved, per §2.7: one dump kept per failing condition); `inst/` empty; 2.6 GiB in all. No process of this case
is running (checked: no `CassandraDaemon` or stress with `c8-w3` in its command line, no `c8-*` user scope).

## 4. Conclusion (stage 2)

- **Verdict:** **`true positive`** ([`oom-agent-playbook.md`](../../../oom-agent-playbook.md)).
- **Protocol status (detail):** `verified-OOM · deployment` (heap OOM), direction **convergence** (D1 and D2 each within their
  contracts), with a key-cache accounting overshoot (D3: U ≈ 2.5 × C, K ≤ C) adding ≈ 0.11 GiB above its cap; whether the
  OOM needs that overshoot was not isolated, so the label is *convergence (possibly mixed)*. Interpretation:
  configuration-sizing gap (a fixed 1 GiB default for a heap pool on a heap-scaled system).

| | Evidence | Met |
|---|---|---|
| V1 Repetition | BW at 1,536 MiB: Java heap OOM in 3/3 clean starts (runs 5, 6, 9) | yes |
| V2 Matched control | B (the build alone, same data, heap, build, node state) at 1,536 MiB: 0/3 (runs 4, 7, 10), post-Full ≤ 85 %; W (writes alone): 0/2 (runs 13, 16), post-Full ≤ 484 MiB | yes |
| V3 Measurement | D1 U 983–994 MiB from the dumps vs K_D1 977–987 MiB (≤ C 1,024); D2 207–217 MiB of regions (C 384); D3 ≈ 190 MiB held vs K 69–70 MB (C 76 MiB) | yes |
| V4 Intervention | `segment_write_buffer_size: 192MiB` (H/8) in the test arm: 0/3 OOM, both builds complete and the index answers in 3/3, stress 18.8–20.1 k op/s (test arm 10.4–11.3 k before its OOM) | yes |
| V5 Initiating failure | `java.lang.OutOfMemoryError: Java heap space` in `launch.log` (shipped `kill -9` on OOM, so no Cassandra ERROR line); throwing thread and stack from each dump (2/3 in a memtable region allocation); dump histograms show D1 ≈ 1 GiB, D2, D3; GC log shows the full-GC spiral at 1,500 MiB | yes |
| V6 Default constraints | `segment_write_buffer_size` 1,024 MiB, memtable H/4 (`heap_buffers`), key cache 5 % H, all shipped and unset in the yaml; only arm I changes the SAI limit | yes |
| V7 Acceptable budget | heap 1,536 MiB, direct 768 MiB (what `cassandra-env.sh` resolves on a 3 GiB node), no container limit; ≥ 512 MiB standing rule. Largest failing heap found: **1,536 MiB (3/3)**; at 2,048 MiB 0/3 (post-Full 93 %, STW ≤ 61 %), the boundary | yes |

- **Reason:** On a stock Cassandra 5.0.9 node with a 1.5 GiB heap (what `cassandra-env.sh` picks on a 3 GiB machine) and every
  capacity at its default, building one SAI index over an existing 2,000,000-row sstable while an unthrottled write load runs
  ended in a Java heap OOM in 3/3 runs (245–305 s after the writes started, 140–186 s into the build), while the same build
  alone (0/3, post-Full ≤ 1,309 MiB), the writes alone (0/2, post-Full ≤ 484 MiB) and the same build-plus-writes with the SAI limit at H/8
  = 192 MiB (0/3, post-Full ≤ 855 MiB, both builds done) did not. The dumps attribute the heap to the SAI segment builder at its
  contract (983–994 MiB live against a counter of 977–987 MiB and a fixed 1,024 MiB limit), memtable slab regions (207–217 MiB,
  within the 384 MiB pool) and the key cache that the build itself fills (≈ 190 MiB held while its weigher counts ≈ 70 MB of a
  76 MiB cap): each control is within its own limit or near it, but the fixed 1 GiB SAI default is two thirds of a 1.5 GiB heap and
  nothing reserves heap before a term is added. At 2 GiB the same workload did not OOM (0/3) but ran at 93 % post-GC
  occupancy with up to 55 % of wall time in GC pauses.
- **Limits of attribution:** the boundary lies between 1.5 and 2 GiB (not bisected); the key-cache overshoot's share was not
  isolated; one node, one index, 32-character distinct terms (shorter or repeated terms change bytes per term); the OC-24 row's
  internode reserves (its ≈ 3.4 GiB estimate) were not exercised.
