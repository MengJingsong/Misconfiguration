# no_constraint — ResultSet.isEmpty() verification solution  <!-- file: cases/no_constraint-resultset_isempty-size_zero--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`ResultSet.java:69`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L69) (`org.apache.cassandra.cql3.ResultSet.isEmpty()`, defined at line 67) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: there is no constraint; `isEmpty()` is a bookkeeping emptiness test and bounds no memory or disk object. |
| Ground | The check only reports whether the row list has zero entries; it neither compares against a limit nor rejects or truncates anything. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. The operands are `size()` ([`ResultSet.java:64`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L64), which returns `rows.size()`) and the literal `0`. `rows` is the instance field `List<List<ByteBuffer>> rows` declared at [`ResultSet.java:49`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L49), set in the constructor at line 59. No yaml entry, JVM property or named constant takes part.

**A2. What it caps.** Nothing. The object it inspects, the `rows` list of buffered result rows (heap), is real memory, but the check does not bound it. It only answers "is the list empty?". Growth of `rows` is not limited here: `addRow` (line 72) and `addColumnValue` (line 78) append unconditionally. The actual caps on result size sit elsewhere (paging, `LIMIT`, aggregation/`trim`, and the guardrails in the select path), not in this method.

**A3. Mechanism.** Enclosing method: `ResultSet.isEmpty()` at `ResultSet.java:67-70`; the check is [`return size() == 0;` at ResultSet.java:69](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/ResultSet.java#L69). True and false outcomes only return a boolean; neither blocks, truncates or frees anything. Callers (ResultSet-typed receivers; the many `result.isEmpty()` hits in `SystemKeyspace.java` are `UntypedResultSet`, a different class): `cql3/selection/ResultSetBuilder.java:168` in `build()`: `if (resultSet.isEmpty() && groupMaker != null && groupMaker.returnAtLeastOneRow()) resultSet.addRow(getOutputRow());`. True outcome adds one output row so that an aggregate query with no matching rows still returns a single row; false outcome returns the set as is. That is result-shape logic, not a limit. Other files importing `cql3.ResultSet` (`ListUsersStatement.java`, `ExecuteMessage.java`, `ResultMessage.java`) do not call `isEmpty()`. No bypass or overshoot applies since nothing is enforced.

**A4. Other consumers.** Heap held by the `rows` list is also consumed by every other result-building and encoding path (`ResultSet.Codec` encoding, paging buffers). They are unrelated to this check.

**A5. Evidence beyond the source.** Searched (grep over `src/java`) for callers of `isEmpty()` on `ResultSet` receivers, for configuration keys or constants near the method, and for tests; found one caller (above), no config key, no constant. No docs or issues relied on; `none`.

## B. Verification solution

**B1. Claim under test.** `ResultSet.isEmpty()` does not cap memory or disk usage: it returns `rows.size() == 0` and no resource usage is bounded by it.

### B2. Unit tier

`n/a: no constraint, there is no limit operand to vary or drive past a boundary.` What answers the question instead is the A1/A3 evidence: the method body is one comparison to the literal 0, and its only caller adds at most one row.

### B3. Cluster tier

`n/a: no constraint, there is no knob or limit to push to a boundary.` What answers the question instead is A2/A3: result-size growth is controlled by code outside this method (A2), and the lone caller's effect is bounded to one added row.

**B4. Risks and cleanup.** None; nothing is built or run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/ResultSet.java
- src/java/org/apache/cassandra/cql3/selection/ResultSetBuilder.java
- grep results over src/java for `isEmpty()` callers and `cql3.ResultSet` importers
- agent-docs playbook-non-config-autonomous.md and _TEMPLATE-autonomous.md

## D. Stage-4 feedback

`none yet`
