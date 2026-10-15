#!/usr/bin/env python3
"""Replays the scratch-buffer ledger written by dob-ledger.btm (case 9d).
  ledger.py <ledger.txt> [--upto BYTES] [--from BYTES] [--dob N] [--json]
Per buffer instance (dob): live bytes after every event (alloc +size; grow-free and replaced -old capacity), its peak, its
capacity after its last close, the thread id that used it last. R = the sum of live bytes over all instances.
As a module: parse(path, start, end) -> list of events; replay(events, state=None) -> state (dict dob -> Buf)."""
import json, re, sys

LINE = re.compile(r'^(new|alloc|grow-free|close|kept|replaced|closed) (.*)$')


def fields(rest):
    return dict(kv.split('=', 1) for kv in re.findall(r'(\w+=\S+)', rest))


def parse(path, start=0, end=None):
    ev = []
    with open(path, 'rb') as f:
        f.seek(start)
        data = f.read(None if end is None else max(0, end - start))
    for raw in data.decode(errors='replace').splitlines():
        m = LINE.match(raw.strip())
        if not m:
            continue
        d = fields(m.group(2))
        d['kind'] = m.group(1)
        for k in ('tid', 'dob', 'cap', 'size', 'pos', 'limit', 'L', 'ms'):
            if k in d:
                try:
                    d[k] = int(d[k])
                except ValueError:
                    pass
        ev.append(d)
    return ev


class Buf:
    def __init__(self, dob):
        self.dob, self.live, self.peak, self.cap_after_close, self.tid, self.allocs, self.direct = dob, 0, 0, None, None, [], None

    def as_dict(self):
        return dict(dob=self.dob, live=self.live, peak=self.peak, cap_after_close=self.cap_after_close, tid=self.tid, allocs=self.allocs, direct=self.direct)


def replay(events, state=None):
    st = {} if state is None else state
    for e in events:
        b = st.setdefault(e['dob'], Buf(e['dob']))
        b.tid = e.get('tid', b.tid)
        k = e['kind']
        if k == 'alloc':
            b.live += e['size']; b.allocs.append(e['size']); b.direct = e.get('direct')
        elif k in ('grow-free', 'replaced'):
            b.live -= e['cap']
        elif k == 'closed':
            b.cap_after_close = e['cap']
        b.peak = max(b.peak, b.live)
    return st


def total(st):
    return sum(b.live for b in st.values())


if __name__ == '__main__':
    a = sys.argv[1:]
    path = a[0]
    start = int(a[a.index('--from') + 1]) if '--from' in a else 0
    end = int(a[a.index('--upto') + 1]) if '--upto' in a else None
    st = replay(parse(path, 0, end))
    if '--dob' in a:
        d = int(a[a.index('--dob') + 1])
        print(json.dumps(st[d].as_dict()))
    else:
        print(f'R={total(st)} instances={len(st)}')
        for b in sorted(st.values(), key=lambda b: -b.peak)[:20]:
            print(json.dumps(b.as_dict()))
