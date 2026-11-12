# file_cache_size-chunkcache-weightedsize--autonomous — stage-4 results  <!-- file: results/file_cache_size-chunkcache-weightedsize--autonomous.md -->

> **Case:** [`file_cache_size-chunkcache-weightedsize--autonomous`](../../stage3-ai-deep-read/cases/file_cache_size-chunkcache-weightedsize--autonomous.md)
>
> **Status:** verdict filed (2026-11-11): unit **Confirmed — caps**, cluster **Confirmed — caps**
>
> **Outcome class:** true positive (estimate `positive`; unit Confirmed — caps, cluster Confirmed — caps)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository base commit `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4): `f49489b34b0e6f4aaf4c331797e3bae32b6bad868aff95092e9b4b40f578bd89`. sha256 of the whole file after the audit's amendments AM1-AM8 (section D, 2026-11-11): **`7e2b6706a3061b7667e18852800c01e2690fa2de0e2814ff2f3871d4d7fce591`**. sha256 of the frozen prediction and conclusions tables (text from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated, 47 lines; copy in `harness/file_cache_size-chunkcache-weightedsize--autonomous/freeze-pred.txt`): **`909809b420570536d3093a2e789139f31561c36ad2cf8634148bf264869162a7`**. The table text is the filed text; AM2 and AM8 (section D) amend one cell and define terms, and are covered by the whole-file hash. Frozen 2026-11-12 02:53 UTC (2026-11-11 local), before any reading. The cluster run used this version. After AM9 (runbook defect D1, extraction step B2e.6 only; the table hash is unchanged, `909809b4…`): **`9d07c7972968c45071396f67a4c2da5e7d68a41562d50704b9b33c79458c8376`**, the version the restarted unit run used. |
| **Harness** | `harness/file_cache_size-chunkcache-weightedsize--autonomous/` (files listed in its README; not committed by this session, the coordinator commits) |
| **Tiers and values** | Unit (B2): `fcs.mib` ∈ {32 (gate control), 33, 64, 128, 256}, file of `2·FCS+64` MiB read twice in 64 KiB chunks, single thread; overshoot probe `fcs.mib=64, hold.chunks=1024`. Cluster (B3): one node, heap 2 GiB, `MaxDirectMemorySize=4G`, 4,000,000 rows × ~1 KiB, LZ4 16 KiB chunks; settings `file_cache_enabled: false` (baseline), `file_cache_size` 64, 256, 512 MiB; 60 s idle + 10 min uniform reads (32 threads) + 60 s after, sampled every 30 s. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (AM1-AM8 applied in section D of the case file; AM9 after unit attempt 1, runbook defect D1) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: off-heap bytes of cached chunks; the operand is Caffeine's weighted size in bytes (weigher = `buffer.capacity()`, `ChunkCache.java:154`). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 32, 33, 64, 128, 256 (256 = the default with a 1 GiB heap, A1); B3b: disabled, 64, 256, 512 (512 = the default with `-Xmx2G`). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d reads the pool's allocated bytes (`sizeInBytes`, overflow) besides the operand; B3d reads JVM direct `MemoryUsed`, NMT "Other" and RSS, with the baseline subtraction for the other consumers (B3h). Gap named: which direct bytes are the cache's (B3d). |
| A. Core question | usage driven to the limit and past it | Met | B2c: each pass inserts `2·FCS+64` MiB against `FCS−32` MiB (≥ 2×); B3c: ~260,000 distinct chunks against ≤ 30,720 cacheable. |
| B. Logic | each step says what it establishes | Met | B2h/B3h name what each control and pass establishes. |
| B. Logic | prediction stated in numbers or a clear relation | Met after AM8 | B2f gives byte ceilings per N; B3f gives bands; AM8 defines "plateau", "about N", "persistently" and "climbing" numerically. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after AM8 | B2g/B3g cover capped, exceeded, flat-across-N, counter capped but real resource grows, workload never reached the cache (Requests flat). A reading matching no row is "Not confirmed (no matching row)" (AM8). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after AM7 | The ceiling follows N in B2f/B3f; direct disallow evidence: AM7 prints the load (miss) count against the final entries (unit); cluster Misses far above Entries at a capped Size (B3h Requests/Misses). |
| B. Logic | alternative explanations and their controls | Met | Positive controls: N=32 gate (instance null) and the first-pass rise from 0 (B2h); the idle samples, the rise during reads and the disabled baseline (B3h); key/row caches off; `MaxDirectMemorySize=4G` so the JVM limit is not the observed cap. |
| C. Specific | a human can follow it from the intro and §9a | Met | Header Estimate line, A2-A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | B2a gives the whole test; B3e gives the steps. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after AM3-AM6 | Stress schema compression unstated (AM3); compaction settling (AM4); instruments specified (AM5); paths, ports and heap (AM6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11 and Ant installed on apt190; the test class, run scripts and a JMX sampler are step-1 work (harness folder). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: ≤ 576 MiB file, ≤ 256 MiB pool against `MaxDirectMemorySize=2G`. Cluster: ~4-5 GB on `/mydata` (1.6 TB free); heap 2 GiB + direct ≤ ~0.6 GiB + stress client ~1 GiB, well within ~14 GiB free; ~4 × 12 min of reads. |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met after AM1, AM2 | Checked in `systems/cassandra/source` (5.0.9): `ChunkCache.java:49-54` (cacheSize, gate), `:151-157` (maximumWeight, ImmediateExecutor, weigher), `:161-175` (load from the pool), `:177-181` and `:140-144` (release), `:241` (rebuffer), `:311-314` (setCapacity throws), `:323-327` (weightedSize); `BufferPools.java:38-39`; `DatabaseDescriptor.java:576-577`; `Config.java:497-499`; `FileHandle.java:411-429`; `CacheMetrics.java:70`; `Info.java:126-139`. All as cited, except: the macro-chunk is 8 MiB, not 1 MiB (AM1), and `BufferManagingRebufferer` also draws on the chunk-cache pool, so the disabled baseline's pool `Size` is not 0 (AM2). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| AM1 | Macro-chunk is 8 MiB (`BufferPool.java:385`); `sizeInBytes` includes overflow | applied 2026-11-11, section D (untracked file, no commit) | citation accuracy; bounds unchanged |
| AM2 | Disabled-row pool Size: small multiple of 8 MiB, ≤ 32 MiB, not 0 | applied 2026-11-11 | `BufferManagingRebufferer.java:45` draws on the same pool; from the source, before any reading |
| AM3 | Stress schema `compression=LZ4Compressor`; same `-col` for reads; ports | applied 2026-11-11 | stress default is `compression = {}`; B3c assumes LZ4 16 KiB |
| AM4 | Wait for 0 pending compactions after the flush | applied 2026-11-11 | same SSTables for every setting |
| AM5 | One JMX sampler for all MBeans, plus NMT Other and RssAnon | applied 2026-11-11 | exact bytes; one JVM per sample instead of per attribute |
| AM6 | Paths, ports, heap; `ant testsome` heap is 1 GiB | applied 2026-11-11 | shared node; heap not load-bearing |
| AM7 | Unit test prints misses/requests (`O05 EVID`) | applied 2026-11-11 | direct evidence that eviction ran (group B) |
| AM8 | Numeric meaning of plateau, about N, persistently, climbing; no-matching-row rule | applied 2026-11-11 | conclusions must be decidable |
| AM9 | B2e step 6: extract by joining the printf fragments (runbook defect D1) | applied 2026-11-11 after unit attempt 1; unit tier restarted | `grep 'O05 FINAL'` shows only the label |
| R-a | A3 step 6 and B2f probe text: replace "1 MiB macro-chunk" in the body text | left for stage 3 | wording; AM1 records the fact |
| R-b | Name the `BufferManagingRebufferer` use of the chunk-cache pool in A4 as another consumer of that pool | left for stage 3 | completeness of A4 |

**Agreement criteria** — not applicable (no run 2).


## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-11 local (UTC 2026-11-12): unit attempt 1 02:56-02:57; cluster shakedowns 02:58-03:14; cluster run 1 03:15-04:10; unit run 1 (restart after D1) 04:12-04:13 | not done |
| Node (CloudLab name and type) | `apt190` (`node3.jason92-325433.misconfiguration-pg0.apt.emulab.net`), 16 cores, 15 GiB RAM (~14 GiB available); shared with OOM-exp (no other Cassandra was running during the runs) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, 5.15.0-198-generic | |
| JDK (`java -version`) | openjdk 11.0.33 | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy (from `systems/cassandra/source/` at repository commit …) | `copy-source.sh /mydata/jingsong-cass-s4/o05-src` on the local machine at repository HEAD `f74aade6` (tag `cassandra-5.0.9`), rsynced to `apt190:/mydata/jingsong-cass-s4/o05/src`; `ant build-test` there (BUILD SUCCESSFUL, 1 min 42 s), which also built `build/apache-cassandra-5.0.9-SNAPSHOT.jar` used by the node | |
| Case-file commit / harness commit | case file and harness untracked at HEAD `f74aade6` (the coordinator commits); case-file sha256 in section 1; harness md5 in `harness/…/README.md` scope (files listed there) | |
| Storage for node data | `/mydata` (`/dev/mapper/emulab-node3--bs`, 1.8 TB, local); data 4,243,744,092 bytes live, 5 SSTables, LZ4 16 KiB chunks, compression ratio 0.979 (`run1/cluster-nodetool.txt`) | |
| Full logs (path, outside the repo) | `apt190:/mydata/jingsong-cass-s4/o05/logs/` — `unit/` (run 1), `unit-attempt1/`, `cluster-run1/` (samples.jsonl, session.log, stress logs, system-*.log, nodetool files), `cluster-shake*` (shakedowns) | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit attempt 1 | B2e step 6 | The test's `printf` reaches the junit log one write per `SubstituteLogger` line, so `grep 'O05 FINAL'` returns only `O05 FINAL fcs=` without values. The values were all in the log (one fragment per line). | Extract by joining the fragments (`unit-analyze.py`); case-file amendment AM9 (section D). Prediction and conclusions unchanged; unit tier restarted from its beginning (run 1, 04:12 UTC). Attempt 1's readings were the same caps (`apt190:…/logs/unit-attempt1/`). | 2026-11-11 | untracked file (no commit) |
| D2 | setup | B2a / B3a | `/mydata` on apt190 is root-owned (755), so `/mydata/jingsong-cass-s4` could not be created as the user. | `sudo mkdir` + `chown jason92` of `/mydata/jingsong-cass-s4` only. Environment, not the case file. | 2026-11-11 | n/a |
| D3 | cluster shakedowns | harness | Harness faults found by the shakedowns (no frozen value read): unquoted `FIXED(5)` (bash syntax error); compaction-wait regex expected `pending tasks:` (5.0 prints `pending tasks   0`); the stop routine trusted the pid file, which Cassandra removes before the JVM exits; a stopped JVM held its listening ports a few seconds after `/proc/<pid>/cmdline` emptied. | Fixed in `cluster-run.py` before run 1 (harness README). | 2026-11-11 | n/a |

## 4. Run 1

**Scope:** unit tier (B2) all values as filed: `fcs.mib` 32, 33, 64, 128, 256 and the probe (64, hold 1024). Cluster tier (B3) all settings as filed: disabled, 64, 256, 512 MiB; 4,000,000 rows; 60 s idle, 10 min read, 60 s post per setting; 20-21 read samples per setting. **Command log:** `run1/unit-session.log`, `run1/cluster-session.txt`; raw readings `run1/unit-o05-lines.txt` (joined test output), `run1/unit-junit-status.txt`, `run1/cluster-samples.jsonl`, `run1/cluster-nodetool.txt`, `run1/cluster-stress-results.txt`, `run1/cluster-system-excerpts.txt`; analyzer output `run1/unit-analysis.txt` (50 PASS, 1 FAIL), `run1/cluster-analysis.txt` (27 PASS, 0 FAIL).

### 4.1 Readings

**Unit tier** (single thread, 64 KiB chunks, file `2·N+64` MiB read twice; `run1/unit-o05-lines.txt`, `run1/unit-analysis.txt`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| All 6 JVMs | `Tests run: 1, Failures: 0, Errors: 0`, BUILD SUCCESSFUL; no `o05*.bin` left, no test process left | `run1/unit-junit-status.txt`, `run1/unit-session.log` |
| N=32 (gate) | `O05 instance=null` | `unit-o05-lines.txt` |
| N=33: cacheSize / maxW / final w / entries / poolSize / overflow | 1,048,576 / 1,048,576 / 1,048,576 / 16 / 33,554,432 (32 MiB) / 0 | same |
| N=64 | 33,554,432 / 33,554,432 / 33,554,432 / 512 / 67,108,864 (64 MiB) / 0 | same |
| N=128 | 100,663,296 / 100,663,296 / 100,663,296 / 1536 / 134,217,728 (128 MiB) / 0 | same |
| N=256 | 234,881,024 / 234,881,024 / 234,881,024 / 3584 / 268,435,456 (256 MiB) / 0 | same |
| First pass (positive control) | w rises from 65,536 at chunk 0 in steps of 16 MiB per 256 chunks to the cap, then stays; second pass: w = cap at every sample, every N | `unit-analysis.txt` (pass0/pass1 series) |
| Eviction evidence (AM7) misses / requests / rebuffer calls | 33: 13,476 / 13,476 / 4,160; 64: 8,126 / 8,556 / 6,144; 128: 8,771 / 10,240 / 10,240; 256: 14,883 / 18,432 / 18,432. Loads exceed the final entries 4.2× (256) to 842× (33): every load beyond the final entries was removed | same |
| Probe (64, hold 1024): maxW / final w / entries / poolSize / overflow / held | 33,554,432 / 33,554,432 / 512 / 74,121,216 / 7,012,352 (6.7 MiB) / 1024. Pooled part = 64 MiB (the pool limit); overflow first appears at chunk 1024 (65,536) and grows to 6.7 MiB | `unit-analysis.txt` (probe series) |

**Cluster tier** — one row per setting (steady = read samples from 180 s to the end; `run1/cluster-analysis.txt`, from `run1/cluster-samples.jsonl`)

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| disabled | baseline | ChunkCache MBeans; pool Size; OverflowSize; direct MemoryUsed (steady median); networking Size | absent (NA); 16 MiB at every read sample; 0; 60.16 MiB; 8 MiB | `cluster-analysis.txt` |
| 64 MiB | A | Capacity; Size (every read sample after the first) | 32 MiB; 32 MiB exactly (33,554,432) at all 19 samples; first read sample 0.44 MiB; idle max 0.44 MiB | same; `cluster-nodetool.txt` (`entries 2048, size 32 MiB, capacity 32 MiB`) |
| 64 MiB | A | pool Size / OverflowSize / direct steady median / delta vs baseline / NMT Other delta / RssAnon delta | 64 MiB / 0 / 108.05 MiB / **47.89 MiB** / 47.88 MiB / 59.75 MiB | `cluster-analysis.txt` |
| 64 MiB | A | Requests / Misses during reads | +20,838,747 / +20,674,584 (entries ≤ 2050) | same |
| 256 MiB | B | Capacity; Size | 224 MiB; 224 MiB exactly at all 19 samples after the first | same; `cluster-nodetool.txt` (`entries 14337, size 224 MiB`) |
| 256 MiB | B | pool / overflow / direct / delta / NMT delta / RssAnon delta | 256 MiB / 0 / 300.17 MiB / **240.01 MiB** / 240.01 MiB / 245.58 MiB | `cluster-analysis.txt` |
| 256 MiB | B | Requests / Misses | +20,709,077 / +19,564,968 | same |
| 512 MiB | C | Capacity; Size | 480 MiB; 480 MiB exactly at all 19 samples after the first | same; `cluster-nodetool.txt` (`entries 30720, size 480 MiB`) |
| 512 MiB | C | pool / overflow / direct / delta / NMT delta / RssAnon delta | 512 MiB / 0 / 556.34 MiB / **496.18 MiB** / 496.18 MiB / 498.39 MiB | `cluster-analysis.txt` |
| 512 MiB | C | Requests / Misses | +21,402,281 / +18,886,072 | same |
| all | — | pool limit per start; pool-full refusals | `Global buffer pool limit is 64/256/512 MiB for chunk-cache` at each start; one `Maximum memory usage reached (N MiB) for chunk-cache buffer pool, cannot allocate chunk of 8.000MiB` per enabled setting | `cluster-system-excerpts.txt` |
| all | — | workload | write 4,000,000 rows, 27,868 op/s, 0 errors; reads 10 min each at 33,791-35,596 op/s, 0 errors | `cluster-stress-results.txt` |
| all | — | JVM flags; yaml | `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=4G -XX:NativeMemoryTracking=summary`; `key_cache_size: 0MiB`, `row_cache_size: 0MiB`, `disk_access_mode: mmap_index_only`, `file_cache_enabled`/`file_cache_size` per setting; table LZ4, `chunk_length_in_kb: 16` | `cluster-session.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. The limit was reached and passed: each pass inserted `2·N+64` MiB against `N−32` MiB [observed: `unit-analysis.txt`, w at the cap from chunk `16·(N−32)` on]. The knob took effect: `cacheSize` printed = `(N−32)` MiB for every N [observed: `unit-o05-lines.txt`]. All six JVMs passed and left nothing [observed: `unit-junit-status.txt`, `unit-session.log`].
2. **Readings** — one B2f cell missed: the probe's overflow was 6.7 MiB, not "about ≥ 32 MiB" [observed: `unit-o05-lines.txt`]. Requests exceeded rebuffer calls at N=33 (3.24 per call) and N=64 (1.39) [observed: `unit-analysis.txt` INFO lines]; inferred cause in part 5. Everything else matches B2f exactly (maxW = cap, not cap + one chunk; pool = N MiB rounded down to 8 MiB).
3. **Matched row** — B2g row 1, "`maxW` ≤ cacheSize + 65 536 for every N, and final w within 10 % of cacheSize → Mechanism works as traced; supports the claim": maxW = cacheSize and final w = cacheSize (ratio 1.000) for N = 33, 64, 128, 256 [observed: `unit-o05-lines.txt`]. Also row 4 (gate and positive control): `instance=null` for N=32, and w rises from 0 to its cap for N ≥ 33 [observed: `unit-analysis.txt`]; and row 6 (probe): overflow 7,012,352 > 0 while maxW = 33,554,432 ≤ cap [observed: `unit-o05-lines.txt`]. Disallow evidence: loads exceed the final entries 4.2× to 842× (AM7) [observed].
4. **Excluded rows** — row 2 (Refuted: maxW grows with file size): maxW never exceeded the cap, while each pass weighed 1.6-130× the cap [observed]. Row 3 (final w < 50 % of cap): final w = 100 % of cap [observed]. Row 5 (pool > N MiB with overflow 0): pool ≤ N MiB at every sample with overflow 0 [observed: `unit-analysis.txt`].
5. **Observed vs. inferred** — (a) [inferred: TinyLFU admission plus `ImmediateExecutor`] the requests above rebuffer calls at small N come from `CachingRebufferer.rebuffer`'s retry loop (`ChunkCache.java:240-242`): a freshly loaded entry that Caffeine rejects at admission is evicted on the same thread, `onRemoval` releases it, `reference()` returns null and the chunk is loaded again. (b) [inferred: arithmetic on the probe series] the probe's overflow is small because the 512 entries the cache keeps are a subset of the 1024 held chunks (at chunk 1024 the pool held 64 MiB + 64 KiB, i.e. the held 64 MiB with no room for a separate 32 MiB of cached buffers): the cache did not admit the later chunks over the earlier ones. Real buffer memory still exceeded the operand (70.7 MiB of buffers against a 32 MiB weighted size), which is path A3(a).
6. **Deviations and gaps** — unit attempt 1 extracted readings with a broken grep (D1); the tier was restarted under AM9 and gave the same caps. The probe magnitude cell of B2f missed (part 2); it is not a B2g row and bears on the size of the referenced-buffer overshoot, not on the cap. `ant testsome` heap 1 GiB (AM6).
7. **Core question** — usage followed the constraint: the operand stood exactly at `(N−32)` MiB for each N and the chunk-cache pool at N MiB (parts 1, 3). The constraint caps usage: insertions of up to 130× the cap left the weighted size at the cap, with eviction directly evidenced by loads far above the retained entries (part 3); the only excess is buffers still referenced by readers (probe, part 5b).

**Conclusion (one line):** B2g row 1 (with rows 4 and 6) — **confirmed**.

**Cluster tier**

1. **Validity** — valid. The knob took effect: capacity 32 / 224 / 480 MiB and pool limit 64 / 256 / 512 MiB per setting [observed: `cluster-analysis.txt`, `cluster-system-excerpts.txt`]. The limit was reached in the first 31 s of each read phase and passed many times over: ~20.7-21.4 M requests, ~18.9-20.7 M misses, against ≤ 30,722 entries [observed]. Hold-fixed settings: key/row caches 0, `mmap_index_only`, heap 2G, `MaxDirectMemorySize=4G`, the same 4.24 GB LZ4 16 KiB dataset (5 SSTables, compactions settled) for every setting [observed: `cluster-session.txt`, `cluster-nodetool.txt`]. Stress: 0 errors [observed: `cluster-stress-results.txt`].
2. **Readings** — nothing unusual. Size sat exactly at capacity from the second read sample on; OverflowSize was 0 throughout; the networking pool stayed at 8 MiB in every setting [observed]. Hit rates were low (0.8 % to 12 %; uniform reads over ~260,000 chunks) [observed: `cluster-nodetool.txt`].
3. **Matched row** — B3g row 1, "Chunk Cache size plateaus at about capacity for each N, and the direct-memory delta is about N → Claim confirmed: the cap governs real off-heap use": every steady sample is exactly at capacity (inside the AM8 bands 29-32.5 / 200-224.5 / 430-480.5 MiB), and the direct deltas 47.9 / 240.0 / 496.2 MiB lie within [cacheSize − 16 MiB, N + 16 MiB] and rise with N [observed: `cluster-analysis.txt`]. NMT "Other" deltas equal the direct deltas and RssAnon deltas agree within 12 MiB [observed]. Also row 5 (positive control): Size rose from ≤ 0.52 MiB (idle and first read sample) to capacity within 31 s [observed]. Disallow evidence: Misses (≈ insertions) exceeded the retained entries by about 600× to 10,000× at a Size held at capacity [observed], and the pool refused further 8 MiB macro-chunks once at N [observed: `cluster-system-excerpts.txt`].
4. **Excluded rows** — row 2 (Refuted for the real resource: overflow climbing, delta far beyond N): OverflowSize 0 and delta ≤ N [observed]. Row 3 (Refuted: Size exceeds capacity persistently): no sample above capacity [observed]. Row 4 (delta for 512 ≈ delta for 64): they differ by 448.3 MiB [observed]. Row 6 (Requests flat → not confirmed): Requests grew by ~21 M per setting [observed].
5. **Observed vs. inferred** — [inferred: the baseline subtraction of B3h] the direct delta is the chunk cache's: the baseline already held the 16 MiB of `BufferManagingRebufferer` slabs (AM2) and the 8 MiB networking pool, which were unchanged in the enabled settings; the delta equals pool Size − 16 MiB in each setting (48 / 240 / 496 MiB).
6. **Deviations and gaps** — none in run 1. Pre-run harness fixes (D3) and AM3/AM4/AM5 changed instruments and setup only.
7. **Core question** — usage followed the constraint (part 3: Size = N − 32 MiB, real direct memory rises by ≈ N − 16 MiB, monotone in N) and the constraint caps it (part 3: a 10-minute read of 4.2 GB at ~34,000 op/s left Size and the pool flat at their limits, with eviction evidenced by misses far above entries). The pool's 32 MiB headroom over the cache is fully used: real off-heap use is about `file_cache_size`, not `file_cache_size − 32`.

**Conclusion (one line):** B3g row 1 (with row 5) — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit-o05-lines.txt` (cacheSize per N), `unit-junit-status.txt` (6 × `Failures: 0, Errors: 0`), `unit-session.log` (no `.bin`, no process); `cluster-session.txt` (yaml lines per setting, JVM flags `-Xmx2G`, `MaxDirectMemorySize=4G`, NMT), `cluster-nodetool.txt` (5 SSTables, 4,243,744,092 B, ratio 0.979), `cluster-stress-results.txt` (0 errors, 10:00 each), `cluster-system-excerpts.txt` (pool limits 64/256/512). |
| 2. Readings | yes | The probe overflow 7,012,352 and the INFO request counts re-read in `unit-o05-lines.txt` / `unit-analysis.txt`; cluster OverflowSize 0 and networking 8 MiB re-read in `cluster-samples.jsonl` (per-setting maxima recomputed in a separate script). |
| 3. Matched row | yes | Unit: FINAL lines re-read for each N (maxW = w = cacheSize). Cluster: the cc_size series re-read from `cluster-samples.jsonl` ([0, 32, 32, …], [0, 224, …], [0, 480, …] MiB) and the end-of-phase `nodetool info` lines (`size 32 MiB, capacity 32 MiB`, `224`/`224`, `480`/`480`) agree with JMX; deltas recomputed from the medians in `cluster-analysis.txt`. |
| 4. Excluded rows | yes | Each excluded row's contrary reading re-read (maxima, overflow, delta difference 448.3 MiB, Requests growth). |
| 5. Observed vs. inferred | yes | Unit (a): `ChunkCache.java:240-242` re-read (`do buf = cache.get(...).reference(); while (buf == null)`) and `:153` (`ImmediateExecutor`); the retry is the only path by which requests exceed rebuffer calls in a single-threaded test. Unit (b): probe series re-read (chunk 1024: pool 67,174,400 = 64 MiB + 65,536 overflow). Cluster: pool Size − 16 MiB = direct delta re-checked per setting (64−16 = 48 vs 47.9; 256−16 = 240 vs 240.0; 512−16 = 496 vs 496.2). None of these inferences is needed for the matched rows. |
| 6. Deviations and gaps | yes | D1 restart re-read (`apt190:…/logs/unit-attempt1/` gave the same FINAL values except miss counts). The probe magnitude miss is recorded, not hidden. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1's two bullets: weighted size ≤ cap + slack (unit and cluster: = cap), and off-heap pool use rises with N and stays within about N (unit pool = N; cluster delta ≈ N − 16 MiB, ≤ N + 16 MiB); the disabled baseline, the idle-then-rise control and the misses ≫ entries evidence are the audited controls. |

### 5.2 Run 2?

**No** — 2026-11-11. Both conclusions rest on observed readings that match the frozen rows exactly (the operand at the cap to the byte in every sample, overflow 0); the two inferred statements do not bear on the matched rows; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** **true positive** (positive, caps): both tiers Confirmed — caps.

**Claim tested:** with `file_cache_enabled: true`, the chunk cache's weighted size never exceeds `cacheSize = (file_cache_size − 32) MiB` by more than (concurrent loading/reading threads × chunk size), and the off-heap memory the node uses for the chunk-cache pool rises with `file_cache_size` and stays within about `file_cache_size` (+ the same small slack), however much data is read (B1).

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 "maxW ≤ cacheSize + 65 536 for every N, and final w within 10 % of cacheSize" (with row 4, gate and positive control, and row 6, probe: overflow > 0 while maxW ≤ cap). One B2f probe cell missed (overflow 6.7 MiB, not ≈ ≥ 32 MiB; part 5b). | caps | run 1 + self-check | 2026-11-11 |
| Cluster | **Confirmed** — B3g row 1 "Chunk Cache size plateaus at about capacity for each N, and the direct-memory delta is about N" (with row 5, positive control) | caps | run 1 + self-check | 2026-11-11 |

**Positive control** (required by the coordinator for this case): unit — `instance=null` at N=32 and the first pass raising the weighted size from 0 to the cap at every N ≥ 33; cluster — Size ≤ 0.52 MiB idle, rising to capacity within 31 s of reads in every enabled setting, against a disabled baseline with no chunk cache.

**Notable findings** (for the stage-3 index and HANDOFF; not verdict-bearing):
- Real off-heap use is about `file_cache_size`, not `file_cache_size − 32`: the chunk-cache pool fills to its limit (64 / 256 / 512 MiB, in 8 MiB macro-chunks) while the cache holds 32 MiB less; the 32 MiB "reserved" headroom is used by pool slabs.
- The pool's macro-chunk is 8 MiB (`BufferPool.java:385`; log: "cannot allocate chunk of 8.000MiB"), not the 1 MiB of its comment and of the case file's A3 (AM1).
- With the cache disabled, readers still allocate from the chunk-cache pool (`BufferManagingRebufferer.java:45`): 16 MiB of slabs at baseline (AM2).
- Small caches under a scan re-load chunks: at N=33 the unit test made 3.24 cache requests per rebuffer call (inferred: Caffeine admission rejects the new entry and `ImmediateExecutor` releases it before `reference()`, so `CachingRebufferer` retries). A read-amplification effect, not a bypass of the cap.
- Referenced buffers outlive eviction (A3(a)): holding 1024 chunks kept 70.7 MiB of buffers against a 32 MiB weighted size; the excess over the pool limit went to unpooled overflow (6.7 MiB).

**Feedback filed:** the case file's section D carries the audit amendments AM1-AM9 (2026-11-11) and a stage-4 verdict note (untracked file; the coordinator commits). No other section amended.

**What stays on apt190** (all under `/mydata/jingsong-cass-s4/o05/`, plus `~/.m2`): `src/` (built tree, 469 MB), `harness/`, `harness-classes/` (`O05Jmx.class`), `logs/` (unit, unit-attempt1, cluster-run1, cluster-shake*; 3.3 MB), `node-run1/{conf,logs}` (86 MB; data, commit log, hints and saved caches removed). No process left running (no CassandraDaemon, stress, test or runner process). The directory `/mydata/jingsong-cass-s4` was created with sudo and is owned by jason92. On the local machine: the copy `/mydata/jingsong-cass-s4/o05-src`.
