/**
 * @name If statements gated by a comparison
 * @description Every `if` statement in Cassandra's main source tree whose condition is a
 *   direct comparison (<, <=, >, >=, ==, !=) between two operands, with a best-effort name
 *   for each operand — the starting point for manually triaging candidate memory-capacity
 *   checks per ../../../cassandra/if-check-exp/README.md.
 * @kind table
 * @id cassandra/if-check-exp/comparison-if-statements
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
  enclosing = ifStmt.getEnclosingCallable()
select f.getRelativePath(), ifStmt.getLocation().getStartLine(),
  enclosing.getDeclaringType().getQualifiedName(), enclosing.getName(),
  operandName(left), op, operandName(right)
