export interface User {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  avatar: string | null;
  createdAt: string;
  updatedAt: string;
}

export enum UserRole {
  Admin = 'admin',
  User = 'user',
  Viewer = 'viewer',
}

export interface Session {
  id: string;
  user: User;
  token: string;
  expiresAt: string;
  ip: string;
  userAgent: string;
}

export interface TrialMetric {
  id: string;
  name: string;
  value: number;
  unit: string;
  timestamp: string;
  tags: Record<string, string>;
}

export interface DashboardStats {
  totalUsers: number;
  activeSessions: number;
  trialsCompleted: number;
  avgResponseTime: number;
  errorRate: number;
  uptime: number;
  metrics: TrialMetric[];
}

export interface AppConfig {
  theme: ThemeConfig;
  notifications: NotificationConfig;
  features: FeatureFlags;
}

export interface ThemeConfig {
  primary: string;
  secondary: string;
  background: string;
  surface: string;
  text: string;
  darkMode: boolean;
}

export interface NotificationConfig {
  enabled: boolean;
  sound: boolean;
  desktop: boolean;
  email: boolean;
  frequency: 'realtime' | 'daily' | 'weekly';
}

export interface FeatureFlags {
  analytics: boolean;
  export: boolean;
  betaFeatures: boolean;
  experimental: boolean;
}
