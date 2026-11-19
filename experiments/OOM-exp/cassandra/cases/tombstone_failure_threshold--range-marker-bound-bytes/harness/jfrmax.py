#!/usr/bin/env python3
# B16 IC: largest ObjectAllocationOutsideTLAB allocation whose stack contains DataOutputBuffer.expandToFit (the response
# buffer growth), plus the count of such allocations and the largest one under LocalDataResponse.  jfrmax.py <file.jfr>
import json, subprocess, sys
out = subprocess.run(['jfr', 'print', '--json', '--events', 'jdk.ObjectAllocationOutsideTLAB', '--stack-depth', '16', sys.argv[1]],
                     capture_output=True, text=True).stdout
ev = json.loads(out)['recording']['events']
best = 0; n = 0; under = 0; sizes = []
for e in ev:
    v = e['values']; st = v.get('stackTrace') or {}
    fr = ['%s.%s' % (f['method']['type']['name'], f['method']['name']) for f in st.get('frames', [])]
    if any('DataOutputBuffer' in x and 'expandToFit' in x for x in fr):
        sz = v['allocationSize']; n += 1; sizes.append(sz); best = max(best, sz)
        if any('LocalDataResponse' in x for x in fr): under = max(under, sz)
print(f'{sys.argv[1]}: events={len(ev)} expandToFit allocs={n} max={best} B ({best/2**20:.1f} MiB) max_under_LocalDataResponse={under/2**20:.1f} MiB '
      f'top sizes MiB={sorted(round(s/2**20,1) for s in sizes)[-6:]}')
