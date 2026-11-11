/*
 * Stage-4 harness (if-check-exp, Hadoop, Jingsong's share) for the case
 *   DF_getAvailable-getLocalPathForWrite-maxCapacity--autonomous
 * Unit tier B2 (amended A1-A5): drives LocalDirAllocator.getLocalPathForWrite(path, size, conf)
 * with known sizes against one or two directories on small loop filesystems, and records, per call,
 * the outcome (directory index or exception), the number after "is" in the failure message, the
 * usable space of each directory before and after the call, and the size of what was written.
 *
 * Inputs (environment, inherited by the surefire fork): LDA_DIR0, LDA_DIR1, LDA_OUT (CSV path),
 * LDA_VARIANT (baseline | ablated, a label only). Copied into
 * hadoop-common-project/hadoop-common/src/test/java/org/apache/hadoop/fs/ of each source copy.
 * Not upstream code; never added to the repository's systems/hadoop/source/.
 */
package org.apache.hadoop.fs;

import java.io.BufferedReader;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.util.DiskChecker.DiskErrorException;
import org.apache.log4j.Level;
import org.apache.log4j.Logger;
import org.junit.Test;

import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertTrue;

public class TestLdaMaxCapacity {
  private static final String CTX = "test.lda.ctx";
  private static final long MIB = 1024L * 1024L;
  private static final int CALLS = 200;
  private static final Pattern MSG_N =
      Pattern.compile("max capacity in any directory \\(.*\\) is (\\d+)");

  private static long du(File d) throws Exception {
    Process p = new ProcessBuilder("du", "-sb", d.getPath()).redirectErrorStream(true).start();
    try (BufferedReader r = new BufferedReader(new InputStreamReader(p.getInputStream()))) {
      String l = r.readLine();
      p.waitFor();
      return Long.parseLong(l.split("\\s+")[0]);
    }
  }

  private static void deleteChildren(File d) throws Exception {
    File[] kids = d.listFiles();
    if (kids == null) {
      return;
    }
    for (File k : kids) {
      FileUtil.fullyDelete(k);
    }
  }

  private static long writeBytes(File f, long n) throws Exception {
    byte[] buf = new byte[(int) MIB];
    long left = n;
    try (FileOutputStream os = new FileOutputStream(f)) {
      while (left > 0) {
        int c = (int) Math.min(buf.length, left);
        os.write(buf, 0, c);
        left -= c;
      }
      os.getFD().sync();
    }
    return Files.size(f.toPath());
  }

  @Test(timeout = 1800000)
  public void run() throws Exception {
    String d0 = System.getenv("LDA_DIR0");
    String d1 = System.getenv("LDA_DIR1");
    String out = System.getenv("LDA_OUT");
    String variant = System.getenv("LDA_VARIANT");
    assertNotNull("LDA_DIR0", d0);
    assertNotNull("LDA_DIR1", d1);
    assertNotNull("LDA_OUT", out);
    Logger.getLogger(LocalDirAllocator.class).setLevel(Level.DEBUG);
    File f0 = new File(d0);
    File f1 = new File(d1);
    assertTrue(f0.isDirectory() && f1.isDirectory());
    File[] all = {f0, f1};
    String[][] sets = {{d0}, {d0, d1}};
    String[] labels = {"1k", "min-64M", "max-64M", "max+64M", "longmax-1"};
    int failedWrites = 0;
    try (PrintWriter csv = new PrintWriter(out, "UTF-8")) {
      csv.println("variant,k3,block,label,size,call,outcome,dir,msgN,a0Before,a1Before,"
          + "a0After,a1After,written,fileSize");
      int block = 0;
      for (String[] set : sets) {
        String k3 = set.length == 1 ? "dir0" : "dir0+dir1";
        Configuration conf = new Configuration();
        conf.set(CTX, String.join(",", set));
        for (String label : labels) {
          block++;
          long min = Long.MAX_VALUE;
          long max = 0;
          for (String s : set) {
            long a = new File(s).getUsableSpace();
            min = Math.min(min, a);
            max = Math.max(max, a);
          }
          long size;
          switch (label) {
            case "1k": size = 1024; break;
            case "min-64M": size = min - 64 * MIB; break;
            case "max-64M": size = max - 64 * MIB; break;
            case "max+64M": size = max + 64 * MIB; break;
            default: size = Long.MAX_VALUE - 1; break;
          }
          System.out.printf("LDA block %d %s k3=%s size=%d min=%d max=%d%n",
              block, label, k3, size, min, max);
          boolean largeWritten = false;
          for (int i = 0; i < CALLS; i++) {
            long a0b = f0.getUsableSpace();
            long a1b = f1.getUsableSpace();
            String outcome;
            int dir = -1;
            String msgN = "";
            long written = 0;
            long fileSize = -1;
            try {
              Path p = new LocalDirAllocator(CTX).getLocalPathForWrite("f/x" + i, size, conf);
              String ps = p.toUri().getPath();
              for (int k = 0; k < all.length; k++) {
                if (ps.startsWith(all[k].getPath() + "/")) {
                  dir = k;
                }
              }
              outcome = "ok";
              long n = 0;
              if (size <= 64 * MIB) {
                n = 2 * size;
              } else if (!largeWritten) {
                n = size + 32 * MIB;
                largeWritten = true;
              }
              if (n > 0) {
                File wf = new File(ps);
                try {
                  fileSize = writeBytes(wf, n);
                  written = n;
                } catch (Exception we) {
                  failedWrites++;
                  outcome = "ok-writefail";
                  System.out.println("LDA writefail block " + block + " call " + i + ": " + we);
                }
                if (size > 64 * MIB) {
                  FileUtil.fullyDelete(wf);
                }
              }
            } catch (DiskErrorException e) {
              outcome = "DiskErrorException";
              Matcher m = MSG_N.matcher(String.valueOf(e.getMessage()));
              if (m.find()) {
                msgN = m.group(1);
              }
              if (i == 0) {
                System.out.println("LDA msg block " + block + ": " + e.getMessage());
              }
            }
            long a0a = f0.getUsableSpace();
            long a1a = f1.getUsableSpace();
            csv.printf("%s,%s,%d,%s,%d,%d,%s,%d,%s,%d,%d,%d,%d,%d,%d%n", variant, k3, block,
                label, size, i, outcome, dir, msgN, a0b, a1b, a0a, a1a, written, fileSize);
          }
          System.out.printf("LDA du block %d dir0=%d dir1=%d%n", block, du(f0), du(f1));
          deleteChildren(f0);
          deleteChildren(f1);
          Thread.sleep(500);
        }
      }
    }
    System.out.println("LDA done failedWrites=" + failedWrites);
  }
}
