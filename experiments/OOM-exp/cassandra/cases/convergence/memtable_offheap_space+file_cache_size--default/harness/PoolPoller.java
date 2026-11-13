// R1 recheck per-pool sampler (2026-11-11). One JMX connection to the local Cassandra node (127.0.0.1:7199),
// one CSV line every INTERVAL ms until the node's PID disappears or the JMX connection fails.
// Usage: java -cp tools PoolPoller <pid> <cgroup-dir|-> <interval-ms> <out.csv>
// Columns: wall clock, /proc RssAnon/RssFile, cgroup memory.current / memory.stat anon,file / events max,oom_kill,
// heap used, JDK direct BufferPool (MemoryUsed, Count), Cassandra BufferPool chunk-cache (Size=reserved+overflow,
// UsedSize, OverflowSize), networking pool Size, ChunkCache (Size=weighted, Entries), memtable off-heap/on-heap
// counters (global AllMemtables*DataSize, i.e. the allocators' own counters K), memks writes (WriteLatency Count),
// MemtablePool PendingFlushTasks and BlockedOnAllocation Count.
import javax.management.*;
import javax.management.remote.*;
import java.nio.file.*;
import java.util.*;
import java.lang.management.*;

public class PoolPoller {
    static MBeanServerConnection c;
    static Object get(String on, String attr) {
        try { return c.getAttribute(new ObjectName(on), attr); } catch (Exception e) { return ""; }
    }
    static String g(String on) { return String.valueOf(get(on, "Value")); }
    static String cnt(String on) { return String.valueOf(get(on, "Count")); }
    static String procField(String pid, String key) {
        try { for (String l : Files.readAllLines(Paths.get("/proc/" + pid + "/status")))
                if (l.startsWith(key + ":")) return l.replaceAll("[^0-9]", ""); } catch (Exception e) { return "gone"; }
        return "";
    }
    static String cg(String dir, String file, String key) {
        if (dir.equals("-")) return "";
        try { List<String> ls = Files.readAllLines(Paths.get(dir, file));
              if (key == null) return ls.get(0).trim();
              for (String l : ls) if (l.startsWith(key + " ")) return l.substring(key.length() + 1).trim(); } catch (Exception e) { return "gone"; }
        return "";
    }
    public static void main(String[] a) throws Exception {
        String pid = a[0], cgd = a[1]; long iv = Long.parseLong(a[2]); Path out = Paths.get(a[3]);
        JMXConnector jc = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:7199/jmxrmi"));
        c = jc.getMBeanServerConnection();
        String M = "org.apache.cassandra.metrics:";
        String hdr = "ts,epoch_ms,rss_anon_kB,rss_file_kB,cg_current_B,cg_anon_B,cg_file_B,cg_ev_max,cg_ev_oom_kill,heap_used_B,"
                + "jdk_direct_used_B,jdk_direct_count,bp_chunk_size_B,bp_chunk_used_B,bp_chunk_overflow_B,bp_net_size_B,"
                + "cc_size_B,cc_entries,mt_offheap_all_B,mt_onheap_all_B,memks_offheap_all_B,memks_writes,pending_flush,blocked_on_alloc\n";
        if (!Files.exists(out)) Files.write(out, hdr.getBytes());
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("HH:mm:ss");
        while (Files.exists(Paths.get("/proc/" + pid))) {
            long t = System.currentTimeMillis();
            String heap;
            try { heap = String.valueOf(((javax.management.openmbean.CompositeData) get("java.lang:type=Memory", "HeapMemoryUsage")).get("used")); } catch (Exception e) { heap = ""; }
            String[] v = {
                f.format(new Date(t)), String.valueOf(t), procField(pid, "RssAnon"), procField(pid, "RssFile"),
                cg(cgd, "memory.current", null), cg(cgd, "memory.stat", "anon"), cg(cgd, "memory.stat", "file"),
                cg(cgd, "memory.events", "max"), cg(cgd, "memory.events", "oom_kill"), heap,
                String.valueOf(get("java.nio:type=BufferPool,name=direct", "MemoryUsed")),
                String.valueOf(get("java.nio:type=BufferPool,name=direct", "Count")),
                g(M + "type=BufferPool,scope=chunk-cache,name=Size"), g(M + "type=BufferPool,scope=chunk-cache,name=UsedSize"),
                g(M + "type=BufferPool,scope=chunk-cache,name=OverflowSize"), g(M + "type=BufferPool,scope=networking,name=Size"),
                g(M + "type=Cache,scope=ChunkCache,name=Size"), g(M + "type=Cache,scope=ChunkCache,name=Entries"),
                g(M + "type=Table,name=AllMemtablesOffHeapDataSize"), g(M + "type=Table,name=AllMemtablesOnHeapDataSize"),
                g(M + "type=Table,keyspace=memks,scope=standard1,name=AllMemtablesOffHeapDataSize"),
                cnt(M + "type=Table,keyspace=memks,scope=standard1,name=WriteLatency"),
                g(M + "type=MemtablePool,name=PendingFlushTasks"), cnt(M + "type=MemtablePool,name=BlockedOnAllocation") };
            Files.write(out, (String.join(",", v) + "\n").getBytes(), StandardOpenOption.APPEND);
            long s = iv - (System.currentTimeMillis() - t); if (s > 0) Thread.sleep(s);
        }
        try { jc.close(); } catch (Exception e) {}
    }
}
