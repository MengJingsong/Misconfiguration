# Scripts of the short-path executor's run (memtable_heap_space)

Written by the executor during its run, 2026-10-06. It kept them in its session scratchpad and on pc80 (`~/short-run/<stem>/`),
not in `harness/`, so the reviewer copied them here afterwards (the node copies were identical to the scratchpad copies).
They are the executor's work, unedited. Also saved by the reviewer, from the node:
`cluster1-clone.diff`, `cluster2-clone.diff`: `git diff` of each cluster clone's `conf`, `bin` and `build.xml` against the tag,
that is, the configuration actually in force for the 64 MiB and 512 MiB runs.
