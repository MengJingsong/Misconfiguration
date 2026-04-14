/**
 * @id java/pattern3-1
 * @name pattern3-1
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case1(DataFlow::Node sink, IfStmt ifStmt, ClassInstanceExpr newObj) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithReturn(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validMetadataNames(newObj.getType().getName()) and
    ifStmt.getEnclosingCallable() = newObj.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < newObj.getLocation().getStartLine()
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt, ClassInstanceExpr newObj
where
    CassFlow::flowPath(source, sink) and
    case1(sink.getNode(), ifStmt, newObj)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; newObj is $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    newObj, newObj.toString()