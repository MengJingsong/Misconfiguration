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
