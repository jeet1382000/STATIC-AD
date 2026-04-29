import { useEffect, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { ArrowLeft, Download, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { api, keysStore } from "../lib/api";

export default function BrandDetail({ onOpenKeys }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const [brand, setBrand] = useState(null);
  const [runs, setRuns] = useState([]);
  const [generating, setGenerating] = useState(false);
  const [angle, setAngle] = useState(params.get("angle") || "");
  const autoTriggered = useRef(false);

  const load = async () => {
    const [b, r] = await Promise.all([api.getBrand(id), api.listRuns(id)]);
    setBrand(b.data);
    setRuns(r.data);
    return { brand: b.data, runs: r.data };
  };

  const onGenerate = async (angleArg) => {
    if (!keysStore.has()) {
      toast.error("Add your keys first.");
      onOpenKeys();
      return;
    }
    setGenerating(true);
    try {
      await api.generate(id, angleArg ?? angle);
      toast.success("15 creatives generated.");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  useEffect(() => {
    load().then(({ brand: b, runs: r }) => {
      if (params.get("autorun") === "1" && r.length === 0 && b?.identity && !autoTriggered.current) {
        autoTriggered.current = true;
        onGenerate(params.get("angle") || "");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  if (!brand) {
    return <div className="max-w-[1440px] mx-auto px-6 md:px-12 py-20 label-mono">Loading<span className="ascii-loader" /></div>;
  }

  const id_ = brand.identity;
  const latestRun = runs[0];

  return (
    <div className="px-12 py-12 max-w-[1280px]">
      <Link to="/" className="label-mono flex items-center gap-2 hover:text-[var(--red)] mb-8" data-testid="back-to-dashboard">
        <ArrowLeft size={14} strokeWidth={1.5} /> Back to workspace
      </Link>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 border-t border-black pt-8">
        <div className="lg:col-span-7">
          <div className="label-mono">№ {brand.id.slice(0, 6)} · brand</div>
          <h1 className="font-display-tight text-6xl md:text-7xl uppercase leading-[0.9] mt-2">{brand.name}</h1>
          <a href={brand.url.startsWith("http") ? brand.url : `https://${brand.url}`} target="_blank" rel="noreferrer" className="font-mono-tech text-sm text-neutral-500 hover:text-[var(--red)] mt-3 inline-block">
            ↗ {brand.url}
          </a>
          {brand.product_name && (
            <div className="mt-4 inline-block border border-black px-3 py-1 label-mono text-black">→ {brand.product_name}</div>
          )}
        </div>
        <div className="lg:col-span-5 flex lg:items-end lg:justify-end gap-3">
          <input
            value={angle}
            onChange={(e) => setAngle(e.target.value)}
            placeholder="Optional creative angle…"
            className="flex-1 h-12 px-4 border border-black/20 focus:border-[var(--red)] focus:outline-none font-mono-tech text-sm"
            data-testid="angle-quick-input"
          />
          <button
            onClick={() => onGenerate()}
            disabled={generating || !id_}
            className="flex items-center gap-2 px-5 h-12 bg-coral hover:bg-coral-deep text-black disabled:opacity-40 transition-colors text-sm font-medium border border-ink"
            data-testid="generate-button"
          >
            {generating ? <span>Generating<span className="ascii-loader" /></span> : <><Sparkles size={14} strokeWidth={1.5} /> Generate 15</>}
          </button>
        </div>
      </div>

      {/* Brand identity card */}
      <section className="mt-16">
        <div className="flex items-center justify-between border-b border-black pb-3 mb-6">
            <h2 className="font-display text-2xl uppercase">Brand identity</h2>
          <span className="label-mono">extracted via claude sonnet 4.5</span>
        </div>

        {!id_ ? (
          <div className="border border-dashed border-black/30 p-10 text-center label-mono">
            No identity yet. Run research from the dashboard.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-px bg-black/10 border border-soft" data-testid="brand-identity-card">
            {/* Palette */}
            <div className="md:col-span-7 bg-white p-8">
              <div className="label-mono mb-3">Palette</div>
              <div className="grid grid-cols-4 gap-px">
                {["primary", "secondary", "accent", "neutral"].map((k) => (
                  <div key={k} className="aspect-square relative" style={{ background: id_.palette[k] }}>
                    <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between">
                      <span className="font-mono-tech text-[10px] uppercase tracking-widest text-white mix-blend-difference">{k}</span>
                      <span className="font-mono-tech text-[10px] uppercase tracking-widest text-white mix-blend-difference">{id_.palette[k]}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
            {/* Fonts */}
            <div className="md:col-span-5 bg-white p-8">
              <div className="label-mono mb-3">Fonts</div>
              <div className="space-y-2">
                {id_.fonts.map((f, i) => (
                  <div key={i} className="border-b border-black/10 pb-2 flex items-baseline justify-between">
                    <span className="font-display text-2xl">{f}</span>
                    <span className="label-mono">№0{i + 1}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* Tone */}
            <div className="md:col-span-7 bg-white p-8">
              <div className="label-mono mb-3">Tone</div>
              <p className="font-display text-xl leading-snug">{id_.tone}</p>
            </div>
            {/* Photography */}
            <div className="md:col-span-5 bg-white p-8">
              <div className="label-mono mb-3">Photography direction</div>
              <p className="text-sm leading-relaxed text-neutral-700">{id_.photography_style}</p>
            </div>
            {/* Keywords */}
            <div className="md:col-span-12 bg-white p-8">
              <div className="label-mono mb-3">Keywords</div>
              <div className="flex flex-wrap gap-2">
                {id_.keywords.map((k, i) => (
                  <span key={i} className="border border-black px-3 py-1 label-mono text-black">{k}</span>
                ))}
              </div>
            </div>
          </div>
        )}
      </section>

      {/* Ad creatives grid */}
      <section className="mt-16">
        <div className="flex items-center justify-between border-b border-black pb-3 mb-6">
            <h2 className="font-display text-2xl uppercase">Ad creatives</h2>
          <div className="flex items-center gap-3">
            <span className="label-mono">{latestRun ? `${latestRun.creatives.filter(c => c.image_url).length}/${latestRun.creatives.length}` : "0/0"}</span>
            {latestRun && (
              <button onClick={() => onGenerate()} className="label-mono hover:text-[var(--red)] flex items-center gap-1" data-testid="regenerate-button">
                <RefreshCw size={12} strokeWidth={1.5} /> Regenerate
              </button>
            )}
          </div>
        </div>

        {generating && (!latestRun || latestRun.creatives.every(c => !c.image_url)) ? (
          <div className="columns-2 md:columns-3 lg:columns-4 gap-3" data-testid="ad-creatives-grid-loading">
            {Array.from({ length: 15 }).map((_, i) => {
              const aspects = ["aspect-square", "aspect-[4/5]", "aspect-[9/16]", "aspect-[16/9]", "aspect-[4/3]"];
              const a = aspects[i % aspects.length];
              return (
                <div key={i} className={`${a} bg-cream-deep border border-soft mb-3 break-inside-avoid flex items-center justify-center`}>
                  <span className="label-mono">№{String(i + 1).padStart(2, "0")} <span className="ascii-loader" /></span>
                </div>
              );
            })}
          </div>
        ) : !latestRun ? (
          <div className="border border-dashed border-black/30 p-10 text-center label-mono">
            No creatives yet. Hit Generate.
          </div>
        ) : (
          <div className="columns-2 md:columns-3 lg:columns-4 gap-3" data-testid="ad-creatives-grid">
            {latestRun.creatives.map((c, i) => {
              const aspectMap = { "1:1": "aspect-square", "4:5": "aspect-[4/5]", "9:16": "aspect-[9/16]", "16:9": "aspect-[16/9]", "4:3": "aspect-[4/3]" };
              const a = aspectMap[c.aspect] || "aspect-square";
              return (
                <div key={c.id} className={`${a} bg-white border border-soft relative group overflow-hidden mb-3 break-inside-avoid`} data-testid={`creative-${i}`}>
                  {c.image_url ? (
                    <>
                      <img src={c.image_url} alt={`Creative ${i + 1}`} className="w-full h-full object-cover" />
                      <div className="absolute top-2 left-2 bg-black text-white label-mono px-2 py-0.5">{c.aspect}</div>
                      {c.template_name && (
                        <div className="absolute top-2 right-2 bg-white/90 label-mono px-2 py-0.5 max-w-[60%] truncate">{c.template_name}</div>
                      )}
                      <div className="absolute inset-0 bg-black/0 group-hover:bg-black/70 transition-colors duration-150 p-4 flex flex-col justify-between opacity-0 group-hover:opacity-100">
                        <span className="font-mono-tech text-[10px] uppercase tracking-widest text-white">№{String(i + 1).padStart(2, "0")} · {c.template_name || "free"}</span>
                        <p className="text-white text-xs leading-relaxed line-clamp-6">{c.prompt}</p>
                        <a href={c.image_url} target="_blank" rel="noreferrer" download className="self-start flex items-center gap-1 label-mono text-white hover:text-[var(--red)]">
                          <Download size={12} strokeWidth={1.5} /> Download
                        </a>
                      </div>
                    </>
                  ) : (
                    <div className="w-full h-full flex flex-col items-center justify-center p-4 text-center">
                      <span className="label-mono mb-2">№{String(i + 1).padStart(2, "0")} · {c.aspect}</span>
                      <span className="text-xs text-[var(--red)] font-mono-tech">{c.error || "no image"}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {runs.length > 1 && (
          <div className="mt-8 label-mono">
            {runs.length} previous runs in history.
          </div>
        )}
      </section>
    </div>
  );
}
