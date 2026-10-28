# no_constraint — StatementRestrictions.hasUnrestrictedClusteringColumns — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`StatementRestrictions.java:751`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L751) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the check compares two small counts (schema clustering column count vs restricted clustering column count) for CQL WHERE-clause validation. |
| Ground | The check bounds no memory or disk object; it only decides whether a query is rejected as "Some clustering keys are missing". |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: `table.clusteringColumns().size()` (number of clustering columns in the table schema, `TableMetadata`, fixed at CREATE TABLE) and `clusteringColumnsRestrictions.size()` (number of restricted clustering columns in this query, `RestrictionSet.size()` returns `restrictions.size()`, RestrictionSet.java:146-149; the field is built per statement in `StatementRestrictions`). Both originate from the parsed schema and WHERE clause; neither is a yaml entry, JVM property or constant. Declaration/origin of the compared check: [`StatementRestrictions.java:751`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L751).

**A2. What it caps.** Nothing. It could in principle bound the number of clustering restrictions held in a per-statement object, but both numbers are bounded by the table's clustering column count (schema-limited, tiny), and the result is a boolean used for query validation, so no memory or disk object is capped.

**A3. Mechanism.** Enclosing method: `private boolean hasUnrestrictedClusteringColumns()` at StatementRestrictions.java:749-752, returning `table.clusteringColumns().size() != clusteringColumnsRestrictions.size()` (line [751](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L751)). Call sites read (only two): 
- StatementRestrictions.java:695, within the check at 692-698: if the query type does not allow clustering slices and some clustering columns are unrestricted (and not static-only), throws `invalidRequest("Some clustering keys are missing: ...")`. True outcome: query rejected; false outcome: validation continues.
- StatementRestrictions.java:1012 in `hasAllPKColumnsRestrictedByEqualities()` (1007-1014; used e.g. by DeleteStatement.java:181 for conditional statements): true makes it return false (conditional delete rejected); false lets the remaining equality tests decide.
Neither outcome allocates, caps or releases memory or disk. No bypass/overshoot concept applies.

**A4. Other consumers.** None; the helper only reads two counters and is private.

**A5. Evidence beyond the source.** Searched: callers (`grep -rn hasUnrestrictedClusteringColumns src`: 3 hits, the definition and the two call sites above); the Javadoc at line 746-748 ("Checks if some clustering columns are not restricted"), confirming a validation purpose. No config key, constant, doc or history entry relates it to a resource limit. Tests and git history not consulted beyond this (source copy has no relevant resource semantics).

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it is a schema/WHERE-clause validity test over two small integer counts.

### B2. Unit tier

`n/a: no constraint, A1 shows both operands are schema/query counts and A3 shows the only effects are throwing InvalidRequestException or returning a boolean; nothing held in memory or disk is bounded.`

### B3. Cluster tier

`n/a: no constraint, A2 and A3 show no memory or disk object is bounded by the check, so there is no resource to measure at the boundary.`

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (lines 685-760, 1000-1014)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/RestrictionSet.java (lines 146-149)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/DeleteStatement.java (grep, line 181)
- agent-docs playbook-non-config-autonomous.md and _TEMPLATE-autonomous.md

## D. Stage-4 feedback

`none yet`
