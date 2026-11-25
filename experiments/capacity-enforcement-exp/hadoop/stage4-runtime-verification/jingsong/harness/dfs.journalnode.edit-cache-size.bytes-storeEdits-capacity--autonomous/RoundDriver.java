// Stage-4 harness, order 20 (dfs.journalnode.edit-cache-size.bytes), cluster tier B3c workload (amendment AM5).
// Runs B3c rounds through org.apache.hadoop.fs.FsShell -- the class behind `hdfs dfs` -- in one JVM, so a round
// does not pay two JVM launches. One round = `-mkdir -p` of 50 deep paths (/w/p$j + 28 x /a{250}) then
// `-rm -r -skipTrash /w`, exactly the B3c commands. Usage: RoundDriver <firstRound> <rounds>
import java.util.ArrayList;
import java.util.List;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FsShell;
import org.apache.hadoop.hdfs.HdfsConfiguration;
import org.apache.hadoop.util.ToolRunner;

public class RoundDriver {
  public static void main(String[] a) throws Exception {
    int first = Integer.parseInt(a[0]);
    int rounds = Integer.parseInt(a[1]);
    StringBuilder comp = new StringBuilder();
    for (int i = 0; i < 250; i++) {
      comp.append('a');
    }
    String A = comp.toString();
    List<String> mk = new ArrayList<>();
    mk.add("-mkdir");
    mk.add("-p");
    for (int j = 1; j <= 50; j++) {
      StringBuilder p = new StringBuilder("/w/p" + j);
      for (int k = 0; k < 28; k++) {
        p.append('/').append(A);
      }
      mk.add(p.toString());
    }
    String[] mkArgs = mk.toArray(new String[0]);
    String[] rmArgs = {"-rm", "-r", "-skipTrash", "/w"};
    Configuration conf = new HdfsConfiguration();
    for (int r = first; r < first + rounds; r++) {
      long t0 = System.currentTimeMillis();
      int rc1 = ToolRunner.run(new FsShell(conf), mkArgs);
      int rc2 = ToolRunner.run(new FsShell(conf), rmArgs);
      System.out.println("ROUND " + r + " mkdir_rc=" + rc1 + " rm_rc=" + rc2 + " ms="
          + (System.currentTimeMillis() - t0) + " pathLen=" + mkArgs[2].length());
      if (rc1 != 0 || rc2 != 0) {
        System.exit(2);
      }
    }
  }
}
