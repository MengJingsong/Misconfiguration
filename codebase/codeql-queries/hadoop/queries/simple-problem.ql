/**
 * @id java/simple-query
 * @name Simple query
 * @description draft query
 * @kind problem
 * @problem.severity warning
 * @tags security
 */

import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

predicate validCallable(Callable callable) {
    callable.getFile().toString() = "DistributedFileSystem" and
    callable.getName() = "create" and
    callable.getLocation().getStartLine() >= 555 and
    callable.getLocation().getEndLine() <= 581
}

from
    Callable callable0, Call innerCall0,
    Callable innerAbstCallable1, Callable innerImplCallable1, Call innerCall1,
    Callable innerAbstCallable2, Callable innerImplCallable2
where
    validCallable(callable0) and
    innerCall0.getEnclosingCallable() = callable0 and
    innerCall0.getCallee() = innerAbstCallable1 and
    callable0.callsImpl(innerImplCallable1) and
    innerAbstCallable1.getName() = innerImplCallable1.getName() and
    innerImplCallable1.getFile().toString() = "FileSystemLinkResolver" and
    innerCall1.getEnclosingCallable() = innerImplCallable1 and
    innerCall1.getCallee() = innerAbstCallable2 and
    // not innerAbstCallable2.isStatic() and
    innerImplCallable1.callsImpl(innerImplCallable2) and
    innerAbstCallable2.getName() = innerImplCallable2.getName()
select
    callable0, "User API related Method $@ -> $@ = $@ -> $@ = $@/$@",
    callable0, callable0.toString(),
    innerCall0, innerCall0.toString(),
    innerImplCallable1, innerImplCallable1.toString(),
    innerCall1, innerCall1.toString(),
    innerAbstCallable2, innerAbstCallable2.toString(),
    innerImplCallable2, innerImplCallable2.toString()