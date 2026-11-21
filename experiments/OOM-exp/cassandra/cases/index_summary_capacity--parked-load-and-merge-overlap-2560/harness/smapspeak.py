#!/usr/bin/env python3
# R18: anonymous mappings >= 8 MiB (smaps.sh) at the sample nearest the peak RssAnon and at the last sample, excluding the
# Java heap reservation (>= 900 MiB). Usage: smapspeak.py <arm dir>
import csv, sys, collections
d = sys.argv[1].rstrip('/'); t0 = int(open(d + '/t0.txt').read())
rows = [r for r in csv.DictReader(open(d + '/sampler.csv')) if r['rss_anon_kb']]
pk = max(rows, key=lambda r: int(r['rss_anon_kb'])); tp = int(pk['epoch_ms'])
snap = collections.defaultdict(list)
for r in csv.DictReader(open(d + '/smaps.csv')): snap[int(r['epoch_ms'])].append((int(r['size_kb']), int(r['rss_kb']), r['start']))
for tag, k in (('peak', min(snap, key=lambda x: abs(x - tp))), ('last', max(snap))):
    b = sorted([x for x in snap[k] if x[0] < 900 * 1024], reverse=True)
    print(f"{tag} smaps@t0+{(k-t0)/1000:.1f}s (peak RssAnon {int(pk['rss_anon_kb'])//1024} at t0+{(tp-t0)/1000:.1f}): n={len(b)} sumSize={sum(x[0] for x in b)/1024:.1f} sumRss={sum(x[1] for x in b)/1024:.1f} MiB")
    print('   ' + ' '.join(f"{x[2]}:{x[0]/1024:.1f}/{x[1]/1024:.1f}" for x in b[:20]))
