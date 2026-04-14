/**
 * @id hadoop/pattern2
 * @name hadoop-pattern2
 * @description configuration restrictions will lead to exception.
 * @kind path-problem
 * @problem.severity warning
 * @tags security
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
    IfStmt ifStmt
where
    HadoopStateFlow::flowPath(source, sink) and
    pattern2(sink.getNode(), ifStmt)
select
    sink, source, sink, "source is $@, sink is $@; ifStmt is $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString()