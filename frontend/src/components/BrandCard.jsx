import { Link } from "react-router-dom";
import { Trash2 } from "lucide-react";

export default function BrandCard({ brand, onDelete }) {
  const accent = brand?.identity?.palette?.accent || brand?.cover_color || "#E52514";
  const primary = brand?.identity?.palette?.primary || "#0A0A0A";
  const secondary = brand?.identity?.palette?.secondary || "#737373";
  const date = new Date(brand.created_at);
  const stamp = date.toLocaleDateString(undefined, { month: "short", day: "2-digit" }).toUpperCase();

  return (
    <div className="group border border-black/10 hover:border-black transition-colors duration-150 bg-white relative" data-testid={`brand-card-${brand.id}`}>
      <Link to={`/brands/${brand.id}`} className="block">
        <div className="aspect-[4/3] grid grid-cols-3 grid-rows-3">
          <div style={{ background: primary }} className="col-span-2 row-span-2" />
          <div style={{ background: accent }} className="col-span-1 row-span-1" />
          <div style={{ background: secondary }} className="col-span-1 row-span-2" />
          <div style={{ background: brand?.identity?.palette?.neutral || "#F5F5F5" }} className="col-span-2 row-span-1 flex items-end p-3">
            <span className="font-mono-tech text-[10px] uppercase tracking-widest text-black/60">{stamp}</span>
          </div>
        </div>
        <div className="p-5 border-t border-black/10">
          <div className="label-mono">№ {brand.id.slice(0, 6)}</div>
          <h3 className="font-display text-2xl font-bold tracking-tight mt-1">{brand.name}</h3>
          <p className="font-mono-tech text-xs text-neutral-500 truncate mt-1">{brand.url}</p>
          {brand.identity?.tone && (
            <p className="text-sm leading-snug text-neutral-700 mt-3 line-clamp-2">{brand.identity.tone}</p>
          )}
        </div>
      </Link>
      <button
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); onDelete(brand.id); }}
        className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 bg-white border border-black/20 hover:border-[#E52514] hover:text-[#E52514] p-2 transition-all"
        title="Delete"
        data-testid={`delete-brand-${brand.id}`}
      >
        <Trash2 size={14} strokeWidth={1.5} />
      </button>
    </div>
  );
}
