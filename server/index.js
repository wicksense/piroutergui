import express from 'express';
import cors from 'cors';
import os from 'os';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execSync } from 'node:child_process';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const stateDir = path.join(__dirname, 'state');
const backupDir = path.join(stateDir, 'backups');
const statePath = path.join(stateDir, 'client-actions.json');

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

function loadState() {
  try {
    const raw = fs.readFileSync(statePath, 'utf8');
    const parsed = JSON.parse(raw);
    return {
      blockedMacs: Array.isArray(parsed.blockedMacs) ? parsed.blockedMacs : [],
      staticLeases: typeof parsed.staticLeases === 'object' && parsed.staticLeases ? parsed.staticLeases : {},
    };
  } catch {
    return { blockedMacs: [], staticLeases: {} };
  }
}

function makeTimestamp() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function backupFileIfExists(filePath, prefix) {
  if (!fs.existsSync(filePath)) return null;

  fs.mkdirSync(backupDir, { recursive: true });
  const backupPath = path.join(backupDir, `${prefix}-${makeTimestamp()}.bak`);
  fs.copyFileSync(filePath, backupPath);
  return backupPath;
}

function saveState(state) {
  fs.mkdirSync(stateDir, { recursive: true });
  const backupPath = backupFileIfExists(statePath, 'client-actions');
  fs.writeFileSync(statePath, JSON.stringify(state, null, 2));
  return backupPath;
}

function readDhcpLeases() {
  const leasesText = execText('cat /var/lib/misc/dnsmasq.leases');
  if (!leasesText) return new Map();

  const leasesMap = new Map();

  for (const line of leasesText.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
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
  const state = loadState();
  const blocked = new Set(state.blockedMacs.map((x) => String(x).toLowerCase()));
  const clients = [];

  for (const line of ipNeighText.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;

    const parts = trimmed.split(/\s+/);
    const ip = parts[0];
    if (!ip || ip === 'N/A') continue;

    const stateLabel = parts.at(-1) || 'UNKNOWN';
    const macIdx = parts.indexOf('lladdr');
    const mac = macIdx >= 0 && parts[macIdx + 1] ? parts[macIdx + 1].toLowerCase() : '';
    const devIdx = parts.indexOf('dev');
    const iface = devIdx >= 0 && parts[devIdx + 1] ? parts[devIdx + 1] : 'unknown';

    const lease = leases.get(ip);
    const hostname = lease?.hostname;

    if (stateLabel === 'FAILED' || stateLabel === 'INCOMPLETE') continue;

    const resolvedMac = mac || lease?.mac || 'N/A';

    clients.push({
      name: hostname || `client-${ip.split('.').at(-1)}`,
      ip,
      mac: resolvedMac,
      iface,
      type: inferDeviceType(hostname || ''),
      status: stateLabel === 'STALE' ? 'Idle' : 'Online',
      blocked: resolvedMac !== 'N/A' ? blocked.has(resolvedMac.toLowerCase()) : false,
      staticLeaseIp: resolvedMac !== 'N/A' ? state.staticLeases[resolvedMac.toLowerCase()] || null : null,
    });
  }

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

  res.json({
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
  });
});

app.post('/api/clients/:mac/block', (req, res) => {
  const mac = String(req.params.mac || '').toLowerCase();
  if (!mac) return res.status(400).json({ error: 'Invalid mac' });

  const state = loadState();
  if (!state.blockedMacs.includes(mac)) state.blockedMacs.push(mac);
  const backupPath = saveState(state);
  return res.json({ ok: true, mac, blocked: true, backupPath });
});

app.post('/api/clients/:mac/unblock', (req, res) => {
  const mac = String(req.params.mac || '').toLowerCase();
  if (!mac) return res.status(400).json({ error: 'Invalid mac' });

  const state = loadState();
  state.blockedMacs = state.blockedMacs.filter((m) => m !== mac);
  const backupPath = saveState(state);
  return res.json({ ok: true, mac, blocked: false, backupPath });
});

app.post('/api/clients/:mac/static-lease', (req, res) => {
  const mac = String(req.params.mac || '').toLowerCase();
  const ip = String(req.body?.ip || '').trim();
  if (!mac || !ip) return res.status(400).json({ error: 'Invalid mac or ip' });

  const state = loadState();
  state.staticLeases[mac] = ip;
  const backupPath = saveState(state);
  return res.json({ ok: true, mac, ip, backupPath });
});

app.delete('/api/clients/:mac/static-lease', (req, res) => {
  const mac = String(req.params.mac || '').toLowerCase();
  if (!mac) return res.status(400).json({ error: 'Invalid mac' });

  const state = loadState();
  delete state.staticLeases[mac];
  const backupPath = saveState(state);
  return res.json({ ok: true, mac, backupPath });
});

app.listen(port, () => {
  console.log(`PiRouterGUI API listening on :${port}`);
});
