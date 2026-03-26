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
npm run dev
```

Then open http://localhost:5173

## Next steps

- Add API layer for `hostapd`, `dnsmasq`, `nftables` and system metrics
- Build auth/session handling
- Add forms for WAN/LAN, DHCP, Wi-Fi, firewall, and QoS settings
- Add live logs + service health panels
