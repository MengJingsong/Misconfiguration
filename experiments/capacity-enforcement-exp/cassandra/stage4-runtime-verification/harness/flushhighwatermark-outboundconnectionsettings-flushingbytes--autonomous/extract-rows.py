#!/usr/bin/env python3
"""o125 runbook-defect fix #1 (B2e step 3): the test's System.out.printf reaches the ant log through
Cassandra's SubstituteLogger one write at a time, so one FHWM row is split over ~22 log lines
("FHWM,", "16384", ",", "8192", ...). This joins the tokens after each "FHWM," marker back into one
row and prints it as "FHWM,<11 fields>". Usage: extract-rows.py <unit-rN.log>"""
import re, sys
TOK = re.compile(r'SubstituteLogger\.java:\d+ - (.*)$')
toks = []
for line in open(sys.argv[1], errors='replace'):
    m = TOK.search(line.rstrip('\n'))
    if m:
        toks.append(m.group(1))
i = 0
while i < len(toks):
    if toks[i] == 'FHWM,':
        row, j = '', i + 1
        while j < len(toks) and row.count(',') < 10:
            row += toks[j]; j += 1
        # the last field follows the 10th comma
        if j < len(toks) and re.fullmatch(r'-?\d+', toks[j]) and not re.search(r',-?\d+$', row):
            row += toks[j]; j += 1
        print('FHWM,' + row)
        i = j
    else:
        i += 1
