import express from 'express';
import cors from 'cors';
import os from 'os';
import { execSync } from 'node:child_process';

const app = express();
const port = process.env.PORT || 8080;

app.use(cors());
app.use(express.json());

function safeExec(command) {
  try {
    return execSync(command, { stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim();
  } catch {
    return 'N/A';
  }
}

function getWanIp() {
  const ip = safeExec('curl -s --max-time 2 https://ifconfig.me');
  return ip || 'N/A';
}

function getServiceStatus(serviceName) {
  const status = safeExec(`systemctl is-active ${serviceName}`);
  if (!status || status === 'N/A') return 'unknown';
  return status;
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
    clients: [
      { name: 'Raveen-MBP', ip: '192.168.8.21', type: 'Laptop', status: 'Online' },
      { name: 'Pixel 9', ip: '192.168.8.33', type: 'Phone', status: 'Online' },
      { name: 'Bedroom TV', ip: '192.168.8.70', type: 'TV', status: 'Idle' },
    ],
  };

  res.json(payload);
});

app.listen(port, () => {
  console.log(`PiRouterGUI API listening on :${port}`);
});
