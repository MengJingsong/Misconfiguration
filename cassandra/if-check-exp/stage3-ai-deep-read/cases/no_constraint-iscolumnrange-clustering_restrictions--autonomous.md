# no constraint — StatementRestrictions.isColumnRange() verification solution  <!-- file: cases/no_constraint-isColumnRange-clustering_restrictions--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the return expression in the helper: [`StatementRestrictions.java:974-975`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L974-L975) (`clusteringColumnsRestrictions.size() < numberOfClusteringColumns \|\| !clusteringColumnsRestrictions.hasOnlyEqualityRestrictions()`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-27 |
| Estimate | `negative` (no constraint): the helper classifies the query shape (slice vs by-name clustering access) and bounds no memory or disk object. |
| Ground | The operands are counts of CQL restrictions in the parsed statement; the result only selects which `ClusteringIndexFilter` class is built. Neither branch holds or limits bytes. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Compared operands:
- `clusteringColumnsRestrictions.size()`: number of restrictions on clustering columns in the statement; field declared at [`StatementRestrictions.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L98), `RestrictionSet.size()` at `RestrictionSet.java:146`. Derived from the parsed CQL WHERE clause.
- `numberOfClusteringColumns`: `table.clusteringColumns().size()` (line 964), schema-derived; forced to 0 for static compact tables (`StatementRestrictions.java:965-971`, `TableMetadata.isStaticCompactTable` at `TableMetadata.java:301`).
- `clusteringColumnsRestrictions.hasOnlyEqualityRestrictions()`: boolean maintained in `RestrictionSet.java:181` (`restriction.isEQ() || restriction.isIN()`), field `RestrictionSet.java:70`.
No yaml entry, JVM property or constant participates.

**A2. What it caps.** Nothing. The check could at most be associated with how much of a partition a read scans (slice vs named rows), but it does not bound it: the slice's size is limited elsewhere (query LIMIT, page size, `tombstone_*_threshold`, `max_value_size`), not by this predicate. It returns a boolean over restriction counts and types, which occupy a few bytes in the statement object.

**A3. Mechanism.** Enclosing method [`StatementRestrictions.isColumnRange()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L962-L976) (`:962-976`). Returns true when some clustering column has no restriction, or any clustering restriction is not EQ/IN (the range/slice case); false when all clustering columns are restricted by EQ/IN. Call sites read:
- `SelectStatement.java:826`: true -> `makeSlices` and `ClusteringIndexSliceFilter` (`:826-832`); false -> `ClusteringIndexNamesFilter` path. Both outcomes just choose a filter type.
- `SelectStatement.java:976`: `assert !restrictions.isColumnRange()` before `getClusteringColumns` (names path).
- `ModificationStatement.java:488`: `hasSlices()`, picks range vs single-row delete handling.
- `AbstractReadCommandBuilder.java:194`: comment only.
No path where either outcome rejects, truncates or caps anything.

**A4. Other consumers.** n/a: no resource is governed.

**A5. Evidence beyond the source.** Searched `src/java` for callers (`grep isColumnRange`, the four hits above); the helper reads no `DatabaseDescriptor`, `CassandraRelevantProperties` or constants. No docs/issues relied on.

## B. Verification solution

**B1. Claim under test.** `isColumnRange()` does not cap memory or disk usage: its result depends only on restriction shape, and the bytes read or held by the query are independent of the predicate's value.

### B2. Unit tier

**As filed (2026-10-27):** `n/a: no constraint, the operands are statement-shape counts and the boolean only selects a filter class (A1-A3)`, with the optional truth-table test as an alternative. **Superseded by the amendment below** (the audit of stage 4, 2026-10-29, applied before the freeze and before any reading; it changes no estimate, no claim and no A-section fact except those listed in section D).

**B2 amendment (2026-10-29, stage-4 audit; design from `none-type-design.md`, operand kind 2).** The operand is a boolean over the *shape* of the WHERE clause (`StatementRestrictions.java:974-975`), so there is no limit to vary and no size to sweep; the operand-sweep design is used instead: both sides of the branch, two values per side, the guarded quantity measured per branch, at three data sizes, in two storage states.

**B2a. Setup.** JDK 11, a tree made by `copy-source.sh` and built with `ant build-test` (never `cassandra/cassandra-5.0.9/`). One JUnit class, `NoneIsColumnRangeAllocTest extends CQLTester`, package `org.apache.cassandra.cql3`, compiled into the tree and run with plain `java ... org.junit.runner.JUnitCore` (`-Xmx2g`, the JVM 11 `--add-exports/--add-opens` of `build.xml:231-262`, `-javaagent:` jamm not needed for this case). Two JVM runs: *plain* (the instrument) and *byteman* (the same test with the counter rules). `ant testsome` is not used. No yaml change beyond the runbook-defect fix below, no JVM property, no cluster. **Runbook-defect fix (2026-10-29, attempt 1 of the first case aborted on it before any reading was taken):** the unit yaml (`test/conf/cassandra.yaml:64-69`) sets read-size guardrails that a default node does not have (`conf/cassandra.yaml:2021-2022` and `Config.java:529-530`: unset): coordinator fail 4096 KiB, local fail 8192 KiB, row index fail 8192 KiB (and warn thresholds). They abort the large reads of the controls and of the scans (`ReadSizeAbortException`). The test sets all six read-size thresholds to null for the run and restores them, and passes a `QueryOptions` built after that (`QueryOptions.forInternalCalls(ConsistencyLevel.ONE, emptyList())`) instead of `QueryOptions.DEFAULT`, because a `QueryOptions` caches the coordinator thresholds when it is constructed (`QueryOptions.java:346`, `ReadThresholds.create()` at `:275-281`) and `DEFAULT` was built at class load (the second aborted attempt). The prediction and the conclusions table are unchanged. **Runbook-defect fix 2 (2026-10-29, after the first complete attempt, `run1a`, whose readings are kept and disclosed in the results file):** 3 warm-up calls leave the JIT unsettled: pass-to-pass differences up to 30 percent and repeat spreads up to 32 percent in cells at N=1,000 and in the large-result controls, from allocation that C2 compilation removes between calls (a constant 32 bytes per row in one repeat set). The frozen prediction and tolerances are unchanged; the warm-up count in B2c and B2e(vi) is raised from 3 to 30 calls per cell, and the tier restarts from its beginning. Whatever the second attempt reads is filed; the first attempt is not discarded.

**B2b. Sweep.** Table `t(pk int, ck1 int, ck2 int, v blob, PRIMARY KEY (pk, ck1, ck2))`, one partition `pk=1` with N rows, `ck1 = 0..N-1`, `ck2 = 7`, `v` = 100 bytes. N in {1,000; 10,000; 100,000}, each on a fresh table. Two storage states per N: *memtable* (no flush; the test asserts no sstable) and *sstable* (one `flush()`, then the test asserts one live sstable and an empty memtable). Five query arms, each returning **exactly one row** (`ck1=5, ck2=7`), so the result is identical and only the restriction shape differs:

| Arm | WHERE (after `pk=1 AND`) | Expected `isColumnRange()` | Expected filter |
|---|---|---|---|
| F1 | `ck1 = 5 AND ck2 = 7` | false | `ClusteringIndexNamesFilter` |
| F2 | `ck1 IN (5) AND ck2 = 7` | false | `ClusteringIndexNamesFilter` |
| T1 | `ck1 = 5` | true (`size()` 1 < 2) | `ClusteringIndexSliceFilter` |
| T2 | `ck1 = 5 AND ck2 >= 7 AND ck2 <= 7` | true (`!hasOnlyEqualityRestrictions`) | `ClusteringIndexSliceFilter` |
| T3 | `ck1 = 5 AND ck2 >= 7` | true | `ClusteringIndexSliceFilter` |

Controls (same table, same instrument): C1 `SELECT v ... WHERE pk=1` (the whole partition, N rows); C2 `SELECT v ... WHERE pk=1 LIMIT 10` (a known row bound that binds on the same resource).

**B2c. Workload and instrument.** Each arm is prepared once with `QueryProcessor.getStatement(cql, ClientState.forInternalCalls())` (a `SelectStatement`) and executed in-thread with `stmt.executeLocally(QueryState.forInternalCalls(), QueryOptions.DEFAULT)`. The guarded quantity is the **bytes the calling thread allocates during one `executeLocally` call**, read with `com.sun.management.ThreadMXBean.getThreadAllocatedBytes(currentThreadId)` before and after (the instrument of `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java`, called directly). Per (arm, N, state): 30 warm-up calls discarded, then 7 timed calls; report median, min and max. The instrument is checked first by a known-answer allocation (an 8 MiB `byte[]` must read 8,388,608 to 8,454,144 bytes). Statement preparation is outside the window (the arms differ in query text length, which is not the quantity under test).

**B2d. Observables and proof the check ran.** (1) For every arm and cell, `stmt.getRestrictions().isColumnRange()` is read, and the filter class actually built by the production path is read from `stmt.getQuery(QueryOptions.DEFAULT, nowInSec)` (a `SinglePartitionReadCommand.Group`, `queries.get(0).clusteringIndexFilter(key)`); the arm is valid only if both match the table in B2b. (2) The returned `ResultMessage.Rows` has exactly one row with `ck1 = 5, ck2 = 7` (for C1, N rows; for C2, 10). (3) In the *byteman* run, a rule at the exit of `StatementRestrictions.isColumnRange` counts true and false returns; a count of zero makes the run *Invalid*.

**B2e. Steps and what each establishes.** (i) Known-answer check: the instrument reads real allocation. (ii) Per cell, branch proof: the check ran on the production path and chose the expected side. (iii) Per cell, per-call allocation of the five arms: whether the side chosen changes what the read allocates. (iv) Across N: whether any difference between sides grows with the data size (a cap would bound or unbound something that grows with N). (v) Controls C1 and C2: the instrument sees growth with the data and sees a bound when one binds. (vi) Noise floor: every cell is measured in two passes (A, then B, each 30 warm-up + 7 timed calls, after all cells of A), and the floor is the largest relative difference between the two medians.

**B2f. Prediction (frozen before any reading).**
- U1 (branch proof): F1 and F2 give `isColumnRange()` false and a names filter; T1, T2, T3 give true and a slice filter; every arm returns the one row `ck1=5, ck2=7`; in the byteman run both return values are counted.
- U2 (equal allocation): in every (N, state) cell, each of F2, T1, T2, T3 has a median within 20 percent of F1's median (|arm - F1| / F1 <= 0.20).
- U3 (flat in N): for each arm and state, median(N=100,000) is between 0.5 and 2 times median(N=1,000).
- U4 (controls): C1 median at N=100,000 is at least 1,000,000 bytes (100,000 rows x at least 10 bytes) and at least 50 times C1 at N=1,000, and at least 100 times F1 at N=100,000; C2 at N=100,000 is at most 0.1 times C1 and between 0.5 and 2 times C2 at N=1,000.
- U5 (noise floor): the two passes' medians differ by at most 5 percent in every cell; the repeats of one cell have a (max-min)/median of at most 10 percent.
- Tolerances and N values are fixed here and are not changed after a reading.

**B2g. Conclusions table.**

| Reading | Verdict | Effect on the constraint |
|---|---|---|
| U1-U5 hold | **Confirmed**: usage does not follow the predicate | `does not cap` |
| U1, U2, U4, U5 hold; U3 fails with every arm (F and T) growing in N in the same way | **Confirmed**: usage follows the data, equally on both sides | `does not cap` |
| Some arm differs from F1 by more than 20 percent in a state and the difference D(N) = arm - F1 grows with N: |D(100,000)| - |D(1,000)| > max(noise floor of the cell, 4,096 bytes) | **Refuted**: the filter chosen by the check changes what is allocated | `caps` (or `caps only on some paths (bypass)` if only one state shows it) |
| U2 fails by a constant offset (more than 20 percent, not growing with N) | **Not confirmed** (a fixed per-filter cost; the prediction missed) | `undetermined` |
| U5 fails (noise above 5 percent) | **Not confirmed**: the effect is not resolved | `undetermined` |
| A control did not move (U4 fails), or the branch proof (U1) fails, or the byteman count is zero | **Invalid** | `undetermined` |

**B2h. Controls.** Positive control: C2 (a bound on rows read) moves allocation by two or more orders of magnitude against C1 at N=100,000 with the same instrument; C1 shows the growth with the data. Noise floor: B2e(vi). Alternative explanations: a difference caused by query text length or by statement preparation is excluded because preparation is outside the window; a difference caused by different result rows is excluded because every arm returns the same row (U1); a difference caused by the memtable-versus-sstable path is split out by the two states.

**B2i. Scope statement.** This is a unit-tier measurement of per-call allocation only. Allocation is not live heap, and the operand has no size (kind 2).

### B3. Cluster tier

n/a: operand has no size (kind 2). Reason added by the 2026-10-29 audit: the guarded quantity is the allocation of one read, a few to tens of kB at one row returned, far below the heap noise of a node (about +-16 MiB with G1); a cluster-tier heap reading cannot resolve it. Unchanged from the filing: no constraint, nothing to push to a boundary. The optional B3 control as filed (100000-row partition on one node, heap read before and after) is not run: its two queries return different numbers of rows, so it would measure the rows returned, not the check.

**B3a-B3h.** n/a: see B3.

**B4. Risks and cleanup.** The unit test writes under its own `-Dcassandra.storagedir` outside the repository tree; nothing else runs. Stop every `java` process started (check `ps -eo cmd | grep '[J]UnitCore'`), and delete only the run directories created by this run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (lines 98, 538, 962-976)
- src/java/org/apache/cassandra/cql3/restrictions/RestrictionSet.java (70, 146, 181, 362)
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (820-832, 970-978)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (484-490)
- src/java/org/apache/cassandra/schema/TableMetadata.java (301)
- src/java/org/apache/cassandra/db/AbstractReadCommandBuilder.java (194)

## D. Stage-4 feedback

**Stage-4 audit, 2026-10-29 (before any reading).** Every citation in A1-A3 and C was re-read in `cassandra/cassandra-5.0.9/`. Held: `StatementRestrictions.java:98, 962-976 (974-975)`, `RestrictionSet.java:70, 146-149, 181, 362-365`, `SelectStatement.java:826-832, 976`, `ModificationStatement.java:484-490 (488)`, `AbstractReadCommandBuilder.java:194` (a comment). Corrections:
1. A1/A3: `TableMetadata.isStaticCompactTable()` (`TableMetadata.java:301-304`) returns `false` in 5.0.9, so the static-compact special case at `StatementRestrictions.java:965-971` is dead code; `numberOfClusteringColumns` is always `table.clusteringColumns().size()` (line 964).
2. B3 (as filed): the optional control compares `WHERE pk=1 AND ck=5` with `WHERE pk=1`, which return different row counts, so it measures rows returned, not the predicate. The amended design returns the same single row on every arm.
3. B2 (as filed): the truth table is kept as the branch proof (U1), made on the production path (the filter class that `SelectStatement.makeClusteringIndexFilter`, `:826-832`, builds), not only the flag.
Estimate unchanged (`negative`). Design applied as B2/B3 amendment dated 2026-10-29. Run results: see below once filed.

**Stage-4 run, 2026-10-29 (unit tier; cluster tier `n/a`).** Results: [`results/no_constraint-iscolumnrange-clustering_restrictions--autonomous.md`](../../stage4-runtime-verification/results/no_constraint-iscolumnrange-clustering_restrictions--autonomous.md). **Verdict: Not confirmed** (B2g row "U5 fails"), Effect `undetermined`, outcome class `undetermined`. Readings: the five arms (names filter: `ck1=5 AND ck2=7`, `ck1 IN (5) AND ck2=7`; slice filter: `ck1=5`, `ck1=5 AND ck2>=7 AND ck2<=7`, `ck1=5 AND ck2>=7`) returned the same row; per-call allocation of the two filter classes differs by a constant 320 to 448 bytes (4 to 8 percent), 5.0 to 5.5 kB (memtable) and 6.6 to 14.5 kB (sstable) at 1,000 to 100,000 rows, and the difference does not grow with the data; U3 (flat in N) was missed equally by every arm in the sstable state (2.07 to 2.12 times); a whole-partition read (21 MB at 100,000 rows) and a LIMIT 10 read (6.6 kB) moved under the same instrument. The frozen noise criterion (5 percent pass to pass) was missed in two control cells at N = 1,000 (C1 14.7 percent, C2 5.6 percent); every F and T cell was within 2.9 percent. Held at Not confirmed because the frozen table says so; the readings are those of "does not cap" (true negative) if that row is set aside. The estimate is unchanged (`negative`). Runbook defects: the unit yaml's read-size guardrails (and `QueryOptions.DEFAULT` caching them) aborted two attempts at the control; 3 warm-up calls were too few (restart with 30). Suggestion for stage 3 / `none-type-design.md`: use an absolute floor for small cells in the noise criterion.
