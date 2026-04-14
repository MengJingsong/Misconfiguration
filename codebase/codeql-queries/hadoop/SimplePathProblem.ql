/**
 * @id java/hadoop/simple-path-flow
 * @name Simple path flow query
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import ConfigSig
import HadoopFlow::PathGraph

from
    HadoopFlow::PathNode source, HadoopFlow::PathNode sink, MethodCall methodCall, DataFlow::Node next, AssignExpr assignExpr
where
    HadoopFlow::flowPath(source, sink) and
    methodCall.getMethod().getName() = "getLongBytes" and
    next.asExpr().getType().getName() = "long" and
    assignExpr.getRhs() = methodCall and
    methodCall.getAnArgument() = sink.getNode().asExpr() and
    assignExpr.getDest() = next.asExpr()

select
    sink, source, sink, "Found a path from $@ to $@, next is $@, assignExpr is $@",
    source, source.toString(),
    sink, sink.toString(),
    next, next.toString(),
    assignExpr, assignExpr.toString()