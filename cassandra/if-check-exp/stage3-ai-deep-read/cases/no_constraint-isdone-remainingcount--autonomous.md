# no_constraint — CBuilder.ArrayBackedBuilder.isDone() — verification solution

| Field | Value |
|---|---|
| Entry pointer | [`CBuilder.java:147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CBuilder.java#L147) (`return remainingCount() == 0 || built;`, helper defined at L145) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no resource constraint; the check is builder-state bookkeeping (slots full or already built). |
| Ground | The check guards an array sized once by the table's clustering-column count; it caps no memory or disk usage. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. Operands of the check:
- `remainingCount()` = `values.length - size` (CBuilder.java:122-125). `values` is declared at CBuilder.java:107 and allocated once at CBuilder.java:114 as `new ByteBuffer[type.size()]`, i.e. the number of clustering columns of the table schema. `size` is a counter (CBuilder.java:108) incremented in `add` (CBuilder.java:136).
- `built` is a boolean flag (CBuilder.java:109), set true in `build()` (154) and `buildBound()` (164).
No yaml entry, JVM property or constant takes part. [Declaration of the array operand: `CBuilder.java:107`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CBuilder.java#L107).

**A2. What it caps.** Nothing. It could in principle be seen as bounding the `ByteBuffer[]` of clustering values, but that array's length is fixed at construction by the schema (a handful of columns), so the check bounds no memory- or disk-significant object. It only prevents overrunning the array (otherwise ArrayIndexOutOfBounds) and reuse of the array after `build()` handed it to a `Clustering` without copying (comment at CBuilder.java:152-153).

**A3. Mechanism.** Enclosing method: private `isDone()` at CBuilder.java:145-148, of the private static class `ArrayBackedBuilder` (CBuilder.java:104). Check: [`CBuilder.java:147`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CBuilder.java#L147). Outcomes: true means the builder is full or already built; false means another value may be appended. Sole caller: `add(V, ValueAccessor<V>)` at [`CBuilder.java:134`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/db/CBuilder.java#L134), which throws `IllegalStateException` when done, else stores the value (136). The other `add(Object)` at 140 reaches it via `add`. `isDone` is private, so no call site exists outside the class (grep of `src/java` found only line 134). No bypass or overshoot: it is an API-misuse guard.

**A4. Other consumers.** n/a: no constraint. The values appended are stored in the array whose size is schema-fixed; the byte buffers' sizes are limited elsewhere (clustering key size limits in the write path), not by this check.

**A5. Evidence beyond the source.** Searched: callers of `isDone` in `src/java` (only `add`), the class source (no config or property reads in `CBuilder.java`), `git`-free reading only. No docs or issues relied on. none.

## B. Verification solution

**B1. Claim under test.** This check does not cap memory or disk usage: it only guards builder state against appending beyond the schema's clustering-column count or after `build()`.

### B2. Unit tier

n/a: no constraint, the operands are the array length fixed by the schema and a boolean flag (A1, A3); no usage-side quantity is compared against a limit.

**B2a-B2h.** n/a: no constraint, answered by A1 and A3.

### B3. Cluster tier

n/a: no constraint, answered by A1-A3: `isDone` is private, called only from `add`, and its operand is the clustering-column count, so no workload can drive heap, off-heap or disk toward a limit through it.

**B3a-B3h.** n/a: no constraint, see above.

**B4. Risks and cleanup.** None; nothing is built or run.

## C. Sources read

- src/java/org/apache/cassandra/db/CBuilder.java
- grep of src/java for `isDone()` and `remainingCount`

## D. Stage-4 feedback

`none yet`
