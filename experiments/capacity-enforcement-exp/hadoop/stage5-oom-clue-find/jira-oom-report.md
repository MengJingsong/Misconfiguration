# Hadoop JIRA OOM report

*Written 2026-11-17* for stage 5 ([`../../stage5-oom-clue-find/README.md`](../../stage5-oom-clue-find/README.md)), method
[`jira-mining.md`](../../stage5-oom-clue-find/jira-mining.md), following the
[Cassandra report](../../cassandra/stage5-oom-clue-find/jira-oom-report.md). This is the analysis of Hadoop's own JIRA
history of out-of-memory failures (HADOOP/common, HDFS, YARN, MAPREDUCE). It feeds the system-agnostic
[OOM clue patterns](../../stage5-oom-clue-find/oom-clue-patterns.md) (`CP-` IDs, §7). It is read only: **nothing is
ever posted to JIRA** or reported upstream.

**Data** (in this folder): [`jira-oom-survey.csv`](jira-oom-survey.csv), one row per issue (961 rows), with the same
columns as Cassandra's survey. Hadoop-specific conventions in the CSV:

- `notes` starts with the issue's primary cause shape (`shape HC-n`, §4; `HC-14 (history)` is a sub-shape of HC-14)
  and ends with the query set that found it (`query:survey` or `query:extension`, §1). It also holds the fix summary
  read from the diff (`fix: …`).
- `flow_detail` holds the short flow code; `flow` holds the full name.
- `diff_checked` holds up to three fix commits (short hashes in `apache/hadoop`). `variant_lead` notes incomplete fixes,
  opt-in fixes and fixes that are missing from the pinned `rel/release-3.4.2`.
- `shard` is `1` for all rows (one reader). `second_pass` is filled for the 32 sampled rows (§2).
- `repro_cost` is a rough heuristic from the trigger text: `low` means a setting or a corrupt input; `high` means
  cluster scale or days of running. Treat it as a hint only.

Issue keys below are written in full (`HDFS-n`, `YARN-n`, …).

## 1. Scope and queries

| Pass | Date | Query (`issues.apache.org/jira`, REST search) | Hits |
|---|---|---|---|
| Survey | 2026-11-17 | `project in (HADOOP,HDFS,YARN,MAPREDUCE) AND (text ~ "OutOfMemoryError" OR text ~ "OOM" OR summary ~ "out of memory" OR text ~ "\"Direct buffer memory\"" OR text ~ "\"GC overhead limit\"" OR text ~ "\"oom-killer\"")`: the Cassandra query, unchanged | **710** (HADOOP 247, HDFS 232, YARN 114, MAPREDUCE 117) |
| Extension | 2026-11-17 | same projects, each term on its own, keeping only keys the survey did not return: `text ~ "\"out of memory\""` (122 new), `summary ~ "memory leak"` (64), `text ~ "\"heap space\""` (42), `text ~ "OutOfMemory"` (28), `text ~ "\"running beyond physical memory\""` (8), `text ~ "\"unable to create new native thread\""` (7), `text ~ "\"Java heap space\""` (4) | **251** keys in the union |
| Targeted checks | 2026-11-17 | `summary ~ "mistakenly"` (14 hits; the 4 that are OOMs are already in the survey); `(summary ~ "\"large number\"" OR summary ~ "\"large value\"") AND (summary ~ memory OR summary ~ OOM)` (6 hits, all in the survey); `text ~ "\"dfs.namenode.max.objects\""` (1 hit, not an OOM) | per query |

**Issues read: 961.** By project: HADOOP 343, HDFS 299, YARN 163, MAPREDUCE 156. Resolutions: Fixed 577,
Unresolved 213, Duplicate 61, Won't Fix 43, Invalid 22, Not A Problem 21, Cannot Reproduce 12, Incomplete 4,
Not A Bug 2, Won't Do 2, other 4 (Later, Resolved, Workaround, Done).

**Screen.** An issue is kept when Hadoop code itself ran out of memory (heap, direct, native including native
threads, or a kernel or cgroup kill) and that is the reported problem. Hadoop-specific decisions:

- **Client libraries are kept.** DFSClient, libhdfs and fuse-dfs, and the S3A, ABFS, WASB and OSS connectors run inside
  long-lived services (HBase, Hive Metastore, Oozie, Spark executors, the NodeManager). Their leaks are reported as
  service OOMs.
- **Standalone CLI and tool memory is excluded**: fs shell listings, OIV, the history viewer, Sqoop, distcp client
  heap and archive tools.
- **User memory is excluded**: a mapper's own data, and container kills of user code. Framework code inside tasks
  (sort buffer, shuffle, merge, record readers) is kept.

Every excluded issue keeps a row with its reason. **593 excluded**: OOM only in passing or no memory mechanism 263;
test, CI or build memory 215; OOM handling only (catch, exit, log, hang after an OOM) 57; client tool memory 25;
"oom" as unrelated text (a user name in old logs) 18; user or application memory 15.

**368 kept**:

| Resolution group | Kept | HADOOP | HDFS | MAPREDUCE | YARN |
|---|---|---|---|---|---|
| Fixed | 201 | 90 | 42 | 36 | 33 |
| Open (Unresolved) | 97 | | | | |
| Closed without a fix: by design or invalid (Won't Fix 14, Not A Problem 12, Invalid 6, Not A Bug 1, Workaround 1, Incomplete 1) | 35 | | | | |
| Closed without a fix: Duplicate 26, Cannot Reproduce 9 | 35 | | | | |
| **Total kept** | **368** | 145 | 87 | 71 | 65 |

## 2. How issues were classified

- **Reading.** One reader (this agent) read all 961 issues: summary, description, and the comment passages around each
  OOM term, plus the full text where the mechanism was unclear. Cassandra used four readers; this survey used one.
- **Fix diffs.** For each kept Fixed issue the fix commit was found by issue key in a full clone of `apache/hadoop`:
  **182 of 201** have commits. **175 diffs were read** (non-test source hunks). For 7 more, a commit was found but its
  first commit shows no relevant hunk: dependency upgrades HADOOP-9672 and HADOOP-17370, merges HADOOP-11105,
  HADOOP-19862 and MAPREDUCE-5351, and unrelated hunks in HADOOP-2095 and HADOOP-4635. The other 19 have no commit:
  pre-split SVN history or branch-1 only. Those are classified from the text.
- **What the diffs changed.**
  - **Fix kind, 8 issues.** For example, HADOOP-6754's "fix" only logs a warning, HADOOP-11446 adds a bounded shared
    pool (a new limit), and HDFS-14655 bounds the JournalNode read pool.
  - **Class or shape, 4 issues**: HADOOP-3550, HADOOP-3670, HDFS-11608 and MAPREDUCE-3057.
  - **Re-screened out, 4 issues.** HADOOP-10158 and YARN-2934 raised OOM only as a review concern. MAPREDUCE-430 and
    MAPREDUCE-6436 turned out to be OOM handling or logging fixes.
- **Columns and classes** use the Cassandra vocabulary: `unprotected:accumulation`, `unprotected:configuration`,
  `bypass:accounting-mismatch`, `bypass:release-defect`, `bypass:late-enforcement`, `bypass:exempt-path`,
  `convergence:multiplicity`, `convergence:standing-pool`.
  - Budget `native` includes native thread exhaustion ("unable to create new native thread", 31 kept issues).
  - Budget `cgroup` means a container or node memory kill.
- **Second pass.** A seeded random sample (seed 20261117) of 20 kept and 12 excluded issues was re-read with the full
  description and the first comments.
  - Screen: 32 of 32 agree. Class: 20 of 20 agree.
  - Cause shape: 18 of 20 agree. HADOOP-1012 moved from HC-7 to HC-2 (it was closed as part of HADOOP-1027).
    HADOOP-17166 moved from HC-8 to HC-7 (per-stream buffers times the number of streams). Both changes are applied.
  - The same reader did both passes, so this is a consistency check, not an independent review.
- **Cause shapes (§4).** Each kept issue has one primary shape, assigned from its trigger, `control_before` and the fix
  diff. HC-1 to HC-14 follow the Cassandra JC-1 to JC-13 shapes and the CP patterns. HC-15 and HC-16 are new.

Class counts (kept / of which Fixed):

| Class | Kept | Fixed |
|---|---|---|
| unprotected:accumulation | 249 | 157 |
| convergence:multiplicity | 38 | 22 |
| unknown (cause never established) | 32 | 5 |
| unprotected:configuration | 28 | 7 |
| bypass:release-defect | 10 | 6 |
| bypass:accounting-mismatch | 9 | 3 |
| bypass:exempt-path | 2 | 1 |
| bypass:late-enforcement, convergence:standing-pool | 0 | 0 |

**Budget (kept):** heap 283, native 65 (31 of them native threads), direct 16, cgroup/kernel 3, unknown 1. Fixed:
heap 159, native 34, direct 6, cgroup 1, unknown 1.

**Flows (kept):**

| Flow | Kept |
|---|---|
| MR AM, JobTracker, TaskTracker and JobHistory state | 46 |
| FileSystem connectors and framework | 41 |
| HDFS client (DFSClient, libhdfs, fuse) | 32 |
| YARN NodeManager | 32 |
| Common utilities (codecs, metrics, conf) | 28 |
| YARN RM scheduler and state | 28 |
| MR shuffle | 26 |
| MR task (sort buffer, spill, merge, readers) | 21 |
| Hadoop IPC | 18 |
| DataNode pipeline and transfer | 16 |
| NameNode namespace | 15 |
| NameNode image, edits, JournalNode | 15 |
| Other daemons (Balancer, NFS gateway, RBF router, distcp, RaidNode) | 14 |
| Web servers | 8 |
| Timeline server | 8 |
| NameNode block management | 6 |
| DataNode volumes and replica map | 6 |
| KMS | 4 |
| Erasure coding | 4 |

**Fix kind (Fixed):** release fix 84, other code change 77, new limit 27, doc or default change 7, backpressure 4,
accounting change 2.

**Configuration.** `config_involved` is yes in 76 of 368 kept issues (21 %). A misconfigured or mis-sized value was the
**direct trigger in 16 (4 %)**:

- HADOOP-9211, MAPREDUCE-5785, MAPREDUCE-5429: heap settings.
- HADOOP-18804, HADOOP-18822, HDFS-17095, HDFS-17096, HDFS-17097: huge values for sizes and counts.
- HDFS-11608: block size above 2 GB.
- HDFS-16550: JournalNode cache equal to the heap.
- HDFS-5262: `dfs.client.socket-timeout=0`.
- HDFS-17953: HA NameNode ID with no address.
- HDFS-2204: wrong port.
- HDFS-3600: `-XX:+DisableExplicitGC` with direct buffers.
- YARN-5370: `debug-delay-sec` of 100 days.
- YARN-7284: DEBUG logging.

## 3. What the history says, in short

1. **Hadoop's OOMs are mostly leaks.** Retention past the end of life (HC-14) is 88 of 201 fixed issues (44 %), against
   11 of 120 in Cassandra. The daemons run for months. The client libraries live inside other long-running services.
   Fixes are mostly a missing `close`, `unregister`, `cancel` or `remove` (release fix 84 of 201).
2. **One cause keeps returning: the per-UGI FileSystem cache.** 17 kept issues, 8 of them fixed: HADOOP-3762,
   MAPREDUCE-5351, MAPREDUCE-5508, YARN-3336, YARN-5438, HDFS-12748, HDFS-15052, MAPREDUCE-6889. The project's
   position is that callers must close (HADOOP-6843 Not A Problem, HADOOP-12707 Won't Fix, HDFS-3545). Metrics
   registrations (HADOOP-10839, HADOOP-10840, HADOOP-11105, HADOOP-16278, HADOOP-18526, YARN-5296) and timers or
   thread pools never shut down (HADOOP-16570, HADOOP-19862, YARN-9639, YARN-9642) are the same shape.
3. **Native threads are a budget of their own.**
   - 31 kept issues end in "unable to create new native thread".
   - The usual cause is one thread per connection, stream, call or event. Examples: HADOOP-210 (NameNode listener),
     HDFS-2452 (DataNode xceivers), HADOOP-18324 and HDFS-14655 (a thread per call to a stuck JournalNode), HDFS-5140
     (55,000 safemode monitors).
   - The only bound is the OS process limit.
4. **Fixes rarely add limits, and new limits often ship off.**
   - Only 27 new limits and 4 backpressure fixes in 201.
   - Several limits default to off:
     - `mapred.linerecordreader.maxlength` is `Integer.MAX_VALUE` (HADOOP-3144).
     - The UniqValueCount maximum is `Long.MAX_VALUE` (HADOOP-1342).
     - `mapreduce.job.max.map` is `-1` (MAPREDUCE-6696).
     - distcp `-useiterator` is off (HADOOP-17531, HADOOP-17620).
     - RM timeline batching is off (YARN-8234).
     - `mapreduce.jobhistory.loadedtasks.cache.size` is unset (MAPREDUCE-6622).
   - So the reported shape is still present at shipped defaults.
5. **Configuration-sized allocations are a small open cluster (HC-16).** Five issues from 2023 report an OOM when one
   setting is set large: `io.file.buffer.size`, `decay-scheduler.metrics.top.user.count`, `file.bytes-per-checksum`,
   `ipc.server.read.threadpool.size` and `dfs.namenode.blockreport.queue.size`. All are unresolved. The code checks
   only `> 0`, or nothing.
6. **Queues with a stalled consumer gather in event dispatchers and IPC (HC-5).** AsyncDispatcher in the AM, RM and NM:
   MAPREDUCE-5043 (fixed), and YARN-270, YARN-4852, YARN-8789 and YARN-9929 (open). IPC: HADOOP-2910 (fixed),
   HADOOP-8942 and HADOOP-18389 (open). Downstream services: HDFS-17953 (IBRs queued for an unreachable NameNode)
   and YARN-8679 (an HBase backend that is down).
7. **Accounting mismatch is rare (9 kept)** and confined to the MR shuffle and sort buffers: int overflow in
   MAPREDUCE-1182 and MAPREDUCE-1228, raw versus compressed sizes in MAPREDUCE-1571, buffers outside the accounting
   in MAPREDUCE-5580, and a counter drifting in MAPREDUCE-7277. Most Hadoop holders have no byte counter at all.

## 4. Cause patterns in the 201 Fixed issues

| ID | Cause shape | Fixed | Open or unfixed | Budget (fixed) | Representative keys | Typical shape |
|---|---|---|---|---|---|---|
| HC-1 | Counter charges a smaller unit than the memory held | 2 | 9 | heap 2 | HADOOP-875, MAPREDUCE-1182; open: MAPREDUCE-5580, MAPREDUCE-7277, MAPREDUCE-1571, MAPREDUCE-1228 | sort-buffer memory model under-counts; shuffle RAM manager in `int` overflows above 2 GB; raw and compressed sizes mixed; IndexCache bookkeeping drifts from its contents |
| HC-2 | Limit counts items, not bytes | 6 | 5 | heap 6 | HADOOP-1027, HDFS-5788, MAPREDUCE-3057, MAPREDUCE-6622, MAPREDUCE-801, MAPREDUCE-6696; open: YARN-5627, YARN-7147, MAPREDUCE-44 | `dfs.ls.limit` counts entries while located listings carry blocks × replicas; JHS cache counts jobs while one job has 250k tasks; in-memory merge bounded in bytes but not in segments |
| HC-3 | Charge returned before the memory is freed (leak inside a pool) | 5 | 4 | native 2, heap 2, direct 1 | HADOOP-14376, HADOOP-18383, MAPREDUCE-5493, MAPREDUCE-7431; open: HADOOP-12007, HADOOP-19901 | CodecPool counts a native decompressor returned but it was never `end()`ed; merged map outputs kept after the budget was released; Netty message not released |
| HC-4 | Held until a response or timeout, and the answer stalls | 4 | 2 | native 2, heap 2 | HADOOP-18324, HDFS-14655, YARN-8404, YARN-8679; open: HDFS-5262, YARN-9769 | a stuck JournalNode keeps one thread per call; timeline publish blocks the dispatcher while ATS or HBase is down; socket timeout 0 means never |
| HC-5 | Queue keeps accepting while its consumer is slow, stalled or dead | 14 | 13 | heap 14 | HADOOP-2910, HADOOP-3104, HADOOP-13560, HADOOP-16248, MAPREDUCE-5043, HDFS-5249, HDFS-17909, HDFS-17953, YARN-8234 | IPC call queue; executor with an unbounded queue; S3A uploads faster than the network; fixed-rate scheduler falling behind; AsyncDispatcher backlog; IBRs for a NameNode that never answers |
| HC-6 | No graceful stop at the limit | 0 | 2 | — | open: HDFS-5461, HDFS-9598 | short-circuit read DirectBufferPool bounded only by `MaxDirectMemorySize`, no fallback |
| HC-7 | Per-owner memory or thread × unbounded owners | 18 | 18 | native 10, heap 8 | HADOOP-210, HADOOP-886, HADOOP-2095, HADOOP-11446, HADOOP-17195, HDFS-2452, HDFS-5364, HDFS-16386, MAPREDUCE-3333, YARN-6523 | thread per connection or stream; thread pool per output stream or FileSystem; native codec per in-memory segment; credentials of every app in every heartbeat |
| HC-8 | Defaults too large or small for the heap, or a size not tied to the heap | 5 | 11 | heap 5 | HADOOP-9211, HADOOP-10093, HDFS-16550, MAPREDUCE-5785, HADOOP-18876; open/closed: MAPREDUCE-5134, MAPREDUCE-7075, MAPREDUCE-6118, HADOOP-14176 | client `-Xmx128m` against `io.sort.mb` 100; container size and `-Xmx` set separately; JournalNode cache in absolute bytes (now a heap fraction); shuffle buffer 0.7 of the heap |
| HC-9 | Memory outside the JVM's limits | 4 | 6 | native 3, direct 1 | HADOOP-637, HDFS-6912, YARN-5368, YARN-9040; open: YARN-6062, YARN-6470, YARN-7603, HDFS-3600 | leveldb native memory in the timeline server (25 GB RSS with an 8 GB heap); direct buffers freed only by GC; sparse shared-memory files |
| HC-10 | A path that skips the limit | 1 | 0 | cgroup 1 | YARN-11967 | with `resource.memory.enforced=true` and the memory cgroup off, the polling pmem check is skipped; a 4 GB container grew to 20 GB |
| HC-11 | Enforcement late or after the allocation | 0 | 1 | — | open: HADOOP-17937 | S3A bytebuffer block of 32 MB allocated at block creation, before any data |
| HC-12 | One item materialized whole | 16 | 14 | heap 15, direct 1 | HADOOP-3144, HADOOP-10987, HDFS-3696, HDFS-7435, MAPREDUCE-1943, MAPREDUCE-4730, YARN-6188, YARN-8242 | a corrupt text "line"; whole directory listing; HTTP upload buffered whole; 100 M counters; all completion events in one RPC; whole NM state store loaded at recovery |
| HC-13 | Allocation sized from untrusted, corrupt or miscomputed input | 19 | 6 | heap 18, native 1 | HADOOP-9676, HADOOP-10940, HADOOP-8361, HDFS-3134, HDFS-8965, MAPREDUCE-3992, YARN-7697, HADOOP-10146, HADOOP-10780 | RPC length from a rogue client or wrong-version server; edit-log lengths; an HTML error page parsed as a map-output header; JDK `available()` returning garbage; `sysconf` returning -1 |
| HC-14 | Retention past the end of life (sub-shapes below) | 88 | 50 | heap 68, native 16, direct 3, unknown 1 | see the sub-shapes | |
| HC-15 | **Managed-entity state with no entity cap** (new) | 11 | 9 | heap 11 | HADOOP-1565, HADOOP-1687, HDFS-1110, HDFS-1114, HDFS-4461, MAPREDUCE-3567, MAPREDUCE-4301, MAPREDUCE-1374, MAPREDUCE-7241; by design: HDFS-4630, HDFS-6088, MAPREDUCE-2345 | per-inode, per-block, per-replica, per-task or per-FileStatus footprint × the number of entities the daemon manages. Fixes shrink the footprint. The project treats the count as an operator sizing matter, and the caps (`dfs.namenode.max.objects`=0, `mapreduce.job.max.map`=-1) are off by default |
| HC-16 | **Allocation sized by an unchecked configuration value** (new) | 1 | 5 | heap 1 | HDFS-11608; open: HADOOP-18804, HADOOP-18822, HDFS-17095, HDFS-17096, HDFS-17097 | buffer, array, preallocated queue or thread count taken directly from a setting checked only for `> 0`; block size above 2 GB overflowing the packet size |
| — | No reusable shape | 7 | 12 | heap 7 | HADOOP-1179, HADOOP-1264, HADOOP-1874, HADOOP-9672, HDFS-7279, YARN-4219, YARN-5337 | cause unknown; Jetty 6 buffer management; Avro bugs |

**HC-14 sub-shapes (fixed issues):**

| Sub-shape | Fixed | Keys |
|---|---|---|
| 14a. A per-instance registration or cache outlives its instance: FileSystem cache per UGI, metrics source, thread-local, `deleteOnExit`, timer or thread pool not shut down, class loader pinned | 32 | HADOOP-3762, HADOOP-8632, HADOOP-9757, HADOOP-10839, HADOOP-10840, HADOOP-11105, HADOOP-12107, HADOOP-12958, HADOOP-15658, HADOOP-16278, HADOOP-16570, HADOOP-18091, HADOOP-18313, HADOOP-18526, HADOOP-19862, HDFS-3646, HDFS-5140, HDFS-12748, HDFS-15052, MAPREDUCE-5351, MAPREDUCE-5508, MAPREDUCE-6621, MAPREDUCE-6889, YARN-3336, YARN-4581, YARN-5296, YARN-5438, YARN-7163, YARN-9067, YARN-9639, YARN-9642, YARN-9714 |
| 14b. Entries for finished or failed work never removed from a daemon's tracking maps: tasks, containers, apps, requests, leases, snapshots | 27 | HADOOP-740, HADOOP-3381, HADOOP-3382, HADOOP-3670, HADOOP-4906, HADOOP-5145, HADOOP-5269, HDFS-4182, HDFS-10763, HDFS-14247, HDFS-14492, HDFS-17499, MAPREDUCE-1892, MAPREDUCE-3343, MAPREDUCE-3977, MAPREDUCE-4379, YARN-539, YARN-1382, YARN-3857, YARN-6406, YARN-6565, YARN-8774, YARN-10467, YARN-10649, YARN-11152, YARN-11489, YARN-11808 |
| 14c. Native or JNI release missing | 11 | HADOOP-459, HADOOP-3737, HADOOP-4635, HADOOP-6207, HADOOP-6754, HADOOP-11526, HADOOP-17209, HDFS-420, HDFS-464, HDFS-596, HDFS-799 |
| 14d. Buffers, streams or an old generation of state kept after use or on an error path | 14 | HADOOP-2053, HADOOP-3865, HADOOP-6460, HADOOP-14028, HADOOP-18621, HADOOP-19330, HDFS-7470, HDFS-13540, HDFS-14308, MAPREDUCE-2510, MAPREDUCE-5168, MAPREDUCE-6169, MAPREDUCE-6528, MAPREDUCE-6628 |
| 14h. History of completed jobs or apps kept in memory, bounded only by count (or not at all) | 4 | HADOOP-787, MAPREDUCE-291, MAPREDUCE-1699, MAPREDUCE-2649 |

**Borderline assignments:**

- HADOOP-3550 (HC-13) is a sort-buffer index error at wrap-around, so the allocation was sized by a miscomputed internal
  length rather than input.
- HADOOP-2910 (HC-5) had a count-bounded queue that dropped the oldest call, so it is also HC-2.
- HDFS-11608 (HC-16) is also HC-13 (int overflow).
- MAPREDUCE-3057 (HC-2) was fixed by lowering the default from 2000 to 5 jobs, so it is also HC-8.
- HADOOP-17166 and HADOOP-17195 (HC-7) are per-stream buffers whose defaults scale with CPU count, so they are also HC-8.
- HDFS-14655 and HADOOP-18324 (HC-4) are thread multiplicity as well (HC-7).
- HC-14h overlaps HC-2 where a count cap exists.

## 5. What the project closes as by design (35 by design or invalid, 35 duplicate or not reproduced)

- **Heap sizing is the operator's job.** Small-file growth of DataNode and NameNode state is a sizing question (HDFS-4630
  Invalid). A DataNode block-count cap was declined (HDFS-6088 Won't Fix). So was a stack-size knob for xceiver
  threads (HDFS-4814). JobTracker and TaskTracker footprint work was dropped (MAPREDUCE-2345, MAPREDUCE-2872 Won't
  Fix). AM OOMs are AM memory configuration (MAPREDUCE-5429 Not A Problem). Default LocalJobRunner settings that OOM
  are acceptable (MAPREDUCE-5134 Not A Problem).
- **Callers must close what they open.** The FileSystem cache keyed by UGI identity is by design: use
  `closeAllForUGI` (HADOOP-6843 Not A Problem, HADOOP-12707 Won't Fix, HDFS-3545 open with the same answer).
- **Connection and thread limits are the control.** Thousands of xceiver threads are bounded by `dfs.datanode.max.transfer.threads`
  (HDFS-285 Not A Problem). Native thread OOMs from OS limits are not bugs (HDFS-12936 Not A Bug, HADOOP-8396
  Invalid).
- **JVM and OS memory outside the heap.** Direct-buffer OOM with `-XX:+DisableExplicitGC` (HDFS-3600) and NM RSS growth
  (YARN-6017) were both Not A Problem.
- **Container sizing.** distcp maps killed beyond physical memory were Won't Fix, since raising the default heap would
  break other jobs (HADOOP-14176). ABFS buffering was moved to disk by default as a workaround (HADOOP-18707).
- **Third-party behaviour.** Buggy codecs (HADOOP-9419 Won't Fix) and non-S3 stores that never end a listing
  (HADOOP-16228 Won't Fix) are out of scope.

As for Cassandra, a by-design closure still marks a real shape: most map to HC-7, HC-8, HC-14 or HC-15. It is a clue
whenever a case file shows the same shape **at shipped defaults**. Phase 2 decides whether a documented contract is
broken.

## 6. Open issues (97) and recent clusters

| Cluster | Keys | Shape |
|---|---|---|
| Settings that size an allocation directly | HADOOP-18804, HADOOP-18822, HDFS-17095, HDFS-17096, HDFS-17097 | HC-16 |
| Dispatcher and IPC queues | YARN-270, YARN-371, YARN-4852, YARN-8789, YARN-9929, HADOOP-8942, HADOOP-18389, HADOOP-19386, HDFS-7607 | HC-5 |
| Registrations and leaks in long-lived clients | HADOOP-13971, HADOOP-14907, HDFS-16045, HADOOP-18624, HADOOP-19624, HADOOP-20058 (default S3A analytics stream keeps per-object state), YARN-11397, HDFS-17670 (EC direct buffers never released) | HC-14a |
| Finished work kept in NM and RM state | YARN-494, YARN-10895, YARN-11400, YARN-11698, YARN-8958, YARN-6918, YARN-5370 | HC-14b |
| Native and off-heap growth | YARN-6062, YARN-6470, YARN-7603, HDFS-18006 (short-circuit shared memory), HADOOP-12619, HADOOP-14392 | HC-9, HC-14c |
| Threads per request | HADOOP-16475 (a renewal thread per login), HADOOP-17861, HDFS-18036, YARN-9839, YARN-9955 | HC-7 |
| Shuffle accounting | MAPREDUCE-5580, MAPREDUCE-6447, MAPREDUCE-7075, MAPREDUCE-7277 | HC-1, HC-8 |
| Whole items | MAPREDUCE-2453, MAPREDUCE-4443, MAPREDUCE-7410, YARN-7284, YARN-9739, YARN-11960 | HC-12 |
| No stop at the direct limit | HDFS-5461, HDFS-9598 | HC-6 |

**Variants and incomplete fixes noticed while reading.** These are not candidates by themselves. They show up when
stage 5 reads the matching case.

- **Fixes not in the pinned `rel/release-3.4.2`**: HDFS-17953 (pendingIBRs unbounded), YARN-11967 (pmem check
  skipped), YARN-11808, HADOOP-19862, and HDFS-17909 (check whether the async router exists in 3.4.2).
- **Opt-in fixes whose default path is unchanged**: HADOOP-17531 and HADOOP-17620 (distcp `-useiterator`), YARN-8234
  (batching off), MAPREDUCE-6622 (task-based cache unset), MAPREDUCE-6696 (`-1`), HADOOP-1342 and HADOOP-3144 (limits
  at `MAX_VALUE`).
- **Partial fixes**:
  - HADOOP-6754 only logs a warning.
  - YARN-6188 still builds the full status string.
  - YARN-8404 moves the pile-up into the publisher's dispatcher queue.
  - HADOOP-10081 leaves the SASL length unbounded; HADOOP-10940 bounds the RPC response later.
- **A default that moved toward memory**: HADOOP-18876 made ABFS buffer uploads in memory (bytebuffer), the opposite of
  the HADOOP-18707 workaround.

## 7. Cause patterns → clue patterns

| JIRA cause shape | Fixed | Clue pattern |
|---|---|---|
| HC-1 counter charges a smaller unit | 2 | CP-1 Counted unit ≠ held memory |
| HC-2 items, not bytes (and HC-14h where a count cap exists) | 6 | CP-2 Item count, not bytes |
| HC-3 charge returned before memory freed | 5 | CP-3 Counter released before the memory is freed |
| HC-4 held until response or timeout, answer stalls | 4 | CP-4 Lifetime ends on response or timeout, and a fault stalls it |
| HC-5 queue with a slow, stalled or dead consumer | 14 | CP-5 Accepting queue with a slow, stalled or dead consumer |
| open: no stop at the direct limit (HDFS-5461, HDFS-9598) | — | CP-6 No graceful stop at the limit |
| HC-7 per-owner memory or thread × owners | 18 | CP-7 Per-owner limit × unbounded owners |
| HC-8 defaults or sizes not tied to the heap | 5 | CP-8 Defaults that together over-commit a shared budget |
| HC-9 memory outside the JVM's limits | 4 | CP-9 Memory outside every JVM limit |
| HC-10 path that skips the limit | 1 | CP-10 A path that skips the limit |
| open: allocation before the check (HADOOP-17937) | — | CP-11 Enforcement late, periodic, or after the allocation |
| HC-12 one item materialized whole | 16 | CP-12 One item materialized whole |
| HC-13 size from untrusted, corrupt or miscomputed input | 19 | CP-13 Allocation size from untrusted or corrupt input |
| HC-14 retention past end of life (a–d, h) | 88 | CP-14 Retention past the end of life |
| **HC-15 managed-entity state with no entity cap** | 11 | **none.** CP-7 covers it only loosely: its owners are connections, peers and threads, not the dataset the daemon manages. Proposed new row, below |
| **HC-16 allocation sized by an unchecked configuration value** | 1 (+5 open) | **none.** CP-13 covers lengths from clients, peers and files, not the operator's configuration. Proposed new row, below |

**Proposed `oom-clue-patterns.md` rows** (source `JIRA hadoop`, 2026-11-17). Not added here: the patterns file is
edited by its owner.

- **Managed-entity state with no entity cap.**
  - Shape: a daemon keeps per-entity state for every file, block, replica, task, container or app it manages. Only heap
    sizing bounds the entity count, and any cap ships off.
  - Question: what per-entity state does this holder keep, how many entities exist at a reachable workload, and is the
    cap (if any) on at defaults?
  - Examples: HADOOP-1565, HADOOP-1687, HDFS-1110, HDFS-1114, MAPREDUCE-3567, MAPREDUCE-4301; by design: HDFS-4630,
    HDFS-6088.
- **Allocation sized by an unchecked configuration value.**
  - Shape: a buffer, array, preallocated queue or thread count takes its size straight from a setting checked only for
    `> 0`, or not at all.
  - Question: does an allocation or thread count take its size directly from a configuration value, and what upper
    bound (heap, protocol maximum) is checked before it is used?
  - Examples: HDFS-11608; open: HADOOP-18804, HADOOP-18822, HDFS-17095, HDFS-17096, HDFS-17097.

**Wording gap, not a new shape: a limit that ships disabled.** Cassandra's JC-7 ("a default that leaves a limit off")
was folded into CP-8. CP-8's shape line now speaks only of defaults that over-commit a shared budget. Hadoop has many
fixes whose limit defaults to off (§3 point 4). CP-8, or its question, could name that case explicitly.

## 8. What is left

- **Diffs.** 19 kept Fixed issues have no fix commit in the git history (pre-split SVN, branch-1 only) and 7 have a
  commit with no relevant hunk. These 26 are classified from text. Kept issues that were not fixed (167) have no diff by
  nature.
- **Comments.** For most issues, only the comment passages around OOM terms were read. Full comment threads were read
  for the 32-issue second pass and where the mechanism was unclear.
- **Second pass.** Done by the same reader. An independent second reader has not checked the classifications.
- **Query coverage.** Out of scope: "full GC", "memory pressure" or "GC pause" reports that never name an OOM, and
  related JIRA projects (HDDS/Ozone, Tez, Submarine). Ozone issues filed under HDFS were screened out as tests or
  passing mentions.
- **Variant leads** against `rel/release-3.4.2` were checked only for the five fixes that landed after it (§6).
  Opt-in and partial fixes are noted but were not traced in the pinned source.
