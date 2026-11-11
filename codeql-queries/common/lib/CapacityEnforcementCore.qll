/**
 * System-agnostic predicates for the stage-1 extension of `capacity-enforcement-exp`
 * beyond `if` statements (decided 2026-11-11).
 *
 * Two kinds of place (experiments/capacity-enforcement-exp/README.md §3.7):
 * - an enforcement place, where usage is compared with a capacity, in any form
 *   (§3.7.2): a comparison outside an `if` condition, a comparison without an
 *   operator (clamp, comparator, overflow check, bit sizing), a verdict used deeper
 *   or in a `switch`, a library call that enforces a capacity, an exception handler;
 * - a capacity-set place, where a capacity gets its value: the writes of a field
 *   that is an operand of a magnitude comparison, and the creation of a container
 *   with a size argument.
 *
 * Matching is structural or by API signature (declaring type + method name), never
 * by identifier names in the system's own code, so stage 1 keeps its "no keyword
 * list" rule. Like the four `if` queries, these only shrink the search space; stage 2
 * ranks the rows and stage 3 decides.
 *
 * Imported as `import common.lib.CapacityEnforcementCore` (via each pack's `common`
 * symlink), next to `common.lib.IfCheckCore`.
 */

import java
import common.lib.IfCheckCore

/* ---------------------------------------------------------------------------
 * Helpers
 * ------------------------------------------------------------------------- */

/** `t`, or its generic source declaration, has `pkg.name` among its supertypes (itself included). */
bindingset[pkg, name]
predicate hasSupertypeNamed(RefType t, string pkg, string name) {
  exists(RefType s |
    s = t.getSourceDeclaration().getASupertype*().getSourceDeclaration() and
    s.hasQualifiedName(pkg, name)
  )
}

/** `mc` calls a method named `name` declared on (a subtype of) `pkg.type`. */
bindingset[pkg, type, name]
predicate callsApi(MethodCall mc, string pkg, string type, string name) {
  mc.getMethod().getName() = name and
  hasSupertypeNamed(mc.getMethod().getDeclaringType(), pkg, type)
}

/** `e` is `anc` or nested inside it, without leaving `anc`'s callable (lambdas stay separate). */
predicate within(Expr e, Expr anc) {
  e.getParent*() = anc and e.getEnclosingCallable() = anc.getEnclosingCallable()
}

/**
 * Where a size or capacity value comes from, from the expression alone, following a
 * local variable to its definitions within the method. Several kinds are joined by
 * `+` in the query output.
 */
string sizeSourceKind(Expr e) {
  e instanceof CompileTimeConstantExpr and
  (if e instanceof Literal then result = "literal" else result = "constant")
  or
  not e instanceof CompileTimeConstantExpr and
  (
    exists(Field f | e.(VarAccess).getVariable() = f |
      if f.isStatic() and f.isFinal() then result = "static-final-field" else result = "field"
    )
    or
    e.(VarAccess).getVariable() instanceof Parameter and result = "parameter"
    or
    exists(LocalVariableDecl v | e.(VarAccess).getVariable() = v |
      result = sizeSourceKind(v.getAnAssignedValue())
    )
    or
    e.(MethodCall).getNumArgument() = 0 and result = "no-arg-call"
    or
    e.(MethodCall).getNumArgument() > 0 and result = "call"
    or
    ((e instanceof AddExpr or e instanceof SubExpr or e instanceof MulExpr or e instanceof DivExpr or e instanceof RemExpr or e instanceof LeftShiftExpr or e instanceof RightShiftExpr or e instanceof UnsignedRightShiftExpr) or e instanceof BitwiseExpr or e instanceof CastingExpr or
     e instanceof ConditionalExpr) and
    result = "computed"
    or
    not e instanceof VarAccess and
    not e instanceof MethodCall and
    not (e instanceof AddExpr or e instanceof SubExpr or e instanceof MulExpr or e instanceof DivExpr or e instanceof RemExpr or e instanceof LeftShiftExpr or e instanceof RightShiftExpr or e instanceof UnsignedRightShiftExpr) and
    not e instanceof BitwiseExpr and
    not e instanceof CastingExpr and
    not e instanceof ConditionalExpr and
    result = "other"
  )
}

/** Short text for an expression in the output (operand names for variables and calls). */
string exprText(Expr e) { result = operandName(e) }

/* ---------------------------------------------------------------------------
 * Enforcement places, form 1: a candidate comparison outside an `if` condition
 * ------------------------------------------------------------------------- */

/**
 * `s` is a counted loop and `cmp` tests its counter: an operand of `cmp` is a variable
 * that the loop's update clause increments, decrements or assigns (`for (i = 0; i < n; i++)`).
 * Kept as a row and tagged `for-counter`, so the pilot can measure how much of the
 * loop-condition form is plain iteration.
 */
predicate countedLoop(ForStmt s, BinaryExpr cmp) {
  exists(Variable v, Expr u |
    u = s.getAnUpdate() and
    cmp.getAnOperand().(VarAccess).getVariable() = v and
    (
      u.(UnaryAssignExpr).getExpr().(VarAccess).getVariable() = v or
      u.(Assignment).getDest().(VarAccess).getVariable() = v
    )
  )
}

/** The comparison sits in an `if` condition: already a row of NarrowedIfStatements.ql. */
predicate inIfCorpus(BinaryExpr cmp) { cmp.getEnclosingStmt() instanceof IfStmt }

/**
 * The context of a candidate comparison that is not in an `if` condition. A comparison
 * can have several contexts (a ternary inside a `return`); the pilot script keeps the
 * first in README §3.7.2 order.
 */
predicate comparisonContext(BinaryExpr cmp, string ctx, string detail) {
  isCandidateComparison(cmp, _, _) and
  not inIfCorpus(cmp) and
  (
    exists(ConditionalExpr ce | within(cmp, ce.getCondition())) and
    ctx = "ternary" and detail = ""
    or
    exists(WhileStmt s | within(cmp, s.getCondition())) and ctx = "loop-condition" and detail = "while"
    or
    exists(DoStmt s | within(cmp, s.getCondition())) and ctx = "loop-condition" and detail = "do"
    or
    exists(ForStmt s | within(cmp, s.getCondition()) |
      ctx = "loop-condition" and
      if countedLoop(s, cmp) then detail = "for-counter" else detail = "for"
    )
    or
    exists(SwitchStmt s | within(cmp, s.getExpr())) and ctx = "switch-selector" and detail = ""
    or
    exists(SwitchExpr s | within(cmp, s.getExpr())) and ctx = "switch-selector" and detail = ""
    or
    exists(LambdaExpr l | cmp.getEnclosingCallable() = l.asMethod()) and
    ctx = "lambda" and detail = ""
    or
    cmp.getEnclosingStmt() instanceof AssertStmt and ctx = "assert" and detail = ""
    or
    cmp.getEnclosingStmt() instanceof ReturnStmt and ctx = "return" and detail = ""
    or
    exists(Call c | within(cmp, c.getAnArgument()) |
      ctx = "argument" and
      detail = c.getCallee().getDeclaringType().getName() + "." + c.getCallee().getName()
    )
    or
    exists(Assignment a | within(cmp, a.getRhs())) and ctx = "assignment" and detail = ""
    or
    exists(LocalVariableDeclExpr d | within(cmp, d.getInit())) and
    ctx = "declaration" and detail = ""
    or
    exists(Field f | within(cmp, f.getInitializer())) and ctx = "field-initializer" and detail = ""
  )
}

/* ---------------------------------------------------------------------------
 * Enforcement places, form 2: comparisons without a comparison operator
 * ------------------------------------------------------------------------- */

/** `Math.min`/`max`, Guava `constrainToRange`/`saturatedCast`: a clamp. */
predicate clampCall(MethodCall mc, string api) {
  exists(string n | n = mc.getMethod().getName() |
    (callsApi(mc, "java.lang", "Math", n) or callsApi(mc, "java.lang", "StrictMath", n)) and
    n = ["min", "max", "clamp"] and
    api = "Math." + n
    or
    callsApi(mc, "com.google.common.primitives", ["Ints", "Longs", "Shorts", "UnsignedInts", "UnsignedLongs"], n) and
    n = ["constrainToRange", "saturatedCast"] and
    api = mc.getMethod().getDeclaringType().getName() + "." + n
  ) and
  // not a clamp of two literals
  not forall(Expr a | a = mc.getAnArgument() | a instanceof CompileTimeConstantExpr)
}

/** A clamp whose argument is a difference (`cap - used`): the remaining capacity. */
predicate clampOnRemaining(MethodCall mc) {
  clampCall(mc, _) and mc.getAnArgument() instanceof SubExpr
}

/** `Long.compare`, `Integer.compareUnsigned`, numeric `compareTo`. */
predicate comparatorCall(MethodCall mc, string api) {
  exists(string n | n = mc.getMethod().getName() |
    n = ["compare", "compareUnsigned"] and
    callsApi(mc, "java.lang", ["Long", "Integer", "Short", "Byte", "Double", "Float"], n) and
    api = mc.getMethod().getDeclaringType().getName() + "." + n
    or
    n = "compareTo" and
    (
      isNumeric(mc.getQualifier()) or
      hasSupertypeNamed(mc.getQualifier().getType(), "java.math", ["BigInteger", "BigDecimal"])
    ) and
    api = "compareTo"
    or
    callsApi(mc, "com.google.common.primitives", ["Ints", "Longs", "UnsignedInts", "UnsignedLongs"], n) and
    n = "compare" and
    api = mc.getMethod().getDeclaringType().getName() + ".compare"
  )
}

/** Capacity tests on JDK/Netty buffers: `hasRemaining()`, `isWritable(n)`, `ensureWritable(n)`. */
predicate bufferCapacityCall(MethodCall mc, string api) {
  callsApi(mc, "java.nio", "Buffer", "hasRemaining") and api = "Buffer.hasRemaining"
  or
  exists(string n | n = ["isWritable", "ensureWritable", "maxWritableBytes", "writableBytes"] |
    callsApi(mc, "io.netty.buffer", "ByteBuf", n) and api = "ByteBuf." + n
  )
  or
  callsApi(mc, "io.netty.channel", "Channel", "isWritable") and api = "Channel.isWritable"
}

/** Power-of-two size classes: `numberOfLeadingZeros`, `highestOneBit`, ... */
predicate bitSizeCall(MethodCall mc, string api) {
  exists(string n |
    n = ["numberOfLeadingZeros", "numberOfTrailingZeros", "highestOneBit", "lowestOneBit"] and
    callsApi(mc, "java.lang", ["Integer", "Long"], n) and
    api = mc.getMethod().getDeclaringType().getName() + "." + n
  )
}

/** A type-width limit enforced by throwing: `Math.addExact`, `toIntExact`, Guava `checkedCast`. */
predicate overflowCheckCall(MethodCall mc, string api) {
  exists(string n | n = mc.getMethod().getName() |
    callsApi(mc, "java.lang", ["Math", "StrictMath"], n) and
    n = ["addExact", "subtractExact", "multiplyExact", "incrementExact", "decrementExact",
        "negateExact", "toIntExact"] and
    api = "Math." + n
    or
    callsApi(mc, "com.google.common.primitives", ["Ints", "Longs", "Shorts", "Chars", "SignedBytes", "UnsignedBytes", "UnsignedInts"], n) and
    n = "checkedCast" and
    api = mc.getMethod().getDeclaringType().getName() + ".checkedCast"
  )
}

/** Index/size checks that throw: Guava `checkElementIndex`, `Objects.checkIndex`, ... */
predicate indexCheckCall(MethodCall mc, string api) {
  exists(string n | n = mc.getMethod().getName() |
    callsApi(mc, "com.google.common.base", "Preconditions", n) and
    n = ["checkElementIndex", "checkPositionIndex", "checkPositionIndexes"] and
    api = "Preconditions." + n
    or
    callsApi(mc, "java.util", "Objects", n) and
    n = ["checkIndex", "checkFromToIndex", "checkFromIndexSize"] and
    api = "Objects." + n
  )
}

/* ---------------------------------------------------------------------------
 * Enforcement places, form 3: enforcement delegated to a library, exceptions
 * ------------------------------------------------------------------------- */

/** A call whose capacity check runs inside a library: bounded queues, semaphores. */
predicate delegatedEnforcementCall(MethodCall mc, string api) {
  exists(string n | n = mc.getMethod().getName() |
    n = ["offer", "put", "add", "offerFirst", "offerLast", "putFirst", "putLast"] and
    callsApi(mc, "java.util.concurrent", "BlockingQueue", n) and
    api = "BlockingQueue." + n
    or
    n = ["offer", "relaxedOffer"] and
    callsApi(mc, "org.jctools.queues", "MessagePassingQueue", n) and
    api = "MessagePassingQueue." + n
    or
    n = ["tryAcquire", "acquire", "acquireUninterruptibly"] and
    callsApi(mc, "java.util.concurrent", "Semaphore", n) and
    api = "Semaphore." + n
  )
}

/** A handler for an exception a capacity or type-width limit throws. */
predicate capacityExceptionCatch(CatchClause cc, string api) {
  exists(RefType t | t = cc.getACaughtType() |
    t.hasQualifiedName("java.nio", "BufferOverflowException") and api = "BufferOverflowException"
    or
    t.hasQualifiedName("java.lang", ["IndexOutOfBoundsException", "ArrayIndexOutOfBoundsException", "ArithmeticException", "OutOfMemoryError", "NegativeArraySizeException"]) and
    api = t.getName()
    or
    t.hasQualifiedName("java.util.concurrent", "RejectedExecutionException") and
    api = "RejectedExecutionException"
    or
    t.hasQualifiedName("java.lang", "IllegalStateException") and
    exists(MethodCall mc | delegatedEnforcementCall(mc, _) and mc.getEnclosingStmt().getEnclosingStmt*() = cc.getTry().getBlock()) and
    api = "IllegalStateException(around a bounded add)"
  )
}

/* ---------------------------------------------------------------------------
 * Enforcement places, form 4: a verdict used deeper, through overrides, or in a switch
 * ------------------------------------------------------------------------- */

/** `c` holds a candidate comparison in its own body. */
predicate holdsComparison(Callable c) {
  exists(BinaryExpr cmp | isCandidateComparison(cmp, _, _) and cmp.getEnclosingCallable() = c)
}

/** `c` calls `x` (virtual dispatch included), both in the analysed source. */
predicate sourceCall(Callable c, Callable x) { c.polyCalls(x) and c.fromSource() and x.fromSource() }

/**
 * The fewest call levels (0, 1 or 2; dispatch included) from `c` to a candidate
 * comparison. Deeper chains are not followed: the pilot measures whether 2 is enough.
 */
int comparisonDepth(Callable c) {
  c.fromSource() and
  (
    holdsComparison(c) and result = 0
    or
    not holdsComparison(c) and
    exists(Callable x | sourceCall(c, x) and holdsComparison(x)) and
    result = 1
    or
    not holdsComparison(c) and
    not exists(Callable x | sourceCall(c, x) and holdsComparison(x)) and
    exists(Callable x, Callable y | sourceCall(c, x) and sourceCall(x, y) and holdsComparison(y)) and
    result = 2
  )
}

/**
 * A place where a method's verdict is used: `call` sits in the condition of an `if`,
 * loop or ternary, or in a `switch` selector, and some implementation `impl` of its
 * target (the static target or an override) reaches a candidate comparison.
 * `already` holds for the rows HelperGuardedIfStatements.ql already emits (an `if`
 * condition, a boolean static target, the comparison in its own body).
 */
predicate verdictUse(MethodCall call, string ctx, Callable impl, int depth, boolean already) {
  (
    exists(IfStmt s | within(call, s.getCondition())) and ctx = "verdict-if"
    or
    exists(LoopStmt s | within(call, s.getCondition())) and ctx = "verdict-loop"
    or
    exists(ConditionalExpr ce | within(call, ce.getCondition())) and ctx = "verdict-ternary"
    or
    exists(SwitchStmt s | within(call, s.getExpr())) and ctx = "verdict-switch"
    or
    exists(SwitchExpr s | within(call, s.getExpr())) and ctx = "verdict-switch"
  ) and
  (impl = call.getMethod().getSourceDeclaration() or impl.(Method).overrides+(call.getMethod().getSourceDeclaration())) and
  depth = comparisonDepth(impl) and
  (
    if
      ctx = "verdict-if" and
      impl = call.getMethod().getSourceDeclaration() and
      call.getMethod().getReturnType().hasName("boolean") and
      depth = 0
    then already = true
    else already = false
  )
}

/* ---------------------------------------------------------------------------
 * Capacity-set places
 * ------------------------------------------------------------------------- */

/** `g` is a one-return, no-argument method that returns field `f` (or a call on it, `conf.x.toBytes()`). */
predicate getterOf(Method g, Field f) {
  g.fromSource() and
  g.getNumberOfParameters() = 0 and
  count(ReturnStmt r | r.getEnclosingCallable() = g) = 1 and
  exists(ReturnStmt r | r.getEnclosingCallable() = g |
    r.getExpr().(VarAccess).getVariable() = f
    or
    r.getExpr().(MethodCall).getQualifier().(VarAccess).getVariable() = f
  )
}

/**
 * Field `f` is read inside an operand of a magnitude candidate comparison, or inside
 * an argument of a clamp, directly or through a one-line getter, as a numeric value
 * (the getter may return `conf.x.toBytes()`, so `f` itself need not be numeric). Equality comparisons
 * are left out: a capacity is compared by magnitude (IfCheckCore.qll, `opClass`).
 */
predicate comparedField(Field f, Expr use) {
  f.fromSource() and
  (
    exists(BinaryExpr cmp, Expr e |
      isCandidateComparison(cmp, _, _) and
      opClass(cmp) = "magnitude" and
      within(e, cmp.getAnOperand()) and
      use = cmp
    |
      isNumeric(e) and
      (e.(VarAccess).getVariable() = f or getterOf(e.(MethodCall).getMethod(), f))
    )
    or
    exists(MethodCall mc, Expr e | clampCall(mc, _) and within(e, mc.getAnArgument()) and use = mc |
      isNumeric(e) and
      (e.(VarAccess).getVariable() = f or getterOf(e.(MethodCall).getMethod(), f))
    )
  )
}

/**
 * A place where field `f` gets a value: its initializer, or a plain assignment (not
 * `+=` and the like, which change usage). `kind` is where it happens: a field
 * initializer, a constructor, a static or instance initializer block, or a method (a
 * setter or a runtime resize).
 */
predicate fieldValueSet(Field f, Expr site, Expr value, string kind) {
  value = f.getInitializer() and site = value and kind = "field-initializer"
  or
  exists(AssignExpr a |
    a.getDest().(VarAccess).getVariable() = f and site = a and value = a.getRhs() and
    // the extractor also models a field initializer as an assignment in an initializer method
    not a.getRhs() = f.getInitializer()
  |
    a.getEnclosingCallable() instanceof Constructor and kind = "constructor"
    or
    a.getEnclosingCallable() instanceof StaticInitializer and kind = "static-initializer"
    or
    a.getEnclosingCallable() instanceof InstanceInitializer and kind = "instance-initializer"
    or
    a.getEnclosingCallable() instanceof Method and
    not a.getEnclosingCallable() instanceof InitializerMethod and
    kind = "method"
  )
}

/** The first numeric argument of `c` (the size argument of a sized constructor). */
Expr firstNumericArgument(Call c) {
  result = c.getArgument(min(int i | isNumeric(c.getArgument(i))))
}

/** A library container type whose constructor takes a size: collections, maps, builders, buffered streams. */
predicate sizedLibraryType(RefType t) {
  not t.getSourceDeclaration().fromSource() and
  (
    hasSupertypeNamed(t, "java.util", ["Collection", "Map", "BitSet"]) or
    hasSupertypeNamed(t, "java.lang", ["StringBuilder", "StringBuffer"]) or
    hasSupertypeNamed(t, "java.io", ["OutputStream", "Writer", "BufferedInputStream", "BufferedReader"]) or
    hasSupertypeNamed(t, "java.util.concurrent", "Semaphore") or
    hasSupertypeNamed(t, "io.netty.channel", "WriteBufferWaterMark") or
    hasSupertypeNamed(t, "org.jctools.queues", "MessagePassingQueue")
  )
}

/**
 * A container created with a size: an array, a sized library constructor, a buffer
 * allocation, a sized Guava/Netty factory, a cache builder limit. `size` is the size
 * argument; `api` names the form.
 */
predicate containerCreation(Expr site, Expr size, string api) {
  size = site.(ArrayCreationExpr).getDimension(0) and
  api = "new " + site.(ArrayCreationExpr).getType().(Array).getElementType().getName() + "[]"
  or
  exists(ClassInstanceExpr cie, RefType t |
    site = cie and t = cie.getConstructedType() and sizedLibraryType(t) and
    size = firstNumericArgument(cie) and
    api = "new " + t.getSourceDeclaration().getName()
  )
  or
  exists(MethodCall mc, string n | site = mc and n = mc.getMethod().getName() |
    callsApi(mc, "java.nio", "ByteBuffer", n) and n = ["allocate", "allocateDirect"] and
    size = mc.getArgument(0) and api = "ByteBuffer." + n
    or
    callsApi(mc, "com.google.common.collect", ["Lists", "Maps", "Sets", "Queues"], n) and
    n.matches("new%With%") and size = firstNumericArgument(mc) and
    api = mc.getMethod().getDeclaringType().getName() + "." + n
    or
    (callsApi(mc, "com.github.benmanes.caffeine.cache", "Caffeine", n) or
     callsApi(mc, "com.google.common.cache", "CacheBuilder", n)) and
    n = ["maximumSize", "maximumWeight", "initialCapacity"] and
    size = mc.getArgument(0) and
    api = mc.getMethod().getDeclaringType().getSourceDeclaration().getName() + "." + n
    or
    (callsApi(mc, "io.netty.buffer", "Unpooled", n) or callsApi(mc, "io.netty.buffer", "ByteBufAllocator", n)) and
    n = ["buffer", "directBuffer", "heapBuffer", "ioBuffer"] and
    size = firstNumericArgument(mc) and
    api = mc.getMethod().getDeclaringType().getSourceDeclaration().getName() + "." + n
  )
}
