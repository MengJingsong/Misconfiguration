// B3e step 2(b), amendment A4: start the HDFS NFS3 gateway (mountd + nfsd) without portmap registration,
// so the node's system rpcbind is left alone. Mount with explicit port=2049,mountport=4242,mountproto=tcp.
import org.apache.hadoop.hdfs.nfs.conf.NfsConfiguration;
import org.apache.hadoop.hdfs.nfs.nfs3.Nfs3;
public class NoRegNfs3 {
  public static void main(String[] args) throws Exception {
    Nfs3 nfs = new Nfs3(new NfsConfiguration());
    nfs.startServiceInternal(false);
    System.out.println("NoRegNfs3 started");
    Thread.currentThread().join();
  }
}
