# no_constraint-isNullOrEmpty-initcond — verification solution  <!-- file: cases/no_constraint-isnullorempty-initcond--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `CreateAggregateStatement.isNullOrEmpty`, body [`CreateAggregateStatement.java:232-233`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java#L232-L233) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the check validates that an aggregate INITCOND is not null or meaningless-empty, and caps no memory or disk. |
| Ground | The check is a CQL validity test on one literal value in a schema statement; it bounds no stored or in-memory object size. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the helper's comparison: `bb` (the INITCOND bytes, from `Terms.asBytes(...)` at `CreateAggregateStatement.java:164`, a `ByteBuffer` parsed from the user's CQL literal; null when no INITCOND is given, line 161) and `bb.remaining() == 0` compared against the literal 0, combined with `type.isEmptyValueMeaningless()` ([`AbstractType.java:458`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/marshal/AbstractType.java#L458)), a per-type boolean (true for non-text/blob types). No yaml entry, JVM property or sized constant takes part.

**A2. What it caps.** Nothing. It could in principle relate to the size of one INITCOND value held in the schema, but it only tests for zero length / null, never an upper size, so it bounds no memory or disk object.

**A3. Mechanism.** Enclosing method: `CreateAggregateStatement.apply(...)`. The helper is private static and has one call site, [`CreateAggregateStatement.java:183`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java#L183) (`if (Constants.NULL_LITERAL != rawInitialValue && isNullOrEmpty(stateType, initialValue))`). True: `ire("INITCOND must not be empty for all types except TEXT, ASCII, BLOB")` is thrown (line 184), rejecting the statement. False: the statement proceeds to build the `UDAggregate` (line ~197 onward). The helper body is at lines 230-234. Only one overload and one caller exist (grep over `src/java`).

**A4. Other consumers.** None related; the INITCOND bytes are stored in the aggregate definition in `system_schema.aggregates`, with no size limit enforced here.

**A5. Evidence beyond the source.** Searched `src/java` for callers of `isNullOrEmpty` in this class (only line 183), and for config keys in the class (none). Error message text states the purpose (semantic emptiness). Docs/issues/history not consulted; none needed.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it only rejects null/zero-length INITCOND for types where empty is meaningless, and accepts arbitrarily large values.

### B2. Unit tier

`n/a: no constraint, the helper has no limit to drive to or past.` Evidence in A1/A3 answers the question: the comparison is against zero and a boolean type property.

### B3. Cluster tier

`n/a: no constraint, there is no knob and no resource it bounds.` Evidence in A2/A3 answers the question instead.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java (lines 160-240)
- src/java/org/apache/cassandra/db/marshal/AbstractType.java (grep of isEmptyValueMeaningless)

## D. Stage-4 feedback

`none yet`
