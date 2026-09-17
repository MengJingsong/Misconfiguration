/**
 * @name Example placeholder query
 * @description Replace with the first real if-check-exp query for Cassandra.
 * @kind problem
 * @problem.severity recommendation
 * @id cassandra/if-check-exp/example
 */

import java
import common.lib.Common

from Method m
where m.getName() = "main"
select m, "Placeholder query — replace me."
