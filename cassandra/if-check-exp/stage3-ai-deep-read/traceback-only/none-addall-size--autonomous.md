# none — trace-back only  <!-- file: traceback-only/none-addall-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/db/RangeTombstoneList.java:213` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** None. The target line, `if (size > 10 * tombstones.size)` at src/java/org/apache/cassandra/db/RangeTombstoneList.java:213 inside `addAll(RangeTombstoneList tombstones)` (declared at line 184), is a pure performance heuristic (lines 196-211 explain it) that picks between calling add() per tombstone (O(m*log n)) and a sorted merge (O(n+m)), based on the ratio of this list's element count `size` to the other list's `tombstones.size`. The factor 10 is a hard-coded literal, and both operands are in-memory element counts used as bookkeeping. It is not a configuration entry, JVM property, or runtime-queried limit, and it does not cap memory or disk use. It cannot be set by yaml, -D property or JMX, and changing it would need a code change and rebuild.
