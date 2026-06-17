'use client';

import { useEffect, useState } from "react";
import "./globals.css";

interface AlertItem {
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

export default function Home() {
  const [data, setData] = useState<BriefingData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Default coach UUID for MVP presentation
  const DEFAULT_COACH_ID = "00000000-0000-0000-0000-000000000000";
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchBriefing = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/briefing/today?coach_id=${DEFAULT_COACH_ID}`);
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

  useEffect(() => {
    fetchBriefing();
  }, []);

  return (
    <div className="layout animate-fade-in">
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
            Client State
          </a>
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
        <header className="header flex-between">
          <div>
            <h1 className="page-title text-gradient">Morning Briefing</h1>
            <p className="page-subtitle text-muted font-sans">Structured Business Intelligence Hub</p>
          </div>
          
          <div className="header-actions">
            <button className="btn btn-secondary" onClick={fetchBriefing} disabled={loading} style={{ padding: '0.5rem 1.2rem', display: 'flex', gap: '0.5rem' }}>
              <span>🔄</span> {loading ? "Syncing..." : "Sync Pipeline"}
            </button>
            <div className="avatar">JD</div>
          </div>
        </header>

        {loading && (
          <div style={{ color: 'var(--text-secondary)', padding: '3rem 0', textAlign: 'center' }}>
            <p style={{ fontSize: '1.2rem' }}>Recalculating feature store time series and building AI briefing...</p>
          </div>
        )}

        {error && (
          <div className="card glass-panel" style={{ borderLeft: '4px solid var(--danger)', padding: '2rem' }}>
            <h3 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>⚠️ Pipeline Connection Error</h3>
            <p style={{ color: 'var(--text-secondary)' }}>{error}</p>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', marginTop: '1rem' }}>
              Ensure your FastAPI backend is running locally or deployed, and credentials for Supabase and Gemini are set in settings.
            </p>
          </div>
        )}

        {!loading && !error && data && (
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
                        <button className="btn btn-primary" style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} onClick={() => alert('Action linked to client lifecycle updates.')}>
                          Execute Action
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
