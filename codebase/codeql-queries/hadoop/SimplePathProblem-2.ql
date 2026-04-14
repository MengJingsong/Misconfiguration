/**
 * @id java/hadoop/simple-path-flow-2
 * @name Simple path flow query 2
 * @description draft query
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import StateConfigSig
import HadoopStateFlow::PathGraph

from
    HadoopStateFlow::PathNode source, HadoopStateFlow::PathNode sink
where
    HadoopStateFlow::flowPath(source, sink)

select
    sink, source, sink, "Found a path from $@ to $@",
    source, source.toString(),
    sink, sink.toString()