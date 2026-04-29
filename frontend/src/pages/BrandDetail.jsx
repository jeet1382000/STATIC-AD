import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, useSearchParams, Link } from "react-router-dom";
import { ArrowLeft, Download, RefreshCw, Sparkles, FileJson, ChevronDown } from "lucide-react";
import { toast } from "sonner";
import { api, keysStore } from "../lib/api";

const COST_PER_IMAGE = 0.003; // fal flux/schnell rough estimate

export default function BrandDetail({ onOpenKeys }) {
  const { id } = useParams();
  const [params] = useSearchParams();
  const [brand, setBrand] = useState(null);
  const [runs, setRuns] = useState([]);
  const [tab, setTab] = useState("dna");
  const [generating, setGenerating] = useState(false);
  const [phaseMsg, setPhaseMsg] = useState("");
  const [angle, setAngle] = useState(params.get("angle") || "");
  const [expanded, setExpanded] = useState({});
  const autoTriggered = useRef(false);
  const logRef = useRef([]);
  const [, forceTick] = useState(0);

  const log = (msg) => { logRef.current = [...logRef.current, { t: new Date(), msg }]; forceTick((x) => x + 1); };

  const load = async () => {
    const [b, r] = await Promise.all([api.getBrand(id), api.listRuns(id)]);
    setBrand(b.data);
    setRuns(r.data);
    return { brand: b.data, runs: r.data };
  };

  const onResearch = async () => {
    if (!keysStore.has()) { toast.error("Add your keys first."); onOpenKeys(); return; }
    setGenerating(true);
    setPhaseMsg("Researching brand…");
    log("№01 Research started — scraping site & extracting brand DNA");
    try {
      await api.research(id);
      log("№01 Research complete");
      await load();
      toast.success("Brand DNA extracted");
    } catch (e) {
      log(`× Research failed: ${e?.response?.data?.detail || e.message}`);
      toast.error(e?.response?.data?.detail || "Research failed");
    } finally {
      setGenerating(false);
      setPhaseMsg("");
    }
  };

  const onGenerate = async (angleArg) => {
    if (!keysStore.has()) { toast.error("Add your keys first."); onOpenKeys(); return; }
    setGenerating(true);
    try {
      log("№02 Prompts — Claude generating filled prompts");
      log("№03 Images — fal.ai rendering creatives in parallel");
      setPhaseMsg("Generating prompts & rendering images…");
      await api.generate(id, angleArg ?? angle);
      log("✓ All done. Ready to download.");
      toast.success("Creatives generated.");
      await load();
    } catch (e) {
      log(`× Generation failed: ${e?.response?.data?.detail || e.message}`);
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally {
      setGenerating(false);
      setPhaseMsg("");
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

  const latestRun = runs[0];
  const totalImages = latestRun?.creatives?.length || 0;
  const renderedImages = latestRun?.creatives?.filter((c) => c.image_url).length || 0;
  const phases = useMemo(() => ({
    research: !!brand?.identity,
    prompts: totalImages > 0,
    images: totalImages > 0 && renderedImages === totalImages,
  }), [brand, totalImages, renderedImages]);

  const allDone = phases.research && phases.prompts && phases.images && totalImages > 0;
  const cost = (renderedImages * COST_PER_IMAGE).toFixed(2);

  if (!brand) {
    return <div className="px-12 py-20 label-mono">Loading<span className="ascii-loader" /></div>;
  }

  const cleanUrl = brand.url.replace(/^https?:\/\//, "");
  const tabs = [
    { id: "dna", label: "Brand DNA" },
    { id: "prompts", label: `Prompts (${totalImages})` },
    { id: "gallery", label: `Gallery (${renderedImages})` },
  ];

  return (
    <div className="flex flex-col min-h-screen">
      {/* Top bar */}
      <header className="border-b border-soft sticky top-0 bg-cream z-20">
        <div className="px-6 md:px-10 py-4 flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 hover:text-[var(--red)]" data-testid="back-to-dashboard">
            <ArrowLeft size={16} strokeWidth={1.5} />
          </Link>
          <div className="flex-1 min-w-0">
            <h1 className="font-display-tight text-2xl md:text-3xl uppercase leading-none truncate">{brand.name}</h1>
            <a href={brand.url.startsWith("http") ? brand.url : `https://${brand.url}`} target="_blank" rel="noreferrer"
               className="font-mono-tech text-xs text-black/55 hover:text-[var(--red)]">{cleanUrl}</a>
          </div>
          <div className="flex items-center gap-4">
            <span className="label-mono flex items-center" style={{ color: allDone ? "#16A34A" : "rgba(0,0,0,0.5)" }} data-testid="brand-status">
              <span className="dot" style={{ background: allDone ? "#16A34A" : "rgba(0,0,0,0.4)" }} />
              {allDone ? "All done" : (generating ? "Running" : "Ready")}
            </span>
            <span className="label-mono">Cost <span className="text-[var(--red)] font-mono-tech">${cost}</span></span>
            {!phases.research && (
              <button onClick={onResearch} disabled={generating} className="px-4 h-10 border border-ink hover:bg-ink hover:text-white text-sm transition-colors disabled:opacity-40" data-testid="research-button">
                {generating ? <span>Running<span className="ascii-loader" /></span> : "Run research"}
              </button>
            )}
            {phases.research && (
              <>
                <input
                  value={angle}
                  onChange={(e) => setAngle(e.target.value)}
                  placeholder="Optional angle…"
                  className="h-10 px-3 border border-soft hover:border-ink focus:border-[var(--red)] focus:outline-none text-sm font-mono-tech w-40 hidden md:block"
                  data-testid="angle-input"
                />
                <button onClick={() => onGenerate()} disabled={generating} className="flex items-center gap-2 px-4 h-10 bg-[var(--red)] hover:bg-black text-white text-sm font-medium disabled:opacity-40 transition-colors" data-testid="generate-button">
                  {generating ? <span>Running<span className="ascii-loader" /></span> : <><Sparkles size={14} strokeWidth={1.75} /> Run pipeline</>}
                </button>
              </>
            )}
            <a
              href={renderedImages > 0 ? api.downloadZipUrl(id) : "#"}
              onClick={(e) => { if (renderedImages === 0) { e.preventDefault(); toast.error("No images to download"); } }}
              className={`flex items-center gap-2 px-5 h-10 text-sm font-medium transition-colors ${
                renderedImages > 0 ? "bg-[var(--red)] hover:bg-black text-white" : "bg-black/10 text-black/30 cursor-not-allowed"
              }`}
              data-testid="zip-download-button"
            >
              <Download size={14} strokeWidth={1.75} /> ZIP
            </a>
          </div>
        </div>

        {/* Phase indicators */}
        <div className="px-6 md:px-10 pb-3 flex items-center gap-3">
          <PhaseChip n="01" label="Research" done={phases.research} active={generating && !phases.research} />
          <PhaseChip n="02" label="Prompts" done={phases.prompts} active={generating && phases.research && !phases.prompts} />
          <PhaseChip n="03" label="Images" done={phases.images} active={generating && phases.prompts && !phases.images} />
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-px bg-black/5 border-t border-soft">
        {/* LEFT: activity log */}
        <section className="bg-cream relative flex flex-col min-h-[400px]" data-testid="activity-log-panel">
          <div className="flex-1 px-8 py-8 overflow-y-auto">
            {logRef.current.length === 0 ? (
              <div className="italic text-black/40 text-sm">Awaiting agent activity…</div>
            ) : (
              <div className="space-y-2 font-mono-tech text-xs">
                {logRef.current.map((l, i) => (
                  <div key={i} className="flex gap-3">
                    <span className="text-black/40 shrink-0">{l.t.toLocaleTimeString().slice(0, 8)}</span>
                    <span className={l.msg.startsWith("×") ? "text-[var(--red)]" : "text-black/85"}>{l.msg}</span>
                  </div>
                ))}
                {generating && <div className="flex items-center gap-2 text-black/55"><span className="ascii-loader" /> {phaseMsg}</div>}
              </div>
            )}
          </div>
        </section>

        {/* RIGHT: tabbed panel */}
        <section className="bg-cream min-h-[400px]" data-testid="tabbed-panel">
          {/* Tabs */}
          <div className="flex items-center px-8 pt-6 gap-8 border-b border-soft">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`pb-3 text-sm font-medium border-b-2 -mb-px transition-colors ${
                  tab === t.id ? "border-ink text-black" : "border-transparent text-black/45 hover:text-black"
                }`}
                data-testid={`tab-${t.id}`}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="px-8 py-8">
            {tab === "dna" && <BrandDNAView brand={brand} onRegenerate={onResearch} busy={generating} />}
            {tab === "prompts" && <PromptsView run={latestRun} expanded={expanded} setExpanded={setExpanded} onRegenerate={() => onGenerate()} busy={generating} />}
            {tab === "gallery" && <GalleryView run={latestRun} />}
          </div>
        </section>
      </div>
    </div>
  );
}

function PhaseChip({ n, label, done, active }) {
  const cls = done
    ? "bg-ink text-white border-ink"
    : active
    ? "bg-white border-ink text-black"
    : "bg-white border-soft text-black/40";
  return (
    <div className={`flex items-center gap-2 border px-3 h-8 ${cls}`} data-testid={`phase-${n}`}>
      <span className="font-mono-tech text-xs">№{n}</span>
      <span className="font-mono-tech text-xs uppercase tracking-widest">{label}</span>
      {active && <span className="ascii-loader text-xs" />}
    </div>
  );
}

// ===================== Brand DNA =====================
function BrandDNAView({ brand, onRegenerate, busy }) {
  const id_ = brand.identity;
  if (!id_) {
    return (
      <div className="border border-dashed border-black/30 p-10 text-center label-mono">
        No brand DNA yet. Hit "Run research".
      </div>
    );
  }
  const ov = id_.brand_overview || {};
  const vs = id_.visual_system || {};
  const pd_ = id_.photography_direction || {};
  const prod = id_.product_details || {};
  const ad = id_.ad_creative_style || {};
  const modifier = id_.image_generation_modifier || "";

  return (
    <div className="space-y-6" data-testid="brand-dna">
      <div className="flex items-center justify-between">
        <span className="label-mono">BRAND-DNA.MD <span className="text-black/35 ml-1">v1</span></span>
        <button onClick={onRegenerate} disabled={busy} className="flex items-center gap-1 label-mono hover:text-[var(--red)] disabled:opacity-40" data-testid="regenerate-dna">
          <RefreshCw size={12} strokeWidth={1.5} /> Regenerate
        </button>
      </div>

      <h2 className="font-display-tight text-4xl md:text-5xl uppercase leading-none">Brand DNA Document</h2>

      <Section title="Brand overview">
        <Row k="Name" v={brand.name} />
        <Row k="Tagline" v={ov.tagline} />
        <Row k="Design Agency" v={ov.design_agency} />
        <Row k="Voice Adjectives (5)" v={(ov.voice_adjectives || []).join(", ")} />
        <Row k="Positioning" v={ov.positioning} />
        <Row k="Competitive Differentiation" v={ov.competitive_differentiation} />
      </Section>

      <Section title="Visual system">
        <Row k="Primary Font" v={vs.primary_font} />
        <Row k="Secondary Font" v={vs.secondary_font} />
        <Row k="Primary Color" v={vs.primary_color} swatch={id_.palette?.primary} />
        <Row k="Secondary Color" v={vs.secondary_color} swatch={id_.palette?.secondary} />
        <Row k="Accent Color" v={vs.accent_color} swatch={id_.palette?.accent} />
        <Row k="Background Colors" v={vs.background_colors} />
        <Row k="CTA Color and Style" v={vs.cta_color_and_style} />
      </Section>

      <Section title="Photography direction">
        <Row k="Lighting" v={pd_.lighting} />
        <Row k="Color Grading" v={pd_.color_grading} />
        <Row k="Composition" v={pd_.composition} />
        <Row k="Subject Matter" v={pd_.subject_matter} />
        <Row k="Props and Surfaces" v={pd_.props_and_surfaces} />
        <Row k="Mood" v={pd_.mood} />
      </Section>

      <Section title="Product details">
        <Row k="Physical Description" v={prod.physical_description} />
        <Row k="Label / Logo Placement" v={prod.label_logo_placement} />
        <Row k="Distinctive Features" v={prod.distinctive_features} />
        <Row k="Packaging System" v={prod.packaging_system} />
      </Section>

      <Section title="Ad creative style">
        <Row k="Typical formats" v={ad.typical_formats} />
        <Row k="Text overlay style" v={ad.text_overlay_style} />
        <Row k="Photo vs illustration" v={ad.photo_vs_illustration} />
        <Row k="UGC usage" v={ad.ugc_usage} />
        <Row k="Offer presentation" v={ad.offer_presentation} />
      </Section>

      {modifier && (
        <Section title="Image generation prompt modifier">
          <p className="text-base leading-relaxed text-black/85">{modifier}</p>
          <p className="label-mono mt-3 text-black/50">Prompt modifier — prepended to every ad</p>
          <p className="text-base leading-relaxed text-black/75 mt-1">{modifier}</p>
        </Section>
      )}
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div>
      <h3 className="font-display text-xl uppercase mt-6 mb-2">{title}</h3>
      <div className="space-y-1.5 pl-4 border-l-2 border-black/10">{children}</div>
    </div>
  );
}

function Row({ k, v, swatch }) {
  if (!v) return null;
  return (
    <div className="text-base leading-relaxed">
      <span className="font-medium">{k}:</span>{" "}
      {swatch && <span className="inline-block w-3 h-3 align-middle mr-1.5 border border-black/20" style={{ background: swatch }} />}
      <span className="text-black/85">{v}</span>
    </div>
  );
}

// ===================== Prompts =====================
function PromptsView({ run, expanded, setExpanded, onRegenerate, busy }) {
  if (!run || !run.creatives?.length) {
    return (
      <div className="border border-dashed border-black/30 p-10 text-center label-mono">
        No prompts yet. Hit "Run pipeline".
      </div>
    );
  }
  const exportJson = () => {
    const data = run.creatives.map((c, i) => ({
      number: i + 1, template: c.template_name, aspect: c.aspect, prompt: c.prompt,
    }));
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a"); a.href = url; a.download = `prompts.json`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-3" data-testid="prompts-list">
      <div className="flex items-center justify-between">
        <span className="label-mono">{run.creatives.length} filled prompts</span>
        <div className="flex items-center gap-4">
          <button onClick={exportJson} className="flex items-center gap-1 label-mono hover:text-[var(--red)]" data-testid="export-json">
            <FileJson size={12} strokeWidth={1.5} /> Export.json
          </button>
          <button onClick={onRegenerate} disabled={busy} className="flex items-center gap-1 label-mono hover:text-[var(--red)] disabled:opacity-40" data-testid="regenerate-prompts">
            <RefreshCw size={12} strokeWidth={1.5} /> Regenerate
          </button>
        </div>
      </div>
      <div className="space-y-2">
        {run.creatives.map((c, i) => {
          const open = !!expanded[c.id];
          return (
            <div key={c.id} className="bg-white border border-soft" data-testid={`prompt-row-${i}`}>
              <button
                onClick={() => setExpanded({ ...expanded, [c.id]: !open })}
                className="w-full flex items-center px-5 py-3 gap-4 hover:bg-cream-deep transition-colors"
              >
                <span className="font-mono-tech text-xs text-[var(--red)] w-12">#{String(i + 1).padStart(2, "0")}</span>
                <span className="flex-1 text-left text-base font-medium">{c.template_name || "Free-form"}</span>
                <span className="font-mono-tech text-xs border border-soft px-2 py-1">{c.aspect}</span>
                <NeedsPill needs={!!c.needs_product} />
                <ChevronDown size={14} strokeWidth={1.5} className={`transition-transform ${open ? "rotate-180" : ""}`} />
              </button>
              {open && (
                <div className="px-5 pb-4 pt-1 text-sm leading-relaxed text-black/80 border-t border-soft bg-cream">
                  {c.prompt}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function NeedsPill({ needs }) {
  return needs ? (
    <span className="bg-[var(--red)] text-white label-mono px-2 py-1 flex items-center gap-1">
      <span className="w-1.5 h-1.5 bg-white rounded-full" /> PRODUCT
    </span>
  ) : (
    <span className="border border-soft text-black/45 label-mono px-2 py-1">TEXT ONLY</span>
  );
}

// ===================== Gallery =====================
function GalleryView({ run }) {
  if (!run || !run.creatives?.length) {
    return (
      <div className="border border-dashed border-black/30 p-10 text-center label-mono">
        No creatives yet. Hit "Run pipeline".
      </div>
    );
  }
  const done = run.creatives.filter((c) => c.image_url).length;
  return (
    <div data-testid="gallery">
      <div className="label-mono mb-4">{done}/{run.creatives.length} generated</div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {run.creatives.map((c, i) => {
          const aspectMap = { "1:1": "aspect-square", "4:5": "aspect-[4/5]", "9:16": "aspect-[9/16]", "16:9": "aspect-[16/9]", "4:3": "aspect-[4/3]" };
          const a = aspectMap[c.aspect] || "aspect-square";
          return (
            <div key={c.id} className={`${a} bg-white border border-soft relative group overflow-hidden`} data-testid={`gallery-tile-${i}`}>
              {c.image_url ? (
                <>
                  <img src={c.image_url} alt={c.template_name || `Creative ${i + 1}`} className="w-full h-full object-cover" />
                  <div className="absolute top-2 left-2 bg-black text-white label-mono px-2 py-1 max-w-[90%] truncate">
                    #{String(i + 1).padStart(2, "0")} · {c.template_name || "Free"}
                  </div>
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/70 transition-colors duration-150 p-4 flex flex-col justify-end opacity-0 group-hover:opacity-100">
                    <p className="text-white text-xs leading-relaxed line-clamp-6">{c.prompt}</p>
                    <a href={c.image_url} target="_blank" rel="noreferrer" download className="self-start mt-3 flex items-center gap-1 label-mono text-white hover:text-[var(--red)]">
                      <Download size={12} strokeWidth={1.5} /> Download
                    </a>
                  </div>
                </>
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center p-4 text-center bg-cream-deep">
                  <span className="label-mono mb-2">#{String(i + 1).padStart(2, "0")} · {c.aspect}</span>
                  <span className="text-xs text-[var(--red)] font-mono-tech">{c.error || "rendering…"}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
