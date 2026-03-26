# PiRouterGUI

Pi-first router admin UI using **Python + FastAPI + HTMX**.

## What it now covers

- Dashboard + service health (`hostapd`, `dnsmasq`, `nftables`, `piroutergui`)
- Interfaces view (LAN/WLAN addresses + routes)
- **Network config** (`wlan` interface + CIDR)
- **Wi-Fi AP config** (SSID, passphrase, channel, hw mode) → writes hostapd config
- **DHCP config** (interface, range, lease duration, static leases) → writes dnsmasq managed block
- **Firewall isolation** toggle (`wlan <-> uplink` block rules) + persist with `iptables-save`
- Client inventory from neighbors + leases + dnsmasq static host config + UI-added devices
- Add/edit/remove static leases from UI
- Monitoring panels (`hostapd_cli`, leases, neighbors, interfaces, routes)
- Authenticated access (login/logout)

## Screenshots (HTMX UI)

![PiRouterGUI HTMX desktop dashboard](docs/assets/htmx-dashboard-desktop.png)

![PiRouterGUI HTMX mobile dashboard](docs/assets/htmx-dashboard-mobile.png)

## Easiest Pi install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/install-pi.sh | bash
```

This will:
- install system deps (`python3`, `hostapd`, `dnsmasq`, `iptables-persistent`, etc.)
- clone/update repo in `~/piroutergui`
- create `.venv` only if missing
- install Python deps only if `requirements.txt` changed
- install + start `piroutergui.service`
- enable service on boot

Open: `http://<pi-ip>:8080`

## Service management

```bash
sudo systemctl status piroutergui
sudo systemctl restart piroutergui
sudo journalctl -u piroutergui -f
```

## Uninstall

```bash
curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
```

Optional flags:

```bash
REMOVE_APP_DIR=true curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
REMOVE_APP_DIR=true REMOVE_STATE=true curl -fsSL https://raw.githubusercontent.com/wicksense/piroutergui/main/scripts/uninstall-pi.sh | bash
```

## Authentication

Enabled by default.

Default credentials (change immediately):
- Username: `admin`
- Password: `change-me`

Configured via systemd environment in `/etc/systemd/system/piroutergui.service`:
- `PRG_AUTH_ENABLED=true|false`
- `PRG_AUTH_USERNAME=...`
- `PRG_AUTH_PASSWORD=...`
- `PRG_AUTH_SECRET=...`

## Safety model

- Backup before state/config writes: `state/backups/*.bak`
- Managed config writes + validation/reload attempts
- Core config paths (service env):
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
