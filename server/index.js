import express from 'express';
import cors from 'cors';
import os from 'os';
import { execSync } from 'node:child_process';

const app = express();
const port = process.env.PORT || 8080;

app.use(cors());
app.use(express.json());

function execText(command) {
  try {
    return execSync(command, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return '';
  }
}

function getWanIp() {
  return execText('curl -s --max-time 2 https://ifconfig.me') || 'N/A';
}

function getServiceStatus(serviceName) {
  return execText(`systemctl is-active ${serviceName}`) || 'unknown';
}

function readDhcpLeases() {
  const leasesText = execText('cat /var/lib/misc/dnsmasq.leases');
  if (!leasesText) return new Map();

  const leasesMap = new Map();

  for (const line of leasesText.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    // dnsmasq format: <expiry> <mac> <ip> <hostname> <client-id>
    const parts = trimmed.split(/\s+/);
    if (parts.length < 4) continue;

    const [, mac, ip, hostname] = parts;
    leasesMap.set(ip, {
      mac: mac?.toLowerCase() ?? '',
      hostname: hostname && hostname !== '*' ? hostname : null,
    });
  }

  return leasesMap;
}

function inferDeviceType(name = '') {
  const value = name.toLowerCase();
  if (!value) return 'Unknown';
  if (value.includes('iphone') || value.includes('pixel') || value.includes('android')) return 'Phone';
  if (value.includes('ipad') || value.includes('tablet')) return 'Tablet';
  if (value.includes('macbook') || value.includes('laptop') || value.includes('thinkpad')) return 'Laptop';
  if (value.includes('tv') || value.includes('chromecast') || value.includes('roku')) return 'TV';
  return 'Device';
}

function discoverClients() {
  const ipNeighText = execText('ip -4 neigh show');
  if (!ipNeighText) return [];

  const leases = readDhcpLeases();
  const clients = [];

  for (const line of ipNeighText.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    // Example: 192.168.8.21 dev wlan0 lladdr 12:34:56:78:9a:bc REACHABLE
    const parts = trimmed.split(/\s+/);
    const ip = parts[0];
    if (!ip || ip === 'N/A') continue;

    const state = parts.at(-1) || 'UNKNOWN';
    const macIdx = parts.indexOf('lladdr');
    const mac = macIdx >= 0 && parts[macIdx + 1] ? parts[macIdx + 1].toLowerCase() : '';
    const devIdx = parts.indexOf('dev');
    const iface = devIdx >= 0 && parts[devIdx + 1] ? parts[devIdx + 1] : 'unknown';

    const lease = leases.get(ip);
    const hostname = lease?.hostname;

    if (state === 'FAILED' || state === 'INCOMPLETE') continue;

    clients.push({
      name: hostname || `client-${ip.split('.').at(-1)}`,
      ip,
      mac: mac || lease?.mac || 'N/A',
      iface,
      type: inferDeviceType(hostname || ''),
      status: state === 'STALE' ? 'Idle' : 'Online',
    });
  }

  // De-duplicate by IP
  const uniqueByIp = new Map();
  for (const client of clients) uniqueByIp.set(client.ip, client);

  return Array.from(uniqueByIp.values()).sort((a, b) => a.ip.localeCompare(b.ip, undefined, { numeric: true }));
}

app.get('/api/health', (_req, res) => {
  res.json({ ok: true, service: 'piroutergui-api' });
});

app.get('/api/overview', (_req, res) => {
  const cpus = os.cpus();
  const load = os.loadavg()[0];
  const normalizedLoad = cpus.length ? (load / cpus.length) * 100 : 0;
  const totalMemGb = os.totalmem() / 1024 / 1024 / 1024;
  const usedMemGb = totalMemGb - os.freemem() / 1024 / 1024 / 1024;
  const clients = discoverClients();

  const payload = {
    node: os.hostname(),
    uptimeSec: os.uptime(),
    stats: {
      cpuLoadPct: Math.max(0, Math.min(100, Number(normalizedLoad.toFixed(1)))),
      memUsedGb: Number(usedMemGb.toFixed(2)),
      memTotalGb: Number(totalMemGb.toFixed(2)),
      wanIp: getWanIp(),
    },
    services: {
      hostapd: getServiceStatus('hostapd'),
      dnsmasq: getServiceStatus('dnsmasq'),
      nftables: getServiceStatus('nftables'),
    },
    clients,
  };

  res.json(payload);
});

app.listen(port, () => {
  console.log(`PiRouterGUI API listening on :${port}`);
});
