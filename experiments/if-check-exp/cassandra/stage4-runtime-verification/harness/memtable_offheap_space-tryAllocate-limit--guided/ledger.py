#!/usr/bin/env python3
"""Read the region ledger of memtable_offheap_space-tryAllocate-limit (region-ledger.btm), case §9a/§9d.

usage: ledger.py <ledger.txt> [--idle-ms MS] [--from-ms MS] [--to-ms MS] [--json FILE]

L(t) = bytes of NativeAllocator regions built (malloc) and not yet freed, taken in file order (the order the
rules ran). Prints:
  - line counts per kind; frees whose peer is not live (should be 0) and mallocs of a peer already live (0);
  - L_idle = L after the last line with ms <= --idle-ms (or 0 if none);
  - max L over lines with --from-ms <= ms <= --to-ms (default: the whole file), and when;
  - per discard (a 'discard' .. 'discarded' bracket of one allocator): A_m = owns at entry, P_m = the region
    bytes it frees, P_m - A_m, and whether 0 <= P_m - A_m <= 1 MiB + 0.002 * A_m (case §9a);
  - regions still live at the end, and how many of them were never in a discard (race stash or live memtables).
"""
import argparse, json, re, sys

MIB = 1048576
LINE = re.compile(r'^(malloc|free|discard|discarded) (.*)$')


def fields(rest):
    return dict(kv.split('=', 1) for kv in rest.split() if '=' in kv)


def read(path):
    out = []
    with open(path) as f:
        for n, raw in enumerate(f, 1):
            m = LINE.match(raw.strip())
            if not m:
                out.append(('bad', {'line': n, 'raw': raw.strip()[:120]}))
                continue
            out.append((m.group(1), fields(m.group(2))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ledger')
    ap.add_argument('--idle-ms', type=int)
    ap.add_argument('--from-ms', type=int)
    ap.add_argument('--to-ms', type=int)
    ap.add_argument('--json')
    a = ap.parse_args()

    ev = read(a.ledger)
    live = {}                 # peer -> cap
    L = 0
    counts = {'malloc': 0, 'free_race': 0, 'free_discard': 0, 'discard': 0, 'discarded': 0, 'bad': 0}
    unmatched_free = 0
    double_malloc = 0
    L_idle = 0
    maxL, maxL_ms = None, None
    open_discards = {}        # alloc id -> {'owns', 'ms', 'freed', 'n'}
    discards = []
    last_ms = None
    for kind, f in ev:
        if kind == 'bad':
            counts['bad'] += 1
            continue
        ms = int(f['ms'])
        last_ms = ms
        if kind == 'malloc':
            counts['malloc'] += 1
            peer, cap = f['peer'], int(f['cap'])
            if peer in live:
                double_malloc += 1
                L -= live[peer]
            live[peer] = cap
            L += cap
        elif kind == 'free':
            site = f.get('site')
            counts['free_' + site] += 1
            peer, cap = f['peer'], int(f['cap'])
            if peer in live:
                L -= live.pop(peer)
            else:
                unmatched_free += 1
            if site == 'discard':
                d = open_discards.get(f.get('alloc'))
                if d is not None:
                    d['freed'] += cap
                    d['n'] += 1
        elif kind == 'discard':
            counts['discard'] += 1
            open_discards[f['alloc']] = {'alloc': f['alloc'], 'owns': int(f['owns']), 'ms': ms, 'freed': 0, 'n': 0}
        elif kind == 'discarded':
            counts['discarded'] += 1
            d = open_discards.pop(f['alloc'], None)
            if d is not None:
                d['gap'] = d['freed'] - d['owns']
                d['bound'] = MIB + 0.002 * d['owns']
                d['within'] = 0 <= d['gap'] <= d['bound']
                discards.append(d)
        if a.idle_ms is not None and ms <= a.idle_ms:
            L_idle = L
        in_window = (a.from_ms is None or ms >= a.from_ms) and (a.to_ms is None or ms <= a.to_ms)
        if in_window and (maxL is None or L > maxL):
            maxL, maxL_ms = L, ms

    res = {
        'counts': counts, 'unmatched_free': unmatched_free, 'double_malloc': double_malloc,
        'L_idle': L_idle, 'max_L': maxL, 'max_L_ms': maxL_ms, 'L_end': L, 'last_ms': last_ms,
        'live_regions_end': len(live), 'open_discards_end': len(open_discards),
        'discards': discards,
    }
    big = [d for d in discards if d['owns'] >= 8 * MIB]
    res['discards_ge_8MiB'] = len(big)
    res['discards_outside_bound'] = [d for d in discards if not d['within']]

    print(f"ledger {a.ledger}: {counts}; unmatched frees {unmatched_free}; mallocs of a live peer {double_malloc}")
    print(f"L_idle={L_idle} B ({L_idle / MIB:.3f} MiB) at idle-ms={a.idle_ms}")
    if maxL is not None:
        print(f"max L={maxL} B ({maxL / MIB:.3f} MiB) at ms={maxL_ms}; max L - L_idle = {(maxL - L_idle) / MIB:.3f} MiB"
              f" (window {a.from_ms}..{a.to_ms})")
    print(f"L at end={L} B ({L / MIB:.3f} MiB) in {len(live)} live regions; discards still open: {len(open_discards)}")
    print(f"discards: {len(discards)} closed, {len(big)} with owns >= 8 MiB, "
          f"{len(res['discards_outside_bound'])} outside 0 <= P_m - A_m <= 1 MiB + 0.002 A_m")
    for d in big:
        print(f"  discard alloc={d['alloc']} ms={d['ms']} A_m={d['owns']} P_m={d['freed']} regions={d['n']} "
              f"P_m-A_m={d['gap']} ({d['gap'] / MIB:.3f} MiB, bound {d['bound'] / MIB:.3f}) "
              f"P_m/A_m={d['freed'] / d['owns']:.5f} {'ok' if d['within'] else 'OUTSIDE'}")
    if a.json:
        with open(a.json, 'w') as f:
            json.dump(res, f, indent=1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
