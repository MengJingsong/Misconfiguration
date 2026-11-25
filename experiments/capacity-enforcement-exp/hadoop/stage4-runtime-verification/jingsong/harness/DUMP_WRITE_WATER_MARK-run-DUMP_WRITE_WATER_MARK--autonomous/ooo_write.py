#!/usr/bin/env python3
import os, mmap, time, argparse
p = argparse.ArgumentParser()
p.add_argument('--dir', required=True); p.add_argument('--files', type=int, default=1)
p.add_argument('--chunk', type=int, default=65536); p.add_argument('--chunks', type=int, default=12288)
p.add_argument('--checkpoint-sleep', type=int, default=20); p.add_argument('--pause', type=int, default=60)
a = p.parse_args()
buf = mmap.mmap(-1, a.chunk); buf.write(b'\xab' * a.chunk)          # page-aligned buffer
fds = [os.open(os.path.join(a.dir, 'f%03d' % i), os.O_WRONLY | os.O_CREAT | os.O_DIRECT, 0o644)
       for i in range(a.files)]
marks = {int(a.chunks * q) for q in (0.75, 0.5, 0.25)}
for k in range(a.chunks - 1, 0, -1):                                   # chunk 0 held back
    for fd in fds:
        assert os.pwrite(fd, buf, k * a.chunk) == a.chunk
    if k in marks:
        print(time.strftime('%T'), 'CHECKPOINT k=%d' % k, flush=True); time.sleep(a.checkpoint_sleep)
print(time.strftime('%T'), 'PAUSE all out-of-order chunks sent', flush=True); time.sleep(a.pause)
for fd in fds:
    os.pwrite(fd, buf, 0); os.close(fd)                                # fill the hole -> write-back
print(time.strftime('%T'), 'DONE', flush=True)
