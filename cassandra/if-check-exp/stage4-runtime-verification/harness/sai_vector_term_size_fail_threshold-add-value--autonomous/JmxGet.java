/*
 * Stage-4 harness (amendment B3d) of sai_vector_term_size_fail_threshold-add-value--autonomous. Not upstream code.
 * usage: java JmxGet.java <host:port> <attribute> <objectName> [<objectName> ...]
 * Prints one line per object name: "<objectName> <attribute>=<value>" or "<objectName> ERROR <exception>".
 * Exit code 0 only if every read succeeded.
 */
import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnector;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

public class JmxGet
{
    public static void main(String[] a) throws Exception
    {
        JMXServiceURL url = new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi");
        int rc = 0;
        try (JMXConnector c = JMXConnectorFactory.connect(url))
        {
            MBeanServerConnection s = c.getMBeanServerConnection();
            for (int i = 2; i < a.length; i++)
            {
                try
                {
                    System.out.println(a[i] + " " + a[1] + "=" + s.getAttribute(new ObjectName(a[i]), a[1]));
                }
                catch (Exception e)
                {
                    System.out.println(a[i] + " ERROR " + e);
                    rc = 1;
                }
            }
        }
        System.exit(rc);
    }
}
