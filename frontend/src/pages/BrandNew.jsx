import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, UploadCloud, X } from "lucide-react";
import { api, keysStore } from "../lib/api";

const MAX_IMAGES = 5;
const MAX_BYTES = 800_000; // ~800KB per image

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve({ name: file.name, size: file.size, dataUrl: r.result });
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

export default function BrandNew({ onOpenKeys }) {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [step, setStep] = useState(1);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [product, setProduct] = useState("");
  const [images, setImages] = useState([]); // {name, dataUrl, size}
  const [angle, setAngle] = useState("");
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInput = useRef(null);

  // Prefill the URL field from ?url=… when the user lands here from the
  // dashboard "Drop a brand URL" input. The brand name field is intentionally
  // left blank for the user to fill in.
  useEffect(() => {
    const incoming = searchParams.get("url");
    if (!incoming) return;
    setUrl((prev) => prev || incoming);
  }, [searchParams]);

  const next = () => {
    if (step === 1 && (!name.trim() || !url.trim())) {
      toast.error("Brand name and URL required");
      return;
    }
    setStep(step + 1);
  };
  const back = () => setStep(Math.max(1, step - 1));

  const addFiles = async (files) => {
    const list = Array.from(files).filter((f) => f.type.startsWith("image/"));
    if (list.length === 0) {
      toast.error("Only image files are allowed");
      return;
    }
    const slots = MAX_IMAGES - images.length;
    if (slots <= 0) {
      toast.error(`Max ${MAX_IMAGES} images`);
      return;
    }
    const taken = list.slice(0, slots);
    const oversize = taken.find((f) => f.size > MAX_BYTES);
    if (oversize) {
      toast.error(`${oversize.name} is over 800KB. Compress first.`);
      return;
    }
    try {
      const converted = await Promise.all(taken.map(fileToDataUrl));
      setImages((prev) => [...prev, ...converted]);
    } catch {
      toast.error("Failed to read file");
    }
  };

  const removeImage = (i) => setImages((prev) => prev.filter((_, idx) => idx !== i));

  const finish = async () => {
    if (!keysStore.has()) {
      toast.error("Add your FAL & Anthropic keys first.");
      onOpenKeys();
      return;
    }
    setBusy(true);
    try {
      const created = await api.createBrand({
        name,
        url,
        product_name: product || null,
        product_images: images.map((i) => i.dataUrl),
      });
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
          <div className={`h-1 w-full ${step >= i ? "bg-[var(--red)]" : "bg-black/15"}`} />
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
      <button onClick={() => navigate("/")} className="label-mono flex items-center gap-2 hover:text-[var(--red)] mb-8" data-testid="wizard-back-link">
        <ArrowLeft size={14} strokeWidth={1.5} /> Back
      </button>

      <div className="label-mono">Brands · New</div>
      <h1 className="font-display-tight text-6xl lg:text-7xl uppercase leading-[0.9] mt-3">
        Create brand workspace<span className="text-[var(--red)]">.</span>
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
            <div className="label-mono">Product images (optional, max {MAX_IMAGES})</div>

            <div
              onClick={() => fileInput.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files);
              }}
              className={`cursor-pointer border-2 border-dashed ${dragOver ? "border-[var(--red)] bg-[var(--red)]/5" : "border-black/30 bg-cream"} hover:border-ink transition-colors py-16 px-8 text-center select-none`}
              data-testid="image-dropzone"
            >
              <input
                ref={fileInput}
                type="file"
                accept="image/*"
                multiple
                onChange={(e) => { if (e.target.files?.length) addFiles(e.target.files); e.target.value = ""; }}
                className="hidden"
                data-testid="image-file-input"
              />
              <div className="flex flex-col items-center gap-3">
                <UploadCloud size={36} strokeWidth={1.25} />
                <div className="font-display text-2xl">Drop product images here</div>
                <div className="text-sm text-black/55">or click to browse</div>
                <div className="label-mono mt-1">PNG · JPG · WEBP · max 800KB each</div>
              </div>
            </div>

            {images.length > 0 && (
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3" data-testid="image-thumbnails">
                {images.map((img, i) => (
                  <div key={i} className="relative aspect-square bg-cream-deep border border-soft group">
                    <img src={img.dataUrl} alt={img.name} className="w-full h-full object-cover" />
                    <button
                      onClick={() => removeImage(i)}
                      className="absolute top-1 right-1 bg-white border border-ink p-1 opacity-0 group-hover:opacity-100 hover:bg-[var(--red)] hover:text-white transition"
                      data-testid={`remove-image-${i}`}
                      type="button"
                    >
                      <X size={12} strokeWidth={1.5} />
                    </button>
                    <div className="absolute bottom-1 left-1 right-1 truncate font-mono-tech text-[10px] bg-white/80 px-1 py-0.5">{img.name}</div>
                  </div>
                ))}
              </div>
            )}

            <p className="text-sm text-black/55">
              Optional reference photos. They give the agent context for the brand's product when generating ad prompts.
            </p>
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
                className="w-full p-4 border border-black/20 focus:border-[var(--red)] focus:outline-none font-mono-tech text-sm bg-white"
                data-testid="angle-input"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Cell k="Brand" v={name} />
              <Cell k="URL" v={url} mono />
              <Cell k="Product" v={product || "(brand-level)"} />
              <Cell k="Reference photos" v={images.length ? `${images.length} attached` : "—"} />
            </div>
          </div>
        )}

        <div className="flex items-center justify-between pt-6 border-t border-soft">
          {step > 1 ? (
            <button onClick={back} className="flex items-center gap-2 text-sm hover:text-[var(--red)]" data-testid="wizard-back-button">
              <ArrowLeft size={14} strokeWidth={1.5} /> Back
            </button>
          ) : <span />}
          {step < 3 ? (
            <button onClick={next} className="flex items-center gap-2 px-6 h-11 bg-[var(--red)] hover:bg-black text-white transition-colors text-sm font-medium" data-testid="wizard-next-button">
              Next <ArrowRight size={14} strokeWidth={1.5} />
            </button>
          ) : (
            <button onClick={finish} disabled={busy} className="flex items-center gap-2 px-6 h-11 bg-[var(--red)] hover:bg-black text-white disabled:opacity-50 transition-colors text-sm font-medium" data-testid="wizard-finish-button">
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
        className={`w-full h-12 px-4 bg-white border ${highlight ? "border-[var(--red)]" : "border-black/20"} focus:border-[var(--red)] focus:outline-none ${mono ? "font-mono-tech text-sm" : "text-base"}`}
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
