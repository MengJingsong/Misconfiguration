# no_constraint — UntypedResultSet.isEmpty() — verification solution  <!-- file: cases/no_constraint-isempty-size--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | helper `UntypedResultSet.isEmpty()`, comparison `size() == 0`: [`UntypedResultSet.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L90) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Sonnet 5.5, Claude Code CLI, 2026-10-27 |
| Estimate | `negative`: no constraint. The check is an emptiness test on a result set and caps no memory or disk. |
| Ground | The comparison `size() == 0` selects a branch (empty or not) in callers. It limits nothing held in memory or on disk. |

**Type:** non-config (none)

## A. Constraint trace

**A1. The constraint.** `no constraint`. The compared operands are:
- `size()`: abstract method [`UntypedResultSet.java:98`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L98) (`public abstract int size()`). It is a runtime-queried row count of the result set. Subclass implementations: `FromResultSet.size()` returns `cqlRows.size()` (line 113-116); `FromResultList` (line 146); `FromPager` (line 188, `size()` at about line 203) and `FromDistributedPager` (line 247) count rows by iterating pages.
- the literal `0`: [`UntypedResultSet.java:90`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L90).

No yaml entry, JVM property, or constant bound takes part. The literal `0` is a zero test, not a limit.

**A2. What it caps.** Nothing. The check could only bound the rows of an internal CQL result set. It bounds none, because it does not stop, truncate or reject anything. It only answers "are there zero rows".

**A3. Mechanism.** Enclosing method: [`UntypedResultSet.isEmpty()`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java#L88-L91) (`UntypedResultSet.java:88-91`), `return size() == 0;`.
- Outcome true (0 rows): the caller takes its "no data" branch (default value, "not found", skip).
- Outcome false: the caller continues, usually with `one()` or iteration.
- Neither outcome limits, evicts, or rejects data. Nothing is held or written because of the check.
- Callers read (sample, not exhaustive): `auth/PasswordAuthenticator.java:183`, `auth/CIDRGroupsMappingManager.java:165,209`, `auth/CassandraNetworkAuthorizer.java:84`, `auth/CIDRPermissionsManager.java:95`, `auth/CassandraAuthorizer.java:229,266`, `db/SystemKeyspace.java:661,669,731,811,1018`. All use it as "found / not found" control flow on small internal system-table lookups. 22 files under `src/java` reference `UntypedResultSet`.
- Bypass or overshoot: not applicable. For `FromPager`, `size()` iterates pages and so can cost memory, but that is a property of `size()`, not a limit set by `isEmpty()`.

**A4. Other consumers.** Not applicable. No resource is governed by this check.

**A5. Evidence beyond the source.** Searched for: all definitions of `isEmpty` in the file (a single one, line 88; no overrides found in the four subclasses by grep of the file); callers in `src/java` (listed above). No config key, doc, issue or history relates to it. Source evidence only, no external links.

## B. Verification solution

**B1. Claim under test.** `UntypedResultSet.isEmpty()` does not cap memory or disk usage. It returns `size() == 0` and influences no allocation or storage limit.

### B2. Unit tier

`n/a: no constraint`. The evidence in A1 to A3 (operands, the two outcomes of the check, callers) answers the question in place of a measurement.

### B3. Cluster tier

`n/a: no constraint`. The evidence in A3 (callers use the result only for found/not-found control flow) answers the question in place of a measurement.

**B4. Risks and cleanup.** None. Nothing is run.

## C. Sources read

- /users/jason92/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/UntypedResultSet.java (lines 55-124)
- grep of callers in `src/java/org/apache/cassandra/{auth,db/SystemKeyspace.java}` (lines listed in A3)
- playbook-non-config-autonomous.md, _TEMPLATE-autonomous.md

## D. Stage-4 feedback

`none yet`
