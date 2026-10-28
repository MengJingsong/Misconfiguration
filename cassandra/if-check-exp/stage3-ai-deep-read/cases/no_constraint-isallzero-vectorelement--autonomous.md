# isAllZero (similarity function all-zero vector check) — verification solution  <!-- file: cases/[stem]--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `isAllZero(float[])` in an anonymous `NativeScalarFunction`, comparison [`VectorFcts.java:99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/VectorFcts.java#L99) (definition at line 96) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5 (claude-sonnet-5-5), Claude Code agent, 2026-10-27 |
| Estimate | `negative`: no constraint. The check is an argument validity test (reject all-zero vectors for cosine similarity), not a cap on memory or disk. |
| Ground | The check bounds nothing held: it scans two already-materialized float[] arguments and either throws `InvalidRequestException` or proceeds to `f.compare`. Its outcome does not change how much heap or disk is used. |

**Type:** non-config (none)

> The only `isAllZero` in `src/java` is this one (grep over `src/java`: definition line 96, calls line 89). One body, so no overload ambiguity.

## A. Constraint trace

**A1. The constraint.** `no constraint`. Compared operands: each element `f` of the `float[] v` argument (declared as the loop variable at [`VectorFcts.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/VectorFcts.java#L98)) against the literal `0` at [`VectorFcts.java:99`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/VectorFcts.java#L99). `v` comes from `arguments.get(0/1)` (lines 86-87), decoded by `type.composeAsFloat(b)` (lines 76-77) from the CQL argument. The gating flag `supportsZeroVectors` is a boolean parameter of `createSimilarityFunction` (line 66), set to `false` only for `similarity_cosine` and `true` for euclidean and dot_product (lines 35-37). No yaml entry, JVM property or size constant is involved.

**A2. What it caps.** Nothing. The only memory object near the check is the decoded `float[]` of the argument (dimension fixed by the vector type), and it already exists before the check runs. The check does not bound its size: dimension is fixed by the column type (line 52-54 check only that both arguments have equal dimensions, a type-compatibility check). The check exists because cosine similarity divides by the vector norm, which is zero for an all-zero vector.

**A3. Mechanism.** Enclosing method: `execute(Arguments)` of the anonymous `NativeScalarFunction` created in `createSimilarityFunction` ([`VectorFcts.java:73-92`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/VectorFcts.java#L89)). Call sites of the helper: [`VectorFcts.java:89`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/VectorFcts.java#L89) only (`if (isAllZero(v1) || isAllZero(v2))`). Helper body (lines 96-103): loop over the array, return `false` at the first non-zero element, `true` if none. Outcomes: `true` for either vector (and `!supportsZeroVectors`) throws `InvalidRequestException("Function ... doesn't support all-zero vectors.")` (line 90-91); `false` for both falls through to `FloatType.instance.decompose(f.compare(v1, v2))` (line 94), a 4-byte float result. The enclosing function is invoked through `NativeFunctions.addFunctionsTo` (`NativeFunctions.java:49` calls `VectorFcts.addFunctionsTo`) when the CQL function is evaluated. Neither outcome retains anything; there is no bypass or overshoot concept.

**A4. Other consumers.** Not applicable: no resource is capped. The argument arrays are transient per-call allocations on the request path, bounded by the vector column's declared dimension and the client message size, neither controlled by this check.

**A5. Evidence beyond the source.** Searched `src/java` for `isAllZero` (one definition, one call site), `supportsZeroVectors` (only in `VectorFcts`), and `similarity_cosine` / `VectorFcts` users (only `NativeFunctions.java:49`). Tests exist that exercise the error message: `test/unit/org/apache/cassandra/cql3/functions/VectorFctsTest.java`, `test/unit/org/apache/cassandra/index/sai/cql/VectorInvalidQueryTest.java`, `VectorTypeTest.java` (matched by grep for `similarity_cosine|all-zero`; not read in depth). No yaml key or property is read near this code. No docs or history relied on.

## B. Verification solution

**B1. Claim under test.** The `isAllZero` check does not cap memory or disk usage: whether it passes or throws, node heap, off-heap and disk use are not bounded by it.

### B2. Unit tier

`n/a: no constraint, there is no usage-side quantity compared against a limit.` Evidence in A answers it: the operands are array elements against literal 0 (A1), the check validates arguments and stores nothing (A2, A3). If a reader wants a sanity run, call `similarity_cosine` through `VectorFcts` with `new float[]{0,0}` versus `{1,0}` in a unit test (the existing `VectorFctsTest` does this) and observe an `InvalidRequestException` versus a float result; this shows control flow only, not a resource effect.

**B2a-B2h.** `n/a: no constraint`, see A1-A3.

### B3. Cluster tier

`n/a: no constraint, no cap exists to push to a boundary.` Evidence in A answers it instead: the helper's two outcomes (throw or compute a 4-byte float, A3) hold no heap or disk state beyond the transient argument arrays, whose size is set by the column's vector dimension (a schema property) and not by this check.

**B3a-B3h.** `n/a: no constraint`, see A1-A3.

**B4. Risks and cleanup.** None: nothing to run.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/VectorFcts.java (whole file)
- src/java/org/apache/cassandra/cql3/functions/NativeFunctions.java (grep of line 49)
- src/java/org/apache/cassandra/db/marshal/VectorType.java (grep of `dimension`)
- grep results over src/java and test/unit (file names only)
- agent-docs playbook-non-config-autonomous.md and _TEMPLATE-autonomous.md

## D. Stage-4 feedback

`none yet`
