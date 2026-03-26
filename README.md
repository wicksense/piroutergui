# PiRouterGUI

A modern web interface for managing a Raspberry Pi based router.

## Current status

Initial UI scaffold is complete:
- Responsive dashboard shell
- Sidebar navigation
- System status cards
- Connected clients table

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
- Runtime state and backups are ignored by git.

## Next steps

- Convert block/unblock to real firewall enforcement (nftables rules)
- Convert static lease action to dnsmasq hostfile writes + service reload
- Build auth/session handling
- Add forms for WAN/LAN, DHCP, Wi-Fi, firewall, and QoS settings
- Add live logs + service health panels
