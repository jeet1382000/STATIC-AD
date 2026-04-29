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
    } catch (e) {
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
    <div className="max-w-[1440px] mx-auto px-6 md:px-12 py-12 md:py-20">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 mb-16">
        <div className="lg:col-span-7">
          <div className="label-mono mb-4">№00 · workspace</div>
          <h1 className="font-display text-5xl md:text-7xl lg:text-8xl font-black tracking-tighter leading-[0.9]">
            Your<br/>workspaces<span className="text-[#E52514]">.</span>
          </h1>
          <p className="text-base md:text-lg text-neutral-700 mt-6 max-w-xl leading-relaxed">
            Drop a URL. The agent reverse-engineers the brand's visual identity — palette,
            fonts, photography direction — then generates 15 static ad creatives. Fully automatic.
          </p>
        </div>
        <div className="lg:col-span-5 flex flex-col justify-end">
          <DropUrlInput onSubmit={onDrop} busy={busy} />
        </div>
      </div>

      <div className="flex items-end justify-between border-t border-black pt-6 mb-8">
        <div className="flex items-baseline gap-4">
          <h2 className="font-display text-2xl font-bold tracking-tight">Brands</h2>
          <span className="label-mono" data-testid="brands-count">{brands.length} total</span>
        </div>
        <div className="flex items-center gap-3">
          <span className="label-mono">sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="label-mono bg-transparent border-b border-black/30 hover:border-black focus:outline-none px-1"
            data-testid="sort-select"
          >
            <option value="recent">recent</option>
            <option value="name">name</option>
          </select>
          <button
            onClick={() => navigate("/brands/new")}
            className="label-mono ml-3 hover:text-[#E52514]"
            data-testid="open-wizard-button"
          >
            Or use the full wizard →
          </button>
        </div>
      </div>

      {loading ? (
        <div className="label-mono py-24 text-center">Loading<span className="ascii-loader" /></div>
      ) : sorted.length === 0 ? (
        <div className="border border-black/10 p-12 md:p-20 grid grid-cols-1 md:grid-cols-2 gap-12 items-center" data-testid="empty-state">
          <div>
            <div className="label-mono mb-3">Empty</div>
            <h3 className="font-display text-4xl md:text-5xl font-black tracking-tighter leading-none">
              No brands yet.
            </h3>
            <p className="text-neutral-600 mt-4 max-w-md leading-relaxed">
              Drop a URL above. The agent does the rest.
            </p>
          </div>
          <div className="aspect-[4/3] bg-black relative overflow-hidden">
            <img
              src="https://images.unsplash.com/photo-1629922944655-a4c0ae9e07f1?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjY2NjV8MHwxfHNlYXJjaHwxfHxtaW5pbWFsaXN0JTIwZWRpdG9yaWFsJTIwZmFzaGlvbiUyMHBob3RvZ3JhcGh5fGVufDB8fHx8MTc3NzQ0MTkxNXww&ixlib=rb-4.1.0&q=85"
              alt=""
              className="absolute inset-0 w-full h-full object-cover opacity-90 mix-blend-luminosity"
            />
            <div className="absolute bottom-3 left-3 label-mono text-white">/ untitled · 00</div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="brands-grid">
          {sorted.map((b) => (
            <BrandCard key={b.id} brand={b} onDelete={onDelete} />
          ))}
        </div>
      )}
    </div>
  );
}
