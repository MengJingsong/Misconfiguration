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

n/a: no constraint, the operands are statement-shape counts and the boolean only selects a filter class (A1-A3). Alternative: a unit test may confirm the truth table only (prepare `SELECT` on a table with 2 clustering columns with restrictions `ck1=?` -> true; `ck1=? AND ck2=?` -> false; `ck1=? AND ck2>?` -> true; `ck1 IN (...) AND ck2=?` -> false) via `QueryProcessor.prepareInternal` and `SelectStatement.getRestrictions().isColumnRange()`; this checks classification, not resource.

**B2a-B2h.** n/a: no constraint; A1-A3 answer the question.

### B3. Cluster tier

n/a: no constraint, nothing to push to a boundary. Alternative (optional control if a reader wants measurement): on one node, JDK 11, table with 1 partition of 100000 rows, run `SELECT * FROM t WHERE pk=1 AND ck=5` (false) and `SELECT * FROM t WHERE pk=1` (true); read heap via `nodetool` / `jcmd GC.heap_info` before and after; usage differs only because rows returned differ, not because of any cap.

**B3a-B3h.** n/a: no constraint.

**B4. Risks and cleanup.** None for the design-only claim; if the optional B3 control is run, use a throwaway data dir, stop the node and verify no process remains.

## C. Sources read

- src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (lines 98, 538, 962-976)
- src/java/org/apache/cassandra/cql3/restrictions/RestrictionSet.java (70, 146, 181, 362)
- src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (820-832, 970-978)
- src/java/org/apache/cassandra/cql3/statements/ModificationStatement.java (484-490)
- src/java/org/apache/cassandra/schema/TableMetadata.java (301)
- src/java/org/apache/cassandra/db/AbstractReadCommandBuilder.java (194)

## D. Stage-4 feedback

`none yet`
