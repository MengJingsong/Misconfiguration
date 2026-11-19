# U10 — DEFAULT_PAGE_SIZE (aggregate internal paging): a plain aggregate with paging off is read as one sub-read into one replica buffer  <!-- file: cassandra/cases/default_page_size--unpaged-aggregate-whole-partition/default_page_size--unpaged-aggregate-whole-partition.md -->

| Field | Value |
|---|---|
| Case ID | `U10` (U = unprotected accumulation / unprotected configuration; README "ID prefixes") |
| From | cluster of phase-1 candidates, primary **`OC-322`**; with OC-309, OC-44, OC-298, OC-299, OC-310, OC-311, OC-312, OC-313, OC-314, OC-315, OC-316, OC-317, OC-318, OC-321 (rows quoted in §1; coverage table there) |
| Phase-1 case file | primary [`default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md); cluster also [`group-limit-isdone-groupcounted--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/group-limit-isdone-groupcounted--autonomous.md), [`group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous.md), [`group-by-limit-incrementGroupCount-groupLimit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/group-by-limit-incrementGroupCount-groupLimit--autonomous.md), [`group-by-row-limit-incrementRowCount-rowsCounted--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/group-by-row-limit-incrementRowCount-rowsCounted--autonomous.md), [`group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous.md), [`per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous.md), [`page_size_fail_threshold-execute-pageSize--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/page_size_fail_threshold-execute-pageSize--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, `build.xml` `base.version` 5.0.9); built copy `pc82:/mydata/s4/cassandra-base` (`build/apache-cassandra-5.0.9-SNAPSHOT.jar`, copied from `pc96` and smoke-tested 2026-11-18) |
| Stage 1 (design) | phase-2 OOM agent, stage 1, 2026-11-18 13:40–14:30 EST; nothing run (pc82 checked read-only) |
| Stage 2 (verify) | phase-2 OOM agent, stage 2 (fresh session), 2026-11-18 13:53–15:35 EST on `pc82`; freeze hash checked (match) |
| Verdict | **true positive** — `verified-OOM · deployment` (unprotected configuration + bypass of the internal row bound) |

## Summary

- **Conclusion:** **true positive** (`verified-OOM · deployment`). At shipped defaults and a 2 GiB heap / 1 GiB direct
  (the full `cassandra-env.sh` resolution of a 4 GiB node), **one** unpaged `SELECT count(v) … WHERE pk = ? AND ck < 65536`
  (≈ 1 GiB of 16 KiB rows) kills the node with `java.lang.OutOfMemoryError: Java heap space` in **3/3** runs; the same
  query with the driver's default 5,000-row paging survives 3/3 (≈ 40 correct counts each), the shipped byte threshold
  switched on (I1) stops it 3/3 by refusing every query, and applying the stated 10,000-row internal paging (I2,
  diagnostic build) stops it 3/3 with every count correct. The budget search fails at 2/4/8/16 GiB heaps (c = 1/2/4/10
  concurrent queries; 16 GiB 3/3); at 31 GiB (pc82's own resolution) no OOM up to c = 48, where the 5 s read timeout
  cancels every read before its buffer outgrows the heap (boundary).
- **Root cause:** a plain aggregate sent with paging off is paged internally with `NO_LIMIT` (the `DEFAULT_PAGE_SIZE`
  fallback that the code comment says is there "to avoid OOM" is applied only to GROUP BY), so the replica serializes the
  whole selected slice into **one** heap `DataOutputBuffer` (`LocalDataResponse.build`; growth ×1.5 to 487 → 730 →
  1,096 MiB arrays). The byte control that would bound it (`read_thresholds_enabled`) ships off; nothing sums the
  buffers of concurrent reads; the only bound left is the 5 s read timeout, which caps time, not bytes.

## 1. Candidate

**Cluster rows (quoted verbatim from
[`phase1-oom-candidates.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md);
`[details]` links repointed so they resolve from this folder; full texts in
[`runs/wave2.md`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md), OC-44 inline):**

> | ID | Date | Phase-1 case file | Agent | Clue (mechanism, rough magnitude at defaults) | Patterns | Status |
> |---|---|---|---|---|---|---|
> | OC-322 | 2026-11-18 | `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` | guided | A plain aggregate with paging off is not paged internally, although the code comment says aggregation is "always paged internally to avoid OOM". [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-322) | CP-10, CP-12, CP-6 | picked: U10 |
> | OC-309 | 2026-11-18 | `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` | autonomous | A plain aggregate with no GROUP BY (AGGREGATE_EVERYTHING, e.g. `SELECT count(v) FROM t WHERE pk=?`) run with paging off is not paged internally, despite the 'always paged internally to avoid OOM' comment. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-309) | — | picked: U10 |
> | OC-44 | 2026-11-16 | `page_size_fail_threshold-execute-pageSize--autonomous` | legacy | [lead list ×2 (blind, E1+E2/E2): `SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize`, `page_size_fail_threshold-execute-pageSize`; N17 cluster; queued as U4] Paging-off or LIMIT ≤ fetch-size queries and aggregates without GROUP BY take the unpaged branch (`SelectStatement.java:338`), which never calls the page-size guard (`:517`), so one read serializes a whole partition into one heap array (stage 4: 411 MB in a 514 MB array; ≈ 1.15 GiB allocated for 100k × 2 KiB rows), up to ≈ 2 GiB per query × 32 concurrent reads. | CP-10, CP-12 | picked: U10 |
> | OC-298 | 2026-11-18 | `group-limit-isdone-groupcounted--autonomous` | autonomous | Holder: the coordinator's ResultSet for a GROUP BY query run with client paging off. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-298) | — | picked: U10 |
> | OC-299 | 2026-11-18 | `group-per-partition-limit-isdoneforpartition-groupinCurrentPartition--autonomous` | autonomous | Holder: each GROUP BY internal sub-page, serialized whole on the replica into one heap DataOutputBuffer (LocalDataResponse) and then deserialized on the coordinator. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-299) | — | picked: U10 |
> | OC-310 | 2026-11-18 | `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` | autonomous | DEFAULT_PAGE_SIZE caps each internal GROUP BY sub-read at 10000 rows, not bytes. Each sub-read is serialized in full into one replica buffer and then deserialized at the coordinator. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-310) | — | picked: U10 |
> | OC-311 | 2026-11-18 | `default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous` | autonomous | An unpaged GROUP BY keeps every result group on the coordinator. GroupByPartitionIterator turns a page size of 0 or less into NO_LIMIT groups and keeps pulling 10000-row sub-pages until the data ends. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-311) | — | picked: U10 |
> | OC-312 | 2026-11-18 | `group-by-limit-incrementGroupCount-groupLimit--autonomous` | autonomous | groupLimit is NO_LIMIT when the query has no LIMIT. With paging off, the GROUP BY pager also turns the page size into NO_LIMIT groups, so the coordinator keeps one ResultSet row per group for the whole scan. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-312) | — | picked: U10 |
> | OC-313 | 2026-11-18 | `group-by-limit-incrementGroupCount-groupLimit--autonomous` | autonomous | The group limit never stops a group in progress. Inside one group, the only stop is rowLimit (the page size, 10000 by default), which counts rows, not bytes. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-313) | — | picked: U10 |
> | OC-314 | 2026-11-18 | `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` | autonomous | rowLimit is set straight from the client fetch size, with no upper bound by default (page_size_warn/fail_threshold -1, and superusers skip guardrails anyway). [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-314) | — | picked: U10 |
> | OC-315 | 2026-11-18 | `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` | autonomous | With paging off, the top-level GROUP BY page is NO_LIMIT groups. Sub-reads are chunked at 10000 rows, but every group's output row stays in the coordinator ResultSet until the end. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-315) | — | picked: U10 |
> | OC-316 | 2026-11-18 | `group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous` | autonomous | groupPerPartitionLimit defaults to NO_LIMIT, and under GROUP BY <partition key> the check at :1000 is never reached. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-316) | — | picked: U10 |
> | OC-317 | 2026-11-18 | `group-per-partition-limit-incrementGroupInCurrentPartitionCount-groupPerPartitionLimit--autonomous` | autonomous | A group that spans a whole partition is not capped by this limit. It is read in sub-reads of rowLimit rows (10000 by default, or the client fetch size, which is unbounded at defaults), and each sub-read is serialized whole into one replica buffer. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-317) | — | picked: U10 |
> | OC-318 | 2026-11-18 | `per-partition-limit-incrementRowCount-rowsincurrentpartition--autonomous` | autonomous | perPartitionLimit counts live rows per partition, not bytes, and defaults to NO_LIMIT. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-318) | — | picked: U10 |
> | OC-321 | 2026-11-18 | `group-by-row-limit-incrementRowCount-rowsCounted--autonomous` | guided | GROUP BY internal sub-read sized in rows only. Holder: each internal sub-read of a GROUP BY is held whole, as one replica DataOutputBuffer and then a decode-and-merge on the coordinator. [details](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/runs/wave2.md#oc-321) | CP-2, CP-12, CP-8, CP-6, CP-7 | picked: U10 |

**Coverage of the cluster by this design** (the shared mechanism: aggregate and GROUP BY reads are bounded only in
rows, never in bytes, and with client paging off the row bound itself is removed or replaced by an internal count; the
read-size thresholds ship off):

| Row | Holder and bound claimed | Covered here? |
|---|---|---|
| **OC-322** (primary) | plain aggregate, paging off → one sub-read of NO_LIMIT rows → whole slice in one replica buffer | **yes** — arms T/M/I and the budget search |
| OC-309 | same as OC-322 (AGGREGATE_EVERYTHING, `AggregationPartitionIterator` keeps NO_LIMIT) | **yes** (same path, same holder) |
| OC-44 | "aggregates without GROUP BY take the unpaged branch (`:338`)" + paging-off / LIMIT ≤ fetch SELECTs | **aggregate part yes**, with a correction: plain aggregates take the pager branch (`SelectStatement.java:342-355`, `aggregationSpec` = `AGGREGATE_EVERYTHING` ≠ null), not `:338`; the sub-page is NO_LIMIT, so the effect is the same (one read of everything; `SelectStatement_DEFAULT_PAGE_SIZE` stage 4: one 411 MB response in a 514 MB array). **Non-aggregate part not covered**: a SELECT with paging off returns what the client asked for; its holder (replica buffer + `ResultSet`) is U4's |
| OC-298, OC-311, OC-312, OC-315, OC-316 | unpaged GROUP BY: top-level page NO_LIMIT groups; coordinator `ResultSet` keeps one output row per group across chunked sub-reads | **no** (not in the verdict). Optional coverage probe `P-GRS` (§2) runs one sweep at 2 GiB and is reported as a note only |
| OC-299, OC-310, OC-313, OC-314, OC-317, OC-321 | GROUP BY internal sub-read bounded only by rows (DEFAULT_PAGE_SIZE 10,000 or the client fetch size), held whole in one replica buffer | **no**. Same holder and same row-count bound as verified **U4** (only the source of the row count differs); the optional intervention `I2` uses this 10,000-row bound as its repaired state at one row width and multiplicity, which is not a test of it |
| OC-318 | PER PARTITION LIMIT counts rows; a page is held twice | **no**. It only lowers U4's row count; U4's holder and result apply |

**Phase-1 constraint and check (primary).** `SelectStatement.DEFAULT_PAGE_SIZE = 10000` (`SelectStatement.java:114`),
substituted for a non-positive page size in `getDataLimits` (`:899-902`, comment "Group by and aggregation queries will
always be paged internally to avoid OOM") and then used only for `groupByLimits` (`:906-914`); a plain aggregate returns
`DataLimits.cqlLimits(NO_LIMIT, NO_LIMIT)` (`:890-896`, `:919`). In `execute` a plain aggregate has
`aggregationSpec = AGGREGATE_EVERYTHING` (`:1447-1449`), so it skips the unpaged branch (`:338`) and takes the pager
(`:342-355`) → `AggregationQueryPager.fetchPage` → `AggregationPartitionIterator(pageSize = -1)` (`AggregationQueryPager.java:59-62`),
whose constructor maps `pageSize <= 0` to `NO_LIMIT` (`:186`, `:193-197`) and whose `computeSubPageSize` returns that value
unchanged and `isDone` is always false (`:425-441`). The first sub-page is fetched with `NO_LIMIT` (`:229-231`), i.e. one
`SinglePartitionReadCommand` over the whole slice. Locally it runs in `StorageProxy.LocalReadRunnable`
(`AbstractReadExecutor.java:165`, inline when a READ permit is free), whose response is `LocalDataResponse.build`: one
`DataOutputBuffer` holding the serialized result (`ReadResponse.java:197-201`; growth `DataOutputBuffer.java:158-180`:
×2 up to 64 MiB, then ×1.5, old and new arrays both live during the copy; cap `MAX_ARRAY_SIZE` = 2^31 − 9, beyond it
`BufferOverflowException`). The stage-3 estimate for the primary was `positive` (the constant caps GROUP BY sub-reads)
with the plain-aggregate non-cap filed as an open point.

**Phase-1 stage 4 (evidence; results of the same stems).**
- [`default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/default_page_size-cqlgroupbylimits_onclose-rowlimit--autonomous.md)
  (pc39, 2026-10-27, true positive for the GROUP BY cap): GROUP BY sub-reads = constant rows (+2 MB / +247 MB / death for
  K = 500 / 10,000 / 200,000 on a 512 MB heap, 2,000,000 × 1 KiB rows); **plain `count(payload)` with the page size
  unset killed the 512 MB node 9/9 on every build after 1.5–1.6 s** (`Pause Full (G1 Humongous Allocation) 299M->299M`;
  death read as OOM from the GC log, no log line — `kill -9`). Unit: the plain aggregate made one raw read of all 200,000
  rows for every constant and page size.
- [`SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/SelectStatement_DEFAULT_PAGE_SIZE-getDataLimits-pageSize--autonomous.md)
  (the OC-44 lead's other stem): with paging off the aggregate makes **1 read whose response is 411,281,225 B (100,000
  rows) in a 513,589,248-byte heap array**.
- [`page_size_fail_threshold-execute-pageSize--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/page_size_fail_threshold-execute-pageSize--autonomous.md)
  (OC-44): paging-off SELECTs are never checked by the page-size guardrail (100,000 × 2 KiB rows, heap Δ 1,168 MiB).
- GROUP BY stems (OC-298 … OC-321): `group-by-row-limit-…` true positive (the row limit caps rows per sub-read, bytes
  follow row width); `group-limit-…`, `group-by-limit-…`, `group-per-partition-limit-incrementGroup…`,
  `per-partition-limit-…` true negative (those limits do not cap memory); `group-per-partition-limit-isdoneforpartition-…`
  undetermined. No stage 4 applied concurrency or an acceptable budget; no OOM was recorded with an error line.

**Contract and defaults (checked against the pinned source, 2026-11-18).** `read_thresholds_enabled = false`
(`Config.java:526`), `local_read_size_fail_threshold = null` (`:530`; yaml `# read_thresholds_enabled: false # scheduled
to be set true in 4.2`, `cassandra.yaml:2015`); `page_size_fail_threshold = -1` (`Config.java:874`; and it counts rows,
`Guardrails.pageSize.guard(pageSize …)` at `SelectStatement.java:517` sees `-1`); `partition_size_fail_threshold = null`
(`Config.java:911`, a write/compaction-time guardrail, not a read bound); `read_request_timeout = 5000ms`
(`Config.java:145`), enforced on a local read by `LocalReadRunnable` (`StorageProxy.java:2204-2205`) and
`QueryCancellationChecker.maybeCancel` per row (`ReadCommand.java:777-792`): the read is aborted and its buffer dropped
once 5 s have passed since the request started (`QueryCancelledException`, logged at DEBUG "Query cancelled (timeout)");
`concurrent_reads = 32` (`Config.java:179`), `native_transport_max_threads` 128 (`cassandra.yaml:1035`, commented
default). Client side: the Java driver 3.12.1 (in the build, `build/lib/jars/cassandra-driver-core-3.12.1-shaded.jar`)
maps `setFetchSize(Integer.MAX_VALUE)` to page size `-1` and then omits the `PAGE_SIZE` flag (checked with `javap` on
pc82, 2026-11-18: `SessionManager.makeRequestMessage` offsets 279–288; `Requests$QueryProtocolOptions` adds `PAGE_SIZE`
only when `pageSize >= 0`), so the server sees `options.getPageSize() = -1`; cqlsh `PAGING OFF` and the Python driver's
`fetch_size = None` do the same.

**JIRA prior art (read only; nothing posted).** Survey
[`jira-oom-survey.csv`](../../../../capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv):
**4415** (*Add cursor API/auto paging*, Fixed 2.0 beta 1: its last commit paged `count(*)` internally to stop OOMs),
**5336** (unpaged count over a wide table via ODBC, Not A Problem: client must page), **11528** (*Server Crash when select
returns more than a few hundred rows*, Unresolved: `SELECT *`/`count(*)` over 100 KB–4 MB blobs, internal paging by rows),
**9413** (*Add a default limit size (in bytes) for requests*, Won't Fix: a per-request cap is defeated by concurrency),
4304 (bytes-limit clause, Later), 6052 (unpaged huge LIMIT, Duplicate). JIRA REST, 2026-11-18 13:55 EST:
`project = CASSANDRA AND (text ~ "aggregate" OR text ~ "aggregation" OR text ~ "count(*)") AND (text ~ "paging" OR text ~
"page size" OR text ~ "fetch size") AND (text ~ OOM OR text ~ OutOfMemoryError OR text ~ "out of memory")` (133 hits; read
the 50 most relevant) and `text ~ "AggregationQueryPager" OR "paged internally" OR "AggregationPartitionIterator"`
(6 hits). Relevant: **CASSANDRA-10707** (GROUP BY, Fixed 3.10; B. Lerer 2016-01-20: "Group by queries are always paged
internally to avoid OOMExceptions"), **CASSANDRA-9724** (2015, Not A Problem; R. Stupp: aggregation pages internally with
the client's page size, "you can cross-check that by turning off paging"), **CASSANDRA-17222** (Open, 7.x: "internally C*
will send multiple internal requests to avoid running out of memory. The page size used for those internal queries is
the same as the external page size"), **CASSANDRA-11745** (bytes limit to queries and paging, Fixed 6.0-alpha3; not in
5.0.x), 11566 (`count(*)` read timeout, Won't Fix). No issue reports an OOM from a plain aggregate with paging off on
3.10+ or asks for the DEFAULT_PAGE_SIZE fallback to apply to it. **Verdict: `new`** as an OOM report; the behaviour
(no internal paging when the client turns paging off) is **known** (9724, 17222) and contradicts the code comment and the
10707 statement; not `known-fixed`.

**Overlap with verified U4** ([case](../cql-row-limit--wide-row-default-pages/cql-row-limit--wide-row-default-pages.md)).
U4 (`verified-OOM · deployment`, unprotected configuration) has the **same holder** (the replica's serialized
`DataOutputBuffer` of one read, `ReadResponse.java:197-201`) and the **same switch** (read thresholds off), and the
same missing sum over concurrent reads. It differs in what bounds the read and in the response side:
- **Bound.** U4's read is bounded by the client's page in rows (5,000, the driver default); here the client sends no page
  size and the server drops its own internal default, so a single read covers the whole slice (≈ 1 GiB here, ≈ 4.4× U4's
  234 MiB page): a server-side bypass of a stated internal bound, not a client-chosen row count.
- **Response.** U4 returns the page (a 234 MiB `ResultSet` copy plus a 234 MiB Netty-encoded frame), which moved its
  endpoint into Netty direct memory above a 2 GiB heap and is limited by the driver's 256 MiB frame cap. Here the response
  is one row, so neither the `ResultSet` nor direct memory nor the driver frame limit is involved: the budget search can
  test the heap domain up to pc82's own resolution (31,744 MiB), which U4 could not.
- **Multiplicity.** U4 needed c = 3 at 2 GiB; here c = 1 is predicted to suffice at 2 GiB.
A U4-like result here (an OOM only with paging on, or in `Message.encode`) would not verify this design.

## 2. Design solution (stage 1; frozen)

**Mechanism.** Direction: **unprotected configuration** (protocol "Unprotected results": the byte control
`read_thresholds_enabled` ships off) on top of a **bypass of the internal row bound** (the `DEFAULT_PAGE_SIZE` fallback
that `getDataLimits` computes is not applied to plain aggregates; `AggregationQueryPager.java:186`, `:193-197`,
`:439-441`; `SelectStatement.java:899-919`), with multiplicity of concurrent reads for the budget search; technique notes
[`bypass-playbook.md`](../../../bypass-playbook.md) (protected vs suspect path: paged vs unpaged) and
[`default-convergence-playbook.md`](../../../default-convergence-playbook.md) (multiplicity sweep at default capacities).
A prepared `SELECT count(v) FROM u10.t WHERE pk = ? AND ck < ?` sent with paging off is executed as one
`SinglePartitionReadCommand` with no row limit; on a single node the request thread runs the local read
(`AbstractReadExecutor.java:165`) and `LocalDataResponse.build` serializes every selected row into one heap
`DataOutputBuffer` (`ReadResponse.java:197-201`); only after the buffer is complete does the coordinator iterate it and
count. The same query with paging on is split into sub-reads of the client page size (5,000 rows) by the same pager.

**Protection map** (fixed before any run; single node, coordinator = replica).

| Domain | Holder (allocation → release) | Counter K | Limit at default | At the limit |
|---|---|---|---|---|
| Internal paging of a plain aggregate | replica `DataOutputBuffer` of the one sub-read (`ReadResponse.java:199`; growth `DataOutputBuffer.java:158-180`) → released after the coordinator has iterated it (`SelectStatement.java:546-549`) | rows per sub-read (`DataLimits` count) | client page size when > 0; **NO_LIMIT with paging off** (the 10,000 fallback is computed but not applied) | none in rows → **bypass of the stated internal bound** |
| Read-size thresholds | same holder (`ReadCommand` size tracking of `row.unsharedHeapSize()`) | bytes | **off** (`Config.java:526`, `:530`) | nothing → **unprotected configuration** |
| Page-size guardrail | — | rows | −1 (off); sees `pageSize = -1` | nothing |
| Partition-size guardrail | sstable partition (write side) | bytes | off (`Config.java:911`) | not a read bound |
| Read timeout | the read in progress | elapsed time since request start | `read_request_timeout` 5 s (`StorageProxy.java:2204-2205`, `ReadCommand.java:777-792`) | read aborted per row, buffer dropped: per-read bytes ≤ serialization rate × 5 s (**the only bound that applies**, time-based) |
| Array cap | the buffer | array length | `MAX_ARRAY_SIZE` 2^31 − 9 | `BufferOverflowException`, read fails (not reached: slices ≤ 1 GiB) |
| Concurrency | one buffer per in-flight read | READ work permits | `concurrent_reads` 32 executing local reads; NTR 128 threads | further reads queue (and expire); no byte sum across reads |
| Response (ledger, not claimed) | `ResultSet` + Netty encode of **one row** | — | `MaxDirectMemorySize` | not a factor (a few bytes) |
| Baseline | key cache min(5 % H, 100 MiB) heap; chunk cache min(512 MiB, H/4) and networking pool min(128 MiB, H/16) direct; memtables empty (read-only workload) | own | defaults | evict / flush |

**Configuration and budget audit.**
- Build: `pc82:/mydata/s4/cassandra-base` copied to `/mydata/u10/tree` (unmodified 5.0.9 build; record the jar sha256).
  JDK 11.0.33 (G1, shipped `jvm11-server.options`: `G1HeapRegionSize=16m`, `MaxGCPauseMillis=300`; `jvm-server.options`:
  `HeapDumpOnOutOfMemoryError`, `AlwaysPreTouch`). Ubuntu 22.04, kernel 5.15.0-203, cgroup v2 (user delegation incl.
  memory). pc82: x86_64 Xeon E5-2660 v2, 40 cores, 125 GiB RAM, 8 GiB swap (excluded per scope), `/mydata` 714 GiB free on
  a spinning RAID volume (`sda` ROTA 1, PERC H710P). Checked read-only 2026-11-18 13:41 EST: no java process, load 0.00,
  `/mydata/s4/` holds only `cassandra-base`.
- **Every capacity constraint at its shipped default** (V6): read thresholds off, page-size and partition-size guardrails
  off, `concurrent_reads` 32, NTR 128, `read_request_timeout` 5 s, `native_transport_timeout` 12 s, caches and memtables
  default, `num_tokens` 16, default table options (LZ4, STCS, BIG format, `caching` keys ALL). The only constraint changed
  is in the intervention arms (I1 config; I2 a diagnostic build). The client's paging choice (off, i.e. no page size) is
  the workload, not a server setting.
- `cassandra.yaml` diff from the shipped file (environment only): `data_file_directories`, `commitlog_directory`,
  `hints_directory`, `saved_caches_directory`, `cdc_raw_directory` under `/mydata/u10/node/`. Addresses stay `localhost`.
- **Budgets** (V7; standing rule: heap and direct ≥ 512 MiB meet V7, 2 GiB ideal). Every lifetime sets both
  `MAX_HEAP_SIZE` and `MAX_DIRECT_MEMORY_SIZE` to the **exact pair `cassandra-env.sh` resolves for a node class**
  (heap = RAM/2, direct = RAM/4 while RAM/2 ≤ 31,744 MiB; above it 31,744M / 15,872M under G1, `cassandra-env.sh:52-67`,
  `USING_CMS` = 1 under G1 as U4's amendment A2 found):

  | Label | Heap / direct | Node class it is the full default resolution of |
  |---|---|---|
  | `2G` (primary) | 2048M / 1024M | 4 GiB RAM |
  | `4G` | 4096M / 2048M | 8 GiB RAM |
  | `8G` | 8192M / 4096M | 16 GiB RAM (also the calibration lifetime) |
  | `16G` | 16384M / 8192M | 32 GiB RAM |
  | `31G` | 31744M / 15872M | ≥ 62 GiB RAM, **pc82's own resolution** |

  Record `-Xmx`/`-Xms`/`-XX:MaxDirectMemorySize` from the process command line in `run.meta`.
- **No container budget.** Each victim runs in `systemd-run --user --scope -p MemoryMax=<heap + direct + 8G>
  -p MemorySwapMax=0` (isolation only); a scope `oom_kill` makes a lifetime **invalid**; record `memory.events` per lifetime.

**Ceiling arithmetic.** Row: `pk int, ck int, v blob` with W = 16,384 B of random bytes; serialized ≈ W + 16 B per row
(stage 4 measured 1,040 B per 1 KiB row). A slice of n rows serializes to S(n) ≈ n × 16,400 B: n = 65,536 → S ≈ 1,025 MiB;
49,152 → 769 MiB; 32,768 → 513 MiB; 16,384 → 256 MiB. The buffer's final capacity F lies in [S, 1.5 S] (growth ×1.5 above
64 MiB; the exact sequence depends on the first writes: U4 saw 216/324 MiB arrays, the OC-44 stage 4 a 489.8 MiB array
for 392 MiB), and the last copy holds old + new ≈ 1.67 F. For the planned n_T = 65,536: **F ≈ 1.0–1.5 GiB held per
in-flight read, ≈ 1.7–2.5 GiB at its last growth**, plus ≈ 3 × S of garbage allocated per read. No contract capacity
bounds it: Σ contract capacities is unbounded in bytes; the implicit ceilings are the 5 s timeout (rate × 5 s per read),
the 2 GiB array cap, and 32 executing local reads × ≈ 1.25 GiB ≈ 40 GiB. Baseline at 2 GiB (read-only): ≈ 0.15–0.3 GiB
(U4). Predicted smallest failing concurrency at n_T (F ≈ 1.25 GiB mid, free = H − 0.3 GiB, one read in its last growth):
**2G → c = 1** (one read's last growth, 1.7–2.5 GiB, exceeds 1.7 GiB free; humongous arrays need contiguous 16 MiB
regions); 4G → 2 (band 2–3); 8G → 5 (4–7); 16G → 11 (8–14); 31G → 22 (16–32). If calibration lowers n_T to 32,768
(F ≈ 0.5–0.77 GiB), the predictions scale by ≈ 2× (2G → c = 2, band 1–3; 31G beyond 32 → likely no OOM there, and
16G becomes the largest failing heap). Direct memory: chunk cache + networking pool ≤ 640 MiB at 2G (limit 1,024 MiB);
the response is one row; predicted far below every direct limit.

**Workload and environment.**
- Node `pc82` only (victim + client on loopback). Work directory **`/mydata/u10/`** (fresh): `tree/`, `conf-pristine/`,
  `cls/`, `template/`, `node/`, `runs/<label>/`, `harness/` (synced from this folder). Never touch `/mydata/s4/`.
- Schema: `CREATE KEYSPACE u10 WITH replication = {'class':'SimpleStrategy','replication_factor':1}`;
  `CREATE TABLE u10.t (pk int, ck int, v blob, PRIMARY KEY (pk, ck))` with default table options.
- Data: **8 partitions (pk 0–7) × 65,536 rows (ck 0–65,535) × 16,384 random bytes** (`java.util.Random(1000 + pk)`),
  8 GiB of payload, 1 GiB per partition. Each insert is 16 KiB (far below `max_mutation_size` 16 MiB and
  `max_value_size` 256 MiB). A partition of 1 GiB is above the documentation's rule-of-thumb size but accepted by every
  default (the partition-size guardrail ships off; it only warns/fails writes and compactions when enabled); queries read
  a clustering slice of it (a time-window aggregate), so the per-query size is the dial n, not the partition.
- Load once (lifetime `LOAD`, 8192M/4096M, not a reading): schema; insert at 64 concurrent async writes, CL ONE, each
  failed insert retried up to 5 times (log failures); `nodetool flush u10`; `nodetool compact u10` (wait); `nodetool
  drain`; SIGTERM by PID. Then `cp -a /mydata/u10/node /mydata/u10/template`; `rm -rf /mydata/u10/template/saved_caches/*`.
  **Every measured lifetime starts from a fresh `cp -a` of the template** (no hard links). Record the template size.
- `VERIFY` (inside the IC lifetime below): for each pk, paged `SELECT ck FROM u10.t WHERE pk = ?` (fetch 5,000) counts
  65,536 rows, and `SELECT v FROM u10.t WHERE pk = ? AND ck = 0` returns 16,384 bytes. A short partition is reloaded
  before any reading (a deviation, recorded).
- Client `U10Load` (Java, driver 3.12.1 from the tree, adapted from U4's `U4Load.java`): one `Cluster`, protocol **v4**,
  16 connections, CL ONE, `FallthroughRetryPolicy`, socket read timeout 120 s; prepared statements. **Paging off** =
  `setFetchSize(Integer.MAX_VALUE)` (server sees −1); **paging on** = `setFetchSize(5000)` (driver default, set
  explicitly; the driver fetches every page). Query kinds: `agg` = `SELECT count(v) FROM u10.t WHERE pk = ? AND ck < ?`
  (bound n); optional `grs` = `SELECT pk, ck, v FROM u10.t WHERE pk = ? AND ck < ? GROUP BY pk, ck` (probe only).
  Modes: `load`, `verify`, `one <pk> <n> <fetch> <kind>` (prints result, rows, latency, error class),
  `run <conns> <steps> <fetch> <kind>` with steps `c:n:secs` (closed loop: c reads in flight; read i of the loop uses
  pk = i mod 8, so concurrent reads hit distinct partitions while c ≤ 8). Per-second CSV: t, step c, n, completed,
  count-correct (result = n), errors split into `ReadTimeout`, `ReadFailure`(READ_SIZE), other, mean latency, in flight.
  Client JVM `-Xmx4g` in its own scope `u10-client-<label>` (`MemoryMax=8G`, `MemorySwapMax=0`).

**Arms and conditions.** Arm **A** = shipped defaults. Arm **I1** = A + `read_thresholds_enabled: true` +
`local_read_size_fail_threshold: 64MiB` (the shipped byte control switched on; same as U4's arm I). Arm **I2** (optional,
diagnostic build) = A on a separate build whose only change is that a plain aggregate with paging off pages internally
at `DEFAULT_PAGE_SIZE` (the stated intent), diff to save as `harness/i2.diff`:

```
--- a/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java
+++ b/src/java/org/apache/cassandra/service/pager/AggregationQueryPager.java
@@ fetchPage(int pageSize, ConsistencyLevel consistency, ClientState clientState, Dispatcher.RequestTime requestTime)
-        return new AggregationPartitionIterator(pageSize, consistency, clientState, requestTime);
+        return new AggregationPartitionIterator(pageSize <= 0 ? org.apache.cassandra.cql3.statements.SelectStatement.DEFAULT_PAGE_SIZE : pageSize,
+                                                consistency, clientState, requestTime);
```
(`AggregationQueryPager.java:62`; `AggregationPartitionIterator` never stops on a count and uses the value as every
sub-page size, so the query still runs to the end of the slice in 10,000-row sub-reads of ≈ 156 MiB.) Build in a
separate copy `/mydata/u10/tree-i2` (delete `build/classes/main/org/apache/cassandra/service/pager/AggregationQueryPager*.class`
first; `ant jar`; never run `ant` in a tree a node runs from); record the jar sha256.

Labels (`steps` as `c:n:secs`; fetch `off` = `Integer.MAX_VALUE`, `5000` = driver default; kind `agg` unless stated):

| Label | Arm | Heap / direct | Fetch | Steps | Reps | Purpose |
|---|---|---|---|---|---|---|
| `LOAD` | — | 8192M / 4096M | — | load, flush, compact, drain | 1 | data (not a reading) |
| `IC` instrument check + `CAL-R` calibration (not readings) | A | 8192M / 4096M | both | see below | 1 | verify data, paging mode, sub-reads per query, read time per n; choose n_T |
| `CAL-2G` sweep | A | 2048M / 1024M | off | `1:4096:20,1:16384:40,1:32768:40,1:n_T:40,2:n_T:40,3:n_T:40,4:n_T:40,6:n_T:40` | 1 | size and multiplicity boundary at 2G; c_T |
| `T-2G-1..3` test | A | 2048M / 1024M | off | `1:4096:20,c_T:n_T:160` | 3 (+2 if 2/3) | V1 |
| `M-2G-1..3` matched control | A | 2048M / 1024M | **5000** | `1:4096:20,c_T:n_T:160` | 3 | V2 (protected path: same query, client paging on) |
| `I1-2G-1..3` intervention | **I1** | 2048M / 1024M | off | `1:4096:20,c_T:n_T:160` | 3 | V4 (config only) |
| `CAL-4G` | A | 4096M / 2048M | off | `1:4096:20,1:n_T:40,2:n_T:40,3:n_T:40,4:n_T:40,6:n_T:40` | 1 | budget search |
| `CAL-8G` | A | 8192M / 4096M | off | `1:4096:20,2:n_T:40,3:n_T:40,4:n_T:40,6:n_T:40,8:n_T:40,10:n_T:40` | 1 | budget search |
| `CAL-16G` | A | 16384M / 8192M | off | `1:4096:20,4:n_T:40,6:n_T:40,8:n_T:40,10:n_T:40,12:n_T:40,16:n_T:40` | 1 | budget search |
| `CAL-31G` | A | 31744M / 15872M | off | `1:4096:20,8:n_T:40,12:n_T:40,16:n_T:40,20:n_T:40,24:n_T:40,32:n_T:40,40:n_T:40` | 1 | budget search (pc82's own resolution) |
| `I2-2G-1..3` (optional) | **I2** build | 2048M / 1024M | off | `1:4096:20,c_T:n_T:160` | 3 | second intervention: restores the stated bound, keeps useful work |
| `REP-<H>-1..2` (optional) | A | largest failing budget | off | warm-up, then its failing c for 160 s | 2 | repetitions at the largest failing budget |
| `P-GRS` probe (optional; coverage note, not a reading) | A | 2048M / 1024M | off, kind `grs` | `1:16384:40,1:32768:40,1:65536:40` | 1 | OC-298 family: does the unpaged GROUP BY `ResultSet` grow to the slice? |

Each sweep stops at the first OOM (the client's step at the victim's death is the failing step, corrected from the 1 s
samples as U4's amendment A3 did). If a budget-search sweep ends without OOM, add one step at the next c in the list
pattern (at most +1 step), then stop. **c_T** = the smallest c at n_T at which `CAL-2G` reached an OOM; if `CAL-2G` OOMs
already at a smaller n with c = 1, c_T = 1. If `CAL-2G` survives to c = 6, run `CAL-2G-x` with
`8:n_T:40,12:n_T:40,16:n_T:40,24:n_T:40,32:n_T:40` before deciding.

**IC / CAL-R procedure** (one lifetime at 8192M/4096M, arm A; a large heap so that every calibration read completes):
1. `VERIFY` (above).
2. Paging mode: `one 0 6000 off` of `SELECT ck FROM u10.t WHERE pk = 0 AND ck < 6000` returns 6,000 rows in the first page
   with no paging state; with fetch 5000 the first page has 5,000 rows and a paging state.
3. Sub-reads per query: read `nodetool tablestats u10.t` "Local read count" before and after one `agg` query at n = 20,000
   with fetch off (expect Δ = 1) and with fetch 5000 (expect Δ = 4 or 5).
4. Read time per n: for n ∈ {8,192, 16,384, 32,768, 49,152, 65,536}, three sequential `agg` queries with fetch off and
   three with fetch 5000 (c = 1); record result (count = n), latency, error class, and old-gen post-GC after each.
5. **n_T** = the largest n whose fetch-off queries all complete in ≤ 3.5 s and whose fetch-5000 queries all complete in
   ≤ 4.5 s (both below the 5 s read timeout). Predicted n_T = 65,536. If no n ≥ 16,384 qualifies, the 5 s timeout bounds
   the holder below an OOM-relevant size at this row width: record it, run `CAL-2G` with n = 65,536 anyway (fetch off) to
   test whether timed-out reads still exhaust the heap, and judge by the verdict rules.

**Harness** (under `harness/` in this folder; adapt U4's verified harness,
[`../cql-row-limit--wide-row-default-pages/harness/`](../cql-row-limit--wide-row-default-pages/harness/)):
`setup.sh` (`mkdir -p /mydata/u10`; `cp -a /mydata/s4/cassandra-base /mydata/u10/tree`; pristine conf; compile `U10Load`
and `C2Sampler` into `/mydata/u10/cls`); `victim-ctl.sh` (`ROOT=/mydata/u10`; arms `A`/`I1`/`LOAD`, and `BUILD` switchable
to `tree-i2` for I2; explicit heap/direct pair always, no "auto"; launch `bin/cassandra -f` under the scope above with
`setsid nohup … < /dev/null`, `CASSANDRA_HEAPDUMP_DIR=<run dir>`, `JVM_EXTRA_OPTS="-XX:NativeMemoryTracking=summary
-Xlog:gc=info,safepoint=info:file=<run>/gc.log:time,uptime,level,tags"`; save `yaml.diff`, `run.meta`); `run-arm.sh
<label> <arm> <heap> <direct> <fetch> <kind> <steps>` (refuse if a `CassandraDaemon` runs; clone; start; ready =
"Starting listening for CQL clients" within 180 s (31G pre-touch), one retry; GC + baseline; `nodetool tablestats u10.t`
before/after; sampler; every 10 s NMT summary and `RssAnon`; T/M/I labels: one `jcmd <pid> GC.class_histogram` at load
second 150 if alive; on client exit or JVM death record the outcome: `OutOfMemoryError` lines from `stdout.log` /
`system.log`, the first error with its stack, hprof present, scope `memory.events`, count of "Query cancelled (timeout)"
in `debug.log`; stop a survivor with `nodetool drain` and SIGTERM by PID; copy small files to `logs/<label>/`); `batch.sh`
(runs the label list in order, enforcing the time plan's hard limits); `C2Sampler.java`, `gcwin.py`, `steps.py` (adapt to
`c:n` steps and the new error columns), `hprofhist.py` (buckets: `byte[]` ≥ 64 MiB with their sizes, `LocalDataResponse`
and `DataOutputBuffer` counts, 16 KiB `byte[]` count), `hprofstacks.py` (threads in `LocalDataResponse.build`,
`DataOutputBuffer.expandToFit`, `AggregationQueryPager`). Launch each lifetime as a background job and poll with bounded
waits (no foreground `sleep`); kill by PID. Full logs, GC logs and hprofs stay in `pc82:/mydata/u10/runs/<label>/`.

**Instruments (U independent of K).** K = rows per sub-read and sub-reads per query: the client's count result (= n per
completed query) and `nodetool tablestats` Δ "Local read count" ÷ attempted queries (≈ 1 with fetch off, ⌈n/5,000⌉ (+1)
with fetch 5000; U4 and stage 4 showed the extra empty read). U = (a) G1 old-gen post-GC usage and heap used (JMX, 1 s);
(b) at an OOM, the hprof from `HeapDumpOnOutOfMemoryError`: count and sizes of `byte[]` ≥ 64 MiB (predicted 1–2 per
in-flight read, 0.5–1.6 GiB each at n_T), `LocalDataResponse`/`DataOutputBuffer` instances, and the dying thread's stack;
for dumps > 8 GiB, run `hprofhist.py` only if time permits (record the first error and the GC log in any case);
(c) surviving T/M/I lifetimes: one `GC.class_histogram` at second 150; (d) GC log → STW fraction per 60 s (`gcwin.py`;
service-loss criterion ≥ 90 % over ≥ 60 s); (e) NTR / ReadStage active (the load reached c), completed and correct
queries/s, error classes, "Query cancelled (timeout)" count (the timeout bound acting); (f) NMT and `RssAnon` every 10 s,
JVM direct (`java.nio` and NMT "Other") for the ledger.

**Predicted response.**
- `IC`: 65,536 rows per partition; paging off returns a 6,000-row first page with no paging state; Δ local reads = 1
  (off) and 4–5 (5000); CAL-R latency roughly linear in n, ≤ 3.5 s at 65,536 (n_T = 65,536).
- `CAL-2G`: c = 1 survives n = 4,096, 16,384 and 32,768 (old post-GC rising, heavy humongous GC at 32,768); **Java heap
  OOM at c = 1, n = n_T** within its 40 s step (band: c = 1–2 at n_T; possibly already at c = 1, n = 32,768).
- `T-2G`: heap OOM 3/3 within 160 s at c_T. First error `java.lang.OutOfMemoryError: Java heap space` on a request or
  ReadStage thread in `DataOutputBuffer.expandToFit` ← `LocalDataResponse.build` (via `AggregationQueryPager`); hprof with
  ≥ 1 `byte[]` of 0.5–1.6 GiB and 1 `LocalDataResponse` per in-flight read; Cassandra's heap dump, then `kill -9`.
- `M-2G` (fetch 5000: sub-reads of ≈ 78 MiB, buffers ≤ 128 MiB): 0/3 OOM; correct counts at ≈ the T arm's per-read time;
  old post-GC < 1 GiB; STW < 50 %; Δ local reads ≈ 14 per query at n_T.
- `I1-2G`: 0/3 OOM; every query fails with READ_SIZE ("… loaded over … bytes … local_read_size_fail_threshold") after
  ≈ 64 MiB counted; 0 useful queries/s (recorded: the bound protects by refusing the aggregate).
- `I2-2G` (if run): 0/3 OOM with correct counts (useful work kept); Δ local reads ≈ ⌈n_T/10,000⌉ (+1) per query.
- Budget search: heap OOM at each budget near its predicted c (4G: 2, 8G: 5, 16G: 11, 31G: 22); **largest failing
  heap predicted 31,744 MiB (pc82's own resolution)**, every endpoint a Java heap OOM in the replica buffer, no Netty
  direct OOM; read timeouts rise with c but do not prevent the OOM.
- No scope `oom_kill`; direct and NMT "Other" far below every direct limit.

**Stopping budget and time plan.** Deadline (task): stage-2 runs and §3–§4 written before **18:07 EST, 2026-11-18**.
pc82's clock is MST = EST − 2 h; log both. Planned from the stage-2 start S (expected ≈ 14:40 EST): setup + harness
S → S+30; `LOAD` (8 GiB at ≈ 20–40 MB/s on the spinning volume, plus flush/compact) + template → S+65; `IC`/`CAL-R` → S+80;
`CAL-2G` → S+90; `T-2G` ×3, `M-2G` ×3, `I1-2G` ×3 (≈ 4.5 min each incl. an 8 GiB `cp -a`) → S+135; `CAL-4G`, `CAL-8G`,
`CAL-16G`, `CAL-31G` (≈ 6–10 min each; the 31G lifetime includes pre-touch and a ≈ 31 GB dump) → S+170; then, in this
order and only as time allows: `I2` (build ≈ 10 min + 3 lifetimes), `REP` ×2, `P-GRS`. **Hard limits:** if S is later than
15:20 EST, skip all optional items and run `CAL-31G` only if it can end by 17:15; no lifetime starts after 17:15 EST unless
it ends by 17:30; every process stopped by 17:35 EST; §3–§4 by 18:07. Per lifetime: load ≤ 180 s (T/M/I), ≤ 8 × 40 s
(sweeps); a node not ready in 180 s is invalid (retry once); client query timeout 120 s. No escalation after an OOM beyond
the planned list. Disk: template 8 GiB + node 8 GiB + hprofs (≤ 2 GiB each at 2G; ≤ 4 + 8 + 16 + 31 GiB for the search)
≈ 100 GiB of 714 GiB; RAM: largest victim scope 31,744 + 15,872 + 8 GiB ≈ 55 GiB + client 8 GiB < 125 GiB; cores: 40
(≤ 40 reads + client).

**Controls and intervention.**
- **Matched control `M-2G` ×3:** same build, budget, data, slice n_T, c_T, connections and client; only the client's paging
  is on (5,000, the driver default), which makes the same pager split the read into 5,000-row sub-reads. It separates the
  holder (one whole-slice buffer) from the query, the data and the work done. The `CAL-2G` step below the failing one (in n
  at c = 1, or in c) is reported as the boundary (one run).
- **Intervention `I1-2G` ×3:** the T workload with the shipped byte control switched on (`read_thresholds_enabled: true`,
  `local_read_size_fail_threshold: 64MiB`); removing the OOM attributes it to the missing byte bound; throughput and
  rejection rate recorded.
- **Intervention `I2-2G` ×3 (optional, diagnostic):** the T workload on the patched build that applies the stated
  10,000-row internal paging to plain aggregates; removing the OOM while keeping correct counts attributes it to the
  missing internal bound. The original failure is on the unmodified build (T).

**Verdict rules (stated before readings).**
- **true positive:** `T-2G` heap OOM in ≥ 3 runs (n/N stated; if 2/3, up to 2 more), `M-2G` 0/3, `I1-2G` 0/3, the dumps show
  the claimed holder (`byte[]` buffers of the size predicted for n_T under `LocalDataResponse.build`) → `verified-OOM ·
  deployment`, direction **unprotected configuration + bypass of the internal row bound** (label it as such in `_INDEX.md`),
  largest failing budget from the search with its n/N.
- **retry:** OOM only in a lifetime with a non-default setting or a budget below 512 MiB; OOM in Netty/`Message.encode`
  rather than the replica buffer; service loss without OOM (`verified-gap`); OOM < 3/5; the control `M-2G` also OOMs (then
  the holder is not the unpaged sub-read); time ran out before V1/V2/V4.
- **false positive:** `CAL-2G` and `CAL-2G-x` reach c = 32 at n_T (NTR/ReadStage active ≥ min(c, 32), load reached) with
  no OOM and old post-GC < 90 % of the heap, and the measurements show why (e.g. the 5 s timeout cancels every read below
  an OOM-relevant buffer size: "Query cancelled (timeout)" counts and histograms of in-flight buffers), with no named
  factor left untried.
- **invalid lifetime:** client JVM OOM, scope `oom_kill`, workload not started, wrong paging mode (Δ local reads ≠ 1 per
  fetch-off query, or count ≠ n on completed queries); fix and rerun, recorded as a deviation.
- Cleanup: stop every process started; keep `/mydata/u10/runs/` and the template (delete hprofs > 8 GiB after summarizing
  if disk falls below 200 GiB free); report what is left. Delete nothing in `/mydata/s4/`.

`sha256 of §1–§2 at freeze: 5c730ede830d636fedc52d3462fbb68ebb6dd5682265e274943af3a22aa50c25` · computed over the lines from `## 1. Candidate` through the line before this one (`sed -n '/^## 1\. Candidate/,/^`sha256 of §1–§2 at freeze/p' <file> | sed '$d' | sha256sum`) · frozen 2026-11-18 (stage 1) · amendments after the freeze: dated, with reason, below this line.


**Amendments (stage 2, 2026-11-18; none changes a constraint, budget, workload or verdict rule):**
- **A1 (13:55 EST, environment).** Work directory `pc82:/mydata/s4/u10-w4/` instead of `/mydata/u10/` (the wave-4 session
  assigned `/mydata/s4/u10-w4` as this case's fresh directory). `/mydata/s4/cassandra-base` was only read (copied to
  `tree/`); nothing else under `/mydata/s4/` was touched. All script paths use `ROOT=/mydata/s4/u10-w4`.
- **A2 (14:01 EST, data; the design's own rule).** `LOAD` wrote 524,231 of 524,288 rows: 57 inserts of pk 7 (ck 10,056 …)
  failed with `WriteTimeoutException` after 5 retries (1,138 retries in all; 1 min 41 s at ≈ 80 MiB/s). Per the design
  ("a short partition is reloaded before any reading"), lifetime `FIX` (8192M/4096M, not a reading;
  `harness/fix-template.sh`, client mode `reload`) re-inserted those 57 rows with their original bytes (same
  `Random(1000 + pk)` sequence), `VERIFY` showed 8 × 65,536 rows and 16,384-byte values, then flush + major compaction
  (1 min 59 s) → the template: 1 sstable, 8,646,564,259 B, partition 1,155,149,911 B. `IC`'s `VERIFY` repeated it on a clone.
- **A3 (14:10 EST, sweep lists).** The "+1 step if a budget-search sweep ends without OOM" was appended to each sweep's
  list in advance (CAL-4G `8:n_T`, CAL-8G `12:n_T`, CAL-16G `20:n_T`, CAL-31G `48:n_T`); a sweep stops at its first OOM,
  so this is the same rule.
- **A4 (14:00 EST, I2 build timing).** The `I2` build (`harness/build-i2.sh`, diff `harness/i2.diff`, `ant jar` 1 min
  22 s, resolver fetched a few poms from Maven Central) ran during `LOAD` (not a reading), in the separate tree
  `tree-i2`. Jar sha256: unmodified `570b5249…a90176e`, I2 `9a390ee0…3473004` (full values in `logs/build-i2.out`).
- **A5 (harness detail).** The client's `cal` mode (CAL-R) runs the 3 queries per n with a 1.5 s gap; old-gen post-GC is
  read from the 1 s JMX samples rather than after each query. `hprofstacks.py` prints 45 frames (U4's printed 14, which
  cut the stack above `LocalDataResponse.build`). Dumps > 9 × 10^9 B (16 GiB lifetimes) were summarized with
  `hprofhist.py` after the batch, when the node was idle.

## 3. Runs (stage 2)

**Environment.** `pc82` (CloudLab `jason92-326665`): Xeon E5-2660 v2, 40 cores, 125 GiB RAM, 8 GiB swap (scopes set
`MemorySwapMax=0`), Ubuntu 22.04, kernel 5.15.0-203-generic, cgroup v2; OpenJDK 11.0.33 (G1, `G1HeapRegionSize=16m`,
`MaxGCPauseMillis=300`, `AlwaysPreTouch`, `HeapDumpOnOutOfMemoryError`, `OnOutOfMemoryError="kill -9 %p"`). Build: unmodified
5.0.9 copied from `/mydata/s4/cassandra-base`, jar sha256 `570b5249d9b9a43f6809eb3da562737492192026f974b2edbd20e94bea90176e`.
Before the start (13:53 EST) no java process ran on pc82 and `/mydata/s4/` held only `cassandra-base`. Every lifetime ran
alone (victim + client on loopback); the resolved `-Xms/-Xmx/-XX:MaxDirectMemorySize` of each lifetime is in its
`run.meta` and matched its label (2048M/1024M, 4096M/2048M, 8192M/4096M, 16384M/8192M, 31744M/15872M). `yaml.diff`: the
five directories only (plus the two I1 lines in I1). Scope `memory.events`: `oom_kill 0` in every lifetime (no lifetime
invalid). JMX direct pool ≤ 49 MiB in every lifetime (limits 1–15.5 GiB). Harness: `harness/`; per-lifetime excerpts
`logs/<label>/` (`outcome`, `steps.txt`, `gcwin.txt`, `hprofhist.txt`, `hprofstacks*.txt`, `oom-excerpt.txt`, `run.meta`,
`yaml.diff`, `memory.events`, gzipped `client.csv`/`samples.csv`); full logs, GC logs and the 10 hprofs (45 GiB) in
`pc82:/mydata/s4/u10-w4/runs/<label>/`. Batch record: `logs/batch.outcomes`, `logs/batch.out`.

**IC / CAL-R** (8192M/4096M, arm A; `logs/IC/`). VERIFY: 8 × 65,536 rows, value 16,384 B. Paging mode: `SELECT ck … ck < 6000`
with fetch off → 6,000 rows in the first page, no paging state; fetch 5000 → 5,000 rows + paging state. Sub-reads per `agg`
query at n = 20,000: Δ "Local read count" **1** with fetch off, **5** with fetch 5000 (predicted 1 and 4–5). Read time per n
(3 queries each, all counts correct):

| n | 8,192 | 16,384 | 32,768 | 49,152 | 65,536 |
|---|---|---|---|---|---|
| fetch off (ms) | 413–457 | 899–913 | 1,894–1,976 | 2,893–2,917 | **3,437–3,488** |
| fetch 5000 (ms) | ≈ 395 | 796–826 | 1,574–1,596 | 2,358–2,396 | 3,206–3,245 |

**n_T = 65,536** (fetch-off max 3,488 ms ≤ 3.5 s; fetch-5000 max 3,245 ms ≤ 4.5 s). Old-gen post-GC max 2,812 MiB in this
8 GiB lifetime; no cancellations, no OOM.

**CAL-2G** (2048M/1024M, fetch off; `logs/CAL-2G/`): c = 1, n = 4,096: 107 correct (≈ 0.19 s), heap max 1,858 MiB, old
post-GC ≤ 837 MiB; c = 1, n = 16,384: 40 correct (≈ 1.0 s), old post-GC ≤ 722 MiB; c = 1, n = 32,768: the first query
completed (2,066 ms; heap sample 1,388 MiB during it), the **second died: `OutOfMemoryError: Java heap space`** (heap dump at
19:11:51.848 UTC, uptime 89.3 s; client step at that time `1:32768`, checked by hand against `client.csv`). Dump (619 MB):
**one** `byte[]` ≥ 64 MiB, **487 MiB**; 1 `DataOutputBuffer`, 1 `LocalDataResponse`, 1 `AggregationQueryPager`. OOM thread
(`hprofstacks-oom.txt`): `ByteBuffer.allocate` ← `DataOutputBuffer.expandToFit:178` ← … `Cell$Serializer.serialize` ←
`UnfilteredPartitionIterators$Serializer.serialize:339` ← **`ReadResponse$LocalDataResponse.build:201`** ←
`ReadCommand.createResponse:374` ← `StorageProxy$LocalReadRunnable.runMayThrow:2211` ← `SEPWorker.run` (a ReadStage task).
→ OOM already at c = 1 and a smaller n, so **c_T = 1** (design rule); the T/M/I arms ran `1:4096:20,1:65536:160`.
`CAL-2G-x` not needed.

**T/M/I arms at 2048M/1024M** (each from a fresh clone of the template; `logs/<label>/`):

| Label | Arm / fetch | Outcome | n_T queries: correct / errors | Readings |
|---|---|---|---|---|
| T-2G-1 | A / off | **heap OOM** at the 1st n_T query (+31 s) | 0 / – | dump 873 MB: 1 `byte[]` **730 MiB**, 1 DOB, 1 LDR, 1 pager; same stack as CAL-2G; HeapDumper at uptime 43.7 s |
| T-2G-2 | A / off | **heap OOM** at the 1st n_T query (+31 s) | 0 / – | dump 873 MB: 1 `byte[]` **730 MiB**, 1 DOB, 1 LDR; same stack |
| T-2G-3 | A / off | **heap OOM** at the 1st n_T query (+32 s) | 0 / – | dump 618 MB: 1 `byte[]` **487 MiB**, 1 DOB, 1 LDR; same stack |
| M-2G-1 | A / 5000 | survived 180 s | 41 / 0 | mean 3.90 s; heap max 1,814 MiB, old post-GC max 662 MiB; Δ local reads 683 (≈ 14 per n_T query); STW max 12 %/60 s |
| M-2G-2 | A / 5000 | survived | 40 / 0 | mean 3.92 s; heap max 1,791, old post-GC max 919 MiB; Δ 668; STW max 12 % |
| M-2G-3 | A / 5000 | survived | 40 / 0 | mean 4.00 s; heap max 1,570, old post-GC max 738 MiB; Δ 657; STW max 13 % |
| I1-2G-1 | I1 / off | survived | 0 / 936 `ReadFailure` (READ_SIZE) | every query refused, incl. the n = 4,096 warm-up (119 failures): "1 nodes loaded over 67113872 bytes and aborted the query … (see local_read_size_fail_threshold)"; heap max 1,807 MiB |
| I1-2G-2 | I1 / off | survived | 0 / 928 | same; heap max 1,863 MiB |
| I1-2G-3 | I1 / off | survived | 0 / 926 | same; heap max 1,875 MiB |
| I2-2G-1 | I2 build / off | survived | 38 / 0 | mean 4.11 s; heap max 1,619, old post-GC max 947 MiB; Δ local reads 372 (≈ 7 per n_T query = ⌈65,536 / 10,000⌉) |
| I2-2G-2 | I2 build / off | survived | 38 / 0 | mean 4.19 s; heap max 1,651, old post-GC max 1,103 MiB; Δ 371 |
| I2-2G-3 | I2 build / off | survived | 44 / 0 | mean 3.60 s; heap max 1,718, old post-GC max 735 MiB; Δ 416 |

(DOB = `DataOutputBuffer`, LDR = `ReadResponse$LocalDataResponse`.) T: the n = 4,096 warm-up completed 103 correct
queries in each run; no "Query cancelled (timeout)", no service loss (STW ≤ 1 s in total). The T dumps hold the buffer of the
one in-flight read just before its next ×1.5 growth (730 → 1,095 MiB, or 487 → 730 MiB) could be allocated. `T-2G-4/5`
not needed (3/3).

**Budget search** (arm A, fetch off, n_T = 65,536; each its own lifetime; `logs/CAL-*/`, `logs/REP-*/`):

| Label | Heap / direct | Steps reached (correct n_T queries; timeouts RT / failures RF) | Outcome | Dump at OOM |
|---|---|---|---|---|
| CAL-4G | 4096M / 2048M | c=1: 12 (mean 3.17 s); c=2: 4 | **heap OOM at c = 2** (11 s into the step) | 1.73 GB: 2 DOB, 2 LDR, 2 pagers; `byte[]` 325, 487, 730 MiB |
| CAL-8G | 8192M / 4096M | c=2: 21; c=3: 27 (mean 4.16 s); c=4: 3 | **heap OOM at c = 4** (≈ 3 s into the step) | 5.1 GB: 4 DOB, 4 LDR, 4 pagers; `byte[]` 730, 730, 1,096 ×3 MiB |
| CAL-16G | 16384M / 8192M | c=4: 37; c=6: 44 (5 RT); c=8: 3 (56 RT, 1 RF); c=10: 0 (42 RT, 4 RF) | **heap OOM at c = 10** (24 s into the step); 216 "Query cancelled (timeout)" before | 11.9 GB: 10 DOB, 10 LDR, 10 pagers; 14 `byte[]` ≥ 64 MiB, Σ 11,197 MiB (487–1,096 MiB each) |
| REP-16384M-1 | 16384M / 8192M | warm-up, then c=10 | **heap OOM at c = 10** (4 s into the step) | 12.8 GB: 10 DOB/LDR/pagers; 14 `byte[]`, Σ 12,049 MiB |
| REP-16384M-2 | 16384M / 8192M | warm-up, then c=10: 1 (21 RT, 9 RF; 60 cancellations) | **heap OOM at c = 10** (19 s into the step) | 12.4 GB: 10 DOB/LDR/pagers; 14 `byte[]`, Σ 11,683 MiB |
| CAL-31G | 31744M / 15872M | c=8: 72 (mean 4.13 s; heap max 29,448 MiB, old post-GC max 5,761 MiB); c=12: 10 (64 RT, 11 RF); c=16 … 48: **0** (RT 84–374 per step, RF 2–48) | **survived to c = 48** (incl. the +1 step); 3,054 "Query cancelled (timeout)"; ReadStage active capped at 32; heap max ≤ 25.9 GiB at c ≥ 12; RSS 34 GB; STW max 6 %/60 s | – |

Every OOM's first error was `java.lang.OutOfMemoryError: Java heap space` with the stack above (`hprofstacks.txt`);
Cassandra's heap dump, then `kill -9`. **Largest failing budget: 16384M / 8192M (the full resolution of a 32 GiB node),
3/3 at c = 10.** At 31744M / 15872M (pc82's own resolution) the endpoint was not reached in the planned steps: up to
c = 8 the reads complete (≈ 4.1 s each, 8 × ≤ 1.6 GiB of buffers), and from c = 12 the reads slow past the 5 s read
timeout and are cancelled per row (`QueryCancelledException`, "Query cancelled for taking too long") before their buffers
reach the heap: the boundary. The c = 9–11 interval at 31 GiB was not in the planned list and was not tried.

**P-GRS probe (coverage note, not a reading; OC-298 family).** `SELECT pk, ck, v … GROUP BY pk, ck`, paging off, 2048M/1024M:
n = 16,384 and 32,768 → every query failed **client-side** with `FrameTooLongException` (the response exceeds the driver's
256 MiB frame; 32 and 16 attempts, the node survived); n = 65,536 → the node died: `io.netty.util.internal.OutOfDirectMemoryError:
failed to allocate 1,075,052,560 byte(s) of direct memory (used: 184,549,376, max: 1,073,741,824)` in `Message.encode`
(`PreV5Handlers$LegacyDispatchHandler.toFlushItem`), turned into a heap OOM by `JVMStabilityInspector.forceHeapSpaceOomMaybe`
(`logs/P-GRS/direct-oom-excerpt.txt`). So the unpaged GROUP BY result does grow to the whole slice on the coordinator (≈ 1 GiB
encoded frame); its endpoint is U4's (Netty direct memory at encode), not this case's replica buffer. Not part of the verdict.

**Deviations from the design:** A1–A5 above; nothing else. Optional items run: I2 ×3, REP ×2 (at 16 GiB, the largest
failing budget), P-GRS. All lifetimes ended by 15:22 EST (batch end); the 16 GiB dump summaries finished by 15:29; all processes stopped (checked 15:30 EST).

## 4. Conclusion (stage 2)

**Verdict: true positive.** Protocol status **`verified-OOM · deployment`**; direction **unprotected configuration
(`read_thresholds_enabled` off) + bypass of the internal row bound** (`DEFAULT_PAGE_SIZE` fallback not applied to plain
aggregates); interpretation: suspected implementation defect (the code comment and CASSANDRA-10707 state that aggregation
"is always paged internally to avoid OOM"; with paging off it is not) on top of a configuration-sizing gap (byte threshold
off by default).

**Reason.** At every shipped default and a 2048 MiB heap / 1024 MiB direct limit (`cassandra-env.sh`'s resolution for a
4 GiB node), a single unpaged `SELECT count(v) FROM u10.t WHERE pk = ? AND ck < 65536` over 65,536 × 16 KiB rows killed the
node with `OutOfMemoryError: Java heap space` in **3/3** runs (T-2G), each at the first such query, on a ReadStage thread in
`DataOutputBuffer.expandToFit` ← `LocalDataResponse.build:201`, with the dump holding exactly one replica buffer of 487–730 MiB
(one `LocalDataResponse`, one `AggregationQueryPager`); IC showed the query is one local read (Δ local reads = 1) and the count
correct when it completes on a larger heap. The matched control with client paging on (5,000, the driver default) survived
**0/3 OOM** with 40–41 correct counts per run, ≈ 14 sub-reads per query and old post-GC ≤ 919 MiB; switching on the shipped
byte threshold (I1, 64 MiB) gave **0/3 OOM** but refused every query (0 useful work, 926–1,056 READ_SIZE failures); restoring
the stated 10,000-row internal paging for plain aggregates (I2, diagnostic build) gave **0/3 OOM** with 38–44 correct counts
and ≈ 7 sub-reads per query. Even 32,768 rows (≈ 513 MiB) OOMed the 2 GiB node at c = 1 (CAL-2G, 2nd query). The budget search
reached the OOM at 4 GiB (c = 2), 8 GiB (c = 4) and **16 GiB (c = 10, 3/3: CAL-16G + REP ×2; 10 buffers, Σ 11.2–12.0 GiB)**;
at 31 GiB (pc82's own resolution) no OOM up to c = 48 because the 5 s read timeout cancels every read from c = 12 on
(3,054 cancellations, 0 useful queries) — the timeout bounds time, not bytes, and at ≤ 16 GiB it did not prevent the OOM
(CAL-16G and REP-2 died while reads were already timing out).

**V1–V7.**

| | Evidence |
|---|---|
| V1 Repetition | T-2G-1..3: heap OOM 3/3 (and CAL-2G at n = 32,768; 16 GiB: CAL-16G + REP-16384M-1/2, 3/3) |
| V2 Matched control | M-2G-1..3 (same build, budget, data, n_T, c, client; paging 5,000): 0/3 OOM, useful work kept |
| V3 Measurement | U: hprof `byte[]` per in-flight read (487/730/1,096 MiB), `DataOutputBuffer`/`LocalDataResponse` counts = in-flight reads (1, 2, 4, 10), JMX heap/old post-GC; K: Δ local reads per query (1 off, ≈ 14 at 5000, ≈ 7 in I2) and count results |
| V4 Intervention | I1-2G-1..3 0/3 (config; protects by refusing: 0 queries/s useful) and I2-2G-1..3 0/3 (diagnostic build, diff `harness/i2.diff`; 0.24–0.27 correct queries/s, same as M); the original failure is on the unmodified build (T) |
| V5 Initiating failure | first error `java.lang.OutOfMemoryError: Java heap space`; OOM thread stack from the dump (`logs/T-2G-*/hprofstacks-oom.txt`) in `DataOutputBuffer.expandToFit` ← `LocalDataResponse.build`; dumps with the holder (`hprofhist.txt`); no scope `oom_kill` |
| V6 Default constraints | every capacity setting at its shipped default (`yaml.diff`: directories only); paging off is the client's request; I1/I2 only in intervention arms |
| V7 Acceptable budget | 2048M heap / 1024M direct = the full default resolution of a 4 GiB node (standing rule: ≥ 512 MiB, 2 GiB ideal); largest failing budget **16384M / 8192M** (32 GiB node), 3/3; no container limit |

**Overlap with U4 (verified, read-limit paging).** Same holder (the replica's `LocalDataResponse` `DataOutputBuffer`), same
off switch (read thresholds) and the same missing sum over concurrent reads; U4's I-arm (64 MiB threshold) is this case's I1.
What differs: U4's read is bounded by the client's 5,000-row page and its response (a `ResultSet` plus a Netty frame of the
page) moves its endpoint into Netty direct memory above 2 GiB; here the server itself drops its stated internal row bound, a
single request reads the whole slice, the response is one row, and the endpoint stays a heap OOM in the replica buffer up to a
16 GiB heap with c = 1 at 2 GiB (U4 needed c = 3). The P-GRS probe shows the GROUP BY members of the cluster (OC-298 …) reach
U4's endpoint instead (Netty direct at encode).

**Cluster rows.** OC-322 and OC-309 (same path): **true positive (U10)**. OC-44: its aggregate part is this result (correction
in §1: plain aggregates take the pager branch, not `:338`); its non-aggregate part is U4's. OC-298, OC-311, OC-312, OC-315,
OC-316 (unpaged GROUP BY `ResultSet`): not tested as a verdict; P-GRS saw the result grow to ≈ 1 GiB and die in Netty direct
memory at 2 GiB (one run, a note). OC-299, OC-310, OC-313, OC-314, OC-317, OC-321, OC-318: not covered (U4's holder and row
bound; I2's 10,000-row sub-reads at 16 KiB rows survived at 2 GiB, which is not a test of them).

**Limits of attribution.** One row width (16 KiB) and one table layout; a single node (coordinator = replica), so the
replica→coordinator copy of a remote read is not exercised. The 31 GiB boundary is "no OOM at c = 8 and c ≥ 12 within 40 s
steps"; c = 9–11 at 31 GiB was not tried (outside the frozen list). The 5 s timeout's protection depends on read speed:
on faster hardware a read serializes more bytes before the timeout, on this node 1 GiB takes ≈ 3.5 s alone.

**Pattern.** Covered by CP-10 (a path that skips the limit: the unpaged aggregate branch) with CP-12 (one item materialized
whole) and CP-6 (nothing refuses before the JVM's OOM), the patterns OC-322 already carries; no new pattern.

**Left on the node.** `pc82:/mydata/s4/u10-w4/` (62 GB): `tree/` and `tree-i2/` (419 MB each), `template/` and the last
clone `node/` (8.1 GB each), `runs/` (45 GB: full logs, GC logs, 10 hprofs of 0.1–12.8 GB), `cls/`, `conf-pristine/`,
`harness/`, `harness-src/`. No process running (no `CassandraDaemon`, client, sampler or hprof job; no `u10-*` scope).
`/mydata/s4/cassandra-base` untouched. Free on `/mydata`: 653 GB, so no hprof was deleted.
