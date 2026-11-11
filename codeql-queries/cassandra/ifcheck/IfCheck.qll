/**
 * Cassandra-specific predicates for the `capacity-enforcement-exp` query pipeline.
 *
 * The system-agnostic comparison predicates (`isNumeric`, `opClass`,
 * `isCandidateComparison`, `operandName`) live in `common/lib/IfCheckCore.qll`
 * and are re-exported from here, so queries keep a single `import ifcheck.IfCheck`.
 * This file adds what depends on Cassandra's layout: which files count as main
 * source, and the package directory used to batch rows. Lives in `ifcheck/`
 * rather than beside the queries because QL module names cannot contain
 * hyphens, so `queries/capacity-enforcement-exp/` is not an importable path.
 *
 * See ../queries/capacity-enforcement-exp/README.md for how these fit the pipeline, and
 * ../../../experiments/capacity-enforcement-exp/README.md for the rules they support.
 */

import java
import common.lib.IfCheckCore

/** Cassandra's own main source tree — excludes tests, tools and generated code. */
predicate inMainSource(File f) { f.getRelativePath().matches("src/java/%") }

/**
 * The package directory of `f` relative to `org/apache/cassandra`, e.g.
 * `db/compaction`, `utils`, `net`. Files directly under `org/apache/cassandra`
 * yield `(root)`.
 *
 * Triage proceeds by directory batch, so this is emitted as its own column
 * rather than being re-derived from the path by hand each time. Grouping on a
 * prefix of it gives coarser batches (`db` from `db/compaction`).
 */
string pkgDir(File f) {
  exists(string rest | rest = f.getRelativePath().suffix("src/java/org/apache/cassandra/".length()) |
    if rest.matches("%/%")
    then result = rest.regexpCapture("(.*)/[^/]*", 1)
    else result = "(root)"
  )
}
