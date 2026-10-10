# pShare inbound-forwarding regression

Run against the rebuilt binary on PATH:

```sh
python3 tests/test_iterate_starvation.py
PSHARE_STRESS_SECONDS=60 python3 tests/test_iterate_starvation.py
```

`PSHARE_BINARY` can select another binary. The test owns two temporary
MOOS communities, dynamically allocated TCP/UDP ports, and process groups;
it launches only test-owned MOOS processes and never uses existing deployment
ports.

It first establishes successful idle UDP routing, then publishes local mail
at 200 Hz and sends a new, tiny UDP marker. The marker must reach the receiver
while that local load continues. On failure it also checks that stopping local
mail releases the queued marker, distinguishing starvation from bad routing.

The old pShare mode was `REGULAR_ITERATE_AND_COMMS_DRIVEN_MAIL` (mode 2).
`CMOOSApp::SleepAsRequired()` skips `Iterate()` when mail arrives before its
deadline. However, `CMOOSApp::DoRunWork()` resets `m_dfLastRunTime` even for
mail-only work. Sustained mail consequently keeps moving the deadline and
starves pShare's inbound UDP forwarding/status publication, while outgoing
mail and the MOOS communications thread can remain responsive.

pShare now batches mail with `REGULAR_ITERATE_AND_MAIL` at its existing
40 Hz frequency. No protocol, payload limit, source timestamp, or mission
watchdog is changed. This is a local workaround; the general MOOS-core
scheduling behavior has not been changed.

## Per-output behavior / broker regression

```sh
python3 tests/test_output_behaviors.py
python3 tests/test_rate_clock.py
python3 tests/test_warped_output.py
```

The test owns two MOOSDB communities, UDP capture sockets and process groups.
It starts only test-owned MOOS processes and does not modify existing
deployments.
It verifies default forwarding, explicit drop/coalesce/latest behaviors,
changed values at 20 Hz through coalesce, identical-repeat suppression,
opaque draw/clear/redraw forwarding, fixed latest deadlines under continuous
updates, final one-shot delivery without later mail, repeated dynamic route
refreshes, wildcard routes, independent destination policies, and real
uFldNodeBroker bridge-to-PSHARE_CMD passthrough (including `rate_clock`) with
a foreign-community ACK.

`test_rate_clock.py` compiles production Route code using a configured pShare
build. `PSHARE_BUILD_DIR` may select its target build directory (containing
`CMakeFiles/pShare.dir`). Assertions cover actual MOOS time warp, first-send
eligibility, fixed deadlines, backward-clock rebasing with retained pending
values, and unchanged duration/count limits. It does not start any apps.
`test_warped_output.py` owns a warp-5 MOOS community and UDP capture socket:
default/MOOS versus wall clocks for drop/latest/coalesce, quiet final-value
flush, repeated dynamic directives, clock changes with pending flush,
wildcard propagation, invalid-clock rejection, and policy diagnostics.

## Configuration

pShare:
```moos
output = src_name=STATUS,route=localhost:9200,frequency=1,behavior=coalesce
output = src_name=NAV_X,route=localhost:9200,frequency=2,behavior=latest,rate_clock=wall
```
uFldNodeBroker:
```moos
bridge = src=STATUS,alias=SHORE_STATUS,frequency=1,behavior=coalesce
bridge = src=NAV_X,frequency=2,behavior=latest,rate_clock=wall
```

Without `frequency`, routes use `forward` by default. A positive numeric
`frequency` is expressed in Hz; when `behavior` is omitted it retains the
existing `drop` semantics:
- `drop`: ignores every message arriving sooner than the rate allows.
- `coalesce`: ignores only identical repeats arriving too soon; changed
  payloads always pass immediately. No pending repeat is created.
- `latest`: replaces pending values and flushes at the prior-send deadline,
  independently of incoming mail. This deliberately discards intermediate
  values; no visual-object/clear/AppCast exceptions are inferred.
- `forward`: every update, without a rate.

Legacy `frequency` / shorthand `@Hz` keep drop semantics. Static, dynamic,
wildcard and multicast directives use the same behavior implementation. A
repeated identical directive preserves the rate clock and pending value.
Changing behavior, rate, or rate clock flushes a pending value before
replacing the old policy. This explicit policy-change flush may send earlier
than the old rate deadline.
Explicit duration/share-count expiry discards pending data with a diagnostic.
Failed pending local sends remain pending for retry; UDP has no remote
delivery guarantee. Original source timestamps remain untouched.

Repeat equality compares serialized opaque payload/type/source metadata,
ignoring only transport timestamp/message ID. This is opt-in: unchanged
values with new timestamps may represent freshness evidence. Timing is
selected independently per output route with `rate_clock=moos|wall`:
- `moos` (default): MOOS seconds, including MOOSTimeWarp. At warp 10, 2 Hz
  means up to 20 real sends/second for drop/latest. This preserves the clock
  used by existing `frequency` and shorthand `@Hz` routes.
- `wall`: monotonic real seconds, unaffected by MOOSTimeWarp or system-clock
  corrections.

App/Comms ticks, arrivals and scheduling still bound throughput; missed
periods are not replayed as catch-up bursts.

Both incoming rate checks and pending-latest flushes use that same selected
clock. A backward clock movement rebases the rate interval at the newly
observed time without discarding pending data. Duration still uses MOOS time,
share counts are unchanged, and source timestamps are never rewritten.
Coalesce still passes changed data immediately; it is not a strict bandwidth
cap. Forward has no rate and ignores clock choice. Invalid clock names are
rejected. Long-form `frequency` can also select `rate_clock`; shorthand
`@Hz` keeps the default MOOS clock.

No global shore limit, graphic-label parsing, tombstone recognition, or
producer-rate policy exists. `PSHARE_OUTPUT_BEHAVIORS`, routing output, and the
broker AppCast expose the per-route clock as well as rate and behavior.
No global route defaults are changed.
