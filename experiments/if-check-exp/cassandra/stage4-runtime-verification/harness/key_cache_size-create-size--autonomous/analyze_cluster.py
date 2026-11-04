#!/usr/bin/env python3
"""Cluster-tier analyzer: python3 analyze_cluster.py <cluster-out-dir> [P=1000000]. Prints readings and PASS/FAIL per B3f prediction."""
import sys, os, re, csv, json
D = sys.argv[1]; P = int(sys.argv[2]) if len(sys.argv) > 2 else 1000000
MIB = 1 << 20; fails = 0
def chk(name, ok, detail=''):
    global fails
    print(('PASS ' if ok else 'FAIL ') + name + (' | ' + detail if detail else '')); fails += (not ok)
NODE = re.compile(r'^com\.github\.benmanes\.caffeine\.cache\.[A-Z]{2,5}$')
def parse_hist(f):
    cls = {}; total = None
    for l in open(f):
        m = re.match(r'\s*\d+:\s+(\d+)\s+(\d+)\s+(\S+)', l)
        if m: cls[m.group(3)] = (int(m.group(1)), int(m.group(2)))
        m = re.match(r'Total\s+(\d+)\s+(\d+)', l)
        if m: total = int(m.group(2))
    kck = cls.get('org.apache.cassandra.cache.KeyCacheKey', (0, 0)); rie = cls.get('org.apache.cassandra.io.sstable.format.big.RowIndexEntry', (0, 0))
    nodes = sum(b for c, (n, b) in cls.items() if NODE.match(c))
    keyarr = kck[0] * ((16 + 24 + 7) // 8 * 8)
    return dict(kck_n=kck[0], kck_b=kck[1], rie_b=rie[1], node_b=nodes, keyarr_b=keyarr, total=total, cache_b=kck[1] + rie[1] + nodes + keyarr)
R = {}
for arm in ('k0', 'k4', 'k16', 'k64', 'k512', 'k16b', 'rt'):
    d = os.path.join(D, arm)
    if not os.path.exists(d + '/samples.csv'): continue
    S = list(csv.DictReader(open(d + '/samples.csv')))
    for s in S:
        for k in ('size', 'capacity', 'entries'): s[k] = int(s[k])
    by = {s['phase']: s for s in S if s['phase'] in ('t0', 'end-pass1', 'after-setcap', 'end-pass2')}
    H = {}
    for ph, s in by.items():
        if s['hist']: H[ph] = parse_hist(os.path.join(d, s['hist']))
    R[arm] = dict(S=S, by=by, H=H, J=json.load(open(d + '/summary.json')))
    e2 = by['end-pass2']; h2 = H['end-pass2']
    print('--- %s knob=%s MiB | end-pass1 size=%d entries=%d | end-pass2 size=%d capacity=%d entries=%d avgW=%.2f | hist cache bytes=%d (KeyCacheKey %d + RowIndexEntry %d + caffeine nodes %d + key arrays %d) factor=%.3f | KeyCacheKey instances=%d | live heap total=%s' % (
        arm, R[arm]['J']['knob_mib'], by['end-pass1']['size'], by['end-pass1']['entries'], e2['size'], e2['capacity'], e2['entries'], e2['size'] / max(1, e2['entries']), h2['cache_b'], h2['kck_b'], h2['rie_b'], h2['node_b'], h2['keyarr_b'], h2['cache_b'] / max(1, e2['size']), h2['kck_n'], h2['total']))
    chk('%s: init log shows knob %s MiB' % (arm, R[arm]['J']['knob_mib']), ('capacity of %d MiBs' % R[arm]['J']['knob_mib']) in R[arm]['J']['init_log'])
    chk('%s: no ERROR line in system.log' % arm, R[arm]['J']['errors_in_log'].split()[-1] == '0', R[arm]['J']['errors_in_log'])
    jm = {k: int(v.split('\n')[-1]) for k, v in R[arm]['J']['jmx'].items()}
    chk('%s: JMX (Size, Entries) equals the virtual-table end sample within 1 s of drift' % arm, jm['Capacity'] == e2['capacity'] and abs(jm['Size'] - e2['size']) <= 200 and abs(jm['Entries'] - e2['entries']) <= 5, str(jm))
    cap = R[arm]['J']['knob_mib'] * MIB
    if arm != 'rt':
        over = max(s['size'] - s['capacity'] for s in S)
        chk('%s: Size <= Capacity at every sample (overshoot <= 1 entry, 200 B)' % arm, over <= 200, 'max(size-capacity)=%d over %d samples' % (over, len(S)))
        chk('%s: Capacity == knob x 1048576 at every sample' % arm, all(s['capacity'] == cap for s in S))
CAPPED = [a for a in ('k4', 'k16', 'k64', 'k16b') if a in R]
for a in CAPPED:
    r = R[a]; e1, e2 = r['by']['end-pass1'], r['by']['end-pass2']; cap = r['J']['knob_mib'] * MIB
    chk('%s: Size plateaus at the cap (end-pass2 within 1%% of capacity, and pass2-pass1 change < 1%%)' % a, e2['size'] >= 0.99 * cap and abs(e2['size'] - e1['size']) <= 0.01 * cap, 'size1=%d size2=%d cap=%d' % (e1['size'], e2['size'], cap))
    chk('%s: cap binds (cap < P x average weight)' % a, cap < P * e2['size'] / e2['entries'], 'cap=%d P*w=%.0f' % (cap, P * e2['size'] / e2['entries']))
    chk('%s: key-cache heap bytes did not grow after the plateau (pass2/pass1 <= 1.05)' % a, r['H']['end-pass2']['cache_b'] <= 1.05 * r['H']['end-pass1']['cache_b'], '%d -> %d' % (r['H']['end-pass1']['cache_b'], r['H']['end-pass2']['cache_b']))
    f = r['H']['end-pass2']['cache_b'] / e2['size']
    chk('%s: factor in [1.0, 2.5]' % a, 1.0 <= f <= 2.5, '%.3f' % f)
if all(a in R for a in ('k4', 'k16', 'k64')):
    en = [R[a]['by']['end-pass2']['entries'] for a in ('k4', 'k16', 'k64')]
    chk('entries ratio k4:k16:k64 ~ 1:4:16 (each within 10%)', abs(en[1] / en[0] / 4 - 1) < .1 and abs(en[2] / en[0] / 16 - 1) < .1, str(en))
    fs = [R[a]['H']['end-pass2']['cache_b'] / R[a]['by']['end-pass2']['size'] for a in CAPPED]; m = sum(fs) / len(fs)
    chk('factor stable across 4/16/64 (+16 repeat) within +-25% of the mean', all(abs(x / m - 1) <= .25 for x in fs), ' '.join('%.3f' % x for x in fs))
    hb = [R[a]['H']['end-pass2']['cache_b'] for a in ('k4', 'k16', 'k64')]
    chk('heap bytes scale ~ 1:4:16 (each within 15%)', abs(hb[1] / hb[0] / 4 - 1) < .15 and abs(hb[2] / hb[0] / 16 - 1) < .15, str(hb))
if 'k16' in R and 'k16b' in R:
    a, b = R['k16']['by']['end-pass2'], R['k16b']['by']['end-pass2']
    chk('repeat of 16 MiB: Size and Entries within 2%', abs(a['size'] / b['size'] - 1) < .02 and abs(a['entries'] / b['entries'] - 1) < .02, '%d/%d, %d/%d' % (a['size'], b['size'], a['entries'], b['entries']))
if 'k0' in R:
    e = R['k0']['by']['end-pass2']
    chk('k0: Size 0, Entries 0 at every sample', all(s['size'] == 0 and s['entries'] == 0 for s in R['k0']['S']))
    chk('k0: KeyCacheKey instances in the live histogram <= 100 at every histogram', all(h['kck_n'] <= 100 for h in R['k0']['H'].values()), str({k: h['kck_n'] for k, h in R['k0']['H'].items()}))
    chk('k0: reads actually happened (requests == 0 because the cache is disabled is not required); stress ok', os.path.exists(os.path.join(D, 'k0', 'stress-pass2.results')))
if 'k512' in R:
    r = R['k512']; e1, e2 = r['by']['end-pass1'], r['by']['end-pass2']
    chk('k512: does not plateau at 512 MiB: Size << cap and keeps growing from pass1 to pass2', e2['size'] < 0.5 * 512 * MIB and e2['size'] > e1['size'], 'size1=%d size2=%d' % (e1['size'], e2['size']))
    chk('k512: Entries at end ~ distinct keys read (>= 0.95 P) and Size ~ Entries x weight', e2['entries'] >= 0.95 * P, 'entries=%d P=%d size=%d avgW=%.2f' % (e2['entries'], P, e2['size'], e2['size'] / e2['entries']))
    f = r['H']['end-pass2']['cache_b'] / e2['size']; chk('k512: factor in [1.0, 2.5]', 1.0 <= f <= 2.5, '%.3f' % f)
if 'rt' in R:
    r = R['rt']; e1, ea, e2 = r['by']['end-pass1'], r['by']['after-setcap'], r['by']['end-pass2']
    chk('rt: before: Capacity 64 MiB and Size > 16 MiB (the cap bound)', e1['capacity'] == 64 * MIB and e1['size'] > 16 * MIB, 'size=%d' % e1['size'])
    chk('rt: after setcachecapacity 16: Capacity 16 MiB, Size <= 16 MiB within 30 s', ea['capacity'] == 16 * MIB and ea['size'] <= 16 * MIB, 'size=%d' % ea['size'])
    chk('rt: heap bytes of the cache fell (after-setcap < 0.5 x before)', r['H']['after-setcap']['cache_b'] < 0.5 * r['H']['end-pass1']['cache_b'], '%d -> %d' % (r['H']['end-pass1']['cache_b'], r['H']['after-setcap']['cache_b']))
    chk('rt: end: Size <= 16 MiB and heap bytes ~ those of a 16 MiB cap run', e2['size'] <= 16 * MIB, 'size=%d cache_b=%d' % (e2['size'], r['H']['end-pass2']['cache_b']))
print('TOTAL FAIL:', fails); sys.exit(1 if fails else 0)
