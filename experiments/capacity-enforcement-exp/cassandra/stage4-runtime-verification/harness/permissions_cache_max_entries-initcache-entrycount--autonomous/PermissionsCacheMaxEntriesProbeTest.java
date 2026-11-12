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
