import java

Callable getCallee(Call call) {
    (
        result.isStatic() and
        call.getCallee() = result and
        call.getCaller().calls(result)
    )
    or (
        (not result.isStatic()) and
        call.getCallee().getName() = result.getName() and
        call.getCaller().callsImpl(result)
    )
}

predicate callableEdges(Callable a, Callable b) {
    not (b.getFile().toString().matches("Test%")) and
    (
        (a.calls(b) and b.isStatic())
        or 
        (a.callsImpl(b) and not b.isStatic())
    )
}

predicate callEdges(Call a, Call b) {
    (not b.getFile().toString().matches("Test%")) and
    exists (
        Callable caller, Callable callee |
        a.getCaller() = caller and
        b.getCaller() = callee and 
        (
            (
                a.getCallee() = callee and
                caller.calls(callee)
            )
            or (
                a.getCallee().getName() = callee.getName() and
                a.getCallee().getNumberOfParameters() = callee.getNumberOfParameters() and
                caller.callsImpl(callee)
            )
        )
    )
}