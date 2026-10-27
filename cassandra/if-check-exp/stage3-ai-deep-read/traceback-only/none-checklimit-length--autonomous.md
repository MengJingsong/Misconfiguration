# none — trace-back only  <!-- file: traceback-only/none-checklimit-length--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | `src/java/org/apache/cassandra/hints/ChecksummedDataInput.java:161` |
| Pinned source | `cassandra-5.0.9` |

## A. Constraint trace

**A1. The constraint.** There is no memory/disk constraint on this line. `ChecksummedDataInput.checkLimit(int length)` (ChecksummedDataInput.java:159-163) compares `getPosition() + length` against the field `limit`, which is initialised to `Long.MAX_VALUE` in `resetLimit()` (ChecksummedDataInput.java:153-157) and is set by `limit(long newLimit)` (ChecksummedDataInput.java:130-134) to `limitMark + newLimit`. The only callers that set it are `HintsReader.readHint` and `readBuffer` (HintsReader.java:234, 340), which pass `size`, the per-hint length value read from the hint file itself and validated by a CRC (HintsReader.java:218-219, 330-331), so the limit is not a configured cap. The check is a data-integrity and bookkeeping guard: it makes a deserialization that reads past the hint's declared size fail with `IOException("Digest mismatch exception")` (ChecksummedDataInput.java:162), and `HintsReader.java:240` calls `checkLimit(0)` after deserializing. The operand `length` is the byte count about to be read (ChecksummedDataInput.java:192, 199). The nearby real size cap is `max_hints_file_size`, declared at Config.java:446-447 (default 128MiB, in mebibytes, yaml key `max_hints_file_size` or the deprecated `max_hints_file_size_in_mb`, shown in cassandra.yaml:106, read via DatabaseDescriptor.java:3720, and it takes effect only on restart as a yaml entry). However, it is enforced in `HintsWriteExecutor.java:239-247` when writing a hints file, not on this line.
