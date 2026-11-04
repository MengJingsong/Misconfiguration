# harness: none-addall-size--autonomous (unit tier only)

Case: [`../../../stage3-ai-deep-read/cases/none-addall-size--autonomous.md`](../../../stage3-ai-deep-read/cases/none-addall-size--autonomous.md) (B2 as amended 2026-10-29). Results: [`../../results/none-addall-size--autonomous.md`](../../results/none-addall-size--autonomous.md).

| File | Role |
|---|---|
| `AddAllBranchTest.java` | JUnit class (package `org.apache.cassandra.db`): builds A (n tombstones) and B (m), measures `ThreadMXBean.getThreadAllocatedBytes` around `A.addAll(B)` (and around 1000 one-tombstone `addAll` calls for the twin), then `size`, capacity (reflection), `unsharedHeapSize()`, `ObjectSizes.measureDeep`, `equals` against a reference; writes `raw.csv`. Observation only. |
| `rules.btm` | Byteman: `ADD` at line 215 (add() branch), `MRG` at line 220 (merge branch), tracing `this.size`, `other.size`, capacity. |
| `unit-run.sh <tree> <outdir> <plain\|bm\|check>` | compiles the test into a `copy-source.sh` tree built with `ant build-test` and runs it with the plain `java` launcher and `JUnitCore` (`-Xmx2g`, jamm agent, module flags from `conf/jvm11-server.options`); `bm` adds the Byteman agent; `check` runs the instrument checks only. |
| `analyze.py <raw.csv> <trace.txt>` | judges the readings against the frozen predictions (B2f (i)-(vii)); `selfcheck.py <run1 dir>` re-derives the numbers independently. |

Run (on the node): `unit-run.sh ~/s4-none OUT check; unit-run.sh ~/s4-none OUT plain; unit-run.sh ~/s4-none OUT bm; analyze.py OUT/raw-plain/raw.csv OUT/raw-bm/trace.txt; selfcheck.py OUT`.
Not for `ant testsome` (no `-XX:+UseSerialGC` anywhere). Never build in `cassandra/cassandra-5.0.9/`.
