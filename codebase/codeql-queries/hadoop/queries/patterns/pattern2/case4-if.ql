import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern2

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink,
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    DefaultFlow::flowPath(source, sink) and
    case4(sink.getNode(), ifStmt, callWithIfStmt, depthOfIfStmt, newObj, callWithMetadata, depthOfMetadata)
select
    ifStmt, ifStmt.getFile(), ifStmt.getLocation().getStartLine()
