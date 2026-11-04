# if-check-exp queries — Hadoop

Stage 1 of [`if-check-exp`](../../../../experiments/if-check-exp/README.md) for
**Hadoop 3.4.2** (`apache/hadoop` @ `rel/release-3.4.2`, vendored at
[`systems/hadoop/source/`](../../../../systems/hadoop/source/)).

The four queries are the Cassandra chain, unchanged in logic. What each query does, why
it filters what it filters, and the pipeline's blind spots are documented once, in the
Cassandra pack's [README](../../../cassandra/queries/if-check-exp/README.md). This file
records only what differs for Hadoop.

## What differs from Cassandra

| | Cassandra | Hadoop |
|---|---|---|
| Comparison logic (`isNumeric`, `opClass`, `isCandidateComparison`, `operandName`) | shared: [`common/lib/IfCheckCore.qll`](../../../common/lib/IfCheckCore.qll) | same file |
| Scope (`inMainSource`) | `src/java/` | `<module>/src/main/java/` of the four core projects: hadoop-common-project, hadoop-hdfs-project, hadoop-yarn-project, hadoop-mapreduce-project. No tests, no generated code (`target/`), no hadoop-tools / cloud-storage / maven-plugins. |
| Batching columns | `pkg` (under `org/apache/cassandra/`) | `moduleDir` (Maven module, e.g. `hadoop-hdfs-project/hadoop-hdfs`), then `pkg` (under `org/apache/hadoop/`) |
| Query `@id` | `cassandra/if-check-exp/...` | `hadoop/if-check-exp/...` |
| Database | `codeql-dbs/cassandra-db` (traced ant build) | `codeql-dbs/hadoop-db` (traced Maven build, [`scripts/build-hadoop-db.sh`](../../../scripts/build-hadoop-db.sh)) |

Scope and database method were decided on 2026-11-04. The database holds the whole
default Maven reactor, so widening the scope only means editing `inMainSource` in
[`../../ifcheck/IfCheck.qll`](../../ifcheck/IfCheck.qll) and re-running.

## Running

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd codeql-queries
./scripts/build-hadoop-db.sh          # once per machine/database; ~minutes on 40 cores, see the script header
./scripts/run-query.sh hadoop hadoop/queries/if-check-exp/NarrowedIfStatements.ql
./scripts/run-query.sh hadoop hadoop/queries/if-check-exp/HelperGuardedIfStatements.ql
```

Results land in `results/hadoop/` and are gitignored, like Cassandra's. Row counts are in
[`experiments/if-check-exp/hadoop/stage1-codeql-preprocessing/README.md`](../../../../experiments/if-check-exp/hadoop/stage1-codeql-preprocessing/README.md).
