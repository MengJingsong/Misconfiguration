import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

// source limitations
predicate simpleTypeSource(DataFlow::Node source) {
    exists(
        FieldDeclaration fd, Field f |
        fd.getFile().getBaseName() = "Config.java"
        and fd.getAField() = f
        and f.getType().getName() in ["int", "long", "double", "Integer", "Double", "Float"]
        and f.getAnAccess() = source.asExpr()
        // and f.getName() = "concurrent_reads"
    )
}

predicate refTypeSource(DataFlow::Node source) {
    exists(
        FieldDeclaration fd, Field f, Method method, MethodCall mc, FieldAccess fa |
        fd.getFile().getBaseName() = "Config.java"
        and fd.getAField() = f
        and f.getType() instanceof RefType
        and f.getType().(RefType).getAMethod() = method
        and (
            method.getName().matches("toMebibytes")
            or method.getName().matches("toKibibytes")
        )
        and not method.getName() = "toString"
        and mc.getCallee() = method
        and mc = source.asExpr()
        and mc.getQualifier() = fa
        and fa.getField() = f
        // and f.getName() = "index_summary_capacity"
    )
}

// edge limitations

// recognize pattern: self.XXX = XXX
predicate extendAssignExpr(DataFlow::Node pred, DataFlow::Node succ) {
    exists(AssignExpr ae, VarAccess lhsField |
        lhsField = ae.getDest() and
        pred.asExpr() = ae.getRhs() and
        succ.asExpr() = lhsField.getVariable().getAnAccess()
    )
}

module CassConfigSig implements DataFlow::ConfigSig {
    predicate isSource(DataFlow::Node source) {
        refTypeSource(source)
        or 
        simpleTypeSource(source)
    }
  
    predicate isBarrier(DataFlow::Node node) {
        not node.asExpr().getType().getName() in ["int", "long", "double", "Integer", "Double", "Float"]
        or node.getLocation().getFile().toString().matches("%Test%")
        or node.getLocation().getFile().toString().matches("%Exception%")
    }

    predicate isSink(DataFlow::Node sink) {
        any()
        // sink.getLocation().getFile().getBaseName() = "DirectStreamingConnectionFactory.java"
    }
  
    predicate isAdditionalFlowStep(DataFlow::Node pred, DataFlow::Node succ) {
        extendAssignExpr(pred, succ)
    }
}

module CassFlow = TaintTracking::Global<CassConfigSig>;