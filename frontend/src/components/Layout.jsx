import { Link, NavLink, useLocation } from "react-router-dom";
import { LayoutGrid, Plus, Settings, KeyRound, LayoutTemplate } from "lucide-react";
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
  ];

  return (
    <div className="min-h-screen bg-cream text-black flex">
      {/* Sidebar */}
      <aside className="w-[240px] shrink-0 border-r border-soft min-h-screen flex flex-col sticky top-0 h-screen" data-testid="sidebar">
        <div className="px-6 pt-6 pb-8 border-b border-soft">
          <Link to="/" className="block" data-testid="logo-link">
            <div className="flex items-center gap-2">
              <span className="font-display text-3xl tracking-tight">STATIC</span>
              <span className="bg-ink text-white label-mono px-1.5 py-0.5">AD</span>
            </div>
            <div className="label-mono mt-1">Studio · v1.0</div>
          </Link>
        </div>

        <nav className="flex-1 px-3 py-4 space-y-1">
          {nav.map((n) => {
            const Active = n.end ? loc.pathname === n.to : loc.pathname.startsWith(n.to);
            const Icon = n.icon;
            return (
              <NavLink
                key={n.to}
                to={n.to}
                className={`flex items-center gap-3 h-10 px-3 transition-colors duration-150 ${
                  Active ? "bg-ink text-white" : "text-black/80 hover:bg-cream-deep"
                }`}
                data-testid={`nav-${n.label.toLowerCase().replace(/\s/g, "-")}`}
              >
                <Icon size={16} strokeWidth={1.5} />
                <span className="text-sm">{n.label}</span>
              </NavLink>
            );
          })}
          <button
            onClick={onOpenKeys}
            className="w-full flex items-center gap-3 h-10 px-3 text-black/80 hover:bg-cream-deep text-sm"
            data-testid="nav-settings"
          >
            <Settings size={16} strokeWidth={1.5} />
            Settings
          </button>
        </nav>

        <div className="px-4 pb-4">
          <button
            onClick={onOpenKeys}
            className="w-full flex items-center gap-2 px-3 py-2.5 border border-soft hover:border-ink bg-white transition-colors"
            data-testid="keys-status-button"
          >
            <KeyRound size={14} strokeWidth={1.5} />
            <span className="label-mono flex-1 text-left">Your keys</span>
            <span className="label-mono flex items-center" style={{ color: hasKeys ? "#16A34A" : "rgba(0,0,0,0.4)" }}>
              <span className={`dot ${hasKeys ? "" : "gray"}`} />
              {hasKeys ? "connected" : "missing"}
            </span>
          </button>
        </div>

        <div className="px-6 py-4 border-t border-soft">
          <div className="label-mono mb-2">Stack</div>
          <ul className="space-y-1 font-mono-tech text-[11px] text-black/60">
            <li>› claude-sonnet-4-5</li>
            <li>› fal-ai / flux-schnell</li>
            <li>› fal.storage</li>
          </ul>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0">{children}</main>
    </div>
  );
}
