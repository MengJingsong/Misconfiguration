/**
 * @id java/simple-path-flow
 * @name Simple path flow query
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import callpath.Utils

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
    target, start, target, "Found a path from $@ to $@",
    start, start.toString(),
    target, target.toString()