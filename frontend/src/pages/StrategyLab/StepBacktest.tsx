import { useEffect, useState, useRef, useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Sparkles, RotateCcw, AlertCircle, FileText, ArrowUpDown, ArrowUp, ArrowDown, TrendingUp, CheckCircle } from "lucide-react";
import {
  strategyLabApi,
  type StrategySession,
  type ExperimentRow,
  type BatchStats,
  type SummarizeResponse,
  type RefineStrategyResponse,
} from "../../lib/strategyLab";
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

interface StepBacktestProps {
  session: StrategySession;
  onWinnerPicked: (experimentId: string) => void;
}

export function StepBacktest({ session, onWinnerPicked }: StepBacktestProps) {
  const [nRuns, setNRuns] = useState(10);
  const [endDate, setEndDate] = useState("2026-06-01");
  const [startDateMin, setStartDateMin] = useState("2000-01-01");
  const [startDateMax, setStartDateMax] = useState("2020-01-01");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<ExperimentRow[]>([]);
  const [stats, setStats] = useState<BatchStats | null>(null);
  const [progress, setProgress] = useState({ completed: 0, total: 0, failed: 0 });
  const [summary, setSummary] = useState<SummarizeResponse | null>(null);
  const [refine, setRefine] = useState<RefineStrategyResponse | null>(null);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [refineStep, setRefineStep] = useState<"idle" | "input" | "review" | "done">("idle");
  const [refineFollowUp, setRefineFollowUp] = useState("");
  const [selectedWinner, setSelectedWinner] = useState<string | null>(null);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [equityExperimentId, setEquityExperimentId] = useState<string | null>(null);
  // Save the exact start dates from the first batch so refinement reuses them (apples-to-apples)
  const [previousStartDates, setPreviousStartDates] = useState<string[] | null>(null);

  const equityCurve = useQuery({
    queryKey: ["equity-curve", equityExperimentId],
    queryFn: () => strategyLabApi.getEquityCurve(equityExperimentId!),
    enabled: !!equityExperimentId,
  });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // On mount, load existing experiments so navigating back shows previous results
  useEffect(() => {
    let cancelled = false;
    strategyLabApi.listExperiments(session.id).then((rows) => {
      if (cancelled || rows.length === 0) return;
      // Find the most recent batch_id
      const batchIds = [...new Set(rows.map((r) => r.batch_id))];
      const latestBatchId = batchIds[0];
      const batchRows = rows.filter((r) => r.batch_id === latestBatchId);
      setBatchId(latestBatchId);
      setExperiments(batchRows);
      setNRuns(batchRows.length);
      setProgress({
        completed: batchRows.filter((r) => r.status === "completed").length,
        total: batchRows.length,
        failed: batchRows.filter((r) => r.status === "failed").length,
      });
      // Load stats for the latest batch
      strategyLabApi.getBatchStats(session.id, latestBatchId).then((s) => {
        if (!cancelled) setStats(s);
      }).catch(() => {});
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [session.id]);

  const start = useMutation({
    mutationFn: () => {
      // If we have fixed start dates from a previous batch (e.g. after refinement),
      // pass them so the new batch runs on the exact same time windows.
      // This enables apples-to-apples comparison of strategy changes.
      const body: {
        n_runs: number; end_date: string;
        start_date_min?: string; start_date_max?: string;
        fixed_start_dates?: string[]; model?: string;
      } = {
        n_runs: nRuns,
        end_date: endDate,
        start_date_min: startDateMin,
        start_date_max: startDateMax,
      };
      if (previousStartDates && previousStartDates.length > 0) {
        body.fixed_start_dates = previousStartDates;
      }
      return strategyLabApi.startExperiments(session.id, body);
    },
    onSuccess: (r) => {
      setBatchId(r.batch_id);
      setExperiments([]);
      setStats(null);
      setSummary(null);
      setRefine(null);
      setSelectedWinner(null);
      setProgress({ completed: 0, total: nRuns, failed: 0 });
    },
  });

  useEffect(() => {
    if (!batchId) return;
    const poll = async () => {
      try {
        const [rows, s] = await Promise.all([
          strategyLabApi.listBatchExperiments(session.id, batchId),
          strategyLabApi.getBatchStats(session.id, batchId),
        ]);
        setExperiments(rows);
        setStats(s);
        setProgress({ completed: s.n_completed, total: s.n_total, failed: s.n_failed });
        // Save start dates once the batch completes (for apples-to-apples comparison on refinement)
        if (s.n_completed + s.n_failed >= nRuns && rows.length > 0) {
          const dates = rows
            .filter((r) => r.start_date)
            .map((r) => r.start_date!.slice(0, 10))
            .sort((a, b) => (a < b ? -1 : 1));
          if (dates.length > 0) {
            setPreviousStartDates(dates);
          }
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch {
        // ignore transient poll errors
      }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batchId, nRuns, session.id]);

  const summarize = useMutation({
    mutationFn: () => strategyLabApi.summarizeBatch(session.id, batchId!, { model: session.model_id }),
    onSuccess: (r) => setSummary(r),
  });

  const refineMut = useMutation({
    mutationFn: (instruction: string) =>
      strategyLabApi.refineAfterBatch(session.id, batchId!, {
        model: session.model_id,
        instruction,
      }),
    onSuccess: (r) => {
      setRefine(r);
      setRefineStep("review");
    },
  });

  const apply = useMutation({
    mutationFn: async (_code: string) => {
      // Code is already saved by the refine endpoint — this is a no-op
      // that just updates UI state
      return;
    },
    onSuccess: () => {
      setApplyError(null);
    },
    onError: (e) => {
      const err = e as { detail?: unknown; message?: string };
      const d = err.detail;
      if (typeof d === "object" && d !== null) {
        const obj = d as { details?: string };
        setApplyError(obj.details || JSON.stringify(d));
      } else if (typeof d === "string") {
        setApplyError(d);
      } else {
        setApplyError(err.message || "Apply failed");
      }
    },
  });

  const isRunning = !!batchId && progress.completed + progress.failed < nRuns;
  const isDone = !!batchId && !isRunning;

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 04 · Backtest</div>
          <h1 className="slab-page-head__title">Validate it.</h1>
          <p className="slab-page-head__lede">
            Run randomized as-of-date windows to see how the strategy holds
            up across regimes. Pick the best run, then deploy.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Validate</span>
          <span
            className={
              isRunning
                ? "slab-status slab-status--live"
                : isDone
                  ? "slab-status slab-status--terminal"
                  : "slab-status slab-status--dim"
            }
          >
            <span className="slab-status__dot" />
            {isRunning ? "RUNNING" : isDone ? "COMPLETE" : "IDLE"}
          </span>
        </div>
      </div>

      <div className="slab-page-body">
        {!batchId && (
          <ConfigForm
            nRuns={nRuns}
            setNRuns={setNRuns}
            endDate={endDate}
            setEndDate={setEndDate}
            startDateMin={startDateMin}
            setStartDateMin={setStartDateMin}
            startDateMax={startDateMax}
            setStartDateMax={setStartDateMax}
            onStart={() => start.mutate()}
            isStarting={start.isPending}
            error={start.error as Error | null}
          />
        )}

        {batchId && (
          <>
            <LiveTicker
              completed={progress.completed}
              total={progress.total}
              failed={progress.failed}
              isRunning={isRunning}
              batchId={batchId}
            />

            {/* All-failed banner */}
            {isDone && progress.failed > 0 && progress.completed === 0 && (
              <div
                className="slab-panel"
                style={{ maxWidth: 1280, marginTop: 16, borderColor: "var(--slab-rose)", backgroundColor: "color-mix(in srgb, var(--slab-rose) 8%, transparent)" }}
              >
                <div style={{ padding: 16, display: "flex", alignItems: "flex-start", gap: 12 }}>
                  <AlertCircle size={18} style={{ color: "var(--slab-rose)", flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 14, color: "var(--slab-rose)", marginBottom: 4 }}>
                      All {progress.total} experiments failed
                    </div>
                    <p style={{ fontSize: 13, color: "var(--slab-paper-subtle)", lineHeight: 1.5 }}>
                      Every run returned an error. This usually means the strategy code has a bug —
                      check the <strong>error messages</strong> in the <strong>Status</strong> column below
                      for details. Common causes: missing imports, database query errors, or division by zero.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {experiments.length > 0 && (
              <ExperimentTable
                rows={experiments}
                selectedWinner={selectedWinner}
                onPick={(id) => {
                  setSelectedWinner(id);
                  onWinnerPicked(id);
                }}
                onShowEquity={(id) => setEquityExperimentId(id)}
              />
            )}

            {/* Equity curve chart */}
            {equityCurve.data && equityCurve.data.equity_curve.length > 0 && (
              <div className="slab-panel" style={{ maxWidth: 1280, marginTop: 16 }}>
                <div className="slab-panel__head">
                  <span className="slab-eyebrow slab-eyebrow--gold">
                    <TrendingUp size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
                    Equity Curve
                  </span>
                  <button
                    type="button"
                    onClick={() => setEquityExperimentId(null)}
                    className="slab-btn slab-btn--xs slab-btn--ghost"
                  >
                    Close
                  </button>
                </div>
                <div style={{ padding: 16 }}>
                  <svg viewBox="0 0 800 240" style={{ width: "100%", height: 240 }}>
                    {(() => {
                      const pts = equityCurve.data.equity_curve;
                      const values = pts.map((p) => p.value);
                      const min = Math.min(...values);
                      const max = Math.max(...values);
                      const range = max - min || 1;
                      const w = 800;
                      const h = 220;
                      const pad = 10;
                      const path = pts
                        .map((p, i) => {
                          const x = pad + (i / (pts.length - 1)) * (w - 2 * pad);
                          const y = pad + h - ((p.value - min) / range) * (h - 2 * pad);
                          return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
                        })
                        .join(" ");
                      const color = values[values.length - 1] >= values[0] ? "var(--slab-terminal)" : "var(--slab-rose)";
                      return <path d={path} fill="none" stroke={color} strokeWidth={2} />;
                    })()}
                  </svg>
                </div>
              </div>
            )}

            {isDone && stats && stats.n_completed > 0 && (
              <>
                <PostBatchActions
                  onSummarize={() => summarize.mutate()}
                  isSummarizing={summarize.isPending}
                  onRefine={() => refineMut.mutate()}
                  isRefining={refineMut.isPending}
                  onAnotherBatch={() => { setBatchId(null); setPreviousStartDates(null); }}
                  summary={summary}
                  refine={refine}
                  onAcceptRefine={(d) => apply.mutate(d)}
                  onRejectRefine={() => { setRefine(null); setRefineStep("idle"); }}
                  isApplying={apply.isPending}
                  applyError={applyError}
                  // NEW props
                  refineInstruction={refineInstruction}
                  setRefineInstruction={setRefineInstruction}
                  refineStep={refineStep}
                  setRefineStep={setRefineStep}
                  refineFollowUp={refineFollowUp}
                  setRefineFollowUp={setRefineFollowUp}
                  onRefineWithInstruction={(instruction) => refineMut.mutate(instruction)}
                  isRefining={refineMut.isPending}
                  onReRun={() => {
                    setBatchId(null);
                    setTimeout(() => start.mutate(), 100);
                  }}
                />
                <ChatPanel
                  sessionId={session.id}
                  defaultModelId={session.model_id}
                />
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}

// ── Configuration form ─────────────────────────────────────────────────
function ConfigForm(props: {
  nRuns: number; setNRuns: (n: number) => void;
  endDate: string; setEndDate: (s: string) => void;
  startDateMin: string; setStartDateMin: (s: string) => void;
  startDateMax: string; setStartDateMax: (s: string) => void;
  onStart: () => void; isStarting: boolean; error: Error | null;
}) {
  return (
    <div style={{ maxWidth: 920 }}>
      <div
        className="slab-eyebrow"
        style={{ marginBottom: 16, color: "var(--slab-paper-faint)" }}
      >
        // Batch parameters
      </div>
      <div className="slab-grid-4">
        <div className="slab-field">
          <label className="slab-field__label">Runs</label>
          <input
            type="number"
            min={1}
            max={500}
            value={props.nRuns}
            onChange={(e) => props.setNRuns(Math.max(1, Math.min(500, parseInt(e.target.value) || 1)))}
            className="slab-input"
            style={{ fontSize: 16 }}
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">End date</label>
          <input
            type="date"
            value={props.endDate}
            onChange={(e) => props.setEndDate(e.target.value)}
            className="slab-input"
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">Start min</label>
          <input
            type="date"
            value={props.startDateMin}
            onChange={(e) => props.setStartDateMin(e.target.value)}
            className="slab-input"
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">Start max</label>
          <input
            type="date"
            value={props.startDateMax}
            onChange={(e) => props.setStartDateMax(e.target.value)}
            className="slab-input"
          />
        </div>
      </div>

      <div style={{ marginTop: 28, display: "flex", alignItems: "center", gap: 16 }}>
        <button
          type="button"
          onClick={props.onStart}
          disabled={props.isStarting}
          className="slab-btn slab-btn--terminal"
          style={{ padding: "12px 24px" }}
        >
          <Play size={12} fill="currentColor" />
          {props.isStarting ? "Starting…" : `Start ${props.nRuns}-run batch`}
        </button>
        {props.error && (
          <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <AlertCircle size={12} />
            {String(props.error?.message ?? "Failed to start")}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Live ticker — three big numbers + a progress bar ──────────────────
function LiveTicker({ completed, total, failed, isRunning, batchId }: {
  completed: number; total: number; failed: number; isRunning: boolean; batchId: string;
}) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="slab-panel" style={{ maxWidth: 1280 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">// Live</span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">batch · {batchId.slice(0, 8)}</span>
      </div>
      <div style={{ padding: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr) auto", gap: 32, alignItems: "center" }}>
        <div>
          <div className="slab-ticker__label">Completed</div>
          <div className="slab-ticker">
            <span className="slab-ticker--gold">{String(completed).padStart(3, "0")}</span>
            <span className="slab-mono slab-mono--lg slab-mono--faint">/{total}</span>
          </div>
        </div>
        <div>
          <div className="slab-ticker__label">Failed</div>
          <div className="slab-ticker">
            <span style={{ color: failed > 0 ? "var(--slab-rose)" : "var(--slab-paper-faint)" }}>
              {String(failed).padStart(3, "0")}
            </span>
          </div>
        </div>
        <div>
          <div className="slab-ticker__label">Progress</div>
          <div className="slab-ticker">
            {String(pct).padStart(2, "0")}<span className="slab-mono slab-mono--lg slab-mono--faint">%</span>
          </div>
        </div>
        <div>
          <span className={isRunning ? "slab-status slab-status--live" : "slab-status slab-status--terminal"}>
            <span className="slab-status__dot" />
            {isRunning ? "Running" : "Complete"}
          </span>
        </div>
      </div>
      {/* hairline progress bar */}
      <div style={{ height: 2, background: "var(--slab-rule)" }}>
        <motion.div
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
          style={{
            height: "100%",
            background: isRunning ? "var(--slab-gold)" : "var(--slab-terminal)",
            boxShadow: isRunning ? "0 0 12px var(--slab-gold-glow)" : "none",
          }}
        />
      </div>
    </div>
  );
}

// ── Experiments table with sorting ────────────────────────────────────
type SortKey = "run_index" | "start_date" | "total_return_pct" | "alpha_pct" | "win_rate" | "cagr_pct" | "sharpe_ratio" | "total_trades";
type SortDir = "asc" | "desc";

function ExperimentTable({ rows, selectedWinner, onPick, onShowEquity }: {
  rows: ExperimentRow[]; selectedWinner: string | null;
  onPick: (id: string) => void;
  onShowEquity: (id: string) => void;
}) {
  const [sortKey, setSortKey] = useState<SortKey>("run_index");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sorted = useMemo(() => {
    const copy = [...rows];
    const k = sortKey;
    const d = sortDir;
    copy.sort((a, b) => {
      let va: any, vb: any;
      if (k === "run_index") { va = a.run_index; vb = b.run_index; }
      else if (k === "start_date") { va = a.start_date || ""; vb = b.start_date || ""; }
      else { va = a.kpis?.[k]; vb = b.kpis?.[k]; }
      if (va == null) va = k === "run_index" ? 9999 : -999999;
      if (vb == null) vb = k === "run_index" ? 9999 : -999999;
      return d === "asc" ? (va > vb ? 1 : -1) : (va < vb ? 1 : -1);
    });
    return copy;
  }, [rows, sortKey, sortDir]);

  const SortIcon = ({ columnKey }: { columnKey: SortKey }) => {
    if (sortKey !== columnKey) return <ArrowUpDown size={10} style={{ opacity: 0.3, verticalAlign: "middle", marginLeft: 4 }} />;
    return sortDir === "asc"
      ? <ArrowUp size={10} style={{ verticalAlign: "middle", marginLeft: 4 }} />
      : <ArrowDown size={10} style={{ verticalAlign: "middle", marginLeft: 4 }} />;
  };

  const Th = ({ columnKey, children }: { columnKey: SortKey; children: React.ReactNode }) => (
    <th className="slab-table__num" onClick={() => handleSort(columnKey)} style={{ cursor: "pointer", userSelect: "none" }}>
      {children}<SortIcon columnKey={columnKey} />
    </th>
  );

  return (
    <div className="slab-panel" style={{ maxWidth: 1280, marginTop: 24 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">// Runs</span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">
          click <span style={{ color: "var(--slab-gold)" }}>pick</span> to mark the winner · click <span style={{ color: "var(--slab-cyan)" }}>chart</span> for equity curve
        </span>
      </div>
      <div style={{ maxHeight: 480, overflow: "auto" }}>
        <table className="slab-table">
          <thead>
            <tr>
              <th onClick={() => handleSort("run_index")} style={{ cursor: "pointer" }}>
                #<SortIcon columnKey="run_index" />
              </th>
              <th onClick={() => handleSort("start_date")} style={{ cursor: "pointer" }}>
                Start<SortIcon columnKey="start_date" />
              </th>
              <Th columnKey="total_return_pct">Return</Th>
              <Th columnKey="alpha_pct">Alpha</Th>
              <Th columnKey="win_rate">Win%</Th>
              <Th columnKey="cagr_pct">CAGR%</Th>
              <Th columnKey="total_trades">Trades</Th>
              <Th columnKey="sharpe_ratio">Sharpe</Th>
              <th>Status</th>
              <th></th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <ExperimentRowView
                key={row.id}
                row={row}
                isSelected={selectedWinner === row.id}
                onPick={() => onPick(row.id)}
                onShowEquity={() => onShowEquity(row.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExperimentRowView({ row, isSelected, onPick, onShowEquity }: {
  row: ExperimentRow; isSelected: boolean; onPick: () => void; onShowEquity: () => void;
}) {
  const k = row.kpis;
  const ret = k?.total_return_pct;
  return (
    <tr className={isSelected ? "slab-table__row--selected" : ""}>
      <td>{String(row.run_index).padStart(3, "0")}</td>
      <td>{row.start_date?.slice(0, 10) ?? "—"}</td>
      <td className="slab-table__num" style={{ color: ret != null && ret >= 0 ? "var(--slab-terminal)" : "var(--slab-rose)" }}>
        {ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%` : "—"}
      </td>
      <td className="slab-table__num">{k?.alpha_pct != null ? `${k.alpha_pct >= 0 ? "+" : ""}${k.alpha_pct.toFixed(1)}%` : "—"}</td>
      <td className="slab-table__num">{k?.win_rate != null ? `${k.win_rate.toFixed(1)}%` : "—"}</td>
      <td className="slab-table__num">{k?.cagr_pct != null ? `${k.cagr_pct.toFixed(1)}%` : "—"}</td>
      <td className="slab-table__num">{k?.total_trades ?? "—"}</td>
      <td className="slab-table__num">{k?.sharpe_ratio != null ? k.sharpe_ratio.toFixed(2) : "—"}</td>
      <td>
        {row.status === "completed" ? (
          <span className="slab-tag slab-tag--terminal">OK</span>
        ) : (
          <span className="slab-tag slab-tag--rose" title={row.error_message ?? ""}>
            FAIL
            {row.error_message && (
              <span style={{ display: "block", fontSize: 10, fontWeight: 400, marginTop: 2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {row.error_message}
              </span>
            )}
          </span>
        )}
      </td>
      <td>
        {row.status === "completed" && (
          <button
            type="button"
            onClick={onShowEquity}
            className="slab-btn slab-btn--xs slab-btn--ghost"
            title="Show equity curve"
          >
            <TrendingUp size={11} />
          </button>
        )}
      </td>
      <td>
        {row.status === "completed" && (
          <button
            type="button"
            onClick={onPick}
            className={`slab-btn slab-btn--xs ${isSelected ? "slab-btn--primary" : ""}`}
          >
            {isSelected ? "✓ Winner" : "Pick"}
          </button>
        )}
      </td>
    </tr>
  );
}

// ── Post-batch actions ────────────────────────────────────────────────
function PostBatchActions(props: {
  onSummarize: () => void; isSummarizing: boolean;
  onRefine: () => void; isRefining: boolean;
  onAnotherBatch: () => void;
  summary: SummarizeResponse | null;
  refine: RefineStrategyResponse | null;
  onAcceptRefine: (diff: string) => void; onRejectRefine: () => void;
  isApplying: boolean;
  applyError: string | null;
  // NEW props
  refineInstruction: string;
  setRefineInstruction: (v: string) => void;
  refineStep: "idle" | "input" | "review" | "done";
  setRefineStep: (v: "idle" | "input" | "review" | "done") => void;
  refineFollowUp: string;
  setRefineFollowUp: (v: string) => void;
  onRefineWithInstruction: (instruction: string) => void;
  isRefining: boolean;
  onReRun: () => void;
}) {
  return (
    <div style={{ maxWidth: 1280, marginTop: 32, display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="slab-eyebrow">// After batch</span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={props.onSummarize}
          disabled={props.isSummarizing}
          className="slab-btn"
        >
          <Sparkles size={11} />
          {props.isSummarizing ? "Analyzing…" : "AI summary"}
        </button>
        <button
          type="button"
          onClick={() => props.setRefineStep("input")}
          disabled={props.refineStep === "review" || props.refineStep === "done"}
          className="slab-btn"
        >
          <Sparkles size={11} />
          Refine strategy
        </button>
        <button
          type="button"
          onClick={props.onAnotherBatch}
          className="slab-btn slab-btn--ghost"
        >
          <RotateCcw size={11} />
          New batch
        </button>
      </div>

      <AnimatePresence>
        {props.summary && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">
                <FileText size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
                AI summary
              </span>
              <span className="slab-mono slab-mono--xs slab-mono--dim">3 paragraphs</span>
            </div>
            <div className="slab-panel__body">
              <p className="slab-prose" style={{ whiteSpace: "pre-wrap" }}>
                {props.summary.summary_text}
              </p>
            </div>
          </motion.div>
        )}

        {/* Step 1: Pre-refine input */}
        {props.refineStep === "input" && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">// Refine strategy</span>
              <span className="slab-mono slab-mono--xs slab-mono--dim">tell the AI what to focus on</span>
            </div>
            <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <textarea
                value={props.refineInstruction}
                onChange={(e) => props.setRefineInstruction(e.target.value)}
                rows={3}
                placeholder="e.g. reduce max drawdown, focus on improving Sharpe ratio, or leave empty for AI to decide"
                className="slab-textarea"
              />
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => props.onRefineWithInstruction(props.refineInstruction)}
                  disabled={props.isRefining}
                  className="slab-btn slab-btn--primary"
                >
                  {props.isRefining ? "Generating changes…" : "Generate changes"}
                </button>
                <button
                  type="button"
                  onClick={() => props.setRefineStep("idle")}
                  className="slab-btn slab-btn--ghost"
                >
                  Cancel
                </button>
              </div>
            </div>
          </motion.div>
        )}

        {/* Step 2: Review panel */}
        {props.refine && props.refineStep === "review" && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">// AI suggested changes</span>
              <span className="slab-mono slab-mono--xs slab-mono--dim">
                {props.refine.validation_status === "passed" ? "✓ validated" : props.refine.validation_status === "partial" ? "⚠ partial" : "✗ failed"}
              </span>
            </div>
            <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {/* Rationale */}
              {props.refine.rationale && (
                <p className="slab-prose" style={{ whiteSpace: "pre-wrap" }}>{props.refine.rationale}</p>
              )}

              {/* KPI Comparison Table */}
              {props.refine.before_kpis && props.refine.after_kpis && Object.keys(props.refine.before_kpis).length > 0 && (
                <div style={{ overflowX: "auto" }}>
                  <table className="slab-table" style={{ minWidth: 400 }}>
                    <thead>
                      <tr>
                        <th>Metric</th>
                        <th className="slab-table__num">Before</th>
                        <th className="slab-table__num">After</th>
                        <th className="slab-table__num">Δ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {["total_return_pct", "sharpe_ratio", "max_drawdown_pct", "win_rate", "total_trades"].map((key) => {
                        const before = props.refine!.before_kpis[key];
                        const after = props.refine!.after_kpis[key];
                        if (before == null && after == null) return null;
                        const b = typeof before === "number" ? before : 0;
                        const a = typeof after === "number" ? after : 0;
                        const delta = a - b;
                        const isPct = key.includes("_pct") || key === "win_rate";
                        const fmt = (v: number) => isPct ? `${v >= 0 ? "+" : ""}${v.toFixed(1)}%` : v.toFixed(2);
                        const label = key.replace(/_pct$/, "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
                        return (
                          <tr key={key}>
                            <td>{label}</td>
                            <td className="slab-table__num">{fmt(b)}</td>
                            <td className="slab-table__num" style={{ color: a >= b ? "var(--slab-terminal)" : "var(--slab-rose)" }}>{fmt(a)}</td>
                            <td className="slab-table__num" style={{ color: delta >= 0 ? "var(--slab-terminal)" : "var(--slab-rose)" }}>
                              {delta >= 0 ? "+" : ""}{fmt(delta)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Change summary */}
              {props.refine.summary && (
                <div style={{ padding: "10px 14px", background: "var(--slab-terminal-glow)", borderRadius: 6 }}>
                  <span className="slab-mono slab-mono--sm" style={{ color: "var(--slab-terminal)" }}>
                    {props.refine.summary}
                  </span>
                </div>
              )}

              {/* Validation log */}
              {props.refine.validation_log.length > 0 && (
                <div>
                  {props.refine.validation_log.map((entry, i) => (
                    <div key={i} className="slab-mono slab-mono--xs" style={{
                      color: entry.includes("FAILED") ? "var(--slab-rose)" : "var(--slab-paper-faint)",
                      padding: "2px 0",
                    }}>
                      {entry}
                    </div>
                  ))}
                </div>
              )}

              {/* Follow-up input */}
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <input
                  type="text"
                  value={props.refineFollowUp}
                  onChange={(e) => props.setRefineFollowUp(e.target.value)}
                  placeholder="Follow-up: make the trailing stop tighter..."
                  className="slab-input"
                  style={{ flex: 1, fontSize: 13 }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && props.refineFollowUp.trim()) {
                      props.onRefineWithInstruction(props.refineFollowUp);
                      props.setRefineFollowUp("");
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={() => {
                    props.onRefineWithInstruction(props.refineFollowUp);
                    props.setRefineFollowUp("");
                  }}
                  disabled={!props.refineFollowUp.trim() || props.isRefining}
                  className="slab-btn slab-btn--sm"
                >
                  Refine
                </button>
              </div>

              {/* Accept / Reject */}
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => {
                    props.onAcceptRefine(props.refine!.code);
                    props.setRefineStep("done");
                  }}
                  disabled={props.isApplying}
                  className="slab-btn slab-btn--primary"
                >
                  {props.isApplying ? "Applying…" : "Accept & Save"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    props.onRejectRefine();
                    props.setRefineStep("idle");
                  }}
                  className="slab-btn slab-btn--ghost"
                >
                  Reject
                </button>
              </div>

              {props.applyError && (
                <div className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <AlertCircle size={12} />
                  {props.applyError}
                </div>
              )}
            </div>
          </motion.div>
        )}

        {/* Step 3: Done — change applied */}
        {props.refineStep === "done" && props.refine && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">// Change applied</span>
            </div>
            <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <CheckCircle size={16} style={{ color: "var(--slab-terminal)" }} />
                <span className="slab-mono slab-mono--sm" style={{ color: "var(--slab-terminal)" }}>
                  {props.refine.version
                    ? `Change applied and saved as "${props.refine.version.strategy_name}"`
                    : "Change applied"}
                </span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={props.onReRun}
                  className="slab-btn slab-btn--terminal"
                >
                  <RotateCcw size={11} />
                  Re-run with same dates
                </button>
                <button
                  type="button"
                  onClick={() => props.setRefineStep("idle")}
                  className="slab-btn slab-btn--ghost"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
