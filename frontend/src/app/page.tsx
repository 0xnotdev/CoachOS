'use client';

import { useEffect, useState } from "react";
import "./globals.css";

interface AlertItem {
  action_id: string | null;
  client_name: string;
  signal_type: string;
  severity: string;
  action_suggested: string;
}

interface BriefingData {
  briefing: string;
  urgent_alerts: AlertItem[];
  revenue_at_risk: number;
  active_signals_count: number;
  pending_actions_count: number;
}

interface ClientListItem {
  client_id: string;
  person_id: string;
  name: string;
  email: string;
  status: string;
  engagement_score: number;
  compliance_score: number;
  revenue_health: number;
  churn_probability: number;
  days_since_checkin: number;
  days_since_payment: number;
}

type TabType = "briefing" | "clients";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("briefing");
  const [data, setData] = useState<BriefingData | null>(null);
  const [clients, setClients] = useState<ClientListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [actioningId, setActioningId] = useState<string | null>(null);
  
  // Real cryptographic token configuration state
  const [token, setToken] = useState<string>("");

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Load token from localStorage on boot
  useEffect(() => {
    const savedToken = localStorage.getItem("supabase_jwt") || "";
    setToken(savedToken);
  }, []);

  const handleTokenChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setToken(value);
    localStorage.setItem("supabase_jwt", value);
  };

  const getHeaders = () => {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    };
  };

  const fetchBriefing = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/briefing/today`, {
        headers: getHeaders()
      });
      
      if (response.status === 401) {
        throw new Error("Invalid or Expired JWT. Please verify your Supabase JWT secret.");
      }
      if (response.status === 403) {
        throw new Error("Your user is not registered as a coach in the system database.");
      }
      if (!response.ok) {
        throw new Error("Failed to retrieve synthesized briefing from backend.");
      }
      const resData: BriefingData = await response.json();
      setData(resData);
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const fetchClients = async () => {
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/briefing/clients`, {
        headers: getHeaders()
      });
      if (response.status === 401) {
        throw new Error("Invalid or Expired JWT. Please check your token credentials.");
      }
      if (!response.ok) {
        throw new Error("Failed to retrieve clients roster from backend.");
      }
      const clientData: ClientListItem[] = await response.json();
      setClients(clientData);
    } catch (err: any) {
      setError(err.message || "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteAction = async (actionId: string, clientName: string) => {
    setActioningId(actionId);
    try {
      const response = await fetch(`${API_URL}/api/v1/actions/${actionId}`, {
        method: "PATCH",
        headers: getHeaders(),
        body: JSON.stringify({ status: "completed" })
      });

      if (response.status === 401 || response.status === 403) {
        throw new Error("Action execution rejected. Invalid authorization privileges.");
      }
      if (!response.ok) {
        throw new Error("Failed to execute action in backend database.");
      }

      if (data) {
        const updatedAlerts = data.urgent_alerts.filter(a => a.action_id !== actionId);
        setData({
          ...data,
          urgent_alerts: updatedAlerts,
          active_signals_count: Math.max(0, data.active_signals_count - 1),
          pending_actions_count: Math.max(0, data.pending_actions_count - 1)
        });
      }
      alert(`Action successfully recorded: Intervention initiated for ${clientName}`);
    } catch (err: any) {
      alert(`Error executing action: ${err.message}`);
    } finally {
      setActioningId(null);
    }
  };

  // Sync state whenever tab or token changes
  useEffect(() => {
    if (token) {
      if (activeTab === "briefing") {
        fetchBriefing();
      } else {
        fetchClients();
      }
    } else {
      setData(null);
      setClients([]);
    }
  }, [activeTab, token]);

  return (
    <div className="layout animate-fade-in">
      {/* Sidebar */}
      <aside className="sidebar glass-panel">
        <div className="logo-container">
          <div className="logo-icon"></div>
          <h2 className="logo-text text-gradient">CoachOS</h2>
        </div>
        
        <nav className="nav-menu">
          <button onClick={() => setActiveTab("briefing")} className={`nav-item ${activeTab === "briefing" ? "active" : ""}`} style={{ width: '100%', textAlign: 'left' }}>
            <span className="nav-icon">📊</span>
            Daily Briefing
          </button>
          <button onClick={() => setActiveTab("clients")} className={`nav-item ${activeTab === "clients" ? "active" : ""}`} style={{ width: '100%', textAlign: 'left' }}>
            <span className="nav-icon">👥</span>
            Client State
          </button>
          <a href="#" className="nav-item">
            <span className="nav-icon">💰</span>
            Revenue Health
          </a>
          <a href="#" className="nav-item">
            <span className="nav-icon">🎯</span>
            Lead Engine
          </a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header flex-between" style={{ alignItems: 'flex-start' }}>
          <div>
            <h1 className="page-title text-gradient">
              {activeTab === "briefing" ? "Morning Briefing" : "Client State Registry"}
            </h1>
            <p className="page-subtitle text-muted font-sans">
              {activeTab === "briefing" ? "Structured Business Intelligence Hub" : "Active Coach-Client Metrics Tracking"}
            </p>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <input 
                type="password" 
                placeholder="Paste Supabase JWT..." 
                value={token} 
                onChange={handleTokenChange}
                style={{
                  background: 'var(--bg-elevated)',
                  border: '1px solid var(--border-color)',
                  color: 'var(--text-primary)',
                  borderRadius: 'var(--border-radius-sm)',
                  padding: '0.5rem 1rem',
                  width: '240px',
                  fontSize: '0.85rem'
                }}
              />
              <button className="btn btn-secondary" onClick={activeTab === "briefing" ? fetchBriefing : fetchClients} disabled={loading || !token} style={{ padding: '0.5rem 1.2rem', display: 'flex', gap: '0.5rem' }}>
                <span>🔄</span> Sync
              </button>
            </div>
            {token && <span style={{ fontSize: '0.75rem', color: 'var(--success)' }}>✓ JWT credential token cached</span>}
          </div>
        </header>

        {!token && (
          <div className="card glass-panel" style={{ borderLeft: '4px solid var(--warning)', padding: '2.5rem', textAlign: 'center' }}>
            <h3 style={{ color: 'var(--warning)', marginBottom: '0.75rem' }}>🔒 Secure Database Shield Active</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem', maxWidth: '600px', margin: '0 auto 1.5rem' }}>
              This intelligence pipeline requires cryptographic tenant validation. Please paste your Supabase bearer JWT token in the password input above to decrypt client states.
            </p>
          </div>
        )}

        {token && loading && (
          <div style={{ color: 'var(--text-secondary)', padding: '3rem 0', textAlign: 'center' }}>
            <p style={{ fontSize: '1.2rem' }}>Decrypting tenant database context and running metrics calculations...</p>
          </div>
        )}

        {token && error && (
          <div className="card glass-panel" style={{ borderLeft: '4px solid var(--danger)', padding: '2rem' }}>
            <h3 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>⚠️ Connection / Validation Refused</h3>
            <p style={{ color: 'var(--text-secondary)' }}>{error}</p>
          </div>
        )}

        {token && !loading && !error && activeTab === "briefing" && data && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {/* KPI Banner metrics */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>REVENUE AT RISK</span>
                <h2 style={{ fontSize: '2rem', color: data.revenue_at_risk > 0 ? 'var(--danger)' : 'var(--success)' }}>
                  ${data.revenue_at_risk.toFixed(2)}
                </h2>
              </div>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>ACTIVE COMPOSITE ALERTS</span>
                <h2 style={{ fontSize: '2rem', color: data.active_signals_count > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
                  {data.active_signals_count}
                </h2>
              </div>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>PENDING STRATEGIC ACTIONS</span>
                <h2 style={{ fontSize: '2rem' }}>{data.pending_actions_count}</h2>
              </div>
            </div>

            {/* Narrative Briefing Card */}
            <section className="card glass-panel">
              <h3 className="card-title" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <span>📖</span> AI Daily Summary
              </h3>
              <div className="briefing-box" style={{ fontSize: '1.05rem', color: 'var(--text-secondary)' }}>
                {data.briefing}
              </div>
            </section>

            {/* Urgent Alerts Action Graph List */}
            {data.urgent_alerts.length > 0 && (
              <section style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <h3 style={{ fontSize: '1.3rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span>⚠️</span> Action Required: High Priority Interventions
                </h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
                  {data.urgent_alerts.map((alert, index) => (
                    <div key={index} className="card glass-panel flex-between" style={{ borderLeft: `4px solid ${alert.severity === 'high' ? 'var(--danger)' : 'var(--warning)'}`, flexDirection: 'row', padding: '1.5rem' }}>
                      <div>
                        <h4 style={{ fontSize: '1.1rem', marginBottom: '0.25rem' }}>{alert.client_name}</h4>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                          Signal Type: <span style={{ color: 'var(--text-primary)', textTransform: 'capitalize' }}>{alert.signal_type.replace('_', ' ')}</span> | Severity: <span style={{ color: alert.severity === 'high' ? 'var(--danger)' : 'var(--warning)' }}>{alert.severity.toUpperCase()}</span>
                        </p>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
                          Target: <strong style={{ color: 'var(--text-primary)' }}>{alert.action_suggested.replace(/_/g, ' ')}</strong>
                        </span>
                        {alert.action_id && (
                          <button 
                            className="btn btn-primary" 
                            style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} 
                            disabled={actioningId === alert.action_id}
                            onClick={() => handleExecuteAction(alert.action_id!, alert.client_name)}
                          >
                            {actioningId === alert.action_id ? "Executing..." : "Execute Action"}
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {token && !loading && !error && activeTab === "clients" && (
          <section className="card glass-panel">
            <h3 className="card-title" style={{ marginBottom: '1.5rem' }}>Client Roster & Predictive Scores</h3>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-color)', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                    <th style={{ padding: '1rem' }}>NAME</th>
                    <th style={{ padding: '1rem' }}>EMAIL</th>
                    <th style={{ padding: '1rem' }}>REVENUE HEALTH</th>
                    <th style={{ padding: '1rem' }}>COMPLIANCE</th>
                    <th style={{ padding: '1rem' }}>ENGAGEMENT</th>
                    <th style={{ padding: '1rem' }}>CHURN RISK</th>
                    <th style={{ padding: '1rem' }}>DAYS SILENT</th>
                  </tr>
                </thead>
                <tbody>
                  {clients.map((client) => (
                    <tr key={client.client_id} style={{ borderBottom: '1px solid var(--border-color)', fontSize: '0.95rem' }}>
                      <td style={{ padding: '1rem', fontWeight: 600 }}>{client.name}</td>
                      <td style={{ padding: '1rem', color: 'var(--text-secondary)' }}>{client.email}</td>
                      <td style={{ padding: '1rem' }}>
                        <span style={{ color: client.revenue_health > 70 ? 'var(--success)' : client.revenue_health > 40 ? 'var(--warning)' : 'var(--danger)' }}>
                          {client.revenue_health}%
                        </span>
                      </td>
                      <td style={{ padding: '1rem' }}>
                        <span style={{ color: client.compliance_score > 70 ? 'var(--success)' : client.compliance_score > 40 ? 'var(--warning)' : 'var(--danger)' }}>
                          {client.compliance_score}%
                        </span>
                      </td>
                      <td style={{ padding: '1rem' }}>
                        <span style={{ color: client.engagement_score > 70 ? 'var(--success)' : client.engagement_score > 40 ? 'var(--warning)' : 'var(--danger)' }}>
                          {client.engagement_score}%
                        </span>
                      </td>
                      <td style={{ padding: '1rem', fontWeight: 600 }}>
                        <span style={{ color: client.churn_probability > 0.6 ? 'var(--danger)' : client.churn_probability > 0.3 ? 'var(--warning)' : 'var(--success)' }}>
                          {(client.churn_probability * 100).toFixed(0)}%
                        </span>
                      </td>
                      <td style={{ padding: '1rem', color: client.days_since_checkin > 7 ? 'var(--danger)' : 'var(--text-secondary)' }}>
                        {client.days_since_checkin} days
                      </td>
                    </tr>
                  ))}
                  {clients.length === 0 && (
                    <tr>
                      <td colSpan={7} style={{ padding: '2rem', textAlign: 'center', color: 'var(--text-muted)' }}>
                        No clients registered under this account.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
