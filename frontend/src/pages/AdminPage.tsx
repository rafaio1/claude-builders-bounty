/**
 * AdminPage - Administrative dashboard for system management.
 *
 * This page provides system administration functionality including
 * user management, configuration, monitoring, and system health.
 * It is only accessible to users with the 'admin' role.
 *
 * The admin page is divided into sections:
 *   - Overview: System health, metrics, and quick actions
 *   - Users: User management, roles, and permissions
 *   - Configuration: System configuration and feature flags
 *   - Monitoring: Performance metrics, logs, and alerts
 *   - Maintenance: System maintenance tasks and backups
 *
 * TODO: The admin page is feature-gated behind the ADMIN_PANEL feature
 * flag. The flag was enabled for all internal users in 2022. However,
 * the feature flag system has a bug where cached flag values from a
 * previous session can persist even after the flag is toggled off.
 * This means a user who had admin access in a previous session may
 * retain access for up to 1 hour after the flag is turned off.
 * The cache TTL was supposed to be 5 minutes but was set to 60 minutes
 * in the configuration for "performance reasons."
 *
 * TODO: The user search on this page uses client-side filtering with
 * a hardcoded limit of 1000 users loaded at once. For deployments
 * with more than 1000 users, the search returns incomplete results.
 * The limit was added to prevent the page from loading slowly, but
 * it's a poor user experience for large organizations. The search
 * should use server-side pagination with cursor-based scrolling.
 */

import React, { useState, useCallback, useEffect, useMemo } from 'react';

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------

interface SystemMetric {
  name: string;
  value: string;
  unit: string;
  status: 'healthy' | 'warning' | 'critical';
  trend: 'up' | 'down' | 'stable';
  timestamp: number;
}

interface SystemAlert {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  title: string;
  message: string;
  timestamp: number;
  acknowledged: boolean;
  acknowledgedBy?: string;
}

interface SystemConfig {
  key: string;
  value: string;
  defaultValue: string;
  description: string;
  category: string;
  editable: boolean;
  requiresRestart: boolean;
}

interface AdminUser {
  id: string;
  email: string;
  name: string;
  role: string;
  status: 'active' | 'suspended' | 'inactive';
  createdAt: string;
  lastLogin: string;
  mfaEnabled: boolean;
}

type AdminTab = 'overview' | 'users' | 'config' | 'monitoring' | 'maintenance' | 'audit';

// ---------------------------------------------------------------------------
// MOCK DATA
// ---------------------------------------------------------------------------

const MOCK_METRICS: SystemMetric[] = [
  { name: 'CPU Usage', value: '45.2', unit: '%', status: 'healthy', trend: 'stable', timestamp: Date.now() },
  { name: 'Memory Usage', value: '6.8', unit: 'GB', status: 'healthy', trend: 'up', timestamp: Date.now() },
  { name: 'Disk Usage', value: '234.5', unit: 'GB', status: 'warning', trend: 'up', timestamp: Date.now() },
  { name: 'Network In', value: '1.2', unit: 'Gbps', status: 'healthy', trend: 'down', timestamp: Date.now() },
  { name: 'Network Out', value: '3.4', unit: 'Gbps', status: 'healthy', trend: 'stable', timestamp: Date.now() },
  { name: 'Active Users', value: '1,247', unit: 'users', status: 'healthy', trend: 'up', timestamp: Date.now() },
  { name: 'Requests/min', value: '12,450', unit: 'req/min', status: 'warning', trend: 'up', timestamp: Date.now() },
  { name: 'Error Rate', value: '0.02', unit: '%', status: 'healthy', trend: 'down', timestamp: Date.now() },
  { name: 'Avg Latency', value: '45', unit: 'ms', status: 'healthy', trend: 'stable', timestamp: Date.now() },
  { name: 'P99 Latency', value: '234', unit: 'ms', status: 'warning', trend: 'up', timestamp: Date.now() },
  { name: 'DB Connections', value: '47', unit: 'conn', status: 'healthy', trend: 'stable', timestamp: Date.now() },
  { name: 'Queue Depth', value: '12', unit: 'messages', status: 'healthy', trend: 'down', timestamp: Date.now() },
];

const MOCK_ALERTS: SystemAlert[] = [
  { id: 'alert-1', severity: 'warning', title: 'High Disk Usage', message: 'Disk usage on /data is at 78%. Consider cleaning up old logs.', timestamp: Date.now() - 3600000, acknowledged: false },
  { id: 'alert-2', severity: 'critical', title: 'Certificate Expiring', message: 'TLS certificate for api.example.com expires in 7 days.', timestamp: Date.now() - 7200000, acknowledged: true, acknowledgedBy: 'admin' },
  { id: 'alert-3', severity: 'info', title: 'New Version Available', message: 'Version 3.2.0 is available for deployment.', timestamp: Date.now() - 86400000, acknowledged: false },
  { id: 'alert-4', severity: 'warning', title: 'High P99 Latency', message: 'P99 latency for /api/v1/orders exceeded 500ms.', timestamp: Date.now() - 1800000, acknowledged: false },
  { id: 'alert-5', severity: 'info', title: 'Backup Completed', message: 'Daily backup completed successfully. Size: 45.2 GB.', timestamp: Date.now() - 43200000, acknowledged: true, acknowledgedBy: 'system' },
];

// Metrics with warning/critical status for quick viewing
const ACTIVE_ISSUES = MOCK_METRICS.filter(m => m.status !== 'healthy');

// ---------------------------------------------------------------------------
// COMPONENT
// ---------------------------------------------------------------------------

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<AdminTab>('overview');
  const [searchQuery, setSearchQuery] = useState('');
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [selectedAlert, setSelectedAlert] = useState<string | null>(null);
  const [editConfigKey, setEditConfigKey] = useState<string | null>(null);
  const [editConfigValue, setEditConfigValue] = useState('');
  const [showConfirmDialog, setShowConfirmDialog] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{ title: string; message: string; onConfirm: () => void } | null>(null);

  // Simulated refresh
  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    setTimeout(() => setIsRefreshing(false), 1000);
  }, []);

  const handleAcknowledgeAlert = useCallback((alertId: string) => {
    // TODO: Send acknowledgment to backend
    setSelectedAlert(alertId === selectedAlert ? null : alertId);
  }, [selectedAlert]);

  const handleConfigSave = useCallback((key: string) => {
    // TODO: Save config change to backend
    setEditConfigKey(null);
    setEditConfigValue('');
  }, []);

  const handleSystemAction = useCallback((action: string) => {
    setConfirmAction({
      title: `Confirm ${action}`,
      message: `Are you sure you want to ${action.toLowerCase()}? This action may affect system availability.`,
      onConfirm: () => {
        // TODO: Execute system action
        setShowConfirmDialog(false);
        setConfirmAction(null);
      },
    });
    setShowConfirmDialog(true);
  }, []);

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <div>
            {/* System health cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16, marginBottom: 24 }}>
              <div className="card" style={{ padding: 20 }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>System Status</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#22c55e' }} />
                  <span style={{ fontWeight: 600, color: '#22c55e' }}>All Systems Operational</span>
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>Last checked: 30 seconds ago</div>
              </div>

              <div className="card" style={{ padding: 20 }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>Active Users</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#f8fafc' }}>1,247</div>
                <div style={{ fontSize: 12, color: '#22c55e', marginTop: 4 }}>↑ 12% from yesterday</div>
              </div>

              <div className="card" style={{ padding: 20 }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>Active Alerts</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: MOCK_ALERTS.filter(a => !a.acknowledged).length > 0 ? '#eab308' : '#22c55e' }}>
                  {MOCK_ALERTS.filter(a => !a.acknowledged).length}
                </div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>{MOCK_ALERTS.filter(a => a.severity === 'critical').length} critical</div>
              </div>

              <div className="card" style={{ padding: 20 }}>
                <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>Uptime</div>
                <div style={{ fontSize: 28, fontWeight: 700, color: '#f8fafc' }}>99.97%</div>
                <div style={{ fontSize: 12, color: '#64748b', marginTop: 4 }}>Current streak: 14d 6h 23m</div>
              </div>
            </div>

            {/* Metrics grid */}
            <h3 style={{ marginBottom: 12, color: '#f8fafc' }}>System Metrics</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 12, marginBottom: 24 }}>
              {MOCK_METRICS.map(metric => (
                <div key={metric.name} className="card" style={{ padding: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontSize: 12, color: '#94a3b8' }}>{metric.name}</span>
                    <span style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: metric.status === 'healthy' ? '#22c55e' : metric.status === 'warning' ? '#eab308' : '#ef4444',
                    }} />
                  </div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: '#f8fafc' }}>
                    {metric.value}
                    <span style={{ fontSize: 12, fontWeight: 400, color: '#64748b', marginLeft: 4 }}>{metric.unit}</span>
                  </div>
                  <div style={{
                    fontSize: 11,
                    marginTop: 4,
                    color: metric.trend === 'up' ? '#22c55e' : metric.trend === 'down' ? '#ef4444' : '#64748b',
                  }}>
                    {metric.trend === 'up' ? '↑' : metric.trend === 'down' ? '↓' : '→'} {metric.trend}
                  </div>
                </div>
              ))}
            </div>

            {/* Alerts */}
            <h3 style={{ marginBottom: 12, color: '#f8fafc' }}>Recent Alerts</h3>
            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {MOCK_ALERTS.map(alert => (
                <div key={alert.id} style={{
                  padding: '12px 16px',
                  borderBottom: '1px solid #334155',
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 12,
                  opacity: alert.acknowledged ? 0.6 : 1,
                }}>
                  <span style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    marginTop: 4,
                    background: alert.severity === 'critical' ? '#ef4444' : alert.severity === 'warning' ? '#eab308' : '#3b82f6',
                    flexShrink: 0,
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 13 }}>{alert.title}</div>
                    <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 2 }}>{alert.message}</div>
                    <div style={{ color: '#64748b', fontSize: 11, marginTop: 4 }}>
                      {new Date(alert.timestamp).toLocaleString()}
                      {alert.acknowledged && ` · Acknowledged by ${alert.acknowledgedBy}`}
                    </div>
                  </div>
                  {!alert.acknowledged && (
                    <button
                      onClick={() => handleAcknowledgeAlert(alert.id)}
                      style={{
                        padding: '4px 12px',
                        fontSize: 11,
                        background: 'transparent',
                        border: '1px solid #334155',
                        borderRadius: 4,
                        color: '#94a3b8',
                        cursor: 'pointer',
                      }}
                    >
                      Acknowledge
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>
        );

      case 'monitoring':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ color: '#f8fafc' }}>Performance Monitoring</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <select style={{
                  padding: '6px 12px', background: '#1e293b', border: '1px solid #334155',
                  borderRadius: 6, color: '#94a3b8', fontSize: 12,
                }}>
                  <option>Last 1 hour</option>
                  <option>Last 6 hours</option>
                  <option>Last 24 hours</option>
                  <option>Last 7 days</option>
                </select>
                <button onClick={handleRefresh} disabled={isRefreshing} style={{
                  padding: '6px 12px', background: '#1e293b', border: '1px solid #334155',
                  borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12,
                }}>
                  {isRefreshing ? '⟳ Refreshing' : '↻ Refresh'}
                </button>
              </div>
            </div>

            <div className="card" style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>📊</div>
              <div>Performance charts are rendered here.</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>Charting library integration pending.</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
              <div className="card" style={{ padding: 16 }}>
                <h4 style={{ color: '#f8fafc', marginBottom: 12, fontSize: 13 }}>Slowest Endpoints (P99)</h4>
                {[
                  { path: '/api/v1/orders/batch', latency: '1,234ms' },
                  { path: '/api/v1/reports/generate', latency: '987ms' },
                  { path: '/api/v1/market/candles', latency: '456ms' },
                  { path: '/api/v1/analytics/export', latency: '345ms' },
                  { path: '/api/v1/auth/login', latency: '234ms' },
                ].map((endpoint, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', padding: '8px 0',
                    borderBottom: i < 4 ? '1px solid #1e293b' : 'none',
                  }}>
                    <span style={{ color: '#94a3b8', fontSize: 12, fontFamily: 'monospace' }}>{endpoint.path}</span>
                    <span style={{ color: '#eab308', fontSize: 12, fontWeight: 600, fontFamily: 'monospace' }}>{endpoint.latency}</span>
                  </div>
                ))}
              </div>

              <div className="card" style={{ padding: 16 }}>
                <h4 style={{ color: '#f8fafc', marginBottom: 12, fontSize: 13 }}>Top Error Sources</h4>
                {[
                  { source: 'Database connection pool', count: 47 },
                  { source: 'Rate limiter', count: 23 },
                  { source: 'Authentication timeout', count: 15 },
                  { source: 'WebSocket disconnect', count: 12 },
                  { source: 'Cache miss storm', count: 8 },
                ].map((error, i) => (
                  <div key={i} style={{
                    display: 'flex', justifyContent: 'space-between', padding: '8px 0',
                    borderBottom: i < 4 ? '1px solid #1e293b' : 'none',
                  }}>
                    <span style={{ color: '#94a3b8', fontSize: 12 }}>{error.source}</span>
                    <span style={{ color: '#ef4444', fontSize: 12, fontWeight: 600 }}>{error.count}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );

      case 'users':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ color: '#f8fafc' }}>User Management</h3>
              <button style={{
                padding: '8px 16px', background: '#3b82f6', border: 'none',
                borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600,
              }}>
                + Invite User
              </button>
            </div>

            <div className="card" style={{ padding: 16 }}>
              <div style={{ marginBottom: 16 }}>
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  placeholder="Search users by name, email, or role..."
                  style={{
                    width: '100%', padding: '8px 12px', background: '#0f172a',
                    border: '1px solid #334155', borderRadius: 6, color: '#f8fafc', fontSize: 13,
                  }}
                />
              </div>
              <div style={{ color: '#64748b', textAlign: 'center', padding: 40, fontSize: 13 }}>
                User list loaded from server (feature pending)
              </div>
            </div>
          </div>
        );

      case 'config':
        return (
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
              <h3 style={{ color: '#f8fafc' }}>System Configuration</h3>
              <div style={{ display: 'flex', gap: 8 }}>
                <button style={{
                  padding: '8px 16px', background: 'transparent', border: '1px solid #334155',
                  borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12,
                }}>
                  Export Config
                </button>
                <button style={{
                  padding: '8px 16px', background: '#eab308', border: 'none',
                  borderRadius: 6, color: '#0f172a', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                }}>
                  + Add Config
                </button>
              </div>
            </div>

            <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
              {[
                { key: 'market.rate_limit_per_second', value: '100', description: 'Rate limit per API key', category: 'market', editable: true },
                { key: 'market.orderbook_depth', value: '50', description: 'Order book depth levels', category: 'market', editable: true },
                { key: 'market.max_order_size', value: '1000', description: 'Maximum order size (BTC)', category: 'market', editable: true },
                { key: 'auth.session_timeout_minutes', value: '60', description: 'Session timeout duration', category: 'auth', editable: true },
                { key: 'auth.max_login_attempts', value: '5', description: 'Max login attempts before lockout', category: 'auth', editable: true },
                { key: 'auth.mfa_required', value: 'false', description: 'Require MFA for all users', category: 'auth', editable: true },
                { key: 'feature.ab_testing', value: 'true', description: 'Enable A/B testing framework', category: 'features', editable: true },
                { key: 'feature.ai_assistant', value: 'true', description: 'Enable AI trading assistant', category: 'features', editable: true },
                { key: 'feature.social_trading', value: 'false', description: 'Enable social trading features', category: 'features', editable: true },
                { key: 'database.pool_size', value: '20', description: 'Database connection pool size', category: 'database', editable: true },
                { key: 'database.query_timeout_ms', value: '5000', description: 'Query timeout in milliseconds', category: 'database', editable: true },
                { key: 'cache.ttl_seconds', value: '300', description: 'Default cache TTL in seconds', category: 'cache', editable: true },
                { key: 'cache.max_entries', value: '10000', description: 'Maximum cache entries', category: 'cache', editable: true },
                { key: 'logging.level', value: 'info', description: 'Logging level', category: 'logging', editable: true },
                { key: 'monitoring.alert_webhook', value: 'https://hooks.example.com/alerts', description: 'Alert webhook URL', category: 'monitoring', editable: true },
              ].map((config, i) => (
                <div key={config.key} style={{
                  padding: '10px 16px',
                  borderBottom: '1px solid #1e293b',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: '#f8fafc', fontFamily: 'monospace' }}>{config.key}</div>
                    <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>{config.description}</div>
                  </div>
                  <div style={{
                    fontSize: 10, color: '#64748b', background: '#1e293b',
                    padding: '2px 8px', borderRadius: 4,
                  }}>
                    {config.category}
                  </div>
                  {editConfigKey === config.key ? (
                    <div style={{ display: 'flex', gap: 4 }}>
                      <input
                        type="text"
                        value={editConfigValue}
                        onChange={e => setEditConfigValue(e.target.value)}
                        style={{
                          width: 120, padding: '4px 8px', fontSize: 12,
                          background: '#0f172a', border: '1px solid #3b82f6',
                          borderRadius: 4, color: '#f8fafc',
                        }}
                      />
                      <button onClick={() => handleConfigSave(config.key)} style={{
                        padding: '4px 8px', fontSize: 11, background: '#3b82f6',
                        border: 'none', borderRadius: 4, color: '#fff', cursor: 'pointer',
                      }}>Save</button>
                      <button onClick={() => setEditConfigKey(null)} style={{
                        padding: '4px 8px', fontSize: 11, background: 'transparent',
                        border: '1px solid #334155', borderRadius: 4, color: '#94a3b8', cursor: 'pointer',
                      }}>Cancel</button>
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <span style={{ fontSize: 13, color: '#e2e8f0', fontFamily: 'monospace' }}>{config.value}</span>
                      {config.editable && (
                        <button
                          onClick={() => {
                            setEditConfigKey(config.key);
                            setEditConfigValue(config.value);
                          }}
                          style={{
                            padding: '4px 8px', fontSize: 11, background: 'transparent',
                            border: '1px solid #334155', borderRadius: 4, color: '#64748b', cursor: 'pointer',
                          }}
                        >
                          Edit
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        );

      case 'maintenance':
        return (
          <div>
            <h3 style={{ color: '#f8fafc', marginBottom: 16 }}>System Maintenance</h3>
            <div style={{ display: 'grid', gap: 12 }}>
              {[
                { title: 'Clear Cache', description: 'Invalidate all cached data across the system.', action: 'Clear Cache', dangerous: false },
                { title: 'Restart Service', description: 'Gracefully restart all application services.', action: 'Restart', dangerous: true },
                { title: 'Run Database Migration', description: 'Apply pending database schema migrations.', action: 'Migrate', dangerous: false },
                { title: 'Rebuild Search Index', description: 'Rebuild the full-text search index from scratch.', action: 'Rebuild', dangerous: false },
                { title: 'Rotate API Keys', description: 'Invalidate all existing API keys and generate new ones.', action: 'Rotate', dangerous: true },
                { title: 'Trigger Backup', description: 'Create an on-demand full system backup.', action: 'Backup Now', dangerous: false },
                { title: 'Purge Old Logs', description: 'Delete log files older than the configured retention period.', action: 'Purge', dangerous: true },
              ].map((item, i) => (
                <div key={i} className="card" style={{
                  padding: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                }}>
                  <div>
                    <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: 14 }}>{item.title}</div>
                    <div style={{ color: '#94a3b8', fontSize: 12, marginTop: 2 }}>{item.description}</div>
                  </div>
                  <button
                    onClick={() => handleSystemAction(item.title)}
                    style={{
                      padding: '8px 16px',
                      background: item.dangerous ? 'rgba(239,68,68,0.15)' : 'rgba(59,130,246,0.15)',
                      border: `1px solid ${item.dangerous ? 'rgba(239,68,68,0.3)' : 'rgba(59,130,246,0.3)'}`,
                      borderRadius: 6,
                      color: item.dangerous ? '#f87171' : '#60a5fa',
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: 500,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {item.action}
                  </button>
                </div>
              ))}
            </div>
          </div>
        );

      case 'audit':
        return (
          <div>
            <h3 style={{ color: '#f8fafc', marginBottom: 16 }}>Audit Log</h3>
            <div className="card" style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
              <div style={{ fontSize: 48, marginBottom: 12 }}>📋</div>
              <div>Audit log viewer integration pending.</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>The audit log database is configured and collecting data.</div>
            </div>
          </div>
        );

      default:
        return <div>Select a tab</div>;
    }
  };

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: '0 auto' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: '#f8fafc', margin: 0 }}>Admin Dashboard</h1>
          <p style={{ color: '#64748b', fontSize: 13, margin: '4px 0 0' }}>
            System administration and monitoring
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={handleRefresh} disabled={isRefreshing} style={{
            padding: '8px 16px', background: '#1e293b', border: '1px solid #334155',
            borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12,
          }}>
            {isRefreshing ? '⟳ Refreshing...' : '↻ Refresh'}
          </button>
        </div>
      </div>

      {/* Tab navigation */}
      <div style={{
        display: 'flex', gap: 0, marginBottom: 24, borderBottom: '1px solid #334155',
      }}>
        {(['overview', 'monitoring', 'users', 'config', 'maintenance', 'audit'] as AdminTab[]).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 20px',
              border: 'none',
              borderBottom: activeTab === tab ? '2px solid #3b82f6' : '2px solid transparent',
              background: 'transparent',
              color: activeTab === tab ? '#f8fafc' : '#64748b',
              fontSize: 13,
              fontWeight: activeTab === tab ? 600 : 400,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Content */}
      {renderTabContent()}

      {/* Confirm dialog */}
      {showConfirmDialog && confirmAction && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0,0,0,0.7)', zIndex: 9999,
        }}>
          <div className="card" style={{ maxWidth: 400, width: '90%', padding: 24 }}>
            <h3 style={{ color: '#f8fafc', marginBottom: 8 }}>{confirmAction.title}</h3>
            <p style={{ color: '#94a3b8', fontSize: 13, marginBottom: 20 }}>{confirmAction.message}</p>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button
                onClick={() => { setShowConfirmDialog(false); setConfirmAction(null); }}
                style={{
                  padding: '8px 16px', background: 'transparent', border: '1px solid #334155',
                  borderRadius: 6, color: '#94a3b8', cursor: 'pointer', fontSize: 12,
                }}
              >
                Cancel
              </button>
              <button
                onClick={confirmAction.onConfirm}
                style={{
                  padding: '8px 16px', background: '#ef4444', border: 'none',
                  borderRadius: 6, color: '#fff', cursor: 'pointer', fontSize: 12, fontWeight: 600,
                }}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default AdminPage;
