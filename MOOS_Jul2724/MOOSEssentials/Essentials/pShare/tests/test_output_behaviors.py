#!/usr/bin/env python3
"""Owned real-MOOS apps/UDP capture: directive behaviors and broker forwarding."""

import os
import re
import select
import signal
import socket
import subprocess
import tempfile
import time
import unittest
from itertools import pairwise
from pathlib import Path


def tcp_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OutputBehaviors(unittest.TestCase):
    def test_directives_and_broker(self):
        with tempfile.TemporaryDirectory(prefix="pshare-behaviors-") as temp:
            root = Path(temp)
            shore = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            shore.bind(("127.0.0.1", 0))
            peer.bind(("127.0.0.1", 0))
            sp, pp = shore.getsockname()[1], peer.getsockname()[1]
            binary = os.environ.get("PSHARE_BINARY", "pShare")
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as incoming:
                incoming.bind(("127.0.0.1", 0))
                incoming_port = incoming.getsockname()[1]
            source_port = tcp_port()
            shore_db_port = tcp_port()
            while source_port == shore_db_port:
                shore_db_port = tcp_port()
            routes = [
                f"output = src_name=TEST_{key},route=127.0.0.1:{sp}{options}"
                for key, options in (
                    ("FORWARD", ""),
                    ("DROP", ",frequency=1"),
                    ("COALESCE", ",frequency=1,behavior=coalesce"),
                    ("REPEAT", ",frequency=1,behavior=coalesce"),
                    ("LATEST", ",frequency=1,behavior=latest"),
                    ("TWO_HZ", ",frequency=2,behavior=latest"),
                    ("ONCE", ",frequency=1,behavior=latest"),
                    ("GRAPHIC", ",frequency=1,behavior=coalesce"),
                )
            ]
            routes += [
                f"output = src_name=TEST_LATEST,dest_name=PEER_LATEST,route=127.0.0.1:{pp},behavior=forward",
                f"output = src_name=PSHARE_CMD,route=127.0.0.1:{pp}",
                f"output = src_name=WILD_*,dest_name=SEEN_,route=127.0.0.1:{sp},frequency=1,behavior=coalesce",
            ]
            events = []
            for key in ("FORWARD", "DROP", "COALESCE", "LATEST", "TWO_HZ"):
                events += [
                    f"event = var=TEST_{key},val=sample_{i},time={i * 0.05:.2f}"
                    for i in range(60)
                ]
            events += [
                "event = var=TEST_REPEAT,val=identical,time=0",
                "event = var=TEST_REPEAT,val=identical,time=0.05",
                "event = var=TEST_REPEAT,val=identical,time=0.10",
                "event = var=TEST_REPEAT,val=identical,time=1.30",
                "event = var=TEST_ONCE,val=initial,time=0",
                "event = var=TEST_ONCE,val=final_once,time=0.10",
                "event = var=TEST_GRAPHIC,val=label=a,active=true,time=0",
                "event = var=TEST_GRAPHIC,val=label=a,active=false,time=0.10",
                "event = var=TEST_GRAPHIC,val=label=a,active=true,time=0.20",
                "event = var=WILD_A,val=wild_initial,time=0",
                "event = var=WILD_A,val=wild_initial,time=0.10",
                "event = var=WILD_A,val=wild_changed,time=0.20",
                f"event = var=PSHARE_CMD,val=cmd=output,src_name=TEST_DYNAMIC,route=127.0.0.1:{sp},frequency=1,behavior=latest,time=0",
                "event = var=TEST_DYNAMIC,val=dynamic_first,time=0.40",
                "event = var=TEST_DYNAMIC,val=dynamic_final,time=0.50",
                # Repeating a route directive must not lose pending state or
                # reset its deadline. Force one refresh inside the closed gate.
                f"event = var=PSHARE_CMD,val=cmd=output,src_name=TEST_DYNAMIC,route=127.0.0.1:{sp},frequency=1,behavior=latest,time=0.60",
            ]
            events += [
                f"event = var=BROKER_SOURCE,val=sample_{i},time={0.5 + i * 0.05:.2f}"
                for i in range(60)
            ]
            events += [
                f"event = var=BROKER_TWO_SOURCE,val=sample_{i},time={0.5 + i * 0.05:.2f}"
                for i in range(60)
            ]
            events = [
                re.sub(r",val=(.*),time=", lambda m: ',val="' + m[1] + '",time=', event)
                for event in events
            ]
            mission = root / "test.moos"
            mission.write_text(f"""ServerHost = 127.0.0.1
ServerPort = {source_port}
Community = behaviors_test
ProcessConfig = ANTLER
{{
  MSBetweenLaunches = 100
  Run = MOOSDB @ NewConsole = false
  Run = {binary} @ NewConsole = false
  Run = uFldNodeBroker @ NewConsole = false
  Run = uTimerScript @ NewConsole = false ~ uEmit
}}
ProcessConfig = pShare
{{
  AppTick = 40
  CommsTick = 100
  input = route=127.0.0.1:{incoming_port}
  {chr(10).join(routes)}
}}
ProcessConfig = uFldNodeBroker
{{
  AppTick = 20
  CommsTick = 20
  auto_bridge_appcast = false
  auto_bridge_realmcast = false
  auto_bridge_pshare_vars = false
  try_shore_host = pshare_route=127.0.0.1:{sp}
  bridge = src=BROKER_SOURCE,alias=BROKER_LATEST,frequency=1,behavior=latest
  bridge = src=BROKER_TWO_SOURCE,alias=BROKER_2HZ,frequency=2,behavior=latest,rate_clock=wall
}}
ProcessConfig = uEmit
{{
  AppTick = 100
  CommsTick = 100
  condition = START_TEST=true
  paused = false
  script_atomic = false
  reset_max = 0
  {chr(10).join(events)}
}}
""")
            # A real foreign community is required: the broker deliberately
            # rejects ACKs published by its own community.
            shore_mission = root / "shore.moos"
            shore_mission.write_text(f"""ServerHost = 127.0.0.1
ServerPort = {shore_db_port}
Community = shore
ProcessConfig = ANTLER
{{
  MSBetweenLaunches = 100
  Run = MOOSDB @ NewConsole = false
  Run = {binary} @ NewConsole = false
}}
ProcessConfig = pShare
{{
  AppTick = 40
  CommsTick = 100
  output = src_name=NODE_BROKER_ACK,route=127.0.0.1:{incoming_port}
}}
""")
            packets = {shore: [], peer: []}
            process = None
            foreign = None
            try:
                with (root / "apps.log").open("w") as log:
                    process = subprocess.Popen(
                        ["pAntler", str(mission)],
                        cwd=root,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    foreign = subprocess.Popen(
                        ["pAntler", str(shore_mission)],
                        cwd=root,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    time.sleep(2)
                    subprocess.run(
                        [
                            "uPokeDB",
                            str(shore_mission),
                            "--quiet",
                            f"NODE_BROKER_ACK:=community=shore,key=0,hostip=127.0.0.1,port_db={shore_db_port}",
                        ],
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )
                    time.sleep(0.2)
                    subprocess.run(
                        ["uPokeDB", str(mission), "--quiet", "START_TEST:=true"],
                        capture_output=True,
                        check=True,
                        timeout=10,
                    )
                    until = time.monotonic() + 5
                    while time.monotonic() < until:
                        for sock in select.select([shore, peer], [], [], 0.1)[0]:
                            data, _ = sock.recvfrom(65535)
                            packets[sock].append((time.monotonic(), data))

                def matching(key, sock=shore):
                    return [(t, b) for t, b in packets[sock] if key.encode() in b]

                for key in ("TEST_FORWARD", "TEST_COALESCE"):
                    values = [
                        int(m[1])
                        for _, b in matching(key)
                        if (m := re.search(rb"sample_(\d+)", b))
                    ]
                    self.assertEqual(values, list(range(60)), key)
                self.assertEqual(len(matching("PEER_LATEST", peer)), 60)
                self.assertEqual(len(matching("TEST_REPEAT")), 2)
                self.assertEqual(len(matching("TEST_GRAPHIC")), 3)
                self.assertTrue(
                    any(b"active=false" in b for _, b in matching("TEST_GRAPHIC"))
                )
                self.assertEqual(len(matching("SEEN_WILD_A")), 2)
                for key in ("TEST_DROP", "TEST_LATEST", "BROKER_LATEST"):
                    samples = matching(key)
                    self.assertGreaterEqual(
                        len(samples),
                        3,
                        key + "\n" + (root / "apps.log").read_text()[-9000:],
                    )
                    self.assertLessEqual(len(samples), 5, key)
                    # Initial packets can already be buffered before capture.
                    self.assertTrue(
                        all(b[0] - a[0] >= 0.9 for a, b in pairwise(samples[1:])), key
                    )
                    if key != "TEST_DROP":
                        self.assertIn(b"sample_59", samples[-1][1], key)
                for key in ("TEST_TWO_HZ", "BROKER_2HZ"):
                    samples = matching(key)
                    self.assertGreaterEqual(len(samples), 6, key)
                    self.assertLessEqual(len(samples), 8, key)
                    self.assertIn(b"sample_59", samples[-1][1], key)
                    self.assertTrue(
                        all(b[0] - a[0] >= 0.45 for a, b in pairwise(samples[2:])), key
                    )
                self.assertEqual(len(matching("TEST_ONCE")), 2)
                self.assertIn(b"final_once", matching("TEST_ONCE")[-1][1])
                self.assertEqual(len(matching("TEST_DYNAMIC")), 2)
                self.assertIn(b"dynamic_final", matching("TEST_DYNAMIC")[-1][1])
                commands = matching("PSHARE_CMD", peer)
                self.assertTrue(
                    any(
                        b"src_name=BROKER_TWO_SOURCE" in b
                        and b"rate_clock=wall" in b
                        for _, b in commands
                    )
                )
                self.assertTrue(
                    any(
                        b"src_name=BROKER_SOURCE" in b
                        and b"dest_name=BROKER_LATEST" in b
                        and b"frequency=1" in b
                        and b"behavior=latest" in b
                        for _, b in commands
                    )
                )
            finally:
                for owned in (process, foreign):
                    if owned is not None and owned.poll() is None:
                        os.killpg(owned.pid, signal.SIGTERM)
                        try:
                            owned.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(owned.pid, signal.SIGKILL)
                            owned.wait(timeout=3)
                shore.close()
                peer.close()


if __name__ == "__main__":
    unittest.main()
