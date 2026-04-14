/**
 * @id java/cassandra/simple-path-flow
 * @name Simple path flow query
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
// import Utils
import ConfigSig

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink, IfStmt ifStmt
where
    CassFlow::flowPath(source, sink)
    and ifStmt.getCondition().getAChildExpr*() = sink.getNode().asExpr()
select
    sink, source, sink, "Found a path from $@ to $@ in ifStmt $@",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString()