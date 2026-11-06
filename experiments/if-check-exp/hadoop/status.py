#!/usr/bin/env python3
"""Result status of Hadoop if-check-exp stage 3 and 4 for one person.
Usage: experiments/if-check-exp/hadoop/status.py jingsong|yang"""
import csv, collections, os, sys
H = os.path.dirname(os.path.abspath(__file__))
who = sys.argv[1].lower() if len(sys.argv) > 1 else sys.exit(__doc__)
s3, s4 = (os.path.join(H, s, who) for s in ('stage3-ai-deep-read', 'stage4-runtime-verification'))
q = list(csv.DictReader(open(os.path.join(s3, 'queue.csv'))))
C = collections.Counter
def n(d): return len(os.listdir(d)) if os.path.isdir(d) else 0
print('%s: %d units in queue' % (who, len(q)))
if who == 'yang':
    for t, c in sorted(C(r['tier'] for r in q).items()):
        rs = [r for r in q if r['tier'] == t]
        print('  tier %-10s %5d  rechecked %5d  promoted %4d' % (t, len(rs), sum(1 for r in rs if r['recheck']), sum(1 for r in rs if r['promoted_band'])))
    print('  recheck results:', dict(C(r['recheck'] for r in q if r['recheck'])))
    print('  next unrechecked order:', next((r['order'] for r in q if not r['recheck'] and r['tier'] in ('1', '2', '3-sample')), 'none in tiers 1/2/3-sample'))
else:
    for b in 'ABC':
        rs = [r for r in q if r['band'] == b]
        print('  band %s %4d  written up %4d' % (b, len(rs), sum(1 for r in rs if r['case_file'])))
    print('  next unwritten order:', next((r['order'] for r in q if not r['case_file'] and not r['anchor']), 'none'))
w = [r for r in q if r['case_file']]
print('case files: %d  (cases/ has %d files)' % (len(w), n(os.path.join(s3, 'cases'))))
print('stage 4: outcome classes', dict(C(r['stage4'] for r in w)), ' results/ has %d' % n(os.path.join(s4, 'results')))
