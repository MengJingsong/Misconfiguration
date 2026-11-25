#!/usr/bin/env python3
# B3c workload. Usage: oow.py <path> <nblocks_after_0> <blocksize> <hold_s> [ooo|seq]
#  ooo: pwrite blocks k = 1..N in ascending order (offset 0 left as a hole), HOLD, sleep hold_s,
#       pwrite block 0, fsync, close.
#  seq: pwrite blocks k = 0..N ascending, HOLD, sleep hold_s, fsync, close.
# Prints the md5 of the whole file content (blocks 0..N in file order).
import hashlib, os, sys, time
path, n, bs, hold = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
mode = sys.argv[5] if len(sys.argv) > 5 else "ooo"
blocks = [os.urandom(bs) for _ in range(n + 1)]
md5 = hashlib.md5()
for b in blocks:
    md5.update(b)
print("MD5 %s bytes %d" % (md5.hexdigest(), bs * (n + 1)), flush=True)
fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o644)
t0 = time.time()
print("START %.3f mode %s" % (t0, mode), flush=True)
order = range(1, n + 1) if mode == "ooo" else range(0, n + 1)
for j, k in enumerate(order, 1):
    assert os.pwrite(fd, blocks[k], k * bs) == bs
    if j % 512 == 0:
        print("PROGRESS %d writes %.1fs" % (j, time.time() - t0), flush=True)
print("HOLD %.3f after %d writes in %.1fs" % (time.time(), len(order), time.time() - t0), flush=True)
time.sleep(hold)
print("HOLDEND %.3f" % time.time(), flush=True)
if mode == "ooo":
    assert os.pwrite(fd, blocks[0], 0) == bs
os.fsync(fd)
os.close(fd)
print("DONE %.3f total %.1fs" % (time.time(), time.time() - t0), flush=True)
