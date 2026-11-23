# U12 (OC-104) — SSTable row-body scratch DataOutputBuffer: a collection row grown by appends is serialized whole into direct memory at compaction  <!-- file: cassandra/cases/sstable-row-body-scratch-DOB--appended-collection-row-compaction/sstable-row-body-scratch-DOB--appended-collection-row-compaction.md -->

| Field | Value |
|---|---|
| Case ID | `U12` (U = unprotected-accumulation case; README "ID prefixes") |
| From | `OC-104` of the phase 1 OOM candidate list (triage 2026-11-18 rank 12); duplicates `OC-118` (covered) and `OC-85` (heap side, measured but not claimed) |
| Phase-1 case file | [`capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`; node build `ms0611:/mydata/s4/cassandra-base`, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`) |
| Stage 1 (design) | OOM agent, phase 2 stage 1, Claude Opus 5.5 (`claude-opus-5-5`), 2026-11-21 08:02–08:12 EST (frozen 08:12) |
| Stage 2 (verify) | OOM agent, phase 2 stage 2 (fresh session), Claude Opus 5.5 (`claude-opus-5-5`), 2026-11-21 08:12–09:40 EST on `ms0611` (runs 08:41–09:14) |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected accumulation) |

## Summary

- **Conclusion:** **true positive.** At shipped defaults on a 2 GiB heap / 1 GiB direct node (what `cassandra-env.sh` sets
  for 4 GiB RAM), one compaction of a map row grown to 600 MiB by 1 MiB appends kills the node with
  `OutOfMemoryError: Direct buffer memory` on `CompactionExecutor:1` in `DataOutputBuffer.expandToFit` ← `UnfilteredSerializer.serialize`,
  3/3 from a restart, and 3/3 on the natural path (700 appends, automatic flushes, the first STCS compaction; no operator action).
  The same 600 MiB in six 100 MiB rows (3/3) and a 420 MiB row (3/3) compact fine; a patch that streams the row body instead
  of copying it into the scratch buffer removes the OOM (3/3, same output size, extended verify passes).
- **Root cause:** when compaction (or flush) writes a row to an SSTable, the whole row body is first
  serialized into the compaction thread's thread-local scratch `DataOutputBuffer`, which is **direct** memory by default and
  grows without any capacity check (doubling to just over 64 MiB, then ×1.5; old and new buffer live together during each
  copy). `DOB_MAX_RECYCLE_BYTES` only trims the buffer at `close()`, after the row. No setting bounds the size of a stored row
  at defaults: `max_mutation_size` bounds one write, and a non-frozen collection collects cells from any number of writes.
  Measured (Byteman, run Dg1): the buffer grows 1.00 MiB × 2ᵏ → 64.0 → 96 → 144 → 216 → 324 → 486 MiB, and the next step
  asks for 729 MiB while the 486 MiB buffer is still live: 1,215 MiB plus 17 MiB of other direct memory, above the
  1,024 MiB direct limit. A row ≤ 486 MiB peaks at 324 + 486 = 810 MiB and survives (run B).
- **How conditional:** one row above 486 MiB is enough at a 1 GiB direct limit; larger limits need larger rows (above
  1,093.5 MiB at 2 GiB direct, above 1,640 MiB at 3 GiB, by the measured growth sequence; not run here), and a single
  thread cannot pass ≈ 3.7 GiB. The rows of 1,000 and 1,500 MiB the design chose for 2 and 3 GiB sit just below those edges
  and survived (0/3, 0/3). The CQL docs say collections are for small data; no limit enforces it.

## 1. Candidate

**Candidate row (phase 1 OOM candidate list, `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md:113`), quoted:**

> | OC-104 | 2026-11-17 | `DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided` | autonomous | When a row is written to an SSTable (memtable flush, compaction, streaming receive, index builds), its whole body is serialized into the thread's scratch DataOutputBuffer. [details](runs/wave1.md#oc-104) | — | picked: U12 (2026-11-21) |

**Full text (`runs/wave1.md`, `## OC-104`), quoted:**

> When a row is written to an SSTable (memtable flush, compaction, streaming receive, index builds), its whole body is serialized
> into the thread's scratch DataOutputBuffer. That buffer is direct memory by default and grows to fit the row: doubling up to
> 64 MiB, then 1.5x. During each growth the old and new buffers coexist, so one row of size R costs up to about 3R of direct memory
> transiently. DOB_MAX_RECYCLE_BYTES (1 MiB) only decides what is kept after close(), not how big the buffer gets while in use. No
> limit bounds a row's size at the defaults: max_mutation_size (16 MiB) applies per write, and a row (for example a collection
> column) can collect cells from any number of writes, with the collection and partition-size guardrails off. A 500 MiB row would
> take about 1-1.5 GiB of direct memory on one flush or compaction thread. With memtable_flush_writers plus concurrent_compactors
> (2-8) threads doing this at once, plus the row materialized on heap, this can pass MaxDirectMemorySize (which defaults to the heap
> size). Above about 2 GiB the buffer throws instead of growing.
>
> **Where:** src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:193-203; src/java/org/apache/cassandra/io/util/DataOutputBuffer.java:48,73-80,87,158-182

**Triage (`runs/triage-2026-11-18.md`, rank 12), quoted:**

> | 12 | OC-104 | yes | single ARM node | Flush and compaction serialize each row body whole into the thread's direct scratch
> DataOutputBuffer, which grows to fit, so a row of R costs up to about 3R transiently. A non-frozen collection row grown to about
> 500 MiB by 1 MiB appends then needs about 1-1.5 GiB of direct memory on one compaction thread (plus about 2-3x R on the heap,
> OC-85), above the default direct limit of about heap/2 at a 2 GiB heap. | Same row shape as U3 (whole collection on read). Same DOB
> holder family as R7/U1 and C3, but those are bounded by max_mutation_size and this one by row size. Duplicates OC-118 and OC-85
> (the heap side). |

**Duplicates named by the triage, quoted (`phase1-oom-candidates.md:127`, `:94`; text from `runs/wave1.md`):**

> **OC-118** (guided, CP-12, CP-11) — Holder: the scratch buffer used for an SSTable row body during flush and compaction. Why
> nothing stops it: serializeRowBody writes one whole row into the thread's scratch buffer. Nothing limits a row's size, for example
> a non-frozen collection built up by many writes. Above 64 MiB the buffer grows by half instead of doubling, and it is only trimmed
> at close. Size: about 2 x the largest row (3x for a moment) on each flush writer and compaction thread at once (2 flush writers +
> 2-8 compactors). **Where:** src/java/org/apache/cassandra/db/rows/UnfilteredSerializer.java:192-203; io/util/DataOutputBuffer.java:158-181

> **OC-85** (autonomous, `max_value_size-read-maxValueSize--guided`) — Holder: the full on-heap Row built when any reader or
> compaction deserializes a row. Every cell of a fetched complex column is deserialized (readComplexColumn loops over all cells, each
> a new byte[]). Why nothing stops it: max_value_size is per cell, and max_mutation_size is per write. A row grown across many writes
> (for example a non-frozen map/list/set appended 1 MiB at a time, merged by compaction) has no size cap except its 32-bit serialized
> row size. Reads, and compaction (merged source rows plus the output row, about 2-3x), materialize it whole. Rough size at defaults:
> up to about 2 GiB per row, times concurrent_reads (32) plus compaction threads. **Where:** UnfilteredSerializer.java:662-690,
> :647-655, :698-700; Cell.java:339; AbstractType.java:594-599

**What this design covers.** **OC-104 and OC-118 in full**: same holder (the thread's scratch `DataOutputBuffer` at the SSTable
row site), same trigger (a row grown by many writes), same endpoint (JVM direct-buffer OOM). The design uses the compaction thread
(the largest rows; flush rows are bounded by the memtable, §2.2 row P5); streaming receive and index builds are not exercised.
**OC-85 is only measured, not claimed**: the merged row on the heap is a co-tenant of every arm (heap peak and histogram are
recorded, §2.6), and supplementary arm H (§2.7) moves the scratch buffer onto the heap; a heap-OOM claim for OC-85 (reads ×
`concurrent_reads`) stays with OC-85, whose row remains `open`. Correction to the OC-104 text: `MaxDirectMemorySize` does not
default to the heap size here; `cassandra-env.sh` sets it from RAM (§2.3).

**Phase-1 case and its stage-4 result.** The phase-1 case's constraint is `DOB_MAX_RECYCLE_BYTES` (JVM property
`cassandra.dob_max_recycle_bytes`, default 1 MiB), checked only in `DataOutputBuffer$1$1.close()` (`DataOutputBuffer.java:73-80`):
a buffer of capacity ≤ 1 MiB is kept on the thread, a larger one is freed and replaced by 128 B. It is a **retention** cap; the case
says so (§4 "It does not see, and does not bound, the buffer's size while in use") and lists the SSTable row site as user 4,
"one row body — **not** bounded by `max_mutation_size`, since a row can accumulate cells from many writes" (case §6 table, row 4).
Its stage 4 ([results](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/DOB_MAX_RECYCLE_BYTES-close-MAX_RECYCLE_BUFFER_SIZE--guided.md),
`pc57`, 2026-10-15, run 1) measured **only the commit-log site** (`CommitLog.add`): 308 held writes each grew the buffer to exactly
2(V + P) with a transient 3(V + P) and were kept iff C ≤ L; unit tier 205/205; confirmed. **The SSTable row site (site 4) was not
measured** in stage 4; no flush or compaction ran in its batches ("no flush in a start, so no flush thread joins site 4").
Related phase-2 cases: **U1/R7** (same holder, commit-log site, items bounded by `max_mutation_size`; R7 true positive at 896 MiB
direct), **C3/R9** (same holder, retention × threads; false positive: retained ≤ 1 MiB per thread), **U3** (same row shape, whole
collection materialized on the heap by reads; true positive at 2–8 GiB heap). None exercises a row grown past `max_mutation_size`
at the SSTable writer.

**Documentation (by-design status).** The CQL docs say collections are "meant for storing/denormalizing relatively small amount of
data" and that data expected to grow unbounded belongs in a clustering table (`doc/modules/cassandra/pages/developing/cql/types.adoc:216-227`).
No document gives a byte limit on a stored collection or row; the limits that exist are per write (`max_mutation_size`), per cell
(`max_value_size`) and per request (`native_transport_max_frame_size`), and the collection guardrails (CASSANDRA-17153) are off and,
by the source comment, check only the added elements (`Maps.java:476-478`). The workload (600 entries of 1 MiB in one map) is
inside every documented limit. Whether this is a sizing gap or accepted documented behavior ("collections are for small data") is
stated in §4.

**JIRA prior art (checked 2026-11-21, read only; nothing posted).**

| Query / source | Hits | Relevant |
|---|---|---|
| Survey `jira-oom-survey.csv` (604 rows), grep `DataOutputBuffer\|scratch\|direct buffer memory\|large row\|huge row\|large collection\|wide row` | 24 | **CASSANDRA-16764** *Compaction repeatedly fails validateReallocation exception* (Unresolved/Triage Needed): a ≈ 2 GB cell; compaction serializes the row into a `DataOutputBuffer` that cannot pass 2 GB, and 16–24 GB heaps were exhausted — the same row-body site at the 2 GiB ceiling, heap-side, not a direct OOM below it. CASSANDRA-16 (0.7, whole wide row in compaction, fixed by lazily compacted rows; 5.0.9 compaction streams partitions but **not** rows). CASSANDRA-12477, -21529 (direct OOM in compaction from BufferPool/chunk-cache load, different holder). CASSANDRA-10592, -11838, -11937 (DOB overflow and recycling; not this path). |
| REST `text ~ "scratchBuffer"` | 8 | **CASSANDRA-16471** (Fixed 5.0): adds `cassandra.dob.allocate_type` "as a means to control memory allocations" (direct or on-heap) — moves the buffer, does not bound it (used in arm H). CASSANDRA-20167, -21535 (write-path allocation cleanups). None on row size. |
| REST `text ~ "DataOutputBuffer" AND (compaction OR flush) AND (OutOfMemoryError OR "direct buffer memory")` | 6 | 16764 (above); **CASSANDRA-20918** *cursor-based low allocation compaction* (Fixed **6.0** only; not in 5.0.9); CASSANDRA-8670 (*Large columns + NIO memory pooling causes excessive direct memory usage*, Fixed 2.2: JDK temporary direct-buffer cache, different holder); 14096, 18398, 18648 unrelated. |
| REST `text ~ "expandToFit"` | 3 | 16764, 16471, 14649 (index summaries > 2G). |
| REST `text ~ "serializeRowBody"` | 19 | 16060 (Invalid; coordinator read DOB realloc on large values); 21083 (flush logic, 6.0); none on the SSTable scratch buffer's in-use size. |
| REST `summary ~ "large row"/"huge row"/"big row"/"large collection"` with compaction/flush | 13 | 0.x–1.x era large-row compaction tickets (3095, 3758, 4316, 7543 …), all pre-3.0 storage engine; none on the 3.0+ scratch buffer. |

**JIRA verdict: `new`** for a direct-memory OOM from the SSTable row-body scratch buffer below the 2 GiB array cap (closest:
CASSANDRA-16764, open, heap-side at the cap). Not a known-fixed bug in 5.0.9 (the cursor compaction of CASSANDRA-20918 is 6.0
only), so this is not a positive control.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

Direction: **unprotected accumulation** (no control applies to the in-use size of the scratch buffer; the only bound is the
implicit one, "the size of one row", which nothing enforces). Technique note: none fits exactly; the shape follows U3 (golden
data, matched payload, add-a-bound intervention) and the budget search of the protocol's standing rule.

1. Every write `UPDATE u12.t SET m = m + {k: <1 MiB blob>} WHERE pk = 0 AND ck = 0` adds one cell to the non-frozen map `m`. The
   only size checks on the write are per write: the native frame (16 MiB), `max_mutation_size` (16 MiB = `commitlog_segment_size`/2,
   `DatabaseDescriptor.java:898-899`), and the collection guardrails, which are off and see only the added fragment
   (`Maps.java:476-488`).
2. The memtable merges the appends into one row; each flush writes that fragment (≤ the memtable cleanup size) as one row of one
   SSTable. The SSTables of one partition each hold a fragment of the same row.
3. Compaction merges the fragments: each source row is deserialized whole onto the heap (`UnfilteredSerializer.java:619`,
   `readComplexColumn` `:662-690`, one heap value per cell; OC-85), merged into one row, and written by
   `SortedTablePartitionWriter.addUnfiltered` → `UnfilteredSerializer.serialize` (`SortedTablePartitionWriter.java:143`).
4. For an SSTable header, `UnfilteredSerializer.java:193-203` takes the thread's scratch buffer
   (`DataOutputBuffer.scratchBuffer.get()`, `:195`), serializes the **whole row body** into it (`serializeRowBody`, `:197`), then
   writes its size and copies it to the file (`:199-203`). The scratch buffer is `ByteBuffer.allocateDirect` by default
   (`DataOutputBuffer.java:55`, `:87`).
5. Each cell value is written with one `write(ByteBuffer)` (`BufferedDataOutputStreamPlus.java:124-138`): when it does not fit, the
   rest triggers `expandToFit(remaining)` (`DataOutputBuffer.java:174-181`), which allocates the new buffer, copies, and only then
   frees the old one (`setBuffer` → `FileUtils.clean`, `:183-187`). The new size is `max(2c, c + count)` while `c ≤ 64 MiB`
   (`DOUBLING_THRESHOLD`, `:48`), else `max(1.5c, c + count)` (`calculateNewSize`, `:158-172`), saturated at
   `MAX_ARRAY_SIZE` = 2³¹ − 9 (`:118`, `:149-155`, `BufferOverflowException` above).
6. With 1 MiB cells, the capacity sequence is 128 B × 2ᵏ up to 64 MiB, then 128, 192, 288, 432, 648, 972, 1,458, 2,047.99 MiB.
   The growth from c to c′ holds c + c′ of direct memory at once. Nothing checks it: `DOB_MAX_RECYCLE_BYTES` acts only at `close()`
   (`DataOutputBuffer.java:73-80`), after the row is written. The JVM's own limit stops it: `Bits.reserveMemory` throws
   `OutOfMemoryError: Direct buffer memory` from `allocateDirect` in `expandToFit` on the compaction thread.
7. On that error `JVMStabilityInspector` logs `OutOfMemory error letting the JVM handle the error:` and then forces a heap OOM
   (`JVMStabilityInspector.java:123-127`, `:193-200`), which triggers `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError=kill -9`.
   The **initiating** error is the direct OOM (V5).

### 2.2 Protection map (fixed before any reading)

| # | Domain / holder | Allocation and owner; release | Local contract (counter, limit) | Scope × multiplicity | What happens at the limit |
|---|---|---|---|---|---|
| P1 | **Claimed holder:** SSTable row-body scratch `DataOutputBuffer` (direct) | `expandToFit` `DataOutputBuffer.java:178` via `allocate` `:87`; owner the compaction (or flush) thread's `FastThreadLocal` (`:63-92`); old buffer freed after the copy (`:186`); buffer > 1 MiB freed at `close()` | **None on the in-use size.** `DOB_MAX_RECYCLE_BYTES` (1 MiB) caps only what is **kept** after `close()`; `MAX_ARRAY_SIZE` is a 2 GiB type bound (throws, not OOM) | per thread; one row at a time per thread; threads = `concurrent_compactors` (2 on ms0611) + `memtable_flush_writers` (2) | JVM `MaxDirectMemorySize` → `OutOfMemoryError: Direct buffer memory` |
| P2 | Row size (what feeds P1) | the stored row; cells from any number of writes | `max_mutation_size` 16 MiB **per write**; `native_transport_max_frame_size` 16 MiB **per request**; `max_value_size` 256 MiB **per cell** on read; `collection_size_fail_threshold` null and `items_per_collection_fail_threshold` −1 (off; and per added fragment, `Maps.java:476-488`); `column_value_size_fail_threshold` null (per value); `partition_size_fail_threshold` null (off; and checked in `SortedTableWriter.endPartition` `:244` **after** the partition is written) | — | none applies to a stored row |
| P3 | Merged row on the heap (OC-85; co-tenant, not claimed) | `readComplexColumn` per cell (`UnfilteredSerializer.java:662-690`); sources + merged row while the partition is written | none | per compaction thread | Java heap OOM (not expected first; §2.4) |
| P4 | Compaction concurrency and rate | `CompactionExecutor` | `concurrent_compactors` = min(8, max(2, min(cores, data dirs))) = **2** (`DatabaseDescriptor.java:777-778`); `compaction_throughput` 64 MiB/s (a rate, not memory) | per node | bounds threads, not bytes |
| P5 | Flush fragments | memtable flush writer (same P1 site) | `memtable_heap_space` = heap/4 = 512 MiB; `memtable_cleanup_threshold` = 1/(1 + 2) = 0.33 → flush at ≈ 170 MiB (`DatabaseDescriptor.java:586-587`, `:753-763`); `memtable_allocation_type: heap_buffers` (`cassandra.yaml:825`) | 2 flush writers | bounds a **flush** row to ≈ 170 MiB (P1 peak at flush ≤ 128 + 192 = 320 MiB), not a compacted row |
| P6 | Other direct tenants (baseline B_d) | networking `BufferPool` (`networking_cache_size` = min(128 MiB, heap/16) = 128 MiB, `DatabaseDescriptor.java:573-574`); chunk cache **off** (`file_cache_enabled` false → `ChunkCache.instance` null, `ChunkCache.java:54`); compressed reader/writer buffers (KiB); Netty's own pooled arenas use Netty's counter, not the JDK pool | per pool | each pool capped; measured as B_d |
| P7 | Commit-log scratch (U1/R7 site) | `CommitLog.java:306`, one 1 MiB write → ≈ 2 MiB, replaced at close | `max_mutation_size` | `MutationStage` threads | not a factor (writes stop before the trigger in T/A/B/I/S arms) |

**K (control counter):** none exists for P1. The only check that reads the buffer's capacity is `close()` (`:73`), which runs after
the row; stage 2 records whether it was reached (it is not reached on the failing allocation). **U** = physical direct memory from
the JDK `java.nio:type=BufferPool,name=direct` pool (`Bits` counter) and, at failure, the heap dump's `DirectByteBuffer` owners.

### 2.3 Configuration and budget audit

- **Build:** `ms0611:/mydata/s4/cassandra-base` (5.0.9-SNAPSHOT jar, built from the pinned source), copied to `/mydata/s4/u12/cassandra`
  (stage 2 records the jar's sha256). The intervention build is a separate copy (§2.8). JDK 11.0.33 (aarch64), G1 (shipped
  `jvm11-server.options`), Ubuntu 22.04, kernel as found, cgroup v2, swap 8 GiB on the host (kept at 0 for the node:
  `systemd-run --user --scope -p MemorySwapMax=0`; **no MemoryMax**, no container budget).
- **Capacity constraints (V6), all at shipped defaults, resolved at the 2 GiB heap:** `DOB_MAX_RECYCLE_BYTES` 1 MiB;
  `cassandra.dob.allocate_type` unset → DIRECT; `DOB_DOUBLING_THRESHOLD_MB` 64; `max_mutation_size` 16 MiB;
  `native_transport_max_frame_size` 16 MiB; `max_value_size` 256 MiB; collection/partition/column-value guardrails off;
  `concurrent_compactors` 2; `memtable_flush_writers` 2; `memtable_heap_space` 512 MiB; `memtable_cleanup_threshold` 0.33;
  `compaction_throughput` 64 MiB/s; `networking_cache_size` 128 MiB; `file_cache_enabled` false (`file_cache_size` 512 MiB would
  apply if enabled); table compaction STCS default (`min_threshold` 4, `max_threshold` 32); compression LZ4 default.
  Other settings: shipped `cassandra.yaml` with only directories, addresses and `num_tokens` as needed for one local node
  (environment); `AllowAllAuthenticator` (default).
- **Budgets (V7).** Claimed node: a **4 GiB-RAM** Cassandra node. `cassandra-env.sh` resolves there heap = ½ RAM = **2048 MiB** and
  `MaxDirectMemorySize` = ¼ RAM = **1024 MiB** (`cassandra-env.sh:58-67`, `:139-158`). ms0611 has 62 GiB, so stage 2 sets
  `MAX_HEAP_SIZE=2048M HEAP_NEWSIZE=512M MAX_DIRECT_MEMORY_SIZE=1024M` (the values cassandra-env.sh computes for 4 GiB; on ms0611
  the unset value would be 15.7 GiB direct — record it). Both ≥ 512 MiB: V7 met by the standing rule. Budget search (S arms):
  8 GiB node → heap 4096M / direct 2048M; 12 GiB node → heap 6144M / direct 3072M (same formula).
- **Supporting deviations (label `diagnostic` only if used in the claimed arm):** `nodetool disableautocompaction` **only while
  building golden data** (not in any measured run); `nodetool compact` as a fallback trigger only if the background compaction has
  not started 90 s after startup (recorded per run; the claim does not depend on which, both are `CompactionTask` on a
  `CompactionExecutor` thread). Byteman is used only in the optional diagnostic run Dg.

### 2.4 Ceiling arithmetic

Row body R for n entries of 1 MiB: n × (1,048,576 + ≈ 9) B, i.e. R ≈ n MiB. The scratch buffer's last growth and its two-buffer
peak (old + new) for R in each band, and the result at each budget (B_d = other direct, expected 10–60 MiB, measured):

| R (MiB) band | last growth (MiB) | P1 peak (MiB) | at 1,024 direct | at 2,048 | at 3,072 |
|---|---|---|---|---|---|
| (64, 128] — arm A (6 × 100) | 64 → 128 | 192 | survive | survive | survive |
| (288, 432] — arm B (420) | 288 → 432 | **720** | survive (margin 304 − B_d) | survive | survive |
| (432, 648] — arms T, I (600) | 432 → 648 | **1,080** | **OOM** (> 1,024 even at B_d = 0) | survive | survive |
| (972, 1,458] — S1 (1,000) | 972 → 1,458 | **2,430** | OOM | **OOM** | survive |
| (1,458, 2,047.99] — S2 (1,500) | 1,458 → 2,047.99 | **3,506** | OOM | OOM | **OOM** |
| ≥ 2,048 | — | — | `BufferOverflowException` (CASSANDRA-16764), no OOM | | |

So at 1 GiB direct the endpoint is reached iff R > 432 MiB, and with one compaction thread no direct limit above ≈ 3,506 MiB +
B_d can be reached by this holder (claimed node range: RAM ≤ ≈ 14 GiB; two compaction threads with two such rows double it, arm S3).
Heap at T: sources ≈ 600 MiB of cell values + baseline ≈ 0.2–0.3 GiB ≈ 0.9 GiB of 2 GiB, so the direct OOM comes first;
at S1 ≈ 1.3 GiB of 4 GiB; at S2 ≈ 1.8 GiB of 6 GiB.

### 2.5 Workload and environment

- **Node:** `ms0611` (Utah m400, aarch64, 8 cores, 62 GiB, `/mydata` ≈ 35 GiB free; checked read-only 2026-11-21 08:05 EST:
  no Java process running, `/mydata/s4/cassandra-base` present, JDK 11.0.33, Ant, Python 3.10). One local node, RF 1. Work only in
  `/mydata/s4/u12/` (owned by jason92 under `/mydata/s4`); **never touch `/mydata/s2r2` or `/mydata/u1r2`**. Data, commit log, logs
  and dumps on `/mydata`. The client runs on ms0611 (loopback; a single client thread is light) — record it.
- **Schema:** `CREATE KEYSPACE u12 WITH replication = {'class':'SimpleStrategy','replication_factor':1};`
  `CREATE TABLE u12.t (pk int, ck int, m map<int, blob>, PRIMARY KEY (pk, ck));` (all table options default).
- **Client:** native protocol **v4** (Lessons: large v5 requests leave unreturned direct buffers), one connection, one request in
  flight, prepared `UPDATE u12.t SET m = m + ? WHERE pk = ? AND ck = ?` with a one-entry map `{k: 1 MiB of os.urandom}` (random so
  LZ4 does not shrink files); k = 0..n−1. Either the bundled Python driver (`lib/cassandra-driver-internal-only-3.29.0.zip`,
  `protocol_version=4`) or a Java client on `lib/cassandra-driver-core-3.12.1-shaded.jar`. Count acknowledged writes; any failed write
  invalidates the golden set.
- **Golden data sets** (built once, at the T configuration 2048M/1024M, then `nodetool drain`, stop, tar the data and commit-log
  directories): `nodetool disableautocompaction u12 t` right after `CREATE TABLE`; write in blocks of 100 entries, `nodetool flush u12 t`
  after each block (each flush row ≤ 100 MiB, P1 peak ≤ 192 MiB). Check after build: SSTable count and `Data.db` sizes.

  | Golden | Rows | Entries per row | SSTables | ≈ R (largest row) | Used by |
  |---|---|---|---|---|---|
  | G600 | 1 (ck 0) | 600 | 6 × ≈ 100 MiB | 600 MiB | T, I, H, S1-control |
  | G6x100 | 6 (ck 0..5; block j writes ck j) | 100 | 6 × ≈ 100 MiB | 100 MiB (same 600 MiB partition) | A |
  | G420 | 1 | 420 | 5 × 84 (blocks of 84) | 420 MiB | B |
  | G1000 | 1 | 1,000 | 10 × 100 | 1,000 MiB | S1 |
  | G1500 | 1 | 1,500 | 15 × 100 | 1,500 MiB | S2 |

- **One run** (all arms except N): fresh run dir `/mydata/s4/u12/runs/<run>/`; untar the golden; start the node with the arm's
  budget (autocompaction is enabled by default on start); STCS sees ≥ 4 similar SSTables and starts a background `COMPACTION`.
  If none has started 90 s after "Startup complete", run `nodetool compact u12 t` (record). Wait for the endpoint: OOM (process
  exits) or compaction finished (one SSTable left, "Compacted" line in `system.log`) or **300 s** after compaction start. Stop the
  node, collect, delete the run's data copy (keep logs; keep the heap dump of the first failing T run, compressed, delete others
  after extracting the holder report, §2.6).
- **Arm N (natural path, no operator action):** fresh empty node at 2048M/1024M, autocompaction on, no `nodetool flush`; write 700
  entries to one row at one request in flight. Expected: memtable flushes at ≈ 170 MiB on their own (P5), STCS compacts the first 4
  fragments (R ≈ 640–680 MiB) while writes continue → direct OOM. Records flush sizes and when the compaction starts.

### 2.6 Instruments (U independent of K)

| # | What | How | Rate |
|---|---|---|---|
| O1 | **U_direct** = JDK direct pool `MemoryUsed`, `TotalCapacity`, `Count`; heap used; `Compaction` metrics `BytesCompacted`, `PendingTasks`; networking `BufferPool` size | JMX sampler (adapt `R7/harness/U1R2Sample.java`), keeps writing NA when the node is down so the death time shows | 250 ms |
| O2 | RssAnon, VmHWM of the node | `/proc/<pid>/status` | 1 s |
| O3 | GC log | the `-Xlog:gc` that `cassandra-env.sh`/`jvm11-server.options` set (add `-Xlog:gc*:file=…` if absent; record) | continuous |
| O4 | Initiating failure | `system.log`/`debug.log`: first `OutOfMemoryError`, its message (`Direct buffer memory`), thread name (`CompactionExecutor:N`), stack through `DataOutputBuffer.expandToFit` ← `UnfilteredSerializer.serialize` ← `SortedTablePartitionWriter.addUnfiltered` ← `CompactionTask` (use `grep -A40`; Lessons: messages on the next line) | after run |
| O5 | Holder at failure | the hprof from the forced heap OOM (`HeapDumpPath` under the run dir via `CASSANDRA_HEAPDUMP_DIR`): `R7/harness/hprof_direct.py` → live `DirectByteBuffer` owners by capacity and referrer chain (expected: one 452,984,832 B = 432 MiB owner ← `DataOutputBuffer$1$1` ← `FastThreadLocal` of the compaction thread); plus a class histogram (`byte[]` ≈ 600 × 1 MiB = the P3 row) | at failure |
| O6 | Compaction progress and path | `nodetool compactionstats` (operation type, bytes) | 2 s |
| O7 | Data state | `ls -l` of `Data.db` before/after; `system.log` "Compacted (…) N sstables to … bytes" for survivors | before/after |
| Dg | (optional, diagnostic, not part of V1) exact growth sequence | Byteman rule at `DataOutputBuffer.expandToFit` AT INVOKE `setBuffer` printing thread name, old capacity, new capacity (phase-1 `dob-ledger.btm` as template) on G600 | event |

Predictions are judged on O1/O4/O5. The 250 ms sampler may miss the c + c′ transient; the failing allocation leaves c = 432 MiB live,
so the sampled peak before the failure is ≥ 432 MiB + B_d and the dump shows the 432 MiB owner.

### 2.7 Arms, dial and predicted response

| Arm | Golden / load | Build | Budget heap / direct | Runs | Predicted | Role |
|---|---|---|---|---|---|---|
| **T** (test) | G600 restart | unpatched | 2048M / 1024M | 3 | **direct OOM 3/3** on `CompactionExecutor`, ≤ 120 s after compaction start; O1 peak ≥ 432 + B_d MiB (≤ 1,024); heap peak 0.8–1.2 GiB; dump: 432 MiB scratch owner | V1 |
| **A** (matched payload) | G6x100 restart | unpatched | 2048M / 1024M | 3 | **no OOM 0/3**; compaction completes (one ≈ 600 MiB SSTable); O1 peak ≤ 192 + B_d MiB | V2 (same bytes, same partition, same SSTables and compaction; only the row size differs) |
| **B** (nearest surviving dial) | G420 restart | unpatched | 2048M / 1024M | 3 | **no OOM 0/3**; O1 peak ≤ 720 + B_d MiB (margin ≈ 25–30 %) | V2 / boundary |
| **I** (intervention) | G600 restart | **patched** (§2.8) | 2048M / 1024M | 3 | **no OOM 0/3**; compaction completes, output ≈ 600 MiB; O1 peak ≈ B_d (no P1 growth); heap as T | V4 |
| N (natural path) | 700 appends, no nodetool | unpatched | 2048M / 1024M | 3 | direct OOM 3/3 at the first STCS compaction (R ≈ 4 × 160–170 MiB) | deployment path, V1 for condition N |
| S1 (budget search) | G1000 restart | unpatched | 4096M / 2048M | 3 | direct OOM 3/3 at the 972 → 1,458 MiB growth (peak 2,430) | V7 search |
| S1-c | G600 restart | unpatched | 4096M / 2048M | 1 | no OOM (peak 1,080 < 2,048) | boundary at S1 budget |
| S2 (budget search) | G1500 restart | unpatched | 6144M / 3072M | 1–3 | direct OOM at the 1,458 → 2,047.99 MiB growth (peak 3,506) | V7 search, largest failing direct |
| H (supplementary) | G600 restart | unpatched + `-Dcassandra.dob.allocate_type=onheap` | 2048M / 1024M | 1 | no direct OOM; heap need ≈ 600 + 432 + 648 MiB + baseline ≈ 1.9 GiB → heap OOM or severe GC likely (the CASSANDRA-16471 knob moves the holder, does not bound it) | OC-85 / knob note |
| S3 (optional) | two tables, each a 1,500-entry row, restart | unpatched | 8192M / 4096M | 1 | two compaction threads each at peak 3,506 → OOM above 3.5 GiB direct | multiplicity extension |
| Dg (optional) | G600 restart + Byteman | unpatched | 2048M / 1024M | 1 | growth lines …, 192→288, 288→432, then OOM at 432→648 | diagnostic attribution |

**Validity rules (set before readings).** A run counts only if (a) the golden set's SSTable count and sizes match the table above
(± 2 %), (b) a compaction of `u12.t` started (O6 or log), and (c) for OOM runs the first OOM is `Direct buffer memory` on a
compaction thread with `expandToFit` in its stack. A run where the first OOM is a heap OOM, or on another thread, is recorded as a
miss of the prediction, not as a T success. Shakedowns (one T run before golden sets are final, any harness test) are not readings.

**Stopping budget:** each run ≤ 300 s after compaction start (≤ 8 min wall including copy/start/stop); no run starts after **13:15
EST**; no escalation after the planned endpoint; arms beyond those in the table need a dated amendment before their readings.

### 2.8 Controls and intervention (why these)

- **A (matched payload):** the same 600 × 1 MiB values, written in the same order into the same partition, flushed into the same six
  ≈ 100 MiB SSTables and compacted by the same task, so data volume, heap use, compaction work and SSTable count match T; only the
  row the scratch buffer has to hold differs (100 MiB vs 600 MiB). This is also the data model the docs recommend (clustering rows).
- **B (nearest surviving):** the largest row below the 432 MiB band edge; its peak (720 MiB) is the highest any surviving row can
  reach at 1 GiB, so B shows the boundary is the band arithmetic, not the data volume.
- **I (add the bound — remove the whole-row copy):** a diagnostic patch to `UnfilteredSerializer.serialize` that, for SSTable
  headers, computes the body size first with the existing `serializedRowBodySize` (`UnfilteredSerializer.java:333-364`, which already
  adds the previous-size vint for SSTable headers) and streams the body straight to the writer — the same scheme the same file uses
  for range-tombstone markers (`:289-293`). Diff to save as `harness/intervention.diff`:

  ```java
          if (header.isForSSTable())
          {
  -           try (DataOutputBuffer dob = DataOutputBuffer.scratchBuffer.get())
  -           {
  -               serializeRowBody(row, flags, helper, dob);
  -
  -               out.writeUnsignedVInt(dob.position() + TypeSizes.sizeofUnsignedVInt(previousUnfilteredSize));
  -               // ...
  -               out.writeUnsignedVInt(previousUnfilteredSize);
  -               out.write(dob.unsafeGetBufferAndFlip());
  -           }
  +           // U12 intervention: no whole-row scratch copy; size computed up front (as for markers, :289-293)
  +           out.writeUnsignedVInt(serializedRowBodySize(row, helper, previousUnfilteredSize, version));
  +           out.writeUnsignedVInt(previousUnfilteredSize);
  +           serializeRowBody(row, flags, helper, out);
          }
  ```

  Build in a **separate copy** `/mydata/s4/u12/cassandra-patched` (never in the tree a node runs from): `javac --release 11` of
  `UnfilteredSerializer.java` against `build/classes/main:lib/*:build/lib/jars/*` (or whatever the copy's classpath holds), then
  `jar uf build/apache-cassandra-5.0.9-SNAPSHOT.jar` with every `UnfilteredSerializer*.class`; fallback `ant jar` after deleting
  those class files (Lessons: Ant timestamps). Record both jars' sha256. **Correctness check of the patched format** (one I run):
  after the compaction, restart and run `nodetool verify -e u12 t` (extended verify deserializes every row; 600 MiB on a 2 GiB heap
  is within T's heap) — it must pass. If the patch cannot be built or verified by 10:30, the intervention is recorded as infeasible
  with that reason and the status carries `(no intervention)`; A then remains the attribution evidence.
- **Throughput note:** I does the same compaction work (output size recorded), so a "no OOM" in I is not a stopped workload.

### 2.9 Time plan (stage 2: 2026-11-21 ≈ 09:00–14:00 EST; no run starts after 13:15; case file written by 14:00)

| EST | Step |
|---|---|
| 09:00–09:15 | check freeze hash; check ms0611 (`ps`, `df`); `/mydata/s4/u12/{cassandra,cassandra-patched,golden,runs}`; copy build; harness (start/stop, sampler, client, run script with `EXPECTED:` lines) |
| 09:15–09:35 | build G600 first; one T shakedown on it (not a reading); patched build in parallel (separate tree, CPU allows) |
| 09:35–10:00 | build G6x100, G420 (G1000, G1500 can build later, between runs) |
| 10:00–10:50 | T×3, A×3, B×3 (interleave T, A, B; ≈ 5 min each) |
| 10:50–11:15 | I×3 + `nodetool verify` once |
| 11:15–11:45 | N×3 |
| 11:45–12:30 | G1000 + S1×3 + S1-c×1 |
| 12:30–13:10 | G1500 + S2×1 (×3 if time) |
| 13:10–13:15 | H×1 or Dg×1 only if they fit before 13:15 |
| 13:15–14:00 | stop everything; self-check script re-parses raw logs; write §3–§4, `_INDEX.md` row, candidate-list write-back per the playbook |

**Drop order (first dropped first):** S3 → Dg → H → S2 runs 2–3 → N runs 2–3 → S1-c → S1 runs 2–3 → S2 → N → S1. **Never
dropped:** T×3, A×3, I×3 (B×3 may drop to B×1 only if I needs the time; then V2 rests on A).

### 2.10 What stays on ms0611

Stage 2 stops every process it started (node by PID, sampler, client) and deletes run data copies and extra dumps; it may keep
`/mydata/s4/u12/` (build copies ≈ 1 GB, goldens ≈ 4.2 GB, logs, one compressed dump) and reports its size.

sha256 of §1–§2 at freeze: e838bf1a6c241f5927ef07a861141b8ef6f63752d31dfbf13b2a495b9757afec (sha256 of the bytes from the line `## 1. Candidate` up to and including the blank line before this line) · amendments after the freeze: A1 (2026-11-21 08:53 EST, §3.0: `nodetool verify` needs `-f` in 5.0.9) · hash re-checked by stage 2 at 08:13 and 09:16 EST: matches

## 3. Runs (stage 2)

### 3.0 Amendments (dated, each before the reading it affects)

- **A1 — 2026-11-21 08:53 EST, §2.8 correctness check of the patched format.** Reason: the step cannot run as written —
  in 5.0.9 `nodetool verify -e u12 t` refuses to run ("verify is disabled unless a [-f|--force] override flag is provided.
  See CASSANDRA-9947 and CASSANDRA-17017", exit 1; run I1, `runs/I1/verify/verify.out`). Change: the check is
  `nodetool verify -e -f u12 t` (extended + the override flag; no other change), run once in a separate run `I-v` (G600,
  patched build, 2048M/1024M, after the background compaction, restart, then verify) after the main queue. No verify
  reading had been taken.

### 3.1 Environment (as run)

- **Node:** `ms0611` (node3.jason92-326377, Utah m400), **aarch64**, 8 cores, 62.7 GiB RAM, Ubuntu 22.04.1, kernel
  5.15.0-191-generic, cgroup v2, swap 8 GiB on the host and **0 for the node** (`systemd-run --user --scope -p MemorySwapMax=0`;
  `memory.swap.max=0`, `memory.max=max`, recorded per run). Checked before use (08:13 EST): no `CassandraDaemon`, no Java
  process; `/mydata` 35 GiB free. Nothing else ran on the node during the runs (one measured node at a time; the client and
  samplers ran on the same host, loopback). `/mydata/s2r2` and `/mydata/u1r2` were not touched.
- **JDK** OpenJDK 11.0.33+9 (aarch64), G1 with the shipped `jvm11-server.options` (`-XX:G1HeapRegionSize=16m`,
  `-XX:+AlwaysPreTouch`, `-XX:+HeapDumpOnOutOfMemoryError`), `-XX:OnOutOfMemoryError=kill -9 %p` from `cassandra-env.sh`,
  GC log from `cassandra-env.sh`'s default `-Xlog:gc=info,heap*=trace,…` (O3; no extra flag added).
- **Builds:** unpatched `/mydata/s4/u12/cassandra` (copy of `ms0611:/mydata/s4/cassandra-base`), jar sha256
  `e55f4f2974cb6120712a5cdfbbed9ee1ba25d97b887cbe71b64fd194f3b5a942`; patched `/mydata/s4/u12/cassandra-patched` (separate copy;
  `UnfilteredSerializer.java` patched per §2.8, `javac --release 11` against `build/classes/main:lib/*:build/lib/jars/*`,
  `jar uf`), jar sha256 `f6cfc2534764b9f48e26099b7d4ce0d25fbe94420d543ecdced2b0224584573c`; diff in
  [`harness/intervention.diff`](harness/intervention.diff) (the frozen diff, verbatim in effect). Repository HEAD at stage 2:
  `08f0194a3`.
- **Configuration:** shipped `cassandra.yaml`; diff [`logs/yaml.diff`](logs/yaml.diff) = data/commitlog/hints/saved_caches/cdc
  directories and `num_tokens: 1` (environment). One data directory → `concurrent_compactors` 2. Budgets via the documented
  `cassandra-env.sh` overrides `MAX_HEAP_SIZE`, `HEAP_NEWSIZE=512M` (ignored with G1, as `cassandra-env.sh` says),
  `MAX_DIRECT_MEMORY_SIZE`. **Resolved** (from the JVM command line, every run): T/A/B/I/N/H/Dg `-Xms2048M -Xmx2048M
  -XX:MaxDirectMemorySize=1024M`; S1/S1-c `4096M`/`2048M`; S2 `6144M`/`3072M`. Unset on ms0611, `cassandra-env.sh` would give
  heap 15,872 MiB and direct 7,936 MiB (RAM > 31.75 GiB branch of `calculate_heap_sizes`; the design's "15.7 GiB direct" was
  the ¼-RAM figure, which this branch does not use). Netty sees the same 1,073,741,824 B limit (dump: `MAX_DIRECT_MEMORY`).
- **Client:** [`harness/U12Load.java`](harness/U12Load.java), driver 3.12.1 shaded, protocol **v4**, one connection, one request
  in flight, `UPDATE u12.t SET m = m + ? WHERE pk = ? AND ck = ?` with one 1 MiB `SecureRandom` value per write.
- **Harness** ([`harness/`](harness/)): `ctl.sh` (gen/start/stop; stop only kills a PID whose command line carries this case's
  log dir), `golden.sh`, `run.sh` (one run; endpoint = node exit / `Compacted` line for `u12.t` / 300 s), `queue.sh`
  (sequential runs, 13:15 cut-off, dump → `hprof_direct.py` → delete), `U12Sample.java` (O1, JMX 250 ms; JDK
  `BufferPool/direct` MemoryUsed/TotalCapacity/Count, heap used, compaction metrics), `analyze.py` (per-run self-check that
  re-parses the raw `samples.csv`, `rss.csv`, `system.log`; compaction start = the `Compacting (…) […/data/u12/t-…]` log
  timestamp), `u12-dg.btm` (Dg), queues `q-main.txt`, `q-verify.txt`. Full run directories:
  `ms0611:/mydata/s4/u12/runs/<run>/` (`progress.txt`, `samples.csv`, `rss.csv`, `compactionstats.txt`, `logs/{system,debug,gc,launch}.log`,
  `first-oom.txt`, `direct-holders.txt`, `outcome.txt`); queue log `runs/queue.log`; one dump kept, `runs/T1/dumps/*.hprof.gz`
  (16 MB).
- **Golden sets** (built 08:17–08:41 EST, unpatched, 2048M/1024M, autocompaction disabled after `CREATE TABLE`, flush per block,
  drain; every write acknowledged, 0 failures; [`logs/goldens.txt`](logs/goldens.txt)) — all within the ± 2 % validity rule:

  | Golden | SSTables | `Data.db` each (B) | Row |
  |---|---|---|---|
  | G600 | 6 | 105,332,508–105,332,510 (100.45 MiB) | 1 row × 600 entries |
  | G6x100 | 6 | 105,332,507–105,332,510 | 6 rows × 100 entries, one per SSTable |
  | G420 | 5 | 88,479,306–88,479,309 (84.38 MiB) | 1 row × 420 |
  | G1000 | 10 | 105,332,506–105,332,510 | 1 row × 1,000 |
  | G1500 | 15 | 105,332,505–105,332,510 | 1 row × 1,500 |

- **Shakedowns (not readings):** `shake-T1` (08:21; the harness found no PID because the pidfile is written late, so no
  samples; the node died of a direct OOM 3.85 s after the compaction started) and `shake-T2` (08:23; direct OOM; a log pattern
  matched `/mydata/s4/u12/` and mislabelled the endpoint). Both harness faults were fixed before T1 (PID from the java command
  line; patterns anchored on `/data/u12/t-`).

### 3.2 Runs (2026-11-21, 08:41–09:14 EST; all background `COMPACTION`, never `nodetool compact`)

U_direct = JDK direct pool `MemoryUsed` (O1, 250 ms). B_d = median of the samples before the compaction start. "t_OOM" = seconds
from the `Compacting` line to the first `OutOfMemoryError` (log timestamps). Peaks are sampled maxima; the c + c′ transient lasts
≈ 0.3–0.5 s and was caught in every run.

| Run | Golden / load | Build | Heap / direct (MiB) | Outcome | First error, thread | t_OOM / compaction time | B_d | U_direct peak (over B_d) | Heap peak | VmHWM |
|---|---|---|---|---|---|---|---|---|---|---|
| T1 | G600 | base | 2048 / 1024 | **direct OOM** | `Direct buffer memory`, `CompactionExecutor:1`, `expandToFit` ← `UnfilteredSerializer.serialize` ← `SortedTablePartitionWriter.addUnfiltered` ← `CompactionTask` | 4.06 s | 17.1 | 829.9 (812.8) | 896 | 3,406 |
| T2 | G600 | base | 2048 / 1024 | **direct OOM** | same | 4.08 s | 17.1 | 829.9 (812.8) | 912 | 3,414 |
| T3 | G600 | base | 2048 / 1024 | **direct OOM** | same | 4.04 s | 17.1 | 829.9 (812.8) | 896 | 3,405 |
| A1–A3 | G6x100 | base | 2048 / 1024 | survived; 6 → 1 SSTable, 602.717 → 602.718 MiB | none | 14.9 s | 17.1 | 291.9 (274.8) ×3 | 1,008 | 2,889–2,902 |
| B1–B3 | G420 | base | 2048 / 1024 | survived; 5 → 1, 421.902 MiB | none | 10.4 s | 17.1 | 829.7 (812.6) ×3 | 800–816 | 3,403–3,414 |
| I1–I3 | G600 | **patched** | 2048 / 1024 | survived; 6 → 1, 602.717 → 602.717 MiB (`Data.db` 631,995,039 B) | none | 13.3 s | 17.1–17.3 | 51.9–52.0 (34.6–34.9) | 992–1,008 | 2,646–2,652 |
| I-v | G600 | patched | 2048 / 1024 | survived (as I); restart; `nodetool verify -e -f u12 t`: **"succeeded. All 1 rows read successfully"**, exit 0 | none | 13.4 s | 17.1 | 51.9 (34.8) | 1,008 | 2,642 |
| N1 | 700 appends, no nodetool | base | 2048 / 1024 | **direct OOM** | same stack as T, `CompactionExecutor:1` | 4.07 s | 42.5 | 853.5 (811.0) | 1,301 | 3,521 |
| N2 | same | base | 2048 / 1024 | **direct OOM** | same | 4.24 s | 123.5* | 853.5 | 1,142 | 3,540 |
| N3 | same | base | 2048 / 1024 | **direct OOM** | same | 4.11 s | 43.5 | 853.5 (810.0) | 1,251 | 3,542 |
| S1-1–3 | G1000 | base | 4096 / 2048 | survived; 10 → 1, 1,004.529 MiB | none | 24.4 s | 17.1 | 1,843.4 (1,826.3) ×3 | 1,600–1,616 | 6,549–6,556 |
| S1c-1 | G600 | base | 4096 / 2048 | survived; 6 → 1 | none | 15.0 s | 17.1 | 1,234.9 (1,217.8) | 1,152 | 5,934 |
| S2-1–3 | G1500 | base | 6144 / 3072 | survived; 15 → 1, 1.471 GiB | none | 30.1 s | 17.1 | 2,788.0 (2,770.9) ×3 | 2,176–2,208 | 9,357–9,366 |
| H1 | G600 | base + `-Dcassandra.dob.allocate_type=onheap` | 2048 / 1024 | **heap OOM** (`Java heap space`, JVM-thrown, launch.log; dump 1.23 GB written, then `kill -9`) | heap | ≈ 6.7 s (gc.log `ReportJavaOutOfMemory` 07:07:31.56 local) | 17.1 | 21.1 (4.0) | 1,879 (last sample) | 2,610 |
| Dg1 | G600 + Byteman | base | 2048 / 1024 | **direct OOM** (as T) | same | 4.13 s | 17.2 | 829.9 (812.7) | 976 | 3,451 |

\* N2's B_d median includes networking buffers of the concurrent client writes; its peak equals N1/N3's.

**Growth sequence (O1 steps and Dg1).** T runs, U_direct over B_d after the compaction start: … 99 → 243 (96 + 144) → 219 (216
live) → 543 (216 + 324) → 813 (324 + 486) → 489 (486 live) → node dead 0.25–0.5 s later. Dg1 requested sizes on
`CompactionExecutor:1` ([`logs/Dg1-dg.txt`](logs/Dg1-dg.txt)): 1,048,588 · 2,097,176 · … · 67,109,632 (64.0007 MiB) · 100,664,448 ·
150,996,672 · 226,495,008 · 339,742,512 · **509,613,768 (486 MiB)** · **764,420,652 (729 MiB, the failing request)**, then
`close cap=509613768` (the try-with-resources `close()` during unwinding). B runs: the same steps up to 813 → 489, then the row
(420 MiB) fits in 486 MiB and the compaction finishes. A runs: 96 → 144 per 100 MiB row (243 = 96 + 144 transient), plus ≈ 35 MiB of
other compaction buffers (also seen in I). S1: … 729 + 1,093.5 = 1,822.5 (sampled 1,826.3); S1-c: 486 + 729 = 1,215 (1,217.8);
S2: 1,093.5 + 1,640.3 = 2,733.8 (+ ≈ 37, sampled 2,770.9). Samples: [`logs/T1-samples-window.csv`](logs/T1-samples-window.csv),
`B1-`, `A1-`, `I1-`, `S1-1-`, `S2-1-samples-window.csv`.

**Initiating failure (O4).** In every T/N/Dg run the first `OutOfMemoryError` in `system.log` is `Direct buffer memory` from
`Bits.reserveMemory` ← `ByteBuffer.allocateDirect` ← `DataOutputBuffer$1$1.allocate` (`DataOutputBuffer.java:87`) ←
`expandToFit` (`:178`) ← `BufferedDataOutputStreamPlus.write` ← `Cell$Serializer.serialize` ← `UnfilteredSerializer.writeComplexColumn`
← `serializeRowBody` ← `UnfilteredSerializer.serialize` (`:197`) ← `SortedTablePartitionWriter.addUnfiltered` (`:143`) ←
`CompactionTask.runMayThrow` ← `CompactionManager$BackgroundCompactionCandidate.run`, on `CompactionExecutor:1`; then
`JVMStabilityInspector` "OutOfMemory error letting the JVM handle the error" and "Force heap space OutOfMemoryError"
([`logs/T1-first-oom.txt`](logs/T1-first-oom.txt), [`logs/N1-first-oom.txt`](logs/N1-first-oom.txt)).

**Holder at failure (O5).** The forced-heap-OOM dump (T1, 85 MB, kept compressed) shows **no** live scratch buffer:
`DataOutputBuffer scratch 0.0 MiB`, owners 18.4 MiB in total ([`logs/T1-direct-holders.txt`](logs/T1-direct-holders.txt)). Reason
(Dg1): the failed `expandToFit` unwinds through the `try (DataOutputBuffer dob = scratchBuffer.get())` of `UnfilteredSerializer.java:195`,
whose `close()` frees the 486 MiB buffer (> `DOB_MAX_RECYCLE_BYTES`) before `JVMStabilityInspector` forces the heap OOM that
writes the dump. The holder is therefore shown by the failing allocation's stack, by the JDK pool at 250 ms before the failure
(530,464,505 B = 505.9 MiB = 486 MiB + B_d + ≈ 3 MiB, T1 t = 3.2–4.0 s), and by Dg1 (486 MiB live, 729 MiB requested, same thread). Heap at
failure 0.64–0.88 GiB of 2 GiB (P3, OC-85's co-tenant, not the cause).

**Arm N (natural path).** Each N run: 700 appends acknowledged, 0 failed (≈ 52 s); the memtable flushed by itself four times at
171.0 MiB (`memtable_cleanup_threshold` 0.33 × 512 MiB; "171.030MiB (33%) on-heap"), STCS compacted those four SSTables (≈ 684 MiB
row) ≈ 3 s after the last write and the node died of the same direct OOM 4.1–4.2 s later
([`logs/N1-flush-compaction.txt`](logs/N1-flush-compaction.txt)). No `nodetool`, no `disableautocompaction`.

### 3.3 Predictions against readings

| Prediction (§2.7, §2.6) | Reading | Held? |
|---|---|---|
| T: direct OOM 3/3 on `CompactionExecutor`, ≤ 120 s | 3/3, `CompactionExecutor:1`, 4.04–4.08 s | yes |
| T: O1 peak ≥ 432 + B_d, ≤ 1,024 | 829.9 MiB (486 live + 324 transient + B_d) | yes |
| T: heap peak 0.8–1.2 GiB | 0.88–0.89 GiB | yes |
| T: dump shows a 432 MiB scratch owner | dump shows none (freed by `close()` on unwind); live buffer was 486 MiB, the failing request 729 MiB (Dg1) | **no** (instrument and band arithmetic; see below) |
| A: 0/3, peak ≤ 192 + B_d | 0/3; peak 274.8 over B_d (96 + 144 + ≈ 35 other) | outcome yes, peak no |
| B: 0/3, peak ≤ 720 + B_d (margin 25–30 %) | 0/3; peak 812.6 over B_d, margin 194 MiB (19 %) | outcome yes, peak no |
| I: 0/3, compaction completes ≈ 600 MiB, O1 ≈ B_d | 0/3; 602.717 MiB, same `Data.db` size as the unpatched S1-c output; +35 MiB; verify passes (I-v) | yes |
| N: direct OOM 3/3 at the first STCS compaction of ≈ 4 × 160–170 MiB | 3/3, 4 × 171 MiB | yes |
| S1: direct OOM 3/3 at 2,048 | 0/3, peak 1,843.4 | **no** |
| S1-c: no OOM | no OOM, peak 1,234.9 | yes |
| S2: direct OOM at 3,072 | 0/3, peak 2,788.0 | **no** |
| H: no direct OOM; heap OOM or severe GC | heap OOM ("Java heap space"), direct +4 MiB | yes |
| Dg: growth …→288→432, OOM at 432→648 | growth …→324→486, OOM at 486→729 | shape yes, sizes no |

**Why the size predictions missed.** §2.1 step 6 assumed capacities 128 B × 2ᵏ (so exactly 64 MiB, then 128, 192, 288, 432, 648 …).
The first growth is `max(2c, c + count)` with count ≈ the whole 1 MiB value, giving 1,048,588 B (1 MiB + 12 B); doubling then
reaches 64 MiB + 768 B, which is **above** `DOUBLING_THRESHOLD` (`capacity > 64 MiB`, `DataOutputBuffer.java:166`), so ×1.5 starts
there: 96, 144, 216, 324, 486, 729, 1,093.5, 1,640.3, 2,047.99 MiB. Corrected bands: R ∈ (324, 486] peaks at 810, (486, 729] at
1,215, (729, 1,093.5] at 1,822.5, (1,093.5, 1,640.3] at 2,733.8, (1,640.3, 2,048) at 3,688. Every reading fits these bands
(T/N 1,215 > 1,024 − B_d; B 810; S1 1,822.5 < 2,048; S1-c 1,215 < 2,048; S2 2,733.8 < 3,072). T, A, B, I and N are unaffected;
S1 and S2 chose rows just below the true band edges, so the budget search above 1 GiB direct did not reach the endpoint.

### 3.4 Deviations from the design

- A1 (verify needs `-f`; §3.0). No other amendment.
- Stopping budget held: every endpoint came within 31 s of its compaction start (limit 300 s); no run started after 13:15 (last run 09:12);
  drop order not needed (every arm in §2.7 ran except optional S3). **S3 not run** (optional, first in the drop order; with the
  S1/S2 rows below the band edges its rows would also have needed the corrected sizes, which needs an amendment).
- The O5 dump does not show the holder (above); V5 rests on the stack, the 250 ms JDK pool readings and Dg1.
- H1's 1.23 GB heap dump was deleted by the queue after `hprof_direct.py` (no class histogram of it was taken); the heap OOM is
  evidenced by `launch.log` and `gc.log` ([`logs/H1-launch-oom.txt`](logs/H1-launch-oom.txt)).
- `nodetool compactionstats` (O6) ran every 2 s; the 250 ms sampler and the log lines were enough to time every phase.
- **Left on `ms0611`** (checked 09:20 EST: no Java process, no `u12-*` scope): `/mydata/s4/u12/` = 2.7 GB — two build copies
  (469 MB each), goldens G600/G6x100/G420 tars (≈ 1.7 GB; G1000/G1500 tars deleted after the runs, their build logs kept),
  `runs/` (42 MB of logs and samples) with one compressed dump (`runs/T1/dumps/*.hprof.gz`, 16 MB); all other dumps deleted.
  The node's instance data directory is empty.

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status: **`verified-OOM · deployment`** — unprotected accumulation (no control applies to the
in-use size of the SSTable row-body scratch buffer; the row it must hold has no enforced size limit).

**Reason.** At shipped defaults and the budget `cassandra-env.sh` resolves for a 4 GiB node (heap 2,048 MiB, direct 1,024 MiB),
compacting six 100 MiB fragments of one 600-entry map row (1 MiB values, every write inside `max_mutation_size`, the native
frame limit and the off-by-default guardrails) killed the node with `OutOfMemoryError: Direct buffer memory` on
`CompactionExecutor:1` in `DataOutputBuffer.expandToFit` ← `UnfilteredSerializer.serialize` ← `SortedTablePartitionWriter.addUnfiltered`
in **3/3** runs (T, 4.0–4.1 s after the compaction started), and in **3/3** natural-path runs with no operator action (N: 700
appends, four automatic 171 MiB flushes, the first STCS compaction). The JDK direct pool, read independently of any Cassandra
counter, held the 486 MiB scratch buffer plus 17 MiB of other direct memory when the next growth asked for 729 MiB (Byteman Dg1:
requested 764,420,652 B with 509,613,768 B live; 486 + 729 + 17 = 1,232 > 1,024); sampled peak 829.9 MiB = 324 + 486 + 17 during
the previous growth. The matched-payload control (same 600 MiB, same partition and six SSTables, rows of 100 MiB) peaked at
291.9 MiB and compacted in 3/3; the nearest surviving row (420 MiB) peaked at 829.7 MiB and compacted in 3/3. Streaming the row
body instead of copying it into the scratch buffer (I) removed the OOM in 3/3 with the same 602.717 MiB output, direct peak 52 MiB,
and an extended verify that passed. The heap was not the binding pool (0.9 GiB of 2 GiB at failure); moving the buffer on-heap
with the CASSANDRA-16471 knob turned the same compaction into a heap OOM (H1).

**V1–V7.**

| | Evidence | Runs |
|---|---|---|
| V1 Repetition | direct OOM 3/3 (T); 3/3 on the natural path (N); also Dg1 and both shakedowns | T1–T3, N1–N3 |
| V2 Matched control | matched payload 0/3 (A); nearest surviving row 0/3 (B), same build and budget | A1–A3, B1–B3 |
| V3 Measurement | U = JDK `BufferPool/direct` MemoryUsed at 250 ms (no Cassandra counter exists for P1, K = none); Byteman request sizes | all; Dg1 |
| V4 Intervention | patched build (no whole-row scratch copy) 0/3 at the same load and output size; patched format verified | I1–I3, I-v |
| V5 Initiating failure | first error `Direct buffer memory` on `CompactionExecutor:1`, stack through `expandToFit` ← `UnfilteredSerializer.serialize`; holder shown by the stack, the pool readings before death and Dg1 (the dump cannot show it: `close()` frees the buffer during unwinding) | T1–T3, Dg1 |
| V6 Default constraints | `DOB_MAX_RECYCLE_BYTES`, `dob.allocate_type`, doubling threshold, `max_mutation_size`, frame size, guardrails, `concurrent_compactors`, memtable and compaction settings all shipped defaults (yaml diff = directories, `num_tokens`) | all |
| V7 Acceptable budget | heap 2,048 MiB / direct 1,024 MiB = `cassandra-env.sh`'s values for a 4 GiB node; ≥ 512 MiB (standing rule), heap at the ideal 2 GiB | T, N |

**Budget search.** Largest direct limit that reached the endpoint here: **1,024 MiB** (n = 3/3 T, 3/3 N). 2,048 MiB (S1, 1,000 MiB
row) and 3,072 MiB (S2, 1,500 MiB row) did not (0/3, 0/3) — those rows sit just below the measured band edges (1,093.5 and
1,640.3 MiB). By the measured growth sequence, 2,048 MiB needs a row above 1,093.5 MiB and 3,072 MiB a row above 1,640.3 MiB
(peaks 2,733.8 and 3,688); one thread cannot exceed ≈ 3,688 MiB + B_d, and rows ≥ 2 GiB throw `BufferOverflowException`
(CASSANDRA-16764) instead. Those larger budgets are arithmetic, not readings.

**Interpretation.** Configuration-sizing / validation gap rather than an implementation slip: the scratch-buffer design copies one
whole row and nothing bounds a row; `max_mutation_size` and the collection guardrails are per write (and off), and
`DOB_MAX_RECYCLE_BYTES` is a retention cap checked at `close()` (CP-11 shape). The CQL docs advise keeping collections small
(`types.adoc:216-227`) but no setting enforces it, and every write here was accepted. The holder is the same one-item-materialized
shape as CP-12, at the SSTable writer rather than the read path. The 4 GiB node's process also reached a VmHWM of 3.4 GiB
(2 GiB pre-touched heap + direct + JVM), close to that node's RAM; the JVM direct limit is reached first.

**Limits.** One node, aarch64, single compaction thread; flush, streaming receive and index-build sites of the same buffer not
exercised; S3 (two threads) not run; the budget search above 1 GiB direct is arithmetic only. OC-85 (heap side) stays open: the
merged row on the heap was measured (≤ 1.3 GiB) but not claimed.
