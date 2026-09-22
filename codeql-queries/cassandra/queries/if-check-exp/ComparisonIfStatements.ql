/**
 * @name If statements gated by a comparison
 * @description Narrows `AllIfStatements.ql` to `if` conditions containing a direct comparison
 *   (`<`, `<=`, `>`, `>=`, `==`, `!=`) between two operands, with a best-effort name for each.
 *   Structural narrowing only — whether a row is a capacity check is decided by reading it
 *   (see ../../../../cassandra/if-check-exp/README.md §3.4-§3.6).
 * @kind table
 * @id cassandra/if-check-exp/comparison-if-statements
 */

import java
import ifcheck.IfCheck

from IfStmt ifStmt, BinaryExpr cmp, Expr left, Expr right, File f, Callable enclosing
where
  (cmp instanceof ComparisonExpr or cmp instanceof EqualityTest) and
  left = cmp.getLeftOperand() and
  right = cmp.getRightOperand() and
  cmp.getEnclosingStmt() = ifStmt and
  f = ifStmt.getFile() and
  inMainSource(f) and
  enclosing = ifStmt.getEnclosingCallable()
select
  f.getRelativePath() as path,
  ifStmt.getLocation().getStartLine() as line,
  pkgDir(f) as pkg,
  enclosing.getDeclaringType().getQualifiedName() as declaringType,
  enclosing.getName() as method,
  operandName(left) as lhs,
  cmp.getOp() as op,
  operandName(right) as rhs,
  opClass(cmp) as opClass
order by pkg, path, line
