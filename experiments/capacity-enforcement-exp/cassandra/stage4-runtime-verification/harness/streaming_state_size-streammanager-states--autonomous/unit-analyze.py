#!/usr/bin/env python3
"""Unit-tier (B2) analysis of streaming_state_size-streammanager-states--autonomous.
Reads the O53 lines of the test log and applies B2f/B2g as amended by S4-A3 and S4-A4 (frozen 2026-11-11).
usage: unit-analyze.py o53-lines.txt [--shakedown]"""
import re, sys
from collections import defaultdict
path = sys.argv[1]; shake = '--shakedown' in sys.argv
w = N = None; rows = defaultdict(list)
for line in open(path):
    m = re.search(r'O53 EMPTY=(\d+) TIMEUUID_SIZE=(\d+) w=(\d+) N=(\d+)', line)
    if m:
        empty, tus, w, N = map(int, m.groups()); continue
    m = re.search(r'O53 peer=(\w+) size=(\w+) cap=(\d+) inserted=(\d+) retained=(\d+) weightNow=(\d+) deep=(\d+)', line)
    if m:
        peer, size = m.group(1) == 'true', m.group(2)
        rows[(peer, size)].append(dict(cap=int(m.group(3)), ins=int(m.group(4)), ret=int(m.group(5)),
                                       wn=int(m.group(6)), deep=int(m.group(7))))
print(f"w = EMPTY {empty} + TIMEUUID_SIZE {tus} = {w}; N = {N}; configurations {len(rows)}")
out = []
def exp(ok, text):
    out.append(ok); print(f"EXPECTED: {'PASS' if ok else 'FAIL'}  {text}")
CAPPED = ['16KiB', '256KiB', '1MiB']
res = {}
for peer in (False, True):
    for size in CAPPED + ['40MiB']:
        s = rows[(peer, size)]
        cap = s[-1]['cap']; P = cap // w; last = s[-1]
        tail = [x['ret'] for x in s[-3:]]
        flat = max(tail) - min(tail) <= 4
        r = dict(cap=cap, P=P, plateau=last['ret'], flat=flat, tail=tail, wn=last['wn'], deep=last['deep'],
                 all_equal=all(x['ret'] == x['ins'] for x in s), final_ins=last['ins'])
        res[(peer, size)] = r
        print(f"peer={peer!s:5} size={size:6} cap={cap:9d} P={P:6d} final inserted={last['ins']} retained={last['ret']} "
              f"last3={tail} plateau*w={last['ret']*w} weightNow={last['wn']} deep={last['deep']} "
              f"wn/cap={last['wn']/cap:.3f} deep/cap={last['deep']/cap:.3f} deep/wn={last['deep']/last['wn']:.3f} "
              f"deep/entry={last['deep']/max(1,last['ret']):.1f}")
print("--- primary (B1 refutation conditions; S4-A4)")
v1 = not all(res[(p, '40MiB')]['all_equal'] for p in (False, True))
exp(not v1, "40MiB: retained = inserted at every sample (both addPeer)")
zero = [(p, s) for p in (False, True) for s in CAPPED if res[(p, s)]['plateau'] == 0]
exp(not zero, f"no capped plateau is 0 (zero: {zero})")
for p in (False, True):
    for s in CAPPED:
        r = res[(p, s)]
        exp(r['flat'], f"peer={p} {s}: flat (max-min of last 3 = {max(r['tail'])-min(r['tail'])} <= 4)")
        exp(r['plateau'] * w <= r['cap'], f"peer={p} {s}: plateau*w {r['plateau']*w} <= cap {r['cap']}")
        exp(r['deep'] <= 2 * r['cap'], f"peer={p} {s}: deep {r['deep']} <= 2*cap {2*r['cap']}")
print("--- secondary bands (deviation only; S4-A3)")
for p in (False, True):
    for s in CAPPED:
        r = res[(p, s)]
        exp(0.7 * r['P'] <= r['plateau'] <= r['P'], f"peer={p} {s}: in band 0.7*P={0.7*r['P']:.1f} <= {r['plateau']} <= P={r['P']}")
for s in CAPPED:
    r = res[(False, s)]
    exp(abs(r['deep'] / r['wn'] - 1) <= 0.20, f"peer=False {s}: weigher ~ jamm |deep/weightNow-1| = {abs(r['deep']/r['wn']-1):.3f} <= 0.20")
    exp(abs(res[(True, s)]['plateau'] - r['plateau']) <= 4, f"{s}: same plateau peer true/false {res[(True,s)]['plateau']} vs {r['plateau']}")
    q = res[(True, s)]
    exp(1.1 <= q['wn'] / q['cap'] <= 2.0, f"peer=True {s}: weightNow/cap {q['wn']/q['cap']:.3f} in [1.1, 2.0]")
    exp(1.1 <= q['deep'] / q['cap'] <= 2.0, f"peer=True {s}: deep/cap {q['deep']/q['cap']:.3f} in [1.1, 2.0]")
print("--- matched B2g row (S4-A4, first match)")
valid_caps = [s for s in CAPPED if all(res[(p, s)]['plateau'] > 0 for p in (False, True))]
def caps_ok(pred): return all(pred(res[(p, s)]) for p in (False, True) for s in valid_caps)
if v1: row = "V1 Invalid run"
elif len(valid_caps) < 2: row = "V2 invalid caps; fewer than two caps remain: Not confirmed"
elif any((not res[(p, s)]['flat']) and res[(p, s)]['plateau'] * w > res[(p, s)]['cap']
         for p in (False, True) for s in ['16KiB', '256KiB'] if s in valid_caps): row = "V3 Refuted - does not cap"
elif caps_ok(lambda r: r['flat'] and r['plateau'] * w <= r['cap']) and not caps_ok(lambda r: r['deep'] <= 2 * r['cap']):
    row = "V4 Refuted (bound) - caps (soft)"
elif caps_ok(lambda r: r['flat'] and r['plateau'] * w <= r['cap'] and r['deep'] <= 2 * r['cap']):
    row = "V5 Confirmed - caps"
else: row = "V6 Not confirmed (no matching row)"
if zero: row += f" (V2 caps excluded: {zero})"
print(("SHAKEDOWN (not a reading): " if shake else "MATCHED: ") + row)
print(f"summary: {sum(out)} PASS, {len(out)-sum(out)} FAIL")
