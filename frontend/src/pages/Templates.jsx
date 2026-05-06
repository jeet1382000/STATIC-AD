import { useEffect, useState } from "react";
import { Pencil, RotateCcw, X, Save, Check, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";

const ASPECTS = ["1:1", "4:5", "9:16", "16:9", "4:3"];

export default function Templates() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
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

  const createTemplate = async (data) => {
    try {
      const r = await api.createTemplate(data);
      setItems((prev) => [...prev, r.data].sort((a, b) => a.number - b.number));
      toast.success("Template created");
      setCreating(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    }
  };

  const deleteTemplate = async (t) => {
    if (!window.confirm(`Delete template "${t.name}"? This cannot be undone.`)) return;
    const prev = items;
    setItems((curr) => curr.filter((x) => x.id !== t.id));
    try {
      await api.deleteTemplate(t.id);
      toast.success("Template deleted");
    } catch {
      toast.error("Delete failed");
      setItems(prev);
    }
  };

  const enabledCount = items.filter((t) => t.enabled).length;

  return (
    <div className="px-12 py-12 max-w-[1280px]">
      <div className="label-mono mb-3">Templates</div>
      <div className="flex items-end justify-between flex-wrap gap-4">
        <h1 className="font-display-tight text-6xl lg:text-7xl uppercase leading-[0.9]">Template library<span className="text-[var(--red)]">.</span></h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setCreating(true)}
            className="flex items-center gap-2 px-4 h-10 bg-[var(--red)] hover:bg-black text-white text-sm font-medium transition-colors"
            data-testid="new-template-button"
          >
            <Plus size={14} strokeWidth={2} /> New template
          </button>
          <button
            onClick={resetAll}
            disabled={resetBusy}
            className="flex items-center gap-2 px-4 h-10 border border-soft hover:border-ink text-sm disabled:opacity-50"
            data-testid="reset-templates-button"
          >
            <RotateCcw size={14} strokeWidth={1.5} /> Reset to defaults
          </button>
        </div>
      </div>
      <p className="text-base text-black/65 mt-4 max-w-3xl leading-relaxed">
        15 production-ready ad templates. Toggle to enable per brand run, or edit the raw prompt scaffold.
        The agent uses every <span className="text-coral">enabled</span> template when generating ads.
      </p>
      <div className="mt-3 label-mono">
        <span data-testid="enabled-count">{enabledCount}</span> / {items.length} enabled
      </div>

      <div className="mt-10 bg-white border border-soft" data-testid="templates-table">
        <div className="grid grid-cols-[64px_1fr_120px_140px_180px_120px_56px] items-center px-5 py-3 bg-cream-deep border-b border-soft">
          <div className="label-mono">№</div>
          <div className="label-mono">Name</div>
          <div className="label-mono">Aspect</div>
          <div className="label-mono">Needs product</div>
          <div className="label-mono">Category</div>
          <div className="label-mono text-right">Enabled</div>
          <div className="label-mono text-right">Del</div>
        </div>

        {loading ? (
          <div className="py-24 text-center label-mono">Loading<span className="ascii-loader" /></div>
        ) : (
          items.map((t) => (
            <div
              key={t.id}
              className="grid grid-cols-[64px_1fr_120px_140px_180px_120px_56px] items-center px-5 py-4 border-b border-soft last:border-b-0 hover:bg-cream"
              data-testid={`template-row-${t.number}`}
            >
              <div className="font-mono-tech text-xs text-black/50">№{String(t.number).padStart(2, "0")}</div>
              <button
                onClick={() => setEditing(t)}
                className="flex items-center gap-2 text-left hover:text-[var(--red)]"
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
                      ? "bg-[var(--red)] text-white border border-[var(--red)]"
                      : "bg-white text-black border border-ink"
                  }`}
                  data-testid={`template-toggle-${t.number}`}
                  aria-pressed={t.enabled}
                >
                  {t.enabled ? "ON" : "OFF"}
                </button>
              </div>
              <div className="flex justify-end">
                <button
                  onClick={() => deleteTemplate(t)}
                  className="w-9 h-9 flex items-center justify-center text-black/40 hover:text-[var(--red)] hover:bg-[var(--red)]/10 transition-colors"
                  data-testid={`template-delete-${t.number}`}
                  aria-label={`Delete template ${t.name}`}
                  title="Delete template"
                >
                  <Trash2 size={15} strokeWidth={1.75} />
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

      {creating && (
        <EditModal
          template={{
            number: (items[items.length - 1]?.number || 0) + 1,
            name: "",
            scaffold: "",
            aspect: "1:1",
            needs_product: false,
          }}
          mode="create"
          onClose={() => setCreating(false)}
          onSave={createTemplate}
        />
      )}
    </div>
  );
}

function EditModal({ template, onClose, onSave, mode = "edit" }) {
  const [name, setName] = useState(template.name);
  const [scaffold, setScaffold] = useState(template.scaffold);
  const [aspect, setAspect] = useState(template.aspect);
  const [needsProduct, setNeedsProduct] = useState(template.needs_product);
  const isCreate = mode === "create";

  return (
    <div className="fixed inset-0 z-50 bg-black/30 backdrop-blur-sm flex items-stretch justify-end" data-testid="template-edit-modal">
      <div className="bg-cream w-full md:w-[760px] max-w-full overflow-y-auto reveal border-l border-ink">
        <div className="px-10 md:px-14 py-10 md:py-14 space-y-8">
          {/* Header */}
          <div>
            <div className="label-mono">
              {isCreate
                ? `New template · №${String(template.number).padStart(2, "0")}`
                : `Edit template №${String(template.number).padStart(2, "0")}`}
            </div>
            <h2 className="font-display-tight text-5xl md:text-6xl uppercase leading-[0.9] mt-2">
              {isCreate ? "Create custom template." : template.name}
            </h2>
          </div>

          {/* Name */}
          <div>
            <div className="label-mono mb-2">Name</div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={isCreate ? "Holiday Sale Bundle" : ""}
              className="w-full h-14 px-4 bg-white border border-ink focus:border-[var(--red)] focus:outline-none text-base"
              data-testid="template-edit-name"
            />
          </div>

          {/* Aspect ratio + checkbox */}
          <div className="flex items-end gap-8 flex-wrap">
            <div className="flex-1 min-w-[200px] max-w-[280px]">
              <div className="label-mono mb-2">Aspect ratio</div>
              <select
                value={aspect}
                onChange={(e) => setAspect(e.target.value)}
                className="w-full h-14 px-4 bg-white border border-ink focus:border-[var(--red)] focus:outline-none text-base font-mono-tech"
                data-testid="template-edit-aspect"
              >
                {ASPECTS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <label className="flex items-center gap-3 cursor-pointer h-14 select-none" data-testid="template-edit-needs-product">
              <span
                className={`w-6 h-6 border border-ink flex items-center justify-center transition-colors ${needsProduct ? "bg-[var(--red)]" : "bg-white"}`}
                role="checkbox"
                aria-checked={needsProduct}
                onClick={() => setNeedsProduct((v) => !v)}
              >
                {needsProduct && <Check size={14} strokeWidth={2.5} className="text-white" />}
              </span>
              <span className="text-base" onClick={() => setNeedsProduct((v) => !v)}>
                Needs product images
              </span>
            </label>
          </div>

          {/* Prompt scaffold */}
          <div>
            <div className="label-mono mb-2">Prompt scaffold</div>
            <textarea
              value={scaffold}
              onChange={(e) => setScaffold(e.target.value)}
              rows={12}
              placeholder={isCreate ? "A bold ad for [BRAND NAME] showing [SUBJECT] on a [BRAND BACKGROUND COLOR] background. Use [BRAND PRIMARY COLOR] for the headline reading \"[HEADLINE TEXT]\"…" : ""}
              className="w-full p-5 bg-white border border-ink focus:border-[var(--red)] focus:outline-none text-base leading-relaxed resize-y"
              data-testid="template-edit-scaffold"
            />
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-6 pt-4 border-t border-soft">
            <button
              onClick={onClose}
              className="flex items-center gap-2 text-base hover:text-[var(--red)]"
              data-testid="template-edit-cancel"
            >
              <X size={16} strokeWidth={1.5} /> Cancel
            </button>
            <button
              onClick={() => onSave({ name, scaffold, aspect, needs_product: needsProduct })}
              disabled={!name.trim() || !scaffold.trim()}
              className="flex items-center gap-2 px-6 h-12 bg-[var(--red)] hover:bg-black text-white text-base font-medium disabled:opacity-40 transition-colors"
              data-testid="template-edit-save"
            >
              <Save size={16} strokeWidth={1.75} /> {isCreate ? "Create template" : "Save"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
