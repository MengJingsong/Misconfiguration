#!/usr/bin/env python3
"""Disk sampler (case-file B3d, amended A5b).
Usage: python3 -I sampler.py <dir> <out.csv>
Every 100 ms: epoch_ms, count and summed bytes of fs-cache-*.bin files under <dir> (recursive);
every 10th sample also `du -sb <dir>`. Runs until SIGTERM."""
import fnmatch, os, signal, subprocess, sys, time

D, OUT = sys.argv[1], sys.argv[2]
stop = False


def on_term(sig, frm):
    global stop
    stop = True


signal.signal(signal.SIGTERM, on_term)
signal.signal(signal.SIGINT, on_term)


def scan():
    n = b = 0
    for root, dirs, files in os.walk(D):
        for f in files:
            if fnmatch.fnmatch(f, "fs-cache-*.bin"):
                try:
                    b += os.lstat(os.path.join(root, f)).st_size
                    n += 1
                except FileNotFoundError:
                    pass
    return n, b


with open(OUT, "w", buffering=1) as o:
    o.write("epoch_ms,files,bytes,du_bytes\n")
    i = 0
    while not stop:
        t = int(time.time() * 1000)
        n, b = scan()
        du = ""
        if i % 10 == 0:
            r = subprocess.run(["du", "-sb", D], capture_output=True, text=True)
            du = r.stdout.split("\t")[0] if r.returncode == 0 else "err"
        o.write(f"{t},{n},{b},{du}\n")
        i += 1
        time.sleep(max(0.0, 0.1 - (time.time() * 1000 - t) / 1000))
