// Known-answer check for HprofRetained.java and selfcheck.py (Amendment 2026-10-28, B3d (6)): a JVM that holds a structure of
// known shape, writes its own class histogram (DiagnosticCommand gcClassHistogram) and its own live heap dump, and prints the
// expected R_cache and R_values computed by hand from JDK 11 layout rules (compressed oops and class pointers).
// usage: java -Xmx256m KnownAnswer.java <outdir>
import java.lang.management.ManagementFactory;
import javax.management.ObjectName;
import java.nio.file.*;

public class KnownAnswer {
    static final class Item { long a, b; int c; byte[] own; Object shared; }       // 12 + 8 + 8 + 4 + 4 + 4 = 40
    static final class Box { Object[] items; long x; }                             // 12 + 4 + 8 = 24
    static final class Holder { Box cache; Object other; }                         // the cut field is `cache`
    static Holder ROOT; static Object SHARED = new int[7]; static Object KEEP;

    static void build() {
        Box box = new Box(); box.items = new Object[100];
        for (int i = 0; i < 100; i++) { Item it = new Item(); it.own = new byte[10]; it.shared = SHARED; box.items[i] = it; }
        ROOT = new Holder(); ROOT.cache = box; ROOT.other = new long[3];
        KEEP = box.items[0];                       // item 0 (and its byte[10]) is also kept elsewhere
    }

    public static void main(String[] a) throws Exception {
        Path out = Paths.get(a[0]); Files.createDirectories(out);
        build();                                   // built in its own frame, so no local variable of main keeps it
        System.gc();
        Object h = ManagementFactory.getPlatformMBeanServer().invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"),
                "gcClassHistogram", new Object[]{new String[0]}, new String[]{String[].class.getName()});
        Files.write(out.resolve("ka-hist.txt"), h.toString().getBytes());
        Path d = out.resolve("ka-dump.hprof"); Files.deleteIfExists(d);
        com.sun.management.HotSpotDiagnosticMXBean hs = ManagementFactory.getPlatformMXBean(com.sun.management.HotSpotDiagnosticMXBean.class);
        hs.dumpHeap(d.toString(), true);
        long item = 40, boxS = 24, arr = 16 + 4 * 100, own = 32;          // byte[10]: 16 + 10 -> 32
        long rCache = boxS + arr + 99 * (item + own);                      // item 0 and its byte[10] are retained by KEEP
        long rValues = 100 * (item + own);                                 // C enters no Item at all, so all 100 and their arrays
        System.out.println("KA expected R_cache=" + rCache + " R_values=" + rValues + " valueInDump=100 valueReachableAfterCut=1 cutEdges=1");
        System.out.println("KA keepalive " + ROOT.cache.items.length + " " + KEEP.hashCode() % 1);
    }
}
