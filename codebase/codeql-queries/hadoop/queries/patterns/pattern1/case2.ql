/**
 * @id java/patterns/pattern1/case2
 * @name pattern1-case2
 * @description metadata is created transitively inside if-else/if-then block
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern1

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink,
    IfStmt ifStmt, ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    DefaultFlow::flowPath(source, sink) and
    case2(sink.getNode(), ifStmt, newObj, callWithMetadata, depthOfMetadata)
select
    newObj, source, sink, "source is $@, sink is $@; ifStmt is $@; newObj is $@ in $@ (" + depthOfMetadata + ")",
    source, source.toString(),
    sink, sink.toString(),
    ifStmt, ifStmt.toString(),
    newObj, newObj.toString(),
    callWithMetadata, callWithMetadata.toString()