import { useEffect, useState } from "react";
import { X, Eye, EyeOff, ExternalLink } from "lucide-react";
import { api, keysStore } from "../lib/api";
import { toast } from "sonner";

export default function KeysModal({ open, onClose }) {
  const [fal, setFal] = useState("");
  const [llm, setLlm] = useState("");
  const [showFal, setShowFal] = useState(false);
  const [showLlm, setShowLlm] = useState(false);
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (open) {
      setFal(keysStore.fal);
      setLlm(keysStore.llm);
      setResult(null);
    }
  }, [open]);

  if (!open) return null;

  const onTest = async () => {
    keysStore.set(fal.trim(), llm.trim());
    setTesting(true);
    setResult(null);
    try {
      const r1 = await api.testAnthropic();
      const r2 = await api.testFal();
      setResult({ ok: true, anthropic: r1.data, fal: r2.data });
      toast.success("Both keys validated.");
    } catch (e) {
      const msg = e?.response?.data?.detail || e.message;
      setResult({ ok: false, error: msg });
      toast.error(msg);
    } finally {
      setTesting(false);
    }
  };

  const onSave = () => {
    keysStore.set(fal.trim(), llm.trim());
    toast.success("Keys saved locally.");
    onClose();
  };

  const onClear = () => {
    keysStore.clear();
    setFal("");
    setLlm("");
    setResult(null);
    toast("Keys cleared.");
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-end md:items-center justify-center" data-testid="keys-modal">
      <div className="bg-white border border-black w-full md:w-[640px] max-h-[92vh] overflow-y-auto reveal">
        <div className="flex items-center justify-between px-8 py-5 border-b border-black/10">
          <div>
            <div className="label-mono">№01 · settings</div>
            <h2 className="font-display text-2xl font-bold tracking-tight">Bring your own keys</h2>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-black hover:text-white transition-colors" data-testid="close-keys-button">
            <X size={18} strokeWidth={1.5} />
          </button>
        </div>

        <div className="px-8 py-6 space-y-6">
          <p className="text-sm leading-relaxed text-neutral-700 max-w-prose">
            Plug in your FAL & Anthropic keys. This studio runs on your credentials — they live in this browser only and are <strong>never stored on the server</strong>. Each pipeline run bills your accounts directly.
          </p>

          {/* FAL key */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="label-mono">FAL API key</label>
              <a href="https://fal.ai/dashboard/keys" target="_blank" rel="noreferrer" className="label-mono hover:text-black flex items-center gap-1">
                Get one <ExternalLink size={12} strokeWidth={1.5} />
              </a>
            </div>
            <div className="flex">
              <input
                type={showFal ? "text" : "password"}
                value={fal}
                onChange={(e) => setFal(e.target.value)}
                placeholder="key:hex…"
                className="flex-1 h-12 px-4 border border-black/20 focus:border-[var(--red)] focus:outline-none font-mono-tech text-sm bg-white"
                data-testid="fal-key-input"
              />
              <button
                onClick={() => setShowFal((s) => !s)}
                className="w-12 border border-l-0 border-black/20 hover:border-black flex items-center justify-center"
                data-testid="toggle-fal-visibility"
              >
                {showFal ? <EyeOff size={14} strokeWidth={1.5} /> : <Eye size={14} strokeWidth={1.5} />}
              </button>
            </div>
            <div className="label-mono">Powers fal.ai image generation.</div>
          </div>

          {/* Anthropic key */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label className="label-mono">Anthropic / Claude API key</label>
              <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer" className="label-mono hover:text-black flex items-center gap-1">
                Get one <ExternalLink size={12} strokeWidth={1.5} />
              </a>
            </div>
            <div className="flex">
              <input
                type={showLlm ? "text" : "password"}
                value={llm}
                onChange={(e) => setLlm(e.target.value)}
                placeholder="sk-ant-…"
                className="flex-1 h-12 px-4 border border-black/20 focus:border-[var(--red)] focus:outline-none font-mono-tech text-sm bg-white"
                data-testid="llm-key-input"
              />
              <button
                onClick={() => setShowLlm((s) => !s)}
                className="w-12 border border-l-0 border-black/20 hover:border-black flex items-center justify-center"
                data-testid="toggle-llm-visibility"
              >
                {showLlm ? <EyeOff size={14} strokeWidth={1.5} /> : <Eye size={14} strokeWidth={1.5} />}
              </button>
            </div>
            <div className="label-mono">Powers brand research & prompt generation (Claude Sonnet 4.5).</div>
          </div>

          {result && (
            <div
              className={`border p-4 text-sm ${result.ok ? "border-black bg-black text-white" : "border-[var(--red)] text-[var(--red)]"}`}
              data-testid="keys-test-result"
            >
              {result.ok ? "Both keys validated. Ready to ship." : `× ${result.error}`}
            </div>
          )}

          <div className="text-[11px] font-mono-tech leading-relaxed text-neutral-500 border-l-2 border-[var(--red)] pl-3">
            Stored locally as <code>localStorage.sas.fal_key</code> & <code>.llm_key</code>. Clear them anytime.
          </div>
        </div>

        <div className="px-8 py-5 border-t border-black/10 flex items-center justify-between gap-3">
          <button
            onClick={onClear}
            className="label-mono hover:text-[var(--red)]"
            data-testid="clear-keys-button"
          >
            Clear keys
          </button>
          <div className="flex items-center gap-3">
            <button
              onClick={onTest}
              disabled={testing || !fal.trim() || !llm.trim()}
              className="px-5 h-11 border border-black hover:bg-black hover:text-white disabled:opacity-40 transition-colors label-mono"
              data-testid="test-keys-button"
            >
              {testing ? <span>Testing<span className="ascii-loader" /></span> : "Test both"}
            </button>
            <button
              onClick={onSave}
              disabled={!fal.trim() || !llm.trim()}
              className="px-5 h-11 bg-coral hover:bg-coral-deep border border-ink text-black disabled:opacity-40 transition-colors text-sm font-medium"
              data-testid="save-keys-button"
            >
              Save & continue
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
