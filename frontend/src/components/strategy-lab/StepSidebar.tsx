import { Check } from "lucide-react";

export interface Step {
  id: number;
  label: string;
  meta: string;
  completed: boolean;
  active: boolean;
}

interface StepSidebarProps {
  steps: Step[];
  onSelect: (id: number) => void;
  sessionName?: string | null;
  modelId?: string | null;
}

export function StepSidebar({ steps, onSelect, sessionName, modelId }: StepSidebarProps) {
  return (
    <aside className="slab-rail">
      <div className="slab-rail__brand">
        <div className="slab-rail__brand-mark">Strategy Lab · v0.1</div>
        <div className="slab-rail__brand-name">The Workshop</div>
      </div>

      {sessionName && (
        <div className="slab-rail__session">
          <div className="slab-eyebrow">Session</div>
          <div className="slab-mono slab-mono--md" style={{ color: "var(--slab-paper)" }}>
            {sessionName.length > 32 ? sessionName.slice(0, 32) + "…" : sessionName}
          </div>
          {modelId && (
            <div className="slab-mono slab-mono--xs slab-mono--dim">model · {modelId}</div>
          )}
        </div>
      )}

      <div style={{ flex: 1, paddingTop: 8 }}>
        {steps.map((s) => (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`slab-rail__step${s.active ? " slab-rail__step--active" : ""}${s.completed ? " slab-rail__step--complete" : ""}`}
            type="button"
          >
            <div className="slab-rail__step-num">
              {s.completed ? (
                <Check size={12} strokeWidth={3} style={{ verticalAlign: "middle" }} />
              ) : (
                String(s.id).padStart(2, "0")
              )}
            </div>
            <div>
              <div className="slab-rail__step-label">{s.label}</div>
              <div className="slab-rail__step-meta">{s.meta}</div>
            </div>
          </button>
        ))}
      </div>

      <div
        style={{
          padding: "16px 22px",
          borderTop: "1px solid var(--slab-rule)",
          fontFamily: "var(--slab-font-mono)",
          fontSize: 9,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          color: "var(--slab-paper-ghost)",
        }}
      >
        <div>Paper only</div>
        <div style={{ marginTop: 2 }}>α · v4 · build 2026.07</div>
      </div>
    </aside>
  );
}
