import javax.management.MBeanServerConnection;
import javax.management.ObjectName;
import javax.management.remote.JMXConnectorFactory;
import javax.management.remote.JMXServiceURL;

/**
 * Stage-4 harness, cluster tier (amendment C5 (3) of 2026-10-27) of max_concurrent_range_requests-computeConcurrencyFactor-liveReturned--autonomous.
 * (adapted from harness/cached_rows_fail_threshold-queryProtectedPartitions-i--autonomous/RfpJmx.java)
 * usage: java RngJmx host:port <ObjectName>::<Attribute> ...   prints one "<ObjectName>::<Attribute>=<value>" line per argument
 *        (exit 2 on any error)
 */
public class RngJmx
{
    public static void main(String[] a) throws Exception
    {
        MBeanServerConnection m = JMXConnectorFactory.connect(new JMXServiceURL("service:jmx:rmi:///jndi/rmi://" + a[0] + "/jmxrmi")).getMBeanServerConnection();
        int rc = 0;
        for (int i = 1; i < a.length; i++)
        {
            String[] p = a[i].split("::");
            try
            {
                System.out.println(a[i] + "=" + m.getAttribute(new ObjectName(p[0]), p[1]));
            }
            catch (Exception e)
            {
                System.out.println(a[i] + "=ERROR " + e);
                rc = 2;
            }
        }
        System.exit(rc);
    }
}
