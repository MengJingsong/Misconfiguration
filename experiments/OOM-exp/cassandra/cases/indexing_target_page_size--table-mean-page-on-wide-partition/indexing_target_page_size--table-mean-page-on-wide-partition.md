# B20 (OC-504) — indexing_target_page_size: a 2i build page sized from the table-wide mean row holds a whole wide partition  <!-- file: cassandra/cases/indexing_target_page_size--table-mean-page-on-wide-partition/indexing_target_page_size--table-mean-page-on-wide-partition.md -->

| Field | Value |
|---|---|
| Case ID | `B20` (B = bypass case; README "ID prefixes") |
| From | `OC-504` of the Cassandra phase-1 OOM candidate list (cluster primary; duplicates `OC-494` and the legacy `OC-43`) |
| Phase-1 case file | [`indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source`, the repo's pinned checkout) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-21 08:00–08:55 EST |
| Stage 2 (verify) | a fresh OOM-agent session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-21 08:15–09:50 EST on `ms0640` |
| Verdict | **true positive** (`verified-OOM · deployment`; bypass, accounting mismatch) |

## Summary

- **Conclusion:** true positive, `verified-OOM · deployment`. One `CREATE INDEX` on a table of 1,000,000 small partitions
  plus one partition of 4,000 rows × 1 MiB killed the node with `OutOfMemoryError: Java heap space` in the index-build
  thread 3/3 at a 2 GiB heap and 3/3 at 4 GiB (5 GiB survived 0/3 with the whole 4.19 GB page live), every constraint at
  its shipped default. The same partition without the skew (control) and the skewed data with the page bounded to 32
  rows (intervention) both built the index with no OOM (0/3 each).
- **Root cause:** the legacy secondary-index build turns its 32 MiB page target into a row count once per build, from the
  **table-wide** mean row size (`SecondaryIndexManager.java:1149-1170`): here 6,618 rows (mean row ≈ 5 KB). The pager
  bounds rows only, and each page is copied whole into an `ImmutableBTreePartition` on the heap
  (`SecondaryIndexManager.java:1066`), so the 4,000 rows of 1 MiB became one 4.19 GB page — 1.75 GB of it was live when a
  2 GiB heap ran out (≈ 42–52 × the target).

## 1. Candidate

**The row** (`phase1-oom-candidates.md`, Status already set to `picked: B20 (2026-11-21)` by the session):

> | OC-504 | 2026-11-18 | `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` | guided |
> Holder: one secondary-index build page, copied whole into an ImmutableBTreePartition on heap before the indexers run.
> [details](runs/wave3.md#oc-504) | CP-12, CP-2, CP-1 | picked: B20 (2026-11-21) |

Full text (`runs/wave3.md`, "OC-504"):

> Holder: one secondary-index build page, copied whole into an ImmutableBTreePartition on heap before the indexers run.
> Why nothing stops it: the 32 MiB target is turned into a row count once per build, from table-wide means of serialized
> size. The pager then bounds only rows (min(pageSize, remaining)); no bytes are checked. (1) For any table with zero
> regular columns (:1164), and when cassandra.force_default_indexing_page_size is set, the page is a flat 10,000 rows with
> no byte bound. (2) A partition whose rows are larger than the table mean gets min(10000, 32 MiB / mean) of its large
> rows. (3) Heap per row exceeds serialized size. The result is the JVM's OutOfMemoryError in the build thread. Size at
> defaults: on the :1164 path, 10,000 x clustering-key rows of up to 64 KiB = up to about 640 MiB per page (stage 4:
> 120-400 MB at 40-60 KB rows). With skew, a table of mean ~10 KB rows and one partition of 1 MiB rows gives about 3.3 GB
> per page. Times concurrent_index_builders = 2.
>
> **Where:** src/java/org/apache/cassandra/index/SecondaryIndexManager.java:1149-1170 (page size from means; 10000-row
> fallbacks at :1151,:1156,:1160,:1164); :1053-1066 (page materialized as ImmutableBTreePartition);
> src/java/org/apache/cassandra/service/pager/AbstractQueryPager.java:95-101 (row count only);
> src/java/org/apache/cassandra/config/Config.java:350 (2 builders)

**Triage** (`runs/triage-2026-11-20.md`, rank 2): "yes (legacy 2i ships enabled, `default_secondary_index` legacy) |
single ARM node | … With skewed data (about 1M small partitions plus one partition of about 2,500–3,000 rows of 1 MiB),
the mean row is small, the page is 10,000 rows, and one page of the wide partition is about 2.5–3 GB, past a 2 GiB heap
in one CREATE INDEX. The zero-regular-column fallback (flat 10,000 rows of 64 KiB clustering keys, about 640 MiB per
page, x 2 concurrent builders) is weaker. … | No existing case. Duplicates OC-494 and the legacy OC-43 (open), so run
once. The build is legacy 2i only: SAI uses its own builder." Cluster note 4: "Index-build page counted in rows: OC-504
(primary), OC-494, plus the legacy OC-43." Note 5(b): "OC-494 (rank 2)" is to be run with the primary.

**The cluster duplicates, quoted:**

> | OC-494 | 2026-11-18 | `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` | autonomous |
> Index build pages have no byte bound in two cases. calculateIndexingPageSize returns a flat 10000 rows with no byte
> bound for any table with zero regular columns (:1164), and otherwise sizes the page from the table-wide mean row size,
> so skewed data defeats the 32 MiB target. [details](runs/wave3.md#oc-494) | — | open |
>
> (details) … A table whose mean row is small (many 100 B rows) but which also has partitions of large rows gets
> pageSize = 10000. indexPartition then materializes each page into an ImmutableBTreePartition on the heap. Rough size:
> 10000 rows x 100 KiB = ~1 GiB per page, per concurrent build (CREATE INDEX or nodetool rebuild_index). Stage 4
> measured ~400 MB per page with 40 KB rows and zero regular columns, against 35 MB on the capped path.

> | OC-43 | 2026-11-16 | `indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous` | legacy |
> [lead list, blind, E1] The index-build page row count comes from the table-wide mean row size, so a partition with rows
> far above the mean gets min(10,000, 32 MiB ÷ mean) large rows (mean ~10 KB with 1 MiB rows → a ≈ 3.3 GB page, × 2
> concurrent builders; arithmetic), and the zero-regular-column fallback gives 10,000 × row size (≈ 400 MB in stage 4). |
> CP-2, CP-12 | open |

**What this design covers.** The **skew path** (mean-based page size, `:1167-1170`) that all three rows name: OC-504 (2),
OC-494's second case and OC-43's first half. Not covered: the `:1164` zero-regular-column fallback (OC-504 (1), OC-494's
first case, OC-43's second half; ≤ 10,000 × 64 KiB ≈ 655 MB per page, × 2 builders ≈ 1.3 GB, weaker, already measured
at ≈ 400 MB per page by phase-1 stage 4) and the non-default `cassandra.force_default_indexing_page_size` property. The
×2 `concurrent_index_builders` multiplier is not needed here: one build page alone exceeds the budget. Stage 2 writes the
verdict to OC-504 only; OC-494 and OC-43 stay as the session decides (this stage changes no list status).

**Phase-1 case file and stage-4 result.** Phase-1 estimate `positive, but with a bypass` (the `:1156/:1160/:1164`
fallbacks drop the byte target). Its stage 4 (2026-10-26, advisor's macOS arm64 machine, run 1; results in
`stage4-runtime-verification/results/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md`):
- unit tier **Confirmed — caps only on some paths (bypass)**: uniform 64 KB rows give `ps` = 563 and pages ≤ 36.9 MB
  (1.10 × 32 MiB); forced 10,000 gives one 131.2 MB page; zero regular columns (`:1164`) gives `ps` = 10000, one 120 MB page;
- cluster tier **Confirmed** (2 GiB heap): `Calculated page size 857` and 35.2–35.8 MB live per page on the computed path;
  397.6–409.1 MB per page on the forced/`:1164` paths. Defect D1: a restarted node compacting the 480 MB partitions of
  40 KB clustering keys died of OOM (that is U9's row-index holder, not this one).
- The 2026-11-16 blind recheck (E1) added the skew overshoot as an untested path: "per-page heap under skew is
  undetermined until a skewed table is run". **No skewed table was ever run**; B20 is that run.

**JIRA prior art** (read only; nothing posted).
- `jira-oom-survey.csv` (604 rows), grep for index build / rebuild / page size: **CASSANDRA-12796** "Heap exhaustion when
  rebuilding secondary index over a table with wide partitions" (Fixed 2.2.9/3.0.11/3.10; survey class
  `bypass:release-defect`): one `OpOrder` group spanned a whole wide partition, so index-memtable flush/reclaim waited and
  flush runnables piled up. Its fix (Sam Tunnicliffe, 2016-11-24: "it's possible to use a Pager here, as in pre 3.0
  versions") is the origin of the paged `indexPartition` this case targets. Different holder (memtable reclaim), fixed.
  Other survey hits (CASSANDRA-16, -2301, -16071, -20752) are compaction, streaming, SASI and SAI builders: not this path.
- REST (`issues.apache.org/jira/rest/api/2/search`, reachable 2026-11-21 08:05–08:09 EST):
  `text~"calculateIndexingPageSize"` → 3 hits: CASSANDRA-12796; **CASSANDRA-13400** (`/ by zero` when an index is created
  on a table with clustering columns only, Fixed 3.0.13) and **CASSANDRA-13448** (possible divide by 0 in 2i, Duplicate):
  the origin of the `:1164` guard. `text~"indexing page size"` (112 hits, first 30 read by title), `text~"index build" AND
  text~"OutOfMemoryError"` (11), `text~"rebuild_index" AND (OutOfMemoryError OR heap)` (26), `summary~index AND
  summary~OOM` (5): no issue reports the page row count from a table-wide mean, or skew, defeating the 32 MiB target.
- **Verdict: `new`** (related: 12796 known-fixed with a different holder; 13400/13448 fixed the divide-by-zero by adding
  the 10,000-row fallback).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

`CREATE INDEX ks.t_ck ON ks.t (ck)` (legacy index: no `USING`, `default_secondary_index` = `legacy_local_table`,
`Config.java:900-901`, `CreateIndexStatement.java:334-340`; the shipped `cassandra.yaml:2260,2264` leave it commented;
`secondary_indexes_enabled` guardrail ships `true`, `Config.java:891`; only `cassandra_latest.yaml:2220` switches to SAI)
registers the index; its initialization task (`CassandraIndex.java:169-173`, since `isBuilt()` is false and the table is
not empty) runs `buildBlocking` (`:688-716`), which submits **one** `CollatedViewIndexBuilder` over all canonical
sstables to the `SecondaryIndexExecutor` (`CompactionManager.java:1899-1926`, pool of `concurrent_index_builders` = 2,
`:2158`, `Config.java:350`). `build()` computes `pageSize = calculateIndexingPageSize()` **once**
(`CollatedViewIndexBuilder.java:74`) and calls `indexPartition(key, …, pageSize, columns)` for every partition key
(`:82`). An index on a clustering column depends on no regular column, so `extractIndexedColumns` returns all regular
and static columns (`:91-113`): the 1 MiB `v` values are read. `calculateIndexingPageSize()` (`SecondaryIndexManager.java:1149-1170`)
takes `meanPartitionSize = getMeanPartitionSize()` and `meanCells = getMeanEstimatedCellPerPartitionCount()`, both
count-weighted means over every canonical sstable's histograms (`ColumnFamilyStore.java:3110-3134`; each sstable's
`EstimatedHistogram.mean()` is the ceiling of the bucket-offset mean, `EstimatedHistogram.java:235-260`, buckets ≈ ×1.2;
partition-size histogram 155 buckets up to 3.5 TB and cell histogram 118 buckets up to 4.1 G cells,
`MetadataCollector.java:60-70`, so the wide partition does not overflow them), then `meanRowsPerPartition = meanCells /
regularColumns` (int), `meanRowSize = meanPartitionSize / meanRowsPerPartition`, `pageSize = max(1, min(10000, 32 MiB /
meanRowSize))` (`:1167-1170`). `indexPartition` pages the partition with a `SinglePartitionPager` (`:1054`);
`fetchPageUnfiltered` limits the page to `min(pageSize, remaining)` **rows** (`AbstractQueryPager.java:95-101`); the
whole page is copied into an `ImmutableBTreePartition` (`SecondaryIndexManager.java:1066`), every cell value deserialized
into its own heap `byte[]` (`ByteBufferAccessor.java:100-103` → `ByteBufferUtil.read`), and only then fed to the indexers
(`:1090-1132`). With 1,000,000 one-row partitions of ≈ 100 B and one partition of 4,000 rows × 1 MiB, the table mean row
is ≈ 5 KB, `pageSize` ≈ 6,600 ≥ 4,000, so the whole 4.2 GB partition is **one page** on the heap of the build thread.
Nothing else bounds it (§2.2). **Direction: bypass, accounting mismatch** (U > C while the row counter K stays at its own
computed value: *Classification by measurement*, row "U > C, K ≤ C"); technique note: [`bypass-playbook.md`](../../../bypass-playbook.md),
row "Accounting mismatch" (fixed charged quantity — rows — with varying object size). Interpretation: suspected
implementation defect (a per-partition page sized from a per-table mean); the 32 MiB target is not documented as a soft
target with any stated overshoot.

### 2.2 Protection map

| Domain | Holder / allocation and release | Counter (K) | Limit at defaults (contract C) | At the limit | Scope and multiplicity |
|---|---|---|---|---|---|
| **Build page (claimed)** | `ImmutableBTreePartition` of one page (`SecondaryIndexManager.java:1066`): BTree of `BTreeRow` → `BufferCell` → `HeapByteBuffer` → `byte[]` per value; garbage after the page's indexing loop (`:1132`, `partition.close()` at `:1135-1141`); one page live at a time per build | rows per page = `pageSize`, computed once per build from table-wide means (`:1149-1170`), enforced as a row limit (`AbstractQueryPager.java:95-101`); hard row ceiling `DEFAULT_PAGE_SIZE` 10,000 (`:142`) | **32 MiB target per page** (`:1154`, hard-coded), contract taken as ≤ 1.25 × 32 MiB = 40 MiB (histogram bucket error ±20 %; phase-1 stage 4 measured 1.06–1.10 × on uniform rows) | nothing: no byte check anywhere on the path | one per running build task; ≤ `concurrent_index_builders` = 2 node-wide; one task per `CREATE INDEX` / `rebuild_index` |
| Index memtable | index entries written by `CassandraIndex` indexers into the index table's memtable (`heap_buffers`) | memtable pool bytes | `memtable_heap_space` = heap/4 (512 MiB at 2 GiB), flush at cleanup threshold 1/(1 + 2 flush writers) ≈ heap/12 | flush; writers block at the pool limit | per node (pool shared by all tables) |
| Key cache | `CaffeineCache` | weigher bytes | min(5 % heap, 100 MiB) = 100 MiB at 2 GiB (≈ 2.14 × real, B7) | eviction | per node; ≤ a few entries here (two sstables) |
| Write-time size limits (would bound the wide partition) | — | — | `partition_size_warn/fail_threshold` null (`Config.java:910-911`), `column_value_size_*` null (`:916`): **off**; `max_mutation_size` 16 MiB per write (1 MiB rows pass); guardrails also skip superusers (AllowAll default) | n/a | per write |
| Read-size limits | — | — | `local_read_size_*` / `coordinator_read_size_*` null (off); the build's internal read is not a client read | n/a | n/a |
| Heap (budget) | JVM heap | — | `-Xmx` per arm (§2.3) | `OutOfMemoryError: Java heap space` → heap dump (`jvm-server.options:120`) → `kill -9` (`cassandra-env.sh:209`) | process |

U for the claimed domain is the bytes of the page's rows on the heap, measured from the hprof (count × length of
`byte[1048576]`, plus `BTreeRow`/`BufferCell` counts), from the GC log (post-GC heap during the build window) and from
`jcmd GC.heap_info`: none of these read K. K is read separately (§2.6).

### 2.3 Configuration and budget audit

**Constraints at shipped defaults (V6)**, resolved on `ms0640` at each heap: page target 32 MiB and row ceiling 10,000
(hard-coded); `cassandra.force_default_indexing_page_size` unset (false); `concurrent_index_builders` 2;
`default_secondary_index` `legacy_local_table` and `default_secondary_index_enabled` true (**legacy 2i is the default
implementation in the shipped `cassandra.yaml`**); `secondary_indexes_enabled` true; `secondary_indexes_per_table`
guardrail off; `memtable_allocation_type: heap_buffers` (`cassandra.yaml:825`); `memtable_heap_space` unset → heap/4;
`memtable_flush_writers` unset → 2 (one data dir); `key_cache_size` unset → min(5 % heap, 100 MiB);
`partition_size_*`, `column_value_size_*`, `local_read_size_*` null; `commitlog_segment_size: 32MiB` (max mutation
16 MiB); `native_transport_max_frame_size` 16 MiB; `column_index_size` unset (64 KiB) and `column_index_cache_size`
2 KiB; sstable format `big` (`storage_compatibility_mode: CASSANDRA_4`); table defaults (STCS 4/32, LZ4 16 KiB chunks);
`compaction_throughput: 64MiB/s`; `auto_snapshot: true`; `AllowAllAuthenticator`. GC: shipped `jvm11-server.options`
(G1 `:63`, `G1HeapRegionSize=16m` `:66` — so a 1 MiB `byte[]` is **not** humongous, `G1NewSizePercent=50` `:70`,
`MaxGCPauseMillis=300` `:79`); `HeapDumpOnOutOfMemoryError` (shipped); the GC log that `cassandra-env.sh:83-84` adds by
default. Stage 2 records the resolved values from `system.log` and `ps` in each lifetime's `run.meta`.

**Arm-specific settings (only these):** `MAX_HEAP_SIZE` / `MAX_DIRECT_MEMORY_SIZE` (budget); arm I adds the Byteman
agent with the intervention rule (§2.8); arm C sets `nodetool setlogginglevel
org.apache.cassandra.index.SecondaryIndexManager TRACE` after startup (one partition → two TRACE lines). Budget-search
lifetimes after the first at each heap add `-XX:-HeapDumpOnOutOfMemoryError` (instrument, disk; no effect before the
error).

**Environment (disclosed, not capacities):** one-node ring on `127.0.0.1`, `ms0640` (aarch64, 8 cores, 62 GiB RAM,
swap 8 GiB on but kept at 0 for the node with `systemd-run --user --scope -p MemorySwapMax=0`, **no** cgroup
`MemoryMax`); JDK 11.0.33; data, commit log, hints, saved caches, logs and dumps under `/mydata/s4/b20/`;
`CASSANDRA_HEAPDUMP_DIR` = the lifetime's run dir. Data preparation (§2.5) runs at a separate 8 GiB "loader" heap with
`nodetool disableautocompaction ks t` (runtime only, not persisted) and `nodetool setcompactionthroughput 0`, then a
major compaction; no arm runs at those settings.

**Budgets (V7).** What `cassandra-env.sh` resolves on `ms0640` itself (62 GiB RAM): heap 15,872 MiB (the heap_limit
branch), direct 7,936 MiB (record). The design claims nodes of **4–10 GiB RAM**, for which `cassandra-env.sh` resolves
heap = ½ RAM and direct = ¼ RAM: 4 GiB RAM → **2 GiB / 1 GiB** (primary, ideal), 6 GiB → 3 GiB / 1.5 GiB,
8 GiB → 4 GiB / 2 GiB, 10 GiB → 5 GiB / 2.5 GiB. Each arm sets exactly that pair. All heaps ≥ 512 MiB: V7 met by the
standing rule. No container limit is a budget (**no cgroup budget is needed**). The upward search is bounded by the data
that fits on `ms0640` (≈ 18 GiB free on `/mydata`), not by the mechanism: the page grows with the wide partition up to
10,000 rows × row size (rows up to the 16 MiB mutation limit), so a larger partition reaches any heap; stage 2 reports
the largest failing heap **for this 4.2 GB partition**.

### 2.4 Ceiling arithmetic

Contracts at 2 GiB: page ≤ 40 MiB × 2 builders = 80 MiB; index memtable ≤ 512 MiB (flushes at ≈ 170 MiB); key cache
≤ 100 MiB (≈ 214 MiB real); baseline (idle node, two user sstables) ≈ 0.15–0.35 GiB live. Σ ≈ 0.35 + 0.08 + 0.51 + 0.21
≈ **1.15 GiB < 2 GiB**: with every contract honoured, one or two builds cannot exhaust a 2 GiB heap. Measured design
numbers (§2.5 data):

| Quantity | Test dataset T (1,000,000 small + 1 wide) | Control dataset C (wide only) |
|---|---|---|
| Wide partition | 4,000 rows × (1,048,576 B value + ≈ 30 B) = 4,194,424,040 B serialized → bucket 4,966,933,177 | same |
| Small partitions | 1,000,000 × ≈ 90–124 B (1 row, 64 B value) → bucket 103 or 124 | none |
| `meanPartitionSize` | (10^6 × 103 + 4,966,933,177) / (10^6 + 1) ≈ **5,070–5,091 B** | 4,966,933,177 B |
| `meanCells` (cells per row = 1) | two sstables: (10^6 × 1 + 1 × 4,768) / (10^6 + 1) → int **1**; one sstable: ceil(1.0048) = **2** | 4,768 (bucket of 4,000) |
| `meanRowSize` | ≈ 5,070–5,091 B (or half with one sstable) | 1,041,723 B |
| **K = pageSize** | **≈ 6,591–6,618** (10,000 with one sstable); the design needs ≥ 4,000 | **32** |
| Rows of the wide partition per page | min(K, 4,000) = **4,000** (one page) | 32 (125 pages) |
| U: page on heap | 4,000 × (1,048,576 + 16 array header + ≈ 250 B row/cell/buffer objects) ≈ **4.195 GB = 125 × C** | ≈ 33.6 MB ≈ 1.0 × C |

The skew needs ≥ ≈ 760,000 small partitions for K ≥ 4,000 (500,000 give K ≈ 3,343); 1,000,000 keep a 1.6 × margin.

| Heap (-Xmx) | Page 4.195 GB + baseline 0.15–0.35 GB vs heap | Feasible OOM? |
|---|---|---|
| 2 GiB (2.147 GB) | 4.35–4.55 GB ≫ 2.15 GB; the OOM comes at ≈ 1,700–1,950 rows into the page | **yes, certain** |
| 3 GiB (3.221 GB) | ≫ | yes (only run if 4 GiB is 0/3) |
| 4 GiB (4.295 GB) | 4.35–4.55 GB > 4.295 GB (page alone = 97.7 % of the heap) | **yes**, predicted 3/3 |
| 5 GiB (5.369 GB) | 4.35–4.55 GB < 5.37 GB (≈ 0.8 GB headroom; heavy GC likely) | no (boundary) |
| 6 GiB | < | no (only if 5 GiB fails) |

### 2.5 Workload and environment

**Node:** `ms0640` only (checked read-only 2026-11-21 08:04 EST: no Java process, load 0.00, 62 GiB RAM, 60 free,
swap 8 GiB unused, `/mydata` 39 GiB with **18 GiB free** (`/mydata/s2r2` 19 GiB and `/mydata/u1r2` are someone else's:
never touch), `/mydata/s4/cassandra-base` present (469 MB; `build/apache-cassandra-5.0.9-SNAPSHOT.jar`,
`build/lib/jars/byteman-4.0.20.jar`, `tools/bin/sstablemetadata`, bundled Python driver
`lib/cassandra-driver-internal-only-3.29.0.zip`), JDK 11.0.33, Ant, Python 3.10.12, cgroup v2; `/mydata/s4` is owned by
`jason92`, so `/mydata/s4/b20` needs no sudo). Never `ant` in the tree a node runs from. Client on the same node.

**Layout** `/mydata/s4/b20/`: `tree/` (copy of `cassandra-base`, ≈ 0.5 GB), `conf-pristine/`, `pristine-C/` and
`pristine-T/` (stopped-node directories: data, commitlog, hints, saved_caches), `work/` (one lifetime's node directory),
`runs/<label>/` (logs, `run.meta`, samplers, at most one hprof at a time).

**Schema:** `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
`CREATE TABLE ks.t (pk bigint, ck int, v blob, PRIMARY KEY (pk, ck))` (table defaults). Trigger (every arm):
`CREATE INDEX t_ck ON ks.t (ck)` (legacy by default; an index on a clustering column, so the build reads `v`).

**Data preparation (once, ≈ 25 min; loader heap 8 GiB / direct 4 GiB; not a reading):**
1. Start a node on an empty `work/`; schema; `nodetool disableautocompaction ks t`; `nodetool setcompactionthroughput 0`.
2. **Wide partition:** `pk = 0`, `ck = 0..3,999`, `v` = 1,048,576 seeded random bytes (incompressible; distinct per row),
   written with the U9 `writer.py` pattern (bundled driver, protocol **4**, CL ONE, prepared INSERT, ≤ 16 in flight,
   `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`). `nodetool flush ks t`; `nodetool compact ks t` (major → one
   sstable W, ≈ 4.2 GB); `SELECT count(*) FROM ks.t WHERE pk = 0` = 4,000; `nodetool drain`; stop. Copy `work/` →
   `pristine-C/` (real copy for every file except W's `*-Data.db`, which is **hard-linked**; sstables are immutable, a
   lifetime only adds files).
3. **Small partitions:** restart on `work/` (same loader settings); write `pk = 1..1,000,000`, `ck = pk mod 4,000`,
   `v` = 64 random bytes (execute_concurrent, ≈ 100 in flight); `nodetool flush ks t` once at the end (one sstable S,
   ≈ 0.1 GB; if the memtable flushed earlier, S may be 2–3 sstables, record); count check `SELECT count(*) FROM ks.t` is
   **not** run (1 M scan); instead `nodetool tablestats ks.t` (estimated partitions ≈ 1,000,001) and `sstablemetadata`.
   Record `token(0)` and the rank of `pk = 0` in token order (`SELECT count(*) FROM ks.t WHERE token(pk) < token(0)` is
   allowed here, at the loader heap, once). `nodetool drain`; stop. `work/` → `pristine-T/` (rename; W's Data.db is the
   same inode as in `pristine-C/`).
4. **Offline K (first-trigger check, before any arm):** run `tools/bin/sstablemetadata` on every `ks/t-*` Data.db of each
   pristine set; `kcalc.py` re-implements `ColumnFamilyStore.java:3110-3134` and `SecondaryIndexManager.java:1149-1170`
   from the printed partition-size and cell-count histograms (bucket offsets, per-sstable ceil mean, int casts) and prints
   K_T and K_C. **Stop the T arms if K_T < 4,000** (premise fails; report). Expected K_T ≈ 6,600 (10,000 if S and W share
   one sstable), K_C = 32.
5. Disk: prep peak ≈ W fragments 4.2 + major-compaction output 4.2 + commit log ≤ 1.5 ≈ 10 GB (of 18); steady state
   ≈ 4.4 GB (W once + S + tree) + one lifetime (hard-linked W, ≤ 0.3 GB of new files) + one hprof (≤ 2.2 GB at 2 GiB,
   ≤ 4.3 GB at 4 GiB). Delete each hprof after parsing.

**Lifetime (one run, clean start):** `rm -rf work/`; copy the arm's pristine set into `work/` (hard link W's Data.db,
copy the rest); start the node with the arm's heap/direct (and agent for I) under `systemd-run --user --scope -p
MemorySwapMax=0`, launched `( setsid nohup … < /dev/null > … 2>&1 & )`; wait for `Starting listening for CQL clients`;
check `nodetool compactionstats` shows 0 pending/active (no compaction overlaps the build: W and S are in different STCS
size buckets, C has one sstable); start samplers; 30 s idle; baseline (`jcmd <pid> GC.heap_info` and one
`jcmd <pid> GC.class_histogram` — a full GC **before** the trigger, symmetric in every arm); arm C: set TRACE; issue
`CREATE INDEX t_ck ON ks.t (ck)` (cqlsh, protocol 4; the statement returns once the schema change is applied; the build
runs asynchronously); detect the endpoint (§2.6 item 6); stop the JVM by PID; copy small files to `runs/<label>/`; parse
the hprof if any, then delete it. Interleave arms (T, C, I, T, C, I, …) so node drift does not align with an arm.

**Run matrix (priority order):**

| Pri | Label | Arm | Heap / direct | Dataset | Runs | Predicted endpoint |
|---|---|---|---|---|---|---|
| 0 | `SHAKE` | C with TRACE, harness check | 2G / 1024M | pristine-C | 1 (not a reading) | build completes; `Calculated page size 32` |
| 1 | `T2-1..3` | T (test) | 2G / 1024M | pristine-T | 3 | heap OOM in the build thread on the first page of `pk = 0` |
| 1 | `C2-1..3` | C (matched control) | 2G / 1024M | pristine-C | 3 | none; build completes, K = 32, 125 pages |
| 1 | `I2-1..3` | I (intervention) | 2G / 1024M + Byteman | pristine-T | 3 | none; build completes; Byteman shows original K_T and returns 32 |
| 2 | `T4-1..3` | T | 4G / 2048M | pristine-T | 3 (hprof only in T4-1) | heap OOM, 3/3 (2/3 acceptable) |
| 2 | `T3-1..3` | T | 3G / 1536M | pristine-T | 3, **only if T4 is 0/3** | heap OOM |
| 3 | `T5-1..3` | T (boundary) | 5G / 2560M | pristine-T | 3 (no hprof) | no OOM: build completes (heavy GC) |
| 3 | `T6-1` | T | 6G / 3072M | pristine-T | 1, **only if T5 ≥ 1/3 OOM** | no OOM |

### 2.6 Instruments (U independent of K)

**K (the control's counter, rows per page):**
1. Offline exact `kcalc.py` per dataset (§2.5 step 4) — no runtime instrumentation in T arms.
2. Arm C: the `Calculated page size {} for indexing ks.t (meanPartitionSize/meanCells/meanRowsPerPartition/meanRowSize)`
   TRACE line (`SecondaryIndexManager.java:1172`) in `debug.log`.
3. Arm I: the Byteman rule prints the original return value `$!` (= K_T computed by the running node on the T data) and
   the value returned (32) to a trace file (`traceOpen`/`traceln`; `CassandraDaemon` closes stdout).

**U (independent of K):**
1. **hprof at the OOM** (shipped `HeapDumpOnOutOfMemoryError`, T2-1..3 and T4-1): `hprofhist.py` (copy from
   `../big-row-index-buffer--64KiB-clustering-wide-partition/harness/`, add buckets "byte[] of length 1,048,576: count,
   total", and counts of `BTreeRow`, `BufferCell`, `HeapByteBuffer`): predicted ≈ 1,700–1,950 arrays of 1 MiB at 2 GiB
   (≥ 1.78 GB, ≥ 83 % of the heap), ≈ 3,800–4,000 at 4 GiB, and as many rows/cells — a size no other holder on this node
   has (small rows carry 64 B; index entries carry no `v`). `hprofstacks.py` (same source): the stack of the
   `SecondaryIndexExecutor` thread.
2. **GC log** (cassandra-env default, `heap*=trace`): post-GC heap after each pause during the build window, full-GC
   count, and the last pause before the error. T: climbs to ≈ the heap; C and I: stays ≤ baseline + 150 MB (C) / + 400 MB
   (I, index memtable of 1 M entries included).
3. **`jcmd <pid> GC.heap_info` every 2 s** (a safepoint, no GC) and `RssAnon` every 2 s.
4. **Progress:** `nodetool compactionstats` every 3 s ("Secondary index build", bytes read / total) and `system.log` lines
   `Submitting index build of t_ck`, `Index build of t_ck complete`. The OOM's position in the build = bytes read at the
   last sample (lower bound) and the rank of `pk = 0` (§2.5 step 3).
5. **Initiating failure (V5):** the first `java.lang.OutOfMemoryError` in `stdout`/`system.log` if any (the shipped
   `-XX:OnOutOfMemoryError="kill -9 %p"` kills the JVM right after the dump, so Cassandra's own handler usually does not log:
   as in U9 amendment A3, the thread and stack come from the hprof), the hprof's thread stacks, and the GC log. Expected
   frames on `SecondaryIndexExecutor:1`: `ByteBufferUtil.read` ← `ByteBufferAccessor.read` ← `Cell$Serializer.deserialize`
   ← `UnfilteredSerializer.readSimpleColumn`/`deserializeRowBody` ← … ← `ImmutableBTreePartition.create` ←
   `SecondaryIndexManager.indexPartition` ← `CollatedViewIndexBuilder.build` ← `CompactionManager$…run`.
6. **Endpoint detection:** poll every 2 s for `java.lang.OutOfMemoryError` in `stdout`/`system.log`, for the JVM PID's
   exit, and for `Index build of t_ck complete`. On an OOM, wait until the hprof size is stable for 10 s (≤ 5 min), then
   make sure the PID is gone (SIGKILL). On completion: wait 10 s, read one more `GC.heap_info`, check a sample of useful
   work (`SELECT count(*) FROM ks.t WHERE ck = 1` = 1 + 250 = **251** on T data, **1** on C data), `nodetool drain`,
   SIGTERM, SIGKILL after 30 s.

Overhead: two `jcmd` and one `nodetool` call per 2–3 s; no Byteman, patch or forced GC after the trigger in T and C
arms (one class histogram before the trigger), so T and C stay `deployment`. Arm I carries Byteman by construction.

### 2.7 Predicted response and stopping budget

- **T2 (claimed endpoint):** 3/3 `OutOfMemoryError: Java heap space` within ≤ 60 s of the build reaching `pk = 0`;
  hprof: ≈ 1,700–1,950 `byte[1048576]` (≥ 83 % of the heap) with as many `BTreeRow`/`BufferCell`; OOM thread
  `SecondaryIndexExecutor:1` in the §2.6 frames (≥ 2/3; if another thread throws first, the dump must still show the
  holder); `Index build of t_ck complete` never appears. K_T (offline, and from I's Byteman) ≈ 6,600 ≥ 4,000.
  Classification: U ≈ 1.8 GB at the failure (and 4.195 GB were requested) against C = 40 MiB (≥ 45 ×), K = K_T within its
  own 10,000-row ceiling → **bypass, accounting mismatch**.
- **C2:** 0/3 OOM; `Calculated page size 32`; build completes in ≤ 5 min; post-GC heap ≤ baseline + 150 MB.
- **I2:** 0/3 OOM; Byteman `original=` ≈ 6,600 (= K_T), `returned=32`; build completes; `ck = 1` count 251; build time
  ≤ 2 × the T arm's pace before `pk = 0` plus 125 pages (useful work kept, not a rejection).
- **T4:** 3/3 OOM (≥ 2/3 accepted as "OOM at 4 GiB"); hprof T4-1 ≈ 3,800–4,000 arrays. **T5:** 0/3 (boundary).
  **Largest failing heap predicted: 4 GiB** for a 4.2 GB partition.
- **Refuting readings:** K_T < 4,000 (premise wrong; stop T arms); T2 completes the build at 2 GiB (claim wrong at this
  size; record U from the GC log); an OOM whose dump lacks the 1 MiB arrays (not the claimed holder → retry); a C2 OOM
  (control fails → attribution lost → retry); I2 OOM (the page is not the cause → retry).
- **Stopping budget:** per lifetime ≤ 15 min (start ≤ 3 min, build endpoint ≤ 8 min after `CREATE INDEX`, dump ≤ 5 min;
  a lifetime that hits the limit is stopped and recorded as "no endpoint, timeout"). No escalation after an OOM beyond the
  matrix.

**Time plan (EST, 2026-11-21):**

| Window | Work |
|---|---|
| 09:00–09:30 | check the freeze hash and the node; `/mydata/s4/b20/`; copy `tree/`, `conf-pristine/`; adapt U9's harness (§2.9) |
| 09:30–09:55 | data preparation (§2.5 steps 1–5), `kcalc.py`; **stop T arms if K_T < 4,000** |
| 09:55–10:05 | `SHAKE` |
| 10:05–11:05 | priority 1: T2/C2/I2 interleaved ×3 (T ≈ 9 min with hprof parse, C ≈ 4 min, I ≈ 6 min) |
| 11:05–11:50 | priority 2: T4 ×3 (T4-1 ≈ 15 min with a 4.3 GB hprof; T4-2/3 ≈ 6 min); T3 ×3 only if T4 is 0/3 |
| 11:50–12:40 | priority 3: T5 ×3 (≈ 7 min each); T6-1 only if T5 fails |
| 12:40–13:15 | slack; **no lifetime starts after 13:15** |
| 13:15–14:00 | stop everything, check no `CassandraDaemon` runs, write §3–§4, write back; **case file done by 14:00** |

**Drop order if behind:** (1) T6-1; (2) T5-2/T5-3 (report T5 n/1); (3) T4-1's hprof parse (keep the file listing and
the GC log; delete the dump); (4) T4-2/T4-3 (report T4 n/1); (5) hprof parsing of T2-2/T2-3 (keep their GC logs and
first-error lines; T2-1's dump parse is the minimum V5 evidence). Never dropped: T2, C2, I2 × 3.

### 2.8 Controls and intervention

- **Matched control C2 (×3)** (V2; bypass "protected path"): same node, build, heap, schema, index statement, and the
  **same wide partition** (the same W sstable inode), same build path; only the 1,000,000 small partitions (the skew) are
  absent, so the table mean equals the wide rows' size and the 32 MiB target binds (K = 32, ≈ 33.6 MB pages). It shows the
  control works on the protected path and that reading the 4.2 GB partition through the build is not itself an OOM.
- **Intervention I2 (×3)** (V4): T data and T heap, plus one Byteman rule that bounds the page to what the 32 MiB target
  gives for this partition's own rows (the restored per-partition byte bound; a diagnostic, saved as
  `harness/b20-intervention.btm`; the unmodified build is what T runs):

  ```
  RULE b20 intervention: bound the index-build page to the 32 MiB target for 1 MiB rows
  CLASS org.apache.cassandra.index.SecondaryIndexManager
  METHOD calculateIndexingPageSize
  AT EXIT
  IF $! > 32
  DO traceOpen("b20", "<run dir>/btm.txt"); traceln("b20", "B20I original=" + $! + " returned=32"); return 32
  ENDRULE
  ```

  Loaded with `-javaagent:tree/build/lib/jars/byteman-4.0.20.jar=script:<rule>` in `JVM_EXTRA_OPTS` (no listener; type-
  check with Byteman's `bmcheck`/`TestScript` first). Useful work is checked (`ck = 1` count 251, build complete, build
  time recorded), so a stopped build cannot pass as protection.
- **Not done:** a patched byte-bounded pager (the rule isolates the page-size choice without a rebuild); the `:1164`
  zero-regular-column path (stage 4 already measured it; weaker); two concurrent builds (one page already exceeds the
  budget); `nodetool rebuild_index` (same builder; not needed).

### 2.9 Harness (to build in stage 2 under `harness/`)

Adapt U9's verified scripts (`../big-row-index-buffer--64KiB-clustering-wide-partition/harness/`): `setup.sh` (root
`/mydata/s4/b20`, `tree/` copy, pristine conf), `victim-ctl.sh` (start with `MAX_HEAP_SIZE`, `MAX_DIRECT_MEMORY_SIZE`,
`CASSANDRA_HEAPDUMP_DIR`, `CASSANDRA_LOG_DIR=<run>/logs`, `JVM_EXTRA_OPTS` for the I agent or
`-XX:-HeapDumpOnOutOfMemoryError`; `systemd-run --user --scope -p MemorySwapMax=0`; `run.meta` with label, arm, heap,
direct, jar sha256, resolved `-Xmx`/`-XX:MaxDirectMemorySize` from `ps`, yaml diff (directories only)), `writer.py`
(wide rows and small rows, §2.5), `prep.sh` (§2.5 steps 1–4), `kcalc.py` (offline K), `run-arm.sh <label> <T|C|I>
<heap> <direct>` (refuse if a `java` `CassandraDaemon` runs; lifetime of §2.5; endpoint detection matching
`java.lang.OutOfMemoryError`, not the JVM argument `OnOutOfMemoryError`), `summarize.py` (one line per lifetime: arm,
heap, K source and value, outcome, bytes read at the endpoint, first OOM thread and top frames, `byte[1048576]`
count/total, peak post-GC heap, baseline, build time, `ck = 1` count), `hprofhist.py`, `hprofstacks.py`, `gcwin.py`
(copied), `b20-intervention.btm`. Run each lifetime as a background job and poll with bounded waits; kill by PID.
Cleanup at the end: no `CassandraDaemon`, `work/` and hprofs deleted; `pristine-*` and `tree/` may stay (say so) or be
removed if the session needs the disk.

`sha256 of §1–§2 at freeze: bf85f027169156f62f7c833a7154439645fe40c4cba964448087f931432de357` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.

**Amendments after the freeze** (2026-11-21, stage 2; prep checks only, each made before any arm reading):

- **A1 (08:25 EST), §2.5 step 2 count check.** `SELECT count(*) FROM ks.t WHERE pk = 0` timed out at the shipped 5 s read
  timeout (a count over 4,000 rows of 1 MiB). Replaced by `sstablemetadata` of W: `totalRows: 4000`, `Covered
  clusterings: [0, 3999]`, one partition (`logs/prep/meta-W.txt`). Reason: the step cannot run as written at defaults.
- **A2 (08:30 EST), §2.5 step 3 rank of `pk = 0`.** Both `SELECT token(pk) … WHERE pk = 0` and the `count(*) … token(pk) <
  token(0)` query timed out (each reads the wide partition). Computed offline instead (`harness/rank.py`, the bundled
  driver's Murmur3 of the 8-byte key): `token(0)` = 2945182322382062539, equal to W's `First token`; **660,162 of the
  1,000,000 small partitions precede `pk = 0`** in token order (66.0 %), so the build meets the wide partition after
  ≈ 2/3 of the small ones.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session (Claude Opus 5.5, `claude-opus-5-5`), 2026-11-21 08:15–09:50 EST. Freeze hash checked
before anything ran: `bf85f027…de357` recomputed equal.

### 3.1 Environment

- **Node `ms0640`** (Utah m400, aarch64, 8 cores, 62 GiB RAM, swap 8 GiB on, cgroup v2), checked 08:16 EST: no Java
  process, load 0.00, `/mydata` 18 GiB free; `/mydata/s2r2` and `/mydata/u1r2` not touched. JDK 11.0.33 (OpenJDK
  11.0.33+9 Ubuntu). One measured node at a time; client (Python driver, cqlsh) on the same node.
- **Build:** `/mydata/s4/b20/tree` = a copy of `/mydata/s4/cassandra-base`; `apache-cassandra-5.0.9-SNAPSHOT.jar`
  sha256 `2a9cbd5c…c26712` (every `run.meta`). Unmodified; arm I adds only the Byteman agent
  (`byteman-4.0.20.jar`, rule `harness/b20-intervention.btm`, type-checked with `TestScript`: no errors).
- **Configuration:** shipped `cassandra.yaml`; the diff of every lifetime is the five directory lines only
  (`logs/*/yaml.diff`). Resolved and logged (`logs/*/run.meta`): `concurrent_index_builders=2`,
  `default_secondary_index=legacy_local_table`, `default_secondary_index_enabled=true`, `secondary_indexes_enabled=true`,
  `memtable_allocation_type=heap_buffers`, `memtable_heap_space` unset → 512 MiB at 2 GiB (1,024 / 1,280 MiB at 4 / 5 GiB),
  `key_cache_size` unset, `column_index_size` unset, `partition_size_fail_threshold=null`, `auto_snapshot=true`.
  Shipped `jvm11-server.options`: G1, `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`,
  `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError=kill -9 %p`; GC log from `cassandra-env.sh`.
- **Budgets (resolved from `ps`, `run.meta`):** `-Xmx2G` / `MaxDirectMemorySize=1024M` (T2, C2, I2, SHAKE), `-Xmx4G` /
  `2048M` (T4), `-Xmx5G` / `2560M` (T5); `systemd-run --user --scope -p MemorySwapMax=0`, no `MemoryMax`. T4-2/3 and
  T5-1..3 add `-XX:-HeapDumpOnOutOfMemoryError` (design §2.3). What `cassandra-env.sh` would resolve on `ms0640`
  itself: 15,872 MiB heap / 7,936 MiB direct (not used; the claimed nodes are 4–10 GiB RAM, §2.3).
- **Data (§2.5, loader heap 8 GiB, not a reading; `logs/prep/prep.log`):** W = `nb-8-big-Data.db`, 4,213,328,198 B, one
  partition `pk = 0`, 4,000 rows × 1 MiB (major compaction of 7 flushed fragments; 16 of the 4,000 writes returned
  `WriteTimeout` at CL ONE but were applied: `totalRows 4000`, A1). S = `nb-9-big-Data.db`, 83,852,076 B, 1,000,000
  one-row partitions (all 1,000,000 writes ok; one flush). Pristine sets: `pristine-C` (W only) and `pristine-T`
  (W + S), W one inode hard-linked into both (`ls -li`: inode 289091, 2 links); every lifetime cloned its set into
  `work/` (`harness/clone.sh`: W hard-linked, every other file copied) and deleted `work/` at the end.
- **Offline K (§2.5 step 4, `harness/kcalc.py`, `logs/prep/kcalc-*.txt`):** histograms exactly as §2.4 predicted —
  W: partition-size bucket 4,966,933,177, cell bucket 4,768; S: partition-size bucket 103 × 1,000,000, cells 1 ×
  1,000,000. **K_T = 6,618** (meanPartitionSize 5,069.93, meanCells 1, meanRowSize 5,069.93 B) ≥ 4,000: the premise
  holds, the T arms run. **K_C = 32.**
- **Harness** (`harness/`): `victim-ctl.sh`, `prep.sh`, `clone.sh`, `writer.py`, `kcalc.py`, `rank.py`, `run-arm.sh`,
  `batch.sh`, `summarize.py`, `table.py`, `hprofhist.py` (U9's, plus the `B20 byte[1048576]` line and `BTreeRow` /
  `HeapByteBuffer` / `ImmutableBTreePartition` counts), `hprofstacks.py`, `gcwin.py` (U9's), `b20-intervention.btm`.
  Trigger: `bin/cqlsh --protocol-version=4 -e "CREATE INDEX t_ck ON ks.t (ck)"` (rc 0 in every lifetime).
- **Logs:** full logs on `ms0640:/mydata/s4/b20/runs/<label>/` (system/debug/gc logs, stdout, `heap.csv`, `cstats.log`,
  `result.txt`, `summary.txt`); excerpts in `logs/<label>/` (summary, run.meta, yaml.diff, gcwin, GC tail, OOM lines,
  hprof histogram and stacks, Byteman trace), the one-line table `logs/runs-table.txt`, and `logs/prep/`.

### 3.2 Runs (in order; interleaved T, C, I as designed)

| Label | Arm | Heap / direct | Start (EST) | Outcome | Trigger → endpoint | K (source) | Live / heap at the endpoint | 1 MiB arrays in the hprof | Useful work |
|---|---|---|---|---|---|---|---|---|---|
| SHAKE | C (check) | 2G / 1024M | 08:31 | build complete | build 12.0 s | 32 (TRACE) | max post-GC 94 MiB | — | `ck = 1` → 1 |
| T2-1 | T | 2G / 1024M | 08:33 | **heap OOM** | 178.8 s | 6,618 (offline) | last Full GCs 1,938 → 1,938 MiB of 2,048 | **1,666 (1.747 GB)** | — |
| C2-1 | C | 2G / 1024M | 08:38 | build complete | build 12.5 s | 32 (TRACE) | max post-GC 71 MiB | — | 1 |
| I2-1 | I | 2G / 1024M + Byteman | 08:40 | build complete | build 267.1 s | `original=6618 returned=32` | max post-GC 460 MiB | — | **251** |
| T2-2 | T | 2G / 1024M | 08:46 | **heap OOM** | 176.7 s | 6,618 | 1,940 → 1,940 MiB | **1,668 (1.749 GB)** | — |
| C2-2 | C | 2G / 1024M | 08:52 | build complete | build 11.8 s | 32 | 91 MiB | — | 1 |
| I2-2 | I | 2G / 1024M + Byteman | 08:53 | build complete | build 274.0 s | `original=6618 returned=32` | 468 MiB | — | 251 |
| T2-3 | T | 2G / 1024M | 08:59 | **heap OOM** | 174.6 s | 6,618 | 1,937 → 1,937 MiB | **1,665 (1.746 GB)** | — |
| C2-3 | C | 2G / 1024M | 09:05 | build complete | build 11.9 s | 32 | 85 MiB | — | 1 |
| I2-3 | I | 2G / 1024M + Byteman | 09:06 | build complete | build 271.6 s | `original=6618 returned=32` | 467 MiB | — | 251 |
| T4-1 | T | 4G / 2048M | 09:12 | **heap OOM** | 187.0 s | 6,618 | 3,859 → 3,859 MiB of 4,096 | **3,586 (3.760 GB)** | — |
| T4-2 | T | 4G / 2048M, no dump | 09:18 | **heap OOM** | 180.7 s | 6,618 | 3,855 → 3,855 MiB | (no dump) | — |
| T4-3 | T | 4G / 2048M, no dump | 09:22 | **heap OOM** | 186.9 s | 6,618 | 3,856 → 3,856 MiB | (no dump) | — |
| T5-1 | T | 5G / 2560M, no dump | 09:27 | build complete | build 269.5 s | 6,618 | young GC 5,049 → 5,049 MiB of 5,120, then Full GC → 293 MiB | — | 251 |
| T5-2 | T | 5G / 2560M, no dump | 09:33 | build complete | build 265.9 s | 6,618 | 5,048 → 5,048, then Full → ≈ 0.3 GiB | — | 251 |
| T5-3 | T | 5G / 2560M, no dump | 09:39 | build complete | build 271.1 s | 6,618 | 5,048 → 5,048, then Full → ≈ 0.3 GiB | — | 251 |

Not run, by the matrix's own conditions: **T3** (only if T4 were 0/3; it was 3/3) and **T6-1** (only if T5 ≥ 1/3; it
was 0/3). Nothing dropped; the matrix finished at 09:45 EST.

**Readings common to every lifetime.** Live heap before the trigger (class histogram total, after its full GC):
57.1–57.4 MiB (`baseline_histo_total` 59.86–60.14 MB); `GC.heap_info` "used" before the trigger 281–425 MiB (includes
garbage). No compaction active or pending at the trigger (`pre_compactionstats`). No `OutOfMemoryError` in any C, I or T5
log. RssAnon peaks: 2.48–2.53 GiB at 2 GiB heaps, 4.65 GiB at 4 GiB, 5.71–5.73 GiB at 5 GiB (no swap: `MemorySwapMax=0`).

**T arms at 2 GiB (V1, V3, V5).** All three: `java.lang.OutOfMemoryError: Java heap space` in `stdout.log` (HotSpot's
line, then `Dumping heap to …`, `Heap dump file created [2,183,302,297 bytes …]`, then the shipped `kill -9`;
`logs/T2-*/stdout-oom.txt`); `Index build of t_ck complete` never appears; 174.6–178.8 s after the trigger. GC: 7–21
Full GCs in the last ≈ 40 s (`G1 Evacuation Pause` Full GCs 1,937–1,940 → same; `logs/T2-*/gc-tail.txt`); service-loss
criterion not met (max 13–35 % STW over 60 s) — the endpoint is the OOM. **hprof (all three parsed, then deleted):** 2.18 GB
dumps, total shallow 1,999–2,005 MiB of which **`byte[1048576]` 1,665–1,668 arrays = 1,665–1,668 MiB (81 % of the heap,
83 % of the live dump)**; one `ImmutableBTreePartition`; `BufferCell` 1,596; the rest is the index memtable
(≈ 661 k `BTreeRow` / `BufferClustering` / `LivenessInfo`, ≈ 0.13 GiB: the 660,162 index entries written before
`pk = 0`) and the key cache (660,189 `KeyCacheKey` + Caffeine nodes + `RowIndexEntry`, ≈ 0.13 GiB). **Stack of the
throwing thread** (the only trace with `OutOfMemoryError.<init>`, identical in all three dumps, `logs/T2-*/hprofstacks.txt`):
`OutOfMemoryError.<init>` ← `ByteArrayAccessor.read(ByteArrayAccessor.java:102)` ← `AbstractType.read:599` ←
`Cell$Serializer.deserialize(Cell.java:339)` ← `UnfilteredSerializer.readSimpleColumn:652` ← `deserializeRowBody:613` ←
`UnfilteredDeserializer.readNext:143` ← `SSTableIterator$ForwardIndexedReader.computeNext:174` ← … ←
`UnfilteredRowIterators$UnfilteredRowMergeIterator.computeNext:525` ← `AbstractBTreePartition.build:314` ←
`ImmutableBTreePartition.create:114/97/66` ← **`SecondaryIndexManager.indexPartition:1066`** ←
**`CollatedViewIndexBuilder.build:82`**. (The design expected `ByteBufferAccessor`; the reader uses the `byte[]`
accessor — same allocation, one `byte[1048576]` per cell value.)

**T arms at 4 GiB.** 3/3 heap OOM, 180.7–187.0 s, last Full GCs 3,855–3,859 MiB of 4,096 MiB. T4-1's 4.20 GB dump:
**3,586 arrays of 1 MiB = 3.760 GB** (88 % of the heap, 91 % of the live dump), total shallow 3,925 MiB, same stack. T4-2/3: HotSpot's `#
java.lang.OutOfMemoryError: Java heap space` / `OnOutOfMemoryError` lines (no dump by design).

**T arms at 5 GiB (boundary).** 0/3 OOM: the build completes in 265.9–271.6 s and `ck = 1` returns 251. The whole page
is held at once: in each run one young GC finds 5,048–5,049 MiB of 5,120 MiB live (`5049M->5049M`), and the next Full GC
(once the page has been indexed and dropped) falls to ≈ 0.29–0.3 GiB (`logs/T5-*/gc-tail.txt`). The 4.19 GB page plus
≈ 0.3–0.5 GiB of other live data fits 5 GiB with ≈ 70 MiB to spare.

**C arms (V2).** 3/3 build complete in 11.8–12.5 s; TRACE `Calculated page size 32 for indexing ks.t
(4.966933177E9/4768/4768/1041722.5622902685)` (`logs/C2-*/summary.txt`); max post-GC heap after the trigger 71–91 MiB
(baseline live 57 MiB; one 32-row page ≈ 33.6 MB): the 32 MiB target binds on the protected path and reading the same
4.2 GB partition through the same builder is not an OOM.

**I arms (V4).** 3/3 build complete in 267.1–274.0 s; Byteman `B20I original=6618 returned=32` once per build (the
running node computed K_T = 6,618 on the T data, equal to the offline value); `ck = 1` → **251** (useful work: the
1,000,000 small partitions and all 125 pages of the wide one were indexed); max post-GC 460–468 MiB (index memtable and key
cache, as in the T dumps); no Full GC after the trigger. Same data, heap and build as T2: only the page row count changed.

### 3.3 Deviations

- First prep attempt (08:19) hung: `prep.sh` piped `victim-ctl.sh start` into `tee`, whose pipe the detached node
  inherited. The loader node was stopped before any data was written (`runs/prep-aborted1/`, `runs/PREP-W-aborted1/` on
  the node); `prep.sh` fixed to redirect to a file and rerun at 08:21. No reading affected.
- A1, A2 above (prep checks that could not run at the 5 s read timeout).
- The `nodetool compactionstats` "Secondary index build" byte counter is not a usable position for the OOM: in T2-1 its last
  sample read 66.7 MB of 4,295 MB (1.6 %) at t + 169 s. The position comes from A2 (pk = 0 after 660,162 small partitions)
  and from the dump (the 1 MiB arrays of the wide partition's first page).
- Design §2.6 U2 predicted C's post-GC ≤ baseline + 150 MB and I's ≤ baseline + 400 MB against the `GC.heap_info`
  baseline; against the live baseline (57 MiB) C is + 14–34 MiB and I + 403–411 MiB (the index memtable of 1 M entries plus
  the key cache): within the stated tolerance for C, ≈ at it for I. Neither arm approaches the heap.
- Predicted page fill at the OOM: 1,700–1,950 arrays at 2 GiB (read 1,665–1,668) and 3,800–4,000 at 4 GiB (read 3,586):
  the other live data (index memtable, key cache) was ≈ 0.26 GiB, at the top of the baseline range assumed.
- hprofs deleted after parsing (T2-1..3, T4-1), as designed. No other deviation.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status (detail): **`verified-OOM · deployment`** — bypass, accounting mismatch
(U > C, K within its own ceiling); interpretation: suspected implementation defect (JIRA: new).

| Condition | Result |
|---|---|
| T at 2 GiB heap / 1 GiB direct (claimed endpoint) | heap OOM **3/3** in the index-build thread |
| C at 2 GiB (same wide partition, no skew) | 0/3; K = 32, build 12 s, post-GC ≤ 91 MiB |
| I at 2 GiB (T data, page bounded to 32 rows by Byteman) | 0/3; build 267–274 s, 251 rows found |
| T at 4 GiB / 2 GiB | heap OOM **3/3** (largest failing heap for this 4.2 GB partition) |
| T at 5 GiB / 2.5 GiB | 0/3 (boundary: the whole 4.19 GB page fits with ≈ 70 MiB to spare) |

| | Evidence |
|---|---|
| V1 Repetition | T2-1..3: 3/3 heap OOM from clean starts (and T4-1..3: 3/3) |
| V2 Matched control | C2-1..3: 0/3, same node, build, heap, schema, statement and W inode; only the skew is absent |
| V3 Measurement | U from the hprof (1,665–1,668 `byte[1048576]` = 1.746–1.749 GB at the failure; 3.760 GB at 4 GiB) and the GC log (1,937–1,940 MiB live of 2,048), independent of K; K from `kcalc.py` (6,618) and the running node via Byteman (6,618, 3/3) |
| V4 Intervention | I2-1..3: 0/3 with useful work kept (build complete, `ck = 1` → 251, ≈ 270 s) |
| V5 Initiating failure | first error `java.lang.OutOfMemoryError: Java heap space` (stdout, 3/3); throwing thread's stack `ByteArrayAccessor.read` ← … ← `ImmutableBTreePartition.create` ← `SecondaryIndexManager.indexPartition:1066` ← `CollatedViewIndexBuilder.build:82`; dump holder = the page's 1 MiB values (81 % of the heap) |
| V6 Default constraints | page target and 10,000-row ceiling hard-coded; `force_default_indexing_page_size` unset; `concurrent_index_builders` 2; legacy 2i default; memtable, key cache, size guardrails at shipped defaults; yaml diff = directories only |
| V7 Acceptable budget | 2 GiB heap / 1 GiB direct (ideal; `cassandra-env.sh` for a 4 GiB-RAM node) and 4 GiB / 2 GiB (8 GiB-RAM node): ≥ 512 MiB, standing rule |

**Reason.** On a table of 1,000,000 one-row partitions (≈ 100 B) plus one partition of 4,000 rows × 1 MiB, the legacy
secondary-index build sized its page once from the table-wide mean row: the node computed K = 6,618 rows (offline
`kcalc.py` and Byteman agree), so the 4,000-row wide partition became a single page that `indexPartition` copies whole
into an `ImmutableBTreePartition`. On a 2 GiB heap the build died 3/3 with `OutOfMemoryError: Java heap space` in that
copy (`SecondaryIndexManager.indexPartition:1066`), the dumps holding 1,665–1,668 values of 1 MiB = 1.75 GB (81 % of the
heap) against a page contract of 32 MiB (≤ 40 MiB with histogram error): U is ≈ 42–52 × C while the row counter K stayed
within its own 10,000-row ceiling. On a 4 GiB heap it failed 3/3 with 3,586 values (3.76 GB, ≈ 90–112 × C); at 5 GiB the
full 4.19 GB page fit (0/3, 5,048–5,049 MiB of 5,120 MiB live). The matched control on the same wide partition without
the skew computed K = 32, built in 12 s and never exceeded 91 MiB post-GC (0/3); bounding the page to 32 rows on the
skewed data (Byteman, `original=6618 returned=32`) removed the OOM 0/3 while indexing everything (251 matches). Every
constraint was at its shipped default and both failing budgets meet V7, so the case is `verified-OOM · deployment`. The
failure grows with the wide partition (up to 10,000 rows × row size per page), so a larger partition reaches any heap;
the boundary reported here (fails at 4 GiB, survives at 5 GiB) holds for this 4.2 GB partition only.

**Limits of attribution.** One node, one data shape (two sstables, one major-compacted wide partition); the skew needs
≥ ≈ 760,000 small partitions per wide one of this size (§2.4). Arm I changes the page row count through Byteman (diagnostic),
not a patched byte-bounded pager. The `:1164` zero-regular-column path, `force_default_indexing_page_size` and two
concurrent builds were not run (§1, §2.8). The OOM is reached through `CREATE INDEX`; `nodetool rebuild_index` uses the
same builder but was not run.

**What is left on `ms0640`:** `/mydata/s4/b20/` ≈ 0.52 GB — `tree/` (469 MB build copy), `runs/` (53 MB of logs),
`harness/`, `conf-pristine/`, `btm/`; `work/`, `pristine-C/`, `pristine-T/` (4.3 GB) and every hprof deleted; no
Cassandra or harness process running (checked 09:46 EST).
