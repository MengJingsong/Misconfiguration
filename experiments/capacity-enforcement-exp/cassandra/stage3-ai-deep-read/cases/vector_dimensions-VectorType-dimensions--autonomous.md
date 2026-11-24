# vector_dimensions (guardrail `vector_dimensions_fail_threshold`) — verification solution  <!-- file: cases/vector_dimensions-VectorType-dimensions--autonomous.md -->

| Field | Value |
|---|---|
| Entry pointer | the given line (a capacity-set place: the UDF-side driver `VectorType` stores its dimension count), **linked**: [`VectorType.java:36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/VectorType.java#L36) (`this.dimensions = dimensions;`) |
| Pinned source | `cassandra-5.0.9` |
| Session / date | claude-opus-5-5, Claude Code 2.1.330, 2026-11-24 |
| Estimate | `negative`. The dimension count stored at line 36 sizes the UDF codec's heap buffers exactly (4·D bytes for `float`), but the only configured limit on D, the `vector_dimensions` guardrail, is checked only for table columns and UDT fields. It is never checked for the argument and return types of `CREATE FUNCTION`/`CREATE AGGREGATE`, which is where this driver type comes from, so heap use at this place follows D whatever the threshold is. |
| Ground | Bypass by construction. `CreateFunctionStatement` prepares its argument and return types without calling `CQL3Type.Raw.validate` (`CreateFunctionStatement.java:110-114`), and that method is the only place `Guardrails.vectorDimensions.guard` is called (`CQL3Type.java:727`, `:925`). So D at line 36 is any positive `int` written in the function signature, and `VectorCodec.FixedLength.serialize` allocates `4·D` bytes per call (`VectorCodec.java:90`, `:106`). Separately, the guardrail is off by default (`-1`) and skips superusers and internal calls. |

## A. Constraint trace

**A1. The constraint.**

- **Name:** `vector_dimensions`, a guardrail (`MaxThreshold`) with two keys, `vector_dimensions_warn_threshold` and `vector_dimensions_fail_threshold`. Only the fail threshold rejects anything; the warn threshold only emits a client warning.
- **Kind:** configuration entry (a guardrail threshold).
- **First declared:** [`Config.java:924-925`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/config/Config.java#L924-L925) (`public volatile int vector_dimensions_warn_threshold = -1;` / `..._fail_threshold = -1;`).
  - Guardrail object: `Guardrails.java:419-425`.
  - Getters and setter: `GuardrailsOptions.java:706-728`. Startup validation: `GuardrailsOptions.java:85`.
- **Unit:** dimensions, i.e. the element count of one vector type.
- **Default:** `-1` (disabled). `MaxThreshold.failValue` maps any value `<= 0` to `Long.MAX_VALUE` (`MaxThreshold.java:56-60`), and a value fails when `D > fail` (`MaxThreshold.java:50-53`). The default is shown commented out in `conf/cassandra.yaml:2183-2186`.
- **How to set it:**
  - yaml keys `vector_dimensions_warn_threshold` / `vector_dimensions_fail_threshold`. A change needs a restart.
  - JMX `org.apache.cassandra.db:type=Guardrails`, `setVectorDimensionsThreshold(int warn, int fail)` (`GuardrailsMBean.java:603-614`, `Guardrails.java:1150-1153`). This takes effect live, because the fields are `volatile`.

The capacity set at the target line is the dimension count `D` of the **driver-side** type `org.apache.cassandra.cql3.functions.types.VectorType`. This is the Java-driver type system that Cassandra embeds for UDFs and `CQLSSTableWriter`.

- The constructor takes `D` and stores it at [`VectorType.java:36`](https://github.com/apache/cassandra/blob/cassandra-5.0.9/src/java/org/apache/cassandra/cql3/functions/types/VectorType.java#L36), after a bare `assert dimensions > 0` (`:34`). There is no upper bound.
- `D` reaches the constructor through this chain:
  1. `DataType.vector` (`DataType.java:448-451`)
  2. `DataTypeClassNameParser.parseOne` (`DataTypeClassNameParser.java:122-128`), which does `Integer.parseInt` on the server type string
  3. `JavaDriverUtils.driverType` / `codecFor` (`JavaDriverUtils.java:55-83`)
  4. `UDFDataType` (`UDFDataType.java:69-73`)
  5. `UDFunction`, for every argument and return type (`UDFunction.java:219-220`)
- Where `D` originally comes from: the integer literal in `vector<T, D>` in CQL (`Parser.g:1916-1918`). The server-side `db.marshal.VectorType` only checks `D > 0` (`db/marshal/VectorType.java:86-90`).

**A2. What it caps.**

- **Intended:** the guardrail limits the dimension count D of a vector type declared by an ordinary user in DDL. That bounds the size of each vector value (4·D bytes for `float`/`int`), and so the heap, network and disk used per value.
- **The quantity compared:** D, the declared dimension, against `fail_threshold` (`Threshold.java:128-143`).
- **At the target place:** the resource is **heap**. The quantity that D sizes is:
  - `FixedLength.valueLength = subtypeCodec.serializedSize() * D` (`VectorCodec.java:90`). Each UDF result serialization does `ByteBuffer.allocate(valueLength)` (`:106`).
  - When an argument is deserialized, the codec builds a list of D boxed elements (`:131-144`; variable-length elements: `:193-203`).

**A3. Mechanism.**

1. **Where the guardrail fires.** It fires only from `CQL3Type.Raw.validate`, in two places:
   - `RawType.validate`, `CQL3Type.java:721-729`
   - `RawVector.validate`, `CQL3Type.java:922-926`: `Guardrails.vectorDimensions.guard(dimension, name, false, state)`

   Collections, tuples and UDT references recurse into these (`CQL3Type.java:799-805`, `:1043-1046`).
2. **Who calls `validate`.** Only these statements:
   - `CreateTableStatement.java:154` and `:603`
   - `AlterTableStatement.java:275`
   - `CreateTypeStatement.java:74`
   - `AlterTypeStatement.java:156`
3. **What `guard` does.**
   - `Guardrail.enabled(state)` is false for superusers and for internal calls (`Guardrail.java:93-96`, `ClientState.java:594-605`). This includes every user when the authenticator does not require authentication (`ClientState.java:602-605`).
   - Otherwise, if `D > fail`, the statement is rejected with `GuardrailViolatedException` ("… has a vector of D dimensions, this exceeds the failure threshold of F."). If `D > warn`, a warning is sent to the client and logged (`Threshold.java:128-143`).
   - It is a one-time DDL check. Nothing at run time ever compares a value against the threshold.
4. **UDF path, which is the bypass.**
   - `CreateFunctionStatement.apply` prepares `rawArgumentTypes` and `rawReturnType` with `prepare(...).getType().udfType()` (`CreateFunctionStatement.java:110-114`). It never calls `validate`. `CreateAggregateStatement` does not call it either.
   - So an ordinary user, with the guardrail set to 16, can create `RETURNS vector<float, 100000000>` or an argument `x vector<float, 100000000>`.
   - `UDFunction.create` then wraps the types (`UDFunction.java:219-220`) and the driver `VectorType` is built with D = 100,000,000. That is the target line.
5. **Run-time use of D at that place.**
   - Return path: the generated UDF class calls `decompose(…, result)` (`src/resources/org/apache/cassandra/cql3/functions/JavaSourceUDF.txt:44`), which calls `UDFDataType.decompose` (`UDFDataType.java:191-199`) and then `VectorCodec.FixedLength.serialize`.
   - `serialize` allocates `valueLength = 4·D` bytes **before** reading the list (`VectorCodec.java:106`). It then iterates D times (`:107-112`), so a shorter list fails with `NoSuchElementException` after the allocation.
   - Argument path: `UDFDataType.compose` (`:175-180`) calls `FixedLength.deserialize`, which loops D times and builds an `ImmutableList` of D boxed values (`VectorCodec.java:125-144`).
   - With threads enabled (the default, `Config.java:627`), the UDF runs on the UDF executor (`UDFunction.java:376-378`, `:466-540`). The only limit there is CPU time (`user_defined_functions_fail_timeout`, default 1500 ms, `Config.java:653`). There is no memory accounting.
6. **Other bypasses and overshoots.**
   - **Vector literals.** A literal gets its type from its element count (`Vectors.java:152-154`) and never passes the guardrail. For a UDF argument, the type comes from the function signature.
   - **Lowered thresholds.** Lowering a threshold does not re-check existing columns or functions.
   - **Excluded users.** Superusers, internal calls and `AllowAllAuthenticator` deployments are exempt.
   - **Overflow.** For D > 536,870,911, `4·D` overflows `int`. `ByteBuffer.allocate` then throws `IllegalArgumentException` and nothing is allocated. That is an accident, not a cap.

**A4. Other consumers.**

- Same heap, sized by D outside this constraint:
  - The server-side `db.marshal.VectorType` serializers (`db/marshal/VectorType.java:184`, `:447`, `:471`, `:486`, `:498`).
  - `CQLSSTableWriter`, which uses driver types too (`CQLSSTableWriter.java:150`).
  - The client response that carries a UDF result.
- Limits that do apply on other paths:
  - Inbound bound values are bounded by the native-protocol message size, which is a separate constraint.
  - The UDF CPU timeout bounds how long, but not how much, a UDF allocates.
  - The JVM heap size is the final bound.

**A5. Evidence beyond the source.**

- `CHANGES.txt:455` "Add guardrail for vector dimensions (CASSANDRA-18730)", https://issues.apache.org/jira/browse/CASSANDRA-18730
- `CHANGES.txt:477` "Add support for vectors in UDFs (CASSANDRA-18613)", https://issues.apache.org/jira/browse/CASSANDRA-18613
- `test/unit/org/apache/cassandra/db/guardrails/GuardrailVectorDimensionsTest.java` covers CREATE/ALTER TABLE and CREATE/ALTER TYPE only. It has no `CREATE FUNCTION` case, which is consistent with the bypass.
- `test/unit/org/apache/cassandra/cql3/validation/operations/CQLVectorTest.java:400-500` shows UDFs with `vector<…>` arguments and return types (e.g. `RETURNS vector<double, 3> … 'return Arrays.asList(…)'`).
- JDK 11 docs:
  - `com.sun.management.ThreadMXBean#getThreadAllocatedBytes`: https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html
  - JFR event `jdk.ObjectAllocationOutsideTLAB` and the `jfr` tool: https://docs.oracle.com/en/java/javase/11/tools/jfr.html

## B. Verification solution

**B1. Claim under test.** With `vector_dimensions_fail_threshold` set to 16 and a non-superuser authenticated session, a UDF whose signature declares `vector<float, D>` with D far above 16 is still created. Each call allocates heap proportional to D (≥ 4·D bytes in `VectorCodec$FixedLength.serialize`), so heap use at the target line follows D and not the guardrail, while the guardrail does reject a table column of the same D for the same user.

### B2. Unit tier

**B2a. Environment and build.**

- Linux, JDK 11 (`java -version` shows 11.x), Apache Ant ≥ 1.10.
- Copy the tree to local disk. Never build in the shared tree:
  ```bash
  WORK=/local-scratch/vd-unit   # any local disk with >= 10 GB free
  mkdir -p $WORK
  rsync -a ~/cassandra-5.0.9/ $WORK/src/
  cd $WORK/src
  ```
- Build with `ant -Dno-checkstyle=true jar build-test`. The first run resolves dependencies from Maven Central.
- Test source: `test/unit/org/apache/cassandra/db/guardrails/VectorDimsUdfBypassTest.java`, in the copy, contents below. It extends the in-tree `GuardrailTester`, which starts an in-JVM node with `PasswordAuthenticator` and an ordinary user `guardrail_user` (`GuardrailTester.java:113-150`). The test `conf/cassandra.yaml` already has `user_defined_functions_enabled: true` (`test/conf/cassandra.yaml:46`).
- JVM options: the `testsome` default `maxmemory="1024m"` (`build.xml:1153`). No change is needed.

```java
package org.apache.cassandra.db.guardrails;

import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.NoSuchElementException;

import org.junit.Test;

import org.apache.cassandra.cql3.functions.types.TypeCodec;
import org.apache.cassandra.db.marshal.FloatType;
import org.apache.cassandra.db.marshal.VectorType;
import org.apache.cassandra.transport.ProtocolVersion;
import org.apache.cassandra.transport.messages.ResultMessage;
import org.apache.cassandra.utils.JavaDriverUtils;

public class VectorDimsUdfBypassTest extends GuardrailTester
{
    static final int[] DIMS = { 16, 17, 1_000, 1_000_000 };
    static final int BIG = 50_000_000;                 // codec-only (step 2), no CQL round trip
    static final com.sun.management.ThreadMXBean TMX =
        (com.sun.management.ThreadMXBean) ManagementFactory.getThreadMXBean();

    static long alloc() { return TMX.getThreadAllocatedBytes(Thread.currentThread().getId()); }

    @Test
    public void run() throws Throwable
    {
        execute(systemClientState, "CREATE TABLE IF NOT EXISTS " + keyspace() + ".base (k int PRIMARY KEY)");
        execute(systemClientState, "INSERT INTO " + keyspace() + ".base (k) VALUES (0)");
        int[][] settings = { { 8, 16 }, { -1, -1 } };   // {warn, fail}
        for (int[] s : settings)
        {
            Guardrails.instance.setVectorDimensionsThreshold(s[0], s[1]);
            String tag = s[1] < 0 ? "off" : "f" + s[1];
            for (int d : DIMS) measure(tag, d, true);
            measure(tag, BIG, false);
        }
        Guardrails.instance.setVectorDimensionsThreshold(-1, -1);
    }

    private void measure(String tag, int d, boolean cql) throws Throwable
    {
        // 1. the operand stored at cql3/functions/types/VectorType.java:36
        org.apache.cassandra.cql3.functions.types.VectorType dt =
            (org.apache.cassandra.cql3.functions.types.VectorType)
            JavaDriverUtils.driverType(VectorType.getInstance(FloatType.instance, d));
        TypeCodec<Object> codec = JavaDriverUtils.codecFor(dt);

        // 2. codec heap use on this thread
        String emptyOutcome = "ok";
        long a = alloc();
        try { codec.serialize(new ArrayList<Float>(), ProtocolVersion.CURRENT); }
        catch (NoSuchElementException e) { emptyOutcome = "NoSuchElementException"; }
        long serEmpty = alloc() - a;

        long serFull = -1, deser = -1, serFullLen = -1;
        if (cql)
        {
            a = alloc();
            ByteBuffer out = codec.serialize(Collections.nCopies(d, 0.0f), ProtocolVersion.CURRENT);
            serFull = alloc() - a; serFullLen = out.remaining();
            ByteBuffer in = ByteBuffer.allocate(4 * d);
            a = alloc();
            List<?> l = (List<?>) codec.deserialize(in, ProtocolVersion.CURRENT);
            deser = alloc() - a;
            if (l.size() != d) throw new AssertionError("size " + l.size());
        }

        // 3. positive control: same D as a table column, ordinary user
        String table;
        try { execute(userClientState, "CREATE TABLE " + keyspace() + ".tpc_" + tag + "_" + d + " (k int PRIMARY KEY, v vector<float, " + d + ">)"); table = "created"; }
        catch (GuardrailViolatedException e) { table = "REJECTED"; }

        // 4. same D in a UDF signature, ordinary user, end to end through CQL
        String fn = "created", retLen = "-", argSize = "-";
        if (cql)
        {
            String mk = keyspace() + ".mk_" + tag + "_" + d, sz = keyspace() + ".sz_" + tag + "_" + d;
            try
            {
                execute(userClientState, "CREATE FUNCTION " + mk + "() CALLED ON NULL INPUT RETURNS vector<float, " + d + "> LANGUAGE java AS 'return Collections.nCopies(" + d + ", 0.0f);'");
                execute(userClientState, "CREATE FUNCTION " + sz + "(x vector<float, " + d + ">) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return x == null ? 0 : x.size();'");
                ResultMessage.Rows r = (ResultMessage.Rows) execute(userClientState, "SELECT " + mk + "() FROM " + keyspace() + ".base WHERE k = 0");
                retLen = String.valueOf(r.result.rows.get(0).get(0).remaining());
                r = (ResultMessage.Rows) execute(userClientState, "SELECT " + sz + "(?) FROM " + keyspace() + ".base WHERE k = 0",
                                                 Collections.singletonList(ByteBuffer.allocate(4 * d)));
                argSize = String.valueOf(r.result.rows.get(0).get(0).getInt(0));
            }
            catch (GuardrailViolatedException e) { fn = "REJECTED"; }
        }

        System.out.printf("RESULT th=%s D=%d dims@36=%d valueLen=%d serEmpty=%d(%s) serFull=%d serFullLen=%d deser=%d table=%s udf=%s udfRetLen=%s udfArgSize=%s%n",
                          tag, d, dt.getDimensions(), codec.serializedSize(), serEmpty, emptyOutcome, serFull, serFullLen, deser, table, fn, retLen, argSize);
    }
}
```

**B2b. Knobs.**

- **Guardrail setting**, set with `Guardrails.instance.setVectorDimensionsThreshold(warn, fail)` (the JMX setter, `Guardrails.java:1150-1153`):
  - `(8, 16)`: a small, binding limit.
  - `(-1, -1)`: the default, disabled. This is the "knob moved" comparison.
- **D** ∈ {16, 17, 1,000, 1,000,000, 50,000,000}:
  - 16 is at the limit and allowed.
  - 17 is just over it.
  - 1,000 and 1,000,000 are three and six orders past it.
  - 50,000,000 is codec-only: a 200 MB buffer, within the 1 GB test heap.

**B2c. Workload.**

- **Steps 1–2:** build the driver type and codec for `vector<float, D>`, then serialize an empty list. That allocates `4·D` and then throws. Then serialize `Collections.nCopies(D, 0f)` (a 4·D-byte result) and deserialize a 4·D-byte zero buffer (D boxed floats).
- **Step 3:** `CREATE TABLE` with the same D as the ordinary user (positive control).
- **Step 4:** the same ordinary user creates a returning UDF and an argument UDF with that D and calls both through CQL.
- **Arithmetic:** D = 17 > 16 already exceeds the fail limit. D = 1,000,000 exceeds it by a factor of 62,500 and gives a 4,000,000-byte value. D = 50,000,000 gives a 200,000,000-byte allocation.

**B2d. Observables and instruments.**

- **The operand at line 36:** `dt.getDimensions()`, plus `codec.serializedSize()` (= 4·D).
- **Heap allocated on the calling thread:** `com.sun.management.ThreadMXBean.getThreadAllocatedBytes`, read before and after each codec call. This is exact per-thread allocation, not live heap.
- **Guardrail outcome:** whether `GuardrailViolatedException` is thrown for the table and for the function.
- **UDF result length and argument size**, read from the result rows.
- **Not observable here:** allocation inside the UDF executor thread in step 4, which is a different thread. There the result length (= 4·D) stands in, and the cluster tier measures the actual allocation with JFR.
- **Output:** the `RESULT` lines go to stdout and are captured in `build/test/output/TEST-org.apache.cassandra.db.guardrails.VectorDimsUdfBypassTest.xml`.

**B2e. Procedure.**

1. `cd $WORK/src` and write the test file above to `test/unit/org/apache/cassandra/db/guardrails/VectorDimsUdfBypassTest.java`.
2. Run:
   ```bash
   ant testsome -Dtest.name=org.apache.cassandra.db.guardrails.VectorDimsUdfBypassTest 2>&1 | tee $WORK/unit.log
   ```
3. Collect the results:
   ```bash
   grep -h RESULT build/test/output/TEST-org.apache.cassandra.db.guardrails.VectorDimsUdfBypassTest*.xml | sed 's/^.*RESULT/RESULT/' > $WORK/unit-results.txt
   ```
4. Run `pgrep -f VectorDimsUdfBypassTest` and confirm it prints nothing (the forked JUnit JVM has exited).

**B2f. Predictions** (identical for `th=f16` and `th=off` unless a row says otherwise)

| D | dims@36 | valueLen | serEmpty | serFull / serFullLen | deser | table (f16) | table (off) | udf | udfRetLen / udfArgSize |
|---|---|---|---|---|---|---|---|---|---|
| 16 | 16 | 64 | < 4 KiB, NoSuchElementException | small / 64 | small | created | created | created | 64 / 16 |
| 17 | 17 | 68 | < 4 KiB | small / 68 | small | **REJECTED** | created | created | 68 / 17 |
| 1,000 | 1000 | 4000 | 4,000–8,000 B | ≥ 4,000 / 4000 | ≥ 16,000 B | **REJECTED** | created | created | 4000 / 1000 |
| 1,000,000 | 1,000,000 | 4,000,000 | 4,000,000–4,100,000 B | ≥ 4,000,000 / 4,000,000 | ≥ 16,000,000 B | **REJECTED** | created | created | 4,000,000 / 1,000,000 |
| 50,000,000 | 50,000,000 | 200,000,000 | 200,000,000–200,100,000 B | (not run) | (not run) | **REJECTED** | created | (not run) | – |

The relation the claim needs:

- `serEmpty ≈ 4·D` (the slope between D = 1,000,000 and D = 50,000,000 is 4.0 ± 0.01 B per dimension), under both settings.
- `udf=created` for every D under `f16`.
- `table=REJECTED` for every D > 16 under `f16`.

**B2g. Readings**

| Observation | Meaning |
|---|---|
| `udf=created`, `dims@36 = D`, `serEmpty ≈ 4·D` for D ≫ 16 under `f16`, and the `f16` numbers equal the `off` numbers | Usage flat across the knob and following D. **Claim confirmed** (negative estimate holds). |
| `table=REJECTED` for D > 16 under `f16`, `created` under `off` | Positive control moved: the guardrail is live and binds for this user on its own path. |
| `udf=REJECTED` (GuardrailViolatedException) for D > 16 under `f16` | The guardrail does govern UDF types. **Claim refuted** (usage follows the constraint). |
| `serEmpty` or `udfRetLen` under `f16` capped at about 4·16 for large D (e.g. D clamped) | Usage follows the constraint. **Claim refuted**. |
| `table=created` for D > 16 under `f16` | The positive control did not move (the guardrail is not applied, e.g. the user is treated as superuser). **Not confirmed**: fix the user setup and rerun. |
| `serEmpty` ≪ 4·D for D = 1,000,000 (e.g. < 1 MB) | The allocation is not taking place as traced (or the instrument is not working). **Not confirmed**: re-check the instrument with a plain `new byte[4_000_000]`. |

**B2h. Controls.**

- Every statement in steps 3 and 4 runs as `userClientState`, an ordinary non-super, non-internal user. This rules out the superuser exemption (`Guardrail.java:95`) as the reason the UDF passes.
- D = 16, which is at the threshold, is the baseline: no rejection anywhere, so 64 B values.
- The `off` run shows the setting change is the only difference between runs.
- `serFullLen` and `udfRetLen` are exact byte counts, independent of how allocation is measured.
- The `ThreadMXBean` deltas are taken around a single call on the same thread, so other threads' allocations are excluded.

### B3. Cluster tier

**B3a. Environment and build.**

- One Linux node with JDK 11 (`JAVA_HOME` set) and Ant. Have at least 4 GB free RAM and at least 5 GB free local disk under `$RUN`.
- Build:
  ```bash
  RUN=/local-scratch/vd-cluster        # local disk, not shared storage
  mkdir -p $RUN/{data,commitlog,hints,saved_caches,cdc_raw,logs}
  rsync -a ~/cassandra-5.0.9/ $RUN/src/
  cd $RUN/src && ant -Dno-checkstyle=true jar
  ```
- Check that ports 7000, 7199 and 9042 are free with `ss -ltn | grep -E ':(7000|7199|9042) '`. If any is taken, change `storage_port` and `native_transport_port` in the yaml and set `JMX_PORT`, which `conf/cassandra-env.sh` reads.
- Edit `$RUN/src/conf/cassandra.yaml`. Replace the existing keys where present, otherwise append them:
  ```yaml
  authenticator: PasswordAuthenticator
  authorizer: CassandraAuthorizer
  user_defined_functions_enabled: true
  user_defined_functions_warn_timeout: 5000ms
  user_defined_functions_fail_timeout: 20000ms
  user_function_timeout_policy: ignore      # a GC stall must not kill the node (default 'die')
  vector_dimensions_warn_threshold: 8
  vector_dimensions_fail_threshold: 16
  data_file_directories: [ <RUN>/data ]
  commitlog_directory: <RUN>/commitlog
  hints_directory: <RUN>/hints
  saved_caches_directory: <RUN>/saved_caches
  cdc_raw_directory: <RUN>/cdc_raw
  ```
  Replace `<RUN>` with the real path.
- JVM: start with `MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M`. G1 is the default (`conf/jvm11-server.options:63`). With a 2 GB heap the G1 region is 1 MB, so any allocation ≥ 512 KB is humongous and goes straight to old-generation regions. The GC log goes to `$CASSANDRA_LOG_DIR/gc.log` (`conf/cassandra-env.sh:81-83`).

**B3b. Knobs.**

- **Guardrail setting:**
  - Run A: `vector_dimensions_fail_threshold: 16` (warn 8).
  - Run B: both keys `-1`, the default. Change the yaml and restart.
- **D in the UDF signature** ∈ {16, 1,000,000, 50,000,000, 100,000,000}:
  - 16 is the in-limit baseline.
  - 1,000,000 gives a 4 MB buffer.
  - 50,000,000 and 100,000,000 give 200 MB and 400 MB buffers. These stay below the 2 GB heap when run one at a time and stay clear of the `int` overflow at D > 536,870,911.

**B3c. Workload.**

- **Functions.** The ordinary role `alice` creates, for each D:
  ```sql
  CREATE FUNCTION vd.big_D() CALLED ON NULL INPUT RETURNS vector<float, D> LANGUAGE java AS 'return new ArrayList<Float>();';
  ```
  Each call allocates `4·D` bytes in `VectorCodec$FixedLength.serialize` and then fails fast with `NoSuchElementException`, so there is no D-long loop and no CPU timeout.
- **Calls.** `SELECT vd.big_D() FROM vd.base WHERE k = 0;` run 10 times sequentially per D, with 2 s between calls.
- **One full success, for completeness:**
  ```sql
  CREATE FUNCTION vd.mk1m() CALLED ON NULL INPUT RETURNS vector<float, 1000000> LANGUAGE java AS 'return Collections.nCopies(1000000, 0.0f);';
  CREATE FUNCTION vd.vsize(x vector<float, 1000000>) CALLED ON NULL INPUT RETURNS int LANGUAGE java AS 'return x == null ? 0 : x.size();';
  SELECT vd.vsize(vd.mk1m()) FROM vd.base WHERE k = 0;
  ```
  The last statement returns 1000000. This exercises both the return path and the argument path.
- **Positive control** (disk, where the guardrail binds):
  ```sql
  CREATE TABLE vd.pc (k int PRIMARY KEY, v vector<float, 100000>) WITH compression = {'enabled': false};
  -- then, if created, 20 x:
  INSERT INTO vd.pc (k, v) VALUES (<i>, vd.mk100k());
  ```
  Here `vd.mk100k()` returns `Collections.nCopies(100000, 1.0f)`. Each row is 400,000 B, so 20 rows ≈ 8 MB on disk after `nodetool flush`.
- **Arithmetic:** 10 calls × 400 MB = 4 GB allocated for D = 100,000,000. That is two heaps' worth, so GC must run, and each call is a separate humongous allocation. Peak live is one buffer, 400 MB.
- **Duration:** about 15 minutes per run.

**B3d. Observables and instruments.**

1. **JFR**, which is the primary instrument.
   - Start: `jcmd $PID JFR.start name=vd settings=profile filename=$RUN/vd-<run>.jfr`.
   - Stop: `jcmd $PID JFR.stop name=vd`.
   - The `profile` settings record `jdk.ObjectAllocationOutsideTLAB` with stack traces. Every buffer of at least 4 MB is allocated outside a TLAB.
   - Reading: count and size of events whose stack contains `VectorCodec$FixedLength.serialize`.
2. **jstat** sampled once a second: `jstat -gc $PID 1000 > $RUN/jstat-<run>.txt`. The `OU` (old used) column jumps by about 4·D per call, because humongous allocations land in old regions.
3. **GC log** at `$RUN/logs/gc.log`: count `G1 Humongous Allocation` pause causes.
4. **Client output:**
   - The `FunctionExecutionException` text (`… failed: java.util.NoSuchElementException`).
   - The guardrail rejection text for the positive control.
   - The `vsize` result.
5. **Disk for the positive control:** `du -sb $RUN/data/vd/pc-*` after `nodetool flush vd pc`.

Not observable directly: the live size of the buffer after the call, since it is garbage at once. JFR gives the allocation size and jstat gives the transient old-generation jump.

**B3e. Procedure.**

1. Start the node:
   ```bash
   cd $RUN/src
   MAX_HEAP_SIZE=2G HEAP_NEWSIZE=400M CASSANDRA_LOG_DIR=$RUN/logs bin/cassandra -p $RUN/cassandra.pid > $RUN/logs/stdout.log 2>&1
   PID=$(cat $RUN/cassandra.pid)
   ```
   Wait until `bin/nodetool status` shows `UN`, and another 15 s for the default superuser to be created.
2. As superuser, run `bin/cqlsh -u cassandra -p cassandra 127.0.0.1` and execute:
   ```sql
   CREATE KEYSPACE vd WITH replication = {'class':'SimpleStrategy','replication_factor':1};
   CREATE TABLE vd.base (k int PRIMARY KEY);
   INSERT INTO vd.base (k) VALUES (0);
   CREATE ROLE alice WITH PASSWORD = 'alice' AND LOGIN = true;
   GRANT ALL PERMISSIONS ON KEYSPACE vd TO alice;
   GRANT ALL PERMISSIONS ON ALL FUNCTIONS IN KEYSPACE vd TO alice;
   ```
   Then wait 3 s for the permission caches to expire.
3. Start the instruments:
   ```bash
   jcmd $PID JFR.start name=vd settings=profile filename=$RUN/vd-A.jfr
   jstat -gc $PID 1000 > $RUN/jstat-A.txt &
   echo $! > $RUN/jstat.pid
   ```
4. As `alice` (`bin/cqlsh -u alice -p alice 127.0.0.1`), run the positive control:
   - `CREATE TABLE vd.pc ...` (above) → record the outcome.
   - Also `CREATE TABLE vd.pc2 (k int PRIMARY KEY, v vector<float, 1000000>);` → record the outcome.
5. As `alice`, create `vd.mk100k`, `vd.mk1m`, `vd.vsize` and `vd.big_16`, `vd.big_1000000`, `vd.big_50000000`, `vd.big_100000000` (bodies above). Record each outcome.
6. Run `SELECT vd.vsize(vd.mk1m()) FROM vd.base WHERE k = 0;` and record the result.
7. For each D in 16, 1000000, 50000000, 100000000, run `SELECT vd.big_D() FROM vd.base WHERE k = 0;` 10 times, 2 s apart, as `alice`. For example, put the statements in `$RUN/calls.cql` and run `bin/cqlsh -u alice -p alice -f $RUN/calls.cql`. Note the wall-clock start of each D block.
8. If `vd.pc` exists, insert 20 rows with `vd.mk100k()`, then run `bin/nodetool flush vd pc` and `du -sb $RUN/data/vd/pc-*`.
9. Stop the instruments:
   ```bash
   jcmd $PID JFR.stop name=vd
   kill $(cat $RUN/jstat.pid)
   ```
10. Extract the allocations:
    ```bash
    $JAVA_HOME/bin/jfr print --json --events jdk.ObjectAllocationOutsideTLAB $RUN/vd-A.jfr > $RUN/alloc-A.json
    python3 -I - $RUN/alloc-A.json <<'EOF'
    import json,sys,collections
    ev=json.load(open(sys.argv[1]))['recording']['events']
    c=collections.Counter()
    for e in ev:
        fr=[f['method']['type']['name']+'.'+f['method']['name'] for f in e['values']['stackTrace']['frames']]
        if any('VectorCodec$FixedLength.serialize' in f for f in fr):
            c[e['values']['allocationSize']]+=1
    for k,v in sorted(c.items()): print(k,v)
    EOF
    ```
    Also run `grep -c "Humongous Allocation" $RUN/logs/gc.log`.
11. Run B. Stop the node with `kill $PID`, wait for the process to exit, and set both thresholds to `-1`. Wipe `$RUN/data`, `$RUN/commitlog`, `$RUN/hints` and `$RUN/saved_caches` so the schema starts clean, then repeat steps 1–10 with `-B` file names.
12. Clean up per B4.

**B3f. Predictions.**

- **Run A (fail = 16).**
  - Step 4: both `CREATE TABLE` statements are **rejected** with "Column v has a vector of 100000 [resp. 1000000] dimensions, this exceeds the failure threshold of 16."
  - Step 5: all functions are **created**. A warning is not expected either, since the guardrail is never consulted.
  - Step 6: returns `1000000`.
  - Step 7:
    - Each `big_D` call returns an error containing `NoSuchElementException`.
    - JFR shows `VectorCodec$FixedLength.serialize` allocations with `allocationSize` ≈ 4,000,016 (×10), 200,000,016 (×10) and 400,000,016 (×10), each ± 16 B for the array header. None ≥ 64 KiB appears for D = 16.
    - jstat `OU` steps up by about 200 MB and about 400 MB around each call in the 50M and 100M blocks.
    - The GC log has at least 20 humongous-allocation-triggered pauses or concurrent starts in those blocks.
  - Step 8: no table, so 0 bytes on disk.
- **Run B (−1).** Same as Run A for steps 5–7: the same allocation sizes and counts within ±16 B. In step 4 both tables are **created**, and in step 8 `du` of `vd.pc` is ≥ 8,000,000 B (20 × 400,000 B plus small overhead).
- **Relation the claim needs:** the allocation per call equals 4·D + 16 independently of the threshold. The positive control's disk goes from 0 to about 8 MB only when the threshold is lifted.

**B3g. Readings**

| Observation | Meaning |
|---|---|
| Run A: functions created, JFR shows 4·D+16-byte `serialize` allocations for D = 1M/50M/100M, matching Run B | Usage follows D and is flat across the knob. **Claim confirmed**. |
| Run A: `pc`/`pc2` rejected and `vd.pc` disk = 0; Run B: created and about 8 MB on disk | Positive control moved: the guardrail binds where it is applied. |
| Run A: `CREATE FUNCTION … vector<float, 1000000>` rejected by the guardrail, or the allocations are capped at about 64 B | Usage follows the constraint. **Claim refuted**. |
| Run A: `pc` created | Positive control did not move (wrong user, wrong yaml). **Not confirmed**: check `nodetool getguardrailsconfig` and that the session is `alice`. |
| No `serialize` allocation events at all, but the calls error | Instrument failure (JFR settings) or a different code path. **Not confirmed**: check that `jfr summary` lists `jdk.ObjectAllocationOutsideTLAB`, then rerun. |
| Node OOM / dies at D = 100M | Heap too small for a 400 MB transient. This supports usage following D, but rerun with D = 50M as the top value. |

**B3h. Controls.**

- Functions are created and called by the ordinary role `alice`, not by the `cassandra` superuser, so the superuser exemption is ruled out.
- D = 16, the in-limit baseline, gives no large allocation, so the instrument is not attributing other allocations to `VectorCodec`.
- Run B differs only in the two threshold keys.
- JFR stack filtering ties the allocation to the target codec.
- The same `mk100k` function feeds the positive control, so the "moves" side and the "flat" side share a workload.
- Sequential calls with gaps keep each humongous allocation separable in jstat.

**B4. Risks and cleanup.**

- **Disk.** Everything goes under `$WORK` / `$RUN` on local disk: the build is about 1.5 GB, data under 100 MB, logs and JFR under 500 MB. Nothing goes on shared storage, and nothing is written into `~/cassandra-5.0.9`.
- **Memory.** At most one 400 MB transient on a 2 GB heap. If the host has less than 4 GB free, use D = 50M as the top value.
- **Overflow.** Never use D > 536,870,911: the `int` overflow would make the test measure an `IllegalArgumentException` instead of an allocation.
- **Cleanup**, after each run:
  - `kill $(cat $RUN/cassandra.pid)`, then wait until `pgrep -f CassandraDaemon` lists no process from `$RUN`.
  - `pkill -f "jstat -gc"` (only the one started here).
  - `pgrep -f VectorDimsUdfBypassTest` (unit tier) must print nothing.
  - Then `rm -rf $RUN/data $RUN/commitlog $RUN/hints $RUN/saved_caches $RUN/cdc_raw`.
  - Keep `logs/`, `*.jfr`, `jstat-*.txt` and `unit-results.txt` as evidence, or remove the whole `$RUN` / `$WORK` once results are filed.
- **Ports.** Check that ports are free before starting, and that no listener remains on 7000/7199/9042 from this run afterwards.

## C. Sources read

- src/java/org/apache/cassandra/cql3/functions/types/VectorType.java
- src/java/org/apache/cassandra/cql3/functions/types/VectorCodec.java
- src/java/org/apache/cassandra/cql3/functions/types/DataType.java
- src/java/org/apache/cassandra/cql3/functions/types/DataTypeClassNameParser.java
- src/java/org/apache/cassandra/cql3/functions/types/TypeCodec.java
- src/java/org/apache/cassandra/utils/JavaDriverUtils.java
- src/java/org/apache/cassandra/cql3/functions/UDFDataType.java
- src/java/org/apache/cassandra/cql3/functions/UDFunction.java
- src/java/org/apache/cassandra/cql3/functions/JavaUDF.java
- src/java/org/apache/cassandra/cql3/functions/VectorFcts.java
- src/resources/org/apache/cassandra/cql3/functions/JavaSourceUDF.txt
- src/java/org/apache/cassandra/cql3/CQL3Type.java
- src/java/org/apache/cassandra/cql3/Vectors.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateFunctionStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateAggregateStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateTableStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/AlterTableStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/CreateTypeStatement.java
- src/java/org/apache/cassandra/cql3/statements/schema/AlterTypeStatement.java
- src/java/org/apache/cassandra/db/marshal/VectorType.java
- src/java/org/apache/cassandra/db/guardrails/Guardrails.java
- src/java/org/apache/cassandra/db/guardrails/GuardrailsMBean.java
- src/java/org/apache/cassandra/db/guardrails/GuardrailsConfig.java
- src/java/org/apache/cassandra/db/guardrails/Guardrail.java
- src/java/org/apache/cassandra/db/guardrails/Threshold.java
- src/java/org/apache/cassandra/db/guardrails/MaxThreshold.java
- src/java/org/apache/cassandra/config/Config.java
- src/java/org/apache/cassandra/config/GuardrailsOptions.java
- src/java/org/apache/cassandra/config/DatabaseDescriptor.java
- src/java/org/apache/cassandra/service/ClientState.java
- src/java/org/apache/cassandra/auth/AuthenticatedUser.java
- src/java/org/apache/cassandra/io/sstable/CQLSSTableWriter.java
- src/java/org/apache/cassandra/tools/nodetool/GuardrailsConfigCommand.java
- src/java/org/apache/cassandra/transport/messages/ResultMessage.java
- src/java/org/apache/cassandra/cql3/ResultSet.java
- src/antlr/Parser.g
- conf/cassandra.yaml
- conf/jvm11-server.options
- conf/jvm-server.options
- conf/cassandra-env.sh
- bin/cassandra
- build.xml
- CHANGES.txt
- test/conf/cassandra.yaml
- test/unit/org/apache/cassandra/db/guardrails/GuardrailVectorDimensionsTest.java
- test/unit/org/apache/cassandra/db/guardrails/GuardrailTester.java
- test/unit/org/apache/cassandra/cql3/validation/operations/CQLVectorTest.java
- test/unit/org/apache/cassandra/cql3/CQLTester.java
- https://issues.apache.org/jira/browse/CASSANDRA-18730 (cited from CHANGES.txt; not fetched)
- https://issues.apache.org/jira/browse/CASSANDRA-18613 (cited from CHANGES.txt; not fetched)
- https://docs.oracle.com/en/java/javase/11/docs/api/jdk.management/com/sun/management/ThreadMXBean.html (not fetched)
- https://docs.oracle.com/en/java/javase/11/tools/jfr.html (not fetched)

## D. Stage-4 feedback

none yet
