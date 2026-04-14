import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import patterns.Pattern2

import DefaultFlow::PathGraph

from 
    DefaultFlow::PathNode source, DefaultFlow::PathNode sink,
    IfStmt ifStmt, MethodCall callWithIfStmt, int depthOfIfStmt,
    ClassInstanceExpr newObj
where
    DefaultFlow::flowPath(source, sink) and
    case2(sink.getNode(), ifStmt, callWithIfStmt, depthOfIfStmt, newObj)
select
    ifStmt, ifStmt.getFile(), ifStmt.getLocation().getStartLine()