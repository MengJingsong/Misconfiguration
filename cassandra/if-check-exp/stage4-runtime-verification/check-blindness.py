#!/usr/bin/env python3
"""Check that a stage-4 executor session stayed blind to the other path.

    python3 check-blindness.py --stem <stem> --for short
    python3 check-blindness.py --stem <stem> --for long [--transcript FILE]

Scans the tool calls (not the prompt) of a Claude Code session transcript for
paths the executor of that path must not touch, and prints every hit. Zero hits
is the pass. By default it reads the newest transcript under
~/.claude/projects/ (any project folder: a session started in ~/repos or in the
repo lands in different ones) and prints the first words of its first prompt so
you can confirm it is the executor's session; pass --transcript FILE to pick one.
"""
import argparse, glob, json, os, sys

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('--stem', required=True)
ap.add_argument('--for', dest='path', choices=['short', 'long'], required=True,
                help='which path\'s executor the transcript belongs to')
ap.add_argument('--transcript')
a = ap.parse_args()
s = a.stem

if a.path == 'short':      # the short executor must not see the long path
    bad = ['HANDOFF.md', 'stage3-ai-deep-read/long-path/', 'comparison/',
           'stage4-runtime-verification/long-path/']
else:                      # the long executor must not see the short path
    bad = ['HANDOFF.md', 'stage3-ai-deep-read/short-path/', 'comparison/',
           'stage4-runtime-verification/short-path/']

f = a.transcript
if not f:
    files = glob.glob(os.path.expanduser('~/.claude/projects/*/*.jsonl'))
    if not files:
        sys.exit('no transcripts found; pass --transcript FILE')
    f = max(files, key=os.path.getmtime)

def first_prompt(path):
    for line in open(path, encoding='utf-8', errors='replace'):
        try: e = json.loads(line)
        except Exception: continue
        if e.get('type') == 'user':
            m = e.get('message', {}).get('content')
            if isinstance(m, list):
                m = ' '.join(x.get('text', '') for x in m if isinstance(x, dict))
            return ' '.join((m or '').split())[:140]
    return '?'

print(f'checking {f}\nfirst prompt: {first_prompt(f)!r}\n')
hits = 0
for line in open(f, encoding='utf-8', errors='replace'):
    try: e = json.loads(line)
    except Exception: continue
    if e.get('type') != 'assistant': continue
    for c in e.get('message', {}).get('content', []) or []:
        if isinstance(c, dict) and c.get('type') == 'tool_use':
            inp = json.dumps(c.get('input', {}))
            if any(b in inp for b in bad):
                hits += 1
                print(f"{c.get('name')}: {inp[:220]}")
print(f'\n{hits} tool call(s) touched paths blocked for the {a.path}-path executor of {s}\n(transcript: {f})')
sys.exit(1 if hits else 0)
