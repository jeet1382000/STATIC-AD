import { useEffect, useState } from "react";
import { Pencil, RotateCcw, X } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

export default function Templates() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [resetBusy, setResetBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const r = await api.listTemplates();
      setItems(r.data);
    } catch {
      toast.error("Failed to load templates");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const toggle = async (t) => {
    const next = !t.enabled;
    setItems((prev) => prev.map((x) => (x.id === t.id ? { ...x, enabled: next } : x)));
    try {
      await api.patchTemplate(t.id, { enabled: next });
    } catch {
      toast.error("Toggle failed");
      setItems((prev) => prev.map((x) => (x.id === t.id ? { ...x, enabled: t.enabled } : x)));
    }
  };

  const saveEdit = async (patch) => {
    try {
      const r = await api.patchTemplate(editing.id, patch);
      setItems((prev) => prev.map((x) => (x.id === editing.id ? r.data : x)));
      toast.success("Template updated");
      setEditing(null);
    } catch {
      toast.error("Update failed");
    }
  };

  const resetAll = async () => {
    if (!window.confirm("Reset all templates to defaults? Edits will be lost.")) return;
    setResetBusy(true);
    try {
      const r = await api.resetTemplates();
      setItems(r.data);
      toast.success("Templates reset");
    } catch {
      toast.error("Reset failed");
    } finally {
      setResetBusy(false);
    }
  };

  const enabledCount = items.filter((t) => t.enabled).length;

  return (
    <div className="px-12 py-12 max-w-[1280px]">
      <div className="label-mono mb-3">Templates</div>
      <div className="flex items-end justify-between flex-wrap gap-4">
        <h1 className="font-display-tight text-6xl lg:text-7xl uppercase leading-[0.9]">Template library<span className="text-[#E52514]">.</span></h1>
        <button
          onClick={resetAll}
          disabled={resetBusy}
          className="flex items-center gap-2 px-4 h-10 border border-soft hover:border-ink text-sm disabled:opacity-50"
          data-testid="reset-templates-button"
        >
          <RotateCcw size={14} strokeWidth={1.5} /> Reset to defaults
        </button>
      </div>
      <p className="text-base text-black/65 mt-4 max-w-3xl leading-relaxed">
        15 production-ready ad templates. Toggle to enable per brand run, or edit the raw prompt scaffold.
        The agent uses every <span className="text-coral">enabled</span> template when generating ads.
      </p>
      <div className="mt-3 label-mono">
        <span data-testid="enabled-count">{enabledCount}</span> / {items.length} enabled
      </div>

      <div className="mt-10 bg-white border border-soft" data-testid="templates-table">
        <div className="grid grid-cols-[64px_1fr_120px_140px_180px_120px] items-center px-5 py-3 bg-cream-deep border-b border-soft">
          <div className="label-mono">№</div>
          <div className="label-mono">Name</div>
          <div className="label-mono">Aspect</div>
          <div className="label-mono">Needs product</div>
          <div className="label-mono">Category</div>
          <div className="label-mono text-right">Enabled</div>
        </div>

        {loading ? (
          <div className="py-24 text-center label-mono">Loading<span className="ascii-loader" /></div>
        ) : (
          items.map((t) => (
            <div
              key={t.id}
              className="grid grid-cols-[64px_1fr_120px_140px_180px_120px] items-center px-5 py-4 border-b border-soft last:border-b-0 hover:bg-cream"
              data-testid={`template-row-${t.number}`}
            >
              <div className="font-mono-tech text-xs text-black/50">№{String(t.number).padStart(2, "0")}</div>
              <button
                onClick={() => setEditing(t)}
                className="flex items-center gap-2 text-left hover:text-[#E52514]"
                data-testid={`template-edit-${t.number}`}
              >
                <span className="text-base font-medium">{t.name}</span>
                <Pencil size={12} strokeWidth={1.5} className="opacity-50" />
              </button>
              <div className="font-mono-tech text-sm">{t.aspect}</div>
              <div className="text-sm">{t.needs_product ? "Yes" : "No"}</div>
              <div className="font-mono-tech text-xs text-black/65">{t.category}</div>
              <div className="flex justify-end">
                <button
                  onClick={() => toggle(t)}
                  className={`label-mono w-16 h-8 flex items-center justify-center transition-colors ${
                    t.enabled
                      ? "bg-[#E52514] text-white border border-[#E52514]"
                      : "bg-white text-black border border-ink"
                  }`}
                  data-testid={`template-toggle-${t.number}`}
                  aria-pressed={t.enabled}
                >
                  {t.enabled ? "ON" : "OFF"}
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {editing && (
        <EditModal
          template={editing}
          onClose={() => setEditing(null)}
          onSave={saveEdit}
        />
      )}
    </div>
  );
}

function EditModal({ template, onClose, onSave }) {
  const [name, setName] = useState(template.name);
  const [scaffold, setScaffold] = useState(template.scaffold);
  return (
    <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center px-6" data-testid="template-edit-modal">
      <div className="bg-white border border-ink w-full max-w-[680px] reveal">
        <div className="flex items-center justify-between px-6 py-4 border-b border-soft">
          <div>
            <div className="label-mono">Template №{String(template.number).padStart(2, "0")}</div>
            <h3 className="font-display text-2xl uppercase">Edit scaffold</h3>
          </div>
          <button onClick={onClose} className="p-2 hover:bg-ink hover:text-white" data-testid="template-edit-close">
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4">
          <div>
            <div className="label-mono mb-2">Name</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-11 px-3 border border-soft focus:border-ink focus:outline-none"
              data-testid="template-edit-name"
            />
          </div>
          <div>
            <div className="label-mono mb-2">Prompt scaffold</div>
            <textarea
              value={scaffold}
              onChange={(e) => setScaffold(e.target.value)}
              rows={8}
              className="w-full p-3 border border-soft focus:border-ink focus:outline-none font-mono-tech text-sm leading-relaxed"
              data-testid="template-edit-scaffold"
            />
            <div className="label-mono mt-2">
              Aspect: {template.aspect} · Category: {template.category} · {template.needs_product ? "Needs product" : "No product needed"}
            </div>
          </div>
        </div>
        <div className="px-6 py-4 border-t border-soft flex items-center justify-end gap-3">
          <button onClick={onClose} className="label-mono hover:text-[#E52514]" data-testid="template-edit-cancel">Cancel</button>
          <button
            onClick={() => onSave({ name, scaffold })}
            disabled={!name.trim() || !scaffold.trim()}
            className="px-5 h-10 bg-[#E52514] hover:bg-black text-white text-sm font-medium disabled:opacity-40 transition-colors"
            data-testid="template-edit-save"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
