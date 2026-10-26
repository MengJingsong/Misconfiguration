import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.openmbean.CompositeData;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Node on 127.0.0.1, JMX port = first argument, no auth.
 *   java Jmx <port> get <bean> <attr> [<bean> <attr> ...]     prints bean|attr|value (CompositeData prints its "used" item)
 *   java Jmx <port> setrf <warn> <fail>                       GuardrailsMBean.setMaximumReplicationFactorThreshold(warn, fail), then prints the two getters
 * Written for maximum_replication_factor-ReplicaList.add-newSize--autonomous (pattern of the other stage-4 Jmx.java files).
 */
public class Jmx
{
    static final String G = "org.apache.cassandra.db:type=Guardrails";

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
                    Object v = m.getAttribute(new ObjectName(a[i]), a[i + 1]);
                    if (v instanceof CompositeData) v = ((CompositeData) v).get("used");
                    System.out.println(a[i] + "|" + a[i + 1] + "|" + v);
                }
            }
            else if (a[1].equals("setrf"))
            {
                m.invoke(new ObjectName(G), "setMaximumReplicationFactorThreshold",
                         new Object[]{ Integer.parseInt(a[2]), Integer.parseInt(a[3]) }, new String[]{ "int", "int" });
                System.out.println("warn|" + m.getAttribute(new ObjectName(G), "MaximumReplicationFactorWarnThreshold"));
                System.out.println("fail|" + m.getAttribute(new ObjectName(G), "MaximumReplicationFactorFailThreshold"));
            }
            else
                throw new IllegalArgumentException(a[1]);
        }
    }
}
