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
      <div className="flex items-end gap-4 border-b-2 border-black focus-within:border-[#E52514] transition-colors duration-150 pb-3">
        <span className="label-mono pb-2">URL ↳</span>
        <input
          ref={ref}
          type="text"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder="https://example.com"
          className="flex-1 bg-transparent outline-none font-display text-3xl md:text-5xl font-bold tracking-tight placeholder:text-black/20"
          disabled={busy}
          data-testid="drop-url-input"
        />
        <button
          type="submit"
          disabled={busy || !val.trim()}
          className="flex items-center gap-2 px-5 h-12 bg-black text-white hover:bg-[#E52514] disabled:opacity-30 transition-colors label-mono"
          data-testid="drop-url-submit"
        >
          {busy ? <span>Building<span className="ascii-loader" /></span> : (<>Run pipeline <ArrowRight size={14} strokeWidth={1.5} /></>)}
        </button>
      </div>
      <div className="label-mono mt-3">
        Drop any brand URL. The agent reverse-engineers the visual identity and generates 15 ad creatives.
      </div>
    </form>
  );
}
