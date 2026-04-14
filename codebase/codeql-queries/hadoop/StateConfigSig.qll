import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
import HadoopHDFSConfigs
import HadoopYARNConfigs
import HadoopMapRedConfigs
import Utils

class HadoopConfigLiteral extends StringLiteral {
    HadoopConfigLiteral() {
        validHadoopHDFSConfigs(this.getValue()) or
        validHadoopYARNConfigs(this.getValue()) or
        validHadoopMapRedConfigs(this.getValue())
    }
}


module HadoopStateConfigSig implements DataFlow::StateConfigSig {

    class FlowState extends string {
        FlowState() {
            this = ["string", "number"]
        }
    }

    predicate isSource(DataFlow::Node source, FlowState state) {
        state = "string" and
        exists (HadoopConfigLiteral lit |
            source.asExpr() = lit  
        )
    }

    predicate isSink(DataFlow::Node sink, FlowState state) {
        state = "number" and
        sink.asExpr().getType().getName() in ["long", "int"] and
        sink.asExpr().getType() instanceof PrimitiveType
        and not isForbiddenFile(sink.getLocation().getFile())
    }

    predicate isAdditionalFlowStep(DataFlow::Node node1, FlowState state1, DataFlow::Node node2, FlowState state2) {
        state1 = "string"
        and state2 = "number"
        and exists (
            MethodCall methodCall |
            methodCall.getMethod().getName() in ["getInt", "getLong", "getLongBytes"] and
            methodCall.getAnArgument() = node1.asExpr() and
            methodCall = node2.asExpr()
        )
    }

    predicate isBarrier(DataFlow::Node node) {
        node.asParameter().getCallable().getName() in ["getInt", "getLong", "getLongBytes"]
    }
}

module HadoopStateFlow = TaintTracking::GlobalWithState<HadoopStateConfigSig>;