/**
 * Shared predicates/classes usable by both the cassandra and hadoop query packs.
 */

import java

predicate isPlaceholder(string s) { s = "placeholder" }
