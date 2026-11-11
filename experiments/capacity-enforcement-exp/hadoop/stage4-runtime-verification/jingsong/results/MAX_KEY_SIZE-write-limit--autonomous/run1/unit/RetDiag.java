import org.apache.hadoop.io.BoundedByteArrayOutputStream;
public class RetDiag {
  static long used(){ for(int i=0;i<3;i++) System.gc(); Runtime r=Runtime.getRuntime(); return r.totalMemory()-r.freeMemory(); }
  public static void main(String[] a){
    int[] caps={65536,65536,65536,1048576,1048576,1048576,16777216,16777216,16777216};
    for(int c:caps){
      long u0=used(); long t0=Runtime.getRuntime().totalMemory();
      BoundedByteArrayOutputStream s=new BoundedByteArrayOutputStream(c);
      long u1=used(); long t1=Runtime.getRuntime().totalMemory();
      System.out.println("C="+c+" u0="+u0+" u1="+u1+" delta="+(u1-u0)+" total0="+t0+" total1="+t1+" len="+s.getBuffer().length);
      s=null;
    }
  }
}
