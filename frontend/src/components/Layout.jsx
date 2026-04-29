import { Link, useLocation } from "react-router-dom";
import { Settings, Plus } from "lucide-react";

export default function Layout({ children, onOpenKeys }) {
  const loc = useLocation();
  return (
    <div className="min-h-screen bg-white text-black flex flex-col">
      <header className="border-b border-black/10 bg-white sticky top-0 z-30" data-testid="app-header">
        <div className="max-w-[1440px] mx-auto px-6 md:px-12 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-3" data-testid="logo-link">
            <span className="w-2.5 h-2.5 bg-[#E52514] inline-block" />
            <span className="font-display text-xl font-black tracking-tight">ADS&nbsp;STUDIO</span>
            <span className="label-mono ml-2 hidden md:inline">v1.0 · byok</span>
          </Link>
          <nav className="flex items-center gap-2">
            <Link
              to="/brands/new"
              className={`hidden md:flex items-center gap-2 px-4 h-10 border border-black bg-black text-white hover:bg-[#E52514] hover:border-[#E52514] transition-colors duration-150 label-mono`}
              data-testid="new-brand-cta"
            >
              <Plus size={14} strokeWidth={1.5} /> New brand
            </Link>
            <button
              onClick={onOpenKeys}
              className="flex items-center gap-2 px-4 h-10 border border-black/20 hover:border-black transition-colors duration-150 label-mono"
              data-testid="open-keys-button"
            >
              <Settings size={14} strokeWidth={1.5} /> Keys
            </button>
          </nav>
        </div>
        {loc.pathname !== "/" && (
          <div className="max-w-[1440px] mx-auto px-6 md:px-12 h-8 flex items-center label-mono border-t border-black/5">
            <Link to="/" className="hover:text-black">/ workspace</Link>
            <span className="mx-2">·</span>
            <span className="text-black">{loc.pathname.replace("/", "")}</span>
          </div>
        )}
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-black/10 mt-24">
        <div className="max-w-[1440px] mx-auto px-6 md:px-12 py-6 flex items-center justify-between label-mono">
          <span>© Ads Studio · A creative pipeline.</span>
          <span>Claude Sonnet 4.5 + fal.ai · BYOK</span>
        </div>
      </footer>
    </div>
  );
}
