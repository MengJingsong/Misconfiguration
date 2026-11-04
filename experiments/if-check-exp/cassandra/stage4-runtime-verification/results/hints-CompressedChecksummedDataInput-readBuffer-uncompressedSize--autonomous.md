# hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous — stage-4 results  <!-- file: results/hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous`](../../stage3-ai-deep-read/cases/hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous.md)
>
> **Status:** **Closed 2026-10-25 - unit Confirmed, cluster Confirmed - does not cap** (estimate negative, matched); one control re-run (D2); no run 2
>
> **Outcome class:** true negative — stage-3 estimate (negative) vs the stage-4 effect on the constraint (does not cap)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Autonomous file. sha256 of the whole file after the audit's amendments (`sha256sum`, 2026-10-25, before any harness reading or run): `a47bfe22711f509e93a2eb232a4beb2afb6e3c2e9a67865274d1d963db89808a` (as filed by the writer: `a53866f1ac1249f934494c4afc1f9aea770f95fbc87c077f9d423c6a2584d789`). Frozen hash of the prediction and conclusion tables plus the amendment block, i.e. `sed -n` of `**B2f.`..`**B2h.`, `**B3f.`..`**B3h.` and `**Audit amendments`..`## C.` in that order, piped to sha256sum: `1cd443fabb275072398315fc01f0668490a893997a664f0d39da8e831ac112a7`. Commit holding the file: none yet (the orchestrator commits; base `f33e621`). **Amended once more on 2026-10-25 after the first control attempt (D2, amendment R11, control mechanism only):** sha256 `61b2eca86591215094d6a3de9d93347b71e7d62acc3f54aac7ef352ff3c03b32`; removing the R11 paragraph restores `a47bfe22…` and the freeze hash above, so no prediction or conclusion row moved. **Final sha256 of the file with section D filed: `3e58d743b4f80458a270c81fed834b78e7b16431f69fe1b9bc5b9a10c1754659`** (this is the value for `_INDEX.md`). |
| **Harness** | `harness/hints-CompressedChecksummedDataInput-readBuffer-uncompressedSize--autonomous/` (README.md there): `ReaderBufferGrowthTest.java` + `unit-run.sh` (unit tier), `cluster-run.py`, `client.py`, `make-node-yaml.sh`, `hu.btm`, `HuHelper.java`, `Jmx.java` (cluster tier), `selfcheck.py`, `HuControl.java` + `hu-inject.btm` (added for D2/R11). Not committed by this agent (the orchestrator commits). **Instrument checks (not readings):** `javac` of the test against the clone; unit shakedowns 1-4 (shake4: three cases, 33 checks, no mismatch, after fixing the harness parse of the block header offset and the empty-block count); `TestScript` on `hu.btm` (3 rules) and `hu-inject.btm` (2 rules), no errors; cluster shakedown (`HU_RUN=shake1`, one cell, 8 x 1 MiB) and control shakedown (`HU_RUN=shake2`, inject at 16 MiB). |
| **Tiers and values** | Unit (B2, amended): LZ4 single block with blob 1 KiB, 100 KiB, 120 KiB, 128 KiB, 129 KiB, 1 MiB, 16 MiB-1 KiB; orders [1 KiB, X] and [X, 1 KiB] for X = 100 KiB, 1 MiB; Deflate 100 KiB and 1 MiB; `file_cache_size` 1, 16, 512 MiB, a fresh JVM per case; positive control (400 x 64 KiB held) at each; forged header (512 MiB over a 2 KiB block). Cluster (B3, amended): node A and B on loopback (127.0.13.1/.2), B down while writing, `file_cache_size` 1, 16, 512 MiB x value 1 KiB (50,000), 100 KiB (500), 1 MiB (64), 8 MiB (8), LZ4 hints compression; positive control: compressed-table reads with the chunk cache on at 16 and 512 MiB. |
| **Audit bottom line** | **Ready after amendments** - 2026-10-25 |

### 1.1 Design audit

The requirements are in the README, "Step 0 — the design audit". One row per
line of each group; cite the case-file section checked.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | B1/A2: off-heap (or heap, Deflate) bytes of one hint reader's decompression buffer, and the `file_cache_size` pool threshold it is compared with. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | B2b/B3b vary `file_cache_size` (1 MiB, 512 MiB) and the block size S, but two knob values only, and 1 MiB is a degenerate value (R1: the pool grows in 8 MiB steps). Amended: {1, 16, 512} MiB (R1, R8). The hard-coded line-134 comparison itself cannot be varied; the design varies the operand S instead, which is the right approach. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d name the counters and the JVM direct pool; B3d said per-reader capacity is not observable. It is, by a Byteman rule at line 141 (R9), and by reflection in the unit tier. The gap that remains: the direct-pool total carries Netty frames of the outgoing hints (named in R9). |
| A. Core question | usage driven to the limit and past it | Met after R1/R7/R8 | The 'limit' is the pool threshold. At 1 MiB it is passed by any request (no chunk fits); at 16/512 MiB by blocks > 128 KiB. The filed B3 sizes 1 KiB/100 KiB reach it only because blocks aggregate to 256 KiB (R7); 8 MiB blocks give ~17.6 MiB against a 1 or 16 MiB threshold. |
| B. Logic | each step says what it establishes | Met | B2e/B3e steps name their readings. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f/B3f are in numbers but several are wrong against the source: macro chunk is 8 MiB not 1 MiB (BufferPool.java:385,443); capacity is exactly S+S/20 and not rounded (:1394-1398,1464); 128 KiB is unpooled; Deflate is heap (DeflateCompressor.java:228-231); 1 KiB/100 KiB hints form 256 KiB blocks (HintsWriter.java:200-221). Amended R1, R2, R3, R7 as exact relations over the headers read from the raw files. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | B2g/B3g cover refuted/confirmed/control-did-not-move/limit-not-reached for the unit tier; B3g lacks a row for the control reading missing (R10 adds it). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Confirmed needs capacity independent of `file_cache_size`, overflow above the threshold with no refusal, and the control binding where the cap applies (pooled path). |
| B. Logic | alternative explanations and their controls | Partly | B2h's control used a 1 MiB threshold, which cannot show a binding cap (R1: nothing is pooled at 1 MiB); B3h's control read workload was not specific. Amended R1 (16 MiB, exact numbers) and R10. Compressed-buffer subtraction in B2h is replaced by exact per-buffer accounting (R6, unit model). |
| C. Specific | a human can follow it from the intro and §9a | Met | Ground, A1-A3 and B1 explain the path; the amendment block lists the corrections. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | B2c's 'blocks [S, S, 2S...]' sentence is garbled and B2a proposed ant testsome plus yaml copies; replaced by R6 (one block per session, header-derived Z) and the harness. Empty blocks (Z=0, C=5) that `Session.append` writes before every hint larger than 256 KiB (HintsWriter.java:205-209) were not known to the writer; found in the shakedown, they change the block count but not the claim (recorded in the harness README). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Met after R6/R8/R9 | Values, counts, sampling and stop condition (hints directory empty) are in the amendments and the scripts. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Two-node loopback harness, Byteman and the client are adapted from the WRITE_BUFFER_SIZE harness; the unit class runs outside `ant testsome` (fresh JVM per case). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | B3c's 2,000 x 1 MiB and 5,000 x 100 KiB were 2.5 GiB of hints per cell for nothing (R8). Reduced to 50-64 MiB per cell; disk per cell < 250 MiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked and correct: CompressedChecksummedDataInput.java:35,45,104,110-116,118-126,134-138,157; ChecksummedDataInput.java:56; RandomAccessReader.java:34; HintsWriter.java:200-221; HintsWriteExecutor.java:50; HintsBuffer.java:152; HintsService.java:110; BufferPools.java:38; BufferPool.java:233-239,443-451,940-943; Config.java:407,447,497; conf/cassandra.yaml:753. Off by one or loose: CompressedHintsWriter.java:49 (originalSize is :50), BufferPool.get '~900-925' (is :904-924). Wrong: '1 MiB macro chunks' (is 8 MiB, :385). Unverified items checked: (1) where the header size is checked: nowhere before the allocation (R4); (2) the header-comment stem is the filed stem (line 1 of the case file). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| R1 | Pool grows in 8 MiB macro chunks: knob values {1, 16, 512} MiB; 16 MiB control with exact numbers | Applied 2026-10-25 (case file, amendment block; sha256 above) | `BufferPool.java:385,443`; the filed 1 MiB threshold never allocates a chunk |
| R2 | Capacity is exactly S + S/20; pooled iff <= 131,072; 128 KiB is unpooled | Applied 2026-10-25 | `BufferPool.java:1394-1398,1464,940` |
| R3 | Deflate is on-heap (counted in overflow, not in the direct pool) | Applied 2026-10-25 | `DeflateCompressor.java:228-231`, `BufferPool.java:208-209,233-239` |
| R4 | Block header size is not validated anywhere before the allocation; add the forged-header case | Applied 2026-10-25 | `CompressedChecksummedDataInput.java:110-138`, `LZ4Compressor.java:167-190`, `HintsReader.java:224,254`, global CRC never read |
| R5 | close() does not return the reader buffer; the initial buffer's put() drives overflow down by 4096 | Applied 2026-10-25 | `ChecksummedDataInput.java:113-116`, `BufferPool.java:811-820` |
| R6 | One block per session; Z/C from the raw file; fresh JVM per case | Applied 2026-10-25 | `HintsWriter.java:200-275` |
| R7 | Corrected B3f: blocks are aggregations up to 256 KiB | Applied 2026-10-25 | `HintsWriteExecutor.java:50,241`, `HintsWriter.java:200-221` |
| R8 | Cluster sizes 50,000 / 500 / 64 / 8 rows; `file_cache_size` {1, 16, 512} MiB; random values; protocol 4; throttle raised | Applied 2026-10-25 | workload arithmetic |
| R9 | Per-reader capacity is observable (Byteman line 141) | Applied 2026-10-25 | B3d "not observable" withdrawn |
| R10 | Positive control: 16 MiB, chunk cache on, compressed table; B3g row for a missing control | Applied 2026-10-25 | the B3h control had no number |

**Agreement criteria** — only if run 2 is chosen; filled before run 2 starts.
One row per observable in the case's §9d:

| Observable | Must match | Tolerance |
|---|---|---|
| `<observable>` | exactly / in shape | `<what counts as the same>` |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-25 17:42 - 18:48 MDT (unit 17:42-17:45; cluster cells 17:45-18:40; R11 control 18:40-18:47; shakedowns 17:33-17:42 and 18:2x, not readings); UTC in `timing/set-A-batch-5.log` | not done |
| Node (CloudLab name and type) | `pc12` = `node1.jason92-320876.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB), reached over ssh from `pc07`. **Environment deviation E1:** both cluster nodes on this host on loopback (A 127.0.13.1 / JMX 7213 / Byteman 9113, B 127.0.13.2 / JMX 7214; native 9145 and storage 7013 on both addresses), as in the WRITE_BUFFER_SIZE run; the design is unchanged. **E2:** the unit tier runs the harness class in one JVM per case outside `ant testsome` (audit R6), classpath and JVM flags of `build.xml`'s `test-run`/jvm11 items. | - |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | - |
| JDK (`java -version`) | openjdk 11.0.32.1 (2026-08-18) | - |
| Ant (`ant -version`) | 1.10.12 | - |
| Local source copy (from `cassandra/cassandra-5.0.9/` at repository commit …) | `~/s4-hu` made by `copy-source.sh` from the repository at `f33e621` (`cassandra/cassandra-5.0.9/` unmodified: `git status --short` empty), local tag `cassandra-5.0.9`; `ant build-test` 1 min 12 s | - |
| Case-file commit / harness commit | case file: not committed by this agent; sha256 `a47bfe22…` at the first freeze and unit tier and the 12 cluster cells, `61b2eca8…` after R11 (D2) for the control (full values in the verdict section); harness not committed (the orchestrator commits); md5 of the node copy before the runs in `run1/harness.md5` (node copy: `cluster-run.py` 7d60e21f… for the cells; the repo's `cluster-run.py` 86fdbb69… adds the `inject` mode used for the R11 control only) | - |
| Storage for node data | `~/s4-hu-run/{A,B}` on local `/dev/sda3` (spinning, ROTA 1), 45 GiB free at start; the unit tier writes a temp dir deleted at the end of each case | - |
| Full logs (path, outside the repo) | `pc12:~/stage4-logs/hu/run1/` (`unit/`, `cluster/<cell>/` with `hu.trace`, `hints-blocks.json`, samples, system logs; `selfcheck.txt`); shakedowns `~/stage4-logs/hu/shake{1,2,3,4}/`; excerpts in `results/<stem>/run1/` | - |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster, cells with 1 KiB values | B3e step 3 / harness check "the hint files hold the values" | The harness compared the **compressed** `.hints` file size with rows x value bytes. The 1 KiB cells reuse 64 random values (a client choice), which LZ4 compresses across a block, so the file (46.3-46.7 MB) is below 0.99 x 51.2 MB: three `EXPECTED ... NO` lines (f1, f16, f512 at 1 KiB). Not a runbook step that failed: the values were all written. | Validity is judged from the raw headers instead: sum of the blocks' Z = 54,650,000 B = 1.067 x the values at 1 KiB (1.001 at 100 KiB, 1.000 at 1 MiB and 8 MiB) in every cell (`run1/cluster/*/hint-blocks.txt`). No change to B3 predictions. | 2026-10-25 (recorded; harness left as run) | none (no case-file change) |
| D2 | cluster, control (B3h) | B3h / audit R10 control: compressed-table reads with the chunk cache on, `file_cache_size` 16 MiB | The control cannot bind. `ChunkCache.cacheSize = file_cache_size - 32 MiB` and the cache exists only if positive (`ChunkCache.java:49-54`): at 16 MiB it is off and the pool stayed at its start-up 8 MiB (peak pooled part 8,388,608, OverflowSize 0, 6,144 reads, `run1/cluster/control_f16/`); at 512 MiB it grew the pool to 167,772,160 without meeting the threshold. A cache sized below the threshold never presses on it. This was a defect of the audit's own R10 (found by the reading "the control did not move"), independent of B3f/B3g, which are unchanged. | Amendment R11 in the case file (dated 2026-10-25): the control runs in the node's own JVM (`HuControl`, `hu-inject.btm`: 400 x 64 KiB taken from the chunk-cache pool and held, flag file, 10 s tick of `HintsDispatchTrigger.run`) at `file_cache_size` 1, 16, 512 MiB. The R10 reads stay as supplementary readings. The 12 cells do not use the control (a separate lifetime, a separate Byteman file and helper jar) and were not repeated; only the control lifetimes were run again. | 2026-10-25 | not committed; case-file sha256 after the fix `61b2eca8…` (the frozen tables and every earlier amendment are byte-identical: removing the R11 paragraph restores `a47bfe22…` and the freeze hash `1cd443fa…`) |
| D3 | unit, harness checks | harness (instrument, no case-file step) | (a) the test's own check "empty blocks = hints larger than 256 KiB" counts the forged header (Z = 512 MiB) as oversized: one `MISMATCH` line in `f16_forged` (517 checks, 1 mismatch); the forged block is a real 2 KiB block with no empty block before it. (b) `unit-run.sh`'s summary lines show empty `rc` text because the harness `STAGE4 summary` lines carry a logger prefix; the numbers are in `test.out`. (c) The first self-check version asserted that 128/129 KiB blocks exceed the 1 MiB threshold at `file_cache_size` 1 MiB (their size delta is 0.27 MB; the relation applies from blocks of 1 MiB) and that peak overflow is byte-equal across `file_cache_size` (random values differ in compressed size by 1-30 bytes at >= 100 KiB, by up to 3 % at 1 KiB). Fixed before it was used for the verdict: a threshold check from 1 MiB blocks, equality within 1 % at >= 100 KiB. | none needed beyond recording; no case-file change | 2026-10-25 | none |

## 4. Run 1

**Scope:** unit tier: 43 cases (LZ4 1 KiB / 100 KiB / 120 KiB / 128 KiB / 129 KiB / 1 MiB / 16 MiB - 1 KiB blobs, four two-block orders, Deflate 100 KiB / 1 MiB, the pool control, at `file_cache_size` 1, 16 and 512 MiB; the forged header at 16 MiB). Cluster tier: 12 cells (`file_cache_size` 1, 16, 512 MiB x 1 KiB, 100 KiB, 1 MiB, 8 MiB values), the pool control in the node's JVM at 1, 16, 512 MiB (R11), and the chunk-cache read control at 16 and 512 MiB (supplementary). No second run of any cell. **Command log:** `run1/unit/summary.txt`, `run1/cluster/<cell>/summary.txt`, `run1/selfcheck.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/test-lines.txt`, one JVM per case; Z = the block header's uncompressedSize parsed from the raw file; "overflow" and "size" are the deltas of `overflowMemoryInBytes()` and `sizeInBytes()` of the chunk-cache pool over the read; capacity read by reflection)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Capacity after a block = 4096 if Z <= 4096 else Z + Z/20, for every Z and compressor | 43/43 cases, 517 harness checks of which 516 `ok` (the one mismatch is D3a); Z 1,089 -> 4,096; 102,466 -> 107,589; 122,946 -> 129,093; 131,138 -> 137,694; 132,162 -> 138,770; 1,048,642 -> 1,101,074; 16,776,259 -> 17,615,071 | `unit/test-lines.txt`, `selfcheck.txt` (SC unit ... capacity) |
| Same final capacity at `file_cache_size` 1, 16, 512 MiB | equal for every case name (13 names x 3 values) | `selfcheck.txt` (SC unit ... equal at fcs 1, 16, 512) |
| Pooled iff cap <= 131,072 and the threshold admits a chunk (8 MiB steps) | 100 KiB (cap 107,589) and 120 KiB (cap 129,093) at 16/512 MiB: overflow delta -4,096 (only the initial buffer's put); 128 KiB (137,694) and 129 KiB: overflow 271,838 / 273,994 at every threshold; at 1 MiB every case is overflow (100 KiB: 211,509) | `unit/test-lines.txt` |
| Overflow above the threshold with no refusal | `file_cache_size` 1 MiB, 1 MiB block: overflow = size delta = 2,202,376 (2.10 x 1 MiB); 16 MiB block: 35,295,131 at 1, 16 and 512 MiB (threshold 16,777,216 at 16 MiB); no exception in any case | `unit/test-lines.txt` (case f1_lz4_1m, f16_lz4_16m) |
| Capacity does not shrink: orders [1 KiB, X] and [X, 1 KiB] | final capacity cap(X) in both orders at all thresholds (X = 100 KiB, 1 MiB) | `selfcheck.txt` |
| Positive control, 400 x 64 KiB held | pooled bytes / overflow bytes: 1 MiB: 0 / 26,214,400; 16 MiB: 16,777,216 / 9,437,184; 512 MiB: 33,554,432 / 0 (exact, pooled never above the threshold); after `put` overflow returns to its start | `unit/test-lines.txt` (case f*_control), `selfcheck.txt` |
| Deflate (heap): capacity 1.05 Z, counted in overflow, nothing in the direct pool | 100 KiB: cap 107,589, overflow 211,125; 1 MiB: cap 1,101,074, overflow 2,198,394; direct-pool delta 0 at all thresholds | `unit/test-lines.txt` |
| Forged header (R4): 2 KiB block, Z rewritten to 536,870,912 | read without error, 1 hint, buffer capacity 563,714,457, overflow +563,710,361 (the JVM direct pool +563.7 MB) | `unit/test-lines.txt` (f16_forged) |
| Accounting (R5, supplementary): after close | overflow stays at cap(Z) - 4,096 for an unpooled reader buffer (the compressed buffer is returned); the pooled slot is not returned | `unit/test-lines.txt`, `selfcheck.txt` |

**Cluster tier** — A and B on loopback, B down while writing, one `.hints` file of A per cell, `hints_compression` LZ4; cap = largest reader buffer capacity in A's Byteman trace; Zmax = the largest block header in the raw hint file; "peak overflow" = chunk-cache `OverflowSize` over its pre-replay baseline; every cell: replay completed in 41-47 s, 0 `ERROR` lines and 0 `OutOfMemoryError` in the A and B system logs (the A log of f1_b1048576 holds only the part after UTC midnight), the trace's (Z, C) pairs equal the raw headers, 0 deviations from the overflow model after every block and reader close

| Capacity value (`file_cache_size`) | Run (value size, rows) | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| 1 MiB / 16 MiB / 512 MiB | 1 KiB, 50,000 | Zmax -> cap observed; peak overflow (compressedBuffer cap) | 261,227 -> 274,288 at all three; 529,897 (259,705) / 514,082 (243,890) / 528,930 (258,738) | `cluster/f*_b1024/` |
| 1 / 16 / 512 MiB | 100 KiB, 500 | the same | 204,940 -> 215,187 at all three; 427,125 (216,034) at all three | `cluster/f*_b102400/` |
| 1 / 16 / 512 MiB | 1 MiB, 64 | the same | 1,048,646 -> 1,101,078 at all three; 2,202,381 / 2,202,382 / 2,202,382 (1,105,399-1,105,400) | `cluster/f*_b1048576/` |
| 1 / 16 / 512 MiB | 8 MiB, 8 | the same | 8,388,679 -> 8,808,112 at all three; 17,646,672 at all three (8,842,656) | `cluster/f*_b8388608/` |
| 1 MiB, 16 MiB | 8 MiB / 1 MiB | Size over baseline vs the threshold | 17,646,672 > 1,048,576 and > 16,777,216; 2,202,381 > 1,048,576; no refusal, no error | `cluster/f1_b*`, `cluster/f16_b8388608` |
| 1 / 16 / 512 MiB | control: 400 x 64 KiB held in the node (R11) | pooled part (`Size - OverflowSize`) / OverflowSize | 0 / +26,214,400; 16,777,216 / +9,437,184; 33,554,432 / 0 | `cluster/inject_f*/` |
| 16 / 512 MiB | supplementary control: chunk-cache reads (D2) | pooled part | 8,388,608 (cache off); 167,772,160 | `cluster/control_f*/` |

### 4.2 Conclusion and logic

1. **Validity** - the limit was reached and each "hold fixed" setting is confirmed. Unit: every case wrote a real file with the production `CompressedHintsWriter` and read it with `HintsReader`; Z and C were parsed from the raw file, so the operand of line 134 is known independent of the reader [observed: `unit/test-lines.txt` block lines]. Cluster: the pool threshold seen by the node equals the configured value in every cell (Capacity gauge, `thr=` in the trace; 1,048,576 / 16,777,216 / 536,870,912) [observed: `cluster/*/hu.trace` -> `trace-compact.txt`]; the hint files held all values (sum of Z >= rows x value bytes in all 12 cells; D1) [observed: `cluster/*/hint-blocks.txt`]; the replay read every block (trace blk lines = raw blocks, (Z, C) pairs equal) and every cell emptied A's hints directory [observed: `cluster/*/summary.txt`]. Pool state is fresh per JVM (unit: one per case; cluster: one per cell) [observed]. Blocks above 128 KiB were reached in all 12 cells: at every value size the largest block exceeds 128 KiB (1 KiB values aggregate to 261 KB blocks, 100 KiB values to 205 KB, 1 MiB and 8 MiB values are their own blocks) [observed: Zmax column]. The positive control moved (see 3). No cell is invalid.
2. **Readings** - unusual items: (a) every hint above the 256 KiB write buffer is preceded by an empty block (Z = 0, C = 5): `Session.append` flushes the empty aggregation buffer first; the reader logs "Unexpected EOF replaying hints" for each, ends that page, and the next page reads the real block (`Unexpected EOF` warnings in A's system log: 64 in the 1 MiB cells at 16 and 512 MiB, 8 in each 8 MiB cell, 0 in the 1 KiB and 100 KiB cells - equal to the number of Z = 0 blocks in each raw file; the 1 MiB cell at 1 MiB cannot be counted because A's `system.log` rolled at UTC midnight during that cell and the copy holds 32 lines), and the replay completes in every cell [observed: `hint-blocks.txt`, A/B system logs on the node, `summary.txt`]. (b) The JVM direct-pool total over the replay (34-93 MB in the trace) is not constant across `file_cache_size` for the same value size (1 MiB values: 70.4, 70.4, 36.8 MB) and is far above the pool's own counters; it carries other direct users, most likely Netty frames of the outgoing hint messages [inferred: the pool counters and the capacities are exact, the remainder is not attributed]. The conclusion does not use the direct total. (c) The three D1 `NO` lines. (d) The R10 read control at 16 MiB did not move (D2); the R11 control did.
3. **Matched row** - Unit, B2g row 1: "capacity ~ 1.05*S for all S, same for both file_cache_size values; overflow > threshold for S > 128 KiB -> claim confirmed (usage does not follow the knob)" - capacity = Z + Z/20 exactly in all 43 cases and equal at 1, 16 and 512 MiB [observed], with the amended reading of "S > 128 KiB" as cap(Z) > 131,072 (Z >= 124,832); overflow above the threshold with no refusal (1 MiB block at 1 MiB: 2,202,376; 16 MiB block at 16 MiB: 35,295,131) [observed]. Row 4 as well: the positive control's pooled bytes stay at or below the threshold (0, 16,777,216, 33,554,432) while the hint blocks overshoot it. Cluster, B3g row 1: "peak replay memory ~ 2.1x B for B >= 1 MiB, identical across the file_cache_size values -> claim confirmed" - in the amended terms of R7 (chunk-cache overflow rises by cap + compressed cap): 2.10 x 1 MiB = 2,202,381-2 and 2.10 x 8 MiB = 17,646,672, equal across the three thresholds within 1 byte (1 MiB) and exactly (8 MiB) [observed]; and row 4: the pool control is flat at the cap (16,777,216 pooled at 16 MiB, 9,437,184 overflow) while the 8 MiB replay at 16 MiB holds 17,646,672 B of overflow, above the 16,777,216 threshold [observed].
4. **Excluded rows** - B2g row 2 (capacity or direct memory scales with / is clamped by `file_cache_size`): capacity is identical at 1, 16, 512 MiB, overflow exceeds the threshold [observed]. Row 3 (a plateau below S with an error): no error in any of 43 cases or 12 cells, forged 512 MiB header read in full [observed]. Row 4 (control: "positive control pool stays <= threshold while blocks exceed it" - this is the Confirmed row). Row 5 (control pool does not stop at the threshold or overflow does not rise with S): the control stopped exactly and overflow rose with S [observed]. Row 6 (S never reached the header): every block header was read (trace = raw) [observed]. B3g row 2 (peak capped near `file_cache_size`): the 8 MiB replay peaks at 17.6 MB with the threshold at 1 and 16 MiB [observed]. Row 3 (the 1 MiB run fails or logs errors for large hints while 512 MiB works): no errors, 8/8 replays complete at 1 MiB [observed]. Row 5 (no hints, or the control does not hit the cap): hints were produced and replayed in all 12 cells; the control hit the cap at 16 MiB exactly [observed]. The R10 row (control reading missing / never reaches 16 MiB): the R10 reads did not (D2), the R11 control did, so the row does not apply to the amended control.
5. **Observed vs. inferred** - inferred: (i) that the node's pool behaves under the R11 stand-in (`HuControl.inject`, a call to the same `BufferPool.get` from the dispatch-trigger thread) as it does for the hint reader's pooled requests (same class and counters; the hint reader's own requests were all above 128 KiB, so they never entered the pooled path [observed]); (ii) the Netty explanation of the direct-pool total; (iii) that on a deployment with two real hosts the numbers would be the same (E1; the buffers are per reader, not per link); (iv) that a 16 MiB block is the largest an unforged file contains (derived from `HintsBuffer.java:152` and `max_mutation_size`; the 16 MiB - 1 KiB value case reached 16,776,259).
6. **Deviations and gaps** - E1, E2, D1-D3; B2e step 5 "repeat with the order of block sizes swapped" was done for X = 100 KiB and 1 MiB only; the cluster tier used one value per cell and one run per cell (no repeats; the cells at one value size agree with each other); Snappy not run (native library); the writer's unit test via `ant testsome` was replaced by per-case JVMs (E2); no thread-level view of a real OOM: the forged case allocates 563.7 MB under `-XX:MaxDirectMemorySize=1g` without failing, an allocation of more than the cap would be an `OutOfMemoryError` from `allocateDirect` (not run).
7. **Core question** - Usage of the hint reader's decompression buffer does not follow `file_cache_size`: its capacity is 1.05 x the block header's uncompressed size, identical at 1, 16 and 512 MiB (parts 3, 4), the size comes from the file and is not bounded by any configured value before the allocation (R4; forged 512 MiB header allocated 563.7 MB), and blocks above 128 KiB are allocated outside the pool and counted only in the overflow gauge, so the memory goes past the threshold (unit 35.3 MB at a 16.8 MB threshold; cluster 17.6 MB at 16.8 MB). The threshold does cap what it governs - pooled traffic of 128 KiB or less (control: exactly 16,777,216 pooled at 16 MiB, the rest overflowing) - but the line-134 buffer is not on that path. The constraint does not cap this usage; the indirect bounds (`max_mutation_size`, the 256 KiB write buffer) are properties of the writer.

**Conclusion (one line):** Unit B2g row 1 (with row 5) and cluster B3g row 1 (with row 4) - the negative claim is confirmed: usage does not follow `file_cache_size` and the constraint does not cap it.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/<stem>/selfcheck.py` re-parses the raw files (`unit/test.out`, `cluster/*/hu.trace`, `hints-blocks.json`, `samples-jmx.csv`, `inject.log`) with its own code, not the harness's `ok` lines: 262 checks ok, 0 FAIL (`run1/selfcheck.txt`). I also re-opened the files named below.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | The threshold values (`thr=`) in all 12 traces are 1,048,576 / 16,777,216 / 536,870,912 as configured; raw headers = trace (Z, C) in each cell (SC cluster ... multiset); sum of raw Z >= rows x value bytes in all cells (re-computed from `hint-blocks.txt`, ratios 1.067 / 1.001 / 1.000 / 1.000); the replay left no `.hints` file (summary lines). |
| 2. Readings | yes | Empty blocks seen in `hint-blocks.txt` (8 Z=0 entries in the 8 MiB files, 64 in the 1 MiB files, none at 1 KiB / 100 KiB); the direct-total spread is in the traces (`trace-compact.txt`), flagged as not used. |
| 3. Matched row | yes | Capacity = cap(Z) in 43/43 unit cases and 12/12 cells (SC unit / SC cluster `max reader capacity = cap(max raw Z)`); equal across thresholds (SC unit `equal at fcs 1, 16, 512`, SC cluster `capacity equal across file_cache_size`); overflow over the threshold: SC unit `size delta exceeds the 1 MiB threshold`, SC cluster `Size over baseline exceeds file_cache_size` (1 MiB and 8 MiB at 1 MiB). The control rows: SC unit control (9 checks) and SC control (10). |
| 4. Excluded rows | yes | Re-counted on the node: `^ERROR` 0 and `java.lang.OutOfMemoryError` 0 in the A and B system logs of all 12 cells and of the control lifetimes (A log of f1_b1048576 partial, see 4.2 part 2); the replay finished and the trace is complete in that cell; the forged-header case read 1 hint; the self-check found no `STAGE4 error` line. |
| 5. Observed vs. inferred | yes | The inferred items (stand-in control, Netty, two hosts) are named; the observed ones each cite a file above. |
| 6. Deviations and gaps | yes | E1, E2, D1-D3, the single run per cell and the missing Snappy case are recorded; D3(c) shows the self-check itself was corrected for two over-strict relations before use. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic of the B1 block: S from the header is not clamped (unit capacity and forged), the pool threshold applies to pooled traffic only (control), the hint reader's request is not pooled (trace: overflow, not pooled part, rises), hence usage exceeds the threshold. |

### 5.2 Run 2?

**No** - 2026-10-25. The conclusion rests on exact relations over raw headers read back from the files, a model that predicted every block's counters with 0 deviations in 43 + 12 runs, and a control that hit its cap exactly; the inferred items do not decide the verdict. The result confirms the negative estimate (no refutation, no new bypass beyond the file-supplied size, which is the claim itself). The one soft spot - the stand-in control (D2) - is covered by the unit-tier control on the same class with identical numbers.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 7. Comparison — only if run 2 was done

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** negative (the entry point is a grow-on-demand test of a file-supplied size against the current capacity; usage tracks the largest block in the hint file, not a knob). **Outcome class:** true negative.

**Claim tested:** "The size of the decompression buffer held by a `CompressedChecksummedDataInput` equals roughly 1.05 x the largest block's `uncompressedSize` in the file, independent of `file_cache_size`; for blocks > 128 KiB, off-heap usage exceeds the `file_cache_size` pool threshold without any refusal." (B1, with the amended statement that capacity is exactly `Z + Z/20` and the pooled/unpooled boundary is cap <= 131,072 and a threshold of at least 8 MiB.) "Confirmed" below means this held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1 (+ row 5, the control): Confirmed - capacity 1.05 x Z exactly, equal at 1/16/512 MiB, overflow past the threshold, forged header allocated in full | does not cap | run 1 + self-check | 2026-10-25 |
| Cluster | B3g row 1 (+ row 4, the control, as amended by R7 and R11): Confirmed - capacity cap(Zmax) in 12/12 cells, 17.6 MB of overflow at a 1 MiB and a 16 MiB threshold, no error | does not cap | run 1 + self-check | 2026-10-25 |

**Positive control** (a negative-estimate file only): the pool threshold binds where the traffic is pooled. Unit, in a fresh JVM per threshold: 400 x 64 KiB held give pooled 0 / 16,777,216 / 33,554,432 bytes and overflow 26,214,400 / 9,437,184 / 0 at 1 / 16 / 512 MiB, exactly as computed from `BufferPool.java:385,443` (pooled never above the threshold). Cluster (R11, in the node): the same numbers in the running node (`inject_f1`, `inject_f16`, `inject_f512`). The hint reader's requests are never in the pooled part (cluster: the replay changes `OverflowSize` and not `Size - OverflowSize`).

**Summary of findings** besides the verdict (not part of the claim): (1) `BufferPool.MACRO_CHUNK_SIZE` is 8 MiB, so `file_cache_size` below 8 MiB disables pooling altogether; (2) `ChunkCache` is off below `file_cache_size` 32 MiB and sized `file_cache_size - 32 MiB` above it (`ChunkCache.java:49-54`); (3) `Session.append` writes an empty compressed block (13 bytes, Z = 0) before every hint above the 256 KiB write buffer when the aggregation buffer is empty, which the reader meets as an EOF and recovers from at the next page; (4) `CompressedChecksummedDataInput.close()` leaves the reader buffer's accounting behind (unpooled: `OverflowSize` stays up by cap(Z); pooled: the slot is never returned), and the `put` of the initial 4,096-byte buffer subtracts 4,096 from a counter that never counted it (`ChecksummedDataInput.java:113-116`, `BufferPool.java:811-820`).

**Feedback filed:** the case file's section D "Stage-4 feedback" updated (not committed; the orchestrator commits); amendments R1-R11 in the case file's "Audit amendments" block (dated 2026-10-25). Final case-file sha256 after all amendments and the feedback text: `3e58d743b4f80458a270c81fed834b78e7b16431f69fe1b9bc5b9a10c1754659`.

**Leftovers:** no process left (checked `ps` for CassandraDaemon / the harness classes: none). Files on `pc12`: `~/s4-hu` (the source copy, 474 MB), `~/s4-hu-run` (2.4 MB, A/B data of the last control lifetime and `tools/`), `~/s4-hu-build.log`, `~/stage4-harness-run/hu/` (+ `hu.md5`), `~/stage4-logs/hu/` (20 MB, logs of run 1 and shakedowns), (the excerpt staging copy `~/hu-ex/` and the `/tmp/hu-*` scratch files were removed).
