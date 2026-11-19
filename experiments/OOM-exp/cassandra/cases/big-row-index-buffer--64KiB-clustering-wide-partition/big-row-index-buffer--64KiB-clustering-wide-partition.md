# U9 — BIG row-index buffer: 64 KiB clustering keys make a wide partition's index twice its data on the writer's heap  <!-- file: cassandra/cases/big-row-index-buffer--64KiB-clustering-wide-partition/big-row-index-buffer--64KiB-clustering-wide-partition.md -->

| Field | Value |
|---|---|
| Case ID | `U9` (U = unprotected accumulation; README "ID prefixes") |
| From | cluster `OC-277` (primary), `OC-280`, `OC-63`, `OC-122` of the phase 1 OOM candidate list (all four marked `picked: U9`) |
| Phase-1 case files | [`max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md) (OC-277), [`max-unsigned-short-validate-sum--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/max-unsigned-short-validate-sum--autonomous.md) (OC-280), [`column_index_cache_size-indexSamples-cacheSizeThreshold--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md) (OC-63), [`concurrent_compactors-submitBackground-getMaximumPoolSize--guided`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md) (OC-122) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `pc91:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | phase-2 OOM agent, stage 1 session, 2026-11-18 13:38–14:20 EST; nothing run (node checked read-only) |
| Stage 2 (verify) | fresh phase-2 OOM agent session, 2026-11-18 13:50–14:50 EST on `pc91`; 24 counted lifetimes + 1 shake-down |
| Verdict | **true positive** · `verified-OOM · deployment` (unprotected accumulation; convergence of 2 compaction writers in arm M) |

## Summary

- **Conclusion:** true positive. One major compaction of a single 15,000-row partition (≈ 0.99 GB of data, 65,535-byte
  clustering keys) ends in `OutOfMemoryError: Java heap space` on the `CompactionExecutor` **3/3 at a 2 GiB heap** and
  **3/3 at 4 GiB**, with every capacity setting at its shipped default. The same happens with no operator action at all
  (background STCS compaction while writing, 2 GiB, 3/3). Two concurrent compactions fail **3/3 at 6 GiB** (one alone
  survives 3/3) and **2/3 at 8 GiB**. Control (16-byte keys) 0/3; intervention `column_index_size: 4MiB` 0/3 at the same
  compaction time.
- **Root cause:** the BIG-format partition writer (the 5.0.9 default format) serializes one `IndexInfo`, holding full
  copies of the block's first and last clustering, per 64 KiB block into one heap `DataOutputBuffer` for the whole
  partition. With 65,535-byte keys every row is a block, so the buffer is 1.99 × the partition's data. It grows by ×1.5
  copies (old + new live: 729 → 1,094 MiB at 2 GiB, 1,640 → 2,048 MiB at 4 GiB). No control bounds it: there is no
  counter, the partition-size guardrail is off and evaluated only after the index is built, and `column_index_cache_size`
  does not limit it. The yaml documents the remedy (raise the granularity or use BTI) only as a recommendation.

## 1. Candidate

**Cluster rows (quoted from `phase1-oom-candidates.md`; Status as written by the picker):**

> | OC-277 | 2026-11-18 | `max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous` | autonomous | The BIG-format partition writer, used for flush and compaction, keeps the whole partition's row index on heap until the partition is finished. [details](runs/wave2.md#oc-277) | — | picked: U9 |

> | OC-280 | 2026-11-18 | `max-unsigned-short-validate-sum--autonomous` | autonomous | The sum limit allows one clustering key of up to 65535 B, as large as a full 64 KiB row-index block. [details](runs/wave2.md#oc-280) | — | picked: U9 |

> | OC-63 | 2026-11-17 | `column_index_cache_size-indexSamples-cacheSizeThreshold--guided` | autonomous | Write path keeps the whole row index of the partition on the heap, and column_index_cache_size does not limit it. [details](runs/wave1.md#oc-63) | — | picked: U9 |

> | OC-122 | 2026-11-17 | `concurrent_compactors-submitBackground-getMaximumPoolSize--guided` | guided | Holder: the BIG-format per-partition row-index buffer (heap DataOutputBuffer) of every SSTable writer: compaction tasks, flush writers, and the separate validation, index-build, view-build and cleanup executors that the compaction thread limit does not count. [details](runs/wave1.md#oc-122) | CP-12, CP-7 | picked: U9 |

**Details (from `runs/wave2.md` and `runs/wave1.md`, abridged to the load-bearing claims).**
- OC-277: each `IndexInfo` holds full copies of its first and last clustering; default granularity 64 KiB
  (`column_index_size` unset); past `column_index_cache_size` (2 KiB) the index goes into one growing `DataOutputBuffer`;
  65,535-byte keys make every row its own block, so the buffer is ≈ 2 × the partition's data (stage 4 measured Index.db
  at 2.0 × R × K); partition size unlimited at defaults; a 1 GiB partition needs ≈ 2 GiB of buffer, ≈ 3.3 GB at the
  peak with the 1.5× growth copy, before the 2 GiB array limit; per concurrent compactor or flush writer (up to 8).
- OC-280: the same, reached from the sum check (`ClusteringPrefix.java:282-287`), which admits one 65,535-byte key.
- OC-63: same holder; adds that `reset()` keeps the grown buffer as `reusableBuffer` for the writer's life, that
  `indexOffsets` grows by 10 slots at a time and `offsets()` copies it; magnitude ≈ 0.3 % of the partition for ≈ 100 B
  keys, tens of percent with KiB-sized keys.
- OC-122: same holder in every SSTable writer; about (2 × clustering size + ≈ 20 B) per 64 KiB; multiplicity is the
  compaction executor plus flush writers plus executors that `concurrent_compactors` does not count.

**Triage (`runs/triage-2026-11-18.md`, rank 3):** "yes / single ARM node … A 0.6-1 GiB partition compacted with nodetool
compact therefore needs a 1.2-2 GiB buffer plus a 1.5x growth copy, which exceeds a 2 GiB heap on one compaction or flush
thread." Overlaps: "No existing case. Duplicates OC-280 (sum check), with OC-63 and OC-122 as the small-key form. U3 is a
read-side whole-row case, not this writer buffer." Its note 5 lists OC-277 among the fast tests ("about 1 GiB of 64
KiB-key rows and one major compaction").

**What this design covers.**

| Row | Covered | Not covered |
|---|---|---|
| OC-277 | Whole claim at one partition: BIG writer, 65,535-byte keys, index ≈ 2 × data, ×1.5 growth copy, compaction (arms T, M) and flush plus background compaction (arm B); budget search 2 → 8 GiB | "up to 8" concurrent writers: `concurrent_compactors` resolves to **2** on `pc91` (one data directory), so at most 2 compaction writers are tested |
| OC-280 | Same mechanism; the single-component 65,535-byte key passes both the per-value (`:278`) and the sum (`:284`) checks | the two-component form (e.g. 32,768 + 32,767 B) is not run |
| OC-63 | The write-path buffer and its growth (large-key form) | the small-key magnitude (≈ 0.3 %, would need a ≫ 100 GiB partition at these budgets: not reachable here); `reusableBuffer` pinning across later partitions of the same writer (one partition per table here); `indexOffsets` +10 growth and the `offsets()` copy (4 B per block, ≈ 60 KB here: not measured separately) |
| OC-122 | Compaction multiplicity up to the resolved `concurrent_compactors` (2, arm M) and flush writers (arm B, incidental) | validation, secondary-index build, view build, cleanup/streaming writers; the row's "x min(8, cores)" is inexact: the default is `min(8, max(2, min(cores, data dirs)))` (`DatabaseDescriptor.java:777-778`) |

**Phase-1 stage-4 evidence.**
- OC-277 (`results/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous.md`, true negative, "does not
  cap"): 65,535-byte keys accepted, 65,536 rejected; side finding (4): "Index.db repeats the clustering of each index
  block: 2.00 x R x K at K = 65535" (Index.db 1,310,899,518 B for R = 10,000). That run spread the rows over 100
  partitions (`pk = i mod 100`, frozen prediction B3c.2) with a 1 GiB heap, so each partition's index was ≈ 13 MB and
  nothing approached the heap: it measured the ratio, not the per-partition buffer.
- OC-280 (`results/max-unsigned-short-validate-sum--autonomous.md`, true negative): the sum check caps one key, usage
  grows linearly with rows of maximal keys.
- OC-63 (`results/column_index_cache_size-indexSamples-cacheSizeThreshold--guided.md`, true positive for the knob): the
  entry class follows `S ≤ T`; weights linear (188 B per block read side, 284 B write side); the key-cache side is capped
  by `key_cache_size`. The writer buffer's own size was not measured.
- OC-122 (`results/concurrent_compactors-submitBackground-getMaximumPoolSize--guided.md`, false negative for disk): the
  running-task count follows `min(n, 8)`; heap "rose with running tasks … but was not analysed".

**JIRA prior art (read only; nothing posted).** Survey CSV (`jira-oom-survey.csv`) hits: CASSANDRA-9754 "Make index info
heap friendly for large CQL partitions" (Triage Needed, unresolved; read-side `IndexInfo` heap for multi-GB partitions,
Birch-tree proposal); CASSANDRA-8269 (Won't Fix; maintainer advice: raise `column_index_size_in_kb` or avoid huge
partitions); CASSANDRA-16764 "Compaction repeatedly fails validateReallocation exception" (Triage Needed; one ≈ 2 GB cell
serialized into a compaction `DataOutputBuffer`, 16–24 GB heaps exhausted); CASSANDRA-16 (fixed 0.7; whole wide row in
memory during compaction, replaced by streamed compaction; its survey note says "check index/row-index building of huge
partitions"). JIRA REST searches on 2026-11-18 (`text ~ "BigFormatPartitionWriter"`; `"ColumnIndex" AND "OutOfMemory"`;
`"IndexInfo" AND "OutOfMemoryError"`; `"column_index_size" AND "OOM"`; `"index entry" AND "compaction" AND
"OutOfMemoryError"`; `"column index" AND "compaction" AND heap, created ≥ 2016`): no issue about the **writer's** row-index
buffer at flush or compaction with large clustering keys. Related: CASSANDRA-11206 (fixed 3.6, introduced
`column_index_cache_size` and shallow index entries: read side only), CASSANDRA-18398 (CEP-25 BTI format, the alternative
the yaml recommends), CASSANDRA-20918 (cursor compaction, 6.0 only). The shipped `cassandra.yaml` (`:1174-1188`) says:
"if large rows, or a very large number of rows per partition are present, it is recommended to increase the index
granularity or switch to the BTI SSTable format". **Verdict: `new`** for this holder, next to the known-open read-side
CASSANDRA-9754; the behaviour is **partly documented** as a sizing recommendation (not a limit), so the interpretation
is a configuration-sizing gap with no enforced bound (stage 2 states it in §4).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

**Direction: unprotected accumulation** (no control applies to the holder; [`verification-protocol.md`](../../../verification-protocol.md)
"Unprotected results"); arm M adds a convergence check (two bounded-count writers) using the
[`combo-playbook.md`](../../../combo-playbook.md) multiplicity step.

`SortedTablePartitionWriter.addUnfiltered` (`io/sstable/format/SortedTablePartitionWriter.java:128-150`) records the
block's `firstClustering` and the current row as `lastClustering`; `BigFormatPartitionWriter.addUnfiltered` (`:207-215`)
closes a block when `currentPosition() - startPosition >= indexSize`, where `indexSize` =
`DatabaseDescriptor.getColumnIndexSize(DEFAULT_GRANULARITY)` = 64 KiB when `column_index_size` is unset (`:49`, `:73`;
`DatabaseDescriptor.java:2029-2032`; yaml `:1188` commented). `addIndexBlock` (`:128-191`) builds an `IndexInfo(first,
last, …)`; while the serialized samples are ≤ `column_index_cache_size` (2 KiB, `Config.java:328`) they stay in a list,
past it everything is serialized into `buffer` = `new DataOutputBuffer(4096)` (`:168-188`, `:193-205`), and every later
block is appended (`:185-188`). `IndexInfo.Serializer.serialize` (`io/sstable/IndexInfo.java:107-117`) writes both
clusterings in full. With a single 65,535-byte clustering (accepted: `db/ClusteringPrefix.java:278-287`) and a small
value, each row serializes to ≥ 65,536 B, so each row is one block and one `IndexInfo` ≈ 2 × (1 + 1 + 3 + 65,535) + ≈ 5 B
= **≈ 131,085 B per row** against ≈ 65.65 KB of row data (ratio ≈ 2.0; stage 4 measured 2.00). The buffer grows in
`DataOutputBuffer.calculateNewSize`/`expandToFit` (`io/util/DataOutputBuffer.java:158-181`): ×2 below 64 MiB
(`DOB_DOUBLING_THRESHOLD_MB`, `CassandraRelevantProperties.java:203`), ×1.5 above, saturating at `MAX_ARRAY_SIZE`
(`:118`, `:149-155`; one step past it throws `BufferOverflowException`). `finish()` (`:217-244`) appends 4 B offsets per
block; `BigTableWriter.createRowIndexEntry` (`io/sstable/format/big/BigTableWriter.java:97-114`) hands the buffer (a
`duplicate()`, no copy) to the index file. The partition-size guardrail is checked in `SortedTableWriter.endPartition`
(`:238-244`) **after** `partitionWriter.finish()`, and is null by default (yaml `:2121-2122`). The input side of the
compaction does not load `IndexInfo`: entries larger than 2 KiB are read as `ShallowIndexedEntry`
(`io/sstable/format/big/RowIndexEntry.java:360-369`).

**Growth simulation** (the buffer-growth rule above applied to 131,085-byte records from a 4,096 B start; stage 1,
Python): growth steps at merged row ≈ 2,592 (324 → 486 MiB, transient 810 MiB), **3,888** (486 → 729 MiB, 1,215 MiB),
**5,832** (729 → 1,094 MiB, 1,823 MiB), **8,748** (1,094 → 1,640 MiB, 2,734 MiB), **13,122** (1,640 → 2,048 MiB,
3,688 MiB); content overflows `MAX_ARRAY_SIZE` at row **16,383** (`BufferOverflowException`, not an OOM). "Transient" =
old + new array live during `expandToFit`. Capacities ± 2 % (the first steps depend on the exact write pattern).

### 2.2 Protection map

| Domain | Holder / allocation and release | Counter (K) | Limit at defaults | At the limit | Scope and multiplicity |
|---|---|---|---|---|---|
| Row-index buffer (claimed) | `BigFormatPartitionWriter.buffer` / `reusableBuffer`, heap `byte[]` in `DataOutputBuffer`; allocated `:193-205`, grown `DataOutputBuffer.java:174-181`; garbage when the writer is closed (per output sstable) | none (`indexSamplesSerializedSize` only decides list vs buffer) | none; `MAX_ARRAY_SIZE` (≈ 2,048 MiB) is an array limit, not a memory control | `BufferOverflowException` past ≈ 2 GiB of content; the writer's task fails | one per SSTable writer: compaction tasks (≤ `concurrent_compactors`), flush writers (`memtable_flush_writers`), other writers not tested |
| Per-key size | `ClusteringPrefix.validate` (`:272-288`) | key bytes | 65,535 B per key and per sum | `InvalidRequestException` | per statement; bounds one `IndexInfo` (≈ 131 KB), not their count |
| Partition size | `Guardrails.partitionSize` (`Guardrails.java:332`), checked at `SortedTableWriter.java:244` | partition bytes | null (off); evaluated after the index is built; guardrails also skip superusers (AllowAll default) | n/a | per partition |
| Writer multiplicity | compaction executor | running tasks | `concurrent_compactors` = 2 on `pc91` | queued | caps compaction writers, not bytes per writer |
| Flush fragment | memtable pool `memtable_heap_space` = heap/4 (`DatabaseDescriptor.java:586-587`), cleanup threshold 1/(1+2) | memtable bytes | heap/4, flush at ≈ heap/12 | flush | bounds a **flush** writer's partition fragment (≈ heap/12 of rows → index ≈ heap/6), not a compaction's merged partition |
| Rate | `compaction_throughput` 64 MiB/s (global limiter) | bytes/s | 64 MiB/s | throttled | time only |
| Heap (budget) | JVM heap | — | `-Xmx` per arm | `OutOfMemoryError: Java heap space` | process |

U for the claimed domain is measured from the heap (hprof largest `byte[]`, G1 humongous regions, class histogram,
stack): there is no K to compare against, so the result is **U against no contract** (unprotected).

### 2.3 Configuration and budget audit

All capacity constraints at shipped defaults (V6), resolved for `pc91` and each heap: `sstable.selected_format` = big
(`Config.java:373`; yaml `:1172` commented); `storage_compatibility_mode: CASSANDRA_4`; `column_index_size` unset → 64 KiB;
`column_index_cache_size: 2KiB`; `memtable_allocation_type: heap_buffers`; `memtable_heap_space` unset → heap/4 (512 MiB
at 2 GiB, 1 GiB at 4 GiB, 1.5 GiB at 6 GiB, 2 GiB at 8 GiB); `memtable_flush_writers` unset → 2 (one data dir,
`DatabaseDescriptor.java:753-755`); cleanup threshold → 1/3; `concurrent_compactors` unset → `min(8, max(2, min(32, 1)))`
= **2**; `compaction_throughput: 64MiB/s`; `partition_size_warn/fail_threshold` null; `column_value_size_*` null;
`commitlog_segment_size: 32MiB` (`max_mutation_size` 16 MiB); table defaults (STCS 4/32, LZ4 16 KiB chunks);
`DOB_DOUBLING_THRESHOLD_MB` 64 (system property default); `AllowAllAuthenticator`. Stage 2 records the resolved values
from `system.log` (`concurrent_compactors`, memtable thresholds, heap) in `run.meta`.

The only arm-specific settings: `MAX_HEAP_SIZE` and `MAX_DIRECT_MEMORY_SIZE` (budget), and in arm **I** only
`column_index_size: 4MiB` (intervention). Environment: one-node ring on `127.0.0.1`, data, commit log, hints and saved
caches under `/mydata/u9/node/`, `auto_snapshot: false` (environment, so dropped tables leave no snapshot), JDK 11.0.33,
G1 (shipped `jvm11-server.options`), `-XX:+HeapDumpOnOutOfMemoryError` (shipped) with `CASSANDRA_HEAPDUMP_DIR` = the run
dir, the GC log that `cassandra-env.sh:83` adds by default (written to the run's log dir), and
`-Dcassandra.printHeapHistogramOnOutOfMemoryError=true` (`CassandraRelevantProperties.java:404`; logs a
`GC.class_histogram` at the first OOM, after the failure; does not change anything before it). Swap off for the node
(`systemd-run --user --scope -p MemorySwapMax=0`); **no** cgroup `MemoryMax` (the budget is the heap; the scope only
blocks swap).

**Budgets (V7).** What the system resolves on `pc91` itself (125 GiB RAM): heap 15,872 MiB, direct 7,936 MiB
(`cassandra-env.sh` heap_limit branch). The design claims nodes of **4–16 GiB RAM**, for which `cassandra-env.sh`
resolves heap = ½ RAM and direct = ¼ RAM: 4 GiB RAM → 2 GiB / 1 GiB, 8 GiB → 4 GiB / 2 GiB, 12 GiB → 6 GiB / 3 GiB,
16 GiB → 8 GiB / 4 GiB. Each arm sets exactly that pair (heap H, direct H/2). All heaps ≥ 512 MiB: V7 met by the
standing rule; 2 GiB is the primary (ideal) budget and the search goes upward 2 → 4 → 6 → 8 GiB. No container limit is
a budget.

### 2.4 Ceiling arithmetic

No contract capacity covers the buffer. Per writer: content ≤ 2,048 MiB; peak transient ≈ 3,688 MiB (row 13,122 step).
Baseline (idle node, no memtable data during a major compaction): ≈ 0.15–0.35 GiB live, measured in every arm before the
compaction. Predicted live peak = baseline + Σ over simultaneous writers of (old + new buffer) + compaction iterators
(a few rows of 65 KB, negligible):

| Heap | Writers | Data per table (R rows) | Peak need (steps reached) | Feasible OOM? |
|---|---|---|---|---|
| 2 GiB | 1 | 15,000 (≈ 985 MB) | 1.82 GiB + baseline at row 5,832; 2.67 GiB at 8,748 | **yes**, certain by row 8,748 |
| 4 GiB | 1 | 15,000 | 3.60 GiB + baseline at row 13,122 (≈ 3.8–3.95 GiB) | **boundary** (G1 needs 1,024 contiguous 2 MiB regions with ≈ 820 held) |
| 6 GiB | 1 (control S) | 15,000 | ≈ 3.9 GiB | no (control) |
| 6 GiB | 2 (arm M) | 15,000 each | lockstep (one global 64 MiB/s limiter): 2 × 3.60 + baseline ≈ 7.4 GiB at row 13,122 | **yes** if the two steps overlap; 1.6 + 3.6 + 0.3 ≈ 5.5 GiB if not |
| 8 GiB | 2 (arm M, optional) | 15,000 each | ≈ 7.4–7.6 GiB | boundary |

R = 15,000 keeps the content (≈ 1,875 MiB) below the 16,383-row overflow with an 8 % margin. Every R and heap fits
`pc91` (32 cores, 125 GiB RAM, `/mydata` 714 GiB free; checked read-only 2026-11-18 18:47 UTC: no Java process, swap
8 GiB unused, rotational disk `sda` PERC H710P, clock UTC).

### 2.5 Workload and environment

**Node:** `pc91` only (x86_64; local; one measured node at a time). Working root `/mydata/u9/` (fresh): `tree/` = a copy
of `/mydata/s4/cassandra-base` (never `ant` in it), `conf-pristine/`, `node/` (per-lifetime data), `runs/<label>/` (logs,
hprof). Client on the same node (Python, small).

**Schema** (per lifetime, fresh): `CREATE KEYSPACE ks WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
arms T, B, M, S, I: `CREATE TABLE ks.t<n> (pk int, ck blob, v blob, PRIMARY KEY (pk, ck))` (table defaults); arm C: same
schema. One partition per table: `pk = 1`.

**Rows** (`writer.py`, adapted from the stage-4 harness
`../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/harness/max-unsigned-short-ClusteringPrefix-validate-accessor-size--autonomous/writer.py`:
the Python driver from `tree/lib/cassandra-driver-internal-only-3.29.0.zip`, protocol **4**, consistency ONE, one
prepared `INSERT INTO ks.t<n> (pk, ck, v) VALUES (1, ?, ?)`, ≤ 16 requests in flight, single-node
`DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`). Row i (0-based):
- **large-key rows (arms T, B, M, S, I):** `ck` = 8-byte big-endian i + 65,527 seeded random bytes = **65,535 B**;
  `v` = 64 random bytes.
- **small-key rows (arm C, matched payload):** `ck` = 8-byte big-endian i + 8 random bytes = 16 B; `v` = 65,583 random
  bytes (so the row's data size matches the large-key row within 0.1 %; each row is still one 64 KiB block).

**Load procedure "L" (arms T, C, S, I, M):** `nodetool disableautocompaction ks t<n>` right after `CREATE TABLE`; write
in chunks of 1,000 rows; after each chunk `nodetool flush ks t<n>` (so each flushed fragment is 1,000 rows ≈ 65.6 MB;
flush buffer ≤ 144 MiB, transient ≤ 240 MiB: the load itself stays far from every budget). R = 15,000 → 15 sstables.
**First-trigger check** after the first flush (stop the arm on failure, B3-style): test rows `Index.db / Data.db` ∈
[1.85, 2.15]; arm C ≤ 0.01; arm I ≤ 0.05. Then record baseline (`jcmd GC.heap_info` and one GC-log line), then the
endpoint step `nodetool compact ks t<n>` (a `MAJOR_COMPACTION`, one output sstable; run in the background with a 600 s
timeout; arm M: `nodetool compact ks t1` and `nodetool compact ks t2` started within 1 s of each other).

**Load procedure "BG" (arm B, everything default, no operator action):** autocompaction left on; write R = 15,000 rows
with ≤ 16 in flight and no manual flush or compaction. Memtable flushes then come at ≈ heap/12 (≈ 170 MiB ≈ 2,600 rows at
2 GiB; flush buffer content ≈ 340 MB, transient ≈ 810 MiB) and STCS (min_threshold 4) starts a background `COMPACTION`
of the first four flushed sstables (≈ 10,400 rows → past the 8,748 step). After the last write, wait up to 10 min for
the endpoint or for compactions to finish (`nodetool compactionstats` shows no pending/active task).

**Arms and run matrix** (priority order; each row is one lifetime from a clean `node/`):

| Pri | Label | Arm | Heap / direct | Tables × R | Load | Runs | Predicted endpoint |
|---|---|---|---|---|---|---|---|
| 0 | `SHAKE` | T, small | 2G / 1024M | 1 × 1,500 | L | 1 (not a reading) | none; checks scripts, first-trigger check, compaction completes, Index ≈ 2 × Data |
| 1 | `T2-1..3` | T (test) | 2G / 1024M | 1 × 15,000 | L | 3 | heap OOM on `CompactionExecutor` in `expandToFit` ← `addIndexBlock`, at merged row ≈ 5,832 (or ≈ 8,748) |
| 1 | `C2-1..3` | C (matched control) | 2G / 1024M | 1 × 15,000 small-key | L | 3 | none; compaction completes, Index.db ≈ 1 MB |
| 1 | `I2-1..3` | I (intervention: `column_index_size: 4MiB`) | 2G / 1024M | 1 × 15,000 | L | 3 | none; compaction completes, Index.db ≈ 31 MB (≈ 235 blocks × 131 KB) |
| 2 | `T4-1..3` | T | 4G / 2048M | 1 × 15,000 | L | 3 | OOM at row ≈ 13,122 (or ≈ 8,748): boundary, 2/3–3/3 |
| 2 | `T3-1..3` | T | 3G / 1536M | 1 × 15,000 | L | 3, **only if T4 is 0/3** | OOM at row ≈ 8,748 or 13,122 |
| 3 | `M6-1..3` | M (2 writers) | 6G / 3072M | 2 × 15,000 (`t1`, `t2`) | L ×2, then both compacts | 3 | OOM at row ≈ 13,122 of both (lockstep) |
| 3 | `S6-1..3` | S (1 writer, control for M) | 6G / 3072M | 1 × 15,000 | L | 3 | none; compaction completes with Index.db ≈ 1.97 GB |
| 4 | `B2-1..3` | B (background, all default) | 2G / 1024M | 1 × 15,000 | BG | 3 | OOM on a `CompactionExecutor` (background `COMPACTION`) or, earlier, on a flush writer, same frames |
| 5 | `M8-1..3` | M | 8G / 4096M | 2 × 15,000 | L ×2 | ≤ 3, only if M6 ≥ 2/3 and time allows | boundary |

Order of execution: SHAKE, then interleave T2/C2/I2 (T2-1, C2-1, I2-1, T2-2, …) so drift in the node does not align with
an arm; then T4 (T3 if needed), M6 and S6 interleaved, B2, M8.

### 2.6 Instruments (U independent of K)

K: none applies (unprotected); recorded anyway: rows written and rejected (client), sstable count, `Data.db` and
`Index.db` sizes per flush (directory listing), `nodetool compactionstats` (bytes compacted / total, every 2 s) →
**merged row at the endpoint** = bytes compacted ÷ mean row size from the flush listing.

U (independent of anything Cassandra counts):
1. **hprof at the OOM** (shipped `HeapDumpOnOutOfMemoryError`): `hprofhist.py` (copy from
   `../cql-row-limit--wide-row-default-pages/harness/`, add a bucket "byte[] ≥ 64 MiB: count, each length") → the largest
   `byte[]` lengths. Prediction: one array of ≈ 729 or ≈ 1,094 MiB (T2), ≈ 1,640 MiB (T4), two of ≈ 1,640 MiB (M6) — a
   size no other holder on this path has (row data is ≈ 65 KB). `hprofstacks.py` (same source) for the thread stacks in
   the dump.
2. **G1 humongous regions** over time from the default GC log (`heap*=trace` prints the "Humongous regions: a->b" line at
   every GC): peak × region size (1 MiB at 2 GiB, 2 MiB at 4–6 GiB, 4 MiB at 8 GiB) against the predicted buffer
   capacity; also heap after each GC.
3. **`jcmd <pid> GC.heap_info` every 2 s** (used / committed; a safepoint, no GC) and `RssAnon` every 2 s.
4. **Class histogram at the OOM** (`printHeapHistogramOnOutOfMemoryError`): `[B` total bytes vs the same reading taken
   with `jcmd GC.class_histogram` at the end of the compaction in C, I and S arms (taken **after** the compaction, so it
   does not alter the arm).
5. **Initiating failure (V5):** first `OutOfMemoryError` in `system.log` / `stdout.log` with thread name and stack
   (expected frames `DataOutputBuffer.expandToFit` ← `BufferedDataOutputStreamPlus.write` ← `IndexInfo$Serializer.serialize`
   or `ClusteringPrefix$Serializer.serialize` ← `BigFormatPartitionWriter.addIndexBlock` ← `addUnfiltered` ←
   `SortedTableWriter.append` ← `CompactionTask`), and the hprof file.
6. Endpoint detection: the run script polls `system.log` and `stdout.log` every 2 s for `OutOfMemoryError`; on the first
   hit it waits until the hprof size is stable for 10 s (≤ 5 min), then stops the JVM by PID (SIGTERM, then SIGKILL after
   30 s). A node that survives is stopped with `nodetool drain` + SIGTERM after the compaction finishes.

Sampling overhead: two `jcmd` calls and one `nodetool compactionstats` per 2 s; no Byteman, no patch, no forced GC in any
counted run (conditions label stays `deployment`).

### 2.7 Predicted response and stopping budget

- **T2:** 3/3 heap OOM during the major compaction, thrown in the claimed frames on a `CompactionExecutor` thread, at a
  merged row in [3,888, 8,748]; largest `byte[]` ≈ 729 / 1,094 MiB; humongous regions ≈ 0.7–1.1 GiB at the last GC
  before the error. No output Index.db.
- **C2:** 0/3 OOM; compaction completes (one sstable, Data ≈ 985 MB, Index ≈ 1 MB); peak humongous ≤ 64 MiB.
- **I2:** 0/3 OOM; compaction completes, Index ≈ 31 MB; compaction time within 2× of C2 (useful work not stopped).
- **T4:** 2/3–3/3 OOM, largest `byte[]` ≈ 1,640 MiB; if 0/3, T3 3/3. **S6** 0/3 (Index ≈ 1.97 GB written).
  **M6** 2/3–3/3 OOM. **B2** 3/3 OOM in background compaction (or a flush writer). **M8** boundary.
- **Refuting readings:** Index.db/Data.db ≈ 1.0 instead of 2.0 (rows not one block each → wrong path, stop); T2
  compaction completes at 2 GiB (U recorded from the GC log; then the claim is wrong at this size); an OOM in another
  frame (record, not the claimed holder; arm is `retry`-worthy, not a positive).
- **Largest failing budget** = the highest heap with ≥ 1 OOM of 3 in the claimed frames (report n/N per heap).
- **Stopping budget:** per lifetime ≤ 25 min (load ≤ 10 min, compaction ≤ 10 min after `nodetool compact` or after the
  last write in B2, dump ≤ 5 min). Whole stage-2 plan below; **no new lifetime after 17:40 EST** on 2026-11-18; every
  process stopped by 17:55 EST; §3–§4 written by **18:07 EST**. No escalation after an OOM beyond the planned matrix.

**Time plan (EST, 2026-11-18; assumes stage 2 starts by 14:30):** harness + SHAKE 14:30–15:10; priority 1 (9 lifetimes ×
≈ 5 min: load ≈ 2 min, compaction < 1 min, dump ≤ 1 min, start/stop 1 min) 15:10–16:00; priority 2 (T4 ×3 ≈ 6 min each)
16:00–16:20; priority 3 (M6 ×3 ≈ 9 min, S6 ×3 ≈ 6 min) 16:20–17:05; priority 4 (B2 ×3 ≈ 7 min) 17:05–17:30; priority 5
only if before 17:40. If behind, drop from the bottom (M8, then B2, then S6/M6); priority 1 and T4 are the minimum for a
verdict. Disk per lifetime ≤ 12 GB (inputs ≈ 3 GB per table, commit log ≈ 1 GB, hprof ≤ heap); delete `node/` after each
lifetime and keep hprofs only for run 1 of each failing arm (summaries of all).

### 2.8 Controls and intervention

- **Matched control C2 (×3)** (V2): same heap, same row count and row data size, same flush cadence and the same major
  compaction; only the clustering size differs (16 B vs 65,535 B), so blocks per partition are equal and only the bytes
  per `IndexInfo` change (≈ 50 B vs 131 KB).
- **Convergence control S6 (×3)** for arm M: one writer at 6 GiB must survive (safe alone, margin ≈ 35 %), so an M6 OOM is
  attributable to two writers at once.
- **Intervention I2 (×3)** (V4): `column_index_size: 4MiB` (the remedy the shipped yaml recommends), all else as T2;
  index blocks per partition drop 64× and the buffer to ≈ 31 MB. Record compaction time and the output Index.db
  (throughput kept, not a rejection).
- **Not done:** a diagnostic patch (the yaml knob isolates the multiplication without changing code); the BTI format
  (needs `storage_compatibility_mode: NONE`, two changes).

### 2.9 Harness (to build in stage 2 under `harness/`)

Adapt U4's verified scripts (`../cql-row-limit--wide-row-default-pages/harness/`): `setup.sh` (root `/mydata/u9`, copy of
`/mydata/s4/cassandra-base`, pristine conf), `victim-ctl.sh` (start with `MAX_HEAP_SIZE`, `MAX_DIRECT_MEMORY_SIZE`,
`CASSANDRA_HEAPDUMP_DIR`, `CASSANDRA_LOG_DIR=<run>/logs`, `JVM_EXTRA_OPTS=-Dcassandra.printHeapHistogramOnOutOfMemoryError=true`,
the yaml diff for arm I, `auto_snapshot: false`; launch `( setsid nohup … < /dev/null > … 2>&1 & )` inside
`systemd-run --user --scope -p MemorySwapMax=0`; save `run.meta` with label, arm, heap, direct, jar sha256, the
resolved `-Xmx`/`-XX:MaxDirectMemorySize` from `ps`, `yaml.diff`), `writer.py` (above), `run-arm.sh <label> <T|C|I|S|M|B>
<heap> <direct> <R>` (refuse if a `CassandraDaemon` runs; clone; start; wait for `Starting listening for CQL clients`;
schema; load; first-trigger check; baseline; samplers; compact; endpoint detection; stop; copy small files to
`logs/<label>/`), `summarize.py` (one line per lifetime: arm, heap, rows, sstables, Data/Index sizes, merged row at the
endpoint, outcome, first OOM thread + top frames, largest `byte[]` lengths, peak humongous, baseline), `hprofhist.py`,
`hprofstacks.py`, `gcwin.py` (copied). Run each lifetime as a background job and poll with bounded waits; kill by PID.

`sha256 of §1–§2 at freeze: 0a7a3d303d4223ddae7cb92eb69ae9f9a1d4632d935d0e7167d3f70bf93d3dbf` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · amendments after the freeze: dated, with reason, below this line.


**Amendments (stage 2, 2026-11-18; none changes a capacity, budget, workload or arm):**
- **A1 (environment, before any reading):** working root `/mydata/s4/u9-w4/` instead of `/mydata/u9/` (the stage-2
  task's node instruction: a fresh directory under `/mydata/s4/`). Same node, build copy and layout (`tree/`,
  `conf-pristine/`, `node/`, `runs/<label>/`).
- **A2 (reading, no setting changed):** the shipped `jvm11-server.options` sets `-XX:G1HeapRegionSize=16m` at every
  heap; §2.6 item 2 assumed 1–4 MiB regions. Humongous readings below are in 16 MiB regions. The setting is shipped, not
  changed.
- **A3 (instrument, no setting changed):** the shipped `-XX:OnOutOfMemoryError="kill -9 %p"` (`cassandra-env.sh:209`)
  kills the JVM right after the heap dump. Cassandra's Java handler therefore never runs: no `system.log` stack and no
  `printHeapHistogramOnOutOfMemoryError` histogram (§2.6 item 4). The class histogram and the OOM thread's stack (V5)
  come from the hprof (`hprofhist.py`, `hprofstacks.py`, §2.6 items 1 and 5), which hold the same information.
- **A4 (instrument):** `nodetool compactionstats` sampled every ≈ 3 s, but a T compaction runs at ≈ 100 MB/s and failed
  4–8 s after it started. The last sample is therefore only a lower bound on the merged row. The endpoint row is read
  from the dump instead: the failing step is the one after the largest live `byte[]`, so the OOM happens when content
  reaches that capacity (729 MiB → row ≈ 5,832; 1,640 MiB → row ≈ 13,121).
- **Harness fixes before any counted lifetime** (not readings): `SHAKE0-harnessbug` stopped at row 1,000 because the
  endpoint detector matched `OnOutOfMemoryError` in the logged JVM arguments (now matches `java.lang.OutOfMemoryError`);
  the "a CassandraDaemon already runs" check matched the controller's own ssh command line (now checks only `java`
  processes); the post-compaction listing waits 8 s for the async deletion of the input sstables.

## 3. Runs (stage 2)

**Stage 2:** fresh OOM-agent session, 2026-11-18 13:50–14:50 EST. Freeze hash checked at the start:
`0a7a3d30…3dbf` recomputed, matches.

### 3.1 Environment

| Item | Value |
|---|---|
| Node | `pc91` = `node0.jason92-326665` (x86_64, 32 cores, 125 GiB, swap 8 GiB unused, `/mydata` 714 GiB free); controller on another node (ssh). Before the first lifetime: no `java` process. One lifetime at a time (`batch.sh`) |
| Build | `/mydata/s4/u9-w4/tree` = copy of `/mydata/s4/cassandra-base`, `apache-cassandra-5.0.9-SNAPSHOT.jar` sha256 `570b5249…0176e` (in every `run.meta`); unmodified |
| JDK / GC | OpenJDK 11.0.33, shipped `jvm11-server.options`: G1, `G1HeapRegionSize=16m`, `G1NewSizePercent=50`, `MaxGCPauseMillis=300`, `AlwaysPreTouch`; shipped `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError=kill -9 %p`; default GC log (`heap*=trace`) |
| Launch | `( setsid nohup systemd-run --user --scope -p MemorySwapMax=0 bin/cassandra -f … & )`; no `MemoryMax` (the budget is the heap) |
| Resolved budgets (`ps`, `run.meta`) | `-Xms=-Xmx` 2G / 4G / 6G / 8G with `-XX:MaxDirectMemorySize` 1024M / 2048M / 3072M / 4096M respectively (heap H, direct H/2, §2.3) |
| Resolved capacities (V6) | yaml diff = data/commitlog/hints/saved_caches/cdc dirs + `auto_snapshot: false` (arm I adds `column_index_size: 4MiB`); logged config `column_index_size=null` (→ 64 KiB), `column_index_cache_size=2KiB`, `concurrent_compactors=null` → **2** (`nodetool getconcurrentcompactors` during T2-2), `compaction_throughput=64MiB/s`, `memtable_heap_space=null` → "Global memtable on-heap threshold … 512MiB" at 2 GiB, `memtable_flush_writers` → 2, `memtable_allocation_type=heap_buffers`, `partition_size_fail_threshold=null`, `storage_compatibility_mode=CASSANDRA_4` (BIG format) |
| Harness | [`harness/`](harness/): `setup.sh`, `victim-ctl.sh`, `run-arm.sh`, `batch.sh`, `writer.py`, `summarize.py`, `excerpt.sh`, `hprofhist.py` (U4's plus a `U9` line: every `byte[]` ≥ 64 MiB), `hprofstacks.py` (U4's, 40 frames), `gcwin.py` (U4's) |
| Logs | full: `pc91:/mydata/s4/u9-w4/runs/<label>/` (`stdout.log`, `logs/system.log`, `logs/gc.log*`, `heap.csv`, `cstats.log`, `load.log`, …); excerpts: [`logs/<label>/`](logs/) (`summary.txt`, `result.txt`, `run.meta`, `hprofhist.txt`, `hprofstacks-first.txt`, `stdout-oom.txt`, `system-compaction.txt`, `gc-humongous-tail.txt`, …), batch logs `logs/batch-*.log`. hprofs kept for run 1 of each failing arm: `T2-1` (1.15 GB), `T4-1` (1.93 GB), `M6-1` (4.53 GB), `B2-1` (1.36 GB); the others were deleted after analysis (§2.7) |

**Left on `pc91`** (checked 14:46 EST): no `java`, `nodetool`, harness or sampler process; `/mydata/s4/u9-w4/` = 8.9 GiB
(`tree/` 419 MiB, `runs/` 8.5 GiB of logs and the four kept hprofs, `excerpts/`, `harness/`, `conf-pristine/`); `node/`
(data) deleted after every lifetime. `/mydata/s4/cassandra-base` untouched.

**Workload check (every lifetime):** first flush of the test table: Data.db 65,909,326 B, Index.db 131,090,992 B,
**ratio 1.989** (arms T/S/M/B; check [1.85, 2.15] passed); arm C 0.0007 (Index 48,991 B; ≤ 0.01 passed); arm I 0.0318
(Index 2,097,510 B; ≤ 0.05 passed). Load L: 15 sstables per table, Data.db 988.64 MB, Index.db 1,966,364,880 B
(= **131,091 B of index per row**, 1.989 × the data), 0 write errors in every L lifetime. Load time ≈ 35 s per table.

### 3.2 Readings

"Live after last Full GC" = the last `Pause Full (G1 Humongous Allocation)` before the error (heap after GC). "Arrays" =
every `byte[]` ≥ 64 MiB in the dump (`U9` line of `hprofhist.txt`). Every OOM is `java.lang.OutOfMemoryError: Java heap
space` (`stdout.log`), followed by the dump and the shipped `kill -9`.

| Lifetime | Arm, heap | Outcome | Time to endpoint | Live after last Full GC | Arrays ≥ 64 MiB in the dump (MiB) | Peak humongous (16 MiB regions) | OOM thread (hprof stack) |
|---|---|---|---|---|---|---|---|
| T2-1 | T, 2G | **OOM** | 4 s after `nodetool compact` | 1,067 / 2,048 MiB | 729.0 | 77 (1,232 MiB) | `expandToFit:178` ← `IndexInfo$Serializer.serialize:110` ← `BigFormatPartitionWriter.addIndexBlock:187` ← `addUnfiltered:214` ← `SortedTableWriter.append` ← `CompactionTask.runMayThrow:224` ← `CompactionManager$9` (major) |
| T2-2 | T, 2G | **OOM** | 4 s | 1,159 / 2,048 | 729.0 | 77 | same |
| T2-3 | T, 2G | **OOM** | 4 s | 903 / 2,048 | 729.0 | 77 | same |
| C2-1/2/3 | C, 2G | completed 3/3 | compaction 7.67 / 7.70 / 8.26 s | — | — | 0 / 0 / 0 | — ; output Data 988.68 MB, **Index.db 745,899 B** |
| I2-1/2/3 | I, 2G | completed 3/3 | compaction 7.72 / 7.92 / 7.91 s | — | — | 6 / 5 / 6 | — ; output Data 988.65 MB, **Index.db 30,807,049 B** |
| T4-1 | T, 4G | **OOM** | 6 s | 1,808 / 4,096 | 1,640.4 | 172 (2,752 MiB) | same frames as T2 |
| T4-2 | T, 4G | **OOM** | 8 s | 1,991 / 4,096 | 1,640.4 | 172 | same |
| T4-3 | T, 4G | **OOM** | 8 s | 1,902 / 4,096 | 1,640.4 | 172 | same |
| T3 | — | not run | — | — | — | — | design: only if T4 is 0/3 |
| M6-1 | M (2 writers), 6G | **OOM** | 6 s | 4,297 / 6,144 | 1,640.4 + 1,093.6 + 1,093.6 | 241 (3,856 MiB) | same frames, one of two `CompactionExecutor` threads |
| M6-2 | M, 6G | **OOM** | 6 s | 2,566 / 6,144 | 1,093.6 + 1,093.6 | 230 | same |
| M6-3 | M, 6G | **OOM** | 6 s | 4,310 / 6,144 | 1,640.4 + 1,093.6 + 1,093.6 | 241 | thread 138 at `expandToFit:178` (allocating 1,640 MiB, OOM); thread 137 at `expandToFit:180` (`newBuffer.put(buffer)`, copying its 1,094 → 1,640 MiB array) |
| S6-1/2/3 | S (1 writer), 6G | completed 3/3 | compaction 24.06 / 23.82 / 23.96 s | — | — | 232 / 232 / 232 (3,712 MiB) | — ; output **Index.db 1,966,375,901 B** (1.99 × Data) |
| B2-1 | B (all default, background), 2G | **OOM** during the load (after row ≈ 13,000–14,000 written) | 4.9 s after the background compaction started | 1,281 / 2,048 | 486.0 + 324.0 | 73 | same writer frames ← `CompactionTask.runMayThrow:224` ← `CompactionManager$BackgroundCompactionCandidate.run:374` (STCS `COMPACTION` of the 4 auto-flushed sstables nb-1..4, 488 MB ≈ 7,440 rows) |
| B2-2 | B, 2G | **OOM** during the load | ≈ 3 s after it started | 1,037 / 2,048 | 324.0 + 324.0 | 66 | same (background compaction of 4 sstables, 502 MB) |
| B2-3 | B, 2G | **OOM** during the load | ≈ 4 s after it started | 1,214 / 2,048 | 324.0 + 324.0 | 66 | same (515 MB); a memtable flush of `t1` was writing at the same moment |
| M8-1 | M, 8G | completed | compactions 29.4 s and 42.4 s (the two writers drifted apart) | — | — | 361 (5,776 MiB) | — ; both outputs Index.db 1,966,375,901 B |
| M8-2 | M, 8G | **OOM** | 8 s | 5,620 / 8,192 | **2,048.0** (`MAX_ARRAY_SIZE`, 2,147,483,639 B) + 1,640.4 + 1,640.4 | 335 | same frames |
| M8-3 | M, 8G | **OOM** | 6 s | 4,215 / 8,192 | 1,640.4 + 1,093.6 + 1,093.6 | 308 | as M6-3 (one writer copying at `:180`, the other failing at `:178`) |

Other readings: B2 load errors (client `WriteTimeout`, CL ONE) 13 / 83 / 13 of 15,000 rows, all while the GC was under
humongous pressure just before the OOM; zero in every other arm. Service-loss criterion (`gcwin.py`): not met in any
lifetime (max 2 % STW over 60 s); the endpoint is a plain OOM, not GC thrash. Idle live heap after a compaction
(`GC.class_histogram`'s full GC): 422 MiB (C2-1), 258–340 MiB (S6-2/3), 533 MiB (M8-1).

**Endpoint row (A4).** A T2 dump holds one 729.0 MiB array (764,458,560 B). The failing request is the next step
(×1.5 → 1,094 MiB), which comes when the content reaches 764,458,560 B, i.e. at merged row 764,458,560 / 131,091 ≈
**5,832** of 15,000. The stage-1 simulation predicted the step at 5,832. T4: 1,720,031,760 B → row ≈ **13,121** (predicted
13,122), failing on the 1,640 → 2,048 MiB step. The last `compactionstats` samples (rows ≈ 2,500–3,200 for T2,
≈ 10,800–11,100 for T4) are consistent lower bounds.

### 3.3 What the numbers show

- **U (independent of any counter; no K exists).** The dump of every OOM holds the row-index buffer as the largest objects
  in the heap, at exactly the predicted growth capacities (324, 486, 729, 1,094, 1,640, 2,048 MiB = the ×1.5 sequence of
  §2.1). Everything else in the dump totals 178–461 MiB of shallow heap (dump total minus these arrays; B2 includes the memtable). At 2 GiB, live after the last Full GC was 903–1,159 MiB
  (729 MiB of it the buffer); the step needs another 1,094 MiB (69 contiguous 16 MiB regions) → no room. At 4 GiB, live
  1,808–1,991 MiB (1,640 MiB buffer); the 2,048 MiB step needs **128 contiguous regions** of 256 while 103 hold the old
  array. The byte sum (≤ 4,039 MiB) is just under 4,096 MiB, but the contiguous humongous request cannot be met: G1 does
  not move humongous objects. This is the "boundary" the design flagged (§2.4).
- **Two writers (M).** The two major compactions advance in lockstep (both at the same `compactionstats` percentage every
  sample, one 64 MiB/s limiter) and grow their buffers together. At 6 GiB, 3/3 OOM at the 1,094 → 1,640 step: in
  M6-1/M6-3 one writer is copying (old 1,094 + new 1,640 live) while the other's 1,640 MiB request fails (4,297–4,310 MiB
  live). M6-2 failed one step earlier (two 1,094 MiB arrays, 2,566 MiB live), with free bytes available but no 103
  contiguous free regions. The single-writer control at the same heap (S6) completed 3/3 with a peak of 3,712 MiB
  humongous, the predicted 1,640 + 2,048 MiB transient. So the 6 GiB OOM needs the second writer (convergence of two
  `concurrent_compactors` slots). At 8 GiB 2/3: M8-2 fails with one writer already at the 2,048 MiB array limit and the
  other at 1,640 → 2,048 MiB (5,620 MiB live); M8-3 fails at 1,094 → 1,640 (contiguity, 4,215 MiB live); M8-1 survives
  because the two writers drifted apart (29 s vs 42 s).
- **Everything default (B).** With no operator action (autocompaction on, no manual flush/compaction), STCS compacted
  the first four flushed sstables (488–515 MB ≈ 7,440–7,850 rows of one partition) while the client kept writing. It failed 3/3 on
  the 324 → 486 or 486 → 729 MiB step. The heap then also held the memtable (on-heap pool up to 512 MiB) and, in B2-2/3,
  a second 324 MiB array of the same size class: by size and timing a memtable flush writer's index buffer for its
  ≈ 2,000-row fragment. So a ≈ 0.5 GB partition is enough in a write-active node at 2 GiB.
- **Matched control (C)** with the same row count, row size, flush cadence and major compaction, and only the clustering
  size changed (16 B): Index.db 0.75 MB, no humongous region, 0/3.
- **Intervention (I)**, `column_index_size: 4MiB` (the yaml's own recommendation): 64× fewer blocks, Index.db 30.8 MB,
  ≤ 6 humongous regions, 0/3. Compaction time 7.72–7.92 s vs 7.67–8.26 s in C, so useful work is unchanged.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** (unprotected accumulation; arm M adds a
convergence of two compaction writers).

**Reason.** A single 15,000-row partition (988.6 MB of data) with 65,535-byte clustering keys makes the BIG partition
writer's row-index `DataOutputBuffer` 1.989 × the data (131,091 B of index per 65.9 KB row). Nothing bounds that buffer:
there is no counter, `partition_size_*` is null and checked only after the index is built, and `column_index_cache_size`
only decides list vs buffer. The writer grows it ×1.5 by copying, so each step briefly holds old + new. One major
compaction gave a heap OOM **3/3 at a 2 GiB heap** (T2) at merged row ≈ 5,832, failing to grow 729 → 1,094 MiB with
903–1,159 MiB live. It gave **3/3 at 4 GiB** (T4) at row ≈ 13,121, failing 1,640 → 2,048 MiB (a 128-region contiguous
humongous request). The OOM thread is always the `CompactionExecutor` in `BigFormatPartitionWriter.addIndexBlock:187` →
`DataOutputBuffer.expandToFit:178`. The same holder in a fully default, operator-free run (B2: autocompaction, STCS
background compaction of ≈ 7,500 rows while writes continue) also gave **3/3 OOM at 2 GiB**. Two concurrent compactions
(the resolved `concurrent_compactors` = 2) gave **3/3 OOM at 6 GiB** (M6), where one writer alone survives 3/3 (S6,
1.97 GB Index.db written). At **8 GiB they gave 2/3** (M8). The matched 16-byte-key control at 2 GiB completed 3/3
(Index.db 0.75 MB), and the intervention `column_index_size: 4MiB` completed 3/3 (Index.db 30.8 MB) at the same
compaction time (≈ 7.8 s).

**Largest failing budget:** heap **8 GiB** (2/3, two concurrent compactions of 15,000-row partitions); single writer
**4 GiB** (3/3), with 6 GiB the single-writer boundary (S6 0/3). The 8 GiB heap is the one `cassandra-env.sh` resolves
for a 16 GiB node. At 4 and 8 GiB part of the failure is G1 humongous contiguity (the requested 1,640 / 2,048 MiB array
needs 103 / 128 contiguous 16 MiB regions, and G1 does not move humongous objects), so the byte sum alone (≤ 4,039 of
4,096 MiB at T4; 4,215 MiB live at M8-3) understates the failure. These are the shipped JVM options, not a tightened
budget.

**Conditions per arm (fixed build 5.0.9, shipped JVM options, all capacity constraints at defaults):**

| Condition | Budget (heap / direct) | Endpoint n/N | Status |
|---|---|---|---|
| T2: 1 major compaction, 15,000 × 65,535-B keys | 2 GiB / 1 GiB | OOM 3/3 | `verified-OOM · deployment` |
| B2: everything default, background STCS, writes continuing | 2 GiB / 1 GiB | OOM 3/3 | `verified-OOM · deployment` (supporting; no operator action) |
| T4: as T2 | 4 GiB / 2 GiB | OOM 3/3 | `verified-OOM · deployment` (controls/intervention run at 2 GiB only) |
| M6: 2 concurrent major compactions | 6 GiB / 3 GiB | OOM 3/3 (S6 single-writer control 0/3) | convergence part `verified-OOM · deployment (no intervention at 6 GiB)` |
| M8: as M6 | 8 GiB / 4 GiB | OOM 2/3 | largest failing budget (2/3) |
| C2 (16-B keys), I2 (`column_index_size: 4MiB`) | 2 GiB / 1 GiB | 0/3 each | control / intervention |

**V1–V7 (fixed condition T2, 2 GiB):**

| | Evidence |
|---|---|
| V1 Repetition | T2-1/2/3 OOM 3/3 from clean `node/` (also T4 3/3, B2 3/3, M6 3/3, M8 2/3) |
| V2 Matched control | C2-1/2/3 (same rows, row size, flushes, compaction, heap; 16-B keys): 0/3, Index.db 745,899 B, 0 humongous regions. For M6: S6 0/3 at 6 GiB |
| V3 Measurement | U from the dumps (`byte[]` ≥ 64 MiB lengths = the buffer capacities 729.0 / 1,640.4 / 2,048.0 MiB), GC-log live heap after Full GC and humongous region counts, on-disk Index.db (1,966,364,880 B per 15,000 rows). There is no K: no control counts this memory (unprotected) |
| V4 Intervention | I2-1/2/3: `column_index_size: 4MiB` (shipped yaml's recommendation), all else equal: 0/3, Index.db 30.8 MB, compaction 7.7–7.9 s (C2 7.7–8.3 s), so useful work is unchanged |
| V5 Initiating failure | `java.lang.OutOfMemoryError: Java heap space` first in `stdout.log` (line 401 in T2-1); OOM thread stack from the hprof ([`logs/T2-1/hprofstacks-first.txt`](logs/T2-1/hprofstacks-first.txt)): `HeapByteBuffer.<init>` ← `DataOutputBuffer.expandToFit:178` ← `IndexInfo$Serializer.serialize:110` ← `BigFormatPartitionWriter.addIndexBlock:187` ← `addUnfiltered:214` ← `SortedTableWriter.append:149` ← `CompactionTask.runMayThrow:224` ← `CompactionManager$9` (major); histogram from the hprof ([`logs/T2-1/hprofhist.txt`](logs/T2-1/hprofhist.txt)): one 729.0 MiB `byte[]`, total shallow 1,068 MiB. No `system.log` stack: the shipped `OnOutOfMemoryError=kill -9` (A3) |
| V6 Default constraints | `column_index_size` unset (64 KiB), `column_index_cache_size` 2 KiB, BIG format (`storage_compatibility_mode: CASSANDRA_4`), `partition_size_*` null, `concurrent_compactors` → 2, `compaction_throughput` 64 MiB/s, memtable defaults; the 65,535-B key is accepted by `ClusteringPrefix.validate`. Only the intervention arm differs |
| V7 Acceptable budget | 2 GiB heap / 1 GiB direct (ideal under the standing rule; what `cassandra-env.sh` resolves for a 4 GiB node); also 4, 6, 8 GiB (8 / 12 / 16 GiB nodes) |

**Classification and interpretation.** **Unprotected accumulation**: no capacity control applies to the writer's
row-index buffer. Its size is (2 × clustering size + ≈ 20 B) per 64 KiB block, for every block of the partition, and
it is held until the partition is finished. Arm M adds a **convergence** of the per-writer buffers across the
`concurrent_compactors` slots (S6 alone survives where M6 fails). The workload stays inside documented limits: keys up
to 65,535 B are accepted, and partition size is unlimited at defaults. Large partitions and rows are allowed. The shipped yaml
**documents** the sizing remedy ("if large rows, or a very large number of rows per partition are present, it is
recommended to increase the index granularity or switch to the BTI SSTable format", `cassandra.yaml:1174-1188`) but
enforces no bound. Interpretation: a **configuration-sizing gap with no enforced bound** at the default granularity and
format, next to the known-open read-side CASSANDRA-9754. With small keys the same buffer is ≈ 0.3 % of the partition
(OC-63), so it needs the large-key shape (or a ≫ 100 GiB partition) to reach a heap.

**Limits of attribution.**
- The OOM thread is identified by its stack (thread names are not resolved from the dump). In B2-2/3 the second 324 MiB
  array is attributed to a flush writer by size and timing only.
- The 4 and 8 GiB results depend on G1's humongous contiguity at the shipped 16 MiB region size, besides the byte total.
- `BufferOverflowException` past the 2 GiB array limit (row 16,383) was not reached: R = 15,000 by design.
- The arms do not cover validation, index/view build, cleanup or streaming writers (OC-122's other writers), the
  two-component 32,768 + 32,767 B key (OC-280), or `reusableBuffer` pinning across partitions (OC-63).
- No intervention arm at 6 and 8 GiB; the 2 GiB intervention addresses the same holder.
