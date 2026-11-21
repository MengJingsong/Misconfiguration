#!/usr/bin/env python3
"""U6: read `jcmd <pid> Thread.print` on stdin; print one line: ntr lex err parse prep measure
ntr = Native-Transport-Requests threads; lex = of those, with a CqlLexer / org.antlr.runtime.Lexer.nextToken frame;
err = of those, with an ErrorCollector.syntaxError frame; parse = with a CqlParser frame (and no lexer frame);
prep = with a parseAndPrepare / prepare( frame of QueryProcessor; measure = with an ObjectSizes.measureDeep frame."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = lex = err = parse = prep = meas = 0
for b in blocks:
    if not b.startswith('"Native-Transport-Requests'): continue
    ntr += 1
    lx = 'CqlLexer' in b or 'org.antlr.runtime.Lexer.nextToken' in b
    if lx: lex += 1
    if 'ErrorCollector.syntaxError' in b: err += 1
    if 'CqlParser' in b and not lx: parse += 1
    if 'QueryProcessor.parseAndPrepare' in b or 'QueryProcessor.prepare(' in b: prep += 1
    if 'ObjectSizes.measureDeep' in b or 'MemoryMeter' in b: meas += 1
print(ntr, lex, err, parse, prep, meas)
