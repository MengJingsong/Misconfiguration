/**
 * @id hadoop/client-api-without-patterns
 * @name hadoop-client-api-without-patterns
 * @description client API that will create metadata without any configuration checking.
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
    ClientCallable start, MetadataCallable target
where
    edges+(start, target) and
    not exists(Callable barrier |
        barrier instanceof Pattern2IfCallable and
        edges+(start, barrier)
    )
select
    target, start, target, "Client API $@ will call $@ without any configuration checking",
    start, start.toString(),
    target, target.toString()