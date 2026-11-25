#!/usr/bin/env python3
"""B28: read `jcmd <pid> Thread.print` on stdin; print one line:
ntr ntr_runnable ntr_lexer ntr_tracekeyspace ntr_formatter tracing_top
ntr = Native-Transport-Requests threads; ntr_lexer = with Cql_Lexer/CqlLexer/ANTLR in the stack; ntr_tracekeyspace = with
TraceKeyspace in the stack; ntr_formatter = with slf4j MessageFormatter in the stack; tracing_top = the TracingStage
thread's first frame in {CommitLog.add, waitForMemory/allocate, responseHandler/get, park, other} (one word)."""
import sys
blocks = sys.stdin.read().split('\n\n')
ntr = run = lex = tk = fm = 0; ttop = 'none'
for b in blocks:
    if b.startswith('"Native-Transport-Requests'):
        ntr += 1
        if 'java.lang.Thread.State: RUNNABLE' in b: run += 1
        if 'CqlLexer' in b or 'Cql_Lexer' in b or 'org.antlr' in b: lex += 1
        if 'TraceKeyspace' in b: tk += 1
        if 'MessageFormatter' in b: fm += 1
    elif b.startswith('"TracingStage'):
        fr = [l.strip()[3:] for l in b.splitlines() if l.strip().startswith('at ')]
        word = 'idle'
        for f in fr:
            if 'CommitLog.add' in f or 'CommitLogSegment' in f: word = 'commitlog'; break
            if 'waitForMemory' in f or 'MemtableAllocator' in f or 'MemtablePool' in f: word = 'memtable-wait'; break
            if 'AbstractWriteResponseHandler.get' in f or 'responseHandler' in f: word = 'wait-response'; break
            if 'StorageProxy' in f or 'Mutation' in f or 'Keyspace.apply' in f: word = 'apply'; break
        if word == 'idle' and fr and 'LinkedBlockingQueue.take' not in b and 'park' not in fr[0]: word = 'other:' + fr[0].split('(')[0][-40:]
        ttop = word
print(ntr, run, lex, tk, fm, ttop)
