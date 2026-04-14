import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import Utils

predicate case1(DataFlow::Node sink, IfStmt ifStmt, ClassInstanceExpr newObj) {
    not newObj.getFile().toString().matches("%Test%") and
    validMetadataNames(newObj.getType().getName()) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    (
        ifStmt.getThen() = newObj.getParent() or
        ifStmt.getElse() = newObj.getParent()
    )
}

predicate case2(DataFlow::Node sink, IfStmt ifStmt, 
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    (
        ifStmt.getThen() = callWithMetadata.getParent() or
        ifStmt.getElse() = callWithMetadata.getParent()
    )
}