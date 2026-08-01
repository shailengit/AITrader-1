import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BookOpen, Terminal, BarChart3, Code } from "lucide-react";
import { strategyLabApi } from "../../lib/strategyLab";

interface StepLibraryProps {
  onSelectStrategy: (path: string) => void;
}

export function StepLibrary({ onSelectStrategy }: StepLibraryProps) {
  const { data: classes, isLoading } = useQuery({
    queryKey: ["strategy-classes"],
    queryFn: () => strategyLabApi.listStrategyClasses(),
  });

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// Library</div>
          <h1 className="slab-page-head__title">Available strategies.</h1>
          <p className="slab-page-head__lede">
            Select a strategy to backtest and deploy. To create a new strategy,
            open the <span style={{ color: "var(--slab-gold)" }}>terminal</span> and describe your idea to Claude Code.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Browse</span>
          <span className="slab-mono slab-mono--gold">STRATEGIES</span>
        </div>
      </div>

      <div className="slab-page-body">
        {isLoading && (
          <div className="slab-mono slab-mono--sm slab-mono--dim">Loading strategies…</div>
        )}

        {classes && classes.length === 0 && (
          <div style={{ textAlign: "center", padding: "64px 16px", color: "var(--slab-paper-faint)" }}>
            <BookOpen size={32} style={{ marginBottom: 12, opacity: 0.3 }} />
            <p className="slab-prose" style={{ fontSize: 14 }}>
              No strategies found. Open the terminal and use Claude Code to generate one.
            </p>
            <p className="slab-mono slab-mono--sm slab-mono--dim" style={{ marginTop: 8 }}>
              Generated strategies live in <code>backend/app/services/strategies/</code>
            </p>
          </div>
        )}

        {classes && classes.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1280 }}>
            {classes.map((c) => (
              <StrategyCard
                key={c.path}
                entry={c}
                onSelect={() => onSelectStrategy(c.path)}
              />
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function StrategyCard({ entry, onSelect }: {
  entry: { name: string; path: string; description: string };
  onSelect: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="slab-panel"
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <Code size={12} style={{ color: "var(--slab-gold)" }} />
            <span className="slab-eyebrow slab-eyebrow--gold">
              {entry.name}
            </span>
          </div>

          {entry.description && (
            <p className="slab-mono slab-mono--sm slab-mono--dim" style={{ marginTop: 4 }}>
              {entry.description}
            </p>
          )}

          <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
            <Terminal size={11} style={{ color: "var(--slab-paper-faint)" }} />
            <span className="slab-mono slab-mono--xs slab-mono--dim">
              {entry.path}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={onSelect}
          className="slab-btn"
          style={{ flexShrink: 0 }}
        >
          <BarChart3 size={11} />
          Backtest
        </button>
      </div>
    </motion.div>
  );
}
