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
    <div className="flex h-screen w-full flex-col md:flex-row overflow-hidden">
      {/* Sidebar */}
      <aside className="hidden w-full shrink-0 border-b md:flex md:w-64 md:flex-col md:border-b-0 md:border-r bg-muted/20">
        <div className="flex h-14 items-center border-b px-4 lg:h-[60px] lg:px-6">
          <Link to="/" className="flex items-center gap-2 font-semibold">
            <UploadCloud className="h-6 w-6" />
            <span className="">Subro</span>
          </Link>
        </div>
        <div className="flex-1 overflow-auto py-2">
          <nav className="grid items-start px-2 text-sm font-medium lg:px-4">
            {navItems.map((item) => (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 transition-all duration-300 ease-apple hover:text-primary",
                  location.pathname === item.href
                    ? "bg-muted text-primary"
                    : "text-muted-foreground",
                )}
              >
                <item.icon className="h-4 w-4" />
                {item.name}
              </Link>
            ))}
          </nav>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center gap-4 border-b bg-muted/40 px-4 lg:h-[60px] lg:px-6">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={openMobileMenu}
              title="Open menu"
            >
              <Menu className="h-5 w-5" />
              <span className="sr-only">Open menu</span>
            </Button>
          </div>
          <div className="w-full flex-1" />
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium hidden sm:inline-block">
              {user?.email}
            </span>
            <Button
              variant="ghost"
              size="icon"
              className="rounded-full"
              onClick={handleLogout}
              title="Logout"
            >
              <LogOut className="h-5 w-5" />
              <span className="sr-only">Logout</span>
            </Button>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex flex-1 flex-col gap-4 p-4 lg:gap-6 lg:p-6 overflow-auto">
          <Outlet />
        </main>
      </div>

      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/50 transition-opacity duration-200"
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
            className="absolute left-0 top-0 h-full w-72 bg-muted/95 border-r shadow-xl transition-transform duration-200 ease-out touch-pan-y"
            style={{ transform: `translateX(${menuTranslate}px)` }}
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <div className="flex h-14 items-center justify-between border-b px-4">
              <Link
                to="/"
                className="flex items-center gap-2 font-semibold"
                onClick={closeMobileMenu}
              >
                <UploadCloud className="h-6 w-6" />
                <span>Subro</span>
              </Link>
              <Button
                variant="ghost"
                size="icon"
                onClick={closeMobileMenu}
                title="Close menu"
              >
                <X className="h-5 w-5" />
                <span className="sr-only">Close menu</span>
              </Button>
            </div>
            <nav className="grid items-start px-2 py-2 text-3xl font-medium">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  to={item.href}
                  onClick={closeMobileMenu}
                  className={cn(
                    "flex items-center gap-4 rounded-lg px-4 py-4 text-3xl leading-snug transition-all duration-300 ease-apple hover:text-primary",
                    location.pathname === item.href
                      ? "bg-muted text-primary"
                      : "text-muted-foreground",
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  {item.name}
                </Link>
              ))}
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}
