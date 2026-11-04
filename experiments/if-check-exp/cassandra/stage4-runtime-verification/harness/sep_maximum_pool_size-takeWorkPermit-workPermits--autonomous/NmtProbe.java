import java.util.concurrent.locks.LockSupport;
public class NmtProbe {
  public static void main(String[] a) throws Exception {
    int n = Integer.parseInt(a[0]);
    System.out.println("READY0"); System.out.flush(); Thread.sleep(Long.parseLong(a[1]));
    for (int i = 0; i < n; i++) { Thread t = new Thread(() -> { while (true) LockSupport.park(); }); t.setDaemon(true); t.start(); }
    System.out.println("READY1"); System.out.flush(); Thread.sleep(600000);
  }
}
