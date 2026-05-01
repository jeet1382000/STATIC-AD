import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { Images, ExternalLink } from "lucide-react";

export default function Gallery() {
  const [brands, setBrands] = useState([]);
  const [allImages, setAllImages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all"); // all | 1:1 | 4:5 | 9:16 | 16:9

  useEffect(() => {
    async function load() {
      try {
        const { data: brandList } = await api.listBrands();
        setBrands(brandList);

        const runPromises = brandList.map(async (b) => {
          try {
            const { data: runs } = await api.listRuns(b.id);
            const latest = runs[0];
            if (!latest) return [];
            return (latest.creatives || [])
              .filter((c) => c.image_url)
              .map((c) => ({ ...c, brandId: b.id, brandName: b.name }));
          } catch {
            return [];
          }
        });

        const results = await Promise.all(runPromises);
        setAllImages(results.flat());
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const aspects = ["all", "1:1", "4:5", "9:16", "16:9"];
  const filtered = filter === "all" ? allImages : allImages.filter((img) => img.aspect === filter);

  return (
    <div className="min-h-screen bg-cream">
      {/* Header */}
      <div className="border-b border-soft px-8 py-6 flex items-center justify-between">
        <div>
          <div className="label-mono mb-1">Global view</div>
          <h1 className="font-display text-4xl tracking-tight">GALLERY</h1>
        </div>
        <div className="flex items-center gap-1">
          {aspects.map((a) => (
            <button
              key={a}
              onClick={() => setFilter(a)}
              className={`label-mono px-3 py-1.5 border transition-colors ${
                filter === a
                  ? "bg-ink text-white border-ink"
                  : "border-soft hover:border-ink bg-cream"
              }`}
            >
              {a === "all" ? "ALL" : a}
            </button>
          ))}
        </div>
      </div>

      <div className="px-8 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-32 label-mono text-black/40">
            <span className="ascii-loader mr-2" /> Loading gallery…
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-32 text-center">
            <Images size={48} strokeWidth={1} className="text-black/20 mb-4" />
            <p className="font-display text-2xl tracking-tight text-black/30">NO IMAGES YET.</p>
            <p className="label-mono mt-2 text-black/30">
              {allImages.length === 0
                ? "Generate ads for a brand to see them here."
                : `No images match the "${filter}" aspect ratio filter.`}
            </p>
            {brands.length === 0 && (
              <Link
                to="/brands/new"
                className="mt-6 bg-ink text-white label-mono px-5 py-2.5 hover:bg-black/80 transition-colors"
              >
                + ADD YOUR FIRST BRAND
              </Link>
            )}
          </div>
        ) : (
          <>
            <div className="label-mono mb-4 text-black/40">
              {filtered.length} IMAGE{filtered.length !== 1 ? "S" : ""}
              {filter !== "all" && ` · ${filter}`}
            </div>
            <div className="columns-2 sm:columns-3 lg:columns-4 xl:columns-5 gap-3 space-y-3">
              {filtered.map((img) => (
                <GalleryItem key={img.id} img={img} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

function GalleryItem({ img }) {
  const [hover, setHover] = useState(false);

  return (
    <div
      className="relative break-inside-avoid group overflow-hidden border border-soft"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <img
        src={img.image_url}
        alt={img.template_name || "Ad creative"}
        className="w-full block object-cover"
        loading="lazy"
      />
      {hover && (
        <div className="absolute inset-0 bg-ink/80 flex flex-col justify-between p-3 transition-opacity">
          <div>
            {img.template_name && (
              <span className="label-mono text-white/80 text-[10px]">{img.template_name}</span>
            )}
            <p className="text-white text-xs mt-1 line-clamp-3 font-mono-tech leading-snug">
              {img.prompt}
            </p>
          </div>
          <div className="flex items-center justify-between mt-2">
            <Link
              to={`/brands/${img.brandId}`}
              className="label-mono text-white/60 hover:text-white text-[10px] transition-colors"
            >
              {img.brandName}
            </Link>
            <a
              href={img.image_url}
              target="_blank"
              rel="noreferrer"
              className="text-white/60 hover:text-white transition-colors"
              title="Open full size"
            >
              <ExternalLink size={12} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
