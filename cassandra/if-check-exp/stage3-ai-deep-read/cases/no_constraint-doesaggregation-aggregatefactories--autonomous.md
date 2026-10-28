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

n/a: no constraint. The evidence in A1-A3 answers the question: the operands are a private counter and the literal 0, with no limit value to vary and nothing held in memory that the check bounds.

### B3. Cluster tier

n/a: no constraint. There is no knob to push to a boundary; A3 shows both outcomes only choose between per-row and aggregate result processing.

**B4. Risks and cleanup.** None; nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/SelectorFactories.java
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/Selection.java (lines 565-600)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/AbstractFunctionSelector.java (lines 136-148, 232-242)
- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/selection/MultiElementFactory.java (lines 58-68)

## D. Stage-4 feedback

`none yet`
