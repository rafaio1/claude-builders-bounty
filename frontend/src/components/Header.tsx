import React from 'react';
import { useAppStore } from '../store';

interface HeaderProps {
  onMenuToggle: () => void;
}

const navItems = [
  { label: 'Dashboard', path: '/' },
  { label: 'Analytics', path: '/analytics' },
  { label: 'Settings', path: '/settings' },
];

const Header: React.FC<HeaderProps> = ({ onMenuToggle }) => {
  const user = useAppStore((state) => state.user);
  const currentPath = window.location.pathname;

  return (
    <header className="app-header">
      <div className="header-left">
        <button
          className="menu-toggle"
          onClick={onMenuToggle}
          aria-label="Toggle sidebar"
        >
          <span className="menu-icon" />
        </button>
        <h1 className="app-title">Tent of Trials</h1>
      </div>

      <nav className="header-nav">
        {navItems.map((item) => (
          <a
            key={item.path}
            href={item.path}
            className={`nav-link ${currentPath === item.path ? 'active' : ''}`}
          >
            {item.label}
          </a>
        ))}
      </nav>

      <div className="header-right">
        <div className="user-info">
          <span className="user-avatar">
            {user?.username?.charAt(0).toUpperCase() || '?'}
          </span>
          <span className="user-name">{user?.username || 'Guest'}</span>
        </div>
      </div>
    </header>
  );
};

export default Header;
