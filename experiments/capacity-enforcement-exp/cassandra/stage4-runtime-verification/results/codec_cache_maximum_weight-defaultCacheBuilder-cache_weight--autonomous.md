# codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous — stage-4 results  <!-- file: results/codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous.md; written outside the repo at ~/writeup-ext/out/o96/results.md -->

> **Case:** [`codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous`](../../stage3-ai-deep-read/cases/codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous.md) (stage-3 extension set, order 96, band B; the amended copy used by this run is `~/writeup-ext/out/o96/case-amended.md`, outside the repo)
>
> **Status:** verdict filed (2026-11-25). Run 1 is done at both tiers (with the optional cluster step 7, cap 100) and self-checked; there is no run 2.
>
> **Outcome class:** **true negative** (estimate `negative`, effect `does not cap` at both tiers). See the [definition](../../../stage4-runtime-verification/README.md#outcome-class).
>
> **Agent:** autonomous (the suffix of the case-file stem). Below, "§9a" means each tier's predictions and conclusions table: B2f and B2g for the unit tier, and B3f and B3g for the cluster tier, read with the audit amendments B2i and B3i. "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D. The run was done as Jingsong, on node `pc72` (x86_64).

## 1. Before run 1: design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Case file `experiments/capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/codec_cache_maximum_weight-defaultCacheBuilder-cache_weight--autonomous.md` at repository HEAD `cd9e1cded`, sha256 as filed `ba9b11132b08c0b24318ef4221bf29980011532538c84323afe662ccef10dc46` (matches `_INDEX.md` §4; copy `harness/freeze/case-as-filed.md`). **Freeze 1** (before unit run 1, 2026-11-25T05:02Z, amendments S4-A1 to S4-A9): sha256 `0d889c09ef9c6d6513726f8175300660d93dee4e73abf99186590647651df4a1` (`harness/freeze/case-frozen.md`). **Freeze 2** (before cluster run 1, 2026-11-25T05:04Z, adds S4-A10 to B3i after the throwaway-node shakedown; B2 and every prediction and row unchanged): sha256 `5e1d073f0cfed803090eb67a3173420325f19576e9318a541f5e00817d2e3ee0` (`harness/freeze/case-frozen-2.md`), the frozen version and the sha256 for `_INDEX.md`. The amended file is written to `~/writeup-ext/out/o96/case-amended.md`; the repository was not edited. |
| **Harness** | `~/writeup-ext/out/o96/harness/` (outside the repo, not committed): `CodecCacheWeightProbeTest.java` (the B2a skeleton verbatim plus `@SuppressWarnings`), `unit-run.sh`, `unit-analyze.py`, `mkyaml.py`, `gen-cql.py`, `cluster-run.sh`, `cluster-analyze.py`, `freeze/`. Copied to the node as `/mydata/jingsong-cass-s4/o96/harness/`. Instrument checks: unit known-answer run `narrow` K=500 gave `size=500 weight=500` (`raw/unit/ant-smoke-narrow-k500.log` on the node, tokens reassembled); cluster shakedown on a throwaway node dir (5 functions, then deleted) showed the UDFs are created and found the S4-D2 instrument defect; a second shakedown confirmed `CodecRegistry$CacheKey` = `StrongValueReference` = 5 for 5 weight-1 entries. |
| **Tiers and values** | Unit (B2): patched copy, `cassandra.test.codec_cache_max_weight` ∈ {100, 1000 (property unset = stock), 10000}; W-A K ∈ {500, 1000, 2000, 5000} (and 2000 at cap 100, 12000 at cap 10000); W-B (440 zero-weight + 5000 weight-1); W-C M ∈ {1, 1000, 10000} at K=2000 (and M=1000 at caps 100 and 10000); 3 repetitions per cell. Cluster (B3): one stock node (cap 1000, not settable), N ∈ {500, 2000, 4000} narrow UDFs then dropped; wide UDFs K=1500 at M=1 and M=2000, each dropped; optional step 7 run: patched jar (`$WORK/unit`), `JVM_EXTRA_OPTS=-Dcassandra.test.codec_cache_max_weight=100`, N ∈ {500, 2000, 4000} then dropped. |
| **Audit bottom line** | **Ready after amendments**, 2026-11-25 (S4-A1 to S4-A10 applied before the freeze of each tier; none changes B1, a prediction or a conclusions row) |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: the claimed resource is on-heap bytes retained by the codec cache; the limit's own unit is abstract weight (type nesting), and the design measures bytes (B2d `deepBytes`, B3d heap after GC), which is the point of the claim. |
| A. Core question | knob varied, ≥ 3 values incl. default, or another approach | Met (unit) / Partly (cluster) | A1: a literal, not settable. Unit: a one-line patch reads a `-D` property with default 1000, values 100/1000/10000 (B2a, B2b). Cluster: stock 1000 only, the load is varied past it (N 500/2000/4000; M 1/2000); the patched cap=100 re-run is optional (B3b, B3e step 7). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: jamm `measureDeep(registry)` and `heapUsed` beside `size`/`weight` (B2d). Cluster: live class histogram and heap after full GC (B3d). Gap named: the cache's weight sum is not observable on the node (B3d). |
| A. Core question | usage driven to the limit and past it | Met | W-A K up to 5× the cap, 12000 at cap 10000; W-C 2×; cluster N to 4× and K=1500 (1.5×) (B2c, B3c). |
| A. Core question | positive control for a negative claim | Met (unit) / Partly (cluster) | Unit: the knob runs move `size`/`weight` and bytes with the cap on the same workload (B2e step 3, B2g row 3). Cluster: the entry count plateauing at the cap while the workload moves heap (B3g row 1); the cap=100 re-run is optional. |
| B. Logic | each step says what it establishes | Met | B1, B2c, B2h, B3c, B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met after S4-A4, S4-A8 | B2f and B3f give numbers; "≈", "plateau", "no knee" were given numeric rules before any reading. |
| B. Logic | every plausible outcome has a conclusions row | Met | B2g/B3g: bytes not following the cap (confirmed), bytes ∝ weight and plateau with the knob (refuted), never plateaus, positive control did not move, limit never reached, workload not applied. A reading between the bands of S4-A8 → not confirmed. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The disallow branch (eviction) is evidenced by `size` stopping at the cap with K > cap (unit) and by the cache-held remainder after drops (cluster). |
| B. Logic | alternative explanations and their controls | Met | B2h/B3h: empty-registry baseline, the real private weigher, `cleanUp()` before reading, same K across M, drop phases separating UDF-held from cache-held codecs. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, B1, B2f, B3f. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after S4-A2, S4-A10 | The PROBE line never appears as one line (S4-D1); the Guava class named for cache entries does not hold weight-1 entries (S4-D2). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after S4-A1, S4-A3, S4-A5 to S4-A7 | B2a/B3a assume `~/cassandra-5.0.9`; repetitions for the knob runs; yaml and sampling commands made exact. |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11.0.33, Ant 1.10.12 and a built 5.0.9 copy at `/mydata/s4/cassandra-base` on `pc72`; PyYAML 5.4.1; cqlsh from the copy. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit: ≤ 40 MB retained in the test JVM (default test heap). Cluster: ≈ 15 MB of schema text for M=2000, 1 GiB heap, 705 GB free on `/mydata`; 500 functions took 24 s. |
| D. Runnable | load-bearing citations spot-checked | Met, one finding | Checked in the 5.0.9 copy: `CodecRegistry.java:297-353` (weigher; vector, UDT, tuple min 1; primitives and shallow collections 0), `:382-406` (cache, builder, `maximumWeight(1000)` at L400), `:597-627` (built-ins bypass the cache); `JavaDriverUtils.java:37,60-63`; `UDFDataType.java:55-72` (`typeCodec` field set from `JavaDriverUtils.codecFor`); `UDFunction.java:219-220`; `TupleType.java:63-67`; `DataType.java:448`; `ProtocolVersion.CURRENT`; `build.xml:1159` (jamm agent), `:1192` (`test.jvm.args`), `:1384` (`test.methods`); `conf/cassandra.yaml:1760`. Finding: Guava 32.0.1 uses `WeightedStrongValueReference` only for weights ≠ 1 (S4-D2). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| S4-A1 | Unit paths: `cp -a /mydata/s4/cassandra-base $WORK/unit`, test package directory created | applied 2026-11-25 (B2i; outside the repo, no commit) | `~/cassandra-5.0.9` does not exist on the shared nodes |
| S4-A2 | Reassemble the PROBE line from the logger's tokens | applied 2026-11-25 (B2i) | S4-D1 |
| S4-A3 | 3 repetitions for every unit cell incl. knob runs | applied 2026-11-25 (B2i) | B2e step 3 did not say |
| S4-A4 | Numeric reading rules for B2f/B2g | applied 2026-11-25 (B2i) | "≈", "plateau" made contradictable before any reading |
| S4-A5 | Cluster paths, yaml by `mkyaml.py`, `ulimit -n`, port check | applied 2026-11-25 (B3i) | shared node layout; soft fd limit 1024 |
| S4-A6 | CQL generated by `gen-cql.py`, errors counted, function count after each file | applied 2026-11-25 (B3i) | exact workload record |
| S4-A7 | Exact sampling commands and parsed fields | applied 2026-11-25 (B3i) | B3d listed observables, not the parse |
| S4-A8 | Numeric reading rules for B3f/B3g (slopes, plateau, ±2 MB noise, ≥ +4 MB) | applied 2026-11-25 (B3i) | "knee", "≈" made contradictable before any reading |
| S4-A9 | Cap=100 re-run is run only if time allows; the results say whether | applied 2026-11-25 (B3i) | 3-hour cap |
| S4-A10 | Count cache entries by `CodecRegistry$CacheKey` (cross-checks `StrongValueReference`, `WeightedStrongValueReference`) | applied 2026-11-25 (B3i, freeze 2) | S4-D2 |
| R-a | Stage 3: A3/B3d should say that Guava holds weight-1 entries in `StrongValueReference` | left for stage 3 (section D note) | factual slip in the instrument choice |
| R-b | Stage 3: B2a/B3a should copy with `copy-source.sh` or from `cassandra-base`, not `rsync ~/cassandra-5.0.9` | left for stage 3 | portability |

**Agreement criteria:** not filled (no run 2).

## 2. Environment

| Field | Run 1 | Run 2 |
|---|---|---|
| Date | 2026-11-25 UTC: build 05:00; unit 05:02–05:11; cluster shakedowns 05:03–05:06; main 05:11–06:24; cap-100 re-run 06:24–06:41; node data deleted and lock released 06:43 | not done |
| Node (CloudLab name and type) | `pc72` = `node2.jason92-326665.misconfiguration-pg0.cloudlab.umass.edu` (UMass), **x86_64**, Intel Xeon E5-2660 v2 @ 2.20 GHz, 40 cores, 125 GiB RAM; node lock `/mydata/s4/NODE-LOCK` held for the whole run | |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-203-generic` | |
| JDK | openjdk 11.0.33 (11.0.33+9-post-1ubuntu1-22.04.1) | |
| Ant | Apache Ant 1.10.12 | |
| Local source copy | `/mydata/s4/cassandra-base` (a `copy-source.sh` copy of `systems/cassandra/source/`, tag `cassandra-5.0.9`, built 2026-11-17), copied with `cp -a` to `/mydata/jingsong-cass-s4/o96/unit` (patched, L400 only; `ant -Duse.jdk11=true jar build-test` 25 s, BUILD SUCCESSFUL, `logs/build-unit.log`) and `/mydata/jingsong-cass-s4/o96/node` (stock; jar checked with `javap`: `ldc2_w 1000l` before `maximumWeight`). `src/` and `test/` of the copy checked identical to the repository at `cd9e1cded` with `diff -rq` (only build-generated `gen-java` and `resources/.../config` differ). | |
| Case-file / harness commit | case file at `cd9e1cded` (as filed); amendments and harness outside the repo, uncommitted; hashes in §1 | |
| Storage for node data | `/mydata` (LVM `emulab-node2--bs`, ext4, 753 GB, 705 GB free); node data `/mydata/jingsong-cass-s4/o96/cdata/`; heap 1 GiB (`-Xms1G -Xmx1G`, G1) | |
| Full logs (outside the repo) | node: `/mydata/jingsong-cass-s4/o96/raw/{unit,cluster,...}/` and `logs/`; copy on the coordinating node: `~/writeup-ext/out/o96/raw/` | |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| S4-D1 | instrument check, unit | B2d/B2e | The unit-test JVM routes `System.out` through a logger that writes each `printf` argument as a separate log line (`SubstituteLogger.java:222 - PROBE `, `- A-empty`, `- size=`, `- 0`, ...), so `grep PROBE` finds no complete line in the console or the XML. | The run script joins the Standard Output tokens and splits at `PROBE ` (S4-A2); probe code unchanged. Found on the known-answer run, before run 1. | 2026-11-25 | outside the repo, no commit (B2i) |
| S4-D2 | shakedown, cluster | B3d | `LocalCache$WeightedStrongValueReference` holds only entries whose weight ≠ 1 (`LocalCache$Strength$1.referenceValue`, Guava 32.0.1); every B3c entry weighs 1, so the named class would read ≈ 0 whatever the cache did (shakedown: none after 5 functions). | Count `CodecRegistry$CacheKey` instead, with both reference classes as cross-checks (S4-A10); found on a throwaway node before cluster run 1; predictions and rows unchanged. | 2026-11-25 | outside the repo, no commit (B3i) |
No step of run 1 failed after the two fixes above (both found before the respective tier's run 1).

## 4. Run 1

**Scope:** unit tier, every B2b cell (3 repetitions); cluster tier, B3e steps 1–6 and 8 on the stock node, then the optional step 7 (patched jar, cap 100, steps 2–4) (run, 06:24–06:41). **Command logs:** `raw/unit/command.log`, `raw/cluster/command.log`, `raw/cluster-pc100/command.log` (paths relative to `/mydata/jingsong-cass-s4/o96/` on `pc72` and to `~/writeup-ext/out/o96/` on the coordinating node; histograms `h_*`, heap-info `hi_*` and `nodetool info` `ni_*` per sample are on the node only).

### 4.1 Readings

**Unit tier.** 36 runs (12 cells × 3 repetitions), each a fresh `ant testsome` JVM, all `Tests run: 1, Failures: 0, Errors: 0` and `BUILD SUCCESSFUL` (`raw/unit/command.log`). All three repetitions of every cell gave identical `size`, `weight` and `deepBytes`, so the median equals each reading. Full table: `raw/unit/analysis.txt`; per-run lines: `raw/unit/probe-<cell>-r<n>.txt`.

| Test or assertion | Result (median of 3; all 3 identical) | B2f prediction | Evidence (file) |
|---|---|---|---|
| Empty-registry baseline (every cell) | `size=0 weight=0 deepBytes=1880` | — | `probe-*-r*.txt` (`*-empty` lines) |
| W-A K=500, cap 1000 | size 500, weight 500, deepBytes 109,528 (219 B/entry) | 500 / 500 / baseline + 500 × 0.1–0.2 KB | `probe-A-cap1000-k500-r{1,2,3}.txt` |
| W-A K=1000, cap 1000 | size 987, weight 987, deepBytes 214,920 | 950–1000 / = size / 0.1–0.3 MB | `probe-A-cap1000-k1000-r*.txt` |
| W-A K=2000, cap 1000 | size 1000, weight 1000, deepBytes 217,624 | 1000 / 1000 / plateau | `probe-A-cap1000-k2000-r*.txt` |
| W-A K=5000, cap 1000 | size 1000, weight 1000, deepBytes 217,624 (= K=2000: plateau) | same as K=2000 ± 10 % | `probe-A-cap1000-k5000-r*.txt` |
| W-B zero-weight only | size 440, weight 0, deepBytes 155,984 | 440 / 0 / 0.1–0.3 MB | `probe-B-cap1000-r*.txt` |
| W-B + 5000 weight-1 vectors | size 1440, weight 1000, deepBytes 368,080; `list<int> still cached: true` (3/3) | 1440 / 1000 / zero-weight all present | `probe-B-cap1000-r*.txt` |
| W-C M=1, K=2000, cap 1000 | size 1000, weight 1000, deepBytes 241,576 (242 B/entry) | 1000 / 1000 / ≈ 0.2 MB | `probe-C-cap1000-m1-k2000-r*.txt` |
| W-C M=1000, K=2000, cap 1000 | size 1000, weight 1000, deepBytes 4,241,576 (4,242 B/entry) | 1000 / 1000 / ≈ 4 MB | `probe-C-cap1000-m1000-k2000-r*.txt` |
| W-C M=10000, K=2000, cap 1000 | size 1000, weight 1000, deepBytes 40,241,576 (40,242 B/entry); heapUsed 53.1 MB vs 13.3 MB at M=1 | 1000 / 1000 / ≈ 40 MB | `probe-C-cap1000-m10000-k2000-r*.txt` |
| W-C ratio M=10000 / M=1 at weight 1000 | **166.6×** (bytes per entry = 242 + 4.0 × M) | ≥ 100× confirms; ≤ 2× refutes | `analysis.txt` |
| Knob: W-A K=2000, cap 100 | size 100, weight 100, deepBytes 23,256 (0.107 × cap-1000 plateau) | 100 / 100 / ≈ 1/10 | `probe-A-cap100-k2000-r*.txt` |
| Knob: W-A K=12000, cap 10000 | size 10000, weight 10000, deepBytes 2,146,968 (9.87 ×) | 10000 / 10000 / ≈ 10× | `probe-A-cap10000-k12000-r*.txt` |
| Knob: W-C M=1000, cap 100 | size 100, weight 100, deepBytes 425,608 | 100 / 100 / ≈ 0.4 MB | `probe-C-cap100-m1000-k2000-r*.txt` |
| Knob: W-C M=1000, cap 10000 (K=2000 < cap) | size 2000, weight 2000, deepBytes 8,481,768 | 2000 / 2000 / ≈ 8 MB | `probe-C-cap10000-m1000-k2000-r*.txt` |
| Bytes per weight unit | M=1: 242 B; M=1000: 4,256 / 4,242 / 4,241 B at caps 100 / 1000 / 10000; M=10000: 40,242 B | — | `analysis.txt` |

**Cluster tier, stock node (cap 1000).** Medians of 3 samples per checkpoint, Δ from `base` (no UDF). Every create and drop file ran with `cqlsh` rc 0 and 0 error lines, and the function count after each file was exactly the intended one (500, 2000, 4000, 0, 1500, 0, 1500, 0). `system.log`: 0 `ERROR` lines, 5 start-up `WARN`s. Heap peak (after GC) 186 MB of 1 GiB. Full table: `raw/cluster/analysis.txt`; per-sample lines: `raw/cluster/readings.txt`.

| Capacity value | Run | Observable (B3d, S4-A10) | Reading | Evidence (file) |
|---|---|---|---|---|
| 1000 (stock) | base | heap after GC; live bytes (histogram Total) | 63.3 MB; 63.2 MB; CacheKey 0, codecs 0 | `readings.txt` (`tag=base`) |
| 1000 | n500 | ΔCacheKey / ΔStrongValueReference / ΔVectorCodec$FixedLength | 500 / 500 / 500 | `readings.txt` (`tag=n500`) |
| 1000 | n2000 | same | **1000** / 1000 / **2000** | `tag=n2000` |
| 1000 | n4000 | same | **1000** / 1000 / **4000** | `tag=n4000` |
| 1000 | n500 / n2000 / n4000 | Δheap after GC (spread of 3) | +10.7 (0.1) / +25.2 (2.4) / +41.8 (0.0) MB; segment rises 10.7, 14.5, 16.6 MB; slopes s0 21.9, s1 9.9, s2 8.5 KB per function (s1 = 0.45·s0, s2 = 0.39·s0) | `analysis.txt` |
| 1000 | ndrop | ΔVectorCodec / ΔCacheKey; Δheap | **1000** / 1000; +58.9 MB (UDFDataType −8000, JavaBasedUDFunction −4000 vs n4000; growth in `[B`, `HeapByteBuffer`, `BufferCell`, `BTreePartitionData`) | `tag=ndrop`; `h_n4000_2.txt` vs `h_ndrop_2.txt` |
| 1000 | w1 | ΔVectorCodec / ΔTupleCodec / ΔCacheKey | **0** (the 1000 cached vector codecs evicted by the new tuple entries) / 1500 / 1000 | `tag=w1` |
| 1000 | w1drop | ΔTupleCodec / ΔTupleType / ΔCacheKey; Δ`[Object;` | 1000 / 1000 / 1000; +6.1 MB | `tag=w1drop` |
| 1000 | w2000 | ΔTupleCodec / ΔCacheKey; Δ`[Object;`; Δheap | 1500 / 1000; +45.9 MB; +120.1 MB | `tag=w2000` |
| 1000 | w2000drop | ΔTupleCodec / ΔTupleType / ΔCacheKey | 1000 / 1000 / 1000 (same count as w1drop) | `tag=w2000drop` |
| 1000 | w2000drop − w1drop | `[Object;` bytes | **+8.3 MB** with 18,278 fewer arrays (1000 arrays of 2001 references ≈ 8.0 MB) | `h_w1drop_2.txt` vs `h_w2000drop_2.txt` |
| 1000 | w2000drop − w1drop | heap after GC; live bytes | **−9.2 MB**; −9.2 MB (memtable classes −9.6 MB: `HeapByteBuffer` −5.8, `BufferCell` −2.0, `AtomicBTreePartition` −1.8) | same |
| 1000 | all | ΔWeightedStrongValueReference | 0 at every checkpoint (S4-D2: weight-1 entries are `StrongValueReference`) | `readings.txt` |
| 1000 | all | create/drop time | 24, 75, 142, 231 s (narrow); 90, 73 s (M=1); 1509, 1371 s (M=2000) | `readings.txt` (`TIMING`) |

**Cluster tier, step 7 (patched jar, cap 100).** Same node, same harness, fresh data directory `cdata-pc100`; JVM line shows `-Dcassandra.test.codec_cache_max_weight=100` (`raw/cluster-pc100/command.log`). Function counts exact, cqlsh 0 errors, `system.log` 0 `ERROR`. Table: `raw/cluster-pc100/analysis.txt`.

| Capacity value | Run | Observable | Reading (cap 100) | Same checkpoint at cap 1000 | Evidence (file) |
|---|---|---|---|---|---|
| 100 | n500 / n2000 / n4000 | ΔCacheKey | **100 / 100 / 100** | 500 / 1000 / 1000 | `raw/cluster-pc100/readings.txt` |
| 100 | n500 / n2000 / n4000 | ΔVectorCodec$FixedLength | 500 / 2000 / 4000 | 500 / 2000 / 4000 | same |
| 100 | n500 / n2000 / n4000 | Δheap after GC | **+10.68 / +25.12 / +41.82 MB** | +10.67 / +25.17 / +41.76 MB (differences ≤ 0.06 MB, noise ±2.4 MB) | same; `raw/cluster/analysis.txt` |
| 100 | ndrop | ΔVectorCodec / ΔCacheKey; Δheap | **100 / 100**; +59.1 MB | 1000 / 1000; +58.9 MB | same |

(MB in the cluster tables are MiB, 2^20 bytes.)

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** Valid. The limit was reached and passed in every cell meant to pass it: K=2000 and 5000 against cap 1000 gave `size` 1000 [observed: `raw/unit/probe-A-cap1000-k{2000,5000}-r*.txt`], K=12000 against cap 10000 gave 10000 [observed: `probe-A-cap10000-k12000-r*.txt`]. The patch took effect: `javap` shows `Long.getLong("cassandra.test.codec_cache_max_weight", …)` in the built class [observed: §2 / `logs/build-unit.log`], and cap 100 gave `size` 100 [observed: `probe-A-cap100-k2000-r*.txt`]. Same K and key generator across M [observed: `harness/CodecCacheWeightProbeTest.java`]. 36/36 runs passed [observed: `raw/unit/command.log`].
2. **Readings.** All three repetitions of every cell are identical in `size`, `weight` and `deepBytes` (only `heapUsed` varies, by ≤ 1.4 MB) [observed: `raw/unit/analysis.txt`]. W-A K=500 bytes per entry (219 B) is just above B2f's 0.1–0.2 KB band; every other `deepBytes` prediction is met within S4-A4's [0.5X, 2X] [observed: `analysis.txt`]. No outlier.
3. **Matched rows (B2g).** All three "claim confirmed" rows:
   - Row 1, "W-C `deepBytes` rises about linearly with M (≥ 100× from M=1 to M=10000) while `size` = `weight` = 1000": 241,576 → 4,241,576 → 40,241,576 B, ratio **166.6×**, with `size` = `weight` = 1000 at every M; bytes per entry = 242 + 4.0·M [observed: `probe-C-cap1000-m*-k2000-r*.txt`].
   - Row 2, "W-B: 440 zero-weight entries stay alongside 1000 weighted ones and the total exceeds 1000 entries": `size` 1440, `weight` 1000, `list<int> still cached: true` in 3/3 [observed: `probe-B-cap1000-r*.txt`].
   - Row 3, "`size`/`weight` plateau at 100 / 1000 / 10000 as the knob changes (positive control moves) and bytes per entry still depend on M": narrow 100 / 1000 / 10000; wide M=1000 100 / 1000 / 2000 (K < cap); bytes per weight unit 4,241–4,256 B at M=1000 against 242 B at M=1 and 40,242 B at M=10000 [observed: `probe-A-cap*-r*.txt`, `probe-C-cap*-r*.txt`, `analysis.txt`].
4. **Excluded rows.**
   - Refuted row, "`deepBytes` roughly ∝ `weight`, the same at every M, and plateaus with the knob": at a fixed M bytes are proportional to weight and plateau with the knob (cap 100: 0.107×, cap 10000: 9.87× the cap-1000 plateau), but they are **not the same at every M** (166.6× apart at the same weight), and B2f's refuted-if ("M=10000 within 2× of M=1") fails [observed: `analysis.txt`]. Excluded.
   - "`size` never plateaus": `size` 1000 at K=5000 [observed]. Excluded.
   - "Positive control did not move": `size` 100 and 10000 at caps 100 and 10000 [observed]. Excluded.
   - "K below the cap in every run": K=2000, 5000, 12000 passed their caps [observed]. Excluded.
5. **Observed vs. inferred.** Every reading the matched rows use is observed. Inferred: (a) that jamm's `measureDeep(registry)` stands for the bytes the cache retains [inferred: it traverses the registry → `LocalCache` → entries → keys and codecs and their `TupleType` lists; statics are excluded, so the shared primitive `DataType` singletons are counted once]; (b) that the 4.0 B per M is the `ImmutableList` of M+1 references in each retained `TupleType` [inferred: the slope equals 4 B per compressed reference].
6. **Deviations and gaps.** S4-D1 (PROBE reassembly), found before run 1. W-A K=500's 219 B/entry slightly above the stated band (an order-of-magnitude estimate; no row depends on it). The stock unpatched copy was not run for the optional B2h cross-check; the `javap` check of both jars (stock `ldc2_w 1000l`; patched `Long.getLong` with default 1000) and the identical `size` at property-unset stand in for it.
7. **Core question.** The cap binds on its own operand: `size` and `weight` stop at the cap and follow it across 100 / 1000 / 10000 (parts 1, 3). Retained bytes do not follow the cap: at a constant weight sum of 1000 they range over 166.6× with tuple width alone, and 440 zero-weight entries sit outside the count (part 3). The constraint therefore caps the weight sum and entry count, not memory.

**Conclusion (unit, one line):** B2g rows 1, 2 and 3 — **confirmed**: the cap does not cap retained bytes.

**Cluster tier**

1. **Validity.** Valid. Every create and drop file applied completely (function counts exactly 500, 2000, 4000, 0, 1500, 0, 1500, 0; cqlsh rc 0, 0 error lines) [observed: `raw/cluster/readings.txt`, `TIMING`/`functions=` lines]. The limit was reached and passed: Δ`CacheKey` 1000 at N=2000 and 4000 [observed]. Stock jar (`ldc2_w 1000l`) [observed: §2]; no client traffic beyond the DDL and the sampling tools [observed: `raw/cluster/command.log`]. Heap peak 186 MB of 1 GiB, no GC pressure, 0 `ERROR` lines [observed: `readings.txt`, `system.log.gz`].
2. **Readings.**
   - The whole-heap observable is dominated by schema mutation data that moves with memtable flushes (memtables are `heap_buffers`): heap after GC rose 17 MB **after** the narrow drop (ndrop +58.9 MB over base, n4000 +41.8 MB), in `[B`, `HeapByteBuffer`, `BufferCell` and `BTreePartitionData` [observed: `h_n4000_2.txt` vs `h_ndrop_2.txt` on the node], and fell 9.2 MB from w1drop to w2000drop, with memtable classes −9.6 MB [observed: `h_w1drop_2.txt` vs `h_w2000drop_2.txt`].
   - One outlier: `w2000` sample 1 histogram `Total` 451.5 MB while its heap after GC (186.0 MB) matches samples 2 and 3; the median is unaffected [observed: `readings.txt`].
   - The cap-100 run reproduces the cap-1000 heap figures to within 0.06 MB at every N [observed: both `readings.txt`].
3. **Matched rows (B3g).**
   - Row 2, "`VectorCodec$FixedLength` count = N above 1000 → eviction frees nothing while UDFs live": Δ = 2000 at N=2000 and 4000 at N=4000 while Δ`CacheKey` = 1000; after the drop exactly 1000 remain, equal to the cache's entries [observed: `readings.txt` `tag=n2000/n4000/ndrop`]. At cap 100 the same: 2000 / 4000 live, 100 after the drop [observed: `raw/cluster-pc100/readings.txt`]. **Matched.**
   - The B3f cap-100 row, "cap=100 re-run, ndrop ≈100 / ≈100; n500…n4000 heap deltas the same as at cap 1000 within noise": 100 / 100; heap deltas +10.68 / +25.12 / +41.82 against +10.67 / +25.17 / +41.76 MB [observed]. Its "Δheap ≈ base" part is missed at both caps alike (+59.1 / +58.9 MB, memtables). The README's condition for confirming a negative claim, "usage flat across the knob values with the positive control moving", is met here: the cap's operand moved 10× (entry plateau 1000 → 100) while the heap at every N did not move.
   - Row 3, "same post-drop entry count at M=1 and M=2000 but about 8 MB more heap": same count, `TupleCodec` 1000 and 1000 [observed]. B3f's own column, Δ`[Ljava.lang.Object;` ≈ +8 MB, is met (+8.3 MiB, with 18,278 fewer arrays) [observed: `h_w1drop_2.txt` vs `h_w2000drop_2.txt`]. S4-A8's heap-after-GC rule (≥ +4 MB) is **not** met (−9.2 MB), because memtable bytes fell by more. **Partly matched**; it is not counted toward the verdict.
   - Row 1, "heap rises linearly with N through 500→4000 with no knee at 1000, while the entry count plateaus at ≈1000": the plateau holds (1000, 1000), and the heap rises in every segment far above noise (+10.7, +14.5, +16.6 MB). But S4-A8's band needs s1 ≥ 0.5·s0, and the reading is s1 = 0.45·s0, s2 = 0.39·s0 (21.9 / 9.9 / 8.5 KB per function). The refuting band (< 0.25·s0) is not met either, so by S4-A8 **row 1 is not matched**. It is not counted toward the verdict. The cap-100 run gives the same three slopes (21.9 / 9.9 / 8.5), so the higher first slope is not set by the cap. Inferred: it is a one-time cost of the first UDFs (keyspace creation and the UDF compiler's classes).
4. **Excluded rows.**
   - Refuting row 4, "heap plateaus or flattens at N≈1000, and the cap=100 re-run moves the knee to N≈100": the heap rises 14.5 and 16.6 MB after N=1000 (both segments are 6× the noise or more), and at cap 100 the heap is unchanged at every N while the entry plateau moved to 100 [observed]. Excluded.
   - "Entry count never plateaus (rises to ≈N)": 1000 at N=4000 [observed]. Excluded.
   - "Heap delta within noise at every N": 14.5 and 16.6 MB segments [observed]. Excluded.
   - "Fewer functions than intended": exact counts [observed]. Excluded.
5. **Observed vs. inferred.** Observed: entry counts, codec counts, function counts, heap after GC, `[Object;` bytes, and the cap-100 heap figures. Inferred:
   - (a) The +8.3 MiB of `[Object;` is the `ImmutableList` arrays of the 1000 cache-held wide `TupleType`s [inferred: 1000 × (16 + 4 × 2001) B ≈ 7.6 MiB; the size tracks the 1000 cached entries, not the 1500 created functions, and appears with fewer arrays].
   - (b) The heap background is memtable schema data [inferred from the class deltas above].
   - (c) The first-segment slope is a one-time cost [inferred; not load-bearing, since the verdict does not use row 1].
6. **Deviations and gaps.**
   - S4-D2 (instrument class), fixed before run 1.
   - B3f's "Δheap back to within a few MB of base" at ndrop, w1drop and the cap-100 ndrop was missed at every cap alike (+58.9 to +71.7 MB), for the reason in part 2. The whole-heap observable cannot resolve the cache's share (≤ 0.2 MB for narrow, ≈ 8 MB for wide) against a moving memtable background, so the bytes comparison for row 3 rests on `[Object;` bytes.
   - Rows 1 and 3 are only partly matched under the fixed S4-A8 rules, and the verdict does not use them.
   - The heap dump of B3d was optional and not taken.
   - Metaspace (the UDF classes) was not measured; it is outside this cap in any case.
7. **Core question.** On a running node the codec cache's weight cap binds on its own operand, as it does in the unit tier: the entry count stops at the cap and follows a 10× change of it (part 3). The heap does not follow it:
   - while functions live, every argument codec stays referenced (Δcodecs = N, not the cap), and the heap at N = 500, 2000 and 4000 is the same at cap 100 as at cap 1000 within 0.06 MB;
   - after the drops, the cache keeps exactly cap-many codecs, but their bytes depend on type width (+8.3 MiB of arrays at the same 1000 entries).
   The constraint does not cap memory (parts 3, 4).

**Conclusion (cluster, one line):** B3g row 2 together with the B3f cap-100 row (the negative-claim condition: flat across the knob while the positive control moves) — **confirmed**: the cap does not cap the heap. Row 3 is partly matched; row 1 is not matched under S4-A8. Neither is used.

## 5. Self-check of run 1 (AI)

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read, 2026-11-25) |
|---|---|---|
| 1. Validity | yes | Re-read `raw/unit/command.log` (37 × `Failures: 0, Errors: 0`, 0 `STOP`, including the smoke run), `probe-A-cap100/10000-*` (100 / 10000), `raw/cluster/readings.txt` (`functions=` 0, 500, 2000, 4000, 0, 1500, 0, 1500, 0; `TIMING` rc 0, 0 errors), `zcat system.log.gz \| grep -c '^ERROR'` = 0 in both cluster runs. |
| 2. Readings | yes | Unit repetitions identical (re-grepped W-C, W-B and knob files); the cluster outlier (`w2000` n=1 `HistTotalBytes` 451,540,504 vs `HeapUsedAfterGC_K` 185,998) re-read and does not affect any median used. |
| 3. Matched row | yes | Unit W-C 241,576 / 4,241,576 / 40,241,576 at size = weight = 1000 (3/3 each); W-B 1440 / 1000 / `true`. Cluster `tag=n2000` CacheKey 1000, VectorCodecFixed 2000; `n4000` 1000 / 4000; `ndrop` 1000 / 1000; cap-100 `n500/n2000/n4000/ndrop` CacheKey 100 and heap 74,209 / 89,014 / 106,104 / 123,842 K vs 74,197 / 89,060 / 106,043 / 123,578 K at cap 1000 (sample 2). The cluster verdict uses only row 2 and the B3f cap-100 row, which are fully met. Using these rather than row 1 is the conclusion's main judgement. B3g lists row 2 as sufficient on its own ("claim confirmed"). The README's confirming condition for a negative claim (flat across knob values, positive control moving) is met only through the cap-100 run, so the cluster verdict depends on that optional step having run. |
| 4. Excluded rows | yes | Every refuting and not-confirmed row of B2g and B3g is addressed with a reading. The refuting cluster row is excluded on two independent readings (the post-1000 heap rise and the unchanged heap at cap 100). |
| 5. Observed vs. inferred | yes | The verdict-bearing statements are observed. Inferences (a)–(c) of the cluster tier are stated as inferred. (a) supports only row 3, which is not used. The arithmetic was re-checked: 1000 × 8,020 B = 7.65 MiB against 8.29 MiB observed. |
| 6. Deviations and gaps | yes | The ndrop heap prediction miss and the memtable confound are recorded rather than explained away. Rows 1 and 3 are reported as not or partly matched rather than counted. |
| 7. Core question | yes | Both tiers: the cap bounds its operand (entry count and weight), and bytes do not follow it. The unit tier shows bytes per weight unit varying 166.6×; the cluster tier shows the heap identical under a 10× cap change. This follows the B1 logic: the bytes are refuted as following the limit only if they are proportional to weight whatever M is, and they are not. |

### 5.2 Run 2?

**No** (decided 2026-11-25). The unit tier is deterministic (identical readings in 3 fresh JVMs per cell). The cluster verdict rests on observed counts and on the cap-100 run, which reproduced the cap-1000 heap figures to within 0.06 MB. The result confirms the file's own (negative) claim; it neither refutes the case nor confirms a bypass.

## 6. Run 2 (fresh AI session, optional)

Not done (§5.2).

## 8. Verdict (AI)

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** negative. **Outcome class:** **true negative** (estimate `negative`, effect `does not cap` at both tiers).

**Claim tested** (B1): "The heap retained by `CodecRegistry`'s codec cache does not follow `maximumWeight(1000)`. The limit does cap the cache's weight sum, and with it the count of weighted entries. The retained bytes, however, vary independently." "Confirmed" below means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1, 2 and 3: at weight 1000, `deepBytes` 0.24 / 4.24 / 40.24 MB for M = 1 / 1000 / 10000 (166.6×); 440 zero-weight entries uncounted (1440 entries, weight 1000); `size`/`weight` follow the cap 100 / 1000 / 10000 | does not cap | run 1 + self-check | 2026-11-25 |
| Cluster | **Confirmed** — B3g row 2 (live argument codecs = N: 2000, 4000 against 1000 cache entries) and the B3f cap-100 row (entry plateau 1000 → 100, heap at N = 500/2000/4000 unchanged within 0.06 MB). Row 3 partly matched (same 1000 post-drop entries; `[Object;` +8.3 MiB at M=2000, but heap after GC −9.2 MB from memtable flushes). Row 1 not matched under S4-A8 (s1 = 0.45·s0, band ≥ 0.5). | does not cap | run 1 (with optional step 7) + self-check | 2026-11-25 |

**Positive control:**
- Unit: the patched knob moves the cache's own operand (`size` 100 / 1000 / 10000) and, for one fixed entry shape, its bytes (0.107× / 1× / 9.87×), on the same workload and instruments.
- Cluster: the cap-100 jar moves the entry plateau from 1000 to 100, and the post-drop remainder from 1000 to 100 codecs. The instruments see the workload move the heap (+41.8 MB over 4000 functions).

**Notes for readers.** The constraint is not without effect: it bounds the entry count and the weight sum, and for entries of one fixed shape the bytes scale with it. It does not bound memory, for three reasons:
- bytes per weight unit depend on type width (unbounded; 166.6× across the widths tried);
- zero-weight entries are not counted;
- on a node, codecs of live UDFs stay referenced whatever the cache evicts.
The cache's share of a node's heap was ≤ 0.2 MB for 1000 narrow entries and about 8 MB for 1000 tuples of width 2000, against tens of MB of schema memtable data from the same DDL.

**Feedback filed:** the amended copy `~/writeup-ext/out/o96/case-amended.md` carries B2i, B3i (S4-A1 to S4-A10) and section D (stage-4 feedback). The repository was not edited (task rule). The repository's case file section D, its `_INDEX.md` row (status and Outcome class `true negative`, sha256 after amendments `5e1d073f0cfed803090eb67a3173420325f19576e9318a541f5e00817d2e3ee0`) and HANDOFF are left for the coordinating session to file from this results file.

## Time spent (UTC, 2026-11-25)

Lock acquired 04:56:54; build 05:00; unit 05:02–05:11; shakedowns 05:03–05:06; cluster main 05:11–06:24; cap-100 re-run 06:24–06:41; cleanup and lock release 06:43. About 1 h 50 min in all.
