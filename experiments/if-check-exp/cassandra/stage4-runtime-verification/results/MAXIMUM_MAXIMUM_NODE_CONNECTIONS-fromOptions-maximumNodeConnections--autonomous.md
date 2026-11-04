# MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous — stage-4 results  <!-- file: results/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.md -->

> **Case:** [`MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous`](../../stage3-ai-deep-read/cases/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/`](../harness/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/).
>
> **Unit: Confirmed — caps** (B2g row 4).
> - `maximum_node_connections` 16, 64, 256 and 512 were accepted. 513 and 1024 were rejected with `Maximum number of connections for
>   index null cannot be <= 0 or > 512, was <M>`.
> - jvector's on-disk graph for 5,000 vectors (dim 8) was 840,016, 2,760,016, 10,440,016 and 20,680,016 B at M = 16, 64, 256, 512:
>   strictly increasing and linear at 40,000 B per unit M. That is 8·N per unit M, not the filed 4·N, because `maxDegree()` = 2·M.
>   Beam width 400 at M = 16 gave the same 840,016 B.
>
> **Cluster: Confirmed — caps** (B3g row 4). One node, the same 20,000 vectors in each table.
> - The `idx_513` CREATE INDEX was refused with the check's message, and the other four indexes were created.
> - TermsData was **3,360,039 / 21,280,039 / 82,720,039 B** at M = 16 / 128 / 512, the same after flush and after a major
>   compaction. Every value equals the re-traced 39 + N·(40 + 8M) to the byte. The filed N·(40 + 4M) ± 1% was not met.
> - The beam-400 control equalled t_16 exactly. PostingLists (480,039 B) and CompressedVectors (88,252 B) were identical across tables.
>
> No run 2.
>
> **Agent:** autonomous. In this file, "§9a" means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster). "§9b–§9e" means B2a–B2e or B3a–B3e. The case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5[1m]), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).
> An earlier stage-3 session wrote the case file; this session did not.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | As filed: sha256 `a195e044…0a36` (`_INDEX.md` §4; in git `HEAD`). Frozen after the step-0 audit's fourteen amendments (2026-10-26, before any run-1 reading) at sha256 **`f60348fb01dd7d0f33aa3ec3923f3ad65f9a427984fb4ace77019f362936336d`**. Both tiers' readings were taken at this version. A new row was added to `_INDEX.md` §4. `run1/freeze.txt` holds this hash plus the harness and self-check hashes. Section D was filled after the verdict (file sha256 now `b83d98e8…d63e`); everything above section D still hashes to `f60348fb…336d`. Nothing committed: no commit was asked for. |
| **Harness** | [`../harness/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/`](../harness/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/) (Notes 1–3 below the table) |
| **Tiers and values** | **Unit (B2):** one `ant testsome` JVM. Test A: M ∈ {16, 64, 256, 512, 513, 1024}. Test B: (M, beam) ∈ {(16,100), (64,100), (256,100), (512,100), (16,400)}; N = 5000, dim 8. **Cluster (B3):** one node, heap 2G; tables t_16, t_128, t_512, t_16b400 (20,000 rows each, `vector<float,8>`), plus t_513 (index attempt only). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

**Note 1, harness files:**
- `MaxNodeConnectionsCapTest.java`: a `CQLTester` subclass holding Test A (CQL `CREATE CUSTOM INDEX`) and Test B (jvector
  `GraphIndexBuilder` + `OnDiskGraphIndex.write`). It prints `PROBE` lines and makes no assertions.
- `unit-run.sh`: copies the test in, runs `testsome`, keeps the logs, removes the test.
- `probe.py`: a bundled-driver client (setup, load, count).
- `files.py`: SAI component sizes per table from `os.stat`.
- `cluster-run.sh`: the whole cluster tier in one node lifetime.

**Note 2, instrument checks before the freeze:**
- **Unit shakedown** with N = 500 (`shakedown/unit1-N500-summary.txt`). It ran as written and left the clone clean. It found one
  problem in this session's own amendment text: the rejection message names the index `null`, not the generated name.
  `StorageAttachedIndex.validateOptions` calls `fromOptions(null, …)` (`StorageAttachedIndex.java:278`). Amendments B2f and B3f were
  corrected, with a dated note, before the freeze. The filed prediction ("cannot be <= 0 or > 512") is unaffected.
- **Cluster shakedown** with 2,000 rows per table (`shakedown/cluster1-rows2000-summary.txt`). Three problems were found, and all were
  fixed before the freeze; no prediction was touched.
  - The compaction wait loop matched `pending tasks: 0`, but 5.0 prints `pending tasks   0`, so the loop waited out its 120 s. The
    regex was fixed in `cluster-run.sh`.
  - `selfcheck.py` cut the server message at the `]` of `[Invalid query]`. Its regex was fixed.
  - The class histograms showed far less than 16·M B of `int[]`/`float[]` per node at large M. `javap` on
    `ConcurrentNeighborSet.mergeNeighbors` shows that merges replace a node's first `int[2M]`/`float[2M]` with arrays sized by the
    actual neighbour count. Amendment B3d had given that as a heap floor (context only, not a verdict condition). B3d and B2e were
    corrected, with a dated note.

**Note 3, self-check:** [`run1/selfcheck.py`](MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/run1/selfcheck.py)
was written before run 1. After the regex fix it scored 43/43 on the two shakedowns (`shakedown/selfcheck-on-shakedown.out`).
Its sha256 `751a1daa…1498` is in `run1/freeze.txt` and was unchanged for run 1.

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: graph bytes per vector, on disk (TermsData) and on heap. M counts neighbour slots, and bytes per slot follow from the format. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met (other approach) | The constant 512 is a compile-time `static final` (`IndexWriterConfig.java:38`), inlined into the comparison, so it cannot be varied without a patch. The design varies its operand M over four values (unit) or three (cluster), including the default 16 and the bound 512, and tries 513 and 1024. This answers "does the cap bound usage?" because usage follows M and M cannot pass 512. |
| A. Core question | real resource measured, not only the counter | Met / Partly | Disk: real file sizes in both tiers. Heap: the unit tier has only jvector's estimate (gap named in amendment B2d). The cluster tier reports class-histogram live bytes, but they are not a verdict condition (amendment B3d). |
| A. Core question | usage driven to the limit and past it | Met | 512 accepted; 513 (and 1024 in the unit tier) refused. |
| B. Logic | each step says what it establishes | Met | B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Met → amended | Exact filed formula. The format was flagged "from memory; stage 4 must confirm" (A3.5/A5), so the bytecode re-trace was added as separate re-traced expectations. The filed predictions were kept, not replaced (amendments B2e, B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | Rows lacked verdict words. Row 5 ("re-trace") had no verdict. No Invalid rows (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Size follows M; the direct disallow evidence is the check's own `InvalidRequestException` text (`IndexWriterConfig.java:133`). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Same data and seed; the beam-width control was in B2h/B3h but not in the cluster tier's knobs, so table `t_16b400` was added (amendment B3c). Other components flat. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Vector generation, output format, flush order, file listing (amendments B2c, B2d, B3c, B3d). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Same amendments. |
| D. Runnable | harness and environment prerequisites exist or are listed | Not met → Met after amendment | `/tmp/c509`, Linux, `ant jar`, `bin/cassandra -p` did not fit this host (amendments B2a, B3a, B4). |
| D. Runnable | workload arithmetic reaches the limit | Met → amended | Disk < 120 MB. With a 2 GiB heap, the default memtable flush threshold (≈ 171 MiB) was near the t_512 memtable's charged graph (≈ 165 MB), so `memtable_heap_space` was set to 1024 MiB and each table flushed alone (amendments B3a, B3c). Load concurrency 8 for jvector's builder pool. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Note 4. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: host clone, property by `System.setProperty`, no `test.jvm.args` | Amendment 2026-10-26 | Paths; the property is read per call. |
| 2 | B2c: exact vectors and Test B cases including (16, 400) | Amendment 2026-10-26 | Group C; B2h control. |
| 3 | B2d: output format; heap gap | Amendment 2026-10-26 | Group C. |
| 4 | B2e: step 1 done at audit; bytecode re-trace (2M) | Amendment 2026-10-26 | A3.5/A5 asked for it. |
| 5 | B2f: re-traced expectations beside the filed ones; rejection text | Amendment 2026-10-26 (text corrected before the freeze) | Group B. |
| 6 | B2g: verdict words, Invalid/Not confirmed rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 7 | B3a: host node, heap 2G, `memtable_heap_space` 1024MiB, tracked node | Amendment 2026-10-26 | Paths; flush threshold. |
| 8 | B3c: tables incl. t_16b400, data, concurrency 8, flush per table | Amendment 2026-10-26 | B3h control; jvector pool. |
| 9 | B3d: files.py, tablestats, driver text, histograms reported | Amendment 2026-10-26 (heap context corrected before the freeze) | Group C. |
| 10 | B3e: one script; optional step 5 not run | Amendment 2026-10-26 | Step 5 asks a different question. |
| 11 | B3f: re-traced exact TermsData and texts | Amendment 2026-10-26 | Group B. |
| 12 | B3g: verdict words, added rows, Effect rule | Amendment 2026-10-26 | Group B. |
| 13 | B3h: beam control table; summing rule | Amendment 2026-10-26 | Group B. |
| 14 | B4: host paths and checks | Amendment 2026-10-26 | Paths. |
| 15 | Correct A3.4/A3.5/B1: jvector 1.0.2's `maxDegree()` is 2·M, so the per-vector graph disk bound at M = 512 is 8 + 4·dim + 4096 B, not + 2048 | Left for stage 3 (section D) | A stage-3 trace error; the filed table still names the outcome (row 4). |
| 16 | Test the heap side with a real-heap observable: retained neighbour arrays follow the actual degree, not M | Left for stage 3 | Not a verdict condition here; see §4.2 part 2. |
| 17 | Optional B3e step 5: what a restart without the property does to existing custom-option indexes (`StorageAttachedIndex.java:200`) | Left for stage 3 | A different question. |

**Note 4, citations checked** in `~/cassandra-src` at `cassandra-5.0.9`: `IndexWriterConfig.java:37-39, 104-134`; `OnHeapGraph.java:96-117,
140-190, 306-365`; `StorageAttachedIndex.java:198-200, 276-279, 1003-1008`; `CassandraRelevantProperties.java:439, 465`;
`Version.java:45, 56, 138-152`; `IndexComponent.java:51`; `SAICodecUtils.java:47-58, 261-269`; `StorageAttachedIndexOptions.java:26`;
`VectorTypeTest.java:279-300`; `.build/parent-pom-template.xml:1239-1241`; `conf/cassandra.yaml:797, 811, 825`; `conf/cassandra-env.sh:51-68`;
`CQLTester.java:1218-1234, 1489-1509`. jvector 1.0.2 (`javap -c -p`): `OnHeapGraphIndex.<init>`, `maxDegree`, `addNode`,
`ramBytesUsedOneNode`, `neighborsRamUsed`; `GraphIndexBuilder.<init>`, `addGraphNode`; `OnDiskGraphIndex.write`;
`ConcurrentNeighborSet.<init>`, `mergeNeighbors`; `NeighborArray.<init>`; `PoolingSupport$ThreadPooling`. All hold. A3's claim
"maxDegree() is M" does not hold (it is 2·M).

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 (unit 18:59:26–18:59:51 EDT; cluster 18:59:58–19:02:45 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab (`run1/stepE.txt`) |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (Apple M1 Pro) |
| Hardware | 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 130 GiB free |
| Network and processes | Loopback 127.0.0.1–.3 present (one node on 127.0.0.1). Ports 7000/7199/9042 free and no daemon before the run; none after. |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit: `ant testsome` forked JVM. Node: `-Xms2G -Xmx2G`, G1 |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip` (subfolder import), protocol 5 |
| Local `cassandra-src` clone | `$W/cassandra-run39` = `~/Library/Caches/stage4/cassandra-run39`, a fresh clone of `~/cassandra-src` at `cassandra-5.0.9`, `b5f2a54210d541339c2e7c17a794195cac0e67c2`. `ant -Dlocal.repository=$W/m2 build-test`: `BUILD SUCCESSFUL` in 50 s. `git status` clean after both tiers. |
| Case-file commit / harness commit | filed version in `HEAD` (`06be79e`); amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-mnc/{data,commitlog,hints,saved_caches,cdc_raw,logs}` and `gc.log`, own `conf/`; wiped before and after |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/` |

Full-log contents, under that directory:
- `clone-build-run39.log`, `stepE.txt`, `unit.out`, `cluster.out`;
- `shakedown/` (`unit1/`, `cluster1/`, `cluster1.out`, `selfcheck-on-shakedown.out`), which is not evidence;
- `unit/`: `ant.log`, `TEST.log`, `TEST.xml`, `probe.txt`, `commands.log`, `summary.txt`;
- `cluster/`: `node.out`, `system.log`, `gc.log`, `histo-{before,after}-<table>.txt`, `commands.log`, `summary.txt`,
  `debug-graph-lines.txt`, `yaml-*`, `jvm-server-options-added.txt`, `error-warn.txt`, `client.err` (empty).

**Machine facts relied on** (from `environment-advisor.md` and earlier runs on this host):
- **Workspace:** every file lives under `$W`; every `ant` call takes `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the
  network ran unsandboxed.
- **Node start:** no `setsid`, so the node is a tracked background `bin/cassandra -f`. The daemon pattern in the scripts is split so
  `pgrep -f` never matches the script itself.
- **Unit test output:** `build/test/logs/**/TEST-<class>.log`, one line per write. `CQLTester.formatQuery` takes one `%s` (only `%s`
  table placeholders were used). Read thresholds did not matter: the test reads nothing back.
- **Driver:** bundled driver, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, heartbeat off, connect retry. It has
  `VectorType`, so the load binds vectors in a prepared statement. `client.err` is empty.
- **jvector builder pool:** `availableProcessors() + 1` = 11 concurrent memtable inserts (`PoolingSupport$ThreadPooling`, re-read with
  `javap` here), so the load concurrency is 8.
- **Heap instruments:** `jstat` cannot attach, so `jcmd GC.class_histogram`. Its totals are post-full-GC live bytes, because the
  histogram forces a full GC: 8 `Pause Full (Heap Inspection Initiated GC)` events in `gc.log`, no other full GC. `GC.heap_info`, MAT
  and jmxterm were not used.
- **Authentication:** the option check has no client-state test (`IndexWriterConfig.java:104-134`), so it is not a guardrail and the
  superuser exemption is irrelevant. `AllowAllAuthenticator` was kept.
- **Script hygiene:** long steps ran in the background and were polled; shakedowns ran before run 1; all bounds were derived from
  source and bytecode; `selfcheck.py` was written before run 1. Byteman was not needed (the constant is not varied).

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| A1 | audit | B2a/B3a/B4 | `/tmp/c509`, Linux, `ant jar` (no test classes), `bin/cassandra -p` (no `setsid` here) | host paths; `build-test`; tracked `bin/cassandra -f` (amendments B2a, B3a, B4) | 2026-10-26, before the freeze; §9a unchanged | uncommitted |
| A2 | audit | B3b/B3h | The B3h beam-width control has no table in B3b/B3c | table `t_16b400` (amendments B3c, B3h) | 2026-10-26, before the freeze | uncommitted |
| A3 | audit | B3a/B3c | With a 2 GiB heap, the default flush threshold (≈ 171 MiB) is close to the t_512 memtable's charged graph (≈ 165 MB); one flush after all loads would also mix memtables | `memtable_heap_space: 1024MiB`; flush per table (amendments B3a, B3c) | 2026-10-26, before the freeze | uncommitted |
| A4 | shakedown | B2f/B3f (amendment text) | The rejection names the index `null` (`StorageAttachedIndex.java:278`), not the generated name | amendment text corrected with a dated note | 2026-10-26, before the freeze; filed prediction unchanged | uncommitted |
| A5 | shakedown | B3d (amendment text) | The heap "floor" of 16·M B per node contradicts `mergeNeighbors` | context sentence corrected with a dated note; not a verdict condition | 2026-10-26, before the freeze | uncommitted |
| A6 | shakedown | harness | The compaction wait regex did not match the 5.0 `compactionstats` format; the `selfcheck.py` regex cut the message at `]` | regexes fixed | 2026-10-26, before the freeze | n/a (harness) |

Run 1: none. Both tiers ran as written at the frozen version.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `MAXIMUM_MAXIMUM_NODE_CONNECTIONS-fromOptions-maximumNodeConnections--autonomous/run1/unit/commands.log`,
`…/run1/cluster/commands.log`.

### 4.1 Readings

**Unit tier.** Sources: `run1/unit/summary.txt` and `probe.txt`. The `PROBE` lines are identical to those in the full `TEST.log`
(`run1/crosscheck.txt`).
- Ant `rc=0`, `Tests run: 1, Failures: 0, Errors: 0`, 9.5 s.
- `PROP allow_custom_parameters=true MAXIMUM_MAXIMUM_NODE_CONNECTIONS=512 DEFAULT_MAXIMUM_NODE_CONNECTIONS=16 N=5000 dim=8`.
- Test A: M = 16, 64, 256 and 512 were accepted. M = 513 and 1024 were rejected with root `InvalidRequestException`: `Maximum number
  of connections for index null cannot be <= 0 or > 512, was 513` (and `was 1024`).

| M | beam | maxDegree | fileBytes | filed 16+N(40+4M) | re-traced 16+N(40+8M) | sumAddBytes | Δ sumAddBytes | max / mean neighbours |
|---|---|---|---|---|---|---|---|---|
| 16 | 100 | 32 | **840,016** | 520,016 | 840,016 | 1,605,000 | — | 32 / 32.00 |
| 64 | 100 | 128 | **2,760,016** | 1,480,016 | 2,760,016 | 5,445,000 | 3,840,000 | 128 / 124.31 |
| 256 | 100 | 512 | **10,440,016** | 5,320,016 | 10,440,016 | 20,805,000 | 15,360,000 | 402 / 191.26 |
| 512 | 100 | 1024 | **20,680,016** | 10,440,016 | 20,680,016 | 41,285,000 | 20,480,000 | 402 / 191.26 |
| 16 | 400 | 32 | **840,016** | 520,016 | 840,016 | 1,605,000 | — | 32 / 32.00 |

`graphSize` was 5000 in every case, and every temporary file was deleted (`tmpDeleted=true`; `unit-run.sh` counted 0 left).

**Cluster tier.** Sources: `run1/cluster/summary.txt`, `debug-graph-lines.txt`, `histo-*-head.txt`, `yaml-overrides.txt`,
`jvm-server-options-added.txt`, `error-warn.txt`.

Setup and validity:
- The property was read back from the daemon's `ps` arguments and from the `JVM Arguments` line. Heap `-Xms2G -Xmx2G`, G1;
  `memtable_heap_space=1024MiB` read back from `system.log`.
- idx_16, idx_128, idx_512 and idx_16b400 were accepted, with their options in `system_schema.indexes` (`construction_beam_width: 400`
  on idx_16b400). **idx_513 rejected**: `InvalidRequest: Error from server: code=2200 [Invalid query] message="Maximum number of
  connections for index null cannot be <= 0 or > 512, was 513"`. idx_513 appears nowhere in `system.log`.
- Each load: 20,000 ok, 0 failed, 3.1–3.4 s. The vector sum was −3.005365 for every table, so the data were identical. `count(*)`
  was 20,000 for each table.
- `debug.log` shows 8 × `Writing graph with 20000 rows and 20000 distinct vectors` (4 flushes + 4 compactions) and 8 × `Computing PQ
  for 20000 vectors`.
- `ERROR` = 0; `java.lang.OutOfMemoryError` = 0. The only `OutOfMemoryError` strings are the JVM flags `-XX:+HeapDumpOnOutOfMemoryError`
  and `-XX:OnOutOfMemoryError` (`crosscheck.txt`). The WARN lines are start-up notices and "Aggregation query used without partition
  key" from the `count(*)` queries.

SAI component sizes (B), one SSTable per table in both listings (generation 1 after flush, 2 after compaction):

| Table (M, beam) | TermsData after flush | after compaction | filed 20,000·(40+4M) | re-traced 39 + 20,000·(40+8M) | PostingLists | CompressedVectors |
|---|---|---|---|---|---|---|
| t_16 (16, 100) | **3,360,039** | 3,360,039 | 2,080,000 | 3,360,039 | 480,039 | 88,252 |
| t_128 (128, 100) | **21,280,039** | 21,280,039 | 11,040,000 | 21,280,039 | 480,039 | 88,252 |
| t_512 (512, 100) | **82,720,039** | 82,720,039 | 41,760,000 | 82,720,039 | 480,039 | 88,252 |
| t_16b400 (16, 400) | **3,360,039** | 3,360,039 | 2,080,000 | 3,360,039 | 480,039 | 88,252 |

Slope: (21,280,039 − 3,360,039)/112 = (82,720,039 − 21,280,039)/384 = **160,000 B per unit M** = 8·N.

Heap (reported, not a verdict condition): class-histogram live bytes before and after each table's load, before its flush.

| Table | Δ live total | Δ `[I` | Δ `[F` | memtable charge for neighbour slots, 20,000·16·M |
|---|---|---|---|---|
| t_16 | +35.5 MB | +4.9 MB | +5.3 MB | 5.1 MB |
| t_128 | +52.7 MB | +16.7 MB | +17.1 MB | 41.0 MB |
| t_512 | +55.1 MB | +17.9 MB | +18.3 MB | 163.8 MB |
| t_16b400 | +40.6 MB | +9.6 MB | +10.1 MB | 5.1 MB |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — Valid. [observed: `unit/summary.txt`]
   - The property was read back `true`, and the constant read 512.
   - `graphSize` was 5000 in every case, and the test passed with all 14 `PROBE` lines present.
   - The beam control equalled the M = 16 case, and the limit was passed (513 and 1024).
2. **Readings** — Two points worth noting.
   - `maxDegree()` is 2·M, as the step-0 bytecode re-trace said (amendment B2e) and not the filed M. [observed]
   - At M = 256 and 512, the real neighbour count saturates at max 402 and mean 191.26, identical for both. So the graph's actual
     degree for these data is set by the data, not by M, once 2·M exceeds it; only the padded on-disk slots keep following M.
     [observed: max/mean columns; inferred: identical structure at 256 and 512]
3. **Matched row** — B2g row 4, "size grows with M but not by 4·N per unit M — format differs from the trace; the claim holds if it is
   monotone", made **Confirmed** by amendment B2g. [observed]
   - 513 and 1024 were rejected with the check's text.
   - `fileBytes` is strictly increasing (840,016 < 2,760,016 < 10,440,016 < 20,680,016) and linear at 40,000 B per unit M = 8·N,
     equal to the re-traced formula to the byte.
   - `sumAddBytes` is strictly increasing, with differences exactly 16·N·ΔM.
4. **Excluded rows**
   - Row 1 (file size matches the filed formula): every size is about 1.6–2× the filed value.
   - Row 2 (513/1024 accepted): both were rejected.
   - Row 3 (size constant across M): 20,680,016 ≠ 840,016.
   - Row 5 / added rows: `maxDegree()` is 2·M, which amendment B2g places in row 4. Monotone, linear and the rejection text all hold,
     so Not confirmed does not apply. Every validity condition holds, so Invalid does not apply.
5. **Observed vs. inferred** — The verdict rests on observed values only. Inferred and not used by the verdict: that the graph
   structure at M = 256 and 512 is the same (equal max and mean neighbour counts suggest it).
6. **Deviations and gaps** — None in the run. The heap side in this tier is jvector's estimate only (named in amendment B2d).
7. **Core question** — The check refuses any M above 512 (direct disallow evidence: the check's own message). On-disk graph bytes
   follow M linearly, 40,000 B per unit M for 5,000 vectors. So the constant bounds per-vector graph disk at the M = 512 value:
   8 + 4·8 + 4·1024 = 4,136 B per vector here, not the filed 2,088.

**Unit tier conclusion:** B2g row 4 — **confirmed**. Effect (amended B2g): **caps**.

**Cluster tier**

1. **Validity** — Valid. [observed: `cluster/summary.txt` READBACK, SETUP, LOAD, COUNT, FILES, ERRORS lines]
   - The property was read back twice. Loads were 20,000 ok and `count(*)` 20,000 for each table, with identical data (vector sum).
   - One SSTable per table in each listing; no ERROR, no OOM; the node stopped cleanly.
   - The limit was passed (idx_513 refused).
2. **Readings** — Points worth noting.
   - TermsData equals the re-traced 39 + N·(40 + 8M) to the byte in all 8 listings. [observed] The filed ±1% band around N·(40 + 4M)
     is missed by 61–98%.
   - The major compaction rebuilt every graph (generation 2; 4 more "Writing graph" lines) with identical sizes. [observed]
   - **Heap does not follow M above the natural degree.** Retained `int[]` + `float[]` rose 10.2 → 33.8 MB from M = 16 to 128, but
     only to 36.2 MB at M = 512. The memtable is charged 16·M B per node (163.8 MB at M = 512, about 4.5× what the arrays hold), and at
     M = 16 a wider beam (400) retained more arrays (19.7 MB) than M = 16 at beam 100. [observed: `histo-*`; inferred: arrays sized by
     the actual degree, per `mergeNeighbors`] This is a reported reading, not a B3g condition (amendment B3d). It bears on B1(b)'s
     "heap per graph node likewise": the real heap per node is bounded by 2·M slots but follows the data's degree, not M.
3. **Matched row** — B3g row 4, "sizes differ but not linearly [as filed] — format differs; the claim holds if monotone and bounded at
   512", made **Confirmed** by amendment B3g. [observed]
   - idx_513 was refused with the check's message, and the other four indexes were created.
   - TermsData is strictly increasing t_16 < t_128 < t_512 and linear at 160,000 B per unit M (8·N).
   - t_16b400 = t_16 exactly, and PostingLists and CompressedVectors are identical across tables.
   - The after-compaction listing gives the same row.
4. **Excluded rows**
   - Row 1 (TermsData within ±1% of 4·N·M scaling): missed by 61–98%.
   - Row 2 (513 accepted): it was refused.
   - Row 3 (same across M): 82,720,039 vs 3,360,039.
   - Added Not confirmed: the order is monotone, the beam control equal, the other components identical, and both listings agree.
   - Added Invalid: every validity condition holds.
5. **Observed vs. inferred** — The verdict rests on observed values only. Inferred and not used by the verdict: why the retained
   heap saturates (array sizing from the bytecode).
6. **Deviations and gaps** — None in the run.
   - Heap was read with class histograms only around each load. The 1.2·M overflow during construction (A3.6) was not isolated.
   - Optional B3e step 5 was not run (amendment B3e).
7. **Core question** — Usage follows the constraint's operand on disk. TermsData grows exactly 160,000 B per unit M for 20,000
   vectors, at M = 16, 128 and 512, after flush and after compaction. An index with M = 513 cannot be created. So the 512 cap bounds
   per-vector graph disk (4,136 B per vector at dim 8). It does not bound the total, which grows with N, as the file says.

**Cluster tier conclusion:** B3g row 4 — **confirmed**. Effect (amended B3g): **caps**.

## 5. Self-check of run 1 — AI

`run1/selfcheck.py` was written before run 1 (sha256 in `run1/freeze.txt`, unchanged). It re-parses the unit `summary.txt` and the
cluster `summary.txt`. It recomputes every filed and re-traced value from the case file's formulas with its own code, and names the
B2g and B3g rows. Output `run1/selfcheck.out`: **43 checks, 43 pass, 0 fail**:
- U0–U15: 16 unit checks. It names the row **Confirmed (row 4: slope 40000 per unit M = 8N re-traced)**; its INFO lines record that the
  filed formula and `maxDegree == M` do not hold.
- C1–C18: 27 cluster checks (C10–C16 once per listing). It names the row **Confirmed (row 4: linear, slope 160000 per unit M)** for both
  listings.

Raw-file cross-checks outside the script (`run1/crosscheck.txt`):
- the `PROBE` lines of the full `TEST.log` are identical to `summary.txt`'s;
- the `Writing graph … 20000 distinct vectors` lines (8);
- the `JVM Arguments` line (`-Xmx2G`, the property);
- no `idx_513` in `system.log`;
- the OOM strings are JVM flags only;
- the histogram `Total` lines;
- the 8 full GCs are the histograms.

### 5.1 Check of run 1's conclusion

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | U0, U1, U5, U6, U11, U15; C1–C3, C7–C11, C17, C18; READBACK and JVM Arguments lines re-read in `system.log` |
| 2. Readings | yes | `summary.txt` re-read: maxDegree 32/128/512/1024; neighbours 402 / 191.26 at both M = 256 and 512; histogram heads re-read for the heap deltas |
| 3. Matched row | yes | U3, U4, U8–U10, U12, U13; C4, C5, C12–C16 for both listings |
| 4. Excluded rows | yes | INFO lines: the filed formula is off in both tiers (row 1 excluded); no acceptance above 512; sizes not constant |
| 5. Observed vs. inferred | yes | The two inferred statements (identical structure at 256/512; array sizing) are not used by the verdict |
| 6. Deviations and gaps | yes | Defects A1–A6 fixed before the freeze. The shakedown fixes touched amendment text (rejection name, heap context), the harness and `selfcheck.py`; no filed prediction or verdict condition was changed after a run-1 reading |
| 7. Core question | yes | The check refuses M > 512 (direct evidence: its message) and disk follows M linearly in both tiers, so the cap bounds per-vector graph bytes on disk |

### 5.2 Run 2?

**No** — 2026-10-26.
- Every verdict statement is observed, and the sizes are exact to the byte against a bytecode-derived formula in both tiers.
- The self-check settles every part from run 1's files.
- The verdict confirms the file's own claim through its row 4. That is not a refutation and not a bypass, although the stage-3
  formula was wrong by a factor of 2 in the degree (section D).

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested (B1):**
- (a) `maximum_node_connections` > 512 is rejected, so no index can be built with M > 512;
- (b) graph bytes per vector follow M up to that bound: on disk, TermsData ≈ N·(8 + 4·dim + 4·M) + constant, so the cap limits
  per-vector graph disk (and heap per graph node likewise).

"Confirmed" below means this claim held, as the filed conclusions table reads it ("the claim holds if monotone").

| Tier | Verdict | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (B2g row 4) | **caps** | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (B3g row 4) | **caps** | run 1 + self-check | 2026-10-26 |

1. **Unit:** M = 513 and 1024 are refused by the check. jvector's graph file is 16 + N·(40 + 8M) B, strictly increasing and linear in M
   (840,016 → 20,680,016 B for M = 16 → 512); beam width does not change it.
2. **Cluster:** idx_513 is refused. TermsData is 3,360,039 / 21,280,039 / 82,720,039 B at M = 16 / 128 / 512 (20,000 vectors) after
   flush and after compaction; beam width and the other SAI components do not change.
3. **The filed format was wrong by a factor of 2.** jvector 1.0.2 sets `maxDegree()` = 2·M, so each vector stores 2·M neighbour slots.
   The bound at M = 512 is 8 + 4·dim + 4096 B per vector, not + 2048. B1(b)'s heap clause holds only as a bound: retained neighbour
   arrays follow the data's actual degree (flat from M = 128 to 512 here), while the memtable is charged 16·M B per node.

**Positive control:** not required, since this is not a negative-estimate file. The M sweep itself, with the beam control and the
flat components, shows that the instrument sees M.

**Feedback filed:**
- The case file's section D is updated (uncommitted).
- Amendments B2a, B2c–B2g, B3a, B3c–B3h and B4 are in the case file (uncommitted).
- `_INDEX.md`: §2 row `f60348fb…336d` added, and the §1 Stage 4 column filled.
- `HANDOFF.md` not edited (`HANDOFF-ADVISOR.md` §8).
