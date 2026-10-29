#!/usr/bin/env python3
"""Independent re-parse of the raw run-1 files of last_valid_segment_row_id-exceedssegmentlimit-sstablerowid--autonomous against the FROZEN predictions
(case file amendments U2/U3/C3 and B2f/B3f). usage: selfcheck.py <run1 dir containing unit/unit.out and cluster/<label>/...>
Prints PASS/FAIL/NOTE per check; a FAIL is a sub-prediction that missed (reported, never edited)."""
import glob, os, re, sys
R = sys.argv[1]; res = []
def chk(name, ok, detail=''):
    res.append(ok); print('%s %s %s' % ('PASS' if ok else 'FAIL', name, detail))
# ---------------- unit ----------------
lab = None; cells = {}
for l in open(R + '/unit/unit.out'):
    m = re.match(r'== (\S+) ', l)
    if m: lab = m.group(1)
    if l.startswith('STAGE4 RESULT'):
        kv = dict(re.findall(r'(\w+)=(\[[^\]]*\]|\S+)', l)); cells[lab] = kv
def g(l, k): return int(cells[l][k])
chk('unit: every run exited and printed a RESULT (27 grid + 5 pair)', len(cells) == 32, 'n=%d' % len(cells))
for cap in (-1, 1000, 100):
    for L in (1, 64, 1024):
        reps = [cells['G-cap%d-L%d-r%d' % (cap, L, r)] for r in (1, 2, 3)]
        same = all(r['segments'] == reps[0]['segments'] and r['peakLimiterBytes'] == reps[0]['peakLimiterBytes'] and r['rowsMax'] == reps[0]['rowsMax'] for r in reps)
        chk('unit: cap=%d L=%dMiB identical in 3 repetitions' % (cap, L), same, 'segments=%s peak=%s' % (reps[0]['segments'], reps[0]['peakLimiterBytes']))
c = lambda cap, L: cells['G-cap%d-L%d-r1' % (cap, L)]
chk('P1 default cap, L=1024 MiB: 1 segment, 200000 rows', c(-1, 1024)['segments'] == '1' and c(-1, 1024)['rowsMax'] == '200000', c(-1, 1024)['segments'])
chk('P2 [pre-registered 3..5] default cap, L=64 MiB: segments', 3 <= int(c(-1, 64)['segments']) <= 5, 'measured %s' % c(-1, 64)['segments'])
chk('P3 [pre-registered 150..400] default cap, L=1 MiB: segments', 150 <= int(c(-1, 1)['segments']) <= 400, 'measured %s' % c(-1, 1)['segments'])
for L in (1, 64):
    pk = int(c(-1, L)['peakLimiterBytes']); lim = L * 1048576
    chk('P4 default cap, L=%d MiB: peak limiter bytes in [L, 1.1 L + 4 MiB]' % L, lim <= pk <= 1.1 * lim + 4 * 1048576, 'peak=%d limit=%d' % (pk, lim))
chk('P4b default cap, L=1024 MiB: peak grows with N (476,329,976 B ~ 2.4 KB/row), below the limit', int(c(-1, 1024)['peakLimiterBytes']) < 1024 * 1048576, c(-1, 1024)['peakLimiterBytes'])
for L in (64, 1024):
    x = c(1000, L)
    chk('P5 cap=1000, L=%d MiB: exactly 200 segments, max 1001 rows, last 801' % L, x['segments'] == '200' and x['rowsMax'] == '1001' and x['lastRows'] == '801', '%s/%s/%s' % (x['segments'], x['rowsMax'], x['lastRows']))
    chk('P5b cap=1000, L=%d MiB: peak bytes far below L (< 10%% of L; B2f gives no number for "far below")' % L, int(x['peakLimiterBytes']) < 0.10 * L * 1048576, x['peakLimiterBytes'])
    x = c(100, L)
    chk('P6 [pre-registered exactly 1980] cap=100, L=%d MiB: segments' % L, x['segments'] == '1980', 'measured %s (ceil(200000/101) = %d)' % (x['segments'], -(-200000 // 101)))
chk('P6b cap=100 segments = ceil(200000/101) = 1981 (the correct arithmetic) and max rows 101', all(c(100, L)['segments'] == '1981' and c(100, L)['rowsMax'] == '101' for L in (1, 64, 1024)))
chk('B2g control: cap 1000/100 gives the same segment count for L=64 and 1024 (independent of L)', c(1000, 64)['segments'] == c(1000, 1024)['segments'] and c(100, 64)['segments'] == c(100, 1024)['segments'])
chk('B2g: at L=1 MiB the byte limit binds before cap 1000 (same as default cap)', c(1000, 1)['segments'] == c(-1, 1)['segments'] and c(1000, 1)['peakLimiterBytes'] == c(-1, 1)['peakLimiterBytes'])
chk('boundary: default cap, rows 0 and cap -> 1 segment', cells['P-default-0-cap']['segments'] == '1')
chk('boundary: default cap, rows 0 and cap+1 -> 2 segments', cells['P-default-0-cap+1']['segments'] == '2')
chk('boundary: cap 1000, rows 0 and 1000 -> 1 segment; 0 and 1001 -> 2', cells['P-cap1000-0-1000']['segments'] == '1' and cells['P-cap1000-0-1001']['segments'] == '2')
chk('gap: rows 0 and 1073741823 -> 2 segments', cells['P-gap-0-1073741823']['segments'] == '2')
# ---------------- cluster ----------------
def cl(label):
    d = R + '/cluster/' + label
    if not os.path.isdir(d) or not os.path.exists(d + '/segments.txt'): return None
    seg = []
    for l in open(d + '/segments.txt'):
        p = [x.strip() for x in l.split('|')]
        if len(p) == 5 and p[1].lstrip('-').isdigit(): seg.append((int(p[1]), int(p[2]), int(p[3]), int(p[4])))
    sb = [int(l.split(',')[1]) for l in open(d + '/segbuf.csv') if re.match(r'^\d+,\d+', l)]
    h = [int(l.split(',')[1]) for l in open(d + '/heap.csv').read().splitlines()[1:] if l.split(',')[1] not in ('-1', '')]
    after = []
    for f in glob.glob(d + '/gc-*.log'):
        for l in open(f, errors='replace'):
            m = re.search(r'Pause (?:Young|Full|Remark|Cleanup).*? (\d+)M->(\d+)M\((\d+)M\)', l)
            if m: after.append(int(m.group(2)))
    rd = open(d + '/readings.txt').read()
    gl = int(re.search(r'GLOBAL_LIMIT_LINES (\d+)', rd).group(1))
    return dict(segs=len(seg), rows=[s[1] for s in seg], span=[s[3] - s[2] for s in seg], segbuf=max(sb or [0]), heap=max(h or [0]) / 1024.0, aftergc=max(after or [0]), gl=gl,
                total=sum(s[1] for s in seg), jar=open(d + '/cmdlog.txt').read())
C = {k: cl(k) for k in ('S16', 'S256a', 'S256b', 'S1024', 'V1024')}
for k, v in C.items():
    if v is None: print('NOTE cluster run %s missing' % k); continue
    print('NOTE cluster %s: segments=%d rowsMax=%d spanMax=%d rowsTotal=%d segbufPeak=%.0fMB heapSampledPeak=%.0fMB heapAfterGcPeak=%dMB globalLimitLines=%d' % (k, v['segs'], max(v['rows']), max(v['span']), v['total'], v['segbuf'] / 1048576.0, v['heap'], v['aftergc'], v['gl']))
if all(C.get(k) for k in ('S16', 'S256a', 'S1024', 'V1024')):
    s16, s256, s1024, v = C['S16'], C['S256a'], C['S1024'], C['V1024']
    chk('C3 default constant: segments strictly decrease 16 > 256 > 1024 MiB', s16['segs'] > s256['segs'] > s1024['segs'], '%d > %d > %d' % (s16['segs'], s256['segs'], s1024['segs']))
    chk('C3 [pre-registered] segments at 1024 MiB in 3..8', 3 <= s1024['segs'] <= 8, 'measured %d' % s1024['segs'])
    chk('C3 [pre-registered] segments at 256 MiB in 15..40', 15 <= s256['segs'] <= 40, 'measured %d' % s256['segs'])
    chk('C3 [pre-registered] segments at 16 MiB in 200..600', 200 <= s16['segs'] <= 600, 'measured %d' % s16['segs'])
    chk('C3 no segment spans more than 5,000,000 row ids (never split at the row cap)', all(max(x['span']) < 5000000 for x in (s16, s256, s1024)))
    chk('C3 [pre-registered] Global-limit lines present at all three limits (segments - 1)', all(x['gl'] >= 1 for x in (s16, s256, s1024)), '%d/%d/%d' % (s16['gl'], s256['gl'], s1024['gl']))
    chk('C3 [pre-registered] small constant (10000) at 1024 MiB: exactly 500 segments, max 10001 rows, last 9501', v['segs'] == 500 and max(v['rows']) == 10001 and sorted(v['rows'])[0] in (9501,) or (v['segs'] == 500 and 9501 in v['rows']), 'segments=%d rowsMax=%d' % (v['segs'], max(v['rows'])))
    chk('C3 [pre-registered] peak SegmentBufferSpaceUsedBytes at 16 MiB < 40 MiB and at 1024 MiB > 400 MiB', s16['segbuf'] < 40 * 1048576 and s1024['segbuf'] > 400 * 1048576, '%.1f MiB / %.1f MiB' % (s16['segbuf'] / 1048576.0, s1024['segbuf'] / 1048576.0))
    chk('C3 [pre-registered] heap-after-GC peak at 1024 MiB exceeds that at 16 MiB by >= 300 MB', s1024['aftergc'] - s16['aftergc'] >= 300, '%d vs %d MB' % (s1024['aftergc'], s16['aftergc']))
    chk('control: small constant at 1024 MiB: peak buffer far below the default constant at 1024 MiB', v['segbuf'] < s1024['segbuf'] / 5, '%.1f vs %.1f MiB' % (v['segbuf'] / 1048576.0, s1024['segbuf'] / 1048576.0))
    chk('jar check: variant run shows LAST_VALID_SEGMENT_ROW_ID = 10000l; std runs show the default', '10000l' in v['jar'] and '1073741822' in s1024['jar'])
if C.get('V1024'):
    v = C['V1024']; n = v['total']
    chk('[post-hoc, NOT pre-registered] small constant: segments = ceil(measured rows / 10001) and rows per segment 10001 except the last', v['segs'] == -(-n // 10001) and max(v['rows']) == 10001, 'rows=%d -> ceil = %d, measured %d segments' % (n, -(-n // 10001), v['segs']))
    print('NOTE the pre-registered 500 assumed 5,000,000 indexed rows; the seed holds %d (cassandra-stress user mode revisits ids: see results defect D2)' % n)
for k in ('S16', 'S256a', 'S1024'):
    if C.get(k): print('NOTE %s: rows per segment %d..%d, bytes per row at the limit ~ %.0f' % (k, min(C[k]['rows']), max(C[k]['rows']), (int(re.search(r'(\d+)', str(C[k]['segbuf'])).group(1))) / max(max(C[k]['rows']), 1)))
print('SUMMARY pass=%d fail=%d' % (sum(res), len(res) - sum(res)))
