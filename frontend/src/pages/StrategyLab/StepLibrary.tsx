import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { BookOpen, Download, Clock, GitBranch, TrendingUp, BarChart3 } from "lucide-react";
import { strategyLabApi, type LibraryListResponse } from "../../lib/strategyLab";

interface StepLibraryProps {
  onLoadSession: (sessionId: string) => void;
}

export function StepLibrary({ onLoadSession }: StepLibraryProps) {
  const { data: strategies, isLoading } = useQuery({
    queryKey: ["strategy-library"],
    queryFn: () => strategyLabApi.listLibrary(),
  });

  const load = useMutation({
    mutationFn: (name: string) => strategyLabApi.loadFromLibrary({ name }),
    onSuccess: (session) => {
      onLoadSession(session.id);
    },
  });

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// Library</div>
          <h1 className="slab-page-head__title">Saved strategies.</h1>
          <p className="slab-page-head__lede">
            Browse previously saved strategies. Click <span style={{ color: "var(--slab-gold)" }}>Load</span> to
            skip straight to the Code step — no need to re-enter the idea.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Browse</span>
          <span className="slab-mono slab-mono--gold">LIBRARY</span>
        </div>
      </div>

      <div className="slab-page-body">
        {isLoading && (
          <div className="slab-mono slab-mono--sm slab-mono--dim">Loading library…</div>
        )}

        {strategies && strategies.length === 0 && (
          <div style={{ textAlign: "center", padding: "64px 16px", color: "var(--slab-paper-faint)" }}>
            <BookOpen size={32} style={{ marginBottom: 12, opacity: 0.3 }} />
            <p className="slab-prose" style={{ fontSize: 14 }}>
              No saved strategies yet. Generate and validate a strategy, then save it to the library.
            </p>
          </div>
        )}

        {strategies && strategies.length > 0 && (
          <div style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 1280 }}>
            {strategies.map((s) => (
              <StrategyCard
                key={s.name}
                entry={s}
                onLoad={() => load.mutate(s.name)}
                isLoading={load.isPending}
              />
            ))}
          </div>
        )}

        {load.isError && (
          <div className="slab-mono slab-mono--sm slab-mono--rose" style={{ marginTop: 16 }}>
            Failed to load strategy: {String((load.error as Error)?.message ?? "Unknown error")}
          </div>
        )}
      </div>
    </>
  );
}

function StrategyCard({ entry, onLoad, isLoading }: {
  entry: LibraryListResponse;
  onLoad: () => void;
  isLoading: boolean;
}) {
  const latest = entry.latest_version;
  const kpis = latest.backtest_kpis || {};
  const ret = kpis.total_return_pct;
  const sharpe = kpis.sharpe_ratio;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="slab-panel"
    >
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
            <GitBranch size={12} style={{ color: "var(--slab-gold)" }} />
            <span className="slab-eyebrow slab-eyebrow--gold">
              {entry.display_name}
            </span>
            <span className="slab-mono slab-mono--xs slab-mono--dim">
              v{entry.version_count}
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", marginTop: 8 }}>
            {ret != null && (
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <TrendingUp size={11} style={{ color: ret >= 0 ? "var(--slab-terminal)" : "var(--slab-rose)" }} />
                <span className="slab-mono slab-mono--sm" style={{ color: ret >= 0 ? "var(--slab-terminal)" : "var(--slab-rose)" }}>
                  {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
                </span>
              </div>
            )}
            {sharpe != null && (
              <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <BarChart3 size={11} style={{ color: "var(--slab-paper-faint)" }} />
                <span className="slab-mono slab-mono--sm slab-mono--dim">Sharpe {sharpe.toFixed(2)}</span>
              </div>
            )}
            <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
              <Clock size={11} style={{ color: "var(--slab-paper-faint)" }} />
              <span className="slab-mono slab-mono--xs slab-mono--dim">
                {latest.created_at?.slice(0, 10)}
              </span>
            </div>
          </div>

          {latest.change_description && (
            <p className="slab-mono slab-mono--sm slab-mono--dim" style={{ marginTop: 8, fontStyle: "italic" }}>
              {latest.change_description}
            </p>
          )}

          {/* Version history */}
          {entry.versions.length > 1 && (
            <details style={{ marginTop: 12 }}>
              <summary className="slab-mono slab-mono--xs slab-mono--dim" style={{ cursor: "pointer" }}>
                {entry.versions.length} versions
              </summary>
              <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 4 }}>
                {entry.versions.slice().reverse().map((v) => (
                  <div key={v.version} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
                    <span className="slab-mono slab-mono--xs slab-mono--gold">v{v.version}</span>
                    <span className="slab-mono slab-mono--xs slab-mono--dim">{v.created_at?.slice(0, 10)}</span>
                    <span className="slab-mono slab-mono--xs slab-mono--faint" style={{ fontStyle: "italic" }}>
                      {v.change_description}
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </div>

        <button
          type="button"
          onClick={onLoad}
          disabled={isLoading}
          className="slab-btn"
          style={{ flexShrink: 0 }}
        >
          <Download size={11} />
          {isLoading ? "Loading…" : "Load"}
        </button>
      </div>
    </motion.div>
  );
}
