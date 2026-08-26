import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type { User, DashboardStats, AppConfig } from '../types';

interface AppState {
  user: User | null;
  config: AppConfig | null;
  stats: DashboardStats | null;
  isLoading: boolean;
  error: string | null;

  setUser: (user: User | null) => void;
  setConfig: (config: AppConfig | null) => void;
  setStats: (stats: DashboardStats | null) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  user: null,
  config: null,
  stats: null,
  isLoading: false,
  error: null,
};

export const useAppStore = create<AppState>()(
  immer((set) => ({
    ...initialState,

    setUser: (user) =>
      set((state) => {
        state.user = user;
      }),

    setConfig: (config) =>
      set((state) => {
        state.config = config;
      }),

    setStats: (stats) =>
      set((state) => {
        state.stats = stats;
      }),

    setLoading: (loading) =>
      set((state) => {
        state.isLoading = loading;
      }),

    setError: (error) =>
      set((state) => {
        state.error = error;
      }),

    reset: () => set(initialState),
  })),
);
