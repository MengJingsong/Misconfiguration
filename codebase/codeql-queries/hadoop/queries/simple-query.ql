import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import callpath.Utils
import callpath.PatternIfs

query predicate edges(Call a, Call b) {
    callEdges(a, b)
    // and not exists (
    //     Callable callable, Call call |
    //     callable = getCallee(call) and
    //     call.getEnclosingCallable() = b.getEnclosingCallable() and
    //     call.getLocation().getStartLine() < b.getLocation().getStartLine() and
    //     exists (
    //         TargetIfCallable targetCallable |
    //         callableEdges+(callable, targetCallable)
    //     )
    // )
}

// query predicate edges(Call a, Call b) {
//     callEdges(a, b)
//     and not exists (
//         Callable callable, Call call |
//         callable.getAReference() = call and
//         call.getEnclosingCallable() = b.getEnclosingCallable() and
//         call.getLocation().getStartLine() < b.getLocation().getStartLine() and
//         exists (
//             TargetIfCallable targetCallable |
//             callable.calls*(targetCallable)
//         )
//     )
// }

// from 
//     StartCallable start, TargetCallable target
// where
//     start.calls(target) or
//     start.callsImpl(target)
// select
//     start, target

// from 
//     Call start, Callable callable, Call target
// where
//     start.getCaller() instanceof StartCallable
//     and start.getCallee().getName() = "create"
//     and callable = getCallee(start)
//     and target.getCaller() = callable
// select
//     start, callable, target, target.getCallee()

from 
    Call start, Call target
where
    start.getCaller() instanceof StartCallable and
    target.getCallee() instanceof TargetCallable and
    edges+(start, target)
select
    start, target

// from 
//     Call start, Call target, Call mid, Call callWithIf, Callable callableWithIf, TargetIfCallable targetIfCallable
// where
//     start.getCaller() instanceof StartCallable
//     and target.getCallee() instanceof TargetCallable
//     and edges+(start, mid) and edges+(mid, target)
//     // and callWithIf.getEnclosingCallable() = mid.getEnclosingCallable()
//     // and callWithIf.getLocation().getStartLine() < mid.getLocation().getStartLine()
//     // and callableWithIf = getCallee(callWithIf)
//     // and callableWithIf.calls*(targetIfCallable)

// select
//     mid
//     // , callWithIf
//     // , callableWithIf
//     // , targetIfCallable