# compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous — stage-4 results  <!-- file: results/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md -->

> **Case:** [`compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous`](../../stage3-ai-deep-read/cases/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — floor enforced; each buffer = the value set, on readers built after the set; total not bounded** (B2g row Confirmed. 0/128/255 refused with the check's message and 2097152 by the byte-conversion check, getter unchanged; fresh readers captured v and every scanner held one direct buffer of exactly v for v = 256 KiB–16 MiB, direct memory moved by T × v (+16,287 B holder per thread) and back on close; the reader opened before `set 16384` kept 262,144-byte buffers; none when v ≤ chunk length; three identical repetitions). **Cluster: Confirmed — same; total = scanners × v** (B3g row Confirmed. JMX `set 255`/`set 0` refused, attribute stays 256; a 16-SSTable compaction after each set held exactly 16 buffers of the value set: peaks 4.1 / 64.1 / 256.1 MiB at 256 KiB / 4 MiB / 16 MiB, all freed; SSTables written before `set 16384` compacted with 256 KiB buffers (4.1 MiB); no buffer with the chunk cache on). Effect: **caps each buffer of readers opened after the change; does not cap the total**. No runbook defect. Self-check 246/246. No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/`](../harness/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. Copied unchanged: `readahead.btm` (from the
> `compressed_read_ahead_buffer_size-applySimpleConfig` harness) and `Jmx.java` (the file's own B3b client, extracted verbatim).
> `unit-run.sh` and `cluster-run.sh` were adapted from the `compressed_read_ahead_buffer_size-applySimpleConfig` harness (copied, then
> changed). No reading from another case is used here.

**What is tested (kept apart throughout).** `setCompressedReadAheadBufferInKB` (JMX, `StorageService.java:1941-1945` →
`DatabaseDescriptor.java:2554-2560`) changes `compressed_read_ahead_buffer_size` (B) at runtime. Three questions: **(1) the floor** —
are values < 256 KiB (including 0) rejected and the setting kept? **(2) pick-up** — does a reader built after the change allocate
buffers of the new B, and does a reader built before it keep the old B (the size is captured once, in the `CompressedChunkReader.Standard`
constructor)? **(3) usage** — does direct memory follow k × B while k scans are open and return when they close? B sizes each
buffer; nothing bounds the total (k scanners × B).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `e985003` (DD batch 4); before the audit its sha256 `05c04901…bcbffc` was checked equal to the filed `_INDEX.md` §4 row. The step-0 audit made **eighteen amendments** (2026-10-25, before any harness run or reading): frozen at sha256 **`a037495a70381051c23614ac1e9b8e54fad05644ce8c12f91a422d594a699244`** (new §2 row). No runbook defect arose; both tiers' run 1 ran at this version (re-checked before the unit run and after both tiers). Section D was filled after the run. Nothing is committed (no commit was asked for); base commit `e985003`. |
| **Harness** | [`../harness/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/`](../harness/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/):<br>• `ReadAheadSetterTest.java`: the filed B2e skeleton plus the audit's additions (per-worker read-ahead map, chunk-cache pool size, captured size per reader, stale-reader cycle, gate control)<br>• `unit-run.sh`<br>• `readahead.btm` (copied unchanged): Byteman at the only allocation and the only free of a read-ahead buffer<br>• `Jmx.java`: the case file's own client (set, 100 ms poll)<br>• `cluster-run.sh`<br>• `selfcheck.py` (independent)<br>**Instrument checks before run 1:** `bash -n` both scripts; `javac` of `Jmx.java` and of the test against the clone's classes; `python3 -I selfcheck.py` dry run on the shakedown logs (parses, no crash). **Unit shakedown** (`-Dstage4.shakedown=true`, value 2048 KiB — not an arm value; no rejection, stale or gate part; [`shakedown/unit-shakedown-summary.txt`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/shakedown/unit-shakedown-summary.txt)): captured 2,097,152; T = 1 / 8 workers each held one direct buffer of 2,097,152; openDelta − T × B = 16,286 / 130,288 (= T × 16,286, the compressed-chunk holder, inside the frozen ±T × 40 KiB); pool change 0. **Cluster shakedown** `sd` (one start, `set 2048`, 4 × 20,000 rows; [`shakedown/cluster-shakedown-summary.txt`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/shakedown/cluster-shakedown-summary.txt)): Byteman `TestScript: no errors`, `Submit -l` lists both rules, `MaxDirectMemorySize=8192M`, `DiskAccessMode is standard`, ratio 0.918 (compressed), 4 `alloc` of 2,097,152 on `CompactionExecutor:1` and 4 `free`, peak 8.10 MiB for 4 × 2 MiB, after −0.08 MiB, 43 baseline samples with spread 0, ≈ 110 ms per poll. Every frozen band holds with room; no bound was changed. |
| **Tiers and values** | **Unit (B2):** rejections 0, 128, 255, 2097152; 2097151 (getter only); v = 256, 1024, 4096, 16384 KiB on a fresh reader each, T = 1 and 8; stale reader (live reader from the flush at 256 KiB, knob 16384, T = 8); gate control (chunk 1024 KiB, v = 512, T = 8); three repetitions.<br>**Cluster (B3):** one node (`n1`, yaml 256KiB, 2 GiB heap): `set 255`, `set 0`; arms `v256`, `v4096`, `v16384`, `v4096b` (repeat), `stale` (written at 256, then `set 16384`, then compacted); a second start `cc` (`file_cache_enabled: true`, `set 16384`). Each arm: fresh keyspace, 16 × 100,000 stress rows (LZ4), one flush each, compaction at 16 MiB/s polled every 100 ms. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Estimate, A2: off-heap bytes of each read-ahead buffer (`allocateDirect`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | Unit 256/1024/4096/16384 KiB, cluster 256/4096/16384 KiB, both incl. the default 256 KiB. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | The direct-pool bean is the real resource but cannot tell read-ahead buffers from the chunk-cache `BufferPool`'s macro-chunks or overflow buffers. Added: pool-size correction and per-worker map readout (B2d), Byteman per-buffer trace (B3d). |
| A. Core question | usage driven to the limit and past it | Met (reinterpreted) | Not a ceiling: B sizes each buffer; "past it" = more scanners (T = 1 / 8; 16 SSTables per compaction). |
| B. Logic | each step says what it establishes | Partly | Steps listed; meaning carried by B2g/B3g. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Met (+ amendment) | Filed bands kept; their observables made exact (corrected deltas, peak definition). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | No Not confirmed / Invalid rows and no row for "a reader opened before the change sees the new value". Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Rejection lines with the check's message and unchanged getter (the disallow branch of line 2556); per-buffer sizes = v. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | "Size read at scan time" vs "at reader construction" was not separable with fresh readers only → **stale-reader control** added at both tiers (B2h, B3h). BufferPool macro-chunk / overflow → pool correction (unit). System-table range reads → trace by file (cluster). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | The test yaml statement was wrong (`file_cache_enabled: true` at line 55: the filed unit tier would have seen no buffer at all); stress uncompressed by default; `disableautocompaction` before the keyspace exists does nothing for it. Corrected (A3 (a)–(c), B2a, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | 2097151 was in B2b but not in the skeleton; barrier timeouts, worker join, gc before each cycle; peak/baseline/after windows defined (B2e, B3d, B3f). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local` paths → `$W/cassandra-run23`, `$W/node-crs`; `-p pidfile` → tracked background process. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit 8 × 16 MiB = 128 MiB ≪ 1 GiB test direct limit. Cluster ≈ 360 MB per arm, 16 × 16 MiB = 256 MiB peak ≪ `MaxDirectMemorySize` 8192M (correction (d): not 2 GiB); 138 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:960-961, 2544-2560, 4581-4598`; `StorageService.java:1935-1945`; `StorageServiceMBean.java:814-815`; `CompressedChunkReader.java:156-254`; `ThreadLocalReadAheadBuffer.java:30-157`; `FileHandle.java:95-157, 197-208, 395-431`; `SSTableReader.java:359-372, 640-644, 1068-1100, 1383-1386`; `BigTableReader.java:501-557`; `ThreadLocalByteBufferHolder.java:30-81`; `BufferManagingRebufferer.java:42-55`; `BufferPool.java:128, 206-290, 385, 460, 810-826, 894-925`; `test/conf/cassandra.yaml:28, 55`; `build.xml:1153`; `conf/cassandra-env.sh:93, 158`; stress `SettingsSchema.java:140-143, 211`; `DisableAutoCompaction.java`, `NodeTool.java:471-495`. **Four filed statements corrected** (A3 amendment (a)–(d)). |

**When a reader picks up the size** (the audit's A3 statement; the runs confirm the rows marked ✓):

| Reader | Size it uses for scans |
|---|---|
| Built after `setCompressedReadAheadBufferInKB(v)` — a fresh `SSTableReader.open`, a flush or compaction output, a streamed or imported SSTable | v (read once in the `Standard` constructor, `CompressedChunkReader.java:236`) ✓ (unit fresh readers; cluster arms) |
| Built before the change (live SSTables, and every clone of them: `sharedCopy()` keeps the factory) | the size at its construction, for its whole life ✓ (unit stale cycle; cluster `stale` arm) |
| Built when the size was ≤ chunk length | none, ever ✓ (unit gate control) |
| Rejected value (< 256 KiB, or > 2,097,151 KiB) | nothing changes; getter unchanged ✓ |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | A3: when a reader picks up the size, what an older reader keeps, setter messages, other direct consumers with derived bounds, four corrections | Amendment 2026-10-25 | Group C; the caller's question; bands need a source basis. |
| 2 | B2a: this host; test yaml line 55 → `false`, restored | Amendment 2026-10-25 | Correction (a): otherwise no buffer at all. |
| 3 | B2b: 2097151 into the procedure; stale-reader control | Amendment 2026-10-25 | Exactness; group B. |
| 4 | B2c: exact workload incl. the gate table | Amendment 2026-10-25 | Exactness. |
| 5 | B2d: pool-size correction, per-worker map, captured size, read-backs | Amendment 2026-10-25 | Real resource vs pool; per-buffer evidence. |
| 6 | B2e: order, gc, barrier timeouts, join, three repetitions | Amendment 2026-10-25 | Exactness; a failed worker must not hang. |
| 7 | B2f: exact messages; filed bands on the corrected deltas | Amendment 2026-10-25 | Group B. |
| 8 | B2g: rows Refuted (pick-up), Not confirmed, Invalid | Amendment 2026-10-25 | Group B. |
| 9 | B2h: stale control | Amendment 2026-10-25 | Separates construction-time from scan-time pick-up. |
| 10 | B3a: this host; Byteman; filed `Jmx.java` | Amendment 2026-10-25 | Per-buffer evidence. |
| 11 | B3b: stale arm; ctl-cache (filed optional control) run | Amendment 2026-10-25 | Group B. |
| 12 | B3c: `compression=LZ4Compressor`; `disableautocompaction ra_<v>` after the first stress run | Amendment 2026-10-25 | Corrections (b), (c): otherwise uncompressed, and compacted at 4 SSTables. |
| 13 | B3d: compaction window; trace; tablestats; setter evidence (no server log for a rejection) | Amendment 2026-10-25 | Exactness; the filed system.log observable does not exist. |
| 14 | B3e: pre-checks, sequence, stop | Amendment 2026-10-25 | Exactness. |
| 15 | B3f: exact forms, peak definition, stale bands | Amendment 2026-10-25 | Group B. |
| 16 | B3g: rows added | Amendment 2026-10-25 | Group B. |
| 17 | B3h: ctl-cache JMX INFO only | Amendment 2026-10-25 | The filed "difference should vanish" is not guaranteed (the cache fills its own pool). |
| 18 | B4: this host's cleanup | Amendment 2026-10-25 | `/local` paths. |
| 19 | Steps do not say what each establishes; `mmap`/`legacy` bypass, range reads, an old and a new reader of one file on one thread (shared block) not run | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit run 1 23:02:32–23:04:06 EDT; cluster run 1 23:04:13–23:34:03 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), 10 cores (Apple T6000, arm64), 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Local clone commit | `$W/cassandra-run23` at `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`); `ant build-test` succeeded in 51 s; test copied in and removed per unit run, test yaml restored (`git status` 0 entries after each unit run) |
| Case-file commit / harness commit | `e985003` + uncommitted amendments (sha256 above) / uncommitted |
| Storage for node data | internal APFS SSD, `$W/node-crs` (wiped before every start and at the end) |
| Re-checked at step E | free disk 139 GiB (138 GiB at the cluster pre-check); ports 7000, 7199, 9042, 9091, 7012 free; loopback 127.0.0.1–.3 present; no `CassandraDaemon` |
| Full logs | `~/Library/Caches/stage4/logs/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb/` (`build-test.log`, `unit-shakedown/`, `cluster-shakedown/`, `unit-run1/`, `cluster-run1/`, `selfcheck.out`) |

## 3. Runbook defects

None. The four filed statements that would have stopped or invalidated a run (test yaml chunk cache, uncompressed stress table,
`disableautocompaction` before the keyspace exists, `MaxDirectMemorySize`) were found by the audit from the source and amended before
any run.

## 4. Run 1

**Scope:** both tiers, every value, control and repetition of B2b and B3b (as amended). **Command logs:** `unit-run1/commands.log`,
`cluster-run1/commands.log`. Excerpts in [`compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/):
`unit/stage4.out`, `unit/summary.txt`, `unit/commands.log`, `unit/yaml-diff-rep1.txt`; `cluster/summary.txt`, `cluster/<arm>-readahead-own.trace`
(the arm's `Data.db` lines; none exists for `cc`: no rule fired on that start and Byteman wrote no file), `cluster/<arm>-poll.csv`,
`cluster/setter-info-lines.txt`; `selfcheck.out`.

### 4.1 Readings

**Unit tier** ([`unit/stage4.out`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/unit/stage4.out); rep1 shown, rep3 identical to the byte; rep2 at most 16 B higher in every v and stale cycle and 520 B lower in the gate cycle)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `ant testsome` × 3 | rc 0, `Tests run: 1, Failures: 0, Errors: 0` each (≈ 19 s) | `unit/commands.log` |
| Read-backs | 1 SSTable, chunk 16,384, live reader `CompressedChunkReader$Standard` captured 262,144, `fileCacheEnabled=false`, `diskAccessMode=standard`, getter 256 KiB | `unit/stage4.out` |
| Setter 0 / 128 / 255 | `REJECTED IllegalArgumentException compressed_read_ahead_buffer_size_in_kb must be at least 256KiB`, getter 256 after each | same |
| Setter 2097152 / 2097151 | `REJECTED ConfigurationException compressed_read_ahead_buffer_size must be positive value <= 2147483646B, but was 2147483648B`, getter 256 / `ACCEPTED`, getter 2097151 | same |
| v = 256 / 1024 / 4096 / 16384, fresh reader | setter accepted, getter = v; captured size = 262,144 / 1,048,576 / 4,194,304 / 16,777,216 | same |
| same, T = 1 | the worker held one direct buffer of exactly v × 1024; openDeltaC = 278,431 / 1,064,863 / 4,210,591 / 16,793,503 = v × 1024 + 16,287; closedDeltaC 16,287; buffer gone after close; countDelta 2 | same |
| same, T = 8 | 8 workers, each one direct buffer of exactly v × 1024; openDeltaC = 2,227,448 / 8,518,904 / 33,684,728 / 134,348,024 = 8 × v × 1024 + 130,296 (= 8 × 16,287); closedDeltaC 130,296; all buffers gone after close; countDelta 16 | same |
| Pool correction | `poolOpen` = `poolClosed` = 0 in every v and stale cycle (no macro-chunk was allocated inside a cycle) | same |
| Stale reader (live reader, knob 16384, T = 8) | captured **262,144** while the getter reads 16384; each worker's buffer **262,144** (not 16,777,216); openDeltaC 2,227,448 (= the v = 256 reading, not 134 MB) | same |
| Gate control (chunk 1024 KiB, v = 512, T = 8) | captured `none`; no worker had a buffer; openDeltaC 8,335,832 ≤ 9,227,468; `poolOpen` 8,388,608 = 8 × 1 MiB rebufferer buffers allocated by the pool directly | same |

**Cluster tier** (one node, 127.0.0.1, `-Xms2G -Xmx2G -XX:MaxDirectMemorySize=8192M`, Byteman on both starts; every compaction ≈ 19.8 s for
16 SSTables of ≈ 22 MB; 185–187 samples inside each window, 42–44 in each baseline with spread 0; [`cluster/summary.txt`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/cluster/summary.txt), [`selfcheck.out`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/selfcheck.out))

| Capacity value | Arm | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| — | n1, cc | read-backs | `compressed_read_ahead_buffer_size=256KiB`, `file_cache_enabled=false` (cc `true`), `DiskAccessMode is standard`, `MaxDirectMemorySize=8192M`, JMX 256 at start, Byteman agent on | `summary.txt` |
| 255, 0 | n1 | setter | `REJECTED 255 javax.management.RuntimeMBeanException: java.lang.IllegalArgumentException: compressed_read_ahead_buffer_size_in_kb must be at least 256KiB now 256`; the same for 0; no INFO line on the node | `summary.txt`, `setter-info-lines.txt` |
| all | n1, cc | setter | every accepted set `OK v now v`; node INFO lines `set compressed read ahead buffer size to` 256, 4096, 16384, 4096, 256, 16384 (n1) and 16384 (cc), in order | `summary.txt`, `setter-info-lines.txt` |
| all | every arm | workload | 16 × 100,000 rows, 0 errors; 16 SSTables before, ratio 0.917; 1 after; `nodetool compact` rc 0 | `summary.txt` |
| 256 KiB | v256 | trace / JMX | 16 `alloc` of 262,144, direct, on `CompactionExecutor:3`, inside the window; 16 `free`; peak 4.11 MiB, after −0.15 MiB | `v256-readahead-own.trace`, `v256-poll.csv` |
| 4096 KiB | v4096 | trace / JMX | 16 × 4,194,304 on `CompactionExecutor:4`, 16 freed; peak 64.13 MiB, after −0.16 | `v4096-*` |
| 16384 KiB | v16384 | trace / JMX | 16 × 16,777,216 on `CompactionExecutor:6`, 16 freed; peak 256.11 MiB, after −0.15 | `v16384-*` |
| 4096 KiB | v4096b | trace / JMX | 16 × 4,194,304 on `CompactionExecutor:5`, 16 freed; peak 64.10 MiB, after −0.16 | `v4096b-*` |
| 256 → 16384 KiB | stale | trace / JMX | written at 256, `set 16384` before the compaction: 16 × **262,144** on `CompactionExecutor:8`, 16 freed; peak **4.11 MiB**, after −0.15 | `stale-*` |
| differences | — | JMX | peak(v4096) − peak(v256) 60.02 MiB, peak(v4096b) − peak(v256) 59.99; peak(v16384) − peak(v4096) 191.98, − peak(v4096b) 192.01; peak(stale) − peak(v256) 0.00; peak(v16384) − peak(stale) 252.00 | `selfcheck.out` |
| 16384 KiB + chunk cache | cc | trace / JMX | no read-ahead allocation for any file (no trace file); INFO: peak 344.78 MiB, after 344.52 MiB — the chunk cache's own pool, retained | `cc-poll.csv`, `selfcheck.out` |
| — | n1 | INFO other files | 1,920 read-ahead allocations of system-table files (stress schema range reads, start-up, system compactions) on `ReadStage-*` (1,294), `Native-Transport-Requests-*` (439), `CompactionExecutor` (145), `main` (42): 943 of 262,144 (readers from start-up), 564 of 4,194,304 and 413 of 16,777,216 (system SSTables flushed after a set); none inside any compaction window | full trace, `selfcheck.out` |

### 4.2 Conclusion and logic

1. **Validity.** Valid.
   - Unit: each repetition read back the expected path — one SSTable, chunk 16,384, `Standard` factory, file cache off, `standard` access [observed: `unit/stage4.out` readback lines]; every worker read one partition and no worker failed (`errors=0`) [observed: same]; the test yaml was restored after the runs [observed: `unit/commands.log`, `clone status 0 entries`].
   - Cluster: read-backs as set; every arm compressed (ratio 0.917) with 16 SSTables before and 1 after, compaction rc 0; ≥ 185 samples in every window; the trace shows all 16 allocations inside the client window [observed: `cluster/summary.txt`, `selfcheck.out`]. Held fixed: heap, `num_tokens: 1`, `disk_access_mode` default, compaction throughput 16 MiB/s for every arm [observed: `cluster-run1/commands.log`].
2. **Readings.** Nothing unusual for the verdict. INFO: (a) system-table scans used both old (262,144, from readers built at start-up) and new sizes (4 / 16 MiB, from system SSTables flushed after a set) on the same node at the same time — the pick-up rule seen on files the runbook did not target [observed: full `n1/readahead.trace`]; (b) with the chunk cache on, direct memory rose by 345 MiB and stayed [observed: `cc-poll.csv`]; (c) the gate control's 1 MiB rebufferer buffers are pool overflow, removed by the correction as derived [observed: `poolOpen=8388608`].
3. **Matched row.**
   - Unit — B2g "**Confirmed**: (r)–(u) of B2f hold in all three repetitions": (r) rejections and getters exact [observed: `unit/stage4.out` set lines]; (s) captured = v × 1024, every worker's buffer = v × 1024 direct, openDeltaC − T·v·1024 = T × 16,287 (band ±T × 40,960), countDelta ≥ T, closedDeltaC = T × 16,287 ≤ T × 40,960 [observed: same]; (t) stale captured and buffers 262,144, openDeltaC 2,227,448 vs E 2,097,152 (band ±327,680) [observed: same]; (u) gate captured `none`, no buffer, openDeltaC ≤ 8 × 1.1 MiB [observed: same]. Self-check 193 unit checks hold.
   - Cluster — B3g "**Confirmed**: (i)–(v) of B3f and the B3h controls hold": (i) both rejections with the message, `now 256`, no INFO line; (ii) every accepted set OK, read back, one INFO line each; (iii) 16 allocations of exactly v × 1024 (stale: 262,144), direct, one `CompactionExecutor` thread, all freed; (iv) all six differences inside their bands (60.02, 59.99 in [51, 69]; 191.98, 192.01 in [163.2, 220.8]; 0.00 ≤ 9; 252.00 in [214.2, 289.8]), after within 0.16 MiB of baseline; (v) validity as in part 1; B3h: cc no read-ahead allocation [observed: `summary.txt`, traces, polls, `selfcheck.out`].
4. **Excluded rows.**
   - Unit **Refuted (setter floor)**: all four out-of-range values rejected, getter unchanged [observed: set lines]. **Refuted (sizing)**: every buffer = v × 1024; openDeltaC grows 64× from v = 256 to 16384 [observed: cycle lines]. **Refuted (pick-up)**: the stale reader kept 262,144 under a getter of 16384, and every fresh reader captured v [observed: reader and stale lines]. **Refuted (release)**: `afterClose` 0 buffers, closedDeltaC = holders only [observed: cycle lines]. **Refuted (gate)**: no buffer, no v-proportional term [observed: gate line]. **Not confirmed**: every corrected delta inside its band; the three repetitions agree. **Invalid**: part 1.
   - Cluster **Refuted (setter floor)**: 255 and 0 rejected, attribute 256. **Refuted (sizing)**: caps = v × 1024; peaks 4 / 64 / 256 MiB. **Refuted (pick-up)**: stale buffers 262,144 and peak 4.11 MiB, 252 MiB below v16384. **Refuted (release)**: 16 `free` per arm, after ≤ 0.16 MiB. **Not confirmed**: all bands hold, ≥ 185 samples per window. **Invalid**: part 1.
5. **Observed vs. inferred.**
   - (a) "No read-ahead buffer in cc" rests on the absence of any trace file; Byteman writes the file only when a rule fires [inferred: the agent was on the command line (`byteman_agent=1`), the same rules fired 4,000 times on n1 and in the shakedown, and the result matches the unit tier's chunk-cache path in the source (`ChunkCache.java:261-265`)]. It decides only the B3h control.
   - (b) The 16,287 B per worker is the compressed-chunk holder [inferred: equals 16,384-byte chunk compressed by LZ4 plus header and CRC, within the derived ≤ 16,472; constant across v and present after close]. It sits inside every band either way.
   - (c) The 345 MiB in cc is the chunk cache's pool [inferred: retained after compaction, no read-ahead allocation]. INFO only.
6. **Deviations and gaps.**
   - None from the frozen runbook. Not exercised: `disk_access_mode: mmap`/`legacy`, range reads as the measured workload (seen as INFO only), an old and a new reader of one file scanned on the same thread (shared block, A3 amendment), concurrent compactions.
   - The self-check reads the setter client output and the compaction exit code and window from `commands.log`, the runner's record; no other file holds them.
7. **Core question.**
   - The setter enforces its floor: values below 256 KiB (and above 2,097,151 KiB) are refused and nothing changes (unit (r), cluster (i)); 0 cannot be set at runtime.
   - An accepted value sizes each read-ahead buffer exactly — but only for readers built after the set; readers built before keep their size (unit (s), (t); cluster (iii), stale arm).
   - Direct memory follows scanners × B and returns on close: 8 × B per 8 scanners, 16 × B per 16-SSTable compaction, 4 → 64 → 256 MiB at 256 KiB → 4 MiB → 16 MiB (unit (s); cluster (iv)); nothing bounds the total.
   - **The runtime setter caps the size of each read-ahead buffer of readers opened after the change; it does not cap the total, which grows with the number of SSTables scanned at once (and threads scanning).**

**Conclusion (one line):** Unit B2g row Confirmed and cluster B3g row Confirmed — **Confirmed** (floor enforced; each buffer = the value set, on readers built after the set; total = scanners × B).

## 5. Self-check of run 1 — AI

Independent script [`harness/.../selfcheck.py`](../harness/compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/selfcheck.py), written before the run-1
readings (one change before them: a guard for a missing `poll.csv`, made during its dry run on the shakedown logs; none after). It
re-parses the raw files and never reads `summary.txt`: unit `stage4.out` and `ant-<rep>.log`; cluster `n1/` and `cc/` `system.log` and
`readahead.trace`, each arm's `poll.csv` and `tablestats-before/after.txt`, and `commands.log` only for the setter client output and the
compaction exit code and window. **Result: 246 of 246 checks hold** ([`run1/selfcheck.out`](compressed_read_ahead_buffer_size-setCompressedReadAheadBufferSizeInKb-sizeInKb--autonomous/run1/selfcheck.out)). INFO lines: other-file allocations inside the windows 0 in every arm; cc 344.78 MiB (chunk cache).

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.out`: `unit.rep*.readback`, `unit.rep*.ant`, `cluster.*.readback`, `cluster.*.sstables`, `cluster.*.compact`, `cluster.*.samples`. `byteman_agent=1` and `MaxDirectMemorySize=8192M` re-read in `cluster-run1/commands.log`. |
| 2. Readings | yes | System-table allocations re-counted in the full `n1/readahead.trace` (943 / 564 / 413 by size; threads `ReadStage-*`, `Native-Transport-Requests-*`, `CompactionExecutor`, `main`); `cc-poll.csv` re-read (≈ 345 MiB to the end); gate `poolOpen=8388608` in `stage4.out`. |
| 3. Matched row | yes | Each clause is a self-check line (`reject.*`, `max.*`, `*.captured`, `*.per_buffer`, `*.openDeltaC`, `*.closedDeltaC`, `*.released`, `stale.*`, `gate.*`; cluster `reject.*`, `setlog`, `per_buffer`, `freed`, `after`, the six differences). |
| 4. Excluded rows | yes | The excluding readings are the same lines; the stale lines carry the pick-up row. |
| 5. Observed vs. inferred | yes | (a) `ls cluster-run1/cc/readahead.trace` → no such file, while `READBACK cc … byteman_agent=1` is in `commands.log`; n1 trace 2,000 alloc / 2,000 free. (b) 16,287 / 130,296 (= 8 × 16,287) in every v cycle and in the shakedown. (c) INFO. |
| 6. Deviations and gaps | yes | No defect, no restart; `unit-run1/` and `cluster-run1/` are the only run-1 folders. |
| 7. Core question | yes | Floor (r)/(i) → per-buffer size on new readers (s)/(iii) → old readers keep theirs (t)/stale → total = scanners × B (T = 1 vs 8; 16 SSTables; 4/64/256 MiB) → no aggregate limit in the source (A3 amendment). |

### 5.2 Run 2?

**No** — 2026-10-25. Every decisive clause is observed (per-buffer sizes from the threads' own maps and the allocation trace, JMX
deltas within kilobytes of prediction, three identical unit repetitions); the one inference (5 a) decides only a control and agrees with the
source. The result neither refutes the case nor confirms a new bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive (scoped: sets a per-scanner buffer size, not an aggregate cap).

**Claim tested (B1):** The value accepted by `setCompressedReadAheadBufferSizeInKb` (≥ 256 KiB) determines the direct-memory buffer
allocated per open SSTable scan on readers opened afterwards: direct memory used by k simultaneously open scans grows by about k × value
and returns to baseline when the scans close. Values below 256 KiB, including 0, are rejected and leave the setting unchanged.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**: B2g row Confirmed. 0/128/255 refused (`IllegalArgumentException`), 2097152 refused (`ConfigurationException`), getter unchanged; fresh readers captured v and every scanner held one direct buffer of exactly v (256 KiB–16 MiB), direct memory = T × v + holders and back on close; the reader opened before the change kept 256 KiB under a knob of 16 MiB; no buffer when v ≤ chunk length; three identical repetitions | **per buffer: caps** (size = the value set, on readers built after the set) · **total: does not cap** (= scanners × value) | run 1 + self-check | 2026-10-25 |
| Cluster | **Confirmed**: B3g row Confirmed. JMX `set 255`/`set 0` refused, attribute stays 256; after each accepted set a 16-SSTable compaction held exactly 16 buffers of the value set (4 / 64 / 256 MiB at 256 KiB / 4 MiB / 16 MiB, differences 60.0 and 192.0 MiB), all freed; SSTables written before `set 16384` were compacted with 256 KiB buffers (4.1 MiB); no buffer with the chunk cache on | **per buffer: caps** · **total: does not cap** (256 MiB from one compaction at 16 MiB, unbounded in SSTables and threads) | run 1 + self-check | 2026-10-25 |

**What each outcome means here.**
- The setter is a guarded runtime knob: 1–255 KiB and 0 are refused (start-up accepts 0 as "disabled"; the setter cannot disable the buffer), and so is anything above 2,097,151 KiB.
- A change applies to readers built afterwards only: existing SSTables keep their old buffer size until compaction replaces them or the node restarts. Lowering the value at runtime therefore does not shrink the buffers of existing SSTables.
- Each buffer is exactly the value; the total is (threads scanning) × (distinct SSTables each scans) × value, with no aggregate limit.

**Feedback filed:**
- The case file's section D was filled (uncommitted). Amendments: the audit's eighteen, all before any reading; nothing amended after a reading.
- Index rows: `_INDEX.md` §1 (Stage 4), §2 (one new hash row: audit freeze), §3 (coverage line).
- For stage 3: (1) a unit tier on `CQLTester` inherits `test/conf/cassandra.yaml`, which sets `file_cache_enabled: true` — check the unit yaml's defaults against the path; (2) `cassandra-stress` tables are uncompressed unless `-schema compression=…`; (3) `nodetool disableautocompaction` without a keyspace does not cover a keyspace created afterwards; (4) `MaxDirectMemorySize` under `bin/cassandra` is a quarter of RAM; (5) a design about "readers opened afterwards" needs a reader opened before the change as its control.

**Processes:** after the cluster tier, `final CassandraDaemon processes: none` and `node-crs` was wiped (`run1/cluster/summary.txt`).
Re-checked at the end of the session: `ps -eo command | grep '[C]assandraDaemon'` empty; no stress or poller JVM; ports 7000/7199/9042/9091/7012
free; `$W/node-crs` removed; the run clone clean (`git status` 0 entries: test yaml restored, test removed); the repository root has no
`build/` or log folder.
