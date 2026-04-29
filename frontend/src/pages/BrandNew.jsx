import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api, keysStore } from "../lib/api";

export default function BrandNew({ onOpenKeys }) {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [product, setProduct] = useState("");
  const [angle, setAngle] = useState("");
  const [busy, setBusy] = useState(false);

  const next = () => {
    if (step === 1 && (!name.trim() || !url.trim())) {
      toast.error("Brand name and URL required");
      return;
    }
    setStep(step + 1);
  };
  const back = () => setStep(Math.max(1, step - 1));

  const finish = async () => {
    if (!keysStore.has()) {
      toast.error("Add your FAL & Anthropic keys first.");
      onOpenKeys();
      return;
    }
    setBusy(true);
    try {
      const created = await api.createBrand({ name, url, product_name: product || null });
      toast.success("Brand created. Running research…");
      await api.research(created.data.id);
      toast.success("Identity extracted. Generating ads…");
      navigate(`/brands/${created.data.id}?autorun=1&angle=${encodeURIComponent(angle)}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Pipeline failed");
    } finally {
      setBusy(false);
    }
  };

  const Stepper = (
    <div className="grid grid-cols-3 gap-3 mb-10" data-testid="stepper">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex flex-col gap-1">
          <div className={`h-1 w-full ${step >= i ? "bg-[#E52514]" : "bg-black/15"}`} />
          <div className="flex items-center justify-between mt-1">
            <span className={`text-sm ${step === i ? "text-black font-medium" : "text-black/40"}`}>Step {i}</span>
            <span className="font-mono-tech text-xs text-black/50">№0{i}</span>
          </div>
        </div>
      ))}
    </div>
  );

  return (
    <div className="px-12 py-12 max-w-[920px]">
      <button onClick={() => navigate("/")} className="label-mono flex items-center gap-2 hover:text-[#E52514] mb-8" data-testid="wizard-back-link">
        <ArrowLeft size={14} strokeWidth={1.5} /> Back
      </button>

      <div className="label-mono">Brands · New</div>
      <h1 className="font-display-tight text-6xl lg:text-7xl uppercase leading-[0.9] mt-3">
        Create brand workspace<span className="text-[#E52514]">.</span>
      </h1>
      <p className="text-black/60 mt-3 mb-10">Three steps. The agent takes over from there.</p>

      {Stepper}

      <div className="bg-white border border-ink p-8 md:p-10 space-y-6">
        {step === 1 && (
          <div className="space-y-6 reveal">
            <Field label="Brand name" testid="brand-name-input" value={name} onChange={setName} placeholder="Aloha" highlight />
            <Field label="Brand URL" testid="brand-url-input" value={url} onChange={setUrl} placeholder="https://aloha.com" mono />
            <Field label="Product name (optional)" testid="product-name-input" value={product} onChange={setProduct} placeholder="Organic Protein Powder" />
          </div>
        )}
        {step === 2 && (
          <div className="space-y-6 reveal">
            <h2 className="font-display text-2xl uppercase">Confirm details</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Cell k="Brand" v={name} />
              <Cell k="URL" v={url} mono />
              <Cell k="Product" v={product || "(brand-level)"} />
              <Cell k="Image model" v="fal-ai/flux-schnell" mono />
            </div>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-6 reveal">
            <h2 className="font-display text-2xl uppercase">Creative angle (optional)</h2>
            <div>
              <div className="label-mono mb-2">Brief</div>
              <textarea
                value={angle}
                onChange={(e) => setAngle(e.target.value)}
                rows={5}
                placeholder="Surprise me. Or describe a campaign angle, season, mood…"
                className="w-full p-4 border border-black/20 focus:border-[#E52514] focus:outline-none font-mono-tech text-sm bg-white"
                data-testid="angle-input"
              />
            </div>
          </div>
        )}

        <div className="flex items-center justify-between pt-6 border-t border-soft">
          {step > 1 ? (
            <button onClick={back} className="label-mono hover:text-[#E52514]" data-testid="wizard-back-button">← Back</button>
          ) : <span />}
          {step < 3 ? (
            <button onClick={next} className="flex items-center gap-2 px-6 h-11 bg-coral hover:bg-coral-deep text-black transition-colors text-sm font-medium" data-testid="wizard-next-button">
              Next <ArrowRight size={14} strokeWidth={1.5} />
            </button>
          ) : (
            <button onClick={finish} disabled={busy} className="flex items-center gap-2 px-6 h-11 bg-[#E52514] hover:bg-black text-white disabled:opacity-50 transition-colors text-sm font-medium" data-testid="wizard-finish-button">
              {busy ? <span>Building<span className="ascii-loader" /></span> : <>Generate ads <ArrowRight size={14} strokeWidth={1.5} /></>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, mono, highlight, testid }) {
  return (
    <div>
      <div className="label-mono mb-2">{label}</div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full h-12 px-4 bg-white border ${highlight ? "border-[#E52514]" : "border-black/20"} focus:border-[#E52514] focus:outline-none ${mono ? "font-mono-tech text-sm" : "text-base"}`}
        data-testid={testid}
      />
    </div>
  );
}
function Cell({ k, v, mono }) {
  return (
    <div className="border border-soft p-4">
      <div className="label-mono mb-1">{k}</div>
      <div className={mono ? "font-mono-tech text-sm" : "text-base"}>{v || "—"}</div>
    </div>
  );
}
