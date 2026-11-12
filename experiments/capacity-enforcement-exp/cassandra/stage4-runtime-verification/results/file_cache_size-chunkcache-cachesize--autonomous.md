# file_cache_size-chunkcache-cachesize--autonomous — stage-4 results  <!-- file: results/file_cache_size-chunkcache-cachesize--autonomous.md; the stem ends in --guided or --autonomous -->

> **Case:** [`file_cache_size-chunkcache-cachesize--autonomous`](../../stage3-ai-deep-read/cases/file_cache_size-chunkcache-cachesize--autonomous.md)
>
> **Status:** self-checked, verdict filed in this file and the case file's section D (2026-11-12); not committed (the coordinator closes the case)
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location.

The protocol behind each section is in
[`../../../stage4-runtime-verification/README.md`](../../../stage4-runtime-verification/README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there). Filing sha256 (`_INDEX.md` §4): `1611f56411db6da69940cd0360f3a332a14666bcade5fae93ab58719b92bbeb5`. sha256 of the whole file after the audit's amendments A1–A7 (2026-11-11): `7c57994fbd22d1f287dcfbe79c0e6adf6c359f166876ed085b0964e095bd025d` (the version the unit run and cluster attempt 1 used). After amendments A8–A9 (runbook defects D1, D2, §3; B3a and B3c only, no prediction or conclusion text changed): `318a204873d832af007704caf534eec3dfe65c0679958fbc52f32ea621474625` (the version the cluster run 1 used; this is the frozen version for `_INDEX.md`). sha256 of the frozen prediction and conclusion tables (text of B2f, B2g, B3f, B3g, from `**B2f.` up to `**B2h.` and from `**B3f.` up to `**B3h.`, concatenated; copy at `/mydata/jingsong-cass-s4/o07/freeze-pred.txt`): `ffb8fa1b5e414a6dd4c0a177014ad3790b8199226787acb4a20f38127de5612f`, recorded in this file at 2026-11-12T02:52Z before any reading, and unchanged after A8–A9 (rechecked). Section D (feedback) is written after the run, so the whole-file hash after it differs (see §8). |
| **Harness** | `harness/file_cache_size-chunkcache-cachesize--autonomous/` (`ChunkCacheCapProbeTest.java`, `unit-run.sh`, `unit-analyze.py`, `JmxSampler.java`, `cluster-run.sh`, `cluster-analyze.py`, `README.md`); not committed by this session. md5 prefixes logged by each run's `summary.txt` match the files as left. |
| **Tiers and values** | Unit (B2): `file_cache_size` 32 (U0), 64 (U1), 128 (U2), 1024 MiB (U3, positive control), 128 MiB with `file_cache_enabled: false` (U4); 64 × 200 × 16 KiB random blobs, LZ4 16 KiB, two read passes. Cluster (B3): one node on 127.0.0.1, heap 2 GiB, direct limit 2 GiB; C0 cache off, C1 128 MiB, C2 256 MiB, C3 1024 MiB (positive control); 500k × 1 KiB stress rows (LZ4 16 KiB), two 2M uniform reads per value. |
| **Audit bottom line** | **Ready after amendments** — 2026-11-11 (A1–A7 applied before any reading; A8–A9 added as runbook-defect fixes during cluster attempt 1, §3) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: bytes of uncompressed chunks held off-heap (weigher = `buffer.capacity()`), plus the pool's direct slabs. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Partly | B2b: 32/64/128/1024 MiB; B3b: off/128/256/1024 MiB. The default (512 MiB at a ≥ 2 GiB heap) is not among them, but the knob is an explicit byte value and 3 binding values plus a non-binding control span it; accepted. |
| A. Core question | real resource measured, not only the counter (gap named) | Met after A3, A5 | B2d pool gauges; B3d pool, JVM direct `MemoryUsed`, NMT `Other`, RSS. The harness adds the JVM direct `MemoryUsed` to the unit tier too. B3d names the attribution gap (difference against C0). |
| A. Core question | usage driven to the limit and past it | Met | Unit data ≈ 200 MiB against 32/96 MiB caps; cluster ≈ 500 MiB against 96/224 MiB. |
| B. Logic | each step says what it establishes | Met | B2h/B3h tie each run to its purpose (boundary, gate, positive control, churn). |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f/B3f: exact caps, 5% bands, ratio 3, C2−C1 ≈ 128 MiB ± 32. |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after A7 | B2g has exceed / flat / below-cap / pool overshoot / boundary rows. B3g lacked the "plateau far below the cap" row that B2g has: A7 adds it (before any reading). A reading that matches no row is "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met after A3 | Ceiling: caps at two values plus the control above. Disallow: eviction count = misses − entries (A3; `recordEviction` records nothing), and the pool's "Maximum memory usage reached" log line. |
| B. Logic | alternative explanations and their controls | Met | U3/C3 positive controls; U4/C0 gate controls; random blobs; flushes; row cache off (B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate row, A1–A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | Commands given; only paths and ports needed changing (A1, A2, A4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | B3d's per-gauge `nodetool sjk` cannot keep a 10 s cadence (A5); process checks by `pgrep -f` are unsafe on a shared node (A6). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met after A1 | B2a's `/users/jason92/cassandra-5.0.9` does not exist; A1 uses `copy-source.sh`. JDK 11 / Ant present. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | 200 MiB / 500 MiB of data; ≈ 1 GiB disk; ≤ 4 GiB heap + direct. `ant testsome` forks a 1 GiB heap (A1), enough for 16-partition flush batches (≈ 50 MiB). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in the copy: ChunkCache.java:49–54 (cacheSize, gate), :151–157 (maximumWeight, weigher, ImmediateExecutor), :161–181 (load, onRemoval), :311–328; FileHandle.java:405–449 (`maybeCached`, Standard and Mmap compressed paths wrapped); BufferPools.java:38–53; BufferPool.java:274–293, :443–468; DatabaseDescriptor.java:576–577, :3784–3793; test/conf/cassandra.yaml:28 (`mmap_index_only`) and :55; build.xml:1153 (`maxmemory=1024m`), :1192; CachesTable.java:57–75. All as cited. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| A1 | Working tree via `copy-source.sh` at `$W/src`; note the 1 GiB forked heap | applied 2026-11-11 (case file untracked; no commit) | B2a path does not exist on the node; heap is set by `maxmemory` |
| A2 | Unit yaml variants also set ports 7300/7301/9342 | applied 2026-11-11 | shared node |
| A3 | Record `misses` (eviction count = misses − entries); `disableCompaction()` | applied 2026-11-11 | direct disallow evidence; stable SSTables between passes |
| A4 | Cluster binds 127.0.0.1, ports 7300/7301/9342, JMX 7499; data under `$W/cdata` | applied 2026-11-11 | shared node |
| A5 | One JMX sampler JVM instead of per-gauge `nodetool sjk`; cqlsh at snapshots | applied 2026-11-11 | 10 s cadence |
| A6 | Process checks by PID and directory | applied 2026-11-11 | other people's daemons on the node |
| A7 | B3g row: C1/C2 plateau ≪ cap while C3 rises → partly wrong | applied 2026-11-11, before any reading | missing outcome row (mirrors B2g row 4) |
| A8 | Stress load with `-schema 'compression=LZ4Compressor'` | applied 2026-11-12 (defect D1) | stress default schema is uncompressed |
| A9 | `MAX_DIRECT_MEMORY_SIZE=2G` | applied 2026-11-12 (defect D2) | cassandra-env.sh sets the direct limit itself |
| R-a | B3c/B3f data-size arithmetic: 500k × 1 KiB stress rows are ≈ 505 MiB uncompressed, not 550–600 MiB; C0 pool baseline is 16 MiB on a 32-thread read, not "a few MiB" | left for stage 3 | found by the run (§4.2 part 2); not applied after readings |
| R-b | Include the default `file_cache_size` (512 MiB) as a value | left for stage 3 | group A, default value |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-11-12 (UTC 02:52–03:14) |
| Node (CloudLab name and type) | node0, `pc96.cloudlab.umass.edu`, 32 cores, 125 GiB (shared: other Cassandra nodes on 127.0.0.11–17 and at `/mydata/b6`, `/mydata/jingsong-cass-s4/o06`) |
| OS and kernel (`uname -r`) | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK (`java -version`) | OpenJDK 11.0.33 (2026-10-20) |
| Ant (`ant -version`) | 1.10.12 |
| Local source copy | `/mydata/jingsong-cass-s4/o07/src`, made by `copy-source.sh` from `systems/cassandra/source/` at repository commit `f74aade6` (cassandra-5.0.9); `ant build-test` BUILD SUCCESSFUL in 1 min 20 s |
| Case-file commit / harness commit | case file untracked at `f74aade6` (sha256 in §1); harness uncommitted (md5 in the run summaries) |
| Storage for node data | `/mydata` (local LVM, ext4, 753 GB, 665 GB free); unit data `src/build/test/cassandra` (deleted after each value), cluster data `/mydata/jingsong-cass-s4/o07/cdata` (deleted at the end) |
| Full logs (path, outside the repo) | `/mydata/jingsong-cass-s4/o07/`: `logs/` (build, unit and cluster driver logs), `run1/unit/` (ant logs, test logs, junit XML, probe output), `run1/cluster/` (cmd.log, samplers, snapshots, stress logs), `clogs/system.log`, `attempt1-*` (stopped cluster attempt 1), `shakedown/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | cluster attempt 1 | B3c load | `cassandra-stress`'s default schema has no compression (`WITH compression = {}`, SettingsSchema.java:141–143, 211). The loaded table had `SSTable Compression Ratio: -1`, no `CompressionInfo.db`; B3c and B3f assume 16 KiB LZ4 chunks. | Amendment A8: `-schema 'compression=LZ4Compressor'`; script stops if the table is uncompressed. B3f/B3g unchanged (table hash unchanged). | 2026-11-12: attempt 1 stopped during C0's first read (no reading evaluated); data wiped; cluster tier restarted from the load | none (case file untracked) |
| D2 | cluster attempt 1 | B3a heap / direct | B3a says the direct limit defaults to the 2 GiB heap. In 5.0.9 `conf/cassandra-env.sh` sets it (lines 50–67, 139–158): the node started with `-XX:MaxDirectMemorySize=15872M`. | Amendment A9: `MAX_DIRECT_MEMORY_SIZE=2G`; script checks the flag on every start. B3f/B3g unchanged. | 2026-11-12, same restart | none |

Evidence for both: `run1/cluster-attempt1/summary.txt`, `run1/cluster-attempt1/tablestats-compression.txt`.

## 4. Run 1

**Scope:** unit U0–U4; cluster load + C0–C3 (after the D1/D2 restart). **Command logs:**
`file_cache_size-chunkcache-cachesize--autonomous/run1/unit/summary.txt` (the ant command per value is in `unit/ant-command-64.txt`), `run1/cluster/cmd.log`, `run1/cluster/summary.txt`.

### 4.1 Readings

**Unit tier** (`run1/unit/unit-<v>.txt`, `run1/unit/summary.txt`; `cap` = `cacheSize`; every run read 25,600 rows in two passes; 4 SSTables, memtable empty at read time, ≈ 211 MB on disk)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Pool-limit log line per value | `Global buffer pool limit is 32.000MiB / 64.000MiB / 128.000MiB / 1.000GiB / 128.000MiB for chunk-cache` for 32/64/128/1024/off | `unit/poollimit-<v>.log` |
| Test heap | `HEAPMAX 1056309248` (1 GiB, `maxmemory` overrides `-Xmx4G`), `MaxDirectMemorySize` flag 0 (default = heap) | `unit/unit-64.txt` |
| U0 (32 MiB) | `CACHE_NULL`; pool size 8.00 MiB max, overflow 0, used 0; JVM direct 8.47 MiB | `unit/unit-32.txt` |
| U1 (64 MiB, cap 32 MiB) | capacity 33,554,432; weighted max = final = 33,554,432 (= cap), first ≥ 0.95 cap at read 2,048; 0 samples > cap; entries 2,048; misses 35,258 → **33,210 evictions**; pool size 64.00 MiB (= `file_cache_size`), overflow 0, used 32.00 MiB; JVM direct 64.50 MiB | `unit/unit-64.txt` |
| U2 (128 MiB, cap 96 MiB) | capacity 100,663,296; weighted max = final = 100,663,296 (= cap); 0 samples > cap; entries 6,144; misses 22,855 → **16,711 evictions**; pool size 128.00 MiB, overflow 0, used 96.00 MiB; JVM direct 128.53 MiB | `unit/unit-128.txt` |
| U3 (1024 MiB, cap 992 MiB; positive control) | weighted final 209,993,728 (200.27 MiB), same after pass 1 and pass 2; entries 12,817 = misses (0 evictions); ≈ 16,410 B per read during pass 1 (linear); pool size 208.00 MiB, overflow 0; JVM direct 208.57 MiB | `unit/unit-1024.txt`, `unit/summary.txt` |
| U4 (128 MiB, gate off) | `CACHE_NULL`; pool size 8.00 MiB, used 0; JVM direct 8.47 MiB | `unit/unit-off.txt` |
| U2 / U1 final weighted | 3.000 | `unit/summary.txt` |

**Cluster tier** (`run1/cluster/`; load: 500,000 partitions, 1 SSTable after compaction, LZ4 16 KiB, ratio 0.994, uncompressed data length 529,888,907 B = 505.34 MiB in 32,343 chunks (`compressioninfo.txt`, `standard1-files.txt`); every read run: 2,000,000 reads, 0 errors (`summary.txt`))

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| off (128 MiB) | C0 control | `system_views.caches` chunks row | absent at all 4 snapshots | `C0-snap.txt` |
| off | C0 | chunk-cache pool Size / Used | 16.00 MiB / ≤ 0.05 MiB | `C0-jmx.csv`, `C0-jmx-snap.csv` |
| off | C0 | JVM direct `MemoryUsed`, final | 63.45 MiB (NMT Other 415.46 MiB) | `C0-jmx-snap.csv`, `C0-snap.txt` |
| 128 MiB | C1 | pool-limit log line | `Global buffer pool limit is 128.000MiB for chunk-cache`; `Maximum memory usage reached (128.000MiB) for chunk-cache buffer pool` at 03:05:15 | `system-log-pool-lines.txt` |
| 128 MiB | C1 | cache size_bytes / entry_count | 100,663,296 (= cap 96 MiB) / 6,144 from the first 10 s sample of read 1 to the end; max 100,663,296 (one sample reads 6,145 entries at the same weight) | `C1-jmx.csv`, `C1-snap.txt` |
| 128 MiB | C1 | misses − entries (evictions) | 3,553,340 − 6,144 = **3,547,196** | `C1-jmx-snap.csv` |
| 128 MiB | C1 | pool Size / Overflow / Used | 128.00 MiB / 0 / 96.00 MiB | `C1-jmx-snap.csv` |
| 128 MiB | C1 | direct `MemoryUsed` final; Δ vs C0 | 175.54 MiB; **+112.08 MiB** (NMT Other Δ +112.08 MiB) | `C1-jmx-snap.csv`, `C1-snap.txt` |
| 256 MiB | C2 | pool-limit log line | `… 256.000MiB for chunk-cache`; `Maximum memory usage reached (256.000MiB)` at 03:08:09 | `system-log-pool-lines.txt` |
| 256 MiB | C2 | cache size_bytes / entry_count | 234,881,024 (= cap 224 MiB) / 14,336; max 224.00 MiB | `C2-jmx.csv`, `C2-snap.txt` |
| 256 MiB | C2 | evictions | 2,481,386 − 14,336 = **2,467,050** | `C2-jmx-snap.csv` |
| 256 MiB | C2 | pool Size / Overflow / Used | 256.00 MiB / 0 / 224.00 MiB | `C2-jmx-snap.csv` |
| 256 MiB | C2 | direct final; Δ vs C0 | 303.54 MiB; **+240.09 MiB** (NMT Other Δ +240.09 MiB) | `C2-jmx-snap.csv`, `C2-snap.txt` |
| 1024 MiB | C3 positive control | cache size_bytes / entry_count | 530,284,544 (505.72 MiB) / 32,366 after read 1, unchanged after read 2 and at final; misses 32,402 (36 evictions) | `C3-jmx-snap.csv`, `C3-snap.txt` |
| 1024 MiB | C3 | pool Size / Overflow | 512.00 MiB / 0 | `C3-jmx-snap.csv` |
| 1024 MiB | C3 | direct final; Δ vs C0 | 559.77 MiB; **+496.32 MiB** | `C3-jmx-snap.csv` |
| all | — | RSS final (MiB) C0/C1/C2/C3 | 2900 / 3036 / 3167 / 3455 | `C?-snap.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — valid. Each value took effect: the pool-limit line equals `file_cache_size` for every run, and `capacity()` equals `file_cache_size − 32 MiB` [observed: `unit/poollimit-*.log`, `unit/unit-*.txt`]. Reads hit SSTables: 4 SSTables, memtable 0 bytes at read time [observed: `SSTABLES` line in each `unit-*.txt`]. The limit was reached and passed: U1 hit its cap at read 2,048 of 25,600, U2 at 5,888 [observed: `unit/summary.txt`].
2. **Readings** — no gap or outlier. U3's 12,817 entries for 12,800 rows of 16,384 B + overhead is the data size (200.27 MiB) [observed]. The pool's slabs reach the full `file_cache_size` (64/128 MiB) while the cache holds `cacheSize` (32/96 MiB); overflow stays 0 [observed: `unit-64.txt`, `unit-128.txt`].
3. **Matched row** — B2g row 1: "U1/U2 final `weighted` ≈ cap and never > cap + 16 KiB; U3 ≈ data size (≫ U1/U2 caps) → Claim confirmed." U1 final = cap exactly, max = cap; U2 likewise; U3 = 200.27 MiB, more than 6 × U1's cap and 2 × U2's [observed: `unit/summary.txt`]. Every B2f relation held: U0/U4 `CACHE_NULL` with pool 8 MiB, entries 2,048 / 6,144, pool ≤ `file_cache_size` + overflow, overflow ≤ 32 MiB, U3 same after both passes, ratio 3.000 [observed: `unit/summary.txt`, "B2f prediction facts"].
4. **Excluded rows** — row 2 (**Refuted**, exceeds cap): 0 samples above cap in U1 and U2 [observed]. Row 3 (U3 also near 32/96 MiB): U3 = 200.27 MiB [observed]. Row 4 (final ≪ cap): finals equal cap [observed]. Row 5 (`poolSize` > `file_cache_size + cacheSize`): max 64 MiB < 96 MiB (U1), 128 < 224 (U2) [observed]. Row 6 (U0 non-null): U0 prints `CACHE_NULL` [observed].
5. **Observed vs. inferred** — one inferred statement: misses − entries = evictions [inferred: each miss runs `load` and inserts one entry (ChunkCache.java:161–175); nothing else removes entries — compaction disabled, no file was closed during the reads; U3, where nothing should be evicted, gives misses = entries exactly, which supports it].
6. **Deviations and gaps** — test heap 1 GiB, not 4 GiB (A1; `HEAPMAX` line); no effect on any cap. Caffeine's transient state between insert and maintenance is not observable (B2d). Ports differ from the test yaml (A2).
7. **Core question** — Usage follows the constraint: the cache operand is exactly `file_cache_size − 32 MiB` at 64 and 128 MiB (parts 1, 3) while the same reads fill 200 MiB at 1024 MiB (part 3), and the disallow branch fired tens of thousands of times (part 5). The real direct memory follows the knob too, at `file_cache_size` (64.5 / 128.5 / 208.6 MiB) (part 2). The constraint caps usage.

**Conclusion (unit, one line):** B2g row 1 — confirmed (caps).

**Cluster tier**

1. **Validity** — valid. The node ran with `-Xmx2G` and `-XX:MaxDirectMemorySize=2G` [observed: `summary.txt` start lines]. The pool-limit line matched each value [observed: `system-log-pool-lines.txt`, `summary.txt`]. The table was LZ4 16 KiB, ratio 0.994 [observed: `cmd.log`, `compressioninfo.txt`]. Each read run completed 2M reads with 0 errors [observed: `summary.txt`]. The limit was reached and passed: C1 and C2 sat at their caps from the first sample of read 1, and the pool logged "Maximum memory usage reached" [observed: `C1-jmx.csv`, `C2-jmx.csv`, `system-log-pool-lines.txt`]. Row cache 0 [observed: `C?-snap.txt` rows row capacity 0].
2. **Readings** — Two B3f point estimates missed; neither is a B3g row. (a) C0's pool `Size` is 16 MiB, not "a few MiB" (used ≤ 0.05 MiB: slabs held by 32 reader threads' local pools) [observed: `C0-jmx.csv`]. Its effect is that the C0 baseline already includes 16 MiB of chunk-cache-pool slabs, so the direct deltas (112, 240 MiB) are `file_cache_size − 16 MiB` [observed: pool 128 − 16 = 112, 256 − 16 = 240]. (b) C3 plateaued at 505.72 MiB, not "≈ 550–600 MiB": the prediction's data-size estimate was high; the table's whole uncompressed data is 505.34 MiB in 32,343 chunks, and C3 holds 32,366 entries (the data plus the 23 system-table chunks present at the baseline) with misses ≈ entries [observed: `compressioninfo.txt`, `C3-jmx-snap.csv`]. So C3 holds the whole hot set, which is what B3f's "keeps rising to ≈ the hot set" means. One sample in C1 and C2 shows entries = cap/16 KiB + 1 at weight = cap [observed: `C1-jmx.csv`]; weight never exceeded the cap.
3. **Matched row** — B3g row 1: "C1/C2 `size_bytes` plateau at ≈ cap; the direct delta is ≈ `file_cache_size` and follows the knob; C3 goes well above → Claim confirmed." C1 = 96.00 MiB, C2 = 224.00 MiB, both exactly the cap [observed: `C1-snap.txt`, `C2-snap.txt`]. Direct delta 112 / 240 / 496 MiB, increasing with the knob; C2 − C1 = 128.00 MiB (B3f: 128 ± 32) [observed: `summary.txt`]; the pool itself is exactly 128 / 256 MiB [observed]. C3 = 505.72 MiB, 2.3 × C2's cap [observed].
4. **Excluded rows** — row 2 (**Refuted**: size > cap + slack, or direct ≫ `file_cache_size` + overflow): 0 samples above cap; deltas below `file_cache_size` [observed]. Row 3 (direct delta same across C1–C3): 112 ≠ 240 ≠ 496 MiB [observed]. Row 4 (overflow ≈ `cacheSize`): `OverflowSize` 0 throughout [observed]. Row 5 (C0 shows a chunks row): absent at all C0 snapshots [observed]. Row 6 (A7; plateau ≪ cap): plateaus equal the cap [observed].
5. **Observed vs. inferred** — (i) evictions = misses − entries [inferred, as for the unit tier; C3, which fits the data, gives misses − entries = 36, while C1/C2 give millions]. (ii) The direct delta against C0 is the chunk cache's [inferred: B3d's attribution by difference; supported by the pool `Size` rising by the same amounts (112, 240, 496 MiB above C0's 16 MiB) and NMT Other moving by the same deltas].
6. **Deviations and gaps** — ports, addresses and directories per A4; JMX sampler per A5; D1/D2 restart (§3). Stress used `-port native=9342 jmx=7499`. The cluster attempt 1 C0 baseline snapshot exists (`/mydata/.../attempt1-cluster/`), from the uncompressed table; it is not used.
7. **Core question** — The cache operand plateaus exactly at `file_cache_size − 32 MiB` at 128 and 256 MiB while the same workload fills 506 MiB at 1024 MiB (part 3), with millions of evictions at the two binding values (part 5). The node's direct memory rises with the knob by exactly the pool size, `file_cache_size` (parts 3, 5). The constraint caps usage, and usage follows it.

**Conclusion (cluster, one line):** B3g row 1 — confirmed (caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read `unit/summary.txt` (pool-limit lines, `Tests run: 1, Failures: 0`), `unit/unit-64.txt` (`SSTABLES,4,memtableLiveBytes,0`, `HEAPMAX`); `cluster/summary.txt` (`-XX:MaxDirectMemorySize=2G`, 0 errors per read run), `cluster/cmd.log` (ratio 0.99407, CompressionInfo.db), `system-log-pool-lines.txt` (two "Maximum memory usage reached" lines, 128 and 256 MiB). |
| 2. Readings | yes | Re-read `C0-jmx.csv` (pool 16,777,216 every sample), `C3-jmx-snap.csv` (530,284,544 / 32,366 / 32,402 at after-read1, after-read2, final), `compressioninfo.txt` (32,343 chunks, 505.34 MiB), `C1-jmx.csv` (6,145 entries at 100,663,296 in two samples). |
| 3. Matched row | yes | `C1-snap.txt` cqlsh row `chunks | 100663296 | 100663296 | 6144` and `C2-snap.txt` row `chunks | 234881024 | 234881024 | 14336`; direct `MemoryUsed` in the `final` lines of `C?-jmx-snap.csv`: C0 66,536,458 B (63.45 MiB), C1 184,065,940 (175.54), C2 318,284,302 (303.54), C3 586,963,684 (559.77); differences recomputed in Python by `cluster-analyze.py` (`summary.txt`). Unit: `unit-64.txt`/`unit-128.txt` `MAX` lines equal the caps. |
| 4. Excluded rows | yes | Every Refuted row (B2g row 2, B3g row 2) addressed with a sample count of 0 above the cap; `OverflowSize` column 0 in all `C?-jmx.csv`; C0 chunks row absent in all four C0 snapshot blocks. |
| 5. Observed vs. inferred | yes | Eviction inference: U3 `FINAL` has misses = entries = 12,817 and C3 misses − entries = 36, against U1 33,210 and C1 3.5 M — consistent with misses counting loads. Direct attribution: `C?-jmx-snap.csv` pool `Size` 16→128→256→512 MiB matches the direct deltas within 0.1 MiB. |
| 6. Deviations and gaps | yes | D1/D2 restart recorded; attempt-1 readings not used; heap override recorded. |
| 7. Core question | yes | Both tiers: operand fixed at the cap for two binding values, positive control above, disallow evidence present, real direct memory follows `file_cache_size`. |

The two B3f point misses (C0 pool 16 MiB; C3 at 505.7 rather than 550–600 MiB) were weighed against the matched row: B3g row 1 does not depend on either, and no B3g row describes either outcome as a failure. They are recorded as stage-3 feedback (R-a), not as a downgrade.

### 5.2 Run 2?

**No** — 2026-11-12. The conclusion rests on direct readings of the cap operand at exact values on both tiers; the inferred statements are supported by the controls; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps) — both tiers Confirmed, effect `caps`.

**Claim tested (B1):** With `file_cache_enabled: true`, the uncompressed-chunk memory held by the chunk cache never exceeds `file_cache_size − 32 MiB` (plus at most a few chunks in flight), however much more SSTable data is read; the node's direct memory attributable to the chunk cache grows with `file_cache_size` and stays within `file_cache_size` plus small overflow; with `file_cache_size ≤ 32 MiB` the cache does not exist.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g row 1 (U1 = 32.00 MiB, U2 = 96.00 MiB exactly at cap, 33,210 / 16,711 evictions; U3 = 200.27 MiB; U0/U4 no cache) | caps | run 1 + self-check | 2026-11-12 |
| Cluster | **Confirmed** — B3g row 1 (C1 = 96.00 MiB, C2 = 224.00 MiB at cap, 3.5 M / 2.5 M evictions; direct Δ vs C0 112 / 240 / 496 MiB; C3 = 505.72 MiB) | caps | run 1 + self-check | 2026-11-12 |

**Positive control:** U3 (1024 MiB) filled to the data size, 200.27 MiB, 6 × U1's cap; C3 (1024 MiB) filled to the whole table, 505.72 MiB, 2.3 × C2's cap.

**Notable findings.**
- The real direct memory follows the full `file_cache_size`, not `cacheSize`: the chunk-cache pool's slabs fill to `file_cache_size` (64/128/256 MiB) while the cache holds `file_cache_size − 32 MiB`; the 32 MiB "reserve" is allocated, not spare. Overflow stayed 0 in every run.
- `cassandra-stress`'s default schema is uncompressed; a design that assumes LZ4 chunks must say `-schema compression=LZ4Compressor` (D1).
- 5.0.9's `cassandra-env.sh` sets `-XX:MaxDirectMemorySize` itself (15,872 MiB on this 125 GiB node with a 2 GiB heap), so "unset → equals heap" is false for `bin/cassandra` (D2).
- The `Entries` gauge read cap/16 KiB + 1 in single samples while the weight stayed at the cap (Caffeine's size is a map size, not the weighted size).

**Feedback filed:** the case file's section D updated (2026-11-12; case file untracked, no commit); amendments A1–A9 in B2a, B2b, B2d, B3a, B3c, B3d, B3e, B3g (dated). Whole-file sha256 after section D: `a5dcbc71f41fd2de99ea567e3fa95ad85d5f9987d506c03b6864f2253d0e81fb`.

**What stays on the node** (node0, `/mydata/jingsong-cass-s4/o07/`, ≈ 490 MiB): the working tree `src/` (built; probe removed, `git status` clean), `logs/`, `run1/` (unit and cluster outputs, conf copy), `clogs/` (node logs), `attempt1-cluster/`, `attempt1-conf/`, `attempt1-clogs/`, `shakedown/`, `freeze-pred.txt`. Cluster data (`cdata/`) and unit test data were deleted. No process from this run is left: node PIDs 861172, 868278, 872481, 876642, 885823, 896882, 906559 and the samplers are gone (checked by PID 2026-11-12T03:14Z); ports 7300/7301/7499/9342 free.
