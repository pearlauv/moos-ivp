#!/usr/bin/env python3
"""Isolated real-MOOS pShare test: local mail must not starve UDP forwarding.

No simulator or flight applications. Every TCP/UDP port is dynamically owned.
Run with the pShare binary under test on PATH or PSHARE_BINARY set explicitly.
"""

import os
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


def free_port(kind):
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class IterateStarvation(unittest.TestCase):
    def test_udp_delivery_during_sustained_local_mail(self):
        with tempfile.TemporaryDirectory(prefix="pshare-starvation-") as temp:
            root = Path(temp)
            sender_port = free_port(socket.SOCK_STREAM)
            receiver_port = free_port(socket.SOCK_STREAM)
            while receiver_port == sender_port:
                receiver_port = free_port(socket.SOCK_STREAM)
            udp_port = free_port(socket.SOCK_DGRAM)
            binary = os.environ.get("PSHARE_BINARY", "pShare")
            receiver = root / "receiver.moos"
            receiver.write_text(f"""ServerHost = 127.0.0.1
ServerPort = {receiver_port}
Community = receiver_probe
ProcessConfig = ANTLER
{{
  MSBetweenLaunches = 100
  Run = MOOSDB @ NewConsole = false
  Run = {binary} @ NewConsole = false ~ pShareReceiver
  Run = uTimerScript @ NewConsole = false ~ uBusyMail
}}
ProcessConfig = pShareReceiver
{{
  AppTick = 40
  CommsTick = 200
  input = route=127.0.0.1:{udp_port}
  output = src_name=LOCAL_LOAD,route=127.0.0.1:{udp_port}
}}
ProcessConfig = uBusyMail
{{
  AppTick = 200
  CommsTick = 200
  condition = ENABLE_LOCAL_LOAD=true
  paused = false
  script_atomic = false
  reset_max = unlimited
  reset_time = 0.005
  event = var=LOCAL_LOAD,val=1,time=0
}}
""")
            sender = root / "sender.moos"
            sender.write_text(f"""ServerHost = 127.0.0.1
ServerPort = {sender_port}
Community = sender_probe
ProcessConfig = ANTLER
{{
  MSBetweenLaunches = 100
  Run = MOOSDB @ NewConsole = false
  Run = {binary} @ NewConsole = false ~ pShareSender
}}
ProcessConfig = pShareSender
{{
  AppTick = 40
  CommsTick = 40
  output = src_name=AFTER_LOAD_PROBE,route=127.0.0.1:{udp_port}
}}
""")
            processes = []
            logs = []
            try:
                for mission in (receiver, sender):
                    log = (root / f"{mission.stem}.log").open("w")
                    logs.append(log)
                    processes.append(
                        subprocess.Popen(
                            ["pAntler", str(mission)],
                            cwd=root,
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            start_new_session=True,
                        )
                    )
                time.sleep(2)
                # Establish working routing before adding local traffic.
                subprocess.run(
                    ["uPokeDB", str(sender), "--quiet", "AFTER_LOAD_PROBE:=baseline"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                baseline = subprocess.run(
                    [
                        "uQueryDB",
                        str(receiver),
                        "--wait=3",
                        "--condition=AFTER_LOAD_PROBE=baseline",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(
                    baseline.returncode, 0, baseline.stdout + baseline.stderr
                )
                subprocess.run(
                    ["uPokeDB", str(receiver), "--quiet", "ENABLE_LOCAL_LOAD:=true"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                time.sleep(1 + float(os.environ.get("PSHARE_STRESS_SECONDS", "0")))
                # A new marker posted only AFTER sustained local load begins.
                subprocess.run(
                    ["uPokeDB", str(sender), "--quiet", "AFTER_LOAD_PROBE:=arrived"],
                    capture_output=True,
                    check=True,
                    timeout=10,
                )
                result = subprocess.run(
                    [
                        "uQueryDB",
                        str(receiver),
                        "--wait=3",
                        "--condition=AFTER_LOAD_PROBE=arrived",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                if result.returncode:
                    # A starvation failure must recover with identical routes
                    # as soon as local mail stops; this rules out bad routing.
                    subprocess.run(
                        [
                            "uPokeDB",
                            str(receiver),
                            "--quiet",
                            "ENABLE_LOCAL_LOAD:=false",
                        ],
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )
                    recovered = subprocess.run(
                        [
                            "uQueryDB",
                            str(receiver),
                            "--wait=3",
                            "--condition=AFTER_LOAD_PROBE=arrived",
                        ],
                        capture_output=True,
                        text=True,
                        check=False,
                        timeout=10,
                    )
                    self.assertEqual(
                        recovered.returncode, 0, recovered.stdout + recovered.stderr
                    )
                self.assertEqual(
                    result.returncode,
                    0,
                    "UDP forwarding starved under local mail:\n"
                    + result.stdout
                    + result.stderr,
                )
            finally:
                for process in processes:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait(timeout=3)
                for log in logs:
                    log.close()


if __name__ == "__main__":
    unittest.main()
