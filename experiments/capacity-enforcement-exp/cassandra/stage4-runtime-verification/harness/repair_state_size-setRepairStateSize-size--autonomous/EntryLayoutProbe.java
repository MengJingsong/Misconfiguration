// Shallow instance sizes in this JVM (JDK 11, compressed oops and class pointers, as on the node) of every class on the per-entry
// object list derived from the source (Amendment 2026-10-28, B3f (iv')). Instances are made with Unsafe.allocateInstance (no
// constructor runs) or plainly for JDK classes; sizes are read from this JVM's own class histogram (bytes / instances).
// usage: java -Xmx512m -cp "<clone>/build/classes/main:<clone>/build/lib/jars/*" EntryLayoutProbe.java
import java.lang.management.ManagementFactory;
import javax.management.ObjectName;
import java.util.*;

public class EntryLayoutProbe {
    static final int N = 1000;
    public static void main(String[] a) throws Exception {
        java.lang.reflect.Field f = sun.misc.Unsafe.class.getDeclaredField("theUnsafe"); f.setAccessible(true);
        sun.misc.Unsafe u = (sun.misc.Unsafe) f.get(null);
        String[] cls = {"org.apache.cassandra.repair.state.CoordinatorState", "org.apache.cassandra.repair.state.CoordinatorState$Phase",
                "org.apache.cassandra.repair.messages.RepairOption", "org.apache.cassandra.repair.state.Completable$Result",
                "org.apache.cassandra.dht.Range", "org.apache.cassandra.utils.TimeUUID",
                "com.google.common.cache.LocalCache$StrongAccessWriteEntry", "com.google.common.cache.LocalCache$StrongValueReference",
                "java.util.HashSet", "java.util.HashMap", "java.util.concurrent.ConcurrentHashMap", "java.util.concurrent.atomic.AtomicReference",
                "java.util.concurrent.atomic.AtomicReferenceArray"};
        List<Object> keep = new ArrayList<>();
        for (String c : cls) { Class<?> k = Class.forName(c, false, EntryLayoutProbe.class.getClassLoader()); for (int i = 0; i < N; i++) keep.add(u.allocateInstance(k)); }
        HashMap<Integer, Integer> m = new HashMap<>(); for (int i = 0; i < N; i++) m.put(i + 1000000, i);   // N HashMap$Node
        keep.add(m);
        for (int i = 0; i < N; i++) { keep.add(new String(new char[]{'r', 's'})); keep.add(new long[6]); keep.add(new Object[32]); }
        System.gc();
        String h = ManagementFactory.getPlatformMBeanServer().invoke(new ObjectName("com.sun.management:type=DiagnosticCommand"),
                "gcClassHistogram", new Object[]{new String[0]}, new String[]{String[].class.getName()}).toString();
        Set<String> want = new HashSet<>(Arrays.asList(cls)); want.addAll(Arrays.asList("java.util.HashMap$Node", "java.lang.String", "[J", "[Ljava.lang.Object;", "[B"));
        for (String l : h.split("\n")) { String[] p = l.trim().split("\\s+"); if (p.length >= 4 && want.contains(p[3])) {
            long n = Long.parseLong(p[1]), b = Long.parseLong(p[2]);
            System.out.println("LAYOUT " + p[3] + " instances=" + n + " bytes=" + b + (p[3].startsWith("[") ? "" : " shallow=" + (b / n) + (b % n == 0 ? "" : " (not uniform)"))); } }
        System.out.println("probe keep " + keep.size() + " " + System.getProperty("java.version") + " " + java.lang.management.ManagementFactory.getRuntimeMXBean().getInputArguments());
    }
}
