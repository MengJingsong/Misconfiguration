#!/usr/bin/env python3
"""Readings and EXPECTED checks for the unit tier of commitlog_segment_size-allocate-endOfBuffer--autonomous (B2f / B2g / B2i).
Usage: python3 -I analyze_unit.py <outdir>   (reads <outdir>/<arm>/seg.csv, seg.summary, arm.yaml)"""
import sys, os, re, math, csv, glob

root = sys.argv[1]
MiB = 1 << 20
bad = []
rows = []
for d in sorted(glob.glob(os.path.join(root, '*/'))):
    arm = os.path.basename(d.rstrip('/'))
    if not os.path.exists(d + 'seg.csv'):
        print(f'ARM {arm}: NO seg.csv'); bad.append(arm); continue
    info = {}
    probes = {}
    for ln in open(d + 'seg.summary'):
        ln = ln.strip()
        if ln.startswith('INFO'):
            info = dict(kv.split('=', 1) for kv in ln.split()[1:])
        elif ln.startswith('PROBE'):
            parts = ln.split()
            probes[parts[1]] = dict(kv.split('=', 1) for kv in parts[2:] if '=' in kv)
            m = re.search(r'oversizedMutations\+(\d+)', ln)
            if m: probes[parts[1]]['oversized'] = m.group(1)
        elif ln.startswith('SUMMARY'):
            summ = dict(kv.split('=', 1) for kv in ln.split()[1:])
    S = int(info['S']); mode = info['accessMode']; comp = info['compression']
    segs = list(csv.DictReader(open(d + 'seg.csv')))
    n = len(segs)
    cap_ok = all(int(r['capacity']) == S for r in segs)
    end_ok = all(int(r['maxEnd']) < int(r['capacity']) for r in segs if int(r['adds']) > 0)
    retired = segs[:-1]
    ret_ok = all(int(r['endOfBuffer']) < int(r['capacity']) and int(r['allocatePosition']) == int(r['capacity']) + 1 and r['stillAllocating'] == 'false' for r in retired)
    # the final segment can be retired by the last probe roll; report its state
    last = segs[-1]
    bound_ok = True; fl_note = ''
    if comp == 'none':
        fl_ok = all(int(r['fileLength']) == S and int(r['onDiskSize']) == S for r in segs)
        fl_note = 'mmap fileLength==S'
    else:
        fl_ok = True
        mx = 0.0
        for r in segs:
            b = S + math.ceil(S / 255) + 32 * max(int(r['blocks']), 0) + 64
            if int(r['fileLength']) > b: fl_ok = False
            mx = max(mx, int(r['fileLength']) / S)
        fl_note = f'lz4 fileLength<=bound (max fileLength/S={mx:.4f})'
    over_S = [int(r['fileLength']) for r in segs if int(r['fileLength']) > S]
    nseg_min = math.ceil(int(info['adds']) * int(info['entry']) / S)
    nseg_ok = n >= nseg_min
    viol_ok = int(summ['violations']) == 0
    pr = probes
    maxp = pr.get('max-accepted', {}); ov = pr.get('oversize', {}); ea = pr.get('edge-a', {}); eb = pr.get('edge-b', {})
    ov_ok = ov.get('exception') == 'MutationExceededMaxSizeException' and ov.get('oversized') == '1' and ov.get('allocatePositionDelta') == '0'
    max_ok = int(maxp.get('total', -1)) == int(info['maxMutationSize']) == S // 2
    ea_ok = ea.get('stayed') == 'true' and int(ea.get('allocPosAfter', -1)) == int(ea.get('capacity', 0)) - 1
    eb_ok = eb.get('rolled') == 'true' and int(eb.get('oldEndOfBuffer', -1)) == int(eb.get('capacity', 0)) - int(eb.get('remaining', 0)) and int(eb.get('oldAllocPos', -1)) == int(eb.get('capacity', 0)) + 1
    ctl_fail = not all(int(r['capacity']) == S + MiB for r in segs)   # B2i.6: the (S+1 MiB) assertion must be false
    ok = all([cap_ok, end_ok, ret_ok, fl_ok, nseg_ok, viol_ok, ov_ok, max_ok, ea_ok, eb_ok, ctl_fail])
    if not ok: bad.append(arm)
    print(f"ARM {arm}: S={S//MiB}MiB mode={mode} comp={comp} entry={info['entry']} adds={info['adds']} segments={n} (>= {nseg_min}) "
          f"maxEnd_max={max(int(r['maxEnd']) for r in segs)} capacity={S}")
    print(f"   EXPECTED capacity==S {cap_ok} | all maxEnd<capacity {end_ok} (violations={summ['violations']}) | retired endOfBuffer<cap, allocPos==cap+1, !stillAllocating {ret_ok} | {fl_note} {fl_ok}"
          f" (files>S: {len(over_S)}) | segments>=min {nseg_ok}")
    print(f"   PROBES max-accepted {max_ok} | oversize {ov_ok} ({ov.get('exception')}, +{ov.get('oversized')}, dPos={ov.get('allocatePositionDelta')}) | edge-a {ea_ok} (rem={ea.get('remaining')} stayed={ea.get('stayed')} after={ea.get('allocPosAfter')}) | edge-b {eb_ok} (rem={eb.get('remaining')} rolled={eb.get('rolled')} oldEnd={eb.get('oldEndOfBuffer')} oldAlloc={eb.get('oldAllocPos')}) | control(S+1MiB assertion false) {ctl_fail}")
    rows.append((arm, S, mode, ok))
print('ARMS_NOT_AS_EXPECTED:', bad if bad else 'none')
