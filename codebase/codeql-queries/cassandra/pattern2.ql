/**
 * @id java/pattern2
 * @name pattern2
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate pattern2(DataFlow::Node sink, IfStmt ifStmt) {
    ifStmtWithThrow(ifStmt) and
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr()
}


import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink,
    IfStmt ifStmt
where
    CassFlow::flowPath(source, sink) and
    pattern2(sink.getNode(), ifStmt)
select
    ifStmt, source, sink, "source is $@, sink is $@; ifStmt is $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString()