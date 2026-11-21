# R13 (retry of B14) — native_transport_max_request_data_in_flight: admitted v5 batches of tiny bound values expand ≈ 10–15× in decode, before any batch check  <!-- file: cassandra/cases/native_transport_max_request_data_in_flight--v5-tiny-value-batch-decode-expansion/native_transport_max_request_data_in_flight--v5-tiny-value-batch-decode-expansion.md -->

| Field | Value |
|---|---|
| Case ID | `R13` (a new attempt at `B14`; README "ID prefixes"); direction planned: bypass, accounting mismatch |
| From | retry of `B14` (row of [`phase2-retry-list.md`](../../phase2-retry-list.md)); B14 came from `OC-11` |
| Phase-1 case file | [`batch_size_fail_threshold-verifyBatchSize-mutations--autonomous`](../../../../capacity-enforcement-exp/cassandra/stage3-ai-deep-read/cases/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md) (via B14); stage 4: [`results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md`](../../../../capacity-enforcement-exp/cassandra/stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md). Related open candidate: `OC-4` (same decode copy, protocol v4) |
| System / pinned source | Cassandra 5.0.9 (`systems/cassandra/source/`, tag `cassandra-5.0.9`); build `ms0604:/mydata/s4/cassandra-base` (aarch64), OpenJDK 11.0.33 |
| Stage 1 (design) | OOM-agent stage-1 session (workflow), 2026-11-20 10:30–11:50 America/New_York |
| Stage 2 (verify) | fresh OOM-agent session (workflow), 2026-11-20 10:39–12:55 America/New_York (runs 10:43–12:51), `ms0604` (aarch64); freeze hash matched; no amendment |
| Verdict | **`true positive`** (status `verified-OOM · deployment`; bypass, accounting mismatch; frozen row O1) |

## Summary

- **Conclusion (stage 2):** **true positive** (`verified-OOM · deployment`). With every capacity at its shipped default
  and a 2 GiB heap, two-partition v5 batches of tiny values reached Java heap OOM **3/3** (≈ 25 s after the 16
  connections were up), in decode, before any batch check or write. The matched control (same wire bytes as 64 blobs,
  same path and rejection, in-flight counter at its cap throughout) survived **0/3** with ≤ 110 MiB of heap after GC;
  capping in-flight at one request survived **0/3**. Budget search: 4 GiB 3/3, **8 GiB 3/3**, 16 GiB OOM 1/3 and GC
  service loss 2/3. aarch64 (m400) only.
- **Root cause (as measured):** the native in-flight limit (heap/10 global, heap/40 per IP) charges a request's **wire
  body bytes**, but `BatchMessage` decode copies every bound value into its own `byte[]` + `HeapByteBuffer` on the Netty
  event loop. At the failure the counter held 14 × 14.7 MB = 206 MB ≤ its 215 MB limit while the heap held ≈ 10× that
  (2.04 GiB after Full GC; the dump 93.7 % decoded-request objects). Nothing charges the expansion, and the batch-size
  check runs only after decode.
- **Hypothesis under test (stage 1):** the native-transport in-flight limit (`native_transport_max_request_data_in_flight`,
  heap/10) charges a v5 request's **wire body bytes** at its first frame, but `BatchMessage` decode copies every bound
  value into its own `byte[]` + `HeapByteBuffer` on the Netty event loop. A 15.8 MB batch of 2.86 M one-byte values
  holds ≈ 10–15× its wire size while it decodes, so the 14 requests the limit admits at a 2 GiB heap need ≈ 2–3.3 GB
  of heap before any batch check runs. B14 showed the endpoint (T 3/3, P 1/1) but its matched control also failed,
  through a write-timeout backlog.
- **What is new against B14:** both the test arm (**P**, tiny values, two partitions) and the matched control (**C′**,
  the same body as 64 blobs, two partitions) are **rejected by `batch_size_fail_threshold` after decode and build**, so
  neither ever reaches the write path and no write-timeout backlog can form. They differ only in the decode
  expansion (≈ 10–15× vs ≈ 1×). The holder is predicted on the event loops in decode with K at the cap; the
  intervention (global in-flight 16 MiB) is kept; the budget search goes 2 → 4 → 8 (→ 16) GiB with 8 GiB dumps allowed
  to finish.

## 1. Candidate

**Retry row (quoted from [`phase2-retry-list.md`](../../phase2-retry-list.md), line 19, status as handed to this
session; the two long cells are stored truncated with "…" in the list, so their full text is quoted after it from B14
§4):**

> | [B14](cases/batch_size_fail_threshold--single-partition-batch-heap-expansion/batch_size_fail_threshold--single-partition-batch-heap-expansion.md) (from OC-11) | 2026-11-18 | The freeze hash matches (99b624dc…). I ran the design as frozen on ms0604 (aarch64), with dated amendments A1–A6 recorded in §3.1. With every capacity at its shipped default and a 2 GiB heap, the tiny-value single-partition batch arm T reached `OutOfMemoryError: Java heap space` in 3/3 runs, at +56, +33 and +24 s after the 16 connections were up. At 4 GiB it failed 1/1 (+71 s). At 8 GiB it failed 2/3 within the hold … | 1. Replace the control with one that never reaches the write path, so no write-timeout backlog can form. For example: C′ = the same 64-blob body split over two partitions (built, then rejected by batch_size_fail_threshold), matched against the two-partition tiny-value arm P (OOM 1/1 here). Both stop before any write and differ only in decode expansion. Alternatively, run C on a… | picked again: R13 (2026-11-20) |

**Full "why retry" (B14 §4 "Reason", condensed only by dropping repeated numbers):** T at 2 GiB OOM 3/3 (+56, +33, +24 s);
4 GiB 1/1 (+71 s); 8 GiB 2/3 within the hold, the third in GC service loss (96 % STW) and then OOM 30 s after the hold-end
SIGTERM. K stayed ≤ C: 206,310,062 B = 14 × 14,736,433 B ≤ 214,748,364 B (exactly 29× and 58× at 4 and 8 GiB). The heap
held ≈ 10× that (2,041 MiB after the last Full GCs vs a 33 MiB baseline); the T2-1 dump is 98.5 % decoded-request objects
(26.8 M `HeapByteBuffer`, 25.7 M `byte[1]`, 514,813 `MD5Digest`, 14 `Envelope` = the 14 admitted requests); the OOME thread
was in `BatchMessage$1.decode` → `CBUtil.readBoundValue:480` / `readValueList` 3/3. In-flight 16 MiB removed the endpoint
0/3 at an unchanged response rate. **But the frozen matched control C (same 15.78 MB bodies as 64 blobs, same exempt
single-partition path) also reached heap OOM 3/3** (+56, +99, +58 s) through a different holder: on the m400 the 15.8 MB
blob writes outran the local write path (289–332 WriteTimeouts per run, MutationStage pending ≤ 50, MUTATION_REQ drops at
≈ 4.4 s); each timeout answered the client and released its in-flight charge while the built mutation stayed queued (C2-2
dump: 92 `Mutation`s and 2.07 GB of blob `byte[]` vs 14 admitted). V2 unmet (frozen row O6).

**Full "what a better design should change" (B14 §4):**
1. Replace the control with one that cannot reach the write path, so no write-timeout backlog can form. For example
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

**This design takes change 1 (first option), 2 (with P), 3 and 4.** The x86 alternative of 1 and change 5 are not taken:
the assigned node is `ms0604` only (aarch64), and the first option of 1 removes the write path from both arms, which is a
stronger match than making the write path fast enough on another architecture. B14's T results are context only; R13 does
not reuse any B14 run as evidence.

**Earlier case and its verdict.** [B14](../batch_size_fail_threshold--single-partition-batch-heap-expansion/batch_size_fail_threshold--single-partition-batch-heap-expansion.md),
verdict **retry** (status `candidate`; V1, V3–V7 met for T at 2 GiB, V2 unmet). Its P2-1 (the two-partition tiny-value
arm, 2 GiB, N = 16) reached heap OOM 1/1 at +26 s, K = 206,310,062 B, 14 threads in decode, 0 NTR threads in
`BatchMessage.execute`, **0 `Batch too large`** before the OOM, memtable 0, MutationStage pending 0. B14's own conclusion
moved the claim off `batch_size_fail_threshold`: "The decode precedes every batch check, so the single-partition
exemption … is not needed for the OOM. The gap is the native in-flight limit counting wire bytes while the v5 decode of
many tiny bound values expands them ≈ 10–15×." This case therefore files under the in-flight constraint.

**Phase-1 case (from B14 §1).** `batch_size_fail_threshold-verifyBatchSize-mutations--autonomous` (stage 3, 2026-10-26):
the constraint `batch_size_fail_threshold` (50 KiB, `Config.java:331-332`) is checked in `verifyBatchSize`
(`BatchStatement.java:330-366`) only after `getMutations` has built every mutation (`:428` → `:439`); single-mutation
batches return at `:334` (CASSANDRA-10876). Its 2026-11-16 recheck left "whether the decoded objects … exceed its on-wire
bytes by a large factor (many tiny cells)" as "a question for the in-flight budget, not for this threshold". Stage 4
(advisor's Mac, 2026-10-26): multi-partition batches rejected iff `dataSize` > 1024·F; single-partition accepted; heap
before the check not measured. The phase-1 candidate closest to this case's holder is **OC-4** (open; `native_transport_max_message_size-processFirstFrameOfLargeMessage-maxMessageSize--guided`):
"decode copies each bound value into its own heap buffer (a 16 MiB batch of 1-byte values ≈ 250 MB, ~15×; the heap/10
reserve admits ~51 such at 8 GiB)", framed there for protocol v4. R13 uses v5, where the reserve is enforced for large
messages (`CQLMessageHandler.java:516-605`), so K ≤ C holds by the server's own check. No list status is changed here.
Distinct from B10 (verified-OOM: refused v5 requests decoded and queued **uncharged**): here every held request **is**
charged; the gap is the charge's unit.

**JIRA prior art (read only; nothing posted).** Survey `capacity-enforcement-exp/cassandra/stage5-oom-clue-find/jira-oom-survey.csv`
(604 rows), grep `in.?flight|decode|bound value|CQL message|native.?transport|batch`: CASSANDRA-8518 (Duplicate, 2014: 22
NTR threads each holding ≈ 3.3 % of heap of request data; asks for an in-flight **byte** limit — the limit that now
exists and is the one tested here), CASSANDRA-9318 (Fixed 3.10: bound in-flight requests/bytes at the coordinator),
CASSANDRA-3911 (Won't Fix: QoS to stop clients OOMing, large batches), CASSANDRA-11838 (Fixed 3.8: heap OOM decoding a large
value, recycled buffers), CASSANDRA-12618 (Fixed: one malformed bound value pre-sizes a huge list), CASSANDRA-6107 /
CASSANDRA-16201 / CASSANDRA-7303 (batch allocation issues on other paths). JIRA REST (2026-11-20 ≈ 10:34 ET, reachable):
`text ~ "native_transport_max_request_data_in_flight"` → 17 hits; relevant **CASSANDRA-20052** (Fixed 4.1.8/**5.0.3**: v5 CQL
message size was unlimited; the fix is the 16 MiB `native_transport_max_message_size` check present in 5.0.9; its text:
"The overload logic just allows to process huge messages for free … does not provide any protection against the most
dangerous requests from a memory pressure point of view" — size per message, not expansion), **CASSANDRA-19534** (Fixed
4.1.6/5.0-rc1: bounded native request queue), CASSANDRA-21141 (Fixed 6.0: fewer allocations turning a `BatchStatement` into
a `Mutation`; throughput, not a bound, and after decode). `text ~ "bytes in flight" AND text ~ "heap"` → 18 hits, none on
decode expansion; `text ~ "readBoundValue"` → 3 hits (11838, 14433 paging-state DoS, 7304), none relevant;
`text ~ "BatchMessage" AND (OOM | OutOfMemory | heap)` → 7 hits (15430 Duplicate: 10× more allocations in
`BatchMessage.execute` in 3.0.18 vs 2.1; 16201; 19959 Triage: generic collection-growth list; others unrelated);
`text ~ "decode" AND text ~ "in-flight" AND text ~ "memory"` → 13 hits, none relevant. CASSANDRA-7402 (Open, 7.x: "Add
metrics to track memory used by client requests") confirms the server has no measure of request heap. **Verdict: `new`**
(no report that the wire-byte in-flight reserve admits ≈ 10× its value in decoded heap for many-tiny-value requests;
the size cap of 20052 and the queue bound of 19534 are fixed and present in 5.0.9 and do not cover it).

## 2. Design solution (stage 1; frozen)

### 2.1 Mechanism

1. **Admission (event loop, charged on wire bytes).** A v5 request larger than one frame (`LARGE_MESSAGE_THRESHOLD` =
   131,071 B, `CQLMessageHandler.java:83`) takes `processFirstFrameOfLargeMessage` (`:516`): the size check against
   `native_transport_max_message_size` (CASSANDRA-20052), then `acquireCapacityAndQueueOnFailure` (`:605`): the body size
   is charged to the connection's 1 MiB queue capacity and the rest to the per-IP (heap/40) and global (heap/10) reserves
   (`AbstractMessageHandler.java:411-426`; defaults `DatabaseDescriptor.java:649-657`); if that fails the connection stops
   reading until capacity is released (no starvation: the message is ≤ both reserves). The frames of the partial message
   are kept as networking-pool (direct) `ShareableBytes` (`AbstractMessageHandler.java:527-546`); a large CQL message never
   expires while it is received (`EXPIRES_AT = Long.MAX_VALUE`, `CQLMessageHandler.java:751`).
2. **Decode (same event loop).** On the last frame `LargeMessage.onComplete` (`:822-835`) wraps the frames
   (`assembleFrame`, `:762-771`) and calls `processRequest` (`:385`), which decodes on the event loop
   (`messageDecoder.decode`, `:390`) before dispatch (`:391`). `BatchMessage.codec.decode` (`BatchMessage.java:56-75`):
   per statement an `MD5Digest` + `byte[16]` (`:68`) and a value list (`:71`, `CBUtil.readValueList`), and **per bound
   value a fresh `byte[len]` wrapped in a `HeapByteBuffer`** (`CBUtil.java:466-480`, copy at `:480`). A 1-byte value is
   4 + 1 wire bytes and ≈ 72 B of heap (+ list slots); a 246,599-byte blob is ≈ 1.0× its wire bytes. The event-loop group
   is `new EpollEventLoopGroup()` (`NativeTransportService.java:69`), Netty default 2 × cores = **16 threads** on this node,
   so at most 16 requests decode at once; B14 saw 14 (= all admitted) decoding together at 2 GiB.
3. **Execute (NTR thread).** `BatchMessage.execute` → `BatchStatement.execute` (`BatchStatement.java:405-431`) →
   `getMutations` (`:428`) builds every row (cells referencing the decoded buffers) → `executeWithoutConditions`
   (`:434-447`) → `verifyBatchSize` (`:439`): for ≥ 2 mutations, `IMutation.dataSize` > 50 KiB ⇒ `logger.error(…)` (`:356`)
   and `InvalidRequestException("Batch too large")` (`:358`). **Both R13 arms P and C′ are two-partition batches far above
   50 KiB, so both are rejected here; neither reaches `StorageProxy.mutateWithTriggers` (`:445`)**: no commit log, no
   memtable, no MutationStage task, no write timeout.
4. **Release.** The error response is flushed and the request's charge released (`CQLMessageHandler.java:500-509`); the
   decoded and built objects become garbage.

So between first frame and response a request holds: its frames (direct), its decoded `BatchMessage` (heap; ≈ 15× body for
P, ≈ 1× for C′) and, on the NTR thread, the built mutations (P ≈ +55,000 × 2.4 KB; C′ ≈ +15 KB). Only the wire body is
charged.

- **Direction (planned, by measurement §2.6):** **bypass — accounting mismatch** (U > C, K ≤ C) of the native in-flight
  control: its purpose is to bound request memory, its counter is wire bytes, and the decode expansion is charged nowhere.
  `batch_size_fail_threshold` is the rejecting check in both arms and is shown not to protect the heap (it runs after
  decode and build). Interpretation to state at stage 2: accounting / configuration-sizing gap (heap/10 of wire bytes is
  sized as if a request held ≈ 1 byte of heap per wire byte); not documented as by design.
- **Technique note:** [`bypass-playbook.md`](../../../bypass-playbook.md) (protected vs suspect payload on the same path,
  matched wire bytes); the budget search follows [`combo-playbook.md`](../../../combo-playbook.md) only for the
  multiplicity per heap.

### 2.2 Protection map

| Domain | Holder (allocation → release) | Counter (K) | Limit (C), shipped default | At the limit |
|---|---|---|---|---|
| **Native request in flight** (claimed) | decoded `BatchMessage` (per value `byte[]` + `HeapByteBuffer`, per statement `MD5Digest` + value `ArrayList`; `BatchMessage.java:56-75`, `CBUtil.java:480`) and, on the NTR thread, the per-statement options and built `Mutation`/`PartitionUpdate` → garbage after the error response (`BatchStatement.java:428-439`) | per-connection queue (1 MiB) + per-IP and global reserve bytes = **wire body bytes**, acquired at the first frame (`CQLMessageHandler.java:605`, `AbstractMessageHandler.java:411-426`); gauge `org.apache.cassandra.metrics:type=Client,name=RequestsSize` | global `native_transport_max_request_data_in_flight` = heap/10, per IP heap/40 (`DatabaseDescriptor.java:649-657`); + `native_transport_receive_queue_capacity` 1 MiB per connection. Contract: bytes of request bodies | connection stops reading until capacity frees |
| Per-batch size (rejecting check, both arms) | the same built mutations | `IMutation.dataSize` | `batch_size_fail_threshold` 50 KiB (`Config.java:331-332`), multi-partition only; checked **after** decode and build (`BatchStatement.java:428` → `:439`) | `InvalidRequestException("Batch too large")` + one ERROR line per batch (`:356-358`) |
| Request size | one message | body size | `native_transport_max_message_size` = min(`max_mutation_size` 16 MiB, heap/10, heap/40) → 16 MiB at heap ≥ 640 MiB (CASSANDRA-20052) | message discarded |
| Mutation size | built mutation per partition | serialized size | `max_mutation_size` 16 MiB, checked in the build (`SingleTableUpdatesCollector.java:112`); each R13 partition ≤ 8 MB | `MutationExceededMaxSizeException` (not expected) |
| Statements / values | — | count | protocol `[short]` 65,535 | protocol error |
| Decoding concurrency | Netty event loops | threads | 16 (2 × cores, `NativeTransportService.java:69`) | further completed messages wait on their loop |
| Executing requests | NTR pool | active tasks | `native_transport_max_threads` 128 | queued |
| Large-message frames | networking `BufferPool` / overflow `allocateDirect` | pool `Size`, `OverflowSize` | `networking_cache_size` min(128 MiB, heap/16); overflow uncapped (B1, B13) | direct; competing endpoint only |
| Memtable / commit log / MutationStage | — | — | `memtable_heap_space` heap/4 etc. | **not reached in any arm** (both arms rejected before the write; checked by instruments) |
| Heap budget | JVM heap | — | `-Xmx` 2 GiB (then 4, 8, 16 GiB) | `OutOfMemoryError: Java heap space` → shipped `HeapDumpOnOutOfMemoryError` + `OnOutOfMemoryError` kill |
| Direct budget | frames, Netty | JMX `java.nio:type=BufferPool,name=direct` | `MaxDirectMemorySize` auto 15,872 MiB on this node | competing endpoint only |

Not on the path at defaults (checked in B14 and unchanged): guardrails (`AllowAllAuthenticator` ⇒ superuser; no batch
guardrail), tracing, audit/FQL, rate limiting (off), `native_transport_throw_on_overload` (client option, not set).

### 2.3 Configuration and budget audit

- **Build:** `ms0604:/mydata/s4/cassandra-base` (Cassandra 5.0.9, `git describe --tags` `cassandra-5.0.9`, the tree B14 ran
  from), **copied** with `cp -a` to the fresh work dir `/mydata/s4/r13-w1/cassandra` (`diff -rq` empty); the shared tree is
  read only. No patch, no rebuild. Record `md5sum` of `conf/cassandra.yaml` (shipped `714ee9bf58b3bc1710377ac16bcbba03`),
  `conf/jvm11-server.options` (`fbad82a853f1b85aea0fa5ea34b6d1bf`), `conf/cassandra-env.sh`
  (`8be0588e87c594a03360751b1dbf4fbf`) in every run; stop if any differs.
- **Configuration:** the shipped `conf/` unchanged for P and C′ (single node, `127.0.0.1`, data under the tree). Every
  capacity in §2.2 at its shipped default (V6): in-flight heap/10 and heap/40, receive queue 1 MiB, max message 16 MiB
  (derived), `batch_size_fail_threshold` 50 KiB, `batch_size_warn_threshold` 5 KiB, `max_mutation_size` 16 MiB (derived),
  `native_transport_max_threads` 128, `memtable_heap_space` heap/4, `write_request_timeout` 2 s, `native_transport_timeout`
  12 s, rate limiting off, connection limits −1. **Intervention arms only:** conf copy `/mydata/s4/r13-w1/conf-i` = shipped
  + one appended line `native_transport_max_request_data_in_flight: 16MiB` (capacity change in an intervention arm, allowed
  by V6).
- **Resolved at each heap** (`Runtime.maxMemory()` = `-Xmx` under G1; read from JMX `StorageService`
  `NativeTransportMaxConcurrentRequestsInBytes[PerIp]`, since `system.log` prints them as `null`):

| Heap | global C (B) | per IP (B) | P charge / request (B) | admitted P requests | C′ charge (B) | admitted C′ |
|---|---|---|---|---|---|---|
| 2 GiB | 214,748,364 | 53,687,091 | 14,736,433 | 14 | 14,736,393 | 14 |
| 4 GiB | 429,496,729 | 107,374,182 | 14,736,433 | 29 | — | — |
| 8 GiB | 858,993,459 | 214,748,364 | 14,736,433 | 58 | — | — |
| 16 GiB | 1,717,986,918 | 429,496,729 | 14,736,433 | 116 | — | — |
| 2 GiB, conf-i | 16,777,216 | 53,687,091 | 14,736,433 | 1 | 14,736,393 | 1 |

  (charge = body − 1,048,576 B queue capacity; P body 15,785,009 B, C′ body 15,784,969 B, §2.4.)
- **Environment (not capacity):** `MAX_HEAP_SIZE=<heap>`, `HEAP_NEWSIZE` unset (G1), so `-Xms = -Xmx`;
  `CASSANDRA_HEAPDUMP_DIR=<run dir>`; `ulimit -n 100000`; `systemd-run --user --scope -p MemorySwapMax=0` (swap 0 for the
  measured process; **no `MemoryMax`**). Linger is `no` on this node (checked 2026-11-20 10:32 ET) and B14 could not
  enable it: drive each series from one `ssh` session kept open for its length (B14 A2), daemon started with
  `setsid nohup`. Shipped G1, `G1HeapRegionSize=16m`, shipped `HeapDumpOnOutOfMemoryError` and `OnOutOfMemoryError` kill.
  **16 GiB runs only:** `JVM_EXTRA_OPTS=-XX:-HeapDumpOnOutOfMemoryError` (appended last, `cassandra-env.sh:307`; confirm
  with `jcmd VM.flags`), because a ≈ 20 GB dump does not fit the disk plan; an instrumentation change in a budget-search run,
  not a capacity change; the initiating thread is then read from the first `system.log` ERROR.
- **Node claimed (V7):** `ms0604` = node2.jason92-326377 (Utah m400, **aarch64**, 8 cores, 62 GiB RAM, 8 GiB swap,
  Ubuntu 22.04, kernel 5.15, OpenJDK 11.0.33). Checked read-only 2026-11-20 10:32 ET: no Java/Cassandra running, ports
  7000/7199/9042 free, 52 GiB free RAM, `/mydata` 39 GiB with **30 GiB free**; `/mydata` holds `s2r2`, `u1r2`,
  `s4/cassandra-base` (B14's `b14-w3` is gone). `cassandra-env.sh` would resolve heap = 31,744 MiB and
  `MaxDirectMemorySize` = 15,872 MiB for this node; with a hand-set heap the direct limit stays 15,872 MiB.
  **Budgets:** heap 2 GiB (ideal), then 4, 8 and 16 GiB (upward search); all ≥ 512 MiB ⇒ V7 met without per-case review
  (standing rule 2026-11-11). Direct: the auto 15,872 MiB. No container limit is a budget, so no owner review is needed.
  ARM: never pool these runs with x86 runs.

### 2.4 Ceiling arithmetic

**Payloads** (prepared `LOGGED` BATCH, consistency ONE, flags 0, protocol v5, 121 segments of ≤ 131,071 B each):
- **P (test):** table `r13.t (k int, c int, v00 … v49 tinyint, PRIMARY KEY (k, c))`; 55,000 statements of
  `INSERT INTO r13.t (k, c, v00, …, v49) VALUES (?, …, ?)` (52 markers), c = 0 … 54,999, every v one byte; statements
  0 … 27,499 on key k, 27,500 … 54,999 on key k + 500,000 (two partitions). Wire per statement 287 B; body = 3 + 55,000 ×
  287 + 6 = **15,785,009 B**. `dataSize` ≈ 33 MB ≫ 51,200 B ⇒ rejected if reached. 2.86 M bound values per request.
- **C′ (matched control):** table `r13.big (k int, c int, v blob, PRIMARY KEY (k, c))`; 64 statements of
  `INSERT INTO r13.big (k, c, v) VALUES (?, ?, ?)`, c = 0 … 63, v = 246,599-byte blob `(bytes(range(256)) * 964)[:246599]`;
  statements 0 … 31 on key k, 32 … 63 on key k + 500,000 (two partitions). Wire per statement 246,640 B; body = 3 + 64 ×
  246,640 + 6 = **15,784,969 B** (40 B less than P). `dataSize` ≈ 15.8 MB ≫ 51,200 B ⇒ rejected. Each partition ≈ 7.9 MB
  < 16 MiB `max_mutation_size`. 192 bound values per request.

**Heap per request (measured in B14 where possible):**
- P decoded, complete: B14 T2-1 dump 2,236,700,523 B of decoded-request objects for 514,813 statements ⇒ ≈ 4.35 KB
  per statement ⇒ **≈ 239 MB per fully decoded request (15.2 × body)** (shallow sizes with 8-byte ids overstate a
  compressed-oops heap by ≈ 10–15 %, so 205–239 MB). Built (NTR): ≈ 2.4 KB × 55,000 ≈ 132 MB more (B14 §2.4 estimate);
  S0 at N = 1 measured 0.6–0.86 GiB after Full GC with one request in flight (decoded + built + garbage).
- C′ decoded: 64 × (246,599 + 16 + 48 + list slots) + 192 small values ≈ **15.8 MB (1.0 × body)**; built ≈ +15 KB.
- Baseline (B14 S0, idle 5.0.9 at 2 GiB on this node): 33 MiB after GC; early after-GC readings 9–79 MiB, one 451 MiB.

| Heap / arm | C / admitted | N conn | Demand if every admitted request is held decoded | Predicted endpoint |
|---|---|---|---|---|
| 2 GiB / P | 214.7 MB / 14 | 16 | ≤ 16 decode at once ⇒ 14 × 205–239 MB = 2.9–3.3 GB > 2,048 MiB | **heap OOM** in decode once ≈ 8.5–10 requests' worth is decoded (2,048 MiB − ≤ 100 MiB baseline) — as in B14 (9.4 requests' worth at failure); K at the cap (14 admitted) |
| 2 GiB / C′ | 214.7 MB / 14 | 16 | 14 × 15.8 MB = 221 MB (+ young garbage) | **survive**: live ≤ 0.1 + 0.25 ≈ 0.35 GB ≈ 17 % of heap (≥ 70 % margin) |
| 2 GiB / P, conf-i | 16.8 MB / 1 | 16 | 1 × (239 + 132) MB ≈ 0.37 GB; S0 bound 0.86 GiB | **survive** (≥ 55 % margin from S0's max) |
| 2 GiB / C′, conf-i | 16.8 MB / 1 | 16 | 1 × 15.8 MB | survive; response rate falls (diagnostic) |
| 4 GiB / P | 429.5 MB / 29 | 32 | 16 decoding × 239 MB = 3.8 GB + 13 decoded/building × 0.37 GB = 4.8 GB ⇒ 8.6 GB | **heap OOM** |
| 8 GiB / P | 859.0 MB / 58 | 64 | 3.8 GB + 42 × 0.37 GB = 15.5 GB ⇒ 19 GB | **heap OOM** (B14 T8: 2/3 in the hold) or service loss |
| 16 GiB / P | 1,718 MB / 116 | 128 | 3.8 GB + 100 × 0.37 GB ≈ 41 GB | OOM if the client sustains 128 connections and requests stay held; uncertain (CPU on 8 cores shared with 16 client processes) |

Σ contract capacities covering this memory: heap/10 + N × 1 MiB of **wire** bytes; the expansion (≈ 15× while decoding)
is covered by nothing, so U ≈ 1.5 × heap at full admission for every heap: the endpoint is arithmetically reachable at
2–16 GiB; the limits on the search are decode/client throughput and dump disk space. Direct: frames ≈ K plus pool
overflow ≤ ≈ 2.5 GB at 16 GiB ≪ 15,872 MiB. Node RAM at 16 GiB: heap 16 + direct ≤ 3 + metaspace/threads ≈ 1 + client
128 × ≈ 48 MB ≈ 6 GiB ≈ 26 GiB < 62 GiB. Disk: one dump on disk at a time (2 GiB ≈ 2.5 GB, 4 GiB ≈ 5.3 GB, 8 GiB ≈ 10.5 GB;
none at 16 GiB), 30 GiB free.

### 2.5 Workload and environment

- **Node:** `ms0604` only (victim and client on the same node, as in B14). Work dir `/mydata/s4/r13-w1/`: `cassandra/`
  (copied tree), `conf-i/`, `harness/`, `runs/<run-id>/`. Before anything: no `java` process with `CassandraDaemon`, ports
  7000/7199/9042 free. Do not touch `/mydata/s2r2`, `/mydata/u1r2`, `/mydata/s4/cassandra-base` (read-only source of the copy).
- **Harness** (`harness/` in this case folder, synced to `/mydata/s4/r13-w1/harness/`): start from B14's
  [`harness/`](../batch_size_fail_threshold--single-partition-batch-heap-expansion/harness/) (`client.py` v5 client with
  its own segment codec, `run.sh`, `series.sh`, `monitor.sh`, `Jmx.java`, `threadcount.py`, `summarize.py`, `excerpt.sh`,
  `hprof-histo.py`, `hprof_oome_thread.py`) with these changes:
  1. Keyspace `b14` → `r13` everywhere (DDL, statements, JMX bean names); unit prefix `r13-`; work dir `/mydata/s4/r13-w1`.
  2. `client.py`: new arm **`Cp`** = C′: arm C's template with statements j ≥ 32 recorded in `offs2` (second partition,
     key k + 500,000, as arm P already does), prepared with `STMT_C`. Keep arm `P` unchanged. Add `--last-delay S`
     (default 0): send all but the last segment of each request, sleep S, send the last one (§2.8 pacing rule only).
     Per-second client line adds `sent_first` (requests whose first segment is sent and not yet answered); response
     statuses keep the server's error code (`0x2200` Invalid = "Batch too large", `0x1100` WriteTimeout, `0x1001`
     Overloaded). Check offline before any run: P body 15,785,009 B, C′ body 15,784,969 B, 121 segments each, 27,500 / 27,500
     and 32 / 32 key offsets.
  3. `run.sh`: (a) find the daemon only among `java` processes (`ps -eo pid=,comm=,args= | awk '$2=="java" && /CassandraDaemon/'`),
     never `pgrep -f` (B14 A6); (b) at the hold end, if `stdout.txt` has `Dumping heap to` without `Heap dump file created`,
     wait for it (≤ 600 s) before any SIGTERM (B14 change 4); (c) optional `JVM_EXTRA_OPTS` passthrough (16 GiB runs);
     (d) preflight `df` avail ≥ heap + 8 GiB, except 16 GiB runs (no dump) ≥ 10 GiB.
  4. `monitor.sh`: `Thread.print` summary every **5 s** (was 10 s); JMX poll every 5 s adds
     `org.apache.cassandra.metrics:type=ClientRequest,scope=Write,name=Latency` `Count` and `…,name=Timeouts` `Count`
     (client writes executed / timed out: must stay 0 in every arm), `type=Table,keyspace=r13,scope=big|t,name=AllMemtablesHeapSize`,
     MutationStage `CompletedTasks` and `PendingTasks`, the networking pool `type=BufferPool,scope=networking,name=OverflowSize`
     and `Size`, and the JDK direct `MemoryUsed`.
  5. `summarize.py`: count `Batch too large` ERROR lines in `system.log*` and responses by status; GC STW share counting
     each GC id once across rotated `gc.log*` files (B14's double count); K_server last answered sample and **K_client** =
     min(Σ `sent_first`, admitted) × charge as the bound used when JMX stops answering; `threads.txt` maxima of event
     loops in `BatchMessage$1.decode` and NTR threads in `BatchMessage.execute` / `getMutations`.
  6. `hprof-histo.py` want-list as B14 (`HeapByteBuffer`, `byte[]` by length 1 and 246,599, `Object[]`, `ArrayList`,
     `MD5Digest`, `BatchMessage`, `Envelope`, `Mutation`, `PartitionUpdate`, `BufferCell`, `BTreeRow`).
- **Per connection:** connection i binds to `127.1.(i // 250).(1 + i % 250)` (own IP, so the per-IP limit never binds),
  STARTUP → PREPARE → closed loop, one batch outstanding, a new key pair per request (k = 1,000,000 × (i+1) + seq). ≤ 8
  connections per client process. `--ddl` creates `r13` (SimpleStrategy RF 1), `r13.t`, `r13.big`.
- **Run driver:** `run.sh <run-id> <base|i> <heap> <P|Cp> <N> <hold-s> [last-delay]`: preflight → wipe tree `data/`, `logs/`
  → start under the scope → wait for `Starting listening for CQL clients` (≤ 300 s) → `jcmd VM.flags`, resolved in-flight
  values from JMX → `--ddl` → 20 s idle baseline with monitors → client → stop at the endpoint (daemon gone +
  `java.lang.OutOfMemoryError` in `stdout.txt`) or at `<hold-s>` → client stop → (dump wait) → `kill`, `-9` after 60 s →
  copy `system.log*`, `gc.log*`, stdout, client and monitor logs → `summarize.py`. Disk guard: avail < 6 GiB ⇒ stop the
  client, record as a deviation.
- **Runs** (all at shipped defaults unless the conf says `i`; one run at a time on `ms0604`):

| Run | Conf | Heap | Arm | N | Hold | Purpose |
|---|---|---|---|---|---|---|
| `SH-P` shakedown | base | 2 GiB | P | 1 | 90 s | reachability: every response `0x2200 Batch too large`, one ERROR line per response, ClientRequest Write count 0, memtables 0; K_server ≈ 14.7 MB while in flight; U_req at N = 1 (component alone) |
| `SH-Cp` shakedown | base | 2 GiB | Cp | 16 | 90 s | every response `0x2200`, no VOID / WriteTimeout, ClientRequest Write count 0, memtable `big` 0; response rate; K_server distribution (applies the §2.8 pacing rule) |
| `P2-1..3` test | base | 2 GiB | P | 16 | ≤ 180 s | V1 |
| `Cp2-1..3` control | base | 2 GiB | Cp | 16 | 180 s | V2 |
| `IP2-1..3` intervention | i | 2 GiB | P | 16 | 150 s | V4 |
| `ICp2-1` | i | 2 GiB | Cp | 16 | 150 s | intervention cost on the control payload (diagnostic, retry change 3) |
| `P4-1..3` | base | 4 GiB | P | 32 | ≤ 240 s | budget search |
| `P8-1..3` | base | 8 GiB | P | 64 | ≤ 300 s (+ dump wait) | budget search |
| `P16-1` (→ `-2`, `-3`) | base + no dump | 16 GiB | P | 128 | ≤ 300 s | budget search, if time |

  **Order:** `SH-P`, `SH-Cp`, then `P2-1`, `Cp2-1`, `IP2-1`, `P2-2`, `Cp2-2`, `IP2-2`, `P2-3`, `Cp2-3`, `IP2-3`, `ICp2-1`,
  `P4-1`, `P8-1`, `P4-2`, `P4-3`, `P8-2`, `P8-3`, `P16-1` (→ `-2`, `-3`). If a budget fails 0/1, do not go higher; run its
  repeats only if they still help the boundary (largest failing budget). If `P2` ends 2/3, run `P2-4` and `P2-5` before the
  budget search (V1 needs ≥ 3 endpoints; report n/N).
- **Time plan (America/New_York; node clock MST = ET − 2 h).** Stage 2 starts ≈ 12:00. Copy tree + harness changes +
  offline body checks: 12:00–12:45. Shakedowns: 12:45–13:00. Ten 2 GiB runs at ≈ 6–7 min each (start ≈ 60–90 s, baseline
  20 s, load ≤ 150–180 s, a 2.5 GB dump ≈ 80 s, teardown ≈ 60 s): 13:00–14:15. `P4-*` ≈ 8 min each, `P8-*` ≈ 11–12 min each
  (dump ≈ 180 s): 14:15–15:15. `P16-*` ≈ 9 min each: 15:15–15:45 (up to 16:15 for three). Dump analysis (full histogram of
  the `P2-1` dump; OOME thread of every failing run; a `Cp2` dump only if one fails) and excerpts in parallel with runs;
  §3–§4 write-up 16:15–17:15. **Hard limits:** no run starts after 16:30; every process stopped and the node checked empty
  by 16:50; the case file done by 17:30. If behind, drop in this order: `P16-*`, `ICp2-1`, `P8-3`, `P8-2`, `P4-3`, `P4-2`;
  never drop a V-run (`P2`, `Cp2`, `IP2`) for a budget-search run.

### 2.6 Instruments

| What | How | Interval | Gives |
|---|---|---|---|
| Heap occupancy (U side) | shipped Xlog `logs/gc.log*` (heap before → after each GC, `Pause Full`, `To-space exhausted`); `jcmd GC.heap_info` (no forced GC) | every GC; 3 s | U(t) = heap after GC − idle baseline (memtables are 0 in every arm, checked) |
| K (server) | JMX `Client.RequestsSize`, `Client.PausedConnections` (one long-lived `Jmx.java` poller) | 5 s | reserve bytes in flight; ≤ C by construction |
| K (client) | per-second `sent_first`, `outstanding` | 1 s | bound on admitted requests when JMX stops answering |
| Held requests | `jcmd Thread.print` → event loops in `BatchMessage$1.decode`; NTR threads in `BatchMessage.execute`, `getMutations`, `verifyBatchSize` | **5 s** | where the requests are held (decode vs build) |
| Write path absent | JMX `ClientRequest,scope=Write,name=Latency` `Count`, `…Timeouts` `Count`; MutationStage `CompletedTasks`/`PendingTasks`; `AllMemtablesHeapSize` of `r13.t`, `r13.big` | 5 s | must stay 0 / flat (system tables only): proves no write-timeout backlog |
| Rejections | `system.log*` count of `Batch for [r13.` … `(see batch_size_fail_threshold)` ERROR lines; client statuses | per run | requests that reached the check |
| Direct / networking pool | JMX direct `MemoryUsed`; networking pool `Size`, `OverflowSize` | 5 s | competing direct endpoint watch |
| Process | `RssAnon`; client `ps -o pcpu,rss` | 3 s / 10 s | native growth; client CPU |
| Throughput | `completions-*.txt` | per response | response rate and kinds per arm (intervention cost) |
| Endpoint | `stdout.txt` first `java.lang.OutOfMemoryError`, `Dumping heap`, `Heap dump file created`, kill line; first `system.log` ERROR with its thread | end | endpoint type, initiating thread |
| Holder at failure (V5) | shipped dump: `hprof_oome_thread.py` (every failing run with a dump), `hprof-histo.py --top 30` (first failing run at 2 GiB; at 4/8 GiB OOME thread only unless time allows) | at failure | decoded-request share; `Envelope` / `BatchMessage` / `Mutation` counts vs admitted |
| Disk | `df -BM /mydata` | 10 s | guard |

Matched instrumentation in every arm; no forced GC or live histogram during load. Dumps: record size and sha256, analyse,
delete (at most one `.hprof` on disk).

### 2.7 Predicted response, outcome rows and stopping budget

**Predicted (before readings):**
- `SH-P`: every response `0x2200 Batch too large` (one ERROR line each), latency ≈ 4–15 s; K_server 14,736,433 while in
  flight; heap after GC during a request 0.3–0.9 GiB; ClientRequest Write count 0; memtables 0.
- `SH-Cp`: every response `0x2200` (no VOID, no WriteTimeout), ≥ 5 responses/s in total; heap after GC ≤ 0.6 GiB;
  ClientRequest Write count 0; memtable `big` 0; K_server max ≥ 0.9 C and median ≥ 0.5 C (else §2.8 pacing rule).
- `P2-*`: **heap OOM 3/3** within 120 s of the last connection; K_server at the last answered sample ≥ 0.9 C (14 admitted)
  or K_client = 14 requests; ≥ 10 event loops in `BatchMessage$1.decode` and ≤ 2 NTR threads in `BatchMessage.execute` at
  the last thread sample; **0 `Batch too large`** before the OOM; ClientRequest Write count 0, memtable 0. U/K at failure
  8–15 (heap after the last Full GC ≈ 1.9–2.04 GiB vs K ≈ 206 MB). Initiating thread an event loop in
  `CBUtil.readBoundValue` / `readRawBytes` / `readValueList` under `BatchMessage$1.decode`. `P2-1` dump: decoded-request
  classes (HeapByteBuffer + `byte[1]` + `Object[]` + `ArrayList` + `MD5Digest`) ≥ 50 % of shallow bytes (expected ≥ 90 %),
  `Envelope` ≤ 14, `Mutation` ≤ 2.
- `Cp2-*`: **survive 0/3** for 180 s; heap after GC max ≤ 0.8 GiB (< 1.4 GiB = 70 % in every case); GC STW share < 50 %
  over the last 60 s; every response `0x2200`, ≥ 5/s; ClientRequest Write count 0.
- `IP2-*`: **survive 0/3** for 150 s; K_server ≤ 14,736,433 in every sample; responses ≥ 1 per 15 s, all `0x2200`; heap
  after GC ≤ 1.4 GiB.
- `ICp2-1`: survive; response rate below `Cp2`'s (one request at a time).
- `P4-*`: OOM 3/3 within 180 s; `P8-*`: OOM ≥ 2/3 within 300 s (holder: decoded requests on NTR threads and in decode);
  `P16-1`: OOM or GC service loss (uncertain).

| Row | Observation | Reading |
|---|---|---|
| O1 | P2 OOM ≥ 3/3 (V1); Cp2 0/3 with responses (V2); IP2 0/3 with responses (V4); U from GC log + dump vs K (V3); OOME thread in decode/build and dump ≥ 50 % decoded-request classes (V5); defaults (V6); 2 GiB (V7); write path absent in P and Cp | **true positive**: `verified-OOM · deployment`, bypass by accounting mismatch of the native in-flight control |
| O2 | P2 ends in GC service loss (≥ 90 % STW over ≥ 60 s) without an OOM by the hold end | `verified-gap · service-loss` at best → **retry** |
| O3 | P2 OOM but decoded/built batch classes < 50 % of the dump, or another holder dominates | attribution fails → **retry** |
| O4 | P2 survives 0/3 with K at the cap and U/K < 5 | expansion estimate wrong: if 14 × measured U_req + baseline < 2 GiB and the same holds at 4 GiB → **false positive**, else **retry** |
| O5 | Cp2 OOM ≥ 1/3 | V2 unmet → **retry**; record its holder (dump histogram) |
| O6 | any VOID, WriteTimeout, ClientRequest Write count > 0 or memtable > 0 in P or Cp | the arm reached the write path: harness/payload invalid → fix before readings (shakedown) or record the run invalid |
| O7 | IP2 OOM ≥ 1/3, or IP2 answers no request | V4 unmet → **retry** |
| O8 | direct-buffer OOM or kernel kill first | competing endpoint → record; **retry** |
| O9 | node fails to start, protocol/CRC errors, client cannot hold N connections, `MutationExceededMaxSize` | invalid run → fix and rerun |

**Stopping budget:** per run as in §2.5 (hold ≤ 150–300 s after the last connection, plus start, dump and stop); one
endpoint per run, no escalation after an OOM; N never above the table value; no run starts after 16:30 ET; the whole stage
within the time plan.

### 2.8 Controls and intervention

- **Matched control (V2), 3 runs: arm C′ (`Cp`).** Same path end to end: v5 large message, same admission and charge
  (14,736,393 vs 14,736,433 B; 14 admitted), decode on the event loops, build on NTR, rejected by the same
  `verifyBatchSize` call with the same ERROR line, same N, heap, build, conf and instruments; neither arm writes. Only the
  payload shape differs: 192 values of which 64 are 246,599-byte blobs vs 2.86 M one-byte values, i.e. decoded heap ≈ 1×
  vs ≈ 15× the charge. Survival shows the endpoint needs the expansion, not the admitted wire volume, the frames, the
  build, the rejection or the ERROR logging.
  - **Pacing rule (pre-registered, not an amendment):** C′ decodes in milliseconds, so its charge could be held for less
    of the time than P's. If `SH-Cp` shows K_server median < 0.5 C (< 107 MB) or max < 0.9 C (< 193 MB), every `Cp2` and
    `ICp2` run uses `--last-delay 2` (the client holds back each request's last segment for 2 s, so the charge is held at
    the cap while the frames wait in direct memory; a large CQL message being received never expires, `CQLMessageHandler.java:751`). Record which
    setting was used and the K_server distribution of every `Cp2` run; a `Cp2` run whose K_server max < 0.9 C is reported
    as such (weaker match), not dropped.
- **Causal intervention (V4), 3 runs: arm I (`IP2`).** Payload P with `native_transport_max_request_data_in_flight: 16MiB`
  (heap/128): the control admits ⌊16,777,216 / 14,736,433⌋ = 1 request at a time, i.e. the limit expressed in what the heap
  can hold at the measured expansion. Survival with responses continuing (rate recorded against `SH-P`, the N = 1
  reference) shows the OOM is caused by the number of concurrently decoded requests the wire-byte count admits. All P
  responses are rejections in every arm, so "useful work" is the response rate. `ICp2-1` records the cost of the same bound
  on the control payload (diagnostic only).
- **Component alone:** `SH-P` (N = 1) gives one request's U_req.
- **V-table plan:** V1 `P2-1..3`; V2 `Cp2-1..3`; V3 U from the GC log + `P2-1` dump vs `RequestsSize` / K_client; V4
  `IP2-1..3`; V5 OOME threads of `P2-1..3` + `P2-1` histogram; V6 §2.3 (md5, resolved values from JMX); V7 2 GiB heap, auto
  direct, no container limit; largest failing budget from `P4/P8/P16` with n/N.

`sha256 of §1–§2 at freeze: 1cbfc3816a56dca09aeda7b1180a7ed6fdf729ab7730e19fb57a5ec74d9990e0` · computed over the lines from `## 1. Candidate` through the line before this one (`awk '/^## 1\. Candidate/{f=1} /^.sha256 of §1–§2 at freeze/{f=0} f' <case file> | sha256sum`), frozen 2026-11-20 · amendments after the freeze: dated, with reason.

## 3. Runs (stage 2)

Stage 2: a fresh OOM-agent session (workflow), 2026-11-20 10:39–12:55 ET on `ms0604`; all runs stopped 12:51 ET, node checked empty 12:53 ET. Freeze hash re-computed at start
with the §2 command: `1cbfc3816a56dca09aeda7b1180a7ed6fdf729ab7730e19fb57a5ec74d9990e0` — **matches**. Node checked
10:40 ET: no `java` process, ports free, 52 GiB free RAM, `/mydata` 30,235 MiB free, Linger `no`.

### 3.1 Amendments and harness notes (dated; none changes a capacity, budget or arm)

No amendment to the frozen design was needed: every run in §2.5's table and order ran as written (the run list is
`harness/list-main.txt`). The notes below record how the harness met the design and one pre-registered rule applied.

- **N1 (10:43 ET, before any run) — linger / series driver.** As §2.3 foresaw (Linger `no`), each series was started
  detached on the node (`setsid nohup bash harness/series.sh <list>`), and ssh sessions to the node were kept open for
  the whole series (a keeper loop waiting for `SERIES DONE`, plus the log watcher), so the user manager and the
  `systemd-run --user --scope` units lived for every run. Environment only.
- **N2 (10:50 ET, after `SH-Cp`, before any `Cp2`/`ICp2` run) — §2.8 pacing rule applied.** `SH-Cp`'s K_server samples
  after the baseline had median 58,945,572 B (< 0.5 C = 107 MB) and max 206,309,502 B. By the pre-registered rule every
  `Cp2` and `ICp2` run uses `--last-delay 2` (the list file records it).
- **N3 (10:51 ET, before any reading of the main series) — `summarize.py` column fix.** The first JMX poll of each run
  comes before some metric beans exist and prints extra fields; `summarize.py` now drops rows that do not have the 15
  columns (it had read `HeapMemoryUsage` as the write count in that one row). Summaries were regenerated; no raw log changed.
- **N4 (11:00 ET) — `oomtime.py` (analysis only).** Reads each run's GC log for the OOM time, the first Full GC and the
  Full-GC "after" values before the endpoint, relative to the last connection established. **Revised 11:58 ET** (after
  `P8-1`, before any budget-search reading was written up): the thread that throws the first OOME prints `Dumping heap to`
  and then waits for the VM thread, which keeps running Full GCs for other threads first, so the `HeapDumper` safepoint
  entry is a late bound (`P4-1`: 35 s late; `P8-1`: 122 s late). t_OOM is now the end of the `HeapDumper` safepoint minus
  the dump duration printed in `stdout.txt` (the dump timer starts when the dump is requested), i.e. B14's "exit − dump
  duration" read from the GC log. Both values are given in §3.3.
- **N5 (11:45 ET) — dump wait.** `run.sh`'s hold-end check waited for the 8 GiB dump as designed (`P8-1`: "dump in progress
  at hold end: waiting", 198 s, dump complete, 10,425,566,716 B). In `P4-1` the dump had already finished when the hold
  ended; the JVM then stayed in Full GCs until the shipped `OnOutOfMemoryError` kill ran 58 s after the hold-end SIGTERM.
  No dump was cut.
- **N6 (12:36 ET) — 16 GiB repeats.** `P16-1` reached the endpoint, so per §2.5 (repeats of the largest failing budget,
  "if time") `P16-2` and `P16-3` were run next from `harness/list-p16.txt` (same line as `P16-1`), with their own keeper
  session. No reading affected.

### 3.2 Environment (as run)

`ms0604` (Utah m400, **aarch64**, 8 cores, MemTotal 65,791,808 kB, 8 GiB swap present, Ubuntu 22.04.1, kernel
5.15.0-191-generic), OpenJDK 11.0.33, Python 3.10.12. Tree `/mydata/s4/r13-w1/cassandra` = `cp -a` of
`/mydata/s4/cassandra-base` (469 MB, `diff -rq` empty, `git describe --tags` = `cassandra-5.0.9`); no patch, no rebuild.
`md5sum` in every run (`runs/<id>/conf-md5.txt`, all 21 runs identical): `conf/cassandra.yaml`
`714ee9bf58b3bc1710377ac16bcbba03` (shipped), `jvm11-server.options` `fbad82a853f1b85aea0fa5ea34b6d1bf`, `cassandra-env.sh`
`8be0588e87c594a03360751b1dbf4fbf`; intervention `conf-i/cassandra.yaml` `0149f45cd4eed69d0be60403bf08a055` (= a copy of the
shipped `conf/` + one line `native_transport_max_request_data_in_flight: 16MiB`). JVM (`jcmd VM.flags`): G1,
`G1HeapRegionSize` 16 MiB, `-Xms = -Xmx` = 2/4/8/16 GiB, **`MaxDirectMemorySize` = 16,642,998,272 B (15,872 MiB, auto)** in every
run, shipped `HeapDumpOnOutOfMemoryError` (off only in `P16-*` via `JVM_EXTRA_OPTS`, see below) and
`OnOutOfMemoryError=kill -9 %p`; open files 100,000; `systemd-run --user --scope -p MemorySwapMax=0` (no `MemoryMax`).
**Resolved in-flight limits (JMX `StorageService`, every run, `runs/<id>/resolved.txt`):** global 214,748,364 B / per IP
53,687,091 B at 2 GiB (= §2.3); 16,777,216 / 53,687,091 B with `conf-i`; 4 GiB 429,496,729 B; 8 GiB 858,993,459 B; 16 GiB see
`P16-1`. Every capacity of §2.2 at its shipped default in every P and Cp run (V6); `IP2`/`ICp2` differ only by the one line.
Harness: `harness/` (`client.py`, `run.sh`, `series.sh`, `monitor.sh`, `Jmx.java`, `threadcount.py`, `summarize.py`,
`oomtime.py`, `stw.py`, `excerpt.sh`, `hprof-histo.py`, `hprof_oome_thread.py`; run lists `list-sh.txt`, `list-main.txt`, `list-p16.txt`). Offline
body check (`client.py --bodylen`): P 15,785,009 B with 27,500 / 27,500 key offsets, Cp 15,784,969 B with 32 / 32, 121 segments
each = §2.4. Full logs: `ms0604:/mydata/s4/r13-w1/runs/<run-id>/` (`driver.txt`, `stdout.txt`, `system.log*`, `gc.log*`,
`jmx.csv`, `threads.txt`, `heapinfo.txt`, `completions-p*.txt`, `client-p*.txt`, `summary.txt`, `oome-thread.txt`,
`histo.txt`, `dump.txt`); series logs `runs/series-list-*.txt.log`; excerpts `logs/<run-id>.txt`. Every dump was deleted
after analysis (size and sha256 in `dump.txt` and below).

### 3.3 Runs

Times are seconds after the last connection was established. "t_OOM" = when the first OOME requested the heap dump (N4);
"(dump at …)" = when the VM thread actually began the dump, i.e. how long the JVM kept running Full GCs after the first
OOME. "K" = server `RequestsSize` (5-s JMX samples; under Full-GC thrash the poller stops answering, so the last answered
sample can precede the endpoint) and **K_client** = min(requests with their first segment sent, admitted) × charge.
"decode / exec" = max over the 5-s `Thread.print` samples of event-loop threads in `BatchMessage$1.decode` / NTR threads in
`BatchMessage.execute` (samples taken during Full-GC thrash return empty and are not counted). "Full GCs" = count and the
heap after them (MiB). Responses: every response in every run was `0x2200 Invalid: Batch too large`; there was **no VOID,
no WriteTimeout, no Overloaded** in any run. `ClientRequest,scope=Write` `Latency.Count` stayed at its post-DDL value 1 and
`Timeouts.Count` at 0, MutationStage pending 0 and completed tasks flat at 1, `AllMemtablesHeapSize` of `r13.t` and `r13.big`
0 in every sample of every run: **no arm reached the write path** (O6 never triggered). The number of `Batch for [r13.…]
… (see batch_size_fail_threshold)` ERROR lines in `system.log*` equals the number of responses in every run (IP2: one more,
the request in flight when the hold ended).

| Run | Heap / arm / N | Endpoint | t_OOM (dump at) | K server (last answered) / K_client (B) | decode / exec | Full GCs (after-GC MiB) | Responses | OOME-initiating thread (top frames) |
|---|---|---|---|---|---|---|---|---|
| SH-P | 2 G / P / 1 | survive 90 s | — | 14,736,433 in every load sample | 1 / 1 | 2 (129, 44); young-GC "after" up to 2,014 | 21 (0.23/s; latency 3.6–9.2 s, median 4.0 s) | — |
| SH-Cp | 2 G / Cp / 16, no delay | survive 90 s | — | median 58,945,572, max 206,309,502 ⇒ pacing rule (N2) | 1 / 1 | 0; after-GC ≤ 94 | 3,939 (43.5/s; median 120 ms) | — |
| **P2-1** | 2 G / P / 16 | **heap OOM** | +25.0 (+79.5) | 14,736,433 at +0.6 s, then silent / **206,310,062** (14 of 16 sent) | **14** / 0 | 37 (1,328 → 2,041 ×30); STW 100 % over the last 60 s | 0 (16 resets at the kill) | `CommitLog` sync thread: `Collections.unmodifiableCollection` ← `AbstractCommitLogSegmentManager.getActiveSegments:609` ← `CommitLog.sync:283` (a bystander allocation into the full heap) |
| Cp2-1 | 2 G / Cp / 16, delay 2 s | survive 180 s | — | **206,309,502 in every load sample** (median = cap) | 0 / 1 | 0; after-GC ≤ 110 | 1,235 (6.81/s; median 2.13 s) | — |
| IP2-1 | 2 G / P / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 in every load sample (1 admitted) | 1 / 1 | 3 (316, 99, 171); young "after" up to 2,048 | 37 (0.25/s) | — |
| **P2-2** | 2 G / P / 16 | **heap OOM** | +23.2 (+43.1) | 103,155,031 at +0.6 s / **206,310,062** | **14** / 0 | 30 (1,432 → 2,035 ×24) | 0 | **event loop**: `ArrayList.<init>` ← `CBUtil.readValueList:561` ← `BatchMessage$1.decode:71` ← `CQLMessageHandler.processRequest:390` ← `CQLMessageHandler$LargeMessage.onComplete:834` |
| Cp2-2 | 2 G / Cp / 16, delay 2 s | survive 180 s | — | 206,309,502 in every load sample | 0 / 2 | 0; after-GC ≤ 74 | 1,235 (6.81/s; median 2.15 s) | — |
| IP2-2 | 2 G / P / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 in every sample | 1 / 1 | 4 (259, 292, 400, 106); young "after" up to 2,039 | 38 (0.25/s) | — |
| **P2-3** | 2 G / P / 16 | **heap OOM** | +25.3 (+59.1) | **206,310,062** (cap, at +5 s) / 206,310,062 | **14** / 1 | 27 (1,351 → 2,039 ×20); STW 95 % | 0 | **event loop**: `CBUtil.readRawBytes:669` ← `readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71`; the first `system.log` ERRORs are two more event loops (`epollEventLoopGroup-5-7`, `-5-16`) with OOME at `CBUtil.readBoundValue:480` |
| Cp2-3 | 2 G / Cp / 16, delay 2 s | survive 180 s | — | 206,309,502 in every load sample | 1 / 1 | 0; after-GC ≤ 86 | 1,237 (6.82/s; median 2.16 s) | — |
| IP2-3 | 2 G / P / 16, in-flight 16 MiB | survive 150 s | — | 14,736,433 in every sample | 1 / 1 | 3 (75, 335, 210); young "after" up to 2,048 | 37 (0.25/s) | — |
| ICp2-1 | 2 G / Cp / 16, delay 2 s, in-flight 16 MiB | survive 150 s | — | 14,736,393 in every sample | 0 / 0 | 0; after-GC ≤ 80 | 73 (0.49/s vs 6.81/s in Cp2) | — |
| **P4-1** | 4 G / P / 32 | **heap OOM** | +88.3 (+123.4) | **427,356,557** (= 29 × charge, cap) | **16** / 6 | 50 (3,142 → 4,081) | 0 | NTR: `ImmutableList.copyOf` ← `QueryOptions$OptionsWithColumnSpecifications.<init>:481` ← `BatchQueryOptions$WithPerStatementVariables.prepareStatement:137` ← `BatchMessage.execute:217` |
| **P8-1** | 8 G / P / 64 | **heap OOM** (dump finished in the dump wait, N5) | +210.8 (+332.8) | **854,713,114** (= 58 ×, cap) | **16** / 26 | 43 (6,898 → 8,180) | 0 | dump trigger: logback `AsyncAppenderBase$Worker` (`ArrayList.grow`), a bystander; the first `system.log` OOM ERROR: `Native-Transport-Requests-18` |
| **P4-2** | 4 G / P / 32 | **heap OOM** | +61.8 (+150.2) | 427,356,557 (cap) | **16** / 5 | 59 (3,153 → 4,080) | 0 | **event loop**: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71` |
| **P4-3** | 4 G / P / 32 | **heap OOM** | +56.5 (+99.3) | 427,356,557 (cap) | **16** / 8 | 24 (3,155 → 4,080) | 0 | **event loop**: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71` |
| **P8-2** | 8 G / P / 64 | **heap OOM** (dump finished in the dump wait, 151 s) | +128.3 (+279.4) | 854,713,114 (cap) | **16** / 22 | 36 (6,906 → 8,182) | 0 | **event loop**: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71` |
| **P8-3** | 8 G / P / 64 | **heap OOM** (dump finished in the dump wait, 217 s) | +153.2 (+349.5) | 854,713,114 (cap) | 14 / 24 | 45 (7,015 → 8,190) | 0 | **event loop**: `ByteBuffer.wrap` ← `CBUtil.readBoundValue:480` ← `readValueList:563` ← `BatchMessage$1.decode:71` |
| **P16-1** | 16 G / P / 128, no dump | **heap OOM** (`# java.lang.OutOfMemoryError: Java heap space`, shipped kill at +251 s, inside the 300 s hold) | ≈ +248 (last Full GC ended +247.7) | **1,709,426,228** (= 116 × charge, cap; resolved C 1,717,986,918 / per IP 429,496,729) | 15 / 59 (30 in `getMutations`) | 13 (13,129 → 16,370; 15 s each; STW 99–100 % over the 60/120/180 s before the last GC, `stw.py`) | 0 | not recorded: no dump (by design, §2.3) and the kill came before any `system.log` ERROR |
| P16-2 | 16 G / P / 128, no dump | **GC service loss** for the rest of the hold (STW 99–100 % over the 60/120/180 s before the hold end, `stw.py`; heap 16,292–16,361 MiB after every Full GC from +90 s), no OOM by the hold end (300 s); SIGTERM ignored, SIGKILL by `run.sh` 60 s later | — | 1,709,426,228 (cap) | 14 / 59 (31 in `getMutations`) | 20 (13,071 → 16,361; 14.6–15 s each) | 0 | — |
| P16-3 | 16 G / P / 128, no dump | **GC service loss** for the rest of the hold (STW 100 % over the 60/120/180 s before the hold end; heap 16,287–16,363 MiB after every Full GC from +100 s), no OOM by the hold end; SIGKILL by `run.sh` | — | 1,709,426,228 (cap) | 16 / 39 (19 in `getMutations`) | 19 (12,549 → 16,363) | 0 | — |

Dumps (size B, sha256 prefix; all deleted after analysis): P2-1 2,172,095,943 `04db2462`; P2-2 2,590,125,476 `16d2b3b6`; P2-3
2,100,803,769 `84aede4d`; P4-1 5,285,064,077 `e2121d79`; P8-1 10,425,566,716 `7d1b6f5b`; P4-2 5,271,093,227 `9fd4e8c0`; P4-3 5,143,360,291 `5e7fd983`; P8-2 10,293,563,416 `667985f0`; P8-3 10,229,089,779 `0382c4ce`; P16-* none (no dump by design).

**Holder at failure, P2-1 dump** (`hprof-histo.py --value-len 1`, every record; shallow sizes estimated with the dump's
8-byte ids, so they overstate a compressed-oops heap by ≈ 10–15 %; `harness`, excerpt `logs/P2-1.txt`): 46,000,864
objects, 1,902,365,751 B. `java.nio.HeapByteBuffer` 21,842,057 / 1,201,313,135 B; `byte[]` 22,357,820 / 403,761,348 B, of
which **`byte[1]` 21,001,778** / 357,030,226 B (the tinyint values); `Object[]` 434,303 / 198,703,480 B (value lists);
`ArrayList` 422,411 / 13,517,152 B; **`MD5Digest` 420,059** / 11,761,652 B; `BatchMessage` 1; **`Envelope` 11**; `Mutation`,
`PartitionUpdate` 0 (not in the dump); `BufferCell` 34, `BTreeRow` 8 (system tables). The decoded-request classes
(`HeapByteBuffer` + `byte[1]` + `Object[]` + `ArrayList` + `MD5Digest`) sum to 1,782,325,645 B = **93.7 %** of the dump.
420,059 statement digests = 7.6 requests' worth of 55,000 statements, spread over 11 envelopes still referenced: all held
requests were part-way through decode, none had reached the build. **U vs K:** heap after the Full GCs at the failure
2,035–2,041 MiB (P2-1..3) minus the 32 MiB idle reading before the load ≈ 2,106 MB, against K ≤ 206,310,062 B ≤ C =
214,748,364 B: **U/K ≈ 10.2** from the GC log, 8.6 from the dump's decoded-request bytes (the dump was written 55 s after
the first OOME, when 11 of the 14 admitted requests were still referenced).

**Readings against the §2.7 predictions.**
- `SH-P`: every response `0x2200`, one ERROR line each, latency 3.6–9.2 s (predicted 4–15 s), K = 14,736,433 while in
  flight, write count and memtables flat ✓. Heap after GC during a request: the two Full GCs left 129 and 44 MiB; young
  collections left up to 2,014 MiB (old regions full of completed requests' garbage). Predicted 0.3–0.9 GiB: the live
  part is lower, the young-GC reading higher; neither is an outcome row.
- `SH-Cp`: every response `0x2200` (no VOID / WriteTimeout), 43.5/s ✓, heap after GC ≤ 94 MiB ✓, write count flat ✓;
  K_server median 59 MB < 0.5 C ⇒ the pre-registered pacing rule (N2).
- `P2-*`: **heap OOM 3/3** ✓ at +25.0, +23.2, +25.3 s (predicted within 120 s); K at the cap (server 206,310,062 in P2-3;
  JMX went silent within 1 s of load in P2-1/P2-2, K_client = 14 admitted in all three) ✓; 14 event loops in
  `BatchMessage$1.decode` and 0–1 NTR thread in `BatchMessage.execute` ✓; **0 `Batch too large`** before the OOM ✓; write
  path absent ✓; U/K ≈ 10 ✓ (predicted 8–15). Initiating thread in `CBUtil.readValueList` / `readRawBytes` under
  `BatchMessage$1.decode` in **2/3** (P2-2, P2-3); in P2-1 the throwing thread was the commit-log sync thread, a small
  allocation by a bystander into a heap already full of decoded requests (its own dump: 93.7 % decoded-request classes),
  as B14's T8-3 dump trigger was the JMX thread. P2-1 dump: decoded-request share 93.7 % ≥ 50 % ✓ (expected ≥ 90 % ✓),
  `Envelope` 11 ≤ 14 ✓, `Mutation` 0 ≤ 2 ✓.
- `Cp2-*`: **survive 0/3** ✓ for 180 s with K_server at the cap (206,309,502 B, 14 requests) in **every** load sample
  (the `--last-delay 2` pacing held the charge at the cap); heap after GC ≤ 110 MiB (≤ 0.8 GiB ✓), no Full GC, STW 0 % ✓;
  1,235–1,237 responses, all `0x2200`, 6.8/s ✓ (≥ 5/s); write count flat ✓. Direct memory up to 1,464 MiB (the frames of
  the held requests), far below the 15,872 MiB limit.
- `IP2-*`: **survive 0/3** ✓; K = 14,736,433 in every sample ✓; 37–38 responses per run (0.25/s, ≥ 1 per 15 s ✓; `SH-P`,
  the N = 1 reference, 0.23/s), all `0x2200`. Heap after GC: Full GCs left 75–400 MiB ✓, but young-GC "after" values
  reached 2,039–2,048 MiB (predicted ≤ 1.4 GiB; the same pattern as `SH-P`, garbage of completed requests in old regions
  until the next Full GC); no OOM, STW 5–6 %.
- `ICp2-1`: survive ✓; 0.49 responses/s vs 6.8/s in `Cp2` ✓ (one request at a time, each held ≥ 2 s by the pacing).
- `P4-*`: OOM **3/3** ✓ (+88.3, +61.8, +56.5 s; predicted within 180 s), K at the cap (29 requests), 16 event loops in decode
  + 5–8 NTR threads in `execute` (decoded requests in the build); initiating thread in decode 2/3, in the NTR build
  (`BatchQueryOptions…prepareStatement` ← `BatchMessage.execute`) 1/3.
- `P8-*`: OOM **3/3** within the 300 s hold ✓ (predicted ≥ 2/3; +210.8, +128.3, +153.2 s), K at the cap (58 requests), 14–16
  event loops in decode + 22–26 NTR threads in `execute`; heap 8,114–8,190 MiB after every Full GC before the OOM. Every
  dump finished inside the dump wait (151–217 s after the hold end, N5). Initiating thread in decode 2/3 (P8-2, P8-3), a
  logging bystander 1/3 (P8-1, whose first `system.log` OOM ERROR is an NTR thread).
- `P16-*` (predicted "OOM or GC service loss, uncertain"): **heap OOM 1/3** (P16-1, ≈ +248 s, shipped kill), **GC service
  loss 2/3** (P16-2, P16-3: from ≈ +100 s every collection was a 15 s Full GC leaving 16.3 GiB, STW 99–100 % over the last
  180 s of the hold, no OOM before the hold end). K at the cap (116 requests) in all three; 14–16 event loops in decode and
  39–59 NTR threads in `execute` (19–31 in `getMutations`): at 16 GiB more admitted requests finish decode and wait in the
  build, which slows the heap's last steps into back-to-back Full GCs rather than an allocation failure. RssAnon ≤ 18,990
  MiB, direct ≤ 1,760 MiB.

### 3.4 Per-condition status and V-table

| Condition | Runs | Endpoint n/N | Status |
|---|---|---|---|
| P, 2 GiB, shipped defaults, N = 16 | P2-1..3 | heap OOM 3/3 | `verified-OOM · deployment` (with the V-table below) |
| Cp (matched control), 2 GiB | Cp2-1..3 | 0/3 (survive 180 s, K at the cap throughout) | control |
| P, 2 GiB, in-flight 16 MiB (intervention) | IP2-1..3 | 0/3 (survive 150 s, responses 0.25/s) | intervention |
| Cp, 2 GiB, in-flight 16 MiB | ICp2-1 | 0/1 | diagnostic (cost) |
| P, 4 GiB, N = 32 | P4-1..3 | heap OOM 3/3 | budget search |
| P, 8 GiB, N = 64 | P8-1..3 | heap OOM 3/3 (within the 300 s hold) | budget search: **largest budget with 3/3** |
| P, 16 GiB, N = 128, no dump | P16-1..3 | heap OOM 1/3; GC service loss (STW ≥ 99 % over ≥ 180 s) 2/3 | budget search: boundary (OOM intermittent) |

| | Requirement | Evidence | Met? |
|---|---|---|---|
| V1 | endpoint ≥ 3 clean runs | P2-1, P2-2, P2-3: `OutOfMemoryError: Java heap space` **3/3** at +25.0, +23.2, +25.3 s | yes |
| V2 | nearest surviving control ≥ 3 runs, no endpoint | Cp2-1..3: same path (v5 large message, same admission and charge 14,736,393 vs 14,736,433 B, decode on the event loops, build, rejection by the same `verifyBatchSize` with the same ERROR line), same N, heap, build, conf and instruments; neither arm writes (write count flat, memtables 0, no WriteTimeout). **0/3**, K at the cap (14 requests) in every load sample, heap after GC ≤ 110 MiB, 6.8 responses/s. Only the payload shape differs (192 values, 64 of them 246,599-byte blobs, vs 2.86 M one-byte values) | yes |
| V3 | U measured independently of K | U from the GC log (heap after the Full GCs 2,035–2,041 MiB vs 32 MiB idle) and the P2-1 dump (decoded-request classes 1.78 GB, 93.7 %); K = `RequestsSize` (server) ≤ 206,310,062 B and K_client = 14 admitted ⇒ **U/K ≈ 10 with K ≤ C** | yes |
| V4 | intervention removes the endpoint ≥ 3 runs | IP2-1..3 (in-flight 16 MiB = one request): **0/3**, 37–38 responses per 150 s (0.25/s, = `SH-P`'s N = 1 rate 0.23/s); K = one request in every sample. Every P response is a rejection in every arm, so useful work is the response rate (§2.8) | yes |
| V5 | initiating failure + holder | first OOME in `BatchMessage$1.decode` → `CBUtil.readValueList:561` / `readRawBytes:669` ← `readBoundValue:480` in P2-2 and P2-3 (P2-3's first `system.log` ERRORs: two more event loops at `readBoundValue:480`); P2-1's throwing thread a bystander (commit-log sync) with the same holder in its dump; P2-1 dump 93.7 % decoded-request classes, 11 `Envelope`s ≤ 14 admitted, 0 `Mutation` | yes |
| V6 | constraints at shipped defaults | shipped `cassandra.yaml` md5 `714ee9bf…` in every P / Cp run; resolved in-flight 214,748,364 / 53,687,091 B (JMX); receive queue 1 MiB, max message 16 MiB (derived), `batch_size_fail_threshold` 50 KiB, all defaults | yes |
| V7 | acceptable budget | heap **2 GiB** (the ideal budget; ≥ 512 MiB standing rule), direct auto 15,872 MiB, no container limit. Budget search: 4 GiB OOM 3/3, **8 GiB OOM 3/3** (largest budget failing every time), 16 GiB OOM 1/3 with GC service loss in the other 2/3 (the node would resolve 31,744 MiB) | yes |

## 4. Conclusion (stage 2)

**Verdict: `true positive`.** Protocol status (detail): **`verified-OOM · deployment`**, direction **bypass —
accounting mismatch** (U > C, K ≤ C) of the native in-flight control `native_transport_max_request_data_in_flight`. Frozen
outcome row **O1**. Interpretation: an accounting / configuration-sizing gap (heap/10 of **wire** bytes assumes about one
byte of heap per wire byte; a v5 batch of tiny bound values holds ≈ 10× that while it decodes); not documented as by design.
Platform: aarch64 (Utah m400) only.

**Reason.** With every capacity at its shipped default and a 2 GiB heap, two-partition v5 batches of 55,000 statements ×
52 one-byte/int values (15,785,009 B each) reached `OutOfMemoryError: Java heap space` in **3/3** runs, 23–25 s after the
16 connections were up, before any batch check ran (0 `Batch too large`, no write path touched). The in-flight counter
stayed at or below its limit: 14 admitted × 14,736,433 B = 206,310,062 B ≤ 214,748,364 B. The heap held ≈ 10× that: 2,035–2,041
MiB after every Full GC at the failure (32 MiB idle), and the P2-1 dump is 93.7 % decoded-request objects (21.8 M
`HeapByteBuffer`, 21.0 M `byte[1]`, 420,059 `MD5Digest`, 11 `Envelope`s, no `Mutation`), with 14 event loops in
`BatchMessage$1.decode` and the first OOME in `CBUtil.readValueList` / `readBoundValue:480` (2/3; the third thrown by a
bystander into the same full heap). The matched control C′ — the same 15.78 MB bodies as 64 blobs over two partitions, the
same admission, decode, build and rejection, **K at the cap in every sample** — survived **0/3** with heap after GC
≤ 110 MiB at 6.8 responses/s. Lowering the in-flight limit to one request (16 MiB) removed the endpoint **0/3** at the
N = 1 response rate (0.25/s vs 0.23/s). The endpoint also holds at larger heaps: 4 GiB **3/3** (+56 to +88 s, 29 requests
admitted), **8 GiB 3/3** (+128 to +211 s, 58 admitted, all inside the 300 s hold); at 16 GiB (116 admitted) it is OOM 1/3
and GC service loss (STW ≥ 99 % over ≥ 180 s) 2/3.

**What else the runs show:**
- The holder is the decoded request on the Netty event loops (≤ 16 decode at once, 2 × cores); at 4 and 8 GiB the
  admitted requests that finished decode add a second holder on NTR threads in `BatchMessage.execute` (5–26 threads; one
  4 GiB OOME was thrown there). The OOM happens before `batch_size_fail_threshold` or any write: requests the server
  rejects anyway are enough. B14's control failure (write-timeout backlog) does not occur once neither arm writes.
- After the first OOME the JVM kept running Full GCs for 20–196 s before the dump ran (N4); the shipped
  `OnOutOfMemoryError` kill ended every failing run.
- At 16 GiB (116 admitted, 39–59 NTR threads in the build) the heap reached 16.3 GiB after every Full GC in all three
  runs, but only one allocation failed inside the 300 s hold; the other two sat in 15 s back-to-back Full GCs (STW ≥ 99 %
  over ≥ 180 s), i.e. GC service loss by the default criterion. 8 GiB is the largest heap that failed 3/3; 16 GiB is the
  boundary where the endpoint turns into service loss with intermittent OOM, as B14 saw at 8 GiB.
- Limits: aarch64 m400 only (never pooled with x86); client and server on one node; one source IP per connection, so the
  per-IP limit (heap/40 = 3 requests at 2 GiB) never binds: the 2 GiB endpoint needs ≥ 5 client addresses (14 admitted /
  3 per IP), as a deployment with several application hosts has. `Cp2`/`ICp2` used the pre-registered `--last-delay 2`
  pacing (N2), so their K was held at the cap. JMX stops answering within a second of the load in P runs, so K is read
  from the client side there (and from the server where it answered, P2-3, P4-*, P8-*).

**What a better design would add (not needed for the verdict):** the same arms on x86 (`pc91`…), where decode is faster,
to show the share of the endpoint that depends on decode speed; and a control that varies only the value count at fixed
wire bytes (e.g. 8-byte values) to map the expansion factor per value size.
