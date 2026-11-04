# ExecuteMessage literal `1000` (trace bound-value length) — verification solution  <!-- file: cases/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ExecuteMessage.java:231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java#L231) (`if (boundValue.length() > 1000)`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string n/a), 2026-10-26; Band D triage mode |
| Estimate | `positive` (scoped to what is persisted). When a prepared EXECUTE is traced, each bound value's CQL literal is cut to 1000 chars plus a 4-char `...'` suffix before it goes into the `parameters` map of the `system_traces.sessions` row. So the trace row's per-value disk and memtable footprint is capped at 1004 chars, whatever the value's size. It does **not** cap the transient heap: the full literal is built first (`:230`). It also does not cap the number of values, the `query` text, or the unprepared QUERY path, where literals sit in `query` uncut (`QueryMessage.java:138`). |
| Ground | — |

## A. Constraint trace

**A1. The constraint.**
- **Name and kind.** A hard-coded integer literal, `1000`, in `ExecuteMessage.traceQuery`. It is written twice: once in the check at [`ExecuteMessage.java:231`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java#L231) and once as the cut length in `boundValue.substring(0, 1000)` at `:232`.
- **Declaration.** None: no named variable, configuration entry or property stands behind it, so the stem uses `ExecuteMessage_literal_1000`.
- **Unit.** Java `String` chars, that is, UTF-16 code units of the rendered CQL literal.
- **Setting it.** It cannot be set. Changing it needs a code change and a restart.


**Limit type (2026-10-29).** non-config: hard-coded constant. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.**
- **Quantity compared.** The length of the CQL-literal rendering of one bound variable, `cs.type.asCQL3Type().toCQLLiteral(bytes)` (`:230`).
- **Resource.** That string becomes one value of the `parameters map<text,text>` column of `system_traces.sessions` (`src/java/org/apache/cassandra/tracing/TraceKeyspace.java:83`). It is written as a mutation, so it lands in the memtable, then in the commit log, then in SSTables on disk.
- **Lifetime.** The row lives for `trace_type_query_ttl` (`conf/cassandra.yaml:1752`, default `1d`; `src/java/org/apache/cassandra/tracing/Tracing.java:93-95`).
- **Bound.** Each bound value contributes at most 1004 chars to the row, against an uncapped size of 2·S+2 chars for an S-byte blob. Disk is the resource that matters; the memtable is secondary.

**A3. Mechanism.**
1. `Message.Request.execute` decides whether to trace ([`Message.java:230-259`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/Message.java#L230-L259)). It traces when the client sets the tracing flag (`:237-241`) or when `StorageService.shouldTraceProbablistically()` fires (`:243-247`; [`StorageService.java:6636-6639`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/service/StorageService.java#L6636-L6639), set by `nodetool settraceprobability`). It then calls `execute(..., shouldTrace)`.
2. `ExecuteMessage.execute` calls `traceQuery(state, prepared)` when `traceRequest` is true ([`ExecuteMessage.java:160-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java#L160-L161)).
3. `traceQuery` (`:213-240`) puts `page_size`, `consistency_level`, `serial_consistency_level` and `query` (`prepared.rawCQLStatement`, uncut, `:223`) into the parameters map. Then, for each bind variable i (`:225`):
   - it renders the full literal (`:230`);
   - blob: `"0x" + hex` ([`BytesSerializer.java:65-68`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/serializers/BytesSerializer.java#L65-L68), unquoted);
   - text: quoted ([`TypeSerializer.java:81-86`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/serializers/TypeSerializer.java#L81-L86), [`AbstractTextSerializer.java:67`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/serializers/AbstractTextSerializer.java#L67), `:80-83`);
   - **target `:231`**: if the length exceeds 1000, it keeps the first 1000 chars and appends `...'` (`:232`);
   - it puts the result under `bound_var_<i>_<name>` (`:236`).
4. `Tracing.instance.begin(...)` (`:239`) leads to `TracingImpl.begin`, which builds the start-session mutation and executes it ([`TracingImpl.java:53-66`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tracing/TracingImpl.java#L53-L66)). `TraceKeyspace.makeStartSessionMutation` writes the row with `.appendAll("parameters", parameters)` and TTL `ttl` ([`TraceKeyspace.java:115-136`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/tracing/TraceKeyspace.java#L115-L136)).
5. Outcome when the limit is reached: the value is silently cut. The request is not rejected, and nothing is logged.
6. Paths that bypass or overshoot the cap:
   - **Transient heap.** The full literal (about 2·S chars for a blob) is allocated before the check (`:230`), so heap during tracing is not capped.
   - **Number of values.** The cap is per value. A statement with B bind variables writes up to B × 1004 chars.
   - **Query text.** `query` (`:223`) is not cut.
   - **Unprepared QUERY path.** Inline literals go into `query` uncut ([`QueryMessage.java:138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/QueryMessage.java#L138)). This path is the positive control below.
   - **BATCH.** Bound values are not traced at all ([`BatchMessage.java:251`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/transport/messages/BatchMessage.java#L251)).
   - **Upstream limit.** Request size is bounded upstream by `native_transport_max_frame_size` (`conf/cassandra.yaml:1044`, 16 MiB) and `max_value_size` (`:1864`).

**A4. Other consumers.**
- The base table write of the same value.
- `system_traces.events` rows written during the request.
- The commit log.
- Other trace sessions.
- Everything else using the memtable heap and the data directory.

**A5. Evidence beyond the source.**
- CASSANDRA-11719, "Add bind variables to trace" (`CHANGES.txt:2743`), https://issues.apache.org/jira/browse/CASSANDRA-11719.
- An existing test asserts the cut: `test/unit/org/apache/cassandra/cql3/TraceCqlTest.java:116-148`, which expects `"'" + boundValue.substring(0, 999) + "...'"`.
- History is not available in the shallow clone: `git log -S` finds only the release commit.

## B. Verification solution

**B1. Claim under test.**
- For a traced prepared EXECUTE with one blob of S bytes, the stored `bound_var_*` value is 2S+2 chars long when 2S+2 ≤ 1000. For every larger S it is exactly 1004 chars, so the `system_traces.sessions` footprint per traced request stays flat as S grows.
- The same value sent as an inline literal through an unprepared QUERY grows the stored `query` parameter, and the sessions table on disk, linearly in S.

### B2. Unit tier

**B2a. Environment and build.**
1. Use JDK 11 and Ant. Clone to local disk, never building in the shared clone: `git clone /Users/yangwang/cassandra-src $WORK/cassandra && cd $WORK/cassandra && git checkout cassandra-5.0.9`.
2. Run `ant jar build-test`.
3. Add `test/unit/org/apache/cassandra/cql3/TraceBoundValueTruncationProbeTest.java` in the local clone only. It extends `CQLTester`, which starts an in-JVM server. `requireNetwork()` enables the native transport for the bundled Java driver 3.x, as `TraceCqlTest` does.
4. Run it with `ant testsome -Dtest.name=org.apache.cassandra.cql3.TraceBoundValueTruncationProbeTest`.
5. JVM options are the test defaults.

> **Amendment U1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2a, B2e and B4 on this host (the advisor's Mac, `stage4-runtime-verification/environment-advisor.md`). The run clone is `$W/cassandra-run57` (`W=~/Library/Caches/stage4`; `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run57`, commit `b5f2a54210`), built once with `ant -Dlocal.repository=$W/m2 build-test` (it also builds `build/apache-cassandra-5.0.9-SNAPSHOT.jar`, so B2a's separate `ant jar` is not needed). The test source is kept at `stage4-runtime-verification/harness/<this stem>/TraceBoundValueTruncationProbeTest.java`; `harness/<this stem>/unit-run.sh` copies it to the B2a path, runs `ant -Dlocal.repository=$W/m2 testsome -Dtest.name=org.apache.cassandra.cql3.TraceBoundValueTruncationProbeTest`, logs every command, copies `build/test/logs/**/TEST-*TraceBoundValueTruncationProbeTest*.log` (where the test's stdout lands, one line per write) out of the clone, removes the copied test and its classes and deletes `build/test/cassandra`. The unit yaml enables read thresholds (`test/conf/cassandra.yaml:63-69`: coordinator warn 1024 KiB, fail 4096 KiB; local warn 4096 KiB, fail 8192 KiB); the largest row this tier reads back is the S = 65 536 control (`query` ≈ 131 KB), below every threshold, so they are left as they are.

**B2b. Knobs.**
- The constant cannot be changed. The varied input is the blob size S in bytes: S ∈ {100, 499, 500, 600, 65 536, 1 048 576}.
  - S = 499 gives a literal of exactly 1000 chars, so no cut.
  - S = 500 gives 1002 chars, the first cut.
  - The large sizes show that the stored length stays flat.
- Text boundary: text T of random alphanumerics (no quotes), with |T| ∈ {998, 999}. The quoted literal is |T|+2 chars, so the first cut is at |T| = 999.
- Multiplicity check: a table with 8 blob columns, each 65 536 bytes.

**B2c. Workload.**
1. `createTable("CREATE TABLE %s (k int PRIMARY KEY, v blob, t text, b0 blob, b1 blob, b2 blob, b3 blob, b4 blob, b5 blob, b6 blob, b7 blob)")`.
2. `TraceStateImpl.WAIT_FOR_PENDING_EVENTS_TIMEOUT_SECS = 5` in `@BeforeClass`, restored in `@AfterClass`, copied from `TraceCqlTest.java:46-58`.
3. `Session s = sessionNet();` (do not close the shared session).
4. **Prepared blob.** `PreparedStatement ps = s.prepare("INSERT INTO " + KEYSPACE + "." + currentTable() + " (k, v) VALUES (?, ?)").enableTracing();`. For each S, fill `new byte[S]` from `new Random(42)` and run `QueryTrace tr = s.execute(ps.bind(S, ByteBuffer.wrap(b))).getExecutionInfo().getQueryTrace();`. The key is `bound_var_1_v`, because k is variable 0.
5. **Prepared text.** Use `(k, t) VALUES (?, ?)` with key `bound_var_1_t`, for |T| ∈ {998, 999}.
6. **Multiplicity.** Use `(k, b0, …, b7) VALUES (?, ?, …, ?)` with eight 65 536-byte blobs.
7. **Positive control (unprepared).** For S ∈ {500, 65 536}, run `SimpleStatement st = new SimpleStatement("INSERT INTO " + KEYSPACE + "." + currentTable() + " (k, v) VALUES (" + (1_000_000 + S) + ", 0x" + ByteBufferUtil.bytesToHex(ByteBuffer.wrap(b)) + ")"); st.enableTracing();` and execute it.
8. Arithmetic: S = 65 536 gives an uncut literal of 131 074 chars, 131× the cap. S = 1 MiB gives 2 097 154 chars. Both are far past 1000.

**B2d. Observables and instruments.** For every traced request:
1. `L = tr.getParameters().get(key).length()` (the driver reads these from `system_traces.sessions`).
2. `M`, the persisted total. Read `execute("SELECT parameters FROM system_traces.sessions WHERE session_id = ?", tr.getTraceId()).one().getMap("parameters", UTF8Type.instance, UTF8Type.instance)` (`UntypedResultSet.java:472`) and sum key and value lengths.
3. The suffix check `value.endsWith("...'")`.
4. For the control, `Lq = tr.getParameters().get("query").length()`.
5. Print each as `PROBE kind=<prepared|text|multi|control> S=<S> L=<L> M=<M> Lq=<Lq> uncut=<2S+2>`.
6. Not observable here: the transient heap of the full literal (allocated on a native-transport thread), and SSTable bytes. The cluster tier covers disk.

**B2e. Procedure.**
1. Write the test.
2. Run `ant testsome …` as in B2a.
3. Collect the `PROBE` lines with `grep PROBE build/test/logs/*TraceBoundValueTruncationProbeTest*` or from stdout.
4. Delete `$WORK/cassandra/build/test/cassandra` afterwards.

> **Amendment U2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2b–B2e, exact. One test method, one JVM, sub-runs in this order: prepared blob S = 100, 499, 500, 600, 65 536, 1 048 576 (k = S); prepared text |T| = 998, 999 (k = 2 000 000 + |T|, T drawn from `A–Z a–z 0–9` with `new Random(42)`); multi (k = 3 000 000, the eight 65 536-byte blobs drawn in turn from one `new Random(42)`, keys `bound_var_1_b0` … `bound_var_8_b7`); control S = 500, 65 536 (k = 1 000 000 + S, key `query`). Each blob is `new byte[S]` filled by `new Random(42).nextBytes`. For each traced request the test computes the full literal it expects the server to render from source (blob `"0x" + ByteBufferUtil.bytesToHex(b)`, `BytesSerializer.java:67`; text `"'" + T + "'"`, `TypeSerializer.java:80-85`), and the expected stored value (the full literal if its length ≤ 1000, else its first 1000 chars + `...'`, `ExecuteMessage.java:231-232`; for the control, the query string it sent). It prints one line per value: `PROBE kind=<prepared|text|multi|control> S=<S or |T|> k=<k> key=<key> L=<length of the driver's value> Lint=<length of the same key in the map read by execute()> suffix=<1 if the value ends with ...'> match=<1 if the value equals the expected stored value> M=<sum of key and value lengths over the map read by execute()> R=<M − L> Lq=<length of query> uncut=<full literal length> tbl=<keyspace.table>`; after the eight multi lines one `MULTI M=<M> sumL=<Σ L> R=<M − Σ L>`; a request whose trace cannot be read or whose key is missing prints `TRACEFAIL kind=… S=… err=…` and the test goes on; the last line is `END`. The test asserts nothing; the rows are matched in B2g. M is read with `execute("SELECT parameters FROM system_traces.sessions WHERE session_id = ?", tr.getTraceId())`. The shared `sessionNet()` session is not closed.

**B2f. Predictions.**

| kind | S or \|T\| | L | suffix `...'` | M |
|---|---|---|---|---|
| prepared blob | 100 | 202 | no | M₀ + 202 |
| prepared blob | 499 | 1000 | no | M₀ + 1000 |
| prepared blob | 500 | 1004 | yes | M₀ + 1004 |
| prepared blob | 600 | 1004 | yes | M₀ + 1004 |
| prepared blob | 65 536 | 1004 | yes | M₀ + 1004 |
| prepared blob | 1 048 576 | 1004 | yes | M₀ + 1004 |
| prepared text | 998 | 1000 | no | — |
| prepared text | 999 | 1004 | yes | — |
| multi (8 × 65 536) | — | each 1004 | yes | M₀′ + 8 × 1004 |
| control | 500 | Lq = len(prefix) + 1002 + 1 | — | grows by 2S |
| control | 65 536 | Lq = len(prefix) + 131 074 + 1 | — | grows by 2S |

Notes on the table:
- M₀ is the constant remainder: the `query`, `consistency_level`, `page_size` and `serial_consistency_level` entries plus the key `bound_var_0_k` and its value. It should stay within ±10 chars across the prepared-blob rows, the only change being the digits of k.
- The claim is wrong if any prepared row with S ≥ 500 has L > 1004, or if M grows with S beyond 1004 chars for the value.

> **Amendment U3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2f, exact values from source. **Prepared blob:** S = 100 → L = 202, suffix 0; S = 499 → L = 1000, suffix 0; S = 500, 600, 65 536, 1 048 576 → L = 1004, suffix 1; every line match = 1 and Lint = L. R − digits(k) is the same on all six lines (R holds the other entries, which do not change, the two bound keys and k's digits; the filed ±10 is kept as the refutation tolerance on the spread of R). **Prepared text:** |T| = 998 → L = 1000, suffix 0; |T| = 999 → L = 1004, suffix 1 (the value is `'` + the first 999 chars of T + `...'`); match = 1. **Multi:** each of the eight values L = 1004, suffix 1, match 1; R_multi = M − Σ L ≤ 1004 (no other entry holds a copy of any 131 074-char literal; Σ L = 8 × 1004 = 8032 plus the 7-char k). **Control:** match = 1 (the stored `query` is the sent query, uncut, `QueryMessage.java:138`), so Lq = 40 + |tbl| + 2S (`INSERT INTO ` 12 + |tbl| + ` (k, v) VALUES (` 16 + k 7 + `, 0x` 4 + 2S + `)` 1), and M(control 65 536) − M(control 500) = 2 × (65 536 − 500) = 130 072 exactly (both k have 7 digits).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| L follows the table: flat at 1004 for S ≥ 500, and the control's Lq grows as 2S | Claim confirmed at unit level |
| L = 2S+2 for S ≥ 500 (no cut) | Claim refuted: the check does not bind |
| L flat, but M grows with S | Something else stores the value in the row; claim refuted for the row footprint |
| Multi row sums to 8 × 1004 | Cap is per value, as traced (A3 bypass confirmed) |
| Control Lq does not grow | The control failed (the trace was not taken, or the literal was rejected); not confirmed |
| `getQueryTrace()` times out or the key is missing | Tracing did not happen; rerun with a longer wait. Not confirmed |

> **Amendment U4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B2g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result. **N0 (Not confirmed — tracing not observed; fix and rerun the tier)** (filed row 6): any `TRACEFAIL` line, a missing `PROBE` line (19 are expected: 6 prepared, 2 text, 8 multi, 2 control, plus 1 `MULTI`), or no `END`. **N1 (Not confirmed — the control failed)** (filed row 5): a control line with match ≠ 1, or M(control 65 536) − M(control 500) < 130 062. **W1 (Refuted — does not cap)** (filed row 2): any prepared line with S ≥ 500, the text line |T| = 999 or any multi line has L > 1004. **W2 (Refuted — the row footprint grows)** (filed row 3): the spread (max − min) of R over the six prepared-blob lines is > 10, or R_multi > 1004. **C (Confirmed — caps the persisted trace value per bound value; the cap is per value, as A3 records)** (filed rows 1 and 4): every U3 cell holds. **N2 (Not confirmed — caps, at a boundary or with content other than claimed):** no line is above 1004 but a boundary cell (S = 100, 499, |T| = 998), a suffix or a match cell differs from U3. **N3 (Not confirmed — undetermined):** no row fits; record which cell differs. The unit tier measures persisted chars, not bytes on disk; disk is the cluster tier's.

**B2h. Controls.**
- The boundary pair 499/500 (and 998/999 for text) pins the threshold at exactly 1000 chars.
- The unprepared control uses the same value bytes through the code path with no cut (`QueryMessage.java:138`), so a flat L cannot come from the driver or the server rejecting large values.
- A fixed seed keeps the values reproducible.
- The base-table write is not measured here.

### B3. Cluster tier

**B3a. Environment and build.**
- **Node.** One Linux node from the local clone `$WORK/cassandra` (`ant jar`).
- **Directories.** All on local disk of known free space (≥ 2 GiB): `data_file_directories: [$WORK/node/data]`, `commitlog_directory: $WORK/node/commitlog`, `hints_directory: $WORK/node/hints`, `saved_caches_directory: $WORK/node/saved_caches`, `cdc_raw_directory: $WORK/node/cdc_raw`. Set these in `$WORK/cassandra/conf/cassandra.yaml`.
- **Other yaml settings.** `auto_snapshot: false`, so TRUNCATE leaves no snapshots. Leave `trace_type_query_ttl: 1d`.
- **Heap.** `MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M`.
- **Start.** `bin/cassandra -p $WORK/node/pid`, then wait for `nodetool status` to show `UN`.
- **Client.** The driver bundled for cqlsh: `PYTHONPATH=$WORK/cassandra/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0 python3 probe.py`. If that import fails, use a venv in `$WORK` with `pip install cassandra-driver==3.29.0`.

> **Amendment C1 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3a on this host. There is no `/local`, `setsid` or `du -b`. The node runs from the clone `$W/cassandra-run57` (U1; `ant` is not run in it while a node runs). Node files live under `$W/node-emt` (data, commit log, hints, saved caches, cdc_raw, logs, and a copy of the clone's `conf/` whose `cassandra.yaml` is the shipped one with these lines replaced: `cluster_name: stage4-emt`, `num_tokens: 1`, `initial_token: 0`, `listen_address` and `rpc_address` 127.0.0.1, the five directories, `auto_snapshot: false`; `trace_type_query_ttl` stays 1d, compression and everything else at the shipped defaults). The directory is made fresh at the start and removed at the end. The node is started as a tracked background process: `CASSANDRA_CONF=$W/node-emt/conf CASSANDRA_LOG_DIR=$W/node-emt/logs MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M bin/cassandra -f > node.out 2>&1 < /dev/null &`, and is up when `nodetool status` shows `UN 127.0.0.1` and `nodetool statusbinary` prints `running` (abort if the process dies). The client is `harness/<this stem>/probe.py`, run with the system Python 3.8 and the bundled driver (`sys.path` gets `lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`, as `bin/cqlsh.py` does; checked to import), protocol 5, `DCAwareRoundRobinPolicy`, `token_metadata_enabled=False`, request timeout 300 s.

**B3b. Knobs.**
- S ∈ {499, 500, 65 536, 1 048 576}.
- Path ∈ {prepared EXECUTE (target), unprepared QUERY with an inline literal (control)}.
- The constant itself cannot be set. The varied quantity is how far S passes the cut.

**B3c. Workload.**
1. Run `CREATE KEYSPACE p WITH replication = {'class':'SimpleStrategy','replication_factor':1}; CREATE TABLE p.t (k int PRIMARY KEY, v blob);`.
2. For each (path, S) cell:
   - `TRUNCATE system_traces.sessions; TRUNCATE system_traces.events; TRUNCATE p.t;`
   - Send N traced requests with fresh random blobs: N = 200 for S ≤ 65 536 and N = 20 for S = 1 MiB.
   - Prepared path: `ps = session.prepare("INSERT INTO p.t (k, v) VALUES (?, ?)")`, then `session.execute(ps, (i, os.urandom(S)), trace=True)`.
   - Control path: `session.execute(SimpleStatement("INSERT INTO p.t (k, v) VALUES (%d, 0x%s)" % (i, os.urandom(S).hex())), trace=True)`.
   - Call `rs.get_query_trace(max_wait_sec=10)` per request, so the session row is complete.
3. Arithmetic for the uncut size of the stored values: 200 × 131 074 ≈ 26.2 MB of random hex at S = 65 536, and 20 × 2 097 154 ≈ 41.9 MB at 1 MiB. With the cut, the prepared rows should store 200 × 1004 ≈ 0.2 MB.
4. Each cell takes a few minutes.

> **Amendment C2 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3c, exact. The schema is created once by `probe.py schema` (keyspace `p`, RF 1, table `p.t (k int PRIMARY KEY, v blob)`, then a 5-s schema settle). Each cell is one `probe.py cell <path> <S> <N>` call, in one node lifetime: (1) `TRUNCATE system_traces.sessions`, `TRUNCATE system_traces.events`, `TRUNCATE p.t` through the driver; (2) for i = 0 … N − 1, a fresh `os.urandom(S)` blob b and one traced request — prepared: `session.execute(ps, (i, b), trace=True)` with `ps = session.prepare("INSERT INTO p.t (k, v) VALUES (?, ?)")` prepared once per call (untraced); control: `session.execute(SimpleStatement("INSERT INTO p.t (k, v) VALUES (%d, 0x%s)" % (i, b.hex())), trace=True)` — followed by `rs.get_query_trace(max_wait_sec=10)`; (3) per request the client checks the trace parameters it got back against the value it expects from source (U2's rule: prepared, the full literal `0x` + hex if ≤ 1000 chars, else its first 1000 chars + `...'`; control, the sent query) and prints one `REQ path= S= i= key= len= suffix= match=` line; a request that raises, or whose trace is unavailable or lacks the key, prints `REQFAIL` with the error. N = 200 for S ≤ 65 536 and N = 20 for S = 1 048 576, as filed. The cell ends with `CELL path= S= N= ok= fail= nmatch= maxlen= minlen= nsuffix= secs=`.

**B3d. Observables and instruments.** Take these after each cell:
1. `nodetool flush system_traces`.
2. `du -sb $WORK/node/data/system_traces/sessions-*/` (excluding `snapshots` and `backups`).
3. `nodetool tablestats system_traces.sessions` "Space used (live)".
4. From the client, `SELECT session_id, parameters FROM system_traces.sessions`: the per-row max and sum of value lengths, plus the max length of the `bound_var_1_v` entries and of the `query` entries.
5. Record `nodetool tablestats p.t` "Space used (live)" as context only.
6. Not observable: the transient heap of the full literal on the coordinator. To look at it anyway, take a JFR allocation profile (`jcmd <pid> JFR.start settings=profile duration=60s filename=$WORK/alloc.jfr`) during the S = 1 MiB prepared cell, and look for `CQL3Type$Native.toCQLLiteral` allocations of about 2 MiB per request. Its presence confirms that the transient heap is uncapped (A3, step 6); it does not change the claim.

> **Amendment C3 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3d on this host, exact. After each cell: (a) `nodetool flush system_traces` and `nodetool flush p`; (b) **Dsess** = the sum of the byte sizes (`stat -f %z`) of every file under `data/system_traces/sessions-*/` outside `snapshots/` and `backups/` (BSD has no `du -b`), with the file list kept; **Dev** and **Dpt** the same for `events-*` and `p/t-*` (context only); (c) `nodetool tablestats system_traces.sessions` and `p.t`, `Space used (live)` (bytes, `-H` not used); (d) `probe.py scan`: `SELECT session_id, parameters FROM system_traces.sessions` with fetch size 5, printing per row the length of `bound_var_1_v` (or −1 when absent), whether it ends with `...'`, the length of `query`, and the sum of all value lengths, then `SCAN rows= nbv= maxbv= minbv= nbvsuffix= maxq= minq= sumv=`. Before each cell's workload and after its TRUNCATEs the same Dsess is taken as **D0** (a control that the cell starts from an empty table). **Item 6 (JFR) is informational and no row depends on it:** `jcmd <pid> JFR.start name=emt settings=profile filename=$W/logs/<this stem>/<run>/alloc.jfr` immediately before the prepared S = 1 MiB cell and `jcmd <pid> JFR.stop name=emt` after it (instead of a fixed 60-s duration, so the window is the cell); then `jfr print --events jdk.ObjectAllocationOutsideTLAB --stack-depth 64` and count **T** = the events with allocation size ≥ 1 MiB whose stack has a `toCQLLiteral` frame.

**B3e. Procedure.**
1. Build, configure and start the node as in B3a.
2. Create the schema.
3. For each cell in the order (prepared 499, prepared 500, prepared 65 536, prepared 1 MiB, control 65 536, control 1 MiB): truncate, run the workload, flush, take the readings.
4. Stop the node: `kill $(cat $WORK/node/pid)`.
5. Check that `pgrep -f CassandraDaemon` is empty.

> **Amendment C4 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3e, exact. (1) Make `$W/node-emt`, start the node (C1), record the `Node configuration` line (auto_snapshot, trace_type_query_ttl), idle 30 s. (2) `probe.py schema`. (3) Cells in the filed order P499, P500, P65536, P1M (JFR around it, C3), Q65536, Q1M (P = prepared, Q = control), each as D0 → cell (C2) → readings (C3). Stop condition: a cell whose `CELL` line has fail > 0 is recorded and the run goes on; the rows decide (C6). (4) Copy `system.log`, stop the node (`nodetool stopdaemon`, then `kill` after 60 s, then `kill -9`), check that `ps -eo command | grep '[C]assandraDaemon'` is empty and remove `$W/node-emt`. A shakedown with N = 5 per cell on a throw-away node precedes run 1 and is not a reading.

**B3f. Predictions.**
- **Per-row stored value.** Prepared cells: `bound_var_1_v` is 1000 chars at S = 499 and 1004 chars at every S ≥ 500. Control cells: `query` length is 2S + 2 + about 40 chars for every row.
- **Sessions table on disk after flush.**
  - Prepared S = 65 536 and S = 1 MiB are both < 1 MiB.
  - Prepared S = 65 536 is within 2× of prepared S = 500, since the row size is the same.
  - Control S = 65 536 is ≥ 13 MB, that is, ≥ 0.5 × 26.2 MB. Random hex has no repeats for LZ4 to remove, so it should be close to 26 MB.
  - Control S = 1 MiB (N = 20) is ≥ 20 MB.
- **Ratio.** Control 65 536 ÷ prepared 65 536 on disk is ≥ 10×.
- **When the claim is wrong.** Prepared S = 65 536 sessions on disk ≥ 5 MB, or any stored `bound_var_1_v` longer than 1004 chars.

> **Amendment C5 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3f, exact, from source; the filed numbers are kept. **Per request (client, C2):** P499 every value L = 1000, suffix 0, match 1; P500, P65536, P1M every value L = 1004, suffix 1, match 1; Q65536 and Q1M every stored `query` equals the sent query, L = 36 + digits(i) + 2S (131 109–131 111 at 65 536; 2 097 189–2 097 190 at 1 MiB). **Per cell (scan, C3):** rows = N; for P cells nbv = N and maxbv = 1000 (P499) or 1004 with nbvsuffix = N (S ≥ 500). **Disk (Dsess):** P65536 < 1 048 576 B and P1M < 1 048 576 B; P65536 ≤ 2 × P500; Q65536 ≥ 13 107 400 B (0.5 × 200 × 131 074); Q1M ≥ 20 000 000 B; Q65536 / P65536 ≥ 10; D0 = 0 B before every cell (no sstable left after TRUNCATE with `auto_snapshot: false`). **T** (informational): ≥ 1. The filed refutation thresholds stay: P65536 ≥ 5 000 000 B, or any stored `bound_var_1_v` longer than 1004.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Prepared sessions size flat across S ≥ 500 (< 1 MiB); control grows to tens of MB | Claim confirmed: the literal cap bounds trace disk usage per bound value |
| Prepared sessions size grows about linearly with S | Claim refuted |
| Both prepared and control stay small | The control failed (tracing not recorded, or rows expired or truncated); not confirmed |
| Base table `p.t` grows with S in both paths | Expected: the cap covers only the trace copy |
| `bound_var_1_v` missing | The trace was not taken via ExecuteMessage; check the driver used EXECUTE (prepared) |

> **Amendment C6 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B3g, rows with verdicts (Effect in brackets), checked in this order; the first matching row is the result. **I (Invalid run):** the node did not start, a cell did not run, or D0 > 0 before a cell. **N0 (Not confirmed — trace not taken via EXECUTE)** (filed row 5): any P-cell request with `REQFAIL`, or a P-cell scan with nbv < N. **N1 (Not confirmed — the control failed)** (filed row 3): Q65536 < 13 107 400 B or Q1M < 20 000 000 B, or a Q-cell request failed or did not match. **W1 (Refuted — does not cap)** (filed row 2 and B3f's last bullet): any stored `bound_var_1_v` longer than 1004 (client or scan), or P65536 ≥ 5 000 000 B. **C (Confirmed — caps the trace disk usage per bound value)** (filed row 1): every C5 per-request, per-cell and disk prediction holds; the 1004-char values ending in `...'` that equal the first 1000 chars of the literal are the direct evidence that the line-231 branch fired. **N2 (Not confirmed — undetermined):** no row fits (for example P65536 between 1 048 576 and 5 000 000 B); record which condition failed. Filed row 4 (`p.t` grows with S in both paths) is context, not a verdict row: Dpt and `p.t` live space are recorded.

**B3h. Controls.**
- The unprepared-literal path carries the same value bytes through the path with no cut (`QueryMessage.java:138`): it is the positive control showing the workload can move sessions disk usage.
- Truncating between cells, with `auto_snapshot: false`, isolates each cell.
- Flushing before measuring makes the on-disk bytes comparable.
- Fresh `os.urandom` blobs defeat compression.
- The 499/500 pair pins the threshold.

**B4. Risks and cleanup.**
- **Disk.** The worst case is about 60 MB for traces plus about 250 MB for `p.t` and the commit log, all under `$WORK/node`. Check free space before starting.
- **Shared clone.** Never build in, or add files to, the shared clone `/Users/yangwang/cassandra-src`.
- **Processes.** After the unit tier, check that no forked test JVM remains (`pgrep -f CQLTester`). After the cluster tier, stop the daemon and check `pgrep -f CassandraDaemon`.
- **Cleanup.** `rm -rf $WORK/node $WORK/alloc.jfr`, and remove the probe test from the local clone.

> **Amendment C7 (2026-10-27, stage-4 step-0 audit, before any harness run or reading).** B4 on this host: nothing goes into `~/cassandra-src`; node files are under `$W/node-emt` and are removed at the end; full logs (including `alloc.jfr`) stay in `$W/logs/<this stem>/`. The node listens on 127.0.0.1 only. The scripts stop the node they started and check that `ps -eo command | grep '[C]assandraDaemon'` is empty; the unit script checks that no test JVM is left (`pgrep -f TraceBoundValueTruncationProbeTest`) and removes the copied test so that the clone's `git status` is clean.

## C. Sources read

- `src/java/org/apache/cassandra/transport/messages/ExecuteMessage.java`
- `src/java/org/apache/cassandra/transport/messages/QueryMessage.java`
- `src/java/org/apache/cassandra/transport/messages/BatchMessage.java`
- `src/java/org/apache/cassandra/transport/Message.java`
- `src/java/org/apache/cassandra/tracing/TracingImpl.java`
- `src/java/org/apache/cassandra/tracing/TraceKeyspace.java`
- `src/java/org/apache/cassandra/tracing/Tracing.java`
- `src/java/org/apache/cassandra/service/StorageService.java`
- `src/java/org/apache/cassandra/cql3/CQL3Type.java`
- `src/java/org/apache/cassandra/cql3/UntypedResultSet.java`
- `src/java/org/apache/cassandra/serializers/TypeSerializer.java`
- `src/java/org/apache/cassandra/serializers/BytesSerializer.java`
- `src/java/org/apache/cassandra/serializers/AbstractTextSerializer.java`
- `test/unit/org/apache/cassandra/cql3/TraceCqlTest.java`
- `test/unit/org/apache/cassandra/cql3/CQLTester.java`
- `conf/cassandra.yaml`
- `CHANGES.txt`
- `bin/cqlsh.py`
- https://issues.apache.org/jira/browse/CASSANDRA-11719

## D. Stage-4 feedback

**2026-10-27, stage 4 run 1** (advisor's Mac; results: [`results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md`](../../stage4-runtime-verification/results/ExecuteMessage_literal_1000-traceQuery-1000--autonomous.md); frozen version sha256 `3b910462a6295b00624c89e3376a43ab84112ae39a9152c196dd86dcf0256466`, after the audit's amendments U1–U4 and C1–C7; uncommitted at the time of the run). **Unit: Confirmed — caps** (U4 row C): the persisted value was 202 / 1000 chars below the cut and exactly 1004 chars (the first 1000 chars of the literal + `...'`) at S = 500, 600, 65 536 and 1 MiB and at |T| = 999; the rest of the row stayed constant (R − digits(k) = 165); eight 64 KiB values cost 8 × 1004 chars; the unprepared control stored the query uncut (ΔM = 130 072 chars exactly). **Cluster: Confirmed — caps per bound value** (C6 row C): every stored `bound_var_1_v` was 1000 chars at S = 499 and exactly 1004 (content-matched) at S ≥ 500; `system_traces.sessions` held 220 882 / 220 148 B after 200 traced requests at S = 500 / 65 536 and 27 834 B after 20 at 1 MiB, against 25 491 511 B and 40 704 895 B for the unprepared control (115.8× at 64 KiB). Informational: a JFR allocation profile of the 1 MiB cell showed 3 allocations ≥ 1 MiB per request (a 4 MB `char[]` in `Hex.bytesToHex`) under `ExecuteMessage.traceQuery` line 230, before the check, as A3 step 6 says (the transient heap is not capped; recommendation S2). Audit findings for stage 3: the predictions needed exact values (M₀ and the control prefix were unknowns), the readings tables had no verdict rows, and the cluster runbook used Linux-only commands; all were fixed by U1–U4 and C1–C7 before any reading. No runbook defect.
