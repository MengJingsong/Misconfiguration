#!/usr/bin/env python3
"""usage: analyze.py <arm-folder> [<off-arm-folder>]    readings of one cluster arm (case B3d/B3g as amended C3, C5).
Per snapshot tag (base, s<ops>): debug.log events, live LogMessage instances, paging-off row count, bytes of LogMessage + LinkedList$Node
+ String + [B (collecting class histogram), post-GC heap used, debug.log events at/after the oldest listed timestamp.
With an OFF arm folder: the ON-minus-OFF byte totals at equal tags and per instance."""
import re, sys, os, datetime
CL = ['org.apache.cassandra.db.virtual.LogMessagesTable$LogMessage', 'java.util.LinkedList$Node', 'java.lang.String', '[B']

def hist(path):
    r = {}
    for l in open(path, errors='replace'):
        p = l.split()
        if len(p) >= 4 and p[0].endswith(':'):
            r[p[3]] = (int(p[1]), int(p[2]))
    return r

def heap_used(path):
    for l in open(path, errors='replace'):
        m = re.search(r'used (\d+)K', l)
        if m: return int(m.group(1)) * 1024
    return -1

def ts_ms(s):  # 2026-10-28 02:21:04.075000+0000
    m = re.match(r'\s*(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\.(\d+)', s)
    t = datetime.datetime.strptime(m.group(1) + ' ' + m.group(2), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
    return int(t.timestamp() * 1000) + int(m.group(3)[:3])

def dl_events(path):
    ev = []
    for l in open(path, errors='replace'):
        m = re.match(r'(TRACE|DEBUG|INFO|WARN|ERROR)\s+\[[^\]]*\]\s+(\d{4}-\d\d-\d\d)T(\d\d:\d\d:\d\d),(\d+)', l)
        if m:
            t = datetime.datetime.strptime(m.group(2) + ' ' + m.group(3), '%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
            ev.append((int(t.timestamp() * 1000) + int(m.group(4)), m.group(1)))
    return ev

def tags(d):
    t = [f[:-7] for f in os.listdir(d) if f.endswith('.events')]
    return sorted(t, key=lambda x: (x != 'base', int(x[1:]) if x != 'base' else 0))

def arm(d):
    out = {}
    ev = dl_events(d + '/debug.log') if os.path.exists(d + '/debug.log') else []
    for t in tags(d):
        e = dict(l.strip().split('=') for l in open(f'{d}/{t}.events'))
        h = hist(f'{d}/hist-{t}.txt')
        rec = {'events': int(e['events_debuglog']), 'epoch': int(e['snapshot_epoch_ms']),
               'inst': h.get(CL[0], (0, 0))[0], 'bytes': sum(h.get(c, (0, 0))[1] for c in CL),
               'b_lm': h.get(CL[0], (0, 0))[1], 'b_node': h.get(CL[1], (0, 0))[1], 'b_str': h.get(CL[2], (0, 0))[1], 'b_arr': h.get(CL[3], (0, 0))[1],
               'heap': heap_used(f'{d}/heap-{t}.txt'), 'rows': int(open(f'{d}/cqlrows-{t}.txt').read().strip() or 0)}
        no = f'{d}/newest-oldest-{t}.txt'
        lines = open(no).read().splitlines() if os.path.exists(no) else []
        if len(lines) >= 2 and ev:
            old = ts_ms(lines[1]); rec['oldest'] = old
            rec['events_since_oldest'] = sum(1 for (x, lv) in ev if old <= x <= rec['epoch'])
        out[t] = rec
    warn = sum(1 for (x, lv) in ev if lv in ('WARN', 'ERROR'))
    return out, warn

if __name__ == '__main__':
    d = sys.argv[1]
    a, warn = arm(d)
    print('arm', d, '| jvm-extra:', open(d + '/jvm-extra.txt').read().strip() if os.path.exists(d + '/jvm-extra.txt') else '', '| capacity line:', open(d + '/capacity-line.txt').read().strip()[-70:] if os.path.exists(d + '/capacity-line.txt') else '')
    print('WARN/ERROR events in debug.log (whole run):', warn)
    base = a.get('base')
    print('%-7s %9s %9s %9s %12s %12s %9s %12s' % ('tag', 'events', 'instances', 'cqlrows', 'bytes4', 'heapAfterGC', 'since_old', 'pred_inst(b0+E-e0)'))
    for t, r in a.items():
        pred = base['inst'] + (r['events'] - base['events']) if base else -1
        print('%-7s %9d %9d %9d %12d %12d %9s %12d' % (t, r['events'], r['inst'], r['rows'], r['bytes'], r['heap'], r.get('events_since_oldest', '-'), pred))
    if len(sys.argv) > 2:
        b, _ = arm(sys.argv[2])
        print('ON minus OFF at equal tags (bytes of LogMessage+Node+String+[B; heap after GC); per instance')
        for t, r in a.items():
            if t in b:
                db = r['bytes'] - b[t]['bytes']; dh = r['heap'] - b[t]['heap']
                print('%-7s dBytes=%12d dHeap=%12d inst=%9d dBytes/inst=%8.1f dHeap/inst=%8.1f' % (t, db, dh, r['inst'], db / max(1, r['inst']), dh / max(1, r['inst'])))
