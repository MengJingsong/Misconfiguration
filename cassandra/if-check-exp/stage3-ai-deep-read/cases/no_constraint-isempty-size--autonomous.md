# no_constraint — ResultSet.isEmpty() verification solution  <!-- file: cases/no_constraint-resultset_isempty-size_zero--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ResultSet.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L69) (`org.apache.cassandra.cql3.ResultSet.isEmpty()`, defined at line 67) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: there is no constraint; `isEmpty()` is a bookkeeping emptiness test and bounds no memory or disk object. |
| Ground | The check only reports whether the row list has zero entries; it neither compares against a limit nor rejects or truncates anything. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. The operands are `size()` ([`ResultSet.java:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L64), which returns `rows.size()`) and the literal `0`. `rows` is the instance field `List<List<ByteBuffer>> rows` declared at [`ResultSet.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L49), set in the constructor at line 59. No yaml entry, JVM property or named constant takes part.

**A2. What it caps.** Nothing. The object it inspects, the `rows` list of buffered result rows (heap), is real memory, but the check does not bound it. It only answers "is the list empty?". Growth of `rows` is not limited here: `addRow` (line 72) and `addColumnValue` (line 78) append unconditionally. The actual caps on result size sit elsewhere (paging, `LIMIT`, aggregation/`trim`, and the guardrails in the select path), not in this method.

**A3. Mechanism.** Enclosing method: `ResultSet.isEmpty()` at `ResultSet.java:67-70`; the check is [`return size() == 0;` at ResultSet.java:69](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L69). True and false outcomes only return a boolean; neither blocks, truncates or frees anything. Callers (ResultSet-typed receivers; the many `result.isEmpty()` hits in `SystemKeyspace.java` are `UntypedResultSet`, a different class): `cql3/selection/ResultSetBuilder.java:168` in `build()`: `if (resultSet.isEmpty() && groupMaker != null && groupMaker.returnAtLeastOneRow()) resultSet.addRow(getOutputRow());`. True outcome adds one output row so that an aggregate query with no matching rows still returns a single row; false outcome returns the set as is. That is result-shape logic, not a limit. Other files importing `cql3.ResultSet` (`ListUsersStatement.java`, `ExecuteMessage.java`, `ResultMessage.java`) do not call `isEmpty()`. No bypass or overshoot applies since nothing is enforced.

**A4. Other consumers.** Heap held by the `rows` list is also consumed by every other result-building and encoding path (`ResultSet.Codec` encoding, paging buffers). They are unrelated to this check.

**A5. Evidence beyond the source.** Searched (grep over `src/java`) for callers of `isEmpty()` on `ResultSet` receivers, for configuration keys or constants near the method, and for tests; found one caller (above), no config key, no constant. No docs or issues relied on; `none`.

## B. Verification solution

**B1. Claim under test.** `ResultSet.isEmpty()` does not cap memory or disk usage: it returns `rows.size() == 0` and no resource usage is bounded by it.

### Amendment 2026-10-29 (stage-4 audit, before the freeze): B2 and B3 filled in (they were `n/a: no constraint`)

Operand kind (none-type-design.md section 2): **1, a count of held data** (`rows.size()`). Citations re-read in `cassandra/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/`: `ResultSet.java` 49, 59, 62-65, 67-70 (check :69), 72, 78; `selection/ResultSetBuilder.java` 157-171 (check :168), `getOutputRow` :173; `statements/SelectStatement.java:1003-1004` (the `groupMaker` handed to the builder is null for a plain select and `GroupMaker.GROUP_EVERYTHING`, whose `returnAtLeastOneRow()` is true (`GroupMaker.java:45-48`), for a non-grouped aggregate (`AggregationSpecification.java:47-49`)). All correct as filed; A3's list of other importers (`ListUsersStatement`, `ExecuteMessage`, `ResultMessage`) is correct (none calls `isEmpty()`). Audit finding: the guarded call `ResultSetBuilder.build()` adds at most one row (the last pending row, or the single output row of an empty aggregate); the rows of a large result are added earlier in `newRow` (:135), so the allocation of `build()` does **not** grow with the number of rows, and growth with rows belongs to the data (the whole query), not to the check. The design below therefore measures `build()` per call (the guarded object) and, separately, the whole query as the control that the instrument sees result growth. The expected result is what the source already says (the true branch only adds one row); the case is run because the harness is cheap.

### B2. Unit tier (amended 2026-10-29)

**B2a. Environment and build.** JDK 11, a `copy-source.sh` copy built with `ant build-test`; one JUnit class `ResultSetIsEmptyTest extends CQLTester` (package `org.apache.cassandra.cql3`, harness `harness/no_constraint-isempty-size--autonomous/`) compiled into the copy and run with the plain `java` launcher and `JUnitCore` (`-Xmx2g`, node module flags, jamm agent, Byteman agent, `stage4.Alloc` on the boot class path as in `batch_size_fail_threshold-...--guided`). Two Byteman JVMs: Alloc mode (brackets `ResultSetBuilder.build()` with `stage4.Alloc.start/end`, no other tracing inside the window) and count mode (`ResultSet.isEmpty()` return values).
**B2b. Knobs.** Rows N in the one partition: 0, 1, 1,000, 20,000 (N = 0 is the only value on the true side of the check). Arm A: `SELECT count(*) FROM t WHERE pk = 1` (aggregate, `returnAtLeastOneRow()` true); arm B: `SELECT v FROM t WHERE pk = 1` (plain, `groupMaker` null).
**B2c. Workload.** `CREATE TABLE t (pk int, ck int, v int, PRIMARY KEY (pk, ck))` once per N; N single-row inserts into pk = 1; each (arm, N) is run 3 warm-up and 7 timed times with `CQLTester.execute`.
**B2d. Observables.** (1) Alloc mode: bytes the calling thread allocated inside `ResultSetBuilder.build()` per call (one `bld` line per query, with `rows=` the returned `ResultSet.size()`), attributed to its (arm, N, repeat) by `mark` lines the test writes before each query. (2) The calling thread's allocation around the whole `execute` call (`query_bytes`) and the row count of the result. (3) Count mode: each `ResultSet.isEmpty()` return value, attributed the same way. Instrument check first: an 8 MiB `byte[]` must read 8 MiB to 8 MiB + 64 KiB.
**B2e. Procedure.** Instrument check; noise block 1 (A at N = 0); then for N in 0, 1, 1000, 20000: arm A then arm B; noise block 2 (A at N = 0); the whole sequence once in Alloc mode and once in count mode.
**B2f. Predictions (frozen).**
(a) Every query calls `isEmpty()` exactly once and the value is true if and only if N = 0 (both arms).
(b) The result has 1 row in arm A at every N, and N rows in arm B.
(c) `build()` allocation: arm B at N = 0 (nothing is added) at most 512 bytes. Arm A at N = 0 minus arm B at N = 0 is between 100 and 1,000 bytes (one output row created by the true branch). For N >= 1 the `build()` allocation of both arms is flat in N: the largest minus the smallest median over N in {1, 1000, 20000} is at most max(2 x noise floor, 512 bytes), and arm A at N = 0 differs from arm A at N = 1 by at most max(2 x noise floor, 512 bytes) (the true branch adds the same single row that the non-empty path adds).
(d) Control: the whole-query allocation of arm B grows with the data: B(20000) / B(1000) between 10 and 25.
(e) Noise floor (A at N = 0, the two blocks): max(range within a block, |difference of the block medians|) at most 512 bytes.
**B2g. Readings.**

| Observation | Meaning | Verdict | Effect |
|---|---|---|---|
| (a), (b), (c) hold, control (d) moved | the true branch adds one row and nothing else; `build()` does not scale with rows | Confirmed | does not cap |
| `build()` allocation lower at N >= 1 than at N = 0 by an amount that matches dropped rows, or any row count below the data size | the check removes or bounds rows | Refuted | caps |
| A(0) minus B(0) below the noise floor | the effect of the branch is not resolved | Not confirmed | undetermined |
| control (d) did not move, `isEmpty()` never true (or never false), or a result size contradicts (b) | the experiment could not show an effect | Invalid / Not confirmed | undetermined |
| numeric ranges of (c)/(e) missed while the relations hold | arithmetic off | Confirmed, with the miss recorded | does not cap |

**B2h. Controls.** The two arms share the table and rows; arm B at N = 0 is the no-branch-effect baseline; the whole-query measurement shows the instrument sees result growth; Alloc mode carries no tracing inside the window.

### B3. Cluster tier

`n/a: below heap noise.` The effect of the branch is one result row of a few hundred bytes created for an empty aggregate; a node-level reading has heap noise of about +-16 MiB with G1. The unit tier decides.

**B3a-B3h.** n/a, see B3.

**B4. Risks and cleanup.** Unit tier only: in-process CQLTester node with data under `~/stage4-logs/none/.../storage-*` on local disk; no daemon is started; the directory is left on the node (logs). Nothing is run under `/proj`.

## C. Sources read

- src/java/org/apache/cassandra/cql3/ResultSet.java
- src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java
- grep results over src/java for `isEmpty()` callers and `cql3.ResultSet` importers
- agent-docs playbook-non-config-autonomous.md and _TEMPLATE-autonomous.md

## D. Stage-4 feedback

**2026-10-29, stage 4 (autonomous, unit tier only; results: [`results/no_constraint-isempty-size--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-isempty-size--autonomous.md)).** Verdict: **Confirmed, does not cap** (one frozen numeric bound missed: `build()` at N = 0 in arm B read 1,176 bytes against at most 512, the window's own overhead); outcome class **true negative** (estimate `negative`). Cluster tier `n/a: below heap noise`. B2/B3 were `n/a: no constraint` as filed and were filled in by the 2026-10-29 amendment (section B) before the freeze; the estimate is unchanged.
Readings: `isEmpty()` called once per query and true exactly for the empty partition; `ResultSetBuilder.build()` allocates 1,384 / 1,448 / 1,472 / 1,440 bytes (count(*), N = 0 / 1 / 1,000 / 20,000) and 1,176 / 1,280 / 1,248 / 1,248 (plain select): flat in N, the empty-aggregate row costs about 64 to 208 bytes; the whole query grew 19.3 x from 1,000 to 20,000 rows (control); noise floor 0 for `build()`.
Feedback for stage 3: (1) the citations in A1-A3 are correct (ResultSet.java 49, 59, 62-70, 72, 78; ResultSetBuilder.java 157-171; the `groupMaker` handed to the builder comes from SelectStatement.java:1003, null for a plain select and `GROUP_EVERYTHING` for a non-grouped aggregate, GroupMaker.java:45-48); (2) the filed `n/a` could have been run: the true branch is exercised by `SELECT count(*)` on an empty partition and measured around `ResultSetBuilder.build()`; (3) `build()` adds at most one row (the other rows of a result are added in `newRow`, ResultSetBuilder.java:135), so the check cannot bound the rows; the result-size growth belongs to the data and to query shape (aggregation, LIMIT, paging), as A2 says.
