"""Owned MOOS/UDP integration: per-route wall versus warped rate clocks."""

import os
import select
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from itertools import pairwise
from pathlib import Path


class WarpedOutputs(unittest.TestCase):
    def test_moos_default_wall_and_dynamic_deadlines(self):
        with tempfile.TemporaryDirectory(prefix="pshare-warped-output-") as temp:
            root = Path(temp)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as capture:
                capture.bind(("127.0.0.1", 0))
                udp_port = capture.getsockname()[1]
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    db_port = reservation.getsockname()[1]
                routes, events = [], []
                for behavior, stem in (
                    ("drop", "DROP"),
                    ("latest", "LATEST"),
                    ("coalesce", "REPEAT"),
                ):
                    for clock in ("wall", "moos"):
                        key = f"CLOCK_{stem}_{clock.upper()}"
                        routes.append(
                            f"output = src_name={key},route=127.0.0.1:{udp_port},"
                            f"frequency=2,behavior={behavior},rate_clock={clock}"
                        )
                        events.extend(
                            f"event = var={key},val="
                            + ("identical" if stem == "REPEAT" else f"sample_{i}")
                            + f",time={i * 0.05:.2f}"
                            for i in range(400)
                        )
                routes.append(
                    f"output = src_name=CLOCK_DEFAULT,route=127.0.0.1:{udp_port},"
                    "frequency=2,behavior=latest"
                )
                events.extend(
                    f"event = var=CLOCK_DEFAULT,val=sample_{i},time={i * 0.05:.2f}"
                    for i in range(400)
                )
                for clock in ("wall", "moos"):
                    key = "CLOCK_ONCE_" + clock.upper()
                    routes.append(
                        f"output = src_name={key},route=127.0.0.1:{udp_port},"
                        f"frequency=2,behavior=latest,rate_clock={clock}"
                    )
                    events.extend(
                        [
                            f"event = var={key},val=initial,time=0",
                            f"event = var={key},val=final_once,time=0.10",
                        ]
                    )
                routes.append(
                    f"output = src_name=CLOCK_WILD_*,dest_name=WARP_,route=127.0.0.1:{udp_port},"
                    "frequency=2,behavior=latest,rate_clock=moos"
                )
                events.extend(
                    f"event = var=CLOCK_WILD_A,val=sample_{i},time={i * 0.05:.2f}"
                    for i in range(400)
                )
                switch = (
                    "cmd=output,src_name=CLOCK_SWITCH,"
                    f"route=127.0.0.1:{udp_port},frequency=1,behavior=latest,rate_clock="
                )
                events.extend(
                    [
                        f'event = var=PSHARE_CMD,val="{switch}wall",time=0',
                        "event = var=CLOCK_SWITCH,val=initial_switch,time=1",
                        "event = var=CLOCK_SWITCH,val=pending_switch,time=1.1",
                        f'event = var=PSHARE_CMD,val="{switch}moos",time=1.2',
                        "event = var=CLOCK_SWITCH,val=after_switch,time=1.3",
                    ]
                )
                command = (
                    "cmd=output,src_name=CLOCK_DYNAMIC,"
                    f"route=127.0.0.1:{udp_port},frequency=1,"
                    "behavior=latest,rate_clock=moos"
                )
                events.extend(
                    [
                        f'event = var=PSHARE_CMD,val="{command}",time=0',
                        "event = var=CLOCK_DYNAMIC,val=first,time=1",
                        "event = var=CLOCK_DYNAMIC,val=dynamic_final,time=1.1",
                        f'event = var=PSHARE_CMD,val="{command}",time=1.2',
                        f'event = var=PSHARE_CMD,val="cmd=output,src_name=CLOCK_BAD,route=127.0.0.1:{udp_port},frequency=2,behavior=latest,rate_clock=invalid",time=0',
                        "event = var=CLOCK_BAD,val=must_not_send,time=2",
                    ]
                )
                routes.append(
                    "output = src_name=PSHARE_OUTPUT_BEHAVIORS,"
                    f"route=127.0.0.1:{udp_port}"
                )
                mission = root / "clock.moos"
                binary = os.environ.get("PSHARE_BINARY", "pShare")
                mission.write_text(f"""ServerHost = 127.0.0.1
ServerPort = {db_port}
Community = clock_test
MOOSTimeWarp = 5
ProcessConfig = ANTLER
{{
  MSBetweenLaunches = 100
  Run = MOOSDB @ NewConsole = false
  Run = {binary} @ NewConsole = false
  Run = uTimerScript @ NewConsole = false ~ uEmit
}}
ProcessConfig = pShare
{{
  AppTick = 40
  CommsTick = 100
  {chr(10).join(routes)}
}}
ProcessConfig = uEmit
{{
  AppTick = 100
  CommsTick = 100
  condition = START_CLOCK_TEST=true
  paused = false
  script_atomic = false
  reset_max = 0
  {chr(10).join(events)}
}}
""")
                process = None
                poker = None
                packets = []
                try:
                    with (root / "apps.log").open("w") as log:
                        process = subprocess.Popen(
                            ["pAntler", str(mission)],
                            cwd=root,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                        # Wait for policy publication as direct evidence that
                        # pShare has completed startup.
                        deadline = time.monotonic() + 8
                        while time.monotonic() < deadline:
                            if select.select([capture], [], [], 0.1)[0]:
                                data, _ = capture.recvfrom(65535)
                                if b"PSHARE_OUTPUT_BEHAVIORS" in data:
                                    break
                        else:
                            self.fail(
                                "pShare did not start\n"
                                + (root / "apps.log").read_text()
                            )
                        # Let the emitter finish its startup connection too.
                        time.sleep(0.5)
                        poker = subprocess.Popen(
                            [
                                "uPokeDB",
                                str(mission),
                                "--quiet",
                                "START_CLOCK_TEST:=true",
                            ],
                            stdout=log,
                            stderr=subprocess.STDOUT,
                        )
                        deadline = time.monotonic() + 5.5
                        while time.monotonic() < deadline:
                            if select.select([capture], [], [], 0.05)[0]:
                                data, _ = capture.recvfrom(65535)
                                packets.append((time.monotonic(), data))
                        self.assertEqual(poker.wait(timeout=2), 0)

                    full_log = (root / "apps.log").read_text()
                    diagnostic = full_log[-12000:]

                    # Status packets also mention route keys. Exclude those so
                    # only actual forwarded data packets count as emissions.
                    data_packets = [
                        p for p in packets if b"PSHARE_OUTPUT_BEHAVIORS" not in p[1]
                    ]

                    def samples(key):
                        return [(t, b) for t, b in data_packets if key.encode() in b]

                    counts = {}
                    for stem in ("DROP", "LATEST", "REPEAT"):
                        wall = samples(f"CLOCK_{stem}_WALL")
                        moos = samples(f"CLOCK_{stem}_MOOS")
                        counts[stem] = (len(wall), len(moos))
                        self.assertGreaterEqual(len(wall), 7, diagnostic)
                        self.assertLessEqual(len(wall), 12, diagnostic)
                        self.assertGreaterEqual(len(moos), 28, diagnostic)
                        self.assertLessEqual(len(moos), 44, diagnostic)
                        self.assertGreater(len(moos), 3 * len(wall), diagnostic)
                        # Initial datagrams may be buffered while uPokeDB exits.
                        for messages, interval in ((wall, 0.43), (moos, 0.075)):
                            self.assertTrue(
                                all(
                                    b[0] - a[0] >= interval
                                    for a, b in pairwise(messages[2:])
                                ),
                                f"{stem}: {counts}\n{diagnostic}",
                            )
                        if stem == "LATEST":
                            self.assertIn(b"sample_399", wall[-1][1])
                            self.assertIn(b"sample_399", moos[-1][1])
                    default = samples("CLOCK_DEFAULT")
                    self.assertGreaterEqual(len(default), 28)
                    self.assertLessEqual(len(default), 44)
                    self.assertIn(b"sample_399", default[-1][1])
                    for clock in ("WALL", "MOOS"):
                        once = samples("CLOCK_ONCE_" + clock)
                        self.assertEqual(len(once), 2, diagnostic)
                        self.assertIn(b"final_once", once[-1][1])
                    dynamic = samples("CLOCK_DYNAMIC")
                    self.assertEqual(len(dynamic), 2, diagnostic)
                    self.assertIn(b"dynamic_final", dynamic[-1][1])
                    switch = samples("CLOCK_SWITCH")
                    self.assertEqual(len(switch), 3, diagnostic)
                    self.assertIn(b"pending_switch", switch[1][1])
                    self.assertIn(b"after_switch", switch[2][1])
                    wild = samples("WARP_CLOCK_WILD_A")
                    self.assertGreaterEqual(len(wild), 28, diagnostic)
                    self.assertLessEqual(len(wild), 44, diagnostic)
                    self.assertIn(b"sample_399", wild[-1][1])
                    self.assertFalse(samples("CLOCK_BAD"))
                    self.assertIn("rate_clock must be wall or moos", full_log)
                    policies = b"\n".join(
                        b for _, b in packets if b"PSHARE_OUTPUT_BEHAVIORS" in b
                    )
                    self.assertRegex(policies, rb"CLOCK_DEFAULT[^;]*rate_clock=moos")
                    self.assertRegex(
                        policies, rb"CLOCK_LATEST_MOOS[^;]*rate_clock=moos"
                    )
                    print(f"warp=5 wall/moos packet counts: {counts}")
                finally:
                    if poker is not None and poker.poll() is None:
                        poker.terminate()
                        try:
                            poker.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            poker.kill()
                            poker.wait(timeout=2)
                    if process is not None and process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main()
