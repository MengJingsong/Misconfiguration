# Pre-run arithmetic check of B2f/B3f from DataOutputBuffer.calculateNewSize and the BufferedDataOutputStreamPlus write paths.
import sys
MiB=1<<20
def run(T, mode, n, hdr=40):
    cap=128; pos=0; ex=[]
    def flush(count):
        nonlocal cap
        if count<=0: return
        new=cap+count
        if cap > MiB*T: new=max(cap*3//2,new)
        else: new=max(cap*2,new)
        ex.append((count,cap,new)); cap=new
    def wb(L):   # write(byte[])
        nonlocal pos
        copied=0
        while copied<L:
            rem=cap-pos
            if rem>0:
                t=min(L-copied,rem); pos+=t; copied+=t
            else: flush(L-copied)
    def wbb(L):  # write(ByteBuffer)
        nonlocal pos
        srcPos=0
        while L-srcPos > cap-pos:
            a=cap-pos; pos+=a; srcPos+=a; flush(L-srcPos)
        pos+=L-srcPos
    if mode=='bytes':
        for _ in range((n*MiB)//65536): wb(65536)
    else:
        wb(hdr)
        for _ in range(n): wb(12); wbb(MiB)
    return ex,pos,cap
for mode,n in [('bytes',200),('bytes',100),('rows',200),('rows',100)]:
    for T in [0,16,64,128,1024]:
        ex,pos,cap=run(T,mode,n)
        print(f"T={T:5d} {mode}{n}: last-but-one={ex[-1][1]} ({ex[-1][1]/MiB:.2f}) final={cap} ({cap/MiB:.2f}) C/S={cap/pos:.3f} transient={(ex[-1][1]+cap)/MiB:.2f} resizes={len(ex)} written={pos}")
