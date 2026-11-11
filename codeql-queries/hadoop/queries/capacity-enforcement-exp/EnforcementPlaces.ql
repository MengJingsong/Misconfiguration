/**
 * @name Enforcement places beyond `if` statements
 * @description Stage-1 extension of 2026-11-11 (experiments/capacity-enforcement-exp/README.md
 *   §3.7.2): candidate enforcement places that NarrowedIfStatements.ql and
 *   HelperGuardedIfStatements.ql do not emit. One row per place and form:
 *   a candidate comparison outside an `if` condition (`pattern` = its context), a
 *   comparison without an operator (clamp, comparator, buffer capacity test, bit sizing,
 *   overflow check, index check), a call whose capacity check runs in a library, a
 *   handler for a capacity exception, or a method verdict used in a loop, ternary or
 *   `switch`, or reached through a deeper call or an override. Structural and API-signature
 *   matching only; stage 2 ranks the rows.
 * @kind table
 * @id hadoop/capacity-enforcement-exp/enforcement-places
 */

import java
import ifcheck.IfCheck
import common.lib.CapacityEnforcementCore

/**
 * One output row: `anchor` locates it; `pattern` is the form; `detail` the API, the
 * argument's callee or the verdict's target; `lhs op rhs` the comparison when there is one.
 */
predicate row(Top anchor, Callable enclosing, string pattern, string detail, string lhs, string op, string rhs) {
  exists(BinaryExpr cmp, Expr l, Expr r, string ctx, string d |
    isCandidateComparison(cmp, l, r) and comparisonContext(cmp, ctx, d) and
    anchor = cmp and enclosing = cmp.getEnclosingCallable() and
    pattern = "comparison/" + ctx and detail = d and
    lhs = operandName(l) and op = cmp.getOp() and rhs = operandName(r)
  )
  or
  exists(MethodCall mc, string api, string kind |
    (
      clampCall(mc, api) and
      (if clampOnRemaining(mc) then kind = "clamp-on-remaining" else kind = "clamp")
      or
      comparatorCall(mc, api) and kind = "comparator"
      or
      bufferCapacityCall(mc, api) and kind = "buffer-capacity"
      or
      bitSizeCall(mc, api) and kind = "bit-size"
      or
      overflowCheckCall(mc, api) and kind = "overflow-check"
      or
      indexCheckCall(mc, api) and kind = "index-check"
      or
      delegatedEnforcementCall(mc, api) and kind = "delegated"
    ) and
    anchor = mc and enclosing = mc.getEnclosingCallable() and
    pattern = "call/" + kind and detail = api and
    (if exists(mc.getArgument(0)) then lhs = operandName(mc.getArgument(0)) else lhs = "") and
    op = "" and
    (if exists(mc.getArgument(1)) then rhs = operandName(mc.getArgument(1)) else rhs = "")
  )
  or
  exists(CatchClause cc, string api |
    capacityExceptionCatch(cc, api) and
    anchor = cc and enclosing = cc.getEnclosingCallable() and
    pattern = "exception/catch" and detail = api and lhs = "" and op = "" and rhs = ""
  )
  or
  exists(MethodCall call, string ctx |
    // a boolean verdict in a condition, or any value in a switch selector
    (if ctx = "verdict-switch" then any() else call.getMethod().getReturnType().hasName("boolean")) and
    verdictUse(call, ctx, _, _, false) and
    anchor = call and enclosing = call.getEnclosingCallable() and
    pattern = ctx and
    detail =
      call.getMethod().getDeclaringType().getName() + "." + call.getMethod().getName() + "() impls=" +
        count(Callable i | verdictUse(call, ctx, i, _, _)) + " minDepth=" +
        min(int dd | verdictUse(call, ctx, _, dd, _)) and
    lhs = "" and op = "" and rhs = ""
  )
}

from Top anchor, Callable enclosing, string pattern, string detail, string lhs, string op, string rhs, File f
where
  row(anchor, enclosing, pattern, detail, lhs, op, rhs) and
  f = anchor.getLocation().getFile() and
  inMainSource(f)
select f.getRelativePath() as path, anchor.getLocation().getStartLine() as line, mavenModule(f) as moduleDir, pkgDir(f) as pkg,
  enclosing.getDeclaringType().getQualifiedName() as declaringType, enclosing.getName() as method,
  "enforcement" as place, pattern, detail, lhs, op, rhs
