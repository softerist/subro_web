/** @vitest-environment jsdom */
import { describe, expect, it, beforeEach, vi } from "vitest";
import { useAuthStore } from "../store/authStore";

describe("authStore", () => {
  beforeEach(() => {
    // Reset state before each test
    useAuthStore.getState().logout();
  });

  it("should have initial state", () => {
    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.user).toBe(null);
    expect(state.accessToken).toBe(null);
  });

  it("should set access token", () => {
    useAuthStore.getState().setAccessToken("test-token");
    expect(useAuthStore.getState().accessToken).toBe("test-token");
  });

  it("should login", () => {
    const mockUser = {
      id: "1",
      email: "test@example.com",
      role: "admin",
      is_superuser: true,
    };
    useAuthStore.getState().login("test-token", mockUser);

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(true);
    expect(state.accessToken).toBe("test-token");
    expect(state.user).toEqual(mockUser);
  });

  it("should logout", () => {
    useAuthStore
      .getState()
      .login("token", { id: "1", email: "e", role: "r", is_superuser: true });
    useAuthStore.getState().logout();

    const state = useAuthStore.getState();
    expect(state.isAuthenticated).toBe(false);
    expect(state.accessToken).toBe(null);
    expect(state.user).toBe(null);
  });

  it("should set user data without altering tokens", () => {
    const user = {
      id: "99",
      email: "user@example.com",
      role: "member",
      is_superuser: false,
    };
    useAuthStore.getState().setUser(user);

    const state = useAuthStore.getState();
    expect(state.user).toEqual(user);
    expect(state.accessToken).toBe(null);
  });

  it("uses in-memory storage fallback when localStorage is unavailable", async () => {
    const originalLocalStorage = window.localStorage;
    Object.defineProperty(window, "localStorage", {
      value: undefined,
      configurable: true,
    });

    vi.resetModules();
    const { useAuthStore: fallbackStore } = await import("../store/authStore");
    const storage = (fallbackStore as any).persist.getOptions().storage;

    storage.setItem("auth-storage", "cached");
    expect(storage.getItem("auth-storage")).toBe("cached");
    storage.removeItem("auth-storage");
    expect(storage.getItem("auth-storage")).toBeNull();

    fallbackStore.getState().logout();
    Object.defineProperty(window, "localStorage", {
      value: originalLocalStorage,
      configurable: true,
    });
  });
});
