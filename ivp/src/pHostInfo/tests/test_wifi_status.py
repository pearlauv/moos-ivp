#!/usr/bin/env python3
"""Compile/test the existing pHostInfo's pure file reader with synthetic proc/sysfs."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import socket
import time
import os

SOURCE = Path(__file__).resolve().parents[1]


class WifiStatusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="hostinfo-wifi-test-")
        cls.addClassCleanup(temporary.cleanup)
        root = Path(temporary.name)
        harness = root / "reader.cpp"
        harness.write_text('''#include "WifiStatus.h"
#include <iostream>
int main(int argc, char** argv) {
  if(argc != 4) return 2;
  const auto result = readWifiStatus(argv[1], argv[2], argv[3]);
  std::cout << result.status_valid << " " << result.link_up << " "
            << result.signal_valid << " " << result.signal_dbm << " "
            << result.detail << "\\n";
}
''')
        cls.binary = root / "reader"
        subprocess.run(["c++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE),
                        str(harness), "-o", str(cls.binary)], check=True, capture_output=True)

    def sample(self, text="wlan1: 0000 60. -50. -256 0 0\n", carrier: str | None = "1", interface="wlan1",
               wireless=True, phy80211=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            device = root / "net/wlan1"
            device.mkdir(parents=True)
            if wireless:
                (device / "wireless").mkdir()
            if phy80211:
                (device / "phy80211").mkdir()
            if carrier is not None:
                (device / "carrier").write_text(carrier)
            proc = root / "wireless"
            proc.write_text(text)
            result = subprocess.run([str(self.binary), interface, str(proc), str(root / "net")],
                                    check=True, capture_output=True, text=True)
            return result.stdout.split()

    def test_reads_selected_board_interface_dbm(self):
        self.assertEqual(self.sample("wlan0: 0000 70. -30. -256\nwlan1: 0000 60. -50. -256\n"),
                         ["1", "1", "1", "-50", "connected"])

    def test_disconnect_invalidates_held_signal(self):
        self.assertEqual(self.sample(carrier="0"), ["1", "0", "0", "0", "disconnected"])

    def test_missing_or_malformed_carrier_is_unknown_not_connected(self):
        for value in (None, "invalid", "2"):
            with self.subTest(value=value):
                self.assertEqual(self.sample(carrier=value), ["0", "0", "0", "0", "carrier_unavailable"])

    def test_rejects_sentinel_relative_nan_and_malformed_levels(self):
        for value in ("-256", "50", "0", "nan", "-50oops", "-200"):
            with self.subTest(value=value):
                self.assertEqual(self.sample(f"wlan1: 0000 60. {value} -256\n"),
                                 ["1", "1", "0", "0", "signal_unavailable"])

    def test_missing_interface_in_proc_has_no_signal(self):
        self.assertEqual(self.sample("wlan0: 0000 60. -40. -256\n"),
                         ["1", "1", "0", "0", "signal_unavailable"])

    def test_rejects_interface_path_traversal(self):
        for interface in ("../wlan1", "..", "wlan1;id", "w" * 16):
            self.assertEqual(self.sample(interface=interface), ["0", "0", "0", "0", "invalid_interface"])

    def test_accepts_cfg80211_identity_without_legacy_wireless_sysfs(self):
        self.assertEqual(self.sample(wireless=False, phy80211=True),
                         ["1", "1", "1", "-50", "connected"])

    def test_does_not_label_ethernet_as_wifi(self):
        self.assertEqual(self.sample(wireless=False), ["0", "0", "0", "0", "wireless_interface_unavailable"])

    def test_live_moos_publishes_invalid_status_and_advancing_time_with_forced_ip(self):
        binaries = SOURCE.parents[2] / "bin"
        for name in ("MOOSDB", "pHostInfo", "uQueryDB"):
            self.assertTrue((binaries / name).is_file(), f"Build {name} before this test")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="hostinfo-moos-test-") as directory:
            root = Path(directory)
            mission = root / "test.moos"
            mission.write_text(f'''ServerHost = 127.0.0.1
ServerPort = {port}
Community = wifi_fixture
ProcessConfig = pHostInfo
{{
  AppTick = 10
  CommsTick = 10
  default_hostip_force = 127.0.0.1
  wifi_interface = pi_no_wifi_test
  wifi_prefix = UAV_WIFI
  wifi_poll_interval = 1
  wifi_syslog = false
}}
''')
            processes = []
            with (root / "processes.log").open("w") as output:
                try:
                    for name in ("MOOSDB", "pHostInfo"):
                        command = [str(binaries / name), str(mission)]
                        if name == "pHostInfo":
                            command.append("--alias=pHostInfo")
                        processes.append(subprocess.Popen(command, env={**os.environ, "HOME": str(root)},
                            cwd=root, stdout=output, stderr=subprocess.STDOUT))
                    for conditions in (("UAV_WIFI_STATUS_VALID=0", "UAV_WIFI_SIGNAL_VALID=0",
                                        "PHI_HOST_IP=127.0.0.1", "UAV_WIFI_SAMPLE_TIME>0"),
                                       None):
                        conditions = conditions or (f"UAV_WIFI_SAMPLE_TIME>{time.time():.6f}",)
                        query = subprocess.run([str(binaries / "uQueryDB"), str(mission),
                            *("--condition=" + item for item in conditions), "--wait=8"],
                            capture_output=True, text=True, timeout=12)
                        self.assertEqual(query.returncode, 0,
                            query.stdout + query.stderr + (root / "processes.log").read_text())
                finally:
                    for process in reversed(processes):
                        if process.poll() is None:
                            process.terminate()
                            try:
                                process.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
