/**
 * @id hadoop/client-api-with-patterns
 * @name hadoop-client-api-with-patterns
 * @description client API that will create metadata with configuration checking.
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java

import ClientCallable
import MetadataCallable
import Pattern2IfCallable
import Utils

query predicate edges(Callable callableA, Callable callableB) {
    dispatchCalls(callableA, callableB)
}

from
    ClientCallable start, MetadataCallable target, Pattern2IfCallable barrier
where
    edges+(start, target) and
    edges+(start, barrier)
select
    target, start, target, "Client API $@ will call $@ with configuration checking",
    start, start.toString(),
    target, target.toString()