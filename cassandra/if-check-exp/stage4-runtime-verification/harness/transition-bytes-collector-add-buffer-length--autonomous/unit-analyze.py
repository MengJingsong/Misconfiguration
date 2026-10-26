#!/usr/bin/env python3
"""Analyzer of the unit tier of transition-bytes-collector-add-buffer-length--autonomous. usage: unit-analyze.py <dir with tc-unit*.txt>
Prints EXPECTED:/OBSERVED lines for B2f (1)-(3), the controls of B2h, and the matched B2g row. Exit 0 always (the lines carry the verdict)."""
import glob, os, re, sys
d = sys.argv[1]
files = sorted(glob.glob(os.path.join(d, 'tc-unit*.txt')))
rows = []
for f in files:
    for l in open(f):
        if l.startswith('TC '):
            kind, *rest = l[3:].split()
            kv = dict(x.split('=', 1) for x in rest if '=' in x)
            kv['_kind'] = kind; kv['_file'] = os.path.basename(f)
            rows.append(kv)
res = []
def chk(name, ok, detail):
    res.append(ok)
    print(f"EXPECTED: {name}: {'HOLDS' if ok else 'FAILS'}  [{detail}]")
by = lambda k: [r for r in rows if r['_kind'] == k]
print('files:', ', '.join(os.path.basename(f) for f in files), 'rows:', len(rows))
print('env:', [r for r in by('env')][:3] and [(r['_file'], r.get('xmx'), r.get('lucene')) for r in by('env')])

sa = [r for r in by('standalone') if r['thr'] != 'none']
bad = []
caps = {}
for r in sa:
    L, cap, pos = int(r['L']), int(r['cap']), int(r['pos'])
    caps.setdefault(L, set()).add(cap)
    band = (cap == 32) if L <= 32 else (L <= cap <= L + L // 8 + 10)
    if not band or cap != int(r['sim_cap']) or pos != L or int(r['pos_after_pop']) != 0 or int(r['cap_after_pop']) != cap:
        bad.append((L, cap, r['sim_cap'], pos))
chk('B2f(1) standalone capacity in band (32 if L<=32 else L..L+L/8+10), equals the library simulation, pos=L, pos 0 after pops', not bad and sa, f'{len(sa)} readings, violations {bad[:3]}')
chk('B2f(1) one capacity per L across guardrail values, repetitions, -Xmx runs', all(len(v) == 1 for v in caps.values()) and caps,
    '; '.join(f'L={L}:{sorted(v)}' for L, v in sorted(caps.items())))
big = [r for r in by('standalone') if r['thr'] == 'none']
chk('B2f(1) no cap beyond 65535 (131072 and 1048576 adds, no exception, capacity = library simulation)', len(big) >= 2 and all(int(r['cap']) == int(r['sim_cap']) and int(r['pos']) == int(r['L']) for r in big),
    '; '.join(f"L={r['L']} cap={r['cap']}" for r in big[:2]))
wk = by('walker')
badw = [(r['call'], r['L'], r['alloc_per_call'], r['lower'], r['upper']) for r in wk if not (int(r['lower']) <= int(r['alloc_per_call']) <= int(r['upper'])) or r['result_equals_key'] != 'true']
chk('B2f(2) [auxiliary] getMax/MinTerm allocation within S(L)+L .. S(L)+L+65536 and result equals the key', wk and not badw, f'{len(wk)} readings, violations {badw[:4]}')
it = by('iterator')
badi = [(r['L'], r['cap'], r['sim_cap'], r['entries'], r['value_len']) for r in it if int(r['cap']) != int(r['sim_cap']) or r['entries'] != '1' or r['value_len'] != r['L'] or int(r['pos_after']) not in (0, -1)]
chk('B2f(3) collecting=true iterator: capacity = standalone capacity for the same L, 1 entry, value length L, pos 0 or -1 after drain (the root frame pops without an add)', it and not badi, f'{len(it)} readings, violations {badi[:3]}')
# knob independence is already carried by (1) one capacity per L; list per-file alloc too
# controls
gr = by('guardrail'); badg = []
for r in gr:
    thr = {'1KiB': 1024, '8KiB': 8192, '64KiB': 65536}[r['thr']]
    for k, v in r.items():
        if k.isdigit():
            want = 'FAIL' if int(k) > thr else 'ok'
            if v != want: badg.append((r['thr'], k, v, want))
chk('B2h control: Guardrails.saiStringTermSize.failsOn fails exactly the sizes above the threshold, at 1KiB, 8KiB, 64KiB', len(gr) >= 3 and not badg, f'{len(gr)} readings, violations {badg[:4]}')
na = by('newarray')
chk('B2h control: allocation instrument counts a known array (new byte[L]: L+16 .. L+80 bytes per call)', na and all(int(r['expected']) <= int(r['per_call']) <= int(r['expected']) + 64 for r in na), '; '.join(f"L={r['L']}:{r['per_call']}" for r in na))
nfiles = len({r['_file'] for r in rows})
chk('B2e step 4: tc-unit.txt plus two -Xmx runs present', nfiles >= 3, f'{nfiles} files')
# matched row
core = all(res[:2]) and res[2] and res[4] and res[5] and res[6]
if core and all(res):
    row = 'B2g row 1: capacity depends only on L; same under all guardrail/-Xmx values - claim confirmed'
elif core:
    row = 'B2g band row: knob-independent, but a numeric sub-claim (allocation bound B2f(2)) failed - confirmed on knob-independence, auxiliary sub-claim mis-specified'
elif res[1] is False:
    row = 'B2g row 2: capacity changes with a knob - claim refuted'
else:
    row = 'no B2g row matches (see FAILS above) - Not confirmed (no matching row)'
print('MATCHED:', row)
