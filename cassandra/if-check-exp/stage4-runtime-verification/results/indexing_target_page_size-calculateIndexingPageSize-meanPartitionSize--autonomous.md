# indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous — stage-4 results  <!-- file: results/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md -->

> **Case:** [`indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous`](../../stage3-ai-deep-read/cases/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/`](../harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/).
>
> **Unit: Confirmed — caps only on some paths (bypass)** (amended B2g rows 1, 4 and 6).
> - T1 (64 KiB blobs, one regular column): `ps` = 563. Pages held 563 / 563 / 563 / 311 rows and at most 36,922,103 B of `Row.dataSize()`, which is 1.10 × 32 MiB.
> - The same data with `cassandra.force_default_indexing_page_size=true`: `ps` = 10000 and one page of all 2,000 rows, 131,162,000 B (3.55 × the default maximum).
> - T2 (zero regular columns, guard `:1164`): `ps` = 10000 and one page of 2,000 rows, 120,042,000 B. T2b, the same table plus one `int` column: `ps` = 595, at most
>   35,726,775 B (1.06 × 32 MiB).
> - T3 (no sstable, guard `:1156`): `meanPartitionSize` = 0.0 and `ps` = 10000.
> - All three repeats of every case were identical.
>
> **Cluster: Confirmed — caps only on some paths (bypass)** (amended B3g row 1). One node, 2 GiB heap, one partition of 12,000 rows of 40,000-char clustering keys per
> table. Live heap was read after a full GC at build start and at each materialized page.
> - Table B (one regular column), K1 unset: `Calculated page size 857` logged in each build, 15 pages of 857 rows (the last 2), and peak − baseline = 35.2 / 35.8 / 35.7 MB.
> - Table B with K1 = true: no log line, `ps` = 10000, pages of 10,000 + 2,000 rows, and a delta of 404.1 / 406.8 / 397.6 MB.
> - Table A (no regular column), K1 unset: the same, 409.1 / 402.0 / 400.9 MB.
> - The bypass deltas are ≥ 11× the default delta.
>
> One runbook defect (D1, cluster attempt 1: the K1 = true restart re-enabled compaction and the node died of OOM). It was fixed in B3c, and the cluster tier was restarted.
> No run 2.
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g (cluster).
> "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`). The case file
> was written by an earlier stage-3 session, not this one.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed with sha256 `ecd9286c…e537` (index §2, "as filed (index batch)"). After the step-0 audit's ten amendments (2026-10-26, before any run-1 reading), frozen at sha256 **`cae4285e0e809f3767278910299a9b787f08456f7de10064bb3ce9d0fc3308b5`**. The unit tier ran at this version. The runbook-defect fix D1 (B3c only; B3f and B3g unchanged) gives sha256 **`e20ec09a93061a6439d4388ebafd6606716da9e0df71731abdf37e5259facae9`**, the version the cluster tier was restarted and run at. Both hashes are new rows in `_INDEX-advisor.md` §2. `run1/freeze.txt` holds them together with the harness and self-check hashes. Section D was filled after these hashes. Nothing was committed, because no commit was asked for. |
| **Harness** | [`../harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/`](../harness/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/): `IndexingPageSizeProbeTest.java` and `unit-run.sh` (B2), `itp.btm`, `gencsv.py` and `cluster-run.sh` (B3). |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM with a 1 GiB heap. Four tables: T1 with K1 ∈ {false, true}, T2, T2b, T3, each measured 3 times. **Cluster (B3):** one node with a 2G heap. Table B with K1 unset and with K1 = true, table A with K1 unset, 3 rebuilds each. The 32 MiB target is a constant and cannot be set (A1). Two things vary instead: the property K1, which skips it, and the schema (zero vs one regular column), which reaches guard `:1164`. Both the unit and cluster designs are filed this way. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Instrument checks before the freeze** (raw shakedown files in `$W/logs/<stem>/shakedown-*`; excerpts in `shakedown/`; none of them is evidence):
- **Unit shakedown 1** (`t3` only; `shakedown/unit-t3-heap1G-summary.txt`) showed that the testsome JVM's max heap is 1,056,309,248 B, not the 4G the case states.
  Shakedown 2 showed that `-Dtest.jvm.args=-Xmx4G` does not override it (`unit2-…`). The source is `maxmemory="1024m"` (`build.xml:1153`), which is appended
  after the jvmargs. Amendment B2a corrects the statement and keeps the default.
- **Byteman:** `TestScript` type-checked all four rules with no errors. The cluster script repeats the check before every start (`run1/cluster/btm-check.txt`).
- **Cluster shakedown 1** (1,200 rows; `shakedown/cluster1-*`): every step ran. The `MemoryMXBean` heap reading, however, was 16.8 MB above gc.log's after-value
  for the same `System.gc()` (78.1 MB vs `->58M`). Under G1 that bean counts eden by whole 16 MiB regions. This is harness defect H1. The rules now print
  `Runtime.totalMemory() − freeMemory()`, and the self-check compares every build's delta with gc.log's `Pause Full (System.gc())` after-values.
- **Cluster shakedown 2** (1,200 rows, 2 repeats; `shakedown/cluster2-summary.txt`, `selfcheck-on-shakedown2.out`): 56 of 56 self-check checks passed.
  Byteman and gc.log deltas agreed within 2.2 MB. Known answer: one page of 1,200 rows of 40,000 B keys read +48.1 MB (40.1 KB per row).
- **Cluster shakedown 3** (600 rows) checked the D1 fix, after cluster attempt 1: the compaction option read back `'enabled': 'false'` in both phases.
- `run1/selfcheck.py` was written before run 1. Its parsers were tested on the shakedowns (`SHAKEDOWN=1`).

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: the heap of one materialized build page (`SecondaryIndexManager.java:1066`) |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | The 32 MiB target is a local constant (A1), so it is not varied. The design compares the default path with two paths that skip the target (K1 and `:1164`), across the same data (B2b, B3b). The reason is given. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: `Row.dataSize()` sums (serialized-size proxy); B2d names the gap (no heap). Cluster as filed: post-young-GC Y and an idle-window baseline. A young pause's after-value includes dead promoted objects, an idle window can hold no GC, and the full page lives only through the indexing loop. Amendment B3d reads the live heap after a full GC at build start and at each materialized page. |
| A. Core question | usage driven to the limit and past it | Met | Unit: 131 MB partitions, ≈ 4 pages at the target. Cluster: 480 MB partitions, ≈ 15 pages at the target; the bypass page is 10,000 rows ≈ 400 MB. |
| B. Logic | each step says what it establishes | Met | B2e, B2h, B3e, B3h |
| B. Logic | prediction stated in numbers or a clear relation | Met | B2f bands; B3f page size 680–980, ≤ 100 MB vs ≥ 350 MB, ≥ 3× |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Verdict words, Effect rules, Invalid rows and the repeat rule added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Disallow evidence: non-last pages hold exactly `ps` rows. Unit, from the probe; cluster, from the `ITP PAGE` rows (amendment B3d). |
| B. Logic | alternative explanations and their controls | Met | K1 on the same data; T2 vs T2b and A vs B differ by one int column; autocompaction off; a static-column index keeps the index memtable small (B2h, B3h) |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1 |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Probe line format, repeat semantics, window marks, debug.log attribution, scripts (amendments B2d, B2e, B3d, B3e) |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The probe's row count excluded the static row (T2 feeds one, `:1094-1100`). The wait for the initial index builds was added (B3c). |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | The filed design assumes Linux, `/local` paths, a `--depth 1` clone, `ant clean jar`, a pid file, and a 4G testsome heap. All fixed (amendments B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | ≈ 960 MB of CSV and ≈ 970 MB of sstables against 131 GiB free. A 400 MB page in a 2 GiB heap (cluster); 131 MB in 1 GiB (unit). |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | See the note below the recommendations. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: host clone `$W/cassandra-run38`, `build-test`, harness probe and runner; heap 1 GiB (`build.xml:1153`), not 4G | Amendment 2026-10-26 | Group D |
| 2 | B2d: probe counts non-static rows (static separately), read thresholds off, `createIndexAsync`, line format | Amendment 2026-10-26 | Group C |
| 3 | B2e: runner, one `@Test` per table, "repeat 3 times" = three measurements on the same data | Amendment 2026-10-26 | Group C |
| 4 | B2g: verdict words, Effect rule, repeat rule, Invalid rows | Amendment 2026-10-26 | Group B |
| 5 | B3a: macOS node layout `$W/node-itp`, `CASSANDRA_CONF`/`CASSANDRA_LOG_DIR`, gc line path, tracked background start, Byteman agent; `HEAP_NEWSIZE` ignored under G1 (recorded, not changed) | Amendment 2026-10-26 | Group D |
| 6 | B3c: `HOME=$W/home` for cqlsh, CSV location, count and tablestats, wait for the initial builds | Amendment 2026-10-26 | Groups C, D |
| 7 | B3d: post-full-GC live heap at build start and at each materialized page (Byteman, observe-only) as the heap observable; returned `ps` on every path; window = the blocking `rebuild_index` call; debug.log attribution by offsets; gc.log Y and `GC.heap_info` kept as secondary | Amendment 2026-10-26 | Group A (the filed instrument cannot see a transient page); group B (disallow evidence) |
| 8 | B3e: one script; raw-file list | Amendment 2026-10-26 | Group C |
| 9 | B3g: verdict words, Effect rule, repeat rule, Invalid rows | Amendment 2026-10-26 | Group B |
| 10 | B4: host paths and cleanup | Amendment 2026-10-26 | Group D |
| 11 | B2a cites `build.xml:1245-1255` for the testsome heap, but that is the `testlist` macro. B3b/B3h say "autocompaction is disabled", but the nodetool switch does not survive B3e's restart (see D1). A3 point (d) says the build reads only the indexed columns; for the cluster's static-column index the 40 KB clustering is still read, so the page is clustering-dominated, which is what B3c intends. | Left for stage 3 (the restart issue was fixed as D1) | Not needed for B1's claim |

**Citations checked** in `~/cassandra-src` (`cassandra-5.0.9`, `b5f2a54210`), all holding:
- `SecondaryIndexManager.java:142, 185, 380-421, 1023-1026, 1036-1145, 1149-1172`;
- `CollatedViewIndexBuilder.java:72-113`; `Index.java:200, 208, 224-226, 593-660`; `CassandraRelevantProperties.java:240`;
- `ColumnFamilyStore.java:936-942, 3110-3134`; `EstimatedHistogram.java:91-109, 235-260`; `MetadataCollector.java:60-69`;
- `AbstractQueryPager.java:95-101`; `BTreeRow.java:522-529`; `Row.java:314`; `CompactionParams.java:123-125`; `CompactionStrategyManager.java:187, 271-273`;
- `conf/logback.xml:41-62`; `conf/jvm11-server.options` (G1, `G1HeapRegionSize=16m`); `conf/cassandra-env.sh:125-128`;
- `test/conf/cassandra.yaml:10, 63-69`; `build.xml:1153, 1245-1255, 1382-1392`; `test/unit/.../StubIndex.java`.

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 18:25:09–18:25:32 EDT; cluster attempt 1 18:25:40–18:28:31; cluster run 18:33:28–18:36:27 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 131 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present; one node on 127.0.0.1. Ports 7000/7199/9042/9091 were free and no Cassandra daemon was running before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: the `ant testsome` forked JVM, `-Xmx1024m` from the junit task. Node: `-Xms2G -Xmx2G`, G1 (16 MiB regions), Byteman 4.0.20 agent (`script:` only) (`JVMARGS` lines in `run1/cluster/summary.txt`). |
| Ant | 1.10.18 |
| Python | 3.8.11 (CSV generator, `cqlsh` COPY, self-check) |
| Local `cassandra-src` clone | `$W/cassandra-run38` = `~/Library/Caches/stage4/cassandra-run38`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 1 min 4 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | Filed at `HEAD` `c5219c8` (sha256 `ecd9286c…e537`). Amendments, harness and results are uncommitted (hashes in §1 and `run1/freeze.txt`). |
| Storage for node data | local SSD under `$W/node-itp` (`conf`, `data`, `commitlog`, `hints`, `saved_caches`, `cdc_raw`, `logs`, `gc.log`), removed at the end of each run |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/indexing_target_page_size-calculateIndexingPageSize-meanPartitionSize--autonomous/` |

What that log directory holds:
- `clone-build-run38.log`, `stepE.txt`, `unit-run.out`, `cluster-run.out`;
- `shakedown-unit*/`, `shakedown-cluster1/`, `-cluster2/`, `-cluster3/`, which are not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `itp.txt`, `summary.txt`, `commands.log`;
- `cluster-attempt1/`: the run stopped by D1, including its node, gc and debug logs;
- `cluster/`: `summary.txt`, `commands.log`, `node.out`, `itp.txt`, `system-{k1unset,k1true}.log`, `debug-k1unset.log`, `debug-k1true.log` (both phases),
  `gc-{k1unset,k1true}.log`, `heapinfo-*.txt`, `compactionstats-*.txt`, `copy-{a,b}.log`, `tablestats-before-index.txt`, `sstables-before-index.txt`, `btm-check.txt`.

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace and commands:**
  - Everything lives under `$W`, and every `ant` call takes `-Dlocal.repository=$W/m2`.
  - Commands touching `$W`, Java or the network ran unsandboxed. `cqlsh` ran with `HOME=$W/home`, because mkdir in `$HOME` is blocked.
  - BSD `stat -f %z` and `sed -i ''`.
- **Node:**
  - There is no `setsid`, so the node runs as a tracked background `bin/cassandra -f`. `JVM_EXTRA_OPTS` is scoped to that command.
  - The daemon pattern in the scripts is split so that `pgrep` does not match the script itself.
  - No ring was needed, so the bootstrap streaming issue does not apply.
- **Instruments:**
  - `jstat` cannot attach, and `GC.heap_info` is not a post-GC value. The heap observable is therefore the used heap right after a forced full GC, printed
    by an observe-only Byteman rule and cross-checked against gc.log.
  - The constant itself is not patched. The design skips it with K1 and with the zero-regular-column schema; both are reachable without Byteman.
- **Unit tests:**
  - `DatabaseDescriptor.daemonInitialization()` runs once per JVM, so the four tables run as four `@Test` methods in one class.
  - The unit yaml's read thresholds are turned off in `@BeforeClass`.
  - Test stdout lands in `build/test/logs/**/TEST-<class>*.log`, one line per write.
- **Authentication:** no guardrail is on this path (`nodetool rebuild_index` → `rebuildIndexesBlocking`; `cqlsh` COPY of 40 KB rows with no guardrail
  configured), so the default `AllowAllAuthenticator` was kept.
- **Run hygiene:**
  - Shakedowns ran before run 1, and every bound came from source.
  - Baselines were taken after ingest and after a forced GC.
  - Long steps ran in the background and were polled with sleeps under 2 minutes.
  - `selfcheck.py` was written before run 1. Raw excerpts were not edited after capture.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| A1 | audit | B2a, B3a, B4 | Linux and `/local` paths, `--depth 1` clone, `ant clean jar`, a pid file, a 4G testsome heap that testsome does not get | Host paths and layout; heap statement corrected to 1 GiB (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted (sha256 `cae4285e…`) |
| A2 | audit | B3d | The filed heap observable (post-young-GC Y, idle-window baseline) cannot see a page that lives only through the indexing loop | Post-full-GC live heap at build start and at each materialized page (amendment B3d); B3f numbers unchanged | 2026-10-26, before the freeze | uncommitted (sha256 `cae4285e…`) |
| H1 | shakedown | harness | `MemoryMXBean` heap used reads up to one 16 MiB eden region high under G1 | Rules print `Runtime` used bytes; gc.log cross-check in the self-check | 2026-10-26, before the freeze | none (harness only; `run1/freeze.txt`) |
| **D1** | run 1, cluster attempt 1 | B3c step 4 / B3e step 5 | `nodetool disableautocompaction ks` does not survive the restart. The K1 = true node started compacting the four sstables of `ks.a` and `ks.b` at `Startup complete` (22:27:52.659 UTC). G1 humongous allocations grew to 88 regions, and 3 s later the node died with `OutOfMemoryError: Java heap space` (`-XX:OnOutOfMemoryError kill -9`). All three K1 = true rebuilds failed with `Connection refused`. Evidence: `run1/cluster-attempt1/defect-D1-compaction-oom.txt`, `summary.txt`. | Step 4 also sets `ALTER TABLE … WITH compaction = {'class':'SizeTieredCompactionStrategy','enabled':'false'}` for both tables, which is stored in the schema; the script reads it back in both phases. B3f/B3g unchanged. | 2026-10-26; the cluster tier restarted from its beginning at sha256 `e20ec09a…` | uncommitted (sha256 `e20ec09a…`) |
| S1 | run 1, self-check | harness | Against attempt 1, `selfcheck.py` v1 let an empty run pass its `all(...)` predictions vacuously, and derived row 1 with no K1 = true reading (`cluster-attempt1/selfcheck-v1-on-attempt1.out`, outside the repo) | An empty run now gives **Invalid run**; D1 checks added (compaction option read back, no `ks.a`/`ks.b` compaction). Fixed before the restarted cluster run. | 2026-10-26 | none (`run1/freeze.txt`, second block) |

The phase-1 readings of attempt 1 (B default and A, 3 builds each) are kept outside the repo. They are not used for the verdict.
Attempt 1 read B-default deltas of 35.3 / 35.8 / 35.7 MB and A deltas of 408.8 / 401.7 / 400.8 MB.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `…/run1/unit/commands.log` and `…/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/test-log-itp-lines.txt`, `summary.txt`, `ant-tests-run.txt`.
- Ant: `Tests run: 4, Failures: 0, Errors: 0`.
- `ITP SETUP read_thresholds_enabled=false maxHeap=1056309248`.
- Each case gave the same line in all 3 repeats, and the property read back equal to K1.

| Case | sstables | meanPartitionSize / meanCells / regular cols | `ps` (B2f band) | pages: rows | max bytes per page (B2f) | static rows |
|---|---|---|---|---|---|---|
| T1, K1=false | 2 | 66,679,644 / 1,119 / 1 | **563** ([420, 620]) | 4: 563, 563, 563, 311 | **36,922,103** = 1.10 × 32 MiB ([0.8, 1.25]) | 0 |
| T1, K1=true | 2 | same | **10000** (exactly) | 1: 2,000 | **131,162,000** (≈ 131 MB; 3.55 × the K1=false max, ≥ 3×) | 0 |
| T2 (0 regular cols) | 2 | 63,063,925 / 1 / 0 | **10000** (exactly) | 1: 2,000 | **120,042,000** (≈ 120 MB) | 1 |
| T2b (+ `v int`) | 2 | 63,063,925 / 1,119 / 1 | **595** ([450, 700]) | 4: 595, 595, 595, 215 | **35,726,775** = 1.06 × 32 MiB ([0.8, 1.25]) | 1 |
| T3 (no flush) | 0 | 0.0 / 0 / 1 | **10000** | 1: 10 | 655,810 | 0 |

- Arithmetic (`:1167-1170`) for T1: 66,679,644 / (1,119 / 1) = 59,589 B estimated per row, so ⌊33,554,432 / 59,589⌋ = 563.
- The real row is 65,581 B (`maxRowDataSize`). The estimate is 9% low because the two histograms' bucket offsets differ (A3 (c)). The page therefore holds 1.10 × the target.
- T2b: 63,063,925 / 1,119 = 56,357 B estimated per row (real 60,045 B), giving 595.

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `itp.txt`, `calculated-page-size-lines.txt`, `gc-*-system-gc-pauses.txt`, `heapinfo-all.txt`, `copy-*-tail.txt`,
`tablestats-before-index.txt`, `yaml-diff.txt`.

Setup and validity:
- COPY imported 12,000 rows into each table (rc 0), and `count(*)` = 12,000 for each.
- 4 sstables per table: table A is 483,571,615 B live, table B 483,471,851 B.
- The compaction option read back `'enabled': 'false'` in both phases, and debug.log holds 0 compaction tasks on `ks.a`/`ks.b` data.
- JVM arguments: `-Xmx2G`, G1, the agent, and `-Dcassandra.force_default_indexing_page_size=true` in phase 2 only.
- `HEAP_NEWSIZE has erroneously been set and will be ignored` was printed at both starts, as B3a notes.
- No ERROR or `OutOfMemoryError` line; only start-up WARNs. No agent error.

`ITP PS` gave meanPartitionSize / meanCells / regular cols as follows:
- table B: 127,271,406.75 / 3,252 / 1, giving `ps` = 857 (estimated row 39,136 B);
- table A: 136,508,134.25 / 1 / 0, giving 10000.

| Run | Rep | logged page size (debug.log, in window) | `ITP PS` | pages: rows | baseline (START) MB | peak (PAGE) MB | **Δ MB** | gc.log System.gc() Δ MB (cross-check) |
|---|---|---|---|---|---|---|---|---|
| Table B, K1 unset | 1 | 857 | 857 | 15: 14 × 857, 2 | 478.4 | 513.5 | **35.2** | 35.7 |
| | 2 | 857 | 857 | same | 471.0 | 506.8 | **35.8** | 35.7 |
| | 3 | 857 | 857 | same | 478.7 | 514.4 | **35.7** | 35.7 |
| Table B, K1 = true | 1 | none | 10000 (prop=true) | 2: 10,000, 2,000 | 75.2 | 479.2 | **404.1** | 401.6 |
| | 2 | none | 10000 | same | 70.0 | 476.7 | **406.8** | 401.6 |
| | 3 | none | 10000 | same | 80.6 | 478.1 | **397.6** | 401.6 |
| Table A, K1 unset | 1 | none | 10000 (prop=null) | 2: 10,000, 2,000 | 471.0 | 880.1 | **409.1** | 401.6 |
| | 2 | none | 10000 | same | 478.1 | 880.1 | **402.0** | 401.6 |
| | 3 | none | 10000 | same | 479.3 | 880.1 | **400.9** | 401.6 |

- Per row: 35.7 MB / 857 = 41.7 KB, and 401.6 MB / 10,000 = 40.2 KB, against a 40,000-char clustering key.
- Secondary readings, not used for B3g:
  - The `GC.heap_info` sampler took 3 samples per ≈ 1 s build. Its maximum used was 481–482 MiB for B default, 526–542 MiB for A and 200–334 MiB for B forced.
    It never reached the 479–880 MB page peaks, which is the sampling gap amendment B3d expected.
  - gc.log max after-value over all pauses in the window: 482M, 831M and 441–443M.
- The phase-1 baseline (471–479 MB) is higher than phase 2's (70–81 MB), which follows ingest. The deltas are per build.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/ant-tests-run.txt`, `test-log-itp-lines.txt`]
   - The 4 tests passed, and every case printed 3 lines.
   - `prop` matched K1, and read thresholds were off.
   - The T1 and T2b partitions span 4 pages, so the limit was reached.
2. **Readings** — Nothing unusual. The repeats are identical. The estimate is below the true row size, by 9% (T1) and 6% (T2b), so the pages hold
   1.10× and 1.06× the target, within B2f's ±25%. [observed; arithmetic inferred from `:1167-1170` and the printed statistics]
3. **Matched row** — amended B2g "Confirmed — caps only on some paths (bypass)". [observed: `test-log-itp-lines.txt`]
   - Row 1: T1 K1=false has `maxBytes` 1.10 × 32 MiB and `ps` 563 ∈ [420, 620]. K1=true gives one page of 2,000 rows, 131.2 MB, 3.55× the default.
   - Row 4: T2 `ps` = 10000 with one page of 2,000 rows, while T2b `ps` = 595 ∈ [450, 700].
   - Row 6: T3 `ps` = 10000 with `meanPartitionSize` = 0.0.
   - Disallow evidence: in T1 and T2b every non-last page holds exactly `ps` rows (563 or 595).
4. **Excluded rows** — [observed]
   - Row 2 (Refuted, does not cap): T1 K1=false `ps` is 563, not 10000, and its maximum page is 36.9 MB, not 131 MB.
   - Row 3: 36.9 MB is well above 10 MB.
   - Row 5 (Refuted in part (ii)): T2 `ps` 10000 ≠ T2b `ps` 595.
   - Row 7 (Invalid): K1=true gave exactly 10000 with `prop=true`.
5. **Observed vs. inferred** — The only inferred statement is that `ps` is `⌊32 MiB / (meanPartitionSize / (meanCells / cols))⌋`. The self-check recomputes it
   from the printed statistics for all 15 lines, and every recomputation matches.
6. **Deviations and gaps** — Heap is 1 GiB, not the stated 4G (amendment B2a); it does not affect any observable. Bytes are `Row.dataSize()` (serialized), not on-heap
   size, as B2d says. `measureDeep` (optional) was not done.
7. **Core question** — Yes, with a bypass.
   - With the property unset and one regular column, the rows per page follow 32 MiB / estimated row size, and page bytes stay at 1.06–1.10 × 32 MiB for 60–65 KB rows (part 3).
   - The same data with the target skipped, by K1 or by having zero regular columns (`:1164`), puts the whole 2,000-row partition in one 120–131 MB page (parts 3, 4).

**Conclusion (unit):** amended B2g "Confirmed — caps only on some paths (bypass)" — confirmed.

**Cluster tier**

1. **Validity** — Valid, at the D1-fixed version. [observed: `cluster/summary.txt`, `itp.txt`]
   - Both tables were fully loaded and nothing compacted them.
   - Every `rebuild_index` returned rc 0 with one START/PS/END and 15 or 2 PAGE lines, and the rows summed to 12,000.
   - The property read-back matched each phase.
   - In every build, the gc.log count of `System.gc()` pauses equals 1 + pages, and its delta matches the Byteman delta within 7.5 MB.
2. **Readings** — The repeats agree within 0.6 MB (B default) and 9.2 MB (bypass). The B-forced and A pages hold the same 10,000 rows and give the same heap delta
   (397.6–409.1 MB). [observed]
3. **Matched row** — amended B3g "Confirmed — caps only on some paths (bypass)" (filed row 1). [observed: `calculated-page-size-lines.txt`, `itp.txt`]
   - B-default delta ≤ 100 MB: 35.2–35.8 MB.
   - B-forced and A deltas ≥ 350 MB: 397.6–409.1 MB, and ≥ 3× the default (minimum 397.6 vs 3 × 35.8 = 107.4).
   - Logged page size 857 ∈ [680, 980] in each B-default build. No line for B-forced or A, whose `ITP PS` is 10000.
   - Disallow evidence: 14 pages of exactly 857 rows before the last.
4. **Excluded rows** — [observed]
   - Row 2 (Refuted, does not cap): B default 35.7 MB is not ≈ B forced 404 MB.
   - Row 3 (all small): the bypass deltas are ≈ 400 MB.
   - Row 4 (A small): A is 400.9–409.1 MB.
   - Row 5: no OOM.
   - Invalid rows: the property matched, every rebuild had rc 0, the counts were 12,000, and PAGE lines are present.
5. **Observed vs. inferred** — Two inferred statements:
   - The full GC in the rule runs while the page is still referenced, so the delta is the page's live heap. The cross-checks support this: about 40 KB per row
     for 857 rows and for 10,000 rows, and gc.log agrees.
   - The baseline does not hold the previous build's pages. Each START reading follows a full GC after the previous build ended.
6. **Deviations and gaps** — Defect D1 restarted the tier; B3f and B3g are unchanged. The heap observable is the amended one; the filed gc.log Y and `GC.heap_info` are
   reported as secondary readings. Each `System.gc()` stops the build for 22–49 ms (`gc-*-system-gc-pauses.txt`). This changes timing, not page sizes.
7. **Core question** — Yes, with a bypass.
   - On a real node, the page computed from the 32 MiB target (857 rows of ≈ 40 KB) held 35.7 MB of live heap per build (parts 3, 7).
   - Skipping the target (K1) or a table with no regular column (`:1164`) gave pages of 10,000 rows and ≈ 400 MB, 11× more, on the same data and node (parts 3, 4).

**Conclusion (cluster):** amended B3g "Confirmed — caps only on some paths (bypass)" — confirmed.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` (sha256 in `run1/freeze.txt`) re-read the raw files: `unit/ant.log`, `unit/TEST.log`, and `cluster/summary.txt`, `node.out` (sliced by the
MARK byte offsets), `debug-k1true.log` (sliced by the debug offsets) and `gc-{k1unset,k1true}.log`. It recomputed `ps`, re-derived both rows, and
cross-checked the heap deltas against gc.log. Output: `run1/selfcheck.out`, **125 checks, 125 pass, 0 fail**; derived rows: unit and cluster "Confirmed — caps only on some
paths (bypass)".

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `TEST.log`: 4 tests, 15 lines, `prop` = K1. Cluster `summary.txt`: COPY/COUNT 12,000, compaction option read back, 0 `ks` compactions, rc 0 for all 9 rebuilds, `daemons_left=0`, clone clean. |
| 2. Readings | yes | Repeats identical (unit); deltas re-read from `node.out` windows match §4.1 to 0.1 MB. |
| 3. Matched row | yes | Each part of B2g rows 1/4/6 and B3g row 1 re-evaluated by the script (`PRED … holds`, 8 unit + 7 cluster). |
| 4. Excluded rows | yes | The script's row derivation checks rows 2, 3, 5 (unit) and rows 2, 3, 4 (cluster) before row 1. |
| 5. Observed vs. inferred | yes | `ps` recomputed for 15 unit lines and 9 cluster builds; the gc.log delta agrees within 8 MiB in all 9 builds. |
| 6. Deviations and gaps | yes | D1 and S1 recorded in §3; the attempt-1 readings are not used. |
| 7. Core question | yes | The steps follow B1 (i) then (ii), with K1 as the positive control on the same data. |

### 5.2 Run 2?

**No** — 2026-10-26. Both conclusions rest on observed readings with an independent cross-check (gc.log) and a recomputed operand. Neither refutes the case.
The bypass is the one the case filed (A3 (a)), and attempt 1's phase-1 readings repeat the run's B-default and A deltas to within 8 MB.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive, with a bypass (case file Estimate line).

**Claim tested** (B1):
- (i) With the property unset and a table with at least one regular column, the rows held per build page are ≈ 32 MiB / meanRowSize, so the heap per page stays near 32 MiB.
- (ii) With `cassandra.force_default_indexing_page_size=true`, or a table with zero regular columns (guard `:1164`), the page is `min(10000, partition rows)` rows, and its heap
  grows with row size with no byte bound.

| Tier | Verdict (B2g / B3g row, as amended) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed — rows 1, 4, 6. Pages of 563 / 595 rows hold 1.10 / 1.06 × 32 MiB; K1 or zero regular columns gives one page of 2,000 rows (131 / 120 MB). | caps only on some paths (bypass) | run 1 + self-check | 2026-10-26 |
| Cluster | Confirmed — row 1. A page of 857 rows held 35.7 MB of live heap; K1 or zero regular columns gives pages of 10,000 rows, ≈ 400 MB. | caps only on some paths (bypass) | run 1 (after fix D1) + self-check | 2026-10-26 |

**Feedback filed:**
- The case file's section D was updated (uncommitted). The case's Estimate and section A need no change, since the run confirmed the filed bypass.
- `_INDEX-advisor.md`: two new §2 rows (frozen `cae4285e…`, D1 fix `e20ec09a…`) and the §1 Stage 4 column.
