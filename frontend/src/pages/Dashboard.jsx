import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import DropUrlInput from "../components/DropUrlInput";
import BrandCard from "../components/BrandCard";
import { api, keysStore } from "../lib/api";

export default function Dashboard({ onOpenKeys }) {
  const [brands, setBrands] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState("recent");
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.listBrands();
      setBrands(r.data);
    } catch {
      toast.error("Failed to load brands");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const onDrop = async (url) => {
    if (!keysStore.has()) {
      toast.error("Add your FAL & Anthropic keys first.");
      onOpenKeys();
      return;
    }
    setBusy(true);
    try {
      const host = url.replace(/^https?:\/\//, "").split("/")[0].split(".").slice(-2)[0] || "Untitled";
      const name = host.charAt(0).toUpperCase() + host.slice(1);
      const created = await api.createBrand({ name, url });
      toast.success("Brand created — running research…");
      await api.research(created.data.id);
      toast.success("Identity extracted. Generating 15 ads…");
      navigate(`/brands/${created.data.id}?autorun=1`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pipeline failed");
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id) => {
    try {
      await api.deleteBrand(id);
      setBrands((b) => b.filter((x) => x.id !== id));
      toast.success("Brand deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  const sorted = [...brands].sort((a, b) =>
    sort === "name" ? a.name.localeCompare(b.name) : b.created_at.localeCompare(a.created_at)
  );

  return (
    <div className="px-12 py-12 max-w-[1280px]">
      <div className="label-mono mb-3">Workspace · brands</div>
      <h1 className="font-display-tight text-7xl lg:text-8xl uppercase leading-[0.85]">
        Static Ad<br/>Studio<span className="text-[var(--red)]">.</span>
      </h1>
      <p className="text-base text-black/70 mt-6 max-w-2xl leading-relaxed">
        Reverse-engineer any brand. Ship ads at agency volume. Drop a URL — research,
        brand DNA, prompt-pack, and 15 production-ready static ads.
      </p>

      <div className="mt-10 max-w-3xl">
        <DropUrlInput onSubmit={onDrop} busy={busy} />
      </div>

      <div className="mt-16 border-t border-ink pt-6 flex items-end justify-between mb-6">
        <div className="flex items-baseline gap-3">
          <h2 className="font-display text-2xl uppercase">Your workspaces</h2>
          <span className="label-mono" data-testid="brands-count">{brands.length}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="label-mono">Sort ·</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="label-mono bg-transparent border-b border-black/30 hover:border-black focus:outline-none px-1"
            data-testid="sort-select"
          >
            <option value="recent">recent</option>
            <option value="name">name</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="label-mono py-24 text-center">Loading<span className="ascii-loader" /></div>
      ) : sorted.length === 0 ? (
        <div className="border border-soft bg-white p-12 grid grid-cols-1 md:grid-cols-12 gap-8 items-center" data-testid="empty-state">
          <div className="md:col-span-7">
            <div className="label-mono mb-3">Empty</div>
            <h3 className="font-display-tight text-5xl uppercase leading-none">No brands yet.</h3>
            <p className="text-black/60 mt-4 max-w-md leading-relaxed">
              Drop a URL above. The agent reverse-engineers the whole visual identity — fonts, palette, photography direction — then generates 15 static ad creatives. Fully automatic.
            </p>
            <button onClick={() => navigate("/brands/new")} className="label-mono text-coral hover:text-[var(--red)] mt-4 underline" data-testid="open-wizard-cta">
              Or use the full wizard →
            </button>
          </div>
          <div className="md:col-span-5 aspect-[4/5] bg-cream-deep relative overflow-hidden">
            <img
              src="https://images.unsplash.com/photo-1629922944655-a4c0ae9e07f1?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NjV8MHwxfHNlYXJjaHwxfHxtaW5pbWFsaXN0JTIwZWRpdG9yaWFsJTIwZmFzaGlvbiUyMHBob3RvZ3JhcGh5fGVufDB8fHx8MTc3NzQ0MTkxNXww&ixlib=rb-4.1.0&q=85"
              alt=""
              className="absolute inset-0 w-full h-full object-cover opacity-90 mix-blend-luminosity"
            />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5" data-testid="brands-grid">
          {sorted.map((b, i) => (
            <BrandCard key={b.id} brand={b} index={i} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
