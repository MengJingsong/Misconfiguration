# OOM leads — patterns from our cases and Cassandra JIRA, and where to look next

*Written 2026-11-12.* This file collects (1) the OOM patterns seen in the Cassandra cases run so far,
(2) the OOM patterns in Cassandra's own JIRA history, and (3) search patterns and concrete leads for
finding further, undocumented OOM cases. It is a lead list, not a result: nothing in §4 has been run.
Statuses and numbers for our cases come from [`cassandra/cases/_INDEX.md`](cassandra/cases/_INDEX.md)
and the linked case files; follow those for evidence. Method and classification rules:
[README](README.md), [verification-protocol.md](verification-protocol.md),
[jira-mining-playbook.md](jira-mining-playbook.md).

## 1. Patterns in our cases (Cassandra 5.0.9)

Cases read: B1, B6 (A–E), B7, R1–R6 (including the superseded run 4 and void run 5 of the row-cache
pair), C1 runs 1–3, commitlog + hints. The 2026-11-12 batch (C1 run 4, C2, C3, R1 at defaults, R6 at
≥ 512 MiB direct) had no results when this was written.

> **Update 2026-11-16.** The 2026-11-12 batch has since finished (see [`_INDEX.md`](cassandra/cases/_INDEX.md)):
> **C1 run 4** `verified-OOM · diagnostic` (P4 resolved: with ≥ 4 loaded peers the per-peer reserves fill
> the 512 MiB global reserve, and the queued frames exceed a 512–640 MiB direct limit); **C2**
> `verified-OOM · deployment` at shipped defaults (concurrent reads to slow clients; no backpressure on
> encoded responses, a J2-type queue); **R1-V** `verified-OOM · deployment` (P3 at defaults, container
> limit); **C3** and **R6-V** `negative`. So P3 and P4 now also have default-regime results, and §1.3's
> takeaway is no longer limited to P1/P2. Lead U1 (DOB buffers being filled are not limited by
> `DOB_MAX_RECYCLE_BYTES`) came out of R6-V/C3; see the campaign plan.

### 1.1 Patterns that led to OOM or service loss

| # | Pattern | Cases | Evidence (short) | Regime |
|---|---|---|---|---|
| P1 | **The limit counts different bytes from the memory actually held** | B6, B7; aggravates R3/R4 | B6: internode queues count on-wire bytes; tiny-cell mutations are ≈ 19.7× (coordinator) / 16.7× (replica) that on heap, blob 2.2×. B7: Caffeine weigher counts key + value only; key cache 2.14×, counter cache 1.80× its cap (8-byte keys), 1.15× at 512 B; cache counter stays at the cap | **default** (verified) |
| P2 | **Memory released only "on response or timeout", and a slow component stalls the response** | B6 A, B, D, E | Coordinator keeps each sent mutation (`hintOnFailure`) until the replica answers or the deadline, charged to no counter; on the replica, expiry happens only when a stage thread runs, and a storage stall blocks those threads. A: 8 GiB replica, 30 s disk stall, default timeouts → ≈ 97% of 2 min in Full GC. D: two slow replicas, 60 s timeouts → heap OOM up to 6 GiB. E: default timeouts → OOM only at 512 MiB (3/5) | default (A verified service loss; D diagnostic: 60 s timeouts) |
| P3 | **Several limits each hold, but nothing bounds their sum** | R1–R6 | Each pool alone 50–80% of the budget; together OOM. R1 off-heap memtable + file cache (container memory limit); R2/R6 hint slabs + per-thread serialization buffers (direct memory); R3/R4 memtable + caches (heap); R5 row cache + index summaries (container limit) | **custom** values or tightened budget only; at defaults R6's window is ≈ 15 MiB wide at 192 MiB direct |
| P4 | **A per-owner limit is multiplied by the number of owners** | R2, C1, (C3, C5) | R2: 36 worker threads each kept a 7.63 MiB buffer (≈ 282 MiB). C1: each receive connection's allowance Q sits outside the global reserve, so N connections hold N·Q extra | R2 custom; C1 at default Q is dominated by the fixed 512 MiB reserve → unresolved |
| P5 | **Timing: fill the standing pool first, then burst** | R5 (runs 4–6), R1, R2, R6 | Row cache + index summaries: burst-then-fill not reached (run 4); concurrent but burst finished early → 93% peak (run 6 A); cache full, then burst → killed at 1973/2000 MiB (run 6 B). Index summaries are capped only at the periodic resize | custom |
| P6 | **At larger heaps the failure is GC collapse, not OOM** | B6 A, B6 D, R3 | B6 A at 8 GiB: ≈ 97% Full GC, OOM only occasionally; B6 D at 8 GiB: ≈ 99% live, survives; R3: ≈ 6.5 min of back-to-back Full GC before the kill | — |

### 1.2 Patterns that did not lead to OOM

| Pattern | Case | Why no OOM |
|---|---|---|
| Leak inside a capped pool | B1 | `LargeMessage.onComplete()` never calls `releaseBuffers()`; the networking pool fills to its 128 MiB cap and stays there, later buffers are unpooled and reclaimed by GC. Counters (`OverflowSize`) drift without bound while memory does not. A growing counter does not prove growing memory. |
| Uncounted overhead that is a fixed share of the heap | B7 | Default caps are derived from the heap, so the overshoot is ≈ 7.5% of the heap up to 2 GiB and shrinks above; other live data never reached the ≈ 92% needed. |
| Memory that does not grow with the variable varied | C1 runs 1–2 | Victim occupancy settled at ≈ 266 MiB regardless of Q and offered load; the fixed global reserve hides the N·Q term. |
| Blocked before a valid arm | commitlog + hints | Disk budget mount filled from flush/compaction overhead in the control arm. |

### 1.3 Takeaway

Both default-regime results (B6, B7) came from P1 and P2, found by tracing a data flow (B6 from the
coordinator write path) or by analysing a failure's heap dump (B7 from R3/R4). The if-check pairs (P3)
reproduce only with custom values or tightened budgets.

## 2. Patterns in Cassandra JIRA

> **Superseded 2026-11-16** by the formal survey [`cassandra/leads/jira-oom-survey.md`](cassandra/leads/jira-oom-survey.md)
> (fix diffs read, second pass). This section is kept as the first pass.

### 2.1 Query and screening

- Query (2026-11-12, `issues.apache.org/jira`, REST search):
  `project = CASSANDRA AND (text ~ "OutOfMemoryError" OR text ~ "OOM" OR summary ~ "out of memory" OR text ~ "\"Direct buffer memory\"" OR text ~ "\"GC overhead limit\"" OR text ~ "\"oom-killer\"")`
  → 604 issues; 347 `Fixed`; 170 `Won't Fix` / `Not A Problem` / `Invalid` / `Duplicate` /
  `Cannot Reproduce` / `Not A Bug` / `Later`.
- Screened out: test, CI and build components; issues mentioning OOM only in comments (148 fixed,
  61 unfixed; for these only titles were scanned, which added 9318, 8969, 4860, 3017, 20052, and
  15013, 16663, 13265, 16886 were pulled by key). Kept: **150 fixed, 97 unfixed**, all read.
- Classification is from title and description only, **not from the fix diffs**; counts are
  approximate and a second pass should spot-check them per the JIRA playbook. Not yet in the
  playbook's `cassandra/leads/jira-oom-survey.csv` format.

### 2.2 Cause patterns in fixed issues (≈ 109 with a real cause)

| # | Pattern | Keys (CASSANDRA-) | Typical shape |
|---|---|---|---|
| J1 | **One large item loaded whole** (29) | 208, 436, 1904, 2652, 2849, 3017, 3624, 4116, 4314, 4555, 4918, 5746, 6149, 6191, 8559, 9530, 11383, 11710, 12268, 12618, 12769, 12796, 13299, 14315, 14925, 16886, 18513, 20052, 20752 | Wide partition, huge mutation, corrupt length field, tombstone pile or oversized message materialized in one piece. E.g. 2652/3624 hint paging × mutation size; 12796/13299 wide partition → one giant mutation in 2i / MV / streaming; 9530/18513 corrupt length → huge allocation; 8559 tombstone warning built a 777 MB string; 20052 v5 CQL message size not limited (fixed 4.1.8) |
| J2 | **Queue without backpressure, or a stalled / dead consumer** (27) | 157, 401, 609, 685, 885, 1607, 2817, 3530, 3537, 5926, 6079, 6087, 6357, 8245, 8285, 8969, 9318, 9525, 10971, 10972, 12358, 12689, 13265, 14855, 15013, 16663, 20084 | Producer outruns consumer, or the consumer stops (dead thread, disk IO, shared executor, stuck wait) while the queue keeps accepting. 10971 compressed commit log / 10972 hints "no backpressure and can OOM"; 14855/15013 native response Flusher queue; 3530/9525 dead thread leaves its queue growing; 6079 flush starved by batchlog on a shared thread; 12358 slow 2i flush holds memtables; 9318 bound in-flight coordinator requests; **8969** documents that high timeouts cause memory build-up |
| J3 | **Per-object memory × number of objects** (16) | 2142, 2301, 3171, 3201, 4142, 4201, 5982, 6169, 9573, 10797, 11854, 13008, 13754, 14096, 15202, 16201 | Buffer per sstable / table / thread / connection / range. 3171 1 MB buffer per sstable in compaction; 4142 scanner per sstable (×5757); 5982 2000 tables of memtables; 13754/16201 per-thread retention; 6169 thread per vnode token; 14096/15202 Merkle trees × ranges; 3201/4201/13008 mmap count ("Map failed") |
| J4 | **Leak, or release on the wrong path** (16) | 2708, 2868, 6047, 6107, 6541, 7743, 7983, 9549, 11026, 11159, 11739, 15400, 15407, 15902, 17895, 21474 | Memory referenced after its lifecycle, often only on error / abort / termination. 2708 dropped table kept in a map; 9549 Ref.GlobalState; 11159 SASI memtable never switched; 15902 repair threads not closed; 17895 zero-copy streaming writer → direct OOM; 21474 NoSpamLogger unbounded cache |
| J5 | **The limit counts the wrong thing** (13) | 2006, 3163, 3741, 4315, 4860, 6078, 6655, 8164, 8639, 9194, 16071, 19336, 20577 | 3741 → 6655 → 9194 deletes not counted in memtable size (fixed three times); 6078 live-ratio estimate; 8639 commit-log replay bounded by mutation count, not bytes; **4860** row cache entry size estimated at 24 B; **4315** move to a weigher counting per-entry overhead (pre-Caffeine library); 16071 MiB setting read as bytes; **19336** `repair_session_space` applied per response, not in total; 20577 unused direct allocation fragments memory |
| J6 | **Defaults too large for the heap** (8) | 1275, 1469, 1558, 1641, 2082, 2413, 4141, 6059 | Memtable / cache defaults OOM newcomers; adaptive defaults introduced |

Excluded from the cause counts: OOM handling and robustness (218, 264, 2076, 2228, 2269, 3655, 5716,
6255, 7507, 7579, 9861, 10553, 12849, 13006, 13987, 14898, 15214, 16254, 17128, 17795, 18336, 19831,
20457, 21578), tools and client-side memory (789, 1867, 2189, 3264, 4098, 4851, 4969, 5555, 5562, 6404,
6775, 7238, 7926, 7956), and test-only OOMs (10697, 11525, 15035, 17213, 18218, 18675, 19356, 19567,
20543, 21410).

Cross-cutting: in most fixed issues the trigger is a **workload or data shape** (wide partitions,
deletes, many tables or sstables, vnodes, repair), not one misconfigured value. A misconfiguration is
the direct trigger mainly in J6, in 16071, and in "user cached too much" reports.

### 2.3 What the project closes as by design (97 unfixed)

- **No global heap governor.** Requests to block requests when the heap is nearly full (4505–4510,
  duplicates; 4510 Won't Fix), basic QoS (3911), a per-request byte limit (9413, 4304), cache safety
  (1445), and heap-pressure reaction (2875) were declined. The project relies on per-mechanism limits
  plus operator sizing.
- **Sizing problems are closed as not-a-bug:** large-blob loads (9092), long batches (7303), "Map
  failed" from `vm.max_map_count` (14474), direct-memory OOMs (17025 Invalid; 18762, 19535 Cannot
  Reproduce), RSS growth to a kernel kill (2868 fixed; 8723, 11109 Cannot Reproduce; 20565 Not A Bug).
- **UDF heap exhaustion** (21227, 21233) is Not A Bug because UDFs are disabled by default.

Consequence for upstream reports: a report needs a **broken or misleading documented contract**, not
only "it can OOM".

### 2.4 JIRA ↔ our cases

| Our case | JIRA | Implication |
|---|---|---|
| B6 | **8969** — the 5.0.9 `cassandra.yaml` (server-side timeouts comment, ≈ l. 1305–1316) says timeouts protect against "memory build up … you should avoid putting these settings too high"; also 9318, 15066 (introduced the internode limits), 14855 / 15013, 13299, 8639 | B6 D's 60 s timeouts are a documented risk (stays `diagnostic`); B6 A (default timeouts + disk stall) is the stronger finding. No ticket found on the on-wire vs heap ratio itself; it is the same family as 8639 |
| B7 | **4860**, **4315**, 10855 (move to Caffeine) | Possibly a regression of 4315's per-entry overhead accounting after the move to Caffeine. **Check the 4315 and 10855 diffs before filing** |
| B1 | 20052 (v5 message size limit, in 5.0.9), 15229 (networking pool did not reuse partly freed chunks) | Search for an existing report of the missing `releaseBuffers()` before filing |
| C1 / C3 / R2 | J3: 13754, 16201; 11937 (DataOutputBuffer trimming of large buffers) | Per-thread retention has OOMed real users; C3 has precedent |
| R1–R6 | J6 and the declined global-governor requests (§2.3) | Summing pools is treated as the operator's job → report as sizing / validation gaps |
| commitlog + hints | 10971, 10972 | Both added backpressure; check those mechanisms for a bypass |

## 3. Search patterns for undocumented OOM cases

Ordered by yield so far. Each pattern gives a question to ask of every memory holder, how to find
candidates in the source, and how to test.

### S1. Counted unit vs held memory (from P1, J5)
- **Ask:** what does the limit count (on-wire bytes, payload, entries, items) and what form does the
  memory take (deserialized objects, container nodes)?
- **Find:** `maximumWeight` / `.weigher(` caches; admission code charging `serializedSize()` or frame
  size; size estimators (`unsharedHeapSize`, live ratio).
- **Test:** one heap histogram per holder gives held ÷ counted. Only run OOM tests where
  ratio × default cap is a large share of the heap. Use worst-case data: many tiny items (1000-cell
  maps, 8-byte keys), tombstone-only writes.

### S2. Release on response or timeout + a stall (from P2, J2)
- **Ask:** what ends this allocation's lifetime, and can the thread that ends it be blocked by the
  same fault?
- **Find:** callback maps, write / read handlers, pending-response holders: read repair, Paxos,
  counter writes, batchlog, hint dispatch, speculative retry.
- **Test:** dm-delay disk stall, `SIGSTOP` a peer (connection stays open, unlike a refused
  connection), packet loss, long GC on a replica. **Keep timeouts at defaults** — raised timeouts are
  already documented (8969).

### S3. Dead or stalled consumer with an accepting queue (from J2)
- **Ask:** if the consumer thread throws or blocks, does anything push back on producers?
- **Find:** executors with unbounded queues (`SEPExecutor` reports a maximum queue of
  `Integer.MAX_VALUE`), work queued without admission control.
- **Test:** stall the consumer (dm-delay) or make it throw (Byteman); watch the queue and heap.
  Candidates: hint dispatch, flush with slow 2i work, batchlog replay, commit-log allocator.

### S4. Owner multiplicity (from P4, J3)
- **Ask:** the limit is per what, and what bounds the number of those?
- **Find:** per-thread buffers (`FastThreadLocal` holders in 5.0.9: `io/util/DataOutputBuffer`,
  `io/util/DataOutputStreamPlus`, `io/util/ThreadLocalByteBufferHolder`, `transport/CBUtil`,
  `io/compress/DeflateCompressor`, `security/EncryptionUtils`, `hints/EncryptedChecksummedDataInput`,
  `utils/vint/VIntCoding`); per-connection allowances; per-table memtables; per-sstable readers;
  per-range Merkle trees.
- **Test:** at defaults, sweep the owner count to realistic extremes (hundreds of tables, thousands
  of sstables, many client connections, a large native-transport thread pool).

### S5. Paths that skip the limit (from J1, J5, B1)
- **Ask:** do startup replay, hint dispatch, batchlog replay, streaming, repair, error / abort paths
  and every protocol version go through the same admission check?
- **Find:** list each limit's callers; compare with every path that creates the same objects.
- History: 609 (commit-log replay ignored memtable limits), 8639 (replay bounded by count), 20052
  (v5 had no message size limit), B1 (release missing on one path only).

### S6. Memory outside the operator's budget (from R1, R5, J4)
- **Ask:** is this memory bounded by `-Xmx`, by `MaxDirectMemorySize`, or only by the container?
- **Find:** JNA `Native.malloc` (row cache, index summaries), mmap, glibc arena retention, Netty.
- **Test:** start from JIRA reports of RSS growth to a kernel kill closed as Cannot Reproduce /
  Invalid / Not A Bug (8723, 11109, 17025, 18762, 19535, 20565; also 2868 fixed). They have real
  symptoms and no explanation; reproducing one at defaults would be strong evidence.

### Process rules
1. **Data-flow tracing (F1) before new configuration pairs.** For each holder in a flow answer:
   counted vs held unit (S1); lifetime end and whether a fault blocks it (S2, S3); owner multiplier
   (S4); budget it draws from (S6). Any "no" or "unclear" is a lead.
2. **Realistic faults, not raised values.** Disk stall, slow replica, dead thread keep the case at
   defaults and reportable.
3. **Check the docs first.** "Undocumented" means the yaml and the docs do not already warn (B6 D
   falls under 8969; B6 A does not).
4. **JIRA fixes as templates.** For each fixed accounting / backpressure bug, check siblings and
   regressions in 5.0.9.
5. **Measure the ratio before the OOM run** (B7 showed the overshoot from one histogram).

## 4. Concrete leads (not run)

Source checked read-only in `systems/cassandra/source` (5.0.9) on 2026-11-12 where a location is given;
everything else is a hypothesis to verify.

| # | Lead | Patterns | Hypothesis | Source / basis | Cost | Priority |
|---|---|---|---|---|---|---|
| L1 | **Native transport in-flight bytes × tiny-cell batches**, mutation stage slowed by a disk stall | S1 + S2 | `native_transport_max_request_data_in_flight` (default heap/10; per IP heap/40) counts request bytes; if tiny-cell batches expand ≈ 20× on heap as in B6, the limit admits ≈ 2× the heap while the stage is slow. B6's mechanism on the client side | Defaults confirmed at `config/DatabaseDescriptor.java:649–657` (`maxMemory()/10`, `/40`); the unit charged (frame vs envelope bytes) still to confirm in `transport/ClientResourceLimits`; payload and harness from B6 | low | 1 |
| L2 | **Paxos state cache weigher** | S1 | Weigher counts only the `accepted` / `committed` update heap size, not the key, the `Snapshot` object or the cache node; B7 sibling for `paxos_cache_size` | `service/paxos/PaxosState.java:73–74`; default `paxos_cache_size` = min(max(1 MiB, 1% of heap), 50 MiB) (`config/DatabaseDescriptor.java:850–852`), so as in B7 the overshoot is bounded by a heap-derived cap at defaults | low (B7 harness) | 2 |
| L3 | **`max_mutation_size` × heap expansion × concurrent writers** | S1 + S4 | 16 MiB on-wire limit (default `commitlog_segment_size / 2`); at ≈ 20× expansion one mutation is ≈ 320 MiB of heap, times `concurrent_writes` | Expansion ratio from B6 | low | 3 |
| L4 | **Hint dispatch / batchlog replay with a stalled or failing consumer** | S3 + S5 | Replay paths may load or queue work without the admission applied to client writes | JIRA 2652, 3624, 6079, 10972 | medium | 4 |
| L5 | **Reproduce an unexplained RSS-growth report at defaults** | S6 | Native or allocator growth not covered by heap / direct limits | JIRA 8723, 11109, 17025, 18762, 19535, 20565 | medium–high | 5 |
| L6 | Prepared-statement and streaming-state cache weighers | S1 | Check whether `QueryProcessor.getSizeOfPreparedStatementForCache` and `StreamingStateWeigher` count container overhead | `cql3/QueryProcessor.java:115–116`, `streaming/StreamManager.java:270–271` | low (read first) | — |
| L7 | Commit-log replay limit unit | S1 + S5 | Check whether 8639's fix bounds replay by heap size or by on-wire bytes; tiny-cell mutations would expand ≈ 20× | JIRA 8639 | low (read first) | — |
| L8 | Tombstone-only / range-tombstone writes in 5.0 memtables | S1 | Regression check of the delete-accounting fixes (3741 → 6655 → 9194) | JIRA | low | — |
| L9 | Variants of the B7 regression | S1 | Confirm whether 4315's per-entry overhead accounting was lost in the Caffeine move (10855) | JIRA 4315, 10855 diffs | low (read first) | — |
| L10 | `repair_session_space`-style limits applied per item, not in total | S1 + S4 | Other "space" limits applied per response or per session | JIRA 19336 | low (read first) | — |
| L11 | Backpressure added by 10971 (compressed commit log) and 10972 (hints) | S5 | Check the new mechanisms for a bypass; relates to the parked commitlog + hints case | JIRA | medium | — |

**Positive controls** suggested by the JIRA playbook (reproduce on the affected version, then the
fixed one): 9194 (delete-only memtable never flushes), 12796 (wide partition + 2i rebuild), 10972
(hints without backpressure). They cover J5, J1 and J2 and are cheap to reproduce.
