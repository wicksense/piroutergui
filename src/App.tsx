import { useEffect, useMemo, useState } from 'react';

type NavKey = 'overview' | 'network' | 'wifi' | 'security' | 'system';

type Client = {
  name: string;
  ip: string;
  mac: string;
  iface: string;
  type: string;
  status: string;
  blocked: boolean;
  staticLeaseIp: string | null;
};

type OverviewData = {
  node: string;
  uptimeSec: number;
  stats: {
    cpuLoadPct: number;
    memUsedGb: number;
    memTotalGb: number;
    wanIp: string;
  };
  services: {
    hostapd: string;
    dnsmasq: string;
    nftables: string;
  };
  clients: Client[];
};

const navItems: { key: NavKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'network', label: 'Network' },
  { key: 'wifi', label: 'Wi-Fi' },
  { key: 'security', label: 'Security' },
  { key: 'system', label: 'System' },
];

function formatUptime(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days}d ${hours}h ${minutes}m`;
}

export default function App() {
  const [activeTab, setActiveTab] = useState<NavKey>('overview');
  const [data, setData] = useState<OverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionBusyMac, setActionBusyMac] = useState<string | null>(null);
  const [applyMessage, setApplyMessage] = useState<string>('');

  const fetchOverview = async () => {
    try {
      setLoading(true);
      const response = await fetch('http://localhost:8080/api/overview');
      const json = (await response.json()) as OverviewData;
      setData(json);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchOverview();
  }, []);

  const runClientAction = async (mac: string, action: 'block' | 'unblock') => {
    if (mac === 'N/A') return;
    setActionBusyMac(mac);
    try {
      await fetch(`http://localhost:8080/api/clients/${encodeURIComponent(mac)}/${action}`, {
        method: 'POST',
      });
      await fetchOverview();
    } finally {
      setActionBusyMac(null);
    }
  };

  const applyManagedConfig = async () => {
    setApplyMessage('Applying managed config...');
    try {
      const res = await fetch('http://localhost:8080/api/system/apply', { method: 'POST' });
      const json = (await res.json()) as { applyResult?: { dnsmasq?: { error?: string | null }; nftables?: { error?: string | null } } };
      const dnsErr = json.applyResult?.dnsmasq?.error;
      const nftErr = json.applyResult?.nftables?.error;
      if (!dnsErr && !nftErr) {
        setApplyMessage('Managed config applied successfully.');
      } else {
        setApplyMessage(`Applied with warnings: ${dnsErr ?? 'dnsmasq ok'} | ${nftErr ?? 'nftables ok'}`);
      }
    } catch {
      setApplyMessage('Apply failed: unable to reach API.');
    }
  };

  const setStaticLease = async (mac: string) => {
    if (mac === 'N/A') return;
    const ip = window.prompt('Set static lease IP (example: 192.168.8.50):');
    if (!ip) return;

    setActionBusyMac(mac);
    try {
      await fetch(`http://localhost:8080/api/clients/${encodeURIComponent(mac)}/static-lease`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip }),
      });
      await fetchOverview();
    } finally {
      setActionBusyMac(null);
    }
  };

  const clearStaticLease = async (mac: string) => {
    if (mac === 'N/A') return;
    setActionBusyMac(mac);
    try {
      await fetch(`http://localhost:8080/api/clients/${encodeURIComponent(mac)}/static-lease`, {
        method: 'DELETE',
      });
      await fetchOverview();
    } finally {
      setActionBusyMac(null);
    }
  };

  const statCards = useMemo(() => {
    if (!data) {
      return [
        { label: 'CPU Load', value: '--' },
        { label: 'Memory', value: '--' },
        { label: 'Uptime', value: '--' },
        { label: 'WAN IP', value: '--' },
      ];
    }

    return [
      { label: 'CPU Load', value: `${data.stats.cpuLoadPct}%` },
      { label: 'Memory', value: `${data.stats.memUsedGb} GB / ${data.stats.memTotalGb} GB` },
      { label: 'Uptime', value: formatUptime(data.uptimeSec) },
      { label: 'WAN IP', value: data.stats.wanIp },
    ];
  }, [data]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div>
          <h1>PiRouterGUI</h1>
          <p>Raspberry Pi Router Control Panel</p>
        </div>
        <nav>
          {navItems.map((item) => (
            <button
              key={item.key}
              className={item.key === activeTab ? 'nav-btn active' : 'nav-btn'}
              onClick={() => setActiveTab(item.key)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="content">
        <header className="header">
          <div>
            <h2>{navItems.find((item) => item.key === activeTab)?.label}</h2>
            <span>Node: {data?.node ?? 'pi-router.local'}</span>
            {applyMessage && <div className="apply-msg">{applyMessage}</div>}
          </div>
          <div className="header-actions">
            <button className="ghost" onClick={() => void applyManagedConfig()}>
              Apply Router Config
            </button>
            <button className="primary" onClick={() => void fetchOverview()}>
              {loading ? 'Refreshing...' : 'Refresh Data'}
            </button>
          </div>
        </header>

        <section className="cards">
          {statCards.map((stat) => (
            <article className="card" key={stat.label}>
              <small>{stat.label}</small>
              <strong>{stat.value}</strong>
            </article>
          ))}
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <h3>Connected Clients</h3>
            <button className="ghost" onClick={() => void fetchOverview()}>
              Refresh
            </button>
          </div>
          <table>
            <thead>
              <tr>
                <th>Device</th>
                <th>IP</th>
                <th>MAC</th>
                <th>Type</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {(data?.clients ?? []).map((client) => (
                <tr key={client.ip}>
                  <td>{client.name}</td>
                  <td>{client.ip}</td>
                  <td>{client.mac}</td>
                  <td>{client.type}</td>
                  <td>
                    <span className={client.status === 'Online' ? 'status online' : 'status'}>
                      {client.status}
                    </span>
                  </td>
                  <td>
                    <div className="action-row">
                      <button
                        className="mini-btn"
                        disabled={actionBusyMac === client.mac}
                        onClick={() => void runClientAction(client.mac, client.blocked ? 'unblock' : 'block')}
                      >
                        {client.blocked ? 'Unblock' : 'Block'}
                      </button>
                      <button className="mini-btn" disabled={actionBusyMac === client.mac} onClick={() => void setStaticLease(client.mac)}>
                        {client.staticLeaseIp ? `Static ${client.staticLeaseIp}` : 'Set Static'}
                      </button>
                      {client.staticLeaseIp && (
                        <button
                          className="mini-btn danger"
                          disabled={actionBusyMac === client.mac}
                          onClick={() => void clearStaticLease(client.mac)}
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <section className="panel">
          <h3>Core Services</h3>
          <div className="service-grid">
            {Object.entries(data?.services ?? {}).map(([name, status]) => (
              <div className="service-item" key={name}>
                <span>{name}</span>
                <span className={status === 'active' ? 'status online' : 'status'}>{status}</span>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
