import org.apache.cassandra.config.DatabaseDescriptor;
public class ConfigProbe {
  public static void main(String[] a) throws Exception {
    try { DatabaseDescriptor.daemonInitialization();
          System.out.println("OK " + a[0] + "=" + DatabaseDescriptor.class.getMethod(a[0]).invoke(null)); }
    catch (Throwable t) { Throwable c = t; while (c.getCause() != null) c = c.getCause();
          System.out.println("REJECT " + t.getClass().getSimpleName() + ": " + t.getMessage() + " / root: " + c); }
  }
}
