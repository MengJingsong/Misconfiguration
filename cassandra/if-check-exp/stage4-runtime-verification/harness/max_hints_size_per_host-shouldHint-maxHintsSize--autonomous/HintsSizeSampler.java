/*
 * Stage-4 harness, cluster tier (B3 as amended 2026-10-27) of
 * max_hints_size_per_host-shouldHint-maxHintsSize--autonomous.
 * (JMX pattern adapted from harness/maxHintsInProgress-checkHintOverload-totalHintsInProgress--autonomous/HintsSampler.java)
 *
 *   java -cp <bin> HintsSizeSampler get  <host> <port> <hintsDir> <hostId>
 *       -> one line: epoch_ms,dir_bytes,files,total_hints,hints_created_n2,max_hints_size_mib
 *   java -cp <bin> HintsSizeSampler loop <host> <port> <hintsDir> <hostId> <out.csv> <stopFile> <periodMs>
 *       -> the same line every periodMs until stopFile exists (header line first)
 * dir_bytes = sum of File.length() over <hintsDir>/<hostId>-*.hints (apparent bytes, as `du -cb`).
 * A value that cannot be read is -1 (error once to stderr).
 */
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.HashSet;
import java.util.Set;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class HintsSizeSampler
{
    static final Set<String> warned = new HashSet<>();

    static long read(MBeanServerConnection c, String bean, String attr)
    {
        try
        {
            return ((Number) c.getAttribute(new ObjectName(bean), attr)).longValue();
        }
        catch (Exception e)
        {
            if (warned.add(bean + attr)) System.err.println("read failed " + bean + " " + attr + ": " + e);
            return -1;
        }
    }

    static long createdN2(MBeanServerConnection c)
    {
        try
        {
            for (ObjectName on : c.queryNames(new ObjectName("org.apache.cassandra.metrics:type=HintsService,*"), null))
            {
                String n = on.getKeyProperty("name");
                if (n != null && n.startsWith("Hints_created") && n.contains("127.0.0.2"))
                    return ((Number) c.getAttribute(on, "Count")).longValue();
            }
            return 0; // counter not created yet: no hint created for n2
        }
        catch (Exception e)
        {
            if (warned.add("created")) System.err.println("read failed Hints_created: " + e);
            return -1;
        }
    }

    static String row(MBeanServerConnection c, File dir, String hostId)
    {
        long bytes = 0; int files = 0;
        File[] fs = dir.listFiles();
        if (fs != null)
            for (File f : fs)
                if (f.getName().startsWith(hostId + "-") && f.getName().endsWith(".hints")) { bytes += f.length(); files++; }
        long th = read(c, "org.apache.cassandra.metrics:type=Storage,name=TotalHints", "Count");
        long cr = createdN2(c);
        long mib = read(c, "org.apache.cassandra.db:type=StorageProxy", "MaxHintsSizePerHostInMiB");
        return System.currentTimeMillis() + "," + bytes + "," + files + "," + th + "," + cr + "," + mib;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[1] + ":" + a[2] + "/jmxrmi");
        try (JMXConnector jc = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection c = jc.getMBeanServerConnection();
            File dir = new File(a[3]);
            String hostId = a[4];
            if (a[0].equals("get"))
            {
                System.out.println(row(c, dir, hostId));
                return;
            }
            File stop = new File(a[6]);
            long period = Long.parseLong(a[7]);
            try (PrintWriter w = new PrintWriter(new FileWriter(a[5], true)))
            {
                w.println("epoch_ms,dir_bytes,files,total_hints,hints_created_n2,max_hints_size_mib");
                w.flush();
                while (true)
                {
                    long t0 = System.currentTimeMillis();
                    w.println(row(c, dir, hostId));
                    w.flush();
                    if (stop.exists()) break;
                    long sl = period - (System.currentTimeMillis() - t0);
                    while (sl > 0 && !stop.exists()) { Thread.sleep(Math.min(sl, 200)); sl = period - (System.currentTimeMillis() - t0); }
                }
            }
        }
    }
}
