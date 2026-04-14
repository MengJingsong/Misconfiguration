/**
 * @id java/patterns/pattern2/case2
 * @name pattern2-case2
 * @description level-1+ exception inside if and before level-0 metadata creation
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern2

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink,
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj
where
    DefaultFlow::flowPath(source, sink) and
    case2(sink.getNode(), ifStmt, callWithIfStmt, depthOfIfStmt, newObj)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt (" + depthOfIfStmt + ") is $@ in $@; newObj is $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    callWithIfStmt, callWithIfStmt.toString(),
    newObj, newObj.toString()
