# B14 — batch_size_fail_threshold: single-partition batches of tiny values skip the batch check and hold ≈ 20× their wire bytes of heap inside the in-flight limit  <!-- file: cassandra/cases/batch_size_fail_threshold--single-partition-batch-heap-expansion/batch_size_fail_threshold--single-partition-batch-heap-expansion.md -->

| Field | Value |
|---|---|
| Case ID | `B14` (bypass, accounting mismatch; README "ID prefixes") |
| From | `OC-11` of the phase 1 OOM candidate list |
| Phase-1 case file | [`batch_size_fail_threshold-verifyBatchSize-mutations--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md); stage 4: [`results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`; built tree `/mydata/s4/cassandra-base` on `ms0604`, `git describe` = `cassandra-5.0.9`, clean), OpenJDK 11.0.33 (aarch64, Ubuntu 22.04) |
| Stage 1 (design) | OOM-agent stage-1 session (workflow), 2026-11-18 ~08:00–08:45 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session (workflow), 2026-11-18 08:14–09:40 America/New_York, `ms0604` (aarch64) |
| Verdict | **`retry`** (status `candidate`; frozen row O6: the matched control also reached OOM) |

## Summary

- **Conclusion (stage 2):** **retry.** Tiny-value batches reached Java heap OOM with all capacities at their defaults:
  3/3 at a 2 GiB heap, 1/1 at 4 GiB, 2/3 within the hold at 8 GiB. The in-flight counter stayed at or below its limit
  (14 × 14.7 MB) while the heap held ≈ 10× that in decoded values (98.5 % of the dump). Capping in-flight at one request
  stopped it 0/3. But the frozen matched control (same bytes as 64 blobs) **also reached OOM 3/3**, through a different
  holder: on this m400, timed-out blob writes released their in-flight charge while 92 built mutations stayed queued.
  So V2 is unmet.
- **Root cause (as measured):** the native in-flight limit counts **wire bytes**. A v5 batch of many tiny bound values
  expands ≈ 10–15× **during decode on the event loops**, before any batch check runs. The two-partition arm failed before
  any `Batch too large`, so `batch_size_fail_threshold` and its single-partition exemption play no part in the endpoint.
- **For the retry:** use a control that never reaches the write (for example the blob batch over two partitions, rejected
  after decode), matched against the two-partition tiny-value arm. Predict the holder in decode with K at the cap.
  Allow 8 GiB runs to finish their dump inside the window.
- **Hypothesis under test (stage 1, as designed):** a CQL `BATCH` whose statements all hit one partition is one mutation,
  so `verifyBatchSize` returns before any size check (`BatchStatement.java:334`); for every batch the check runs only after
  the whole request has been decoded (`BatchMessage.java:56-75`, one heap `byte[]` + `HeapByteBuffer` per bound value,
  `CBUtil.java:480`) and built into a `PartitionUpdate` (`BatchStatement.java:428` → `:270-324`). The only control that
  bounds concurrent requests, the native in-flight limit (heap/10 global, heap/40 per IP), charges the **on-wire body
  bytes**. A 15.8 MB batch of 55,000 rows × 50 one-byte cells holds ≈ 20× that (≈ 330 MB) on the heap while it is in flight,
  so the 14 requests the limit admits at a 2 GiB heap need ≈ 4.6 GB, and the heap is predicted to fail at 4–6 concurrent
  requests (K ≈ 0.3–0.4 of the limit) with every capacity at its shipped default.

## 1. Candidate

**Candidate row (quoted from `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/phase1-oom-candidates.md`, status as
handed to this session):**

> | OC-11 | 2026-11-12 | `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous` | legacy | [N9] Single-partition, internal and virtual-table batches skip `batch_size_fail_threshold`, and the whole batch is on the heap before the check; bounded by the 16 MiB message size, so a payload shape for other candidates rather than a holder. | CP-10, CP-11 | picked: B14 |

**Phase-1 case (stage 3, 2026-10-26).** The constraint is `batch_size_fail_threshold` (default `50KiB`,
`Config.java:331-332`; `conf/cassandra.yaml:1842-1844` "Fail any multiple-partition batch exceeding this value"). Its operand
is `IMutation.dataSize` (cell data, not serialized size or object overhead), checked once per request in
`verifyBatchSize` (`BatchStatement.java:332-366`) after `getMutations` has built every mutation (`:428` → `:439`). Bypasses
traced: single-mutation batches (`:334`, CASSANDRA-10876), conditional batches (`:422-423`), virtual-table batches
(`:425-426`), internal batches (`:559-570`), and the overshoot before the check (the whole batch is already on the
coordinator heap). The recheck (2026-11-16, E1–E4) named the gap this case tests: "the decoded request plus every built
`IMutation` … are already on the coordinator heap" and left "whether the decoded objects … exceed its on-wire bytes by a
large factor (many tiny cells)" undetermined — "a question for the in-flight budget, not for this threshold". The phase-1
row likewise calls the shape "a payload shape for other candidates rather than a holder". This case tests that shape
**with its own holder**: the in-flight batch request itself.

**Stage 4 (advisor's Mac, 2026-10-26, outcome class true positive, "caps only on some paths (bypass)").** Unit tier: at
F = 50, 100, 200 KiB a multi-partition batch was rejected (`Batch too large`, 0 rows, 0 memtable bytes, one ERROR line
each) iff its measured `dataSize` > 1024·F; all 18 single-partition batches were accepted, up to 209,015 B at F = 50.
Cluster tier (heap 2 GiB): `multi 30` put 0 B on disk at 50 KiB and 12.31 MB at 100/200 KiB; `single 30` put 12.31 MB at
every F. Stage 4 measured disk and memtable bytes only; the coordinator heap before the check was named as not measured.

**JIRA prior art (read only; nothing posted).** Survey file
`capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv` (604 rows): CASSANDRA-3911 (Won't Fix:
"QoS … to stop clients OOMing" — large batch requests, no per-request limits; by-design set), CASSANDRA-16201 (Fixed
3.11.10/4.0: `BatchUpdatesCollector` pre-sized each partition's row builder to the batch's total row count, NTR threads
held hundreds of MB; fix stops the over-allocation — a different allocation than the one here; in 5.0.9
`SingleTableUpdatesCollector` sizes by the per-key count, `BatchStatement.java:296-299`), CASSANDRA-6107 (Fixed 1.2.11,
prepared-batch cache, unrelated path). JIRA REST search (2026-11-18, `project = CASSANDRA AND …`):
`text ~ "batch_size_fail_threshold"` → 64 hits, relevant: CASSANDRA-10876 (Fixed 3.6: "ignore size on single partition batch
statements" — the exemption is intentional), CASSANDRA-12761 (Fixed 3.10: yaml text updated for it), CASSANDRA-11522 (Not A
Problem: "a batch with a single statement is exactly the same than a single similar insert"), CASSANDRA-16232 (Open: the
threshold does not apply to LWTs), CASSANDRA-19413 (Triage: the operand ignores primary-key size), CASSANDRA-17193 (open:
move the thresholds to guardrails); `summary ~ "batch" AND (OOM | OutOfMemory | heap)` → 10 hits, none for in-flight
expansion (16201, 6107, 7303 Thrift response, others unrelated); `text ~ "single partition batch" AND text ~ "memory"` →
33 hits, relevant: CASSANDRA-15430 (Duplicate, 3.0.18 `BatchMessage.execute` 10× more allocations than 2.1),
CASSANDRA-21141 (Fixed 6.0: reduce allocations turning a `BatchStatement` into a `Mutation` — throughput, not a bound),
CASSANDRA-7402 (Open: "Add metrics to track memory used by client requests" — no such metric exists). **Verdict:** the
single-partition exemption is **by design / documented** (10876, 12761, 11522); the OOM claim — the wire-byte in-flight
limit admitting ≈ 2× the heap in decoded and built tiny-cell batches, all checks after allocation — is **`new`** (no report;
7402 open says request memory is not measured). Relation to other candidates (not a list change): OC-4 (open) names the same
decode copy (`≈ 15×` for a 16 MiB batch of 1-byte values) for the v4 one-request-per-connection admission; this case uses
protocol v5, where the in-flight limit is enforced for large messages, so K ≤ C holds by the server's own check.

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

1. **Decode (event loop, charged on wire bytes).** A v5 request larger than one 128 KiB frame takes
   `CQLMessageHandler.processFirstFrameOfLargeMessage` (`CQLMessageHandler.java:516`): size check against
   `native_transport_max_message_size` (`:551`), then in the default non-throwing mode `acquireCapacityAndQueueOnFailure`
   (`:603-605`, `:693-698`): the body size is charged to the connection's 1 MiB queue capacity and the rest to the per-IP
   (heap/40) and global (heap/10) reserves (`AbstractMessageHandler.java:411-426`); if that fails the connection is paused
   until capacity is released (`:639-647`, no starvation because the message is ≤ both reserves). The completed message is
   decoded by `BatchMessage.codec.decode` (`BatchMessage.java:56-75`): per statement an `MD5Digest` + `byte[16]` (`:68`) and a
   value list (`:71`, `CBUtil.readValueList` `:555-565`), and **per bound value a fresh `byte[len]` wrapped in a
   `HeapByteBuffer`** (`CBUtil.readBoundValue` `:466-481`, copy at `:480`). For a 1-byte value that is 4 + 1 bytes on the
   wire and ≈ 72 B of heap.
2. **Execute (NTR thread).** `BatchMessage.execute` (`:173-232`) builds one `QueryOptionsWrapper` per statement
   (`BatchQueryOptions.java:105-118`) and a new `BatchStatement` (`BatchMessage.java:227`); `BatchStatement.execute`
   (`BatchStatement.java:405-430`) calls `getMutations` (`:428` → `:270-324`), which builds every row of the batch
   (`BTreeRow`, `Clustering`, `LivenessInfo`, one `BufferCell` per value, referencing the decoded `ByteBuffer`) into
   `PartitionUpdate`s and checks `max_mutation_size` on the built mutation (`SingleTableUpdatesCollector.java:112`,
   `Mutation.java:169-176`).
3. **The batch check, after the build.** `executeWithoutConditions` (`:434-447`) calls `verifyBatchSize` (`:439`), which
   returns at once for one mutation (`:334`); for ≥ 2 mutations it compares `dataSize` with 50 KiB and throws
   `Batch too large` (`:352-358`) — after steps 1–2 have allocated everything.
4. **Apply.** For one mutation `mutateAtomic` is false (`:444`), so no batchlog; `StorageProxy.mutateWithTriggers` (`:445`)
   applies it locally (RF 1, one node): `CommitLog.add` (`CommitLog.java:304`, serialize to the thread's scratch buffer) and
   the memtable (`memtable_allocation_type: heap_buffers`, counted against `memtable_heap_space` = heap/4). The request
   thread waits for the write; the in-flight charge is released when the response is sent.

The decoded request (step 1) lives until the response; the built mutation (step 2) until the write completes. Neither is
charged anywhere except as the request's **wire** bytes in step 1. With n statements of m one-byte cells (plus `int` key and
clustering), wire ≈ 287 B per statement for m = 50 and the live heap ≈ 6–6.6 KB per statement (§2.4), so U/K ≈ 20×.

- **Direction (planned, by measurement §2.6):** **bypass — accounting mismatch** (U > C, K ≤ C) of the native-transport
  in-flight control, whose purpose is to bound request memory but whose counter is wire bytes; the shape is enabled by the
  documented single-partition exemption of `batch_size_fail_threshold` (an intentional exception, CASSANDRA-10876) and by the
  check's position after allocation (late enforcement for multi-partition batches, arm P). Interpretation to state at
  stage 2: accounting/configuration-sizing gap (heap/10 of wire bytes is sized as if requests held ≈ 1× their wire size).
- **Technique note:** [`bypass-playbook.md`](../../../bypass-playbook.md) (protected path vs suspect path, matched payload);
  the in-flight multiplicity follows [`combo-playbook.md`](../../../combo-playbook.md) only for the budget search.

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit |
|---|---|---|---|---|
| **Native request in flight** (claimed) | decoded `BatchMessage` (per value `byte[]` + `HeapByteBuffer`, per statement `MD5Digest`, value `ArrayList`; `BatchMessage.java:56-75`, `CBUtil.java:480`) and, on the NTR thread, the per-statement options and built `Mutation`/`PartitionUpdate` (rows, cells) → unreachable after the response (`BatchStatement.java:270-324`, `:445`) | per-connection queue (1 MiB) + per-IP and global reserve bytes = **wire body bytes** (`AbstractMessageHandler.java:411-426`; gauge `org.apache.cassandra.metrics:type=Client,name=RequestsSize`, `ClientMetrics.java:129`) | global `native_transport_max_request_data_in_flight` = heap/10, per IP heap/40 (`DatabaseDescriptor.java:649-656`); + 1 MiB per connection (`native_transport_receive_queue_capacity`, `Config.java:302`). Contract: bytes of request bodies, nothing about heap per byte | connection paused until capacity frees (`CQLMessageHandler.java:639-647`) |
| Per-batch size | the same built mutations | `IMutation.dataSize` (cell data) | `batch_size_fail_threshold` 50 KiB (`Config.java:331-332`); **documented to apply only to multi-partition batches** (yaml `:1843`, `BatchStatement.java:334`); checked after the build (`:428` → `:439`) | `InvalidRequestException("Batch too large")` + ERROR line; built objects become garbage |
| Request size | one message | body size | `native_transport_max_message_size` = min(`max_mutation_size` 16 MiB, heap/10, heap/40) (`DatabaseDescriptor.java:903-905`, `:3237-3244`) → 16 MiB at heap ≥ 640 MiB; frames 128 KiB | message discarded (too big) |
| Mutation size | built mutation | serialized size | `max_mutation_size` = ½ `commitlog_segment_size` 32 MiB = 16 MiB (`DatabaseDescriptor.java:898-899`) checked after the build (`SingleTableUpdatesCollector.java:112`) and at `CommitLog.add` (`:304`) | `MutationExceededMaxSizeException` |
| Statements per batch / values per statement | — | count | protocol `[short]` = 65,535 (`BatchMessage.java:59`, `CBUtil.java:557`) | protocol error |
| Executing requests | NTR pool | active tasks | `native_transport_max_threads` 128 (`Config.java:283`) | queued |
| Memtable | cloned cells (`heap_buffers`) | memtable pool bytes | `memtable_heap_space` = heap/4 (`DatabaseDescriptor.java:586-587`), flush at `memtable_cleanup_threshold` = 1/(1+2) (`:753-763`) | flush; writers block at the limit |
| Commit-log serialize scratch | `DataOutputBuffer.scratchBuffer` per writer | — | recycle cap only | direct memory; competing endpoint, not the claim |
| Heap budget | JVM heap | — | `-Xmx` 2 GiB (then 4, 8 GiB) | `OutOfMemoryError: Java heap space` → shipped `-XX:+HeapDumpOnOutOfMemoryError` + `OnOutOfMemoryError` kill |
| Direct budget | Netty frames, v5 large-message buffers, scratch | JMX `java.nio:type=BufferPool,name=direct` | `MaxDirectMemorySize` auto 15,872 MiB on this node | competing endpoint only |

Not on the path at defaults (checked): guardrails (default `AllowAllAuthenticator` ⇒ superuser, and no batch guardrail),
tracing (off), audit/FQL (off), `QueryEvents` listeners (none), slow-query monitor (reads only), rate limiting (off),
`native_transport_throw_on_overload` (client option, not set).

### 2.3 Configuration and budget audit

- **Build:** the existing `ms0604:/mydata/s4/cassandra-base` (Cassandra 5.0.9, `git describe` `cassandra-5.0.9`, `git status`
  clean, `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, built 2026-11-17 21:01 MST per `/mydata/s4/build-base.log`), **copied**
  to `/mydata/b14/cassandra` with `cp -a` (469 MB) so the run never touches the shared tree. No patch, no rebuild: the
  intervention is a configuration arm. Record `md5sum conf/cassandra.yaml` (shipped:
  `714ee9bf58b3bc1710377ac16bcbba03`), `conf/jvm11-server.options` (`fbad82a853f1b85aea0fa5ea34b6d1bf`),
  `conf/cassandra-env.sh` (`8be0588e87c594a03360751b1dbf4fbf`).
- **Configuration:** the shipped `conf/` unchanged for the test, control and protected-path arms (single node, `127.0.0.1`,
  `rpc_address: localhost`, data/commit log under the tree's `data/`, `heap_buffers`, `auto_snapshot` default). Every capacity
  constraint in §2.2 at its shipped default (V6): `batch_size_fail_threshold` 50 KiB, `batch_size_warn_threshold` 5 KiB,
  `native_transport_max_request_data_in_flight` heap/10, `…_per_ip` heap/40, `native_transport_receive_queue_capacity`
  1 MiB, `native_transport_max_message_size` derived (16 MiB), `max_mutation_size` derived (16 MiB),
  `commitlog_segment_size` 32 MiB, `native_transport_max_threads` 128, `memtable_heap_space` heap/4,
  `memtable_cleanup_threshold` derived (0.333), `write_request_timeout` 2 s, `native_transport_timeout` 12 s,
  `native_transport_rate_limiting_enabled` false, connection limits −1. **Intervention arm only:** a conf copy
  `/mydata/b14/conf-i` with one appended line `native_transport_max_request_data_in_flight: 16MiB` (capacity change in an
  intervention arm, allowed by V6).
- **Resolved at each heap** (`Runtime.maxMemory()` = `-Xmx` under G1; record from `system.log`'s config line and
  `jcmd VM.flags`): 2 GiB → global 214,748,364 B, per IP 53,687,091 B, memtable 512 MiB, max message 16,777,216 B;
  4 GiB → 429,496,729 / 107,374,182 / 1,024 MiB; 8 GiB → 858,993,459 / 214,748,364 / 2,048 MiB.
- **Environment settings (not capacity):** `MAX_HEAP_SIZE=<heap>` and `HEAP_NEWSIZE` unset (G1 ignores it), so
  `-Xms = -Xmx`; `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `ulimit -n 100000` in the launching shell (hard 1,048,576);
  `systemd-run --user --scope -p MemorySwapMax=0` (swap 0 for the measured process; **no `MemoryMax`**, no container budget);
  `sudo loginctl enable-linger jason92` at start (Linger is `no` now), `disable-linger` at the end. GC log: the shipped
  `cassandra-env.sh` Xlog to `logs/gc.log`. G1, `G1HeapRegionSize=16m` (`jvm11-server.options:63-66`), shipped
  `-XX:+HeapDumpOnOutOfMemoryError` (`jvm-server.options:120`) and `OnOutOfMemoryError` kill.
- **Node claimed (V7):** `ms0604` (Utah m400, **aarch64**, 8 cores, 65,791,808 kB RAM, 8 GiB swap present, Ubuntu 22.04,
  kernel 5.15, OpenJDK 11.0.33, Python 3.10.12; `/mydata` 39 GiB with 30 GiB free; no Cassandra or Java running; other
  folders `/mydata/s2r2`, `/mydata/u1r2`, `/mydata/s4/c5-w1` present and **not to be touched**; checked read-only
  2026-11-18 08:00–08:10 EST). `cassandra-env.sh` would resolve heap = 31,744 MiB (G1: `heap_limit` 31,744 < ½ RAM 32,124)
  and `MaxDirectMemorySize` = 15,872 MiB for this node; with a hand-set heap the direct limit stays 15,872 MiB
  (`cassandra-env.sh:62`, `:139-158`). **Budgets:** heap 2 GiB (ideal), then 4 and 8 GiB (upward search); all ≥ 512 MiB ⇒
  V7 met without per-case review (standing rule 2026-11-11). Direct: the auto 15,872 MiB. No container limit is a budget
  (no `MemoryMax`), so this design does not need an owner review. ARM: never pool these runs with x86 runs.

### 2.4 Ceiling arithmetic

**Payload T (test).** Table `b14.t (k int, c int, v00 … v49 tinyint, PRIMARY KEY (k, c))`; prepared
`INSERT INTO b14.t (k, c, v00, …, v49) VALUES (?, …, ?)` (52 markers). One `LOGGED` BATCH = n = 55,000 statements, all with
the same k (one partition), c = 0 … 54,999, each v = 1 byte.
- Wire per statement: kind 1 + id `[short bytes]` 18 + count 2 + k (4+4) + c (4+4) + 50 × (4+1) = **287 B**.
- Body = type 1 + n 2 + 55,000 × 287 + consistency 2 + flags `[int]` 4 = **15,785,009 B** (≤ 16,777,216 max message;
  ≤ 53,687,091 per IP at 2 GiB); 121 v5 segments of ≤ 131,071 B.
- Reserve charged per request = 15,785,009 − 1,048,576 (queue capacity) = **14,736,433 B**; max admitted concurrently at
  2 GiB: ⌊214,748,364 / 14,736,433⌋ = **14** (4 GiB: 29; 8 GiB: 58).
- Serialized mutation ≈ 55,000 × ≈ 115 B ≈ 6.3 MB < 16 MiB `max_mutation_size` ✓ (S0 confirms the write succeeds).
  `dataSize` ≈ 55,000 × ≈ 600 B ≈ 33 MB ≫ 50 KiB: a two-partition batch of the same rows is rejected (arm P).
- **Heap per request (estimate, compressed oops):** decoded per value `byte[1..4]` 24 B + `HeapByteBuffer` 48 B = 72 B × 52
  = 3,744 B; value `ArrayList` + `Object[52]` 248 B; `MD5Digest` + `byte[16]` 56 B; list slots 8 B ⇒ **≈ 4.06 KB/statement
  decoded**. Built: 50 × `BufferCell` 40 B + `BTreeRow` + cell `Object[]` ≈ 250 B + clustering/liveness ≈ 80 B + options
  wrapper and key list ≈ 100 B ⇒ **≈ 2.4 KB/statement built**. Total ≈ 6.0–6.6 KB/statement ⇒ **U_req ≈ 330–363 MB
  (315–346 MiB) per request = 21–23 × body**. Error band used for predictions: 15–25 × (U_req 236–394 MB).
- **Baseline** (idle 5.0.9 at 2 GiB on aarch64, B11/B12 on m400s): 240–400 MB live; memtable counted ≤ heap/4.

| Heap | C global / max admitted | N (connections) | Memtable ≤ | Demand if all admitted are held | Predicted endpoint |
|---|---|---|---|---|---|
| 2 GiB | 214.7 MB / 14 | 16 | 512 MiB | 14 × 236–394 MB = 3.3–5.5 GB | heap OOM once 4–6 requests are held (300 + ≤ 512 + n × 330 MB > 2,048 MiB ⇒ n ≥ 4.1 with a full memtable, ≥ 5.8 with an empty one): K ≈ 59–89 MB ≈ 0.28–0.41 C |
| 4 GiB | 429.5 MB / 29 | 32 | 1,024 MiB | 6.8–11.4 GB | OOM at 8–12 held |
| 8 GiB | 859.0 MB / 58 | 64 | 2,048 MiB | 13.7–22.9 GB | OOM at 16–25 held |
| 2 GiB, control C (blob payload, same body bytes) | 14 | 16 | 512 MiB | 14 × ≈ 16–32 MB (decode copy + slab clone) ≈ 0.22–0.45 GB | survive: ≤ 0.3 + 0.5 + 0.45 ≈ 1.3 GiB (≥ 35 % margin) |
| 2 GiB, intervention I (global in-flight 16 MiB) | ⌊16,777,216 / 14,736,433⌋ = 1 | 16 | 512 MiB | 1 × 236–394 MB | survive: ≤ 0.4 + 0.5 + 0.39 ≈ 1.3 GiB |

Σ contract capacities covering this memory: heap/10 + N MiB of **wire** bytes, plus memtable heap/4; the expansion
(≈ 20 × K) is covered by nothing. Since U ≈ 2.1 × heap at full admission for every heap (heap/10 × 21), the endpoint is
arithmetically reachable at 2, 4 and 8 GiB; the only limits on the search are client throughput and dump disk space.
Direct: v5 large messages and Netty frames ≈ 1–2.5 × K ≤ 2.2 GB at 8 GiB ≪ 15,872 MiB.

### 2.5 Workload and environment

- **Node:** `ms0604` only (victim and client on the same node; the client is outside the node's scope). Work dirs:
  `/mydata/b14/cassandra` (copied tree), `/mydata/b14/conf-i` (intervention conf), `/mydata/b14/runs/<run-id>/` (logs,
  monitors, dumps). Before anything: `ps -eo cmd | grep '[C]assandraDaemon'` and `ss -ltn | grep -E ':(7000|7199|9042) '`
  empty. Do not touch `/mydata/s2r2`, `/mydata/u1r2`, `/mydata/s4/c5-w1`, `/mydata/s4/cassandra-base` (read only, copy from).
- **Harness** (`harness/` in this folder, synced to `/mydata/b14/harness/`; stdlib Python 3 except the segment codec):
  - `client.py` — raw CQL **protocol v5** client. Adapt B11's v4 client
    (`../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/client.py`: socket binding, STARTUP, frame I/O).
    v5 specifics: STARTUP (`{"CQL_VERSION":"3.0.0"}`) and its READY are **unframed** v5 envelopes (header
    `0x05, flags 0, stream int16, opcode, length int32`); every later envelope is wrapped in v5 segments using the bundled
    driver's codec (`sys.path.insert(0, '<tree>/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0')`,
    `from cassandra.segment import SegmentCodec`; `SegmentCodec().encode(io.BytesIO, envelope)` splits into ≤ 131,071-byte
    segments with CRC24/CRC32); responses are read by parsing segment headers (3-byte LE header + CRC24, payload length =
    low 17 bits, payload + CRC32) and reassembling envelopes. PREPARE body (v5): `[long string] query` + `[int] flags 0`;
    RESULT kind 4 gives `[short bytes] id` (then `result_metadata_id`, ignored). BATCH (opcode `0x0D`) body: type `0x00`
    (LOGGED), `[short] n`, per statement `0x01` + `[short bytes] id` + `[short] count` + values `[int len][bytes]`, then
    consistency `0x0001` (ONE), flags `[int] 0`.
  - Connection i binds its socket to source address `127.1.(i // 250).(1 + i % 250)` before `connect(('127.0.0.1', 9042))`,
    so every connection is its own IP (per-IP limit never binds; the global limit and the server's pause enforce K ≤ C).
  - Per connection: STARTUP → PREPARE → closed loop, **one batch outstanding per connection**: build/patch, send, wait for
    the response, repeat. The batch body is built **once per process** into a template; per request the connection's copy
    (`bytearray`) gets its partition key written at every statement's k offset (`struct.pack_into('>i', buf, off, k)`,
    k = 1,000,000 × (i+1) + request seq, so every request writes a new partition), then is segment-encoded and sent with
    `sendall`. Arms (`--arm`):
    - **`T` test:** payload T of §2.4 (55,000 statements × 52 values, body 15,785,009 B).
    - **`C` control (matched payload, same path):** table `b14.big (k int, c int, v blob, PRIMARY KEY (k, c))`, prepared
      `INSERT INTO b14.big (k, c, v) VALUES (?, ?, ?)`, LOGGED BATCH of 64 statements, one partition, c = 0 … 63, each v a
      blob of 246,599 B (`(bytes(range(256)) * 964)[:246599]`, compressible so sstables stay small); body =
      3 + 64 × 246,640 + 6 = **15,784,969 B** (40 B less than T; same reserve charge within 0.0003 %).
    - **`P` protected path (diagnostic):** payload T with statements 0 … 27,499 on key k and 27,500 … 54,999 on key k+1
      (two mutations, same bytes): built, then rejected by `batch_size_fail_threshold` (`Batch too large`, ERROR line each).
  - Processes: `--procs ⌈N/8⌉`, ≤ 8 connections per process (threads, blocking sockets). The per-request Python work
    (55,000 `pack_into` + CRC32 over 15.8 MB) is ≈ 0.1 s; record client CPU (`ps -o pcpu`) in every arm.
  - Logs: `completions.txt` (`t_ms conn latency_ms status`; status `VOID`, or the ERROR code and first 120 chars), and a
    per-second line per process (`t_ms open established outstanding completed errors K_client`), K_client =
    outstanding × body (upper bound of the server's charge).
  - `--ddl` creates keyspace `b14` (`SimpleStrategy`, RF 1) and both tables (`IF NOT EXISTS`) over a v5 QUERY.
  - `--check k` prints `SELECT count(*) FROM b14.t WHERE k = <k>` (S0 only).
  - `run.sh <run-id> <conf: base|i> <heap> <arm> <N> <hold-s>`: preflight (no daemon, ports free, `df -BG /mydata` avail
    ≥ heap + 8 GiB) → wipe `/mydata/b14/cassandra/{data,logs}` → start
    `( ulimit -n 100000; [CASSANDRA_CONF=/mydata/b14/conf-i] MAX_HEAP_SIZE=<heap> CASSANDRA_HEAPDUMP_DIR=<run dir>
    systemd-run --user --scope -p MemorySwapMax=0 --unit=b14-<run-id> -- /mydata/b14/cassandra/bin/cassandra -f
    > <run dir>/stdout.txt 2>&1 < /dev/null & )` (launched with `setsid nohup`, polled, never a foreground sleep) → wait
    for `Starting listening for CQL clients` (≤ 300 s) → `jcmd <pid> VM.flags`, grep the config line for the resolved
    in-flight values → `--ddl` → 20 s idle with monitors running (baseline) → client → stop at the endpoint (daemon gone +
    `java.lang.OutOfMemoryError` in `stdout.txt`) or after `<hold-s>` → stop the client, `kill <pid>` (`-9` after 60 s),
    wait for the scope to end → copy `system.log`, `gc.log*`, stdout, client and monitor logs into the run dir →
    `summarize.py`. Disk guard during load: if `df /mydata` avail < 6 GiB, stop the client and record it as a deviation.
  - `monitor.sh`, `summarize.py`: §2.6. Dump tools: copy `hprof-histo.py` from
    `../native_transport_receive_queue_capacity--refused-v5-request-uncharged-drift/harness/` (class histogram of all
    records) and `hprof_oome_thread.py` from `../ExecuteMessage_literal_1000--traced-render-outside-inflight/harness/`.
- **Arms and order** (all at shipped defaults unless stated; one run at a time on `ms0604`):

| Run | Conf | Heap | Arm | N | Hold | Purpose |
|---|---|---|---|---|---|---|
| `S0` shakedown | base | 2 GiB | T | 1 | 60 s | reachability, not a reading: responses `VOID`; `--check` = 55,000 rows for a completed k; no `Batch too large`, no `MutationExceededMaxSize`; `RequestsSize` readable and ≈ 14.7 MB while the request is in flight; old-gen after GC rises by ≈ U_req during a request (instrument check) |
| `T2-1..3` test | base | 2 GiB | T | 16 | ≤ 180 s | V1 at 2 GiB |
| `C2-1..3` control | base | 2 GiB | C | 16 | 150 s | V2 (matched wire bytes, same single-partition path, low expansion) |
| `I2-1..3` intervention | conf-i | 2 GiB | T | 16 | 150 s | V4 (in-flight bound sized to the expansion: one request held) |
| `T4-1` (→ `-2`, `-3` if time) | base | 4 GiB | T | 32 | ≤ 240 s | budget search |
| `P2-1` | base | 2 GiB | P | 16 | ≤ 180 s | diagnostic: does the batch check, where it applies, protect the heap? |
| `T8-1` (→ `-2`, `-3` if time) | base | 8 GiB | T | 64 | ≤ 240 s | budget search |

  Order of execution: `S0`, `T2-1`, `C2-1`, `I2-1`, `T2-2`, `C2-2`, `I2-2`, `T2-3`, `C2-3`, `I2-3`, `T4-1`, `P2-1`,
  `T8-1`, then repeats of the largest failing budget as time allows. If `T4-1` survives, skip `T8-1` (largest failing budget
  2 GiB). If `T8-1` fails and time allows, repeat it before anything else.
- **Time plan (America/New_York; node clock is MST = ET − 2 h).** Stage 2 assumed to start ≈ 08:45. Harness + copy +
  shakedown `S0`: 08:45–09:30. Each run ≈ 5–6 min (start ≈ 60–90 s on the m400, 20 s baseline, load ≤ 150–240 s,
  teardown and copy ≈ 60 s): nine V-runs 09:30–10:25; `T4-1` 10:25–10:32; `P2-1` 10:32–10:38; `T8-1` 10:38–10:46.
  **Hard limits:** no run starts after 10:40 (a run that cannot finish by 10:50 is skipped); every process stopped and the
  node checked empty by 10:55; dump analysis that does not fit is skipped (record which). If behind schedule, drop in this
  order: `T8-1`, `P2-1`, `T4-1`; never drop a V-run for a budget-search run.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Heap occupancy (U side) | `logs/gc.log` (shipped Xlog): per GC heap before → after, `Old`/`Humongous` regions, `Pause Full`, `To-space exhausted`; `jcmd <pid> GC.heap_info` (no forced GC) | every GC; 3 s | live heap after each GC; U_req(t) = old-after-GC − baseline (idle 20 s) − memtable heap |
| Memtable heap | `nodetool sjk mx -b org.apache.cassandra.metrics:type=Table,keyspace=b14,scope=t,name=AllMemtablesHeapSize -f Value --get` (`scope=big` in arm C) | 10 s | memtable share, subtracted from U |
| K (server) | `nodetool sjk mx -b org.apache.cassandra.metrics:type=Client,name=RequestsSize -f Value --get`; `…name=PausedConnections` | 10 s | global reserve bytes (≤ C by construction), paused connections |
| K (client) | client per-second lines | 1 s | outstanding × body |
| Held requests (actual concurrency) | `jcmd <pid> Thread.print`: count NTR threads with a `BatchMessage.execute` frame (and of those in `getMutations`/`addUpdates`, in `StorageProxy`/`AbstractWriteResponseHandler.get`, in `CommitLog.add`, in `Memtable.put`), and event-loop threads in `BatchMessage$1.decode`; `MutationStage` pending via `sjk mx … type=ThreadPools,path=request,scope=MutationStage,name=PendingTasks` | 10 s | n_held(t); local-write backlog (if > 0 with write timeouts, label the backlog, see O5) |
| Direct memory | `sjk mx -b java.nio:type=BufferPool,name=direct -f MemoryUsed --get` | 10 s | competing direct endpoint watch |
| Process | `RssAnon` from `/proc/<pid>/status`; client `ps -o pcpu,rss` | 3 s | native growth; client CPU |
| Throughput | `completions.txt` | per request | completed batches, errors by kind (WriteTimeout `0x1100`, Overloaded `0x1001`, Invalid `0x2200` "Batch too large"), latency — an intervention that stops useful work is not protection |
| Endpoint | `stdout.txt`: first `java.lang.OutOfMemoryError` line, `Dumping heap to …`, `OnOutOfMemoryError` kill; `system.log` ERROR lines with thread names; process exit | at end | endpoint type and initiating thread |
| Holder at failure (V5) | the shipped heap dump: `hprof_oome_thread.py` (OOME thread stack) and `hprof-histo.py --top 30 --value-len 1`: counts and shallow bytes of `java.nio.HeapByteBuffer`, `byte[]` of length 1 (the tinyint values), `org.apache.cassandra.db.rows.BufferCell`, `…rows.BTreeRow`, `…utils.MD5Digest`, `…transport.messages.BatchMessage`, `…db.Mutation`, `…cql3.BatchQueryOptions$WithPerStatementVariables$1`, `java.util.ArrayList`, `Object[]` | first failing run per budget (full); every failing run: OOME thread at least | batch-request share of the heap; `BatchMessage` count = requests held (compare with 14 = C in requests) |
| Disk | `df -BM /mydata` | 10 s | disk guard |

`monitor.sh` runs the same samplers in every arm (matched instrumentation); no forced GC, no live histogram during load.
`summarize.py` writes `summary.txt` per run: endpoint and time to it after the last connection established, max
n_held, max K_server and K_client, K_server at the last sample before the endpoint, max old-after-GC, U_req/K estimate at
the last two samples, memtable heap max, completions/errors by kind, max direct and RssAnon, GC STW share over the last
60 s (service-loss criterion), client CPU, and the dump findings. Dumps: analyze, record size + sha256 + findings in the run
dir, then delete the `.hprof` (keep at most one on disk); a 4/8 GiB dump is analyzed only if the time plan allows.

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted (before readings):**
- `S0`: one request at a time completes (`VOID`, latency ≈ 1–4 s on the m400); old-gen after GC during a request rises by
  ≈ 250–400 MB above baseline; K_server ≈ 14.7 MB while in flight.
- `T2-*`: heap OOM (`OutOfMemoryError: Java heap space`) within 120 s of the last connection, **3/3**, with n_held 4–8 at the
  last sample and K_server ≤ 14 × 14.7 MB (≤ C); U_req/K_server between 10 and 30; the dump shows `BatchMessage` instances
  ≥ 3 and the batch-request classes (HeapByteBuffer + `byte[1]` + BufferCell + BTreeRow + MD5Digest + their lists) ≥ 50 %
  of the dump's shallow bytes; memtable ≤ 512 MiB. Initiating thread: an NTR thread in the batch execute path or an event
  loop in `BatchMessage$1.decode` (either is in the claimed holder's path).
- `C2-*`: survive 150 s 0/3 OOM, old-after-GC peak ≤ 1.4 GiB (≤ 70 % of heap), batches completing; GC STW share < 90 %.
- `I2-*`: survive 150 s 0/3, n_held ≤ 1, completions > 0 (≥ 1 batch per 10 s), PausedConnections > 0.
- `T4-1`: OOM (n_held 8–12); `T8-1`: OOM (n_held 16–25), if the client sustains N.
- `P2-1`: OOM likely (the decode and build precede the check; residence shorter, so possibly needs more held requests) or a
  survive with `Batch too large` for every batch; either is recorded as a diagnostic reading.

| Row | Observation | Reading |
|---|---|---|
| O1 | T2 OOM ≥ 3/3 (V1), C2 0/3 (V2), I2 0/3 with completions (V4), U measured from GC log and dump (V3), dump/OOME thread show the batch-request holder ≥ 50 % (V5), defaults (V6), 2 GiB heap (V7) | **true positive**: `verified-OOM · deployment`, bypass by accounting mismatch of the in-flight control (shape enabled by the documented single-partition exemption) |
| O2 | T2 ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM event by the hold end | `verified-gap · service-loss` at best → **retry** (raise hold or N within C) |
| O3 | T2 OOM but the batch-request classes < 50 % of the heap at failure, or the largest holder is something else (memtable over its count, commit-log scratch, another queue) | attribution fails → **retry** (name the holder) |
| O4 | T2 survives 0/3 with n_held at the admitted maximum (14) and U_req/K < 5 | expansion estimate wrong; if 14 × measured U_req + baseline + memtable < 2 GiB and the same holds at 4 GiB, **false positive**; else **retry** |
| O5 | T2 OOM, but write timeouts precede it and MutationStage pending > 0 or `BatchMessage`/`Mutation` count in the dump > 14 | held requests exceed K's admission (local-write backlog, S2-like) → classify **mixed**; true positive only if V5 still shows the batch holder ≥ 50 % and n_held ≤ 14 at the last sample, else **retry** |
| O6 | C2 OOM (≥ 1/3) | the expansion is not the cause (or the baseline/memtable is) → **retry** |
| O7 | I2 OOM (≥ 1/3), or I2 completes no batch | intervention fails / stops useful work → V4 unmet → `(no intervention)` cannot be claimed; **retry** |
| O8 | direct-buffer OOM or kernel kill first | competing endpoint → record; **retry** |
| O9 | batches rejected (`Batch too large` in T/C, `MutationExceededMaxSize`, protocol errors), node fails to start, or client cannot hold N connections | invalid run: fix the harness before readings (shakedown) or record as invalid |

**Stopping budget:** per run as in §2.5 (hold ≤ 150–240 s after the last connection, plus start/stop); no escalation after
an OOM (one endpoint per run); the whole stage within the time plan (§2.5); N never above the arm's table value (above the
admitted maximum it only adds paused connections).

### 2.8 Controls and intervention

- **Matched control (V2), 3 runs:** arm C — the same path (prepared LOGGED BATCH, one partition, exempt from the batch
  check), same body bytes (15,784,969 vs 15,785,009), same N, heap, build, conf and instruments; only the payload shape
  differs (64 large values instead of 2.86 M one-byte values), so the in-flight charge K is the same and U/K ≈ 1–2 instead
  of ≈ 20. Survival shows the endpoint needs the expansion, not the wire volume, memtable or commit log.
- **Causal intervention (V4), 3 runs:** arm I — the shipped build and payload T with `native_transport_max_request_data_in_flight:
  16MiB` (heap/128 instead of heap/10): the in-flight control admits ⌊16,777,216 / 14,736,433⌋ = 1 request at a time, i.e.
  the limit expressed in what the heap can hold at the measured expansion. Survival with batches still completing (record
  rate) shows the OOM is caused by the number of concurrently held batch requests that the wire-byte count admits. No
  diagnostic patch is needed; if one is wanted later (charging an expansion-aware estimate at admission), it is a separate
  build and a dated amendment.
- **Protected-path reading (diagnostic, 1 run):** arm P tests the second half of OC-11 ("the whole batch is on the heap
  before the check"); its result says whether `batch_size_fail_threshold`, where it applies, bounds this memory.
- **Low multiplicity:** `S0` (N = 1) doubles as the component-alone reading (one request's U_req).
- **V-table plan:** V1 `T2-1..3`; V2 `C2-1..3`; V3 U from GC log + dump vs `RequestsSize`; V4 `I2-1..3`; V5 `T2-1` dump +
  OOME threads of `T2-1..3`; V6 §2.3 (shipped yaml md5, resolved values from `system.log`); V7 2 GiB heap, auto direct, no
  container limit; largest failing budget from `T4-*`/`T8-*` with n/N.

`sha256 of §1–§2 at freeze: 99b624dc67ca61ca6d6dfbd9c7684c28483de9b07140ccc9d37afea8b27d504b` · computed over the lines from `## 1. Candidate` through the line before this one (`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`), frozen 2026-11-18 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session (workflow), 2026-11-18 08:14–09:40 America/New_York. Freeze hash re-computed at
start with the §2 command: `99b624dc…d27504b` — **matches**.

### 3.1 Amendments (dated, with reasons; all recorded before the reading they affect)

- **A1 (2026-11-18 08:15 ET, before any run) — work directory.** The stage-2 task assigned the fresh directory
  `/mydata/s4/b14-w3` on `ms0604`; every `/mydata/b14/…` path of §2.3/§2.5 is `/mydata/s4/b14-w3/…` (tree
  `cassandra/`, `conf-i/`, `harness/`, `runs/<run-id>/`). `cp -a` of `/mydata/s4/cassandra-base` (469 MB, `diff -rq` empty,
  `git describe --tags` = `cassandra-5.0.9`). Environment only.
- **A2 (08:16, before any run) — linger.** `sudo loginctl enable-linger` was refused by this session's permission system,
  so Linger stays `no`. Instead every run is driven from one `ssh` session that stays open for the whole series, so the
  user manager (and the `systemd-run --user --scope` units) live for the run; the daemon itself is still started with
  `setsid nohup`. Environment only; no measured value changes.
- **A3 (08:20, before any run) — instruments.** (a) The JMX gauges of §2.6 (RequestsSize, PausedConnections,
  AllMemtablesHeapSize for `t` and `big`, MutationStage PendingTasks, NTR Active/PendingTasks, direct `MemoryUsed`, heap
  used) are read by one long-lived `Jmx.java poll` JVM (copied from B10's harness) **every 5 s** instead of one
  `nodetool sjk mx` JVM per bean every 10 s: same beans, one JVM instead of ~5 per 10 s on an 8-core m400, denser sampling.
  (b) The v5 segment codec is re-implemented in `client.py` with the bundled driver's algorithm and constants
  (`cassandra/segment.py` of `cassandra-driver-internal-only-3.29.0.zip`: CRC24 init `0x875060` poly `0x1974F0B`, CRC32
  initial `crc32(fa 2d 55 ca)`, ≤ 131,071-byte payloads) instead of importing the driver package; the server accepted
  every segment (no CRC errors). Body sizes checked offline: T 15,785,009 B, C 15,784,969 B, P 15,785,009 B, 121 segments
  each — exactly §2.4. (c) The shipped `system.log` config line prints the derived in-flight values as `null`; the resolved
  values are read from JMX `StorageService` (`NativeTransportMaxConcurrentRequestsInBytes[PerIp]`).
- **A4 (2026-11-18 08:24 ET, after S0, before any T2/C2/I2 reading) — every T batch ends in a WriteTimeout on this node.**
  S0 (N = 1) got 9/9 responses `0x1100 Operation timed out - received only 0 responses` after 5.2–6.9 s; no VOID; memtable
  of `b14.t` ≤ 3 MiB, i.e. the local mutation is dropped as expired before it is applied. Thread samples put the single NTR
  thread in `getMutations` (the build) in 6/9 samples: building 55,000 rows × 50 cells on the m400 with one request
  already driving the 2 GiB heap into Full GCs takes longer than the shipped `write_request_timeout` 2 s. The design is
  **kept as frozen** (no timeout raised, so V6 and the deployment label are not touched). Consequences recorded before
  readings: (i) §2.1 step 4 (apply) does not happen for T/I payloads at defaults on this node; the claimed holder
  (decoded request + built mutation, steps 1–2) is still allocated in full and held until the timeout response, ≈ 6 s
  per request; the in-flight charge is held for the same time; (ii) the S0 check "`--check` = 55,000 rows" cannot be
  made (nothing is written); (iii) **for the throughput criteria of S0 and arm I, a "completion" is a server response
  (VOID or WriteTimeout)**, because at N = 1 with no contention no T batch is ever written on this node, so data-write
  throughput is 0 in every T-payload arm independently of the intervention; I-arm useful work is compared as response
  rate against S0 (N = 1). Arm C (64 large values, fast build) is expected to write (VOID) and so carries a memtable
  that T does not — a harsher control, not a weaker one. Recorded as a limit in §4.
- **A5 (08:24, after S0) — S0 GC reading, U_req at N = 1 larger than predicted.** Not a design change; recorded so the
  2 GiB predictions are read against it: baseline heap after GC 33 MiB before load; with one request in flight the 8
  Full GCs left 649–893 MiB (median ≈ 750 MiB), i.e. one held request ≈ 0.6–0.86 GiB ≈ 40–57 × its 15.8 MB body,
  above the §2.4 band (15–25 ×). STW share over the last 60 s 36 % (below the service-loss criterion). The run survived
  (N = 1 alone is below the endpoint).
- **A6 (09:16 ET, after T8-1) — repeats of T8.** T8-1 failed, so per §2.5 T8-2 and T8-3 were run next (time allowed).
  A first launch of them aborted in preflight at 07:16:25 MST because `pgrep -f CassandraDaemon` matched the launching
  `ssh` command line itself (which contained that word); no daemon was running; the two empty run dirs were removed and
  the pair relaunched at 07:16:49 MST (log `runs/series-list-t8.aborted-preflight.log`). No reading affected.
- **Harness note (not a design change).** `C2-2` was the only arm-C dump histogrammed (flag set on the list at 08:32 ET,
  after C2-1 failed and before C2-2 started) to name the control's holder; per §2.6 the full histogram was planned for the
  first failing T run per budget (done for T2-1; the 4 and 8 GiB dumps were analysed for the OOME thread only, the time
  plan did not include their histograms). When a run reaches its hold end while the OOM heap dump is still being written
  (T8-1, T8-2), `run.sh` sends SIGTERM and after 60 s SIGKILL: T8-2's dump was cut at 7,615 MiB (no "Heap dump file
  created" line); its OOME line and OOME-thread trace (written at the start of the dump) are intact.

### 3.2 Environment (as run)

`ms0604` (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, swap 8 GiB present, Ubuntu 22.04.1, kernel
5.15.0-191-generic), OpenJDK 11.0.33, Python 3.10.12. Tree `/mydata/s4/b14-w3/cassandra` (copy of the 5.0.9 build, `git
describe --tags` `cassandra-5.0.9`). `md5sum` per run (`runs/<id>/conf-md5.txt`): `conf/cassandra.yaml`
`714ee9bf58b3bc1710377ac16bcbba03` (shipped), `jvm11-server.options` `fbad82a853f1b85aea0fa5ea34b6d1bf`,
`cassandra-env.sh` `8be0588e87c594a03360751b1dbf4fbf`; intervention `conf-i/cassandra.yaml`
`0149f45cd4eed69d0be60403bf08a055` (= shipped + `native_transport_max_request_data_in_flight: 16MiB`). JVM (from
`jcmd VM.flags` / the `JVM Arguments` line): G1, `G1HeapRegionSize` 16 MiB, `-Xms = -Xmx` = 2/4/8 GiB,
**`MaxDirectMemorySize` = 16,642,998,272 B (15,872 MiB, auto)**, shipped `HeapDumpOnOutOfMemoryError` and
`OnOutOfMemoryError=kill -9 %p`; open files 100,000; scope `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`).
Resolved at 2 GiB (JMX `StorageService`): global in-flight 214,748,364 B, per IP 53,687,091 B (= §2.3). At 4 and 8 GiB
not read directly; the server counter stopped at exactly 29 × and 58 × 14,736,433 B (427,356,557 and 854,713,114 B),
consistent with heap/10 = 429,496,729 and 858,993,459 B. Every capacity in §2.2 at its shipped default in all T, C, P
runs (V6); arm I only differs by the one line. Harness: `harness/` (`client.py` v5 client, `run.sh`, `series.sh`,
`monitor.sh`, `Jmx.java`, `threadcount.py`, `summarize.py`, `excerpt.sh`, dump tools `hprof-histo.py` (want-list changed)
and `hprof_oome_thread.py`, run lists `list-main.txt`, `list-t8.txt`). Full logs: `ms0604:/mydata/s4/b14-w3/runs/<run-id>/`
(`stdout.txt`, `system.log`, `gc.log*`, `jmx.csv`, `threads.txt`, `heapinfo.txt`, `completions-p*.txt`, `client-p*.txt`,
`summary.txt`, `oome-thread.txt`, `histo.txt`, `dump.txt`); excerpts: `logs/<run-id>.txt`. All dumps were deleted after
analysis (size and sha256 in `dump.txt`).

### 3.3 Runs

Times: "t_OOM" = (daemon exit − dump duration) − last connection established, ±2 s. "K" = server `RequestsSize`
(5-s JMX samples; under Full-GC thrash the JMX poller stops answering, so the last good sample can precede the endpoint).
"held" = threads with `BatchMessage.execute` on NTR / threads in `BatchMessage$1.decode` (event loops), max over 10-s
`Thread.print` samples. Full-GC "after" = heap after each `Pause Full`. Responses = server answers to the client
(VOID or error).

| Run | Heap / arm / N | Endpoint | t_OOM | K max (B) | held NTR / decode | Full GCs (after-GC, MiB) | Responses in run | OOME-initiating thread (top Cassandra frames) |
|---|---|---|---|---|---|---|---|---|
| S0 | 2 G / T / 1 | survive 60 s | — | 14,736,433 | 1 / 0 | 8 (649–893); baseline 33 | 9 WriteTimeout (5.2–6.9 s), 0 VOID | — |
| T2-1 | 2 G / T / 16 | **heap OOM** | +56 s | 206,310,062 (= 14 × 14,736,433) | 1 / **14** | 27 (1361 → 2041 ×20) | 0 (16 resets at exit) | epoll event loop: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71` ← `CQLMessageHandler$LargeMessage.onComplete` |
| C2-1 | 2 G / C / 16 | **heap OOM** | +56 s | 207,358,078 | 14 (all waiting for the write) / 1 | 46 (866 → 2026) | 93 VOID + 289 WriteTimeout; MutationStage pending ≤ 39; memtable `big` ≤ 90 MiB; direct ≤ 822 MiB | event loop: `CBUtil.readRawBytes:669` ← `readBoundValue:480` ← `BatchMessage$1.decode:71` |
| I2-1 | 2 G / T / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 (1 request) | 1 / 0 | 22 (631–978) | 23 WriteTimeout (1.5 / 10 s), 0 VOID | — |
| T2-2 | 2 G / T / 16 | **heap OOM** | +33 s | 206,310,062 | 0 / **14** | 41 (1375 → 2047 ×36) | 0 | event loop: `ArrayList.<init>` ← `CBUtil.readValueList:561` ← `BatchMessage$1.decode:71` |
| C2-2 | 2 G / C / 16 | **heap OOM** | +99 s | 206,309,502 | 14 (waiting) / 0 | > 100 at 2017 (STW > 90 % over the last 60 s) | 104 VOID + 332 WriteTimeout; MutationStage pending ≤ 50; memtable ≤ 121 MiB; MUTATION_REQ dropped 25–32 / 5 s (mean 4.3–4.6 s) | compaction thread: `ByteArrayAccessor.read` ← `Cell$Serializer.deserialize` ← … ← `SSTableRewriter.append` |
| I2-2 | 2 G / T / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 | 1 / 1 | 23 | 24 WriteTimeout (1.6 / 10 s) | — |
| T2-3 | 2 G / T / 16 | **heap OOM** | +24 s | 44,209,299 (last answered sample) | 0 / **14** | 32 (→ 2040) | 0 | event loop: `CBUtil.readRawBytes:669` ← `readBoundValue:480` ← `BatchMessage$1.decode:71` |
| C2-3 | 2 G / C / 16 | **heap OOM** | +58 s | 206,309,502 | 14 (waiting) / 1 | 33 (→ 2020) | 89 VOID + 303 WriteTimeout; pending ≤ 40; memtable ≤ 151 MiB | event loop: `CBUtil.readRawBytes:669` ← `readBoundValue:480` ← `BatchMessage$1.decode` |
| I2-3 | 2 G / T / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 | 1 / 1 | 23 | 23 WriteTimeout (1.5 / 10 s) | — |
| T4-1 | 4 G / T / 32 | **heap OOM** | +71 s | 427,356,557 (= 29 ×) | 15 / **16** | 26 (→ 4089) | 0 | event loop: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `BatchMessage$1.decode` |
| P2-1 | 2 G / P (2 partitions) / 16 | **heap OOM** | +26 s | 206,310,062 | 0 / **14** | 27 (→ 2039) | 0; **0 `Batch too large`** in `system.log` | event loop: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `BatchMessage$1.decode` |
| T8-1 | 8 G / T / 64 | **heap OOM** | +62 s | 854,713,114 (= 58 ×) | 20 / 14 | 7 (6886 → 8118; 6.6–7.4 s each), STW 96 % last 60 s | 0 | **NTR**: `Arrays.copyOf` ← `BTree$Builder.add` ← `RegularAndStaticColumns$Builder.addAll` (mutation build) |
| T8-2 | 8 G / T / 64 | **heap OOM** | +166 s (Full GCs from +23 s; STW 96 % over the 60 s before the OOM) | 854,713,114 | 22 / 14 | 20 (→ 8189) | 0 | NTR: `Arrays.copyOf` ← `BTree$Builder.add` ← `RegularAndStaticColumns$Builder.addAll` |
| T8-3 | 8 G / T / 64 | **GC service loss** in the hold (STW 96 % over the last 60 s, heap 8,178 MiB after every GC from +23 s); heap OOM **30 s after** the hold-end SIGTERM (not counted as the endpoint) | (OOM at +272 s, after hold end +240 s) | 854,713,114 | 27 / 14 | 35 (8178 throughout) | 0 | dump trigger: RMI/JMX connection thread (`TCPTransport.handleMessages`, the monitor's poller); first `system.log` ERROR: epoll event loop, `CBUtil.readBoundValue:480` ← `BatchMessage$1.decode:71` |

T8 timing from the GC log and the dump line (T8-1: OOM ≈ 07:11:13 MST = +65 s, dump 180 s, completed; T8-2: last GC
07:20:52 = +166 s, then the dump until the 07:23:08 SIGKILL; T8-3: Full GCs 07:26:19–07:30:28, hold end and SIGTERM
07:29:58, first OOME 07:30:28). STW shares are recomputed with each GC id counted once across the rotated `gc.log*`
files (`summarize.py` adds rotated files twice, so its "STW share" line over-reads for runs with rotation, e.g. 241 %).

Dumps (size, sha256 prefix; all deleted after analysis): T2-1 2,598,090,113 `93fb95e1`; T2-2 2,605,087,864 `6526c112`;
T2-3 2,242,369,049 `e65329a3`; C2-1 2,136,759,979 `effd8309`; C2-2 2,145,482,535 `9c69f1e8`; C2-3 2,142,482,295
`4e1e4a5b`; T4-1 5,302,729,611 `68ba18d2`; P2-1 2,494,356,238 `c2243746`; T8-1 10,486,520,804 `1ab4abbf`; T8-2 7,985,507,717
`08e9ac98` (cut by the SIGKILL, see note); T8-3 1,689,170,437 `a14d3219` (cut likewise; its OOME was after the hold end).

**Holder at failure, T2-1 dump** (`hprof-histo.py`, every record; shallow sizes estimated with the dump's 8-byte ids, so
they overstate a compressed-oops heap by ≈ 10–15 %): 56,218,033 objects, 2,271,521,104 B. `java.nio.HeapByteBuffer`
26,769,155 / 1,472,303,525 B; `byte[]` 27,374,650 / 490,799,434 B, of which **`byte[1]` 25,739,212** / 437,566,604 B (the
tinyint values); `Object[]` 528,215 / 242,665,856 B (value lists); `ArrayList` 517,092 / 16,546,944 B; **`MD5Digest`
514,813** / 14,414,764 B; `BatchMessage` 1; **`Envelope` 14**; `BufferCell` 34, `BTreeRow` 8. The decoded-request classes
sum to 2,236,700,523 B = **98.5 %** of the dump. 14 envelopes = the 14 requests the global limit admits; 514,813 statement
digests = 9.4 requests' worth of the 55,000 statements, i.e. all 14 admitted requests were part-way through decode.
U (heap after the last Full GCs 2,041 MiB − 33 MiB baseline ≈ 2,106 MB) / K (206,310,062 B) ≈ **10.2** (shallow-dump
estimate 10.8).

**Holder at failure, C2-2 dump (control):** 720,967 objects, 2,127,429,497 B; **`byte[]` 108,203 / 2,071,421,478 B (97.4 %)**
— the 246,599-byte blobs, ≈ 8,400 of them ≈ 131 batches' worth; **`Mutation` 92, `PartitionUpdate` 92**, `BatchMessage` 8,
`Envelope` 8, `MD5Digest` 542, `HeapByteBuffer` 18,089, `byte[1]` 336. 92 built mutations are alive against 14 requests the
in-flight limit admits: the requests whose writes timed out (2 s) were answered and their charge released while their
mutations were still queued on the local MutationStage (pending ≤ 50, MUTATION_REQ drops at ≈ 4.4 s latency). The
control's endpoint is a **local-write backlog outside the in-flight count**, not the decode expansion.

**Readings against the §2.7 predictions.**
- `S0`: K ≈ 14.7 MB ✓; old-gen after GC during a request rose by 616–860 MiB (predicted 250–400 MB; A5); responses are
  WriteTimeouts, not VOID (A4).
- `T2-*`: heap OOM **3/3** ✓, K ≤ C ✓ — but K was **at** the cap (14/14 requests admitted, 0.96 C), not at 0.28–0.41 C, and
  the held requests were on the **event loops in decode** (14 threads in `BatchMessage$1.decode`), not 4–8 on NTR threads:
  on the m400 one request's decode of 2.86 M values takes longer than the time to admit all 14, so all 14 are decoded
  concurrently and the heap fills with **decoded** values (10 × K) before any reaches `execute`. OOME thread in the claimed
  holder's path 3/3 (`CBUtil.readBoundValue:480` / `readValueList:561-563` under `BatchMessage$1.decode:71`); dump
  holder 98.5 % ≥ 50 % ✓; memtable 0 ✓.
- `C2-*`: predicted survive 0/3 — **observed OOM 3/3** (row **O6**). Holder (C2-2 dump): built blob mutations of
  timed-out writes, 92 alive vs 14 admitted.
- `I2-*`: survive **0/3 OOM** ✓, n_held ≤ 1 ✓, responses 23–24 per 150 s ✓ (= S0's 1.5 / 10 s; no T batch is ever written,
  A4); PausedConnections stayed 0 / negative (the gauge read −24/−25), so the pause was not visible on that gauge;
  K stayed at one request (14,736,433 B) in every sample.
- `T4-1`: OOM ✓ (K = 29/29 admitted, 16 decoding + 15 on NTR). `T8-*`: OOM within the hold **2/3** (T8-1, T8-2; K = 58/58;
  the failing thread an NTR thread in the mutation build), T8-3 GC service loss for ≈ 220 s then an OOM 30 s after the
  hold-end SIGTERM. `P2-1`: OOM **before the batch check is reached** (0 `Batch too large`): where
  `batch_size_fail_threshold` applies it does not protect the heap, because the decode precedes it.

### 3.4 V-table (for the fixed condition T, 2 GiB, shipped defaults)

| | Requirement | Evidence | Met? |
|---|---|---|---|
| V1 | endpoint ≥ 3 clean runs | T2-1, T2-2, T2-3: heap OOM **3/3** (+56, +33, +24 s) | yes |
| V2 | nearest surviving control ≥ 3 runs, no endpoint | C2-1..3 (matched wire bytes, same exempt path): heap OOM **3/3** (+56, +99, +58 s) via a different holder (C2-2 dump: 92 built blob mutations alive vs 14 admitted, write-timeout backlog). S0 (N = 1) survived, but once, 60 s | **no** (row O6) |
| V3 | U measured independently of K | GC log (after-Full-GC 2,041 MiB vs 33 MiB baseline) and T2-1 dump (decoded-request classes 2.24 GB) vs `RequestsSize` 206,310,062 B ⇒ U/K ≈ 10 | yes (T) |
| V4 | intervention removes the endpoint ≥ 3 runs | I2-1..3 (in-flight 16 MiB): 0/3 OOM, one request admitted, responses 23–24 / 150 s = S0's rate (no T batch written in any arm, A4) | yes, with the A4 limit |
| V5 | initiating failure + holder | OOME thread 3/3 in `BatchMessage$1.decode` → `CBUtil.readValueList` / `readBoundValue:480`; T2-1 dump 98.5 % decoded-request classes, 14 envelopes = 14 admitted | yes |
| V6 | constraints at shipped defaults | shipped yaml md5 `714ee9bf…` in every T/C/P run; resolved in-flight 214,748,364 / 53,687,091 B | yes |
| V7 | acceptable budget | heap 2 GiB (ideal), direct auto 15,872 MiB, no container limit; largest failing heap **8 GiB** (OOM 2/3 within the hold, the third service loss then OOM after SIGTERM); 4 GiB 1/1 | yes |

## 4. Conclusion (stage 2)

**Verdict: `retry`.** Protocol status (detail): **`candidate`**: V1, V3–V7 hold for T at 2 GiB, but V2 does not.
The frozen outcome row is **O6** ("C2 OOM (≥ 1/3) … → retry"). Conditions label if V2 were met: `deployment` (defaults,
2 GiB, no supporting deviation; A4 is an observation, not a change).

**Reason.** With every capacity at its shipped default and a 2 GiB heap, the test arm reached `OutOfMemoryError: Java heap
space` in 3/3 runs, 24–56 s after the 16 connections were up. At 4 GiB it failed 1/1. At 8 GiB it failed 2/3 within the
hold; the third run was in GC service loss (96 % STW) and then failed 30 s after the hold-end SIGTERM. The in-flight
counter stayed at or below its limit: 206,310,062 B = 14 × 14,736,433 B ≤ 214,748,364 B (and exactly 29× and 58× at 4 and
8 GiB). The heap held ≈ 10× that: after the last Full GCs 2,041 MiB versus a 33 MiB baseline. The T2-1 dump puts 98.5 %
of its 2.27 GB in decoded-request objects (26.8 M `HeapByteBuffer`, 25.7 M `byte[1]`, 514,813 `MD5Digest`, 14 `Envelope`
= the 14 admitted requests). The OOME thread was in `BatchMessage$1.decode` → `CBUtil.readBoundValue:480` /
`readValueList` in 3/3 runs. Bounding the in-flight limit to one request (16 MiB) removed the endpoint 0/3 at an
unchanged response rate. However, the frozen matched control C (same 15.78 MB bodies as 64 blobs, same exempt
single-partition path) **also reached heap OOM 3/3** (+56, +99, +58 s), through a different holder. On this m400 the
15.8 MB blob writes outran the local write path: 289–332 WriteTimeouts per run, MutationStage pending up to 50,
MUTATION_REQ drops at ≈ 4.4 s. Each timeout answered the client and released its in-flight charge while the built
mutation stayed queued: the C2-2 dump holds 92 `Mutation`s and 2.07 GB of blob `byte[]` (97 %) against 14 admitted
requests. So the control does not show that the same wire volume is safe without the expansion, and V2 is unmet.

**What the runs establish anyway (for the retry design and the session):**
- The claimed holder is real and dominant, but it sits **in decode on the Netty event loops**, not on NTR threads after
  decode as predicted. All 14 admitted requests decode concurrently; at the failure K is at the cap (0.96 C), not at 0.3–0.4 C.
  On the m400 the request's U_req at N = 1 (S0) is 0.6–0.86 GiB, about 40–57× its body.
- **`batch_size_fail_threshold` is irrelevant to this endpoint.** P2-1 (two partitions, which the check would reject)
  failed the same way before any `Batch too large` was logged. The decode precedes every batch check, so the
  single-partition exemption (CASSANDRA-10876, by design) is not needed for the OOM. The gap is the native in-flight
  limit counting wire bytes while the v5 decode of many tiny bound values expands them ≈ 10–15×. This is the same decode
  copy as OC-4, here under protocol v5, where the limit is enforced.
- Interpretation: an accounting / configuration-sizing gap of the in-flight control. heap/10 of wire bytes assumes
  ≈ 1 byte of heap per wire byte. Nothing in the server documents the expansion.
- The control's own endpoint is a second, separate shape: **timed-out local writes release their in-flight charge while
  their mutations remain queued** (92 alive vs 14 admitted). It needs no expansion and is a lead for the candidate list
  (local-write backlog outside the in-flight count). The session decides whether to file it.
- Limits: ARM m400 only (never pooled with x86). At defaults no T batch is ever written on this node: the build takes
  longer than the 2 s write timeout (A4), so the "useful work" comparison for V4 is the response rate. JMX stopped
  answering under Full-GC thrash, so K's last sample can precede the endpoint (T2-3: 44 MB). Dumps at 4/8 GiB were
  analysed for the OOME thread only.

**What a better design should change (retry):**
1. **Replace the control** with one that cannot reach the write path, so no write-timeout backlog can form. For example
   C′ = the same 64-blob body split over **two partitions** (built, then rejected by `batch_size_fail_threshold`, no write),
   matched against **P** (tiny values, two partitions; OOM 1/1 here) as the test arm. Both stop before any write and
   differ only in the decode expansion. Alternatively, keep C on a node where a 15.8 MB write completes within 2 s
   (x86 `pc91`…), and prove in a shakedown that C runs with 0 timeouts and MutationStage pending 0.
2. Make **P (or T) × 3** the test arm with the holder predicted on the **event loops in decode** and K at the cap. Sample
   threads at ≤ 5 s, and read K from the client side when JMX stops answering.
3. Keep the intervention (in-flight 16 MiB; 0/3 here) and add it for the new control.
4. At 8 GiB, use a hold ≥ 300 s, and do not SIGTERM while an OOM dump is being written (wait for "Heap dump file
   created"), so all 3 repeats can end inside the window.
5. Optionally, run the test on x86 to show the endpoint also holds where batches complete (VOID) and the build/apply
   path is reached.
