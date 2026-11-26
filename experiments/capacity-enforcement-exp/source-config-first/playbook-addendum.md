# Config-first addendum to the stage-3 autonomous playbook (2026-11-26)

> Given to a stage-3 autonomous agent **together with** [`../stage3-ai-deep-read/playbook-autonomous.md`](../stage3-ai-deep-read/playbook-autonomous.md)
> and [`../stage3-ai-deep-read/_TEMPLATE-autonomous.md`](../stage3-ai-deep-read/_TEMPLATE-autonomous.md), for a unit from the
> config-first lead source ([`README.md`](README.md), step 3). Where this file and the playbook differ, this file wins.
> Everything else in the playbook holds: the goal, the two tiers, the estimate, design only, the output template.

**Your target is a configuration entry, not a code location.** You are given its name, its kind (yaml entry or
JVM system property) and the line where it is declared. Start at the declaration and follow the value forward
through every getter, field and argument it flows into, to the places where it **restricts memory or disk**:
where it decides whether, or how much, memory or disk is used. Examples are a comparison, a capacity given to a
container, pool, cache or queue, a count of workers or concurrent tasks that each hold memory, or a switch that
turns such a limit on or off.

1. **List every place** you find (`file:line`, one line on what it restricts) in the first case file's notes,
   under a heading `## Config-first: places found`.
2. **Write one case file per place, at most three**, choosing the places that bound the most memory or disk.
   Each case file is a complete template of its own: the Entry pointer row is that place (linked); A1 links the
   declaration. Places beyond three stay in the list for a later unit.
3. **If the value restricts no memory or disk anywhere**, write one case file anyway. Use the place that comes
   closest as the Entry pointer, give the estimate `negative`, and state the ground. The verification solution
   then tests that usage does **not** follow the entry.
4. Add the header row `| Lead source | config-first |` right after the Pinned source row of every case file.
5. Name each file `<stem>--autonomous.md`, with the stem `[entry]-[function]-[operand]` as the playbook says.
   Use the entry's own name as `[entry]`.

Do not open anything outside the source tree you were given, in particular no other case files.
