import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";

function statusOf(brand) {
  if (!brand.identity) return { label: "PENDING", color: "rgba(0,0,0,0.4)" };
  return { label: "DONE", color: "#16A34A" };
}

export default function BrandCard({ brand, index, onDelete }) {
  const status = statusOf(brand);
  const palette = brand?.identity?.palette;
  const num = `№${String(index + 1).padStart(2, "0")}`;

  return (
    <div className="group bg-white border border-soft hover:border-ink transition-colors duration-150 relative" data-testid={`brand-card-${brand.id}`}>
      <Link to={`/brands/${brand.id}`} className="block">
        <div className="flex items-center justify-between px-5 py-3 border-b border-soft">
          <span className="label-mono">{num}</span>
          <span className="label-mono flex items-center" style={{ color: status.color }}>
            <span className="dot" style={{ background: status.color }} />
            {status.label}
          </span>
        </div>
        <div className="px-5 pt-5">
          <h3 className="font-display-tight text-3xl uppercase leading-none">{brand.name}</h3>
          <p className="font-mono-tech text-xs text-black/55 mt-2 truncate">{brand.url.replace(/^https?:\/\//, "")}</p>
        </div>
        <div className="px-5 pt-5 pb-5">
          {palette ? (
            <div className="grid grid-cols-4 gap-px h-24 bg-black/10 border border-soft">
              <div style={{ background: palette.primary }} />
              <div style={{ background: palette.secondary }} />
              <div style={{ background: palette.accent }} />
              <div style={{ background: palette.neutral }} />
            </div>
          ) : (
            <div className="grid grid-cols-3 gap-px h-24 bg-black/10 border border-soft">
              {[0, 1, 2].map((i) => (
                <div key={i} className="bg-cream-deep flex items-center justify-center">
                  <span className="text-black/20 text-xl">▢</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between px-5 py-3 border-t border-soft">
          <span className="label-mono">{brand.identity ? "research · ok" : "research · pending"}</span>
          <span className="label-mono text-coral">Open →</span>
        </div>
      </Link>
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(brand.id); }}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 bg-white border border-soft hover:border-[var(--red)] hover:text-[var(--red)] p-1.5 transition-all"
        title="Delete"
        data-testid={`delete-brand-${brand.id}`}
      >
        <Trash2 size={12} strokeWidth={1.5} />
      </button>
    </div>
  );
}
