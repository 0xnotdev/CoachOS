'use client';

import { useEffect, useState } from "react";
import "./globals.css";

export default function Home() {
  const [briefing, setBriefing] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Default coach UUID for MVP presentation
  const DEFAULT_COACH_ID = "00000000-0000-0000-0000-000000000000";
  // Fallback to localhost during development, can be configured via environment variables
  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchBriefing = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/api/v1/briefing/today?coach_id=${DEFAULT_COACH_ID}`);
      if (!response.ok) {
        throw new Error("Failed to retrieve synthesized briefing from backend.");
      }
      const data = await response.json();
      setBriefing(data.briefing);
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
            <h1 className="page-title">Morning Briefing</h1>
            <p className="page-subtitle text-muted">Real-time Coach Intelligence Summary</p>
          </div>
          
          <div className="header-actions">
            <button className="btn btn-secondary" onClick={fetchBriefing} disabled={loading}>
              <span style={{ marginRight: '8px' }}>🔄</span> {loading ? "Syncing..." : "Sync Data"}
            </button>
            <div className="avatar">JD</div>
          </div>
        </header>

        <div className="content-grid">
          <section className="card glass-panel animate-fade-in" style={{ animationDelay: '0.1s' }}>
            <h3 className="card-title">📖 Your Daily AI Chief of Staff Briefing</h3>
            
            {loading && (
              <div style={{ color: 'var(--text-secondary)', padding: '2rem 0' }}>
                Fetching real-time business context and generating briefing...
              </div>
            )}

            {error && (
              <div style={{ color: 'var(--danger)', padding: '2rem 0' }}>
                ⚠️ Error: {error}. Make sure backend is running and Supabase/Gemini credentials are configured.
              </div>
            )}

            {!loading && !error && (
              <div className="briefing-box">
                {/* Render the LLM generated briefing cleanly */}
                <p>{briefing}</p>
              </div>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
