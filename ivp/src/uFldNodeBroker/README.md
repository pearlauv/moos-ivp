# Per-bridge sharing policy

`uFldNodeBroker` accepts optional per-bridge pShare policies:

```moos
bridge = src=STATUS,alias=SHORE_STATUS,frequency=1,behavior=coalesce
bridge = src=NAV_DIAGNOSTIC,frequency=1,behavior=latest,rate_clock=wall
bridge = src=EVENT,behavior=forward
```

The broker validates and passes `frequency`, `behavior`, and optional
`rate_clock=moos|wall` into
its dynamically generated `PSHARE_CMD` output directives. It does not time,
interpret, coalesce or queue payloads itself. Without options it preserves
normal unrestricted forwarding. An automatically added bridge does not
replace an explicit user policy; conflicting duplicate policies are rejected.

- **forward:** send every update. This is the default without a frequency, and
  no frequency is allowed when it is selected explicitly.
- **drop:** deliberately discard every update arriving inside the rate period.
  This remains the default when a frequency is given without a behavior.
- **coalesce:** discard only an identical repeat arriving inside the period.
  Changed payloads always pass immediately. Equality ignores transport
  timestamp/message ID but includes opaque value/type/source metadata.
- **latest:** explicitly replace pending values inside the period. pShare
  sends the last pending value at the previous-send deadline without needing
  another update. New arrivals do not extend the deadline. This can discard
  meaningful intermediate changes/clears and is only safe when the owner
  intentionally declares latest-state semantics.

Frequencies are positive numeric Hz values. `rate_clock=moos` is the default,
preserving the existing frequency behavior. It measures MOOS seconds including
time warp: 2 Hz at warp 10 allows up to 20 real sends/second for drop/latest,
subject to incoming traffic and app/communication scheduling. `rate_clock=wall`
uses monotonic real seconds instead. Changed coalesce payloads still pass
immediately regardless of clock. Pending flush and clock-rewind handling belong
to pShare; clock changes explicitly flush pending data before replacing policy.
Duration/count limits and original source timestamps are unaffected.
There is no inference from variable names, graphics labels, or target
telemetry. Policies apply separately to each pShare route. Original source
timestamps are retained. Broker-discovery traffic is unchanged.

The isolated real-MOOS/UDP regression is
`MOOS/MOOSEssentials/Essentials/pShare/tests/test_output_behaviors.py` in the
moos-ivp repository. It includes broker-generated latest-state routes using a
real foreign-community ACK.
