# denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous — stage-4 results  <!-- file: results/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.md -->

> **Case:** [`denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous`](../../stage3-ai-deep-read/cases/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps** (run 1; closed, not re-run). **Cluster: Confirmed — caps (per table)**
> (cluster re-run "run 1b" of 2026-10-27 at the re-frozen version `e15e95b1…1e74`, after the user-authorised amendment of B3d, B3e,
> B3f (i) and (v), B3g and B3h; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/`](../harness/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/).
>
> **Run-1 status (as filed 2026-10-26):** verdict filed, 2026-10-26. **Unit: Confirmed — caps. Cluster: Not confirmed — caps (per table).**
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `04aa8df3…3dfc` (DD batch 4). Frozen after the step-0 audit's sixteen amendments (2026-10-26): sha256 **`0d0a30a16e6789b46ef3dafb6c1fcde827e559e243864c23ab5abce5cf062531`**. Runbook fix 1 (B2e, unit read-size guardrail; §9a unchanged) gave **`15dcf035e8c4a9a7a2c18612be4d4a9c175cbfdc41e0b5d6ed4ba7fd3adb153a`**, at which the unit tier's run 1 ran. Runbook fix 2 (B3d, heap instrument, found by the cluster shakedown before cluster run 1; §9a unchanged) gave **`ebd479808be0d53ea5a912d6bc9f98d2addcd919f616db2877c868c41b69d859`**, at which the cluster tier's run 1 ran. All three are new rows in `_INDEX-advisor.md` §2. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/`](../harness/denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/): `DenylistPerTableTest.java` (B2e's skeleton and imports plus the B2e amendment and runbook fix 1), `unit-run.sh`; `Jmx.java` (B3b verbatim), `make-node-conf.sh` (adapted from the repair setter case, one node), `cluster-run.sh`. Not committed. Instrument checks: (i) the audit probe [`audit/EntrySize.java`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/audit/EntrySize.java) built `PartitionDenylist$DenylistEntry` with the build's classes and measured it with `ObjectSizes.measureDeep` ([`audit/audit-entrysize.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/audit/audit-entrysize.txt)); (ii) the test class compiled in the run clone (`ant build-test`, `BUILD SUCCESSFUL`, [`audit/compile-summary.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/audit/compile-summary.txt)); (iii) a cluster shakedown (M = 2000, P = 100, 500, 2000, 100) ran every step — start, settings read-back, schema, empty load, `set 0`, CSV, COPY, flush, row count, four set/read-back/load/measure labels, stop, wipe ([`shakedown/summary.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/shakedown/summary.txt)); it exposed defect 2 ([`shakedown/heap-instruments.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/shakedown/heap-instruments.txt)); its readings are not judged. |
| **Tiers and values** | Unit (B2): M = 3000 keys of 4 KiB; setter values 0, −5 (rejection), P = 10, 100, 1000, 2500 (load path), 100 + one JMX add (refresh path), 50 (timer-refresh path, added at the audit); three runs. Cluster (B3): one node, 2 GiB heap, M = 20,000 keys of 8 KiB; 0 (rejection), P = 1000, 5000, 20000, 1000, each set over JMX and followed by a JMX `loadPartitionDenylist`. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-26. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of the run clone.

**What the source says, derived at the audit (the brief's questions).**
- *Defaults and flags.* `partition_denylist_enabled` defaults to **false** (`Config.java:759`); `denylist_writes_enabled`, `denylist_reads_enabled`, `denylist_range_reads_enabled` default to true (`:761-765`) and act only on queries to a denied table; `denylist_refresh` 600 s (`:767`); `denylist_max_keys_per_table` 1000 (`:774`), `denylist_max_keys_total` 10000 (`:780`), `denylist_consistency_level` QUORUM (`:786`). The cluster node sets `partition_denylist_enabled: true`, CL ONE, total 1,000,000 and reads all eight back from `system_views.settings`. The unit test sets enabled and CL ONE in code (as `PartitionDenylistTest.java:76-79` does).
- *JMX names.* MBean `org.apache.cassandra.db:type=StorageProxy` (`StorageProxy.java:189`). `DenylistMaxKeysPerTable` and `DenylistMaxKeysTotal` are **write-only attributes** (setters only, `StorageProxyMBean.java:82-83`); `loadPartitionDenylist` (`:73`), `denylistKey`, `removeDenylistKey` (`:80-81`), `isKeyDenylisted` (`:84`) are **operations**. No getter exists, so the stored value is read back from `system_views.settings`.
- *Paths that read at most the per-table limit.* Full load (`load()` → `getDenylistForAllTablesFromCQL`, `PartitionDenylist.java:222-238`, `:463-513`) reads each table with `limit = min(P, total − processed)` (`:497`); the timer refresh (`refreshAfterWrite(denylist_refresh)`, `:185`; `reload`, `:201-213`) and the refresh after a JMX add/remove (`refreshTableDenylist`, `:243-286`, `:515-528`) read with `limit = P` (`:388-391`). Every path sends `LIMIT limit+1` (`:404-409`) and stops copying at `limit` (`:437-447`). The setter (`DatabaseDescriptor.java:4813-4818`) rejects `value <= 0` at `:4815`; a stored value takes effect at the next load or refresh, not before (the cache is replaced or refreshed only then).
- *Keys beyond the limit.* Not loaded, so **not denied** (`isKeyPermitted` reads only `entry.keys`, `:318-321`); one ERROR per read, `Partition denylist for ks/t has exceeded the per-table allowance of (P). Remaining keys were ignored` (`:419-431`). The kept keys are the first P in clustering order (blob, unsigned bytes) of the table's one denylist partition (`SystemDistributedKeyspace.java:175-183`).
- *Heap per held key.* A fresh exact-size `HeapByteBuffer` per key (the local response is serialized and deserialized with `ByteBufferUtil.read`, `ReadResponse.java:182-203`, `ByteBufferUtil.java:444-452`) plus its token. With Murmur3 (the node) a 24 B `LongToken`; with ByteOrdered (**the unit yaml's partitioner**, `test/conf/cassandra.yaml:18`, not switched by `CQLTester.prepareServer()`) a `BytesToken` holding a **copy** of the key (`ByteOrderedPartitioner.java:66-69`, `:146-151`; `ByteBufferUtil.java:190-195`). Computed with the build's `measureDeep`: **8,294.6 B per 8 KiB key** (Murmur3) and **≈ 8,303 B per 4 KiB key** (ByteOrdered, 2.03 × the key bytes).
- *Instruments vs quantities.* Every quantity predicted is persistent (the entry is held until the next load), so a reading after GC sees it; the transient `LIMIT P+1` result (unpaged, `QueryOptions.forInternalCalls`) is neither predicted nor measured.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: keys held in the heap cache entry per table, a count with a derivable byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 10, 100, 1000 (default), 2500; B3b: 1000 (default), 5000, 20000, 1000. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | Unit: `measureDeep` of the entry; cluster: live heap after GC, `[B` bytes. |
| A. Core question | usage driven to the limit and past it | Met | M = 3000 > every unit P; cluster M = 20000 ≥ every P (P = M at 20000). |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g; left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | **B2f's deep band is wrong by the source** (≤ raw × 1.3 + 64 KiB, but the ByteOrdered token copies the key: deep ≈ 2.03 × raw); replaced by computed values ±2 %. ERROR count open (now exactly 7 with their allowances). Cluster bands were in prose; now stated, and checked to contain the derived values. |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: deep off the computed value, timer path not applied, ERROR count, getter after rejection, runs disagree, read failure (empty entry), row count, read-back, ingest drift, partial band failure, reversibility, node failure. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 now needs the exact counts/bytes, the rejections with the value unchanged, and the exact ERROR lines. |
| B. Logic | alternative explanations and their controls | Partly → Met after amendment | Read failure leaving an empty entry (`:450-454`) now a row; post-ingest drift control added (B3d). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Output location (test log, not XML), `printf` splitting, read-back, segment reading. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | The timer path, named in B1 and the Estimate, had no step (added, B2e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (B2a, B3a, B4 amendments). |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit 12 MB of rows in a 1 GiB JVM; cluster 330 MB CSV, 166 MB entry at P = 20000 in 2 GiB, 137 GiB free. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:4813-4818`; `StorageProxy.java:189`, `:3062-3113`, `:3130-3175`; `StorageProxyMBean.java:73-84`; `PartitionDenylist.java:92-111`, `:180-238`, `:243-286`, `:302-329`, `:385-528`; `Config.java:759-786`; `SystemDistributedKeyspace.java:175-183`; `QueryProcessor.java:377-392`. All match. Not caught at the audit: `test/conf/cassandra.yaml:63-67` (defect 1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and runner | Amendment 2026-10-26 (uncommitted) | CloudLab path. |
| 2 | B2c: ByteOrdered partitioner and its key copy; clustering order of kept keys; limit per path | Amendment 2026-10-26 | Decides B2f's bytes and which key is dropped. |
| 3 | B2d: read the test log; exact ERROR text; exact-size keys | Amendment 2026-10-26 | Known defect on this machine; source. |
| 4 | B2e: `println`, membership read from the entry, **timer-refresh step** | Amendment 2026-10-26 | Output splitting; B1 names refresh. |
| 5 | B2f: computed deep (83,200 · 830,800 · 8,304,368 · 20,756,560 ±2 %); 7 ERROR lines 10, 100, 1000, 2500, 100, 100, 50; `afterTimer` 50; per-run rule | Amendment 2026-10-26 | Filed band wrong by the source; counts open. |
| 6 | B2g, B2h: row 1's requirements; eight rows; controls' evidence | Amendment 2026-10-26 | Group B. |
| 7 | B3a: one node on this host; flags; G1 full GC | Amendment 2026-10-26 | CloudLab paths. |
| 8 | B3b: MBean, attribute vs operation; read-back from `system_views.settings` | Amendment 2026-10-26 | No JMX getter. |
| 9 | B3c: CSV path, row count 20000 | Amendment 2026-10-26 | P = 20000 depends on M. |
| 10 | B3d: readings; `Error reading` lines (empty entry); post-ingest control `used_i` | Amendment 2026-10-26 | Baseline taken before a 330 MB ingest. |
| 11 | B3e: run order, shakedown | Amendment 2026-10-26 | Open. |
| 12 | B3f: derived 8,294.6 B/key → 7.91 / 39.55 / 158.2 MiB; bands [2, 14] · [30, 50] · [120, 200] MiB; difference [24, 40] MiB; ERROR lines exact; drift ≤ 6 MiB | Amendment 2026-10-26 | Bands derived; disallow evidence and drift unstated. |
| 13 | B3g, B3h, B4: row 1's requirements; eight rows; controls; host paths | Amendment 2026-10-26 | Group B. |
| 14 | A cluster test of the timer-refresh and add/remove paths | Left for stage 3 | Unit tier covers them. |
| 15 | Report the transient `LIMIT P+1` result (unpaged; serialized and deserialized copies) as heap the cap bounds only indirectly | Left for stage 3 (section D) | Not in B1. |
| 16 | Note in A2 that per-key heap depends on the partitioner (ByteOrdered doubles it) | Left for stage 3 (section D) | Scope. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-26 EDT (audit 00:05–00:16; unit attempt 0 00:17–00:18; unit run 1 00:20–00:21; shakedown 00:22–00:23; cluster run 1 00:25–00:27) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 137 GiB free at start (136 GiB at the cluster runs); loopback 127.0.0.1, .2, .3 on `lo0` (only .1 used); ports 7000, 7199, 7200, 9042, 9091 free; no Cassandra daemon before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork (1 GiB). Node: `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G`, `-XX:+UseG1GC` in `JVM Arguments`), shipped `jvm11-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): `$W/cassandra-run25` (`ant -Dlocal.repository=$W/m2 build-test`, 52 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-dlmk` (data, commit log, the 328 MB CSV), wiped before and after; JMX 7199 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/` — `clone.log`, `build-test-run25.log`, `unit-compile/`, `unit-attempt0-r{1,2,3}/`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log, `stdout.txt`, `error-lines.txt`), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `settings.txt`, `rows.txt`, `copy.log`, `set0*.txt`, `node/` node logs, per label `heap_info.txt`, `histogram.txt`, `set.txt`, `readback.txt`, `load.txt`, `system-segment.log`, `error-exceeded.txt`); audit probe `~/Library/Caches/stage4/audit-run25/` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | 1 (unit, attempt 0) | B2e/B2c, the reads of `system_distributed.partition_denylist` | All three runs errored: `ReadSizeAbortException: … has exceeded the size failure threshold of 4,194,304 bytes` ([`run1/unit/attempt0/r1/error.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1/unit/attempt0/r1/error.txt)). `test/conf/cassandra.yaml:63-67` enables read thresholds with a 4096KiB coordinator fail threshold; a read of > ≈ 1000 keys of 4 KiB aborts (in the loads it would be caught at `PartitionDenylist.java:450-454` and leave an **empty** entry). The node default is off (`Config.java:526`). | `DatabaseDescriptor.setReadThresholdsEnabled(false)` in the test's `init()`; the harness counts only `has exceeded the <type> allowance` lines (the guardrail's message also says "has exceeded the"). B2f–B2h unchanged; the unit tier restarted (r1–r3 below). | 2026-10-26 | sha256 `15dcf035…153a` |
| 2 | shakedown before cluster run 1 | B3d, "`GC.heap_info` and record the used heap" | `used` after two `GC.run` counts the young regions (16 MiB each at 2 GiB) the node allocates afterwards: in the shakedown it moved by up to ≈ 17 MB with no change in the cache (`2 young (32768K)`), against bands of ±6 MiB ([`shakedown/heap-instruments.txt`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/shakedown/heap-instruments.txt)). | "Used heap after GC" read as the `Total` bytes of `GC.class_histogram` (it forces a full GC and counts only live objects); `heap_info` still recorded. Predicted quantity, baseline, control, values and bands unchanged. The cluster run 1 had not started. | 2026-10-26 | sha256 `ebd47980…d859` |

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-27 by the cluster re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3d baseline / B3f (i), (v) | The frozen baseline used₀ was taken after the empty load and before the 330 MB ingest. The ingest left 216 MiB live, so the drift control (v) and the four absolute Δ bands of (i) failed, while every count, read-back, ERROR line, difference and reversal held. The tier was Not confirmed (§4.2). | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** five dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)`. B3d: the baseline used_b is taken after the ingest, at a null label (set 1000, read-back, no load; histogram Total after a forced full GC). That the cache is empty there follows from `PartitionDenylist.java:222-236`, `:312`, `:473-475`. B3e: the null label, fresh clone, shakedown first. B3f (i′): Δ_P = used_P − used_b. The centres are entry(P) = 8,288·P + 4·T(P) + 176 B, from the entry's structures (JDK 11 `Buffer`/`ByteBuffer` and Guava 32.0.1 `RegularImmutableSet`/`RegularImmutableSortedSet`/`chooseTableSize` bytecode). The widths are the filed tolerance. B3f (v′): \|used_b − used_b1\| ≤ 6 MiB, replacing the pre-ingest drift relation, which is now recorded. B3g: row 1 read with (i′) and (v′), with three baseline rows. B3h: the baseline control. New sha256 `e15e95b1…1e74` as a new row in `_INDEX-advisor.md` §2. The whole cluster tier was re-run from its beginning in a fresh clone (§7). B1, B3f (ii)–(iv), (vi) and the unit tier are unchanged. | user, 2026-10-27 | sha256 `e15e95b1…1e74` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a/B3e paths | `cluster-run.sh` and `make-node-conf.sh` were fixed to run 1's clone (`cassandra-run25`) and node root (`$W/node-dlmk`). | Both read `DLMK_C` and `DLMK_NODE`; the defaults reproduce run 1. | AI, 2026-10-27 | n/a (harness) |
| H2 | cluster re-run | B3d, B3e (amended) | Run 1's harness had no null label. | With `DLMK_B2=1`, `cluster-run.sh` follows the post-ingest `measure ingest` with label `B2`: `Jmx set DenylistMaxKeysPerTable 1000`, read-back, `measure B2`. With it unset, the script behaves as in run 1. The start line records the clone, the node and the harness sha256. sha256 prefixes: `cluster-run.sh` `093c904f` (run 1) → `df51aea4`; `make-node-conf.sh` `d91803e6` → `af27ad36`; `Jmx.java` `6aff0f4b` (unchanged). | AI, 2026-10-27 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's relations and the closed unit tier. | `run1b-cluster/selfcheck.py` takes the cluster part of `run1/selfcheck.py`. Under `--relations run1` it is unchanged: same check names and notes, and its output on run 1's raw files is identical. Under `--relations amended` it checks (i′) and (v′). `--M`/`--P` serve the shakedown, and `--b-label` substitutes a baseline label, for information only. It exits non-zero on any failed check. `run1/selfcheck.py` is unchanged. | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1/unit/) (`r1`–`r3`: `commands.log`, `summary.txt`, `stdout.txt`, `error-lines.txt`, `junit-testsuite.txt`; `attempt0/`); [`run1/cluster/`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `settings.txt`, `rows.txt`, `copy-tail.txt`, `set0*.txt`, `system-log-denylist-lines.txt`; per label `heap_info.txt`, `histogram-excerpt.txt`, `set.txt`, `readback.txt`, `load.txt`, `error-exceeded.txt`).

### 4.1 Readings

**Unit tier** (ByteOrdered partitioner, `rows=3000`, `getter0=1000`; JUnit 1 test, 0 failures, 0 errors in each run)

| Test or assertion | r1 | r2 | r3 | Predicted | Evidence |
|---|---|---|---|---|---|
| set 0 / set −5 | `REJECTED 0 getter=1000`, `REJECTED -5 getter=1000` (`denylist_max_keys_per_table must be a positive integer.`) | same | same | rejected, getter 1000 | `run1/unit/r*/stdout.txt` |
| keys at P = 10 · 100 · 1000 · 2500 (getter = P) | 10 · 100 · 1000 · 2500 | same | same | min(P, 3000) | `stdout.txt` |
| rawBytes | 40,960 · 409,600 · 4,096,000 · 10,240,000 | same | same | keys × 4096 | `stdout.txt` |
| deep | **83,200 · 830,800 · 8,304,368 · 20,756,560** | same | same | the same values ±2 % | `stdout.txt` |
| deep(2500)/deep(1000) | 2.4995 | same | same | 2.5 ± 0.3 | computed |
| refresh after a JMX add (P = 100) | `beforeAdd keys=100`; `afterAdd keys=100 denylistKeyReturned=true addedKeyInEntry=false rows=3001` | same | same | 100, true, 3001; `addedKeyInEntry` recorded | `stdout.txt` |
| timer refresh (P = 50, no load) | `keysBeforeWait=100`; `timer get returned keys=100`; `afterTimer keys=50 waitedMs=101` | 50 (111 ms) | 50 (101 ms) | 50 | `stdout.txt` |
| ERROR lines `has exceeded the per-table allowance of (…)` | 7: 10, 100, 1000, 2500, 100, 100, 50 | same | same | exactly these 7 | `error-lines.txt` |

**Cluster tier** (one node, Murmur3; settings read back: `partition_denylist_enabled true`, `denylist_consistency_level ONE`, `denylist_max_keys_total 1000000`, reads/writes/range reads `true`, `denylist_refresh 600s`; COPY `20000 rows imported … 2.552 seconds (0 skipped)`; `count` 20000)

| Label | Set / read-back | `Loaded … in` | ERROR allowance lines | live heap (histogram Total) | Δ vs used₀ | Δ vs used_i | `[B` bytes | Evidence |
|---|---|---|---|---|---|---|---|---|
| base (empty load) | — | 1 ms | none | 49,242,552 | — | — | 15,765,944 | `cluster/base/` |
| set 0 | `REJECTED 0 javax.management.RuntimeMBeanException: java.lang.IllegalArgumentException: denylist_max_keys_per_table must be a positive integer.`; read-back 1000 | — | — | — | — | — | — | `set0.txt`, `set0-readback.txt` |
| ingest (after COPY + flush, no load) | — | — | — | 275,852,240 | **216.11 MiB** (drift) | — | 233,969,624 | `cluster/ingest/` |
| P = 1000 | `OK 1000` / 1000 | 55 ms | `(1000)` | 284,156,440 | 224.03 MiB | **7.92 MiB** (8,304.2 B/key) | 242,179,640 | `cluster/L1-P1000/` |
| P = 5000 | `OK 5000` / 5000 | 160 ms | `(5000)` | 317,347,808 | 255.69 MiB | **39.57 MiB** (8,299.1 B/key) | 275,014,304 | `cluster/L2-P5000/` |
| P = 20000 | `OK 20000` / 20000 | 631 ms | none | 441,777,784 | 374.35 MiB | **158.24 MiB** (8,296.3 B/key) | 398,137,288 | `cluster/L3-P20000/` |
| P = 1000 (again) | `OK 1000` / 1000 | 32 ms | `(1000)` | 284,197,120 | 224.07 MiB | **7.96 MiB** (8,344.9 B/key) | 242,186,648 | `cluster/L4-P1000/` |

Derived at the audit: 7.91 · 39.55 · 158.2 MiB (8,294.6 B/key). `[B` minus the post-ingest `[B`: 8,210.0 · 8,208.9 · 8,208.4 · 8,217.0 B per key
(expected 8,208). Δ_5000 − Δ_1000 = 31.65 MiB; last P = 1000 − first = 40,680 B. No `Error reading` line; six `Loaded` lines (startup,
base, four loads). At P = 20000 the histogram holds 20,137 `Murmur3Partitioner$LongToken` and 20,000 more `HeapByteBuffer` than after the
ingest. The ingest drift: after both flushes of `partition_denylist` completed (`Completed flushing … nb-1` 127.8 MiB, `nb-2` 28.6 MiB),
the heap still held 20,009 `BTreeRow` and ≈ 218 MB more `[B` in only ≈ 1,215 more arrays (slab-sized), unchanged through every later
reading. `heap_info` `used` agreed with the histogram Total within 1 KiB at every label after the ingest (base: 66.0 MB vs 49.2 MB).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — three runs, each 1 test, 0 failures, 0 errors [observed: `run1/unit/r*/junit-testsuite.txt`]; `rows=3000` before the sweep, total cap 1,000,000 (every ERROR line says `per-table`) [observed: `stdout.txt`, `error-lines.txt`]. Valid.
2. **Readings** — nothing unusual; the three runs are identical except the timer wait (101–111 ms) [observed].
3. **Matched row** — B2g row 1, "keys = min(P, 3000) and bytes scale with P — claim confirmed", with the amendment's requirements (i)–(vi): deep exactly the computed values (0.0 % off); ratio 2.4995; getter = P; 0 and −5 rejected with getter 1000; exactly 7 ERROR lines with allowances 10, 100, 1000, 2500, 100, 100, 50; `afterAdd keys=100`, `true`, `rows=3001`; `afterTimer keys=50`; in all three runs [observed: `stdout.txt`, `error-lines.txt`].
4. **Excluded rows** — "keys = 3000 for every P": keys = P [observed]. "`afterAdd` > 100": 100 [observed]. "deep ≫ raw × 1.3" and the added "deep ≥ 1.3 × computed" / "deep outside ±2 %": deep equal to the computed value [observed]. "0 or −5 accepted": rejected [observed]. Added rows: timer ≠ 50 — 50; ERROR count ≠ 7 — 7; getter changed — 1000; runs disagree — identical; compile/test failure — none after fix 1 [observed]. `addedKeyInEntry=false` (recorded): the added `0xff…ff` key is beyond the cap and not denied, as derived [observed].
5. **Observed vs. inferred** — that the deep value is twice the key bytes because of the ByteOrdered token copy is inferred from the source and the audit probe; it is not needed for the match (deep equals the value computed from that structure).
6. **Deviations and gaps** — the timer-refresh step, `println` output and membership read were added at the audit; read thresholds were disabled (defect 1). Nothing skipped.
7. **Core question** — on all three paths (full load, refresh after a JMX add, timed refresh) the entry holds exactly min(P, M) keys right after the next read, and its deep size follows P exactly (8,320 → 8,303 B per key, ×2.4995 from 1000 to 2500); 0 and −5 are refused and leave 1000; keys beyond P (including a freshly added one) are dropped from the cache with one ERROR per read.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — node up with the 2 GiB G1 heap [observed: `summary.txt` `JVM`]; settings read back [observed: `settings.txt`]; 20,000 rows [observed: `rows.txt`, `copy-tail.txt`]; each set read back equal to P [observed: `*/readback.txt`]; no read error, six `Loaded` lines [observed: `system-log-denylist-lines.txt`]. The run is valid; the drift control is a §9a condition, not a validity condition (B3g).
2. **Readings** — the post-ingest control moved by 216.11 MiB [observed: `base/` and `ingest/` histograms]; it stayed constant afterwards (the `BTreeRow` count is 20,009 at every later label) [observed: `*/histogram-excerpt.txt`].
3. **Matched row** — not row 1. Row 1 requires (i)–(v) of the B3f amendment; (ii)–(iv) hold exactly [observed: read-backs, `set 0` rejected with read-back 1000, one `per-table allowance of (P)` line at 1000, 5000, 1000 and none at 20000 or the empty load, no `Error reading`], Δ_5000 − Δ_1000 = 31.65 MiB and the reversal (40,680 B) hold, but **(v) fails** (drift 216.11 MiB > 6 MiB) and so do the absolute bands of (i) (Δ vs used₀ = 224.03 / 255.69 / 374.35 / 224.07 MiB) [observed]. The readings match the added B3g row **"abs(used_i − used₀) > 6 MiB — the baseline moved with the ingest; absolute Δ not interpretable — Not confirmed (Δ against used_i and the differences reported)"**. Against used_i, Δ = 7.92 / 39.57 / 158.24 / 7.96 MiB, each inside its frozen band and within 0.7 % of the derived value [observed; computed by `run1/selfcheck.py`].
4. **Excluded rows** — "Δ ≈ 160 MiB for every P": Δ (vs used_i) 7.92 → 158.24 → 7.96 MiB [observed]. "Δ grows by ≫ 8 KiB/key": 8,296–8,345 B/key [observed]. "0 accepted": rejected [observed]. Added rows: read error — none; rows ≠ 20000 — 20000; read-back ≠ P — none; ERROR lines off — exact; not reversible — 40,680 B; node failure — none [observed]. "Δ inside its band for some P and not others": against used₀ all four are outside, so this is the drift row, not a partial failure [observed].
5. **Observed vs. inferred** — that the drift is the flushed `heap_buffers` memtable of `partition_denylist` still referenced (20,009 `BTreeRow`, slab-sized byte arrays) is inferred from the histogram classes; it does not change the matched row.
6. **Deviations and gaps** — the heap instrument is the histogram Total (defect 2, before the run); the timer and add/remove paths are not run on the node (unit tier only). Murmur3 here, ByteOrdered in the unit tier, so per-key costs differ by design.
7. **Core question** — on a node, each JMX set followed by a load leaves exactly min(P, M) keys on the heap: the live heap above the post-ingest level is 8.30 / 41.50 / 165.93 / 8.34 MB for P = 1000 / 5000 / 20000 / 1000 (8.3 KB per 8 KiB key, `[B` 8,208 B per key), it shrinks back when P is lowered, 0 is refused, and the ERROR line names the allowance used. The frozen baseline (before the ingest) cannot show this because the ingest left 216 MiB on the heap, so the cluster tier stays Not confirmed by its own table.

**Conclusion (cluster tier):** B3g added row "baseline moved with the ingest" — **not confirmed** (every count, read-back, ERROR line, difference and reversal as predicted; Δ against the post-ingest control inside every band).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1/selfcheck.py), written before any
run-1 reading and independent of the harness (it re-reads the JUnit XML and the raw test logs; the node's raw `system.log`, splitting it at
each `Loaded partition denylist cache` line to assign ERROR lines to loads; the raw `heap_info` and histogram files; the raw Jmx and cqlsh
outputs): **76 checks, 5 failed** — exactly the drift control and the four absolute Δ bands against used₀, matching §4.2
([`run1/selfcheck.out`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1/selfcheck.out)). Changes after it was
written: (a) before cluster run 1, to read the instrument named by runbook fix 2 (histogram Total; `heap_info` still printed); (b) after
cluster run 1, the parser of `rows.txt` skips cqlsh's `count` header (its first pass read the header as the value and failed that check),
and INFO lines print Δ against used_i (reporting only). No check or bound was changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | JUnit counts; settings, row count, read-backs and `Loaded` lines from the raw files. |
| 2. Readings | yes | Drift 216.11 MiB re-derived from the raw histograms; `BTreeRow` 20,009 at every later label (`histogram-excerpt.txt`). |
| 3. Matched row | yes | Unit: all row-1 checks pass in r1–r3 (52 checks). Cluster: every count/read-back/ERROR/difference/reversal check passes; only the drift and the four absolute bands fail → the added drift row, Not confirmed. |
| 4. Excluded rows | yes | Deep equals the computed value; ERROR allowances per load from the raw `system.log`. |
| 5. Observed vs. inferred | yes | The memtable explanation of the drift is not used for the row. |
| 6. Deviations and gaps | yes | Stated. |
| 7. Core question | yes | Setter → limit of the next read → keys held (exact, both tiers) → heap (exact deep size; live heap above the post-ingest level 8.3 KB/key). |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier rests on exact readings in three runs. The cluster tier's failed parts are one cause (a baseline
taken before a 330 MB ingest that left 216 MiB live), observed in the raw histograms; a second run of the same frozen runbook keeps the same
baseline and cannot change the matched row. A re-run with the baseline after the ingest would need a re-frozen B3f (user authorisation, as in
the earlier re-runs on this branch).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3d, B3e, B3f (i)/(v), B3g, B3h amendment — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The unit tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed only through the heap baseline. used₀ was taken after the empty load and before the 330 MB ingest, and the ingest left 216 MiB live. So the drift control B3f (v) and the four absolute bands of (i) failed, while every count, read-back, ERROR line, the difference Δ_5000 − Δ_1000 and the reversal held (§4.1–§4.2). The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of the whole cluster tier on 2026-10-27. |
| **Amendment** | Five dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user) — B3d / B3e / B3f (i) and (v) / B3g / B3h`, each next to the text it changes. Each says plainly that it follows run 1's readings.<br>**Baseline (B3d), from the source.** used_b1 is the measurement right after COPY, flush and row count. used_b is taken at a **null label** that does every step of a P label except the load: `Jmx set DenylistMaxKeysPerTable 1000` (the stored value, `Config.java:774`; the setter only stores, `DatabaseDescriptor.java:4813-4818`), read-back, 5 s, `GC.run` ×2, `heap_info`, and the histogram Total (a forced full GC, live objects). The cache holds no `dl.t1` entry there: the last load ran on an empty table and installed an empty cache (`PartitionDenylist.java:473-475`, `:222-236`); COPY writes to `system_distributed` return before `denylist.get` (`:312`, `:292-300`); and nothing reads `dl.t1`. The source does not bound the lifetime of the post-ingest state (run 1: the flushed `heap_buffers` memtable, `conf/cassandra.yaml:825`), so the baseline must be shown stable.<br>**Centres (B3f (i′)), from the entry's structures.** Per key: the `byte[8192]` (8,208 B), the `HeapByteBuffer` (48 B; JDK 11 `javap`: 4 ints + 1 long + 1 ref + 1 int + 3 booleans after a 12 B header), the `LongToken` (24 B) and two references in the Guava 32.0.1 arrays (8 B), which makes 8,288 B. Add the `RegularImmutableSet` table of 4·T(P) B, with T = `chooseTableSize(P)` from the bytecode (2,048 / 8,192 / 32,768), and 176 B of fixed headers. That gives **entry(P) = 8,296,368 · 41,472,944 · 165,891,248 B**. These equal the audit probe's `measureDeep` values, which were computed before any reading. Other heap a load leaves live is independent of P and ≪ 1 MiB: one cache node (`:222-236`), no statement cache (`QueryProcessor.java:345-348`, `:893-905`), the chunk cache off (`Config.java:499`), and the result set is a local (`:413`).<br>**Widths.** The filed tolerance, not narrowed: ±25 % or ±6 MiB. Δ_1000 in [1.91, 13.91], Δ_5000 in [29.66, 49.44], Δ_20000 in [118.65, 197.76] MiB; difference in [23.73, 39.55] MiB; reversal ≤ 6 MiB.<br>**(v′).** \|used_b − used_b1\| ≤ 6 MiB. The ingest residue used_b1 − used₀ is recorded and is not a condition.<br>**B3g.** Row 1 is read with (i′) and (v′). Three rows are added: used_b missing or unstable; every Δ below its band or any Δ < 0; every Δ above its band by a similar amount. All three give Not confirmed.<br>B1, B3f (ii)–(iv), (vi) and the unit tier are unchanged. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's readings were known** when the amendment was written: used₀ 49,242,552 B; post-ingest 275,852,240 B (drift 216.11 MiB); used_P 284,156,440 / 317,347,808 / 441,777,784 / 284,197,120 B; Δ against the post-ingest reading 7.92 / 39.57 / 158.24 / 7.96 MiB (8.3 KB per key); difference 31.65 MiB; reversal 40,680 B; 20,009 `BTreeRow` held after the ingest. No new number comes from these readings: the centres come from the source and bytecode, and the widths and the 6 MiB are the filed ones. **Would run 1 pass?** Only partly. With its post-ingest reading substituted for used_b, every (i′) relation holds (`run1b-cluster/selfcheck-known-answer-on-run1-relations-amended-b-ingest.out`: 25 checks, 1 failed, which is the missing null label). But run 1 has no null-label reading, so (v′) cannot be evaluated. Under the amended table run 1 falls in the row "used_b missing", **Not confirmed** (`…-relations-amended.out`: 23 checks, 6 failed). |
| **Case-file version** | sha256 **`e15e95b1b683889a8336375dd6953e0a12d66b9727ba4d9f03a1dfb2baba1e74`**. It is a new row in `_INDEX-advisor.md` §2: "re-frozen after run 1 for cluster re-run (B3d, B3e, B3f (i) and (v), B3g, B3h), authorised by the user". The earlier rows (`04aa8df3…`, `0d0a30a1…`, `15dcf035…`, `ebd47980…`) are kept. It was hashed at 18:47:30 EDT, after the fresh clone was built (18:43–18:44) and before the shakedown (18:49:45) or any re-run reading (18:52:50). The same hash was recorded again at 18:49:37 in `run1b-cluster/harness-sha-run2.txt`. Section D was filled afterwards, so the file's current hash differs by that section only. Base commit `aabb19d`; nothing committed. |
| **Harness** | Run 1's harness with changes H1 (paths), H2 (null label) and H3 (self-check) only (§3).<br>sha256 at the re-run: `cluster-run.sh` `df51aea4`, `make-node-conf.sh` `af27ad36`, `Jmx.java` `6aff0f4b` (unchanged, B3b verbatim), `selfcheck.py` `80645a82` (`run1b-cluster/harness-sha-run2.txt`).<br>Commands: `DLMK_C=$W/cassandra-run65 DLMK_NODE=$W/node-dlmk2 DLMK_B2=1 cluster-run.sh shake2 2000 100 500 2000 100`, then the same with `run2 20000 1000 5000 20000 1000`.<br>Instrument checks: in the shakedown, the null label read back 1000 and added no `Loaded` line (6 in all). The self-check ran end to end on the shakedown first: 25 checks, 0 failed, exit 0 (`run1b-cluster/shakedown/selfcheck.out`; shakedown Δ 0.808 / 3.984 / 15.865 / 0.842 MiB against entry 0.792 / 3.956 / 15.824 MiB, baseline stable to 7,784 B, ingest residue 27.06 MiB; not judged). |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18; free disk 112 GiB. Cluster
re-run 2026-10-27: shakedown 18:49:45–18:51:33 EDT, re-run 18:52:50–18:54:42 EDT. Fresh clone from `~/cassandra-src` at
`b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change: `$W/cassandra-run65` (`ant -Dlocal.repository=$W/m2 build-test`,
`BUILD SUCCESSFUL`, 53 s; `run1b-cluster/clone-build-run65.txt`). Node `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M` (`-Xms2G -Xmx2G`, `-XX:+UseG1GC`), as in run 1.
Node data and the 328 MB CSV in `$W/node-dlmk2`, wiped before and after. Full logs: `~/Library/Caches/stage4/logs/denylist_max_keys_per_table-setDenylistMaxKeysPerTable/`:
`clone-run65.log`, `build-test-run65.log`, `harness-sha-run2.txt`, `driver-shake2.out`, `cluster-shake2/`, `selfcheck-shake2.out`, `driver-run2.out`,
`cluster-run2/` (as run 1's `cluster-run1/`, plus `B2/`), `selfcheck-run2.out`, `selfcheck-run2-under-run1-relations.out`,
`selfcheck-known-answer-run1-relations-{run1,amended,amended-b-ingest}.out`. Excerpts: [`run1b-cluster/`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1b-cluster/)
(`cluster/` with run 1's kinds of files plus `B2/`; `shakedown/`; `selfcheck.py`; `selfcheck.out`; `selfcheck-rerun-under-run1-relations.out`;
`selfcheck-known-answer-on-run1-relations-{run1,amended,amended-b-ingest}.out`; `driver.out`; `harness-sha-run2.txt`; `clone-build-run65.txt`).

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt`, `settings.txt`, `rows.txt`, `copy-tail.txt`, `set0*.txt`, `system-log-denylist-lines.txt` and, per label,
`histogram-excerpt.txt`, `heap_info.txt`, `set.txt`, `readback.txt`, `load.txt`, `error-exceeded.txt`; recomputed from the raw files by `selfcheck.py`.
Settings read back: `partition_denylist_enabled true`, `denylist_consistency_level ONE`, `denylist_max_keys_total 1000000`, reads, writes and range reads `true`,
`denylist_refresh 600s`. COPY `20000 rows imported … 2.673 seconds (0 skipped)`; `count` 20000. `partition_denylist` flushed twice
(`MEMTABLE_LIMIT`, 170.7 MiB on-heap, and `USER_FORCED`, 42.0 MiB).

| Label | Set / read-back | `Loaded … in` | ERROR allowance lines | live heap (histogram Total) | Δ vs used_b | entry(P) derived | Δ − entry | band (MiB) | `[B` vs B2 per key | `HeapByteBuffer` vs B2 | Evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|
| base (empty load) | — | 1 ms | none | 49,419,088 (used₀) | — | — | — | — | — | — | `cluster/base/` |
| set 0 | `REJECTED 0 … IllegalArgumentException: denylist_max_keys_per_table must be a positive integer.`; read-back 1000 | — | — | — | — | — | — | — | — | — | `set0.txt`, `set0-readback.txt` |
| ingest (after COPY + flush) | — | — | — | 286,545,520 (used_b1) | — | — | — | — | — | — | `cluster/ingest/` |
| B2 (null label) | `OK 1000` / 1000, no load | — | — | **286,553,176 (used_b)**; used_b − used_b1 = **7,656 B** | — | — | — | (v′) ≤ 6 MiB | — | — | `cluster/B2/` |
| P = 1000 | `OK 1000` / 1000 | 55 ms | `(1000)` | 294,867,200 | **8,314,024 B = 7.929 MiB** (8,314.0 B/key) | 8,296,368 | +17,656 | [1.91, 13.91] | 8,213.7 | +1,000 | `cluster/L1-P1000/` |
| P = 5000 | `OK 5000` / 5000 | 172 ms | `(5000)` | 328,059,688 | **41,506,512 B = 39.584 MiB** (8,301.3) | 41,472,944 | +33,568 | [29.66, 49.44] | 8,209.5 | +5,000 | `cluster/L2-P5000/` |
| P = 20000 | `OK 20000` / 20000 | 660 ms | none | 452,489,880 | **165,936,704 B = 158.250 MiB** (8,296.8) | 165,891,248 | +45,456 | [118.65, 197.76] | 8,208.5 | +20,000 | `cluster/L3-P20000/` |
| P = 1000 (again) | `OK 1000` / 1000 | 33 ms | `(1000)` | 294,904,552 | **8,351,376 B = 7.964 MiB** (8,351.4) | 8,296,368 | +55,008 | [1.91, 13.91] | 8,219.0 | +1,000 | `cluster/L4-P1000/` |

Δ_5000 − Δ_1000 = **31.655 MiB** (centre 31.640, band [23.73, 39.55]). Last P = 1000 − first = **37,352 B** (≤ 6 MiB). No `Error reading` line,
no `global allowance` line, six `Loaded` lines (startup, base, four loads; none at the null label), three `ERROR` lines in all. Recorded, not a
condition: the ingest residue used_b1 − used₀ = **237,126,432 B = 226.14 MiB** (run 1: 216.11 MiB). The histogram holds 20,009 `BTreeRow`
at the ingest, at B2 and at every label (7 at base). `Murmur3Partitioner$LongToken` is 133 / 137 at base / ingest / B2, then
1,137 / 5,137 / 20,137 / 1,137. `heap_info` `used` agreed with the histogram Total within 2 KiB at every label after the ingest (base: 16 MiB high, one young region allocated
after the GC; the instrument issue of runbook fix 2, recorded only).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`e15e95b1…`, hashed at 18:47:30, before the shakedown and the re-run) [observed: `_INDEX-advisor.md` §2; `harness-sha-run2.txt`; `commands.log` first line 18:52:50].
   - Every step of B3 ran from the beginning in the frozen order, in a fresh clone, after a shakedown [observed: `summary.txt`, `shakedown/summary.txt`].
   - The node ran with a 2 GiB G1 heap. Settings were read back; 20,000 rows; every set was read back equal to P; the null label read back 1000 and loaded nothing; no read error [observed: `summary.txt` `JVM`, `settings.txt`, `rows.txt`, `*/readback.txt`, `system-log-denylist-lines.txt`].
   - Valid.
2. **Readings.** The post-ingest level again sits far above used₀ (226.14 MiB), as in run 1. The null label agrees with the post-ingest reading to 7,656 B. The `BTreeRow` count is constant from the ingest on [observed: histograms].
3. **Matched row.** B3g row 1, "Δ tracks min(P, M) × 8 KiB and shrinks back when P is lowered — claim confirmed on a node", read with the 2026-10-26 and 2026-10-27 amendments. Each part [observed; computed by `run1b-cluster/selfcheck.py`]:
   - (i′) Δ vs used_b = 7.929 / 39.584 / 158.250 / 7.964 MiB, each inside its band and within 0.7 % of entry(P); Δ_5000 − Δ_1000 = 31.655 MiB in [23.73, 39.55]; last − first = 37,352 B ≤ 6 MiB;
   - (ii) read-back = P after each set; `set 0` → `REJECTED … IllegalArgumentException`, read-back 1000;
   - (iii) exactly one `per-table allowance of (P)` line at P = 1000, 5000 and the last 1000; none at P = 20000 or at the empty load;
   - (iv) no `Error reading` line; one `Loaded` line per load;
   - (v′) \|used_b − used_b1\| = 7,656 B ≤ 6 MiB;
   - 20,000 rows.

   **Tier rule: Confirmed.**
4. **Excluded rows.**
   - "Δ ≈ 160 MiB for every P": Δ goes 7.93 → 158.25 → 7.96 MiB.
   - "Δ grows by ≫ 8 KiB/key": 8,296.8–8,351.4 B per key.
   - "0 accepted": rejected.
   - Read error, row count ≠ 20000, read-back ≠ P: none.
   - "Δ inside its band for some P and not others": all inside.
   - ERROR lines off: exact. Not reversible: 37 KB. Node failure: none.
   - Added 2026-10-27: used_b missing or unstable: no (7.7 KB). Every Δ below its band, or Δ < 0: no. Every Δ above its band: no.
   - The superseded drift row is not applied; its quantity is recorded (226.14 MiB).

   [observed]
5. **Observed vs. inferred.**
   - Observed: every relation, from the raw histograms, Jmx and cqlsh outputs and `system.log`.
   - Inferred: that the 226 MiB residue is the flushed `heap_buffers` memtable of `partition_denylist` still referenced (20,009 `BTreeRow`). It is not needed: the baseline is taken after it and shown stable, and the reversal shows it did not move during the loads.
6. **Deviations and gaps.**
   - None against the re-frozen runbook.
   - The amendment was written knowing run 1's readings (stated in §7.1 and in the amendment). The centres are from the source and the widths are the filed ones.
   - The timer and add/remove refresh paths are not run on the node (unit tier only), as in run 1.
   - Δ − entry (17.7–55.0 KB) is the P-independent remainder the amendment predicted to be ≪ 1 MiB.
7. **Core question.** On a node, each JMX set followed by a load leaves exactly min(P, M) keys on the heap: `HeapByteBuffer` +P and `[B` ≈ 8,208 B per key. The live heap above a stable post-ingest baseline equals the entry size derived from its structures, within 56 KB (8,288 B per key + table + headers). It shrinks back when P is lowered. 0 is refused, and the ERROR line names the allowance used. The entry caps the heap the denylist cache holds for one table.

**Conclusion (one line):** B3g row 1 with the amended B3f (i′) and (v′): confirmed.

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads the node's raw `system.log`, splitting it at each `Loaded partition denylist cache` line to assign
the ERROR lines to loads. It also re-reads the raw histogram and `heap_info` files of every label, the raw Jmx `set.txt` and `set0.txt`, and the raw cqlsh
read-backs, `settings.txt` and `rows.txt`. It does not use `summary.txt`. It was written after the re-freeze and before any re-run reading, and was not
changed after the shakedown or the re-run.
- **Pass 0 (shakedown, `--M 2000 --P 100 500 2000 100`, run end to end first):** 25 checks, 0 failed, exit 0 (`run1b-cluster/shakedown/selfcheck.out`).
- **Pass 1 (re-run raw files, amended relations):** **25 checks, 25 hold, 0 fail**, exit 0 ([`run1b-cluster/selfcheck.out`](denylist_max_keys_per_table-setDenylistMaxKeysPerTable-value--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 24 checks, 5 failed: the drift and the four absolute bands. The 24 lines are **identical** to the cluster lines of `run1/selfcheck.out` (`selfcheck-known-answer-on-run1-relations-run1.out`).
- **Pass 3 (run 1's raw files, amended relations):** 23 checks, 6 failed. There is no null label, so (v′) and the four Δ against used_b cannot be read. The script tells run 1 apart from the re-run (`…-relations-amended.out`). With run 1's post-ingest reading substituted (`--b-label ingest`, information only): 25 checks, 1 failed, the missing null label (`…-amended-b-ingest.out`).
- **Pass 4 (information, re-run raw files, run-1 relations):** 24 checks, 5 failed, the same five as run 1: drift 226.14 MiB, and Δ vs used₀ of 234.08 / 265.73 / 384.40 / 234.11 MiB. The frozen pre-ingest baseline would have failed again (`selfcheck-rerun-under-run1-relations.out`).

Raw files re-opened by hand: `cluster-run2/B2/histogram.txt` (`Total 825858 286553176`); `L3-P20000/histogram.txt` (`Total 886781 452489880`);
`B2/set.txt` `OK 1000` and `B2/readback.txt` `1000`; `node/system.log` (6 `Loaded` lines, 3 `ERROR` lines, all `per-table allowance`);
`commands.log` (14 `GC.run`, two per measurement).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the shakedown; read-backs, rows, settings and the null label re-read. |
| 2. Readings | yes | Totals, `[B`, `HeapByteBuffer` and `BTreeRow` recomputed from the raw histograms. |
| 3. Matched row | yes | Every (i′), (ii)–(iv) and (v′) check passes. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The residue's cause is not used. |
| 6. Deviations and gaps | yes | The non-blind amendment is stated. |
| 7. Core question | yes | caps (per table); usage follows min(P, M) at the derived entry size and reverses. |

**Run 2?** No (2026-10-27). Every count, read-back and ERROR line repeats run 1 exactly. Δ against a stable post-ingest baseline lies within 56 KB
of the derived entry size at every label. A further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps (per table)** (B3g row 1 with the amended B3f (i′), (v′)). It is filed in §8 as a new cluster row; the run-1 cluster row
(Not confirmed) is kept.

**End of the re-run:** no `CassandraDaemon`, `cqlsh`, `Jmx.java` or `jcmd` process; port 7199 free; `$W/node-dlmk2` removed; `$W/cassandra-run65`
clean (`git status` 0 entries); no `cassandra.logdir_IS_UNDEFINED/` or log folder in the repository (2026-10-27, after the self-check).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "After `setDenylistMaxKeysPerTable(P)` and a denylist load or refresh, the in-memory denylist entry for a table holds
exactly `min(P, M)` keys, where M is the number of denylisted rows for that table. Its heap therefore grows with `min(P, M)` and not with M.
Values ≤ 0 are rejected." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: keys = P at 10, 100, 1000, 2500 and on the add-refresh (100) and timer-refresh (50) paths; deep exactly as computed, 8,303–8,320 B per 4 KiB key on ByteOrdered; 0 and −5 rejected, value 1000; 7 ERROR lines as derived; three identical runs) | caps | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** (added row "baseline moved with the ingest": the frozen baseline before the 330 MB ingest is 216 MiB below the post-ingest level; every other part exact — read-backs, `set 0` rejected, ERROR lines, Δ_5000 − Δ_1000 = 31.65 MiB, reversal 40 KB; Δ against the post-ingest control 7.92 / 39.57 / 158.24 / 7.96 MiB, inside every band) | caps (per table) | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `e15e95b1…`, after the user-authorised B3d, B3e, B3f (i)/(v), B3g, B3h amendment) | **Confirmed** — B3g row 1 with the amended B3f (i′), (v′): Δ above the post-ingest baseline (null label) 7.929 / 39.584 / 158.250 / 7.964 MiB for P = 1000 / 5000 / 20000 / 1000 against the derived entry sizes 7.912 / 39.552 / 158.206 MiB (bands [1.91, 13.91] / [29.66, 49.44] / [118.65, 197.76]); baseline stable to 7,656 B; Δ_5000 − Δ_1000 = 31.655 MiB; reversal 37,352 B; read-backs exact; `set 0` rejected, value 1000; ERROR lines (1000), (5000), none, (1000); `HeapByteBuffer` +P; ingest residue 226.14 MiB recorded | caps (per table): after a JMX set and a load the node holds exactly min(P, M) keys, at 8,288 B per 8 KiB key plus the hash table, and the heap shrinks back when P is lowered | cluster re-run (§7) + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D (uncommitted); the sixteen step-0 amendments and the two runbook fixes (B2e, B3d) are in the
case file, dated, with the three sha256 values as new rows in `_INDEX-advisor.md` §2; `_INDEX-advisor.md` §1 Stage 4 column and the coverage
line updated. No section was amended for a refutation (none occurred).

**Feedback filed for the cluster re-run (2026-10-27):** the five amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` in the
case file (B3d, B3e, B3f (i) and (v), B3g, B3h); a new `_INDEX-advisor.md` §2 row (`e15e95b1…`); the case file's section D (new entry); the §1 Stage 4
column (run-1 text kept, re-run verdict appended). The coverage section is not touched (the case was already counted as closed). No refutation, so no
other case section is amended. Recommendation for stage 3: a heap baseline for a cache filled from a system table must be taken after the ingest and
shown stable (here a flushed `heap_buffers` memtable left 216–226 MiB live); run 1's pre-ingest baseline was its only failed part.
