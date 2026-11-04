# batch_size_fail_threshold — mutation batch

> **Index:** [../_INDEX.md](../_INDEX.md)
>
> **Source:** apache/cassandra @ tag `cassandra-5.0.9`

**Estimate: negative** (Rule 3, recorded in `predicted-negative.md`, batch "the capacity-word pass": the check runs after the batch's mutations are fully built, so it does not gate object creation). This file writes the negative estimate up with a test of the opposite claim: that `batch_size_fail_threshold` does **not** cap the memory a node uses to handle a batch.

## 1. Location

| Field | Content |
|-------|---------|
| **Case ID** | BATCH_SIZE_FAIL_THRESHOLD-VERIFYBATCHSIZE-FAILTHRESHOLD |
| **Constraint** | `batch_size_fail_threshold` — configuration entry (`cassandra.yaml`, default 50 KiB), live-settable (JMX `setBatchSizeFailureThreshold`) |
| **Enforcement pattern** | (c) guard before the write path proceeds — but placed after the batch's mutations are built (the reason it was rejected) |
| **Capacity check** | [`BatchStatement.verifyBatchSize():352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L352) — `size > failThreshold` |
| **Decision point** | the same line: throws `InvalidRequestException("Batch too large")` at [`BatchStatement.java:358`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L358), else the batch proceeds to `StorageProxy.mutateWithTriggers` |
| **Allocation site** | the mutations are built before the check, in [`BatchStatement.execute():428`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L428) (`getMutations(...)`) |
| **Related cases** | [`local_read_size_fail_threshold…`](local_read_size_fail_threshold-addSize-failBytes--guided.md), [`coordinator_read_size_fail_threshold…`](coordinator_read_size_fail_threshold-shouldReject-thresholdBytes--guided.md) (read-side siblings), [`max_mutation_size…`](max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md) |

```java
// BatchStatement.execute: the mutations exist before the size is checked
executeWithoutConditions(getMutations(clientState, options, false, timestamp, nowInSeconds, requestTime),
                         options.getConsistency(), requestTime);
// executeWithoutConditions
verifyBatchSize(mutations);
// verifyBatchSize
long size = IMutation.dataSize(mutations);
if (size > warnThreshold) { ... if (size > failThreshold) { ...; throw new InvalidRequestException("Batch too large"); } }
```

## 2. Context

A CQL batch groups several writes. A very large batch is a risk to the coordinator, so Cassandra warns above a size and fails above a larger one. The failure is raised after the coordinator has already turned the statements into in-memory mutations, so it protects the replicas and the commit log from the batch more than it protects the coordinator's own memory.

## 3. Module

| Field | Content |
|-------|---------|
| **Module** | CQL write path (`cql3/statements`) |
| **One-line role** | Executes client CQL statements on the coordinator, including batches. |

## 4. Capacity check & limit

| Field | Content |
|-------|---------|
| **Is this a capacity check?** | yes for the bytes of one batch; partial for the node, because it is a per-request cap and the check runs late |
| **Usage-side operand** | `size` — the summed `dataSize()` of the batch's partition updates ([`IMutation.dataSize():63`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java#L63)) |
| **Limit-side operand** | `DatabaseDescriptor.getBatchSizeFailThreshold()` |
| **Limit type** | Configuration entry |

**Limit initialization path:**

1. [`Config.batch_size_fail_threshold:332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L332) — declared, default `50KiB`
2. [`DatabaseDescriptor.getBatchSizeFailThreshold():2071`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2071) — `toBytesInLong()`
3. [`DatabaseDescriptor.setBatchSizeFailThresholdInKiB():2091`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2091) — live setter, reached through [`StorageService.setBatchSizeFailureThreshold():6833`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6833)
4. [`verifyBatchSize():349`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L349) — read at the comparison

## 5. Decision point & branch semantics

| Field | Content |
|-------|---------|
| **Decision point** | [`BatchStatement.verifyBatchSize():352`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L352) |
| **Verdict** | n/a |

| Outcome | Condition | Effect |
|---------|-----------|--------|
| **Allow** | `size <= failThreshold` (and a warning above `batch_size_warn_threshold`) | the batch goes on to `StorageProxy.mutateWithTriggers` |
| **Disallow** | `size > failThreshold` | logs an error, traces, throws `InvalidRequestException("Batch too large")` |

**Not reached for:** a batch of one mutation ([`BatchStatement.java:334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L334) returns early), and conditional (LWT) batches, which take `executeWithConditions` ([`BatchStatement.java:423`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L423)) and never call `verifyBatchSize`.

## 6. Code path

### 6a. Allow path → object creation

1. [`execute():428`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L428) — `getMutations(...)` builds every mutation of the batch on the coordinator heap
2. [`executeWithoutConditions():439`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L439) — `verifyBatchSize(mutations)` runs; the size is under the limit
3. `StorageProxy.mutateWithTriggers` sends the mutations to replicas, where they enter the commit log and memtable (bounded by the memtable and commit-log limits, not by this one)

### 6b. Disallow path effect

The check throws, so replicas never see the batch. The coordinator's mutations are already built and become garbage on return. Nothing is released early: the memory was spent before the check.

## 7. Object & resource

| Field | Content |
|-------|---------|
| **Object created** | the batch's `Mutation` objects and their partition updates, on the coordinator |
| **Resource consumed** | heap on the coordinator (and, past the check, replica memtable and commit-log bytes) |
| **Rough sizing** | about the batch's `dataSize()` plus per-object overhead; the request body also sits in a native-transport buffer until the statement runs |
| **Lifetime / release** | until the request completes (rejected or written) |

## 8. Maximum memory/disk bound

By the rejection's reading, the threshold bounds what reaches the replicas, not what the coordinator holds: a rejected batch is built in full first, so coordinator heap per rejected batch scales with the batch size, not with the threshold. The transport's own limits (`native_transport_max_message_size`, `native_transport_max_request_data_in_flight`) cap the request before it reaches this code; the threshold changes only the accept/reject decision.

## 9. Test design (guidance for stage 4)

**Stage 3 writes this section; stage 3 never runs it.** No measured numbers and no verdict are recorded here.

### 9a. Procedure and conclusions

**Testability:** config, live-settable (JMX `StorageService.setBatchSizeFailureThreshold`).

**Claim under test (the rejection):** `batch_size_fail_threshold` does not bound the coordinator memory spent on a batch; for a batch above the threshold, the heap allocated while handling it follows the batch's size, not the threshold.

**How this verifies the hypothesis:**

- **Hypothesis:** the check runs after the mutations are built, so allocation per rejected batch is independent of the threshold.
- **Test:** vary the threshold over 50 KiB (default), 500 KiB and 5 MiB; send unlogged multi-partition batches of 1 MiB, 4 MiB and 16 MiB; read the coordinator thread's allocated bytes per request and whether the batch was rejected.
- **Logic:** (1) rejection happens exactly when the batch size passes the threshold (else the run is invalid); (2) allocated bytes per request are read at each (threshold, size) pair; (3) a positive control lowers `native_transport_max_message_size` below the request size, where a cap that binds before the build must cut allocation; (4) the claim is confirmed only if allocation tracks the batch size while the threshold has no effect on it and the control cuts it.
- **Refuted if:** allocation for a rejected batch falls as the threshold falls, or stays under a bound set by the threshold.

**Procedure:**

1. **Unit tier** — call `BatchStatement.execute` on a prepared multi-partition batch with a controlled `DatabaseDescriptor` threshold, and read `ThreadMXBean.getThreadAllocatedBytes` for the calling thread around the call.
2. **Cluster tier** — one node; send the batches over the native protocol and read the coordinator's allocation from a Byteman rule or JFR allocation events; confirm the rejection from the client error and the log line.
3. **Positive control** — repeat the 16 MiB batch with `native_transport_max_message_size` lowered below the request size.
4. **Compare** with the prediction.

**Prediction (what the rejection claims):** for a batch above the threshold, allocated bytes per request are within the noise band of each other across thresholds and grow with batch size; the batch is rejected iff size > threshold; the positive control lowers allocation.

**Conclusions:**

| Result | Conclusion |
|---|---|
| Rejected batches allocate about the same bytes at every threshold and the allocation grows with batch size; the control cuts it | **Confirmed** — the threshold does not bound coordinator memory. |
| Allocation per rejected batch falls with the threshold | **Refuted** — usage follows the threshold; the check or something derived from it runs before the build. |
| Allocation is flat in both threshold and batch size | **Not confirmed** — the instrument or workload is not seeing the build; rerun. |
| Allocation is flat but the positive control does not cut it | **Not confirmed** — the instrument cannot see a cap that binds. |
| No batch reaches the threshold | **Invalid run** — raise the batch size or lower the threshold. |

### 9b. Setup

| Field | Content |
|-------|---------|
| **Constraint knob** | JMX `StorageService.setBatchSizeFailureThreshold(<KiB>)` (live); yaml `batch_size_fail_threshold` (restart). |
| **Confirm it took effect** | JMX `getBatchSizeFailureThreshold`, and the rejection's log line "exceeding specified threshold of …". |
| **Capacity values** | 50 KiB (default), 500 KiB, 5 MiB. Keep `batch_size_warn_threshold` below the threshold (`setBatchSizeWarnThreshold`). |
| **Scope** | Per request; node-wide use is `threshold × concurrent batches`, so send one batch at a time. |
| **Level** | Unit and cluster. |

**Hold fixed:**

| Setting | Value | Why |
|---|---|---|
| `native_transport_max_message_size` | 64 MiB except in the control (**amended 2026-10-20, R1:** with `native_transport_max_request_data_in_flight` and `…_per_ip` both 256 MiB; the filed 256 MiB would fail at startup) | keeps the transport from rejecting first |
| batch type | `UNLOGGED`, 64 partitions per batch | removes batchlog writes, keeps `mutations.size() > 1` |
| heap | `-Xms4G -Xmx4G` | removes sizing as a variable |
| concurrency | 1 client, 1 request in flight | one batch per measurement |

**Controls:** an idle node, a batch below the threshold (accepted), and the positive control.

**Reset between runs:** none needed; restart the node between threshold values if allocation counters are read process-wide.

### 9c. Workload

```bash
# cluster tier: batches of B MiB, 64 partitions, value size B/64
python3 harness/send_batches.py --size-mib <1|4|16> --partitions 64 --count 20
```

Unit tier: the same batch through `BatchStatement.execute` in a `CQLTester`-based test.

### 9d. Observables

| Observable | How to read it | When to sample | Trap |
|---|---|---|---|
| **Disallow evidence** | the client's "Batch too large" error and the log line "exceeding specified threshold" | per request | Produced only by this check ([`BatchStatement.java:358`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L358)). |
| **Allocated bytes per request** — the real resource | Byteman rule on `BatchStatement.execute` entry/exit reading `ThreadMXBean.getThreadAllocatedBytes`; or JFR allocation events | per request | The request body is decoded on a netty thread; read the executing thread only, and note the decode separately. |
| **Heap high-water** | `jcmd <pid> GC.heap_info` after a forced GC between requests | after each batch | One batch at a time, or GC noise swamps it. |

### 9e. Running the scenarios

1. **Control run** — default threshold, a 16 KiB batch (accepted); record allocation.
2. **Scenario A — default threshold** — 1, 4 and 16 MiB batches; all rejected; record allocation per size.
3. **Scenario B — vary the threshold** — repeat at 500 KiB and 5 MiB; the 1 MiB batch is accepted at 5 MiB.
4. **Scenario C — positive control** — set `native_transport_max_message_size` to 512 KiB, send the 16 MiB batch; the transport must discard it; record allocation.

### 9f. Stage-4 audit amendments (2026-10-20)

Made at the step-0 audit, before any run or reading; each is a dated change that leaves the claim, the prediction and the conclusions table as filed (results file §1.1 gives the reason for each). Where one corrects a number or a procedure above, this block governs.

- **R1 (9b: transport settings).** With `-Xmx4G` the defaults are `native_transport_max_request_data_in_flight` = heap/10 (about 410 MiB) and `…_per_ip` = heap/40 (about 102 MiB), and `native_transport_max_message_size` may not exceed either (`DatabaseDescriptor.java:911-915`); the derived default is `min(max_mutation_size, both)` = 16 MiB, which would refuse the 16 MiB batch at the transport. Set in the yaml (restart) `native_transport_max_request_data_in_flight` and `native_transport_max_request_data_in_flight_per_ip` to 256 MiB and `native_transport_max_message_size` to 64 MiB for every arm except the control, which lowers `native_transport_max_message_size` to 512 KiB.
- **R2 (9d: control reading).** A request the transport discards never reaches `BatchStatement.execute`, so the executing thread's allocation is trivially 0 there. For the control also read the networking pool `Size` delta (`BufferPool,scope=networking,name=Size`) and the heap high-water; the control's effect is on retained and decoded buffers.
- **R3 (9a: "within the noise band", "falls").** At a fixed batch size, "the same" means the medians of the 20 requests at the three thresholds differ by less than 10 % of one another; "falls with the threshold" means the median at 50 KiB is more than 50 % below the median at 5 MiB.
- **R4 (9c: protocol).** All arms use native protocol v5 (the control's discard is the v5 large-message path; v4 and older fall under `native_transport_max_frame_size`, `Envelope.java:429`). Reuse the in-tree `SimpleClient` of the closed `native_transport_receive_queue_capacity` harness.
- **R5 (9a: which pairs the prediction covers).** At the 5 MiB threshold the 1 MiB and 4 MiB batches are accepted, not rejected. The prediction is read on the rejected pairs only: 50 KiB and 500 KiB with 1, 4 and 16 MiB, and 5 MiB with 16 MiB. The accepted pairs are read to show that the allocation includes the build.

**Step-1 amendments (2026-10-20),** made while writing the harness, from the source only, before any run or reading (results file §1.1 and §3). They leave the claim, the conclusions rows and R3's numeric edges as filed; they change where "allocated bytes per request" is read and how the unit tier reaches the check.

- **R7 (9a Test and Prediction, 9d: where a batch's bytes are allocated).** The bound values are copied to the heap when the request is decoded, on the connection's event-loop thread: `BatchMessage$1.decode` ([`BatchMessage.java:71`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/BatchMessage.java#L71)) → `CBUtil.readValueList` → `readBoundValue` → `ByteBuffer.wrap(readRawBytes(cb, length))` ([`CBUtil.java:480`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CBUtil.java#L480)). The cells `getMutations` builds wrap those buffers without a copy ([`UpdateParameters.java:172`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UpdateParameters.java#L172)), so the executing thread's allocation inside `BatchStatement.execute` holds only the build's per-object overhead (64 partitions in every arm) and cannot grow with the batch's bytes, whatever the threshold does. Read alone, it would land on the "flat in both" row for a reason that has nothing to do with the claim. **"Allocated bytes per request" in 9a is therefore the coordinator's allocation for the request:** the event-loop thread's bytes during `BatchMessage$1.decode` plus the executing thread's bytes during `BatchMessage.execute` (which contains `BatchStatement.execute`, `verifyBatchSize` and, for an accepted batch, the hand-off to the write path). Each comes from one Byteman line per request (`harness/<stem>/batch-alloc.btm`). The rows of 9a are matched on this sum. The 9d reading as filed (the executing thread inside `BatchStatement.execute`) is recorded beside it as a secondary reading and does not select a row. Not measured on either thread: an accepted batch's local apply, which runs on the `MUTATION` stage, and the frame bytes held in the networking pool before the decode (the pool is read per arm, R2).
- **R8 (9a Procedure 1: unit tier).** The unit tier sends the same batches over protocol v5 to `CQLTester`'s in-process server (`requireNetwork()`, `SimpleClient`), with the same Byteman rules, instead of calling `BatchStatement.execute` from the test thread. A direct call would skip the decode (R7) and could not run the positive control. The test raises `native_transport_max_message_size` to 64 MiB with `DatabaseDescriptor.setNativeTransportMaxMessageSizeInBytes` (the unit yaml's derived default is 2.5 MiB, half its 5 MiB commit-log segment), sets the threshold with `setBatchSizeFailThresholdInKiB`, and runs the control by lowering the message size to 512 KiB with the same setter, which the large-message path reads per message ([`CQLMessageHandler.java:551`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/CQLMessageHandler.java#L551)). The values, sizes, counts and arms are those of the cluster tier (9e).

## 10. Provenance

| Field | Content |
|--------|---------|
| **Estimate** | `negative` |
| **Ground** | Rule 3: the check does not gate object creation, it rejects an already-built batch post hoc |
| **Autonomous reference** | none |
| **Stage-3 feed** | 3b (capacity-word pass, recorded in `predicted-negative.md`) |
| **Filed by / Date** | guided agent session, 2026-10-19 |
| **Line numbers checked** | 2026-10-19 against `cassandra-5.0.9` |
| **Escape hatch / Target-3 note** | single-mutation batches and conditional batches are never checked (§5) |
| **Stage-4 feedback** | **2026-10-20, run 1, both tiers: Confirmed — does not cap** ([results](../../stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided.md)). A rejected batch's coordinator allocation (decode + execute, R7) is 2.48 / 8.77 / 33.93 MB at 1 / 4 / 16 MiB on the cluster tier, the same within 0.6 % at thresholds 50 KiB, 500 KiB and 5 MiB (unit within 1.0 %). The disallow branch fired for exactly the 140 batches above the threshold (client error, `rej` trace line and log line each). The positive control (`native_transport_max_message_size` 512 KiB) cut the allocation to 0. The negative estimate stands. **Correction to R7 (9f) and to §6b:** the build inside `BatchStatement.execute` does allocate the batch's bytes. `getMutations` serializes every mutation for `Mutation.validateSize` (`SingleTableUpdatesCollector.toMutations:112` → `Mutation.validateSize:171` → `serializedSize`, a JFR diagnostic), so a rejected batch costs about 2 × its bytes of heap before the check: one copy at decode and one serialization. R7's filed reasoning that the build "cannot grow with the batch's bytes" was wrong. Both readings select the same 9a row, and §9 is left as frozen (hash `a7fa623e…`). Side observation: on a v5 connection the large-message frame buffers stayed in the networking pool's overflow (1.32 GB after 220 batches, never released), the retention the `networking_cache_size` results recorded. |
| **Notes** | The rejection reasons that the check is post hoc; the same shape as the filed `coordinator_read_size_fail_threshold`, which qualified on the half of its check that withholds work. Here no work is withheld on the coordinator, so the rejection stands on the source; the test settles it on measured bytes. Pilot of the rejected-entry write-up. |

---

## 11. Notes

- The first rejection line in `predicted-negative.md` for this check (`BatchStatement.java:352`, "line corrected 2026-09-28, recorded as `:349`") already carries the corrected line.
