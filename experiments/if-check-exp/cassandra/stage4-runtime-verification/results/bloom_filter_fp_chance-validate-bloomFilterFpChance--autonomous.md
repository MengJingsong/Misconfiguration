# bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous — stage-4 results  <!-- file: results/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.md -->

> **Case:** [`bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous`](../../stage3-ai-deep-read/cases/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps. Cluster: Confirmed — caps.**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/`](../harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `9c4373f2…7b89` (schema batch). Frozen after the step-0 audit's sixteen amendments (2026-10-26): sha256 **`56ee6b8e3163f8b89e16f524c68d06cd6c5e8c15a7641a15f72300c5c4826688`**, at which both tiers' run 1 ran; a new row in `_INDEX.md` §4. Section D was filled after this hash. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/`](../harness/bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/): `BloomFpChanceCapTest.java` (B2c–B2e as amended), `unit-run.sh`; `make-node-conf.sh` (copied from the denylist case's harness, with the clone, node paths and cluster name changed), `cluster-run.sh` (B3e as amended). Not committed. Instrument checks: (i) the test class compiled in the run clone (`BUILD SUCCESSFUL`, [`run1/unit/compile-summary.txt`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/run1/unit/compile-summary.txt)); (ii) a unit shakedown (`BFP_SHAKE=1`: N = 10,000 and 40,000, 10,000 absent keys) ran every step ([`shakedown/unit-shake-summary.txt`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/shakedown/unit-shake-summary.txt)); (iii) a cluster shakedown (n = 100,000 per keyspace, every step including phase 2 and step 6) ran to the end and left nothing running ([`shakedown/cluster-shake-summary.txt`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/shakedown/cluster-shake-summary.txt)); (iv) `run1/selfcheck.py` was written before any run-1 reading and its parsers were exercised on both shakedowns. Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): fp = 1.0, 0.1, 0.01, 0.001, 0.0001, 0.00007 at N = 1,000,000 and 4,000,000 (1,000,000 absent keys each); rejected values 6.71e-05, 6.0e-05, 1.0000001, 0, -0.1; direct `getFilter(N, 6.0e-05)` for both N. Cluster (B3): one node, 4 GiB heap, `big` format, compaction disabled; six keyspaces `bf_1` (1.0), `bf_01` (0.1), `bf_001` (0.01, the STCS default), `bf_0001` (0.001), `bf_00001` (0.0001, added at the audit), `bf_00007` (0.00007), 4,000,000 partitions each; boundary ALTERs 0.0000671 and 1.01; phase 2 (+4,000,000 into `bf_001`); step 6 (ALTER `bf_001` to 0.1, then `upgradesstables -a`). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**What the source says, derived at the audit.**
- *The check* (`TableParams.java:160-167`): `fp <= probs[20][14]` (= 6.71e-05, `BloomCalculations.java:195-200`) or `fp > 1` throws `ConfigurationException` via `fail` (`:206-209`); the CQL path reaches it through `TableAttributes.validate()` (`:59-66`) from `AlterTableStatement` (`:190-192`).
- *Bits per key* from `computeBloomSpec(20, fp)` over the `probs` table (`BloomCalculations.java:140-172`): 0.1 → 5 (K 3), 0.01 → 10 (K 5), 0.001 → 15 (K 7), 0.0001 → 20 (K 10), 0.00007 → 20 (K 13); fp = 1.0 → `AlwaysPresent` (`FilterFactory.java:62-63`). Allocation `ceil((n·b + 20)/64)·8` B (`FilterFactory.java:70-75`, `OffHeapBitSet.java:39-53`); serialized = + 8 B (`BloomFilterSerializer.java:65-70`, `OffHeapBitSet.java:139-142`).
- *Key counts on the node*: a flush sizes each filter with the memtable's exact partition count (`Flushing.java:117`); a rewrite (`upgradesstables`) with the source sstable's HyperLogLog++ estimate (`CompactionAwareWriter.java:84,235`, `DefaultCompactionWriter.java:62-64`, `SSTableReader.java:302-342`, p = 13 at `MetadataCollector.java:147`). The writer reads the table's current fp (`SortedTableWriter.java:445`); a loaded filter is not rebuilt on an fp change (`FilterComponent.java:43,119`).
- *Instrument*: the `BloomFilterOffHeapMemoryUsed` gauge sums `bitset.offHeapSize()`, i.e. the byte count given to `Memory.allocate` (`BloomFilterMetrics.java:68-72`, `SSTableReaderWithFilter.java:116-124`); the Filter.db file sizes are the independent disk reading.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap bitset bytes and Filter.db bytes. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: six accepted values incl. 0.01 (STCS default) and 0.1 (LCS default); B3b: five (six after amendment). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Gauge = native allocation size; Filter.db file sizes as the real disk resource; process RSS as context; gap (no per-allocation native reading) named in the B3d amendment. |
| A. Core question | usage driven to the limit and past it | Partly → Met after amendment | Unit: 0.0001 and 0.00007 both at 20 bits, values past the bound rejected. Cluster had one b = 20 value: `bf_00001` added. |
| B. Logic | each step says what it establishes | Met | B2e/B3e with B2h/B3h. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f exact; "small fixed header", "sampling error", "≈", "a few hundred bytes", step-6 tolerance given numbers. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Rows had meanings without verdicts; added rows for counter vs disk, invalid run, accepted value failing, control failing. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Exact sizes per fp plus the rejection messages and the direct-call control (unit); refused ALTERs plus read-back (cluster). |
| B. Logic | alternative explanations and their controls | Met | N×4 (per key vs fixed), identical data in six tables, compaction disabled (now with evidence), du vs gauge. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Output location and format; absent-key inconsistency (B2d 1M vs B2e N). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | cqlsh/stress commands, limit-reached check (`totalRows`), sampling points. |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local` paths, `-R`, `du -cb` (not on macOS). |
| D. Runnable | workload arithmetic reaches the limit | Met | 28M writes at about 60k/s, ≈ 6 GB disk of 129 GiB free, 4 GiB heap of 32 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | All files in section C; every cited line matches. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, runner, output from the test log | Amendment 2026-10-26 (uncommitted) | `/local`; XML is not where stdout lands here. |
| 2 | B2c/B2e: 1M absent keys (`N..N+999,999`), order | Amendment 2026-10-26 | B2d and B2e disagreed. |
| 3 | B2d/B2e: `BFP` lines; stop condition | Amendment 2026-10-26 | Open. |
| 4 | B2f: serialized = off + 8, K per fp, Poisson 3σ FP bound, exact messages | Amendment 2026-10-26 | Derived. |
| 5 | B2g/B2h: verdicts per row; added rows; control evidence | Amendment 2026-10-26 | Group B. |
| 6 | B3a: this host; node dir; start method | Amendment 2026-10-26 | Paths, no root. |
| 7 | B3b: keyspace `bf_00001` (0.0001) | Amendment 2026-10-26 | Ceiling observable on the node. |
| 8 | B3c: commands; `totalRows` limit-reached check | Amendment 2026-10-26 | Open. |
| 9 | B3d: `stat -f %z`; sstablemetadata fields; instrument named; RSS context; exact recorded checks | Amendment 2026-10-26 | BSD; group A. |
| 10 | B3e: order, one script, shakedown | Amendment 2026-10-26 | Places the added keyspace. |
| 11 | B3f: ±1%, 300 B per sstable, step 6 ±4% (HLL++ p = 13), message text | Amendment 2026-10-26 | Derived. |
| 12 | B3g/B3h/B4: verdicts per row; added rows; control evidence; paths | Amendment 2026-10-26 | Group B. |
| 13 | Test an existing table whose fp is ALTERed to exactly 1.0 (filter dropped on next load, A1) | Left for stage 3 | Not in B1. |
| 14 | A3 could say that the rewrite path sizes filters from an HLL estimate, so a rewritten sstable's filter is not exactly `keys × b` | Left for stage 3 (section D) | Observed in step 6, consistent with A3's overshoot note. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (clone 20:24, build 20:24–20:25; audit and freeze to 20:30; compile check 20:30:37; unit shakedown 20:30:58; cluster shakedown 20:32:20–20:35:34; unit run 1 20:36:39–20:36:58; cluster run 1 20:37:04–20:47:56) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS, solid state), 129 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042, 9091 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork, 1 GiB. Node: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (`-Xms4G -Xmx4G -XX:+UseG1GC`, read from `JVM Arguments`) |
| Ant | 1.10.18 |
| Python | 3.8.11 (cqlsh; self-check) |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run42` (fresh clone, `ant -Dlocal.repository=$W/m2 build-test`, 58 s); `W=~/Library/Caches/stage4`; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-bf42` (data, commit log, hints), wiped before and after each cluster run |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/bloom_filter_fp_chance-validate-bloomFilterFpChance/` — `clone.log`, `build-test-run42.log`, `unit-compile/`, `unit-shake/`, `unit-r1/` (ant log, JUnit XML, test log, `stdout.txt`, `summary.txt`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `node/` logs, seven `stress-*.txt`, `alter-*.txt`, `readback-*.txt`, `compactionhistory-*.txt`, `schema.txt`; per record point `P1/`, `ALL/`, `P2/`, `S6a/`, `S6b/` × keyspace: `tablestats.txt`, `filter-files.txt`, `ls-l.txt`, `sstablemetadata.txt`, `rss.txt`) |

Machine facts relied on (from `environment-advisor.md` and the session brief): all files under `$W` (no `mkdir` in `$HOME`; cqlsh with `HOME=$W/home`); every `ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run outside the tool sandbox; no `setsid` (node started as a tracked `nohup … -f &` process, pid from `$!`, stopped by drain and `kill <pid>`; the daemon name split in the scripts' patterns); BSD tools (`stat -f %z` instead of `du -cb`, `sed -i ''`); `DatabaseDescriptor.daemonInitialization()` in the test's `@BeforeClass`; test stdout from `build/test/logs/**/TEST-<class>.log`, one line per `println`; `nodetool disableautocompaction` kept because the node is not restarted in this tier (evidence: no `bf_` line in `compactionhistory` before step 6); no foreground sleep near the tool timeout (cluster run in the background, polled); shakedowns before run 1; bounds derived from source; `selfcheck.py` written before readings. No guardrail is on the path (schema DDL by a superuser under AllowAllAuthenticator, and no guardrail reads `bloom_filter_fp_chance` in 5.0.9's `TableAttributes`/`TableParams`), so the authenticator was left as shipped.

## 3. Runbook defects

None. Both tiers ran as amended at `56ee6b8e…6688`.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stdout.txt`, `junit-testsuite.txt`, `compile-summary.txt`); [`run1/cluster/`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `yaml-tail.txt`, `jvm-arguments.txt`, `schema.txt`, `alter-*.txt`, `readback-*.txt`, `stress-*-results.txt`, `compactionhistory-*-bf.txt`; per record point and keyspace `tablestats-bloom.txt`, `filter-files.txt`, `sstablemetadata-excerpt.txt`, `rss.txt`).

### 4.1 Readings

**Unit tier** (JUnit 1 test, 0 failures, 0 errors; `BFP done` present; one run)

| fp (b) | N = 1M offHeap / serialized | N = 4M offHeap / serialized | Predicted (B2f) | hashCount | fpCount of 10^6 (1M / 4M; bound) | validate |
|---|---|---|---|---|---|---|
| 1.0 (0) | 0 / 0, `AlwaysPresentFilter` | 0 / 0, `AlwaysPresentFilter` | 0 | – | 1,000,000 / 1,000,000 | ok |
| 0.1 (5) | 625,008 / 625,016 | 2,500,008 / 2,500,016 | 625,008 / 2,500,008 | 3 | 92,238 / 91,802 (≤ 100,948) | ok |
| 0.01 (10) | 1,250,008 / 1,250,016 | 5,000,008 / 5,000,016 | 1,250,008 / 5,000,008 | 5 | 9,366 / 9,455 (≤ 10,300) | ok |
| 0.001 (15) | 1,875,008 / 1,875,016 | 7,500,008 / 7,500,016 | 1,875,008 / 7,500,008 | 7 | 1,049 / 1,018 (≤ 1,094) | ok |
| 0.0001 (20) | 2,500,008 / 2,500,016 | 10,000,008 / 10,000,016 | 2,500,008 / 10,000,008 | 10 | 89 / 83 (≤ 130) | ok |
| 0.00007 (20) | 2,500,008 / 2,500,016 | 10,000,008 / 10,000,016 | 2,500,008 / 10,000,008 | 13 | 81 / 84 (≤ 95) | ok |

Evidence: `run1/unit/stdout.txt` (from the raw test log). No false negative on the first 1,000 inserted keys in any filter.

| Test or assertion | Result | Evidence |
|---|---|---|
| reject 6.71e-05, 6.0e-05, 1.0000001, 0, -0.1 | each `ConfigurationException`, `bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0 (got 6.71E-5 / 6.0E-5 / 1.0000001 / 0.0 / -0.1)` | `stdout.txt` |
| direct `getFilter(N, 6.0e-05)`, N = 1M and 4M | each `UnsupportedOperationException`, `Unable to satisfy 6.0E-5 with 20 buckets per element` | `stdout.txt` |

**Cluster tier** (one node; every stress run `Total partitions: 4,000,000`, `Total errors: 0`, 60–66k op/s; 12 sstables per keyspace after its flush, all `nb-*-big`; every sstable's `Bloom Filter FP chance` = its table's fp; `totalRows` sum 4,000,000 per keyspace; no `bf_` compaction before step 6; system.log 0 ERROR lines; `Number of partitions (estimate)` 3,967,638 per keyspace, recorded)

| Keyspace (fp, b) | Observable | Reading | Prediction / band (B3f amendment) | Evidence |
|---|---|---|---|---|
| `bf_1` (1.0, 0) | gauge / space / Filter.db files | 0 / 0 / none | 0, no Filter.db | `run1/cluster/P1/bf_1/` |
| `bf_01` (0.1, 5) | gauge | **2,500,072 B** (+0.003%) | 2,500,000 ± 1% (exact Σ 2,500,072) | `P1/bf_01/tablestats-bloom.txt` |
| `bf_001` (0.01, 10) | gauge | **5,000,072 B** (+0.001%) | 5,000,000 ± 1% (exact 5,000,072) | `P1/bf_001/` |
| `bf_0001` (0.001, 15) | gauge | **7,500,072 B** (+0.001%) | 7,500,000 ± 1% (exact 7,500,072) | `P1/bf_0001/` |
| `bf_00001` (0.0001, 20) | gauge | **10,000,080 B** (+0.0008%) | 10,000,000 ± 1% (exact 10,000,080) | `P1/bf_00001/` |
| `bf_00007` (0.00007, 20) | gauge | **10,000,072 B** (+0.0007%) | 10,000,000 ± 1% (exact 10,000,072); within 1% of `bf_00001` | `P1/bf_00007/` |
| each of the five | Filter.db sum (12 files) and `Bloom filter space used` | gauge + 96 B for each (= + 8 B × 12) | ≤ 300 B × 12 from the gauge (exact + 96) | `P1/*/filter-files.txt`, `tablestats-bloom.txt` |
| all six (ALL) | re-read before step 4 | identical to P1 | stable | `ALL/*/` |
| boundary ALTER 0.0000671 | cqlsh | exit 2, `ConfigurationException: bloom_filter_fp_chance must be larger than 6.71E-5 and less than or equal to 1.0 (got 6.71E-5)` | refused with the message | `alter-0.0000671.txt` |
| boundary ALTER 1.01 | cqlsh | exit 2, same message `(got 1.01)` | refused | `alter-1.01.txt` |
| `bf_01` read-back | `system_schema.tables` | 0.1 | 0.1 | `readback-bf_01.txt` |
| phase 2 `bf_001` (8M keys) | gauge / Filter.db | **10,000,144 B** / 10,000,336 B (24 sstables, `totalRows` 8,000,000) | 10,000,000 ± 1% (exact 10,000,144) | `P2/bf_001/` |
| step 6 after ALTER to 0.1 | gauge / read-back | **10,000,144 B** (= P2) / 0.1; sstables still report 0.01 | unchanged | `S6a/bf_001/`, `readback-bf_001.txt` |
| step 6 after `upgradesstables -a` | gauge / FP chance / rows | **4,993,696 B** (−0.13%); all 24 sstables 0.1; `totalRows` 8,000,000; 24 `Upgrade sstables` lines | 5,000,000 ± 4%; exact from the HLL estimates 4,993,696 | `S6b/bf_001/`, `compactionhistory-S6b-bf.txt` |
| RSS (context) | `ps -o rss` | 4.06–4.33 GiB from phase 1 to step 6a (it does not move with the filter sizes, which are at most 10 MB), 3.84 GiB after the rewrite | context only | `*/rss.txt` |

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 1 test, 0 failures, 0 errors [observed: `run1/unit/junit-testsuite.txt`]; `BFP done` present, every filter line present [observed: `stdout.txt`]. The limit is reached: the accepted range is driven to its 20-bit end (0.0001, 0.00007) and past each bound (five rejected values). Valid.
2. **Readings** — nothing unusual. fpCount at 0.0001 and 0.00007 (81–89 per 10^6) exceeds fp × 10^6 but lies within the amended Poisson bound; the theoretical rates of the chosen specs are 8.89e-05 and 6.79e-05 (`probs[20][10]`, `probs[20][13]`) [inferred: source].
3. **Matched row** — B2g row 1, "Sizes match the table exactly and grow 4× with N", with the amendment's conditions: all twelve offHeap values equal B2f; serialized = offHeap + 8 for all ten Bloom filters; `validate=ok` for all six accepted values; the five boundary values rejected with the exact message; step 4 throws for both N; fp = 1.0 gives `AlwaysPresentFilter` with 0 B [observed: `stdout.txt`].
4. **Excluded rows** — row 2 (not exact): exact [observed]. Row 3 (equal for fp ≠ 1.0): 625,008 to 2,500,008 at 1M [observed]. Row 4 (a boundary value passes): none [observed]. Row 5 (fp = 1.0 non-zero): 0 [observed]. Added (a) accepted failing: none; (b) serialized ≠ +8: none; (c) step 4 not throwing: throws; (d) FP above bound: none; (e) invalid: no [observed].
5. **Observed vs. inferred** — that `offHeapSize()` is the native allocation is inferred from the source (`OffHeapBitSet.java:39-53`, `Memory.allocate(byteCount)`); the conclusion rests on the exact match, not on this inference.
6. **Deviations and gaps** — instruments added at the audit (`BFP` lines, `validate`, false-negative check); one run.
7. **Core question** — the setting sets the filter's native allocation exactly per key: 5 / 10 / 15 / 20 / 20 bits per key for 0.1 / 0.01 / 0.001 / 0.0001 / 0.00007, 0 B at 1.0, ×4 bytes for ×4 keys; the check at `:161` refuses every value that would ask for more than 20 bits per key (and the direct call without it fails), so 20 bits per key is the cap.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — node up with the 4 GiB G1 heap [observed: `summary.txt` `JVM` line]; six tables created with their fp and no compression [observed: `schema.txt`]; every keyspace `totalRows` 4,000,000 (bf_001 8,000,000 after phase 2) [observed: `*/sstablemetadata-excerpt.txt`]; stress 0 errors each [observed: `stress-*-results.txt`]; no `bf_` compaction before step 6 and 12 sstables per keyspace throughout phase 1 [observed: `compactionhistory-ALL-bf.txt`, `-S6a-bf.txt`, `tablestats-bloom.txt`]; `big` format [observed: `summary.txt` FORMAT line]; 0 ERROR lines; no process left. Valid.
2. **Readings** — nothing unusual. Each gauge equals Σ ceil((rows_i·b + 20)/64)·8 over its 12 sstables exactly, as derived for flush sizing [observed vs recorded check in `run1/selfcheck.out`]. `Number of partitions (estimate)` reads 3,967,638 (an HLL merge, −0.8%); the exact count is `totalRows` [observed].
3. **Matched row** — B3g row 1, "Per-keyspace bytes follow b(fp) × N/8 within 1-2%", with the amendment's conditions: (i) all five gauges within 1% (largest deviation +0.003%), `bf_1` 0 with no Filter.db; (ii) Filter.db and space = gauge + 96 B; `bf_00001` and `bf_00007` differ by 8 B; both ALTERs refused with the message, read-back 0.1; phase 2 10,000,144 B within 1% of 10,000,000 [observed: files in 4.1].
4. **Excluded rows** — row 2 (constant factor): deviations ≤ 0.003% [observed]. Row 3 (equal across fp): 2.5 / 5.0 / 7.5 / 10.0 / 10.0 MB [observed]. Row 4 (`bf_1` filters): none [observed]. Row 5 (ALTER succeeds): both exit 2 with the message [observed]. Row 6 (phase 2 does not double): 5,000,072 → 10,000,144 [observed]. Added (a) disk vs gauge: + 96 B [observed]; (b) invalid: no [observed]; (c) step 6 off prediction: no — unchanged after the ALTER, 4,993,696 B (−0.13%) and all FP 0.1 after the rewrite [observed].
5. **Observed vs. inferred** — that the gauge reads the native allocation is inferred from the source; the Filter.db bytes (a real disk resource, written from the same bitset) agree with it to the derived 8 B per sstable [observed]. That step 6's 4,993,696 B comes from HLL-sized filters is supported by its exact equality with Σ ceil((card_i·5 + 20)/64)·8 over the pre-upgrade `Estimated cardinality` values [observed, recorded check].
6. **Deviations and gaps** — the keyspace `bf_00001` and the instruments added at the audit; `stat -f %z` instead of `du -cb`; no per-allocation native-memory reading (process RSS recorded as context only, as the file says). One run.
7. **Core question** — on a node, the table's setting decides the filter memory and disk per partition key: 4M keys cost 0 / 2.5 / 5.0 / 7.5 / 10.0 / 10.0 MB off heap (and the same + 8 B per sstable on disk) for fp 1.0 / 0.1 / 0.01 / 0.001 / 0.0001 / 0.00007, doubling with twice the keys; values beyond the 20-bit end are refused at DDL time and the table keeps its setting. An ALTER changes only newly written sstables (here, after `upgradesstables`, sized from HLL estimates).

**Conclusion (cluster tier):** B3g row 1 — **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/run1/selfcheck.py), written before any run-1 reading and independent of the harness summaries (it re-reads the raw test log and JUnit XML; per record point the raw `tablestats.txt`, `sstablemetadata.txt`, `filter-files.txt` and `ls -l` listing, whose Filter.db sizes it sums independently of the `stat` file; the raw stress outputs, ALTER outputs, read-backs, compaction histories and `system.log`): **203 checks, 0 failed** (unit 84, cluster 119); unit "row 1 → Confirmed, caps", cluster "row 1 → Confirmed, caps; step 6 as predicted: True" ([`run1/selfcheck.out`](bloom_filter_fp_chance-validate-bloomFilterFpChance--autonomous/run1/selfcheck.out)). Two changes after it was written, both after the shakedowns and before any run-1 reading: a `%` formatting error, and the unit per-key check changed from "ratio exactly 4" (wrong: word rounding) to "|(off₄ − 8) − 4·(off₁ − 8)| ≤ 40 B". No bound of the case file was changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts and `BFP done`; `totalRows`, stress errors, compaction history, format, ERROR count from the raw files. |
| 2. Readings | yes | Exact per-sstable sums re-derived from raw `sstablemetadata`; the FP counts within bound. |
| 3. Matched row | yes | Unit: all twelve sizes, ten +8 checks, five messages, two direct throws. Cluster: five bands, disk +96, ceiling, ALTERs, read-back, phase 2. |
| 4. Excluded rows | yes | Each excluded row's reading re-read. |
| 5. Observed vs. inferred | yes | The one inference (gauge = native allocation) is backed by the disk reading, not used alone. |
| 6. Deviations and gaps | yes | Stated; none changes a reading's meaning. |
| 7. Core question | yes | Setting → b(fp) (`computeBloomSpec`) → `ceil((n·b + 20)/64)·8` B per filter → gauge and Filter.db, exact; bound → refused DDL and the direct-call failure. |

### 5.2 Run 2?

**No** — decided 2026-10-26. Both tiers are exact (unit) or exact to the byte against the per-sstable formula (node), observed directly, and the self-check holds in every part; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "For a fixed set of N partition keys written to fresh sstables: bloom filter off-heap bytes equal `Σ_sstables ceil((keys_i × b(fp) + 20)/64) × 8`, with b(fp) ∈ {0, 5, 10, 15, 20} for fp ∈ {1.0, 0.1, 0.01, 0.001, 0.00007}; `Filter.db` bytes track the same; any fp ≤ 6.71e-05 or > 1 is refused, so no table can exceed 20 bits per key." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: offHeap exactly `ceil((N·b + 20)/64)·8` at all 12 points, b = 0/5/10/15/20/20; serialized = + 8; five boundary values refused with the exact message; direct `getFilter(N, 6.0E-5)` throws) | caps | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (row 1: 4M keys → 0 / 2,500,072 / 5,000,072 / 7,500,072 / 10,000,080 / 10,000,072 B off heap for fp 1.0 / 0.1 / 0.01 / 0.001 / 0.0001 / 0.00007, Filter.db + 96 B each; both boundary ALTERs refused; phase 2 → 10,000,144 B; step 6 as predicted) | caps | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted); the sixteen step-0 amendments are in the case file, dated, with the sha256 as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column updated. The Estimate line is left as filed. No section was amended for a refutation (none occurred).
