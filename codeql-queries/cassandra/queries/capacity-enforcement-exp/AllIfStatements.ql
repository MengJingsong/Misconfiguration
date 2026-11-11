/**
 * @name All if statements
 * @description Pure inventory of every `if` statement in Cassandra's main source tree — the
 *   unfiltered starting point of the `capacity-enforcement-exp` pipeline. No filtering beyond the source
 *   tree itself; see ../../../../experiments/capacity-enforcement-exp/README.md for the rules that later
 *   stages narrow toward.
 * @kind table
 * @id cassandra/capacity-enforcement-exp/all-if-statements
 */

import java
import ifcheck.IfCheck

from IfStmt ifStmt, Callable enclosing, File f
where
  f = ifStmt.getFile() and
  inMainSource(f) and
  enclosing = ifStmt.getEnclosingCallable()
select
  f.getRelativePath() as path,
  ifStmt.getLocation().getStartLine() as line,
  pkgDir(f) as pkg,
  enclosing.getDeclaringType().getQualifiedName() as declaringType,
  enclosing.getName() as method,
  ifStmt as stmt
order by pkg, path, line
