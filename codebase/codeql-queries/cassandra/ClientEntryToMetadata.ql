/**
 * @id cassandra/client-entry-to-metadata
 * @name cassandra-client-entry-to-metadata
 * @description client entry that will create metadata
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java

import ClientCallable
import MetadataCallable
import Utils

query predicate edges(Callable callableA, Callable callableB) {
    dispatchCalls(callableA, callableB)
}

from
    ClientCallable start, MetadataCallable target
where
    edges+(start, target)
select
    target, start, target, "Client entry $@ will call $@",
    start, start.toString(),
    target, target.toString()