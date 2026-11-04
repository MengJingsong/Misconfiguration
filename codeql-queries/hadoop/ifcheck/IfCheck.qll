/**
 * Hadoop-specific predicates for the `if-check-exp` query pipeline.
 *
 * The system-agnostic comparison predicates (`isNumeric`, `opClass`,
 * `isCandidateComparison`, `operandName`) live in `common/lib/IfCheckCore.qll`
 * and are re-exported from here, so queries keep a single `import ifcheck.IfCheck`.
 * This file adds what depends on Hadoop's layout, the counterpart of
 * `cassandra/ifcheck/IfCheck.qll`.
 *
 * Paths are relative to the database's source root, which is a copy of
 * `systems/hadoop/source/` (apache/hadoop @ rel/release-3.4.2), so they map 1:1
 * onto that tree.
 *
 * See ../queries/if-check-exp/README.md for the Hadoop specifics and
 * ../../cassandra/queries/if-check-exp/README.md for the pipeline itself.
 */

import java
import common.lib.IfCheckCore

/**
 * Stage-1 scope for Hadoop: hand-written main source (`<module>/src/main/java/`)
 * of the four core projects — hadoop-common-project, hadoop-hdfs-project,
 * hadoop-yarn-project and hadoop-mapreduce-project.
 *
 * Excludes tests (`src/test/`), code generated during the build (under
 * `target/`, e.g. protobuf classes), and the other top-level projects
 * (hadoop-tools, hadoop-cloud-storage-project, hadoop-maven-plugins, ...) —
 * the counterpart of Cassandra's scope, `src/java/` without tests or tools.
 * Decided 2026-11-04.
 */
predicate inMainSource(File f) {
  exists(string p | p = f.getRelativePath() |
    (
      p.matches("hadoop-common-project/%") or
      p.matches("hadoop-hdfs-project/%") or
      p.matches("hadoop-yarn-project/%") or
      p.matches("hadoop-mapreduce-project/%")
    ) and
    p.matches("%/src/main/java/%") and
    not p.matches("%/target/%") and
    not generatedIntoSrc(p)
  )
}

/**
 * Generated code that the build writes into `src/main/java/` rather than `target/`,
 * so the `target/` exclusion misses it. Upstream lists these paths in its own
 * `.gitignore`; they are not in `systems/hadoop/source/`.
 *
 * - hadoop-yarn-server-resourcemanager: `jsonschema2pojo` writes
 *   `.../scheduler/capacity/placement/schema/{MappingRulesDescription,Rule}.java`
 *   from `src/main/json_schema/`.
 *
 * Found 2026-11-04 by comparing the database's in-scope files with `git ls-files`.
 */
bindingset[p]
predicate generatedIntoSrc(string p) {
  p.matches("hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java/org/apache/hadoop/yarn/server/resourcemanager/scheduler/capacity/placement/schema/%")
}

/**
 * The Maven module directory of `f`: its path up to `/src/main/java/`, e.g.
 * `hadoop-hdfs-project/hadoop-hdfs`. Hadoop has ~80 modules, so this is the
 * first batching key; `pkgDir` subdivides within a module.
 */
string mavenModule(File f) { result = f.getRelativePath().regexpCapture("(.*)/src/main/java/.*", 1) }

/**
 * The package directory of `f` relative to `org/apache/hadoop`, e.g.
 * `hdfs/server/namenode`, `ipc`, `yarn/server/resourcemanager/scheduler`.
 * Files directly under `org/apache/hadoop` yield `(root)`; files outside
 * `org/apache/hadoop` (rare) use their full package directory.
 */
string pkgDir(File f) {
  exists(string inSrc, string rest |
    inSrc = f.getRelativePath().regexpCapture(".*/src/main/java/(.*)", 1) and
    (
      if inSrc.matches("org/apache/hadoop/%")
      then rest = inSrc.suffix("org/apache/hadoop/".length())
      else rest = inSrc
    )
  |
    if rest.matches("%/%")
    then result = rest.regexpCapture("(.*)/[^/]*", 1)
    else result = "(root)"
  )
}
