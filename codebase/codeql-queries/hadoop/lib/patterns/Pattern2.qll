import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import Utils

predicate case1(DataFlow::Node sink, IfStmt ifStmt, ClassInstanceExpr newObj) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    ifStmt.getEnclosingCallable() = newObj.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < newObj.getLocation().getStartLine()
}

predicate case2(DataFlow::Node sink, 
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    methodCallWithIfStmt(callWithIfStmt, ifStmt, depthOfIfStmt) and
    callWithIfStmt.getEnclosingCallable() = newObj.getEnclosingCallable() and
    callWithIfStmt.getLocation().getEndLine() < newObj.getLocation().getStartLine()
}

predicate case3(DataFlow::Node sink, 
    IfStmt ifStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    ifStmt.getEnclosingCallable() = callWithMetadata.getEnclosingCallable() and
    ifStmt.getLocation().getEndLine() < callWithMetadata.getLocation().getStartLine()
}

predicate case4(DataFlow::Node sink, 
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata) {
    not newObj.getFile().toString().matches("%Test%") and
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    validHadoopMetadataNames(newObj.getType().getName()) and
    methodCallWithIfStmt(callWithIfStmt, ifStmt, depthOfIfStmt) and
    methodCallWithMetadata(callWithMetadata, newObj, depthOfMetadata) and
    callWithIfStmt.getEnclosingCallable() = callWithMetadata.getEnclosingCallable() and
    callWithIfStmt.getLocation().getEndLine() < callWithMetadata.getLocation().getStartLine()
}