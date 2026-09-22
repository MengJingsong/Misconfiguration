# CodeQL Queries

CodeQL queries used to analyze codebases (Cassandra, Hadoop) for the misconfiguration cases
documented in this repo.

## Layout

- `common/` — shared `.qll` library files usable by both targets. Not a separate CodeQL pack
  (see note below) — just plain QL source.
- `cassandra/` — query pack for the Cassandra database (`misconfiguration/cassandra`).
  Its `queries/if-check-exp/` holds the pipeline that feeds
  [`cassandra/if-check-exp`](../cassandra/if-check-exp/README.md); see that folder's own
  [README](cassandra/queries/if-check-exp/README.md) for the stage-by-stage narrowing.
- `hadoop/` — query pack for the Hadoop database (`misconfiguration/hadoop`). Scaffold only:
  `hadoop/queries/` is currently empty.
- `scripts/` — driver scripts that work against either database (not part of any qlpack).
- `results/` — output from query runs (CSV or SARIF, see below). **Contents are gitignored**
  via `results/.gitignore` (`*` with `!.gitignore`), so the directory is tracked but nothing
  in it is. Results are regenerated per machine rather than committed.

Each target pack has its own `queries/` for `.ql` files, and a `common` symlink
(`cassandra/common -> ../common`, `hadoop/common -> ../common`) so shared code lives in one
place on disk but is imported as part of each pack (e.g. `import common.lib.Common`), not as a
separate dependency. Anything exclusive to one target goes directly under that target's own
directory instead (e.g. `cassandra/some_helper/Foo.qll`, imported as `import some_helper.Foo`).

**Why not a separate `common` qlpack with a normal pack dependency?** We tried that first
(`misconfiguration/common` as its own qlpack, referenced via `dependencies:` in each target's
`qlpack.yml`, resolved locally through `--additional-packs`). The CodeQL CLI's version solver
resolves it fine, but query compilation then fails with `could not resolve module` for anything
in it, specifically once `codeql/java-all` is also a dependency (which it always is, since we
need the Java extractor). This reproduces even in an isolated pack outside this repo — looks
like a solver/import-resolution bug in this CLI build (codeql 2.27.0) for unregistered local
pack-to-pack dependencies. Same-pack imports (via a symlink, as done here) don't hit this path
and work reliably, so that's what we use instead.

## Running a query

Compiled databases live outside this repo, under `/proj/misconfiguration-PG0/codeql-dbs/`
(e.g. `cassandra-db`, `hadoop-db`).

```bash
export PATH="/proj/misconfiguration-PG0/tools/codeql:$PATH"
./scripts/run-query.sh cassandra cassandra/queries/if-check-exp/NarrowedIfStatements.ql
```

Usage is `run-query.sh <cassandra|hadoop> <query-or-dir-path> [output-name]`. Paths are
relative to `codeql-queries/`. The optional third argument overrides the output file's base
name, which otherwise defaults to the query's own file name.

### Output format

The script picks the format from the query's `@kind`, because the two need different CodeQL
subcommands:

| `@kind` | How it runs | Output |
|---------|-------------|--------|
| `table`, `graph` | `codeql query run` → `codeql bqrs decode --format=csv` (the intermediate `.bqrs` is deleted) | `results/<target>/<name>.csv` |
| anything else (`problem`, `path-problem`) | `codeql database analyze --format=sarif-latest` | `results/<target>/<name>.sarif` |

`database analyze` expects alert-shaped queries and cannot interpret a plain data dump, which
is why the table/graph path exists. **Every query in `if-check-exp/` is `@kind table`, so the
pipeline produces CSV**, which is what the triage stage reads.
