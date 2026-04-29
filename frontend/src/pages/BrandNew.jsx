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

  const stepper = (
    <div className="flex items-center gap-6 mb-12">
      {[1, 2, 3].map((i) => (
        <div key={i} className="flex items-center gap-2" data-testid={`step-indicator-${i}`}>
          <span className={`font-mono-tech text-xs ${step === i ? "text-[#E52514]" : step > i ? "text-black" : "text-black/30"}`}>
            №0{i}
          </span>
          <span className={`label-mono ${step === i ? "text-black" : "text-black/40"}`}>
            Step {i}
          </span>
          <span className={`h-px w-12 ${step >= i ? "bg-black" : "bg-black/20"}`} />
        </div>
      ))}
    </div>
  );

  return (
    <div className="max-w-[1440px] mx-auto px-6 md:px-12 py-12 md:py-20">
      <button onClick={() => navigate("/")} className="label-mono flex items-center gap-2 hover:text-[#E52514] mb-10" data-testid="wizard-back-link">
        <ArrowLeft size={14} strokeWidth={1.5} /> Back
      </button>

      <div className="label-mono">Brands · New</div>
      <h1 className="font-display text-5xl md:text-7xl font-black tracking-tighter leading-[0.9] mt-3 mb-3">
        Create brand<br/>workspace<span className="text-[#E52514]">.</span>
      </h1>
      <p className="text-neutral-600 mb-12 max-w-xl">Three steps. The agent takes over from there.</p>

      {stepper}

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 border-t border-black pt-12">
        <div className="lg:col-span-3">
          <div className="font-mono-tech text-7xl font-black tracking-tighter text-[#E52514]" data-testid="step-counter">
            {String(step).padStart(2, "0")}
          </div>
          <div className="label-mono mt-2">/ 03</div>
        </div>

        <div className="lg:col-span-7 space-y-8">
          {step === 1 && (
            <div className="space-y-6 reveal">
              <h2 className="font-display text-3xl font-bold tracking-tight">Brand basics</h2>
              <Field label="Brand name" testid="brand-name-input" value={name} onChange={setName} placeholder="e.g. Aesop" />
              <Field label="Brand URL" testid="brand-url-input" value={url} onChange={setUrl} placeholder="https://aesop.com" mono />
            </div>
          )}
          {step === 2 && (
            <div className="space-y-6 reveal">
              <h2 className="font-display text-3xl font-bold tracking-tight">Product (optional)</h2>
              <Field label="Product name" testid="product-name-input" value={product} onChange={setProduct} placeholder="e.g. B & Tea Balancing Toner" />
              <p className="text-sm text-neutral-600">Leave empty for a brand-level campaign.</p>
            </div>
          )}
          {step === 3 && (
            <div className="space-y-6 reveal">
              <h2 className="font-display text-3xl font-bold tracking-tight">Creative angle (optional)</h2>
              <div>
                <div className="label-mono mb-2">Brief</div>
                <textarea
                  value={angle}
                  onChange={(e) => setAngle(e.target.value)}
                  rows={4}
                  placeholder="Surprise me. Or describe a campaign angle, season, mood…"
                  className="w-full p-4 border border-black/20 focus:border-[#E52514] focus:outline-none font-mono-tech text-sm"
                  data-testid="angle-input"
                />
              </div>
              <div className="border border-black bg-black text-white p-6">
                <div className="label-mono text-white/60 mb-2">Confirm</div>
                <div className="font-display text-2xl font-bold">{name}</div>
                <div className="font-mono-tech text-xs text-white/70 mt-1">{url}</div>
                {product && <div className="text-sm mt-3">→ {product}</div>}
              </div>
            </div>
          )}
        </div>

        <div className="lg:col-span-2 flex lg:flex-col items-end lg:items-start lg:justify-end gap-3">
          {step > 1 && (
            <button onClick={back} className="px-5 h-11 border border-black/20 hover:border-black label-mono" data-testid="wizard-back-button">
              Back
            </button>
          )}
          {step < 3 ? (
            <button onClick={next} className="flex items-center gap-2 px-5 h-11 bg-black text-white hover:bg-[#E52514] transition-colors label-mono" data-testid="wizard-next-button">
              Next <ArrowRight size={14} strokeWidth={1.5} />
            </button>
          ) : (
            <button onClick={finish} disabled={busy} className="flex items-center gap-2 px-5 h-11 bg-[#E52514] text-white hover:bg-black disabled:opacity-50 transition-colors label-mono" data-testid="wizard-finish-button">
              {busy ? <span>Building<span className="ascii-loader" /></span> : <>Generate <ArrowRight size={14} strokeWidth={1.5} /></>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder, mono, testid }) {
  return (
    <div>
      <div className="label-mono mb-2">{label}</div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full h-12 px-4 border border-black/20 focus:border-[#E52514] focus:outline-none ${mono ? "font-mono-tech text-sm" : "font-display text-xl"}`}
        data-testid={testid}
      />
    </div>
  );
}
