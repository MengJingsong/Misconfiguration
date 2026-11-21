# R18 (retry of R10 / R5) — index_summary_capacity: parked full-sampling summaries plus the merge's output-summary overlap, at the approved 2,560 MiB container  <!-- file: cassandra/cases/index_summary_capacity--parked-load-and-merge-overlap-2560/index_summary_capacity--parked-load-and-merge-overlap-2560.md -->

| Field | Value |
|---|---|
| Case ID | `R18` (a new attempt at retry row `R10`, itself a retry of `R5`) |
| From | retry of `R10` ([phase-2 retry list](../../phase2-retry-list.md), row R10, status `picked again: R18 (2026-11-21)`) |
| Phase-1 case file | [`index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-adjustSamplingLevels-remainingSpace--autonomous.md) (E2 flag), [`index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-applySimpleConfig-indexSummaryCapacityInMiB--autonomous.md), [`index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/index_summary_capacity-distributeRemainingSpace-extraSpaceRequired--autonomous.md) (as R10) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`); build on pc99 `/mydata/s4/cassandra-base`, jar sha256 `570b5249…0176e` (same jar as R10 and C4; re-checked read-only 2026-11-21 01:54 EST) |
| Stage 1 (design) | OOM agent, phase-2 stage 1 session (Claude Opus 5.5), 2026-11-21 01:50–02:50 EST |
| Stage 2 (verify) | OOM agent, phase-2 stage 2 session (Claude Opus 5.5, fresh), 2026-11-21 02:01–05:48 EST runs on pc99; §3–§4 written by 05:50 EST |
| Verdict | **true positive** (A: `verified-OOM · deployment`, mixed; B: `verified-OOM · deployment`, unprotected accumulation) |
| Ready for stage 2 | **yes**: the only budget used is the owner-approved heap 1,280 / direct 640 / container 2,560 MiB (ruling 2026-11-20, §2.3) |

## Summary

- **Design (stage 1).** Two separately concluded conditions on pc99, both at the owner-approved budget **heap 1,280 /
  direct 640 / container 2,560 MiB**, all capacities at shipped defaults (BIG, `index_summary_capacity` auto = 64 MB,
  resize every 60 min, STCS, default backstop compaction):
  - **A (the R10 row's main change):** R10's four arms at L 2,560 — T = parked full-sampling P (≈ 316 MB of summaries vs a
    64 MB pool) + one default STCS merge of Q (4 × 4 M partitions); controls P alone and Q alone; intervention = the shipped
    redistribution of P before Q. At L 2,560 the Q import stays ≈ 170 MiB below the ceiling (R10's T died at the import),
    and Q alone keeps ≈ 215 MiB of margin (R10's K_Q died at its trim at L 2,048).
  - **B (the row's separate lead, moved to the approved budget):** one default STCS merge of a larger set Q7 (4 × 7 M
    partitions) alone; control = condition A's Q-alone arm (the same merge with 16 M instead of 28 M partitions, shared);
    intervention = `min_index_interval: 512` set on the table after the import and before the merge, which shrinks only the
    output summary builder and its copies (the claimed holder) 4×.
- **Budget arithmetic** uses R10's measured anon ceiling (L − memcg `file_mapped` 170.5 − ≈ 45 MiB in a compaction, i.e.
  ≈ 2,344 MiB at L 2,560; U1 was killed at anon-rss 2,346), recalibrated by Z before any reading.
- **Conclusion (stage 2): true positive, both conditions, at the owner-approved budget and all-default capacities.** A: T (parked P + one STCS merge of Q4) memcg OOM-killed **3/3** in the merge (anon-rss 2,335–2,346 MiB, `CompactionExecutor`); P alone, the merge alone and the merge after the shipped redistribution of P survived 3/3 each. B: one default STCS merge of Q7 (28 M partitions) alone killed **3/3** at 85 % (the output summary builder's growth past 180.7 MiB; anon-rss 2,330 MiB); the 16 M merge (K_Q) and the same merge with `min_index_interval` 512 survived 3/3. Both `verified-OOM · deployment`.
- **Root cause:** `index_summary_capacity` is enforced only by the periodic
  redistribution; summaries loaded or written in the window are malloc'd at full sampling with no byte check, and a
  merge holds its inputs' summaries, the growing output summary (one extra copy at each growth and at the trim), the
  output bloom filter and compression metadata at once, all outside the heap and direct limits.

## 1. Candidate

**Retry row R10, quoted** ([`phase2-retry-list.md`](../../phase2-retry-list.md)):

> | [R10](cases/index_summary_capacity--parked-load-plus-compaction-overlap/index_summary_capacity--parked-load-plus-compaction-overlap.md) (retry of R5) | 2026-11-20 | At the owner-approved container 2,048 / heap 1,024 / direct 512 on pc99, all defaults: parked full-sampling summaries P (316 MB vs a 51 MB pool) survive alone 3/3; T (P + Q) killed 3/3 but before any compaction (during the Q `nodetool import` or just after); the Q-alone control and the redistribute intervention were also killed 3/3 at the end-of-merge trim. Every kill shows memcg `file_mapped` 170.5 MiB (JVM's own mapped files, charged because caches are dropped), so headroom was ≈ 410–445 MiB, not C4's ≈ 595. At heap 1,280 / container 2,560, T died in the compaction (1/1, no controls); at 1,536 / 3,072 T survived. V2, V4 unmet | (1) Run T, K_P, K_Q and I ×3 at heap 1,280 / direct 640 / container 2,560 (container budget approved by the owner for V7, 2026-11-20); (2) calibrate the anon ceiling as L − memcg `file_mapped` − ≈ 15 MiB kernel, not just idle; (3) keep the Q load clear of the ceiling or deliver Q by flush/compaction output instead of `nodetool import`; (4) separate lead: Q alone (one default STCS merge of four full-sampling sstables, 16 M × 1,000-B keys) killed 3/3 at 2,048 — a single-term design (smaller-Q control, redistribute-before-merge intervention) | picked again: R18 (2026-11-21) |

**Earlier case and its verdict.** [R10](../index_summary_capacity--parked-load-plus-compaction-overlap/index_summary_capacity--parked-load-plus-compaction-overlap.md)
(2026-11-20, **retry**, protocol status `candidate`; V2 and V4 unmet). On pc99 at heap 1,024 / direct 512 / L 2,048
(owner-approved), defaults (pool 51 MB): K_P (P7 + P12 + P21 imported, 40 M partitions, summaries 316,251,012 B) survived
3/3 at +317–346 MiB; T was killed 3/3 **before any compaction** (T1, T3 during the Q import at anon-rss 1,859 MiB; T2 38 s
after it at 1,864); K_Q (Q1–Q4 alone) was killed 3/3 at the trim of its merge (98.4–99.6 %, anon-rss 1,830–1,834); I
(P redistributed to 19.8 MB first) was killed 3/3 at the last builder resize (85–86 %, anon-rss 1,830). Every kill record
shows memcg `file_mapped` 170.5 MiB and file-rss ≈ 175 MiB. Budget search: **U1** (T at heap 1,280 / direct 640 / L 2,560;
I0 1,699, after P 2,033) was killed **in the compaction** at 56.8 % (the 69.4 → 104.1 MiB builder resize, P blocks
resident, anon-rss 2,346.1, cg anon 2,349.1, `CompactionExecutor`); **U2** (1,536 / 3,072) survived, peak +743 = P 328 +
merge 415, compaction 292,473 ms. Helper H2 (no limit) measured the Q4 merge term at **+431 MiB** peak (the trim) and
D_q = 339 s. R5 (the row before) is the 2026-11-03 pre-protocol row-cache + summary-burst kill; R10 §1 explains why the
row cache (off by default) was replaced by the parked summary pool (the C4 shape).

**Phase-1 constraint and check** (unchanged from R10 §1). `index_summary_capacity` (`Config.java:539-540`; empty → 5 % of
heap, `DatabaseDescriptor.java:866-869`; 64 MB at `-Xmx1280m`, read back in U1), applied only by the periodic
redistribution (`IndexSummaryManager.java:117-147`, first run one interval after start, 60 min;
`IndexSummaryRedistribution.java:103-154`). Phase-1 stage 4: `adjustSamplingLevels` `Confirmed — caps only on some paths
(bypass)` (1,930 MiB of summaries stood under a 64 MiB cap until a run); `applySimpleConfig` `Not confirmed — caps
(counted size)` after each run.

**Source re-read for this design (2026-11-21).**
- The compaction writer's summary builder takes the table's **current** `min_index_interval` when the writer is created:
  `BigTableWriter.java:255` `new IndexSummaryBuilder(b.getKeyCount(), b.getTableMetadataRef().getLocal().params.minIndexInterval,
  BASE_SAMPLING_LEVEL)`; the builder sizes its entry buffer from `expectedKeys / minIndexInterval`
  (`IndexSummaryBuilder.java:100-128`) and samples every `minIndexInterval` keys (`:235`). An `ALTER TABLE … WITH
  min_index_interval = 512` issued before the merge starts therefore makes the merge write a summary with one entry per
  512 partitions (¼ of the default).
- `ColumnFamilyStore.reload()` (`ColumnFamilyStore.java:382-401`) touches compaction thresholds/params and indexes, not
  summaries; already-loaded summaries keep their level and interval until the next redistribution
  (`IndexSummaryRedistribution.java:193-203` is the only place that reacts to an interval change). So the ALTER leaves the
  input summaries, the bloom filter and the compression metadata of the merge unchanged; it changes only the output
  summary builder and its copies.
- `CassandraDaemon.java:435`: the background compaction submitter runs every 1 min, first 5 min after start (R10 measured
  the merge starting at t0 + 348.5–352.7 s in every Q arm).

**JIRA prior art** (re-checked read only 2026-11-21 ≈ 01:55 EST: REST search on issues.apache.org (reachable, HTTP 200)
and `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`; nothing posted):

| Query | Hits | Relevant |
|---|---|---|
| `text ~ "\"index summary\"" AND text ~ compaction AND (text ~ "oom-killer" OR text ~ "off-heap" OR text ~ "native memory")` | 61 | **CASSANDRA-8552** "Large compactions run out of off-heap RAM" (Cannot Reproduce); 8723 (RSS grows until OOM-kill, Cannot Reproduce); rest unrelated (compaction bugs) |
| `text ~ IndexSummaryBuilder AND (memory OR trim OR copy)` | 16 | **8757** (builder off-heap, share memory between early-open builds, Fixed); **14649** (summaries > 2 GB, builder uses more space than necessary; Fixed 4.0 — the writer-side `trim()` whose copy this design measures); 12014, 13785 (> 2 GB assertions) |
| `text ~ min_index_interval AND (memory OR OOM)` | 50 | **5519** (pool + periodic resampling: the design, Fixed 2.1); **6379** (min/max_index_interval introduced, Fixed); 8993 (effective interval bug, Fixed); none on the merge's transient output summary |
| keys 20565, 12699 | 2 | 20565 (kernel OOM-kill, anon-rss 29.6 GB, Not A Bug, no holder named); 12699 (page-table memory in large mmap'd compactions, Unresolved: a different holder, measured here as `pagetables`) |
| survey CSV (`summar`, `IndexSummaryBuilder`, `oom-killer`) | — | 2875 (Won't Fix), 8552, 8723, 10821 (OOM-killer during heavy compaction, Won't Fix), 10930 (cap off-heap, Unresolved), 13131, 13663, 15006, 15531, 20565 (as above) |

Verdict: **new** as an OOM path at defaults (no report of a merge's input + output summary + trim copy, alone or on a
parked uncapped load, as the cause of a memcg kill); periodic-only enforcement is **by design** (5519); large-compaction
native growth was reported without a holder (8552 Cannot Reproduce, 10821 Won't Fix). Not a known-fixed bug, so not a
positive control. Unchanged from R10.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

All capacities at shipped values; BIG format (`storage_compatibility_mode: CASSANDRA_4`); 1,000-byte partition keys as
in C4/R10. Each BIG sstable's summary holds one entry per 128 partitions (key + 8-byte position, 1,012 B per entry with
the 4-byte offset) in JNA `malloc` (`Memory.allocate` → `MemoryUtil.allocate` → `Native.malloc`): outside `-Xmx`, outside
`MaxDirectMemorySize`, invisible to NMT. Summaries are loaded (`nodetool import`) and written (compaction) at full
sampling; `index_summary_capacity` is applied only by the 60-min redistribution.

1. **Standing term P (C4 shape, condition A).** `nodetool import -q` of R10's P7, P12, P21 (40 M partitions): summaries
   301.6 MiB + compression metadata 19.2 MiB stay resident (R10: +315–335 MiB, K = 316,251,012 B vs a 64 MB pool at heap
   1,280) until the next periodic run (none in an arm). No STCS bucket forms among P (R10 §2.4; confirmed: P never
   compacted in R10).
2. **Merge term Q (E2 + replacement overlap).** `nodetool import -q` of four equal sstables forms one STCS bucket; the
   default backstop starts one background `COMPACTION` ≈ 80 s later. The writer builds the output summary in a
   `SafeMemoryWriter` that grows by allocate-copy-free (old and new blocks both resident for the copy; R10 saw each
   growth as a ≈ 1 s overlap in smaps) and is trimmed by one more copy at `prepareToCommit()`
   (`IndexSummaryBuilder.java:246-251`, `BigTableWriter.java:320`). Meanwhile the inputs' summaries stay live until the
   commit, and the output's bloom filter (zeroed → resident, ≈ 1.26 B/partition measured) and compression metadata
   (0.50 B/partition) are malloc'd with no control. Peak at the trim: inputs + output bloom + output compression metadata
   + written output summary + its trim copy. Measured for Q4 (16 M partitions): **+415** (victim U2, P parked) to **+431
   MiB** (helper H2), 1.047–1.087 × the model (396.4).
3. **Endpoint (A).** At L 2,560 the compaction-time anon ceiling is ≈ 2,344 MiB (§2.4), idle ≈ 1,699: P alone (+335) and
   Q4 alone (+431) fit; P + Q4 (+766) does not: memcg OOM-kill **during the merge**, while P is parked (U1, 1/1).
   The intervention (shipped redistribution of P to the pool first) removes ≈ 280 MiB of P and should let the merge finish.
4. **Endpoint (B).** Q7 = four sstables of 7 M partitions (28 M): the merge term scales with partitions, ≈ +726–754 MiB,
   which alone exceeds the ≈ 645 MiB of headroom: memcg OOM-kill at the last builder resize or at the trim. Q4 alone (16 M,
   the same merge 0.57× smaller) fits (shared control). Setting `min_index_interval` to 512 before the merge cuts the
   output builder and its copies from 2 × 211 to 2 × 52.8 MiB and should let the merge finish.

**Direction label (proposed; decided from readings in stage 2).** A: **mixed / combo** — a standing summary pool above
its cap in the documented periodic window (U > C, K > C: unprotected accumulation inside a periodic contract, as C4)
plus the merge's replacement overlap (no control covers the in-flight output summary, the output bloom filter or
compression metadata), converging in one process budget. B: **unprotected accumulation** — one merge's transient
summary/bloom/compression memory, with no control (the pool counts an output only once its reader is tracked, and
enforces only periodically); the input summaries are counted above C (K > C) throughout. Technique notes:
[`combo-playbook.md`](../../../combo-playbook.md) (standing + growing layer, each alone, remove one),
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (defaults, feasibility first).

**What changes from R10, and why (the row's items).**
1. Budget → heap 1,280 / direct 640 / L 2,560 for every arm (owner-approved).
2. Ceiling → calibrated as L − `file_mapped` − kernel overhead, measured per arm from `memory.stat` (§2.5 phase 2 rule).
3. Q load clear of the ceiling → at L 2,560 the T pre-merge peak is ≈ 2,034 + 130 + ≤ 40 transient ≈ 2,204 against an
   import-time ceiling ≈ 2,374 (margin ≈ 170; U1's import returned rc 0). Delivering Q by flushes instead was rejected:
   16 M × 1,000-byte partitions through CQL and memtable flushes on one rotational disk take hours and produce many small
   sstables, not one four-way merge.
4. Separate lead → condition B, moved to the approved budget (any other budget needs a new owner review). At L 2,560 the
   R10 Q4 merge fits, so B uses a larger merge (Q7) and Q4 becomes its smaller-Q control. The row's "redistribute before
   merge" intervention is **replaced**: at L 2,560 it would shrink only the inputs (Q7: 211 → ≤ 64 MB, ≈ −150 MiB),
   leaving a predicted peak of ≈ 2,275–2,303 vs a ceiling of ≈ 2,344 (margin 41–69 MiB, no clean separation), and it does
   not touch the claimed holder (the output builder). `min_index_interval: 512` (a table option, changed in the
   intervention arm only, V6) acts on the output builder alone (§1 source re-read).

### 2.2 Protection map (fixed before the run)

| Domain | Allocation and owner | Local contract (counter K, limit C) | Scope / multiplicity | Lifetime | Budget covering it |
|---|---|---|---|---|---|
| Index summaries, loaded (P; Q inputs) | `IndexSummary` offsets + entries (JNA malloc) from `Summary.db` at its saved level | K = `IndexSummaries.MemoryPoolSizeInMB` / tablestats "Index summary off heap memory used"; C = auto 5 % of heap = **64 MB** at 1,280 (read back), applied only by the periodic run (soft, periodic) | per sstable; no bound between runs; importer opens each sstable twice and frees the first copy asynchronously | until compaction commit / next downsample | container only |
| Index summary being written (merge output) | `IndexSummaryBuilder` entries + offsets (`SafeMemoryWriter`, malloc); each growth and the trim copy | none (counted only after an early-open reader is tracked) | one per running merge (`concurrent_compactors` auto = 2; one bucket → one task) | until commit; old block until the copy completes | container |
| Untrimmed builder tail (N19 analogue) | builder capacity beyond written bytes | none | per builder | until trim | address space only (unzeroed malloc; R10: `Rss` = written); measured, not a term |
| Bloom filters | `OffHeapBitSet` (malloc, zeroed); inputs 16 B; output sized for the merged key estimate | none; gauge `BloomFilterOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Compression metadata | chunk offsets (malloc) | none; gauge `CompressionMetadataOffHeapMemoryUsed` | per sstable | sstable lifetime | container |
| Heap | Java heap, `-XX:+AlwaysPreTouch` | `-Xmx` 1,280 MiB | process | resident from start | container + `-Xmx` |
| Direct buffers | networking pool (auto 320 MiB limit), reader buffers (chunk cache off) | `MaxDirectMemorySize` 640 MiB | process | standing | container + direct limit |
| JVM native baseline | metaspace, code cache, GC, stacks, arenas | none | process | standing (+≈ 20–30 MiB drift) | container |
| **JVM mapped files charged to the scope** (new row from R10) | jars, `libjvm.so`, other mapped binaries faulted in by the victim after the per-arm `drop_caches` | none; memcg `file_mapped` (R10: **170.5 MiB** in every kill record, both budgets) | process | standing, hot (not reclaimed before the kill) | container (reduces the anon ceiling) |
| Kernel memory of the scope | page tables (incl. mmap'd `Index.db` reads), kernel stacks, slab, sockets | none | cgroup | transient | container (R10: L − anon-rss − `file_mapped` = 17–19 MiB at import, 43–48 MiB in a merge) |
| Page cache (unmapped) | `Data.db`/`Index.db` reads and merge writes | reclaimable by the memcg | cgroup | reclaimable | `memory.current` `file` (not a term) |

### 2.3 Configuration and budget audit

- **Build:** pc99 `/mydata/s4/cassandra-base` (5.0.9, unmodified; jar sha256
  `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`, read-only check 2026-11-21 01:54 EST). No `ant`.
  Victim runs from a copy: `rsync -a --exclude data --exclude logs /mydata/s4/cassandra-base/ /mydata/s4/r18/node/`.
  No helper node copy is needed (no helper checks; R10's H1/H2 stand).
- **Node:** pc99 (`node4.jason92-326665`), x86_64, 32 cores, 125 GiB RAM, 8 GiB swap (0 for the victim), cgroup v2, kernel
  5.15.0-203-generic, OpenJDK 11.0.33; `/mydata` = LVM on one rotational disk (`sda`, ROTA 1), **657 GiB free**. At the
  2026-11-21 01:54 EST read-only check: load 0.00, no Java process, no user scope, 124 GiB free memory; `/mydata/s4/` holds
  only `cassandra-base` and `r10/data/pristine` (58 GB). Re-check before phase 0 and record.
- **yaml (victim):** shipped `conf/cassandra.yaml` with environment edits only (R10's set): `cluster_name: r18`,
  addresses/seeds 127.0.0.1, `storage_port: 27060`, `native_transport_port: 29060`, data/commitlog/saved_caches/hints
  directories under the arm folder. Every capacity setting shipped (as R10 §2.3: `index_summary_capacity` empty,
  `index_summary_resize_interval: 60m`, `compaction_throughput: 64MiB/s`, `concurrent_compactors` unset,
  `sstable_preemptive_open_interval: 50MiB`, `memtable_allocation_type: heap_buffers`, `file_cache_enabled` unset,
  `networking_cache_size` unset, `disk_access_mode` unset, `row_cache_size: 0MiB`, key/counter cache auto). Save the diff
  per arm; fail the arm if a non-environment line differs.
- **Table:** keyspace and table names stay **`r10.isx`** (the names the pristine and Q7 sstables were generated for):
  `CREATE KEYSPACE r10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE r10.isx (pk text
  PRIMARY KEY, v int);` all options default (STCS `min_threshold` 4, `bucket_low` 0.5, `bucket_high` 1.5,
  `min_sstable_size` 50 MiB, `min_index_interval` 128, `max_index_interval` 2048, `bloom_filter_fp_chance` 0.01, LZ4 16 KiB).
  **IB only:** `ALTER TABLE r10.isx WITH min_index_interval = 512;` at t0 + 300 s (§2.5).
- **JVM (victim):** `MAX_HEAP_SIZE=1280M`, `MAX_DIRECT_MEMORY_SIZE=640M` (`cassandra-env.sh` `calculate_heap_sizes` for RAM
  2,560 MiB: ½ and ¼), `HEAP_NEWSIZE` unset, G1 (shipped `jvm11-server.options`), `-XX:+AlwaysPreTouch` (shipped),
  `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary -XX:ParallelGCThreads=16 -XX:ConcGCThreads=16
  -Dcassandra.jmx.local.port=27299"`, `taskset` even CPUs 0–30 (R10's choices; samplers and generators on odd CPUs).
- **Resolved values to read back per arm:** heap 1,280, direct 640, "memory pool size of **64 MB** and a resize interval
  of 60 minutes", `compaction_throughput` 64 MiB/s, concurrent compactors 2, preemptive open 50 MiB, networking pool
  320 MiB, `disk_access_mode` `mmap_index_only`, `storage_compatibility_mode` CASSANDRA_4.
- **Budgets (V7).** Heap 1,280 MiB, direct 640 MiB (≥ 512 MiB: standing rule met; they do not cover the claimed holder,
  R10 §1), and **container `memory.max` 2,560 MiB, `memory.swap.max` 0** (`systemd-run --user --scope -p MemoryMax=2560M -p
  MemorySwapMax=0`): a 2.5 GiB node with `cassandra-env.sh`'s own heap/direct split. **Owner approval for V7:** "R10's
  next budget (heap 1,280 / direct 640 / container 2,560) is approved for V7" (owner ruling 2026-11-20, root `HANDOFF.md`
  wave 5) and, for this case, the coordinator's relay of the owner ruling of 2026-11-20 ("the container budget heap
  1,280 MiB / direct 640 MiB / container 2,560 MiB is approved for V7"; any other container budget needs a new review).
  Both conditions use only this budget. **No budget search upward in R18** (any other L needs a review): the largest
  budget reaching A's endpoint stays L 2,560, with R10's U2 (L 3,072, 0/1) as the boundary; for B the boundary is predicted
  (§2.7), not run.
- **Supporting choices** (owner-accepted for R10 on 2026-11-20 and reused unchanged): (a) 1,000-byte partition keys with
  a shared 988-byte prefix; (b) ≈ 61 GB of sstables (plus ≈ 31 GB for Q7) on a small node; (c) `nodetool import -q`;
  (d) sstables written offline by `CQLSSTableWriter` (`GenSorted`, `nb`, 16-byte `Filter.db`); (e) the four sstables of a
  merge set arrive in one import; (f) in A's intervention arm only, one JMX `IndexSummaryManager.redistributeSummaries()`
  between the imports. **New in R18:** (g) Q7 generated by the same `GenSorted` as (a)/(d), keys 56 M–84 M; (h) in B's
  intervention arm only, the table option `min_index_interval` = 512 (a capacity-related table option that differs from
  its default only in an intervention arm, which V6 allows); (i) the per-arm `drop_caches` is kept and stated: a
  cold-started container owns its mapped binaries (R10 row item 2). (g)–(i) do not change the budget; listed for the
  owner's information, not as a blocker.

### 2.4 Ceiling arithmetic

**Anon ceiling at L 2,560 (from R10's kill records).** L − kernel anon-rss at the kill − `file_mapped`: 17–19 MiB when the
kill comes in the importer / JIT (T1–T3 at 2,048), 43–48 MiB in a merge (KQ, I at 2,048; U1 at 2,560: 2,560 − 2,346.1 −
170.5 = 43.4). So at L 2,560 with `file_mapped` 170.5: **A_c ≈ 2,344 MiB** during a merge, **A_i ≈ 2,372 MiB** during an
import. Idle at heap 1,280: **I0 ≈ 1,699** (U1 1,699–1,700; R10 spread at heap 1,024 was ± 7 over 12 arms).

**Per-partition sizes** (1,000-byte keys, R10's files): summary 7.906 B (1,012 B per 128); compression metadata 0.503 B;
output bloom 1.263 B (H2: 20,205,160 B for 16 M); `Index.db` 1,008 B; `Data.db` 78.8 B. Merge-term factor measured/model
= **1.047–1.087** (U2 415, H2 431 vs model 396.4).

| Set | Keys `[lo, hi)` | Partitions | Summaries (MiB) | Compr. meta (MiB) | `Data.db` each (MB) | `Index.db` total (GB) | Source |
|---|---|---|---|---|---|---|---|
| P = P7 + P12 + P21 | 16 M–56 M | 40 M | 301.6 | 19.2 | 555 / 952 / 1,669 | 40.3 | R10 pristine |
| Q4 = Q1–Q4 | 0–16 M | 16 M | 120.6 | 7.7 | ≈ 315 | 16.1 | R10 pristine |
| Q7 = Q7a–Q7d | 56–63, 63–70, 70–77, 77–84 M | 28 M | 211.1 | 13.4 | ≈ 555 | 28.2 | new (phase 1) |

STCS: Q7 alone forms one bucket (four equal sizes, each ≥ 50 MiB). Q7 is never combined with P or Q4 in an arm. After
the Q4 merge in an A arm, the output (≈ 1.3 GB) can bucket with P12 and P21 (3 < `min_threshold`): no second merge (R10
U2: 4 sstables after).

**Merge term models (MiB), at the trim (peak):**

| Term | Q4 (16 M) | Q7 (28 M) | Q7 with `min_index_interval` 512 (IB) |
|---|---|---|---|
| Inputs' summaries + compression metadata | 128.3 | 224.5 | 224.5 |
| Output bloom + compression metadata | 19.3 + 7.7 = 27.0 | 33.7 + 13.4 = 47.1 | 47.1 |
| Output summary written + trim copy | 120.6 + 120.6 | 211.1 + 211.1 | 52.8 + 52.8 |
| **Model** | 396.4 | **693.8** | **377.2** |
| **× 1.047–1.087 (measured factor)** | **415–431** (measured) | **726–754** | **395–411** |

**Predicted peaks against the ceiling** (I0 1,699; A_c 2,344; A_i 2,372):

| Arm | Terms | Predicted peak RssAnon | vs ceiling | Margin |
|---|---|---|---|---|
| K_P (P alone) | 1,699 + 335 (R10: +315–346 incl. drift) | ≈ 2,045 | below A_c | ≈ 300 |
| T, pre-merge (Q import on P) | 1,699 + 335 + 130 + ≤ 40 import transient | ≈ 2,204 | below A_i | ≈ 170 |
| **T** (P + Q4 merge) | 1,699 + 335 + 415–431 | **2,449–2,465** | **above A_c** | **exceeds by 105–121** (kill once the merge term passes ≈ 310: U1 at 56.8 %) |
| K_Q (Q4 alone; also B's control) | 1,699 + 415–431 | ≈ 2,114–2,130 | below A_c | ≈ 214–230 (≥ 50 % of the term; ≥ 33 % of headroom) |
| I (P redistributed to ≤ 64 MB, then Q4) | 1,699 + 45–60 (R10: +34–47 at a 51 MB pool) + 415–431 | ≈ 2,159–2,190 | below A_c | ≈ 154–185 |
| **QB** (Q7 alone) | 1,699 + 726–754 | **2,425–2,453** | **above A_c** | **exceeds by 81–109** |
| IB (Q7, interval 512 before the merge) | 1,699 + 395–411 | ≈ 2,094–2,110 | below A_c | ≈ 234–250 |

**Feasibility at defaults.** If the pool were enforced continuously (summaries ≤ 64 MB): A peak ≈ 1,699 + 64 + 19.2 +
7.7 + 27.0 + 2 × 120.6 (the in-flight output, bounded only by the merge) ≈ 2,058 MiB < A_c: the endpoint needs the window.
B with inputs at the cap: 1,699 + 64 + 13.4 + 47.1 + 422.2 ≈ 2,246 < A_c (margin ≈ 100): B needs both the inputs above the
cap and the full-sampling output with its trim copy. **Error bounds:** I0 ± 30 MiB (R10 ± 7 at one heap, one U1 sample at
1,280); `file_mapped` ± 2 (constant in 12 records); kernel overhead in a merge 43–48; merge factor 1.047–1.087; P term ± 15;
drift +20–30 over an arm. Worst case for T (I0 1,669, factor 1.047): 2,419 > 2,344 by 75; for QB: 2,395 > 2,344 by 51;
worst high for I (I0 1,729 + 60 + 431 + 20 drift): 2,240 (margin 104); for K_Q: 2,180 (164); for IB: 2,160 (184).

**Measured mid-merge resize.** The builder's last growth copies the written bytes into a 1.5× block while the old block
is live (R10 KQ: +104 MiB spike at 104.1 → 156.1). For Q7 the growth past 156.1 MiB comes at ≈ 74 % of the merge
(written 156.1 of 211.1), predicted merge term there ≈ (224.5 + 33.7 + 10 + 2 × 156.1) × 1.05–1.13 = 610–656: QB may be
killed at that resize (≈ 2,309–2,355, near A_c) or at the trim (2,425–2,453). Both are the claimed holder.

### 2.5 Workload and environment

**Paths.** Everything new under `/mydata/s4/r18/` (`node/`, `gen/`, `data/pristine/Q7{a,b,c,d}/`, `stage_node/`,
`arms/<arm>/`, `logs/`). R10's pristine sets are used **read-only** from `/mydata/s4/r10/data/pristine/` (hardlinked into
`stage_node/`, same file system; never written, never deleted by R18). Harness under `harness/` of this folder, adapted
from R10's (`../index_summary_capacity--parked-load-plus-compaction-overlap/harness/`); install with copy + `mv`, never
edit a running script; launch with `( setsid nohup … < /dev/null > /dev/null 2>&1 & )`.

**Phase 0 — checks, harness, data verification (03:00–03:20; not readings).**
1. Freeze hash; node checks (`ps -eo cmd | grep '[C]assandraDaemon'`, `ss -ltn`, `/proc/loadavg`, `df -h /mydata`,
   `systemctl --user list-units --type=scope`); rsync the node copy.
2. Harness: R10's `arm.sh`, `batch.sh`, `sampler.sh`, `smaps.sh`, `cstats.sh`, `ISSampler.java`, `GenSorted.java`,
   `gen.sh`, `analyze.py` with these changes only: root `/mydata/s4/r18`, `cluster_name r18`, ports 27060/29060/27299,
   source sets from either pristine root, Q set selectable (`Q4` = Q1–Q4, `Q7` = Q7a–Q7d), new flag `ALTER` (IB: at t0 + 300
   s run `ALTER TABLE r10.isx WITH min_index_interval = 512;` and read it back from `system_schema.tables`), observation
   after the merge end **+30 s** (snaps at +10 and +30 s), no-Q arms observe to **t0 + 620 s**, `batch.sh` refuses to start an
   arm at or after **06:45 America/New_York**, per-arm hard limit 16 min (A) / 22 min (B). New sampler column set (1 s):
   `memory.stat` `anon`, `file`, `file_mapped`, `kernel_stack`, `pagetables`, `slab`, `sock`, and `memory.current`.
3. Verify R10's pristine sets against R10's generator record: the 56 file names and sizes equal
   [`logs/pristine-listing.txt`](../index_summary_capacity--parked-load-plus-compaction-overlap/logs/pristine-listing.txt)
   (checked at design time: 56/56 match, mode 0444, 61,353,352,470 B), and each `Data.db`'s CRC32 equals its
   `Digest.crc32` (7 files, ≈ 4.6 GB). A mismatch → regenerate that set with R10's `GenSorted` and keys before any arm.

**Phase 1 — Q7 dataset (03:06–03:15; not a reading).** `gen.sh` (R10's `GenSorted`, 988-char `Random(49)` prefix +
`%012d`, `CQLSSTableWriter.sorted()`, table `r10.isx`, generator `-Xmx8g`, odd CPUs) for Q7a [56 M, 63 M), Q7b [63 M, 70 M),
Q7c [70 M, 77 M), Q7d [77 M, 84 M) in parallel. Checks per sstable: one `-big-Data.db`; `Summary.db` = 55,344,256 B +
header (2,032 B in R10's 7 M set P7: expect 55,346,288 ± 0.1 %); `Filter.db` 16 B; `CompressionInfo.db` ≈ 3,523,967 B;
`Data.db` within ± 2 % of each other (one STCS bucket); estimated cardinality within ± 3 % of 7 M. `chmod a-w`. **Cutoff:**
not done by 03:25 → condition B is dropped (recorded; A proceeds).

**Phase 2 — calibration Z (≈ 4 min, may overlap the end of phase 1; not a mechanism reading).** Victim with no P, no Q at
heap 1,280 / L 2,560: I0_Z (median RssAnon of the last 30 s of 60 s idle) and `file_mapped_Z`, `pagetables_Z`,
`kernel_stack_Z` from `memory.stat`. Compute **A_c = 2,560 − file_mapped_Z − 45** and **A_i = 2,560 − file_mapped_Z − 18**.
**Pre-declared check** (all with the §2.4 terms): K_Q: I0_Z + 431 + 20 ≤ A_c − 100; I: I0_Z + 60 + 431 + 20 ≤ A_c − 100; T
pre-merge: I0_Z + 335 + 170 ≤ A_i − 100; T: I0_Z + 335 + 415 ≥ A_c + 50; QB: I0_Z + 726 ≥ A_c + 50; IB: I0_Z + 411 + 20 ≤
A_c − 100. With I0_Z = 1,699 and `file_mapped` 170.5 all hold (I0_Z window ≈ [1,669, 1,733]; the I inequality is the tightest, margin 34 at I0_Z = 1,699). If any fails, the budget
may not change (owner ruling) and no set is resized: record a dated note naming the failed inequality and its margin
before the first verdict arm, run the arms as designed, and read the outcomes with that note (a failed control-side
inequality makes a control kill a "margin" retry, not a design fault).

**Per-arm staging and cleaning** (R10's rule). `cp -al <pristine>/X stage_node/X`, then real copies
(`cp --remove-destination`) of `*-Summary.db` and `*-Statistics.db`. After the arm: `rm -rf stage_node/* arms/<arm>/{data,
commitlog,saved_caches,hints}` (compaction outputs, `tmp`/`tmplink` included). Before each arm: `sync; sudo -n sh -c 'echo 3
> /proc/sys/vm/drop_caches'`.

**Arm procedure** (`arm.sh <arm> 1280 2560 <P 0|1> <Q -|Q4|Q7> <redistribute 0|1> <alter 0|1>`), R10's timeline:
1. Pre-checks (ports 27060/29060/27299 free, no victim daemon); record load, free memory, disk.
2. Start in a fresh scope `systemd-run --user --scope --unit=r18-<arm>-<epoch> -p MemoryMax=2560M -p MemorySwapMax=0 --
   taskset -c 0,2,…,30 node/bin/cassandra -f`; t0 = launch epoch. Samplers at PID: `sampler.sh` (0.2 s), memcg stat (1 s),
   `smaps.sh` (1 s), `nodetool compactionstats` (5 s). CQL within 180 s or invalid. Read back §2.3 values.
3. Create keyspace and table; idle 60 s; I0 = median RssAnon of the last 30 s; idle snap (tablestats, ISSampler, NMT,
   `memory.stat`).
4. If P: at t0 + 150 s `nodetool -p 27299 import -q r10 isx stage_node/P7 stage_node/P12 stage_node/P21`; snap at +30 s.
5. If redistribute (I): at t0 + 210 s ISSampler `invoke` `redistributeSummaries`; record "Completed resizing" and the pool
   after (≤ 64 MB); snap at +20 s.
6. If Q: at t0 + 270 s `nodetool -p 27299 import -q r10 isx <the four Q dirs>`; record rc.
7. If alter (IB): at t0 + 300 s the `ALTER TABLE` above; record the read-back `min_index_interval` 512 and that no
   "Compacting" line precedes it (if the merge started first → invalid arm).
8. The default backstop starts the merge (no manual trigger); no "Compacting" by t0 + 480 s → invalid. Observe until
   "Compacted" + 30 s (or the JVM is gone); no-Q arms observe to t0 + 620 s. Snaps at +10 and +30 s.
9. Stop (`kill` SIGTERM by PID, ≤ 30 s, then `kill -9`); check the scope is gone; save `memory.events`, the kernel OOM
   block (`sudo -n dmesg`, naming `r18-<arm>`), log excerpts (`Loading new SSTables`, `Done loading`, `Initializing index
   summary manager`, `Compacting`, `Compacted`, `Redistributing`/`Completed resizing`, ERROR), GC log. Clean.

**Phase 3A — condition A verdict arms (readings), interleaved T, K_P, K_Q, I × 3** (T: P, Q4; K_P: P; K_Q: Q4; I: P,
redistribute, Q4).

**Phase 3B — condition B verdict arms (readings), interleaved QB, IB × 3** (QB: Q7; IB: Q7, alter). B's matched control is
A's K_Q (same build, budget, staging rule, timeline, instruments; a smaller merge of the same shape). If phase 3A has not
produced three valid K_Q arms, B has no control and is not concluded.

### 2.6 Instruments

- **Process / cgroup (0.2 s):** R10's `sampler.sh`: RssAnon, VmRSS, RssFile; `memory.current`, `memory.stat` `anon`/`file`,
  `memory.events` `max`/`oom`/`oom_kill`. U for the process = RssAnon / cgroup `anon` (JNA malloc is anonymous).
- **Ceiling terms (1 s, new):** `memory.stat` `file_mapped`, `kernel_stack`, `pagetables`, `slab`, `sock`; reported at idle,
  after each import, during the merge and in the last row before a kill (checks A_c per arm).
- **Per holder, independent of K:** `smaps.sh` (1 s): anonymous mappings ≥ 8 MiB with `Size` and `Rss` — P summary blocks
  (157.7 / 90.1 / 52.6 MiB), Q4 input blocks (≈ 30 MiB each), Q7 input blocks (≈ 52.8 MiB each), the output bloom block
  (19.3 MiB Q4, ≈ 33.7 MiB Q7), the builder's growth blocks (`Rss` = written) and the trim block (120.2 MiB Q4; ≈ 211 MiB
  Q7; ≈ 52.8 MiB IB); Σ `Summary.db` + `CompressionInfo.db` of the loaded sets; ΔU(T) − ΔU(I) vs P's excess over the pool;
  ΔU(QB) − ΔU(IB) vs 2 × (211.1 − 52.8) = 316.6 MiB model; `compactionstats` progress to place each peak in the merge.
- **Counters K:** `IndexSummaries` `MemoryPoolSizeInMB` / `MemoryPoolCapacityInMB` (ISSampler); tablestats "Index summary
  / Bloom filter / Compression metadata off heap memory used", "SSTable count" after each import and after the merge;
  the IB output `Summary.db` size (expect ≈ 55.3 MB vs ≈ 221.4 MB at 128).
- **JVM-internal:** NMT summary at idle and at +10 s; GC log (shipped `-Xlog:gc`); no heap OOM expected.
- **Initiating failure (V5):** kernel block "invoked oom-killer … CONSTRAINT_MEMCG … oom_memcg=…r18-<arm>… Killed process
  <pid> (java) … anon-rss … file-rss …" with the invoking thread (expected `CompactionExecutor`), `memory.events oom_kill`
  1, memcg stats in the block (`anon`, `file_mapped`), the last sampler/smaps rows (holder snapshot) and the last
  `compactionstats` progress. No heap dump (no heap holder claimed).

### 2.7 Predicted response and stopping budget

| Arm (1,280 / 640 / 2,560, pool 64 MB) | Predicted peak Δ (MiB) | Predicted peak RssAnon | Endpoint | K (summary pool) |
|---|---|---|---|---|
| Z | 0 (+≈ 25 startup) | I0 ≈ 1,699 ± 30 | none | 0 |
| K_P ×3 | +335 standing | ≈ 2,045 | none, 0/3 | 316.25 MB > C all arm |
| K_Q ×3 | +415–431 at the trim | ≈ 2,114–2,130 | none, 0/3; merge completes (1 output, `Summary.db` 126.5 MB) | 126.5 MB > C before and after |
| **T ×3** | +335 then +130 at the Q import (≤ 2,204), then rising in the merge | ≥ A_c ≈ 2,344 | **memcg OOM-kill 3/3 during the merge** (progress ≈ 40–75 %, at a builder growth copy), `CompactionExecutor`, P blocks resident in smaps; the Q import returns rc 0 | 442.75 MB > C at the kill |
| I ×3 | +45–60 after the redistribution, then +415–431 | ≈ 2,159–2,190 | none, 0/3; merge completes, same output `Summary.db` as K_Q | ≤ 64 MB after the redistribution |
| **QB ×3** | +224.5 after the import, then rising to +726–754 | ≥ A_c ≈ 2,344 | **memcg OOM-kill 3/3 in the merge**, at the last builder growth (≈ 74 %) or at the trim (≥ 97 %), `CompactionExecutor`; builder block `Rss` 156–211 MiB in smaps | 221.4 MB > C at the kill |
| IB ×3 | +224.5, then +395–411 | ≈ 2,094–2,110 | none, 0/3; merge completes in ≤ 1.2 × QB's duration; output `Summary.db` ≈ 55.3 MB | 221.4 MB before; ≈ 55 MB output after |

Also predicted: no "Redistributing index summaries" line in any arm except I's call; ΔU after each import = Σ
(`Summary.db` + `CompressionInfo.db`) ± 5 %; builder blocks with `Rss` = written (N19 tail not resident); `file_mapped`
≈ 170 MiB in every arm after start; merge durations ≈ 290–340 s (Q4) and ≈ 510–600 s (Q7); B's boundary (predicted, not
run) ≈ L 2,740–2,800 MiB (I0(L) ≈ 1,699 + 0.556 × (L − 2,560) from R10's three heaps; A_c(L) ≈ L − 216).

**What each outcome means (for §4), per condition.**
- **A:** T 3/3 killed after its merge started, K_P 0/3, K_Q 0/3, I 0/3, smaps holder blocks as §2.6 → V1–V5 with V6–V7
  (approved budget) → **true positive** for A (`verified-OOM · deployment`, mixed). A T kill before its merge starts does
  not count for the claim (as R10); if that leaves < 3 valid T kills, A is retry. A kill in K_Q or I → retry
  (the merge term or ceiling is not as modelled; check the Z note). T survives with the merge done → retry (margin model
  wrong), no escalation.
- **B:** QB 3/3 killed in the merge, K_Q 0/3 (from A), IB 0/3 with its merge completed → **true positive** for B
  (`verified-OOM · deployment`, unprotected accumulation). QB survives with its merge done → B is a **false positive
  candidate only if** its measured peak is below A_c and the ceiling arithmetic at L 2,560 cannot reach the endpoint for
  any default-sized merge named here; otherwise retry. IB killed → retry (the output summary is not the deciding holder).
- **Case verdict:** a per-condition status table; the case is **true positive** if either condition meets V1–V7 (as
  R15: "B true positive · A retry"), otherwise retry (or false positive only if both conditions meet the false-positive
  rule). Heap or direct OOM anywhere → record thread and stack; not this mechanism.

**Stopping budget.** Per arm ≤ 16 min (A) / ≤ 22 min (B); an invalid arm is repeated at most once and only if the repeat
can start by 06:45; no escalation after kills (no larger sets, no other budget, no raised capacities); **no arm starts after
06:45 EST**; every process stopped and §3–§4 written by **07:30 EST 2026-11-21**.

### 2.8 Controls and intervention

- **Matched controls (V2), ×3 each:** A — K_P (standing layer alone) and K_Q (merge layer alone), same build, budget,
  keys, staging, timeline; B — K_Q (the same merge shape with 16 M instead of 28 M partitions; component at low size,
  margin ≈ 214–230 MiB ≥ the 30 % starting target of the protocol).
- **Causal interventions (V4), ×3 each, unmodified build:** A — I: the shipped redistribution of P (what the periodic task
  does every 60 min) between the imports; it removes P's excess and leaves Q4 and the merge identical. B — IB:
  `min_index_interval` 512 set after the Q7 import and before the merge; it shrinks only the merge's output summary builder,
  its growth copies and its trim copy (≈ −340 MiB), leaving the inputs, bloom filter and compression metadata identical.
  Throughput check: the merge completes in I and IB (rc of the task, one output sstable, "Compacted … 4 sstables").
- **Repetitions:** every verdict arm from a clean start (fresh scope, fresh directories, fresh staging, dropped page cache).

### 2.9 Time plan (stage 2, S = 03:00 EST 2026-11-21; window ends 07:30)

Arm wall times from R10 (launch to scope gone + 35 s overhead): T ≈ 9.2 min (U1 killed at t0 + 516 s); K_P ≈ 11 min (to
t0 + 620 s); K_Q and I ≈ 12 min (merge end ≈ t0 + 640–690 s, + 30 s); QB ≈ 14.5 min (kill at ≈ t0 + 760–900 s); IB ≈ 16
min (merge end ≈ t0 + 860–950 s, + 30 s).

| Step | Duration | Ends at |
|---|---|---|
| Phase 0: freeze hash, node checks, node copy, harness, pristine verification | 20 min | 03:20 |
| Phase 1: Q7 generation and checks (in parallel with phase 0, 03:06–03:15; cutoff 03:25) | — | 03:15 |
| Phase 2: Z (after phase 1 finishes writing) | 4 min | 03:20 |
| Phase 3A: T1 KP1 KQ1 I1 T2 KP2 KQ2 I2 T3 KP3 KQ3 I3 (≈ 44 min per round) | ≈ 132 min | ≈ 05:32 |
| Phase 3B: QB1 IB1 QB2 IB2 QB3 IB3 (≈ 30.5 min per pair) | ≈ 92 min | ≈ 07:04 (last start ≈ 06:48) |
| Process check, cleanup, §3–§4 (written progressively from 04:00), write-backs left to the coordinator | — | ≤ 07:30 |

The plan is ≈ 3 min over the 06:45 start limit at the end of 3B, so the drop order applies from the start (pre-declared):
1. Shorten without changing any reading: no-Q arms observe to t0 + 560 s (past T's latest predicted kill); merge arms
   observe +10 s after "Compacted" (snap +10 only); stop by SIGTERM at once.
2. If phase 3A ends after 05:40, run B in the order QB1, IB1, QB2, IB2, QB3, IB3 and start nothing after 06:45. B with
   fewer than 3 QB and 3 IB arms is **not concluded** (its runs are recorded as a lead for a retry row).
3. Phase 3A is never shortened in favour of B. If 3A itself slips (invalid arms), finish complete triples in the order
   T, K_Q, I, K_P and record the missing runs; B is then dropped.
4. Q7 generation past 03:25 → B dropped at once (A only, ≈ 132 min, ends ≈ 05:35).

**Resources.** Victim ≤ 2.5 GiB (container); four generators ≤ 32 GiB (never during a measured arm; Z may overlap only
their file checks); disk: R10 pristine 58 GB (read-only) + Q7 ≈ 31 GB + ≤ 30 GB per B arm and ≤ 18 GB per A arm (merge
output, deleted after each arm) on 657 GiB free. **Left on pc99 at the end:** `/mydata/s4/r18/` (Q7 pristine ≈ 31 GB, run
logs), R10's pristine untouched; no process, no scope.

`sha256 of §1–§2 at freeze: d1c9712d6566d3324965c49c981334ef61764cdc069cd9af0852ee2fb4cea274` (bytes from the line `## 1. Candidate` up to, not including, this line) · amendments after the freeze: none.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session (Claude Opus 5.5), started 2026-11-21 02:01 EST (≈ 1 h before the design's planned
S = 03:00; every step ran as designed, only earlier, so the time plan's drop order never applied). Node clock: pc99's
local time (in `summary.txt` and the batch logs) is MST = EST − 2 h; epochs are UTC ms.

**Freeze check (02:01 EST).** sha256 of the bytes from `## 1. Candidate` up to the freeze line =
`d1c9712d6566d3324965c49c981334ef61764cdc069cd9af0852ee2fb4cea274`, equal to §2's line. No amendment was made.

**Environment (as run).** pc99 (`node4.jason92-326665`), x86_64, 32 cores, 125 GiB, 8 GiB swap (0 for the victim:
`memory.swap.max` 0 read back per arm), cgroup v2, kernel 5.15.0-203-generic, OpenJDK 11.0.33, `/mydata` on the
rotational `sda`. Node check at 02:01 EST: load 0.00, no `CassandraDaemon`, no Java process, no user scope, ports
27060/29060/27299 free, 124 GiB free memory, 657 GiB free on `/mydata`; `/mydata/s4/` held only `cassandra-base` and
`r10/data/pristine`. Build `/mydata/s4/cassandra-base` jar sha256 `570b5249…0176e` (re-read 02:02 EST), its
`conf/cassandra.yaml`, `cassandra-env.sh`, `jvm11-server.options` byte-identical (md5) to the pinned
`systems/cassandra/source/conf/` files; rsynced to `/mydata/s4/r18/node/` (same jar sha256; `conf/` identical to the base).
No `ant`. Harness: [`harness/`](harness/) (R10's scripts with the §2.5 changes only: `arm.sh`, `batch.sh` with a queue
file and the 06:45 EST no-start rule, `sampler.sh`/`smaps.sh`/`cstats.sh` unchanged, new `memstat.sh` (1 s `memory.stat`
ceiling terms), `table.py`, `smapspeak.py`, `export.sh`, `GenSorted.java`/`ISSampler.java` unchanged, `gen.sh`,
`genall.sh`, `checkdata.sh`, `verify_pristine.py`; arm queues `queue-*.txt`). yaml: shipped `conf/cassandra.yaml` + 11
environment lines (cluster `r18`, addresses, ports 27060/29060, directories under the arm; [`logs/Z/cassandra.yaml.diff`](logs/Z/cassandra.yaml.diff));
every arm's diff checked by `arm.sh`. Victim JVM (`jvm-args-excerpt.txt`): `-Xms1280M -Xmx1280M
-XX:MaxDirectMemorySize=640M` (**resolved MaxDirectMemorySize 640 MiB**, set by `MAX_DIRECT_MEMORY_SIZE` = L/4), G1,
`-XX:+AlwaysPreTouch`, NMT summary, 16 GC threads (the later `JVM_EXTRA_OPTS` flag wins over `cassandra-env.sh`'s 32),
JMX 27299, `taskset` even CPUs 0–30. Read back in every arm: "memory pool size of **64 MB** and a resize interval of
**60 minutes**", `index_summary_capacity=null`, `index_summary_resize_interval=60m`, `compaction_throughput=64MiB/s`,
concurrent compactors **2** (nodetool), `sstable_preemptive_open_interval=50MiB`, `disk_access_mode=mmap_index_only` (auto),
`file_cache_enabled=false`, `memtable_allocation_type=heap_buffers`, `row_cache_size=0MiB`,
`storage_compatibility_mode=CASSANDRA_4`, "Global buffer pool limit is 320.000MiB". Container `systemd-run --user --scope
-p MemoryMax=2560M -p MemorySwapMax=0`, `memory.max` 2684354560 read back. Full run data: `/mydata/s4/r18/` on pc99
(`arms/<arm>/` with `summary.txt`, `sampler.csv`, `memstat.csv`, `smaps.csv`, `cstats.txt`, `logs/`, `dmesg-block.txt`;
`logs/batch-{Z,3A,3B}.log`); excerpts in [`logs/`](logs/).

**Phase 0 — R10 pristine verification (02:03–02:05 EST)** ([`logs/phase0-1-node-records.txt`](logs/phase0-1-node-records.txt)):
the 56 files of `/mydata/s4/r10/data/pristine/` equal R10's generator listing in name and size (56/56, no extra file,
61,353,352,470 B, all mode 0444), and the CRC32 of each of the 7 `Data.db` equals its `Digest.crc32` (7/7 OK). Read only;
no set regenerated.

**Phase 1 — Q7 (02:03:09–02:06:50 EST, 215 s; cutoff 03:25 met).** `genall.sh`: Q7a–Q7d in parallel with R10's `GenSorted`
(unchanged), then the checks, `chmod a-w`:

| Set | Keys | `Data.db` (B) | `Summary.db` (B) vs ⌈N/128⌉×1,012 | `Filter.db` | `CompressionInfo.db` (B) | `Index.db` (B) | Est. cardinality (dev.) |
|---|---|---|---|---|---|---|---|
| Q7a | 56–63 M | 554,761,323 | 55,346,288 vs 55,344,256 (+2,032 header) | 16 B | 3,523,967 | 7,055,737,583 | 6,995,056 (−0.07 %) |
| Q7b | 63–70 M | 551,590,058 | 55,346,288 | 16 B | 3,523,967 | 7,055,737,583 | 7,017,696 (+0.25 %) |
| Q7c | 70–77 M | 551,561,004 | 55,346,288 | 16 B | 3,523,967 | 7,055,737,583 | 7,016,158 (+0.23 %) |
| Q7d | 77–84 M | 554,737,525 | 55,346,288 | 16 B | 3,523,967 | 7,055,737,583 | 7,082,673 (+1.18 %) |

All as predicted (`Summary.db` exactly P7's 55,346,288; `Data.db` within 0.58 % of each other; cardinality within ± 3 %).
Total 30,671,143,033 B in `/mydata/s4/r18/data/pristine/`.

**Phase 2 — calibration Z (02:06:57–02:09:39 EST)** ([`logs/Z/`](logs/Z/)): no P, no Q, heap 1,280 / L 2,560. Up in 49 s;
**I0_Z = 1,716 MiB** (median RssAnon of the last 30 s of 60 s idle; cgroup `anon` 1,720.5); idle `memory.stat` medians over
the same 30 s: **`file_mapped_Z` = 172.1 MiB** (172.1–174.2), `pagetables` 3.9, `kernel_stack` 1.7, `slab` 7.7, `sock` 0;
NMT committed 1,733 MB (heap 1,280). So **A_c = 2,560 − 172.1 − 45 = 2,342.9 MiB** and **A_i = 2,560 − 172.1 − 18 =
2,369.9 MiB**. Pre-declared check (recorded 02:10 EST, before T1's first reading), I0_Z = 1,716 (17 above the §2.4 value,
inside its window [1,669, 1,733]):

| Inequality | Left | Right | Holds | Margin |
|---|---|---|---|---|
| K_Q: I0_Z + 431 + 20 ≤ A_c − 100 | 2,167 | 2,242.9 | yes | 75.9 |
| I: I0_Z + 60 + 431 + 20 ≤ A_c − 100 | 2,227 | 2,242.9 | yes | 15.9 |
| T pre-merge: I0_Z + 335 + 170 ≤ A_i − 100 | 2,221 | 2,269.9 | yes | 48.9 |
| T: I0_Z + 335 + 415 ≥ A_c + 50 | 2,466 | 2,392.9 | yes | 73.1 |
| QB: I0_Z + 726 ≥ A_c + 50 | 2,442 | 2,392.9 | yes | 49.1 |
| IB: I0_Z + 411 + 20 ≤ A_c − 100 | 2,147 | 2,242.9 | yes | 95.9 |

All hold; no note was needed. The I inequality is the tightest (15.9 MiB), as the design said.

**Phase 3A — condition A (02:09:59–04:20:48 EST), interleaved T1 KP1 KQ1 I1 T2 KP2 KQ2 I2 T3 KP3 KQ3 I3, all valid**
(`batch-3A.log`; one row per arm from `table.py`, excerpts in `logs/<arm>/`). Every arm: CQL up in 49–53 s, pool read
back 64 MB, yaml diff environment-only, Q import (when present) at t0 + 270.1–270.7 s with rc 0, the default backstop
started the one four-way merge at t0 + 348.9–352.5 s (no manual trigger), no "Redistributing index summaries" line except
the I arms' own call, no ERROR line, no heap or direct OOM. RssAnon in MiB; Δ against the arm's own I0.

| Arm (start EST) | I0 | after P (Δ) | after redistribution | Q pre-merge peak | Merge | Peak RssAnon sampled (Δ) | Endpoint | Kill record: anon-rss / cg `anon` / `file_mapped` (MiB), thread | K summary (B) |
|---|---|---|---|---|---|---|---|---|---|
| T1 (02:09:59) | 1,696 | 2,028 (+332) | — | 2,162 | killed at **55.96 %** (cstats t0 + 505 s) | 2,279 (+583) | **memcg OOM-kill** t0 + 511 s | 2,346.4 / 2,349.8 / 170.3, `CompactionExecu` | 316,251,012 |
| KP1 (02:18:45) | 1,697 | 2,034 (+337) | — | — | none (no Q) | 2,038 (+341) | none (to t0 + 627 s) | — | 316,251,012 ×3 |
| KQ1 (02:29:23) | 1,701 | — | — | 1,825 | done, 315,142 ms | 2,118 (+417) at the trim | none | — | 0 → 126,500,000 |
| I1 (02:41:17) | 1,698 | 2,013 (+315) | 1,729 (+31) | 1,877 | done, 280,496 ms | 2,157 (+459) at the trim | none | — | 316,251,012 → 19,766,384 → 146,266,384 |
| T2 (02:52:37) | 1,701 | 2,026 (+325) | — | 2,156 | killed at **85.54 %** (t0 + 597 s) | 2,345 (+644) at t0 + 520.7 (the 69.4 → 104.1 growth) | **memcg OOM-kill** t0 + 601 s | 2,336.1 / 2,339.4 / 170.5, `CompactionExecu` | 316,251,012 |
| KP2 (03:02:51) | 1,703 | 2,037 (+334) | — | — | none | 2,041 (+338) | none | — | 316,251,012 ×3 |
| KQ2 (03:13:29) | 1,711 | — | — | 1,833 | done, 297,672 ms | 2,131 (+420) | none | — | 0 → 126,500,000 |
| I2 (03:25:03) | 1,695 | 2,034 (+339) | 1,744 (+49) | 1,879 | done, 292,562 ms | 2,168 (+473) | none | — | 316,251,012 → 19,766,384 → 146,266,384 |
| T3 (03:36:39) | 1,702 | 2,032 (+330) | — | 2,157 | killed at **84.55 %** (t0 + 598 s) | 2,340 (+638) at t0 + 522.1 (the 69.4 → 104.1 growth) | **memcg OOM-kill** t0 + 605 s | 2,334.7 / 2,337.5 / 170.4, `CompactionExecu` | 316,251,012 |
| KP3 (03:46:57) | 1,703 | 2,041 (+338) | — | — | none | 2,047 (+344) | none | — | 316,251,012 ×3 |
| KQ3 (03:57:36) | 1,698 | — | — | 1,833 | done, 304,132 ms | 2,137 (+439) | none | — | 0 → 126,500,000 |
| I3 (04:09:17) | 1,703 | 2,033 (+330) | 1,752 (+49) | 1,878 | done, 294,003 ms | 2,172 (+469) | none | — | 316,251,012 → 19,766,384 → 146,266,384 |

Readings for condition A:
- **T 3/3 killed in the merge** (none before it; every Q import returned rc 0 and the pre-merge peak stayed at
  2,156–2,162, ≈ 208–214 below A_i): kernel block "CompactionExecu invoked oom-killer … CONSTRAINT_MEMCG …
  oom_memcg=…/r18-T<n>-<epoch>.scope … Killed process (java) … anon-rss 2,390,720–2,402,732 kB", `memory.events`
  `oom_kill` 1 ([`logs/T1/dmesg-block.txt`](logs/T1/dmesg-block.txt), T2, T3). L − anon-rss − `file_mapped` at the kill =
  43.3 / 53.4 / 54.9 MiB (`pagetables` 8.1–9.6 of it). T1 died at the 69.4 → 104.1 MiB builder growth (56 %, as R10's U1),
  T2 and T3 survived that growth by 3–8 MiB (sampled peaks 2,345 and 2,340 at t0 + 521–522 s) and died at the next one
  (104.1 → 156.1, 84.6–85.5 %). Holder snapshot at the peak ([`logs/T3/smapspeak.txt`](logs/T3/smapspeak.txt)): P's summary
  blocks 157.7 / 90.1 / 52.6 MiB fully resident (`Rss` = `Size`), the builder's old 69.4 and new 104.1 (69.5 written)
  blocks both resident, the output bloom block, the Q inputs' blocks.
- **K_P 0/3** (+338–344 standing, P blocks 157.7 / 90.1 / 52.6 resident to the end, K 316,251,012 B > C = 64 MB the
  whole arm; no redistribution), **K_Q 0/3** (merge done in 297.7–315.1 s; peak 2,118–2,137 at the trim: builder 156.1
  (120.2 written) + trim copy 120.2 resident together ([`logs/KQ1/smapspeak.txt`](logs/KQ1/smapspeak.txt)); margin to
  A_c 206–225 MiB; output `Summary.db` 126,502,032 B), **I 0/3** (merge done in 280.5–294.0 s with the same output; peak
  2,157–2,172, margin 171–186).
- **Intervention attribution:** the shipped redistribution took P from 316,251,012 to 19,766,384 B (≤ C) in 200 ms and
  RssAnon fell by **284 / 290 / 281 MiB** (postP − postR), against P's excess over its new size of 282.8 MiB; with P
  downsampled the identical Q4 merge completed 3/3, with P parked it was killed 3/3.
- **Merge term** (sampled peak − I0): K_Q +417–439 (the model's 415–431, factor 1.05–1.11); the T kills came
  with P (+325–332) plus the partial merge term at 56–86 % progress.

**Phase 3B — condition B (04:20:53–05:47:09 EST), QB1 IB1 QB2 IB2 QB3 IB3, all valid** (`batch-3B.log`). Phase 3A
gave three valid K_Q arms, so B had its control. Every arm: up in 49–53 s, pool 64 MB, Q7 import at t0 + 270.5–270.6 s rc 0
(staged `Summary.db` 4 × 55,346,288 B), merge started by the backstop at t0 + 351.2–352.5 s, no redistribution, no ERROR.
IB: `ALTER TABLE r10.isx WITH min_index_interval = 512` at t0 + 300 s, rc 0, read back `min_index_interval 512 |
max_index_interval 2048` from `system_schema.tables`, **0** `Compacting` lines for `isx` before it (so the merge's writer
was created after the change in all three).

| Arm (start EST) | I0 | Q7 pre-merge peak (Δ) | RssAnon at 50 / 70 / 84 % of the merge | Merge | Peak RssAnon sampled (Δ) | Endpoint | Kill record: anon-rss / cg `anon` / `file_mapped` (MiB), thread | Output `Summary.db` / K after |
|---|---|---|---|---|---|---|---|---|
| QB1 (04:20:53) | 1,705 | 1,924 (+219) | 2,100 / 2,144 / 2,176 | killed at **85.44 %** (cstats t0 + 801 s) | 2,236 (+531) at t0 + 653.8 (the 120.5 → 180.7 growth) | **memcg OOM-kill** t0 + 804 s | 2,330.6 / 2,333.8 / 170.4, `CompactionExecu` | — |
| IB1 (04:34:31) | 1,708 | 1,940 (+232) | 2,021 / 2,035 / 2,045 | done, 517,608 ms | 2,120 (+412) at t0 + 868.9 (the trim) | none | — | 55,346,288 B / 55,344,256 |
| QB2 (04:49:50) | 1,708 | 1,930 (+222) | 2,107 / 2,150 / 2,179 | killed at **85.34 %** (t0 + 792 s) | 2,266 (+558) at t0 + 796.0 | **memcg OOM-kill** t0 + 796 s | 2,330.7 / 2,333.6 / 170.5, `CompactionExecu` | — |
| IB2 (05:03:16) | 1,708 | 1,940 (+232) | 2,026 / 2,040 / 2,049 | done, 513,092 ms | 2,093 (+385) | none | — | 55,346,288 B / 55,344,256 |
| QB3 (05:18:29) | 1,706 | 1,926 (+220) | 2,101 / 2,142 / 2,172 | killed at **85.57 %** (t0 + 796 s) | 2,236 (+530) at t0 + 650.9 (the 120.5 → 180.7 growth) | **memcg OOM-kill** t0 + 799 s | 2,330.4 / 2,333.6 / 170.5, `CompactionExecu` | — |
| IB3 (05:32:00) | 1,699 | 1,927 (+228) | 2,022 / 2,034 / 2,042 | done, 508,432 ms | 2,075 (+376) | none | — | 55,346,288 B / 55,344,256 |

Readings for condition B:
- **QB 3/3 killed in the merge**, all at 85.3–85.6 % progress: kernel block "CompactionExecu invoked oom-killer …
  CONSTRAINT_MEMCG … oom_memcg=…/r18-QB<n>-<epoch>.scope … Killed process (java) … anon-rss 2,386,348–2,386,640 kB,
  pgtables 13,156–13,204 kB", `oom_kill` 1 ([`logs/QB1/dmesg-block.txt`](logs/QB1/dmesg-block.txt), QB2, QB3); L − anon-rss −
  `file_mapped` = 58.8–59.1 MiB (`pagetables` ≈ 12.9 of it). **Where:** for Q7 the builder's blocks were 120.5 → 180.7 →
  271.1 MiB (not Q4's 104.1 → 156.1), and the kill came at the growth past 180.7 MiB: 180.6 of 211.1 MiB written = 85.6 %,
  matching the progress at the kill. Holder snapshot ([`logs/QB2/smapspeak.txt`](logs/QB2/smapspeak.txt), last sample before
  the kill, t0 + 796.0 s): the new builder block **271.1 MiB (39.6 written)** and the old **180.7 (180.7 resident)** at
  once, the four input summary blocks **4 × 52.6 MiB** resident, the output bloom block 33.5 MiB; QB1/QB3 show the full
  180.7 block (180.6 written) in their last sample. This is the design's "last builder growth" endpoint (§2.4 placed it at
  ≈ 74 % with Q4's block sizes; the holder is the same, the block sizes differ).
- **K_Q 0/3** (phase 3A; the same merge shape with 16 M partitions; margin to A_c 206–225 MiB).
- **IB 0/3**: merges completed in 508.4–517.6 s (within the predicted 510–600 s ± 1 %, "Compacted … 4 sstables … 28,000,000
  total partitions"), one output with `Summary.db` 55,346,288 B (¼ of the 221.4 MB the default interval writes); peak
  2,075–2,120 (+376–412; predicted +395–411), margin to A_c ≥ 223 MiB. Holder at the IB peak: builder 60.2 (52.6 written)
  and the trimmed 52.6-MiB copy instead of 180.7 + 271.1.
- **Intervention attribution at matched progress:** QB − IB = +79 / +109 / +130 MiB at 50 / 70 / 84 % (mean over the three
  pairs), against the model's written-builder difference (211.1 − 52.8) × progress = 79 / 111 / 133 MiB; the inputs, bloom
  filter and compression metadata are identical between the arms (pre-merge Δ +219–222 vs +228–232). The remaining step to
  the kill is the 271.1-MiB growth allocation that IB never makes.
- Q7 input summaries stood above the pool from the import to the kill (K 221.4 MB counted after the import vs C = 64 MB;
  no redistribution ran), as in K_Q (126.5 MB).

**Deviations from the design:** none in procedure, data, budget or instruments. Recorded differences from the
predictions: I0 per arm 1,695–1,711 (Z 1,716); T2 and T3 survived the 104.1-MiB growth (by 3–8 MiB) and died at the next
one; QB's endpoint at 85 % (block sizes 120.5/180.7/271.1) rather than ≈ 74 %; the sampled peaks (0.2 s) of killed arms
stay below the kernel's anon-rss because the last allocation spike falls between samples. `table.py`'s "+30" column did not
parse (a regex bug in the analysis script only; the +30 snaps are in each `summary.txt`). Harness scripts were not edited
while running.

**Left on pc99 (checked 05:48 EST):** no Java process, no `r18-*` scope (only `init.scope`), no harness process, ports
27060/29060/27299 free, load 0.90. `/mydata/s4/r18/` = 31.1 GB: `data/pristine/Q7{a,b,c,d}` **30.67 GB** (mode 0444, kept
for a later case), `arms/` 126 MB (per-arm logs and samplers; data, commitlog and staging deleted after each arm), `node/`
343 MB (the build copy), `gen/` + `logs/` < 1 MB. R10's `/mydata/s4/r10/data/pristine/` (61.35 GB) untouched: re-verified
at 05:48 EST (56/56 names and sizes, mode 0444, 7/7 CRC32 OK; [`logs/verify-pristine-end.txt`](logs/verify-pristine-end.txt)).

## 4. Conclusion (stage 2)

**Verdict: true positive** (both conditions).

| Condition | Endpoint n/N | Controls | Intervention | Protocol status | Verdict |
|---|---|---|---|---|---|
| A — parked P (316 MB vs a 64 MB pool) + one default STCS merge of Q4 | T: memcg OOM-kill **3/3**, all in the merge (56 / 86 / 85 %) | K_P 0/3 (+338–344), K_Q 0/3 (peak 2,118–2,137, merge done) | I (shipped redistribution of P first) 0/3, merge done 280–294 s | `verified-OOM · deployment` (mixed: periodic-only pool enforcement + the merge's uncontrolled replacement overlap) | **true positive** |
| B — one default STCS merge of Q7 (4 × 7 M partitions) alone | QB: memcg OOM-kill **3/3**, all in the merge (85.3–85.6 %) | K_Q 0/3 (shared with A) | IB (`min_index_interval` 512 before the merge) 0/3, merge done 508–518 s | `verified-OOM · deployment` (unprotected accumulation) | **true positive** |

**V1–V7 (each condition at heap 1,280 / direct 640 / container 2,560 MiB, unmodified 5.0.9, shipped capacities):**

| | A | B |
|---|---|---|
| V1 repetition | T1–T3, 3/3 killed during the merge | QB1–QB3, 3/3 killed during the merge |
| V2 matched control | K_P1–3 and K_Q1–3 survive (each layer alone; margins ≈ 296–305 and 206–225 MiB to A_c) | K_Q1–3 survive (the same merge with 16 M instead of 28 M partitions) |
| V3 U independent of K | `smaps` blocks: P summaries 157.7 / 90.1 / 52.6 MiB resident; builder old + new blocks; RssAnon ΔP = +325–339 vs K 316 MB; redistribution −281–290 MiB vs 282.8 predicted | `smaps` blocks: 4 × 52.6 input summaries, builder 180.7 + 271.1, bloom 33.5; QB − IB = 79 / 109 / 130 MiB at 50 / 70 / 84 % vs 79 / 111 / 133 modelled |
| V4 intervention | I1–I3: P downsampled to 19.8 MB by the shipped call, the identical merge completes 3/3 | IB1–IB3: the output builder ¼ size, the identical merge completes 3/3 (output `Summary.db` 55.3 MB) |
| V5 initiating failure | kernel memcg OOM records, invoking thread `CompactionExecutor`, `oom_kill` 1, smaps holder snapshot at the peak / last sample | the same; last sample shows the 271.1-MiB growth block beside the full 180.7 block |
| V6 default constraints | `index_summary_capacity` auto (64 MB read back), resize 60 min, STCS and compaction settings shipped, `min_index_interval` 128 | the same; `min_index_interval` differs only in the intervention arm |
| V7 acceptable budget | owner-approved 1,280 / 640 / 2,560 (ruling 2026-11-20); MaxDirectMemorySize resolved 640 MiB | the same |

**Reason.** At the owner-approved budget (heap 1,280 / direct 640 / container 2,560 MiB, I0 ≈ 1,700 MiB, `file_mapped`
≈ 172 MiB, so an anon ceiling A_c ≈ 2,343 MiB during a merge) and all-default capacities, **A**: P's full-sampling
summaries stayed parked at 316,251,012 B against a 64 MB pool (+325–339 MiB RssAnon) because the pool is enforced only by
the 60-min redistribution, and the default STCS merge of Q4 then added its inputs' summaries, the output bloom and
compression metadata and the output summary builder with its growth copies; T was killed 3/3 in the merge at kernel
anon-rss 2,334.7–2,346.4 MiB (thread `CompactionExecutor`), while P alone (2,038–2,047), the merge alone (2,118–2,137) and
the merge after the shipped redistribution of P (2,157–2,172, P −281–290 MiB) all survived 3/3. **B**: a single default
STCS merge of four 7 M-partition sstables (input summaries 4 × 55.3 MB, 221 MB vs the 64 MB pool, plus an output summary
builder that reached 180.7 MiB and needed a 271.1-MiB block for its next growth) was killed 3/3 at 85.3–85.6 % at
anon-rss 2,330.4–2,330.7 MiB; the same merge with 16 M partitions (K_Q) and the same Q7 merge with `min_index_interval`
512 (builder ¼; peak 2,075–2,120, merges done in 508–518 s) survived 3/3. No summary memory is bounded by `-Xmx` or
`MaxDirectMemorySize` (JNA `malloc`), the pool counts only tracked readers and acts only periodically, and nothing bounds
the merge's in-flight output summary and its copies.

**Classification (from the readings).** A: **mixed** — a standing domain above its pool between periodic runs (U ≈ 316 MB
> C = 64 MB, K = U: CP-11 periodic enforcement, as C4) plus the merge's transient native memory with no control, needed
together for the kill (each alone survives). B: **unprotected accumulation** — the merge's output summary builder, its
growth copy and the inputs' summaries in native memory outside every JVM limit (CP-9), the pool counting the inputs above
C (K > C) with no check in the merge window (CP-11). Interpretation: by design for the periodic pool (CASSANDRA-5519); a
sizing gap for the container (no control relates summary or merge memory to the process budget); no implementation
defect claimed. Clue patterns: CP-9 and CP-11 cover both shapes (no new pattern needed).

**Limits of attribution.** The budget is a 2.5 GiB container with `cassandra-env.sh`'s own split, approved by the owner;
no upward search was run (owner ruling: no other budget is approved). Boundary: A at L 3,072 survived in R10's U2 (0/1);
B's boundary is predicted at ≈ L 2,740–2,800, not run. The datasets use 1,000-byte partition keys (owner-accepted for R10)
— the merge term scales with key length × partitions / 128, so smaller keys need proportionally more partitions. Supporting
choices (a)–(i) of §2.3 are unchanged; the conditions label is `deployment` because none alters timing or capacity
outside the intervention arms. Heap and direct memory never failed; the kernel memcg kill is the only endpoint.
