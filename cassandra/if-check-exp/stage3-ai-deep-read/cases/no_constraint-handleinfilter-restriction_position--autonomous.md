# no constraint — ClusteringColumnRestrictions.handleInFilter verification solution  <!-- file: cases/no_constraint-handleinfilter-restriction_position--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the return expression of [`ClusteringColumnRestrictions.java:228`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictions.java#L228) (helper `handleInFilter` defined at line 226) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the helper only decides whether a clustering restriction can be served by a slice or must be applied as a row filter. It caps no memory or disk object. |
| Ground | The check compares a restriction kind and a column position (CQL planning metadata). It holds and bounds no buffer, cache or file. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of `restriction.isContains() || restriction.isLIKE() || index != restriction.getFirstColumn().position()`:
- `restriction.isContains()`: default method [`SingleRestriction.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/SingleRestriction.java#L49) (true for CONTAINS / CONTAINS KEY restrictions).
- `restriction.isLIKE()`: `SingleRestriction.java:39` (true for LIKE).
- `index`: parameter, the expected clustering position, computed by callers (`keyPosition` at `ClusteringColumnRestrictions.java:121`, `position` at lines 189 and 209: `0` initially, then `lastColumn.position() + 1`).
- `restriction.getFirstColumn().position()`: `Restriction.java:43` declares `getFirstColumn()`; `position()` is the column's index among clustering columns from the table schema.
No yaml entry, JVM property or constant takes part (the only literals are the initial `0`).

**A2. What it caps.** Nothing. It could in principle relate to the size of a result set (a filtered query reads more than a sliced one), but the helper itself only returns a boolean on schema positions and restriction type; it bounds no object held in memory or on disk.

**A3. Mechanism.** Enclosing method: [`handleInFilter`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictions.java#L228) (private, lines 226-229), the check is on line 228.
- True: the restriction cannot be turned into a clustering slice (it is CONTAINS or LIKE, or a clustering column was skipped, so position is non-contiguous). Callers treat it as "needs filtering".
- False: restriction is contiguous with the previous ones and goes into clustering bounds.
Callers read (all in the same file): `boundsAsClustering` line 128 (true: `break` out of building bounds, remaining restrictions left to the row filter); `needFiltering` line 196 (true: return true; leads to the ALLOW FILTERING requirement in `StatementRestrictions.java:280,326,704`); `addToRowFilter` line 215 (true or has supporting index: add restriction to the RowFilter and `continue`). Neither outcome allocates, caps or rejects based on a size. Nothing bypasses or overshoots anything because there is no limit.

**A4. Other consumers.** Not applicable; no resource is bounded. Searched: `grep -rn handleInFilter src` (only the 4 hits above, all in this class); no yaml key, `CassandraRelevantProperties` entry or guardrail is read in or around the helper (the guardrail `inSelectCartesianProduct` at line 109 is in a different method, `valuesAsClustering`, and is not part of this check).

**A5. Evidence beyond the source.** none. (Source and the call-site reading above only; no issue or doc search relied on.)

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: its result depends only on the restriction kind and clustering column positions, not on any size, count or configured limit.

### B2. Unit tier

n/a: no constraint. The answer to "what does it bound" is in A1-A3: the operands are a restriction type flag and two column positions; both branches only select between slice bounds and row filtering. No usage-side value exists to measure.

(Optional sanity check an engineer may run: parse `SELECT ... WHERE ck1 = ? AND ck3 = ?` and `... WHERE ck1 CONTAINS ?`-style statements through `StatementRestrictions` and confirm `needFiltering()` is true exactly when `handleInFilter` is true, independent of any yaml setting.)

### B3. Cluster tier

n/a: no constraint. Evidence in A1/A2 answers it instead: no heap, off-heap or disk quantity is compared. A cluster run would only show that filtered queries need ALLOW FILTERING, which is not a resource cap.

**B2/B3 readings, controls.** n/a: no constraint (see A1-A3).

**B4. Risks and cleanup.** none; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/restrictions/ClusteringColumnRestrictions.java
- src/java/org/apache/cassandra/cql3/restrictions/SingleRestriction.java
- src/java/org/apache/cassandra/cql3/restrictions/Restriction.java
- src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (call sites of needFiltering / boundsAsClustering)

## D. Stage-4 feedback

`none yet`
