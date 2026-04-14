/**
 * @name pattern 2 export
 * @kind table
 * @id hadoop/pattern2-out
 * @description export the results of pattern 2 query.
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import Utils
import StateConfigSig

predicate pattern2(DataFlow::Node sink, IfStmt ifStmt) {
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr()
}

import HadoopStateFlow::PathGraph

from
    HadoopStateFlow::PathNode source, HadoopStateFlow::PathNode sink,
    IfStmt ifStmt, Callable callable
where
    HadoopStateFlow::flowPath(source, sink) 
    and pattern2(sink.getNode(), ifStmt) 
    and ifStmt.getEnclosingCallable() = callable
select
    callable.getFile().getRelativePath(),
    callable.getLocation().getStartLine()