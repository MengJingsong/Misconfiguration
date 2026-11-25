import java.nio.ByteBuffer; import java.nio.file.*; import java.util.*;
import org.apache.hadoop.conf.Configured; import org.apache.hadoop.fs.*;
import org.apache.hadoop.util.*;
import org.apache.hadoop.fs.Path; import org.apache.hadoop.fs.FileSystem; // A9 (2026-11-25)
public class MmapCapProbe extends Configured implements Tool {
  static String snap() throws Exception {
    long n = 0, bytes = 0;
    for (String l : Files.readAllLines(Paths.get("/proc/self/maps"))) {
      if (l.contains("/blk_") && !l.endsWith(".meta")) {
        String[] r = l.split(" ")[0].split("-");
        n++; bytes += Long.parseLong(r[1], 16) - Long.parseLong(r[0], 16);
      }
    }
    String vm = "", rf = "";
    for (String l : Files.readAllLines(Paths.get("/proc/self/status"))) {
      if (l.startsWith("VmSize:")) vm = l.replaceAll("\\s+", " ");
      if (l.startsWith("RssFile:")) rf = l.replaceAll("\\s+", " ");
    }
    return "blkMaps=" + n + " blkMappedBytes=" + bytes + " " + vm + " " + rf;
  }
  public int run(String[] a) throws Exception {
    Path p = new Path(a[0]); int holdSec = Integer.parseInt(a[1]);
    FileSystem fs = p.getFileSystem(getConf());
    FileStatus st = fs.getFileStatus(p);
    long bs = st.getBlockSize(); int nb = (int) (st.getLen() / bs);
    System.out.println("conf dfs.client.mmap.cache.size=" + getConf().get("dfs.client.mmap.cache.size"));
    System.out.println("before " + snap());
    try (FSDataInputStream in = fs.open(p)) {
      for (int i = 0; i < nb; i++) {
        ByteBuffer b = in.read(null, (int) bs, EnumSet.of(ReadOption.SKIP_CHECKSUMS));
        if (b == null || b.remaining() != bs) throw new IllegalStateException("short zero-copy read at " + i);
        long s = 0; for (int o = b.position(); o < b.limit(); o += 4096) s += b.get(o);
        in.releaseBuffer(b);
        System.out.println("step " + i + " sum=" + s + " " + snap());
      }
    }
    System.out.println("after-close " + snap());
    Thread.sleep(holdSec * 1000L);
    System.out.println("end " + snap());
    return 0;
  }
  public static void main(String[] a) throws Exception { System.exit(ToolRunner.run(new MmapCapProbe(), a)); }
}
