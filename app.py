from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
from datetime import datetime
from ipaddress import ip_network
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
BACKUP_DIR = STATE_DIR / "backups"
STATE_PATH = STATE_DIR / "client-actions.json"

DNSMASQ_CONFIG_PATH = Path(os.getenv("PRG_DNSMASQ_CONFIG_PATH", "/etc/dnsmasq.conf"))
HOSTAPD_CONF_PATH = Path(os.getenv("PRG_HOSTAPD_CONF_PATH", "/etc/hostapd/hostapd.conf"))
HOSTAPD_DEFAULT_PATH = Path(os.getenv("PRG_HOSTAPD_DEFAULT_PATH", "/etc/default/hostapd"))
RC_LOCAL_PATH = Path(os.getenv("PRG_RC_LOCAL_PATH", "/etc/rc.local"))
IPTABLES_RULES_PATH = Path(os.getenv("PRG_IPTABLES_RULES_PATH", "/etc/iptables/rules.v4"))
NFT_MANAGED_PATH = Path(os.getenv("PRG_NFT_MANAGED_PATH", "/etc/nftables.d/piroutergui-blocklist.nft"))

DNSMASQ_RELOAD_CMD = os.getenv("PRG_DNSMASQ_RELOAD_CMD", "systemctl reload dnsmasq")
HOSTAPD_RESTART_CMD = os.getenv("PRG_HOSTAPD_RESTART_CMD", "systemctl restart hostapd")
NFT_APPLY_CMD = os.getenv("PRG_NFT_APPLY_CMD", f"nft -f {NFT_MANAGED_PATH}")

DNSMASQ_BEGIN = "# BEGIN PIRouterGUI managed dnsmasq"
DNSMASQ_END = "# END PIRouterGUI managed dnsmasq"
RCLOCAL_BEGIN = "# BEGIN PIRouterGUI managed rc.local"
RCLOCAL_END = "# END PIRouterGUI managed rc.local"

AUTH_ENABLED = os.getenv("PRG_AUTH_ENABLED", "true").lower() == "true"
AUTH_USERNAME = os.getenv("PRG_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("PRG_AUTH_PASSWORD", "change-me")
AUTH_SECRET = os.getenv("PRG_AUTH_SECRET", "piroutergui-secret")
AUTH_COOKIE = "prg_auth"

app = FastAPI(title="PiRouterGUI")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def default_state() -> dict[str, Any]:
    return {
        "blockedMacs": [],
        "staticLeases": {},
        "deviceNames": {},
        "network": {"wlanIface": "wlan0", "uplinkIface": "eth0", "wlanCidr": "192.168.50.1/24"},
        "wifi": {"interface": "wlan0", "ssid": "mimicnetpi", "channel": "6", "hwMode": "g", "wpaPassphrase": "yourpassword"},
        "dhcp": {
            "interface": "wlan0",
            "rangeStart": "192.168.50.10",
            "rangeEnd": "192.168.50.100",
            "netmask": "255.255.255.0",
            "leaseTime": "24h",
        },
        "firewall": {"enabled": True, "wifiIface": "wlan0", "uplinkIface": "eth0"},
        "meta": {"importedDnsmasqHosts": False},
    }


def auth_cookie_value() -> str:
    payload = f"{AUTH_USERNAME}:{AUTH_PASSWORD}:{AUTH_SECRET}".encode()
    return hashlib.sha256(payload).hexdigest()


def is_authenticated(request: Request) -> bool:
    if not AUTH_ENABLED:
        return True
    token = request.cookies.get(AUTH_COOKIE, "")
    return hmac.compare_digest(token, auth_cookie_value())


def exec_text(command: str) -> str:
    try:
        return subprocess.check_output(command, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def run_cmd(command: str) -> dict[str, Any]:
    try:
        out = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT).strip()
        return {"ok": True, "output": out}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": (e.output or str(e)).strip()}


def ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_if_exists(path: Path, prefix: str) -> str | None:
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    out = BACKUP_DIR / f"{prefix}-{ts()}.bak"
    shutil.copy2(path, out)
    return str(out)


def restore_from_backup(path: Path, backup_path: str | None) -> None:
    if backup_path:
        shutil.copy2(backup_path, path)


def load_state() -> dict[str, Any]:
    state = default_state()
    try:
        raw = json.loads(STATE_PATH.read_text())
        if isinstance(raw, dict):
            state["blockedMacs"] = list(raw.get("blockedMacs", state["blockedMacs"]))
            state["staticLeases"] = dict(raw.get("staticLeases", state["staticLeases"]))
            state["deviceNames"] = dict(raw.get("deviceNames", state["deviceNames"]))
            state["network"].update(raw.get("network", {}))
            state["wifi"].update(raw.get("wifi", {}))
            state["dhcp"].update(raw.get("dhcp", {}))
            state["firewall"].update(raw.get("firewall", {}))
            state["meta"].update(raw.get("meta", {}))
    except Exception:
        pass
    return state


def save_state(state: dict[str, Any]) -> str | None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    b = backup_if_exists(STATE_PATH, "state")
    STATE_PATH.write_text(json.dumps(state, indent=2))
    return b


def set_managed_block_text(text: str, begin: str, end: str, block: str) -> str:
    managed = f"{begin}\n{block.rstrip()}\n{end}\n"
    if begin in text and end in text:
        start = text.find(begin)
        finish = text.find(end, start)
        if finish >= 0:
            finish += len(end)
            return f"{text[:start]}{managed}{text[finish:]}"
    if text and not text.endswith("\n"):
        text += "\n"
    return f"{text}\n{managed}"


def parse_dnsmasq_conf() -> dict[str, Any]:
    result = {"interface": "wlan0", "rangeStart": "192.168.50.10", "rangeEnd": "192.168.50.100", "netmask": "255.255.255.0", "leaseTime": "24h", "hosts": []}
    try:
        lines = DNSMASQ_CONFIG_PATH.read_text().splitlines()
    except Exception:
        return result

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("interface="):
            result["interface"] = line.split("=", 1)[1].strip()
        elif line.startswith("dhcp-range="):
            parts = [x.strip() for x in line.split("=", 1)[1].split(",")]
            if len(parts) >= 4:
                result["rangeStart"], result["rangeEnd"], result["netmask"], result["leaseTime"] = parts[0], parts[1], parts[2], parts[3]
        elif line.startswith("dhcp-host="):
            parts = [x.strip() for x in line.split("=", 1)[1].split(",") if x.strip()]
            if len(parts) >= 2:
                result["hosts"].append({"mac": parts[0].lower(), "ip": parts[1], "hostname": parts[2] if len(parts) >= 3 else ""})
    return result


def parse_hostapd_conf() -> dict[str, str]:
    result = {"interface": "wlan0", "ssid": "mimicnetpi", "channel": "6", "hw_mode": "g", "wpa_passphrase": "yourpassword"}
    try:
        lines = HOSTAPD_CONF_PATH.read_text().splitlines()
    except Exception:
        return result

    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key in result:
            result[key] = value
    return result


def read_wlan_cidr(iface: str) -> str:
    out = exec_text(f"ip -o -4 addr show dev {iface}")
    for line in out.splitlines():
        parts = line.split()
        if "inet" in parts:
            idx = parts.index("inet")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    return ""


def parse_interfaces() -> list[dict[str, str]]:
    links = exec_text("ip -o link show")
    addrs = exec_text("ip -o -4 addr show")
    addr_map: dict[str, str] = {}
    for line in addrs.splitlines():
        parts = line.split()
        if len(parts) >= 4:
            iface = parts[1]
            cidr = parts[3]
            addr_map[iface] = cidr

    items: list[dict[str, str]] = []
    for line in links.splitlines():
        parts = line.split(":")
        if len(parts) < 2:
            continue
        iface = parts[1].strip()
        if iface == "lo":
            continue
        items.append({"name": iface, "cidr": addr_map.get(iface, "-")})
    return items


def get_local_networks() -> list[str]:
    out = exec_text("ip -4 route show")
    networks: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        first = line.split()[0]
        if first == "default":
            continue
        if "/" not in first:
            first = f"{first}/32"
        try:
            net = str(ip_network(first, strict=False))
            if net not in networks:
                networks.append(net)
        except Exception:
            continue
    return networks


def infer_device_type(name: str) -> str:
    x = (name or "").lower()
    if any(k in x for k in ["iphone", "pixel", "android"]):
        return "Phone"
    if any(k in x for k in ["ipad", "tablet"]):
        return "Tablet"
    if any(k in x for k in ["macbook", "laptop", "thinkpad"]):
        return "Laptop"
    if any(k in x for k in ["tv", "chromecast", "roku"]):
        return "TV"
    return "Device"


def is_valid_mac(mac: str) -> bool:
    parts = mac.split(":")
    if len(parts) != 6:
        return False
    try:
        return all(len(p) == 2 and 0 <= int(p, 16) <= 255 for p in parts)
    except Exception:
        return False


def is_valid_ipv4(ip: str) -> bool:
    try:
        ip_network(f"{ip}/32", strict=False)
        return ip.count(".") == 3
    except Exception:
        return False


def is_valid_cidr(cidr: str) -> bool:
    try:
        ip_network(cidr, strict=False)
        return "/" in cidr
    except Exception:
        return False


def subnet_from_ip(ip: str) -> str:
    parts = ip.split(".")
    if len(parts) == 4:
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    return "unknown"


def read_dhcp_leases() -> dict[str, dict[str, str | None]]:
    out = exec_text("cat /var/lib/misc/dnsmasq.leases")
    leases: dict[str, dict[str, str | None]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        _, mac, ip, host = parts[:4]
        leases[ip] = {"mac": mac.lower(), "hostname": None if host == "*" else host}
    return leases


def discover_clients(state: dict[str, Any]) -> list[dict[str, Any]]:
    neigh = exec_text("ip -4 neigh show")
    leases = read_dhcp_leases()
    blocked = {x.lower() for x in state.get("blockedMacs", [])}
    rows: dict[str, dict[str, Any]] = {}

    # Live neighbors
    for line in neigh.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        ip = parts[0]
        status = parts[-1]
        if status in {"FAILED", "INCOMPLETE"}:
            continue
        mac = ""
        iface = "unknown"
        if "lladdr" in parts:
            idx = parts.index("lladdr")
            if idx + 1 < len(parts):
                mac = parts[idx + 1].lower()
        if "dev" in parts:
            idx = parts.index("dev")
            if idx + 1 < len(parts):
                iface = parts[idx + 1]
        lease = leases.get(ip, {})
        hostname = lease.get("hostname")
        resolved_mac = mac or str(lease.get("mac") or "N/A")
        rows[ip] = {
            "name": state.get("deviceNames", {}).get(resolved_mac.lower()) or hostname or f"client-{ip.split('.')[-1]}",
            "ip": ip,
            "subnet": subnet_from_ip(ip),
            "mac": resolved_mac,
            "iface": iface,
            "type": infer_device_type(hostname or ""),
            "status": "Idle" if status == "STALE" else "Online",
            "blocked": resolved_mac != "N/A" and resolved_mac.lower() in blocked,
            "staticLeaseIp": state.get("staticLeases", {}).get(resolved_mac.lower()),
        }

    # Lease entries
    for ip, lease in leases.items():
        if ip in rows:
            continue
        hostname = lease.get("hostname") or ""
        resolved_mac = str(lease.get("mac") or "N/A")
        rows[ip] = {
            "name": state.get("deviceNames", {}).get(resolved_mac.lower()) or hostname or f"client-{ip.split('.')[-1]}",
            "ip": ip,
            "subnet": subnet_from_ip(ip),
            "mac": resolved_mac,
            "iface": "dhcp",
            "type": infer_device_type(hostname),
            "status": "Lease",
            "blocked": resolved_mac != "N/A" and resolved_mac.lower() in blocked,
            "staticLeaseIp": state.get("staticLeases", {}).get(resolved_mac.lower()),
        }

    # Configured static hosts from dnsmasq.conf
    dns_cfg = parse_dnsmasq_conf()
    for host in dns_cfg.get("hosts", []):
        ip = str(host.get("ip", ""))
        mac = str(host.get("mac", "N/A")).lower()
        if not ip or ip in rows:
            continue
        hostname = str(host.get("hostname", ""))
        rows[ip] = {
            "name": state.get("deviceNames", {}).get(mac) or hostname or f"client-{ip.split('.')[-1]}",
            "ip": ip,
            "subnet": subnet_from_ip(ip),
            "mac": mac,
            "iface": "dhcp-config",
            "type": infer_device_type(hostname),
            "status": "Configured",
            "blocked": mac in blocked,
            "staticLeaseIp": state.get("staticLeases", {}).get(mac) or ip,
        }

    # State-only configured devices
    for mac, ip in state.get("staticLeases", {}).items():
        ip_s = str(ip)
        mac_l = str(mac).lower()
        if not ip_s or ip_s in rows:
            continue
        name = str(state.get("deviceNames", {}).get(mac_l, "")).strip()
        rows[ip_s] = {
            "name": name or f"client-{ip_s.split('.')[-1]}",
            "ip": ip_s,
            "subnet": subnet_from_ip(ip_s),
            "mac": mac_l,
            "iface": "piroutergui",
            "type": infer_device_type(name),
            "status": "Configured",
            "blocked": mac_l in blocked,
            "staticLeaseIp": ip_s,
        }

    def _ip_key(row: dict[str, Any]) -> list[int]:
        try:
            return [int(p) for p in str(row["ip"]).split(".")]
        except Exception:
            return [999, 999, 999, 999]

    return sorted(rows.values(), key=_ip_key)


def merge_dnsmasq_hosts_into_state(state: dict[str, Any]) -> None:
    if state.get("meta", {}).get("importedDnsmasqHosts"):
        return

    for host in parse_dnsmasq_conf().get("hosts", []):
        mac = str(host.get("mac", "")).lower()
        ip = str(host.get("ip", "")).strip()
        if not mac or not ip:
            continue
        state.setdefault("staticLeases", {}).setdefault(mac, ip)
        hostname = str(host.get("hostname", "")).strip()
        if hostname:
            state.setdefault("deviceNames", {}).setdefault(mac, hostname)

    state.setdefault("meta", {})["importedDnsmasqHosts"] = True


def apply_dnsmasq_settings(state: dict[str, Any]) -> dict[str, Any]:
    merge_dnsmasq_hosts_into_state(state)
    save_state(state)

    cfg = state["dhcp"]
    iface = cfg["interface"]
    r0, r1, mask, lease = cfg["rangeStart"], cfg["rangeEnd"], cfg["netmask"], cfg["leaseTime"]

    static_lines: list[str] = []
    for mac, ip in sorted(state.get("staticLeases", {}).items(), key=lambda x: str(x[1])):
        if not is_valid_mac(str(mac).lower()) or not is_valid_ipv4(str(ip)):
            continue
        host = str(state.get("deviceNames", {}).get(str(mac).lower(), "")).strip()
        if host:
            static_lines.append(f"dhcp-host={str(mac).lower()},{str(ip).strip()},{host}")
        else:
            static_lines.append(f"dhcp-host={str(mac).lower()},{str(ip).strip()}")

    block_lines = [
        "# Generated by PiRouterGUI",
        f"interface={iface}",
        f"dhcp-range={r0},{r1},{mask},{lease}",
        *static_lines,
    ]
    block = "\n".join(block_lines)

    old_text = ""
    if DNSMASQ_CONFIG_PATH.exists():
        old_text = DNSMASQ_CONFIG_PATH.read_text()
    new_text = set_managed_block_text(old_text, DNSMASQ_BEGIN, DNSMASQ_END, block)

    DNSMASQ_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_if_exists(DNSMASQ_CONFIG_PATH, "dnsmasq-conf")
    DNSMASQ_CONFIG_PATH.write_text(new_text)

    check = run_cmd("dnsmasq --test")
    if not check["ok"]:
        restore_from_backup(DNSMASQ_CONFIG_PATH, backup)
        return {"ok": False, "backupPath": backup, "error": f"dnsmasq validation failed: {check['error']}"}

    reload_res = run_cmd(DNSMASQ_RELOAD_CMD)
    if not reload_res["ok"]:
        restore_from_backup(DNSMASQ_CONFIG_PATH, backup)
        return {"ok": False, "backupPath": backup, "error": f"dnsmasq reload failed: {reload_res['error']}"}

    return {"ok": True, "backupPath": backup, "validated": True, "reloaded": True}


def apply_nft_blocklist(state: dict[str, Any]) -> dict[str, Any]:
    NFT_MANAGED_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup = backup_if_exists(NFT_MANAGED_PATH, "nft-managed")

    blocked = [str(x).lower() for x in state.get("blockedMacs", []) if is_valid_mac(str(x).lower())]
    nft = [
        "#!/usr/sbin/nft -f",
        "# Managed by PiRouterGUI",
        "table inet piroutergui {",
        "  set blocked_macs {",
        "    type ether_addr",
        "    elements = {",
        f"      {', '.join(sorted(blocked))}" if blocked else "",
        "    }",
        "  }",
        "  chain forward {",
        "    type filter hook forward priority 0; policy accept;",
        "    ether saddr @blocked_macs drop",
        "  }",
        "}",
    ]
    NFT_MANAGED_PATH.write_text("\n".join(nft) + "\n")

    check = run_cmd(f"nft -c -f {NFT_MANAGED_PATH}")
    if not check["ok"]:
        restore_from_backup(NFT_MANAGED_PATH, backup)
        return {"ok": False, "backupPath": backup, "error": f"nft validation failed: {check['error']}"}

    apply = run_cmd(NFT_APPLY_CMD)
    if not apply["ok"]:
        restore_from_backup(NFT_MANAGED_PATH, backup)
        return {"ok": False, "backupPath": backup, "error": f"nft apply failed: {apply['error']}"}

    return {"ok": True, "backupPath": backup, "validated": True, "applied": True}


def write_managed_files(state: dict[str, Any]) -> dict[str, Any]:
    dns = apply_dnsmasq_settings(state)
    nft = apply_nft_blocklist(state)
    return {"dnsmasq": dns, "nftables": nft}


def apply_network_settings(state: dict[str, Any]) -> dict[str, Any]:
    net = state["network"]
    iface = net["wlanIface"]
    cidr = net["wlanCidr"]
    if not is_valid_cidr(cidr):
        return {"ok": False, "error": "invalid wlan CIDR"}

    old_text = RC_LOCAL_PATH.read_text() if RC_LOCAL_PATH.exists() else "#!/bin/bash\n\nexit 0\n"
    block = f"# Generated by PiRouterGUI\nip link set {iface} up\nip addr replace {cidr} dev {iface}"
    new_text = set_managed_block_text(old_text, RCLOCAL_BEGIN, RCLOCAL_END, block)

    backup = backup_if_exists(RC_LOCAL_PATH, "rc-local")
    RC_LOCAL_PATH.write_text(new_text)
    run_cmd(f"chmod +x {RC_LOCAL_PATH}")

    apply1 = run_cmd(f"ip link set {iface} up")
    apply2 = run_cmd(f"ip addr replace {cidr} dev {iface}")
    if not apply1["ok"] or not apply2["ok"]:
        restore_from_backup(RC_LOCAL_PATH, backup)
        return {"ok": False, "backupPath": backup, "error": (apply1.get("error") or apply2.get("error") or "failed applying interface config")}

    return {"ok": True, "backupPath": backup}


def apply_wifi_settings(state: dict[str, Any]) -> dict[str, Any]:
    wifi = state["wifi"]
    iface = wifi["interface"]
    ssid = wifi["ssid"]
    channel = wifi["channel"]
    hw_mode = wifi["hwMode"]
    passphrase = wifi["wpaPassphrase"]

    content = "\n".join(
        [
            f"interface={iface}",
            "driver=nl80211",
            f"ssid={ssid}",
            f"hw_mode={hw_mode}",
            f"channel={channel}",
            "wmm_enabled=0",
            "auth_algs=1",
            "wpa=2",
            f"wpa_passphrase={passphrase}",
            "wpa_key_mgmt=WPA-PSK",
            "rsn_pairwise=CCMP",
            "",
            "ctrl_interface=/var/run/hostapd",
            "ctrl_interface_group=0",
            "",
        ]
    )

    HOSTAPD_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    b1 = backup_if_exists(HOSTAPD_CONF_PATH, "hostapd-conf")
    b2 = backup_if_exists(HOSTAPD_DEFAULT_PATH, "hostapd-default")

    HOSTAPD_CONF_PATH.write_text(content)
    HOSTAPD_DEFAULT_PATH.write_text(f'DAEMON_CONF="{HOSTAPD_CONF_PATH}"\n')

    check = run_cmd(f"hostapd -t {HOSTAPD_CONF_PATH}")
    if not check["ok"]:
        restore_from_backup(HOSTAPD_CONF_PATH, b1)
        restore_from_backup(HOSTAPD_DEFAULT_PATH, b2)
        return {"ok": False, "backupPath": b1, "error": f"hostapd validation failed: {check['error']}"}

    restart = run_cmd(HOSTAPD_RESTART_CMD)
    if not restart["ok"]:
        restore_from_backup(HOSTAPD_CONF_PATH, b1)
        restore_from_backup(HOSTAPD_DEFAULT_PATH, b2)
        return {"ok": False, "backupPath": b1, "error": f"hostapd restart failed: {restart['error']}"}

    return {"ok": True, "backupPath": b1, "restarted": True}


def _ensure_forward_rule(wifi_iface: str, uplink_iface: str, should_exist: bool) -> str | None:
    check = run_cmd(f"iptables -C FORWARD -i {wifi_iface} -o {uplink_iface} -j DROP")
    if should_exist and not check["ok"]:
        add = run_cmd(f"iptables -A FORWARD -i {wifi_iface} -o {uplink_iface} -j DROP")
        if not add["ok"]:
            return add.get("error")
    if not should_exist and check["ok"]:
        rem = run_cmd(f"iptables -D FORWARD -i {wifi_iface} -o {uplink_iface} -j DROP")
        if not rem["ok"]:
            return rem.get("error")
    return None


def apply_firewall_settings(state: dict[str, Any]) -> dict[str, Any]:
    fw = state["firewall"]
    wifi_iface = fw["wifiIface"]
    uplink_iface = fw["uplinkIface"]
    enabled = bool(fw["enabled"])

    backup = backup_if_exists(IPTABLES_RULES_PATH, "iptables-rules")

    # Only manage pair-wise isolation rules for wifi <-> uplink. Do not change global FORWARD policy.
    e1 = _ensure_forward_rule(wifi_iface, uplink_iface, enabled)
    e2 = _ensure_forward_rule(uplink_iface, wifi_iface, enabled)
    if e1 or e2:
        return {"ok": False, "backupPath": backup, "error": e1 or e2}

    save = run_cmd(f"iptables-save > {IPTABLES_RULES_PATH}")
    if not save["ok"]:
        return {"ok": False, "backupPath": backup, "error": f"failed to persist iptables: {save.get('error', '')}"}

    return {"ok": True, "backupPath": backup, "persisted": True}


def read_firewall_state(defaults: dict[str, Any]) -> dict[str, Any]:
    out = exec_text("iptables -S FORWARD")
    rule_a = f"-A FORWARD -i {defaults['wifiIface']} -o {defaults['uplinkIface']} -j DROP"
    rule_b = f"-A FORWARD -i {defaults['uplinkIface']} -o {defaults['wifiIface']} -j DROP"
    enabled = rule_a in out and rule_b in out
    data = dict(defaults)
    data["enabled"] = enabled
    return data


def get_monitor_data() -> dict[str, str]:
    return {
        "hostapdStations": exec_text("hostapd_cli all_sta") or "(no stations)",
        "dhcpLeases": exec_text("cat /var/lib/misc/dnsmasq.leases") or "(no leases)",
        "neighbors": exec_text("ip neigh show") or "(no neighbors)",
        "interfaces": exec_text("ip -4 addr show") or "(no interface data)",
        "routes": exec_text("ip -4 route show") or "(no route data)",
    }


def get_overview() -> dict[str, Any]:
    state = load_state()

    # Pull live config defaults from host files
    dns = parse_dnsmasq_conf()
    wifi_live = parse_hostapd_conf()

    state["dhcp"].update(
        {
            "interface": dns.get("interface", state["dhcp"]["interface"]),
            "rangeStart": dns.get("rangeStart", state["dhcp"]["rangeStart"]),
            "rangeEnd": dns.get("rangeEnd", state["dhcp"]["rangeEnd"]),
            "netmask": dns.get("netmask", state["dhcp"]["netmask"]),
            "leaseTime": dns.get("leaseTime", state["dhcp"]["leaseTime"]),
        }
    )
    state["wifi"].update(
        {
            "interface": wifi_live.get("interface", state["wifi"]["interface"]),
            "ssid": wifi_live.get("ssid", state["wifi"]["ssid"]),
            "channel": wifi_live.get("channel", state["wifi"]["channel"]),
            "hwMode": wifi_live.get("hw_mode", state["wifi"]["hwMode"]),
            "wpaPassphrase": wifi_live.get("wpa_passphrase", state["wifi"]["wpaPassphrase"]),
        }
    )

    wlan_iface = state["network"].get("wlanIface", "wlan0")
    live_cidr = read_wlan_cidr(wlan_iface)
    if live_cidr:
        state["network"]["wlanCidr"] = live_cidr

    state["firewall"] = read_firewall_state(state["firewall"])

    loadavg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    cpus = os.cpu_count() or 1
    mem_total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    mem_free = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
    mem_total_gb = mem_total / (1024**3)
    mem_used_gb = (mem_total - mem_free) / (1024**3)

    return {
        "node": os.uname().nodename,
        "uptimeSec": float(exec_text("cut -d. -f1 /proc/uptime") or 0),
        "stats": {
            "cpuLoadPct": max(0, min(100, round((loadavg / cpus) * 100, 1))),
            "memUsedGb": round(mem_used_gb, 2),
            "memTotalGb": round(mem_total_gb, 2),
            "wanIp": exec_text("curl -s --max-time 2 https://ifconfig.me") or "N/A",
        },
        "services": {
            "hostapd": exec_text("systemctl is-active hostapd") or "unknown",
            "dnsmasq": exec_text("systemctl is-active dnsmasq") or "unknown",
            "nftables": exec_text("systemctl is-active nftables") or "unknown",
            "piroutergui": exec_text("systemctl is-active piroutergui") or "unknown",
        },
        "networks": get_local_networks(),
        "interfaces": parse_interfaces(),
        "network": state["network"],
        "wifi": state["wifi"],
        "dhcp": state["dhcp"],
        "firewall": state["firewall"],
        "clients": discover_clients(state),
        "monitor": get_monitor_data(),
    }


def render_overview(request: Request, message: str = "") -> HTMLResponse:
    return templates.TemplateResponse(request, "_overview.html", {"overview": get_overview(), "message": message})


def apply_message(prefix: str, result: dict[str, Any]) -> str:
    if result.get("ok"):
        return prefix
    return f"{prefix} (warning): {result.get('error', 'unknown error')}"


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if not AUTH_ENABLED:
        return await call_next(request)

    path = request.url.path
    if path.startswith("/static") or path == "/login":
        return await call_next(request)

    if is_authenticated(request):
        return await call_next(request)

    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": ""})


@app.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if not AUTH_ENABLED:
        return RedirectResponse(url="/", status_code=302)

    if hmac.compare_digest(username, AUTH_USERNAME) and hmac.compare_digest(password, AUTH_PASSWORD):
        resp = RedirectResponse(url="/", status_code=302)
        resp.set_cookie(AUTH_COOKIE, auth_cookie_value(), httponly=True, samesite="lax")
        return resp

    return templates.TemplateResponse(request, "login.html", {"error": "Invalid username or password"})


@app.post("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=302)
    resp.delete_cookie(AUTH_COOKIE)
    return resp


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"overview": get_overview(), "message": ""})


@app.get("/partials/overview", response_class=HTMLResponse)
def overview_partial(request: Request):
    return render_overview(request)


@app.post("/network/apply", response_class=HTMLResponse)
def update_network(request: Request, wlan_iface: str = Form(...), wlan_cidr: str = Form(...)):
    state = load_state()
    state["network"].update({"wlanIface": wlan_iface.strip(), "wlanCidr": wlan_cidr.strip()})
    # Keep firewall Wi-Fi iface aligned, but uplink is managed only from Firewall panel.
    state["firewall"].update({"wifiIface": wlan_iface.strip()})
    save_state(state)
    res = apply_network_settings(state)
    return render_overview(request, apply_message("Network settings applied.", res))


@app.post("/wifi/apply", response_class=HTMLResponse)
def update_wifi(
    request: Request,
    interface: str = Form(...),
    ssid: str = Form(...),
    passphrase: str = Form(...),
    channel: str = Form(...),
    hw_mode: str = Form("g"),
):
    state = load_state()
    state["wifi"].update(
        {
            "interface": interface.strip(),
            "ssid": ssid.strip(),
            "wpaPassphrase": passphrase.strip(),
            "channel": channel.strip(),
            "hwMode": hw_mode.strip() or "g",
        }
    )
    save_state(state)
    res = apply_wifi_settings(state)
    return render_overview(request, apply_message("Wi-Fi AP settings applied.", res))


@app.post("/dhcp/apply", response_class=HTMLResponse)
def update_dhcp(
    request: Request,
    interface: str = Form(...),
    range_start: str = Form(...),
    range_end: str = Form(...),
    netmask: str = Form(...),
    lease_time: str = Form(...),
):
    state = load_state()
    state["dhcp"].update(
        {
            "interface": interface.strip(),
            "rangeStart": range_start.strip(),
            "rangeEnd": range_end.strip(),
            "netmask": netmask.strip(),
            "leaseTime": lease_time.strip(),
        }
    )
    save_state(state)
    res = apply_dnsmasq_settings(state)
    return render_overview(request, apply_message("DHCP settings applied.", res))


@app.post("/firewall/apply", response_class=HTMLResponse)
def update_firewall(request: Request, uplink_iface: str = Form(...), enabled: str | None = Form(None)):
    state = load_state()
    wifi_iface = state.get("network", {}).get("wlanIface", state.get("firewall", {}).get("wifiIface", "wlan0"))
    state["firewall"].update(
        {
            "wifiIface": wifi_iface.strip(),
            "uplinkIface": uplink_iface.strip(),
            "enabled": enabled == "on",
        }
    )
    state["network"]["uplinkIface"] = uplink_iface.strip()
    save_state(state)
    res = apply_firewall_settings(state)
    return render_overview(request, apply_message("Firewall isolation settings applied.", res))


@app.post("/clients/add", response_class=HTMLResponse)
def add_client(request: Request, mac: str = Form(...), ip: str = Form(...), hostname: str = Form("")):
    mac = mac.strip().lower()
    ip = ip.strip()
    hostname = hostname.strip()

    if not is_valid_mac(mac):
        return render_overview(request, "Add device failed: invalid MAC format.")
    if not is_valid_ipv4(ip):
        return render_overview(request, "Add device failed: invalid IPv4 address.")

    state = load_state()
    state.setdefault("staticLeases", {})[mac] = ip
    if hostname:
        state.setdefault("deviceNames", {})[mac] = hostname
    save_state(state)
    apply = write_managed_files(state)
    errs = [x.get("error") for x in [apply.get("dnsmasq", {}), apply.get("nftables", {})] if x.get("error")]
    msg = "Device added." if not errs else f"Device added with warnings: {' | '.join(errs)}"
    return render_overview(request, msg)


@app.post("/clients/{mac}/block", response_class=HTMLResponse)
def block_client(request: Request, mac: str):
    state = load_state()
    mac = mac.lower()
    if mac not in state["blockedMacs"]:
        state["blockedMacs"].append(mac)
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, apply_message("Client blocked.", apply.get("nftables", {})))


@app.post("/clients/{mac}/unblock", response_class=HTMLResponse)
def unblock_client(request: Request, mac: str):
    state = load_state()
    state["blockedMacs"] = [x for x in state["blockedMacs"] if x != mac.lower()]
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, apply_message("Client unblocked.", apply.get("nftables", {})))


@app.post("/clients/{mac}/static-lease", response_class=HTMLResponse)
def set_static_lease(request: Request, mac: str, ip: str = Form(...)):
    if not is_valid_ipv4(ip.strip()):
        return render_overview(request, "Static lease failed: invalid IPv4 address.")
    state = load_state()
    state.setdefault("staticLeases", {})[mac.lower()] = ip.strip()
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, apply_message("Static lease saved.", apply.get("dnsmasq", {})))


@app.post("/clients/{mac}/static-lease/delete", response_class=HTMLResponse)
def clear_static_lease(request: Request, mac: str):
    state = load_state()
    state.setdefault("staticLeases", {}).pop(mac.lower(), None)
    state.setdefault("deviceNames", {}).pop(mac.lower(), None)
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, apply_message("Static lease removed.", apply.get("dnsmasq", {})))


@app.post("/system/apply", response_class=HTMLResponse)
def apply_all(request: Request):
    state = load_state()
    parts = [
        apply_network_settings(state),
        apply_wifi_settings(state),
        apply_dnsmasq_settings(state),
        apply_firewall_settings(state),
        apply_nft_blocklist(state),
    ]
    errors = [p.get("error") for p in parts if not p.get("ok") and p.get("error")]
    msg = "All settings applied." if not errors else f"Applied with warnings: {' | '.join(errors)}"
    return render_overview(request, msg)
