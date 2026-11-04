# batch_size_fail_threshold — verification solution  <!-- file: cases/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`BatchStatement.java:334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L334) (`if (mutations.size() <= 1) return;`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string n/a), 2026-10-26; Band D triage mode |
| Estimate | `positive` (scoped): a batch that spans more than one mutation and whose summed `PartitionUpdate.dataSize()` is above `batch_size_fail_threshold` is rejected before `StorageProxy.mutateWithTriggers`. So it adds nothing to memtables, the commit log or the batchlog. The target line exempts batches of at most one mutation (one partition key per keyspace), and those are not capped at all. |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `batch_size_fail_threshold`, a configuration entry.
- Declared at [`Config.java:331-332`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L331-L332) as a `DataStorageSpec.IntKibibytesBound` with default `50KiB`. The old name `batch_size_fail_threshold_in_kb` is still accepted (`@Replaces`).
- Sibling entries: `batch_size_warn_threshold` with default `5KiB` ([`Config.java:329-330`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L329-L330)) and `unlogged_batch_across_partitions_warn_threshold` with default 10 ([`Config.java:334`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L334)).
- Shipped yaml: `conf/cassandra.yaml:1842-1844`, which says "Fail any multiple-partition batch exceeding this value".
- Read through `DatabaseDescriptor.getBatchSizeFailThreshold()`, which returns bytes ([`DatabaseDescriptor.java:2069-2071`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L2069-L2071)).
- Can be changed at runtime with `DatabaseDescriptor.setBatchSizeFailThresholdInKiB` (`:2089-2091`), which is exposed over JMX as `StorageService.setBatchSizeFailureThreshold` ([`StorageService.java:6833`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6833), MBean [`StorageServiceMBean.java:1043`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageServiceMBean.java#L1043)). A yaml change needs a restart; a JMX change does not.


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../../../stage3-ai-deep-read/README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** The quantity compared is `IMutation.dataSize(mutations)`, the sum of `PartitionUpdate.dataSize()` over every partition update in the batch (`src/java/org/apache/cassandra/db/IMutation.java:63-72`). That is the cell data size, not the serialized size.
- What it protects is per-batch write volume: memtable heap or off-heap space, commit-log bytes, and for logged batches the `system.batches` row written before the batch is applied.
- It is a per-request cap. It is not a cap on the node's total usage.

**A3. Mechanism.**
1. `BatchStatement.execute` calls `getMutations` ([`BatchStatement.java:428`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L428)). That builds every `IMutation` on the coordinator heap (`:270-324`). Mutations are grouped by keyspace and partition key, so one partition key gives one mutation.
2. `executeWithoutConditions` calls `verifyBatchSize(mutations)` (`:439`).
3. Target `:334`: if `mutations.size() <= 1`, the method returns and no threshold is checked (CASSANDRA-10876).
4. Otherwise `size = IMutation.dataSize(mutations)` (`:338`).
   - If `size > warnThreshold` (`:340`) and `size > failThreshold` (`:352`), the code traces, logs an ERROR and throws `InvalidRequestException("Batch too large")` (`:354-358`).
   - Above warn but not above fail, it only warns (`:360-365`).
   - The fail check sits inside the warn check. If an operator sets warn above fail, batches between the two values are not rejected.
5. Only after that does it call `StorageProxy.mutateWithTriggers` (`:445`; [`StorageProxy.java:1116`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1116)). For a logged batch that path is `mutateAtomically` ([`StorageProxy.java:1173`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageProxy.java#L1173)), which writes the batchlog (`:1223`, `:1286-1301`).

Bypasses:
- The target line itself: a single-partition batch of any size is accepted. It is capped only by `max_mutation_size`, `Mutation.validateSize` ([`Mutation.java:169-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L169-L175)), which defaults to half of `commitlog_segment_size` ([`DatabaseDescriptor.java:898-899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L899); `conf/cassandra.yaml:660` gives 32MiB).
- Conditional batches go to `executeWithConditions` ([`BatchStatement.java:422-423`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchStatement.java#L422-L423)) and never call `verifyBatchSize`.
- Batches that update virtual tables (`:425-426`) also skip it.
- Internal batches skip it too: `executeLocally` and `executeInternalWithoutCondition` (`:559-570`).
- Overshoot before the check: the whole batch is already on the coordinator heap (step 1) when it is checked.

**A4. Other consumers.** Other writers to the same memtables and commit log:
- non-batch writes,
- hints,
- other tables,
- compaction, which uses disk.

Request size on the native transport is bounded separately by the transport frame and in-flight limits.

**A5. Evidence beyond the source.**
- The yaml comment at `conf/cassandra.yaml:1837-1844`.
- CASSANDRA-10876, cited in the code at `BatchStatement.java:333`: https://issues.apache.org/jira/browse/CASSANDRA-10876

## B. Verification solution

**B1. Claim under test.** For a non-conditional CQL batch spanning two or more partitions, the data the node persists from that batch follows `batch_size_fail_threshold`:
- If the summed `dataSize` is at most F, the batch is applied in full.
- If it is above F, nothing from the batch reaches the memtable, the commit log or an sstable.

A batch on a single partition is not subject to F at all, which is the effect of the target line.

### B2. Unit tier

**B2a. Environment and build.**
1. On local disk: `export WORK=/local/$USER/c509 && git clone /path/to/shared/cassandra-src $WORK/cassandra && cd $WORK/cassandra && git checkout cassandra-5.0.9`.
2. Use JDK 11: `export JAVA_HOME=/usr/lib/jvm/java-11-openjdk`.
3. Build with `ant jar`.
4. Add the test file `$WORK/cassandra/test/unit/org/apache/cassandra/cql3/BatchFailThresholdProbeTest.java`, which extends `org.apache.cassandra.cql3.CQLTester`.
5. Run it with `ant testsome -Dtest.name=org.apache.cassandra.cql3.BatchFailThresholdProbeTest`. The default test JVM options are fine.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** `/local` does not exist on the advisor's machine
> (`stage4-runtime-verification/environment-advisor.md`). Clone: `source ~/Library/Caches/stage4/env.sh` (JDK 11), then
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run32` and `ant -Dlocal.repository=$W/m2 build-test` (every
> `ant` call takes `-Dlocal.repository=$W/m2`). The probe lives in
> `stage4-runtime-verification/harness/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous/BatchFailThresholdProbeTest.java`;
> `unit-run.sh` in the same folder copies it into the clone, runs it and removes it (step 4–5 above).

**B2b. Knobs.** F is set with `DatabaseDescriptor.setBatchSizeFailThresholdInKiB(F)` in `@Before`, together with `setBatchSizeWarnThresholdInKiB(1)` so that warn is below fail. Values:
- F = 50 (the default)
- F = 200 (a raised cap, to show the boundary moves with the knob)

> **Amendment B2b (2026-10-26, stage-4 audit, before any reading).** A third value, **F = 100**, is added, so the knob takes
> three values including the default (group A). Order: F = 50, 100, 200. After setting F and warn, the probe prints a read-back
> line `PROBE readback F=<F> failBytes=<getBatchSizeFailThreshold()> warnBytes=<getBatchSizeWarnThreshold()>`; it must show
> `failBytes = 1024·F` and `warnBytes = 1024`. This is a plain configuration check, not a guardrail, so there is no superuser
> exemption (`BatchStatement.java:332-366`) and the test's default client is fine.

**B2c. Workload.** Table: `CREATE TABLE %s (k int, c int, v blob, PRIMARY KEY (k, c))`. The blob `v` holds B random bytes.
- **Multi-partition batch:** `BEGIN BATCH INSERT ... (k=1,c=0,v=?); INSERT ... (k=2,c=0,v=?); APPLY BATCH`. Its dataSize is about 2·B plus some tens of bytes (clustering, timestamps, liveness).
- **Single-partition batch:** the same, but with k=1 and c=0 and c=1. That is one mutation.
- B values in KiB: 10, 24, 26, 60, 98, 102. These give dataSize of about 20, 48, 52, 120, 196 and 204 KiB, which brackets both F values.
- All requests go through the client path, `executeNet(ProtocolVersion.CURRENT, query, bb1, bb2)`, so that `BatchStatement.execute` → `verifyBatchSize` runs. `execute()` is the internal path and bypasses the check (A3).

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).** As written the probe cannot run:
> 1. `CQLTester.formatQuery` is `String.format(query, "<ks>.<table>")` with **one** argument (`CQLTester.java:1598-1602`), so a
>    batch text with two `%s` throws `MissingFormatArgumentException`. The probe writes the table as `%1$s` in both inserts:
>    multi `BEGIN BATCH INSERT INTO %1$s (k, c, v) VALUES (1, 0, ?); INSERT INTO %1$s (k, c, v) VALUES (2, 0, ?); APPLY BATCH`,
>    single the same with `(1, 0, ?)` and `(1, 1, ?)`.
> 2. `executeNet` needs the native server: `@BeforeClass` calls `requireNetwork()` (`CQLTester.java:613-616`).
> 3. B2d(i)'s `QueryProcessor.parseStatement(String, ClientState)` already returns a prepared `CQLStatement`
>    (`QueryProcessor.java:372-375`), which has no `prepare` method; the probe casts its result to `BatchStatement` directly.
> 4. bb1 and bb2 are B·1024 bytes from `java.util.Random` with a fixed seed (new bytes per case), so the run repeats exactly.
> 5. One loop over F (B2b order) × B (10, 24, 26, 60, 98, 102) × shape (multi, single) = 36 cases, in that nesting. Per case:
>    `TRUNCATE %s` (internal), operand (B2d i), memtable before, `executeNet`, rows and memtable after. Each case prints one line,
>    with `System.out.println(String.format(...))`:
>    `PROBE F=<F> B=<B> shape=<s> mutations=<n> dataSize=<bytes> rejected=<true|false> msg=<exception message or -> rows=<n> memDelta=<bytes>`.
>    A non-"Batch too large" exception is caught and printed in `msg`; the loop goes on. The last line is `PROBE done cases=<n>`.

**B2d. Observables and instruments.**
- **(i) The operand.** Parse the batch: `BatchStatement bs = (BatchStatement) QueryProcessor.parseStatement(formatQuery(q), ClientState.forInternalCalls()).prepare(ClientState.forInternalCalls())`. Bind values through `QueryOptions.forInternalCalls(ConsistencyLevel.ONE, List.of(bb1, bb2))`. Then call `bs.getMutations(ClientState.forInternalCalls(), BatchQueryOptions.withoutPerStatementVariables(opts), false, FBUtilities.timestampMicros(), FBUtilities.nowInSeconds(), Dispatcher.RequestTime.forImmediateExecution())` and pass the result to `IMutation.dataSize(...)`. Record the mutation count and the size.
- **(ii) The outcome.** Record whether an `InvalidQueryException` with message "Batch too large" is raised.
- **(iii) Persisted rows.** `SELECT count(*) FROM %s` after each case. Truncate between cases.
- **(iv) Memtable bytes.** `getCurrentColumnFamilyStore().getTracker().getView().getCurrentMemtable().getLiveDataSize()`, before and after.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** `rejected=true` means `executeNet` threw; the message is
> printed and must be `Batch too large` for a rejection to count as the check's (B2f). The forked test JVM writes stdout and the
> server's log to `build/test/logs/**/TEST-org.apache.cassandra.cql3.BatchFailThresholdProbeTest.log`, one line per write; that
> file is the observable. **(v) Disallow evidence:** the number of `ERROR` lines in that log containing
> `(see batch_size_fail_threshold)` (`BatchStatement.java:356-357`) must equal the number of rejected cases. Gap named: (iv) is
> the memtable's own accounting of cell data, not the live heap, and the coordinator heap that holds the built mutations before
> the check (A3, overshoot) is not measured. The commit log is not read in this tier.

**B2e. Procedure.**
1. Write the test with one `@Test` per (F, B, shape) combination, or a loop that logs `F,B,shape,mutations,dataSize,rejected,rows,memtableDelta` to stdout.
2. Run `ant testsome ...`.
3. Collect the lines from `build/test/output/` or the console.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Run `harness/.../unit-run.sh` with no argument (as
> `source ~/Library/Caches/stage4/env.sh; C=$W/cassandra-run32 unit-run.sh`). It copies the probe into
> `test/unit/org/apache/cassandra/cql3/`, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.BatchFailThresholdProbeTest`,
> copies the test log (B2d) and the Ant log to `$W/logs/<stem>/unit/`, extracts the `PROBE` lines, and removes the probe and its
> classes so the clone's `git status` is clean. A shakedown may pass `-Dprobe.f=<list>` and `-Dprobe.b=<list>` (comma-separated
> KiB) through `-Dtest.jvm.args`; run 1 uses no argument, i.e. the filed values.

**B2f. Predictions.**

Multi-partition batch (mutations = 2):

| F (KiB) | Batches accepted | Batches rejected |
|---|---|---|
| 50 | B = 10 and 24 (dataSize ≤ about 49 KiB): rows +2, memtable delta ≥ 2·B | B ≥ 26: rows +0, memtable delta 0 |
| 200 | B ≤ 98 | B = 102 |

Single-partition batch (mutations = 1): every B, including 102 at F = 50, is accepted, with rows +2 and memtable delta ≥ 2·B.

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** Exact forms (B and F in KiB; bytes = 1024·KiB):
> - **Operand (validity):** `mutations` = 2 for multi and 1 for single; `dataSize` within [2048·B, 2048·B + 256] for both shapes
>   (two cells of B·1024 value bytes plus per-row and per-partition fields of tens of bytes, `AbstractCell.java:120-127`,
>   `BTreeRow.java:522-529`, `PartitionUpdate.java:346-349`).
> - **Rule:** a case is rejected, with message `Batch too large`, **if and only if** `mutations ≥ 2` and `dataSize > 1024·F`,
>   using the measured `dataSize`. A rejected case has rows = 0 and memDelta = 0 exactly; an accepted case has rows = 2 and
>   memDelta ≥ 2048·B.
> - From the bound above, multi is rejected for B ≥ 26 at F = 50, for B ≥ 60 at F = 100 (accepted B ≤ 26), and for B = 102 at
>   F = 200; single is accepted at every (F, B). Rejected cases: 4 + 3 + 1 = 8 of 36.
> - (v): exactly 8 `ERROR … (see batch_size_fail_threshold)` lines in the test log.
> - Read-back lines as in amendment B2b; the test ends `PROBE done cases=36` and Ant reports no failure or error.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| The rejection boundary sits at dataSize ≈ F for both F values, and rejected batches leave rows and memtable unchanged | Claim confirmed for multi-partition batches |
| A multi-partition batch with dataSize > F is accepted, or leaves rows or memtable bytes behind | Claim wrong |
| A single-partition batch with dataSize > F is rejected | The target line does not exempt as traced, so the trace is wrong |
| The boundary does not move between F = 50 and F = 200 | The knob is not effective; claim wrong |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above: row 1 **Confirmed**
> (it needs every case to follow the amended B2f rule at all three F, with (v) equal to the number of rejections); rows 2, 3
> and 4 **Refuted**. Rows added so every plausible outcome has one:
>
> | Observation | Meaning |
> |---|---|
> | A read-back differs from the set value, an operand is outside the B2f bound or has the wrong mutation count, or fewer than 36 cases ran | **Invalid** run (fix the instrument as a runbook defect and restart the tier) |
> | A multi batch with dataSize ≤ 1024·F is rejected, or a rejection's message is not `Batch too large` | Something other than F binds; **Not confirmed** |
> | Rejections follow the rule but (v) does not equal the number of rejections | Disallow branch not shown directly; **Not confirmed** |
> | A rejected case leaves rows = 1 (partial application) | Claim wrong; **Refuted** (as row 2) |
> | No row fits | Feedback to stage 3; no verdict |
>
> **Effect rule:** row 1 with every single-partition case accepted → **caps only on some paths (bypass)** (the multi-partition
> batch is capped; the single-partition batch, B1's own exemption, is not). Row 3 alone with row 1's multi part holding →
> Refuted, Effect **caps**. Rows 2 or 4 → Effect **does not cap**. Invalid / Not confirmed → **undetermined**.

**B2h. Controls.**
- The F = 200 run shows that the same batches are applied when the cap is higher, so a rejection really comes from F and not from some other limit.
- Keep warn at 1 KiB so that the nesting in A3 cannot hide the fail check.
- Measure the operand with `getMutations` on the same bound values, so the exact dataSize is known instead of estimated.

### B3. Cluster tier

**B3a. Environment and build.**
1. One Linux node, built as in B2a, running from `$WORK/cassandra`.
2. In `conf/cassandra.yaml`:
   - point `data_file_directories`, `commitlog_directory`, `hints_directory`, `saved_caches_directory` and `cdc_raw_directory` at `$WORK/node/{data,commitlog,hints,caches,cdc}` on local disk with at least 5 GiB free;
   - set `batch_size_warn_threshold: 5KiB` and `batch_size_fail_threshold: <F>`.
3. Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
4. Start with `bin/cassandra -p $WORK/node/pid`. Wait until `bin/nodetool status` shows `UN`.
5. Client: python3 with the bundled driver, `export PYTHONPATH=$WORK/cassandra/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`. Check it with `python3 -c 'import cassandra'`. If the import fails, install `cassandra-driver==3.29.0` into a venv under `$WORK`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine: `$WORK/cassandra` is
> `$W/cassandra-run32` (built as in amendment B2a; no test probe left in it), and `$WORK/node` is `$W/node-bsf`. The node runs
> with its own `CASSANDRA_CONF=$W/node-bsf/conf` (a copy of the clone's `conf/` with the overrides of step 2 plus
> `listen_address`/`rpc_address: 127.0.0.1`) and `CASSANDRA_LOG_DIR=$W/node-bsf/logs`. There is no `setsid`, so step 4 is a
> tracked background `bin/cassandra -f > node.out 2>&1 < /dev/null` (not `-p`, which daemonizes); ready when `nodetool status`
> shows `UN 127.0.0.1` **and** `nodetool statusbinary` prints `running`; the script aborts if the process dies during start.
> Heap 2G as filed. The filed `PYTHONPATH` import works with the bundled 3.29.0 zip (checked 2026-10-26, `run1/stepE.txt`); the
> client uses `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False` and `idle_heartbeat_interval=0`.

**B3b. Knobs.** F ∈ {50KiB, 200KiB}, set in the yaml with a restart. A JMX change through `StorageService.BatchSizeFailureThreshold` is also allowed.

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** A third value, **F = 100KiB**, is added (group A: three
> values including the default). Order 50, 100, 200, each set in the yaml with a restart (no JMX). Read-back: the node's
> startup configuration line in `system.log` must contain `batch_size_fail_threshold=<F>KiB` and `batch_size_warn_threshold=5KiB`.
> Not a guardrail (`BatchStatement.java:332-366`), so the default `AllowAllAuthenticator` is fine.

**B3c. Workload.**
- Schema: `CREATE KEYSPACE b WITH replication={'class':'SimpleStrategy','replication_factor':1}`, plus `CREATE TABLE b.t (k int, c int, v blob, PRIMARY KEY (k,c)) WITH compression={'enabled':false}`.
- A script `batch.py <shape> <B_KiB> <N>` sends N=200 logged batches with `os.urandom(B*1024)` values:
  - `multi`: two partitions per batch, keys `2i` and `2i+1`;
  - `single`: one partition per batch, key `i`, rows c=0 and c=1.

  It prints counts of OK and "Batch too large" responses.
- Runs: `multi 30` (about 60 KiB per batch; total 200 × 60 KiB ≈ 12 MiB if accepted), `multi 10` (about 20 KiB), and `single 30`.
- The arithmetic: 60 KiB is above F = 50 and below F = 200; 20 KiB is below both. Each run takes under a minute.

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).**
> 1. A fourth run, **`multi 60`** (about 120 KiB per batch; 200 × 120 KiB ≈ 24 MiB if accepted), so that with F = 100 the
>    boundary falls between two workloads: 20 KiB and 60 KiB below it, 120 KiB above it. Order per F: `multi 30`, `multi 10`,
>    `single 30`, `multi 60`.
> 2. `batch.py` (in `harness/<stem>/`) sends each batch as a driver `BatchStatement(BatchType.LOGGED)` of a prepared
>    `INSERT INTO b.t (k, c, v) VALUES (?, ?, ?)`, one batch at a time; this reaches `BatchStatement.execute` →
>    `executeWithoutConditions` → `verifyBatchSize` (`BatchStatement.java:405-445`). Exact sizes: B·1024 random bytes per value.
>    It prints `RESULT shape=<s> B=<B> n=<N> ok=<n> rejected=<n> other_errors=<n> first=<first error message>`; "rejected"
>    means a server `InvalidRequest` whose message contains `Batch too large`.

**B3d. Observables and instruments.**
- Client-side counts of OK and rejected batches.
- `bin/nodetool tablestats b.t`: "Memtable data size" and "Local write count", read before and after each run.
- `bin/nodetool flush b t; du -sb $WORK/node/data/b/t-*/` for disk.
- `SELECT count(*) FROM b.t`.
- `grep -c "Batch too large\|see batch_size_fail_threshold" logs/system.log`.
- What cannot be seen directly: commit-log bytes per batch, because segments are preallocated. Disk is measured through the flushed sstables instead.

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).** BSD `du` has no `-b`, and `TRUNCATE` with the default
> `auto_snapshot: true` (`conf/cassandra.yaml:1147`) moves the truncated sstables into the table's `snapshots/`, which `du` of
> the table directory would count in the next run. Disk bytes are therefore the sum of file sizes under the table directory,
> **skipping `snapshots/` and `backups/`** (`batch.py bytes <dir>`), read before the run and after the flush; the run's disk
> Δ is the difference, and the number of `*-Data.db` files is recorded. The `ERROR` count is the number of lines containing
> `see batch_size_fail_threshold` in the `system.log` bytes written **during** that run (from the file's byte offset at the run's
> start), not the whole file. "Memtable data size" and "Local write count" are read from `nodetool tablestats b.t` before the run
> and after it, before the flush. An automatic flush during a run would move memtable bytes to disk before the reading: the
> script greps `system.log` for `Flushing largest` and records it.

**B3e. Procedure.**
1. Start the node with F=50KiB and create the schema.
2. Run `multi 30` and record the observables. Then flush, `du`, and `TRUNCATE b.t`.
3. Repeat step 2 for `multi 10` and for `single 30`.
4. Stop the node with `kill $(cat $WORK/node/pid)`. Set F=200KiB, restart, and repeat steps 2 and 3.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `harness/<stem>/cluster-run.sh` (no
> arguments in run 1): wipe and create `$W/node-bsf`; for F in 50, 100, 200 KiB: write F into the node's yaml, start and wait
> (amendment B3a), read back F (amendment B3b), create the schema with `IF NOT EXISTS`, then the four runs of amendment B3c, each
> as: observables before → `batch.py` → observables after (before the flush) → `nodetool flush b t` → bytes and `count(*)` →
> `TRUNCATE b.t`; then stop the node with `nodetool stopdaemon` (a `kill` of the tracked process if it does not exit within
> 60 s) and check no daemon is left. The data directory is kept across the three restarts, as filed. A shakedown may pass
> `<N>` (batches per run) as the only argument; run 1 uses N = 200.

**B3f. Predictions.**

| F | `multi 30` | `multi 10` | `single 30` |
|---|---|---|---|
| 50KiB | 200 rejected; local write count +0; memtable size about unchanged; count 0; no sstable (du of the table dir unchanged, ≈ 0); 200 ERROR lines | 200 OK; 400 rows; sstable ≈ 4 MiB | 200 OK; 400 rows; sstable ≈ 12 MiB, despite 60 KiB > F |
| 200KiB | 200 OK; 400 rows; sstable ≈ 12 MiB (within ±15%) | (as above) | (as above) |

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** Exact forms, N = 200, and the added F and run:
>
> | F | `multi 30` (≈ 60 KiB) | `multi 10` (≈ 20 KiB) | `single 30` | `multi 60` (≈ 120 KiB) |
> |---|---|---|---|---|
> | 50KiB | R | A | A | R |
> | 100KiB | A | A | A | R |
> | 200KiB | A | A | A | A |
>
> **R (rejected):** ok = 0, rejected = 200, other errors 0; memtable data size after = before; local write count Δ = 0;
> `count(*)` = 0; disk Δ = 0 and no new `*-Data.db`; exactly 200 `see batch_size_fail_threshold` lines written during the run.
> **A (accepted):** ok = 200, rejected = 0, other errors 0; `count(*)` = 400; local write count Δ > 0; memtable data size after
> ≥ 400·1024·B; disk Δ within ±15 % of 400·1024·B (multi 10: 4,096,000 B; multi 30 and single 30: 12,288,000 B; multi 60:
> 24,576,000 B); 0 `see batch_size_fail_threshold` lines during the run. Read-back of F as in amendment B3b; no `Flushing largest`
> line for `b.t`.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| `multi 30` gives zero bytes at 50KiB and about 12 MiB at 200KiB | Disk follows F; confirmed |
| `multi 30` at 50KiB leaves rows or sstable bytes | Claim wrong |
| `single 30` at 50KiB gives about 12 MiB | The target-line exemption is confirmed: single-partition batches are not capped |
| `single 30` is rejected | The trace is wrong |
| `multi 10` is rejected at 50KiB | Something other than F binds; investigate |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words: row 1 together with row 3 is
> **Confirmed** (it needs every cell of amended B3f to hold, at all three F, including `multi 60` rejected at 50 and 100 and
> accepted at 200, and the ERROR count equal to the rejections); rows 2 and 4 **Refuted**; row 5 **Not confirmed**. Rows added:
>
> | Observation | Meaning |
> |---|---|
> | A read-back of F differs, the node dies or does not start, other (non-"Batch too large") errors occur, or an automatic flush of `b.t` happens during a run | **Invalid** run (runbook defect; restart the tier) |
> | An accepted-by-prediction run (`multi 30` at 100 or 200, `multi 60` at 200) is rejected | Something other than F binds; **Not confirmed** |
> | `multi 60` is accepted at 50 or 100 | Disk does not follow F; **Refuted** (as row 2) |
> | Rejections as predicted but the ERROR count differs from 200 per rejected run | Disallow branch not shown directly; **Not confirmed** |
> | An accepted run's disk Δ outside ±15 % of 400·1024·B | Disk measure does not track data size; **Not confirmed** for that cell (the rejected cells are read on their own) |
> | No row fits | Feedback to stage 3; no verdict |
>
> **Effect rule:** as amendment B2g — Confirmed with `single 30` accepted at 50 → **caps only on some paths (bypass)**.

**B3h. Controls.**
- The 200KiB run is the positive control: the same workload moves disk usage once the cap is raised.
- `multi 10` shows that small multi-partition batches pass.
- Compression is disabled and the blobs are random, so the sstable size tracks data size.
- RF=1 on one node, so there are no hints and no remote batchlog.

**B4. Risks and cleanup.**
- Everything lives under `$WORK` on local disk; the total written is under 100 MiB.
- After each tier, kill the node by pid and check `pgrep -f CassandraDaemon` returns nothing.
- Then `rm -rf $WORK/node`. Remove the clone when done.
- Nothing goes into the shared source tree.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine everything lives under
> `W=~/Library/Caches/stage4`: clone `$W/cassandra-run32`, node `$W/node-bsf` (wiped before and after the cluster tier), logs
> `$W/logs/<stem>/`. The no-daemon check is `ps -eo command | grep '[C]assandraDaemon'` (empty). The clone is kept (its
> `git status` must be clean); it is not removed.

## C. Sources read

src/java/org/apache/cassandra/cql3/statements/BatchStatement.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/db/IMutation.java
src/java/org/apache/cassandra/db/Mutation.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/service/StorageServiceMBean.java
src/java/org/apache/cassandra/service/StorageProxy.java
conf/cassandra.yaml
https://issues.apache.org/jira/browse/CASSANDRA-10876

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine** — results:
[`../../stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md`](../../stage4-runtime-verification/results/batch_size_fail_threshold-verifyBatchSize-mutations--autonomous.md)
(uncommitted). Frozen at sha256 `0e9c927f…016a` after fifteen audit amendments (B2a–B2g, B3a–B3g, B4); no run-1 defect.
- **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1). At F = 50, 100, 200 KiB a multi-partition batch was
  rejected (`Batch too large`, 0 rows, 0 memtable bytes, one ERROR line each) if and only if its measured `dataSize` exceeded
  1024·F; all 18 single-partition batches were accepted, up to 209,015 B at F = 50.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g rows 1 and 3). `multi 30` (≈ 60 KiB): 0 B on disk at 50 KiB,
  12.31 MB at 100 and 200 KiB; `multi 60` (≈ 120 KiB): 0 B at 50 and 100, 24.60 MB at 200; every rejected run 200/200 rejected
  with 200 ERROR lines; `single 30`: 12.31 MB at every F.
- For stage 3: the filed probe did not run as written (`CQLTester.formatQuery` takes one argument, so a batch with two `%s`
  fails; `parseStatement(String, ClientState)` already prepares; `requireNetwork()` missing), and `du` of the table directory
  after `TRUNCATE` counts `snapshots/` under the default `auto_snapshot: true`. The other bypasses in A3 (conditional batches,
  virtual tables) were not exercised.
