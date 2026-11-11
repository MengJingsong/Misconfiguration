/**
 * System-agnostic predicates for the `capacity-enforcement-exp` query pipeline.
 *
 * These encode the experiment's notion of a candidate comparison and do not depend
 * on any one system's layout. Each target pack's `ifcheck/IfCheck.qll` imports this
 * module (re-exporting it to the queries) and adds the system-specific parts: which
 * files count as main source (`inMainSource`) and how rows are batched (`pkgDir`).
 *
 * Imported as `import common.lib.IfCheckCore` (via each pack's `common` symlink).
 * See ../../cassandra/queries/capacity-enforcement-exp/README.md for the pipeline.
 */

import java

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
