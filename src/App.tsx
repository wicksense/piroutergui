import { useState } from 'react';

type NavKey = 'overview' | 'network' | 'wifi' | 'security' | 'system';

const navItems: { key: NavKey; label: string }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'network', label: 'Network' },
  { key: 'wifi', label: 'Wi-Fi' },
  { key: 'security', label: 'Security' },
  { key: 'system', label: 'System' },
];

const systemStats = [
  { label: 'CPU Load', value: '18%' },
  { label: 'Memory', value: '612 MB / 2 GB' },
  { label: 'Uptime', value: '2d 04h 17m' },
  { label: 'WAN IP', value: '100.85.42.12' },
];

const clients = [
  { name: 'Raveen-MBP', ip: '192.168.8.21', type: 'Laptop', status: 'Online' },
  { name: 'Pixel 9', ip: '192.168.8.33', type: 'Phone', status: 'Online' },
  { name: 'Bedroom TV', ip: '192.168.8.70', type: 'TV', status: 'Idle' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<NavKey>('overview');

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
            <span>Node: pi-router.local</span>
          </div>
          <button className="primary">Apply Changes</button>
        </header>

        <section className="cards">
          {systemStats.map((stat) => (
            <article className="card" key={stat.label}>
              <small>{stat.label}</small>
              <strong>{stat.value}</strong>
            </article>
          ))}
        </section>

        <section className="panel">
          <div className="panel-title-row">
            <h3>Connected Clients</h3>
            <button className="ghost">Refresh</button>
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
              {clients.map((client) => (
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
      </main>
    </div>
  );
}
