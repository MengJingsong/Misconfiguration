# no_constraint ContainsRestriction.isSupportedBy — verification solution  <!-- file: cases/no_constraint-containsrestriction_issupportedby-index_capability--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `SingleColumnRestriction$ContainsRestriction.isSupportedBy()` (its OR-accumulating checks at [`SingleColumnRestriction.java:530-537`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/SingleColumnRestriction.java#L530-L537)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (Claude Code), 2026-10-27 |
| Estimate | `negative`: there is no resource constraint; the helper only asks whether a secondary index supports CONTAINS / CONTAINS KEY / entry-EQ operators on a column. |
| Ground | The checks compare collection-element counts in the query against zero and ask an index for operator capability; nothing held in memory or on disk is capped. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands: (a) `numberOfValues()`, `numberOfKeys()`, `numberOfEntries()` at lines 557-575 of `SingleColumnRestriction.java`, which return `values.size()`, `keys.size()`, `entryKeys.size()` of the lists parsed from the CQL `WHERE` clause (fields of `ContainsRestriction`, declared at [`SingleColumnRestriction.java:448`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/SingleColumnRestriction.java#L448) ff.), compared with the literal `0`; (b) `index.supportsExpression(columnDef, Operator)` declared at [`Index.java:421`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/Index.java#L421), a boolean capability test (for `CassandraIndex`, [`CassandraIndex.java:262`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/index/internal/CassandraIndex.java#L262)). No yaml entry, JVM property or constant sets a limit.

**A2. What it caps.** Nothing. The `> 0` tests only decide which operators to ask the index about. No memory or disk object is bounded.

**A3. Mechanism.** Enclosing method: `ContainsRestriction.isSupportedBy(Index)`, [`SingleColumnRestriction.java:526-540`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/SingleColumnRestriction.java#L526-L540). If values exist, OR in `supportsExpression(CONTAINS)` (530-531); if keys exist, OR in CONTAINS_KEY (533-534); if entries exist, OR in EQ (536-537); return the OR. Outcome true: the index can serve the restriction (no filtering needed); false: the restriction is not index-served and goes to filtering (which `ALLOW FILTERING` must permit) or is rejected. Neither outcome limits or releases memory or disk. Call sites read: `SingleColumnRestriction.java:78` (`hasSupportingIndex`), `:88` (`findSupportingIndex`), `:98` (`findSupportingIndexFromQueryPlan`), `:108` (base `needsFiltering`, overridden by Contains at `:550`, [`SingleColumnRestriction.java:550`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/restrictions/SingleColumnRestriction.java#L550)). Other subclasses have their own `isSupportedBy` bodies (213, 258, 429, 691, 776, 887); this target is the Contains one only.

**A4. Other consumers.** None related; searched for callers (above), for config keys near the method (none), and `supportsExpression` implementers (`CassandraIndex`, SAI, custom indexes), all capability checks.

**A5. Evidence beyond the source.** none (source read only).

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: its result depends only on which operators the query uses and which the index supports, not on any size.

### B2. Unit tier

n/a: no constraint, there is no limit to drive an operand toward. Answered instead by A1/A3: operands are counts compared with 0 and a boolean capability, with no size bound anywhere in the helper.

### B3. Cluster tier

n/a: no constraint, there is no resource limit to push to a boundary. Answered instead by A2/A3: both outcomes only choose index use vs filtering, and the helper holds and releases nothing.

**B4. Risks and cleanup.** n/a: nothing is run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/restrictions/SingleColumnRestriction.java (lines 68-115, 448, 520-575)
- src/java/org/apache/cassandra/index/Index.java (grep, line 421)
- src/java/org/apache/cassandra/index/internal/CassandraIndex.java (grep, line 262)

## D. Stage-4 feedback

`none yet`
