# file_cache_size-allocateMoreChunks-memoryUsageThreshold — stage-4 results  <!-- file: long-path/results/file_cache_size-allocateMoreChunks-memoryUsageThreshold.md -->

> **Case:** [`file_cache_size-allocateMoreChunks-memoryUsageThreshold`](../../stage3-ai-deep-read/cases/file_cache_size-allocateMoreChunks-memoryUsageThreshold--guided.md)
>
> **Status:** **Closed 2026-10-19 — all tiers verified at stage 4 (verdicts below).** verdict filed (2026-10-14) — **unit: Confirmed; cluster: Confirmed for the pool, §8 refuted in part** (the plateau is ⌊*T*/8 MiB⌋ × 8 MiB at 16 · 64 · 100 · 128 MiB and the node's direct memory does not move below the demand, but above it the pool fills to *T* under churn: at the default, 512 MiB reserved for a 250 MiB demand); no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `531c3ba` (the last commit touching the case file) plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash before the amendments `517b2b53f612a3a1fd246c0ca28a82cf50810f8e`; **after the amendments `6c8293ca9b45c67da0a4e96336a10d781c2fc960`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`); §9a alone `86831b868231977145d9770eb32da60c025b2cff`. §9a is frozen at this version. Recorded 2026-10-14 20:06 EDT, before any reading of this case existed (no earlier session ran it; `pc57:~/stage4-logs/` had no folder for it). One later dated correction to 9b/9d after the instrument shakedown, §9a unchanged (`86831b86…`): `P` read from the Byteman `made` trace, the INFO line's `8.000MiB`, the reader-demand check by `Hits` (§1.2); **§9 hash at run 1 `dd9734a886ff90ae9cda1b3e68322670ab776a53`**. |
| **Harness** | `../harness/file_cache_size-allocateMoreChunks-memoryUsageThreshold/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/fcs/`. |
| **Tiers and values** | Unit: upstream `BufferPoolTest`; harness `BufferPoolCeilingTest`, pools of 16 · 20 · 64 · 100 MiB. Cluster (one node on `pc57`, RF 1, one lifetime per value, dataset built once): `file_cache_size` 16 · 64 · 100 · 128 MiB and the default (512 MiB at `MAX_HEAP_SIZE=4G`), scenario A (*C* = 4) and B (*C* = 200) at every value. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Pooled direct bytes of the `chunk-cache` `BufferPool` (`memoryAllocated`), against the node's direct memory (§8, 9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 16 · 64 · 100 · 128 MiB and the default, restart per value (`static final` path, §4; 9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | NMT `Other` and `java.nio` direct `MemoryUsed` beside `Size`/`OverflowSize` (9d). |
| A. Core question | usage driven to the limit and past it | **Not met** | As written the load cannot reach even 16 MiB: stress's `standard1` has no clustering column, so a read takes the names-filter path and touches **one** SSTable, closing each reader before the next (`SinglePartitionReadCommand.java:700-707`, `:951-1046`, stop at `:986-989`); and `concurrent_reads: 32` bounds reads in flight regardless of `threads=512` (`AbstractReadExecutor.java:165`). Demand ≈ 32 × 16 KiB ≈ 0.5 MiB, not 160 MiB (rec. 1). |
| B. Logic | each step says what it establishes | Met | §9a "How this verifies", Logic (1)–(4). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | The plateau `⌊T/M⌋ × M` is exact; `D` was an estimate, so `O` and the total had no number a reading could miss (rec. 2). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows for over-threshold, not following, refusal seen by a caller, overflow below the ceiling, never reached, OOM; §8 refuted has its own row. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau per value + the INFO line, `Misses` and `O > 0`. The INFO line is weaker than the text says: the `NoSpamLogger` is static, keyed by the message, 15 min (`BufferPool.java:135`), so at most one line per lifetime; a Byteman counter on the branch is added (rec. 3). |
| B. Logic | alternative explanations and their controls | Met | Idle floor (networking pool, Netty), oversize requests (`:910`, 9a row), OOM fallback (row and `MaxDirectMemorySize=8G`), default arm as the unsaturated control. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | It needed the read path re-derived (rec. 1); the sampler as specified starts one JVM per gauge (`nodetool sjk` per call), which cannot read `Size` and `OverflowSize` within one second (rec. 4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Fine once the workload is replaced; 9e skipped A at 16 MiB, which the new `D_A` makes unnecessary (rec. 5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `jcmd`, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built, Byteman 4.0.20, the bundled Python driver 3.29.0; 32 cores, 251 GiB RAM, 51 GB free on `/`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Not met → Met after rec. 1 | New workload: 20 SSTables × 2,000 partitions × 4 KiB = 165 MB on disk; `D_B` = 200 reads × 20 readers × 64 KiB = 250 MiB > 128 MiB and < 512 MiB (default unsaturated); 8 GiB direct limit not near; about 5 min per value. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `Config.java:493-497`; `DatabaseDescriptor.java:573-577`, `:3784-3793`; `BufferPools.java:38-55`; `BufferPool.java:128-135` (sizes, the static `NoSpamLogger`), `:143-159`, `:187-196`, `:206-247` (`get`, `tryGet`, `allocate`, `put`), `:274-301`, `:375-482` (`GlobalPool`, `MACRO_CHUNK_SIZE` = 8 MiB with the stale "1 MiB" comment at `:384`, `getInternal` `:417-432`, the check `:443`, CAS `:452`, allocation `:460`, OOM `:462-468`), `:764-958` (`LocalPool`: `put` releases a fully-free owned chunk to the global pool `:839-858`; `get` falls back to `allocate` `:904-924`; `tryGet` marks `Misses` `:940-955`), `:1095-1110` (`allocateDirectAligned` = capacity + one page), `:1628-1634` (`unsafeReset`, the only reset of `memoryAllocated`); `BufferPoolMetrics.java:40-66`; `ChunkCache.java:50-54`, `CassandraRelevantProperties.java:227`; `BufferManagingRebufferer.java:42-54`; `CompressedChunkReader.java:81-96`; `FileHandle.java:390-430`; `Config.java:122`, `:179`, `:283`; `SinglePartitionReadCommand.java:679-850`, `:907-930`, `:951-1060`; `UnfilteredRowIterators.java:130-150`, `:398-541`; `AbstractReadExecutor.java:165`; `LZ4Compressor.java:240-243`; `ThreadLocalByteBufferHolder.java:77`. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | Replace the workload: a clustering table read by slice (merge path, every SSTable's reader open at once), *c* = 64 KiB chunks, `concurrent_reads` and `native_transport_max_threads` 256, a 500 ms Byteman hold at `UnfilteredRowMergeIterator.close()` so `D` = *C* · *k* · *c*; 20 SSTables of 2,000 partitions. | Applied 2026-10-14 (9b and 9c amendments); uncommitted | As written the load wants ≈ 0.5 MiB at once and the run would be invalid at every value. |
| 2 | State `D_A`, `D_B`, `O_peak`, the total and the direct-memory rise as numbers and bands. | Applied 2026-10-14 (9a Prediction, last bullet) | So that a reading can contradict the total and §8's claim, not only the plateau. |
| 3 | Byteman counters for refusals, macro chunks created and overflow allocations (chunk-cache only); the INFO line expected exactly once per lifetime. | Applied 2026-10-14 (9c, 9d amendments) | The rate-limited INFO line confirms but cannot count. |
| 4 | One in-JVM JMX sampler (all gauges per row, 1 s) instead of `nodetool sjk` per gauge; `java.nio` direct `MemoryUsed` beside NMT. | Applied 2026-10-14 (9c, 9d amendments) | `P` must not be a difference of two moments; NMT costs a JVM start per reading. |
| 5 | Run A at every value; add 100 MiB to the unit sizes; assert `Misses`/`Hits` and the unreleased reservation in the unit steps; the cluster run order. | Applied 2026-10-14 (9e amendments) | Completes the steps; the unit tier then covers the cluster tier's non-multiple value. |
| 6 | §7 "Lifetime / release" and §11 third note: `memoryAllocated` is never decremented (macro chunks "are never released", `:378`; only `unsafeReset()` resets it), and an OOM at `:460` leaves it bumped (the CAS at `:452` comes first). | Recorded in 9d's amendment; **left for stage 3** to correct §7 and §11 | Not load-bearing: the OOM case is an invalid-run row, and the plateau prediction is unaffected. |
| 7 | §5's "Escape hatch" paragraph: the OOM message says buffers "will be allocated in on-heap memory", but the fallback at `:923` is `allocateDirect` (off-heap). | Left for stage 3 | A misleading upstream log message; worth an upstream note beside the stale "1 MiB" comment. |
| 8 | §6b "Note the log is suppressed … `NoSpamLogger` rate-limits it": the interval is 15 minutes and the logger is static (shared by both pools, one statement per message), so the line is at most once per 15 min per JVM. | Left for stage 3 (stated in 9d's amendment) | Precision only. |

### 1.2 Instrument checks (not readings)

- **Unit harness:** compiled with `javac` against the clone's classpath before the run (20:11); its consistency checks run inside the
  counted unit run (§4).
- **Byteman:** `TestScript` first rejected `if { }` blocks and then void ternaries in the actions (Byteman has neither); each counter
  became a counting rule plus a conditional trace rule. Then `TestScript: no errors` for all eight rules (re-run by `cluster-run.py`
  before every start, `testscript.txt`); `Submit -l` lists all eight on the node. The outer-instance access `$0.this$0.name` type-checks.
- **Dataset build** (`cluster-run.py build`, 20:12–20:14, `pc57:~/stage4-logs/fcs/build/`): 20 `-Data.db` files, `ks1` 167,072,516 B
  on disk, `DESCRIBE` shows `'chunk_length_in_kb': '64'`; each pass 2,000 partitions × 4 rows in about 0.8 s. The default resolved to
  512 MiB (startup line `Global buffer pool limit is 512.000MiB for chunk-cache and 128.000MiB for networking`). The JVM command line
  carries `-XX:MaxDirectMemorySize` twice, the shipped `15872M` and then ours, `8G`; HotSpot takes the last.
- **Shakedown 1** (`cluster-run.py instrument`, 20:14–20:16, `pc57:~/stage4-logs/fcs/instrument-1/`), at 16 MiB. Three harness
  defects, none touching §9a: (1) the INFO regex expected `8MiB`, the line prints `8.000MiB`; (2) the sampler's `Size − OverflowSize`
  read 17.1 MiB at a 16 MiB pool: under load `OverflowSize` moves between the two `getAttribute` calls, so the exact `P` is taken from
  the `made` trace lines (8 MiB per line) and the sampler figure is kept as an approximate cross-check; (3) the reader-demand check
  ("`Size` in A above idle") cannot hold at 16 MiB, because start-up already took both macro chunks (both `made` lines are from start-up,
  while the SSTables are opened), so it became "`Hits` in A ≥ 0.9 × 20 × reads". The case's 9b/9d were corrected (dated, §9 hash now
  `dd9734a8…`, §9a still `86831b86…`). Also seen: NMT `Other` rose by about 1 GB in B while `java.nio` direct `MemoryUsed` rose by
  255 MiB — `Other` holds native memory the JDK's direct-buffer count does not see (inferred: Netty's pooled direct arenas, allocated
  without a `Cleaner`). §9a was **not** changed for this; the frozen NMT clause is judged at the end.
- **Shakedown 2** (20:17–20:19, `pc57:~/stage4-logs/fcs/instrument/`): `INSTRUMENT CHECK PASSED` — 20 SSTables per read at every
  percentile, `Hits` +3,060 in A for 156 reads (3,120 buffers), `O` > 0 at +1.9 s into B, refusals and overflow allocations counted,
  198 reads held at once, NMT parses, every read returned 4 rows. `P` (trace) 16 MiB in B; the sampler's figure reached 30.7 MiB,
  confirming defect (2).
- The repository folder and the node copy `~/stage4-harness-run/fcs/` are byte-identical (`md5sum`, 20:19). md5s:
  `BufferPoolCeilingTest.java` `6be998d6`, `cluster-run.py` `22d85736`, `hold.btm` `6b6160ec`, `make-node-yaml.sh` `955a5fe6`,
  `PoolSampler.java` `21eec4ab`, `README.md` `31477ae5`, `send-cql.py` `a16ad4aa`, `unit-run.sh` `b7c95259`. The chain script
  `~/stage4-harness-run/fcs-chain.sh` runs the five values in order, then `compare`.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-14, 20:11–20:47 EDT (supplementary lifetime 20:48–20:54) | not done |
| Node (CloudLab name and type) | `pc57` (`node0.jason92-319347`), 32 cores, 251 GiB; this session runs on it | |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`); `BufferPoolCeilingTest.java` copied in, untracked | |
| Case-file commit / harness commit | base `531c3ba` + uncommitted amendments (§1) / uncommitted (§1) | |
| Storage for node data | local `/dev/sda3` (`~/cassandra-run1/data`), 54 GB free | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/fcs/` (`unit/`, `build/`, `instrument-1/`, `instrument/`, `run1/<value>/`, `chain.log`) | |

## 3. Runbook defects

None in run 1: every step ran as written. The three harness defects found by shakedown 1, before any reading, are in §1.2 (fixed in
the harness; the case's 9b/9d corrected, §9a unchanged).

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| — | — | — | none | — | — | — |

## 4. Run 1

**Scope:** unit tier (upstream `BufferPoolTest`, harness `BufferPoolCeilingTest` at 16 · 20 · 64 · 100 MiB); cluster tier at
`file_cache_size` 16 · 64 · 100 · 128 MiB and the default, one node lifetime each, idle → A (*C* = 4, 30 s) → B (*C* = 200, 150 s) →
after, chained 20:19:58–20:47:44 (`run1/cluster/chain.log`). Plus one **supplementary diagnostic lifetime** at the default
(20:48–20:54, `hold.btm` + `netty-probe.btm`, its own log root), not part of §9a's readings. **Command log:** `run1/unit/unit-run.txt`;
per value `run1/cluster/<v>/summary.txt` (every `EXPECTED:` line), raw `samples.csv`, `phases.csv`, `nmt.csv`, `bm.trace.excerpt`
(every `made`, `dump` and `hold` line), `system.excerpt.log`, `client.excerpt.log`; full logs `pc57:~/stage4-logs/fcs/`.

### 4.1 Readings

**Unit tier**

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `BufferPoolTest` (pool 8 MiB; `testMaxMemoryExceeded*`) | 38 tests, 0 failures, 0 errors | `run1/unit/unit-run.txt`, `TEST-…BufferPoolTest.xml` |
| `BufferPoolCeilingTest`, 96 checks | 4 tests, **96 checks, 0 mismatches** | `run1/unit/harness.out` |
| Step 1: pooled at the ceiling, overflow 0 | 16 → 16,777,216 · 20 → 16,777,216 · 64 → 67,108,864 · 100 → **100,663,296 (96 MiB)**; 128 · 128 · 512 · 768 hits | `harness.out` (`1-ceiling`) |
| Step 2: five more, each non-null and direct | overflow 655,360 B (5 × 128 KiB), pooled unchanged, `Misses` +5, `Hits` unchanged, at every size | `harness.out` (`2-past`) |
| Step 3: `tryGet(128 KiB)` | `null`, `Misses` +1 | `harness.out` |
| Steps 4–5: buffers back | overflow 0; pooled reservation unchanged (16 · 16 · 64 · 96 MiB), used 0; the next `get` is served without a new macro chunk | `harness.out` (`5-all-back`, `6-reuse`) |

**Cluster tier** — `P` = 8 MiB × the `made` lines (§1.2); `O` = `OverflowSize` peak; rises are over the idle control's median
(`java.nio` direct `MemoryUsed`) or idle NMT reading. Every value: `Capacity` and the startup line equal *T*; 20 SSTables per read at
50 · 95 · 99 % and max; 198–199 reads held at once in B; every read (236 in A, 50–53 k in B) returned 4 rows; no OOM line, no ERROR line.

| Value | P idle | P after A | P in B (every sample after the first `O` > 0) | `O` peak | `P + O` peak | direct rise | NMT `Other` rise | refusals / overflow allocations in B | `Misses` in B | INFO lines | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 MiB | 8 | 16 | **16** (first `O` at +2.4 s, 150.9 s after) | 234.31 MiB | 250.31 | 263.47 MiB | 1,079.4 MiB | 947,479 / 933,145 (61,154,590,720 B = *n* × 65,536) | +933,145 | 1 | `run1/cluster/16/` |
| 64 MiB | 8 | 64 | **64** (+2.4 s, 150.9 s) | 187.38 | 251.38 | 263.93 | 1,063.5 | 817,138 / 739,111 | +739,111 | 1 | `…/64/` |
| 100 MiB | 8 | 96 | **96** (+2.4 s, 150.9 s) | 154.81 | 250.81 | 262.65 | 1,078.0 | 746,676 / 618,779 | +618,779 | 1 | `…/100/` |
| 128 MiB | 8 | 128 | **128** (+2.4 s, 150.9 s) | 122.44 | 250.44 | 262.15 | 1,078.4 | 679,439 / 499,427 | +499,427 | 1 | `…/128/` |
| default (512 MiB) | 8 | 216 | **512** (64 macro chunks; `O` never > 0) | 0 | 512.0 | **524.90** | 1,340.9 | 372,244 / **0** | 0 | 1 (`512.000MiB`, at 00:44:25 UTC, in B) | `…/default/` |

After B, at every value: `O` = 0 and `P` unchanged (trace and sampler agree once the load stops). Overflow bytes equal 65,536 × the
overflow count at every saturated value, so every overflow buffer is a 64 KiB reader buffer (no oversize request). Across values
(`run1/cluster/compare.txt`): plateau 16 · 64 · 96 · 128 MiB; `P + O` peak spread **1.06 MiB**; direct rise spread over the four
saturated values **1.78 MiB**, over all five **262.75 MiB**; NMT `Other` rise spread 15.9 MiB over the four, 277.4 MiB over all five.

**Supplementary lifetime at the default** (`run1/supplementary/`): repeats the default arm (`P` after A 208 MiB, in B 512 MiB, `O` 0,
370,740 refusals, direct rise 523.47 MiB) and adds two counts. **Recycles** of chunk-cache normal chunks: in A 718 full, **1,652
partial**; in B 158,611 full, **370,069 partial** (`GlobalPool.recycle()` vs `recyclePartially()`). **Netty** no-cleaner direct memory
(`PlatformDependent.usedDirectMemory()`): 224 MiB idle, 288 MiB after A, **1,040 MiB** after B (+816 MiB, 64 direct arenas);
`PooledByteBufAllocator.DEFAULT` itself 16 MiB throughout.

### 4.2 Conclusion and logic

1. **Validity** — valid. The limit was reached and passed at 16 · 64 · 100 · 128 MiB (`O` > 0 from +2.4 s, 150.9 s of B after it)
   [observed: `run1/cluster/<v>/summary.txt`]. Hold-fixed settings: `MAX_HEAP_SIZE=4G` and `MaxDirectMemorySize=8G` (last of two flags),
   NMT summary [observed: `summary.txt` "JVM flags"]; `concurrent_reads` and `native_transport_max_threads` 256 and the `file_cache_size`
   line [observed: yaml diff in `summary.txt`]; chunk cache off (default property; `ChunkCache` would log its own size, absent)
   [inferred: no `-Dcassandra.file_cache_enabled` on the command line]; heap memtables (shipped yaml); dataset 20 SSTables, 64 KiB chunks,
   reads only, compaction disabled [observed: `instrument/build-summary.txt`, 20 SSTables per read in every `tablehistograms.txt`]; the
   demand *C* · *k* · *c*: 198–199 reads held, *k* = 20 [observed: `bm.trace.excerpt` `hold` lines, `tablehistograms.txt`]. No OOM
   fallback [observed: `system.excerpt.log`].
2. **Readings** — (a) Scenario A raised `P` to the ceiling at 64 · 100 · 128 MiB and to 216 MiB at the default, against `D_A` = 5 MiB,
   with `O` = 0: the frozen "A: `P` ≤ 16 MiB" missed at four values. (b) At the default `P` reached the full 512 MiB in B, not 248–264 MiB,
   with 372,244 refusals and the INFO line — the frozen default bullet missed on `P`, refusals and the INFO line; it held on `O` = 0 and
   no overflow allocation. (c) NMT `Other` rose by about 1.07 GB at every saturated value, far above the direct rise (the frozen NMT
   clauses missed). All three are explained by observed mechanisms, part 5.
3. **Matched row** — "`P` and the ceiling as above, but native memory over idle falls as *T* falls (beyond the 25 % band) → **Confirmed
   for the pool; §8 refuted**". The pool part: `P` plateaus at exactly ⌊*T*/*M*⌋ × *M* (16 · 64 · 96 · 128 MiB) at every sample after the
   first `O` > 0, never above *T* in any lifetime, moving with *T* in 8 MiB steps (100 MiB → 96) [observed: `made` lines]; `Capacity` = *T*;
   the disallow branch fired, by three independent signs: refusals counted at `allocateMoreChunks()` exit, overflow allocations at
   `BufferPool.allocate()` equal to `Misses`, and the INFO line once [observed: `bm.trace.excerpt` dumps, `samples.csv`,
   `system.excerpt.log`]. The native-memory part: the direct rise falls from 524.9 MiB at the default to 262–264 MiB at 128 MiB and below,
   a fall of 262.75 MiB, beyond the 28 MiB band [observed: `samples.csv`]. The row asks to check that the overflow is not released
   earlier: it is not — the fall is in `P` (512 → 128 MiB), not in `O` (0 at the default) [observed].
   **But §8 is refuted only above the demand:** across 16 · 64 · 100 · 128 MiB the total `P + O` stays within 1.06 MiB and the direct rise
   within 1.78 MiB while `P` changes by 112 MiB [observed] — there the knob moves bytes between pooled and overflow and the memory does
   not follow it, exactly as §8 says.
4. **Excluded rows** — *Confirmed incl. §8*: the direct rise is not flat across the sweep (262.75 MiB spread). *Refuted, `P` passes the
   threshold*: `made` × 8 MiB ≤ *T* in every lifetime. *Refuted, `P` does not move with T*: 16 → 64 → 96 → 128. *Not confirmed, readers block
   or error*: `O` > 0 and every read returned 4 rows. *Not confirmed, `O` > 0 below the ceiling*: at every sample after the first `O` > 0,
   `P` equals the ceiling; overflow bytes = 65,536 × count (no oversize request); no OOM line. *Invalid, never reached*: reached at four
   values. *Invalid, OOM*: no `failed to allocate chunk` line.
5. **Observed vs. inferred** — The conclusion's load-bearing extra statement is **why the pool fills to *T* when the demand is below it**,
   now observed: reading `BufferPool.java`, an evicted normal chunk freed part-way goes to `partiallyFreedChunks` (`tryRecycleFullyOrPartially`,
   `:1272-1281`) and is no longer `EVICTED`, so it is not recycled again when it becomes fully free (`:1244-1245`); `getInternal()`
   takes `chunks`, then a **new macro chunk**, and only after a refusal `partiallyFreedChunks` (`:419-431`). The supplementary lifetime
   counted 370,069 partial recycles against 158,611 full in B, and 1,652 against 718 in A [observed: `supplementary/bm.trace.excerpt`];
   at 16 MiB, A logged 1,537 refusals with no overflow, i.e. refusals served from that queue [observed: `cluster/16/summary.txt`]. The
   reads here need 10 normal chunks per thread against a 3-slot local queue, so evictions are certain; a load whose buffers fit in three
   chunks per thread might not fill the pool [inferred: not tested]. NMT `Other` = `java.nio` direct + Netty's no-cleaner arenas
   [observed: supplementary, 523.5 + 816 ≈ 1,339.5 MiB]; Netty's share is set by the 200 concurrent requests, not by *T* (flat to 16 MiB
   across the saturated values) [observed].
6. **Deviations and gaps** — The workload was replaced at the audit (§1.1); `P` is read from the `made` trace, not from `Size − OverflowSize`
   (§1.2). One run per value (no repeat), but the default arm, the one carrying the refutation, was repeated in the supplementary lifetime
   with the same result (512 MiB, direct rise 523.5 MiB). The cluster read the direct memory the node *holds*, which for the pool is
   reservation (the macro chunks are never freed); the RSS was not read (the case's rule). The demand was set by a Byteman hold; real reads
   would produce a lower, noisier `D`, which changes where the crossover sits, not the mechanism.
7. **Core question** — Following §9a's Logic: (1) the load exceeded the pool at every value but the default (part 1); (2) pooled bytes
   stop at the quantised limit while the overflow takes the rest, and the disallow branch fired (part 3); (3) the plateau follows *T* in
   8 MiB steps (part 3); (4) the total is flat **only below the demand** (part 3) — above it the pool fills to *T* under churn (part 5).
   So `file_cache_size` caps the pool exactly, and usage of the pool follows it; it caps the node's direct memory for these reads only
   when it is the larger of the two, giving **direct memory ≈ max(⌊*T*/8 MiB⌋ × 8 MiB, `D`)**: lowering it below the demand saves
   nothing, lowering it from above the demand towards it saves memory one-for-one.

**Conclusion (one line):** "`P` and the ceiling as above, but native memory over idle falls as *T* falls" — **Confirmed for the pool;
§8 refuted above the demand** (it holds below it); sub-predictions for A, the default arm's `P`, and NMT missed, causes observed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` re-parses the raw files (it does not import `cluster-run.py`) and prints `run1/selfcheck.txt`: **83 checks hold,
10 fail**. The 10 are exactly the frozen relations reported as missed in §4.2 part 2 (A `P` ≤ 16 MiB at 64 · 100 · 128 · default; the
default's `P` band, refusal/INFO absence; the direct-rise and two NMT spreads) — the same lines the run script marked `NO`. Every
agreement check (C15: its own `O` peak, `P`, direct rise, refusals, overflow and NMT figures equal `result.json`) holds at all five
values. Run on the node's full logs and on the repository excerpts (`selfcheck.py cluster unit`) it prints the same output, byte for byte.

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `summary.txt` JVM flags and yaml diffs, `tablehistograms.txt` (20 at every percentile), `hold` lines (max 198–199), `system.excerpt.log` (no OOM, no ERROR), C1/C2/C4/C6/C14. |
| 2. Readings | yes | C3 and C7/C8/C11 (default), X3–X5 reproduce each miss with the same figures. |
| 3. Matched row | yes | C5/C7 (`P` = ceiling after the first `O`, never above *T*), C10 (refusals, overflow = `Misses`, bytes = 65,536 × *n*), C11 (one INFO line naming `chunk-cache` and `8.000MiB`), X1 (plateau), X2 (`P + O` spread 1.06 MiB), X3 (direct rise 263.47 · 263.93 · 262.65 · 262.15 · 524.9 MiB). |
| 4. Excluded rows | yes | As part 4; C9 (`P + O` in [225, 266] MiB) and C13 (after B) also hold. |
| 5. Observed vs. inferred | yes | `supplementary/bm.trace.excerpt` re-read: `recycle full=159526 partial=371721` at B's end against `full=915 partial=1652` at A's end; `netty used_nocleaner` 234,881,024 → 1,090,519,040. Code citations re-read at the tag. The one inferred statement (a load fitting three chunks per thread may not fill the pool) is marked and not used for the verdict. |
| 6. Deviations and gaps | yes | — |
| 7. Core question | yes | The answer follows §9a's four Logic steps; step 4 splits at the demand, which is what the matched row and the flat saturated band show together. |

### 5.2 Run 2?

**No** — 2026-10-14. The result refutes part of §8, which is the case for a run 2, but the refuting arm (the default) was repeated in
an independent lifetime with the same figures (512 MiB, 523.5 vs 524.9 MiB), the mechanism is read in the source and counted
(partial recycles), and every figure was re-derived from raw files by the self-check. A fresh-session run 2 remains available if
Jingsong wants independent insurance.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

| Tier | Verdict (§9a row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — the pool stops at ⌊*T*/8 MiB⌋ × 8 MiB (16 · 16 · 64 · 96 MiB at 16 · 20 · 64 · 100 MiB), every request past it is served directly and counted as overflow, `tryGet` sees the refusal, the reservation is kept after release | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed for the pool; §8 refuted above the demand** (row 2) — plateau 16 · 64 · 96 · 128 MiB, disallow branch fired three ways, total and direct memory flat (spread ≤ 1.8 MiB) while *T* < `D`; at the default the pool filled to 512 MiB for a 250 MiB demand (direct rise 524.9 vs 262–264 MiB) through partial recycling | run 1 + self-check (+ supplementary lifetime) | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" (uncommitted), including the §8 amendment recommended to stage 3 and the
notes of §1.1 recs. 6–8; §8 itself is left for stage 3 to rewrite.
