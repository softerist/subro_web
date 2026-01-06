import { create } from "zustand";

interface SettingsState {
  setupCompleted: boolean | null; // null = loading
  setupRequired: boolean | null; // NEW: True if wizard should be shown
  setupForced: boolean | null; // NEW: True if FORCE_INITIAL_SETUP is set
  isLoading: boolean;
  error: string | null;
  setSetupState: (
    completed: boolean,
    required: boolean,
    forced: boolean,
  ) => void;
  setSetupCompleted: (completed: boolean) => void; // Legacy for compatibility
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

export const useSettingsStore = create<SettingsState>()((set) => ({
  setupCompleted: null,
  setupRequired: null,
  setupForced: null,
  isLoading: true,
  error: null,
  setSetupState: (completed, required, forced) =>
    set({
      setupCompleted: completed,
      setupRequired: required,
      setupForced: forced,
      isLoading: false,
    }),
  setSetupCompleted: (completed) =>
    set({
      setupCompleted: completed,
      setupRequired: !completed, // Backward compatible: not completed = required
      setupForced: false,
      isLoading: false,
    }),
  setLoading: (loading) => set({ isLoading: loading }),
  setError: (error) => set({ error, isLoading: false }),
  reset: () =>
    set({
      setupCompleted: null,
      setupRequired: null,
      setupForced: null,
      isLoading: true,
      error: null,
    }),
}));
