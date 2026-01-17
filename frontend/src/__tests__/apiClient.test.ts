/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it, vi } from "vitest";

const interceptorHandlers: {
  request?: (config: any) => any;
  responseFulfilled?: (response: any) => any;
  responseRejected?: (error: any) => Promise<unknown>;
} = {};

const mockApi: any = vi.fn();

vi.mock("axios", () => ({
  __esModule: true,
  default: {
    create: vi.fn(() => {
      mockApi.mockResolvedValue({ data: {} });
      mockApi.post = vi.fn();
      mockApi.interceptors = {
        request: {
          use: vi.fn((onFulfilled: (config: any) => any) => {
            interceptorHandlers.request = onFulfilled;
            return 0;
          }),
        },
        response: {
          use: vi.fn((onFulfilled: any, onRejected: any) => {
            interceptorHandlers.responseFulfilled = onFulfilled;
            interceptorHandlers.responseRejected = onRejected;
            return 0;
          }),
        },
      };
      mockApi.defaults = {};
      return mockApi;
    }),
  },
  create: vi.fn(() => mockApi),
}));

// Suppress [API] logs during tests
const originalLog = console.log;
const originalError = console.error;
vi.spyOn(console, "log").mockImplementation((...args) => {
  if (typeof args[0] === "string" && args[0].includes("[API]")) return;
  originalLog(...args);
});
vi.spyOn(console, "error").mockImplementation((...args) => {
  if (typeof args[0] === "string" && args[0].includes("[API]")) return;
  originalError(...args);
});

describe("apiClient interceptors", () => {
  let authStore: typeof import("../store/authStore").useAuthStore;

  beforeEach(async () => {
    vi.resetModules();
    vi.clearAllMocks();
    interceptorHandlers.request = undefined;
    interceptorHandlers.responseRejected = undefined;
    ({ useAuthStore: authStore } = await import("../store/authStore"));
    authStore.getState().logout();

    // Import after resetting modules so interceptors register with fresh handlers
    await import("../lib/apiClient");
  });

  it("attaches bearer token to outgoing requests except refresh", async () => {
    authStore.getState().setAccessToken("token-123");
    const requestHandler = interceptorHandlers.request!;

    const config = await requestHandler({
      url: "/v1/jobs/",
      headers: {},
    });
    expect(config?.headers?.Authorization).toBe("Bearer token-123");

    const configWithoutHeaders = await requestHandler({
      url: "/v1/jobs/",
      headers: undefined,
    });
    expect(configWithoutHeaders?.headers?.Authorization).toBe(
      "Bearer token-123",
    );

    const refreshConfig = await requestHandler({
      url: "/v1/auth/refresh",
      headers: {},
    });
    expect(refreshConfig?.headers?.Authorization).toBeUndefined();
  });

  it("refreshes token on 401 and retries original request", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    authStore.getState().setAccessToken("old-token");
    mockApi.post.mockResolvedValueOnce({
      data: { access_token: "new-token" },
    });
    mockApi.mockResolvedValueOnce({ data: { ok: true } });

    const originalRequest: any = { url: "/v1/protected", headers: undefined };
    const error = { config: originalRequest, response: { status: 401 } };

    const result = await responseHandler(error);

    expect(mockApi.post).toHaveBeenCalledWith("/v1/auth/refresh");
    expect(originalRequest._retry).toBe(true);
    expect(mockApi).toHaveBeenCalledWith(
      expect.objectContaining({
        url: "/v1/protected",
        headers: expect.objectContaining({
          Authorization: "Bearer new-token",
        }),
      }),
    );
    expect(authStore.getState().accessToken).toBe("new-token");
    expect(result).toEqual({ data: { ok: true } });
  });

  it("logs out and redirects when refresh fails", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      value: {
        ...originalLocation,
        href: "http://localhost/dashboard",
        pathname: "/dashboard",
      },
      writable: true,
      configurable: true,
    });

    const logoutSpy = vi.spyOn(authStore.getState(), "logout");
    mockApi.post.mockResolvedValueOnce({ data: { access_token: null } });

    const error = {
      config: { url: "/v1/protected", headers: {} },
      response: { status: 401 },
    };

    await expect(responseHandler(error)).rejects.toThrow(
      "Refresh did not return a new access token.",
    );

    expect(logoutSpy).toHaveBeenCalled();
    expect(window.location.href).toContain("/login");
    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
  });

  it("does not redirect when already on login but still logs out", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    authStore.getState().setAccessToken("token");
    const originalLocation = window.location;
    const locationMock = {
      ...originalLocation,
      href: "http://localhost/login",
      pathname: "/login",
    };
    Object.defineProperty(window, "location", {
      value: locationMock,
      writable: true,
      configurable: true,
    });

    const logoutSpy = vi.spyOn(authStore.getState(), "logout");
    mockApi.post.mockResolvedValueOnce({ data: { access_token: null } });
    const error = {
      config: { url: "/v1/protected", headers: {} },
      response: { status: 401 },
    };

    await expect(responseHandler(error)).rejects.toBeInstanceOf(Error);

    expect(logoutSpy).toHaveBeenCalled();
    expect(window.location.href).toBe("http://localhost/login");
    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
  });
  it("handles concurrent 401 requests with a single refresh", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    authStore.getState().setAccessToken("old-token");

    // Set default return for the retried requests (api(originalRequest))
    mockApi.mockResolvedValue({ data: { ok: true } });

    // Mock refresh endpoint - intentional delay to simulate network
    mockApi.post.mockImplementation(async (url: string) => {
      if (url === "/v1/auth/refresh") {
        await new Promise((resolve) => setTimeout(resolve, 50));
        return { data: { access_token: "new-token-concurrent" } };
      }
      return { data: { ok: true } };
    });

    const req1: any = { url: "/v1/resource1", headers: {} };
    const req2: any = { url: "/v1/resource2", headers: {} };

    const error1 = { config: req1, response: { status: 401 } };
    const error2 = { config: req2, response: { status: 401 } };

    // Trigger both handling roughly at the same time
    const [res1, res2] = await Promise.all([
      responseHandler(error1),
      responseHandler(error2),
    ]);

    // Should call refresh ONLY ONCE
    expect(mockApi.post).toHaveBeenCalledWith("/v1/auth/refresh");
    // We can't easily check call count to be exactly 1 if the implementation logic overlaps,
    // but the logic `if (!refreshPromise)` ensures singleton.
    // Let's verify via call count.
    const refreshCalls = mockApi.post.mock.calls.filter(
      (args: any[]) => args[0] === "/v1/auth/refresh",
    );
    expect(refreshCalls).toHaveLength(1);

    // Both requests should have been retried with new token
    expect(req1.headers.Authorization).toBe("Bearer new-token-concurrent");
    expect(req2.headers.Authorization).toBe("Bearer new-token-concurrent");

    expect(res1).toEqual({ data: { ok: true } });
    expect(res2).toEqual({ data: { ok: true } });
  });

  it("does not loop if refresh request itself fails with 401", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;

    const refreshRequest: any = { url: "/v1/auth/refresh", headers: {} };
    const error = { config: refreshRequest, response: { status: 401 } };

    // Should reject immediately, not loop
    await expect(responseHandler(error)).rejects.toMatchObject({
      response: { status: 401 },
    });
  });

  it("rejects non-401 errors and missing config directly", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    const genericError = {
      config: { url: "/oops" },
      response: { status: 500 },
    };
    await expect(responseHandler(genericError)).rejects.toBe(genericError);

    const noConfigError = {};
    await expect(responseHandler(noConfigError)).rejects.toBe(noConfigError);
  });

  it("passes through successful responses", () => {
    const onFulfilled = interceptorHandlers.responseFulfilled!;
    const resp = { data: { ok: true } };
    expect(onFulfilled(resp)).toBe(resp);
  });

  it("handles refresh API throwing an error and logs out", async () => {
    const responseHandler = interceptorHandlers.responseRejected!;
    authStore.getState().setAccessToken("token");
    const originalLocation = window.location;
    Object.defineProperty(window, "location", {
      value: {
        ...originalLocation,
        href: "http://localhost/dashboard",
        pathname: "/dashboard",
      },
      writable: true,
    });
    const logoutSpy = vi.spyOn(authStore.getState(), "logout");

    mockApi.post.mockRejectedValueOnce(new Error("network fail"));
    const error = {
      config: { url: "/v1/protected", headers: {} },
      response: { status: 401 },
    };

    await expect(responseHandler(error)).rejects.toBeInstanceOf(Error);
    expect(logoutSpy).toHaveBeenCalled();
    expect(window.location.href).toContain("/login");
    Object.defineProperty(window, "location", {
      value: originalLocation,
      writable: true,
    });
  });
});
