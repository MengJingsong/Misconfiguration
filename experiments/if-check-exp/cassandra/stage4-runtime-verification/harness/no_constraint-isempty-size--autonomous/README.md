# harness: no_constraint-isempty-size--autonomous (unit tier only)

Case: [`../../../stage3-ai-deep-read/cases/no_constraint-isempty-size--autonomous.md`](../../../stage3-ai-deep-read/cases/no_constraint-isempty-size--autonomous.md) (B2 as amended 2026-10-29). Results: [`../../results/no_constraint-isempty-size--autonomous.md`](../../results/no_constraint-isempty-size--autonomous.md).

| File | Role |
|---|---|
| `ResultSetIsEmptyTest.java` | `CQLTester` subclass (package `org.apache.cassandra.cql3`): one table per N (0, 1, 1,000, 20,000 rows in pk = 1), arms A (`SELECT count(*)`) and B (`SELECT v`), 3 warm-up + 7 repeats, a `mark` line before each query (and a closing `mark block=end`), whole-query thread allocation in `raw.csv`. |
| `Alloc.java` | copy of `harness/batch_size_fail_threshold-verifyBatchSize-failThreshold--guided/Alloc.java` (thread allocation between `start`/`end`, compiled into a jar on the boot class path). |
| `rules-alloc.btm` / `rules-count.btm` | Byteman: `Alloc.start/end` around `ResultSetBuilder.build()` / `Alloc.line` with each `ResultSet.isEmpty()` return value. |
| `unit-run.sh <tree> <outdir> <check\|alloc\|count>` | as for the other two cases, plus the helper jar. |
| `analyze.py <raw.csv> <alloc trace> <count trace>`, `selfcheck.py <run1 dir>` | judge against B2f (a)-(e); independent re-derivation. |
