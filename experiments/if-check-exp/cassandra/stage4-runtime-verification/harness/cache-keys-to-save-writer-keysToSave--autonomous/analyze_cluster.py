#!/usr/bin/env python3
"""Cluster-tier analysis for cache-keys-to-save-writer-keysToSave--autonomous: reads <dir>/{main,ctl20,yaml10k}/results.json and prints
EXPECTED lines (ok / MISMATCH) for the B3f relations (as amended 2026-10-26) and the B3g row they select.
usage: analyze_cluster.py <cluster-dir> [min_entries=300000]
Reading rules fixed before run 1 (not tuned to readings):
  limit reached: entries before each save >= 300000 (> 100000 > 10000);
  logged n == K exactly when 0 < K < entries; logged n == entries (within 0.5 %) when K in {0, 2147483647};
  data file bytes F(K) = hdr + n e: e_full = (F_full - hdr0)/n_full with hdr0 = F(10000) - 10000 e from the two-point fit; K-limited files satisfy
    F(K) <= 1.05 * e_full * K + hdr0 + 64 (no file larger than K e_max);
  F(10000)/F(100000) <= 0.11 ; F(K=0) and F(default) equal within 1 % and equal to each other's n;
  live gauges Entries and Size identical before and after every save and equal across the K sweep (no reads between saves);
  control: entries(20 MiB) < 0.5 x entries(200 MiB); Size(20 MiB) <= 20 MiB; the K=10000 file in the 20 MiB arm equals the 200 MiB arm's within 5 %;
  yaml arm: JMX read-back 10000 at startup; the periodic save and the manual save log n == 10000; file within 5 % of the main arm's K=10000 file.
Informational (no row): heap peak during each save; e versus the unit tier's e."""
import json, os, sys
d = sys.argv[1]; MINE = int(sys.argv[2]) if len(sys.argv) > 2 else 300000
bad = 0
def exp(name, ok, detail=''):
    global bad
    print('EXPECTED %s: %s %s' % (name, 'ok' if ok else 'MISMATCH', detail)); bad += 0 if ok else 1
def load(a):
    p = os.path.join(d, a, 'results.json')
    return json.load(open(p)) if os.path.exists(p) else None
main, ctl, yml = load('main'), load('ctl20'), load('yaml10k')
MAX = 2147483647
if not main: print('no main results'); sys.exit(1)
S = {s['K']: s for s in main['saves']}
F = {k: s['files_after'].get('KeyCache-g.db') for k, s in S.items()}
E = {k: s['before']['entries'] for k, s in S.items()}
for k, s in sorted(S.items()):
    print('main K=%d readback=%s n_logged=%s file=%s crc=%s meta=%s entries=%d size=%d heap_peak=%s' % (k, s['K_readback'], s['n_logged'], F[k], s['files_after'].get('KeyCache-g.crc'), s['files_after'].get('KeyCache-g.metadata'), E[k], s['before']['size'], s['heap_peak_during_save']))
exp('main: every K read back through JMX equals the value set', all(s['K_readback'] == str(k) for k, s in S.items()))
exp('main: limit reached (entries >= %d before every save)' % MINE, all(e >= MINE for e in E.values()), str(E))
exp('main: no read between saves (Entries and Size identical before/after each save and across the sweep)',
    all(s['before'] == s['after'] for s in S.values()) and len({(s['before']['entries'], s['before']['size']) for s in S.values()}) == 1,
    str({k: (s['before']['entries'], s['before']['size'], s['after']['entries'], s['after']['size']) for k, s in S.items()}))
for k in (10000, 100000):
    exp('main K=%d logged n == K (K < entries)' % k, S[k]['n_logged'] == k, 'n=%s' % S[k]['n_logged'])
for k in (0, MAX):
    exp('main K=%d logged n == entries (within 0.5 %%)' % k, abs(S[k]['n_logged'] - E[k]) <= 0.005 * E[k], 'n=%s entries=%d' % (S[k]['n_logged'], E[k]))
n = {k: S[k]['n_logged'] for k in S}
e = (F[0] - F[10000]) / float(n[0] - n[10000]); hdr = F[10000] - e * n[10000]
print('derived: e=%.2f bytes/entry hdr=%.1f bytes (two-point fit K=10000 / K=0)' % (e, hdr))
for k in sorted(F):
    exp('main K=%d file bytes affine in n (|resid| <= 1 %% of file)' % k, abs(F[k] - (hdr + e * n[k])) <= 0.01 * F[k], 'file=%d pred=%.0f' % (F[k], hdr + e * n[k]))
for k in (10000, 100000):
    exp('main K=%d file <= 1.05 e_full K + hdr + 64 (no file above K e_max)' % k, F[k] <= 1.05 * e * k + hdr + 64, 'file=%d bound=%.0f' % (F[k], 1.05 * e * k + hdr + 64))
exp('main F(10000)/F(100000) <= 0.11', F[10000] / float(F[100000]) <= 0.11, 'ratio=%.4f' % (F[10000] / float(F[100000])))
exp('main F(K=0) == F(default) within 1 %', abs(F[0] - F[MAX]) <= 0.01 * F[0], 'F0=%d Fmax=%d' % (F[0], F[MAX]))
exp('main K=0 file larger than K=10000 and K=100000 files', F[0] > F[100000] > F[10000])
print('INFO metadata file bytes by K (depends on the sstables the saved keys touch, CacheService.java:433-447; no row): ' + str({k: S[k]['files_after'].get('KeyCache-g.metadata') for k in S}))
if ctl:
    C = {s['K']: s for s in ctl['saves']}
    eC = C[10000]['before']['entries']; eM = E[0]
    exp('control: entries(20 MiB) < 0.5 x entries(200 MiB)', eC < 0.5 * eM, 'entries20=%d entries200=%d' % (eC, eM))
    exp('control: Size(20 MiB) <= 20 MiB', C[10000]['before']['size'] <= 20 * 1024 * 1024, 'size=%d' % C[10000]['before']['size'])
    exp('control: logged n == 10000 at K=10000; n == entries at K=0', C[10000]['n_logged'] == 10000 and abs(C[0]['n_logged'] - eC) <= 0.005 * eC, 'n=%s,%s entries=%d' % (C[10000]['n_logged'], C[0]['n_logged'], eC))
    f10 = C[10000]['files_after'].get('KeyCache-g.db'); f0 = C[0]['files_after'].get('KeyCache-g.db')
    exp('control: K=10000 file within 5 % of the 200 MiB arm\'s', abs(f10 - F[10000]) <= 0.05 * F[10000], 'f20=%d f200=%d' % (f10, F[10000]))
    exp('control: full file (K=0) smaller than half the 200 MiB arm\'s', f0 < 0.5 * F[0], 'f20=%d f200=%d' % (f0, F[0]))
else:
    print('no ctl20 results')
if yml:
    exp('yaml: startup read-back 10000', yml.get('yaml_readback') == '10000')
    per = yml['periodic']['new']
    exp('yaml: periodic save (startup-captured K) logged n == 10000', bool(per) and per[-1]['n'] == 10000, str([p['n'] for p in per]))
    man = yml['saves'][-1]
    exp('yaml: manual save logged n == 10000', man['n_logged'] == 10000, 'n=%s' % man['n_logged'])
    fy = man['files_after'].get('KeyCache-g.db')
    exp('yaml: file within 5 % of the main arm\'s K=10000 file', abs(fy - F[10000]) <= 0.05 * F[10000], 'fy=%d f=%d' % (fy, F[10000]))
else:
    print('no yaml10k results')
# B3g classification
cls = []
if any(0 < k < E[k] and S[k]['n_logged'] > k for k in (10000, 100000)): cls.append('file larger than K for K < entries: knob does not cap; claim wrong')
if len({s['before']['size'] for s in S.values()}) > 1: cls.append('live key-cache size changes with K: knob affects memory')
print('B3g classification:', '; '.join(cls) if cls else ('file size and logged n follow min(K, entries): claim holds (disk cap works on a real node)' if bad == 0 else 'see MISMATCH lines'))
print('MISMATCH total', bad); sys.exit(1 if bad else 0)
