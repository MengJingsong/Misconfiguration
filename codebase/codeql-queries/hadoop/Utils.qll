import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
import HadoopHDFSConfigs
import HadoopYARNConfigs
import HadoopMapRedConfigs

Callable getCallee(Call call) {
    (
        result.isStatic() and
        call.getCallee() = result and
        call.getCaller().calls(result) and
        call.getNumArgument() = result.getNumberOfParameters()
    )
    or (
        (not result.isStatic()) and
        call.getCallee().getName() = result.getName() and
        call.getCaller().callsImpl(result) and
        call.getNumArgument() = result.getNumberOfParameters()
    )
}

predicate dispatchCalls(Callable a, Callable b) {
    (a.calls(b) and b.isStatic())
    or 
    (a.callsImpl(b) and not b.isStatic())
}

predicate isForbiddenFile(File file) {
    file.getRelativePath().regexpMatch(".*([Tt]est|[Ee]xample|[Ee]xception).*")
}

predicate ifStmtWithThrow(IfStmt ifStmt) {
    exists(
        ThrowStmt throwStmt |
        ifStmt.getElse() = throwStmt.getParent() or
        ifStmt.getThen() = throwStmt.getParent()
    )
}

predicate ifStmtWithReturn(IfStmt ifStmt) {
    exists(
        ReturnStmt returnStmt |
        ifStmt.getElse() = returnStmt.getParent() or
        ifStmt.getThen() = returnStmt.getParent()
    )
}

// // Predicate to check if a method call that creates a metadata object inside.
// predicate methodCallWithMetadata(MethodCall call, ClassInstanceExpr newObj, int depth) {
//     validHadoopMetadataNames(newObj.getType().getName()) and
//     depth in [1 .. 5] and
//     (
//         (depth = 1 and newObj.getEnclosingCallable() = call.getCallee()) or
//         (
//             depth > 1 and
//             exists(
//                 MethodCall innerCall |
//                 call.getCallee() = innerCall.getCaller() and
//                 methodCallWithMetadata(innerCall, newObj, depth - 1)
//             )
//         )
//     )
// }

// predicate methodCallWithIfStmt(MethodCall call, IfStmt ifStmt, int depth) {
//     depth in [1 .. 5] and
//     (
//         (depth = 1 and ifStmt.getEnclosingCallable() = call.getCallee()) or
//         (
//             depth > 1 and
//             exists(
//                 MethodCall innerCall |
//                 call.getCallee() = innerCall.getCaller() and
//                 methodCallWithIfStmt(innerCall, ifStmt, depth - 1)
//             )
//         )   
//     )
// }