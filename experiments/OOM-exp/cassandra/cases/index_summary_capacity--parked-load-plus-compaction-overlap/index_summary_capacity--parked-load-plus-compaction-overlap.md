# R10 (retry of R5) — index_summary_capacity: parked full-sampling summaries plus the compaction replacement overlap  <!-- file: cassandra/cases/index_summary_capacity--parked-load-plus-compaction-overlap/index_summary_capacity--parked-load-plus-compaction-overlap.md -->

| Field | Value |
|---|---|
| Case ID | `R10` (a new attempt at retry row `R5`) |
| From | retry of `R5` ([phase-2 retry list](../../phase2-retry-list.md), row R5, status `picked again: R10`) |
| Phase-1 case file | [`index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) (E2 flag), [`index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md) (E1 / N19); R5's own: [`index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md), [`row_cache_size-create-serialized_size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/row_cache_size-create-serialized_size--autonomous.md) (dropped here, see §1) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` base.version 5.0.9); build on pc99 `/mydata/s4/cassandra-base`, jar sha256 `570b5249…0176e` (same jar as C4) |
| Stage 1 (design) | OOM agent, phase-2 stage 1 session (Claude Opus 5.5), 2026-11-20 10:30–11:30 EST |
| Stage 2 (verify) | OOM agent, fresh phase-2 stage 2 session (Claude Opus 5.5), 2026-11-20 10:54–13:45 EST (runs), interrupted by a usage limit ≈ 13:00, resumed and written up 21:30 EST |
| Verdict | **retry** (`candidate`; T 3/3 killed before the compaction, but K_Q 3/3 and I 3/3 killed too) |
| Ready for stage 2 | was no (V7 owner review); owner approved the container budget and choices (a)–(f) on 2026-11-20 before any run (§3) |

## Summary

- **Design (stage 1):** at shipped defaults (BIG format, `index_summary_capacity` auto = 5 % of heap, resize every
  60 min, STCS, `compaction_throughput` 64 MiB/s), a node first loads a set **P** of full-sampling sstables (a standing,
  uncapped summary pool parked until the next periodic run: the C4 shape, replacing R5's row cache, which is off by
  default), then a set **Q** of four equal sstables that the default background compaction merges at once. The merge
  builds the output's full-sampling summary (E2) while the inputs' summaries stay live and copies it once more when it
  trims the builder (replacement overlap). Each set alone survives; together they are predicted to be killed by the
  kernel memcg OOM-killer near the end of the compaction. Control: P alone, Q alone; intervention: one run of the
  shipped redistribution between P and Q (what the periodic task would have done).
- **Budget:** every byte of the claimed holder (index summaries, plus the compaction output's bloom filter and
  compression metadata) is JNA `malloc`, outside `-Xmx` and `MaxDirectMemorySize`. No heap or direct-memory budget can
  be reached by it, so no default-reachable heap-budget design exists for R5's direction; the only covering budget is a
  container limit (2,048 MiB, heap 1,024, direct 512, the budget the owner approved for C4). **Not ready for stage 2
  until the owner reviews V7 for this case.**
- **Conclusion (stage 2): retry** (`candidate`). At heap 1,024 / container 2,048 (owner-approved), defaults, the parked
  P load alone survived 3/3, but the test arm was killed 3/3 by the memcg OOM-killer **before its compaction started**
  (at the import of Q onto parked P), and the controls failed too: Q alone was killed 3/3 at the trim of its merge, and
  the intervention (P redistributed to the cap) 3/3 at the last builder resize. The container's usable headroom was
  ≈ 410–445 MiB over idle, not the ≈ 595 MiB modelled from C4, because 170.5 MiB of the JVM's mapped files stay charged to
  the scope. One step up (heap 1,280 / L 2,560) T was killed **in** the compaction with P parked (1/1); at 3,072 it
  survived. A retry should run the four arms at L 2,560 and calibrate the anon ceiling (L − mapped files).
- **Root cause (as measured):** `index_summary_capacity` is applied only by the periodic redistribution; summaries loaded
  or written in the window (import, compaction output) are malloc'd at full sampling with no byte check (K 316 MB vs a
  51 MB pool for the whole window), and a compaction holds its inputs' summaries, the growing output summary (one extra
  copy at each growth and at the trim), the output bloom filter and compression metadata at once, all outside heap and
  direct limits.

## 1. Candidate

**Retry row R5, quoted** ([`phase2-retry-list.md`](../../phase2-retry-list.md)):

> | [R5](cases/candidates/row_cache_size+index_summary_capacity--run6.md) | 2026-11-03 | `candidate (pre-protocol)`: schedule B (row cache 550 MiB `SerializingCacheProvider` parked, then a 1.5M-partition index-summary burst) → cgroup kill 1/1 at 1,973 of 2,000 MiB in the flush/compaction tail; alone 78 % / 80 %; schedule A 93 %, no kill; custom sizes, `-Xmx384M`, `min_index_interval=1`, resize 120 m. The R5 recheck (×3) was queued but never run (corroborated 2026-11-17 by two phase-1 flags, status unchanged) | Campaign row R5: schedule B ×3, R and I alone ×3, intervention ×3 by lowering `row_cache_size` (the 1-minute resize arm is not a clean intervention: its heap OOMed), per-pool readings at the kill, attribute arm C's heap OOM (dump kept on the node). Toward defaults: full-sampling summaries between periodic runs (E2 flag: ≈ 440 MB from one major compaction vs ≈ 409 MiB default cap at an 8 GiB heap) and untrimmed upsample buffers (N19, 1.729× counted); the row cache is off by default, so argue it or replace it with another standing pool (C4/B5 shape) | picked again: R10 (2026-11-20) |

**Earlier case and its verdict.** [`row_cache_size+index_summary_capacity--run6`](../candidates/row_cache_size+index_summary_capacity--run6.md)
(2026-11-03, `candidate (pre-protocol)`, mapped to **retry** on 2026-11-17): schedule B — row cache filled to a custom
550 MiB (`SerializingCacheProvider`, JNA malloc), then a 64-thread, 1.5 M-partition write burst into a table with
`min_index_interval=1` — was killed by the kernel memcg OOM-killer **1/1** at anon-rss 1,973 MiB of a 2,000 MiB cgroup
(`-Xmx384M`, `index_summary_resize_interval: 120m`), the killing allocation in `CompactionExecutor` during the burst's
flush/compaction tail. Alone: row cache 78 %, burst 80 %; concurrent schedule A peaked at 93 % with no kill. Arm C (resize
1 m) avoided the native kill but died of an unattributed **heap** OOM at `-Xmx384M`. V1, V2, V4 (one run each), V6
(custom `row_cache_size`, `index_summary_capacity` 100 MiB, `min_index_interval` 1, `memtable_heap_space` 220 MiB) and
V7 (384 MiB heap) are unmet. Runs 4 (not reached) and 5 (void) are superseded attempts in the same folder.

**Cases the row names.**
- **C4** ([`index_summary_capacity--full-sampling-load-window`](../index_summary_capacity--full-sampling-load-window/index_summary_capacity--full-sampling-load-window.md),
  2026-11-18, **true positive**, `verified-OOM · deployment`, kernel memcg kill): `nodetool import -q` of 90 M partitions
  (1,000-byte keys) in four full-sampling sstables (summaries 678.6 MiB vs a 51 MB pool) killed the JVM in a 2,048 MiB
  container (heap 1,024, direct 512) 3/3 at anon-rss 2,030 MiB; BCD (316.7 MiB) survived 3/3 at 87 %; the same files
  with summaries downsampled to the cap survived 3/3. Owner approved the container budget (V7) on 2026-11-17. Its
  readings give this design its baseline (idle RssAnon 1,425–1,444 MiB at heap 1,024 on pc96; kill at kernel anon-rss
  2,030–2,031 MiB at L 2,048), its generator (`GenSorted.java`), its staging rule, the importer's double open (each
  sstable's summary briefly live twice: T1 +376 MiB ≈ 2 × B's 193 MiB) and its per-partition sizes (`Summary.db`
  ⌈N/128⌉ × 1,012 B; `CompressionInfo.db` 0.503 B; `Data.db` 78.8 B; `Index.db` 1,008 B; `Filter.db` 16 B from
  `CQLSSTableWriter`).
- **B5** (C4/B5 shape): the old campaign row "C4/B5, mixed: replacement overlap / periodic index-summary enforcement"
  (`campaign-plan.md`, retired 2026-11-17; never run under its own ID; C4 took its periodic-enforcement half). This case
  takes the **replacement-overlap** half: old (input) and new (output) summaries of one compaction live together.
- **E2 flag** (phase-1 recheck of `adjustSamplingLevels-remainingSpace`, `campaign-plan.md` row R5/P2): the write path
  mallocs every summary at full sampling with no capacity check and only the periodic run shrinks it; ≈ 440 MB from one
  major compaction vs the ≈ 409 MiB cap at an 8 GiB heap.
- **N19** (lead N19 / OC-49, `_run-log.md` 2026-11-17): summaries rebuilt by upsampling keep an untrimmed
  `IndexSummaryBuilder` buffer, 1.729 × the counted size at stage 4 (allocated bytes, 32-byte keys). C4 §1 bounded it
  by C × 76/(K + 12) (≤ 485 MiB at a 2 GiB heap, 4-byte keys, needing ≈ 430 M partitions to fill even a 51 MiB pool).
  Source re-read for this design (`SafeMemoryWriter.java:47-66`, `Memory.java:65`, `MemoryUtil.java:81-84`): builder
  capacity is plain `malloc` that is **not zeroed**, and growth copies only the written bytes, so the untrimmed tail is
  address space, resident only where written. N19's 1.729 × is therefore an allocation figure, probably not RSS; it is
  **not a term of this design** (no upsample runs: no periodic run inside an arm). The writer-path analogue that does
  cost resident memory is the copy at each resize and at the final `trim()` (§2.1), which this design uses and stage 2
  measures (§2.6, smaps `Size` vs `Rss`).

**Why not the row cache.** `row_cache_size` defaults to 0 (`Config.java`, yaml `row_cache_size: 0MiB`), so any row-cache
arm fails V6. The default standing pools that do exist are either on-heap (key cache, counter cache, memtable heap,
prepared statements: pre-touched heap, so they add nothing to process memory and do not share a budget with summaries)
or direct (networking pool ≤ 128 MiB, chunk cache off by default). The standing pool that is on at defaults, native and
large is the summary pool itself between periodic runs: the C4 shape. It replaces the row cache here.

**Why no heap-budget design (the session's "toward defaults" request).** Index summaries, bloom filters
(`OffHeapBitSet`) and compression metadata are allocated by `Memory.allocate` → `MemoryUtil.allocate` →
`Native.malloc` (`MemoryUtil.java:81-84`): outside `-Xmx`, outside `MaxDirectMemorySize` (only `ByteBuffer.allocateDirect`
reservations count there) and invisible to NMT. Their heap-side objects (`IndexSummary` headers, first/last keys,
`ReadableBoundary` keys) are a few KiB per sstable. No heap or direct-memory limit can be exhausted by this holder at any
data volume; a heap OOM in this scenario would be another holder (as R5's arm C at `-Xmx384M`). The only budget that
covers R5's direction is process memory, i.e. a container (cgroup) limit, argued case by case (§2.3). So
`ready_for_stage2 = false` with an owner-review reason, as for C4 before its approval.

**Phase-1 constraint and check.** `index_summary_capacity` (`Config.java:539-540`; empty → `DatabaseDescriptor.java:866-869`:
5 % of `Runtime.totalMemory()`, 51 MB at `-Xmx1024m`, read back in C4), enforced only by the periodic redistribution
(`IndexSummaryManager.java:117-147`, first run one interval after start, `index_summary_resize_interval: 60m`;
`IndexSummaryRedistribution.java:103-154, 258`). Stage 4 (`adjustSamplingLevels`, cluster, 2026-10-21, `Confirmed —
caps only on some paths (bypass)`): 1,930 MiB of summaries stood under a 64 MiB cap until a run; `applySimpleConfig`
(2026-10-25, `Not confirmed — caps (counted size)`): after each run the counted size is ≤ C + 4 KiB.

**JIRA prior art** (read only; REST search on issues.apache.org 2026-11-20 ≈ 10:45 EST, plus
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`; nothing posted):

| Query | Hits | Relevant |
|---|---|---|
| `text ~ "\"index summary\"" AND text ~ compaction AND (off-heap OR offheap OR OOM OR oom-killer)` | 65 | **CASSANDRA-8552** "Large compactions run out of off-heap RAM" (Cannot Reproduce, 2.1); 8723 (RSS grows until OOM-kill, Cannot Reproduce); 12014 (summary > 2 GB assertion, Fixed) |
| `text ~ SafeMemoryWriter` | 16 | **8757** (IndexSummaryBuilder off-heap, share memory between `build()` calls: removed the per-early-open copy, Fixed 2.1.5); **14649** (builder over-allocation / > 2 GB, Fixed 4.0: writer path trims); 13785, 15084, 10592 (realloc errors) |
| `text ~ "nodetool import" AND (memory OR OOM)` | 47 | none about summaries or memory at import |
| keys 5519, 10821 | 2 | 5519 (pool + periodic resampling: the design, Fixed 2.1); 10821 (kernel OOM-killer during heavy compaction, Won't Fix; bloom filters / compression metadata unprotected) |
| survey CSV (`summar`, `off-heap`, `native`, `oom-killer`) | — | 2875 (Won't Fix, by design), 4303 (bloom filters as largest holder, Later), 8499 (writer leak on failure, Fixed), 10930 (cap off-heap memory, Unresolved), 13131 (service script vs OOM-killer, Unresolved) |

Verdict: periodic-only enforcement is **by design** (5519); native growth in large compactions was reported (8552,
Cannot Reproduce; 10821, Won't Fix) and the early-open copy was fixed (8757); the overlap of a parked uncapped load with
one compaction's input + output + trim copy as an OOM path at defaults is **new** (no report). Not a known-fixed bug, so
not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

All capacities at shipped values; BIG format (`storage_compatibility_mode: CASSANDRA_4`). Each BIG sstable's index
summary holds one entry per 128 partitions (key + 8-byte position) plus a 4-byte offset, in `Memory.allocate` (JNA
malloc). Summaries are loaded (`nodetool import`, restart) and written (flush, compaction, streaming) at full sampling;
`index_summary_capacity` is applied only by the redistribution task, every 60 min.

1. **Standing term P (C4 shape).** `nodetool import -q` of three full-sampling sstables P7, P12, P21 (40 M partitions,
   1,000-byte keys) adds their summaries (301.6 MiB) and compression metadata (19.2 MiB) to process memory, 5.9 × the
   51 MB pool, until the next periodic run (`SSTableImporter.java:157-238`; no redistribution is triggered). Sizes are
   chosen so no STCS bucket forms among them.
2. **Compaction term Q (E2 + replacement overlap, B5 shape).** A second `nodetool import -q` of four equal sstables
   Q1–Q4 (4 M partitions each) forms one STCS bucket at `min_threshold` 4. The importer adds them with
   `Tracker.addSSTables` (`SSTableImporter.java:230`), which submits nothing; the default backstop
   (`CassandraDaemon.java:435`: `submitBackground` for every table every 1 min, first 5 min after start) starts a
   background `COMPACTION` within ≤ 60 s. The writer (`BigTableWriter` `IndexWriter`) builds the output summary with
   `IndexSummaryBuilder(expectedKeys = 16 M)` (`IndexSummaryBuilder.java:97-128`): initial entry buffer 76 B × 125,000
   = 9.06 MiB, grown by `SafeMemoryWriter.resizeTo` (`SafeMemoryWriter.java:47-66`, ×2 up to 64 MiB, then ×1.5,
   `DataOutputBuffer.java:158-172`) to 18.1, 36.2, 72.5, 108.7, 163.1 MiB; **each growth allocates a new block and copies
   the written bytes before freeing the old one**, and `prepareToCommit()` (`IndexSummaryBuilder.java:246-251`, called
   from `BigTableWriter.java:320` before the transaction commits) `trim()`s by one more copy to the exact 120.6 MiB.
   Meanwhile the four input sstables (and their summaries) stay live until the commit (early-open readers share the
   input and builder memory: `IndexSummaryBuilder.build(…, boundary)` uses `sharedCopy()`, 8757). The output's bloom
   filter (`FilterFactory.getFilter(16 M, 0.01)`, 10 bits/key, zeroed at allocation → resident, 19.1 MiB; the inputs
   carry 16-byte filters) and compression metadata (7.7 MiB) are also malloc'd, with no control. Resident peak of the
   compaction near its end: inputs (120.6 + 7.7) + output bloom 19.1 + output compression metadata 7.7 + output summary
   written (120.6) + its trim copy (120.6) = **396.4 MiB**, i.e. 3.0 × the summaries of the merged data, for a few
   hundred ms; just before the trim 275.7 MiB; at the last resize (written 108.7 MiB) 372 MiB.
3. **Endpoint.** In a container sized as a node with RAM = 2 × heap, the pre-touched heap and the JVM's native
   baseline leave ≈ 595 MiB (C4: idle 1,425–1,444, kill at anon 2,030 of 2,048). P alone (320.8) and Q alone (396.4) fit;
   P + Q (717.2) does not: the kernel memcg OOM-killer ends the JVM in the last ≈ 10 % of the compaction (at the last
   builder resize or at the trim), while summaries are counted at 422 MiB against a 51 MB pool.

**Direction label (proposed; decided from readings in stage 2):** **mixed / combo** — convergence of two summary terms
within the documented periodic window, in one process budget: the standing parked load (U > C and K > C for the summary
pool during the window = unprotected accumulation in the documented periodic window, as C4) and the compaction's
replacement overlap (input + output + trim copy; bloom filter and compression metadata unprotected, no control).
Technique notes: [`combo-playbook.md`](../../../combo-playbook.md) (standing layer + growing layer, components alone,
remove one layer), [`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (defaults, feasibility first).

### 2.2 Protection map (fixed before the run)

| Domain | Allocation and owner | Local contract (counter K, limit C) | Scope / multiplicity | Lifetime | Budget covering it |
|---|---|---|---|---|---|
| Index summaries, loaded (P, Q inputs) | `IndexSummary` offsets + entries (JNA malloc), loaded from `Summary.db` at its saved level (`BigSSTableReaderLoadingBuilder.loadSummary`) | K = `IndexSummaries.MemoryPoolSizeInMB` / table gauge `IndexSummaryOffHeapMemoryUsed` (Σ `getOffHeapSize()` of tracked sstables); C = auto 5 % of heap (51 MB at 1,024, read back), applied only by the periodic run (soft, periodic) | per sstable; no bound between runs; the importer opens each sstable twice (in place, then after the move) and frees the first copy asynchronously | until release or next downsample | process / container only |
| Index summary, being written (compaction output) | `IndexSummaryBuilder` entries + offsets (`SafeMemoryWriter`, JNA malloc); resize and trim copies | not counted until early-open readers enter the tracker (counted at their boundary length); no check | one per running compaction (`concurrent_compactors` auto = 2 on pc99; one bucket → one task) | until commit (output) / until the copy completes (old block; early-open readers may keep it until the next early open, `sstable_preemptive_open_interval` 50 MiB) | container |
| Untrimmed builder tail (N19 analogue) | builder capacity beyond written bytes | none | per builder | until trim | **address space only** (not resident, unzeroed malloc); measured, not a term |
| Bloom filters | `OffHeapBitSet` (malloc, zeroed) — inputs 16 B each; output sized for 16 M keys | no control; gauge `BloomFilterOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Compression metadata | chunk offsets (malloc), from `CompressionInfo.db` / writer `SafeMemory` (×2 growth) | no control; gauge `CompressionMetadataOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Heap | Java heap, `-XX:+AlwaysPreTouch` | `-Xmx` 1,024 MiB | process | resident from start | container + `-Xmx` |
| Direct buffers | networking pool (auto), chunk-cache buffer pool (cache off; reader buffers) | `MaxDirectMemorySize` 512 MiB | process | standing | container + direct limit |
| JVM native baseline | metaspace, code cache, GC, stacks, glibc arenas | none | process | standing (+≈ 30 MiB `Arena Chunk` growth seen in C4) | container |
| Page cache | `Index.db` read through mmap (`disk_access_mode` auto = `mmap_index_only`), compaction writes of `Index.db`/`Data.db` (dirty, then written back) | none; reclaimable by the memcg (dirty pages after writeback) | per cgroup | reclaimable | counted in `memory.current` as `file`, not `anon` |

### 2.3 Configuration and budget audit

- **Build:** pc99 `/mydata/s4/cassandra-base` (5.0.9, unmodified, `ant jar` already done: jar sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, checked read-only 2026-11-20 10:38 EST, identical
  to C4's). Do not run `ant` there. Victim and helper run from copies: `rsync -a --exclude data --exclude logs
  /mydata/s4/cassandra-base/ /mydata/s4/r10/node/` and `/mydata/s4/r10/helper/`.
- **Node:** pc99 (`node4.jason92-326665`, UMass), x86_64, 32 cores, 125 GiB RAM, 8 GiB swap (kept at 0 for the
  victim), cgroup v2, kernel 5.15.0-203, OpenJDK 11.0.33, Ant 1.10.12; `/mydata` = LVM on **one rotational disk** (sda,
  765 GiB), 714 GiB free; idle (load 0.00, no `CassandraDaemon`) at the 10:38 check. Re-check before each phase
  (`ps -eo cmd | grep '[C]assandraDaemon'`, `ss -ltn`, `/proc/loadavg`, `df -h /mydata`) and record.
- **yaml (victim):** shipped `conf/cassandra.yaml` with **environment edits only** (the C4 set): `cluster_name: r10`,
  `listen_address`/`rpc_address`/`seeds` 127.0.0.1, `storage_port: 27050`, `native_transport_port: 29050`,
  `data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` under the arm folder.
  Every capacity setting stays shipped: `index_summary_capacity:` empty (auto), `index_summary_resize_interval: 60m`,
  `compaction_throughput: 64MiB/s`, `concurrent_compactors` unset (auto), `sstable_preemptive_open_interval: 50MiB`,
  `memtable_allocation_type: heap_buffers`, `file_cache_enabled` unset (false), `networking_cache_size` unset,
  `disk_access_mode` unset, `row_cache_size: 0MiB`, `key_cache_size` / `counter_cache_size` auto. Save the diff per arm;
  fail the arm if any non-environment line differs.
- **Table:** `CREATE KEYSPACE r10 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE r10.isx (pk text PRIMARY KEY, v int);` — all table options default (STCS `min_threshold` 4,
  `bucket_low` 0.5, `bucket_high` 1.5, `min_sstable_size` 50 MiB; `min_index_interval` 128, `max_index_interval` 2048,
  `bloom_filter_fp_chance` 0.01, LZ4 16 KiB chunks). The generator's table statement uses the same keyspace/table name.
- **JVM (victim):** `MAX_HEAP_SIZE=1024M`, `MAX_DIRECT_MEMORY_SIZE=512M` (`cassandra-env.sh` `calculate_heap_sizes` for
  RAM 2,048 MiB: ½ and ¼), `HEAP_NEWSIZE` unset, G1 (shipped `jvm11-server.options`), `-XX:+AlwaysPreTouch` (shipped),
  `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:ParallelGCThreads=16 -XX:ConcGCThreads=16
  -Dcassandra.jmx.local.port=27199"` (C4 amendment 1: `cassandra-env.sh:235` ignores an exported `JMX_PORT`),
  `taskset -c 0,2,…,30`. Helper: heap 4 GiB, no container, ports 27051/29051/27198, odd CPUs.
- **Resolved values to read back per arm** (system.log, `/proc/<pid>/cmdline`): heap 1,024, direct 512, "memory pool
  size of N MB" (expect 51), resize interval 60 min, `compaction_throughput` 64 MiB/s, concurrent compactors (expect 2),
  preemptive open 50 MiB, networking pool limit.
- **Budgets.** Heap 1,024 MiB and direct 512 MiB (≥ 512 MiB: V7 standing rule met, but they **do not cover the claimed
  holder**, §1). **Container** `memory.max` = **2,048 MiB** with `memory.swap.max` = 0 (`systemd-run --user --scope -p
  MemoryMax=2048M -p MemorySwapMax=0`): the claimed node has 2 GiB RAM, heap ½ of it as `cassandra-env.sh` resolves. This
  is the only budget covering the claimed memory, so **V7 needs the owner's case-by-case review** (standing rule covers
  heap and direct only). Precedents: C4 (2,048 / heap 1,024, approved 2026-11-17 23:05 EST, `verified-OOM · deployment`),
  R1-V family A (L = 2 × heap, accepted 2026-11-12). Budget search upward: one T run at heap 1,280 / L 2,560 (direct 640,
  claimed 2.5 GiB node); if that is killed, one at 1,536 / 3,072 (§2.5 phase 4).
- **Supporting choices for the owner to accept** (not capacity settings): (a) 1,000-byte partition keys with a shared
  988-byte prefix (as C4); (b) ≈ 61 GB of sstables (56 M partitions) on a 2 GiB node; (c) `nodetool import -q` (as C4);
  (d) sstables written offline by `CQLSSTableWriter` (as C4; 16-byte `Filter.db`, `nb` version via
  `toolInitialization`); (e) the four Q sstables arrive in one import (a restore or bulk load of four similar files,
  which STCS merges at once); (f) in the **intervention arm only**, one JMX call of the shipped
  `IndexSummaryManager.redistributeSummaries()` between the two imports (what the periodic task does every 60 min;
  `nodetool` has no command for it).

### 2.4 Ceiling arithmetic

Per partition (1,000-byte keys, from C4's files): summary 1,012/128 = 7.906 B; compression metadata 0.503 B; output
bloom filter 1.25 B (10 bits); `Index.db` 1,008 B; `Data.db` 78.8 B.

| Sstable | Keys `[lo, hi)` | Partitions | Summary (MiB) | Compr. meta (MiB) | `Data.db` (MB, STCS size) | `Index.db` (GB) |
|---|---|---|---|---|---|---|
| Q1–Q4 | 0–4 M, 4–8 M, 8–12 M, 12–16 M | 4 M each | 30.16 each, 120.64 | 1.92 each, 7.68 | ≈ 315 each | 4.03 each |
| P7 | 16 M–23 M | 7 M | 52.78 | 3.36 | ≈ 551 | 7.06 |
| P12 | 23 M–35 M | 12 M | 90.48 | 5.76 | ≈ 945 | 12.10 |
| P21 | 35 M–56 M | 21 M | 158.34 | 10.08 | ≈ 1,654 | 21.17 |

STCS buckets (ascending size, join if size < 1.5 × bucket average): {Q1–Q4} avg 315 → P7 551 > 473 → new; P12 945 >
827 → new; P21 1,654 > 1,418 → new. Only {Q1–Q4} reaches `min_threshold` 4 (margins 14–17 % on size). P never compacts.

| Term (resident, MiB) | P alone (K_P) | Q alone (K_Q) | T = P + Q | I = P redistributed + Q |
|---|---|---|---|---|
| P summaries + compr. meta | 320.8 | — | 320.8 | ≤ 51 + 19.2 = 70.2 |
| P import transient (one extra copy of P21's summary, C4 amendment 5) | ≤ +158.3 | — | ≤ +158.3 (before Q) | ≤ +158.3 (before the redistribution) |
| Q inputs: summaries + compr. meta | — | 128.3 | 128.3 | 128.3 |
| Output bloom + compr. meta | — | 26.8 | 26.8 | 26.8 |
| Output summary written + trim copy (end) | — | 241.3 | 241.3 | 241.3 |
| **Peak Δ over idle** | 320.8 (worst 479.1 at import) | **396.4** (275.7 before the trim) | **717.2** (692.6 at the last resize) | **466.6** |
| **Peak RssAnon at idle 1,437** (% of 2,048) | 1,758 (85.8 %); worst 1,916 (93.6 %) | 1,833 (89.5 %) | **2,154 (105 %) → kill at ≈ 2,030** | 1,904 (93.0 %) |

**Feasibility at defaults.** Σ contract capacities if the cap held (summary pool ≤ 51 MB at all times): idle 1,437 + 51 +
bloom/compression of everything (19.2 + 7.7 + 26.8) + the in-flight output summary bounded only by the merge (241.3) ≈
1,783 MiB = 87 % of L: the endpoint is impossible if the pool were enforced continuously. As loaded and compacted (no run
in the window): 2,154 MiB = 105 %. **Error bounds:** idle ± 60 MiB (pc99 not yet measured; C4 pc96 spread 1,425–1,444);
summaries exact to the file header; compression metadata ± 5 %; bloom ± 5 %; Arena-chunk growth +30 MiB (C4). Worst
low for T (idle 1,377): 2,094 > 2,030 (margin 64); worst high for K_Q (idle 1,497 + 30): 1,923 (margin 107); K_P worst
(idle 1,497 + import transient + 30): 2,006 (margin 24 — only if the full one-copy transient happens; C4's K arms
showed VmHWM = VmRSS, i.e. no transient, in 3/3); I worst high: 1,994 (margin 36). The calibration rule in §2.5 keeps
the margins if pc99's idle differs.

### 2.5 Workload and environment

**Paths:** everything under `/mydata/s4/r10/` (`node/`, `helper/`, `gen/`, `data/pristine/{Q1,Q2,Q3,Q4,P7,P12,P21}/`,
`stage_node/<set>` (fixed staging paths, C4 amendment 5), `arms/<arm>/`, `logs/`). Nothing else on pc99 is touched.
Harness copies in `harness/` of this folder; small excerpts in `logs/<arm>/`.

**Phase 0 — checks and harness (≈ 20 min).** Node checks (§2.3); rsync the node copies; copy C4's harness
(`../index_summary_capacity--full-sampling-load-window/harness/`: `GenSorted.java`, `gen.sh`, `sampler.sh`, `arm.sh`,
`ISSampler.java`, `export.sh`, `analyze.py`) into `harness/` and adapt (keyspace `r10`, ports, paths; new steps below).
New `smaps.sh <pid> <csv>`: every 1 s, from `/proc/<pid>/smaps`, every anonymous mapping ≥ 8 MiB with its `Size` and
`Rss` (epoch ms, start address, size kB, rss kB) — the malloc'd summary, bloom and builder blocks are such mappings, so
this is a per-holder U independent of K. Install scripts with copy + `mv` (never edit a running script).

**Phase 1 — dataset (≈ 20 min; not a reading).** `GenSorted <outdir> <lo> <hi>` as C4 (key i = 988-char `Random(49)`
prefix + `%012d`, Murmur3-sorted, `CQLSSTableWriter.sorted()`, `toolInitialization()` from the shipped yaml, `nb`
files), table statement `CREATE TABLE r10.isx (pk text PRIMARY KEY, v int)`, generator `-Xmx8g`. Round 1: P21, P12,
P7 in parallel (taskset odd CPUs); round 2: Q1–Q4 in parallel. **Cutoff:** if round 1 has not finished by phase start +
30 min, stop and record blocked-by-time for the dataset (no rescaling: the sizes carry the STCS and margin arithmetic).
Checks per sstable: one `-big-Data.db`; `Summary.db` = ⌈N/128⌉ × 1,012 + header ± 0.1 %; `Filter.db` 16 B;
`CompressionInfo.db` and `Data.db` sizes (STCS margins of §2.4 must hold: each P `Data.db` ≥ 1.6 × the Q mean and P
sizes ≥ 1.6 × each other; else record and stop); `tools/bin/sstablemetadata` "Estimated cardinality" (or the
`Statistics.db` compaction metadata) present and within ± 3 % of N for Q1–Q4 (it sets the builder's `expectedKeys`).
`chmod a-w` the pristine files.

**Phase 1b — helper checks (≈ 15 min; not readings).** Helper (heap 4 GiB, no container): (i) default (verifying)
`nodetool import` of Q1 → rc 0, tablestats summary bytes = Q1's `Summary.db` − header (exact). Drop. (ii) Q-compaction
check: `import -q` Q1–Q4 at uptime ≥ 4.5 min, confirm a background `COMPACTION` of exactly these four starts at the
next backstop tick ("Compacting (…)" in debug.log, `nodetool compactionstats`), time it (**D_q**), and confirm the output
`Summary.db` = 126,500,000 B + header and the builder growth steps in `smaps.sh` (expect blocks of 9.06 → 163.1 MiB
`Size`, `Rss` ≈ written). Stop; drop its data.

**Per-arm staging.** As C4: `cp -al data/pristine/X stage_node/X`, then real copies (`cp --remove-destination`) of
`*-Summary.db` and `*-Statistics.db`; all else hardlinks. After the arm: `rm -rf stage_node/* arms/<arm>/{data,commitlog,saved_caches,hints}`
(compaction outputs and `tmp`/`tmplink` files included). Before each arm: `sync; sudo -n sh -c 'echo 3 >
/proc/sys/vm/drop_caches'` (pc99 is assigned to this case; record if another experiment runs there and then skip it).

**Arm procedure** (`harness/arm.sh <arm> <heap> <L> <P|-> <Q|-> <redistribute 0|1>`):
1. Pre-checks (ports 27050/29050/27199 free, no other victim daemon); record load, free memory, disk.
2. Start in a fresh scope: `systemd-run --user --scope --unit=r10-<arm>-<epoch> -p MemoryMax=<L>M -p MemorySwapMax=0
   -- taskset -c 0,2,…,30 node/bin/cassandra -f` (launched with `setsid nohup`); t0 = start epoch. Samplers start when
   the PID exists: `sampler.sh` (0.2 s), `smaps.sh` (1 s), `nodetool compactionstats` every 5 s. Wait for CQL (≤ 180 s,
   else invalid). Read back §2.3 values.
3. Create keyspace and table (cqlsh retries as C4 amendment 3). Idle 60 s; I0 = median RssAnon of the last 30 s;
   tablestats, ISSampler (`IndexSummaries` attributes), NMT summary.
4. If P: at t0 + 150 s, `nodetool -p 27199 import -q r10 isx stage_node/P7 stage_node/P12 stage_node/P21`; record rc and
   time; wait 30 s; tablestats + ISSampler.
5. If redistribute (I only): at t0 + 210 s, ISSampler `invoke` `redistributeSummaries` (as C4 phase 3), record the
   "Completed resizing" line, pool used after (≤ C); wait 20 s.
6. If Q: at t0 + 270 s (uptime ≥ 4.5 min), `nodetool -p 27199 import -q r10 isx stage_node/Q1 … stage_node/Q4`; record
   rc. The default backstop starts the compaction at its next tick (≈ t0 + 300–360 s). **No manual trigger.** If no
   "Compacting" line by t0 + 480 s → invalid arm (record; may be repeated once).
7. Observe until the compaction finishes (+ 120 s) or the JVM is gone; with no Q, observe until t0 + 300 s + D_q + 120 s
   (same length as a Q arm). tablestats, ISSampler and NMT at +10 s and +120 s after the end.
8. Stop (`nodetool stopdaemon`, ≤ 60 s, then kill by PID); check the scope is gone; save `memory.events`, kernel OOM
   block (`sudo -n dmesg`, block naming `r10-<arm>`), system/debug log excerpts (`Loading new SSTables`, `Done loading`,
   `Initializing index summary manager`, `Compacting`, `Compacted`, `Redistributing`/`Completed resizing`, ERROR), GC log.
9. Clean (staging rule). **Hard limit per arm: 25 min**; past it, stop the arm and record it as over time.

**Phase 2 — calibration Z (≈ 6 min; not a mechanism reading).** One arm with no P and no Q at 1,024 / 2,048: I0_Z.
Pre-declared rule: if I0_Z ∈ [1,377, 1,497] MiB, the test condition is heap 1,024 / L 2,048. Otherwise keep heap 1,024 and
direct 512 and set **L = 2,048 + (I0_Z − 1,437) rounded to 64 MiB** (keeps the headroom of §2.4), recorded as a dated
note before any verdict arm; the owner's V7 review applies to that L.

**Phase 3 — verdict arms (readings), interleaved T, K_P, K_Q, I ×3** at the test condition:
- **T** (test ×3): P then Q, no redistribution.
- **K_P** (control ×3): P only (same timeline and observation length).
- **K_Q** (control ×3): Q only (same timeline).
- **I** (intervention ×3): P, one redistribution, then Q.

**Phase 4 — budget search upward (single runs).** `U1` = T at heap 1,280 / L 2,560 (direct 640; predicted idle ≈ 1,701 +
717 = 2,418, 94 % → survives: boundary). If U1 is killed, `U2` = T at 1,536 / 3,072 (≈ 1,977 + 717 = 2,694, 88 %).
Report the largest failing L with its n/N.

### 2.6 Instruments

- **Process / cgroup (0.2 s):** C4's `sampler.sh`: RssAnon, VmRSS, RssFile; cgroup `memory.current`, `memory.stat`
  `anon`/`file`, `memory.events` `max`/`oom`/`oom_kill`. U for the process = RssAnon / cgroup `anon` (JNA malloc is
  anonymous).
- **Per holder, independent of K:** (a) `smaps.sh` (1 s): the large anonymous mappings — P summaries appear as blocks of
  `Size` 52.8 / 90.5 / 158.3 MiB (+ offsets 4 B × entries), Q input summaries 30.2 MiB each, output bloom 19.1 MiB, the
  output builder block stepping 9.06 → 163.1 MiB with `Rss` = written bytes, and the trim block 120.6 MiB; (b) Σ file
  sizes (`Summary.db`, `CompressionInfo.db`) of the loaded sets; (c) ΔU(T) − ΔU(I) against Σ P `Summary.db` minus the
  pool after redistribution; (d) `nodetool compactionstats` progress (bytes of total) to place the peak in the merge.
- **Counters K:** `IndexSummaries` `MemoryPoolSizeInMB`, `MemoryPoolCapacityInMB` (ISSampler); tablestats "Index summary
  / Bloom filter / Compression metadata off heap memory used", "SSTable count" (after each import, after the compaction).
- **JVM-internal native:** NMT summary at idle and +120 s (Arena growth ≈ 30 MiB expected; ΔRssAnon beyond it is outside
  NMT).
- **Heap:** GC log (shipped `-Xlog:gc`); no heap OOM expected; heap committed = `-Xmx` (pre-touch).
- **Initiating failure (V5):** kernel block "invoked oom-killer … CONSTRAINT_MEMCG … oom_memcg=…r10-<arm>… Killed
  process <pid> (java) … anon-rss:…", the invoking thread (expected `CompactionExecutor`), `memory.events oom_kill` 1,
  the last sampler/smaps rows, and the last `compactionstats` progress. No heap dump (no heap holder claimed); the smaps
  rows at the kill are the holder snapshot.

### 2.7 Predicted response and stopping budget

| Arm (1,024 / 2,048, pool 51 MB) | Predicted peak Δ (MiB) | Predicted peak RssAnon | Endpoint | K (summary pool) |
|---|---|---|---|---|
| Z | 0 | I0 ≈ 1,437 ± 60 | none | 0 |
| K_P | 320.8 standing (≤ 479 transient at import) | ≈ 1,758 (86 %) | none, 0/3 | 301.6 MiB > C for the whole arm |
| K_Q | 396.4 at the trim; 128.3 + 26.8 + 120.6 = 275.7 standing just before; 148.0 after commit | ≈ 1,833 (89.5 %) | none, 0/3; compaction completes (1 output sstable, `Summary.db` 126.5 MB) | 120.6 MiB > C before and after the merge |
| **T** | 717.2 (692.6 at the last resize) | ≈ 2,154 (105 %) | **memcg OOM-kill 3/3** in the last ≈ 10 % of the compaction (`compactionstats` ≥ 85 %), invoking thread `CompactionExecutor`; P import survives (≤ 1,916) | 422.2 MiB > C at the kill |
| I | 466.6 | ≈ 1,904 (93 %) | none, 0/3; compaction completes | ≤ 51 after redistribution, then 171.6 → 171.6 after the merge |
| U1 (1,280 / 2,560) | 717.2 | ≈ 2,418 (94 %) | none (boundary) | — |

Also predicted: no `Redistributing` line in any arm except the I call (first periodic run 60 min after start); ΔU
standing after each import = Σ (`Summary.db` + `CompressionInfo.db`) ± 5 %; the builder blocks in smaps show `Rss` ≈
written bytes, not capacity (N19's tail not resident); D_q ≈ 3–8 min on pc99's single disk (Q `Data.db` 1.26 GB at the
64 MiB/s throttle ≈ 20 s; `Index.db` 16 GB read + 16 GB written).

**What each outcome means (for §4):** T 3/3 killed, K_P 0/3, K_Q 0/3, I 0/3, smaps holder blocks matching §2.4 → true
positive candidate (if the owner accepts the container budget). T survives with the full merge done and ΔU ≈ prediction
→ the margin model is wrong: retry with a larger Q (no in-place redesign). A kill in K_Q or I → the compaction term is
larger than modelled (e.g. page-cache reclaim failure: check the kernel record's `anon-rss` vs `file-rss`): retry. A kill
in T before the Q import → the import transient, not the mechanism: invalid for the claim. Heap OOM anywhere → record
the thread and stack; not this mechanism.

**Stopping budget:** each arm ≤ 25 min; each invalid arm repeated at most once; no escalation after the kills (no larger
sets, no smaller L than phase 2's rule, no raised capacities). Stage 2 stops starting arms at **16:30 EST** and ends
(processes stopped, write-up done) by **17:30 EST 2026-11-20**.

### 2.8 Controls and intervention

- **Matched controls (V2), ×3 each:** K_P (the standing layer alone) and K_Q (the compaction layer alone), same build,
  budget, keys, staging, timeline and observation length. Together they show each term is safe alone and the endpoint
  needs both at once (convergence).
- **Causal intervention (V4), ×3:** I = T plus one run of the shipped redistribution between the two imports (unmodified
  build; the action the periodic task performs every 60 min). It downsamples P to the pool (≤ 51 MB) and leaves Q and
  the compaction identical. If the kill disappears, the cause is the parked summaries' excess over the cap during the
  window. Throughput check: the Q compaction must complete in I (rc 0, one output sstable, same output `Summary.db`
  size as K_Q).
- **Repetitions:** every verdict arm from a clean start (fresh scope, fresh data directories, fresh staging, dropped page
  cache).

### 2.9 Time plan (stage 2 from S ≈ 12:00 EST)

| Step | Duration | Ends at (S = 12:00) |
|---|---|---|
| Phase 0: checks, node copies, harness | 20 min | 12:20 |
| Phase 1: dataset (2 rounds) and checks | 25 min | 12:45 |
| Phase 1b: helper checks (import, Q-compaction timing D_q) | 15 min | 13:00 |
| Phase 2: Z | 6 min | 13:06 |
| Phase 3: 12 verdict arms: 9 with Q (≈ 5 min to the tick + D_q + 2 min observe + 2 min stop/clean ≈ 15 min with D_q ≈ 6) + 3 K_P (same length, ≈ 15) | ≈ 180 min | 16:06 |
| Phase 4: U1 (and U2 only if U1 killed and before 16:30) | 15–30 min | 16:21–16:36 |
| Process check, cleanup, §3–§4, write-backs | 40 min | ≤ 17:15 |

**Cut rules (pre-declared):** if D_q (phase 1b) > 10 min, skip phase 4 and shorten K_P's observation to end at the
same uptime as the median Q arm; if phase 3 cannot finish by 16:30 at the measured pace, finish complete triples in the
order T, K_Q, I, K_P and record the missing runs. Resources at peak: victim ≤ 2.5 GiB (container), helper ≤ 6 GiB,
three generators ≤ 27 GiB (never during a measured arm), ≈ 61 GB pristine + ≤ 18 GB per arm (compaction output, deleted
after) on `/mydata` (714 GiB free). Left on pc99 at the end: the pristine dataset under `/mydata/s4/r10/data/` (until the
owner accepts the results), no process, no scope.

### 2.10 Owner review needed before stage 2

**ready_for_stage2 = false.** Reason: the budget that covers the claimed holder is a **container (cgroup) limit**
(2,048 MiB, heap 1,024 / direct 512, or the L set by the phase-2 calibration rule), because index summaries, bloom
filters and compression metadata are JNA malloc outside the heap and the direct limit; a heap- or direct-budget design
for R5's direction cannot exist (§1). The owner approved the same budget shape for C4 (2026-11-17); this case needs its
own V7 review of the container budget and of supporting choices (a)–(f) of §2.3, notably (e) four similar sstables
imported at once and (f) the JMX redistribution in the intervention arm only.

`sha256 of §1–§2 at freeze: 0cac19a68a12bfae87224245b07f53b9948f5fab65cd4f6ca389d307c81cafea` (bytes from the line `## 1. Candidate` up to, not including, this line) · amendments after the freeze: none.

## 3. Runs (stage 2)

**Owner ruling (Jingsong, 2026-11-20, before any run; relayed to the stage-2 session at ≈ 10:54 EST).** The design's
container budget is approved for V7: container 2,048 MiB, heap 1,024 MiB, direct 512 MiB (C4's shape), with the design's
calibration rule for the container size (§2.5 phase 2), and its supporting choices (a)–(f) of §2.3, including (e) the four
similar-sized sstables arriving in one import and (f) the JMX `redistributeSummaries` call in the intervention arm only.

**Stage-2 start (2026-11-20 10:54 EST).** Freeze hash re-computed over §1–§2 (bytes from `## 1. Candidate` up to the
`sha256` line): `0cac19a6…c81cafea`, matches. pc99 at 10:55: no `CassandraDaemon`, no Java, load 0.00, 126 GiB free,
714 GiB free on `/mydata`, `sda` rotational, kernel 5.15.0-203, OpenJDK 11.0.33, base jar sha256 `570b5249…0176e`
(matches §2.3). Stage 2 started ≈ 1 h before the design's S = 12:00; the time plan's durations and cut rules are kept,
with 16:30 as the last arm start and 17:30 as the hard end.

**Amendments after the freeze:** none. The design ran as written. Harness details that the design leaves open (not
design changes, fixed before the readings they touch): generators pinned to the odd CPUs 1–31 with one
`cassandra.storagedir` per generator; the helper on CPUs 1,3,…,15; the samplers (`sampler.sh` 0.2 s, `smaps.sh` 1 s) and the
5 s `nodetool compactionstats` loop on CPUs 17,19,…,31 (off the victim's even CPUs); light snapshots (tablestats +
`ISSampler attrs`, no `jcmd`) 30 s after the P import (`postP`) and 20 s after the redistribution (`postR`); NMT only at
idle, +10 s and +120 s; helper check (i) imports Q1 at t0 + 100 s and does not wait for a compaction (no reading). Node
clock: the node's local time (in `summary.txt`) is EST − 2 h; epochs are UTC.

**Environment (as run).** pc99 (`node4.jason92-326665`), x86_64, 32 cores, 125 GiB, 8 GiB swap (0 for the victim:
`memory.swap.max` 0 read back), cgroup v2, kernel 5.15.0-203-generic, OpenJDK 11.0.33, `/mydata` on the rotational `sda`.
Build: `/mydata/s4/cassandra-base` (5.0.9, unmodified, jar sha256 `570b5249…0176e`), rsynced to `/mydata/s4/r10/node/`
(victim) and `/mydata/s4/r10/helper/`; no `ant` run. yaml: shipped `conf/cassandra.yaml` + 11 environment lines (cluster
name, addresses, ports 27050/29050, directories under the arm); every arm's `cassandra.yaml.diff` was checked by
`arm.sh` (no non-environment line). Victim JVM (`jvm-args-excerpt.txt`): `-Xms1024M -Xmx1024M
-XX:MaxDirectMemorySize=512M` (resolved: 512 MiB, set by `MAX_DIRECT_MEMORY_SIZE` = L/4), G1, `-XX:+AlwaysPreTouch`,
NMT summary, 16 GC threads (the later `JVM_EXTRA_OPTS` flag wins over `cassandra-env.sh`'s 32), JMX 27199, `taskset`
even CPUs 0–30. Read back from system.log and nodetool per arm: "memory pool size of **51 MB** and a resize interval of
**60 minutes**", `index_summary_capacity=null`, `compaction_throughput=64MiB/s`, concurrent compactors **2**,
`sstable_preemptive_open_interval=50MiB`, `disk_access_mode=mmap_index_only` (auto), `file_cache_enabled=false`,
`memtable_allocation_type=heap_buffers`, `storage_compatibility_mode=CASSANDRA_4`, networking "Global buffer pool limit
is 256.000MiB". Container: `systemd-run --user --scope -p MemoryMax=2048M -p MemorySwapMax=0`, `memory.max` 2147483648
read back. Full run data: `/mydata/s4/r10/` on pc99 (`arms/<arm>/` with `summary.txt`, `sampler.csv`, `smaps.csv`,
`cstats.txt`, `logs/`, `dmesg-block.txt`; `logs/batch-*.log`); excerpts in [`logs/`](logs/), harness in [`harness/`](harness/).

**Phase 1 — dataset (10:55–11:02 EST).** `GenSorted` (C4's, keyspace `r10`), round 1 P21/P12/P7 in parallel (10:55:46 →
11:00:13), round 2 Q1–Q4 in parallel (11:00:13 → 11:02:23); well inside the 30 min cutoff. Checks
([`logs/checkdata.csv`](logs/checkdata.csv), [`logs/pristine-listing.txt`](logs/pristine-listing.txt)):

| Set | N | `Data.db` (B) | `Summary.db` (B) vs ⌈N/128⌉×1,012 | `Filter.db` | `CompressionInfo.db` (B) | `Index.db` (B) | Est. cardinality (dev.) |
|---|---|---|---|---|---|---|---|
| Q1–Q4 | 4 M each | 314.70 / 314.76 / 316.59 / 314.76 M | 31,627,032 vs 31,625,000 (+2,032 header) | 16 B | 2,013,711 | 4,031,737,583 | −0.48 / −1.22 / −0.21 / −1.73 % |
| P7 | 7 M | 554.74 M | 55,346,288 vs 55,344,256 | 16 B | 3,523,967 | 7,055,737,583 | −0.99 % |
| P12 | 12 M | 951.63 M | 94,877,032 vs 94,875,000 | 16 B | 6,041,055 | 12,095,737,583 | −0.69 % |
| P21 | 21 M | 1,668.98 M | 166,033,788 vs 166,031,756 | 16 B | 10,571,823 | 21,167,737,583 | −1.73 % |

STCS margins hold: P7 / Q mean = 1.76, P12 / P7 = 1.72, P21 / P12 = 1.75 (each ≥ 1.6). Cardinality within ± 3 %. Total
pristine ≈ 59 GB (`df`: 59 GiB used on `/mydata`). Files `chmod a-w`.

**Phase 1b — helper checks (not readings; helper heap 4 GiB, no container, pool 204 MB).**
- **H1** (11:02–11:07): default (verifying) `nodetool import` of Q1 → rc 0 in 34 s; tablestats "Index summary off heap
  memory used: 31,625,000" = Q1 `Summary.db` − 2,032-byte header (exact); compression metadata 2,013,672 B; bloom 8 B.
- **H2** (11:08–11:21): `import -q` Q1–Q4 at t0 + 271 s (rc 0, 1 s); the backstop started one background `COMPACTION` of
  exactly these four at t0 + 349 s ("Compacting (61505730…)" on `CompactionExecutor:3`); "Compacted … 4 sstables … 1.174GiB
  to 1.215GiB … in **338,639 ms** … 16,000,000 total partitions merged" → **D_q = 339 s** (< 10 min: no cut rule applies;
  K_P observes until t0 + 300 + 339 + 120 ≈ **760 s**). Output counted: summary **126,500,000 B** (as §2.5 expects), bloom
  20,205,160 B (19.3 MiB), compression metadata 8,031,216 B. smaps showed the builder blocks with `Rss` = written bytes and
  the copy overlap at each growth (1 s samples: 69.4 → 104.1 MiB with both resident for ~1 s, then 104.1 → 156.1 Size,
  then the trimmed 120.2 MiB block at the commit). RssAnon (helper, I0 4,586 MiB): +129 after the import (Q inputs: §2.4
  128.3), rising to +314 at the end of the merge, **peak +431 MiB at the commit/trim instant** (t0 + 687.5 s; §2.4
  predicted 396.4), standing **+314** after the commit (predicted 148: the freed input and builder blocks were not all
  returned to the OS). [`logs/H1/`](logs/H1/), [`logs/H2/`](logs/H2/).

**Phase 2 — calibration Z (11:22–11:27).** Victim, no P, no Q, heap 1,024 / L 2,048: up in 49 s, **I0_Z = 1,418 MiB**
(RssAnon; NMT committed 1,453 MB; cgroup `file` 268 MiB), peak 1,443, no `memory.events max`. I0_Z ∈ [1,377, 1,497] →
by the pre-declared rule the test condition is **heap 1,024 / direct 512 / L 2,048** (the owner-approved budget).
[`logs/Z/`](logs/Z/).

**Interruption and resume (note, 2026-11-20 21:30 EST).** The stage-2 session was cut off by an API usage limit (not by
the design) at about 13:00 EST, while phase 3 was at arm KP3. The node-side runner (`batch.sh phase3`, then
`phase4.sh`, both launched with `setsid nohup` before the cut-off) kept running without the session and finished every
planned arm by itself: phase 3 ended 13:23:35 EST ("BATCH DONE"), phase 4 ran U1 (13:23–13:32) and, because U1 was killed,
U2 (13:32–13:45), "PHASE4 DONE" 13:45:40 EST, all before the 16:30 no-start rule. Checked on resume (21:27 EST): no
`CassandraDaemon`, runner, sampler or `r10-*` scope on pc99; every arm's `summary.txt` ends with "done arm", "scope gone:
inactive", "end reason: normal", no `INVALID`; no staging directory left; load 0.05. **Completed cleanly before the cut-off
and reused:** the generated dataset (`data/pristine/`, 58 GB), H1, H2 (D_q), Z (calibration), and all 14 later arms (T1–3,
KP1–3, KQ1–3, I1–3, U1, U2), each with a complete log. **Cut mid-run:** nothing (no arm was running at the resume and none
was left incomplete), so nothing is redone.

**Amendment 1 (2026-11-20 21:30 EST, clock only; ordered by the coordinator after the interruption).** The time plan of
§2.9/§2.7 is shifted by the same offset as the deadline (+10 h): no arm starts after **02:30 EST 2026-11-21**; all runs
stopped and the case file written by **03:30 EST 2026-11-21**. Cut rules unchanged. The design and the owner-approved
container budget are unchanged. No reading was affected: every arm had already run under the original clock, and no
arm was started after the resume.

**Phase 3 and phase 4 — runs (readings).** Every arm from a clean start (fresh scope, fresh directories, fresh staging,
page cache dropped). Times t0 + s (t0 = launch). U = RssAnon (0.2 s sampler); Δ against the arm's I0. Kill rows quote the
kernel record (`dmesg-block.txt`: "Memory cgroup out of memory: Killed process … anon-rss … file-rss …", memcg stats
`anon` and `file_mapped`); every kill has `memory.events oom_kill` 1 and `CONSTRAINT_MEMCG`, `oom_memcg=…r10-<arm>-….scope`.
Source of each row: [`logs/arm-table.txt`](logs/arm-table.txt), [`logs/batch-logs.txt`](logs/batch-logs.txt), `logs/<arm>/`.

| Arm | I0 | After P import (Δ) | After redistribution | Q import | Compaction (start; last progress) | Peak U (Δ) | Outcome (invoking thread; kernel anon-rss / file-rss; memcg file_mapped) | K summary pool |
|---|---|---|---|---|---|---|---|---|
| T1 | 1,414 | 1,735 (+321) | — | t0+270.5, rc 2 | none started | 1,828 (+414) at t0+272.0 | **killed during the Q import** (`RMI TCP Connect`, importer opening Q2); 1,859.7 / 175.2; 170.5 | 316.25 MB vs 51 MB |
| T2 | 1,413 | 1,733 (+320) | — | t0+270.7, rc 0 | none started (pending 0) | 1,859 (+446) at t0+302 | **killed 38 s after the Q import**, P + Q standing (`C2 CompilerThread`); 1,864.2 / 174.9; 170.5 | 316.25 MB (then + Q 126.5) |
| T3 | 1,418 | 1,739 (+321) | — | t0+270.8, rc 2 | none started | 1,825 (+407) at t0+272.2 | **killed during the Q import** (`RMI TCP Connect`); 1,859.4 / 175.1; 170.5 | 316.25 MB |
| KP1 | 1,412 | 1,729 (+317) | — | — | — | 1,751 (+339) | survived to t0+772; +120: 1,750; `memory.events max` 2,719 | 316.25 MB all arm |
| KP2 | 1,420 | 1,738 (+318) | — | — | — | 1,766 (+346) | survived; +120: 1,759; max 2,852 | 316.25 MB |
| KP3 | 1,423 | 1,745 (+322) | — | — | — | 1,761 (+338) | survived; +120: 1,760; max 2,666 | 316.25 MB |
| KQ1 | 1,417 | — | — | t0+270.6, rc 0 | t0+348.8; 98.40 % at t0+628 | 1,823 (+406) at t0+595.5 (104→156 MiB builder copy) | **killed at the trim** (builder 120.2 MiB written; `CompactionExecutor`); 1,830.1 / 175.2; 170.5 | 0 → (Q 126.5 MB, counted only after the import) |
| KQ2 | 1,423 | — | — | t0+270.6, rc 0 | t0+349.1; 99.57 % at t0+634 | 1,830 (+407) at t0+598.3 | **killed at the trim** (builder 120.1 MiB written; `CompactionExecutor`); 1,834.1 / 175.2; 170.5 | as KQ1 |
| KQ3 | 1,416 | — | — | t0+270.8, rc 0 | t0+348.5; 99.53 % at t0+634 | 1,827 (+411) at t0+597.5 | **killed at the trim** (builder 120.0 MiB written; `CompactionExecutor`); 1,829.9 / 175.2; 170.5 | as KQ1 |
| I1 | 1,423 | 1,748 (+325) | 1,466 (+43); pool 316,251,328 → 19,766,700 B in 395 ms, avg interval 128 → 466.8 | t0+270.3, rc 0 | t0+352.7; 85.13 % at t0+581 | 1,776 (+353) at t0+510 | **killed at the last builder resize** (104.1 MiB block full → 156.1 MiB copy; `CompactionExecutor`); 1,829.7 / 175.2; 170.5 | 19.77 MB ≤ 51 MB before Q |
| I2 | 1,409 | 1,724 (+315) | 1,443 (+34); same redistribution | t0+270.7, rc 0 | t0+349.2; 85.85 % at t0+595 | 1,788 (+379) at t0+598.6 | **killed at the last builder resize** (`CompactionExecutor`); 1,830.2 / 175.2; 170.5 | 19.77 MB |
| I3 | 1,413 | 1,741 (+328) | 1,460 (+47); same redistribution | t0+271.0, rc 0 | t0+351.6; 85.73 % at t0+586 | 1,789 (+376) at t0+511.7 | **killed at the last builder resize** (`CompactionExecutor`); 1,830.0 / 175.2; 170.5 | 19.77 MB |
| U1 (1,280 / 2,560, direct 640, pool 64 MB) | 1,699 | 2,033 (+334) | — | t0+270.3, rc 0 | t0+351.8; 56.78 % at t0+512 | 2,284 (+585) at t0+515.9 | **killed in the compaction**, at the 69.4 → 104.1 MiB builder resize, P blocks 157.7 / 90.1 / 52.6 MiB resident (`CompactionExecutor`); 2,346.1 / 175.2; 170.5 | 316.25 MB vs 64 MB |
| U2 (1,536 / 3,072, direct 768, pool 76 MB) | 1,985 | 2,312 (+327) | — | t0+270.4, rc 0 | t0+351.7; done in 292,473 ms | 2,728 (+743) at t0+643.5 (trim) | **survived**; +120: 2,609 (+624); max 92,338; after: 4 sstables, summaries 442,751,012 B, bloom 20,205,184 B, compression 28,167,944 B | 442.75 MB vs 76 MB |

Resolved values read back in every arm as in "Environment" (pool 51 MB at heap 1,024; 64 MB at 1,280, 76 MB at 1,536;
direct 512 / 640 / 768 = L/4; networking pool 256 / 320 / 384 MiB). No `Redistributing index summaries` line in any arm
(the periodic task never ran: first run 60 min after start); the only redistribution is the I-arm JMX call. The Q
compaction ran in every Q arm that reached it as the default backstop's background `COMPACTION` of exactly Q1–Q4 (no
manual trigger), starting at t0 + 348.5–352.7 s. The import order is the hash-set order of the paths (P12, P7, P21; Q4,
Q3, Q2, Q1), the same in every arm.

**Per-holder readings (U independent of K).**
- **P (standing layer):** ΔU 315–328 MiB 30 s after the P import in all nine P arms (prediction 320.8 = Σ `Summary.db` +
  `CompressionInfo.db`); smaps shows the three summary blocks as fully resident anonymous mappings of 157.7, 90.1 and
  52.6 MiB (`Size` = `Rss`; P21, P12, P7 entries). K = 316,251,012 B against a 51 MB pool for the whole of every K_P and T
  arm (6.2 × C). No P-import transient above the standing level was seen (KP peaks +338–346 incl. ~20 MiB drift).
- **Redistribution (I arms):** the shipped call downsampled P to 19,766,384 B (≤ C) and RssAnon fell by 282–290 MiB within
  20 s (I1 1,748 → 1,466): the parked excess is the summaries, and it is returned to the OS.
- **Q (compaction layer):** +126–130 MiB after the Q import (Q input summaries + compression metadata, prediction 128.3).
  During the merge U rises steadily (the output bloom filter, compression metadata and summary builder) and the builder
  appears in smaps as one anonymous block per growth step (34 → 53 → 69.4 → 104.1 → 156.1 MiB `Size`), `Rss` = written
  bytes; at each growth the old and new blocks are both resident for ~1 s (KQ1: +104 MiB spike at t0+595.5 when the
  104.1 MiB block was copied into the 156.1 MiB one), and the final trim copies the 120.6 MiB written summary once more.
  Helper H2 (no limit) measured the whole Q term: peak **+431 MiB** at the trim (§2.4 predicted 396.4), +314 standing
  after the commit (predicted 148; freed blocks not all returned by glibc). N19's untrimmed tail stayed non-resident (the
  156.1 MiB block held 104–120 MiB `Rss`), as §1 predicted.
- **Effective ceiling of the container.** Every kill at L 2,048 came at kernel anon-rss **1,829.7–1,864.2 MiB**, with
  file-rss 175 MiB and memcg `file_mapped` **170.5 MiB** in every record (kernel stacks + page tables ≈ 6–11 MiB): the
  JVM's own mapped files (jars, `libjvm.so` …), charged to the scope because the per-arm `drop_caches` (§2.5) makes the
  victim fault them in itself, are not reclaimed. Usable anon headroom above I0 is therefore **≈ 410–445 MiB**, not the
  ≈ 595 MiB §2.4 took from C4 (C4's kill records show memcg `file` ≈ 5 MB and anon-rss ≈ 2,030 MiB: there the mapped JVM
  files were charged elsewhere). At L 2,560 (U1) the kill came at anon-rss 2,346 MiB (again L − 175 file − ~39).
- **Heap and direct:** no heap or direct-memory error in any arm (system.log ERROR count 0 in all 14 arms); heap committed
  = `-Xmx` (pre-touch); NMT committed at idle ≈ 1,453 MB, unchanged by the imports (the summary memory is outside NMT).

**Deviations from the design:** none in the procedure (amendment 1 is clock only and came after all readings). Phase 4
ran U2 because U1 was killed, as §2.5 prescribes.

## 4. Conclusion (stage 2)

**Verdict: retry.** Protocol status (detail): **`candidate`** — the test arm reached OOM 3/3, but the matched control
K_Q (the compaction layer alone) and the intervention I also reached the same endpoint 3/3, so V2 and V4 fail at the
approved budget; the test-arm kills were the import load of Q on top of parked P, not the claimed compaction overlap.
Direction as measured: the summary pool is unprotected between periodic runs (U > C and K > C during the window, as in
C4); the replacement overlap of one compaction (input + output + copy at growth/trim, plus the unprotected output bloom
filter and compression metadata) is uncovered by any control.

**Reason.** At heap 1,024 / direct 512 / container 2,048 (owner-approved V7, all capacities at defaults, pool 51 MB), the
parked P load stood at +315–328 MiB (K 316 MB vs C 51 MB) and survived alone 3/3 (KP peaks 1,751–1,766 MiB), but T was
killed 3/3 **before any compaction started**: twice while `nodetool import` opened the Q sstables (anon-rss 1,859 MiB) and
once 38 s later with P + Q standing (1,864 MiB), so the claimed holder (the compaction's output summary and its copies)
was never live in T. Q alone (K_Q) was killed 3/3 at the end of its merge, at the trim copy (builder 120 MiB written,
98.4–99.6 % progress, anon-rss 1,830–1,834 MiB), and the intervention I (P downsampled to 19.8 MB by the shipped
redistribution, ΔU −282 to −290 MiB) was killed 3/3 at the last builder resize (85–86 %, anon-rss 1,830 MiB). The design's
pre-declared reading for "a kill in K_Q or I" is retry. The cause of the miss is the budget model: the scope is charged
170.5 MiB of mapped JVM files that the kernel never reclaims (constant in all 9 kill records), so the anon ceiling is
≈ 1,830–1,864 MiB (headroom ≈ 410–445 MiB over I0 ≈ 1,415) instead of C4's ≈ 2,030 (595 MiB headroom), while the Q
compaction alone needs ≈ +410–431 MiB at its trim (helper: +431). The budget search confirms the shape one step up: at
heap 1,280 / L 2,560, T (U1) was killed **in the compaction** (56.8 %, at the 69 → 104 MiB builder resize, P's summary blocks
resident, anon-rss 2,346 MiB) — the claimed overlap — but only once and without matched controls at that budget; at
1,536 / 3,072 (U2) T survived (peak 2,728 MiB, +743 = P 327 + compaction 416). Largest budget reaching the endpoint: L 2,560
(1/1, U1); L 3,072 0/1.

**What a better design should change (for the retry row).**
1. **Run the test condition at heap 1,280 / direct 640 / L 2,560** (U1's budget, a 2.5 GiB node, owner review of the
   container), where T was killed in the compaction with P parked: predicted K_Q ≈ 1,699 + 431 = 2,130 vs anon ceiling
   ≈ 2,346 (margin ≈ 215), I ≈ 1,699 + 70 + 431 = 2,200 (margin ≈ 145), K_P ≈ 2,035; T ≈ 2,465 → kill. Run T, K_P, K_Q, I
   ×3 there.
2. **Model and calibrate the container's anon ceiling, not only I0:** in Z read memcg `file_mapped` after idle (here
   170.5 MiB constant once caches are dropped) and set L or the set sizes from L − file_mapped − ~15 MiB kernel; keep the
   per-arm `drop_caches` (a cold-started container really owns its mapped binaries) but state it, since C4's runs did not
   charge those pages.
3. **Keep the Q import below the ceiling in T:** the Q load (+126–130 MiB, with the importer's per-sstable double open)
   on top of parked P reached the ceiling before the merge. Either size P so that I0 + P + Q-load + import transient stays
   ≥ 100 MiB below the ceiling while I0 + P + 431 exceeds it (at L 2,048 no P works, because K_Q alone already reaches the
   ceiling; at L 2,560 the measured P works), or let Q arrive through the write path (flush/compaction outputs, no import
   double open).
4. **Use the K_Q result as its own lead:** at the approved 2 GiB budget, one default STCS merge of four full-sampling
   sstables (16 M partitions, 1,000-byte keys, summaries 120.6 MiB vs a 51 MB pool) was killed 3/3 at its trim. A
   single-term design (B5 replacement overlap alone: test Q, control a smaller Q such as 4 × 3 M, intervention by the
   redistribution of Q's inputs before the merge, which would remove the inputs' excess) could reach V1–V7 at L 2,048
   without P.

**Limits of attribution.** The kills are memcg kills whose last allocation was in the importer (T1, T3), the JIT (T2),
or the compaction (KQ, I, U1); they show the total was at the ceiling, and smaps shows which blocks were resident, but
not which byte is "the" cause. U1 is one run without matched controls at its budget. The dataset (1,000-byte keys,
offline `CQLSSTableWriter` files, `nodetool import -q`) and the four-at-once import are owner-accepted supporting choices
(a)–(e); the result does not speak for short keys or for flush-produced sstables.

**Left on pc99:** `/mydata/s4/r10/` ≈ 58 GB (`data/pristine/` ≈ 58 GB generated sstables, `arms/` 67 MB of run logs,
`node/` and `helper/` 365 MB each, `gen/`, `logs/`); no process, no scope.
