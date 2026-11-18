# Cassandra JIRA OOM report

*Written 2026-11-17* for stage 5 ([`../../stage5-oom-clue-find/README.md`](../../stage5-oom-clue-find/README.md)), method
[`jira-mining.md`](../../stage5-oom-clue-find/jira-mining.md). This is the analysis of Cassandra's own JIRA history of
out-of-memory failures, written to build the system-agnostic
[OOM clue patterns](../../stage5-oom-clue-find/oom-clue-patterns.md) (`CP-` IDs, §7). It is read only: **nothing is
ever posted to JIRA** or reported upstream.

**Data** (in this folder): [`jira-oom-survey.csv`](jira-oom-survey.csv) (one row per issue, 604 rows: screen, flow,
budget, trigger, control, class, fix kind, notes), [`jira-oom-survey.md`](jira-oom-survey.md) (the survey's own summary,
positive-control shortlist and variant leads), [`jira-oom-survey-second-pass.md`](jira-oom-survey-second-pass.md) (the
quality check), [`jira-prior-art-verified-cases.md`](jira-prior-art-verified-cases.md) (prior art for the phase-2 cases).
Issue numbers below are CASSANDRA-*n*.

## 1. Scope and queries

| Pass | Date | Query (`issues.apache.org/jira`, REST search) | Hits |
|---|---|---|---|
| Survey | 2026-11-16 | `project = CASSANDRA AND (text ~ "OutOfMemoryError" OR text ~ "OOM" OR summary ~ "out of memory" OR text ~ "\"Direct buffer memory\"" OR text ~ "\"GC overhead limit\"" OR text ~ "\"oom-killer\"")` | **604** |
| First pass (superseded) | 2026-11-12 | the same query; title and description only, no diffs | 604 |
| Targeted checks | 2026-11-17 | per-lead queries, e.g. `text ~ "segment_write_buffer_size"` (60), `text ~ "index summary" AND (upsample …)` (22), `text ~ "scratchBuffer" OR …` (14), `text ~ "reserve_global_capacity"` (13), `text ~ "offheap_objects" AND (…)` (42) | per query |

Resolutions of the 604: Fixed 347, Unresolved 82, Duplicate 50, Won't Fix 41, Cannot Reproduce 27, Not A Problem 26,
Invalid 14, Later 7, Not A Bug 5, other 5.

**Screen.** An issue is kept when the server itself ran out of memory (heap, direct, native, or a kernel/cgroup kill) and
that is the reported problem. Excluded: test, CI and build memory; client, driver and tool memory; issues about OOM
handling only (heap-dump flags, `OnOutOfMemoryError`); issues where OOM appears only in passing. Every excluded issue
keeps a row with its reason. **246 kept**:

| Resolution group | Kept |
|---|---|
| Fixed | 120 |
| Open (Unresolved 42, Later 3) | 45 |
| Closed without a fix: by design or invalid (Won't Fix 17, Not A Problem 13, Invalid 8, Not A Bug 4, other 3) | 45 |
| Closed without a fix: Duplicate 26, Cannot Reproduce 10 | 36 |

## 2. How issues were classified

- **Reading.** Four agents read about 151 issues each, description and all comments.
- **Fix diffs.** For each kept Fixed issue the fix commit was found in a full clone of `apache/cassandra` by issue key
  (or by commits named in comments): **115 of 120** have their diff read; 5 have no commit. A class rests on the
  issue text and the diff, not the title.
- **Columns.** `flow` (where in the data path the memory grows), `budget` (heap, direct, native, cgroup/kernel),
  `trigger` (workload, data shape, failure event, configuration), `control_before` (what was meant to bound it),
  `class`, `fix_kind`, `config_involved`.
- **Classes** (the capacity-enforcement vocabulary): `unprotected:accumulation` (no control applies),
  `unprotected:configuration` (a control exists but its default leaves it off or unbounded),
  `bypass:accounting-mismatch`, `bypass:release-defect` (leak inside a capped pool), `bypass:late-enforcement`,
  `bypass:exempt-path`, `convergence:multiplicity` (needs an explicit per-owner cap), `convergence:standing-pool`.
- **Second pass.** One agent normalized conventions across the four shards, read the diffs of 36 rows first classified
  from commit subjects, and spot-checked a seeded random sample of 25 kept and 15 excluded issues. Agreement: screen
  39/40, class 25/25 on mechanism (23/25 strictly; both differences come from the convention change), fix kind 24/25.
  One excluded issue (11845) was re-screened in.
- **Cause patterns (this report).** The classes say *how a control failed*; for clue finding we also need the *shape of
  the code* that grew. For §4 each of the 120 Fixed issues was given one primary cause shape from its trigger,
  `control_before` and fix (CSV columns), refining the first pass's six shapes. Assignment is one reader's judgment;
  borderline cases are noted in §4.

Class counts (kept / of which Fixed):

| Class | Kept | Fixed |
|---|---|---|
| unprotected:accumulation | 131 | 72 |
| unknown (cause never established) | 42 | 2 |
| unprotected:configuration | 22 | 4 |
| bypass:accounting-mismatch | 18 | 16 |
| convergence:multiplicity | 14 | 10 |
| bypass:release-defect | 8 | 8 |
| bypass:late-enforcement | 5 | 4 |
| bypass:exempt-path | 4 | 2 |
| convergence:standing-pool | 2 | 2 |

Budget (kept): heap 197, direct 19, native 17, cgroup/kernel 12, unknown 1. Flows (kept): replica mutation stage →
memtable → flush 54, read path and caches 39, repair/streaming 30, compaction 28, client request intake 28,
coordinator read 19, coordinator write 11, internode messaging 9, hints 8, other or unknown 20.
Fix kind (Fixed): other code change 46, release fix 23, new limit 18, accounting change 14, doc or default change 11,
backpressure 6, none 2. `config_involved` = yes in 66 of 246 (27 %), mostly a default size or an OS limit
(`vm.max_map_count`, ulimit) rather than a user's mistaken value.

## 3. What the history says, in short

1. **Most real OOMs are unprotected accumulation** (153 of 246 with the configuration subclass): memory no control
   covers, grown by a data or workload shape (wide partitions, large cells, many sstables or tables, deletes, repair
   over many ranges). A constraint-by-constraint inventory sees these only where a case file's holder sits next to the
   unbounded one.
2. **Accounting mismatch is the most common bypass** (18 kept, 16 fixed), and it recurs on the same holders: deletes
   not counted in memtables were fixed three times (3741 → 6655 → 9194).
3. **Fixes rarely add limits** (18 new limits and 6 backpressure of 120). Most remove one allocation or release a
   leaked reference, so siblings of a fixed path stay worth checking.
4. **Direct and native memory are a small share (36 of 246) but hold most recent and open issues** (21529, 21656,
   19535, 17025, 18762).
5. **The trigger is usually a workload or data shape**, not one misconfigured value; a misconfiguration is the direct
   trigger mainly in default sizing (§4, JC-7) and OS limits.

## 4. Cause patterns in the 120 Fixed issues

| ID | Cause shape | Fixed | Budget | Representative keys | Typical shape |
|---|---|---|---|---|---|
| JC-1 | Counter charges a smaller unit than the memory held | 11 | heap 9, native 2 | 3741, 6655, 9194, 4315, 4860, 6078, 6149, 16071, 4201, 20298 | deletes charged as 0 bytes; cache weigher counts the value only (4315) or 24 B per row (4860); live-ratio estimate capped; a MiB setting read as bytes (16071); slab regions charged by requested bytes (20298, test-only fix) |
| JC-2 | Limit counts items, not bytes | 4 | heap 4 | 2652, 3624, 8639, 6107 | hint pages sized in columns while columns are huge; commit-log replay bounded by 1000 mutations; prepared cache bounded by entry count |
| JC-3 | Charge returned before the memory is freed (leak inside a capped pool) | 9 | heap 9 | 157, 8164, 12358, 11026, 3163, 11159, 12796 | a flushed memtable still referenced (MBean, index summary, sstable min/max slices pin slabs); memory released in accounting before a slow 2i flush frees it |
| JC-4 | Held until a response or timeout, and the answer stalls | 5 | heap 5 | 8969, 9318, 3537, 1607, 3440 | coordinator keeps in-flight requests for the timeout; an expiry timer that died keeps all callbacks; writes at CL ZERO had no ack to throttle |
| JC-5 | Queue keeps accepting while its consumer is slow, stalled or dead | 13 | heap 12, direct 1 | 401, 685, 885, 10971, 10972, 12689, 14855, 9525, 20084, 8245 | stage queues unbounded; compressed commit log and file hints had no backpressure; MV lock stalls all MutationStage threads; native Flusher fell off the event loop; a dead commit-log allocator thread |
| JC-6 | Per-owner memory × an unbounded number of owners | 19 | heap 15, direct 3, native 1 | 3171, 4142, 5661, 6191, 10797, 2006, 13754, 7743, 15452, 14096, 15202, 19336, 20577, 20752, 13008 | 1 MB buffer or scanner per sstable; per-table memtables with no server-wide cap; per-thread retained builders and Netty caches; Merkle trees × ranges × tables; mmap regions per sstable vs `vm.max_map_count` |
| JC-7 | Defaults too large for the heap, or a default that leaves a limit off | 8 | heap 7, direct 1 | 1469, 1641, 2413, 6059, 2142, 11710, 8116 | memtable and cache defaults OOM small heaps; a 512 MiB file-cache default above a small direct limit (11710); `rpc_max_threads` unlimited by default |
| JC-8 | Memory outside the JVM's limits | 2 | native 1, cgroup 1 | 2868, 9573 | JDK native leak; mmap of many sstables at startup (most issues of this shape are open or closed unfixed, §5–§6) |
| JC-9 | A path that skips the limit | 2 | heap 2 | 609, 20052 | commit-log replay ignored memtable limits; protocol v5 messages had no size limit, even before auth |
| JC-10 | Limit enforced late, by a background or periodic actor | 4 | heap 4 | 5982, 6079, 8285, 6087 | memtable cap enforced by a meter/flusher on a shared, delayed thread; flusher not started until after replay |
| JC-11 | One item materialized whole | 15 | heap 15 | 16, 208, 4098, 4116, 4314, 4415, 8559, 11383, 12268, 13299, 14925, 16201, 2849 | wide row compacted in memory; unpaged results; whole index segment stitched in RAM; a tombstone warning string of 777 MB (8559); a decimal rendered with a huge scale (14925); a wide partition streamed into an MV as one mutation (13299) |
| JC-12 | Allocation sized from untrusted or corrupt input | 11 | heap 11 | 475, 3017, 12618, 12769, 9530, 18513, 264, 5706, 6260, 9265, 4555 | a 4-byte length or count from a client, peer or file trusted as an allocation size |
| JC-13 | Retention past the end of life (leak with no capped pool) | 11 | heap 8, native 2, direct 1 | 2708, 6047, 8499, 9549, 11739, 11854, 14834, 15902, 17895, 21474 | a map never cleared on drop; release missing on abort or failure paths; repair threads not closed after termination; an unbounded log de-duplication cache (21474, fixed only in 6.0/7.0) |
| — | No reusable shape | 6 | — | 7310, 7546, 7983, 11034, 11344, 19356 | cause unknown; CAS spin-loop garbage; an infinite loop; bloom filters sized from a 6–10× over-estimate; Accord state |

Borderline assignments: 13299 (JC-11) is also a path skip (the mutation size limit applies only to the commit log);
13754 (JC-6) is also retention (thread-local builders); 4098 and 4415 (JC-11) are also row-count limits (JC-2);
8116 (JC-7) is also a per-thread multiplicity. The first pass's six shapes map as: *one large item* → JC-11 and JC-12;
*queue without backpressure* → JC-4 and JC-5; *per-object × count* → JC-6; *leak or release on the wrong path* →
JC-3 and JC-13; *the limit counts the wrong thing* → JC-1 and JC-2; *defaults too large* → JC-7.

## 5. What the project closes as by design (45 by design or invalid, 36 duplicate or not reproduced)

- **No global heap governor.** Requests to block requests when the heap is nearly full (4505–4510, 4510 Won't Fix),
  basic QoS (3911), a default per-request byte limit (9413: "defeated by concurrency"), a bytes clause for queries
  (4304, Later), sane bounds on every `BlockingQueue` (5039, superseded by 9318) and heap-pressure reaction (2875) were
  all declined. The project relies on per-mechanism limits and operator sizing.
- **Client-chosen size is the client's problem.** Range or slice queries that ask for more rows than fit (691, 3861,
  4743, 5336), long batches (7303), a hot partition under write load (10937), large partitions with the row cache
  (10615): Not A Problem / Won't Fix, "page, or use the limit you need".
- **Overload is shed by timeouts, not queues.** 6346 (Not A Problem: lower the write timeout; see 685 for why stage
  queues are unbounded) and 11460 (60 GB MutationStage, Won't Fix).
- **Operating-system and sizing problems are not bugs.** "Map failed" from `vm.max_map_count` (14474 Not A Problem;
  12009, 13523, 16243 open), direct-memory OOMs (17025 Invalid, pointing at `jdk.nio.maxCachedBufferSize`; 18762,
  19535 Cannot Reproduce), RSS growth to a kernel kill (8723, 11109 Cannot Reproduce; 20565 Not A Bug).
- **Features off by default are out of scope.** UDF heap exhaustion (21227, 21233 Not A Bug: UDFs are disabled and
  trusted); MV mutation size (12783, open; MVs are experimental).

Consequence for clue finding: a by-design closure still marks a real shape (most map to JC-5, JC-6, JC-8 or JC-11).
It is a clue whenever a case file shows the same shape **at shipped defaults**; phase 2 decides whether a documented
contract is broken.

## 6. Open issues (45) and recent clusters

| Cluster | Keys | Shape |
|---|---|---|
| Direct pools and Netty | 21529 (BufferPool at 16.6 of 16.6 GB direct), 11082 (Netty water marks set, not checked), 13126, 15006, 16154 (cache transiently past its maximum) | JC-6/JC-8, no graceful stop at the limit |
| JVM limits vs the machine | 10930 (limit off-heap memory), 10689, 13931, 19976 (no `jdk.nio.maxCachedBufferSize`), 15531, 8763, 12699 | memory outside the JVM limits |
| Lengths from input | 8052, 14433 (PagingState), 14997 (client decompression length, before auth) | JC-12 |
| Large items and paging | 9754, 11528, 12783, 15250 (IN cartesian product; guardrail added later, off by default), 16764 | JC-11, JC-2 |
| Many copies × peers | 11748, 14840 (schema copies per peer at bootstrap) | JC-6 |
| Skipped checks | 12707 (tombstone threshold not applied in one loop), 21401 (decimal aggregates skip the precision cap) | JC-9 |
| Unbounded collections | 19959 | JC-13 |

Not reproduced with a real symptom (8152, 8552, 8723, 11109, 18762, 19535, 20565) are native or kernel-side growth
with no explanation; they are the history's least understood shape.

## 7. Cause patterns → clue patterns

Each JC shape is covered by one `CP-` pattern in
[`oom-clue-patterns.md`](../../stage5-oom-clue-find/oom-clue-patterns.md) (source `JIRA cassandra`). Shapes that the
JIRA history shows only as open or unfixed issues still count as JIRA-sourced.

| JIRA cause shape | Fixed | Clue pattern |
|---|---|---|
| JC-1 counter charges a smaller unit | 11 | CP-1 Counted unit ≠ held memory |
| JC-2 items, not bytes | 4 | CP-2 Item count, not bytes |
| JC-3 charge returned before memory freed | 9 | CP-3 Counter released before the memory is freed |
| JC-4 held until response or timeout, answer stalls | 5 | CP-4 Lifetime ends on response or timeout, and a fault stalls it |
| JC-5 queue with a slow, stalled or dead consumer | 13 | CP-5 Accepting queue with a slow, stalled or dead consumer |
| open: water marks unchecked, overflow past a pool (11082, 21529, 16154; 11710) | — | CP-6 No graceful stop at the limit |
| JC-6 per-owner × owners | 19 | CP-7 Per-owner limit × unbounded owners |
| JC-7 defaults too large / limit off by default | 8 | CP-8 Defaults that together over-commit a shared budget |
| JC-8 memory outside the JVM's limits (+ open §6) | 2 | CP-9 Memory outside every JVM limit |
| JC-9 path that skips the limit | 2 | CP-10 A path that skips the limit |
| JC-10 late enforcement | 4 | CP-11 Enforcement late, periodic, or after the allocation |
| JC-11 one item materialized whole | 15 | CP-12 One item materialized whole |
| JC-12 size from untrusted or corrupt input | 11 | CP-13 Allocation size from untrusted or corrupt input |
| JC-13 retention past end of life | 11 | CP-14 Retention past the end of life |
