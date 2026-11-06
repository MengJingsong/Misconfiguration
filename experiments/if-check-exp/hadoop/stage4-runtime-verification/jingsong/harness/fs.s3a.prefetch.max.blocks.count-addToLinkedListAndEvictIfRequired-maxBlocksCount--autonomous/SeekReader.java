/*
 * Stage-4 cluster tier workload (case-file B3a/B3c, amended A5a) for
 * fs.s3a.prefetch.max.blocks.count-addToLinkedListAndEvictIfRequired-maxBlocksCount--autonomous.
 * Usage: hadoop jar seekreader.jar SeekReader [-D k=v ...] <s3a path> <holdSeconds>
 * For b = 0 .. numBlocks-1: seek(b * blockSize + 100), read 4096 bytes, sleep 200 ms.
 * Then hold the stream open, print IFCHK,stats and the IOStatistics, close.
 */
import java.io.InputStream;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.conf.Configured;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.FileStatus;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.fs.statistics.IOStatistics;
import org.apache.hadoop.fs.statistics.IOStatisticsLogging;
import org.apache.hadoop.fs.statistics.IOStatisticsSupport;
import org.apache.hadoop.util.Tool;
import org.apache.hadoop.util.ToolRunner;

public class SeekReader extends Configured implements Tool {

  private static long val(IOStatistics st, String name) {
    if (st == null) {
      return -2;
    }
    Long v = st.gauges().get(name);
    if (v == null) {
      v = st.counters().get(name);
    }
    return v == null ? -1 : v;
  }

  @Override
  public int run(String[] args) throws Exception {
    Path p = new Path(args[0]);
    int hold = Integer.parseInt(args[1]);
    Configuration conf = getConf();
    String n = conf.get("fs.s3a.prefetch.max.blocks.count", "unset");
    long blockSize = conf.getLongBytes("fs.s3a.prefetch.block.size", 8L * 1024 * 1024);
    FileSystem fs = p.getFileSystem(conf);
    FileStatus st = fs.getFileStatus(p);
    long numBlocks = (st.getLen() + blockSize - 1) / blockSize;
    System.out.println("IFCHK,start," + n + "," + st.getLen() + "," + blockSize + "," + numBlocks
        + ",streamType=" + conf.get("fs.s3a.input.stream.type") + ",bufferDir="
        + conf.get("fs.s3a.buffer.dir") + "," + System.currentTimeMillis());
    byte[] buf = new byte[4096];
    try (FSDataInputStream in = fs.open(p)) {
      InputStream wrapped = in.getWrappedStream();
      System.out.println("IFCHK,stream," + wrapped.getClass().getName());
      int readErrors = 0;
      for (long b = 0; b < numBlocks; b++) {
        // A9: a read that throws (eviction/get race) is logged and retried, up to 3 attempts per block.
        for (int attempt = 1; attempt <= 3; attempt++) {
          try {
            in.seek(b * blockSize + 100);
            int got = 0;
            while (got < buf.length) {
              int r = in.read(buf, got, buf.length - got);
              if (r < 0) {
                break;
              }
              got += r;
            }
            break;
          } catch (java.io.IOException e) {
            readErrors++;
            System.out.println("IFCHK,readerror," + b + "," + attempt + "," + e);
            if (attempt == 3) {
              throw e;
            }
          }
        }
        Thread.sleep(200);
      }
      System.out.println("IFCHK,readerrors," + readErrors);
      System.out.println("IFCHK,loopdone," + System.currentTimeMillis());
      Thread.sleep(hold * 1000L);
      IOStatistics ios = IOStatisticsSupport.retrieveIOStatistics(in);
      System.out.println("IFCHK,stats," + n + "," + wrapped.getClass().getSimpleName() + ","
          + val(ios, "stream_read_blocks_in_cache") + ","
          + val(ios, "stream_evict_blocks_from_cache") + ","
          + val(ios, "stream_file_cache_eviction") + "," + System.currentTimeMillis());
      System.out.println("IOSTATS " + IOStatisticsLogging.ioStatisticsToPrettyString(ios));
    }
    System.out.println("IFCHK,closed," + System.currentTimeMillis());
    return 0;
  }

  public static void main(String[] args) throws Exception {
    System.exit(ToolRunner.run(new Configuration(), new SeekReader(), args));
  }
}
