<!-- file: cases/permissions_cache_max_entries-initcache-entrycount--autonomous.md -->
# permissions_cache_max_entries — verification solution  <!-- file: cases/permissions_cache_max_entries-initcache-entrycount--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the statement that builds the auth cache, as given, **linked**: [`AuthCache.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/AuthCache.java#L344) (the builder statement spans L344-L348; the capacity gets its value at `.maximumSize(getMaxEntries())`, [`AuthCache.java:346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/AuthCache.java#L346)) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive` — the value of `permissions_cache_max_entries` is passed to Caffeine's `maximumSize`, which evicts entries so the cache's entry count stays at or below it; the heap the cache retains is entry count × per-entry size, so it follows the knob. It caps entries, not bytes, and the cap holds only while the cache exists (validity > 0 and an authorizer that requires authorization). |
| Ground | — |

> **Scope note.** `AuthCache.initCache` is shared by every auth cache. The entry-count knob that
> reaches line 344/346 depends on the subclass: `permissions_cache_max_entries` (PermissionsCache,
> JmxPermissionsCache), `roles_cache_max_entries` (RolesCache, NetworkPermissionsCache,
> CIDRPermissionsCache), `credentials_cache_max_entries` (PasswordAuthenticator's CredentialsCache,
> MutualTlsAuthenticator's cache). This case picks **`permissions_cache_max_entries` on
> PermissionsCache**: its key set (user × resource) is the one a client can grow the most, so it is
> the one where a cap matters most. The mechanism, and so the verdict, is the same for the others.

## A. Constraint trace

**A1. The constraint.** `permissions_cache_max_entries`; configuration entry (yaml), also changeable at
runtime through JMX. Declared in
[`Config.java:91`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L91)
as `public volatile int permissions_cache_max_entries = 1000;`. Unit: number of cache entries (one
entry = one `(AuthenticatedUser, IResource)` pair). Default: the literal 1000, not derived from
anything. It does not appear in `conf/cassandra.yaml` (only documented as `<type>_cache_max_entries`
in `doc/modules/cassandra/pages/managing/operating/security.adoc:386`), but any yaml key that matches a
`Config` field is accepted, so `permissions_cache_max_entries: N` can be added to `cassandra.yaml`
(needs a restart). Read/written through `DatabaseDescriptor.getPermissionsCacheMaxEntries()` /
`setPermissionsCacheMaxEntries()` (`DatabaseDescriptor.java:1818-1826`), wired into PermissionsCache
at `PermissionsCache.java:35-36`. At runtime: JMX attribute `MaxEntries` of
`org.apache.cassandra.auth:type=PermissionsCache` (`AuthCache.setMaxEntries`, `AuthCache.java:289-296`),
or `nodetool setauthcacheconfig --cache-name PermissionsCache --max-entries N`
(`SetAuthCacheConfig.java:91-95`); no restart. The runtime path is refused if
`-Dcassandra.disable_auth_caches_remote_configuration=true` (`AuthCache.java:291-292`,
`CassandraRelevantProperties.java:191`). No validation of the value: a negative value makes
Caffeine's `maximumSize` throw `IllegalArgumentException` (builder contract), 0 makes the cache keep
nothing.

**A2. What it caps.** Heap. The quantity compared against the limit is the cache's entry count
(Caffeine's weighted size with the default weigher of 1 per entry). Each entry retains a Caffeine
node, a `Pair`, the `AuthenticatedUser` (often shared with the connection), the `IResource` (for
example a `RoleResource` holding the role-name `String`) and the `Set<Permission>` value. The
per-entry byte size is **not** bounded by the knob: it grows with the length of the resource name.

**A3. Mechanism.**
1. `AuthenticatedUser` creates the node-wide cache statically:
   `new PermissionsCache(DatabaseDescriptor.getAuthorizer())` (`AuthenticatedUser.java:42`).
   The `AuthCache` constructor calls `init()` → `initCache(null)` (`AuthCache.java:179`, `:185-188`).
2. `initCache` returns `null` (no cache at all) if the authorizer does not require authorization
   (`AuthCache.java:331-332`, `PermissionsCache.java:41`) or `permissions_validity <= 0`
   (`AuthCache.java:334-335`).
3. Otherwise the cache is built at the entry statement
   [`AuthCache.java:344`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/AuthCache.java#L344)
   with the capacity set at
   [`AuthCache.java:346`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/AuthCache.java#L346)
   `.maximumSize(getMaxEntries())`. There is no `if` in Cassandra that compares the count with the
   limit; the check that enforces it is inside Caffeine 3.1.8 (`.build/parent-pom-template.xml:1059-1061`):
   after each write, the cache's maintenance compares its weighted size with the maximum and evicts
   (W-TinyLFU) until it is back under. Cassandra's only other enforcement point is the runtime
   resize, [`AuthCache.java:357`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/AuthCache.java#L357)
   `policy.setMaximum(getMaxEntries())`, reached from `setMaxEntries` (`AuthCache.java:289-296`).
4. Entries are added on lookup: `ClientState.authorize` → `AuthenticatedUser.getPermissions` →
   `permissionsCache.getPermissions` → `AuthCache.get` → `cache.get(k)` loads on miss
   (`ClientState.java:646-648`, `AuthenticatedUser.java:126-129`, `PermissionsCache.java:44-47`,
   `AuthCache.java:223-228`). Each permission check walks the resource chain and looks up each level
   until one grants the permission (`ClientState.java:528-536`). For a superuser the load is
   `resource.applicablePermissions()` (`CassandraAuthorizer.java:79-80`), so a single lookup per
   statement suffices.
5. Outcome at the limit: the insert succeeds and some entry (possibly the new one, if TinyLFU
   rejects it) is evicted; the request is never refused. Evicted keys are re-loaded from
   `system_auth` on next use.
6. Bypasses and overshoots:
   - Caffeine's bound is eventually enforced: the size may exceed the maximum briefly while writes
     sit in the write buffer before maintenance runs (Caffeine docs, A5).
   - The bound is on count, not bytes: a key with a long resource name (e.g. a role name of
     thousands of characters, `RoleResource.java:86-89`) retains that many bytes per entry.
   - `warm()` bulk-loads with `cache.putAll` (`AuthCache.java:417-418`); this still goes through
     Caffeine's bound.
   - The knob is shared by PermissionsCache and JmxPermissionsCache (`AuthorizationProxy.java:561-562`);
     a runtime change through one MBean updates the shared `Config` value but re-sizes only that
     MBean's cache (`AuthCache.java:294-295`); the other keeps its old maximum until its own
     `initCache` runs (e.g. `invalidate()`, `AuthCache.java:234-237`).
   - With the cache disabled (`validity <= 0`, AllowAllAuthorizer) every lookup calls the loader
     (`AuthCache.java:225-226`): nothing is retained, so the knob is irrelevant.

**A4. Other consumers.** Other auth caches, each with its own `*_cache_max_entries`
(roles, credentials, network permissions, CIDR, JMX permissions; see the scope note); Caffeine's
frequency sketch (sized from the maximum / current size); transient per-request objects (query
strings, parsed statements, `ClientState`); the `system_views.permissions_cache_keys` virtual table
copies all keys into a result set when queried (`PermissionsCacheKeysTable.java:44-52`); all other
heap users of the node (memtables, key/row caches, chunk cache, schema).

**A5. Evidence beyond the source.**
- Caffeine 3.1.8 `Caffeine.maximumSize(long)` Javadoc: the cache may evict before the limit is
  exceeded or temporarily exceed it while evicting; negative values throw `IllegalArgumentException`:
  https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumSize(long)
- Cassandra security docs, auth cache settings (`<type>_cache_max_entries`):
  `doc/modules/cassandra/pages/managing/operating/security.adoc:383-388`.
- CASSANDRA-9189 (cited in `DropRoleStatement.java:46-47`: avoid caching information about roles
  that do not exist) — relevant because the cluster workload below relies on non-existent roles
  still producing a permissions-cache entry.
- Existing test `test/unit/org/apache/cassandra/auth/AuthCacheTest.java` (shows an `AuthCache`
  subclass can be driven in a plain JUnit JVM).

## B. Verification solution

**B1. Claim under test.** With `permissions_cache_max_entries = M` and the permissions cache enabled,
after N > M distinct `(user, resource)` lookups the permissions cache holds at most M entries
(transiently a little more), and the heap it retains is ≈ min(M, N) × per-entry size; raising M above N
lets the same workload retain ≈ N entries. Wrong if the retained entry count (or retained heap) with
M < N is materially above M, i.e. close to N.

### B2. Unit tier

**B2a. Environment and build.** Linux, JDK 11, Ant. Copy the tree to local disk
(`rsync -a /users/jason92/cassandra-5.0.9/ /mydata/o03/cassandra-5.0.9/`, or any local path with ≥5 GB
free) and work only in the copy. Build: `cd /mydata/o03/cassandra-5.0.9 && ant jar build-test`
(network access to Maven Central is needed for dependency resolution). Test source:
`test/unit/org/apache/cassandra/auth/PermissionsCacheMaxEntriesProbeTest.java` in the copy (same
package so it can read the protected `cache` field). The `testsome` target runs it with
`-Dcassandra.config=test/conf/cassandra.yaml` and `maxmemory=1024m` (`build.xml:1153`, `:1382-1391`).

**B2b. Knobs.** `DatabaseDescriptor.setPermissionsCacheMaxEntries(M)` before constructing the cache,
M ∈ {0, 100, 1000, 10000, 100000}: 0 = degenerate (keeps nothing), 100/1000/10000 = binding with
N = 30000, 1000 = default, 100000 = non-binding (positive control). Separately M = -1 (expect
construction failure) and a runtime shrink 10000 → 100 via `setMaxEntries` (line 357 path). Held
fixed: `permissions_validity` = 3600000 ms and `permissions_update_interval` = 3600000 ms (so no
expiry or refresh during the run), active update false.

**B2c. Workload.** One `AuthenticatedUser("probe")`, N = 30000 distinct resources
`RoleResource.role(<8-digit index> + 'x' * (L-8))`, L = 4000 characters, each looked up once via
`getPermissions`. A stub authorizer (subclass of the test `StubAuthorizer`) returns a fixed
`EnumSet.of(Permission.DROP)` and counts calls. N = 30000 > M for every binding M (3× the largest
binding value), so the limit is reached and passed. Uncapped retained heap ≈ 30000 × ~4.2 KB ≈ 126 MB,
under the 1024 MB test heap.

**B2d. Observables and instruments.** (1) Operand: `cache.cleanUp()` then `cache.estimatedSize()`
and `getAll().size()` — the entry count Caffeine compares with the maximum. (2) Loader call count
(should equal N; a second pass over the first 100 keys shows hits only when they were retained).
(3) Secondary: used heap after three `System.gc()` calls, before the fill and after it with the cache
still referenced (`ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed()`); approximate
only (GC is advisory). Cannot be observed directly: which entries were evicted, or the transient
overshoot before `cleanUp()`.

**B2e. Procedure.**
1. Create the test file in the copy:

```java
package org.apache.cassandra.auth;

import java.lang.management.ManagementFactory;
import java.util.EnumSet;
import java.util.Set;
import java.util.concurrent.atomic.AtomicLong;

import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.config.DatabaseDescriptor;

import static org.junit.Assert.assertTrue;
import static org.junit.Assert.fail;

public class PermissionsCacheMaxEntriesProbeTest
{
    static final int N = 30000, L = 4000;
    static int seq = 0;

    static class CountingAuthorizer extends StubAuthorizer
    {
        final AtomicLong loads = new AtomicLong();
        @Override public Set<Permission> authorize(AuthenticatedUser u, IResource r)
        { loads.incrementAndGet(); return EnumSet.of(Permission.DROP); }
    }

    static class ProbeCache extends PermissionsCache
    {
        ProbeCache(IAuthorizer a) { super(a); }
        @Override protected String getObjectName() { return MBEAN_NAME_BASE + "PermissionsCacheProbe" + (seq++); }
        long settledSize() { cache.cleanUp(); return cache.estimatedSize(); }
    }

    @BeforeClass
    public static void setup()
    {
        DatabaseDescriptor.daemonInitialization();
        DatabaseDescriptor.setPermissionsValidity(3_600_000);
        DatabaseDescriptor.setPermissionsUpdateInterval(3_600_000);
        DatabaseDescriptor.setPermissionsCacheActiveUpdate(false);
    }

    static long usedAfterGc()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(200); } catch (InterruptedException e) {} }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    static String name(int i)
    {
        StringBuilder sb = new StringBuilder(String.format("%08d", i));
        while (sb.length() < L) sb.append('x');
        return sb.toString();
    }

    static ProbeCache fill(int max, CountingAuthorizer a)
    {
        DatabaseDescriptor.setPermissionsCacheMaxEntries(max);
        ProbeCache c = new ProbeCache(a);
        AuthenticatedUser u = new AuthenticatedUser("probe");
        for (int i = 0; i < N; i++)
            c.getPermissions(u, RoleResource.role(name(i)));
        return c;
    }

    void runArm(int max)
    {
        CountingAuthorizer a = new CountingAuthorizer();
        long before = usedAfterGc();
        ProbeCache c = fill(max, a);
        long size = c.settledSize();
        long heapDelta = usedAfterGc() - before;
        long loadsAfterFill = a.loads.get();
        AuthenticatedUser u = new AuthenticatedUser("probe");
        for (int i = 0; i < 100; i++) c.getPermissions(u, RoleResource.role(name(i)));
        System.out.printf("PROBE max=%d n=%d estimatedSize=%d asMap=%d loads=%d reloads100=%d heapDeltaMB=%.1f%n",
                          max, N, size, c.getAll().size(), loadsAfterFill, a.loads.get() - loadsAfterFill,
                          heapDelta / 1048576.0);
        assertTrue("size " + size + " > max " + max, size <= Math.max(max, 0));
        c.shutdownNow();
    }

    @Test public void m0()      { runArm(0); }
    @Test public void m100()    { runArm(100); }
    @Test public void m1000()   { runArm(1000); }
    @Test public void m10000()  { runArm(10000); }
    @Test public void m100000() { runArm(100000); }

    @Test
    public void negative()
    {
        DatabaseDescriptor.setPermissionsCacheMaxEntries(-1);
        try { new ProbeCache(new CountingAuthorizer()); fail("expected IllegalArgumentException"); }
        catch (IllegalArgumentException e) { System.out.println("PROBE max=-1 -> " + e); }
    }

    @Test
    public void shrinkAtRuntime()
    {
        CountingAuthorizer a = new CountingAuthorizer();
        ProbeCache c = fill(10000, a);
        long before = c.settledSize();
        c.setMaxEntries(100);                       // AuthCache.java:289-296 -> :357
        long after = c.settledSize();
        System.out.printf("PROBE shrink 10000->100 before=%d after=%d%n", before, after);
        assertTrue(after <= 100);
        c.shutdownNow();
    }
}
```

2. Run each arm in its own JVM so heap readings do not mix:
   `for m in m0 m100 m1000 m10000 m100000 negative shrinkAtRuntime; do ant testsome -Dtest.name=org.apache.cassandra.auth.PermissionsCacheMaxEntriesProbeTest -Dtest.methods=$m; done`
3. Collect: `grep -h PROBE build/test/output/TEST-org.apache.cassandra.auth.PermissionsCacheMaxEntriesProbeTest-*.xml`.

**B2f. Predictions.** (N = 30000, L = 4000)

| M | estimatedSize after cleanUp | loads | reloads of first 100 | heap delta |
|---|---|---|---|---|
| 0 | 0 | 30000 | 100 | ≈ 0 MB (< 2 MB) |
| 100 | ≤ 100 (expected exactly 100) | 30000 | ≈ 100 | ≈ 0.4 MB |
| 1000 | ≤ 1000 (expected 1000) | 30000 | ≈ 100 (most early keys evicted) | ≈ 4 MB |
| 10000 | ≤ 10000 (expected 10000) | 30000 | ≈ 100 | ≈ 42 MB |
| 100000 | 30000 | 30000 | 0 | ≈ 126 MB |
| -1 | construction throws `IllegalArgumentException` | — | — | — |
| shrink 10000→100 | before 10000, after ≤ 100 | — | — | — |

Relation: size = min(M, N); heap delta ∝ size (≈ 4.2 KB per entry, within a factor 1.5).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| size = min(M, N) for all M, heap delta scales with it, M=100000 arm holds 30000 | claim confirmed at unit level |
| size for M < N materially above M (e.g. ≥ 2M or ≈ N) after `cleanUp()` | claim wrong: the bound does not hold |
| M=100000 arm also small (≪ 30000) | workload or cache broken (e.g. cache null: validity not applied); not a test of the claim |
| loads < N in a binding arm | keys not distinct or loader not reached; fix workload |
| size bounded but heap delta ≈ the uncapped arm | count is capped but memory is retained elsewhere; claim (memory part) wrong |
| shrink arm stays at 10000 | runtime path (line 357) does not enforce; partial refutation |

**B2h. Controls.** M=100000 positive control (same workload, cap not binding, operand moves to N);
M=0 floor; the loader count shows the workload really reached the cache; long validity rules out
time-based expiry as the cause of a small size; one arm per JVM avoids heap carry-over; the probe
cache has its own MBean name so the node-wide static PermissionsCache (disabled under the test
config's AllowAllAuthorizer) does not interfere.

### B3. Cluster tier

**B3a. Environment and build.** One Linux node, JDK 11, Ant, Python 3 (3.8–3.11). Use the same local
copy built with `ant jar`. Edit `conf/cassandra.yaml` in the copy:

```
authenticator: PasswordAuthenticator
authorizer: CassandraAuthorizer
permissions_validity: 3600000ms
permissions_update_interval: 3600000ms
permissions_cache_max_entries: <M>          # appended line, varied per arm
data_file_directories: [/mydata/o03/run/data]
commitlog_directory: /mydata/o03/run/commitlog
saved_caches_directory: /mydata/o03/run/saved_caches
hints_directory: /mydata/o03/run/hints
cdc_raw_directory: /mydata/o03/run/cdc_raw
listen_address: 127.0.0.1
rpc_address: 127.0.0.1
seed_provider: (keep default, seeds "127.0.0.1:7000")
```

JVM: `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=200M` (G1 from `conf/jvm11-server.options`). Logs:
`export CASSANDRA_LOG_DIR=/mydata/o03/run/logs`.

**B3b. Knobs.** `permissions_cache_max_entries` M ∈ {1000 (default), 5000, 100000 (non-binding,
positive control)}, set in yaml with a fresh start per arm (avoids the shared-knob issue of A3.6).
Plus control arm "cache off": `permissions_validity: 0ms` with M = 100000. Plus dynamic arm: in the
M=100000 run, after measuring, `bin/nodetool setauthcacheconfig --cache-name PermissionsCache --max-entries 1000`.

**B3c. Workload.** As the default superuser `cassandra`, send N = 20000 statements
`DROP ROLE IF EXISTS '<8-digit i><'x' × 3992>'` (role name length L = 4000) for distinct non-existent
roles. Each statement is authorized before validation (`QueryProcessor.java:271`):
`DropRoleStatement.authorize` → `checkPermission(DROP, role)` (`DropRoleStatement.java:42-44`,
`AuthenticationStatement.java:55-59`) → one permissions-cache lookup for `roles/<name>` that a
superuser always satisfies at the first level, so one new entry each; `execute` then does nothing
because the role does not exist (`DropRoleStatement.java:70`; `isExistingRole` reads the table directly,
`CassandraRoleManager.java:423-426`, so the roles cache does not grow). Arithmetic: uncapped
20000 × ~4.2 KB ≈ 84 MB retained; M = 1000 → ≈ 4 MB; M = 5000 → ≈ 21 MB. Duration ≈ 1–5 min per arm.

Driver (save outside the source tree, e.g. `/mydata/o03/drop_roles.py`):

```python
import sys, glob, os
home, n, L = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
z = glob.glob(os.path.join(home, 'lib', 'cassandra-driver-internal-only-*.zip'))[0]
ver = os.path.basename(z)[len('cassandra-driver-internal-only-'):-4]
sys.path.insert(0, os.path.join(z, 'cassandra-driver-' + ver))
from cassandra.cluster import Cluster
from cassandra.auth import PlainTextAuthProvider
c = Cluster(['127.0.0.1'], auth_provider=PlainTextAuthProvider('cassandra', 'cassandra'))
s = c.connect()
pad = 'x' * (L - 8)
for i in range(n):
    s.execute("DROP ROLE IF EXISTS '%08d%s'" % (i, pad))
c.shutdown()
print('sent', n)
```

(If the bundled driver fails to import, use `python3 -m venv /mydata/o03/venv && /mydata/o03/venv/bin/pip install cassandra-driver==3.29.0` and drop the three `sys.path` lines.)

**B3d. Observables and instruments.**
(1) Entry count: `bin/nodetool sjk mx -b org.apache.cassandra.auth:type=PermissionsCache -f EstimatedSize -mg`
(AuthCacheMBean `getEstimatedSize`, `AuthCache.java:317-320`), read 10 s after the workload ends.
(2) Retained objects: `jcmd $PID GC.class_histogram` (forces a full GC; live objects only); record
instances of `org.apache.cassandra.auth.RoleResource` and total bytes of `[B`.
(3) Heap used after GC: `jcmd $PID GC.run; jcmd $PID GC.heap_info`.
Take (2)/(3) at baseline (after login works, before the workload) and after the workload.
(4) Cross-check only after (2)/(3): `bin/cqlsh -u cassandra -p cassandra -e "SELECT count(*) FROM system_views.permissions_cache_keys"` (materializes all keys temporarily, so never before a heap reading).
Cannot be observed directly: the bytes of one cache entry (inferred from deltas) and transient
overshoot during the run.

**B3e. Procedure.** For each arm (1000, 5000, 100000, cache-off):
1. `rm -rf /mydata/o03/run && mkdir -p /mydata/o03/run/logs`; set yaml per B3a/B3b.
2. `cd /mydata/o03/cassandra-5.0.9 && bin/cassandra -p /mydata/o03/run/pid > /mydata/o03/run/logs/stdout.txt 2>&1`; `PID=$(cat /mydata/o03/run/pid)`.
3. Wait until `bin/cqlsh -u cassandra -p cassandra -e "LIST ROLES"` succeeds (default superuser is created a few seconds after startup); check `system.log` for `(Re)initializing PermissionsCache (... /<M>/false)` (`AuthCache.java:338-339`).
4. Baseline: `jcmd $PID GC.class_histogram > base.hist; jcmd $PID GC.run; jcmd $PID GC.heap_info > base.heap`.
5. `python3 /mydata/o03/drop_roles.py /mydata/o03/cassandra-5.0.9 20000 4000`.
6. `sleep 10`; read EstimatedSize; `jcmd $PID GC.class_histogram > after.hist; jcmd $PID GC.run; jcmd $PID GC.heap_info > after.heap`; then the virtual-table count.
7. Dynamic arm (only in the 100000 run): `bin/nodetool setauthcacheconfig --cache-name PermissionsCache --max-entries 1000`, `sleep 10`, repeat step 6 readings into `shrink.*`.
8. `bin/nodetool stopdaemon` (or `kill $PID`), wait, `pgrep -f CassandraDaemon` must print nothing; keep the readings, `rm -rf /mydata/o03/run`.

**B3f. Predictions.** (N = 20000, L = 4000; Δ = after − baseline)

| Arm | EstimatedSize | Δ RoleResource instances | Δ `[B` bytes / Δ heap after GC |
|---|---|---|---|
| M = 1000 | ≤ 1000 (≈ 1000) | ≈ 1000 | ≈ 4 MB (≤ 8 MB) |
| M = 5000 | ≤ 5000 (≈ 5000) | ≈ 5000 | ≈ 21 MB |
| M = 100000 | 20000 | ≈ 20000 | ≈ 84 MB |
| M = 100000 then shrink to 1000 | ≤ 1000 | back to ≈ 1000 | back to ≈ 4 MB |
| cache off (validity 0) | 0 | ≈ 0 | ≈ 0 |

Relation: Δ(5000)/Δ(1000) ≈ 5, Δ(100000)/Δ(1000) ≈ 20, within ±30 % (heap-after-GC noise of a few MB
is expected; the RoleResource count is the sharp reading).

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| EstimatedSize and Δ RoleResource ≈ min(M, 20000); Δ bytes scales the same | claim confirmed: heap follows the knob |
| M = 1000 arm retains ≈ 20000 RoleResource / ≈ 84 MB | claim wrong: the cap does not govern retained heap |
| EstimatedSize ≤ M but Δ RoleResource or Δ bytes ≈ the uncapped arm | count capped but memory held elsewhere (claim's memory part wrong; look for another retainer) |
| M = 100000 arm does not grow (≈ baseline) | positive control failed (cache disabled, wrong authorizer, or statements rejected): no conclusion |
| shrink leaves ≈ 20000 entries | runtime path (line 357) not enforcing |
| cache-off arm grows | retention not from the permissions cache; workload confounded |

**B3h. Controls.** M = 100000 is the positive control (same workload, cap not binding, heap moves);
cache-off arm shows the retention is the cache's; baseline histogram per run removes unrelated heap;
long validity/update interval removes expiry; non-existent roles keep the roles cache and
`system_auth` unchanged; histogram forces a full GC so only live objects count; one fresh node per
arm avoids carry-over.

**B4. Risks and cleanup.** Unit tier: builds only in the local copy; test heap 1 GB; build output in
the copy (`build/`), delete the copy afterwards if space is needed (~2–3 GB). Cluster tier: data,
commit log, hints, saved caches and logs all under `/mydata/o03/run` (a few hundred MB at most); the
DROP statements write nothing to `system_auth`; 1 GB heap. Stop the node with `nodetool stopdaemon`
/ `kill`, confirm `pgrep -f CassandraDaemon` and `pgrep -f drop_roles.py` are empty, then
`rm -rf /mydata/o03/run`. Nothing is written to shared storage or the shared source tree.

## C. Sources read

/users/jason92/writeup-ext/playbook-autonomous.md
/users/jason92/writeup-ext/_TEMPLATE-autonomous.md
src/java/org/apache/cassandra/auth/AuthCache.java
src/java/org/apache/cassandra/auth/PermissionsCache.java
src/java/org/apache/cassandra/auth/AuthenticatedUser.java
src/java/org/apache/cassandra/auth/CassandraAuthorizer.java
src/java/org/apache/cassandra/auth/CassandraRoleManager.java
src/java/org/apache/cassandra/auth/RoleResource.java
src/java/org/apache/cassandra/auth/AuthCacheService.java
src/java/org/apache/cassandra/auth/NetworkPermissionsCache.java
src/java/org/apache/cassandra/auth/CIDRPermissionsCache.java
src/java/org/apache/cassandra/auth/RolesCache.java
src/java/org/apache/cassandra/auth/PasswordAuthenticator.java
src/java/org/apache/cassandra/auth/MutualTlsAuthenticator.java
src/java/org/apache/cassandra/auth/jmx/AuthorizationProxy.java
src/java/org/apache/cassandra/config/Config.java
src/java/org/apache/cassandra/config/DatabaseDescriptor.java
src/java/org/apache/cassandra/config/CassandraRelevantProperties.java
src/java/org/apache/cassandra/service/ClientState.java
src/java/org/apache/cassandra/service/StorageService.java
src/java/org/apache/cassandra/cql3/QueryProcessor.java
src/java/org/apache/cassandra/cql3/statements/DropRoleStatement.java
src/java/org/apache/cassandra/cql3/statements/AuthenticationStatement.java
src/java/org/apache/cassandra/cql3/statements/AlterRoleStatement.java
src/java/org/apache/cassandra/db/virtual/PermissionsCacheKeysTable.java
src/java/org/apache/cassandra/tools/nodetool/SetAuthCacheConfig.java
src/java/org/apache/cassandra/tools/nodetool/GetAuthCacheConfig.java
src/java/org/apache/cassandra/utils/MBeanWrapper.java
src/antlr/Parser.g
conf/cassandra.yaml
conf/jvm-server.options, conf/jvm11-server.options, conf/cassandra-env.sh
bin/cqlsh.py
build.xml
.build/parent-pom-template.xml
doc/modules/cassandra/pages/managing/operating/security.adoc
test/unit/org/apache/cassandra/auth/AuthCacheTest.java
test/unit/org/apache/cassandra/auth/StubAuthorizer.java
https://www.javadoc.io/doc/com.github.ben-manes.caffeine/caffeine/3.1.8/com.github.benmanes.caffeine.cache/com/github/benmanes/caffeine/cache/Caffeine.html#maximumSize(long) (cited from the library's documented contract, not fetched in this session)

## D. Stage-4 feedback

### D1. Stage-4 audit amendments (2026-11-12, before any reading)

Applied by the stage-4 design audit (results file
`../../stage4-runtime-verification/results/permissions_cache_max_entries-initcache-entrycount--autonomous.md`, section 1).
They are recorded here, not in B, so B's text stays as filed; where an amendment and B differ, the amendment is the frozen version.
None depends on a reading.

- **AM1 (B2a, B3a, B3c, B3e, B4: paths and build).** The working tree is a `copy-source.sh` copy of this repository's
  `systems/cassandra/source/` (not `/users/jason92/cassandra-5.0.9`), at `/mydata/jingsong-cass-s4/o03/src` on the run node,
  built with `ant build-test` (which includes `jar`). Every `/mydata/o03/...` path in B reads `/mydata/jingsong-cass-s4/o03/...`
  (`/mydata/o03/cassandra-5.0.9` reads `/mydata/jingsong-cass-s4/o03/src`).
- **AM2 (B3a, B3e: ports on a shared node).** The node is shared, so the cluster tier uses `storage_port: 7300`,
  `ssl_storage_port: 7301`, `native_transport_port: 9342`, JMX port 7499 (`JMX_PORT` in the copy's `conf/cassandra-env.sh`),
  seeds `"127.0.0.1:7300"`; `nodetool` takes `-p 7499`, `cqlsh` takes `127.0.0.1 9342`, the driver `port=9342`. B3e.8 and B4's
  `pgrep -f CassandraDaemon` is replaced by checking this run's own PID and `ps -eo cmd | grep '[C]assandraDaemon'` filtered on
  this run's directory (other projects' daemons on the node are not this run's). B3e.3 also waits for
  `nodetool -p 7499 statusbinary` to print `running` (environment.md section 6).
- **AM3 (B2f, column "reloads of first 100").** For the binding arms (M = 100, 1000, 10000) this column is informational, range 0-100,
  not a checked prediction: which keys Caffeine keeps after a one-pass scan of distinct keys depends on its W-TinyLFU admission
  (a candidate whose sketch frequency does not exceed the victim's is normally rejected, so early keys may stay). For M = 0
  (100 reloads) and M = 100000 (0 reloads) it stays a prediction. No B2g row uses it.
- **AM4 (B2g: thresholds).** N = 30000, size = `estimatedSize` after `cleanUp()`.
  Row 1 ("confirmed") holds when, for every M in {0, 100, 1000, 10000}, 0.95 x min(M, N) <= size <= M; the M = 100000 arm holds
  >= 27000 (expected 30000); loads = 30000 in every arm; and the heap delta "scales with it": per-entry bytes = heap delta / size
  is between 2.8 and 6.3 KB (4.2 KB within a factor 1.5) for M = 1000, 10000 and 100000, and the heap delta is < 2 MB for M = 0 and
  M = 100 (the noise floor of the `System.gc()` reading).
  Row 2 ("bound does not hold"): size > 1.1 x M after `cleanUp()` in any binding arm. A size in (M, 1.1 x M], or below
  0.95 x min(M, N), matches no row: "Not confirmed (no matching row)".
  Row 3 ("workload or cache broken"): the M = 100000 arm holds < 27000.
  Row 4: loads < 30000 in any arm.
  Row 5 ("count capped, memory elsewhere"): the heap delta of a binding arm (M <= 10000) is >= 0.5 x the M = 100000 arm's.
  Row 6 ("shrink arm stays"): shrink arm `after` > 100.
  The M = -1 arm is informational (A1's builder contract); no B2g row depends on it.
- **AM5 (B3d, B3f, B3g: readings and thresholds).** Live-heap readings use the `GC.class_histogram` output (it forces a full GC
  and lists live objects): the `RoleResource` instance count, the `[B` bytes and the histogram `Total` bytes; `GC.heap_info`
  after `GC.run` is recorded as a secondary reading (environment lesson: live heap is the histogram total, not `heap_info`).
  Δ = after - baseline of the same arm. "≈ min(M, 20000)" for EstimatedSize and Δ RoleResource means within ±10 % (the
  baseline holds a few login entries).
  Row 1 ("confirmed") holds when: EstimatedSize <= M + 10 for M = 1000 and 5000 and every arm's EstimatedSize and Δ RoleResource
  are within ±10 % of min(M, 20000); the ratios Δ RoleResource(5000)/Δ RoleResource(1000) are in 3.5-6.5 and
  Δ RoleResource(100000)/Δ RoleResource(1000) in 14-26 (B3f's ±30 %); and Δ `[B` bytes "scales the same": Δ `[B` / Δ RoleResource
  is 2.8-6.3 KB for the 5000 and 100000 arms and Δ `[B` <= 8 MB for the 1000 arm.
  Row 2 ("cap does not govern retained heap"): the M = 1000 arm's Δ RoleResource >= 10000.
  Row 3 ("count capped, memory elsewhere"): EstimatedSize <= M + 10 but Δ RoleResource or Δ `[B` of the 1000 or 5000 arm
  >= 0.5 x the 100000 arm's.
  Row 4 ("positive control failed"): the 100000 arm's Δ RoleResource < 2000.
  Row 5 ("shrink not enforcing"): EstimatedSize after the shrink > 1100.
  Row 6 ("cache-off arm grows"): the cache-off arm's Δ RoleResource > 500 or Δ `[B` > 8 MB.
  A reading that meets no row is "Not confirmed (no matching row)".

### D2. Stage-4 feedback

2026-11-12, run 1 on apt138 (results: `../../stage4-runtime-verification/results/permissions_cache_max_entries-initcache-entrycount--autonomous.md`).
**Unit: Confirmed — caps** (B2g row 1: settled size = min(M, 30000) exactly for M = 0, 100, 1000, 10000, 100000; 3.8-4.1 KB
per entry; runtime shrink 10000 -> 100). **Cluster: Confirmed — caps** (B3g row 1: EstimatedSize 1000 / 5000 / 20014 and live
`RoleResource` +1001 / +5001 / +20001 for M = 1000 / 5000 / 100000, live `[B` +3.9 / +19.2 / +76.7 MB; runtime shrink to 1000
back to 1000 entries; cache off retains nothing). **Outcome class: true positive.** Nothing in A or B is refuted. Runbook
defect D1 (B2e.3 output location) fixed by AM6 (D3). The cap is on entries; per-entry bytes follow the resource-name length (A2).

### D3. Runbook-defect fixes (2026-11-12)

- **AM6 (B2e.3, runbook defect D1, found by the unit shakedown before run 1).** In the test JVM, `System.out` is wrapped by the
  test logback configuration (`test/conf/logback-test.xml`) and written to `build/test/logs/<jdk>/TEST-<class>.log`, one log line
  per `write()` with the newlines dropped; nothing reaches the junit XML, so B2e.3's `grep` finds no `PROBE` line. Fix: collect from
  that log and rejoin the fragments of each `PROBE` record (harness `collect-probe.py`). The test class, the arms, B2f and B2g are
  unchanged.
