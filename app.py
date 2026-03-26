from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
BACKUP_DIR = STATE_DIR / "backups"
STATE_PATH = STATE_DIR / "client-actions.json"

DNSMASQ_MANAGED_PATH = Path(os.getenv("PRG_DNSMASQ_MANAGED_PATH", "/etc/dnsmasq.d/piroutergui-static.conf"))
NFT_MANAGED_PATH = Path(os.getenv("PRG_NFT_MANAGED_PATH", "/etc/nftables.d/piroutergui-blocklist.nft"))
DNSMASQ_RELOAD_CMD = os.getenv("PRG_DNSMASQ_RELOAD_CMD", "systemctl reload dnsmasq")
NFT_APPLY_CMD = os.getenv("PRG_NFT_APPLY_CMD", f"nft -f {NFT_MANAGED_PATH}")

app = FastAPI(title="PiRouterGUI")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


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


def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {"blockedMacs": [], "staticLeases": {}}


def save_state(state: dict[str, Any]) -> str | None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    b = backup_if_exists(STATE_PATH, "client-actions")
    STATE_PATH.write_text(json.dumps(state, indent=2))
    return b


def write_managed_files(state: dict[str, Any]) -> dict[str, Any]:
    result = {"dnsmasq": {}, "nftables": {}}

    DNSMASQ_MANAGED_PATH.parent.mkdir(parents=True, exist_ok=True)
    result["dnsmasq"]["backupPath"] = backup_if_exists(DNSMASQ_MANAGED_PATH, "dnsmasq-managed")
    dns_lines = ["# Managed by PiRouterGUI"]
    for mac, ip in state.get("staticLeases", {}).items():
        dns_lines.append(f"dhcp-host={str(mac).lower()},{str(ip).strip()}")
    DNSMASQ_MANAGED_PATH.write_text("\n".join(dns_lines) + "\n")
    check = run_cmd("dnsmasq --test")
    if check["ok"]:
        result["dnsmasq"]["validated"] = True
        reload_res = run_cmd(DNSMASQ_RELOAD_CMD)
        result["dnsmasq"]["reloaded"] = reload_res["ok"]
        if not reload_res["ok"]:
            result["dnsmasq"]["error"] = reload_res["error"]
    else:
        result["dnsmasq"]["error"] = check["error"]

    NFT_MANAGED_PATH.parent.mkdir(parents=True, exist_ok=True)
    result["nftables"]["backupPath"] = backup_if_exists(NFT_MANAGED_PATH, "nft-managed")
    blocked = [str(x).lower() for x in state.get("blockedMacs", []) if x]
    nft = [
        "#!/usr/sbin/nft -f",
        "# Managed by PiRouterGUI",
        "table inet piroutergui {",
        "  set blocked_macs {",
        "    type ether_addr",
        "    elements = {",
        f"      {', '.join(blocked)}" if blocked else "",
        "    }",
        "  }",
        "  chain forward {",
        "    type filter hook forward priority 0; policy accept;",
        "    ether saddr @blocked_macs drop",
        "  }",
        "}",
    ]
    NFT_MANAGED_PATH.write_text("\n".join(nft) + "\n")
    check2 = run_cmd(f"nft -c -f {NFT_MANAGED_PATH}")
    if check2["ok"]:
        result["nftables"]["validated"] = True
        apply_res = run_cmd(NFT_APPLY_CMD)
        result["nftables"]["applied"] = apply_res["ok"]
        if not apply_res["ok"]:
            result["nftables"]["error"] = apply_res["error"]
    else:
        result["nftables"]["error"] = check2["error"]

    return result


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


def infer_device_type(name: str) -> str:
    x = name.lower()
    if any(k in x for k in ["iphone", "pixel", "android"]):
        return "Phone"
    if any(k in x for k in ["ipad", "tablet"]):
        return "Tablet"
    if any(k in x for k in ["macbook", "laptop", "thinkpad"]):
        return "Laptop"
    if any(k in x for k in ["tv", "chromecast", "roku"]):
        return "TV"
    return "Device"


def discover_clients() -> list[dict[str, Any]]:
    neigh = exec_text("ip -4 neigh show")
    leases = read_dhcp_leases()
    state = load_state()
    blocked = {x.lower() for x in state.get("blockedMacs", [])}
    rows: dict[str, dict[str, Any]] = {}

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
            "name": hostname or f"client-{ip.split('.')[-1]}",
            "ip": ip,
            "mac": resolved_mac,
            "iface": iface,
            "type": infer_device_type(hostname or ""),
            "status": "Idle" if status == "STALE" else "Online",
            "blocked": resolved_mac != "N/A" and resolved_mac.lower() in blocked,
            "staticLeaseIp": state.get("staticLeases", {}).get(resolved_mac.lower()),
        }

    return sorted(rows.values(), key=lambda x: [int(p) for p in x["ip"].split(".")])


def get_overview() -> dict[str, Any]:
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
        },
        "clients": discover_clients(),
    }


def render_overview(request: Request, message: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "_overview.html",
        {"overview": get_overview(), "message": message},
    )


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, "index.html", {"overview": get_overview(), "message": ""})


@app.get("/partials/overview", response_class=HTMLResponse)
def overview_partial(request: Request):
    return render_overview(request)


@app.post("/clients/{mac}/block", response_class=HTMLResponse)
def block_client(request: Request, mac: str):
    state = load_state()
    mac = mac.lower()
    if mac not in state["blockedMacs"]:
        state["blockedMacs"].append(mac)
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, "Client blocked." if not apply["nftables"].get("error") else f"Block warning: {apply['nftables'].get('error')}")


@app.post("/clients/{mac}/unblock", response_class=HTMLResponse)
def unblock_client(request: Request, mac: str):
    state = load_state()
    state["blockedMacs"] = [x for x in state["blockedMacs"] if x != mac.lower()]
    save_state(state)
    write_managed_files(state)
    return render_overview(request, "Client unblocked.")


@app.post("/clients/{mac}/static-lease", response_class=HTMLResponse)
def set_static_lease(request: Request, mac: str, ip: str = Form(...)):
    state = load_state()
    state.setdefault("staticLeases", {})[mac.lower()] = ip.strip()
    save_state(state)
    apply = write_managed_files(state)
    return render_overview(request, "Static lease saved." if not apply["dnsmasq"].get("error") else f"Lease warning: {apply['dnsmasq'].get('error')}")


@app.post("/clients/{mac}/static-lease/delete", response_class=HTMLResponse)
def clear_static_lease(request: Request, mac: str):
    state = load_state()
    state.setdefault("staticLeases", {}).pop(mac.lower(), None)
    save_state(state)
    write_managed_files(state)
    return render_overview(request, "Static lease removed.")


@app.post("/system/apply", response_class=HTMLResponse)
def apply_config(request: Request):
    state = load_state()
    apply = write_managed_files(state)
    errs = [x.get("error") for x in [apply.get("dnsmasq", {}), apply.get("nftables", {})] if x.get("error")]
    msg = "Managed config applied." if not errs else f"Apply warnings: {' | '.join(errs)}"
    return render_overview(request, msg)
