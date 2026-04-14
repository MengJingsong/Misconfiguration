import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern2

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink,
    IfStmt ifStmt,
    ClassInstanceExpr newObj, MethodCall callWithMetadata, int depthOfMetadata
where
    DefaultFlow::flowPath(source, sink) and
    case3(sink.getNode(), ifStmt, newObj, callWithMetadata, depthOfMetadata)
select
    ifStmt, ifStmt.getFile(), ifStmt.getLocation().getStartLine()