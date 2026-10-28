# no constraint — StatementRestrictions.needFiltering(TableMetadata) — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`StatementRestrictions.java:985`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L985) and [`:992`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L992) (helper `needFiltering`, defined at line 982) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the helper is a query-planning predicate (does the query need ALLOW FILTERING) and bounds no memory or disk object. |
| Ground | The helper compares a count of restrictions to zero and delegates to an index-support test; both only classify the query. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the helper's checks: (1) `filterRestrictions.needsFiltering(indexRegistry)` ([`StatementRestrictions.java:985`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L985)); `filterRestrictions` is an `IndexRestrictions` field, built from the WHERE clause; `IndexRestrictions.needsFiltering` (IndexRestrictions.java:74) asks whether an index group supports every restriction. (2) `numberOfRestrictions == 0` ([`StatementRestrictions.java:992`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L992)); `numberOfRestrictions` is a local counter (line 988-990) summing custom index expressions and `Restrictions.size()` of the filter restrictions, a count of parsed WHERE restrictions. (3) `!clusteringColumnsRestrictions.isEmpty()`, same line. No yaml entry, JVM property, or constant is compared against a limit.

**A2. What it caps.** Nothing. It could be seen as relating to unbounded scans (ALLOW FILTERING), but the helper only returns a boolean classification; it does not limit rows, bytes or partitions read. Counts are of query restrictions (a handful of small objects per query).

**A3. Mechanism.** Enclosing method: [`StatementRestrictions.needFiltering(TableMetadata)`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L982) (982-993; the only overload with this name in this class; `ClusteringColumnRestrictions.needFiltering()` at line 190 of its file is a different method). Outcomes: at [`:985`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L985) true means an index cannot satisfy all restrictions so filtering is required, returns true; at [`:992`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java#L992) true when no non-PK restrictions exist but clustering restrictions do (e.g. a slice with no filter restrictions), still filtering. Nothing is dropped, truncated or allocated differently on either outcome. Call sites read: SelectStatement.java:988 (`getRowFilter`: if the filter needs reconciliation, is a mutable intersection and needFiltering, requires the `intersect_filtering_query_enabled` guardrail via `Guardrails.intersectFilteringQueryEnabled.ensureEnabled`, a boolean feature flag that is a yaml guardrail but is not a size/count cap and is not evaluated in this helper); SelectStatement.java:1610 (`checkNeedsFiltering`: if no ALLOW FILTERING, `checkFalse(needFiltering)` rejects the query with `REQUIRES_ALLOW_FILTERING_MESSAGE`); TokenFilter.java:322 (delegation `restrictions.needFiltering(table)`, which is a partition-key restrictions method, not this one; listed for completeness).

**A4. Other consumers.** n/a: no resource is bounded. Filtering queries do consume heap/CPU in the read path, but that is outside this helper and is not capped by it.

**A5. Evidence beyond the source.** Searched `needFiltering(`, `needsFiltering(` and the `usesSecondaryIndexing` uses across `src/java`; found only the call sites above. No config key, constant or guardrail threshold participates. Not run: no tests or history consulted beyond the Javadoc ("Checks if the query need to use filtering", line 978-981).

## B. Verification solution

**B1. Claim under test.** `needFiltering(TableMetadata)` does not cap memory or disk usage: its result is a function of the query's restriction structure only and is independent of any size limit.

### B2. Unit tier

n/a: no constraint, there is no limit-side value to push past. The evidence in A1 and A3 (operands are a restriction count and an index-support predicate, outcomes are a boolean used for validation) answers the question instead.

### B3. Cluster tier

n/a: no constraint, there is no memory or disk cap to drive a node to. A3 shows both outcomes only decide whether ALLOW FILTERING is required or the intersect-filtering guardrail is consulted.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/StatementRestrictions.java (lines 100-120, 595-640, 840-870, 970-1010)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/SelectStatement.java (978-995, 1600-1613)
- grep results over src/java for needFiltering / needsFiltering definitions and callers

## D. Stage-4 feedback

`none yet`
