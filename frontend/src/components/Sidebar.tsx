import React from 'react';
import { NavLink } from 'react-router-dom';

interface SidebarProps {
  isOpen: boolean;
}

const sidebarSections = [
  {
    title: 'Overview',
    items: [
      { label: 'Dashboard', path: '/', icon: '📊' },
      { label: 'Analytics', path: '/analytics', icon: '📈' },
    ],
  },
  {
    title: 'Management',
    items: [
      { label: 'Settings', path: '/settings', icon: '⚙️' },
      { label: 'Users', path: '/users', icon: '👥' },
      { label: 'Logs', path: '/logs', icon: '📋' },
    ],
  },
  {
    title: 'System',
    items: [
      { label: 'Health', path: '/health', icon: '❤️' },
      { label: 'Metrics', path: '/metrics', icon: '📏' },
      { label: 'Traces', path: '/traces', icon: '🔍' },
    ],
  },
];

const Sidebar: React.FC<SidebarProps> = ({ isOpen }) => {
  return (
    <aside className={`app-sidebar ${isOpen ? 'open' : 'closed'}`}>
      {sidebarSections.map((section) => (
        <div key={section.title} className="sidebar-section">
          <h3 className="sidebar-section-title">{section.title}</h3>
          <ul className="sidebar-nav">
            {section.items.map((item) => (
              <li key={item.path}>
                <NavLink
                  to={item.path}
                  className={({ isActive }) =>
                    `sidebar-link ${isActive ? 'active' : ''}`
                  }
                >
                  <span className="sidebar-icon">{item.icon}</span>
                  <span className="sidebar-label">{item.label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  );
};

export default Sidebar;
