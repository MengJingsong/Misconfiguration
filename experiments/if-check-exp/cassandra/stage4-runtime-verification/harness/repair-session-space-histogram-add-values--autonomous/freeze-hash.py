#!/usr/bin/env python3
"""usage: freeze-hash.py <case file>. Prints the sha256 of the prediction and conclusion tables (B2f-g and B3f-g: the text from '**B2f.' to '**B2h.' and from '**B3f.' to '**B3h.') and of the whole file."""
import hashlib, sys
p = sys.argv[1]; s = open(p).read()
seg = lambda a, b: s[s.index(a):s.index(b)]
t = seg('**B2f.', '**B2h.') + seg('**B3f.', '**B3h.')
print('tables', hashlib.sha256(t.encode()).hexdigest())
print('file  ', hashlib.sha256(open(p, 'rb').read()).hexdigest())
