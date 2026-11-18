# C4 — index_summary_capacity: full-sampling summaries loaded outside the periodic cap exhaust the native headroom  <!-- file: cassandra/cases/index_summary_capacity--full-sampling-load-window/index_summary_capacity--full-sampling-load-window.md -->

| Field | Value |
|---|---|
| Case ID | `C4` (assigned at pick; takes over the never-run campaign row "C4/B5, mixed: replacement overlap / periodic index-summary enforcement") |
| From | `OC-49` of the phase 1 OOM candidate list; related retry row `R5` (stays `open`, not picked here) |
| Phase-1 case file | [`index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md); also [`index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` base.version 5.0.9) |
| Stage 1 (design) | OOM agent, phase-2 stage 1 session (Claude Opus 5.5), 2026-11-17 22:40–23:20 EST |
| Stage 2 (verify) | fresh OOM-agent sessions (Claude Opus 5.5): runs 2026-11-17 23:05 – 2026-11-18 00:21 EST, cut off by an API usage limit; resumed 2026-11-18 02:55–03:10 EST (refinement run, §3–§4) |
| Verdict | **true positive** (`verified-OOM · deployment`, kernel memcg OOM-kill; unprotected accumulation in the documented periodic window) |

## Summary

- **Design (stage 1):** BIG-format index summaries are malloc'd native memory, outside the heap and outside
  `MaxDirectMemorySize`. Their pool (`index_summary_capacity`, auto = 5 % of the heap) is enforced only by a
  periodic task (`index_summary_resize_interval`, 60 min). Sstables that arrive with full-sampling `Summary.db`
  (bulk load via `nodetool import`, restore, a restart within the hour after a load) are loaded uncapped. The
  design imports ≈ 90 M partitions with 1,000-byte keys (≈ 679 MiB of summaries against a 51 MiB cap, plus
  ≈ 150 MiB of bloom filters and compression metadata) into a node whose heap is 50 % of a 2 GiB container,
  and predicts a kernel memcg OOM-kill. Control: half the data. Intervention: the same sstables with their
  summaries already at the cap level.
- **Budget:** a container (cgroup `memory.max`) limit is the budget, because no heap or direct-memory limit
  covers this memory. So the design waits for the owner's review of the container budget (V7) before stage 2.
- **Conclusion (stage 2):** true positive, `verified-OOM · deployment`. Importing 90 M partitions in four full-sampling
  sstables (summaries 678.6 MiB vs a 51 MB pool) got the JVM OOM-killed by the container (2,048 MiB, heap 1,024) in 3/3
  runs at anon-rss 2,030 MiB; the smaller set (BCD) survived 3/3 at 87 %, and the same sstables with summaries
  downsampled to the cap survived 3/3 at 75–77 %. Largest failing container 2,048 MiB; 2,560 survives at its limit.
- **Root cause:** `index_summary_capacity` is applied only by the 60-min redistribution task; summaries loaded by
  `nodetool import` (or any open of full-sampling sstables) are malloc'd at full size, outside the heap and direct limits,
  with no byte bound until the next run. The yaml calls the pool best-effort, so this is an unprotected accumulation
  within a documented window (a sizing gap), not an implementation defect.

## 1. Candidate

**Candidate row, quoted** (phase 1 OOM candidate list, `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`):

> | OC-49 | 2026-11-17 | `index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous` | legacy | [lead list, blind, E1; N19] A summary rebuilt by upsampling keeps its `IndexSummaryBuilder` buffer sized for 64-byte keys and is never trimmed (`prepareToCommit` is not called on that path), while the pool counts 4 B + entry bytes: 76 B per entry, 1.73× measured for 32-byte keys, ≈ 3× for 12-byte keys, +300 to +800 MiB of native malloc at an 8 GiB heap. | CP-1, CP-14 | picked: C4 |

**Related retry row R5** (phase-2 retry list, status `open`), "what a better design should change", quoted in part:

> Toward defaults: full-sampling summaries between periodic runs (E2 flag: ≈ 440 MB from one major compaction vs ≈ 409 MiB default cap at an 8 GiB heap) and untrimmed upsample buffers (N19, 1.729× counted); the row cache is off by default, so argue it or replace it with another standing pool (C4/B5 shape)

**Old campaign row C4/B5** (`campaign-plan.md`, retired 2026-11-17): "mixed (replacement-overlap / periodic
enforcement) — Replacement overlap or periodic index-summary enforcement — Old/new live allocations, enforcement
intervals, format/path applicability; changed scheduling/interval control. Classify by whether local contracts hold."

**Phase-1 constraint and check.** `index_summary_capacity` (`Config.java:539-540`, yaml key empty →
`DatabaseDescriptor.java:866-869`: `max(1, (int)(Runtime.totalMemory() × 0.05 / 2^20))` MiB). The check is the
periodic redistribution (`IndexSummaryManager.java:117-147`: scheduled with initial delay = interval, default
`index_summary_resize_interval: 60m`, `Config.java:543`; `IndexSummaryRedistribution.java:103-154, 258`), which
shrinks the counted total Σ `getOffHeapSize()` to ≤ the pool after each run, down to the floor at
`max_index_interval` (2048 → 1/16 of full sampling).

**What stage 4 measured.**
- `applySimpleConfig` (unit re-run 2026-10-25, `Not confirmed — caps (counted size)`): after each redistribution the
  counted size is ≤ C + 4 KiB, proportional to C, evenly spread; summaries rebuilt by **upsampling** allocate
  76 × (Σ maxEntries + k) B = **1.729 ×** their counted size for 32-byte keys (5,946,316 vs 3,439,832 B), because
  `BigTableReader.java:631-640` builds them with `IndexSummaryBuilder` and never calls `prepareToCommit()`
  (`IndexSummaryBuilder.java:100-128, 246-251`). Cluster tier: counted size capped after R1; RSS not measured there.
- `adjustSamplingLevels` (cluster, 2026-10-21, `Confirmed — caps only on some paths (bypass)`): with no run,
  **1930 MiB of summaries stood under a 64 MiB cap** (20 sstables, 1000-byte keys, `min_index_interval` 1 in that
  test), RssAnon falling by the same bytes at each later run (within 0.3 %). The cap holds only at each run.

**Why the design is not the upsample buffer alone.** The OC-49 excess is a ratio on the counted pool: an
upsampled summary holds 76/(K + 12) × its counted bytes for keys K ≤ 64 B (1.73 × at 32 B, 4.75 × at 4 B), and the
counted pool is ≤ C after every run. So that excess is bounded by C × 76/(K + 12): ≤ 243 MiB at a 1 GiB heap,
≤ 485 MiB at 2 GiB (4-byte keys), and to fill even a 51 MiB counted pool with 16-byte entries takes ≈ 430 M partitions,
whose bloom filters (≈ 1.25 B per partition at `bloom_filter_fp_chance` 0.01, ≈ 512 MiB) would dominate the native
growth. It cannot be the main holder of a default-budget OOM that a run tonight can produce. The same holder
(index summaries) has a larger gap at defaults: nothing caps them between runs, which is the R5 direction and
the old C4/B5 row. This case designs for that gap; the untrimmed-builder term is named in the protection map
and left as a follow-up (it also appears when `Summary.db` is missing: the loading builder at
`BigSSTableReaderLoadingBuilder.java:209-229` calls `build()` without `prepareToCommit()`).

**JIRA prior art** (read only, REST search on issues.apache.org, 2026-11-17 ≈ 22:55 EST; plus the survey
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`; nothing posted):

| Query | Hits | Relevant |
|---|---|---|
| `project=CASSANDRA AND text ~ "\"index summary\"" AND (text ~ memory OR text ~ OOM)` | 91 | CASSANDRA-5519 (the pool and periodic resampling, Fixed 2.1: the design); 14649 (builder "trim" allocated extra space on the writer path, Fixed 2.2.14/3.0.18/3.11.4/4.0; the upsample path still never trims); 6359 (sstableloader did not free summary memory, Fixed 2.0.3); 17735 (resize interval / capacity config bugs, Fixed 4.0.6/4.1); 21832 (read rates undercount BF false positives, Patch Available: share, not total); 20491 (document off-heap memory, open: lists index summaries with `index_summary_capacity` as their limit) |
| `text ~ IndexSummaryBuilder AND (trim OR capacity OR upsample OR untrimmed)` | 4 | 14649, 13545, 8993, 15084: none on the upsample/rebuild path |
| `text ~ buildSummaryAtLevel OR index_summary_capacity OR index_summary_resize_interval` | 60 | none about load-time or between-run overshoot or OOM |
| survey CSV (`summar`, `index_interval`, `bloom`) | — | 2875 (Won't Fix: shrink indexes on low heap; by design), 10821 (Won't Fix: kernel OOM-killer during compaction, bloom filters and compression metadata unprotected), 11344 (BF sizing with LCS, Fixed), 3224 (BF for L0 backlog) |

Verdict: periodic-only enforcement is **by design** (5519; the yaml describes the resize interval); loading
full-sampling summaries over the cap until the next run as an OOM path is **new** (no report); the untrimmed
upsample/rebuild buffer is **new** (14649 fixed only the writer path). Not a known-fixed bug, so not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

At shipped defaults (BIG format, `storage_compatibility_mode: CASSANDRA_4`, yaml `#  selected_format: big`), every
sstable carries an index summary: one entry per 128 partitions (`min_index_interval` 128) holding the full
partition key, an 8-byte index position and a 4-byte offset, allocated with `Memory.allocate` → JNA
`Native.malloc` (`MemoryUtil.java:81-84`), i.e. **native memory outside the heap, outside `MaxDirectMemorySize`
and invisible to NMT**. When an sstable is opened from disk its `Summary.db` is loaded at the level it was saved
(`BigSSTableReaderLoadingBuilder.loadSummary`, exact-size allocation). Sstables written by a flush, compaction,
`CQLSSTableWriter` or a streaming writer are saved at full sampling (`BigTableWriter.java:255, 320`). The pool
`index_summary_capacity` is applied only by the redistribution task, first run one full interval after start
(`IndexSummaryManager.java:122-147`), then every 60 min. **`nodetool import`** (`SSTableImporter.java:157-238`)
opens each new sstable (`SSTableReader.moveAndOpenSSTable`), keeps them all open and adds them to the tracker at
the end; nothing triggers a redistribution. So after an import of D sstables, native memory grows by their full
summaries (plus their bloom filters, `Filter.db`, and compression metadata, `CompressionInfo.db`, which have no
capacity control at all) and stays there up to 60 min. With 1,000-byte keys the summaries dominate (7.9 B per
partition vs 1.25 B of bloom filter). Inside a container sized as a node with RAM = 2 × heap, the pre-touched heap
(`-XX:+AlwaysPreTouch`, `jvm-server.options:128`) plus the JVM's native baseline leave ≈ 600 MiB; the imported
summaries exceed it and the kernel memcg OOM-killer ends the JVM.

**Direction label (proposed, decided from the readings in stage 2):** convergence of uncapped native index
structures with the heap in one process budget, where the summary pool is over its cap during the documented
periodic window: by the protocol's table, U > C and K > C for the summary pool = **bypass by late (periodic)
enforcement** if the cap is the contract, or **unprotected accumulation within a documented window** if the
window is the contract (the protocol counts a documented periodic window into C). Bloom filters and compression
metadata: unprotected (no control). The ID keeps the assigned `C4`. Technique notes:
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (defaults, feasibility first) and
[`bypass-playbook.md`](../../../bypass-playbook.md) (late enforcement: compare protected and suspect path).

### 2.2 Protection map (fixed before the run)

| Domain | Allocation and owner | Local contract (counter K, limit C) | Scope / multiplicity | Lifetime | Budget covering it |
|---|---|---|---|---|---|
| Index summaries (claimed holder) | `IndexSummary` offsets + entries, `Memory.allocate` (JNA malloc), per BIG sstable; loaded from `Summary.db` | K = `IndexSummaries.MemoryPoolSizeInMB` = Σ `getOffHeapSize()` (also table gauge `IndexSummaryOffHeapMemoryUsed`); C = auto 5 % of heap (51 MiB at a 1024 MiB heap, read back from the log line `memory pool size of N MB`); enforced only by the periodic run (soft, periodic) | per sstable, all tables; no bound on sstables loaded between runs | until sstable release or the next downsample | process memory only (container) |
| Untrimmed builder buffers (OC-49 term) | `IndexSummaryBuilder` capacity kept by summaries built at `BigTableReader.java:631` (upsample) or `BigSSTableReaderLoadingBuilder.java:209` (no `Summary.db`) | counted as entries only; alloc = 76 B/entry for K ≤ 64 B, ≤ 2 × (growth) above | not reached by this design (no upsample, `Summary.db` present); recorded as 0 by design | until the next downsample | container |
| Bloom filters | `OffHeapBitSet` (JNA malloc) per sstable, loaded from `Filter.db` | no control (`bloom_filter_fp_chance` 0.01 sizes it, 10 bits per partition); gauge `BloomFilterOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Compression metadata | chunk offsets (JNA malloc), from `CompressionInfo.db` | no control (8 B per 16 KiB chunk); gauge `CompressionMetadataOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Heap | Java heap, pre-touched | `-Xmx` = 1024 MiB (`MAX_HEAP_SIZE`) | process | standing, resident from start | container + `-Xmx` |
| Direct buffers | Netty / networking pool (`networking_cache_size` = min(128, heap/16) = 64 MiB), chunk cache off (`file_cache_enabled: false`) | `MaxDirectMemorySize` 512 MiB | process | standing | container + direct limit |
| JVM native baseline | metaspace, code cache, GC structures, thread stacks, glibc arenas | none | process | standing | container |
| Page cache of read files | `Summary.db`, `Filter.db`, `CompressionInfo.db` reads; mmap'd `Index.db` (`disk_access_mode: mmap_index_only`) | none; clean file pages, reclaimable by the memcg before an OOM-kill | per cgroup | reclaimable | counted in `memory.current` as `file`, not `anon` |

### 2.3 Configuration and budget audit

- **Build:** `/mydata/s4/cassandra-base`, built from a copy of `systems/cassandra/source/` (5.0.9) with
  `ant jar` (JDK 11.0.33 on pc96, Ant 1.10.12). If another session has already built it there (a
  `build/apache-cassandra-5.0.9-SNAPSHOT.jar` exists and no `ant` runs in it), reuse it read-only; never run `ant`
  in a tree a node runs from. Each node runs from its own copy: `rsync -a --exclude data --exclude logs
  /mydata/s4/cassandra-base/ /mydata/s4/c4-w1/node/` (victim) and `/mydata/s4/c4-w1/helper/` (helper).
- **Node:** pc96 (local, `node0.jason92-325405`), x86_64, 32 cores, 125 GiB RAM, 8 GiB swap (kept at 0 for the
  victim with `MemorySwapMax=0`), cgroup v2, `/mydata` on a rotational RAID volume (PERC H710P), 572 GiB free
  at stage 1 (checked read-only 22:41 EST). Other sessions share the node: check `ps -eo cmd | grep
  '[C]assandraDaemon'`, `ss -ltn`, `/proc/loadavg` and `df -h /mydata` before each phase and record them.
- **yaml (victim):** the shipped `conf/cassandra.yaml` with **environment edits only**: `cluster_name: c4w1`,
  `listen_address`/`rpc_address`/`seeds` 127.0.0.1, `storage_port: 27040`, `native_transport_port: 29040`,
  `data_file_directories`, `commitlog_directory`, `saved_caches_directory`, `hints_directory` under the arm
  folder. Every capacity setting stays at its shipped value: `index_summary_capacity:` (empty → auto),
  `index_summary_resize_interval: 60m`, `memtable_allocation_type: heap_buffers`, `file_cache_enabled` unset
  (false), `networking_cache_size` unset (auto), `disk_access_mode` unset (`mmap_index_only`). Save the diff per
  arm; fail the arm if a non-environment line differs.
- **Table (victim and generator):** `CREATE KEYSPACE c4 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE c4.isx (pk text PRIMARY KEY, v int);` — every table option default (STCS, `min_index_interval`
  128, `max_index_interval` 2048, `bloom_filter_fp_chance` 0.01, LZ4 with 16 KiB chunks).
- **JVM (victim):** `MAX_HEAP_SIZE=1024M`, `MAX_DIRECT_MEMORY_SIZE=512M` (what `cassandra-env.sh`
  `calculate_heap_sizes` gives for RAM = 2048 MiB: heap ½, direct ¼), `HEAP_NEWSIZE` unset, G1 (shipped
  `jvm11-server.options`), `-XX:+AlwaysPreTouch` (shipped). `JMX_PORT=27099` (exported before
  `bin/cassandra`; `cassandra-env.sh` honours it). `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary
  -XX:ParallelGCThreads=16 -XX:ConcGCThreads=16"` and `taskset -c 0,2,4,…,30`: the R1-V pc96 settings, so the
  idle baseline is comparable with R1-V's pc96 readings (heap 768: idle RssAnon 1124–1146 MiB; 1024: 1409–1423;
  1536: 1958–1967; R1-V case file §"Completion of the re-run").
- **Resolved defaults to read back per arm** (system.log, `jvm-args.txt` from `/proc/<pid>/cmdline`): heap
  1024, direct 512, index summary pool ("Initializing index summary manager with a memory pool size of N MB and a
  resize interval of 60 minutes", N expected 51; stage 4 saw 50 at `-Xms1024m`, so 50–51), networking pool 64,
  memtable heap/off-heap limits 256.
- **Budgets:** heap 1024 MiB and direct 512 MiB (both ≥ 512 MiB: V7 standing rule met). **Container**
  `memory.max` = 2048 MiB (`systemd-run --user --scope -p MemoryMax=2048M -p MemorySwapMax=0`), the claimed node
  being one with 2 GiB RAM, heap = 50 % of it as `cassandra-env.sh` and `hardware.adoc` put it. This is the only
  budget that covers the claimed memory, so **V7 needs the owner's case-by-case review** (the protocol's
  standing rule covers heap and direct only). Precedent: R1-V family A (L = 2 × heap) accepted by the
  researcher on 2026-11-12 and its pc96 condition A-768 (container 1536) filed `verified-OOM · deployment` on
  2026-11-16. Search upward: 1536 / 3072 (claimed 3 GiB node); fallback down: 768 / 1536 (§2.5).
- **Supporting choices for the owner to accept** (not capacity settings): (a) partition keys of 1,000 bytes
  (`text`, within the 65,535-byte key limit) sharing a 988-byte prefix (path- or URL-like keys); (b) a data
  density of ≈ 92 GB of sstables (≈ 90 M partitions) on a 2 GiB node; (c) `nodetool import -q` (the documented
  "quick" import: no verification, no cache invalidation); the default import first verifies each sstable
  (reads every `Data.db`, ≈ 6–10 min per arm on this disk) and then opens it the same way, so the loaded memory
  is the same; (d) the generator writes the sstables offline with `CQLSSTableWriter` (the documented bulk-load
  tool), equivalent to sstables streamed or restored from another node.

### 2.4 Ceiling arithmetic

Per sstable at full sampling, keys of 1,000 B: entries ⌈N/128⌉ × 1,012 B (1,000 key + 8 position + 4 offset);
bloom filter ≈ N × 10 bits; compression metadata ≈ ⌈N × 1,015 B / 16 KiB⌉ × 8 B.

| Sstable | Partitions N | Summary (MiB) | Bloom filter (MiB) | Compression metadata (MiB) | Sum (MiB) | On disk (≈ GB, Index.db + LZ4 Data.db) |
|---|---|---|---|---|---|---|
| A | 48,000,000 | 361.9 | 57.2 | 22.7 | 441.8 | 48.4 + ≈ 2.5–5 |
| B | 24,000,000 | 181.0 | 28.6 | 11.3 | 220.9 | 24.2 + ≈ 1.3–2.5 |
| C | 12,000,000 | 90.5 | 14.3 | 5.7 | 110.5 | 12.1 + ≈ 0.6–1.2 |
| D | 6,000,000 | 45.2 | 7.2 | 2.8 | 55.2 | 6.0 + ≈ 0.3–0.6 |
| **ABCD** | 90,000,000 | **678.6** | 107.3 | 42.5 | **828.4** | ≈ 91 + 5–9 |
| BCD (control) | 42,000,000 | 316.7 | 50.1 | 19.8 | 386.6 | |
| ABCD at the cap (intervention) | 90,000,000 | ≤ 51 (floor 42.4) | 107.3 | 42.5 | ≤ 200.8 | |

The four sizes are a factor 2 apart, so each sstable is alone in its STCS bucket (bucket 0.5–1.5 × average,
`min_threshold` 4): no compaction starts after the import.

**Feasibility at defaults (heap 1024, L 2048).** Σ contract capacities if the cap held: idle ≈ 1,415 (pc96
R1-V, includes heap 1024, networking pool, JVM baseline) + 51 (summary pool) + 107.3 + 42.5 ≈ 1,616 MiB = 79 % of
L: the endpoint is impossible while the summary pool is at its cap. With the pool uncapped (as loaded):
1,415 + 828 ≈ 2,243 MiB = 110 % of L. The R1-V pc96 kills happened at RssAnon ≈ 98 % of L (kernel anon-rss
1,999–2,010 at L 2048), so the predicted kill point is cumulative RssAnon ≈ 2,005 MiB, i.e. ΔU ≈ 590 MiB into the
import. Error bounds: idle ± 30 MiB (pc96 spread plus no write load here), bloom-filter bits ± 10 %, compression
metadata ± 20 %, summaries exact to the header (from `Summary.db` sizes). The test arm stays above the kill point
for any combination of those errors (worst case 1,385 + 678.6 + 96 + 34 = 2,194 MiB); the control (BCD) stays below
(worst case 1,445 + 316.7 + 55 + 24 = 1,841 MiB = 89.9 %); the intervention (worst case 1,445 + 51 + 118 + 51 =
1,665 MiB = 81 %).

### 2.5 Workload and environment

**Paths:** everything under `/mydata/s4/c4-w1/` (`node/`, `helper/`, `gen/`, `data/pristine/{A,B,C,D}/`,
`data/int-<cap>/`, `arms/<arm>/`, `logs/`); nothing else on the node is touched. Harness copies under
`<case folder>/harness/`; small excerpts under `<case folder>/logs/<arm>/`.

**Phase 0 — build and checks (≈ 10 min).** Copy the pinned source to `/mydata/s4/cassandra-base` (if absent),
`ant jar`, record the jar sha256 and `git`-less tree hash (`find src -type f | sort | xargs sha256sum | sha256sum`).

**Phase 1 — dataset (generated once, ≈ 30 min; not a reading).**
- `gen/GenSorted.java` (written by stage 2) on the classpath `build/apache-cassandra-5.0.9-SNAPSHOT.jar:build/lib/jars/*`,
  JDK 11 client options from `conf/jvm11-clients.options`, `DatabaseDescriptor.clientInitialization()` (the
  builder does it). Arguments: output dir, `lo`, `hi`. Key i = `PREFIX + String.format("%012d", i)`, where
  `PREFIX` = 988 characters drawn from `[a-z0-9]` by `new java.util.Random(49)`; value `v` = 1.
  Sstable ranges: D = [0, 6 M), C = [6 M, 18 M), B = [18 M, 42 M), A = [42 M, 90 M) (disjoint keys).
- Order rows by Murmur3 token: token(i) = `Murmur3Partitioner.instance.getToken(ByteBufferUtil.bytes(key(i))).getLongValue()`;
  sort ascending (signed long), ties by key bytes; then `CQLSSTableWriter.builder().inDirectory(dir)
  .forTable("CREATE TABLE c4.isx (pk text PRIMARY KEY, v int)").using("INSERT INTO c4.isx (pk, v) VALUES (?, ?)")
  .sorted().build()` and `addRow(key(i), 1)` in that order; one output sstable per run (no max size). Generator
  heap `-Xmx8g`, at most two generators at once, pinned with `taskset -c 1,3,5,7,9,11,13,15`.
- Generate D first and time it; then A and C together, then B. **Cutoff:** if D's rate projects the whole set
  past phase-start + 45 min, scale all four N by one factor f < 1 chosen to meet it, recompute §2.4 and record a
  dated amendment before any arm (the fallback budget below then applies if f < 0.75).
- Check each sstable: exactly one `-big-Data.db` per directory, `Summary.db` size = ⌈N/128⌉ × 1,012 + header
  (≤ 2.1 KB incl. first/last keys) ± 0.1 %, `Filter.db` and `CompressionInfo.db` sizes recorded
  (`ls -l`, these file sizes are the independent U estimates for §2.6). Instrument check (not a reading): in the
  helper node (heap 4 GiB, no container, ports 27041/29041/27098), import D with the **default** (verifying)
  `nodetool import`; it must succeed (proves the sorted order and format), then `nodetool tablestats c4.isx`
  index-summary bytes = D's summary size ± 0.1 %. Stop the helper; drop its data.
- Keep the generated directories as `data/pristine/{A,B,C,D}/` (read-only by convention; `chmod a-w` on files).

**Per-arm staging (identical initial state).** For each set in the arm: `cp -al data/pristine/X arms/<arm>/stage/X`
then replace `*-Summary.db` and `*-Statistics.db` with real copies (`cp --remove-destination`), because
import mutates `Statistics.db` and a redistribution rewrites `Summary.db` in place; `Data.db`, `Index.db`,
`Filter.db`, `CompressionInfo.db`, `Digest`, `TOC` stay hardlinks (never written). After the arm, `rm -rf
arms/<arm>/{stage,data,commitlog,saved_caches,hints}`.

**Arm procedure** (one script, `harness/arm.sh <arm> <heap> <L> <set list> [int-<cap>]`):
1. Pre-checks: no other `CassandraDaemon` using ports 27040/29040/27099; record load, free memory, disk.
2. Start the victim in a fresh scope: `systemd-run --user --scope --unit=c4w1-<arm>-<epoch> -p MemoryMax=<L>M
   -p MemorySwapMax=0 -- taskset -c 0,2,…,30 node/bin/cassandra -f`, with the environment of §2.3; wait for CQL
   (≤ 180 s, else invalid arm). Read back heap, direct, pool size, networking pool from logs and `jvm-args.txt`.
3. Create the keyspace and table with `node/bin/cqlsh 127.0.0.1 29040`.
4. Idle: 60 s; the 1 s sampler runs from step 2. Idle value I0 = median RssAnon of the last 30 s.
   Take tablestats, ISSampler (`IndexSummaries` attributes), NMT summary at idle.
5. Import: `node/bin/nodetool -p 27099 import -q c4 isx <stage>/D <stage>/C <stage>/B <stage>/A` (only the arm's
   sets, always in the order D, C, B, A); record start and end epoch ms and the exit code.
6. Observe 120 s after the import returns (or until the JVM is gone): tablestats, ISSampler and NMT at +10 s,
   +60 s, +120 s.
7. Stop: `nodetool -p 27099 stopdaemon`, wait ≤ 60 s, kill by PID if needed; check the scope unit is gone;
   save `memory.events` (read in the sampler), the kernel OOM block (`sudo -n dmesg`, block naming the scope,
   R1-V `dmesg-block.sh` adapted to the unit prefix `c4w1-`), the system/debug log excerpts (`Loading new SSTables`,
   `Done loading`, `Initializing index summary manager`, any `Redistributing index summaries`, any ERROR).
8. Clean the arm's data (staging rule above).

**Phase 2 — budget search (single runs; readings).**
- `S1`: test set ABCD at heap 1024 / L 2048. `S2`: ABCD at heap 1536 / L 3072 (direct 768, claimed 3 GiB node).
- (a) S1 killed, S2 alive → the test condition is **1024 / 2048** (main plan). (b) both killed → the test condition
  is 1536 / 3072 (cap read back, ≈ 76 MiB; control BCD predicted 1,962 + 387 = 2,349 = 76 %), and run `S3` =
  ABCD at 2048 / 4096 once. (c) S1 alive → record ΔU against §2.4, then the test condition is **768 / 1536**
  (direct 384, cap ≈ 38) with the control **CD** (1,135 + 166 = 1,301 = 85 %; BCD would be 99 %) and the
  intervention at cap 38.
- If time remains after phase 4 (see the time plan), one refinement run between the largest failing and the
  smallest surviving heap (e.g. 1280 / 2560: predicted 1,690 + 828 = 2,518 = 98 %, marginal).

**Phase 3 — intervention set (≈ 8 min; not a reading).** In the helper (no container, heap 4 GiB, yaml
`index_summary_capacity: <cap>MiB` where `<cap>` is the victim's read-back pool size at the test heap,
`index_summary_resize_interval: -1`), import staged copies of A–D (`-q`), then invoke
`redistributeSummaries` once over JMX (the stage-4 `ISSampler.java invoke` mode, copied from
`capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous/`,
table name changed to `c4.isx`). Check: "Completed resizing … current approximate memory used: ≤ <cap> MiB",
`MemoryPoolSizeInMB` ≤ cap, every sstable's `Summary.db` rewritten (smaller). Stop the helper; move its
`c4/isx-*` directory content (the four sstables, hardlinked data plus the new `Summary.db`) to
`data/int-<cap>/{A,B,C,D}/` (one directory per sstable, by partition count from `Statistics.db`/`sstablemetadata`).
Stage it like pristine sets (copies of `Summary.db` and `Statistics.db`).

**Phase 4 — verdict arms (readings), interleaved T, K, I, T, K, I, T, K, I at the test condition:**
- **T** (test, ×3): ABCD as generated (full-sampling summaries).
- **K** (matched control, ×3): BCD (47 % of the partitions, same keys, same node and budget).
- **I** (intervention, ×3): ABCD from `int-<cap>` (identical files except `Summary.db` at the cap level).
S1 counts as the first T run only if its procedure was identical (same script version); otherwise T ×3 is run anew.

### 2.6 Instruments

- **1 s sampler** (`harness/sampler.sh <pid> <cgroup dir> <csv>`): epoch ms, `RssAnon`, `VmRSS`, `RssFile`
  from `/proc/<pid>/status`; cgroup `memory.current`, `memory.stat` `anon` and `file`, `memory.events`
  `max`, `oom`, `oom_kill`. U for the whole process = RssAnon and cgroup `anon` (JNA malloc is anonymous memory).
- **Per holder, independent of K:** Σ `Summary.db`, `Filter.db`, `CompressionInfo.db` sizes of the sstables
  imported (from `ls -l` before staging), and ΔU(T) − ΔU(I) (identical arms except the summaries) against
  Σ `Summary.db`(T) − Σ `Summary.db`(I).
- **Counters K:** `IndexSummaries` `MemoryPoolSizeInMB`, `MemoryPoolCapacityInMB`, `IndexIntervals`
  (ISSampler); `nodetool tablestats c4.isx`: "Index summary off heap memory used", "Bloom filter off heap memory
  used", "Compression metadata off heap memory used", "SSTable count". The table gauges count only sstables in the
  tracker, which `nodetool import` adds at the end: in a killed arm K stays at the pre-import value, and U is read
  from the sampler and the file sizes.
- **JVM-internal native:** NMT summary (committed) at idle and +60 s: must stay within ± 20 MiB, so ΔRssAnon is
  outside NMT (JNA).
- **Initiating failure:** kernel block "invoked oom-killer … CONSTRAINT_MEMCG … oom_memcg=…c4w1-<arm>…
  Killed process <pid> (java) … anon-rss:…"; `memory.events oom_kill` = 1; last sampler row ≤ 1 s before; the
  debug log's last opened sstable (`Opening …` lines from `SSTableReader`), which tells how much of the set had
  loaded.

### 2.7 Predicted response and stopping budget

| Arm (test condition 1024 / 2048) | Predicted ΔU after import (MiB) | Predicted peak RssAnon (% of L) | Endpoint |
|---|---|---|---|
| T | 828 (summaries 679) | ≈ 2,243 → killed at ≈ 2,005 (≈ 98 %) while A loads | **kernel memcg OOM-kill**, 3/3 |
| K | 387 (summaries 317) | ≈ 1,802 (88 %) | none, 3/3; K = 317 MiB > C = 51 for 120 s (no run) |
| I | ≤ 201 (summaries ≤ 51) | ≈ 1,616 (79 %) | none, 3/3; K ≤ C |
| S2 (1536 / 3072) | 828 | ≈ 2,790 (91 %) | none (boundary) |

Also predicted: no "Redistributing index summaries" line in any victim arm (first run due 60 min after start);
ΔU − (Σ file sizes of the loaded sstables) within ± 5 %; NMT committed unchanged within ± 20 MiB.

**Stopping budget:** each arm ≤ 8 min wall (start ≤ 180 s, idle 60 s, import, 120 s observation, stop); no
arm is repeated beyond the plan except an arm declared invalid (CQL never up, wrong read-back, another
process on the ports), at most once each; no escalation after the kills (no larger sets, no smaller budgets than
§2.5's fallback). Everything ends by **02:30 EST on 2026-11-18**.

**What each outcome would mean** (for §4): T killed 3/3, K 0/3, I 0/3 with ΔU tracking the summary files →
true positive candidate (V1–V7 if the owner accepts the container budget). T not killed at any tested budget,
with the full set loaded and ΔU ≈ prediction → false positive within this data volume only if the ceiling
arithmetic shows no larger volume fits a realistic node; otherwise retry with a larger data set (the data volume
was the dial left). Kills in K or I → the margin is wrong: retry with the measured idle (no re-design in place).

### 2.8 Controls and intervention

- **Matched control (V2), ×3:** BCD at the same build, budget, keys, staging and procedure: the same holder at
  47 % of the multiplicity, predicted 12 % below the kill point. It shows the node survives the import of a
  smaller full-sampling set, so the endpoint depends on the volume of summaries loaded at once.
- **Causal intervention (V4), ×3:** ABCD with `Summary.db` already downsampled to the pool cap by the
  shipped redistribution code (unmodified build, phase 3). Only the summaries change; bloom filters, compression
  metadata, `Index.db`, `Data.db` and the import are identical. If the kill disappears, the excess of the
  summaries over their cap (the gap between load and the periodic run) is the cause. Throughput is not an issue
  (no client load); the import of all four sstables must succeed in I (exit code 0, SSTable count 4).
- **Repetitions:** every verdict arm from a clean start (fresh scope, fresh data directories, fresh staging).

### 2.9 Time plan (stage 2, from its start S)

| Step | Duration | Ends at |
|---|---|---|
| Phase 0: checks, source copy, `ant jar`, harness, instrument checks | 15 min | S + 0:15 |
| Phase 1: dataset generation and checks (cutoff rule above) | 35 min | S + 0:50 |
| Phase 2: S1, S2 (≤ 8 min each) | 16 min | S + 1:06 |
| Phase 3: intervention set | 8 min | S + 1:14 |
| Phase 4: 9 verdict arms (≈ 5–6 min each) | 50 min | S + 2:04 |
| Optional refinement run, cleanup of processes, §3–§4 write-up | 20 min | S + 2:24 |

Latest start for the full plan: **00:05 EST** (end 02:29). Between 00:05 and 00:25: skip S2 and the
refinement (end ≈ S + 2:00). After 00:25: do not start; record it as blocked by time. Resources at peak: victim ≤ 3
GiB (container), helper ≤ 6 GiB, two generators ≤ 2 × 9 GiB (never with a measured arm), 16 + 8 pinned CPUs,
≈ 100 GB on `/mydata` (pristine set; per-arm copies ≤ 0.8 GB; the int set ≈ 0.05 GB plus hardlinks). Left on the
node at the end: the dataset under `/mydata/s4/c4-w1/data/` (kept until the owner accepts the wave's results),
no running process, no scope.

`sha256 of §1–§2 at freeze: 16fff307d8b7127d43184724abb665668107ef77d8f3b17b3db6aeba9b25a473` (bytes from the line `## 1. Candidate` up to, not including, this line) · amendments after the freeze: §2.10 (stage 2, dated; the hash above still matches §1–§2.9 as frozen, checked 2026-11-17 23:05 EST).

### 2.10 Owner review and stage-2 amendments (after the freeze; recorded before any reading)

**V7 review (owner, 2026-11-17 23:05 EST): APPROVED.** The owner approved the 2048 MiB container (cgroup
`memory.max`) budget with heap 1024 MiB and direct 512 MiB, the budget search (1536 / 3072, fallback 768 / 1536),
1,000-byte partition keys with a shared 988-byte prefix, ≈ 92 GB of data on a 2 GiB node, `nodetool import -q`, and
offline `CQLSSTableWriter` bulk-written sstables (supporting choices (a)–(d) of §2.3).

**Amendment 1 (2026-11-17 23:10 EST, environment; a step could not run as written).** `conf/cassandra-env.sh:235`
sets `JMX_PORT="7199"` unconditionally, so an exported `JMX_PORT` is not honoured (§2.3 assumed it was). The JMX port
is set instead with `JVM_EXTRA_OPTS=... -Dcassandra.jmx.local.port=27099` (victim) / `27098` (helper); `JVM_EXTRA_OPTS`
is appended last (`cassandra-env.sh:307`), so this later `-D` wins (read back in `jvm-args.txt`; `nodetool -p 27099` connects).
No file of the build is edited.

**Amendment 2 (2026-11-17 23:12 EST, dataset; recomputed prediction, not a design change).** The generated sstables carry
a 16-byte `Filter.db` (no bloom-filter bits): `CQLSSTableWriter` in sorted mode creates its writer with key count 0
(`AbstractSSTableSimpleWriter.java:115`, `SSTableTxnWriter.createRangeAware(..., 0, ...)`), so
`FilterFactory.getFilter(0, 0.01)` sizes the filter for 0 keys (`SortedTableWriter.java:445`); on import
`loadFilter` accepts it (same FP chance), so it is not rebuilt. The bloom-filter domain is therefore ≈ 0 MiB in every
arm instead of 107.3 MiB (§2.4). Everything else in §2.4 holds (D's `Summary.db` = 47,439,532 B = ⌈6 M/128⌉ × 1,012 +
2,032 B header; `CompressionInfo.db` 2,988,327 B, 0.50 B per partition → ≈ 42.7 MiB for ABCD). Recomputed predictions
(same idle 1,415 ± 30 MiB, kill point ≈ 2,005 MiB RssAnon at L 2048):

| Arm (1024 / 2048) | Predicted ΔU (MiB) | Predicted peak RssAnon | Endpoint |
|---|---|---|---|
| T (ABCD) | 678.6 + 42.7 = 721 | 2,136 (104 %); worst low 1,385 + 678.6 + 34 = 2,098 > 2,005 | memcg OOM-kill while A loads (D+C+B bring it to ≈ 1,752) |
| K (BCD) | 316.7 + 19.8 = 337 | 1,752 (86 %); worst high 1,786 (87 %) | none |
| I (ABCD at cap 51) | ≤ 51 + 42.7 | ≤ 1,509 (74 %) | none |
| S2 (1536 / 3072) | 721 | ≈ 1,962 + 721 = 2,683 (87 %) | none |

The change removes an uncontrolled domain from every arm, so the summaries carry nearly all of ΔU (a stricter
attribution). Sstables written by a node's own flush, compaction or streaming have full bloom filters, which would add
≈ 107 MiB on top: the generated set is the lighter case.

**Amendment 3 (2026-11-17 23:13 EST, harness; no reading affected).** The first helper instrument check
(`arms/check-D.aborted-script-edit/`) was aborted: the arm script was overwritten in place while it ran (bash reads a
running script by offset) and it also ran with `-q` instead of the verifying import. It was re-run from a clean start
(`arms/check-D/`). New script versions are installed with copy + `mv`. The re-run (`arms/check-D.invalid-cqlsh-timeout/`)
was invalid as well: `cqlsh` timed out connecting (5 s default) while the generators loaded the disk, so the table was
never created; the arm script now retries `cqlsh` (connect timeout 30 s, up to 5 tries) and checks the table exists.

**Amendment 4 (2026-11-17 23:26 EST, dataset; a step could not run as written).** The first generated set was written
in sstable version `oa` (the 5.0 format): `DatabaseDescriptor.applyStorageCompatibilityMode` forces `NONE` in client
mode (`DatabaseDescriptor.java:1604-1606`), so `CQLSSTableWriter` run with `clientInitialization` writes `oa`. The
victim runs the shipped `storage_compatibility_mode: CASSANDRA_4`, whose BIG current version is `nb`
(`BigFormat.java:343`), and refuses `oa` files as incompatible (`BigFormat.java:518`; the import silently found "No new
SSTables", checked by parsing the file name in daemon mode: "incompatible sstable version (oa)"). The `oa` set was
deleted and the whole set regenerated with `DatabaseDescriptor.toolInitialization()` from the shipped, unmodified
`conf/cassandra.yaml` (as the bundled sstable tools initialise; `-Dcassandra.storagedir=/mydata/s4/c4-w1/gen/storage`
for the tool's unused directories), which writes `nb-*-big-*` files, the version a CASSANDRA_4 node writes itself.
Same keys, same order, same sizes expected; amendment 2 (16-byte `Filter.db`) to be re-checked on the new set.

**Amendment 5 (2026-11-17 23:43 EST, after S1, before S2's readings were used and before any verdict arm; procedure).**
`nodetool import` keeps its source directories in a hash set (S1's log: `srcPaths='[.../B, .../A, .../D, .../C]'`), so
the load order follows the hash of the path strings, not the command line; §2.5 step 5's "always in the order D, C, B,
A" cannot be imposed. To keep the order the same in every arm with the same sets, the verdict arms stage at a fixed
path (`/mydata/s4/c4-w1/stage_node/<X>`, symlinked as `arms/<arm>/stage`), which gives the order **B, A, D, C** for
ABCD (T and I) and **B, D, C** for BCD (K), recorded per arm from the `Opening` lines. S1 and S2 staged under
`arms/<arm>/stage` (S1 order B, A, D, C; S2 order D, C, B, A); by §2.5's rule S1 therefore does not count as a T run
and T is run three times anew. Also observed in S1/S2 (no design change): with a source directory, the importer opens
each sstable **twice**, once in place to choose the target disk (`SSTableImporter.getTargetDirectory`,
`SSTableImporter.java:297`, then released) and once after the move (`SSTableReader.moveAndOpenSSTable`), so each
sstable's summary is allocated twice in a row; a transient overlap of up to one extra summary is possible during the
import.

**Amendment 6 (2026-11-17 23:44 EST, instrument).** S1's 1 s sampler saw only one row inside the 4 s import (the
growth happens within ≈ 0.3–0.5 s per sstable), so the sampler interval is lowered to **0.2 s** for the later arms
(the protocol asks for an interval shorter than the growth window; reading `/proc/<pid>/status` and three cgroup files
costs < 1 % of one core). In a killed arm, the kernel OOM record (`anon-rss`) remains the reading at the kill.

**Amendment 7 (2026-11-17 23:48 EST, intervention-set helper yaml).** `index_summary_resize_interval: -1` is refused
in 5.0 ("Invalid duration: -1"); the shipped yaml comment says a null value disables the task, so the helper's yaml
sets `index_summary_resize_interval:` (empty) with `index_summary_capacity: 51MiB` (the victim's read-back pool at heap
1024: "memory pool size of 51 MB"). Helper only; no victim arm changes.


## 3. Runs (stage 2)

**Resumption note (2026-11-18 02:55 EST, continuing stage-2 session, Claude Opus 5.5).** The first stage-2 session was cut
off by an API usage limit after 00:21 EST (not by the design), before it wrote §3–§4 or exported the verdict-arm
excerpts. Nothing was running on pc96 at resumption (no `CassandraDaemon`, `GenSorted`, sampler or `nodetool`; no
`stage_*` directory; load 1.97). Freeze hash of §1–§2.9 re-checked: `16fff307…a473`, matches. Inspected
`/mydata/s4/c4-w1/` (`logs/batch-phase2.log`, `logs/batch-phase4.log`, every `arms/<arm>/summary.txt`, sampler CSV,
dmesg block, system/debug logs). **Reused, all complete with clean logs:** the build (`/mydata/s4/cassandra-base`, jar
sha256 `570b5249…0176e`), the `nb` dataset `data/pristine/{A,B,C,D}` (92 GB), the intervention set `data/int-51`,
the instrument check `check-D`, the budget search S1/S2, and **all nine verdict arms T1–T3, K1–K3, I1–I3** (phase 4
ran 23:51–00:21 with one script version, `arm.sh` sha256 `8c66a006…`, identical to `harness/arm.sh`). Each verdict
arm has its start read-back, idle snapshot, import exit code, sampler rows to the end, stop/scope-gone line, dmesg
search and log excerpt; I1's import lines sit in the rotated `logs/system.log.2026-11-17.0.zip` (local-midnight
rotation), read from there. No arm was redone. Not yet done at resumption: the optional refinement run (§2.5 phase 2)
and the exports to `logs/`. The design's own stopping clock (§2.7, 02:30 EST) was replaced by the session's deadline
(07:30 EST); the one optional refinement run below is the only run started after resumption, planned before its reading:
`R1280` = ABCD at heap 1280 / L 2560 (direct 640), predicted standing RssAnon ≈ 1,705 + 734 ≈ 2,440 MiB (≈ 95 % of L),
marginal (kill point ≈ 98 % of L).

### 3.1 Environment (as run)

pc96 (local, `node0.jason92-325405`), x86_64, 32 cores, 125 GiB RAM, kernel 5.15.0-198-generic, cgroup v2, OpenJDK
11.0.33 (G1), `/mydata` rotational RAID. Build `/mydata/s4/cassandra-base` (5.0.9, `ant jar`, unmodified): jar sha256
`570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, source tree hash
`aea91c484d53ff9ba2a839d699f71952a13b4db6634e47735eaefc2b55745e90` (`logs/build-hash.txt`); victim runs from
`/mydata/s4/c4-w1/node/`, helper from `/mydata/s4/c4-w1/helper/`. Victim yaml: shipped file plus the 11 environment
lines of §2.3 (`logs/<arm>/cassandra.yaml.diff`, checked per arm; none other). Read back in every victim arm
(`logs/<arm>/summary.txt`): `-Xms/-Xmx` = heap, `-XX:MaxDirectMemorySize` = L/4 (512M at L 2048, 640M at 2560, 768M at
3072), G1, `-XX:+AlwaysPreTouch`, GC threads 16 (the later `JVM_EXTRA_OPTS` value wins over the env's 32), JMX 27099
(amendment 1), `index_summary_capacity=null` → "memory pool size of **51 MB**" at heap 1024 (64 MB at 1280, 76 MB at 1536),
`index_summary_resize_interval=60m`, `disk_access_mode=mmap_index_only`, `file_cache_enabled=false`,
`memtable_allocation_type=heap_buffers`, networking pool auto ("Global buffer pool limit is 256 MiB" at heap 1024),
affinity even CPUs 0–30. Scope per arm: `systemd-run --user --scope -p MemoryMax=<L>M -p MemorySwapMax=0`
(`memory.max` and `memory.swap.max` = 0 read back). Pre-checks per arm: load 0.2–2.4 in the verdict arms; no other
daemon on the arm's ports (other sessions' Cassandra daemons ran on other ports during S2 (1) and R1280 (3)).
Full logs: `/mydata/s4/c4-w1/arms/<arm>/` (summary.txt, sampler.csv, system/debug/gc logs, dmesg block, NMT,
tablestats, ISSampler); excerpts in `logs/<arm>/` of this folder; batch logs `logs/batch-phase2.log`,
`logs/batch-phase4.log`, `logs/batch-refine.log`.

### 3.2 Phases 0–1: build, dataset, instrument check (not readings)

- Dataset (amendments 2 and 4): `nb` BIG sstables from `GenSorted.java` (harness/), 1,000-byte keys (988-byte shared prefix,
  `Random(49)`), Murmur3-sorted, one sstable per set, generated 23:26–23:39 EST. Sizes (`logs/pristine-listing.txt`):

  | Set | Partitions | `Summary.db` (B) | `CompressionInfo.db` (B) | `Filter.db` | `Index.db` (B) | `Data.db` (B) |
  |---|---|---|---|---|---|---|
  | D | 6,000,000 | 47,439,532 | 3,020,551 | 16 B | 6,047,737,583 | 472,548,395 |
  | C | 12,000,000 | 94,877,032 | 6,041,055 | 16 B | 12,095,737,583 | 951,237,675 |
  | B | 24,000,000 | 189,752,032 | 12,082,071 | 16 B | 24,191,737,583 | 1,907,758,730 |
  | A | 48,000,000 | 379,502,032 | 24,164,103 | 16 B | 48,398,410,969 | 3,823,559,666 |
  | ABCD | 90,000,000 | 711,570,628 (678.6 MiB) | 45,307,780 (43.2 MiB) | — | ≈ 90.7 GB | ≈ 7.2 GB |

  Each `Summary.db` = ⌈N/128⌉ × 1,012 B + 2,032 B header, as §2.4 predicted.
- Instrument check `check-D` (helper, heap 4 GiB, no container, **default verifying** import): rc 0 in 21 s, SSTable count
  1, "Index summary off heap memory used" **47,437,500 B** = D's `Summary.db` − its 2,032-byte header (exact). Three
  earlier attempts were invalid and are kept under their names (amendments 3 and 4).
- Intervention set `int-51` (phase 3, helper, `index_summary_capacity: 51MiB`, task disabled per amendment 7): import -q
  ABCD, then one `redistributeSummaries` over JMX (406 ms): pool 711,562,500 B → **44,474,364 B (42.4 MiB ≤ 51)**,
  average interval 128 → 554.7 (every sstable at the floor `max_index_interval` 2048 except by rounding). New
  `Summary.db`: A 23,721,288, B 11,861,660, C 5,932,352, D 2,967,192 B; every other component a hardlink of the
  pristine file (link count 3, `logs/int-51-listing.txt`).

### 3.3 Phase 2: budget search (single runs)

| Run | Heap / L (direct) | Pool C | Load order | I0 RssAnon (MiB) | Endpoint | Reading at end |
|---|---|---|---|---|---|---|
| S1 (1 s sampler, older script, not a T run) | 1024 / 2048 (512) | 51 MB | B, A, D, C | 1,426 | **memcg OOM-kill** while A's first open (in place) ran, 2.1 s into the import | kernel `anon-rss:2078672kB` (2,030 MiB); `oom_kill` 1 |
| S2 | 1536 / 3072 (768) | 76 MB | D, C, B, A | 1,977 | alive, import rc 0 (2.9 s), 4 sstables | standing ΔRssAnon +720 MiB at +60 s; peak cg `memory.current` 2,772 MiB (90 % of L); K = 711,562,500 B |
| R1280 (refinement, after resumption) | 1280 / 2560 (640) | 64 MB | B, A, D, C | 1,701 | alive, import rc 0 but 7–8 s; 4 sstables | standing ΔRssAnon +721 MiB at +60 s; RssAnon 2,494 MiB at +120 s (97 % of L), cg `anon` 2,440 MiB (95 %) with `memory.current` pinned at the limit (2,560 MiB, file pages being reclaimed), `memory.events max` 515, no OOM |

Outcome (§2.5 case a): S1 killed, S2 alive → test condition **1024 / 2048**. The refinement places the boundary between
L 2048 (killed) and L 2560 (survives at its limit, under reclaim pressure).

### 3.4 Phase 4: verdict arms at 1024 / 2048 (cap 51 MB), interleaved T, K, I ×3, script `8c66a006…`, sampler 0.2 s

| Arm | Sets (load order) | I0 RssAnon (MiB) | Import | Endpoint | Peak / kill reading | Standing ΔRssAnon at +60 s (MiB) | K: summary bytes (tablestats) |
|---|---|---|---|---|---|---|---|
| T1 | ABCD (B, A) | 1,437 | rc 2 (JMX EOF: JVM gone) at 2.9 s | **memcg OOM-kill** during A's second open (after move) | kernel `anon-rss:2079792kB` = 2,031 MiB (ΔU 594); cg `anon` 2,133,934,080 B at the kill | — | 0 (import adds to the tracker at the end) |
| K1 | BCD (D, C, B) | 1,444 | rc 0, 2.0 s, 3 sstables | none | peak RssAnon 1,787; cg current 1,863 (91 %) | +331 | 332,062,500 (316.7 MiB > C 51) |
| I1 | ABCD@int-51 (B, A, D, C) | 1,431 | rc 0, 1.5 s, 4 sstables | none | peak 1,573; cg current 1,600 (78 %) | +97 | 44,474,364 (42.4 MiB ≤ C) |
| T2 | ABCD (B, A) | 1,425 | rc 2 at 3.0 s | **memcg OOM-kill** during A's second open | kernel `anon-rss:2078836kB` = 2,030 MiB (ΔU 605) | — | 0 |
| K2 | BCD | 1,430 | rc 0, 2.0 s | none | peak 1,787; cg current 1,864 (91 %) | +334 | 332,062,500 |
| I2 | ABCD@int-51 | 1,439 | rc 0, 1.5 s | none | peak 1,558; cg current 1,615 (79 %) | +95 | 44,474,364 |
| T3 | ABCD (B, A) | 1,430 | rc 2 at 2.9 s | **memcg OOM-kill** during A's second open | kernel `anon-rss:2079228kB` = 2,030 MiB (ΔU 600) | — | 0 |
| K3 | BCD | 1,428 | rc 0, 1.9 s | none | peak 1,786; cg current 1,860 (91 %) | +332 | 332,062,500 |
| I3 | ABCD@int-51 | 1,437 | rc 0, 1.5 s | none | peak 1,531; cg current 1,587 (77 %) | +80 | 44,474,364 |

**T 3/3 killed, K 0/3, I 0/3.** Every kill: kernel block "oom-kill:constraint=CONSTRAINT_MEMCG … oom_memcg=…/c4w1-T<n>-….scope
… Killed process <pid> (java)", `memory.events oom_kill` 1 (`logs/T<n>/dmesg-block.txt`, `summary.txt`); the faulting
thread was the importer's `RMI TCP Connection` thread (`do_anonymous_page`, i.e. a malloc'd page being touched). No
"Redistributing index summaries" line in any victim arm (first run due 60 min after start); no ERROR before the kill.

### 3.5 Attribution readings (U independent of K)

- **Standing ΔU equals the file sizes of the loaded summaries plus compression metadata** (JNA malloc, read from disk at
  exact size): S2 +720 MiB vs 678.6 + 43.2 = 721.8 MiB (−0.3 %); R1280 +721 MiB (−0.1 %); K1–K3 +331 to +334 vs
  316.7 + 20.2 = 336.9 MiB (−1 to −2 %); I1–I3 +80 to +97 vs 42.4 + 43.2 = 85.6 MiB (±12 MiB). Between I and the ABCD
  arms (identical files except `Summary.db`) the difference is the summaries alone: 720 − 91 (I mean) ≈ 629 MiB measured vs
  678.6 − 42.4 = 636 MiB of `Summary.db`.
- **NMT** committed rose 1,449 → 1,483–1,485 MiB from idle to +60 s in every surviving arm (K, I, S2, R1280 alike),
  all of it `Arena Chunk` (+30–31 MiB, JVM-internal, same whether ΔU was 80 or 735 MiB) plus 1–2 MiB class/code: the
  ± 20 MiB prediction missed by that arena growth, but ΔRssAnon is outside NMT (JNA malloc) as predicted. Heap committed
  stayed at `-Xmx` (pre-touched).
- **Counters K vs C:** the summary gauge and `IndexSummaries` pool read 711,562,500 B (678.6 MiB) after ABCD (S2, R1280)
  against C = 76 / 64 MB, and 332,062,500 B after BCD (K arms) against C = 51 MB: **U > C and K > C** for the whole
  observation window, no run of the periodic task. In T the gauges stay 0 because the importer adds the sstables to the
  tracker only at the end, which the killed JVM never reached; U there comes from the sampler, the kernel record and the
  files.
- **Transient overlap (observed, not designed):** the importer opens each sstable in place, releases it, and opens it again
  after the move (amendment 5); the release runs on `ScheduledExecutors.nonPeriodicTasks` (`SSTableReader.java:1540`),
  so two copies of one summary can be live for a moment. T1's 0.2 s rows: RssAnon 1,437 → 1,813 (+376 ≈ 2 × B's 193 MiB)
  after B's two opens, a dip to 1,780 when the first copy is freed, then the kill during A's second open. VmHWM =
  VmRSS at +10 s in K and S2, so there the transient never exceeded the standing value. The endpoint does not depend on the
  overlap: the standing ABCD load at heap 1024 is I0 (1,425–1,437) + 720 = **2,145–2,157 MiB RssAnon > L = 2,048 MiB**
  before page cache and kernel memory; the overlap only decides at which open the kill comes (S1 was killed earlier, at A's
  first open, with B + A ≈ 578 MiB loaded).
- **Predictions vs readings:** idle 1,415 ± 30 → 1,425–1,444 (inside); T kill at ≈ 2,005 MiB RssAnon while A loads →
  kernel anon-rss 2,030–2,031 while A loads; K peak 1,752 (86 %) → 1,786–1,787 (87 %); I ≤ 1,509 → 1,531–1,573 (75–77 %,
  the +30 MiB arena growth); S2 2,683 → 2,711 (88 %).

### 3.6 Deviations from the design

Amendments 1–7 (§2.10) as recorded before the readings. Also: S1 does not count as a T run (older script, 1 s sampler,
different staging path), so T ran three times anew; I1's import lines are in the local-midnight rotated
`system.log.2026-11-17.0.zip` (read from there, appended to `logs/I1/log-excerpt.txt`); the NMT prediction missed (above);
the §2.7 stopping clock (02:30) was replaced by the session deadline (07:30) only for the optional refinement R1280, which
§2.5 planned. No arm was repeated, none was invalid among S1, S2, T1–T3, K1–K3, I1–I3 and R1280.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** (kernel memcg OOM-kill), under the owner's V7
review of the 2 GiB container (2026-11-17 23:05 EST).

**Reason.** At shipped defaults (index-summary pool auto = 51 MB at a 1,024 MiB heap, resize every 60 min) a node with a
2,048 MiB container, 1,024 MiB heap and 512 MiB direct limit was OOM-killed by the kernel in **3/3** runs (plus S1) when
`nodetool import -q` loaded 90 M partitions in four full-sampling BIG sstables: the importer opened B and A, malloc'ing
their `Summary.db` at full size (B 181 MiB, A 362 MiB; 678.6 MiB for the whole set against the 51 MB cap), and the
JVM was killed at anon-rss 2,030–2,031 MiB, 2.9 s into the import, with no redistribution run and no rejection. The
matched control (BCD, 47 % of the partitions, summaries 316.7 MiB = 6.2 × the cap) survived **0/3 kills** at 87 % RssAnon
(91 % `memory.current`), and the intervention (the same sstables with `Summary.db` downsampled to the cap by the shipped
redistribution code, 42.4 MiB) survived **0/3 kills** at 75–77 %, importing all four sstables. Standing ΔRssAnon equals the
summary plus compression-metadata file sizes within 2 % (S2 +720 vs 721.8 MiB), outside NMT, and the summary counter itself
reads 678.6 MiB against a 76 MB pool for the whole observation window. Budget search: the largest container that reaches the
endpoint is **2,048 MiB (heap 1,024)**; at 2,560 MiB (heap 1,280) the node survives pinned at its limit (RssAnon 97 % of L,
`memory.current` at the limit, 515 `memory.events max`), at 3,072 MiB (heap 1,536) at 90 %.

**Classification.** By the measurement table the summary pool has U > C and K > C (678.6 MiB counted against 51–76 MB) with
enforcement only on the 60-min timer (CP-11). The yaml documents the pool as "best-effort … may need to use more than this
amount", and the timer as the mechanism, so the overshoot lies within the documented contract: the case is **unprotected
accumulation** (no byte bound on summaries loaded between two runs; compression metadata has no control at all) on native
memory outside `-Xmx` and `MaxDirectMemorySize` (CP-9), reached through the bulk-import path (CP-10-like: the load path never
triggers the redistribution). Interpretation: intentional soft target, a configuration-sizing gap; not an implementation
defect. Not a known JIRA (§1); CASSANDRA-20491 (open) lists `index_summary_capacity` as the limit of this memory.

| | Evidence |
|---|---|
| V1 Repetition | T1–T3 killed 3/3 from clean starts (fresh scope, data and staging), kernel record each (§3.4) |
| V2 Matched control | K1–K3 (BCD) 0/3, same build, budget, keys, staging; peak 87 % RssAnon / 91 % cgroup (margin ≈ 9 % to the limit, declared 12 % in §2.4: below the 30 % starting target, stated) |
| V3 Measurement | U from sampler RssAnon / cgroup anon, kernel anon-rss and the file sizes; K from tablestats and `IndexSummaries` (§3.5) |
| V4 Intervention | I1–I3 (summaries at the cap, unmodified build) 0/3 kills, import rc 0 with 4 sstables each |
| V5 Initiating failure | kernel CONSTRAINT_MEMCG block + `oom_kill` 1, faulting importer thread, last `Opening` line (A); holder = JNA malloc, not visible to a heap histogram: attributed by the I/K differential and the file-size match (no native dump) |
| V6 Default constraints | `index_summary_capacity` auto (51 MB), `index_summary_resize_interval` 60m, `min/max_index_interval` 128/2048, all other yaml capacity settings shipped; only environment lines differ |
| V7 Acceptable budget | heap 1,024 and direct 512 (standing rule); container 2,048 approved by the owner 2026-11-17 23:05 EST |

**Limits.** One node, one data shape: 1,000-byte keys sharing a 988-byte prefix, ≈ 92 GB on a 2 GiB node, written offline
with `CQLSSTableWriter` (owner-approved supporting choices). Those sstables have empty bloom filters (amendment 2); sstables a
node writes itself would add ≈ 107 MiB more, so the tested set is the lighter case. `-q` import used in the victim arms (the
verifying import loads the same summaries, shown on D only). The restart-after-load and restore paths, the upsample/untrimmed
builder term of OC-49, and client load during the window were not tested. The kill instant includes a transient double-open
overlap of the importer, but the standing load alone exceeds the budget (§3.5).

**Left on pc96:** `/mydata/s4/c4-w1/` — `data/pristine/` (≈ 92 GB) and `data/int-51/` (hardlinks plus 44 MB of summaries),
`gen/` (≈ 6 GB incl. tool storage), `node/`, `helper/` (365 MB each), `arms/` (17 MB of logs), `logs/`; the build
`/mydata/s4/cassandra-base`. No process, scope or `stage_*` directory left.
