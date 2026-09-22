/**
 * @name If statements gated by a boolean helper that compares internally
 * @description Closes a residual completeness gap in `NarrowedIfStatements.ql` for enforcement
 *   pattern (a). That query finds the capacity check only when the comparison is written
 *   directly in the `if` condition. When the comparison is hidden behind a boolean helper —
 *   `if (!pool.hasRoom())`, `if (isOverLimit())` — the `if` itself carries no comparison, so
 *   the row never appears, even though the `if`'s own branches are what decide allow vs.
 *   disallow. That is still pattern (a): the check is the decision, one call frame down.
 *
 *   This query finds `if` statements whose condition calls a boolean method declared in
 *   Cassandra's own source, where that method's body contains a candidate numeric comparison.
 *   It reports the `if` site and the comparison found inside the callee.
 *
 *   Mechanical narrowing only: it does not check that the helper's comparison is a
 *   usage-vs-limit test, nor that the `if`'s branches diverge on object creation. Both remain
 *   read-and-judge calls (see ../../../../cassandra/if-check-exp/README.md §3.4-§3.6).
 * @kind table
 * @id cassandra/if-check-exp/helper-guarded-if-statements
 */

import java
import ifcheck.IfCheck

/**
 * `call` appears in `ifStmt`'s condition and targets `callee`, a boolean-returning method
 * declared in Cassandra's own source (so its body is visible to the analysis).
 *
 * The call may be negated or combined with other conditions — any call inside the condition
 * expression counts, which is what catches `if (!pool.hasRoom())` and
 * `if (x == null && isOverLimit())` alike.
 */
predicate conditionCallsHelper(IfStmt ifStmt, MethodCall call, Method callee) {
  call.getParent*() = ifStmt.getCondition() and
  callee = call.getMethod() and
  callee.getReturnType().hasName("boolean") and
  inMainSource(callee.getFile())
}

from
  IfStmt ifStmt, MethodCall call, Method callee, BinaryExpr cmp, Expr left, Expr right, File f,
  Callable enclosing
where
  f = ifStmt.getFile() and
  inMainSource(f) and
  enclosing = ifStmt.getEnclosingCallable() and
  conditionCallsHelper(ifStmt, call, callee) and
  // the comparison lives in the helper's body, not in the if condition itself —
  // rows where it is already in the condition belong to NarrowedIfStatements.ql
  cmp.getEnclosingCallable() = callee and
  isCandidateComparison(cmp, left, right) and
  not cmp.getEnclosingStmt() = ifStmt
select
  f.getRelativePath() as path,
  ifStmt.getLocation().getStartLine() as line,
  pkgDir(f) as pkg,
  enclosing.getDeclaringType().getQualifiedName() as declaringType,
  enclosing.getName() as method,
  callee.getDeclaringType().getQualifiedName() + "." + callee.getName() + "()" as helper,
  cmp.getLocation().getStartLine() as helperLine,
  operandName(left) as lhs,
  cmp.getOp() as op,
  operandName(right) as rhs,
  opClass(cmp) as opClass
order by opClass, pkg, path, line
