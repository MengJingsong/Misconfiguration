# no_constraint — UDFunction.equalsWithoutTypes — verification solution  <!-- file: cases/no_constraint-udfunction.equalswithouttypes-body--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `UDFunction.equalsWithoutTypes()`, comparison chain: [`UDFunction.java:640-647`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java#L640-L647) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint; the method is an equality test used for schema comparison and does not cap memory or disk. |
| Ground | The compared operands are already-held schema metadata fields; the result only selects a boolean/Difference outcome and bounds nothing stored. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands compared (all instance fields of `UDFunction`, no config or constant involved): `name` (FunctionName), `argTypes.size()`, `argNames`, `body` (String), `language` (String), `calledOnNullInput` (boolean). All are fields of the UDFunction object, set in its constructor from the CREATE FUNCTION statement or from schema rows; declaration of the check: [`UDFunction.java:640-647`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java#L640-L647). No yaml entry, JVM property or constant is read.

**A2. What it caps.** Nothing. The check could at most be said to touch the function `body` string (heap), but it only compares it with `String.equals`; it neither limits its size nor allocates.

**A3. Mechanism.** Enclosing method: private `equalsWithoutTypes(UDFunction other)` at `UDFunction.java:640`, a conjunction of field equalities (the check is the `&&` chain at [`UDFunction.java:642-646`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java#L642-L646)). Outcomes: true means the two functions agree on everything except argument/return types; false means they differ. Call sites read: `equals(Object)` at `UDFunction.java:635` (adds argTypes and returnType equality), and `compare(Function)` at `UDFunction.java:658` (false returns `Difference.SHALLOW`; true continues to a deep type comparison). No bypass or overshoot concept applies; the method does not enforce anything.

**A4. Other consumers.** n/a: no resource constrained. (Sibling helpers of the same shape: `UDAggregate.equalsWithoutTypesAndFunctions` at `UDAggregate.java:258`, `UserType.equalsWithoutTypes` at `UserType.java:358`; not traced.)

**A5. Evidence beyond the source.** Searched `src/` for `equalsWithoutTypes` (only the call sites above, plus the same-named private methods in UserType/UDAggregate); read the method body and both callers. No config keys, docs or history consulted; none needed for a pure equality test. Nothing found that links it to a limit.

## B. Verification solution

**B1. Claim under test.** `UDFunction.equalsWithoutTypes` does not cap memory or disk usage; it only reports whether two function definitions match apart from types.

### B2. Unit tier

n/a: no constraint, so there is no limit operand to drive; the evidence in A1 and A3 (operand list, two callers, no config or constant read) answers the question instead.

### B3. Cluster tier

n/a: no constraint, so there is no limit to push to a boundary; the evidence in A1 to A3 answers the question instead.

**B4. Risks and cleanup.** None; nothing is built or run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/UDFunction.java (lines 620-690)
- grep of `equalsWithoutTypes` across /users/jason92/cassandra-5.0.9/src

## D. Stage-4 feedback

`none yet`
