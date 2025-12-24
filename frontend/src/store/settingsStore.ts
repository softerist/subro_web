import { create } from "zustand";

interface SettingsState {
  setupCompleted: boolean | null; // null = loading
  isLoading: boolean;
  error: string | null;
  setSetupCompleted: (completed: boolean) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useSettingsStore = create<SettingsState>()((set) => ({
  setupCompleted: null,
  isLoading: true,
  error: null,
  setSetupCompleted: (completed) =>
    set({ setupCompleted: completed, isLoading: false }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error, isLoading: false }),
  reset: () => set({ setupCompleted: null, isLoading: true, error: null }),
}));
