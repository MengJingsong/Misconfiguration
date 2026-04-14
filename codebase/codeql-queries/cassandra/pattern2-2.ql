/**
 * @id java/pattern2-2
 * @name pattern2-2
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case2(DataFlow::Node sink, IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt, ClassInstanceExpr newObj) {
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validMetadataNames(newObj.getType().getName()) and
    methodCallWithIfStmt(callWithIfStmt, ifStmt, depthOfIfStmt) and
    callWithIfStmt.getEnclosingCallable() = newObj.getEnclosingCallable() and
    callWithIfStmt.getLocation().getEndLine() < newObj.getLocation().getStartLine() and
    not newObj.getFile().toString().matches("%Test%")
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt, MethodCall callWithIfStmt, ClassInstanceExpr newObj, int depthOfIfStmt
where
    CassFlow::flowPath(source, sink) and
    case2(sink.getNode(), ifStmt, callWithIfStmt, depthOfIfStmt, newObj)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; callWithIfStmt is $@; newObj is $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    callWithIfStmt, callWithIfStmt.toString(),
    newObj, newObj.toString()