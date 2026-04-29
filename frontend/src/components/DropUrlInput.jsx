import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";

export default function DropUrlInput({ onSubmit, busy }) {
  const [val, setVal] = useState("");
  const ref = useRef(null);
  useEffect(() => { ref.current?.focus(); }, []);

  const submit = (e) => {
    e?.preventDefault();
    const v = val.trim();
    if (!v) return;
    onSubmit(v);
  };

  return (
    <form onSubmit={submit} className="w-full" data-testid="drop-url-form">
      <div className="label-mono mb-2">Drop a brand URL</div>
      <div className="flex border border-ink bg-white">
        <input
          ref={ref}
          type="text"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder="https://oatly.com"
          className="flex-1 h-14 px-5 bg-transparent outline-none font-mono-tech text-base placeholder:text-black/30"
          disabled={busy}
          data-testid="drop-url-input"
        />
        <button
          type="submit"
          disabled={busy || !val.trim()}
          className="flex items-center gap-2 px-7 h-14 bg-coral hover:bg-coral-deep text-black border-l border-ink disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm font-medium"
          data-testid="drop-url-submit"
        >
          {busy ? <span>Building<span className="ascii-loader" /></span> : <>→ Generate ads</>}
        </button>
      </div>
      <p className="text-sm text-black/60 mt-3 max-w-2xl leading-relaxed">
        Paste any brand homepage. The agent runs all 3 phases automatically — research → prompts → 15 images.
        No further input needed. Average run: 6–10 minutes.{" "}
        <a href="/brands/new" className="text-coral underline hover:text-[#E52514]">Need to upload product photos? Use the wizard ↗</a>
      </p>
    </form>
  );
}
