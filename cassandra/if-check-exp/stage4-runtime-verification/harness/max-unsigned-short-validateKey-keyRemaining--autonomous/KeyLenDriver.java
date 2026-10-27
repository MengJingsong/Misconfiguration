import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.Validation;
import org.apache.cassandra.db.marshal.AbstractType;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.db.marshal.Int32Type;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.exceptions.InvalidRequestException;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.memory.HeapPool;
import org.apache.cassandra.utils.concurrent.OpOrder;

/**
 * Stage-4 unit driver for max-unsigned-short-validateKey-keyRemaining--autonomous (B2 with amendments B2i).
 * Target: Validation.validateKey(TableMetadata, ByteBuffer) (Validation.java:51); QueryProcessor.validateKey is the shadowing method.
 *   bounds          (method, L) rows, null, and the Int32Type order check
 *   stream N L      N fresh distinct L-byte keys through Validation.validateKey, none held; heap after full GC
 *   hold L          hold 1,000 then 5,000 accepted L-byte keys; retained heap after full GC
 *   oom L           hold accepted L-byte keys until OutOfMemoryError (run with -Xmx256m)
 *   control         HeapPool 64 MiB (a cleaner that frees nothing): 1,024 allocations of 65535 B return, the 1,025th blocks; Validation accepts 100,000 more keys meanwhile
 * Lines start with "STAGE4 ". Every comparison with a prediction prints "STAGE4 check <what> ok|MISMATCH ...".
 */
public class KeyLenDriver
{
    static TableMetadata md, mdInt;

    static long heap()
    {
        for (int i = 0; i < 3; i++) { System.gc(); try { Thread.sleep(50); } catch (InterruptedException e) {} }
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    static String tryQ(ByteBuffer k)
    {
        try { QueryProcessor.validateKey(k); return "accepted"; }
        catch (InvalidRequestException e) { return "rejected:" + e.getMessage(); }
    }

    static String tryV(TableMetadata m, ByteBuffer k)
    {
        try { Validation.validateKey(m, k); return "accepted"; }
        catch (InvalidRequestException e) { return "rejected:" + e.getMessage(); }
    }

    static void check(String what, boolean ok, String detail)
    {
        System.out.println("STAGE4 check " + what + (ok ? " ok" : " MISMATCH") + " " + detail);
    }

    static String expect(int L)
    {
        if (L == 0) return "rejected:Key may not be empty";
        if (L > 65535) return "rejected:Key length of " + L + " is longer than maximum of 65535";
        return "accepted";
    }

    static TableMetadata table(AbstractType<?> t)
    {
        return TableMetadata.builder("ks", "t").partitioner(Murmur3Partitioner.instance).addPartitionKeyColumn("k", t).build();
    }

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        md = table(BytesType.instance);
        mdInt = table(Int32Type.instance);
        System.out.println("STAGE4 info maxmemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version"));
        switch (a[0])
        {
            case "bounds":
            {
                int[] ls = { 0, 1, 1000, 65534, 65535, 65536, 70000, 1000000 };
                for (int L : ls)
                {
                    ByteBuffer k = ByteBuffer.allocate(L);
                    String q = tryQ(k), v = tryV(md, k);
                    System.out.println("STAGE4 bound L=" + L + " QueryProcessor=" + q + " Validation=" + v);
                    check("bound L=" + L + " Validation", v.equals(expect(L)), v);
                    check("bound L=" + L + " QueryProcessor", q.equals(expect(L)), q);
                }
                String qn = tryQ(null), vn = tryV(md, null);
                System.out.println("STAGE4 bound null QueryProcessor=" + qn + " Validation=" + vn);
                check("bound null Validation", vn.equals("rejected:Key may not be empty"), vn);
                check("bound null QueryProcessor", qn.equals("rejected:Key may not be empty"), qn);
                // order of the checks: length (line 51) before type validation (line 60)
                String o1 = tryV(mdInt, ByteBuffer.allocate(65536));
                String o2 = tryV(mdInt, ByteBuffer.allocate(65535));
                String o3 = tryV(mdInt, ByteBuffer.allocate(4));
                System.out.println("STAGE4 order Int32 L=65536 " + o1);
                System.out.println("STAGE4 order Int32 L=65535 " + o2);
                System.out.println("STAGE4 order Int32 L=4 " + o3);
                check("order Int32 L=65536 rejected by the length check", o1.equals(expect(65536)), o1);
                check("order Int32 L=65535 rejected by the type, not the length", o2.startsWith("rejected:") && !o2.contains("Key length") && o2.contains("Expected 4 or 0 byte int"), o2);
                check("order Int32 L=4 accepted", o3.equals("accepted"), o3);
                break;
            }
            case "stream":
            {
                int n = Integer.parseInt(a[1]), L = Integer.parseInt(a[2]);
                long h0 = heap(), accepted = 0, bytes = 0, rejected = 0;
                long t0 = System.nanoTime();
                for (int i = 0; i < n; i++)
                {
                    ByteBuffer k = ByteBuffer.allocate(L);
                    k.putInt(0, i); // distinct
                    if (tryV(md, k).equals("accepted")) accepted++; else rejected++;
                    bytes += L;
                }
                long ms = (System.nanoTime() - t0) / 1000000;
                long h1 = heap();
                System.out.println("STAGE4 stream n=" + n + " L=" + L + " accepted_calls=" + accepted + " rejected_calls=" + rejected
                                   + " key_bytes_validated=" + bytes + " ms=" + ms + " heap_before=" + h0 + " heap_after=" + h1);
                check("stream all accepted", accepted == n && rejected == 0, "accepted=" + accepted + " rejected=" + rejected);
                check("stream heap after gc below 100 MB", h1 < 100_000_000L, "heap_after=" + h1);
                check("stream total key bytes above the per-key cap x 1000", bytes > 65535L * 1000, "bytes=" + bytes + " cap=65535");
                break;
            }
            case "hold":
            {
                int L = Integer.parseInt(a[1]);
                List<ByteBuffer> keep = new ArrayList<>();
                long h0 = heap();
                long[] m = new long[2];
                int[] steps = { 1000, 5000 };
                for (int s = 0; s < 2; s++)
                {
                    while (keep.size() < steps[s])
                    {
                        ByteBuffer k = ByteBuffer.allocate(L);
                        if (L >= 4) k.putInt(0, keep.size()); else k.put(0, (byte) keep.size()); // L<4: keys cannot all differ
                        if (!tryV(md, k).equals("accepted"))
                            throw new IllegalStateException("key rejected at L=" + L);
                        keep.add(k);
                    }
                    m[s] = heap();
                    System.out.println("STAGE4 hold L=" + L + " keys=" + keep.size() + " retained_bytes=" + (m[s] - h0) + " heap=" + m[s]);
                }
                double slope = (m[1] - m[0]) / 4000.0;
                System.out.println("STAGE4 hold L=" + L + " slope_bytes_per_key=" + slope + " per_1000_keys_MB=" + (slope * 1000 / 1e6));
                check("hold L=" + L + " slope within L+40..L+120", slope >= L + 40 && slope <= L + 120, "slope=" + slope);
                System.out.println("STAGE4 keep " + keep.size());
                break;
            }
            case "oom":
            {
                int L = Integer.parseInt(a[1]);
                List<ByteBuffer> keep = new ArrayList<>();
                long rejected = 0;
                boolean oom = false;
                try
                {
                    for (int i = 0; i < 20000; i++)
                    {
                        ByteBuffer k = ByteBuffer.allocate(L);
                        k.putInt(0, i);
                        if (!tryV(md, k).equals("accepted")) rejected++;
                        keep.add(k);
                    }
                }
                catch (OutOfMemoryError e)
                {
                    oom = true;
                }
                int held = keep.size();
                keep = null;
                System.out.println("STAGE4 oom L=" + L + " oom=" + oom + " held_before_oom=" + held + " validation_rejections=" + rejected);
                check("oom occurred", oom, "held=" + held);
                check("oom after 1500..4100 held keys", held >= 1500 && held <= 4100, "held=" + held);
                check("oom with no validation rejection", rejected == 0, "rejected=" + rejected);
                break;
            }
            case "control":
            {
                final long LIMIT = 64L << 20;
                HeapPool pool = new HeapPool(LIMIT, 0.75f, () -> org.apache.cassandra.utils.concurrent.ImmediateFuture.success(true));
                final HeapPool.Allocator alloc = new HeapPool.Allocator(pool);
                final OpOrder order = new OpOrder();
                final OpOrder.Group group = order.start();
                final AtomicInteger done = new AtomicInteger();
                Thread w = new Thread(() -> { for (int i = 0; i < 5000; i++) { alloc.allocate(65535, group); done.incrementAndGet(); } });
                w.setDaemon(true);
                w.start();
                long t0 = System.currentTimeMillis();
                int last = -1;
                while (System.currentTimeMillis() - t0 < 60000)
                {
                    Thread.sleep(500);
                    int d = done.get();
                    if (d == last && d > 0 && System.currentTimeMillis() - t0 > 3000) break;
                    last = d;
                }
                int d1 = done.get();
                long used = pool.onHeap.used();
                // key validations meanwhile: all accepted, the pool does not care
                long accepted = 0, rejected = 0;
                for (int i = 0; i < 100000; i++)
                {
                    ByteBuffer k = ByteBuffer.allocate(65535);
                    k.putInt(0, i);
                    if (tryV(md, k).equals("accepted")) accepted++; else rejected++;
                }
                Thread.sleep(2000);
                int d2 = done.get();
                System.out.println("STAGE4 control limit=" + LIMIT + " allocations_returned=" + d1 + " used=" + used + " state=" + w.getState()
                                   + " after_2s_more=" + d2 + " validations_accepted=" + accepted + " rejected=" + rejected);
                check("control exactly 1024 allocations returned", d1 == 1024 && d2 == 1024, "d1=" + d1 + " d2=" + d2);
                check("control used equals 1024 x 65535", used == 1024L * 65535, "used=" + used);
                check("control 1025th allocation still blocked", w.getState() == Thread.State.WAITING || w.getState() == Thread.State.TIMED_WAITING, "state=" + w.getState());
                check("control validation accepted 100000 keys", accepted == 100000 && rejected == 0, "accepted=" + accepted + " rejected=" + rejected);
                break;
            }
            default: throw new IllegalArgumentException(a[0]);
        }
        System.out.flush();
        System.exit(0); // the control's blocked worker is a daemon, but be explicit
    }
}
