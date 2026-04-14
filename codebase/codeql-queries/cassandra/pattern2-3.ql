/**
 * @id java/pattern2-3
 * @name pattern2-3
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case3(DataFlow::Node sink, 
    IfStmt ifStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validMetadataNames(newObj.getType().getName()) and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    ifStmt.getEnclosingCallable() = callWithMetadata.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < callWithMetadata.getLocation().getStartLine()
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt, ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    CassFlow::flowPath(source, sink) and
    case3(sink.getNode(), ifStmt, newObj, callWithMetadata, depthOfMetadata)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; callWithMetadata is $@; newObj is $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    callWithMetadata, callWithMetadata.toString(),
    newObj, newObj.toString()