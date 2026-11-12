#!/usr/bin/env python3
"""Write a node's cassandra.yaml from the pristine copy: set (replace or append) top-level keys and the seeds line.
usage: set-yaml.py <pristine> <out> key=value ... ; value written verbatim after 'key: '."""
import re, sys
src, out, kv = sys.argv[1], sys.argv[2], [a.split('=', 1) for a in sys.argv[3:]]
text = open(src).read()
for k, v in kv:
    if k == 'seeds':
        text, n = re.subn(r'^(\s*- seeds: ).*$', r'\g<1>' + v, text, flags=re.M); assert n == 1, 'seeds'
        continue
    text, n = re.subn(r'^' + re.escape(k) + r':.*$', f'{k}: {v}', text, flags=re.M)
    assert n <= 1, k
    if n == 0:
        text += f'\n{k}: {v}\n'
open(out, 'w').write(text)
