import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;

import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * JMX client for org.apache.cassandra.diag:type=DiagnosticEventService (DiagnosticEventService.java:60-63), node on 127.0.0.1.
 *   java DiagJmx <port> enabled                     isDiagnosticsEnabled
 *   java DiagJmx <port> enable <class>              enableEventPersistence
 *   java DiagJmx <port> disable <class>             disableEventPersistence
 *   java DiagJmx <port> read <class>                readEvents(class, 0, 100000): prints "READ class count=<n> minKey=<k> maxKey=<k> opBytes=<sum of operation string lengths>"
 *   java DiagJmx <port> heap                        java.lang:type=Memory HeapMemoryUsage used
 *   java DiagJmx <port> drain <class> <ms> <stopfile>   unbounded client-side retainer (control): every <ms> ms readEvents(class, lastSeen, 100000),
 *                                                   keeps every returned map in a list; prints "DRAIN retained=<n>" until <stopfile> exists
 */
public class DiagJmx
{
    static final ObjectName B;
    static { try { B = new ObjectName("org.apache.cassandra.diag:type=DiagnosticEventService"); } catch (Exception e) { throw new RuntimeException(e); } }

    @SuppressWarnings("unchecked")
    static SortedMap<Long, Map<String, ?>> read(MBeanServerConnection m, String cls, long last) throws Exception
    {
        return (SortedMap<Long, Map<String, ?>>) m.invoke(B, "readEvents", new Object[]{ cls, last, 100000 },
                                                          new String[]{ "java.lang.String", "java.lang.Long", "int" });
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            switch (a[1])
            {
                case "enabled":
                    System.out.println("ENABLED " + m.getAttribute(B, "DiagnosticsEnabled"));
                    break;
                case "enable":
                    m.invoke(B, "enableEventPersistence", new Object[]{ a[2] }, new String[]{ "java.lang.String" });
                    System.out.println("ENABLE-OK " + a[2]);
                    break;
                case "disable":
                    m.invoke(B, "disableEventPersistence", new Object[]{ a[2] }, new String[]{ "java.lang.String" });
                    System.out.println("DISABLE-OK " + a[2]);
                    break;
                case "read":
                {
                    SortedMap<Long, Map<String, ?>> r = read(m, a[2], 0L);
                    long ob = 0;
                    for (Map<String, ?> e : r.values()) { Object o = e.get("operation"); if (o != null) ob += o.toString().length(); }
                    System.out.println("READ " + a[2] + " count=" + r.size() + " minKey=" + (r.isEmpty() ? -1 : r.firstKey()) + " maxKey=" + (r.isEmpty() ? -1 : r.lastKey()) + " opBytes=" + ob);
                    break;
                }
                case "heap":
                    System.out.println("HEAPUSED " + ((CompositeData) m.getAttribute(new ObjectName("java.lang:type=Memory"), "HeapMemoryUsage")).get("used"));
                    break;
                case "drain":
                {
                    long ms = Long.parseLong(a[3]);
                    File stop = new File(a[4]);
                    List<Map<String, ?>> kept = new ArrayList<>();
                    long last = 0;
                    int k = 0;
                    while (!stop.exists())
                    {
                        SortedMap<Long, Map<String, ?>> r = read(m, a[2], last);
                        for (Map.Entry<Long, Map<String, ?>> e : r.entrySet()) { kept.add(e.getValue()); last = Math.max(last, e.getKey()); }
                        if (++k % 20 == 0) { System.out.println("DRAIN retained=" + kept.size() + " last=" + last); System.out.flush(); }
                        Thread.sleep(ms);
                    }
                    System.out.println("DRAIN-FINAL retained=" + kept.size() + " last=" + last);
                    break;
                }
                default:
                    throw new IllegalArgumentException(a[1]);
            }
        }
    }
}
