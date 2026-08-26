import React from 'react';

const metricPlaceholders = [
  { id: 'requests', label: 'Request Volume', type: 'line' },
  { id: 'latency', label: 'Latency Distribution', type: 'histogram' },
  { id: 'errors', label: 'Error Breakdown', type: 'pie' },
  { id: 'users', label: 'User Growth', type: 'area' },
  { id: 'performance', label: 'Performance Score', type: 'gauge' },
  { id: 'sessions', label: 'Session Duration', type: 'bar' },
];

const Analytics: React.FC = () => {
  const [timeRange, setTimeRange] = React.useState('24h');

  return (
    <div className="analytics">
      <div className="analytics-header">
        <div>
          <h2>Analytics</h2>
          <p className="analytics-subtitle">
            Performance metrics and usage statistics
          </p>
        </div>
        <select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          className="time-range-select"
        >
          <option value="1h">Last hour</option>
          <option value="24h">Last 24 hours</option>
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="90d">Last 90 days</option>
        </select>
      </div>

      <div className="metrics-grid">
        {metricPlaceholders.map((metric) => (
          <div key={metric.id} className="metric-card">
            <div className="metric-card-header">
              <h3>{metric.label}</h3>
              <span className="metric-type-badge">{metric.type}</span>
            </div>
            <div className="metric-chart-placeholder">
              <div className="chart-area">
                <svg viewBox="0 0 200 80" className="chart-skeleton">
                  <polyline
                    points="0,60 20,45 40,50 60,35 80,40 100,25 120,30 140,20 160,28 180,15 200,22"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    opacity="0.3"
                  />
                </svg>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default Analytics;
