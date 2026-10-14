// SPDX-License-Identifier: GPL-3.0-or-later
// Optional, read-only Linux companion-board Wi-Fi status. No shell commands,
// scans, credentials, radio changes, or flight-controller access.
#ifndef P_HOST_INFO_WIFI_STATUS_HEADER
#define P_HOST_INFO_WIFI_STATUS_HEADER

#include <cctype>
#include <cmath>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>

struct WifiStatus {
  bool status_valid = false;
  bool link_up = false;
  bool signal_valid = false;
  double signal_dbm = 0;
  std::string detail = "unavailable";
};

inline bool validWifiInterface(const std::string& name)
{
  if(name.empty() || name.size() > 15 || name == "." || name == "..")
    return false;
  for(unsigned char c : name) {
    if(!std::isalnum(c) && c != '_' && c != '-' && c != '.')
      return false;
  }
  return true;
}

inline bool parseWifiSignal(std::istream& stream, const std::string& interface,
                            double& signal)
{
  std::string line;
  while(std::getline(stream, line)) {
    const auto colon = line.find(':');
    if(colon == std::string::npos)
      continue;
    std::istringstream identity(line.substr(0, colon));
    std::string name;
    identity >> name;
    if(name != interface)
      continue;
    std::istringstream fields(line.substr(colon + 1));
    std::string status;
    double quality = 0;
    double level = 0;
    // Linux appends a decimal point to updated values, e.g. "60. -50.".
    std::string level_text;
    if(!(fields >> status >> quality >> level_text))
      return false;
    std::istringstream number(level_text);
    if(!(number >> level) || !number.eof())
      return false;
    // Reject unknown sentinels (-256), non-finite and unsigned/relative values.
    // Do not fabricate dBm by rescaling a driver-specific quality percentage.
    if(!std::isfinite(level) || level < -127 || level >= 0)
      return false;
    signal = level;
    return true;
  }
  return false;
}

inline WifiStatus readWifiStatus(const std::string& interface,
                                 const std::string& proc_file = "/proc/net/wireless",
                                 const std::string& sys_net = "/sys/class/net")
{
  WifiStatus result;
  if(!validWifiInterface(interface)) {
    result.detail = "invalid_interface";
    return result;
  }
  // Ensure this is a wireless interface, not an Ethernet carrier mislabelled Wi-Fi.
  struct stat info;
  const std::string wireless_dir = sys_net + "/" + interface + "/wireless";
  const std::string phy_dir = sys_net + "/" + interface + "/phy80211";
  const bool legacy_wireless = stat(wireless_dir.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
  const bool cfg80211_wireless = stat(phy_dir.c_str(), &info) == 0 && S_ISDIR(info.st_mode);
  if(!legacy_wireless && !cfg80211_wireless) {
    result.detail = "wireless_interface_unavailable";
    return result;
  }
  int carrier = -1;
  std::ifstream carrier_file(sys_net + "/" + interface + "/carrier");
  if(!(carrier_file >> carrier) || (carrier != 0 && carrier != 1)) {
    result.detail = "carrier_unavailable";
    return result;
  }
  result.status_valid = true;
  result.link_up = carrier == 1;
  if(!result.link_up) {
    result.detail = "disconnected";
    return result;
  }
  std::ifstream wireless(proc_file);
  result.signal_valid = parseWifiSignal(wireless, interface, result.signal_dbm);
  result.detail = result.signal_valid ? "connected" : "signal_unavailable";
  return result;
}

#endif
