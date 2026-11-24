#!/usr/bin/env python3
"""Stage-4 o122 cluster tier: read alloc-*.json (jfr print --json) and session.log of each config,
match large byte[] outside-TLAB events to the reads, check B3f as amended by B3i.4.
usage: analyze_cluster.py <results-dir-parent> C1:100 C2:200 C3:200 C4:200:ctrl"""
import json, re, sys, os
from datetime import datetime

MiB = 1 << 20
BIG = 50 * MiB


def ts_ms(s):
    # JFR JSON startTime: ISO-8601 with offset, e.g. 2026-11-24T06:30:01.123456789Z or +00:00
    s = s.replace('Z', '+00:00')
    m = re.match(r'(.*T\d\d:\d\d:\d\d)(\.\d+)?([+-]\d\d:\d\d)$', s)
    base, frac, off = m.group(1), (m.group(2) or '.0'), m.group(3)
    frac = (frac + '000000')[:7]
    return int(datetime.fromisoformat(base + frac + off).timestamp() * 1000)


def events(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    d = json.load(open(path))
    out = []
    for e in d['recording']['events']:
        v = e['values']
        oc = v.get('objectClass') or {}
        name = oc.get('name') if isinstance(oc, dict) else str(oc)
        size = v.get('allocationSize')
        frames = []
        st = v.get('stackTrace') or {}
        for f in (st.get('frames') or []):
            mth = f.get('method') or {}
            t = (mth.get('type') or {}).get('name', '?')
            frames.append('%s.%s:%s' % (t, mth.get('name', '?'), f.get('lineNumber')))
        th = v.get('eventThread') or {}
        out.append(dict(t=ts_ms(v['startTime']), cls=name, size=size, frames=frames,
                        thread=(th.get('javaName') or th.get('osName')) if isinstance(th, dict) else th))
    return out


def main():
    base = sys.argv[1]
    ok = bad = 0
    summary = []
    for spec in sys.argv[2:]:
        parts = spec.split(':')
        cfg, vmib, ctrl = parts[0], int(parts[1]), len(parts) > 2
        V = vmib * MiB
        R = os.path.join(base, 'results-' + cfg)
        sess = open(os.path.join(R, 'session.log')).read()
        reads = [(int(a), int(b), int(rc)) for a, b, rc in re.findall(r'READ\d start=(\d+) end=(\d+) rc=(\d+)', sess)]
        rk = re.search(r'READK start=(\d+) end=(\d+) rc=(\d+)', sess)
        san = re.search(r'SANITY_READ start=(\d+) end=(\d+) rc=(\d+)', sess)
        syslog = open(os.path.join(R, 'system.log')).read()
        # one failed read = one ERROR entry at JVMStabilityInspector.java:70 (the same exception is logged again at :76)
        blocks = re.split(r'\n(?=(?:ERROR|WARN|INFO|DEBUG) +\[)', syslog)
        entries = []
        for blk in blocks:
            mm = re.match(r'ERROR +\[[^\]]+\] (\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d),(\d{3}) JVMStabilityInspector\.java:70', blk)
            if mm:
                t = int(datetime.fromisoformat(mm.group(1) + '+00:00').timestamp() * 1000) + int(mm.group(2))
                entries.append((t, blk))
        def in_win(t, w):
            return w[0] - 500 <= t <= w[1] + 500
        eof_pat = r'EOF after \d+ bytes out of %d\b' % V
        cor_pat = r'Corrupt value length %d encountered, as it exceeds the maximum of %d' % (V, 64 * MiB)
        eof_v = sum(1 for (t, blk) in entries if re.search(eof_pat, blk) and any(in_win(t, (a, b)) for a, b, _ in reads))
        corrupt = sum(1 for (t, blk) in entries if re.search(cor_pat, blk) and any(in_win(t, (a, b)) for a, b, _ in reads))
        eof_any = len(entries)
        eof_after_alloc = sum(1 for (t, blk) in entries if re.search(eof_pat, blk) and 'ByteArrayAccessor.read(ByteArrayAccessor.java:103)' in blk
                              and 'TrackedDataInputPlus.checkCanRead(TrackedDataInputPlus.java:187)' in blk)
        print('  ERROR entries (:70) total=%d; with EOF out of V thrown at checkCanRead:187 via ByteArrayAccessor.java:103 = %d'
              % (len(entries), eof_after_alloc))
        ev = events(os.path.join(R, 'alloc-read.json')) or []
        big = [e for e in ev if e['cls'] in ('byte[]', '[B') and e['size'] is not None and e['size'] >= BIG]
        inband = [e for e in big if V <= e['size'] <= V + 64]
        withstack = [e for e in inband if any('ByteArrayAccessor.read' in f for f in e['frames'])]
        per_read = []
        for (a, b, rc) in reads:
            n = [e for e in big if a - 500 <= e['t'] <= b + 500]
            per_read.append(len(n))
        k_big = None
        if rk:
            a, b = int(rk.group(1)), int(rk.group(2))
            k_big = len([e for e in big if a - 500 <= e['t'] <= b + 500])
        wev = events(os.path.join(R, 'alloc-write.json')) or []
        S = None
        m = re.search(r'cfg=\S+ S=(\d+)', sess)
        if m: S = int(m.group(1))
        san_ev = []
        if san and S:
            a, b = int(san.group(1)), int(san.group(2))
            san_ev = [e for e in wev if e['cls'] in ('byte[]', '[B') and S <= (e['size'] or 0) <= S + 64 and a - 500 <= e['t'] <= b + 500]
        print('== %s  V=%d  control=%s' % (cfg, V, ctrl))
        print('  reads (start,end,rc):', reads)
        print('  system.log, SELECT v reads: EOF..out of V reads=%d, Corrupt value length(V,64MiB) reads=%d (all :70 entries incl. SELECT k: %d)'
              % (eof_v, corrupt, eof_any))
        print('  JFR read session: outside-TLAB events=%d, byte[]>=50MiB=%d, in [V,V+64]=%d, with ByteArrayAccessor.read=%d'
              % (len(ev), len(big), len(inband), len(withstack)))
        for e in big:
            print('    event t=%d size=%d thread=%s top=%s' % (e['t'], e['size'], e['thread'], ' <- '.join(e['frames'][:4])))
        print('  big events per SELECT v read window:', per_read, ' SELECT k window:', k_big)
        print('  sanity read (write session): byte[] events of size in [S,S+64] in its window: %d %s'
              % (len(san_ev), [e['size'] for e in san_ev]))

        def chk(name, cond):
            nonlocal ok, bad
            if cond: ok += 1
            else: bad += 1
            print('  %s %s' % ('OK ' if cond else 'BAD', name))
        chk('3 SELECT v reads ran', len(reads) == 3)
        chk('sanity instrument: one ~S byte[] event in sanity window', len(san_ev) >= 1)
        if not ctrl:
            chk('EOF out of V logged once per read (3)', eof_v == 3)
            chk('one ~V byte[] per read window', per_read == [1, 1, 1])
            chk('in-band events in SELECT v windows == EOF reads',
                len([e for e in inband if any(in_win(e['t'], (a, b)) for a, b, _ in reads)]) == eof_v)
            chk('every in-band event has ByteArrayAccessor.read frame', len(withstack) == len(inband))
            chk('no big byte[] outside band', len(big) == len(inband))
        else:
            chk('Corrupt value length logged per read (3)', corrupt == 3)
            chk('no byte[] >= 50 MiB', len(big) == 0)
            chk('no EOF out of V', eof_v == 0)
        summary.append((cfg, V, eof_v, corrupt, len(big), len(inband), per_read, k_big, sorted(set(e['size'] for e in inband))))
    print('\nSUMMARY cfg V eofV corrupt big inband per_read selectk sizes')
    for s in summary:
        print('SUMMARY', *s)
    print('CHECKS ok=%d bad=%d' % (ok, bad))


if __name__ == '__main__':
    main()
