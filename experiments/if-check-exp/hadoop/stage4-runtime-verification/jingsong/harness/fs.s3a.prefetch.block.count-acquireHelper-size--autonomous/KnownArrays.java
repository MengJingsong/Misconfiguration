/* Instrument check for hprof_count.py and the histogram parser (stage-4 harness): holds <count> byte[<len>] and sleeps. */
public class KnownArrays {
  public static void main(String[] a) throws Exception {
    int n = Integer.parseInt(a[0]), len = Integer.parseInt(a[1]);
    byte[][] keep = new byte[n][];
    for (int i = 0; i < n; i++) keep[i] = new byte[len];
    System.out.println("holding " + n + " x " + len);
    Thread.sleep(Long.parseLong(a[2]) * 1000);
    System.out.println(keep.length);
  }
}
