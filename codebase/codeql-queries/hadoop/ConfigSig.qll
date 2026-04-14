import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
import HadoopHDFSConfigs
import HadoopYARNConfigs
import HadoopMapRedConfigs


// edge limitations
// recognize pattern: self.XXX = XXX
predicate extendAssignExpr(DataFlow::Node pred, DataFlow::Node succ) {
    exists(AssignExpr ae, VarAccess lhsField |
        lhsField = ae.getDest() and
        pred.asExpr() = ae.getRhs() and
        succ.asExpr() = lhsField.getVariable().getAnAccess()
    )
}

// recognize pattern: XXX=XXX.getInt(XXX)
predicate extendGetter(DataFlow::Node pred, DataFlow::Node succ) {
    exists(
            MethodCall methodCall |
            (
                // methodCall.getMethod().getName() = "getInt" or
                // methodCall.getMethod().getName() = "getLong" or
                methodCall.getMethod().getName() = "getLongBytes"
                // methodCall.getMethod().getName() = "getDouble" or
                // methodCall.getMethod().getName() = "getFloat"
            ) and
            // methodCall.getAnArgument*().getAChildExpr() = pred.asExpr() and
            methodCall.getAnArgument() = pred.asExpr() and
            methodCall = succ.asExpr()
        )
}

module HadoopConfigSig implements DataFlow::ConfigSig {
    predicate isSource(DataFlow::Node source) {
        // source.getLocation().getFile().getBaseName() = "HdfsClientConfigKeys.java"and
        exists (StringLiteral lit |
            // validHadoopHDFSConfigs(lit.getValue()) and
            // validHadoopYARNConfigs(lit.getValue()) and
            // validHadoopMapRedConfigs(lit.getValue()) and
            lit.getValue() = "dfs.blocksize" and
            source.asExpr() = lit  
        )
    }
  
    predicate isBarrier(DataFlow::Node node) {
        // not (
        //     node.asExpr().getType().getName() = "int"
        //     or node.asExpr().getType().getName() = "long"
        //     or node.asExpr().getType().getName() = "double"
        //     or node.asExpr().getType().getName() = "Integer"
        //     or node.asExpr().getType().getName() = "Double"
        //     or node.asExpr().getType().getName() = "Float"
        // ) or 
        node.getLocation().getFile().toString().matches("%Test%")
        or node.getLocation().getFile().toString().matches("%Exception%")
    }

    predicate isSink(DataFlow::Node sink) {
        // any()
        // sink.asExpr().getType().getName() in ["int", "long", "double", "Integer", "Double", "Float"]
        sink.asExpr().getType().getName() = "String"
    }
  
    predicate isAdditionalFlowStep(DataFlow::Node pred, DataFlow::Node succ) {
        extendAssignExpr(pred, succ)
        // extendGetter(pred, succ)
    }
}

// module HadoopFlow = TaintTracking::Global<HadoopConfigSig>;
module HadoopFlow = DataFlow::Global<HadoopConfigSig>;