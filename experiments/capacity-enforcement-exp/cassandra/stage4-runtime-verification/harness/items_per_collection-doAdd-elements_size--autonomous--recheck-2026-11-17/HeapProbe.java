// JMX probe for the recheck run of items_per_collection-doAdd-elements_size--autonomous (design R5).
// usage: java -cp <dir> HeapProbe snap <out.tsv>        all threads' allocated bytes, heap, GC counts, JVM uptime
//        java -cp <dir> HeapProbe get <objectName> <attr>
//        java -cp <dir> HeapProbe readthresholds <true|false> <abortSpec|->   (StorageService setters, then read-back)
// Connects to the node's local JMX (127.0.0.1:7199, no auth: shipped cassandra-env.sh LOCAL_JMX=yes).
import javax.management.*;
import javax.management.remote.*;
import java.lang.management.*;
import java.io.*;
import java.util.*;

public class HeapProbe {
    public static void main(String[] a) throws Exception {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u)) {
            MBeanServerConnection s = c.getMBeanServerConnection();
            switch (a[0]) {
                case "snap": snap(s, a[1]); break;
                case "get":
                    System.out.println("RESULT get " + a[1] + " " + a[2] + " = " + s.getAttribute(new ObjectName(a[1]), a[2]));
                    break;
                case "readthresholds": {
                    ObjectName ss = new ObjectName("org.apache.cassandra.db:type=StorageService");
                    // shakedown fix S2: these are MBean attributes (getter/setter pairs), not operations
                    s.setAttribute(ss, new Attribute("ReadThresholdsEnabled", Boolean.parseBoolean(a[1])));
                    if (!a[2].equals("-"))
                        s.setAttribute(ss, new Attribute("LocalReadTooLargeAbortThreshold", a[2]));
                    System.out.println("RESULT readthresholds enabled=" + s.getAttribute(ss, "ReadThresholdsEnabled")
                                       + " localAbort=" + s.getAttribute(ss, "LocalReadTooLargeAbortThreshold"));
                    break;
                }
                default: throw new IllegalArgumentException(a[0]);
            }
        }
    }

    static void snap(MBeanServerConnection s, String out) throws Exception {
        com.sun.management.ThreadMXBean t = ManagementFactory.newPlatformMXBeanProxy(
            s, ManagementFactory.THREAD_MXBEAN_NAME, com.sun.management.ThreadMXBean.class);
        RuntimeMXBean rt = ManagementFactory.newPlatformMXBeanProxy(s, ManagementFactory.RUNTIME_MXBEAN_NAME, RuntimeMXBean.class);
        MemoryMXBean mem = ManagementFactory.newPlatformMXBeanProxy(s, ManagementFactory.MEMORY_MXBEAN_NAME, MemoryMXBean.class);
        List<GarbageCollectorMXBean> gcs = ManagementFactory.getPlatformMXBeans(s, GarbageCollectorMXBean.class);
        long epoch = System.currentTimeMillis();
        long up = rt.getUptime();
        long[] ids = t.getAllThreadIds();
        long[] al = t.getThreadAllocatedBytes(ids);
        ThreadInfo[] inf = t.getThreadInfo(ids);
        MemoryUsage h = mem.getHeapMemoryUsage();
        long sum = 0;
        try (PrintWriter w = new PrintWriter(new FileWriter(out))) {
            w.printf("epoch_ms\t%d%nuptime_ms\t%d%nheap_used\t%d%nheap_committed\t%d%n", epoch, up, h.getUsed(), h.getCommitted());
            for (GarbageCollectorMXBean g : gcs)
                w.printf("gc\t%s\t%d\t%d%n", g.getName().replace(' ', '_'), g.getCollectionCount(), g.getCollectionTime());
            for (int i = 0; i < ids.length; i++) {
                if (al[i] < 0) continue;
                sum += al[i];
                String n = inf[i] == null ? "?" : inf[i].getThreadName().replace('\t', ' ');
                w.printf("t\t%d\t%d\t%s%n", ids[i], al[i], n);
            }
        }
        System.out.println("RESULT snap file=" + out + " epoch_ms=" + epoch + " uptime_ms=" + up + " threads=" + ids.length
                           + " alloc_sum=" + sum + " heap_used=" + h.getUsed());
    }
}
