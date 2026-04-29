import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";

function statusOf(brand) {
  if (brand.done_ads > 0 && brand.done_ads === brand.total_ads) return { label: "DONE", color: "#16A34A" };
  if (brand.total_ads > 0 && brand.done_ads < brand.total_ads) return { label: "PARTIAL", color: "#D97706" };
  if (brand.identity) return { label: "READY", color: "rgba(0,0,0,0.55)" };
  return { label: "PENDING", color: "rgba(0,0,0,0.4)" };
}

export default function BrandCard({ brand, index, onDelete }) {
  const status = statusOf(brand);
  const num = `№${String(index + 1).padStart(2, "0")}`;
  const cleanUrl = brand.url.replace(/^https?:\/\//, "");
  const thumbs = (brand.thumb_urls || []).slice(0, 3);
  const palette = brand.identity?.palette;
  const fallbackTiles = palette
    ? [palette.primary, palette.accent, palette.secondary]
    : ["#ECE6D7", "#ECE6D7", "#ECE6D7"];

  return (
    <div className="group bg-cream border border-ink hover:bg-white transition-colors duration-150 relative" data-testid={`brand-card-${brand.id}`}>
      <Link to={`/brands/${brand.id}`} className="block">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-3 border-b border-ink/15">
          <span className="font-mono-tech text-sm text-black/70">{num}</span>
          <span className="font-mono-tech text-sm flex items-center" style={{ color: status.color }}>
            <span className="dot" style={{ background: status.color }} />
            {status.label}
          </span>
        </div>

        {/* Name + URL */}
        <div className="px-6 pt-7 pb-6 border-b border-ink/15">
          <h3 className="font-display-tight text-5xl uppercase leading-none">{brand.name}</h3>
          <p className="font-mono-tech text-sm text-black/55 mt-3">{cleanUrl}</p>
        </div>

        {/* Thumbnail strip */}
        <div className="px-0">
          <div className="grid grid-cols-3 gap-px bg-ink/10 border-b border-ink/15">
            {thumbs.length > 0
              ? thumbs.map((src, i) => (
                  <div key={i} className="aspect-[4/5] bg-white overflow-hidden">
                    <img src={src} alt="" className="w-full h-full object-cover" loading="lazy" />
                  </div>
                ))
              : fallbackTiles.map((bg, i) => (
                  <div key={i} className="aspect-[4/5] flex items-center justify-center" style={{ background: bg }}>
                    <span className="text-white/60 text-xs mix-blend-difference font-mono-tech uppercase tracking-widest">empty</span>
                  </div>
                ))}
          </div>
        </div>

        {/* Footer */}
        <div className="grid grid-cols-3 items-center px-6 py-3">
          <span className="font-mono-tech text-sm text-black/70">
            {brand.done_ads}/{brand.total_ads || "0"} ads
          </span>
          <span className="font-mono-tech text-sm text-[var(--red)] text-center">
            ${(brand.cost || 0).toFixed(2)}
          </span>
          <span className="font-mono-tech text-sm text-right">Open →</span>
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
