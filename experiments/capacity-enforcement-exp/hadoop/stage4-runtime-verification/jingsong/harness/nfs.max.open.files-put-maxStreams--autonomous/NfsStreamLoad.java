/*
 * Stage-4 instrument (capacity-enforcement-exp, Hadoop, Jingsong): load client for the cluster tier (B3) of
 * nfs.max.open.files-put-maxStreams--autonomous. Not upstream.
 *
 * One blocking TCP connection to the NFS gateway (localhost:2049), ONC RPC with AUTH_SYS, using the
 * hadoop-nfs classes (as TestOutOfOrderWrite does). Phase 1: M CREATEs (UNCHECKED) of /nfsload-<runid>-<i>
 * back to back. Phase 2: one UNSTABLE WRITE of <chunk> bytes at <offset> per file. Prints one line per file
 * and a summary, prints SENT, then sleeps <holdSec> and exits.
 *
 * Usage: NfsStreamLoad <M> <chunkBytes> <offset> <runid> <uid> <gid> <holdSec>
 */
import java.io.DataInputStream;
import java.io.DataOutputStream;
import java.io.ByteArrayOutputStream;
import java.io.BufferedOutputStream;
import java.net.Socket;
import java.nio.ByteBuffer;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.hdfs.nfs.nfs3.Nfs3Utils;
import org.apache.hadoop.nfs.nfs3.FileHandle;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant;
import org.apache.hadoop.nfs.nfs3.Nfs3Constant.WriteStableHow;
import org.apache.hadoop.nfs.nfs3.request.CREATE3Request;
import org.apache.hadoop.nfs.nfs3.request.SetAttr3;
import org.apache.hadoop.nfs.nfs3.request.WRITE3Request;
import org.apache.hadoop.oncrpc.RpcAcceptedReply;
import org.apache.hadoop.oncrpc.RpcCall;
import org.apache.hadoop.oncrpc.RpcReply;
import org.apache.hadoop.oncrpc.XDR;
import org.apache.hadoop.oncrpc.security.CredentialsSys;
import org.apache.hadoop.oncrpc.security.VerifierNone;

public class NfsStreamLoad {
  static DataOutputStream out;
  static DataInputStream in;
  static CredentialsSys cred;
  static int xidSeq = 0x5000;

  static XDR header(int proc) {
    XDR x = new XDR();
    RpcCall.getInstance(++xidSeq, Nfs3Constant.PROGRAM, Nfs3Constant.VERSION, proc, cred, new VerifierNone())
        .write(x);
    return x;
  }

  /** Sends one record, returns the reply positioned after the RPC header; null if not accepted/success. */
  static XDR rpc(XDR req) throws Exception {
    byte[] b = req.getBytes();
    out.writeInt(0x80000000 | b.length);
    out.write(b);
    out.flush();
    ByteArrayOutputStream acc = new ByteArrayOutputStream();
    while (true) {
      int mark = in.readInt();
      int len = mark & 0x7fffffff;
      byte[] frag = new byte[len];
      in.readFully(frag);
      acc.write(frag);
      if ((mark & 0x80000000) != 0) {
        break;
      }
    }
    XDR r = new XDR(acc.toByteArray());
    RpcReply reply = RpcReply.read(r);
    if (reply.getXid() != xidSeq) {
      throw new IllegalStateException("xid mismatch " + reply.getXid() + " != " + xidSeq);
    }
    if (!(reply instanceof RpcAcceptedReply)
        || ((RpcAcceptedReply) reply).getAcceptState() != RpcAcceptedReply.AcceptState.SUCCESS) {
      System.out.println("RPC not accepted: " + reply.getState() + " "
          + (reply instanceof RpcAcceptedReply ? ((RpcAcceptedReply) reply).getAcceptState() : ""));
      return null;
    }
    return r;
  }

  public static void main(String[] a) throws Exception {
    int m = Integer.parseInt(a[0]);
    int chunk = Integer.parseInt(a[1]);
    long offset = Long.parseLong(a[2]);
    String runid = a[3];
    int uid = Integer.parseInt(a[4]);
    int gid = Integer.parseInt(a[5]);
    int holdSec = Integer.parseInt(a[6]);

    Configuration conf = new Configuration();
    int nnId = Nfs3Utils.getNamenodeId(conf);
    FileHandle root = new FileHandle(16385L /* INodeId.ROOT_INODE_ID */, nnId);
    cred = new CredentialsSys();
    cred.setUID(uid);
    cred.setGID(gid);
    System.out.println("ARGS M=" + m + " chunk=" + chunk + " offset=" + offset + " runid=" + runid + " uid=" + uid
        + " gid=" + gid + " nnId=" + nnId + " fs=" + conf.get("fs.defaultFS"));

    Socket s = new Socket("localhost", 2049);
    s.setTcpNoDelay(true);
    out = new DataOutputStream(new BufferedOutputStream(s.getOutputStream(), 1 << 20));
    in = new DataInputStream(s.getInputStream());

    FileHandle[] h = new FileHandle[m];
    int[] cst = new int[m];
    int[] wst = new int[m];
    long t1 = System.currentTimeMillis();
    for (int i = 0; i < m; i++) {
      XDR x = header(Nfs3Constant.NFSPROC3.CREATE.getValue());
      new CREATE3Request(root, "nfsload-" + runid + "-" + i, Nfs3Constant.CREATE_UNCHECKED, new SetAttr3(), 0)
          .serialize(x);
      XDR r = rpc(x);
      if (r == null) {
        cst[i] = -2;
        continue;
      }
      cst[i] = r.readInt();
      if (cst[i] == 0 && r.readBoolean()) {
        h[i] = new FileHandle();
        h[i].deserialize(r);
      }
    }
    long t2 = System.currentTimeMillis();
    for (int i = 0; i < m; i++) {
      if (h[i] == null) {
        wst[i] = -3;
        continue;
      }
      XDR x = header(Nfs3Constant.NFSPROC3.WRITE.getValue());
      new WRITE3Request(h[i], offset, chunk, WriteStableHow.UNSTABLE, ByteBuffer.wrap(new byte[chunk])).serialize(x);
      XDR r = rpc(x);
      wst[i] = r == null ? -2 : r.readInt();
    }
    long t3 = System.currentTimeMillis();
    int cOk = 0, wOk = 0, wJb = 0, wOther = 0;
    for (int i = 0; i < m; i++) {
      System.out.println("FILE " + i + " fileId=" + (h[i] == null ? -1 : h[i].getFileId()) + " create_status="
          + cst[i] + " write_status=" + wst[i]);
      if (cst[i] == 0) {
        cOk++;
      }
      if (wst[i] == 0) {
        wOk++;
      } else if (wst[i] == 10008) {
        wJb++;
      } else {
        wOther++;
      }
    }
    System.out.println("SUMMARY createOk=" + cOk + " writeOk=" + wOk + " writeJukebox=" + wJb + " writeOther="
        + wOther + " phase1Ms=" + (t2 - t1) + " phase2Ms=" + (t3 - t2));
    System.out.println("SENT " + System.currentTimeMillis());
    System.out.flush();
    Thread.sleep(holdSec * 1000L);
    s.close();
    System.out.println("EXIT " + System.currentTimeMillis());
  }
}
