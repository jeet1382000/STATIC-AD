import { Link, NavLink, useLocation } from "react-router-dom";
import { LayoutGrid, Plus, Settings, KeyRound, LayoutTemplate, Images } from "lucide-react";
import { keysStore } from "../lib/api";
import { useEffect, useState } from "react";

export default function Layout({ children, onOpenKeys }) {
  const loc = useLocation();
  const [hasKeys, setHasKeys] = useState(keysStore.has());

  useEffect(() => {
    const t = setInterval(() => setHasKeys(keysStore.has()), 1000);
    return () => clearInterval(t);
  }, []);

  const nav = [
    { to: "/", label: "Brands", icon: LayoutGrid, end: true },
    { to: "/brands/new", label: "New brand", icon: Plus },
    { to: "/templates", label: "Templates", icon: LayoutTemplate },
    { to: "/settings", label: "Settings", icon: Settings },
    { to: "/gallery", label: "Gallery", icon: Images },
  ];

  return (
    <div className="min-h-screen bg-cream text-black flex">
      {/* Sidebar */}
      <aside className="w-[240px] shrink-0 border-r border-soft min-h-screen flex flex-col sticky top-0 h-screen" data-testid="sidebar">
        <div className="px-6 pt-6 pb-8 border-b border-soft">
          <Link to="/" className="block" data-testid="logo-link">
            <div className="flex items-center gap-2">
              <span className="font-display text-3xl tracking-tight">STATIC</span>
              <span className="bg-coral text-ink label-mono px-1.5 py-0.5">AD</span>
            </div>
            <div className="label-mono mt-1">STUDIO · V1.0</div>
          </Link>
        </div>

        <nav className="flex-1 py-3 space-y-0.5">
          {nav.map((n) => {
            const Active = n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to);
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={`flex items-center gap-3 h-11 px-5 transition-colors duration-150 ${
                  Active ? "bg-ink text-white" : "text-black hover:bg-cream-deep"
                }`}
                data-testid={`nav-${n.label.toLowerCase().replace(/\s/g, "-")}`}
              >
                <Icon size={18} strokeWidth={2} />
                <span className="text-base font-semibold">{n.label}</span>
              </NavLink>
            );
          })}
        </nav>

        <div className="px-4 pb-6">
          <button
            onClick={onOpenKeys}
            className="w-full flex items-center gap-2 px-3 py-3 border border-ink bg-cream hover:bg-cream-deep transition-colors"
            data-testid="keys-status-button"
          >
            <KeyRound size={15} strokeWidth={1.5} />
            <span className="label-mono flex-1 text-left">Your keys</span>
            <span className="label-mono flex items-center" style={{ color: hasKeys ? "#16A34A" : "rgba(0,0,0,0.4)" }}>
              <span className={`dot ${hasKeys ? "" : "gray"}`} />
              {hasKeys ? "connected" : "missing"}
            </span>
          </button>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
