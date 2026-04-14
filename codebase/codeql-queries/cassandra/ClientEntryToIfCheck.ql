/**
 * @id cassandra/client-entry-to-if-check
 * @name cassandra-client-api-to-if-check
 * @description client API that will call if-check
 * @kind path-problem
 * @problem.severity warning
 * @tags security
 */

import java

import ClientCallable
import Pattern2IfCallable
import Utils

query predicate edges(Callable callableA, Callable callableB) {
    dispatchCalls(callableA, callableB)
}

from
    ClientCallable start, Pattern2IfCallable target
where
    edges+(start, target)
select
    target, start, target, "Client API $@ will call if-checks $@",
    start, start.toString(),
    target, target.toString()