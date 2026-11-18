# C4 — index_summary_capacity: full-sampling summaries loaded outside the periodic cap exhaust the native headroom  <!-- file: cassandra/cases/index_summary_capacity--full-sampling-load-window/index_summary_capacity--full-sampling-load-window.md -->

| Field | Value |
|---|---|
| Case ID | `C4` (assigned at pick; takes over the never-run campaign row "C4/B5, mixed: replacement overlap / periodic index-summary enforcement") |
| From | `OC-49` of the phase 1 OOM candidate list; related retry row `R5` (stays `open`, not picked here) |
| Phase-1 case file | [`index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md); also [`index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` base.version 5.0.9) |
| Stage 1 (design) | OOM agent, phase-2 stage 1 session (Claude Opus 5.5), 2026-11-17 22:40–23:20 EST |
| Stage 2 (verify) | pending (a fresh session) |
| Verdict | `pending` |

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
- **Conclusion:** pending (stage 2).

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

pending

## 4. Conclusion (stage 2)

pending
