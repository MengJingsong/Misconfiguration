# compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous — stage-4 results  <!-- file: results/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous.md -->

> **Case:** [`compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous`](../../stage3-ai-deep-read/cases/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — each buffer is exactly the knob; total not bounded** (B2g row 1. ConfigProbe: `1KiB`/`255KiB` refused with the check's message, `0KiB` → 0, `256KiB`/unset → 262,144. With the file cache off, every scanner held one direct buffer of exactly B: 16 × 262,144 and 16 × 4,194,304 at k16, one at k1, and the direct pool moved by exactly 16 × B / B on open and back on close. None at B = 0, at B = chunk length (256 KiB on a 256 KiB-chunk table), with the chunk cache on, or on a point read). **Cluster: Confirmed — each buffer is exactly the knob; total = scanners × B** (B3g row 1. `100KiB` stopped start-up with rc 3. A major compaction of 32 LZ4 SSTables allocated exactly 32 direct buffers of B on one `CompactionExecutor` thread, all live together and all freed at the end; the direct pool rose by 0.1 / 8.1 / 512.1 MiB at B = 0 / 256 KiB / 16 MiB and by 64.1 MiB with 4 SSTables at 16 MiB, and fell back. With the chunk cache on: no read-ahead buffer, but the cache's own pool took 505 MiB). Effect: **caps each buffer (its size is the knob); does not cap the total**. Runbook defects D1 (stress table uncompressed) and D2 (unit arm `16KiB` refused at start-up) fixed before the counted runs. No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/`](../harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. Copied unchanged: `ConfigProbe.java` (from the
> `max_value_size-applySimpleConfig` harness). `unit-run.sh` and `cluster-run.sh` were adapted from the `max_value_size-applySimpleConfig`
> and `counter_cache_size-applySimpleConfig` harnesses (copied, then changed); `CrabJmx.java` is modelled on the `counter_cache_size`
> sampler. No reading from another case is used here.

**What the constraint is (kept apart throughout).** `compressed_read_ahead_buffer_size` (B) is the size of **one** off-heap buffer that a
scan of a compressed SSTable allocates per (thread, data file) when the file is read through the standard (non-mmap, non-chunk-cache)
reader. Two questions are kept apart: **(1) per buffer** — is each buffer exactly B (none when B = 0 or B ≤ chunk length)? **(2) total** —
is the total direct memory of read-ahead buffers bounded by anything? The source has no total: k concurrent scanners hold k × B
(A3 amendment). "Confirmed" below means the file's claim held: (1) yes, and (2) total = scanners × B, not bounded by the knob.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (DD batch 2); before the audit its sha256 `182ee6ef…58e2` was checked equal to the filed `_INDEX.md` §4 row. The step-0 audit made **eighteen amendments** (2026-10-25, before any harness run or reading): frozen at sha256 `ae58d43e…4c56f`. Two runbook fixes followed, each before the affected tier's counted run 1, each a new §2 row: **D1** (B3c, after the cluster shakedown; predictions unchanged) → `9418b903…9577`; **D2** (B2b, B2c, B2f, B2g for one unit arm, after the first unit attempt stopped; audit re-opened for that arm, reason independent of any reading) → final frozen sha256 **`fae97cc2e0b914a244eebd9ee60a50ad6936976cb47bd684e3419d1cc55d0d6c`**. The counted unit run 1 and the cluster run 1 both ran at this version (re-checked before the unit run, and after both tiers). Section D was filled after the hash. Nothing is committed (no commit was asked for); base commit `f60cce1`. |
| **Harness** | [`../harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/`](../harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/):<br>• `ConfigProbe.java` (copied unchanged)<br>• `ReadAheadProbeTest.java`: the B2 mechanism (CQLTester; direct-pool bean and the test thread's read-ahead map read by reflection)<br>• `unit-run.sh`<br>• `readahead.btm`: Byteman rules at the only allocation (`ThreadLocalReadAheadBuffer.getBlock`, after `BufferType.allocate`) and the only free (`clear`, at `FileUtils.clean`)<br>• `CrabJmx.java`: one-connection JMX sampler (direct pool every 250 ms) and setter<br>• `cluster-run.sh`<br>• `selfcheck.py` (independent)<br>**Instrument checks before run 1:** `bash -n`, `ast.parse`, `javac` passed. **Unit shakedown** (arm `1024KiB`, not an arm value; [`shakedown/unit-shakedown-summary.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/shakedown/unit-shakedown-summary.txt)): 16 live buffers of 1,048,576 B, Δopen = Δclose = 16,777,216 exactly, k1 = 1,048,576 — inside every frozen band. After D2 a second unit shakedown (`1024KiB-chunk64`) checked the chunk-length property (chunk 65,536, same Δ). **Cluster shakedown** `sd` (16 MiB, 4 × 20,000 rows; [`shakedown/cluster-shakedown1-summary.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/shakedown/cluster-shakedown1-summary.txt)): Byteman `TestScript: no errors`, `Submit -l` lists both rules, the sampler gave 120 baseline samples; **but the stress table was uncompressed** (`SSTable Compression Ratio: -1.00000`, no buffer for the table) → runbook defect D1 (§3). Shakedown 2 after the fix ([`…/cluster-shakedown2-summary.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/shakedown/cluster-shakedown2-summary.txt)): ratio 0.957, 4 `alloc` lines of 16,777,216 on `CompactionExecutor:3`, 4 `free` lines, Δpeak 64.1 MiB for E = 64 MiB, Δafter 0.07 MiB, baseline spread 0.01 MiB — every frozen band holds with room; no bound was changed. |
| **Tiers and values** | **Unit (B2):** ConfigProbe `0KiB`, `1KiB`, `255KiB`, `256KiB`, unset. Probe arms (16 SSTables, LZ4, chunk 16 KiB unless stated): `0KiB`, `256KiB-chunk256` (B = chunk length = 256 KiB; replaces `16KiB`, D2), `256KiB` (default), `4096KiB`, `ctl-cache` (4096KiB, `file_cache_enabled: true`); cycles k16 and k1 after a warm-up.<br>**Cluster (B3):** one node, 2 GiB heap, `MaxDirectMemorySize=8192M`, Byteman on every running start: `z100` (refusal), `c0`, `c256` (default value), `c16m`, `ctl-cache` (16 MiB + chunk cache), `ctl-k4` (16 MiB, 4 SSTables); each: 32 × 100,000 stress rows (LZ4), one flush per chunk, then a major compaction sampled at 250 ms. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25 (re-opened once for D2, then ready). |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Estimate, A2: off-heap bytes of the read-ahead buffer (`ByteBuffer.allocateDirect`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met (+ amendment) | Unit {0, 16, 256, 4096} KiB and cluster {0, 256 KiB, 16 MiB} include the default 256 KiB. ConfigProbe lacked the default; added (B2b). The `16KiB` arm later proved unrunnable (D2). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | The direct-pool bean is the real resource for `allocateDirect`, but alone it cannot tell the read-ahead buffers from other direct buffers. Added the per-buffer instruments: the test thread's map (B2d) and Byteman at the allocation and free sites (B3d). |
| A. Core question | usage driven to the limit and past it | Met (reinterpreted) | Not a ceiling: the knob sizes each buffer; "past it" means more scanners than one. k = 1 / 16 (unit) and 4 / 32 (cluster) show whether the total follows the scanners. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈ 16 × B ±10%" replaced by exact per-buffer capacities and source-derived bands (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | B2g/B3g had 4 / 3 rows, no Invalid, Not confirmed or "total capped" row, and did not separate per buffer from total. Rows added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (reinterpreted) | Here: each buffer = B (map / trace), none at B = 0 and B ≤ chunk (the "disallow" branch at `CompressedChunkReader.java:237`), start-up refusal of 1–255 KiB. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | **Chunk cache** (control arms; the filed "Δ ≈ 0" cluster expectation is not guaranteed — the cache fills its own direct pool, B3h amendment). **Other direct buffers** (≤ 9 MiB bound derived; B = 0 arm). **Cold pool** (unit warm-up cycle). **System-table scans** (trace by file). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Read paths, access modes and buffer counts stated (A3 amendment). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | "cron-like" flush loop → 32 stress runs with one flush each (B3c); 1 s `nodetool sjk` → 250 ms one-connection sampler (B3d). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local` paths → clone `cassandra-run21`, `$W/probe-crab`, `$W/node-crab`. |
| D. Runnable | workload arithmetic reaches the limit | Met | ≈ 0.95 GB per start, 32 × 16 MiB = 512 MiB peak ≪ `MaxDirectMemorySize` 8192M (corrected from "= heap", A3 amendment); 142 GiB free. Unit: 16 × 4 MiB = 64 MiB ≪ 1 GiB test heap/direct limit. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:533-551, 576-577, 960-961, 2544-2560`; `Config.java:122, 341, 499`; `CompressedChunkReader.java:92-96, 156-254`; `ThreadLocalReadAheadBuffer.java:41-156`; `FileHandle.java:132-157, 329-331, 395-431`; `ChunkCache.java:48-53, 262-265`; `SSTableReader.java:1068-1100, 1383-1386`; `SSTableScanner.java:78`; `SSTableSimpleScanner.java:76`; `AbstractCompactionStrategy.java:256-266`; `CompactionTask.java:200-202`; `SizeTieredCompactionStrategy.java:205-215`; `BufferManagingRebufferer.java:42-55`; `BufferPool.java:128, 206-238, 385, 443-460, 810-826, 906-925`; `ThreadLocalByteBufferHolder.java:69-80`; `LZ4Compressor.java:239-242`; `BufferType.java:24-36`; `FileUtils.java:362-380`; `StorageService.java:1933-1945`; `conf/cassandra-env.sh:57-66, 139-158`; stress `SettingsSchema.java:141-143, 211`. **Two filed statements corrected:** `disk_access_mode: auto` keeps the standard reader (only `mmap` and, on 64-bit, `legacy` bypass); `MaxDirectMemorySize` is a quarter of RAM here, not the heap. |

**Which reads use the buffer, and how many can exist** (the audit's A3 statement; the runs confirm the rows marked ✓):

| Read path | Read-ahead buffer? | Count at once |
|---|---|---|
| Compaction (all strategies), cleanup, streaming receive, offline tools: `getScanner()` → `SSTableSimpleScanner` | yes, in the scanner's constructor ✓ (unit, cluster) | one per (thread, file): a compaction of k SSTables holds k ✓ |
| Partition-range reads: `BigTableScanner`/`BtiTableScanner` (`SSTableScanner`) | yes ✓ (seen in the shakedown trace on `ReadStage-*` and `Native-Transport-Requests-*` threads, for `system_schema` tables) | one per (`ReadStage` thread, SSTable scanned) |
| Point reads (`createReader()` without `forScan`) | no ✓ (unit INFO: 0 bytes, 0 buffers) | — |
| `disk_access_mode: mmap` / `legacy` (64-bit) | no (`CompressedChunkReader.Mmap`) | — (not run) |
| `file_cache_enabled: true` | no ✓ (control arms) | — |
| Uncompressed table | no ✓ (cluster shakedown 1, by accident) | — |
| B = 0 or B ≤ chunk length | no ✓ | — |
| **Total over threads and files** | no counter and no cap anywhere | Σ over threads of distinct files scanned × B |

The JMX setter rejects 0 (and anything < 256) with `IllegalArgumentException: compressed_read_ahead_buffer_size_in_kb must be at least 256KiB`
(`DatabaseDescriptor.java:2554-2557`), while start-up accepts 0 as "disabled" (`:960`): recorded at the cluster tier (§4).

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: read paths, access modes, count per (thread, file), no total cap, setter vs start-up, two corrections, the ≤ 9 MiB bound on other direct buffers | Amendment 2026-10-25 (audit statement) | Brief; group C; bands need a source-derived bound. |
| 2 | B2a: this host; CQLTester probe via `ant testsome`; test yaml line 55 → `false`, restored | Amendment 2026-10-25 | Paths; the unit yaml enables the chunk cache. |
| 3 | B2b: default added to ConfigProbe; probe and control arms listed | Amendment 2026-10-25 | Group A. |
| 4 | B2c: seeded data; warm-up cycle; k16 and k1; point-read INFO | Amendment 2026-10-25 | A cold pool allocates an 8 MiB macro-chunk inside the interval. |
| 5 | B2d: the thread's read-ahead map by reflection; Δopen / Δclose; read-backs incl. reader factory | Amendment 2026-10-25 | Per-buffer evidence; validity. |
| 6 | B2e: order, timeouts | Amendment 2026-10-25 | Exactness. |
| 7 | B2f: exact messages and bands | Amendment 2026-10-25 | Group B; the ±10% band had no source basis. |
| 8 | B2g: verdict rows, per buffer and total separate | Amendment 2026-10-25 | Group B; brief. |
| 9 | B2h: control band ≤ 9 MiB instead of "≈ 0" | Amendment 2026-10-25 | The chunk cache can itself allocate a pool macro-chunk. |
| 10 | B3a: this host; Byteman; `CrabJmx`; `MaxDirectMemorySize` read, not assumed | Amendment 2026-10-25 | Real resource; correction. |
| 11 | B3b: starts and shakedown | Amendment 2026-10-25 | Exactness. |
| 12 | B3c: 32 stress runs with one flush each | Amendment 2026-10-25 | Exact SSTable count. |
| 13 | B3d: 250 ms one-connection sampler; trace; setter INFO; NMT not used | Amendment 2026-10-25 | `jstat` cannot attach; `nodetool sjk` per sample is too slow. |
| 14 | B3e: pre-checks, sequence, drain/stop | Amendment 2026-10-25 | Exactness. |
| 15 | B3f: exact (i)–(vii) with bands | Amendment 2026-10-25 | Group B. |
| 16 | B3g: verdict rows | Amendment 2026-10-25 | Group B. |
| 17 | B3h: chunk-cache control decided by the trace; JMX INFO | Amendment 2026-10-25 | The filed "no 512 MiB peak" is not guaranteed by the source. |
| 18 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 19 | Steps do not say what each establishes; `mmap`/`legacy` bypass, range-read and cross-thread-close paths not run | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit run 1 18:02:53–18:04:51 EDT; cluster run 1 18:05:03–18:33:12 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), 10 cores (Apple T6000, arm64), 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Local clone commit | `$W/cassandra-run21` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`); `ant build-test` succeeded in 51 s; probe test copied in and removed per unit run, test yaml restored (`git status` clean after each unit run) |
| Case-file commit / harness commit | `0dcdfe0` + uncommitted amendments (sha256 above) / uncommitted |
| Storage for node data | internal APFS SSD, `$W/node-crab` (wiped before every start and at the end); 142 GiB free |
| Re-checked at step E | free disk 143 GiB; ports 7000, 7199, 9042, 9091 free; loopback 127.0.0.1–.3 present; no `CassandraDaemon` |
| Full logs | `~/Library/Caches/stage4/logs/compressed_read_ahead_buffer_size-applySimpleConfig/` (`unit-run1/`, `unit-run1.attempt-1/`, `cluster-run1/`, `cluster-shakedown/`, `cluster-shakedown2/`, `unit-shakedown*/`, `selfcheck.out`, `build-test.log`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown (before run 1) | B3c | `cassandra-stress` creates `keyspace1.standard1` uncompressed by default (`SettingsSchema.java:141-143, 211`), so the filed workload never reaches `CompressedChunkReader.Standard`; the shakedown read compression ratio −1 and no read-ahead buffer for the table. Every start would have been Invalid by B3f (iii). | Every stress run adds `-schema 'compression=LZ4Compressor'`. B3f, B3g, B3h unchanged. | Fixed in the case file, 2026-10-25; cluster tier not yet run | `9418b903…9577` |
| D2 | unit run 1, first attempt | B2b (arm `16KiB`) | 16 KiB is inside the range the start-up check refuses (`DatabaseDescriptor.java:960`): the arm's JVM stopped with `compressed_read_ahead_buffer_size must be at least 256KiB (set to 0 to disable), but was 16KiB` ([`run1/unit/attempt1-16KiB-refusal.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/unit/attempt1-16KiB-refusal.txt)). | The arm's purpose (B = chunk length → no buffer) kept with a valid value: `256KiB-chunk256` (B = 256 KiB, `chunk_length_in_kb: 256`). This changes that arm's read-back and E (B2f), so the audit was re-opened for it: E includes 16 × 256 KiB of rebufferer buffers that `BufferPool` allocates directly for chunks > 128 KiB (derived from the source, not from a reading). Unit tier restarted from its beginning. | Audit re-opened and fixed, 2026-10-25 | `fae97cc2…d6c` |

**Kept, not used:** the first unit attempt (`unit-run1.attempt-1/`) ran `0KiB`, `256KiB`, `4096KiB`, `ctl-cache` at version `9418b903…`; its
readings equal the counted run's to the byte but are not part of the verdict. Its `16KiB` refusal is quoted only as INFO (an extra value
that B1(a) also covers). No prediction of an arm that had a reading was changed.

## 4. Run 1

**Scope:** both tiers, every value and start of B2b and B3b (as amended). **Command logs:** `unit-run1/commands.log`, `cluster-run1/commands.log`.
Excerpts in [`compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/):
`unit/summary.txt`, `unit/stage4.out`, `unit/p1-*.lines.txt`; `cluster/summary.txt`, `cluster/<start>-readahead-own.trace` (the table's lines; c256, c16m, ctl-k4 only — at c0 and ctl-cache no rule fired and no trace file exists),
`cluster/<start>-jmx.csv`, `cluster/refusal-z100.txt`; `selfcheck.out`.

### 4.1 Readings

**Unit tier** ([`unit/summary.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/unit/summary.txt), [`unit/stage4.out`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/unit/stage4.out))

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `0KiB` / `256KiB` / unset | `OK getCompressedReadAheadBufferSize=0` / `=262144` / `=262144` | `unit/p1-*.lines.txt` |
| ConfigProbe `1KiB` / `255KiB` | `REJECT ConfigurationException: compressed_read_ahead_buffer_size must be at least 256KiB (set to 0 to disable), but was 1KiB` / `… 255KiB` | `unit/p1-*.lines.txt` |
| Read-backs, every arm | B as set; `diskAccessMode=standard`; 16 SSTables; chunk 16,384 (262,144 in `256KiB-chunk256`); factory `CompressedChunkReader$Standard=16`, file cache `false` (control: `ChunkCache$CachingRebufferer=16`, `true`); 32,000 rows, ≈ 132.5 MB on disk | `unit/stage4.out` |
| `256KiB`, k16 / k1 | open: 16 / 1 live buffers, all keys data files of the table, `caps=[262144x16]` / `[262144x1]`, all direct; closed: 0. Δopen = Δclose = 4,194,304 / 262,144 (exactly 16 × B / B) | `unit/stage4.out` |
| `4096KiB`, k16 / k1 | 16 / 1 live buffers of 4,194,304, direct; closed 0. Δopen = Δclose = 67,108,864 / 4,194,304 | `unit/stage4.out` |
| `0KiB`, k16 / k1 | 0 live buffers; Δopen = Δclose = 0 | `unit/stage4.out` |
| `256KiB-chunk256` (B = chunk), k16 / k1 | 0 live read-ahead buffers; Δopen = Δclose = 4,194,304 / 262,144 = k × 256 KiB rebufferer buffers (predicted, D2); a read-ahead buffer would have doubled it | `unit/stage4.out` |
| `ctl-cache` (4 MiB, chunk cache), k16 / k1 | 0 live buffers; Δopen = Δclose = 0 | `unit/stage4.out` |
| INFO point read (`k = 5`) | 1 row, 0 bytes of direct memory, 0 buffers, in every arm | `unit/stage4.out` |
| INFO first attempt, `16KiB` | start-up refused with the check's message | `unit/attempt1-16KiB-refusal.txt` |

**Cluster tier** (one node, 127.0.0.1, `-Xmx2G -XX:MaxDirectMemorySize=8192M`, Byteman on every running start; compaction ≈ 15 s for
32 SSTables, 2–3 s for 4; [`cluster/summary.txt`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/cluster/summary.txt))

| Capacity value | Start | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| `100KiB` | z100 | exit, output | rc 3 after 2 s, no `Startup complete`; `Exception encountered during startup: compressed_read_ahead_buffer_size must be at least 256KiB (set to 0 to disable), but was 100KiB` | `summary.txt`, `refusal-z100.txt` |
| all | every start | read-backs | config `compressed_read_ahead_buffer_size` = `0KiB` / `256KiB` / `16MiB` / `16MiB` / `16MiB`; JMX `CompressedReadAheadBufferInKB` = 0 / 256 / 16384 / 16384 / 16384; `file_cache_enabled=false` (ctl-cache `true`); `DiskAccessMode is standard, indexAccessMode is mmap`; `-XX:MaxDirectMemorySize=8192M`; Byteman agent on the command line | `summary.txt` |
| all | every start | workload | 32 × 100,000 rows (ctl-k4: 4 ×), 0 errors; before compaction 32 SSTables (ctl-k4: 4), compression ratio 0.957–0.959; ≈ 951 MB live; after: 1 SSTable, `nodetool compact` rc 0 | `summary.txt` |
| `0KiB` | c0 | trace / JMX | no read-ahead allocation of any file (no trace line); Δpeak 0.11 MiB, Δafter −0.04 MiB (baseline 48.65 MiB, 120 samples, spread 0) | `c0-jmx.csv`, `selfcheck.out` |
| `0KiB` | c0 | INFO setter | `SET 0 REJECTED … IllegalArgumentException: compressed_read_ahead_buffer_size_in_kb must be at least 256KiB`, read-back stays 0; `SET 255` the same — the setter refuses the value start-up accepted | `summary.txt` |
| `256KiB` | c256 | trace | 32 `alloc` lines for 32 distinct `keyspace1/standard1` `Data.db` files, each `knob=262144 cap=262144 direct=true`, all on `CompactionExecutor:3`, inside the compaction window; 32 `free` lines on the same thread; 32 live together | `c256-readahead-own.trace` |
| `256KiB` | c256 | JMX | Δpeak 8.11 MiB; minus Δpeak(c0): 8,388,610 B vs E = 8,388,608 (INFO: band as wide as E); Δafter −0.04 MiB; 59 samples inside the buffers' life | `c256-jmx.csv`, `selfcheck.out` |
| `16MiB` | c16m | trace | 32 `alloc` lines, each `cap=16777216 direct=true`, on `CompactionExecutor:4`; 32 `free` lines; 32 live together | `c16m-readahead-own.trace` |
| `16MiB` | c16m | JMX | Δpeak 512.11 MiB; minus Δpeak(c0): 536,870,903 B vs E = 536,870,912 (diff −9 B; band ±9 MiB); Δafter −0.04 MiB; 57 samples inside | `c16m-jmx.csv`, `selfcheck.out` |
| `16MiB` + chunk cache | ctl-cache | trace / JMX | no read-ahead allocation of any file (no trace line); INFO: Δpeak 505.1 MiB and Δafter 504.9 MiB — the chunk cache's own direct pool, retained | `ctl-cache-jmx.csv`, `selfcheck.out` |
| `16MiB`, 4 SSTables | ctl-k4 | trace / JMX | 4 `alloc` lines of 16,777,216 on `CompactionExecutor:3`, 4 `free`; Δpeak 64.10 MiB, minus Δpeak(c0) 67,097,147 B vs E = 67,108,864 (diff −11,717 B); Δafter 0.07 MiB; 6 samples inside | `ctl-k4-readahead-own.trace`, `ctl-k4-jmx.csv` |
| `256KiB`, `16MiB` | c256, c16m, ctl-k4 | INFO other files | 495 / 492 / 156 read-ahead allocations of `system_schema` and `system.local` files on `ReadStage-*`, `Native-Transport-Requests-*`, `main` and `CompactionExecutor` threads — the stress driver's schema range reads and start-up — each of size B, all freed, none live at the compaction peak | full traces, `selfcheck.out` |

### 4.2 Conclusion and logic

1. **Validity.** Valid.
   - Unit: every arm read back B as set, `diskAccessMode=standard`, 16 SSTables, the expected chunk length, and the expected reader factory on all 16 files (`Standard` with the cache off, `CachingRebufferer` with it on), so the traced path was the one exercised [observed: `unit/stage4.out` readback lines]. Each scanner yielded one partition (`partitions=16` / `1`) [observed: same]. The test yaml was restored after every run [observed: `unit-run1/commands.log`, `clone status 0 entries`].
   - Cluster: every read-back equals the value set, the table was compressed (ratio 0.957–0.959), k = 32 (ctl-k4: 4) before compaction, compaction finished (1 SSTable) [observed: `cluster/summary.txt`]. The sampler took 120 baseline samples with zero spread and ≥ 6 samples inside every buffer lifetime [observed: `*-jmx.csv`, `selfcheck.out`]. Held fixed at every start: heap, `num_tokens: 1`, defaults for `disk_access_mode` and `compaction_throughput` [observed: `cluster-run1/summary.txt` YAML lines; config lines].
2. **Readings.** Nothing unusual for the verdict. Two INFO observations: (a) the stress driver's schema queries made range reads of `system_schema` tables allocate a read-ahead buffer of the full B per file (16 MiB per tiny file at c16m) on `ReadStage` and `Native-Transport-Requests` threads [observed: full traces]; (b) with the chunk cache on, the node's direct memory rose by 505 MiB during the same compaction and stayed there [observed: `ctl-cache-jmx.csv`] — the amended B3h had made this JMX reading INFO because the filed "no 512 MiB peak" was not guaranteed by the source.
3. **Matched row.**
   - Unit — B2g "**Confirmed**: the five ConfigProbe lines as in B2f and (i)–(iv) hold in every arm":
     - ConfigProbe 5/5 exact [observed: `unit/p1-*.lines.txt`].
     - (ii) per buffer: `256KiB` and `4096KiB` showed `live=16 own=16 caps=[Bx16] direct=all` at k16 and `[Bx1]` at k1; `0KiB`, `256KiB-chunk256` and `ctl-cache` showed 0 buffers; every closed reading 0 [observed: `unit/stage4.out`].
     - (iii) real resource: Δclose = Δopen = E exactly in all ten cycles (4,194,304; 262,144; 67,108,864; 4,194,304; 0; 0; 4,194,304 and 262,144 for the 256 KiB-chunk arm, which are its rebufferer buffers; 0; 0) [observed: same].
     - (iv) total: Δclose(k16) = 16 × Δclose(k1) in both sized arms [observed: same].
   - Cluster — B3g "**Confirmed**: (i)–(vi) hold and the B3h controls hold":
     - (i) z100 rc 3 with the message [observed: `summary.txt`, `refusal-z100.txt`]. (ii) read-backs [observed: `summary.txt`]. (iii) k and ratio [observed: same].
     - (iv) per buffer: c256 and c16m each 32 allocations of exactly B, direct, on one `CompactionExecutor` thread, 32 frees on it, 32 live together; c0 and ctl-cache none [observed: `c*-readahead-own.trace`; absence of any trace file at c0 / ctl-cache].
     - (v) real resource: c16m 512.0 MiB vs E = 512 MiB (diff −9 B); ctl-k4 64.0 MiB vs 64 MiB (diff −11.4 KiB); c0 0.11 MiB ≤ 9 MiB; Δafter ≤ 0.07 MiB at c0, c256, c16m, ctl-k4; c256 8.0 MiB (INFO, = E) [observed: `*-jmx.csv`, `selfcheck.out`].
     - (vi) compaction rc 0 and 1 SSTable after, every start [observed: `summary.txt`].
     - B3h: ctl-cache no read-ahead allocation; ctl-k4 4 × 16 MiB and 64 MiB [observed: as above].
4. **Excluded rows.**
   - Unit **Refuted (sizing)**: every live buffer had capacity B; 16 buffers at k16 (not 1); Δclose differs 16 × (4 MiB − 256 KiB) between the two sized arms; no buffer at B = 0 or B = chunk length [observed: `unit/stage4.out`].
   - Unit **Refuted (start-up)**: 1 and 255 KiB refused, 0, 256 KiB and unset accepted [observed: `unit/p1-*.lines.txt`].
   - Unit **Refuted (total)**: Δclose(k16) = 16 × B, not ≈ B [observed: same].
   - Unit **Not confirmed**: every Δ inside its band (all exactly E) [observed: same]. **Leak**: 0 live buffers and Δ back to before after every close [observed: same]. **Invalid**: part 1.
   - Cluster **Refuted (sizing)**: caps = B, counts = k, nothing at c0, c16m JMX at 512 MiB (not the c256 value) [observed: traces, `selfcheck.out`]. **Refuted (start-up)**: z100 did not start. **Refuted (scaling)**: ctl-k4 showed 4 buffers and 64 MiB [observed: `ctl-k4-*`].
   - Cluster **Not confirmed**: both decisive bands hold, ≥ 6 samples per window. **Leak**: frees = allocs, Δafter ≤ 0.07 MiB. **Invalid**: part 1.
5. **Observed vs. inferred.**
   - (a) "No read-ahead buffer at c0 and ctl-cache" rests on the absence of any trace line; Byteman writes its file only when a rule fires [inferred: the agent was on both command lines (`byteman_agent=1`), the same rules fired in c256, c16m, ctl-k4 and both shakedowns (`Submit -l` listed them), and the result agrees with the unit tier's direct map readout for B = 0 and the chunk cache, and with c0's 0.11 MiB JMX peak]. It decides the c0 / ctl-cache clause of (iv).
   - (b) The 505 MiB in ctl-cache is the chunk cache's buffer pool [inferred: A3 amendment, `file_cache_size` = 512 MiB at a 2 GiB heap, retained after compaction]. INFO only.
   - (c) That compaction scans open all k scanners before reading [observed in the trace: all 32 allocations precede all 32 frees, max live 32].
6. **Deviations and gaps.**
   - D1 and D2 (§3) were fixed before the counted runs; the first unit attempt is kept and not used.
   - Not exercised: `disk_access_mode: mmap` / `legacy` bypass, concurrent compactions, range reads as the measured workload (seen only as INFO), and a scanner closed on another thread than it was opened on (A3 amendment: its buffer would not be freed).
   - The self-check reads the refusal and `nodetool compact` exit codes, the compaction client window and the JMX get/set output from `commands.log`, the runner's record; no other file holds them.
7. **Core question.**
   - Each read-ahead buffer is exactly the knob: B bytes of direct memory per scanner of a compressed SSTable (unit part 3 (ii); cluster (iv)), none when B = 0 or B ≤ chunk length, and values 1–255 KiB cannot be configured at start-up (parts 3, 4).
   - The total is not bounded: it is scanners × B — 16 × B vs 1 × B in one thread (unit (iv)), 32 × B vs 4 × B in one compaction (cluster (v)), 512 MiB at 16 MiB — and nothing sums or limits it (A3 amendment).
   - **`compressed_read_ahead_buffer_size` caps the size of each read-ahead buffer exactly; it does not cap the total off-heap memory of read-ahead buffers, which grows with the number of SSTables scanned at once (and threads scanning).**

**Conclusion (one line):** Unit B2g row 1 and cluster B3g row 1 — **Confirmed** (each buffer = B; total = scanners × B, not bounded by the knob).

## 5. Self-check of run 1 — AI

Independent script [`harness/.../selfcheck.py`](../harness/compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/selfcheck.py). It was written before the counted run-1 readings were read (amended for D2 before the
unit tier restarted). It re-parses the raw files and never reads `summary.txt`:
- unit: `p1-<v>.out`, `stage4.out` (the probe's own lines);
- cluster, per start: `readahead.trace`, `jmx.csv`, `system.log`, `node.out`, `tablestats-before/after.txt`; `commands.log` only for the exit codes, the compaction window and the JMX get/set output.

It re-derives every B2f and B3f clause. **Result: 93 of 93 checks hold** ([`run1/selfcheck.out`](compressed_read_ahead_buffer_size-applySimpleConfig-compressed_read_ahead_buffer_size--autonomous/run1/selfcheck.out)). INFO lines: point reads 0 bytes in every arm; other-file allocations (system tables) 0 / 495 / 492 / 0 / 156; c256 band 8.0 MiB = E; ctl-cache 505 MiB (chunk cache); both setter calls rejected.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: readback ×5 unit, ×5 cluster; `sstables`, `compaction`, `samples_in_window` lines. `byteman_agent=1` and the YAML lines re-read in `cluster-run1/commands.log`. |
| 2. Readings | yes | The system-table allocations were re-read in the full `c256/readahead.trace` (thread names `ReadStage-*`, `Native-Transport-Requests-*`, `main`, `CompactionExecutor:*`; files `system_schema/*`, `system/local`); `ctl-cache-jmx.csv` re-read (Δ stays ≈ 505 MiB to the end). |
| 3. Matched row | yes | Each clause is a self-check line (per buffer, `d_close`, `d_open`, `total_k16_vs_k1`, `per_buffer`, `jmx_band`, `released`). |
| 4. Excluded rows | yes | The excluding readings are the same lines plus `unit.knob_changes_total` and `cluster.z100.refused`. |
| 5. Observed vs. inferred | yes | (a) re-checked: no `readahead.trace` exists in `cluster-run1/c0/` or `ctl-cache/`, while `byteman_agent=1` is in both READBACK lines; the unit `0KiB` and `ctl-cache` map readouts are 0. (b) INFO. (c) re-read in `c16m-readahead-own.trace` (last alloc 1792967050…, first free 1792967064…). |
| 6. Deviations and gaps | yes | `unit-run1.attempt-1/` holds the first attempt (16KiB refusal in `ant-16KiB.log`); `cluster-shakedown/sd/tablestats-before.txt` shows ratio −1.00000. |
| 7. Core question | yes | Per buffer (unit map, cluster trace) → total (k16 vs k1, 32 vs 4, JMX) → no aggregate limit in the source, each with its part. |

### 5.2 Run 2?

**No** — 2026-10-25. The conclusion rests on observed readings; the one inference that decides a clause (5 a) is supported by three independent
observations. Every reading equals its prediction to the byte or within kilobytes, the self-check settles every part, and the result neither
refutes the case nor confirms a new bypass (the chunk-cache and B ≤ chunk bypasses are the file's own A3 statements).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped: sizes, per scanner).

**Claim tested (B1):**
- (a) Values 1–255 KiB stop start-up; 0 and ≥ 256 KiB are accepted.
- (b) With size B (> chunk length) and k SSTables scanned concurrently by one thread, the direct memory attributable to read-ahead is ≈ k × B while the scans are open and returns to baseline when they close; with B = 0 or B ≤ chunk length it is ≈ 0.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row 1. ConfigProbe 5/5. Each scanner held one direct buffer of exactly B (262,144 / 4,194,304), 16 at k16 and 1 at k1; the direct pool moved by exactly 16 × B / B and returned on close; none at B = 0, B = chunk length, or with the chunk cache | **per buffer: caps** (size = B exactly) · **total: does not cap** (= scanners × B) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row 1. `100KiB` refused at start-up (rc 3). A major compaction of 32 SSTables held exactly 32 buffers of B at once on one thread (0 / 8 MiB / 512 MiB of direct memory at B = 0 / 256 KiB / 16 MiB; 64 MiB with 4 SSTables), all freed at its end; no buffer with the chunk cache on. JMX setter rejects 0 (INFO) | **per buffer: caps** · **total: does not cap** (512 MiB from one compaction at 16 MiB, unbounded in the number of SSTables and threads) | run 1 + self-check | 2026-10-25 |

**What each outcome means here.**
- "Each buffer is exactly the knob": the knob is a per-scanner size, honoured to the byte; 0 (or a value ≤ the table's chunk length) turns the buffer off.
- "Total usage is bounded": **no.** There is no counter or limit over buffers; the total is (threads scanning) × (distinct SSTables each scans) × B. One compaction over many SSTables, many range reads in parallel, or a large B multiply it (one range read of a tiny system table at 16 MiB allocated 16 MiB per file).
- The setter (`setCompressedReadAheadBufferInKB`, JMX) rejects 0 although start-up accepts 0, so the buffer can be disabled only by restart.

**Feedback filed:**
- The case file's section D was filled (uncommitted). Amendments: the audit's eighteen, D1 (B3c) and D2 (B2b, B2c, B2f, B2g), all before the counted runs; nothing amended after a counted reading.
- Index rows: `_INDEX.md` §1 (Stage 4), §2 (three new hash rows: audit freeze, D1, D2), §3 (coverage line).
- For stage 3: (1) `cassandra-stress` tables are uncompressed unless `-schema compression=…` is given — check the table's compression when a case depends on it; (2) a knob value used to show a disabled branch must itself pass the start-up check (16 KiB did not); (3) the filed `disk_access_mode: auto` bypass is wrong at 5.0.9 (`auto` → `standard`); (4) `MaxDirectMemorySize` from `bin/cassandra` is a quarter of RAM (here 8 GiB), not the heap; (5) a chunk-cache control cannot be expected to keep direct memory flat — the cache fills its own pool (505 MiB here).

**Processes:** after the cluster tier, `final CassandraDaemon processes: none` and `node-crab` was wiped (`run1/cluster/summary.txt`).
Re-checked at the end of the session: `ps -eo command | grep '[C]assandraDaemon'` empty; no stress, probe or sampler JVM; ports 7000/7199/9042/9091/7012 free; `$W/node-crab` and `$W/probe-crab` removed; the run clone clean (`git status` 0 entries: test yaml restored, probe test removed); the repository root has no `build/` or log folder.
