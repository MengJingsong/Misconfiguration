/**
 * @id java/callpath/callpath
 * @name callpath
 * @description find if there is a call path from startFile to INodeFile constructor
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import callpath.Utils
import StartAndEnd

query predicate edges(Call a, Call b) {
    callEdges(a, b)
}

from 
    Call start, Call target
where
    start.getCaller() instanceof StartCallable and
    target.getCallee() instanceof TargetCallable and
    edges+(start, target)
select
    start, start, target, "path found from $@ to $@",
    start, start.toString(),
    target, target.toString()