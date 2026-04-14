/**
 * @id java/pattern2-4
 * @name pattern2-4
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case4(DataFlow::Node sink, 
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validMetadataNames(newObj.getType().getName()) and
    methodCallWithIfStmt(callWithIfStmt, ifStmt, depthOfIfStmt) and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    callWithIfStmt.getEnclosingCallable() = callWithMetadata.getEnclosingCallable() and
    callWithIfStmt.getLocation().getEndLine() < callWithMetadata.getLocation().getStartLine()
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    CassFlow::flowPath(source, sink) and
    case4(sink.getNode(), ifStmt, callWithIfStmt, depthOfIfStmt, newObj, callWithMetadata, depthOfMetadata)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; callWithIfStmt is $@; callWithMetadata is $@; newObj is $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    callWithIfStmt, callWithIfStmt.toString(),
    callWithMetadata, callWithMetadata.toString(),
    newObj, newObj.toString()