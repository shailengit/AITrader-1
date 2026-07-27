import { useState, useEffect } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, Cpu, Cloud } from "lucide-react";
import { strategyLabApi, type OllamaModel, type ModelVariant } from "../../lib/strategyLab";
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

interface StepIdeaProps {
  onCreated: (sessionId: string) => void;
  defaultModel?: string;
  sessionId?: string;  // if set, shows ChatPanel after creation
}

const DEFAULT_MODEL = "deepseek-v4-flash:cloud";

const EXAMPLE_PROMPTS = [
  "Buy stocks where EMA20 crosses above EMA200. Rank by crossover angle + market cap. Hold top 5, exit on death cross or 20% trailing stop.",
  "Bollinger squeeze + OBV accumulation + EPS acceleration q/q. Hold 3 names max.",
  "Mean-reversion on RSI(2) oversold in uptrending sectors, ranked by relative strength.",
];

export function StepIdea({ onCreated, defaultModel = DEFAULT_MODEL, sessionId }: StepIdeaProps) {
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState(defaultModel);
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: () =>
      strategyLabApi.createSession({
        name: name.trim() || autoName(prompt),
        prompt: prompt.trim(),
        model_id: model,
      }),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["strategy-lab-sessions"] });
      onCreated(session.id);
    },
  });

  const canSubmit = prompt.trim().length > 0 && !create.isPending;

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 01 · Idea</div>
          <h1 className="slab-page-head__title">Describe the strategy.</h1>
          <p className="slab-page-head__lede">
            Plain English. The LLM will turn this into a structured plan,
            write the code, run randomized backtests, and prepare it for
            paper trading.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Description</span>
          <span className="slab-mono slab-mono--gold">READY</span>
        </div>
      </div>

      <div className="slab-page-body slab-grid-bg">
        <div style={{ maxWidth: 880 }}>
          {/* Session name */}
          <div className="slab-field" style={{ marginBottom: 28 }}>
            <label className="slab-field__label">
              Session name
              <span className="slab-mono slab-mono--xs slab-mono--faint">· optional</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={autoName(prompt) || "untitled-strategy"}
              className="slab-input"
            />
            <div className="slab-field__hint">
              Auto-generated from the first 60 characters of your prompt if left empty.
            </div>
          </div>

          {/* Prompt — the big one */}
          <div className="slab-field" style={{ marginBottom: 28 }}>
            <label className="slab-field__label">
              Strategy in plain English
              <span className="slab-mono slab-mono--xs slab-mono--faint">
                · {prompt.length} chars
              </span>
            </label>
            <textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              rows={9}
              placeholder="Buy stocks where EMA20 crosses above EMA200. Rank by crossover angle + market cap. Hold top 5, exit on death cross or 20% trailing stop."
              className="slab-textarea"
              style={{ fontSize: 14, lineHeight: 1.7 }}
            />
            <div className="slab-field__hint">
              Or pick an example below to start from a known good prompt.
            </div>
          </div>

          {/* Examples as horizontal chips */}
          <div style={{ marginBottom: 36 }}>
            <div className="slab-eyebrow" style={{ marginBottom: 10 }}>Examples</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {EXAMPLE_PROMPTS.map((ex, i) => (
                <button
                  key={i}
                  type="button"
                  onClick={() => setPrompt(ex)}
                  className="slab-textarea"
                  style={{
                    textAlign: "left",
                    padding: "10px 14px",
                    cursor: "pointer",
                    background: "var(--slab-ink-2)",
                    color: "var(--slab-paper-dim)",
                    fontSize: 12,
                    lineHeight: 1.5,
                    borderColor: "var(--slab-rule-soft)",
                    fontFamily: "var(--slab-font-sans)",
                    fontStyle: "italic",
                  }}
                >
                  <span className="slab-mono slab-mono--xs slab-mono--gold" style={{ marginRight: 10 }}>
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  {ex}
                </button>
              ))}
            </div>
          </div>

          {/* Model picker */}
          <div className="slab-field" style={{ marginBottom: 32 }}>
            <label className="slab-field__label">Model</label>
            <ModelPicker value={model} onChange={setModel} disabled={create.isPending} />
          </div>

          {/* Submit */}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              type="button"
              onClick={() => create.mutate()}
              disabled={!canSubmit}
              className="slab-btn slab-btn--primary"
              style={{ padding: "12px 24px" }}
            >
              {create.isPending ? "Initializing…" : "Begin"}
              {!create.isPending && <ArrowRight size={12} />}
            </button>
            {create.isError && (
              <span className="slab-mono slab-mono--sm slab-mono--rose">
                × {String((create.error as Error)?.message ?? "Failed to create session")}
              </span>
            )}
          </div>
        </div>

        {/* ChatPanel — only shown after session is created */}
        {sessionId && (
          <ChatPanel
            sessionId={sessionId}
            defaultModelId={model}
          />
        )}
      </div>
    </>
  );
}

function autoName(prompt: string): string {
  const trimmed = prompt.trim();
  if (!trimmed) return "";
  return trimmed.slice(0, 60) + (trimmed.length > 60 ? "..." : "");
}

// ── Model picker — grid of cards with cloud/local markers ────────────
export function ModelPicker({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    strategyLabApi
      .listModels()
      .then((m) => { if (mounted) { setModels(m); setLoading(false); } })
      .catch((e) => { if (mounted) { setError(String(e)); setLoading(false); } });
    return () => { mounted = false; };
  }, []);

  if (loading) {
    return <div className="slab-mono slab-mono--sm slab-mono--dim">Loading model registry…</div>;
  }
  if (error) {
    return <div className="slab-mono slab-mono--sm slab-mono--rose">× Failed: {error}</div>;
  }

  // Flatten to a sorted, alphabetized list
  type Row = { id: string; modelName: string; variant: ModelVariant };
  const rows: Row[] = [];
  for (const m of models) {
    for (const v of m.variants) {
      rows.push({ id: `${m.id}:${v.name}`, modelName: m.id, variant: v });
    }
  }
  rows.sort((a, b) => a.id.localeCompare(b.id));

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
        gap: 6,
      }}
    >
      {rows.map((r) => {
        const isCloud = r.variant.type === "cloud";
        const selected = r.id === value;
        return (
          <motion.button
            key={r.id}
            type="button"
            onClick={() => onChange(r.id)}
            disabled={disabled}
            whileHover={{ x: 2 }}
            transition={{ duration: 0.1 }}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: 10,
              padding: "10px 14px",
              background: selected ? "var(--slab-gold-glow)" : "var(--slab-ink-2)",
              border: `1px solid ${selected ? "var(--slab-gold)" : "var(--slab-rule)"}`,
              cursor: disabled ? "not-allowed" : "pointer",
              textAlign: "left",
              fontFamily: "var(--slab-font-mono)",
              opacity: disabled ? 0.5 : 1,
              position: "relative",
            }}
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 0, flex: 1 }}>
              <div
                className="slab-mono slab-mono--md"
                style={{
                  color: selected ? "var(--slab-paper)" : "var(--slab-paper-dim)",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {r.modelName}
              </div>
              <div className="slab-mono slab-mono--xs slab-mono--faint">variant · {r.variant.name}</div>
            </div>
            <span
              className="slab-tag"
              style={{
                borderColor: isCloud ? "var(--slab-paper-faint)" : "var(--slab-gold)",
                color: isCloud ? "var(--slab-paper-dim)" : "var(--slab-gold)",
                flexShrink: 0,
              }}
            >
              {isCloud ? <Cloud size={9} /> : <Cpu size={9} />}
              {isCloud ? "cloud" : "local"}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
