import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import javax.management.MBeanServer;
import javax.management.ObjectName;

/**
 * Stage-4 harness, cluster re-run (Amendment 2026-10-27 (after run 1, authorised by the user) — B3f/C7 P4) of
 * max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous. Instrument known answer outside Cassandra.
 *
 * Question: how many bytes does one byte[] of length len add to the "Total" of GC.class_histogram (the instrument behind L in
 * RngProbe.liveTotal()) in a JVM with node 1's G1 settings (-XX:+UseG1GC -XX:G1HeapRegionSize=16m, conf/jvm11-server.options:63,66)?
 * Prediction written in the amendment: A(len) = align8(16 + len) if that is below half a region; otherwise the array is humongous and
 * occupies ceil(align8(16 + len) / R) whole regions, A(len) = that many regions x R, because G1 fills the rest of the last region with a
 * filler object that the histogram counts.
 *
 * usage: java -XX:+UseG1GC -XX:G1HeapRegionSize=16m -Xms4G -Xmx4G HumongousKnownAnswer <k> <len> [<len> ...]
 * prints, per len, the measured Total delta per array, the [B delta per array, the other-class delta per array, and both predictions.
 */
public class HumongousKnownAnswer
{
    static Map<String, Long> histo() throws Exception
    {
        MBeanServer mbs = ManagementFactory.getPlatformMBeanServer();
        String r = (String) mbs.invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"), "gcClassHistogram",
                                       new Object[]{ new String[0] }, new String[]{ String[].class.getName() });
        Map<String, Long> m = new HashMap<>();
        for (String line : r.split("\n"))
        {
            String t = line.trim();
            String[] f = t.split("\\s+");
            if (t.startsWith("Total"))
                m.put("Total", Long.parseLong(f[2]));
            else if (f.length >= 4 && f[0].endsWith(":"))
                m.merge(f[3], Long.parseLong(f[2]), Long::sum);
        }
        return m;
    }

    static long align8(long x)
    {
        return (x + 7) / 8 * 8;
    }

    public static void main(String[] a) throws Exception
    {
        int k = Integer.parseInt(a[0]);
        long region = Long.parseLong(ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class)
                                                       .getVMOption("G1HeapRegionSize").getValue());
        System.out.println("KA,region=" + region + ",k=" + k + ",jvm=" + System.getProperty("java.vm.version"));
        for (int i = 1; i < a.length; i++)
        {
            int len = Integer.parseInt(a[i]);
            Map<String, Long> h0 = histo();
            List<byte[]> keep = new ArrayList<>();
            for (int j = 0; j < k; j++)
                keep.add(new byte[len]);
            Map<String, Long> h1 = histo();
            long dTotal = h1.get("Total") - h0.get("Total");
            long dB = h1.getOrDefault("[B", 0L) - h0.getOrDefault("[B", 0L);
            long base = align8(16 + (long) len);
            long predHum = base >= region / 2 ? (base + region - 1) / region * region : base;
            System.out.println("KA,len=" + len + ",total_per_array=" + (dTotal / k) + ",byte_array_per_array=" + (dB / k)
                               + ",other_per_array=" + ((dTotal - dB) / k) + ",pred_plain=" + base + ",pred_region=" + predHum
                               + ",humongous=" + (base >= region / 2) + ",kept=" + keep.size());
            keep.clear();
        }
    }
}
