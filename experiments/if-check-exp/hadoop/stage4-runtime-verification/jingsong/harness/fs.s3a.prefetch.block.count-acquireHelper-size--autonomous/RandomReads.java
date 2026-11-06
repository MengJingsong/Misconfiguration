/*
 * Stage-4 harness (if-check-exp, Hadoop, Jingsong's share), case fs.s3a.prefetch.block.count-acquireHelper-size--autonomous,
 * cluster tier, amendments A7, A10 and A11 (progress line every 1 s) (package ifchk: `hadoop` accepts only a package-qualified class name): a real S3A client (run with `hadoop RandomReads ...`) that puts the prefetch pool under
 * pressure with random reads, and observes, read-only, the operand createdItems.size() (BoundedResourcePool.java:176) and
 * waits in BufferPool.acquire's retry loop (which continues only when tryAcquire returned null: the check was false).
 *
 * Usage: hadoop ifchk.RandomReads <s3a-uri> <local-copy> <blockCount> <iterations> <readBytes>
 * Prints: IFCHK-RR,n,size,maxCreated,waitSamples,maxCreatedAtWait,bytesRead,mismatches,samples
 */
package ifchk;

import java.io.RandomAccessFile;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.net.URI;
import java.util.Arrays;
import java.util.Random;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;

public class RandomReads {

  static Object field(Object o, String name) throws Exception {
    for (Class<?> c = o.getClass(); c != null; c = c.getSuperclass()) {
      try {
        Field f = c.getDeclaredField(name);
        f.setAccessible(true);
        return f.get(o);
      } catch (NoSuchFieldException e) {
        // try the superclass
      }
    }
    throw new NoSuchFieldException(o.getClass().getName() + "." + name);
  }

  static volatile Object pool;          // BoundedResourcePool of this stream
  static volatile String chain = "";
  static volatile boolean stop;
  static volatile long samples, waitSamples;
  static volatile int maxCreated = -1, maxCreatedAtWait = -1, size = -1;
  static volatile int iter;
  static volatile long bytesDone;
  static volatile int n0;
  static volatile int mism;

  static Object resolve(Object in) throws Exception {
    Object s = in;
    StringBuilder sb = new StringBuilder();
    while (s instanceof FSDataInputStream) {
      sb.append(s.getClass().getName()).append(" > ");
      s = ((FSDataInputStream) s).getWrappedStream();
    }
    sb.append(s.getClass().getName());
    Object inner = field(s, "inputStream");          // S3APrefetchingInputStream.inputStream
    sb.append(" > ").append(inner.getClass().getName());
    Object bm = field(inner, "blockManager");        // S3ACachingInputStream.blockManager
    sb.append(" > ").append(bm.getClass().getName());
    Object bp = field(bm, "bufferPool");             // CachingBlockManager.bufferPool
    Object p = field(bp, "pool");                    // BufferPool.pool
    sb.append(" > ").append(bp.getClass().getName()).append(".pool");
    chain = sb.toString();
    size = (Integer) field(p, "size");
    return p;
  }

  public static void main(String[] args) throws Exception {
    URI uri = new URI(args[0]);
    String local = args[1];
    int n = Integer.parseInt(args[2]);
    int iterations = Integer.parseInt(args[3]);
    int readBytes = Integer.parseInt(args[4]);
    Configuration conf = new Configuration();
    conf.setInt("fs.s3a.prefetch.block.count", n);
    FileSystem fs = FileSystem.newInstance(uri, conf);
    Path path = new Path(uri);
    long len = fs.getFileStatus(path).getLen();
    final Thread main = Thread.currentThread();
    FSDataInputStream in = fs.open(path);
    pool = resolve(in);
    final Method numCreated = pool.getClass().getMethod("numCreated");
    numCreated.setAccessible(true);
    System.out.println("IFCHK-RR-CHAIN," + chain + ",size=" + size + ",len=" + len
        + ",type=" + conf.get("fs.s3a.input.stream.type") + ",blockSize=" + conf.get("fs.s3a.prefetch.block.size"));
    n0 = n;
    Thread sampler = new Thread(() -> {
      long lastPrint = System.nanoTime();
      while (!stop) {
        try {
          int c = (Integer) numCreated.invoke(pool);
          if (c > maxCreated) {
            maxCreated = c;
          }
          StackTraceElement[] st = main.getStackTrace();
          for (int i = 0; i + 1 < st.length; i++) {
            if (st[i].getClassName().equals("org.apache.hadoop.fs.impl.prefetch.Retryer")
                && st[i].getMethodName().equals("continueRetry")
                && st[i + 1].getClassName().equals("org.apache.hadoop.fs.impl.prefetch.BufferPool")
                && st[i + 1].getMethodName().equals("acquire")) {
              waitSamples++;
              if (c > maxCreatedAtWait) {
                maxCreatedAtWait = c;
              }
              break;
            }
          }
          samples++;
          if (System.nanoTime() - lastPrint >= 1_000_000_000L) {   // A11: readings survive a timeout kill
            lastPrint = System.nanoTime();
            System.out.println(String.format("IFCHK-RR-PROGRESS,%d,%d,%d,%d,%d,%d,%d,%d,%d,mainState=%s",
                n0, size, maxCreated, waitSamples, maxCreatedAtWait, iter, bytesDone, mism, samples, main.getState()));
            System.out.flush();
          }
          Thread.sleep(1);
        } catch (Exception e) {
          System.out.println("IFCHK-RR-SAMPLER-ERROR," + e);
          return;
        }
      }
    }, "ifchk-sampler");
    sampler.setDaemon(true);
    sampler.start();

    Random rnd = new Random(20261106L + n);
    byte[] buf = new byte[readBytes];
    byte[] ref = new byte[readBytes];
    long bytes = 0;
    int mismatches = 0;
    try (RandomAccessFile raf = new RandomAccessFile(local, "r")) {
      for (int i = 0; i < iterations; i++) {
        long off = Math.floorMod(rnd.nextLong(), len - readBytes);
        in.seek(off);
        in.readFully(buf, 0, readBytes);
        bytes += readBytes;
        bytesDone = bytes;
        iter = i + 1;
        raf.seek(off);
        raf.readFully(ref, 0, readBytes);
        if (!Arrays.equals(buf, ref)) {
          mismatches++;
          mism = mismatches;
        }
      }
    }
    stop = true;
    sampler.join();
    System.out.println(String.format("IFCHK-RR,%d,%d,%d,%d,%d,%d,%d,%d",
        n, size, maxCreated, waitSamples, maxCreatedAtWait, bytes, mismatches, samples));
    in.close();
    fs.close();
  }
}
