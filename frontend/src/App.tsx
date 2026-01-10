import { useEffect, useState } from "react";
import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useLocation,
} from "react-router-dom";
import { useAuthStore } from "@/store/authStore";
import { useSettingsStore } from "@/store/settingsStore";
import { getSetupStatus } from "@/lib/settingsApi";
import { authApi } from "@/features/auth/api/auth";
import LoginPage from "@/pages/LoginPage";
import ForgotPasswordPage from "@/pages/ForgotPasswordPage";
import ResetPasswordPage from "@/pages/ResetPasswordPage";
import SetupPage from "@/pages/SetupPage";
import DashboardPage from "@/pages/DashboardPage";
import SettingsPage from "@/pages/SettingsPage";
import StatisticsPage from "@/pages/StatisticsPage";
import { UsersPage } from "@/features/admin/pages/UsersPage";
import AuditLogPage from "@/features/admin/pages/AuditLogPage";
import { PathsPage } from "@/features/paths/routes/PathsPage";
import { ForceChangePasswordPage } from "@/features/auth/pages/ForceChangePasswordPage";
import DashboardLayout from "@/components/layout/DashboardLayout";

// Loading spinner component
const LoadingSpinner = () => (
  <div className="min-h-screen bg-background flex items-center justify-center">
    <div className="text-center space-y-4">
      <div className="w-8 h-8 border-2 border-primary border-t-transparent rounded-full animate-spin mx-auto" />
      <p className="text-muted-foreground text-sm">Loading...</p>
    </div>
  </div>
);

// Auth Bootstrap - refresh session on initial load if possible
const AuthBootstrap = ({ children }: { children: React.ReactNode }) => {
  const [isReady, setIsReady] = useState(false);
  const setupRequired = useSettingsStore((state) => state.setupRequired);
  const accessToken = useAuthStore((state) => state.accessToken);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const login = useAuthStore((state) => state.login);
  const logout = useAuthStore((state) => state.logout);
  const setAccessToken = useAuthStore((state) => state.setAccessToken);

  useEffect(() => {
    let isMounted = true;

    const bootstrap = async () => {
      // If we have an access token already, we're ready
      if (accessToken) {
        if (isMounted) {
          setIsReady(true);
        }
        return;
      }

      // If setup is required, don't try to refresh auth
      // This prevents 401 errors in the console on the setup page
      if (setupRequired === true) {
        if (isMounted) {
          setIsReady(true);
        }
        return;
      }

      try {
        const sessionStatus = await authApi.checkSession();

        if (sessionStatus.is_authenticated && sessionStatus.access_token) {
          const newAccessToken = sessionStatus.access_token;
          setAccessToken(newAccessToken);
          try {
            const user = await authApi.getMe();
            if (isMounted && user) {
              login(newAccessToken, {
                id: user.id,
                email: user.email,
                role: user.role ?? "user",
                api_key_preview: user.api_key_preview ?? null,
                is_superuser: user.is_superuser ?? false,
                force_password_change: user.force_password_change ?? false,
                preferences: user.preferences,
              });
            }
          } catch (_err) {
            if (isMounted) {
              logout();
            }
          }
        } else if (isMounted && isAuthenticated) {
          // If we thought we were authenticated but backend says no -> logout
          logout();
        }
      } catch (_err) {
        if (isMounted && isAuthenticated) {
          logout();
        }
      }

      if (isMounted) {
        setIsReady(true);
      }
    };

    bootstrap();

    return () => {
      isMounted = false;
    };
  }, [
    accessToken,
    isAuthenticated,
    login,
    logout,
    setAccessToken,
    setupRequired,
  ]);

  if (!isReady) {
    return <LoadingSpinner />;
  }

  return <>{children}</>;
};

// Setup Check Wrapper - checks if setup is required
const SetupCheckWrapper = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { setupRequired, isLoading, setSetupState, setError } =
    useSettingsStore();

  useEffect(() => {
    const checkSetupStatus = async () => {
      try {
        const status = await getSetupStatus();
        setSetupState(
          status.setup_completed,
          status.setup_required,
          status.setup_forced,
        );
      } catch (err) {
        // If we can't reach the API, assume setup might be needed
        console.error("Failed to check setup status:", err);
        setError("Failed to connect to server");
        // Set to completed to allow normal flow if API is down
        setSetupState(true, false, false);
      }
    };

    // Only check if we haven't loaded yet
    if (setupRequired === null) {
      checkSetupStatus();
    }
  }, [setupRequired, setSetupState, setError]);

  // Show loading while checking setup status
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // If setup is required and not already on /onboarding, redirect
  if (setupRequired === true && location.pathname !== "/onboarding") {
    return <Navigate to="/onboarding" replace />;
  }

  // If setup is not required and on /onboarding, redirect to login
  if (setupRequired === false && location.pathname === "/onboarding") {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

// Protected Route Wrapper
const ProtectedRoute = ({ children }: { children: JSX.Element }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  return children;
};

// Public Route Wrapper (redirects to dashboard if already logged in)
const PublicRoute = ({ children }: { children: JSX.Element }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }
  return children;
};

function AppRoutes() {
  return (
    <SetupCheckWrapper>
      <AuthBootstrap>
        <Routes>
          {/* Onboarding route - public, only accessible when setup not completed */}
          <Route path="/onboarding" element={<SetupPage />} />

          {/* Login route - public */}
          <Route
            path="/login"
            element={
              <PublicRoute>
                <LoginPage />
              </PublicRoute>
            }
          />

          {/* Forgot Password route - public */}
          <Route
            path="/forgot-password"
            element={
              <PublicRoute>
                <ForgotPasswordPage />
              </PublicRoute>
            }
          />

          {/* Reset Password route - public */}
          <Route
            path="/reset-password"
            element={
              <PublicRoute>
                <ResetPasswordPage />
              </PublicRoute>
            }
          />

          {/* Force Password Change route - protected but outside DashboardLayout to avoid infinite loop */}
          <Route
            path="/change-password"
            element={
              <ProtectedRoute>
                <ForceChangePasswordPage />
              </ProtectedRoute>
            }
          />

          {/* Protected routes with DashboardLayout */}
          <Route
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/paths" element={<PathsPage />} />
            <Route path="/statistics" element={<StatisticsPage />} />
            <Route path="/admin/users" element={<UsersPage />} />
            <Route path="/admin/audit" element={<AuditLogPage />} />

            {/* Admin-only settings page */}
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <SettingsPage />
                </ProtectedRoute>
              }
            />
          </Route>

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthBootstrap>
    </SetupCheckWrapper>
  );
}

function App() {
  return (
    <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppRoutes />
    </Router>
  );
}

export default App;
