# B3c step 5: CSV of ROWS lines "0,<ck>,1[,1]"; ck = 5-digit row number followed by 39995 'a' (40,000 chars).
# usage: python3 -I gencsv.py <out.csv> <rows> <a|b>
import sys
out, rows, kind = sys.argv[1], int(sys.argv[2]), sys.argv[3]
tail = ',1,1\n' if kind == 'b' else ',1\n'
with open(out, 'w') as f:
    for i in range(rows):
        f.write('0,' + ('%05d' % i) + 'a' * 39995 + tail)
