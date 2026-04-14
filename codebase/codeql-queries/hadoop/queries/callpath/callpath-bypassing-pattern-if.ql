/**
 * @id java/callpath/callpath-bypassing-pattern-if
 * @name callpath-bypassing-pattern-if
 * @description find if there is a call path from startFile to INodeFile constructor that bypasses certain pattern if statements
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
    and not exists (
        Callable callable, Call call |
        // callable = getCallee(call) and
        callable = call.getCallee() and
        call.getEnclosingCallable() = b.getEnclosingCallable() and
        call.getLocation().getStartLine() < b.getLocation().getStartLine() and
        exists (
            TargetIfCallable targetCallable |
            callable.calls*(targetCallable)
            // callableEdges+(callable, targetCallable)
        )
    )
}

from 
    Call start, Call target
where
    start.getCaller() instanceof StartCallable and
    target.getCallee() instanceof TargetCallable and
    edges+(start, target)
select
    start, start, target, "Path found from $@ to $@",
    start, start.toString(),
    target, target.toString()