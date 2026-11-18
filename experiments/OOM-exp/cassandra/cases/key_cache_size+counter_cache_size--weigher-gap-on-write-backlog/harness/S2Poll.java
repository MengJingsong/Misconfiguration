// R8 (2026-11-17): S2 run-2 S2Poll plus key/counter cache Size and Entries; exits when V is gone.
// S2 run 2 sampler (2026-11-16): ONE long-lived JVM polling the local Cassandra over JMX (127.0.0.1:7199), replacing
// run 1's per-sample nodetool/cqlsh calls (each a new JVM/Python process; on the 8-core m400 under load a nodetool
// cycle took ~30 s and competed with the victim for CPU). No forced GC: heap from MemoryMXBean (used/committed).
//   java -Xmx48m S2Poll <intervalMs> <cgroupDir>      prints one line per sample to stdout
import javax.management.*;
import javax.management.remote.*;
import java.lang.management.*;
import java.nio.file.*;

public class S2Poll {
    static Object get(MBeanServerConnection c, String on, String attr) {
        try { return c.getAttribute(new ObjectName(on), attr); } catch (Exception e) { return "-"; }
    }
    static String rd(String p) { try { return new String(Files.readAllBytes(Paths.get(p))).trim(); } catch (Exception e) { return "-"; } }
    public static void main(String[] a) throws Exception {
        long iv = Long.parseLong(a[0]); String cg = a[1];
        JMXConnector j = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
        MBeanServerConnection c = j.getMBeanServerConnection();
        MemoryMXBean mem = ManagementFactory.newPlatformMXBeanProxy(c, ManagementFactory.MEMORY_MXBEAN_NAME, MemoryMXBean.class);
        String tp = "org.apache.cassandra.metrics:type=ThreadPools,path=request,scope=%s,name=%s";
        String tb = "org.apache.cassandra.metrics:type=Table,keyspace=b6,scope=t_blob,name=%s";
        while (true) {
            long t = System.currentTimeMillis() / 1000; String heap;
            try { MemoryUsage u = mem.getHeapMemoryUsage(); heap = (u.getUsed() >> 20) + "/" + (u.getCommitted() >> 20); } catch (Exception e) { break; }
            System.out.println(t + " heapMiB=" + heap
                + " mut_pending=" + get(c, String.format(tp, "MutationStage", "PendingTasks"), "Value")
                + " mut_active=" + get(c, String.format(tp, "MutationStage", "ActiveTasks"), "Value")
                + " mut_done=" + get(c, String.format(tp, "MutationStage", "CompletedTasks"), "Value")
                + " ntr_pending=" + get(c, String.format(tp, "Native-Transport-Requests", "PendingTasks"), "Value")
                + " ntr_active=" + get(c, String.format(tp, "Native-Transport-Requests", "ActiveTasks"), "Value")
                + " memtable_live=" + get(c, String.format(tb, "MemtableLiveDataSize"), "Value")
                + " memtable_onheap=" + get(c, String.format(tb, "MemtableOnHeapSize"), "Value")
                + " hints_created=" + get(c, "org.apache.cassandra.metrics:type=Storage,name=TotalHints", "Count")
                + " hints_inprog=" + get(c, "org.apache.cassandra.metrics:type=Storage,name=TotalHintsInProgress", "Count")
                + " kc_size=" + get(c, "org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Size", "Value")
                + " kc_entries=" + get(c, "org.apache.cassandra.metrics:type=Cache,scope=KeyCache,name=Entries", "Value")
                + " cc_size=" + get(c, "org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Size", "Value")
                + " cc_entries=" + get(c, "org.apache.cassandra.metrics:type=Cache,scope=CounterCache,name=Entries", "Value")
                + " memcur=" + rd(cg + "/memory.current") + " swapcur=" + rd(cg + "/memory.swap.current"));
            System.out.flush();
            Thread.sleep(iv);
        }
        System.exit(0);
    }
}
