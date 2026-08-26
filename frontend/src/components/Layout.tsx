import React from 'react';
import Header from './Header';
import Sidebar from './Sidebar';

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = React.useState(true);

  return (
    <div className="app-layout">
      <Header
        onMenuToggle={() => setSidebarOpen((prev) => !prev)}
      />
      <div className="app-body">
        <Sidebar isOpen={sidebarOpen} />
        <main className="app-content">
          {children}
        </main>
      </div>
    </div>
  );
};

export default Layout;
