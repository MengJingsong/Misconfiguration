#!/usr/bin/env python3
"""JMX helper for the stage-4 cluster tier (B3d, A4.4). No jq on the node.

  jmxtool.py get <url> <attr>                      print one attribute of the first bean (or NA)
  jmxtool.py sample <out.csv> <nn_url> <jn_url> <stopfile>
      every 2 s: epoch_ms,QueuedEditsSize,IsOutOfSync,CurrentLagTxns,jn1BytesWritten
"""
import json
import os
import sys
import time
import urllib.request


def bean(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        b = json.load(r).get("beans", [])
    return b[0] if b else {}


def attr(url, name):
    try:
        v = bean(url).get(name)
        return "NA" if v is None else str(v)
    except Exception:
        return "ERR"


def main():
    if sys.argv[1] == "get":
        print(attr(sys.argv[2], sys.argv[3]))
        return
    if sys.argv[1] == "sample":
        out, nn, jn, stop = sys.argv[2:6]
        with open(out, "a") as f:
            if os.path.getsize(out) == 0:
                f.write("epoch_ms,QueuedEditsSize,IsOutOfSync,CurrentLagTxns,jn1BytesWritten\n")
            nxt = time.time()
            while not os.path.exists(stop):
                t = int(time.time() * 1000)
                try:
                    b = bean(nn)
                    q = b.get("QueuedEditsSize", "NA")
                    o = b.get("IsOutOfSync", "NA")
                    lag = b.get("CurrentLagTxns", "NA")
                except Exception:
                    q = o = lag = "ERR"
                w = attr(jn, "BytesWritten")
                f.write(f"{t},{q},{o},{lag},{w}\n")
                f.flush()
                nxt += 2.0
                time.sleep(max(0.0, nxt - time.time()))
        return
    sys.exit("usage")


if __name__ == "__main__":
    main()
