import org.apache.cassandra.config.DatabaseDescriptor;
import org.apache.cassandra.io.util.File;
import org.apache.cassandra.db.Directories;
import org.apache.cassandra.cql3.statements.schema.CreateTableStatement;
import org.apache.cassandra.schema.TableMetadata;
public class DiagList2 {
  public static void main(String[] a) throws Exception {
    DatabaseDescriptor.clientInitialization(false);
    TableMetadata md = CreateTableStatement.parse("CREATE TABLE s4ks.t_m16 (k int PRIMARY KEY, v blob)", "s4ks").build();
    Directories d = new Directories(md, new Directories.DataDirectory[]{ new Directories.DataDirectory(new File("/tmp/diag-o117-unused")) });
    System.out.println("list(true): " + d.sstableLister(new File(a[0]), Directories.OnTxnErr.IGNORE).skipTemporary(true).list(true).keySet());
    System.exit(0);
  }
}
