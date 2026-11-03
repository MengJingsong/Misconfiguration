// Stage-4 harness (repair_session_space-initHelper-max--autonomous, C2): minimal JMX attribute client.
// usage: java JmxAttr <port> get <objectName> <attribute>
//        java JmxAttr <port> set <objectName> <attribute> <int>     (sets, then prints the value read back)
// Prints "<attribute>=<value>"; exits 1 on any error.
import javax.management.Attribute;
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class JmxAttr
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://127.0.0.1:" + a[0] + "/jmxrmi");
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection m = c.getMBeanServerConnection();
            ObjectName on = new ObjectName(a[2]);
            if (a[1].equals("set"))
                m.setAttribute(on, new Attribute(a[3], Integer.parseInt(a[4])));
            System.out.println(a[3] + "=" + m.getAttribute(on, a[3]));
        }
        catch (Exception e)
        {
            System.out.println("ERROR " + e);
            System.exit(1);
        }
    }
}
