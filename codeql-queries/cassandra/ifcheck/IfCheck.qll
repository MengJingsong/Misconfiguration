/**
 * Shared predicates for the `if-check-exp` query pipeline.
 *
 * Cassandra-local (not in `common/`) because these encode this experiment's
 * notion of a candidate capacity check, which is not meaningful for other
 * targets. Lives in `ifcheck/` rather than beside the queries because QL
 * module names cannot contain hyphens, so `queries/if-check-exp/` is not an
 * importable path. Imported as `import ifcheck.IfCheck`.
 *
 * See ../queries/if-check-exp/README.md for how these fit the pipeline, and
 * ../../../cassandra/if-check-exp/README.md for the rules they support.
 */

import java

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

/** True if `e`'s static type is a numeric primitive or a numeric boxed/wrapper type. */
predicate isNumeric(Expr e) {
  e.getType() instanceof NumericType
  or
  e.getType().(BoxedType).getPrimitiveType() instanceof NumericType
}

/**
 * `magnitude` for `<`, `<=`, `>`, `>=`; `equality` for `==`, `!=`.
 *
 * A capacity check is inherently a magnitude comparison, so `equality` rows are
 * far more likely to be noise (`index == 0`, sentinel tests). They are kept
 * rather than dropped — an exact-value counter cap (`count == MAX`) is
 * conceivable, and silently discarding ~40% of the corpus would be an
 * invisible decision — but the column lets triage read magnitude rows first.
 */
string opClass(BinaryExpr cmp) {
  cmp instanceof ComparisonExpr and result = "magnitude"
  or
  cmp instanceof EqualityTest and result = "equality"
}

/**
 * A comparison worth triaging: numeric on both sides, not a null check, and not
 * a comparison between two literals (nothing variable to bound).
 */
predicate isCandidateComparison(BinaryExpr cmp, Expr left, Expr right) {
  (cmp instanceof ComparisonExpr or cmp instanceof EqualityTest) and
  left = cmp.getLeftOperand() and
  right = cmp.getRightOperand() and
  not left instanceof NullLiteral and
  not right instanceof NullLiteral and
  not (left instanceof Literal and right instanceof Literal) and
  isNumeric(left) and
  isNumeric(right)
}

/** Best-effort human-readable name for a comparison operand. */
string operandName(Expr e) {
  exists(Variable v | e.(VarAccess).getVariable() = v | result = v.getName())
  or
  exists(Method m | e.(MethodCall).getMethod() = m | result = m.getName() + "()")
  or
  not e instanceof VarAccess and
  not e instanceof MethodCall and
  result = e.toString()
}
