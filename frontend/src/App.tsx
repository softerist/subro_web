import { useEffect } from "react";
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
import LoginPage from "@/pages/LoginPage";
import SetupPage from "@/pages/SetupPage";
import DashboardPage from "@/pages/DashboardPage";
import SettingsPage from "@/pages/SettingsPage";
import StatisticsPage from "@/pages/StatisticsPage";
import { UsersPage } from "@/features/admin/pages/UsersPage";
import { PathsPage } from "@/features/paths/routes/PathsPage";
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

// Setup Check Wrapper - checks if setup is completed
const SetupCheckWrapper = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { setupCompleted, isLoading, setSetupCompleted, setError } =
    useSettingsStore();

  useEffect(() => {
    const checkSetupStatus = async () => {
      try {
        const status = await getSetupStatus();
        setSetupCompleted(status.setup_completed);
      } catch (err) {
        // If we can't reach the API, assume setup might be needed
        console.error("Failed to check setup status:", err);
        setError("Failed to connect to server");
        // Set to true to allow normal flow if API is down
        setSetupCompleted(true);
      }
    };

    // Only check if we haven't loaded yet
    if (setupCompleted === null) {
      checkSetupStatus();
    }
  }, [setupCompleted, setSetupCompleted, setError]);

  // Show loading while checking setup status
  if (isLoading) {
    return <LoadingSpinner />;
  }

  // If setup not completed and not already on /setup, redirect
  if (setupCompleted === false && location.pathname !== "/setup") {
    return <Navigate to="/setup" replace />;
  }

  // If setup is completed and on /setup, redirect to login
  if (setupCompleted === true && location.pathname === "/setup") {
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

// Admin Route Wrapper
const AdminRoute = ({ children }: { children: JSX.Element }) => {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const user = useAuthStore((state) => state.user);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!user?.is_superuser && user?.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
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
      <Routes>
        {/* Setup route - public, only accessible when setup not completed */}
        <Route path="/setup" element={<SetupPage />} />

        {/* Login route - public */}
        <Route
          path="/login"
          element={
            <PublicRoute>
              <LoginPage />
            </PublicRoute>
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

          {/* Admin-only settings page */}
          <Route
            path="/settings"
            element={
              <AdminRoute>
                <SettingsPage />
              </AdminRoute>
            }
          />
        </Route>

        {/* Default redirect */}
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
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
