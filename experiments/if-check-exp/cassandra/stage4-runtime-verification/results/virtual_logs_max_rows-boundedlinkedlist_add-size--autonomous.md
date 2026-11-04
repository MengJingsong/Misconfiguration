# virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous — stage-4 results  <!-- file: results/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md -->

> **Case:** [`virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous`](../../stage3-ai-deep-read/cases/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous.md)
>
> **Status:** **Self-checked 2026-10-27 — unit Confirmed (caps), cluster Confirmed (caps) for the row count; two filed heap sub-predictions of the cluster tier missed (byte readings drowned by the memtable and GC noise of the workload); the case file's B3a (shipped logback.xml feeds the table) was wrong and is amended; no run 2**
>
> **Outcome class:** true positive — stage-3 estimate `positive` against the stage-4 effect `caps` ([definition](../README.md#outcome-class))
>
> **Agent:** autonomous (B2 = unit tier, B3 = cluster tier, feedback = section D).

## 1. Before run 1 — design audit and freeze

| Field | Content |
|---|---|
| **Case-file version** | sha256 of the whole file after the audit's amendments (U1-U5 in B2, C1-C7 in B3, all dated 2026-10-27): `ac361a2e3182237d0b0cd4b8de3eb35b7743803f6b85511a8a137aa57c2b7e71` (`sha256sum`, taken before the unit run and unchanged until section D was filled). The repository HEAD for this session is `6e6cf92`; the case file, harness and results are uncommitted in the working tree (this session does not commit). The frozen text is everything above section D. |
| **Harness** | [`harness/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous/`](../harness/virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous/README.md), uncommitted: `VirtualLogsMaxRowsProbeTest.java`, `unit-run.sh`, `unit-all.sh` (B2); `make-node.sh`, `cluster-run.sh`, `chain.sh`, `analyze.py`, `analyze-all.sh`, `selfcheck.py` (B3). **Instrument checks (not readings):** `javac` of the probe against the build; a shakedown of the unit probe at sizes 10 and 1000 (known answer: row count = min(adds, size), newest/oldest ids as arithmetic says; this also found the missing JDK 11 module flags, fixed in `unit-run.sh`); the upstream `LogMessagesTableTest` in the run copy (`ant testsome`, 6 run, 0 failures; `run1/unit/upstream-LogMessagesTableTest.summary`); three shakedown arms of `cluster-run.sh` (N = 1000, 2000 to 6000 stress operations) whose output was **seen before the freeze and is not a reading**: they found that `SELECT count(*)` returned 105 where the buffer held 726 messages (amendment C3) and that the CQL row listing and the instance count are different quantities; and `analyze.py` was run on the shakedown arm. |
| **Tiers and values** | Unit (B2): sizes 1000, 5000, 50000, 100000 (200-character messages, size + 5000 adds), 100000 with 2000-character messages, 100000 with 600 adds (control), 1000 with 50 x size adds, an 8-thread run, `resolveBufferSize()` for 10 property values in-process and 5 through `-D`. Cluster (B3): one node, `-Dcassandra.virtual.logs.max.rows` = 1000 / 20000 / 100000 / 200000 (out of range) / unset, the OFF arm (appender left commented out as shipped), and `w1000` (appender on at the shipped WARN threshold); five cumulative stress steps up to 100,000 writes with `org.apache.cassandra` at TRACE (about 1.6 million log events per arm). Both tiers kept. |
| **Audit bottom line** | **Ready after amendments** — 2026-10-27 |

### 1.1 Design audit

| Group | Check | Rating | Note (section checked) |
|---|---|---|---|
| A. Core question | constrained quantity is memory or disk bytes | Met | A2/B1: heap; the cap is a row count and A3 names the byte size as rows x message size. |
| A. Core question | knob varied, ≥ 3 values incl. default — or another approach, with the reason | Met | B2b has sizes 1000 / 5000 / 100000 and property values on both clamp edges; B3b has 1000 / 20000 / 100000 / 200000. The default (unset) arm was added (C4). |
| A. Core question | real resource measured, not only the counter (gap named) | Partly | B2d/B3d offered the histogram and a heap reading, but with no way to separate the table from the rest of the heap and with `count(*)` as the row count. Fixed: unit bytes per row from the histogram delta of four classes (U3); cluster ON-minus-OFF byte totals (C3). The cluster byte reading remained noisy (see 4.2 part 2). |
| A. Core question | usage driven to the limit and past it | Met | B2c adds size + 5000 (and 50 x size); B3c with the TRACE workload gives 1.6 million events per arm against N up to 100000 (C2); the filed "INFO/DEBUG lines" could not have reached N (see C1, C2). |
| B. Logic | each step says what it establishes | Met | B2e/B3e numbered. |
| B. Logic | prediction stated in numbers or a clear relation | Partly | B2f/B3f were relations ("roughly linearly", "several-fold"); numbers added before the runs (U4, C5). |
| B. Logic | every plausible outcome has a conclusions row with its evidence | Partly | rows for count above N, below N and flat heap exist; none for "CQL rows below the instance count" and none for the controls: added (U5, C7). |
| B. Logic | confirmation needs ceiling-follows-knob and direct disallow evidence | Met | B2g/B3g: count == N for each N, and eviction visible as the oldest id moving (unit) and as events since the oldest listed row staying near N while the run's events grow (cluster, C3). |
| B. Logic | alternative explanations and their controls | Partly | B3h's "baseline run with no workload" cannot tell a cap from an appender that never feeds the table. Added the OFF arm and the WARN-threshold arm (C4). |
| C. Specific | a human can follow it from the intro and B1/B2g/B3g | Met | A1-A4, B1. |
| C. Specific | an AI can run B2a-B2e / B3a-B3e without re-deriving the code path | Partly | **B3a is wrong**: the shipped `logback.xml` has the `CQLLOG` appender and its `appender-ref` commented out (lines 112-118, 127-129) and a `WARN` threshold, so the table is never fed by the default file (C1). The unit test construction (`LogMessagesTable(String,int)` is package-private; needs `DatabaseDescriptor` initialised and the JDK 11 module flags) was not spelled out (U1). |
| C. Specific | knob, values, workload, commands, observables, sampling, stop conditions exact | Partly | "a loop of schema changes / nodetool flush / repair plus cassandra-stress" does not name a volume: replaced by the TRACE workload with cumulative steps (C2). |
| D. Runnable | harness and environment prerequisites exist or are listed | Partly | written in step 1 (this session); JDK, Ant, build present on pc41. |
| D. Runnable | workload arithmetic reaches the limit (data, time, disk, memory) | Met after amendment | 1.6 million events per arm in 25-70 s of stress at 2-14k ops/s; `debug.log` of about 400 MB per arm (raised rolling size, local disk, 51 GB free at the end); -Xmx2g holds 100000 messages of 100-300 bytes (30 MB). |
| D. Runnable | load-bearing citations spot-checked against the pinned source | Met | Checked in `cassandra/cassandra-5.0.9`: `LogMessagesTable.java:57-59` (constants), `:72-92` (constructors), `:146-152` (`resolveBufferSize`), `:176-200` (`BoundedLinkedList`, the `==` check at `:193`), `:129-132`; `CassandraRelevantProperties.java:338`; `VirtualTableAppender.java:125`; `conf/logback.xml:112-130`; `CassandraDaemon.java:542-543` (`flushBuffer`). All as cited except the `logback.xml` assumption (C1). |

| # | Recommendation | Applied? | Why |
|---|---|---|---|
| R1 | Private logback.xml with the appender enabled and a TRACE threshold (C1) | Applied 2026-10-27 | the shipped file never feeds the table |
| R2 | Volume from a TRACE stress workload (C2) | Applied | filed volume not specified and not reachable at INFO/DEBUG |
| R3 | Row count from a collecting class histogram, not `count(*)` (C3) | Applied | `count(*)` returned 105 for 726 messages (shakedown) |
| R4 | OFF arm and WARN arm as controls (C4, C7) | Applied | "cap" must be told from "never fed" |
| R5 | Numeric heap prediction per entry = L + 96 B (U4); ON-minus-OFF in the cluster (C3, C5) | Applied | the filed "linear" is not decidable |
| R6 | JUnit through the java launcher with module flags (U1) | Applied | `ant testsome` heap; `FileUtils` needs the JDK 11 flags |
| R7 | For stage 3: a note that `system_logs` reads (CQL) can show fewer rows than the buffer holds, because `data()` keys rows by (timestamp, running index) assuming time order (lines 111-119) | left for stage 3 | observed in the cluster tier (4.2 part 2) |

## 2. Environment

| Field | Run 1 |
|---|---|
| Date | 2026-10-27 (node clock UTC 2026-10-28 02:15-02:58; unit tier 02:33, cluster 02:33-02:58) |
| Node | `pc41` = `node4.jason92-321705.misconfiguration-pg0.cloudlab.umass.edu` (40 cores, 251 GiB) |
| OS and kernel | Ubuntu 22.04.2 LTS, `5.15.0-198-generic` |
| JDK | openjdk 11.0.32.1 (2026-08-18) |
| Ant | Apache Ant 1.10.12 |
| Local source copy | `~/c4-vlr` from `cassandra/cassandra-5.0.9/` at repository commit `6e6cf92` (`copy-source.sh`, tag `cassandra-5.0.9` in the local baseline), `ant build-test` BUILD SUCCESSFUL (1 min 9 s) |
| Case-file / harness commit | uncommitted (working tree of `6e6cf92`); case-file sha256 in section 1; harness md5s in `run1/unit/harness.md5` |
| Storage for node data | `~/stage4-vlr/node` on local `/dev/sda3` (63 GB, 51 GB free at the end), removed after each arm; nothing under `/proj` |
| Full logs (outside the repo) | `pc41:~/stage4-logs/vlr/run1/{unit,cluster}/` (per arm: histograms, row listings, `debug.log` copy, `system.log`, stress output); discarded shakedowns in `~/stage4-logs/vlr/{shake,shake-c}` |

## 3. Runbook defects

| # | Run | Step | Problem | Fix | Decision (date) |
|---|---|---|---|---|---|
| D1 | cluster (found in the shakedown, before the freeze) | B3a: "Logging config must include the VirtualTableAppender (default logback.xml)" | the default `logback.xml` has the appender commented out and a WARN filter; the table stays empty | private `logback.xml` (C1) | 2026-10-27, before the freeze; claim, prediction and rows unchanged in substance |
| D2 | cluster (shakedown) | B3d: `SELECT count(*)` as the row count | returned about 105 where the buffer held 726 messages (and 362 vs 1000 after a burst) | instance count of a class histogram as the primary reading, a paging-off listing as a lower bound (C3) | 2026-10-27, before the freeze |
| D3 | unit (shakedown) | B2a: JUnit on the build classpath | `ExceptionInInitializerError` in `FileUtils`: the JDK 11 `--add-exports/--add-opens` flags of `conf/jvm11-server.options` were missing | `unit-run.sh` passes them from that file as an argument file | 2026-10-27, before the freeze |
| D4 | cluster | B3e step 4: "verify no java process remains with `pgrep -f CassandraDaemon`" | a `pgrep`/`grep` pattern inside the run script can match its own shell (the closed trie case printed "left: 1" after every arm) | `ps -eo pid,comm,args \| awk '$2=="java" && /CassandraDaemon/'` (C6); every arm printed `left: 0` | 2026-10-27, before the freeze |

## 4. Run 1

**Scope:** every B2 and B3 value of section 1. **Command logs:** `virtual_logs_max_rows-boundedlinkedlist_add-size--autonomous/run1/` (`unit/*.out`, `unit/*.log.summary`, `cluster/<arm>/cmdlog.txt`, `cluster/analysis.txt`, `cluster/chain.log`, `selfcheck.txt`). Abbreviations: N_eff = the size the table resolves to; E = `debug.log` events; b0/e0 = instance count and events at the base reading; "inst" = live `LogMessagesTable$LogMessage` instances in a collecting class histogram; "rows" = rows of a paging-off CQL listing.

### 4.1 Readings

**Unit tier** (`run1/unit/`)

| Test or assertion | Result | Evidence |
|---|---|---|
| sizes 1000 / 5000 / 50000 / 100000, 200-char messages, adds = size - 1, size, size + 1, size + 5000 | at every checkpoint: `bufferSize = min(adds, size)`, newest id = adds, oldest id = max(1, adds - size + 1) (e.g. size 100000, adds 105000: buffer 100000, newest 105000, oldest 5001) | `cap-len200.out` |
| same four sizes, after the last add | `dataRows == bufferSize == LogMessage instances == size` (1000, 5000, 50000, 100000) | `cap-len200.out` RESULT lines |
| bytes per entry (histogram delta of `LogMessage` + `LinkedList$Node` + `String` + `[B`), sizes with at least 50000 rows | 299 B (size 50000) and 297 B (size 100000) at L = 200 (predicted [280, 312]); 29,785,648 B in total for 100000 (predicted 28-31 MB) | `cap-len200.out` |
| size 100000, 2000-character messages | 2099 B per entry (predicted [2080, 2112]); 209,991,272 B in total (predicted 208-211 MB); `dataRows == bufferSize == instances == 100000` | `cap-len2000.out` |
| control, size 100000, 600 adds | `bufferSize == dataRows == instances == 600` (the cap is not reached) | `cap-adds-lt-size.out` |
| size 1000, 50000 adds (50 x the cap) | `bufferSize == dataRows == instances == 1000` | `cap-50x.out` |
| 8 threads x 200000 adds, size 1000 | final `bufferSize` 1000, sampled maximum 1000, `dataRows` 1000 | `mt8.out` |
| `resolveBufferSize()` in-process | unset 50000; 999 -> 50000; 1000 -> 1000; 1001 -> 1001; 50000; 50001; 100000 -> 100000; 100001 -> 50000; 0 -> 50000; -1 -> 50000 | `resolve-inproc.out` |
| `resolveBufferSize()` through `-D` on the JVM command line | unset 50000; 999 -> 50000; 1000 -> 1000; 100000 -> 100000; 100001 -> 50000 | `resolve-D-*.out` |
| upstream `LogMessagesTableTest` (known-answer for the harness) | 6 run, 0 failures | `upstream-LogMessagesTableTest.summary` |

**Cluster tier** (`run1/cluster/<arm>/`, `run1/cluster/analysis.txt`). Steps are cumulative stress writes: s2000 ... s100000 (E about 34 thousand to 1.6 million).

| Capacity value | Run | Observable | Reading | Evidence |
|---|---|---|---|---|
| 1000 | `n1000` | inst at s2000 / s10000 / s20000 / s40000 / s100000 | 1000 at every step (E = 34321 ... 1,620,733); base 725 | `n1000/*.events`, `hist-*.4classes.txt`, `analysis.txt` |
| | | rows (paging-off listing) | 467, 289, 715, 697, 699 (lower bound, below inst) | `cqlrows-*.txt` |
| | | events at or after the oldest listed row | 1191, 1261, 1066, 1193, 1184 (run's E up to 1.6 M) | `analysis.txt` column since_old |
| | | capacity line, process arguments | "at most 1000 rows"; `-Dcassandra.virtual.logs.max.rows=1000` | `capacity-line.txt`, `proc-args.txt` |
| 20000 | `n20000` | inst | 20000 at every step from s2000 (E = 34309) on | same files |
| | | events at or after the oldest row | 20179, 20489, 20051, 20184, 20099 | `analysis.txt` |
| 100000 | `n100000` | inst | 34321 at s2000 (E = 34321, below the cap: equals b0 + E - e0), then 100000 at s10000 ... s100000 (E up to 1,620,489) | `n100000/*` |
| | | rows | 16527, 37524, 53783, 66770, 74136 | `cqlrows-*.txt` |
| | | events at or after the oldest row | 34321, 100296, 100184, 100145, 100084 | `analysis.txt` |
| 200000 (out of range) | `n200000` | capacity line, inst | "at most 50000 rows" with `-Dcassandra.virtual.logs.max.rows=200000`; inst 34333 at s2000, 50000 from s10000 on | `n200000/capacity-line.txt`, `proc-args.txt`, `analysis.txt` |
| unset | `nunset` | capacity line, inst | "at most 50000 rows", no property in the arguments; inst 34326 at s2000, 50000 from s10000 on | `nunset/*` |
| appender left as shipped | `off` | inst, rows | 0 and 0 at every step, E up to 1,620,305 | `off/*` |
| 1000 at the shipped WARN threshold | `w1000` | inst, rows; WARN/ERROR events of the run | 6 and 6 at every step; `debug.log` of the run holds 6 WARN/ERROR events; E up to 1,620,205 | `w1000/*`, `analysis.txt` |
| heap, ON minus OFF at equal steps (bytes of the four classes; post-GC heap) | | bytes per instance, N >= 20000 | n20000: 509, 510, 510, 90, 300; n100000: 102, 194, 236, 226, 173; n200000 (N_eff 50000): 377, 331, 331, 163, 163; nunset: 164, 184, 184, 163, 100. For N = 1000 the difference is not positive (+3.4 MB, +3.4, +3.4, -5.0, -6.0 MB) | `analysis.txt` |
| | | total ON-minus-OFF at s10000, N = 100000 | 19.4 MB (instances 100000); the OFF arm itself rises 27.9 -> 46.8 MB over the run (memtable, caches) | `analysis.txt` |

### 4.2 Conclusion and logic

1. **Validity.** The cap was reached and passed in both tiers [observed: unit `cap-*.out` with adds up to 50 x size; cluster `analysis.txt`, E up to 1.6 million against N of at most 100000]. Held-fixed settings: the knob took effect on the process [observed: `proc-args.txt` shows the `-D` flag for each arm, `capacity-line.txt` shows the table size the node resolved]; heap 2 GB [observed: `vmflags.txt`]; the appender and its threshold [observed: `logback.diff` in each arm's folder: appender and reference uncommented, threshold TRACE (WARN for `w1000`), and the `off` arm uses the shipped file]; one node, fresh data directory per arm [observed: `cmdlog.txt`]; no leftover daemon [observed: `CassandraDaemon processes left: 0` at the end of every `cmdlog.txt`; `ps` after the chain: 0]. Valid.
2. **Readings.** (a) The CQL row listing is below the instance count in every burst reading (467 vs 1000, 74136 vs 100000): the listing collapses rows that share (timestamp, running index) when events from many threads interleave within a millisecond [inferred: `data()` increments the index only for consecutive equal timestamps, `LogMessagesTable.java:111-119`; at idle (base reading) the two agree, 725 vs 725 [observed: `n1000/base.events`, `cqlrows-base.txt`]; the 8-thread unit run lists exactly 1000 because its timestamps are monotone [observed: `mt8.out`]]. So `count(*)` and the listing are lower bounds and the instance count is the buffer size. (b) The filed heap sub-predictions of the cluster tier missed: the ON-minus-OFF byte total per instance is not the same within 25 percent across arms (90-510 B), and the N = 1000 arm gives a non-positive difference; the byte ratio N = 100000 / N = 1000 of 60-140 is undefined. [inferred: the workload writes 100000 rows into the stress table, so the memtable, caches and young-generation state differ between arms by about 10 MB, which swamps the 0.1 MB that 1000 messages occupy and blurs the 5-20 MB of the larger arms; the OFF arm alone moves by 19 MB over the run [observed: `analysis.txt`].] The per-entry figures that were predicted as a band of 60-600 B are inside it in every reading (90 to 510 B) [observed]. The exact per-entry bytes come from the unit tier (L + 96 B) [observed]. (c) Events reach the table in the order of their creation only approximately, which is why events at or after the oldest listed row exceed N by 0.2 to 1 percent (and 20 percent at N = 1000) [inferred]; all values are far below the run's E for the steps in which E exceeds 2N + 1000.
3. **Matched row.** Unit B2g row 1 "Row count == size after size+5000 adds, instance count equal -> claim confirmed" [observed: `cap-len200.out`, `cap-len2000.out`: `dataRows == bufferSize == instances == size` for the four sizes and for 2000-character messages; the oldest id moves, newest id = adds]. Cluster B3g row 1 "count == N (or 50000 for out of range), instances match -> confirmed": the instance count (the buffer size) equals N_eff for N = 1000 / 20000 / 100000 / 200000 (50000) / unset (50000) at every step past the cap, tolerance +5 not needed (exact) [observed: `analysis.txt`, `selfcheck.txt`], equals b0 + E - e0 below it (n100000 s2000: 34321) [observed], and the number of events at or after the oldest listed row stays near N while E grows (e.g. 100084 against E = 1,620,489 at N = 100000) [observed].
4. **Excluded rows.** "Row count exceeds size" (B2g row 2, B3g row 2): no, the maximum over all readings is N_eff [observed: `selfcheck.txt`]; "Resolved size outside [1000, 100000]": no, all 15 resolutions are in range or 50000 [observed: `resolve-*.out`]; "Heap flat across sizes with same adds -> measurement invalid": the unit heap grows with size (14.99 MB at 50000, 29.79 MB at 100000, 210 MB at 100000 x 2000-char) [observed]; cluster "count < N and log lines < N -> limit not reached": only in the `w1000` arm, by design (6 < 1000 WARN/ERROR events) [observed]; the cluster rows of the filed table were never below N_eff once E exceeded it.
5. **Observed vs. inferred.** Inferred: (i) why the CQL listing is below the instance count (collapse of same-key rows); (ii) the cause of the byte noise (memtable and GC state of the stress workload); (iii) that the live instance count is the buffer size and not buffer plus in-flight objects (a message being appended at the instant of the histogram adds at most one per logging thread; the histogram is taken 10 s after the workload stops, with DEBUG-level logging continuing at a few lines per second; the readings are exactly N_eff in all 25 arm-steps with the cap passed or reached, which supports it) — it also agrees with `bufferSize` by reflection in the unit tier [observed].
6. **Deviations and gaps.** The filed volume (INFO/DEBUG lines from schema changes, flushes, repair) was replaced by the TRACE workload (C2); the filed `count(*)` by the instance count (C3); the logging configuration of B3a was wrong (C1). Messages in the cluster tier are not "ordinary size" controlled: their length varies (QueryProcessor lines of 100-300 characters); only the unit tier fixes the length. The cluster tier's byte reading is a noisy measurement, not a precise one (part 2). One run per arm, single node, no repeats. The `w1000` arm covers one threshold only.
7. **Core question.** Did usage follow the constraint, and does it cap usage? Yes, in rows and therefore in heap: with the knob at 1000, 20000, 100000, 200000 (clamped to 50000) and unset, the number of retained `LogMessage` objects stopped at exactly N_eff while the log volume went to between 16 times N (N = 100000) and 1600 times N (N = 1000), the oldest entries were dropped (unit: oldest id moves; cluster: events at the oldest row stay near N), and the heap per retained entry is `L + 96` bytes (unit), so the table's heap is bounded by N x (message length + 96 B) [steps 1-3 of the filed logic: parts 3 and 4; the bytes: part 2(b) and the unit tier]. The cap binds only for the messages that reach the appender: with the shipped file the table is empty (arm `off`), and with the appender on but its shipped WARN threshold the table held 6 messages (arm `w1000`).

**Conclusion (one line):** Unit B2g row 1 — confirmed (caps); Cluster B3g row 1 — confirmed (caps) on the row count, with the filed byte-level sub-predictions (cross-arm per-entry agreement, N-ratio of the ON-minus-OFF bytes) missed because of workload noise.

## 5. Self-check of run 1 — AI

### 5.1 Check of run 1's conclusion

Re-opened 2026-10-27: every committed excerpt under `run1/` was re-parsed by `harness/.../selfcheck.py` (written independently of `analyze.py`; its output is `run1/selfcheck.txt`: 116 PASS, 0 FAIL, "ALL PASS"), the raw `cmdlog.txt` of `n100000`, `off` and `w1000`, `capacity-line.txt` and `proc-args.txt` of all seven arms, `hist-s100000.4classes.txt` of `n100000`, and on the node `ps` for leftovers.

| Part | Holds? | Note (file re-read) |
|---|---|---|
| 1. Validity | yes | `proc-args.txt` of the seven arms: `-Dcassandra.virtual.logs.max.rows=` 1000 / 20000 / 100000 / 200000 / (none) / (none, off) / 1000 (w1000); `capacity-line.txt`: 1000 / 20000 / 100000 / 50000 / 50000 / 50000 / 1000; `logback.diff` of `w1000` shows the appender and its reference uncommented with the `<level>WARN</level>` line unchanged (no level line in the diff), of `off` only the two rolling-size lines (no appender lines); `left: 0` in each `cmdlog.txt`. |
| 2. Readings | yes | `selfcheck.txt`: all instance counts equal min(N_eff, b0 + E - e0); the CQL rows never exceed the instance count; the byte noise is as stated (`analysis.txt` rows quoted in 4.1 re-read). |
| 3. Matched row | yes | `n100000/hist-s100000.4classes.txt`: `LogMessagesTable$LogMessage` 100000 instances, 3,200,000 B (32 B each); `cqlrows-s100000.txt` 74136; `s100000.events` 1,620,489. |
| 4. Excluded rows | yes | `selfcheck.txt` has no instance count above N_eff; `resolve-*.out` rows re-read: 15 resolutions as stated; `w1000/*.4classes.txt`: instances 6. |
| 5. Observed vs. inferred | yes | the weakest inference is (ii) (cause of the byte noise): it does not enter the verdict, which rests on the instance counts and the unit tier. The `LinkedList$Node` line of `hist-s100000.4classes.txt` shows 100539 nodes (539 belong to other lists), which confirms the histogram counts all holders, and `LogMessage` is the specific class. |
| 6. Deviations and gaps | yes | listed; none of the conclusions depends on the byte reading of the cluster tier. |
| 7. Core question — the steps from reading to answer follow the audited logic | yes | steps: the knob reaches the process (arguments, capacity line) -> volume exceeds N (events) -> the buffer holds N_eff (instances) -> oldest dropped (events since the oldest row) -> controls (OFF, WARN). |

### 5.2 Run 2?

**No** (2026-10-27). The unit tier's result is exact (row counts and bytes against a pre-registered band, in 11 independent JVMs); the cluster tier's row counts are exact in 25 arm-steps over five knob values with two controls (10 more control arm-steps); the only inferred cause (byte noise) does not affect the verdict. A run 2 could add a no-write workload (a read-only or log-only source) to make the cluster byte reading precise.

## 6. Run 2 — fresh AI session (optional)

Not done.

## 8. Verdict — AI

**Stage-3 estimate:** positive. **Outcome class:** true positive (positive, caps): the buffer never holds more than N_eff messages, so the table's heap is bounded by N_eff x (message size + about 96 B); the cap works as traced.

**Claim tested (B1):** with `cassandra.virtual.logs.max.rows=N` (N in [1000, 100000]), the `system_logs` buffer holds at most N messages and its heap use grows with N and stops growing once N messages are held; out-of-range values (for example 500 or 200000) fall back to 50000.

| Tier | Verdict (B2g / B3g row) | Effect on the constraint | Basis | Date |
|---|---|---|---|---|
| Unit | Confirmed (B2g row 1: row count == size, instance count equal, heap per entry L + 96 B and linear in size; clamp as claimed) | caps | run 1 + self-check | 2026-10-27 |
| Cluster | Confirmed (B3g row 1: live instances == N_eff for 1000 / 20000 / 100000 / 200000 -> 50000 / unset -> 50000; eviction visible; OFF and WARN controls as predicted); filed byte-level sub-predictions missed (workload noise) | caps (only for events that reach the appender: not with the shipped logback.xml, and only WARN and above with its shipped threshold) | run 1 + self-check | 2026-10-27 |

**Feedback filed:** the case file's section D updated (no commit by this session); amendments U1-U5 and C1-C7 (2026-10-27) in B2 and B3. For stage 3: the shipped `logback.xml` does not feed `system_logs` (appender commented out, WARN filter), so "the default node's table is empty"; a CQL `count(*)` or listing under-reports the buffer when events share milliseconds.
