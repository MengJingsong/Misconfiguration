/**
 * @id java/patterns/pattern1/case1
 * @name pattern1-case1
 * @description metadata is created directly inside if-else/if-then block
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern1

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
