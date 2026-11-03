# repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous — stage-4 results  <!-- file: results/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.md -->

> **Case:** [`repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous`](../../stage3-ai-deep-read/cases/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous.md)
>
> **Status:** verdict filed, 2026-10-27. **Unit: Confirmed — caps** (run 1; closed, not re-run). **Cluster: Confirmed — caps (per tree)**
> (cluster re-run "run 1b" of 2026-10-27 at the re-frozen version `7384672a…0ea2`, after the user-authorised amendment of B3d, B3e,
> B3f (v) and B3g; §7, §8). The run-1 cluster verdict below (Not confirmed) stays on record as filed.
>
> **Outcome class:** true positive — the stage-3 estimate (`positive`) against the effect found in §8 ([definition](../README.md#outcome-class)); filed 2026-11-03 when the advisor's results were merged, from the final tier verdicts in §8.
>
> **Provenance:** advisor-run (the advisor's machine, [`environment-advisor.md`](../environment-advisor.md)); merged into this repository on 2026-11-03. The raw run folders cited as evidence (`run1/`, `run2/`: logs, samples, leak dumps) are held by the advisor and are not part of this repository; the harness is under [`harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/`](../harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/).
>
> **Run-1 status (as filed 2026-10-26):** verdict filed, 2026-10-26. **Unit: Confirmed — caps. Cluster: Not confirmed — caps (per tree).**
>
> **Agent:** autonomous. "§9a" below means each tier's predictions and conclusions table: B2f and B2g (unit), B3f and B3g
> (cluster); "§9b–§9e" means B2a–B2e or B3a–B3e; the case file's feedback section is its section D.
>
> **Session:** Claude Opus 5.5 (claude-opus-5-5), Claude Code, 2026-10-25/26, on the advisor's machine (`environment-advisor.md`).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | Filed as sha256 `f5349cd1…e52a` (DD batch 4). Frozen after the step-0 audit's fourteen amendments (2026-10-25): sha256 **`757c14a4bfd7595081356f9b096a0777074d5221b4714c9e504519c1bed3243e`**. One runbook fix during run 1 (defect 1, B2e, the unit output's location; §9a unchanged) gave **`258b36ffdc413dbf9491ba42ab942a10882eeec051b691a1c1374ee1ff32c9fa`**, at which both tiers' run 1 ran. Both are new rows in `_INDEX-advisor.md` §2. Nothing is committed (no commit was asked for). |
| **Harness** | [`../harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/`](../harness/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/): `TreeDepthSetterTest.java` (B2e's skeleton verbatim plus B2e's imports), `unit-run.sh`; `Jmx.java` (B3b verbatim), `make-node-conf.sh` (copied from the startup-path case's harness, two nodes), `cluster-run.sh`. Not committed. Instrument checks: (i) the test class compiled in the run clone at the audit (`ant build-test`, `BUILD SUCCESSFUL`, `$W/logs/…/audit-compile.log`); (ii) a cluster shakedown with 30,000 partitions ran every step: ring, stress, compaction wait, `set 9`, four labels with set/read-back, 4 `Allocating` lines per repair (2^14 leaves there, buffer 1,343,520 = 82·2^14 + 32), `Prepared`/`Created` lines, poller, histograms, cleanup ([`shakedown/summary.txt`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/shakedown/summary.txt)). Its readings are not used (data term 14; 1.6 s repairs left no histogram sample with tree objects and no visible direct rise). |
| **Tiers and values** | Unit (B2): setter values 9, 0 (rejection), 21, 30 (warning), 10, 14, 18, 20 (trees built at 1024 MiB), control 18 at 1 MiB; three runs. Cluster (B3): two nodes (127.0.0.1, .2), RF 2, 2,500,000 partitions, `repair_session_space: 1024MiB`; 9 (rejection), then 10, 16, 20 (= the default), 16 again, set over JMX on both nodes. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-25. |

### 1.1 Design audit

Citations re-read in `~/cassandra-src` at `cassandra-5.0.9` (`b5f2a54210`), the commit of both run clones. Every term the
predictions depend on was computed at the audit from the built clone by [`audit/Depth.java`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/audit/Depth.java)
(it repeats `ValidationManager.java:62-79`, int arithmetic included), before any reading ([`audit/audit-depth.txt`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/audit/audit-depth.txt)).

**When a set value takes effect (derived from the source).** The setter (`DatabaseDescriptor.java:4075-4084`) writes the volatile
`conf.repair_session_max_tree_depth` (`Config.java:206`); its only reader on the repair path is `ValidationManager.java:76`, inside
`createMerkleTrees`, which runs once per validation in `doValidation` (`:127`) after the validation iterator is opened and before
`Validator.prepare` → `trees.init()` (`Validator.java:117-124`). A set therefore governs every validation whose `createMerkleTrees` runs
after it, on that node only (the value is not propagated). An in-flight repair keeps the tree size of any validation already past `:127`
(the `MerkleTree` objects are sized then, `MerkleTree.java:139-147`); validations of the same repair that have not yet reached `:127`
(another table, a later session, a replica whose request is still queued) use the new value. The coordinator's off-heap copies take the
size of the trees they receive (`MerkleTree.java:714`, `:782`). No restart is needed. The runbook sets before each repair, so each
repair's trees all use the value set.

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: leaves per Merkle tree (2^d), on heap on the replicas and off heap on the coordinator, each with a fixed byte size. |
| A. Core question | knob varied, ≥ 3 values incl. default | Met | B2b: 10, 14, 18, 20; B3b: 10, 16, 20 (20 = the default) plus a repeat. |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | Unit: Runtime heap delta (GC noise named). Cluster: off-heap buffer sizes from the allocating code's own log line, the direct pool, live-histogram leaf counts. Shallow counts only; named. |
| A. Core question | usage driven to the limit and past it | Met (after B2c/B3c amendments) | Space and data terms computed: unit space 22 at 1024 MiB, data 22; cluster space 20 at 1024 MiB (ratio 0.45–0.55), data 21. At d = 20 in the cluster both the entry and the space term are 20. |
| B. Logic | each step says what it establishes | Partly | Implied by B2g/B3g; left for stage 3. |
| B. Logic | prediction stated in numbers or a clear relation | Partly → Met after amendment | B3f's buffer formula is wrong by the source (82 B low) and its line count ("≥ 2", n2 only) misses the local trees, which are moved off heap too; B2f's control was a range; B3f's direct band had an upper side that other direct users can break. Amended (B2f, B3f). |
| B. Logic | every plausible outcome has a conclusions row | Not met → Met after amendment | Missing: heap reading failing while sizes follow, rejection with value changed, warning count wrong, control off, runs disagree, line count, formula constant, read-back, data term, repeat, repair failure, silent instrument. Added (B2g, B3g). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Partly → Met after amendment | Row 1 of each tier now requires the exact sizes and the rejection of 9 (and 0) with the value unchanged. |
| B. Logic | alternative explanations and their controls | Partly | Unit space-binding control (B2h). Cluster: space read back per value (B3b amendment), compaction disabled (B3c amendment); no cluster space-binding control (left for stage 3). |
| C. Specific | a human can follow it from the intro and §9a | Met | Estimate, A3, B1, tables. |
| C. Specific | an AI can run §9b–§9e without re-deriving the code path | Partly → Met after amendment | Sampling interval, line count, where to read S, ring details open. |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly → Met after amendment | B3c's fallback "raise to 2048MiB" cannot work: `getRepairSessionSpaceInMiB() * 1048576` is an int product (`ValidationManager.java:62`), 2048 MiB overflows, `rangeAvailableBytes` = 1 and the space term = 1 (computed). Bounds, compaction, the 3 s sampler. Amended (B3b–B3e). |
| D. Runnable | harness and environment prerequisites exist or are listed | Met | Mapped to this host (B2a, B3a amendments): one clone per node, `127.0.0.2` present. |
| D. Runnable | workload arithmetic reaches the limit | Met | Unit d = 20 tree ≈ 110 MB in a 1 GiB JVM. Cluster ≈ 620 MB live per node, 2 × 4 GiB heaps on 32 GiB, ≈ 85 s stress. |
| D. Runnable | load-bearing citations spot-checked against the pinned clone | Met | `DatabaseDescriptor.java:596-607`, `:4070-4101`; `StorageService.java:4979-5014`; `StorageServiceMBean.java:481-494`; `ValidationManager.java:54-89`, `:127`; `Validator.java:117-158`, `:280-307`; `MerkleTree.java:139-147`, `:682-802`, `:1160-1163`, `:1451-1457`, `:1520-1541`; `Murmur3Partitioner.java:52`, `:269-271`; `RepairJob.java:306-358`. All match. |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| 1 | B2a: this host's clone and runner; Murmur3 from `CQLTester.java:418` | Amendment 2026-10-25 (uncommitted) | CloudLab path. |
| 2 | B2c: space terms 22 / 12 and data term 22 computed | Amendment 2026-10-25 | Estimate only. |
| 3 | B2d: warning text and where readings are read | Amendment 2026-10-25 | Open. |
| 4 | B2f: control 4,096 exactly; one warning each for 21 and 30; getter 20 after rejections; per-run rule | Amendment 2026-10-25 | Range; counts open. |
| 5 | B2g: row 1's requirements; six rows added | Amendment 2026-10-25 | Group B. |
| 6 | B3a: this host's two-node ring, clones, heaps, ports | Amendment 2026-10-25 | CloudLab paths. |
| 7 | B3b: Jmx.java in source mode; read-backs incl. `RepairSessionSpaceInMiB` | Amendment 2026-10-25 | Space term must be shown constant. |
| 8 | B3c: space 20 at 1024 MiB, no raise; **2048MiB fallback overflows** (use ≤ 2047MiB); compaction wait and `disableautocompaction`; data term; bounds | Amendment 2026-10-25 | Source. |
| 9 | B3d: 4 allocation lines per repair (local trees moved off heap, `Validator.java:295-300`); 1 s `jcmd` histograms; `Prepared`/`Created` lines by byte offset; poller baseline | Amendment 2026-10-25 | Source; 3 s can miss a validation. |
| 10 | B3e: run order, bounds, shakedown | Amendment 2026-10-25 | Open. |
| 11 | B3f: buffer = 82·2^d + 32 (84,000 / 5,373,984 / 85,983,264); 4 lines; S = 2·2^d; Lmax band; direct ≥ 0.95 × 4 × buffer at d = 16, 20; repeat; rejection | Amendment 2026-10-25 | Formula and count wrong by the source. |
| 12 | B3g: row 1's requirements; nine rows added | Amendment 2026-10-25 | Group B. |
| 13 | B3h, B4: controls' evidence; this host's paths | Amendment 2026-10-25 | Open. |
| 14 | Test what an in-flight repair uses (a set between two tables' validations of one repair) | Left for stage 3 | Not in B1. |
| 15 | A cluster space-binding control, and a set > 20 on the cluster | Left for stage 3 | Not needed for B3g. |
| 16 | Report `repair_session_space` ≥ 2048 MiB collapsing trees to depth 1 (int overflow at `ValidationManager.java:62`) as a finding on that constraint | Left for stage 3 (section D) | Different constraint. |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-25 (audit 23:40–23:48; unit attempt 0 23:50; unit run 1 23:52–23:53; shakedown 23:53–23:55) to 2026-10-26 00:00 EDT (cluster run 1 23:56–00:00) |
| Node | `yangwang-mbp` (the advisor's laptop), single host; not CloudLab |
| OS and kernel | macOS 27.0.1 (26A434), Darwin 27.0.0 arm64; 10 cores, 32 GiB RAM; internal SSD (APFS), 138 GiB free at start (137 GiB at the shakedown); loopback 127.0.0.1, .2, .3 on `lo0` (checked at start and by the harness); ports 7000, 7199, 7200, 7299, 7399, 9042, 9091 free; no `CassandraDaemon` before |
| JDK | OpenJDK 11.0.32.1 (Homebrew, arm64). Unit JVM: junit fork (1 GiB). Nodes: `MAX_HEAP_SIZE=4G HEAP_NEWSIZE=800M` (`-Xms4G -Xmx4G` in `JVM Arguments`), shipped `jvm-server.options` |
| Ant | 1.10.18 |
| Local `cassandra-src` clone commit | `b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`): unit and n1 `$W/cassandra-run24` (`ant -Dlocal.repository=$W/m2 build-test`, 49 s), n2 `$W/cassandra-run24-n2` (`ant jar`, 51 s); `W=~/Library/Caches/stage4` |
| Case-file commit / harness commit | uncommitted (sha256 in §1) |
| Storage for node data | local SSD, `$W/node-rsmtds/{n1,n2}` (617 MB live per node), wiped before and after; JMX 7199 / 7200 |
| Full logs (path, outside the repo) | `~/Library/Caches/stage4/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/` — `clone.log`, `build-test-run24.log`, `jar-run24-n2.log`, `audit-compile.log`, `audit-depth.txt`, `unit-attempt0-r{1,2,3}/`, `unit-r{1,2,3}/` (ant log, JUnit XML, test log), `cluster-shake/`, `cluster-run1/` (`commands.log`, `summary.txt`, `stress.log`, `set9-n1.txt`, `get-n2.txt`, `n{1,2}/` node logs — `debug.log` rolled at local midnight into `debug.log.2026-10-25.0.zip`, which holds the repair lines — and per label `hist/*.txt`, `samples.csv`, `n1-direct.csv`, `repair.log`, `n*-set.txt`, `n*-debug-segment.log`, `n*-alloc.txt`, `n*-prepared.txt`, `n*-created.txt`) |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| 1 | 1 (unit, attempt 0) | B2e "Output is in `build/test/output/TEST-….xml`" | The unit JVM routes `System.out` to the logger (`test/conf/logback-test.xml`): the XML's system-out was empty and the printed lines were in the test log, each `printf` split into one line per format piece. The harness's reading file came out empty (`run1/unit/attempt0/`). | Read the lines from `build/test/logs/**/TEST-…TreeDepthSetterTest.log`, joining the pieces; dated runbook fix in B2e. B2f–B2h unchanged. The unit tier restarted from its beginning (r1–r3 below); the self-check's unit reader was changed to read the test log (§5). | 2026-10-25 | sha256 `258b36ff…32c9fa` |

Re-freeze after run 1 (R1, a case-file amendment authorised by the user) and harness changes for the cluster re-run (added 2026-10-27 by the cluster re-run session):

| # | Run | Step | Problem | Fix | Decision (date) | Case-file version with the fix |
|---|---|---|---|---|---|---|
| R1 | cluster run 1 (reading, not a runbook defect) | B3f (v) / B3b's poller | B3f (v)'s direct-pool bound failed at d = 16 and its repeat: the 200 ms poller sampled on both sides of the ≈ 12 ms interval in which the four buffers coexist (2 of 4 buffers seen); the tier was Not confirmed (§4.2) | **Re-freeze, authorised by the user (Yang, the advisor) on 2026-10-27:** four dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` — B3d (an observe-only Byteman rule file `rsmtd.btm` on n1 at the exit of `MerkleTree.allocate` and the entry of `MerkleTree$OffHeapNode.release`: an atomic running total of tree bytes `mt` and the direct pool's `MemoryUsed` read at each event; derived from `MerkleTree.java:747-754,985-991`, `RepairJob.java:310-357`, `FileUtils.java:362-380` and the JDK 11 `DirectByteBuffer`/`Bits`/`ManagementFactoryHelper` bytecode), B3e (TestScript, agent check, fresh clones, shakedown first), B3f (v′) (the frozen bound 0.95 × 4 × buffer and its baseline kept, the peak read at the events; (v-a) added: 4 allocations before the first release, `mt` peak exactly 4 × buffer, back at start after 4 releases) and B3g (row 1 read with (v′); four rows added). New sha256 `7384672a…0ea2` as a new row in `_INDEX-advisor.md` §2. The whole cluster tier was re-run from its beginning in fresh clones (§7). B1, B3f (i)–(iv), (vi), (vii), B3h and the unit tier unchanged | user, 2026-10-27 | sha256 `7384672a…0ea2` (uncommitted; no commit asked for) |
| H1 | cluster re-run | B3a/B3e paths | `cluster-run.sh` and `make-node-conf.sh` fixed run 1's clones (`cassandra-run24`, `-n2`) and node root (`$W/node-rsmtds`) | Both read `RSMTD_C1`, `RSMTD_C2`, `RSMTD_NODE`; the defaults reproduce run 1 | AI, 2026-10-27 | n/a (harness) |
| H2 | cluster re-run | B3d, B3e (amended) | run 1's harness had no event-tied instrument | New `rsmtd.btm` (the B3d amendment's two rules, nothing else). `cluster-run.sh` with `RSMTD_BM=1`: TestScript of `rsmtd.btm` against the n1 clone (abort on error), n1 started with `JVM_EXTRA_OPTS=-javaagent:…byteman-4.0.20.jar=script:rsmtd.btm,boot:…`, a `BM-AGENT` check after start, per label `n1-rsmtd.txt` (the `RSMTD` lines written after the label's `node.out` offset) and an `EVENT` summary line. With `RSMTD_BM` unset the script behaves as in run 1. sha256 prefixes: `cluster-run.sh` `571938d1` (run 1) → `c9eb0235`; `make-node-conf.sh` `15940fd7` → `153d6f84`; `Jmx.java` `dcaa8d23` (unchanged); `rsmtd.btm` `999afb7a` (new) | AI, 2026-10-27 | n/a (harness) |
| H3 | cluster re-run | self-check | `run1/selfcheck.py` checks run 1's (v) and the closed unit tier | `run1b-cluster/selfcheck.py`: the cluster part of `run1/selfcheck.py`, unchanged under `--relations run1`, with (v′) and the instrument checks under `--relations amended`, a `--shake N` mode for the shakedown, and a read of the `RepairSessionSpaceInMiB` read-back from the summary's KNOB lines. `run1/selfcheck.py` unchanged | AI, 2026-10-27 | n/a (harness) |

## 4. Run 1

**Scope:** both tiers, all values in §1. **Command logs:** [`run1/unit/`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1/unit/) (`r1`–`r3`: `commands.log`, `summary.txt`, `stdout.txt`, `test-log-lines.txt`, `junit-testsuite.txt`; `attempt0/`); [`run1/cluster/`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1/cluster/) (`commands.log`, `summary.txt`, `stress-results.txt`, `set9-n1.txt`, `get-n2.txt`; per label `n1-alloc.txt`, `n*-prepared.txt`, `n*-created.txt`, `samples.csv`, `n1-direct.csv`, `n1-timeline.txt`, `repair.log`, `n*-set.txt`).

### 4.1 Readings

**Unit tier** (Murmur3, RF 1, one full-ring range reported with 2^22 partitions; JUnit 1 test, 0 failures, 0 errors in each run)

| Test or assertion | r1 | r2 | r3 | Predicted | Evidence |
|---|---|---|---|---|---|
| set 9 / set 0 | `REJECTED 9`, getter 20; `REJECTED 0`, getter 20 | same | same | rejected, getter 20 | `run1/unit/r*/stdout.txt` |
| set 21 / set 30 | getter 21 / 30; one WARN each `repair_session_max_tree_depth of 21 > 20 could lead to excessive memory usage` (and 30); 2 such lines in total | same | same | accepted, one warning each | `test-log-lines.txt` |
| size at d = 10 · 14 · 18 · 20 (1024 MiB) | 1,024 · 16,384 · 262,144 · 1,048,576 | same | same | 2^d | `stdout.txt` |
| heapDelta d = 18 / d = 20 (B) | 27,263,336 / 109,053,632 | 26,871,120 / 109,052,064 | 27,263,336 / 109,050,896 | — | `stdout.txt` |
| heapDelta(20)/heapDelta(18) | 4.000 | 4.058 | 4.000 | [3.4, 4.6] | computed |
| heapDelta(20)/2^20 | 104.0 B | 104.0 B | 104.0 B | [80, 250] B | computed |
| heapDelta d = 10 · 14 | −2,038,328 · 1,706,208 | −2,263,768 · 1,707,664 | −2,252,968 · 1,707,784 | noise allowed (only size asserted) | `stdout.txt` |
| control 1 MiB, d = 18 | 4,096 | 4,096 | 4,096 | 4,096 | `stdout.txt` |

**Cluster tier** (stress 2,500,000 partitions, 0 errors, 29,281 op/s, 85 s; 5 sstables and 617 MB live per node after the compaction wait;
`Created 2 merkle trees … 2,500,352 / 2,500,224 partitions` on n1 / n2 at every label, so P/2 ≈ 1.25 M > 2^20 and the data term is 21;
`RepairSessionSpaceInMiB` read back 1024 on both nodes at every label; every repair exit 0, 10.7–13.1 s, `Repair completed successfully`)

| Value | Read-back n1 / n2 | n1 `Allocating` lines (bytes each) | predicted | S (`Prepared`) n1 / n2 | n2 Lmax (samples with leaves) | n1 direct rise (B) | bound | Evidence |
|---|---|---|---|---|---|---|---|---|
| set 9 on n1 | `REJECTED javax.management.RuntimeMBeanException: java.lang.IllegalArgumentException: Cannot set repair_session_max_tree_depth to 9 which is < 10, doing nothing`, `now 20`; n2 `now 20` | — | — | — | — | — | — | `set9-n1.txt`, `get-n2.txt` |
| 10 | 10 / 10 | 4 × **84,000** | 84,000 | 2,048 / 2,048 | **2,048** (7 of 13) | 169,024 | recorded only | `cluster/d10/` |
| 16 | 16 / 16 | 4 × **5,373,984** | 5,373,984 | 131,072 / 131,072 | **131,072** (7 of 12) | **10,748,480** | ≥ 20,421,139 | `cluster/d16/` |
| 20 (default) | 20 / 20 | 4 × **85,983,264** | 85,983,264 | 2,097,152 / 2,097,152 | **2,097,152** (7 of 13) | 383,471,706 | ≥ 326,736,403 | `cluster/d20/` |
| 16 (repeat) | 16 / 16 | 4 × **5,373,984** | 5,373,984 | 131,072 / 131,072 | **131,072** (7 of 13) | **10,747,968** | ≥ 20,421,139 | `cluster/d16r/` |

n2 logged no `Allocating` line at any value. n2 Lmax ratios ×64 (10 → 16) and ×16 (16 → 20). The d = 16 and repeat rises equal 2 buffers
(2 × 5,373,984 = 10,747,968) within 512 B. The d = 20 rise (383,471,706) is taken at the sample …163,270 epoch ms (03:59:23,270 UTC), before the fourth `Allocating` line (23,306): 3 buffers (257,949,792) plus 125,521,914 B of other direct memory.
Timeline on n1 (`n1-timeline.txt`): the first two buffers (n1's own trees) are allocated ≈ 1.3 s before the last two (n2's); at d = 16 the
fourth allocation is at 03:58:54,915 UTC and the trees are released with `Created 0 sync tasks based on 2 merkle tree responses` at
03:58:54,927 (12 ms later); the poller's samples are at …134,850 and …135,095 epoch ms, bracketing that window
(`d16/n1-direct.csv`). At d = 20 the four-buffer window is 03:59:23,306–23,402 (96 ms); no sample fell inside it either (samples at …163,270 and …163,481).

### 4.2 Conclusion and logic

**Unit tier**

1. **Validity** — three runs, each 1 test, 0 failures [observed: `run1/unit/r*/junit-testsuite.txt`, `summary.txt`]; the space term at 1024 MiB is 22 and the data term 22, so the entry is the smallest term for every swept d [inferred: audit computation, `audit/audit-depth.txt`; consistent with size = 2^d]. Valid.
2. **Readings** — heapDelta at d = 10 is negative and at d = 14 small, inside GC noise, as B2f allows; nothing else unusual [observed].
3. **Matched row** — B2g row 1, "`size` = 2^d for all d and heap ratio ≈ 4 — claim confirmed", with the amendment's requirements: sizes 1,024 · 16,384 · 262,144 · 1,048,576 in all three runs; heap ratio 4.000 / 4.058 / 4.000 in [3.4, 4.6]; 104.0 B per leaf in [80, 250]; 9 and 0 rejected, getter 20; 21 and 30 accepted with one warning each; control 4,096 [observed: `stdout.txt`, `test-log-lines.txt`].
4. **Excluded rows** — "size independent of d": ×16 per +4 [observed]. "9 or 0 accepted": `REJECTED` [observed]. "21/30 rejected": getter 21, 30 [observed]. "Control = 2^18": 4,096 [observed]. Added rows: heap criterion fails — none; getter changed after rejection — 20; warning count ≠ 1 — 1 each; control ≠ 4,096 — no; runs disagree — sizes identical, ratios within the band; compile/run failure — none (after the runbook fix) [observed].
5. **Observed vs. inferred** — the space and data terms (audit computation); the match does not need them beyond size = 2^d, which is observed.
6. **Deviations and gaps** — the readings are in the test log, not the XML (defect 1, fixed before the restart). heapDelta is a Runtime total, not a deep size of the tree.
7. **Core question** — through the JMX setter, the next tree built has exactly 2^d leaves and its heap grows 4.0× per +2 (104 B per leaf); values below 10 are refused and leave the value at 20; values above 20 are stored with one warning, so there is no upper cap.

**Conclusion (unit tier):** B2g row 1 — **confirmed**.

**Cluster tier**

1. **Validity** — stress wrote 2,500,000 partitions with 0 errors [observed: `cluster/stress-results.txt`]; both nodes read back each set value and 1024 MiB [observed: `d*/n*-set.txt`, `summary.txt` `KNOB`]; P/2 > 2^20 at every label [observed: `n*-created.txt`]; every repair succeeded [observed: `repair.log`]; two `UN` nodes with tokens −2^63 and 0 [observed: `summary.txt` `RING`, `YAML`]. Valid.
2. **Readings** — the direct-pool rise at d = 16 (and its repeat) is 2 buffers, not 4 [observed: `d16/n1-direct.csv`, `d16r/n1-direct.csv`]; the four buffers coexist for 12 ms between two poller samples 245 ms apart [observed: `d16/n1-timeline.txt` and the CSV timestamps].
3. **Matched row** — not row 1. Row 1 requires all of (i)–(vii) of the B3f amendment; (i)–(iv), (vi), (vii) hold exactly [observed: 4 × 84,000 / 5,373,984 / 85,983,264 = 82·2^d + 32; S = 2·2^d on both nodes; n2 Lmax = 2·2^d; repeat identical; 9 rejected, now 20], and (v) passes its number at d = 20 (383,471,706 ≥ 326,736,403; but that sample precedes the fourth buffer, so it is three buffers plus ≈ 125.5 MB of other direct memory, not four trees) and **fails at d = 16 and its repeat** (10,748,480 and 10,747,968 < 20,421,139) [observed]. The readings match the added B3g row **"Lines exact but the direct rise below the bound at d = 16 or 20 → Not confirmed for direct memory"**. That row's stated cause ("trees not held together as traced") is contradicted by the timeline: the four trees were held together, for 12 ms, and the 200 ms poller (B3b's own instrument) did not sample inside that window [observed: `n1-timeline.txt`, `n1-direct.csv`]. The frozen table has no row for "instrument interval longer than the holding window"; under the no-tuning rule the verdict stays the matched row, Not confirmed.
4. **Excluded rows** — "buffer size the same for all d": 84,000 → 5,373,984 → 85,983,264 [observed]. "d = 20 sizes match 2^19 or lower": 2^20 [observed]. "9 accepted": rejected [observed]. Added rows: formula constant off — none; line count ≠ 4 — 4 every time; Lmax outside band — none; read-back ≠ set — none; data term binds — P/2 ≈ 1.25 M; repeat differs — identical; repair/stress failure — none; no n2 sample with leaves — 7 per label [observed].
5. **Observed vs. inferred** — that the d = 16 shortfall is a sampling artifact rests on the log timestamps and the CSV timestamps, both observed; that the ≈ 125.5 MB above three buffers in the d = 20 peak sample is the internode receive buffer of n2's response is inferred (not needed; it only means the d = 20 pass of (v) does not show four trees either).
6. **Deviations and gaps** — (i) 1 s `jcmd` sampling instead of 3 s `jmap` (amendment, before the run). (ii) Two nodes on one host. (iii) At d = 20 the entry and the space term are both 20, so d = 20 does not separate them; 10 and 16 are bounded by the entry alone. (iv) Histograms count shallow leaf instances only.
7. **Core question** — every tree built after a JMX set follows it exactly: on the replica 2·2^d on-heap leaves, on the coordinator four off-heap buffers of 82·2^d + 32 bytes, ×64 then ×16 across 10 → 16 → 20; 9 is refused and the value stays 20. The entry caps the per-tree memory of the next validation. The frozen direct-pool bound failed at d = 16 only because the 200 ms poller missed a 12 ms window, so the cluster tier stays Not confirmed by its own table.

**Conclusion (cluster tier):** B3g added row "direct rise below the bound at d = 16" — **not confirmed** (every size, count and rejection reading as predicted).

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

[`run1/selfcheck.py`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1/selfcheck.py), written before
any reading, independent of the harness (it re-reads the JUnit XML, the raw unit test logs, each node's whole `debug.log` and its rolled
zip, assigning lines to labels by their own UTC timestamps; the raw `jcmd` histogram files; the raw poller CSVs; the raw Jmx outputs;
`repair.log`; `stress.log`): **117 checks, 2 failed** — exactly the d = 16 and repeat direct-rise bounds, matching §4.2
([`run1/selfcheck.out`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1/selfcheck.out)).
Changes after it was written, each only to read a file it missed: (a) 2026-10-25, after unit attempt 0, the unit lines are read from the
test log instead of the XML's system-out (defect 1); (b) 2026-10-26, after the cluster run, `debug.log.*` (the rolled zip) is read as well,
since `debug.log` rolled at local midnight. No check or bound was changed.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | Stress totals from `stress.log`; read-backs from the raw `n*-set.txt`; P from the raw `debug.log` zip; repair success; JUnit counts. |
| 2. Readings | yes | Direct rises re-derived from the raw CSVs: 10,748,480 / 383,471,706 / 10,747,968. |
| 3. Matched row | yes | Unit: all row-1 checks pass in r1–r3. Cluster: every size/count/S/Lmax/rejection check passes; only the two d = 16 direct checks fail → the added row, Not confirmed. |
| 4. Excluded rows | yes | 4 lines and none on n2 at every label; ×64/×16; repeat identical. |
| 5. Observed vs. inferred | yes | The sampling-artifact explanation is read from the timeline and the CSV timestamps; it does not change the matched row. |
| 6. Deviations and gaps | yes | Stated. |
| 7. Core question | yes | Setter → depth of the next validation's trees (exact, both tiers) → heap ×4 per +2 (unit), buffers and leaves ×64/×16 (cluster). |

### 5.2 Run 2?

**No** — decided 2026-10-26. The unit tier rests on exact readings; the cluster tier's failed part is explained by observed timestamps, and a
second run of the same frozen runbook would use the same 200 ms poller and cannot change the matched row. A re-run with a finer direct-pool
instrument would need a re-frozen B3f/B3b (user authorisation, as in the earlier re-runs on this branch).

## 6. Run 2 — fresh AI session (optional)

Not done (§5.2).

## 7. Cluster re-run ("run 1b") after the B3d, B3e, B3f (v), B3g amendment — 2026-10-27

Added by a stage-4 session, Claude Opus 5.5 (claude-opus-5-5), 2026-10-27, **authorised by the user (Yang, the advisor) on 2026-10-27**.
Sections 1–6 above are run 1 as filed and are not changed. Run 1's excerpts under `run1/` are untouched. The unit tier is closed and
was not re-run.

### 7.1 Frozen version and harness

| Field | Content |
|---|---|
| **Why** | Run 1's cluster tier was Not confirmed through one frozen relation, B3f (v), the direct-pool rise. It failed at d = 16 and its repeat because B3b's 200 ms poller sampled on both sides of the ≈ 12 ms interval in which the four buffers coexist (§4.1–§4.2). The instrument could not see the transient quantity. The README says a wrong §9a "is a dated amendment to the case file and the affected tier starts again". The user authorised an amendment and a re-run of the whole cluster tier on 2026-10-27. |
| **Amendment** | Four dated amendments `Amendment 2026-10-27 (after run 1, authorised by the user) — B3d / B3e / B3f (v) / B3g`, each next to the text it changes. Each says plainly that it follows run 1's readings.<br>**Instrument (B3d), from the source.** The coordinator's tree memory changes only at `MerkleTree.allocate` (`MerkleTree.java:747-754`, `allocateDirect` at `:751`; called for n1's own trees moved off heap, `Validator.java:293-305` → `MerkleTrees.java:373-377` → `MerkleTree.java:776-785`, and for n2's trees deserialized, `:707-730`, `:787-792`) and at `MerkleTree$OffHeapNode.release` (`:985-991`) → `FileUtils.clean` (`FileUtils.java:362-380`). Release is reached through `MerkleTree.release` (`:164-168`) and `MerkleTrees.release` (`MerkleTrees.java:148-150`) at `RepairJob.java:355`/`:357`, only after `MerkleTrees.difference` (`:310-318`). So the four buffers coexist from the fourth allocation to the first release. That interval is a differencing time, which the source does not bound from below, so no fixed-period poller is guaranteed to see it.<br>**What the pool counts, from the JDK 11.0.32.1 bytecode (`javap`).** `DirectByteBuffer(int)` reserves `cap` with `Bits.reserveMemory` before it returns; page alignment is off by default. `Bits.tryReserveMemory` adds the reservation to `RESERVED_MEMORY` and 1 to `COUNT`. `clean()` runs `DirectByteBuffer$Deallocator.run` synchronously (`Unsafe.freeMemory`, `Bits.unreserveMemory`). The JMX bean `java.nio:type=BufferPool,name=direct` wraps `SharedSecrets.getJavaNioAccess().getDirectBufferPool()`, whose `getMemoryUsed()` is `Bits.RESERVED_MEMORY` (`ManagementFactoryHelper.getBufferPoolMXBeans`, `Bits$1`).<br>**The rule.** `rsmtd.btm` (two observe-only rules on n1) prints, at each allocation exit and each release entry, the epoch ms, the capacity, an atomic running total `mt` (`incrementCounter`, ±cap) and the pool's `MemoryUsed`/`Count`.<br>**(v′).** The frozen bound is kept: peak − baseline ≥ 0.95 × 4 × buffer at d = 16, 20 (≥ 20,421,139 B, ≥ 326,736,403 B), baseline = the poller's pre-repair median as frozen. Only the peak changes: it is now the largest pool reading at the events. Added **(v-a)** at every label: 4 `alloc` + 4 `release` lines, each `cap` = 82·2^d + 32, all four allocations before the first release, `mt` peak = start + 4 × buffer (336,000 · 21,495,936 · 343,933,056 B), `mt` back at start after the fourth release, and the `alloc` count equal to the `Allocating` count.<br>**B3g.** Row 1 is read with (v′). Four rows are added: (v-b) fails → Not confirmed for direct memory; (v-a) fails → Not confirmed (not held or released as traced); instrument silent or faulty → Invalid for (v′); a low poller peak with (v′) holding → not a failure.<br>B1, B3f (i)–(iv), (vi), (vii), B3h and the unit tier are unchanged. |
| **What was known of run 1, and would run 1 pass** | **All of run 1's readings were known** when the amendment was written: 4 `Allocating` lines of 82·2^d + 32 B per repair; S = Lmax = 2·2^d; poller rises 10,748,480 / 10,747,968 B at d = 16 and its repeat (2 buffers) and 383,471,706 B at d = 20 (3 buffers plus other direct memory, a sample taken before the fourth allocation); four-buffer intervals of ≈ 12 ms and 96 ms from the log timestamps. The numbers of (v′) come from B3f (i) and the frozen 0.95 × 4 rule, not from these readings. **Run 1 would not pass.** Its raw files have no `RSMTD` lines, so under the amended relations it matches "instrument silent → Invalid for (v′)". The known-answer pass `run1b-cluster/selfcheck-known-answer-on-run1-relations-amended.out` gives 86 checks with 18 failed: TestScript and agent absent, and no event lines at any label. With its poller peak in place of the event peak, (v-b) still fails at d = 16 and the repeat. Run 1's log timeline (four `Allocating` lines before `Created 0 sync tasks`) was consistent with (v-a) but is not the counter. |
| **Case-file version** | sha256 **`7384672a82f6957c2c0532d1e4bf427a2993b281c5636098537b3ba239440ea2`**. It is a new row in `_INDEX-advisor.md` §2, "re-frozen after run 1 for cluster re-run (B3d, B3e, B3f (v), B3g), authorised by the user". The earlier rows (`f5349cd1…`, `757c14a4…`, `258b36ff…`) are kept. Hashed at 18:24:15 EDT, before any re-run command or reading (clone 18:24, shakedown 18:27:35, re-run 18:30:39). The same hash was recorded again at 18:30:38 in `run1b-cluster/harness-sha-run2.txt`. Section D was filled afterwards. Base commit `1ef2c33`; nothing committed. |
| **Harness** | Run 1's harness with changes H1 (paths), H2 (the Byteman instrument) and H3 (the self-check) only (§3).<br>sha256 prefixes at the re-run: `cluster-run.sh` `c9eb0235`, `make-node-conf.sh` `153d6f84`, `Jmx.java` `dcaa8d23` (unchanged, B3b verbatim), `rsmtd.btm` `999afb7a` (`run1b-cluster/harness-sha-run2.txt`).<br>Commands: `RSMTD_C1=$W/cassandra-run64 RSMTD_C2=$W/cassandra-run64-n2 RSMTD_NODE=$W/node-rsmtds2 RSMTD_BM=1 cluster-run.sh shake2 30000`, then the same with `run2` (n = 2,500,000).<br>Instrument checks: TestScript `Type checked rule "rsmtd alloc"`, `… "rsmtd release"`, `TestScript: no errors` (standalone and in each run, `cluster/testscript.txt`). In the shakedown, 4 + 4 `RSMTD` lines per label, `mt` 0 → 4 × buffer → 0, and `alloc` count = `Allocating` count. The shakedown self-check ran end to end: 88 checks, 0 failed, exit 0 (`run1b-cluster/shakedown/selfcheck.out`). |

### 7.2 Environment

Same host as run 1 (§2): `yangwang-mbp`, macOS 27.0.1 / Darwin 27.0.0 arm64, OpenJDK 11.0.32.1, Ant 1.10.18; loopback 127.0.0.1–.3 on `lo0`; free disk
116 GiB. Cluster re-run 2026-10-27: shakedown 18:27:35–18:29:52 EDT, re-run 18:30:39–18:35:15 EDT. Fresh clones from `~/cassandra-src` at
`b5f2a54210d541339c2e7c17a794195cac0e67c2` (tag `cassandra-5.0.9`), no local change: `$W/cassandra-run64` (`ant -Dlocal.repository=$W/m2 build-test`,
`BUILD SUCCESSFUL`, 53 s; n1, and the nodetool/stress/Byteman jar) and `$W/cassandra-run64-n2` (`ant … jar`, `BUILD SUCCESSFUL`, 52 s; n2)
(`run1b-cluster/clone-build-run64.txt`). Nodes `-Xms4G -Xmx4G`, `-XX:MaxDirectMemorySize=8192M` (cassandra-env default), n1 with the Byteman agent
(`run1b-cluster/cluster/n1-jvm-args-excerpt.txt`). Node data `$W/node-rsmtds2` (617.6 MB live per node), wiped before and after. Pre-checks and
final checks in `summary.txt`. Full logs (65 MB): `~/Library/Caches/stage4/logs/repair_session_max_tree_depth-setRepairSessionMaxTreeDepth/`:
`clone-run64.log`, `build-test-run64.log`, `jar-run64-n2.log`, `driver-shake2.out`, `cluster-shake2/`, `driver-run2.out`, `harness-sha-run2.txt`,
`cluster-run2/` (as run 1's `cluster-run1/`, plus `testscript.txt`, `n1/node.out` with the `RSMTD` lines, and per label `n1-rsmtd.txt`),
`selfcheck-known-answer-run1-relations-{run1,amended}.out`. Excerpts: [`run1b-cluster/`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1b-cluster/)
(`cluster/` with run 1's kinds of files plus `testscript.txt`, `n1-jvm-args-excerpt.txt` and per label `n1-rsmtd.txt`; `shakedown/`; `selfcheck.py`;
`selfcheck.out`; `selfcheck-rerun-under-run1-relations.out`; `selfcheck-known-answer-on-run1-relations-{run1,amended}.out`; `driver.out`;
`harness-sha-run2.txt`; `clone-build-run64.txt`).

### 7.3 Readings

From `run1b-cluster/cluster/summary.txt`, `d*/n1-rsmtd.txt`, `n1-alloc.txt`, `n*-prepared.txt`, `n*-created.txt`, `samples.csv`, `n1-direct.csv`,
`repair.log`, `n*-set.txt`; recomputed from the raw files by `selfcheck.py`. Stress 2,500,000 partitions, 0 errors, 26,417 op/s, 94 s; 5 SSTables
and 617.6 MB live per node after the compaction wait; `Created 2 merkle trees … 2,500,352 / 2,500,224 partitions` on n1 / n2 at every label
(P/2 > 2^20, data term 21); `RepairSessionSpaceInMiB` read back 1024 on both nodes at every label; every repair exit 0, 10.4–13.4 s, `Repair
completed successfully`; `set 9` on n1 → `REJECTED … Cannot set repair_session_max_tree_depth to 9 which is < 10, doing nothing`, `now 20`, n2 `now 20`;
`BM-AGENT n1 javaagent_in_jvm_args=1 agent_errors=0`; 32 `RSMTD` lines in all, none outside the four repairs.

| Value | Read-back n1 / n2 | `Allocating` lines on n1 (B) / on n2 | S n1 / n2 | n2 Lmax (samples with leaves) | (v-a) `alloc`/`release`, allocs before 1st release, `mt` start → peak → end | (v-b) event peak − baseline (B) | bound | poller rise (recorded) | 4th alloc → 1st release |
|---|---|---|---|---|---|---|---|---|---|
| 10 | 10 / 10 | 4 × **84,000** / 0 | 2,048 / 2,048 | **2,048** (6 of 12) | 4/4, 4, 0 → **336,000** → 0 | 51,352,235 − 51,015,467 = 336,768 | recorded only | 168,768 | 2 ms |
| 16 | 16 / 16 | 4 × **5,373,984** / 0 | 131,072 / 131,072 | **131,072** (6 of 12) | 4/4, 4, 0 → **21,495,936** → 0 | 80,802,785 − 51,016,235 = **29,786,550** | ≥ 20,421,139 | 8,290,998 | 31 ms |
| 20 (default) | 20 / 20 | 4 × **85,983,264** / 0 | 2,097,152 / 2,097,152 | **2,097,152** (7 of 13) | 4/4, 4, 0 → **343,933,056** → 0 | 529,410,889 − 59,122,374 = **470,288,515** | ≥ 326,736,403 | 468,385,923 | 102 ms |
| 16 (repeat) | 16 / 16 | 4 × **5,373,984** / 0 | 131,072 / 131,072 | **131,072** (7 of 12) | 4/4, 4, 0 → **21,495,936** → 0 | 198,282,057 − 176,786,121 = **21,495,936** | ≥ 20,421,139 | 384 | 2 ms |

Every `RSMTD` `cap` equals the label's buffer. All 16 `alloc` lines come from `AntiEntropyStage:1` and all 16 `release` lines from `RepairJobTask:3`. At d = 16 and the repeat,
the pool readings at the fourth `alloc` and at the first `release` are equal (80,802,785; 198,282,057). At d = 20 they are 529,410,889 and 520,719,177:
other direct memory fell by 8,691,712 B in the 102 ms between them. Pool composition at the fourth allocation (event peak − baseline − 4 × buffer):
+8,290,614 B at d = 16, at the third allocation the pool `Count` rose by 2 (131 → 133), i.e. one non-tree direct buffer besides the tree;
+126,355,459 B at d = 20; 0 B at the repeat. The poller's rise at d = 16 (8,290,998) is that non-tree memory, still held after the trees were released:
the poller again saw none of the four trees at d = 16, and at the repeat it saw a rise of 384 B. The baseline of the repeat (176.8 MB) is
117.7 MB above d = 20's (59.1 MB): direct memory kept after the d = 20 repair. n2 logged no `Allocating` line. n2 Lmax ratios: ×64 (10 → 16) and ×16 (16 → 20).

### 7.4 Cluster re-run — conclusion and logic

1. **Validity.**
   - The re-run used the re-frozen version (`7384672a…`, hashed at 18:24:15, before the first command) [observed: `_INDEX-advisor.md` §2; `harness-sha-run2.txt`; `commands.log` first line 18:30:39].
   - Every step of B3 ran from the beginning in the frozen order, in fresh clones, after a shakedown [observed: `summary.txt`, `shakedown/summary.txt`].
   - Stress wrote 2,500,000 partitions with 0 errors [observed: `stress-results.txt`].
   - Both nodes read back every set value and 1024 MiB; P/2 > 2^20 at every label; every repair succeeded; two `UN` nodes [observed].
   - The instrument was loaded and type-checked, with no agent error. The `alloc` count equals the `Allocating` count at every label [observed: `testscript.txt`, `n1-jvm-args-excerpt.txt`, `summary.txt` `BM-AGENT`, `n1-rsmtd.txt`].
   - Valid.
2. **Readings.** Every size, count and rejection reading repeats run 1's exactly. The event-tied pool peaks see all four buffers at every label. The 200 ms poller again misses them at d = 16 and the repeat (8,290,998 and 384 B). The four-buffer interval was 31 ms, 102 ms and 2 ms [observed: `n1-rsmtd.txt`, `n1-direct.csv`].
3. **Matched row.** B3g row 1, "Buffer sizes equal the formula for each d; leaf counts scale ×64 then ×16 → claim confirmed at node level", read with the 2026-10-25 and 2026-10-27 amendments. Each part [observed]:
   - (i) 4 × 84,000 / 5,373,984 / 85,983,264 B = 82·2^d + 32;
   - (ii) exactly 4 lines per repair on n1, none on n2;
   - (iii) S = 2·2^d on both nodes, `Created 2 merkle trees`;
   - (iv) n2 Lmax = 2·2^d, inside [2·2^d, 2·2^d + 16];
   - **(v-a)** 4 + 4 events with the right capacity, all allocations before the first release, `mt` 0 → 4 × buffer → 0 at all four labels;
   - **(v-b)** 29,786,550 ≥ 20,421,139 (d = 16), 470,288,515 ≥ 326,736,403 (d = 20), 21,495,936 ≥ 20,421,139 (repeat);
   - (vi) the repeat equals d16 in (i)–(iv);
   - (vii) 9 rejected, `now 20`.

   **Tier rule: Confirmed.**
4. **Excluded rows.**
   - "Buffer size the same for all d": ×64, ×16.
   - "d = 20 sizes match 2^19 or lower": 2^20.
   - "9 accepted": rejected.
   - Formula off by a constant: none. Line count ≠ 4: none. Lmax outside its band: none. Read-back ≠ the set value: none. Data term binds: P/2 ≈ 1.25 M. The repeat differs: no. Repair or stress failure: none. No n2 sample with leaves: 6–7 per label.
   - Added 2026-10-27: "(v-a) holds but (v-b) below": no. "(v-a) fails": no. "Instrument silent or faulty": no. "Poller below with (v′) holding": yes, at d = 16 and the repeat. This is recorded and is not a failure by its row.

   [observed]
5. **Observed vs. inferred.**
   - Observed: every relation, from the raw `node.out` lines and the raw CSV.
   - Inferred: that the non-tree +8.29 MB at d = 16 and +126 MB at d = 20 are internode buffers for n2's validation response, and that the 117.7 MB kept after d = 20 is pooled network memory. These are not needed: the bound is a lower bound, and at the repeat the rise is exactly 4 buffers with no other memory.
6. **Deviations and gaps.**
   - None against the re-frozen runbook.
   - The amendment was written knowing run 1's readings (stated in §7.1 and in the amendment). The bound and baseline are run 1's frozen ones; only the instrument that supplies the peak changed, and (v-a) was added.
   - The Byteman agent on n1 is observe-only but adds two prints per tree.
   - At d = 20 the entry and the space term are both 20 (as in run 1), so 10 and 16 are the values bounded by the entry alone.
   - Histograms count shallow leaf instances.
7. **Core question.**
   - Every tree built after a JMX set follows it exactly: 2·2^d on-heap leaves on the replica, and on the coordinator four off-heap buffers of 82·2^d + 32 B, ×64 then ×16.
   - The coordinator holds all four at once: 4 × buffer of direct memory, seen in the JVM's own direct pool at the moment they coexist. It frees all of them after differencing.
   - 9 is refused and the value stays 20.
   - The entry caps the per-tree memory of the next validation.

**Conclusion (one line):** B3g row 1 with the amended B3f (v′): confirmed.

### 7.5 Self-check of the cluster re-run — AI

`run1b-cluster/selfcheck.py` (H3) re-reads n1's whole `node.out`. It assigns the `RSMTD` lines to labels by their own epoch ms, not from the harness's
`n1-rsmtd.txt`. It also re-reads each node's whole `debug.log`, the raw `jcmd` histograms, the raw poller CSVs, the raw Jmx outputs, `repair.log`, `stress.log`,
`testscript.txt` and n1's `system.log`. `summary.txt` is used only for the repair windows, the KNOB space read-back and the final-process line. It was written
after the re-freeze and before any re-run reading, and was not changed after the shakedown or the re-run.
- **Pass 0 (shakedown, `--shake 30000`, run end to end first):** 88 checks, 0 failed, exit 0 (`run1b-cluster/shakedown/selfcheck.out`).
- **Pass 1 (re-run raw files, amended relations):** **97 checks, 97 hold, 0 fail**, exit 0 ([`run1b-cluster/selfcheck.out`](repair_session_max_tree_depth-setRepairSessionMaxTreeDepth-depth--autonomous/run1b-cluster/selfcheck.out)).
- **Pass 2 (known answer, run 1's raw files, run-1 relations):** 71 checks, 2 failed. These are exactly the d = 16 and repeat poller rises (10,748,480; 10,747,968). The 63 cluster lines it shares with `run1/selfcheck.out` are **identical**; the 8 extra lines are the KNOB space read-backs (all 1024) (`run1b-cluster/selfcheck-known-answer-on-run1-relations-run1.out`).
- **Pass 3 (run 1's raw files, amended relations):** 86 checks, 18 failed: no TestScript, no agent and no `RSMTD` lines at any label, so run 1 is in the "instrument silent → Invalid for (v′)" row. The script tells run 1 apart from the re-run (`…-relations-amended.out`).
- **Pass 4 (information, re-run raw files, run-1 relations):** 2 failed, the d = 16 and repeat poller rises (8,290,998; 384). The poller still cannot see the interval (`selfcheck-rerun-under-run1-relations.out`).

Raw files re-opened by hand: `cluster-run2/n1/node.out` (the d = 16 lines: `mt` 5,373,984 → 21,495,936, `used` 56,275,841 → 80,802,785, `count` 130 → 134); n1 `debug.log`
(the four `Allocating … 5373984` lines at 22:33:50,652–,738 UTC, 1 ms before each `RSMTD alloc` ms); `d16/n1-direct.csv` (samples at …430,609 and …430,820, on both sides of the four-buffer interval …430,739–…430,770);
`system.log` (`JVM Arguments` with the agent; the only `OutOfMemory` text is the `-XX:+HeapDumpOnOutOfMemoryError` flag; 0 `ERROR` lines on either node).

| Part | Holds? | Note |
|---|---|---|
| 1. Validity | yes | Re-frozen hash before the first command; read-backs, stress, P, repairs, instrument checks re-read. |
| 2. Readings | yes | Event peaks and `mt` recomputed from `node.out`; baselines and poller rises from the CSVs. |
| 3. Matched row | yes | Every (i)–(vii) and (v′) check passes at every label. |
| 4. Excluded rows | yes | |
| 5. Observed vs. inferred | yes | The non-tree memory is named and not needed for the bound. |
| 6. Deviations and gaps | yes | Non-blind amendment stated. |
| 7. Core question | yes | caps (per tree); usage follows d exactly; four trees held together and released. |

**Run 2?** No (2026-10-27). The re-run repeats every run-1 size and count exactly, and the amended relation rests on exact counter readings; a further run would not change the row.

### 7.6 Verdict of the cluster re-run

**Confirmed — caps (per tree)** (B3g row 1 with the amended B3f (v′)). It is filed in §8 as a new cluster row; the run-1 cluster row
(Not confirmed) is kept.

**End of the re-run:** no `CassandraDaemon`, `cassandra-stress`, `Jmx.java` or `jcmd` process; ports 7000/7199/7200/9042 free; `$W/node-rsmtds2`
removed; `$W/cassandra-run64` and `$W/cassandra-run64-n2` clean (`git status` 0 entries); no `cassandra.logdir_IS_UNDEFINED/` or log folder in the
repository (2026-10-27, after the self-check).

## 8. Verdict — AI

**Stage-3 estimate:** positive.

**Claim tested:** "When `repair_session_space` and the partition count allow deeper trees, each merkle tree built after a JMX
`setRepairSessionMaximumTreeDepth(d)` has exactly 2^d leaves, so tree memory scales with 2^d. Values < 10 are rejected and leave the setting
unchanged. Values > 20 are accepted, with only a warning." (B1)

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | **Confirmed** (row 1: size = 2^d at d = 10, 14, 18, 20 in three runs; heap ×4.00–4.06 per +2, 104 B per leaf; control 4,096; 9 and 0 rejected, value 20; 21 and 30 stored with one warning each) | caps | run 1 + self-check | 2026-10-26 |
| Cluster | **Not confirmed** (added row "direct rise below the bound at d = 16": 2 of 4 buffers seen by the 200 ms poller, the four coexisting for 12 ms; every other row-1 part exact — 4 × (82·2^d + 32) B on n1, S = Lmax = 2·2^d, repeat identical, 9 rejected) | caps (per tree) | run 1 + self-check | 2026-10-26 |
| Cluster (re-run at `7384672a…`, after the user-authorised B3d, B3e, B3f (v), B3g amendment) | **Confirmed** — B3g row 1 with the amended B3f (v′): 4 × (82·2^d + 32) B on n1 (84,000 · 5,373,984 · 85,983,264), none on n2; S = Lmax = 2·2^d; repeat identical; 9 rejected, `now 20`; (v-a) Byteman counter: 4 allocations before the first release and `mt` 0 → 4 × buffer → 0 at every label; (v-b) event-tied direct-pool peak − baseline 29,786,550 B (d = 16), 470,288,515 B (d = 20), 21,495,936 B (repeat) against ≥ 20,421,139 / 326,736,403 / 20,421,139 (the 200 ms poller again saw none of the four trees at d = 16: 8,290,998 B, recorded only) | caps (per tree): each tree after a JMX set has 2^d leaves; the coordinator holds RF × ranges = 4 off-heap trees of 82·2^d + 32 B at once, visible in the JVM direct pool, and frees them after differencing | cluster re-run (§7) + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D (uncommitted); the fourteen step-0 amendments and the B2e runbook fix are in the case file,
dated, with both sha256 values as new rows in `_INDEX-advisor.md` §2; `_INDEX-advisor.md` §1 Stage 4 column and the coverage line updated.
No section was amended for a refutation (none occurred).

**Feedback filed for the cluster re-run (2026-10-27):** the four amendments `Amendment 2026-10-27 (after run 1, authorised by the user)` in the
case file (B3d, B3e, B3f (v), B3g); a new `_INDEX-advisor.md` §2 row (`7384672a…`); the case file's section D (new entry); the §1 Stage 4 column
(run-1 text kept, re-run verdict appended). The coverage section is not touched (the case was already counted as closed). No refutation, so no
other case section is amended. Recommendation for stage 3: a bound on a transient quantity (here the four trees held from the last allocation to the
first release, 2–102 ms) needs an instrument at the allocation and release points; a periodic poller cannot see it.
