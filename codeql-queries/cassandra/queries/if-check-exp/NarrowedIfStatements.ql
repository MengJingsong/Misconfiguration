/**
 * @name If statements gated by a numeric comparison, excluding null checks and literal-only
 *   comparisons
 * @description Further mechanical (structural, not keyword) narrowing of
 *   `ComparisonIfStatements.ql`'s output: drops comparisons against `null`, comparisons between
 *   two literals with no variable/call involved, and comparisons whose operands aren't numeric
 *   (capacity/threshold checks are inherently magnitude comparisons) — the next stage in
 *   manually triaging candidate memory-capacity checks per
 *   ../../../cassandra/if-check-exp/README.md.
 * @kind table
 * @id cassandra/if-check-exp/narrowed-if-statements
 */

import java

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

/** True if `e`'s static type is a numeric primitive or a numeric boxed/wrapper type. */
predicate isNumeric(Expr e) {
  e.getType() instanceof NumericType
  or
  e.getType().(BoxedType).getPrimitiveType() instanceof NumericType
}

from
  IfStmt ifStmt, BinaryExpr cmp, string op, Expr left, Expr right, File f, Callable enclosing
where
  (cmp instanceof ComparisonExpr or cmp instanceof EqualityTest) and
  op = cmp.getOp() and
  left = cmp.getLeftOperand() and
  right = cmp.getRightOperand() and
  cmp.getEnclosingStmt() = ifStmt and
  f = ifStmt.getFile() and
  f.getRelativePath().matches("src/java/%") and
  enclosing = ifStmt.getEnclosingCallable() and
  // drop null checks
  not left instanceof NullLiteral and
  not right instanceof NullLiteral and
  // drop comparisons between two literals (nothing variable to bound)
  not (left instanceof Literal and right instanceof Literal) and
  // keep only numeric-typed comparisons (magnitude checks, not reference/boolean/enum equality)
  isNumeric(left) and
  isNumeric(right)
select f.getRelativePath(), ifStmt.getLocation().getStartLine(),
  enclosing.getDeclaringType().getQualifiedName(), enclosing.getName(),
  operandName(left), op, operandName(right)
