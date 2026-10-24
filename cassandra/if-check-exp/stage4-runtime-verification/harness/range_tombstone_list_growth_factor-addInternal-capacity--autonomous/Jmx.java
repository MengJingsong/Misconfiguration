import java.io.File;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness for range_tombstone_list_growth_factor (all three files). Node on 127.0.0.1, JMX port = first argument, no auth.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]        prints bean|attr|value per pair
 *   java Jmx <port> setdouble <bean> <set<Name>> <value>        sets the write-only attribute <Name> (the MBean's set<Name>(double)) and prints OK or the exception
 *   java Jmx <port> poll <ms> <stopfile> <bean> <attr> ...       one connection: every <ms> ms prints "<epoch ms>,<v1>,<v2>,..." until <stopfile> exists
 * Derived from the Jmx.java of the max_mutation_size harness (get, poll); setdouble added.
 */
public class Jmx
{
    static Object value(MBeanServerConnection m, String bean, String attr) throws Exception
    {
        Object v = m.getAttribute(new ObjectName(bean), attr);
        if (v instanceof CompositeData)
            return ((CompositeData) v).get("used");
        return v;
    }

    public static void main(String[] a) throws Exception
    {
        JMXServiceURL u = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + Integer.parseInt(a[0]) + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(u))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            if (a[1].equals("get"))
            {
                for (int i = 2; i + 1 < a.length; i += 2)
                {
                    try { System.out.println(a[i] + "|" + a[i + 1] + "|" + value(m, a[i], a[i + 1])); }
                    catch (Exception e) { System.out.println(a[i] + "|" + a[i + 1] + "|ERROR " + e.getClass().getSimpleName()); }
                }
            }
            else if (a[1].equals("setdouble"))
            {
                try
                {
                    // the MBean's set<Name>(double) with no matching getter is a write-only attribute, not an operation
                    String attr = a[3].startsWith("set") ? a[3].substring(3) : a[3];
                    m.setAttribute(new ObjectName(a[2]), new javax.management.Attribute(attr, Double.valueOf(a[4])));
                    System.out.println("OK set " + attr + "=" + a[4]);
                }
                catch (Exception e)
                {
                    System.out.println("ERROR " + e);
                }
            }
            else if (a[1].equals("poll"))
            {
                long ms = Long.parseLong(a[2]);
                File stop = new File(a[3]);
                while (!stop.exists())
                {
                    long t0 = System.currentTimeMillis();
                    StringBuilder sb = new StringBuilder().append(t0);
                    for (int i = 4; i + 1 < a.length; i += 2)
                    {
                        String v;
                        try { v = String.valueOf(value(m, a[i], a[i + 1])); } catch (Exception e) { v = "ERR"; }
                        sb.append(',').append(v);
                    }
                    System.out.println(sb);
                    System.out.flush();
                    long sl = ms - (System.currentTimeMillis() - t0);
                    if (sl > 0) Thread.sleep(sl);
                }
            }
        }
    }
}
