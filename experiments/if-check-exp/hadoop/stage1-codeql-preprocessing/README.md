# Stage 1 — Hadoop (structural preprocessing, CodeQL)

Hadoop instance of stage 1. The method is in
[`../../stage1-codeql-preprocessing/README.md`](../../stage1-codeql-preprocessing/README.md); the
queries are the Cassandra chain, unchanged in logic, documented in the Cassandra pack's
[README](../../../../codeql-queries/cassandra/queries/if-check-exp/README.md). This file records
the Hadoop scope, database and output. **Done 2026-11-04.**

## Source, scope, database

| | |
|---|---|
| Source | `apache/hadoop` @ `rel/release-3.4.2` (commit `84e8b89`), vendored at [`systems/hadoop/source/`](../../../../systems/hadoop/source/). Every `path` in the CSVs is relative to that tree. |
| Scope | `<module>/src/main/java/` of the four core projects: hadoop-common-project, hadoop-hdfs-project, hadoop-yarn-project, hadoop-mapreduce-project (6,754 `.java` files). No tests, no generated code, no hadoop-tools / hadoop-cloud-storage-project / hadoop-maven-plugins. Decided 2026-11-04; defined by `inMainSource` in [`codeql-queries/hadoop/ifcheck/IfCheck.qll`](../../../../codeql-queries/hadoop/ifcheck/IfCheck.qll). |
| Database | `/proj/misconfiguration-PG0/codeql-dbs/hadoop-db` (outside the repo; 557 MB). Built by [`codeql-queries/scripts/build-hadoop-db.sh`](../../../../codeql-queries/scripts/build-hadoop-db.sh): traces `mvn clean install -DskipTests -DskipShade` (JDK 8, Maven 3.6.3, CodeQL 2.27.0) on a local-disk copy, the whole default reactor (114 modules, ~10 min on 40 cores). Same method as `cassandra-db` (traced ant build), so types resolve fully. |
| Queries | [`codeql-queries/hadoop/queries/if-check-exp/`](../../../../codeql-queries/hadoop/queries/if-check-exp/README.md) |
| Results | `codeql-queries/results/hadoop/` (**gitignored**, regenerate per machine) |

Two build-time facts worth knowing:

- **Node version fix in the build copy.** The release pins Node v12.22.1 for
  `hadoop-yarn-applications-catalog-webapp`'s frontend build, and its yarn dependencies now need
  Node ≥ 18, so a stock build fails there. The build script bumps Node/Yarn in the *local copy's*
  `hadoop-project/pom.xml` (the versions `systems/hadoop/build-src/step2-CorrectHadoopPOM.sh`
  uses). No Java source changes.
- **Generated code inside `src/main/java/`.** `jsonschema2pojo` writes two classes into
  hadoop-yarn-server-resourcemanager's `.../placement/schema/`, which upstream gitignores.
  `inMainSource` excludes them explicitly (`generatedIntoSrc`); the `target/` exclusion covers
  everything else generated (protobuf etc.).

## Running it

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
cd <checkout>/codeql-queries
./scripts/build-hadoop-db.sh      # only if hadoop-db does not exist yet (FORCE=1 to rebuild)
./scripts/run-query.sh hadoop hadoop/queries/if-check-exp/NarrowedIfStatements.ql
./scripts/run-query.sh hadoop hadoop/queries/if-check-exp/HelperGuardedIfStatements.ql
```

## Output

Columns are Cassandra's plus `moduleDir` (the Maven module, e.g. `hadoop-hdfs-project/hadoop-hdfs`)
before `pkg` (package directory under `org/apache/hadoop/`). Stage 2 reads columns by name, so
the extra column does not break anything.

| File | Rows | magnitude | equality |
|---|---|---|---|
| `NarrowedIfStatements.csv` | 9,269 | 5,247 | 4,022 |
| `HelperGuardedIfStatements.csv` | 1,573 | 842 | 731 |
| **Pattern-(a) corpus** | **10,842** | **6,089** | **4,753** |

Funnel: 44,150 `if` statements → 28,669 direct comparisons → 9,269 numeric non-trivial, plus 1,573
helper-guarded (a sibling query, not a funnel step). Counts as of 2026-11-04, on `hadoop-db` built
that day.

Narrowed rows by project: hdfs 3,126 · yarn 2,473 · common 2,342 · mapreduce 1,328, across 45
modules; the largest are hadoop-hdfs (2,214), hadoop-common (2,145),
hadoop-yarn-server-resourcemanager (857), hadoop-mapreduce-client-core (763) and hadoop-hdfs-client
(577).

For comparison, Cassandra's corpus is 5,588 rows (4,489 + 1,099) from 2,528 files; Hadoop's is
about 1.9× larger from 2.7× the files.

## Checks done on this output (2026-11-04)

- **Database completeness.** The database's in-scope files were compared with `git ls-files` of the
  vendored tree. Every file containing code is extracted. Not extracted: 114 `package-info.java`
  (package annotations only) and two 17-line license-only stubs in the nodemanager
  (`webapp/AggregatedLogs{Block,Page}.java`). The only extra files were the two generated
  `jsonschema2pojo` classes, now excluded.
- **Every row resolves.** In all four CSVs, every `path` exists in `systems/hadoop/source/`, is in
  scope, and its `line` holds an `if`. In 447 narrowed rows the operator is on a later line of a
  multi-line condition (sampled: correct).
- **Known checks are present**, e.g. `ipc/Server.java:2452` `checkDataLength: dataLength >
  maxDataLength` (`ipc.maximum.data.length`), and `FSDirectory.java:1272` / `:1293`
  (`verifyMaxComponentLength`, `verifyMaxDirItems`).

## Feeding stage 2

[`codeql-queries/scripts/make-stage2-batches.py`](../../../../codeql-queries/scripts/make-stage2-batches.py)
builds the stage-2 batches from these CSVs (since 2026-11-04 it takes per-system settings). For
Hadoop it reads its anchors from
[`../stage2-ai-preprocessing/anchors.md`](../stage2-ai-preprocessing/anchors.md) (18 rows, the
three checks above among them), has no consumed subtrees, prefixes each unit's text with
`moduleDir`, and defaults to 200 units per batch: 9,684 units (9,269 rows + 415 helpers) in 49
batches.

The structural blind spot of stage 1 applies unchanged: a capacity check written outside an `if`
condition (ternary, assignment, `return`, method argument) is in no CSV. See the method README.
