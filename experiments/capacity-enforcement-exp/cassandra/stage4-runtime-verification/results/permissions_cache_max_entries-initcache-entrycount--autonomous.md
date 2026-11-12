# permissions_cache_max_entries-initcache-entrycount--autonomous — stage-4 results  <!-- file: results/permissions_cache_max_entries-initcache-entrycount--autonomous.md -->

> **Case:** [`permissions_cache_max_entries-initcache-entrycount--autonomous`](../../stage3-ai-deep-read/cases/permissions_cache_max_entries-initcache-entrycount--autonomous.md)
>
> **Status:** verdict filed (2026-11-12); audited and frozen 02:54 UTC, run 1 unit 02:58-03:00 UTC, cluster 03:03-03:10 UTC, self-checked
>
> **Outcome class:** true positive (estimate `positive`; unit **Confirmed — caps**, cluster **Confirmed — caps**; caps the entry count, so heap ≈ M x per-entry size, and per-entry size is not bounded by the knob)
>
> **Agent:** autonomous (the suffix of the case-file stem). For an autonomous
> file, "§9a" below means each tier's predictions and conclusions table: B2f and B2g
> (unit), B3f and B3g (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; and the case
> file's feedback section is its section D, not §10. One results file per case file.

**Relative links in this template** are written for where a *copy* of it lives
— inside `results/` — not for the template's own location one level up.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Repository HEAD `f74aade6` (the case file is untracked there; the coordinator commits it). Filing sha256 (`_INDEX.md` §4): `aeea2403ea2de046fe2e301a7e72dd0040061725c6ffc6e756ab0a71e0d6b297`. sha256 of the whole file after the audit's amendments AM1-AM5 (section D1 of the case file, 2026-11-12): `7699cce76a787e8f8365ad96f7786a8081183f8776e13990fa09ca0b8a774fd4`. sha256 of the frozen prediction and conclusion text (B2f-B2g from `**B2f.` up to `**B2h.`, B3f-B3g from `**B3f.` up to `**B3h.`, and the amendment block D1 from `### D1.` up to `### D2.`, concatenated; copy kept at `/mydata/jingsong-cass-s4/o03-local/freeze-pred.txt` on the coordinating machine and `/mydata/jingsong-cass-s4/o03/freeze-pred.txt` on apt138): `65402215d62bd72399e349caaa6b34dac0623cbfc80beeecdd0928fdb0410b45`. Frozen 2026-11-12 02:54 UTC, before any reading. Section D2 (feedback) is outside the table hash and changes after the run. |
| **Harness** | `harness/permissions_cache_max_entries-initcache-entrycount--autonomous/` (files listed in its README; not committed by this session, the coordinator commits) |
| **Tiers and values** | Unit (B2): `PermissionsCacheMaxEntriesProbeTest` as filed, N = 30000 distinct `RoleResource` keys of 4000 characters; M in {0, 100, 1000 (default), 10000, 100000 (positive control)}, plus M = -1 and a runtime shrink 10000 -> 100; one JVM per arm. Cluster (B3): one node, 1 GiB heap, N = 20000 `DROP ROLE IF EXISTS` of distinct 4000-character non-existent roles as the superuser; M in {1000 (default), 5000, 100000 (positive control)} plus a runtime shrink 100000 -> 1000 and a cache-off arm (`permissions_validity: 0ms`). |
| **Audit bottom line** | **Ready after amendments** — 2026-11-12 (AM1-AM5 applied in the case file's section D1) |

### 1.1 Design audit

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Partly | A1/A2: the knob is an entry count; each entry has a derivable byte size (≈ 4.2 KB with a 4000-character resource name, B2c). Accepted as a count with a derivable byte size; A2 names that per-entry bytes are not bounded by the knob. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b: 0, 100, 1000 (default), 10000, 100000; B3b: 1000 (default), 5000, 100000, plus runtime shrink and cache off. |
| A. Core question | real resource measured, not only the counter (gap named) | Met | B2d: heap after `System.gc()` beside `estimatedSize`; B3d: class histogram (live `RoleResource`, `[B`) beside `EstimatedSize`. AM5 fixes the live-heap reading to the histogram. Gap named: per-entry bytes inferred from deltas. |
| A. Core question | usage driven to the limit and past it | Met | N = 30000 (unit) and 20000 (cluster) distinct keys, 3x to 30x the binding values. |
| B. Logic | each step says what it establishes | Met | B2h/B3h name each control's purpose; B2e/B3e steps are arm-by-arm. |
| B. Logic | prediction stated in numbers or a clear relation | Met after AM3 | B2f/B3f give sizes, counts and MB; size = min(M, N). The "reloads of first 100" column for binding arms is not predictable from source (Caffeine W-TinyLFU admission), made informational (AM3). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Met after AM4, AM5 | Rows for confirmed, bound broken, positive control failed, loads short, count capped / memory elsewhere, shrink not enforcing, cache-off grows. "≈", "materially above", "≪" and "scales" were not quantified: AM4/AM5 give thresholds; readings between rows are "Not confirmed (no matching row)". |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | The ceiling follows M across arms; the disallow (eviction) effect is shown directly by `estimatedSize` settling at M while loads = N, by the live `RoleResource` count, and by the runtime shrink (line 357). No `if` in Cassandra: the eviction is inside Caffeine (A3.3). |
| B. Logic | alternative explanations and their controls | Met | Expiry ruled out by 1 h validity/update interval; positive control M = 100000; cache-off arm; baseline histogram per arm; one JVM / fresh node per arm. |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3 and B1 state the claim and the mechanism. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Met | The full test class (B2e) and the driver (B3c) are given. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | Paths name a different user's tree and a non-shared node (AM1); default ports clash on a shared node (AM2); thresholds missing (AM4, AM5). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | JDK 11, Ant, Python 3.10 (bundled driver) on apt138; build per environment.md §3. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met | Unit uncapped ≈ 126 MB in a 1 GiB test heap; cluster uncapped ≈ 84 MB in a 1 GiB heap; disk a few hundred MB on `/mydata` (1.6 TB free); one 1 GiB node at a time (≈ 14 GiB free). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in the copy (cassandra-5.0.9): `AuthCache.java:344-346` (builder, `.maximumSize(getMaxEntries())`), `:357` (`setMaximum`), `:289-296` (`setMaxEntries` -> `initCache(cache)`), `:317-320` (`getEstimatedSize`), `:331-339` (null cache when not required / validity <= 0; log line), `:390-394` (`shutdownNow`), `:207` (`getAll`), `:74` (protected `cache`); `Config.java:91` (default 1000); `DatabaseDescriptor.java:1798-1836`; `PermissionsCache.java:29-47`; `AuthenticatedUser.java:42`, `:126-129`; `ClientState.java:474-536`, `:646-648` (no superuser shortcut before the cache); `CassandraAuthorizer.java:79-80`; `DropRoleStatement.java:42-75`; `AuthenticationStatement.java:55-59`; `QueryProcessor.java:271`; `CassandraRoleManager.java:423-426`, `:549-558` (`isExistingRole` reads the table, not the roles cache); `RoleResource.java:63-91` (one `name` field per instance, so ≈ 4 KB per key); Caffeine 3.1.8 (`.build/parent-pom-template.xml:1059-1061`). All as cited. |

| # | Recommendation | Applied? (amendment date and commit, or "left for stage 3") | Why |
|---|---|---|---|
| AM1 | Working tree = `copy-source.sh` copy at `/mydata/jingsong-cass-s4/o03/src` on apt138; all `/mydata/o03` paths moved | applied 2026-11-12 (case file D1; untracked, no commit) | B2a names another user's tree; the run must not touch shared source |
| AM2 | Ports 7300/7301/9342, JMX 7499, seeds `127.0.0.1:7300`; daemon check by own PID/directory; wait for `statusbinary` | applied 2026-11-12 | node shared with another project; `pgrep -f CassandraDaemon` would see other daemons |
| AM3 | "Reloads of first 100" for binding arms informational (0-100) | applied 2026-11-12 | not predictable from source: Caffeine's admission policy decides which keys survive a one-pass scan |
| AM4 | Unit thresholds for every B2g row | applied 2026-11-12 | "≈", "materially above", "≪", "scales" unquantified |
| AM5 | Cluster live heap from the class histogram; thresholds for every B3g row | applied 2026-11-12 | same, plus the environment lesson that `heap_info` after `GC.run` is not live heap |
| R-a | State in A2 that the shared knob also sizes `JmxPermissionsCache`, and that the scope note's other caches are separate knobs (already in A3.6) | left for stage 3 | wording only |
| R-b | Name in B2f the expected Caffeine structures (frequency sketch, hash table) in the per-entry figure | left for stage 3 | the 1.5x band covers them |

**Agreement criteria** — run 2 not planned (one run per the coordinator's instructions).


## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-11-12 (unit 02:58:43-03:00:48 UTC; cluster 03:03:02-03:10:46 UTC; shakedowns 02:55-02:58 and 03:01-03:02 UTC) | not done |
| Node (CloudLab name and type) | `apt138` (`node2.jason92-325433.misconfiguration-pg0.apt.emulab.net`), 16 cores, 15 GiB RAM (~14 GiB free); shared with another project (OOM-exp): this run used loopback 127.0.0.1 with storage 7300, ssl 7301, native 9342, JMX 7499 (all checked free before each tier) | |
| OS and kernel (`uname -r`) | Ubuntu 22.04, 5.15.0-198-generic | |
| JDK (`java -version`) | openjdk 11.0.33 (2026-10-20) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local source copy | `copy-source.sh /mydata/jingsong-cass-s4/o03-src` on the coordinating machine at repository HEAD `f74aade6` (`systems/cassandra/source` clean; tag `cassandra-5.0.9`), rsynced to `apt138:/mydata/jingsong-cass-s4/o03/src`; `ant build-test` BUILD SUCCESSFUL in 1 min 47 s | |
| Case-file / harness commit | case file and harness untracked at HEAD `f74aade6` (the coordinator commits). Case-file sha256 at the freeze `7699cce7...`; after AM6 (D3, runbook defect D1, before run 1) `0dd2face1204b0feb3d7289d741ed31449deb8436ad1ac9aef2bb19f17d90c93` (the version run 1 used); harness md5 prefixes in `run1/unit-summary.txt` and `run1/cluster-session.txt` | |
| Storage for node data | `/mydata` on apt138 (local LVM volume, 1.8 TB, 1.6 TB free); node data per arm in `/mydata/jingsong-cass-s4/o03/run1/cluster/node`, removed after each arm; heap 1 GiB (`MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`, G1); unit test JVM 1 GiB (`testsome` `maxmemory`) | |
| Full logs (path, outside the repo) | `apt138:/mydata/jingsong-cass-s4/o03/run1/{unit,cluster}/` (unit: junit XML, `TEST-*.log`, `ant-*.log`; cluster per arm: `*.hist`, `*.heap`, `system.log`, `gc.log*`, `driver.txt`, `cassandra.yaml`, `yaml.diff`); shakedowns in `.../o03/shakedown{,-a}/`; build log `.../o03/logs/build-test.log` | |

## 3. Runbook defects

| # | Run | Step (§9b–§9e) | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| D1 | unit shakedown (before run 1) | B2e.3 | `grep PROBE` over the junit XML found nothing: the test logback config wraps `System.out` and writes it to `build/test/logs/_jdk11/TEST-<class>.log`, one log line per `write()` with newlines dropped, so a `printf` record arrives as 14 fragments | collect from that log and rejoin the fragments (`collect-probe.py`); test class, arms, B2f and B2g unchanged. Case-file amendment AM6 (section D3). The tier had not started (shakedown only); run 1 used the fixed collection from its first arm | 2026-11-12 | untracked file (no commit) |

Not defects, applied at the audit (section 1): AM1 (paths), AM2 (ports on a shared node).

## 4. Run 1

**Scope:** unit tier (B2) all arms as filed: M = 0, 100, 1000, 10000, 100000, -1, shrink 10000 -> 100, one JVM each, N = 30000, L = 4000. Cluster tier (B3) all arms as filed: M = 1000, 5000, 100000 (+ runtime shrink to 1000), cache off (validity 0, M = 100000), N = 20000 `DROP ROLE IF EXISTS` of 4000-character non-existent roles, fresh node per arm. **Command log:** `run1/unit-summary.txt`, `run1/cluster-session.txt`; raw readings `run1/unit-probe-lines.txt`, `run1/cluster-hist-excerpts.txt`; analyzer output in `run1/unit-summary.txt` (end) and `run1/cluster-analysis.txt`; self-check `run1/selfcheck.txt`; one arm's yaml change `run1/cluster-M1000-yaml.diff`.

### 4.1 Readings

**Unit tier** (N = 30000 distinct keys, L = 4000; heap delta = used heap after 3x `System.gc()`, after fill minus before)

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| M = 0 | estimatedSize 0, asMap 0, loads 30000, reloads of first 100 = 100, heap delta -0.3 MB | `run1/unit-probe-lines.txt` |
| M = 100 | 100, 100, 30000, 100, 0.1 MB | same |
| M = 1000 (default) | 1000, 1000, 30000, 100, 3.7 MB (3.79 KB per entry) | same |
| M = 10000 | 10000, 10000, 30000, 100, 39.9 MB (4.09 KB per entry) | same |
| M = 100000 (positive control) | 30000, 30000, 30000, 0, 120.5 MB (4.11 KB per entry) | same |
| M = -1 | `java.lang.IllegalArgumentException: maximum size must not be negative` at construction | same |
| runtime shrink 10000 -> 100 (`setMaxEntries`, line 357 path) | before 10000, after 100 | same |
| junit | 7 JVMs, each `Tests run: 1, Failures: 0, Errors: 0` (the test's own `size <= max` assertions passed) | `run1/unit-summary.txt`, `run1/selfcheck.txt` |
| analyzer | 20 `EXPECTED PASS`, 0 FAIL; matched B2g row 1 | `run1/unit-summary.txt` |

**Cluster tier** (Δ = after - baseline of the same arm; RoleResource and `[B` from `GC.class_histogram` (live objects after a full GC); baseline per arm: EstimatedSize 14, RoleResource 6)

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| M = 1000 | arm M1000 | EstimatedSize / vtable count | 1000 / 1000 | `run1/cluster-session.txt`, `run1/cluster-analysis.txt` |
| M = 1000 | | Δ RoleResource; Δ `[B`; Δ histogram total; `[B`/entry | 1001; 3.90 MB; 4.86 MB; 3.99 KB | `run1/cluster-hist-excerpts.txt`, `run1/cluster-analysis.txt` |
| M = 5000 | arm M5000 | EstimatedSize / vtable | 5000 / 5000 | same |
| M = 5000 | | Δ RoleResource; Δ `[B`; Δ total; `[B`/entry | 5001; 19.22 MB; 20.73 MB; 3.94 KB | same |
| M = 100000 (positive control) | arm M100000 | EstimatedSize / vtable | 20014 / 20015 | same |
| M = 100000 | | Δ RoleResource; Δ `[B`; Δ total; `[B`/entry | 20001; 76.67 MB; 80.48 MB; 3.93 KB | same |
| 100000 -> 1000 at runtime | arm M100000, shrink | EstimatedSize / vtable; Δ RoleResource; Δ `[B`; Δ total | 1000 / 1000; 1001; 3.91 MB; 5.51 MB; `system.log` shows a second `(Re)initializing PermissionsCache (3600000/3600000/1000/false)` line | same; `run1/selfcheck.txt` |
| cache off (validity 0) | arm off | EstimatedSize / vtable; Δ RoleResource; Δ `[B`; Δ total | 0 / 0; 0; 0.06 MB; 0.71 MB; no `(Re)initializing PermissionsCache` line | same |
| all arms | | workload; node health | `sent 20000` in 25.5-26.2 s per arm, no driver traceback; 0 `^ERROR` lines, 0 `OutOfMemoryError`; init line per arm shows the arm's M | `run1/selfcheck.txt` |
| ratios | | Δ RoleResource 5000/1000; 100000/1000 | 5.00; 19.98 | `run1/cluster-analysis.txt` |
| secondary | | `GC.heap_info` used after `GC.run`, after the workload | 69875K (M1000), 85800K (M5000), 146983K (M100000, base 64488K), 65667K (off) | `run1/cluster-session.txt`, `run1/selfcheck.txt` |

### 4.2 Conclusion and logic

1. **Validity** — Valid. The limit was reached and passed in every binding arm: unit loads = 30000 against M <= 10000 [observed: `run1/unit-probe-lines.txt`]; cluster 20000 statements sent against M = 1000 and 5000 [observed: `run1/selfcheck.txt`, driver lines], each producing one new entry (the M = 100000 arm grew by 20000 entries) [observed]. Held fixed: validity and update interval 3600000 ms (unit by the test's `setup`; cluster in each arm's yaml and in the init log line `3600000/3600000/<M>/false`) [observed: `run1/selfcheck.txt`, `run1/cluster-M1000-yaml.diff`]; active update false [observed: same log line]; one JVM / fresh node per arm [observed: `run1/unit-summary.txt`, `run1/cluster-session.txt`]. Positive controls moved: unit M = 100000 held 30000 entries and 120.5 MB; cluster M = 100000 held 20014 entries and +80.5 MB live [observed].
2. **Readings** — Nothing contradicts another reading. Notes: (a) the unit M = 0 heap delta is -0.3 MB (noise of the `System.gc()` reading, below the 2 MB floor) [observed]; (b) in the binding unit arms all of the first 100 keys were reloaded (100), so Caffeine kept late keys, not early ones; AM3 had made this column informational, and the original B2f value (≈ 100) held [observed]; (c) the cluster baseline holds 14 cache entries and 6 `RoleResource` objects from the logins and `LIST ROLES` [observed: `run1/cluster-session.txt`]; with M = 1000 the settled size is exactly 1000 including them.
3. **Matched row** — Unit, B2g row 1: "size = min(M, N) for all M, heap delta scales with it, M=100000 arm holds 30000" — sizes 0 / 100 / 1000 / 10000 / 30000 = min(M, 30000) exactly; per-entry bytes 3.79 / 4.09 / 4.11 KB (AM4 band 2.8-6.3) and deltas < 2 MB at M = 0 and 100; M = 100000 holds 30000 [observed: `run1/unit-probe-lines.txt`, `run1/unit-summary.txt`]. Cluster, B3g row 1: "EstimatedSize and Δ RoleResource ≈ min(M, 20000); Δ bytes scales the same" — EstimatedSize 1000 / 5000 / 20014 and Δ RoleResource 1001 / 5001 / 20001 (all within 0.1 % of min(M, 20000)); ratios 5.00 and 19.98 (B3f: 5 and 20, ±30 %); Δ `[B` per entry 3.99 / 3.94 / 3.93 KB and Δ `[B` = 3.90 MB at M = 1000 (<= 8 MB) [observed: `run1/cluster-analysis.txt`, `run1/cluster-hist-excerpts.txt`]. The B3f rows for the shrink (EstimatedSize 1000, Δ RoleResource back to 1001, Δ `[B` back to 3.91 MB) and cache off (0, 0, 0.06 MB) hold too [observed].
4. **Excluded rows** — Unit: row 2 (size materially above M): every binding size equals M, M = 0 holds 0 [observed]. Row 3 (positive control small): 30000 [observed]. Row 4 (loads < N): 30000 in every arm [observed]. Row 5 (count capped, heap ≈ uncapped): binding heap deltas 0.1-39.9 MB against 120.5 MB uncapped, largest ratio 0.33 < 0.5 [observed]. Row 6 (shrink stays at 10000): after = 100 [observed]. Cluster: row 2 (M = 1000 retains ≈ 20000): Δ RoleResource 1001 [observed]. Row 3 (count capped, memory elsewhere): Δ RoleResource 1001 / 5001 and Δ `[B` 3.90 / 19.22 MB against 20001 and 76.67 MB uncapped (ratios <= 0.25) [observed]. Row 4 (positive control flat): +20001 [observed]. Row 5 (shrink leaves ≈ 20000): 1000 [observed]. Row 6 (cache-off grows): Δ RoleResource 0, Δ `[B` 0.06 MB [observed].
5. **Observed vs. inferred** — Inferred: (i) that the live `RoleResource` count counts permissions-cache keys [inferred: the workload's only long-lived `RoleResource` is the cache key (DROP ROLE of a non-existent role writes nothing and the roles cache is not touched, `DropRoleStatement.java:42-75`, `CassandraRoleManager.java:423-426`); supported by the cache-off arm (Δ 0) and the shrink (Δ back to 1001), both observed]; (ii) that Δ `[B` is the role-name bytes of the retained keys [inferred: 3.93-3.99 KB per entry against 4000 Latin-1 characters per name]; (iii) that the unit heap delta measures retained cache memory [inferred: `System.gc()` is advisory; the readings are consistent across arms (3.8-4.1 KB per entry) and with the cluster's 4.0-4.1 KB per entry (Δ histogram total / Δ RoleResource)].
6. **Deviations and gaps** — (a) Amendments AM1-AM5 at the audit and AM6 for defect D1 (sections 1 and 3); none changed a prediction or a conclusion row's meaning (AM3-AM5 quantified them before any reading). (b) Live heap read from the class histogram rather than `GC.heap_info` (AM5); `heap_info` agrees in direction (M100000 +80.6 MB used after `GC.run`). (c) Not observable, as filed: which entries were evicted and the transient overshoot before Caffeine's maintenance runs; every size reading is after settling (`cleanUp()` in the unit tier, 10 s idle in the cluster tier). (d) The cap is on entries, not bytes (filed in A2): per-entry bytes follow the resource-name length, which no knob bounds; this run used one name length (4000). (e) Shared-node practice: the parent directory `/mydata/jingsong-cass-s4` was created with `sudo` (owned by `jason92`) because `/mydata` is root-owned; one helper script copy was written to `/tmp/o03-cp.py` on apt138 for the shakedown collection check and deleted in the same command (outside the agreed directory; nothing else of this run was written outside `/mydata/jingsong-cass-s4/o03` and `~/.m2`).
7. **Core question** — Usage followed the constraint and the constraint caps it. With N distinct permission lookups past the limit, the settled entry count was exactly min(M, N) at every value (unit 0 / 100 / 1000 / 10000 / 30000; cluster 1000 / 5000 / 20014), the live keys and their bytes followed it (cluster Δ `RoleResource` 1001 / 5001 / 20001, Δ `[B` 3.9 / 19.2 / 76.7 MB, ratio 1 : 5 : 20), and the disallow effect was seen directly: loads kept going to N while the count stayed at M, and a runtime shrink to 1000 (the line-357 path) dropped a 20014-entry cache to 1000 entries and its live keys from 20007 to 1007 (parts 3 and 4). The cache-off arm retained nothing, so the retention is the cache's (part 4). The heap held is M x per-entry size, and per-entry size is not bounded by the knob (part 6 (d)).

**Conclusion (one line):** Unit B2g row 1, cluster B3g row 1 — claim confirmed: `permissions_cache_max_entries` caps the permissions cache's entry count and with it the retained heap (≈ 4 KB x M here) (effect: caps).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

`harness/.../selfcheck.py` re-parses the raw files with its own code (the fragmented test log, the junit XML, every `*.hist`, `session.txt`, each arm's `system.log` and `driver.txt`); output `run1/selfcheck.txt`. Its first version mis-split the test-log lines (double space after `INFO`) and found no unit record; fixed (an instrument fault of the self-check, not a reading), it reproduced every number of section 4.1.

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `selfcheck.txt`: `sent 20000` and no traceback in every arm; init lines `3600000/3600000/1000/false`, `.../5000/...`, `.../100000/...` then `.../1000/...` (shrink), none for `off`; junit 7 x tests=1 failures=0 errors=0. |
| 2. Readings | yes | `unit-probe-lines.txt` re-read: M = 0 delta -0.3 MB, reloads 100 in the binding arms; `cluster-session.txt`: baseline EstimatedSize 14 in each cached arm. |
| 3. Matched row | yes | Sizes, per-entry bytes, Δ RoleResource and ratios re-derived independently in `selfcheck.txt` (e.g. M5000 dRR=5001, d[B=19.22 MB); each clause of B2g / B3g row 1 and AM4 / AM5 holds. |
| 4. Excluded rows | yes | Each exclusion cites a number `selfcheck.txt` reproduces; the largest binding/uncapped ratio (unit 39.9 / 120.5 = 0.33, cluster 19.22 / 76.67 = 0.25) is below the 0.5 of rows 5 / 3. |
| 5. Observed vs. inferred | yes | (i) rests on two observed controls (cache off Δ 0, shrink Δ back to 1001); (ii) and (iii) agree with each other within 5 %. |
| 6. Deviations and gaps | yes | All amendments predate the readings (freeze 02:54 UTC; first reading 02:59 UTC in `unit-summary.txt`); D1 found in a shakedown, not run 1. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | B1 -> B2b-B2e / B3b-B3e -> B2f / B3f -> B2g / B3g row 1, with the positive control (M = 100000) and the cache-off and shrink controls. |

### 5.2 Run 2?

**No** (2026-11-12). The coordinator asked for run 1 only; both tiers agree, every reading lands on the predicted value with wide margins (exact sizes, ratios 5.00 and 19.98), the conclusion's inferred points rest on observed controls, and the result confirms a positive claim with no bypass.

## 6. Run 2 — fresh AI session (optional)

Not done (section 5.2).

## 7. Comparison — only if run 2 was done

Not applicable.

## 8. Verdict — AI

Jingsong may overrule any verdict at any time; record an override here with its date and reason.

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): both tiers Confirmed, effect caps.

**Claim tested:** (B1) With `permissions_cache_max_entries = M` and the permissions cache enabled, after N > M distinct `(user, resource)` lookups the permissions cache holds at most M entries (transiently a little more), and the heap it retains is ≈ min(M, N) x per-entry size; raising M above N lets the same workload retain ≈ N entries. "Confirmed" below means this claim held.

| Tier | Verdict (§9a row; for an autonomous file, the B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | B2g row 1: **Confirmed** — settled size = min(M, 30000) exactly for M = 0, 100, 1000, 10000, 100000; heap 3.8-4.1 KB per entry; runtime shrink 10000 -> 100 | caps (entry count; heap ≈ M x per-entry size) | run 1 + self-check | 2026-11-12 |
| Cluster | B3g row 1: **Confirmed** — EstimatedSize and live `RoleResource` = min(M, 20000) for M = 1000, 5000, 100000; live `[B` 3.9 / 19.2 / 76.7 MB; runtime shrink to 1000 and cache-off controls as predicted | caps (entry count; heap ≈ M x per-entry size) | run 1 + self-check | 2026-11-12 |

**Positive control:** M = 100000 (non-binding) on the same workload — unit 30000 entries / 120.5 MB, cluster 20014 entries / Δ 20001 `RoleResource` / Δ 76.7 MB `[B`.

**Feedback filed:** the case file's section D updated: D1 (audit amendments AM1-AM5), D2 (stage-4 feedback), D3 (AM6, runbook defect D1); no section of the trace was refuted. Case-file sha256 after the feedback: `2041e3cf3f02d1eb25a6835f5ce413139451b3b0f2ab7539d7132c4166882d09`; the frozen prediction and conclusion text re-hashes to `65402215...0b45` after the run (unchanged since the freeze). **Open points for the user:** (1) the knob caps entries, not bytes: a client that can choose resource names (role names here, 4000 characters) sets the per-entry size, so the heap bound is M x the longest key, which nothing in this knob bounds (filed in A2/A3.6, confirmed in shape: ≈ 4 KB per 4000-character entry); (2) `JmxPermissionsCache` shares the knob (A3.6) and was not exercised. **Upstream / doc candidates:** none for a bug; doc note that `*_cache_max_entries` bounds entries, not memory. **Leftovers on apt138:** nothing running (checked after the run: no `CassandraDaemon` from `/mydata/jingsong-cass-s4`, no test JVM, no `drop_roles.py`; ports 7300/7301/7499/9342 free); kept on the node: `/mydata/jingsong-cass-s4/o03/` (working tree `src` with `build/` and `JMX_PORT="7499"` in its `conf/cassandra-env.sh`, ≈ 469 MB; `run1/`, `shakedown/`, `shakedown-a/`, `logs/`, `harness/`, `freeze-pred.txt`; ≈ 480 MB in total) and the dependency cache `~/.m2`; on the coordinating machine `/mydata/jingsong-cass-s4/o03-src` (the copy) and `/mydata/jingsong-cass-s4/o03-local/freeze-pred.txt`.
