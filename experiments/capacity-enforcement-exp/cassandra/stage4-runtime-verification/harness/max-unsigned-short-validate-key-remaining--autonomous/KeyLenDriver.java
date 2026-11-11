import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.cql3.QueryProcessor;
import org.apache.cassandra.cql3.Validation;
import org.apache.cassandra.db.marshal.BytesType;
import org.apache.cassandra.dht.Murmur3Partitioner;
import org.apache.cassandra.exceptions.InvalidRequestException;
import org.apache.cassandra.schema.TableMetadata;
import org.apache.cassandra.utils.ByteBufferUtil;

/**
 * Stage-4 unit driver for max-unsigned-short-validate-key-remaining--autonomous (B2, with amendments B2i).
 *   bounds            one line per (method, L): accepted / rejected + message, plus null, empty and UNSET rows
 *   stream <N> <L>    N freshly allocated distinct L-byte keys through both methods, none held; heap after a full GC
 *   hold <L>          hold 1,000 then 5,000 accepted L-byte keys; retained heap after a full GC at 0 / 1000 / 5000
 * Output lines start with "STAGE4 ". Every comparison with a prediction prints "STAGE4 check <what> ok|MISMATCH ...".
 */
public class KeyLenDriver
{
    static TableMetadata md;

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

    static String tryV(ByteBuffer k)
    {
        try { Validation.validateKey(md, k); return "accepted"; }
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

    public static void main(String[] a) throws Exception
    {
        DatabaseDescriptor.daemonInitialization();
        md = TableMetadata.builder("ks", "t").partitioner(Murmur3Partitioner.instance)
                          .addPartitionKeyColumn("k", BytesType.instance).build();
        System.out.println("STAGE4 info maxmemory=" + Runtime.getRuntime().maxMemory() + " java=" + System.getProperty("java.version"));
        switch (a[0])
        {
            case "bounds":
            {
                int[] ls = { 0, 1, 1000, 65534, 65535, 65536, 70000, 1000000 };
                for (int L : ls)
                {
                    ByteBuffer k = ByteBuffer.allocate(L);
                    String q = tryQ(k), v = tryV(k);
                    System.out.println("STAGE4 bound L=" + L + " QueryProcessor=" + q + " Validation=" + v);
                    check("bound L=" + L + " QueryProcessor", q.equals(expect(L)), q);
                    check("bound L=" + L + " Validation", v.equals(expect(L)), v);
                }
                String qn = tryQ(null), vn = tryV(null);
                System.out.println("STAGE4 bound null QueryProcessor=" + qn + " Validation=" + vn);
                check("bound null QueryProcessor", qn.equals("rejected:Key may not be empty"), qn);
                check("bound null Validation", vn.equals("rejected:Key may not be empty"), vn);
                String qu = tryQ(ByteBufferUtil.UNSET_BYTE_BUFFER);
                System.out.println("STAGE4 bound UNSET QueryProcessor=" + qu);
                check("bound UNSET QueryProcessor (empty buffer, B2i.2)", qu.equals("rejected:Key may not be empty"), qu);
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
                    if (tryQ(k).equals("accepted")) accepted++; else rejected++;
                    if (tryV(k).equals("accepted")) accepted++; else rejected++;
                    bytes += L;
                }
                long ms = (System.nanoTime() - t0) / 1000000;
                long h1 = heap();
                System.out.println("STAGE4 stream n=" + n + " L=" + L + " accepted_calls=" + accepted + " rejected_calls=" + rejected
                                   + " key_bytes_validated=" + bytes + " ms=" + ms + " heap_before=" + h0 + " heap_after=" + h1);
                check("stream all accepted", accepted == 2L * n && rejected == 0, "accepted=" + accepted + " rejected=" + rejected);
                check("stream heap after gc below 100 MB", h1 < 100_000_000L, "heap_after=" + h1);
                check("stream total key bytes above the per-key cap", bytes > 65535L * 1000, "bytes=" + bytes + " cap=65535");
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
                        if (!tryQ(k).equals("accepted") || !tryV(k).equals("accepted"))
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
            default: throw new IllegalArgumentException(a[0]);
        }
    }
}
