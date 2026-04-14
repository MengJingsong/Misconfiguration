/**
 * @name pattern 2 export
 * @kind table
 * @id cassandra/pattern2-out
 * @description export the results of pattern 2 query.
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import Utils
import ConfigSig

predicate pattern2(DataFlow::Node sink, IfStmt ifStmt) {
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr()
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt, Callable callable
where
    CassFlow::flowPath(source, sink) 
    and pattern2(sink.getNode(), ifStmt) 
    and ifStmt.getEnclosingCallable() = callable
select
    callable.getFile().getRelativePath(),
    callable.getLocation().getStartLine(),
    ifStmt.getLocation().getStartLine()