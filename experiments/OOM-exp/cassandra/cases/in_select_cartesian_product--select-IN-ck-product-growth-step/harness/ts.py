#!/usr/bin/env python3
# R14: prefix every stdin line with the wall clock (epoch s, ms precision) and append to the file in argv[1].
import sys, time
out = open(sys.argv[1], 'a', buffering=1)
for line in sys.stdin:
    out.write('%.3f %s' % (time.time(), line))
