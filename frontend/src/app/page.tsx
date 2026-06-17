import Image from "next/image";
import "./globals.css";

export const metadata = {
  title: "CoachOS | AI Chief of Staff",
  description: "The intelligence layer for modern coaching businesses",
};

export default function Home() {
  return (
    <div className="layout">
      {/* Sidebar */}
      <aside className="sidebar glass-panel">
        <div className="logo-container">
          <div className="logo-icon"></div>
          <h2 className="logo-text text-gradient">CoachOS</h2>
        </div>
        
        <nav className="nav-menu">
          <a href="#" className="nav-item active">
            <span className="nav-icon">📊</span>
            Daily Briefing
          </a>
          <a href="#" className="nav-item">
            <span className="nav-icon">👥</span>
            Intelligence Graph
          </a>
          <a href="#" className="nav-item">
            <span className="nav-icon">💰</span>
            Revenue Intelligence
          </a>
          <a href="#" className="nav-item">
            <span className="nav-icon">🎯</span>
            Lead Engine
          </a>
          <a href="#" className="nav-item">
            <span className="nav-icon">⚡</span>
            Integrations
          </a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header flex-between">
          <div>
            <h1 className="page-title">Morning Briefing</h1>
            <p className="page-subtitle text-muted">Tuesday, June 17, 2026</p>
          </div>
          
          <div className="header-actions">
            <button className="btn btn-secondary">
              <span style={{ marginRight: '8px' }}>🔄</span> Sync Data
            </button>
            <div className="avatar">JD</div>
          </div>
        </header>

        <div className="content-grid">
          {/* Urgent Alerts */}
          <section className="card glass-panel alert-card animate-fade-in" style={{ animationDelay: '0.1s' }}>
            <div className="card-header flex-between">
              <h3 className="card-title" style={{ color: 'var(--danger)' }}>🔴 Urgent Items (2)</h3>
            </div>
            <div className="alert-list">
              <div className="alert-item">
                <div className="alert-dot danger"></div>
                <div className="alert-content">
                  <p className="alert-text"><strong>Sarah M.</strong> — payment failed 2x, engagement down 40%. Likely to churn.</p>
                  <div className="alert-actions">
                    <button className="btn-sm btn-primary">Intervene</button>
                    <button className="btn-sm btn-secondary">Dismiss</button>
                  </div>
                </div>
              </div>
              <div className="alert-item">
                <div className="alert-dot warning"></div>
                <div className="alert-content">
                  <p className="alert-text"><strong>Jake R.</strong> — hasn't checked in for 8 days. Last message sentiment: negative.</p>
                  <div className="alert-actions">
                    <button className="btn-sm btn-primary">Message</button>
                    <button className="btn-sm btn-secondary">Dismiss</button>
                  </div>
                </div>
              </div>
            </div>
          </section>

          {/* Revenue */}
          <section className="card glass-panel animate-fade-in" style={{ animationDelay: '0.2s' }}>
            <div className="card-header">
              <h3 className="card-title">💰 Revenue Intelligence</h3>
              <p className="metric-primary">$12,400 <span className="metric-trend positive">↑ 4.2%</span></p>
            </div>
            <ul className="insight-list">
              <li>3 renewals due this week ($1,800)</li>
              <li>1 expansion opportunity identified (Mike T.)</li>
              <li className="text-danger">$400 at risk from failed payments</li>
            </ul>
          </section>

          {/* Leads */}
          <section className="card glass-panel animate-fade-in" style={{ animationDelay: '0.3s' }}>
            <div className="card-header">
              <h3 className="card-title">🎯 Lead Engine</h3>
              <p className="metric-primary">4 <span className="metric-subtitle">Active Leads</span></p>
            </div>
            <ul className="insight-list">
              <li>2 high-intent leads awaiting follow-up</li>
              <li>1 consultation booked for tomorrow</li>
            </ul>
          </section>

          {/* Wins */}
          <section className="card glass-panel animate-fade-in" style={{ animationDelay: '0.4s' }}>
            <div className="card-header">
              <h3 className="card-title">📈 System Wins</h3>
            </div>
            <ul className="insight-list">
              <li>Client retention stabilized at 94%</li>
              <li>Avg transformation velocity increased by 12%</li>
            </ul>
          </section>
        </div>
      </main>

      <style dangerouslySetInnerHTML={{__html: `
        .layout {
          display: flex;
          min-height: 100vh;
        }

        .sidebar {
          width: 280px;
          border-right: 1px solid var(--border-color);
          border-top: none;
          border-bottom: none;
          border-left: none;
          border-radius: 0;
          padding: 2rem 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 3rem;
        }

        .logo-container {
          display: flex;
          align-items: center;
          gap: 1rem;
        }

        .logo-icon {
          width: 32px;
          height: 32px;
          background: linear-gradient(135deg, var(--accent-primary), var(--info));
          border-radius: 8px;
          box-shadow: var(--shadow-glow);
        }

        .nav-menu {
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .nav-item {
          display: flex;
          align-items: center;
          gap: 1rem;
          padding: 0.75rem 1rem;
          border-radius: var(--border-radius-md);
          color: var(--text-secondary);
          transition: all 0.2s;
          font-weight: 500;
        }

        .nav-item:hover, .nav-item.active {
          background: var(--bg-elevated);
          color: var(--text-primary);
        }

        .nav-item.active {
          border-left: 3px solid var(--accent-primary);
          background: var(--accent-light);
        }

        .main-content {
          flex: 1;
          padding: 3rem 4rem;
          overflow-y: auto;
        }

        .header {
          margin-bottom: 3rem;
        }

        .page-title {
          font-size: 2.5rem;
          margin-bottom: 0.5rem;
        }

        .avatar {
          width: 44px;
          height: 44px;
          border-radius: 50%;
          background: var(--bg-elevated);
          border: 2px solid var(--border-color);
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          margin-left: 1rem;
        }

        .header-actions {
          display: flex;
          align-items: center;
        }

        .content-grid {
          display: grid;
          grid-template-columns: repeat(2, 1fr);
          gap: 1.5rem;
        }

        .card {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .alert-card {
          grid-column: 1 / -1;
          border-left: 4px solid var(--danger);
        }

        .card-header {
          margin-bottom: 0.5rem;
        }

        .metric-primary {
          font-size: 2.5rem;
          font-family: var(--font-display);
          font-weight: 700;
          margin-top: 0.5rem;
        }

        .metric-trend {
          font-size: 1rem;
          font-weight: 500;
          vertical-align: middle;
          margin-left: 0.5rem;
          padding: 0.25rem 0.75rem;
          border-radius: 20px;
          background: var(--success-bg);
          color: var(--success);
        }

        .metric-subtitle {
          font-size: 1rem;
          color: var(--text-muted);
          font-weight: 500;
        }

        .insight-list {
          list-style: none;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .insight-list li {
          position: relative;
          padding-left: 1.5rem;
          color: var(--text-secondary);
        }

        .insight-list li::before {
          content: '•';
          position: absolute;
          left: 0;
          color: var(--accent-primary);
          font-weight: bold;
        }

        .text-danger {
          color: #fca5a5 !important;
        }

        .alert-list {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .alert-item {
          display: flex;
          gap: 1rem;
          padding: 1rem;
          background: rgba(0,0,0,0.2);
          border-radius: var(--border-radius-sm);
        }

        .alert-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          margin-top: 6px;
          flex-shrink: 0;
        }
        
        .alert-dot.danger { background: var(--danger); box-shadow: 0 0 10px var(--danger); }
        .alert-dot.warning { background: var(--warning); box-shadow: 0 0 10px var(--warning); }

        .alert-content {
          flex: 1;
        }

        .alert-actions {
          margin-top: 0.75rem;
          display: flex;
          gap: 0.5rem;
        }

        .btn-sm {
          padding: 0.4rem 1rem;
          font-size: 0.875rem;
          border-radius: var(--border-radius-sm);
          font-weight: 600;
          transition: all 0.2s;
        }
      `}} />
    </div>
  );
}
