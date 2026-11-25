import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.io.sstable.Descriptor;
import org.apache.cassandra.db.lifecycle.LifecycleTransaction;
import org.apache.cassandra.db.Directories;
public class DiagList {
  public static void main(String[] a) throws Exception {
    DatabaseDescriptor.clientInitialization(false);
    File f = new File(a[0]);
    try { System.out.println("parsed: " + Descriptor.fromFileWithComponent(f)); } catch (Throwable t) { t.printStackTrace(System.out); }
    System.out.println("files: " + LifecycleTransaction.getFiles(new File(a[1]).toPath(), (x, y) -> { System.out.println(" " + y + " " + x); return true; }, Directories.OnTxnErr.IGNORE).size());
    System.exit(0);
  }
}
