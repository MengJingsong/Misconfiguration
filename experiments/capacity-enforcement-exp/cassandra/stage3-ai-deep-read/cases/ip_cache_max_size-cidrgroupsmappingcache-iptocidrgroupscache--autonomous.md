# ip_cache_max_size — verification solution  <!-- file: cases/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | [`CIDRGroupsMappingCache.java:59`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/CIDRGroupsMappingCache.java#L59) (not an if statement: the line where the IP-to-CIDR-groups Caffeine cache is built, and where its capacity is set at L60 by `.maximumSize(DatabaseDescriptor.getIpCacheMaxSize())`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | Claude Code autonomous subagent, 2026-11-11 |
| Estimate | `positive`. `ip_cache_max_size` sets Caffeine's `maximumSize` on `ipToCidrGroupsCache`, and Caffeine's eviction loop keeps the entry count at or below it. Each entry holds a key `InetAddress` plus cache and map nodes (~130 B). The value `Set<String>` is shared with the interval tree, so retained heap should be about 130 B × min(distinct client IPs, cap). The cap is small by default (100 entries, ~13 KB), but heap follows it. |
| Ground | — |

> **Link rule.** Links are permalinks at the pinned tag. Lines in Caffeine (a library that
> Cassandra pulls in at version 3.1.8, `.build/parent-pom-template.xml:1059-1061`) link to the
> Caffeine repository at tag `v3.1.8`.

## A. Constraint trace

**A1. The constraint.**
- **Name:** `ip_cache_max_size`. It is a parameter of the `cidr_authorizer` configuration entry, not a top-level yaml key.
- **Kind:** a configuration entry. `cidr_authorizer` is a `ParameterizedClass` (`Config.java:87`). Its `parameters` map is a `Map<String,String>`, and the key is looked up there.
- **First declared / read:** in [`DatabaseDescriptor.java:1759-1771`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1759-L1771) (`getIpCacheMaxSize()`):
  - the default is a local literal `100` ([L1761](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1761));
  - the key is read at [L1766](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/DatabaseDescriptor.java#L1766);
  - the value is parsed with `Integer.parseInt` at L1770.
  - It is documented, commented out, at [`conf/cassandra.yaml:281-282`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/conf/cassandra.yaml#L281-L282): "Maximum number of entries an IP to CIDR groups cache can accommodate".
- **Unit:** cache entries, one per distinct client IP address. Bytes are not counted.
- **Default:** 100. It is used when `cidr_authorizer` or its `parameters` is null, or when the key is absent or empty (L1763-1768).
- **How to set it:** only in `cassandra.yaml`, under `cidr_authorizer: parameters:` (with `class_name: CassandraCIDRAuthorizer`). There is no `-D` property, JMX setter or nodetool command.
- **When it is read:** once, when `CassandraCIDRAuthorizer.setup()` builds the cache (`CassandraCIDRAuthorizer.java:68`). Setup runs at node start (`StorageService.java:1455`), so a change needs a restart.
- **Validation:** none in Cassandra. A negative value makes Caffeine throw `IllegalArgumentException("maximum size must not be negative")` ([Caffeine.java:400](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/Caffeine.java#L400)), so setup fails. A value of `0` means no entry is kept. A non-integer value throws `NumberFormatException`.
- **Effect:** none unless `cidr_authorizer.class_name` is `CassandraCIDRAuthorizer`. The default `AllowAllCIDRAuthorizer` (`cassandra.yaml:262`) has no cache.

**A2. What it caps.**
- **Resource:** JVM heap.
- **What is capped:** the number of entries in `ipToCidrGroupsCache`, a `LoadingCache<InetAddress, Set<String>>` (`CIDRGroupsMappingCache.java:45`). Caffeine compares its `weightedSize()` against `maximum()`. With no weigher each entry weighs 1, so the compared quantity is the entry count.
- **Retained heap per entry** (JDK 11, compressed oops):
  - the key `Inet4Address`: 16 B, plus its `InetAddressHolder`, 32 B;
  - a Caffeine node: about 32-40 B;
  - a `ConcurrentHashMap$Node`: 32 B;
  - a hash-table slot: about 4-8 B amortised.
  - **Total:** about 120-135 B per entry.
- **What is not per entry:** the value `Set<String>` is not copied. It is the same `HashSet` object the interval tree holds for the matching CIDR (`CIDRGroupsMappingIntervalTree.java:320`, `return current.values`), or the shared `Collections.emptySet()` when the `cidr_groups` table is empty (L113).
- **Frequency sketch:** Caffeine also allocates a `long[ceilPow2(max)]` (8 B × ceilPow2(max)) once the cache reaches half of the maximum ([BoundedLocalCache.java:1886-1893](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java#L1886-L1893); [FrequencySketch.java:95](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/FrequencySketch.java#L95)).

**A3. Mechanism.**
1. **Cache built:** [`CIDRGroupsMappingCache.java:59-62`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/auth/CIDRGroupsMappingCache.java#L59-L62) builds the cache with `maximumSize(getIpCacheMaxSize())`, `executor(ImmediateExecutor.INSTANCE)` and the loader `lookupCidrGroupsCacheForIp` (L112-123).
2. **Lookups that populate it:** `lookupCidrGroupsForIp` → `ipToCidrGroupsCache.get(ip)` (L133). It is reached three ways:
   - **Client requests:** every permission check on a client request, `ClientState.validateLogin()` → `user.hasAccessFromIp(remoteAddress)` (`ClientState.java:577`, `AuthenticatedUser.java:156`) → `CassandraCIDRAuthorizer.hasCidrAccess` → `lookupCidrGroupsForIp` (`CassandraCIDRAuthorizer.java:128`).
     - In MONITOR mode (the default mode), every authenticated user reaches the lookup, superusers included. The early return at L125 applies only in ENFORCE mode, and there only for roles without CIDR restrictions.
     - `validateLogin` runs before the "readable system tables" shortcut (`ClientState.java:458-464`). So even `SELECT ... FROM system.local` triggers a lookup.
   - **JMX:** the `org.apache.cassandra.db:type=CIDRGroupsMappingManager` operation `getCidrGroupsOfIP(String)` (`CIDRGroupsMappingManager.java:234-244`, MBean name at L60) calls the same `lookupCidrGroupsForIp`.
   - **nodetool:** `nodetool getcidrgroupsofip <ip>` uses that JMX operation.
3. **Miss:** the loader queries the interval tree (`CIDRGroupsMappingLoader.java:87-94`).
   - If the IP matches no CIDR, the tree returns `null` (`CIDRGroupsMappingIntervalTree.java:328`). Caffeine does not store null results, so no entry is added.
   - If it matches, or the table is empty (`emptySet`), an entry is inserted.
4. **The enforcing check, in Caffeine:** each insert goes through `afterWrite` ([BoundedLocalCache.java:1528](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java#L1528)) → `scheduleDrainBuffers` → `executor.execute(drainBuffersTask)`. Because the executor is `ImmediateExecutor`, `execute` runs the task inline on the calling thread (`ImmediateExecutor.java:136-140`). That task runs `maintenance` → `evictEntries` ([L705](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java#L705)), whose check is [`while (weightedSize() > maximum())`](https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java#L768). That check evicts victims (W-TinyLFU) until the count is at or below the cap.
   - **Outcome at the limit:** an old or new entry is evicted. Lookups never fail; the evicted IP is simply looked up in the tree again next time.
5. **Overshoot and bypass:**
   - **Transient:** writes buffered in Caffeine's write buffer between drains, so a few entries over the cap under concurrent inserts, gone after the next drain.
   - **Full flush:** every `cidr_groups_cache_refresh_interval` minutes (default 5, `DatabaseDescriptor.java:1749-1757`; schedule at `CIDRGroupsMappingCache.java:65-70`), and on `nodetool reloadcidrgroupscache`, the cache is emptied (`invalidateAll`, L83).
   - **No bypass found:** no other path stores per-IP entries.

**A4. Other consumers.** These use heap in the same feature but are outside this cap:
- the interval trees built from `system_auth.cidr_groups` (`CIDRGroupsMappingLoader`), which grow with the size of that table;
- `CIDRPermissionsCache` (per role, governed by the auth-cache settings);
- per-CIDR-group metric counters (`CIDRAuthorizerMetrics.java:84-96`, keyed by group name);
- the latency timers, which use bounded reservoirs;
- per-connection native-transport state (one `ClientState` and its channel per open connection).

None of them holds per-IP state for the life of the cache.

**A5. Evidence beyond the source.**
- `NEWS.txt:163` (CIDR authorizer added).
- `CHANGES.txt:458` (CASSANDRA-18592, CIDR filtering authorizer): https://issues.apache.org/jira/browse/CASSANDRA-18592
- `CHANGES.txt:407` (CASSANDRA-18805, Caffeine upgrade): https://issues.apache.org/jira/browse/CASSANDRA-18805
- `CHANGES.txt:187` (CASSANDRA-20220, CIDR authorizer parameters can be set): https://issues.apache.org/jira/browse/CASSANDRA-20220
- `doc/modules/cassandra/pages/managing/operating/security.adoc`.
- Existing tests that set up the authorizer: `test/unit/org/apache/cassandra/auth/CassandraCIDRAuthorizerMonitorModeTest.java`, `AuthTestUtils.java:150-208`.

## B. Verification solution

**B1. Claim under test.** With `CassandraCIDRAuthorizer` enabled, the number of entries in `ipToCidrGroupsCache`, and the heap it retains, follow min(N, `ip_cache_max_size`) when N distinct client IPs that match a CIDR group are looked up. The heap retained is about 130 B per entry plus 8 B × ceilPow2(cap) for the frequency sketch. The claim is wrong if the entry count, or the retained `Inet4Address` count on a node, exceeds the cap by more than a few after the cache drains.

### B2. Unit tier

**B2a. Environment and build.**
- Linux, JDK 11, Ant. Network access to Maven Central is needed for the first dependency resolve.
- Copy the tree to local disk and work only there:
  `export WORK=/tmp/o04-$USER; mkdir -p $WORK; rsync -a /users/jason92/cassandra-5.0.9/ $WORK/src/`
- Check `df -h /tmp`: at least 5 GB free. If not, use another local disk.
- Build in `$WORK/src`: `ant jar build-test`.
- The test JVM is the standard forked JUnit JVM: `maxmemory=1024m`, jamm agent, `build.xml:1153-1159`.

**B2b. Knobs.** Set `ip_cache_max_size` (system property `probe.max`, passed through `-Dtest.jvm.args`, which the test macro forwards, `build.xml:1192`) to each of:

| `ip_cache_max_size` | Why this value |
|---|---|
| `0` | Degenerate cap |
| `100` | The default |
| `100000` | Cap binds below N |
| `1000000` | Above N, so the cap does not bind; this is the positive control showing the workload moves heap |

The workload size is fixed at `probe.n=600000`. The test sets `cidr_groups_cache_refresh_interval=1440` so no periodic flush occurs during the run.

**B2c. Workload.**
- One CIDR group `g10` → `10.0.0.0/8` is inserted, and the cache is reloaded.
- **Control step first:** 1,000 lookups of `192.168.x.y`, which matches no group.
- **Then:** `cidrAuthorizer.lookupCidrGroupsForIp` is called for N = 600,000 distinct addresses `10.(i>>16).(i>>8).i`, i = 0…599,999. All fall in `10.0.0.0/8`.
- **Why the cap is reached:** 600,000 > 100,000 > 100, so the cap is crossed for every value below 1,000,000. At 1,000,000 the cache reaches 600,000 entries, which is at least half the max, so the sketch is also allocated.

**B2d. Observables and instruments.**
- **The check's own operand:** `ipToCidrGroupsCache.estimatedSize()` after `cleanUp()`. The field is read by reflection; the class is in the same package as the static `CassandraCIDRAuthorizer.cidrGroupsMappingCache`.
- **The running maximum:** estimatedSize sampled every 65,536 lookups.
- **The configured maximum:** `policy().eviction().get().getMaximum()`.
- **Heap:** used heap from `MemoryMXBean` after 3× `System.gc()` with 200 ms sleeps, before and after the loop.
- **Limitation:** heap delta is approximate (other test-JVM activity, GC accounting). The entry count is exact.

**B2e. Procedure.**
1. Create `$WORK/src/test/unit/org/apache/cassandra/auth/IpCacheMaxSizeProbeTest.java`:
```java
package org.apache.cassandra.auth;

import java.lang.management.ManagementFactory;
import java.lang.reflect.Field;
import java.net.InetAddress;
import java.util.*;

import com.github.benmanes.caffeine.cache.LoadingCache;
import org.junit.Assert;
import org.junit.BeforeClass;
import org.junit.Test;

import org.apache.cassandra.SchemaLoader;
import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.config.ParameterizedClass;
import org.apache.cassandra.cql3.CIDR;
import org.apache.cassandra.cql3.CQLTester;

public class IpCacheMaxSizeProbeTest extends CQLTester
{
    static final int MAX = Integer.getInteger("probe.max", 100);
    static final int N = Integer.getInteger("probe.n", 600_000);
    private static final AuthTestUtils.LocalCassandraCIDRAuthorizer cidrAuthorizer =
        new AuthTestUtils.LocalCassandraCIDRAuthorizer(ICIDRAuthorizer.CIDRAuthorizerMode.MONITOR);

    @BeforeClass
    public static void defineSchema()
    {
        SchemaLoader.prepareServer();
        Map<String, String> p = new HashMap<>();
        p.put("cidr_authorizer_mode", "MONITOR");
        p.put("ip_cache_max_size", String.valueOf(MAX));
        p.put("cidr_groups_cache_refresh_interval", "1440");
        DatabaseDescriptor.getRawConfig().cidr_authorizer =
            new ParameterizedClass(CassandraCIDRAuthorizer.class.getName(), p);
        SchemaLoader.setupAuth(new AuthTestUtils.LocalCassandraRoleManager(),
                               new AuthTestUtils.LocalPasswordAuthenticator(),
                               new AuthTestUtils.LocalCassandraAuthorizer(),
                               new AuthTestUtils.LocalCassandraNetworkAuthorizer(),
                               cidrAuthorizer);           // setup() builds the cache at CIDRGroupsMappingCache:59
        AuthCacheService.initializeAndRegisterCaches();   // initCaches() -> loadCidrGroupsCache()
    }

    @SuppressWarnings("unchecked")
    private static LoadingCache<InetAddress, Set<String>> ipCache() throws Exception
    {
        Field f = CIDRGroupsMappingCache.class.getDeclaredField("ipToCidrGroupsCache");
        f.setAccessible(true);
        return (LoadingCache<InetAddress, Set<String>>) f.get(CassandraCIDRAuthorizer.cidrGroupsMappingCache);
    }

    private static long usedAfterGc() throws InterruptedException
    {
        for (int i = 0; i < 3; i++) { System.gc(); Thread.sleep(200); }
        return ManagementFactory.getMemoryMXBean().getHeapMemoryUsage().getUsed();
    }

    @Test
    public void probe() throws Exception
    {
        AuthTestUtils.insertCidrsMappings(Collections.singletonMap(
            "g10", Collections.singletonList(CIDR.getInstance("10.0.0.0/8"))));   // also reloads the cache
        LoadingCache<InetAddress, Set<String>> c = ipCache();
        System.out.println("PROBE policyMaximum=" + c.policy().eviction().get().getMaximum());

        // control: IPs outside every CIDR group -> loader returns null -> nothing cached
        for (int i = 0; i < 1000; i++)
            cidrAuthorizer.lookupCidrGroupsForIp(InetAddress.getByAddress(
                new byte[]{ (byte) 192, (byte) 168, (byte) (i >>> 8), (byte) i }));
        c.cleanUp();
        System.out.println("PROBE outsideGroups estimatedSize=" + c.estimatedSize());

        long base = usedAfterGc();
        long maxSeen = 0;
        for (int i = 0; i < N; i++)
        {
            cidrAuthorizer.lookupCidrGroupsForIp(InetAddress.getByAddress(
                new byte[]{ 10, (byte) (i >>> 16), (byte) (i >>> 8), (byte) i }));
            if ((i & 0xFFFF) == 0) maxSeen = Math.max(maxSeen, c.estimatedSize());
        }
        c.cleanUp();
        long size = c.estimatedSize();
        maxSeen = Math.max(maxSeen, size);
        long after = usedAfterGc();
        System.out.printf("PROBE max=%d n=%d estimatedSize=%d maxSampledSize=%d heapDeltaBytes=%d%n",
                          MAX, N, size, maxSeen, after - base);
        Assert.assertNotNull(c);
    }
}
```
2. Then run the following:
```
cd $WORK/src
for M in 0 100 100000 1000000; do
  ant testsome -Dtest.name=org.apache.cassandra.auth.IpCacheMaxSizeProbeTest \
       -Dtest.jvm.args="-Dprobe.max=$M -Dprobe.n=600000" 2>&1 | tee $WORK/unit-$M.log
  grep PROBE $WORK/unit-$M.log build/test/output/TEST-org.apache.cassandra.auth.IpCacheMaxSizeProbeTest*.xml
done
```
Each value runs in its own forked JVM, so there is no carry-over between values. If `PROBE policyMaximum` does not equal `M`, the property did not reach the test: put the value in the `MAX` constant and rerun.

**B2f. Predictions** (N = 600,000).

| max | outsideGroups size | estimatedSize | maxSampledSize | heapDelta |
|---|---|---|---|---|
| 0 | 0 | 0 | ≤ a few | < 2 MB |
| 100 | 0 | 100 (±1 transient) | ≤ ~100 | < 2 MB |
| 100,000 | 0 | 100,000 | ≤ ~100,000 | ≈ 100k × ~125 B + 1 MB sketch ≈ 13 MB (accept 8-20 MB) |
| 1,000,000 | 0 | 600,000 | 600,000 | ≈ 600k × ~125 B + 8 MB sketch ≈ 80 MB (accept 50-110 MB) |

Two relations should also hold:
- heapDelta(1,000,000) / heapDelta(100,000) ≈ 5-7;
- heapDelta(100) ≈ heapDelta(0).

**B2g. Readings.**

| Observation | Meaning |
|---|---|
| estimatedSize = min(N, max) for every max; heap delta scales as predicted | Claim confirmed at unit level: the cap governs entry count and retained heap. |
| estimatedSize > max by more than a handful after `cleanUp()` (e.g. 600,000 at max=100) | Claim wrong: the cap is not enforced. |
| Entry count capped but heapDelta at max=100 is as large as at max=1,000,000 | The count is capped but something else per lookup is retained. Claim (heap) wrong; look at A4 consumers. |
| max=1,000,000 run does not reach 600,000 entries / heap does not move | Positive control failed (workload not reaching the cache, e.g. IPs not matched, or a reload flushed it). Not confirmed; fix the setup. |
| outsideGroups size > 0 | A3 step 3 trace wrong (nulls cached). Note it; it does not change the cap claim. |

**B2h. Controls.**
- The `policyMaximum` printout shows that the knob reached the cache.
- The 192.168 lookups show that only matched IPs are cached.
- The max=1,000,000 run shows that the same workload does move count and heap when the cap does not bind (positive control).
- The refresh interval of 1440 rules out a periodic `invalidateAll` shrinking the cache.
- Each value runs in a fresh JVM, so no state carries over.

### B3. Cluster tier

**B3a. Environment and build.**
- **Nodes:** one Linux node with JDK 11 and Ant. One node is enough: the cache is per node, and lookups are local.
- **Build:** use the copy from B2a (or a fresh `rsync` to `$WORK/src`), then `cd $WORK/src && ant jar`.
- **Directories:** `mkdir -p $WORK/data/{data,commitlog,saved_caches,hints,cdc}`. All on local disk with at least 5 GB free.
- **Edits to `$WORK/src/conf/cassandra.yaml`** (the copy only):
```
authenticator: PasswordAuthenticator
cidr_authorizer:
  class_name: CassandraCIDRAuthorizer
  parameters:
    cidr_authorizer_mode: "MONITOR"
    cidr_groups_cache_refresh_interval: "1440"
    ip_cache_max_size: "<K>"
data_file_directories:
    - <WORK>/data/data
commitlog_directory: <WORK>/data/commitlog
saved_caches_directory: <WORK>/data/saved_caches
hints_directory: <WORK>/data/hints
cdc_raw_directory: <WORK>/data/cdc
```
  - Replace the existing `authenticator:` line and the `cidr_authorizer:` block at L261-282. Write `<WORK>` out literally as the absolute path.
  - Quote the parameter values: the map is `Map<String,String>`.
- **Heap:** `export MAX_HEAP_SIZE=1G HEAP_NEWSIZE=256M` before starting. JMX stays at the default, local only, 127.0.0.1:7199, no auth (`cassandra-env.sh:229-235`).
- Make sure no other Cassandra on this host uses ports 7000, 7199 or 9042: `ss -ltnp | egrep ':(7000|7199|9042)\b'` must be empty.

**B3b. Knobs.** `ip_cache_max_size` K is one of the following, with one fresh node start (wiped data dir) per value:

| K | Why this value |
|---|---|
| `100` | Default |
| `100000` | Binds below the workload |
| `1000000` | Does not bind for N = 600,000; positive control |

The value is set in yaml, and a restart is required (A1).

**B3c. Workload.**
- **Setup:** `nodetool updatecidrgroup lo 127.0.0.0/8` then `nodetool reloadcidrgroupscache`. Every loopback source then matches group `lo`, so each lookup inserts an entry.
- **(W1) JMX path, main workload:** a JMX client calls `getCidrGroupsOfIP` on N = 600,000 distinct addresses `127.(i>>16).(i>>8).(i&255)` for i = 65,536 … 665,535 (127.1.0.0 to 127.10.39.255; this avoids 127.0.0.x). At an expected ~2-10k local RMI calls/s, this takes about 1-5 min.
  - **Arithmetic:** 600,000 > 100,000 > 100. With K = 1,000,000 the cache should hold 600,000 entries, ≈ 80 MB: measurable against a 1 GB heap.
- **(W2) Native client path, confirmation, M = 2,000 logins:**
  - **Setup:** run it after `nodetool reloadcidrgroupscache` has emptied the cache.
  - **What it does:** a raw native-protocol v4 client binds each connection to a distinct source `127.200.(i/250).(1+i%250)`, logs in as `cassandra/cassandra`, and runs `SELECT release_version FROM system.local`. That query triggers `validateLogin` → lookup (A3 step 2).
  - **Duration:** each login costs one bcrypt check (~50-100 ms), so about 2-4 min.

**B3d. Observables and instruments.**
- **Retained objects:** `jcmd <pid> GC.class_histogram`, which forces a full GC and counts live objects only. Read these rows:
  - `java.net.Inet4Address`;
  - `java.net.InetAddress$InetAddressHolder`;
  - `java.util.concurrent.ConcurrentHashMap$Node`;
  - the Caffeine node class (the row matching `com.github.benmanes.caffeine.cache.P` whose instance count jumps; expected `PSMS`).
  - Bytes are taken from those rows.
- **Heap:** `jcmd <pid> GC.heap_info` after `jcmd <pid> GC.run` (used heap), and `nodetool info | grep -i heap`.
- **Sampling:** histograms at baseline (twice, 60 s apart, to measure noise), right after W1, 60 s later, after `nodetool reloadcidrgroupscache`, and after W2.
- **Not observable directly:** the cache's entry count. Cassandra exports no metric for it; `system_views.cidr_filtering_metrics_*` and `nodetool cidrfilteringstats` give only counts and latencies. The `Inet4Address` delta is the proxy.

**B3e. Procedure** (repeat for each K).
1. Configure as in B3a with the chosen K, then `rm -rf $WORK/data/*/*`.
2. Start the node and check it:
   - `cd $WORK/src && bin/cassandra -p $WORK/cassandra.pid > $WORK/start-$K.log 2>&1`;
   - wait until `bin/nodetool status` shows `UN`;
   - `PID=$(cat $WORK/cassandra.pid)`;
   - `grep -i cidr logs/system.log` shows no errors.
3. Wait until `bin/cqlsh -u cassandra -p cassandra -e "select release_version from system.local"` succeeds. The default role is created about 10 s after startup.
4. Set up and check the group:
   - `bin/nodetool updatecidrgroup lo 127.0.0.0/8; bin/nodetool reloadcidrgroupscache; bin/nodetool getcidrgroupsofip 127.1.0.1` must print `lo`.
   - Then reload again (`bin/nodetool reloadcidrgroupscache`) to start from an empty cache.
5. Take the baseline: `jcmd $PID GC.class_histogram > $WORK/h-$K-base1.txt`; `sleep 60`; repeat to `h-$K-base2.txt`; `jcmd $PID GC.run; jcmd $PID GC.heap_info > $WORK/heap-$K-base.txt`.
6. Run W1. Create `$WORK/tools/JmxProbe.java`:
```java
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.*;
public class JmxProbe {
  public static void main(String[] a) throws Exception {
    int start = Integer.parseInt(a[0]), n = Integer.parseInt(a[1]);
    JMXConnector c = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
    MBeanServerConnection m = c.getMBeanServerConnection();
    ObjectName on = new ObjectName("org.apache.cassandra.db:type=CIDRGroupsMappingManager");
    long t0 = System.nanoTime();
    for (int i = start; i < start + n; i++) {
      String ip = "127." + ((i >>> 16) & 255) + "." + ((i >>> 8) & 255) + "." + (i & 255);
      m.invoke(on, "getCidrGroupsOfIP", new Object[]{ ip }, new String[]{ "java.lang.String" });
    }
    System.out.printf("done %d lookups in %.1f s%n", n, (System.nanoTime() - t0) / 1e9);
    c.close();
  }
}
```
   Then compile and run it: `cd $WORK/tools && javac JmxProbe.java && java -cp . JmxProbe 65536 600000`.
7. Measure after W1: `jcmd $PID GC.class_histogram > $WORK/h-$K-w1.txt`; `jcmd $PID GC.run; jcmd $PID GC.heap_info > $WORK/heap-$K-w1.txt`; `sleep 60`; histogram again to `h-$K-w1b.txt` to check stability.
8. Run the flush control: `bin/nodetool reloadcidrgroupscache`; `jcmd $PID GC.class_histogram > $WORK/h-$K-flushed.txt`.
9. Run W2. Create `$WORK/tools/NativeProbe.java`:
```java
import java.io.*; import java.net.*; import java.nio.charset.StandardCharsets;
public class NativeProbe {
  static byte[] body(IOConsumer w) throws IOException { ByteArrayOutputStream b = new ByteArrayOutputStream(); w.accept(new DataOutputStream(b)); return b.toByteArray(); }
  interface IOConsumer { void accept(DataOutputStream d) throws IOException; }
  static void str(DataOutputStream d, String s) throws IOException { byte[] x = s.getBytes(StandardCharsets.UTF_8); d.writeShort(x.length); d.write(x); }
  static void send(DataOutputStream o, int op, byte[] b) throws IOException { o.writeByte(4); o.writeByte(0); o.writeShort(0); o.writeByte(op); o.writeInt(b.length); o.write(b); o.flush(); }
  static int recv(DataInputStream in) throws IOException { in.readByte(); in.readByte(); in.readShort(); int op = in.readUnsignedByte(); byte[] b = new byte[in.readInt()]; in.readFully(b);
    if (op == 0) throw new IOException("ERROR " + new String(b, StandardCharsets.UTF_8)); return op; }
  public static void main(String[] a) throws Exception {
    int m = Integer.parseInt(a[0]);
    byte[] startup = body(d -> { d.writeShort(1); str(d, "CQL_VERSION"); str(d, "3.0.0"); });
    byte[] tok = "\0cassandra\0cassandra".getBytes(StandardCharsets.UTF_8);
    byte[] auth = body(d -> { d.writeInt(tok.length); d.write(tok); });
    byte[] q = "SELECT release_version FROM system.local".getBytes(StandardCharsets.UTF_8);
    byte[] query = body(d -> { d.writeInt(q.length); d.write(q); d.writeShort(1); d.writeByte(0); });
    for (int i = 0; i < m; i++) {
      String src = "127.200." + (i / 250) + "." + (1 + i % 250);
      try (Socket s = new Socket()) {
        s.bind(new InetSocketAddress(src, 0));
        s.connect(new InetSocketAddress("127.0.0.1", 9042), 5000);
        DataOutputStream o = new DataOutputStream(new BufferedOutputStream(s.getOutputStream()));
        DataInputStream in = new DataInputStream(new BufferedInputStream(s.getInputStream()));
        send(o, 0x01, startup); if (recv(in) != 0x03) throw new IOException("expected AUTHENTICATE");
        send(o, 0x0F, auth);    if (recv(in) != 0x10) throw new IOException("expected AUTH_SUCCESS");
        send(o, 0x07, query);   if (recv(in) != 0x08) throw new IOException("expected RESULT");
      }
    }
    System.out.println("done " + m + " logins");
  }
}
```
   Then compile and run it: `javac NativeProbe.java && java -cp . NativeProbe 2000`; then `jcmd $PID GC.class_histogram > $WORK/h-$K-w2.txt`.
10. Stop the node: `kill $(cat $WORK/cassandra.pid)`. Wait, then `pgrep -f CassandraDaemon -u $USER` must be empty; use `kill -9` only if it is still there after 60 s.
11. Compute the deltas, for example `grep -E ' java.net.Inet4Address$' $WORK/h-$K-*.txt`. Deltas are relative to `base2`, for instances and bytes, for each row listed in B3d. The heap delta comes from the `heap_info` used values.

**B3f. Predictions** (ΔInet4Address = instances minus base2; baseline noise is expected to be within ± a few hundred).

| K | Δ after W1 | Heap Δ after W1 | Δ after flush | Δ after W2 |
|---|---|---|---|---|
| 100 | ≈ +100 | < 5 MB (noise) | ≈ 0 | ≈ +100 |
| 100,000 | ≈ +100,000 | ≈ 13 MB (accept 8-20) | ≈ 0 | ≈ +2,000 |
| 1,000,000 | ≈ +600,000 | ≈ 80 MB (accept 50-110) | ≈ 0 | ≈ +2,000 |

- In every run, ΔInetAddressHolder ≈ ΔInet4Address ≈ Δ(Caffeine node) ≈ Δ(CHM$Node).
- The `w1b` reading (60 s later) equals `w1`, because the refresh interval is 1440 min.

**B3g. Readings.**

| Observation | Meaning |
|---|---|
| ΔInet4Address after W1 ≈ min(600,000, K) and heap Δ scales as predicted; drops to ≈ 0 after flush | Claim confirmed: the cap governs retained heap on a real node. |
| ΔInet4Address after W1 ≫ K (e.g. ~600,000 at K=100) and drops on flush | Claim wrong: the cache exceeds its configured cap. |
| ΔInet4Address after W1 ≫ K but does **not** drop on flush | The retention is not this cache (another per-IP consumer). This is not a refutation of the cap; investigate. |
| Heap Δ tracks K but with a per-entry cost far from ~130 B (e.g. > 500 B) | The cap holds, but the A2 per-entry estimate is wrong; record the measured bytes per entry. |
| K=1,000,000 run shows Δ ≪ 600,000 | Positive control failed: the IPs were not matched (check `getcidrgroupsofip`), a reload flushed the cache, or the workload did not run. Not confirmed. |
| W2: Δ ≈ +min(2,000, K) | The native client path populates the same capped cache. |
| W2: Δ ≈ 0 at K=1,000,000 | The client path did not reach the lookup (check the MONITOR mode setting and the client errors). W1 still stands. |

**B3h. Controls.**
- Two baselines 60 s apart give the noise floor.
- The `reloadcidrgroupscache` flush attributes the retained objects to this cache (A3 step 5).
- K=1,000,000 is the positive control: the same workload with the cap not binding.
- `getcidrgroupsofip 127.1.0.1 = lo` shows that the IPs match a group, so they are cached and not dropped as null.
- The refresh interval of 1440 rules out timed flushes.
- A fresh data dir and a fresh JVM per K remove carry-over.

**B4. Risks and cleanup.**
- **Disk:** everything goes under `$WORK` on local disk, under 1 GB in total: the build plus about 100 MB of node data and logs. Nothing is written to the shared source tree or shared storage. Check `du -sh $WORK` at the end.
- **Processes:** the unit tests run in forked JVMs that exit when done. Each cluster run ends with `kill` of the pid, and `pgrep -f CassandraDaemon -u $USER` must show nothing. The JmxProbe and NativeProbe JVMs exit by themselves.
- **Ports and network:** ports 7000, 7199 and 9042 are bound on loopback only. The 127.x source addresses are loopback and need no configuration on Linux.
- **Cleanup:** `rm -rf $WORK` after copying out the logs and histograms that are needed.

## C. Sources read
- /users/jason92/writeup-ext/playbook-autonomous.md
- /users/jason92/writeup-ext/_TEMPLATE-autonomous.md
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingCache.java
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingLoader.java
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingIntervalTree.java
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingTable.java
- src/java/org/apache/cassandra/auth/CIDRGroupsMappingManager.java
- src/java/org/apache/cassandra/auth/CassandraCIDRAuthorizer.java
- src/java/org/apache/cassandra/auth/AbstractCIDRAuthorizer.java
- src/java/org/apache/cassandra/auth/AllowAllCIDRAuthorizer.java
- src/java/org/apache/cassandra/auth/AuthenticatedUser.java
- src/java/org/apache/cassandra/auth/AuthConfig.java
- src/java/org/apache/cassandra/service/ClientState.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/metrics/CIDRAuthorizerMetrics.java
- src/java/org/apache/cassandra/concurrent/ImmediateExecutor.java
- src/java/org/apache/cassandra/tools/nodetool/GetCIDRGroupsOfIP.java, UpdateCIDRGroup.java
- conf/cassandra.yaml, conf/cassandra-env.sh
- build.xml, .build/parent-pom-template.xml, .build/cassandra-deps-template.xml
- test/unit/org/apache/cassandra/auth/CassandraCIDRAuthorizerMonitorModeTest.java, AuthTestUtils.java
- test/unit/org/apache/cassandra/SchemaLoader.java
- CHANGES.txt, NEWS.txt
- https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/BoundedLocalCache.java
- https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/Caffeine.java
- https://github.com/ben-manes/caffeine/blob/v3.1.8/caffeine/src/main/java/com/github/benmanes/caffeine/cache/FrequencySketch.java

## D. Stage-4 feedback

**2026-11-12, run 1 (apt179):** unit **Confirmed — caps** (B2g row 1: entries = min(600000, max) exactly, heapDelta
0.07 / 0.08 / 13.5 / 81.0 MB); cluster **Confirmed — caps** (B3g rows 1 and 6: retained addresses +102 / +100,002 /
+600,002 for K = 100 / 100000 / 1000000, live heap +0.14 / 13.6 / 88.8 MB, ≈ 0 after the flush; native logins fill the same
cache). Outcome class: true positive. Measured ~120 B per entry in the per-entry objects (142-155 B with the arrays). Noted,
outside the frozen rows: after a flush ~22.5 MB stays at K = 1,000,000 (sketch, hash table, an unidentified `int[]`).
No trace section refuted. Results: `../../stage4-runtime-verification/results/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md`.

**Stage-4 audit amendments (2026-11-12, before any reading).** These change the runbook (B2a, B3a, B3d, B3e) and define the
tolerances of words already in B2f-B2g and B3f-B3g; no prediction value or conclusions row is changed. Results:
`../../stage4-runtime-verification/results/ip_cache_max_size-cidrgroupsmappingcache-iptocidrgroupscache--autonomous.md`.

- **AM1 (B2a, B3a: where and how to build).** `WORK=/mydata/jingsong-cass-s4/o04` on the run node; `$WORK/src` is a
  `copy-source.sh` copy of the repository's `systems/cassandra/source/` (not `/users/jason92/cassandra-5.0.9`, not `/tmp`).
  Build `ant build-test` for the unit tier; after the unit tier, `ant jar` once, and no `ant` while a node runs from the tree.
- **AM2 (B3a, B3e, JmxProbe, NativeProbe: ports on a shared node).** The node uses `storage_port: 7300`,
  `ssl_storage_port: 7301`, seeds `"127.0.0.1:7300"`, `native_transport_port: 9342`, and JMX port 7499 (`JMX_PORT` in the
  copy's `conf/cassandra-env.sh`). The port check of B3a is on 7300, 7301, 7499, 9342. `nodetool` takes `-p 7499`; `cqlsh`
  takes `127.0.0.1 9342`; JmxProbe connects to 127.0.0.1:7499 and NativeProbe to 127.0.0.1:9342 (the port is a program
  argument; otherwise the code is as filed). B3e.10's check is `ps -eo pid,cmd | grep '[C]assandraDaemon'` filtered on
  `$WORK`, since other users' nodes may run on the host.
- **AM3 (B3d, B3e.5/7/11: which heap number).** "Heap Δ after W1" is the `Total` bytes line of `GC.class_histogram`
  (live objects after the full GC the histogram forces) at `w1` minus at `base2`. The `GC.heap_info` used value after
  `GC.run` (base vs w1) is recorded beside it, but the row match uses the histogram total (on these nodes `heap_info`
  after `GC.run` has not been a reliable live-heap reading).
- **AM4 (B2f-B2g, B3f-B3g: tolerances of "≈", "a few", "a handful").**
  - Unit: "a few" / "a handful" = at most 16 entries. A stated entry count is met if the reading is within ±16 of it
    (the 100 row keeps its own ±1). "heapDelta(100) ≈ heapDelta(0)" = within 2 MB of each other.
  - Cluster: "Δ ≈ X" for an instance count = within X ± (0.05·X + 500); "≈ 0" = |Δ| ≤ 500. "ΔA ≈ ΔB" for the four rows of
    B3f's first bullet = each within ±(0.05·ΔInet4Address + 500) of ΔInet4Address. "w1b equals w1" = Inet4Address count
    within ±500. "Δ ≫ K" = Δ > 2·K + 500.
  - A reading that meets no row under these tolerances is reported as "Not confirmed (no matching row)".
