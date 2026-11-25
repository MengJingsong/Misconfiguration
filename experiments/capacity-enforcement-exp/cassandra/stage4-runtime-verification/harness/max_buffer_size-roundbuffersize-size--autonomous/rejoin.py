# Amendment A6: under ant testsome, System.out reaches the log through SubstituteLogger one write() at a time,
# so a printf line arrives in pieces. Rejoin all pieces in order and split into records at "PROBE ".
import re, sys
pieces = []
for line in open(sys.argv[1], errors='replace'):
    m = re.search(r'SubstituteLogger\.java:\d+ - (.*)$', line.rstrip('\n'))
    if m:
        pieces.append(m.group(1))
text = ''.join(pieces)
if 'PROBE' not in text:  # output not split: fall back to whole lines
    text = ''.join(l for l in open(sys.argv[1], errors='replace') if 'PROBE' in l)
for rec in re.split(r'(?=PROBE )', text):
    rec = rec.strip()
    if rec.startswith('PROBE '):
        m = re.match(r'(PROBE MAX_BUFFER_SIZE=\d+|PROBE strategy=\S+ r=\d+ bufferSize=\d+ chunk=\d+ bufCap=\d+ dUsed=-?\d+ dOverflow=-?\d+ perReader=-?\d+)', rec)
        print(m.group(1) if m else 'UNPARSED ' + rec)
