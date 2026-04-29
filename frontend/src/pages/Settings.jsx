import { useEffect, useState } from "react";
import { Eye, EyeOff, ExternalLink, KeyRound, Save, Trash2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { api, keysStore } from "../lib/api";

export default function Settings() {
  const [fal, setFal] = useState("");
  const [llm, setLlm] = useState("");
  const [showFal, setShowFal] = useState(false);
  const [showLlm, setShowLlm] = useState(false);
  const [falStatus, setFalStatus] = useState("idle"); // idle | testing | ok | bad
  const [llmStatus, setLlmStatus] = useState("idle");
  const [defaults, setDefaults] = useState({ quality: "medium", variations_per_prompt: 1, cost_cap_per_run_usd: 20 });
  const [savingDefaults, setSavingDefaults] = useState(false);

  useEffect(() => {
    setFal(keysStore.fal);
    setLlm(keysStore.llm);
    api.getSettings().then((r) => setDefaults(r.data)).catch(() => {});
  }, []);

  const bothConnected = !!fal.trim() && !!llm.trim();

  const saveKeys = () => {
    keysStore.set(fal.trim(), llm.trim());
    toast.success("Keys saved to browser");
  };

  const clearKeys = () => {
    keysStore.clear();
    setFal("");
    setLlm("");
    setFalStatus("idle");
    setLlmStatus("idle");
    toast("Keys cleared.");
  };

  const testFal = async () => {
    keysStore.set(fal.trim(), llm.trim());
    setFalStatus("testing");
    try {
      await api.testFal();
      setFalStatus("ok");
      toast.success("FAL key valid");
    } catch (e) {
      setFalStatus("bad");
      toast.error(e?.response?.data?.detail || "FAL test failed");
    }
  };

  const testLlm = async () => {
    keysStore.set(fal.trim(), llm.trim());
    setLlmStatus("testing");
    try {
      await api.testAnthropic();
      setLlmStatus("ok");
      toast.success("Anthropic key valid");
    } catch (e) {
      setLlmStatus("bad");
      toast.error(e?.response?.data?.detail || "Anthropic test failed");
    }
  };

  const saveDefaults = async () => {
    setSavingDefaults(true);
    try {
      const r = await api.patchSettings({
        quality: defaults.quality,
        variations_per_prompt: Number(defaults.variations_per_prompt),
        cost_cap_per_run_usd: Number(defaults.cost_cap_per_run_usd),
      });
      setDefaults(r.data);
      toast.success("Defaults saved");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Save failed");
    } finally {
      setSavingDefaults(false);
    }
  };

  return (
    <div className="px-12 py-12 max-w-[920px]">
      <div className="label-mono mb-3">Settings</div>
      <h1 className="font-display-tight text-6xl lg:text-7xl uppercase leading-[0.9]">Configuration<span className="text-[var(--red)]">.</span></h1>
      <p className="text-base text-black/60 mt-4 max-w-2xl">
        Your API keys live in this browser only. Defaults are saved on the server.
      </p>

      {/* BYOK Card */}
      <section className="mt-12 bg-white border border-soft" data-testid="byok-card">
        <header className="flex items-center justify-between px-8 py-5 border-b border-soft">
          <div className="flex items-center gap-2">
            <KeyRound size={14} strokeWidth={1.5} />
            <span className="label-mono">Bring-your-own keys</span>
          </div>
          <span className="label-mono flex items-center" style={{ color: bothConnected ? "#16A34A" : "rgba(0,0,0,0.4)" }}>
            <span className={`dot ${bothConnected ? "" : "gray"}`} />
            {bothConnected ? "both connected" : "incomplete"}
          </span>
        </header>

        <div className="px-8 py-6 space-y-7">
          <div className="bg-cream-deep border border-soft p-4 flex items-start gap-3" data-testid="storage-banner">
            <ShieldCheck size={16} strokeWidth={1.5} className="mt-0.5 shrink-0 text-[#16A34A]" />
            <p className="text-sm leading-relaxed">
              Stored as <code className="font-mono-tech text-xs">localStorage.sas.fal_key</code> &amp;{" "}
              <code className="font-mono-tech text-xs">.llm_key</code> in <em>this</em> browser only.
              Never written to the server. Each pipeline run bills <strong>your</strong> FAL &amp; Anthropic accounts.
            </p>
          </div>

          {/* FAL */}
          <KeyRow
            label="FAL API key"
            help="Powers fal.ai image generation."
            link="https://fal.ai/dashboard/keys"
            value={fal}
            onChange={setFal}
            show={showFal}
            onToggleShow={() => setShowFal((s) => !s)}
            status={falStatus}
            onTest={testFal}
            placeholder="key:hex…"
            testid="fal-key"
          />

          {/* Anthropic */}
          <KeyRow
            label="Anthropic / Claude API key"
            help="Brand research & prompt generation (Claude Sonnet 4.5)."
            link="https://console.anthropic.com/settings/keys"
            value={llm}
            onChange={setLlm}
            show={showLlm}
            onToggleShow={() => setShowLlm((s) => !s)}
            status={llmStatus}
            onTest={testLlm}
            placeholder="sk-ant-…"
            testid="llm-key"
          />

          <div className="flex items-center gap-4 pt-2">
            <button
              onClick={saveKeys}
              disabled={!fal.trim() || !llm.trim()}
              className="flex items-center gap-2 px-5 h-11 bg-[var(--red)] hover:bg-black text-white text-sm font-medium disabled:opacity-40 transition-colors"
              data-testid="save-keys-button"
            >
              <Save size={14} strokeWidth={1.75} /> Save keys to browser
            </button>
            <button
              onClick={clearKeys}
              className="flex items-center gap-2 text-[var(--red)] hover:text-black text-sm font-medium"
              data-testid="clear-keys-button"
            >
              <Trash2 size={14} strokeWidth={1.5} /> Clear
            </button>
          </div>
        </div>
      </section>

      {/* Defaults Card */}
      <section className="mt-8 bg-white border border-soft" data-testid="defaults-card">
        <div className="px-8 py-6 space-y-6">
          <div className="label-mono">Defaults</div>

          <div>
            <div className="label-mono mb-2">Quality</div>
            <select
              value={defaults.quality}
              onChange={(e) => setDefaults({ ...defaults, quality: e.target.value })}
              className="w-full h-12 px-4 bg-white border border-soft hover:border-ink focus:border-[var(--red)] focus:outline-none text-base"
              data-testid="defaults-quality"
            >
              <option value="low">low — faster (2 steps)</option>
              <option value="medium">medium — balanced (4 steps)</option>
              <option value="high">high — sharper (8 steps)</option>
            </select>
          </div>

          <div>
            <div className="label-mono mb-2">Variations per prompt</div>
            <select
              value={defaults.variations_per_prompt}
              onChange={(e) => setDefaults({ ...defaults, variations_per_prompt: Number(e.target.value) })}
              className="w-full h-12 px-4 bg-white border border-soft hover:border-ink focus:border-[var(--red)] focus:outline-none text-base"
              data-testid="defaults-variations"
            >
              {[1, 2, 3, 4].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </div>

          <div>
            <div className="label-mono mb-2">Cost cap per run (USD)</div>
            <input
              type="number"
              min={0}
              step={1}
              value={defaults.cost_cap_per_run_usd}
              onChange={(e) => setDefaults({ ...defaults, cost_cap_per_run_usd: e.target.value })}
              className="w-full h-12 px-4 bg-white border border-soft hover:border-ink focus:border-[var(--red)] focus:outline-none text-base font-mono-tech"
              data-testid="defaults-costcap"
            />
          </div>
        </div>
      </section>

      <div className="mt-6 flex justify-end">
        <button
          onClick={saveDefaults}
          disabled={savingDefaults}
          className="flex items-center gap-2 px-5 h-11 bg-[var(--red)] hover:bg-black text-white text-sm font-medium disabled:opacity-40 transition-colors"
          data-testid="save-defaults-button"
        >
          <Save size={14} strokeWidth={1.75} /> {savingDefaults ? "Saving…" : "Save defaults"}
        </button>
      </div>
    </div>
  );
}

function KeyRow({ label, help, link, value, onChange, show, onToggleShow, status, onTest, placeholder, testid }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="label-mono">{label}</label>
        <a href={link} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[var(--red)] hover:text-black text-sm">
          Get one <ExternalLink size={12} strokeWidth={1.5} />
        </a>
      </div>
      <div className="flex">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="flex-1 h-12 px-4 border border-soft hover:border-ink focus:border-[var(--red)] focus:outline-none font-mono-tech text-sm bg-white"
          data-testid={`${testid}-input`}
        />
        <button
          onClick={onToggleShow}
          className="w-12 border border-l-0 border-soft hover:border-ink flex items-center justify-center"
          data-testid={`${testid}-toggle`}
          type="button"
        >
          {show ? <EyeOff size={14} strokeWidth={1.5} /> : <Eye size={14} strokeWidth={1.5} />}
        </button>
        <button
          onClick={onTest}
          disabled={!value.trim() || status === "testing"}
          className={`px-5 h-12 border border-l-0 border-soft hover:border-ink text-sm font-medium disabled:opacity-40 ${
            status === "ok" ? "bg-black text-white border-black" : status === "bad" ? "border-[var(--red)] text-[var(--red)]" : ""
          }`}
          data-testid={`${testid}-test`}
          type="button"
        >
          {status === "testing" ? "Testing…" : status === "ok" ? "✓ OK" : "Test"}
        </button>
      </div>
      <div className="text-sm text-black/55">{help}</div>
    </div>
  );
}
