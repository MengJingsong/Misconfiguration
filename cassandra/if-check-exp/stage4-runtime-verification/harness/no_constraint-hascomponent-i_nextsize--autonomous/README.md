# harness: no_constraint-hascomponent-i_nextsize--autonomous (unit tier only)

Case: [`../../../stage3-ai-deep-read/cases/no_constraint-hascomponent-i_nextsize--autonomous.md`](../../../stage3-ai-deep-read/cases/no_constraint-hascomponent-i_nextsize--autonomous.md) (B2 as amended 2026-10-29). Results: [`../../results/no_constraint-hascomponent-i_nextsize--autonomous.md`](../../results/no_constraint-hascomponent-i_nextsize--autonomous.md).

| File | Role |
|---|---|
| `ClusteringHasComponentTest.java` | JUnit class (package `org.apache.cassandra.db`): 16 `BytesType` clustering columns; serializes a `ClusteringBound` of `nextSize` components of 1,024 bytes with `ClusteringBoundOrBoundary.serializer`, `new ClusteringPrefix.Deserializer(...)`, `prepare(0x02, 0)` outside the window, then thread-allocation around `compareNextTo(probe)` with a probe of S components; reads `deserializedSize` by reflection; controls (64 KiB components; `setMaxValueSize(512)`, which stores 0 MiB). Writes `raw.csv`. |
| `rules.btm` | Byteman: `F` at line 654 (`hasComponent` returns false), `D` at `deserializeOne` entry. |
| `unit-run.sh <tree> <outdir> <plain\|bm\|check>` | as for `none-addall-size--autonomous`. |
| `analyze.py <raw.csv> [<trace.txt>]`, `selfcheck.py <run1 dir>` | judge against B2f; independent re-derivation. |
