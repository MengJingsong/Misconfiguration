# max_mutation_size (startup invariant vs commitlog_segment_size in applySimpleConfig) — verification solution  <!-- file: cases/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`DatabaseDescriptor.java:900`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L900) (`900#1`, `commitlog_segment_size.toKibibytes() < 2 * max_mutation_size.toKibibytes()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (claude-opus-5-5), Claude Code at Meta (version string not available in the sandbox), 2026-10-25, band D triage |
| Estimate | `positive`: an explicit `max_mutation_size` must be ≤ half the segment size (line 900), and at runtime every write is refused when its serialized size plus entry overhead exceeds it (`Mutation.java:169-176`, called from `CommitLog.java:304`, `SingleTableUpdatesCollector.java:112`, `BatchUpdatesCollector.java:149`), which bounds the size of any single mutation buffered for the commit log and kept in a segment. It also sizes hint buffers (`HintsService.java:110`). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.** `max_mutation_size`, configuration entry ([`Config.java:406-407`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L406-L407), `IntKibibytesBound`, default `null`; legacy `max_mutation_size_in_kb`), documented in `conf/cassandra.yaml:652-657`. When unset: `commitlog_segment_size KiB / 2` ([`DatabaseDescriptor.java:898-899`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L899)). When set: rejected if `segment KiB < 2 × max KiB` (`:900-901`). Getter `getMaxMutationSize()` in bytes (`:2827-2830`); read into the interface constant `IMutation.MAX_MUTATION_SIZE` at class init ([`IMutation.java:31`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/IMutation.java#L31)), so restart required.


**Limit type (2026-10-29).** not-a-case: the entry-pointer `if` reconciles two settings (`commitlog_segment_size` against twice `max_mutation_size`), not usage against a capacity ([README §6](../README.md#6-rules-that-hold-for-both-agents)). The verification solution and the stage-4 results are kept as filed.
**A2. What it caps.** Size of one mutation (serialized bytes + `ENTRY_OVERHEAD_SIZE` = 12, `CommitLogSegment.java:93`): bounds the per-write commit-log allocation, the `DataOutputBuffer` scratch serialization (`CommitLog.java:306-311`), and the hint buffer size (`HintsService.java:110`, 2 × max).

**A3. Mechanism.**
1. Startup default/invariant ([`DatabaseDescriptor.java:898-901`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L898-L901)). The invariant guarantees a maximal mutation always fits in an empty segment ([`CommitLogSegment.java:240-247`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java#L240-L247) returns −1 when it does not fit; the manager would otherwise keep advancing segments, [`CommitLogSegmentManagerStandard.java:52-57`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java#L52-L57)).
2. Coordinator-side: CQL statements validate each mutation ([`SingleTableUpdatesCollector.java:112`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java#L112), [`BatchUpdatesCollector.java:149`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/BatchUpdatesCollector.java#L149)).
3. Replica-side: `CommitLog.add` validates again ([`CommitLog.java:304`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/commitlog/CommitLog.java#L304)); oversize → `MutationExceededMaxSizeException`, `OverSizedMutations` meter ([`Mutation.java:172-175`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/Mutation.java#L172-L175)).
- Bypass: mutations written with `durable_writes = false` skip the commit log (not traced here); the coordinator still validates on the CQL path.

**A4. Other consumers.** `native_transport_max_message_size` (CQL frame), `internode_max_message_size`, guardrails on column value size, memtables.

**A5. Evidence beyond the source.** `conf/cassandra.yaml:652-660`. Related existing cases: `max_mutation_size-validateSize-MAX_MUTATION_SIZE--guided.md`, `max_mutation_size-allocateBytes-slabCapacity--autonomous.md`.

## B. Verification solution

**B1. Claim under test.** (a) With `commitlog_segment_size: S`, an explicit `max_mutation_size` M is accepted iff 2M ≤ S (KiB arithmetic). (b) A mutation whose serialized size + 12 B exceeds M is refused and is never appended to the commit log, so no commit-log allocation exceeds M.

### B2. Unit tier

**B2a. Environment and build.** Local clone `/local/c509`, `ant jar`; `ConfigProbe` (as in `prepared_statements_cache_size-applySimpleConfig-preparedStatementsCacheSizeInMiB--autonomous.md` B2a) with getter `getMaxMutationSize`. Mechanism: CQLTester probe `org.apache.cassandra.probe.MaxMutationProbeTest` run by `ant testsome -Dtest.name=…`; knobs set in the local clone's `test/conf/cassandra.yaml` (segment already 5MiB at line 10).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2a.** This host (`environment-advisor.md`): run clone `$W/cassandra-run16` (`W=~/Library/Caches/stage4`, tag `cassandra-5.0.9`, `b5f2a54210`), built with `ant -Dlocal.repository=$W/m2 build-test` (not `ant jar`: the probe test needs the test classes); `CP="$C/build/classes/main:$C/build/lib/jars/*"`. `ConfigProbe.java` is copied unchanged from `harness/commitlog_segment_size-applySimpleConfig-commitlog_segment_size--autonomous/`; each yaml variant runs in its own `java -Xms1G -Xmx1G` process with the 17 JDK 11 module flags of `build.xml:244-261` (`daemonInitialization()` runs once per JVM), on a copy of the clone's `conf/cassandra.yaml` with the `commitlog_segment_size` line (`:660`) replaced, a `max_mutation_size` line appended when set, and the five directories under `$W/probe-mms/data`. Mechanism: `MaxMutationProbeTest` (harness folder) copied into `$C/test/unit/org/apache/cassandra/probe/`, **one** `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.probe.MaxMutationProbeTest -Dtest.timeout=900000` JVM per value (`IMutation.MAX_MUTATION_SIZE` is a static constant read once per JVM, `IMutation.java:31`); the value is set by appending `max_mutation_size: <M>` to the clone's `test/conf/cassandra.yaml` (line 10 stays `commitlog_segment_size: 5MiB`; the file has no `max_mutation_size` line), restored with `git checkout` after each JVM; `$C/build/test/cassandra` removed before each. Script `harness/<stem>/unit-run.sh`.

**B2b. Knobs.** ConfigProbe with `commitlog_segment_size: 8MiB` and `max_mutation_size` ∈ {`4096KiB` (2M = S, accept), `4097KiB` (reject), unset (→ 4096 KiB)}; with segment `32MiB` and `max_mutation_size` ∈ {`16384KiB` (accept), `16385KiB` (reject)}. Test: segment 5MiB with M ∈ {1024KiB, 2560KiB}.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2b.** ConfigProbe (getter `getMaxMutationSize`, six JVMs): (`8MiB`, `4096KiB`), (`8MiB`, `4097KiB`), (`8MiB`, unset), (`32MiB`, `16384KiB`), (`32MiB`, `16385KiB`), and (`32MiB`, unset) — the shipped default, added for group A. Mechanism JVMs (S = 5 MiB): M ∈ {`1024KiB`, `2048KiB`, unset (→ 2560 KiB, the derived default; the filed explicit `2560KiB` is the same value and is replaced by the default form)} plus the B2h control JVM `1026KiB`.

**B2c. Workload.** `createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob)")`; insert blobs of size M − 1 KiB (accept) and M + 1 KiB (reject); then 50 inserts of M − 1 KiB to push through ≥ 2 segments.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2c.** Exact, per mechanism JVM, all through `execute(…)` (the internal CQL path; `SingleTableUpdatesCollector.toMutations` validates each mutation with overhead 12, `SingleTableUpdatesCollector.java:112`, before it is applied through `CommitLog.add`): (1) key 1, blob A = M − 1,024 B; (2) key 2, blob B = M + 1,024 B; (3) **exact boundary**: k = t_B − B from (2)'s message total t_B; probe x = M − k + 9; repeat at most 6 times on fresh keys: insert blob x; if refused with total t ≠ M + 1, set x ← x − (t − (M + 1)); if accepted, x ← x + 16; stop when a refusal reports total exactly M + 1; then insert blob x − 1 on a fresh key (t is strictly increasing in the blob size, `Mutation.serializedSize`, but the vint length prefixes make k depend on the size, so k from (2) is only a start); (4) **replica-side check, driven directly**: build `PartitionUpdate.simpleBuilder(table, 900).row().add("v", <M + 1,024 B>).buildAsMutation()` and call `CommitLog.instance.add(m)` — this skips the coordinator check and reaches `CommitLog.java:304`; then the same with M − 1,024 B (key 901); (5) 50 inserts of M − 1,024 B (keys 1000–1049). Control JVM `1026KiB`: its step (1) blob is 1,049,600 B, the same blob the `1024KiB` JVM refuses at step (2).

**B2d. Observables and instruments.** Exceptions; `CommitLog.instance.metrics.oversizedMutations.getCount()`; commit-log file contents are not parsed—instead `CommitLog.instance.getCurrentPosition()` before/after the refused insert (must not move).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2d.** Per request: outcome; exception class, its cause chain and message; `oversizedMutations` count before and after; `CommitLog.instance.getCurrentPosition()` (segment id, position) before and after; whether the row is present (`SELECT`). Bytes allocated across a request = Δposition if the segment id is unchanged, else the position in the new segment. Read-back per JVM: `getCommitLogSegmentSize()`, `getMaxMutationSize()`, `IMutation.MAX_MUTATION_SIZE`. For step (4) also `m.serializedSize(MessagingService.current_version)` and the top stack frames of the exception. INFO: elapsed time of step (5).

**B2e. Procedure.** ConfigProbe variants; per M: edit test yaml, run, record; restore yaml.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2e.** Order: ConfigProbe JVMs in the B2b order; then mechanism JVMs `1024KiB`, `1026KiB`, `2048KiB`, unset. The test writes `STAGE4` lines to `$L/stage4.out` and asserts nothing about the claim; `unit-run.sh` logs each command to `commands.log` and writes `summary.txt`; the clone's test yaml is restored and the probe test removed at the end.

**B2f. Predictions.** ConfigProbe: `4096KiB` with 8MiB → `OK …=4194304`; `4097KiB` → `REJECT … commitlog_segment_size must be at least twice the size of max_mutation_size / 1024`; unset → `OK …=4194304`; same pattern at 32MiB. Test: M − 1 KiB accepted; M + 1 KiB refused with `InvalidRequestException` caused by `MutationExceededMaxSizeException`, oversizedMutations +1, current position unchanged; the 50 inserts complete without stalling.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2f** (exact forms; the filed relations are kept). ConfigProbe: (`8MiB`, `4096KiB`) → `OK getMaxMutationSize=4194304`; (`8MiB`, `4097KiB`) → `REJECT ConfigurationException: commitlog_segment_size must be at least twice the size of max_mutation_size / 1024` (`DatabaseDescriptor.java:900-901`: 8,192 < 2 × 4,097); (`8MiB`, unset) → `OK getMaxMutationSize=4194304` (`:898-899`: 8,192 KiB / 2); (`32MiB`, `16384KiB`) → `OK …=16777216`; (`32MiB`, `16385KiB`) → the same REJECT message; (`32MiB`, unset) → `OK …=16777216`. Mechanism, per JVM: (i) read-back S = 5,242,880 and M in bytes (1,048,576 / 1,050,624 / 2,097,152 / 2,621,440) equal in `getMaxMutationSize()` and `IMutation.MAX_MUTATION_SIZE`; (ii) blob A accepted, count unchanged, row present; (iii) blob B refused: the thrown exception is an `InvalidRequestException` and `MutationExceededMaxSizeException` is its class or in its cause chain (the filed "caused by" is read this way: the exception *is* a subclass, `MutationExceededMaxSizeException.java:32`), message `Rejected an oversized mutation (<t>/<M>)` with t > M, count +1 exactly, bytes allocated < 4,096 (an appended entry would allocate t + 12 > 1 MiB; 4,096 allows a sync marker, a segment header and small system writes), row absent; (iv) the boundary search ends with a refusal whose message total is exactly M + 1 (count +1, row absent) within its 6 tries, and blob x − 1 (total M) is accepted (count unchanged, row present) — `totalSize > MAX_MUTATION_SIZE`, `Mutation.java:171-172`; (v) direct `CommitLog.add` of the M + 1,024 B mutation throws `MutationExceededMaxSizeException` with `Mutation.validateSize` ← `CommitLog.add` on its stack, count +1, bytes allocated < 4,096; the M − 1,024 B mutation returns a position, count unchanged (INFO: bytes allocated vs serializedSize + 12, plus 8 if a sync marker intervened); (vi) all 50 inserts accepted, count unchanged across them, segment id after − before ≥ 2 (≈ 50 × (M − 1 KiB) ≥ 10 S of entries).

**B2g. Readings.**
| Observation | Meaning |
|---|---|
| accept/reject exactly at 2M = S; M+1KiB refused | claim holds |
| 2M > S accepted | invariant not enforced; claim (a) wrong |
| M+1KiB accepted and position advances by > M | cap not enforced; claim (b) wrong |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2g** (rows added; the filed rows keep their meaning). Verdict mapping:

| Observation | Verdict |
|---|---|
| ConfigProbe as in B2f, and (i)–(vi) hold in all four mechanism JVMs, and the B2h control holds | **Confirmed — caps** (an explicit M is accepted iff 2M ≤ S; every mutation with total > M is refused at the coordinator and at `CommitLog.add` with no commit-log allocation; the boundary is exactly M and moves with M) |
| a value with 2M > S accepted, or 2M = S refused | **Refuted** in part (a) |
| blob B, the boundary total M + 1, or the oversized direct `CommitLog.add` accepted; or bytes allocated ≥ M across a refused request; or blob x − 1 (total M) refused | **Refuted** in part (b) |
| read-back (i) differs, a refusal by an exception other than `MutationExceededMaxSizeException`, or the B2h control refused | **Invalid** |
| refusals right but the count is not +1, the boundary search does not converge, or (vi) fails | **Not confirmed** |

**B2h. Controls.** M+1KiB insert with M raised by 2 KiB → accepted (shows the boundary is M, not another limit).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B2h.** The control is the `1026KiB` JVM's step (1): blob 1,049,600 B (total ≈ 1,049,667 by k from the `1024KiB` JVM, ≤ 1,050,624) is **accepted**, count unchanged, row present, while the same blob is refused in the `1024KiB` JVM; and its own B (1,051,648 B) is refused with max 1,050,624. This shows the boundary moves with M and is not another limit (S, the commit-log segment, is 5 MiB in every JVM).

### B3. Cluster tier

**B3a. Environment and build.** Single node from `/local/c509` as in the commitlog-segment case B3a (`/local/run`, `MAX_HEAP_SIZE=2G`).

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3a.** This host: one node from `$W/cassandra-run16` on 127.0.0.1, conf copied from the clone and yaml lines replaced (`cluster-run.sh`, pattern of the commit-log harness), directories `$W/node-mms/{data,commitlog,hints,saved_caches,cdc_raw}`, wiped before and after each arm; `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. Held fixed in every arm: `commitlog_segment_size: 8MiB`, `num_tokens: 1`, `initial_token: 0`, `commitlog_total_space: 1024MiB` (bounds disk), `batch_size_warn_threshold: 4096KiB` and `batch_size_fail_threshold: 4096KiB` (a multi-partition batch over the shipped 50 KiB is refused with `Batch too large` before any mutation check, `BatchStatement.java:331-358`), and — in every arm except the INFO arm `tdef` — `native_transport_max_message_size: 64MiB` with `native_transport_max_request_data_in_flight: 128MiB` and `…_per_ip: 128MiB`. **Which check refuses which request** (source, pinned clone): (1) the native transport, protocol v5: a message whose body exceeds `native_transport_max_message_size` is consumed and discarded, `OversizedCQLMessageException` (an `InvalidRequestException`) `CQL Message of size <n> bytes exceeds allowed maximum of <L> bytes`, OverSizedMutations unchanged (`CQLMessageHandler.java:551-556, 824-826, 847-851`); its default is min(max_mutation_size, in-flight, in-flight per IP) (`DatabaseDescriptor.java:903-905, 3237-3244`), i.e. **M itself**, so the filed "all under the default native message limit" is wrong: every M + 4 KiB request would be refused here first. The 16 MiB `native_transport_max_frame_size` limit (`Envelope.java:197, 429-439, 484`) applies to the pre-v5 decoder only; v5 frames are reassembled by `CQLMessageHandler` and checked against the message limit, so it does not bind at protocol 5, and no request here exceeds 4.01 MiB anyway; (2) the coordinator, CQL path: `SingleTableUpdatesCollector.java:112` / `BatchUpdatesCollector.java:149` → `Mutation.validateSize` → `MutationExceededMaxSizeException` `Rejected an oversized mutation (<t>/<M>) for keyspace: …`, OverSizedMutations +1 (`Mutation.java:169-176`, `MutationExceededMaxSizeException.java:32-60`), client `InvalidRequest`; (3) the commit log: `CommitLog.add` → the same `validateSize` (`CommitLog.java:304`), reached by mutations that did not pass (2) — on one node, the batchlog mutation of a logged multi-partition batch (`BatchStatement.java:439-445`, `StorageProxy.java:1286-1301`, `BatchlogManager.java:139-165`), whose failure is logged as `Failed to apply mutation locally` and returned as a write failure (`StorageProxy.java:1674-1690`), OverSizedMutations +1. Script `harness/<stem>/cluster-run.sh`.

**B3b. Knobs.** (`commitlog_segment_size`, `max_mutation_size`) ∈ {(`8MiB`, `4097KiB`) → abort; (`8MiB`, `1024KiB`); (`8MiB`, unset → 4096 KiB)}.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3b.** Arms, in order: `a4097` (`max_mutation_size: 4097KiB`, expect start-up refusal), `m1024` (`1024KiB`), `m2048` (`2048KiB`; B3h control and third value), `mdef` (no line: derived default 4096 KiB), and the INFO arm `tdef` (`1024KiB` with the native message and in-flight limits left at their defaults; it shows check (1) shadowing check (2) and is not used for the verdict). A shakedown `sd` (the `m1024` settings, stress n = 200) runs first as a harness check, not a reading.

**B3c. Workload.** Python driver: insert one row with blob 1 MiB + 4 KiB, one with 1 MiB − 4 KiB, one with 4 MiB + 4 KiB, one with 4 MiB − 64 KiB (all under the default native message limit); then `cassandra-stress write n=2000 -col size=FIXED\(900000\) n=FIXED\(1\) -rate threads=8` (≈ 1.8 GB) to show near-limit mutations flow.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3c.** Bundled driver (`lib/cassandra-driver-internal-only-*.zip`, protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`), keyspace `ks` RF 1, table `ks.big (k int PRIMARY KEY, v blob)`, prepared `INSERT` with the blob bound (zeros). Requests per arm, in order (blob bytes; batch rows are on distinct partitions): `m1024`: key 1 1,052,672 (1 MiB + 4 KiB), key 2 1,044,480 (1 MiB − 4 KiB), logged batch keys 11/12 614,400 each, unlogged batch keys 21/22 614,400 each; `m2048`: key 1 1,052,672, key 3 2,101,248 (2 MiB + 4 KiB), key 4 2,093,056 (2 MiB − 4 KiB), logged batch keys 11/12 614,400 each; `mdef`: key 5 4,198,400 (4 MiB + 4 KiB), key 6 4,128,768 (4 MiB − 64 KiB), key 1 1,052,672 (INFO); `tdef`: key 1 1,052,672, key 2 1,044,480. Then, in `m1024` only (and `sd` with n=200): `tools/bin/cassandra-stress write n=2000 no-warmup -col 'size=FIXED(900000)' 'n=FIXED(1)' -rate threads=8 -node 127.0.0.1` (`no-warmup` makes the count exact; ≈ 1.8 GB, each mutation ≈ 900 KB < 1,048,576).

**B3d. Observables and instruments.** Driver exceptions; `nodetool sjk mx -mg -b org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations -f Count`; `ls -l /local/run/data/commitlog`; `system.log` lines for the rejection.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3d.** A one-connection JMX reader (`MMSampler`, pattern of the commit-log harness's `CLSampler`; `jstat` cannot attach here and `nodetool sjk` can exit 0 on failure) reads `org.apache.cassandra.metrics:type=CommitLog,name=OverSizedMutations` Count and `org.apache.cassandra.db:type=Commitlog` `ActiveContentSize` (the synced content of the active segments, `CommitLog.java:430-436`, `CommitLogSegment.java:650-653`) before each request and 12 s after it (the periodic sync runs every 10 s and `contentSize` is `lastSyncedOffset`), and every 2 s during stress. Driver exception class and message; rows read back by `SELECT`; `system.log` lines `Rejected an oversized mutation` / `Failed to apply mutation locally`; read-back from `system_views.settings` (`commitlog_segment_size`, `max_mutation_size`, `native_transport_max_message_size`, `batch_size_fail_threshold`); stress's `Total partitions` / `Total errors`; for `a4097` the exit code of `bin/cassandra -f` and its output.

**B3e. Procedure.** Abort case: start, confirm exit + message. Others: wipe, start, run inserts, stress, sample, stop, check no process left.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3e.** Pre-checks: no `CassandraDaemon`, ports 7000/7199/9042/9091 free, ≥ 20 GiB free. `a4097`: `bin/cassandra -f`, wait ≤ 120 s for exit, record rc and output. Other arms: wipe, start, wait for `UN` and native transport `running`, read back, create schema, wait 15 s, the requests of B3c each with its JMX before/after pair, then (m1024) stress with the 2-s reader, then `nodetool drain`, stop, confirm no process, wipe.

**B3f. Predictions.** M = 1024 KiB: 1 MiB + 4 KiB refused, 1 MiB − 4 KiB accepted, OverSizedMutations = 1; M = 4096 KiB: 4 MiB + 4 KiB refused, 4 MiB − 64 KiB accepted. Stress at 900 KB per row: all accepted under M = 1024 KiB.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3f** (exact forms; filed relations kept). (i) `a4097` exits with rc 3 within 120 s without `Startup complete`, output containing `commitlog_segment_size must be at least twice the size of max_mutation_size / 1024` (`DatabaseDescriptor.java:900-901`, `CassandraDaemon.java:746-768`). (ii) Read-back: `max_mutation_size` = `1024KiB` / `2048KiB` / `4096KiB` in m1024 / m2048 / mdef, `commitlog_segment_size` = `8MiB`, `native_transport_max_message_size` = 64 MiB. (iii) Every request expected refused by the mutation check (m1024 key 1; m2048 key 3; mdef key 5): driver `InvalidRequest` whose message contains `Rejected an oversized mutation (` and `/<M bytes>)`, OverSizedMutations +1 exactly, |Δ ActiveContentSize| < 65,536 B (an appended entry would add > M ≥ 1 MiB; 64 KiB allows sync markers, small system writes and the discard of a schema-only segment), row absent. (iv) Every request expected accepted (m1024 key 2; m2048 keys 1 and 4; mdef key 6): no exception, count unchanged, Δ ActiveContentSize ≥ blob − 65,536 B, row present. (v) The m1024 logged batch: driver `WriteFailure`, OverSizedMutations +1 exactly, `system.log` `Failed to apply mutation locally` with `MutationExceededMaxSizeException` `Rejected an oversized mutation (<t>/1048576) for keyspace: system`, neither row present, |Δ ActiveContentSize| < 65,536; the m1024 unlogged batch accepted, count unchanged, both rows present. (vi) m1024 stress: `Total partitions` 2,000 and `Total errors` 0, OverSizedMutations unchanged across stress. (vii) mdef as (iii)/(iv) with M = 4,194,304. INFO: mdef key 1; `tdef` (expected from the source: key 1 refused by the transport, `CQL Message of size … exceeds allowed maximum of 1048576 bytes`, count unchanged; key 2 accepted).

**B3g. Readings.**
| Observation | Meaning |
|---|---|
| refusals exactly above M | constraint caps per-mutation size |
| oversize accepted | claim wrong |
| abort for 4097KiB with 8MiB | invariant holds |

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3g** (rows added). Verdict mapping:

| Observation | Verdict |
|---|---|
| (i)–(vii) hold and the B3h control holds | **Confirmed — caps** (per-mutation size: the start-up invariant holds; every mutation over M is refused, at the coordinator for single statements and at `CommitLog.add` for the batchlog, without commit-log content; the boundary moves with M) |
| `a4097` starts | **Refuted** in part (a) |
| an expected-refused request accepted or its row present, or Δ ActiveContentSize ≥ M across a refusal | **Refuted** in part (b) |
| a request meant for the mutation check refused by another check (`CQL Message of size`, `Batch too large`), read-back (ii) differs, or the B3h control refused | **Invalid** (the check was not reached, or the knob was not applied) |
| refusals right but a count is not +1, an ActiveContentSize relation fails while the refusal holds, or (vi) fails | **Not confirmed** |
| `tdef` | INFO only |

**B3h. Controls.** Same oversize insert with M raised to 2048 KiB → accepted.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B3h.** Arm `m2048`: the 1,052,672-byte key-1 insert refused in m1024 is accepted (count unchanged, row present), and the logged batch refused in m1024 is accepted (its batchlog mutation, ≈ 1.2 MiB, is below 2 MiB; both rows present, count unchanged).

**B4. Risks and cleanup.** ≈ 2 GiB data; check `df -h /local` ≥ 6 GiB. Stop node and stress; `pgrep -f CassandraDaemon` empty; restore test yaml, delete probe test; `rm -rf /local/run /local/probe/data`.

> **Amendment 2026-10-25 (stage-4 audit, Claude Opus 5.5, before any reading), B4.** This host: ≤ 4 GB per arm on the internal APFS SSD (`$W/node-mms`; commit log ≤ 1 GiB + one segment, SSTables ≈ 1.8 GB), ≥ 20 GiB free required; stop node and stress, `ps -eo command | grep '[C]assandraDaemon'` empty; restore the clone's test yaml, delete the probe test; `rm -rf $W/node-mms $W/probe-mms`.

## C. Sources read

src/java/org/apache/cassandra/config/DatabaseDescriptor.java (891-901, 2825-2830)
src/java/org/apache/cassandra/config/Config.java (396-407)
src/java/org/apache/cassandra/db/IMutation.java (28-75)
src/java/org/apache/cassandra/db/Mutation.java (169-176)
src/java/org/apache/cassandra/db/commitlog/CommitLog.java (300-325)
src/java/org/apache/cassandra/db/commitlog/CommitLogSegment.java (93, 240-255)
src/java/org/apache/cassandra/db/commitlog/CommitLogSegmentManagerStandard.java (40-60)
src/java/org/apache/cassandra/cql3/statements/SingleTableUpdatesCollector.java (112), BatchUpdatesCollector.java (149)
src/java/org/apache/cassandra/hints/HintsService.java (110)
conf/cassandra.yaml (652-660)

## D. Stage-4 feedback

**2026-10-25 — stage 4 run 1 (Claude Opus 5.5, advisor's machine), results [`results/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.md`](../../stage4-runtime-verification/results/max_mutation_size-applySimpleConfig-max_mutation_size--autonomous.md).** Frozen after seventeen audit amendments (sha256 `e69f7208…296a`, `_INDEX.md` §4); uncommitted.
- **Unit: Confirmed — caps** (per mutation). B2g row 1: ConfigProbe accepted 2M = S and refused 2M = S + 2 KiB at 8 and 32 MiB (traced message), unset = S/2; at M = 1024/1026/2048 KiB and the default 2560 KiB a mutation of total M + 1 was refused (`MutationExceededMaxSizeException`, +1, 0 bytes allocated) and one of total M accepted (an entry of exactly M bytes); a direct `CommitLog.add` over M was refused at `CommitLog.java:304` with nothing allocated; the 1026 KiB control accepted the blob the 1024 KiB JVM refused.
- **Cluster: Confirmed — caps** (per mutation). B3g row 1: `4097KiB` with 8 MiB stops start-up (rc 3); M + 4 KiB refused as oversized at 1024/2048/4096 KiB with no commit-log content added; the logged batch's batchlog mutation (1,229,013 B) refused at `CommitLog.add` with `WriteFailure`; 2,000 × 900 KB stress passed; the 2048 KiB control accepted the request and the batch.
- **For stage 3:** the filed B3c's "all under the default native message limit" was wrong: the default `native_transport_max_message_size` is min(max_mutation_size, in-flight limits) = M (`DatabaseDescriptor.java:903-905, 3237-3244`), so every M + 4 KiB request is refused by the transport first (seen in the INFO arm: `CQL Message of size 1052740 bytes exceeds allowed maximum of 1048576 bytes`, count +0). A logged multi-partition batch also needs `batch_size_fail_threshold` raised (50 KiB default). The hint-buffer sizing (`HintsService.java:110`) was not exercised.
