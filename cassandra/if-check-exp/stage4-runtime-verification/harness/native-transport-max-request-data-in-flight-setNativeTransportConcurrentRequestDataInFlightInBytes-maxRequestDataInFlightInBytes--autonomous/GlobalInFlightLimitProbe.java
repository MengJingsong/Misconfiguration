/*
 * Stage-4 unit-tier probe for native_transport_max_request_data_in_flight
 * (case B2, amended 2026-10-26). One mode per fresh JVM:
 *   sweep L      4 threads tryAllocate(262144) on the real ClientResourceLimits.GLOBAL_LIMIT through an endpoint Allocator
 *   default      the limit at startup and after setGlobalLimit(-1) equals maxMemory/10
 *   control L    the same loop with L far above the workload: no failure
 *   v4 L         PreV5Handlers.java:182-184 style: tryAllocate, on failure allocate anyway
 *   msg-default  native_transport_max_message_size follows min(max_mutation_size, global, per-IP)
 *   msg-explicit yaml sets native_transport_max_message_size: 1MiB; the setter only lowers it
 * Lines: "CHECK <name> expected=<x> actual=<y> OK|MISMATCH", "U,<mode>,<key>=<value>", and a final
 * "RESULT <mode> checks=<n> mismatches=<m>".  Package org.apache.cassandra.transport: Allocator is package-private.
 */
package org.apache.cassandra.transport;

import java.net.InetAddress;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.net.ResourceLimits.Outcome;

public class GlobalInFlightLimitProbe
{
    static final long CHUNK = 262144, MiB = 1048576, GiB = 1L << 30;
    static int checks = 0, mismatches = 0;
    static String mode;

    static void check(String name, Object expected, Object actual)
    {
        checks++;
        boolean ok = String.valueOf(expected).equals(String.valueOf(actual));
        if (!ok) mismatches++;
        System.out.println("CHECK " + mode + " " + name + " expected=" + expected + " actual=" + actual + " " + (ok ? "OK" : "MISMATCH"));
    }

    static void u(String key, Object v) { System.out.println("U," + mode + "," + key + "=" + v); }

    /** run `attempts` tryAllocate(CHUNK) from 4 threads; returns outcome counts; tracks the maximum usage seen */
    static Map<Outcome, AtomicInteger> loop(ClientResourceLimits.Allocator a, int attempts, AtomicLong maxUsage) throws Exception
    {
        Map<Outcome, AtomicInteger> counts = new ConcurrentHashMap<>();
        for (Outcome o : Outcome.values()) counts.put(o, new AtomicInteger());
        AtomicInteger next = new AtomicInteger();
        Thread[] ts = new Thread[4];
        for (int t = 0; t < 4; t++)
        {
            ts[t] = new Thread(() -> {
                while (next.getAndIncrement() < attempts)
                {
                    Outcome o = a.tryAllocate(CHUNK);
                    counts.get(o).incrementAndGet();
                    long use = ClientResourceLimits.getCurrentGlobalUsage();
                    maxUsage.accumulateAndGet(use, Math::max);
                }
            });
            ts[t].start();
        }
        for (Thread t : ts) t.join();
        return counts;
    }

    public static void main(String[] args) throws Exception
    {
        mode = args[0];
        long L = args.length > 1 ? Long.parseLong(args[1]) : 0;
        DatabaseDescriptor.daemonInitialization();
        long E = Runtime.getRuntime().maxMemory();
        u("maxMemory", E);
        u("startup_global_limit", ClientResourceLimits.getGlobalLimit());
        u("startup_per_ip_limit", ClientResourceLimits.getEndpointLimit());
        u("startup_message_size", DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
        u("max_mutation_size", DatabaseDescriptor.getMaxMutationSize());
        InetAddress addr = InetAddress.getByName("127.0.0.1");

        switch (mode)
        {
            case "sweep":
            case "control":
            {
                ClientResourceLimits.setEndpointLimit(GiB);
                ClientResourceLimits.setGlobalLimit(L);
                check("getGlobalLimit", L, ClientResourceLimits.getGlobalLimit());
                check("usage_initial", 0, ClientResourceLimits.getCurrentGlobalUsage());
                ClientResourceLimits.Allocator a = ClientResourceLimits.getAllocatorForEndpoint(addr);
                AtomicLong maxUsage = new AtomicLong();
                if (mode.equals("control"))
                {
                    Map<Outcome, AtomicInteger> c = loop(a, 48, maxUsage);
                    check("successes", 48, c.get(Outcome.SUCCESS).get());
                    check("failures", 0, c.get(Outcome.INSUFFICIENT_GLOBAL).get() + c.get(Outcome.INSUFFICIENT_ENDPOINT).get());
                    check("usage_after", 48 * CHUNK, ClientResourceLimits.getCurrentGlobalUsage());
                    u("max_usage_seen", maxUsage.get());
                    a.release(48 * CHUNK);
                    check("usage_after_release", 0, ClientResourceLimits.getCurrentGlobalUsage());
                    break;
                }
                int fit = (int) (L / CHUNK);
                Map<Outcome, AtomicInteger> c = loop(a, fit + 16, maxUsage);
                check("successes", fit + (System.getProperty("probe.mutant") != null ? 1 : 0), c.get(Outcome.SUCCESS).get());   // probe.mutant: instrument check, expectation deliberately wrong
                check("failures", 16, c.get(Outcome.INSUFFICIENT_GLOBAL).get());
                check("failures_endpoint", 0, c.get(Outcome.INSUFFICIENT_ENDPOINT).get());
                check("usage_after_fill", L, ClientResourceLimits.getCurrentGlobalUsage());
                check("max_usage_seen_le_L", true, maxUsage.get() <= L);
                u("max_usage_seen", maxUsage.get());
                int half = fit / 2;
                a.release(half * CHUNK);
                check("usage_after_release_half", L - half * CHUNK, ClientResourceLimits.getCurrentGlobalUsage());
                Map<Outcome, AtomicInteger> c2 = loop(a, half + 16, maxUsage);
                check("successes_after_release", half, c2.get(Outcome.SUCCESS).get());
                check("failures_after_release", 16, c2.get(Outcome.INSUFFICIENT_GLOBAL).get());
                check("usage_after_refill", L, ClientResourceLimits.getCurrentGlobalUsage());
                check("max_usage_seen_le_L_2", true, maxUsage.get() <= L);
                a.release(L);
                check("usage_after_release_all", 0, ClientResourceLimits.getCurrentGlobalUsage());
                break;
            }
            case "default":
            {
                check("startup_default_is_maxMemory_div_10", E / 10, ClientResourceLimits.getGlobalLimit());
                ClientResourceLimits.setGlobalLimit(64 * MiB);
                ClientResourceLimits.setGlobalLimit(-1);
                check("after_setGlobalLimit_minus1", E / 10, ClientResourceLimits.getGlobalLimit());
                break;
            }
            case "v4":
            {
                ClientResourceLimits.setEndpointLimit(GiB);
                ClientResourceLimits.setGlobalLimit(8 * MiB);
                ClientResourceLimits.Allocator a = ClientResourceLimits.getAllocatorForEndpoint(addr);
                AtomicLong maxUsage = new AtomicLong();
                Map<Outcome, AtomicInteger> c = loop(a, 32, maxUsage);
                check("fill_successes", 32, c.get(Outcome.SUCCESS).get());
                check("usage_after_fill", 8 * MiB, ClientResourceLimits.getCurrentGlobalUsage());
                for (int i = 0; i < 4; i++)
                {
                    check("tryAllocate_fails_" + i, Outcome.INSUFFICIENT_GLOBAL, a.tryAllocate(CHUNK));
                    a.allocate(CHUNK);       // PreV5Handlers.java:182-184
                }
                check("usage_after_forced", 8 * MiB + 4 * CHUNK, ClientResourceLimits.getCurrentGlobalUsage());
                check("usage_gt_L", true, ClientResourceLimits.getCurrentGlobalUsage() > 8 * MiB);
                for (int i = 0; i < 4; i++)
                    check("later_tryAllocate_fails_" + i, Outcome.INSUFFICIENT_GLOBAL, a.tryAllocate(CHUNK));
                a.release(8 * MiB + 4 * CHUNK);
                check("usage_after_release_all", 0, ClientResourceLimits.getCurrentGlobalUsage());
                break;
            }
            case "msg-default":
            {
                long mut = DatabaseDescriptor.getMaxMutationSize();
                check("startup_size_is_min3", Math.min(mut, Math.min(ClientResourceLimits.getGlobalLimit(), ClientResourceLimits.getEndpointLimit())),
                      DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setEndpointLimit(GiB);
                ClientResourceLimits.setGlobalLimit(MiB);
                check("size_after_global_1MiB", Math.min(mut, MiB), DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setGlobalLimit(64 * MiB);
                check("size_after_global_64MiB", Math.min(mut, 64 * MiB), DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                break;
            }
            case "msg-explicit":
            {
                check("startup_size_explicit", MiB, DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setEndpointLimit(GiB);
                check("size_after_per_ip_1GiB", MiB, DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setGlobalLimit(64 * MiB);
                check("size_after_global_64MiB", MiB, DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setGlobalLimit(524288);
                check("size_after_global_512KiB", 524288, DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                ClientResourceLimits.setGlobalLimit(8 * MiB);
                check("size_after_global_8MiB", 524288, DatabaseDescriptor.getNativeTransportMaxMessageSizeInBytes());
                break;
            }
            default:
                throw new IllegalArgumentException(mode);
        }
        System.out.println("RESULT " + mode + (args.length > 1 ? " L=" + L : "") + " checks=" + checks + " mismatches=" + mismatches);
        System.exit(mismatches == 0 ? 0 : 1);
    }
}
