# max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction — stage-4 results  <!-- file: short-path/results/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md -->

> **Case:** short path: `../../../stage3-ai-deep-read/short-path/cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`
>
> **Status:** verdict filed (unit and cluster tiers, run 1 + self-check; no run 2)
>
> **Path:** short. The "case file" below is the short-path solution; "§9a" means B2f/B2g (unit) and B3f/B3g (cluster);
> "§9b–§9e" means B2a–B2e or B3a–B3e.

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the solution file `e8b505e1802722d76642c664e71a55ee2cbb23536bb88e1852edecce143ae7b1`, taken before any run and again after the last run (unchanged). `short-path/_INDEX.md` is not in this workspace, so I could not compare the hash with it; the copy script should do that. The file was never edited. |
| **Harness** | `../harness/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/`: `00-setup.sh` (sha256 `cd9ec00c…`), `10-unit.sh` (`a5669d4c…`), `MaxCompactionSpaceOperandTest.java` (`ace03a5b…`), `20-cluster.sh` (`43666b5f…`), `cassandra-yaml-changes.txt` (`2fda938d…`). No commit: there is no repository in this workspace. |
| **Tiers and values** | Unit (B2): pct ∈ {1.0, 0.95, 0.5, 0.0}, FakeFileStore usableSpace 1,000,000,000 B, plus the B2h control 10,000,000 B; minFree 0. Cluster (B3): pct ∈ {1.0, 0.5}, one node, a 2 GiB data filesystem, min_free_space_per_drive 10 MiB. |
| **Audit bottom line** | **Ready**, with the runbook defects R1–R5 in §3 (a substitute for `sudo mount`, paths, the table name, the load's row count), fixed in the harness. One finding was noted before the cluster run and left as is, because the short-path design is never amended: by the design's own A3.1 formula, B3f's pct=1.0 row cannot hold with the B3c workload (see D2 below). — 2026-10-08 |
| **Files read** | Workspace: `cassandra/if-check-exp/stage4-runtime-verification/README.md`; `cassandra/if-check-exp/stage4-runtime-verification/_TEMPLATE.md`; `cassandra/if-check-exp/stage4-runtime-verification/environment.md`; `cassandra/if-check-exp/stage3-ai-deep-read/short-path/cases/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction.md`; and the files I wrote under `short-path/harness/<stem>/` and `short-path/results/<stem>/`. I ran `find . -type f` once at the workspace root to list it. |
| | Outside the workspace (this machine): none. The tool runtime wrote a transcript, background-task outputs and one oversized tool result under `/tmp/claude-1000/…` and `~/.claude/projects/…` (written by the harness, not opened by me except to read my own command outputs back). ssh used the default `~/.ssh` config and known_hosts implicitly. |
| | Node `jason92@pc57.cloudlab.umass.edu`: `~` (one `ls -la ~` before starting: only dotfiles, no earlier run directories); `~/short-run/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/` (everything I created); clone source `/proj/misconfiguration-PG0/git-repos/cassandra-src` (read only, by `git clone --branch cassandra-5.0.9`, nothing else under `/proj` touched or listed); `sudo apt-get update` / `apt-get install openjdk-11-jdk ant` (environment.md §1). In the clone I read `src/java/org/apache/cassandra/db/Directories.java`, `config/Config.java`, `config/DatabaseDescriptor.java`, `db/compaction/CompactionTask.java`, `db/compaction/SizeTieredCompactionStrategy.java`, `db/ColumnFamilyStore.java` (getExpectedCompactedFileSize), `test/unit/org/apache/cassandra/db/DirectoriesTest.java`, `test/conf/logback-test.xml`, `build.xml`, `bin/cassandra`, `bin/cassandra.in.sh`, `conf/cassandra-env.sh`, `conf/cassandra.yaml`, `tools/stress/src/.../SettingsCommand.java`, `src/java/org/apache/cassandra/tools/NodeTool.java` (greps). `/tmp` on the node: one probe of unprivileged tmpfs mounting created and removed `/tmp/tmp.144GGnf50g` (should have been under the run directory); the JDK left two empty directories, `/tmp/hsperfdata_root` (created at 10:54 MDT by the apt post-install, as root) and `/tmp/hsperfdata_jason92` (by the ant/JUnit JVMs); I left both. |
| | Second node `pc50`: not touched. Web pages: none fetched. **Nothing opened that should not have been.** |

### 1.1 Design audit

Short path: groups A–C are **not applied** (README, "Auditing a short-path solution"); what they would have flagged is listed after the table. D and the safety rules are applied to each tier.

| Group | Check | Rating (Met / Partly / Not met) | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | not applied | see side note |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | not applied | see side note |
| A. Core question | real resource measured, not only the counter (gap named) | not applied | see side note |
| A. Core question | usage driven to the limit and past it | not applied | see side note |
| B. Logic | each step says what it establishes | not applied | see side note |
| B. Logic | prediction stated in numbers or a clear relation | not applied | see side note |
| B. Logic | every plausible outcome has a conclusions row with its evidence | not applied | see side note |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | not applied | see side note |
| B. Logic | alternative explanations and their controls | not applied | see side note |
| C. Specific | a human can follow it from the intro and §9a | not applied | see side note |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | not applied | see side note |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | not applied | see side note |
| D. Runnable | harness and environment prerequisites exist or are listed | Met (B2), Partly (B3) | B2a/B2e list the test file and build. B3a needs `sudo mount -o loop`, which is outside the sudo scope given for this run (JDK and Ant only): defect R1. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Partly | B2c: exact ±1 at the budget. Met. B3c: the load does reach and pass the limit at both values, and fits the node (2 GiB data fs, 57 GB free on `/`, 251 GiB RAM). But B3c computes the budget as pct × *capacity* (2038 / 1019 MiB). A3.1 and `Directories.java:563-569` compute pct × (*current* usable − minFree). With ~1.5 GiB loaded on 2 GiB, usable is ~0.5 GiB, so the pct=1.0 budget is ~0.49 GiB, below the ~1.5 GiB request. I noted this before the cluster run (D2). B3f's pct=1.0 row is therefore expected to fail on the source alone. I ran it as written. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | At `b5f2a542…`: `Config.java:344` (`= .95`); `DatabaseDescriptor.java:1016-1017` (range check), `:2579-2587` (getter/setter); `Directories.java:544-561` (gate, WARN at :553), `:563-569` (budget), `:781-785` (DataDirectory.getAvailableSpace has no pct term); `CompactionTask.java:98-115` (reduceScope), `:384-457` (check loop, abort at :434-442), `:469-472` (`partialCompactionsAcceptable = !isUserDefined`); STCS `getMaximalTask` creates a non-user-defined `CompactionTask`, so `nodetool compact` can reduce scope. |
| Safety | shared-infrastructure rules | Met after R1/R2 | Data on a fixed-size filesystem, not `/proj`. A separate local clone. One run at a time. Every node stopped and checked. B4's cleanup (`umount`, `rm` the image) is automatic for a namespace-scoped tmpfs. |
| Predictions | stated before any run | Met | B2f table, B3f table and the B3f sentence; frozen with the file hash above. |

**Side note: what groups A–C would have flagged (not applied).**
- A: the cluster tier varies the knob over two values only, {1.0, 0.5}, without the default 0.95. The unit tier covers four values, including 0.95.
- B: B3g has no row for "both values warn and reduce scope, to different depths". That is the natural outcome once the budget is understood as a fraction of free space (D2). B3f's pct=1.0 peak "≈ 2×1.5 GiB … up to ≈2038 MiB" cannot happen on a 2 GiB filesystem. B3g's confirmation row needs pct=1.0 to show no warnings, which by the source does not depend on the knob alone.
- C: `nodetool disableautocompaction ks.tbl` is not the CLI syntax (`ks tbl`). The table name `tbl` does not match what `cassandra-stress` writes (`standard1`). `n=<rows>` is left open. `/local/disk/...` is a placeholder path.

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B3c/B3f: compute the cluster budget as pct × (free space at check time − min_free), not pct × capacity. Then either load less (for example ~0.6 GiB, so that ~1.4 GiB stays free and only pct=0.5 trips), or predict "both reduce scope, to depths that follow pct". | left for stage 3 (the short solution is never amended) | A design error found by audit, independent of any reading. |
| 2 | B3a: give a loop-mount alternative that needs no root (for example a tmpfs in a user namespace), or state that root is needed. | left for stage 3; worked around in the harness (R1) | runnability |
| 3 | B3c: name the stress table (`standard1`) and the `nodetool` syntax, and give `n`. | left for stage 3; fixed in the harness (R4) | exactness |
| 4 | B3g: add rows for "both warn, different depth" and for "pct=1.0 also reduces scope". | left for stage 3 | missing outcomes |

## 2. Environment

| Field | Run 1 | Run 2 (fresh AI session, if done) |
|---|---|---|
| Date | 2026-10-08 (unit 16:57–16:58 UTC; cluster pct=1.0 17:12–17:18 UTC, pct=0.5 17:22–17:28 UTC) | not done |
| Node (CloudLab name and type) | `pc57.cloudlab.umass.edu` = `node0.jason92-319347.misconfiguration-pg0.cloudlab.umass.edu`, 32 cores, 251 GiB RAM | |
| OS and kernel (`uname -r`) | Ubuntu 22.04 (environment.md), `5.15.0-187-generic` | |
| JDK (`java -version`) | openjdk 11.0.32.1 2026-08-18 (`run1/00-setup.log.excerpt`) | |
| Ant (`ant -version`) | Apache Ant 1.10.12 | |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (`cassandra-5.0.9`), at `~/short-run/<stem>/cassandra`, used by both tiers | |
| Case-file commit / harness commit | solution sha256 `e8b505e1…`; harness sha256 values in §1 (no repository) | |
| Storage for node data | data dir: 2 GiB tmpfs (2,147,483,648 B) in a private user+mount namespace, one fresh instance per knob value (R1, R3); commit log, hints, caches and logs on local `/dev/sda3` under `~/short-run/<stem>/cluster/<tag>/` | |
| Full logs (path, outside the repo) | node `pc57`: `~/short-run/max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/` — `logs/00-setup.log`, `logs/10-unit.log`, `logs/10-unit.attempt1.log`, `unit/`, `cluster/pct1.0/` and `cluster/pct0.5/` (`run.log`, `logs/system.log`, `logs/debug.log`, `sample-disk.log`, `sample-compactionstats.log`, `stress-*.log`, `nodetool-compact.out`), `logs/20-cluster-pct1.0*.ssh.log`, `logs/20-cluster-pct0.5.ssh.log` | |

**Path mapping (the design's paths → this run).** `~/work/cassandra-5.0.9-unit` and `/local/disk/cassandra-5.0.9-cluster` → one clone, `~/short-run/<stem>/cassandra`. `/local/disk/cass-data` (loop ext4) → `~/short-run/<stem>/cluster/<tag>/mnt` (tmpfs). The design's `sample1.log`/`sample2.log` → `cluster/pct1.0/sample-disk.log` and `cluster/pct0.5/sample-disk.log`. Nothing the design put under `/tmp` was placed there; the JVM's `java.io.tmpdir` was `cluster/<tag>/tmp`.

## 3. Runbook defects

A short-path solution is never amended, so every fix is in the harness. "Restart" means the affected tier was started again from the beginning.

| # | Run | Step | Problem | Fix | Decision (date) | Case-file commit with the fix |
|---|---|---|---|---|---|---|
| R1 | 1 | B3a | `sudo mount -o loop` of an ext4 image: sudo on this node was granted only for installing the JDK and Ant. | A 2 GiB tmpfs mounted in a private user+mount namespace (`unshare -rm`), with no sudo. The node, nodetool, stress, `du` and `df` all run inside it (`20-cluster.sh`). Inside the namespace the user is uid 0, so `bin/cassandra` needs `-R`. Effect on the claim: none. `FileStore.getUsableSpace()` reads the tmpfs's free space, which equals `df`'s avail (known-answer check). The fs is RAM-backed, so write timing differs, and the knob does not depend on timing. | AI, 2026-10-08 | none (never amended) |
| R2 | 1 | B2a, B3a | Placeholder paths (`~/work`, `/local/disk/...`). Separate clones per tier. | One local clone under the run directory for both tiers (the added test class is not in the server jar). Mapping in §2. | AI, 2026-10-08 | none |
| R3 | 1 | B3e step 5 | "Wipe data dir, keep the mount, restart": a namespace-scoped mount cannot outlive one script. | Each knob value gets a fresh, empty 2 GiB tmpfs and a fresh node, with the same config except the knob. | AI, 2026-10-08 | none |
| R4 | 1 | B3c | The table `ks.tbl`, `nodetool disableautocompaction ks.tbl`, and `n=<rows>` are not exact. | `cassandra-stress write … -schema keyspace=ks "replication(factor=1)"` writes `ks.standard1`. The schema is created by a 1-row write (`-pop seq=1..1`, no-warmup). Then `nodetool disableautocompaction ks standard1`, then the load in chunks of 500,000 rows (`-pop seq` ranges, no-warmup, threads=50, `nodetool flush` after each) until `du -sb` of the data dir ≥ 1.5 GiB. That took 14 chunks (7,000,000 rows, 1,724,789,598 B). The pct=0.5 run loaded the same 14 chunks. One chunk's granularity overshoots ~1.5 GiB to ~1.6 GiB. | AI, 2026-10-08 | none |
| R5 | 1 | B3d | `du -sh` and `df -h` are human-rounded. | `du -sb` and `df -B1` (bytes), sampled every 2 s; `nodetool compactionstats` and the `tpstats` CompactionExecutor line polled every ~2 s. | AI, 2026-10-08 | none |
| H1 | 1 (unit, attempt 1) | instrument check | My known-answer step ran `DirectoriesTest` with `-Dtest.methods=…`. The class is `@Parameterized`, so no method matched and ant failed (`run1/unit/10-unit.attempt1.excerpt`). This was a harness defect, before any reading. | Run the whole `DirectoriesTest` as the known answer (42 tests). The unit tier was restarted from the beginning (attempt 1's log was kept as `10-unit.attempt1.log`). | AI, 2026-10-08 | none |
| H2 | 1 (cluster, attempt 1) | pre-check | The in-script "node already running" check used `ps -eo cmd \| grep '[C]assandraDaemon'` and matched my own ssh command line, which contained the text of a grep pattern. The script aborted before creating anything. | Match `java` processes only (`ps -eo comm,args \| awk '$1=="java" && /CassandraDaemon/'`). Restarted. Every standalone check used the prescribed command, with no such literal in the command line. | AI, 2026-10-08 | none |

## 4. Run 1

**Scope:** unit tier, all of B2 (4 pct values × 2 usableSpace values). Cluster tier, B3 at pct = 1.0 and 0.5, once each (B3h's optional repeat not done).
**Command logs:** `max_space_usable_for_compactions_in_percentage-hasDiskSpaceForCompactionsAndStreams-availableForCompaction/run1/00-setup.log.excerpt`, `run1/unit/10-unit.log.excerpt`, `run1/cluster/pct1.0.run.log.excerpt`, `run1/cluster/pct0.5.run.log.excerpt`. Full logs on the node (§2).

### 4.1 Readings

**Unit tier.** Instrument check first: the upstream `DirectoriesTest` passed, 42 tests with 0 failures and 0 errors, including `testFreeCompactionSpace[0,1]` and `testHasAvailableSpace[0,1]` (`run1/unit/TEST-org.apache.cassandra.db.DirectoriesTest.xml`).

| Test or assertion | Result | Evidence (file) |
|---|---|---|
| `MaxCompactionSpaceOperandTest.budgetAndGateAcrossPercentages` | pass (tests=1, failures=0, errors=0) | `run1/unit/TEST-org.apache.cassandra.db.MaxCompactionSpaceOperandTest.xml` |
| `getAvailableSpaceForCompactions`, usable 1e9: pct 1.0 / 0.95 / 0.5 / 0.0 | 1,000,000,000 / 950,000,000 / 500,000,000 / 0, equal to `round(usable×pct)` each time | `run1/unit/readings.txt` |
| same, usable 1e7 (B2h control) | 10,000,000 / 9,500,000 / 5,000,000 / 0: scales linearly | `run1/unit/readings.txt` |
| `hasDiskSpace(expected−1)` and `hasDiskSpace(expected+1)`, pct > 0, both usable values | true / false in all 6 cases | `run1/unit/readings.txt` |
| pct = 0: `hasDiskSpace(0)` / `hasDiskSpace(1)` | true / false (both usable values) | `run1/unit/readings.txt` |
| DEBUG line `has <budget> bytes available, checking if we can write <req> bytes` | exactly one per call, with budget = expected, for all 16 calls | `run1/unit/readings.txt` |
| WARN line `has only <budget> available, but <req> is needed` | exactly one per over-budget call (8 of 8), with the stringified expected budget (e.g. `905.99 MiB` at 0.95); none for under-budget calls (8 of 8) | `run1/unit/readings.txt` |
| total checks | 56 OK, 0 MISMATCH | `run1/unit/readings.txt` |

**Cluster tier.** The same dataset for both values: 14 sstables, Data.db total 1,595,595,865 B (pct 1.0) and 1,595,789,000 B (pct 0.5).

| Capacity value | Run | Observable (B3d) | Reading | Evidence (file) |
|---|---|---|---|---|
| both | instrument | known answer: write 100 MiB to the data fs | `du` = 104,857,600 B; `df` avail drop = 104,857,600 B | `cluster/pct*.run.log.excerpt` (`KNOWN_ANSWER`) |
| 1.0 | config | `Node configuration` line | `max_space_usable_for_compactions_in_percentage=1.0`, `min_free_space_per_drive=10MiB`, `skip_stream_disk_space_check=false` | `cluster/pct1.0.run.log.excerpt` |
| 0.5 | config | same | `…=0.5`, `10MiB`, `false` | `cluster/pct0.5.run.log.excerpt` |
| both | config | `nodetool statusautocompaction ks standard1` before and after the load | `not running` (disabled) | `cluster/pct*.run.log.excerpt` |
| both | config | per-table disk-space check | no "Compaction space check is disabled" line (`space check not disabled`) | `cluster/pct*.run.log.excerpt` |
| 1.0 | load | data dir after the load (flush only, autocompaction off) | `du` 1,724,789,598 B; fs avail 421,933,056 B | `cluster/pct1.0.run.log.excerpt` (`LOAD chunk=14`) |
| 0.5 | load | same | `du` 1,724,982,767 B; fs avail 421,736,448 B | `cluster/pct0.5.run.log.excerpt` |
| 1.0 | before load | budget in Directories DEBUG, early system-table compaction | 2,136,104,960 B | `cluster/pct1.0.debug.log.grep` |
| 0.5 | before load | same | 1,068,052,480 B (exactly ½ of the above) | `cluster/pct0.5.debug.log.grep` |
| 1.0 | compact | budget in the DEBUG line at `nodetool compact` | 411,447,296 B = (421,933,056 − 10,485,760) × 1.0 | `cluster/pct1.0.debug.log.grep` |
| 0.5 | compact | same | 205,625,344 B = (421,736,448 − 10,485,760) × 0.5 | `cluster/pct0.5.debug.log.grep` |
| 1.0 | compact | first request vs. budget | 1,595,595,865 B requested > 411,447,296 B | `cluster/pct1.0.debug.log.grep` |
| 1.0 | compact | WARN `FileStore … has only 392.39 MiB available` / `Not enough space for compaction … Reducing scope` / `insufficient space … removing largest SSTable` | 11 / 11 / 11 | `cluster/pct1.0.debug.log.grep`, `cluster/pct1.0.run.log.excerpt` |
| 0.5 | compact | same (`has only 196.1 MiB available`) | 13 / 13 / 13 | `cluster/pct0.5.debug.log.grep`, `cluster/pct0.5.run.log.excerpt` |
| 1.0 | compact | final accepted request; what was compacted | 341,726,605 B ≤ 411,447,296; **3 of 14 sstables** (325.9 MiB → 327.0 MiB), compactionhistory bytes_in 341,726,605 / bytes_out 342,920,882 | `cluster/pct1.0.debug.log.grep`, `cluster/pct1.0.run.log.excerpt` |
| 0.5 | compact | same | 113,887,785 B ≤ 205,625,344; **1 of 14 sstables** (108.6 MiB → 108.6 MiB), bytes_in = bytes_out = 113,887,785 | `cluster/pct0.5.debug.log.grep`, `cluster/pct0.5.run.log.excerpt` |
| 1.0 | compact | `compactionstats`: reduced / sstables dropped / aborted | 1 / 11 / 0 | `cluster/pct1.0.run.log.excerpt` |
| 0.5 | compact | same | 1 / 13 / 0 | `cluster/pct0.5.run.log.excerpt` |
| 1.0 | compact | `nodetool compact` exit; SSTable count before → after | rc 0, no error; 14 → 12 | `cluster/pct1.0.run.log.excerpt`, `cluster/pct1.0.compactionstats-and-nodetool-compact.txt` |
| 0.5 | compact | same | rc 0, no error; 14 → 14 (one sstable rewritten) | `cluster/pct0.5.run.log.excerpt`, `cluster/pct0.5.compactionstats-and-nodetool-compact.txt` |
| 1.0 | compact | peak `du` of the data dir (2 s samples) and growth over the pre-compaction value | 2,076,669,081 B; growth 351,879,483 B (≤ budget 411,447,296); lowest fs avail 69,918,720 B; after: 1,726,297,890 B | `cluster/pct1.0.sample-disk.window.txt` |
| 0.5 | compact | same | 1,819,485,994 B; growth 94,503,227 B sampled (the 113.9 MB output finished between samples; ≤ budget 205,625,344); after: 1,724,994,475 B | `cluster/pct0.5.sample-disk.window.txt` |
| both | errors | `^ERROR` lines in debug.log | 0 | `cluster/pct*.debug.log.grep` |
| both | stop | node stopped, no daemon left | `NODE_STOPPED none left`; separate `ps -eo cmd \| grep '[C]assandraDaemon'` empty before and after each value | `cluster/pct*.run.log.excerpt` |

### 4.2 Conclusion and logic

**Unit tier (B2)**

1. **Validity.** The tier ran as written: the B2b values, the B2c ±1 requests, and minFree held at 0 (`minFreeBytes=0` printed in each series). [observed: `run1/unit/readings.txt`] The build and the code under test pass the upstream known answer. [observed: `run1/unit/TEST-org.apache.cassandra.db.DirectoriesTest.xml`] Valid.
2. **Readings.** Nothing unusual. 56/56 checks OK. [observed: `run1/unit/readings.txt`]
3. **Matched rows (B2g).**
   - "`getAvailableSpaceForCompactions` equals `round(usableSpace*pct)` for all four values": met at both usable values. [observed: `readings.txt`]
   - "`hasDiskSpace…(expected-1)==true` and `(expected+1)==false` for every pct>0": met. The pct=0 case also holds as B2f specifies (0 → true, 1 → false). [observed: `readings.txt`]
   - The B2h control scales linearly at usable 1e7. [observed: `readings.txt`]
4. **Excluded rows.**
   - "flat across pct": excluded, the budget takes 4 distinct values.
   - "returns true above expected": excluded, false in 8/8 cases.
   - "log line inconsistent": excluded, the DEBUG budget equals expected in 16/16 lines and the WARN in 8/8. [observed: `readings.txt`]
5. **Observed vs. inferred.** None of the unit conclusions rests on an inferred statement.
6. **Deviations and gaps.** The test is my implementation of B2e step 2 (one method looping over both usable values). It contains no negative control of its own, so its mismatch path was not exercised. The upstream known answer covers the code under test. The `FakeFileStore` reads no real disk (stated in B2d).
7. **Core question.** In-process, the compaction/stream budget is exactly `round((usable − minFree) × pct)`, and the gate admits a request at budget − 1 and rejects one at budget + 1, for every pct, including the default 0.95. Within this check, the knob proportionally sets the cap.

**Conclusion (unit):** B2g rows 1 and 3 — **confirmed**.

**Cluster tier (B3)**

1. **Validity.** Both runs held the B3b/B3h settings fixed except the knob:
   - The same 14 load chunks, with the same `du` within 0.02 %. [observed: both `run.log.excerpt`]
   - `min_free_space_per_drive=10MiB`, `skip_stream_disk_space_check=false`, autocompaction `not running`, and the per-table space check not disabled. [observed: same]
   - The disk instrument passed its known answer. [observed: `KNOWN_ANSWER`]
   - The limit was reached at both values: the first request (≈1.596 GB) exceeded the logged budget. [observed: `debug.log.grep`]
   - Valid, with the deviations R1–R4.
2. **Readings.**
   - The design's discriminating assumption did not hold: pct=1.0 also failed the check (11 times). [observed: `pct1.0.debug.log.grep`]
   - The budgets are exactly (free − 10 MiB) × pct at both moments read, before the load and at compaction. [observed: both `debug.log.grep`; arithmetic in §4.1]
   - The pct=0.5 peak sample under-reads the true peak: a 6 s compaction with 2 s sampling. The output size (113,887,785 B) bounds it. [observed: `pct0.5.sample-disk.window.txt`, compactionhistory in `pct0.5.run.log.excerpt`]
3. **Matched row.** No B3g row fits the comparison of the two knob values. The README's "No §9a row fits" applies (feedback to stage 3; the short file is not amended).
   - Part of B3g row 1 holds: "pct=0.5 run shows 'Not enough space'/'Reducing scope' in log". [observed: `pct0.5.debug.log.grep`: 13 + 13 lines]
   - Its second part, "pct=1.0 run does not", is contradicted: 11 + 11 lines at pct=1.0. [observed: `pct1.0.debug.log.grep`]
   - B3g row 4, "Memtable flush (before any compaction) grows the data dir past the pct-based budget while compaction is still disabled", is met. With autocompaction disabled, flushes alone grew the data dir to 1,724,982,767 B (1645 MiB) at pct=0.5. That is past the design's ~1019 MiB "pct-based budget". It is also past the budget the node itself computed before the load, 1,068,052,480 B. [observed: `pct0.5.run.log.excerpt` LOAD lines; `pct0.5.debug.log.grep`]
   - B3f per value: the pct=0.5 prediction holds in every part.
     - ≥1 WARN (13).
     - Partial compaction leaving originals unmerged (1 of 14 compacted).
     - Growth from this compaction ≤ ~1019 MiB (≤ 113.9 MB output).
   - The pct=1.0 prediction is **refuted** in every part. It predicted "completes; no 'Not enough space'/'Reducing scope' lines; peak ≈ 2×1.5 GiB… settling to ≈1.5 GiB"; the run showed 11 WARNs, 11 sstables dropped, and only 3 of 14 compacted. The peak growth was 0.35 GB, not ~1.5 GiB.
4. **Excluded rows.**
   - Row 2, "Both runs behave identically (no warnings either way)": excluded. Both warn, and the runs differ: 3 vs. 1 sstables compacted, 11 vs. 13 dropped, 342 MB vs. 114 MB written. [observed: both `run.log.excerpt`]
   - Row 3, "pct=0.5 aborts/reduces but disk usage still grows past ~1019 MiB from this compaction": excluded. The growth is ≤ 113.9 MB (output size) and ≤ 94.5 MB sampled. [observed: `pct0.5.sample-disk.window.txt`]
   - The B3f sentence ("pct=0.5 completing the full compaction identically to pct=1.0, with no log warnings… would contradict"): not triggered. Neither run completed the full compaction.
5. **Observed vs. inferred.** The verdict depends on these inferred statements:
   - (a) The pct=1.0 failure follows from the design's workload arithmetic, not from a fault in the knob. [inferred: the logged budget equals (free − 10 MiB) × 1.0 exactly, which matches `Directories.java:563-569` as cited in A3.1, and free space after the 1.6 GiB load was 0.42 GB]
   - (b) The difference in compaction depth between the runs is caused by the knob. [inferred: identical data and config otherwise, and logged budgets in a ratio of exactly 0.5]
   - (c) The pct=0.5 growth is bounded by its output size. [inferred: the sampling interval exceeds part of the write]
6. **Deviations and gaps.**
   - tmpfs instead of loop-mounted ext4 (R1). No ext4 reserved blocks, and RAM-speed writes.
   - The load is ~1.6 GiB, not ~1.5 GiB (R4). That makes no difference to D2: at 1.5 GiB, free would still be ~0.5 GiB < 1.5 GiB.
   - One run per value: B3h's optional repeat was not done.
   - The streaming path (A3.5) was not exercised by B3.
   - The pct=0.5 peak is under-sampled.
7. **Core question.** Usage followed the constraint.
   - The budget the node computed halved exactly with the knob, at both times read (part 2). [observed]
   - Each compaction was cut until its expected write fit that budget, and its measured disk growth stayed within it: 352 MB ≤ 411 MB, and ≤ 114 MB ≤ 206 MB (parts 3–4). [observed]
   - Flush-driven growth ignored the knob (row 4).
   - So the knob caps compaction-driven disk growth at pct × (free − min_free) measured at check time, not at pct × capacity. The design's cluster prediction assumed the latter, so its pct=1.0 row and the discriminating B3g row do not hold.

**Conclusion (cluster):** no B3g row fits the knob comparison. B3f's pct=1.0 row is **refuted** (design arithmetic, D2); its pct=0.5 row holds; B3g row 4 (flush overshoot) is **confirmed**. Overall: **not confirmed** as the design states it.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

| Part | Holds? (yes / no) | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | I re-read `pct1.0.run.log.excerpt` and `pct0.5.run.log.excerpt`: the `KNOWN_ANSWER`, the Node configuration values, `not running` twice each, `LOAD chunk=14`, `LOAD_DONE nchunks=14`, `NODE_STOPPED none left`. For the unit tier, `readings.txt` has `minFreeBytes=0` twice, and the DirectoriesTest xml has tests=42, errors=0, failures=0. |
| 2. Readings | yes | Re-read both `debug.log.grep`: budgets 2136104960 / 1068052480 before the load, and 411447296 / 205625344 at compaction. The arithmetic checks: 421,933,056 − 10,485,760 = 411,447,296, and (421,736,448 − 10,485,760)/2 = 205,625,344. |
| 3. Matched row | yes | WARN counts re-counted: 11 at `Directories.java:553` and 11 at `CompactionTask.java:446` (pct 1.0); 13 and 13 (pct 0.5). Compacted lines: "3 sstables" and "1 sstables". Row 4: the LOAD line `du_data=1724982767` comes before `COMPACT_START`. |
| 4. Excluded rows | yes | Window samples re-read: max growth 351,879,483 (1.0) and 94,503,227 (0.5). compactionhistory: bytes_out 342,920,882 and 113,887,785. |
| 5. Observed vs. inferred | yes | (a)–(c) are tagged inferred. (a) and (b) rest on budgets logged by the node, not on my own arithmetic only. |
| 6. Deviations and gaps | yes | R1–R5, H1–H2 and the under-sampled peak are listed. None of them changes which row matches. |
| 7. Core question | yes | The steps run from logged budget, to gate decision (WARN/reduce), to measured growth within the budget, which answers "does it cap, does it follow". The answer differs from the design's capacity-based framing, and the conclusion says so instead of claiming confirmation. |

### 5.2 Run 2?

**No** (2026-10-08). The unit result is exact and observed. The cluster conclusion rests on budgets the node logged itself, and the refutation of B3f's pct=1.0 row follows from the source formula, independent of timing. A repeat would not change the matched rows. The README's run 2 is out of scope for this executor in any case.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

| Tier | Verdict (B2g / B3g row) | Basis | Date |
|---|---|---|---|
| Unit | **Confirmed.** B2g row 1 ("`getAvailableSpaceForCompactions` equals `round(usableSpace*pct)` for all four values") and row 3 ("`(expected-1)==true` and `(expected+1)==false` for every pct>0"); B2f matched in all 16 cells, B2h linear. | run 1 + self-check | 2026-10-08 |
| Cluster | **Not confirmed: no B3g row fits the knob comparison.** B3f pct=1.0 is refuted (11 "Not enough space"/"Reducing scope" WARNs, 3/14 sstables compacted), because the budget is pct × (free − min_free) at check time, not pct × capacity as B3c assumed. B3f pct=0.5 holds. B3g row 4 (flush grows the data dir past the pct budget) is confirmed. Measured: the node's budget halved exactly with the knob, and compaction growth stayed within it at both values. | run 1 + self-check | 2026-10-08 |

**Feedback filed:** none in the solution (short path: never amended). For stage 3, recorded here only: recommendations 1–4 in §1.1. The main one: B3's budget arithmetic should use free space at check time.
