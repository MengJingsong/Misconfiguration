#!/usr/bin/env python3
"""R20 (case file section 2.5): hold for a C4/I4 run from its T4 run: max(300, 2 x (t_OOM - t_trig) + 60) s, or 600 s if
that T run did not OOM. t_OOM = the driver's first 'OOM line seen' (1-s resolution), t_trig from trigger.txt.
Usage: holdfrom.py <T run dir>  -> prints the hold in s"""
import os, re, sys, datetime as dt
R = sys.argv[1]
drv = open(os.path.join(R, 'driver.txt')).read(); tt = open(os.path.join(R, 'trigger.txt')).read()
m = re.search(r'(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+)(-0700) OOM line seen', drv)
t = re.search(r'^t_trig (\d+) ', tt, re.M)
if not ('oom:' in drv and m and t):
    print(600); sys.exit()
t_oom = dt.datetime.fromisoformat(m.group(1) + '-07:00').timestamp(); t_trig = int(t.group(1)) / 1000
d = max(0.0, t_oom - t_trig)
print(int(round(max(300, 2 * d + 60))))
