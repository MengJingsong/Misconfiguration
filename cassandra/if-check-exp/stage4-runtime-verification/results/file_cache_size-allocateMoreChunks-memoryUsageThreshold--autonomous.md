# file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous — stage-4 results  <!-- file: results/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.md -->

> **Case:** [`file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous`](../../stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous.md)
>
> **Status:** verdict filed (2026-10-27)
>
> **Outcome class:** undetermined — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/`](../harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/).
>
> **Agent:** autonomous. "§9a" = B2f/B2g (unit) and B3f/B3g (cluster); runbook = B2a–B2e / B3a–B3e; feedback = section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code CLI, 2026-10-27, advisor's Mac (`advisor-run`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed `9bc2de1e5feea1b60c09483d2b49e366c0f648c6ba5bc6ab5925664ae2879d07` (commit `a146c1b`). Frozen after the audit's eight amendments (U1–U3, C1–C5): `10148c88060310aeeb66a359b0db26927e86c3668ed1b932dac3420531674cdf`. After runbook-defect fix D1, found by the cluster shakedown before run 1: **`89b5f6fec9513c24b2d5ee999fe645174d2bc21addde42d25e48c16229b96c0c`**. Both tiers of run 1 ran at this version. All three hashes are rows in `_INDEX-advisor.md` §2. Not committed (uncommitted working tree on `advisor-run`, HEAD `2ec1622`) |
| **Harness** | `harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/`: `BufferPoolCapProbeTest.java`, `unit-run.sh`, `fcs-node.btm` (observe-only), `FcsSampler.java` (JMX), `make-node-conf.sh`, `cluster-run.sh`; `results/<stem>/run1/selfcheck.py`. Not committed. Reused tools: `make-node-conf.sh` is a copy of `harness/bloom_filter_fp_chance-getFilter-maxFalsePosProbability--autonomous/make-node-conf.sh` with clone, node path and cluster name changed; the node mechanics of `cluster-run.sh` (timeout wrapper, start, wait, stop, idle wait, final check) are adapted from that folder's `cluster-run.sh`; `unit-run.sh`'s shell structure from `harness/max_queue_weight-acquireWeight-weight--autonomous/unit-run.sh`; `FcsSampler.java`'s JMX connection code follows `harness/column_index_cache_size-indexSamples-cacheSizeThreshold--guided/Jmx.java`. No source file was changed. Every value, band and expectation here was derived from the pinned source; none was taken from another case file or results file (the guided file of the same constraint and its results were not opened) |
| **Instrument checks** | Byteman `TestScript` type-checked the three node rules, including the inner-class field path `$0.this$0` (`run1/typecheck-node-rules.txt`, "no errors"). Unit: two shakedowns (`unit-shake`, `unit-shake2`); the first showed that the `FCSU-ENV` line printed before logging was initialised went to ant's output, so it now prints after the pool is created (harness only). Cluster shakedown (`cluster-shake`: N = 400,000, 60-s reads, 48 MiB and 0 MiB) exercised every step: at the quiet samples the gauge pooled equalled the largest `BMFC SLAB` value (50,331,648 and 0), and it showed D1. Self-check end to end on the shakedowns: unit 61/61 exit 0, cluster 18/18 exit 0 after D1 (`run1/shake/`) |
| **Tiers and values** | Unit: one JVM per T ∈ {0, 1.5 MiB, 4 MiB, 8 MiB, 16 MiB} with 384 × 64 KiB, and T = 512 MiB (default) with 16,384 × 64 KiB. Cluster: one node, 8,000,000 partitions of 512 B (LZ4, 16 KiB chunks), 10-min uniform reads at `file_cache_size` ∈ {48, 96, 192 MiB, default (512 MiB), 0} |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A | constrained quantity is memory or disk bytes | Met | A2/B1: bytes of pooled direct slabs (`memoryAllocated`) |
| A | knob varied, ≥ 3 values incl. default | Partly → Met after U2(c)/C2(a) | Filed: five unit values and four cluster values, without the default. Both tiers now add 512 MiB, the default at any heap ≥ 2 GiB (`DatabaseDescriptor.java:576-577`) |
| A | real resource measured, not only the counter | Partly (gap named) | Unit: only the pool's counters (B2d says so). Cluster: the pool gauges, the JVM's `java.nio` direct total and NMT. C3(b) uses an observe-only Byteman read of `memoryAllocated`, because the gauge difference `Size − OverflowSize` is not atomic. Gap: the direct total includes other consumers (A4), so the pool's own direct bytes are seen only through its counter |
| A | usage driven to the limit and past it | Met | Unit: 24 MiB (and 2·T for the default) against every T. Cluster: uniform reads over ~4.2 GB against caps of at most 512 MiB; B3g row 4 covers "never reached" |
| B | each step says what it establishes | Met | B2g/B3g, B2h/B3h |
| B | prediction in numbers | Met | B2f exact per T; B3f bounds and order |
| B | every plausible outcome has a row | Partly → Met after U3/C5 | Neither table had verdict words, an order or an Invalid row |
| B | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after U3/C5 | B2g row 1 and B3g row 1 named the ceiling only. U3(6) also needs the message at every T > 0; C5(6) needs `BMFC CAP chunk-cache` at 48 MiB |
| B | alternative explanations and controls | Met | T = 16 MiB and 192 MiB positive controls; T = 0 / 0 MiB silent branch; networking gauges unchanged; `heap_buffers` and `standard` remove confounders |
| C | a human can follow it | Met | A3 + B1 |
| C | an AI can run it without re-deriving | Partly → Met after U2/C4 | `pool.unsafeFree()` (B2e step 2) does not exist; one JVM per value; exact sequence and abort conditions |
| C | values, commands, observables exact | Partly → Met after C2/C3 | The read command lacked the write's `-col` spec; `sjk mx` replaced; plateau, "overflow growing" and the log-line masking defined |
| D | prerequisites exist or are listed | Partly → Met after U1/C1 | `/local`, Linux and jvm-options edits replaced by this host's clone, paths and `JVM_EXTRA_OPTS` |
| D | workload arithmetic | Met | ~4.2 GB data against 118 GiB free; ≤ 1.1 GiB direct in the unit JVM (limit 2 GiB); 2 GiB direct limit on the node; about 1 h of node time |
| D | citations spot-checked | Met, with findings S1–S4 | `BufferPool.java:128-135, 142-189, 230-300, 385, 410-485, 903-960, 1095-1103, 1318, 1628-1635`; `BufferPools.java:38-56`; `BufferPoolMetrics.java:58-64`; `ChunkCache.java:49-54, 147-172`; `DatabaseDescriptor.java:573-577, 3784-3793`; `Config.java:494-514`; `NoSpamLogger.java:149-167, 212-255`; `conf/cassandra.yaml:744-759`; `conf/jvm11-server.options:63` |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| U1 | host clone `$W/cassandra-run63`, build, harness test path | applied 2026-10-27 (uncommitted) | no `/local` here |
| U2 | one JVM per T; `unsafeReset()` for the missing `unsafeFree()`; default T = 512 MiB with 1 GiB demand and `-XX:MaxDirectMemorySize=2g`; exact output lines | applied | shared NoSpam statement (S2); B2e step 2 not runnable as written (S3); default value |
| U3 | B2g verdict words, order and Effect rule | applied | missing Invalid row and verdict words; disallow evidence |
| C1 | host node, start-up options, cleanup | applied | this host |
| C2 | default value; read command with `-col`; arithmetic | applied | default value; stress reads need the write's column spec |
| C3 | JMX sampler; pooled_exact by Byteman; CAP/REFUSE lines; log masking; definitions | applied | non-atomic gauge pair; direct disallow evidence; shared NoSpam statement |
| C4 | exact sequence, abort conditions, shakedown | applied | exactness |
| C5 | B3g verdict words, order and Effect rule | applied | missing rows |
| S1 | **For stage 3 (claim):** `MACRO_CHUNK_SIZE = 64 * NORMAL_CHUNK_SIZE` = 64 × 128 KiB = **8 MiB** (`BufferPool.java:128, 385`). The Javadoc at `:384` says "1 MiB", and the log message prints `cannot allocate chunk of 8.000MiB`. So a slab is 8 MiB, split into 64 normal chunks (A3.3 says 8), and serves 128 buffers of 64 KiB (B2c says 16). B1's ceiling is `floor(T/8 MiB)·8 MiB`, not `floor(T/1 MiB)·1 MiB`. Source expectation: pooled 0 at T = 1.5 and 4 MiB, with all 24 MiB overflowing | left for stage 3; predictions not changed | it changes B1's claim and B2f; the run decides |
| S2 | For stage 3: the message at `:447` uses one static NoSpamLogger statement for every pool in the JVM (`BufferPool.java:135`; `NoSpamLogger.java:212, 252`). Only the first pool to hit its cap logs within 15 min, so "exactly when the cap is hit" (B1) holds per JVM, not per pool | applied as U2(a)/C3(d) for the run | instrument and claim detail |
| S3 | For stage 3: `BufferPool` has no `unsafeFree()`; it is on `GlobalPool` (package-private) and reached through `unsafeReset()` | applied as U2(b) | B2e step 2 |
| S4 | For stage 3: A3.3/A3.6 say "1 MiB plus one page" per slab; it is 8 MiB plus one page (`allocateDirectAligned`, `:1095-1103`) | left for stage 3 | text fix |
| R1 | Measure the pool's own direct bytes, not only the counter, e.g. Byteman on `allocateDirectAligned` with the JVM direct total as a cross-check | left for stage 3 | outside this design |

**Order slip (recorded).** The first unit shakedown (`unit-shake`) ran on 2026-10-27 at 13:31, after the harness was written but before the
amendments were written into the case file and frozen. No prediction was written or changed in view of it: B2f is unchanged as filed;
U2(c)'s T = 512 MiB row applies B1's filed formula; U3 maps each filed B2g row to a verdict word by that row's own wording ("Claim refuted",
"partial result", "Claim confirmed"). The run-1 unit tier ran after the freeze.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (unit 13:46–13:48, cluster 13:47–14:47 EDT) |
| Node | `yangwang-mbp` (advisor's laptop), single host, 10 cores, 32 GiB |
| OS and kernel | macOS 27.0.1 (26A434) / Darwin 27.0.0 arm64 (T6000) |
| JDK | OpenJDK 11.0.32.1 (Homebrew) |
| Ant | 1.10.18 |
| Python | 3.8.11 (self-check) |
| Clone commit | `$W/cassandra-run63` (`W=~/Library/Caches/stage4`), `b5f2a54210d541339c2e7c17a794195cac0e67c2`, `cassandra-5.0.9`; `ant -Dlocal.repository=$W/m2 build-test` succeeded in 56 s |
| Case-file / harness commit | uncommitted (repo HEAD `2ec1622`); case-file sha256 values in §1 |
| Storage | internal SSD, APFS, 118 GiB free; node dir `$W/node-fcs` (wiped after) |
| Loopback | 127.0.0.1–.3 present on `lo0` (only .1 used) |
| Full logs | `$W/logs/file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/` (`clone-build.log`, `unit-shake`, `unit-shake2`, `unit-r1`, `cluster-shake`, `cluster-r1`) |

**Machine lessons relied on.**
- Workspace and environment: `$W` and `env.sh`; every ant call with `-Dlocal.repository=$W/m2`; commands touching `$W` or Java ran unsandboxed; scripts made executable before running.
- Unit test JVM: a knob for the forked JVM goes through `-Dtest.jvm.args` (here `-XX:MaxDirectMemorySize=2g`, read back in `FCSU-ENV`); `build.xml` appends `-Xmx1024m`; the TEST log is per class, so it is deleted before each method and copied after; test stdout is written one line per `System.out` call, and only after logging is initialised.
- Node: no `setsid`, so the node runs as a tracked background process; `cassandra-env.sh` sets `-XX:MaxDirectMemorySize=8192M` and the later `-XX:MaxDirectMemorySize=2G` from `JVM_EXTRA_OPTS` wins (both appear in the `JVM Arguments` line); system.log is read from its byte offset at each start; the daemon class name is kept out of pkill patterns.
- Instruments: `nodetool sjk mx` replaced by a small JMX client; Byteman rules on Cassandra classes need no `boot:`; a sampler cannot see what happens between samples, so the counter is read at the point of interest by an observe-only rule; NMT is reported for information only.
- Stress: the read uses the write's `-col` spec.
- Protocol habits: shakedowns before run 1; `selfcheck.py` run end to end on the shakedown output with its exit status checked; long steps run in the background and polled; no `cassandra.logdir_IS_UNDEFINED/` left in the clone.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster shakedown (before run 1) | C3(b) "the last chunk-cache value" | Each `BMFC SLAB` line reads `memoryAllocated` when it prints. Two threads allocating together printed the same value (`16777216` twice) and could print out of order (`run1/shake/cluster-shake-48MiB-slab-lines.txt`) | pooled_exact = the largest chunk-cache SLAB value, which equals `memoryAllocated` at the end of the run; the line count is the slab count. B3f, B3g and C5 unchanged | fixed 2026-10-27; cluster tier not yet run | `89b5f6fe…` |

Harness changes during the shakedowns (no case-file change): `FCSU-ENV` printed after the pool is created; the self-check's SLAB consistency check
follows D1 (multiples of 8 MiB, largest = count × 8 MiB).

## 4. Run 1

**Command logs:** `file_cache_size-allocateMoreChunks-memoryUsageThreshold--autonomous/run1/unit/commands.log`, `run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `run1/unit/TEST-<m>.log`, `TEST-<m>.xml`). Six JVMs, each 1 test, 0 failures, 0 errors. `FCSU-ENV`: `macroChunkSize=8388608 normalChunkSize=131072`; the JVM arguments include `-XX:MaxDirectMemorySize=2g`.

| T | demand | B1 ceiling `floor(T/1 MiB)` (B2f pooled) | pooled | overflow | used | buffers from the pool | message for `probe-<T>` (B2f) | after puts: size / overflow / used |
|---|---|---|---|---|---|---|---|---|
| 0 | 24 MiB | 0 | **0** | 25,165,824 | 25,165,824 | 0 of 384 | absent (absent) | 0 / 0 / 0 |
| 1.5 MiB | 24 MiB | 1,048,576 | **0** | 25,165,824 | 25,165,824 | 0 of 384 | present (present) | 0 / 0 / 0 |
| 4 MiB | 24 MiB | 4,194,304 | **0** | 25,165,824 | 25,165,824 | 0 of 384 | present (present) | 0 / 0 / 0 |
| 8 MiB | 24 MiB | 8,388,608 | **8,388,608** | 16,777,216 | 25,165,824 | 128 of 384 | present (present) | 8,388,608 / 0 / 0 |
| 16 MiB | 24 MiB | 16,777,216 | **16,777,216** | 8,388,608 | 25,165,824 | 256 of 384 | present (present) | 16,777,216 / 0 / 0 |
| 512 MiB (default) | 1 GiB | 536,870,912 | **536,870,912** | 536,870,912 | 1,073,741,824 | 8,192 of 16,384 | present (present) | 536,870,912 / 0 / 0 |

Every message reads `Maximum memory usage reached (<T>) for probe-<T> buffer pool, cannot allocate chunk of 8.000MiB`, one per JVM.

**Cluster tier** (`run1/cluster/summary.txt`; per value `run1/cluster/<value>/samples-*.txt`, `bmfc-*.txt`, `caplog-*.txt`, `capcheck-*.txt`, `nmt-*.txt`, `info-*.txt`, `stress-excerpt.txt`).
LOAD: 8,000,000 writes, 0 errors, 67,552 op/s; after `compact`, one SSTable of 4,450,715,221 B (LZ4, `chunk_length_in_kb` 16, ratio 0.98).
Every read run: 10 min, 0 errors, 72,789–76,400 op/s; 61 samples in the read window plus 3 quiet ones. The node ran G1 with `-Xms2G -Xmx2G` and the effective `-XX:MaxDirectMemorySize=2G`, with the Byteman agent loaded.
Networking `Capacity` was 134,217,728 in every sample of every run. Its pool held one slab (one `BMFC SLAB networking 8388608` line per run), with no networking CAP line and no networking message. system.log has 0 `ERROR` lines.

| Value | Capacity (read back) | pooled_exact (largest `BMFC SLAB chunk-cache`) | SLAB lines | `BMFC CAP chunk-cache` | `BMFC REFUSE chunk-cache` | chunk-cache message | overflow > 0 (samples in window) / max | gauge pooled at quiet sample | largest gauge `Size − OverflowSize` in window | direct `MemoryUsed` at quiet sample | NMT Other committed | `nodetool info` chunk cache |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 48 MiB | 50,331,648 | **50,331,648** | 6 | yes, at 50,331,648 | yes | 1 | 61 of 61 / 24,748,032 | 50,331,648 | 58,884,096 | 101,221,816 | 443,252 KB | 16 MiB of 16 MiB |
| 96 MiB | 100,663,296 | **100,663,296** | 12 | yes, at 100,663,296 | yes | 1 | 61 / 25,247,744 | 100,663,296 | 101,556,224 | 152,178,625 | 493,015 KB | 64 MiB of 64 MiB |
| 192 MiB | 201,326,592 | **201,326,592** | 24 | yes, at 201,326,592 | yes | 1 | 61 / 26,705,920 | 201,326,592 | 201,736,192 | 259,247,058 | 597,574 KB | 159.99 MiB of 160 MiB |
| default (512 MiB) | 536,870,912 | **536,870,912** | 64 | yes, at 536,870,912 | yes | 1 | 61 / 40,812,544 | 536,870,912 | 537,690,112 | 591,504,129 | 922,043 KB | 480 MiB of 480 MiB |
| 0 MiB | 0 | **0** | 0 | **no** | yes, at 0 / 0 | 0 | 52 of 61 / 73,728 | 0 | 90,112 | 44,798,505 | 388,151 KB | (cache disabled; no line) |

The gauge difference `Size − OverflowSize` exceeded the knob in 22 / 19 / 29 / 11 / 25 of the 64 samples of the five runs, by 8 KB to 8.55 MB (48 MiB run). In 98 of those 106 samples the two `Size` reads of the same sample differ. At 0 MiB the gauge difference reached 90,112 B, although no slab was ever allocated (no SLAB line, `Capacity` 0).

### 4.2 Conclusion and logic

1. **Validity.**
   - Unit: all six methods ran in their own JVMs (`TEST-<m>.xml`: 1 test, 0 failures, 0 errors). `threshold` = T, `used` = demand, and `overflow` > 0 at every T [observed: `run1/unit/summary.txt`].
   - Cluster: every node started. Every `Capacity` read-back equals the knob (536,870,912 for the default), and the `Global buffer pool limit is … for chunk-cache` line names the knob. All stress runs had 0 errors. Each run with T > 0 has `BMFC` lines. At the quiet sample the gauge pooled equals pooled_exact in all five runs [observed: `run1/cluster/summary.txt`, `<value>/capcheck-*.txt`, `<value>/samples-*.txt`].
   - B3a's settings were in force: `disk_access_mode: standard`, `memtable_allocation_type: heap_buffers`, `file_cache_enabled: true` and `concurrent_reads: 32` are in every `yaml-tail-*.txt`. The `DiskAccessMode is standard` line is in `<value>/syslog-greps.txt`.
   - Valid.
2. **Readings.**
   - Unit: pooled is 0 at T = 1.5 and 4 MiB, against B2f's 1 MiB and 4 MiB. The pool's slab is 8 MiB (`FCSU-ENV macroChunkSize=8388608`; the message says "chunk of 8.000MiB"), so a pool below 8 MiB can never allocate one [observed: `run1/unit/TEST-t1_5MiB.log`, `TEST-t4MiB.log`; inferred: `BufferPool.java:385, 443`].
   - Cluster: the gauge difference overshot the knob in many samples, by up to 8.55 MB. This is read skew between `Size` and `OverflowSize`, not pooled memory: in 98 of the 106 overshooting samples the two `Size` reads differ, the 0 MiB run shows up to 90 KB of "pooled" with no slab at all, and every quiet sample matches pooled_exact exactly [observed: `samples-*.txt`]. C3(b) set pooled_exact as the judged reading before run 1 for this reason.
   - Overflow is positive throughout every read window. The chunk cache sat at its weight (knob − 32 MiB) in each run with T > 0 [observed: `info-*.txt`].
3. **Matched rows.**
   - Unit: U3(5), B2g row 5, **Not confirmed**: "Pooled < floor(T/1 MiB) MiB while overflow > 0 — the cap binds below T … note it as a partial result". At T = 1.5 MiB pooled is 0 < 1,048,576 − 131,072 with 24 MiB overflow, and at T = 4 MiB 0 < 4,194,304 − 131,072 with 24 MiB overflow [observed: unit table].
   - Unit Effect **caps**. Pooled ≤ B1's ceiling at every T, and it differs between T values (0 → 8 → 16 → 512 MiB). Where T is a multiple of 8 MiB, pooled equals T exactly, with the message present [observed].
   - Cluster: C5(6), B3g row 1, **Confirmed — caps**: "Pooled ≤ knob in all runs and increases from 48 to 96 to 192 [to the default]". pooled_exact is 50,331,648 / 100,663,296 / 201,326,592 / 536,870,912, which equals each knob exactly and increases strictly. It is 0 at 0 MiB. Direct disallow evidence: `BMFC CAP chunk-cache 50331648 50331648` at 48 MiB, at the same moment as the `Maximum memory usage reached (48.000MiB) for chunk-cache` message [observed: `48MiB/bmfc-48MiB.txt`, `48MiB/caplog-48MiB.txt`].
4. **Excluded rows.**
   - Unit row 2 (Refuted, pooled > ceiling): pooled ≤ ceiling at every T.
   - Unit row 3 (Refuted, flat): pooled takes four values across T > 0.
   - Unit row 4 (Refuted, branch): the message is absent at T = 0 and present at every T > 0.
   - Unit row 1 (Confirmed): missed at T = 1.5 and 4 MiB.
   - Unit Invalid: part 1.
   - Cluster row 2 (Refuted, pooled > knob): pooled_exact = knob, never above. The gauge overshoot is excluded as an instrument artefact (part 2), and C3(b) fixed that instrument before run 1.
   - Cluster row 3 (Refuted, flat): pooled ×2, ×2, ×2.67.
   - Cluster row 5 (Refuted, branch): at 0 MiB there is no CAP line and no message, but a REFUSE line, so the silent branch ran. At 48 MiB the CAP line and the message are both present, and no networking message could have masked it.
   - Cluster row 4 (Not confirmed, never reached): at 48 MiB pooled = 48 MiB and overflow > 0.
   - Cluster Invalid: part 1.
5. **Inferred statements the conclusion depends on.**
   - (a) The unit row-5 miss comes from the 8 MiB slab size (`BufferPool.java:385`), not from local-pool fragmentation, the cause B2g row 5 suggests. Evidence: `served` = 0 at T = 1.5 and 4 MiB (no slab at all), and the slab count is exactly T / 8 MiB at 8, 16 and 512 MiB.
   - (b) The `BMFC SLAB` value read after each slab's CAS is `memoryAllocated` at the end of the run (D1). The quiet-sample equality with the gauges, in all five runs, cross-checks this.
   - (c) Real direct memory: the pool's slabs are direct buffers of 8 MiB plus one page (`:1095-1103`). Direct `MemoryUsed` rises with the knob (44.8 / 101 / 152 / 259 / 592 MB at 0 / 48 / 96 / 192 / 512 MiB) and is ≥ pooled in every run. The about 45 MB of other direct use at 0 MiB stays roughly constant. This is consistent with the counter but is not a per-pool measurement (named gap).
6. **Deviations and gaps.**
   - The first unit shakedown ran before the freeze (§1, order slip); no prediction changed.
   - D1 was fixed before run 1.
   - The filed instrument (`sjk mx` gauges) was replaced by C3 before any reading. The run shows the replacement was needed: the gauge pair alone would have shown "pooled > knob" samples.
   - Native memory is not observed in the unit tier (B2d).
   - NMT "Other" is reported for information only.
7. **Core question.**
   - Usage follows the knob, in steps of the 8 MiB slab. On the node, pooled direct memory equals `file_cache_size` exactly at 48, 96, 192 and 512 MiB and is 0 at 0 MiB. In the unit tier pooled equals T at every multiple of 8 MiB and is 0 below 8 MiB (parts 3 and 5a).
   - The disallow branch fired directly: the CAP line and the message at the cap, the silent REFUSE at 0, and overflow absorbing every request past the cap (part 3).
   - So `file_cache_size` caps the chunk-cache pool's slab memory at `floor(T/8 MiB)·8 MiB`. Requests beyond the cap become unpooled direct buffers that no limit bounds (overflow up to 41 MB here, part 2).
   - The filed claim's 1 MiB granularity is wrong. That is why the unit tier does not confirm B1's exact ceiling at T = 1.5 and 4 MiB, although every reading stays at or below it.

**Conclusion (one line):** unit B2g row 5 (U3(5)) — not confirmed, caps; cluster B3g row 1 (C5(6)) — confirmed, caps.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` was written before run 1 and checked end to end on the shakedowns (unit 61/61 and cluster 18/18 after D1, exit 0 both). It re-parses the raw TEST logs and junit XML (unit). For the cluster it re-parses the raw sampler lines, the node stdout (`node-<value>.out`), the node's full `system.log` sliced by the recorded byte offsets, the cap read-backs, the stress outputs and the NMT files. It recomputes pooled_exact, the window and quiet samples, overflow, and every U3 and C5 condition on its own. Results: **unit 62/62 pass, exit 0** (`run1/selfcheck-unit.out`, verdict "Not confirmed (row 5) -- caps"); **cluster 43/43 pass, exit 0** (`run1/selfcheck-cluster.out`, verdict "Confirmed (row 1) -- caps"). Each matches the conclusion.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `run1/unit/TEST-t*.xml` (tests="1" failures="0" errors="0"); `run1/cluster/<value>/capcheck-*.txt` first line `cc_capacity` = knob; `stress-excerpt.txt` "Total errors : 0"; `yaml-tail-*.txt` |
| 2. Readings | yes | Re-read `48MiB/samples-48MiB.txt` line 27: `cc_size=71802880 cc_overflow=12918784 cc_size2=59899904`, so the largest gauge difference (58,884,096) comes from a sample whose two `Size` reads differ by 11.9 MB; `0MiB/samples-0MiB.txt` shows `cc_size − cc_overflow` up to 90,112 with `cc_capacity=0` and `0MiB/bmfc-0MiB.txt` has no chunk-cache SLAB line |
| 3. Matched rows | yes | `run1/unit/TEST-t1_5MiB.log` and `TEST-t4MiB.log` `pooled=0 … overflow=25165824`; `48MiB/bmfc-48MiB.txt` six chunk-cache SLAB lines, largest 50331648, and `BMFC CAP chunk-cache 50331648 50331648`; `default/bmfc-default.txt` 64 lines, largest 536870912 |
| 4. Excluded rows | yes | `0MiB/caplog-0MiB.txt` empty; `0MiB/bmfc-0MiB.txt` has REFUSE and no CAP; `caplog_networking=0` in every RESULT line |
| 5. Observed vs inferred | yes | (a) `served=0` at 1.5 and 4 MiB and `macroChunkSize=8388608`; (b) quiet-sample equality in all five runs (self-check check "gauge pooled = pooled_exact"); (c) is the named gap R1 |
| 6. Deviations and gaps | yes | order slip and D1 recorded; shakedown evidence under `run1/shake/` |
| 7. Core question | yes | The logic follows B1: the ceiling follows the knob and the disallow evidence is direct. The one B1 element that fails (1 MiB granularity) is a claim error found from source at audit (S1) and is reported, not tuned away |

### 5.2 Run 2?

**No** (2026-10-27). Both tiers rest on exact observed equalities: unit counters exact; node pooled_exact equal to the knob in every run and equal to the gauges at rest. The unit miss is a deterministic consequence of the 8 MiB slab, and every seed would repeat it. The inferred statements are cross-checked in run 1's own evidence or named as a gap. The cluster result neither refutes the claim nor confirms a bypass. The unit result is "Not confirmed" for a source-derived reason (S1) that a second run would not change.

## 6. Run 2

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):** for a BufferPool with threshold T bytes, the pooled slab memory (`Size − OverflowSize` = `memoryAllocated`) never exceeds `floor(T/1 MiB)·1 MiB` and reaches that ceiling when demand is larger. Demand beyond the ceiling appears as `OverflowSize`, unpooled direct memory, and is not capped. The target branch (`:445`) writes the "Maximum memory usage reached" message exactly when T > 0 and the cap is hit, and stays silent for T = 0.

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Not confirmed** (B2g row 5; U3(5)) | caps (pooled = `floor(T/8 MiB)·8 MiB`: 0 at 1.5 and 4 MiB, = T at 8, 16, 512 MiB; never above B1's ceiling) | run 1 + self-check | 2026-10-27 |
| Cluster | **Confirmed** (B3g row 1; C5(6)) | caps (pooled direct slab memory = `file_cache_size` exactly at 48/96/192/512 MiB, 0 at 0 MiB; overflow unbounded) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** case file section D updated (2026-10-27, uncommitted). No section was amended by the result. The audit amendments U1–U3 and C1–C5 and the defect fix D1 are in the case file. The claim error S1 (8 MiB slab) is recorded in section D for stage 3. In `_INDEX-advisor.md` the §1 Stage 4 column and the §2 rows were filled.
