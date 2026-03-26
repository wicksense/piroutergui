# PiRouterGUI

A modern web interface for managing a Raspberry Pi based router.

## Current status

Implemented:
- Responsive dashboard shell
- Sidebar navigation
- System status cards
- Connected clients discovery (`ip neigh` + `dnsmasq.leases` enrichment)
- Client actions: block/unblock + static lease set/clear
- Managed config apply for dnsmasq + nftables
- Backup-first writes for state and managed config files

## Screenshots

### Desktop dashboard

![PiRouterGUI desktop dashboard](docs/assets/dashboard-desktop.png)

### Mobile layout

![PiRouterGUI mobile dashboard](docs/assets/dashboard-mobile.png)

## Getting started

```bash
npm install
npm run dev:api   # terminal 1 (API on :8080)
npm run dev       # terminal 2 (UI on :5173)
```

Then open http://localhost:5173

## Safety behavior

- Every client action change auto-backs up previous state file to:
  - `server/state/backups/client-actions-YYYYMMDD-HHMMSS.bak`
- Managed system files are written separately (no primary config overwrite):
  - `PRG_DNSMASQ_MANAGED_PATH` (default `/etc/dnsmasq.d/piroutergui-static.conf`)
  - `PRG_NFT_MANAGED_PATH` (default `/etc/nftables.d/piroutergui-blocklist.nft`)
- Before each managed file write, existing file is backed up into `server/state/backups/`
- Validation happens before reload/apply:
  - `dnsmasq --test`
  - `nft -c -f <managed file>`
- Runtime state and backups are ignored by git.

## Next steps

- Add authentication/session controls
- Add stronger input validation + conflict checks for static IP assignment
- Add router logs view + service restart controls
- Add WAN/LAN/DHCP/Wi-Fi full config forms
