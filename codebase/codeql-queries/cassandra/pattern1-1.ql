/**
 * @id java/pattern1-1
 * @name pattern1-1
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case1(DataFlow::Node sink, IfStmt ifStmt, MetadataCallable metadataCallable, Call call) {
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    getCallee(call) = metadataCallable and
    (
        ifStmt.getThen() = call.getEnclosingStmt().getParent() or
        ifStmt.getElse() = call.getEnclosingStmt().getParent() or
        ifStmt = call.getEnclosingStmt().getParent()
    )
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink, IfStmt ifStmt, MetadataCallable metadataCallable, Call call
where
    CassFlow::flowPath(source, sink) and
    case1(sink.getNode(), ifStmt, metadataCallable, call)
select
    sink.getNode(), source, sink, "source is $@, sink is $@; ifStmt is $@; metadataCallable is $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    call, call.toString()