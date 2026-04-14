/**
 * @id java/pattern1-2
 * @name pattern1-2
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */


import java
import semmle.code.java.dataflow.DataFlow

import Utils
import ConfigSig

predicate case2(DataFlow::Node sink, IfStmt ifStmt, MetadataCallable metadataCallable, Call call) {
    ifStmt.getCondition().getAChildExpr*() = sink.asExpr() and
    exists (Callable callable |
        getCallee(call) = callable and
        (
            ifStmt.getThen() = call.getEnclosingStmt().getParent() or
            ifStmt.getElse() = call.getEnclosingStmt().getParent() or
            ifStmt = call.getEnclosingStmt().getParent()
        ) and
        callableEdges+(callable, metadataCallable)
    )
}

import CassFlow::PathGraph

from
    CassFlow::PathNode source, CassFlow::PathNode sink, IfStmt ifStmt, MetadataCallable metadataCallable, Call call
where
    CassFlow::flowPath(source, sink) and
    case2(sink.getNode(), ifStmt, metadataCallable, call)
select
    metadataCallable, source, sink, "source is $@, sink is $@; ifStmt is $@; metadataCallable is $@ called by $@ ",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    metadataCallable, metadataCallable.toString(),
    call, call.toString()