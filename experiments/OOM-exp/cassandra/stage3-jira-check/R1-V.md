# R1-V — stage 3 JIRA check (2026-11-23)

**Case file:** [`../cases/convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md`](../cases/convergence/memtable_offheap_space+file_cache_size--default/memtable_offheap_space+file_cache_size--default.md)
(verdict true positive; current status: condition A-768 on pc96 `verified-OOM · deployment`, researcher 2026-11-16; condition B withdrawn).

**Mechanism checked (case §4 and the 2026-11-16 re-run).** Two off-heap pools, each sized from the heap at its default
(off-heap memtable `memtable_offheap_space` = heap/4 with `offheap_objects`; chunk cache `file_cache_size` = min(512 MiB,
heap/4) with `file_cache_enabled: true`), each within its own cap, together with the heap and the JVM's native baseline
exceed a container limit of 2 × heap: kernel memcg OOM-kill 3/3 at heap 768 / L 1,536 MiB (also 1,024 / 2,048; 1,536 / 3,072
survives). Each pool alone survives; nothing relates the two pools, the heap and the process budget.

**Label: `documented only`**

## Closest issues

| Key | Title | Status / resolution | Created | Fix versions | Fix commit in 5.0.9? | Match | Why |
|---|---|---|---|---|---|---|---|
| CASSANDRA-10930 | Limit off-heap memory | Open (last update 2026-08-26, fixVersion bump; last comment 2017) | 2015-12-23 | 7.x | n.a. | related | Asks to limit off-heap by default or check that RAM > 2 × heap, because the OOM killer may act "if max_mem <= 2*heap"; about the direct-memory default, no pool holder. |
| CASSANDRA-20491 | Document offheap memory used by Cassandra | Open (no comments) | 2025-03-27 | — | n.a. | related | Draft table lists off-heap memtables and the chunk cache with their settings; no sum or budget rule. A documentation request, not a report. |
| CASSANDRA-11681 | Pick a better file_cache_size_in_mb default | Open | 2016-04-28 | — | n.a. | related | Default tuning (upward), not budgets. |
| CASSANDRA-16036 | Add flag to disable chunk cache and disable by default | Resolved / Fixed | 2020-08-07 | 4.0-beta3, 4.0 | yes (4.0 code base) | related | Chunk cache off by default for read performance, not memory; R1-V enables it (documented option). |
| CASSANDRA-8552 / CASSANDRA-8723 | Large compactions run out of off-heap RAM / … memory usage continuously increases until process is killed by OOM | Resolved / Cannot Reproduce | 2015-01-02 / 2015-02-02 | — | n.a. | related | OOM-killer reports on 2.1 without an established holder. |
| CASSANDRA-21529 | Cassandra process is crashing due to OOM errors on direct buffer memory. | Open | 2026-07-20 | — | n.a. | related | `offheap_objects` + 8 GiB chunk cache on 5.0.6, but a JVM direct OOM on a 96 GB VM, not a memcg kill; same "pools sum past the budget" family. |

**Documented:** yes, with sources:
- `conf/cassandra.yaml:747-748` (`file_cache_size`): "Defaults to the smaller of 1/4 of heap or 512MB. This pool is
  allocated off-heap, so is in addition to the memory allocated for heap."
- `conf/cassandra.yaml:792-795` (`memtable_heap_space` / `memtable_offheap_space`): "Total permitted memory to use for
  memtables. … If omitted, Cassandra will set both to 1/4 the size of the heap."
- `doc/modules/cassandra/pages/managing/operating/hardware.adoc:23-26`: "In addition to the heap, Cassandra will use
  significant amounts of RAM offheap for compression metadata, bloom filters, row, key, and counter caches, and an in
  process page cache."
- `doc/modules/cassandra/pages/managing/operating/hardware.adoc:36-37`: "The Cassandra heap should be no less than 2GB, and
  no more than 50% of your system RAM".

**Reason.** No issue reports the two default off-heap pools jointly exceeding a container budget; the closest are general
requests to limit (10930) or document (20491) off-heap memory, both open and unchanged since the 2026-11-16 check. The
shipped docs state each ingredient: both pools are off-heap "in addition to" the heap, both default to ¼ heap, and the
heap should be ≥ 2 GB and ≤ 50 % of RAM. The verified condition keeps the 50 % rule (heap = ½ container) but uses heaps of
768–1,024 MiB, below the documented 2 GB minimum; at 1,536 MiB heap (still below 2 GB) it survives 3/3. So the failing
range lies outside the documented sizing guidance, and the docs warn about the pools' extra memory; that is the basis for
`documented only`. What the docs do not give is a sum rule (heap + memtable off-heap + chunk cache + direct + baseline);
that gap is the subject of 20491. Note: the earlier condition B (heap 60 % of the container) was withdrawn for the same
reason (case header).

## Query log

Snapshot 2026-11-23, `https://issues.apache.org/jira/rest/api/2/search` (no authentication, requests ≥ 2 s apart),
11 JQL queries; hit count = `total` returned. JIRA `text ~` is tokenized, so broad queries (hits > 30) are mostly noise;
their top 50 results were skimmed. Issues read in full (`/rest/api/2/issue/<KEY>`): CASSANDRA-10930, 20491, 16036, 10964.
Fix-commit checks in `~/jira-s3/cassandra-history.git` (`git log --all --grep`, `git merge-base --is-ancestor <commit> cassandra-5.0.9`).

| # | JQL | Hits |
|---|---|---|
| 1 | `project = CASSANDRA AND (text ~ "file_cache_size" AND (text ~ "OOM killer" OR text ~ "oom-killer" OR text ~ oomkiller))` | 5 |
| 2 | `project = CASSANDRA AND (text ~ "offheap_objects" AND (text ~ "OOM killer" OR text ~ "oom-killer" OR text ~ RSS))` | 0 |
| 3 | `project = CASSANDRA AND (text ~ "memtable_offheap_space" AND text ~ "file_cache_size")` | 35 |
| 4 | `project = CASSANDRA AND (text ~ "chunk cache" AND (text ~ RSS OR text ~ "off-heap" ) AND (text ~ OOM OR text ~ killed))` | 16 |
| 5 | `project = CASSANDRA AND ((text ~ container OR text ~ cgroup OR text ~ kubernetes) AND text ~ "off-heap" AND (text ~ OOM OR text ~ "memory limit"))` | 50 |
| 6 | `project = CASSANDRA AND ((text ~ "oom-killer" OR text ~ "OOM killer" OR text ~ "oom_kill") AND created >= 2024-01-01)` | 10 |
| 7 | `project = CASSANDRA AND (text ~ "file_cache_enabled" AND (text ~ memory OR text ~ OOM))` | 77 |
| 8 | `project = CASSANDRA AND ((summary ~ offheap OR summary ~ "off heap") AND summary ~ memory)` | 9 |
| 9 | `project = CASSANDRA AND (created >= 2026-11-10 AND (text ~ OOM OR text ~ OutOfMemoryError OR text ~ memory OR text ~ heap OR text ~ "direct buffer" OR text ~ "off-heap"))` *(shared sweep, all eight cases)* | 5 |
| 10 | `project = CASSANDRA AND (updated >= 2026-11-16 AND key in (CASSANDRA-11082, CASSANDRA-21656, CASSANDRA-19958, CASSANDRA-13213, CASSANDRA-10930, CASSANDRA-20491, CASSANDRA-21529, CASSANDRA-7402))` *(shared sweep, all eight cases)* | 0 |
| 11 | `key in (CASSANDRA-21508, CASSANDRA-15066, CASSANDRA-9318, CASSANDRA-7402, CASSANDRA-15375, CASSANDRA-18304, CASSANDRA-6510, CASSANDRA-4753, CASSANDRA-19534, CASSANDRA-16471, CASSANDRA-11937, CASSANDRA-10971, CASSANDRA-21535, CASSANDRA-15358, CASSANDRA-20296, CASSANDRA-19535, CASSANDRA-11681, CASSANDRA-20565, CASSANDRA-8757, CASSANDRA-12699, CASSANDRA-10821, CASSANDRA-20551, CASSANDRA-21522, CASSANDRA-7937)` *(shared sweep, all eight cases)* | 24 |
