# file_cache_size-chunk_cache_eviction-weighted_size--autonomous — stage-4 results  <!-- file: results/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md -->

> **Case:** [`file_cache_size-chunk_cache_eviction-weighted_size--autonomous`](../../stage3-ai-deep-read/cases/file_cache_size-chunk_cache_eviction-weighted_size--autonomous.md)
>
> **Status:** verdict filed (2026-11-12)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4): `8598c5712b4ce312e779fbfaa02c0ad1a9a1b48671f947a2697b0eda0d495ed1`. sha256 of the whole file after the audit amendments AM1–AM6 (section D, 2026-11-11): **`dbb3f006032762d2b3865c0c03a83fb2b95024c1adb556dfed883612c0c17342`**. sha256 of the frozen prediction and conclusion tables (text of B2f + B2g, from `**B2f.` up to `**B2h.`, then B3f + B3g, from `**B3f.` up to `**B3h.`, then the two wording amendments AM5 and AM6 of section D, concatenated; copy at `/mydata/jingsong-cass-s4/o06/freeze/pred-tables.txt`, frozen case file at `/mydata/jingsong-cass-s4/o06/freeze/case-frozen.md`): **`bf9be65d660ee7ee62b84d5eb9e967ef05df945b1d3c46be819dd14f410fb22b`**. Frozen 2026-11-12 03:03 UTC, before any reading. |
| **Harness** | `harness/file_cache_size-chunk_cache_eviction-weighted_size--autonomous/` (files listed in its README; not committed by this session) |
| **Tiers and values** | Unit (B2): `file_cache_size` F ∈ {32, 33, 64, 160} MiB, one fresh `ant testsome` JVM per F, 256 MiB uncompressed file read in 64 KiB chunks (sequential pass, then a seeded random pass). Cluster (B3): one node, heap 2 GiB, `MaxDirectMemorySize=4G`, F ∈ {32, 96, 288, 2080} MiB, 1.5M × 1 KiB rows LZ4 (AM2), 3M uniform point reads per F after a restart. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (AM1–AM6, case file section D) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of off-heap buffers retained by the chunk cache (weigher = `buffer.capacity()`, ChunkCache.java:154), plus the chunk-cache pool slabs. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | The given line is a constant (32), so the design varies `file_cache_size` and tests that the cap is F−32, not F (B2b, B3b): 4 values per tier, including the boundary 32. The default (`min(512, heap/4)`, cache disabled by default, `file_cache_enabled: false`) is not run; left for stage 3 (R-a). |
| A. Core question | real resource measured, not only the counter (gap named) | Met (cluster) / Partly (unit) | B3d: direct `MemoryUsed`, NMT "Other", RSS beside `size_bytes`. B2d: counter plus the pool's slab bytes; the process's direct memory is named as not observable there. |
| A. Core question | usage driven to the limit and past it | Met | B2c: 256 MiB read ≥ 2× the largest cap (128 MiB). B3c: ~1.5 GiB of chunks ≥ 6× the 256 MiB cap. |
| B. Logic | each step says what it establishes | Met | B2b/B3b give the reason for each F; B2h/B3h the controls. |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f exact byte caps; B3f caps and deltas with tolerances. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after AM5, AM6 | B2g/B3g cover capped at F−32, capped at F (reserve not applied), above cap (refuted), never reached, pool bypass / partial, positive control. AM5/AM6 give "≈", "a few chunks", "≫", "~1.5 GiB" numeric meaning. A reading matching no row is "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after AM4 | Ceiling follows F−32 across 3 values; disallow = eviction; AM4 adds misses and evictions (unit) and `Misses`/`Entries` (cluster) as direct evidence that entries were evicted at the cap. |
| B. Logic | alternative explanations and their controls | Met | Data exhausted (file ≥ 2× cap; F=2080 positive control), cache disabled (F=32 boundary), noise from other off-heap users (F=32 baseline subtraction), key cache off. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate line, A1–A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | B2c gives the test body; B3c–B3e the commands. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Stress compression wrong (AM2); paths and ports (AM3). Sampling every 5 s and a 60 s tail are exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, `build-test` (environment.md §1–3); the probe test and the sampler are step-1 work (harness). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit 256 MiB in `build/tmp` on /mydata (664 GB free); cluster ~1.6 GB data + commitlog; heap 2 GiB + direct ≤ 4 GiB = 6 GiB (budget 16 GiB). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after AM1 | Checked in `systems/cassandra/source` (5.0.9): ChunkCache.java:49-54, :149-157 (maximumWeight, ImmediateExecutor, weigher), :163-181, :304-328; BufferPools.java:37-38; BufferPool.java:128, :233-238, :274-292, :443, :904-923; FileHandle.java:405-447; DatabaseDescriptor.java:250, :576-577, :3784-3793; CachesTable.java:74-75; BufferPoolMetrics names (`Size`, `UsedSize`, `OverflowSize`, `Capacity`). All as cited except the slab size (8 MiB, not 1 MiB: AM1). Found while checking the commands: stress's default schema is uncompressed (AM2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| AM1 | Slab size is 8 MiB (`MACRO_CHUNK_SIZE`), not 1 MiB | applied 2026-11-11 (section D; case file untracked) | citation accuracy; no prediction change |
| AM2 | Add `compression=LZ4Compressor` to the stress `-schema` | applied 2026-11-11 | stress's own schema is uncompressed; B3c/B3f assume LZ4 16 KiB chunks |
| AM3 | Paths, copy method and ports of the shared node | applied 2026-11-11 | the filed `/local/ccprobe` and default ports are not available |
| AM4 | Eviction evidence (misses, evictions, entries); one JMX client for the sampler | applied 2026-11-11 | direct disallow evidence; `nodetool sjk` starts one JVM per gauge, too slow for 5 s |
| AM5 | Numeric meaning of B2g's words | applied 2026-11-11 | unambiguous matching |
| AM6 | Numeric meaning of B3g's words | applied 2026-11-11 | unambiguous matching |
| R-a | Run the default `file_cache_size` (`min(512, heap/4)`) as a fourth value | left for stage 3 | the design's three positive values already show the relation |
| R-b | The "reserve" is shared first-come headroom (A3 5d): a test of whether other pool users actually get it would need a second consumer | left for stage 3 | not needed for the claim tested (B1) |

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-12 UTC (unit 03:05–03:06; cluster 03:06–03:20) | not done |
| Node | local node0 (shared; 32 cores, 125 GiB); this run on 127.0.0.1 with storage 7400 / ssl 7401 / native 9442 / JMX 7599 (Byteman not used, port 9491 unused) | |
| OS and kernel | Ubuntu 22.04, `5.15.0-198-generic` | |
| JDK | openjdk 11.0.33 (2026-10-20) | |
| Ant | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/jingsong-cass-s4/o06/src`, `copy-source.sh` at repository HEAD `f74aade6` (tag `cassandra-5.0.9`), `ant build-test` BUILD SUCCESSFUL in 1 min 18 s | |
| Case-file / harness commit | both untracked at HEAD `f74aade6` (coordinator commits); case-file sha256 in section 1; harness md5 in `run1/unit-summary.txt` and `run1/cluster-session.txt` | |
| Storage for node data | `/mydata/jingsong-cass-s4/o06/node` on local `/dev/mapper/emulab-node0--bs` (removed after the run); data 1,609,649,953 bytes in 1 SSTable after compaction, LZ4 16 KiB, compression ratio 0.9938 | |
| Full logs | `/mydata/jingsong-cass-s4/o06/logs/` (`run1/unit/`, `run1/cluster/` with `cass-logs/system.log`, `gc.log`, `jmx-*.csv`, `cql-*.txt`, `nmt-*.csv`, `stress-*.log`; `shakedown/`; `build.log`) | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| — | audit | B3c | Stress's own schema is uncompressed (found while auditing, before any run) | AM2, applied before the freeze | 2026-11-11 | untracked |
| H1 | run 1, analysis (harness, not runbook) | B3d / AM6 window | The first version of `cluster-analyze.py` took "the last minute of the read run" as `[read_end − 60 s, read_end]`. Every read run lasted 49–65 s, so that window reached back before `read_start` into 1–2 samples taken with an empty cache, and averaged them in. Found when its F=288 delta (205.6 MiB) disagreed with the raw series (steady 336 MiB from 9 s into the read). | The window is clipped to the read run, `[max(read_start, read_end − 60 s), read_end]`, as AM6's words "of the read run" say; no prediction or conclusion row changed. Both outputs are kept (`run1/cluster-analysis-v1-unclipped.txt`, `run1/cluster-analysis.txt`). See 4.2 part 6 and the open point in section 8. | 2026-11-12 | n/a (harness) |

## 4. Run 1

**Scope:** unit tier F ∈ {32, 33, 64, 160} as filed (plus AM4 instruments); cluster tier F ∈ {32, 96, 288, 2080} as filed with AM2–AM4. **Command log:** `run1/unit-summary.txt`, `run1/cluster-session.txt`; raw readings `run1/unit-probe-lines.txt`, `run1/cluster-jmx-<F>.csv`, `run1/cluster-marks.txt`; analyzer `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (one fresh `ant testsome` JVM per F; 256 MiB file = 4096 chunks of 64 KiB, uncompressed, wrapped by `ChunkCache$CachingRebufferer`; 8192 reads per F)

| F | capacity | max weightedSize | max entries | pool Size (= max over run) | pool Used | overflow | misses / evictions | Evidence |
|---|---|---|---|---|---|---|---|---|
| 32 | instance null, `cacheSize=0` | — | — | — | — | — | — | `run1/unit-probe-lines.txt` |
| 33 | 1,048,576 | 1,048,576 | 16 | 33,554,432 (32 MiB, 4 slabs) | 1,048,576 | 0 | 26,584 / 26,568 | same |
| 64 | 33,554,432 | 33,554,432 (after pass 1 and pass 2) | 512 | 67,108,864 (= F) | 33,554,432 | 0 | 11,413 / 10,901 | same |
| 160 | 134,217,728 | 134,217,728 (reached in pass 1) | 2048 | 167,772,160 (= F) | 134,217,728 | 0 | 6,251 / 4,203 | same |
| ratio | maxW(160) / maxW(64) = 4.0000 | | | | | | | `run1/selfcheck.txt` |

All four junit runs: 1 test, 0 failures, 0 errors; no `ccprobe*` file left (`run1/unit-summary.txt`).

**Cluster tier** (1.5M partitions × 1 KiB, one LZ4 16 KiB SSTable; 3M uniform reads per F, 41–53 s each, 0 errors; JMX every 5 s; "read-run mean" = mean over `[max(read_start, read_end − 60 s), read_end]`; "tail" = the 60 s after the read, cache settled)

| F | Observable (B3d) | Reading | Evidence |
|---|---|---|---|
| 32 | `chunks` row; ChunkCache MBeans | no row in all 27 cqlsh samples; MBeans absent | `run1/cluster-analysis.txt`, `cql-32.txt` on node |
| 32 | chunk-cache pool Size / Overflow | 16 MiB / 0 | `run1/cluster-jmx-32.csv` |
| 32 | direct MemoryUsed (baseline B) | read-run mean 63.63 MiB; tail 63.92 MiB | same |
| 96 | capacity_bytes (JMX and cqlsh) | 67,108,864 | `run1/cluster-jmx-96.csv`, `run1/cluster-analysis.txt` |
| 96 | size_bytes | 67,108,864 from the first sample in the read (5 s) to the end; max 67,108,864 (JMX and cqlsh); 0 samples above cap + 32 × 16 KiB | same |
| 96 | entries; misses; evictions | 4096–4102; 3,187,637; 3,183,541 | same; `nodetool info`: "entries 4096, size 64 MiB, capacity 64 MiB, 3187679 misses" (`run1/cluster-nodetool-info-chunkcache.txt`) |
| 96 | pool Size / Used / Overflow | 96 MiB (= F) / 64.05 MiB / 0; system.log "Maximum memory usage reached (96.000MiB) for chunk-cache buffer pool" at 03:12:50 | `run1/cluster-jmx-96.csv`, `run1/cluster-systemlog-excerpt.txt` |
| 96 | direct delta vs B | read-run 79.98 MiB; tail 80.04 MiB; NMT Other delta 51.9 MiB; RSS delta 27.7 MiB | `run1/cluster-analysis.txt` |
| 288 | capacity_bytes | 268,435,456 | same |
| 288 | size_bytes | 268,435,456 from 9 s into the read to the end; max 268,435,456; 0 samples above cap + 32 chunks | `run1/cluster-jmx-288.csv` |
| 288 | entries; misses; evictions | 16,384–16,385; 2,933,159; 2,916,775 | same; `nodetool info` "entries 16384, size 256 MiB, capacity 256 MiB" |
| 288 | pool Size / Used / Overflow | 288 MiB (= F) / 256.06 MiB / 0; "Maximum memory usage reached (288.000MiB)" at 03:15:40 | same |
| 288 | direct delta vs B | read-run 253.36 MiB (unclipped window, H1: 205.63 MiB); tail 272.16 MiB; NMT Other delta 260.1 MiB; RSS delta 247.6 MiB | `run1/cluster-analysis.txt`, `run1/cluster-analysis-v1-unclipped.txt` |
| 96 → 288 | delta(288) − delta(96) | read-run 173.4 MiB; tail 192.1 MiB (B3f: ≈ 192 MiB) | `run1/cluster-analysis.txt` |
| 2080 | capacity_bytes | 2,147,483,648 | `run1/cluster-jmx-2080.csv` |
| 2080 | size_bytes | grows 0.39 MB → 1,358,970,880 (10 s) → 1,590,263,808 (30 s) and stays; below capacity | same |
| 2080 | entries; misses; evictions | 97,062; 97,038; ≈ 0 (−24: 24 entries were loaded before the first sample) | same; `nodetool info` "entries 97062, size 1.48 GiB, capacity 2 GiB, 97098 misses" |
| 2080 | pool Size / Used / Overflow | 1520 MiB / 1516.6 MiB / 0 | same |
| 2080 | direct delta vs B | read-run 1367.3 MiB (mean includes the 20 s fill); tail 1504.8 MiB | `run1/cluster-analysis.txt` |
| all | node health | 0 `ERROR` lines, no `OutOfMemoryError`; stress 3,000,000 reads, 0 errors per F; networking pool 8 MiB throughout | `run1/selfcheck.txt`, `run1/cluster-stress-results.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed: unit, maxW = cap for 33/64/160 with 4096 distinct chunks read (2× to 256× the cap) [observed: `run1/unit-probe-lines.txt`]; cluster, size_bytes = capacity within 5–9 s of each read at 96 and 288 while ~97k distinct chunks (1.48 GiB) were read [observed: `run1/cluster-jmx-96.csv`, `-288.csv`, `-2080.csv`]. Hold-fixed settings: same file and read order for every unit F (seeded) [observed: harness source; `PROBEFILE` lines]; cluster: same compacted single SSTable for every F, key cache 0, heap 2 GiB, `disk_access_mode: mmap_index_only`, restart per F, no pending compaction [observed: `run1/cluster-session.txt`]; LZ4 16 KiB checked [observed: `run1/cluster-session.txt`, DESCRIBE]. Positive control moved (F=2080 grew to 1.48 GiB) [observed].
2. **Readings** — (a) At every enabled F, in both tiers, the chunk-cache pool's slabs reached exactly F MiB while the cache held F − 32 MiB (pool Used = F − 32) [observed]; at 96 and 288 the pool logged "Maximum memory usage reached" [observed: `run1/cluster-systemlog-excerpt.txt`]; overflow stayed 0 [observed]. (b) Misses exceed reads at small caps: unit F=33, 13,219 misses in the 4096-read sequential pass; cluster F=96, 3.19M misses for 3M reads [observed] — a just-loaded chunk is evicted at insert and the reader reloads it (ChunkCache.java:240-242 `do ... while (buf == null)`) [inferred: code path; consistent with misses − entries = evictions]. (c) The cluster read runs lasted 41–53 s, shorter than the "last minute" AM6 names (H1).
3. **Matched row** — Unit, B2g row 1: "maxW plateaus at (F−32) MiB for 33/64/160; instance null at 32" — maxW = 1,048,576 / 33,554,432 / 134,217,728 = cap exactly, within B2f's ± 65,536 (AM5), instance null at 32 [observed]; with the positive-control row: maxW(160)/maxW(64) = 4.0000, within 3.8–4.2 (AM5) [observed]. Every B2f cell holds (capacity, maxW, entries ≤ 16/512/2048, pool Size ≤ F, overflow 0) [observed: `run1/selfcheck.txt`]. Cluster, B3g row 1: "size_bytes plateaus at F−32 MiB for 96/288 and direct delta ≈ F−32" — size_bytes = 67,108,864 and 268,435,456 [observed]; direct delta 79.98 MiB ∈ 64 ± 32 and 253.36 MiB ∈ 256 ± 32 [observed: `run1/cluster-analysis.txt`] (the steady tail values 80.04 and 272.16 MiB are inside the same bands); and B3g positive-control row: F=2080 plateau 1,590,263,808 B (1.48 GiB) ≥ 1 GiB and below capacity while F=288 stays at 256 MiB [observed]. Disallow evidence: millions of evictions at 96/288 against ≈ 0 at 2080 [observed: `run1/cluster-analysis.txt`].
4. **Excluded rows** — Unit: "plateaus at F MiB" — maxW(64) = 32 MiB, maxW(160) = 128 MiB, far below F − 65,536 [observed]; "maxW > cap + a few chunks" (refuted) — maxW never above cap [observed]; "well below the cap" — maxW = cap [observed]; "overflow > 0 or pool Size > F" — overflow 0, pool Size = F, not above [observed]. Cluster: "plateaus at F MiB" — 64 / 256 MiB, not 96 / 288 [observed]; "keeps growing past F−32" (refuted) — 0 samples above cap + 32 chunks, direct delta not above (F−32)+64 [observed]; "direct delta ≫ F" (partial) — 80 and 253 (tail 272) MiB, not above F + 32 = 128 / 320 MiB, OverflowSize 0 [observed]; "F=2080 also stays low" — 1.48 GiB [observed].
5. **Observed vs. inferred** — Inferred: (i) that the direct delta against F=32 is the chunk cache's own memory [inferred: the delta equals pool Size(F) − pool Size(32) = 80 and 272 MiB to within 0.2 MiB in the tail, networking pool flat at 8 MiB, overflow 0]; (ii) the reason misses exceed reads (2(b)) — not needed for the verdict; (iii) that clipping the AM6 window to the read run is what AM6 means (H1).
6. **Deviations and gaps** — (a) AM1–AM6 (section 1). (b) H1: with the unclipped first-version window the F=288 delta is 205.63 MiB, outside 256 ± 32, and the cluster tier would match no B3g row ("Not confirmed (no matching row)"); with the window AM6 describes ("of the read run") it is 253.36 MiB, and the steady tail value 272.16 MiB is also inside the band. The verdict below uses the clipped window; flagged for the user. (c) Unit tier sampling is between reads, so the transient weight inside one Caffeine write is not observed (named in B2d); the cluster sampler (5 s) cannot see sub-second overshoot either, and none of 23–25 samples per F exceeded the cap. (d) The node's working directory was the repository's stage3 folder (inherited from the launching shell); heap dumps and logs went to the log directory and nothing was written in the repository (checked). (e) Only Cassandra's own counters attribute memory to the cache; the process-level readings (direct `MemoryUsed`, NMT "Other", RSS) agree in size at F=288 and F=2080 and are noisier at F=96 (NMT 52, RSS 28 MiB against direct 80 MiB).
7. **Core question** — Usage followed the constraint and the constraint caps it: with the same data read, the chunk cache's retained bytes stopped at exactly `file_cache_size − 32 MiB` (1, 32, 128 MiB in the unit tier; 64 and 256 MiB on the node) and only grew to the dataset (1.48 GiB) when the cap was above it, with the excess evicted (parts 3, 4). The real direct memory tracked the knob as well (deltas 80 and 272 MiB steady, 192 MiB apart for a 192 MiB step in F), but it tracks F rather than F − 32: the chunk-cache pool holds slabs up to the full F (part 2(a)), so the 32 MiB "reserve" is free space inside slabs that are never released — a cap of F on the process, F − 32 on the cached data.

**Conclusion (one line):** Unit B2g row 1 + positive-control row, cluster B3g row 1 + positive-control row — claim confirmed (effect: caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parsed the junit XML, `probe-lines.txt`, `jmx-<F>.csv`, `cql-<F>.txt`, `marks.txt`, the stress logs and `system.log` with its own code (output `run1/selfcheck.txt`). It reproduced every number cited: unit caps, maxW, entries, pool, overflow, evictions and the 4.0000 ratio; cluster capacities, size max, last-window sizes, pool max, overflow 0, direct deltas 79.98 / 253.36 / 1367.29 MiB and tails 80.04 / 272.16 / 1504.84 MiB; stress 3,000,000 reads with 0 errors per F; 0 `ERROR` lines, 0 `OutOfMemoryError`, 2 pool-limit lines.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/cluster-session.txt`: LZ4 16 KiB, 1 SSTable, load 1,500,000 with 0 errors; `unit-summary.txt`: 4 × 0 failures. |
| 2. Readings | yes | Pool = F and overflow 0 in `cluster-jmx-96.csv` / `-288.csv` and `unit-probe-lines.txt`; the two "Maximum memory usage reached" lines in `cluster-systemlog-excerpt.txt`. |
| 3. Matched row | yes | Each part of B2g row 1, B3g row 1 and both positive-control rows reproduced by `selfcheck.txt`. |
| 4. Excluded rows | yes | Every refuted / partial row is excluded by a number `selfcheck.txt` reproduces. |
| 5. Observed vs. inferred | yes | (i) pool(F) − pool(32) = 80 / 272 MiB matches the tail deltas (80.04 / 272.16) in `cluster-jmx-*.csv`. |
| 6. Deviations and gaps | yes, with H1 recorded | The window choice is the one point where a different (unclipped) implementation changes the cluster row; both outputs are kept and the choice is flagged. |
| 7. Core question | yes | B1 → B2b–e / B3b–e → B2f/B3f → B2g/B3g in that order; disallow (eviction) evidence and the positive control both present. |

### 5.2 Run 2?

**No** (2026-11-12). The unit tier matches every predicted value exactly; the cluster cache operand is exact (capacity = size at every sample after fill), and the direct-memory band holds under both the clipped read-run window and the steady tail. The only dependence on an analysis choice (H1) is recorded for the user; a run 2 would not resolve it, since it concerns the wording of AM6, not the readings.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps) — both tiers Confirmed, effect caps.

**Claim tested:** (B1) With `file_cache_enabled: true` and `file_cache_size = F` MiB (F > 32), the chunk cache's retained bytes (`ChunkCache.weightedSize()` / `size_bytes`) plateau at, and never exceed by more than a few chunks, `(F − 32) MiB`, not `F` MiB, however much data is read; the node's direct memory attributable to the chunk cache follows `F − 32`.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 and positive-control row: **Confirmed** — maxW = F − 32 MiB exactly at 33/64/160 (1, 32, 128 MiB), instance null at 32, ratio 4.000, evictions at every F, overflow 0 | caps | run 1 + self-check | 2026-11-12 |
| Cluster | B3g row 1 and positive-control row: **Confirmed** — size_bytes = 64 / 256 MiB exactly at F = 96 / 288, never above; direct delta 80 / 253 MiB (steady 80 / 272) within (F−32) ± 32 MiB; F=2080 grows to 1.48 GiB; OverflowSize 0 | caps | run 1 + self-check | 2026-11-12 |

**Feedback filed:** the case file's section D (audit amendments AM1–AM6 and the stage-4 result, 2026-11-11/12; untracked, no commit). No section of the trace is refuted. **A3 step 5(d) is borne out and sharpened:** the 32 MiB "reserve" is not left to other users; the chunk-cache pool's slabs grew to the full `file_cache_size` in both tiers (pool Size = F, Used = F − 32, "Maximum memory usage reached" logged) and are never released, so the process's direct memory for the chunk cache is bounded by F, the cached data by F − 32.

**Open points for the user:** (1) H1 — the cluster direct-memory delta at F=288 depends on the averaging window: 253 MiB with the read-run window AM6 describes (used here), 272 MiB at steady state, but 206 MiB (outside the band, no matching row) with the first analyzer's window, which reached before the read start. (2) The pool's free space inside full slabs (the "reserve") is not observable as a separate quantity; only Size and Used are.

**Notable findings (not part of the claim):** (a) Chunk reload amplification at small caps: when Caffeine evicts a just-loaded chunk at insert, `CachingRebufferer.rebuffer` (ChunkCache.java:240-242) retries `cache.get(...).reference()` and reloads it from disk; at F=33 (16 entries) the sequential pass made 13,219 loads for 4,096 reads, and on the node at F=96 there were 3.19M misses for 3M reads (hit rate 4 %). A performance note, not a cap bypass. (b) `cassandra-stress`'s default schema is uncompressed (`WITH compression = {}`), a trap for any design that assumes default table compression (AM2).

**Leftovers on node0:** nothing running (no CassandraDaemon, stress, sampler or JUnit JVM of this run; checked by `ps` against `/mydata/jingsong-cass-s4/o06` and the recorded PIDs 893643, 900406, 911854, 921521, 929204). Node data `/mydata/jingsong-cass-s4/o06/node` removed. Kept: `/mydata/jingsong-cass-s4/o06/src` (working tree, 469 MB), `conf-run/`, `freeze/`, `logs/` (20 MB).
