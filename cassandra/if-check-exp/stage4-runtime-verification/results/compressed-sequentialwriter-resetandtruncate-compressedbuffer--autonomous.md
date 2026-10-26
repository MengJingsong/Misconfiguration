# compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous — stage-4 results

> **Case:** [`compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous`](../../stage3-ai-deep-read/cases/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous.md)
>
> **Status:** run 1 and self-check done 2026-10-26 (no run 2) — unit Confirmed (B2g, does not cap); cluster Confirmed (B3g, does not cap); verdict filed
>
> **Outcome class:** true negative — stage-3 estimate `negative` against the stage-4 effect `does not cap`
>
> **Agent:** autonomous. "§9a" below means B2f/B2g (unit) and B3f/B3g (cluster); "§9b–§9e" means B2a–B2e / B3a–B3e; the case file's feedback section is its section D.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file, untracked at audit time (the orchestrator commits it). sha256 of the whole file after the audit's amendments: `0ce1a2742f945a5b0ac9377dccdbb4c8b424d6f7163c1b8d53afe664625f9ad7` (2026-10-26, before any reading). The file's section D (feedback) was filled after the runs; sha256 of the file with that feedback: see §8. Frozen tables, sha256 of the exact text from `**B2f.` up to `**B2h.` (exclusive): `d17da307967c4c9e8b8a4b8f267db7cb03566175087a54d00be38815e6996347`; from `**B3f.` up to `**B3h.` (exclusive): `c849d6846f853623a4cd95bc56c77dc8c6d85359e435777d227ab3ef25081b55` (recompute: `sed -n '/^\*\*B2f\./,/^\*\*B2h\./p' <file> \| sed '$d' \| sha256sum`) |
| **Harness** | `harness/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous/` (uncommitted; orchestrator commits) |
| **Tiers and values** | Unit (B2): LZ4 x chunk {4096, 16384, 65536, 1048576} x {random, zeros}; Mock forcing arm (ratio 2.0, min_compress_ratio 2.0), Mock ratio-0.5 arm, early-return arm. Cluster (B3): LZ4 `chunk_length_in_kb` {4, 16, 256, 1024}, `concurrent_compactors` {1, 4} at chunk 1024, uncompressed control, scrub arms S1 (corrupted SSTable) and S2 (Byteman-shrunk buffer) |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: direct (off-heap) bytes of the writer's `compressed` and `buffer`; the "constraint" is `chunk_length_in_kb` (no limit at :247). |
| A. Core question | knob varied, >= 3 values incl. default | Met | B2b/B3b: four chunk values (16 KiB default included); writer count {1, 4}. |
| A. Core question | real resource measured, not only the counter | Partly | B2d/B3d: capacity of the allocated direct buffer (the resource) and BufferPool/NMT totals; the totals also contain read-side buffers that scale with chunk length. Gap named by amendment (direct R1/R2/R3 trace added). |
| A. Core question | usage driven to the limit and past it | Partly | No limit exists; "past it" = the forced grow (Mock arm unit, S2 cluster). The original Mock arm (ratio 0.5) could not do this (see rec. 1). |
| B. Logic | each step says what it establishes | Met | B2e/B3e. |
| B. Logic | prediction in numbers or clear relation | Partly | B2f ratios and overheads were wrong ("64x to 256 KiB-class", "+ about 20 bytes"); B3f "roughly 2 x chunk" confounded. Corrected before any reading (recs. 2, 4). |
| B. Logic | every plausible outcome has a row | Partly | Rows were missing for R2 firing in normal runs and for S1 not reaching :247. Added (rec. 5). |
| B. Logic | confirmation needs ceiling-follows-knob and disallow evidence | Met | Negative claim: the "disallow" is the branch itself; evidence = R2/R3 and the Mock/S2 forced grow. |
| B. Logic | alternatives and controls | Met | B2h/B3h plus the amended negative controls. Positive control for the instrument: the Mock forcing arm / S2 (a grow happens and is seen); chunk sweep shows the buffer moves with the knob. |
| C. Specific | human can follow | Met | A3 is clear. |
| C. Specific | AI can run without re-deriving | Partly | B2c was inconsistent (8 chunks, mark after 2); fixed. Ports, yaml, Byteman rules supplied by the harness. |
| C. Specific | exact values/commands | Partly | Cluster volume 2M rows x 4 tables too large for the aim; reduced to 200,000 rows x 1 KiB per chunk value (rec. 6). |
| D. Runnable | harness/prereqs exist | Met | JDK 11, Ant, Byteman 4.0.20 on pc12; `ant build-test` of `~/s4-cs` done (1m16s). |
| D. Runnable | workload arithmetic reaches the limit | Met | writer scratch is independent of volume; 200 MB/table, node has 45 GB free. |
| D. Runnable | citations spot-checked | Met after corrections | Verified in 5.0.9: CSW :98, :149, :160-176, :224, :233-237, :241, :246, :247, :249-250, :255-258, :265-268, :275-283, :305; CompressionMetadata chunkOffsetBy :466-469; SSTableRewriter :140-152; SortedTableWriter :297-302; SortedTableScrubber :300; Big :167,188; Bti :187,210; CompressionParams :48-49, :55, :187-190, :345-360, :444-458; LZ4 :113-115/:240-243, Snappy :77-80, Zstd :105-108/:208-211, Deflate :88-92, Noop :45-48; DataComponent :68-98; Config :399; BufferType allocateDirect. Wrong: MockCompressor :57-60 ratio claim (rec. 1); B2c arithmetic; B2f ratios. Also: Deflate and Noop prefer ON_HEAP (A2 names only LZ4/Zstd as off-heap, true). A5's docs URL not opened (stated by the writer; not needed). `syncInternal` always calls `doFlush` (SequentialWriter.java:213-217), so `chunkOffsetBy(nextChunkIndex)` always exists at :246. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | MockCompressor at ratio 0.5 does not exceed its bound (compress writes exactly `ceil(n/ratio + extra)` = capacity); the forcing arm is ratio 2.0 with `min_compress_ratio` 2.0 (raw chunk path stores chunk > chunk/2). Keep ratio 0.5 as a no-fire control. | Applied 2026-10-26 (A3 step 5, B2b, B2f, B2g, B2h) | Source: `MockCompressor.java:57-60,71-79`; `CompressedSequentialWriter.java:160-165`. |
| 2 | Correct B2f numbers: capacities 4132 / 16468 / 65813 / 1052708 | Applied 2026-10-26 (B2f) | lz4-java bound `n + n/255 + 16` plus 4. |
| 3 | Fix B2c workload sequence (2 chunks, mark, 4 chunks) and add file-length proof of passing :233 | Applied 2026-10-26 (B2c) | Internal inconsistency. |
| 4 | Add direct Byteman writer-capacity trace R1/R2/R3 and exact B3f relation | Applied 2026-10-26 (B3d, B3f) | Pool totals include reader buffers. |
| 5 | Add rows to B3g (R2 fires in normal run; S1 does not reach :247) | Applied 2026-10-26 (B3g) | Missing outcomes. |
| 6 | Specify scrub arms S1/S2 and reduce data volume | Applied 2026-10-26 (B3c) | Reachability; user instruction to mark n/a if corruption is not reliable. |
| 7 | Real compressors never fire the branch (stored <= max(bound, chunk) <= bound) | Left as a note in A3 step 5 (amended text) | Explains why the branch is unreachable. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (UTC) |
| Node | pc12 (`node1.jason92-320876`, 198.22.255.22), 40 cores, 251 GiB |
| OS and kernel | Ubuntu 22.04, 5.15.0-187-generic |
| JDK / Ant | OpenJDK 11.0.32.1 / Ant 1.10.12 |
| Local source copy | `~/s4-cs` from `cassandra/cassandra-5.0.9/` at repository commit `1ae567d` (copy-source.sh) |
| Case-file commit / harness commit | uncommitted (orchestrator); case-file sha256 `0ce1a274...9ad7` unchanged since the freeze |
| Storage for node data | local `/` (`~/s4-cs/data`, ext, 45 GB free) |
| Full logs | `pc12:~/s4-cs-logs/` (`run1/<arm>/` for the cluster arms, `unit-run.log`, `unit-readings.txt`, `run1-*.out`); excerpts in `results/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous/run1/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit | B2d (harness) | First run of `ChunkBufferGrowthTest` failed with `NoSuchFieldException: buffer` after the first INFO line (reflection looked for `buffer` on `SequentialWriter`; it is declared higher up). No reading was taken. | Instrument fix: `field()` walks the superclasses. The prediction and case file were not touched. | 2026-10-26 | none (harness only) |
| 2 | unit | B2e | `ant testsome -Dtest.name=ChunkBufferGrowthTest` runs a second pseudo-suite `ChunkBufferGrowthTest` (no package) that ends `ClassNotFoundException` and makes ant exit 1, although the real suite `org.apache.cassandra.io.compress.ChunkBufferGrowthTest` has `Tests run: 1, Failures: 0, Errors: 0` (`run1/unit-junit-and-selfcheck.txt`). | None needed; the readings come from `unit-readings.txt` and the real suite's line. | 2026-10-26 | none |

The audit's case-file amendments (before any reading) are listed in §1.1.

## 4. Run 1

**Scope:** unit tier (all cells); cluster tier: chunk sweep C4 C16 C256 C1024 (1 compactor), W4 (4 tables, chunk 1024, 4 compactors), U (uncompressed), S1 (real scrub of a corrupted SSTable) at three offsets (0.55, 0.40, 0.70 of the Data.db), S2 (scrub with the grow forced by Byteman). Scrub corruption was reliable (3 of 3 offsets reached line 247), so no sub-step is n/a and nothing is a deviation. **Command log:** `results/compressed-sequentialwriter-resetandtruncate-compressedbuffer--autonomous/run1/` (`cluster-summaries.txt` carries each arm's `session` summary, `traces-excerpt.txt` the Byteman lines, `unit-readings.txt`).

### 4.1 Readings

**Unit tier** (`run1/unit-readings.txt`; 17 READING lines; `SUMMARY failures=0`)

| Test or assertion | Result | Evidence |
|---|---|---|
| LZ4, chunk 4096 / 16384 / 65536 / 1048576, random and zeros (8 cells): `compressed` capacity before and after `resetAndTruncate` | 4132 / 16468 / 65813 / 1052708 before and after, same object, direct, base buffer = chunk; file shrank to the mark chunk offset (path went past :233) | unit-readings.txt `cell=lz4` |
| Capacity ratios | 16 KiB/4 KiB = 3.985, 64 KiB/4 KiB = 15.93, 1 MiB/4 KiB = 254.8; capacity/chunk = 1.0088, 1.0051, 1.0042, 1.0039 | recomputed in `selfcheck.py` |
| Early-return control (mark inside the current chunk, :233 true) | file length 16388 before and after, same object | `cell=lz4-early` |
| Mock forcing arm (ratio 2.0, min_compress_ratio 2.0), 4 chunks | before = chunk/2 (2048 / 8192 / 32768 / 524288), after = chunk exactly (4096 / 16384 / 65536 / 1048576), new object, file shrank | `cell=mock-force` |
| Mock ratio 0.5 arm (the write-up's original arm) | before = after = 2 x chunk (8192 ... 2097152), same object: does not fire | `cell=mock-ratio0.5` |

**Cluster tier** (Byteman R1 constructor trace = the writer scratch; pool = secondary)

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| chunk 4 KiB | C4 | ks writers: buffer / compressed / direct | 5 writers (4 flush + 1 compaction): 4096 / 4132 / true; R2 never printed | cluster-summaries.txt, traces-excerpt.txt |
| chunk 16 KiB | C16 | same | 5 writers: 16384 / 16468 / true; no R2 | same |
| chunk 256 KiB | C256 | same | 5 writers: 262144 / 263192 / true; no R2 | same |
| chunk 1024 KiB | C1024 | same | 5 writers: 1048576 / 1052708 / true; no R2 | same |
| chunk 1024 KiB, 4 tables, 4 compactors | W4 | writers; alive together | 20 writers (16 flush + 4 compaction), all 1048576 / 1052708; the 4 compaction writers overlap (last init 1792980523443 < first cleanup 1792980527489) | selfcheck output, traces-excerpt.txt |
| uncompressed | U | ks writers | 0 `CompressedSequentialWriter` for ks (system-table writers are in the trace, so the rule was live) | traces-excerpt.txt |
| chunk 4/16/256/1024 KiB, W4 | C*, W4 | direct pool peak minus baseline (secondary, includes reader buffers) | 1,121,970 / 1,153,152 / 1,888,938 / 7,401,094 B; W4 29,605,041 B; U 61,044 B | cluster-summaries.txt |
| same | C*, W4, U | NMT "Other" committed, peak minus baseline | +1,095 / +1,126 / +308 / +1,084 KB; W4 +28,927 KB; U +60 KB | cluster-summaries.txt |
| same | C*, W4, U | heap used, max during compaction | 662.5 / 658.1 / 629.0 / 629.6 MB; W4 1086.6 MB; U 649.4 MB | cluster-summaries.txt |
| S1 offset 0.55 / 0.40 / 0.70 (real scrub, chunk 16 KiB) | S1-55, S1-40, S1-70 | R2 `compressedCap`, `chunkSize`; R3 identity | 3 of 3: scrubber failure path reached (`resetAndTruncate` called once each, "Error reading partition" in system.log); R2 cap 16468, chunkSize 16454, R3 cap 16468 with the same identity: no grow | traces-excerpt.txt |
| S2 offset 0.55 (grow forced to 64 bytes at line 247) | S2-55 | R2f, R3 | forced cap 64; R3 cap 16454 = chunkSize exactly, new identity (1115998594 vs 1068134451) | traces-excerpt.txt |

### 4.2 Conclusion and logic

1. **Validity** — The runs are valid. Chunk sweep: the schema read-back shows the intended `chunk_length_in_kb` and LZ4 for each arm [observed: cluster-summaries.txt "schema read-back"]; 4 SSTables per table before the compaction [observed: "sstables before compaction" and EXPECTED line]; the compaction ran (`nodetool` rc 0, 1 SSTable per table after) [observed]. "Limit reached": there is no limit at :247; the branch was reached in S1 (R2 printed 3 of 3, after `resetAndTruncate` went past :233, shown by the chunk offsets differing: `curChunkOffset` 526624 vs the mark's) [observed: traces-excerpt.txt]. Unit: the early-return control kept the file length, the normal cells shrank it to the mark's chunk offset, so :247 was evaluated in the 16 normal cells [observed: unit-readings.txt]. `concurrent_compactors` 1 and 4 were set in the yaml [observed: cluster-summaries.txt "yaml:" lines].
2. **Readings** — Pool totals exceed the writer scratch: C1024 +7.4 MB against 2 x 1 MiB + 4 KiB for one writer, and the 4 KiB arm +1.1 MB against about 8 KiB, while the uncompressed arm is +0.06 MB. The 1.1 MB floor is present in every compressed arm (read-side buffers of the compaction, not the writer), and the amended B3d warned that totals cannot separate the two. Heap peaks are within 5 % across the four chunk values.
3. **Matched row** — Unit: B2g rows "Capacity unchanged, same identity, for LZ4 in every cell" (claim (a)), "MockCompressor forcing arm ... capacity after equals the stored chunk size, larger than before" (bare grow, no ceiling) and "Capacity proportional to chunk across cells" (claim (b)). Cluster: B3g row "R1 capacities equal the trace form above for every chunk value, R2 silent in normal runs, S2 grows to exactly `chunkSize`" plus "Peak direct usage proportional to chunk and writers; no extra step at scrub reset" for the scrub: R1 matches 4132 / 16468 / 263192 / 1052708 for all chunk values [observed], R2 silent in C*, W4, U [observed], S2 R3 = chunkSize [observed]. Writer count: W4 shows 4 concurrent compaction writers against 1 [observed].
4. **Excluded rows** — "Capacity differs from the initial length with a real compressor" (Refuted): all 8 lz4 cells and all S1 R3 lines have the initial capacity [observed]. "Mock: capacity clamped at some limit": the forcing arm grew to the full 1,048,576 [observed]. "Capacity flat across chunk sizes / usage independent of chunk_length" (control failed): R1 capacities scale with chunk and the pool delta rises with chunk [observed]. "Branch never evaluated": excluded by the file-length proof (unit) and R2 (S1) [observed]. "R2 prints in a normal run or S1 with chunkSize > capacity": excluded, R2 silent in C*/W4/U, and chunkSize 16454 < 16468 [observed]. "Usage follows a node-level limit": `MaxDirectMemorySize` 1g was never approached (pool peak 80 MB) [observed]. "Compaction never opened more than one writer": W4 had 4 [observed]. "S1 never evaluates :247": excluded, 3 of 3 evaluated it.
5. **Observed vs. inferred** — Inferred: (i) that the 1.1 MB pool floor is read-side buffers of the compaction (reason: it is present with chunk 4 KiB, absent for the uncompressed table, and the compaction opens four input readers); the verdict does not depend on it. (ii) That "no shipped compressor can fire the branch" (source argument in A3 step 5 as amended: stored <= max(bound, chunk) <= bound): the runs support it for LZ4 only; Snappy, Zstd, Deflate and Noop were not run. (iii) That the S1 corruption model (one flipped byte in a compressed chunk) is a representative scrub failure.
6. **Deviations and gaps** — No sub-step n/a; the real scrub path was reached in all 3 offsets. The original B3f sentence "roughly 2 x chunk x writers" for the pool total was not met numerically (pool totals are 3.6 x that at chunk 1024, both for one and for four writers, and 1.1 MB at 4 KiB); the audit amendment had already moved the decisive reading to the R1 trace, and the sentence is recorded here as a miss of the pool-total wording, not hidden. Only LZ4 was run in the cluster; only 3 corruption offsets with one chunk size (16 KiB); no run with the node's 1 MiB-chunk table through scrub. The scrub path raised `java.lang.AssertionError: Buffer holder has not been acquired` (`WrappingRebufferer.offset`) to `nodetool scrub` (rc 2) in all four scrub lifetimes after the CRC failure; the scrub still finished with the other partitions in the new SSTable (`complete: 3 partitions in new sstable`, 120 / 80 / 160 rows readable). That is outside this case and not examined. The docs URL in A5 was not opened (as the writer states).
7. **Core question** — Usage of the writer scratch follows `chunk_length_in_kb` (R1: 4132 -> 1052708 B across the four values, times the number of live writers: 1 vs 4 in W4) and nothing else: the `compressed.capacity() < chunkSize` check at :247 did not bound it. With a real compressor it never grew the buffer, even in the real scrubber failure path (3 of 3), and when the grow was forced (unit Mock arm, cluster S2) the buffer became exactly the stored chunk size with no ceiling. So the check is a bare grow-on-demand, not a cap, and the claim "the constraint does not cap usage" held at both tiers (steps: R1 trace, R2/R3 trace, forced arms, as in the B1 logic).

**Conclusion (one line):** unit B2g "Capacity unchanged, same identity, for LZ4 in every cell" plus "Mock forcing arm grows to the stored chunk size, no ceiling" (claim held: does not cap); cluster B3g "R1 capacities equal the trace form, R2 silent in normal runs, S2 grows to exactly `chunkSize`" (claim held: does not cap) — confirmed.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses `unit-readings.txt` and the raw Byteman traces (not the runner's EXPECTED lines) and recomputes the formulas: `SELFCHECK ALL PASS 26 / 26` (`run1/unit-junit-and-selfcheck.txt`). The cites below were re-read after it ran.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `traces-excerpt.txt`: `reset` lines show `curChunkOffset` (526624, 378508, 674746) different from the R2 `curChunkOffset` (493708, 329134, 658288, the mark's chunk after the assignment at :244), so :233 was false; `cluster-summaries.txt`: schema read-back and sstable counts for each arm; `unit-readings.txt`: early arm unchanged length, normal arms shrunk. |
| 2. Readings | yes | Pool numbers re-read in `cluster-summaries.txt` (1,121,970 ... 29,605,041); the 1.1 MB floor and the miss of the original B3f pool wording are stated, not smoothed. |
| 3. Matched row | yes | R1 values in `traces-excerpt.txt` equal 4132 / 16468 / 263192 / 1052708 (selfcheck recomputed `4+n+n/255+16`); S2 R3 cap 16454 = R2 chunkSize 16454. |
| 4. Excluded rows | yes | R2 appears only in the S arms (selfcheck: "no r2 anywhere in the trace" for C*/W4); U has no ks init lines; W4 overlap interval list printed by selfcheck. |
| 5. Observed vs. inferred | yes | Inferred (i)-(iii) are listed in 4.2 part 5; the verdict does not rest on (i); (ii) limits the "no shipped compressor" statement to LZ4 as run, plus the source argument. |
| 6. Deviations and gaps | yes | Original B3f pool sentence recorded as a miss; AssertionError in the scrubber recorded; only LZ4 run. |
| 7. Core question | yes | Steps follow B1: size set by chunk (R1), branch not reached with real compressors (R2 silent; S1 evaluated and did not grow), forced grow has no ceiling (unit Mock, S2). |

### 5.2 Run 2?

**No** — decided 2026-10-26. The conclusion rests on direct per-writer traces and exact numbers that the self-check recomputed from raw files; the one inferred statement the verdict depends on (a real compressor cannot fire the branch) is backed by the source argument and 8 + 3 observations on LZ4, and the result confirms the estimate rather than refuting it.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative. **Outcome class:** true negative (negative, does not cap).

**Claim tested (B1):** (a) the reallocation at :247-250 is not a cap: it never fires for real compressors, so the capacity of `compressed` stays equal to `initialCompressedBufferLength(chunk_length)`; when forced it grows to exactly the stored chunk size with no ceiling. (b) Writer scratch memory follows `chunk_length_in_kb` (with the number of concurrent writers), not any node-level limit. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed: "Capacity unchanged, same identity, for LZ4 in every cell"; Mock forcing arm "bare grow, no ceiling"; "Capacity proportional to chunk" | does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed: "R1 capacities equal the trace form, R2 silent in normal runs, S1 evaluated :247 without growing (3 of 3), S2 grows to exactly `chunkSize`" | does not cap | run 1 + self-check | 2026-10-26 |

**Positive control** (negative-estimate file): the instrument sees a grow when one happens: unit Mock forcing arm (capacity chunk/2 -> chunk, new identity, four chunk values) and cluster S2 (64 -> 16454 = chunkSize, new identity); and the buffer moves with the knob: R1 capacity 4132 -> 1052708 over the chunk sweep, and 4 vs 1 concurrent compaction writers (W4 vs C1024). The uncompressed arm U (no writer built) is the negative control.

**Case-file sha256 after the section D feedback:** `697793634f1900b5a51e08a4093590fbf9bf2301d2ee2b68245478d3435eb891` (frozen version before it: `0ce1a274...f9ad7`).

**Feedback filed:** the case file's section D updated with the audit amendments and this verdict (the orchestrator commits). Sections amended before any reading: A3 step 5, B2b, B2c, B2f, B2g, B2h, B3c, B3d, B3f, B3g (all dated 2026-10-26).

**Leftovers on pc12:** none running (no `CassandraDaemon`, no `ant`, ports 7327/9327/9349/7027 free). Files remain: `~/s4-cs` (the tree, with `ChunkBufferGrowthTest.java` and `build/`), `~/s4-cs-logs/`, `~/s4-cs-harness/`. Node data `~/s4-cs-data` was removed.
