# CASSANDRA JIRA OOM survey (task J1)

*Done 2026-11-16* per [`jira-mining-playbook.md`](../../jira-mining-playbook.md). Data:
[`jira-oom-survey.csv`](jira-oom-survey.csv) (one row per issue, 604 rows). Second-pass record:
[`jira-oom-survey-second-pass.md`](jira-oom-survey-second-pass.md). Prior-art check of the verified cases:
[`jira-prior-art-verified-cases.md`](jira-prior-art-verified-cases.md). This replaces the title/description-only
first pass in [`OOM-leads.md`](../../OOM-leads.md) §2 (2026-11-12) as the reference; that section is kept as history.

ID prefixes used here (README rule): **B** = bypass, **C** = convergence, **R** = recheck, **S** = stacked combo,
**U** = unprotected-accumulation lead, **J** = JIRA task (J1 Cassandra, J2 Hadoop), **F** = data-flow tracing task.
Issue numbers are CASSANDRA-*n*.

## 1. Query and method

- **Query** (2026-11-16, `issues.apache.org/jira` REST search): `project = CASSANDRA AND (text ~ "OutOfMemoryError" OR
  text ~ "OOM" OR summary ~ "out of memory" OR text ~ "\"Direct buffer memory\"" OR text ~ "\"GC overhead limit\"" OR
  text ~ "\"oom-killer\"")` → **604 issues** (Fixed 347, Unresolved 82, Duplicate 50, Won't Fix 41, Cannot Reproduce
  27, Not A Problem 26, Invalid 14, Later 7, Not A Bug 5, other 5).
- **Reading.** Four agents read 151 issues each (description and all comments). Excluded: test/CI/build memory, client
  or tool memory, OOM-handling robustness only, and issues where OOM is not the reported problem. Every issue keeps a
  row with its screen reason.
- **Fix diffs.** For every kept Fixed issue the fix commit was looked up in a full clone of `apache/cassandra` by issue
  key (or by the commits named in comments). **115 of 120 kept Fixed issues have their diff read**; 5 have no commit
  (`diff_read` = no commit found). Classification uses the issue text and the diff.
- **Second pass** (playbook requirement): one agent normalized conventions across shards, read the diffs of 36 rows that
  had been classified from commit subjects only, and spot-checked a seeded random sample (25 kept, 15 excluded).
  Agreement: screen 39/40, class 25/25 on mechanism (23/25 strictly, both differences from the convention change),
  fix_kind 24/25. One excluded issue was re-screened in (11845).
- **Conventions.** `unprotected:accumulation` = memory grows and no capacity control applies;
  `unprotected:configuration` = a control exists but its default or configured value leaves it off or unbounded;
  `convergence:multiplicity` needs an explicit per-owner cap; a leak inside a capped pool is `bypass:release-defect`,
  an uncapped leak is `unprotected:accumulation` with fix_kind `release fix`. Flows use the data-flow playbook names;
  the original wording is kept in `flow_detail`.

## 2. Counts (246 kept)

**Resolution groups:** fixed 120; open 45 (Unresolved 42, Later 3); closed without a fix 81 (by design or invalid 45:
Won't Fix 17, Not A Problem 13, Invalid 8, Not A Bug 4, other 3; Duplicate 26; Cannot Reproduce 10).

| Class | Kept | of which Fixed |
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

| Flow | Kept |
|---|---|
| replica mutation stage → memtable → flush (incl. commit log, replay, index/MV flush) | 54 |
| read path and caches | 39 |
| repair / streaming | 30 |
| compaction | 28 |
| client request intake | 28 |
| coordinator read | 19 |
| coordinator write | 11 |
| internode messaging | 9 |
| hints | 8 |
| unknown | 8 |
| other (JVM runtime 5, gossip/schema 4, Accord 1, logging 1, multiple 1) | 12 |

| fix_kind (kept Fixed, 120) | Count |
|---|---|
| other (code change that removes the allocation or the trigger) | 46 |
| release fix | 23 |
| new limit | 18 |
| accounting change | 14 |
| doc or default change | 11 |
| backpressure | 6 |
| none (marked Fixed without a fix) | 2 |

**Budget (kept):** heap 197, direct 19, native 17, cgroup/kernel 12, unknown 1.
**Misconfiguration involved:** `config_involved` = yes in **66 of 246** kept issues (27 %); in most of them the
trigger is a default sizing or an OS limit (`vm.max_map_count`, ulimit), not a user's mistaken value.

## 3. What the history says

1. **Most real OOMs are unprotected accumulation** (131 + 22 of 246): memory that no capacity control covers, grown by a
   data or workload shape (wide partitions, huge cells, many sstables or tables, deletes, repairs over many ranges).
   The capacity-check inventory of capacity-enforcement-exp cannot see these; JIRA and data-flow tracing (task F1) can.
2. **Accounting mismatch is the most common bypass** (18, 16 fixed), and the same pattern recurs: deletes not counted
   in memtables (3741 → 6655 → 9194), commit-log replay bounded by count (8639), hint pages by columns (2652, 3624),
   cache weighers (4315, 4860). Our B6 and B7 are new members of this family.
3. **Fixes rarely add limits** (18 new limits and 6 backpressure of 120). Most fixes remove one allocation or release a
   leaked reference, so siblings of the fixed path are the natural variant leads.
4. **Direct and native memory are a small share of the history (36 of 246)** but are where the recent and open issues
   cluster (21529, 21656, 19535, 17025, 18762), matching our C1, C2 and S1 results.
5. **The project closes sizing problems as by design** (45 closed by design or invalid): a report needs a broken or
   misleading documented contract (see `OOM-leads.md` §2.3).

## 4. Positive-control shortlist (reproduce on the affected build, then the fixed one)

Chosen for low cost and different classes and flows. Each is a known, fixed bug: reproducing it shows our harness
detects and attributes a real OOM; it is not a new finding.

| Issue | Class · flow | Affected → fixed | Trigger |
|---|---|---|---|
| **9194** (with 6655, 3741) | bypass:accounting-mismatch · memtable | 2.0/2.1 → 2.0.15/2.1.6 | delete-only workload: deletes not charged, memtable never flushes |
| **8639** | bypass:accounting-mismatch · commit-log replay | → 3.2 | replay bounded by mutation count, not bytes; dense mutations OOM on restart |
| **11026** | bypass:release-defect · memtable flush | 3.0.2 → 3.0.3 | sstable min/max values are slices of memtable slabs, pinning 1 MiB slabs |
| **20052** | bypass:exempt-path · client request intake | → 4.1.8 / 5.0.3 | v5 messages had no size limit, even an unauthenticated AUTH_RESPONSE (B1 shares this path) |
| **19336** | convergence:multiplicity · repair | → 4.0.13 / 4.1.5 / 5.0 | Merkle trees × concurrent validation requests (vnodes, many tables) |
| **10972** | unprotected:accumulation · hints | → 3.0.4 / 3.4 | file-based hints with no buffer cap (fix: `MAX_HINT_BUFFERS`) |

Alternates: 2652/3624 (hint paging), 10797 (stream writers × sstables, needs a tightened budget), 12689 (MV lock
deadlock stalls MutationStage; a stalled-consumer control for B6/S2), 14834 (histogram spool per LCS output sstable).

## 5. Variant leads in 5.0.9 (not run; each needs the pre-pick JIRA check before it is queued)

Each was checked against the pinned 5.0.9 source by the reading agent unless marked *to verify*.

| Lead | Source issue(s) | 5.0.9 observation | Shape |
|---|---|---|---|
| **Merkle-tree requests unbounded at defaults** | 19336, 17787, 18762 | `concurrent_merkle_tree_requests` defaults to 0 (no limit), so the fix is opt-in; the yaml says `repair_session_space` "limits memory usage for Merkle tree calculations" | unprotected:configuration; documented-contract gap |
| **Client-supplied decompression length** | 14997 (open) | `transport/Compressor.java` LZ4 (and Snappy) allocates `heapBuffer(uncompressedLength)` from a 4-byte client value; compression is negotiated at STARTUP, before auth (v4 and below) | unprotected:accumulation; one request |
| **NoSpamLogger unbounded message map** | 21474 (fixed only in 6.0-alpha3/7.0) | `NoSpamLogger.lastMessage` is an unbounded map; some keys include client-influenced text (corrupt-frame CRC values, protocol-exception messages) | unprotected:accumulation; regression check of an unbackported fix |
| **Direct pools summed past `MaxDirectMemorySize`** | 21529 (open, 5.0.6) | chunk cache + networking pool + unpooled users each capped, never checked together | convergence (direct); same family as R1-V / C1 / S1 |
| **Decimal aggregates skip the precision cap** | 21401 (open) | SUM/AVG in `AggregateFcts` use `BigDecimal` without `MathContext`; `DecimalType` arithmetic caps at 10,000 digits | bypass:exempt-path; tiny request |
| **Slab region waste uncharged** | 20298 (test-only fix) | `SlabAllocator` charges requested bytes but holds a 1 MiB region per memtable; many tables leave unaccounted waste | bypass:accounting-mismatch (B7-like) |
| **Commit-log replay counts serialized bytes** | 8639 | the 64 MiB in-flight bound charges serialized size; tiny-cell mutations expand on heap (B6 ratio) | bypass:accounting-mismatch; same as lead N4 (N = new lead from the capacity-enforcement bypass notes) |
| **Guardrails off by default** | 15250, 9454, 9413 | `in_select_cartesian_product`, `partition_keys_in_select`, read-size thresholds all disabled by default | unprotected:configuration; cheap positive-style checks |
| **JDK temporary direct-buffer cache × threads** | 10689, 13931, 19976, 17025 | 5.0.9 sets no `-Djdk.nio.maxCachedBufferSize` | unprotected:configuration (native) |
| **Per-thread read-ahead buffers** | 15452 | `ThreadLocalReadAheadBuffer` keeps 256 KiB direct per thread per sstable; `close()` frees only the current thread's entry | unprotected:accumulation (direct); *to verify* on cross-thread close |
| **MutationStage queue unbounded with stalled consumers** | 6346, 10937, 11460, 12689, 13213, 19958 | unchanged; relies on timeout shedding | same family as B6 and S2 |
| **Streaming split by rows, not bytes** | 13299 | `CassandraStreamReceiver` batches 100 rows; wide rows with large cells still form large mutations | unprotected:accumulation |

## 6. Open items

- 42 kept issues remain `unknown` (no cause established); they were not reworked.
- Rows flagged for a human look in the second-pass record: 12707, 13126, 11082, 8295, 10766, the configuration vs
  accumulation borderline rows (1445, 15531, 21227, 21233), 3171 and 3535, and excluded rows similar to 11845
  (6862, 8917, 14653).
- Not done here: positive-control runs, and turning variant leads into campaign rows (each needs its own pre-pick
  check). Hadoop survey (J2) not started.
