import java
import semmle.code.java.dataflow.DataFlow
import semmle.code.java.dataflow.TaintTracking
import external.ExternalArtifact

import Utils
import ConfigSig

from
    string str
where
    str = "abcdtestxyz"
    and str.regexpMatch(".*([Tt]est|[Ee]xample|[Ee]xception).*")
select str