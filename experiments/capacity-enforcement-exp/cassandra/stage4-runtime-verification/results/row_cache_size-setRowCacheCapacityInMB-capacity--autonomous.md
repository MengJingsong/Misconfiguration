# row_cache_size-setRowCacheCapacityInMB-capacity--autonomous — stage-4 results  <!-- file: results/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.md -->

> **Case:** [`row_cache_size-setRowCacheCapacityInMB-capacity--autonomous`](../../stage3-ai-deep-read/cases/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps** (run 1; closed, not re-run). **Cluster: Confirmed — caps**
> (cluster re-run "run 1b" of 2026-10-27 at the re-frozen version `219ff0f9…d4f`, after the user-authorised amendment of B3d, B3e,
> B3f (iii), B3g, B3h and B4; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/`](../harness/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/).
>
> **Run-1 status (as filed 2026-10-26):** verdict filed, 2026-10-26. **Unit: Confirmed — caps. Cluster: Not confirmed — caps** (the cache's own size is capped exactly at every C; process RSS follows C in slope, but the yaml-set and runtime-set C = 64 runs differ by 18 %, beyond the frozen ± 15 %).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `21fd9d5a…e464` (service batch). Frozen after the step-0 audit's seventeen amendments and the fixes of runbook defects 1 and 2 (all 2026-10-26, all before run 1): sha256 **`f6890ca6bf92814dcc97663f789da8bb5c19fc95e52498e41c42dfb70dd96635`**, at which both tiers' run 1 ran; a new row in `_INDEX.md` §4. Section D was filled after this hash. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/`](../harness/row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/): `RowCacheCapacityProbeTest.java` (B2c–B2e as amended), `unit-run.sh`; `make-node-conf.sh` (copied from the bloom_filter_fp_chance validate case's harness, with the clone, node paths and cluster name changed and the NMT line added), `RcsJmx.java` (JMX poller, one-shot reader, and the −1 call), `cluster-run.sh` (B3e as amended). Not committed. Instrument checks: (i) the test class compiled in the run clone (`BUILD SUCCESSFUL`, [`run1/unit/compile-summary.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1/unit/compile-summary.txt)); (ii) a unit shakedown (`RCP_SHAKE=1`, N = 8,000) ran every step ([`shakedown/unit-shake-summary.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/shakedown/unit-shake-summary.txt)); (iii) cluster shakedowns (N = 30,000; control 64, capped 8/4/2, yaml 4, RT shrink to 4): the first two stopped on runbook defects 1 and 2 (§3), the third ran every step and left nothing running ([`shakedown/cluster-shake-summary.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/shakedown/cluster-shake-summary.txt)); it showed that `RcsJmx neg` called a JMX operation that does not exist (a void one-argument `set…` method of a standard MBean is a write-only attribute), so `neg` was changed to `setAttribute("RowCacheCapacityInMB", -1L)` and checked on a short-lived node ([`shakedown/jmx-neg-instrument-check.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/shakedown/jmx-neg-instrument-check.txt)) — a harness fix, not a case-file change; (iv) `run1/selfcheck.py` was written before any run-1 reading and its parsers were exercised on both shakedowns. Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): C = 16, 8, 4, 2, 1 MiB (runtime setter, after invalidation), N = 40,000 rows of 1,024 B; second pass at C = 1; step 4 (refill at 16, shrink to 1 without invalidation, 2,000 misses); C = −1. Cluster (B3): one node, 1 GiB heap, 300,000 partitions (5 × 200 B columns); BASE (`rows_per_partition: NONE`), R512 (control), R128 / R64 / R32 (fresh node at yaml 512, C set by `nodetool setcachecapacity 0 C 0`), Y64 (yaml 64), RT (read 200,000 keys at 512, shrink to 64, read the other 100,000, then −1 through JMX). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone, and in OHC 0.5.1's
sources (`ohc-core-0.5.1-sources.jar` from Maven Central, unpacked under `$W/tools-rcs/ohc-src/`; the version from
`.build/parent-pom-template.xml:41`).

**What the source says, derived at the audit.**
- *The check* (`CacheService.java:327-333`): `capacity < 0` throws `RuntimeException("capacity should not be negative.")`; otherwise `rowCache.setCapacity(capacity × 2^20)` → `InstrumentingCache` → `OHCacheAdapter.setCapacity` → `OHCacheLinkedImpl.setCapacity`.
- *The runtime setter evicts nothing.* `OHCacheLinkedImpl.setCapacity` (`:655-665`) adds `(new − old)/segments` to each segment's free capacity (`OffHeapLinkedMap.updateFreeCapacity`, `:166-176`); eviction happens only in a put into that segment (`putEntry`, `:283-307`, while free < `allocLen`, evict the LRU tail). A hit puts nothing. A3 step 2 ("OHC evicts to the new capacity") is therefore true only after inserts — the B2b/B2e and B3b/B3e amendments add a shrink of a full cache followed by misses.
- *Cap arithmetic.* `allocLen` = 64 + roundUp8(keyLen) + valueLen (`linked/Util.java:89-92`); `memUsed` = capacity − Σ free (`:1205-1207`); segments = `roundUpToPowerOf2(2 × availableProcessors)` (`OHCacheBuilder.java:152`): 4 in the unit JVM (`-XX:ActiveProcessorCount=2`, `build.xml:136`, `:1170`), 32 on the node. So used ≤ C·2^20 exactly after puts, and a full cache holds ≥ C·2^20 − segments·allocLen.
- *Native memory.* OHC allocates each entry with JNA `Native.malloc` (`Uns.java:182-193`, `JNANativeAllocator`; logged `OHC using JNA OS native malloc/free` on every node start), invisible to NMT. On this host `malloc_good_size(n)` = 1,536 for 1,025 ≤ n ≤ 1,536 (macOS small zone, 512-B quantum; read with `ctypes` at the audit), so a ~1.2 KB entry costs g = 1,536 B of native memory — the filed "+ ≤ 15 %" band was re-expressed with g.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: OHC off-heap bytes (`memUsed`) and process RSS. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach | Met | B2b: five values incl. the yaml start 16; B3b: four plus a yaml repeat. (The shipped default 0 disables the cache — `NopCacheProvider`; B1 is conditional on an enabled cache.) |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit names its gap (counter only); cluster RSS with a no-cache baseline; amended with the macOS allocation unit g and OHC's eviction count. |
| A. Core question | usage driven to the limit and past it | Met | Unit demand 47 MB > 16 MiB; cluster 360 MB vs 32–128 MiB; R512 control under the cap. |
| B. Logic | each step says what it establishes | Partly → Met after amendment | Steps added for the runtime shrink of a full cache. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "small fraction", "within one sampling interval" given numbers; exact cap and fill bound; dEvict = N − entries. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Rows had meanings without verdicts; added guard, runtime-shrink, ambiguous-native and invalid rows. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Disallow = eviction; OHC `getEvictionCount()` added (unit); refused −1 on both tiers. |
| B. Logic | alternative explanations and their controls | Met | BASE run for non-cache RSS, fresh process per run, key/counter/chunk caches off; amended with compaction off and evidence per control. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | B3b (runtime set) and B3e (yaml restart) disagreed; reconciled. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Output lines, exact JMX gauges, poller cadence, run order, checks. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local`, `/proc`, Linux; macOS `ps`; no `setsid`. |
| D. Runnable | workload arithmetic reaches the limit | Met | 300,000 × 1.2 KB = 360 MB > 128 MiB and < 512 MiB; ≈ 320 MB on disk of 128 GiB free; 1 GiB heap + ≤ 0.5 GiB native of 32 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Every line cited in A1–A5 matches (yaml :564, Config :472-474, DD :3916-3919, MBean :54, nodetool :30-42, NodeProbe :1088-1094, CacheService :146-147/:329/:332, OHCProvider, jvm-server.options :128, tests). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, runner, output from the test log | Amendment 2026-10-26 (uncommitted) | `/local`, Linux. |
| 2 | B2b/B2e: step 4 — shrink a full cache at runtime, then miss | Amendment 2026-10-26 | Entry pointer otherwise exercised only on an empty cache; OHC evicts lazily. |
| 3 | B2c: order and data | Amendment 2026-10-26 | Open. |
| 4 | B2d: `RCP` lines; OHC eviction/put-fail counts by reflection | Amendment 2026-10-26 | Format open; direct disallow evidence. |
| 5 | B2e: stop condition | Amendment 2026-10-26 | Open. |
| 6 | B2f: segments, exact cap, fill bound, dEvict = N − entries, step 3/4 values, guard message | Amendment 2026-10-26 | Derived. |
| 7 | B2g/B2h: verdicts per row; added rows; control evidence | Amendment 2026-10-26 | Group B. |
| 8 | B3a: this host; node dir; `ps` for RSS; start method | Amendment 2026-10-26 | Linux paths. |
| 9 | B3b/B3e: fresh node per run, C by the runtime setter, one yaml repeat; RT shrinks after 200,000 keys and misses on 100,000; −1 by JMX | Amendment 2026-10-26 | B3b/B3e disagreed; RT as filed could not evict. |
| 10 | B3c: commands; major compaction then compaction disabled; caching per run | Amendment 2026-10-26 | Open; identical sstables in every run. |
| 11 | B3d: exact JMX gauges every 2 s; NMT as context; malloc unit g | Amendment 2026-10-26 | Exact readings; platform allocation unit. |
| 12 | B3e: order, checks, shakedown | Amendment 2026-10-26 | Open. |
| 13 | B3f: Size cap and fill, R512 entries, ρ band with g, slope, Y64 vs R64, RT lazy then capped, −1 | Amendment 2026-10-26 | Derived; filed RT prediction contradicted the OHC source. |
| 14 | B3g/B3h/B4: verdicts per row; added rows; control evidence; paths | Amendment 2026-10-26 | Group B. |
| 15 | A3 step 2 should say that a capacity decrease takes effect per segment at the next insert, not at the call | Left for stage 3 (section D) | Confirmed by the readings. |
| 16 | A test of `row_cache_size: 0` (Nop provider) with a non-zero runtime set (`UnsupportedOperationException`, A1) | Left for stage 3 | Not in B1. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (clone 21:40:53–21:40:59, build 21:40:59–21:41:49; audit, OHC sources and amendments to 23:08; compile check 23:09; unit shakedown 23:10:54; cluster shakedowns 23:11:47 (defect 1), 23:16:31 (defect 2), 23:22:19–23:34:00; JMX instrument check ≈ 23:35; freeze 23:35; unit run 1 23:36:17–23:36:40; cluster run 1 23:37:03–23:49:51) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM; internal SSD (APFS), 128 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042, 9091 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork, `-XX:ActiveProcessorCount=2`. Node: `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (`-Xms1G -Xmx1G`, `-XX:NativeMemoryTracking=summary`, read from `JVM Arguments`) |
| Ant | 1.10.18 |
| Python | 3.8.11 (cqlsh; self-check; `ctypes` for `malloc_good_size`) |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run44` (fresh clone, `ant -Dlocal.repository=$W/m2 build-test`, `BUILD SUCCESSFUL` in 50 s); `W=~/Library/Caches/stage4`; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-rcs44` (data, commit log, hints, saved caches), wiped before and after each cluster run |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/row_cache_size-setRowCacheCapacityInMB-capacity/` — `clone.log`, `build-test-run44.log`, `unit-compile/`, `unit-shake/`, `unit-r1/` (ant log, JUnit XML, test log, `stdout.txt`, `summary.txt`), `cluster-shake-defect1/`, `cluster-shake-defect2/`, `cluster-shake/`, `jmx-check/`, `cluster-run1/` (`commands.log`, `summary.txt`; per run `write/ BASE/ R512/ R128/ R64/ R32/ Y64/ RT/`: `node/` logs, `stress-*.txt`, `samples.csv`, `rss.txt`, `info-*.txt`, `nmt-*.txt`, `tablestats.txt`, `compactionhistory.txt`, `schema.txt`, `yaml-tail.txt`; `RT/neg.txt`) |

Machine facts relied on (from `environment-advisor.md` and the session brief): all files under `$W` (no `mkdir` in `$HOME`; cqlsh with `HOME=$W/home`); every `ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run outside the tool sandbox; no `setsid` (node started as a tracked `nohup … -f &` process, pid from `$!`, stopped by drain and `kill <pid>`; the daemon name split in the scripts' patterns); BSD tools (`ps -o rss=` instead of `/proc/<pid>/status`, `du -sk`); no jmxterm (own JMX client); test stdout from `build/test/logs/**/TEST-<class>.log`, one line per `println`; the unit yaml's read thresholds are irrelevant here (single 1 KB rows read internally); `nodetool disableautocompaction` does not survive a restart, so the table option `compaction = {…, 'enabled':'false'}` was used (evidence: the same three `keyspace1` compactions, all from the write phase, in every run's history); fresh process per run (distinct pids); shakedowns before run 1; long steps in the background, polled; bounds derived from source; `selfcheck.py` written before readings. No guardrail is on the path (row cache reads and a JMX/nodetool capacity set; no guardrail reads `row_cache_size` in 5.0.9), so the authenticator was left as shipped.

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| 1 | cluster shakedown (before run 1 and the freeze) | B3c read command (as amended) | `cassandra-stress read … -pop seq=…` without the write's `-col size=FIXED(200) n=FIXED(5)` validates rows against the default column spec: 50 × `Data returned was not validated`, then `Failed to execute warmup`, exit 1 ([`shakedown/defect1-stress-read-excerpt.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/shakedown/defect1-stress-read-excerpt.txt)). | Every read carries `-col size=FIXED(200) n=FIXED(5)`; stress's default warmup is kept. B3f/B3g unchanged. | Dated amendment "runbook defect 1", 2026-10-26; tier restarted | uncommitted (in the frozen version) |
| 2 | cluster shakedown (before run 1 and the freeze) | B3c caching per run (my B3c amendment) | R64 read 37,500 times (7,500 warmup + 30,000) with `rows_per_partition: 'ALL'` and stored nothing (0 entries): the node had preloaded its prepared statements at start-up under `'NONE'` (`Preloaded 2 prepared statements` 03:19:04 UTC, `ALTER … 'ALL'` 03:19:06 UTC), and a caching-only ALTER does not invalidate them (`QueryProcessor.java:1082-1087`, `TableMetadata.changeAffectsPreparedStatements` `:661-670`), so the read command took `cacheRows()` from stale metadata (`SinglePartitionReadCommand.java:547-558`) ([`shakedown/defect2-R64-excerpt.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/shakedown/defect2-R64-excerpt.txt)). | BASE sets `'ALL'` back after its read, before its stop; R512 sets nothing. B3f/B3g unchanged. | Dated amendment "runbook defect 2", 2026-10-26; tier restarted | uncommitted (in the frozen version) |

Neither run 1 tier hit a defect.

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-27 by the cluster re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3f (iii), B3g row 1 / added row (b) | The frozen RSS relations failed: ρ 1.343 (R64) and 1.191 (R32) outside [0.85, 1.15], and Y64's ΔRSS 18.0 % below R64's against ± 15 %; the tier was Not confirmed through row (b)'s Y64 clause (§4.2). RSS includes what the macOS allocator does with OHC's JNA mallocs, which Cassandra's source does not determine. | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** six dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` — B3d (instrument (5): an observe-only Byteman ledger at OHC's own bookkeeping points `Uns.allocated`/`Uns.freed`), B3e (fresh clone, agent, checks), B3f (iii) (ρ and the Y64-vs-R64 RSS relation become records; the strict increase and slope stay; added (iii′-1)–(iii′-6) on the ledger, derived from the OHC 0.5.1 and Cassandra source), B3g (row 1 read with (iii′); rows (c) extended, (d), (e) added), B3h (BASE as the ledger's null control), B4 (paths). New sha256 `219ff0f9…d4f` as a new row in `_INDEX.md` §4. The whole cluster tier re-run from its beginning in a fresh clone (§7). B1, B3f (i), (ii), (iv), the strict increase and slope, and the unit tier unchanged. | user, 2026-10-27 | sha256 `219ff0f9…d4f` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a/B3e paths | `cluster-run.sh` and `make-node-conf.sh` were fixed to run 1's clone (`cassandra-run44`) and node (`$W/node-rcs44`). | Both read `RCS_C` and `RCS_NODE`; the defaults reproduce run 1; run labels `run2`/`shake2` take run 1's / the shakedown's values. | AI, 2026-10-27 | n/a (harness) |
| H2 | cluster re-run | B3d (5), B3e (amended) | Run 1's harness had no ledger. | New `RcsLedger.java` (Byteman helper and MBean `stage4:type=RcsLedger`) and `rcs-ledger.btm`; with `RCS_BM=1`, `cluster-run.sh` compiles the helper, runs `TestScript` (abort on an error), starts every node with the agent, records the agent check per run, and takes `RcsJmx ledger` one-shots (start, end; RT before the set, after it, after the misses). `RcsJmx.java`: a `ledger` command and twelve ledger columns appended after `rss_kib` in `poll` (the first ten columns unchanged). New `LedgerKnownAnswer.java` (the instrument's known-answer check outside Cassandra) and `excerpt.sh` (copies excerpts; reads only). Without `RCS_BM` the script behaves as in run 1. sha256 prefixes: `cluster-run.sh` `c3f164fa` (run 1) → `3dacd562`; `make-node-conf.sh` `06f450b3` → `ee0f805a`; `RcsJmx.java` `75766142` → `3fb3950c`; new `RcsLedger.java` `0673e2b6`, `rcs-ledger.btm` `9aeb464e`. | AI, 2026-10-27 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations and the closed unit tier. | `run1b-cluster/selfcheck.py` copies the cluster part of `run1/selfcheck.py` verbatim; under `--relations run1` its output on run 1's raw files is identical to the 106 cluster lines of `run1/selfcheck.out`; under `--relations amended` the ρ and Y64-vs-R64 RSS lines become uncounted context lines and the ledger checks and the amended B3g precedence are added. It exits non-zero on any failed counted check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stdout.txt`, `junit-testsuite.txt`, `compile-summary.txt`); [`run1/cluster/`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1/cluster/) (`commands.log`, `summary.txt`; per run `samples.csv`, `rss.txt`, `info-*-caches.txt`, `stress-*-results.txt`, `node-log-excerpt.txt`, `nmt-*-excerpt.txt`, `tablestats-excerpt.txt`, `compactionhistory-keyspace1.txt`, `schema.txt`, `yaml-tail.txt`, `error-count.txt`; `RT/neg.txt`).

### 4.1 Readings

**Unit tier** (JUnit 1 test, 0 failures, 0 errors; `RCP done` present; `OHCacheLinkedImpl(capacity=16777216 ,segments=4 ,…, maxEntrySize=4194304`; perEntry = allocLen = 1,176 B in every pass)

| C (MiB) | capacity | max used (every read) / samples | final used (fill) | entries | entries ratio | dMiss / dHit | dEvict (= N − entries) | dPutFail |
|---|---|---|---|---|---|---|---|---|
| 16 | 16,777,216 | 16,774,464 / 40 ≤ cap | 16,774,464 (0.99984) | 14,264 | – | 40,000 / 0 | 25,736 (25,736) | 0 |
| 8 | 8,388,608 | 8,387,232 / 40 ≤ cap | 8,387,232 (0.99984) | 7,132 | 0.5000 | 40,000 / 0 | 32,868 (32,868) | 0 |
| 4 | 4,194,304 | 4,191,264 / 40 ≤ cap | 4,191,264 (0.99928) | 3,564 | 0.4997 | 40,000 / 0 | 36,436 (36,436) | 0 |
| 2 | 2,097,152 | 2,093,280 / 40 ≤ cap | 2,093,280 (0.99815) | 1,780 | 0.4994 | 40,000 / 0 | 38,220 (38,220) | 0 |
| 1 | 1,048,576 | 1,044,288 / 40 ≤ cap | 1,044,288 (0.99591) | 888 | 0.4989 | 40,000 / 0 | 39,112 (39,112) | 0 |

Every final used ≥ C·2^20 − 4·1,176 (B2f (i)). Evidence: `run1/unit/stdout.txt`.

| Test or assertion | Result | Evidence |
|---|---|---|
| step 1, C = −1 | `java.lang.RuntimeException`, `capacity should not be negative.`; capacity 16,777,216 before and after | `stdout.txt` |
| step 3, second pass at C = 1 | dMiss 40,000, dHit **0** (≤ 888), dEvict 40,000, used ≤ 1,044,288 | `stdout.txt` |
| step 4, refill at 16 | used 16,774,464, entries 14,264 | `stdout.txt` |
| step 4, `setRowCacheCapacityInMB(1)` without invalidation | **used 16,774,464 and entries 14,264 unchanged**, capacity 1,048,576 | `stdout.txt` (`RCP shrink`) |
| step 4, then 2,000 misses | final used **1,044,288** (≤ 2^20), entries 888, dEvict 15,376 (= 14,264 + 2,000 − 888), dMiss 2,000; samples at 1,000 and 2,000 reads 1,044,284 / 1,044,288; the per-read maximum of the pass, 12,841,918, is from its first reads, when one of the four segments had been trimmed (16,774,464 − 12,841,918 = 3,932,546 ≈ one segment) and the others had not yet had a put | `stdout.txt` |

**Cluster tier** (one node; every stress run `Total errors: 0` and all partitions; `system.log` 0 ERROR lines in every run; 1 sstable in every run; the same three `keyspace1` compactions, all from the write phase, in every run; key and counter cache capacity 0 bytes at start and end of every run; row cache initialised at 512 MiB (Y64: 64 MiB), OHC with JNA malloc; distinct pid per run; allocLen = Size/Entries = 1,198.6 B (R512) and 1,200.0 B (capped runs), so g = 1,536 B)

| Run | C | Observable | Reading | Prediction (B3f amendment) | Evidence |
|---|---|---|---|---|---|
| BASE | (NONE) | entries / ΔRSS | 0 / **39,360 KiB** (40.3 MB) | 0; baseline | `run1/cluster/BASE/` |
| R512 | 512 | Entries / Size | **300,000 / 359,578,900 B** | ≥ 297,000; ≤ 536,870,912 | `R512/samples.csv` |
| R512 | 512 | ΔRSS; ΔRSS − base; ρ | 444,848 KiB; 415.2 MB; **ρ 0.901** | ρ ∈ [0.85, 1.15] | `R512/rss.txt` |
| R128 | 128 (runtime) | max Size / final Size (fill) / Entries | 134,208,210 / **134,208,000 (0.9999)** / 111,840; capacity 134,217,728 in every sample | every sample ≤ 134,217,728; fill ≥ 0.8 | `R128/samples.csv` |
| R128 | | ΔRSS; − base; ρ | 192,208 KiB; 156.5 MB; **ρ 0.911** | [0.85, 1.15] | `R128/rss.txt` |
| R64 | 64 (runtime) | max / final (fill) / Entries | 67,096,985 / **67,084,800 (0.9996)** / 55,904 | ≤ 67,108,864; ≥ 0.8 | `R64/samples.csv` |
| R64 | | ΔRSS; − base; ρ | 151,968 KiB; 115.3 MB; **ρ 1.343** | [0.85, 1.15] — **outside** | `R64/rss.txt` |
| R32 | 32 (runtime) | max / final (fill) / Entries | 33,541,910 / **33,523,200 (0.9991)** / 27,936 | ≤ 33,554,432; ≥ 0.8 | `R32/samples.csv` |
| R32 | | ΔRSS; − base; ρ | 89,280 KiB; 51.1 MB; **ρ 1.191** | [0.85, 1.15] — **outside** | `R32/rss.txt` |
| Y64 | 64 (yaml) | max / final (fill) / Entries | 67,085,010 / **67,084,800 (0.9996)** / 55,904 | ≤ 67,108,864; ≥ 0.8 | `Y64/samples.csv` |
| Y64 | | ΔRSS; − base; ρ | 124,560 KiB; 87.2 MB; **ρ 1.016** | [0.85, 1.15] | `Y64/rss.txt` |
| R32 < R64 < R128 < R512 | | ΔRSS − base | 51.1 < 115.3 < 156.5 < 415.2 MB, strictly increasing | strictly increasing | `*/rss.txt` |
| slope R32 → R128 | | s = (156.5 − 51.1) MB / ((111,840 − 27,936) × 1,536 B) | **0.818** | [0.8, 1.2] | `*/rss.txt`, `*/samples.csv` |
| Y64 vs R64 | | ΔRSS | 127,549,440 vs 155,615,232 B: **−18.0 %** | within ± 15 % — **outside** | `Y64/rss.txt`, `R64/rss.txt` |
| RT, after 200,000 keys | 512 | Entries / Size | 200,000 / 239,578,900 | Entries ≥ 198,000 | `RT/samples.csv`, `summary.txt` |
| RT, `setcachecapacity 0 64 0` | → 64 | Size in the 3 JMX samples and the 6 poller samples before the next miss | **239,578,900 unchanged**, capacity 67,108,864 | unchanged (lazy) | `RT/samples.csv`, `summary.txt` |
| RT, after 100,000 misses | 64 | Size / Entries | **67,084,800 (0.9996)** / 55,904 | ≤ 67,108,864; ≥ 0.8 | `RT/samples.csv` |
| RT, −1 through JMX | | outcome / capacity | `RuntimeMBeanException` wrapping `java.lang.RuntimeException: capacity should not be negative.`; capacity 67,108,864 before and after | refused; unchanged | `RT/neg.txt` |
| RT RSS (context) | | RSS0 → RSS1 | 1,343,952 → 1,656,048 KiB | context only | `RT/` summary line |
| NMT (context) | | `Total committed` | grows by ≈ 375–405 MB in every run including BASE (heap 1 GiB fixed; "Other" ≈ 394 MB = direct buffers); the row cache does not appear | invisible (JNA malloc) | `*/nmt-*-excerpt.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 1 test, 0 failures, 0 errors [observed: `run1/unit/junit-testsuite.txt`]; `RCP done` and every pass line present; 40,000 rows, one sstable [observed: `stdout.txt`]. The limit is reached: demand 40,000 × 1,176 B = 47.0 MB exceeds every C [observed: perEntry]. Valid.
2. **Readings** — nothing unusual. The per-read maximum of step 4's miss pass (12,841,918) lies above 2^20; it is the per-segment lazy window that the B2b/B2e amendment derives ("nothing is evicted until the next put into that segment") — the B2g row-2 exception is worded "between the set and the first miss", which is narrower than that derivation; B2g row 2 is defined on samples (B2d: every 1,000 reads and at the end), and both samples of that pass are ≤ 2^20 [observed: `stdout.txt`]. Recorded as a wording point for the case, not a reading against the cap.
3. **Matched row** — B2g row 1, "used ≤ C·2^20 and entries ∝ C", with the B2f amendment's (ii)–(vi): every sample and every per-read value of the five sweep passes ≤ C·2^20; fill 0.9959–0.9998 (≥ C·2^20 − 4·1,176); entries ratios 0.4989–0.5000; dMiss 40,000, dHit 0; dEvict exactly N − entries in all five passes, dPutFail 0; step 3 dHit 0 ≤ 888; guard throws the exact message, capacity unchanged; step 4 unchanged at the set, then 1,044,288 ≤ 2^20 with dEvict 15,376 [observed: `stdout.txt`].
4. **Excluded rows** — row 2 (used > C at a sample): none [observed]. Row 3 (knob ignored): entries 888 at C = 1, ratios ≈ 0.5 [observed]. Row 4 (not caching): 14,264 entries at 16, dMiss = N [observed]. Added (a) guard: refused [observed]; (b) step 4 > 2^20 after the misses: 1,044,288 [observed]; (c) off-band: none [observed]; (d) used dropping at the set: unchanged [observed]; (e) invalid: no [observed].
5. **Observed vs. inferred** — that `weightedSize` is OHC's off-heap byte count is from the source (`OHCProvider.java:97-100`, `memUsed`); the eviction count is OHC's own (`OffHeapLinkedMap.removeEldest`) [inferred: source]. Native bytes are not observed on this tier (the file names the gap).
6. **Deviations and gaps** — step 4 and the eviction counter added at the audit; one run.
7. **Core question** — the runtime setter sets OHC's capacity; every insert evicts LRU entries of its segment so used never exceeds C·2^20 (the cache filled to 99.6–99.98 % of 16, 8, 4, 2, 1 MiB and its entry count halved with C, with exactly N − entries evictions); a negative value is refused. A decrease takes effect segment by segment at the next insert, not at the call.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — every hold-fixed check of the B3e amendment holds [observed: `selfcheck.out`]: yaml lines per run, `-Xmx1G`, key/counter capacity 0, `saved_caches` empty at start, one sstable, no compaction after the write phase, caching `NONE` for BASE and `ALL` after, stress 0 errors with all partitions, 0 ERROR lines, distinct pids; the limit is reached (R512 holds 359.6 MB of data, three to eleven times the capped C). Valid.
2. **Readings** — the cache's own size is capped and full in every capped run; RSS growth is monotone in C, but ρ is 1.343 at R64 and 1.191 at R32, and Y64 (same C set by yaml) grew 28 MB less than R64 [observed: `*/rss.txt`]. RSS has a noise or allocator component of that order on this host that the frozen bands did not allow for [inferred: R64 and Y64 hold the same 55,904 entries of 1,200 B, per `samples.csv`].
3. **Matched row** — B3g added row (b), "Size capped but … Y64 off R64 by more than 15 % → **Not confirmed** (caps on the counter, native reading ambiguous)": Y64 vs R64 −18.0 % [observed]. Row 1's own conditions also hold — (i) cap and fill, (ii) R512 300,000 entries, (iv) RT lazy then capped and −1 refused, and "tracks C" (monotone; s = 0.818 ∈ [0.8, 1.2]) [observed] — but row (b) names the Y64 condition explicitly, and the self-check script, written before the readings, ranks row (b) before row 1; when two rows match, the narrower verdict is filed.
4. **Excluded rows** — row 2 (flat): increasing, s = 0.818 ≥ 0.5 [observed]. Row 3 (Size > C): largest sample 0.99991·C (R32) [observed]. Row 4 (control did not cache): 300,000 entries [observed]. Added (a) (RT not capped or −1 accepted): 67,084,800 ≤ 64 MiB; refused [observed]. Added (c) invalid: no [observed].
5. **Observed vs. inferred** — that RSS growth minus BASE is the row cache's native memory is inferred (OHC's mallocs are invisible to NMT, as predicted: NMT grows alike in BASE and R512); that each entry costs 1,536 B is from `malloc_good_size` [inferred: platform]. R512 (ρ 0.901) and R128 (0.911) fit that unit; R64 and R32 sit above it.
6. **Deviations and gaps** — the instruments, the run plan and RT were set at the audit; the `neg` call was fixed after the shakedown (harness only). Stress warmup (as written) adds misses on keys the counted read also reads. One run; run 2 not done (§5.2).
7. **Core question** — on a node, the setter (runtime or yaml) caps the row cache's own off-heap size exactly: 512 → all 300,000 rows (359.6 MB); 128 / 64 / 32 MiB → 99.9–99.99 % full, never above; a runtime shrink of a full cache frees nothing until inserts, after which it holds; −1 is refused. Process RSS grows with C (51 → 115 → 157 → 415 MB above the no-cache read, slope 0.82 of the per-entry allocation), but the frozen agreement bands for the native reading were missed at C = 64 and 32 and between the two ways of setting 64, so the native-memory half of B1 is not confirmed on this run.

**Conclusion (cluster tier):** B3g added row (b) — **not confirmed** (caps on the counter; native reading ambiguous).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1/selfcheck.py), written before any run-1 reading and independent of the harness summaries' numbers (it re-reads the raw test log and JUnit XML; per cluster run the raw `samples.csv`, `stress-*.txt`, `rss.txt`, `info-*.txt`, `yaml-tail.txt`, `system.log`, `tablestats.txt`, `compactionhistory.txt`, `schema.txt`, `RT/neg.txt`, the pids in `commands.log`, and computes g with `malloc_good_size`): **160 lines; 155 checks, 3 failed** (unit 0 of 49, cluster 3 of 106: ρ at R64, ρ at R32, Y64 vs R64); unit "row 1 → Confirmed, caps", cluster "added (b) → Not confirmed (counter capped, native reading ambiguous)" ([`run1/selfcheck.out`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1/selfcheck.out)). One change after it was written, after the unit shakedown and before any run-1 reading: the allocator log line was made a context check (not a validity check). No bound of the case file was changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Unit JUnit counts and `RCP done`; cluster hold-fixed checks from the raw files (yaml, JVM args, info lines, schema, compaction history, stress totals, ERROR count, pids). |
| 2. Readings | yes | Unit per-pass values and samples re-read; cluster per-sample caps and fills, ΔRSS per run; the step-4 per-read maximum stated with its cause. |
| 3. Matched row | yes | Unit row 1 with every amended condition; cluster row (b) on the Y64 −18.0 % reading, with row 1's other conditions recorded as holding. |
| 4. Excluded rows | yes | Each excluded row's reading re-read. |
| 5. Observed vs. inferred | yes | The cluster's native reading rests on inference (RSS − BASE, g); that inference is exactly what the missed bands put in doubt, which is why the tier is not confirmed. |
| 6. Deviations and gaps | yes | Stated; the `neg` harness fix and stress warmup do not change a reading's meaning. |
| 7. Core question | yes | Unit: setter → OHC capacity → per-segment eviction at insert → used ≤ C exactly, evictions = N − entries. Cluster: same cap on the node's counter; native growth monotone but outside the frozen agreement bands. |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier is exact and holds in every part. The cluster tier's verdict is already the frozen
table's narrower row; a run 2 under the same frozen bands would test the RSS noise of this host, not the claim, and changing the
bands would need a re-freeze that only the user can authorise.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3d, B3e, B3f (iii), B3g, B3h, B4 amendment — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The unit tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed only through B3f (iii)'s RSS relations: ρ 1.343 (R64) and 1.191 (R32) outside [0.85, 1.15] (which alone would have left row 1 standing) and Y64's ΔRSS 18.0 % below R64's against ± 15 % (added row (b)), while every Size, Entries, RT and −1 reading, the strict increase of ΔRSS − ΔRSS_BASE and the slope s held (§4.1–§4.2). OHC allocates each entry with JNA `Native.malloc`, so RSS also contains the allocator's behaviour, which Cassandra's source does not determine. The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of the whole cluster tier on 2026-10-27. |
| **Choice of instrument, and why** | Of the two routes named in the brief — count the bytes OHC itself mallocs and frees, or derive an RSS band that includes the allocator's quantum and retention — the first was chosen. What OHC takes and returns is fixed by its source and Cassandra's (one block of allocLen per cached entry, a table per segment, transient blocks freed before the read returns), so it admits exact relations. The allocator's retention (free memory kept in its zones, pages compressed or returned by the OS) is not documented as a quantity, so an RSS band that "includes retention" would have had to be chosen rather than derived; and the allocator's size class turned out to depend on the process (below). The re-run itself then showed RSS falling by 174 MiB during the Y64 read while the cache filled (§7.3), which no band derived from the source could have covered. |
| **Amendment** | Six dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user) — B3d / B3e / B3f (iii) / B3g / B3h / B4`, each next to the text it changes; each says plainly that it follows run 1's readings.<br>**B3d, instrument (5):** an observe-only Byteman ledger at OHC 0.5.1's own bookkeeping points `org.caffinitas.ohc.linked.Uns.allocated(address, bytes)` and `Uns.freed(address)` (`Uns.java:104-113`, `:90-102`, called only by `allocate(long, boolean)` after a non-zero malloc, `:338-346`, and by `free(long)` before the free, `:361-367`; every allocation site of the linked implementation goes through them; OHC is used by nothing else in Cassandra). Helper `RcsLedger` keeps per live block {bytes, `malloc_size`} and exposes MBean `stage4:type=RcsLedger`: entry blocks (< 65,536 B) and table blocks (≥ 65,536 B) with counts, bytes, `malloc_size` totals, a_max, unknown frees, duplicates, and the live-size histogram. Poller columns and one-shots at start, end and around RT's set.<br>**B3f (iii′), from the source:** (1) at the end of each run `EntryBlocks` = Entries and `EntryBytes` = Size, exactly (one block of allocLen per entry, `OHCacheLinkedImpl.java:238, 257`; free capacity −bytes `OffHeapLinkedMap.java:307`, +allocLen on removal `:730`; Size = `memUsed()` `OHCacheLinkedImpl.java:1205-1207`; transient blocks freed before the read returns, `:250/284`, `:279`, `OffHeapLinkedMap.java:319-326`, `HashEntries.java:174-182`; no TTL, so no `Timeouts` blocks); (2) 32 tables of 8,192 slots × 8 B, doubling at 0.75 load, never shrinking: T = 2,097,152 B in BASE and the capped runs (allocLen > 1,064 B → < 3,943 entries per segment < 6,144), 4,194,304 B in R512 (9,375 ± 95 per segment, between 6,144 and 12,288), 2,097,152 + 65,536·k in RT (6,250 ± 78 per segment, k not fixed), unchanged by the shrink; (3) `EntryBytes` ≤ C·2^20 + 300·a_max at every sample (≤ 6 transient blocks per in-flight read, ≤ 50 reads in flight); (4) C·2^20 − 32·a_max < `EntryBytes` ≤ C·2^20 at the end (after an evicting put 0 ≤ free < a_max per segment, `OffHeapLinkedMap.java:283-307`); (5) \|Y64 − R64\| < 32·a_max on `EntryBytes`, tables equal (both have 64·2^20/32 per segment, `OHCProvider.java:40`, `OHCacheLinkedImpl.java:655-665`), replacing the RSS relation; (6) RT lazy at the set, then (1) and (4). ρ and the Y64-vs-R64 ΔRSS become records; the strict increase and s ∈ [0.8, 1.2] stay conditions, unchanged.<br>**B3g:** row 1 read with (iii′); the ρ clause and row (b)'s Y64 clause superseded; (c) Invalid extended to the ledger (agent, MBean, unknown frees, duplicates, `malloc_size` errors); (d) native blocks over C·2^20 (+ the in-flight allowance at a sample) → Refuted; (e) ledger model off within the caps → Not confirmed. B3h: BASE as the ledger's null control. B4: paths.<br>B1, B3f (i), (ii), (iv), the strict increase and slope, B3h's other controls and the unit tier are unchanged. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's readings were known** when the amendment was written (results §4.1: Size, Entries, ΔRSS per run, ρ 0.901 / 0.911 / 1.343 / 1.191 / 1.016, s = 0.818, Y64 vs R64 −18.0 %, the RT samples and the −1 call). Also known before the re-freeze, from instrument checks made today and recorded in the B3d amendment: the ledger's known answer outside Cassandra ([`run1b-cluster/instrument/known-answer.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/instrument/known-answer.txt)), and that **inside a JVM on this host `malloc_size`/`malloc_good_size` give a 1,280-B block for 1,025–1,280-B requests**, whereas the Python process the run-1 audit used gives 1,536 B ([`instrument/jvm-malloc-size-probe.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/instrument/jvm-malloc-size-probe.txt), [`instrument/python-malloc-good-size.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/instrument/python-malloc-good-size.txt)); B3d (4)'s g and the frozen slope were left unchanged. No number of (iii′) comes from a reading: the equalities and table sizes are from the source, the 300·a_max and 32·a_max allowances from the OHC eviction loop and B3c's 50 threads, a_max from the same run. **Would run 1 pass?** Not evaluable: run 1 has no ledger, so under the amended table it falls in added row (c), **Invalid** (`run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out`: 129 checks, 29 failed — the eight agent checks and 21 ledger readings missing). Its Size readings alone would meet the Size form of (iii′-4) and (iii′-5) if a_max ≥ 1,200 B (deficits 9,728 / 24,064 / 31,232 / 24,064 B; Y64 − R64 = 0). |
| **Case-file version** | sha256 **`219ff0f911a6acd8a98b4b6b753859e175f85a2ae688c45ba8d770e7ce5acd4f`**, a new row in `_INDEX.md` §4: "re-frozen after run 1 for cluster re-run (B3d, B3e, B3f (iii), B3g, B3h, B4), authorised by the user". The earlier rows (`21fd9d5a…`, `f6890ca6…`) are kept. Hashed at 19:25:40 EDT, after the fresh clone was built (19:18:55–19:19:57) and before the shakedown (19:28:42) or any re-run reading (19:40:55); recorded again at 19:25:58 in [`run1b-cluster/harness-sha-run2.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/harness-sha-run2.txt). Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `2bb5ef9`; nothing committed. |
| **Harness** | Run 1's harness with changes H1 (paths), H2 (ledger) and H3 (self-check) only (§3).<br>sha256 at the re-run: `cluster-run.sh` `3dacd562`, `make-node-conf.sh` `ee0f805a`, `RcsJmx.java` `3fb3950c`, `RcsLedger.java` `0673e2b6`, `rcs-ledger.btm` `9aeb464e` (also in the run's summary line), `LedgerKnownAnswer.java`, `selfcheck.py` (`harness-sha-run2.txt`).<br>Commands: `RCS_C=$W/cassandra-run67 RCS_NODE=$W/node-rcs67 RCS_BM=1 cluster-run.sh shake2`, then the same with `run2`.<br>Instrument checks: `TestScript: no errors` for both rules (in each run's `testscript.txt`); the known answer outside Cassandra (above); in the shakedown every node loaded the agent and registered the MBean with `malloc_size=true`, 0 agent error lines, 0 unknown frees. The self-check ran end to end on the shakedown first: 154 checks, 1 failed — the slope s = 0.715 at the shakedown's small capacities (2–8 MiB), not judged — exit status 1 as designed ([`run1b-cluster/shakedown/selfcheck.out`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/shakedown/selfcheck.out)); every ledger relation held there (e.g. R4: 3,488 blocks = Entries, 4,168,160 B = Size; Y4 − R4 = 0). |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18; free disk 111 GiB. Cluster
re-run 2026-10-27: instrument checks 19:21–19:24 EDT, shakedown 19:28:42–19:40:30, re-run 19:40:55–19:54:04. Fresh clone from `~/cassandra-src` at
`b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change: `$W/cassandra-run67` (`ant -Dlocal.repository=$W/m2 build-test`,
`BUILD SUCCESSFUL`, 54 s; [`run1b-cluster/clone-build-run67.txt`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/clone-build-run67.txt)). Node `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (`-Xms1G -Xmx1G`, NMT summary), as in run 1, plus
`-javaagent:…/byteman-4.0.20.jar=script:…/rcs-ledger.btm,boot:…,sys:…/rcs-ledger.jar` (read from `JVM Arguments` in every run). Node data in `$W/node-rcs67`, wiped before and after.
Full logs: `~/Library/Caches/stage4/logs/row_cache_size-setRowCacheCapacityInMB-capacity/`: `clone-run67.log`, `build-test-run67.log`, `ledger-known-answer/`
(`known-answer.txt`, `jvm-malloc-size-probe.txt`), `harness-sha-run2.txt`, `driver-shake2.out`, `cluster-shake2/`, `selfcheck-shake2.out`, `driver-run2.out`,
`cluster-run2/` (as run 1's `cluster-run1/`, plus `testscript.txt` and per run `ledger-*.txt` and the ledger columns in `samples.csv`), `selfcheck-run2.out`,
`selfcheck-run2-under-run1-relations.out`, `selfcheck-known-answer-run1-relations-{run1,amended}.out`. Excerpts: [`run1b-cluster/`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/)
(`cluster/` with run 1's kinds of files plus `ledger-*.txt`, `node-out-agent-lines.txt`, `testscript.txt`; `shakedown/`; `instrument/`; `selfcheck.py`; `selfcheck.out`;
`selfcheck-rerun-under-run1-relations.out`; `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`; `driver.out` (empty: the script writes to its logs); `harness-sha-run2.txt`; `clone-build-run67.txt`).

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt` and, per run, `samples.csv`, `ledger-*.txt`, `rss.txt`, `stress-*-results.txt`, `node-log-excerpt.txt`,
`node-out-agent-lines.txt`; recomputed from the raw files by `selfcheck.py`. Every hold-fixed check of B3e holds as in run 1: every stress run
`Total errors: 0` with all partitions; 0 `ERROR` lines; 1 sstable and the same three write-phase compactions in every run; key and counter cache
capacity 0; `saved_caches` empty at start; caching `NONE` for the write phase and BASE, `ALL` after; distinct pids. Every node: agent in `JVM Arguments`,
`RCSLEDGER registered … malloc_size=true`, 0 agent error lines; `UnknownFrees`, `DuplicateAllocs`, `MallocSizeErrors` 0 at every reading.

| Run | C (MiB) | Size: max sample / end (fill) | Entries | ledger end: `EntryBlocks` / `EntryBytes` | `TableBlocks` / `TableBytes` (predicted) | max sample `EntryBytes` (bound C·2^20 + 300·a_max) | end deficit C·2^20 − `EntryBytes` (bound 32·a_max = 38,400) | ΔRSS − base | Evidence |
|---|---|---|---|---|---|---|---|---|---|
| BASE | (NONE) | 0 / 0 | 0 | 0 / 0 | 32 / 2,097,152 (2,097,152) | — | — | ΔRSS 45,744,128 B (base) | `cluster/BASE/` |
| R512 | 512 | — / 359,610,395 | **300,000** | **300,000 / 359,610,395** | 32 / **4,194,304** (4,194,304) | — | — | 293,355,520 | `cluster/R512/` |
| R128 | 128 (runtime) | 134,208,315 / 134,208,000 (0.9999) | 111,840 | **111,840 / 134,208,000** | 32 / 2,097,152 (2,097,152) | 134,209,314 (134,577,728) | 9,728 | 152,862,720 | `cluster/R128/` |
| R64 | 64 (runtime) | 67,100,440 / 67,084,800 (0.9996) | 55,904 | **55,904 / 67,084,800** | 32 / 2,097,152 | 67,086,219 (67,468,864) | 24,064 | 77,889,536 | `cluster/R64/` |
| R32 | 32 (runtime) | 33,536,585 / 33,523,200 (0.9991) | 27,936 | **27,936 / 33,523,200** | 32 / 2,097,152 | 33,544,215 (33,914,432) | 31,232 | 35,618,816 | `cluster/R32/` |
| Y64 | 64 (yaml) | 67,085,115 / 67,084,800 (0.9996) | 55,904 | **55,904 / 67,084,800** | 32 / 2,097,152 | 67,091,304 (67,468,864) | 24,064 | ΔRSS **−182,648,832** (RSS fell during the read) | `cluster/Y64/` |

a_max = 1,200 B in every run (R512's live entry sizes 1,185–1,200 B; the capped runs' all 1,200 B). The cache's native blocks equal its counter exactly at the end of every run.

| Relation | Reading | Prediction | Evidence |
|---|---|---|---|
| (iii′-5) Y64 vs R64 | `EntryBytes` 67,084,800 vs 67,084,800: **0**; tables 2,097,152 both | \< 38,400; equal | `Y64/ledger-end.txt`, `R64/ledger-end.txt` |
| strict increase (kept) | ΔRSS − base: 35.6 < 77.9 < 152.9 < 293.4 MB (R32 < R64 < R128 < R512) | strictly increasing | `*/rss.txt` |
| slope s (kept, with g = 1,536) | (152,862,720 − 35,618,816) / ((111,840 − 27,936) × 1,536) = **0.910** | [0.8, 1.2] | `*/rss.txt`, `*/samples.csv` |
| RT after 200,000 keys | Size 239,610,395, Entries 200,000; ledger 200,000 blocks / 239,610,395 B; tables **4,063,232** (k = 30: 30 × 131,072 + 2 × 65,536) | Entries ≥ 198,000; T = 2,097,152 + 65,536·k | `RT/ledger-beforeset.txt` |
| RT, `setcachecapacity 0 64 0` | Size 239,610,395 in the 3 JMX samples and the 6 poller samples before the next miss; ledger unchanged (200,000 / 239,610,395, tables 4,063,232); capacity 67,108,864 | unchanged (lazy) | `RT/samples.csv`, `RT/ledger-afterset.txt`, `summary.txt` |
| RT after 100,000 misses | Size 67,084,800 (0.9996), Entries 55,904; ledger **55,904 / 67,084,800**, tables 4,063,232 (unchanged) | ≤ 64 MiB and ≥ 0.8; (iii′-1), (iii′-4); T unchanged | `RT/ledger-aftermisses.txt` |
| RT −1 through JMX | `RuntimeMBeanException` wrapping `java.lang.RuntimeException: capacity should not be negative.`; capacity 67,108,864 before and after | refused; unchanged | `RT/neg.txt` |

Recorded, not conditions (context): every live entry block of every run is a **1,280-B** `malloc_size` block (`EntryMalloc` = 1,280 × `EntryBlocks`; 1.067–1.068 × `EntryBytes`);
tables 65,536 / 131,072 B blocks exactly. ρ as filed (g = 1,536): R512 0.637, R128 0.890, R64 0.907, R32 0.830, Y64 −2.660; ρ′ = (ΔRSS − base)/`EntryMalloc`: 0.764,
1.068, 1.088, 0.996, −3.192; slope against `EntryMalloc` 1.092. Y64's RSS rose to 1,411,760 KiB while the cache filled, then fell to 1,162,464 KiB while it stayed full
(`Y64/samples.csv`), 178,368 KiB below its start, with no swap configured (`vm.swapusage` 0): the OS took resident pages from the JVM during that run, so ΔRSS is not
the cache's memory there. RT RSS 1,346,528 → 1,660,752 KiB. NMT `Total committed` grows alike in BASE and R512 (≈ 385 MB); the row cache is not in NMT (JNA malloc).
OHC took 3 blocks per miss (R512: 900,064 allocations, 600,032 frees: sentinel, old-value copy, entry; plus 64 tables).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`219ff0f9…`, hashed at 19:25:40, before the shakedown and the re-run) [observed: `_INDEX.md` §4; `harness-sha-run2.txt`; `summary.txt` first line 19:40:55].
   - Every step of B3 ran from the beginning in the frozen order, in a fresh clone, after a shakedown [observed: `summary.txt`, `shakedown/summary.txt`].
   - Every hold-fixed check of B3e and every ledger validity check of the B3e amendment holds [observed: `selfcheck.out`].
   - The limit is reached: R512 holds 359.6 MB of data, three to eleven times the capped C [observed].
   - Valid.
2. **Readings.** The cache's own size is capped and full in every capped run, as in run 1, to the byte (Size 134,208,000 / 67,084,800 / 33,523,200 — the same values as run 1). OHC's live native entry blocks equal Size and Entries exactly at every end reading; the tables are the predicted 32 × 64 KiB (R512: 32 × 128 KiB). RSS behaved worse than in run 1 (Y64 fell by 174 MiB during its read) [observed: `samples.csv`, `ledger-*.txt`, `rss.txt`].
3. **Matched row.** B3g row 1, "Size ≤ C and ΔRSS−base tracks C — the knob caps native row cache memory", read with the 2026-10-26 and 2026-10-27 amendments. Each part [observed; computed by `run1b-cluster/selfcheck.py`]:
   - (i) every sample Size ≤ C·2^20 (largest 0.99993·C at R32), fill 0.9991–0.9999, Capacity = C·2^20;
   - (ii) R512 300,000 entries, Size 359,610,395 ≤ 512 MiB;
   - (iv) RT: 200,000 entries; Size and ledger unchanged at the set; 67,084,800 ≤ 64 MiB after the misses; −1 refused, capacity unchanged;
   - "tracks C": ΔRSS − base strictly increasing; s = 0.910 ∈ [0.8, 1.2];
   - (iii′-1) `EntryBlocks` = Entries and `EntryBytes` = Size in BASE, R512, R128, R64, R32, Y64 and RT after the misses; (iii′-2) 32 tables, 2,097,152 / 4,194,304 B as predicted, RT 4,063,232 unchanged across the shrink; (iii′-3) every sample within C·2^20 + 300·a_max — in fact no sample exceeded C·2^20 (largest 134,209,314 / 67,086,219 / 33,544,215 / 67,091,304 B at R128 / R64 / R32 / Y64); (iii′-4) deficits 9,728 / 24,064 / 31,232 / 24,064 / 24,064 B < 38,400; (iii′-5) Y64 − R64 = 0; (iii′-6) lazy at the set.

   **Tier rule: Confirmed.**
4. **Excluded rows.**
   - Row 2 (flat): increasing, s = 0.910 ≥ 0.5. Row 3 (Size > C): none. Row 4 (control did not cache): 300,000 entries.
   - Added (a) (RT not capped, or −1 accepted): 67,084,800 ≤ 64 MiB; refused.
   - Added (b) (s outside [0.8, 1.2]): 0.910.
   - Added (c) (Invalid, incl. ledger): no — agent and MBean on every node, 0 unknown frees, duplicates, `malloc_size` errors, 0 agent errors.
   - Added (d) (native blocks over the cap): no sample over C·2^20 + 300·a_max, no end reading over C·2^20.
   - Added (e) (ledger model off): every (iii′) relation exact.
   - The superseded ρ and Y64-vs-R64 RSS relations are not applied; their quantities are recorded (they would fail again: ρ 0.637 / 0.830 / −2.660, Y64 ΔRSS negative).

   [observed]
5. **Observed vs. inferred.**
   - Observed: every relation, from the raw ledger one-shots, poller samples, JMX outputs, stress results and logs.
   - Inferred: that the ledger sees every OHC block rests on the source (all allocation and free sites go through `Uns.allocated`/`Uns.freed`) and is supported by 0 unknown frees from JVM start, BASE's ledger of exactly 32 tables, and the instrument's known answer. That RSS is unreliable here (Y64) is an observation about the host, not used for the verdict.
6. **Deviations and gaps.**
   - None against the re-frozen runbook.
   - The amendment was written knowing run 1's readings and, before the re-freeze, the JVM's 1,280-B block size (stated in §7.1 and in the amendment). The equalities and table sizes are from the source; the allowances from the eviction loop and the workload.
   - The frozen slope uses g = 1,536 B (B3d (4)), which is not the JVM's block size (1,280 B); it is kept as frozen and holds (0.910); with 1,280 B it would be 1.092 (context).
   - The agent's helper holds a map of live blocks on the heap (≈ 300,000 entries at R512); the heap is pre-touched (1 GiB), so RSS is not affected by it.
7. **Core question.** On a node, the setter (runtime or yaml) caps the row cache's off-heap memory, and now on the memory itself, not only its counter: the native blocks OHC holds for entries equal the counter to the byte at the end of every run (300,000 rows = 359,610,395 B at 512; 111,840 / 55,904 / 27,936 rows = 134,208,000 / 67,084,800 / 33,523,200 B at 128 / 64 / 32 MiB, each within 32 KiB of C), never exceed C at any sample, and the yaml-set and runtime-set 64 MiB caches hold the same bytes. On top of these OHC keeps 2–4 MiB of hash tables, and the macOS allocator reserves 1,280 B for each ≈ 1.2 KB entry (6.7 % over `EntryBytes`). A runtime shrink frees nothing until inserts, after which it holds; −1 is refused.

**Conclusion (one line):** B3g row 1 with the amended B3f (iii′): confirmed — caps.

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the raw `samples.csv` (all columns), `ledger-*.txt` (first line and histogram), `stress-*.txt`, `rss.txt`,
`info-*.txt`, `yaml-tail.txt`, `node/system.log` (JVM arguments incl. the agent), `node/node.out` (registration and agent error lines), `tablestats.txt`,
`compactionhistory.txt`, `schema.txt`, `RT/neg.txt` and the pids in `commands.log`; like run 1's, it takes only the RT JMX sample lines from `summary.txt`.
It was written after the re-freeze and before any re-run reading, and was not changed after the shakedown or the re-run.
- **Pass 0 (shakedown, run end to end first):** 154 checks, 1 failed (the shakedown's slope, not judged), exit 1 (`run1b-cluster/shakedown/selfcheck.out`).
- **Pass 1 (re-run raw files, amended relations):** **154 checks, 154 hold, 0 fail**, exit 0; verdict `row 1 -> Confirmed, caps` ([`run1b-cluster/selfcheck.out`](row_cache_size-setRowCacheCapacityInMB-capacity--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 106 checks, 3 failed (ρ R64, ρ R32, Y64 vs R64), verdict added (b); the 106 lines are **identical** to the cluster lines of `run1/selfcheck.out` (`selfcheck-known-answer-on-run1-relations-run1.out`; `diff` empty).
- **Pass 3 (run 1's raw files, amended relations):** 129 checks, 29 failed — no agent, no ledger; verdict added (c), Invalid: the script tells run 1 apart from the re-run (`…-relations-amended.out`).
- **Pass 4 (information, re-run raw files, run-1 relations):** 106 checks, 4 failed — ρ R512 0.637, ρ R32 0.830, ρ Y64 −2.660, Y64 vs R64; verdict added (b). The frozen RSS relations would have failed again, at other runs (`selfcheck-rerun-under-run1-relations.out`).

Raw files re-opened by hand: `cluster-run2/R128/ledger-end.txt` (`EntryBlocks=111840 EntryBytes=134208000`, `size=134208000 entries=111840`, histogram `1200:111840;65536:32;`);
`Y64/ledger-end.txt` (`EntryBytes=67084800`, same as `R64/ledger-end.txt`); `RT/ledger-beforeset.txt` and `ledger-afterset.txt` (both `EntryBytes=239610395`, `TableBytes=4063232`,
histogram `…65536:2;131072:30;`), `ledger-aftermisses.txt` (`EntryBytes=67084800`, `TableBytes=4063232`); `R64/node/node.out` (`RCSLEDGER registered stage4:type=RcsLedger malloc_size=true`);
`Y64/samples.csv` (RSS 1,343,104 → 1,411,760 → 1,162,464 KiB); `summary.txt` (`TestScript: no errors`, final daemon processes none, node wiped).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the shakedown; hold-fixed checks and ledger validity re-read. |
| 2. Readings | yes | Sizes, entries, ledger values and RSS recomputed from the raw files. |
| 3. Matched row | yes | Every (i), (ii), (iv), "tracks C" and (iii′) check passes. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The ledger's completeness rests on the source and is supported by 0 unknown frees and BASE. |
| 6. Deviations and gaps | yes | The non-blind amendment and the JVM block size are stated. |
| 7. Core question | yes | caps: OHC's native entry bytes = the counter ≤ C, the same for yaml and runtime set. |

**Run 2?** No (2026-10-27). Every cache reading repeats run 1 to the byte, and the ledger relations are exact equalities read in one JMX session;
a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps** (B3g row 1 with the amended B3f (iii′)). It is filed in §8 as a new cluster row; the run-1 cluster row (Not confirmed) is kept.

**End of the re-run:** no `CassandraDaemon`, `cassandra-stress`, `RcsJmx` or `LedgerKnownAnswer` process; ports 7000/7199/9042 free; `$W/node-rcs67` removed;
`$W/cassandra-run67` clean (`git status` 0 entries); no `cassandra.logdir_IS_UNDEFINED/` folder in the repository or the clone (2026-10-27, after the self-check).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "With the row cache enabled, for any capacity C set by `setRowCacheCapacityInMB(C)` (or `row_cache_size: C MiB`), the row cache's used memory stays ≤ C×2^20 bytes while reading a data set many times larger, and the process's off-heap footprint grown by the row cache scales with C; a negative C is refused." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: used ≤ C·2^20 at every read for C = 16/8/4/2/1 MiB, full to 99.6–99.98 %, entries 14,264 → 888 halving with C, OHC evictions exactly N − entries; −1 refused; a runtime shrink of a full cache evicts nothing until the next inserts, then holds at 1,044,288 ≤ 2^20) | caps | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** (added row (b): Size ≤ C in every sample at 128/64/32 MiB and full; R512 all 300,000 rows; RT lazy at the set, then 67,084,800 ≤ 64 MiB; −1 refused; RSS above the no-cache read 51 / 115 / 157 / 415 MB, monotone, slope 0.818 — but ρ 1.343 (R64) and 1.191 (R32) outside [0.85, 1.15], and yaml-set Y64 18.0 % below runtime-set R64, beyond ± 15 %) | caps | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `219ff0f9…`, after the user-authorised B3d, B3e, B3f (iii), B3g, B3h, B4 amendment) | **Confirmed** — B3g row 1 with the amended B3f (iii′): Size ≤ C·2^20 at every sample and full (134,208,000 / 67,084,800 / 33,523,200 B at 128 / 64 / 32 MiB; yaml 64 the same), R512 all 300,000 rows (359,610,395 B); OHC's live native entry blocks (Byteman ledger at `Uns.allocated`/`Uns.freed`) = Entries and = Size exactly at the end of every run, never above C at a sample, within 32 KiB of C; 32 hash tables of 2,097,152 B (R512 4,194,304 B) as derived; Y64 − R64 = 0 B; RT lazy at the set (Size and ledger unchanged), then 67,084,800 ≤ 64 MiB; −1 refused; ΔRSS − base strictly increasing, s = 0.910; ρ and Y64-vs-R64 ΔRSS recorded only (Y64's RSS fell 174 MiB during its read) | caps (the cache's native blocks equal its counter and stay ≤ C, set at runtime or in yaml; plus 2–4 MiB of OHC hash tables, and the JVM's allocator reserves 1,280 B per ≈ 1.2 KB entry) | cluster re-run (§7) + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D (uncommitted); the seventeen step-0 amendments and the two runbook-defect fixes are in the case file, dated, with the sha256 as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column updated. The Estimate line is left as filed. No section was amended for a refutation (none occurred).

**Feedback filed for the cluster re-run (2026-10-27):** the six amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` in the case file (B3d, B3e, B3f (iii), B3g, B3h, B4); a new `_INDEX.md` §4 row (`219ff0f9…`); the case file's section D (new entry); the §1 Stage 4 column (run-1 text kept, re-run verdict appended). The coverage section is not touched. No refutation, so no other case section is amended. Recommendations for stage 3: (1) a native-memory claim for a JNA-malloc cache is best tested on the blocks the library itself takes and returns (here exact to the byte) rather than on RSS, which on this host fell by 174 MiB during one read; (2) the allocator's size class depends on the process — 1,280 B for a 1,025–1,280-B request inside the JVM, 1,536 B in the Python process used at the run-1 audit — so B3d (4)'s g overstated the per-entry reservation by 20 %.
