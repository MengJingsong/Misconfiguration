# paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous — stage-4 results  <!-- file: results/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.md -->

> **Case:** [`paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous`](../../stage3-ai-deep-read/cases/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous.md)
>
> **Status:** verdict filed, 2026-10-25. **Unit: Confirmed — caps** (B2g row 1). **Cluster: Confirmed — caps** (B3g row 1: the retained `PaxosState$Snapshot` count is exactly ⌊C·2^20 / 4,352 B⌋ = 481 · 7,710 · 4,818 at 2 · 32 · 20 (auto) MiB, ratios 16.03 and 10.02; 200,000 LWTs per lifetime; the in-flight map `ACTIVE` stays at 0 in every histogram; the live heap grows by 1.114 / 1.099 × the weight difference, inside the band R_pred ± tol derived at the audit, R_pred = 1.094 / 1.095). Paxos variant `v1` (default at this tag). No run 2.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../../../stage4-runtime-verification/README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/`](../harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/).
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25, on the advisor's machine (`environment-advisor.md`).
> The verdict is against this file's own predictions and conclusions. `ConfigProbe.java` was copied unchanged from the
> `counter_cache_size-applySimpleConfig` harness, and `unit-run.sh`, `cluster-run.sh`, `cluster-chain.sh` and the JMX sampler follow that harness's patterns
> (copied, then adapted in the copy). That case's readings are not used as evidence here. The live-heap band was derived from
> the source of `PaxosState.RECENT` (a Caffeine map built in `PaxosState`, not a `CaffeineCache`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed in commit `0dcdfe0` (sha256 `d834cdab…96f2fe`, checked equal to the filed row before the audit). Frozen after the step-0 audit's seventeen amendments (2026-10-25, before any harness run or reading): sha256 `712c362b64199fb430a5ce85fa0c48fbb8f024e642b2bf7341a1d473c656ea1a`. Re-hashed after the runbook fix R1 (§3; claim, predictions and conclusions unchanged): **`b40c73a80ba50b43953dfc18144a4104580582f538819376d42283e28ade3feb`**. Both are new rows in `_INDEX.md` §4. Both tiers' run 1 ran at `b40c73a8…3feb`. Nothing committed (no commit was asked for). |
| **Harness** | [`../harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/`](../harness/paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/): `ConfigProbe.java` (copied unchanged from the counter-cache harness), `PaxosCacheCapProbeTest.java` (mechanism test, CQLTester), `unit-run.sh`; `PaxosSampler.java` (one-connection JMX sampler: heap, CASWrite and the table's `CasPrepare/Propose/CommitLatency` counts), `pcs-client.py` (bundled Python driver, LWT load, starts the under-load histograms), `cluster-run.sh` (one node lifetime), `cluster-chain.sh` (run 1 order and the shakedown). Instrument checks before run 1: the three Java files compiled against the run clone (`instrument-compile.log`, rc 0); cluster shakedown at 2 MiB with 20,000 + 300 LWTs (`run1/shakedown/`, a harness check, not a reading), which found harness defects H1 and H2 (§3); its first attempt was interrupted by an operator-side kill (§3) and the shakedown was repeated. **Bound check against the shakedown:** the final `Snapshot` count was 481 = ⌊2 MiB / 4,352⌋, the w_c B3f was derived with; the histogram's bytes / instances matched the derivation's shallow sizes for `Snapshot` 32, `PaxosState$Key` 24, `Ballot` 32 (one per entry: shared, as derived), `PartitionUpdate` 32, `BTreePartitionData` 32, `EncodingStats` 32, `MutableDeletionInfo` 24, `PSMW` 40, `BufferCell` 40, `BTreeRow` 40, `LivenessInfo` 24, `LongToken` 24, `HeapByteBuffer` 48. Two items differ: the retained commit is a plain `Commit$Committed`, 24 B, not `CommittedWithTTL`, 32 B (`UnsafeSnapshot(Commit)` rebuilds it, `PaxosState.java:276-279`), and the key is a `PreHashedDecoratedKey`, 40 B, not `BufferDecoratedKey`, 24 B. Net u = 440 B instead of 432 B, which moves R_pred by +0.002. That is inside the frozen allowance of 0.015 for the uncertain items, so the band was not changed. The self-check prints R with u = 440 as INFO. Self-check: [`run1/selfcheck.py`](paxos_cache_size-applySimpleConfig-paxosCacheSizeInMiB--autonomous/run1/selfcheck.py). |
| **Tiers and values** | Unit (B2): ConfigProbe with `-1MiB`, `0MiB`, unset (auto), `-Xms1G -Xmx1G`, each its own `java`; mechanism test with C ∈ {0MiB, 1MiB, 4MiB, auto (10)}, one `ant testsome` JVM per value (`-Xms1024m`), N = 20,000 LWTs of 1 KiB, controls (a), (b) in every JVM. Cluster (B3): one node, `MAX_HEAP_SIZE=2G`, `2MiB`, `32MiB`, auto (= 20 MiB). In each lifetime: a 300-LWT control, a 200,000-LWT main load (4 KiB values, 32 in flight) with three under-load histograms, then a flush and a final histogram. |
| **Audit bottom line** | **Ready after amendments**, 2026-10-25. |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2: on-heap bytes held by `PaxosState.RECENT`. The operand is the Caffeine weight Σ (`accepted.update` + `committed.update`).`unsharedHeapSize()` (`PaxosState.java:72-76`). |
| A. Core question | knob varied, ≥ 3 values incl. default | Partly → Met after amendment | Cluster had 2/32/auto. The unit test had only 1/4 MiB, so auto (10 MiB) and `0MiB` were added (amendment B2b). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly → Met after amendment | Unit: weight only (gap named, amendment B2d). Cluster: B3d had a `Snapshot` count and an old-gen difference with no derivation. Amendments B3d and B3f replace them with the live histogram `Total`, a real-heap relation (vii) whose band is derived from the source, and `ACTIVE` read separately (vi). |
| A. Core question | usage driven to the limit and past it | Met | Unit 20,000 × 1,280 B = 24 / 6.1 / 2.4 × the 1 / 4 / 10 MiB caps. Cluster 200,000 × 4,352 B = 870 MB, 415 × the 2 MiB cap. |
| B. Logic | each step says what it establishes | Partly | B2e/B3e list steps; the readings tables carry the meaning. Left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | "≈ 1.1–1.3 KiB", "≈ 4.2 KiB" and "± other noise" were replaced by w = 1,280 B and w_c = 4,352 B derived from the source, exact floors and tolerances (amendments B2c, B2f, B3c, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Partly → Met after amendment | B2g/B3g had three or four rows. Amendments B2g and B3g add rows for: ConfigProbe failure, `0MiB` rejected, LWT failure, limit not reached, weight vs heap mismatch, workload errors, control failure and ACTIVE growth. |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met (after amendment B2d/B3f) | Plateau ∝ C plus evictions (applied − own in the unit tier; 200,000 committed vs E retained in the cluster tier). |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Control (a) "N = plateau/2" would re-use written keys, which do not apply and reload from `system.paxos`, so it now uses fresh keys with exact expectations (B2h). The 300-key cluster control gets an exact delta in every lifetime (B3h). ACTIVE is separated from RECENT (B2d, B3f (vi)). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Added: the JVM split, the test-yaml line (none exists), auto heap (`-Xms`), the variant (v1) and its path, the stash sequence per LWT, and the read-back via `system_views.settings` (B2a, B2c, B3a, B3c). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The client, histogram points, JMX sampler, flush and compaction wait are now exact (B3c, B3d, B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly → Met after amendment | `/local/...` paths replaced by this host's clone, probe and node directories (B2a, B3a, B4). ConfigProbe needs the JDK 11 module flags. |
| D. Runnable | workload arithmetic reaches the limit | Met | See A. Disk ≈ 1.7 GB per lifetime (148 GiB free). The 200,000 LWTs took 44–45 s per lifetime. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | Checked in `~/cassandra-src` at `cassandra-5.0.9`: `DatabaseDescriptor.java:847-861, 1011-1012, 3942-3945`, `Config.java:485, 1051`, `conf/cassandra.yaml:825, 1602`, `PaxosState.java:70-76, 131-166, 211-243, 268-280, 343-400, 514-527, 672-806`, `Paxos.java:1210-1222`, `StorageProxy.java:326-328, 495-540, 695-760, 776-845`, `Commit.java:222-256`, `PartitionUpdate.java:74-78, 357-361, 855-880, 956-976`, `BTreePartitionData.java:37-52`, `BTreeRow.java:70-91, 532-541`, `BufferCell.java:35-43, 141-144`, `BufferClustering.java:44-49`, `LivenessInfo.java:287-290`, `DeletionTime.java:183-188`, `MutableDeletionInfo.java:76-79, 249-255`, `EncodingStats.java:74-76`, `BTree.java:112-115, 954-965`, `ObjectSizes.java:155-175`, `BytesType.java:47-51`, `CBUtil.java:443-450`, `TableMetrics.java:807-809`; `caffeine-3.1.8.jar` (`javap -p` of `BoundedLocalCache`: `maximum()`, `weightedSize()`). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and probe dir; ConfigProbe copied with the JDK 11 flags; one `ant testsome` per value; `-Xms1024m`; variant v1 and its path stated | Amendment 2026-10-25 | Paths did not exist; once-per-JVM initialisation; auto reads `totalMemory()`; the variant decides the traced path. |
| 2 | B2b: `0MiB` and auto added to the test | Amendment 2026-10-25 | Group A default. |
| 3 | B2c: exact statement, clear, calibration; w = 1,280 B derived | Amendment 2026-10-25 | "≈ 1.1–1.3 KiB". |
| 4 | B2d: own-table count by reflection, Caffeine `weightedSize()`/`maximum()` by reflection, ACTIVE apart, eviction inference | Amendment 2026-10-25 | `Key` fields are package-private; Caffeine stats not recorded. |
| 5 | B2e: order | Amendment 2026-10-25 | Open. |
| 6 | B2f: exact ConfigProbe lines and relations (i)–(v) | Amendment 2026-10-25 | "≈" without tolerance. |
| 7 | B2g: seven rows | Amendment 2026-10-25 | Group B. |
| 8 | B2h: controls (a) on fresh keys, (b), (c) exact | Amendment 2026-10-25 | Re-used keys would not apply. |
| 9 | B3a: this host; read-back by `system_views.settings` and committed heap | Amendment 2026-10-25 | No log line names the paxos cache size. |
| 10 | B3b: auto = 20 MiB at `-Xms2G` | Amendment 2026-10-25 | Exactness. |
| 11 | B3c: exact client; w_c = 4,352 B derived | Amendment 2026-10-25 | "≈ 4.2 KiB". |
| 12 | B3d: histogram points and classes, JMX sampler with the v1 path counters | Amendment 2026-10-25 | `jstat` cannot attach; v1 path evidence. |
| 13 | B3e: order, flush + compaction wait, shakedown with a bound check | Amendment 2026-10-25 | Heap memtables (`heap_buffers`). |
| 14 | B3f: relations (i)–(vii), (vi) ACTIVE, (vii) real-heap band from the source | Amendment 2026-10-25 | Group A. |
| 15 | B3g: seven rows | Amendment 2026-10-25 | Group B. |
| 16 | B3h: control exact per lifetime | Amendment 2026-10-25 | Exactness. |
| 17 | B4: this host's disk check and cleanup | Amendment 2026-10-25 | `/local` paths. |
| 18 | B2e/B3e steps do not say what each establishes | Left for stage 3 | Not needed for a valid run. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (unit attempt 0, 10:43–10:44 EDT, stopped at R1; unit 10:45–10:47; shakedown 10:47–10:58; cluster 11:00–11:07 EDT) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS, `/dev/disk3s1`), 149 GiB free at start, 148 GiB before each lifetime (re-checked; the harness requires ≥ 20 GiB); loopback 127.0.0.1–.3 present (re-checked with `ifconfig lo0`; one node used, 127.0.0.1); ports 7000/7199/9042/9091 free and no `CassandraDaemon` before the run (re-checked at the end, §8) |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). ConfigProbe: `java -Xms1G -Xmx1G` + the 17 JDK 11 module flags. Test: `ant testsome` forks, `-Xmx1024m` (build.xml) + `-Xms1024m` (`totalMemory` = `maxMemory` = 1,056,309,248 B). Node: G1, `-Xms2G -Xmx2G` (`MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`), committed heap 2,147,483,648 B in every lifetime |
| Ant | 1.10.18 |
| Python / driver | 3.8.11; bundled `cassandra-driver-internal-only-3.29.0.zip`, protocol 5 |
| Local `cassandra-src` clone commit | `$W/cassandra-run13` = `~/Library/Caches/stage4/cassandra-run13`, `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), built with `ant -Dlocal.repository=$W/m2 build-test` (`BUILD SUCCESSFUL`, 51 s); `caffeine-3.1.8.jar` |
| Paxos variant | `v1` (default, `Config.java:1051`; read back in the test and from `system_views.settings` in every lifetime); `paxos_state_purging` `legacy` |
| Case-file commit / harness commit | filed `0dcdfe0`; amendments, harness and results uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-pcs/{data,commitlog,hints,saved_caches,cdc_raw,logs}`, wiped before and after each lifetime (≈ 1.7 GB live data at the end of a lifetime); ConfigProbe data under `$W/probe-pcs/data` (removed) |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/paxos_cache_size-applySimpleConfig/`: `clone-build-run13.log`, `instrument-compile.log`, `unit-attempt0-R1/` (the stopped attempt), `unit-run.out`, `unit/` (`p1-*.out`, `ant-*.log`, `TEST-*.xml`, `stage4.out`, `summary.txt`, `commands.log`, yaml diffs), `shakedown/{sd-c2-attempt1-interrupted,sd-c2}/` (not evidence), `cluster/{c2,c32,cauto}/` (`system.log`, `node.out`, `samples.csv`, `histo-*.txt`, `heapinfo-*.txt`, `client-*.json`, `tablestats-final.txt`, `summary.txt`, `commands.log`), `cluster/chain.out`, `selfcheck.out` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| R1 | run 1, unit | B2c (first LWT) | In a plain `CQLTester` JVM the token ring is empty. The first `QueryProcessor.process(… IF NOT EXISTS, QUORUM)` failed in `StorageProxy.legacyCas` → `ReplicaPlans.forPaxos` → `TokenMetadata.firstTokenIndex` (AssertionFailedError) in all four JVMs, before any Paxos state existed (`run1/unit-attempt0-R1/failure-1MiB-excerpt.txt`). ConfigProbe had run as predicted. | The test calls `CQLTester.requireNetwork()` first, which runs `StorageService.instance.initServer()`. The LWT path is unchanged. Dated amendment in the case file's B2a (stage-4 runbook fix R1); new sha256 row. The unit tier restarted from its beginning (ConfigProbe included). | 2026-10-25, before any unit reading of `RECENT` | none (uncommitted) |

Harness defects (no case-file change, no effect on a reading):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit |
|---|---|---|---|---|---|---|
| H1 | shakedown | B3e (compaction wait) | 5.0.9's `nodetool compactionstats` prints `pending tasks                    0` without a colon, so the wait loop never matched and ran out its 300 s bound | match `^pending tasks:?[[:space:]]+0` | 2026-10-25, before run 1 | none |
| H2 | shakedown | B3d (histogram excerpt) | the excerpt did not list `Commit$Committed`, `PreHashedDecoratedKey`, `BTreeRow`, `BufferCell`, `LivenessInfo` (the full histograms had them) | added to the excerpt pattern | 2026-10-25, before run 1 | none |

**Operator interruption (shakedown attempt 1, not a defect of the case or the harness):** during attempt 1's compaction wait (H1), a separate foreground `sleep` command of this session hit the tool's 2-minute timeout at 10:55:42. The shakedown script received the same termination: its exit trap stopped and wiped the node before the final histogram. The attempt's files are kept in `shakedown/sd-c2-attempt1-interrupted/`. The shakedown was repeated in full (`shakedown/sd-c2/`). After that, no long foreground waits were used.

The repeated shakedown found no other defect. Its readings are not used, except for the bound check in §1.

## 4. Run 1

**Scope:** both tiers, every value in §1. **Command logs:** `run1/unit/commands.log`, `run1/cluster/<label>/commands.log`, `run1/chain.out`.

### 4.1 Readings

**Unit tier** (`run1/unit/summary.txt`, `stage4.out`, `p1-*.line`, `junit-*.txt`, `TEST-*.xml`; one JVM per row; all four `ant testsome` rc 0, `Tests run: 1, Failures: 0, Errors: 0`; every run line: `variant=v1 useV2=false purging=legacy`, `recentClass=…caffeine.cache.SSMW`)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| ConfigProbe `-1MiB` | `REJECT ConfigurationException: Invalid yaml: …/-1MiB.yaml / root: java.lang.IllegalArgumentException: Invalid data storage: -1MiB … only non-negative values are accepted`; the `paxos_cache_size option was set incorrectly` message (line 859) does not appear | `p1--1MiB.line` |
| ConfigProbe `0MiB` | `OK getPaxosCacheSizeInMiB=0` | `p1-0MiB.line` |
| ConfigProbe unset (`-Xms1G -Xmx1G`) | `OK getPaxosCacheSizeInMiB=10` | `p1-unset.line` |
| Calibration (C ≥ 1 MiB) | own = 100 after 100 LWTs; **w = 1,280 B** (ownWeight 128,000 / 100) = the derived value; Caffeine `weightedSize()` 128,000 | `stage4.out` |

| C | value / Caffeine `maximum()` (B) | max weigher sum over 21 readings | final own = `RECENT.size()` | ⌊cap/w⌋ | applied − own (evicted, inferred) | max ACTIVE | control (a) | control (b) |
|---|---|---|---|---|---|---|---|---|
| 0MiB | 0 / 0 | 0 | 0 | — | 20,000 (none kept) | 0 | M = 0 | 1 applied, 49 not; own 0 |
| 1MiB | 1 / 1,048,576 | 1,048,320 (≤ cap) | 819 | 819 | 19,181 | 0 | M = 409 → own 409, weight 523,520 = M·w | 1 / 49; own 1 (weight 1,344) |
| 4MiB | 4 / 4,194,304 | 4,193,280 (≤ cap) | 3,276 | 3,276 | 16,724 | 0 | M = 1,638 → own 1,638, weight 2,096,640 = M·w | 1 / 49; own 1 |
| auto | 10 / 10,485,760 (`totalMemory` 1,056,309,248) | 10,484,480 (≤ cap) | 8,191 | 8,192 | 11,809 | 0 | M = 4,095 → own 4,095, weight 5,241,600 = M·w | 1 / 49; own 1 |

All 20,000 LWTs were applied in every JVM. Caffeine's own `weightedSize()` equals the recomputed weigher sum at every reading. own(4MiB)/own(1MiB) = 4.0000; own(auto)/own(1MiB) = 10.0012.

**Cluster tier** (`run1/cluster/<label>/summary.txt`, `client-*.json`, `readback-settings.json`, `samples.csv`, `histo-excerpt-*.txt`, `tablestats-final.txt`; one node lifetime per value)

| Value | Observable | 2MiB (c2) | 32MiB (c32) | auto (cauto) |
|---|---|---|---|---|
| (i) | `system_views.settings` `paxos_cache_size` / `paxos_variant` / `paxos_state_purging` | `2MiB` / `v1` / `legacy` | `32MiB` / `v1` / `legacy` | null / `v1` / `legacy`; committed heap 2,147,483,648 → 20 |
| (ii) | control applied / errors; main applied / not / errors; main time | 300 / 0; 200,000 / 0 / 0; 44.8 s | 300 / 0; 200,000 / 0 / 0; 44.0 s | 300 / 0; 200,000 / 0 / 0; 43.7 s |
| (ii) | final CASWrite, CasPrepare, CasPropose, CasCommit counts | 200,300 each | 200,300 each | 200,300 each |
| (iii) | `Snapshot` baseline → after control; `PaxosState` after control | 0 → 300; 0 | 0 → 300; 0 | 0 → 300; 0 |
| (iv) | `Snapshot` under load at 25 / 50 / 75 % | 481 / 481 / 481 | 7,710 / 7,710 / 7,710 | 4,818 / 4,818 / 4,818 |
| (iv) | final `Snapshot` E (⌊C·2^20/4,352⌋) | **481** (481) | **7,710** (7,710) | **4,818** (4,818) |
| (vi) | `PaxosState` (ACTIVE) under load / final | 0 / 0 / 0; 0 | 0 / 0 / 0; 0 | 0 / 0 / 0; 0 |
| (vii) | live `Total`, baseline → final (after flush and compactions) | 45,732,424 → 54,953,848 | 45,836,744 → 89,987,072 | 45,738,664 → 75,705,456 |
| — | `ks.t` / `system.paxos` live bytes on disk, memtable data | 0.83 GB / 0.85 GB, 0 | 0.83 GB / 0.85 GB, 0 | similar, 0 |

Derived (recomputed by `selfcheck.py`): E(32)/E(2) = 16.029 (predicted 16.029); E(auto)/E(2) = 10.017 (predicted 10.017); w_c(measured) = C·2^20/E = 4,360.0 · 4,352.1 · 4,352.7 B, each consistent with w_c = 4,352 B under the floor. **D(32 − 2) = 35,033,224 B, S = 31,460,608 B, D/S = 1.114** (R_pred 1.094, tol ± 0.148). **D(auto − 2) = 20,751,608 B, S = 18,874,624 B, D/S = 1.099** (R_pred 1.095, tol ± 0.237). Per extra retained entry the live heap grows by 4,846 B (c32) and 4,785 B (cauto), against a weight of 4,352 B.

Histogram classes, c32 − c2 at the end (`selfcheck.out` INFO lines; ΔE = 7,229): exactly +7,229 instances each (one per retained entry) of `Snapshot` (32 B), `PaxosState$Key` (24 B), `Commit$Committed` (24 B), `PartitionUpdate` (32 B), `BTreePartitionData` (32 B), `EncodingStats` (32 B), `MutableDeletionInfo` (24 B), `BTreeRow` (40 B), `BufferCell` (40 B), `LivenessInfo` (24 B), `PreHashedDecoratedKey` (40 B) and `LongToken` (24 B). Also: `PSMW` +7,230 (40 B); `Ballot` +7,668 (one per entry plus a few in flight); `HeapByteBuffer` +14,458 (2 per entry: value and key, 48 B); `[B` +29.9 MB (2.02 per entry: 4,112 B value + 24 B key); `[Ljava.util.concurrent.ConcurrentHashMap$Node;` +61,440 B (predicted 4ΔL = 61,440); `[J` +57,456 B (predicted 8ΔT = 61,440). For cauto − c2 the same per-entry pattern holds, with table +28,672 (predicted 28,672).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity.** [observed: `stage4.out`, `p1-*.line`, `junit-*.txt`] The knob read back as set in every JVM (0/1/4, and auto 10 within the frozen 9–11). Caffeine's `maximum()` equals value × 2^20 exactly. The variant is v1 with `useV2` false. All LWTs applied. Calibration retained exactly one entry per applied key. The cap was passed 24×, 6.1× and 2.4×. Both controls met their frozen expectations in every JVM. Only the appended yaml line differed between JVMs (`p2-yaml-diff-*.txt`). Valid. (The first attempt stopped at R1 before any `RECENT` reading; §3.)
2. **Readings.** Nothing unusual. Control (b)'s single entry weighs 1,344 B = 1,280 + 64: the 49 non-applying LWTs propose an empty update, so the stashed state also holds an empty `Accepted`. No frozen relation depends on that weight (only own = 1).
3. **Matched row.** B2g row 1, "RECENT plateau ∝ C, weight ≤ C", with the amended B2f. [observed: (i) as in 1; (ii) w = 1,280 B; (iii) max weigher sum ≤ cap at every reading (1,048,320 · 4,193,280 · 10,484,480); (iv) own 819 · 3,276 · 8,191 in {⌊cap/w⌋ − 1, ⌊cap/w⌋}, ratios 4.000 and 10.001; (v) ACTIVE 0 at every reading; ConfigProbe as predicted; controls exact.]
4. **Excluded rows.** "RECENT.size() → N": own stays at ⌊cap/w⌋. "RECENT empty": 100 entries after calibration at every C ≥ 1 MiB. "ACTIVE grows with N": 0 at every reading. Added rows: `-1MiB` not accepted, and the rejection is the parser's message, not line 859's. `0MiB` was accepted and auto is in range. ConfigProbe did not fail for another reason. No LWT threw after R1. The plateau is proportional to C. w = 1,280 B, so the "w ≠ 1,280" row does not apply. No control missed.
5. **Observed vs. inferred.** [inferred: no Caffeine statistics] Evictions are applied − own. Each applied key's `commitDirect` stashes one entry (observed in calibration: 100 for 100), and nothing else removes entries after the clear.
6. **Deviations and gaps.** None in the procedure after R1. The unit tier reads the weight, not the retained heap (a gap named at the audit; the cluster tier covers the heap).
7. **Core question.** The startup value becomes `RECENT`'s maximum weight. The retained weight follows the knob (⌊cap/1,280⌋ entries, ratios 4 and 10) and never exceeds it, because entries are evicted. `0MiB` keeps nothing, and LWTs still succeed. A negative value never reaches the check at `DatabaseDescriptor.java:854`.

**Unit tier conclusion:** B2g row 1, **confirmed**.

**Cluster tier**

1. **Validity.** [observed: `readback-settings.json`, `client-*.json`, `samples.csv`, `yaml-overrides.txt`, `tablestats-final.txt`] The read-back gives 2MiB / 32MiB / null (auto 20 from the committed heap) and variant v1 in every lifetime. 200,300 LWTs were applied with 0 errors per lifetime. The table's `CasPrepare`, `CasPropose` and `CasCommit` counts are each 200,300, which shows that every LWT went through `legacyPrepare`, `legacyPropose` and `applyCommit`, the v1 path the file traces. The cap was passed at every value. The control met its frozen expectation in all three lifetimes. Heap flags and yaml were the same except for the knob line. Memtables were empty (flushed) at the final histogram. Valid.
2. **Readings.** The under-load histograms show `PaxosState` = 0. Each `jmap` safepoint caught no handler inside a `PaxosState` operation. That is consistent with the frozen bound (≤ 64) but is not a measure of the in-flight peak.
3. **Matched row.** B3g row 1, "Snapshot count ∝ C, heap difference ≈ C difference", which by amendment needs B3f (i)–(vii) and B3h. [observed: (i) exact; (ii) 200,000 applied, 0 errors, Cas* counts = applied; (iii) +300 exactly, ACTIVE 0; (iv) E = 481 · 7,710 · 4,818 = ⌊C·2^20/4,352⌋ exactly, under load equal to E; (v) ratios 16.029 and 10.017 equal the predicted values; (vi) ACTIVE 0 in every histogram; (vii) D/S = 1.114 and 1.099, inside 0.946–1.242 and 0.858–1.332.]
4. **Excluded rows.** "Snapshot count ≈ 200,000": E ≤ 7,710. "Snapshot count ≈ 0": E = ⌊C·2^20/w_c⌋. Added rows: the read-back and variant match; the workload was complete with Cas* = applied; no count above (iv)'s set at any histogram; E is within (iv)'s set, so the derivation row does not apply; "(i)–(vi) hold but (vii) fails" does not apply because (vii) holds; ACTIVE did not grow; no control missed.
5. **Observed vs. inferred.** [inferred: histogram class deltas] The heap outside the weight is attributed to the per-entry objects listed in B3f (vii), each found exactly once per retained entry in the class deltas. The observed per-entry growth (4,846 / 4,785 B) is 77 / 12 B above the derivation with u = 440 B (w_c − 40 + 440 + table and sketch ≈ 4,769 / 4,773 B). About 24 B of that is a third `Object[1]` per entry, found in the class deltas but not in the derivation; the rest is lifetime-to-lifetime noise in other `Object[]` arrays (c32 only). The verdict rests on (vii)'s observed ratio, not on this attribution.
6. **Deviations and gaps.** No heap dump (instance counts and class totals only). The live heap is compared between lifetimes (D), not against an absolute baseline, as frozen. The under-load histograms ran while the load continued, as frozen.
7. **Core question.** Usage follows the constraint. The retained Paxos states plateau at exactly C / 4,352 B (1 : 16.03 : 10.02 for 2 : 32 : 20 MiB) while 200,000 distinct partitions are written, so 199,819 / 192,590 / 195,482 of the 200,300 committed states are evicted. The real live heap follows the knob linearly at ≈ 1.1 × the weight. The audit derived that factor from the source before the run: the unweighed `Snapshot`, key, commit, partition-update shells and the Caffeine node per entry. The separate in-flight map `ACTIVE` is not capped by the knob, but it stays empty between operations and holds nothing at any histogram. This is the cap the file claims; `ACTIVE` is not a bypass of it at this workload.

**Cluster tier conclusion:** B3g row 1, **confirmed**.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`run1/selfcheck.py` was written separately from the harness. It re-reads the raw `p1-*.out`, `stage4.out` and `TEST-*.xml`, and for each lifetime `client-*.json`, `samples.csv`, `histo-0-baseline.txt`, `histo-1-control.txt`, `histo-load-*.txt`, `histo-2-end.txt` and `system.log` under the full log root. It recomputes R_pred with its own L(E)/T(E) functions. Result: **106 relation checks, 106 hold, 0 fail**, exit 0 (`run1/selfcheck.out`).

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Re-read: knob per JVM and read-back per lifetime, Caffeine `maximum()`, variant, junit counts, applied counts, Cas* counts, and both controls in every JVM and lifetime. |
| 2. Readings | yes | Max weigher sum over all unit readings; Caffeine `weightedSize()` equal to it at every reading; histogram counts from the full histograms; control (b)'s 1,344 B noted and not used by any relation. |
| 3. Matched row | yes | B2f (i)–(v) each against its frozen tolerance; B3f (i)–(vii) recomputed; D/S = 1.1136 and 1.0994 against R_pred 1.0940 ± 0.148 and 1.0948 ± 0.237. |
| 4. Excluded rows | yes | Every row of B2g/B3g, original and added, is addressed in §4.2 with a reading. |
| 5. Observed vs. inferred | yes | The unit eviction inference rests on the applied count (re-read) and the calibration's one entry per key. The heap attribution is labelled inferred and printed as INFO lines, not counted as relations. |
| 6. Deviations and gaps | yes | R1 restarted the unit tier at the new version (both TEST sets kept). H1 and H2 affected only the shakedown, and the self-check reads the full histograms. |
| 7. Core question — the steps follow the audited logic | yes | read-back → v1 path counts → control → plateau ∝ C → ACTIVE apart → live heap vs the derived relation, in B2e/B3e's order. |

### 5.2 Run 2?

**No** (decided 2026-10-25). Every load-bearing figure is observed and recomputed by the self-check. Both tiers' counts are exact floors (⌊cap/w⌋, with w measured equal to the derivation), the heap relation holds at two independent pairs, and the result neither refutes the case nor confirms a bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive.

**Claim tested (B1):** With `paxos_cache_size: C`, after LWTs on many more distinct partitions than fit, `PaxosState.RECENT`'s summed weight stays ≤ C MiB and its size plateaus at ≈ C / (per-entry update weight); the corresponding heap scales with C. "Confirmed" means this claim held.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed**, B2g row 1. `-1MiB` is rejected by the parser (it never reaches line 854); `0MiB` → 0 (nothing kept, LWTs still applied); auto → 10. The weigher sum is ≤ cap at every reading, own = ⌊cap/1,280 B⌋ = 819 · 3,276 · 8,191 at 1 · 4 · 10 MiB (ratios 4.000, 10.001), and 19,181 · 16,724 · 11,809 were evicted. ACTIVE was 0 throughout; controls exact. | caps | run 1 (after R1) + self-check | 2026-10-25 |
| Cluster | **Confirmed**, B3g row 1. Paxos v1. Read-back C; 200,000 LWTs per lifetime with 0 errors and CasPrepare = CasPropose = CasCommit = applied. `Snapshot` count E = ⌊C·2^20/4,352 B⌋ = 481 · 7,710 · 4,818 (1 : 16.03 : 10.02), the same under load; control +300 exactly; ACTIVE 0 in every histogram. Live(32) − live(2) = 1.114 × the weight difference (1.099 for auto − 2), inside R_pred ± tol (R_pred 1.094 / 1.095, from the unweighed per-entry shells + Caffeine node, table and sketch). | caps (retained Paxos states and their weight capped exactly at C; real heap bounded and proportional to C at ≈ 1.1 × C; the unbounded `ACTIVE` map held nothing between operations) | run 1 + self-check | 2026-10-25 |

**Feedback filed:** the case file's section D (uncommitted), plus the runbook fix R1 in B2a (dated). No section of the case was amended after run 1's readings. Recommendations for stage 3, not applied:
1. A2 could state that the real heap per entry is weight + ≈ 440 B (unweighed `Snapshot`, key, `Committed`, `PartitionUpdate` shell, partition data, stats, partition key, Caffeine node and map node), plus table and sketch.
2. A3 could note that the retained `committed` is a plain `Commit$Committed`: `UnsafeSnapshot(Commit)` drops the TTL wrapper.
3. A CQLTester probe that runs LWTs through `StorageProxy.cas` needs `requireNetwork()` (token ring).
4. B4 still names `/local` paths (superseded by the B4 amendment).

**End of run:** `pgrep -f CassandraDaemon` is empty and no ConfigProbe, client or sampler process is left; ports 7000/7199/9042/9091 are free. `$W/node-pcs` and `$W/probe-pcs` are removed. The probe test is removed from `$W/cassandra-run13`, and its `test/conf/cassandra.yaml` is restored (`git status` clean). No `build/` or log folder exists in the repository root. Checked 2026-10-25 after the self-check.
