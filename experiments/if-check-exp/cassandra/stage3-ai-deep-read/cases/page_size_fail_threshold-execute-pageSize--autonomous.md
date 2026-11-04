# page_size_fail_threshold (guardrail) — verification solution  <!-- file: cases/page_size_fail_threshold-execute-pageSize--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SelectStatement.java:338`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java#L338), `:338#2`, `:602#1`, `:602#2` (`pageSize <= 0`, `query.limits().count() <= pageSize`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Opus 5.5 (`claude-opus-5-5`), Claude Code at Meta (version string n/a), 2026-10-26; Band D triage mode |
| Estimate | `undetermined`. The guardrail caps rows per page only on the paged branch. These four checks send paging-off queries, and queries whose LIMIT is at most the page size, to the unpaged branch, where `Guardrails.pageSize.guard` (`:517`) is never called. The row cap is also a count, not bytes. Whether coordinator heap per response follows the threshold therefore depends on the branch, and stage 4 should measure both. |
| Ground | — (the expected partial result is: capped on the paged branch, not capped on the branches these checks select) |

## A. Constraint trace

**A1. The constraint.** The `page_size` guardrail: config entries `page_size_warn_threshold` and `page_size_fail_threshold`.
- Declared at [`Config.java:873-874`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L873-L874) as `volatile int` with default `-1`, which means disabled.
- The unit is rows per page, the native-protocol fetch size.
- Commented out in `conf/cassandra.yaml:2089-2090`.
- Guardrail object: [`Guardrails.java:237-246`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L237-L246).
- Settable at runtime through the JMX `GuardrailsMBean.setPageSizeThreshold(warn, fail)` ([`GuardrailsMBean.java:335`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java#L335); [`Guardrails.java:874`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrails.java#L874)). A yaml change needs a restart.
- It applies only to ordinary users. `Guardrail.enabled` returns false for internal and superuser client states, and when the daemon is not initialised ([`Guardrail.java:93-96`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L93-L96)).


**Limit type (2026-10-29).** config: yaml entry. The traced constraint decides ([README §6](../README.md#6-rules-that-hold-for-both-agents)).
**A2. What it caps.** It caps the client-requested page size that the coordinator uses for a paged SELECT, and with it the rows the coordinator materializes and returns per response. The resource is coordinator heap, and also replica heap for the read response. The compared value is `pageSize` from `QueryOptions.getPageSize()` (`SelectStatement.java:291`, `:586`).

**A3. Mechanism.**
- Client path, `SelectStatement.execute` (`:280-361`):
  - Target `:338`: `if (aggregationSpec == null && (pageSize <= 0 /*#1*/ || query.limits().count() <= pageSize /*#2*/ || query.isTopK()))` runs the query unpaged: `execute(query, ...)` → `query.execute(...)` → `processResults`, which builds the whole result in one `ResultMessage.Rows` (`:340`, `:417-431`).
  - Otherwise the paged `execute(state, Pager, ...)` runs (`:344-355`). Its first statement is `Guardrails.pageSize.guard(pageSize, table(), false, clientState)` (`:517`).
  - `Threshold.guard` fails when value > fail, by throwing `GuardrailViolatedException` ([`Threshold.java:128-138`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L128-L138), [`Guardrail.java:140`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Guardrail.java#L140)), and warns when value > warn ([`Threshold.java:140-142`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/guardrails/Threshold.java#L140-L142)).
- Internal / NODE_LOCAL path, `executeInternal` (`:579-623`): the same predicate at target `:602` selects the unpaged `executeInternal` (`:604-607`) or the paged `execute` (`:612-621`), and only the latter reaches `:517`.
  - Plain internal callers use `QueryOptions.forInternalCalls`, whose page size is `-1` ([`QueryOptions.java:62-75`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryOptions.java#L62-L75), `:540`), so they always take the unpaged branch. The guardrail is disabled for them anyway.
  - Client NODE_LOCAL selects reach `executeLocally` → `executeInternal` with client options ([`QueryProcessor.java:312-327`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/QueryProcessor.java#L312-L327), gated by `-Dcassandra.enable_nodelocal_queries=true`, `:283`).
- Bypasses:
  - (#1) paging off: no row cap at all;
  - (#2) LIMIT L with L ≤ pageSize: a pageSize above the fail threshold is accepted and L rows come back in one response, even if L is far above the threshold;
  - TopK queries;
  - superusers and internal callers.
- The existing test `test/unit/org/apache/cassandra/db/guardrails/GuardrailPageSizeTest.java` asserts the LIMIT ≤ pageSize case is valid ("query with limit under thresholds": `LIMIT 1` with page size 11 > fail 10 is valid). So bypass #2 is intended for small limits, but no limit is placed on L itself.

**A4. Other consumers.** Other things that use coordinator and replica heap for reads:
- `local_read_size_*` and `coordinator_read_size_*` read thresholds (only when `isReadThresholdsEnabled`, `:334-335`);
- tombstone thresholds;
- concurrent requests;
- the native transport queue limits.

**A5. Evidence beyond the source.** `GuardrailPageSizeTest` (above) and the `conf/cassandra.yaml:2085-2090` comment block.

## B. Verification solution

**B1. Claim under test.** For an ordinary user with `page_size_fail_threshold = T`:
- A paged SELECT with fetch size > T is rejected, and one with fetch size ≤ T returns at most fetch-size rows per response.
- A SELECT with paging off, or with LIMIT L ≤ fetch size, is not checked against T. It returns all its rows (up to L) in one response, and the coordinator heap grows with that response size, not with T.

### B2. Unit tier

**B2a. Environment and build.**
1. Clone to local disk: `export WORK=/local/$USER/c509; git clone /path/to/shared/cassandra-src $WORK/cassandra; cd $WORK/cassandra; git checkout cassandra-5.0.9`.
2. Use JDK 11 and run `ant jar`.
3. Add the test file `test/unit/org/apache/cassandra/db/guardrails/PageSizeBranchProbeTest.java`, which extends `ThresholdTester` with the same constructor arguments as `GuardrailPageSizeTest`: `Guardrails.pageSize`, `Guardrails::setPageSizeThreshold`, and the getters. That gives it `userClientState`, an ordinary logged-in user, and a daemon-initialized guardrail setup.
4. Run `ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.PageSizeBranchProbeTest`.

> **Amendment B2a (2026-10-26, stage-4 audit, before any reading).** `/local` and `/path/to/shared` do not exist on the advisor's machine
> (`stage4-runtime-verification/environment-advisor.md`). Clone: `source ~/Library/Caches/stage4/env.sh` (JDK 11), then
> `git clone --branch cassandra-5.0.9 ~/cassandra-src $W/cassandra-run33` and `ant -Dlocal.repository=$W/m2 build-test` (not
> `ant jar`: `testsome` needs the test classes; every `ant` call takes `-Dlocal.repository=$W/m2`). The probe is
> `stage4-runtime-verification/harness/page_size_fail_threshold-execute-pageSize--autonomous/PageSizeBranchProbeTest.java`; `unit-run.sh` in the same folder copies it into the clone, runs step 4 and removes it.
> No change is needed for the user: `GuardrailTester.setUpClass` calls `requireAuthentication()` and `requireNetwork()`
> (`GuardrailTester.java:112-131`), so `userClientState` is an ordinary user under `PasswordAuthenticator` (`ClientState.java:594-605`).

**B2b. Knobs.** (warn, fail) ∈ {(5, 10), (500, 1000)}, set with `Guardrails.instance.setPageSizeThreshold(w, f)` in `@Before`.

> **Amendment B2b (2026-10-26, stage-4 audit, before any reading).** A third pair, **(−1, −1)**, the default (`Config.java:873-874`, disabled), is added so the knob takes
> three values including the default (group A). Order: (5, 10), (500, 1000), (−1, −1). The probe has one test method that loops
> over the pairs, so each pair is set inside the loop with `Guardrails.instance.setPageSizeThreshold(w, f)` (not in `@Before`), and
> read back: `PROBE readback warn=<w> fail=<f> getWarn=<getPageSizeWarnThreshold()> getFail=<getPageSizeFailThreshold()>` must
> show the values set.

**B2c. Workload.**
- Table: `CREATE TABLE %s (k int, c int, v text, PRIMARY KEY (k, c))` with 2000 rows: k=0, c=0..1999, v = a 100-char string.
- Each query is run through two entry points, both with `userClientState`:
  - **(D)** the client path: `((SelectStatement) QueryProcessor.parseStatement(q, state)).execute(new QueryState(state), QueryOptions.create(ConsistencyLevel.ONE, List.of(), false, P, null, null, ProtocolVersion.CURRENT, KEYSPACE), Dispatcher.RequestTime.forImmediateExecution())`, which reaches target `:338`;
  - **(L)** `statement.executeLocally(new QueryState(state), sameOptions)`, which reaches target `:602`. This is the `GuardrailPageSizeTest.executeWithPaging` pattern.
- Cases (P = page size):
  - c1: `SELECT * FROM %s WHERE k=0`, P=3
  - c2: same, P=11
  - c3: same, P=-1 (paging off)
  - c4: `... LIMIT 2000`, P=2000
  - c5: `... LIMIT 2001`, P=2000
  - c6: same as c2 but with `superClientState`
- Arithmetic: with fail=10, c2, c4 and c5 have P > 10, and c3 has no P. 2000 rows is 200× the threshold.

> **Amendment B2c (2026-10-26, stage-4 audit, before any reading).**
> 1. `v` is a fixed 100-character string (`a`…`z` repeated); the 2000 rows are inserted with `CQLTester.execute` (an internal call,
>    not subject to the guardrail) and read back with `SELECT count(*)`: `PROBE table <t> rows=2000`.
> 2. Cases c1–c6 run at every threshold pair and both entry points: 3 × 2 × 6 = 36 cases.
> 3. The unit yaml enables read thresholds (`test/conf/cassandra.yaml:63-67`); a node with the default yaml has none. They are another
>    consumer (A4), and their warnings would land in observable (d). The probe turns them off first
>    (`DatabaseDescriptor.setReadThresholdsEnabled(false)`) and prints
>    `PROBE setup readThresholdsEnabled=false userOrdinary=true superOrdinary=false daemonInitialized=true`.

**B2d. Observables and instruments.** For each case record:
- (a) whether it threw `GuardrailViolatedException` / `InvalidRequestException` with "Aborting query ... page size";
- (b) `rows.result.size()`, the rows in the response;
- (c) whether `rows.result.metadata.getPagingState() != null`, meaning more pages;
- (d) captured client warnings (`ClientWarn.instance.captureWarnings()` before, `getWarnings()` after).

Which branch was taken is not observable directly. It is inferred from (a) and (d), because the guard is the only consumer of the threshold.

> **Amendment B2d (2026-10-26, stage-4 audit, before any reading).** One line per case:
> `PROBE case thr=<w>:<f> entry=<D|L> case=<cN> P=<P> state=<user|super> rows=<n> hasMore=<b> pageSizeWarnings=<n> warnings=<n> threw=[<class>: <message>] warntext=[…]`
> (`rows=-1 hasMore=na` when it threw). `pageSizeWarnings` counts captured warnings that contain "page size" and "exceeds warning
> threshold" (the warn text, `Guardrails.java:242-244`). A failure also puts its message in `ClientWarn` (`Guardrail.java:133`), so a
> throwing case has `warnings=1`. Stdout lands in `build/test/logs/.../TEST-<class>.log`, one line per `println`; `unit-run.sh` copies it.
> Supporting disallow evidence: each fail logs `ERROR … Guardrail page_size violated: Aborting query …`, but the guardrail logger
> is a `NoSpamLogger` with a 10-minute interval per message (`Guardrail.java:47-48`), so the tier logs one ERROR line per distinct
> message: 3 (`11`/`10`, `2000`/`10`, `2000`/`1000`), and no `page_size` WARN line. Gap: the unit tier counts rows per response, not
> heap bytes (each row carries a 100-byte value).

**B2e. Procedure.**
1. Write the test with a loop over (thresholds, entry point, case) that prints `thr,entry,case,P,threw,rows,hasMore,warnings`.
2. Run it, then collect the output.

> **Amendment B2e (2026-10-26, stage-4 audit, before any reading).** Run `stage4-runtime-verification/harness/page_size_fail_threshold-execute-pageSize--autonomous/unit-run.sh` with no argument. It logs each command, keeps `ant.log`, `TEST.log` and the `PROBE`
> lines under `$W/logs/page_size_fail_threshold-execute-pageSize--autonomous/unit/`, and removes the probe, so the clone's
> `git status` is clean afterwards.

**B2f. Predictions.** Same for (D) and (L):

| Case | fail = 10 | fail = 1000 |
|---|---|---|
| c1 | rows 3, hasMore true | — |
| c2 | throws | rows 11, hasMore true, no warning |
| c3 | no throw; rows 2000; hasMore false; no warning | rows 2000 |
| c4 | no throw; rows 2000; no warning (P = 2000 > 10 not checked) | no throw; rows 2000; no warning (P = 2000 > 1000 not checked) |
| c5 | throws | throws |
| c6 | rows 11 (superuser exempt) | — |

> **Amendment B2f (2026-10-26, stage-4 audit, before any reading).** The table above leaves cells blank and has no (−1, −1) column. Full predictions, the same for (D) and (L):
>
> | Case | fail = 10 (warn 5) | fail = 1000 (warn 500) | fail = −1 (default) |
> |---|---|---|---|
> | c1 (P 3) | rows 3, hasMore true | rows 3, hasMore true | rows 3, hasMore true |
> | c2 (P 11) | throws `GuardrailViolatedException` "… page size 11 exceeds fail threshold of 10." | rows 11, hasMore true | rows 11, hasMore true |
> | c3 (paging off) | rows 2000, hasMore false | rows 2000, hasMore false | rows 2000, hasMore false |
> | c4 (LIMIT 2000, P 2000) | rows 2000, hasMore false | rows 2000, hasMore false | rows 2000, hasMore false |
> | c5 (LIMIT 2001, P 2000) | throws "… page size 2000 exceeds fail threshold of 10." | throws "… page size 2000 exceeds fail threshold of 1000." | rows 2000, hasMore true (paged; the pager is not exhausted after exactly 2000 of LIMIT 2001: `AbstractQueryPager.java:200, 235-237`, `DataLimits.java:139-142`) |
> | c6 (P 11, superuser) | rows 11, hasMore true | rows 11, hasMore true | rows 11, hasMore true |
>
> Every case that does not throw has `pageSizeWarnings=0` (no paged user case has warn < P ≤ fail). Six of the 36 cases throw.
> Validity lines: the setup line as in amendment B2c, `rows=2000`, the three read-backs, `PROBE done cases=36`, and Ant reports no
> failure or error.

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| c2 and c5 throw while c3 and c4 return 2000 rows | Guardrail binds only on the paged branch; the claim is confirmed |
| c3 or c4 throw or warn | The guardrail is enforced on the unpaged branch; claim wrong (the cap covers these branches) |
| c2 does not throw at fail=10 | Guardrail not active in the harness (e.g. superuser or daemon not initialized); not confirmed, so fix the harness |
| (D) and (L) differ | `:338` and `:602` behave differently; report it |

> **Amendment B2g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows:
> - Row 1 → **Confirmed**: all 36 cells match amended B2f. In particular, c2 and c5 throw where predicted, while c3 and c4 return
>   2000 rows with no throw and no page-size warning at fail 10 and 1000.
> - Row 2 → **Refuted**.
> - Row 3 → **Invalid** (harness): a runbook defect, and the tier restarts.
> - Row 4 → **Not confirmed**: B1 and B2f say both entry points behave the same. The Effect is read per entry point.
> - Added: the setup line, the table rows, a read-back or the case count differs from amended B2f → **Invalid**.
> - Added: any other cell differs from amended B2f (for example c6 throws, c1 has rows ≠ 3, or c5 at −1 is not paged) →
>   **Not confirmed**, and the case goes back to stage 3 as feedback.
> - The ERROR-line count (amendment B2d) is supporting evidence. A mismatch is recorded but does not change the row.
> - **Effect rule:** Confirmed → **caps only on some paths (bypass)**; Refuted → **caps**; otherwise **undetermined**.

**B2h. Controls.**
- c1, c2 and c5 are the positive control: the same table and user, where the cap is known to bind.
- c6 checks that the user exemption works as traced.
- Raising fail to 1000 shows the c2 rejection is caused by the threshold.

> **Amendment B2h (2026-10-26, stage-4 audit, before any reading).** The (−1, −1) pair, the default, shows that c2 and c5 pass when the guardrail is off. So their rejections
> come from T, and the same queries return 11 and 2000 rows.

### B3. Cluster tier

**B3a. Environment and build.**
1. One Linux node from the local clone (B2a).
2. `conf/cassandra.yaml`:
   - all data, commitlog, hints, saved_caches and cdc directories under `$WORK/node/` on local disk with at least 5 GiB free;
   - `authenticator: PasswordAuthenticator`, `authorizer: CassandraAuthorizer`;
   - `page_size_warn_threshold: 500`, `page_size_fail_threshold: 1000`.
3. In `conf/jvm-server.options`, add `-Xlog:gc*:file=$WORK/node/gc.log:time,uptime` with the literal path written out.
4. Heap: `export MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`.
5. Start with `bin/cassandra -p $WORK/node/pid`.
6. Client: python3 with `PYTHONPATH=$WORK/cassandra/lib/cassandra-driver-internal-only-3.29.0.zip/cassandra-driver-3.29.0`; check with `python3 -c 'import cassandra'`, and fall back to a venv with `cassandra-driver==3.29.0`.

> **Amendment B3a (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine:
> - `$WORK/cassandra` is `$W/cassandra-run33` (built as in amendment B2a, no probe left in it).
> - `$WORK/node` is `$W/node-psf`, with its own copy of `conf/` (`CASSANDRA_CONF`) and `CASSANDRA_LOG_DIR=$W/node-psf/logs`.
> - The overrides are appended to the node's yaml: the directories, `listen_address`/`rpc_address: 127.0.0.1`,
>   `authenticator: PasswordAuthenticator`, `authorizer: CassandraAuthorizer`, `page_size_warn_threshold: 500`,
>   `page_size_fail_threshold: 1000`, and **`read_request_timeout: 60000ms`**.
>   - The timeout is raised because the coordinator waits `read_request_timeout` (5000 ms, `conf/cassandra.yaml:1322`) for the
>     single local response (`ReadCallback.java:100`), and Q3's response is built in one heap buffer of about 205 MB
>     (`ReadResponse.java:197-203`). A timeout fits no B3g row.
>   - The driver's request timeout is 120 s.
>   - Neither setting changes what T checks.
> - Step 3: `-Xlog:gc*:file=$W/node-psf/gc.log:time,uptime` (literal path) goes into the node's `jvm-server.options`. Then
>   `cassandra-env.sh` adds no GC log of its own (`cassandra-env.sh:78-83`).
> - Step 4 stays as filed. The node runs G1 with 16 MiB regions (`jvm11-server.options:63, 66`), and G1 ignores `HEAP_NEWSIZE`
>   (`cassandra-env.sh:125-127`).
> - Step 5: there is no `setsid` on this host, so the node is a tracked background `bin/cassandra -f > node.out 2>&1 < /dev/null`.
>   It is ready when `nodetool status` shows `UN` and `nodetool statusbinary` prints `running`.
> - Step 6: the filed `PYTHONPATH` form imports the driver (`run1/stepE.txt`). The driver uses protocol 5,
>   `DCAwareRoundRobinPolicy`, token and schema metadata off, heartbeat off, and `PlainTextAuthProvider`.

**B3b. Knobs.**
- Main value: fail threshold T = 1000.
- Repeat once with the guardrail disabled (`-1` for both thresholds) as a baseline. It can be set over JMX with `bin/nodetool sjk mx -b org.apache.cassandra.db:type=Guardrails -mc -op setPageSizeThreshold -a -1 -1`, or with a yaml change and a restart.

> **Amendment B3b (2026-10-26, stage-4 audit, before any reading).** Three values in one node lifetime, giving group A's three values including the default:
> - **T = 1000** (warn 500), from the yaml as filed.
> - **T = 10000** (warn 5000), set over JMX.
> - **T = −1** (warn −1, the default, disabled), set over JMX. It replaces the filed "disabled" repeat, and all five queries run at
>   it (a superset of "repeat Q2 and Q5").
>
> The JMX values are set with `GuardrailsMBean.setPageSizeThreshold(warn, fail)` (`Guardrails.java:874`) through the harness's JMX
> client `PsJmx`, not `nodetool sjk mx`, which exits 0 on failure. Read-backs: each value through the `PageSizeWarnThreshold` /
> `PageSizeFailThreshold` attributes at the start and end of its phase, and the yaml value also from the startup configuration line.

**B3c. Workload.**
- As `cassandra`/`cassandra`, create:
  - `CREATE ROLE app WITH PASSWORD='app' AND LOGIN=true` (not a superuser);
  - `CREATE KEYSPACE p WITH replication={'class':'SimpleStrategy','replication_factor':1}`;
  - `CREATE TABLE p.wide (k int, c int, v blob, PRIMARY KEY (k,c)) WITH compression={'enabled':false}`;
  - `GRANT SELECT ON KEYSPACE p TO app`.
- Load one partition with k=0, c=0..99,999 and v = 2 KiB of `os.urandom`, about 200 MiB, using prepared inserts at concurrency 32. Then `nodetool flush p wide`.
- Queries, run as `app` by `probe.py <fetch_size|off> <limit|none>`, each run 3 times:
  - Q1: fetch 500, no limit; read only the first page.
  - Q2: fetch 2000, no limit.
  - Q3: paging off (`session.default_fetch_size=None` and `SimpleStatement(..., fetch_size=None)`), no limit.
  - Q4: fetch 50,000, `LIMIT 50000`.
  - Q5: fetch 50,000, `LIMIT 50001`.
- Arithmetic: Q3 materializes about 100,000 × 2 KiB ≈ 200 MiB in one response, and Q4 about 100 MiB, against T = 1000 rows (≈ 2 MiB).

> **Amendment B3c (2026-10-26, stage-4 audit, before any reading).**
> 1. The query text is not given. It is `SELECT k, c, v FROM p.wide WHERE k = 0` with ` LIMIT n` for Q4 and Q5: the single loaded
>    partition, as in the unit tier. Without `WHERE k = 0` it would be a range read, a different code path.
> 2. Load:
>    - As `cassandra`, a prepared `INSERT INTO p.wide (k, c, v) VALUES (0, ?, ?)` for c = 0..99,999, with v = `os.urandom(2048)`,
>      sent by `execute_concurrent_with_args` with concurrency 32.
>    - The setup client retries the login until the default superuser exists (created about 10 s after the first start,
>      `CassandraRelevantProperties.java:538`).
>    - Setup prints `app`'s `is_superuser` (must be `False`) and its permissions.
> 3. `probe.py q <fetch|off> <limit|none>` reads only the first page in every query. It prints:
>    - the outcome, the first-page rows, `has_more` and the value bytes;
>    - the page-size warnings in the response (`response_future.warnings`);
>    - the error class and message.
> 4. Every query runs at every T, in the order Q1 ×3, Q2 ×3, …, Q5 ×3.

**B3d. Observables and instruments.**
- Client: the exception class and message, `len(rs.current_rows)` for the first page, and `rs.has_more_pages`.
- Server heap:
  - `jstat -gc $(cat $WORK/node/pid) 100 > jstat_Qn.txt` during each query; take the peak of (S0U+S1U+EU+OU) minus the 2-second pre-query median;
  - G1 humongous allocations in `gc.log` ("Humongous regions" before/after) in the query window.
- Rows-read counter: `bin/nodetool sjk mx -b org.apache.cassandra.metrics:type=ClientRequestSize,name=RowsRead -mg -f Count` before and after.
- What cannot be seen directly: the per-response byte size on the server. It is inferred from the heap peak and the client row count.

> **Amendment B3d (2026-10-26, stage-4 audit, before any reading).**
> 1. `jstat` cannot attach on this host. Heap is read over JMX by `PsJmx poll`: `java.lang:type=Memory` `HeapMemoryUsage.used`
>    every 100 ms into `heap.tsv`, the same quantity as jstat's S0U+S1U+EU+OU. G1 reports eden in whole 16 MiB regions, so the
>    resolution is 16 MiB.
> 2. **Heap peak delta** of a query = the largest sample in [probe start, probe end + 3 s] minus the median of the samples in the
>    2 s before the probe starts. The value for a (T, Q) cell is the median over its three repetitions.
> 3. Before each query's 2-s pre-window, an explicit full GC runs over JMX (amendment B3h).
> 4. RowsRead:
>    - `org.apache.cassandra.metrics:type=ClientRequestSize,name=RowsRead` `Count`, read through `PsJmx` before and after each
>      query (`ClientRequestSizeMetrics.java:40`). A bean not yet registered (before the first non-system query) reads 0.
>    - Its Δ equals the response's rows on both branches (`SelectStatement.java:357-358`).
>    - System keyspaces, including the auth lookups, are excluded (`SchemaConstants.java:67-68, 144-148`).
>    - A rejected query adds 0.
> 5. Direct disallow evidence:
>    - the client's `InvalidRequest` carrying the guardrail message;
>    - the system.log line `ERROR … Guardrail page_size violated: Aborting query …`, logged once per distinct message per
>      10 minutes (`Guardrail.java:47-48`).
> 6. Humongous regions: the `Humongous regions: a->b` lines of `gc.log` inside each query window. Informational, with no
>    prediction.

**B3e. Procedure.**
1. Start the node and load the data. Restart it once, so that heap reflects a fresh JVM, and wait 30 s.
2. For each Q in Q1..Q5, three times each: start jstat, wait 2 s, run the probe, wait 3 s, stop jstat, and read RowsRead and the client output.
3. Disable the guardrail and repeat Q2 and Q5.
4. Stop the node.

> **Amendment B3e (2026-10-26, stage-4 audit, before any reading).** One script, `stage4-runtime-verification/harness/page_size_fail_threshold-execute-pageSize--autonomous/cluster-run.sh`:
> 1. Node directory, overrides, start, setup, load, flush, tablestats, `count(*)`.
> 2. Restart, then wait 30 s.
> 3. Start the heap poller.
> 4. For T in 1000 (yaml), 10000 and −1 (JMX, read back): Q1–Q5, three times each. Each query:
>    - explicit GC;
>    - RowsRead;
>    - 2 s;
>    - the probe;
>    - 3 s;
>    - RowsRead;
>    - the query's system.log slice.
> 5. Stop the poller and the node, copy `system.log` and `gc.log`, and wipe the node directory.
>
> `summarize.py` builds `readings.txt` from the raw files.

**B3f. Predictions** (T = 1000):

| Query | Outcome | Heap peak delta |
|---|---|---|
| Q1 | first page 500 rows, has_more true | < 50 MiB |
| Q2 | rejected: "Aborting query for table wide, page size 2000 exceeds fail threshold of 1000." | ≈ 0 |
| Q3 | succeeds, 100,000 rows in one page, has_more false | ≥ 200 MiB (at least the response size) |
| Q4 | succeeds, 50,000 rows in one page | ≥ 100 MiB |
| Q5 | rejected | — |
| Q2 and Q5 with the guardrail disabled | succeed | — |

> **Amendment B3f (2026-10-26, stage-4 audit, before any reading).** Exact predictions. 100,000 rows, value 2,048 B, MiB = 1,048,576 B. Heap Δ as defined in amendment B3d:
>
> | Query | T = 1000 (yaml; warn 500) | T = 10000 (JMX; warn 5000) | T = −1 (default) |
> |---|---|---|---|
> | Q1 fetch 500 | ok, first page 500 rows, has_more true; heap Δ < 50 MiB | same | same |
> | Q2 fetch 2000 | rejected: `InvalidRequest` containing "Aborting query for table wide, page size 2000 exceeds fail threshold of 1000."; heap Δ < 50 MiB | ok, 2000 rows, has_more true; heap Δ < 50 MiB | as at 10000 |
> | Q3 paging off | ok, 100,000 rows, has_more false; heap Δ ≥ 204,800,000 B | same | same |
> | Q4 fetch 50,000, LIMIT 50,000 | ok, 50,000 rows, has_more false; heap Δ ≥ 102,400,000 B | same | same |
> | Q5 fetch 50,000, LIMIT 50,001 | rejected, "… page size 50000 exceeds fail threshold of 1000." | rejected, "… page size 50000 exceeds fail threshold of 10000." | ok, 50,000 rows, has_more true; heap Δ ≥ 102,400,000 B |
>
> Sources of the numbers:
> - 204,800,000 B = 100,000 × 2,048 B, the filed "at least the response size" (B3c: "100,000 × 2 KiB ≈ 200 MiB").
> - 102,400,000 B = 50,000 × 2,048 B.
> - The filed "≈ 0" for Q2 becomes < 50 MiB, Q1's bound (a rejected query reads no rows).
>
> Conditions:
> - Every accepted query: 0 page-size warnings, and RowsRead Δ = rows.
> - Every rejected query: RowsRead Δ = 0.
> - Outcome, rows and has_more must hold in each repetition. The heap bounds apply to the median of three.
> - The query phase logs exactly 3 `page_size` ERROR lines (2000/1000, 50000/1000, 50000/10000) and 0 `page_size` WARN lines: no
>   accepted paged query has warn < P ≤ T.
>
> Validity:
> - yaml and JMX read-backs as set;
> - `app` is not a superuser;
> - the load reports 100,000 ok and 0 failed, and `count(*)` = 100,000;
> - no node death, other than an OOM reading (amended B3g);
> - no other ERROR line in the query phase.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| Q2 and Q5 rejected; Q3 and Q4 succeed with large single responses and heap ≥ response size | Usage does not follow T on the branches chosen by `:338#1` and `#2`; confirmed |
| Q3 or Q4 rejected or truncated to ≤ 1000 rows | T caps these branches; claim wrong |
| Q2 not rejected | Guardrail inactive (check the user is not a superuser and auth is on); not confirmed |
| Q3 heap delta < 50 MiB | The response is streamed, not materialized; the heap side of the claim is wrong (the row side stands) |

> **Amendment B3g (2026-10-26, stage-4 audit, before any reading).** Verdict words for the rows above, and added rows:
> - Row 1 → **Confirmed** when all of amended B3f holds:
>   - at T = 1000, Q2 and Q5 are rejected, and Q3 and Q4 succeed with full single responses within their heap bounds;
>   - the T = 10000 and T = −1 columns hold as amended.
> - Row 2 → **Refuted**: Q3 or Q4 is rejected, or truncated to ≤ T rows, at any finite T.
> - Row 3 → **Invalid**: Q2 not rejected at T = 1000 means the guardrail is inactive. A runbook defect.
> - Row 4 → **Not confirmed**: the Q3 heap Δ median is below 50 MiB.
> - Added: the Q3 heap median lies between 50 MiB and 204,800,000 B, or the Q4 median is below 102,400,000 B → **Not confirmed**.
>   The heap side is not shown.
> - Added: Q3 or Q4 ends with `java.lang.OutOfMemoryError` on the node → this counts as the heap part of row 1. Per B4, the response
>   exceeded the heap, so usage did not follow T. The node is restarted and the remaining queries run.
> - Added: a paged-branch cell (Q1; Q2 at 10000 and −1; Q5 at −1), or any other T = 10000 or T = −1 cell, differs from amended
>   B3f → **Not confirmed**.
> - Added: **Invalid** if any of these fails:
>   - a read-back;
>   - the superuser check;
>   - the load or the count;
>   - the node, other than an OOM reading;
>   - the sampler: a query window with fewer than 15 pre-window samples.
> - The ERROR-line count is supporting evidence. A mismatch is recorded.
> - **Effect rule:** as amendment B2g. Row 4 and the heap row give **caps only on some paths (bypass)** for rows, with the heap
>   side undetermined.

**B3h. Controls.**
- Q1, Q2 and Q5 are the positive control, showing the cap binds on the same data and user.
- The disabled-guardrail run shows that rejections come from T.
- Data is flushed and the JVM restarted, so memtables do not inflate the heap baseline.
- Repeating each query 3 times averages out GC timing.

> **Amendment B3h (2026-10-26, stage-4 audit, before any reading).** Before each query's 2-s pre-window, the harness runs an explicit full GC over JMX:
> `java.lang:type=Memory` `gc()`, which is a full G1 collection because there are no ExplicitGC flags in `conf/`.
> - Why: B3h wants a heap baseline free of earlier usage (memtables flushed, a fresh JVM), but the queries run back to back. Without
>   a collection, the pre-window median holds the garbage of the queries before.
> - The shakedown at 20,000 rows found this: the baseline rose from 256 to 1,848 MiB over 15 queries with no collection
>   (`results/<stem>/shakedown/`). That shakedown is not a run-1 reading.
> - With a collected baseline, peak − baseline counts what the query holds or allocates until the next collection.
> - Q3's response stays referenced while it is built and processed, so a collection inside the window does not remove it.
> - No bound changes. The three repetitions remain.

**B4. Risks and cleanup.**
- Data is about 200 MiB plus commit log, under `$WORK/node`.
- Q3 could pressure a 2 GiB heap. If the node dies with OOM, record that as a reading (it supports the claim) and restart.
- At the end: `kill $(cat $WORK/node/pid)`, check `pgrep -f CassandraDaemon` is empty, then `rm -rf $WORK/node`.
- Never write into the shared clone.

> **Amendment B4 (2026-10-26, stage-4 audit, before any reading).** On the advisor's machine everything lives under `W=~/Library/Caches/stage4`:
> - Clone `$W/cassandra-run33`. It is kept, and its `git status` must be clean.
> - Node `$W/node-psf`, wiped before and after the cluster tier.
> - Logs under `$W/logs/page_size_fail_threshold-execute-pageSize--autonomous/`.
> - The node stops with `nodetool stopdaemon`. The no-daemon check is `ps -eo command | grep '[C]assandraDaemon'`, which must be
>   empty.

## C. Sources read

src/java/org/apache/cassandra/cql3/statements/SelectStatement.java
src/java/org/apache/cassandra/cql3/QueryOptions.java
src/java/org/apache/cassandra/cql3/QueryProcessor.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/db/guardrails/Guardrails.java
src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java
src/java/org/apache/cassandra/db/guardrails/Guardrail.java
src/java/org/apache/cassandra/db/guardrails/Threshold.java
src/java/org/apache/cassandra/metrics/ClientRequestSizeMetrics.java
test/unit/org/apache/cassandra/db/guardrails/GuardrailPageSizeTest.java
test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java
conf/cassandra.yaml

## D. Stage-4 feedback

**2026-10-26, stage 4 run 1 on the advisor's machine.** Results:
[`../../stage4-runtime-verification/results/page_size_fail_threshold-execute-pageSize--autonomous.md`](../../stage4-runtime-verification/results/page_size_fail_threshold-execute-pageSize--autonomous.md)
(uncommitted). Frozen at sha256 `42872914…2854` after seventeen audit amendments (B2a–B2h, B3a–B3h, B4); no run-1 defect.
- **Unit: Confirmed — caps only on some paths (bypass)** (B2g row 1). All 36 cells matched amended B2f, and (D) and (L) were
  identical.
  - P > fail was rejected with `GuardrailViolatedException`: c2 at fail 10, and c5 at 10 and 1000.
  - Paging off (c3) and `LIMIT 2000` with P = 2000 (c4) returned all 2000 rows in one response, with no rejection and no warning,
    at fail 10 and 1000.
  - At the default −1, nothing was rejected.
- **Cluster: Confirmed — caps only on some paths (bypass)** (B3g row 1). One node, `PasswordAuthenticator`, role `app` (not a
  superuser), 100,000 × 2 KiB rows in one partition, three runs per cell.
  - At T = 1000, Q2 (fetch 2000) and Q5 (fetch 50,000, `LIMIT 50001`) were rejected with the guardrail message and RowsRead Δ 0.
  - At every T (1000, 10000, −1), Q3 (paging off) returned 100,000 rows in one response, with coordinator heap Δ median
    1,152–1,168 MiB; Q4 (`LIMIT 50000`) returned 50,000 rows, at 688–704 MiB.
  - On the paged branch the heap follows the cap: the 50,000-row page cost 688 MiB when allowed (T = −1), and 16–32 MiB when
    rejected.
- **Note for stage 3.** The heap Δ counts all allocation in the window, not only retained heap: no GC fell inside a window.
  Q3's Δ is about 6× its value bytes. The TopK and NODE_LOCAL bypasses listed in A3 were not run.
