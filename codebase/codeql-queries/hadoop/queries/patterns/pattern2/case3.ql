/**
 * @id java/patterns/pattern2/case3
 * @name pattern2-case3
 * @description level-0 exception inside if and before level-1+ metadata creation
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
    IfStmt ifStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    DefaultFlow::flowPath(source, sink) and
    case3(sink.getNode(), ifStmt, newObj, callWithMetadata, depthOfMetadata)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; newObj (" + depthOfMetadata + ") is $@ in $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    newObj, newObj.toString(),
    callWithMetadata, callWithMetadata.toString()