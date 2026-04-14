/**
 * @id hadoop/callable-with-patterns
 * @name callable-with-patterns
 * @description find all callables that will call pattern-ifs
 * @kind table
 */

import java
import Utils
import Pattern2IfCallable

query predicate edges(Callable a, Callable b) {
    dispatchCalls(a, b)
    and not isForbiddenFile(a.getFile())
}

from
    Callable start, Pattern2IfCallable target
where
    edges+(start, target)
select
    start.getFile().getRelativePath(), start.getLocation().getStartLine()