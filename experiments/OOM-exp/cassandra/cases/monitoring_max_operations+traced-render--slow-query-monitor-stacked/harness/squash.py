#!/usr/bin/env python3
"""squash.py: stdin -> stdout, every run of >= 64 hex digits [0-9a-f] replaced by 'H' (so the monitor's uncut 32 MB
names can be grepped quickly). Streams in 16 MiB chunks."""
import re, sys
RX = re.compile(rb'[0-9a-f]{64,}')
inp = sys.stdin.buffer; out = sys.stdout.buffer; carry = b''
while True:
    b = inp.read(1 << 24)
    if not b:
        out.write(RX.sub(b'H', carry)); break
    b = carry + b
    m = re.search(rb'[^0-9a-f][0-9a-f]*\Z', b)
    cut = m.start() + 1 if m else 0
    head, tail = b[:cut], b[cut:]
    out.write(RX.sub(b'H', head))
    carry = tail if len(tail) < 64 else b'a' * 64
out.flush()
