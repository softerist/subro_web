import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  LogOut,
  UploadCloud,
  Users,
  Folder,
  Settings,
  BarChart3,
  Menu,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/features/auth/api/auth";
import { useRef, useState } from "react";
import packageJson from "../../../package.json";

const APP_VERSION = packageJson.version;
const ENV_SUFFIX = import.meta.env.MODE === "development" ? "DEV" : "PROD";
const VERSION_DISPLAY = `V${APP_VERSION}-${ENV_SUFFIX}`;

export default function DashboardLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const isAdmin = user?.role === "admin" || user?.is_superuser;
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const [menuTranslate, setMenuTranslate] = useState(0);
  const touchStartXRef = useRef<number | null>(null);
  const menuWidthRef = useRef(288);

  const handleLogout = async () => {
    await authApi.logout();
    navigate("/login");
  };

  const openMobileMenu = () => {
    setIsMobileMenuOpen(true);
    setMenuTranslate(0);
  };

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
    setMenuTranslate(0);
  };

  const handleTouchStart = (event: React.TouchEvent<HTMLDivElement>) => {
    touchStartXRef.current = event.touches[0]?.clientX ?? null;
  };

  const handleTouchMove = (event: React.TouchEvent<HTMLDivElement>) => {
    if (touchStartXRef.current === null) return;
    const currentX = event.touches[0]?.clientX ?? touchStartXRef.current;
    const deltaX = currentX - touchStartXRef.current;
    if (deltaX >= 0) return;
    const menuWidth = menuWidthRef.current;
    const clamped = Math.max(deltaX, -menuWidth);
    setMenuTranslate(clamped);
  };

  const handleTouchEnd = () => {
    if (touchStartXRef.current === null) return;
    const menuWidth = menuWidthRef.current;
    const shouldClose = Math.abs(menuTranslate) > menuWidth * 0.35;
    if (shouldClose) {
      closeMobileMenu();
    } else {
      setMenuTranslate(0);
    }
    touchStartXRef.current = null;
  };

  const navItems = [
    { name: "Dashboard", href: "/dashboard", icon: LayoutDashboard },
    { name: "Paths", href: "/paths", icon: Folder },
    { name: "Statistics", href: "/statistics", icon: BarChart3 },
    ...(isAdmin
      ? [
          { name: "Users", href: "/admin/users", icon: Users },
          { name: "Settings", href: "/settings", icon: Settings },
        ]
      : []),
  ];

  return (
    <div className="flex h-screen w-full flex-col md:flex-row overflow-hidden bg-[#0a0a0c]">
      {/* Sidebar */}
      <aside className="hidden w-full shrink-0 border-b md:flex md:w-64 md:flex-col md:border-b-0 md:border-r border-slate-800/50 bg-slate-900/40 backdrop-blur-xl z-20">
        <div className="flex h-14 items-center border-b border-slate-800/50 px-4 lg:h-[60px] lg:px-6">
          <Link to="/" className="flex items-center gap-2 font-bold group">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20 group-hover:shadow-blue-500/40 transition-all duration-300">
              <UploadCloud className="h-5 w-5 text-white" />
            </div>
            <span className="text-xl tracking-tight bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
              Subro
            </span>
          </Link>
        </div>
        <div className="flex-1 overflow-auto py-6">
          <nav className="grid items-start px-3 text-sm font-medium space-y-1">
            {navItems.map((item) => {
              const isActive = location.pathname === item.href;
              return (
                <Link
                  key={item.href}
                  to={item.href}
                  className={cn(
                    "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-300 ease-apple group relative",
                    isActive
                      ? "bg-blue-500/10 text-blue-400 ring-1 ring-blue-500/20 shadow-[0_0_15px_-3px_rgba(59,130,246,0.3)]"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40",
                  )}
                >
                  <item.icon
                    className={cn(
                      "h-4 w-4 transition-transform duration-300 group-hover:scale-110",
                      isActive
                        ? "text-blue-400"
                        : "text-slate-500 group-hover:text-slate-300",
                    )}
                  />
                  {item.name}
                  {isActive && (
                    <div className="absolute left-0 w-1 h-4 bg-blue-500 rounded-r-full shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer / User Info */}
        <div className="p-3 border-t border-slate-800/50 space-y-1">
          <div className="flex items-center gap-3 px-2 py-2.5 rounded-xl bg-slate-800/30 border border-slate-700/30">
            <div className="h-8 w-8 rounded-full bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center border border-slate-600/30">
              <span className="text-[10px] font-bold text-slate-400 uppercase">
                {user?.email?.substring(0, 2)}
              </span>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-slate-200 truncate">
                {user?.email}
              </p>
              <p className="text-[10px] text-slate-500 capitalize">
                {user?.role || "User"}
              </p>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-500 hover:text-red-400 transition-colors"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
          <div className="text-[9px] text-slate-600 font-mono tracking-wider w-fit mx-auto opacity-50 hover:opacity-100 transition-opacity">
            {VERSION_DISPLAY}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden relative">
        {/* Subtle background glow */}
        <div className="absolute top-[-10%] right-[-5%] w-[40%] h-[40%] bg-blue-500/5 blur-[120px] pointer-events-none rounded-full" />
        <div className="absolute bottom-[-10%] left-[-5%] w-[30%] h-[30%] bg-indigo-500/5 blur-[100px] pointer-events-none rounded-full" />

        {/* Header */}
        <header className="flex h-14 items-center gap-4 border-b border-slate-800/50 bg-slate-900/20 backdrop-blur-md px-4 lg:height-[60px] lg:px-6 shrink-0 z-10">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden text-slate-400 hover:text-white"
              onClick={openMobileMenu}
              title="Open menu"
            >
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open menu</span>
            </Button>
          </div>
          <div className="w-full flex-1" />
        </header>

        {/* Page Content */}
        <main className="flex flex-1 flex-col overflow-auto relative p-6">
          <Outlet />
        </main>
      </div>

      {/* Mobile Menu (unchanged logic but updated theme) */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-[100] md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/60 backdrop-blur-sm transition-opacity duration-300"
            aria-label="Close menu"
            onClick={closeMobileMenu}
            style={{
              opacity:
                1 -
                Math.min(Math.abs(menuTranslate) / menuWidthRef.current, 1) *
                  0.4,
            }}
          />
          <div
            className="absolute left-0 top-0 h-full w-72 bg-slate-900/20 backdrop-blur-xl border-r border-slate-800 shadow-2xl transition-transform duration-300 ease-apple touch-pan-y"
            style={{ transform: `translateX(${menuTranslate}px)` }}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <div className="flex h-14 items-center justify-between border-b border-slate-800 px-4">
              <Link
                to="/"
                className="flex items-center gap-2 font-bold"
                onClick={closeMobileMenu}
              >
                <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center shadow-lg shadow-blue-500/20">
                  <UploadCloud className="h-4 w-4 text-white" />
                </div>
                <span className="text-lg bg-gradient-to-r from-cyan-400 to-blue-500 bg-clip-text text-transparent">
                  Subro
                </span>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                onClick={closeMobileMenu}
                title="Close menu"
                className="text-slate-400 hover:text-white"
              >
                <X className="h-5 w-5" />
                <span className="sr-only">Close menu</span>
              </Button>
            </div>
            <nav className="grid items-start px-2 py-6 text-sm font-medium space-y-1">
              {navItems.map((item) => {
                const isActive = location.pathname === item.href;
                return (
                  <Link
                    key={item.href}
                    to={item.href}
                    onClick={closeMobileMenu}
                    className={cn(
                      "flex items-center gap-4 rounded-lg px-4 py-3.5 transition-all duration-300",
                      isActive
                        ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/40",
                    )}
                  >
                    <item.icon
                      className={cn(
                        "h-5 w-5",
                        isActive ? "text-blue-400" : "text-slate-500",
                      )}
                    />
                    <span className="text-lg">{item.name}</span>
                  </Link>
                );
              })}
            </nav>

            {/* Mobile Sidebar Footer */}
            <div className="absolute bottom-0 left-0 right-0 p-3 border-t border-slate-800 bg-slate-900/80 backdrop-blur-md space-y-1.5">
              <div className="flex items-center gap-3 px-3 py-3.5 rounded-xl bg-slate-800/40 border border-slate-700/40">
                <div className="h-10 w-10 rounded-full bg-gradient-to-br from-slate-700 to-slate-800 flex items-center justify-center border border-slate-600/30">
                  <span className="text-xs font-bold text-slate-400 uppercase">
                    {user?.email?.substring(0, 2)}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-slate-200 truncate">
                    {user?.email}
                  </p>
                  <p className="text-[11px] text-slate-500 capitalize">
                    {user?.role || "User"}
                  </p>
                </div>
                <button
                  onClick={() => {
                    closeMobileMenu();
                    handleLogout();
                  }}
                  className="p-2 text-slate-500 hover:text-red-400 transition-colors"
                >
                  <LogOut className="h-5 w-5" />
                </button>
              </div>
              <div className="flex flex-col items-center opacity-40">
                <div className="text-[10px] text-slate-500 font-mono tracking-wider">
                  {VERSION_DISPLAY}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
