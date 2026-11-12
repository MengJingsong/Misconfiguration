// Known-answer check for jfr-parse.py (not a case reading): 5 threads each allocate one 3 MiB byte[]
// inside a method named retrieveTemporaryBuffer; one 2 MiB byte[] is allocated elsewhere.
public class JfrParseCheck
{
    static byte[][] keep = new byte[6][];
    static byte[] retrieveTemporaryBuffer(int n) { return new byte[n]; }
    public static void main(String[] a) throws Exception
    {
        Thread[] ts = new Thread[5];
        for (int i = 0; i < 5; i++) { final int id = i; ts[i] = new Thread(() -> keep[id] = retrieveTemporaryBuffer(3 << 20)); ts[i].start(); }
        for (Thread t : ts) t.join();
        keep[5] = new byte[2 << 20];
        System.out.println("done");
    }
}
