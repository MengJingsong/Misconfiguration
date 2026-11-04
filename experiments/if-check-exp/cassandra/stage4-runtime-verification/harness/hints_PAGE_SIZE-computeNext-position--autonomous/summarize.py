#!/usr/bin/env python3
"""Readings tables for hints_PAGE_SIZE-computeNext-position--autonomous (stage 4, B2/B3 as amended 2026-10-26).
usage: summarize.py unit <unit log dir>      (reads hpcap.txt)
       summarize.py cluster <cluster out dir> (reads summary.txt, arm-*/hpcap.txt, arm-*/hist.txt)
Only builds tables; the independent check is results/<stem>/run1/selfcheck.py."""
import math, os, re, statistics, sys

PAGE = 524288

def unit(d):
    files, pages, ends = {}, {}, {}
    for ln in open(os.path.join(d, 'hpcap.txt')):
        kv = dict(re.findall(r'(\w+)=(\S+)', ln))
        if ln.startswith('HPCAP-FILE'):
            files[(int(kv['v']), kv['fmt'])] = kv
        elif ln.startswith('HPCAP-END'):
            ends[(int(kv['v']), kv['fmt'], kv['it'])] = kv
        elif ln.startswith('HPCAP v='):
            pages.setdefault((int(kv['v']), kv['fmt'], kv['it']), []).append({k: int(kv[k]) for k in ('page', 'c', 'P', 'sum')})
    print('v fmt it | N e(min=max) fileBytes | pages(pred) | c full pages (pred) | P range full pages | P<PAGE+e | sum=P-12c | last page c,P')
    for (v, fmt, it), ps in sorted(pages.items()):
        f = files[(v, fmt)]; N = int(f['N']); e = int(f['emin']); emax = int(f['emax'])
        cpred = max(1, math.ceil(PAGE / e)); ppred = math.ceil(N / cpred)
        full = ps[:-1] if len(ps) > 1 else ps
        cs = sorted(set(p['c'] for p in full)); Ps = [p['P'] for p in full]
        okP = all(PAGE <= p['P'] < PAGE + e for p in full) if e < PAGE else all(p['P'] == e for p in ps)
        okS = all(p['sum'] == p['P'] - 12 * p['c'] for p in ps)
        print(f"{v} {fmt} {it} | {N} {e}{'' if e == emax else '/' + str(emax)} {f['fileBytes']} | {len(ps)}({ppred}) | {cs} ({cpred}) | "
              f"{min(Ps)}..{max(Ps)} | {okP} | {okS} | {ps[-1]['c']},{ps[-1]['P']}")

def cluster(d):
    summ = open(os.path.join(d, 'summary.txt')).read().splitlines()
    arms = [l.split()[1] for l in summ if l.startswith('ARM ')]
    for a in arms:
        marks = {}
        for l in summ:
            m = re.match(r'MARK (\S+) (\S+).* ms=(\d+)', l)
            if m and m.group(1) == a:
                marks[m.group(2)] = int(m.group(3))
        jc = {}
        for l in summ:
            m = re.match(r'JMXCOUNT (\S+) (\S+) \| RESULT (.*)', l)
            if m and m.group(1) == a:
                jc[m.group(2)] = dict(re.findall(r'(\w+)=(\d+)', m.group(3)))
        arm = [l for l in summ if l.startswith('ARM ' + a + ' ')][0]
        N = int(re.search(r' N=(\d+)', arm).group(1)); v = int(re.search(r' v=(\d+)', arm).group(1))
        files, cur = [], None
        for ln in open(os.path.join(d, 'arm-' + a, 'hpcap.txt')):
            if ln.startswith('HPCAP file start'):
                cur = []; files.append(cur)
            elif ln.startswith('HPCAP page'):
                kv = dict(re.findall(r'(\w+)=(\S+)', ln))
                if cur is None:
                    cur = []; files.append(cur)
                cur.append((int(kv['sent']), int(kv['bytes']), kv['action']))
        allp = [p for f in files for p in f]
        nonlast = [p for f in files for p in f[:-1]]
        sents = [p[0] for p in nonlast] or [p[0] for p in allp]
        k = statistics.mode(sents) if sents else 0
        kform = sorted(set(max(1, math.ceil(PAGE / (b / s + 12))) for s, b, _ in nonlast if s))
        samples, cur = [], None
        for ln in open(os.path.join(d, 'arm-' + a, 'hist.txt')):
            if ln.startswith('#SAMPLE'):
                cur = {'t0': int(re.search(r't0=(\d+)', ln).group(1)), 'hint': 0, 'B': None, 'err': False}; samples.append(cur)
            elif cur is not None:
                f = ln.split()
                if ln.rstrip().endswith(' org.apache.cassandra.hints.Hint'):
                    cur['hint'] = int(f[1])
                elif len(f) >= 4 and f[3] == '[B':
                    cur['B'] = int(f[2])
                elif re.search(r'Exception|Unable to open|not responding', ln):
                    cur['err'] = True
        ok = [s for s in samples if s['B'] is not None]
        base = [s for s in ok if marks['baseline-start'] <= s['t0'] < marks['baseline-end']]
        deliv = [s for s in ok if marks['resume'] <= s['t0'] < marks['delivery-end']]
        b0 = statistics.median([s['B'] for s in base]) if base else None
        hc = [s['hint'] for s in deliv]
        print(f"ARM {a} v={v} N={N} | files={len(files)} pages={len(allp)} sent_total={sum(p[0] for p in allp)} abort={sum(p[2] != 'CONTINUE' for p in allp)}")
        print(f"  k(mode non-last)={k} formula(non-last)={kform} non-last sent set={sorted(set(sents))} max bytes={max([p[1] for p in allp] or [0])} bound={PAGE + v + 100}")
        print(f"  last pages per file: {[f[-1][:2] for f in files if f]}")
        print(f"  samples total={len(samples)} ok={len(ok)} baseline={len(base)} delivery={len(deliv)} | baseline Hint max={max([s['hint'] for s in base] or [0])}")
        if hc:
            print(f"  delivery Hint max={max(hc)} median={statistics.median(hc)} (k+2={k + 2}, 1.1k={1.1 * k:.1f}); [B baseline median={b0} max delivery={max(s['B'] for s in deliv)} "
                  f"delta={max(s['B'] for s in deliv) - b0 if b0 is not None else None} bound k*v+8MiB={k * v + 8388608}")
        if 'before' in jc and 'after' in jc:
            dj = {x: int(jc['after'][x]) - int(jc['before'][x]) for x in jc['before']}
            print(f"  JMX before={jc['before']} after-before={dj}")

if __name__ == '__main__':
    {'unit': unit, 'cluster': cluster}[sys.argv[1]](sys.argv[2])
