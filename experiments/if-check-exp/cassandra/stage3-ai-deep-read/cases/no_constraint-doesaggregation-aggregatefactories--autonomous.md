# no constraint — SelectorFactories.doesAggregation() verification solution  <!-- file: cases/no_constraint-selectorfactories_doesaggregation-numberofaggregatefactories--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`SelectorFactories.java:160`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SelectorFactories.java#L160) (`return numberOfAggregateFactories > 0;` in `doesAggregation()`, line 158) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: there is no resource constraint; the check is a bookkeeping predicate (does any selector factory aggregate?) |
| Ground | The comparison `count > 0` bounds no memory or disk object; it only selects between per-row and aggregate result handling. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `numberOfAggregateFactories` (a private `int` field, declared at [`SelectorFactories.java:62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SelectorFactories.java#L62), only mutated by `++numberOfAggregateFactories` at line 106 inside the constructor loop, counting factories whose `isAggregateSelectorFactory()` is true) and the literal `0`. Neither comes from yaml, a JVM property, or a limit constant.

**A2. What it caps.** Nothing. It bounds no heap, off-heap or disk object. The result only chooses between two selection modes; the count of aggregate factories is at most the number of selected columns in the CQL statement and is not compared against any limit.

**A3. Mechanism.** Enclosing method: `SelectorFactories.doesAggregation()` ([`SelectorFactories.java:158-161`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SelectorFactories.java#L160)). Outcomes: `true` means at least one selector is an aggregate, so callers treat the query as aggregating (one output row for the whole result, `Selectors.isAggregate()`); `false` means rows are processed one by one. Neither outcome stops, rejects or truncates anything because of a size limit. Call sites read: `Selection.java:575` and `Selection.java:592` (`isAggregate()` of the processing selection and its `Selectors`), `AbstractFunctionSelector.java:142` (the only rejecting use: throws `InvalidRequestException` "aggregate functions cannot be used as arguments of aggregate functions", a nesting/semantic validation, not a size limit), `AbstractFunctionSelector.java:239` (`isAggregateSelectorFactory`), `MultiElementFactory.java:64` (`isAggregateSelectorFactory`).

**A4. Other consumers.** n/a: no resource is constrained. (Aggregation state such as an accumulator is held per query in the selectors, and result-set size is bounded by other mechanisms, for example query paging and `aggregation_subpage_size_in_kb`, that this predicate does not read.)

**A5. Evidence beyond the source.** Searched `grep -rn doesAggregation src/java` (5 call sites above, none in tests under `src/java`); searched the field `numberOfAggregateFactories` (3 occurrences, all in `SelectorFactories.java`). No config key, property or doc reference involved. History not consulted; none needed for a trivial predicate.

## B. Verification solution

**B1. Claim under test.** `SelectorFactories.doesAggregation()` does not cap memory or disk usage: its result depends only on the shape of the select clause, not on any size limit.

### B2. Unit tier

**As filed (2026-10-27):** `n/a: no constraint. The evidence in A1-A3 answers the question: the operands are a private counter and the literal 0, with no limit value to vary and nothing held in memory that the check bounds.` **Superseded by the amendment below** (stage-4 audit, 2026-10-29, applied before the freeze and before any reading; it changes no estimate and no claim). The audit found that the last half of that sentence does not hold: the branch decides whether the result keeps one row or one row per input row (section D).

**B2 amendment (2026-10-29, stage-4 audit; design from `none-type-design.md`, operand kind 2 whose branch gates result retention).** The operand is a count compared with 0, which is a flag; there is no limit to vary. Both sides of the branch are run over a data-size sweep and the retained result and the per-call allocation are measured per branch.

**B2a. Setup.** JDK 11, a tree made by `copy-source.sh` and built with `ant build-test` (never `cassandra/cassandra-5.0.9/`). One JUnit class, `NoneDoesAggregationAllocTest extends CQLTester`, package `org.apache.cassandra.cql3`, compiled into the tree and run with plain `java ... org.junit.runner.JUnitCore` (`-Xmx2g`, the JVM 11 `--add-exports/--add-opens` of `build.xml:231-262`, `-javaagent:` jamm 0.4.0 from `build/lib/jars` for `ObjectSizes.measureDeep`). Two JVM runs: *plain* (the instrument) and *byteman* (the same test with counter rules). `ant testsome` is not used. No yaml change beyond the runbook-defect fix below, no cluster. **Runbook-defect fix (2026-10-29, attempt 1 of the first case aborted on it before any reading was taken):** the unit yaml (`test/conf/cassandra.yaml:64-69`) sets read-size guardrails that a default node does not have (`conf/cassandra.yaml:2021-2022` and `Config.java:529-530`: unset): coordinator fail 4096 KiB, local fail 8192 KiB, row index fail 8192 KiB (and warn thresholds). They abort the large reads of the controls and of the scans (`ReadSizeAbortException`). The test sets all six read-size thresholds to null for the run and restores them, and passes a `QueryOptions` built after that (`QueryOptions.forInternalCalls(ConsistencyLevel.ONE, emptyList())`) instead of `QueryOptions.DEFAULT`, because a `QueryOptions` caches the coordinator thresholds when it is constructed (`QueryOptions.java:346`, `ReadThresholds.create()` at `:275-281`) and `DEFAULT` was built at class load (the second aborted attempt). The prediction and the conclusions table are unchanged. **Runbook-defect fix 2 (2026-10-29, after the first complete attempt, `run1a`, whose readings are kept and disclosed in the results file):** 3 warm-up calls leave the JIT unsettled: pass-to-pass differences up to 30 percent and repeat spreads up to 32 percent in cells at N=1,000 and in the large-result controls, from allocation that C2 compilation removes between calls (a constant 32 bytes per row in one repeat set). The frozen prediction and tolerances are unchanged; the warm-up count in B2c and B2e(vi) is raised from 3 to 30 calls per cell, and the tier restarts from its beginning. Whatever the second attempt reads is filed; the first attempt is not discarded. **Runbook-defect fix 3 (2026-10-29, same attempt):** `ObjectSizes.measureDeep(resultSet.rows)` read a constant 1,048,568 to 1,048,768 bytes in every arm, including the one-row arms (a buffer in the rows is a view of a shared 1 MiB array), so V2 and V4 could not be evaluated as stated. The retained size is now `measureDeep` of a compact copy of the rows (every buffer copied to an exact-size heap buffer, the lists rebuilt at exact size); the raw `measureDeep(resultSet.rows)` is still written to a second column. V2 and V4 keep their numbers; B2c is reworded.

**B2b. Sweep.** Table `t(pk int, ck int, v int, PRIMARY KEY (pk, ck))`, one partition `pk=1` with N rows, `ck = v = 0..N-1`, N in {1,000; 10,000; 100,000}, each on a fresh table, memtable only (the test asserts no sstable). Arms:

| Arm | Query | `doesAggregation()` | Expected result |
|---|---|---|---|
| P | `SELECT v FROM t WHERE pk=1` | not evaluated: a plain column selection is a `SimpleSelection` whose `isAggregate()` returns false directly (`Selection.java:460-463`) | N rows |
| P2 | `SELECT abs(v) FROM t WHERE pk=1` | false (1 factory, 0 aggregate; `SelectionWithProcessing`, `Selection.java:573-576`) | N rows |
| A1 | `SELECT max(v) FROM t WHERE pk=1` | true (1) | 1 row, value N-1 |
| A2 | `SELECT max(v), min(v) FROM t WHERE pk=1` | true (2) | 1 row, values N-1 and 0 |

Control C: `SELECT v FROM t WHERE pk=1 LIMIT 100` (a known row bound on the same resource). Unpaged (`QueryOptions.DEFAULT`), so a non-aggregate result is one `ResultSet` of N rows.

**B2c. Workload and instrument.** Each arm is prepared once with `QueryProcessor.getStatement(cql, ClientState.forInternalCalls())` and run in-thread with `stmt.executeLocally(QueryState.forInternalCalls(), QueryOptions.DEFAULT)`. Per (arm, N): 30 warm-up calls discarded, then 7 timed calls. Two quantities per call: (1) **allocation**, bytes allocated by the calling thread during the call (`ThreadMXBean.getThreadAllocatedBytes`, as in `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`); (2) **retained result**, `org.apache.cassandra.utils.ObjectSizes.measureDeep` (jamm) of a compact copy of the returned `ResultSet.rows` (each buffer copied to an exact-size heap buffer, lists rebuilt at exact size; runbook-defect fix 3), and `resultSet.size()`; the raw `measureDeep(resultSet.rows)` is recorded beside it. The instruments are checked first: an 8 MiB `byte[]` must read 8,388,608 to 8,454,144 bytes, and `measureDeep` of a `new byte[1_000_000]` must read 1,000,016 to 1,000,064 bytes. All timed calls of one cell run back to back; the heap is not collected between calls (the quantities do not depend on it).

**B2d. Observables and proof the check ran.** (1) For each arm the production selection is read: `SelectStatement.selection.isAggregate()` (reflection on the private field) and the result row count and values. (2) In the *byteman* run, a rule at the exit of `SelectorFactories.doesAggregation` counts true and false returns, attributed to the arm by test-side marks (one mark before each arm is prepared, one before each cell), and a rule at the entry of `AggregationQueryPager.fetchPageInternal` counts the aggregate path (audit: aggregate queries are always fetched through this pager, `SelectStatement.java:596-615`); a zero `doesAggregation` count for P2, A1 or A2, or a nonzero one for P, makes the run *Invalid*.

**B2e. Steps and what each establishes.** (i) Instrument known-answers. (ii) Per cell, branch proof (the flag took the side the arm intends, the row counts and values are right). (iii) Retained result per arm across N: whether the side chosen changes what is held. (iv) Allocation per arm across N: whether the scan work, which is done on both sides, follows the data on both. P2 is the false side of the checked line itself (P never evaluates it). (v) Control C: the instruments see a bound when one binds. (vi) Noise floor: every cell is measured in two passes (A then B, each 30 warm-up and 7 timed calls); the floor is the largest relative difference between the two passes' medians, and for retained size the difference between the passes.

**B2f. Prediction (frozen before any reading).**
- V1 (branch proof): P and P2 have `isAggregate()` false and N rows; A1 and A2 have it true and 1 row; A1's value is N-1; A2's values are N-1 and 0; the byteman run counts `doesAggregation` false for P2, true for A1 and A2, and not at all for P.
- V2 (retained result): the retained size of the rows (compact copy) of P and of P2 at N=100,000 is at least 4,000,000 bytes (at least 40 bytes per row) and at least 50 times their value at N=1,000; A1 and A2 are at most 2,048 bytes at every N and their maximum over N is at most 1.5 times their minimum.
- V3 (allocation): for every arm (P, P2, A1, A2), the median at N=100,000 is at least 10 times the median at N=1,000; and at each N >= 10,000 each of A1, A2 allocates at least 0.3 times what P2 allocates (aggregating does not remove the scan).
- V4 (control): C returns 100 rows at N=100,000; its retained size there is at most 0.01 times P's; its allocation at N=100,000 is at most 0.1 times P's and between 0.5 and 2 times its own at N=1,000.
- V5 (noise floor): the two passes' allocation medians differ by at most 5 percent in every cell, the repeats of one cell have (max-min)/median at most 10 percent, and the retained sizes of the two passes are equal within 1 percent.

**B2g. Conclusions table.**

| Reading | Verdict | Effect on the constraint |
|---|---|---|
| V1, V4, V5 hold and V2 holds (P's and P2's retained result follows N, A's is one row and flat) | **Refuted**: the flag decides whether the result is held per input row or as one row; a prediction miss in V3 is recorded as a deviation, and if A's allocation is flat in N the scan is also avoided | `caps only on some paths (bypass)` (the result is bounded to one row for aggregate queries and not otherwise; no configured limit; the estimate stays `negative`) |
| V1, V4, V5 hold; P's and A's retained results are both flat or both follow N equally | **Confirmed**: usage does not follow the flag | `does not cap` |
| V1, V4 hold; V5 fails, or the P-minus-A retained difference is below the noise floor | **Not confirmed**: the effect is not resolved | `undetermined` |
| Control C did not move (V4 fails), or V1 fails (a flag on the wrong side, a wrong value), or the byteman count is zero | **Invalid** | `undetermined` |

**B2h. Controls.** Positive control: C (a row bound) moves retained size and allocation by two orders of magnitude at N=100,000 under the same instruments. Noise floor: B2e(vi). Alternative explanations: a difference caused by the number of result rows other than the flag is excluded by V1 (rows are what the flag changes, which is the finding itself); a difference caused by parse and prepare is excluded because preparation is outside the window.

**B2i. Scope statement.** A unit-tier measurement of per-call allocation and retained result size. Allocation is not live heap. No configured limit is involved.

### B3. Cluster tier

n/a: operand has no size (kind 2). Reason added by the 2026-10-29 audit: the retained result of the largest unit arm is a few MB (100,000 rows), the same order as the heap noise of a node (about +-16 MiB with G1), so a cluster-tier heap reading could not resolve it; the unit tier's retained-size reading is exact. Unchanged from the filing: no constraint, nothing to push to a boundary.

**B3a-B3h.** n/a: see B3.

**B4. Risks and cleanup.** The unit test writes under its own `-Dcassandra.storagedir` outside the repository tree. Stop every `java` process started (check `ps -eo cmd | grep '[J]UnitCore'`), and delete only the run directories created by this run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SelectorFactories.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/Selection.java (lines 565-600)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/AbstractFunctionSelector.java (lines 136-148, 232-242)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/MultiElementFactory.java (lines 58-68)

## D. Stage-4 feedback

**Stage-4 audit, 2026-10-29 (before any reading).** Every citation in A1-A5 and C was re-read in `cassandra/cassandra-5.0.9/`. Held: `SelectorFactories.java:62, 105-106, 158-161`, `Selection.java:573-576, 590-593`, `AbstractFunctionSelector.java:140-143, 237-240`, `MultiElementFactory.java:62-65`. Corrections:
1. A2/A3/A4: "nothing is held in memory that the check bounds" and "neither outcome ... truncates anything" do not hold for the result set. `Selection.isAggregate()` (`Selection.java:573-576, 590-593`, from `doesAggregation()`) makes `SelectStatement.getAggregationSpecFactory` (`SelectStatement.java:1446-1449`) return `AGGREGATE_EVERYTHING_FACTORY`; the resulting `GroupMaker` makes `ResultSetBuilder.newRow` (`ResultSetBuilder.java:128-136`) fold every input row into one output row, whereas without it `groupMaker` is null and each input row adds an output row to `ResultSet.rows`. The branch therefore gates result retention (one row against one per input row). No configured limit participates; the estimate stays `negative`.
2. A4: `aggregation_subpage_size_in_kb` does not exist in 5.0.9 (`grep -rni subpage src/java` hits only local names in `AggregationQueryPager.java:230-295, 439`). What the aggregate branch does select is the internal pager: `SelectStatement.executeInternal` (`:579-615`) and `execute` (`:520-540`, comment at `:536`: "For GROUP BY or aggregation queries we always page internally even if the user has turned paging off") route aggregate queries through `AggregationQueryPager`.
3. Found at the shakedown, before any allocation reading, and amended before the run: a plain column selection (`SELECT v`) is a `SimpleSelection`, whose `isAggregate()` returns false directly (`Selection.java:460-463`), so it never evaluates `numberOfAggregateFactories > 0`. The false side of the checked line is exercised by a query with processing but no aggregate, e.g. `SELECT abs(v)` (`SelectionWithProcessing`, `Selection.java:573-576`); arm P2 was added to B2b/B2d/B2f for that (P is kept as the no-processing arm). Amendment time 2026-10-29 04:14 UTC; the first frozen hash is superseded (results file section 1).
4. A5: the callers of `doesAggregation()` are exactly `Selection.java:575, 592`, `AbstractFunctionSelector.java:142, 239`, `MultiElementFactory.java:64` (five), as filed.
Design applied as B2 amendment dated 2026-10-29; B3 stays `n/a` with the reason stated there. Run results: see below once filed.

**Stage-4 run, 2026-10-29 (unit tier; cluster tier `n/a`).** Results: [`results/no_constraint-doesaggregation-aggregatefactories--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-doesaggregation-aggregatefactories--autonomous.md). **Verdict: Not confirmed** (B2g row "V1, V4 hold; V5 fails"), Effect `undetermined`, outcome class `undetermined`. Readings (one partition of 1,000 / 10,000 / 100,000 rows): the retained result of the plain and `abs(v)` queries is 124 bytes per row (12,400,040 B at 100,000 rows), that of `max(v)` is 168 B and of `max(v), min(v)` 240 B at every N (73,810 times smaller at 100,000 rows); allocation per call follows N in every arm (about 80 times for 100 times the rows) and the aggregate arms allocate 0.53 of the `abs(v)` arm; a LIMIT 100 control moved both (12,440 B retained). V1 to V4 held; the frozen noise criterion V5 was missed in the allocation of three cells at N = 1,000 (15.6 to 18.0 percent pass to pass); retained sizes were identical between passes. If the noise row is set aside the readings are those of "Refuted, `caps only on some paths (bypass)`" (the branch decides one result row against one per input row; no configured limit), a false negative; the estimate would stay `negative`. Runbook defects: the unit yaml's read-size guardrails (set to null for the run), 3 warm-up calls too few (30), and `ObjectSizes.measureDeep(resultSet.rows)` reading a constant 1 MiB in every arm (retained size now measured on a compact copy).
