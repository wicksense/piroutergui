import { useEffect, useMemo, useState } from 'react';

type NavKey = 'overview' | 'network' | 'wifi' | 'security' | 'system';

type Client = { name: string; ip: string; type: string; status: string };

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
          </div>
          <button className="primary" onClick={() => void fetchOverview()}>
            {loading ? 'Refreshing...' : 'Refresh Data'}
          </button>
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
                <th>Type</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.clients ?? []).map((client) => (
                <tr key={client.ip}>
                  <td>{client.name}</td>
                  <td>{client.ip}</td>
                  <td>{client.type}</td>
                  <td>
                    <span className={client.status === 'Online' ? 'status online' : 'status'}>
                      {client.status}
                    </span>
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
