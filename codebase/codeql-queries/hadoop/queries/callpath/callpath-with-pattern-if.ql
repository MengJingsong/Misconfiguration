/**
 * @id java/callpath/callpath-with-pattern-if
 * @name callpath-with-pattern-if
 * @description find if there is a call path from startFile to INodeFile constructor and contains certain pattern if statements
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import callpath.Utils
import callpath.PatternIfs
import StartAndEnd

query predicate edges(Call a, Call b) {
    callEdges(a, b)
}

from 
    Call start, Call target, Call mid, Call callWithIf, Callable callableWithIf, TargetIfCallable targetIfCallable
where
    start.getCaller() instanceof StartCallable and
    target.getCallee() instanceof TargetCallable and
    edges+(start, mid) and edges+(mid, target) and
    callWithIf.getEnclosingCallable() = mid.getEnclosingCallable() and
    callWithIf.getLocation().getStartLine() < mid.getLocation().getStartLine() and
    callableWithIf = getCallee(callWithIf) and
    callableWithIf.calls*(targetIfCallable)

select
    mid, start, mid, "callWithIf: $@", 
    callWithIf, callWithIf.toString()