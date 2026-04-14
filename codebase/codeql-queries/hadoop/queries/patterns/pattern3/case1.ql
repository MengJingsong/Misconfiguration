/**
 * @id java/patterns/pattern3/case1
 * @name pattern3-case1
 * @description return inside if and before level-0 metadata creation
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern3

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink, IfStmt ifStmt, ClassInstanceExpr newObj
where
    DefaultFlow::flowPath(source, sink) and
    case1(sink.getNode(), ifStmt, newObj)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; newObj is $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    newObj, newObj.toString()