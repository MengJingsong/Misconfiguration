# column_index_cache_size-indexSamples-cacheSizeThreshold — stage-4 results  <!-- file: long-path/results/column_index_cache_size-indexSamples-cacheSizeThreshold.md -->

> **Case:** [`column_index_cache_size-indexSamples-cacheSizeThreshold`](../../../stage3-ai-deep-read/long-path/cases/column_index_cache_size-indexSamples-cacheSizeThreshold.md)
>
> **Status:** verdict filed (2026-10-14) — **Confirmed at both tiers**, both sites (write path at three values on the node, read path at four, live); the read path's operand is `S + h`, seen on the node at the boundary (*n* = 66 written indexed, read shallow at 2 KiB); no run 2
>
> **Path:** long. One results file per path, each in its path's folder.

**Fill the sections in order.** The audit (§1), run 1 (§4) and the self-check
(§5) are required; run 2 (§6) and the comparison (§7) are filled only if §5.2
chooses run 2. No step waits for a human.
The protocol behind each section is in
[`../../README.md`](../../README.md#the-run-protocol).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Base commit `986cf19` (the last commit touching the case file) plus the step-0 amendments of 2026-10-14 (uncommitted at freeze). §9 hash before the amendments `851e418b67834734f8d4c231be76101cd2deb021`; **after the amendments `b56c6fa87f4bdf3d605a3337e2ed1d940de0c4b1`** (`sed -n '/^## 9\. /,/^## 10\. /p' <case> \| git hash-object --stdin`); §9a alone `abf9d963e517f75acd3bbf61acd43b7e045026a2`. §9a is frozen at this version. Recorded 2026-10-14 17:36 EDT, before any reading of this case existed (no earlier session ran it; `pc57:~/stage4-logs/` had no folder for it). Two later dated corrections to 9b/9c, both with §9a unchanged (`abf9d963…`): the JMX wording found at the instrument check (§1.2), and runbook defect 1 (§3); **§9 hash at run 1 `73420d9b07411fd4c031f967fa951e7ceabf8d88`**. |
| **Harness** | `../harness/column_index_cache_size-indexSamples-cacheSizeThreshold/`, written by this session after the freeze (§1.2). Node copy `pc57:~/stage4-harness-run/cics/`. |
| **Tiers and values** | Unit: upstream `RowIndexEntryTest`; harness `ColumnIndexThresholdTest` (one JVM), write-time and read-time thresholds 0 · 2 (default) · 16 · 256 KiB, *n* = 2 · 10 · 34 · 270 · 2,200 · 18,000 blocks, and the 2 KiB boundary (*n* = 50 … 90). Cluster (one node on `pc57`, RF 1, one node lifetime): *T* = 0 · 2 · 16 · 256 KiB set over JMX, classes C1 · CB · C2 · C3 · C4 at every value, live flip 256 → 16 KiB, large-cache arm, write-path arm W. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-14 |

### 1.1 Design audit

Citations re-read against the pinned clone `/proj/misconfiguration-PG0/git-repos/cassandra-src` (`git describe --tags` = `cassandra-5.0.9`).

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | Heap retained per row-index entry: the `IndexInfo[]` of an `IndexedEntry` against the constant `ShallowIndexedEntry` (§7, §9a claim). |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | 0 · 2 (default) · 16 · 256 KiB at both tiers, live over JMX on the node (9b). |
| A. Core question | real resource measured, not only the counter (gap named) | Met | The census (`GC.class_histogram`: live `IndexedEntry`, `ShallowIndexedEntry`, `IndexInfo`) and the heap after a full collection; the key cache's `Size` is the weigher's figure, and §9a says why the node heap alone cannot decide ("Why the entry class"). Gap noted, not load-bearing: `IndexedEntry.unsharedHeapSize()` leaves out the `int[] offsets` array (16 + 4*n* B, `RowIndexEntry.java:497`, `:534`, `:613-620`), so the weigher under-charges each read-path entry by about 2 % (rec. 7). |
| A. Core question | usage driven to the limit and past it | Met | Every class is read at a value above and below its `S` (C4 never below), plus the boundary (unit step 5, class CB). |
| B. Logic | each step says what it establishes | Met | §9a "How this verifies", Logic (1)–(5). |
| B. Logic | prediction stated in numbers or a clear relation | Partly | Class by threshold is exact, but stated for one operand: the read path compares `S + h`, not `S` (rec. 1). The key-cache and census rows were relations without a form a pass could miss (rec. 4). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met | Rows for no flip, re-cap missing, write path lagging, `Entries` not rising, flat heap, no displaced I/O, invalid dataset. An off-by-one at the boundary had no explicit place (amended, below the table). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The entry class per read is the disallow evidence (census; amended to a per-read trace line). |
| B. Logic | alternative explanations and their controls | Partly | The key-cache-off arm cannot do its job: at capacity 0 the cache retains nothing, so it removes retention, not the cap (rec. 2). Partitions split across SSTables would shrink `S` (rec. 3). Idle control, invalidation and BIG check are in place. |
| C. Specific | a human can follow it from the intro and §9a | Met | §9 intro, §9a. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly | The `S` measurement on the node was the key-cache weight difference, which is the weight, not `S` (9d says so); the "index-file reads" observable was elapsed time under the page cache (rec. 4). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | 9e's cluster steps name scenario A and B but not which classes are read at each value; 9b names "the boundary pair" on the cluster with no step (rec. 5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Harness listed as step-1 work (9c). `pc57` (this host): JDK 11.0.32.1, Ant 1.10.12, `jcmd`, `~/cassandra-run1` at `cassandra-5.0.9` (`b5f2a54`), built, Byteman 4.0.20 in `build/lib/jars/`, the bundled Python driver; 251 GiB RAM, 54 GB free on `/`. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | About 2.6 GB of data and 2.6 M rows: fits the disk; the key cache demand exceeds `K` = 8 MiB for every indexed class (C1 ≈ 2,000 × 6 KiB, C2 ≈ 500 × 46 KiB, C3 ≈ 100 × 370 KiB). But the load as written runs into automatic flushes at about 340 MiB of memtable (rec. 3). The unit builder writes 100 KiB of fake data per row, 220 MB for *n* = 2,200 per build (rec. 6). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Read in context: `BigFormatPartitionWriter.java:49-119` (the check at `:113`, the threshold read once at `:73`/`:85`), `:128-205` (`:170-171`, `:181`, the `2 T` buffer at `:204`), `:217-251` (`indexInfoSerializedSize()` = `S` in both modes); `RowIndexEntry.java:216-240` (`create()`), `:341-375` (`size` at `:345`, `:358`, the check at `:360`), `:459-465`, `:484-665` (`IndexedEntry`, weight `:613-620`, `serialize()` `:624-641`), `:671-800` (`ShallowIndexedEntry`, weight `:767-770`, `serialize()` `:773-785`), `:814-840` (`fetchIndex`); `IndexInfo.java:59-163`; `BigTableWriter.java:96-128`, `:410-421`; `BigTableReader.java:215-360` (only the matching key's entry is deserialized, `:325`, cached at `:343`; others skipped, `:349`); `KeyCache.java:60-67`; `CaffeineCache.java:55-70` (weigher = key + value `unsharedHeapSize()`, `ImmediateExecutor`); `CacheService.java:119-135`, `:336-342`; `CacheMetrics.java:69-71`; `KeyCacheKey.java:33`, `:59-61`; `StorageService.java:6789-6826`; `StorageServiceMBean.java:1035-1038`; `DatabaseDescriptor.java:2044-2057`; `Config.java:326-328`; `BigFormat.java:343` (`nb` under `CASSANDRA_4`); `DeletionTime.java:205-340`; `conf/cassandra.yaml:525`, `:797-825`, `:1185-1200`, `:1840-1844`, `:2320`; `RowIndexEntryTest.java:89-280`; `build.xml:33` (locals compiled in, so Byteman can read `size`). |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| 1 | State the read path's operand: `size` = `S + h`, `h` = vint(`headerLength`) + `DeletionTime` (12 B at `nb`) + vint(*n*); read-path class indexed iff `S + h ≤ T`, write path iff `S ≤ T`. The unit boundary step finds both flip points. | Applied 2026-10-14 (9a Prediction; 9a below the Conclusions table; 9e unit amendment); uncommitted | As written, the boundary step and any class near a threshold would be judged against the wrong operand on the read path. |
| 2 | Replace the key-cache-off arm (capacity 0) by a large-cache arm (256 MiB over JMX, `setKeyCacheCapacityInMB`). | Applied 2026-10-14 (9b Controls) | Capacity 0 retains nothing; the arm would not show the uncapped total. |
| 3 | Load whole partitions in order and flush at partition boundaries every ≤ 100,000 rows; the dataset check requires one `write` line per partition and one *n* and `S` per class. | Applied 2026-10-14 (9c amendment) | At 4 GiB the memtable flushes on its own at about a third of 1 GiB: C3 and C4 would be split across SSTables. |
| 4 | Byteman observation (`write`, `read`, `fetch`) for the exact `S`, the branch per read and the index-file reads; the exact forms of the key-cache, census and large-cache rows. | Applied 2026-10-14 (9a Prediction, last bullet; 9c amendment) | The written observables could not separate `S` from the weight, and elapsed time under the page cache cannot show the displaced reads. |
| 5 | Read every class at every value; boundary class CB (*n* = 60 … 80); write-path arm W (`ks1.w` at 16 then 2 KiB); the run order as `cluster-run.py` runs it. | Applied 2026-10-14 (9b Controls, 9c, 9e amendments) | 9e left the class per scenario open; 9b's cluster boundary pair had no step; the write path was observed on the node at one value only. |
| 6 | Unit builder: 1,024 fake bytes per row with `column_index_size` 1 KiB; add *n* = 18,000; assert the `2 T` buffer and `indexSamples()`. | Applied 2026-10-14 (9c, 9e unit amendments) | Same one-block-per-row shape without 220 MB of temporary file per build; a never-indexed analogue of C4; the uncapped buffer term of §8. |
| 7 | §7 "Rough sizing" and §5's weight table: `IndexedEntry.unsharedHeapSize()` does not count the `int[] offsets` array (16 + 4*n* B per entry; `:497`, `:534`, `:613-620`), and an entry restored from the saved cache has `offsets = null` (`:563`). | Left for stage 3 | Not load-bearing (about 2 % of an entry's weight); worth one line in §7. |
| 8 | 9b's `-Xms4G -Xmx4G`: on the node this is `MAX_HEAP_SIZE=4G` (`cassandra-env.sh` sets both). | Left for stage 3 | Cosmetic. |

### 1.2 Instrument checks (not readings)

- **Unit harness:** compiled with `javac` against the clone's classpath before the run; its consistency checks run inside the
  counted unit run (§4).
- **Byteman:** `TestScript` type-checks the six rules of `index-trace.btm` with no errors (re-run by `cluster-run.py` before each
  start; `testscript.txt`); `Submit -l` lists all six on the node.
- **Cluster shakedown 1** (`cluster-run.py instrument`, 17:44–17:46, `pc57:~/stage4-logs/cics/instrument-1/`): 5 C1-shaped and 2
  C2-shaped partitions. `write` lines: C1 *n* 30, `S` 925, `IndexedEntry`; C2 *n* 250, `S` 7,745, `ShallowIndexedEntry`, at
  `T` = 2,048. 9e instrument check passed (2 KiB: a `read … IndexedEntry` line, census 1 `IndexedEntry`, 30 `IndexInfo`; 0: a
  `ShallowIndexedEntry` line, 11 `fetch` lines, census 1 shallow). C2 at 256 KiB indexed (`IndexInfo` 500 = 250 × 2, no `fetch`), at
  0 shallow (30 `fetch` lines, `Entries` +2, 128 B per shallow entry). **Defect found:** `setKeyCacheCapacityInMB` cannot be invoked as
  an operation (`NoSuchMethodException`); JMX exposes it as the write-only attribute `KeyCacheCapacityInMB`. `Jmx.java` gained a
  `setonly` mode, `cluster-run.py` uses it and now stops if the `Capacity` gauge does not follow; 9b's wording corrected (dated, §9a
  unchanged: §9 hash now `384dd3be7d6b8605dd005fb36418cc2e5f35b67f`, §9a still `abf9d963…`).
- **Cluster shakedown 2** (17:46–17:47, `pc57:~/stage4-logs/cics/instrument/`): as above, and the capacity follows (268,435,456, then
  8,388,608). `INSTRUMENT CHECK PASSED`. The one `NO` is the indexed re-cap form, which cannot hold with 2 partitions (demand
  94 KB ≪ 8 MiB) — expected in a shakedown.
- The repository folder and the node copy `~/stage4-harness-run/cics/` are byte-identical (`md5sum`, 17:48). md5s: `cluster-run.py`
  `bb6ba479`, `ColumnIndexThresholdTest.java` `7971464d`, `histo.sh` `315cac36`, `index-trace.btm` `49042573`, `Jmx.java` `f5ecd0ff`,
  `make-node-yaml.sh` `78806fa3`, `send-cql.py` `3768e7f1`, `unit-run.sh` `733b9756`.

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-14: unit 17:38–17:40, cluster 17:52–18:00 EDT (first cluster start 17:48–17:52 stopped at defect 1) | not done |
| Node (CloudLab name and type) | `pc57` = `node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu` (32 cores, 251 GiB); this session ran on it, no ssh | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, `5.15.0-187-generic` | |
| JDK (`java -version`) | OpenJDK 11.0.32.1 | |
| Ant (`ant -version`) | 1.10.12 | |
| Local `cassandra-src` clone commit | `~/cassandra-run1` at `b5f2a54` (`cassandra-5.0.9`) | |
| Case-file commit / harness commit | `986cf19` + uncommitted amendments (§1, §3) / uncommitted (md5s in §1.2; `cluster-run.py` after defect 1 `962f4a71`) | |
| Storage for node data | local disk `/dev/sda3` (`~/cassandra-run1/data`) | |
| Full logs (path, outside the repo) | `pc57:~/stage4-logs/cics/` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | 1 (cluster, first start 17:48–17:52) | 9c amendment "Dataset check" | The check required one `S` per class; C3's partitions have `S` = 63,492 (68) or 63,493 (32). A row's timestamp is encoded against each flush's minimum, so a row can be a byte longer and a block width's vint can change. The run stopped (`FAIL: dataset check failed`) before the sweep: no reading was taken. The other classes passed (C1 925, C2 7,745, C4 511,492; CB *n* 60…80, `S` 1,855…2,475). | One *n* per class and an `S` spread ≤ 1 %, with `S` within ×2 of the target; predictions already use each partition's own `S` from the `write` trace. `cluster-run.py` and 9c amended. §9a unchanged (hash `abf9d963…`); §9 hash now `73420d9b07411fd4c031f967fa951e7ceabf8d88`. | Fixed and the cluster tier restarted from its beginning (fresh node, fresh load), 2026-10-14 17:52; first start's logs kept as `pc57:~/stage4-logs/cics/run1-start1-defect1/` | uncommitted |


## 4. Run 1

**Scope:** unit tier (upstream `RowIndexEntryTest`; `ColumnIndexThresholdTest`, one JVM) and cluster tier (one node, one lifetime: load,
sweep 0 · 2 · 16 · 256 KiB × C1 · CB · C2 · C3 · C4, live flip, large-cache arm, arm W). **Command log:**
`column_index_cache_size-indexSamples-cacheSizeThreshold/run1/` — `unit/` (`harness.out`, `unit-run.log`, `upstream-summary.txt`),
`cluster/` (`summary.txt`, `readings.csv`, `testscript.txt`, `trace-excerpt-CB-and-W.txt`, the large-cache census head and heap,
`summary-start1-defect1.txt`), `instrument/` (both shakedowns), `selfcheck.py` and `selfcheck.txt`. Full logs: `pc57:~/stage4-logs/cics/`
(`run1/index.trace` 8.1 MB, `run1/histo/` 16 MB, `run1/session.log`, `run1/system.log`).

### 4.1 Readings

**Unit tier** (`run1/unit/harness.out`; `S`, `h` in bytes; classes: I = `IndexedEntry`, S = `ShallowIndexedEntry`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Upstream `RowIndexEntryTest` (thresholds 99999 and 0 KiB) | pass, 4 tests | `unit/upstream-summary.txt`, `unit/unit-run.log` |
| `ColumnIndexThresholdTest` | pass: **569 checks, 0 mismatches** | `unit/harness.out` (`STAGE4 done checks 569 mismatches 0`) |
| `S(n)` for *n* = 2 · 10 · 34 · 270 · 2,200 · 18,000 | 59 · 299 · 1,037 · 8,353 · 68,385 · 573,985, the same at every write-time threshold; `h` = 14 · 14 · 14 · 15 · 15 · 16 = 12 + 1 + vint(*n*) | `STAGE4 row` lines |
| Write-path class at *T*w = 0 · 2 · 16 · 256 KiB | I iff `S ≤ T`w: *n* ≤ 34 I from 2 KiB; 270 I from 16 KiB; 2,200 I at 256 KiB only; 18,000 never; all S at 0. `indexSamples()` null and the buffer allocated iff `S > T`w | `STAGE4 row`, checks `_write_class`, `_indexSamples_null…`, `_buffer_allocated…` |
| Read-path class at *T*r = 0 · 2 · 16 · 256 KiB, every (*n*, *T*w) | 96 deserializations, I iff `size ≤ T`r whatever *T*w was (a live change re-flips every entry) | `STAGE4 read` lines |
| Entry weight | `ShallowIndexedEntry` **72 B** for every *n*, *T* and path; read-path `IndexedEntry` 448 · 1,952 · 6,464 · 50,832 · 413,672 B = **188 B per block** exactly; write-path `IndexedEntry` 640 · 2,912 · 9,728 · 76,752 · 624,872 B (284 B per block) | `STAGE4 info`, `STAGE4 row` |
| `2 T` buffer | capacity exactly `2 T` whenever `S ≤ 2 T`; grown past `S` otherwise | checks `_buffer_capacity_*` |
| Boundary at 2 KiB, *n* = 50 … 90 | write class flips after *n*w = 66 (`S` 2,029 / 2,060), read class after *n*r = 66 (`size` 2,043 / 2,074): for this row shape (31 B a block) `h` = 14 is smaller than a block, so both sites flip at the same *n* | `STAGE4 boundary`, `STAGE4 info boundary` |

**Cluster tier** (`run1/cluster/summary.txt`, `readings.csv`; raw `pc57:~/stage4-logs/cics/run1/index.trace`, `histo/`)

Dataset (`write` lines at load, *T* = 2,048): C1 2,000 × *n* 30, `S` 925; CB 21 partitions, *n* 60 … 80, `S` 1,855 … 2,475; C2 500 × *n* 250,
`S` 7,745; C3 100 × *n* 2,000, `S` 63,492–63,493; C4 16 × *n* 16,000, `S` 511,492; one line per partition; 34 `nb-*-big-Data.db`. Write
classes at load: C1 I, C2–C4 S, CB I for *n* ≤ 66.

| Capacity value | Run | Observable (§9d) | Reading | Evidence (file) |
|---|---|---|---|---|
| all | matrix | read-path class (`read` lines, `src=disk`) | indexed reads per *T* = 0 · 2 · 16 · 256 KiB: **C1 0 · 2,000 · 2,000 · 2,000; CB 0 · 6 · 21 · 21; C2 0 · 0 · 500 · 500; C3 0 · 0 · 0 · 100; C4 0 · 0 · 0 · 0**; every disk line on the branch `size ≤ T` (0 mismatches in 2,637 × 4 + arms); `size − S` = 14 (C1, CB), 15 (C2–C4) on every line | `summary.txt` `MATRIX`, `PASS`; `selfcheck.txt` |
| 2 KiB | CB (boundary) | write vs read class | *n* = 60…65 I/I; **66: `S` 2,041 ≤ 2,048, written I; `size` 2,055 > 2,048, read S**; 67…80 S/S | `trace-excerpt-CB-and-W.txt`; `selfcheck.txt` `info CB` |
| all | shallow passes (22) | key cache | `Entries` + *P* exactly; `Size` + **128 B per entry** in every one (72 B entry + 56 B key) | `readings.csv` |
| 2, 16, 256 | indexed C1 | key cache, census | `Entries` 1,454–1,455 of 2,000; `Size` 8,386,672–8,386,752 of 8,388,608 (*w* ≈ 5,768 B); live `IndexedEntry` 1,454, `IndexInfo` 43,620 = 30 × 1,454 | `readings.csv`, `histo/sweep-*k-C1.txt` |
| 16, 256 | indexed C2 | key cache, census | `Entries` 178 of 500; `Size` 8,341,736 (*w* ≈ 46,900 B); `IndexedEntry` 177, `IndexInfo` 44,250 = 250 × 177 | same |
| 256 | indexed C3 (sweep, flip) | key cache, census | `Entries` 23–24 of 100; `Size` 8,274,896 (*w* ≈ 376,100 B); `IndexedEntry` 22, `IndexInfo` 44,000 = 2,000 × 22 | same |
| 16, 256 | CB (all indexed) | census | 21 `IndexedEntry`, `IndexInfo` 1,470 = Σ*n*; `Size` 279,168 (demand below *K*: the re-cap form does not apply) | same |
| all | displaced cost | `fetch` lines; upstream `IndexInfoReads` | shallow passes: 11 · 13 · 15 · 21 · 27 `fetch` lines per read (C1 · CB · C2 · C3 · C4: 22,000 · 273 · 7,500 · 2,100 · 432), `IndexInfoReads` + *P* (+ ≤ 4 system); indexed passes: **0** and + 0 | `readings.csv` |
| all | real resource, heap after a full collection | `GC.heap_info` used | idle 532.0–533.6 MB (spread 1,620 KiB); shallow passes at idle; indexed passes of C1/C2/C3 540.6–542.1 MB (+8.4–8.5 MB, the cache's 8 MiB) | `readings.csv` `heap_used_kb` |
| 256 → 16 | live flip, C3 | class, files | 100/100 I at 256 KiB, then 100/100 S at 16 KiB with no flush; Data.db 34 → 34; no new `ks1.t` `write` line | `summary.txt` `EXPECTED: live flip` |
| 256, K = 256 MiB | large-cache arm, C3 | key cache, census, heap | `Capacity` 268,435,456; `Entries` + 100, `Size` 37,612,880 (376,128 B each); `IndexedEntry` 100, `IndexInfo` 200,000 (8.0 MB); heap 571.2 MB = **+29.99 MB** over the capped pass, cache `Size` **+29.34 MB**; then 16 KiB: + 100 entries at 128 B | `summary.txt` `LARGE vs CAPPED`; `histo-large-256k-C3-head.txt` |
| 16 then 2 | arm W | write-path class on the node | `ks1.w` pk 1–5 flushed at 16 KiB: I, `T=16384` in the line; pk 6–10 at 2 KiB: S, `T=2048`; *n* 250, `S` 7,745 | `trace-excerpt-CB-and-W.txt` |
| — | elapsed | client pass time | C1 shallow 1.46 s, indexed 0.95–1.08 s; the others ≤ 0.4 s (page cache: not judged, §9d) | `readings.csv` |

### 4.2 Conclusion and logic

1. **Validity** — valid. BIG `nb` [observed: `cluster/summary.txt` `DATASET … all nb-*-big: True`]; one `write` line per partition, one *n* a
   class, `S` within ×2 of 1 · 8 · 64 · 512 KiB (925 · 7,745 · 63,492 · 511,492) [observed: `summary.txt` `DATASET`; `selfcheck.txt`]; key
   cache 8 MiB [observed: `INSTRUMENT jmx` `capacity 8388608`]; `column_index_size` 4 KiB and *n* = rows / 4 [observed: `DATASET`]; heap 4 GiB,
   G1 [observed: `JVM heap flags`]; autocompaction off and nothing rewritten [observed: no `ks1.t` `write` line after load, `selfcheck.txt`
   `ks1.t written only at load`]; limit reached and passed: every class is read above and below its `S + h` except C4 (never below, the
   control) [observed: `MATRIX`].
2. **Readings** — four run-script `EXPECTED` lines read `NO`, all CB at 16 and 256 KiB, both from the script's judging, not the readings:
   (a) the indexed re-cap form was applied to CB, whose demand (21 × ≈ 12.7 KB) is below *K* — §9a states the form only for classes whose
   indexed weights exceed *K*; (b) `IndexInfo = n × IndexedEntry` used one *n*, but CB's *n* is 60…80: the census 1,470 equals Σ*n* exactly
   [observed: `selfcheck.txt`]. The C3 indexed pass leaves 23–24 `Entries` with 22 live `IndexedEntry`: the other one or two are system-table
   entries added by the client [observed: `readings.csv`; inferred: the probe's system reads]. At 2 KiB CB is mixed (6 I, 15 S), as predicted.
3. **Matched row** — "Entry class follows `S ≤ T` for every class and threshold (unit and cluster); `unsharedHeapSize()` is linear in *n* for
   indexed and constant for shallow; `Entries` and `Size` move as predicted; the live JMX change re-flips read-path entries with no rewrite →
   **Confirmed**" (with "follows" read as amended: `S ≤ T` written, `S + h ≤ T` read):
   - entry class: unit 24 write-path and 96 read-path cases, cluster every disk read of the sweep and arms, 0 mismatches [observed:
     `unit/harness.out`, `selfcheck.txt`]; the two operands differ on the node exactly where predicted (CB *n* = 66) [observed:
     `trace-excerpt-CB-and-W.txt`];
   - weights: 188 B per block indexed (read path), 72 B shallow for every *n* [observed: `unit/harness.out` `STAGE4 info`]; on the node 128 B
     per shallow cache entry in all 22 shallow passes, and ≈ 5.8 · 46.9 · 376 KB per indexed C1 · C2 · C3 entry [observed: `readings.csv`];
   - `Entries` / `Size`: shallow `Entries` + *P* and `Size` far below *K*; indexed `Size` within one entry of *K* with fewer entries than
     partitions [observed: `readings.csv`, `selfcheck.txt`];
   - live change: the whole sweep ran on SSTables written at 2 KiB, and the 256 → 16 KiB flip re-flipped C3 with no new SSTable [observed:
     `summary.txt`].
4. **Excluded rows** —
   - *Refuted (re-cap):* `Size` stays within one entry of *K* in every indexed pass of a class with demand above *K* (C1, C2, C3) [observed].
   - *Refuted (no change at the predicted T):* the class changes at the predicted *T* for every class, and at the predicted *n* at the
     boundary for both sites (unit *n*w = *n*r = 66; node write ≤ 66, read ≤ 65) [observed]. BIG and multi-block hold (validity).
   - *Write path lags (Confirmed, as §4 says):* not a lag but its premise is shown: arm W's new flush writers use the value in force when they
     are built (16 KiB → I, 2 KiB → S), while SSTables already written keep their on-disk form and the read path ignores it [observed:
     `trace-excerpt-CB-and-W.txt`, `MATRIX`]. Recorded, consistent with the matched row.
   - *Not confirmed (`Entries` does not rise when shallow):* it rises by *P* in every shallow pass [observed].
   - *Total heap flat:* not flat but moved only by the cache's budget: indexed passes +8.4–8.5 MB over idle (*K* = 8 MiB), shallow passes at
     idle; the large-cache arm +29.99 MB against `Size` +29.34 MB [observed: `readings.csv`, `summary.txt`]. Consistent with §8.
   - *Not confirmed (index-file reads do not rise):* 11–27 `IndexInfo` reads from the index file per shallow read, none per indexed read
     [observed: `readings.csv` `fetch_lines`, `iireads_delta`].
   - *Invalid run:* excluded by part 1.
5. **Observed vs. inferred** — the conclusion rests on observed statements. Inferred, not load-bearing: the extra `Entries` in indexed passes
   are system-table entries; the large-cache heap difference is the cached entries (the census shows +78 `IndexedEntry` and +156,000
   `IndexInfo` over the capped pass, which the heap difference matches to 2 %, the `int[] offsets` that the weigher omits being of that order).
6. **Deviations and gaps** — runbook defect 1 (§3) restarted the cluster tier before any reading; the JMX wording fix (§1.2) was found by the
   shakedown. The four run-script `NO` lines are judging defects in `cluster-run.py`, recorded and settled by the self-check from the raw
   files (part 2); `cluster-run.py` is not changed after the run. Elapsed time was recorded but not judged (page cache, §9d). The unit row
   shape could not separate the two operands at the boundary (`h` < one block); the node's row shape did.
7. **Core question** — Logic (1): the classes sit where intended (part 1). (2) At each threshold the classes with `S + h ≤ T` are read as
   `IndexedEntry` and the others as `ShallowIndexedEntry`, so the heap one entry retains is bounded by the threshold — 188 B per block of an
   index no larger than *T* — and above it is a constant 72 B (part 3). (3) The number of indexed entries follows the threshold
   (`MATRIX`). (4) The flip is the only difference: same SSTables, live JMX change, no rewrite (part 3). (5) `Entries` rise and `Size`
   falls when entries go shallow, and `Size` is held at *K* when they are indexed (part 3). **Usage follows the constraint per entry, and the
   node-wide total is capped by `key_cache_size`, not by this knob** (§8): raising the threshold to 256 KiB made each C3 entry 376 KB but left
   the cache at 8 MiB; only removing the cache's cap (256 MiB) let the heap grow by the entries' weight.

**Conclusion (one line):** "Entry class follows `S ≤ T` … the live JMX change re-flips read-path entries with no rewrite" — **confirmed** at
both tiers.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Independent script `run1/selfcheck.py` re-parses the raw `index.trace`, the census files (windowing each pass by their mtimes) and
`unit/harness.out`; the key-cache gauges exist only in `readings.csv` (the run script's JMX reads) and are recomputed from there. Output
`run1/selfcheck.txt`: **169 checks, 0 failed**.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt` dataset lines (one write line per partition, one *n*, `S` spread and ×2); `summary.txt` `DATASET`, `JVM heap flags`, `INSTRUMENT jmx`; `ks1.t written only at load`. |
| 2. Readings | yes | The four `NO` lines re-read in `summary.txt`; Σ*n* for CB = 1,470 = census (`selfcheck.txt`); CB's demand 279,168 B < *K* (`readings.csv`). |
| 3. Matched row | yes | Every disk read on the branch `size ≤ T`, `size − S` = 12 + 1 + vint(*n*) on every line, `IndexInfo` = *n* × `IndexedEntry`, 128 B per shallow entry in every shallow pass, the indexed `Size` bounds, the CB boundary and arm W, all from the raw trace and census (`selfcheck.txt`); unit classes and weights from `harness.out`. |
| 4. Excluded rows | yes | `fetch` counts per pass and `IndexInfoReads` deltas (`readings.csv`, recounted from the trace in `selfcheck.txt`); heap figures (`readings.csv`). |
| 5. Observed vs. inferred | yes | The two inferred statements are not needed for the matched row. |
| 6. Deviations and gaps | yes | Defect 1 log `cluster/summary-start1-defect1.txt` (stopped before the sweep); shakedown summaries in `instrument/`. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | Logic (1)–(5) of §9a each cite a part above. |

### 5.2 Run 2?

**No** — decided 2026-10-14. The conclusion rests on observed statements, every self-check part holds from the raw files, and the result
neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

| Tier | Verdict (§9a row; for a short-path file, the B2g / B3g row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed** — entry class follows `S ≤ T` (write) and `size = S + h ≤ T` (read, live) at 0 · 2 · 16 · 256 KiB and at the boundary; weights linear (188 B/block) and constant (72 B) | run 1 + self-check | 2026-10-14 |
| Cluster | **Confirmed** — the same at every class and value, live over JMX with no rewrite; key cache re-capped at *K*; displaced cost as index-file reads; write path on the node at 2 and 16 KiB; `S + h` boundary seen (*n* = 66) | run 1 + self-check | 2026-10-14 |

**Feedback filed:** the case file's §10 "Stage-4 feedback" (uncommitted). Stage-3 notes (not applied to §1–§8): (1) the read path compares
`S + h`, not `S`, so an entry with `S` in (`T − h`, `T`] is written indexed and loaded shallow (seen at CB *n* = 66); (2) a write-path
`IndexedEntry` weighs 284 B per block against the read path's 188 B (its clusterings are buffer-backed), relevant only where the writer's entry
enters the key cache (key-cache migration on compaction, `BigTableWriter.java:113-125`); (3) `IndexedEntry.unsharedHeapSize()` omits the
`int[] offsets` array (rec. 7). No bypass: §8 and the Target-3 note stand.
