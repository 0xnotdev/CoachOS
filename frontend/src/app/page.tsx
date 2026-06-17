'use client';

import { useEffect, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { supabase } from "./supabase";
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

type TabType = "briefing" | "clients" | "onboard";

export default function Home() {
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabType>("briefing");
  const [token, setToken] = useState<string>("");
  
  // Custom manual auth input states
  const [showManualAuth, setShowManualAuth] = useState<boolean>(false);
  const [manualToken, setManualToken] = useState<string>("");

  // Supabase Auth input states
  const [authEmail, setAuthEmail] = useState<string>("");
  const [authPassword, setAuthPassword] = useState<string>("");
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authLoading, setAuthLoading] = useState<boolean>(false);

  // Onboarding registration input states
  const [regName, setRegName] = useState<string>("");
  const [regEmail, setRegEmail] = useState<string>("");
  const [stripeAcct, setStripeAcct] = useState<string>("");
  const [webhookSecret, setWebhookSecret] = useState<string>("");
  const [onboardResult, setOnboardResult] = useState<any | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // 1. Initialize Authentication session tracking
  useEffect(() => {
    // Load local token if present
    const savedToken = localStorage.getItem("supabase_jwt") || "";
    if (savedToken) {
      setToken(savedToken);
      setManualToken(savedToken);
    }

    if (!supabase) {
      setShowManualAuth(true);
      return;
    }

    // Get initial session
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (session) {
        const accessToken = session.access_token;
        setToken(accessToken);
        localStorage.setItem("supabase_jwt", accessToken);
        setShowManualAuth(false);
      } else {
        setShowManualAuth(true);
      }
    });

    // Listen for authentication changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (session) {
        const accessToken = session.access_token;
        setToken(accessToken);
        localStorage.setItem("supabase_jwt", accessToken);
        setShowManualAuth(false);
      } else {
        setToken("");
        localStorage.removeItem("supabase_jwt");
        setShowManualAuth(true);
      }
    });

    return () => subscription.unsubscribe();
  }, []);

  const getHeaders = () => {
    return {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`
    };
  };

  // 2. React Query: Fetch Morning Briefing
  const { 
    data: briefingData, 
    isLoading: isBriefingLoading, 
    error: briefingError, 
    refetch: refetchBriefing 
  } = useQuery<BriefingData>({
    queryKey: ["briefing", token],
    queryFn: async () => {
      const response = await fetch(`${API_URL}/api/v1/briefing/today`, {
        headers: getHeaders()
      });
      if (response.status === 401) {
        throw new Error("Invalid or Expired JWT credentials.");
      }
      if (response.status === 403) {
        throw new Error("Your user profile is not registered as a coach.");
      }
      if (!response.ok) {
        throw new Error("Failed to fetch today's briefing.");
      }
      return response.json();
    },
    enabled: !!token && activeTab === "briefing",
  });

  // 3. React Query: Fetch Client List
  const { 
    data: clientsData = [], 
    isLoading: isClientsLoading, 
    error: clientsError, 
    refetch: refetchClients 
  } = useQuery<ClientListItem[]>({
    queryKey: ["clients", token],
    queryFn: async () => {
      const response = await fetch(`${API_URL}/api/v1/briefing/clients`, {
        headers: getHeaders()
      });
      if (response.status === 401) {
        throw new Error("Invalid or Expired JWT credentials.");
      }
      if (response.status === 403) {
        throw new Error("Your user profile is not registered as a coach.");
      }
      if (!response.ok) {
        throw new Error("Failed to fetch client registry.");
      }
      return response.json();
    },
    enabled: !!token && activeTab === "clients",
  });

  // 4. React Query Mutation: Execute / Dismiss Alerts
  const actionMutation = useMutation({
    mutationFn: async ({ actionId, status }: { actionId: string, status: "completed" | "rejected" }) => {
      const response = await fetch(`${API_URL}/api/v1/actions/${actionId}`, {
        method: "PATCH",
        headers: getHeaders(),
        body: JSON.stringify({ status })
      });
      if (!response.ok) {
        throw new Error("Failed to update status on the action.");
      }
      return response.json();
    },
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: ["briefing", token] });
      alert(`Action successfully ${variables.status === 'completed' ? 'executed' : 'dismissed'}.`);
    },
    onError: (err: any) => {
      alert(`Action execution failed: ${err.message}`);
    }
  });

  // 5. React Query Mutation: Onboard Coach Profile
  const onboardMutation = useMutation({
    mutationFn: async (payload: { name: string, email: string, stripe_connected_account_id: string | null, webhook_secret: string | null }) => {
      const response = await fetch(`${API_URL}/api/v1/coaches/register`, {
        method: "POST",
        headers: getHeaders(),
        body: JSON.stringify({
          name: payload.name,
          email: payload.email,
          stripe_connected_account_id: payload.stripe_connected_account_id
        })
      });

      if (!response.ok) {
        const errPayload = await response.json();
        throw new Error(errPayload.detail || "Registration request failed.");
      }

      const res = await response.json();
      
      if (payload.webhook_secret) {
        const secretResponse = await fetch(`${API_URL}/api/v1/coaches/integrations/stripe`, {
          method: "PATCH",
          headers: getHeaders(),
          body: JSON.stringify({
            stripe_webhook_secret: payload.webhook_secret
          })
        });
        if (!secretResponse.ok) {
          const secretErr = await secretResponse.json();
          throw new Error(secretErr.detail || "Failed to secure webhook signature credentials.");
        }
      }

      return res;
    },
    onSuccess: (res) => {
      setOnboardResult(res);
      alert("Registration completed successfully!");
      queryClient.invalidateQueries({ queryKey: ["briefing", token] });
      queryClient.invalidateQueries({ queryKey: ["clients", token] });
      setActiveTab("briefing");
    },
    onError: (err: any) => {
      alert(`Onboarding setup failed: ${err.message}`);
    }
  });

  // Handle manual token submission
  const handleManualTokenSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!manualToken.trim()) return;
    setToken(manualToken.trim());
    localStorage.setItem("supabase_jwt", manualToken.trim());
    alert("Token configured successfully.");
  };

  // Handle Supabase Auth sign-in or sign-up
  const handleSupabaseAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!supabase) return;
    setAuthLoading(true);
    try {
      if (authMode === "login") {
        const { data, error } = await supabase.auth.signInWithPassword({
          email: authEmail,
          password: authPassword
        });
        if (error) throw error;
        if (data.session) {
          setToken(data.session.access_token);
          localStorage.setItem("supabase_jwt", data.session.access_token);
          alert("Logged in successfully!");
        }
      } else {
        const { data, error } = await supabase.auth.signUp({
          email: authEmail,
          password: authPassword
        });
        if (error) throw error;
        alert("Check your email for confirmation link!");
      }
    } catch (err: any) {
      alert(`Auth failed: ${err.message}`);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = async () => {
    if (supabase) {
      await supabase.auth.signOut();
    }
    setToken("");
    setManualToken("");
    localStorage.removeItem("supabase_jwt");
    setShowManualAuth(true);
    alert("Logged out successfully.");
  };

  const handleRegisterFormSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      alert("You must be authenticated before registering.");
      return;
    }
    onboardMutation.mutate({
      name: regName,
      email: regEmail,
      stripe_connected_account_id: stripeAcct || null,
      webhook_secret: webhookSecret || null
    });
  };

  const activeError = activeTab === "briefing" ? briefingError : clientsError;
  const activeLoading = activeTab === "briefing" ? isBriefingLoading : isClientsLoading;

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
          <button onClick={() => setActiveTab("onboard")} className={`nav-item ${activeTab === "onboard" ? "active" : ""}`} style={{ width: '100%', textAlign: 'left' }}>
            <span className="nav-icon">⚙️</span>
            Onboard Account
          </button>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="header flex-between" style={{ alignItems: 'flex-start' }}>
          <div>
            <h1 className="page-title text-gradient">
              {activeTab === "briefing" && "Morning Briefing"}
              {activeTab === "clients" && "Client State Registry"}
              {activeTab === "onboard" && "Coach Settings & Setup"}
            </h1>
            <p className="page-subtitle text-muted font-sans">
              {activeTab === "briefing" && "Structured Business Intelligence Hub"}
              {activeTab === "clients" && "Active Coach-Client Metrics Tracking"}
              {activeTab === "onboard" && "Register profile & configure multi-tenant webhooks"}
            </p>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', alignItems: 'flex-end' }}>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              {token ? (
                <button className="btn btn-secondary" onClick={handleLogout} style={{ padding: '0.5rem 1.2rem' }}>
                  🔒 Logout
                </button>
              ) : null}
              <button 
                className="btn btn-secondary" 
                onClick={activeTab === "briefing" ? () => refetchBriefing() : () => refetchClients()} 
                disabled={activeLoading || !token || activeTab === "onboard"} 
                style={{ padding: '0.5rem 1.2rem', display: 'flex', gap: '0.5rem' }}
              >
                <span>🔄</span> Sync
              </button>
            </div>
            {token && <span style={{ fontSize: '0.75rem', color: 'var(--success)' }}>✓ JWT credential session active</span>}
          </div>
        </header>

        {/* Authentication Gateway */}
        {!token && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', maxWidth: '450px', margin: '3rem auto' }}>
            {supabase ? (
              <section className="card glass-panel" style={{ padding: '2rem' }}>
                <h3 style={{ marginBottom: '1.25rem', textAlign: 'center' }} className="text-gradient">
                  {authMode === "login" ? "Coach Login" : "Coach Sign Up"}
                </h3>
                <form onSubmit={handleSupabaseAuth} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  <input 
                    type="email" 
                    placeholder="Coach Email Address" 
                    required 
                    value={authEmail}
                    onChange={(e) => setAuthEmail(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                  <input 
                    type="password" 
                    placeholder="Account Password" 
                    required 
                    value={authPassword}
                    onChange={(e) => setAuthPassword(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                  <button type="submit" className="btn btn-primary" style={{ padding: '0.7rem' }} disabled={authLoading}>
                    {authLoading ? "Verifying..." : authMode === "login" ? "Login" : "Sign Up"}
                  </button>
                </form>
                <div style={{ marginTop: '1rem', textAlign: 'center', fontSize: '0.85rem' }}>
                  <button 
                    onClick={() => setAuthMode(authMode === "login" ? "signup" : "login")}
                    style={{ color: 'var(--accent-primary)', textDecoration: 'underline' }}
                  >
                    Switch to {authMode === "login" ? "Sign Up" : "Login"}
                  </button>
                </div>
              </section>
            ) : null}

            {/* Manual JWT Bypass Panel (For Development & offline testing support) */}
            <section className="card glass-panel" style={{ padding: '2rem', borderTop: '2px solid var(--accent-primary)' }}>
              <h3 style={{ marginBottom: '0.75rem', textAlign: 'center' }}>🔒 Direct Token Bypass</h3>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem', marginBottom: '1.25rem', textAlign: 'center' }}>
                No Supabase URL configured. Enter a direct JWT token payload here to bypass authentication routing.
              </p>
              <form onSubmit={handleManualTokenSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <input 
                  type="password" 
                  placeholder="Paste Supabase bearer JWT..." 
                  required 
                  value={manualToken}
                  onChange={(e) => setManualToken(e.target.value)}
                  style={{
                    background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-color)',
                    color: 'var(--text-primary)',
                    borderRadius: 'var(--border-radius-sm)',
                    padding: '0.6rem 1rem',
                    fontFamily: 'monospace',
                    fontSize: '0.8rem'
                  }}
                />
                <button type="submit" className="btn btn-secondary" style={{ padding: '0.6rem' }}>
                  Apply Bypass Token
                </button>
              </form>
            </section>
          </div>
        )}

        {token && activeLoading && (
          <div style={{ color: 'var(--text-secondary)', padding: '5rem 0', textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', marginBottom: '0.5rem' }}>⏳ Querying Pipeline</div>
            <p>Syncing tenant metadata states and analyzing active prediction models...</p>
          </div>
        )}

        {token && activeError && activeTab !== "onboard" && (
          <div className="card glass-panel" style={{ borderLeft: '4px solid var(--danger)', padding: '2rem' }}>
            <h3 style={{ color: 'var(--danger)', marginBottom: '0.5rem' }}>⚠️ Connection / Validation Refused</h3>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>{(activeError as Error).message}</p>
            {((activeError as Error).message.includes("not registered as a coach") || (activeError as Error).message.includes("403")) && (
              <button className="btn btn-primary" onClick={() => setActiveTab("onboard")}>
                Go to Onboarding Setup
              </button>
            )}
          </div>
        )}

        {/* tab 1: briefing view */}
        {token && !activeLoading && !activeError && activeTab === "briefing" && briefingData && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.5rem' }}>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>REVENUE AT RISK</span>
                <h2 style={{ fontSize: '2rem', color: briefingData.revenue_at_risk > 0 ? 'var(--danger)' : 'var(--success)' }}>
                  ${briefingData.revenue_at_risk.toFixed(2)}
                </h2>
              </div>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>ACTIVE COMPOSITE ALERTS</span>
                <h2 style={{ fontSize: '2rem', color: briefingData.active_signals_count > 0 ? 'var(--warning)' : 'var(--text-primary)' }}>
                  {briefingData.active_signals_count}
                </h2>
              </div>
              <div className="card glass-panel">
                <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>PENDING STRATEGIC ACTIONS</span>
                <h2 style={{ fontSize: '2rem' }}>{briefingData.pending_actions_count}</h2>
              </div>
            </div>

            <section className="card glass-panel">
              <h3 className="card-title" style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <span>📖</span> AI Daily Summary
              </h3>
              <div className="briefing-box" style={{ fontSize: '1.05rem', color: 'var(--text-secondary)' }}>
                {briefingData.briefing}
              </div>
            </section>

            {briefingData.urgent_alerts.length > 0 && (
              <section style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <h3 style={{ fontSize: '1.3rem', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span>⚠️</span> Action Required: High Priority Interventions
                </h3>
                
                <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '1rem' }}>
                  {briefingData.urgent_alerts.map((alert, index) => (
                    <div key={index} className="card glass-panel flex-between" style={{ borderLeft: `4px solid ${alert.severity === 'high' ? 'var(--danger)' : 'var(--warning)'}`, flexDirection: 'row', padding: '1.5rem' }}>
                      <div>
                        <h4 style={{ fontSize: '1.1rem', marginBottom: '0.25rem' }}>{alert.client_name}</h4>
                        <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                          Signal Type: <span style={{ color: 'var(--text-primary)', textTransform: 'capitalize' }}>{alert.signal_type.replace('_', ' ')}</span> | Severity: <span style={{ color: alert.severity === 'high' ? 'var(--danger)' : 'var(--warning)' }}>{alert.severity.toUpperCase()}</span>
                        </p>
                      </div>
                      
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginRight: '0.75rem' }}>
                          Target: <strong style={{ color: 'var(--text-primary)' }}>{alert.action_suggested.replace(/_/g, ' ')}</strong>
                        </span>
                        {alert.action_id && (
                          <>
                            <button 
                              className="btn btn-primary" 
                              style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} 
                              disabled={actionMutation.isPending}
                              onClick={() => actionMutation.mutate({ actionId: alert.action_id!, status: "completed" })}
                            >
                              Execute
                            </button>
                            <button 
                              className="btn btn-secondary" 
                              style={{ padding: '0.5rem 1rem', fontSize: '0.85rem' }} 
                              disabled={actionMutation.isPending}
                              onClick={() => actionMutation.mutate({ actionId: alert.action_id!, status: "rejected" })}
                            >
                              Dismiss
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </section>
            )}
          </div>
        )}

        {/* tab 2: client list view */}
        {token && !activeLoading && !activeError && activeTab === "clients" && (
          <section className="card glass-panel animate-fade-in">
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
                  {clientsData.map((client: ClientListItem) => (
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
                        {client.days_since_checkin >= 999 ? "Never checked in" : `${client.days_since_checkin} days`}
                      </td>
                    </tr>
                  ))}
                  {clientsData.length === 0 && (
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

        {/* tab 3: onboarding coach form */}
        {token && activeTab === "onboard" && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            <section className="card glass-panel animate-fade-in" style={{ maxWidth: '650px' }}>
              <h3 className="card-title" style={{ marginBottom: '1.5rem' }}>Provision Coach Profile</h3>
              
              <form onSubmit={handleRegisterFormSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Coach Full Name</label>
                  <input 
                    type="text" 
                    required 
                    placeholder="John Doe" 
                    value={regName}
                    onChange={(e) => setRegName(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Business Contact Email</label>
                  <input 
                    type="email" 
                    required 
                    placeholder="john@business.com" 
                    value={regEmail}
                    onChange={(e) => setRegEmail(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Stripe Connect Account ID (Optional)</label>
                  <input 
                    type="text" 
                    placeholder="acct_1xxxxxxxxx" 
                    value={stripeAcct}
                    onChange={(e) => setStripeAcct(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
                  <label style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>Stripe Webhook Secret (Optional)</label>
                  <input 
                    type="password" 
                    placeholder="whsec_xxxxxxxxxx" 
                    value={webhookSecret}
                    onChange={(e) => setWebhookSecret(e.target.value)}
                    style={{
                      background: 'var(--bg-elevated)',
                      border: '1px solid var(--border-color)',
                      color: 'var(--text-primary)',
                      borderRadius: 'var(--border-radius-sm)',
                      padding: '0.6rem 1rem'
                    }}
                  />
                </div>

                <button 
                  type="submit" 
                  className="btn btn-primary" 
                  style={{ padding: '0.75rem', width: '100%', marginTop: '0.5rem' }}
                  disabled={onboardMutation.isPending}
                >
                  {onboardMutation.isPending ? "Provisioning Profile..." : "Register Profile & Generate Webhooks"}
                </button>
              </form>
            </section>

            {onboardResult && (
              <section className="card glass-panel" style={{ maxWidth: '650px', borderLeft: '4px solid var(--success)' }}>
                <h3 style={{ color: 'var(--success)', marginBottom: '0.5rem' }}>✓ Profile Active</h3>
                <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem', marginBottom: '1rem' }}>
                  Configure your Stripe Dashboard Webhooks to forward events directly to this isolated URL endpoint:
                </p>
                <div style={{
                  background: 'var(--bg-elevated)',
                  padding: '0.8rem',
                  borderRadius: 'var(--border-radius-sm)',
                  fontSize: '0.9rem',
                  color: 'var(--text-primary)',
                  wordBreak: 'break-all',
                  fontFamily: 'monospace'
                }}>
                  {API_URL}{onboardResult.webhook_url}
                </div>
              </section>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
