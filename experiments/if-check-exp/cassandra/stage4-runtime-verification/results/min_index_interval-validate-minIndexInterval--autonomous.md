# min_index_interval-validate-minIndexInterval--autonomous — stage-4 results  <!-- file: results/min_index_interval-validate-minIndexInterval--autonomous.md -->

> **Case:** [`min_index_interval-validate-minIndexInterval--autonomous`](../../stage3-ai-deep-read/cases/min_index_interval-validate-minIndexInterval--autonomous.md)
>
> **Status:** verdict filed, 2026-10-26. **Unit: Confirmed — caps (m); M a floor. Cluster: Confirmed — caps (m); M a floor (does not cap).**
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/min_index_interval-validate-minIndexInterval--autonomous/`](../harness/min_index_interval-validate-minIndexInterval--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `3462f60e…2840` (schema batch, commit `a902cc2`). Frozen after the step-0 audit's sixteen amendments (2026-10-26): sha256 **`5446447ad9c9693edaa39d3d256347bddb801afd22c397c4c6b200c4edd6823e`**, at which both tiers' run 1 ran; a new row in `_INDEX.md` §4. Section D was filled after this hash. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/min_index_interval-validate-minIndexInterval--autonomous/`](../harness/min_index_interval-validate-minIndexInterval--autonomous/): `IndexIntervalCapTest.java` (B2c–B2e as amended), `unit-run.sh` (adapted from the bloom_filter_fp_chance validate harness); `make-node-conf.sh` (copied from that harness with the clone, node paths and cluster name changed), `MiiProbe.java` (JMX client, pattern of the index_summary_capacity case's `ISSampler.java`), `cluster-run.sh` (B3e as amended). Not committed. Instrument checks: (i) the test class compiled in the run clone (`BUILD SUCCESSFUL`, [`run1/unit/compile-summary.txt`](min_index_interval-validate-minIndexInterval--autonomous/run1/unit/compile-summary.txt)); `MiiProbe` compiled with `javac`; (ii) a unit shakedown (`MII_SHAKE=1`, N = 10,000) ran every step ([`shakedown/unit-shake-summary.txt`](min_index_interval-validate-minIndexInterval--autonomous/shakedown/unit-shake-summary.txt)); (iii) a cluster shakedown (n = 100,000 per keyspace, both lifetimes, phases 2a/2b and step 6) ran to the end and left nothing running ([`shakedown/cluster-shake-summary.txt`](min_index_interval-validate-minIndexInterval--autonomous/shakedown/cluster-shake-summary.txt)); (iv) `run1/selfcheck.py` was written before any run-1 reading and its parsers were exercised on both shakedowns. Shakedown readings are not judged. |
| **Tiers and values** | Unit (B2): m = 1, 16, 128, 512 (M 2048) over N = 1,000,000 8-byte keys; downsampling of the m = 128 summary to the floors of M = 2048 and 512; validation 0, −5, 128/127, 128/128; `calculateSamplingLevel` for both M. Cluster (B3): one node, 4 GiB heap, `big` format, compaction disabled by table option; five keyspaces `ii_1` (m 1), `ii_16` (16), `ii_128` (128), `ii_512` (512), all M 2048, and `ii_m512` (m 128, M 512), 4,000,000 partitions each; boundary ALTERs `min_index_interval = 0` and `max_index_interval = 64`; lifetime 2 with a 1-minute resize interval: phase 2a at the default pool (204 MiB), phase 2b at pool 0 MiB; step 6 (`ii_m512` M → 2048, then → 256). |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**What the source says, derived at the audit.**
- *The checks* (`TableParams.java:185-194`): m < 1 and M < m throw `ConfigurationException` via `fail` (`:206-209`). The CQL path validates a builder holding the defaults plus the given options (`TableAttributes.java:59-66`), so `ALTER … max_index_interval = 64` on `ii_128` is checked against the default m 128.
- *Summary size at write* (`IndexSummaryBuilder.java:100-131, 200-244, 246-252, 268-278`): one entry per m keys, `ceil(keys/m)` entries; counted off-heap bytes `4 × count + Σ (keyLen + 8)` (`IndexSummary.java:259-262`); the write path trims the builder memory before building (`BigTableWriter.java:320-321`).
- *Downsampling* (`IndexSummaryBuilder.java:299-380`, `Downsampling.java:41-148`): level clamp `[max(1, ceil(128·m/M)), 128]`; the removed entries follow the start-point pattern, giving exact counts (489 and 1,954 for the unit tier).
- *Redistribution with no reads* (`IndexSummaryRedistribution.java:159-268, 327-355`): idealSpace 0, target 1 entry, so every sstable is listed for its floor; **`distributeRemainingSpace` then hands back every listed sstable whose regained bytes still fit in the pool**. At the default pool (int(4 GiB × 0.05) = 204 MiB, `DatabaseDescriptor.java:867-869`) against ≈ 95 MB of full summaries, all are handed back and nothing is downsampled; only a pool below the full total lets the floors appear. This is why phase 2 was split (2a at the default pool as a control, 2b at 0 MiB).
- *Instruments*: the table gauge and `MemoryPoolSizeInMB` sum `getOffHeapSize()`; the `IndexIntervals` MBean map gives each sstable's effective interval `round(128/L × m)` (`IndexSummaryManager.java:165-173`); Summary.db = 24-B header + the counted bytes + first and last key with 4-B lengths (`IndexSummary.java:401-421`, `IndexSummaryComponent.java:118-128`) = gauge + 52 B per sstable for 10-byte stress keys (`SettingsCommandPreDefined.java:82,108`).

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: off-heap bytes of BIG index summaries; Summary.db on disk. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b/B3b: m = 1, 16, 128 (default), 512; M = 2048 (default), 512, and 256 in step 6. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: the summary's two `Memory` blocks (`alloc`) added; cluster: Summary.db bytes as the independent reading, RSS context, gap named (B2d, B3d amendments). |
| A. Core question | usage driven to the limit and past it | Met | m = 1 (densest allowed), m = 0 / −5 / M < m refused; cluster phase 2b drives the pool below the floor total. |
| B. Logic | each step says what it establishes | Partly → Met after amendment | Phase 2 at the default pool could not show the M floor (`distributeRemainingSpace`); split into 2a / 2b (B3a, B3e amendments). |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B2f/B3f used ≈; exact values and bands derived (B2f, B3f amendments). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Rows had meanings without verdicts; added real-resource, phase 2a/2b, step 6 and invalid rows (B2g, B3g amendments). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | Sizes ∝ 1/m plus refused DDL / validate; floors plus the per-sstable levels from `IndexIntervals` and the `force upsample` log line. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Compaction disabled by table option (survives the restart); phase 1 without redistribution read back; phase 2a as the pool control (B3h amendment). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | B3b keyspace `ii`/`t…` vs B3c `ii_X` inconsistency resolved (B3b amendment); output format (B2d). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | Commands, waits (`Completed resizing` counts), stop conditions (B2e, B3c, B3e amendments). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local` paths, `-R`, `du -cb`, `jmxtool` (B2a, B3a, B3d amendments). |
| D. Runnable | workload arithmetic reaches the limit | Met | 20 M writes at ≈ 73k/s, < 1 GB disk of 127 GiB free, 4 GiB heap of 32 GiB. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | All files in section C; every cited line matches. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone, runner, output from the test log | Amendment 2026-10-26 (uncommitted) | `/local`; output location open. |
| 2 | B2c: `prepareToCommit()` before `build()`; order | Amendment 2026-10-26 | Mirrors the write path; otherwise the summary keeps the untrimmed builder memory. |
| 3 | B2d: `MII` lines; `alloc` as the real resource | Amendment 2026-10-26 | Group A. |
| 4 | B2e: stop condition | Amendment 2026-10-26 | Open. |
| 5 | B2f: exact sizes, downsample counts, messages | Amendment 2026-10-26 | Derived. |
| 6 | B2g/B2h: verdicts, added rows, control evidence | Amendment 2026-10-26 | Group B. |
| 7 | B3a: this host; phase 2 split into 2a (default pool) and 2b (pool 0 via MBean) | Amendment 2026-10-26 | Derived from `distributeRemainingSpace`: at the default pool the floors cannot appear. |
| 8 | B3b: keyspace names | Amendment 2026-10-26 | B3b vs B3c inconsistency. |
| 9 | B3c: exact commands, compaction disabled by table option, `totalRows` check | Amendment 2026-10-26 | The restart re-enables compaction after `disableautocompaction`. |
| 10 | B3d: `MiiProbe` (with `IndexIntervals`), `stat -f %z`, sstablemetadata, gap | Amendment 2026-10-26 | Tools; group A. |
| 11 | B3e: procedure and waits | Amendment 2026-10-26 | Follows 7. |
| 12 | B3f: exact relations; bands ±1 % (P1), ±2 % (P2b, S6) | Amendment 2026-10-26 | Derived; ±2 % from the start-point remainder (≤ 0.61 % in 300 simulated splits). |
| 13 | B3g/B3h/B4: verdicts, added rows, control evidence, paths | Amendment 2026-10-26 | Group B. |
| 14 | A3 should say that with no reads the pool is not ignored: `distributeRemainingSpace` keeps every summary that fits, so the M floor appears only when the pool is short; and B1 (b)'s "they follow M, not `index_summary_capacity`" holds only below the full total | Left for stage 3 (section D) | Changes the claim's wording, not needed for the run (handled by 7). |
| 15 | The CQL validate checks M against the *default* m 128 when only M is given (`TableAttributes.java:59-66`), so `ALTER … max_index_interval = 64` on a table with m = 16 would be refused by the CQL validate even though 64 ≥ 16 — worth a test | Left for stage 3 | Not in B1. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (clone 20:53, build 20:53–20:54 (55 s); audit and freeze to 21:17; compile check 21:00:59; unit shakedown 21:01:20; cluster shakedown 21:02:44–21:16:26; unit run 1 21:17:48–21:18:06; cluster run 1 21:18:12–21:36:13) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 127 GiB free; loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used: one node); ports 7000, 7199, 9042 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork. Node: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (`-Xms4G -Xmx4G -XX:+UseG1GC`, read from `JVM Arguments`) |
| Ant | 1.10.18 |
| Python | 3.8.11 (cqlsh; self-check) |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run43` (fresh clone, `ant -Dlocal.repository=$W/m2 build-test`, 55 s); `W=~/Library/Caches/stage4`; `git status` clean after the runs |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-mii43` (data, commit log, hints), wiped before and after each cluster run |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/min_index_interval-validate-minIndexInterval/` — `clone.log`, `build-test-run43.log`, `unit-compile/`, `unit-shake/`, `unit-r1/` (ant log, JUnit XML, test log, `stdout.txt`, `summary.txt`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `node1/` and `node2/` logs, five `stress-*.txt`, `alter-*.txt`, `readback-*.txt`, `setcap.txt`, `compactionhistory-{1,2}.txt`, `redistribution-lines-2.txt`, `schema.txt`, `snaps/*.txt`; per record point `P1/`, `P1end/`, `P2a/`, `P2b/`, `S6a/`, `S6b/` × keyspace: `tablestats.txt`, `summary-files.txt`, `ls-l.txt`, `sstablemetadata.txt`, `rss.txt`) |

Machine facts relied on (from `environment-advisor.md` and the session brief): all files under `$W` (no `mkdir` in `$HOME`; cqlsh with `HOME=$W/home`); every `ant` call with `-Dlocal.repository=$W/m2`; commands touching `$W`, Java or the network run outside the tool sandbox; no `setsid` (node started as a tracked `nohup … -f &` process, pid from `$!`, stopped by drain and `kill <pid>`; the daemon name split in the scripts' patterns); BSD tools (`stat -f %z` instead of `du -cb`, `sed -i ''`); no jmxterm (a small JMX client, `MiiProbe`); `DatabaseDescriptor.daemonInitialization()` in the test's `@BeforeClass`; test stdout from `build/test/logs/**/TEST-<class>.log`, one line per `println`; `nodetool disableautocompaction` does not survive a restart, so the table option `'enabled':'false'` was used (evidence: no `ii_` line in either `compactionhistory`, constant sstable counts); no foreground sleep near the tool timeout (cluster run in the background, polled); shakedowns before run 1; bounds derived from source; `selfcheck.py` written before readings. The node's `system.log` timestamps are UTC (`YYYY-MM-DDTHH:MM:SS,mmm`), seen in the shakedown; the self-check parses them as UTC. No guardrail is on the path (schema DDL by a superuser under AllowAllAuthenticator; no guardrail reads `min_index_interval`/`max_index_interval` in 5.0.9's `TableAttributes`/`TableParams`), so the authenticator was left as shipped.

## 3. Runbook defects

None. Both tiers ran as amended at `5446447a…823e`.

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](min_index_interval-validate-minIndexInterval--autonomous/run1/unit/) (`commands.log`, `summary.txt`, `stdout.txt`, `junit-testsuite.txt`, `compile-summary.txt`); [`run1/cluster/`](min_index_interval-validate-minIndexInterval--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `yaml-tail-{1,2}.txt`, `yaml-is-{1,2}.txt`, `jvm-arguments.txt`, `schema.txt`, `alter-*.txt`, `readback-*.txt`, `setcap.txt`, `redistribution-lines-2.txt`, `stress-*-results.txt`, `compactionhistory-{1,2}-ii.txt`, `error-count-{1,2}.txt`, `snaps/{P1,P2a,P2b,S6a,S6b}.txt`; per record point and keyspace `tablestats-summary.txt`, `summary-files.txt`, `ls-l-summary.txt`, `sstablemetadata-excerpt.txt`, `rss.txt`).

### 4.1 Readings

**Unit tier** (JUnit 1 test, 0 failures, 0 errors; `MII done` present; no too-low-interval warning; one run; N = 1,000,000 keys of 8 B)

| Summary | entries | offHeap (B) | alloc (B) | level | interval | Predicted (B2f amendment) |
|---|---|---|---|---|---|---|
| m = 1 | 1,000,000 | 20,000,000 | 20,000,000 | 128 | 1 | 1,000,000 / 20,000,000 |
| m = 16 | 62,500 | 1,250,000 | 1,250,000 | 128 | 16 | 62,500 / 1,250,000 |
| m = 128 | 7,813 | 156,260 | 156,260 | 128 | 128 | 7,813 / 156,260 |
| m = 512 | 1,954 | 39,080 | 39,080 | 128 | 512 | 1,954 / 39,080 |
| m = 128 downsampled, M = 2048 (target 8) | 489 | 9,780 | 9,780 | 8 | 2,048 | 489 / 9,780 |
| m = 128 downsampled, M = 512 (target 32) | 1,954 | 39,080 | 39,080 | 32 | 512 | 1,954 / 39,080 |

| Test or assertion | Result | Evidence |
|---|---|---|
| validate m = 0, m = −5 | `ConfigurationException: min_index_interval must be greater than or equal to 1 (got 0)` / `(got -5)` | `run1/unit/stdout.txt` |
| validate 128/127 | `ConfigurationException: max_index_interval must be greater than or equal to min_index_interval (128) (got 127)` | `stdout.txt` |
| validate 128/128 | ok | `stdout.txt` |
| `calculateSamplingLevel(128, 7813, 1, 128, M)` | 8 (M 2048), 32 (M 512) | `stdout.txt` |

**Cluster tier** (one node; every stress run `Total partitions: 4,000,000`, `Total errors: 0`, 72–78k op/s; 6 sstables per keyspace, all `nb-*-big`, constant through every record point; `totalRows` sum 4,000,000 per keyspace at every point; no `ii_` line in either `compactionhistory`; 0 ERROR lines in both lifetimes; lifetime 1 `ResizeIntervalInMinutes` −1 and no `Redistributing` line; lifetime 2 pool 204 MB, interval 1 min)

| Point | Observable | ii_1 (m 1) | ii_16 (16) | ii_128 (128) | ii_512 (512) | ii_m512 (128, M 512) | Prediction / band (B3f amendment) |
|---|---|---|---|---|---|---|---|
| P1 | gauge (B) | **88,000,000** | **5,500,044** | **687,566** | **171,952** | **687,544** | 88,000,000 / 5,500,000 / 687,500 / 171,875 / 687,500 ± 1 %; each equal to Σ ceil(rows_i/m)·22 |
| P1 | interval of every sstable | 1 | 16 | 128 | 512 | 128 | = m (level 128) |
| P1 | Σ Summary.db (6 files) | 88,000,312 | 5,500,356 | 687,878 | 172,264 | 687,856 | gauge + 52 × 6 = + 312 |
| P1 | boundary ALTERs on ii_128 | `min_index_interval = 0`: cqlsh exit 2, `ConfigurationException: min_index_interval must be greater than or equal to 1 (got 0)`; `max_index_interval = 64`: exit 2, `… must be greater than or equal to min_index_interval (128) (got 64)`; read-back 128 / 2048 | | | | | refused with the messages, unchanged |
| P2a (pool 204 MiB, 2 redistributions, 120 s) | gauge / intervals | 88,000,000 / 1 | 5,500,044 / 16 | 687,566 / 128 | 171,952 / 512 | 687,544 / 128 | unchanged from P1; both runs `downsample: 0, force resample: 0, upsample: 0, force upsample: 0` |
| P2b (pool 0, 5 redistributions after the set) | interval of every sstable (level) | 128 (L 1) | 2,048 (L 1) | 2,048 (L 8) | 2,048 (L 32) | 512 (L 32) | floors max(1, ceil(128·m/M)) |
| P2b | gauge (B) | **687,544** | **43,076** | **43,076** | **43,076** | **171,952** | 687,500 / 42,969 / 42,969 / 42,969 / 171,875 ± 2 %; each equal to Σ down(ceil(rows_i/m), L)·22 |
| P2b | Σ Summary.db | 687,856 | 43,388 | 43,388 | 43,388 | 172,264 | gauge + 312 |
| P2b | total of the five | 988,724 B (pool 989,193 B with the other keyspaces) against a capacity of 0 | | | | | ≈ 1.03 MB > 0 |
| S6a (ii_m512 M → 2048) | ii_m512 gauge / interval | (others unchanged) | | | | **43,054** / 2,048 (L 8) | 42,969 ± 2 % (exact 43,054); log `downsample: 6` |
| S6b (ii_m512 M → 256) | ii_m512 gauge / interval | (others unchanged) | | | | **343,794** / 256 (L 64) | 343,750 ± 2 % (exact 343,794); log `force upsample: 6` |
| all | process RSS (context) | 4.52 GiB at P1, 4.42 at P2a, 4.04 at P2b, 3.75 at S6 | | | | | context only |

The first redistribution after the pool was set to 0 logged `downsample: 30` (the 30 ii sstables); every later one logged `downsample: 0 …` until the ALTERs (`run1/cluster/redistribution-lines-2.txt`).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — JUnit 1 test, 0 failures, 0 errors [observed: `run1/unit/junit-testsuite.txt`]; `MII done` and every line present; no `is too low for` warning in the test log [observed: raw test log via `selfcheck.out`]. Valid.
2. **Readings** — nothing unusual: every value equals the amended B2f value [observed: `stdout.txt`].
3. **Matched row** — B2g row 1 ("Entries = ceil(N/m) and bytes = 20 × entries") together with row 3 ("Downsampled level = ceil(128·m/M) and bytes scale with it") and all four validation results, as the B2g amendment requires for **Confirmed**: sizes 1,000,000 / 62,500 / 7,813 / 1,954 entries and 20 B each; downsampled levels 8 and 32 with 489 and 1,954 entries; `calculateSamplingLevel` 8 and 32; m = 0, −5 and 128/127 refused with the exact messages, 128/128 accepted [observed: `stdout.txt`].
4. **Excluded rows** — row 2 (bytes do not fall with m): 20,000,000 → 39,080 B [observed]. Row 4 (below the M floor): levels 8 and 32 = the floors [observed]. Row 5 (m = 0 or M < m passes): refused [observed]. Added (a) alloc ≠ offHeap: equal at all six points [observed]; (b) off the exact values: none [observed]; (c) `calculateSamplingLevel` ≠ 8 / 32: no [observed]; (d) 128/128 refused: accepted [observed]; (e) invalid: no [observed].
5. **Observed vs. inferred** — that `alloc` is the native memory the summary holds is inferred from the source (`Memory.size()` of the two blocks it owns, `IndexSummary.java:82-85, 249-257`); the conclusion rests on both counters agreeing exactly with the B2f values.
6. **Deviations and gaps** — `prepareToCommit()` and the `alloc` reading were added at the audit; no process-level native reading; one run.
7. **Core question** — `min_index_interval` sets the summary's memory exactly: one 20-B entry per m keys, so 1M keys cost 20 MB at m = 1 and 39 KB at m = 512, and m < 1 is refused, so no table can sample more densely than every key. `max_index_interval` sets how far a summary can be downsampled: the lowest level `ceil(128·m/M)` (8 at M = 2048, 32 at M = 512), a floor under the memory, not a ceiling over it.

**Conclusion (unit tier):** B2g rows 1 and 3 — **confirmed**; Effect `caps` (m), with M a floor.

**Cluster tier**

1. **Validity** — node up with the 4 GiB G1 heap in both lifetimes [observed: `summary.txt` `JVM` lines, `jvm-arguments.txt`]; five tables created with their (m, M), no compression, compaction `enabled: false` [observed: `schema.txt`]; `totalRows` 4,000,000 per keyspace at every point [observed: `*/sstablemetadata-excerpt.txt`]; stress 0 errors [observed: `stress-*-results.txt`]; no `ii_` compaction and 6 sstables per keyspace throughout [observed: `compactionhistory-*-ii.txt`, `tablestats-summary.txt`]; `big` format; 0 ERROR lines; the pool set to 0 and read back 0 [observed: `setcap.txt`]; ≥ 2 redistributions before each record point of lifetime 2 [observed: `redistribution-lines-2.txt`]; nothing left running. Valid.
2. **Readings** — nothing unusual. Every gauge equals the per-sstable source formula exactly (P1: Σ ceil(rows_i/m)·22; P2b: Σ down(…)·22; S6a: the 32 → 8 start points on the P2b summaries; S6b: a level-64 builder over rows_i) [observed vs recorded checks in `run1/selfcheck.out`]. RSS fell from 4.52 to 3.75 GiB across lifetime 2 while the summaries fell by ≈ 94 MB, but RSS mixes heap and other native memory and is context only.
3. **Matched rows** — (a) B3g row 1 ("Phase 1 bytes ∝ 1/m within a few %") as amended: all five P1 gauges within 1 % (largest +0.045 %), intervals = m, Σ Summary.db = gauge + 312 B each; and row 6's ALTERs refused with the B3f messages and read back 128 / 2048 [observed: files in 4.1]. (b) B3g row 3 ("Phase 2 bytes settle at the M floors, and step 6 moves them with M") as amended: P2a unchanged with `downsample: 0` in both runs; P2b every sstable at its floor and every gauge within 2 % (largest +0.25 %); S6a 43,054 B at level 8 and S6b 343,794 B at level 64 after `force upsample: 6`, the other four unchanged [observed].
4. **Excluded rows** — row 2 (equal across m): 88,000,000 → 171,952 B [observed]. Row 4 (below the floor): every interval equals the floor interval, none higher [observed: `snaps/P2b.txt`]. Row 5 (no redistribution): 2 runs in 2a, 5 after the set in 2b [observed]. Row 6 (an ALTER accepted): both exit 2 [observed]. Added (c) P2a not unchanged: unchanged [observed]; (d) P2b not at the floors: at the floors [observed]; (e) step 6 off: no [observed]; (f) Summary.db ≠ gauge + 52 × sstables: equal at all 30 keyspace-points [observed]; (g) invalid: no [observed].
5. **Observed vs. inferred** — that the gauge is the summaries' native memory is inferred from the source (the unit tier showed counted = allocated for flushed and downsampled summaries; the 6 upsampled ii_m512 summaries of S6b were rebuilt by `buildSummaryAtLevel`, which does not trim, so their allocation may exceed the counted 343,794 B — not measured). Summary.db, a real disk resource written from the same bytes, agrees to the derived 52 B per sstable at every point [observed]. Each sstable's level is read from `IndexIntervals` [observed], not inferred from bytes.
6. **Deviations and gaps** — phase 2 split into 2a/2b (audit, derived from `distributeRemainingSpace`), pool set through JMX rather than yaml, `MiiProbe` and `stat -f %z` instead of `jmxtool` and `du -cb`; no per-allocation native reading on the node. One run.
7. **Core question** — on a node, `min_index_interval` decides the summaries' off-heap memory and Summary.db bytes per key: 4M keys cost 88.0 / 5.50 / 0.688 / 0.172 MB at m = 1 / 16 / 128 / 512 (exactly 22 B per sampled key); m = 0 is refused at DDL time. `max_index_interval` does not cap usage: it is the floor the redistribution cannot go below. With no reads and a pool of 0 MiB the five tables settled at 0.99 MB, all at their floors, above the pool; moving M on one table moved its floor (43 KB at 2048, 344 KB at 256). At the default pool (204 MiB) nothing was downsampled at all.

**Conclusion (cluster tier):** (a) B3g row 1 — **confirmed**, Effect `caps`; (b) B3g row 3 — **confirmed**: M sets a floor (Effect for :188 `does not cap`).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](min_index_interval-validate-minIndexInterval--autonomous/run1/selfcheck.py), written before any run-1 reading and independent of the harness summaries (it re-reads the raw test log and JUnit XML; per record point the raw `tablestats.txt`, `sstablemetadata.txt`, `summary-files.txt` and the `ls -l` listing, whose Summary.db sizes it sums independently of the `stat` file; the raw JMX snapshots, stress outputs, ALTER outputs and exit codes, read-backs, `setcap.txt`, compaction histories and both `system.log` files; it re-implements the start-point pattern and the level-L builder from the source): **215 checks, 0 failed** (unit 30, cluster 185); unit "rows 1 + 3 + validation → Confirmed, caps", cluster "row 1 + row 6 → (a) Confirmed, caps | row 3 → (b) Confirmed, M floors (does not cap)" ([`run1/selfcheck.out`](min_index_interval-validate-minIndexInterval--autonomous/run1/selfcheck.out)). One change after it was written, after the shakedowns and before any run-1 reading: the `system.log` timestamp parser (the node writes UTC with a `T`, seen in the shakedown). No bound of the case file was changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts, `MII done`, no warning; `totalRows`, stress, compaction histories, sstable counts, ERROR counts, setcap read-back, redistribution counts from the raw files. |
| 2. Readings | yes | Exact per-sstable sums re-derived from raw `sstablemetadata` rows with the re-implemented start points / builder. |
| 3. Matched row | yes | Unit: six size points, six alloc = offHeap, four validations, two levels. Cluster: five P1 bands, intervals, disk; ALTERs; P2a; P2b floors and bands; S6a/S6b. |
| 4. Excluded rows | yes | Each excluded row's reading re-read. |
| 5. Observed vs. inferred | yes | The inference (gauge = native memory) is backed by Summary.db and the unit tier's alloc; the untrimmed upsample in S6b is named as unmeasured. |
| 6. Deviations and gaps | yes | Stated; none changes a reading's meaning. |
| 7. Core question | yes | m → `ceil(keys/m)` entries × (keyLen + 12) B, exact, and m < 1 refused; M → floor `ceil(128·m/M)`, reached only when the pool is short, moved by ALTER. |

### 5.2 Run 2?

**No** — decided 2026-10-26. Both tiers match the source formulas exactly, the per-sstable levels were observed directly, and the self-check holds in every part; the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

**Stage-3 estimate:** 185#1 positive; 188#1 undetermined.

**Claim tested:** "(a) For fixed N keys, BIG index summary off-heap bytes at full sampling equal `Σ ceil(keys_i/m) × (keyLen + 12)`. They fall as m rises, and m < 1 is refused. (b) Under redistribution with no reads, summary bytes settle at `≈ (ceil(128·m/M)/128) × full`. They follow M, not `index_summary_capacity`, and M < m is refused." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (rows 1 and 3: 1M keys → 20,000,000 / 1,250,000 / 156,260 / 39,080 B at m = 1 / 16 / 128 / 512, allocated = counted; downsampling stops at levels 8 and 32 (489 / 1,954 entries); m = 0, −5 and 128/127 refused, 128/128 accepted) | caps (m); M sets a floor, does not cap | run 1 + self-check | 2026-10-26 |
| Cluster | **Confirmed** (a: row 1, 4M keys → 88,000,000 / 5,500,044 / 687,566 / 171,952 B at m = 1 / 16 / 128 / 512, Summary.db + 52 B per sstable, both boundary ALTERs refused; b: row 3, pool 0 → every sstable at its floor, 0.99 MB in all above the pool; ALTER M moved ii_m512 to 43,054 B (2048) and 343,794 B (256); at the default 204 MiB pool nothing was downsampled) | caps (m); M sets a floor, does not cap | run 1 + self-check | 2026-10-26 |

**Feedback filed:** the case file's section D (uncommitted); the sixteen step-0 amendments are in the case file, dated, with the sha256 as a new row in `_INDEX.md` §4; `_INDEX.md` §1 Stage 4 column updated. The Estimate line is left as filed. No section was amended for a refutation (none occurred).
