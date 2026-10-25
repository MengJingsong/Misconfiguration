#!/usr/bin/env python3 -I
"""Reduce the full cluster cell folders (pulled from the node) to small committed excerpts.
usage: make-cluster-excerpts.py <pulled dir with <cell>/> <run1 dir>   (writes <run1>/cluster/<cell>/)"""
import os, re, shutil, sys
src, dst = sys.argv[1], os.path.join(sys.argv[2], 'cluster')
for cell in sorted(os.listdir(src)):
    d = os.path.join(src, cell)
    if not os.path.exists(d + '/summary.txt'): continue
    o = os.path.join(dst, cell); os.makedirs(o, exist_ok=True)
    for f in ('summary.txt', 'settings.txt', 'yaml.diff', 'phases.csv', 'sampler.summary', 'sampler.events', 'du.txt', 'cdc-verdict.txt', 'freed-up-excerpt.txt'):
        if os.path.exists(os.path.join(d, f)): shutil.copy(os.path.join(d, f), o)
    # sampler.csv: keep the header, the first and last rows and every row whose (links, link_bytes, idx_files) differs from the previous one
    rows = open(d + '/sampler.csv').read().splitlines()
    keep = [rows[0]]; prev = None
    for i, l in enumerate(rows[1:], 1):
        k = tuple(l.split(',')[1:3] + l.split(',')[4:5])
        if k != prev or i == len(rows) - 1: keep.append(l)
        prev = k
    open(o + '/sampler-changes.csv', 'w').write('\n'.join(keep) + '\n')
    st = open(d + '/stress-W.txt', errors='replace').read().splitlines()
    sel = [l for l in st if re.match(r'(Op rate|Total partitions|Total errors|Total operation time|Running with|Results:|END)', l.strip())]
    open(o + '/stress-W-results.txt', 'w').write('\n'.join(sel[:40]) + '\n')
    # counts from the node's logs (pulled alongside when present)
    cnt = []
    for f, pat, tag in (('system.log', r'^WARN.*Rejecting mutation to keyspace', 'WARN_Rejecting'), ('system.log', r'^ERROR', 'ERROR_lines'),
                        ('system.log', r'CDCWriteException', 'CDCWriteException_mentions'), ('debug.log', r'Freed up', 'FreedUp_debug')):
        p = os.path.join(d, f)
        n = sum(1 for l in open(p, errors='replace') if re.search(pat, l)) if os.path.exists(p) else -1
        cnt.append('%s=%d' % (tag, n))
    open(o + '/log-counts.txt', 'w').write(' '.join(cnt) + '\n')
