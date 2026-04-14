import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking

import HadoopHDFSConfigs


from StringLiteral lit
where validHadoopHDFSConfigs(lit.getValue())
select lit, lit.getValue(), lit.getLocation().getFile().getBaseName()
