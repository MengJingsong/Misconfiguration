package org.apache.cassandra.utils.memory;

import java.lang.reflect.Field;
import java.util.*;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicLong;

import org.apache.cassandra.utils.concurrent.ImmediateFuture;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 unit tier for max_region_size-tryswapregion-minsize--autonomous (B2). One JVM per call:
 *   java ... org.apache.cassandra.utils.memory.NativeAllocatorRegionProbe <case> [arg]
 * case: C1 | C2 | C3 <size> | C4 <A> | P1 | Z.  Prints lines "READ key=value ..." to stdout; exit 0.
 * Private state (NativeAllocator.regions, Region.capacity, RACE_ALLOCATED) is read by reflection.
 */
public class NativeAllocatorRegionProbe
{
    static final OpOrder order = new OpOrder();
    static final OpOrder.Group group = order.start();

    static NativePool pool(long limit)
    {
        return new NativePool(1L << 30, limit, 0.75f, () -> ImmediateFuture.success(false)); // no-op cleaner
    }

    @SuppressWarnings("unchecked")
    static List<Integer> caps(NativeAllocator a) throws Exception
    {
        Field f = NativeAllocator.class.getDeclaredField("regions");
        f.setAccessible(true);
        ConcurrentLinkedQueue<Object> q = (ConcurrentLinkedQueue<Object>) f.get(a);
        List<Integer> out = new ArrayList<>();
        for (Object r : q)
        {
            Field c = r.getClass().getDeclaredField("capacity");
            c.setAccessible(true);
            out.add(c.getInt(r));
        }
        return out;
    }

    static void report(String label, NativePool p, NativeAllocator... as) throws Exception
    {
        long owns = 0, total = 0, max = 0, n = 0;
        List<Integer> all = new ArrayList<>();
        for (NativeAllocator a : as)
        {
            owns += a.offHeap().owns();
            for (int c : caps(a)) { total += c; max = Math.max(max, c); n++; if (as.length <= 1) all.add(c); }
        }
        System.out.println("READ " + label + " owns=" + owns + " used=" + p.offHeap.used() + " limit=" + p.offHeap.limit
                           + " capTotal=" + total + " capMax=" + max + " regions=" + n + " slack=" + (total - owns)
                           + (as.length <= 1 ? " caps=" + all : ""));
    }

    static void discard(NativeAllocator... as)
    {
        for (NativeAllocator a : as) { a.setDiscarding(); a.setDiscarded(); }
    }

    public static void main(String[] args) throws Exception
    {
        String c = args[0];
        switch (c)
        {
            case "C1": // 20000 x 64 B, L = 1 GiB
            {
                NativePool p = pool(1L << 30); NativeAllocator a = new NativeAllocator(p);
                for (int i = 0; i < 20000; i++) a.allocate(64, group);
                report("C1", p, a); discard(a); break;
            }
            case "C2": // L = 10000, 100 x 100 B, then tryAllocate(1)
            {
                NativePool p = pool(10000); NativeAllocator a = new NativeAllocator(p);
                for (int i = 0; i < 100; i++) a.allocate(100, group);
                report("C2", p, a);
                System.out.println("READ C2 tryAllocate1=" + p.offHeap.tryAllocate(1));
                discard(a); break;
            }
            case "C3": // one allocation of args[1] bytes
            {
                int s = Integer.parseInt(args[1]);
                NativePool p = pool(1L << 30); NativeAllocator a = new NativeAllocator(p);
                a.allocate(s, group);
                report("C3 size=" + s, p, a); discard(a); break;
            }
            case "C4": // A allocators x (100 x 64 B)
            {
                int n = Integer.parseInt(args[1]);
                NativePool p = pool(1L << 30); NativeAllocator[] as = new NativeAllocator[n];
                for (int k = 0; k < n; k++) { as[k] = new NativeAllocator(p); for (int i = 0; i < 100; i++) as[k].allocate(64, group); }
                report("C4 A=" + n, p, as); discard(as); break;
            }
            case "Z": // zero-slack control: exactly 8192 once
            {
                NativePool p = pool(1L << 30); NativeAllocator a = new NativeAllocator(p);
                a.allocate(8192, group);
                report("Z", p, a); discard(a); break;
            }
            case "P1": // positive control: pool limit 2 MiB blocks the writer
            {
                long L = 2L << 20;
                NativePool p = pool(L); NativeAllocator a = new NativeAllocator(p);
                AtomicLong done = new AtomicLong(); AtomicBoolean extra = new AtomicBoolean();
                Thread t = new Thread(() -> {
                    for (int i = 0; i < 32768; i++) { a.allocate(64, group); done.incrementAndGet(); }
                    System.out.println("READ P1 filled calls=" + done.get());
                    a.allocate(64, group);            // the 32769th call: 2 MiB + 64 > L
                    extra.set(true);
                }, "p1-writer");
                t.setDaemon(true); t.start();
                Thread.sleep(1500);
                report("P1 beforeRelease", p, a);
                System.out.println("READ P1 writerState=" + t.getState() + " extraCallReturned=" + extra.get() + " calls=" + done.get());
                a.offHeap().adjust(-6400, group);      // release 100 x 64 B: signals hasRoom
                t.join(5000);
                System.out.println("READ P1 afterRelease writerState=" + t.getState() + " extraCallReturned=" + extra.get());
                report("P1 afterRelease", p, a);
                break;
            }
            default: throw new IllegalArgumentException(c);
        }
        System.out.flush();
        System.exit(0);
    }
}
