/**
 * @name Capacity-set places
 * @description Stage-1 extension of 2026-11-11 (experiments/capacity-enforcement-exp/README.md
 *   §3.7): places where a capacity gets its value. Two forms:
 *   `field/<kind>`: an initializer or plain assignment of a field that is read in a
 *   magnitude candidate comparison or a clamp (directly or through a one-line getter),
 *   found structurally from the enforcement side; `create/<api>`: a container created
 *   with a size (array, sized library constructor, buffer allocation, sized factory,
 *   cache-builder limit). Initial-size hints are included (ruling 2026-11-11).
 *   `sizeSource` says where the value comes from (literal, constant, field, parameter,
 *   call, ...): a size taken from the data (a parameter or a call) is kept and flagged
 *   this way, not filtered out. Stage 2 ranks the rows.
 * @kind table
 * @id cassandra/capacity-enforcement-exp/capacity-set-places
 */

import java
import ifcheck.IfCheck
import common.lib.CapacityEnforcementCore

predicate row(Expr site, string pattern, string detail, string target, string value, string source) {
  exists(Field f, string kind, Expr v |
    comparedField(f, _) and
    fieldValueSet(f, site, v, kind) and
    pattern = "field/" + kind and
    detail = count(Expr u | comparedField(f, u)) + " comparison(s)" and
    target = f.getDeclaringType().getName() + "." + f.getName() and
    value = exprText(v) and
    source = concat(string k | k = sizeSourceKind(v) | k, "+")
  )
  or
  exists(Expr size, string api |
    containerCreation(site, size, api) and
    pattern = "create" and
    detail = api and
    target = "" and
    value = exprText(size) and
    source = concat(string k | k = sizeSourceKind(size) | k, "+")
  )
}

from Expr site, string pattern, string detail, string target, string value, string source, File f, Callable enclosing
where
  row(site, pattern, detail, target, value, source) and
  f = site.getFile() and
  inMainSource(f) and
  enclosing = site.getEnclosingCallable()
select f.getRelativePath() as path, site.getLocation().getStartLine() as line, pkgDir(f) as pkg,
  enclosing.getDeclaringType().getQualifiedName() as declaringType, enclosing.getName() as method,
  "capacity-set" as place, pattern, detail, target, value, source as sizeSource
