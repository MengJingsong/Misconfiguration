/**
 * @name All if statements
 * @description Inventory of every `if` statement in Cassandra's main source tree
 *   (`src/java/...`), as the starting point for the if-check-exp survey — see
 *   ../../../cassandra/if-check-exp/README.md for the filter rules applied
 *   manually to shortlist candidates from this list.
 * @kind table
 * @id cassandra/if-check-exp/all-if-statements
 */

import java

from IfStmt ifStmt, Callable enclosing, File f
where
  f = ifStmt.getFile() and
  f.getRelativePath().matches("src/java/%") and
  enclosing = ifStmt.getEnclosingCallable()
select ifStmt, f.getRelativePath(), ifStmt.getLocation().getStartLine(),
  enclosing.getDeclaringType().getQualifiedName(), enclosing.getName()
