# prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous — stage-4 results  <!-- file: results/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md -->

> **Case:** [`prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous`](../../stage3-ai-deep-read/cases/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g rows 1 and 2). **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1 and the added bypass row: the cache is capped and follows the knob; the `system.prepared_statements` memtable grows by one partition per distinct PREPARE whatever the knob). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/`](../harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions; the closed `storePreparedStatement-capacityToBytes` file was
> used only as a worked example and for its instruments' pattern.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `ffb60647…3251`). Frozen after the step-0 audit's sixteen amendments (2026-10-25, before any harness or reading): sha256 `ea4b8f5f614105edbc7c96345b4a596946741e9d6c82825386f69229b9f6222e`. One runbook fix during run 1 (B2a, Program 1's `java` command; §3 defect 1) gave the version both tiers ran at: sha256 **`f325aef5d053674c79374be74776bc69c5cea22a06cbdf13e3252f09c2874dbc`**. Both are new rows in `_INDEX.md` §4. Not committed (no commit was asked for). |
| **Harness** | [`../harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/`](../harness/prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/): `ConfigProbe.java` (Program 1, the case's text verbatim), `PreparedCacheCapProbeTest.java` (Program 2), `unit-run.sh` (unit); `prep.py` (bundled-driver client), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order). Instrument checks before run 1: both Java files compiled against the run clone (`instrument-compile.log`, rc 0); cluster harness shakedown at 2 MiB with 2,000 statements (`shakedown/sd-k2/`, a harness check, not a reading). Self-check: [`run1/selfcheck.py`](prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/selfcheck.py). |
| **Tiers and values** | Unit (B2): Program 1 with `0MiB`, `1MiB`, unset (auto), `-Xmx1G`, each its own `java`; Program 2 with C ∈ {1, 4, 16 MiB, auto = 10 MiB}, one `ant testsome` JVM per value, N = ⌈4 × 16 MiB / w⌉ distinct 50-column SELECTs, controls B2h (a) and (b) in every JVM. Cluster (B3): one node, `MAX_HEAP_SIZE=2G`, `0MiB` (start failure), `2MiB`, auto (= 10 MiB), `32MiB` with 20,000 distinct PREPAREs each, plus the B3h control lifetime at `32MiB` (500 distinct, then 40 re-prepares of each). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes of the prepared-statement cache; the operand is the Caffeine weight (`key.size() + measureDeep`), a byte estimate (`QueryProcessor.java:947-958`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Program 1 had the default; Program 2 (1/4/16 MiB) and the cluster (0/2/32 MiB) did not, and the cluster had only two capped values. Auto added to both (amendments B2b, B3b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: weight read exactly by reflection (amendment B2d), coarse heap logged without a prediction. Cluster: `QueryHandler$Prepared` instance count and the `jmap -histo:live` total (amendment B3d; no heap dump/MAT here). The cache's own retained size is read only as a difference between knob values (named gap). |
| A. Core question | usage driven to the limit and past it | Met | Unit offers 4 × 16 MiB at every value; cluster 20,000 statements (≈ 400 MiB of would-be weight at w ≈ 21 KB) against at most 32 MiB. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps without saying what each shows; the readings tables carry it. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈", "±10 %" for the plateau only, "roughly 30 MiB × ratio" — tolerances fixed for every relation (amendments B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | No rows for a Program 1 failure unrelated to the knob, counter not following the cache, control failure, limit never reached at 2 MiB, real heap not following the weight, or heap growth outside the cache. Added (amendments B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Plateau ∝ C plus evictions > 0 (the size-eviction branch, `QueryProcessor.java:132-137`) and, in the cluster, the per-minute discard warning; startup refusal of `0MiB` for claim (a). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | B2h/B3h controls named but their starting state and expected values were open; derived from the source (amendments B2h, B3h). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1 state the claim and mechanism. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Placeholder statement text (`ks.tbl`), column type, keyspace rule, JVM split, order (amendments B2a, B2c, B2e, B3c, B3e). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The cluster had no wait for the per-minute warning that B3g row 1 requires (a task at a fixed 1-minute rate, `QueryProcessor.java:120-126`): 65 s wait added (B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local/...` paths, a network clone and `pip install` do not exist/work here: this host's clone, probe dir, node dir and the bundled driver (amendments B2a, B3a, B3c). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit N ≈ 3,000 statements × ≈ 21 KB ≈ 64 MiB offered; cluster 20,000 statements; 150 GiB free disk; node data < 1 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:795-810, 4178-4181`, `DataStorageSpec.java:160-163` (`0MiB` text), `QueryProcessor.java:93, 107, 112-138, 142-145, 239-242, 731-767, 815-833, 947-973`, `CQLMetrics.java:44, 48`, `CassandraDaemon.java:751-767` and the `:887` log line, `MD5Digest.size()` = 16 + 4. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, probe dir and recipe; one `ant testsome` per value | Amendment 2026-10-25 | Paths did not exist; once-per-JVM initialisation. |
| 2 | B2b: auto added to Program 2 | Amendment 2026-10-25 | Group A default. |
| 3 | B2c: exact statement, table, no keyspace, N rule | Amendment 2026-10-25 | Placeholders; keyspace doubles entries (HANDOFF §10). |
| 4 | B2d: weightedSize read by reflection, sum as cross-check | Amendment 2026-10-25 | B2f's prediction is about it; the file left it optional. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact Program 1 lines and tolerances (i)–(iv) | Amendment 2026-10-25 | "≈" without tolerance. |
| 7 | B2g: five rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: controls start from an empty cache; expected values | Amendment 2026-10-25 | "C unchanged", "count stays 1" ambiguous. |
| 9 | B3a: this host; readiness | Amendment 2026-10-25 | Paths. |
| 10 | B3b: auto added; log read-back | Amendment 2026-10-25 | Group A; restart-only knob. |
| 11 | B3c: bundled driver, no session keyspace | Amendment 2026-10-25 | No network installs; keyspace rule. |
| 12 | B3d: sampling between batches; heap from the live histogram | Amendment 2026-10-25 | No MAT; `jstat` cannot attach here. |
| 13 | B3e: order and a 65 s wait for the discard warning | Amendment 2026-10-25 | The warning row could not fire otherwise. |
| 14 | B3f: relations (i)–(vi) | Amendment 2026-10-25 | Tolerances. |
| 15 | B3g: four rows | Amendment 2026-10-25 | Group B. |
| 16 | B3h: both controls in one lifetime; expected values; validity bound on w | Amendment 2026-10-25 | Undefined. |
| 17 | B2d's coarse heap reading and B1 (b)'s "retained heap … scales with C" have no unit-tier prediction | Left for stage 3 | Not needed for a valid run; the cluster tier carries the heap part. |
| 18 | B4 mentions `/local` paths and `pgrep -f ConfigProbe` | Left for stage 3 | Superseded by the B2a/B3a amendments. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit 09:11–09:14 EDT; shakedown 09:14–09:15; cluster 09:16–09:27 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64 (T6000); 10 cores, 32 GiB RAM; internal SSD (APFS, `/dev/disk3s1`), 150 GiB free at start; loopback 127.0.0.1–.3 present (one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run (rechecked at the end, §8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Program 1: plain `java -Xms1G -Xmx1G` (+ the JDK 11 module flags after runbook fix 1). Program 2: `ant testsome` forks (maxMemory 1,056,309,248 B). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`) |
| Ant | 1.10.18 |
| Python / driver | Python 3.8.11; driver bundled in the clone, `cassandra-driver-internal-only-3.29.0.zip`, protocol 5 |
| Local `cassandra-src` clone commit | `$W/cassandra-run10` = `~/Library/Caches/stage4/cassandra-run10`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 49 s) |
| Case-file commit / harness commit | filed `0dcdfe0`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-psca/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime (< 1 MB data per run); Program 1 data under `$W/probe-psca/data` |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/prepared_statements_cache_size-applySimpleConfig/` — `clone-build-run10.log`, `instrument-compile.log`, `unit-attempt0/` (before runbook fix 1 and harness fix H1), `unit/` (`p1-*.out`, `ant-k*.log`, `TEST-k*.xml`, `stage4.out`, `summary.txt`, `commands.log`), `shakedown/sd-k2/` (not evidence), `cluster/{startfail-0,k2,kauto,k32,ctl32}/` (`system.log`, `node.out`, `samples.csv`, `histo-*.txt`, `heapinfo-*.txt`, `summary.txt`, `commands.log`, `client.err`), `cluster/chain.out` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| 1 | unit, attempt 0 | B2a/B2e step 1, Program 1 | The case's `java` command runs without JDK 11 module flags; all three variants printed `REJECT ExceptionInInitializerError: null / root: java.lang.IllegalAccessException: access to public member failed: jdk.internal.ref.Cleaner.clean…, from org.apache.cassandra.io.util.FileUtils` — `daemonInitialization` fails before the knob is read (`run1/unit-attempt0/`) | add the seventeen `--add-exports`/`--add-opens` flags of `build.xml:244-261` to the command; dated amendment to B2a; the unit tier restarted from Program 1 | 2026-10-25; §9a (B2f/B2g) unchanged; new sha256 `f325aef5…` | uncommitted |
| H1 | unit, attempt 0 | B2e step 2 (harness) | `unit-run.sh` called `ant testsome` without `-Dlocal.repository=$W/m2`; the resolver looked in `$W/home/.m2` and `BUILD FAILED` (missing jacoco agent jar) before any test compiled — no Program 2 reading existed | harness only: pass `-Dlocal.repository=$W/m2` | 2026-10-25; harness defect | none |

The cluster shakedown (2 MiB, 2,000 statements, `WAIT_AFTER=5`) found no harness defect; its readings are not used.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/unit/commands.log`, `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/cluster/<label>/commands.log`, `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/chain.out`.

### 4.1 Readings

**Unit tier** (`prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/unit/summary.txt`, `stage4.out`, `p1-*.line`; one JVM per row; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| Program 1, `0MiB` | `REJECT ConfigurationException: prepared_statements_cache_size option was set incorrectly to '0MiB', supported values are <integer> >= 0.` (root: the same exception) | `p1-0MiB.line` |
| Program 1, `1MiB` | `OK getPreparedStatementsCacheSizeMiB=1` | `p1-1MiB.line` |
| Program 1, unset (`-Xmx1G`) | `OK getPreparedStatementsCacheSizeMiB=10` | `p1-unset.line` |
| Calibration (every JVM) | `id.size()` 20 B, `pstmntSize` 21,792 B, **w = 21,812 B**; 1 entry after one prepare; `keyspace_in_clientstate=null`; N = ⌈4 × 16 MiB / w⌉ = 3,077 | `stage4.out` |

| C | cap (B) | max weightedSize over 31 samples (≤ cap + w?) | final count | C/w | evicted (N − count) | ratio to 1 MiB | B2h (a): ⌊count/2⌋ re-prepared into an empty cache | B2h (b): one text × N |
|---|---|---|---|---|---|---|---|---|
| 1 MiB | 1,048,576 | 1,046,976 (yes) | 48 | 48.07 | 3,029 (3,029) | 1 | 24 → count 24, evicted 0 | count 1, evicted 0 |
| 4 MiB | 4,194,304 | 4,187,904 (yes) | 192 | 192.29 | 2,885 (2,885) | 4.000 | 96 → 96, 0 | 1, 0 |
| 16 MiB | 16,777,216 | 16,773,428 (yes) | 769 | 769.17 | 2,308 (2,308) | 16.021 | 384 → 384, 0 | 1, 0 |
| auto = 10 MiB (`maxMemory` 1,056,309,248) | 10,485,760 | 10,469,760 (yes) | 480 | 480.73 | 2,597 (2,597) | 10.000 | 240 → 240, 0 | 1, 0 |

The reflection weightedSize equals the sum of `key.size() + pstmntSize` at every sample (124/124). Coarse heap after GC (no prediction): +3.79 · +6.43 · +17.70 · +12.43 MB at 1 · 4 · 16 · auto MiB.

**Cluster tier** (`prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous/run1/cluster/<label>/summary.txt`, `samples.csv`, `histo-lines-*.txt`, `system-log-excerpt.txt`; one node lifetime per row; 20,000 distinct PREPAREs in 20 batches, 0 client errors in every run)

| Value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| `0MiB` | startup | daemon | exited after ≈ 4 s, never listened for CQL; `system.log`: `ERROR [main] … CassandraDaemon.java:887 - Exception encountered during startup: prepared_statements_cache_size option was set incorrectly to '0MiB', supported values are <integer> >= 0.` | `startfail-0/startfail.txt`, `system-log-excerpt.txt` |
| `2MiB` | A | read-back / count / evicted | `Initialized … with 2 MiB`; count 96 from the first sample at 1,000 to the end (21 samples + final); evicted 19,904 = 20,000 − 96 | `k2/samples.csv` |
| `2MiB` | A | heap | `Prepared` instances 29 → 127 (count + 31); live bytes 47,382,408 → 70,944,296 (+23.56 MB); memtable `AtomicBTreePartition` 43 → 20,044, `BTreeRow` 6 → 20,007 | `k2/histo-lines-*.txt` |
| `2MiB` | A | discard warning | 2 lines, first `7080 prepared statements discarded in the last minute because cache limit reached (2 MiB)` | `k2/discard-warnings.txt` |
| auto | B | read-back / count / evicted | `… with 10 MiB`; count 482 constant from 1,000 on; evicted 19,518 = 20,000 − 482 | `kauto/samples.csv` |
| auto | B | heap / warning | instances 513 (count + 31); live 47,377,552 → 78,122,216 (+30.74 MB); partitions +20,001, rows +20,001; 2 warnings (first: 7,518 … (10 MiB)) | `kauto/` |
| `32MiB` | C | read-back / count / evicted | `… with 32 MiB`; count 1,542 constant from 2,000 on; evicted 18,458 = 20,000 − 1,542 | `k32/samples.csv` |
| `32MiB` | C | heap / warning | instances 1,573 (count + 31); live 47,480,144 → 97,892,248 (+50.41 MB); partitions +20,001, rows +20,001; 2 warnings (first: 6,458 … (32 MiB)) | `k32/` |
| `32MiB` | control (B3h) | count / evicted | 500 distinct → count 500, evicted 0; the same 500 texts × 40 (20,000 PREPAREs, 0 errors) → count 500, evicted 0, after the 65 s wait 500; 0 discard warnings; instances 530 (500 + 30); partitions +501 | `ctl32/samples.csv`, `ctl32/summary.txt` |

Derived (recomputed by `selfcheck.py`): count(32)/count(2) = 16.062, count(auto)/count(2) = 5.021; per-entry weight cap/count = 21,845 · 21,755 · 21,760 B; `Prepared` instances − count = 31 in all three runs; **D = live(32) − live(2) = 26,947,952 B = 0.857 × 30 MiB**; D(auto − 2) = 7,177,920 B = 0.856 × 8 MiB.

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — [observed: `unit/summary.txt`, `stage4.out`] the knob read back as set in every JVM (`cap_mib` 1/4/16/10 = expected auto 10); the cap was passed 4–64× (N × w = 67.1 MB offered); one entry per prepare; both B2h controls met their frozen expectations at every value; only the yaml line differed between JVMs (`p2-yaml-diff-*.txt`). Valid.
2. **Readings** — nothing unusual: weightedSize always within one entry below the cap (never above it), count exactly ⌊C/w⌋.
3. **Matched rows** — B2g row 1, "0MiB rejected, 1MiB accepted, auto = 10" [observed: `p1-*.line`, exact text of amended B2f]; B2g row 2, "weightedSize plateaus at ≈ C and scales with C; evictions > 0" [observed: B2f (i) max ≤ cap at 4/4; (ii) counts 48/192/769/480 vs C/w 48.07/192.29/769.17/480.73; (iii) evicted = N − count exactly and > 0; (iv) ratios 4.000/16.021/10.000].
4. **Excluded rows** — "grows past C + w": max weightedSize ≤ cap in 124/124 samples. "Not proportional to C": ratios within 0.2 % of C. "N reached without evictions": 2,308–3,029 evictions. Added rows: `0MiB` was not accepted; `1MiB` not rejected and auto = 10; Program 1 failed for another reason only before runbook fix 1 (attempt 0, §3), not at the frozen version; the counter follows the cache (evicted = N − count); no control missed.
5. **Observed vs. inferred** — all statements observed; none inferred.
6. **Deviations and gaps** — runbook defect 1 and harness defect H1 (§3) were fixed before any Program 2 reading; the tier restarted. The unit tier reads the weight, not the retained heap (gap named at the audit).
7. **Core question** — the startup check refuses exactly `0MiB` and the resolved value becomes the cache's maximum weight: the cached weight follows the knob (⌊C/w⌋ entries at four values, ratios 4/16/10) and never exceeds it, by evicting.

**Unit tier conclusion:** B2g rows 1 and 2 — **confirmed**.

**Cluster tier**

1. **Validity** — [observed: `*/summary.txt` READBACK lines] the knob read back 2/10/32 MiB; the cap was passed at every value (evicted 18,458–19,904); the B3h controls met their expectations (500/0 and 500/0); same heap flags, yaml differing only in the knob line (`yaml-overrides.txt`), same client and workload. Valid.
2. **Readings** — the whole-JVM live heap grows by 23.6–50.4 MB although the cache holds 2–32 MiB of weight; the knob-dependent part (D) and a part independent of the knob both appear.
3. **Matched rows** — B3g row 1, "plateau proportional to C, evictions > 0, warning logged" with amended B3f (i)–(vi) [observed: plateau constant over the last five samples at 96/482/1,542; ratios 16.062 and 5.021; evicted = 20,000 − count; instances − count = 31 at every value; 2 warnings each; D = 0.857 × 30 MiB]; **and** the added row "(i)–(vi) hold, and the whole-JVM live heap also grows with the 20,000 offered statements by an amount that does not depend on C" [observed: memtable partitions +20,001 and rows +20,001 in every main run regardless of C, +501 with 500 distinct statements; inferred: growth − 0.857 × weight = 21.76 · 21.75 · 21.66 MB at 2 · 10 · 32 MiB].
4. **Excluded rows** — "Prepared instance count ≈ 20,000 regardless of C": 127/513/1,573. "Plateau equal for both C": 96 vs 1,542. "0MiB starts": exited, no CQL listener. Added rows: (vi) holds (0.857 within 0.5–2), so "bounds the estimate, not the real heap" does not apply; evicted 19,904 ≠ 0 at 2 MiB; no control missed, no read-back mismatched.
5. **Observed vs. inferred** — [inferred: same offered n] D is the cache's retained heap because the 20,000 offered statements are the same in both runs, so heap that depends on n cancels; the auto run, not used to compute the 0.857, gives the same ratio (0.856) independently. [inferred: histogram class counts] the knob-independent ≈ 21.7 MB is the memtable of `system.prepared_statements` (one partition and row per distinct PREPARE, `SystemKeyspace.writePreparedStatement`, `QueryProcessor.java:831-833`; an eviction adds a deletion, not a removal): partitions +20,001 at every C and +501 in the control, where re-prepares write nothing.
6. **Deviations and gaps** — no heap dump: the cache's own retained size is read only as D (a difference between knob values). Flush of the system table (it would move the growth to disk) was not reached in a run this short. The B3h control's validity bound used the unit tier's w (21,812 B); the cluster's per-entry weight (≈ 21,760 B) is within 0.3 % of it.
7. **Core question** — usage of the cache follows the constraint: its entries plateau at ⌊C/w⌋ (1 : 5 : 16), the extra live heap per extra MiB of knob is 0.86 MiB, and the excess is evicted and reported. The knob does not bound all heap a flood of distinct PREPAREs uses: the persisted-statement memtable grows by ≈ 1.1 KB per distinct statement whatever the knob.

**Cluster tier conclusion:** B3g row 1 — **confirmed for the cache**; added bypass row — **bypass as recorded** (`system.prepared_statements` memtable).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` (written separately from the harness, re-reads the raw `p1-*.out`, `stage4.out`, `TEST-*.xml`, each lifetime's `system.log`, `samples.csv`, `histo-*.txt` and the control's files under the full log root): **73 checks, ALL HOLD**, exit 0 (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | knob per JVM and read-back per lifetime, one entry per prepare, N rule, junit counts, client prepared 20,000 with 0 errors per run, controls (8 unit, 4 cluster) re-read. |
| 2. Readings | yes | max weightedSize per JVM recomputed over all samples; live totals and `Prepared` lines read from the full histograms. |
| 3. Matched row | yes | B2f (i)–(iv) and B3f (i)–(vi) each tested against its frozen tolerance; D/30 MiB = 0.857 recomputed. |
| 4. Excluded rows | yes | every row of B2g/B3g (with the added rows) addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | the memtable attribution rests on the class counts (+20,001 / +501, re-read from `histo-1-end.txt`) and is labelled inferred; the verdict's "caps" for the cache does not depend on it. The knob-independent remainder (21.66–21.76 MB) is constant to 0.5 % across a 16× range of C. |
| 6. Deviations and gaps | yes | §3 defects; no heap dump; no flush reached. |
| 7. Core question — the steps follow the audited logic | yes | startup refusal → plateau ∝ C → evictions/warning → heap D ∝ C → controls, in B2e/B3e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-25). Every load-bearing figure (counts, evictions, read-backs, instance counts, the startup message) is observed and recomputed by the self-check; the one inferred statement (the memtable attribution) names the bypass and is supported by exact class counts; the same pattern was measured independently for the sibling `storePreparedStatement` case.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** (a) `prepared_statements_cache_size: 0MiB` prevents startup with the message at `DatabaseDescriptor.java:808`, any value ≥ 1 MiB is accepted; (b) with C MiB the summed weight of cached prepared statements never exceeds C MiB (beyond one entry of slack) and the retained heap of `QueryHandler$Prepared` instances scales with C, not with the number of distinct statements prepared. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** — B2g rows 1 and 2: `0MiB` refused with the traced message, `1MiB` → 1, auto → 10; weightedSize ≤ cap at every sample, count ⌊C/w⌋ = 48 · 192 · 769 · 480 (w = 21,812 B), evicted = N − count, both controls as frozen | caps | run 1 (after runbook fix 1) + self-check | 2026-10-25 |
| Cluster | **Confirmed** — B3g row 1 and the added bypass row: `0MiB` start aborted; plateau 96 · 482 · 1,542 (1 : 5.02 : 16.06), evicted = 20,000 − count, `Prepared` instances = count + 31, discard warning logged, D = 0.857 × 30 MiB, controls 500/0 and 500/0; the `system.prepared_statements` memtable grows by one partition per distinct PREPARE (+20,001 at every C, ≈ 21.7 MB) | caps only on some paths (bypass) | run 1 + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted). No section of the case amended after run 1 other than runbook fix 1 (B2a), which left B2f/B2g unchanged. Recommendations for stage 3, left unapplied: (1) A4 lists `system.prepared_statements` as an on-disk consumer only; until a flush it is an on-heap memtable, the largest heap consumer of a PREPARE flood, and the claim could name it; (2) Program 1's command needs the JDK 11 module flags as filed; (3) B2d's coarse heap reading has no prediction (recommendation 17).

**End of run:** `pgrep -f CassandraDaemon` and `pgrep -f ConfigProbe` empty, ports 7000/7199/9042/9091 free, `$W/node-psca` wiped, `test/conf/cassandra.yaml` restored and the probe test removed from `$W/cassandra-run10` (2026-10-25 09:28 EDT).
