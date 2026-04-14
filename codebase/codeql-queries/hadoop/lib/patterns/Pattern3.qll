import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import Utils

predicate case1(DataFlow::Node sink, IfStmt ifStmt, ClassInstanceExpr newObj) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithReturn(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    ifStmt.getEnclosingCallable() = newObj.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < newObj.getLocation().getStartLine()
}

predicate case2(DataFlow::Node sink, 
    IfStmt ifStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithReturn(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    ifStmt.getEnclosingCallable() = callWithMetadata.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < callWithMetadata.getLocation().getStartLine()
}