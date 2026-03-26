# PiRouterGUI

Pi-first router admin UI built with **Python + FastAPI + HTMX**.

## Current capabilities

- Service health dashboard (`hostapd`, `dnsmasq`, `nftables`, `piroutergui`)
- Interfaces + routes view
- **Network panel**: set Wi‑Fi interface + CIDR (`wlan0`, `192.168.50.1/24`)
- **Wi‑Fi AP panel**: edit hostapd settings (SSID, passphrase, channel, hw mode)
- **DHCP panel**: edit dnsmasq interface/range/lease + static leases
- **Firewall panel**: toggle isolation rules between Wi‑Fi and uplink interfaces
- Device inventory from:
  - `ip neigh`
  - `dnsmasq.leases`
  - static `dhcp-host` entries
  - PiRouterGUI-added devices
- Per-device actions: block/unblock, set/clear static lease
- Add new device form (MAC + IP + optional hostname)
- Monitoring panels (hostapd stations, leases, neighbors, interfaces, routes)
- Login authentication (cookie session)
- Inline descriptions in each section (what it does + which file(s) it affects)

## Screenshot

![PiRouterGUI dashboard](docs/assets/htmx-dashboard-desktop.png)

## One-command Pi install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/install-pi.sh | bash
```

Installer behavior:
- installs required packages (`python3`, `hostapd`, `dnsmasq`, `iptables-persistent`, etc.)
- clones/updates repo to `~/piroutergui`
- creates `.venv` only if missing
- installs Python deps only when `requirements.txt` changes
- installs + starts `piroutergui.service`
- enables service on boot

Open: `http://<pi-ip>:8080`

## Updates

```bash
cd ~/piroutergui
git pull --ff-only
./scripts/install-pi.sh
```

## Service operations

```bash
sudo systemctl status piroutergui
sudo systemctl restart piroutergui
sudo journalctl -u piroutergui -f
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
```

Optional cleanup:

```bash
REMOVE_APP_DIR=true curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
REMOVE_APP_DIR=true REMOVE_STATE=true curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
```

## Authentication

Enabled by default.

Default credentials (change immediately):
- Username: `admin`
- Password: `change-me`

Configured in `/etc/systemd/system/piroutergui.service` via:
- `PRG_AUTH_ENABLED`
- `PRG_AUTH_USERNAME`
- `PRG_AUTH_PASSWORD`
- `PRG_AUTH_SECRET`

## Safety / file writes

- Backups are stored in: `state/backups/*.bak`
- Service runs as root (needed for host network config writes)
- Core config paths are environment-configurable:
  - `PRG_DNSMASQ_CONFIG_PATH` (default `/etc/dnsmasq.conf`)
  - `PRG_HOSTAPD_CONF_PATH` (default `/etc/hostapd/hostapd.conf`)
  - `PRG_HOSTAPD_DEFAULT_PATH` (default `/etc/default/hostapd`)
  - `PRG_RC_LOCAL_PATH` (default `/etc/rc.local`)
  - `PRG_IPTABLES_RULES_PATH` (default `/etc/iptables/rules.v4`)
  - `PRG_NFT_MANAGED_PATH` (default `/etc/nftables.d/piroutergui-blocklist.nft`)

## Docker (full-control mode)

```bash
git clone https://github.com/wicksense/piroutergui.git
cd piroutergui
sudo docker compose -f docker-compose.full.yml up -d --build
```
