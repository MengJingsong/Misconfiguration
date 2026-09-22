/**
 * @name If statements gated by a numeric comparison, excluding null checks and literal-only
 *   comparisons
 * @description Further mechanical (structural, not keyword) narrowing of
 *   `ComparisonIfStatements.ql`'s output: drops comparisons against `null`, comparisons between
 *   two literals with no variable/call involved, and comparisons whose operands aren't numeric
 *   (capacity/threshold checks are inherently magnitude comparisons) — the input to the
 *   read-and-judge triage stage described in ../../../../cassandra/if-check-exp/README.md §7.2.
 *
 *   Because it keeps comparisons whose enclosing statement is an `if`, this is structurally
 *   exactly enforcement pattern (a) (README §3.2), which is the pipeline's current scope.
 *   Patterns (b) and (c) need the separate queries listed in this folder's README.
 * @kind table
 * @id cassandra/if-check-exp/narrowed-if-statements
 */

import java
import ifcheck.IfCheck

from IfStmt ifStmt, BinaryExpr cmp, Expr left, Expr right, File f, Callable enclosing
where
  isCandidateComparison(cmp, left, right) and
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
order by opClass, pkg, path, line
