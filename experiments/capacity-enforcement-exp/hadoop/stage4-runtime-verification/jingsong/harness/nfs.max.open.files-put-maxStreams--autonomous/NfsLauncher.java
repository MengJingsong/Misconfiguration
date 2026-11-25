/*
 * Stage-4 instrument: B3a "Option C" launcher. Starts the NFS gateway (mountd + nfs3) from the distribution's
 * jars WITHOUT portmapper registration (Nfs3.java:55-58, startServiceInternal(false)), so the host's rpcbind
 * is not touched. Not upstream. In package s4 because `hadoop <class>` rejects a class name without a dot
 * (runbook defect 4, 2026-11-25).
 */
package s4;

import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.hdfs.nfs.nfs3.Nfs3;

public class NfsLauncher {
  public static void main(String[] a) throws Exception {
    Nfs3 n = new Nfs3(new NfsConfiguration());
    n.startServiceInternal(false);
    System.out.println("NFS3 LAUNCHER STARTED (no portmap registration)");
    System.out.flush();
    Thread.sleep(Long.MAX_VALUE);
  }
}
